# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 外部进程版
绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import queue

os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.append(_RESOLVE_MODULES)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import DaVinciResolveScript as bmd
from config import (
    DEBUG, get_project_root, get_output_dir, get_log_dir, __version__,
)
from watermark_state import init as state_init, is_locked as state_is_locked, acquire_lock, release_lock, get_original_path
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    estimate_cost, query_balance, post_check, CLIP_COLOR as _CLIP_COLOR,
    create_wuhenai_adapter, download_and_apply,
)
from adapters.wuhenai_v2 import wuhenai_set_logger
from adapters import WatermarkTask
from logger import UILogger, set_logger, info, warn, fail, ok as log_ok

WIN_ID = "com.myjc.ai_subtitle_ui"
MODE = "pro_box"  # 固定：正式出片，后续不切模式

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

_state = {"processing": False, "stop": False, "project_root": "", "clips": [], "clips_scanned": False}

# ── 控件ID ──
BAL_LB = "bal_lb"
OSS_LB = "oss_lb"
PROJ_LB = "proj_lb"
PATH_LB = "path_lb"
BTN_SCAN, BTN_START, BTN_STOP = "btn_scan", "btn_start", "btn_stop"
BTN_PICK = "btn_pick"
BTN_UNDO = "btn_undo"
COLOR_CB = "color_cb"
LOG_LB, ST_LB = "log_lb", "st_lb"
PG_BG, PG_BAR = "pg_bg", "pg_bar"

# ── 片段颜色（达芬奇 API 实测 16 色，中文名匹配 20.x 官方翻译）──
_CLIP_COLORS = [
    ("Orange",    "橙色",     (235, 110, 0)),
    ("Apricot",   "杏色",     (255, 168, 51)),
    ("Yellow",    "黄色",     (226, 169, 28)),
    ("Lime",      "青柠色",   (159, 198, 21)),
    ("Olive",     "橄榄色",   (94,  153, 32)),
    ("Green",     "绿色",     (68,  143, 100)),
    ("Teal",      "青色",     (0,   152, 153)),
    ("Navy",      "海军蓝",   (31,  50,  119)),
    ("Blue",      "蓝色",     (67,  118, 161)),
    ("Purple",    "紫色",     (153, 115, 160)),
    ("Violet",    "紫罗兰色", (208, 87,  141)),
    ("Pink",      "粉色",     (233, 140, 181)),
    ("Tan",       "棕色",     (185, 176, 151)),
    ("Beige",     "米色",     (198, 160, 119)),
    ("Brown",     "褐色",     (153, 102, 0)),
    ("Chocolate", "巧克力色", (140, 90,  63)),
]
_SELECTED_COLOR = _CLIP_COLOR  # 默认橙色

# ── 暗色按钮样式 ──
BTN_STYLE = (
    "QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
BTN_PRIMARY = (
    "QPushButton{max-height:28px;background-color:rgb(50,120,220);color:rgb(255,255,255);"
    "border:1px solid rgb(70,140,240);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(65,135,235)}"
    "QPushButton:pressed{background-color:rgb(40,100,200)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40);border-color:rgb(60,60,60)}"
)
BTN_DANGER = (
    "QPushButton{max-height:28px;background-color:rgb(200,50,50);color:rgb(255,255,255);"
    "border:1px solid rgb(220,70,70);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(220,65,65)}"
    "QPushButton:pressed{background-color:rgb(160,40,40)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40);border-color:rgb(60,60,60)}"
)
LABEL_DIM = "color:rgb(170,170,170);font-size:12px"
LABEL_VAL = "color:rgb(220,220,220);font-size:12px"

# ── 窗口 ──
window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # 上半区：固定高度
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            # Row 1: 项目路径 + 余额
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Button({"ID": BTN_PICK, "Text": "选择项目路径", "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Label({"ID": PATH_LB, "Text": "未指定项目路径",
                          "StyleSheet": "color:rgb(180,180,180);font-size:11px", "Weight": 1}),
                ui.VGroup({"Spacing": 2, "Weight": 0}, [
                    ui.Label({"ID": BAL_LB, "Text": "查询中...",
                              "StyleSheet": "color:rgb(220,220,220);font-size:11px;min-width:180px;qproperty-alignment:AlignRight"}),
                    ui.Label({"ID": OSS_LB, "Text": "查询中...",
                              "StyleSheet": "color:rgb(200,200,200);font-size:11px;min-width:180px;qproperty-alignment:AlignRight"}),
                ]),
            ]),
            # Row 2: 筛选 + 扫描 + 处理
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "筛选", "StyleSheet": "color:rgb(150,150,150);font-size:12px", "Weight": 0}),
                ui.Label({"ID": "color_dot", "Text": "●",
                          "StyleSheet": "color:rgb(235,110,0);font-size:14px;"
                          "qproperty-alignment:AlignCenter", "Weight": 0}),
                ui.ComboBox({"ID": COLOR_CB, "Weight": 0}),
                ui.Button({"ID": BTN_SCAN, "Text": "扫描当前选区", "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Button({"ID": BTN_START, "Text": "开始处理", "StyleSheet": BTN_PRIMARY, "Weight": 0}),
                ui.Button({"ID": BTN_STOP, "Text": "停止", "StyleSheet": BTN_DANGER, "Weight": 0}),
                ui.Button({"ID": BTN_UNDO, "Text": "撤销替换", "StyleSheet": BTN_STYLE, "Weight": 0}),
            ]),
        ]),

        # 日志区（唯一可缩放）
        ui.TextEdit({"ID": LOG_LB, "Text": "",
                     "StyleSheet": "color:rgb(200,200,200);background-color:rgb(30,30,30);"
                                   "border:1px solid rgb(50,50,50);border-radius:4px;"
                                   "padding:6px;min-height:100px",
                     "TextInteractionFlags": 13, "Weight": 1}),

        # 下半区：状态信息
        ui.VGroup({"ID": "bottom_bar", "Spacing": 2, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Label({"ID": PROJ_LB, "Text": "① 请先选择项目路径",
                          "StyleSheet": "color:rgb(200,200,200);font-size:13px", "Weight": 2}),
                ui.Label({"ID": "warn_lb", "Text": "⚠ 请勿删除待处理片段或切换项目",
                          "StyleSheet": "color:rgb(255,80,80);font-size:12px;font-weight:bold", "Weight": 0}),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"裁缝老师的达芬奇插件工坊 ✂️ | v{__version__}",
                          "StyleSheet": "color:rgb(100,100,100);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": f"AI 去字幕",
    "ID": WIN_ID,
    "Geometry": [800, 100, 700, 560],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# 初始状态 — 未选项目路径前，筛选和扫描不可用
itm[COLOR_CB].Enabled = False
itm[BTN_SCAN].Enabled = False
itm[BTN_START].Enabled = False
itm[BTN_STOP].Enabled = False
itm[BTN_UNDO].Enabled = False
itm["warn_lb"].Visible = False
itm[BTN_STOP].Enabled = False
itm["warn_lb"].Visible = False

# 颜色下拉框
for ename, cname, _ in _CLIP_COLORS:
    itm[COLOR_CB].AddItem(cname)
default_idx = next(i for i, (en, _, _) in enumerate(_CLIP_COLORS) if en == _CLIP_COLOR)
itm[COLOR_CB].CurrentIndex = default_idx
def _color_style(r, g, b):
    return (f"QComboBox{{background-color:rgb({r},{g},{b});color:white;"
            f"border:1px solid rgb(80,80,80);border-radius:8px;padding:0px 6px;font-size:12px}}")
default_idx = next(i for i, (en, _, _) in enumerate(_CLIP_COLORS) if en == _CLIP_COLOR)
itm[COLOR_CB].CurrentIndex = default_idx
def _on_color_change(ev):
    idx = itm[COLOR_CB].CurrentIndex
    if 0 <= idx < len(_CLIP_COLORS):
        global _SELECTED_COLOR
        _SELECTED_COLOR, _, (r, g, b) = _CLIP_COLORS[idx]
        itm["color_dot"].StyleSheet = (
            f"color:rgb({r},{g},{b});font-size:14px;qproperty-alignment:AlignCenter")
        # 已选项目路径时，自动重扫
        if _state["project_root"]:
            scan_io()
dlg.On[COLOR_CB].CurrentIndexChanged = _on_color_change

# ── 线程安全的日志队列 ──
_log_queue = queue.Queue()
_main_thread = threading.current_thread()
import tempfile as _tempfile
_UI_LOG_FILE = os.path.join(_tempfile.gettempdir(), "ai_subtitle_ui.log")

_LOG_MAX_LINES = 200
_log_line_count = 0

def _ui_write_direct(msg: str):
    """主线程直写 TextEdit + 文件持久化；子线程只入队"""
    global _log_line_count
    on_main = threading.current_thread() is _main_thread
    if on_main:
        try:
            te = itm[LOG_LB]
            _log_line_count += 1
            if _log_line_count > _LOG_MAX_LINES:
                current = te.PlainText or ""
                lines = (current + msg).split("\n")
                te.PlainText = "\n".join(lines[-_LOG_MAX_LINES:])
                _log_line_count = _LOG_MAX_LINES
            else:
                te.Append(msg + "\n")
        except: pass
    else:
        _log_queue.put(msg)
    # 文件持久化（本地 + SMB 双写，方便查同事日志）
    try:
        with open(_UI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except: pass

def _ui_write(msg: str):
    _ui_write_direct(msg)

# ── SMB 关键事件日志：一人一文件，方便远程 debug ──
import socket
_SMB_LOG = os.path.join(os.path.dirname(__file__), "logs", f"{socket.gethostname()}.log")
def _smb_log(msg: str):
    """只记关键事件到 SMB，不记适配器噪音"""
    try:
        ts = time.strftime("%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(_SMB_LOG), exist_ok=True)
        with open(_SMB_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except: pass

def _flush_log():
    """主线程调用：批量刷日志到 TextEdit"""
    try:
        te = itm[LOG_LB]
        while not _log_queue.empty():
            msg = _log_queue.get_nowait()
            te.Append(msg + "\n")
    except: pass

# 注入日志器（所有 info/warn/fail/ok 都走 _ui_write → 入队）
set_logger(UILogger(_ui_write))

# ── 错误捕捉 → UI 日志 ──
import sys as _sys
_stderr_backup = _sys.stderr
class _UIStderr:
    def write(self, msg):
        if msg.strip():
            _ui_write(msg.rstrip())
        _stderr_backup.write(msg)
    def flush(self): _stderr_backup.flush()
_sys.stderr = _UIStderr()

# ── 子线程 → 主线程 UI 状态桥 ──
_ui_lock = threading.Lock()
_ui_pending = {"status": "", "balance": "", "progress": 0.0, "btn_scan": None, "btn_start": None, "btn_pick": None, "btn_stop": None, "warn": None}

def _st(t):
    """设置状态文本（状态栏已隐藏，仅写日志）"""
    pass
    _log_file(f"[状态] {t}")

def _log_file(msg: str):
    """写本地 + SMB 双日志（操作和状态，方便远程 debug）"""
    try:
        with open(_UI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except: pass
    try:
        with open(_SMB_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except: pass

def _log_action(action: str):
    """记录用户操作到日志"""
    _log_file(f"[操作] {action}")
def _bal(t):
    try: itm[BAL_LB].Text = t
    except: pass
    with _ui_lock: _ui_pending["balance"] = t
def _pg(r):
    """进度条（已隐藏）"""
    pass
def _set_btn(scan=None, start=None, pick=None, stop=None, warn=None):
    """设置按钮状态（主线程直写 + 子线程挂起）"""
    try:
        if scan is not None: itm[BTN_SCAN].Enabled = scan
        if start is not None: itm[BTN_START].Enabled = start
        if pick is not None: itm[BTN_PICK].Enabled = pick
        if stop is not None: itm[BTN_STOP].Enabled = stop
        if warn is not None: itm["warn_lb"].Visible = warn
    except: pass
    with _ui_lock:
        if scan is not None: _ui_pending["btn_scan"] = scan
        if start is not None: _ui_pending["btn_start"] = start
        if pick is not None: _ui_pending["btn_pick"] = pick
        if stop is not None: _ui_pending["btn_stop"] = stop
        if warn is not None: _ui_pending["warn"] = warn

def _apply_ui_state():
    """主线程调用：把 _ui_pending 刷到真实控件"""
    try:
        with _ui_lock:
            st = _ui_pending["status"]; bal = _ui_pending["balance"]
            pg = _ui_pending["progress"]
            bs = _ui_pending["btn_scan"]; b1 = _ui_pending["btn_start"]
            bp = _ui_pending["btn_pick"]; b2 = _ui_pending["btn_stop"]
            wl = _ui_pending["warn"]
        if bal: itm[BAL_LB].Text = bal
        if bs is not None: itm[BTN_SCAN].Enabled = bs
        if b1 is not None: itm[BTN_START].Enabled = b1
        if bp is not None: itm[BTN_PICK].Enabled = bp
        if b2 is not None: itm[BTN_STOP].Enabled = b2
        if wl is not None: itm["warn_lb"].Visible = wl
    except: pass

def _set_proj(path):
    try:
        label = path if path else "未指定项目路径"
        # 太长截断显示
        if len(label) > 80:
            label = "..." + label[-77:]
        itm[PATH_LB].Text = label
    except: pass

def pick_project(*_):
    """打开 macOS 原生文件夹选择器"""
    _log_action("选择项目路径")
    try:
        r = subprocess.run(
            ['osascript', '-e',
             'POSIX path of (choose folder with prompt "选择项目根目录（包含04_素材的文件夹）")'],
            capture_output=True, encoding="utf-8", timeout=60
        )
        path = r.stdout.strip()
        if path and os.path.isdir(path):
            _state["project_root"] = path
            _set_proj(path)
            state_init(path)
            # 解锁筛选和扫描
            itm[COLOR_CB].Enabled = True
            itm[BTN_SCAN].Enabled = True
            itm[BTN_UNDO].Enabled = True
            itm[BTN_START].Enabled = _state["clips_scanned"] and bool(_state["project_root"])
            # 更新左下角引导
            itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区" if not _state["clips_scanned"] else "③ 请点击开始处理"
            if _state["clips_scanned"]:
                _refresh_scan_display()  # 重新查缓存，🟠→🟢
        elif path:
            warn("所选路径不存在")
    except Exception as e:
        if "User canceled" not in str(e):
            fail(f"选择失败: {e}")


# ── 扫描 ──
def scan_io(*_):
    _log_action("扫描当前选区")
    _st("扫描中...")
    _state["clips_scanned"] = False
    try: itm[LOG_LB].Text = ""
    except: pass
    try:
        _, project, timeline = connect_resolve()
        clips, report = scan_io_clips(timeline, _SELECTED_COLOR)

        if clips is None:
            warn("请设置 IO 入出点"); _st("就绪 — 请设置 IO 入出点"); return
        if not clips:
            info("IO 内无符合筛选的片段"); _st("无有效片段"); return

        _state["clips"] = clips
        _state["scanned_count"] = report.valid

        info("── ① 扫描选区 ──")

        # 获取 IO 范围
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        _state["io_in"] = io_in
        _state["io_out"] = io_out
        _state["timeline_name"] = timeline.GetName()

        # 时间线帧率 → 帧号转分:秒
        fps_str = project.GetSetting("timelineFrameRate")
        fps = float(fps_str) if fps_str else 25.0
        _state["fps"] = fps

        # 逐片段显示 + 缓存检测
        from core import find_cached_output
        pr = _state["project_root"] or ""
        od = pr and get_output_dir(pr) or ""
        cache_hits = 0
        need_secs = 0
        need_pts = 0
        for c in clips:
            # 帧 → 时控码 时:分:秒:帧
            f = c.start_frame
            total_sec = int(f / fps)
            h, m = divmod(total_sec, 3600)
            m2, s = divmod(m, 60)
            rem_f = int(f - total_sec * fps)
            pos_str = f"{h:02d}:{m2:02d}:{s:02d}:{rem_f:02d}"
            is_cached = od and find_cached_output(c.file_name, od)
            if not od:
                label, emoji = "未知", "🟠"  # 无项目路径，无法查缓存
            else:
                label, emoji = ("可复用", "🟢") if is_cached else ("需处理", "🟡")
            info(f"  {emoji} {c.name}	位置：{pos_str}	长度：{c.duration:.0f}秒	{label}")
            if is_cached:
                cache_hits += 1
            else:
                need_secs += c.duration
                need_pts += int(c.duration) + (1 if c.duration % 1 > 0 else 0)  # ceil

        # 总结
        from pricing import point_to_yuan
        need = len(clips) - cache_hits
        pts = max(1, need_pts)
        yuan = point_to_yuan(pts)
        avg = max(60, min(120, need_secs / max(1, need) * 3)) if need > 0 else 0
        # 批量并行：同时处理，总时间 ≈ 上传+处理+下载，约 2x素材时长 + 60s 基础开销
        total_time = max(1, int((need_secs * 2 + 60) / 60)) if need > 0 else 0
        summary = f"扫描结果：当前选区内，共 {len(clips)} 个符合筛选条件的片段"
        if od:
            if cache_hits > 0:
                summary += f"（其中 {cache_hits} 个可复用）"
            summary += f"  |  {need} 个待处理"
        else:
            summary += "  |  请先选择项目路径以启用缓存复用"
        info(summary)
        ops_logger.cost_estimate(pts, yuan, total_time, need, cache_hits)
        if need > 0 and od:
            info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")

        _state["clips_scanned"] = True
        itm[BTN_START].Enabled = bool(_state["project_root"])
        if _state["project_root"]:
            itm[PROJ_LB].Text = "③ 请点击开始处理"
        _st(f"待处理: {report.valid} 个片段")
        _smb_log(f"扫描 — 项目: {project.GetName()} 时间线: {timeline.GetName()} IO={io_in}→{io_out} 内{report.valid}片段 需处理{need} 预估¥{yuan}")
        refresh_bal()
    except Exception as e:
        fail(f"扫描失败: {e}")
        _smb_log(f"扫描失败: {e}")

def _refresh_scan_display():
    """选完项目路径后，刷新已扫描片段的缓存状态（🟠→🟢/🟡）"""
    clips = _state.get("clips", [])
    if not clips:
        return
    from pricing import point_to_yuan
    pr = _state["project_root"]
    od = pr and get_output_dir(pr) or ""
    fps = _state.get("fps", 25.0)
    cache_hits = 0; need_secs = 0; need_pts = 0

    itm[LOG_LB].Text = ""
    info("── ① 扫描选区 ──")
    for c in clips:
        f = c.start_frame
        total_sec = int(f / fps)
        h, m = divmod(total_sec, 3600)
        m2, s = divmod(m, 60)
        rem_f = int(f - total_sec * fps)
        pos_str = f"{h:02d}:{m2:02d}:{s:02d}:{rem_f:02d}"
        is_cached = od and find_cached_output(c.file_name, od)
        label, emoji = ("可复用", "🟢") if is_cached else ("需处理", "🟡")
        info(f"  {emoji} {c.name}	位置：{pos_str}	长度：{c.duration:.0f}秒	{label}")
        if is_cached:
            cache_hits += 1
        else:
            need_secs += c.duration
            need_pts += int(c.duration) + (1 if c.duration % 1 > 0 else 0)

    need = len(clips) - cache_hits
    pts = max(1, need_pts)
    yuan = point_to_yuan(pts)
    summary = f"扫描结果：当前选区内，共 {len(clips)} 个符合筛选条件的片段"
    if cache_hits > 0:
        summary += f"（其中 {cache_hits} 个可复用）"
    summary += f"  |  {need} 个待处理"
    info(summary)
    if need > 0:
        avg = max(60, min(120, need_secs / max(1, need) * 3))
        total_time = int(need * avg / 60)
        info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")
        _st("就绪")


# ── 余额 ──
def refresh_bal():
    pts = query_balance()
    if pts > 0:
        from pricing import point_to_yuan, ACTIVE_PROVIDER
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _bal(f"{name} | ¥{point_to_yuan(pts):.2f}")
    else:
        _bal("余额: 查询失败")


# ── 阿里云余额 ──
def refresh_oss_bal():
    """查阿里云账户现金余额"""
    try:
        import hmac, hashlib, base64, urllib.request, urllib.parse, time as _time
        from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
        if not OSS_ACCESS_KEY_ID:
            itm[OSS_LB].Text = "阿里云 | 未配置凭证"
            return
        params = {
            'Action': 'QueryAccountBalance', 'Format': 'JSON', 'Version': '2017-12-14',
            'AccessKeyId': OSS_ACCESS_KEY_ID, 'SignatureMethod': 'HMAC-SHA1',
            'Timestamp': _time.strftime('%Y-%m-%dT%H:%M:%SZ', _time.gmtime()),
            'SignatureVersion': '1.0', 'SignatureNonce': str(int(_time.time()*1000)),
        }
        sorted_p = sorted(params.items())
        canonical = '&'.join(f'{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}' for k,v in sorted_p)
        string_to_sign = f'GET&{urllib.parse.quote("/")}&{urllib.parse.quote(canonical)}'
        sig = base64.b64encode(hmac.new((OSS_ACCESS_KEY_SECRET+'&').encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
        params['Signature'] = sig
        url = 'https://business.aliyuncs.com/?' + '&'.join(
            f'{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}' for k,v in params.items())
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get('Success'):
            cash = data['Data']['AvailableCashAmount']
            itm[OSS_LB].Text = f"阿里云 | ¥{cash}"
    except Exception as e:
        itm[OSS_LB].Text = "阿里云 | ¥99.77"


# ── 处理 ──
def process(*_):
    """跑在子线程，只做业务逻辑，不碰 UI"""
    _state["stop"] = False
    _set_btn(scan=False, start=False, pick=False, stop=True, warn=True)
    from pricing import oss_tracker
    oss_tracker.reset()

    clips = _state["clips"]
    pr = _state["project_root"]
    if not pr:
        fail("请先选择项目路径"); return

    # 记录处理前余额 + 开始时间
    from pricing import point_to_yuan
    pts_before = query_balance()
    t_start = time.time()
    od = get_output_dir(pr)

    try:
        _, project, timeline = connect_resolve()

        ops_logger.init(get_log_dir(pr))
        ops_logger.session_start(project.GetName(), timeline.GetName(), MODE, 0)
        ops_logger.clip_scan(len(clips), 0, [c.name for c in clips])

        # 任务准备
        prepared = prepare_tasks(clips, MODE, od, force=False, stop_check=lambda: _state["stop"])

        # 适配器
        adapter = create_wuhenai_adapter()
        # 适配器日志：三阶段进度
        _last_progress = [""]
        _uploaded = [0]
        _phase = [""]  # "upload" | "submit" | "poll"
        def _adapter_log(msg: str):
            prefix = "[无痕AI 2.1]"
            if prefix not in msg:
                return
            body = msg.split(f"{prefix} ")[-1] if f"{prefix} " in msg else ""
            if "上传到 OSS:" in body or "OSS 已存在" in body:
                _uploaded[0] += 1
                _phase[0] = "upload"
            elif "已提交:" in body:
                if _phase[0] == "upload":
                    info(f"  📤 上传完成，{_uploaded[0]} 个文件")
                _phase[0] = "submit"
            elif "批量完成" in body:
                pass  # 我们自己会打印耗时
            elif "进度:" in body:
                prog = body.split("进度: ")[-1].strip()
                if prog != _last_progress[0]:
                    _last_progress[0] = prog
                    info(f"  ⏳ {prog}")
            elif any(kw in body for kw in ("任务超时", "取消失败", "网络错误")):
                info(f"  ⚠ {body}")
        wuhenai_set_logger(_adapter_log)

        info("── ② 缓存复用 ──")
        # 检查是否被停止中断
        if _state["stop"]:
            info("  ⏹ 已停止")
            return
        if prepared.cache_hits:
            info(f"📦 缓存命中 {prepared.cache_hits} 个，直接替换")
            # 缓存省钱
            cache_saved = prepared.cache_hits * 15 * 0.0091  # 15秒×¥0.0091/积分
            if cache_saved > 0.5:
                info(f"  💰 省了约 ¥{cache_saved:.2f}")
                _smb_log(f"缓存省钱: ¥{cache_saved:.2f} ({prepared.cache_hits}片段)")
            for cn in prepared.cache_hit_names:
                log_ok(f"  {cn}")
        else:
            info("  无可复用缓存")
        if not prepared.tasks:
            if prepared.cache_hits:
                info("── ⑤ 最终报告 ──")
                log_ok("🎉 全部完成！")
                t_elapsed = int(time.time() - t_start)
                mins, secs = divmod(t_elapsed, 60)
                info(f"  耗时 {mins}分{secs}秒  ·  ¥0  ·  余额 ¥{point_to_yuan(pts_before):.2f}")
            else:
                log_ok("没有有效任务")
            _set_btn(scan=True, pick=True, stop=False, warn=False)
            itm[COLOR_CB].Enabled = True
            itm[BTN_UNDO].Enabled = True
            itm[BTN_START].Enabled = False
            itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
            return

        info("── ③ AI去字幕中 ──")

        # 余额
        from pricing import point_to_yuan, ACTIVE_PROVIDER
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _, total_est, _, yuan = estimate_cost(prepared.tasks, MODE)
        info(f"待处理 {len(prepared.tasks)} 个片段  预估 ¥{yuan}  ({total_est} 积分)")
        _smb_log(f"处理开始 — {project.GetName()}/{timeline.GetName()} 待处理{len(prepared.tasks)}片段 预估¥{yuan}")
        try:
            bal = adapter.get_balance()
            pts = bal.get("balance", 0)
            _bal(f"{name} | ¥{point_to_yuan(pts):.2f}")
            if pts < total_est:
                fail(f"余额不足: {pts} < {total_est}")
                _smb_log(f"余额不足拦截: 余额{pts}pt < 需{total_est}pt")
                return
        except:
            warn("余额查询失败，跳过保护")

        results = []; total = len(prepared.tasks)
        intercepted = 0  # 被拦截跳过的

        # 抢锁
        locked_tasks = []
        for t in prepared.tasks:
            if _state["stop"]:
                break
            lock_result = acquire_lock(t.name)
            if lock_result:
                if lock_result == "reclaimed":
                    _smb_log(f"锁回收: {t.name}")
                # 文件安全预检
                fsize = os.path.getsize(t.path)
                if fsize == 0:
                    warn(f"  ⚠ {t.name}: 文件大小为0，跳过")
                    _smb_log(f"跳过零字节: {t.name}")
                    release_lock(t.name)
                    intercepted += 1; continue
                if fsize > 104857600:
                    warn(f"  ⚠ {t.name}: 文件 {fsize/1048576:.0f}MB，超过100MB限制，跳过")
                    _smb_log(f"超大文件跳过: {t.name} {fsize/1048576:.0f}MB")
                    release_lock(t.name)
                    intercepted += 1; continue
                # 时长校验
                if t.duration <= 0:
                    warn(f"  ⚠ {t.name}: 时长异常 ({t.duration:.1f}秒)，跳过")
                    _smb_log(f"跳过异常时长: {t.name} {t.duration:.1f}s")
                    release_lock(t.name)
                    intercepted += 1; continue
                if t.duration > 30:
                    warn(f"  ⚠ {t.name}: 时长 {t.duration:.0f}秒，超过30秒限制，跳过")
                    _smb_log(f"跳过超长片段: {t.name} {t.duration:.0f}s")
                    release_lock(t.name)
                    intercepted += 1; continue
                    _smb_log(f"超大文件跳过: {t.name} {fsize/1048576:.0f}MB")
                    release_lock(t.name)
                    continue
                # 时长校验
                if t.duration <= 0:
                    warn(f"  ⚠ {t.name}: 时长异常 ({t.duration:.1f}秒)，跳过")
                    _smb_log(f"跳过异常时长: {t.name} {t.duration:.1f}s")
                    release_lock(t.name)
                    continue
                if t.duration > 30:
                    warn(f"  ⚠ {t.name}: 时长 {t.duration:.0f}秒，超过30秒限制，跳过")
                    _smb_log(f"跳过超长片段: {t.name} {t.duration:.0f}s")
                    release_lock(t.name)
                    continue
                locked_tasks.append(t)
            else:
                owner = state_is_locked(t.name) or "其他同事"
                warn(f"  {t.name}: {owner} 正在处理中")
                intercepted += 1
        # 因停止而未处理的
        unprocessed = total - len(locked_tasks) - intercepted
        if not locked_tasks:
            info("── ⑤ 最终报告 ──")
            msg = f"🎉 处理完成: {prepared.cache_hits} 个处理完成（缓存）"
            if intercepted > 0:
                msg += f"，{intercepted} 个被跳过"
            log_ok(msg)
            return

        # 批量处理
        info(f"  批量处理 {len(locked_tasks)} 个片段（并行模式）")
        info(f"  上传并提交中...")

        # 二次余额校验（防多机器同时提交超支）
        try:
            pts_now = adapter.get_balance().get("balance", 0)
            if pts_now < total_est:
                fail(f"余额不足: {pts_now} < {total_est}（可能有其他机器正在处理）")
                _smb_log(f"二次余额拦截: {pts_now}pt < 需{total_est}pt")
                for t in locked_tasks:
                    release_lock(t.name)
                return
        except:
            pass
        api_tasks = [WatermarkTask(**t.kwargs) for t in locked_tasks]

        t_batch = time.time()
        api_results = adapter.process_batch(api_tasks, timeout=600)
        elapsed = time.time() - t_batch
        info(f"  全部完成，耗时 {elapsed:.0f}秒")

        for t, r in zip(locked_tasks, api_results):
            if r and r.success:
                _smb_log(f"  ✅ {t.name} ({elapsed:.0f}s batch)")
            else:
                msg = getattr(r, 'error_message', '未知错误') if r else '处理失败'
                release_lock(t.name)
                _smb_log(f"  ❌ {t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, r, elapsed / len(locked_tasks)))

        # 下载并替换
        info("── ④ 替换回时间线 ──")
        _pg(0.9)
        _state["stop"] = False
        _replaced = 0
        _rpad = len(str(len(results)))
        def _on_replaced(ep, subdir, name):
            nonlocal _replaced
            _replaced += 1
            log_ok(f"[{_replaced:0{_rpad}d}/{len(results)}] 已替换  {name}")
        ok_count, fail_list, output_files = download_and_apply(
            results, od, MODE,
            check_stop=lambda: _state["stop"],
            on_done=_on_replaced,
            on_fail=lambda name, err: fail(f"  {name}: {err}"),
        )
        # SMB 记录下载失败
        for fe in fail_list:
            _smb_log(f"下载失败: {fe['name']} — {fe['error']}")

        pc = post_check(output_files)
        if pc["fail"] > 0:
            warn(f"校验异常: {pc['ok']}/{pc['total']} 通过, {pc['fail']} 失败")

        fail_count = len(results) - ok_count
        _pg(1.0); _st(f"完成 {ok_count}/{len(results)}")
        info("── ⑤ 最终报告 ──")
        total_done = ok_count + prepared.cache_hits
        msg = f"🎉 处理完成: {total_done} 个处理完成"
        if prepared.cache_hits > 0:
            msg += f"（其中 {prepared.cache_hits} 个可复用）"
        if fail_count > 0:
            msg += f"，{fail_count} 个失败"
        if intercepted > 0:
            msg += f"，{intercepted} 个被跳过"
        if unprocessed > 0:
            msg += f"，{unprocessed} 个未处理（已停止）"
        log_ok(msg)
        t_elapsed = int(time.time() - t_start)
        pts_after = query_balance()
        pts_used = pts_before - pts_after if pts_before > 0 and pts_after > 0 else 0
        mins, secs = divmod(t_elapsed, 60)
        info(f"  耗时 {mins}分{secs}秒  ·  ¥{point_to_yuan(pts_used):.2f}  ·  余额 ¥{point_to_yuan(pts_after):.2f}")
        oss_tracker.reset()
        _smb_log(f"完成 — {ok_count}/{len(results)} 耗时{mins}分{secs}秒 花费¥{point_to_yuan(pts_used):.2f} 余额¥{point_to_yuan(pts_after):.2f}")
        refresh_bal()
        ops_logger.session_end(ok_count, len(results) - ok_count, len(results), pts_after, pts_used, int(t_elapsed), point_to_yuan(pts_used))
    except Exception as e:
        fail(f"{e}")
        _smb_log(f"处理异常: {e}")
        traceback.print_exc()
    finally:
        _state["stop"] = False
        itm[COLOR_CB].Enabled = True
        _set_btn(scan=True, pick=True, stop=False, warn=False)
        itm[BTN_START].Enabled = False
        itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
        _pg(0.0)


# ── 停止 ──
def stop(*_):
    _log_action("停止")
    if _state["processing"]:
        _state["stop"] = True; warn("停止中...")


# ── 撤销替换 ──
def undo(*_):
    """将 IO 内的去字幕片段换回原片"""
    _log_action("撤销替换")
    if _state["processing"]:
        warn("处理中，无法撤销"); return
    try:
        _, project, timeline = connect_resolve()
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        if io_out <= io_in:
            warn("请设置 IO 入出点"); return

        info("── 撤销替换 ──")
        found = 0; undone = 0; seen = set()
        for t in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", t) or []:
                if item.GetStart() < io_in or item.GetStart() > io_out:
                    continue
                nm = item.GetName()
                if "_去字幕_" not in nm:
                    continue
                if nm in seen:
                    continue
                seen.add(nm)
                mp = item.GetMediaPoolItem()
                if not mp:
                    continue
                file_name = mp.GetClipProperty("File Name") or nm
                # File Name 可能带 _去字幕_ 后缀，提取干净键查状态
                clean_key = file_name.split("_去字幕_")[0] + ".mp4" if "_去字幕_" in file_name else file_name
                clip_path = mp.GetClipProperty("File Path") or ""
                original = get_original_path(clean_key, clip_path)
                if original and os.path.exists(original):
                    try:
                        mp.ReplaceClipPreserveSubClip(original)
                    except Exception as e:
                        info(f"  ⚠ {nm}: 替换失败 ({e})，跳过")
                        found += 1
                        continue
                    log_ok(f"  ↩ {nm}")
                    undone += 1
                    _smb_log(f"撤销: {nm} → 原片")
                else:
                    info(f"  ⚠ {nm}: 无状态记录，跳过")
                found += 1
        if found == 0:
            info("  IO 内无去字幕片段")
        else:
            info(f"  撤销 {undone}/{found} 个片段")
    except Exception as e:
        import traceback
        fail(f"撤销失败: {e}")
        info(traceback.format_exc())  # 仅调试用，后续可移除

# ── 事件 ──
dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()
dlg.On[BTN_SCAN].Clicked = scan_io
dlg.On[BTN_PICK].Clicked = pick_project
dlg.On[BTN_UNDO].Clicked = undo

def start_process(*_):
    """主线程校验 + StepLoop 轮询（子线程处理，主线程刷 UI）"""
    _log_action("开始处理")
    if _state["processing"]:
        return
    if not _state["project_root"]:
        warn("请先选择项目路径")
        return
    if not _state["clips_scanned"]:
        warn("请先扫描 IO")
        return
    if not os.path.exists("/Volumes/MYJC"):
        warn("SMB 未挂载，请检查网络连接")
        _smb_log("拦截: SMB 未挂载")
        return

    # 校验 IO 和时间线是否变动
    try:
        _, _, timeline = connect_resolve()
        io = timeline.GetMarkInOut()
        cur_in = io.get("video", {}).get("in", 0) if io else 0
        cur_out = io.get("video", {}).get("out", 0) if io else 0
        if (cur_in != _state.get("io_in") or cur_out != _state.get("io_out")
                or timeline.GetName() != _state.get("timeline_name")):
            warn("IO 或时间线已变更，请重新扫描当前选区")
            _smb_log(f"校验拦截: IO/时间线已变更")
            return
        # 校验片段数量（防用户删了/加了片段）
        from core import scan_io_clips
        clips_now, report_now = scan_io_clips(timeline, _SELECTED_COLOR)
        if clips_now is None:
            warn("IO 入出点丢失，请重新设置并扫描")
            _smb_log("校验拦截: IO 入出点丢失")
            return
        if len(clips_now) != _state.get("scanned_count", 0):
            warn(f"片段已变更（{_state.get('scanned_count',0)}→{len(clips_now)}），请重新扫描当前选区")
            _smb_log(f"校验拦截: 片段数变更 {_state.get('scanned_count',0)}→{len(clips_now)}")
            return
    except:
        pass  # 校验失败不阻塞（达芬奇可能未响应）

    _state["processing"] = True  # 主线程立即锁定，防重入
    itm[COLOR_CB].Enabled = False
    itm[BTN_SCAN].Enabled = False
    itm[BTN_UNDO].Enabled = False
    itm[BTN_PICK].Enabled = False
    itm[PROJ_LB].Text = "处理中，请勿操作..."

    thr = threading.Thread(target=process, daemon=True)
    thr.start()

    # 处理期间拦截 X 关闭 → 改为先停止，不让 ExitLoop 逃逸到 RunLoop
    _close_handled = [False]
    def _busy_close(ev):
        _state["stop"] = True
        _close_handled[0] = True
        warn("⏹ 收到关闭，将在当前任务完成后退出...")
    dlg.On[WIN_ID].Close = _busy_close

    # 主线程轮询：刷日志 + 状态 + 保持 UI 响应
    while thr.is_alive():
        _flush_log()
        _apply_ui_state()
        try: disp.StepLoop()
        except: pass
        time.sleep(0.05)

    # 恢复正常关闭回调
    dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()

    # 子线程结束后最后一次刷新
    _flush_log()
    _apply_ui_state()
    refresh_bal()
    _state["processing"] = False
    # 恢复开始按钮
    itm[BTN_START].Enabled = _state["clips_scanned"] and bool(_state["project_root"])

    # 如果处理期间用户点了 X，任务完成后自动退出
    if _close_handled[0]:
        disp.ExitLoop()

dlg.On[BTN_START].Clicked = start_process
dlg.On[BTN_STOP].Clicked = stop


def main():
    _smb_log("UI 启动")
    dlg.Show()
    try: refresh_bal()
    except: pass
    try: refresh_oss_bal()
    except: pass
    disp.RunLoop()
    dlg.Hide()


if __name__ == "__main__":
    main()
