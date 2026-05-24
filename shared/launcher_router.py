#!/usr/bin/env python3
# launcher_router.py — 达芬奇插件工坊 统一启动路由器（部署后永不更新）
# 每台机器一份，按主机名判断读本地开发版还是 SMB 稳定版：
#   Dev 机 → 本地开发目录
#   灰度名单 → SMB gray/
#   其他人 → SMB 根目录
#
# 路径来源：优先读 ~/达芬奇插件工坊/deploy.json，不存在则用默认值
#
# 用法:
#   import launcher_router; launcher_router.route("AI去字幕", ui_module="stable_ui")
import sys, os, json, socket


from deploy_config import load as _load_deploy_config

_deploy = _load_deploy_config()
_SMB_ROOT = _deploy.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_DEV_HOSTS = set(_deploy.get("dev_hosts", ["BryandeMac-mini.local", "BryandeMac-mini"]))
_DEV_DIR_BASE = os.path.expanduser(
    _deploy.get("dev_dir", "~/WorkBuddy/达芬奇插件工坊")
)


def route(product_name: str, ui_module: str = "ui"):
    """按 hostname 路由到正确的代码目录，然后启动 UI。

    Args:
        product_name: 产品目录名（如 "AI去字幕"、"交付自检工具"）
        ui_module:   UI 入口模块名（如 "stable_ui"、"ui"）
    """
    _SMB_BASE = os.path.join(_SMB_ROOT, product_name)
    _DEV_DIR = os.path.join(_DEV_DIR_BASE, product_name)
    _SHARED_DIR = os.path.join(_DEV_DIR_BASE, "shared")

    _host = socket.gethostname()
    _code_dir = _SMB_BASE

    if _host in _DEV_HOSTS:
        _code_dir = _DEV_DIR
        sys.path.insert(0, _SHARED_DIR)
    else:
        _gray_file = os.path.join(_SMB_BASE, "gray.json")
        try:
            with open(_gray_file) as f:
                gray = json.load(f)
            if _host in gray.get("gray", []):
                _code_dir = os.path.join(_SMB_BASE, "gray")
        except Exception:
            pass

    sys.path.insert(0, _code_dir)
    sys.path.insert(0, os.path.join(_SMB_ROOT, "shared"))

    # ── dry-run 自检 ──
    if "--dry-run" in sys.argv:
        import importlib
        print(f"═══ {product_name} 部署自检 ═══")
        checks = []
        v = sys.version_info
        checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))
        routing = "DEV" if _host in _DEV_HOSTS else "SMB"
        checks.append(("路由", True, f"{routing}: {_code_dir}"))
        for mod in ["config", ui_module]:
            try:
                importlib.import_module(mod)
                checks.append((mod, True, "OK"))
            except Exception as e:
                checks.append((mod, False, str(e)[:60]))
        try:
            from config import version_string
            checks.append(("版本", True, version_string()))
        except Exception:
            checks.append(("版本", False, "ERR"))
        ok = all(c[1] for c in checks)
        for name, passed, detail in checks:
            print(f"  {'✅' if passed else '❌'} {name}: {detail}")
        print(f"\n{'✅ 部署自检通过' if ok else '❌ 部署自检失败'}")
        sys.exit(0 if ok else 1)

    # ── 启动 UI ──
    _mod = __import__(ui_module)
    _mod.main()
