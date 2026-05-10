# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 外部进程版
绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import math
import traceback
import queue

os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

# shared/ 模块路径（放在产品目录之前，确保 shared 模块优先）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))

from fusionscript_loader import bmd
fu = bmd.scriptapp("Fusion")
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)
from config import (
    DEBUG, get_output_dir, get_log_dir, __version__, __channel__, version_string,
    SMB_SCRIPTS, SMB_MOUNT, DEV_LOG_DIR, SMB_LOG_DIR, PRODUCT_NAME, BRAND_NAME,
)
from subtitle_state import init as state_init, is_locked as state_is_locked, acquire_lock, release_lock, get_original_path
import ledger
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    estimate_cost, query_balance, post_check, CLIP_COLOR as _CLIP_COLOR,
    download_and_apply,
)
from adapters import SubtitleTask
from logger import UILogger, set_logger, info, warn, fail, ok as log_ok

WIN_ID = "com.myjc.ai_subtitle_ui"
MODE = "pro_box"  # 固定：正式出片，后续不切模式

_state = {"processing": False, "stop": False, "project_root": "", "clips": [], "clips_scanned": False}

# ── 控件ID ──
BAL_LB = "bal_lb"
OSS_LB = "oss_lb"
PROJ_LB = "proj_lb"
PATH_LB = "path_lb"
BTN_SCAN, BTN_START, BTN_STOP = "btn_scan", "btn_start", "btn_stop"
BTN_PICK = "btn_pick"
BTN_CONFIRM = "btn_confirm"
BTN_UNDO = "btn_undo"
COLOR_CB = "color_cb"
LOG_LB, ST_LB = "log_lb", "st_lb"
PG_BAR = "pg_bar"

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
            # Row 1: 项目路径 + 余额（FixedSize 硬锁，防溢出）
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Button({"ID": BTN_CONFIRM, "Text": "✓ 确认此路径", "StyleSheet": BTN_PRIMARY, "Weight": 0}),
                ui.Button({"ID": BTN_PICK, "Text": "选择项目路径", "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Label({"ID": PATH_LB, "Text": "未指定项目路径",
                          "StyleSheet": "color:rgb(180,180,180);font-size:11px", "Weight": 1}),
                ui.VGroup({"Spacing": 2, "Weight": 0}, [
                    ui.Label({"ID": BAL_LB,                                 "Text": "<div align='right'>查询中...</div>", "FixedSize": [170, 16],
                              "StyleSheet": "color:rgb(220,220,220);font-size:11px"}),
                    ui.Label({"ID": OSS_LB, "Text": "<div align='right'>查询中...</div>", "FixedSize": [170, 16],
                              "StyleSheet": "color:rgb(200,200,200);font-size:11px"}),
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

        # 进度条（简单 Label，处理时动态 Resize）
        ui.VGroup({"ID": "pg_group", "Spacing": 2, "Weight": 0}, [
            ui.Label({"ID": ST_LB, "Text": "",
                      "StyleSheet": "color:rgb(180,180,180);font-size:11px;min-height:16px"}),
            ui.Label({"ID": PG_BAR, "Text": "",
                      "StyleSheet": "min-height:8px;max-height:8px;background-color:rgb(102,221,39);border-radius:3px",
                      "MinimumSize": [0, 8]}),
        ]),

        # 日志区（唯一可缩放）
        ui.TextEdit({"ID": LOG_LB, "Text": "",
                     "StyleSheet": "color:rgb(200,200,200);background-color:rgb(30,30,30);"
                                   "border:1px solid rgb(50,50,50);border-radius:4px;"
                                   "padding:6px;min-height:100px",
                     "ReadOnly": True, "Weight": 1}),

        # 下半区：状态信息
        ui.VGroup({"ID": "bottom_bar", "Spacing": 2, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Label({"ID": PROJ_LB, "Text": "① 请先选择项目路径",
                          "StyleSheet": "color:rgb(200,200,200);font-size:13px", "Weight": 2}),
                ui.Label({"ID": "warn_lb", "Text": "⚠ 请勿切换至其他项目",
                          "StyleSheet": "color:rgb(255,80,80);font-size:12px;font-weight:bold", "Weight": 0}),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"{BRAND_NAME} | v{version_string()}",
                          "StyleSheet": "color:rgb(100,100,100);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": f"{PRODUCT_NAME}",
    "ID": WIN_ID,
    "Geometry": [800, 100, 880, 560],  # Geometry: [x, y, w, h]
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# 初始状态 — 未选项目路径前，筛选和扫描不可用
itm[BTN_CONFIRM].Visible = False
itm[COLOR_CB].Enabled = False
itm[BTN_SCAN].Enabled = False
itm[BTN_START].Enabled = False
itm[BTN_STOP].Enabled = False
itm[BTN_UNDO].Enabled = False
itm["warn_lb"].Visible = False
itm[PG_BAR].Visible = False  # 处理时由 _pg() 控制显示
itm[ST_LB].Text = ""

# 强制刷新布局，防止初始化时控件溢出窗口
dlg.RecalcLayout()

# 颜色下拉框
for ename, cname, _ in _CLIP_COLORS:
    itm[COLOR_CB].AddItem(cname)
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
# 日志路径（常量来自 config.py）
# dev 版写本地 dev 目录；生产版写 ~/.workbuddy/logs/（持久化，非 /tmp）
_UI_LOG_FILE = os.path.join(DEV_LOG_DIR, "ui.log") if __channel__ == "dev" else \
               os.path.join(os.path.expanduser("~/.workbuddy/logs"), "ui.log")

# 确保日志目录存在（生产版 ~/.workbuddy/logs/ 可能未创建）
os.makedirs(os.path.dirname(_UI_LOG_FILE), exist_ok=True)

# dev 版写本地固定目录，避免混入生产 SMB 目录
_SMB_LOG_DIR = DEV_LOG_DIR if __channel__ == "dev" else SMB_LOG_DIR
_SMB_LOG = os.path.join(_SMB_LOG_DIR, f"{socket.gethostname()}.log")

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
                try:
                    te.MoveCursor("End", "MoveAnchor")
                    te.EnsureCursorVisible()
                except Exception:  # 日志截断是非关键路径，失败静默
                    pass
            else:
                te.Append(msg + "\n")
        except Exception:  # _smb_log 轮转失败不阻塞 UI
            import sys; print(f"[ui_write] UI 刷新失败", file=sys.stderr)
        # 追加后自动滚到底部
        try:
            te.MoveCursor("End", "MoveAnchor")
            te.EnsureCursorVisible()
        except Exception:  # _smb_log 写入失败不阻塞 UI
            pass
    else:
        _log_queue.put(msg)
    # 文件持久化（本地 + SMB 双写，方便查同事日志）
    try:
        with open(_UI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:  # 日志追加失败不阻塞 UI
        import sys; print(f"[ui_write] 本地日志写入失败", file=sys.stderr)

def _ui_write(msg: str):
    _ui_write_direct(msg)

# ── SMB 关键事件日志：一人一文件，方便远程 debug ──
# _SMB_LOG 已在文件顶部定义，始终指向 SMB
def _smb_log(msg: str):
    """只记关键事件到 SMB，不记适配器噪音"""
    try:
        ts = time.strftime("%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(_SMB_LOG), exist_ok=True)
        with open(_SMB_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # SMB 写入失败不阻塞 UI
        import sys
        print(f"[_smb_log FAIL] {msg}", file=sys.stderr)

def _check_smb():
    """全局 SMB 健康检查 + 自动重挂。返回 True=在线"""
    if os.path.exists(SMB_MOUNT):
        return True
    warn("⚠ SMB 已断开，尝试重挂...")
    from macos_utils import mount_smb
    for _ in range(3):
        try:
            if mount_smb():
                info("✅ SMB 已恢复")
                _smb_log("SMB 重挂成功")
                return True
        except Exception:  # SMB 状态检查失败不阻塞 UI
            pass
    fail("❌ SMB 重挂失败，插件不可用")
    _smb_log("SMB 重挂失败 3 次")
    return False

def _flush_log():
    """主线程调用：批量刷日志到 TextEdit"""
    try:
        te = itm[LOG_LB]
        while not _log_queue.empty():
            msg = _log_queue.get_nowait()
            te.Append(msg + "\n")
    except Exception:  # SMB 初始化失败不阻塞 UI
        # UI 未就绪时静默（初始化时序），真实错误由 _smb_log 覆盖
        pass

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
_ui_pending = {"status": "", "balance": "", "progress": -1.0, "btn_scan": None, "btn_start": None, "btn_pick": None, "btn_stop": None, "warn": None}

# ── 时间估算常量（实测数据 2026-05-08）──
# 公式：sum(片段秒数)×2.3 + 60 秒（含上传+API+下载固定开销）
# 单片段网络波动大（±30%），批量 3+ 片段偏差稳定在 ±10% 内
import time as _time_module
# 以下全局变量由子线程写入、主线程轮询读取。CPython GIL 保证单值赋值原子性，
# 且使用模式为"一写多读"无竞态条件，无需额外锁。
_t_start = 0.0          # 处理开始时间
_task_count = 0         # 待处理总数
_t_estimated = 0.0      # 预估总秒数（扫描时计算）
_t_last_update = 0.0    # 上次 UI 更新

_phase_text = ""         # 当前阶段描述（处理线程设，轮询循环读）

def _st(t):
    """处理线程调用：仅记录阶段文本，不写 UI（避免与倒计时冲突）"""
    global _phase_text
    _phase_text = t

def _update_countdown():
    """每轮轮询调用：唯一写 PROJ_LB 的函数，整合阶段 + 倒计时 + 进度条"""
    try:
        if _t_start <= 0 or _t_estimated <= 0:
            return
        now = _time_module.time()
        elapsed = now - _t_start
        remaining = max(0, _t_estimated - elapsed)
        ratio = getattr(_st, '_last_ratio', 0)

        mins, secs = divmod(int(remaining), 60)
        if remaining > 5:
            time_str = f"还剩 {secs}秒" if mins == 0 else f"还剩 {mins}分{secs}秒"
        elif remaining > 0:
            time_str = "即将完成..."
        else:
            time_str = _phase_text or "处理中..."  # 超时了还在跑，不显示 0 秒

        phase = _phase_text or "AI 处理中..."
        # 百分比：只在 adapter 报了真实进度时显示（批量模式），不造假的
        pct_str = f"  {int(ratio*100)}%" if ratio > 0.05 else ""
        itm[PROJ_LB].Text = f"⏳ {phase}{pct_str}  ·  {time_str}"

        # 进度条：时间驱动也行，比没有好
        est_ratio = min(0.95, elapsed / _t_estimated)
        actual = max(ratio, est_ratio)
        if actual > 0:
            _pg(actual)
    except Exception as e:
        _smb_log(f"_update_countdown 异常: {e}")

_pg_last_milestone = 0  # 上次记录的进度里程碑

# 进度条容器最大宽度（动态获取，非硬编码）
_PG_MAX_W_FALLBACK = 800  # 仅当 GetGeometry 失败时兜底

def _pg(r):
    """更新进度条（0.0=开始, 1.0=完成），里程碑时写 SMB 日志"""
    global _pg_last_milestone
    ratio = max(0.0, min(r, 1.0))
    for m in (0.10, 0.25, 0.50, 0.75, 0.90, 1.0):
        if ratio >= m > _pg_last_milestone:
            _pg_last_milestone = m
            elapsed = int(_time_module.time() - _t_start) if _t_start > 0 else 0
            _smb_log(f"进度 {int(m*100)}%  |  已过 {elapsed}秒  |  预估 {_t_estimated:.0f}秒")
            break
    if ratio == 0:
        _pg_last_milestone = 0
    try:
        _st._last_ratio = ratio
        # 100% 时：先让父容器算出真实宽度，再据此填满进度条
        if ratio >= 1.0:
            try: itm["pg_group"].RecalcLayout()
            except Exception: pass
            try: itm[PG_BAR].RecalcLayout()
            except Exception: pass
        # 动态获取容器宽度（GetGeometry 返回 dict {1:x,2:y,3:w,4:h}，不是 list）
        try:
            pg_geo = itm["pg_group"].GetGeometry()
            max_w = pg_geo[3] if pg_geo.get(3, 0) > 0 else _PG_MAX_W_FALLBACK
        except Exception:  # 余额查询网络失败不阻塞 UI 更新
            max_w = _PG_MAX_W_FALLBACK
        bar_w = max(2, int(max_w * ratio))
        itm[PG_BAR].Resize([bar_w, 8])
        itm[PG_BAR].Visible = ratio > 0.005
        try: itm[PG_BAR].Update()
        except Exception:  # 余额解析失败不阻塞 UI
            #达芬奇 UIManager 控件未完全渲染时 Update 可能失败
            pass
    except Exception:  # 状态栏更新失败不阻塞 UI
        pass

def _log_file(msg: str):
    """写本地 + SMB 双日志（操作和状态，方便远程 debug）"""
    try:
        with open(_UI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:  # 进度条更新失败不阻塞 UI
        import sys; print(f"[_log_file] 本地日志写入失败", file=sys.stderr)
    try:
        with open(_SMB_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:  # 按钮状态更新失败不阻塞 UI
        import sys; print(f"[_log_file] SMB日志写入失败", file=sys.stderr)

def _log_action(action: str):
    """记录用户操作到日志"""
    _log_file(f"[操作] {action}")
def _bal(t):
    try: itm[BAL_LB].Text = f"<div align='right'>{t}</div>"
    except Exception: _smb_log(f"[ui_widgets] BAL_LB 赋值失败")
    with _ui_lock: _ui_pending["balance"] = f"<div align='right'>{t}</div>"  # HTML 包装也在挂起数据里

def _set_btn(scan=None, start=None, pick=None, stop=None, warn=None):
    """设置按钮状态（主线程直写 + 子线程挂起）"""
    try:
        if scan is not None: itm[BTN_SCAN].Enabled = scan
        if start is not None: itm[BTN_START].Enabled = start
        if pick is not None: itm[BTN_PICK].Enabled = pick
        if stop is not None: itm[BTN_STOP].Enabled = stop
        if warn is not None: itm["warn_lb"].Visible = warn
    except Exception: _smb_log("[ui_widgets] _set_btn 失败")
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
        if pg >= 0: _pg(pg)
    except Exception: _smb_log("[ui_widgets] _apply_ui_state 失败")

def _set_proj(path):
    try:
        label = path if path else "未指定项目路径"
        # 去掉固定前缀 /Volumes/MYJC/
        if label.startswith("/Volumes/MYJC/"):
            label = label[14:]
        # 太长从右边截断
        if len(label) > 65:
            label = label[:62] + "..."
        itm[PATH_LB].Text = label
    except Exception: _smb_log("[ui_widgets] _set_proj 失败")

def _guess_project_root():
    """从媒体池 01_素材 片段路径推测项目根目录（众数投票）。零磁盘 IO，纯字符串。"""
    try:
        import fusionscript_loader
        r = fusionscript_loader.bmd.scriptapp("Resolve")
        if not r:
            return None
        proj = r.GetProjectManager().GetCurrentProject()
        if not proj:
            return None
        mp = proj.GetMediaPool()
        root = mp.GetRootFolder()
        material = None
        for sub in root.GetSubFolderList():
            if sub.GetName() == "01_素材":
                material = sub
                break
        if not material:
            return None

        from collections import Counter
        import re
        counter = Counter()
        # 匹配路径中任意 /数字_名称/ 的文件夹
        _ROOT_PATTERN = re.compile(r'/(\d{2}_[^/]*)/')

        def _extract_root(file_path):
            matches = list(_ROOT_PATTERN.finditer(file_path))
            if not matches:
                return None
            return file_path[:matches[-1].start()]

        def _collect(folder, depth=0):
            if depth > 8 or counter.total() >= 200:
                return
            for c in (folder.GetClipList() or []):
                p = c.GetClipProperty("File Path")
                if p:
                    rp = _extract_root(p)
                    if rp:
                        counter[rp] += 1
            for sub in (folder.GetSubFolderList() or []):
                _collect(sub, depth + 1)

        _collect(material)
        if not counter:
            return None
        proj_root, _count = counter.most_common(1)[0]
        return proj_root if os.path.isdir(proj_root) else None
    except Exception:  # 项目路径猜测失败不阻塞 UI 初始化
        return None


def auto_detect_project():
    """插件启动时推测项目根目录，显示建议等待用户确认。推测成功返回 True，失败返回 False。"""
    global _suggested_path
    if not _check_smb():
        return False
    try:
        path = _guess_project_root()
        if not path:
            return False
        _suggested_path = path
        _set_proj(path)  # 显示路径，但尚未确认
        itm[BTN_CONFIRM].Visible = True
        itm[BTN_PICK].Text = "手动选择"
        itm[PROJ_LB].Text = "① 请确认或手动选择项目路径"
        return True
    except Exception:  # 路径自动检测失败不阻塞 UI
        return False

_suggested_path = ""  # 推测但尚未确认的路径


def confirm_project(*_):
    """用户点击确认按钮，正式接受推测的路径"""
    global _suggested_path
    path = _suggested_path
    if not path or not os.path.isdir(path):
        warn("路径无效，请手动选择")
        return
    _log_action("确认项目路径")
    _state["project_root"] = path
    state_init(path)
    ledger.init(path)
    itm[COLOR_CB].Enabled = True
    itm[BTN_SCAN].Enabled = True
    itm[BTN_UNDO].Enabled = True
    itm[BTN_START].Enabled = False
    itm[BTN_CONFIRM].Enabled = False
    itm[BTN_CONFIRM].Text = "已确认"
    itm[BTN_PICK].Text = "更改路径"
    itm[PATH_LB].StyleSheet = "color:rgb(102,221,39);font-size:11px"  # 绿色确认态
    itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
    _suggested_path = ""

def pick_project(*_):
    """打开 macOS 原生文件夹选择器，默认位置推测为当前媒体池项目目录"""
    if not _check_smb():
        return
    _log_action("选择项目路径")
    try:
        default_dir = _guess_project_root()
        prompt = "选择项目根目录（包含04_素材的文件夹）"
        from macos_utils import pick_folder
        path = pick_folder(prompt, default_dir)
        if path:
            _state["project_root"] = path
            _set_proj(path)
            state_init(path)
            ledger.init(path)
            itm[BTN_CONFIRM].Enabled = False
            itm[BTN_CONFIRM].Text = "已确认"
            itm[BTN_PICK].Text = "更改路径"
            itm[PATH_LB].StyleSheet = "color:rgb(102,221,39);font-size:11px"
            itm[COLOR_CB].Enabled = True
            itm[BTN_SCAN].Enabled = True
            itm[BTN_UNDO].Enabled = True
            itm[BTN_START].Enabled = _state["clips_scanned"] and bool(_state["project_root"])
            itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区" if not _state["clips_scanned"] else "③ 请点击开始处理"
            if _state["clips_scanned"]:
                from ui_pipeline import _refresh_scan_display
                _refresh_scan_display()
        elif path:
            warn("所选路径不存在")
    except Exception as e:
        if "User canceled" not in str(e):
            fail(f"选择失败: {e}")


