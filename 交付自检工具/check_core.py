# -*- coding: utf-8 -*-
"""
交付自检 — 核心检查逻辑（纯函数，与 UI/CLI 无关）

所有结果统一格式：
    {"status":"pass"|"fail"|"warn", "track":"", "timecode":"", "detail":"",
     "is_summary": True|False}

track / timecode / detail 均为干净独立字段，UI 端无需解析/截取。
"""

from timecode import SMPTE

# 轨道类型 → UI 缩写（与达芬奇界面一致：ST/V/A）
_TRACK_LABEL = {"subtitle": "ST", "video": "V", "audio": "A"}


def _track_short(track_type, index):
    """拼接轨道缩写，如 V1, A10, ST1"""
    return _TRACK_LABEL.get(track_type, track_type[0].upper()) + str(index)


def _make_result(status, track="", timecode="", detail="", is_summary=False):
    """工厂函数，统一构造结果 dict"""
    return {"status": status, "track": track, "timecode": timecode,
            "detail": detail, "is_summary": is_summary}


def check_track_structure(timeline, expected_subtitle=1, expected_video=5, expected_audio=10) -> list:
    """检查字幕/视频/音频轨道数量是否符合模板。

    Returns:
        list[dict]: 每个轨道类型一条结果（无汇总行）
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
            results.append(_make_result("pass", detail=f"{label}轨道: {actual} (通过)"))
        else:
            results.append(_make_result("fail", detail=f"{label}轨道: {actual} (应为 {expected})"))

    return results


def check_subtitle_clamping(timeline, threshold_frames=5, fps=25.0) -> list:
    """检查字幕：① 时长过短 ② 间距夹帧。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    results = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_count == 0:
        results.append(_make_result("warn", detail="无字幕轨道", is_summary=True))
        return results

    issues_short = []
    issues_gap = []
    total_count = 0
    disabled_count = 0

    for si in range(1, subtitle_count + 1):
        track = _track_short("subtitle", si)
        items = timeline.GetItemListInTrack("subtitle", si)
        if not items:
            continue

        sorted_items = sorted(items, key=lambda it: it.GetStart())
        prev_end = None
        prev_name = ""

        for item in sorted_items:
            total_count += 1
            name = item.GetName()
            start_frame = item.GetStart()
            end_frame = item.GetEnd()
            duration = end_frame - start_frame

            try:
                enabled = item.GetClipEnabled()
            except Exception:
                enabled = True
            if enabled is False:
                disabled_count += 1
                continue

            text = name
            try:
                mp_item = item.GetMediaPoolItem()
                if mp_item:
                    mp_props = mp_item.GetClipProperty()
                    if mp_props:
                        n = mp_props.get("Clip Name", "")
                        if n and n != name:
                            text = n
            except Exception:
                pass

            # ① 时长过短
            if duration <= threshold_frames:
                smpte = SMPTE(); smpte.fps = fps; smpte.df = False
                tc = smpte.gettc(start_frame)
                issues_short.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"过短  {text}  ({duration}帧)",
                ))

            # ② 间距夹帧
            if prev_end is not None:
                gap = start_frame - prev_end
                if 0 < gap <= threshold_frames:
                    smpte = SMPTE(); smpte.fps = fps; smpte.df = False
                    tc = smpte.gettc(start_frame)
                    issues_gap.append(_make_result(
                        "fail", track=track, timecode=tc,
                        detail=f"夹帧  {gap} 帧  ({prev_name} → {text})",
                    ))

            prev_end = end_frame
            prev_name = text

    # 汇总
    total_issues = len(issues_short) + len(issues_gap)
    if total_issues == 0:
        parts = [f"共 {total_count} 条字幕, 无异常"]
        if disabled_count:
            parts.append(f"跳过 {disabled_count} 条禁用")
        results.append(_make_result("pass", detail=", ".join(parts), is_summary=True))
    else:
        parts = []
        if issues_short:
            parts.append(f"过短: {len(issues_short)} 条")
        if issues_gap:
            parts.append(f"夹帧: {len(issues_gap)} 处")
        if disabled_count:
            parts.append(f"跳过 {disabled_count} 条禁用")
        results.append(_make_result("fail", detail=", ".join(parts), is_summary=True))
        results.extend(issues_short)
        results.extend(issues_gap)

    return results


def check_disabled_items(timeline, fps=25.0) -> list:
    """检查所有轨道上被禁用的片段（字幕/视频/音频）。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    results = []
    issues = []
    total_count = 0

    for track_type in ["subtitle", "video", "audio"]:
        track_count = timeline.GetTrackCount(track_type)
        for ti in range(1, track_count + 1):
            track = _track_short(track_type, ti)
            items = timeline.GetItemListInTrack(track_type, ti)
            if not items:
                continue

            for item in items:
                total_count += 1
                name = item.GetName()
                start_frame = item.GetStart()

                try:
                    enabled = item.GetClipEnabled()
                except Exception:
                    enabled = True
                if enabled is not False:
                    continue

                text = name
                try:
                    mp_item = item.GetMediaPoolItem()
                    if mp_item:
                        mp_props = mp_item.GetClipProperty()
                        if mp_props:
                            n = mp_props.get("Clip Name", "")
                            if n and n != name:
                                text = n
                except Exception:
                    pass

                smpte = SMPTE(); smpte.fps = fps; smpte.df = False
                tc = smpte.gettc(start_frame)

                issues.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{text}  (已禁用)",
                ))

    if not issues:
        results.append(_make_result("pass",
            detail=f"共 {total_count} 个片段, 无禁用", is_summary=True))
    else:
        results.append(_make_result("fail",
            detail=f"已禁用: {len(issues)} 个片段", is_summary=True))
        results.extend(issues)

    return results


# ── 参考案例（已从注册表移除，保留代码作模板）──

def check_weather(timeline, fps=25.0) -> list:
    """天气检查 — 扩展性参考案例"""
    import random
    name = timeline.GetName()
    seed = sum(ord(c) for c in name)
    rng = random.Random(seed + 42)
    temp = rng.randint(-5, 42)
    hum = rng.randint(10, 99)

    issues = []
    if hum > 80:
        issues.append(_make_result("fail", detail=f"湿度过高: {hum}% (建议除湿)"))
    if temp > 35:
        issues.append(_make_result("fail", detail=f"温度过高: {temp}°C (建议开空调)"))
    if temp < 0:
        issues.append(_make_result("fail", detail=f"温度过低: {temp}°C (建议取暖)"))

    if not issues:
        return [_make_result("pass",
            detail=f"天气适宜: {temp}°C, 湿度 {hum}%", is_summary=True)]

    issues.insert(0, _make_result("fail",
        detail=f"天气异常: {temp}°C, 湿度 {hum}%", is_summary=True))
    return issues
