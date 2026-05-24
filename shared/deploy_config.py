"""部署配置统一入口。

取代各产品目录中分散复制的 _load_deploy_config() / _read_smb_mount()。
单一来源：~/达芬奇插件工坊/deploy.json
"""
import json as _json
import os as _os


def load() -> dict:
    """读取 deploy.json，不存在返回空 dict。"""
    cfg_path = _os.path.expanduser("~/达芬奇插件工坊/deploy.json")
    try:
        with open(cfg_path) as f:
            return _json.load(f)
    except Exception:
        return {}


def get_smb_mount(default="/Volumes/MYJC") -> str:
    """读取 SMB 挂载点。"""
    cfg = load()
    return cfg.get("smb_mount", default) or default
