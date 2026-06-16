#!/usr/bin/env python3
"""
Agent 自动安装脚本。
用法:
  python install_agent.py            → 检测环境，需要权限时输出 need_sudo/need_admin
  python install_agent.py --continue → 跳过已完成步骤，执行需要权限的操作
输出: 每行一个 JSON，agent 逐行解析。
状态文件: ~/.delivery_checker_install_state.json（断点续装）
"""
import json, os, sys, shutil, subprocess

_STATE_FILE = os.path.join(os.path.expanduser("~"),
                           ".delivery_checker_install_state.json")
_HERE = os.path.dirname(os.path.abspath(__file__))
_IS_MACOS = sys.platform == "darwin"
_IS_WIN = sys.platform == "win32"

PRODUCT = "交付自检工具"
LAUNCHER_NAME = "launcher_personal.py"


def _say(obj):
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _load_state():
    if os.path.exists(_STATE_FILE):
        with open(_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(s):
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(s, f)


def _dr_scripts():
    if _IS_MACOS:
        return os.path.join("/Library/Application Support",
            "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts")
    return os.path.join(os.environ["PROGRAMDATA"],
        "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts")


def _find_python():
    """Return path to Python 3.11+ with tkinter, or None."""
    candidates = []
    if _IS_MACOS:
        candidates = [
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
        ]
    else:
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                         "Python313", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                         "Python312", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                         "Python311", "python.exe"),
            os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python",
                         "Python313", "python.exe"),
            os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python",
                         "Python312", "python.exe"),
            os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python",
                         "Python311", "python.exe"),
            "C:\\Python313\\python.exe",
            "C:\\Python312\\python.exe",
            "C:\\Python311\\python.exe",
        ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                subprocess.run([p, "-c", "import tkinter"],
                               capture_output=True, timeout=10, check=True)
                return p
            except Exception:
                continue
    return None


def _enable_scripting(dr_scripts):
    """Enable External Scripting in DaVinci config."""
    if _IS_MACOS:
        dc = os.path.join(os.path.expanduser(
            "~/Library/Preferences/Blackmagic Design/DaVinci Resolve"),
            "config.dat")
    else:
        dc = os.path.join(os.environ["APPDATA"],
            "Blackmagic Design", "DaVinci Resolve", "Preferences",
            "config.dat")
    if not os.path.isfile(dc):
        return "skipped"
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            c = open(dc, "r", encoding=enc).read()
            break
        except UnicodeDecodeError:
            continue
    if "System.Scripting.Mode = 1" in c:
        return "already"
    if "System.Scripting.Mode = 0" in c:
        c = c.replace("System.Scripting.Mode = 0",
                      "System.Scripting.Mode = 1")
        with open(dc, "w", encoding=enc) as f:
            f.write(c)
        return "enabled"
    return "skipped"


def main():
    state = _load_state()
    is_continue = "--continue" in sys.argv
    dr = _dr_scripts()
    target = os.path.join(dr, PRODUCT)
    edit = os.path.join(dr, "Edit")

    # Step 1: Check Python
    if not state.get("python"):
        py = _find_python()
        if not py:
            _say({"action": "error",
                  "reason": "Python 3.11+ with tkinter not found",
                  "hint": "Install Python 3.13 from python.org (check tcl/tk)"})
            return
        state["python"] = py
        _save_state(state)
    py = state["python"]

    _say({"step": "init",
          "platform": sys.platform,
          "python": py,
          "dr_scripts": dr})

    # Step 2: Copy code to DaVinci Scripts
    if not state.get("copied"):
        if not os.access(dr, os.W_OK):
            src = _HERE
            if is_continue:
                # Agent already got permission, try copy
                try:
                    if os.path.exists(target):
                        shutil.rmtree(target, ignore_errors=True)
                    shutil.copytree(src, target,
                        ignore=shutil.ignore_patterns("__pycache__", ".git",
                            ".DS_Store"))
                    # Remove files not needed at install target
                    for f in ("install_agent.py",):
                        fp = os.path.join(target, f)
                        if os.path.exists(fp):
                            os.unlink(fp)
                    state["copied"] = True
                    _save_state(state)
                except PermissionError:
                    _say({"action": "error", "reason": "Permission denied"})
                    return
            else:
                if _IS_MACOS:
                    _say({"action": "need_sudo",
                          "cmd": f"python3 {os.path.join(_HERE, 'install_agent.py')} --continue",
                          "reason": "需要管理员权限写入 DaVinci Scripts 目录"})
                else:
                    _say({"action": "need_admin",
                          "cmd": f"python \"{os.path.join(_HERE, 'install_agent.py')}\" --continue",
                          "reason": "需要管理员权限写入 ProgramData"})
                return
        else:
            # Writable, copy directly
            if os.path.exists(target):
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(src, target,
                ignore=shutil.ignore_patterns("__pycache__", ".git",
                    ".DS_Store"))
            for f in ("install_agent.py",):
                fp = os.path.join(target, f)
                if os.path.exists(fp):
                    os.unlink(fp)
            state["copied"] = True
            _save_state(state)

    _say({"step": "copied", "target": target})

    # Step 3: Create launcher
    if not state.get("launcher"):
        os.makedirs(edit, exist_ok=True)
        lp = os.path.join(edit, f"{PRODUCT}.py")
        with open(lp, "w", encoding="utf-8") as f:
            f.write("import subprocess,os,sys\n")
            f.write("_HERE=os.path.dirname(os.path.abspath(__file__))\n")
            f.write(f"_IDIR=os.path.join(_HERE,'..',{repr(PRODUCT)})\n")
            f.write(f"_LP=os.path.join(_IDIR,{repr(LAUNCHER_NAME)})\n")
            f.write("_ENV=os.environ.copy()\n")
            f.write("_ENV['PYTHONIOENCODING']='utf-8'\n")
            f.write("_ENV['PYTHONUTF8']='1'\n")
            f.write("_ENV['WORKBUDDY_PERSONAL']='1'\n")
            f.write(f"subprocess.Popen([{repr(py)},'-B',_LP],env=_ENV)\n")
        if _IS_MACOS:
            os.chmod(lp, 0o755)
        state["launcher"] = lp
        _save_state(state)

    _say({"step": "launcher", "path": lp})

    # Step 4: External Scripting
    es = _enable_scripting(dr)
    _say({"step": "scripting", "status": es})

    # Done
    _say({"action": "done",
          "launch": "Workspace → Scripts → Edit → 交付自检工具"})
    # Clean state
    if os.path.exists(_STATE_FILE):
        os.unlink(_STATE_FILE)


if __name__ == "__main__":
    main()
