#!/usr/bin/env python3
"""
tools/check.py — 环境体检
─────────────────────────
开 session 第一条命令。发现问题马上报，不等到写代码才发现。

用法:
  python3 tools/check.py
"""
import sys, os, subprocess

REQUIRED = {
    "DaVinci Resolve.app": "/Applications/DaVinci Resolve/DaVinci Resolve.app",
    "fusionscript.so": "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
    "RESOLVE_MODULES": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    "README.txt (API文档)": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/README.txt",
    "Python 3.13": "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
}


def check_path(label, path):
    exists = os.path.exists(path)
    status = "✅" if exists else "❌"
    print(f"  {status} {label}: {path if not exists else ''}")
    return exists


def check_davinci_running():
    try:
        result = subprocess.run(["pgrep", "-l", "Resolve"], capture_output=True, text=True)
        running = result.returncode == 0
        print(f"  {'✅ 运行中' if running else '⚪ 未启动'} DaVinci Resolve")
        return running
    except:
        print(f"  ⚪ 无法检测 DaVinci 状态")
        return None


def check_smb():
    path = "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"
    exists = os.path.exists(path)
    print(f"  {'✅' if exists else '❌'} SMB 插件目录: {path}")
    return exists


def check_python():
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True, text=True
        )
        version = result.stdout.strip()
        is_ok = version.startswith("3.")
        print(f"  {'✅' if is_ok else '❌'} Python {version}")
        return is_ok
    except:
        print(f"  ❌ Python 不可用")
        return False


def check_import():
    try:
        subprocess.run([
            sys.executable, "-c",
            "import sys; sys.path.append('/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules'); "
            "import DaVinciResolveScript; print('ok')"
        ], capture_output=True, text=True, timeout=10, check=True)
        print(f"  ✅ DaVinciResolveScript 可导入")
        return True
    except:
        print(f"  ❌ DaVinciResolveScript 导入失败")
        return False


def main():
    print("━" * 50)
    print("  达芬奇开发环境体检")
    print("━" * 50)
    
    print("\n  路径:")
    all_ok = True
    for label, path in REQUIRED.items():
        if not check_path(label, path):
            all_ok = False
    
    print("\n  运行状态:")
    if not check_davinci_running():
        pass  # not a blocker
    check_smb()
    
    print("\n  Python:")
    if not check_python():
        all_ok = False
    check_import()
    
    print("\n" + "━" * 50)
    if all_ok:
        print("  ✅ 环境正常。下一步: python3 tools/inspect.py")
    else:
        print("  ❌ 有问题，请先修复以上报错")
    print("━" * 50)


if __name__ == "__main__":
    main()
