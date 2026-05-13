# -*- coding: utf-8 -*-
"""
分辨率工具集。

来源：
  - calc_output_dimensions() → Batch_io_Pro.py 张来吃 v2.0.4（VFX Pull 标准）
  - resolution_name() → mappings.py
  - 方向分类 → 项目自有逻辑
"""

import math

from mappings import RESOLUTION_MAPPING, PAR_MAPPING


def parse(res_str: str) -> tuple:
    """'1920x1080' → (1920, 1080)。格式不对返回 (0, 0)。"""
    try:
        w, h = res_str.split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 0, 0


def name(w: int, h: int) -> str:
    """返回标准分辨率名，不匹配返回 'WxH'。"""
    return RESOLUTION_MAPPING.get((w, h), f"{w}x{h}")


def name_from_str(res_str: str) -> str:
    """'1920x1080' → 'HD'。"""
    w, h = parse(res_str)
    return name(w, h)


def is_portrait(w: int, h: int) -> bool:
    """竖屏（h > w）"""
    return h > w


def is_landscape(w: int, h: int) -> bool:
    """横屏（w > h）"""
    return w > h


def is_square(w: int, h: int) -> bool:
    """正方形（w == h）"""
    return w == h


def classify(w: int, h: int) -> str:
    """返回 'portrait' | 'landscape' | 'square'。"""
    if h > w:
        return "portrait"
    if w > h:
        return "landscape"
    return "square"


def calc_output_dimensions(
    res_str: str,
    par_str: str = "Square",
    target: int = 2048,
    direction: str = "按宽度",
) -> tuple:
    """PAR 感知的输出分辨率计算（VFX Pull 标准）。

    竖屏素材或其他方向下无需缩放的，直接返回原分辨率。
    结果保证偶数像素。

    Args:
        res_str: MediaPoolItem Resolution，如 '1920x1080'
        par_str: MediaPoolItem PAR，如 'Square'（默认 1.0）
        target: 目标宽度/高度（按宽度方向时为目标宽，按高度方向时为目标高）
        direction: '按宽度' | '按高度'

    Returns:
        (width, height) — 整数元组
    """
    w, h = parse(res_str)
    if not w or not h:
        return 0, 0

    par = PAR_MAPPING.get(par_str, 1.0)

    if direction == "按宽度":
        if h > w or w <= target:
            return w, h
        height = math.floor(target / w * h / 2 / par) * 2
        return int(target), int(height)
    else:
        if h > w or h <= target:
            return w, h
        width = math.floor(target / (h / par) * w / 2) * 2
        return int(width), int(target)
