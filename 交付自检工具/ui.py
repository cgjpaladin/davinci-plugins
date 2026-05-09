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
from check_core import check_track_structure, check_subtitle_clamping, check_disabled_items

# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════
WIN_ID = "com.myjc.delivery_checker"

# 控件 ID
CHK_TRACK, CHK_SUBTITLE, CHK_BLACK, CHK_DISABLED = \
    "chk_track", "chk_subtitle", "chk_black", "chk_disabled"
LBL_SUB_VAL, LBL_VID_VAL, LBL_AUD_VAL = "lbl_sub", "lbl_vid", "lbl_aud"
EDIT_SUB, EDIT_VID, EDIT_AUD = "edit_sub", "edit_vid", "edit_aud"
BTN_EDIT_TRACK = "btn_edit_track"
BTN_SAVE_TRACK = "btn_save_track"
LBL_CLAMP_VAL = "lbl_clamp"
EDIT_CLAMP = "edit_clamp"
BTN_EDIT_CLAMP = "btn_edit_clamp"
BTN_SAVE_CLAMP = "btn_save_clamp"
BTN_START = "btn_start"
TREE_RESULT = "tree_result"
ST_LB = "st_lb"
HINT_LB = "hint_lb"

# ── 结果列定义：加/删/挪/开关列只改这里 ──
#   enabled=False → 列暂时隐藏，不删定义
COLUMNS = [
    {"header": "状态", "width": 40,  "key": "icon",  "enabled": True},
    {"header": "轨道", "width": 50,  "key": "track", "enabled": True},
    {"header": "位置", "width": 100, "key": "tc",    "enabled": True},
    {"header": "详情", "width": 480, "key": "msg",   "enabled": True},
]

# 当前启用的列（enabled=True）
_ENABLED_COLS = [c for c in COLUMNS if c.get("enabled", True)]


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
    """轨道结构检查"""
    return check_track_structure(timeline, *_track_values)

def _run_clamp_check(timeline, fps):
    """字幕夹帧检查"""
    return check_subtitle_clamping(timeline, _clamp_value, fps)

def _run_disabled_check(timeline, fps):
    """启用/禁用检查"""
    return check_disabled_items(timeline, fps)

CHECKS = [
    {"id": "track",            "section": "轨道结构", "chk_id": CHK_TRACK,    "run_fn": _run_track_check},
    {"id": "subtitle_clamp",   "section": "字幕长度", "chk_id": CHK_SUBTITLE, "run_fn": _run_clamp_check},
    {"id": "subtitle_disabled","section": "启用/禁用", "chk_id": CHK_DISABLED, "run_fn": _run_disabled_check},
    {"id": "black_border",     "section": "黑边检测", "chk_id": CHK_BLACK,    "run_fn": None},
]
# 扩展指南：
#   - 加新检查：往 CHECKS 末尾加一行 dict，写 run_fn
#   - 换位置：移动 list 中 dict 的位置
#   - 暂时关闭：run_fn 设为 None
#   - 如果新检查需要专属 CheckBox，在控件 ID 区和 UI 布局区加对应行

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════
_track_values = [DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS]
_track_editing = False
_clamp_value = DEFAULT_CLAMP_THRESHOLD
_clamp_editing = False
_checking = False

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

window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # ── 上半区：检查选项 + 开始按钮 ──
        ui.HGroup({"Spacing": 10, "Weight": 0}, [
            # 左侧：三个选项 VGroup
            ui.VGroup({"Spacing": 6, "Weight": 0}, [

            # ① 轨道结构
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_TRACK, "Text": "轨道结构", "Checked": True,
                             "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}),
                ui.Label({"Text": "字幕轨", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_SUB_VAL, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_SUB, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                             "MaximumSize": [24, 22], "Weight": 0}),
                ui.Label({"Text": "视频轨", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_VID_VAL, "Text": str(DEFAULT_VIDEO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_VID, "Text": str(DEFAULT_VIDEO_TRACKS),
                             "MaximumSize": [24, 22], "Weight": 0}),
                ui.Label({"Text": "音频轨", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_AUD_VAL, "Text": str(DEFAULT_AUDIO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_AUD, "Text": str(DEFAULT_AUDIO_TRACKS),
                             "MaximumSize": [24, 22], "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_TRACK, "Text": "✎",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_TRACK, "Text": "✓",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),

            # ② 字幕夹帧
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_SUBTITLE, "Text": "字幕长度", "Checked": True,
                             "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}),
                ui.Label({"Text": "阈值", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_CLAMP_VAL, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_CLAMP, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                             "MaximumSize": [24, 22], "Weight": 0}),
                ui.Label({"Text": "帧", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_CLAMP, "Text": "✎",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_CLAMP, "Text": "✓",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),

            # ③ 启用/禁用检查
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_DISABLED, "Text": "启用/禁用", "Checked": True,
                             "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}),
            ]),

            # ④ 黑边（置灰）
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_BLACK, "Text": "黑边检测 （开发中...）",
                             "Checked": False, "Enabled": False,
                             "StyleSheet": "font-size:13px;color:rgb(100,100,100)", "Weight": 0}),
            ]),

            ]),  # 结束左侧 VGroup

            ui.HGap({"Weight": 1}),  # 弹簧，把按钮推到最右

            # 右侧：开始检查按钮，高度匹配三行
            ui.Button({"ID": BTN_START, "Text": "开始检查",
                       "StyleSheet": BTN_PRIMARY, "Weight": 0,
                       "MinimumSize": [120, _BTN_HEIGHT]}),
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
    "Geometry": [800, 100, 780, 520],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, window_layout)

itm = dlg.GetItems()

# ═══════════════════════════════════════════
# 初始状态
# ═══════════════════════════════════════════
itm[EDIT_SUB].Visible = False
itm[EDIT_VID].Visible = False
itm[EDIT_AUD].Visible = False
itm[BTN_SAVE_TRACK].Visible = False
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

def _render_sections(sections, tree):
    """将检查结果渲染到结果 Tree"""
    for i, sec in enumerate(sections):
        hdr = tree.NewItem()
        hdr_title = sec["title"]
        if sec["all_ok"]:
            hdr_title += "  — 全部通过"
        elif sec["summary"]:
            hdr_title += "  —  " + sec["summary"]
        _set_row_texts(hdr, "▶", "", "", hdr_title)
        tree.AddTopLevelItem(hdr)

        if not sec["all_ok"]:
            for row_data in sec["rows"]:
                row = tree.NewItem()
                _set_row(row, row_data)
                tree.AddTopLevelItem(row)

        # 区域间空行
        if i < len(sections) - 1:
            gap = tree.NewItem()
            _set_row_texts(gap, "", "", "", "")
            tree.AddTopLevelItem(gap)


# ═══════════════════════════════════════════
# 轨道编辑：✎ 进入编辑 / ✓ 保存
# ═══════════════════════════════════════════

def _enter_track_edit():
    """进入轨道编辑模式"""
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
        itm[EDIT_SUB].Visible = False
        itm[EDIT_VID].Visible = False
        itm[EDIT_AUD].Visible = False
        itm[BTN_SAVE_TRACK].Visible = False
        itm[LBL_SUB_VAL].Visible = True
        itm[LBL_VID_VAL].Visible = True
        itm[LBL_AUD_VAL].Visible = True
        itm[BTN_EDIT_TRACK].Visible = True
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
    })
    _action_log(r.get("detail", ""))
    return True, False


# ═══════════════════════════════════════════
# 开始检查
# ═══════════════════════════════════════════

def _start_check():
    global _checking
    if _checking:
        return
    _checking = True
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
                "title": check["section"],
                "summary": summary_text,
                "rows": section_rows,
                "all_ok": all_ok,
            })

        # 按区域展示
        _render_sections(sections, tree)

        # 总结
        if has_failures:
            _action_log("❌ 检查未通过 — 请修复上述问题")
            itm[ST_LB].Text += "  |  ❌ 未通过"
        else:
            _action_log("✅ 所有检查通过")
            itm[ST_LB].Text += "  |  ✅ 通过"
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
