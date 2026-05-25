#!/usr/bin/env python3
"""AI去字幕 — 永久壳

部署到每台机器的 Fusion/Scripts/Edit/ 目录，**永远不更新**。
只做三件事：找 Python → 启动 SMB 上的真实 launcher → 看门狗。
更新代码只推 SMB，不用再碰 20 台机器。
"""
import subprocess, os, glob, json, time

# 1. 找最新非达芬奇 Python（优先级：framework > usr/bin）
_python = "/usr/bin/python3"
for p in sorted(glob.glob(
    "/Library/Frameworks/Python.framework/Versions/3.*/bin/python3"
), reverse=True):
    if os.path.exists(p):
        _python = p
        break

# 2. 读 deploy.json 找 SMB 路径
_cfg = {}
try:
    _cfg_path = os.path.expanduser("~/达芬奇插件工坊/deploy.json")
    if os.path.exists(_cfg_path):
        with open(_cfg_path) as f:
            _cfg = json.load(f)
except Exception:
    pass
_smb = _cfg.get("smb_root", "/Volumes/MYJC/06_Software/达芬奇脚本")
_launcher = f"{_smb}/AI去字幕/launcher.py"

# 3. 启动 SMB 上的真实 launcher
_p = subprocess.Popen([_python, _launcher])

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
