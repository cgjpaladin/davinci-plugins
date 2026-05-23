#!/usr/bin/env python3
"""渲染队列批量提交工具。

从当前媒体池文件夹自动发现时间线，选择渲染预设，批量添加到渲染队列。
适合紧接在「交付自检」检查通过后使用。
"""

import re
import os
import sys
import time
from datetime import datetime

# ── 配置 ──
_COMMON_DELIVERY_RE = re.compile(r"^\d{2}_")
def _delivery_default(name):
    """常用交付合集：01-99 全勾，00_ 不勾，非编号不勾。"""
    return bool(_COMMON_DELIVERY_RE.match(name)) and not name.startswith("00_")

_TIMELINE_NAME_RE = re.compile(r"^\d{2,3}$")
_PLACEHOLDER_NAME = "项目名称"
_EXPORT_SUFFIX = "_交付版本合集"
_EXPORT_SUBDIR = "11_导出"

# ── 系统默认预设（DaVinci 自带，过滤掉）──
_SYSTEM_PRESET_PREFIXES = (
    "H.264", "H.265", "HyperDeck", "ProRes", "YouTube", "Vimeo",
    "TikTok", "Presentations", "Dropbox", "Replay", "IMF",
    "FCP", "Premiere", "Audio Only", "AVID", "Pro Tools",
    "Tencent",
)

def _is_system_preset(name):
    for prefix in _SYSTEM_PRESET_PREFIXES:
        if name.startswith(prefix):
            return True
    return False

try:
    from config import version_string, PRODUCT_NAME
except ImportError:
    version_string = lambda: "dev"
    PRODUCT_NAME = "渲染队列工具"

_LOG_DIR = os.path.expanduser("~/达芬奇插件工坊/logs")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = "/tmp"

def _log(msg):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        with open(os.path.join(_LOG_DIR, "render_batch.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)

# ── 按钮样式（同去字幕工具）──
_BTN_STYLE = (
    "QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
)
_BTN_PRIMARY = (
    "QPushButton{max-height:28px;background-color:rgb(50,120,220);color:rgb(255,255,255);"
    "border:1px solid rgb(70,140,240);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(65,135,235)}"
    "QPushButton:pressed{background-color:rgb(40,100,200)}"
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from fusionscript_loader import bmd

# ── UIManager 包装（统一使用 dict 参数风格）──

def L(id_, text, **extra):
    """Label。"""
    return ui.Label({"ID": id_, "Text": text, **extra})

def B(id_, text, **extra):
    """Button — 默认灰色风格。"""
    return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN_STYLE, "Weight": 0, **extra})

def BP(id_, text, **extra):
    """Button — 蓝色主按钮。"""
    return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN_PRIMARY, "Weight": 0, **extra})

def CB(id_, text, checked=True, enabled=True):
    """CheckBox。"""
    return ui.CheckBox({"ID": id_, "Text": text, "Checked": checked, "Enabled": enabled})

def LE(id_, text):
    """LineEdit。"""
    return ui.LineEdit({"ID": id_, "Text": text})

def SEP(text):
    """分隔线。"""
    return ui.Label({"ID": f"SEP_{text}", "Text": f"── {text} ──", "Weight": 0})

def HG(*widgets):
    """水平排列。"""
    return ui.HGroup({"Weight": 0}, list(widgets))

def VG(*widgets):
    """垂直排列。"""
    return ui.VGroup({"Weight": 0}, list(widgets))


def _derive_project_name(project_dir):
    if not project_dir:
        return ""
    folder = os.path.basename(project_dir.rstrip("/"))
    m = re.match(r"^\d{8}_(.*)", folder)
    return m.group(1) if m else folder


def _get_project_root_from_clip(project):
    try:
        count = project.GetTimelineCount()
        for i in range(1, count + 1):
            t = project.GetTimelineByIndex(i)
            items = t.GetItemListInTrack("video", 1) or []
            for it in items:
                mp = it.GetMediaPoolItem()
                if mp:
                    path = mp.GetClipProperty().get("File Path", "")
                    if path:
                        return path
    except Exception:
        pass
    return ""


def _get_export_info(project):
    clip_path = _get_project_root_from_clip(project)
    if clip_path:
        p = os.path.abspath(clip_path)
        while p and p != "/":
            if re.match(r"^\d{8}_", os.path.basename(p)):
                return p, _derive_project_name(p)
            p = os.path.dirname(p)
    return "", _PLACEHOLDER_NAME


def _get_folder_timelines(project):
    try:
        folder = project.GetMediaPool().GetCurrentFolder()
        if not folder:
            return []
        clips = folder.GetClipList()
    except Exception:
        return []
    seen = set()
    names = []
    for clip in clips:
        try:
            props = clip.GetClipProperty()
        except Exception:
            continue
        if props.get("Type", "") not in ("Timeline", "时间线"):
            continue
        name = clip.GetName()
        if name not in seen:
            seen.add(name)
            names.append(name)
    names.sort(key=lambda n: int(n) if n.isdigit() else float("inf"))
    return names


def show():
    global ui
    resolve = bmd.scriptapp("Resolve")
    if not resolve:
        print("达芬奇未运行")
        return
    fu = bmd.scriptapp("Fusion")
    if not fu:
        print("Fusion 不可用")
        return
    ui = fu.UIManager
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        print("未打开项目")
        return

    timeline_names = _get_folder_timelines(project)
    compliant_tls = [n for n in timeline_names if _TIMELINE_NAME_RE.match(n)]
    skipped_tls = [n for n in timeline_names if n not in set(compliant_tls)]

    preset_names = [n for n in project.GetRenderPresetList() if not _is_system_preset(n)]
    if not preset_names:
        print("项目没有渲染预设")
        return

    numbered = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n)]
    custom = [n for n in preset_names if not _COMMON_DELIVERY_RE.match(n)]
    numbered.sort(key=lambda n: int(n[:2]))
    preset_names = numbered + custom

    export_root, project_name = _get_export_info(project)
    export_full = os.path.join(export_root, _EXPORT_SUBDIR, f"{project_name}{_EXPORT_SUFFIX}") if export_root else ""
    dir_exists = os.path.isdir(export_full) if export_full else False

    # ── disp ──
    disp = bmd.UIDispatcher(ui)

    # ── 构建窗口内联组件 ──
    tl_widgets = []
    tl_ids, tl_map = [], {}
    if not compliant_tls and not skipped_tls:
        tl_widgets.append(ui.Label({"ID": "TLNone", "Text": "当前文件夹无时间线"}))
    else:
        for i, name in enumerate(compliant_tls):
            cid = f"TLCB_{i}"
            tl_ids.append(cid)
            tl_map[cid] = name
            tl_widgets.append(CB(cid, name, True, True))
        for i, name in enumerate(skipped_tls):
            cid = f"TLSKP_{i}"
            tl_ids.append(cid)
            tl_map[cid] = name
            tl_widgets.append(CB(cid, f"{name} (不合规)", False, False))

    pr_widgets = []
    pr_ids, pr_map = [], {}
    for i, name in enumerate(preset_names):
        cid = f"PRCB_{i:02d}"
        pr_ids.append(cid)
        pr_map[cid] = name
        pr_widgets.append(CB(cid, name, _delivery_default(name), True))

    # ── 主窗口 ──
    win = disp.AddWindow({
        "WindowTitle": f"{PRODUCT_NAME} v{version_string()}",
        "ID": "RenderBatchWin",
        "Geometry": [100, 100, 580, 600],
    }, [
        ui.VGroup({"ID": "RootV", "Spacing": 6}, [
            # ── 输出目录（去字幕风格）──
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                B("BtnConfirm", "✓ 确认此路径"),
                B("BtnPick", "选择项目路径"),
                ui.Label({"ID": "DirProjName", "Text":
                    f"项目: {project_name}" if export_root else "未指定项目路径",
                    "StyleSheet": "color:rgb(180,180,180);font-size:11px;", "Weight": 1}),
                ui.Label({"ID": "DirStatus", "Text": "已存在" if dir_exists else "需创建",
                    "StyleSheet": "color:rgb(50,180,80);font-size:11px;" if dir_exists else "color:rgb(235,110,0);font-size:11px;",
                    "Weight": 0}),
            ]),
            # ── 分割线 ──
            ui.Label({"ID": "Sep1", "Text": "━" * 80, "StyleSheet": "font-size:6px;color:#666;"}),
            # ── 时间线 + 预设 ──
            L("TLSection", "时间线 & 渲染预设", StyleSheet="font-size:14px;font-weight:bold;"),
            ui.HGroup({"ID": "MainPanels", "Weight": 10, "Spacing": 8}, [
                ui.VGroup({"Weight": 1, "Spacing": 2}, [
                    ui.HGroup({"Weight": 0}, [
                        L("TLTitle", "时间线", Weight=1),
                        L("TLCount", f"{len(compliant_tls)} 合规 / {len(skipped_tls)} 跳过"),
                    ]),
                    *tl_widgets,
                    HG(B("TLSelectAll", "全选合规")),
                ]),
                ui.VGroup({"Weight": 0, "Spacing": 0}, [
                    ui.Label({"Text": "┃", "StyleSheet": "font-size:18px;color:#666;", "Weight": 0, "MinimumSize": [0, 22]})
                    for _ in range(20)
                ]),
                ui.VGroup({"Weight": 1, "Spacing": 2}, [
                    ui.HGroup({"Weight": 0}, [
                        L("PRTitle", "渲染预设", Weight=1),
                        L("PRCount", f"{sum(1 for n in preset_names if _delivery_default(n))}/{len(preset_names)} 已选"),
                    ]),
                    HG(B("PRCommon", "常用交付合集")),
                    *pr_widgets,
                ]),
            ]),
            # ── 分割线 ──
            ui.Label({"ID": "Sep2", "Text": "━" * 80, "StyleSheet": "font-size:6px;color:#666;"}),
            # ── ③ 操作 ──
            ui.HGroup({"Weight": 0}, [
                L("Stats", "", Weight=1),
                BP("Submit", "加入渲染队列"),
            ]),
        ]),
    ])
    win.RecalcLayout()

    items = win.GetItems()

    # ── 可变状态（用户可手动选择其他路径）──
    _export_root = export_root
    _project_name = project_name

    def _read_checked(id_list):
        result = []
        for cid in id_list:
            try:
                if items[cid].Checked:
                    result.append(cid)
            except Exception:
                pass
        return result

    def _update_stats():
        tl_c = len(_read_checked(tl_ids))
        pr_c = len(_read_checked(pr_ids))
        items["Stats"].Text = f"{tl_c} x {pr_c} = {tl_c * pr_c} 个渲染任务"

    def _on_tl_select_all(ev):
        for cid in tl_ids:
            if cid.startswith("TLSKP_"):
                continue
            try:
                items[cid].Checked = True
            except Exception:
                pass
        _update_stats()

    def _on_pr_common(ev):
        for cid in pr_ids:
            name = pr_map.get(cid, "")
            try:
                items[cid].Checked = _delivery_default(name)
            except Exception:
                pass
        _update_stats()

    def _on_confirm(ev):
        nonlocal _export_root, _project_name
        if not _export_root or _project_name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请先选择项目或填写项目名称")
            return
        export_dir = os.path.join(_export_root, _EXPORT_SUBDIR, f"{_project_name}{_EXPORT_SUFFIX}")
        items["DirProjName"].Text = f"项目: {_project_name}"
        if not os.path.isdir(export_dir):
            try:
                os.makedirs(export_dir, exist_ok=True)
                items["DirStatus"].Text = "已创建"
                items["DirStatus"]["StyleSheet"] = "color:rgb(50,180,80);font-size:11px;"
            except Exception as e:
                items["DirStatus"].Text = "创建失败"
                disp.ShowMessage("错误", f"创建目录失败: {e}")
                return
        else:
            items["DirStatus"].Text = "已存在"
            items["DirStatus"]["StyleSheet"] = "color:rgb(50,180,80);font-size:11px;"
        _log(f"确认路径: {export_dir}")

    def _on_pick(ev):
        nonlocal _export_root, _project_name
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(title="选择项目根目录（包含 11_导出 的文件夹）")
        root.destroy()
        if not path:
            return
        _export_root = path
        _project_name = _derive_project_name(path) or os.path.basename(path)
        items["DirProjName"].Text = f"项目: {_project_name}"
        export_dir = os.path.join(_export_root, _EXPORT_SUBDIR, f"{_project_name}{_EXPORT_SUFFIX}")
        items["DirStatus"].Text = "已存在" if os.path.isdir(export_dir) else "需创建"
        items["DirStatus"]["StyleSheet"] = "color:rgb(50,180,80);font-size:11px;" if os.path.isdir(export_dir) else "color:rgb(235,110,0);font-size:11px;"
        _log(f"手动选择: {path} → {_project_name}")

    def _on_submit(ev):
        _log(f"=== 开始提交渲染队列 (v{version_string()}) ===")
        _log(f"项目: {project.GetName()}, 数据库: {pm.GetCurrentDatabase().get('DbName','?')}")
        tl_checked = [tl_map[c] for c in _read_checked(tl_ids) if not c.startswith("TLSKP_")]
        pr_checked = [pr_map[c] for c in _read_checked(pr_ids)]
        _log(f"选中时间线: {len(tl_checked)} 条, 预设: {len(pr_checked)} 个")

        if not tl_checked:
            disp.ShowMessage("提示", "没有选中合规时间线")
            return
        if not pr_checked:
            disp.ShowMessage("提示", "没有选中渲染预设")
            return

        proj_name = _project_name
        if not proj_name or proj_name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请填写项目名称（占位名「项目名称」不可用）")
            return

        export_dir = os.path.join(_export_root, _EXPORT_SUBDIR, f"{proj_name}{_EXPORT_SUFFIX}")
        if not os.path.isdir(export_dir):
            try:
                os.makedirs(export_dir, exist_ok=True)
            except Exception as e:
                disp.ShowMessage("错误", f"创建目录失败: {e}")
                return

        tl_checked_set = set(tl_checked)
        tl_objs = {}
        for i in range(1, project.GetTimelineCount() + 1):
            try:
                t = project.GetTimelineByIndex(i)
                if t.GetName() in tl_checked_set:
                    tl_objs[t.GetName()] = t
            except Exception:
                continue

        failed = []
        success = 0
        for tl_name in sorted(tl_checked):
            t = tl_objs.get(tl_name)
            if not t:
                failed.append(tl_name)
                continue
            project.SetCurrentTimeline(t)
            for pr_name in pr_checked:
                try:
                    if not project.LoadRenderPreset(pr_name):
                        failed.append(f"{tl_name} → {pr_name}")
                        continue
                    project.SetRenderSettings({"TargetDir": export_dir})
                    jid = project.AddRenderJob()
                    if jid:
                        success += 1
                    else:
                        failed.append(f"{tl_name} → {pr_name}")
                except Exception as e:
                    failed.append(f"{tl_name} → {pr_name} ({e})")
                time.sleep(0.03)

        msg = f"成功添加 {success} 个渲染任务"
        if failed:
            msg += f"\n跳过 {len(failed)} 个: " + " ".join(failed[:10])
        _log(f"结果: 成功 {success}, 失败 {len(failed)}, 输出目录: {export_dir}")
        disp.ShowMessage("完成", msg)

    win.On["TLSelectAll"].Clicked = _on_tl_select_all
    win.On["PRCommon"].Clicked = _on_pr_common
    win.On["Submit"].Clicked = _on_submit
    win.On["BtnConfirm"].Clicked = _on_confirm
    win.On["BtnPick"].Clicked = _on_pick
    win.On["RenderBatchWin"].Close = lambda ev: disp.ExitLoop()

    _update_stats()
    win.Show()
    disp.RunLoop()
    win.Hide()


ui = None  # set by show()
disp = None

if __name__ == "__main__":
    show()
