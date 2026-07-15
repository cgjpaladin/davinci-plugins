# -*- coding: utf-8 -*-
"""配置弹窗 builders + CONFIG_SECTIONS 注册表。
show_config_dialog 入口仍在 ui.py（需要访问全局变量），本文件只提供纯 build 函数。
"""

from fusionscript_loader import bmd
fu = bmd.scriptapp("Fusion")
ui = fu.UIManager

from config import IS_PERSONAL, MANUAL_URL
from styles import *
from license_ui import trial_days_left, format_trial

import os, subprocess, time, socket, json

# ── API Key 持久化 ──
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

# ── Builder ── _build_api_key_input ──
def _build_api_key_input(sid, label):
    """Label 显示当前值 + 编辑按钮（弹系统输入框防 IME 崩溃）"""
    is_secret = "secret" in sid or "key" in sid
    lbl_id = f"cfg_{sid}_lbl"
    btn_id = f"cfg_{sid}_btn"
    def _do_edit():
        try:
            from tkinter import Tk
            root = Tk(); root.withdraw()
            try: root.clipboard_get()
            except: pass
            root.destroy()
        except Exception:
            pass
        _keys = _load_api_keys()
        cur = _keys.get(sid, "")
        if is_secret and cur:
            cur = cur[:4] + "****" + cur[-4:] if len(cur) > 8 else cur[:4]
        new_val = subprocess.run(["osascript", "-e",
            f'set userInput to text returned of (display dialog "编辑 {label}" default answer "" with title "编辑 {label}")'],
            capture_output=True, text=True, timeout=60).stdout.strip()
        if new_val:
            _keys = _load_api_keys()
            _keys[sid] = new_val
            _save_api_keys(_keys)
            log_fn(f"✅ {label} 已保存")
    return [
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.Label({"ID": lbl_id, "Text": "",
                "StyleSheet": f"color:rgb(180,180,180);{FONT_SM};{FONT_BOLD}",
                "Weight": 0}),
            ui.Button({"ID": btn_id, "Text": "编辑", "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
        ]),
        ui.VGap(SPACE_TIGHT),
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.Label({"ID": f"cfg_{sid}_note", "Text": "",
                "StyleSheet": f"color:rgb(130,130,130);{FONT_XS}", "Weight": 0}),
        ]),
    ]

# ── Builder ── _build_censor_personal ──
CONFIG_WIDGETS = {}  # 导出给 ui.py 的 {widget_id: widget_base_id} 映射
def _build_censor_personal():
    return [ui.Label({"Text": "1、右键「短剧违禁词表.csv」→ 打开方式 → WPS / Excel / Numbers\n2、改完保存后，重新运行检查即可生效",
        "StyleSheet": f"color:rgb(130,130,130);{FONT_SM}", "Weight": 0})]

# ── Builder ── _build_mask_ratio ──
_MASK_PRESETS = ["1", "1.33", "1.66", "1.77", "1.85", "2.0", "2.35", "2.39", "2.40"]
_MASK_UNSET = "（未设置）"
def _build_mask_ratio():
    opts = [_MASK_UNSET] + [f"{m}:1" for m in _MASK_PRESETS] + ["自定义"]
    cid = "cfg_mask_custom"
    combo = ui.ComboBox({"ID": "cfg_mask_combo", "Weight": 0})
    for o in opts:
        combo.AddItem(o)
    custom = ui.LineEdit({"ID": cid, "PlaceholderText": "如: 2.35", "Weight": 0, "Visible": False})
    CONFIG_WIDGETS[cid] = "cfg_mask_combo"
    return [
        ui.HGroup({"Spacing": SPACE_COMPACT, "Weight": 0}, [combo, custom]),
    ]

# ── Builder ── _build_smb_paths ──
def _build_smb_paths():
    return [
        ui.HGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, [
            ui.Button({"ID": "cfg_smb_add", "Text": "+ 添加路径", "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
            ui.Button({"ID": "cfg_smb_del", "Text": "- 删除路径", "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
        ]),
        ui.VGap(SPACE_TIGHT),
        ui.Label({"ID": "cfg_smb_list", "Text": "", "StyleSheet": f"color:rgb(180,180,180);{FONT_SM}", "Weight": 0}),
    ]

# ── 分隔符 ──
def _sep():
    return ui.Label({"Text": "", "StyleSheet": STYLE_DIVIDER, "Weight": 0})

# ── 授权区域 ──
TRIAL_LB = "trial_lb"
BTN_AI_TYPO = "btn_ai_typo"
HINT_LB = "hint_lb"
def _build_auth_section():
    """授权区域三行固定布局"""
    return [
        ui.HGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, [
            ui.Label({"ID": TRIAL_LB, "Text": "", "StyleSheet": STYLE_HINT, "Weight": 0}),
        ]),
    ]

# ── CONFIG_SECTIONS 注册表 ──
CONFIG_SECTIONS = [
    {"id": "mask_ratio",     "label": "画面遮幅宽高比", "type": "mask_ratio",      "builder": _build_mask_ratio},
    {"id": "smb_paths",      "label": "SMB 路径检测目录", "type": "smb_paths",       "builder": _build_smb_paths},
    {"id": "censor_personal","label": "个人违禁词词典",   "type": "censor_personal", "builder": _build_censor_personal},
    {"id": "deepseek_key",   "label": "DeepSeek API Key",  "type": "api_key",         "builder": lambda: _build_api_key_input("deepseek_key", "DeepSeek API Key")},
    {"id": "feishu_app_id",  "label": "飞书应用 ID",       "type": "api_key",         "builder": lambda: _build_api_key_input("feishu_app_id", "飞书应用 ID")},
    {"id": "feishu_secret",  "label": "飞书应用密钥",      "type": "api_key",         "builder": lambda: _build_api_key_input("feishu_secret", "飞书应用密钥")},
]

def _validate_config_sections():
    """CONFIG_SECTIONS 注册表校验：builder 可调用 + type 有 saver"""
    errors = []
    _known_types = {"api_key", "mask_ratio", "smb_paths", "censor_personal"}
    for s in CONFIG_SECTIONS:
        b = s.get("builder")
        if not callable(b):
            errors.append(f"CONFIG_SECTIONS['{s['id']}'] builder 不可调用: {b}")
        if s["type"] not in _known_types:
            errors.append(f"CONFIG_SECTIONS['{s['id']}'] type={s['type']} 未在 _do_save 中处理")
    if errors:
        raise AssertionError("CONFIG_SECTIONS 注册表校验失败:\n  " + "\n  ".join(errors))

_validate_config_sections()
del _validate_config_sections
