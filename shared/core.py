"""
core.py — AI去字幕共享业务逻辑
pipeline.py 和 stable_ui.py 的共同基础层。

设计原则：
- 纯函数：不操作 Resolve 状态（ReplaceClip/mark_processed 留给调用者）
- 行为契约：与 subtitle-plugin-rules SKILL.md 严格对齐
- 零用户可见输出：不 print/ui，只返回数据或写 SMB 运维日志
"""

# ═══════════════════════════════════════════
# 颜色恢复（ReplaceClip 后统一逻辑）
# ═══════════════════════════════════════════

def restore_clip_colors(mp_item, tl_item, tl_color, mp_color, alt_tl_items=None, log_tag="",
                        linked_colors=None):
    """ReplaceClip 后恢复片段原始颜色。

    Args:
        linked_colors: [(linked_tl_item, original_color), ...]
                       caller 在 ReplaceClip 前保存，此处精确还原（含空串=无颜色）
    """
    label = f"[core] {log_tag} " if log_tag else "[core] "

    if mp_color:
        mp_item.SetClipColor(mp_color)
    else:
        try: mp_item.ClearClipColor()
        except Exception: pass

    # 片段色独立还原——与媒体池色互不交叉
    if tl_item:
        try:
            tl_item.SetClipColor(tl_color) if tl_color else tl_item.ClearClipColor()
        except Exception:
            _smb_log(f"{label}恢复 tl 颜色失败: {tl_item.GetName()}")

    for alt_tl, alt_color in (alt_tl_items or ()):
        if alt_color:
            try:
                alt_tl.SetClipColor(alt_color)
            except Exception:
                _smb_log(f"{label}恢复 alt tl 颜色失败")

    # 链接音频：精确还原 ReplaceClip 前 caller 保存的原色（包括空串=无颜色）
    for li, orig_color in (linked_colors or []):
        try:
            li.SetClipColor(orig_color)
        except Exception:
            _smb_log(f"{label}恢复链接音频颜色失败: {li.GetName()}")

import os
import math
import re
import time
import unicodedata
import urllib.request
from copy import deepcopy
from typing import Optional, NamedTuple, Callable, Any

from config import (
    DEFAULT_MODE, MAX_SOURCE_DURATION,
    CLIP_COLOR,
    ADAPTER_CONFIGS, DEBUG,
    get_output_dir, get_log_dir,
)
from ops_logger import _smb_log
from pricing import estimate_cost, point_to_yuan
from pricing import oss_tracker
from adapters import SubtitleTask, SubtitleResult
from subtitle_state import acquire_lock, release_lock
import ledger
from log_writer import get_logger as _get_logger
_log_ops = _get_logger("AI去字幕")
# (record_original, find_output, session_start 等) 不加前缀容易与本地函数混淆


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
    start_frame: int         # 时间线起始帧
    tl_item: object = None   # TimelineItem 引用（替换后恢复颜色用）
    resolution: str = "1920x1080"  # 达芬奇API获取，fallback
    tl_color: str = ""       # TimelineItem 颜色
    mp_color: str = ""       # MediaPoolItem 颜色
    alt_tl_items: tuple = ()  # ((TimelineItem, tl_color), ...) 同文件去重跳过的额外片段


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
    kwargs: dict            # SubtitleTask 构造参数
    duration: float
    tl_item: object = None  # TimelineItem 引用
    tl_color: str = ""      # TimelineItem 原始颜色
    mp_color: str = ""      # MediaPoolItem 原始颜色
    alt_tl_items: tuple = ()  # ((TimelineItem, tl_color), ...) 同文件其他片段


class PreparedTasks(NamedTuple):
    """prepare_tasks 完整结果"""
    tasks: list[TaskRecord]   # 待处理任务列表
    cache_hits: int           # 由缓存完成的片段数
    cache_hit_names: list     # 缓存命中的片段名



# ═══════════════════════════════════════════
# 达芬奇连接
# ═══════════════════════════════════════════

def connect_resolve():
    """获取 Resolve/Project/Timeline。失败抛 RuntimeError。"""
    import fusionscript_loader  # noqa: F811 — 确保加载
    resolve = fusionscript_loader.bmd.scriptapp("Resolve")
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
        # 达芬奇 GetClipProperty 可能抛非预期异常（SWIG类型转换失败），
        # 且视频时长获取不应阻塞扫描流程，降级返回0
        return 0


def extract_ep(filename: str) -> str:
    """从文件名提取 EP 编号，如 'EP01_xxx.mp4' → 'EP01'"""
    m = re.match(r'(EP\d+)', filename)
    return m.group(1) if m else "EP00"


def build_output_path(file_name: str, output_dir: str, mode: str = "") -> tuple:
    """
    构建输出路径。
    返回 (full_path, ep, subdir, clean_name)

    目录结构: {output_dir}/{EP}/{base}_去字幕.mp4

    mode 参数预留：未来可能根据处理模式（如 all_area vs sel_area）选择不同输出子目录。
    当前所有模式共用一个输出路径，mode 参数由调用方传入但函数未消费。
    """
    base_name = re.sub(r'_去字幕.*$', '', os.path.splitext(file_name)[0])
    subdir = ""
    ep = extract_ep(file_name)
    ep_dir = os.path.join(output_dir, ep)
    os.makedirs(ep_dir, exist_ok=True)

    clean_name = f"{base_name}_去字幕.mp4"
    full = os.path.join(ep_dir, clean_name)

    return full, ep, subdir, clean_name


# ═══════════════════════════════════════════
# 余额查询
# ═══════════════════════════════════════════

def query_balance(adapter=None) -> float:
    """查询适配器余额，返回可用点数。异常返回 0。

    调用方传入已创建的适配器实例。不关心供应商类型。
    """
    import time
    try:
        bal = adapter.get_balance()
        if "balance" in bal:
            return float(bal["balance"])
        # GhostCut 格式：pointAssets 数组
        now_ms = time.time() * 1000
        return float(sum(
            a["pointBalance"] for a in bal.get("pointAssets", [])
            if a["pointBalance"] > 0 and a.get("expireTime", now_ms + 1) > now_ms
        ))
    except Exception:
        return 0


# ═══════════════════════════════════════════
# IO 扫描 — 核心过滤链
# ═══════════════════════════════════════════

def scan_io_clips(timeline, clip_color: str = "Orange") -> tuple:
    """
    扫描 IO 区间内所有视频片段，返回 (clips, report)。

    过滤链（与 subtitle-plugin-rules SKILL.md 严格一致）：
      ❌ IO 未设 → 返回 None
      ❌ GetClipEnabled()==False → skipped_disabled
      ❌ 颜色≠目标颜色 → 静默跳过
      ❌ MediaPoolItem==None → skipped_nomp + 警告
      ❌ 摄影机元数据（ISO/Lens/Gamma等）→ skipped_camera
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
             "skipped_disabled": 0, "skipped_nonvideo": 0, "skipped_compound": 0,
             "skipped_camera": 0}
    candidates = []  # (item, track#)  → 第二轮用 File Name 去重
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

            candidates.append((item, t))

    # 按时间线位置排序
    candidates.sort(key=lambda x: x[0].GetStart())

    # 第二轮：用 File Name 去重 + 过滤 + 构建 ClipEntry
    seen_fnames = set()
    # {file_name: [(tl_item, tl_color), ...]} — 同文件去重跳过的额外片段
    alt_tl_by_fname: dict = {}
    for item, t in candidates:
        stats["total"] += 1
        color = item.GetClipColor()

        # 颜色过滤（扫描筛选用片段色彩，替换时分别还原片段+媒体池色）
        if clip_color and color != clip_color:
            continue

        mp = item.GetMediaPoolItem()
        if not mp:
            stats["skipped_nomp"] += 1
            if clip_color and color == clip_color:
                pass  # 警告由调用者处理
            continue

        # 摄影机素材过滤：有摄影机元数据的跳过（不可能带字幕）
        _cam_fields = ("ISO", "Camera Model", "Lens", "Gamma", "Color Space")
        if any(mp.GetClipProperty(f) for f in _cam_fields):
            stats["skipped_camera"] = stats.get("skipped_camera", 0) + 1
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

        file_name = mp.GetClipProperty("File Name") or item.GetName() or f"clip_{item.GetStart()}"
        display_name = item.GetName() or file_name  # 用于离线产物过滤

        # 跳过所有"去字幕"产物
        if "_去字幕" in display_name:
            continue
        
        # 用 File Name 去重 — 同文件多段：首段入 clips，其余记录到 alt_tl_by_fname
        if file_name in seen_fnames:
            alt_tl_by_fname.setdefault(file_name, []).append((item, color or ""))
            continue
        seen_fnames.add(file_name)
        
        duration = get_video_duration(mp)
        resolution = mp.GetClipProperty("Resolution") or "1920x1080"

        clips.append(ClipEntry(
            mp_item=mp, name=file_name, path=path,
            file_name=file_name, duration=duration, start_frame=item.GetStart(),
            tl_item=item, resolution=resolution,
            tl_color=color or "", mp_color=mp.GetClipColor() or "",
        ))

    # 合并 alt_tl_items：同文件去重跳过的片段记入 ClipEntry，ReplaceClip 后恢复其颜色
    if alt_tl_by_fname:
        clips = [ce._replace(alt_tl_items=tuple(alt_tl_by_fname.get(ce.file_name, ())))
                 for ce in clips]

    # 构造报告
    report = ScanReport(
        total=stats["total"],
        valid=len(clips),
        skipped=stats,
    )

    return clips, report


# ═══════════════════════════════════════════
# 任务准备 — 校验 + 缓存
# ═══════════════════════════════════════════

def prepare_tasks(
    clips: list,
    mode: str,
    output_dir: str,
    force: bool = False,
    stop_check=None,
) -> PreparedTasks:
    """
    任务准备流水线：
     1. 前置校验（时长）
     2. 缓存复用（扫输出目录）
     3. 构建 TaskRecord 列表

    Args:
        clips: scan_io_clips 返回的 ClipEntry 列表
        mode: 处理模式
        output_dir: 输出目录
        force: True 则跳过缓存复用

    Returns:
        PreparedTasks: (tasks, cache_hits, cache_hit_names)
    """
    # ── Step 1: 前置校验 ──
    valid_clips = []
    for c in clips:
        ledger.record_original(c.file_name, c.path)

        if c.duration <= 0:
            continue  # 时长异常，跳过

        valid_clips.append(c)

    # ── Step 2: 缓存复用 ──
    cache_hit_names = []
    remaining_clips = []

    if not force:
        for c in valid_clips:
            if stop_check and stop_check():
                break  # 用户点了停止
            cached = ledger.find_output(c.file_name)
            if cached:
                replaced = False
                try:
                    old_path = c.mp_item.GetClipProperty("File Path") or c.path
                    # 保存链接音频原色（ReplaceClip 前读取）
                    linked_colors = []
                    try:
                        for li in (c.tl_item.GetLinkedItems() or ()):
                            linked_colors.append((li, li.GetClipColor() or ""))
                    except Exception: pass
                    replaced = c.mp_item.ReplaceClipPreserveSubClip(cached)
                    if replaced:
                        actual_out = c.mp_item.GetClipProperty("File Path") or cached
                        restore_clip_colors(c.mp_item, c.tl_item, c.tl_color, c.mp_color,
                                           c.alt_tl_items, log_tag="缓存命中",
                                           linked_colors=linked_colors)
                        ledger.record_completed(c.file_name, actual_out, original_path=old_path,
                                                strategy="cached", points=0,
                                                tl_color=c.tl_color, mp_color=c.mp_color)
                        cache_hit_names.append(c.name)
                        continue
                except Exception:
                    _smb_log(f"[core] 缓存命中 ReplaceClip 异常（可能被其他用户锁定媒体池）: {c.name}")
                # ReplaceClip 失败（返回 False 或异常）— 不降级，直接跳过
                _smb_log(f"[core] 跳过 {c.name}: ReplaceClip 失败，媒体池可能被其他用户锁定")
                continue
            remaining_clips.append(c)
    else:
        remaining_clips = valid_clips

    # ── Step 3: 构建 TaskRecord ──
    task_records = []
    for c in remaining_clips:
        kwargs = {"video_path": c.path, "language": "zh", "model": mode, "duration": c.duration, "resolution": c.resolution}
        # mask 由适配器自行计算，不在此处预设错误值
        task_records.append(TaskRecord(
            mp_item=c.mp_item, name=c.name, path=c.path,
            kwargs=kwargs, duration=c.duration,
            tl_item=c.tl_item, tl_color=c.tl_color, mp_color=c.mp_color,
            alt_tl_items=c.alt_tl_items,
        ))

    return PreparedTasks(
        tasks=task_records,
        cache_hits=len(cache_hit_names),
        cache_hit_names=cache_hit_names,
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

def post_check(output_files: list) -> dict:
    """验证输出文件完整性（纯函数，不输出）。
    检查: 文件存在→大小正常

    Args:
        output_files: 已生成的文件路径列表

    Returns:
        {"total": int, "ok": int, "fail": int, "problems": [{"file": str, "issues": [str]}]}
    """
    result: dict[str, Any] = {"total": len(output_files), "ok": 0, "fail": 0, "problems": []}

    if not output_files:
        return result

    for f in output_files:
        name = os.path.basename(f)
        issues = []

        if not os.path.exists(f):
            issues.append("文件不存在")
        else:
            size = os.path.getsize(f)
            if size == 0:
                issues.append("零字节文件")
            elif size < 1024 * 100:  # < 100KB
                issues.append(f"文件过小 ({size} bytes)")

        if issues:
            result["problems"].append({"file": name, "issues": issues})
            result["fail"] += 1
        else:
            result["ok"] += 1

    return result


# ═══════════════════════════════════════════
# 共享流水线 — CLI 和 UI 的共同基础
# ═══════════════════════════════════════════

def process_single_clip(
    task,
    adapter,  # BaseAdapter 子类，由调用方注入
    mode: str,
    on_attempt: Optional[Callable] = None,
    cancel_check=None,
) -> tuple:
    """
    处理单个片段：加锁 → 重试(最多3次) → 返回结果。
    出错时自动释放锁。CLI 和 UI 共享同一处理逻辑。

    Args:
        task: TaskRecord
        adapter: 已初始化的无痕AI 2.1 适配器
        mode: 处理模式
        on_attempt: (attempt: int, name: str) -> None  每次尝试前回调

    Returns:
        (SubtitleResult, elapsed_seconds)
    """
    if not acquire_lock(task.name):
        return (SubtitleResult(success=False, task_id="", error_message="被锁定"), 0)

    result = None
    elapsed = 0.0
    for attempt in range(3):
        if on_attempt:
            on_attempt(attempt, task.name)

        try:
            _log_ops.ops({"event": "task_submit", "name": task.name, "mode": mode,
                           "duration": task.duration, "attempt": attempt})
            t0 = time.time()
            result = adapter.process(SubtitleTask(**task.kwargs), timeout=600, cancel_check=cancel_check)
            elapsed = time.time() - t0
            _log_ops.ops({"event": "task_result", "name": task.name,
                           "task_id": str(getattr(result, 'task_id', '')),
                           "elapsed": elapsed, "success": result.success})
            if not result.success:
                release_lock(task.name)
            break
        except Exception as e:
            if attempt < 2:
                wait = 3 * (attempt + 1)
                _log_ops.ops({"event": "task_error", "name": task.name,
                               "error": str(e)[:200], "attempt": attempt})
                time.sleep(wait)
            else:
                _log_ops.ops({"event": "task_error", "name": task.name,
                               "error": str(e)[:100], "attempt": attempt})
                release_lock(task.name)
                result = SubtitleResult(
                    success=False, task_id="",
                    error_message=f"重试2次后失败: {str(e)[:100]}",
                )


    # 严重超时警告（实际 > 预估 × 2）
    if elapsed > 0 and task.duration > 0:
        from pipeline_utils import estimate_processing_time
        est = estimate_processing_time([task])
        if elapsed > est * 2:
            factor = elapsed / est
            _smb_log(f"[core] ⚠️ 严重超时: {task.name} 预估{est:.0f}s 实际{elapsed:.0f}s ({factor:.1f}倍)")
            _log_ops.ops({"event": "task_error", "name": task.name,
                           "error": f"超时 {factor:.1f}倍 (预估{est:.0f}s)", "attempt": 99})
    return (result, elapsed)


def download_and_apply(
    results: list,
    output_dir: str,
    mode: str,
    check_stop: Optional[Callable] = None,
    on_done: Optional[Callable] = None,
    on_fail: Optional[Callable] = None,
    on_start: Optional[Callable] = None,
    provider: str = "",
) -> tuple:
    """
    下载 API 处理结果 → ReplaceClip → 标记完成。
    CLI 和 UI 共享同一下载替换逻辑。

    Args:
        results: [(mp_item, name, path, result, elapsed), ...]
        output_dir: 输出根目录
        mode: 处理模式
        check_stop: () -> bool, 返回 True 则中断
        on_done: (ep, subdir, clean_name) -> None
        on_fail: (clean_name, error) -> None

    Returns:
        (success_count, fail_list, output_files)
    """
    success_count = 0
    fail_list = []
    output_files = []

    # 磁盘空间预检（粗略估算：每个结果约 30MB）
    try:
        st = os.statvfs(output_dir or ".")
        free_mb = (st.f_frsize * st.f_bavail) // (1024 * 1024)
        need_mb = len(results) * 30
        if free_mb < need_mb and free_mb < 1024:  # < 1GB 才报警
            msg = f"磁盘空间不足: 可用{free_mb}MB < 约需{need_mb}MB"
            if on_fail:
                for _, name, _, _, _ in results:
                    on_fail(name, msg)
            return 0, [{"name": "磁盘", "error": msg}], []
    except OSError:
        # os.statvfs 在 SMB 断连时可能失败，磁盘检查不是关键路径，失败不阻塞处理
        _smb_log("[core] 磁盘空间预检跳过（SMB可能不可用）")

    for mp_item, name, path, result, elapsed, *rest in results:
        tl_item = rest[0] if rest else None          # TimelineItem
        tl_color = rest[1] if len(rest) > 1 else ""  # TimelineItem 原色
        mp_color = rest[2] if len(rest) > 2 else ""  # MediaPoolItem 原色
        alt_tl_items = rest[3] if len(rest) > 3 else ()  # 同文件去重跳过的额外片段
        if check_stop and check_stop():
            break
        if not result or not result.success:
            fail_list.append({
                "name": name,
                "error": getattr(result, 'error_message', '') if result else '',
            })
            continue

        file_name = os.path.basename(path)
        dl, ep, subdir, clean_name = build_output_path(file_name, output_dir, mode)

        if on_start:
            on_start(clean_name)

        try:
            is_remote = result.output_path.startswith("http")
            urllib.request.urlretrieve(result.output_path, dl)
            if is_remote:
                oss_tracker.track_download(os.path.getsize(dl))
        except Exception as e:
            fail_list.append({"name": name, "error": f"下载失败: {e}"})
            if on_fail:
                on_fail(clean_name, f"下载失败: {e}")
            release_lock(name)
            continue

        # 下载后快速校验（文件存在 + 大小正常），不合格不替换
        if not os.path.exists(dl) or os.path.getsize(dl) == 0:
            fail_list.append({"name": name, "error": "下载文件为空或不存在"})
            if on_fail:
                on_fail(clean_name, "下载文件为空或不存在")
            release_lock(name)
            continue

        fn = mp_item.GetClipProperty("File Name") or file_name
        # 保存链接音频原色（ReplaceClip 前读取）
        linked_colors = []
        try:
            for li in (tl_item.GetLinkedItems() if tl_item else [] or ()):
                linked_colors.append((li, li.GetClipColor() or ""))
        except Exception: pass
        try:
            replaced = mp_item.ReplaceClipPreserveSubClip(dl)
        except Exception:
            replaced = False
            _smb_log(f"[core] ReplaceClip 异常（可能被其他用户锁定媒体池）: {name}")

        # 无论 ReplaceClip 是否成功，下载已完成，记录到账本（下次可直接复用缓存）
        # 元数据从 adapter result 提取
        meta = getattr(result, 'metadata', {}) or {}
        strategy = meta.get("strategy", "")
        resolution = meta.get("resolution", "")
        meta_dur = meta.get("duration", 0)
        if meta_dur > 0 and strategy:
            unit_cost = 1.5 if strategy == "all_area" else 1
            points = math.ceil(meta_dur * unit_cost)
            cost_yuan = point_to_yuan(points)
        else:
            points = 0
            cost_yuan = 0.0

        output_path_for_ledger = dl  # 下载路径，即使 ReplaceClip 失败也可缓存
        ledger.record_completed(fn, output_path_for_ledger, original_path=path,
                                strategy=strategy, resolution=resolution,
                                points=points, cost_yuan=cost_yuan,
                                tl_color=tl_color, mp_color=mp_color,
                                provider=provider)

        if replaced:
            # 恢复原色
            restore_clip_colors(mp_item, tl_item, tl_color, mp_color, alt_tl_items,
                               log_tag="下载替换", linked_colors=linked_colors)
            actual_path = mp_item.GetClipProperty("File Path") or dl
            success_count += 1
            output_files.append(actual_path)
            if on_done:
                on_done(ep, subdir, clean_name)
        else:
            fail_list.append({"name": name, "error": "替换失败（可能被其他用户锁定媒体池）"})
            if on_fail:
                on_fail(clean_name, "替换失败（可能被其他用户锁定媒体池）")
        release_lock(name)

    return success_count, fail_list, output_files
