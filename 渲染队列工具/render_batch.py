#!/usr/bin/env python3
"""渲染队列批量提交工具."""
import re, os, sys
from datetime import datetime

_COMMON_DELIVERY_RE = re.compile(r"^\d{2}_")
def _delivery_default(name):
    return bool(_COMMON_DELIVERY_RE.match(name)) and not name.startswith("00_")
_TIMELINE_NAME_RE = re.compile(r"^\d{2,3}$")
_PLACEHOLDER_NAME = "项目名称"
_EXPORT_SUFFIX = "_交付版本合集"
_EXPORT_SUBDIR = "11_导出"
_SYSTEM = ("H.264","H.265","HyperDeck","ProRes","YouTube","Vimeo","TikTok",
    "Presentations","Dropbox","Replay","IMF","FCP","Premiere","Audio Only",
    "AVID","Pro Tools","Tencent")
def _is_system(n):
    for s in _SYSTEM:
        if n.startswith(s): return True
    return False

try:
    from config import version_string, PRODUCT_NAME
except ImportError:
    version_string = lambda: "dev"; PRODUCT_NAME = "渲染队列工具"

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

_BTN = ("QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}")
_BTN1 = ("QPushButton{max-height:28px;background-color:rgb(50,120,220);color:rgb(255,255,255);"
    "border:1px solid rgb(70,140,240);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(65,135,235)}"
    "QPushButton:pressed{background-color:rgb(40,100,200)}")

def L(id_, text, **kw): return ui.Label({"ID": id_, "Text": text, **kw})
def B(id_, text, **kw): return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN, "Weight": 0, **kw})
def BP(id_, text, **kw): return ui.Button({"ID": id_, "Text": text, "StyleSheet": _BTN1, "Weight": 0, **kw})
def CB(id_, text, checked=True, enabled=True):
    return ui.CheckBox({"ID": id_, "Text": text, "Checked": checked, "Enabled": enabled})
def SEP():
    return ui.Label({"Text": "━" * 80, "StyleSheet": "font-size:6px;color:#666;", "Weight": 0})
def VLINES(n=15):
    return [ui.Label({"Text": "┃", "StyleSheet": "font-size:18px;color:#666;",
        "Weight": 0, "MinimumSize": [0, 22]}) for _ in range(n)]

def _derive_name(d):
    if not d: return ""
    m = re.match(r"^\d{8}_(.*)", os.path.basename(d.rstrip("/")))
    return m.group(1) if m else ""

def _clip_root(project):
    try:
        for i in range(1, project.GetTimelineCount() + 1):
            for it in (project.GetTimelineByIndex(i).GetItemListInTrack("video", 1) or []):
                mp = it.GetMediaPoolItem()
                if mp:
                    p = mp.GetClipProperty().get("File Path", "")
                    if p: return p
    except: pass
    return ""

def _export_info(project):
    cp = _clip_root(project)
    if cp:
        p = os.path.abspath(cp)
        while p and p != "/":
            if re.match(r"^\d{8}_", os.path.basename(p)):
                return p, _derive_name(p)
            p = os.path.dirname(p)
    return "", _PLACEHOLDER_NAME

def _tl_from_folder(project):
    try:
        f = project.GetMediaPool().GetCurrentFolder()
        if not f: return []
        clips = f.GetClipList()
    except: return []
    seen, names = set(), []
    for c in clips:
        try: props = c.GetClipProperty()
        except: continue
        if props.get("Type","") not in ("Timeline","时间线"): continue
        n = c.GetName()
        if n not in seen: seen.add(n); names.append(n)
    names.sort(key=lambda n: int(n) if n.isdigit() else float("inf"))
    return names

# ══════════════════════════════════════════

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

    timelines = _tl_from_folder(project)
    compliant = [n for n in timelines if _TIMELINE_NAME_RE.match(n)]
    skipped = [n for n in timelines if n not in set(compliant)]

    presets = [n for n in project.GetRenderPresetList() if not _is_system(n)]
    numbered = sorted([n for n in presets if _COMMON_DELIVERY_RE.match(n)], key=lambda x: int(x[:2]))
    custom = [n for n in presets if not _COMMON_DELIVERY_RE.match(n)]
    presets = numbered + custom

    root, name = _export_info(project)
    label = root
    if label.startswith("/Volumes/MYJC/"): label = label[14:]
    if len(label) > 65: label = label[:62] + "..."

    disp = bmd.UIDispatcher(ui)

    # ── 时间线 TextEdit（自带滚动）──
    tl_text = ""
    if compliant:
        tl_text = "\n".join(compliant)
    if skipped:
        if tl_text: tl_text += "\n"
        tl_text += "\n".join(f"（跳过）{n}" for n in skipped)
    if not tl_text:
        tl_text = "当前文件夹无时间线"

    # ── 预设 CheckBox ──
    pr_ids, pr_map = [], {}
    pr_widgets = []
    for i, n in enumerate(presets):
        cid = f"PRCB_{i:02d}"; pr_ids.append(cid); pr_map[cid] = n
        pr_widgets.append(CB(cid, n, _delivery_default(n), True))

    win = disp.AddWindow({
        "WindowTitle": f"{PRODUCT_NAME} v{version_string()}",
        "ID": "RenderBatchWin",
        "Geometry": [100, 100, 580, 680],
    }, [
        ui.VGroup({"ID": "RootV", "Spacing": 4}, [
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                B("BtnOk", "✓ 确认此路径"),
                B("BtnPick", "选择项目路径"),
                ui.Label({"ID": "DirLabel", "Text": label or "未指定项目路径",
                    "StyleSheet": "color:rgb(180,180,180);font-size:11px;", "Weight": 1}),
                ui.Label({"ID": "DirStatus", "Text": "需确认", "FixedSize": [120, 16],
                    "StyleSheet": "color:rgb(200,200,200);font-size:11px;",
                    "Alignment": {"AlignRight": True}}),
            ]),
            SEP(),
            L("Section", "时间线 & 渲染预设", StyleSheet="font-size:14px;font-weight:bold;"),
            ui.HGroup({"ID": "Main", "Spacing": 8, "Weight": 10}, [
                ui.VGroup({"Weight": 1, "Spacing": 2}, [
                    ui.HGroup({"Weight": 0}, [
                        L("TLTitle", "时间线", Weight=1),
                        L("TLCount", f"{len(compliant)} 合规 / {len(skipped)} 跳过"),
                    ]),
                    ui.TextEdit({"ID": "TLText", "Text": tl_text,
                        "Weight": 10, "FixedSize": [220, 300]}),
                    ui.HGroup({"Weight": 0}, [B("TLAll", "全不选")]),
                ]),
                ui.VGroup({"Weight": 0, "Spacing": 0}, VLINES()),
                ui.VGroup({"Weight": 1, "Spacing": 2}, [
                    ui.HGroup({"Weight": 0}, [
                        L("PRTitle", "渲染预设", Weight=1),
                        L("PRCount", f"{sum(1 for n in presets if _delivery_default(n))}/{len(presets)} 已选"),
                    ]),
                    ui.VGroup({"Weight": 0, "Spacing": 1}, pr_widgets),
                    ui.HGroup({"Weight": 0}, [B("PRAll", "常用交付合集")]),
                ]),
            ]),
            SEP(),
            ui.HGroup({"Weight": 0}, [L("Stats", "", Weight=1), BP("Submit", "加入渲染队列")]),
        ]),
    ])
    win.RecalcLayout()
    items = win.GetItems()
    _root, _name = root, name
    _tl_all = True  # 全选/全不选

    def _read_checked(ids):
        r = []
        for cid in ids:
            try:
                if items[cid].Checked: r.append(cid)
            except: pass
        return r

    def _update_stats():
        tl_c = len(compliant) if _tl_all else 0
        pr_c = len(_read_checked(pr_ids))
        items["Stats"].Text = f"{tl_c} x {pr_c} = {tl_c * pr_c} 个渲染任务"

    def _on_tl_all(ev):
        nonlocal _tl_all
        _tl_all = not _tl_all
        items["TLAll"].Text = "全不选" if _tl_all else "全选合规"
        _update_stats()

    def _on_pr_all(ev):
        for cid in pr_ids:
            try: items[cid].Checked = _delivery_default(pr_map.get(cid, ""))
            except: pass
        _update_stats()

    def _on_ok(ev):
        nonlocal _root, _name
        if not _root or _name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请先选择项目"); return
        ed = os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}")
        lb = _root
        if lb.startswith("/Volumes/MYJC/"): lb = lb[14:]
        if len(lb) > 65: lb = lb[:62] + "..."
        items["DirLabel"].Text = lb
        items["DirLabel"]["StyleSheet"] = "color:rgb(102,221,39);font-size:11px;"
        if not os.path.isdir(ed):
            try:
                os.makedirs(ed, exist_ok=True)
                items["DirStatus"].Text = "已创建"
            except Exception as e:
                items["DirStatus"].Text = "创建失败"; disp.ShowMessage("错误", f"{e}"); return
        else:
            items["DirStatus"].Text = "已确认"
        items["DirStatus"]["StyleSheet"] = "color:rgb(102,221,39);font-size:11px;"
        _log(f"确认: {ed}")

    def _on_pick(ev):
        nonlocal _root, _name
        import tkinter as tk; from tkinter import filedialog
        r = tk.Tk(); r.withdraw()
        path = filedialog.askdirectory(title="选择项目根目录")
        r.destroy()
        if not path: return
        _root = path
        _name = _derive_name(path) or os.path.basename(path)
        lb = _root
        if lb.startswith("/Volumes/MYJC/"): lb = lb[14:]
        if len(lb) > 65: lb = lb[:62] + "..."
        items["DirLabel"].Text = lb
        items["DirLabel"]["StyleSheet"] = "color:rgb(180,180,180);font-size:11px;"
        ex = os.path.isdir(os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}"))
        items["DirStatus"].Text = "已存在" if ex else "需创建"
        items["DirStatus"]["StyleSheet"] = "color:rgb(200,200,200);font-size:11px;"
        _log(f"手动: {path}")

    def _on_submit(ev):
        _log(f"=== 提交渲染 (v{version_string()}) ===")
        tl_ok = compliant if _tl_all else []
        pr_ok = [pr_map[c] for c in _read_checked(pr_ids)]
        if not tl_ok: disp.ShowMessage("提示", "没有选中合规时间线"); return
        if not pr_ok: disp.ShowMessage("提示", "没有选中渲染预设"); return
        if not _name or _name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请先确认项目名称"); return
        ed = os.path.join(_root, _EXPORT_SUBDIR, f"{_name}{_EXPORT_SUFFIX}")
        if not os.path.isdir(ed):
            try: os.makedirs(ed, exist_ok=True)
            except Exception as e: disp.ShowMessage("错误", f"{e}"); return

        ts = set(tl_ok)
        to = {}
        for i in range(1, project.GetTimelineCount() + 1):
            try:
                t = project.GetTimelineByIndex(i)
                if t.GetName() in ts: to[t.GetName()] = t
            except: continue

        # 路径只设一次
        project.SetRenderSettings({"TargetDir": ed})

        failed, ok = [], 0
        for pn in pr_ok:
            if not project.LoadRenderPreset(pn):
                failed.append(f"预设加载失败: {pn}"); continue
            project.SetRenderSettings({"TargetDir": ed})
            _log(f"预设: {pn}")
            for tn in sorted(tl_ok):
                t = to.get(tn)
                if not t: failed.append(tn); continue
                try:
                    project.SetCurrentTimeline(t)
                    jid = project.AddRenderJob()
                    if jid: ok += 1
                    else: failed.append(f"{tn}->{pn}")
                except Exception as e:
                    failed.append(f"{tn}->{pn}({e})")

        msg = f"成功添加 {ok} 个渲染任务"
        if failed: msg += f"\n跳过 {len(failed)} 个: " + " ".join(failed[:10])
        _log(f"结果: 成功 {ok}, 失败 {len(failed)}, 目录: {ed}")
        disp.ShowMessage("完成", msg)

    win.On["TLAll"].Clicked = _on_tl_all
    win.On["PRAll"].Clicked = _on_pr_all
    win.On["BtnOk"].Clicked = _on_ok
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
