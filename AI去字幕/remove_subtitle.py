#!/usr/bin/env python3
"""
remove_subtitle.py — 达芬奇 AI 去字幕插件

双入口：
  人类入口: 达芬奇 Workspace → Scripts → remove_subtitle
  AI入口:   python3 remove_subtitle.py --mode pro_box --dry-run --report-json report.json
"""
import argparse
import json
import os
import re
import sys
import time
import traceback

# 路径初始化
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# OSS 用量追踪 (oss_tracker.reset() 已移至 run_pipeline 开头)
from pricing import oss_tracker
from ops_logger import _smb_log

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if _RESOLVE_MODULES not in sys.path:
    sys.path.append(_RESOLVE_MODULES)

from config import (
    API_TIMEOUT, DEFAULT_MODE, MODE_LABELS,
    DEBUG, SCAN_ONLY, __version__,
    get_output_dir, get_log_dir, PLUGIN_DIR,
)
from adapters import SubtitleTask
from subtitle_state import get_clip_status, init as state_init
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    build_output_path, estimate_cost, query_balance, get_io,
    post_check, CLIP_COLOR as _CLIP_COLOR,
    create_wuhenai_adapter, process_single_clip, download_and_apply,
)
from logger import title, step, ok, warn, fail, info, set_logger, PrintLogger
import ops_logger


# ═══════════════════════════════════════════
# Pipeline（可脚本化调用）
# ═══════════════════════════════════════════

def run_pipeline(mode: str = None, dry_run: bool = False, force: bool = False,
                 scan_only: bool = False, report_json: str = "",
                 batch: bool = False, project_root: str = "") -> dict:
    """执行完整去字幕流程 (无痕AI 2.1, sel_area ¥0.36/分钟)。"""
    oss_tracker.reset()

    # ── 0. 环境自检 ──
    from config import WUHENAI_V2_API_KEY, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET

    checks = [
        ("SMB 挂载", os.path.exists("/Volumes/MYJC")),
        ("API Key", bool(WUHENAI_V2_API_KEY)),
        ("OSS 凭证", bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET)),
        ("达芬奇运行", os.path.exists("/Applications/DaVinci Resolve")),
    ]
    for name, ok_flag in checks:
        if not ok_flag:
            fail(f"环境自检失败: {name} 不可用")
    if not all(f for _, f in checks):
        step("💡 请确保: SMB 已挂载 / .env 已配置 / 达芬奇已启动")
        report = {"error": "环境自检失败", "checks": {n: f for n, f in checks}}
        _write_report(report, report_json)
        return report
    step(f"✅ 环境自检通过 (SMB/API/OSS/DVR)")

    mode = mode or DEFAULT_MODE
    report = {
        "version": __version__,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "adapter": "wuhenai",
        "dry_run": dry_run,
        "force": force,
        "scan_only": scan_only,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # ── OSS 预检 ──
    if not dry_run and not scan_only:
        try:
            probe = create_wuhenai_adapter()
            if not probe.check_oss():
                fail("无痕AI OSS 不可用，请检查阿里云账号状态")
                report["error"] = "OSS不可用"
                _write_report(report, report_json)
                return report
        except Exception as e:
            fail(f"OSS 预检失败: {e}")
            report["error"] = str(e)
            _write_report(report, report_json)
            return report

    # ── 1. 连接 ──
    try:
        resolve, project, timeline = connect_resolve()
        report["resolve"] = resolve.GetVersionString()
        report["project"] = project.GetName()
        report["timeline"] = timeline.GetName()
    except Exception as e:
        report["error"] = str(e)
        _write_report(report, report_json)
        return report

    title(f"AI 去字幕 v{__version__}")
    info(f"Resolve: {report['resolve']}")
    info(f"项目: {report['project']}")
    info(f"时间线: {report['timeline']}")

    # ── 2. 扫描 IO ──
    clips, scan_report = scan_io_clips(timeline, _CLIP_COLOR)
    if clips is None:
        fail("IO 未设置")
        report["error"] = "IO 未设置"
        _write_report(report, report_json)
        return report

    io_in, io_out = get_io(timeline)
    report["io"] = {"in": io_in, "out": io_out}
    report["scan"] = {
        "total": scan_report.total,
        "valid": scan_report.valid,
        "skipped": scan_report.skipped,
    }

    info(f"🎬 IO({io_in}→{io_out}): {scan_report.valid}/{scan_report.total} 符合筛选")
    if not clips:
        ok("没有需要处理的片段")
        _write_report(report, report_json)
        return report

    step(f"共 {len(clips)} 个片段", "📋")

    # ── 3. 项目路径 ──
    if not project_root or not os.path.isdir(project_root):
        report["error"] = "请通过 --project-root 指定项目根目录"
        _write_report(report, report_json)
        return report

    output_dir = get_output_dir(project_root)
    report["project_root"] = project_root
    report["output_dir"] = output_dir
    info(f"项目路径: {report['project_root']}")
    info(f"输出目录: {output_dir}")

    state_init(project_root)
    import ledger; ledger.init(project_root)
    ops_logger.init(get_log_dir(project_root))
    ops_logger.session_start(report["project"], report["timeline"], mode, 0)
    ops_logger.clip_scan(len(clips), 0, [c.name for c in clips])

    # ── 4. 任务准备 ──
    prepared = prepare_tasks(clips, mode, output_dir, force=force)
    report["cache_hits"] = prepared.cache_hits
    report["task_count"] = len(prepared.tasks)

    if prepared.cache_hits:
        step(f"📦 缓存命中 {prepared.cache_hits} 个，剩余 {len(prepared.tasks)} 个需 API")
        # 缓存省钱 — 用实际片段时长 (无痕AI 按秒计费 1积分/秒 × ¥0.0091)
        import math as _m
        _cc = {c.name: c.duration for c in clips}
        _cs = sum(_m.ceil(_cc.get(cn, 0)) for cn in prepared.cache_hit_names)
        if _cs > 0:
            info(f"  💰 缓存省钱: ¥{_cs * 0.0091:.2f} ({_cs}秒)")
            report["cache_saved_secs"] = _cs
            report["cache_saved_yuan"] = round(_cs * 0.0091, 2)
    if not prepared.tasks:
        ok(f"全部由缓存完成！({prepared.cache_hits}个)")
        ops_logger.session_end(prepared.cache_hits, 0, prepared.cache_hits)
        report["completed"] = prepared.cache_hits
        _write_report(report, report_json)
        return report

    # ── 5. 余额 ──
    total_units, total_est, unit_cost, yuan = estimate_cost(prepared.tasks, mode)
    adapter = create_wuhenai_adapter()
    try:
        bal = adapter.get_balance()
        pts = bal.get("balance", 0)
    except Exception:
        pts = 0

    report["cost"] = {"seconds": total_units, "points": total_est, "unit_cost": unit_cost,
                      "yuan": yuan, "balance": round(pts, 1)}

    step(f"💰 {report['mode_label']} — {total_est}积分(¥{report['cost']['yuan']}) | 无痕AI")
    if pts > 0:
        info(f"余额: {pts:.1f} 积分")
        if pts < total_est:
            fail(f"余额不足: {pts:.1f} < {total_est}")
            ops_logger.balance_check(pts, total_est, "blocked")
            report["error"] = "余额不足"
            _write_report(report, report_json)
            return report
        ops_logger.balance_check(pts, total_est, "proceed")
    else:
        warn("余额查询失败，跳过保护")

    # ── 干跑 / 仅扫描 → 到此为止 ──
    # 时长过滤（>30s 提示并跳过）
    valid_tasks = []
    for t in prepared.tasks:
        if t.duration > 30:
            warn(f"  ⚠ {t.name}: 时长 {t.duration:.0f}秒，超过30秒限制，跳过")
            continue
        valid_tasks.append(t)
    prepared.tasks[:] = valid_tasks  # 原地替换

    if dry_run or scan_only:
        tag = "🔍 仅扫描" if scan_only else "🔍 Dry-run"
        step(f"{tag} — 共 {len(prepared.tasks)} 个片段，未调 API")
        for i, t in enumerate(prepared.tasks, 1):
            info(f"  {i}. {t.name} ({t.path})")
        ops_logger.session_end(0, 0, len(prepared.tasks))
        report["dry_run_completed"] = True
        _write_report(report, report_json)
        return report

    # ── 6. 处理（串行或批量）──
    adapter = create_wuhenai_adapter()
    results = []
    stop_file = os.path.join(PLUGIN_DIR, ".stop")
    local_stop = os.path.join("/tmp", f"ai_subtitle.stop.{os.uname().nodename}")

    t_phase_prep = time.time()  # 准备阶段结束（缓存+余额+校验完成）

    if batch:
        step(f"🚀 批量处理 {len(prepared.tasks)} 个片段 | 并行模式")

        # 二次余额校验（防多机器同时提交超支）
        try:
            pts_now = adapter.get_balance().get("balance", 0)
            if pts_now < total_est:
                fail(f"余额不足: {pts_now} < 需{total_est}（可能有其他机器正在处理）")
                return report
        except Exception:
            _smb_log("[remove_subtitle] 额度保护查询失败，跳过")

        api_tasks = [SubtitleTask(**t.kwargs) for t in prepared.tasks]
        t0 = time.time()
        api_results = adapter.process_batch(api_tasks, timeout=API_TIMEOUT)
        elapsed = time.time() - t0

        for i, (t, r) in enumerate(zip(prepared.tasks, api_results)):
            ops_logger.task_submit(t.name, mode, t.duration, 0)
            ops_logger.task_result(t.name, str(getattr(r, 'task_id', '')), elapsed / len(prepared.tasks), r.success)
            if r and r.success:
                ok(f"{t.name} | {getattr(r, 'task_id', '')}")
            else:
                msg = getattr(r, 'error_message', '未知错误') if r else '处理失败'
                fail(f"{t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, r, elapsed / len(prepared.tasks)))
    else:
        step(f"🚀 处理 {len(prepared.tasks)} 个片段 | 串行")

        def _check_stop():
            return os.path.exists(stop_file) or os.path.exists(local_stop)

        for idx, t in enumerate(prepared.tasks, 1):
            if _check_stop():
                for sf in (stop_file, local_stop):
                    if os.path.exists(sf): os.remove(sf)
                warn(f"⏹ 停止，跳过剩余 {len(prepared.tasks)-idx+1} 个片段")
                break
            # 每处理前检查达芬奇是否还活着
            try:
                if not resolve.GetProjectManager().GetCurrentProject():
                    fail("达芬奇已断开，停止处理")
                    break
            except:
                fail("达芬奇已断开，停止处理")
                break

            info(f"[{idx}] {t.name} → 上传中...")
            result, elapsed = process_single_clip(t, adapter, mode)
            if result.success:
                ok(f"{t.name} ({elapsed:.0f}s | {getattr(result, 'task_id', '')})")
            else:
                msg = getattr(result, 'error_message', '未知错误')
                fail(f"{t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, result, elapsed))

    # ── 7. 下载 + ReplaceClip ──
    t_phase_api = time.time()  # API 阶段结束, 下载阶段开始
    step(f"📥 下载 {len(results)} 个结果")
    success_count, fail_list, output_files = download_and_apply(
        results, output_dir, mode,
        check_stop=lambda: os.path.exists(stop_file) or os.path.exists(local_stop),
        on_done=lambda ep, subdir, name: info(f"→ {ep}/{subdir}/{name}"),
        on_fail=lambda name, err: fail(f"{name}: {err}"),
    )

    # ── 8. Post-check ──
    step(f"🔍 校验输出")
    pc = post_check(output_files)
    if pc["fail"] == 0 and pc["total"] > 0:
        ok(f"全部 {pc['total']} 个文件校验通过")
    elif pc["fail"] > 0:
        warn(f"{pc['ok']}/{pc['total']} 通过, {pc['fail']} 个异常")
        for p in pc["problems"]:
            fail(f"  {p['file']}: {', '.join(p['issues'])}")

    report["results"] = {
        "total": len(results), "success": success_count,
        "failed": len(results) - success_count,
        "fail_details": fail_list,
        "output_files": output_files,
    }
    # 阶段耗时
    t_done = time.time()
    api_secs = round(t_phase_api - t_phase_prep, 1)
    dl_secs = round(t_done - t_phase_api, 1)
    report["phase_timing"] = {
        "api_secs": api_secs,
        "download_secs": dl_secs,
        "total_processing_secs": round(t_done - t_phase_prep, 1),
    }
    # Console 输出阶段耗时
    step(f"── 阶段耗时 ──")
    info(f"  AI处理 (上传+API): {api_secs:.0f}秒")
    info(f"  下载替换: {dl_secs:.0f}秒")
    # 超时检测（超过预估 2 倍报警）
    need_secs = sum(t.duration for t in prepared.tasks)
    expected = max(60, need_secs * 2 + 60)
    total_proc = t_done - t_phase_prep
    if total_proc > expected * 2:
        warn(f"⚠ 处理超时: 实际 {total_proc:.0f}秒 > 预估 {expected:.0f}秒×2，可能网络波动")
    # OSS 费用统计
    from pricing import oss_tracker
    oss_cost = oss_tracker.snapshot()
    report["oss_cost"] = oss_cost
    if oss_cost["traffic_gb"] > 0:
        info(f"📦 OSS 流量: {oss_cost['traffic_gb']:.2f}GB, 费用: ¥{oss_cost['total_cost']:.2f}")
    oss_tracker.reset()

    ok(f"{success_count}/{len(results)} 个片段完成 → {output_dir}")
    total_elapsed = int(t_done - t_phase_prep)
    mins, secs = divmod(total_elapsed, 60)
    info(f"总耗时 {mins}分{secs}秒")
    ops_logger.session_end(success_count, len(results) - success_count, len(results))
    _write_report(report, report_json)
    return report


def _write_report(report: dict, path: str):
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        info(f"📋 报告已输出: {path}")
    except Exception as e:
        warn(f"报告写入失败: {e}")


# ═══════════════════════════════════════════
# 入口：达芬奇菜单 或 命令行
# ═══════════════════════════════════════════

def main():
    """双入口：无参数=达芬奇菜单入口（引导用UI）；有参数=CLI 开发者模式。"""
    # 达芬奇菜单入口（无参数）→ 使用 UI，走 ui_external.py
    if len(sys.argv) == 1 and sys.argv[0].endswith(".py"):
        info("请通过 AI去字幕 UI 使用，或传 --project-root 参数")
        return

    # 命令行入口（AI 开发者）
    parser = argparse.ArgumentParser(
        description=f"AI 去字幕 v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python3 remove_subtitle.py --dry-run --report-json report.json\n"
               "  python3 remove_subtitle.py --mode basic --force"
    )
    parser.add_argument("--mode", choices=["basic", "pro_box"], default=DEFAULT_MODE,
                        help=f"处理模式 (默认: {DEFAULT_MODE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="完整诊断但不调 API，不花钱")
    parser.add_argument("--scan-only", action="store_true",
                        help="仅扫描 IO，不调 API")
    parser.add_argument("--force", action="store_true",
                        help="跳过可复用片段，强制重新处理")
    parser.add_argument("--report-json", default="",
                        help="结构化报告输出路径")
    parser.add_argument("--batch", action="store_true",
                        help="批量并行处理（上传全部→一次提交→一起等）")
    parser.add_argument("--check", action="store_true",
                        help="仅环境自检 (SMB/API/OSS/DVR)，不处理")
    parser.add_argument("--project-root", default="",
                        help="项目根目录（含04_素材的文件夹），AI 传入，不推断")
    args = parser.parse_args()

    if args.check:
        from config import WUHENAI_V2_API_KEY, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
        checks = {
            "SMB 挂载": os.path.exists("/Volumes/MYJC"),
            "API Key (无痕AI 2.1)": bool(WUHENAI_V2_API_KEY),
            "OSS 凭证 (阿里云)": bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET),
            "达芬奇运行": os.path.exists("/Applications/DaVinci Resolve"),
        }
        title("🔍 环境自检")
        all_ok = True
        for name, ok_flag in checks.items():
            (ok if ok_flag else fail)(f"{name}: {'✅' if ok_flag else '❌'}")
            if not ok_flag:
                all_ok = False
        if all_ok:
            ok("全部通过 ✅")
        else:
            warn("存在问题，请先修复")
        return

    try:
        run_pipeline(
            mode=args.mode,
            dry_run=args.dry_run,
            force=args.force,
            scan_only=args.scan_only,
            report_json=args.report_json,
            batch=args.batch,
            project_root=args.project_root,
        )
    except Exception as e:
        fail(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
