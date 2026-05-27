#!/usr/bin/env python3
# launcher_personal.py — 个人版启动器（不依赖 SMB / deploy_config）
import subprocess, os, sys, shutil

_PYTHON = shutil.which("python3") or "/usr/bin/python3"
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.dirname(os.path.realpath(sys.argv[0]))

# shared/ 在同级目录
_SHARED = os.path.join(_HERE, 'shared')
if os.path.isdir(_SHARED):
    sys.path.insert(0, _SHARED)

from log_writer import get_logger
_log = get_logger("交付自检工具")
_log.launcher(f"个人版启动 ui: {os.path.join(_HERE, 'ui.py')}")

_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
_env["WORKBUDDY_PERSONAL"] = "1"
subprocess.Popen([_PYTHON, os.path.join(_HERE, 'ui.py')], env=_env)
