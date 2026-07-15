# -*- coding: utf-8 -*-
"""配置弹窗模块。被 ui.py 调用。"""

from fusionscript_loader import bmd
fu = bmd.scriptapp("Fusion")
ui = fu.UIManager
from config import IS_PERSONAL, MANUAL_URL
from styles import *
from license_ui import trial_days_left, format_trial

# UI 控件 ID（主窗口）
TRIAL_LB = "trial_lb"
BTN_AI_TYPO = "btn_ai_typo"
HINT_LB = "hint_lb"
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

_mask_ratio = None        # 遮幅宽高比（内存态：重启/切工程重置）
_last_project_name = ""   # 检测工程切换
_config_open = False  # 防配置窗口重复打开
def _check_project_mask_reset():
    """检测工程切换：换工程则重置遮幅为未设置"""
    global _mask_ratio, _last_project_name
    try:
        resolve = bmd.scriptapp('Resolve')
        if resolve:
            project = resolve.GetProjectManager().GetCurrentProject()
            if project:
                name = project.GetName()
                if name != _last_project_name:
                    _last_project_name = name
                    _mask_ratio = None
                    log_fn(f"🎬 工程切换: {name} — 遮幅已重置")
    except Exception:
        pass

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


def show_config_dialog(log_fn=None, _main_itm=None):
    """打开配置窗口"""
    if _config_open:
        return
    _config_open = True
    _check_project_mask_reset()  # 切工程则重置遮幅
    CONFIG_WIN_ID = "com.myjc.delivery_checker_config"

    config_disp = bmd.UIDispatcher(fu.UIManager)

    # ── 从注册表生成布局（个人版过滤）──
    _is_personal = IS_PERSONAL
    _sections = CONFIG_SECTIONS if _is_personal else [s for s in CONFIG_SECTIONS if s["id"] not in ("deepseek_key", "feishu_app_id", "feishu_secret")]
    body_widgets = []
    # 授权区（仅个人版，三行固定布局）
    if _is_personal:
        body_widgets.extend(_build_auth_section())
    # CONFIG_SECTIONS 各区域
    for section in _sections:
        sec_widgets = [_sec(section["label"])]
        builder = section.get("builder")
        if builder:
            if section["type"] == "api_key":
                sec_widgets.extend(builder(section["id"], section["label"]))
            else:
                sec_widgets.extend(builder())
        else:
            sec_widgets.append(ui.Label({"Text": f"(未知类型: {section['type']})", "StyleSheet": STYLE_WARN, "Weight": 0}))
        sec_widgets.append(_sep())
        body_widgets.append(ui.VGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, sec_widgets))

    config_layout = [
        ui.VGroup({"Spacing": SPACE_NONE}, [
            ui.VGroup({"Spacing": 0, "Weight": 0}, body_widgets),
            ui.VGap({"Weight": 1}),
            ui.Label({"ID": "cfg_hint", "Text": "", "Visible": False,
                      "StyleSheet": "color:rgb(220,80,60);font-size:12px", "Weight": 0}),
            # ── 按钮（底部居中）──
            ui.HGroup({"Spacing": SPACE_WIDE, "Weight": 0}, [
                ui.HGap({"Weight": 1}),
                ui.Button({"ID": "cfg_cancel", "Text": "关闭",
                           "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Button({"ID": "cfg_save", "Text": "保存",
                           "StyleSheet": BTN_PRIMARY, "Weight": 0}),
                ui.HGap({"Weight": 1}),
            ]),
        ]),
    ]

    config_dlg = config_disp.AddWindow({
        "WindowTitle": "交付自检工具 — 配置",
        "ID": CONFIG_WIN_ID,
        "Geometry": [820, 120, 360, 620],
        "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
    }, config_layout)

    cfg = config_dlg.GetItems()

    # ── 授权区初始化 ──
    if _is_personal:
        try:
            from shared.license import load_credential
            c = load_credential()
            p = c.get("payload", {}) if c else {}
            is_activated = c and not p.get("is_trial", True)
            if is_activated:
                cfg["cfg_auth_status"].Text = "✅ 已激活 · 永久授权"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(80,200,100);font-size:13px"
                cfg["cfg_activate_btn"].Enabled = False
                cfg["cfg_deactivate_btn"].Enabled = True
            else:
                tsd = p.get("trial_start_date")
                if tsd:
                    from datetime import date as _dt
                    d = trial_days_left(tsd)
                else:
                    d = 30
                cfg["cfg_auth_status"].Text = f"⏳ 试用剩余 {d} 天  |  ¥99 永久授权"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(200,180,60);font-size:12px"
                cfg["cfg_activate_btn"].Enabled = True
                cfg["cfg_deactivate_btn"].Enabled = False
        except Exception: pass

    # ── 预填（掩码显示，真值保留在 _api_values）──
    _keys = _load_api_keys()
    # 从 .env 迁移旧配置（兼容旧变量名）
    _migrated = False
    if not _keys or not _keys.get("deepseek_key"):
        for _env_candidate in [
            os.path.join(_SCRIPT_DIR, ".env"),
            "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
        ]:
            if not os.path.exists(_env_candidate): continue
            try:
                with open(_env_candidate, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEEPSEEK_API_KEY=") and not _keys.get("deepseek_key"):
                            _keys["deepseek_key"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                            _migrated = True
                        elif line.startswith("FEISHU_APP_ID=") or line.startswith("FEISHU_BOT_APP_ID="):
                            if not _keys.get("feishu_app_id"):
                                _keys["feishu_app_id"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                                _migrated = True
                        elif line.startswith("FEISHU_APP_SECRET=") or line.startswith("FEISHU_BOT_APP_SECRET="):
                            if not _keys.get("feishu_secret"):
                                _keys["feishu_secret"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                                _migrated = True
            except Exception: pass  # noop: 配置写入失败不影响主流程
            if _migrated and _keys:
                _save_api_keys(_keys); log_fn("📂 从 .env 迁移了 API 配置")
                break
    _api_values = {k: v for k, v in _keys.items() if v}
    def _mask(val):
        return val[:5] + "…" + val[-4:] if len(val) > 12 else val[:4] + "…" if len(val) > 8 else val
    try:
        if _keys.get("deepseek_key"): cfg["cfg_deepseek_key_lbl"].Text = _mask(_keys["deepseek_key"])
        if _keys.get("feishu_app_id"): cfg["cfg_feishu_app_id_lbl"].Text = _keys["feishu_app_id"]
        if _keys.get("feishu_secret"): cfg["cfg_feishu_secret_lbl"].Text = _mask(_keys["feishu_secret"])
    except Exception: pass

    # ── 轨道数量（LineEdit 直输）──
    try:
        cfg["cfg_sub"].Text = str(_track_values[0])
        cfg["cfg_vid"].Text = str(_track_values[1])
        cfg["cfg_aud"].Text = str(_track_values[2])
    except Exception:
        pass

    # 初始化子词典勾选框
    SUB_CBOX_MAP = [
        ("cfg_csub_cn", "cn"),
        ("cfg_csub_en", "en"),
        ("cfg_csub_bw", "bw"),
        ("cfg_csub_sms", "bw_sms"),
    ]
    for cbox_id, key in SUB_CBOX_MAP:
        try:
            cfg[cbox_id].Checked = _censor_subs.get(key, True)
        except Exception:
            pass

    # ── 保存 ──
    _save_busy = False
    def _save(ev):
        nonlocal _save_busy
        if _save_busy:
            return
        _save_busy = True
        cfg["cfg_save"].Enabled = False
        cfg["cfg_cancel"].Enabled = False
        try:
            _do_save(ev)
        finally:
            _save_busy = False
            cfg["cfg_save"].Enabled = True
            cfg["cfg_cancel"].Enabled = True

    def _do_save(ev):
        global _censor_subs, _ai_allowed
        err = ""
        _validation_err = False
        for section in _sections:
            t = section["type"]
            if t == "api_key":
                sid = section["id"]
                val = _api_values.get(sid, "")  # 从内存取值，非 UI 控件
                if val:
                    # 掩码（含"…"）→ 跳过校验，保留旧值
                    if "…" not in val:
                        _hints = {
                            "deepseek_key": ("sk-", 35, "DeepSeek Key 应以 sk- 开头，至少 35 位"),
                            "feishu_app_id": ("cli_", 20, "飞书 App ID 应以 cli_ 开头"),
                            "feishu_secret": ("", 10, "飞书 App Secret 至少 10 位"),
                        }
                        if sid in _hints:
                            prefix, min_len, hint = _hints[sid]
                            if (prefix and not val.startswith(prefix)) or len(val) < min_len:
                                _validation_err = True
                                try:
                                    cfg["cfg_hint"].Visible = True
                                    cfg["cfg_hint"].Text = f"⚠ {hint}"
                                except Exception: log_fn(f"⚠ cfg_hint 渲染失败: {hint}")
                                continue
                    try:
                        _keys = _load_api_keys()
                        # 如果用户输入的是掩码（含"…"），保留存储的真值
                        if "…" in val:
                            val = _api_values.get(sid, val)
                        _keys[sid] = val; _save_api_keys(_keys)
                        log_fn(f"🔑 {section['label']} 已保存")
                    except Exception as e:
                        err = f"保存失败: {e}"
                        log_fn(f"⚠ API Key 保存异常: {e}")
            elif t == "smb_paths":
                try:
                    from shared.deploy_config import save_smb_paths
                    ok = save_smb_paths(_smb_paths_cache)
                    log_fn(f"{'✅' if ok else '⚠'} 服务器路径: {len(_smb_paths_cache)} 条")
                    # 清缓存让下次检测重新采集路径信息
                    from check_core import _clear_clip_files_cache
                    _clear_clip_files_cache()
                except Exception as e:
                    log_fn(f"⚠ 路径保存失败: {e}")
            elif t == "censor_personal":
                pass
            elif t == "mask_ratio":
                global _mask_ratio
                preset = cfg["cfg_mask_preset"].CurrentText
                custom = cfg["cfg_mask_custom"].Text.strip()
                if preset == _MASK_UNSET:
                    _mask_ratio = None
                    log_fn("🎬 遮幅已清除（未设置）")
                    continue
                if preset in _MASK_PRESETS:
                    val = preset
                elif custom:
                    val = custom
                else:
                    _mask_ratio = None
                    log_fn("🎬 遮幅已清除（未设置）")
                    continue
                try:
                    fv = float(val)
                    if fv <= 0:
                        err = err or "遮幅值必须大于 0"
                        continue
                    if fv > 100:
                        err = err or "遮幅值过大（≤100）"
                        continue
                    _mask_ratio = val
                    log_fn(f"🎬 遮幅宽高比: {_mask_ratio}")
                except ValueError:
                    err = err or f"遮幅值无效: {val}（需为数字，如 2.35）"
        if err or _validation_err:
            if err: log_fn(f"⚠ {err}")
            try:
                cfg["cfg_hint"].Visible = True
                cfg["cfg_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                if err: cfg["cfg_hint"].Text = f"⚠ {err}"
            except Exception: log_fn(f"⚠ cfg_hint 渲染失败: {err}")
            return  # 不关闭对话框，留在配置页让用户重试
        config_dlg.Hide(); config_disp.ExitLoop()

    # ── 激活 / 停用（独立于配置保存，三行固定布局只改文字颜色）──
    if _is_personal:
        _auth_busy = False
        def _do_activate(ev):
            nonlocal _auth_busy
            if _auth_busy: return
            _auth_busy = True
            cfg["cfg_activate_btn"].Enabled = False
            try:
                import subprocess, re, os
                # tkinter 三框激活码弹窗（独立子进程，Popen 不阻塞 DaVinci UI）
                r = subprocess.Popen([sys.executable, "-c", r'''
import tkinter as tk, sys, os
# macOS: bring tkinter to front; Windows: no-op（Win32 默认前台）
if sys.platform == "darwin":
    import subprocess; subprocess.run(["/usr/bin/osascript", "-e", 'tell application "System Events" to set frontmost of process "Python" to true'], timeout=2, capture_output=True)
root = tk.Tk()
root.withdraw()  # 先隐藏，避免左上角闪现
root.title("交付自检工具 · 激活")
root.resizable(False, False)
root.attributes("-topmost", True)
root.lift()
root.focus_force()

tk.Label(root, text="请输入激活码", font=("", 12)).pack(pady=(15, 5))

frame = tk.Frame(root)
frame.pack(pady=5)
entries = []
svars = []

def _validate(new):
    return new == "" or (len(new) <= 4 and all(c.isascii() and c.isalnum() for c in new))

def _on_change(idx):
    val = ''.join(c for c in svars[idx].get() if c.isascii() and c.isalnum()).upper()
    svars[idx].set(val)
    if len(val) == 4 and idx < 2:
        entries[idx + 1].focus_set()
    elif len(val) == 0 and idx > 0:
        entries[idx - 1].focus_set()
        entries[idx - 1].icursor("end")

for i in range(3):
    sv = tk.StringVar()
    sv.trace_add("write", lambda *a, idx=i: _on_change(idx))
    svars.append(sv)
    e = tk.Entry(frame, width=6, font=("Menlo", 16), justify="center",
                 textvariable=sv, validate="key",
                 validatecommand=(root.register(_validate), "%P"))
    e.pack(side="left", padx=2)
    entries.append(e)
    if i < 2:
        tk.Label(frame, text="—", font=("", 14), fg="#888").pack(side="left")

btn_frame = tk.Frame(root)
btn_frame.pack(pady=(15, 10))
result = [""]
err_lbl = tk.Label(root, text="", fg="#d04040", font=("", 11))
err_lbl.pack()

def _ok():
    parts = [sv.get().strip().upper() for sv in svars]
    if len(parts[0]) == 4 and len(parts[1]) == 4 and len(parts[2]) == 4:
        result[0] = f"{parts[0]}-{parts[1]}-{parts[2]}"
        root.destroy()
    else:
        err_lbl.config(text="⚠ 请输入完整 12 位")

tk.Button(btn_frame, text="取消", width=8, command=root.destroy).pack(side="left", padx=5)
tk.Button(btn_frame, text="激活", width=8, command=_ok).pack(side="left", padx=5)
# 居中
root.update_idletasks()
w, h = root.winfo_width(), root.winfo_height()
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"+{int((sw-w)/2)}+{int((sh-h)/2)}")
root.deiconify()  # 中心就位后再显示
entries[0].focus_set()
root.mainloop()
print(result[0])
'''], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    stdout, stderr = r.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    r.kill()
                    cfg["cfg_activate_btn"].Enabled = True; _auth_busy = False; return
                if r.returncode != 0:
                    log_fn(f"🪟 激活弹窗: 子进程异常 (退出码 {r.returncode})")
                    cfg["cfg_activate_btn"].Enabled = True; _auth_busy = False; return
                code = stdout.strip()
                if not code:
                    cfg["cfg_activate_btn"].Enabled = True; _auth_busy = False; return
                if not re.fullmatch(r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}', code):
                    cfg["cfg_auth_status"].Text = "⚠ 激活码格式错误"
                    cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                    cfg["cfg_activate_btn"].Enabled = True; _auth_busy = False; return
                cfg["cfg_auth_status"].Text = "⏳ 正在连接服务器…"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,160,40);font-size:12px"
                cfg["cfg_activate_btn"].Enabled = False
                cfg["cfg_deactivate_btn"].Enabled = False
                cfg["cfg_save"].Enabled = False
                cfg["cfg_cancel"].Enabled = False
                from shared.license import activate, load_credential
                c = load_credential()
                ts = 0
                if c and c.get("payload", {}).get("is_trial"):
                    ts = max(0, c["payload"].get("expire_time", 0) - int(time.time()))
                ok, msg = activate(code)
                log_fn(f"🔑 激活: {'✅' if ok else '❌'} {msg}")
                if ok:
                    global _ai_allowed
                    _ai_allowed = True
                    _keys = _load_api_keys(); _keys["activation_code"] = code
                    if ts: _keys["trial_remain_secs"] = str(ts)
                    _save_api_keys(_keys)
                    _main_itm[BTN_AI_TYPO].Text = "字幕检测"; _main_itm[BTN_AI_TYPO].Enabled = True
                    _main_itm[TRIAL_LB].Text = "已激活 ✓"
                    cfg["cfg_auth_status"].Text = "✅ 已激活 · 永久授权"
                    cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(80,200,100);font-size:13px"
                    cfg["cfg_activate_btn"].Enabled = False
                    cfg["cfg_deactivate_btn"].Enabled = True
                else:
                    _log_activate_fail(code, msg)
                    cfg["cfg_auth_status"].Text = f"⚠ {msg}"
                    cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                    cfg["cfg_activate_btn"].Enabled = True
                    cfg["cfg_deactivate_btn"].Enabled = False
            except Exception as e:
                import traceback
                _log_activate_fail(code, f"{e}\n{traceback.format_exc()}")
                cfg["cfg_auth_status"].Text = f"⚠ 激活失败: {e}"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                cfg["cfg_activate_btn"].Enabled = True
                cfg["cfg_deactivate_btn"].Enabled = False
            finally:
                _auth_busy = False
                cfg["cfg_save"].Enabled = True
                cfg["cfg_cancel"].Enabled = True

        def _do_deactivate(ev):
            nonlocal _auth_busy
            if _auth_busy: return
            _auth_busy = True
            try:
                cfg["cfg_auth_status"].Text = "⏳ 正在连接服务器…"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,160,40);font-size:12px"
                cfg["cfg_deactivate_btn"].Enabled = False
                cfg["cfg_activate_btn"].Enabled = False
                cfg["cfg_save"].Enabled = False
                cfg["cfg_cancel"].Enabled = False
                from shared.license import deactivate, load_credential
                ok, msg = deactivate()
                log_fn(f"🔓 停用: {'✅' if ok else '❌'} {msg}")
                if ok:
                    global _ai_allowed
                    _ai_allowed = False
                    _keys = _load_api_keys()
                    if _keys.get("activation_code"): del _keys["activation_code"]; _save_api_keys(_keys)
                    _main_itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"; _main_itm[BTN_AI_TYPO].Enabled = False
                    c = load_credential()
                    p = c.get("payload", {}) if c else {}
                    tsd = p.get("trial_start_date")
                    if tsd:
                        from datetime import date as _dt
                        d = trial_days_left(tsd)
                    elif p.get("expire_time"):
                        d = max(0, (p["expire_time"] - int(time.time())) // 86400)
                    else:
                        d = 30
                    _main_itm[TRIAL_LB].Text = format_trial(d, p.get("machine_fingerprint", "")[:8])
                    cfg["cfg_auth_status"].Text = f"⏳ 试用剩余 {d} 天"
                    cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(200,180,60);font-size:12px"
                    cfg["cfg_activate_btn"].Enabled = True
                    cfg["cfg_deactivate_btn"].Enabled = False
                else:
                    cfg["cfg_auth_status"].Text = f"⚠ {msg}"
                    cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                    cfg["cfg_deactivate_btn"].Enabled = True
                    cfg["cfg_activate_btn"].Enabled = False
            except Exception as e:
                cfg["cfg_auth_status"].Text = f"⚠ 停用失败: {e}"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                cfg["cfg_deactivate_btn"].Enabled = True
            finally:
                _auth_busy = False
                cfg["cfg_save"].Enabled = True
                cfg["cfg_cancel"].Enabled = True

        try: config_dlg.On["cfg_activate_btn"].Clicked = _do_activate
        except Exception: pass
        try: config_dlg.On["cfg_deactivate_btn"].Clicked = _do_deactivate
        except Exception: pass

        # ── 复制指纹 ──
        def _copy_fp(ev):
            import subprocess as _sp
            try:
                from shared.license import get_machine_fingerprint
                fp = get_machine_fingerprint()
                if sys.platform == "darwin":
                    _sp.run(["pbcopy"], input=fp.encode(), timeout=3)
                else:
                    _sp.run(["clip"], input=fp.encode(), timeout=3, shell=True)
                cfg["cfg_auth_status"].Text = "✅ 指纹已复制到剪贴板"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(80,200,100);font-size:12px"
            except Exception as e:
                cfg["cfg_auth_status"].Text = f"⚠ 复制失败: {e}"
                cfg["cfg_auth_status"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
        try: config_dlg.On["cfg_copy_fp"].Clicked = _copy_fp
        except Exception: pass

        # ── API Key 编辑按钮 → 系统弹窗（防 UIManager IME 崩溃）──
        _api_edit_config = {
            "deepseek_key": {"title": "交付自检工具 · DeepSeek API Key", "prompt": "请输入 DeepSeek API Key（以 sk- 开头）", "is_secret": True},
            "feishu_app_id": {"title": "交付自检工具 · 飞书 App ID", "prompt": "请输入飞书 App ID（以 cli_ 开头）", "is_secret": False},
            "feishu_secret": {"title": "交付自检工具 · 飞书 App Secret", "prompt": "请输入飞书 App Secret", "is_secret": True},
        }
        _api_edit_busy = set()
        def _make_api_edit_handler(sid):
            def _handler(ev):
                nonlocal _api_values, _api_edit_busy
                if sid in _api_edit_busy:
                    return
                _api_edit_busy.add(sid)
                btn_id = f"cfg_{sid}_btn"
                try:
                    cfg[btn_id].Enabled = False
                except Exception: pass
                try:
                    cfg_info = _api_edit_config[sid]
                    from tk_dialogs import input_text
                    val = input_text(
                        prompt=cfg_info["prompt"],
                        title=cfg_info["title"],
                        default=_api_values.get(sid, ""),
                        is_secret=cfg_info["is_secret"])
                    if not val:
                        if sid in _api_values:
                            del _api_values[sid]
                        cfg[f"cfg_{sid}_lbl"].Text = ""
                    else:
                        _api_values[sid] = val
                        lbl_id = f"cfg_{sid}_lbl"
                        masked = val[:5] + "…" + val[-4:] if len(val) > 12 else val
                        cfg[lbl_id].Text = masked
                    log_fn(f"🔑 {cfg_info['prompt'].split('（')[0].strip()} 已编辑")
                finally:
                    _api_edit_busy.discard(sid)
                    try:
                        cfg[btn_id].Enabled = True
                    except Exception: pass
            return _handler

        for sid in ["deepseek_key", "feishu_app_id", "feishu_secret"]:
            try:
                config_dlg.On[f"cfg_{sid}_btn"].Clicked = _make_api_edit_handler(sid)
            except Exception: pass

    # ── 编辑违禁词 ──
    censor_path = _CENSOR_PERSONAL_CSV
    def _edit_censor(ev):
        import subprocess
        from check_core import clear_censor_cache
        clear_censor_cache(censor_path)
        try:
            import subprocess
            if _sys.platform == "darwin":
                log_fn(f"📂 即将打开 Finder: {censor_path}")
                subprocess.Popen(["open", "-R", censor_path])
            else:
                log_fn(f"📂 即将打开 Explorer: {censor_path}")
                subprocess.Popen(["explorer", "/select,", censor_path])
        except Exception:
            _main_itm[HINT_LB].Text = "右键「短剧违禁词表.csv」→ 打开方式 → WPS / Excel / Numbers"
            log_fn("📝 Finder 已定位个人词典")

    # ── SMB 路径编辑 ──（_smb_paths_cache 已在上方从 deploy.json 加载）

    def _refresh_smb_paths_combo():
        nonlocal _smb_paths_cache
        c = cfg["cfg_smb_paths_combo"]
        c.Clear()
        if _smb_paths_cache:
            for p in _smb_paths_cache:
                c.AddItem(p)
            c.Text = _smb_paths_cache[0]
        else:
            c.Text = "未配置：路径检测将被跳过"

    _smb_add_busy = False
    def _add_smb_path(ev):
        nonlocal _smb_paths_cache, _smb_add_busy
        if _smb_add_busy: return
        _smb_add_busy = True
        cfg["cfg_smb_add"].Enabled = False
        try:
            path = fu.RequestDir()
            if path and path not in _smb_paths_cache:
                _smb_paths_cache.append(path)
                _refresh_smb_paths_combo()
                log_fn(f"📂 添加路径: {path}")
        except Exception as e:
            log_fn(f"⚠ 文件夹选择失败: {e}")
        finally:
            _smb_add_busy = False
            cfg["cfg_smb_add"].Enabled = True

    def _delete_smb_path(ev):
        nonlocal _smb_paths_cache
        selected = cfg["cfg_smb_paths_combo"].CurrentText
        if not selected or selected not in _smb_paths_cache:
            return
        _smb_paths_cache.remove(selected)
        _refresh_smb_paths_combo()
        log_fn(f"🗑 删除路径: {selected}")

    config_dlg.On["cfg_edit_censor"].Clicked = _edit_censor
    config_dlg.On["cfg_smb_add"].Clicked = _add_smb_path
    config_dlg.On["cfg_smb_del"].Clicked = _delete_smb_path
    config_dlg.On["cfg_save"].Clicked = _save
    config_dlg.On["cfg_cancel"].Clicked = lambda ev: config_disp.ExitLoop()
    config_dlg.On[CONFIG_WIN_ID].Close = lambda ev: config_disp.ExitLoop()

    log_fn("⚙ 打开配置窗口")
    # 初始化 SMB 路径显示（必须在 handler 定义之后调用 _refresh_smb_paths_combo）
    try:
        from shared.deploy_config import get_smb_paths
        _smb_paths_cache = get_smb_paths()
        _refresh_smb_paths_combo()
    except Exception:
        _smb_paths_cache = []

    # 初始化遮幅宽高比 ComboBox
    
    try:
        combo = cfg["cfg_mask_preset"]
        
        combo.AddItem(_MASK_UNSET)
        
        for p in _MASK_PRESETS:
            combo.AddItem(p)
        
        if _mask_ratio is None:
            combo.SetCurrentIndex(0)
            cfg["cfg_mask_custom"].Text = ""
            log_fn(f"🎬 mask_init: state=None idx=0")
        elif _mask_ratio in _MASK_PRESETS:
            idx = _MASK_PRESETS.index(_mask_ratio) + 1
            combo.SetCurrentIndex(idx)
            cfg["cfg_mask_custom"].Text = ""
            log_fn(f"🎬 mask_init: state=preset({_mask_ratio}) idx={idx}")
        else:
            combo.SetCurrentIndex(len(_MASK_PRESETS))
            cfg["cfg_mask_custom"].Text = _mask_ratio
            log_fn(f"🎬 mask_init: state=custom({_mask_ratio})")
    except Exception as _e:
        import traceback
        log_fn(f"⚠ 遮幅初始化失败: {_e}\n{traceback.format_exc()}")

    config_dlg.Show()
    config_dlg.RecalcLayout()
    config_disp.RunLoop()
    config_dlg.Hide()
    _config_open = False

