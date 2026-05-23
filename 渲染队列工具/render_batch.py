#!/usr/bin/env python3
"""渲染队列批量提交工具。"""
import re, os, sys, time
from datetime import datetime

_COMMON_DELIVERY_RE = re.compile(r"^\d{2}_")
def _delivery_default(name):
    return bool(_COMMON_DELIVERY_RE.match(name)) and not name.startswith("00_")

_TIMELINE_NAME_RE = re.compile(r"^\d{2,3}$")
_PLACEHOLDER_NAME = "项目名称"
_EXPORT_SUFFIX = "_交付版本合集"
_EXPORT_SUBDIR = "11_导出"

_SYSTEM_PRESET_PREFIXES = (
    "H.264","H.265","HyperDeck","ProRes","YouTube","Vimeo",
    "TikTok","Presentations","Dropbox","Replay","IMF",
    "FCP","Premiere","Audio Only","AVID","Pro Tools","Tencent",
)
def _is_system_preset(name):
    for p in _SYSTEM_PRESET_PREFIXES:
        if name.startswith(p): return True
    return False

try:
    from config import version_string, PRODUCT_NAME
except ImportError:
    version_string = lambda: "dev"
    PRODUCT_NAME = "渲染队列工具"

_LOG_DIR = os.path.expanduser("~/达芬奇插件工坊/logs")
try: os.makedirs(_LOG_DIR, exist_ok=True)
except: _LOG_DIR = "/tmp"

def _log(msg):
    s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{s}] {msg}"
    try:
        with open(os.path.join(_LOG_DIR, "render_batch.log"), "a") as f:
            f.write(line + "\n")
    except: pass
    print(line)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from fusionscript_loader import bmd

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

def L(id_, text, **extra):
    return ui.Label({"ID": id_, "Text": text, **extra})
def B(id_, text, **extra):
    return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN_STYLE, "Weight": 0, **extra})
def BP(id_, text, **extra):
    return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN_PRIMARY, "Weight": 0, **extra})
def CB(id_, text, checked=True, enabled=True):
    return ui.CheckBox({"ID": id_, "Text": text, "Checked": checked, "Enabled": enabled})
def LE(id_, text):
    return ui.LineEdit({"ID": id_, "Text": text})
def HG(*widgets):
    return ui.HGroup({"Spacing": 6, "Weight": 0}, list(widgets))
def DIVIDER(count=80):
    return ui.Label({"ID": "div", "Text": "━" * count, "StyleSheet": "font-size:6px;color:#666;", "Weight": 0})
def VLINE_LABELS(count=12):
    return [ui.Label({"Text": "┃", "StyleSheet": "font-size:18px;color:#666;", "Weight": 0,
                      "MinimumSize": [0, 22]}) for _ in range(count)]

def _derive_project_name(d):
    if not d: return ""
    m = re.match(r"^\d{8}_(.*)", os.path.basename(d.rstrip("/")))
    return m.group(1) if m else ""

def _clip_root_path(project):
    try:
        for i in range(1, project.GetTimelineCount() + 1):
            t = project.GetTimelineByIndex(i)
            for it in (t.GetItemListInTrack("video", 1) or []):
                mp = it.GetMediaPoolItem()
                if mp:
                    p = mp.GetClipProperty().get("File Path", "")
                    if p: return p
    except: pass
    return ""

def _get_export_info(project):
    cp = _clip_root_path(project)
    if cp:
        p = os.path.abspath(cp)
        while p and p != "/":
            if re.match(r"^\d{8}_", os.path.basename(p)):
                return p, _derive_project_name(p)
            p = os.path.dirname(p)
    return "", _PLACEHOLDER_NAME

def _folder_timelines(project):
    try:
        folder = project.GetMediaPool().GetCurrentFolder()
        if not folder: return []
        clips = folder.GetClipList()
    except: return []
    seen, names = set(), []
    for c in clips:
        try: props = c.GetClipProperty()
        except: continue
        if props.get("Type","") not in ("Timeline","时间线"): continue
        n = c.GetName()
        if n not in seen:
            seen.add(n); names.append(n)
    names.sort(key=lambda n: int(n) if n.isdigit() else float("inf"))
    return names

def show():
    global ui
    resolve = bmd.scriptapp("Resolve")
    if not resolve: print("达芬奇未运行"); return
    fu = bmd.scriptapp("Fusion")
    if not fu: print("Fusion 不可用"); return
    ui = fu.UIManager
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project: print("未打开项目"); return

    timelines = _folder_timelines(project)
    compliant = [n for n in timelines if _TIMELINE_NAME_RE.match(n)]
    skipped = [n for n in timelines if n not in set(compliant)]

    presets = [n for n in project.GetRenderPresetList() if not _is_system_preset(n)]
    numbered = sorted([n for n in presets if _COMMON_DELIVERY_RE.match(n)], key=lambda x: int(x[:2]))
    custom = [n for n in presets if not _COMMON_DELIVERY_RE.match(n)]
    presets = numbered + custom

    export_root, project_name = _get_export_info(project)
    proj_label = export_root
    if proj_label.startswith("/Volumes/MYJC/"): proj_label = proj_label[14:]
    if len(proj_label) > 65: proj_label = proj_label[:62] + "..."

    disp = bmd.UIDispatcher(ui)

    # 时间线 widgets
    tl_ids, tl_map = [], {}
    tl_widgets = []
    if not compliant and not skipped:
        tl_widgets.append(L("TLNone", "当前文件夹无时间线"))
    else:
        for i, n in enumerate(compliant):
            tl_ids.append(cid := f"TLCB_{i}"); tl_map[cid] = n
            tl_widgets.append(CB(cid, n, True, True))
        for i, n in enumerate(skipped):
            tl_ids.append(cid := f"TLSKP_{i}"); tl_map[cid] = n
            tl_widgets.append(CB(cid, f"{n} (不合规)", False, False))

    # 预设 widgets
    pr_ids, pr_map = [], {}
    pr_widgets = []
    for i, n in enumerate(presets):
        cid = f"PRCB_{i:02d}"
        pr_ids.append(cid); pr_map[cid] = n
        pr_widgets.append(CB(cid, n, _delivery_default(n), True))

    win_layout = [
        ui.VGroup({"ID": "RootV", "Spacing": 6}, [
            # ── 输出目录 ──
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                B("BtnConfirm", "✓ 确认此路径"),
                B("BtnPick", "选择项目路径"),
                ui.Label({"ID": "DirProjName", "Text": proj_label or "未指定项目路径",
                    "StyleSheet": "color:rgb(180,180,180);font-size:11px;", "Weight": 1}),
                ui.Label({"ID": "DirStatus", "Text": "需确认", "FixedSize": [120, 16],
                    "StyleSheet": "color:rgb(200,200,200);font-size:11px;",
                    "Alignment": {"AlignRight": True}}),
            ]),
            DIVIDER(),
            # ── 时间线 | 渲染预设 ──
            L("TLSection", "时间线 & 渲染预设", StyleSheet="font-size:14px;font-weight:bold;"),
            ui.HGroup({"ID": "MainPanels", "Spacing": 8, "Weight": 10}, [
                ui.VGroup({"Weight": 1, "Spacing": 1}, [
                    ui.HGroup({"Weight": 0}, [
                        L("TLTitle", "时间线", Weight=1),
                        L("TLCount", f"{len(compliant)} 合规 / {len(skipped)} 跳过"),
                    ]),
                    *tl_widgets,
                    HG(B("TLSelectAll", "全选合规")),
                ]),
                ui.VGroup({"Weight": 0, "Spacing": 0}, VLINE_LABELS()),
                ui.VGroup({"Weight": 1, "Spacing": 1}, [
                    ui.HGroup({"Weight": 0}, [
                        L("PRTitle", "渲染预设", Weight=1),
                        L("PRCount", f"{sum(1 for n in presets if _delivery_default(n))}/{len(presets)} 已选"),
                    ]),
                    *pr_widgets,
                    HG(B("PRCommon", "常用交付合集")),
                ]),
            ]),
            DIVIDER(),
            # ── 操作 ──
            ui.HGroup({"Weight": 0}, [
                L("Stats", "", Weight=1),
                BP("Submit", "加入渲染队列"),
            ]),
        ]),
    ]

    win = disp.AddWindow({
        "WindowTitle": f"{PRODUCT_NAME} v{version_string()}",
        "ID": "RenderBatchWin",
        "Geometry": [100, 100, 580, 720],
    }, win_layout)
    win.RecalcLayout()
    items = win.GetItems()
    _root, _name = export_root, project_name

    def _read_checked(ids):
        r = []
        for cid in ids:
            try:
                if items[cid].Checked: r.append(cid)
            except: pass
        return r

    def _update_stats():
        tl = len(_read_checked(tl_ids))
        pr = len(_read_checked(pr_ids))
        items["Stats"].Text = f"{tl} x {pr} = {tl * pr} 个渲染任务"

    def _on_tl_select_all(ev):
        for cid in tl_ids:
            if cid.startswith("TLSKP_"): continue
            try: items[cid].Checked = True
            except: pass
        _update_stats()

    def _on_pr_common(ev):
        for cid in pr_ids:
            try: items[cid].Checked = _delivery_default(pr_map.get(cid, ""))
            except: pass
        _update_stats()

    def _on_confirm(ev):
        nonlocal _root, _name
        if not _root or _name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请先选择项目")
            return
        ed = os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}")
        label = _root
        if label.startswith("/Volumes/MYJC/"): label = label[14:]
        if len(label) > 65: label = label[:62] + "..."
        items["DirProjName"].Text = label
        items["DirProjName"]["StyleSheet"] = "color:rgb(102,221,39);font-size:11px;"
        if not os.path.isdir(ed):
            try:
                os.makedirs(ed, exist_ok=True)
                items["DirStatus"].Text = "已创建"
            except Exception as e:
                items["DirStatus"].Text = "创建失败"
                disp.ShowMessage("错误", f"创建目录失败: {e}"); return
        else:
            items["DirStatus"].Text = "已确认"
        items["DirStatus"]["StyleSheet"] = "color:rgb(102,221,39);font-size:11px;"
        _log(f"确认路径: {ed}")

    def _on_pick(ev):
        nonlocal _root, _name
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk(); r.withdraw()
        path = filedialog.askdirectory(title="选择项目根目录")
        r.destroy()
        if not path: return
        _root = path
        _name = _derive_project_name(path) or os.path.basename(path)
        label = _root
        if label.startswith("/Volumes/MYJC/"): label = label[14:]
        if len(label) > 65: label = label[:62] + "..."
        items["DirProjName"].Text = label
        ed = os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}")
        items["DirStatus"].Text = "已存在" if os.path.isdir(ed) else "需创建"
        items["DirStatus"]["StyleSheet"] = "color:rgb(200,200,200);font-size:11px;"
        items["DirProjName"]["StyleSheet"] = "color:rgb(180,180,180);font-size:11px;"
        _log(f"手动选择: {path} → {_name}")

    def _on_submit(ev):
        _log(f"=== 开始提交渲染队列 (v{version_string()}) ===")
        tl_checked = [tl_map[c] for c in _read_checked(tl_ids) if not c.startswith("TLSKP_")]
        pr_checked = [pr_map[c] for c in _read_checked(pr_ids)]
        if not tl_checked: disp.ShowMessage("提示", "没有选中合规时间线"); return
        if not pr_checked: disp.ShowMessage("提示", "没有选中渲染预设"); return
        if not _name or _name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请先确认项目名称"); return
        ed = os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}")
        if not os.path.isdir(ed):
            try: os.makedirs(ed, exist_ok=True)
            except Exception as e: disp.ShowMessage("错误", f"创建目录失败: {e}"); return

        tl_set = set(tl_checked)
        tl_objs = {}
        for i in range(1, project.GetTimelineCount() + 1):
            try:
                t = project.GetTimelineByIndex(i)
                if t.GetName() in tl_set: tl_objs[t.GetName()] = t
            except: continue

        failed, success = [], 0
        for tn in sorted(tl_checked):
            t = tl_objs.get(tn)
            if not t: failed.append(tn); continue
            project.SetCurrentTimeline(t)
            for pn in pr_checked:
                try:
                    if not project.LoadRenderPreset(pn): failed.append(f"{tn}->{pn}"); continue
                    project.SetRenderSettings({"TargetDir": ed})
                    jid = project.AddRenderJob()
                    if jid: success += 1
                    else: failed.append(f"{tn}->{pn}")
                except Exception as e: failed.append(f"{tn}->{pn}({e})")
                time.sleep(0.03)

        msg = f"成功添加 {success} 个渲染任务"
        if failed: msg += f"\n跳过 {len(failed)} 个: " + " ".join(failed[:10])
        _log(f"结果: 成功 {success}, 失败 {len(failed)}, 目录: {ed}")
        disp.ShowMessage("完成", msg)

    win.On["TLSelectAll"].Clicked = _on_tl_select_all
    win.On["PRCommon"].Clicked = _on_pr_common
    win.On["BtnConfirm"].Clicked = _on_confirm
    win.On["BtnPick"].Clicked = _on_pick
    win.On["Submit"].Clicked = _on_submit
    win.On["RenderBatchWin"].Close = lambda ev: disp.ExitLoop()

    _update_stats()
    win.Show()
    disp.RunLoop()
    win.Hide()

ui = None
if __name__ == "__main__":
    show()
