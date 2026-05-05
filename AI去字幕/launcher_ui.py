# -*- coding: utf-8 -*-
# AI 去字幕 — UI 启动器母版（部署后永不更新）
# 部署时复制到: ~/Library/Application Support/.../Fusion/Scripts/Edit/
#
# 策略：达芬奇内嵌 Python 无法稳定运行 UI，改用外部 Python 3.13 子进程。
# 本文件只有 10 行，部署后永不更新——总监改 SMB 上的 ui_external.py 即可全员同步。
import os
import subprocess
import sys
import time

_SMB_PLUGIN = "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"
_UI_SCRIPT = os.path.join(_SMB_PLUGIN, "ui_external.py")

# 优先用系统 Python 3.13，fallback 到系统自带
_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"

# 记录子进程输出到临时文件，方便排查问题
import tempfile
_log = os.path.join(tempfile.gettempdir(), "ai_subtitle_ui.log")
with open(_log, "a", encoding="utf-8") as f:
    f.write(f"\n=== AI去字幕 UI 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
# 确保子进程 UTF-8 环境（达芬奇内嵌 Python 默认 ASCII）
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
_env["LC_CTYPE"] = "en_US.UTF-8"
subprocess.Popen([_PYTHON, _UI_SCRIPT], env=_env,
                 stdout=open(_log, "a", encoding="utf-8"),
                 stderr=open(_log, "a", encoding="utf-8"))
