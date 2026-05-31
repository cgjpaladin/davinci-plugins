# -*- coding: utf-8 -*-
"""License 系统 — 纯 Python 标准库。

机器指纹采集、凭证读写、HMAC 校验、云函数通信。

架构：Downie 风格 — 客户端不做验签，全部信任服务端。
"""
import hashlib
import hmac
import json
import os
import plistlib
import platform
import ssl
import stat
import subprocess
import time
import uuid
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Dict, Optional, Tuple

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════

# 云函数地址 — 环境变量优先，兜底读 shared/.env
BACKEND_URL = os.environ.get("WB_LICENSE_URL", "")

if not BACKEND_URL:
    # 尝试从 shared/.env 读取（达芬奇 Launcher 不会自动传环境变量）
    _env_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
    ]
    for _ep in _env_paths:
        try:
            with open(_ep) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("WB_LICENSE_URL="):
                        BACKEND_URL = line.split("=", 1)[1].strip().strip("\"'")
                        break
            if BACKEND_URL:
                break
        except FileNotFoundError:
            continue

# 凭证存储路径（3 份冗余）
def _get_credential_paths() -> list:
    """macOS 三份冗余路径"""
    home = Path.home()
    return [
        home / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "license.dat",
        home / "Library" / "Preferences" / "com.blackmagicdesign.resolve" / "license.dat",
        home / ".config" / "dv_license" / "license.dat",
    ]


# ═══════════════════════════════════════════
# T1: 机器指纹
# ═══════════════════════════════════════════

def get_machine_fingerprint() -> str:
    """采集 macOS 硬件特征，生成不可逆的 64 字符 SHA256 指纹。

    采集特征：IOPlatformUUID + MAC 地址 + Volume UUID + CPU 架构。
    两次 SHA256 哈希 + 固定盐值，保证唯一且不可逆。
    """
    raw_parts = []

    # 1. IOPlatformUUID（主板唯一标识）
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5
        )
        plist_data = plistlib.loads(result.stdout.encode("utf-8"))
        ioreg_uuid = plist_data.get("IOPlatformUUID", "")
        raw_parts.append(ioreg_uuid)
    except Exception:
        raw_parts.append("uuid_fallback")

    # 2. MAC 地址
    try:
        raw_parts.append(str(uuid.getnode()))
    except Exception:
        raw_parts.append("mac_fallback")

    # 3. Volume UUID
    try:
        result = subprocess.run(
            ["diskutil", "info", "/"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "Volume UUID:" in line:
                raw_parts.append(line.split(":", 1)[1].strip())
                break
        else:
            raw_parts.append("vol_fallback")
    except Exception:
        raw_parts.append("vol_fallback")

    # 4. CPU 架构
    raw_parts.append(platform.machine())

    # 拼接 → 两次 SHA256
    raw_str = "|".join(raw_parts)
    primary = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    final = hashlib.sha256(
        (primary + "DV_LICENSE_SALT_v1").encode("utf-8")
    ).hexdigest()
    return final


# ═══════════════════════════════════════════
# T2: 凭证读写 + 三备份
# ═══════════════════════════════════════════

def _protect_file(path: Path):
    """设置文件为系统隐藏 + 仅当前用户可读写"""
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    # macOS: chflags hidden
    os.chflags(path, stat.UF_HIDDEN)


def save_credential(data: dict) -> None:
    """将凭证写入三个冗余路径"""
    payload = json.dumps(data)
    for path in _get_credential_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
        _protect_file(path)


def load_credential() -> Optional[dict]:
    """从三份备份中读取一份合法凭证。

    优先级：第一个存在的 → 交叉校验（多数投票）。
    """
    paths = _get_credential_paths()
    valid = []

    for path in paths:
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                cred = json.load(f)
            # 基本格式校验
            if "payload" in cred and "signature" in cred:
                valid.append(cred)
        except Exception:
            continue

    if not valid:
        return None

    # 多数投票：取出现次数最多的那份
    best = max(valid, key=lambda c: sum(
        1 for v in valid if json.dumps(v, sort_keys=True) == json.dumps(c, sort_keys=True)
    ))
    return best


def cross_validate_and_repair() -> bool:
    """交叉校验三份备份，自动修复不一致的文件。

    返回 True 表示至少有一份合法凭证可用。
    """
    best = load_credential()
    if best is None:
        return False

    # 用最佳凭证修复所有路径
    for path in _get_credential_paths():
        try:
            if path.exists():
                with open(path, "r") as f:
                    existing = json.load(f)
                if json.dumps(existing, sort_keys=True) == json.dumps(best, sort_keys=True):
                    continue  # 一致，跳过
            # 不一致或不存在 → 写入
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(best, f)
            _protect_file(path)
        except Exception:
            pass

    return True


# ═══════════════════════════════════════════
# T3: HTTP 请求封装
# ═══════════════════════════════════════════

_SSL_CTX = ssl._create_unverified_context()


def _post_to_backend(endpoint: str, data: dict, timeout: int = 10) -> Tuple[bool, dict]:
    """向云函数发送 HTTPS POST，带重试。

    Returns:
        (success, response_dict) — response_dict 含 status/msg/token 等
    """
    url = BACKEND_URL + endpoint if BACKEND_URL else ""
    if not url:
        return False, {"msg": "未配置后端地址"}

    req_data = json.dumps(data).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DaVinciPlugin/2.2.1",
        "X-Platform": platform.system(),
        "X-Request-Nonce": os.urandom(16).hex(),
    }

    last_err = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url=url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                return True, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = str(e.reason)
        except Exception as e:
            last_err = str(e)
        time.sleep(1)  # 重试前等 1 秒

    return False, {"msg": f"请求失败({last_err})"}


# ═══════════════════════════════════════════
# T5: 高级 API
# ═══════════════════════════════════════════

def init_trial() -> Tuple[bool, str]:
    """首次试用初始化。

    采集指纹 → 发云函数 → 收凭证 → 本地存三份。

    Returns:
        (success, message)
    """
    if not BACKEND_URL:
        return False, "未配置授权后端（离线模式）"

    fp = get_machine_fingerprint()
    ok, resp = _post_to_backend("/license", {
        "action": "init_trial",
        "machine_fingerprint": fp,
    })
    if not ok:
        return False, resp.get("msg", "连接后端失败")

    if resp.get("status") != "ok":
        return False, resp.get("msg", "试用初始化失败")

    token = resp.get("license_token")
    if token:
        # token 是 JSON 字符串，解析后存
        if isinstance(token, str):
            token = json.loads(token)
        save_credential(token)

    return True, resp.get("msg", f"试用开始，剩余 {resp.get('trial_days', 30)} 天")


def activate(activate_key: str) -> Tuple[bool, str]:
    """激活正式授权。

    Returns:
        (success, message)
    """
    if not BACKEND_URL:
        return False, "未配置授权后端"

    fp = get_machine_fingerprint()
    ok, resp = _post_to_backend("/license", {
        "action": "activate",
        "activate_key": activate_key.strip().upper(),
        "machine_fingerprint": fp,
    })
    if not ok:
        return False, resp.get("msg", "连接后端失败")

    if resp.get("status") != "ok":
        return False, resp.get("msg", "激活失败")

    token = resp.get("license_token")
    if token:
        if isinstance(token, str):
            token = json.loads(token)
        save_credential(token)

    return True, resp.get("msg", "激活成功")


def verify_local() -> Tuple[bool, str]:
    """本地离线校验：仅检查宽限期时间戳。

    不验签、不连网。签名校验由下次心跳在服务端完成。

    Returns:
        (is_valid, message)
    """
    cred = load_credential()
    if cred is None:
        return False, "无授权凭证"

    payload = cred.get("payload", {})
    now = int(time.time())

    # 检查离线宽限期
    grant_end = payload.get("offline_grant_end", 0)
    if grant_end and now > grant_end:
        return False, f"离线宽限期已过（{time.strftime('%Y-%m-%d', time.localtime(grant_end))}），需联网同步"

    # 基础时间合理性检查
    issue = payload.get("issue_time", 0)
    expire = payload.get("expire_time", 0)
    if issue and now < issue - 86400:
        return False, "系统时间异常"

    return True, "凭证有效"


def heartbeat() -> Tuple[bool, str]:
    """月度心跳同步。

    上传本地凭证 + 最新指纹 → 服务端重签 → 更新本地三份。

    Returns:
        (success, message)
    """
    if not BACKEND_URL:
        return True, "离线模式，跳过心跳"

    cred = load_credential()
    fp = get_machine_fingerprint()

    ok, resp = _post_to_backend("/license", {
        "action": "heartbeat",
        "license_token": json.dumps(cred) if cred else "",
        "machine_fingerprint": fp,
    })
    if not ok:
        return False, resp.get("msg", "心跳失败")

    token = resp.get("license_token")
    if token:
        if isinstance(token, str):
            token = json.loads(token)
        save_credential(token)

    return True, resp.get("msg", "心跳成功")
