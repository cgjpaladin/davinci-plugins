# -*- coding: utf-8 -*-
"""
时间线检查 — 核心检查逻辑（纯函数，与 UI/CLI 无关）

所有函数接受达芬奇 API 对象，返回结构化的检查结果列表。
不 import UI 模块，不写文件，不 print。
"""


def check_track_structure(timeline, expected_subtitle=1, expected_video=5, expected_audio=10) -> list:
    """检查字幕/视频/音频轨道数量是否符合模板。

    Args:
        timeline: DaVinci Resolve Timeline 对象
        expected_subtitle: 预期的字幕轨数量
        expected_video: 预期的视频轨数量
        expected_audio: 预期的音频轨数量

    Returns:
        list[dict]: 每个轨道类型一条结果
            {"status": "pass"|"fail", "type": "track", "label": "字幕", "actual": 1, "expected": 1, "message": "..."}
    """
    results = []
    checks = [
        ("字幕", "subtitle", expected_subtitle),
        ("视频", "video", expected_video),
        ("音频", "audio", expected_audio),
    ]

    for label, track_type, expected in checks:
        actual = timeline.GetTrackCount(track_type)
        if actual == expected:
            results.append({
                "status": "pass",
                "type": "track",
                "label": label,
                "actual": actual,
                "expected": expected,
                "message": f"✅ {label}轨道: {actual} (通过)",
            })
        else:
            results.append({
                "status": "fail",
                "type": "track",
                "label": label,
                "actual": actual,
                "expected": expected,
                "message": f"❌ {label}轨道: {actual} (应为 {expected})",
            })

    return results


def check_subtitle_clamping(timeline, threshold_frames=3, fps=25.0) -> list:
    """检查字幕夹帧：① 时长过短的字幕 ② 两个字幕间距过短。

    Args:
        timeline: DaVinci Resolve Timeline 对象
        threshold_frames: 夹帧阈值（帧数），≤N 帧即标记
        fps: 时间线帧率，用于时码转换

    Returns:
        list[dict]:
            第一条为汇总，后续为具体问题
    """
    results = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_count == 0:
        results.append({
            "status": "warn",
            "type": "subtitle",
            "message": "⚠ 无字幕轨道, 跳过夹帧检查",
        })
        return results

    issues_short = []   # 时长过短
    issues_gap = []     # 间距过短
    total_count = 0
    disabled_count = 0

    for si in range(1, subtitle_count + 1):
        items = timeline.GetItemListInTrack("subtitle", si)
        if not items:
            continue

        # 按起始帧排序
        sorted_items = sorted(items, key=lambda it: it.GetStart())

        prev_end = None
        prev_name = ""

        for item in sorted_items:
            total_count += 1
            name = item.GetName()
            start_frame = item.GetStart()
            end_frame = item.GetEnd()
            duration = end_frame - start_frame

            # 跳过禁用字幕
            try:
                enabled = item.GetClipEnabled()
            except Exception:
                enabled = True
            if enabled is False:
                disabled_count += 1
                continue

            # 尝试获取字幕文本
            text = name
            try:
                mp_item = item.GetMediaPoolItem()
                if mp_item:
                    mp_props = mp_item.GetClipProperty()
                    if mp_props:
                        clip_name = mp_props.get("Clip Name", "")
                        if clip_name and clip_name != name:
                            text = clip_name
            except Exception:
                pass

            # ① 时长过短
            if duration <= threshold_frames:
                from timecode import SMPTE
                smpte = SMPTE()
                smpte.fps = fps
                smpte.df = False
                tc = smpte.gettc(start_frame)

                issues_short.append({
                    "status": "fail",
                    "type": "subtitle_short",
                    "track": f"S{si}",
                    "timecode": tc,
                    "name": text,
                    "duration_frames": duration,
                    "message": f"❌ S{si} {tc}  {text}  ({duration}帧)",
                })

            # ② 间距过短: 当前字幕开头 - 上一个字幕结尾 ≤ 阈值
            if prev_end is not None:
                gap = start_frame - prev_end
                if 0 < gap <= threshold_frames:
                    from timecode import SMPTE
                    smpte = SMPTE()
                    smpte.fps = fps
                    smpte.df = False
                    tc_prev = smpte.gettc(prev_end)
                    tc_curr = smpte.gettc(start_frame)

                    issues_gap.append({
                        "status": "fail",
                        "type": "subtitle_gap",
                        "track": f"S{si}",
                        "timecode_prev": tc_prev,
                        "timecode_curr": tc_curr,
                        "gap_frames": gap,
                        "prev_name": prev_name,
                        "curr_name": text,
                        "message": f"❌ S{si} {tc_prev}→{tc_curr}  间距 {gap} 帧  ({prev_name} → {text})",
                    })

            prev_end = end_frame
            prev_name = text

    # 汇总
    total_issues = len(issues_short) + len(issues_gap)
    if total_issues == 0:
        summary_msg = f"✅ 通过: {total_count} 条字幕, 无夹帧"
    else:
        parts = []
        if issues_short:
            parts.append(f"{len(issues_short)} 条时长≤{threshold_frames}帧")
        if issues_gap:
            parts.append(f"{len(issues_gap)} 处间距≤{threshold_frames}帧")
        summary_msg = f'❌ 夹帧: {", ".join(parts)} / 共 {total_count} 条字幕'

    if disabled_count:
        summary_msg += f" (跳过 {disabled_count} 条禁用)"

    results.append({"status": "fail" if total_issues > 0 else "pass",
                    "type": "subtitle",
                    "message": summary_msg})
    results.extend(issues_short)
    results.extend(issues_gap)

    return results
