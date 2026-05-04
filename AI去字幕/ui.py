# -*- coding: utf-8 -*-
"""
AI 去字幕 UI 启动器 — 两阶段加载
阶段1: 纯 UI 窗口（只创建控件，不加载业务逻辑）
阶段2: import 业务模块
"""
import sys

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if _RESOLVE_MODULES not in sys.path:
    sys.path.append(_RESOLVE_MODULES)

import DaVinciResolveScript as bmd

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

WIN_ID = "com.myjc.ai_subtitle"

# ══ 阶段1: 创建窗口 ══
t1 = ui.Label({"ID": "t1", "Text": "窗口加载中..."})
t2 = ui.Label({"ID": "t2", "Text": ""})

dlg = disp.AddWindow({
    "WindowTitle": "AI 去字幕",
    "ID": WIN_ID,
    "Geometry": [800, 300, 500, 500],
}, [
    ui.VGroup({"Spacing": 10}, [
        t1,
        ui.Label({"ID": "mode_lb", "Text": "模式: 正式出片"}),
        ui.Button({"ID": "btn", "Text": "扫描 IO"}),
        t2,
    ]),
])

itm = dlg.GetItems()

def _close(ev):
    disp.ExitLoop()

dlg.On[WIN_ID].Close = _close
dlg.On["btn"].Clicked = lambda ev: _close(ev)

# ══ 阶段2: 加载业务逻辑 ══
itm["t1"].Text = "正在加载插件..."
itm["t2"].Text = ""

errors = []
try:
    sys.path.insert(0, "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕")
    from config import DEFAULT_MODE, MODE_LABELS, __version__
    itm["t1"].Text = f"AI 去字幕 v{__version__}"
    itm["mode_lb"].Text = f"模式: {MODE_LABELS.get(DEFAULT_MODE, '正式出片')}"
    itm["t2"].Text = "加载完成 ✅ — 点击按钮退出测试"
except Exception as e:
    itm["t1"].Text = "加载失败"
    itm["t2"].Text = str(e)[:200]

def main():
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()
