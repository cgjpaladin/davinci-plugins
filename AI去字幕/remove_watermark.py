#!/usr/bin/env python3
"""
remove_watermark.py — 达芬奇 AI 去字幕插件

双入口：
  人类入口: 达芬奇 Workspace → Scripts → remove_watermark
  AI入口:   python3 remove_watermark.py --mode pro_box --dry-run --report-json report.json
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

# 重置 OSS 用量追踪
from pricing import oss_tracker
oss_tracker.reset()

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if _RESOLVE_MODULES not in sys.path:
    sys.path.append(_RESOLVE_MODULES)

from config import (
    API_TIMEOUT, DEFAULT_MODE, MODE_LABELS,
    DEBUG, SCAN_ONLY, __version__,
    get_project_root, get_output_dir, get_log_dir, PLUGIN_DIR,
)
from adapters import WatermarkTask
from watermark_state import get_clip_status, init as state_init
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
                 batch: bool = False) -> dict:
    """执行完整去字幕流程 (无痕AI 2.1, sel_area ¥0.36/分钟)。"""
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
    project_root = get_project_root(clips[0].path if clips else None)
    if not DEBUG and not project_root:
        report["error"] = "无法识别项目目录"
        _write_report(report, report_json)
        return report

    output_dir = get_output_dir(project_root)
    report["project_root"] = project_root or "(调试模式)"
    report["output_dir"] = output_dir
    info(f"项目路径: {report['project_root']}")
    info(f"输出目录: {output_dir}")

    state_init(project_root)
    ops_logger.init(get_log_dir(project_root))
    ops_logger.session_start(report["project"], report["timeline"], mode, 0)
    ops_logger.clip_scan(len(clips), 0, [c.name for c in clips])

    # ── 4. 任务准备 ──
    prepared = prepare_tasks(clips, mode, output_dir, force=force)
    report["cache_hits"] = prepared.cache_hits
    report["task_count"] = len(prepared.tasks)

    if prepared.cache_hits:
        step(f"📦 缓存命中 {prepared.cache_hits} 个，剩余 {len(prepared.tasks)} 个需 API")
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

    if batch:
        step(f"🚀 批量处理 {len(prepared.tasks)} 个片段 | 并行模式")
        api_tasks = [WatermarkTask(**t.kwargs) for t in prepared.tasks]
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
        stop_file = os.path.join(PLUGIN_DIR, ".stop")
        local_stop = os.path.join("/tmp", f"ai_subtitle.stop.{os.uname().nodename}")

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
    # OSS 费用统计
    from pricing import oss_tracker
    oss_cost = oss_tracker.snapshot()
    report["oss_cost"] = oss_cost
    if oss_cost["traffic_gb"] > 0:
        info(f"📦 OSS 流量: {oss_cost['traffic_gb']:.2f}GB, 费用: ¥{oss_cost['total_cost']:.2f}")
    oss_tracker.reset()

    ok(f"{success_count}/{len(results)} 个片段完成 → {output_dir}")
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
    # 达芬奇菜单入口（无参数）→ 走环境变量默认
    if len(sys.argv) == 1 and sys.argv[0].endswith(".py"):
        run_pipeline(mode=DEFAULT_MODE, scan_only=SCAN_ONLY)
        return

    # 命令行入口（AI 开发者）
    parser = argparse.ArgumentParser(
        description=f"AI 去字幕 v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python3 remove_watermark.py --dry-run --report-json report.json\n"
               "  python3 remove_watermark.py --mode basic --force"
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
    args = parser.parse_args()

    try:
        run_pipeline(
            mode=args.mode,
            dry_run=args.dry_run,
            force=args.force,
            scan_only=args.scan_only,
            report_json=args.report_json,
            batch=args.batch,
        )
    except Exception as e:
        fail(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
