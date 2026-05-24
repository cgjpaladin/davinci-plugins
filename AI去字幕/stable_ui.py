# -*- coding: utf-8 -*-
"""
stable_ui.py — AI去字幕 UI 入口

架构: ui_widgets.py (UI表面) → ui_pipeline.py (业务逻辑) → stable_ui.py (事件绑定+启动)
stable_ui.py 由 launcher.py 通过 subprocess.Popen 外部进程启动。
"""
import os
import socket
import subprocess
import threading
import time
import traceback
import sys

# shared/ 模块路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))

from ui_widgets import (
    itm, dlg, disp, _state, WIN_ID, MODE,
    _CLIP_COLORS, _SELECTED_COLOR,
    _check_smb, _flush_log, _apply_ui_state,
    _st, _pg, _bal, _set_btn, _set_proj,
    _event_log, _log_file, _log_action,
    _ui_lock, _ui_pending,
    BAL_LB, OSS_LB, PROJ_LB, PATH_LB,
    BTN_SCAN, BTN_START, BTN_STOP, BTN_PICK, BTN_CONFIRM, BTN_UNDO,
    COLOR_CB, LOG_LB, ST_LB, PG_BAR,
    pick_project, confirm_project, auto_detect_project,
)
import ui_widgets as _uw  # 用于跨模块读全局变量(防import拷贝陷阱)
from ui_pipeline import (
    scan_io, refresh_bal, refresh_oss_bal, process, stop, undo,
    _refresh_scan_display,
)
from core import connect_resolve
from config import get_output_dir, __version__
from logger import info, warn, fail, ok as log_ok

# 关闭窗口时清理
_cleanup_done = False

def on_show(ev):
    """窗口显示时自动刷新余额"""
    if not _check_smb():
        return
    try:
        refresh_bal()
    except Exception as e:
        warn(f"余额刷新失败: {e}")
        _event_log(f"余额刷新失败: {e}")
    try:
        refresh_oss_bal()
    except Exception as e:
        warn(f"阿里云余额刷新失败: {e}")
        _event_log(f"阿里云余额刷新失败: {e}")

def on_close(ev):
    """关闭窗口清理"""
    global _cleanup_done
    if _cleanup_done:
        disp.ExitLoop()
        return
    _cleanup_done = True
    try:
        if _state.get("processing"):
            _state["stop"] = True
            # 停止等待时间（秒）
            time.sleep(0.3)
    except Exception:
        pass
    disp.ExitLoop()

# ═══════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════

def start_process(*_):
    """主线程入口：启动子线程处理 + 轮询消费日志/状态"""
    if _state["processing"]:
        return
    if not _state.get("project_root"):
        warn("请先选择项目路径")
        return
    if not _state.get("clips_scanned"):
        warn("请先扫描当前选区")
        return

    _log_action("开始处理")
    _state["processing"] = True
    _state["stop"] = False

    _set_btn(scan=False, start=False, pick=False, stop=True, warn=True)
    _st("准备中...")
    _pg(0)

    thr = threading.Thread(target=process, daemon=True)
    thr.start()

    while thr.is_alive():
        _flush_log()
        _apply_ui_state()
        disp.StepLoop(100)

    _flush_log()
    _apply_ui_state()

    _state["processing"] = False
    _set_btn(scan=True, start=_state.get("clips_scanned", False) and bool(_state.get("project_root")),
             pick=True, stop=False, warn=False)
    itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"

    # 处理完成通知
    from macos_utils import notify
    notify("达芬奇插件工坊", "AI 去字幕处理完成")

# ═══════════════════════════════════════════
# 事件绑定（必须在所有函数定义之后）
# ═══════════════════════════════════════════

dlg.On[BTN_PICK].Clicked = pick_project
dlg.On[BTN_CONFIRM].Clicked = confirm_project
dlg.On[BTN_SCAN].Clicked = scan_io
dlg.On[BTN_START].Clicked = start_process
dlg.On[BTN_STOP].Clicked = stop
dlg.On[BTN_UNDO].Clicked = undo
dlg.On[WIN_ID].Show = on_show
dlg.On[WIN_ID].Close = on_close


def main():
    """显示 UI 窗口并进入事件循环（阻塞直到用户关闭）。窗口打开后刷余额。"""
    # 防重复窗口（PID 锁文件，跨进程可用）
    _lock_file = os.path.join(os.path.dirname(__file__), ".ui_instance.lock")
    if os.path.exists(_lock_file):
        try:
            with open(_lock_file) as f:
                _old_pid = int(f.read().strip())
            os.kill(_old_pid, 0)
            sys.exit(0)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    with open(_lock_file, "w") as f:
        f.write(str(os.getpid()))
    try:
        dlg.Show()
        dlg.RecalcLayout()
        # 自动推测项目路径（零 SMB IO，毫秒级）
        auto_detect_project()
        # Show 事件在达芬奇 UIDispatcher 中可能异步触发，余额刷新放这里更可靠
        if _check_smb():
            try:
                refresh_bal()
            except Exception as e:
                warn(f"余额刷新失败: {e}")
                _event_log(f"余额刷新失败: {e}")
            try:
                refresh_oss_bal()
            except Exception as e:
                warn(f"阿里云余额刷新失败: {e}")
                _event_log(f"阿里云余额刷新失败: {e}")
        disp.RunLoop()
    except Exception as e:
        fail(f"UI 错误: {e}")
        traceback.print_exc()
        disp.ExitLoop()


if __name__ == "__main__":
    main()
