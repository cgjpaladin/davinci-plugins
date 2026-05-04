"""
AI 去字幕 — 交互界面 v1.0
用达芬奇 UIManager + UIDispatcher，零外部依赖
"""

import sys, os, time, re, math, json, subprocess, traceback, urllib.request
from copy import deepcopy

# ── 达芬奇环境 ──
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

sys.path.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr

from config import *
from adapters import WatermarkTask, WatermarkResult
from adapters.ghostcut import GhostCutAdapter
from watermark_state import init as state_init, record_original, need_restore, mark_processed, acquire_lock, release_lock
import ops_logger

COLORS = ["Orange", "Yellow", "Green", "Blue", "Purple", "Pink", "Red"]
WIN_ID = "com.myjc.ai_subtitle"
_processing = False
_stop_flag = False
_current_mode = DEFAULT_MODE


def get_mode():
    return _current_mode


def on_mode_basic(ev):
    global _current_mode
    _current_mode = "basic"
    w = ui.FindWindow(WIN_ID)
    if w:
        w.GetItems()["btn_basic"].Flat = False
        w.GetItems()["btn_pro"].Flat = True


def on_mode_pro(ev):
    global _current_mode
    _current_mode = "pro_box"
    w = ui.FindWindow(WIN_ID)
    if w:
        w.GetItems()["btn_basic"].Flat = True
        w.GetItems()["btn_pro"].Flat = False


def get_duration(fp):
    for ff in ("ffprobe", "/opt/homebrew/bin/ffprobe"):
        try:
            r = subprocess.run([ff, "-v", "quiet", "-show_entries", "format=duration",
                                "-of", "csv=p=0", fp], capture_output=True, text=True, timeout=10)
            return float(r.stdout.strip())
        except: continue
    return 0


def _get_ui():
    resolve = dvr.scriptapp("Resolve")
    fu = resolve.Fusion()
    return fu.UIManager, dvr.UIDispatcher(fu.UIManager)


def _log(itm, msg):
    itm["log_output"].InsertPlainText(msg + "\n")


def _do_scan(itm):
    resolve = dvr.scriptapp("Resolve")
    t = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
    io = t.GetMarkInOut()
    io_in = io["video"]["in"]
    io_out = io["video"]["out"]
    
    clr = itm["filter_color"].CurrentText
    
    seen = {}
    for tr in range(1, t.GetTrackCount("video") + 1):
        for item in t.GetItemListInTrack("video", tr) or []:
            s, e = item.GetStart(), item.GetEnd()
            if s >= io_out or e <= io_in:
                continue
            n = item.GetName()
            if n in seen:
                existing = seen[n]
                if clr and existing.GetClipColor() == clr:
                    continue
            seen[n] = item
    
    results = []
    stats = {"total": 0, "ok": 0, "red": 0, "bad": 0}
    
    for n, item in seen.items():
        stats["total"] += 1
        if clr and item.GetClipColor() != clr:
            continue
        
        flags = item.GetFlagList() or []
        if isinstance(flags, dict):
            flags = list(flags.values())
        if "Red" in flags:
            stats["red"] += 1
            continue
        
        mp = item.GetMediaPoolItem()
        if not mp:
            stats["bad"] += 1
            continue
        p = mp.GetClipProperty("File Path")
        if not p or not os.path.exists(p):
            stats["bad"] += 1
            continue
        
        stats["ok"] += 1
        results.append((mp, n, p))
    
    mode = get_mode()
    unit = COST_PER_MODE.get(mode, 1)
    total_units = sum(math.ceil(get_duration(c[2]) / 30) for c in results)
    
    lines = [f"📊 {stats['ok']} 个 {clr or '全部'}色片段可处理"]
    if stats["red"]:
        lines.append(f"⏭ {stats['red']} 个红色旗标")
    lines.append(f"💰 预估 {total_units} × {unit} = {total_units * unit} 点")
    
    itm["scan_result"].PlainText = "\n".join(lines)
    itm["btn_start"].Enabled = stats["ok"] > 0
    return results


def _update_balance(itm):
    try:
        a = GhostCutAdapter(deepcopy(ADAPTER_CONFIGS["ghostcut"]))
        b = a.get_balance()
        now = time.time() * 1000
        pts = sum(x["pointBalance"] for x in b.get("pointAssets", [])
                  if x["pointBalance"] > 0 and x.get("expireTime", now + 1) > now)
    except:
        pts = 0
    itm["lbl_balance"].Text = f"余额: {pts:.1f} 点"
    return pts


def on_scan(ev):
    w = ev["sender"]
    itm = w.GetItems()
    try:
        _do_scan(itm)
    except Exception as e:
        itm["scan_result"].PlainText = f"❌ {e}"


def on_start(ev):
    w = ev["sender"]
    itm = w.GetItems()
    itm["btn_start"].Enabled = False
    itm["btn_stop"].Enabled = True
    itm["log_output"].PlainText = ""
    
    resolve = dvr.scriptapp("Resolve")
    proj = resolve.GetProjectManager().GetCurrentProject()
    
    clips = _do_scan(itm)
    if not clips:
        _log(itm, "没有可处理的片段")
        itm["btn_start"].Enabled = True
        itm["btn_stop"].Enabled = False
        return
    
    mode = get_mode()
    proj_root = get_project_root(clips[0][2])
    out_dir = get_output_dir(proj_root)
    mode_label = MODE_LABELS.get(mode, mode)
    _log(itm, f"模式: {mode_label} | 项目: {proj_root}")
    _log(itm, f"输出: {out_dir}")
    
    state_init(proj_root)
    ops_logger.init(get_log_dir(proj_root))
    ops_logger.session_start(proj.GetName(), "", mode, 0)
    _update_balance(itm)
    
    adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
    valid = []
    
    for mp_item, name, path in clips:
        record_original(name, path)
        rst = need_restore(name, mode)
        if rst == "__SKIP__":
            _log(itm, f"  ⏭ {name} 已是最佳状态")
            continue
        if rst:
            mp_item.ReplaceClip(rst)
            path = rst
        
        dur = get_duration(path)
        if dur > MAX_SOURCE_DURATION:
            continue
        
        kwargs = {"video_path": path, "language": "zh", "model": mode}
        if mode == "pro_box":
            kwargs["mask_regions"] = [{"type": "remove_only_ocr", "start": 0, "end": 99999,
                                        "region": DEFAULT_MASK_REGION}]
        valid.append((mp_item, name, path, kwargs, dur))
    
    total = len(valid)
    ok = 0
    stop_flag = False
    adapter = GhostCutAdapter(adapter_cfg)
    
    for idx, (mp_item, name, path, kwargs, dur) in enumerate(valid, 1):
        if itm["btn_stop"].Enabled == False:
            stop_flag = True
        if stop_flag:
            _log(itm, f"  ⏹ 停止，剩余 {total - idx + 1}")
            break
        
        if not acquire_lock(name):
            _log(itm, f"  [{idx}/{total}] {name} → ⏭ 他人处理中")
            continue
        
        _log(itm, f"  [{idx}/{total}] {name} → 处理中...")
        
        result = None
        elapsed = 0
        for attempt in range(3):
            try:
                t0 = time.time()
                ops_logger.task_submit(name, mode, dur, attempt)
                result = adapter.process(WatermarkTask(**kwargs), timeout=API_TIMEOUT)
                elapsed = time.time() - t0
                ops_logger.task_result(name, str(getattr(result, 'task_id', '')), elapsed, result.success)
                break
            except Exception as e:
                ops_logger.task_error(name, str(e)[:200], attempt)
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                else:
                    release_lock(name)
                    result = WatermarkResult(success=False, task_id="",
                                             error_message=f"重试失败: {str(e)[:80]}")
        
        if result and result.success:
            base = re.sub(r'_去字幕_.*$', '', os.path.splitext(name)[0])
            tag = MODE_FILE_TAGS.get(mode, mode)
            ep = "EP00"
            m = re.match(r'(EP\d+)', name)
            if m: ep = m.group(1)
            ep_dir = get_output_dir(proj_root, ep)
            v = 1
            while True:
                cn = f"{base}_去字幕_{tag}_v{v:02d}.mp4"
                dl = os.path.join(ep_dir, cn)
                if not os.path.exists(dl): break
                v += 1
            
            urllib.request.urlretrieve(result.output_path, dl)
            if mp_item.ReplaceClip(dl):
                mark_processed(name, dl, mode)
                ok += 1
                _log(itm, f"  ✅ [{idx}/{total}] {name} ({elapsed:.0f}秒)")
            else:
                _log(itm, f"  ⚠ [{idx}/{total}] {name} ReplaceClip 失败")
            release_lock(name)
        else:
            err = getattr(result, 'error_message', '未知') if result else '未知'
            _log(itm, f"  ❌ [{idx}/{total}] {name}: {err}")
    
    _log(itm, f"\n[完成] {ok}/{total}")
    ops_logger.session_end(ok, total - ok, total)
    _update_balance(itm)
    itm["btn_start"].Enabled = True
    itm["btn_stop"].Enabled = False


def on_stop(ev):
    w = ev["sender"]
    w.GetItems()["btn_stop"].Enabled = False


def build_ui(ui):
    return ui.VGroup({"Spacing": 6}, [
        ui.HGroup({"Weight": 0}, [
            ui.Label({"ID": "lbl_title", "Text": "AI 去字幕",
                       "Font": ui.Font({"Family": "Helvetica", "PointSize": 16, "Bold": True})}),
            ui.HGap(),
            ui.Label({"ID": "lbl_balance", "Text": "余额: ---",
                       "Font": ui.Font({"PointSize": 12})}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Text": "模式:"}),
            ui.Button({"ID": "btn_basic", "Text": "快速预览", "Flat": DEFAULT_MODE != "basic", "Weight": 0}),
            ui.Button({"ID": "btn_pro", "Text": "正式出片", "Flat": DEFAULT_MODE != "pro_box", "Weight": 0}),
            ui.HGap(),
            ui.Label({"Text": "筛选:"}),
            ui.ComboBox({"ID": "filter_color"}),
            ui.Button({"ID": "btn_scan", "Text": "扫描"}),
        ]),
        ui.TextEdit({"ID": "scan_result", "ReadOnly": True,
                      "MaximumSize": [9999, 70]}),
        ui.HGroup({"Weight": 0}, [
            ui.Button({"ID": "btn_start", "Text": "开始处理", "Enabled": False}),
            ui.Button({"ID": "btn_stop", "Text": "停止", "Enabled": False}),
        ]),
        ui.TextEdit({"ID": "log_output", "ReadOnly": True}),
    ])


def show():
    # 达芬奇脚本环境自动注入 resolve, fusion, bmd
    resolve = dvr.scriptapp("Resolve")
    fu = resolve.Fusion()
    ui = fu.UIManager
    disp = bmd.UIDispatcher(ui)
    
    win = ui.FindWindow(WIN_ID)
    if win:
        win.Show()
        win.Raise()
        return
    
    dlg = disp.AddWindow({
        "ID": WIN_ID,
        "WindowTitle": "AI 去字幕 v1.0",
        "Geometry": [200, 200, 520, 600],
    }, build_ui(ui))
    
    itm = dlg.GetItems()
    for c in COLORS:
        itm["filter_color"].AddItem(c)
    itm["filter_color"].AddItem("全部")
    itm["filter_color"].CurrentText = CLIP_COLOR or "全部"
    
    dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()
    dlg.On["btn_scan"].Clicked = on_scan
    dlg.On["btn_start"].Clicked = on_start
    dlg.On["btn_stop"].Clicked = on_stop
    dlg.On["btn_basic"].Clicked = on_mode_basic
    dlg.On["btn_pro"].Clicked = on_mode_pro
    
    dlg.Show()
    _update_balance(itm)
    disp.RunLoop()
