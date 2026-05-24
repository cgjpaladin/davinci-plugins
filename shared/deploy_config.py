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


def get_python_path(default="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3") -> str:
    """读取外挂 Python 路径（用于 subprocess 启动 UI）。
    
    每台机器在 deploy.json 中配置自己的 python_path。
    Python 版本升级时改 JSON 不动代码。
    """
    cfg = load()
    return cfg.get("python_path", default) or default
