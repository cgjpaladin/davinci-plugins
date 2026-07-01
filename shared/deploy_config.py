"""部署配置统一入口。

取代各产品目录中分散复制的 _load_deploy_config() / _read_smb_mount()。
单一来源：<系统级插件目录>/deploy.json
"""
import json as _json
import os as _os

_INSTALL_DIR = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具"


def load() -> dict:
    """读取 deploy.json，不存在返回空 dict。"""
    cfg_path = _os.path.join(_INSTALL_DIR, "deploy.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}


def get_smb_mount(default="/Volumes/MYJC") -> str:
    """读取 SMB 挂载点（向后兼容）。"""
    cfg = load()
    return cfg.get("smb_mount", default) or default


def get_smb_paths() -> list:
    """读取服务器素材路径列表。支持旧版 smb_mount 单字符串自动迁移。"""
    cfg = load()
    paths = cfg.get("smb_paths")
    if isinstance(paths, list):
        return [p for p in paths if isinstance(p, str) and p.strip()]
    return []


def save_smb_paths(paths: list) -> bool:
    """保存服务器素材路径列表到 deploy.json。"""
    cfg_path = _os.path.expanduser("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具/deploy.json")
    cfg = load()
    cfg["smb_paths"] = [p.strip() for p in paths if isinstance(p, str) and p.strip()]
    try:
        _os.makedirs(_os.path.dirname(cfg_path), exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            _json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_python_path() -> str:
    """自动发现外挂 Python 路径（用于 subprocess 启动 UI）。
    
    跳过达芬奇自带的 Python。优先取最新框架安装版。
    装好 Python 即可，无需 JSON 配置。
    """
    import glob as _glob

    candidates = []
    # 官版安装器：自动匹配 3.10~3.99，排序取最新
    candidates.extend(sorted(_glob.glob(
        "/Library/Frameworks/Python.framework/Versions/3.*/bin/python3"
    ), reverse=True))
    # Homebrew (Apple Silicon / Intel)
    candidates.extend(sorted(_glob.glob("/opt/homebrew/bin/python3*"), reverse=True))
    candidates.extend(sorted(_glob.glob("/usr/local/bin/python3*"), reverse=True))
    # 最后兜底
    candidates.append("/usr/bin/python3")

    for p in candidates:
        if not _os.path.exists(p):
            continue
        try:
            real = _os.path.realpath(p)
        except Exception:
            real = p
        if "/DaVinci Resolve/" in real:
            continue  # 跳过达芬奇自带的
        return p

    return "/usr/bin/python3"
