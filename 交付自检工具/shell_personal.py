#!/usr/bin/env python3
# shell_personal.py — 个人版壳，跟安装目录在同级
import subprocess, os, sys, shutil

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.dirname(os.path.realpath(sys.argv[0]))

_INSTALL_DIR = os.path.join(_HERE, "..", "交付自检工具")
_LAUNCHER = os.path.join(_INSTALL_DIR, "launcher_personal.py")

if not os.path.exists(_LAUNCHER):
    raise FileNotFoundError(f"找不到 {_LAUNCHER}，请重新安装")

_PYTHON = None
for _py in [
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
]:
    if os.path.exists(_py):
        _PYTHON = _py
        break
if not _PYTHON:
    _PYTHON = shutil.which("python3") or "/usr/bin/python3"
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
_env["PYTHONUTF8"] = "1"
_env["WORKBUDDY_PERSONAL"] = "1"
# 清除旧 .pyc 缓存，防止加载过期字节码
for _root, _dirs, _files in os.walk(_INSTALL_DIR):
    for _d in _dirs:
        if _d == "__pycache__":
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)
subprocess.Popen([_PYTHON, "-B", _LAUNCHER], env=_env)
