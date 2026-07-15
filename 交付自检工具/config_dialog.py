# -*- coding: utf-8 -*-
"""配置弹窗辅助模块：API Key 持久化 + 遮幅常量 + 主窗口控件 ID。
Builder 函数和 CONFIG_SECTIONS 留在 ui.py（需共享同一个 UIManager 实例）。
"""

import os

# ── API Key 持久化（macOS Keychain，零明文落盘）──
def _load_api_keys():
    from secure_store import load_all, migrate_legacy
    keys = load_all()
    if not keys:
        migrate_legacy()
        keys = load_all()
    if not keys:
        return {}
    return keys

def _save_api_keys(keys):
    from secure_store import save
    for k, v in keys.items():
        if v:
            save(k, v)

# ── 遮幅预设 ──
_MASK_PRESETS = ["1", "1.33", "1.66", "1.77", "1.85", "2.0", "2.35", "2.39", "2.40"]
_MASK_UNSET = "（未设置）"

# ── 主窗口控件 ID ──
TRIAL_LB = "trial_lb"
BTN_AI_TYPO = "btn_ai_typo"
HINT_LB = "hint_lb"

CONFIG_WIDGETS = {}
