"""
core.py — AI去字幕共享业务逻辑
remove_watermark.py 和 ui_external.py 的共同基础层。

设计原则：
- 纯函数：不操作 Resolve 状态（ReplaceClip/mark_processed 留给调用者）
- 行为契约：与 watermark-plugin-rules SKILL.md 严格对齐
- 零副作用：不 print/log/ui，只返回数据
"""

import os
import re
import time
import unicodedata
import urllib.request
from copy import deepcopy
from typing import Optional, NamedTuple, Callable

from config import (
    DEFAULT_MODE, MAX_SOURCE_DURATION,
    CLIP_COLOR, DEFAULT_MASK_REGION,
    ADAPTER_CONFIGS, DEBUG,
    get_project_root, get_output_dir, get_log_dir,
)
from pricing import estimate_cost, point_to_yuan
from pricing import oss_tracker
from adapters import WatermarkTask, WatermarkResult
from adapters.wuhenai_v2 import WuhenAIV21Adapter
from watermark_state import record_original, mark_processed, acquire_lock, release_lock
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
    start_frame: int         # 时间线起始帧


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


def build_output_path(file_name: str, output_dir: str, mode: str = "") -> str:
    """
    构建输出版本化路径。
    返回 (full_path, ep, subdir, clean_name)

    目录结构: {output_dir}/{EP}/{base}_去字幕_v{XX}.mp4
    """
    base_name = re.sub(r'_去字幕_.*$', '', os.path.splitext(file_name)[0])
    subdir = ""
    ep = extract_ep(file_name)
    ep_dir = os.path.join(output_dir, ep)
    os.makedirs(ep_dir, exist_ok=True)

    version = 1
    while True:
        clean_name = f"{base_name}_去字幕_v{version:02d}.mp4"
        full = os.path.join(ep_dir, clean_name)
        if not os.path.exists(full):
            break
        version += 1

    return full, ep, subdir, clean_name


def find_cached_output(file_name: str, output_dir: str, mode: str = None) -> Optional[str]:
    """
    扫输出目录找已处理文件。返回最高版本路径 / None。
    """
    base = os.path.splitext(file_name)[0]
    cached = None
    cached_ver = -1

    try:
        for root_dir, _, files in os.walk(output_dir):
            for f in files:
                if f.startswith(f"{base}_去字幕_v") and f.endswith(".mp4"):
                    ver_match = re.search(r'_v(\d+)\.mp4$', f)
                    ver = int(ver_match.group(1)) if ver_match else 0
                    if ver > cached_ver:
                        cached_ver = ver
                        cached = os.path.join(root_dir, f)
    except Exception:
        pass

    return cached


# ═══════════════════════════════════════════
# 余额查询
# ═══════════════════════════════════════════

def query_balance(adapter_config: dict = None) -> float:
    """查询无痕AI 2.1 余额（默认），返回可用点数。异常返回 0。

    如需查鬼手余额，传入 adapter_config=ADAPTER_CONFIGS['ghostcut']。
    """
    try:
        if adapter_config and adapter_config.get("app_key"):
            # 鬼手（备用适配器）
            from adapters.ghostcut import GhostCutAdapter
            adapter = GhostCutAdapter(adapter_config)
            bal = adapter.get_balance()
            now_ms = time.time() * 1000
            return sum(
                a["pointBalance"] for a in bal.get("pointAssets", [])
                if a["pointBalance"] > 0 and a.get("expireTime", now_ms + 1) > now_ms
            )
        else:
            cfg = adapter_config or deepcopy(ADAPTER_CONFIGS["wuhenai_v21"])
            adapter = WuhenAIV21Adapter(cfg)
            bal = adapter.get_balance()
            return bal.get("balance", 0)
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
    for item, t in candidates:
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

        file_name = mp.GetClipProperty("File Name") or item.GetName() or f"clip_{item.GetStart()}"
        display_name = item.GetName() or file_name  # 用于离线产物过滤

        # 跳过所有"去字幕"产物（_去字幕_快速预览_ / _去字幕_正式出片_ 等）
        # 这类片段不是原片，不应出现在扫描结果中
        if "_去字幕_" in display_name:
            continue
        
        # 用 File Name 去重
        if file_name in seen_fnames:
            continue
        seen_fnames.add(file_name)
        
        duration = get_video_duration(mp)

        clips.append(ClipEntry(
            mp_item=mp, name=file_name, path=path,
            file_name=file_name, duration=duration,
            start_frame=item.GetStart(),
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
        record_original(c.file_name, c.path)

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
            cached = find_cached_output(c.file_name, output_dir, mode)
            if cached:
                if c.mp_item.ReplaceClipPreserveSubClip(cached):
                    mark_processed(c.file_name, cached, mode)
                    cache_hit_names.append(c.name)
                    continue
            remaining_clips.append(c)
    else:
        remaining_clips = valid_clips

    # ── Step 3: 构建 TaskRecord ──
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
    检查: 文件存在→大小正常→ffprobe 可读

    Args:
        output_files: 已生成的文件路径列表

    Returns:
        {"total": int, "ok": int, "fail": int, "problems": [{"file": str, "issues": [str]}]}
    """
    result = {"total": len(output_files), "ok": 0, "fail": 0, "problems": []}

    if not output_files:
        return result

    try:
        import subprocess
        has_ffprobe = subprocess.run(["which", "ffprobe"], capture_output=True).returncode == 0
    except:
        has_ffprobe = False

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

            # ffprobe 视频可读性 + 时长校验
            if has_ffprobe and not issues:
                try:
                    r = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "csv=p=0", f],
                        capture_output=True, text=True, timeout=15
                    )
                    dur = float(r.stdout.strip()) if r.stdout.strip() else 0
                    if dur <= 0:
                        issues.append("视频时长异常或无法解析")
                    elif dur < 3:
                        issues.append(f"视频过短 ({dur:.1f}秒)")
                except (subprocess.TimeoutExpired, ValueError):
                    issues.append("ffprobe 解析超时，文件可能损坏")

        if issues:
            result["problems"].append({"file": name, "issues": issues})
            result["fail"] += 1
        else:
            result["ok"] += 1

    return result


# ═══════════════════════════════════════════
# 共享流水线 — CLI 和 UI 的共同基础
# ═══════════════════════════════════════════

def create_wuhenai_adapter(mode: str = "pro_box") -> WuhenAIV21Adapter:
    """创建标准配置的无痕AI 2.1 适配器（sel_area 模式）。
    CLI 和 UI 都通过这个函数创建适配器，保证行为一致。
    """
    adapter_cfg = deepcopy(ADAPTER_CONFIGS["wuhenai_v21"])
    adapter_cfg["model"] = "video_removal_std"
    adapter_cfg["method"] = "sel_area"
    return WuhenAIV21Adapter(adapter_cfg)


def process_single_clip(
    task,
    adapter: WuhenAIV21Adapter,
    mode: str,
    on_attempt: Callable = None,
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
        (WatermarkResult, elapsed_seconds)
    """
    if not acquire_lock(task.name):
        return (WatermarkResult(success=False, task_id="", error_message="被锁定"), 0)

    result = None
    elapsed = 0
    for attempt in range(3):
        if on_attempt:
            on_attempt(attempt, task.name)

        try:
            ops_logger.task_submit(task.name, mode, task.duration, attempt)
            t0 = time.time()
            result = adapter.process(WatermarkTask(**task.kwargs), timeout=600, cancel_check=cancel_check)
            elapsed = time.time() - t0
            ops_logger.task_result(
                task.name, str(getattr(result, 'task_id', '')), elapsed, result.success,
            )
            if not result.success:
                release_lock(task.name)
            break
        except Exception as e:
            if attempt < 2:
                wait = 3 * (attempt + 1)
                ops_logger.task_error(task.name, str(e)[:200], attempt)
                time.sleep(wait)
            else:
                ops_logger.task_error(task.name, str(e)[:100], attempt)
                release_lock(task.name)
                result = WatermarkResult(
                    success=False, task_id="",
                    error_message=f"重试2次后失败: {str(e)[:100]}",
                )

    return (result, elapsed)


def download_and_apply(
    results: list,
    output_dir: str,
    mode: str,
    check_stop: Callable = None,
    on_done: Callable = None,
    on_fail: Callable = None,
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
    except:
        pass  # 检查失败不阻塞

    for mp_item, name, path, result, elapsed in results:
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

        if mp_item.ReplaceClipPreserveSubClip(dl):
            fn = mp_item.GetClipProperty("File Name") or file_name
            mark_processed(fn, dl, mode)
            success_count += 1
            output_files.append(dl)
            if on_done:
                on_done(ep, subdir, clean_name)
        else:
            fail_list.append({"name": name, "error": "ReplaceClip 失败"})
            if on_fail:
                on_fail(clean_name, "ReplaceClip 失败")
        release_lock(name)

    return success_count, fail_list, output_files
