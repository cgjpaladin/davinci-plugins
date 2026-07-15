# -*- coding: utf-8 -*-
"""配置弹窗 builders + CONFIG_SECTIONS 注册表。
show_config_dialog 入口仍在 ui.py（需访问全局变量），本文件只提供纯 build 函数。
"""

from fusionscript_loader import bmd
fu = bmd.scriptapp("Fusion")
ui = fu.UIManager

from config import IS_PERSONAL, MANUAL_URL
from styles import *
from license_ui import trial_days_left, format_trial

import os, subprocess, time, socket, json


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



# ── 凭证持久化（macOS Keychain，零明文落盘）──
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

def _api_keys_path():  # 保留兼容旧调用
    return os.path.join(_DATA_DIR, "api_keys.json")


def _build_api_key_input(sid, label):
    """Label 显示当前值 + 编辑按钮（弹系统输入框防 IME 崩溃）"""
    is_secret = "secret" in sid or "key" in sid
    lbl_id = f"cfg_{sid}_lbl"
    btn_id = f"cfg_{sid}_btn"
    return [
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.Label({"ID": lbl_id, "Text": "",
                "StyleSheet": "font-size:11px;color:rgb(160,160,160)", "Weight": 1,
                "MinimumSize": [150, 22], "WordWrap": False}),
            ui.Button({"ID": btn_id, "Text": "编辑", "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
        ]),
    ]

def _build_censor_personal():
    return [
        ui.VGap(SPACE_TIGHT),
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.Button({"ID": "cfg_edit_censor", "Text": "在 Finder 中定位",
                       "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
            ui.Label({"Text": "右键 → 打开方式 → WPS / Excel / Numbers",
                      "StyleSheet": "color:rgb(140,140,140);font-size:12px", "Weight": 0}),
        ]),
    ]

_MASK_PRESETS = ["1", "1.33", "1.66", "1.77", "1.85", "2.0", "2.35", "2.39", "2.40"]
_MASK_UNSET = "（未设置）"

def _build_mask_ratio():
    """遮幅宽高比：下拉预设 + 自定义输入"""
    return [
        ui.Label({"Text": "DaVinci API 无法自动读取遮幅，请手动设置画面宽高比。",
                  "StyleSheet": "color:rgb(140,140,140);font-size:11px", "Weight": 0}),
        ui.VGap(SPACE_SM),
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.ComboBox({"ID": "cfg_mask_preset", "Text": "", "Weight": 0, "MinimumSize": [100, 0]}),
            ui.Label({"ID": "cfg_mask_custom_lbl", "Text": "自定义",
                      "StyleSheet": "color:rgb(140,140,140);font-size:13px", "Weight": 0}),
            ui.LineEdit({"ID": "cfg_mask_custom", "Text": "",
                         "StyleSheet": "font-size:12px",
                         "MinimumSize": [60, 0], "Weight": 0}),
        ]),
    ]

def _build_smb_paths():
    """服务器素材路径配置：ComboBox 选择 + 添加/删除按钮"""
    return [
        ui.ComboBox({"ID": "cfg_smb_paths_combo", "Text": ""}),
        ui.VGap(SPACE_SM),
        ui.HGroup({"Spacing": SPACE_SM, "Weight": 0}, [
            ui.Button({"ID": "cfg_smb_add", "Text": "+ 添加路径",
                       "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
            ui.Button({"ID": "cfg_smb_del", "Text": "− 删除路径",
                       "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
        ]),
    ]

CONFIG_SECTIONS = [
    {"id": "deepseek_key",   "label": "DeepSeek API Key", "type": "api_key",       "builder": _build_api_key_input},
    {"id": "feishu_app_id",  "label": "飞书 App ID", "type": "api_key",            "builder": _build_api_key_input},
    {"id": "feishu_secret",  "label": "飞书 App Secret", "type": "api_key",        "builder": _build_api_key_input},
    {"id": "mask_ratio",     "label": "画面遮幅宽高比", "type": "mask_ratio",      "builder": _build_mask_ratio},
    {"id": "smb_paths",      "label": "脱机素材检测路径（可多选）", "type": "smb_paths", "builder": _build_smb_paths},
    {"id": "censor_personal", "label": "个人词典", "type": "censor_personal",       "builder": _build_censor_personal},
]

_validate_config_sections()
del _validate_config_sections

# ── 分隔符 ──
def _sep():
    return ui.Label({"Text": "─" * 48, "Weight": 0,
        "StyleSheet": "color:rgb(80,80,80);font-size:10px"})

def _sec(title):
    return ui.Label({"Text": f"▸ {title}", "Weight": 0,
        "StyleSheet": "color:rgb(180,180,180);font-size:13px;font-weight:bold"})

def _build_auth_section():
    """授权管理：Label 显示状态/激活码 + 复制指纹 + 激活/停用按钮。"""
    return [
        _sec("授权管理"),
        ui.VGap(SPACE_SM),
        ui.Label({"ID": "cfg_auth_status", "Text": "", "Weight": 0,
            "StyleSheet": "color:rgb(200,180,60);font-size:12px"}),
        ui.VGap(SPACE_SM),
        ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, [
            ui.Button({"ID": "cfg_copy_fp", "Text": "复制指纹", "StyleSheet": BTN_STYLE, "Weight": 0}),
            ui.Button({"ID": "cfg_activate_btn", "Text": "激活", "StyleSheet": BTN_PRIMARY, "Weight": 0}),
            ui.Button({"ID": "cfg_deactivate_btn", "Text": "停用", "StyleSheet": BTN_STYLE, "Weight": 0}),
        ]),
        ui.VGap(SPACE_SM),
        _sep(),
    ]


