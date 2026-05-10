# -*- coding: utf-8 -*-
"""
管道共享工具 — CLI 和 UI 共用的计算/校验逻辑。

避免两边各写一套相同公式导致不同步。
"""

import math
import os


# ── 片段校验 ──

MAX_FILE_SIZE = 100 * 1024 * 1024   # 100MB
MAX_DURATION = 30                   # 秒


def validate_task(task) -> tuple:
    """校验一个 TaskRecord 是否可处理。

    Returns:
        (is_valid: bool, error: str|None)
    """
    # 零字节
    try:
        fsize = os.path.getsize(task.path)
    except OSError:
        return False, "文件不可读"
    if fsize == 0:
        return False, "文件大小为0"
    if fsize > MAX_FILE_SIZE:
        return False, f"文件 {fsize / 1048576:.0f}MB，超过 {MAX_FILE_SIZE / 1048576:.0f}MB 限制"
    # 时长
    if task.duration <= 0:
        return False, f"时长异常 ({task.duration:.1f}秒)"
    if task.duration > MAX_DURATION:
        return False, f"时长 {task.duration:.0f}秒，超过 {MAX_DURATION}秒限制"
    return True, None


# ── 缓存省钱计算 ──

def calc_cache_savings(clips, cache_hit_names: list, provider: str = "") -> dict:
    """计算缓存命中所节省的费用。

    Args:
        clips: ClipEntry 列表（含 name, duration）
        cache_hit_names: 缓存命中的片段名列表
        provider: 供应商标识（"wuhenai" / "ghostcut"），空则查 active provider

    Returns:
        {"secs": int, "yuan": float}
    """
    if not provider:
        from pricing import ACTIVE_PROVIDER as provider
    clip_dur = {c.name: c.duration for c in clips}
    total_secs = sum(math.ceil(clip_dur.get(cn, 0)) for cn in cache_hit_names)
    # 按供应商费率计算
    from pricing import point_to_yuan
    points_per_sec = 1.0  # 默认 1 积分/秒
    try:
        from pricing_defaults import PRICING
        p = PRICING.get(provider, {})
        points_per_sec = p.get("points_per_sec", 1.0)
    except Exception:
        pass
    return {
        "secs": total_secs,
        "yuan": round(total_secs * points_per_sec * point_to_yuan(1), 2),
    }


# ── 时间预估 ──

def estimate_processing_time(tasks: list) -> float:
    """预估处理耗时（秒）。

    实测公式：片段总秒数 × 2.0 + 60 基础开销（v1.8 并发上传降低系数）。
    单片段时无并发收益，系数保持 2.3。
    """
    total_secs = sum(math.ceil(t.duration) for t in tasks)
    if len(tasks) <= 1:
        return total_secs * 2.3 + 60
    return total_secs * 2.0 + 60


# ── 耗时格式化 ──

def format_duration(seconds: float) -> str:
    """秒数 → 'X分Y秒'"""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}分{secs}秒"
