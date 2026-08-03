from __future__ import annotations
#!/usr/bin/env python3
"""API Key 安全存储：macOS Keychain（主）→ chmod 600 文件（兜底）。

零外部依赖（只用标准库）。"""
import json, os, stat, subprocess, sys

_SERVICE  = "达芬奇插件工坊/交付自检工具"
_IS_MACOS = sys.platform == "darwin"

# api_keys.json 路径（多产品共享一套 Keychain，文件仅兜底用）
if _IS_MACOS:
    _LEGACY = os.path.join(os.path.expanduser("~/Library/Application Support/交付自检"), "api_keys.json")
else:
    _LEGACY = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "交付自检", "api_keys.json")

# ── macOS Keychain ────────────────────────────────────────────
def _macos_keychain_save(account: str, password: str):
    subprocess.run(["security", "add-generic-password",
                    "-s", _SERVICE, "-a", account, "-w", password, "-U"],
                   capture_output=True, check=False)

def _macos_keychain_load(account: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password",
                        "-s", _SERVICE, "-a", account, "-w"],
                       capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None

def _macos_keychain_delete(account: str):
    subprocess.run(["security", "delete-generic-password",
                    "-s", _SERVICE, "-a", account],
                   capture_output=True, check=False)

# ── 文件兜底（chmod 600）──────────────────────────────────────
def _file_save(key: str, value: str):
    data = {}
    if os.path.exists(_LEGACY):
        try:
            with open(_LEGACY, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data[key] = value
    os.makedirs(os.path.dirname(_LEGACY), exist_ok=True)
    with open(_LEGACY, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(_LEGACY, stat.S_IRUSR | stat.S_IWUSR)  # 600

def _file_load(key: str) -> str | None:
    if not os.path.exists(_LEGACY):
        return None
    try:
        with open(_LEGACY, encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key)
    except Exception:
        return None

def _file_delete(key: str):
    if not os.path.exists(_LEGACY):
        return
    try:
        with open(_LEGACY, encoding="utf-8") as f:
            data = json.load(f)
        data.pop(key, None)
        with open(_LEGACY, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(_LEGACY, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

# ── 公共接口 ──────────────────────────────────────────────────

def save(name: str, value: str):
    """保存一个凭证。macOS → Keychain；其他 → chmod 600 文件。"""
    value = str(value)  # 防御：int/float 转字符串，避免 subprocess 崩
    if _IS_MACOS:
        _macos_keychain_save(name, value)
    else:
        _file_save(name, value)

def load(name: str) -> str | None:
    """读取凭证。macOS → Keychain；其他 → 文件。"""
    if _IS_MACOS:
        return _macos_keychain_load(name)
    return _file_load(name)

def delete(name: str):
    """删除凭证。"""
    if _IS_MACOS:
        _macos_keychain_delete(name)
    else:
        _file_delete(name)

def load_all() -> dict:
    """读取全部凭证，返回 {name: value}。"""
    if _IS_MACOS:
        result = {}
        for k in ("deepseek_key", "feishu_app_id", "feishu_secret", "activation_code"):
            v = _macos_keychain_load(k)
            if v:
                result[k] = v
        return result
    else:
        try:
            with open(_LEGACY, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def migrate_legacy():
    """迁移：api_keys.json → Keychain。运行一次即可，幂等。"""
    if not _IS_MACOS:
        return
    legacy = load_all() if not _IS_MACOS else {}
    # 也读文件版兜底
    if os.path.exists(_LEGACY):
        try:
            with open(_LEGACY, encoding="utf-8") as f:
                legacy.update(json.load(f))
        except Exception:
            pass
    for k, v in legacy.items():
        if v:
            _macos_keychain_save(k, v)
    if legacy:
        os.rename(_LEGACY, _LEGACY + ".migrated")
