# -*- coding: utf-8 -*-
"""授权 UI 模块。纯 Python，无 DaVinci 依赖。"""

from datetime import date


def trial_days_left(trial_start_ordinal):
    """试用剩余天数（从 ordinal 日期算起，共 30 天）"""
    return max(0, 30 - (date.today() - date.fromordinal(trial_start_ordinal)).days)


def format_trial(days: int, fp: str = "") -> str:
    """试用文本统一格式"""
    if days > 10:
        return f"试用剩余 {days} 天"
    suffix = f"  |  请联系购买: 微信 paladinpp / B站 电影裁缝Bryan  |  ID: {fp}" if fp else "  |  请联系购买: 微信 paladinpp / B站 电影裁缝Bryan"
    if days > 0:
        return f"试用剩余 {days} 天{suffix}"
    return f"试用剩余 0 天{suffix}"
