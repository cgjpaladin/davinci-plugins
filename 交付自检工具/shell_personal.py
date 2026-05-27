#!/usr/bin/env python3
# shell_personal.py — 个人版壳，放在 Fusion Scripts 目录，指向本地安装目录
import subprocess, os, sys

_INSTALL_DIR = os.path.expanduser("~/Documents/交付自检工具")
_LAUNCHER = os.path.join(_INSTALL_DIR, "launcher_personal.py")

if not os.path.exists(_LAUNCHER):
    raise FileNotFoundError(f"找不到 {_LAUNCHER}，请重新安装")

_PYTHON = "/usr/bin/python3"
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
subprocess.Popen([_PYTHON, _LAUNCHER], env=_env)
