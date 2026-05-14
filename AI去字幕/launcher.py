#!/usr/bin/env python3
# launcher.py — AI去字幕 启动器
# 部署到达芬奇 Fusion/Scripts/Edit/，通过 subprocess 外挂外部 Python 进程运行 UI
# 注意: DaVinci Fusion 内 __file__ 不存在，需 fallback
import subprocess, os, sys, time, socket, json

_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"

# __file__ 在 DaVinci Fusion 引擎内不存在，fallback 到已知路径
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊"

# ═══ 部署配置（可选，不存在则用默认值）═══
def _load_deploy_config():
    """读取 ~/达芬奇插件工坊/deploy.json，不存在返回空 dict"""
    cfg_path = os.path.expanduser("~/达芬奇插件工坊/deploy.json")
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except Exception:
        return {}

_deploy = _load_deploy_config()
_SMB_ROOT = _deploy.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_DEV_HOSTS = set(_deploy.get("dev_hosts", ["BryandeMac-mini.local", "BryandeMac-mini"]))
_DEV_DIR_BASE = os.path.expanduser(
    _deploy.get("dev_dir", "~/WorkBuddy/达芬奇插件工坊")
)

# 让 shared/ 可导入（先加本地 fallback，再加 SMB shared）
sys.path.insert(0, os.path.join(_HERE, '..', 'shared'))
sys.path.insert(0, os.path.join(_SMB_ROOT, 'shared'))

from log_writer import get_logger
_log = get_logger("AI去字幕")

_PRODUCT_NAME = "AI去字幕"
_PRODUCT_DIRS = [
    os.path.join(_SMB_ROOT, _PRODUCT_NAME),
    os.path.join(_DEV_DIR_BASE, _PRODUCT_NAME),
]

# Dev 机本地优先
if socket.gethostname() in _DEV_HOSTS:
    _PRODUCT_DIRS.reverse()

_STABLE_UI = None
for d in _PRODUCT_DIRS:
    candidate = os.path.join(d, 'stable_ui.py')
    if os.path.exists(candidate):
        _STABLE_UI = candidate
        break

if not _STABLE_UI:
    _log.launcher(f"找不到 stable_ui.py，搜索: {_PRODUCT_DIRS}")
    raise FileNotFoundError(f"找不到 stable_ui.py")

_log.launcher(f"启动 stable_ui: {_STABLE_UI} python: {_PYTHON}")

# dry-run 自检（仅外部 Python 可见，Fusion 内不会带这个参数）
if '--dry-run' in sys.argv:
    import socket
    print(f"═══ AI去字幕 部署自检 ═══")
    checks = []
    v = sys.version_info
    checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))
    host = socket.gethostname()
    routing = "DEV" if host in _DEV_HOSTS else "SMB"
    checks.append(("路由", True, routing))
    checks.append(("stable_ui", os.path.exists(_STABLE_UI), _STABLE_UI))
    checks.append(("python", os.path.exists(_PYTHON), _PYTHON))
    result = subprocess.run([_PYTHON, '-c',
        f'import sys; sys.path.insert(0,"{os.path.dirname(_STABLE_UI)}"); '
        f'sys.path.insert(0,"{os.path.dirname(_STABLE_UI)}/../shared"); '
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

# 启动外部 Python 进程（stdout/stderr 保留给子进程，不归 log_writer 管）
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen([_PYTHON, _STABLE_UI], env=_env)
