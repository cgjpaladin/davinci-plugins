# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 外部进程版
绕过达芬奇内嵌 Python，用系统 Python 3.13 运行，已验证窗口构造正常
"""
import sys, os, time, threading, re, math, urllib.request
from copy import deepcopy

os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.append(_RESOLVE_MODULES)
sys.path.insert(0, "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕")

import DaVinciResolveScript as bmd
from config import (
    ADAPTER_CONFIGS, DEFAULT_MODE, MODE_LABELS, MODE_FILE_TAGS,
    COST_PER_MODE, MAX_SOURCE_DURATION, CLIP_COLOR, DEFAULT_MASK_REGION,
    DEBUG, get_project_root, get_output_dir, get_log_dir, __version__
)
from adapters import WatermarkTask, WatermarkResult
from adapters.ghostcut import GhostCutAdapter
from watermark_state import *
import ops_logger

WIN_ID = "com.myjc.ai_subtitle_ui"

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

_state = {"processing": False, "stop": False, "mode": DEFAULT_MODE}

# ── 控件ID ──
MODE_CB, BAL_LB = "mode_cb", "bal_lb"
BTN_SCAN, BTN_START, BTN_STOP = "btn_scan", "btn_start", "btn_stop"
LOG_LB, ST_LB = "log_lb", "st_lb"
PG_BG, PG_BAR = "pg_bg", "pg_bar"

# ── 窗口 ──
dlg = disp.AddWindow({
    "WindowTitle": f"AI 去字幕 v{__version__}",
    "ID": WIN_ID,
    "Geometry": [800, 300, 500, 520],
    "WindowFlags": {"Window": True, "WindowStaysOnTopHint": True},
}, [
    ui.VGroup({"Spacing": 8}, [
        ui.HGroup({"Spacing": 10}, [
            ui.Label({"ID": "lb1", "Text": "模式:"}),
            ui.ComboBox({"ID": MODE_CB}),
            ui.Label({"ID": BAL_LB, "Text": "💰 --"}),
        ]),
        ui.HGroup({"Spacing": 10}, [
            ui.Button({"ID": BTN_SCAN, "Text": "扫描 IO"}),
            ui.Button({"ID": BTN_START, "Text": "开始处理"}),
            ui.Button({"ID": BTN_STOP, "Text": "停止"}),
        ]),
        ui.Label({"ID": LOG_LB, "Text": ""}),
        ui.Stack({"ID": "pg_stack"}, [
            ui.Label({"ID": PG_BG, "StyleSheet": "max-height: 3px; background-color: rgb(37,37,37);"}),
            ui.Label({"ID": PG_BAR, "StyleSheet": "max-height: 1px; background-color: rgb(102,221,39);"}),
        ]),
        ui.Label({"ID": ST_LB, "Text": "就绪 — 设置 IO 后点击扫描"}),
    ]),
])

itm = dlg.GetItems()
for k in ("basic", "pro_box"):
    itm[MODE_CB].AddItem(MODE_LABELS.get(k, k))
dt = MODE_LABELS.get(DEFAULT_MODE, "正式出片")
count = itm[MODE_CB].Count()
for i in range(count):
    if itm[MODE_CB].ItemText(i) == dt:
        itm[MODE_CB].CurrentIndex = i; break


def _log(msg):
    try:
        lg = itm[LOG_LB]; t = (lg.Text or "").split("\n")
        lg.Text = "\n".join(t[-50:]) + msg + "\n"
    except: pass

def _st(t): 
    try: itm[ST_LB].Text = t
    except: pass

def _bal(t):
    try: itm[BAL_LB].Text = t
    except: pass

def _pg(r):
    try: itm[PG_BAR].Resize([max(1, int(itm[PG_BG].GetGeometry()[3]*r)), 3])
    except: pass

def _dur(mp):
    try: f=int(mp.GetClipProperty("Frames") or 0); fps=float(mp.GetClipProperty("FPS") or 24); return f/fps if fps else 0
    except: return 0

def _resolve():
    r=bmd.scriptapp("Resolve")
    if not r: raise RuntimeError("请先启动 DaVinci")
    return r

# ── 扫描 ──
def scan_io(*_):
    _st("扫描中...")
    try:
        r=_resolve(); pj=r.GetProjectManager().GetCurrentProject(); tl=pj.GetCurrentTimeline()
        if not tl: _log("请先打开时间线"); return
        mk=tl.GetMarkInOut(); v=mk.get("video",{}) if mk else {}; i1,i2=v.get("in",0),v.get("out",0)
        if i2<=i1: _log("请设置IO入出点"); return
        _log(f"IO: {i1}-{i2}")
        seen={}
        for t in range(1,tl.GetTrackCount("video")+1):
            its=tl.GetItemListInTrack("video",t)
            if not its: continue
            for it in its:
                s,e=it.GetStart(),it.GetEnd()
                if s>=i2 or e<=i1: continue
                nm=it.GetName()
                if nm in seen: ex,_=seen[nm]
                if CLIP_COLOR and ex.GetClipColor()==CLIP_COLOR: continue
                seen[nm]=(it,t)
        total,ok=0,0; sk={}
        for nm,(it,_) in seen.items():
            total+=1
            if CLIP_COLOR and it.GetClipColor()!=CLIP_COLOR: continue
            rs=None
            if not it.GetClipEnabled(): rs="禁用"
            elif not it.GetMediaPoolItem(): rs="无媒体引用"
            else:
                mp=it.GetMediaPoolItem(); tp=mp.GetClipProperty("Type") or ""
                if tp in ("复合","Fusion","VFX连接"): rs={"复合":"复合片段","Fusion":"Fusion","VFX连接":"VFX"}.get(tp,tp)
                elif "视频" not in tp: rs=tp or "非视频"
                else:
                    fp=mp.GetClipProperty("File Path")
                    if not fp or not os.path.exists(fp): rs="文件缺失" if fp else "无路径"
            if rs: sk[rs]=sk.get(rs,0)+1; _log(f"  {nm}: {rs}")
            else: ok+=1; _log(f"  {nm}")
        _log("─"*40); _log(f"共 {total} 片段，{ok} 符合筛选")
        _st(f"扫描完成: {ok} 个待处理")
        threading.Thread(target=lambda:(GhostCutAdapter(deepcopy(ADAPTER_CONFIGS["ghostcut"])).get_balance(),None) and None, daemon=True).start()
    except Exception as e: _log(f"扫描失败: {e}")

# ── 刷新余额 ──
def refresh_bal():
    try:
        a=GhostCutAdapter(deepcopy(ADAPTER_CONFIGS["ghostcut"])); b=a.get_balance(); n=time.time()*1000
        p=sum(x["pointBalance"] for x in b.get("pointAssets",[]) if x["pointBalance"]>0 and x.get("expireTime",n+1)>n)
        _bal(f"💰 {p:.1f} 点")
    except: _bal("💰 查询失败")

# ── 处理 ──
def process(*_):
    if _state["processing"]: return
    _state["processing"]=True; _state["stop"]=False; itm[BTN_START].Enabled=False
    try:
        r=_resolve(); pj=r.GetProjectManager().GetCurrentProject(); tl=pj.GetCurrentTimeline()
        mode=_state["mode"]; mt=MODE_FILE_TAGS.get(mode,mode)
        mk=tl.GetMarkInOut(); v=mk.get("video",{}) if mk else {}; i1,i2=v.get("in",0),v.get("out",0)
        if i2<=i1: _log("未设置IO"); return
        seen={}
        for t in range(1,tl.GetTrackCount("video")+1):
            its=tl.GetItemListInTrack("video",t)
            if not its: continue
            for it in its:
                s,e=it.GetStart(),it.GetEnd()
                if s>=i2 or e<=i1: continue
                nm=it.GetName()
                if nm in seen: ex,_=seen[nm]
                if CLIP_COLOR and ex.GetClipColor()==CLIP_COLOR: continue
                seen[nm]=(it,t)
        clips=[]
        for nm,(it,_) in seen.items():
            if CLIP_COLOR and it.GetClipColor()!=CLIP_COLOR: continue
            if not it.GetClipEnabled(): continue
            mp=it.GetMediaPoolItem()
            if not mp: continue
            tp=mp.GetClipProperty("Type") or ""
            if tp in ("复合","Fusion","VFX连接") or "视频" not in tp: continue
            fp=mp.GetClipProperty("File Path")
            if not fp or not os.path.exists(fp): continue
            clips.append((mp,nm,fp))
        if not clips: _log("没有有效片段"); return
        _log(f"共 {len(clips)} 个片段 | {MODE_LABELS.get(mode,mode)}")
        pr=get_project_root(clips[0][2]) if clips else None
        if not DEBUG and not pr: _log("无法识别项目目录"); return
        od=get_output_dir(pr); state_init(pr); ops_logger.init(get_log_dir(pr))
        valid=[]; cc=0
        for mp,nm,path in clips:
            if "_去字幕_正式出片" in nm: continue
            if mode in ("pro","pro_box") and "_去字幕_快速预览" in nm: mp.ReplaceClipPreserveSubClip(path)
            else: record_original(mp.GetClipProperty("File Name") or nm, path)
            fn=mp.GetClipProperty("File Name") or nm; base=os.path.splitext(fn)[0]; ch=None
            try:
                cv2=-1
                for rd,_,fls in os.walk(od):
                    for f in fls:
                        if f.startswith(f"{base}_去字幕_{mt}_v") and f.endswith(".mp4"):
                            vm=re.search(r'_v(\d+)\.mp4$',f); vv=int(vm.group(1)) if vm else 0
                            if vv>cv2: cv2=vv; ch=os.path.join(rd,f)
            except: pass
            if ch:
                if mp.ReplaceClipPreserveSubClip(ch): mark_processed(fn,ch,mode); cc+=1
                else: d=_dur(mp)
                if d<=MAX_SOURCE_DURATION: valid.append((mp,nm,path,fn,d))
            else:
                d=_dur(mp)
                if d>MAX_SOURCE_DURATION: _log(f"  {nm}: 时长{d:.0f}s > 上限"); continue
                valid.append((mp,nm,path,fn,d))
        if cc: _log(f"缓存命中 {cc} 个")
        if not valid: _log("全部完成！" if cc else "没有有效任务"); return
        uc=COST_PER_MODE.get(mode,5); tu=sum(max(1,math.ceil(d/30)) for _,_,_,_,d in valid); te=uc*tu
        _log(f"预估: {te} 点 (¥{te*0.19:.2f})")
        adapter=GhostCutAdapter(deepcopy(ADAPTER_CONFIGS["ghostcut"]))
        try:
            b=adapter.get_balance(); n=time.time()*1000
            p=sum(x["pointBalance"] for x in b.get("pointAssets",[]) if x["pointBalance"]>0 and x.get("expireTime",n+1)>n)
            _bal(f"💰 {p:.1f} 点")
            if p<te: _log(f"余额不足: {p:.1f} < {te}"); return
        except: _log("余额查询失败，跳过保护")
        results=[]; total=len(valid)
        for idx,(mp,nm,path,fn,dur) in enumerate(valid,1):
            if _state["stop"]: _log("用户停止"); break
            _st(f"{idx}/{total} {nm}"); _pg(idx/total)
            if not acquire_lock(fn): _log(f"[{idx}/{total}] {nm}: 被锁定"); results.append((mp,nm,path,None,0)); continue
            st2=time.time(); kw={"video_path":path,"language":"zh","model":mode}
            if mode=="pro_box": kw["mask_regions"]=[{"type":"remove_only_ocr","start":0,"end":99999,"region":DEFAULT_MASK_REGION}]
            try:
                task=WatermarkTask(**kw); result=adapter.submit_task(task)
                adapter.wait_for_result(result.task_id); el=time.time()-st2
                _log(f"[{idx}/{total}] {nm} ({el:.0f}s)")
            except Exception as e:
                result=WatermarkResult(success=False,error_message=str(e)); el=time.time()-st2
                _log(f"[{idx}/{total}] {nm}: {e}")
            finally: release_lock(fn)
            results.append((mp,nm,path,result,el))
        _pg(0.9); ok=0
        for mp,nm,path,result,el in results:
            if _state["stop"]: break
            if not result or not result.success: continue
            fn=os.path.basename(path); bn=re.sub(r'_去字幕_.*$','',os.path.splitext(fn)[0])
            sd="01_预览版" if mode=="basic" else "02_正式出片"; ep="EP00"
            em=re.match(r'(EP\d+)',fn)
            if em: ep=em.group(1)
            ep_dir=os.path.join(od,ep,sd); os.makedirs(ep_dir,exist_ok=True)
            ver=1
            while os.path.exists(os.path.join(ep_dir,f"{bn}_去字幕_{mt}_v{ver:02d}.mp4")): ver+=1
            cl=f"{bn}_去字幕_{mt}_v{ver:02d}.mp4"; dl=os.path.join(ep_dir,cl)
            urllib.request.urlretrieve(result.output_path,dl)
            if mp.ReplaceClipPreserveSubClip(dl):
                mark_processed(mp.GetClipProperty("File Name") or fn,dl,mode); ok+=1
                _log(f"  {cl}")
            else: _log(f"  {cl} 替换失败")
            release_lock(fn)
        _pg(1.0); _st(f"完成 {ok}/{len(results)}"); _log(f"{ok}/{len(results)} 完成"); _bal("")
    except Exception as e: _log(f"{e}")
    finally: _state["processing"]=False; _state["stop"]=False; itm[BTN_START].Enabled=True

# ── 停止 ──
def stop(*_):
    if _state["processing"]: _state["stop"]=True; _log("停止信号已发送...")
    else: disp.ExitLoop()

# ── 事件绑定 ──
dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()
dlg.On[MODE_CB].CurrentTextChanged = lambda ev: _state.update(mode={"快速预览":"basic","正式出片":"pro_box"}.get(ev["Text"],DEFAULT_MODE))
dlg.On[BTN_SCAN].Clicked = scan_io
dlg.On[BTN_START].Clicked = lambda ev: threading.Thread(target=process,daemon=True).start()
dlg.On[BTN_STOP].Clicked = stop

def main():
    threading.Thread(target=refresh_bal,daemon=True).start()
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()

if __name__ == "__main__":
    main()
