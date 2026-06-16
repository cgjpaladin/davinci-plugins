#!/usr/bin/env python3
"""跨平台抽象层 — 统一 macOS / Windows 路径和系统命令差异。

用法:
    from platform import is_windows, is_macos, app_data_dir, python_candidates,
                           open_in_explorer, dr_scripts_dir, smb_root
"""

import os
import sys
import shutil
import subprocess

_IS_WINDOWS = sys.platform == "win32"
_IS_MACOS = sys.platform == "darwin"


def is_windows() -> bool:
    return _IS_WINDOWS


def is_macos() -> bool:
    return _IS_MACOS


# ═══ Python 路径 — Launcher 用 ═══

def python_candidates() -> list[str]:
    """返回当前平台所有可能的 Python 解释器路径（按优先级排列）。"""
    if _IS_MACOS:
        return [
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
        ]
    if _IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = []
        # 用户安装（权限低但最常见）
        if local:
            candidates.append(os.path.join(local, "Programs", "Python", "Python313", "python.exe"))
            candidates.append(os.path.join(local, "Programs", "Python", "Python312", "python.exe"))
            candidates.append(os.path.join(local, "Programs", "Python", "Python311", "python.exe"))
        # 全用户安装
        candidates.append("C:\\Python313\\python.exe")
        candidates.append("C:\\Python312\\python.exe")
        candidates.append("C:\\Python311\\python.exe")
        # Program Files
        candidates.append("C:\\Program Files\\Python313\\python.exe")
        candidates.append("C:\\Program Files\\Python312\\python.exe")
        return candidates
    return []


def find_python() -> str | None:
    """在当前平台找到可用的 Python 解释器。"""
    for py in python_candidates():
        if os.path.isfile(py):
            return py
    # 兜底：系统 PATH
    py = shutil.which("python3") or shutil.which("python")
    if py:
        return py
    return None


# ═══ 应用数据目录 ═══

def app_data_dir(subdir: str = "交付自检") -> str:
    """返回平台级应用数据目录。
    macOS: ~/Library/Application Support/交付自检/
    Windows: %APPDATA%/交付自检/
    """
    if _IS_MACOS:
        return os.path.join(os.path.expanduser("~/Library/Application Support"), subdir)
    if _IS_WINDOWS:
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), subdir)
    return os.path.join(os.path.expanduser("~"), "." + subdir)


def app_logs_dir(subdir: str = "交付自检工具") -> str:
    """返回平台级日志目录。"""
    if _IS_MACOS:
        return os.path.expanduser(f"~/.workbuddy/logs/{subdir}")
    if _IS_WINDOWS:
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), subdir, "logs")
    return os.path.expanduser(f"~/.{subdir}/logs")


# ═══ DaVinci Resolve 路径 ═══

def dr_scripts_dir() -> str:
    """返回 DaVinci Resolve Fusion Scripts 系统级目录。"""
    if _IS_MACOS:
        return "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
    if _IS_WINDOWS:
        return os.path.join(
            os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
            "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts")
    return ""


def dr_scripting_env() -> dict[str, str] | None:
    """返回 DaVinci 脚本环境变量（Windows 不需要，macOS 设 RESOLVE_SCRIPT_API）。"""
    if _IS_MACOS:
        return {"RESOLVE_SCRIPT_API": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"}
    return None  # Windows 不需要


# ═══ 系统命令 ═══

def open_in_explorer(path: str):
    """在文件管理器中定位文件。macOS: Finder，Windows: Explorer。"""
    if _IS_MACOS:
        subprocess.Popen(["open", "-R", path])
    elif _IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", path])


def alert_dialog(title: str, message: str):
    """系统级弹窗（macOS osascript / Windows msg）。不阻塞调用方。"""
    if _IS_MACOS:
        subprocess.Popen(["osascript", "-e",
            f'display dialog "{message}" with title "{title}" '
            f'buttons {{"确定"}} default button "确定"'])
    elif _IS_WINDOWS:
        # msg 是 cmd 内置命令，需通过 cmd /c 启动
        subprocess.Popen(["cmd", "/c", "msg", os.environ.get("USERNAME", "%USERNAME%"),
                         message])


# ═══ SMB 路径 — 仅公司版用 ═══

def smb_root() -> str:
    """返回 SMB 根路径。macOS: /Volumes/MYJC，Windows: UNC 路径。"""
    if _IS_MACOS:
        return "/Volumes/MYJC"
    # Windows: 从 deploy.json 读，或使用默认 UNC
    return os.environ.get("WORKBUDDY_SMB_ROOT", "")


def smb_scripts_dir() -> str:
    """返回 SMB 共享脚本目录。"""
    if _IS_MACOS:
        return "/Volumes/MYJC/06_Software/达芬奇脚本"
    # Windows: UNC 路径
    root = smb_root()
    if root:
        return os.path.join(root, "06_Software", "达芬奇脚本")
    return ""


def smb_shared_env() -> str:
    """返回 SMB 共享 .env 文件路径。"""
    return os.path.join(smb_scripts_dir(), "shared", ".env")


def is_smb_mounted() -> bool:
    """SMB 是否已挂载。"""
    if _IS_MACOS:
        return os.path.isdir(smb_root())
    if _IS_WINDOWS:
        root = smb_root()
        if root and os.path.isdir(root):
            return True
        return False
    return False


def smb_path_to_local(smb_url: str) -> str:
    """smb://server/share/path → 平台本地路径。"""
    if _IS_MACOS:
        if smb_url.startswith("smb://"):
            return "/Volumes/" + smb_url.split("smb://", 1)[1].split("/", 1)[1]
        return smb_url
    if _IS_WINDOWS:
        if smb_url.startswith("smb://"):
            parts = smb_url.replace("smb://", "").split("/", 1)
            if len(parts) == 2:
                return f"\\\\{parts[0]}\\{parts[1].replace('/', '\\')}"
        return smb_url
    return smb_url
