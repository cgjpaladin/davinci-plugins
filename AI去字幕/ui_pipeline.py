# -*- coding: utf-8 -*-
"""
ui_pipeline.py — AI去字幕 UI 业务逻辑
扫描 / 处理 / 停止 / 撤销 / 余额查询
依赖 ui_widgets.py 提供的 itm, _state, 控件操作函数
"""
import traceback
import os
import sys
import json
import subprocess
import threading
import time
import math
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse

# shared/ 模块路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))

from config import (
    DEBUG, get_output_dir, get_log_dir, __version__,
    SMB_SCRIPTS, SMB_AI_PROJECT,
)
from subtitle_state import init as state_init, acquire_lock, release_lock, is_locked as state_is_locked
import ledger
from timecode import SMPTE
from pipeline_utils import validate_task, calc_cache_savings, estimate_processing_time, format_duration
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    estimate_cost, query_balance, post_check, CLIP_COLOR as _CLIP_COLOR,
    download_and_apply,
)
from adapters.wuhenai_v2 import wuhenai_set_logger
from adapters import SubtitleTask, create_wuhenai_adapter
from logger import UILogger, set_logger
from pricing import point_to_yuan, oss_tracker, ACTIVE_PROVIDER
from interface import DaVinciPipelineUI

# 从 ui_widgets 导入所有 UI 表面元素
from ui_widgets import (
    itm, dlg, disp, _state, WIN_ID, MODE,
    _CLIP_COLORS, _SELECTED_COLOR,
    _check_smb, _flush_log, _apply_ui_state,
    _st, _pg, _bal, _set_btn, _set_proj,
    _smb_log, _log_file, _log_action,
    _ui_lock, _ui_pending,
    _t_start, _t_estimated, _task_count,
    _update_countdown,
    BAL_LB, OSS_LB, PROJ_LB, PATH_LB,
    BTN_SCAN, BTN_START, BTN_STOP, BTN_PICK, BTN_UNDO,
    COLOR_CB, LOG_LB, ST_LB, PG_BAR,
)
import ui_widgets as _uw  # 用于跨模块写全局变量 _t_start/_t_estimated/_task_count

# ── UI 抽象层 ──
ui = DaVinciPipelineUI(itm, _st, _pg, _bal, dlg, _smb_log)

# ── 媒体池自动导航 ──
def discover_folders():
    """列出 SMB 上的所有项目目录。
    Returns: [(项目名, 完整路径), ...] 或 []"""
    results = []
    project_base = SMB_AI_PROJECT
    if not os.path.isdir(project_base):
        return results
    try:
        for name in sorted(os.listdir(project_base)):
            full = os.path.join(project_base, name)
            if os.path.isdir(full) and not name.startswith("."):
                results.append((name, full))
    except Exception:
        # SMB断连时 os.listdir 失败，降级返回空列表（非关键路径）
        pass
    return results

# ── 扫描 ──
_version_checked = False

def _format_tc(frame: int, fps: float, df: bool = False) -> str:
    """帧数 → SMPTE 时码字符串（支持丢帧时码）"""
    tc = SMPTE()
    tc.fps = fps
    tc.df = df
    return tc.gettc(frame)

def _show_clip_stats(clips, od, fps, df, start_frame, allow_unknown=False):
    """遍历片段列表，显示缓存状态并统计。
    scan_io() 和 _refresh_scan_display() 的共享核心。
    Returns: {cache_hits, need_secs, need_pts, need, pts, yuan}
    """
    cache_hits = 0; need_secs = 0; need_pts = 0
    for c in clips:
        pos_str = _format_tc(c.start_frame + start_frame, fps, df)
        is_cached = bool(od and ledger.find_output(c.file_name))
        if allow_unknown and not od:
            label, emoji = "未知", "🟠"
        else:
            label, emoji = ("可复用", "🟢") if is_cached else ("需处理", "🟡")
        ui.log_info(f"  {emoji} {c.name} | 位置：{pos_str} | 长度：{c.duration:.0f}秒 | {label}")
        if is_cached:
            cache_hits += 1
        else:
            need_secs += c.duration
            need_pts += int(c.duration) + (1 if c.duration % 1 > 0 else 0)

    need = len(clips) - cache_hits
    pts = max(1, need_pts)
    yuan = point_to_yuan(pts)
    summary = f"扫描结果：当前选区内，共 {len(clips)} 个符合筛选条件的片段"
    if od:
        if cache_hits > 0:
            summary += f"（其中 {cache_hits} 个可复用）"
        summary += f"  |  {need} 个待处理"
    else:
        summary += "  |  请先选择项目路径以启用缓存复用"
    ui.log_info(summary)
    return {"cache_hits": cache_hits, "need_secs": need_secs, "need_pts": need_pts,
            "need": need, "pts": pts, "yuan": yuan}

def scan_io(*_):
    """扫描时间线 IO 范围内标橙色的片段，显示缓存/预估信息。每次点击扫描按钮触发。
    注：片段遍历逻辑与 _refresh_scan_display() 有约50行重复，修改任一处需同步另一处。
    """
    global _version_checked
    if not _check_smb(): return
    # 首次扫描时检查 SMB 上的版本是否已更新
    if not _version_checked:
        _version_checked = True
        try:
            import re
            smb_cfg = os.path.join(SMB_SCRIPTS, "AI去字幕", "config.py")
            if os.path.exists(smb_cfg):
                with open(smb_cfg) as f:
                    m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
                if m and m.group(1) != __version__:
                    ui.log_warn(f"⚠ 版本已更新（{__version__} → {m.group(1)}），请重启达芬奇以生效")
        except Exception:
            # 版本检查是非关键路径：SMB不可用/config格式变化时静默跳过
            pass
    _log_action("扫描当前选区")
    ui.set_status("扫描中...")
    _state["clips_scanned"] = False
    try: itm[LOG_LB].Text = ""
    except Exception: _smb_log("[ui_pipeline] 清空 LOG_LB 失败")
    try:
        _, project, timeline = connect_resolve()
        clips, report = scan_io_clips(timeline, _SELECTED_COLOR)

        if clips is None:
            ui.log_warn("请设置 IO 入出点"); ui.set_status("就绪 — 请设置 IO 入出点"); return
        if not clips:
            ui.log_info("IO 内无符合筛选的片段"); ui.set_status("无有效片段"); return

        _state["clips"] = clips
        _state["scanned_count"] = report.valid

        ui.log_info("── ① 扫描选区 ──")

        # 获取 IO 范围
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        _state["io_in"] = io_in
        _state["io_out"] = io_out
        _state["timeline_name"] = timeline.GetName()

        # 时间线帧率 + 丢帧标志 + 起始偏移
        fps_str = project.GetSetting("timelineFrameRate")
        fps = float(fps_str) if fps_str else 25.0
        df = bool(int(timeline.GetSetting("timelineDropFrameTimecode") or 0))
        start_frame = timeline.GetStartFrame()
        _state["fps"] = fps
        _state["df"] = df
        _state["start_frame"] = start_frame

        # 逐片段显示 + 缓存检测
        pr = _state["project_root"] or ""
        od = pr and get_output_dir(pr) or ""
        stats = _show_clip_stats(clips, od, fps, df, start_frame, allow_unknown=not od)
        need, pts, yuan = stats["need"], stats["pts"], stats["yuan"]

        # 批量并行：同时处理，总时间 ≈ 上传+处理+下载，约 2x素材时长 + 60s 基础开销
        need_secs = stats["need_secs"]
        # 多片段并发上传（v1.8）：系数 2.0；单片段无并发收益仍用 2.3
        factor = 2.0 if len(clips) > 1 else 2.3
        total_time = max(1, math.ceil((need_secs * factor + 60) / 60)) if need > 0 else 0
        if need > 0 and od:
            ui.log_info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")

        ops_logger.cost_estimate(pts, yuan, total_time, need, stats["cache_hits"])

        _state["clips_scanned"] = True
        itm[BTN_START].Enabled = bool(_state["project_root"])
        if _state["project_root"]:
            itm[PROJ_LB].Text = "③ 请点击开始处理"
        ui.set_status(f"待处理: {report.valid} 个片段")
        _smb_log(f"扫描 — 项目: {project.GetName()} 时间线: {timeline.GetName()} IO={io_in}→{io_out} 内{report.valid}片段 需处理{need} 约{total_time}分钟 预估¥{yuan}")
        refresh_bal()
    except Exception as e:
        ui.log_fail(f"扫描失败: {e}")
        _smb_log(f"扫描失败: {e}")

def _refresh_scan_display():
    """选完项目路径后，刷新已扫描片段的缓存状态（🟠→🟢/🟡）"""
    clips = _state.get("clips", [])
    if not clips:
        return
    pr = _state["project_root"]
    od = pr and get_output_dir(pr) or ""
    fps = _state.get("fps", 25.0)
    df = _state.get("df", False)
    start_frame = _state.get("start_frame", 0)

    itm[LOG_LB].Text = ""
    ui.log_info("\n\n── ① 扫描选区 ──")
    stats = _show_clip_stats(clips, od, fps, df, start_frame)
    need, pts, yuan = stats["need"], stats["pts"], stats["yuan"]
    if need > 0:
        need_secs = stats["need_secs"]
        avg = max(60, min(120, need_secs / max(1, need) * 3))
        total_time = int(need * avg / 60)
        ui.log_info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")
        ui.set_status("就绪")


# ── 余额 ──
_cached_balance = 0  # 启动时刷新一次，处理期间复用，避免重复HTTP

def refresh_bal():
    """刷新余额显示（主线程调用，UI 按钮绑定）"""
    global _cached_balance
    pts = query_balance()
    _cached_balance = pts
    if pts > 0:
        _bal(f"无痕 ¥{point_to_yuan(pts):.2f}")
    else:
        _bal("余额: 查询失败")


# ── 阿里云余额 ──
def refresh_oss_bal():
    """查阿里云账户现金余额"""
    try:
        from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
        if not OSS_ACCESS_KEY_ID:
            itm[OSS_LB].Text = "<div align='right'>阿里云 | 未配置凭证</div>"
            return
        # 阿里云签名要求所有非[0-9a-zA-Z]字符编码，包括 /
        _enc = lambda s: urllib.parse.quote(str(s), safe="")
        params = {
            'Action': 'QueryAccountBalance', 'Format': 'JSON', 'Version': '2017-12-14',
            'AccessKeyId': OSS_ACCESS_KEY_ID, 'SignatureMethod': 'HMAC-SHA1',
            'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'SignatureVersion': '1.0', 'SignatureNonce': str(int(time.time()*1000)),
        }
        sorted_keys = sorted(params.keys())
        canonical = '&'.join(f'{_enc(k)}={_enc(params[k])}' for k in sorted_keys)
        string_to_sign = f'GET&{_enc("/")}&{_enc(canonical)}'
        sig = base64.b64encode(hmac.new((OSS_ACCESS_KEY_SECRET+'&').encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
        params['Signature'] = sig
        url = 'https://business.aliyuncs.com/?' + '&'.join(
            f'{_enc(k)}={_enc(params[k])}' for k in sorted_keys + ['Signature'])
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get('Success'):
            cash = data['Data']['AvailableCashAmount']
            itm[OSS_LB].Text = f"<div align='right'>阿里云 | ¥{cash}</div>"
    except Exception as e:
        ui.log_warn(f"阿里云余额查询异常: {e}")
        itm[OSS_LB].Text = "<div align='right'>阿里云 | 查询失败</div>"


# ── 处理 ──
def process(*_):
    """跑在子线程，只做业务逻辑，不碰 UI"""
    _state["stop"] = False
    _state["processing"] = True
    _set_btn(scan=False, start=False, pick=False, stop=True, warn=True)
    oss_tracker.reset()

    clips = _state["clips"]
    pr = _state["project_root"]
    if not pr:
        ui.log_fail("请先选择项目路径"); return

    # 记录处理前余额 + 开始时间 + 阶段计时
    pts_before = _cached_balance
    t_start = time.time()
    t_prep_end = t_start  # 初始化
    od = get_output_dir(pr)

    try:
        _, project, timeline = connect_resolve()

        ops_logger.init(get_log_dir(pr))
        ops_logger.session_start(project.GetName(), timeline.GetName(), MODE, 0)
        ops_logger.clip_scan(len(clips), 0, [c.name for c in clips])

        # 任务准备
        prepared = prepare_tasks(clips, MODE, od, force=False, stop_check=lambda: _state["stop"])

        # 适配器
        adapter = create_wuhenai_adapter()
        # 适配器日志：关键信息入 SMB 日志便于排查，错误同时推送 UI
        def _adapter_log(msg: str):
            if "[无痕AI 2.1]" not in msg:
                return
            body = msg.split("[无痕AI 2.1] ")[-1] if "[无痕AI 2.1] " in msg else ""
            # 框选/提交/完成 等关键信息
            if any(kw in body for kw in ("框选", "全屏自动", "已提交", "全部完成")):
                _smb_log(f"[适配器] {body}")
            # 已提交/完成 → 推送到 UI（不显示 task_id）
            if any(kw in body for kw in ("已提交", "全部完成")):
                clean = body.split(" → ")[0] if " → " in body else body
                ui.log_info(f"  {clean}")
            # 错误 → SMB + UI
            if any(kw in body for kw in ("失败", "超时", "网络错误")):
                _smb_log(f"[适配器] {body}")
                ui.log_info(f"  ⚠ {body}")
        wuhenai_set_logger(_adapter_log)

        ui.log_info("\n\n── ② 缓存复用 ──")
        # 检查是否被停止中断
        if _state["stop"]:
            ui.log_info("  ⏹ 已停止")
            return
        if prepared.cache_hits:
            ui.log_info(f"📦 缓存命中 {prepared.cache_hits} 个，直接替换")
            savings = calc_cache_savings(clips, prepared.cache_hit_names)
            if savings["yuan"] > 0.01:
                ui.log_info(f"  💰 省了约 ¥{savings['yuan']} ({savings['secs']}秒)")
                _smb_log(f"缓存省钱: ¥{savings['yuan']} ({prepared.cache_hits}片段 {savings['secs']}秒)")
            for cn in prepared.cache_hit_names:
                ui.log_ok(f"  {cn}")
        else:
            ui.log_info("  无可复用缓存")
        if not prepared.tasks:
            if prepared.cache_hits:
                ui.log_info("\n\n── ⑤ 最终报告 ──")
                ui.log_ok("🎉 全部完成！")
                t_elapsed = int(time.time() - t_start)
                ui.log_info(f"  耗时 {format_duration(t_elapsed)}  ·  ¥0  ·  余额 ¥{point_to_yuan(pts_before):.2f}")
                # 缓存省钱统计
                savings = calc_cache_savings(clips, prepared.cache_hit_names)
                if savings["secs"] > 0:
                    ui.log_info(f"  💰 缓存省钱: ¥{savings['yuan']} ({savings['secs']}秒)")
                ui.notify("AI 去字幕", f"全部由缓存完成（{prepared.cache_hits}个片段）")
            else:
                ui.log_ok("没有有效任务")
            _set_btn(scan=True, pick=True, stop=False, warn=False)
            itm[COLOR_CB].Enabled = True
            itm[BTN_UNDO].Enabled = True
            itm[BTN_START].Enabled = False
            itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
            return

        ui.log_info("\n\n── ③ AI去字幕中 ──")
        ui.set_progress(0.05); ui.set_status(f"准备处理 {len(prepared.tasks)} 个片段...")

        # 余额
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _, total_est, _, yuan = estimate_cost(prepared.tasks, MODE)
        _smb_log(f"处理开始 — {project.GetName()}/{timeline.GetName()} 待处理{len(prepared.tasks)}片段 预估¥{yuan}")
        try:
            bal = adapter.get_balance()
            pts = bal.get("balance", 0)
            _bal(f"无痕 ¥{point_to_yuan(pts):.2f}")
            if pts < total_est:
                ui.log_fail(f"余额不足: {pts} < {total_est}")
                _smb_log(f"余额不足拦截: 余额{pts}pt < 需{total_est}pt")
                return
        except Exception:
            # 余额查询是前置检查，API可能网络波动，失败不阻塞处理
            ui.log_warn("余额查询失败，跳过保护")

        results = []; total = len(prepared.tasks)
        intercepted = 0  # 被拦截跳过的

        # 抢锁
        locked_tasks = []
        for t in prepared.tasks:
            if _state["stop"]:
                break
            lock_result = acquire_lock(t.name)
            if lock_result:
                if lock_result == "reclaimed":
                    _smb_log(f"锁回收: {t.name}")
                # 文件 + 时长校验
                ok_flag, err_msg = validate_task(t)
                if not ok_flag:
                    ui.log_warn(f"  ⚠ {t.name}: {err_msg}，跳过")
                    _smb_log(f"校验跳过: {t.name} — {err_msg}")
                    release_lock(t.name)
                    intercepted += 1; continue
                locked_tasks.append(t)
            else:
                owner = state_is_locked(t.name) or "其他同事"
                ui.log_warn(f"  {t.name}: {owner} 正在处理中")
                intercepted += 1
        # 因停止而未处理的
        unprocessed = total - len(locked_tasks) - intercepted
        if not locked_tasks:
            ui.log_info("\n\n── ⑤ 最终报告 ──")
            msg = f"🎉 处理完成: {prepared.cache_hits} 个处理完成（缓存）"
            if intercepted > 0:
                msg += f"，{intercepted} 个被跳过"
            ui.log_ok(msg)
            return

        # 二次余额校验（防多机器同时提交超支）
        try:
            pts_now = adapter.get_balance().get("balance", 0)
            if pts_now < total_est:
                ui.log_fail(f"余额不足: {pts_now} < {total_est}（可能有其他机器正在处理）")
                _smb_log(f"二次余额拦截: {pts_now}pt < 需{total_est}pt")
                for t in locked_tasks:
                    release_lock(t.name)
                return
        except Exception:
            # 二次余额校验失败不阻塞（网络波动），主流程已有首次余额检查
            pass
        api_tasks = [SubtitleTask(**t.kwargs) for t in locked_tasks]

        t_prep_end = time.time()  # 准备阶段结束

        # 真实进度回调：把 API 返回的进度百分比同步到 UI
        def _on_progress(phase, ratio):
            _st._last_ratio = ratio
            ui.set_progress(ratio)
            phase_names = {"upload": "上传中...", "submit": "提交中...",
                           "processing": "AI 处理中...", "download": "下载中..."}
            global _phase_text
            _phase_text = phase_names.get(phase, "处理中...")

        t_batch = time.time()
        # 设置倒计时全局变量（_update_countdown 在稳定版轮询中消费）
        _uw._t_start = t_batch
        _uw._t_estimated = estimate_processing_time(locked_tasks)
        _uw._task_count = len(api_tasks)
        _smb_log(f"预估时间 — 片段总{sum(math.ceil(t.duration) for t in locked_tasks)}秒 ({len(api_tasks)}个) 公式={_uw._t_estimated:.0f}秒")
        if len(api_tasks) == 1:
            # 单片段：单任务模式（更快，无批量开销）
            ui.log_info("    AI 处理中...")
            ui.set_status("AI 处理中...")
            result = adapter.process(api_tasks[0], timeout=600,
                                     cancel_check=lambda: _state["stop"])
            api_results = [result]
        else:
            # 多片段：批量并行模式
            ui.log_info(f"    AI 处理中...")
            api_results = adapter.process_batch(api_tasks, timeout=600,
                                                cancel_check=lambda: _state["stop"],
                                                progress_callback=_on_progress)
        elapsed = time.time() - t_batch
        ui.log_info(f"  全部完成，耗时 {elapsed:.0f}秒")
        ui.set_progress(0.7); ui.set_status(f"下载处理结果...")

        for t, r in zip(locked_tasks, api_results):
            if r and r.success:
                release_lock(t.name)
                _smb_log(f"  ✅ {t.name} ({elapsed:.0f}s batch)")
            else:
                msg = getattr(r, 'error_message', '未知错误') if r else '处理失败'
                release_lock(t.name)
                ui.log_fail(f"  ❌ {t.name}: {msg}")
                _smb_log(f"  ❌ {t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, r, elapsed / len(locked_tasks),
                           t.tl_item, t.tl_color or "", t.mp_color or "", t.alt_tl_items or ()))

        # 下载 + 替换（下载归 ③，替换瞬间完成）
        ui.log_info("  下载处理结果...")
        _state["stop"] = False
        ok_count, fail_list, output_files = download_and_apply(
            results, od, MODE,
            check_stop=lambda: _state["stop"],
            on_start=lambda name: ui.set_status(f"下载中... {name}"),
            on_done=lambda ep, subdir, name: None,  # 替换结果统一在 ④ 展示
            on_fail=lambda name, err: ui.log_fail(f"  {name}: {err}"),
        )
        for fe in fail_list:
            _smb_log(f"下载失败: {fe['name']} — {fe['error']}")

        # ④ 替换回时间线 — 替换已完成，这里只展示结果
        ui.log_info("\n── ④ 替换回时间线 ──")
        for i, of in enumerate(output_files, 1):
            ui.log_ok(f"[{i:0{len(str(len(results)))}d}/{len(results)}] 已替换  {os.path.basename(of)}")

        fail_count = len(results) - ok_count
        ui.set_progress(1.0); ui.set_status(f"完成 {ok_count}/{len(results)}")
        ui.log_info("\n\n── ⑤ 最终报告 ──")
        t_api_end = time.time()

        # post_check 放这里（用户已看到"完成"，后台静默校验）
        pc = post_check(output_files)
        if pc["fail"] > 0:
            ui.log_warn(f"校验异常: {pc['ok']}/{pc['total']} 通过, {pc['fail']} 失败")
            for p in pc["problems"]:
                ui.log_warn(f"  ❌ {p['file']}: {', '.join(p['issues'])}")
            ui.log_warn("  💡 建议撤销后重新处理")

        # 阶段耗时
        t_prep_elapsed = int(t_prep_end - t_start)
        t_api_elapsed = int(t_api_end - t_prep_end)
        t_replace_elapsed = int(time.time() - t_api_end)

        total_done = ok_count + prepared.cache_hits
        msg = f"🎉 处理完成: {total_done} 个处理完成"
        if prepared.cache_hits > 0:
            msg += f"（其中 {prepared.cache_hits} 个可复用）"
        if fail_count > 0:
            msg += f"，{fail_count} 个失败"
        if intercepted > 0:
            msg += f"，{intercepted} 个被跳过"
        if unprocessed > 0:
            msg += f"，{unprocessed} 个未处理（已停止）"
        ui.log_ok(msg)

        t_elapsed = int(time.time() - t_start)
        # 直接显示耗时和费用（不调API查余额，省2-6秒，用户可秒关）
        ui.log_info(f"  总耗时 {format_duration(t_elapsed)}  ·  ¥{yuan:.2f}")

        # OSS 流量（内部记录，不展示给用户）
        oss = oss_tracker.snapshot()
        if oss["traffic_gb"] > 0.001:
            _smb_log(f"OSS: {oss['traffic_gb']:.3f}GB ¥{oss['total_cost']:.4f}")

        oss_tracker.reset()
        _smb_log(f"完成 — {ok_count}/{len(results)} 耗时{format_duration(t_elapsed)} 预估¥{yuan:.2f} 余额(处理前)¥{point_to_yuan(pts_before):.2f} 阶段:{t_prep_elapsed}/{t_api_elapsed}/{t_replace_elapsed}s")
        # 用缓存余额更新UI（不调API，不阻塞）
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _bal(f"无痕 ¥{point_to_yuan(pts_before):.2f}")
        ops_logger.session_end(ok_count, len(results) - ok_count, len(results), pts_before, total_est, int(t_elapsed), yuan)

        # 阶段耗时明细（内部记录）
        _smb_log(f"阶段耗时 — 准备:{t_prep_elapsed}s AI:{t_api_elapsed}s 替换:{t_replace_elapsed}s")

        # macOS 系统通知（子线程也可发出，不需要主线程）
        ui.notify("AI 去字幕", f"{total_done}个片段处理完成（耗时{format_duration(t_elapsed)}）")
    except Exception as e:
        ui.log_fail(f"{e}")
        _smb_log(f"处理异常: {e}")
        traceback.print_exc()
    finally:
        _state["stop"] = False
        _state["processing"] = False
        itm[COLOR_CB].Enabled = True
        itm[BTN_UNDO].Enabled = True
        _set_btn(scan=True, pick=True, stop=False, warn=False)
        itm[BTN_START].Enabled = False
        itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
        try: itm[ST_LB].Text = ""
        except Exception: _smb_log("[ui_pipeline] 清空 ST_LB 失败")


# ── 停止 ──
def stop(*_):
    _log_action("停止")
    if _state["processing"]:
        _state["stop"] = True; ui.log_warn("停止中...")


# ── 撤销替换 ──
def undo(*_):
    """将 IO 内的去字幕片段换回原片（基于 ledger 记录，不靠文件名匹配）"""
    _log_action("撤销替换")
    if _state["processing"]:
        ui.log_warn("处理中，无法撤销"); return
    try:
        _, project, timeline = connect_resolve()
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        if io_out <= io_in:
            ui.log_warn("请设置 IO 入出点"); return

        ui.log_info("\n\n── 撤销替换 ──")
        found = 0; undone = 0
        for t in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", t) or []:
                # 与 IO 有重叠才算（不只是 Start 在内）
                if item.GetEnd() <= io_in or item.GetStart() >= io_out:
                    continue
                mp = item.GetMediaPoolItem()
                if not mp:
                    continue
                # 只撤销当前选中颜色的片段
                item_color = item.GetClipColor() or ""
                if item_color != _SELECTED_COLOR:
                    continue
                path = mp.GetClipProperty("File Path") or ""
                rec = ledger.find_completed_record(path)
                original = rec.get("original_path", "") if rec else ""
                if original and os.path.exists(original):
                    # 保存当前颜色（用户可能设了任意颜色），撤销后恢复
                    save_tl_color = item.GetClipColor() or ""
                    save_mp_color = mp.GetClipColor() or ""
                    mp.ReplaceClipPreserveSubClip(original)
                    if save_mp_color:
                        mp.SetClipColor(save_mp_color)
                    if save_tl_color and save_tl_color != save_mp_color:
                        try: item.SetClipColor(save_tl_color)
                        except Exception:
                            # 颜色恢复失败不阻塞撤销（达芬奇协作模式偶发异常）
                            pass
                    ui.log_ok(f"  ↩ {item.GetName()}")
                    undone += 1
                    found += 1
                    _smb_log(f"撤销: {item.GetName()} → 原片")

        if found == 0:
            ui.log_info("  IO 内无已处理片段")
        else:
            ui.log_info(f"  撤销 {undone}/{found} 个片段")
    except Exception as e:
        ui.log_fail(f"撤销失败: {e}")

