"""
交付自检工具 — Windows 安装脚本（Python 版）
由 Win安装.bat 调用，负责全部安装逻辑。
"""
import os, sys, shutil, subprocess, zipfile, tempfile
from datetime import datetime

PRODUCT = "交付自检工具"
DR_SCRIPTS = os.path.join(os.environ["PROGRAMDATA"],
    "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts")
TARGET = os.path.join(DR_SCRIPTS, "Edit", PRODUCT)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ZIP = os.path.join(HERE, "data.zip")
DR_CONFIG = os.path.join(os.environ["APPDATA"],
    "Blackmagic Design", "DaVinci Resolve", "Preferences", "config.dat")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(os.path.join(tempfile.gettempdir(), f"{PRODUCT}_install.log"),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def check_admin():
    try:
        r = subprocess.run(["net", "session"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def find_python():
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Python313", "python.exe"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Python312", "python.exe"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Python311", "python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python", "Python313", "python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python", "Python312", "python.exe"),
        os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python", "Python311", "python.exe"),
        "C:\\Python313\\python.exe",
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def check_tkinter(python):
    try:
        subprocess.run([python, "-c", "import tkinter"],
                       capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


def enable_external_scripting():
    if not os.path.isfile(DR_CONFIG):
        log("DaVinci 尚未运行，跳过 External Scripting 设置")
        return
    # config.dat 可能是 ANSI(GBK) 或 UTF-8，尝试两种编码
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(DR_CONFIG, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    if "System.Scripting.Mode = 1" in content:
        log("External Scripting 已启用")
        return
    if "System.Scripting.Mode = 0" in content:
        content = content.replace("System.Scripting.Mode = 0",
                                  "System.Scripting.Mode = 1")
        with open(DR_CONFIG, "w", encoding=enc) as f:
            f.write(content)
        log("External Scripting 已启用")
    else:
        log("DaVinci 未运行过，跳过 External Scripting")


def install():
    log(f"=== {PRODUCT} 安装开始 ===")

    # 1. 管理员
    if not check_admin():
        log("错误: 需要管理员权限")
        print("\n请右键 Win安装.bat →「以管理员身份运行」\n")
        input("按回车退出...")
        sys.exit(1)

    # 2. Python
    python = find_python()
    if not python:
        log("错误: 未找到 Python 3.11+")
        print("\n未找到 Python 3.11+。请从 python.org 下载安装（勾选 Add to PATH 和 tcl/tk）\n")
        input("按回车退出...")
        sys.exit(1)
    log(f"Python: {python}")

    # 3. data.zip（兼容旧名 请勿直接解压此文件.zip）
    zip_candidates = [DATA_ZIP, os.path.join(HERE, "请勿直接解压此文件.zip")]
    actual_zip = None
    for z in zip_candidates:
        if os.path.isfile(z):
            actual_zip = z
            break
    if not actual_zip:
        log(f"错误: 未找到 data.zip")
        files = os.listdir(HERE)
        zips = [f for f in files if f.endswith('.zip')]
        print(f"\n当前目录: {HERE}")
        print(f"找到的 zip 文件: {zips}")
        print("请确保 data.zip 与 Win安装.bat 在同一目录\n")
        input("按回车退出...")
        sys.exit(1)

    # 4. 备份旧版
    if os.path.isdir(TARGET):
        backup = f"{TARGET}_backup_{datetime.now().strftime('%Y%m%d')}"
        log(f"备份旧版本 → {backup}")
        if os.path.exists(backup):
            shutil.rmtree(backup, ignore_errors=True)
        shutil.move(TARGET, backup)

    # 5. 解压（data.zip 内有一层 交付自检工具/ 目录）
    log("解压中...")
    extract_to = os.path.dirname(TARGET)  # → Scripts/Edit/
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(actual_zip, "r") as zf:
        zf.extractall(extract_to)
    log(f"解压完成 → {extract_to}")

    # 6. Launcher
    launcher = os.path.join(DR_SCRIPTS, "Edit", f"{PRODUCT}.bat")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("chcp 65001 >nul\n")
        f.write(f'"{python}" "{os.path.join(TARGET, "launcher_personal.py")}"\n')
    log(f"Launcher → {launcher}")

    # 7. External Scripting
    enable_external_scripting()

    # 8. tkinter
    if not check_tkinter(python):
        log("警告: tkinter 不可用")
        print("\n⚠ tkinter 未安装！弹窗功能将不可用。请重装 Python 并勾选 tcl/tk\n")
    else:
        log("tkinter 可用")

    # 9. 完成
    log(f"=== {PRODUCT} 安装完成 ===")
    print(f"\n[OK] {PRODUCT} 安装完成！\n")
    print("启动: DaVinci Resolve → Workspace → Scripts → Edit → 交付自检工具")
    print(f"手动启动: {launcher}\n")


if __name__ == "__main__":
    try:
        install()
    except Exception as e:
        log(f"安装失败: {e}")
        print(f"\n安装失败: {e}\n")
    try:
        input("\n按回车退出...")
    except (EOFError, OSError):
        pass
