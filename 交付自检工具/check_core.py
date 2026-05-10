# -*- coding: utf-8 -*-
"""
交付自检 — 核心检查逻辑（纯函数，与 UI/CLI 无关）

所有结果统一格式：
    {"status":"pass"|"fail"|"warn", "track":"", "timecode":"", "detail":"",
     "is_summary": True|False}

track / timecode / detail 均为干净独立字段，UI 端无需解析/截取。
"""

from timecode import SMPTE
from config import AUDIO_TRACK_PRESET, VIDEO_TRACK_PRESET, SUBTITLE_TRACK_PRESET
import json
import os
import re

# ── 缓存：避免重复 IPC ──
_items_cache = {}
_props_cache = {}  # item_uid → {enabled, name, mp, mp_props, property, channel_mapping}
_smpte_cache = {}  # fps → SMPTE 实例
_censor_cache = {}  # path → [words]

def clear_censor_cache(path=None):
    """清除违禁词缓存。path=None → 清全部，path=str → 清指定文件。"""
    global _censor_cache
    if path is None:
        _censor_cache.clear()
    else:
        _censor_cache.pop(path, None)

def preload_timeline_items(timeline):
    """预加载所有轨道的片段列表及常用属性，避免重复 IPC。"""
    global _items_cache, _props_cache
    _items_cache.clear()
    _props_cache.clear()
    for track_type in ["subtitle", "video", "audio"]:
        count = timeline.GetTrackCount(track_type)
        for ti in range(1, count + 1):
            items = timeline.GetItemListInTrack(track_type, ti)
            _items_cache[(track_type, ti)] = items
            if items:
                for it in items:
                    uid = it.GetUniqueId()
                    try:
                        enabled = it.GetClipEnabled()
                    except Exception:
                        enabled = True
                    try:
                        mp = it.GetMediaPoolItem()
                    except Exception:
                        mp = None
                    try:
                        props = it.GetProperty()
                    except Exception:
                        props = {}
                    cached = {"enabled": enabled, "mp": mp, "props": props or {}}
                    # 缓存片段名 + 媒体池名 + 分辨率 + fps + 时间线位置 + 源帧范围
                    try:
                        cached["name"] = it.GetName()
                    except Exception:
                        pass
                    try:
                        if mp:
                            mp_props = mp.GetClipProperty()
                            if mp_props:
                                cached["mp_name"] = mp_props.get("Clip Name", "")
                                cached["mp_resolution"] = mp_props.get("Resolution", "")
                                cached["mp_fps"] = mp_props.get("FPS", "")
                    except Exception:
                        pass
                    try:
                        cached["start"] = it.GetStart()
                        cached["end"] = it.GetEnd()
                    except Exception:
                        pass
                    if track_type == "video":
                        try:
                            cached["source_start"] = it.GetSourceStartFrame()
                            cached["source_end"] = it.GetSourceEndFrame()
                        except Exception:
                            pass
                    if track_type == "audio":
                        try:
                            raw = it.GetSourceAudioChannelMapping()
                            if isinstance(raw, str):
                                try:
                                    import json as _json
                                    cached["channel_mapping"] = _json.loads(raw)
                                except Exception:
                                    cached["channel_mapping"] = raw
                            else:
                                cached["channel_mapping"] = raw
                        except Exception:
                            cached["channel_mapping"] = None
                    _props_cache[uid] = cached

def _get_cached(item, key, default=None):
    """从缓存读取 item 属性。"""
    try:
        uid = item.GetUniqueId()
        return _props_cache.get(uid, {}).get(key, default)
    except Exception:
        return default

def _get_smpte(fps):
    """获取缓存的 SMPTE 实例。"""
    if fps not in _smpte_cache:
        smpte = SMPTE()
        smpte.fps = fps
        smpte.df = False
        _smpte_cache[fps] = smpte
    return _smpte_cache[fps]

def _get_items(timeline, track_type, ti):
    """获取轨道片段（优先缓存）。"""
    key = (track_type, ti)
    if key in _items_cache:
        return _items_cache[key]
    return timeline.GetItemListInTrack(track_type, ti)

# 轨道类型 → UI 缩写（与达芬奇界面一致：ST/V/A）
_TRACK_LABEL = {"subtitle": "ST", "video": "V", "audio": "A"}

def _in_io_range(it, io_range):
    """判断片段是否在 IO 范围内。io_range=None → 全通过。"""
    if io_range is None:
        return True
    io_in, io_out = io_range
    return _get_cached(it, "start", 0) < io_out and _get_cached(it, "end", 0) > io_in



def _track_short(track_type, index):
    """拼接轨道缩写，如 V1, A10, ST1"""
    return _TRACK_LABEL.get(track_type, track_type[0].upper()) + str(index)


def _make_result(status, track="", timecode="", detail="", reason="", is_summary=False):
    """工厂函数，统一构造结果 dict"""
    return {"status": status, "track": track, "timecode": timecode,
            "detail": detail, "reason": reason, "is_summary": is_summary}


def _check_track_details(timeline, track_type, prefix, preset_list, results):
    """通用轨道详情检查：名称 + 启用（+ 子类型如果有）。

    preset_list 每项: {"name": str, "enabled": bool, "subtype": str (optional)}
    只检查实际存在的轨道——缺失轨由数量总览行覆盖，不重复列出。
    每个问题独立一行，detail=当前状态，reason=应为值。
    """
    actual_count = timeline.GetTrackCount(track_type)
    for idx, preset in enumerate(preset_list):
        ti = idx + 1
        if ti > actual_count:
            continue
        track_label = f"{prefix}{ti}"
        preset_name = preset["name"]

        actual_name = timeline.GetTrackName(track_type, ti)
        if actual_name != preset_name:
            results.append(_make_result("fail", track=track_label,
                detail=f"{preset_name}: 当前 \"{actual_name}\"",
                reason=f"应为 \"{preset_name}\""))

        if "subtype" in preset:
            actual_sub = timeline.GetTrackSubType(track_type, ti)
            if actual_sub != preset["subtype"]:
                results.append(_make_result("fail", track=track_label,
                    detail=f"{preset_name}: 当前 {actual_sub}",
                    reason=f"应为 {preset['subtype']}"))

        actual_enabled = timeline.GetIsTrackEnabled(track_type, ti)
        if actual_enabled != preset["enabled"]:
            state = "禁用" if actual_enabled is False else "启用"
            expected_state = "启用" if preset["enabled"] else "禁用"
            results.append(_make_result("fail", track=track_label,
                detail=f"{preset_name}: {state}",
                reason=f"应为 {expected_state}"))


def check_track_structure(timeline, expected_subtitle=1, expected_video=5, expected_audio=10,
                          audio_preset=None, video_preset=None, subtitle_preset=None) -> list:
    """检查字幕/视频/音频轨道数量 + 各轨名称/启用状态。

    音频轨：数量不对 → 只提示重新应用预设，不列详情。
           数量对但名称/启用不对 → 列出每轨差异。

    Returns:
        list[dict]: 轨道数量 + 各轨详情（pass 不列出详情）
    """
    if audio_preset is None:
        audio_preset = AUDIO_TRACK_PRESET
    if video_preset is None:
        video_preset = VIDEO_TRACK_PRESET
    if subtitle_preset is None:
        subtitle_preset = SUBTITLE_TRACK_PRESET

    results = []

    # ── 轨道数量 ──
    for label, track_type, expected in [
        ("字幕", "subtitle", expected_subtitle),
        ("视频", "video",    expected_video),
    ]:
        actual = timeline.GetTrackCount(track_type)
        if actual == expected:
            results.append(_make_result("pass", detail=f"{label}轨道: {actual} (通过)"))
        else:
            results.append(_make_result("fail",
                detail=f"{label}轨道: 当前 {actual} 轨", reason=f"应为 {expected} 轨"))

    actual_audio = timeline.GetTrackCount("audio")
    if actual_audio == expected_audio:
        # 数量对 → 再检查名称是否都对得上
        names_ok = True
        for idx, preset in enumerate(audio_preset):
            if idx + 1 > actual_audio:
                break
            if timeline.GetTrackName("audio", idx + 1) != preset["name"]:
                names_ok = False
                break
        if names_ok:
            results.append(_make_result("pass", detail=f"音频轨道: {actual_audio} (通过)"))
        else:
            results.append(_make_result("fail",
                detail=f"音频轨道: 当前 {actual_audio} 轨，但轨道名称与预设不符",
                reason="请重新应用总线预设"))
    else:
        results.append(_make_result("fail",
            detail=f"音频轨道: 当前 {actual_audio} 轨",
            reason=f"应为 {expected_audio} 轨，请重新应用总线预设"))

    # ── 各轨详情 ──
    _check_track_details(timeline, "subtitle", "ST", subtitle_preset, results)
    _check_track_details(timeline, "video",    "V",  video_preset, results)

    # 音频轨：只有数量+名称都对时才列详情（否则=预设没正确应用，列详情无意义）
    if actual_audio == expected_audio and names_ok:
        _check_track_details(timeline, "audio", "A", audio_preset, results)

    return results


def check_subtitle_clamping(timeline, threshold_frames=5, fps=25.0, io_range=None) -> list:
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
        items = _get_items(timeline, "subtitle", si)
        if not items:
            continue

        sorted_items = sorted(items, key=lambda it: _get_cached(it, "start", 0))
        prev_end = None
        prev_name = ""

        for item in sorted_items:
            if not _in_io_range(item, io_range):
                continue
            total_count += 1
            name = _get_cached(item, "name", "")
            start_frame = _get_cached(item, "start", 0)
            end_frame = _get_cached(item, "end", 0)
            duration = end_frame - start_frame

            if _get_cached(item, "enabled", True) is False:
                disabled_count += 1
                continue

            text = name
            mp_name = _get_cached(item, "mp_name", "")
            if mp_name and mp_name != name:
                text = mp_name

            # ① 时长过短
            if duration <= threshold_frames:
                smpte = _get_smpte(fps)
                tc = smpte.gettc(start_frame)
                issues_short.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{text}  {duration}帧，过短",
                ))

            # ② 间距夹帧
            if prev_end is not None:
                gap = start_frame - prev_end
                if 0 < gap <= threshold_frames:
                    smpte = _get_smpte(fps)
                    tc = smpte.gettc(start_frame)
                    issues_gap.append(_make_result(
                        "fail", track=track, timecode=tc,
                        detail=f"{prev_name} → {text}  {gap}帧，夹帧",
                    ))

            prev_end = end_frame
            prev_name = text

    # 汇总
    total_issues = len(issues_short) + len(issues_gap)
    if total_issues == 0:
        parts = ["无异常"]
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


def check_disabled_items(timeline, fps=25.0, io_range=None) -> list:
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
            items = _get_items(timeline, track_type, ti)
            if not items:
                continue

            for item in items:
                if not _in_io_range(item, io_range):
                    continue
                total_count += 1
                if _get_cached(item, "enabled", True) is not False:
                    continue
                name = _get_clip_name(item)
                start_frame = _get_cached(item, "start", 0)

                smpte = _get_smpte(fps)
                tc = smpte.gettc(start_frame)

                issues.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{name}，未启用",
                ))

    if not issues:
        results.append(_make_result("pass",
            detail="无禁用", is_summary=True))
    else:
        results.append(_make_result("fail",
            detail=f"未启用: {len(issues)} 个片段", is_summary=True))
        results.extend(issues)

    return results


def _get_clip_name(item):
    """获取片段显示名：优先 MediaPoolItem 的 Clip Name，否则用 TimelineItem 名"""
    mp_name = _get_cached(item, "mp_name")
    if mp_name:
        name = _get_cached(item, "name", "")
        if mp_name != name:
            return mp_name
    return _get_cached(item, "name", "") or item.GetName()


def check_black_frames(timeline, fps=25.0, io_range=None) -> list:
    """检测黑帧：合并所有视频轨的有效片段后，找未被覆盖的时间段。

    有效片段条件：启用 + 不透明度=100 + 有 MediaPoolItem。
    禁用的、不透明度≠100、调整片段不计入覆盖，并记录原因+片段名。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    valid_intervals = []      # 有效覆盖: [(start, end)]
    invalid_intervals = []    # 无效覆盖: [(start, end, reason, track, name)]
    video_count = timeline.GetTrackCount("video")

    if video_count == 0:
        return [_make_result("warn", detail="无视频轨道", is_summary=True)]

    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue

        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            s = _get_cached(it, "start", 0)
            e = _get_cached(it, "end", 0)
            name = _get_clip_name(it)

            # 检查禁用
            if _get_cached(it, "enabled", True) is False:
                invalid_intervals.append((s, e, "未启用", track, name))
                continue
            # 检查是否调整片段
            mp = _get_cached(it, "mp")
            if mp is None:
                invalid_intervals.append((s, e, "调整片段/无素材", track, name))
                continue
            # 检查不透明度
            opacity = _get_cached(it, "props", {}).get("Opacity", 100)
            if opacity != 100:
                invalid_intervals.append((s, e, f"不透明度 {opacity}%", track, name))
                continue

            valid_intervals.append((s, e))

    if not valid_intervals:
        tl_end = timeline.GetEndFrame()
        return [
            _make_result("fail", detail="全部片段无效, 整条时间线为黑帧", is_summary=True),
            _make_result("fail", detail=f"全域黑帧  {tl_end} 帧"),
        ]

    # 合并有效区间，找空隙
    valid_intervals.sort()
    merged = []
    for s, e in valid_intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    tl_start = timeline.GetStartFrame()
    tl_end = timeline.GetEndFrame()
    gaps = []  # [(start, end, reason, track, name)]
    prev = tl_start
    for s, e in merged:
        if s > prev:
            reason = "无片段覆盖"
            track = ""
            gap_name = ""
            for is_, ie, ir, it_, in_ in invalid_intervals:
                if is_ < s and ie > prev:
                    reason = ir
                    track = it_
                    gap_name = in_
                    break
            gaps.append((prev, s, reason, track, gap_name))
        prev = max(prev, e)
    if prev < tl_end:
        reason = "无片段覆盖"
        track = ""
        gap_name = ""
        for is_, ie, ir, it_, in_ in invalid_intervals:
            if is_ < tl_end and ie > prev:
                reason = ir
                track = it_
                gap_name = in_
                break
        gaps.append((prev, tl_end, reason, track, gap_name))

    # ── 补充：音频尾部超出视频（用子帧精度）──
    last_video = merged[-1][1] if merged else tl_end
    for ai in range(1, timeline.GetTrackCount("audio") + 1):
        audio_items = _get_items(timeline, "audio", ai)
        if not audio_items:
            continue
        track = f"A{ai}"
        for it in audio_items:
            # 音频用子帧精度算真实尾部
            a_start = _get_cached(it, "start", 0)
            a_dur = it.GetDuration(True)
            a_end_real = a_start + a_dur
            if a_end_real > last_video:
                overrun = round(a_end_real - last_video, 2)
                audio_name = _get_clip_name(it)
                gaps.append((last_video, int(a_end_real) + 1,
                             f"音频超出视频尾 {overrun}帧", track, audio_name))

    if not gaps:
        return [_make_result("pass",
            detail="覆盖完整, 无黑帧",
            is_summary=True)]

    smpte = SMPTE()
    smpte.fps = fps
    smpte.df = False

    results = [_make_result("fail",
        detail=f"黑帧: {len(gaps)} 处空隙",
        is_summary=True)]

    for s, e, gap_reason, track, name in gaps:
        duration = e - s
        tc = smpte.gettc(s)
        if gap_reason == "无片段覆盖":
            detail = f"空白 {duration} 帧"
        elif gap_reason.startswith("音频超出"):
            detail = f"{gap_reason}，{name}" if name else gap_reason
        elif name:
            detail = f"{name}，{gap_reason}"
        else:
            detail = f"{duration} 帧，{gap_reason}"
        results.append(_make_result("fail", timecode=tc, track=track,
                                    detail=detail))

    return results


def check_audio_mono(timeline, fps=25.0, io_range=None) -> list:
    """检测音频片段声道异常：声道静音 / 立体声被压成单声道。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    issues = []
    audio_count = timeline.GetTrackCount("audio")

    for ai in range(1, audio_count + 1):
        items = _get_items(timeline, "audio", ai)
        if not items:
            continue
        track = f"A{ai}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            # 跳过禁用的片段
            if _get_cached(it, "enabled", True) is False:
                continue

            name = _get_clip_name(it)
            start_frame = _get_cached(it, "start", 0)
            ch_map = _get_cached(it, "channel_mapping")
            if not ch_map:
                continue

            smpte = SMPTE()
            smpte.fps = fps
            smpte.df = False
            tc = smpte.gettc(start_frame)

            tm = ch_map.get("track_mapping", {})
            for ch_key, ch_data in tm.items():
                ch_idx = ch_data.get("channel_idx", [])
                ch_type = ch_data.get("type", "")
                ch_muted_flag = ch_data.get("mute", False)

                # ① 声道静音（channel_idx 含 0 或 mute=True）
                if ch_muted_flag or 0 in ch_idx:
                    # 判断左右
                    if len(ch_idx) >= 2 and ch_idx[1] == 0:
                        ch_reason = "右声道静音"
                    elif ch_idx[0] == 0:
                        ch_reason = "左声道静音"
                    else:
                        ch_reason = "声道静音"
                    issues.append(_make_result(
                        "fail", track=track, timecode=tc,
                        detail=f"{name}，{ch_reason}",
                    ))
                    break  # 一片段只报一次

                # ② 立体声源被压成单声道
                embedded = ch_map.get("embedded_audio_channels", 0)
                if embedded >= 2 and ch_type == "mono" and len(ch_idx) == 1:
                    issues.append(_make_result(
                        "fail", track=track, timecode=tc,
                        detail=f"{name}，单声道片段",
                    ))
                    break

    if not issues:
        return [_make_result("pass",
            detail="所有音频声道正常",
            is_summary=True)]

    results = [_make_result("fail",
        detail=f"声道异常: {len(issues)} 处",
        is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_glyph(timeline, fps=25.0, io_range=None) -> list:
    """检测字幕异体字：康熙部首 / 全角拉丁字母。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_count == 0:
        return [_make_result("warn", detail="无字幕轨道", is_summary=True)]

    smpte = SMPTE()
    smpte.fps = fps
    smpte.df = False

    for si in range(1, subtitle_count + 1):
        items = _get_items(timeline, "subtitle", si)
        if not items:
            continue
        track = f"ST{si}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            text = _get_cached(it, "name", "")
            start_frame = _get_cached(it, "start", 0)
            tc = smpte.gettc(start_frame)

            for ch in text:
                cp = ord(ch)
                if 0x2F00 <= cp <= 0x2FDF or 0xFF21 <= cp <= 0xFF3A or 0xFF41 <= cp <= 0xFF5A:
                    issues.append(_make_result("fail", track=track, timecode=tc,
                        detail=f"{repr(text)}，含异体字",
                        reason="请手动删除字幕中的文本，并重新输入"))
                    break  # 一片段只报一条

    if not issues:
        return [_make_result("pass", detail="无异体字", is_summary=True)]

    results = [_make_result("fail", detail=f"异体字: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_linebreak(timeline, fps=25.0, io_range=None) -> list:
    """检测字幕换行：CPL 超限 / 硬换行。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_count == 0:
        return [_make_result("warn", detail="无字幕轨道", is_summary=True)]

    try:
        cpl = int(timeline.GetSetting().get("limitSubtitleCPL", 0))
    except Exception:
        cpl = 0

    smpte = SMPTE()
    smpte.fps = fps
    smpte.df = False

    for si in range(1, subtitle_count + 1):
        items = _get_items(timeline, "subtitle", si)
        if not items:
            continue
        track = f"ST{si}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            text = _get_cached(it, "name", "")
            start_frame = _get_cached(it, "start", 0)
            tc = smpte.gettc(start_frame)

            # 硬换行
            if '\n' in text:
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{repr(text)}，含硬换行"))
                continue

            # CPL 超限
            if cpl > 0 and len(text) > cpl:
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{repr(text)}，超单行 {cpl} 字上限"))
                continue

    if not issues:
        return [_make_result("pass", detail="换行正常", is_summary=True)]

    results = [_make_result("fail", detail=f"换行异常: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_censor(timeline, dict_path, fps=25.0, io_range=None) -> list:
    """检测字幕含违禁词。

    Args:
        dict_path: 违禁词文件路径，一行一词

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    global _censor_cache
    # 加载字典 + 编译正则
    if dict_path not in _censor_cache:
        words = []
        category_map = {}   # word → "cat1 > cat2"
        suggestion_map = {} # word → "sug1 / sug2 / ..."
        if os.path.isfile(dict_path):
            with open(dict_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if not w or w.startswith("#"):
                        continue
                    parts = w.split(",")
                    # 纯单词列表（无逗号，兼容 censor_cn.txt 等）
                    if len(parts) == 1:
                        word = parts[0].strip()
                        if word:
                            words.append((word, [], "", ""))
                        continue
                    # CSV 格式：一级分类,二级分类,违禁词,建议替换1[,建议替换2...]
                    if len(parts) < 3:
                        continue
                    cat1 = parts[0].strip()
                    cat2 = parts[1].strip()
                    word = parts[2].strip()
                    if not word:
                        continue
                    sug_list = [p.strip() for p in parts[3:] if p.strip()]
                    words.append((word, sug_list, cat1, cat2))
                    if cat1 or cat2:
                        cat_str = " > ".join(c for c in (cat1, cat2) if c)
                        category_map[word] = cat_str
                    if sug_list:
                        suggestion_map[word] = " / ".join(sug_list)
        # 编译正则：按长度降序（长词优先匹配）
        word_list = sorted([w for w, *_ in words], key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(w) for w in word_list)) if word_list else None
        _censor_cache[dict_path] = (words, pattern, suggestion_map, category_map)

    censor_words, pattern, suggestion_map, category_map = _censor_cache[dict_path]
    if not pattern:
        return [_make_result("warn", detail="违禁词字典为空", is_summary=True)]

    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_count == 0:
        return [_make_result("warn", detail="无字幕轨道", is_summary=True)]

    smpte = _get_smpte(fps)
    for si in range(1, subtitle_count + 1):
        items = _get_items(timeline, "subtitle", si)
        if not items:
            continue
        track = f"ST{si}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            text = _get_cached(it, "name", "")
            start_frame = _get_cached(it, "start", 0)
            tc = smpte.gettc(start_frame)

            m = pattern.search(text)
            if m:
                word = m.group()
                detail_parts = [f"含违禁词: {word}"]
                cat = category_map.get(word)
                if cat:
                    detail_parts.append(f" [{cat}]")
                reason_text = ""
                sug = suggestion_map.get(word)
                if sug:
                    reason_text = f"建议替换为: {sug}"
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{repr(text)}，{''.join(detail_parts)}",
                    reason=reason_text))

    if not issues:
        return [_make_result("pass", detail="无违禁词", is_summary=True)]

    results = [_make_result("fail", detail=f"违禁词: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_timeline_settings(timeline, project=None, fps=25.0) -> list:
    """检查时间线级别设置：起始时码 / 是否覆盖项目设置。

    Args:
        project: 项目对象，用于对比时间线设置是否覆盖项目默认值

    Returns:
        list[dict]: 每条差异一行
    """
    results = []

    # ── ① 起始时码 ──
    start_tc = timeline.GetStartTimecode()
    if start_tc != "00:00:00:00":
        results.append(_make_result("fail",
            detail=f"起始时码 {start_tc}", reason="应为 00:00:00:00"))
    else:
        results.append(_make_result("pass", detail="起始时码: 00:00:00:00 (通过)"))

    # ── ② 使用项目设置 ──
    if project is None:
        try:
            from fusionscript_loader import bmd
            resolve = bmd.scriptapp("Resolve")
            if resolve:
                project = resolve.GetProjectManager().GetCurrentProject()
        except Exception:
            pass

    if project:
        # 只要任一项返回空字符串 = 未勾选「使用项目设置」
        check_keys = [
            "timelineFrameRate",
            "timelinePlaybackFrameRate",
            "timelineResolutionWidth",
            "colorScienceMode",
            "superScale",
        ]
        unchecked = False
        for key in check_keys:
            pv = project.GetSetting(key)
            tv = timeline.GetSetting(key)
            if pv is not None and pv != "" and (tv is None or tv == ""):
                unchecked = True
                break

        if unchecked:
            results.append(_make_result("fail",
                detail="未使用项目设置", reason="应勾选「使用项目设置」"))
        else:
            results.append(_make_result("pass", detail="使用项目设置 (通过)"))
    else:
        results.append(_make_result("warn", detail="无法对比项目设置"))

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


def check_black_borders(timeline, project=None, fps=25.0, io_range=None) -> list:
    """检测视频轨可见片段的黑边：缩放不足、位移、旋转导致的未覆盖区域。"""
    import math
    issues = []
    video_count = timeline.GetTrackCount("video")
    if video_count == 0:
        return [_make_result("warn", detail="无视频轨道", is_summary=True)]
    timeline_w, timeline_h = 1920, 1080
    if project:
        try:
            timeline_w = int(project.GetSetting("timelineResolutionWidth") or timeline_w)
            timeline_h = int(project.GetSetting("timelineResolutionHeight") or timeline_h)
        except: pass
    try:
        tl_w = timeline.GetSetting("timelineResolutionWidth")
        tl_h = timeline.GetSetting("timelineResolutionHeight")
        if tl_w: timeline_w = int(tl_w)
        if tl_h: timeline_h = int(tl_h)
    except: pass
    smpte = _get_smpte(fps)
    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items: continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range): continue
            if _get_cached(it, "enabled", True) is False: continue
            if _get_cached(it, "mp") is None: continue
            res_str = _get_cached(it, "mp_resolution", "")
            if not res_str or "x" not in res_str: continue
            try: src_w, src_h = map(int, res_str.split("x"))
            except: continue
            props = _get_cached(it, "props", {})
            if not props: continue
            zoom_x = float(props.get("ZoomX", 1.0))
            zoom_y = float(props.get("ZoomY", 1.0))
            pan = float(props.get("Pan", 0.0))
            tilt = float(props.get("Tilt", 0.0))
            rot = math.radians(float(props.get("RotationAngle", 0.0)))
            cx = timeline_w / 2.0 + pan
            cy = timeline_h / 2.0 + tilt
            src_ratio = src_w / src_h if src_h else 1
            tl_ratio = timeline_w / timeline_h if timeline_h else 1
            fit_scale = max(timeline_w / src_w, timeline_h / src_h) if abs(src_ratio - tl_ratio) < 0.02 else 1.0
            eff_w = src_w * fit_scale * zoom_x
            eff_h = src_h * fit_scale * zoom_y
            cos_r_raw = math.cos(rot); sin_r_raw = math.sin(rot)
            hw, hh = eff_w / 2.0, eff_h / 2.0
            has_gap = False
            for tx, ty in [(0, 0), (timeline_w, 0), (timeline_w, timeline_h), (0, timeline_h)]:
                dx, dy = tx - cx, ty - cy
                lx = dx * cos_r_raw + dy * sin_r_raw
                ly = -dx * sin_r_raw + dy * cos_r_raw
                if abs(lx) > hw or abs(ly) > hh:
                    has_gap = True; break
            if not has_gap: continue
            name = _get_clip_name(it)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，有黑边", reason="适当调整以规避黑边"))
    if not issues:
        return [_make_result("pass", detail="无黑边", is_summary=True)]
    results = [_make_result("fail", detail=f"黑边: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_speed(timeline, project_fps=25.0, io_range=None) -> list:
    """检测视频轨片段变速问题：慢放但未使用光流或帧混合。"""
    issues = []
    video_count = timeline.GetTrackCount("video")
    if video_count == 0:
        return [_make_result("warn", detail="无视频轨道", is_summary=True)]
    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items: continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range): continue
            if _get_cached(it, "enabled", True) is False: continue
            if _get_cached(it, "mp") is None: continue
            t_dur = _get_cached(it, "end", 0) - _get_cached(it, "start", 0)
            if t_dur <= 0: continue
            s_dur = abs(_get_cached(it, "source_end", 0) - _get_cached(it, "source_start", 0))
            if s_dur <= 0: continue
            src_fps = float(_get_cached(it, "mp_fps", project_fps) or project_fps)
            retime = int(_get_cached(it, "props", {}).get("RetimeProcess", 0))
            tl_sec = t_dur / project_fps
            src_sec = s_dur / src_fps
            speed = src_sec / tl_sec * 100
            threshold = min(project_fps / src_fps, 1.0) * 100
            # 容忍 1% 浮点误差，避免 speed=99.6 显示为 100% 却报变速
            if speed < threshold - 1.0 and retime not in (2, 3):
                name = _get_clip_name(it)
                smpte = _get_smpte(project_fps)
                tc = smpte.gettc(_get_cached(it, "start", 0))
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{name}，速度为{speed:.0f}%",
                    reason="调整变速，或使用帧混合/光流法"))
    if not issues:
        return [_make_result("pass", detail="变速正常", is_summary=True)]
    results = [_make_result("fail", detail=f"变速: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_video_clamping(timeline, threshold_frames=1, fps=25.0, io_range=None) -> list:
    """检测视频轨夹帧：启用的视频片段时长 ≤ X 帧。"""
    issues = []
    video_count = timeline.GetTrackCount("video")
    if video_count == 0:
        return [_make_result("warn", detail="无视频轨道", is_summary=True)]
    smpte = _get_smpte(fps)
    checked = 0
    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items: continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range): continue
            if _get_cached(it, "enabled", True) is False: continue
            if _get_cached(it, "mp") is None: continue
            checked += 1
            duration = _get_cached(it, "end", 0) - _get_cached(it, "start", 0)
            if duration <= threshold_frames:
                name = _get_clip_name(it)
                tc = smpte.gettc(_get_cached(it, "start", 0))
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{name}，仅 {duration} 帧，时长过短",
                    reason="检查是否夹帧"))
    if not issues:
        return [_make_result("pass",
            detail="无夹帧" if checked else "无可检片段", is_summary=True)]
    results = [_make_result("fail", detail=f"夹帧: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results
