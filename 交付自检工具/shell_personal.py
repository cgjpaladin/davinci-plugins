#!/usr/bin/env python3
# shell_personal.py — 个人版壳，放在 Fusion/Scripts/Edit/，指向 ../交付自检工具/
import subprocess, os, sys

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.dirname(os.path.realpath(sys.argv[0]))

_INSTALL_DIR = os.path.join(_HERE, "..", "交付自检工具")
_LAUNCHER = os.path.join(_INSTALL_DIR, "launcher_personal.py")

if not os.path.exists(_LAUNCHER):
    raise FileNotFoundError(f"找不到 {_LAUNCHER}，请重新安装")

_PYTHON = "/usr/bin/python3"
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen([_PYTHON, _LAUNCHER], env=_env)
