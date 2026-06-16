@echo off
setlocal enabledelayedexpansion
set "PYTHON="
for %%p in (
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist %%p if "!PYTHON!"=="" set "PYTHON=%%p"
)
if "%PYTHON%"=="" (
    echo Python 3.11+ not found
    echo Please install from python.org (check "Add to PATH" and "tcl/tk")
    pause
    exit /b 1
)

set "TMPPY=%TEMP%\dv_install.py"
findstr /v "^:::" "%~f0" > "%TMPPY%"
"%PYTHON%" "%TMPPY%"
del "%TMPPY%"
exit /b

:::# -*- coding: utf-8 -*-
"""Win install — embedded in .bat, extracted and run by the stub above."""
import os, sys, shutil, subprocess, zipfile, tempfile
from datetime import datetime

P = "交付自检工具"
DR = os.path.join(os.environ["PROGRAMDATA"], "Blackmagic Design",
                  "DaVinci Resolve", "Fusion", "Scripts")
TG = os.path.join(DR, "Edit", P)
HD = os.path.dirname(os.path.abspath(__file__))
DC = os.path.join(os.environ["APPDATA"], "Blackmagic Design",
                  "DaVinci Resolve", "Preferences", "config.dat")

def L(m):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = f"[{t}] {m}"
    print(s)
    try:
        with open(os.path.join(tempfile.gettempdir(),
                  f"{P}_install.log"), "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass

def admin():
    try:
        return subprocess.run(["net", "session"], capture_output=True,
                              timeout=5).returncode == 0
    except Exception:
        return False

def py():
    cs = [
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
    for p in cs:
        if os.path.isfile(p):
            return p
    return None

def esc():
    if not os.path.isfile(DC):
        L("DaVinci not run yet, skip External Scripting")
        return
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(DC, "r", encoding=enc) as f:
                c = f.read()
            break
        except UnicodeDecodeError:
            continue
    if "System.Scripting.Mode = 1" in c:
        L("External Scripting already enabled")
    elif "System.Scripting.Mode = 0" in c:
        c = c.replace("System.Scripting.Mode = 0",
                      "System.Scripting.Mode = 1")
        with open(DC, "w", encoding=enc) as f:
            f.write(c)
        L("External Scripting enabled")

def main():
    L(f"=== {P} install start ===")
    if not admin():
        L("Not admin")
        print("\nRight-click Win安装.bat -> Run as Administrator\n")
        return
    p = py()
    if not p:
        L("Python 3.11+ not found")
        print("\nPython 3.11+ not found. Install from python.org\n")
        return
    L(f"Python: {p}")

    # data.zip (also try old name)
    zips = [os.path.join(HD, n) for n in ("data.zip", "请勿直接解压此文件.zip")]
    zf = None
    for z in zips:
        if os.path.isfile(z):
            zf = z
            break
    if not zf:
        zs = [f for f in os.listdir(HD) if f.endswith('.zip')]
        L(f"data.zip not found. zips in dir: {zs}")
        return

    # backup
    if os.path.isdir(TG):
        bu = f"{TG}_backup_{datetime.now().strftime('%Y%m%d')}"
        if os.path.exists(bu):
            shutil.rmtree(bu, ignore_errors=True)
        shutil.move(TG, bu)
        L(f"Backup -> {bu}")

    # extract
    et = os.path.dirname(TG)
    os.makedirs(et, exist_ok=True)
    with zipfile.ZipFile(zf, "r") as z:
        z.extractall(et)
    L(f"Extracted -> {et}")

    # launcher
    lb = os.path.join(DR, "Edit", f"{P}.bat")
    with open(lb, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("chcp 65001 >nul\n")
        f.write(f'"{p}" "{os.path.join(TG, "launcher_personal.py")}"\n')
    L(f"Launcher -> {lb}")

    esc()
    L(f"=== {P} install done ===")
    print(f"\n[OK] {P} installed!\n")
    print("Launch: DaVinci Resolve -> Workspace -> Scripts -> Edit -> 交付自检工具")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        L(f"Install failed: {e}")
        print(f"\nInstall failed: {e}\n")
    try:
        input("\nPress Enter to exit...")
    except (EOFError, OSError):
        pass
