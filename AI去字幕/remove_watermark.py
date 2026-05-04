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
import urllib.request
from copy import deepcopy

# 路径初始化
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if _RESOLVE_MODULES not in sys.path:
    sys.path.append(_RESOLVE_MODULES)

from config import (
    ADAPTER_CONFIGS, API_TIMEOUT, DEFAULT_MODE, MODE_LABELS,
    COST_PER_MODE, DEBUG, SCAN_ONLY, __version__,
    get_project_root, get_output_dir, get_log_dir, PLUGIN_DIR,
)
from adapters import WatermarkTask, WatermarkResult
from adapters.ghostcut import GhostCutAdapter
from adapters.wuhenai_v2 import WuhenAIV2Adapter
from watermark_state import mark_processed, get_clip_status, release_lock, acquire_lock, init as state_init
from core import (
    connect_resolve, scan_io_clips, prepare_tasks,
    build_output_path, estimate_cost, query_balance, get_io,
    post_check, CLIP_COLOR as _CLIP_COLOR,
)
from logger import title, step, ok, warn, fail, info, set_logger, PrintLogger
import ops_logger


# ═══════════════════════════════════════════
# Pipeline（可脚本化调用）
# ═══════════════════════════════════════════

def run_pipeline(mode: str = None, dry_run: bool = False, force: bool = False,
                 scan_only: bool = False, report_json: str = "",
                 batch: bool = False, adapter_name: str = "wuhenai") -> dict:
    """执行完整去字幕流程，返回结构化报告。

    Args:
        adapter_name: "wuhenai" (默认) | "ghostcut"
    """
    mode = mode or DEFAULT_MODE
    report = {
        "version": __version__,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "adapter": adapter_name,
        "dry_run": dry_run,
        "force": force,
        "scan_only": scan_only,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # ── 适配器选择 + OSS 预检（无痕AI）──
    if adapter_name == "wuhenai":
        adapter_cfg = deepcopy(ADAPTER_CONFIGS["wuhenai_v2"])
        adapter_cfg["model"] = "video_removal_std"
        adapter_cfg["method"] = "sel_area"
        AdapterClass = WuhenAIV2Adapter

        # OSS 预检（余额预检放在后面）
        try:
            probe = AdapterClass(adapter_cfg)
            if not dry_run and not scan_only and not probe.check_oss():
                warn("无痕AI OSS 不可用，自动降级为 GhostCut")
                adapter_name = "ghostcut"
            if adapter_name == "ghostcut":
                adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
                adapter_cfg["model"] = mode
                AdapterClass = GhostCutAdapter
                report["adapter"] = "ghostcut"
                report["adapter_fallback"] = True
                report["adapter_fallback_reason"] = "OSS不可用"
        except Exception:
            pass  # 预检失败不阻断，继续尝试

    if adapter_name == "ghostcut":
        adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
        adapter_cfg["model"] = mode
        AdapterClass = GhostCutAdapter

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
    prepared = prepare_tasks(clips, timeline, mode, output_dir, project_root, force=force)
    report["cache_hits"] = prepared.cache_hits
    report["pro_upgrades"] = prepared.pro_upgrades
    report["task_count"] = len(prepared.tasks)

    if prepared.pro_upgrades:
        info(f"↻ {prepared.pro_upgrades} 个预览版将升级")
    if prepared.cache_hits:
        step(f"📦 缓存命中 {prepared.cache_hits} 个，剩余 {len(prepared.tasks)} 个需 API")
    if not prepared.tasks:
        ok(f"全部由缓存完成！({prepared.cache_hits}个)")
        ops_logger.session_end(prepared.cache_hits, 0, prepared.cache_hits)
        report["completed"] = prepared.cache_hits
        _write_report(report, report_json)
        return report

    # ── 5. 余额 ──
    total_units, total_est, unit_cost = estimate_cost(prepared.tasks, mode)
    try:
        adapter = AdapterClass(adapter_cfg)
        bal = adapter.get_balance()
        if adapter_name == "wuhenai":
            pts = bal.get("balance", 0)
            cost_info = "积分"
        else:
            now_ms = time.time() * 1000
            pts = sum(a["pointBalance"] for a in bal.get("pointAssets", [])
                      if a["pointBalance"] > 0 and a.get("expireTime", now_ms+1) > now_ms)
            cost_info = "点"
    except Exception:
        pts = 0; cost_info = "点"

    report["cost"] = {"units": total_units, "points": total_est, "unit_cost": unit_cost,
                      "yuan": round(total_est * 0.19, 2), "balance": round(pts, 1)}

    step(f"💰 {report['mode_label']} — {total_est}{cost_info}(¥{report['cost']['yuan']}) | {adapter_name}")
    if pts > 0:
        info(f"余额: {pts:.1f} {cost_info}")
        if pts < total_est:
            if adapter_name == "wuhenai":
                # 无痕AI 余额不足 → 试试降级 GhostCut
                warn(f"无痕AI 余额不足 ({pts:.1f} < {total_est})，自动降级为 GhostCut")
                adapter_name = "ghostcut"
                adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
                adapter_cfg["model"] = mode
                AdapterClass = GhostCutAdapter
                cost_info = "点"
                report["adapter"] = "ghostcut"
                report["adapter_fallback"] = True
                report["adapter_fallback_reason"] = "余额不足"
                # 重新查 GhostCut 余额
                try:
                    adapter2 = GhostCutAdapter(adapter_cfg)
                    bal2 = adapter2.get_balance()
                    now_ms = time.time() * 1000
                    pts = sum(a["pointBalance"] for a in bal2.get("pointAssets", [])
                              if a["pointBalance"] > 0 and a.get("expireTime", now_ms+1) > now_ms)
                    report["cost"]["balance"] = round(pts, 1)
                    info(f"GhostCut 余额: {pts:.1f} 点")
                    if pts < total_est:
                        fail(f"GhostCut 余额也不足: {pts:.1f} < {total_est}")
                        ops_logger.balance_check(pts, total_est, "blocked")
                        report["error"] = "余额不足"
                        _write_report(report, report_json)
                        return report
                    ops_logger.balance_check(pts, total_est, "proceed")
                except Exception:
                    warn("GhostCut 余额查询失败，跳过保护")
            else:
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
    adapter = AdapterClass(adapter_cfg)
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

        for idx, t in enumerate(prepared.tasks, 1):
            if os.path.exists(stop_file) or os.path.exists(local_stop):
                for sf in (stop_file, local_stop):
                    if os.path.exists(sf): os.remove(sf)
                warn(f"⏹ 停止，跳过剩余 {len(prepared.tasks)-idx+1} 个片段")
                break

            if not acquire_lock(t.name):
                warn(f"[{idx}] {t.name}: 被锁定，跳过")
                results.append((t.mp_item, t.name, t.path,
                                WatermarkResult(success=False, task_id="", error_message="锁定"), 0))
                continue

            result = None; elapsed = 0
            for attempt in range(3):
                try:
                    if attempt > 0:
                        info(f"[{idx}] {t.name} → 重试 {attempt}/2...")
                    else:
                        info(f"[{idx}] {t.name} → 上传中...")
                    ops_logger.task_submit(t.name, mode, t.duration, attempt)
                    t0 = time.time()
                    result = adapter.process(WatermarkTask(**t.kwargs), timeout=API_TIMEOUT)
                    elapsed = time.time() - t0
                    ops_logger.task_result(t.name, str(getattr(result, 'task_id', '')), elapsed, result.success)
                    if not result.success: release_lock(t.name)
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = 3 * (attempt + 1)
                        ops_logger.task_error(t.name, str(e)[:200], attempt)
                        warn(f"[{idx}] {t.name}: {e}，{wait}s后重试...")
                        time.sleep(wait)
                    else:
                        err_msg = str(e)[:100]
                        ops_logger.task_error(t.name, err_msg, attempt)
                        fail(f"[{idx}] {t.name}: 重试2次均失败: {err_msg}")
                        release_lock(t.name)
                        result = WatermarkResult(success=False, task_id="",
                                                error_message=f"重试2次后失败: {err_msg}")

            if result and result.success:
                ok(f"{t.name} ({elapsed:.0f}s | {getattr(result, 'task_id', '')})")
            else:
                msg = getattr(result, 'error_message', '未知错误') if result else '处理失败'
                fail(f"{t.name}: {msg}")
            results.append((t.mp_item, t.name, t.path, result or WatermarkResult(success=False), elapsed))

    # ── 7. 下载 + ReplaceClip ──
    step(f"📥 下载 {len(results)} 个结果")
    success_count = 0; output_files = []; fail_list = []

    for mp_item, name, path, result, elapsed in results:
        if not result or not result.success:
            fail_list.append({"name": name, "error": getattr(result, 'error_message', '') if result else ''})
            continue

        file_name = os.path.basename(path)
        dl, ep, subdir, clean_name = build_output_path(file_name, output_dir, mode)

        urllib.request.urlretrieve(result.output_path, dl)
        info(f"→ {ep}/{subdir}/{clean_name} ({os.path.getsize(dl)/1024/1024:.1f}MB)")

        if mp_item.ReplaceClipPreserveSubClip(dl):
            fn = mp_item.GetClipProperty("File Name") or name
            mark_processed(fn, dl, mode)
            ok(f"{clean_name} — ReplaceClip 完成")
            success_count += 1
            output_files.append(dl)
        else:
            fail_list.append({"name": name, "error": "ReplaceClip 失败"})
            fail(f"{clean_name} ReplaceClip 失败")
        release_lock(name)

    # ── 8. Post-check ──
    step(f"🔍 校验输出")
    post_check(output_files)

    report["results"] = {
        "total": len(results), "success": success_count,
        "failed": len(results) - success_count,
        "fail_details": fail_list,
        "output_files": output_files,
    }
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
                        help="跳过缓存复用，强制重新处理")
    parser.add_argument("--report-json", default="",
                        help="结构化报告输出路径")
    parser.add_argument("--batch", action="store_true",
                        help="批量并行处理（上传全部→一次提交→一起等）")
    parser.add_argument("--adapter", choices=["wuhenai", "ghostcut"], default="wuhenai",
                        help="API 适配器 (默认: wuhenai，OSS不通自动降级ghostcut)")
    args = parser.parse_args()

    try:
        run_pipeline(
            mode=args.mode,
            dry_run=args.dry_run,
            force=args.force,
            scan_only=args.scan_only,
            report_json=args.report_json,
            batch=args.batch,
            adapter_name=args.adapter,
        )
    except Exception as e:
        fail(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
