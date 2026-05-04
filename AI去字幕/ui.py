# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 达芬奇内部入口
两阶段加载：先显示窗口 → 异步加载业务模块

注意：达芬奇 v20 内部环境有窗口自动关闭 bug。
      如需稳定 UI 体验，请用 ui_external.py（外部子进程方案）。
      本脚本仅作快速状态查看入口。
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

# 阶段1: 创建窗口
dlg = disp.AddWindow({
    "WindowTitle": "AI 去字幕",
    "ID": WIN_ID,
    "Geometry": [800, 300, 480, 200],
}, [
    ui.VGroup({"Spacing": 10}, [
        ui.Label({"ID": "title_lb", "Text": "AI 去字幕"}),
        ui.Label({"ID": "info_lb", "Text": "加载中..."}),
        ui.HGroup({"Spacing": 10}, [
            ui.Button({"ID": "close_btn", "Text": "关闭"}),
        ]),
    ]),
])

itm = dlg.GetItems()

def _close(ev):
    disp.ExitLoop()

dlg.On[WIN_ID].Close = _close
dlg.On["close_btn"].Clicked = _close

# 阶段2: 加载业务模块
try:
    sys.path.insert(0, "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕")
    from config import DEFAULT_MODE, MODE_LABELS, __version__
    from core import connect_resolve, scan_io_clips, query_balance, CLIP_COLOR as _CLIP_COLOR

    itm["title_lb"].Text = f"AI 去字幕 v{__version__}"

    # 快速状态扫描
    info_lines = []
    try:
        _, project, timeline = connect_resolve()
        info_lines.append(f"项目: {project.GetName()}")
        info_lines.append(f"时间线: {timeline.GetName()}")

        clips, report = scan_io_clips(timeline, _CLIP_COLOR)
        if clips is None:
            info_lines.append("IO: 未设置")
        else:
            info_lines.append(f"IO 内: {report.valid} 个待处理片段")

        mode_label = MODE_LABELS.get(DEFAULT_MODE, "正式出片")
        info_lines.append(f"模式: {mode_label}")

        pts = query_balance()
        if pts > 0:
            info_lines.append(f"余额: {pts:.1f} 点 (¥{pts*0.19:.2f})")
    except Exception as e:
        info_lines.append(f"状态: {e}")

    itm["info_lb"].Text = "\n".join(info_lines)
except Exception as e:
    itm["title_lb"].Text = "加载失败"
    itm["info_lb"].Text = str(e)[:300]


def main():
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()
