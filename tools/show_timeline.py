#!/usr/bin/env python3
"""时间线快照 — 查看当前 IO 范围内所有视频轨的完整片段信息。

涵盖 TimelineItem + MediaPoolItem 所有可读数据，一次性获取到位。

用法（达芬奇运行时）:
    python3 show_timeline.py              # 当前 IO 范围
    python3 show_timeline.py --all        # 全时间线
    python3 show_timeline.py --v1         # 只看 V1
    python3 show_timeline.py --full       # 含完整 MediaPoolItem 元数据
    python3 show_timeline.py --json       # JSON 输出（给程序消费）
"""

import sys
import os
import json

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import _env
_env.setup()

import DaVinciResolveScript as dvr

SPEED_TOLERANCE = 0.02  # 2% 以内不算变速
MIN_SOURCE_DUR = 0.08    # 源时长 < 2帧 → 静帧/调整片段，不检测变速

# 达芬奇官方枚举映射（来自 Resolve API README.txt）
COMPOSITE_NAMES = {
    0: "正常", 1: "添加", 2: "减去", 3: "差值", 4: "正片叠底",
    5: "滤色", 6: "叠加", 7: "强光", 8: "柔光",
    9: "变暗", 10: "变亮", 11: "颜色减淡", 12: "颜色加深",
    13: "排除", 14: "色相", 15: "饱和度", 16: "着色",
    17: "亮度遮罩", 18: "划分", 19: "线性减淡", 20: "线性加深",
    21: "线性光", 22: "亮光", 23: "点光", 24: "实色混合",
    25: "较亮颜色", 26: "较暗颜色", 27: "前景", 28: "Alpha",
    29: "反向Alpha", 30: "亮度", 31: "反向亮度",
}
RETIME_NAMES = {0: "项目设置", 1: "邻近", 2: "帧混合", 3: "光流法"}
VERSION_TYPE_NAMES = {0: "本地", 1: "远程"}

# ── 辅助函数 ────────────────────────────────────────────


def safe_call(fn):
    """安全调用，返回 (value, error)"""
    try:
        return fn(), None
    except Exception as e:
        return None, str(e)


def get_speed_info(item, timeline_fps):
    """返回 {'label', 'ratio', 'retime_process'} 或 None。
    基于源时间（秒）vs 时间线时间（秒）计算，自动抵消帧率差异。"""
    try:
        src_start = safe_call(item.GetSourceStartTime)[0]
        src_end = safe_call(item.GetSourceEndTime)[0]
        if src_start is None or src_end is None:
            return None
        src_dur_sec = src_end - src_start
        if src_dur_sec <= 0:
            return None
        # 源时长 < 2帧 → 静帧/调整片段，非真正变速
        if src_dur_sec < MIN_SOURCE_DUR:
            return None
        tl_dur_frames = safe_call(item.GetDuration)[0]
        if tl_dur_frames is None or timeline_fps is None:
            return None
        tl_dur_sec = tl_dur_frames / timeline_fps

        ratio = tl_dur_sec / src_dur_sec  # >1 = 慢放, <1 = 快放
        if abs(ratio - 1.0) < SPEED_TOLERANCE:
            return None

        props = safe_call(item.GetProperty)[0] or {}
        retime = props.get('RetimeProcess', 0)

        # Resolve UI 显示速度百分比 = 1/ratio
        speed_pct = round(1 / ratio * 100, 1)
        retime_label = RETIME_NAMES.get(retime, f'?{retime}')
        label = f'{speed_pct}%({retime_label})'
        return {'label': label, 'ratio': round(ratio, 4), 'speed_pct': speed_pct, 'retime_process': retime}
    except Exception:
        return None


def get_clip_data(item, timeline_fps, include_full_meta=False):
    """提取一个 TimelineItem 的全部可用数据。"""
    data = {}

    # ── TimelineItem 层 ──
    data['name'] = item.GetName()
    data['unique_id'] = safe_call(item.GetUniqueId)[0]
    data['start'] = safe_call(item.GetStart)[0]
    data['end'] = safe_call(item.GetEnd)[0]
    data['duration'] = safe_call(item.GetDuration)[0]
    data['color'] = safe_call(item.GetClipColor)[0] or ''
    data['enabled'] = safe_call(item.GetClipEnabled)[0]
    data['track'] = safe_call(item.GetTrackTypeAndIndex)[0]  # ['video', 1]

    # 源帧范围
    data['source_start_frame'] = safe_call(item.GetSourceStartFrame)[0]
    data['source_end_frame'] = safe_call(item.GetSourceEndFrame)[0]
    data['source_start_time'] = safe_call(item.GetSourceStartTime)[0]
    data['source_end_time'] = safe_call(item.GetSourceEndTime)[0]
    data['left_offset'] = safe_call(item.GetLeftOffset)[0]
    data['right_offset'] = safe_call(item.GetRightOffset)[0]

    # 变速（基于秒级时间，自动抵消帧率差异）
    speed = get_speed_info(item, timeline_fps)
    data['speed'] = speed

    # Transform 属性（来自 GetProperty）
    props = safe_call(item.GetProperty)[0] or {}
    data['transform'] = {
        'pan': props.get('Pan', 0),
        'zoom_x': props.get('ZoomX', 1),
        'zoom_y': props.get('ZoomY', 1),
        'rotation': props.get('RotationAngle', 0),
        'opacity': props.get('Opacity', 100),
        'composite_mode': props.get('CompositeMode', 0),
        'flip_x': props.get('FlipX', False),
        'flip_y': props.get('FlipY', False),
        'crop_left': props.get('CropLeft', 0),
        'crop_right': props.get('CropRight', 0),
        'crop_top': props.get('CropTop', 0),
        'crop_bottom': props.get('CropBottom', 0),
        'retime_process': props.get('RetimeProcess', 0),
        'motion_estimation': props.get('MotionEstimation', 0),
        'scaling': props.get('Scaling', 0),
    }

    # 标记
    markers = safe_call(item.GetMarkers)[0] or {}
    data['markers'] = markers

    # 旗标
    flags = safe_call(item.GetFlags)[0] or {}
    flag_list = safe_call(item.GetFlagList)[0] or []
    data['flags'] = list(flags.keys()) if flags else flag_list

    # 链接片段数
    linked = safe_call(item.GetLinkedItems)[0] or []
    data['linked_items'] = len(linked)

    # 版本
    cv = safe_call(item.GetCurrentVersion)[0] or {}
    data['current_version'] = cv

    # 枚举版本列表（本地+远程），跳过默认单版本
    version_count = 0
    version_types = []
    for vt in [0, 1]:
        names = safe_call(lambda: item.GetVersionNameList(vt))[0] or []
        if len(names) > 1:
            version_count += len(names)
            version_types.append(f'{VERSION_TYPE_NAMES.get(vt, vt)}×{len(names)}')
    data['version_summary'] = f'{version_count}版本({" + ".join(version_types)})' if version_count > 1 else ''

    # Fusion
    data['fusion_comp_count'] = safe_call(item.GetFusionCompCount)[0] or 0
    data['num_nodes'] = safe_call(item.GetNumNodes)[0] or 0

    # 音频
    data['voice_isolation'] = safe_call(item.GetVoiceIsolationState)[0] or {}

    # ── MediaPoolItem 层 ──
    mp_item = safe_call(item.GetMediaPoolItem)[0]
    if mp_item:
        mp_data = {}
        props = safe_call(mp_item.GetClipProperty)[0] or {}

        mp_data['file_path'] = props.get('File Path', '')
        mp_data['file_name'] = props.get('File Name', '')
        mp_data['clip_name'] = props.get('Clip Name', '')  # 媒体池中的名称（可能≠时间线显示名）
        mp_data['clip_directory'] = props.get('Clip Directory', '')
        mp_data['resolution'] = props.get('Resolution', '')
        mp_data['fps'] = props.get('FPS', '')
        mp_data['video_codec'] = props.get('Video Codec', '')
        mp_data['audio_codec'] = props.get('Audio Codec', '')
        mp_data['format'] = props.get('Format', '')
        mp_data['type'] = props.get('Type', '')  # '视频 + 音频' 等
        mp_data['audio_ch'] = props.get('Audio Ch', '')
        mp_data['sample_rate'] = props.get('Sample Rate', '')
        mp_data['bit_depth'] = props.get('Bit Depth', '')
        mp_data['duration_tc'] = props.get('Duration', '')
        mp_data['total_frames'] = props.get('Frames', '')
        mp_data['start_tc'] = props.get('Start TC', '')
        mp_data['end_tc'] = props.get('End TC', '')
        mp_data['data_level'] = props.get('Data Level', '')
        mp_data['field_dominance'] = props.get('Field Dominance', '')
        mp_data['par'] = props.get('PAR', '')
        mp_data['super_scale'] = props.get('Super Scale', 1)
        mp_data['date_created'] = props.get('Date Created', '')
        mp_data['date_modified'] = props.get('Date Modified', '')
        mp_data['usage_count'] = props.get('Usage', '')
        mp_data['online_status'] = props.get('Online Status', '')
        mp_data['input_color_space'] = props.get('Input Color Space', '')
        mp_data['proxy'] = props.get('Proxy', '')
        mp_data['proxy_media_path'] = props.get('Proxy Media Path', '')

        if include_full_meta:
            mp_data['_full'] = props

        data['media_pool'] = mp_data
    else:
        data['media_pool'] = None

    return data


# ── 格式化输出 ──────────────────────────────────────────


def print_clip(data):
    """单片段紧凑输出"""
    mp = data['media_pool'] or {}
    t = data['transform']

    # 第1行：帧范围 + 时长 + 状态标签
    tags = []
    if data['color'] == 'Orange':
        tags.append('🟠Orange')
    if not data['enabled']:
        tags.append('⏸禁用')
    if data['speed']:
        tags.append(f'⚡{data["speed"]["label"]}')
    if data['markers']:
        mk_colors = set(m['color'] for m in data['markers'].values())
        tags.append(f'📍{",".join(mk_colors)}标记×{len(data["markers"])}')
    if data['flags']:
        tags.append(f'🚩{",".join(data["flags"])}')
    if data['linked_items'] > 0:
        tags.append(f'🔗×{data["linked_items"]}')
    if t['composite_mode'] != 0:
        cm_name = COMPOSITE_NAMES.get(t['composite_mode'], f'模式{t["composite_mode"]}')
        tags.append(f'合成:{cm_name}')
    if t['opacity'] != 100:
        tags.append(f'透明:{t["opacity"]:.0f}%')
    if mp and mp.get('online_status') and mp['online_status'] != 'Online':
        tags.append(f'⚠{mp["online_status"]}')
    if data.get('version_summary'):
        tags.append(f'🎨{data["version_summary"]}')

    tag_str = ' '.join(tags) if tags else '-'
    print(f'  [{data["start"]:>5}-{data["end"]:<5}] {data["duration"]:>4}帧  {tag_str}')

    # 第2行：文件名（如与媒体池名不同则标注）
    print(f'           {data["name"]}')
    if mp and mp.get('clip_name') and mp['clip_name'] != data['name']:
        print(f'           ↳ 真实文件: {mp["clip_name"]}')

    # 第3行：媒体信息（如果有）
    if mp:
        info_parts = []
        if mp.get('resolution'):
            info_parts.append(mp['resolution'])
        if mp.get('fps'):
            info_parts.append(f'{mp["fps"]}fps')
        if mp.get('video_codec'):
            info_parts.append(mp['video_codec'])
        if mp.get('format'):
            info_parts.append(mp['format'])
        if mp.get('type'):
            info_parts.append(mp['type'])
        if info_parts:
            print(f'           📁 {" · ".join(info_parts)}')

        # 代理媒体
        if mp.get('proxy_media_path'):
            print(f'           🔄 代理: {mp["proxy_media_path"]}')

    # 第4行：标记详情
    if data['markers']:
        for frame, mk in sorted(data['markers'].items()):
            note = mk.get('note', '')
            name = mk.get('name', '')
            text = name or note
            print(f'           📍 @{frame}f [{mk["color"]}] {text}')


def print_text(data):
    """简洁输出"""
    print(f'  [{data["start"]:>5}-{data["end"]:<5}] {data["duration"]:>4}帧  {data["name"]}')
    if data['markers']:
        for frame, mk in sorted(data['markers'].items()):
            print(f'           📍 @{frame}f [{mk["color"]}] {mk.get("name", mk.get("note", ""))}')


# ── 主入口 ──────────────────────────────────────────────


def main():
    resolve = dvr.scriptapp('Resolve')
    if not resolve:
        print('❌ 达芬奇没连上')
        return

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print('❌ 没打开项目')
        return

    timeline = project.GetCurrentTimeline()
    if not timeline:
        print('❌ 没打开时间线')
        return

    show_all = '--all' in sys.argv
    v1_only = '--v1' in sys.argv
    include_full = '--full' in sys.argv
    json_out = '--json' in sys.argv

    # 范围
    mark = timeline.GetMarkInOut()
    if mark and mark.get('video') and not show_all:
        io_in = mark['video'].get('in', 0)
        io_out = mark['video'].get('out', 0)
        if io_in >= io_out:  # IO 无效
            io_in, io_out = 0, timeline.GetEndFrame()
    else:
        io_in = 0
        io_out = timeline.GetEndFrame()

    # 收集所有片段
    all_clips = []
    timeline_fps = timeline.GetSetting('timelineFrameRate')
    video_tracks = timeline.GetTrackCount('video')
    track_iter = [(1, 'video')] if v1_only else [(i, 'video') for i in range(1, video_tracks + 1)]

    for ti, tt in track_iter:
        items = timeline.GetItemListInTrack(tt, ti)
        if not items:
            continue
        for item in items:
            if item.GetStart() < io_out and item.GetEnd() > io_in:
                data = get_clip_data(item, timeline_fps, include_full)
                data['_track_name'] = timeline.GetTrackName(tt, ti)
                all_clips.append(data)

    if json_out:
        # JSON 输出
        output = {
            'project': project.GetName(),
            'timeline': timeline.GetName(),
            'fps': timeline_fps,
            'io': {'in': io_in, 'out': io_out},
            'clips': all_clips,
            'summary': {
                'total': len(all_clips),
                'orange': sum(1 for c in all_clips if c['color'] == 'Orange'),
                'disabled': sum(1 for c in all_clips if not c['enabled']),
                'speed_changed': sum(1 for c in all_clips if c.get('speed')),
                'with_markers': sum(1 for c in all_clips if c.get('markers')),
            }
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return

    # 文本输出
    print(f'项目: {project.GetName()}')
    print(f'时间线: {timeline.GetName()}')
    print(f'帧率: {timeline_fps} fps')
    if show_all:
        print(f'范围: 全时间线 (0 — {io_out})')
    else:
        print(f'IO: {io_in} — {io_out} ({io_out - io_in} 帧)')
    print()

    # 按轨道分组输出
    current_track = None
    track_clips = []
    stats = {'total': 0, 'orange': 0, 'disabled': 0, 'speed': 0, 'markers': 0}

    for data in all_clips:
        tn = data['_track_name']
        ti = data['track'][1] if data['track'] else '?'
        if tn != current_track:
            current_track = tn
            track_clips = []

        track_clips.append(data)
        stats['total'] += 1
        if data['color'] == 'Orange':
            stats['orange'] += 1
        if not data['enabled']:
            stats['disabled'] += 1
        if data.get('speed'):
            stats['speed'] += 1
        if data.get('markers'):
            stats['markers'] += 1

        # 输出（在轨道切换时输出标题）
        if len(track_clips) == 1:
            print(f'━━━ V{ti} ({tn}) ━━━')

        # 文本片段简化输出
        if data['media_pool'] is None and data['name'] == '文本':
            print_text(data)
        else:
            print_clip(data)
        print()

    # 汇总
    parts = [f'共 {stats["total"]} 个片段']
    if stats['orange']:
        parts.append(f'Orange: {stats["orange"]}')
    if stats['disabled']:
        parts.append(f'禁用: {stats["disabled"]}')
    if stats['speed']:
        parts.append(f'变速: {stats["speed"]}')
    if stats['markers']:
        parts.append(f'有标记: {stats["markers"]}')
    print(f'═══ {"，".join(parts)} ═══')


if __name__ == '__main__':
    main()
