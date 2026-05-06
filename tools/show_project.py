#!/usr/bin/env python3
"""项目设置快照 — 查看当前项目的完整设置信息。

用法（达芬奇运行时）:
    python3 show_project.py
    python3 show_project.py --json
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


TIMELINE_SETTINGS = [
    'timelineFrameRate', 'timelineResolutionWidth', 'timelineResolutionHeight',
    'timelineOutputResolutionWidth', 'timelineOutputResolutionHeight',
    'timelinePixelAspectRatio',
]
COLOR_SETTINGS = [
    'colorScienceMode', 'colorManagedMode', 'colorScienceModeVersion2',
    'timelineColorSpace', 'outputColorSpace',
    'toneMappingMode', 'toneMappingHDRMasteringNits',
    'lookupTableInterpolation',
]
IMAGE_SETTINGS = [
    'superScale', 'superResolution', 'videoMonitoringFormat',
    'videoMonitoringSDIStandard',
]
GENERAL_SETTINGS = [
    'workingFrameRate', 'videoBitDepth',
    'imageRetentionMode', 'thumbnailsMode',
]
RENDER_SETTINGS = [
    'renderResizeFilter', 'optimizedMediaFormat', 'proxyMediaFormat',
]


def main():
    resolve = dvr.scriptapp('Resolve')
    if not resolve:
        print('❌ 达芬奇没连上')
        return

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        print('❌ 没打开项目')
        return

    timeline = project.GetCurrentTimeline()

    json_out = '--json' in sys.argv

    data = {
        'product': resolve.GetProductName(),
        'version': resolve.GetVersionString(),
        'current_page': resolve.GetCurrentPage(),
        'project': project.GetName(),
        'timeline': timeline.GetName() if timeline else '(无)',
    }

    # 数据库
    db = pm.GetCurrentDatabase()
    data['database'] = db

    # 时间线条目
    tc = project.GetTimelineCount()
    data['timeline_count'] = tc

    # 项目设置
    all_settings = TIMELINE_SETTINGS + COLOR_SETTINGS + IMAGE_SETTINGS + GENERAL_SETTINGS + RENDER_SETTINGS
    settings = {}
    for key in all_settings:
        try:
            val = project.GetSetting(key)
            if val is not None and val != '':
                settings[key] = val
        except:
            pass
    data['settings'] = settings

    # 时间线设置
    if timeline:
        tl_settings = {}
        for key in ['timelineFrameRate', 'timelineIn', 'timelineOut',
                     'timelineStartTimecode']:
            try:
                val = timeline.GetSetting(key)
                if val is not None and val != '':
                    tl_settings[key] = val
            except:
                pass
        tl_settings['start_frame'] = timeline.GetStartFrame()
        tl_settings['end_frame'] = timeline.GetEndFrame()
        tl_settings['track_count'] = {
            'video': timeline.GetTrackCount('video'),
            'audio': timeline.GetTrackCount('audio'),
            'subtitle': timeline.GetTrackCount('subtitle'),
        }
        data['timeline_settings'] = tl_settings

    # 当前渲染设置
    fmt_codec = project.GetCurrentRenderFormatAndCodec()
    render_mode = project.GetCurrentRenderMode()
    data['render'] = {
        'format_codec': fmt_codec,
        'mode': 'Individual clips' if render_mode == 0 else 'Single clip',
    }

    if json_out:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    # ── 文本输出 ──
    print(f'达芬奇: {data["version"]}')
    print(f'当前页: {data["current_page"]}')
    print(f'数据库: {db.get("DbType", "?")} / {db.get("DbName", "?")}')
    print()
    print(f'项目: {data["project"]}')
    print(f'时间线: {data["timeline"]}（共 {tc} 条）')
    print()

    if timeline:
        ts = data['timeline_settings']
        print('── 时间线 ──')
        print(f'  帧范围: {ts["start_frame"]} — {ts["end_frame"]}')
        print(f'  轨道: V{ts["track_count"]["video"]} A{ts["track_count"]["audio"]} S{ts["track_count"]["subtitle"]}')
        if ts.get('timelineFrameRate'):
            print(f'  帧率: {ts["timelineFrameRate"]} fps')
        print()

    print('── 项目设置 ──')
    s = settings
    for group_name, group_keys in [
        ('时间线/分辨率', TIMELINE_SETTINGS),
        ('色彩科学', COLOR_SETTINGS),
        ('图像/监看', IMAGE_SETTINGS),
        ('通用', GENERAL_SETTINGS),
    ]:
        printed = False
        for key in group_keys:
            if key in s:
                if not printed:
                    print(f'  [{group_name}]')
                    printed = True
                print(f'    {key}: {s[key]}')
    print()

    print(f'── 渲染 ──')
    print(f'  格式: {fmt_codec.get("format", "?")} / {fmt_codec.get("codec", "?")}')
    print(f'  模式: {data["render"]["mode"]}')
    print()


if __name__ == '__main__':
    main()
