# -*- coding: utf-8 -*-
"""
ui_pipeline.py — AI去字幕 UI 业务逻辑
扫描 / 处理 / 停止 / 撤销 / 余额查询
依赖 ui_widgets.py 提供的 itm, _state, 控件操作函数
"""
import traceback
import os
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

from config import (
    DEBUG, get_output_dir, get_log_dir, __version__,
)
from subtitle_state import init as state_init, acquire_lock, release_lock, is_locked as state_is_locked
import ledger
import ops_logger
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    estimate_cost, query_balance, post_check, CLIP_COLOR as _CLIP_COLOR,
    create_wuhenai_adapter, download_and_apply,
)
from adapters.wuhenai_v2 import wuhenai_set_logger
from adapters import SubtitleTask
from logger import UILogger, set_logger, info, warn, fail, ok as log_ok
from pricing import point_to_yuan, oss_tracker, ACTIVE_PROVIDER

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

# ── 媒体池自动导航 ──
def discover_folders():
    """列出 SMB 上的所有项目目录。
    Returns: [(项目名, 完整路径), ...] 或 []"""
    results = []
    project_base = "/Volumes/MYJC/08_AI_Project"
    if not os.path.isdir(project_base):
        return results
    try:
        for name in sorted(os.listdir(project_base)):
            full = os.path.join(project_base, name)
            if os.path.isdir(full) and not name.startswith("."):
                results.append((name, full))
    except Exception:
        pass
    return results

# ── 扫描 ──
_version_checked = False

def scan_io(*_):
    """扫描时间线 IO 范围内标橙色的片段，显示缓存/预估信息。每次点击扫描按钮触发。"""
    global _version_checked
    if not _check_smb(): return
    # 首次扫描时检查 SMB 上的版本是否已更新
    if not _version_checked:
        _version_checked = True
        try:
            import re
            smb_cfg = "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕/config.py"
            if os.path.exists(smb_cfg):
                with open(smb_cfg) as f:
                    m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
                if m and m.group(1) != __version__:
                    warn(f"⚠ 版本已更新（{__version__} → {m.group(1)}），请重启达芬奇以生效")
        except Exception:
            pass
    _log_action("扫描当前选区")
    _st("扫描中...")
    _state["clips_scanned"] = False
    try: itm[LOG_LB].Text = ""
    except Exception: _smb_log("[ui_pipeline] 清空 LOG_LB 失败")
    try:
        _, project, timeline = connect_resolve()
        clips, report = scan_io_clips(timeline, _SELECTED_COLOR)

        if clips is None:
            warn("请设置 IO 入出点"); _st("就绪 — 请设置 IO 入出点"); return
        if not clips:
            info("IO 内无符合筛选的片段"); _st("无有效片段"); return

        _state["clips"] = clips
        _state["scanned_count"] = report.valid

        info("── ① 扫描选区 ──")

        # 获取 IO 范围
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        _state["io_in"] = io_in
        _state["io_out"] = io_out
        _state["timeline_name"] = timeline.GetName()

        # 时间线帧率 → 帧号转分:秒
        fps_str = project.GetSetting("timelineFrameRate")
        fps = float(fps_str) if fps_str else 25.0
        _state["fps"] = fps

        # 逐片段显示 + 缓存检测
        pr = _state["project_root"] or ""
        od = pr and get_output_dir(pr) or ""
        cache_hits = 0
        need_secs = 0
        need_pts = 0
        for c in clips:
            # 帧 → 时控码 时:分:秒:帧
            f = c.start_frame
            total_sec = int(f / fps)
            h, m = divmod(total_sec, 3600)
            m2, s = divmod(m, 60)
            rem_f = int(f - total_sec * fps)
            pos_str = f"{h:02d}:{m2:02d}:{s:02d}:{rem_f:02d}"
            is_cached = od and ledger.find_output(c.file_name)
            if not od:
                label, emoji = "未知", "🟠"  # 无项目路径，无法查缓存
            else:
                label, emoji = ("可复用", "🟢") if is_cached else ("需处理", "🟡")
            info(f"  {emoji} {c.name} | 位置：{pos_str} | 长度：{c.duration:.0f}秒 | {label}")
            if is_cached:
                cache_hits += 1
            else:
                need_secs += c.duration
                need_pts += int(c.duration) + (1 if c.duration % 1 > 0 else 0)  # ceil

        # 总结
        need = len(clips) - cache_hits
        pts = max(1, need_pts)
        yuan = point_to_yuan(pts)
        avg = max(60, min(120, need_secs / max(1, need) * 3)) if need > 0 else 0
        # 批量并行：同时处理，总时间 ≈ 上传+处理+下载，约 2x素材时长 + 60s 基础开销
        total_time = max(1, math.ceil((need_secs * 2.3 + 60) / 60)) if need > 0 else 0
        summary = f"扫描结果：当前选区内，共 {len(clips)} 个符合筛选条件的片段"
        if od:
            if cache_hits > 0:
                summary += f"（其中 {cache_hits} 个可复用）"
            summary += f"  |  {need} 个待处理"
        else:
            summary += "  |  请先选择项目路径以启用缓存复用"
        info(summary)
        ops_logger.cost_estimate(pts, yuan, total_time, need, cache_hits)
        if need > 0 and od:
            info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")

        _state["clips_scanned"] = True
        itm[BTN_START].Enabled = bool(_state["project_root"])
        if _state["project_root"]:
            itm[PROJ_LB].Text = "③ 请点击开始处理"
        _st(f"待处理: {report.valid} 个片段")
        _smb_log(f"扫描 — 项目: {project.GetName()} 时间线: {timeline.GetName()} IO={io_in}→{io_out} 内{report.valid}片段 需处理{need} 约{total_time}分钟 预估¥{yuan}")
        refresh_bal()
    except Exception as e:
        fail(f"扫描失败: {e}")
        _smb_log(f"扫描失败: {e}")

def _refresh_scan_display():
    """选完项目路径后，刷新已扫描片段的缓存状态（🟠→🟢/🟡）"""
    clips = _state.get("clips", [])
    if not clips:
        return
    pr = _state["project_root"]
    od = pr and get_output_dir(pr) or ""
    fps = _state.get("fps", 25.0)
    cache_hits = 0; need_secs = 0; need_pts = 0

    itm[LOG_LB].Text = ""
    info("\n\n── ① 扫描选区 ──")
    for c in clips:
        f = c.start_frame
        total_sec = int(f / fps)
        h, m = divmod(total_sec, 3600)
        m2, s = divmod(m, 60)
        rem_f = int(f - total_sec * fps)
        pos_str = f"{h:02d}:{m2:02d}:{s:02d}:{rem_f:02d}"
        is_cached = od and ledger.find_output(c.file_name)
        label, emoji = ("可复用", "🟢") if is_cached else ("需处理", "🟡")
        info(f"  {emoji} {c.name} | 位置：{pos_str} | 长度：{c.duration:.0f}秒 | {label}")
        if is_cached:
            cache_hits += 1
        else:
            need_secs += c.duration
            need_pts += int(c.duration) + (1 if c.duration % 1 > 0 else 0)

    need = len(clips) - cache_hits
    pts = max(1, need_pts)
    yuan = point_to_yuan(pts)
    summary = f"扫描结果：当前选区内，共 {len(clips)} 个符合筛选条件的片段"
    if cache_hits > 0:
        summary += f"（其中 {cache_hits} 个可复用）"
    summary += f"  |  {need} 个待处理"
    info(summary)
    if need > 0:
        avg = max(60, min(120, need_secs / max(1, need) * 3))
        total_time = int(need * avg / 60)
        info(f"预估: ≤¥{yuan} (≤{pts} 积分) | 约 {total_time} 分钟")
        _st("就绪")


# ── 余额 ──
_cached_balance = 0  # 启动时刷新一次，处理期间复用，避免重复HTTP

def refresh_bal():
    """刷新余额显示（主线程调用，UI 按钮绑定）"""
    global _cached_balance
    pts = query_balance()
    _cached_balance = pts
    if pts > 0:
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _bal(f"{name} | ¥{point_to_yuan(pts):.2f}")
    else:
        _bal("余额: 查询失败")


# ── 阿里云余额 ──
def refresh_oss_bal():
    """查阿里云账户现金余额"""
    try:
        from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
        if not OSS_ACCESS_KEY_ID:
            itm[OSS_LB].Text = "阿里云 | 未配置凭证"
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
            itm[OSS_LB].Text = f"阿里云 | ¥{cash}"
    except Exception as e:
        warn(f"阿里云余额查询异常: {e}")
        itm[OSS_LB].Text = "阿里云 | 查询失败"


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
        fail("请先选择项目路径"); return

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
                info(f"  {clean}")
            # 错误 → SMB + UI
            if any(kw in body for kw in ("失败", "超时", "网络错误")):
                _smb_log(f"[适配器] {body}")
                info(f"  ⚠ {body}")
        wuhenai_set_logger(_adapter_log)

        info("\n\n── ② 缓存复用 ──")
        # 检查是否被停止中断
        if _state["stop"]:
            info("  ⏹ 已停止")
            return
        if prepared.cache_hits:
            info(f"📦 缓存命中 {prepared.cache_hits} 个，直接替换")
            # 缓存省钱 — 用实际片段时长 * 无痕AI按秒计费 (1积分/秒 × ¥0.0091/积分)
            _cache_clips = {c.name: c.duration for c in clips}
            _cache_secs = sum(math.ceil(_cache_clips.get(cn, 0)) for cn in prepared.cache_hit_names)
            cache_saved = _cache_secs * 0.0091
            if cache_saved > 0.01:
                info(f"  💰 省了约 ¥{cache_saved:.2f} ({_cache_secs}秒)")
                _smb_log(f"缓存省钱: ¥{cache_saved:.2f} ({prepared.cache_hits}片段 {_cache_secs}秒)")
            for cn in prepared.cache_hit_names:
                log_ok(f"  {cn}")
        else:
            info("  无可复用缓存")
        if not prepared.tasks:
            if prepared.cache_hits:
                info("\n\n── ⑤ 最终报告 ──")
                log_ok("🎉 全部完成！")
                t_elapsed = int(time.time() - t_start)
                mins, secs = divmod(t_elapsed, 60)
                info(f"  耗时 {mins}分{secs}秒  ·  ¥0  ·  余额 ¥{point_to_yuan(pts_before):.2f}")
                # 缓存省钱统计
                _cache_clips = {c.name: c.duration for c in clips}
                _cache_secs = sum(math.ceil(_cache_clips.get(cn, 0)) for cn in prepared.cache_hit_names)
                if _cache_secs > 0:
                    info(f"  💰 缓存省钱: ¥{_cache_secs * 0.0091:.2f} ({_cache_secs}秒)")
                # macOS 通知
                try:
                    subprocess.run(["osascript", "-e",
                        f'display notification "全部由缓存完成（{prepared.cache_hits}个片段）" with title "AI 去字幕" subtitle "处理完成"'],
                        timeout=5, capture_output=True)
                except Exception:
                    pass
            else:
                log_ok("没有有效任务")
            _set_btn(scan=True, pick=True, stop=False, warn=False)
            itm[COLOR_CB].Enabled = True
            itm[BTN_UNDO].Enabled = True
            itm[BTN_START].Enabled = False
            itm[PROJ_LB].Text = "② 请选择筛选条件并扫描当前选区"
            return

        info("\n\n── ③ AI去字幕中 ──")
        _pg(0.05); _st(f"准备处理 {len(prepared.tasks)} 个片段...")

        # 余额
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _, total_est, _, yuan = estimate_cost(prepared.tasks, MODE)
        _smb_log(f"处理开始 — {project.GetName()}/{timeline.GetName()} 待处理{len(prepared.tasks)}片段 预估¥{yuan}")
        try:
            bal = adapter.get_balance()
            pts = bal.get("balance", 0)
            _bal(f"{name} | ¥{point_to_yuan(pts):.2f}")
            if pts < total_est:
                fail(f"余额不足: {pts} < {total_est}")
                _smb_log(f"余额不足拦截: 余额{pts}pt < 需{total_est}pt")
                return
        except:
            warn("余额查询失败，跳过保护")

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
                # 文件安全预检
                fsize = os.path.getsize(t.path)
                if fsize == 0:
                    warn(f"  ⚠ {t.name}: 文件大小为0，跳过")
                    _smb_log(f"跳过零字节: {t.name}")
                    release_lock(t.name)
                    intercepted += 1; continue
                if fsize > 104857600:
                    warn(f"  ⚠ {t.name}: 文件 {fsize/1048576:.0f}MB，超过100MB限制，跳过")
                    _smb_log(f"超大文件跳过: {t.name} {fsize/1048576:.0f}MB")
                    release_lock(t.name)
                    intercepted += 1; continue
                # 时长校验
                if t.duration <= 0:
                    warn(f"  ⚠ {t.name}: 时长异常 ({t.duration:.1f}秒)，跳过")
                    _smb_log(f"跳过异常时长: {t.name} {t.duration:.1f}s")
                    release_lock(t.name)
                    intercepted += 1; continue
                if t.duration > 30:
                    warn(f"  ⚠ {t.name}: 时长 {t.duration:.0f}秒，超过30秒限制，跳过")
                    _smb_log(f"跳过超长片段: {t.name} {t.duration:.0f}s")
                    release_lock(t.name)
                    intercepted += 1; continue
                locked_tasks.append(t)
            else:
                owner = state_is_locked(t.name) or "其他同事"
                warn(f"  {t.name}: {owner} 正在处理中")
                intercepted += 1
        # 因停止而未处理的
        unprocessed = total - len(locked_tasks) - intercepted
        if not locked_tasks:
            info("\n\n── ⑤ 最终报告 ──")
            msg = f"🎉 处理完成: {prepared.cache_hits} 个处理完成（缓存）"
            if intercepted > 0:
                msg += f"，{intercepted} 个被跳过"
            log_ok(msg)
            return

        # 二次余额校验（防多机器同时提交超支）
        try:
            pts_now = adapter.get_balance().get("balance", 0)
            if pts_now < total_est:
                fail(f"余额不足: {pts_now} < {total_est}（可能有其他机器正在处理）")
                _smb_log(f"二次余额拦截: {pts_now}pt < 需{total_est}pt")
                for t in locked_tasks:
                    release_lock(t.name)
                return
        except:
            pass
        api_tasks = [SubtitleTask(**t.kwargs) for t in locked_tasks]

        t_prep_end = time.time()  # 准备阶段结束

        # 真实进度回调：把 API 返回的进度百分比同步到 UI
        def _on_progress(phase, ratio):
            _st._last_ratio = ratio
            _pg(ratio)
            phase_names = {"upload": "上传中...", "submit": "提交中...",
                           "processing": "AI 处理中...", "download": "下载中..."}
            global _phase_text
            _phase_text = phase_names.get(phase, "处理中...")

        t_batch = time.time()
        # 设置倒计时全局变量（_update_countdown 在稳定版轮询中消费）
        _uw._t_start = t_batch
        _uw._t_estimated = sum(math.ceil(t.duration) for t in api_tasks) * 2.3 + 60  # 实测公式：秒数×2.3+60
        _uw._task_count = len(api_tasks)
        _smb_log(f"预估时间 — 片段总{sum(math.ceil(t.duration) for t in api_tasks)}秒 ({len(api_tasks)}个) 公式={_uw._t_estimated:.0f}秒 (sum×2.3+60)")
        if len(api_tasks) == 1:
            # 单片段：单任务模式（更快，无批量开销）
            info("    AI 处理中...")
            result = adapter.process(api_tasks[0], timeout=600,
                                     cancel_check=lambda: _state["stop"])
            api_results = [result]
        else:
            # 多片段：批量并行模式
            info(f"    AI 处理中...")
            api_results = adapter.process_batch(api_tasks, timeout=600,
                                                cancel_check=lambda: _state["stop"],
                                                progress_callback=_on_progress)
        elapsed = time.time() - t_batch
        info(f"  全部完成，耗时 {elapsed:.0f}秒")
        _pg(0.7); _st(f"下载替换中...")

        for t, r in zip(locked_tasks, api_results):
            if r and r.success:
                release_lock(t.name)
                _smb_log(f"  ✅ {t.name} ({elapsed:.0f}s batch)")
            else:
                msg = getattr(r, 'error_message', '未知错误') if r else '处理失败'
                release_lock(t.name)
                fail(f"  ❌ {t.name}: {msg}")
                _smb_log(f"  ❌ {t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, r, elapsed / len(locked_tasks),
                           t.tl_item, t.tl_color or "", t.mp_color or ""))

        # 下载并替换
        info("\n\n── ④ 替换回时间线 ──")
        _pg(0.9); _st(f"替换中...")
        _state["stop"] = False
        _replaced = 0
        _rpad = len(str(len(results)))
        def _on_replaced(ep, subdir, name):
            nonlocal _replaced
            _replaced += 1
            log_ok(f"[{_replaced:0{_rpad}d}/{len(results)}] 已替换  {name}")
        ok_count, fail_list, output_files = download_and_apply(
            results, od, MODE,
            check_stop=lambda: _state["stop"],
            on_start=lambda name: _st(f"下载中... {name}"),
            on_done=_on_replaced,
            on_fail=lambda name, err: fail(f"  {name}: {err}"),
        )
        # SMB 记录下载失败
        for fe in fail_list:
            _smb_log(f"下载失败: {fe['name']} — {fe['error']}")

        fail_count = len(results) - ok_count
        _pg(1.0); _st(f"完成 {ok_count}/{len(results)}")
        info("\n\n── ⑤ 最终报告 ──")
        t_api_end = time.time()

        # post_check 放这里（用户已看到"完成"，后台静默校验）
        pc = post_check(output_files)
        if pc["fail"] > 0:
            warn(f"校验异常: {pc['ok']}/{pc['total']} 通过, {pc['fail']} 失败")
            for p in pc["problems"]:
                warn(f"  ❌ {p['file']}: {', '.join(p['issues'])}")
            warn("  💡 建议撤销后重新处理")

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
        log_ok(msg)

        t_elapsed = int(time.time() - t_start)
        mins, secs = divmod(t_elapsed, 60)
        # 直接显示耗时和费用（不调API查余额，省2-6秒，用户可秒关）
        info(f"  总耗时 {mins}分{secs}秒  ·  ¥{yuan:.2f}")

        # OSS 流量（内部记录，不展示给用户）
        oss = oss_tracker.snapshot()
        if oss["traffic_gb"] > 0.001:
            _smb_log(f"OSS: {oss['traffic_gb']:.3f}GB ¥{oss['total_cost']:.4f}")

        oss_tracker.reset()
        _smb_log(f"完成 — {ok_count}/{len(results)} 耗时{mins}分{secs}秒 预估¥{yuan:.2f} 余额(处理前)¥{point_to_yuan(pts_before):.2f} 阶段:{t_prep_elapsed}/{t_api_elapsed}/{t_replace_elapsed}s")
        # 用缓存余额更新UI（不调API，不阻塞）
        name = "无痕AI 2.1" if "wuhenai" in ACTIVE_PROVIDER else ACTIVE_PROVIDER
        _bal(f"{name} | ¥{point_to_yuan(pts_before):.2f}")
        ops_logger.session_end(ok_count, len(results) - ok_count, len(results), pts_before, total_est, int(t_elapsed), yuan)

        # 阶段耗时明细（内部记录）
        _smb_log(f"阶段耗时 — 准备:{t_prep_elapsed}s AI:{t_api_elapsed}s 替换:{t_replace_elapsed}s")

        # macOS 系统通知（子线程也可发出，不需要主线程）
        try:
            note = f"{total_done}个片段处理完成（耗时{mins}分{secs}秒）"
            result = subprocess.run(["osascript", "-e",
                f'display notification "{note}" with title "AI 去字幕" subtitle "处理完成"'],
                timeout=5, capture_output=True, text=True)
            if result.returncode != 0:
                _smb_log(f"macOS 通知失败: {result.stderr.strip()}")
        except Exception as e:
            _smb_log(f"macOS 通知异常: {e}")
    except Exception as e:
        fail(f"{e}")
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
        _pg(0.0)
        try: itm[ST_LB].Text = ""
        except Exception: _smb_log("[ui_pipeline] 清空 ST_LB 失败")


# ── 停止 ──
def stop(*_):
    _log_action("停止")
    if _state["processing"]:
        _state["stop"] = True; warn("停止中...")


# ── 撤销替换 ──
def undo(*_):
    """将 IO 内的去字幕片段换回原片"""
    _log_action("撤销替换")
    if _state["processing"]:
        warn("处理中，无法撤销"); return
    try:
        _, project, timeline = connect_resolve()
        io = timeline.GetMarkInOut()
        io_in = io.get("video", {}).get("in", 0) if io else 0
        io_out = io.get("video", {}).get("out", 0) if io else 0
        if io_out <= io_in:
            warn("请设置 IO 入出点"); return

        info("\n\n── 撤销替换 ──")
        found = 0; undone = 0; seen = set()
        for t in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", t) or []:
                if item.GetStart() < io_in or item.GetStart() > io_out:
                    continue
                nm = item.GetName()
                if "_去字幕" not in nm:
                    continue
                if nm in seen:
                    continue
                seen.add(nm)
                found += 1
                mp = item.GetMediaPoolItem()
                if not mp:
                    continue
                file_name = mp.GetClipProperty("File Name") or nm
                # File Name 去 _去字幕 后缀 → 状态键
                key = file_name.replace("_去字幕.mp4", ".mp4") if "_去字幕" in file_name else file_name
                original = ledger.get_original_path(key)
                if original and os.path.exists(original):
                    mp.ReplaceClipPreserveSubClip(original)
                    log_ok(f"  ↩ {nm}")
                    undone += 1
                    _smb_log(f"撤销: {nm} → 原片")
        if found == 0:
            info("  IO 内无去字幕片段")
        else:
            info(f"  撤销 {undone}/{found} 个片段")
    except Exception as e:
        fail(f"撤销失败: {e}")

