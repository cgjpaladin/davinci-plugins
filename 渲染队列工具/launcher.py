#!/usr/bin/env python3
# launcher.py — 渲染队列工具 启动器
import subprocess, os, sys, time, socket, json

_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊"

def _load_deploy_config():
    cfg_path = os.path.expanduser("~/达芬奇插件工坊/deploy.json")
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except Exception:
        return {}

_deploy = _load_deploy_config()
_SMB_ROOT = _deploy.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_DEV_HOSTS = set(_deploy.get("dev_hosts", ["BryandeMac-mini.local", "BryandeMac-mini"]))
_DEV_DIR_BASE = os.path.expanduser(_deploy.get("dev_dir", "~/WorkBuddy/达芬奇插件工坊"))

_PRODUCT_NAME = "渲染队列工具"
_PRODUCT_DIRS = [
    os.path.join(_SMB_ROOT, _PRODUCT_NAME),
    os.path.join(_DEV_DIR_BASE, _PRODUCT_NAME),
]
if socket.gethostname() in _DEV_HOSTS:
    _PRODUCT_DIRS.reverse()

_RUNNER = None
for d in _PRODUCT_DIRS:
    candidate = os.path.join(d, 'render_batch.py')
    if os.path.exists(candidate):
        _RUNNER = candidate
        break

if not _RUNNER:
    raise FileNotFoundError(f"找不到 render_batch.py，搜索: {_PRODUCT_DIRS}")

if '--dry-run' in sys.argv:
    checks = []
    checks.append(("Python", sys.version_info >= (3, 9), f"{sys.version_info.major}.{sys.version_info.minor}"))
    host = socket.gethostname()
    checks.append(("路由", True, "DEV" if host in _DEV_HOSTS else "SMB"))
    checks.append(("render_batch.py", os.path.exists(_RUNNER), _RUNNER))
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"  {'✅' if passed else '❌'} {name}: {detail}")
    print(f"\n{'✅' if ok else '❌'}")
    sys.exit(0 if ok else 1)

_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen([_PYTHON, _RUNNER], env=_env)
