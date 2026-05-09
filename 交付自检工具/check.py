#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交付自检 — CLI 入口

用法（达芬奇运行时）：
    python3 check.py                        # 默认阈值
    python3 check.py --track 1,5,10         # 轨道模板：字幕,视频,音频
    python3 check.py --clamp 3               # 夹帧阈值
    python3 check.py --only track            # 只检查轨道
    python3 check.py --only subtitle         # 只检查字幕
    python3 check.py --json                  # JSON 输出
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))

from config import (
    DEFAULT_CLAMP_THRESHOLD,
    DEFAULT_SUBTITLE_TRACKS,
    DEFAULT_VIDEO_TRACKS,
    DEFAULT_AUDIO_TRACKS,
    __version__,
)
from check_core import check_track_structure, check_subtitle_clamping, check_disabled_items, check_black_frames
from fusionscript_loader import bmd

# ── CLI 检查注册表 ──
# run_fn(timeline, fps, args) — 统一签名
def _cli_run_track(timeline, fps, args):
    return check_track_structure(timeline, args.track_sub, args.track_vid, args.track_aud)

def _cli_run_subtitle(timeline, fps, args):
    return check_subtitle_clamping(timeline, args.clamp, fps)

def _cli_run_disabled(timeline, fps, args):
    return check_disabled_items(timeline, fps)

def _cli_run_black_frame(timeline, fps, args):
    return check_black_frames(timeline, fps)

CLI_CHECKS = [
    {"id": "track",    "section": "轨道结构", "fn": _cli_run_track},
    {"id": "subtitle", "section": "字幕长度", "fn": _cli_run_subtitle},
    {"id": "disabled", "section": "启用/禁用", "fn": _cli_run_disabled},
    {"id": "black",    "section": "黑帧检测", "fn": _cli_run_black_frame},
]


def parse_args():
    p = argparse.ArgumentParser(description="交付自检工具")
    p.add_argument("--track", type=str, default=None,
                   help="轨道模板: 字幕,视频,音频 (如 1,5,10)")
    p.add_argument("--clamp", type=int, default=DEFAULT_CLAMP_THRESHOLD,
                   help=f"夹帧/过短阈值 (默认 {DEFAULT_CLAMP_THRESHOLD})")
    p.add_argument("--only", type=str, choices=["track", "subtitle", "black"], default=None,
                   help="仅检查指定项")
    p.add_argument("--no-track", action="store_true", help="跳过轨道检查")
    p.add_argument("--no-subtitle", action="store_true", help="跳过字幕检查")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    return p.parse_args()


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

    # 轨道模板 — 挂在 args 上，统一传给 run_fn
    if args.track:
        parts = args.track.split(",")
        if len(parts) != 3:
            print("❌ --track 格式: 字幕,视频,音频 (如 1,5,10)", file=sys.stderr)
            return 1
        args.track_sub, args.track_vid, args.track_aud = map(int, parts)
    else:
        args.track_sub, args.track_vid, args.track_aud = \
            DEFAULT_SUBTITLE_TRACKS, DEFAULT_VIDEO_TRACKS, DEFAULT_AUDIO_TRACKS

    # 确定要跑哪些检查
    run_ids = set(c["id"] for c in CLI_CHECKS)
    if args.only == "track":
        run_ids = {"track"}
    elif args.only == "subtitle":
        run_ids = {"subtitle", "disabled"}
    elif args.only == "black":
        run_ids = {"black"}
    if args.no_track:
        run_ids.discard("track")
    if args.no_subtitle:
        run_ids.discard("subtitle")
        run_ids.discard("disabled")

    all_results = []
    has_failures = False

    for check in CLI_CHECKS:
        if check["id"] not in run_ids:
            continue

        results = check["fn"](timeline, fps, args)

        all_results.append({"section": check["section"], "results": results})
        for r in results:
            if r["status"] == "fail":
                has_failures = True

    # 输出
    if args.json:
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
                if r.get("is_summary"):
                    print(f"  {r['detail']}")
                else:
                    track = r.get("track", "")
                    tc = r.get("timecode", "")
                    prefix = f"{track} {tc}  " if track or tc else ""
                    print(f"  {prefix}{r['detail']}")
            print()

        if has_failures:
            print("❌ 检查未通过")
        else:
            print("✅ 所有检查通过")

    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
