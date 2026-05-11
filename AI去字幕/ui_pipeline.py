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
    SMB_SCRIPTS, SMB_AI_PROJECT, PRODUCT_NAME,
)
from subtitle_state import init as state_init, acquire_lock, release_lock, is_locked as state_is_locked
import ledger
from timecode import SMPTE
from pipeline_utils import validate_task, calc_cache_savings, estimate_processing_time, format_duration
from log_writer import get_logger as _get_logger
_log_ops = _get_logger("AI去字幕")
from core import (
    connect_resolve, scan_io_clips,
    query_balance, CLIP_COLOR as _CLIP_COLOR,
    restore_clip_colors,
)
from adapters import create_preferred_adapter
from logger import UILogger, set_logger
from pricing import point_to_yuan, ACTIVE_PROVIDER
from interface import DaVinciPipelineUI

# 从 ui_widgets 导入所有 UI 表面元素
import ui_widgets as _uw
from ui_widgets import (
    itm, dlg, disp, _state, WIN_ID, MODE,
    _CLIP_COLORS,
    _check_smb, _flush_log, _apply_ui_state,
    _st, _pg, _bal, _set_btn, _set_proj,
    _event_log, _log_file, _log_action,
    _ui_lock, _ui_pending,
    _t_start, _t_estimated, _task_count,
    _update_countdown,
    BAL_LB, OSS_LB, PROJ_LB, PATH_LB,
    BTN_SCAN, BTN_START, BTN_STOP, BTN_PICK, BTN_UNDO,
    COLOR_CB, LOG_LB, ST_LB, PG_BAR,
)
import ui_widgets as _uw  # 用于跨模块写全局变量 _t_start/_t_estimated/_task_count

# ── UI 抽象层 ──
ui = DaVinciPipelineUI(itm, _st, _pg, _bal, dlg, _event_log)

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
    except Exception: _event_log("[ui_pipeline] 清空 LOG_LB 失败")
    try:
        _, project, timeline = connect_resolve()
        clips, report = scan_io_clips(timeline, _uw._SELECTED_COLOR)

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

        _log_ops.ops({"event": "cost_estimate", "est_points": pts, "est_yuan": yuan,
                       "est_minutes": total_time, "need_process": need, "cache_hits": stats["cache_hits"]})

        # 章节尾部空行：与后续 pipeline 步骤（②复用缓存）之间的分隔
        ui.log_info("")

        _state["clips_scanned"] = True
        itm[BTN_START].Enabled = bool(_state["project_root"])
        if _state["project_root"]:
            itm[PROJ_LB].Text = "③ 请点击开始处理"
        ui.set_status(f"待处理: {report.valid} 个片段")
        _event_log(f"扫描 — 项目: {project.GetName()} 时间线: {timeline.GetName()} IO={io_in}→{io_out} 内{report.valid}片段 需处理{need} 约{total_time}分钟 预估¥{yuan}")
        refresh_bal()
    except Exception as e:
        ui.log_fail(f"扫描失败: {e}")
        _event_log(f"扫描失败: {e}")

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
    ui.log_info("\n── ① 扫描选区 ──")
    stats = _show_clip_stats(clips, od, fps, df, start_frame)
    need, pts, yuan = stats["need"], stats["pts"], stats["yuan"]
    if need > 0:
        need_secs = stats["need_secs"]
        avg = max(60, min(120, need_secs / max(1, need) * 3))
        total_time = int(need * avg / 60)
        ui.log_info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")
        ui.log_info("")  # 章节尾部空行
        ui.set_status("就绪")


# ── 余额 ──
_cached_balance = 0
_cached_provider = ""
_cached_pricing_key = "wuhenai"  # point_to_yuan() 定价 key

def refresh_bal():
    """刷新余额显示 — 按 ADAPTER_PRIORITY 依次尝试"""
    global _cached_balance, _cached_provider, _cached_pricing_key
    from pricing_defaults import ADAPTER_PRIORITY

    for key in ADAPTER_PRIORITY:
        try:
            if key == "ghostcut":
                from adapters import create_ghostcut_adapter
                a = create_ghostcut_adapter()
                bal = a.get_balance()
                pts = sum(x["pointBalance"] for x in bal.get("pointAssets", []) if x["pointBalance"] > 0)
            else:
                from adapters import create_wuhenai_adapter
                a = create_wuhenai_adapter()
                pts = query_balance(a)
            if pts >= 5:
                _cached_balance = pts
                _cached_provider = a.name
                _cached_pricing_key = key
                _bal(f"{_cached_provider} | ¥{point_to_yuan(pts, provider=key):.2f}")
                return
        except Exception:
            continue
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
    """跑在子线程。核心流水线委托给 SubtitlePipeline。

    只在 before_submit 钩子中加入 UI 专属的并发锁+校验逻辑，
    其余步骤（余额/提交/下载/验证/报告）全走基类统一模板。
    """
    _state["stop"] = False
    _state["processing"] = True
    _set_btn(scan=False, start=False, pick=False, stop=True, warn=True)

    clips = _state["clips"]
    pr = _state["project_root"]
    if not pr:
        ui.log_fail("请先选择项目路径"); return

    pts_before = _cached_balance

    try:
        from pipeline import SubtitlePipeline
        from pipeline_base import ResultItem
        from subtitle_state import acquire_lock, release_lock, is_locked as state_is_locked
        from pipeline_utils import validate_task, estimate_processing_time
        import math

        pipeline = SubtitlePipeline()

        # ── UI 专属钩子 ──

        # 跳过 CLI 的环境自检（UI 有自己的检查路径）
        pipeline._check_env = lambda: None
        pipeline._preflight = lambda: None
        # UI 的 scan_io() 已经展示过扫描结果，跳过管道内的重复展示
        pipeline._show_scan_summary = lambda clips: None

        # 进度回调
        def _on_progress(phase, ratio):
            _st._last_ratio = ratio
            ui.set_progress(ratio)

        # UI 专属：并发锁 + 校验
        def _ui_before_submit(tasks):
            from adapters import create_preferred_adapter

            # ── 前置探活：API + OSS ──
            probe = create_preferred_adapter()
            api_ok = probe.check_health()
            oss_ok = probe.check_oss() if hasattr(probe, 'check_oss') else True
            if not api_ok or not oss_ok:
                parts = []
                if not api_ok: parts.append(f"{probe.name} API 不可用")
                if not oss_ok: parts.append("阿里云 OSS 不可用")
                ui.log_fail(f"❌ 预检失败: {' / '.join(parts)} — 请稍后重试")
                ui.set_status("预检失败")
                ui.set_progress(0)
                _event_log(f"预检失败 — API={api_ok} OSS={oss_ok}")
                return []

            # ── 并发锁 + 校验 ──
            locked = []
            for t in tasks:
                if _state["stop"]:
                    break
                lock_result = acquire_lock(t.name)
                if lock_result:
                    if lock_result == "reclaimed":
                        _event_log(f"锁回收: {t.name}")
                    ok_flag, err_msg = validate_task(t)
                    if not ok_flag:
                        ui.log_warn(f"  ⚠ {t.name}: {err_msg}，跳过")
                        _event_log(f"校验跳过: {t.name} — {err_msg}")
                        release_lock(t.name)
                        continue
                    locked.append(t)
                else:
                    owner = state_is_locked(t.name) or "其他同事"
                    ui.log_warn(f"  {t.name}: {owner} 正在处理中")
            return locked

        pipeline._before_submit = _ui_before_submit

        # 缓存展示覆盖（UI 有详细的逐条展示，标题走 pipeline.log）
        def _ui_do_prepare(clips, mode):
            tasks, cache_hits, cache_hit_names = pipeline._prepare(clips, mode)
            pipeline._report["cache_hits"] = cache_hits
            pipeline._report["task_count"] = len(tasks)

            if cache_hits:
                for cn in cache_hit_names:
                    pipeline.log.ok(f"{cn} — 可复用")
                from pipeline_utils import calc_cache_savings
                savings = calc_cache_savings(clips, cache_hit_names)
                pipeline.log.cache_savings(cache_hits, savings.get("yuan", 0), savings.get("secs", 0))
                _event_log(f"缓存省钱: ¥{savings.get('yuan', 0)} ({cache_hits}片段 {savings.get('secs', 0)}秒)")
            else:
                pipeline.log.info("无可复用缓存")

            if not tasks:
                return [], True  # 全部缓存完成 → 仍会走最终报告

            # 设置倒计时（_update_countdown 在稳定版轮询中消费）
            _uw._t_start = time.time()
            _uw._t_estimated = estimate_processing_time(tasks) if tasks else 60
            _uw._task_count = len(tasks)
            return tasks, False

        pipeline._do_prepare = _ui_do_prepare

        # ── 执行 ──
        pipeline.run(
            ui=DaVinciPipelineUI(itm, _st, _pg, _bal, dlg, _event_log),
            project_root=pr, mode=MODE,
            clips=clips, batch=True,
            stop_check=lambda: _state["stop"],
            on_progress=_on_progress,
        )

        # 余额更新（处理完成后用缓存的余额）
        _bal(f"{_cached_provider} | ¥{point_to_yuan(pts_before, provider=_cached_pricing_key):.2f}")

    except Exception as e:
        ui.log_fail(f"{e}")
        _event_log(f"处理异常: {e}")
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
        except Exception: _event_log("[ui_pipeline] 清空 ST_LB 失败")


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

        ui.log_info("── 撤销替换 ──")
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
                if item_color != _uw._SELECTED_COLOR:
                    continue
                path = mp.GetClipProperty("File Path") or ""
                rec = ledger.find_completed_record(path)
                original = rec.get("original_path", "") if rec else ""
                if original and os.path.exists(original):
                    # 保存当前颜色（用户可能设了任意颜色），撤销后恢复
                    save_tl_color = item.GetClipColor() or ""
                    save_mp_color = mp.GetClipColor() or ""
                    # 保存链接音频原色（ReplaceClip 前读取）
                    linked_colors = []
                    try:
                        for li in (item.GetLinkedItems() or ()):
                            linked_colors.append((li, li.GetClipColor() or ""))
                    except Exception: pass
                    mp.ReplaceClipPreserveSubClip(original)
                    restore_clip_colors(mp, item, save_tl_color, save_mp_color, log_tag="撤销",
                                       linked_colors=linked_colors)
                    ui.log_ok(f"  ↩ {item.GetName()}")
                    undone += 1
                    found += 1
                    _event_log(f"撤销: {item.GetName()} → 原片")

        if found == 0:
            ui.log_info("  IO 内无已处理片段")
        else:
            ui.log_info(f"  撤销 {undone}/{found} 个片段")
    except Exception as e:
        ui.log_fail(f"撤销失败: {e}")

