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

# 云函数地址 — 替换为腾讯云 SCF 部署后的真实 URL
BACKEND_URL = os.environ.get(
    "WB_LICENSE_URL",
    ""  # 待部署后填入
)

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
