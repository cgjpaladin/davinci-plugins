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
import json

# 达芬奇官方API目录（系统级，保留）
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
    __channel__,
    version_string,
    DEFAULT_CLAMP_THRESHOLD,
    DEFAULT_BLACK_FRAME_SEC,
    DEFAULT_SUBTITLE_TRACKS,
    DEFAULT_VIDEO_TRACKS,
    DEFAULT_AUDIO_TRACKS,
    AUDIO_TRACK_PRESET,
)
from check_core import (check_track_structure, check_subtitle_clamping, check_disabled_items,
                          check_black_frames, check_audio_mono, check_timeline_settings,
                          check_subtitle_glyph, check_subtitle_linebreak, check_subtitle_censor,
                          check_black_borders, check_speed, check_video_clamping, preload_timeline_items,
                          check_color, check_camera_on_high_tracks, check_audio_color_tracks,
                          check_path_location, check_offline_clips)

# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════
WIN_ID = "com.myjc.delivery_checker"

# 控件 ID
CHK_TRACK, CHK_SUB_DURATION, CHK_SUB_LINEBREAK, CHK_SUB_GLYPH = \
    "chk_track", "chk_sub_dur", "chk_sub_br", "chk_sub_glyph"
CHK_BLACK, CHK_VIDEO_CLAMP, CHK_BORDER, CHK_SPEED, CHK_MONO, CHK_LOUDNESS, CHK_FRAGMENT, CHK_TIMELINE, CHK_COLOR = \
    "chk_black", "chk_vid_clamp", "chk_border", "chk_speed", "chk_mono", "chk_loudness", "chk_fragment", "chk_timeline", "chk_color"
CHK_CENSOR_SYSTEM, CHK_CENSOR_PERSONAL, CHK_TYPO = "chk_censor_sys", "chk_censor_personal", "chk_typo"
CHK_CAMERA = "chk_camera"
CHK_AUDIO_COLOR = "chk_audio_color"
CHK_PATH = "chk_path"
CHK_OFFLINE = "chk_offline"
CHK_BLACK_FRAME = CHK_BLACK  # 别名
BTN_START = "btn_start"
BTN_CONFIG = "btn_config"
BTN_AI_TYPO = "btn_ai_typo"
BTN_VALIDATE_SCRIPT = "btn_validate_script"
EDIT_SCRIPT_SRC = "edit_script_src"
EDIT_SCRIPT_EP = "edit_script_ep"
LBL_SCRIPT_STATUS = "lbl_script_status"
BTN_TOGGLE_GROUP = "btn_toggle_group_"  # + group_name → "btn_toggle_group_工程"
TREE_RESULT = "tree_result"
GROUP_TREE = "group_tree"
HINT_LB = "hint_lb"

# ── 结果列定义：加/删/挪/开关列只改这里 ──
#   enabled=False → 列暂时隐藏，不删定义
COLUMNS = [
    {"header": "轨道",   "width": 48,  "key": "track",  "enabled": True},
    {"header": "时码",   "width": 120, "key": "tc",     "enabled": True},
    {"header": "问题",   "width": 300, "key": "msg",    "enabled": True},
    {"header": "建议",   "width": 180, "key": "reason", "enabled": True},
]

# 当前启用的列（enabled=True）
_ENABLED_COLS = [c for c in COLUMNS if c.get("enabled", True)]

# ── 结果分组顺序（四大分组，控制 Tree 渲染层级）──
GROUP_ORDER = ["工程", "视频", "音频", "字幕", "色彩"]

# ── check_core 输出字段 → Tree 列 key 映射（单一真相源）──
# 加新字段规则：这里加一行 → COLUMNS 加一列 → _process_result 自动映射
# 删字段同理：这里删一行 → COLUMNS 删对应列 → 完
FIELD_TO_COLUMN = {
    "track":    "track",     # 轨道（直接透传）
    "timecode": "tc",        # 时码（仅 key 名不同）
    "detail":   "msg",       # 问题（仅 key 名不同）
    "reason":   "reason",    # 建议（直接透传）
}

# 启动时校验：FIELD_TO_COLUMN 与 COLUMNS 一致
def _validate_field_map():
    col_keys = {c["key"] for c in COLUMNS if c.get("enabled", True)}
    map_keys = set(FIELD_TO_COLUMN.values())
    only_in_map = map_keys - col_keys
    only_in_col = col_keys - map_keys
    errors = []
    if only_in_map:
        errors.append(f"FIELD_TO_COLUMN 中有但 COLUMNS 中无: {only_in_map}")
    if only_in_col:
        errors.append(f"COLUMNS 中有但 FIELD_TO_COLUMN 中无: {only_in_col}")
    if errors:
        raise AssertionError("字段映射不一致:\n  " + "\n  ".join(errors))
_validate_field_map()
del _validate_field_map


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
# ═══════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════
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

def _run_track_check(timeline, fps, **_kw):
    """轨道结构"""
    return check_track_structure(timeline, *_track_values)

def _run_sub_duration_check(timeline, fps, **_kw):
    """字幕时长（过短 + 夹帧）"""
    return check_subtitle_clamping(timeline, _clamp_value, fps, io_range=_kw.get("io_range"))

def _run_sub_glyph_check(timeline, fps, **_kw):
    """字幕异体字"""
    return check_subtitle_glyph(timeline, fps, io_range=_kw.get("io_range"))

def _run_sub_linebreak_check(timeline, fps, **_kw):
    """字幕换行（CPL + 硬换行）"""
    return check_subtitle_linebreak(timeline, fps, io_range=_kw.get("io_range"))

def _run_fragment_check(timeline, fps, **_kw):
    """片段状态（启用/禁用）"""
    return check_disabled_items(timeline, fps, io_range=_kw.get("io_range"))

def _run_black_frame_check(timeline, fps, **_kw):
    """黑帧"""
    return check_black_frames(timeline, fps, threshold_sec=_black_frame_sec, io_range=_kw.get("io_range"))

def _run_black_border_check(timeline, fps, **_kw):
    """黑边"""
    return check_black_borders(timeline, project=_kw.get("project"), fps=fps, io_range=_kw.get("io_range"))

def _run_speed_check(timeline, fps, **_kw):
    """变速"""
    return check_speed(timeline, project_fps=fps, io_range=_kw.get("io_range"))

def _run_video_clamp_check(timeline, fps, **_kw):
    """视频夹帧"""
    return check_video_clamping(timeline, _video_clamp_threshold, fps, io_range=_kw.get("io_range"))

def _run_mono_check(timeline, fps, **_kw):
    """声道"""
    return check_audio_mono(timeline, fps, io_range=_kw.get("io_range"))

def _run_color_check(timeline, fps, **_kw):
    """调色"""
    return check_color(timeline, project=_kw.get("project"), fps=fps, io_range=_kw.get("io_range"))

def _run_camera_track_check(timeline, fps, **_kw):
    """实拍素材越轨"""
    return check_camera_on_high_tracks(timeline, fps=fps, io_range=_kw.get("io_range"))

def _run_audio_color_check(timeline, fps, **_kw):
    """音频颜色越轨"""
    return check_audio_color_tracks(timeline, fps=fps, io_range=_kw.get("io_range"))

def _run_timeline_check(timeline, fps, **_kw):
    """时间线设置"""
    return check_timeline_settings(timeline, fps=fps, project=_kw.get("project"))

def _run_path_check(timeline, fps, **_kw):
    """当前时间线 SMB 路径检测"""
    return check_path_location(timeline, fps=fps, io_range=_kw.get("io_range"), project=_kw.get("project"))

def _run_offline_check(timeline, fps, **_kw):
    """当前时间线脱机文件检测"""
    return check_offline_clips(timeline, fps=fps, io_range=_kw.get("io_range"))

def _run_censor_system(timeline, fps, **_kw):
    """系统词典（合并所有启用的子词典→一次扫描）"""
    import tempfile, csv
    SUB_MAP = [
        ("cn",     ["censor_cn.txt"]),
        ("en",     ["censor_en.txt"]),
        ("bw",     ["censor_bw.txt"]),
        ("bw_sms", ["censor_bw_sms.txt"]),
    ]
    # 加载个人词典白名单
    whitelist_path = None
    personal_csv = os.path.join(_SCRIPT_DIR, "dicts", "短剧违禁词表.csv")
    white_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        if os.path.isfile(personal_csv):
            whitelist = []
            with open(personal_csv, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 2 and row[1].strip():
                        whitelist.append(row[1].strip())
            if whitelist:
                for w in whitelist:
                    white_tmp.write(w + "\n")
                white_tmp.close()
                whitelist_path = white_tmp.name
    except Exception:
        pass
    if not whitelist_path:
        white_tmp.close()

    # 合并启用的子词典 → 临时文件 → 一次扫描
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        for key, dict_files in SUB_MAP:
            if _censor_subs.get(key, True):
                for df in dict_files:
                    path = os.path.join(_SCRIPT_DIR, "dicts", df)
                    if os.path.isfile(path):
                        with open(path, "r", encoding="utf-8", errors="ignore") as src:
                            tmp.write(src.read())
        tmp.close()
        all_results = check_subtitle_censor(timeline, tmp.name, fps,
            io_range=_kw.get("io_range"), use_warn=True,
            whitelist_path=whitelist_path)
    finally:
        os.unlink(tmp.name)
        if whitelist_path:
            try: os.unlink(whitelist_path)
            except: pass

    # 过滤个人词典已覆盖的词
    personal_words = set()
    if _kw.get("personal_enabled"):
        personal_path = os.path.join(_SCRIPT_DIR, "dicts", "短剧违禁词表.csv")
        if os.path.isfile(personal_path):
            with open(personal_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if w and not w.startswith("#"):
                        parts = w.split(",")
                        if len(parts) >= 3:
                            personal_words.add(parts[2].strip())

    if personal_words:
        all_results = _filter_covered(all_results, personal_words)
    return all_results

def _run_censor_personal(timeline, fps, **_kw):
    """个人词典（黑名单+白名单）"""
    import tempfile, csv
    csv_path = os.path.join(_SCRIPT_DIR, "dicts", "短剧违禁词表.csv")
    black_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    white_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        blacklist = []
        whitelist = []
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                for row in reader:
                    if len(row) >= 1:
                        b = row[0].strip()
                        if b:
                            blacklist.append(b)
                    if len(row) >= 2:
                        w = row[1].strip()
                        if w:
                            whitelist.append(w)
        for w in blacklist:
            black_tmp.write(w + "\n")
        black_tmp.close()
        if whitelist:
            for w in whitelist:
                white_tmp.write(w + "\n")
            white_tmp.close()
            return check_subtitle_censor(timeline, black_tmp.name, fps,
                io_range=_kw.get("io_range"), whitelist_path=white_tmp.name)
        else:
            white_tmp.close()
            return check_subtitle_censor(timeline, black_tmp.name, fps,
                io_range=_kw.get("io_range"))
    finally:
        try: os.unlink(black_tmp.name)
        except: pass
        try: os.unlink(white_tmp.name)
        except: pass

def _make_result_passthrough(status, track="", timecode="", detail="", reason="", is_summary=False):
    """同 check_core._make_result 格式，避免跨模块循环导入。"""
    return {"status": status, "track": track, "timecode": timecode,
            "detail": detail, "reason": reason, "is_summary": is_summary}

def _filter_covered(results, personal_words):
    """过滤掉个人词典已覆盖的违禁词。保留汇总行，移除被覆盖的详情行。"""
    kept = [results[0]]  # 保留汇总行
    removed = 0
    for r in results[1:]:
        word = r.get("detail", "")
        if word and word in personal_words:
            removed += 1
            continue
        kept.append(r)
    # 更新汇总行
    if removed:
        total = len(kept) - 1
        if total == 0:
            kept[0] = _make_result_passthrough("pass", detail="系统违禁词典: 无违禁词 (已由个人词典覆盖)", is_summary=True)
        else:
            kept[0] = _make_result_passthrough("fail",
                detail=f"系统违禁词典: {total} 处  (个人词典覆盖 {removed} 处)", is_summary=True)
    return kept
CHECKS = [
    # 第零道门（无gate → 永远跑）
    {"id": "timeline",      "section": "工程设置", "chk_id": CHK_TIMELINE,      "group": "工程", "subgroup": "设置",   "run_fn": _run_timeline_check,     "tracks": [], "gate": ""},
    {"id": "offline",       "section": "脱机检测", "chk_id": CHK_OFFLINE,       "group": "工程", "subgroup": "路径",   "run_fn": _run_offline_check,       "tracks": ["video"], "gate": ""},
    {"id": "path",          "section": "路径检测", "chk_id": CHK_PATH,           "group": "工程", "subgroup": "路径",   "run_fn": _run_path_check,          "tracks": ["video"], "gate": ""},
    {"id": "track",         "section": "轨道结构", "chk_id": CHK_TRACK,          "group": "工程", "subgroup": "轨道",   "run_fn": _run_track_check,        "tracks": ["subtitle","video","audio"], "gate": ""},
    {"id": "fragment",      "section": "启用/禁用", "chk_id": CHK_FRAGMENT,       "group": "工程", "subgroup": "启用",   "run_fn": _run_fragment_check,      "tracks": ["subtitle","video","audio"], "gate": "all"},
    # 字幕门
    {"id": "sub_linebreak", "section": "换行",     "chk_id": CHK_SUB_LINEBREAK,  "group": "字幕", "subgroup": "文本",   "run_fn": _run_sub_linebreak_check, "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "sub_duration",  "section": "时长",     "chk_id": CHK_SUB_DURATION,   "group": "字幕", "subgroup": "文本",   "run_fn": _run_sub_duration_check,  "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "sub_glyph",     "section": "异体字",   "chk_id": CHK_SUB_GLYPH,      "group": "字幕", "subgroup": "合规",   "run_fn": _run_sub_glyph_check,     "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "censor_personal","section": "个人词典","chk_id": CHK_CENSOR_PERSONAL,"group": "字幕", "subgroup": "合规",   "run_fn": _run_censor_personal,     "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "censor_system",  "section": "系统词典","chk_id": CHK_CENSOR_SYSTEM, "group": "字幕", "subgroup": "合规",   "run_fn": _run_censor_system,       "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "typo",           "section": "错别字校对",  "chk_id": CHK_TYPO,           "group": "字幕", "subgroup": "合规",   "run_fn": None,                     "tracks": [], "gate": "subtitle"},
    # 视频门
    {"id": "video_clamp",   "section": "夹帧",     "chk_id": CHK_VIDEO_CLAMP,    "group": "视频", "subgroup": "夹帧",   "run_fn": _run_video_clamp_check,   "tracks": ["video"], "gate": "video"},
    {"id": "black_frame",   "section": "黑帧",     "chk_id": CHK_BLACK,          "group": "视频", "subgroup": "黑帧",   "run_fn": _run_black_frame_check,   "tracks": ["video","audio"], "gate": "video"},
    {"id": "black_border",  "section": "黑边",     "chk_id": CHK_BORDER,         "group": "视频", "subgroup": "黑边",   "run_fn": _run_black_border_check,  "tracks": ["video"], "gate": "video"},
    {"id": "speed",         "section": "变速",     "chk_id": CHK_SPEED,           "group": "视频", "subgroup": "变速",   "run_fn": _run_speed_check,         "tracks": ["video"], "gate": "video"},
    {"id": "camera_track",  "section": "视频越轨", "chk_id": CHK_CAMERA,          "group": "视频", "subgroup": "越轨",   "run_fn": _run_camera_track_check,  "tracks": ["video"], "gate": "video"},
    {"id": "color",         "section": "色彩",     "chk_id": CHK_COLOR,           "group": "色彩", "subgroup": "色彩",   "run_fn": _run_color_check,         "tracks": ["video"], "gate": "video"},
    # 音频门
    {"id": "audio_mono",    "section": "声道",     "chk_id": CHK_MONO,           "group": "音频", "subgroup": "声道",   "run_fn": _run_mono_check,          "tracks": ["audio"], "gate": "audio"},
    {"id": "audio_loudness","section": "音量",     "chk_id": CHK_LOUDNESS,       "group": "音频", "subgroup": "声道",   "run_fn": None,                     "tracks": [], "gate": "audio"},
    {"id": "audio_color",   "section": "音频越轨", "chk_id": CHK_AUDIO_COLOR,     "group": "音频", "subgroup": "越轨",   "run_fn": _run_audio_color_check,   "tracks": ["audio"], "gate": "audio"},
]
# 扩展指南：
#   - gate: ""=无门永远跑, "subtitle"/"video"/"audio"=受对应结构门控制
#   - tracks: 声明需要的轨道类型, []不预加载; gate 关闭时相关轨道也不会预加载
#   - 换位置：移动 list 中 dict 的位置
#   - 暂时关闭：run_fn 设为 None

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
_clamp_value = DEFAULT_CLAMP_THRESHOLD
_video_clamp_threshold = 2  # 视频夹帧阈值（帧）
_black_frame_sec = DEFAULT_BLACK_FRAME_SEC
_censor_subs = {"base": True, "en": True, "bw": True, "bw_sms": True}
_checking = False

# ── 配置持久化（本地 JSON，每人独立）──
def _save_config_to_file():
    """保存当前配置到本地 JSON 文件"""
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        data = {
            "track_values": _track_values,
            "clamp_threshold": _clamp_value,
            "video_clamp_threshold": _video_clamp_threshold,
            "black_frame_sec": _black_frame_sec,
            "censor_subs": _censor_subs,
        }
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _action_log(f"⚠ 保存配置失败: {e}")

def _load_config_from_file():
    """从本地 JSON 加载配置，文件不存在则跳过"""
    global _track_values, _clamp_value, _video_clamp_threshold, _black_frame_sec, _censor_subs
    if not os.path.isfile(_CONFIG_FILE):
        return
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _track_values = data.get("track_values", _track_values)
        _clamp_value = data.get("clamp_threshold", _clamp_value)
        _video_clamp_threshold = data.get("video_clamp_threshold", _video_clamp_threshold)
        _black_frame_sec = data.get("black_frame_sec", _black_frame_sec)
        _censor_subs = data.get("censor_subs", _censor_subs)
        _action_log(f"📂 加载配置: 轨道={_track_values} 夹帧={_clamp_value} 黑帧={_black_frame_sec}s")
    except Exception as e:
        _action_log(f"⚠ 读取配置失败: {e}")

# ═══════════════════════════════════════════
# 日志系统（统一 log_writer 模块）
# ═══════════════════════════════════════════
from log_writer import get_logger
_log = get_logger("交付自检工具")
_HOSTNAME = socket.gethostname()
_CONFIG_DIR = os.path.expanduser("~/Library/Application Support/交付自检")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")

def _ts():
    return time.strftime("%m-%d %H:%M:%S")

def _action_log(msg: str):
    try:
        _log.ui(f"[{_ts()}] {msg}")
    except Exception:
        pass


# ═══════════════════════════════════════════
# UI 布局
# ═══════════════════════════════════════════
_CHECK_ROW_STYLE = "font-size:13px;color:rgb(220,220,220)"
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

def _section_checkboxes(*check_ids):
    """从 CHECKS 查找指定 ID 生成 CheckBox 列表。
    自动区分：run_fn 有效的 → 正常勾选框，run_fn=None → 灰色 disabled。
    ID 不存在 → 红色错误标记。
    """
    widgets = []
    for cid in check_ids:
        check = next((c for c in CHECKS if c["id"] == cid), None)
        if check is None:
            _action_log(f"_section_checkboxes: 未知 check_id '{cid}'")
            widgets.append(ui.Label({"Text": f"?{cid}",
                "StyleSheet": "color:red;font-size:12px", "Weight": 0}))
            continue
        if check.get("run_fn") is None:
            widgets.append(_disabled_cb(check["chk_id"], check["section"]))
        else:
            widgets.append(_cb(check["chk_id"], check["section"]))
    return widgets

def _build_group_rows(group_name, extras=None):
    """从 CHECKS 自动生成一个分组的所有 CheckBox。
    
    group_name: 分组名，extras: [额外控件...] — 追加到行末尾
    Returns: [HGroup] — 一行
    """
    extras = extras or []
    group_checks = [c for c in CHECKS if c.get("group") == group_name]
    if not group_checks:
        return []
    
    widgets = [
        *_section_checkboxes(*[c["id"] for c in group_checks]),
        *extras,
    ]
    return [ui.HGroup({"Spacing": 6, "Weight": 0}, widgets)]

# ── 特殊控件常量（已迁移到「配置」弹窗）──

window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # ── 上半区：检查选项 + 开始按钮（左 2/3）| AI校对（右 1/3）──
        ui.HGroup({"Spacing": 8, "Weight": 0}, [

            # ====== 左区：原始检查面板 ======
            ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.Label({"ID": "lbl_check_title", "Text": "常规检查",
                      "StyleSheet": "font-size:13px;font-weight:bold;color:#ccc",
                      "Weight": 0, "Alignment": {"AlignHCenter": True}}),
            ui.HGroup({"Spacing": 10, "Weight": 0}, [
                # 最左：5 个分组开关
                ui.VGroup({"Spacing": 2, "Weight": 0}, list(
                    ui.Button({"ID": f"{BTN_TOGGLE_GROUP}{gn}", "Text": gn,
                               "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                               "MinimumSize": [44, 22]})
                    for gn in GROUP_ORDER
                )),

                # 左侧：检查选项
                ui.VGroup({"Spacing": 2, "Weight": 0}, [
                *_build_group_rows("工程"),
                *_build_group_rows("视频"),
                *_build_group_rows("音频"),
                *_build_group_rows("字幕"),
                *_build_group_rows("色彩"),
                ]),

                ui.HGap({"Weight": 1}),

                # 开始检查 + 配置
                ui.VGroup({"Spacing": 4, "Weight": 0}, [
                    ui.Button({"ID": BTN_START, "Text": "开始检查",
                               "StyleSheet": BTN_PRIMARY, "Weight": 0,
                               "MinimumSize": [100, 95]}),
                    ui.Button({"ID": BTN_CONFIG, "Text": "配置",
                               "StyleSheet": BTN_STYLE, "Weight": 0,
                               "MinimumSize": [100, 20]}),
                ]),
            ]),
            ]),  # 结束左区 VGroup

            ui.VGroup({"Weight": 0, "MinimumSize": [10, 0]}, [
                ui.Label({"Text": "", "Weight": 0.03}),
                ui.Label({"Text": "", "Weight": 0.94,
                          "MinimumSize": [1, 0],
                          "StyleSheet": "background-color:rgba(160,160,160,0.55);"}),
                ui.Label({"Text": "", "Weight": 0.03}),
            ]),

            # ====== 右区：AI校对面板 ======
            ui.VGroup({"Spacing": 4, "Weight": 0, "MinimumSize": [220, 0]}, [
                ui.Label({"ID": "lbl_ai_title", "Text": "AI 字幕校对",
                          "StyleSheet": "font-size:13px;font-weight:bold;color:#ccc",
                          "Weight": 0, "Alignment": {"AlignHCenter": True}}),
                ui.Label({"ID": "lbl_ai_hint", "Text": "剧本链接或本地路径:",
                          "StyleSheet": "font-size:11px;color:#888", "Weight": 0}),
                ui.LineEdit({"ID": EDIT_SCRIPT_SRC, "Text": "",
                            "Weight": 0, "PlaceholderText": "飞书链接 / 本地路径"}),
                ui.Label({"ID": "lbl_ai_ep", "Text": "校对集号（如 7 或 7-9）:",
                          "StyleSheet": "font-size:11px;color:#888", "Weight": 0}),
                ui.HGroup({"Spacing": 6, "Weight": 0}, [
                    ui.LineEdit({"ID": EDIT_SCRIPT_EP, "Text": "",
                                "Weight": 0, "PlaceholderText": "7 或 7-9",
                                "MinimumSize": [72, 0]}),
                    ui.Label({"ID": "lbl_ai_sep", "Text": "│",
                              "StyleSheet": "font-size:13px;color:#555",
                              "Weight": 0}),
                    ui.Label({"ID": LBL_SCRIPT_STATUS, "Text": "",
                              "StyleSheet": "font-size:11px;color:#888",
                              "Weight": 0, "WordWrap": True}),
                ]),
                ui.HGroup({"Spacing": 6, "Weight": 0}, [
                    ui.Button({"ID": BTN_VALIDATE_SCRIPT, "Text": "校验剧本",
                              "StyleSheet": BTN_PRIMARY.replace("100", "60"),
                              "Weight": 0, "MinimumSize": [108, 36]}),
                    ui.Button({"ID": BTN_AI_TYPO, "Text": "开始校对",
                              "StyleSheet": BTN_PRIMARY.replace("100", "80"),
                              "Weight": 0, "MinimumSize": [108, 36]}),
                ]),
            ]),

        ]),  # 结束上半区 HGroup

        # ── 结果区：左侧分组 + 右侧数据 ──
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.Label({"ID": "lbl_gate_warn", "Text": "",
                      "StyleSheet": "color:rgb(220,180,80);font-size:13px;padding:6px 10px",
                      "Weight": 0, "WordWrap": True, "MinimumSize": [0, 48]}),
        ]),
        ui.HGroup({"Spacing": 4, "Weight": 1.0}, [
            ui.Tree({"ID": GROUP_TREE, "Weight": 0,
                     "Events": {"ItemClicked": True},
                     "Indentation": 0,
                     "RootIsDecorated": False,
                     "MinimumSize": [110, 0]}),
            ui.Tree({"ID": TREE_RESULT, "Weight": 1.0,
                     "Events": {"ItemClicked": True, "ItemDoubleClicked": True}}),
        ]),

        # ── 底栏 ──
        ui.VGroup({"Spacing": 2, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Label({"ID": HINT_LB, "Text": "请点击「开始检查」",
                          "StyleSheet": "color:rgb(130,130,130);font-size:10px", "Weight": 0,
                          "MinimumSize": [260, 16]}),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"裁缝老师的达芬奇插件工坊 ✂️ | v{version_string()}",
                          "StyleSheet": "color:rgb(100,100,100);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": "交付自检工具",
    "ID": WIN_ID,
    "Geometry": [800, 100, 900, 520],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# ═══════════════════════════════════════════
# 初始状态
# ═══════════════════════════════════════════
itm[BTN_START].Enabled = False
itm[BTN_AI_TYPO].Enabled = False
itm[BTN_VALIDATE_SCRIPT].Enabled = False
itm[EDIT_SCRIPT_SRC].Text = ""

# Tree 表头
tree = itm[TREE_RESULT]
_setup_tree_header(tree)

# 左侧导航 Tree — 检查时动态填充
group_tree = itm[GROUP_TREE]
_cached_sections = []

# ═══════════════════════════════════════════
# Tree 渲染
# ═══════════════════════════════════════════

def _render_group(group_name, sections, tree):
    """渲染一个 group 或 subgroup 的检查结果到右侧 Tree"""
    tree.Clear()
    _setup_tree_header(tree)
    # 判断是 group 还是 subgroup
    all_sg = sorted(set(c.get("subgroup", c.get("group", "")) for c in CHECKS if c.get("group") == group_name))
    if all_sg:
        # 是 group → 渲染其下所有 subgroup 的行
        for sg in all_sg:
            secs = [s for s in sections if s.get("subgroup") == sg]
            for sec in secs:
                for row_data in sec["rows"]:
                    row = tree.NewItem()
                    _set_row(row, row_data)
                    tree.AddTopLevelItem(row)
    else:
        # 是 subgroup → 只渲染该子类
        secs = [s for s in sections if s.get("subgroup") == group_name]
        for sec in secs:
            for row_data in sec["rows"]:
                row = tree.NewItem()
                _set_row(row, row_data)
                tree.AddTopLevelItem(row)


# ═══════════════════════════════════════════
# 配置弹窗（注册表驱动 — 加/删/调顺序只改 CONFIG_SECTIONS）
# ═══════════════════════════════════════════

# ── 配置项注册表（顺序 = UI 从上到下）──
# 加新项：末尾加一个 dict（id / label / type），然后补对应的 _build_xxx 和 _save_xxx
# 调顺序：移动 dict 位置
# 删项：删 dict + 删对应的 _build_xxx / _save_xxx
CONFIG_SECTIONS = [
    {
        "id": "track_count",
        "label": "轨道数量预设",
        "type": "track_preset",
    },
    {
        "id": "clamp_threshold",
        "label": "字幕时长阈值",
        "type": "clamp_threshold",
    },
    {
        "id": "video_clamp_threshold",
        "label": "视频夹帧阈值",
        "type": "video_clamp_threshold",
    },
    {
        "id": "black_frame_sec",
        "label": "黑帧时长阈值",
        "type": "black_frame_sec",
    },
    {
        "id": "censor_system_subs",
        "label": "系统词典",
        "type": "censor_system_subs",
    },
    {
        "id": "censor_personal",
        "label": "个人词典",
        "type": "censor_personal",
    },
]

# ── 各 type 的 UI 构建函数 → [widget, ...] ──
def _build_track_preset():
    return [
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Label({"Text": "字幕", "StyleSheet": "color:rgb(150,150,150);font-size:13px",
                      "Weight": 0, "MinimumSize": [28, 22]}),
            ui.LineEdit({"ID": "cfg_sub", "Text": str(_track_values[0]),
                         "MaximumSize": [35, 22], "Weight": 0}),
            ui.Label({"Text": "视频", "StyleSheet": "color:rgb(150,150,150);font-size:13px",
                      "Weight": 0, "MinimumSize": [28, 22]}),
            ui.LineEdit({"ID": "cfg_vid", "Text": str(_track_values[1]),
                         "MaximumSize": [35, 22], "Weight": 0}),
            ui.Label({"Text": "音频", "StyleSheet": "color:rgb(150,150,150);font-size:13px",
                      "Weight": 0, "MinimumSize": [28, 22]}),
            ui.LineEdit({"ID": "cfg_aud", "Text": str(_track_values[2]),
                         "MaximumSize": [35, 22], "Weight": 0}),
        ]),
    ]

def _build_clamp_threshold():
    return [
        ui.HGroup({"Spacing": 6, "Weight": 0}, [
            ui.LineEdit({"ID": "cfg_clamp", "Text": str(_clamp_value),
                         "MaximumSize": [45, 22], "Weight": 0}),
            ui.Label({"Text": "帧（≤此值判定为过短/夹帧）",
                      "StyleSheet": "color:rgb(140,140,140);font-size:12px", "Weight": 0}),
        ]),
    ]

def _build_video_clamp_threshold():
    return [
        ui.HGroup({"Spacing": 6, "Weight": 0}, [
            ui.LineEdit({"ID": "cfg_vid_clamp", "Text": str(_video_clamp_threshold),
                         "MaximumSize": [45, 22], "Weight": 0}),
            ui.Label({"Text": "帧（≤此值判定为视频夹帧）",
                      "StyleSheet": "color:rgb(140,140,140);font-size:12px", "Weight": 0}),
        ]),
    ]

def _build_black_frame_sec():
    return [
        ui.HGroup({"Spacing": 6, "Weight": 0}, [
            ui.LineEdit({"ID": "cfg_black_sec", "Text": str(int(_black_frame_sec)),
                         "MaximumSize": [35, 22], "Weight": 0}),
            ui.Label({"Text": "秒（≥此值判定为大段黑场）",
                      "StyleSheet": "color:rgb(140,140,140);font-size:12px", "Weight": 0}),
        ]),
    ]

def _build_censor_system_subs():
    return [
        ui.VGroup({"Spacing": 3, "Weight": 0}, [
            ui.HGroup({"Spacing": 10, "Weight": 0}, [
                ui.CheckBox({"ID": "cfg_csub_cn", "Text": "中文词库 (4.0k词)",
                             "StyleSheet": "color:rgb(200,200,200);font-size:12px",
                             "Weight": 0, "Checked": True}),
                ui.CheckBox({"ID": "cfg_csub_en", "Text": "英文词库 (2.7k词)",
                             "StyleSheet": "color:rgb(200,200,200);font-size:12px",
                             "Weight": 0, "Checked": True}),
            ]),
            ui.HGroup({"Spacing": 10, "Weight": 0}, [
                ui.CheckBox({"ID": "cfg_csub_bw", "Text": "通用违禁词 (1.6k词)",
                             "StyleSheet": "color:rgb(200,200,200);font-size:12px",
                             "Weight": 0, "Checked": True}),
                ui.CheckBox({"ID": "cfg_csub_sms", "Text": "短信违禁词 (2.3k词)",
                             "StyleSheet": "color:rgb(200,200,200);font-size:12px",
                             "Weight": 0, "Checked": True}),
            ]),
        ]),
    ]

def _build_censor_personal():
    return [
        ui.HGroup({"Spacing": 6, "Weight": 0}, [
            ui.Button({"ID": "cfg_edit_censor", "Text": "在 Finder 中打开",
                       "StyleSheet": BTN_STYLE_SM, "Weight": 0}),
            ui.Label({"Text": "右键 CSV → 打开方式 → WPS Office 编辑",
                      "StyleSheet": "color:rgb(140,140,140);font-size:12px", "Weight": 0}),
        ]),
    ]

_SECTION_BUILDERS = {
    "track_preset":             _build_track_preset,
    "clamp_threshold":          _build_clamp_threshold,
    "video_clamp_threshold":    _build_video_clamp_threshold,
    "black_frame_sec":          _build_black_frame_sec,
    "censor_system_subs":       _build_censor_system_subs,
    "censor_personal":          _build_censor_personal,
}


def _show_config_dialog():
    """打开配置窗口"""
    CONFIG_WIN_ID = "com.myjc.delivery_checker_config"

    config_disp = bmd.UIDispatcher(fu.UIManager)

    # ── 从注册表生成布局 ──
    # 节间间距（section 与 section 之间）
    _SECTION_GAP = 8
    body_widgets = [
        ui.Label({"Text": "配置", "StyleSheet": "font-size:15px;font-weight:bold;color:rgb(220,220,220)",
                  "Weight": 0}),
    ]
    for section in CONFIG_SECTIONS:
        sec_widgets = [ui.Label({
            "Text": section["label"],
            "StyleSheet": "font-size:13px;font-weight:bold;color:rgb(220,220,220)",
            "Weight": 0,
        })]
        builder = _SECTION_BUILDERS.get(section["type"])
        if builder:
            sec_widgets.extend(builder())
        else:
            sec_widgets.append(ui.Label({
                "Text": f"(未知类型: {section['type']})",
                "StyleSheet": "color:red;font-size:12px", "Weight": 0,
            }))
        # 每节包成独立 VGroup，节内紧凑
        body_widgets.append(ui.VGroup({"Spacing": 2, "Weight": 0}, sec_widgets))

    config_layout = [
        ui.VGroup({"Spacing": 0}, [
            ui.VGroup({"Spacing": _SECTION_GAP, "Weight": 0}, body_widgets),
            ui.VGap({"Weight": 1}),

            # ── 按钮（底部居中）──
            ui.HGroup({"Spacing": 10, "Weight": 0}, [
                ui.HGap({"Weight": 1}),
                ui.Button({"ID": "cfg_reset", "Text": "恢复默认",
                           "StyleSheet": BTN_STYLE, "Weight": 0}),
                ui.Button({"ID": "cfg_cancel", "Text": "取消",
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
        "Geometry": [820, 120, 420, 430],
        "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
    }, config_layout)

    cfg = config_dlg.GetItems()

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

    # ── 保存（按类型分发）──
    def _save(ev):
        global _clamp_value, _track_values, _censor_subs, _video_clamp_threshold
        msg_parts = []

        for section in CONFIG_SECTIONS:
            t = section["type"]
            if t == "clamp_threshold":
                try:
                    cv = int(cfg["cfg_clamp"].Text)
                    if cv < 1:
                        _action_log("⚠ 时长阈值不能小于1, 放弃保存")
                        return
                except ValueError:
                    _action_log(f"⚠ 时长阈值无效: {cfg['cfg_clamp'].Text}, 放弃保存")
                    return
                old = _clamp_value
                _clamp_value = cv
                if old != cv:
                    msg_parts.append(f"阈值 {old}→{cv}")

            elif t == "video_clamp_threshold":
                global _video_clamp_threshold
                try:
                    cv = int(cfg["cfg_vid_clamp"].Text)
                    if cv < 1:
                        _action_log("⚠ 视频夹帧阈值不能小于1, 放弃保存")
                        return
                except ValueError:
                    _action_log(f"⚠ 视频夹帧阈值无效: {cfg['cfg_vid_clamp'].Text}, 放弃保存")
                    return
                old = _video_clamp_threshold
                _video_clamp_threshold = cv
                if old != cv:
                    msg_parts.append(f"视频夹帧 {old}→{cv}")

            elif t == "black_frame_sec":
                try:
                    cv = float(cfg["cfg_black_sec"].Text)
                    if cv <= 0:
                        _action_log("⚠ 黑帧阈值必须大于0, 放弃保存")
                        return
                except ValueError:
                    _action_log(f"⚠ 黑帧阈值无效: {cfg['cfg_black_sec'].Text}, 放弃保存")
                    return
                old = _black_frame_sec
                _black_frame_sec = cv
                if old != cv:
                    msg_parts.append(f"黑帧 {old}s→{cv}s")

            elif t == "track_preset":
                old = _track_values.copy()
                try:
                    sv = int(cfg["cfg_sub"].Text)
                    vv = int(cfg["cfg_vid"].Text)
                    av = int(cfg["cfg_aud"].Text)
                except Exception:
                    _action_log("⚠ 轨道数量读取失败, 放弃保存")
                    return
                _track_values = [sv, vv, av]
                if old != _track_values:
                    msg_parts.append(f"轨道 {old}→{_track_values}")

            elif t == "censor_system_subs":
                old_subs = _censor_subs.copy()
                for cbox_id, key in SUB_CBOX_MAP:
                    try:
                        _censor_subs[key] = cfg[cbox_id].Checked
                    except Exception:
                        pass
                if old_subs != _censor_subs:
                    msg_parts.append(f"词典 {old_subs}→{_censor_subs}")

            elif t == "censor_personal":
                pass  # 编辑按钮独立处理

        if msg_parts:
            _action_log("⚙ 配置保存: " + ", ".join(msg_parts))
        else:
            _action_log("⚙ 配置保存: 无变更")
        _save_config_to_file()
        config_dlg.Hide()
        config_disp.ExitLoop()

    # ── 编辑违禁词（打开系统文本编辑）──
    censor_path = os.path.join(_SCRIPT_DIR, "dicts", "短剧违禁词表.csv")
    def _edit_censor(ev):
        import subprocess
        from check_core import clear_censor_cache
        clear_censor_cache(censor_path)
        subprocess.Popen(["open", "-R", censor_path])
        _action_log("📝 在 Finder 中定位个人词典")

    config_dlg.On["cfg_edit_censor"].Clicked = _edit_censor
    config_dlg.On["cfg_save"].Clicked = _save
    config_dlg.On["cfg_cancel"].Clicked = lambda ev: config_disp.ExitLoop()
    config_dlg.On["cfg_reset"].Clicked = lambda ev: _reset_defaults()

    def _reset_defaults():
        global _track_values, _clamp_value, _video_clamp_threshold, _black_frame_sec, _censor_subs
        _track_values = [DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS]
        _clamp_value = DEFAULT_CLAMP_THRESHOLD
        _video_clamp_threshold = 2
        _black_frame_sec = DEFAULT_BLACK_FRAME_SEC
        _censor_subs = {"base": True, "en": True, "bw": True, "bw_sms": True}
        _save_config_to_file()
        try:
            cfg["cfg_sub"].Text = str(_track_values[0])
            cfg["cfg_vid"].Text = str(_track_values[1])
            cfg["cfg_aud"].Text = str(_track_values[2])
            cfg["cfg_clamp"].Text = str(_clamp_value)
            cfg["cfg_vid_clamp"].Text = str(_video_clamp_threshold)
            cfg["cfg_black_sec"].Text = str(int(_black_frame_sec))
            for cbox_id, key in SUB_CBOX_MAP:
                cfg[cbox_id].Checked = _censor_subs.get(key, True)
        except Exception:
            pass
        _action_log("🔄 配置已恢复默认")
    config_dlg.On[CONFIG_WIN_ID].Close = lambda ev: config_disp.ExitLoop()

    _action_log("⚙ 打开配置窗口")
    config_dlg.Show()
    config_disp.RunLoop()
    config_dlg.Hide()


# ═══════════════════════════════════════════
# 结果处理
# ═══════════════════════════════════════════
#
# 数据流 Schema（全链路）：
#   check_core._make_result()
#       → {status, track, timecode, detail, reason, is_summary}
#           ↓ _process_result() + FIELD_TO_COLUMN
#       → {icon, track, tc, msg, reason}
#           ↓ _start_check() 分组
#       → section: {group, title, summary, rows, all_ok}
#           ↓ _render_group() 渲染
#       → Tree:  1. Group ◆ Check → ❌ 问题 | 建议
#
# 扩展规则：
#   - 加 check_core 字段 → _make_result + FIELD_TO_COLUMN + COLUMNS（3处）
#   - 改字段映射 → 只改 FIELD_TO_COLUMN
#   - 改列宽/顺序/显隐 → 只改 COLUMNS
#
# detail/reason 语义约定（2026-05-10 沉淀）：
#   detail（→"问题"列）= 问题的简洁描述，不含"应为"/"建议"等
#   reason（→"建议"列）= 修复方向或原因，可为空
#   汇总行（is_summary）≠ 详情行（detail），禁止重复

def _process_result(r, rows_list):
    """处理单条检查结果，通过 FIELD_TO_COLUMN 映射到 Tree 列。
    返回 (is_fail, is_warn, is_pass)，三者互斥"""
    if r["status"] == "pass":
        return False, False, True

    icon = "❌" if r["status"] == "fail" else "⚠"
    cols = FIELD_TO_COLUMN
    rows_list.append({
        cols["track"]:    r.get("track", ""),
        cols["timecode"]: r.get("timecode", ""),
        cols["detail"]:   f"{icon} | {r.get('detail', '')}",
        cols["reason"]:   r.get("reason", ""),
    })
    _action_log(r.get("detail", ""))
    return r["status"] == "fail", r["status"] == "warn", False


# ═══════════════════════════════════════════
# AI 校对
# ═══════════════════════════════════════════

def _run_ai_typo():
    """独立入口：AI 字幕校对，含多道门。"""
    global _checking
    if _checking:
        return
    _checking = True
    itm[BTN_AI_TYPO].Enabled = False
    itm[BTN_VALIDATE_SCRIPT].Enabled = False
    itm[BTN_START].Enabled = False

    def _stop(msg):
        itm[HINT_LB].Text = msg
        _action_log(msg)

    try:
        from llm_typo_check import check_typos
        from script_parser import parse_script, match_timeline

        # ═══ 门0: 有空字幕？ ═══
        resolve = bmd.scriptapp("Resolve")
        timeline = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        if not timeline:
            return _stop("❌ 未找到当前时间线")
        entries = []
        for ti in range(1, timeline.GetTrackCount("subtitle") + 1):
            for it in (timeline.GetItemListInTrack("subtitle", ti) or []):
                try:
                    entries.append(it.GetName() or "")
                except Exception:
                    pass
        if not entries:
            return _stop("⚠ 当前时间线无字幕，跳过校对")
        _action_log(f"📝 字幕: {len(entries)} 条")

        # ═══ 门1: 剧本读得通？ ═══
        src = itm[EDIT_SCRIPT_SRC].Text.strip()
        try:
            parsed = parse_script(src)
            _action_log(f"📖 剧本解析完成: {len(parsed.get('episodes',{}))} 集")
        except Exception as e:
            return _stop(f"❌ 剧本解析失败: {e}")

        # ═══ 门2: 集号找得到？ ═══
        tl_name = timeline.GetName()
        ep_input = itm[EDIT_SCRIPT_EP].Text.strip()
        try:
            ctx = match_timeline(parsed, tl_name, ep_override=ep_input or None)
            _action_log(f"🎯 匹配集号: EP{ctx['episode']} ({'手动' if ep_input else '自动'})")
        except Exception as e:
            return _stop(f"❌ 集号匹配失败: {e}")

        # ═══ 门3: 有对话内容？ ═══
        if not ctx.get("lines"):
            _action_log(f"⚠ 第 {ctx['episode']} 集剧本无对话行，校对可能不准确")
        if not ctx.get("characters"):
            _action_log("⚠ 未提取到人物名，人名校验将跳过")

        # ═══ LLM 校对 ═══
        itm[HINT_LB].Text = "AI 校对中..."
        _action_log(f"🤖 LLM 校对开始 ({len(entries)}字幕 vs {len(ctx.get('lines',[]))}行剧本)")
        result = check_typos(entries, ctx.get("characters", []), ctx.get("lines", []))
        if result.get("error"):
            return _stop(f"❌ 校对失败: {result.get('error')}")
        if result.get("error") == "all_failed":
            return _stop("❌ 所有模型均不可用，请检查 API key 或网络")

        corrections = result.get("corrections", [])
        provider = result.get("provider", "?")
        model = result.get("model", "?")

        tree = itm[TREE_RESULT]
        tree.Clear()
        _setup_tree_header(tree)

        if not corrections:
            itm[HINT_LB].Text = f"✅ 未发现错别字  ({provider}/{model})"
            _action_log(f"✅ 校对完成: 0处错别字 ({provider}/{model})")
            return

        from timecode import SMPTE
        fps = float(timeline.GetSetting("timelineFrameRate") or 25)
        smpte = SMPTE(); smpte.fps = fps; smpte.df = False

        for c in corrections:
            row = tree.NewItem()
            row.Text[1] = f"字幕[{c['index']}]"
            row.Text[2] = f"❌ {c['original']} → {c['correction']}"
            row.Text[3] = c.get("reason", "")
            tree.AddTopLevelItem(row)

        itm[HINT_LB].Text = (
            f"🔍 发现 {len(corrections)} 处错别字"
            f"  |  模型: {provider}/{model}"
        )
        _action_log(f"🔍 发现 {len(corrections)} 处错别字 ({provider}/{model})")

    except Exception as e:
        _action_log(f"💥 AI校对崩溃: {e}")
        itm[HINT_LB].Text = f"❌ 校对异常: {e}"

    finally:
        _checking = False
        itm[BTN_VALIDATE_SCRIPT].Enabled = _SCRIPT_SRC_VALID
        itm[BTN_AI_TYPO].Enabled = _SCRIPT_CONFIRMED
        itm[BTN_START].Enabled = True


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

    try:
        any_checked = any(
            itm[c["chk_id"]].Checked for c in CHECKS if c.get("run_fn")
        )
        if not any_checked:
            _action_log("⚠ 未选择任何检查项")
            return

        _action_log(f"▶ 开始检查 (轨道模板={_track_values}, 夹帧阈值={_clamp_value})")
        itm[HINT_LB].Text = "检查中..."

        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            _action_log("❌ 未连接达芬奇")
            return

        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            _action_log("❌ 未打开项目")
            return

        timeline = project.GetCurrentTimeline()
        if not timeline:
            _action_log("❌ 未打开时间线")
            return

        fps = float(project.GetSetting("timelineFrameRate"))

        # IO 范围：有则只扫 IO 内
        io_range = None
        try:
            marks = timeline.GetMarkInOut()
            if marks and marks.get("video"):
                io_in = marks["video"].get("in")
                io_out = marks["video"].get("out")
                if io_in is not None and io_out is not None and io_out > io_in:
                    io_range = (io_in, io_out)
                    _action_log(f"IO 选区: {io_in} → {io_out}")
        except Exception:
            pass

        _action_log(f"项目: {project.GetName()}")
        _action_log(f"时间线: {timeline.GetName()}")
        _action_log(f"帧率: {fps} fps")

        # ── 四道门：结构不对则跳过整组检查（仅当用户勾选了对应结构检查才生效）──
        # Gate 0: 起始时码归零（仅当勾了「时间线」检查）
        gate0_ok = not itm[CHK_TIMELINE].Checked or (timeline.GetStartFrame() == 0)
        gate_warnings = []
        if not gate0_ok:
            _action_log("⚠ 起始时码非零，后续所有检查已跳过，请归零时码后重新运行")
            gate_warnings.append("⚠ 起始时码非 00:00:00:00，后续所有检查已跳过，请归零时码后重新运行")

        sub_count = timeline.GetTrackCount("subtitle")
        vid_count = timeline.GetTrackCount("video")
        aud_count = timeline.GetTrackCount("audio")

        def _all_enabled(tt, count):
            for ti in range(1, count + 1):
                try:
                    if not timeline.GetIsTrackEnabled(tt, ti): return False
                except: pass
            return True

        aud_names_ok = True
        if aud_count == DEFAULT_AUDIO_TRACKS:
            for idx, preset in enumerate(AUDIO_TRACK_PRESET):
                if timeline.GetTrackName("audio", idx + 1) != preset["name"]:
                    aud_names_ok = False; break

        gates = {}
        if itm[CHK_TRACK].Checked:
            # 用户勾了轨道结构 → 启用门判断
            gates["subtitle"] = gate0_ok and sub_count == DEFAULT_SUBTITLE_TRACKS and _all_enabled("subtitle", sub_count)
            gates["video"]    = gate0_ok and vid_count == DEFAULT_VIDEO_TRACKS and _all_enabled("video", vid_count)
            gates["audio"]    = gate0_ok and aud_count == DEFAULT_AUDIO_TRACKS and _all_enabled("audio", aud_count) and aud_names_ok
        else:
            gates["subtitle"] = gate0_ok
            gates["video"]    = gate0_ok
            gates["audio"]    = gate0_ok

        # 三门合一：任意一门不通 → 后续所有检查跳过
        gate_all_ok = gate0_ok and all(gates.values())

        if itm[CHK_TRACK].Checked:
            failed_gates = []
            for gate, label in [("video","视频轨道"), ("audio","音频轨道"), ("subtitle","字幕轨道")]:
                if not gates[gate]:
                    failed_gates.append(label)
                    _action_log(f"⚠ {label}结构异常")
            if failed_gates:
                gate_warnings.append(f"⚠ {'、'.join(failed_gates)}结构异常，所有检查已跳过，请先修复基础问题后重新运行")

        if gate_warnings:
            itm["lbl_gate_warn"].Text = "\n".join(gate_warnings)
            itm["lbl_gate_warn"].Visible = True
        else:
            itm["lbl_gate_warn"].Text = ""
            itm["lbl_gate_warn"].Visible = False

        # 按需预加载：只加载会实际运行的检查需要的轨道
        # （门关闭 → 对应检查跳过，轨道也不用预加载）
        needed = set()
        for check in CHECKS:
            g = check.get("gate", "")
            if check.get("run_fn") and itm[check["chk_id"]].Checked:
                if not g or gate_all_ok:
                    needed.update(check.get("tracks", []))
        preload_timeline_items(timeline, track_types=list(needed) if needed else None)

        # 清空结果
        tree.Clear()
        _setup_tree_header(tree)

        has_failures = False
        has_warnings = False
        pass_count = 0
        fail_count = 0
        warn_count = 0
        sections = []

        # 按注册表顺序执行检查
        for check in CHECKS:
            if not check.get("run_fn"):
                continue
            if not itm[check["chk_id"]].Checked:
                continue
            # 门关闭 → 跳过（三门合一：任一不通全停）
            g = check.get("gate", "")
            if g and not gate_all_ok:
                _action_log(f"⏭ {check['section']}检查跳过（门未通过）")
                continue

            _action_log(f"── {check['section']}检查 ──")
            try:
                all_results = list(check["run_fn"](
                    timeline=timeline, fps=fps, project=project,
                    personal_enabled=itm[CHK_CENSOR_PERSONAL].Checked,
                    io_range=io_range))
            except Exception:
                import traceback
                _action_log(f"❌ {check['section']}检查崩溃: {traceback.format_exc()}")
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
                _action_log(f"⚠ {check['section']} 检查缺少 is_summary=True 汇总行 — 请给 check_core 函数加上")

            for r in rest:
                is_fail, is_warn, is_pass = _process_result(r, section_rows)
                if is_pass:
                    pass_count += 1
                    section_pass += 1
                elif is_fail:
                    fail_count += 1
                    has_failures = True
                elif is_warn:
                    warn_count += 1
                    has_warnings = True

            all_ok = not section_rows and section_pass > 0
            sections.append({
                "group": check.get("group", ""),
                "subgroup": check.get("subgroup", check.get("group", "")),
                "title": check["section"],
                "summary": summary_text,
                "rows": section_rows,
                "all_ok": all_ok,
            })

        # 路径检测失败 → 加入门警告（路径 + 脱机任一项失败全停）
        for s in sections:
            if s["title"] == "路径检测" and not s["all_ok"]:
                gate_warnings.append(f"⚠ 媒体池存在非 SMB 路径文件，详见下方检测结果")

        # 缓存 sections，重建左侧导航（只保留有数据的）
        global _cached_sections
        _cached_sections = sections
        group_tree.Clear()
        ghdr2 = group_tree.NewItem()
        ghdr2.Text[0] = "分类"
        group_tree.SetHeaderItem(ghdr2)

        first_group = None
        for name in GROUP_ORDER:
            # 收集该组的 subgroup
            subgroups = []
            for c in CHECKS:
                if c.get("group") == name:
                    sg = c.get("subgroup", name)
                    if sg not in subgroups:
                        subgroups.append(sg)

            # 检查有没有数据
            has_group_data = any(s.get("group") == name and s["rows"] for s in sections)
            if not has_group_data:
                continue
            if first_group is None:
                first_group = name

            # 大类行
            gi = group_tree.NewItem()
            gi.Text[0] = name
            group_tree.AddTopLevelItem(gi)

            # 子类行
            for sg in subgroups:
                if any(s.get("subgroup") == sg and s["rows"] for s in sections):
                    child = group_tree.NewItem()
                    child.Text[0] = f"  · {sg}"
                    group_tree.AddTopLevelItem(child)

        if first_group:
            _render_group(first_group, sections, tree)

        # 总结 → 左下角状态栏
        elapsed_ms = int((time.time() - _start_time) * 1000)
        jump_hint = "💡 点击结果行可跳转到对应时间码"
        if has_failures:
            hint = f"❌ 未通过 {fail_count} 项"
            if has_warnings:
                hint += f"，⚠ {warn_count} 项警告"
            hint += f"  |  {jump_hint}"
            _action_log("❌ 检查未通过 — 请修复上述问题")
        elif has_warnings:
            hint = f"⚠ {warn_count} 项警告  |  {jump_hint}"
            _action_log("⚠ 有警告 — 请检查")
        else:
            hint = f"✅ 通过  |  {jump_hint}"
            _action_log("✅ 所有检查通过")
        itm[HINT_LB].Text = hint

        # ── 结果持久化 ──
        try:
            _log.ops({
                "t": time.time(),
                "project": project.GetName(),
                "timeline": timeline.GetName(),
                "fps": fps,
                "has_failures": has_failures,
                "has_warnings": has_warnings,
                "pass": pass_count, "fail": fail_count, "warn": warn_count,
                "sections": [
                    {"group": s["group"], "section": s["section"],
                     "all_ok": s["all_ok"],
                     "fails": [{k: v for k, v in r.items() if not k.startswith("_")}
                               for r in s.get("rows", []) if "❌" in str(r.get("detail", ""))]}
                    for s in sections
                ],
            })
        except Exception:
            pass

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _action_log(f"❌ 检查崩溃: {e}")
        _action_log(tb)
        itm[HINT_LB].Text = f"❌ 检查崩溃: {e}"
    finally:
        _checking = False
        itm[BTN_START].Enabled = True
        itm[BTN_VALIDATE_SCRIPT].Enabled = _SCRIPT_SRC_VALID
        itm[BTN_AI_TYPO].Enabled = _SCRIPT_CONFIRMED


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
    _load_config_from_file()
    try:
        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            _action_log("⚠ 未连接达芬奇")
            itm[HINT_LB].Text = "⚠ 请先启动 DaVinci Resolve"
            return

        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            _action_log("⚠ 未打开项目")
            itm[HINT_LB].Text = "⚠ 请先打开一个项目"
            return

        timeline = project.GetCurrentTimeline()
        if not timeline:
            _action_log("⚠ 未打开时间线")
            itm[HINT_LB].Text = "⚠ 当前项目没有时间线"
            return

        fps = float(project.GetSetting("timelineFrameRate"))
        _action_log(f"连接达芬奇: 成功")
        _action_log(f"项目: {project.GetName()}")
        _action_log(f"时间线: {timeline.GetName()}  |  {fps} fps")
        itm[BTN_START].Enabled = True
        itm[HINT_LB].Text = "请点击「开始检查」"

    except Exception as e:
        _action_log(f"❌ 初始化失败: {e}")
        itm[HINT_LB].Text = f"❌ 初始化失败: {e}"


def _on_close(ev):
    global _checking
    _checking = False
    _action_log("窗口关闭")
    disp.ExitLoop()



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
dlg.On[BTN_START].Clicked = lambda ev: _start_check()
dlg.On[BTN_CONFIG].Clicked = lambda ev: _show_config_dialog()
dlg.On[BTN_AI_TYPO].Clicked = lambda ev: _run_ai_typo()
dlg.On[BTN_VALIDATE_SCRIPT].Clicked = lambda ev: _confirm_script(ev)

# 剧本链接输入框变化时校验格式
_SCRIPT_SRC_VALID = False
_SCRIPT_CONFIRMED = False
def _validate_script_src(ev):
    global _SCRIPT_SRC_VALID, _SCRIPT_CONFIRMED
    src = itm[EDIT_SCRIPT_SRC].Text.strip()
    ok = bool(src) and any(src.startswith(p) for p in (
        "https://", "http://", "/Volumes/", "smb://", "~/", "/"))
    if "feishu.cn" in src or "docs.qq.com" in src:
        ok = ok and len(src) > 30
    _SCRIPT_SRC_VALID = ok
    _SCRIPT_CONFIRMED = False
    itm[LBL_SCRIPT_STATUS].Text = ""
    itm[BTN_VALIDATE_SCRIPT].Enabled = ok and not _checking
    itm[BTN_AI_TYPO].Enabled = False
    if not ok and src:
        _action_log(f"⚠ 剧本链接格式异常: {src[:60]}...")

def _confirm_script(ev):
    """验证剧本：下载+解析+集号匹配（纯 Python，不调 LLM）。"""
    global _SCRIPT_CONFIRMED
    if _checking or not _SCRIPT_SRC_VALID:
        return
    _action_log("🔍 校验剧本...")
    itm[LBL_SCRIPT_STATUS].Text = "🔄 验证中..."
    itm[BTN_VALIDATE_SCRIPT].Enabled = False
    itm[BTN_AI_TYPO].Enabled = False

    try:
        from script_parser import parse_script, match_timeline
        src = itm[EDIT_SCRIPT_SRC].Text.strip()
        parsed = parse_script(src)
        resolve = bmd.scriptapp("Resolve")
        timeline = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        tl_name = timeline.GetName() if timeline else ""
        ep_input = itm[EDIT_SCRIPT_EP].Text.strip()
        ctx = match_timeline(parsed, tl_name, ep_override=ep_input or None)
        _SCRIPT_CONFIRMED = True
        n_lines = len(ctx.get("lines", []))
        n_chars = len(ctx.get("characters", []))
        msg = f"✅ 剧本校验通过 - 第{ctx['episode']}集（{n_lines}行对话,{n_chars}角色）"
        itm[LBL_SCRIPT_STATUS].Text = f"✅ 验证通过 - 第{ctx['episode']}集"
        _action_log(msg)
    except Exception as e:
        _SCRIPT_CONFIRMED = False
        itm[LBL_SCRIPT_STATUS].Text = f"❌ {e}"
        _action_log(f"❌ 剧本校验失败: {e}")
    finally:
        itm[BTN_VALIDATE_SCRIPT].Enabled = _SCRIPT_SRC_VALID and not _checking
        itm[BTN_AI_TYPO].Enabled = _SCRIPT_CONFIRMED and not _checking
dlg.On[EDIT_SCRIPT_SRC].TextChanged = _validate_script_src

# 分组开关事件
def _make_group_toggle(group_name):
    def _toggle(ev):
        group_checks = [c for c in CHECKS if c.get("group") == group_name and c.get("run_fn")]
        if not group_checks:
            return
        all_on = all(itm[c["chk_id"]].Checked for c in group_checks)
        target = not all_on
        for c in group_checks:
            itm[c["chk_id"]].Checked = target
        _action_log(f"{'☑' if target else '☐'} {group_name} 分组 {'全选' if target else '全不选'}")
    return _toggle

for _gn in GROUP_ORDER:
    dlg.On[f"{BTN_TOGGLE_GROUP}{_gn}"].Clicked = _make_group_toggle(_gn)

def _on_group_click(ev):
    """左侧点击 → 子类行(· 前缀)显示该子类，大类行显示全组"""
    item = ev.get("Item")
    if item is None:
        item = group_tree.CurrentItem()
    if item is None:
        return
    text = item.Text[0]
    text_stripped = text.lstrip()
    if text_stripped.startswith("· "):
        _render_group(text_stripped[2:], _cached_sections, tree)
    else:
        _render_group(text, _cached_sections, tree)

dlg.On[GROUP_TREE].ItemClicked = _on_group_click
dlg.On[TREE_RESULT].ItemClicked = _on_result_click
dlg.On[TREE_RESULT].ItemDoubleClicked = _on_result_click
dlg.On[WIN_ID].Show = _on_show
dlg.On[WIN_ID].Close = _on_close


# ═══════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════

def main():
    _action_log("═══ 交付自检 启动 v" + version_string() + " ═══")
    dlg.Show()
    dlg.RecalcLayout()
    _init_connection()
    disp.RunLoop()
    dlg.Hide()
    # os._exit 跳过 C++ 全局析构，避免 fusionscript.so 的
    # ReusePoolManager::~ReusePoolManager SIGSEGV（DaVinci 20.3.2 已知 bug）
    os._exit(0)


if __name__ == "__main__":
    main()
