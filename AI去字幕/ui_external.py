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
from watermark_state import init as state_init, is_locked as state_is_locked
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    estimate_cost, query_balance, post_check, CLIP_COLOR as _CLIP_COLOR,
    create_wuhenai_adapter, process_single_clip, download_and_apply,
)
from adapters.wuhenai_v2 import wuhenai_set_logger
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
BTN_SCAN, BTN_START, BTN_STOP = "btn_scan", "btn_start", "btn_stop"
BTN_PICK = "btn_pick"
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
LABEL_DIM = "color:rgb(170,170,170);font-size:12px"
LABEL_VAL = "color:rgb(220,220,220);font-size:12px"

# ── 窗口 ──
window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # 上半区：固定高度
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Button({"ID": BTN_PICK, "Text": "选择项目路径", "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": BAL_LB, "Text": "查询中...",
                              "StyleSheet": "color:rgb(220,220,220);font-size:11px;qproperty-alignment:AlignRight"}),
                    ui.Label({"ID": OSS_LB, "Text": "查询中...",
                              "StyleSheet": "color:rgb(200,200,200);font-size:11px;qproperty-alignment:AlignRight"}),
                ]),
            ]),
            ui.Label({"ID": "warn_lb", "Text": "⚠ 请勿删除待处理片段或切换项目",
                      "StyleSheet": "color:rgb(255,80,80);font-size:12px;font-weight:bold"}),
            ui.Label({"ID": PROJ_LB, "Text": "请先选择项目路径",
                      "StyleSheet": "color:rgb(180,180,180);font-size:11px"}),
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "筛选条件", "StyleSheet": "color:rgb(150,150,150);font-size:12px", "Weight": 0}),
                ui.Label({"ID": "color_dot", "Text": "●",
                          "StyleSheet": "color:rgb(235,110,0);font-size:14px;"
                          "qproperty-alignment:AlignCenter", "Weight": 0}),
                ui.ComboBox({"ID": COLOR_CB, "Weight": 0}),
                ui.Button({"ID": BTN_SCAN, "Text": "扫描当前选区", "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Button({"ID": BTN_START, "Text": "开始处理", "StyleSheet": BTN_PRIMARY, "Weight": 0}),
                ui.Button({"ID": BTN_STOP, "Text": "停止", "StyleSheet": BTN_STYLE, "Weight": 0}),
            ]),
        ]),

        # 日志区（唯一可缩放）
        ui.TextEdit({"ID": LOG_LB, "Text": "",
                     "StyleSheet": "color:rgb(200,200,200);background-color:rgb(30,30,30);"
                                   "border:1px solid rgb(50,50,50);border-radius:4px;"
                                   "padding:6px;min-height:100px",
                     "TextInteractionFlags": 13, "Weight": 1}),

        # 下半区：固定高度
        ui.VGroup({"Spacing": 2, "Weight": 0}, [
            ui.Stack({"ID": "pg_set"}, [
                ui.Label({"ID": PG_BG, "StyleSheet": "max-height:3px;background-color:rgb(37,37,37)"}),
                ui.Label({"ID": PG_BAR, "StyleSheet": "max-height:3px;background-color:rgb(50,120,220)"}),
            ]),
            ui.HGroup({"Spacing": 0}, [
                ui.Label({"ID": ST_LB, "Text": "就绪 — 请设置 IO 入出点后点击扫描",
                          "StyleSheet": "color:rgb(150,150,150);font-size:11px", "Weight": 0}),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"达芬奇插件工坊 ✂️ | v{__version__}",
                          "StyleSheet": "color:rgb(120,120,120);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": f"AI 去字幕",
    "ID": WIN_ID,
    "Geometry": [800, 100, 480, 560],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# 初始状态
itm[PG_BAR].Visible = False
itm[BTN_START].Enabled = False
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
    """设置状态文本（主线程直写 + 文件记录）"""
    try: itm[ST_LB].Text = t
    except: pass
    with _ui_lock: _ui_pending["status"] = t
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
    try:
        itm[PG_BAR].Visible = r > 0
        if r > 0:
            bw = itm[PG_BG].GetGeometry() or [0,0,0,3]
            itm[PG_BAR].Resize([max(1, int(bw[3] * r)), 3])
    except: pass
    with _ui_lock: _ui_pending["progress"] = r
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
        if st: itm[ST_LB].Text = st
        if bal: itm[BAL_LB].Text = bal
        if pg > 0:
            itm[PG_BAR].Visible = True
            bw = itm[PG_BG].GetGeometry() or [0,0,0,3]
            itm[PG_BAR].Resize([max(1, int(bw[3] * pg)), 3])
        elif pg == 0:
            itm[PG_BAR].Visible = False
        if bs is not None: itm[BTN_SCAN].Enabled = bs
        if b1 is not None: itm[BTN_START].Enabled = b1
        if bp is not None: itm[BTN_PICK].Enabled = bp
        if b2 is not None: itm[BTN_STOP].Enabled = b2
        if wl is not None: itm["warn_lb"].Visible = wl
    except: pass

def _set_proj(path):
    try:
        label = path if path else "请选择项目文件夹"
        # 太长截断显示
        if len(label) > 60:
            label = "..." + label[-57:]
        itm[PROJ_LB].Text = label
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
            itm[BTN_START].Enabled = _state["clips_scanned"] and bool(_state["project_root"])
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

        info("── 扫描中 ──")

        # 获取 IO 范围
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0

        # 时间线帧率 → 帧号转分:秒
        fps_str = project.GetSetting("timelineFrameRate")
        fps = float(fps_str) if fps_str else 25.0

        # 逐片段显示 + 缓存检测
        from core import find_cached_output
        pr = _state["project_root"] or ""
        od = pr and get_output_dir(pr) or ""
        cache_hits = 0
        need_secs = 0
        for c in clips:
            # 帧 → 时控码 时:分:秒:帧
            f = c.start_frame
            total_sec = int(f / fps)
            h, m = divmod(total_sec, 3600)
            m2, s = divmod(m, 60)
            rem_f = int(f - total_sec * fps)
            pos_str = f"{h:02d}:{m2:02d}:{s:02d}:{rem_f:02d}"
            is_cached = od and find_cached_output(c.file_name, od)
            label = "缓存命中" if is_cached else "需处理"
            emoji = "🟢" if is_cached else "🟡"
            info(f"  {emoji} {c.name}	位置：{pos_str}	长度：{c.duration:.0f}秒	{label}")
            if is_cached:
                cache_hits += 1
            else:
                need_secs += c.duration

        # 总结
        from pricing import point_to_yuan
        need = len(clips) - cache_hits
        pts = max(1, int(need_secs))
        yuan = point_to_yuan(pts)
        avg = max(60, min(120, need_secs / max(1, need) * 3)) if need > 0 else 0
        total_time = int(need * avg / 60) if need > 0 else 0
        summary = f"当前选区内，共 {len(clips)} 个符合筛选条件的片段。"
        if cache_hits > 0:
            summary += f" 其中 {cache_hits} 个已有本地缓存  |  {need} 个待处理"
        info(summary)
        ops_logger.cost_estimate(pts, yuan, total_time, need, cache_hits)
        if need > 0:
            info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")

        _state["clips_scanned"] = True
        itm[BTN_START].Enabled = bool(_state["project_root"])
        _st(f"待处理: {report.valid} 个片段")
        _smb_log(f"扫描 — 项目: {project.GetName()} 时间线: {timeline.GetName()} IO={io_in}→{io_out} 内{report.valid}片段 需处理{need} 预估¥{yuan}")
        refresh_bal()
    except Exception as e:
        fail(f"扫描失败: {e}")
        _smb_log(f"扫描失败: {e}")
        _st("就绪")


# ── 余额 ──
def refresh_bal():
    pts = query_balance()
    if pts > 0:
        from pricing import point_to_yuan, ACTIVE_PROVIDER
        name = "去字幕" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
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
        prepared = prepare_tasks(clips, timeline, MODE, od, pr, force=False)

        # 适配器
        adapter = create_wuhenai_adapter()
        # 适配器日志：进度走状态栏，其余过滤
        def _adapter_log(msg: str):
            if "状态:" in msg:
                try:
                    pct = msg.split("进度:")[1].strip() if "进度:" in msg else ""
                    _st(f"处理中{pct}%" if pct else "排队中...")
                except: pass
            elif "任务已提交" in msg:
                _st(msg.split("] ")[-1] if "] " in msg else msg)
            elif any(kw in msg for kw in ("任务超时", "取消失败", "网络错误")):
                info(msg)
        wuhenai_set_logger(_adapter_log)

        info("── 缓存替换中 ──")
        if prepared.cache_hits:
            info(f"📦 缓存命中 {prepared.cache_hits} 个，直接替换")
            for cn in prepared.cache_hit_names:
                log_ok(f"  {cn}")
        if not prepared.tasks:
            log_ok("全部完成！" if prepared.cache_hits else "没有有效任务"); return

        info("── AI处理中 ──")

        # 余额
        from pricing import point_to_yuan, ACTIVE_PROVIDER
        name = "去字幕" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _, total_est, _, yuan = estimate_cost(prepared.tasks, MODE)
        info(f"待处理 {len(prepared.tasks)} 个片段  预估 ¥{yuan}  ({total_est} 积分)")
        _smb_log(f"处理开始 — {project.GetName()}/{timeline.GetName()} 待处理{len(prepared.tasks)}片段 预估¥{yuan}")
        try:
            bal = adapter.get_balance()
            pts = bal.get("balance", 0)
            _bal(f"{name} | ¥{point_to_yuan(pts):.2f}")
            if pts < total_est:
                fail(f"余额不足: {pts} < {total_est}"); return
        except:
            warn("余额查询失败，跳过保护")

        results = []; total = len(prepared.tasks)

        for idx, t in enumerate(prepared.tasks, 1):
            if _state["stop"]:
                warn("⏹ 已停止，不再处理剩余片段")
                break
            # 每处理前检查达芬奇是否还活着
            try:
                if not bmd.scriptapp('Resolve'):
                    fail("达芬奇已断开，停止处理")
                    break
            except:
                fail("达芬奇已断开，停止处理")
                break
            _st(f"{idx:02d}/{total} {t.name}"); _pg(idx/total)
            pad = len(str(total))
            info(f"[{idx:0{pad}d}/{total}] 处理中  {t.name}")
            result, elapsed = process_single_clip(t, adapter, MODE, cancel_check=lambda: _state["stop"])
            if result.success:
                _smb_log(f"  ✅ {t.name} ({elapsed:.0f}s)")
            else:
                msg = getattr(result, 'error_message', '未知错误')
                if msg == "被锁定":
                    owner = state_is_locked(t.name) or "其他同事"
                    warn(f"[{idx:02d}/{total}] {t.name}: {owner} 正在处理中")
                else:
                    fail(f"[{idx:02d}/{total}] {t.name}: {msg}")
                _smb_log(f"  ❌ {t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, result, elapsed))

        # 下载并替换
        info("── 替换回时间线 ──")
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

        pc = post_check(output_files)
        if pc["fail"] > 0:
            warn(f"校验异常: {pc['ok']}/{pc['total']} 通过, {pc['fail']} 失败")

        fail_count = len(results) - ok_count
        _pg(1.0); _st(f"完成 {ok_count}/{len(results)}")
        parts = []
        if ok_count > 0:
            parts.append(f"{ok_count} 个 AI 处理完成")
        if fail_count > 0:
            parts.append(f"{fail_count} 个失败")
        if prepared.cache_hits > 0:
            parts.append(f"{prepared.cache_hits} 个缓存替换")
        log_ok(f"处理完成: {'，'.join(parts)}")
        info("── 最终报告 ──")
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
        _set_btn(scan=True, pick=True, stop=False)
        _pg(0.0)


# ── 停止 ──
def stop(*_):
    _log_action("停止")
    if _state["processing"]:
        _state["stop"] = True; warn("停止中...")


# ── 事件 ──
dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()
dlg.On[BTN_SCAN].Clicked = scan_io
dlg.On[BTN_PICK].Clicked = pick_project

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

    _state["processing"] = True  # 主线程立即锁定，防重入

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
