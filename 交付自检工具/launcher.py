#!/usr/bin/env python3
# launcher.py — 交付自检工具 启动器
import subprocess, os, sys, time, socket, json

_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊"

# ═══ 部署配置（统一入口 shared/deploy_config.py）═══
# 先加 shared/ 路径再导入
sys.path.insert(0, os.path.join(_HERE, '..', 'shared'))
from deploy_config import load as _load_deploy_config

_deploy = _load_deploy_config()
_SMB_ROOT = _deploy.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_DEV_HOSTS = set(_deploy.get("dev_hosts", ["BryandeMac-mini.local", "BryandeMac-mini"]))
_DEV_DIR_BASE = os.path.expanduser(
    _deploy.get("dev_dir", "~/WorkBuddy/达芬奇插件工坊")
)

# 让 shared/ 可导入（SMB 备用）
sys.path.insert(0, os.path.join(_SMB_ROOT, 'shared'))

from log_writer import get_logger
_log = get_logger("交付自检工具")

_PRODUCT_NAME = "交付自检工具"
_PRODUCT_DIRS = [
    os.path.join(_SMB_ROOT, _PRODUCT_NAME),
    os.path.join(_DEV_DIR_BASE, _PRODUCT_NAME),
]

# Dev 机本地优先
if socket.gethostname() in _DEV_HOSTS:
    _PRODUCT_DIRS.reverse()

_UI_SCRIPT = None
for d in _PRODUCT_DIRS:
    candidate = os.path.join(d, 'ui.py')
    if os.path.exists(candidate):
        _UI_SCRIPT = candidate
        break

if not _UI_SCRIPT:
    _log.launcher(f"找不到 ui.py，搜索: {_PRODUCT_DIRS}")
    raise FileNotFoundError(f"找不到 ui.py")

_log.launcher(f"启动 ui: {_UI_SCRIPT}")
_log.launcher(f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}  ({_PYTHON})")
_log.launcher(f"路由: {'DEV(本地优先)' if socket.gethostname() in _DEV_HOSTS else 'SMB(全公司)'}  (host={socket.gethostname()})")
_log.launcher(f"SMB: {'已挂载' if os.path.isdir(_SMB_ROOT) else '未挂载'}  ({_SMB_ROOT})")

if '--dry-run' in sys.argv:
    import socket
    print(f"═══ 交付自检工具 部署自检 ═══")
    checks = []
    v = sys.version_info
    checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))
    host = socket.gethostname()
    routing = "DEV" if host in _DEV_HOSTS else "SMB"
    checks.append(("路由", True, routing))
    checks.append(("ui.py", os.path.exists(_UI_SCRIPT), _UI_SCRIPT))
    checks.append(("python", os.path.exists(_PYTHON), _PYTHON))
    result = subprocess.run([_PYTHON, '-c',
        f'import sys; sys.path.insert(0,"{os.path.dirname(_UI_SCRIPT)}"); '
        f'sys.path.insert(0,"{os.path.dirname(_UI_SCRIPT)}/../shared"); '
        f'import config; print(config.version_string())'
    ], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        checks.append(("模块导入", True, result.stdout.strip()))
    else:
        checks.append(("模块导入", False, result.stderr.strip()[:60]))
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"  {'✅' if passed else '❌'} {name}: {detail}")
    print(f"\n{'✅ 部署自检通过' if ok else '❌ 部署自检失败'}")
    sys.exit(0 if ok else 1)

_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen([_PYTHON, _UI_SCRIPT], env=_env)
