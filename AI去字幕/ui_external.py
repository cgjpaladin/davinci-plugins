# -*- coding: utf-8 -*-
"""
AI 去字幕 UI — 外部进程版
绕过达芬奇内嵌 Python，用系统 Python 3.13 运行。
核心逻辑收敛到 core.py，本文件只做 UI 事件绑定 + 线程编排。
"""
import os
import sys
import time
import threading
import traceback
import urllib.request
from copy import deepcopy

os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.append(_RESOLVE_MODULES)
sys.path.insert(0, "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕")

import DaVinciResolveScript as bmd
from config import (
    ADAPTER_CONFIGS, DEFAULT_MODE, MODE_LABELS,
    DEBUG, get_project_root, get_output_dir, get_log_dir, __version__,
)
from adapters import WatermarkTask
from adapters.ghostcut import GhostCutAdapter
from watermark_state import (
    mark_processed, release_lock, acquire_lock, init as state_init,
)
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    build_output_path, estimate_cost, query_balance, post_check,
    CLIP_COLOR as _CLIP_COLOR,
)
from logger import UILogger, set_logger, info, warn, fail, ok as log_ok

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

# ── 窗口（注意：构造时不用 Visible: False，避免 ScriptSymbolD0Ev 崩溃）──
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

# 启动时隐藏进度条
itm[PG_BAR].Visible = False

# ── 注入 UI 日志器 ──
def _ui_write(msg: str):
    try:
        lg = itm[LOG_LB]; t = (lg.Text or "").split("\n")
        lg.Text = "\n".join(t[-50:]) + msg + "\n"
    except: pass

set_logger(UILogger(_ui_write))

def _st(t):
    try: itm[ST_LB].Text = t
    except: pass

def _bal(t):
    try: itm[BAL_LB].Text = t
    except: pass

def _pg(r):
    try:
        itm[PG_BAR].Visible = True
        itm[PG_BAR].Resize([max(1, int(itm[PG_BG].GetGeometry()[3]*r)), 3])
    except: pass


# ── 扫描 ──
def scan_io(*_):
    _st("扫描中...")
    try:
        _, project, timeline = connect_resolve()
        clips, report = scan_io_clips(timeline, _CLIP_COLOR)

        if clips is None:
            warn("请设置IO入出点"); return

        info(f"IO: {report.total} 个片段，{report.valid} 个符合筛选")
        for c in clips:
            info(f"  {c.name}")

        _st(f"扫描完成: {report.valid} 个待处理")
        threading.Thread(target=refresh_bal, daemon=True).start()
    except Exception as e:
        fail(f"扫描失败: {e}")


# ── 刷新余额 ──
def refresh_bal():
    pts = query_balance()
    if pts > 0:
        _bal(f"💰 {pts:.1f} 点")
    else:
        _bal("💰 查询失败")


# ── 处理 ──
def process(*_):
    if _state["processing"]: return
    _state["processing"] = True; _state["stop"] = False; itm[BTN_START].Enabled = False
    mode = _state["mode"]

    try:
        _, project, timeline = connect_resolve()

        # 扫描
        clips, _ = scan_io_clips(timeline, _CLIP_COLOR)
        if clips is None:
            warn("未设置IO"); return
        if not clips:
            info("没有有效片段"); return

        # 项目路径
        pr = get_project_root(clips[0].path) if clips else None
        if not DEBUG and not pr:
            fail("无法识别项目目录"); return
        od = get_output_dir(pr)
        state_init(pr)
        ops_logger.init(get_log_dir(pr))
        ops_logger.session_start(project.GetName(), timeline.GetName(), mode, 0)
        ops_logger.clip_scan(len(clips), 0, [c.name for c in clips])

        info(f"共 {len(clips)} 个片段 | {MODE_LABELS.get(mode, mode)}")

        # 任务准备（校验+缓存）
        prepared = prepare_tasks(clips, timeline, mode, od, pr, force=False)

        if prepared.pro_upgrades:
            info(f"  ↻ {prepared.pro_upgrades} 个预览版将升级")
        if prepared.cache_hits:
            log_ok(f"  📦 缓存命中 {prepared.cache_hits} 个")
        if not prepared.tasks:
            log_ok("全部完成！" if prepared.cache_hits else "没有有效任务")
            ops_logger.session_end(prepared.cache_hits, 0, prepared.cache_hits)
            return

        # 余额检查
        _, total_est, _ = estimate_cost(prepared.tasks, mode)
        info(f"预估: {total_est} 点 (¥{total_est*0.19:.2f})")
        pts = query_balance()
        if pts > 0:
            ops_logger.balance_check(pts, total_est, "proceed" if pts >= total_est else "blocked")
            _bal(f"💰 {pts:.1f} 点")
            if pts < total_est:
                fail(f"余额不足: {pts:.1f} < {total_est}")
                ops_logger.session_end(0, 0, len(prepared.tasks), pts)
                return
        else:
            warn("余额查询失败，跳过保护")

        # 串行处理（含重试）
        adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
        adapter_cfg["model"] = mode
        adapter = GhostCutAdapter(adapter_cfg)
        results = []; total = len(prepared.tasks)

        for idx, t in enumerate(prepared.tasks, 1):
            if _state["stop"]:
                warn("用户停止"); break
            _st(f"{idx}/{total} {t.name}"); _pg(idx/total)

            if not acquire_lock(t.name):
                warn(f"[{idx}/{total}] {t.name}: 被锁定"); continue

            result = None; elapsed = 0
            for attempt in range(3):
                try:
                    if attempt > 0:
                        warn(f"[{idx}/{total}] {t.name} → 重试 {attempt}/2...")
                    ops_logger.task_submit(t.name, mode, t.duration, attempt)
                    st2 = time.time()
                    task = WatermarkTask(**t.kwargs)
                    result = adapter.process(task, timeout=600)
                    elapsed = time.time() - st2
                    ops_logger.task_result(t.name, str(getattr(result, 'task_id', '')), elapsed, result.success)
                    if not result.success: release_lock(t.name)
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = 3 * (attempt + 1)
                        ops_logger.task_error(t.name, str(e)[:200], attempt)
                        warn(f"[{idx}/{total}] {t.name}: {e}，{wait}s后重试...")
                        time.sleep(wait)
                    else:
                        ops_logger.task_error(t.name, str(e)[:100], attempt)
                        fail(f"[{idx}/{total}] {t.name}: 重试2次均失败")
                        release_lock(t.name)
                        elapsed = 0
                        from adapters import WatermarkResult
                        result = WatermarkResult(success=False, task_id="",
                                                error_message=f"重试2次后失败: {str(e)[:100]}")

            if result and result.success:
                info(f"[{idx}/{total}] {t.name} ({elapsed:.0f}s)")
            else:
                msg = getattr(result, 'error_message', '未知错误') if result else '处理失败'
                fail(f"[{idx}/{total}] {t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, result, elapsed))

        # 下载 + ReplaceClip
        _pg(0.9); ok_count = 0; output_files = []
        for mp_item, name, path, result, elapsed in results:
            if _state["stop"]: break
            if not result or not result.success: continue

            fn = os.path.basename(path)
            dl, ep, subdir, clean_name = build_output_path(fn, od, mode)

            urllib.request.urlretrieve(result.output_path, dl)
            if mp_item.ReplaceClipPreserveSubClip(dl):
                mark_processed(mp_item.GetClipProperty("File Name") or fn, dl, mode)
                ok_count += 1
                output_files.append(dl)
                log_ok(f"  {ep}/{subdir}/{clean_name}")
            else:
                fail(f"  {clean_name} 替换失败")
            release_lock(name)

        # Post-check
        post_check(output_files)

        _pg(1.0); _st(f"完成 {ok_count}/{len(results)}")
        log_ok(f"{ok_count}/{len(results)} 完成"); _bal("")
        ops_logger.session_end(ok_count, len(results) - ok_count, len(results))
    except Exception as e:
        fail(f"{e}")
        traceback.print_exc()
        ops_logger.session_end(0, 0, 0)
    finally:
        _state["processing"] = False; _state["stop"] = False
        itm[BTN_START].Enabled = True


# ── 停止 ──
def stop(*_):
    if _state["processing"]:
        _state["stop"] = True; warn("停止信号已发送...")
    else:
        disp.ExitLoop()


# ── 事件绑定 ──
dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()
dlg.On[MODE_CB].CurrentTextChanged = lambda ev: _state.update(
    mode={"快速预览": "basic", "正式出片": "pro_box"}.get(ev["Text"], DEFAULT_MODE))
dlg.On[BTN_SCAN].Clicked = scan_io
dlg.On[BTN_START].Clicked = lambda ev: threading.Thread(target=process, daemon=True).start()
dlg.On[BTN_STOP].Clicked = stop


def main():
    threading.Thread(target=refresh_bal, daemon=True).start()
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()


if __name__ == "__main__":
    main()
