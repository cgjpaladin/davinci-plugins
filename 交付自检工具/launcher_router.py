#!/usr/bin/env python3
# 交付自检 — 启动器（部署后永不更新）
# 每台机器一份，按主机名判断读本地开发版还是 SMB 稳定版：
#   Bryan → 本地开发目录
#   灰度名单 → SMB gray/
#   其他人 → SMB 根目录
import sys, os, json, socket

_SCRIPT_NAME = "交付自检.py"
_DEV_HOSTS = {"BryandeMac-mini.local", "BryandeMac-mini"}  # 裁缝老师的机器
_SMB_BASE = "/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具"
_DEV_DIR = os.path.expanduser("~/WorkBuddy/达芬奇插件工坊/交付自检工具")
_SHARED_DIR = os.path.join(_DEV_DIR, "..", "shared")  # 本地开发用

_host = socket.gethostname()
_code_dir = _SMB_BASE
_shared_smb = os.path.join(_SMB_BASE, "..", "shared")  # SMB shared/

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
sys.path.insert(0, os.path.join(_SMB_BASE, "..", "shared"))  # SMB shared/ 模块

if "--dry-run" in sys.argv:
    import importlib
    print("═══ 交付自检 部署自检 ═══")
    checks = []
    v = sys.version_info
    checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))
    checks.append(("路由", True, f"{'DEV' if _host in _DEV_HOSTS else 'SMB'}: {_code_dir}"))
    for mod in ["config", "ui", "check_core"]:
        try: importlib.import_module(mod); checks.append((mod, True, "OK"))
        except Exception as e: checks.append((mod, False, str(e)[:60]))
    try:
        from config import version_string; checks.append(("版本", True, version_string()))
    except: checks.append(("版本", False, "ERR"))
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks: print(f"  {'✅' if passed else '❌'} {name}: {detail}")
    print(f"\n{'✅ 部署自检通过' if ok else '❌ 部署自检失败'}")
    sys.exit(0 if ok else 1)

import ui
ui.main()
