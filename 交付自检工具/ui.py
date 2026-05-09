# -*- coding: utf-8 -*-
"""
交付自检工具 UI — 外部进程版

绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
使用 fusionscript_loader 连接 Resolve。
"""
import os
import socket
import sys
import time
import traceback

os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from fusionscript_loader import bmd
fu = bmd.scriptapp("Fusion")
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

from config import (
    __version__,
    DEFAULT_CLAMP_THRESHOLD,
    DEFAULT_SUBTITLE_TRACKS,
    DEFAULT_VIDEO_TRACKS,
    DEFAULT_AUDIO_TRACKS,
)
from check_core import (check_track_structure, check_subtitle_clamping, check_disabled_items,
                          check_black_frames, check_audio_mono, check_timeline_settings,
                          check_subtitle_glyph, check_subtitle_linebreak, check_subtitle_censor,
                          preload_timeline_items)

# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════
WIN_ID = "com.myjc.delivery_checker"

# 控件 ID
CHK_TRACK, CHK_SUB_DURATION, CHK_SUB_LINEBREAK, CHK_SUB_GLYPH = \
    "chk_track", "chk_sub_dur", "chk_sub_br", "chk_sub_glyph"
CHK_BLACK, CHK_BORDER, CHK_MONO, CHK_LOUDNESS, CHK_FRAGMENT, CHK_TIMELINE, CHK_COLOR = \
    "chk_black", "chk_border", "chk_mono", "chk_loudness", "chk_fragment", "chk_timeline", "chk_color"
CHK_CENSOR_CN, CHK_CENSOR_EN, CHK_CENSOR_NRTA, CHK_CENSOR_JUICY = "chk_censor_cn", "chk_censor_en", "chk_censor_nrta", "chk_censor_juicy"
CHK_BLACK_FRAME = CHK_BLACK  # 别名
LBL_SUB_VAL, LBL_VID_VAL, LBL_AUD_VAL = "lbl_sub", "lbl_vid", "lbl_aud"
EDIT_SUB, EDIT_VID, EDIT_AUD = "edit_sub", "edit_vid", "edit_aud"
BTN_EDIT_TRACK = "btn_edit_track"
BTN_SAVE_TRACK = "btn_save_track"
LBL_CLAMP_VAL = "lbl_clamp"
EDIT_CLAMP = "edit_clamp"
BTN_EDIT_CLAMP = "btn_edit_clamp"
BTN_SAVE_CLAMP = "btn_save_clamp"
BTN_START = "btn_start"
BTN_SEL_ALL = "btn_sel_all"
BTN_DESEL_ALL = "btn_desel_all"
TREE_RESULT = "tree_result"
ST_LB = "st_lb"
HINT_LB = "hint_lb"

# ── 结果列定义：加/删/挪/开关列只改这里 ──
#   enabled=False → 列暂时隐藏，不删定义
COLUMNS = [
    {"header": "状态", "width": 40,  "key": "icon",   "enabled": True},
    {"header": "轨道", "width": 50,  "key": "track",  "enabled": True},
    {"header": "位置", "width": 100, "key": "tc",     "enabled": True},
    {"header": "详情", "width": 280, "key": "msg",    "enabled": True},
    {"header": "原因", "width": 200, "key": "reason", "enabled": True},
]

# 当前启用的列（enabled=True）
_ENABLED_COLS = [c for c in COLUMNS if c.get("enabled", True)]

# ── 结果分组顺序（四大分组，控制 Tree 渲染层级）──
GROUP_ORDER = ["工程", "视频", "音频", "字幕"]


def _col_index(key):
    """根据 key 找在启用列中的索引（用于跳转等）"""
    for i, c in enumerate(_ENABLED_COLS):
        if c["key"] == key:
            return i
    return -1


def _setup_tree_header(tree):
    """根据启用的列设置树列表头"""
    hdr = tree.NewItem()
    for i, col in enumerate(_ENABLED_COLS):
        hdr.Text[i] = col["header"]
    tree.SetHeaderItem(hdr)
    for i, col in enumerate(_ENABLED_COLS):
        tree.ColumnWidth[i] = col["width"]


def _set_row(row, data):
    """根据启用的列 + data 字典填充一行"""
    for i, col in enumerate(_ENABLED_COLS):
        row.Text[i] = data.get(col["key"], "")


def _set_row_texts(row, *texts):
    """直接按列位置设文本（用于标题行等）"""
    for i, t in enumerate(texts):
        row.Text[i] = t


# ═══════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════
_CHECK_ROWS = 6
_BTN_HEIGHT = min(_CHECK_ROWS * 22 + (_CHECK_ROWS - 1) * 2 + 5 * 16, 120)
BTN_STYLE = (
    "QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
BTN_ICON = (
    "QPushButton{max-height:20px;max-width:24px;background-color:transparent;color:rgb(150,150,150);"
    "border:1px solid transparent;border-radius:3px;padding:0px}"
    "QPushButton:hover{background-color:rgb(60,60,60);color:rgb(220,220,220)}"
)
BTN_STYLE_SM = (
    "QPushButton{max-height:22px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:2px 8px;text-align:left}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
)
BTN_PRIMARY = (
    "QPushButton{max-height:28px;background-color:rgb(50,120,220);color:rgb(255,255,255);"
    "border:1px solid rgb(70,140,240);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(65,135,235)}"
    "QPushButton:pressed{background-color:rgb(40,100,200)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
BTN_DANGER = (
    "QPushButton{max-height:28px;background-color:rgb(200,50,50);color:rgb(255,255,255);"
    "border:1px solid rgb(220,70,70);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(220,65,65)}"
    "QPushButton:pressed{background-color:rgb(160,40,40)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
LABEL_DIM = "color:rgb(150,150,150);font-size:12px"
LABEL_GRAY = "color:rgb(120,120,120);font-size:12px"
LABEL_VAL = "color:rgb(200,200,200);font-size:12px"

# 编辑按钮（小图标）
BTN_ICON = (
    "QPushButton{max-height:20px;max-width:24px;background-color:transparent;color:rgb(150,150,150);"
    "border:1px solid transparent;border-radius:3px;padding:0px}"
    "QPushButton:hover{background-color:rgb(60,60,60);color:rgb(220,220,220)}"
)

# ═══════════════════════════════════════════
# 检查注册表（加新检查 = 这里加一行；换顺序 = 挪位置）
# ═══════════════════════════════════════════

def _run_track_check(timeline, fps):
    """轨道结构"""
    return check_track_structure(timeline, *_track_values)

def _run_sub_duration_check(timeline, fps):
    """字幕时长（过短 + 夹帧）"""
    return check_subtitle_clamping(timeline, _clamp_value, fps)

def _run_sub_glyph_check(timeline, fps):
    """字幕异体字"""
    return check_subtitle_glyph(timeline, fps)

def _run_sub_linebreak_check(timeline, fps):
    """字幕换行（CPL + 硬换行）"""
    return check_subtitle_linebreak(timeline, fps)

def _run_fragment_check(timeline, fps):
    """片段状态（启用/禁用）"""
    return check_disabled_items(timeline, fps)

def _run_black_frame_check(timeline, fps):
    """黑帧"""
    return check_black_frames(timeline, fps)

def _run_mono_check(timeline, fps):
    """声道"""
    return check_audio_mono(timeline, fps)

def _run_timeline_check(timeline, fps):
    """时间线设置"""
    return check_timeline_settings(timeline, fps=fps)

def _run_censor_cn(timeline, fps):
    """中文违禁词"""
    return check_subtitle_censor(timeline, os.path.join(_SCRIPT_DIR, "dicts", "censor_cn.txt"), fps)

def _run_censor_en(timeline, fps):
    """英文违禁词"""
    return check_subtitle_censor(timeline, os.path.join(_SCRIPT_DIR, "dicts", "censor_en.txt"), fps)

def _run_censor_nrta(timeline, fps):
    """广电违禁词"""
    return check_subtitle_censor(timeline, os.path.join(_SCRIPT_DIR, "dicts", "censor_nrta.txt"), fps)

def _run_censor_juicy(timeline, fps):
    """短剧违禁词"""
    return check_subtitle_censor(timeline, os.path.join(_SCRIPT_DIR, "dicts", "censor_juicy.txt"), fps)

CHECKS = [
    {"id": "timeline",      "section": "时间线",   "chk_id": CHK_TIMELINE,      "group": "工程", "run_fn": _run_timeline_check},
    {"id": "track",         "section": "轨道结构", "chk_id": CHK_TRACK,          "group": "工程", "run_fn": _run_track_check},
    {"id": "fragment",      "section": "片段状态", "chk_id": CHK_FRAGMENT,       "group": "工程", "run_fn": _run_fragment_check},
    {"id": "sub_duration",  "section": "时长",     "chk_id": CHK_SUB_DURATION,   "group": "字幕", "run_fn": _run_sub_duration_check},
    {"id": "sub_linebreak", "section": "换行",     "chk_id": CHK_SUB_LINEBREAK,  "group": "字幕", "run_fn": _run_sub_linebreak_check},
    {"id": "sub_glyph",     "section": "异体字",   "chk_id": CHK_SUB_GLYPH,      "group": "字幕", "run_fn": _run_sub_glyph_check},
    {"id": "censor_cn",     "section": "中文违禁词","chk_id": CHK_CENSOR_CN,     "group": "字幕", "run_fn": _run_censor_cn},
    {"id": "censor_en",     "section": "英文违禁词","chk_id": CHK_CENSOR_EN,     "group": "字幕", "run_fn": _run_censor_en},
    {"id": "censor_nrta",   "section": "广电违禁词","chk_id": CHK_CENSOR_NRTA,   "group": "字幕", "run_fn": _run_censor_nrta},
    {"id": "censor_juicy",  "section": "短剧违禁词","chk_id": CHK_CENSOR_JUICY,  "group": "字幕", "run_fn": _run_censor_juicy},
    {"id": "black_frame",   "section": "黑帧",     "chk_id": CHK_BLACK,          "group": "视频", "run_fn": _run_black_frame_check},
    {"id": "black_border",  "section": "黑边",     "chk_id": CHK_BORDER,         "run_fn": None},
    {"id": "audio_mono",    "section": "声道",     "chk_id": CHK_MONO,           "group": "音频", "run_fn": _run_mono_check},
    {"id": "audio_loudness","section": "音量",     "chk_id": CHK_LOUDNESS,       "run_fn": None},
    {"id": "color",         "section": "色彩",     "chk_id": CHK_COLOR,           "run_fn": None},
]
# 扩展指南：
#   - 加新检查：往 CHECKS 末尾加一行 dict，写 run_fn
#   - 换位置：移动 list 中 dict 的位置
#   - 暂时关闭：run_fn 设为 None
#   - 如果新检查需要专属 CheckBox，在控件 ID 区和 UI 布局区加对应行

# ── 启动时校验：CHECKS 注册表与 run_fn 一致性 ──
def _validate_checks():
    """确保 CHECKS 中每个 run_fn 都存在且可调用。"""
    import inspect
    errors = []
    for c in CHECKS:
        fn = c.get("run_fn")
        if fn is None:
            continue
        if not callable(fn):
            errors.append(f"CHECKS['{c['id']}'] run_fn 不可调用: {fn}")
            continue
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            errors.append(f"CHECKS['{c['id']}'] run_fn 无法获取签名: {fn}")
            continue
        params = list(sig.parameters.keys())
        if not params:
            errors.append(f"CHECKS['{c['id']}'] run_fn 无参数: {fn}")
    if errors:
        raise AssertionError("CHECKS 注册表校验失败:\n  " + "\n  ".join(errors))

_validate_checks()
del _validate_checks  # 用完即焚，不污染命名空间

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════
_track_values = [DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS]
_track_editing = False
_clamp_value = DEFAULT_CLAMP_THRESHOLD
_clamp_editing = False
_checking = False

# 轨道编辑 UI 暂时关闭（裁缝老师说放开时改 True 即可）
_TRACK_EDIT_VISIBLE = False

# ═══════════════════════════════════════════
# 日志系统
# ═══════════════════════════════════════════
_HOSTNAME = socket.gethostname()
_LOG_DIR_SMB = "/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具/logs"
_LOG_FILE_SMB = os.path.join(_LOG_DIR_SMB, f"{_HOSTNAME}.log")

# 本地开发日志
_DEV_LOG_DIR = "/tmp/delivery_checker_dev"
_LOG_FILE_LOCAL = os.path.join(_DEV_LOG_DIR,
                               f"{_HOSTNAME}.log" if not __version__.endswith("-dev")
                               else f"{_HOSTNAME}_dev.log")


def _ts():
    """当前时间戳字符串"""
    return time.strftime("%m-%d %H:%M:%S")


def _action_log(msg: str):
    """记录操作日志：SMB + 本地文件"""
    ts = _ts()
    line = f"[{ts}] {msg}"

    # SMB 持久化
    try:
        os.makedirs(_LOG_DIR_SMB, exist_ok=True)
        with open(_LOG_FILE_SMB, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    # 本地文件
    try:
        os.makedirs(_DEV_LOG_DIR, exist_ok=True)
        with open(_LOG_FILE_LOCAL, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════
# UI 布局
# ═══════════════════════════════════════════
_CHECK_ROW_STYLE = "font-size:13px;color:rgb(220,220,220)"
_SECTION_LABEL = "color:rgb(220,220,220);font-size:14px;font-weight:bold;min-height:18px"

def _sec_label(text):
    """行内分类标签"""
    return ui.Label({"Text": text, "StyleSheet": _SECTION_LABEL, "Weight": 0})
_DISABLED_CB = {"Checked": False, "Enabled": False, "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}

def _cb(id_, text, extra=None):
    """快捷创建 CheckBox"""
    cfg = {"ID": id_, "Text": text, "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0, "Checked": True}
    if extra:
        cfg.update(extra)
    return ui.CheckBox(cfg)

def _disabled_cb(id_, text):
    """创建灰色不可点的 CheckBox，文案加 (待开发)"""
    return _cb(id_, f"{text} (待开发)", _DISABLED_CB)

window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # ── 上半区：检查选项 + 开始按钮 ──
        ui.HGroup({"Spacing": 10, "Weight": 0}, [
            # 左侧
            ui.VGroup({"Spacing": 2, "Weight": 0}, [

            # ═══ 工程设置 ═══
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _sec_label("工程"),
                _cb(CHK_TIMELINE, "时间线"),
                _cb(CHK_FRAGMENT, "片段状态"),
                _cb(CHK_TRACK, "轨道结构"),
                ui.Label({"ID": "lbl_track_sub", "Text": "字幕", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_SUB_VAL, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_SUB, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                             "MaximumSize": [20, 20], "Weight": 0}),
                ui.Label({"ID": "lbl_track_vid", "Text": "视频", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_VID_VAL, "Text": str(DEFAULT_VIDEO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_VID, "Text": str(DEFAULT_VIDEO_TRACKS),
                             "MaximumSize": [20, 20], "Weight": 0}),
                ui.Label({"ID": "lbl_track_aud", "Text": "音频", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_AUD_VAL, "Text": str(DEFAULT_AUDIO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_AUD, "Text": str(DEFAULT_AUDIO_TRACKS),
                             "MaximumSize": [20, 20], "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_TRACK, "Text": "✎", "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_TRACK, "Text": "✓", "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),

            # ═══ 视频 ═══
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _sec_label("视频"),
                _cb(CHK_BLACK, "黑帧"),
                _disabled_cb(CHK_BORDER, "黑边"),
            ]),

            # ═══ 音频 ═══
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _sec_label("音频"),
                _cb(CHK_MONO, "声道"),
                _disabled_cb(CHK_LOUDNESS, "音量"),
            ]),

            # ═══ 字幕 ═══
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _sec_label("字幕"),
                _cb(CHK_SUB_DURATION, "时长"),
                _cb(CHK_SUB_LINEBREAK, "换行"),
                _cb(CHK_SUB_GLYPH, "异体字"),
                ui.Label({"Text": "阈值", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_CLAMP_VAL, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_CLAMP, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                             "MaximumSize": [20, 20], "Weight": 0}),
                ui.Label({"Text": "帧", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_CLAMP, "Text": "✎", "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_CLAMP, "Text": "✓", "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _cb(CHK_CENSOR_CN, "中文违禁词"),
                _cb(CHK_CENSOR_JUICY, "短剧违禁词"),
                _disabled_cb(CHK_CENSOR_EN, "英文违禁词"),
                _disabled_cb(CHK_CENSOR_NRTA, "广电违禁词"),
            ]),

            # ═══ 色彩 ═══
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                _sec_label("色彩"),
                _cb(CHK_COLOR, "（待开发）", _DISABLED_CB),
            ]),

            ]),  # 结束左侧 VGroup

            ui.HGap({"Weight": 1}),

            # 全选/全不选 + 开始检查
            ui.VGroup({"Spacing": 4, "Weight": 0}, [
                ui.Button({"ID": BTN_SEL_ALL, "Text": "全选",
                           "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                           "MinimumSize": [60, 22]}),
                ui.Button({"ID": BTN_DESEL_ALL, "Text": "全不选",
                           "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                           "MinimumSize": [60, 22]}),
            ]),

            ui.Button({"ID": BTN_START, "Text": "开始检查",
                       "StyleSheet": BTN_PRIMARY, "Weight": 0,
                       "MinimumSize": [_BTN_HEIGHT, _BTN_HEIGHT]}),
        ]),

        # ── 状态标签 ──
        ui.Label({"ID": ST_LB, "Text": "",
                  "StyleSheet": "color:rgb(180,180,180);font-size:11px;min-height:18px",
                  "Weight": 0}),

        # ── 结果区：Tree（可点击跳转）──
        ui.Tree({"ID": TREE_RESULT, "Weight": 1.0,
                 "Events": {"ItemClicked": True, "ItemDoubleClicked": True}}),

        # ── 底栏 ──
        ui.VGroup({"Spacing": 2, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Label({"ID": HINT_LB, "Text": "请点击「开始检查」",
                          "StyleSheet": "color:rgb(130,130,130);font-size:10px", "Weight": 0,
                          "MinimumSize": [260, 16]}),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"裁缝老师的达芬奇插件工坊 ✂️ | v{__version__}",
                          "StyleSheet": "color:rgb(100,100,100);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": "交付自检",
    "ID": WIN_ID,
    "Geometry": [800, 100, 900, 520],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# ═══════════════════════════════════════════
# 初始状态
# ═══════════════════════════════════════════
# 轨道编辑 UI 暂时关闭（由 _TRACK_EDIT_VISIBLE 控制）
itm["lbl_track_sub"].Visible = _TRACK_EDIT_VISIBLE
itm[LBL_SUB_VAL].Visible = _TRACK_EDIT_VISIBLE
itm[EDIT_SUB].Visible = _TRACK_EDIT_VISIBLE
itm["lbl_track_vid"].Visible = _TRACK_EDIT_VISIBLE
itm[LBL_VID_VAL].Visible = _TRACK_EDIT_VISIBLE
itm[EDIT_VID].Visible = _TRACK_EDIT_VISIBLE
itm["lbl_track_aud"].Visible = _TRACK_EDIT_VISIBLE
itm[LBL_AUD_VAL].Visible = _TRACK_EDIT_VISIBLE
itm[EDIT_AUD].Visible = _TRACK_EDIT_VISIBLE
itm[BTN_EDIT_TRACK].Visible = _TRACK_EDIT_VISIBLE
itm[BTN_SAVE_TRACK].Visible = _TRACK_EDIT_VISIBLE

itm[EDIT_CLAMP].Visible = False
itm[BTN_SAVE_CLAMP].Visible = False
itm[BTN_EDIT_CLAMP].Visible = False  # 暂不可编辑，要恢复删这行即可
itm[BTN_START].Enabled = False

# Tree 表头
tree = itm[TREE_RESULT]
_setup_tree_header(tree)

# ═══════════════════════════════════════════
# Tree 渲染
# ═══════════════════════════════════════════

def _render_groups(sections, tree):
    """按四大分组层级渲染结果到 Tree。
    
    三级结构：
        ▲ 工程（Group 父节点）
          ◆ 时间线  —  汇总（Check 子节点）
            ❌  V1  00:00:01:00  详情...  原因...（Detail 行）
    """
    # 按 GROUP_ORDER 顺序，从 sections 中筛选
    for group_name in GROUP_ORDER:
        secs = [s for s in sections if s.get("group") == group_name]
        if not secs:
            continue

        # ── Group 父节点 ──
        group_parent = tree.NewItem()
        _set_row_texts(group_parent, f"▲ {group_name}", "", "", "", "")
        tree.AddTopLevelItem(group_parent)

        # ── 各检查 ──
        for sec in secs:
            # Check 子节点
            check_row = tree.NewItem()
            title = sec["title"]
            if sec["all_ok"]:
                title += "  — 全部通过"
            elif sec["summary"]:
                title += "  —  " + sec["summary"]
            _set_row_texts(check_row, f"◆ {title}", "", "", "", "")
            group_parent.AddChild(check_row)

            # Detail 行（只在不通过时显示）
            if not sec["all_ok"]:
                for row_data in sec["rows"]:
                    row = tree.NewItem()
                    _set_row(row, row_data)
                    group_parent.AddChild(row)


# ═══════════════════════════════════════════
# 轨道编辑：✎ 进入编辑 / ✓ 保存
# ═══════════════════════════════════════════

def _enter_track_edit():
    """进入轨道编辑模式"""
    if not _TRACK_EDIT_VISIBLE:
        return
    global _track_editing
    _track_editing = True
    itm[EDIT_SUB].Text = itm[LBL_SUB_VAL].Text
    itm[EDIT_VID].Text = itm[LBL_VID_VAL].Text
    itm[EDIT_AUD].Text = itm[LBL_AUD_VAL].Text
    itm[LBL_SUB_VAL].Visible = False
    itm[LBL_VID_VAL].Visible = False
    itm[LBL_AUD_VAL].Visible = False
    itm[BTN_EDIT_TRACK].Visible = False
    itm[EDIT_SUB].Visible = True
    itm[EDIT_VID].Visible = True
    itm[EDIT_AUD].Visible = True
    itm[BTN_SAVE_TRACK].Visible = True
    _action_log("✎ 轨道数字 编辑模式")


def _save_track_edit():
    """保存轨道编辑"""
    global _track_editing, _track_values
    try:
        sv = int(itm[EDIT_SUB].Text)
        vv = int(itm[EDIT_VID].Text)
        av = int(itm[EDIT_AUD].Text)
        if sv < 0 or vv < 0 or av < 0:
            _action_log("⚠ 轨道数字不能为负, 放弃保存")
            return
    except ValueError:
        _action_log(f"⚠ 轨道数字无效: {itm[EDIT_SUB].Text},{itm[EDIT_VID].Text},{itm[EDIT_AUD].Text}, 放弃保存")
        return

    old = _track_values.copy()
    _track_values = [sv, vv, av]
    _track_editing = False
    itm[LBL_SUB_VAL].Text = str(sv)
    itm[LBL_VID_VAL].Text = str(vv)
    itm[LBL_AUD_VAL].Text = str(av)
    itm[EDIT_SUB].Visible = False
    itm[EDIT_VID].Visible = False
    itm[EDIT_AUD].Visible = False
    itm[BTN_SAVE_TRACK].Visible = False
    itm[LBL_SUB_VAL].Visible = True
    itm[LBL_VID_VAL].Visible = True
    itm[LBL_AUD_VAL].Visible = True
    itm[BTN_EDIT_TRACK].Visible = True

    _action_log(f"✎ 轨道数字 保存: [{old[0]},{old[1]},{old[2]}] → [{sv},{vv},{av}]")


def _refuse_edit():
    """拒绝编辑：恢复显示模式"""
    global _track_editing, _clamp_editing
    if _track_editing:
        _track_editing = False
        itm[EDIT_SUB].Visible = _TRACK_EDIT_VISIBLE
        itm[EDIT_VID].Visible = _TRACK_EDIT_VISIBLE
        itm[EDIT_AUD].Visible = _TRACK_EDIT_VISIBLE
        itm[BTN_SAVE_TRACK].Visible = _TRACK_EDIT_VISIBLE
        itm[LBL_SUB_VAL].Visible = _TRACK_EDIT_VISIBLE
        itm[LBL_VID_VAL].Visible = _TRACK_EDIT_VISIBLE
        itm[LBL_AUD_VAL].Visible = _TRACK_EDIT_VISIBLE
        itm[BTN_EDIT_TRACK].Visible = _TRACK_EDIT_VISIBLE
        _action_log("✎ 轨道数字 取消编辑")
    if _clamp_editing:
        _clamp_editing = False
        itm[EDIT_CLAMP].Visible = False
        itm[BTN_SAVE_CLAMP].Visible = False
        itm[LBL_CLAMP_VAL].Visible = True
        itm[BTN_EDIT_CLAMP].Visible = True
        _action_log("✎ 夹帧阈值 取消编辑")


# ═══════════════════════════════════════════
# 夹帧阈值编辑
# ═══════════════════════════════════════════

def _enter_clamp_edit():
    global _clamp_editing
    _clamp_editing = True
    itm[EDIT_CLAMP].Text = itm[LBL_CLAMP_VAL].Text
    itm[LBL_CLAMP_VAL].Visible = False
    itm[BTN_EDIT_CLAMP].Visible = False
    itm[EDIT_CLAMP].Visible = True
    itm[BTN_SAVE_CLAMP].Visible = True
    _action_log("✎ 夹帧阈值 编辑模式")


def _save_clamp_edit():
    global _clamp_editing, _clamp_value
    try:
        cv = int(itm[EDIT_CLAMP].Text)
        if cv < 1:
            _action_log("⚠ 夹帧阈值不能小于1, 放弃保存")
            return
    except ValueError:
        _action_log(f"⚠ 夹帧阈值无效: {itm[EDIT_CLAMP].Text}, 放弃保存")
        return

    old = _clamp_value
    _clamp_value = cv
    _clamp_editing = False
    itm[LBL_CLAMP_VAL].Text = str(cv)
    itm[EDIT_CLAMP].Visible = False
    itm[BTN_SAVE_CLAMP].Visible = False
    itm[LBL_CLAMP_VAL].Visible = True
    itm[BTN_EDIT_CLAMP].Visible = True

    _action_log(f"✎ 夹帧阈值 保存: {old} → {cv}")


# ═══════════════════════════════════════════
# 结果处理
# ═══════════════════════════════════════════

def _process_result(r, rows_list):
    """处理单条检查结果。读取 track/timecode/detail 三字段，无需解析。返回 (has_fail, is_pass)"""
    if r["status"] == "pass":
        return False, True

    icon = "❌" if r["status"] == "fail" else "⚠"
    rows_list.append({
        "icon": icon,
        "tc": r.get("timecode", ""),
        "track": r.get("track", ""),
        "msg": r.get("detail", ""),
        "reason": r.get("reason", ""),
    })
    _action_log(r.get("detail", ""))
    return True, False


# ═══════════════════════════════════════════
# 开始检查
# ═══════════════════════════════════════════

def _start_check():
    global _checking, _start_time
    if _checking:
        return
    _checking = True
    _start_time = time.time()
    itm[BTN_START].Enabled = False

    any_checked = any(
        itm[c["chk_id"]].Checked for c in CHECKS if c.get("run_fn")
    )
    if not any_checked:
        _action_log("⚠ 未选择任何检查项")
        _checking = False
        itm[BTN_START].Enabled = True
        return

    _action_log(f"▶ 开始检查 (轨道模板={_track_values}, 夹帧阈值={_clamp_value})")
    itm[HINT_LB].Text = "检查中..."

    try:
        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            _action_log("❌ 未连接达芬奇")
            _checking = False
            itm[BTN_START].Enabled = True
            return

        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            _action_log("❌ 未打开项目")
            _checking = False
            itm[BTN_START].Enabled = True
            return

        timeline = project.GetCurrentTimeline()
        if not timeline:
            _action_log("❌ 未打开时间线")
            _checking = False
            itm[BTN_START].Enabled = True
            return

        fps = float(project.GetSetting("timelineFrameRate"))

        itm[ST_LB].Text = f"项目: {project.GetName()}  |  时间线: {timeline.GetName()}  |  {fps} fps"
        _action_log(f"项目: {project.GetName()}")
        _action_log(f"时间线: {timeline.GetName()}")
        _action_log(f"帧率: {fps} fps")

        # 预加载所有轨道片段（避免每个检查重复 IPC）
        preload_timeline_items(timeline)

        # 清空结果
        tree.Clear()
        _setup_tree_header(tree)

        has_failures = False
        pass_count = 0
        fail_count = 0
        sections = []

        # 按注册表顺序执行检查
        for check in CHECKS:
            if not check.get("run_fn"):
                continue
            if not itm[check["chk_id"]].Checked:
                continue

            _action_log(f"── {check['section']}检查 ──")
            all_results = list(check["run_fn"](timeline, fps))
            section_rows = []
            section_pass = 0
            summary_text = ""

            # 第一条如果是汇总行，提取到标题里
            if all_results and all_results[0].get("is_summary"):
                summary_text = all_results[0]["detail"]
                rest = all_results[1:]
            else:
                summary_text = ""
                rest = all_results

            for r in rest:
                has_fail, is_pass = _process_result(r, section_rows)
                if is_pass:
                    pass_count += 1
                    section_pass += 1
                elif has_fail:
                    fail_count += 1
                    has_failures = True

            all_ok = not section_rows and section_pass > 0
            sections.append({
                "group": check.get("group", ""),
                "title": check["section"],
                "summary": summary_text,
                "rows": section_rows,
                "all_ok": all_ok,
            })

        # 按分组层级展示
        _render_groups(sections, tree)

        # 总结
        elapsed_ms = int((time.time() - _start_time) * 1000)
        if has_failures:
            _action_log("❌ 检查未通过 — 请修复上述问题")
            itm[ST_LB].Text += f"  |  ❌ 未通过  ({elapsed_ms}ms)"
        else:
            _action_log("✅ 所有检查通过")
            itm[ST_LB].Text += f"  |  ✅ 通过  ({elapsed_ms}ms)"
        itm[HINT_LB].Text = "💡 点击结果行可跳转到对应时间码"

    except Exception as e:
        _action_log(f"❌ 检查崩溃: {e}")
        traceback.print_exc()
    finally:
        _checking = False
        itm[BTN_START].Enabled = True


# ═══════════════════════════════════════════
# 结果点击 → 跳转播放头
# ═══════════════════════════════════════════

def _on_result_click(ev):
    """Tree 行点击 → 跳到对应时间码"""
    try:
        # ev 里可能有 Item 键，CurrentItem 是方法要加 ()
        item = ev.get("Item")
        if item is None:
            item = tree.CurrentItem()
        if item is None:
            _action_log(f"⚠ 跳转: 取不到 Item, ev={type(ev)} keys={list(ev.keys()) if hasattr(ev,'keys') else '?'}")
            return
        # 从 COLUMNS 找到 timecode 列的真实索引
        tc_idx = _col_index("tc")
        tc = item.Text[tc_idx] if tc_idx >= 0 else ""
        if not tc:
            return
        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            return
        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            return
        timeline = project.GetCurrentTimeline()
        if not timeline:
            return
        timeline.SetCurrentTimecode(tc)
        _action_log(f"🎯 跳转到 {tc}")
    except Exception as e:
        _action_log(f"⚠ 跳转失败: {e}")


# ═══════════════════════════════════════════
# 窗口事件
# ═══════════════════════════════════════════

def _on_show(ev):
    pass  # 初始化放在 main() 里，Show 事件在子进程模式下不可靠


def _init_connection():
    """初始化达芬奇连接，设置按钮状态"""
    try:
        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            _action_log("⚠ 未连接达芬奇")
            itm[ST_LB].Text = "⚠ 请先启动 DaVinci Resolve"
            return

        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            _action_log("⚠ 未打开项目")
            itm[ST_LB].Text = "⚠ 请先打开一个项目"
            return

        timeline = project.GetCurrentTimeline()
        if not timeline:
            _action_log("⚠ 未打开时间线")
            itm[ST_LB].Text = "⚠ 当前项目没有时间线"
            return

        fps = float(project.GetSetting("timelineFrameRate"))
        _action_log(f"连接达芬奇: 成功")
        _action_log(f"项目: {project.GetName()}")
        _action_log(f"时间线: {timeline.GetName()}  |  {fps} fps")
        itm[ST_LB].Text = f"就绪 — {project.GetName()} / {timeline.GetName()}  |  {fps} fps"
        itm[BTN_START].Enabled = True
        itm[HINT_LB].Text = "请点击「开始检查」"

    except Exception as e:
        _action_log(f"❌ 初始化失败: {e}")
        itm[ST_LB].Text = f"❌ 初始化失败: {e}"


def _on_close(ev):
    global _checking
    _checking = False
    _refuse_edit()
    _action_log("窗口关闭")
    disp.ExitLoop()


def _toggle_all(checked):
    """全选/全不选所有可用的 CheckBox"""
    for c in CHECKS:
        cid = c["chk_id"]
        if cid is None or c.get("run_fn") is None:
            continue
        try:
            itm[cid].Checked = checked
            _action_log(f"{'☑' if checked else '☐'} {c['section']}")
        except Exception:
            pass


# ═══════════════════════════════════════════
# 事件绑定
# ═══════════════════════════════════════════

# CheckBox 事件 — 从 CHECKS 自动生成
for _c in CHECKS:
    _cid = _c["chk_id"]
    if _cid is None:
        continue
    _section = _c["section"]
    dlg.On[_cid].Clicked = (
        lambda ev, cid=_cid, sec=_section: _action_log(
            f"{'☑' if itm[cid].Checked else '☐'} {sec} {'勾选' if itm[cid].Checked else '取消'}"
        )
    )
dlg.On[BTN_EDIT_TRACK].Clicked = lambda ev: _enter_track_edit()
dlg.On[BTN_SAVE_TRACK].Clicked = lambda ev: _save_track_edit()
dlg.On[BTN_EDIT_CLAMP].Clicked = lambda ev: _enter_clamp_edit()
dlg.On[BTN_SAVE_CLAMP].Clicked = lambda ev: _save_clamp_edit()
dlg.On[BTN_START].Clicked = lambda ev: _start_check()
dlg.On[BTN_SEL_ALL].Clicked = lambda ev: _toggle_all(True)
dlg.On[BTN_DESEL_ALL].Clicked = lambda ev: _toggle_all(False)
dlg.On[TREE_RESULT].ItemClicked = _on_result_click
dlg.On[TREE_RESULT].ItemDoubleClicked = _on_result_click
dlg.On[WIN_ID].Show = _on_show
dlg.On[WIN_ID].Close = _on_close


# ═══════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════

def main():
    _action_log("═══ 交付自检 启动 v" + __version__ + " ═══")
    dlg.Show()
    dlg.RecalcLayout()
    _init_connection()
    disp.RunLoop()
    dlg.Hide()


if __name__ == "__main__":
    main()
