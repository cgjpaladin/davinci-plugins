# -*- coding: utf-8 -*-
# AI v1.2 local test launcher
import os, subprocess, sys, time, atexit, tempfile

_LOCAL = "/Users/bryan/WorkBuddy/达芬奇插件工坊/AI去字幕_v1.2"
_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
_UI_SCRIPT = os.path.join(_LOCAL, "ui_external.py")
_log = os.path.join(tempfile.gettempdir(), "ai_subtitle_v12_ui.log")

sys.path.insert(0, _LOCAL)
_version = "?.?.?"
try:
    import config
    _version = config.version_string()
except Exception:
    pass

with open(_log, "a", encoding="utf-8") as f:
    f.write(f"\n=== AI v1.2 UI test {_version} {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
_env["LC_CTYPE"] = "en_US.UTF-8"
_stdout = open(_log, "a", encoding="utf-8")
_stderr = open(_log, "a", encoding="utf-8")
atexit.register(_stdout.close)
atexit.register(_stderr.close)
subprocess.Popen([_PYTHON, _UI_SCRIPT], env=_env, stdout=_stdout, stderr=_stderr)
