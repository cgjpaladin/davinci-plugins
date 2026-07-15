#!/usr/bin/env python3
"""交付自检工具 — 永久壳

部署到每台机器的 Fusion/Scripts/Edit/ 目录，**永远不更新**。
只做三件事：找 Python → 启动 SMB 上的真实 launcher → 看门狗。
更新代码只推 SMB，不用再碰 20 台机器。
"""
import subprocess, os, glob, json, time, re

# 1. 找最新非达芬奇 Python（按版本号排序，不是字符串排序）
# ⚠️ 此段代码与 AI去字幕/shell.py 同步。改了这里，两个地方都要改。
_python = "/usr/bin/python3"
_versions = []
for p in glob.glob("/Library/Frameworks/Python.framework/Versions/3.*/bin/python3"):
    m = re.search(r"/Versions/(3\.\d+)/", p)
    if m:
        _versions.append((tuple(int(x) for x in m.group(1).split(".")), p))
for _, p in sorted(_versions, key=lambda x: x[0], reverse=True):
    if not os.path.exists(p):
        continue
    try:
        if "/DaVinci Resolve/" in os.path.realpath(p):
            continue
    except Exception:
        pass
    _python = p
    break

# 2. 读 deploy.json 找 SMB 路径
_cfg = {}
try:
    _cfg_path = os.path.expanduser("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具/deploy.json")
    if os.path.exists(_cfg_path):
        with open(_cfg_path, encoding="utf-8") as f:
            _cfg = json.load(f)
except Exception:
    pass
_smb = _cfg.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_launcher = f"{_smb}/交付自检工具/launcher.py"

# 3. 启动 SMB 上的真实 launcher
_env = os.environ.copy()
_env["PYTHONUTF8"] = "1"
_p = subprocess.Popen([_python, _launcher], env=_env)

# 4. 看门狗：达芬奇退出时杀掉孤儿子进程
while True:
    time.sleep(15)
    try:
        r = subprocess.run(["pgrep", "-x", "Resolve"], capture_output=True, timeout=5)
        if r.returncode != 0:
            _p.kill()
            os._exit(0)
    except Exception:
        pass
