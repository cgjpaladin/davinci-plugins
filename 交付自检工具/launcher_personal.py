#!/usr/bin/env python3
# launcher_personal.py — 个人版启动器（不依赖 SMB / deploy_config）
import subprocess, os, sys, shutil

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
_env["PYTHONUTF8"] = "1"            # PEP 540: 全局 UTF-8 模式
_env["WORKBUDDY_PERSONAL"] = "1"

# 加载安装目录 .env 的 API Key
_dotenv = os.path.join(_HERE, ".env")
if os.path.exists(_dotenv):
    try:
        with open(_dotenv, encoding="utf-8") as f:
            for _line in f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _env[_k.strip()] = _v.strip().strip("\"'")
    except Exception:
        pass

subprocess.Popen([_PYTHON, "-B", os.path.join(_HERE, 'ui.py')], env=_env)
