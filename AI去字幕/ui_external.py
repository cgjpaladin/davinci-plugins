# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 灰度路由层

根据 gray.json 配置和本机 hostname 决定执行稳定版还是灰度版。
零额外文件——hostname 遵循 Mac-mini-{IP末段} 命名规范（Macmini远程登录 skill）。
"""
import json
import os
import re
import socket
import sys

# ── 本机标识：从 hostname 提取 ──
# 规范: Mac-mini-101.local → 101
# 非标: BryandeMac-mini.local → bryan（裁缝老师本机）
_HOSTNAME = socket.gethostname()
_M = re.search(r"Mac-mini-(\d+)", _HOSTNAME)
_MY_ID = _M.group(1) if _M else "bryan"

_BASE = os.path.dirname(os.path.abspath(__file__))
_GRAY_CFG = os.path.join(_BASE, "gray.json")
_SMB_BASE = os.path.dirname(_BASE)

# 默认：稳定版
_target_dir = _BASE
_target_script = os.path.join(_BASE, "stable_ui.py")

# 检查灰度配置
if os.path.exists(_GRAY_CFG):
    try:
        with open(_GRAY_CFG, encoding="utf-8") as f:
            cfg = json.load(f)
        if _MY_ID in cfg.get("targets", []):
            gray_dir = os.path.join(_SMB_BASE, cfg.get("gray_dir", ""))
            gray_script = os.path.join(gray_dir, "stable_ui.py")
            if os.path.exists(gray_script):
                _target_dir = gray_dir
                _target_script = gray_script
    except Exception:
        pass  # 任何异常 → fallback 到稳定版

# 确保目标目录在 sys.path 最前面
if _target_dir in sys.path:
    sys.path.remove(_target_dir)
sys.path.insert(0, _target_dir)

# 执行目标脚本
with open(_target_script, encoding="utf-8") as f:
    _target_code = f.read()
exec(compile(_target_code, _target_script, 'exec'), {
    '__name__': '__main__',
    '__file__': _target_script,
})
