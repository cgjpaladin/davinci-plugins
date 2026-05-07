# -*- coding: utf-8 -*-
"""进度条验证 v3：多方案对比"""
import os, sys, time, threading
os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
sys.path.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as bmd

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

layout = [
    ui.VGroup({"Spacing": 6}, [
        ui.Label({"Text": "进度条动画测试", "StyleSheet": "font-size:14px"}),
        ui.HGroup({"Spacing": 4}, [
            ui.Button({"ID": "btn1", "Text": "方案1: StepLoop"}),
            ui.Button({"ID": "btn2", "Text": "方案2: sleep+Update"}),
            ui.Button({"ID": "btn3", "Text": "方案3: thread+Dispatch"}),
            ui.Button({"ID": "btn_close", "Text": "关闭"}),
        ]),
        ui.Label({"ID": "bar", "Text": "",
                  "StyleSheet": "max-height:12px;background-color:rgb(102,221,39);border-radius:3px"}),
        ui.TextEdit({"ID": "log", "ReadOnly": True, "StyleSheet": "min-height:80px"}),
    ]),
]

dlg = disp.AddWindow({"WindowTitle": "进度条测试v3", "ID": "pg3", "Geometry": [200, 200, 520, 250]}, layout)
itm = dlg.GetItems()
itm["bar"].Visible = True
_MAX_W = 480

def do_log(msg):
    itm["log"].Append(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

def set_bar(ratio):
    ratio = max(0.0, min(1.0, float(ratio)))
    w = int(_MAX_W * ratio)
    itm["bar"].Resize([w, 12])
    itm["bar"].FixedSize = [w, 12]

# 方案1: StepLoop
def anim1(ev):
    do_log("方案1: StepLoop 5步")
    t0 = time.time()
    for i in range(6):
        set_bar(i / 5.0)
        disp.StepLoop(800)
    do_log(f"方案1完成, 耗时{time.time()-t0:.1f}s")

# 方案2: sleep + Update
def anim2(ev):
    do_log("方案2: sleep+Update 5步")
    t0 = time.time()
    for i in range(6):
        set_bar(i / 5.0)
        try: itm["bar"].Update()
        except: pass
        time.sleep(0.8)
    do_log(f"方案2完成, 耗时{time.time()-t0:.1f}s")

# 方案3: thread + Dispatch
def anim3(ev):
    do_log("方案3: thread+Dispatch 10步")
    def _run():
        for i in range(11):
            r = i / 10.0
            disp.Dispatch(lambda ratio=r: (set_bar(ratio), do_log(f"  ratio={ratio:.1f}")))
            time.sleep(0.5)
        disp.Dispatch(lambda: do_log("方案3完成"))
    threading.Thread(target=_run, daemon=True).start()

dlg.On["btn1"].Clicked = anim1
dlg.On["btn2"].Clicked = anim2
dlg.On["btn3"].Clicked = anim3
dlg.On["btn_close"].Clicked = lambda ev: disp.ExitLoop()
dlg.Show()
disp.RunLoop()
