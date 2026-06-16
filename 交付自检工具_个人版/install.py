"""
交付自检工具 — Windows 安装脚本
由 Win安装.bat 调用，或手动: python install.py
"""
import os, sys, shutil, subprocess, zipfile, tempfile
from datetime import datetime

P = chr(0x4ea4)+chr(0x4ed8)+chr(0x81ea)+chr(0x68c0)+chr(0x5de5)+chr(0x5177)
SCRIPTS = os.path.join(os.environ["PROGRAMDATA"],
    "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts")
TARGET = os.path.join(SCRIPTS, P)
EDIT = os.path.join(SCRIPTS, "Edit")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ZIP = os.path.join(HERE, "data.zip")
STANDARD = {"Color","Comp","Deliver","Edit","Tool","Utility","Views"}

def log(msg):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = f"[{t}] {msg}"
    print(s)
    try:
        with open(os.path.join(tempfile.gettempdir(), f"{P}_install.log"),
                  "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass

def is_admin():
    try:
        return subprocess.run(["net","session"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False

def find_python():
    for p in [
        os.path.join(os.environ.get("ProgramFiles","C:\\Program Files"),"Python313","python.exe"),
        os.path.join(os.environ.get("ProgramFiles","C:\\Program Files"),"Python312","python.exe"),
        os.path.join(os.environ.get("ProgramFiles","C:\\Program Files"),"Python311","python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"],"Programs","Python","Python313","python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"],"Programs","Python","Python312","python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"],"Programs","Python","Python311","python.exe"),
        "C:\\Python313\\python.exe","C:\\Python312\\python.exe","C:\\Python311\\python.exe",
    ]:
        if os.path.isfile(p):
            return p
    return None

def fix_garbled_dir():
    for n in os.listdir(SCRIPTS):
        fp = os.path.join(SCRIPTS, n)
        if n not in STANDARD and os.path.isdir(fp) and os.path.isdir(os.path.join(fp,"shared")):
            if n != P:
                if os.path.exists(TARGET):
                    shutil.rmtree(TARGET, ignore_errors=True)
                os.rename(fp, TARGET)
                log("Fixed garbled dir name")
            return

def enable_scripting():
    dc = os.path.join(os.environ["APPDATA"],
        "Blackmagic Design", "DaVinci Resolve", "Preferences", "config.dat")
    if not os.path.isfile(dc):
        return
    for enc in ("utf-8","gbk","latin-1"):
        try:
            c = open(dc,"r",encoding=enc).read()
            break
        except UnicodeDecodeError:
            continue
    if "System.Scripting.Mode = 1" in c:
        log("External Scripting already enabled")
    elif "System.Scripting.Mode = 0" in c:
        c = c.replace("System.Scripting.Mode = 0","System.Scripting.Mode = 1")
        with open(dc,"w",encoding=enc) as f:
            f.write(c)
        log("External Scripting enabled")

def main():
    log(f"=== {P} install start ===")

    if not is_admin():
        print("\nPlease right-click on Win安装.bat -> Run as Administrator\n")
        return

    py = find_python()
    if not py:
        print("\nPython 3.11+ not found. Install from python.org\n")
        return
    log(f"Python: {py}")

    if not os.path.isfile(DATA_ZIP):
        print(f"\ndata.zip not found in: {HERE}\n")
        return

    if os.path.isdir(TARGET):
        bu = f"{TARGET}_backup_{datetime.now().strftime('%Y%m%d')}"
        if os.path.exists(bu):
            shutil.rmtree(bu, ignore_errors=True)
        shutil.move(TARGET, bu)
        log(f"Backup -> {bu}")

    with zipfile.ZipFile(DATA_ZIP,"r") as z:
        z.extractall(SCRIPTS)
    fix_garbled_dir()
    log(f"Extracted -> {SCRIPTS}")

    lp = os.path.join(EDIT, f"{P}.py")
    with open(lp,"w",encoding="utf-8") as f:
        f.write("import subprocess,os,sys\n")
        f.write("_HERE=os.path.dirname(os.path.abspath(__file__))\n")
        f.write(f"_IDIR=os.path.join(_HERE,chr(46)+chr(46),{repr(P)})\n")
        f.write(f"_LP=os.path.join(_IDIR,{repr('launcher_personal.py')})\n")
        f.write("_ENV=os.environ.copy()\n")
        f.write(f"_ENV[{repr('PYTHONIOENCODING')}]={repr('utf-8')}\n")
        f.write(f"_ENV[{repr('PYTHONUTF8')}]={repr('1')}\n")
        f.write(f"_ENV[{repr('WORKBUDDY_PERSONAL')}]={repr('1')}\n")
        f.write(f"subprocess.Popen([{repr(py)},{repr('-B')},_LP],env=_ENV)\n")
    log(f"Launcher -> {lp}")

    enable_scripting()

    ok = os.path.isfile(os.path.join(TARGET,"ui.py"))
    log(f"Install {'OK' if ok else 'FAILED'}")
    print(f"\n{'[OK]' if ok else '[FAIL]'} {P} installed!\n")
    if ok:
        print("Launch: DaVinci Resolve -> Workspace -> Scripts -> Edit -> 交付自检工具\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Error: {e}")
        print(f"\nError: {e}\n")
    try:
        input("\nPress Enter to exit...")
    except (EOFError, OSError):
        pass
