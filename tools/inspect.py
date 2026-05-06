#!/usr/bin/env python3
"""
tools/inspect.py — 达芬奇现场速览
─────────────────────────────────
一条命令回到开发现场。默认显示汇总，用 flag 深入。

用法:
  python3 tools/inspect.py              默认汇总
  python3 tools/inspect.py --timeline   IO 内片段全貌
  python3 tools/inspect.py --project    项目设置
  python3 tools/inspect.py --mediapool  媒体池结构
  python3 tools/inspect.py --api        常用 API 速查
  python3 tools/inspect.py --all        全部
  python3 tools/inspect.py --json       JSON 输出（给程序读）
"""
import sys, os, json, argparse

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import _env
_env.setup()

import DaVinciResolveScript as bmd


def _resolve():
    r = bmd.scriptapp("Resolve")
    if not r: raise RuntimeError("请先启动 DaVinci Resolve Studio")
    return r


# ═══════════════════════════════════════════
# 环境信息
# ═══════════════════════════════════════════

def env_info():
    r = _resolve()
    pj = r.GetProjectManager().GetCurrentProject()
    return {
        "resolve_version": r.GetVersionString(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sys.platform,
        "project": pj.GetName() if pj else None,
        "timeline": pj.GetCurrentTimeline().GetName() if pj and pj.GetCurrentTimeline() else None,
    }


# ═══════════════════════════════════════════
# 时间线 IO 片段
# ═══════════════════════════════════════════

def timeline_io():
    r = _resolve()
    pj = r.GetProjectManager().GetCurrentProject()
    if not pj: return []
    tl = pj.GetCurrentTimeline()
    if not tl: return []
    mk = tl.GetMarkInOut()
    v = mk.get("video", {}) if mk else {}
    i_in, i_out = v.get("in", 0), v.get("out", 0)
    
    clips = []
    for t in range(1, tl.GetTrackCount("video") + 1):
        items = tl.GetItemListInTrack("video", t)
        if not items: continue
        for idx, item in enumerate(items):
            s, e = item.GetStart(), item.GetEnd()
            if i_out > i_in and (s >= i_out or e <= i_in):
                continue
            mp = item.GetMediaPoolItem()
            clips.append({
                "track": t,
                "index": idx,
                "name": item.GetName(),
                "start": s,
                "end": e,
                "color": item.GetClipColor(),
                "enabled": item.GetClipEnabled(),
                "type": mp.GetClipProperty("Type") if mp else "?",
                "file_name": mp.GetClipProperty("File Name") if mp else None,
                "file_path": mp.GetClipProperty("File Path") if mp else None,
            })
    return clips


# ═══════════════════════════════════════════
# API 速查 — 从 skill 里提取的常用签名
# ═══════════════════════════════════════════

API_CHEATSHEET = {
    "Resolve": [
        "Fusion()",
        "GetProjectManager()",
        "OpenPage('edit'|'color'|'deliver'|...)",
        "GetVersionString()",
    ],
    "Project": [
        "GetCurrentTimeline()",
        "GetTimelineByIndex(idx)",
        "GetTimelineCount()",
        "GetMediaPool()",
        "GetSetting('timelineFrameRate')",
        "LoadRenderPreset(name)",
        "SetRenderSettings({...})",
        "AddRenderJob()",
        "StartRendering()",
        "IsRenderingInProgress()",
    ],
    "Timeline": [
        "GetName()",
        "GetTrackCount('video'|'audio'|'subtitle')",
        "GetItemListInTrack('video', n) ← 两个参数！",
        "GetMarkInOut() → {video: {in, out}}",
        "SetMarkInOut(in_frame, out_frame)",
        "GetSetting('timelineFrameRate')",
    ],
    "TimelineItem": [
        "GetName()",
        "GetStart() / GetEnd()",
        "GetClipColor() → 'Orange', 'Pink', ...",
        "GetClipEnabled()",
        "GetMediaPoolItem()",
        "GetProperty('ZoomX') / SetProperty('ZoomX', v)",
        "AddMarker(frame, color, name, note, dur, customData)",
    ],
    "MediaPoolItem": [
        "GetClipProperty('File Name') ← 最稳的标识",
        "GetClipProperty('File Path')",
        "GetClipProperty('Type') → '视频', '音频', '复合', ...",
        "GetClipProperty('FPS') / GetClipProperty('Frames')",
        "GetClipProperty('Resolution')",
        "ReplaceClipPreserveSubClip(path) ← 替换源文件保留裁剪 ✅",
        "GetClipColor()",
    ],
}


# ═══════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════

def fmt_clip(c, verbose=False):
    status = "✅" if c["enabled"] else "🚫"
    if verbose:
        return (f"  V{c['track']} [{c['index']}] {status} {c['name']}\n"
                f"        {c['start']}-{c['end']} | {c['type']} | {c['color']}\n"
                f"        {c['file_name']}")
    return f"  V{c['track']} [{c['index']}] {status} {c['name']}  {c['start']}-{c['end']}  {c['type']}  {c['color']}"


def print_summary():
    env = env_info()
    clips = timeline_io()
    
    print("━" * 60)
    print(f"  达芬奇 {env['resolve_version']} | Python {env['python_version']} | {env['platform']}")
    print(f"  项目: {env['project'] or '(无)'}  |  时间线: {env['timeline'] or '(无)'}")
    print("━" * 60)
    
    if clips:
        print(f"\n  IO 内片段 ({len(clips)}):")
        for c in clips[:20]:
            print(fmt_clip(c))
        if len(clips) > 20:
            print(f"  ... 还有 {len(clips)-20} 个片段（用 --timeline 看全部）")
    else:
        io = _io_info()
        if io:
            print(f"\n  IO: {io[0]}-{io[1]}（无片段）")
        else:
            print("\n  ⚠️ 未设 IO，片段列表为空")
    
    print(f"\n  常用命令:")
    print(f"    python3 tools/inspect.py --api       API 速查")
    print(f"    python3 tools/inspect.py --timeline  片段全貌")
    print(f"    python3 tools/inspect.py --project   项目设置")
    print(f"    python3 tools/inspect.py --all       全部输出")
    print(f"    python3 tools/runner.py ui           UI 自动化测试")


def _io_info():
    r = _resolve()
    pj = r.GetProjectManager().GetCurrentProject()
    if not pj: return None
    tl = pj.GetCurrentTimeline()
    if not tl: return None
    mk = tl.GetMarkInOut()
    v = mk.get("video", {}) if mk else {}
    i_in, i_out = v.get("in", 0), v.get("out", 0)
    return (i_in, i_out) if i_out > i_in else None


def print_timeline_detail():
    clips = timeline_io()
    io = _io_info()
    print(f"IO: {io[0]}-{io[1]}" if io else "IO: (未设)")
    print(f"片段数: {len(clips)}\n")
    for c in clips:
        print(fmt_clip(c, verbose=True))
        print()


def print_api():
    print("━" * 40)
    print("  API 速查（常用方法签名）")
    print("━" * 40)
    for obj, methods in API_CHEATSHEET.items():
        print(f"\n  {obj}:")
        for m in methods:
            print(f"    .{m}")


def main():
    parser = argparse.ArgumentParser(description="达芬奇现场速览")
    parser.add_argument("--timeline", action="store_true")
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--mediapool", action="store_true")
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        env = env_info()
        clips = timeline_io()
        io = _io_info()
        print(json.dumps({
            "env": env,
            "io": {"in": io[0], "out": io[1]} if io else None,
            "clips": clips,
            "clip_count": len(clips),
        }, ensure_ascii=False, indent=2))
        return
    
    if args.api:
        print_api()
        return
    
    if args.all:
        print_summary()
        print()
        print_timeline_detail()
        print_api()
        return
    
    if args.timeline:
        print_timeline_detail()
        return
    
    # 默认：汇总
    print_summary()


if __name__ == "__main__":
    main()
