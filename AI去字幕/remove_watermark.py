#!/usr/bin/env python3
"""
remove_watermark.py — 达芬奇 AI 去字幕插件

用法：
  1. 在达芬奇 Edit 页面用 IO 区间选中要去字幕的片段（变橘黄色）
  2. 运行此脚本（Workspace → Scripts → remove_watermark）
  3. 脚本自动处理 IO 内所有片段 → 下载到 SMB 02_结果 → 导入媒体池

架构：
  - 适配器模式，换 API 只改配置
  - 影视工业级：不导出不渲染，直接用源文件
"""

import os
import re
import math
import subprocess
import sys
import time
import traceback
from copy import deepcopy

# 自动识别插件所在目录（支持 SMB 共享部署）
# 注意：达芬奇运行脚本时，__file__ 指向启动器文件，不是这里
# 我们需要找到 config.py 所在目录（即整个插件的根目录）
import os as _os
_plugin_root = _os.path.dirname(_os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# 添加达芬奇 API 路径
RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if RESOLVE_MODULES not in sys.path:
    sys.path.append(RESOLVE_MODULES)

import DaVinciResolveScript as dvr_script

from config import ADAPTER_CONFIGS, API_TIMEOUT, DEFAULT_MODE, MAX_SOURCE_DURATION, CLIP_COLOR, DEFAULT_MASK_REGION, COST_PER_MODE, DEBUG, get_project_root, get_output_dir, get_log_dir, MODE_LABELS, MODE_FILE_TAGS, PLUGIN_DIR, SCAN_ONLY, __version__
from adapters import WatermarkTask, WatermarkResult
from adapters.ghostcut import GhostCutAdapter
from watermark_state import record_original, need_restore, mark_processed, get_clip_status, init as state_init, acquire_lock, release_lock
import ops_logger


# ============================================================
# 工具函数
# ============================================================

def get_resolve():
    resolve = dvr_script.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("请先启动 DaVinci Resolve Studio")
    return resolve


def get_video_duration(file_path):
    """用 ffprobe 快速获取视频时长（秒），兼容达芬奇 PATH 环境"""
    for ff_cmd in ("ffprobe", "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):
        try:
            result = subprocess.run(
                [ff_cmd, "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", file_path],
                capture_output=True, text=True, timeout=10
            )
            return float(result.stdout.strip())
        except Exception:
            continue
    return 0


def get_source_items(timeline):
    """
    获取 IO 区间内所有片段的 TimelineItem（去重）。
    直接拿对象，不搜媒体池——O(1) 不是 O(n)。
    返回 [(timeline_item, name, start_frame), ...]
    """
    io = timeline.GetMarkInOut()
    io_in = io.get("video", {}).get("in", 0)
    io_out = io.get("video", {}).get("out", 0)
    
    if io_out <= io_in:
        raise RuntimeError("请先在时间线上设置 IO 区间（选中要去字幕的片段）")
    
    print(f"[IO] 帧 {io_in} → {io_out}")
    
    results = []
    seen = {}  # name → (item, track#) — 同片段多轨时保留最佳
    stats = {"total": 0, "skipped_nomp": 0, "skipped_nopath": 0}
    
    for t in range(1, timeline.GetTrackCount("video") + 1):
        items = timeline.GetItemListInTrack("video", t)
        if not items:
            continue
        for item in items:
            s, e = item.GetStart(), item.GetEnd()
            if s < io_out and e > io_in:
                name = item.GetName()
                # 保留颜色匹配的版本；如果已有匹配的则跳过
                if name in seen:
                    existing_item, _ = seen[name]
                    # 如果已有版本已匹配颜色，不替换
                    if CLIP_COLOR and existing_item.GetClipColor() == CLIP_COLOR:
                        continue
                seen[name] = (item, t)
    
    for name, (item, t) in seen.items():
        stats["total"] += 1
        color = item.GetClipColor()
        
        # 颜色过滤 — 所有模式只处理匹配颜色的片段
        if CLIP_COLOR and color != CLIP_COLOR:
            continue
        
        mp = item.GetMediaPoolItem()
        if not mp:
            stats["skipped_nomp"] += 1
            continue
        
        path = mp.GetClipProperty("File Path")
        if not path or not os.path.exists(path):
            stats["skipped_nopath"] += 1
            continue
        
        results.append((mp, name, path))
    
    # 打印报告
    color_tag = CLIP_COLOR or "全部"
    skipped_total = sum(stats[k] for k in stats if k.startswith("skipped_"))
    ok = len(results)
    print(f"\n  🎬 检测到 {stats['total']} 个片段，其中 {ok} 个符合筛选")
    
    if not results and DEFAULT_MODE not in ("pro", "pro_box"):
        raise RuntimeError(f"IO 区间内没有{color_tag}色视频片段（共扫描 {stats['total']} 个片段，跳过 {skipped_total} 个）")
    return results


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print(f"  AI 去字幕 v{__version__}")
    print("=" * 60)
    
    try:
        resolve = get_resolve()
        print(f"[Resolve] {resolve.GetVersionString()}")
        
        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            raise RuntimeError("请先打开一个项目")
        print(f"[项目] {project.GetName()}")
        
        timeline = project.GetCurrentTimeline()
        if not timeline:
            raise RuntimeError("请先打开一条时间线")
        print(f"[时间线] {timeline.GetName()}")
        io = timeline.GetMarkInOut()
        
        # 1. IO 区间内所有片段
        items = get_source_items(timeline)
        print(f"\n[任务] 共 {len(items)} 个片段\n")
        
        if not items:
            print("[完成] 没有需要处理的片段")
            ops_logger.session_end(0, 0, 0)
            return
        
        # 2. 从第一个片段自动检测项目根目录
        project_root = get_project_root(items[0][2] if items else None)
        if not DEBUG and not project_root:
            raise RuntimeError(
                "无法自动识别项目目录。\n"
                "请设置环境变量 WATERMARK_PROJECT=/Volumes/MYJC/.../项目名"
            )
        output_dir = get_output_dir(project_root)
        print(f"[项目路径] {project_root or '(调试模式)'}")
        print(f"[输出目录] {output_dir}")
        
        # 3. 初始化状态 + 日志（现在知道项目根了）
        state_init(project_root)
        ops_logger.init(get_log_dir(project_root))
        ops_logger.session_start(project.GetName(), timeline.GetName(), DEFAULT_MODE, 0)
        
        # 结构化日志: 片段扫描
        ops_logger.clip_scan(len(items), 0, [name for _, name, _ in items])
        
        # Pro模式：捡起文件名含「快速预览」的片段（即使褪色）
        pro_upgrades = 0
        i_in = io["video"]["in"]
        i_out = io["video"]["out"]
        if DEFAULT_MODE in ("pro", "pro_box"):
            scanned_names = {n for _, n, _ in items}
            for t2 in range(1, timeline.GetTrackCount("video") + 1):
                for item2 in timeline.GetItemListInTrack("video", t2) or []:
                    s2, e2 = item2.GetStart(), item2.GetEnd()
                    if s2 >= i_out or e2 <= i_in:
                        continue
                    nm2 = item2.GetName()
                    if nm2 in scanned_names or "_去字幕_快速预览" not in nm2:
                        continue
                    mp2 = item2.GetMediaPoolItem()
                    if not mp2:
                        continue
                    # 找原片：状态文件优先，兜底 find
                    rst = need_restore(nm2, DEFAULT_MODE)
                    if rst:
                        items.append((mp2, nm2, rst))
                    else:
                        base2 = re.sub(r'_去字幕_.*$', '', os.path.splitext(nm2)[0])
                        try:
                            result = subprocess.run(
                                ["find", "04_素材/02_视频/", "-name", f"{base2}.mp4"],
                                capture_output=True, text=True,
                                cwd=project_root, timeout=10
                            )
                            found = result.stdout.strip()
                            if found:
                                items.append((mp2, nm2, found))
                        except Exception:
                            pass  # find 失败，这个片段跳过
                    scanned_names.add(nm2)
                    pro_upgrades += 1
        if pro_upgrades:
            print(f"  ↻ 检测到 {pro_upgrades} 个已有预览版，将升级")
        
        # 4. 前置校验
        print(f"\n  校验:")
        valid_tasks = []
        for mp_item, name, path in items:
            is_preview = "_去字幕_快速预览" in name
            is_pro_done = "_去字幕_正式出片" in name
            
            if is_pro_done:
                print(f"  ✅ {name}: 已有正式出片版")
                continue
            
            if DEFAULT_MODE == "basic" and is_preview:
                print(f"  ⏭ {name}: 已有预览版")
                continue
            
            if DEFAULT_MODE in ("pro", "pro_box") and is_preview:
                print(f"  ↻ {name}: 还原原片")
                mp_item.ReplaceClip(path)  # path 已在上游设为原片路径
            else:
                record_original(name, path)
            
            duration = get_video_duration(path)
            if duration > MAX_SOURCE_DURATION:
                print(f"  ⛔ {name}: 时长 {duration:.0f}秒 > 上限，跳过")
                continue
            
            task_kwargs = {"video_path": path, "language": "zh", "model": DEFAULT_MODE}
            if DEFAULT_MODE in ("pro_box",):
                task_kwargs["mask_regions"] = [{
                    "type": "remove_only_ocr",
                    "start": 0, "end": 99999,
                    "region": DEFAULT_MASK_REGION
                }]
            
            valid_tasks.append((mp_item, name, path, task_kwargs, duration))
        
        if not valid_tasks:
            print("  → 有效任务 0 个\n")
            print("[完成] 没有需要处理的片段")
            ops_logger.session_end(0, 0, 0)
            return
        
        print(f"\n  → 有效任务 {len(valid_tasks)} 个\n")
        
        # 只扫描模式
        if SCAN_ONLY:
            print(f"\n{'='*40}")
            print(f"  🔍 仅扫描模式（未调用 API）")
            print(f"  模式: {MODE_LABELS.get(DEFAULT_MODE, DEFAULT_MODE)}")
            for i, (_, name, _, _, _) in enumerate(valid_tasks, 1):
                print(f"  {i}. {name}")
            print(f"  共 {len(valid_tasks)} 个片段待处理")
            print(f"{'='*40}\n")
            ops_logger.session_end(0, 0, len(valid_tasks))
            return
        
        # ── 余额预估（按时长：每 30 秒为一个计费单位）──
        unit_cost = COST_PER_MODE.get(DEFAULT_MODE, 5)
        total_units = sum(max(1, math.ceil(d / 30)) for _, _, _, _, d in valid_tasks)
        total_est = unit_cost * total_units
        
        print(f"\n{'='*40}")
        mode_label = MODE_LABELS.get(DEFAULT_MODE, DEFAULT_MODE)
        rate_min = f"¥{unit_cost * 0.19 * 2:.2f}/分钟"
        print(f"  处理模式:   {mode_label}（{unit_cost} 点/30秒，{rate_min}）")
        print(f"  预估消耗:   {total_units} × {unit_cost} 点 = {total_est} 点 (¥{total_est * 0.19:.2f})")
        
        # 查询余额
        try:
            adapter = GhostCutAdapter(deepcopy(ADAPTER_CONFIGS["ghostcut"]))
            bal = adapter.get_balance()
            now_ms = time.time() * 1000
            pts = sum(a["pointBalance"] for a in bal.get("pointAssets", [])
                      if a["pointBalance"] > 0 and a.get("expireTime", now_ms + 1) > now_ms)
            print(f"  余额: {pts:.1f} 点")
            
            if pts < total_est:
                print(f"\n  ⛔ 余额不足: {pts:.1f} 点 < 预估 {total_est} 点，请先充值再执行")
                ops_logger.balance_check(pts, total_est, "blocked")
                ops_logger.session_end(0, 0, len(valid_tasks), pts)
                return
            ops_logger.balance_check(pts, total_est, "proceed")
        except Exception:
            pts = 0
            print(f"  余额: 查询失败，跳过保护")
        
        print(f"{'='*40}\n")
        
        print(f"\n[处理] {len(valid_tasks)} 个片段 | 串行模式\n")
        
        # 5. 串行处理（达芬奇 Python 线程不安全）
        adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
        results = []
        
        stop_file = os.path.join(PLUGIN_DIR, ".stop")  # 全局停止（SMB）
        local_stop = os.path.join("/tmp", f"ai_subtitle.stop.{os.uname().nodename}")  # 本地停止
        for idx, (mp_item, name, path, kwargs, _dur) in enumerate(valid_tasks, 1):
            if os.path.exists(stop_file) or os.path.exists(local_stop):
                for sf in (stop_file, local_stop):
                    if os.path.exists(sf):
                        os.remove(sf)
                print(f"  ⏹ 停止，跳过剩余 {len(valid_tasks) - idx + 1} 个片段")
                break
            
            # 原子锁
            if not acquire_lock(name):
                print(f"  [{idx}] {name} → ⏭ 其他用户正在处理，跳过")
                results.append((mp_item, name, WatermarkResult(
                    success=False, task_id="", error_message="其他用户正在处理此片段"
                ), 0))
                continue
            
            adapter = GhostCutAdapter(adapter_cfg)
            max_retries = 2
            result = None
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        print(f"  [{idx}] {name} → 重试 {attempt}/{max_retries}...")
                    else:
                        print(f"  [{idx}] {name} → 上传中...")
                    ops_logger.task_submit(name, DEFAULT_MODE, _dur, attempt)
                    t0 = time.time()
                    result = adapter.process(WatermarkTask(**kwargs), timeout=API_TIMEOUT)
                    elapsed = time.time() - t0
                    ops_logger.task_result(name, str(getattr(result, 'task_id', '')), elapsed, result.success)
                    if not result.success:
                        release_lock(name)
                    break  # 成功或逻辑失败，跳出重试
                except Exception as e:
                    if attempt < max_retries:
                        wait = 3 * (attempt + 1)
                        ops_logger.task_error(name, str(e)[:200], attempt)
                        print(f"  [{idx}] {name}: {e}，{wait}秒后重试...")
                        time.sleep(wait)
                    else:
                        err_msg = str(e)[:100]
                        ops_logger.task_error(name, err_msg, attempt)
                        print(f"  [{idx}] {name}: 重试 {max_retries} 次均失败: {err_msg}")
                        release_lock(name)
                        elapsed = 0
                        result = WatermarkResult(
                            success=False, task_id="", error_message=f"重试{max_retries}次后失败: {err_msg}"
                        )
            
            if result and result.success:
                print(f"  ✅ {name} ({elapsed:.0f}秒 | ID: {getattr(result, 'task_id', '')})")
            else:
                print(f"  ❌ {name}: {getattr(result, 'error_message', '未知错误') if result else '处理失败'}")
            results.append((mp_item, name, result or WatermarkResult(success=False), elapsed if 'elapsed' in dir() else 0))
            print()  # 片段间空行
        
        
        print(f"\n[输出] {len(results)} 个结果\n")
        
        # 5. 下载 + ReplaceClip（串行 — Resolve 不线程安全）
        success_count = 0
        for mp_item, name, result, elapsed in results:
            if not result or not result.success:
                continue
            
            base_name = re.sub(r'_去字幕_.*$', '', os.path.splitext(name)[0])
            mode_tag = MODE_FILE_TAGS.get(DEFAULT_MODE, DEFAULT_MODE)
            subdir = "01_预览版" if DEFAULT_MODE == "basic" else "02_正式出片"
            
            # EP 分组
            ep = "EP00"
            ep_match = re.match(r'(EP\d+)', name)
            if ep_match:
                ep = ep_match.group(1)
            ep_dir = os.path.join(output_dir, ep, subdir)
            os.makedirs(ep_dir, exist_ok=True)
            
            version = 1
            while True:
                clean_name = f"{base_name}_去字幕_{mode_tag}_v{version:02d}.mp4"
                dl = os.path.join(ep_dir, clean_name)
                if not os.path.exists(dl):
                    break
                version += 1
            
            print(f"  [下载] {clean_name} ...")
            urllib.request.urlretrieve(result.output_path, dl)
            print(f"  → {ep}/{subdir}/{clean_name} ({os.path.getsize(dl)/1024/1024:.1f} MB)")
            
            if mp_item.ReplaceClip(dl):
                print(f"  ↻ ReplaceClip 完成")
                mark_processed(name, dl, DEFAULT_MODE)
                print(f"  📋 状态: {get_clip_status(name)}\n")
                success_count += 1
            else:
                print(f"  ⚠ ReplaceClip 失败\n")
            release_lock(name)
        
        print(f"  🎉 {success_count}/{len(results)} 个片段完成 → {output_dir}")
        
        # 结构化日志: 会话结束
        ops_logger.session_end(success_count, len(results) - success_count, len(results))
    
    except Exception as e:
        print(f"\n[错误] {e}")
        traceback.print_exc()
        ops_logger.session_end(0, 0, 0)
        sys.exit(1)


if __name__ == "__main__":
    main()
