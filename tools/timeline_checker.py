#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间线检查工具 v1.0.0
检查三项：黑边、字幕夹帧、轨道结构。

用法（达芬奇运行时）：
    python3 timeline_checker.py

在达芬奇中打开项目和时间线后运行此脚本。
"""

import sys
import os

# ── 路径设置：引入 shared/ 模块 ────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.join(_HERE, '..', 'shared')
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from fusionscript_loader import bmd
from timecode import SMPTE
from resolution import parse as parse_resolution

# ── 配置 ───────────────────────────────────────────────
SUBTITLE_CLAMP_THRESHOLD = 2       # ≤N 帧算夹帧
EXPECTED_SUBTITLE_TRACKS = 1
EXPECTED_VIDEO_TRACKS = 5
EXPECTED_AUDIO_TRACKS = 10

# ── 辅助 ───────────────────────────────────────────────


def _frame_to_tc(frames: int, fps: float) -> str:
    """帧数 → SMPTE 时码（非丢帧）"""
    smpte = SMPTE()
    smpte.fps = fps
    smpte.df = False
    return smpte.gettc(frames)


def _parse_resolution_safe(res_str):
    """安全解析分辨率字符串，返回 (w, h) 或 (0, 0)"""
    if not res_str:
        return 0, 0
    return parse_resolution(res_str)


def _aspect_ratio(w: int, h: int) -> float:
    """宽高比"""
    if not w or not h:
        return 0
    return w / h


def _tracks_match(label: str, actual: int, expected: int) -> tuple:
    """返回 (passed: bool, msg: str)"""
    if actual == expected:
        return True, f'✅ {label}: {actual} (通过)'
    return False, f'❌ {label}: {actual} (应为 {expected})'


# ── 检查 1：轨道结构 ───────────────────────────────────


def check_track_structure(timeline) -> list:
    """检查字幕/视频/音频轨道数量是否符合模板。返回错误消息列表。"""
    errors = []

    subtitle_count = timeline.GetTrackCount("subtitle")
    video_count = timeline.GetTrackCount("video")
    audio_count = timeline.GetTrackCount("audio")

    passed, msg = _tracks_match("字幕轨道", subtitle_count, EXPECTED_SUBTITLE_TRACKS)
    if not passed:
        errors.append(msg)
    else:
        errors.append(msg)  # 通过也打印

    passed, msg = _tracks_match("视频轨道", video_count, EXPECTED_VIDEO_TRACKS)
    if not passed:
        errors.append(msg)
    else:
        errors.append(msg)

    passed, msg = _tracks_match("音频轨道", audio_count, EXPECTED_AUDIO_TRACKS)
    if not passed:
        errors.append(msg)
    else:
        errors.append(msg)

    return errors


# ── 检查 2：黑边 ────────────────────────────────────────


def check_black_borders(timeline, tl_width: int, tl_height: int, fps: float) -> list:
    """检查所有视频轨片段是否有黑边风险。返回错误/警告消息列表。"""
    errors = []
    tl_aspect = _aspect_ratio(tl_width, tl_height)
    if not tl_aspect:
        errors.append('⚠ 无法获取时间线分辨率')
        return errors

    video_track_count = timeline.GetTrackCount("video")
    total_clips = 0
    mismatched = 0
    compensated = 0
    no_source = 0

    for ti in range(1, video_track_count + 1):
        items = timeline.GetItemListInTrack("video", ti)
        if not items:
            continue

        for item in items:
            total_clips += 1
            name = item.GetName()
            start_frame = item.GetStart()

            # 跳过复合片段/生成器
            mp_item = item.GetMediaPoolItem()
            if not mp_item:
                no_source += 1
                continue

            # 源分辨率
            mp_props = mp_item.GetClipProperty()
            src_res = mp_props.get('Resolution', '') if mp_props else ''
            src_w, src_h = _parse_resolution_safe(src_res)
            if not src_w or not src_h:
                no_source += 1
                continue

            src_aspect = _aspect_ratio(src_w, src_h)

            # 比例匹配 → 无黑边
            if abs(src_aspect - tl_aspect) < 0.01:
                continue

            # 比例不匹配 → 检查是否已用缩放/裁切补偿
            transform_props = item.GetProperty() or {}
            zoom_x = transform_props.get('ZoomX', 1.0)
            zoom_y = transform_props.get('ZoomY', 1.0)
            crop_l = transform_props.get('CropLeft', 0)
            crop_r = transform_props.get('CropRight', 0)
            crop_t = transform_props.get('CropTop', 0)
            crop_b = transform_props.get('CropBottom', 0)
            pan = transform_props.get('Pan', 0.0)

            has_zoom = abs(zoom_x - 1.0) > 0.01 or abs(zoom_y - 1.0) > 0.01
            has_crop = crop_l != 0 or crop_r != 0 or crop_t != 0 or crop_b != 0
            has_pan = abs(pan) > 0.01

            if has_zoom or has_crop or has_pan:
                # 已调整，但仍需人工确认
                compensated += 1
                tc = _frame_to_tc(start_frame, fps)
                errors.append(
                    f'⚠ V{ti} {tc}  {name}  '
                    f'({src_w}x{src_h} ≠ {tl_width}x{tl_height}, 已缩放/裁切, 需人工确认)'
                )
            else:
                # 未调整 → 大概率有黑边
                mismatched += 1
                tc = _frame_to_tc(start_frame, fps)
                errors.append(
                    f'❌ V{ti} {tc}  {name}  '
                    f'({src_w}x{src_h} ≠ {tl_width}x{tl_height}, 未缩放, 可能存在黑边)'
                )

    # 汇总
    if mismatched == 0 and compensated == 0:
        status = f'✅ 通过: {total_clips} 个视频片段, 无黑边风险'
    elif mismatched == 0:
        status = f'⚠ 需确认: {compensated}/{total_clips} 个片段比例不同但已缩放'
    else:
        status = f'❌ 黑边风险: {mismatched} 个未缩放 + {compensated} 个需确认 / 共 {total_clips} 个片段'
    if no_source:
        status += f' (跳过 {no_source} 个无源片段)'

    # 将汇总插入到开头
    errors.insert(0, status)
    return errors


# ── 检查 3：字幕夹帧 ────────────────────────────────────


def check_subtitle_frame_clamping(timeline, fps: float) -> list:
    """检查字幕轨上时长过短（夹帧）的字幕。返回错误消息列表。"""
    errors = []
    subtitle_track_count = timeline.GetTrackCount("subtitle")

    if subtitle_track_count == 0:
        errors.append('⚠ 无字幕轨道, 跳过夹帧检查')
        return errors

    total_subtitles = 0
    clamped_count = 0
    disabled_count = 0

    for si in range(1, subtitle_track_count + 1):
        items = timeline.GetItemListInTrack("subtitle", si)
        if not items:
            continue

        for item in items:
            total_subtitles += 1
            name = item.GetName()
            start_frame = item.GetStart()
            duration = item.GetDuration()

            # 跳过禁用的字幕
            enabled = item.GetClipEnabled()
            if enabled is False:
                disabled_count += 1
                continue

            if duration <= SUBTITLE_CLAMP_THRESHOLD:
                clamped_count += 1
                tc = _frame_to_tc(start_frame, fps)

                # 尝试获取字幕文本
                text = name
                mp_item = item.GetMediaPoolItem()
                if mp_item:
                    mp_props = mp_item.GetClipProperty()
                    if mp_props:
                        clip_name = mp_props.get('Clip Name', '')
                        if clip_name:
                            text = clip_name

                errors.append(
                    f'❌ S{si} {tc}  "{text}"  ({duration}帧)'
                )

    if clamped_count == 0:
        status = f'✅ 通过: {total_subtitles} 条字幕, 无夹帧'
    else:
        status = f'❌ 夹帧: {clamped_count}/{total_subtitles} 条字幕时长 ≤ {SUBTITLE_CLAMP_THRESHOLD} 帧'
    if disabled_count:
        status += f' (跳过 {disabled_count} 条禁用)'

    errors.insert(0, status)
    return errors


# ── 主入口 ──────────────────────────────────────────────


def main():
    resolve = bmd.scriptapp('Resolve')
    if not resolve:
        print('❌ 请先启动 DaVinci Resolve')
        return 1

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print('❌ 请先打开一个项目')
        return 1

    timeline = project.GetCurrentTimeline()
    if not timeline:
        print('❌ 当前项目没有时间线')
        return 1

    # 时间线基本信息
    fps = float(project.GetSetting("timelineFrameRate"))
    tl_width = int(project.GetSetting("timelineResolutionWidth"))
    tl_height = int(project.GetSetting("timelineResolutionHeight"))

    # ── 报告头 ──
    print()
    print('═' * 56)
    print('   📋 时间线检查报告')
    print('═' * 56)
    print(f'   项目: {project.GetName()}')
    print(f'   时间线: {timeline.GetName()}')
    print(f'   分辨率: {tl_width}×{tl_height}  |  帧率: {fps} fps')
    print()

    # ── 执行三项检查 ──
    all_errors = []
    has_failures = False

    # 检查 1：轨道结构
    print('━' * 56)
    print('   ① 轨道结构')
    print('━' * 56)
    track_results = check_track_structure(timeline)
    for r in track_results:
        print(f'      {r}')
        if r.startswith('❌'):
            has_failures = True
    print()

    # 检查 2：黑边
    print('━' * 56)
    print('   ② 黑边检查')
    print('━' * 56)
    border_results = check_black_borders(timeline, tl_width, tl_height, fps)
    for r in border_results:
        print(f'      {r}')
        if r.startswith('❌'):
            has_failures = True
    print()

    # 检查 3：字幕夹帧
    print('━' * 56)
    print('   ③ 字幕夹帧')
    print('━' * 56)
    subtitle_results = check_subtitle_frame_clamping(timeline, fps)
    for r in subtitle_results:
        print(f'      {r}')
        if r.startswith('❌'):
            has_failures = True
    print()

    # ── 总结 ──
    print('═' * 56)
    if has_failures:
        print('   ❌ 检查未通过 — 请修复上述问题后重新检查')
    else:
        print('   ✅ 所有检查通过')
    print('═' * 56)
    print()

    return 1 if has_failures else 0


if __name__ == '__main__':
    sys.exit(main())
