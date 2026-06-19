# -*- coding: utf-8 -*-
"""License 后端 — Python 标准库（未部署，仅作参考）。

当前在线后端是 cloud/license_fc.js（阿里云 FC + 飞书 Base）。
此文件 SQLite 方案从未上线。

处理动作：
  init_trial  → 初始化试用（首次）
  activate    → 激活正式授权
  heartbeat   → 月度心跳同步

安全：HMAC-SHA256 签名，密钥在云函数环境变量 HMAC_SECRET。
数据库：SQLite（免费内置），单文件 db.sqlite3。
"""
import hashlib
import hmac
import json
import os
import sqlite3
import time
import urllib.parse
from typing import Dict, Tuple


# ═══════════════════════════════════════════
# 配置（云函数环境变量）
# ═══════════════════════════════════════════

ADMIN_KEY = os.environ.get("ADMIN_KEY", "").encode("utf-8")

HMAC_SECRET = os.environ.get("HMAC_SECRET", "CHANGE_ME_IN_SCF_ENV").encode("utf-8")
DB_PATH = os.environ.get("DB_PATH", "/tmp/license.db")
TRIAL_DAYS = 30            # 试用天数
OFFLINE_GRANT_DAYS = 30    # 离线宽限期
HEARTBEAT_GRACE_HOURS = 1  # 心跳去重窗口


# ═══════════════════════════════════════════
# 数据库
# ═══════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _init_db():
    """建表（幂等）"""
    db = _get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS keys (
            activate_key TEXT PRIMARY KEY,
            status TEXT DEFAULT 'available',   -- available | sold | activated | revoked
            max_devices INTEGER DEFAULT 1,
            is_enterprise INTEGER DEFAULT 0,
            created_at INTEGER,
            sold_at INTEGER,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activate_key TEXT,
            machine_fingerprint TEXT,
            issue_time INTEGER,
            expire_time INTEGER,
            offline_grant_end INTEGER,
            platform TEXT,
            nonce TEXT,
            products TEXT DEFAULT '{}',
            fail_count INTEGER DEFAULT 0,
            last_heartbeat INTEGER,
            UNIQUE(activate_key, machine_fingerprint)
        );

        CREATE TABLE IF NOT EXISTS trials (
            machine_fingerprint TEXT PRIMARY KEY,
            trial_start INTEGER,
            trial_end INTEGER,
            offline_grant_end INTEGER,
            platform TEXT,
            created_at INTEGER
        );
    """)
    db.commit()


# ═══════════════════════════════════════════
# HMAC 签名
# ═══════════════════════════════════════════

def _sign(payload: dict) -> str:
    """HMAC-SHA256 签名"""
    items = sorted(payload.items(), key=lambda x: x[0])
    sign_str = "&".join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in items])
    return hmac.new(HMAC_SECRET, sign_str.encode("utf-8"), hashlib.sha256).hexdigest()


def _make_token(payload: dict) -> str:
    """生成完整凭证：payload + signature"""
    signature = _sign(payload)
    return json.dumps({"payload": payload, "signature": signature})


# ═══════════════════════════════════════════
# 业务逻辑
# ═══════════════════════════════════════════

def _handle_init_trial(data: dict) -> dict:
    """首次试用初始化"""
    fp = data.get("machine_fingerprint", "")
    if not fp:
        return {"status": "error", "msg": "机器指纹为空"}
    platform_val = data.get("platform", "unknown")

    db = _get_db()
    # 检查是否已试用过
    existing = db.execute("SELECT * FROM trials WHERE machine_fingerprint = ?", (fp,)).fetchone()
    if existing:
        # 已试用——返回已有凭证
        now = int(time.time())
        if now > existing["trial_end"]:
            return {"status": "error", "msg": "试用已结束，请购买正式授权"}
        payload = {
            "activate_key": "",
            "machine_fingerprint": fp,
            "issue_time": existing["trial_start"],
            "expire_time": existing["trial_end"],
            "offline_grant_end": existing["offline_grant_end"],
            "nonce": os.urandom(8).hex(),
            "platform": platform_val,
            "products": {},
            "is_trial": True,
        }
        return {"status": "ok", "msg": f"试用中，剩余 {max(0,(existing['trial_end']-now)//86400)} 天",
                "license_token": _make_token(payload), "trial_days": max(0, (existing["trial_end"]-now)//86400)}

    # 首次试用
    now = int(time.time())
    trial_end = now + TRIAL_DAYS * 86400
    grant_end = now + OFFLINE_GRANT_DAYS * 86400

    db.execute(
        "INSERT INTO trials (machine_fingerprint, trial_start, trial_end, offline_grant_end, platform, created_at) VALUES (?,?,?,?,?,?)",
        (fp, now, trial_end, grant_end, platform_val, now)
    )
    db.commit()

    payload = {
        "activate_key": "",
        "machine_fingerprint": fp,
        "issue_time": now,
        "expire_time": trial_end,
        "offline_grant_end": grant_end,
        "nonce": os.urandom(8).hex(),
        "platform": platform_val,
        "products": {},
        "is_trial": True,
    }
    return {"status": "ok", "msg": f"试用开始，剩余 {TRIAL_DAYS} 天",
            "license_token": _make_token(payload), "trial_days": TRIAL_DAYS}


def _handle_activate(data: dict) -> dict:
    """激活正式授权"""
    key = data.get("activate_key", "").strip().upper()
    fp = data.get("machine_fingerprint", "")
    platform_val = data.get("platform", "unknown")

    if not key or not fp:
        return {"status": "error", "msg": "参数不完整"}

    db = _get_db()

    # 校验激活码
    row = db.execute("SELECT * FROM keys WHERE activate_key = ?", (key,)).fetchone()
    if not row:
        return {"status": "error", "msg": "激活码无效"}
    if row["status"] not in ("sold", "gifted", "activated"):
        return {"status": "error", "msg": f"激活码状态异常（{row['status']}）"}

    # 检查是否已绑定其他设备
    lic = db.execute("SELECT * FROM licenses WHERE activate_key = ?", (key,)).fetchone()
    if lic and lic["machine_fingerprint"] != fp:
        # 自动迁移：解绑旧设备
        db.execute("DELETE FROM licenses WHERE activate_key = ?", (key,))

    now = int(time.time())
    expire_time = now + 365 * 86400 * 10  # 10 年买断
    grant_end = now + OFFLINE_GRANT_DAYS * 86400

    # 查询该激活码对应的产品（当前默认全部解锁）
    products = {"delivery_checker": True}

    db.execute(
        """INSERT OR REPLACE INTO licenses
           (activate_key, machine_fingerprint, issue_time, expire_time, offline_grant_end, platform, nonce, products, fail_count, last_heartbeat)
           VALUES (?,?,?,?,?,?,?,?,0,?)""",
        (key, fp, now, expire_time, grant_end, platform_val, os.urandom(8).hex(), json.dumps(products), now)
    )
    # 标记 Key 已激活
    db.execute("UPDATE keys SET status = 'activated' WHERE activate_key = ?", (key,))
    db.commit()

    payload = {
        "activate_key": key,
        "machine_fingerprint": fp,
        "issue_time": now,
        "expire_time": expire_time,
        "offline_grant_end": grant_end,
        "nonce": os.urandom(8).hex(),
        "platform": platform_val,
        "products": products,
        "is_trial": False,
    }
    return {"status": "ok", "msg": "激活成功",
            "license_token": _make_token(payload)}


def _handle_heartbeat(data: dict) -> dict:
    """月度心跳"""
    fp = data.get("machine_fingerprint", "")
    if not fp:
        return {"status": "error", "msg": "机器指纹为空"}

    db = _get_db()
    now = int(time.time())
    grant_end = now + OFFLINE_GRANT_DAYS * 86400

    # 查正式授权
    lic = db.execute(
        "SELECT * FROM licenses WHERE machine_fingerprint = ? ORDER BY last_heartbeat DESC LIMIT 1",
        (fp,)
    ).fetchone()

    if lic:
        # 正式授权：刷新宽限期
        db.execute(
            "UPDATE licenses SET offline_grant_end = ?, last_heartbeat = ?, fail_count = 0 WHERE id = ?",
            (grant_end, now, lic["id"])
        )
        db.commit()

        payload = {
            "activate_key": lic["activate_key"],
            "machine_fingerprint": fp,
            "issue_time": lic["issue_time"],
            "expire_time": lic["expire_time"],
            "offline_grant_end": grant_end,
            "nonce": os.urandom(8).hex(),
            "platform": lic["platform"],
            "products": json.loads(lic["products"]) if lic["products"] else {},
            "is_trial": False,
        }
        return {"status": "ok", "msg": "心跳成功", "license_token": _make_token(payload)}

    # 查试用记录
    trial = db.execute("SELECT * FROM trials WHERE machine_fingerprint = ?", (fp,)).fetchone()
    if trial:
        if now > trial["trial_end"]:
            return {"status": "error", "msg": "试用已结束"}
        db.execute(
            "UPDATE trials SET offline_grant_end = ? WHERE machine_fingerprint = ?",
            (grant_end, fp)
        )
        db.commit()
        payload = {
            "activate_key": "",
            "machine_fingerprint": fp,
            "issue_time": trial["trial_start"],
            "expire_time": trial["trial_end"],
            "offline_grant_end": grant_end,
            "nonce": os.urandom(8).hex(),
            "platform": trial["platform"] if "platform" in trial.keys() else "unknown",
            "products": {},
            "is_trial": True,
        }
        return {"status": "ok", "msg": "心跳成功", "license_token": _make_token(payload)}

    return {"status": "error", "msg": "未找到授权记录"}


def _handle_manage(data: dict) -> dict:
    """管理操作：生成激活码（需 ADMIN_KEY 验证）"""
    key = data.get("admin_key", "")
    if not key or key.encode("utf-8") != ADMIN_KEY:
        return {"status": "error", "msg": "管理密钥错误"}
    action = data.get("manage_action", "")
    if action == "gen_key":
        new_key = os.urandom(6).hex().upper()
        formatted = f"{new_key[:4]}-{new_key[4:8]}-{new_key[8:12]}"
        db = _get_db()
        db.execute(
            "INSERT OR IGNORE INTO keys (activate_key, status, created_at) VALUES (?, 'sold', ?)",
            (formatted, int(time.time()))
        )
        db.commit()
        return {"status": "ok", "key": formatted, "msg": f"激活码已生成: {formatted}"}
    elif action == "list_keys":
        db = _get_db()
        rows = db.execute("SELECT * FROM keys ORDER BY created_at DESC LIMIT 20").fetchall()
        return {"status": "ok", "keys": [dict(r) for r in rows]}
    elif action == "delete_trial":
        fp = data.get("machine_fingerprint", "")
        if fp:
            db = _get_db()
            db.execute("DELETE FROM trials WHERE machine_fingerprint = ?", (fp,))
            db.commit()
            return {"status": "ok", "msg": f"已删除试用记录: {fp[:16]}..."}
        return {"status": "error", "msg": "缺少 machine_fingerprint"}
    else:
        return {"status": "error", "msg": f"未知管理操作: {action}"}


# ═══════════════════════════════════════════
# SCF 入口
# ═══════════════════════════════════════════

ROUTES = {
    "init_trial": _handle_init_trial,
    "activate": _handle_activate,
    "heartbeat": _handle_heartbeat,
    "manage": _handle_manage,
}


def main_handler(event, context):
    """腾讯云 SCF 标准入口"""
    _init_db()

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"status": "error", "msg": "请求格式错误"})}

    action = body.get("action", "")
    handler = ROUTES.get(action)

    if not handler:
        return {"statusCode": 400, "body": json.dumps({"status": "error", "msg": f"未知动作: {action}"})}

    result = handler(body)
    status_code = 200 if result.get("status") == "ok" else 401
    return {"statusCode": status_code, "body": json.dumps(result, ensure_ascii=False)}
