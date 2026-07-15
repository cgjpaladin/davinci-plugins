# -*- coding: utf-8 -*-
"""
tools/_env.py — 达芬奇脚本环境统一配置
所有通用工具（show_*/runner）从这里取路径，不再各自硬编码。
"""
import os
import sys
import platform

# ── 达芬奇 API 路径 ──
# 以下 Developer/Scripting 为达芬奇官方安装目录（系统级），保留不改
_SYS = platform.system()

if _SYS == "Darwin":
    RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    RESOLVE_SCRIPT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    RESOLVE_SCRIPT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
    CRASH_LOG = os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/crash_archive.txt")
elif _SYS == "Windows":
    RESOLVE_MODULES = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                                   "Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules")
    RESOLVE_SCRIPT_LIB = "C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\fusionscript.dll"
    RESOLVE_SCRIPT_API = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                                      "Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting")
    CRASH_LOG = ""  # Windows crash log path differs
else:
    # Linux
    RESOLVE_MODULES = "/opt/resolve/Developer/Scripting/Modules"
    RESOLVE_SCRIPT_LIB = "/opt/resolve/libs/Fusion/fusionscript.so"
    RESOLVE_SCRIPT_API = "/opt/resolve/Developer/Scripting"
    CRASH_LOG = ""


def setup():
    """初始化达芬奇脚本环境（只需调用一次）"""
    if RESOLVE_MODULES not in sys.path:
        sys.path.append(RESOLVE_MODULES)

    if "RESOLVE_SCRIPT_API" not in os.environ:
        os.environ["RESOLVE_SCRIPT_API"] = RESOLVE_SCRIPT_API
    if "RESOLVE_SCRIPT_LIB" not in os.environ:
        os.environ["RESOLVE_SCRIPT_LIB"] = RESOLVE_SCRIPT_LIB
