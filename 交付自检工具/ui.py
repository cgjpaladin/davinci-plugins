# -*- coding: utf-8 -*-
"""
交付自检工具 UI — 外部进程版

绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
使用 fusionscript_loader 连接 Resolve。
"""
import os
import socket
import sys
import subprocess
import time
import traceback
import json
import webbrowser

# 达芬奇官方API目录（macOS 需要手动设置）
import sys as _sys
if _sys.platform == "darwin":
    os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
    os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

# 跨平台数据目录
if _sys.platform == "darwin":
    _DATA_DIR = os.path.expanduser("~/Library/Application Support/交付自检")
else:
    _DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "交付自检")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 个人版: 优先用插件自带 shared/，避免被全局旧版 ../shared 遮蔽
_plugin_shared = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared')
if os.path.isdir(_plugin_shared):
    sys.path.insert(0, _plugin_shared)
# 全局 shared（公司版）作为兜底
_global_shared = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared')
if os.path.isdir(_global_shared):
    sys.path.insert(1, _global_shared)
_smb_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _smb_root not in sys.path and not os.environ.get("WORKBUDDY_PERSONAL"):
    sys.path.insert(0, _smb_root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CENSOR_PERSONAL_CSV = os.path.join(_SCRIPT_DIR, "dicts", "短剧违禁词表.csv")

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
    IS_PERSONAL,
    MANUAL_URL,
)
from check_core import (check_track_structure, check_subtitle_clamping, check_disabled_items,
                          check_black_frames, check_audio_mono, check_timeline_settings,
                          check_through_edits, check_tailboard, check_coloring_markers,
                          check_black_borders, check_speed, check_video_clamping, preload_timeline_items,
                          check_subtitle_glyph, check_subtitle_linebreak, check_subtitle_censor,
                          check_color, check_camera_on_high_tracks, check_audio_color_tracks,
                          _get_smpte, _make_result,
                          check_path_location, check_offline_clips)
from export_debug import export_debug_package
from license_ui import trial_days_left, format_trial

# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════
WIN_ID = "com.myjc.delivery_checker"

# 控件 ID
CHK_TRACK, CHK_SUB_DURATION, CHK_SUB_LINEBREAK, CHK_SUB_GLYPH = \
    "chk_track", "chk_sub_dur", "chk_sub_br", "chk_sub_glyph"
CHK_BLACK, CHK_VIDEO_CLAMP, CHK_BORDER, CHK_SPEED, CHK_MONO, CHK_LOUDNESS, CHK_FRAGMENT, CHK_TIMELINE, CHK_COLOR = \
    "chk_black", "chk_vid_clamp", "chk_border", "chk_speed", "chk_mono", "chk_loudness", "chk_fragment", "chk_timeline", "chk_color"
CHK_CENSOR_SYSTEM, CHK_CENSOR_PERSONAL = "chk_censor_sys", "chk_censor_personal"
CHK_CAMERA = "chk_camera"
CHK_AUDIO_COLOR = "chk_audio_color"
CHK_TAG_MARKERS = "chk_tag_markers"
CHK_PATH = "chk_path"
CHK_OFFLINE = "chk_offline"
CHK_BLACK_FRAME = CHK_BLACK  # 别名
CHK_THROUGH_EDITS = "chk_through_edits"
CHK_TAILBOARD = "chk_tailboard"
BTN_START = "btn_start"
BTN_CONFIG = "btn_config"
BTN_AI_TYPO = "btn_ai_typo"
EDIT_SCRIPT_SRC = "edit_script_src"
_SCRIPT_SRC_PATH = ""  # 真实路径（UI 只显示文件名）
BTN_TOGGLE_GROUP = "btn_toggle_group_"  # + group_name → "btn_toggle_group_工程"
TREE_RESULT = "tree_result"
GROUP_TREE = "group_tree"
BTN_UPDATE = "btn_update"
HINT_LB = "hint_lb"
TRIAL_LB = "trial_lb"
ERR_LB = "err_lb"
BTN_ERR_SEND = "btn_err_send"
BTN_MANUAL = "btn_manual"

# License 状态（main() 中设置，_unlock_ui 等位置需要读取）
_ai_allowed = True

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
GROUP_ORDER = ["工程", "视频", "音频", "色彩"]

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

# ── 设计参数（改皮肤只改这里） ──
from styles import (FONT_H1, FONT_H2, FONT_BODY, FONT_SM, FONT_XS, FONT_DIV, FONT_BOLD,
                    SPACE_NONE, SPACE_TIGHT, SPACE_COMPACT, SPACE_SM, SPACE_NORMAL, SPACE_RELAXED, SPACE_WIDE,
                    SIZE_BTN_H, SIZE_BTN_SM_W, SIZE_BTN_MD_W, SIZE_BTN_LG_W, SIZE_BTN_XL_W, SIZE_BTN_XL_H,
                    SIZE_TOGGLE, SIZE_LINE_H, SIZE_CHECK_W, SIZE_GAP_TINY, SIZE_GAP_SM,
                    PAD_BTN, PAD_PANEL, PAD_PANEL_WIDE, RAD_BTN, RAD_PANEL, DIVIDER_BARS,
                    STYLE_HEADING, STYLE_ACCENT, STYLE_DIM, STYLE_HINT, STYLE_FOOTER, STYLE_DIVIDER,
                    STYLE_CHECK_ROW, STYLE_WARN,
                    BTN_STYLE, BTN_ICON, BTN_STYLE_SM, BTN_PRIMARY, BTN_DANGER)

from config_dialog import _load_api_keys, _save_api_keys, _MASK_PRESETS, _MASK_UNSET, TRIAL_LB, BTN_AI_TYPO, HINT_LB, CONFIG_WIDGETS
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

def _run_fw_check(timeline, fps, **_kw):
    """字幕全半角检测"""
    import re
    fw_pattern = re.compile(r'[\uff00-\uffef]')  # 全角字符范围
    fw_to_hw = str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
        '！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')
    results = []
    for it in (timeline.GetItemListInTrack("subtitle", 1) or []):
        try:
            text = it.GetName() or ""
            fw_chars = fw_pattern.findall(text)
            if fw_chars:
                fixed = text.translate(fw_to_hw)
                if fixed != text:
                    s = _get_smpte(fps)
                    tc = s.gettc(int(it.GetStart()))
                    results.append({"status": "fail", "track": "ST1",
                                    "timecode": tc,
                                    "detail": f"{text} → {fixed}",
                                    "reason": "全角转半角"})
        except Exception:
            pass
    if not results:
        results.append({"status": "pass", "detail": "无全角字符", "is_summary": True})
    return results

def _run_fragment_check(timeline, fps, **_kw):
    """片段状态（启用/禁用）"""
    return check_disabled_items(timeline, fps, io_range=_kw.get("io_range"))

def _run_black_frame_check(timeline, fps, **_kw):
    """黑帧"""
    return check_black_frames(timeline, fps, threshold_sec=_black_frame_sec, io_range=_kw.get("io_range"))

def _run_black_border_check(timeline, fps, **_kw):
    """黑边"""
    return check_black_borders(timeline, project=_kw.get("project"), fps=fps, io_range=_kw.get("io_range"), mask_ratio=_mask_ratio)

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

def _run_tag_markers_check(timeline, fps, **_kw):
    """调色标记"""
    return check_coloring_markers(timeline, project=_kw.get("project"), fps=fps, io_range=_kw.get("io_range"))

def _run_camera_track_check(timeline, fps, **_kw):
    """实拍素材越轨"""
    return check_camera_on_high_tracks(timeline, fps=fps, io_range=_kw.get("io_range"))

def _run_through_edit_check(timeline, fps, **_kw):
    return check_through_edits(timeline, fps, io_range=_kw.get("io_range"))

def _run_tailboard_check(timeline, fps, **_kw):
    """尾板检测"""
    return check_tailboard(timeline, fps, io_range=_kw.get("io_range"))

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
        ("city",   ["cities_cn.txt"]),
    ]
    # 加载个人词典白名单
    whitelist_path = None
    personal_csv = _CENSOR_PERSONAL_CSV
    white_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        if os.path.isfile(personal_csv):
            whitelist = []
            with open(personal_csv, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 1 and row[0].strip():
                        whitelist.append(row[0].strip())
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
            except Exception: pass

    # 过滤个人词典已覆盖的词
    personal_words = set()
    if _kw.get("personal_enabled"):
        personal_path = _CENSOR_PERSONAL_CSV
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
    csv_path = _CENSOR_PERSONAL_CSV
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
                        w = row[0].strip()
                        if w:
                            whitelist.append(w)
                    if len(row) >= 3:
                        b = row[2].strip()
                        if b:
                            blacklist.append(b)
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
        except Exception: pass
        try: os.unlink(white_tmp.name)
        except Exception: pass

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
            kept[0] = _make_result("pass", detail="系统违禁词典: 无违禁词 (已由个人词典覆盖)", is_summary=True)
        else:
            kept[0] = _make_result("fail",
                detail=f"系统违禁词典: {total} 处  (个人词典覆盖 {removed} 处)", is_summary=True)
    return kept
CHECKS = [
    # gate="" → 不用门控制，直接跑
    {"id": "timeline",      "section": "工程设置", "chk_id": CHK_TIMELINE,      "group": "工程", "subgroup": "设置",   "run_fn": _run_timeline_check,     "tracks": [], "gate": ""},
    {"id": "offline",       "section": "脱机检测", "chk_id": CHK_OFFLINE,       "group": "工程", "subgroup": "路径",   "run_fn": _run_offline_check,       "tracks": ["video", "audio"], "gate": ""},
    {"id": "path",          "section": "路径检测", "chk_id": CHK_PATH,           "group": "工程", "subgroup": "路径",   "run_fn": _run_path_check,          "tracks": ["video", "audio"], "gate": ""},
    {"id": "track",         "section": "轨道结构", "chk_id": CHK_TRACK,          "group": "工程", "subgroup": "轨道",   "run_fn": _run_track_check,        "tracks": ["subtitle","video","audio"], "gate": ""},
    {"id": "fragment",      "section": "启用/禁用", "chk_id": CHK_FRAGMENT,       "group": "工程", "subgroup": "启用",   "run_fn": _run_fragment_check,      "tracks": ["subtitle","video","audio"], "gate": "all"},
    # 字幕门
    {"id": "sub_linebreak", "section": "换行",     "chk_id": CHK_SUB_LINEBREAK,  "group": "字幕", "subgroup": "文本",   "run_fn": _run_sub_linebreak_check, "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "sub_duration",  "section": "时长",     "chk_id": CHK_SUB_DURATION,   "group": "字幕", "subgroup": "文本",   "run_fn": _run_sub_duration_check,  "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "sub_glyph",     "section": "异体字",   "chk_id": CHK_SUB_GLYPH,      "group": "字幕", "subgroup": "合规",   "run_fn": _run_sub_glyph_check,     "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "censor_personal","section": "个人词典","chk_id": CHK_CENSOR_PERSONAL,"group": "字幕", "subgroup": "合规",   "run_fn": _run_censor_personal,     "tracks": ["subtitle"], "gate": "subtitle"},
    {"id": "censor_system",  "section": "系统词典","chk_id": CHK_CENSOR_SYSTEM, "group": "字幕", "subgroup": "合规",   "run_fn": _run_censor_system,       "tracks": ["subtitle"], "gate": "subtitle"},
    # 视频门
    {"id": "video_clamp",   "section": "夹帧",     "chk_id": CHK_VIDEO_CLAMP,    "group": "视频", "subgroup": "夹帧",   "run_fn": _run_video_clamp_check,   "tracks": ["video"], "gate": "video"},
    {"id": "black_frame",   "section": "黑帧",     "chk_id": CHK_BLACK,          "group": "视频", "subgroup": "黑帧",   "run_fn": _run_black_frame_check,   "tracks": ["video","audio"], "gate": "video"},
    {"id": "black_border",  "section": "黑边",     "chk_id": CHK_BORDER,         "group": "视频", "subgroup": "黑边",   "run_fn": _run_black_border_check,  "tracks": ["video"], "gate": "video"},
    {"id": "speed",         "section": "变速",     "chk_id": CHK_SPEED,           "group": "视频", "subgroup": "变速",   "run_fn": _run_speed_check,         "tracks": ["video"], "gate": "video"},
    {"id": "camera_track",  "section": "视频越轨", "chk_id": CHK_CAMERA,          "group": "视频", "subgroup": "越轨",   "run_fn": _run_camera_track_check,  "tracks": ["video"], "gate": "video"},
    {"id": "through_edit",  "section": "直通编辑", "chk_id": CHK_THROUGH_EDITS,  "group": "视频", "subgroup": "直通",   "run_fn": None,                     "tracks": ["video"], "gate": "",  "hidden": True},
    {"id": "tailboard",     "section": "尾板",     "chk_id": CHK_TAILBOARD,     "group": "视频", "subgroup": "尾板",   "run_fn": _run_tailboard_check,     "tracks": ["video"], "gate": "video"},
    {"id": "color",         "section": "色彩",     "chk_id": CHK_COLOR,           "group": "色彩", "subgroup": "色彩",   "run_fn": _run_color_check,         "tracks": ["video"], "gate": "video"},
    {"id": "tag_markers",    "section": "调色标记", "chk_id": CHK_TAG_MARKERS,     "group": "色彩", "subgroup": "调色标记","run_fn": _run_tag_markers_check,    "tracks": ["video"], "gate": "video"},
    # 音频门
    {"id": "audio_mono",    "section": "声道",     "chk_id": CHK_MONO,           "group": "音频", "subgroup": "声道",   "run_fn": _run_mono_check,          "tracks": ["audio"], "gate": "audio"},
    {"id": "audio_loudness","section": "音量",     "chk_id": CHK_LOUDNESS,       "group": "音频", "subgroup": "声道",   "run_fn": None,                     "tracks": [], "gate": "audio"},
    {"id": "audio_color",   "section": "音频越轨", "chk_id": CHK_AUDIO_COLOR,     "group": "音频", "subgroup": "越轨",   "run_fn": _run_audio_color_check,   "tracks": ["audio"], "gate": "audio"},
]
# 扩展指南：
#   - gate: ""=不用门控制直接跑, 非空=受 gates_ok 控制（四扇并行门全过才跑）
#   - tracks: 声明需要的轨道类型, []不预加载; 门关闭时相关轨道也不会预加载
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

_track_values = [DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS]
_clamp_value = DEFAULT_CLAMP_THRESHOLD
_video_clamp_threshold = 2  # 视频夹帧阈值（帧）
_black_frame_sec = DEFAULT_BLACK_FRAME_SEC
_censor_subs = {"base": True, "en": True, "bw": True, "bw_sms": True}
_mask_ratio = None        # 遮幅宽高比（内存态：重启/切工程重置）
_last_project_name = ""   # 检测工程切换
_checking = False
_BUSY = False
_config_open = False  # 防配置窗口重复打开

def _lock_ui(label: str):
    global _BUSY; _BUSY = True
    itm[BTN_START].Enabled = False; itm[BTN_UPDATE].Enabled = False
    itm[BTN_ERR_SEND].Enabled = False; itm[BTN_MANUAL].Enabled = False
    itm[BTN_CONFIG].Enabled = False
    itm["btn_browse_script"].Enabled = False
    itm["btn_paste_link"].Enabled = False

def _unlock_ui():
    global _BUSY; _BUSY = False
    itm[BTN_START].Enabled = True; itm[BTN_START].Text = "开始检查"
    itm[BTN_UPDATE].Enabled = True; itm[BTN_ERR_SEND].Enabled = True
    itm[BTN_MANUAL].Enabled = True
    itm[BTN_CONFIG].Enabled = True
    itm["btn_browse_script"].Enabled = True
    itm["btn_paste_link"].Enabled = True
    if _ai_allowed: itm[BTN_AI_TYPO].Enabled = True

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
                    _action_log(f"🎬 工程切换: {name} — 遮幅已重置")
    except Exception:
        pass

# ═══════════════════════════════════════════
# 日志系统（统一 log_writer 模块）
# ═══════════════════════════════════════════
from log_writer import get_logger
_log = get_logger("交付自检工具")
_HOSTNAME = socket.gethostname()
_CONFIG_DIR = _DATA_DIR
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")

def _ts():
    return time.strftime("%m-%d %H:%M:%S")

def _action_log(msg: str):
    _stderr_msg = msg  # try 外捕获，确保文件写入失败时 stderr 仍能输出
    try:
        _log.ui(f"[{_ts()}] {msg}")
    except Exception:
        pass
    if any(k in _stderr_msg for k in ("❌", "⚠", "Error", "失败", "Traceback", "崩溃", "异常")):
        print(_stderr_msg, file=sys.stderr)
    if any(k in msg for k in ("异常", "崩溃", "Traceback", "ModuleNotFound", "ImportError")) and "结构异常" not in msg and "格式异常" not in msg:
        _ui_error_state["count"] += 1
        try: _update_err_counter()
        except Exception: pass  # noop: 配置写入失败不影响主流程

# ═══════════════════════════════════════════
# UI 布局
# ═══════════════════════════════════════════
_CHECK_ROW_STYLE = STYLE_CHECK_ROW
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
    自动区分：hidden → 不生成, run_fn=None → 灰色 disabled, 正常 → 勾选框。
    """
    widgets = []
    for cid in check_ids:
        check = next((c for c in CHECKS if c["id"] == cid), None)
        if check is None:
            _action_log(f"_section_checkboxes: 未知 check_id '{cid}'")
            widgets.append(ui.Label({"Text": f"?{cid}",
                "StyleSheet": STYLE_WARN, "Weight": 0}))
            continue
        if check.get("hidden"):
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
    return [ui.HGroup({"Spacing": SPACE_NORMAL, "Weight": 0}, widgets)]

# ── 特殊控件常量（已迁移到「配置」弹窗）──

window_layout = [
    ui.VGroup({"Spacing": 2}, [

        # ── 上半区：常规检查（左）| 字幕检测（右）──
        ui.HGroup({"Spacing": SPACE_RELAXED, "Weight": 0}, [

            # ====== 左区：原始检查面板 ======
            ui.VGroup({"Spacing": SPACE_SM, "Weight": 0}, [
            ui.Label({"ID": "lbl_check_title", "Text": "常规检查",
                      "StyleSheet": STYLE_HEADING,
                      "Weight": 0, "Alignment": {"AlignHCenter": True}}),
            ui.HGroup({"Spacing": SPACE_WIDE, "Weight": 0}, [
                # 最左：5 个分组开关
                ui.VGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, list(
                    ui.Button({"ID": f"{BTN_TOGGLE_GROUP}{gn}", "Text": gn,
                               "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                               "MinimumSize": SIZE_TOGGLE})
                    for gn in GROUP_ORDER
                )),

                # 左侧：检查选项
                ui.VGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, [
                *_build_group_rows("工程"),
                *_build_group_rows("视频"),
                *_build_group_rows("音频"),
                *_build_group_rows("色彩"),
                ]),

                ui.HGap({"Weight": 0, "MinimumSize": [10, 0]}),

                # 开始检查 + 配置
                ui.VGroup({"Spacing": SPACE_SM, "Weight": 0}, [
                    ui.Button({"ID": BTN_START, "Text": "开始检查",
                               "StyleSheet": BTN_PRIMARY, "Weight": 0,
                               "MinimumSize": [SIZE_BTN_XL_W, SIZE_BTN_XL_H]}),
                    ui.Button({"ID": BTN_CONFIG, "Text": "配置",
                               "StyleSheet": BTN_STYLE, "Weight": 0,
                               "MinimumSize": [SIZE_BTN_XL_W, SIZE_BTN_H]}),
                ]),
            ]),
            ]),  # 结束左区 VGroup

            ui.HGap({"Weight": 0, "MinimumSize": SIZE_GAP_TINY}),
            ui.VGroup({"Weight": 0, "Spacing": SPACE_NONE}, [
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER,
                          "Weight": 0, "MinimumSize": [0, SIZE_LINE_H]}),
            ]),
            ui.HGap({"Weight": 0, "MinimumSize": SIZE_GAP_TINY}),

            # ====== 右区：字幕检测面板 ======
            ui.VGroup({"Spacing": SPACE_TIGHT, "Weight": 0, "MinimumSize": [220, 0]}, [
                ui.Label({"ID": "lbl_ai_title", "Text": "字幕检测",
                          "StyleSheet": STYLE_HEADING,
                          "Weight": 0, "Alignment": {"AlignHCenter": True}}),
                ui.Label({"ID": EDIT_SCRIPT_SRC, "Text": "选填，提供剧本可启用 AI 错别字校对",
                          "StyleSheet": "font-size:10px;color:#999", "Weight": 0}),
                ui.VGap(SPACE_TIGHT),
                ui.HGroup({"Spacing": SPACE_SM, "Weight": 0}, [
                    ui.Button({"ID": "btn_browse_script", "Text": "📂 本地",
                               "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                               "MinimumSize": [64, SIZE_BTN_SM_W]}),
                    ui.Button({"ID": "btn_paste_link", "Text": "🔗 飞书",
                               "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                               "MinimumSize": [64, SIZE_BTN_SM_W]}),
                ]),
                ui.VGap(SPACE_SM),
                ui.Button({"ID": BTN_AI_TYPO, "Text": "字幕检测",
                              "StyleSheet": BTN_PRIMARY.replace("100", "80"),
                              "Weight": 0, "MinimumSize": [108, 36]}),
            ]),

        ]),  # 结束上半区 HGroup

        # ── 结果区：分组 + 数据 ──
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
        ui.VGroup({"Spacing": SPACE_TIGHT, "Weight": 0}, [
            ui.Label({"ID": "lbl_gate_warn", "Text": "",
                      "StyleSheet": "color:rgb(220,180,80);font-size:13px;padding:4px 10px",
                      "Weight": 0, "WordWrap": True, "MinimumSize": [0, SIZE_LINE_H]}),
            # 操作按钮行
            ui.HGroup({"Spacing": SPACE_SM, "Weight": 0}, [
                ui.Label({"ID": TRIAL_LB, "Text": "",
                          "StyleSheet": "color:rgb(220,180,60);font-size:10px",
                          "Weight": 1, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.HGap({"Weight": 1}),
                ui.Button({"ID": BTN_UPDATE, "Text": "",
                           "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                           "MinimumSize": [70, SIZE_BTN_H]}),
                ui.Button({"ID": BTN_MANUAL, "Text": "📖 使用手册",
                           "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                           "MinimumSize": [SIZE_BTN_LG_W, SIZE_BTN_H]}),
                ui.Button({"ID": BTN_ERR_SEND, "Text": "📋 导出日志",
                           "StyleSheet": BTN_STYLE_SM, "Weight": 0,
                           "MinimumSize": [SIZE_BTN_LG_W, SIZE_BTN_H]}),
            ]),
            # 状态栏
            ui.HGroup({"Spacing": SPACE_COMPACT, "Weight": 0}, [
                ui.Label({"ID": HINT_LB, "Text": "请点击「开始检查」",
                          "StyleSheet": STYLE_HINT, "Weight": 1,
                          "WordWrap": True, "MinimumSize": [0, SIZE_LINE_H]}),
                ui.Label({"Text": f"裁缝老师的达芬奇插件工坊 ✂️ | v{version_string()}",
                          "StyleSheet": STYLE_FOOTER, "Weight": 0}),
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
itm[BTN_UPDATE].Visible = False  # 构造里设 Visible=False 有 UIManager bug，运行时设

# ═══════════════════════════════════════════
# 初始状态
# ═══════════════════════════════════════════
itm[BTN_START].Enabled = False
itm[BTN_AI_TYPO].Enabled = _ai_allowed
itm[EDIT_SCRIPT_SRC].Text = "选填，提供剧本可启用 AI 错别字校对"
_SCRIPT_SRC_PATH = ""

# Tree 表头
tree = itm[TREE_RESULT]
_setup_tree_header(tree)

# 左侧导航 Tree — 检查时动态填充
group_tree = itm[GROUP_TREE]
_cached_sections = []

# ═══════════════════════════════════════════
# Tree 渲染
# ═══════════════════════════════════════════

def _render_group(group_name, sections, tree, parent_group=""):
    """渲染一个 group 或 subgroup 的检查结果到右侧 Tree"""
    tree.Clear()
    _setup_tree_header(tree)
    # 判断是 group 还是 subgroup
    all_sg = sorted(set(c.get("subgroup", c.get("group", "")) for c in CHECKS if c.get("group") == group_name))
    if all_sg:
        # 是 group → 渲染其下所有 subgroup 的行
        for sg in all_sg:
            secs = [s for s in sections if s.get("subgroup") == sg and s.get("group") == group_name]
            for sec in secs:
                for row_data in sec["rows"]:
                    row = tree.NewItem()
                    _set_row(row, row_data)
                    tree.AddTopLevelItem(row)
    else:
        # 是 subgroup → 用 parent_group 与 group_name 双重过滤
        if parent_group:
            secs = [s for s in sections if s.get("subgroup") == group_name and s.get("group") == parent_group]
        else:
            secs = [s for s in sections if s.get("subgroup") == group_name]
        for sec in secs:
            for row_data in sec["rows"]:
                row = tree.NewItem()
                _set_row(row, row_data)
                tree.AddTopLevelItem(row)

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
            ui.HGap(15),
            ui.Label({"ID": "cfg_mask_custom_lbl", "Text": "自定义",
                      "StyleSheet": "color:rgb(140,140,140);font-size:13px", "Weight": 0,
                      "Visible": False}),
            ui.LineEdit({"ID": "cfg_mask_custom", "Text": "",
                         "StyleSheet": "font-size:12px",
                         "MinimumSize": [60, 0], "Weight": 0,
                         "Visible": False}),
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


def _show_config_dialog():
    """打开配置窗口"""
    global _config_open
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
                _save_api_keys(_keys); _action_log("📂 从 .env 迁移了 API 配置")
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
                                except Exception: _action_log(f"⚠ cfg_hint 渲染失败: {hint}")
                                continue
                    try:
                        _keys = _load_api_keys()
                        # 如果用户输入的是掩码（含"…"），保留存储的真值
                        if "…" in val:
                            val = _api_values.get(sid, val)
                        _keys[sid] = val; _save_api_keys(_keys)
                        _action_log(f"🔑 {section['label']} 已保存")
                    except Exception as e:
                        err = f"保存失败: {e}"
                        _action_log(f"⚠ API Key 保存异常: {e}")
            elif t == "smb_paths":
                try:
                    from shared.deploy_config import save_smb_paths
                    ok = save_smb_paths(_smb_paths_cache)
                    _action_log(f"{'✅' if ok else '⚠'} 服务器路径: {len(_smb_paths_cache)} 条")
                    # 清缓存让下次检测重新采集路径信息
                    from check_core import _clear_clip_files_cache
                    _clear_clip_files_cache()
                except Exception as e:
                    _action_log(f"⚠ 路径保存失败: {e}")
            elif t == "censor_personal":
                pass
            elif t == "mask_ratio":
                global _mask_ratio
                preset = cfg["cfg_mask_preset"].CurrentText
                custom = cfg["cfg_mask_custom"].Text.strip()
                if preset == _MASK_UNSET:
                    _mask_ratio = None
                    _action_log("🎬 遮幅已清除（未设置）")
                    continue
                if preset in _MASK_PRESETS:
                    val = preset
                elif custom:
                    val = custom
                else:
                    _mask_ratio = None
                    _action_log("🎬 遮幅已清除（未设置）")
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
                    _action_log(f"🎬 遮幅宽高比: {_mask_ratio}")
                except ValueError:
                    err = err or f"遮幅值无效: {val}（需为数字，如 2.35）"
        if err or _validation_err:
            if err: _action_log(f"⚠ {err}")
            try:
                cfg["cfg_hint"].Visible = True
                cfg["cfg_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
                if err: cfg["cfg_hint"].Text = f"⚠ {err}"
            except Exception: _action_log(f"⚠ cfg_hint 渲染失败: {err}")
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
                    _action_log(f"🪟 激活弹窗: 子进程异常 (退出码 {r.returncode})")
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
                _action_log(f"🔑 激活: {'✅' if ok else '❌'} {msg}")
                if ok:
                    global _ai_allowed
                    _ai_allowed = True
                    _keys = _load_api_keys(); _keys["activation_code"] = code
                    if ts: _keys["trial_remain_secs"] = str(ts)
                    _save_api_keys(_keys)
                    itm[BTN_AI_TYPO].Text = "字幕检测"; itm[BTN_AI_TYPO].Enabled = True
                    itm[TRIAL_LB].Text = "已激活 ✓"
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
                _action_log(f"🔓 停用: {'✅' if ok else '❌'} {msg}")
                if ok:
                    global _ai_allowed
                    _ai_allowed = False
                    _keys = _load_api_keys()
                    if _keys.get("activation_code"): del _keys["activation_code"]; _save_api_keys(_keys)
                    itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"; itm[BTN_AI_TYPO].Enabled = False
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
                    itm[TRIAL_LB].Text = format_trial(d, p.get("machine_fingerprint", "")[:8])
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
                    _action_log(f"🔑 {cfg_info['prompt'].split('（')[0].strip()} 已编辑")
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
                _action_log(f"📂 即将打开 Finder: {censor_path}")
                subprocess.Popen(["open", "-R", censor_path])
            else:
                _action_log(f"📂 即将打开 Explorer: {censor_path}")
                subprocess.Popen(["explorer", "/select,", censor_path])
        except Exception:
            itm[HINT_LB].Text = "右键「短剧违禁词表.csv」→ 打开方式 → WPS / Excel / Numbers"
            _action_log("📝 Finder 已定位个人词典")

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
                _action_log(f"📂 添加路径: {path}")
        except Exception as e:
            _action_log(f"⚠ 文件夹选择失败: {e}")
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
        _action_log(f"🗑 删除路径: {selected}")

    config_dlg.On["cfg_edit_censor"].Clicked = _edit_censor
    config_dlg.On["cfg_smb_add"].Clicked = _add_smb_path
    config_dlg.On["cfg_smb_del"].Clicked = _delete_smb_path
    config_dlg.On["cfg_save"].Clicked = _save
    config_dlg.On["cfg_cancel"].Clicked = lambda ev: config_disp.ExitLoop()
    config_dlg.On[CONFIG_WIN_ID].Close = lambda ev: config_disp.ExitLoop()

    _action_log("⚙ 打开配置窗口")
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
        combo.AddItem("自定义…")  # 最后一个选项对应自定义输入
        
        combo.RecalcLayout()  # AddItem 后重新计算 ComboBox 宽度
        
        if _mask_ratio is None:
            combo.SetCurrentIndex(0)
            cfg["cfg_mask_custom"].Text = ""
            _action_log(f"🎬 mask_init: state=None idx=0")
        elif _mask_ratio in _MASK_PRESETS:
            idx = _MASK_PRESETS.index(_mask_ratio) + 1
            combo.SetCurrentIndex(idx)
            cfg["cfg_mask_custom"].Text = ""
            _action_log(f"🎬 mask_init: state=preset({_mask_ratio}) idx={idx}")
        else:
            combo.SetCurrentIndex(len(_MASK_PRESETS) + 1)  # "自定义…"
            cfg["cfg_mask_custom"].Text = _mask_ratio
            _action_log(f"🎬 mask_init: state=custom({_mask_ratio})")
    except Exception as _e:
        import traceback
        _action_log(f"⚠ 遮幅初始化失败: {_e}\n{traceback.format_exc()}")

    # ── 遮幅："自定义…"选项才显示标签+输入框 ──
    _CUSTOM_IDX = len(_MASK_PRESETS) + 1
    def _toggle_custom_visible():
        idx = combo.CurrentIndex
        is_custom = idx == _CUSTOM_IDX
        cfg["cfg_mask_custom_lbl"].Visible = is_custom
        cfg["cfg_mask_custom"].Visible = is_custom
        config_dlg.RecalcLayout()
    _toggle_custom_visible()
    config_dlg.On["cfg_mask_preset"].CurrentIndexChanged = lambda ev: _toggle_custom_visible()

    config_dlg.Show()
    config_dlg.RecalcLayout()
    config_disp.RunLoop()
    config_dlg.Hide()
    _config_open = False

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
    return r["status"] == "fail", r["status"] == "warn", False

# ═══════════════════════════════════════════
# AI 校对
# ═══════════════════════════════════════════

def _save_typo_session(timeline, entries, entry_starts, parsed, all_lines,
                       script_src, result, project=None):
    """每次 LLM 校对后完整存档（输入+输出），复盘时对比交付 SRT 使用。

    路径: ~/Library/Application Support/交付自检/typo_sessions/{项目}/{时间线}/{时间戳}.json
    """
    import json as _json, shutil as _shutil, hashlib as _hashlib, datetime as _dt
    try:
        proj_name = project.GetName() if project else "未知项目"
        tl_name = timeline.GetName() or "未命名时间线"
    except Exception:
        proj_name, tl_name = "未知", "未知"

    # sanitize: 替换文件名不安全字符
    safe_proj = "".join(c if c.isalnum() or c in "_-." else "_" for c in proj_name)[:80]
    safe_tl = "".join(c if c.isalnum() or c in "_-." else "_" for c in tl_name)[:60]

    base = os.path.join(_DATA_DIR, "typo_sessions")
    session_dir = os.path.join(base, safe_proj, safe_tl)
    os.makedirs(session_dir, exist_ok=True)

    ts = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    model = result.get("model", "unknown")
    fname = f"{ts}_{model}.json"
    path = os.path.join(session_dir, fname)

    # 组装 session 数据
    session = {
        "meta": {
            "project": proj_name,
            "timeline": tl_name,
            "timestamp": _dt.datetime.now().isoformat(),
            "model": model,
            "provider": result.get("provider", "?"),
            "entry_count": len(entries),
            "script_source": script_src,
            "line_count": len(all_lines),
        },
        "entries": [
            {"index": i, "start_frame": int(entry_starts[i]) if i < len(entry_starts) else 0,
             "text": entries[i]}
            for i in range(len(entries))
        ],
        "prompt": {
            "script_preview": all_lines[:3] if all_lines else [],
            "script_line_count": len(all_lines),
        },
        "result": {
            "same_show": result.get("same_show"),
            "corrections": result.get("corrections", []),
            "error": result.get("error"),
            "raw_tail": result.get("raw_tail"),
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        _json.dump(session, f, ensure_ascii=False, indent=2)

    _action_log(f"📁 校对存档: {os.path.join(safe_proj, safe_tl, fname)}")

    # 清理：同时间线保留最近 20 份，删旧
    existing = sorted([f for f in os.listdir(session_dir) if f.endswith(".json")])
    if len(existing) > 20:
        for old in existing[:-20]:
            os.remove(os.path.join(session_dir, old))

def _run_ai_typo():
    """一步到位：下载剧本 → 解析 → 集号匹配 → LLM 校对（含剧集一致性检测）。"""
    global _checking
    if _BUSY or _checking:
        return
    if not _ai_allowed:
        fp = (_cred or {}).get("payload", {}).get("machine_fingerprint", "")[:8]
        itm[TRIAL_LB].Text = format_trial(0, fp)
        return
    _checking = True
    itm[HINT_LB].Text = ""
    itm[HINT_LB]["StyleSheet"] = f"{STYLE_HINT};"
    itm[GROUP_TREE].Clear()
    itm[TREE_RESULT].Clear()
    itm["lbl_gate_warn"].Text = ""
    itm["lbl_gate_warn"].Visible = False
    _action_log("🧹 已清提示+分类+结果树+门控警告")
    _lock_ui("检查中")

    def _stop(msg):
        itm[HINT_LB].Text = msg
        _action_log(msg)

    try:
        from llm_typo_check import check_typos
        from script_parser import parse_script, set_log_callback
        set_log_callback(_action_log)

        # ═══ 门0: 有空字幕？ ═══
        resolve = bmd.scriptapp("Resolve")
        timeline = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        if not timeline:
            return _stop("❌ 未找到当前时间线")
        entries = []
        entry_starts = []
        for it in (timeline.GetItemListInTrack("subtitle", 1) or []):
            try:
                entries.append(it.GetName() or "")
                entry_starts.append(it.GetStart())
            except Exception:
                pass
        if not entries:
            return _stop("⚠ 当前时间线无字幕，跳过校对")
        _action_log(f"📝 字幕: {len(entries)} 条")

        # ═══ 门1: 下载+解析剧本 ═══
        src = _SCRIPT_SRC_PATH or itm[EDIT_SCRIPT_SRC].Text.strip()
        if not src or src == "选填，提供剧本可启用 AI 错别字校对":
            itm[HINT_LB].Text = "字幕系统检测中..."
            itm[HINT_LB]["StyleSheet"] = f"{STYLE_HINT};"
            try:
                from check_core import preload_timeline_items as _preload
                fps = float(timeline.GetSetting("timelineFrameRate") or 25.0)
                _preload(timeline, track_types=["subtitle"])
                sections = {"文本":{"subgroup":"文本","group":"字幕","rows":[]},
                           "合规":{"subgroup":"合规","group":"字幕","rows":[]}}
                for _nm,_fn,_sg in [("换行",_run_sub_linebreak_check,"文本"),("时长",_run_sub_duration_check,"文本"),
                                     ("全半角",_run_fw_check,"文本"),
                                     ("异体字",_run_sub_glyph_check,"合规"),("系统词典",_run_censor_system,"合规"),
                                     ("个人词典",_run_censor_personal,"合规")]:
                    cr = _fn(timeline,fps)
                    _action_log(f"  {_nm}: {len(cr)} 项")
                    for r in cr:
                        if r.get("is_summary"): continue
                        icon = "❌" if r.get("status")=="fail" else "⚠"
                        sections[_sg]["rows"].append({
                            FIELD_TO_COLUMN["track"]:r.get("track",""),
                            FIELD_TO_COLUMN["timecode"]:r.get("timecode",""),
                            FIELD_TO_COLUMN["detail"]:f"{icon} | {r.get('detail','')}",
                            FIELD_TO_COLUMN["reason"]:r.get("reason","")})
                for sg in sections.values():
                    sg["rows"].sort(key=lambda r: r.get(FIELD_TO_COLUMN["timecode"],""))
                tree = itm[TREE_RESULT]; tree.Clear(); _setup_tree_header(tree)
                itm[GROUP_TREE].Clear()
                global _cached_sections; _cached_sections = list(sections.values())
                _render_group("字幕",[s for s in sections.values() if s["rows"]],tree)
                gt = itm[GROUP_TREE]; hdr = gt.NewItem(); hdr.Text[0] = "分类"; gt.SetHeaderItem(hdr)
                for sg_name in ["文本","合规"]:
                    if sections.get(sg_name,{}).get("rows"):
                        gi = gt.NewItem(); gi.Text[0] = sg_name; gt.AddTopLevelItem(gi)
                total = sum(len(s["rows"]) for s in sections.values())
                _action_log(f"📝 字幕系统检测: {total} 项")
                _stop("字幕系统检测完成")
            except Exception as e:
                import traceback; _action_log(f"❌ 字幕检测异常: {e}")
                _stop(f"检测失败: {e}")
            _checking = False; _unlock_ui(); return

        # 剧本文件校验：大小上限 + 格式白名单（飞书链接不在此校验）
        if os.path.isfile(src):
            fsize = os.path.getsize(src)
            if fsize > 20 * 1024 * 1024:
                return _stop(f"❌ 剧本文件过大 ({fsize//1024//1024}MB)")
            lo = src.lower()
            if not (lo.endswith((".docx", ".doc", ".pdf", ".txt", ".md"))):
                return _stop("❌ 暂不支持此格式，请使用 .docx / .doc / .pdf / .txt / .md")
        try:
            parsed = parse_script(src)
            all_lines = parsed.get("lines", [])
            _action_log(f"📖 剧本: {len(all_lines)} 行")
        except Exception as e:
            return _stop(f"❌ 剧本解析失败: {e}")

        _action_log(f"📖 剧本: {len(all_lines)} 行 → 喂给 AI")
        _ts_start = time.time()
        itm[BTN_START].Enabled = False; itm[BTN_AI_TYPO].Enabled = False

        # ═══ LLM 校对 ═══
        itm[HINT_LB].Text = "AI 校对中..."
        _action_log(f"🤖 LLM 校对开始 ({len(entries)}字幕 vs {len(all_lines)}行剧本)")

        # 先跑系统规则：换行/时长→直接渲染，违禁词/异体字→喂给AI
        from check_core import preload_timeline_items as _preload2
        sys_candidates = ""
        direct_results = []  # 换行/时长，不经AI直接显示
        try:
            fps = float(timeline.GetSetting("timelineFrameRate") or 25.0)
            _preload2(timeline, track_types=["subtitle"])
            # 换行+时长 → 直接进Tree
            for _nm, _fn in [("换行",_run_sub_linebreak_check),("时长",_run_sub_duration_check)]:
                for r in _fn(timeline, fps):
                    if not r.get("is_summary"):
                        r["_check_name"] = _nm
                        direct_results.append(r)
            # 违禁词+异体字 → 序列化喂给AI
            sys_results = []
            for _nm, _fn in [("异体字",_run_sub_glyph_check),("系统词典",_run_censor_system),
                              ("个人词典",_run_censor_personal)]:
                for r in _fn(timeline, fps):
                    if r.get("is_summary"): continue
                    r["_check_name"] = _nm
                    sys_results.append(r)
            lines = []
            for r in sys_results:
                tc = r.get("timecode", "")
                detail = r.get("detail", "")
                cname = r.get("_check_name", "")
                # 统一用指令式格式，让 AI 直接行动而非审查
                if "真实地名" in cname:
                    lines.append(f"- {tc} 出现真实地名「{detail}」→ 应替换为架空地名")
                else:
                    lines.append(f"- {tc} 出现违禁词「{detail}」→ 应修正")
            if lines:
                sys_candidates = "\n".join(lines)
            _action_log(f"📋 系统候选 {len(lines)} 条，喂给 AI（+{time.time()-_ts_start:.0f}s）")
        except Exception:
            _action_log("⚠ 系统规则预检失败，跳过候选")
            sys_candidates = ""

        tl_name = timeline.GetName() or ""
        ep_input = ""
        try:
            cpl = int(timeline.GetSetting().get("limitSubtitleCPL", 0))
        except Exception:
            cpl = 0
        result = check_typos(entries, all_lines,
                                    timeline_name=tl_name, episode=ep_input,
                                    system_candidates=sys_candidates, cpl=cpl)
        _action_log(f"🤖 AI 校对完成（+{time.time()-_ts_start:.0f}s）")
        if result.get("error"):
            attempts = result.get("attempts", [])
            if attempts:
                providers = ", ".join(f"{a['model']}({a['result']})" for a in attempts)
                msg = f"❌ 所有 AI 供应商均失败: {providers}\n请检查 API Key 或网络连接"
            else:
                msg = f"❌ 校对失败: {result['error']}"
            _action_log(msg)
            return _stop(msg)

        corrections = result.get("corrections", [])
        provider = result.get("provider", "?")
        model = result.get("model", "?")
        _action_log(f"🤖 AI 结果: {len(corrections)}处修正, same_show={result.get('same_show')} ({provider}/{model})")

        # ═══ 存档：完整保存本次校对的输入+输出（复盘用）═══
        _save_typo_session(timeline, entries, entry_starts, parsed, all_lines,
                           _SCRIPT_SRC_PATH or itm[EDIT_SCRIPT_SRC].Text.strip(), result,
                           project=resolve.GetProjectManager().GetCurrentProject())

        _action_log("🎨 开始渲染结果...")
        tree = itm[TREE_RESULT]
        tree.Clear()
        tree.ColumnCount = len(_ENABLED_COLS)
        _setup_tree_header(tree)
        all_rows = []  # 收集所有行，最后统一排序
        direct_rows = []  # 单独跟踪：系统检测（换行/时长）
        ai_rows = []      # 单独跟踪：AI 修正

        # 先添加直接结果（换行/时长），等 AI 结果也加入后统一渲染
        for r in direct_results:
            icon = "❌" if r.get("status")=="fail" else "⚠"
            row = {"track": r.get("track",""), "tc": r.get("timecode",""),
                   "msg": f"{icon} | {r.get('detail','')}（{r.get('_check_name','系统')}）",
                   "reason": r.get("reason","")}
            all_rows.append(row)
            direct_rows.append(row)
        _action_log(f"🎨 direct={len(direct_rows)}")

        # 传错剧本：红字警告区提示
        if result.get("same_show") is False:
            itm["lbl_gate_warn"].Text = "⚠ 字幕与剧本疑似不同剧集，请检查剧本链接是否正确"
            itm["lbl_gate_warn"].Visible = True
            _action_log("⚠ LLM 判定字幕与剧本非同一部剧")
            itm[HINT_LB].Text = "⚠ 疑似不同剧集，请检查剧本链接"

        # AI 有结果才追加 corrections
        _action_log(f"🎨 corrections={len(corrections)}")
        if corrections:
            smpte = _get_smpte(float(timeline.GetSetting("timelineFrameRate") or 25))

            for c in corrections:
                idx = c['index'] - 1
                tc_str = ""
                if 0 <= idx < len(entry_starts):
                    tc_str = smpte.gettc(entry_starts[idx])
                icon = "⚠"
                row = {"track": "ST1", "tc": tc_str,
                       "msg": f"{icon} | {c['original']} → {c['correction']}",
                       "reason": c.get('reason', '')}
                all_rows.append(row)
                ai_rows.append(row)

        # 统一渲染：系统结果在前，AI 结果在后，各自按时码排序
        _action_log(f"🎨 direct={len(direct_rows)} ai={len(ai_rows)} rendering...")
        _render_err = None
        if direct_rows or ai_rows:
            try:
                _s = _get_smpte(float(timeline.GetSetting("timelineFrameRate") or 25))
                direct_rows.sort(key=lambda r: _s.getframes(r.get("tc") or "00:00:00:00"))
                ai_rows.sort(key=lambda r: _s.getframes(r.get("tc") or "00:00:00:00"))
                for r in direct_rows + ai_rows:
                    row = tree.NewItem()
                    _set_row(row, r)
                    tree.AddTopLevelItem(row)
                _action_log(f"🎨 rendered={len(all_rows)} rows")
            except Exception as _e:
                _render_err = str(_e)
                _action_log(f"🎨 render FAIL: {_render_err}")
        else:
            # 无任何结果时显示一行提示，避免用户以为卡住了
            row = tree.NewItem()
            _set_row(row, {"track": "—", "tc": "—", "msg": "✅ 未发现问题", "reason": f"AI: {provider}/{model}"})
            tree.AddTopLevelItem(row)

        # 重建左侧分类（用 · 前缀区分子类，匹配 _on_group_click）
        gt = itm[GROUP_TREE]; gt.Clear()
        hdr = gt.NewItem(); hdr.Text[0] = "分类"; gt.SetHeaderItem(hdr)
        _cached_sections = []
        if direct_rows:
            _cached_sections.append({"subgroup": "文本", "group": "字幕", "rows": direct_rows})
        if ai_rows:
            _cached_sections.append({"subgroup": "AI检测", "group": "字幕", "rows": ai_rows})
        for sg in _cached_sections:
            gi = gt.NewItem(); gi.Text[0] = f"· {sg['subgroup']}"; gi.Text[1] = sg["group"]; gt.AddTopLevelItem(gi)
        _action_log(f"🎨 _cached_sections={len(_cached_sections)} [{', '.join(s['subgroup']+':'+str(len(s['rows'])) for s in _cached_sections)}]")

        total_all = len(all_rows)
        if corrections or direct_results:
            itm[HINT_LB].Text = (
                f"🔍 发现 {total_all} 处问题"
                f"（系统: {len(direct_results)}处 + AI: {len(corrections)}处）"
                f"  |  模型: {provider}/{model}"
                f"  |  AI 校对结果仅供参考，请剪辑师自行甄别"
            )
            _action_log(f"🔍 发现 {total_all} 处问题（系统={len(direct_results)} AI={len(corrections)}）({provider}/{model})")
        else:
            total = len(all_rows)
            itm[HINT_LB].Text = f"✅ 未发现错别字，{total} 项系统问题  ({provider}/{model})"
            _action_log(f"✅ 校对完成: 0处错别字, {total}系统 ({provider}/{model})")

    except Exception as e:
        _action_log(f"💥 AI校对失败，请重试")
        import sys as _sys2
        traceback.print_exc(file=_sys2.stderr)
        itm[HINT_LB].Text = f"❌ 校对异常: {e}"

    finally:
        _unlock_ui()
        _checking = False
        itm[BTN_START].Enabled = True; itm[BTN_AI_TYPO].Enabled = _ai_allowed

# ═══════════════════════════════════════════
# 开始检查
# ═══════════════════════════════════════════

def _start_check():
    global _checking, _start_time, _UPDATE_INFO, _ai_allowed, _trial_expired
    if _BUSY or _checking:
        return
    
    # 读后台子进程的更新检测结果（兜底：RunLoop前没读到的话，第一次开始检查时再读）
    if _update_result_path and os.path.exists(_update_result_path):
        _r = None
        try:
            import json as _json
            with open(_update_result_path) as f: _r = _json.load(f)
        except Exception: pass
        try: os.remove(_update_result_path)
        except OSError: pass
        if _r and _r.get("update_available"):
            _UPDATE_INFO = _r
            _action_log(f"⬆ 发现新版本 v{_r['latest']} (当前 {__version__})")
            itm[HINT_LB].Text = f"⬆ 新版本 v{_r['latest']} — 点击右侧按钮更新"
            itm[BTN_UPDATE].Visible = True
            itm[BTN_UPDATE].Text = "⬆ 更新"
            itm[BTN_UPDATE]["StyleSheet"] = "background-color:rgb(220,180,60);color:#1a1a1a;font-size:11px;font-weight:bold;border-radius:3px;padding:2px 8px"
    
    # 读后台子进程的 FC 验证结果（兜底）
    if _fc_result_path and os.path.exists(_fc_result_path):
        _r = None
        try:
            import json as _json2
            with open(_fc_result_path) as f: _r = _json2.load(f)
        except Exception: pass
        try: os.remove(_fc_result_path)
        except OSError: pass
        if _r and isinstance(_r, dict) and _r.get("ok") is False:
            _ai_allowed = False; _trial_expired = True
            _action_log(f"License 吊销: {_r.get('msg')}")
            itm[TRIAL_LB].Text = format_trial(0)
            itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"
            itm[BTN_AI_TYPO].Enabled = False
    
    _checking = True
    _start_time = time.time()
    _lock_ui("检查中")

    try:
        any_checked = any(
            itm[c["chk_id"]].Checked for c in CHECKS if c.get("run_fn") and c.get("group") != "字幕"
        )
        if not any_checked:
            _action_log("⚠ 未选择任何检查项")
            return

        _action_log(f"▶ 开始检查 (轨道模板={_track_values}, 夹帧阈值={_clamp_value})")
        itm[HINT_LB].Text = "检查中..."
        itm[HINT_LB]["StyleSheet"] = f"{STYLE_HINT};"  # 重置样式

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

        # ── 四扇并行门：任一不通 → 全部门控检查跳过 ──
        # 工程门：仅当勾了「工程设置」才生效，要求时码归零
        engineering_ok = not itm[CHK_TIMELINE].Checked or (timeline.GetStartFrame() == 0)
        gate_warnings = []
        if not engineering_ok:
            _action_log("⚠ 起始时码非零，后续门控检查已跳过，请归零时码后重新运行")
            gate_warnings.append("⚠ 起始时码非 00:00:00:00，后续门控检查已跳过，请归零时码后重新运行")

        sub_count = timeline.GetTrackCount("subtitle")
        vid_count = timeline.GetTrackCount("video")
        aud_count = timeline.GetTrackCount("audio")

        def _all_enabled(tt, count):
            for ti in range(1, count + 1):
                try:
                    if not timeline.GetIsTrackEnabled(tt, ti):
                        return False
                except Exception:
                    _action_log(f"⚠ 无法读取 {tt} 轨 {ti} 启用状态，视为未启用")
                    return False
            return True

        aud_names_ok = True
        if aud_count == DEFAULT_AUDIO_TRACKS:
            for idx, preset in enumerate(AUDIO_TRACK_PRESET):
                if timeline.GetTrackName("audio", idx + 1) != preset["name"]:
                    aud_names_ok = False; break

        gates = {}
        if itm[CHK_TRACK].Checked and not IS_PERSONAL:
            # 用户勾了轨道结构 → 三门严格检查（个人版跳过）
            gates["subtitle"] = engineering_ok and sub_count == DEFAULT_SUBTITLE_TRACKS and _all_enabled("subtitle", sub_count)
            gates["video"]    = engineering_ok and vid_count == DEFAULT_VIDEO_TRACKS and _all_enabled("video", vid_count)
            gates["audio"]    = engineering_ok and aud_count == DEFAULT_AUDIO_TRACKS and _all_enabled("audio", aud_count) and aud_names_ok
        else:
            gates["subtitle"] = engineering_ok
            gates["video"]    = engineering_ok
            gates["audio"]    = engineering_ok

        # 四扇并行门：任一不通 → 全部门控检查跳过
        gates_ok = engineering_ok and all(gates.values())

        if itm[CHK_TRACK].Checked and not IS_PERSONAL:
            failed_gates = []
            for gate, label in [("video","视频轨道"), ("audio","音频轨道"), ("subtitle","字幕轨道")]:
                if not gates[gate]:
                    failed_gates.append(label)
                    _action_log(f"⚠ {label}结构异常")
            if failed_gates:
                gate_warnings.append(f"⚠ {'、'.join(failed_gates)}结构异常，所有门控检查已跳过，请先修复基础问题后重新运行")

        if gate_warnings:
            itm["lbl_gate_warn"].Text = "  ⚠  ".join(gate_warnings)
            itm["lbl_gate_warn"].Visible = True
        else:
            itm["lbl_gate_warn"].Text = ""
            itm["lbl_gate_warn"].Visible = False

        # 按需预加载：只加载会实际运行的检查需要的轨道
        # （门关闭 → 对应检查跳过，轨道也不用预加载）
        needed = set()
        for check in CHECKS:
            if check.get("hidden") or check.get("group") == "字幕":
                continue
            g = check.get("gate", "")
            if check.get("run_fn") and itm[check["chk_id"]].Checked:
                if not g or gates_ok:
                    needed.update(check.get("tracks", []))
        try:
            from check_core import _clear_clip_files_cache
            _clear_clip_files_cache()
            preload_timeline_items(timeline, track_types=list(needed) if needed else None)
        except Exception:
            _action_log("⚠ 预加载失败（可能是旧版 API），回退逐条查询")
            # 不影响后续检查，_get_items() 自带逐条 IPC

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
            if not check.get("run_fn") or check.get("group") == "字幕":
                continue
            if not itm[check["chk_id"]].Checked:
                continue
            # 门关闭 → 跳过（四扇并行门：任一不通全停）
            g = check.get("gate", "")
            if g and not gates_ok:
                _action_log(f"⏭ {check['section']}检查跳过（门未通过）")
                continue

            _action_log(f"── {check['section']}检查 ──")
            try:
                all_results = list(check["run_fn"](
                    timeline=timeline, fps=fps, project=project,
                    personal_enabled=itm.get(CHK_CENSOR_PERSONAL,True),
                    io_range=io_range, debug_log=_action_log))
            except Exception:
                import traceback
                _action_log(f"❌ {check['section']}检查失败，请重试（详情已存日志）")
                # 原始异常写 stderr 供排错，不暴露给用户
                import sys as _sys
                traceback.print_exc(file=_sys.stderr)
                # 返回 warn 而非空列表，让用户看到此项不可用
                all_results = [_make_result("warn",
                    detail=f"{check['section']}: 检查不可用",
                    reason="可能是达芬奇版本不支持此 API，请升级或关闭此检查",
                    is_summary=True)]
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

            # 逐条记录检查结果到日志
            for r in rest:
                detail = r.get("detail", "")
                track = r.get("track", "")
                tc = r.get("timecode", "")
                line = f"  {track} {tc}  {detail}" if track else detail
                if r.get("status") == "pass":
                    pass  # 通过的不要噪音
                else:
                    _action_log(line)

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
                if any(s.get("subgroup") == sg and s.get("group") == name and s["rows"] for s in sections):
                    child = group_tree.NewItem()
                    child.Text[0] = f"  · {sg}"
                    child.Text[1] = name   # 存父组名，供 _on_group_click 解歧义
                    group_tree.AddTopLevelItem(child)

        if first_group:
            _render_group(first_group, sections, tree)

        # 总结 → 左下角状态栏
        elapsed_ms = int((time.time() - _start_time) * 1000)
        jump_hint = "💡 点击结果行可跳转到对应时间码"
        if has_failures:
            itm[HINT_LB].Text = f"❌ {fail_count} 项未通过，请修复后重新检查"
            if has_warnings:
                itm[HINT_LB].Text += f"，⚠ {warn_count} 项警告"
            itm[HINT_LB].Text += f"  |  {jump_hint}"
            _action_log("❌ 检查未通过 — 请修复上述问题")
        elif has_warnings:
            itm[HINT_LB].Text = f"⚠ {warn_count} 项警告  |  {jump_hint}"
            _action_log("⚠ 有警告 — 请检查")
        else:
            itm[HINT_LB].Text = "全部检查通过 ✓  现在可以交付渲染了"
            itm[HINT_LB]["StyleSheet"] = "color:rgb(50,205,50);font-size:10px;"
            _action_log("✅ 所有检查通过")

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
                    {"group": s["group"], "section": s["title"],
                     "all_ok": s["all_ok"],
                     "fails": [{k: v for k, v in r.items() if not k.startswith("_")}
                               for r in s.get("rows", []) if r.get("status") == "fail"]}
                    for s in sections
                ],
            })
        except Exception as e:
            _action_log(f"⚠ 结果持久化写入失败: {e}")

    except Exception as e:
        _action_log(f"❌ 检查异常: {type(e).__name__}（详情已记录）")
        import sys as _sys3, traceback; traceback.print_exc(file=_sys3.stderr)
        itm[HINT_LB].Text = "❌ 检查失败，请重试"
    finally:
        _unlock_ui()
        _checking = False

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

_ui_error_state = {"count": 0}

def _on_err_report(ev):
    """导出日志到本地"""
    _action_log(f"📤 导出按钮被点击 (error_count={_ui_error_state["count"]})")
    if _BUSY:
        return
    _lock_ui("导出日志")
    itm[BTN_ERR_SEND].Text = "⏳ 导出中..."
    export_debug_package(itm, BTN_ERR_SEND, _ui_error_state, _action_log, _DATA_DIR, trial_days_left, _load_api_keys, version_string)
    _unlock_ui()

def _log_activate_fail(code: str, detail: str):
    """持久化激活失败记录，供调试导出使用。"""
    import json, os
    try:
        fp = os.path.join(_DATA_DIR, "activate_fails.jsonl")
        record = json.dumps({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "detail": detail,
        }, ensure_ascii=False)
        with open(fp, "a", encoding="utf-8") as f:
            f.write(record + "\n")
    except Exception:
        pass

def _update_err_counter():
    """报错时更新按钮文字"""
    if _ui_error_state["count"] > 0:
        itm[BTN_ERR_SEND].Text = f"⚠️ {_ui_error_state["count"]} 个报错"
    else:
        itm[BTN_ERR_SEND].Text = "📋 导出日志"
dlg.On[BTN_ERR_SEND].Clicked = _on_err_report

def _on_manual(ev):
    """使用手册：检测连通性，在线→浏览器，离线→QR"""
    import socket, threading
    from urllib.parse import urlparse

    # 先测通目标域名，再决定走哪条路径
    online = False
    try:
        host = urlparse(MANUAL_URL).hostname
        s = socket.create_connection((host, 443), timeout=2)
        s.close()
        online = True
    except Exception:
        pass

    if online:
        try:
            webbrowser.open(MANUAL_URL)
        except Exception:
            pass
        return

    # 离线：显示 QR 弹窗
    def _show_qr():
        import tkinter as tk
        try:
            from shared._qr import generate
            matrix, size = generate(MANUAL_URL.encode())
        except Exception:
            return

        root = tk.Tk()
        root.title("使用手册")
        root.resizable(False, False)
        root.configure(bg="white")
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        cell = 8; pad = 20; cw = size * cell + pad * 2
        root.geometry(f"{cw + 40}x{cw + 120}")
        _font_title = ("", 18, "bold")
        _font_text = ("", 12)

        tk.Label(root, text="📖 使用手册", font=_font_title, bg="white", fg="#111").pack(pady=(18, 0))
        tk.Label(root, text="已检测到离线环境，自动展示二维码",
                font=_font_text, bg="white", fg="#666").pack(pady=(6, 0))

        c = tk.Canvas(root, width=cw, height=cw, highlightthickness=0, bg="white")
        c.pack(pady=(14, 18))
        c.create_rectangle(0, 0, cw, cw, fill="white", outline="#ddd")
        for r in range(size):
            for col in range(size):
                if matrix[r][col]:
                    x = pad + col * cell; y = pad + r * cell
                    c.create_rectangle(x, y, x + cell, y + cell, fill="black", outline="")

        root.mainloop()

    threading.Thread(target=_show_qr, daemon=True).start()

_browse_busy = False

def _browse_script(ev):
    """Fusion 原生文件选择器（零子进程、零 Dock 图标）"""
    global _browse_busy, _SCRIPT_SRC_PATH
    if _browse_busy: return
    _browse_busy = True
    itm["btn_browse_script"].Enabled = False
    try:
        itm[HINT_LB].Text = "正在打开文件选择器..."
        path = fu.RequestFile()
        if path:
            _SCRIPT_SRC_PATH = path
            itm[EDIT_SCRIPT_SRC].Text = os.path.basename(path)
            _on_script_src_changed()
            _action_log(f"📂 选择剧本: {path}")
            itm[HINT_LB].Text = f"已选择: {os.path.basename(path)}"
        else:
            itm[HINT_LB].Text = "请点击「开始检查」"
    except Exception as e:
        _action_log(f"⚠ 文件选择失败: {e}")
        itm[HINT_LB].Text = "文件选择失败"
    finally:
        _browse_busy = False
        itm["btn_browse_script"].Enabled = True
dlg.On["btn_browse_script"].Clicked = _browse_script

# 一键更新
_UPDATING = False
_UPDATE_INFO = {}  # 版本检查结果，防止 NameError
_update_result_path = ""  # 更新检测子进程结果文件
_fc_result_path = ""  # FC 验证子进程结果文件

def _do_update(ev):
    """弹更新日志 → 确认后一直留在屏幕上 → 下载完成变关闭按钮"""
    global _UPDATING
    if _BUSY or _UPDATING or not _UPDATE_INFO.get("update_available"):
        return

    notes = _UPDATE_INFO.get("notes", "") or "暂无更新说明"
    new_ver = _UPDATE_INFO.get("latest", "?")
    try: from config import __version__ as _cur_ver
    except Exception: _cur_ver = "?"
    notes = f"当前版本 {_cur_ver} → {new_ver}\n\n{notes}"
    CX, CY, CW, CH = 180, 120, 440, 380
    update_disp = bmd.UIDispatcher(fu.UIManager)
    _items = {}

    _items["up_icon"]   = ui.Label({"ID": "up_icon", "Text": "🎉", "StyleSheet": "font-size:22px", "Weight": 0})
    _items["up_title"]  = ui.Label({"ID": "up_title", "Text": f"新版本 v{new_ver}",
                                    "StyleSheet": "font-size:16px;font-weight:bold;color:rgb(255,255,255)", "Weight": 0})
    _items["up_body"]   = ui.TextEdit({"ID": "up_body", "ReadOnly": True, "Text": notes,
                                    "Weight": 1,
                                    "StyleSheet": "font-size:13px;color:rgb(200,200,200);background-color:rgb(30,30,30);"
                                                  "border:1px solid rgb(50,50,50);border-radius:4px;padding:8px"})
    _items["up_status"] = ui.Label({"ID": "up_status", "Text": "",
                                    "StyleSheet": "font-size:12px;color:rgb(140,140,140)", "Weight": 0})
    _items["updateNotesCancel"] = ui.Button({"ID": "updateNotesCancel", "Text": "取消",
                                    "StyleSheet": BTN_STYLE_SM, "Weight": 0, "MinimumSize": [80, SIZE_BTN_H]})
    _items["updateNotesGo"]     = ui.Button({"ID": "updateNotesGo", "Text": "立即更新",
                                    "StyleSheet": "background-color:rgb(60,140,220);color:#fff;font-size:13px;font-weight:bold;border-radius:3px;padding:4px 16px",
                                    "Weight": 0, "MinimumSize": [88, SIZE_BTN_H]})

    dlg = update_disp.AddWindow(
        {"WindowTitle": "更新", "ID": "updateNotesDlg",
         "Geometry": [CX, CY, CW, CH], "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True}},
        [ui.VGroup({"Spacing": 8},
         [ui.HGroup({"Spacing": 8, "Weight": 0}, [_items["up_icon"], _items["up_title"]]),
          _items["up_body"], _items["up_status"],
          ui.HGroup({"Spacing": 14, "Weight": 0},
           [ui.HGap({"Weight": 1}), _items["updateNotesCancel"], _items["updateNotesGo"]])])])
    dlg.Show()
    _items = dlg.GetItems()
    _action_log(f"🪟 更新弹窗: 标题=新版本 v{new_ver}, 按钮=立即更新|取消")

    _go_clicked = [False]

    def _cancel(ev):
        _action_log("🪟 取消")
        dlg.Hide(); update_disp.ExitLoop()

    def _go(ev):
        if _go_clicked[0]:
            _action_log("🪟 关闭"); dlg.Hide(); update_disp.ExitLoop(); return
        _go_clicked[0] = True
        _action_log("🪟 开始下载")
        _items["updateNotesGo"].Text = "下载中…"; _items["updateNotesGo"].Enabled = False
        _items["up_status"].Text = "⏳ 准备下载…"

        try:
            import importlib, shared.updater as _upd, config as _cfg
            importlib.reload(_upd)
            r = _upd.check("delivery_checker", _cfg.__version__)
            if r.get("update_available"): _UPDATE_INFO.update(r)
        except Exception: pass

        try:
            def _update_progress(downloaded, total):
                if total:
                    pct = downloaded * 100 // total
                    bar_fill = pct // 5
                    bar = "█" * bar_fill + "░" * (20 - bar_fill)
                    _items["up_status"].Text = f"⬇ [{bar}] {pct}% {downloaded//1024}/{total//1024}KB"
                else:
                    _items["up_status"].Text = f"⬇ {downloaded//1024}KB 已下载"
            _UPDATING = True
            _do_update_sync(progress_callback=_update_progress)
            _items["up_icon"].Text = "✅"
            _items["up_title"].Text = "更新完成"
            _items["up_body"].PlainText = "请重启达芬奇插件生效"
            _items["up_status"].Text = ""
            _action_log("🪟 ✅更新完成")
        except Exception as e:
            _items["up_icon"].Text = "❌"
            _items["up_title"].Text = "更新失败"
            # 翻译常见错误为人话
            _err_raw = str(e)
            if "timeout" in _err_raw.lower() or "timed out" in _err_raw.lower():
                _err_friendly = "下载超时，请检查网络后重试"
            elif "certificate" in _err_raw.lower() or "ssl" in _err_raw.lower():
                _err_friendly = "网络连接不安全，请检查系统时间或关闭代理"
            elif "all links" in _err_raw.lower() or "链路均不可达" in _err_raw:
                _err_friendly = "所有下载链路均不可达，请稍后重试"
            else:
                _err_friendly = f"下载失败，请稍后重试"
            _items["up_body"].PlainText = _err_friendly
            _items["up_status"].Text = ""
            _action_log(f"🪟 ❌更新失败: {_err_raw[:80]}")
        _UPDATING = False
        _items["updateNotesGo"].Text = "关闭"; _items["updateNotesGo"].Enabled = True

    dlg.On["updateNotesGo"].Clicked = _go
    dlg.On["updateNotesCancel"].Clicked = _cancel
    dlg.On["updateNotesDlg"].Close = _cancel

    update_disp.RunLoop()
    del update_disp

# ======================================================================
#  Windows 增量更新支持（自提权 + 自包含安装脚本）
#  等价 Mac 的 osascript administrator 弹密码：Windows 弹一次 UAC。
# ======================================================================
def _generate_win_update_bat(plugin_root):
    """运行时生成自包含安装脚本：把 plugin_root 复制到系统安装目录。"""
    import tempfile
    _bat = os.path.join(tempfile.gettempdir(), "deli_install_update.bat")
    _content = (
        "@echo off\n"
        "chcp 65001 >nul\n"
        "set \"SRC=%~2\"\n"
        "if \"%SRC%\"==\"\" set \"SRC=%~1\"\n"
        "if \"%SRC%\"==\"\" (echo SRC_MISSING>\"%PROGRAMDATA%\\deli_update_result.txt\" & exit /b 2)\n"
        "set \"DST=%PROGRAMDATA%\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\交付自检工具\"\n"
        "if not exist \"%DST%\" mkdir \"%DST%\"\n"
        "robocopy \"%SRC%\" \"%DST%\" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul\n"
        "if errorlevel 8 (echo FAILED>\"%PROGRAMDATA%\\deli_update_result.txt\" & exit /b 1)\n"
        "echo OK>\"%PROGRAMDATA%\\deli_update_result.txt\"\n"
        "exit /b 0\n"
    )
    with open(_bat, "w", encoding="utf-8") as _f:
        _f.write(_content)
    return _bat

def _read_update_result():
    _p = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "deli_update_result.txt")
    try:
        with open(_p, encoding="utf-8") as _f:
            return _f.read().strip()
    except Exception:
        return None

def _run_elevated_windows(bat_path, plugin_root):
    """以管理员身份运行 bat（弹一次 UAC），等价 Mac 输密码。返回进程退出码。"""
    import ctypes
    from ctypes import wintypes, Structure, byref, c_ulong, c_void_p, c_int
    _SEE_MASK_NOCLOSEPROCESS = 0x00000040
    _SW_HIDE = 0

    class _SHELLEXECUTEINFO(Structure):
        _fields_ = [
            ("cbSize", c_ulong),
            ("fMask", c_ulong),
            ("hwnd", c_void_p),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", c_int),
            ("hInstApp", c_void_p),
            ("lpIDList", c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hKeyClass", c_void_p),
            ("dwHotKey", c_ulong),
            ("hIconOrMonitor", c_void_p),
            ("hProcess", c_void_p),
        ]
    _params = '/c "{0}" --update "{1}"'.format(bat_path, plugin_root)
    _sei = _SHELLEXECUTEINFO()
    _sei.cbSize = ctypes.sizeof(_sei)
    _sei.fMask = _SEE_MASK_NOCLOSEPROCESS
    _sei.hwnd = None
    _sei.lpVerb = "runas"
    _sei.lpFile = "cmd.exe"
    _sei.lpParameters = _params
    _sei.lpDirectory = None
    _sei.nShow = _SW_HIDE
    _sei.hInstApp = None
    _sei.lpIDList = None
    _sei.lpClass = None
    _sei.hKeyClass = None
    _sei.dwHotKey = 0
    _sei.hIconOrMonitor = None
    _sei.hProcess = None
    if not ctypes.windll.shell32.ShellExecuteExW(byref(_sei)):
        return 1223  # 用户拒绝 UAC 或触发失败
    _hproc = _sei.hProcess
    ctypes.windll.kernel32.WaitForSingleObject(_hproc, 600000)  # 最多等 10 分钟
    _ec = c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(_hproc, byref(_ec))
    ctypes.windll.kernel32.CloseHandle(_hproc)
    return _ec.value

def _do_update_sync(progress_callback=None):
    """同步下载 + 安装 — 每步写日志方便远程监控。progress_callback(downloaded, total)"""
    from urllib.request import Request, urlopen
    from urllib.parse import quote, urlparse, urlunparse
    import json, subprocess, tempfile, zipfile, shlex, ssl, base64, hashlib
    from shared.update_config import (
        TIMEOUT_DOWNLOAD_SINGLE, TIMEOUT_INSTALL, MIN_DOWNLOAD_SIZE, UPDATE_FILE
    )
    _ctx = ssl._create_unverified_context()

    url = _UPDATE_INFO.get("urls", "")
    urls = url if isinstance(url, list) else ([url] if url else [])
    if not urls:
        raise RuntimeError("更新地址无效")
    expected_sha256 = _UPDATE_INFO.get("sha256")
    _action_log(f"📦 下载链路: {len(urls)} 条, 第一条: {urls[0][:60]}...")

    try:
        data = None
        errors = []  # 记录每条链路的失败原因
        _tmp_dir = None
        for idx, dl_url in enumerate(urls):
            _action_log(f"⬇ 下载 [{idx+1}/{len(urls)}]: {dl_url}")
            try:
                p = urlparse(dl_url)
                safe = urlunparse(p._replace(path=quote(p.path, safe='/')))
                req = Request(safe)
            except Exception as e:
                errors.append(f"{dl_url[:60]}: {e}"); continue
            try:
                req.add_header("User-Agent", "DaVinciPlugin/delivery_checker")
                # 先 HEAD 拿文件大小
                head_req = Request(safe, method="HEAD")
                head_req.add_header("User-Agent", "DaVinciPlugin/delivery_checker")
                total_size = 0
                try:
                    with urlopen(head_req, timeout=10, context=_ctx) as hr:
                        total_size = int(hr.getheader("Content-Length", 0))
                except Exception:
                    pass
                _action_log(f"   ⬇ [{idx+1}/{len(urls)}] {dl_url[:80]}... size={total_size//1024}KB" if total_size else f"   ⬇ [{idx+1}/{len(urls)}] {dl_url[:80]}...")
                with urlopen(req, timeout=TIMEOUT_DOWNLOAD_SINGLE, context=_ctx) as resp:
                    chunks = []
                    downloaded = 0
                    CHUNK = 8192
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            try:
                                progress_callback(downloaded, total_size)
                            except Exception:
                                pass
                    data = b"".join(chunks)
                if data and len(data) >= MIN_DOWNLOAD_SIZE:
                    if data[:4] != b'PK\x03\x04':
                        errors.append(f"{dl_url[:60]}: 响应不是 zip")
                        continue
                    break
                errors.append(f"{dl_url[:60]}: 下载文件无效")
            except Exception as e:
                errors.append(f"{dl_url[:60]}: {e}")
                continue
        if not data:
            err_detail = "; ".join(errors) if errors else "无"
            raise RuntimeError(f"所有下载链路失败 ({len(errors)}条): {err_detail}")

        # GitHub API base64 解码
        try:
            api_data = json.loads(data.decode("utf-8"))
            if isinstance(api_data, dict) and api_data.get("encoding") == "base64":
                data = base64.b64decode(api_data["content"])
                _action_log(f"   解码 API: {len(data)//1024}KB")
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            pass

        # SHA256 校验
        if expected_sha256:
            got = hashlib.sha256(data).hexdigest()
            if got != expected_sha256:
                raise RuntimeError(f"SHA256 校验失败: {got[:16]}... ≠ {expected_sha256[:16]}...")
            _action_log("   SHA256 ✓")
        _action_log(f"   📦 下载完成: {len(data)//1024}KB, 开始安装…")
        # ---- 跨平台：准备临时目录（Windows→%TEMP%，Mac→/var/folders）----
        _tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(_tmp_dir, "update.zip")
        with open(zip_path, "wb") as f:
            f.write(data)
        with zipfile.ZipFile(zip_path, metadata_encoding="utf-8") as zf:
            zf.extractall(_tmp_dir)

        # 找插件根目录（含 shell_personal.py 的那个目录）
        _plugin_root = None
        for _root, _dirs, _files in os.walk(_tmp_dir):
            if "shell_personal.py" in _files:
                _plugin_root = _root
                break
        if not _plugin_root:
            raise RuntimeError("更新包中未找到插件文件 (shell_personal.py)")

        # ---- 查找安装脚本：优先同包内，其次已装目录兜底，再次运行时生成 ----
        _is_win = sys.platform.startswith("win")
        cmd = None
        if _is_win:
            for _r, _, _fs in os.walk(_tmp_dir):
                if "install_update.bat" in _fs:
                    cmd = os.path.join(_r, "install_update.bat"); break
        else:
            for _r, _, _fs in os.walk(_tmp_dir):
                if "install_update.command" in _fs:
                    cmd = os.path.join(_r, "install_update.command"); break
        if not cmd:
            # 已安装目录里的兜底脚本
            _fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "install_update.bat" if _is_win else "install_update.command")
            if os.path.exists(_fallback):
                cmd = _fallback
        if not cmd and _is_win:
            cmd = _generate_win_update_bat(_plugin_root)   # 运行时自生成，自包含
        if not cmd:
            raise RuntimeError("安装包中未找到安装脚本")

        _action_log("   → 开始安装更新…")
        if _is_win:
            # Windows：自提权运行（等价 Mac 输密码，弹一次 UAC）
            _rc = _run_elevated_windows(cmd, _plugin_root)
            if _rc != 0:
                _err = _read_update_result() or f"安装失败 (错误码 {_rc})"
                if _rc in (1223, 2):
                    _err = "更新已取消"
                raise RuntimeError(_err)
        else:
            os.chmod(cmd, 0o755)
            script = f'do shell script "/bin/bash {shlex.quote(cmd)} --update" with administrator privileges'
            result = subprocess.run(["osascript", "-e", script], timeout=TIMEOUT_INSTALL,
                                    capture_output=True, start_new_session=True,
                                    env={**os.environ, "TERM": "dumb"})
            if result.returncode != 0:
                # 解析 osascript 返回码，转为人话
                if result.returncode == 1:
                    try:
                        stderr_text = result.stderr.decode('utf-8', errors='replace').strip()
                    except Exception:
                        stderr_text = ""
                    if "-128" in stderr_text:
                        err = "更新已取消"
                    elif "not found" in stderr_text.lower() or "no such file" in stderr_text.lower():
                        err = "未找到安装脚本，请重新下载更新包"
                    elif stderr_text:
                        err = f"安装失败: {stderr_text.split(chr(10))[0][:100]}"
                    else:
                        err = "安装失败，请重试"
                else:
                    err = f"安装失败 (错误码 {result.returncode})"
                raise RuntimeError(err)
        itm[HINT_LB].Text = "✅ 更新完成！请重启达芬奇插件生效"
        itm[BTN_UPDATE].Text = "✅"
        _unlock_ui()
        _UPDATING = False
        _action_log("✅ 更新完成，等待重启达芬奇")
    except Exception as e:
        _action_log(f"❌ 更新失败: {e}")
        _ui_error_state["count"] += 1
        _update_err_counter()
        raise
    finally:
        if _tmp_dir:
            import shutil; shutil.rmtree(_tmp_dir, ignore_errors=True)
dlg.On[BTN_UPDATE].Clicked = _do_update
dlg.On[BTN_MANUAL].Clicked = _on_manual

# 剧本链接格式校验
def _on_script_src_changed(_=None):
    src = _SCRIPT_SRC_PATH or itm[EDIT_SCRIPT_SRC].Text.strip()
    if not src or src == "选填，提供剧本可启用 AI 错别字校对":
        return
    ok = any(src.startswith(p) for p in (
        "https://", "http://", "/Volumes/", "smb://", "~/", "/"))
    if "feishu.cn" in src or "docs.qq.com" in src:
        ok = ok and len(src) > 30
        # 飞书/腾讯文档: 格式校验 + 显示名称
        if "feishu.cn" in src or "docs.qq.com" in src:
            ok = ok and len(src) > 30
            if "feishu.cn" in src:
                from script_parser import _normalize_feishu_url
                normalized = _normalize_feishu_url(src)
                disp = "飞书文档" if normalized.startswith("feishu_docx:") else \
                       "飞书文件" if normalized.startswith("feishu_file:") else \
                       "飞书文件夹" if normalized.startswith("feishu_folder:") else \
                       "飞书链接"
                itm[EDIT_SCRIPT_SRC].Text = disp
                itm[HINT_LB].Text = f"已选择: {disp}"
    if not ok and src:
        _action_log(f"⚠ 剧本链接格式异常: {src[:60]}...")

# 🔗 粘贴链接（tkinter 弹窗，跨平台统一）
_link_busy = False
def _paste_link(ev):
    global _link_busy, _SCRIPT_SRC_PATH
    if _link_busy: return
    _link_busy = True
    itm["btn_paste_link"].Enabled = False
    from tk_dialogs import input_text
    try:
        val = input_text("粘贴飞书链接", title="交付自检工具")
        if val:
            _SCRIPT_SRC_PATH = val
            _on_script_src_changed()
            _action_log(f"🔗 粘贴链接: {val[:60]}...")
    finally:
        _link_busy = False
        itm["btn_paste_link"].Enabled = True

dlg.On["btn_paste_link"].Clicked = _paste_link

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
        sg = text_stripped[2:]
        parent_group = item.Text[1] if item.Text[1] else ""
        _render_group(sg, _cached_sections, tree, parent_group=parent_group)
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
    # 个人版：从安装目录加载 .env API Key
    _here = os.path.dirname(os.path.abspath(__file__))
    _dotenv = os.path.join(_here, ".env")
    if os.path.exists(_dotenv):
        try:
            with open(_dotenv, encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip("'\"")
                        if _v:
                            os.environ[_k] = _v
        except Exception:
            pass
    # api_keys.json 的 key 通过 Keychain 读取 → 注入 os.environ
    # .env 是安装时的种子，之后 Keychain 是唯一存储源
    _ENV_MAP = {
        "deepseek_key": "DEEPSEEK_API_KEY",
        "feishu_app_id": "FEISHU_BOT_APP_ID",
        "feishu_secret": "FEISHU_BOT_APP_SECRET",
    }
    try:
        from secure_store import load_all, migrate_legacy
        _keystore = load_all()
        if not _keystore:
            migrate_legacy()
            _keystore = load_all()
        for _k, _env_k in _ENV_MAP.items():
            if _keystore.get(_k):
                os.environ[_env_k] = _keystore[_k]
        _action_log("🔐 Keychain 凭证已注入环境变量")
    except Exception as _e:
        _action_log("⚠ Keychain 不可用，使用 .env 兜底")

    _action_log("═══ 交付自检 启动 v" + version_string() + " ═══")
    # 防重复窗口（PID 锁文件，跨进程可用）
    _lock_file = os.path.join(_here, ".ui_instance.lock")
    if os.path.exists(_lock_file):
        try:
            with open(_lock_file, encoding="utf-8") as f:
                _old_pid = int(f.read().strip())
            os.kill(_old_pid, 0)  # 进程存在 → 已有一个窗口
            sys.exit(0)
        except (ProcessLookupError, PermissionError, ValueError):
            pass  # 锁文件残留，清理后继续
    with open(_lock_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    # ── 启动时灰按钮 + 联网校验（单线程，零竞态）──
    itm[TRIAL_LB].Text = "⏳ 联网校验中…"
    itm[BTN_START].Enabled = False
    itm[BTN_AI_TYPO].Enabled = False
    itm[BTN_CONFIG].Enabled = False
    itm[BTN_UPDATE].Enabled = False
    itm[HINT_LB].Text = ""
    dlg.Show()
    dlg.RecalcLayout()
    _init_connection()

    # ══ License ══（仅个人版，同步校验）
    global _ai_allowed, _trial_expired
    _ai_allowed = True
    _trial_expired = False
    _cred = None
    if IS_PERSONAL:
        try:
            from shared.license import init_trial, verify_local, verify_activation, load_credential
            cred = load_credential()
            _cred = cred
            if cred:
                ok, msg = verify_local()
                cred = load_credential()
                _cred = cred
                p = cred.get("payload", {})
                is_trial = p.get("is_trial", True)
                if is_trial:
                    tsd = p.get("trial_start_date")
                    if tsd:
                        from datetime import date as _dt_date
                        elapsed = (_dt_date.today() - _dt_date.fromordinal(tsd)).days
                        if elapsed < 0:
                            text = "试用权限异常，请联系裁缝老师"
                            _ai_allowed = False
                        else:
                            d = trial_days_left(tsd)
                            text = format_trial(d)
                            _ai_allowed = d > 0
                            if not _ai_allowed:
                                _trial_expired = True
                    else:
                        d = max(0, (p.get("expire_time", 0) - int(time.time())) // 86400)
                        text = format_trial(d)
                        _ai_allowed = d > 0
                        if not _ai_allowed:
                            _trial_expired = True
                else:
                    text = "已激活 ✓"
                    # 后台子进程验证 FC（不阻塞启动），verify_local 已通过
                    global _fc_result_path
                    import tempfile as _tmp_fc
                    _fc_result_path = os.path.join(_tmp_fc.gettempdir(), f"dv_fc_{os.getpid()}.json")
                    try:
                        _shared_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared")
                        _script_dir = os.path.dirname(os.path.abspath(__file__))
                        _check_code = f'''import sys,json,os
sys.path.insert(0,r"{_shared_dir}")
sys.path.insert(0,r"{_script_dir}")
from shared.license import verify_activation
try:
    ok,msg=verify_activation(_writeback=False)
    with open(sys.argv[1],"w") as f:json.dump({{"ok":ok,"msg":msg}},f)
except Exception as e:
    with open(sys.argv[1],"w") as f:json.dump({{"ok":False,"error":str(e)}},f)
'''
                        subprocess.Popen([sys.executable, "-c", _check_code, _fc_result_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception: pass
                itm[TRIAL_LB].Text = text
                _action_log(f"License: {text}  ({'✅' if ok else '❌ '+msg})")
            else:
                ok, msg = init_trial()
                if ok:
                    cred = load_credential()
                    _cred = cred
                    if cred:
                        p = cred.get("payload", {})
                        tsd = p.get("trial_start_date")
                        if tsd:
                            from datetime import date as _dt_date
                            d = trial_days_left(tsd)
                        else:
                            d = max(0, (p.get("expire_time", 0) - int(time.time())) // 86400)
                        text = format_trial(d)
                        _ai_allowed = d > 0
                    else:
                        text = msg
                else:
                    text = msg
                    _ai_allowed = False
                itm[TRIAL_LB].Text = text
                _action_log(f"License试用: {'✅' if ok else '❌'} → 显示: \"{text}\"")
        except Exception as e:
            _action_log(f"License异常: {type(e).__name__}: {e}")
            _ai_allowed = False
        if not _ai_allowed:
            itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"
            itm[BTN_AI_TYPO].Enabled = False
            fp = (_cred or {}).get("payload", {}).get("machine_fingerprint", "")
            fp_short = fp[:8] if fp else ""
            if _trial_expired:
                itm[TRIAL_LB].Text = format_trial(0, fp_short)
            else:
                itm[TRIAL_LB].Text = f"{itm[TRIAL_LB].Text}  |  ID: {fp_short}" if fp_short else itm[TRIAL_LB].Text
            if not _cred:
                itm[HINT_LB].Text = ""
    else:
        # 公司版：无 License，清除 ⏳ 占位
        itm[TRIAL_LB].Text = ""
        _action_log("公司版，跳过 License 校验")

    # ── 恢复按钮 ──
    itm[BTN_START].Enabled = True
    itm[BTN_CONFIG].Enabled = True
    itm[BTN_UPDATE].Enabled = True
    itm[BTN_AI_TYPO].Enabled = _ai_allowed
    if not itm[HINT_LB].Text:
        itm[HINT_LB].Text = "请点击「开始检查」"
    if itm[TRIAL_LB].Text.startswith("⏳"):
        itm[TRIAL_LB].Text = "试用权限异常，请联系裁缝老师"

    # ── 后台检查更新 ──
    itm[BTN_UPDATE].Visible = True
    itm[BTN_UPDATE].Text = "⏳ 检查更新中…"
    itm[BTN_UPDATE]["StyleSheet"] = "color:#888;font-size:11px;border-radius:3px;padding:2px 8px;background-color:#3a3a3a"
    import tempfile as _tmp
    global _update_result_path
    _update_result_path = os.path.join(_tmp.gettempdir(), f"dv_update_{os.getpid()}.json")
    _subp = None
    try:
        _shared_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared")
        _check_code = f'''import sys,json,time
sys.path.insert(0,"{_shared_dir}")
from updater import check
r=check("delivery_checker",sys.argv[1],timeout=3)
with open(sys.argv[2],"w") as f:json.dump(r,f)
'''
        _action_log(f"🔍 更新子进程: py={sys.executable[-40:]}, shared_exists={os.path.exists(_shared_dir)}")
        _subp = subprocess.Popen([sys.executable, "-c", _check_code, __version__, _update_result_path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as e:
        _action_log(f"⚠ 更新子进程启动失败: {e}")

    # 等子进程写出结果（最多 3s）
    import time as _poll_t
    _t0 = _poll_t.time()
    for _ in range(30):
        if os.path.exists(_update_result_path):
            break
        _poll_t.sleep(0.1)
    _elapsed = _poll_t.time() - _t0
    _found = os.path.exists(_update_result_path)

    # 读结果
    _result = None
    if _found and _update_result_path:
        try:
            import json as _json
            with open(_update_result_path) as f: _result = _json.load(f)
        except Exception: pass
        try: os.remove(_update_result_path)
        except OSError: pass

    # 如果没结果且子进程还在，读 stderr 诊断
    _stderr_msg = ""
    if not _result and _subp:
        try:
            _, _stderr = _subp.communicate(timeout=1)
            _stderr_msg = _stderr.decode("utf-8", errors="replace")[:200] if _stderr else ""
        except Exception: pass

    # ── 面板更新 ──
    if _result and _result.get("update_available"):
        # 状态 A: 有更新
        global _UPDATE_INFO
        _UPDATE_INFO = _result
        _action_log(f"⬆ 发现新版本 v{_result['latest']} (当前 {__version__})")
        itm[HINT_LB].Text = f"⬆ 新版本 v{_result['latest']} — 点击右侧按钮更新"
        itm[BTN_UPDATE].Text = "⬆ 更新"
        itm[BTN_UPDATE]["StyleSheet"] = "background-color:rgb(220,180,60);color:#1a1a1a;font-size:11px;font-weight:bold;border-radius:3px;padding:2px 8px"
        if _result.get("force"):
            itm[BTN_START].Enabled = False
            itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"
            itm[HINT_LB].Text += "（必须更新）"
    elif not _found:
        # 状态 B: 子进程没写结果（崩溃/超时/网络不通）
        itm[BTN_UPDATE].Text = "⚠ 检查失败"
        itm[BTN_UPDATE]["StyleSheet"] = "color:#e88;font-size:11px;border-radius:3px;padding:2px 8px;background-color:#3a3a3a"
        _action_log(f"⚠ 更新检测失败 (elapsed={_elapsed:.1f}s, err={_stderr_msg[:80]})")
    else:
        # 状态 C: 没有新版本
        itm[BTN_UPDATE].Text = "✓ 已是最新"
        itm[BTN_UPDATE]["StyleSheet"] = "color:#8a8;font-size:11px;border-radius:3px;padding:2px 8px;background-color:#3a3a3a"
        _action_log(f"🔍 更新检测: 已是最新 v{_result.get('latest','?') if _result else '?'}, elapsed={_elapsed:.1f}s, stderr={_stderr_msg[:50]}")

    # 读 FC 验证结果
    if _fc_result_path and os.path.exists(_fc_result_path):
        _r = None
        try:
            with open(_fc_result_path) as f: _r = json.load(f)
        except Exception: pass
        try: os.remove(_fc_result_path)
        except OSError: pass
        if _r and isinstance(_r, dict) and _r.get("ok") is False:
            _ai_allowed = False; _trial_expired = True
            _action_log(f"License 吊销: {_r.get('msg')}")
            itm[TRIAL_LB].Text = format_trial(0)
            itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"
            itm[BTN_AI_TYPO].Enabled = False

    disp.RunLoop()
    dlg.Hide()
    # os._exit 跳过 C++ 全局析构，避免 fusionscript.so 的
    # ReusePoolManager::~ReusePoolManager SIGSEGV（DaVinci 20.3.2 已知 bug）
    os._exit(0)

if __name__ == "__main__":
    main()
