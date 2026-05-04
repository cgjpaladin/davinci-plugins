#!/usr/bin/env python3
"""媒体池快照 — 查看媒体池结构、文件夹和素材属性。

用法（达芬奇运行时）:
    python3 show_mediapool.py              # 列出当前文件夹结构
    python3 show_mediapool.py --clips      # 列出当前文件夹内的素材详情
    python3 show_mediapool.py --tree       # 完整文件夹树
    python3 show_mediapool.py --json       # JSON 输出
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


CLIP_KEYS = [
    'File Name', 'File Path', 'Clip Name', 'Resolution', 'FPS',
    'Video Codec', 'Format', 'Type', 'Duration', 'Frames',
    'Audio Ch', 'Sample Rate', 'Audio Codec',
    'Proxy', 'Proxy Media Path', 'Online Status',
    'Date Created', 'Date Modified', 'Usage',
    'Super Scale', 'Input Color Space', 'Data Level',
]


def folder_tree(folder, indent=0, max_depth=3):
    """递归输出文件夹树。"""
    if indent > max_depth:
        return
    name = folder.GetName()
    clips = folder.GetClipList() or []
    subs = folder.GetSubFolderList() or []

    prefix = '  ' * indent
    stale = '⚠' if folder.GetIsFolderStale() else ''
    print(f'{prefix}📁 {name}{stale} ({len(clips)}片段, {len(subs)}子文件夹)')

    for sub in subs:
        folder_tree(sub, indent + 1, max_depth)


def clip_summary(mp_item):
    """素材关键信息一行。"""
    props = mp_item.GetClipProperty() or {}
    name = props.get('File Name', mp_item.GetName())
    res = props.get('Resolution', '?')
    fps = props.get('FPS', '?')
    codec = props.get('Video Codec', props.get('Format', '?'))
    dur = props.get('Duration', '?')
    t = props.get('Type', '?')
    online = props.get('Online Status', '')
    proxy = '🔄' if props.get('Proxy Media Path') else ''
    offline = '⚠Offline' if online and online != 'Online' else ''
    color = mp_item.GetClipColor() or ''
    markers = mp_item.GetMarkers() or {}
    mk = f'📍×{len(markers)}' if markers else ''

    parts = [f'{res}', f'{fps}fps', codec, dur, t]
    info = ' · '.join(p for p in parts if p and p != '?')
    extras = ' '.join(x for x in [proxy, offline, mk, f'#{color}' if color else ''] if x)
    return f'  {name}\n    {info}  {extras}'


def main():
    resolve = dvr.scriptapp('Resolve')
    if not resolve:
        print('❌ 达芬奇没连上')
        return

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print('❌ 没打开项目')
        return

    mp = project.GetMediaPool()
    current = mp.GetCurrentFolder()
    root = mp.GetRootFolder()

    show_clips = '--clips' in sys.argv
    show_tree = '--tree' in sys.argv
    json_out = '--json' in sys.argv

    print(f'项目: {project.GetName()}')
    print(f'当前文件夹: {current.GetName() if current else "?"}')

    if json_out:
        def folder_to_dict(f):
            return {
                'name': f.GetName(),
                'clips': [c.GetName() for c in (f.GetClipList() or [])],
                'subfolders': [folder_to_dict(s) for s in (f.GetSubFolderList() or [])],
            }
        data = {
            'project': project.GetName(),
            'current_folder': current.GetName() if current else None,
            'root': folder_to_dict(root),
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if show_tree:
        print('\n── 文件夹树 ──')
        folder_tree(root)
        print()
        return

    if show_clips:
        print(f'\n── {current.GetName()} 内素材 ──')
        clips = current.GetClipList() or []
        if not clips:
            print('  (空)')
        for clip in clips:
            print(clip_summary(clip))
        print(f'\n共 {len(clips)} 个')
        return

    # 默认：当前文件夹一览
    print(f'\n── 当前文件夹内容 ──')
    subs = current.GetSubFolderList() or []
    clips = current.GetClipList() or []
    print(f'  子文件夹: {len(subs)}')
    for s in subs:
        s_clips = s.GetClipList() or []
        print(f'    📁 {s.GetName()} ({len(s_clips)}片段)')
    print(f'  素材: {len(clips)}')
    for clip in clips[:20]:
        print(f'    🎬 {clip.GetName()}')
    if len(clips) > 20:
        print(f'    ... 还有 {len(clips) - 20} 个，用 --clips 查看详情')


if __name__ == '__main__':
    main()
