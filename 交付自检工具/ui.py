# -*- coding: utf-8 -*-
"""
交付自检工具 UI — 外部进程版

绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
使用 fusionscript_loader 连接 Resolve。
"""
import json
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
from check_core import check_track_structure, check_subtitle_clamping, check_disabled_subtitles

# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════
WIN_ID = "com.myjc.delivery_checker"

# 控件 ID
CHK_TRACK, CHK_SUBTITLE, CHK_BLACK = "chk_track", "chk_subtitle", "chk_black"
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
LOG_TE = "log_te"
ST_LB = "st_lb"

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


def _action_log(msg: str, to_ui: bool = True):
    """记录操作日志：SMB 文件（始终）+ UI TextEdit（可选）"""
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

    # UI
    if to_ui:
        _ui_log(line)


def _ui_log(msg: str):
    """追加到 UI 日志区（TextEdit）"""
    try:
        te = itm[LOG_TE]
        te.Append(msg + "\n")
        te.MoveCursor("End", "MoveAnchor")
        te.EnsureCursorVisible()
    except Exception:
        pass


# ═══════════════════════════════════════════
# UI 布局
# ═══════════════════════════════════════════
_CHECK_ROW_STYLE = "font-size:13px;color:rgb(220,220,220)"

window_layout = [
    ui.VGroup({"Spacing": 0}, [

        # ── 上半区：检查选项 ──
        ui.VGroup({"Spacing": 6, "Weight": 0}, [

            # ① 轨道结构
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_TRACK, "Text": "轨道结构", "Checked": True,
                             "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}),
                ui.Label({"Text": "字幕", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_SUB_VAL, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_SUB, "Text": str(DEFAULT_SUBTITLE_TRACKS),
                             "MaximumSize": [30, 22], "Weight": 0}),
                ui.Label({"Text": "视频", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_VID_VAL, "Text": str(DEFAULT_VIDEO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_VID, "Text": str(DEFAULT_VIDEO_TRACKS),
                             "MaximumSize": [30, 22], "Weight": 0}),
                ui.Label({"Text": "音频", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_AUD_VAL, "Text": str(DEFAULT_AUDIO_TRACKS),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_AUD, "Text": str(DEFAULT_AUDIO_TRACKS),
                             "MaximumSize": [30, 22], "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_TRACK, "Text": "✎",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_TRACK, "Text": "✓",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),

            # ② 字幕夹帧
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_SUBTITLE, "Text": "字幕夹帧", "Checked": True,
                             "StyleSheet": _CHECK_ROW_STYLE, "Weight": 0}),
                ui.Label({"Text": "阈值", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Label({"ID": LBL_CLAMP_VAL, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                          "StyleSheet": LABEL_GRAY, "Weight": 0}),
                ui.LineEdit({"ID": EDIT_CLAMP, "Text": str(DEFAULT_CLAMP_THRESHOLD),
                             "MaximumSize": [30, 22], "Weight": 0}),
                ui.Label({"Text": "帧", "StyleSheet": LABEL_DIM, "Weight": 0}),
                ui.Button({"ID": BTN_EDIT_CLAMP, "Text": "✎",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
                ui.Button({"ID": BTN_SAVE_CLAMP, "Text": "✓",
                           "StyleSheet": BTN_ICON, "Weight": 0}),
            ]),

            # ③ 黑边（置灰）
            ui.HGroup({"Spacing": 6, "Weight": 0}, [
                ui.CheckBox({"ID": CHK_BLACK, "Text": "黑边检测 （开发中...）",
                             "Checked": False, "Enabled": False,
                             "StyleSheet": "font-size:13px;color:rgb(100,100,100)", "Weight": 0}),
            ]),

            # 开始按钮
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.HGap({"Weight": 1}),
                ui.Button({"ID": BTN_START, "Text": "开始检查",
                           "StyleSheet": BTN_PRIMARY, "Weight": 0, "MinimumSize": [120, 32]}),
                ui.HGap({"Weight": 1}),
            ]),
        ]),

        # ── 状态标签 ──
        ui.Label({"ID": ST_LB, "Text": "",
                  "StyleSheet": "color:rgb(180,180,180);font-size:11px;min-height:18px",
                  "Weight": 0}),

        # ── 结果区：Tree（可点击跳转）──
        ui.Tree({"ID": TREE_RESULT, "Weight": 0.4,
                 "Events": {"ItemClicked": True, "ItemDoubleClicked": True}}),

        # ── 日志区：TextEdit ──
        ui.TextEdit({"ID": LOG_TE, "Text": "",
                     "StyleSheet": "color:rgb(200,200,200);background-color:rgb(30,30,30);"
                                   "border:1px solid rgb(50,50,50);border-radius:4px;"
                                   "padding:6px;min-height:80px",
                     "ReadOnly": True, "Weight": 0.6}),

        # ── 底栏 ──
        ui.VGroup({"Spacing": 2, "Weight": 0}, [
            ui.HGroup({"Spacing": 8}, [
                ui.Label({"Text": " ", "Weight": 1}),
                ui.Label({"Text": f"裁缝老师的达芬奇插件工坊 ✂️ | 交付自检 v{__version__}",
                          "StyleSheet": "color:rgb(100,100,100);font-size:10px", "Weight": 0}),
            ]),
        ]),
    ]),
]

dlg = disp.AddWindow({
    "WindowTitle": f"交付自检 v{__version__}",
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
itm[BTN_START].Enabled = False

# Tree 表头
tree = itm[TREE_RESULT]
tree_header = tree.NewItem()
tree_header.Text[0] = "状态"
tree_header.Text[1] = "位置"
tree_header.Text[2] = "详情"
tree.SetHeaderItem(tree_header)
tree.ColumnWidth[0] = 50
tree.ColumnWidth[1] = 120
tree.ColumnWidth[2] = 500

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
# CheckBox 事件
# ═══════════════════════════════════════════

def _on_chk_track(ev):
    checked = itm[CHK_TRACK].Checked
    _action_log(f"{'☑' if checked else '☐'} 轨道结构 {'勾选' if checked else '取消'}")


def _on_chk_subtitle(ev):
    checked = itm[CHK_SUBTITLE].Checked
    _action_log(f"{'☑' if checked else '☐'} 字幕夹帧 {'勾选' if checked else '取消'}")


# ═══════════════════════════════════════════
# 开始检查
# ═══════════════════════════════════════════

def _start_check():
    global _checking
    if _checking:
        return
    _checking = True
    itm[BTN_START].Enabled = False

    do_track = itm[CHK_TRACK].Checked
    do_subtitle = itm[CHK_SUBTITLE].Checked
    if not do_track and not do_subtitle:
        _action_log("⚠ 未选择任何检查项")
        _checking = False
        itm[BTN_START].Enabled = True
        return

    _action_log(f"▶ 开始检查 (轨道={do_track}, 字幕={do_subtitle}, "
                f"轨道模板={_track_values}, 夹帧阈值={_clamp_value})")

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
        tree_header_new = tree.NewItem()
        tree_header_new.Text[0] = "状态"
        tree_header_new.Text[1] = "位置"
        tree_header_new.Text[2] = "详情"
        tree.SetHeaderItem(tree_header_new)
        tree.ColumnWidth[0] = 50
        tree.ColumnWidth[1] = 120
        tree.ColumnWidth[2] = 500

        has_failures = False

        # ① 轨道结构
        if do_track:
            _action_log("── 轨道结构检查 ──")
            results = check_track_structure(timeline, *_track_values)
            for r in results:
                row = tree.NewItem()
                row.Text[0] = "✅" if r["status"] == "pass" else "❌"
                row.Text[1] = ""
                row.Text[2] = r["message"]
                tree.AddTopLevelItem(row)
                _action_log(r["message"].replace("✅ ", "").replace("❌ ", ""), to_ui=False)
                if r["status"] == "fail":
                    has_failures = True

        # ② 字幕夹帧
        if do_subtitle:
            _action_log("── 字幕夹帧检查 ──")
            results = check_subtitle_clamping(timeline, _clamp_value, fps)
            for r in results:
                row = tree.NewItem()
                if r["status"] == "pass":
                    row.Text[0] = "✅"
                elif r["status"] == "fail":
                    row.Text[0] = "❌"
                    has_failures = True
                else:
                    row.Text[0] = "⚠"

                tc = r.get("timecode", r.get("timecode_prev", ""))
                row.Text[1] = tc
                row.Text[2] = r["message"]

                tree.AddTopLevelItem(row)
                _action_log(r["message"].replace("✅ ", "").replace("❌ ", "").replace("⚠ ", ""), to_ui=False)

            # 禁用字幕检查
            results_disabled = check_disabled_subtitles(timeline, fps)
            for r in results_disabled:
                row = tree.NewItem()
                if r["status"] == "pass":
                    row.Text[0] = "✅"
                elif r["status"] == "fail":
                    row.Text[0] = "❌"
                    has_failures = True
                else:
                    row.Text[0] = "⚠"

                tc = r.get("timecode", "")
                row.Text[1] = tc
                row.Text[2] = r["message"]

                tree.AddTopLevelItem(row)
                _action_log(r["message"].replace("✅ ", "").replace("❌ ", "").replace("⚠ ", ""), to_ui=False)

        # 总结
        if has_failures:
            _action_log("❌ 检查未通过 — 请修复上述问题")
            itm[ST_LB].Text += "  |  ❌ 未通过"
        else:
            _action_log("✅ 所有检查通过")
            itm[ST_LB].Text += "  |  ✅ 通过"

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
        # 尝试从事件中获取被点击的 Item
        item = ev.get("Item")
        if item is None:
            item = tree.CurrentItem
        if item is None:
            _action_log(f"⚠ 跳转: 取不到 Item (ev keys: {list(ev.keys()) if hasattr(ev, 'keys') else type(ev)})")
            return
        tc = item.Text[1]
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

dlg.On[CHK_TRACK].Clicked = _on_chk_track
dlg.On[CHK_SUBTITLE].Clicked = _on_chk_subtitle
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
