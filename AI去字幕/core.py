"""
core.py — AI去字幕共享业务逻辑
remove_watermark.py 和 ui_external.py 的共同基础层。

设计原则：
- 纯函数：不操作 Resolve 状态（ReplaceClip/mark_processed 留给调用者）
- 行为契约：与 watermark-plugin-rules SKILL.md 严格对齐
- 零副作用：不 print/log/ui，只返回数据
"""

import math
import os
import re
import time
import unicodedata
from copy import deepcopy
from typing import Optional, NamedTuple

from config import (
    COST_PER_MODE, DEFAULT_MODE, MAX_SOURCE_DURATION,
    CLIP_COLOR, DEFAULT_MASK_REGION, MODE_FILE_TAGS,
    ADAPTER_CONFIGS, DEBUG,
    get_project_root, get_output_dir, get_log_dir,
)
from adapters import WatermarkTask
from adapters.ghostcut import GhostCutAdapter
from watermark_state import record_original, mark_processed, need_restore
import ops_logger


# ═══════════════════════════════════════════
# 结构化数据类型
# ═══════════════════════════════════════════

class ClipEntry(NamedTuple):
    """IO 内一个有效片段"""
    mp_item: object          # MediaPoolItem
    name: str                # 时间线显示名
    path: str                # 磁盘文件路径
    file_name: str           # File Name（最稳定标识）
    duration: float          # 秒
    is_preview: bool         # 是否已有快速预览版
    is_pro_done: bool        # 是否已有正式出片版


class ScanReport(NamedTuple):
    """IO 扫描统计"""
    total: int               # IO 内视频总数（去重后）
    valid: int               # 符合颜色+类型的片段数
    skipped: dict            # {原因: 数量}


class TaskRecord(NamedTuple):
    """一个就绪的 API 任务"""
    mp_item: object
    name: str
    path: str
    kwargs: dict            # WatermarkTask 构造参数
    duration: float


class PreparedTasks(NamedTuple):
    """prepare_tasks 完整结果"""
    tasks: list             # [TaskRecord, ...]
    cache_hits: int         # 由缓存完成的片段数
    cache_hit_names: list   # 缓存命中的片段名
    pro_upgrades: int       # 预览版升级数


# ═══════════════════════════════════════════
# 达芬奇连接
# ═══════════════════════════════════════════

def connect_resolve():
    """获取 Resolve/Project/Timeline。失败抛 RuntimeError。"""
    import DaVinciResolveScript as dvr_script
    resolve = dvr_script.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("请先启动 DaVinci Resolve Studio")

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError("请先打开一个项目")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("请先打开一条时间线")

    return resolve, project, timeline


def get_io(timeline) -> tuple:
    """获取 IO 入出点。返回 (in, out)，未设返回 (0, 0)。"""
    mk = timeline.GetMarkInOut()
    if not mk:
        return (0, 0)
    v = mk.get("video", {})
    return (v.get("in", 0), v.get("out", 0))


def get_video_duration(mp_item) -> float:
    """从 MediaPoolItem 获取视频时长（秒），零外部依赖。"""
    try:
        frames = int(mp_item.GetClipProperty("Frames") or 0)
        fps = float(mp_item.GetClipProperty("FPS") or 24)
        return frames / fps if fps > 0 else 0
    except Exception:
        return 0


def extract_ep(filename: str) -> str:
    """从文件名提取 EP 编号，如 'EP01_xxx.mp4' → 'EP01'"""
    m = re.match(r'(EP\d+)', filename)
    return m.group(1) if m else "EP00"


def build_output_path(file_name: str, output_dir: str, mode: str) -> str:
    """
    构建输出版本化路径。
    返回 (full_path, ep, subdir, clean_name)

    目录结构: {output_dir}/{EP}/{01_预览版|02_正式出片}/{base}_去字幕_{tag}_v{XX}.mp4
    """
    base_name = re.sub(r'_去字幕_.*$', '', os.path.splitext(file_name)[0])
    mode_tag = MODE_FILE_TAGS.get(mode, mode)
    subdir = "01_预览版" if mode == "basic" else "02_正式出片"
    ep = extract_ep(file_name)
    ep_dir = os.path.join(output_dir, ep, subdir)
    os.makedirs(ep_dir, exist_ok=True)

    version = 1
    while True:
        clean_name = f"{base_name}_去字幕_{mode_tag}_v{version:02d}.mp4"
        full = os.path.join(ep_dir, clean_name)
        if not os.path.exists(full):
            break
        version += 1

    return full, ep, subdir, clean_name


def find_cached_output(file_name: str, output_dir: str, mode: str) -> Optional[str]:
    """
    扫输出目录找已处理文件。返回最高版本路径 / None。
    """
    base = os.path.splitext(file_name)[0]
    mode_tag = MODE_FILE_TAGS.get(mode, mode)
    cached = None
    cached_ver = -1

    try:
        for root_dir, _, files in os.walk(output_dir):
            for f in files:
                if f.startswith(f"{base}_去字幕_{mode_tag}_v") and f.endswith(".mp4"):
                    ver_match = re.search(r'_v(\d+)\.mp4$', f)
                    ver = int(ver_match.group(1)) if ver_match else 0
                    if ver > cached_ver:
                        cached_ver = ver
                        cached = os.path.join(root_dir, f)
    except Exception:
        pass

    return cached


def estimate_cost(tasks: list, mode: str) -> tuple:
    """
    预估消耗。返回 (total_units, total_points, unit_cost)
    unit_cost 用 COST_PER_MODE，每 30 秒为一个计费单位。
    """
    unit_cost = COST_PER_MODE.get(mode, 5)
    total_units = sum(max(1, math.ceil(t.duration / 30)) for t in tasks)
    total_points = unit_cost * total_units
    return total_units, total_points, unit_cost


def query_balance(adapter_config: dict = None) -> float:
    """查询鬼手余额，返回可用点数。异常返回 0。"""
    try:
        cfg = adapter_config or deepcopy(ADAPTER_CONFIGS["ghostcut"])
        adapter = GhostCutAdapter(cfg)
        bal = adapter.get_balance()
        now_ms = time.time() * 1000
        pts = sum(
            a["pointBalance"] for a in bal.get("pointAssets", [])
            if a["pointBalance"] > 0 and a.get("expireTime", now_ms + 1) > now_ms
        )
        return pts
    except Exception:
        return 0


# ═══════════════════════════════════════════
# IO 扫描 — 核心过滤链
# ═══════════════════════════════════════════

def scan_io_clips(timeline, clip_color: str = "Orange") -> tuple:
    """
    扫描 IO 区间内所有视频片段，返回 (clips, report)。

    过滤链（与 watermark-plugin-rules SKILL.md 严格一致）：
      ❌ IO 未设 → 返回 None
      ❌ GetClipEnabled()==False → skipped_disabled
      ❌ 颜色≠目标颜色 → 静默跳过
      ❌ MediaPoolItem==None → skipped_nomp + 警告
      ❌ Type in (复合,Fusion,VFX连接) → skipped_compound + 警告
      ❌ Type 不含"视频" → skipped_nonvideo + 警告
      ❌ File Path 空/不存在 → skipped_nopath + 警告
      ✅ → 进入 clips 列表

    Returns:
        (list[ClipEntry], ScanReport)  或  (None, None) 表示 IO 未设
    """
    io_in, io_out = get_io(timeline)
    if io_out <= io_in:
        return None, None

    stats = {"total": 0, "skipped_nomp": 0, "skipped_nopath": 0,
             "skipped_disabled": 0, "skipped_nonvideo": 0, "skipped_compound": 0}
    seen = {}  # name → (item, track#)
    clips = []

    for t in range(1, timeline.GetTrackCount("video") + 1):
        items = timeline.GetItemListInTrack("video", t)
        if not items:
            continue
        for item in items:
            s, e = item.GetStart(), item.GetEnd()
            if s >= io_out or e <= io_in:
                continue

            # 跳过禁用片段
            if not item.GetClipEnabled():
                stats["skipped_disabled"] += 1
                continue

            name = item.GetName()
            # 同名去重：已有的 Orange 版本优先保留
            if name in seen:
                existing_item, _ = seen[name]
                if clip_color and existing_item.GetClipColor() == clip_color:
                    continue
            seen[name] = (item, t)

    # 第二轮：过滤 + 构建 ClipEntry
    for name, (item, t) in seen.items():
        stats["total"] += 1
        color = item.GetClipColor()

        # 颜色过滤
        if clip_color and color != clip_color:
            continue

        mp = item.GetMediaPoolItem()
        if not mp:
            stats["skipped_nomp"] += 1
            if clip_color and color == clip_color:
                pass  # 警告由调用者处理
            continue

        # 虚拟容器片段
        mp_type = mp.GetClipProperty("Type") or ""
        if mp_type in ("复合", "Fusion", "VFX连接"):
            stats["skipped_compound"] += 1
            if clip_color and color == clip_color:
                pass  # 警告由调用者处理
            continue

        # 只处理视频
        if "视频" not in mp_type:
            stats["skipped_nonvideo"] += 1
            if clip_color and color == clip_color:
                pass  # 警告由调用者处理
            continue

        path = mp.GetClipProperty("File Path")
        if not path or not os.path.exists(path):
            stats["skipped_nopath"] += 1
            if clip_color and color == clip_color:
                pass  # 警告由调用者处理
            continue

        file_name = mp.GetClipProperty("File Name") or name
        duration = get_video_duration(mp)

        clips.append(ClipEntry(
            mp_item=mp, name=name, path=path,
            file_name=file_name, duration=duration,
            is_preview="_去字幕_快速预览" in name,
            is_pro_done="_去字幕_正式出片" in name,
        ))

    # 构造报告
    skipped_total = sum(v for k, v in stats.items() if k.startswith("skipped_"))
    report = ScanReport(
        total=stats["total"],
        valid=len(clips),
        skipped=stats,
    )

    return clips, report


# ═══════════════════════════════════════════
# 任务准备 — 校验 + 缓存 + Pro 升级
# ═══════════════════════════════════════════

def prepare_tasks(
    clips: list,
    timeline,
    mode: str,
    output_dir: str,
    project_root: str = "",
    force: bool = False,
) -> PreparedTasks:
    """
    完整的任务准备流水线：
     1. 前置校验（已完成/预览版/时长）
     2. Pro 升级扫描（找已有预览版 → 还原原片 → 重新处理）
     3. 缓存复用（扫输出目录）
     4. 构建 TaskRecord 列表

    Args:
        clips: scan_io_clips 返回的 ClipEntry 列表
        timeline: 达芬奇 Timeline 对象
        mode: 处理模式 ("basic"/"pro_box")
        output_dir: 输出目录
        project_root: 项目根目录
        force: True 则跳过缓存复用

    Returns:
        PreparedTasks: (tasks, cache_hits, cache_hit_names, pro_upgrades)
    """
    # ── Step 1: Pro 升级扫描 ──
    pro_upgrades = 0
    io_in, io_out = get_io(timeline)

    if mode in ("pro", "pro_box"):
        scanned_names = {c.name for c in clips}
        for t2 in range(1, timeline.GetTrackCount("video") + 1):
            for item2 in timeline.GetItemListInTrack("video", t2) or []:
                s2, e2 = item2.GetStart(), item2.GetEnd()
                if s2 >= io_out or e2 <= io_in:
                    continue
                if not item2.GetClipEnabled():
                    continue
                nm2 = item2.GetName()
                if nm2 in scanned_names or not re.search(r'_去字幕_快速预览_v\d+\.\w+$', nm2):
                    continue
                mp2 = item2.GetMediaPoolItem()
                if not mp2:
                    continue
                mp2_type = mp2.GetClipProperty("Type") or ""
                if "视频" not in mp2_type:
                    continue
                # 找原片
                file_name2 = mp2.GetClipProperty("File Name") or nm2
                original = need_restore(file_name2, mode)
                if original:
                    clips.append(ClipEntry(
                        mp_item=mp2, name=nm2, path=original,
                        file_name=file_name2, duration=get_video_duration(mp2),
                        is_preview=True, is_pro_done=False,
                    ))
                else:
                    # 兜底: 文件系统搜索
                    base2 = re.sub(r'_去字幕_.*$', '', os.path.splitext(nm2)[0])
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["find", "04_素材/02_视频/", "-name", f"{base2}.mp4"],
                            capture_output=True, text=True, encoding="utf-8",
                            cwd=project_root, timeout=10
                        )
                        found = result.stdout.strip()
                        if found:
                            clips.append(ClipEntry(
                                mp_item=mp2, name=nm2, path=found,
                                file_name=file_name2, duration=get_video_duration(mp2),
                                is_preview=True, is_pro_done=False,
                            ))
                    except Exception:
                        pass
                scanned_names.add(nm2)
                pro_upgrades += 1

    # ── Step 2: 前置校验 ──
    valid_clips = []
    for c in clips:
        if c.is_pro_done:
            continue  # 已有正式出片版

        if mode == "basic" and c.is_preview:
            continue  # 已有预览版

        if mode in ("pro", "pro_box") and c.is_preview:
            # 还原原片
            c.mp_item.ReplaceClipPreserveSubClip(c.path)
        else:
            record_original(c.file_name, c.path)

        if c.duration > MAX_SOURCE_DURATION:
            continue

        valid_clips.append(c)

    # ── Step 3: 缓存复用 ──
    cache_hit_names = []
    remaining_clips = []

    if not force:
        for c in valid_clips:
            cached = find_cached_output(c.file_name, output_dir, mode)
            if cached:
                if c.mp_item.ReplaceClipPreserveSubClip(cached):
                    mark_processed(c.file_name, cached, mode)
                    cache_hit_names.append(c.name)
                    continue
            remaining_clips.append(c)
    else:
        remaining_clips = valid_clips

    # ── Step 4: 构建 TaskRecord ──
    task_records = []
    for c in remaining_clips:
        kwargs = {"video_path": c.path, "language": "zh", "model": mode}
        if mode in ("pro_box",):
            kwargs["mask_regions"] = [{
                "type": "remove_only_ocr",
                "start": 0, "end": 99999,
                "region": DEFAULT_MASK_REGION,
            }]
        task_records.append(TaskRecord(
            mp_item=c.mp_item, name=c.name, path=c.path,
            kwargs=kwargs, duration=c.duration,
        ))

    return PreparedTasks(
        tasks=task_records,
        cache_hits=len(cache_hit_names),
        cache_hit_names=cache_hit_names,
        pro_upgrades=pro_upgrades,
    )


# ═══════════════════════════════════════════
# Unicode 字符映射 — 文件名安全 + 跨源匹配
# ═══════════════════════════════════════════

# 全角/变体 → ASCII 基准字符映射表
# 新增映射只需追加一行，sanitize/normalize 自动生效。
_CHAR_MAP = [
    ('\uff1a', ':'), ('\uff1f', '?'), ('\uff01', '!'),
    ('\uff0c', ','), ('\uff0f', '/'),
    ('\uff08', '('), ('\uff09', ')'), ('\u3010', '['), ('\u3011', ']'),
    ('\u2018', "'"), ('\u2019', "'"), ('\u201c', '"'), ('\u201d', '"'),
    ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'), ('\uff0d', '-'),
    ('\u2022', '\u00b7'), ('\u2027', '\u00b7'), ('\u30fb', '\u00b7'),
    ('\uff65', '\u00b7'), ('\u0387', '\u00b7'), ('\u2219', '\u00b7'),
]
_CHAR_TRANSLATE = str.maketrans({k: v for k, v in _CHAR_MAP})


def sanitize_filename(text: str) -> str:
    """将文本中的不安全字符替换为文件系统安全形式。"""
    result = re.sub(r'[\x00-\x1f]', '', text)
    result = result.translate(_CHAR_TRANSLATE)
    result = result.replace('/', '&').replace('\\', '&')
    result = result.replace(': ', '：').replace(':', '：')
    result = result.replace('?', '？').replace('*', '\u2731')
    result = result.replace('"', "'")
    result = result.replace('<', '\u300a').replace('>', '\u300b').replace('|', '\uff5c')
    result = result.rstrip(' .')
    return unicodedata.normalize('NFC', result)


def normalize_for_match(s: str) -> str:
    """Unicode 变体折叠 + 标点归一化，用于跨源名称匹配。"""
    s = unicodedata.normalize('NFC', s).translate(_CHAR_TRANSLATE)
    s = s.replace('…', '').replace('...', '')
    s = re.sub(r':\s+', ':', s)
    s = re.sub(r'\s*([()[\]])\s*', r'\1', s)
    s = re.sub(r'\s+', ' ', s)
    return s.lower().strip()


# ═══════════════════════════════════════════
# Post-check 输出验证
# ═══════════════════════════════════════════

def post_check(output_files: list):
    """验证输出文件完整性。

    Args:
        output_files: 已生成的文件路径列表
    """
    from logger import ok, warn, fail, info as _info

    if not output_files:
        _info("无输出文件，跳过验证")
        return

    total = len(output_files)
    ok_count = 0
    fail_count = 0

    for f in output_files:
        name = os.path.basename(f)
        problems = []

        # 零字节检测
        if not os.path.exists(f):
            problems.append("文件不存在")
        else:
            size = os.path.getsize(f)
            if size == 0:
                problems.append("零字节文件")
            elif size < 1024 * 100:  # < 100KB
                problems.append(f"文件过小 ({size} bytes)")

        if problems:
            fail(f"{name}: {', '.join(problems)}")
            fail_count += 1
        else:
            ok_count += 1

    if fail_count == 0:
        ok(f"全部 {total} 个文件校验通过")
    else:
        warn(f"{ok_count}/{total} 通过, {fail_count} 个异常")
