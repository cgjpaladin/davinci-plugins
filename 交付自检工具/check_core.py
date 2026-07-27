# -*- coding: utf-8 -*-
"""
交付自检 — 核心检查逻辑（纯函数，与 UI/CLI 无关）

所有结果统一格式：
    {"status":"pass"|"fail"|"warn", "track":"", "timecode":"", "detail":"",
     "is_summary": True|False}

track / timecode / detail 均为干净独立字段，UI 端无需解析/截取。
"""

from timecode import SMPTE
from config import AUDIO_TRACK_PRESET, VIDEO_TRACK_PRESET, SUBTITLE_TRACK_PRESET, IS_PERSONAL as _IS_PERSONAL
from camera_detect import is_camera_footage
import json
import os
import re

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TAIL_KW = ("未完待续", "定格转场", "全剧终")

# ── 缓存：避免重复 IPC ──
_items_cache: dict = {}
_props_cache: dict = {}  # item_uid → {enabled, name, mp, mp_props, property, channel_mapping}
_smpte_cache: dict = {}  # fps → SMPTE 实例
_censor_cache: dict = {}  # path → [words]

def clear_censor_cache(path=None):
    """清除违禁词缓存。path=None → 清全部，path=str → 清指定文件。"""
    global _censor_cache
    if path is None:
        _censor_cache.clear()
    else:
        _censor_cache.pop(path, None)


def preload_timeline_items(timeline, track_types=None):
    """预加载轨道片段列表及常用属性，避免重复 IPC。

    Args:
        track_types: 要预加载的轨道类型列表，None=全部 ["subtitle","video","audio"]
                    传空列表 [] 只清缓存不预加载
    """
    global _items_cache, _props_cache
    _items_cache.clear()
    _props_cache.clear()
    _clear_clip_files_cache()

    if track_types is None:
        track_types = ["subtitle", "video", "audio"]

    # 未预加载的轨道初始化为空列表（_get_items 不再回退 API 调用）
    all_types = ["subtitle", "video", "audio"]
    for tt in all_types:
        for ti in range(1, timeline.GetTrackCount(tt) + 1):
            if tt not in track_types:
                _items_cache[(tt, ti)] = []

    for track_type in track_types:
        count = timeline.GetTrackCount(track_type)
        for ti in range(1, count + 1):
            items = timeline.GetItemListInTrack(track_type, ti) or []
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
                        props = it.GetProperty() or {}
                    except Exception:
                        props = {}
                    # GetProperty 在某些版本返回 None → 用 GetClipProperty 逐字段兜底
                    if not props or not props.get("ZoomX"):
                        for key in ("ZoomX", "ZoomY", "Pan", "Tilt", "RotationAngle",
                                    "RetimeProcess", "Opacity"):
                            try:
                                v = it.GetClipProperty(key)
                                if v is not None:
                                    props[key] = v
                            except Exception:
                                pass
                    cached = {"enabled": enabled, "mp": mp, "props": props}
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
                            cached["audio_dur"] = it.GetDuration(True) or 0
                        except Exception:
                            cached["audio_dur"] = 0
                        try:
                            raw = it.GetSourceAudioChannelMapping()
                            if isinstance(raw, str):
                                try:
                                    cached["channel_mapping"] = json.loads(raw)
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
    """获取轨道片段（缓存优先；未预加载的轨道返回空列表）。"""
    key = (track_type, ti)
    if key in _items_cache:
        return _items_cache[key]
    return timeline.GetItemListInTrack(track_type, ti) or []

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


def _check_track_empty(count, track_label):
    """轨道为空时返回 fail summary，否则返回 None"""
    if count == 0:
        return [_make_result("fail", detail=f"无{track_label}轨道", is_summary=True)]
    return None

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

    音频轨三层检查（逐级递进）：
      ① Fairlight 预设文件是否存在
      ② 预设文件 MD5 是否与参考版本一致（防旧版本）
      ③ 轨道名称/数量是否匹配（推断是否正确应用到时间线）

    Returns:
        list[dict]: 轨道数量 + 各轨详情（pass 不列出详情）
    """
    import hashlib

    # 个人版跳过（轨数/轨名/Fairlight 均为公司预设）
    if _IS_PERSONAL:
        return [_make_result("pass", detail="轨道结构: 个人版已跳过（轨数/轨名/Fairlight 不可用）", is_summary=True)]

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
            results.append(_make_result("pass", detail=f"{label}轨道: {actual} (通过)", is_summary=True))
        else:
            results.append(_make_result("fail",
                detail=f"{label}轨道: 当前 {actual} 轨", reason=f"应为 {expected} 轨", is_summary=True))

    # ═══ 音频检查 ═══
    actual_audio = timeline.GetTrackCount("audio")

    # ① MD5 校验预设文件（缺失/版本不对 = 同一出口）
    preset_path = os.path.expanduser(
        "~/Library/Preferences/Blackmagic Design/DaVinci Resolve/"
        "Fairlight/Presets/CONSOLE_FLEXI/交付总线设置.dat")
    _PRESET_HASH = "eb3ad5485026fa8e568608638d118a2d"

    try:
        with open(preset_path, "rb") as f:
            actual_hash = hashlib.md5(f.read()).hexdigest()
        if actual_hash != _PRESET_HASH:
            status = "warn" if _IS_PERSONAL else "fail"
            results.append(_make_result(status,
                detail="Fairlight 预设: 版本过旧",
                reason="交付总线设置.dat 与参考版本不一致，请更新预设文件"))
        else:
            results.append(_make_result("pass",
                detail="Fairlight 预设: 版本正确 (MD5 校验通过)"))
    except Exception:
        results.append(_make_result("fail",
            detail="Fairlight 预设: 文件缺失或无法读取",
            reason=f"请确保 {preset_path} 存在且为最新版本"))

    # ③ 轨道名称/数量（推断是否正确应用到时间线）
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

    for si in range(1, 2):  # 仅 ST1（主力字幕轨）
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
                    reason="请检查字幕是否夹帧",
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
                        reason="请调整字幕间距",
                    ))

            prev_end = end_frame
            prev_name = text

    # 汇总
    total_issues = len(issues_short) + len(issues_gap)
    if total_issues == 0:
        parts = ["无异常"]
        if disabled_count:
            parts.append(f"跳过 {disabled_count} 条禁用")
        results.append(_make_result("pass", detail="字幕时长: 全部通过", is_summary=True))
    else:
        parts = []
        if issues_short:
            parts.append(f"过短: {len(issues_short)} 条")
        if issues_gap:
            parts.append(f"夹帧: {len(issues_gap)} 处")
        if disabled_count:
            parts.append(f"跳过 {disabled_count} 条禁用")
        results.append(_make_result("fail", detail=f"字幕时长: {total_issues} 处", is_summary=True))
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
                    reason="请在时间线上启用该片段",
                ))

    if not issues:
        results.append(_make_result("pass",
            detail="启用/禁用: 全部通过", is_summary=True))
    else:
        results.append(_make_result("fail",
            detail=f"启用/禁用: {len(issues)} 处", is_summary=True))
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


def check_black_frames(timeline, fps=25.0, threshold_sec=1.0, io_range=None) -> list:
    """检测黑帧：合并所有视频轨的有效片段后，找未被覆盖的时间段。

    有效片段条件：启用 + 不透明度=100 + 有 MediaPoolItem。
    禁用的、不透明度≠100、调整片段不计入覆盖，并记录原因+片段名。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    valid_intervals = []      # 有效覆盖: [(start, end)]
    invalid_intervals = []    # 无效覆盖: [(start, end, reason, track, name)]
    video_count = timeline.GetTrackCount("video")

    empty = _check_track_empty(video_count, "视频")
    if empty: return empty

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
            # 检查是否脱机/生成片段
            mp = _get_cached(it, "mp")
            if mp is None:
                invalid_intervals.append((s, e, "脱机/无素材", track, name))
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
    merged: list = []
    for s, e in valid_intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    tl_start = timeline.GetStartFrame()
    tl_end = timeline.GetEndFrame()
    gaps = []  # [(start, end, reason, track, name, clip_start)]
    prev = tl_start
    for s, e in merged:
        if s > prev:
            reason = "无片段覆盖"
            track = ""
            gap_name = ""
            clip_tc = prev  # 间隙时码
            for is_, ie, ir, it_, in_ in invalid_intervals:
                if is_ < s and ie > prev:
                    reason = ir
                    track = it_
                    gap_name = in_
                    clip_tc = is_  # 特定片段导致 → 用片段的时码
                    break
            gaps.append((prev, s, reason, track, gap_name, clip_tc))
        prev = max(prev, e)
    if prev < tl_end:
        reason = "无片段覆盖"
        track = ""
        gap_name = ""
        clip_tc = prev
        for is_, ie, ir, it_, in_ in invalid_intervals:
            if is_ < tl_end and ie > prev:
                reason = ir
                track = it_
                gap_name = in_
                clip_tc = is_
                break
        gaps.append((prev, tl_end, reason, track, gap_name, clip_tc))

    # ── 补充：音频尾部超出视频（用子帧精度，从预加载缓存读取）──
    last_video = merged[-1][1] if merged else tl_end
    audio_max_end = last_video
    for ai in range(1, timeline.GetTrackCount("audio") + 1):
        audio_items = _get_items(timeline, "audio", ai)
        if not audio_items:
            continue
        for it in audio_items:
            a_start = _get_cached(it, "start", 0)
            a_dur = _get_cached(it, "audio_dur", 0)
            if a_dur <= 0:
                continue
            a_end_real = a_start + a_dur
            if a_end_real > audio_max_end:
                audio_max_end = a_end_real

    if audio_max_end > last_video:
        overrun = round(audio_max_end - last_video, 2)
        gaps.append((last_video, int(audio_max_end) + 1,
                     f"音频超出视频尾 {overrun}帧", "", "", last_video))

    if not gaps:
        return [_make_result("pass",
            detail="黑帧: 全部通过",
            is_summary=True)]

    smpte = _get_smpte(fps)

    results = [_make_result("fail",
        detail=f"黑帧: {len(gaps)} 处",
        is_summary=True)]

    for s, e, gap_reason, track, name, clip_tc in gaps:
        duration = e - s
        tc = smpte.gettc(clip_tc)
        if gap_reason == "无片段覆盖":
            detail = f"空白 {duration} 帧"
            reason = "请删除大段黑场" if duration >= threshold_sec * fps else "请检查是否有夹帧"
        elif gap_reason.startswith("音频超出"):
            detail = f"{gap_reason}，{name}" if name else gap_reason
            reason = "请调整音频长度使其不超过视频尾"
        elif gap_reason.startswith("不透明度"):
            detail = f"{name}，不透明度不为 100%"
            reason = "请将不透明度调回 100%"
        elif gap_reason == "未启用":
            detail = f"{name}，{gap_reason}"
            reason = "请在时间线上启用该片段"
        elif name:
            detail = f"{name}，{gap_reason}"
            reason = "请替换为有效视频素材"
        else:
            detail = f"{duration} 帧，{gap_reason}"
            reason = ""
        results.append(_make_result("fail", timecode=tc, track=track,
                                    detail=detail, reason=reason))

    return results


def check_audio_mono(timeline, fps=25.0, io_range=None) -> list:
    """检测音频片段声道异常：声道静音 / 声道缩减 / mono↔stereo 轨道错配。

    规则：
      ① 声道静音：ch_idx 含 0 或 mute=True
      ② 声道缩减：源声道数 > mapping 中活跃声道数（5.1→2.0 删声道、stereo→mono 压单声道）
         - 不检测 5.1→2.0 自动下混（emb=6, act=6，达芬奇正常下混不计为缩减）
      ③ mono↔stereo 错配：单声道素材放立体声轨道 或 立体声素材放单声道轨道

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
        track_sub = timeline.GetTrackSubType("audio", ai)
        smpte = _get_smpte(fps)

        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue

            name = _get_clip_name(it)
            start_frame = _get_cached(it, "start", 0)
            ch_map = _get_cached(it, "channel_mapping")
            if not ch_map:
                continue
            embedded = ch_map.get("embedded_audio_channels", 0)
            if not embedded:
                continue

            tc = smpte.gettc(start_frame)
            tm = ch_map.get("track_mapping", {})
            item_has_issue = False

            # ── ① + ②：逐 mapping 遍历，同时统计活跃声道 ──
            active_channels = 0
            for ch_key, ch_data in tm.items():
                ch_idx = ch_data.get("channel_idx", [])
                ch_muted_flag = ch_data.get("mute", False)

                # ① 声道静音
                if ch_muted_flag or 0 in ch_idx:
                    if len(ch_idx) >= 2 and ch_idx[1] == 0:
                        ch_reason = "右声道静音"
                    elif len(ch_idx) >= 2 and ch_idx[0] == 0:
                        ch_reason = "左声道静音"
                    else:
                        ch_reason = "声道静音"
                    issues.append(_make_result(
                        "fail", track=track, timecode=tc,
                        detail=f"{name}，{ch_reason}",
                        reason="请将音频片段复制为立体声",
                    ))
                    item_has_issue = True
                    break  # 一片段只报一次 mute

                # 统计活跃声道（ch_idx 不含 0，取长度）
                active_channels += len([c for c in ch_idx if c > 0])

            # ① 已报 → 跳过 ②③
            if item_has_issue:
                continue

            # ── ② 声道缩减：源声道 > 活跃声道 ──
            if embedded > active_channels:
                if active_channels == 0:
                    ch_reason = "全部声道丢失"
                elif embedded >= 6 and active_channels <= 2:
                    ch_reason = f"多声道被缩减（{embedded}声道→{active_channels}声道）"
                elif embedded == 2 and active_channels == 1:
                    ch_reason = f"立体声被缩减为单声道"
                else:
                    ch_reason = f"声道被缩减（{embedded}→{active_channels}）"
                issues.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{name}，{ch_reason}",
                    reason="请检查音频片段声道设置",
                ))
                item_has_issue = True
                continue
            # ── ③ mono↔stereo 轨道错配 ──
            if track_sub == "stereo" and embedded == 1:
                issues.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{name}，单声道片段放在立体声轨道",
                    reason="请将片段属性改为立体声（右键→片段属性→音频→格式）",
                ))
            elif track_sub == "mono" and embedded >= 2:
                issues.append(_make_result(
                    "fail", track=track, timecode=tc,
                    detail=f"{name}，立体声片段放在单声道轨道",
                    reason="请将片段移到立体声轨道",
                ))

    if not issues:
        return [_make_result("pass",
            detail="声道: 全部通过",
            is_summary=True)]

    results = [_make_result("fail",
        detail=f"声道: {len(issues)} 处",
        is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_glyph(timeline, fps=25.0, io_range=None) -> list:
    """检测字幕不规范字符：根据 Unicode 范围正则匹配。
    范围定义见 dicts/bad_char_ranges.txt（CJK 兼容/部首/全角/私用区等）。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    # ── 加载范围 → 编译正则（缓存）──
    range_path = os.path.join(_SCRIPT_DIR, "dicts", "bad_char_ranges.txt")
    if range_path not in _censor_cache:
        try:
            ranges = []
            with open(range_path, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # 格式: U+XXXX-U+YYYY  ...
                    parts = line.split()
                    if len(parts) >= 1 and parts[0].startswith("U+"):
                        m = re.match(r"U\+([0-9A-Fa-f]+)(?:-U\+([0-9A-Fa-f]+))?", parts[0])
                        if m:
                            lo = int(m.group(1), 16)
                            hi = int(m.group(2), 16) if m.group(2) else lo
                            ranges.append((lo, hi))
            # 编译成正则字符类（用 chr() 避免 \u 4位限制）
            if ranges:
                chars = []
                for lo, hi in ranges:
                    chars.append(chr(lo))
                    if lo != hi:
                        chars.append("-")
                        chars.append(chr(hi))
                _censor_cache[range_path] = re.compile("[" + "".join(chars) + "]")
            else:
                _censor_cache[range_path] = None
        except Exception:
            _censor_cache[range_path] = None
    glyph_re = _censor_cache[range_path]

    if glyph_re is None:
        return [_make_result("fail", detail="不规范字符范围为为空", is_summary=True)]

    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    empty = _check_track_empty(subtitle_count, "字幕")
    if empty: return empty

    smpte = _get_smpte(fps)

    for si in range(1, 2):  # 仅 ST1（主力字幕轨）
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

            m = glyph_re.search(text)
            if m:
                issues.append(_make_result("warn", track=track, timecode=tc,
                    detail=f"{text}，含不规范字符「{m.group()}」",
                    reason="请替换为规范汉字"))

    if not issues:
        return [_make_result("pass", detail="异体字: 全部通过", is_summary=True)]

    results = [_make_result("warn", detail=f"异体字: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_linebreak(timeline, fps=25.0, io_range=None) -> list:
    """检测字幕换行：CPL 超限 / 硬换行。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    empty = _check_track_empty(subtitle_count, "字幕")
    if empty: return empty

    try:
        cpl = int(timeline.GetSetting().get("limitSubtitleCPL", 0))
    except Exception:
        cpl = 0

    smpte = _get_smpte(fps)

    for si in range(1, 2):  # 仅 ST1（主力字幕轨）
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
                    detail=f"硬换行: {text}",
                    reason="请调整断句"))
                continue

            # CPL 超限
            if cpl > 0 and len(text) > cpl:
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"超单行 {cpl} 字上限: {text}",
                    reason="请调整断句"))
                continue

    if not issues:
        return [_make_result("pass", detail="换行: 全部通过", is_summary=True)]

    results = [_make_result("fail", detail=f"换行异常: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_subtitle_censor(timeline, dict_path, fps=25.0, io_range=None, use_warn=False, whitelist_path=None, debug_log=None) -> list:
    """检测字幕含违禁词。

    Args:
        dict_path: 违禁词文件路径，一行一词
        use_warn: True=用⚠, False=用❌（个人词典用❌，系统词典用⚠）
        whitelist_path: 白名单文件路径，匹配到的词无条件跳过

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    global _censor_cache
    # 加载字典 + 编译正则
    if dict_path not in _censor_cache:
        words: list = []
        category_map = {}   # word → "cat1 > cat2"
        suggestion_map = {} # word → "sug1 / sug2 / ..."
        if os.path.isfile(dict_path):
            with open(dict_path, "r", encoding="utf-8-sig") as f:
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
        # 编译正则：按长度降序（长词优先匹配），过滤空词
        word_list = sorted([w for w, *_ in words if w], key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(w) for w in word_list)) if word_list else None
        _censor_cache[dict_path] = (words, pattern, suggestion_map, category_map)

    censor_words, pattern, suggestion_map, category_map = _censor_cache[dict_path]
    if not pattern:
        return [_make_result("fail", detail="违禁词字典为空", is_summary=True)]

    # ── 白名单（缓存）──
    wl_pattern = None
    if whitelist_path:
        wl_key = f"WL:{whitelist_path}"
        if wl_key not in _censor_cache:
            wl_words = []
            try:
                with open(whitelist_path, encoding="utf-8-sig") as f:
                    for line in f:
                        w = line.strip()
                        if w and not w.startswith("#"):
                            wl_words.append(w)
            except Exception:
                pass
            _censor_cache[wl_key] = re.compile("|".join(re.escape(w) for w in sorted(wl_words, key=len, reverse=True))) if wl_words else None
        wl_pattern = _censor_cache[wl_key]

    issues = []
    subtitle_count = timeline.GetTrackCount("subtitle")
    empty = _check_track_empty(subtitle_count, "字幕")
    if empty: return empty

    smpte = _get_smpte(fps)
    for si in range(1, 2):  # 仅 ST1（主力字幕轨）
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
                # 白名单过滤：匹配词在白名单中 → 跳过
                if wl_pattern and wl_pattern.search(word):
                    continue
                sug = suggestion_map.get(word, "")
                reason_text = "检查违禁词"
                status = "warn" if use_warn else "fail"
                issues.append(_make_result(status, track=track, timecode=tc,
                    detail=word, reason=reason_text))

    if not issues:
        return [_make_result("pass", detail="无违禁词", is_summary=True)]

    status = "warn" if use_warn else "fail"
    results = [_make_result(status, detail=f"违禁词: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def _fmt_duration(sec: float) -> str:
    """格式化秒数为 m:ss。"""
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"

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
            detail=f"起始时码 {start_tc}", reason="应为 00:00:00:00", is_summary=True))
    else:
        results.append(_make_result("pass", detail="起始时码: 00:00:00:00 (通过)", is_summary=True))

    # ── ② 时长检测 ──
    total_frames = timeline.GetEndFrame()
    duration_sec = total_frames / max(fps, 1)
    if duration_sec < 41:
        results.append(_make_result("fail",
            detail=f"时长 {duration_sec:.0f}s（不足41s）",
            reason="低于付费集最低时长，单集需≥41s"))
    elif duration_sec > 180:
        results.append(_make_result("fail",
            detail=f"时长 {_fmt_duration(duration_sec)}（超过180s）",
            reason="抖音单集≤3分钟，超时驳回。建议优化至90秒左右"))
    else:
        results.append(_make_result("pass", detail=f"时长: {_fmt_duration(duration_sec)} (通过)"))

    # ── ③ 命名规范 ──
    import re
    tl_name = timeline.GetName()
    if _IS_PERSONAL:
        results.append(_make_result("pass", detail=f"命名: {tl_name} (个人版用自定义命名)", is_summary=True))
    elif re.match(r'^\d{2,3}$', tl_name):
        results.append(_make_result("pass", detail=f"命名: {tl_name} (通过)"))
    else:
        results.append(_make_result("fail",
            detail=f"命名: {tl_name}",
            reason="请改为 01、02、03 等两位数格式"))

    # ── ④ 使用项目设置 ──
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
        results.append(_make_result("fail", detail="无法对比项目设置"))

    return results


# ── 直通编辑 ──

def check_through_edits(timeline, fps=25.0, io_range=None) -> list:
    """检测直通编辑：相邻同素材片段且源帧连续（间隔≤1帧）。只查视频轨。"""
    issues = []
    smpte = _get_smpte(fps)
    for vi in range(1, timeline.GetTrackCount("video") + 1):
        items = timeline.GetItemListInTrack("video", vi) or []
        prev_uid = None
        for i in range(len(items) - 1):
            a = items[i]; b = items[i + 1]
            if not _in_io_range(a, io_range):
                prev_uid = None
                continue
            try:
                am = a.GetMediaPoolItem(); bm = b.GetMediaPoolItem()
                uid_a = am.GetUniqueId() if am else None
                uid_b = bm.GetUniqueId() if bm else None
            except Exception:
                uid_a = uid_b = None
            if not uid_a or uid_a != uid_b:
                continue
            # 直通编辑：源帧连续，se==ss（同一切点）
            a_se = a.GetSourceEndFrame()
            b_ss = b.GetSourceStartFrame()
            if a_se != b_ss:
                continue
            name = _get_clip_name(a)
            tc = smpte.gettc(_get_cached(a, "start"))
            issues.append(_make_result("warn", track=f"V{vi}", timecode=tc,
                detail=f"直通编辑: {name}",
                reason="建议连接片段，以减少调色镜头数"))
    if not issues:
        return [_make_result("pass", detail="直通编辑: 全部通过", is_summary=True)]
    return [_make_result("warn", detail=f"直通编辑: {len(issues)} 处", is_summary=True)] + issues


# ── 尾板检测 ──

def check_tailboard(timeline, fps=25.0, io_range=None) -> list:
    """检测结尾是否有尾板（定格转场 + 未完待续/全剧终）。

    规则：最后 10 秒内，所有视频轨中必须同时存在：
    - 名称含"定格转场"的片段
    - 名称含"未完待续"或"全剧终"的片段
    """
    total_frames = timeline.GetEndFrame()
    tail_start = max(0, total_frames - int(fps * 10))
    has_freeze = False
    has_text = False
    text_names = []  # 记录已找到的文字尾板名称（性能优化：找到一个就够）

    for vi in range(1, timeline.GetTrackCount("video") + 1):
        if has_freeze and has_text:
            break
        for it in _get_items(timeline, "video", vi):
            if int(_get_cached(it, "end", 0)) < tail_start:
                continue
            name = _get_cached(it, "name", "") or ""
            if not name:
                try:
                    name = it.GetName() or ""
                except Exception:
                    continue
            if not has_freeze and "定格转场" in name:
                has_freeze = True
            if not has_text and ("未完待续" in name or "全剧终" in name):
                has_text = True
                text_names.append(name)

    # 生成结果
    if has_freeze and has_text:
        return [_make_result("pass", detail="尾板: 定格转场 + 结尾文字 (通过)", is_summary=True)]

    if not has_freeze and not has_text:
        detail = "结尾缺少定格转场和结尾文字"
    elif not has_freeze:
        detail = "结尾缺少定格转场"
    else:
        detail = "结尾缺少文字（未完待续/全剧终）"

    return [
        _make_result("warn", detail=detail,
                     reason="请在时间线末尾添加定格转场和未完待续（或全剧终）",
                     is_summary=True),
        _make_result("warn", detail=detail,
                     reason="请在时间线末尾添加定格转场和未完待续（或全剧终）"),
    ]


def _exposed_ranges(clip_start, clip_end, cover_intervals):
    """计算片段被覆盖后实际暴露的帧范围。

    Args:
        clip_start, clip_end: 片段原始帧范围 [start, end)
        cover_intervals: 上层有效覆盖的帧区间列表 [(start, end), ...]
    Returns:
        list of (start, end) 暴露帧范围
    """
    if not cover_intervals:
        return [(clip_start, clip_end)]
    # 排序并合并重叠覆盖区间
    sorted_iv = sorted(cover_intervals, key=lambda x: x[0])
    merged = [list(sorted_iv[0])]
    for iv_s, iv_e in sorted_iv[1:]:
        if iv_s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], iv_e)
        else:
            merged.append([iv_s, iv_e])
    # 减去覆盖区间，得到暴露区间
    exposed = []
    cur = clip_start
    for ms, me in merged:
        if ms > cur:
            exposed.append((cur, ms))
        cur = max(cur, me)
    if cur < clip_end:
        exposed.append((cur, clip_end))
    return exposed


def check_black_borders(timeline, project=None, fps=25.0, io_range=None, debug_log=None, mask_ratio=None) -> list:
    """检测视频轨可见片段的黑边：缩放不足、位移、旋转导致的未覆盖区域。
    mask_ratio: 用户手动设置的画面宽高比（如 2.35），用于排除有意的遮幅黑边。"""
    import math
    issues = []
    video_count = timeline.GetTrackCount("video")
    empty = _check_track_empty(video_count, "视频")
    if empty: return empty

    # ── 取时间线分辨率（三层兜底，取不到就放弃）──
    timeline_w = timeline_h = 0
    if project:
        try:
            pw = project.GetSetting("timelineResolutionWidth")
            ph = project.GetSetting("timelineResolutionHeight")
            if pw: timeline_w = int(pw)
            if ph: timeline_h = int(ph)
        except Exception:
            pass
    if not (timeline_w and timeline_h):
        try:
            tw = timeline.GetSetting("timelineResolutionWidth")
            th = timeline.GetSetting("timelineResolutionHeight")
            if tw: timeline_w = int(tw)
            if th: timeline_h = int(th)
        except Exception:
            pass
    if not (timeline_w and timeline_h):
        return [_make_result("fail",
            detail="黑边检测: 无法读取时间线分辨率，已跳过",
            is_summary=True),
            _make_result("fail",
            reason="请检查项目设置中的时间线分辨率是否正常")]

    smpte = _get_smpte(fps)
    # ── 遮幅：用户设了宽高比 → 计算有效画面区域，排除有意的上下遮幅 ──
    _masked_t = 0
    _masked_b = timeline_h
    if mask_ratio:
        try:
            _mr = float(mask_ratio)
            if _mr > 0:
                _content_h = timeline_w / _mr  # 有效画面高度
                _bar_h = (timeline_h - _content_h) / 2.0
                if _bar_h > 1:  # 遮幅高度 > 1px 才启用
                    _masked_t = _bar_h
                    _masked_b = timeline_h - _bar_h
        except (ValueError, TypeError):
            pass
    # 先收集所有轨上所有片段的时间范围（用于覆盖判定）
    all_ranges = {}  # track_index → [(start, end), ...]
    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items: continue
        all_ranges[vi] = [(it, _get_cached(it, "start", 0), _get_cached(it, "end", 0)) for it in items]
    # 从顶层往下遍历，上层覆盖下层 → 跳过不可见片段
    for vi in range(video_count, 0, -1):
        if vi not in all_ranges: continue
        track = f"V{vi}"
        for it_data in all_ranges[vi]:
            it, s, e = it_data if len(it_data) == 3 else (it_data[0], it_data[1], it_data[2])
            if not _in_io_range(it, io_range): continue
            if _get_cached(it, "enabled", True) is False: continue
            if _get_cached(it, "mp") is None: continue
            # 收集上层覆盖区间（启用且 Opacity=100% 的片段视为有效遮挡）
            cover_intervals = []
            for uvi in range(vi + 1, video_count + 1):
                if uvi not in all_ranges: continue
                for uit, us, ue in all_ranges[uvi]:
                    if _get_cached(uit, "enabled", True) is False:
                        continue
                    u_props = _get_cached(uit, "props", {})
                    if float(u_props.get("Opacity", 100) or 100) < 100:
                        continue
                    ov_s = max(s, us)
                    ov_e = min(e, ue)
                    if ov_e > ov_s:
                        cover_intervals.append((ov_s, ov_e))
            # 合并重叠区间，计算实际暴露的子区间
            exposed_ranges = _exposed_ranges(s, e, cover_intervals)
            if not exposed_ranges:
                continue
            clip_dur = e - s
            res_str = _get_cached(it, "mp_resolution", "")
            if not res_str or "x" not in res_str: continue
            try: src_w, src_h = map(int, res_str.split("x"))
            except Exception: continue
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
            fit_scale = min(timeline_w / src_w, timeline_h / src_h)
            eff_w = src_w * fit_scale * zoom_x
            eff_h = src_h * fit_scale * zoom_y
            # 素材够大且轴对齐（旋转 ≈ 90° 倍数）→ 偏位是故意的构图选择
            # RotationAngle 为累计值（如 -5156.6°），用 % 360 归一化后 ±30° 容差匹配
            rot_360 = abs(math.degrees(rot)) % 360
            near_axis = any(abs(rot_360 - a) < 30.0 or abs(rot_360 - (a + 360)) < 30.0
                           for a in (0, 90, 180, 270))
            if near_axis:
                # 近轴路径：先用轴对齐快速判断
                nearest = min((0, 90, 180, 270), key=lambda a: min(abs(rot_360 - a), abs(rot_360 - (a + 360))))
                if nearest in (90, 270):
                    check_w, check_h = eff_h, eff_w
                else:
                    check_w, check_h = eff_w, eff_h
                # 尺寸够大且中心未偏移且旋转为 180° 的整倍数 → 安全跳过
                if (check_w >= timeline_w and check_h >= timeline_h
                    and abs(cx - timeline_w/2) < 0.5 and abs(cy - timeline_h/2) < 0.5
                    and rot_360 % 180 < 1.0):
                    continue
            # 统一角检测（覆盖近轴 + 非近轴）。遮幅模式下检测有效画面区域而非全画布
            cos_r_raw = math.cos(rot); sin_r_raw = math.sin(rot)
            hw, hh = eff_w / 2.0, eff_h / 2.0
            has_gap = False
            _canvas_corners = [(0, _masked_t), (timeline_w, _masked_t),
                               (timeline_w, _masked_b), (0, _masked_b)]
            for tx, ty in _canvas_corners:
                dx, dy = tx - cx, ty - cy
                lx = dx * cos_r_raw + dy * sin_r_raw
                ly = -dx * sin_r_raw + dy * cos_r_raw
                if abs(lx) > hw or abs(ly) > hh:
                    has_gap = True; break
            if not has_gap: continue
            name = _get_clip_name(it)
            # 跳过特殊片段（定场/转场/结尾画面）
            if any(kw in name for kw in _TAIL_KW):
                continue
            for exp_s, exp_e in exposed_ranges:
                tc = smpte.gettc(exp_s)
                dur_info = f"（{exp_e - exp_s}帧）" if (exp_e - exp_s) < clip_dur else ""
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{name}，有黑边{dur_info}", reason="适当调整以规避黑边"))
    if not issues:
        return [_make_result("pass", detail="黑边: 全部通过", is_summary=True)]
    results = [_make_result("fail", detail=f"黑边: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_speed(timeline, project_fps=25.0, io_range=None, debug_log=None) -> list:
    """检测视频轨片段变速问题：慢放但未使用光流或帧混合。"""
    issues = []
    video_count = timeline.GetTrackCount("video")
    empty = _check_track_empty(video_count, "视频")
    if empty: return empty
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
            s_dur = abs(_get_cached(it, "source_end", 0) - _get_cached(it, "source_start", 0)) + 1
            if s_dur <= 0: continue
            src_fps = float(_get_cached(it, "mp_fps", project_fps) or project_fps)
            # mp_fps 为空时尝试 GetClipProperty 兜底
            if not _get_cached(it, "mp_fps", ""):
                try:
                    fallback = it.GetClipProperty("FPS")
                    if fallback:
                        src_fps = float(fallback)
                except Exception:
                    pass
            if not src_fps or src_fps <= 0:
                continue  # 无法确定帧率，跳过
            retime = int(_get_cached(it, "props", {}).get("RetimeProcess", 0))
            tl_sec = t_dur / project_fps
            src_sec = s_dur / src_fps
            speed = src_sec / tl_sec * 100
            threshold = min(project_fps / src_fps, 1.0) * 100
            # 容忍 ±2% 误差（如 50fps→25fps 时间线，49% 不报）
            if speed < threshold - 2.0 and retime not in (2, 3):
                # 跳过静帧/图片（天然无变速，素材1帧拉长到N帧）
                mp = _get_cached(it, "mp")
                if mp:
                    try:
                        if mp.GetClipProperty("Type") in ("静帧", "Still"):
                            continue
                    except Exception:
                        pass
                name = _get_clip_name(it)
                if any(kw in name for kw in _TAIL_KW):
                    continue
                smpte = _get_smpte(project_fps)
                tc = smpte.gettc(_get_cached(it, "start", 0))
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{name}，速度为{speed:.0f}%",
                    reason="调整变速，或使用帧混合/光流法"))
    if not issues:
        return [_make_result("pass", detail="变速: 全部通过", is_summary=True)]
    results = [_make_result("fail", detail=f"变速: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_video_clamping(timeline, threshold_frames=1, fps=25.0, io_range=None, debug_log=None) -> list:
    """检测视频轨夹帧：启用的视频片段时长 ≤ X 帧。"""
    issues = []
    video_count = timeline.GetTrackCount("video")
    empty = _check_track_empty(video_count, "视频")
    if empty: return empty
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
            detail="视频夹帧: 全部通过", is_summary=True)]
    results = [_make_result("warn", detail=f"夹帧: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


def check_color(timeline, project=None, fps=25.0, io_range=None) -> list:
    """检查调色：① 时间线节点为空 ② 片段唯一节点套 Sony LUT 但可能漏调色。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    SONY_LUT = "Sony/SLog3SGamut3.CineToLC-709TypeA.cube"
    issues = []

    # ── ① 时间线节点 ──
    tl_nodes = 0
    try:
        tl_graph = timeline.GetNodeGraph()
        if tl_graph is not None:
            tl_nodes = tl_graph.GetNumNodes()
    except Exception:
        issues.append(_make_result("fail",
            detail="调色: 无法读取时间线 NodeGraph",
            reason="可能是达芬奇版本不支持，请手动检查调色节点"))

    if tl_nodes > 0:
        issues.append(_make_result("fail",
            detail=f"时间线有 {tl_nodes} 个节点",
            reason="请删除时间线节点"))

    # ── ② 片段节点（加缓存避免重复 IPC）──
    _lut_cache = {}
    _node_cache = {}
    video_count = timeline.GetTrackCount("video")
    for vi in range(1, video_count + 1):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            if _get_cached(it, "mp") is None:
                continue
            try:
                uid = it.GetUniqueId()
            except Exception:
                continue
            try:
                if uid not in _node_cache:
                    graph = it.GetNodeGraph()
                    _node_cache[uid] = graph.GetNumNodes() if graph else 0
                n = _node_cache[uid]
            except Exception:
                n = 0
            try:
                if uid not in _lut_cache:
                    _lut_cache[uid] = it.GetLUT(1)
                lut = _lut_cache[uid]
            except Exception:
                lut = None

            if n == 1 and lut == SONY_LUT:
                name = _get_clip_name(it)
                smpte = _get_smpte(fps)
                tc = smpte.gettc(_get_cached(it, "start", 0))
                issues.append(_make_result("fail", track=track, timecode=tc,
                    detail=f"{name}，在唯一节点上应用了索尼 LUT",
                    reason="请检查是否漏掉了调色"))

    if not issues:
        return [_make_result("pass",
            detail="调色: 全部通过",
            is_summary=True)]
    return [_make_result("fail",
                         detail=f"调色: {len(issues)} 处",
                         is_summary=True)] + issues


# ── 调色标记 ──

# 打码效果关键词（OFX 工具名含以下即可匹配）
_EFFECT_BLUR = {"径向模糊", "方向模糊", "方形模糊", "缩放模糊", "镜头模糊", "马赛克模糊", "高斯模糊"}

def check_coloring_markers(timeline, project=None, fps=25.0, io_range=None) -> list:
    """检测有打码效果且节点数≤2的片段，在起始帧打红色标记「调色注意」。

    不会覆盖已有标记（叠加策略）。
    """
    issues = []
    marker_count = 0

    for vi in range(1, timeline.GetTrackCount("video") + 1):
        for it in _get_items(timeline, "video", vi):
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue

            try:
                ng = it.GetNodeGraph()
                if ng is None:
                    continue
                n = ng.GetNumNodes()
            except Exception:
                continue
            if n > 2:
                continue

            has_blur = False
            for ni in range(1, n + 1):
                tools = ng.GetToolsInNode(ni) or []
                for t in tools:
                    if any(kw in t.lower() for kw in _EFFECT_BLUR):
                        has_blur = True
                        break
                if has_blur:
                    break

            if not has_blur:
                continue

            # 打红色标记（timeine 级，尺子上可见）
            start_f = _get_cached(it, "start", 0)
            end_f = _get_cached(it, "end", start_f + 1)
            mid_f = (int(start_f) + int(end_f)) // 2
            try:
                timeline.AddMarker(mid_f, "Red", "调色注意: 打码", "", 1)
                marker_count += 1
            except Exception:
                issues.append(_make_result("fail",
                    track=f"V{vi}",
                    timecode=_get_smpte(fps).gettc(start_f),
                    detail=f"{_get_cached(it, 'name', '')}，打标记失败",
                    reason="请手动添加调色标记"))

    if issues:
        total = marker_count + len(issues)
        return [_make_result("fail",
                detail=f"调色标记: {marker_count}/{total} 成功，{len(issues)} 失败",
                is_summary=True)] + issues

    detail = f"已完成: {marker_count} 处标记" if marker_count else "无需标记"
    return [
        _make_result("pass", detail=f"调色标记: {detail}", is_summary=True),
        _make_result("pass", detail=detail, reason="已自动打红色标记，请在时间线确认")
    ]



from deploy_config import get_smb_paths

# ── 片段文件信息缓存（脱机+路径检测共享，避免重复 IPC）──
_clip_files_cache = None  # {(track, name): {"start": int, "mp": item|None, "path": str|None}}


def _collect_clip_files(timeline, io_range=None):
    """收集当前时间线所有视频轨+音频轨片段的基本文件信息。缓存优先。"""
    global _clip_files_cache
    if _clip_files_cache is not None:
        return _clip_files_cache
    info = {}
    for vi in range(1, timeline.GetTrackCount("video") + 1):
        for it in _get_items(timeline, "video", vi):
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            name = _get_clip_name(it)
            start = _get_cached(it, "start", 0)
            mp = _get_cached(it, "mp")
            path = ""
            mp_type = ""
            if mp is not None:
                try:
                    path = mp.GetClipProperty("File Path") or ""
                except Exception:
                    pass
                try:
                    mp_type = mp.GetClipProperty("Type") or ""
                except Exception:
                    pass
            key = (f"V{vi}", name)
            if key not in info:
                props = _get_cached(it, "props", {})
                info[key] = {"start": start, "mp": mp, "path": path, "track": f"V{vi}", "mp_type": mp_type, "props": props}
    for ai in range(1, timeline.GetTrackCount("audio") + 1):
        for it in _get_items(timeline, "audio", ai):
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            name = _get_clip_name(it)
            start = _get_cached(it, "start", -1)
            if start < 0:  # 音频未预加载
                try:
                    start = int(it.GetStart())
                except Exception:
                    start = 0
            mp = _get_cached(it, "mp")
            # 音频轨未预加载，mp 为空时直接取
            if mp is None:
                try:
                    mp = it.GetMediaPoolItem()
                except Exception:
                    pass
            path = ""
            mp_type = ""
            if mp is not None:
                try:
                    path = mp.GetClipProperty("File Path") or ""
                except Exception:
                    pass
                try:
                    mp_type = mp.GetClipProperty("Type") or ""
                except Exception:
                    pass
            key = (f"A{ai}", name)
            if key not in info:
                info[key] = {"start": start, "mp": mp, "path": path, "track": f"A{ai}", "mp_type": mp_type}
    _clip_files_cache = info
    return info


def _clear_clip_files_cache():
    global _clip_files_cache
    _clip_files_cache = None


def check_path_location(timeline, project=None, fps=25.0, io_range=None) -> list:
    """检查当前时间线素材路径是否在服务器上（使用共享缓存）。"""
    issues = []
    # 现场读 deploy.json，不缓存——配置页改路径后立即生效
    prefixes = get_smb_paths()
    if not prefixes:
        return [_make_result("pass", detail="路径检测: 未配置服务器路径，已跳过", is_summary=True)]
    seen = set()
    for (track, name), info in _collect_clip_files(timeline, io_range).items():
        path = info["path"]
        if not path or path in seen:
            continue
        seen.add(path)
        if not any(path.startswith(p) for p in prefixes):
            smpte = _get_smpte(fps)
            tc = smpte.gettc(info["start"])
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，不在服务器路径",
                reason="请将素材移至服务器后重新链接"))

    if not issues:
        return [_make_result("pass",
                             detail="路径检测: 全部在服务器上",
                             is_summary=True)]
    return [_make_result("fail",
                         detail=f"路径检测: {len(issues)} 处不在服务器上",
                         is_summary=True)] + issues


def check_offline_clips(timeline, fps=25.0, io_range=None, debug_log=None) -> list:
    """检查当前时间线是否存在脱机文件（使用共享缓存）。

    达芬奇两种脱机模式：
      - MediaPoolItem 被删：mp=None，时间线上还在但媒体池里找不到
      - 源文件丢失：mp 存在，但 File Path 为空（文件被移动/删除/改名）
    """
    _MEDIA_EXT = {".mp4", ".mxf", ".mov", ".avi", ".r3d", ".braw",
        ".mts", ".m2t", ".m2ts", ".mpg", ".mpeg", ".m4v", ".mkv",
        ".wmv", ".flv", ".webm", ".ts", ".3gp", ".vob",
        ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp",
        ".dpx", ".exr", ".psd", ".tga", ".targa",
        ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2",
        ".heic", ".heif", ".avif", ".webp", ".crm", ".ari"}
    issues = []
    seen_mp = set()
    for (track, name), info in _collect_clip_files(timeline, io_range).items():
        mp = info["mp"]
        if mp is None:
            # 无 MediaPoolItem → 多级判脱机
            # L1: 空 Property → 转场（交叉叠化等），跳过
            props = info.get("props", {})
            if not props:
                continue
            # L2: 无 Distortion 键 → 生成器/文字（Text+/纯色等），跳过
            if "Distortion" not in props:
                continue
            # L3: 有 Distortion 但无 mp → 按扩展名判脱机
            lo = name.lower()
            if not any(lo.endswith(ext) for ext in _MEDIA_EXT):
                continue
            smpte = _get_smpte(fps)
            tc = smpte.gettc(info["start"])
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，脱机文件",
                reason="请重新链接源文件或替换素材"))
            continue
        try:
            mp_uid = mp.GetUniqueId()
        except Exception:
            continue
        if mp_uid in seen_mp:
            continue
        seen_mp.add(mp_uid)
        # 复合片段/内部合成无外部文件，跳过脱机检测
        mp_type = info.get("mp_type", "")
        if mp_type in ("复合", "合成", "Compound", "Fusion Composition"):
            continue
        path = info["path"]
        if path:
            continue
        smpte = _get_smpte(fps)
        tc = smpte.gettc(info["start"])
        issues.append(_make_result("fail", track=track, timecode=tc,
            detail=f"{name}，脱机文件",
            reason="请重新链接源文件或替换素材"))

    if not issues:
        return [_make_result("pass",
                             detail="脱机检测: 无脱机文件",
                             is_summary=True)]
    return [_make_result("fail",
                         detail=f"脱机检测: {len(issues)} 处脱机",
                         is_summary=True)] + issues


def check_camera_on_high_tracks(timeline, fps=25.0, io_range=None, debug_log=None) -> list:
    """检查视频越轨（前置：视频轨数=5）。
    ① 实拍素材（含摄影机元数据）放在了 V4/V5 — 应放 V1-V3
    ② 尾板素材（未完待续/定格转场/全剧终）放在了 V1-V3 — 应放 V4-V5
    ③ 文本/Text+ 放在了 V1-V3 — 应放 V4-V5
    ④ 调整图层放在了 V1/V4/V5 — 应放 V2-V3

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    # ── 前置：视频轨数必须为 5 ──
    video_count = timeline.GetTrackCount("video")
    if video_count != len(VIDEO_TRACK_PRESET):
        if debug_log: debug_log(f"视频越轨跳过: 轨数 {video_count} ≠ {len(VIDEO_TRACK_PRESET)}")
        return [_make_result("fail",
            detail=f"视频轨数 {video_count}≠{len(VIDEO_TRACK_PRESET)}，跳过视频越轨检测",
            is_summary=True)]
    _cam_cache = {}   # mp_unique_id → bool: 是否为实拍素材
    issues = []

    # ── ① 实拍素材不得在 V4/V5 ──
    for vi in (4, 5):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            mp = _get_cached(it, "mp")
            if mp is None:
                continue

            try:
                mp_uid = mp.GetUniqueId()
            except Exception:
                continue
            if mp_uid not in _cam_cache:
                try:
                    _cam_cache[mp_uid] = is_camera_footage(mp)
                except Exception:
                    _cam_cache[mp_uid] = False
            if not _cam_cache[mp_uid]:
                continue

            name = _get_clip_name(it)
            smpte = _get_smpte(fps)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，位于第 {vi} 轨",
                reason="实拍素材请放 V1-V3"))

    # ── ② 尾板素材不得在 V1-V3 ──
    for vi in (1, 2, 3):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            name = _get_clip_name(it)
            if not any(kw in name for kw in _TAIL_KW):
                continue

            smpte = _get_smpte(fps)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，位于第 {vi} 轨",
                reason="尾板请放 V4-V5"))

    # ── ③ 文本/Text+ 不得在 V1-V3 ──
    _type_cache = {}  # mp_uid → type str
    for vi in (1, 2, 3):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            name = _get_clip_name(it)
            mp = _get_cached(it, "mp")
            # 判断：MP存在→查Type，MP不存在→查名字
            is_text = False
            if mp is not None:
                try:
                    mp_uid = mp.GetUniqueId()
                except Exception:
                    mp_uid = None
                if mp_uid is not None:
                    if mp_uid not in _type_cache:
                        try:
                            _type_cache[mp_uid] = mp.GetClipProperty("Type") or ""
                        except Exception:
                            _type_cache[mp_uid] = ""
                    is_text = _type_cache[mp_uid] in ("Text", "Text+", "文本", "文本+")
            else:
                # 时间线上直接创建的文本片段（无MP）
                is_text = name.startswith("文本") or name in ("Text", "Text+")
            if not is_text:
                continue

            smpte = _get_smpte(fps)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，位于第 {vi} 轨",
                reason="文本/Text+请放 V4-V5"))

    # ── ④ 调整图层不得在 V1/V4/V5 ──
    for vi in (1, 4, 5):
        items = _get_items(timeline, "video", vi)
        if not items:
            continue
        track = f"V{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            name = _get_clip_name(it)
            mp = _get_cached(it, "mp")
            is_adj = False
            if mp is not None:
                try:
                    mp_uid = mp.GetUniqueId()
                except Exception:
                    mp_uid = None
                if mp_uid is not None:
                    if mp_uid not in _type_cache:
                        try:
                            _type_cache[mp_uid] = mp.GetClipProperty("Type") or ""
                        except Exception:
                            _type_cache[mp_uid] = ""
                    is_adj = _type_cache[mp_uid] == "调整剪辑"
            else:
                # 时间线上直接创建的调整图层（无MP）
                is_adj = name == "调整片段"
            if not is_adj:
                continue

            smpte = _get_smpte(fps)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=f"{name}，位于第 {vi} 轨",
                reason="调整图层请放 V2-V3"))

    if not issues:
        return [_make_result("pass", detail="视频越轨: 全部通过", is_summary=True)]

    results = [_make_result("fail",
        detail=f"视频越轨: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results


# ── 音频颜色 → 轨道映射 ──
# key: GetClipColor() 返回值, value: (允许轨道范围, 音频类型)
_AUDIO_COLOR_RULES = {
    "":        ((1, 3), "人声"),   # 无色
    "Purple":  ((1, 3), "人声"),   # 紫色
    "Yellow":  ((1, 3), "人声"),   # 黄色
    "Pink":    ((4, 7), "音效"),   # 粉色
    "Chocolate": ((8, 10), "音乐"), # 巧克力色
}


def _audio_color_detail(color, vi, name):
    """根据颜色和轨道生成 detail/reason。A1-A3 无色不报。"""
    if not color:
        if 1 <= vi <= 3:
            return None  # A1-A3 无色 = 合规（人声）
        return (f"{name}，未设置色彩",
                "请归类为人声/音效/音乐对应色彩")
    rule = _AUDIO_COLOR_RULES.get(color)
    if rule is None:
        return (f"{name}，色彩为{color}",
                "请归类为人声/音效/音乐对应色彩")
    (lo, hi), cat = rule
    if lo <= vi <= hi:
        return None  # 合规
    # 越轨
    loc_map = {(1, 3): "A1-A3", (4, 7): "A4-A7", (8, 10): "A8-A10"}
    dest = loc_map.get((lo, hi), f"A{lo}-A{hi}")
    return (f"{name}，位于第 {vi} 轨",
            f"{cat}请放 {dest}")


def check_audio_color_tracks(timeline, fps=25.0, io_range=None, debug_log=None) -> list:
    """检查音频媒体池颜色越轨（前置：音轨数=10 且名称匹配预设）。

    短剧项目音频轨道颜色约定：
      A1-A3（VO/OS）→ 无色/紫色/黄色（人声）
      A4-A7（SFX）   → 粉色（音效）
      A8-A10（BGM）  → 巧克力色（音乐）
      其他颜色       → 未归类

    MP 颜色 ≠ 时间线颜色。此检查读 MediaPoolItem.GetClipColor()。
    包含复合片段。

    Returns:
        list[dict]: 第一条为汇总(is_summary=True)，后续为具体问题
    """
    # ── 前置①：音轨数必须为 10 ──
    audio_count = timeline.GetTrackCount("audio")
    if audio_count != len(AUDIO_TRACK_PRESET):
        if debug_log: debug_log(f"音频越轨跳过: 音轨数 {audio_count} ≠ {len(AUDIO_TRACK_PRESET)}")
        return [_make_result("fail",
            detail=f"音轨数 {audio_count}≠{len(AUDIO_TRACK_PRESET)}，跳过音频越轨检测",
            is_summary=True)]

    # ── 前置②：音频轨名称必须匹配预设 ──
    names_ok = True
    for idx, preset in enumerate(AUDIO_TRACK_PRESET):
        if idx + 1 > audio_count:
            break
        if timeline.GetTrackName("audio", idx + 1) != preset["name"]:
            names_ok = False
            break
    if not names_ok:
        if debug_log: debug_log("音频越轨跳过: 轨名与预设不匹配")
        return [_make_result("fail",
            detail="音频轨名称与预设不符，跳过音频越轨检测",
            is_summary=True)]

    # ── 颜色检查 ──
    _color_cache = {}  # mp_unique_id → color str
    issues = []

    for vi in range(1, audio_count + 1):
        items = _get_items(timeline, "audio", vi)
        if not items:
            continue
        track = f"A{vi}"
        for it in items:
            if not _in_io_range(it, io_range):
                continue
            if _get_cached(it, "enabled", True) is False:
                continue
            mp = _get_cached(it, "mp")
            if mp is None:
                continue

            # 缓存：同一 MediaPoolItem 只查一次颜色
            try:
                mp_uid = mp.GetUniqueId()
            except Exception:
                continue
            if mp_uid not in _color_cache:
                try:
                    _color_cache[mp_uid] = mp.GetClipColor() or ""
                except Exception:
                    _color_cache[mp_uid] = ""
            color = _color_cache[mp_uid]

            result = _audio_color_detail(color, vi, _get_clip_name(it))
            if result is None:
                continue

            smpte = _get_smpte(fps)
            tc = smpte.gettc(_get_cached(it, "start", 0))
            issues.append(_make_result("fail", track=track, timecode=tc,
                detail=result[0], reason=result[1]))

    if not issues:
        return [_make_result("pass", detail="音频越轨: 全部通过", is_summary=True)]

    results = [_make_result("fail",
        detail=f"音频越轨: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results
