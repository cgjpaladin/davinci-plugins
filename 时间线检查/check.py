#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间线检查 — CLI 入口

用法（达芬奇运行时）：
    python3 check.py                        # 默认阈值
    python3 check.py --track 1,5,10         # 轨道模板：字幕,视频,音频
    python3 check.py --clamp 3               # 夹帧阈值
    python3 check.py --only track            # 只检查轨道
    python3 check.py --only subtitle         # 只检查字幕
    python3 check.py --no-track --no-subtitle  # 跳过某项
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from fusionscript_loader import bmd
from timecode import SMPTE

from config import (
    DEFAULT_CLAMP_THRESHOLD,
    DEFAULT_SUBTITLE_TRACKS,
    DEFAULT_VIDEO_TRACKS,
    DEFAULT_AUDIO_TRACKS,
    __version__,
)
from core import check_track_structure, check_subtitle_clamping


def parse_args():
    p = argparse.ArgumentParser(description="时间线检查工具")
    p.add_argument("--track", type=str, default=None,
                   help="轨道模板: 字幕,视频,音频 (如 1,5,10)")
    p.add_argument("--clamp", type=int, default=DEFAULT_CLAMP_THRESHOLD,
                   help=f"夹帧阈值 (默认 {DEFAULT_CLAMP_THRESHOLD})")
    p.add_argument("--only", type=str, choices=["track", "subtitle"], default=None,
                   help="仅检查指定项")
    p.add_argument("--no-track", action="store_true", help="跳过轨道检查")
    p.add_argument("--no-subtitle", action="store_true", help="跳过字幕检查")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    return p.parse_args()


def _frame_to_tc(frames, fps):
    smpte = SMPTE()
    smpte.fps = fps
    smpte.df = False
    return smpte.gettc(frames)


def main():
    args = parse_args()

    resolve = bmd.scriptapp("Resolve")
    if not resolve:
        print("❌ 请先启动 DaVinci Resolve", file=sys.stderr)
        return 1

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print("❌ 请先打开一个项目", file=sys.stderr)
        return 1

    timeline = project.GetCurrentTimeline()
    if not timeline:
        print("❌ 当前项目没有时间线", file=sys.stderr)
        return 1

    fps = float(project.GetSetting("timelineFrameRate"))

    # 解析轨道模板
    if args.track:
        parts = args.track.split(",")
        if len(parts) != 3:
            print("❌ --track 格式: 字幕,视频,音频 (如 1,5,10)", file=sys.stderr)
            return 1
        exp_sub, exp_vid, exp_aud = map(int, parts)
    else:
        exp_sub, exp_vid, exp_aud = DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS

    # 确定检查范围
    do_track = do_subtitle = True
    if args.only == "track":
        do_subtitle = False
    elif args.only == "subtitle":
        do_track = False
    if args.no_track:
        do_track = False
    if args.no_subtitle:
        do_subtitle = False

    all_results = []
    has_failures = False

    if do_track:
        results = check_track_structure(timeline, exp_sub, exp_vid, exp_aud)
        all_results.append({"section": "轨道结构", "results": results})
        for r in results:
            if r["status"] == "fail":
                has_failures = True

    if do_subtitle:
        results = check_subtitle_clamping(timeline, args.clamp, fps)
        all_results.append({"section": "字幕夹帧", "results": results})
        for r in results:
            if r["status"] == "fail":
                has_failures = True

    # 输出
    if args.json:
        import json
        output = {
            "project": project.GetName(),
            "timeline": timeline.GetName(),
            "fps": fps,
            "has_failures": has_failures,
            "checks": all_results,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        print()
        print(f"项目: {project.GetName()}")
        print(f"时间线: {timeline.GetName()}")
        print(f"帧率: {fps} fps")
        print()

        for section in all_results:
            print(f"── {section['section']} ──")
            for r in section["results"]:
                print(f"  {r['message']}")
            print()

        if has_failures:
            print("❌ 检查未通过")
        else:
            print("✅ 所有检查通过")

    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
