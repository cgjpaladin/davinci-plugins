# -*- coding: utf-8 -*-
"""
tools/dvr.py — 达芬奇开发标准库
───────────────────────────────
导入一次，所有脚本共用。不再在每个文件里重复 resolve()/project()/timeline()。

用法:
  from tools.dvr import resolve, project, timeline, clips, scan_io, balance
  from tools.dvr import dr, prj, tl        # 短别名

  tl.GetName()                              # 一行拿到时间线名
  for c in scan_io():                       # 一行遍历 IO 内片段
      print(c.name, c.path, c.duration)
"""
import os, sys, time, math, re
from copy import deepcopy

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import _env
_env.setup()

import DaVinciResolveScript as _bmd


# ═══════════════════════════════════════════
# 基础连接 — 每个脚本的第一步
# ═══════════════════════════════════════════

def _safe(func):
    """@safe_resolve_call 装饰器 — 自动检查 Resolve 连接状态（灵感来自 resolve-mcp）"""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        r = _bmd.scriptapp("Resolve")
        if not r:
            raise RuntimeError("请先启动 DaVinci Resolve Studio")
        return func(*args, **kwargs)
    return wrapper


def resolve():
    """获取 Resolve 对象。失败抛 RuntimeError。"""
    r = _bmd.scriptapp("Resolve")
    if not r:
        raise RuntimeError("请先启动 DaVinci Resolve Studio")
    return r


def fusion():
    """获取 Fusion 对象。"""
    f = _bmd.scriptapp("Fusion")
    if not f:
        raise RuntimeError("无法获取 Fusion 对象")
    return f


def ui_manager():
    """获取 UIManager 和 UIDispatcher。"""
    f = fusion()
    return f.UIManager, _bmd.UIDispatcher(f.UIManager)


def project():
    """获取当前项目。无项目返回 None。"""
    r = resolve()
    return r.GetProjectManager().GetCurrentProject()


def timeline():
    """获取当前时间线。无时间线返回 None。"""
    pj = project()
    return pj.GetCurrentTimeline() if pj else None


# 短别名
dr = resolve
prj = project
tl = timeline


# ═══════════════════════════════════════════
# IO 区间 — 最常用操作
# ═══════════════════════════════════════════

def get_io():
    """获取当前 IO 入出点。返回 (in_frame, out_frame)，未设返回 None。"""
    tl = timeline()
    if not tl:
        return None
    mk = tl.GetMarkInOut()
    v = mk.get("video", {}) if mk else {}
    i_in, i_out = v.get("in", 0), v.get("out", 0)
    return (i_in, i_out) if i_out > i_in else None


class ClipInfo:
    """IO 内片段的结构化信息"""
    __slots__ = ("track", "index", "item", "media_pool_item", "name",
                 "start", "end", "color", "enabled", "clip_type",
                 "file_name", "file_path", "fps", "duration", "resolution")
    
    def __init__(self, track, idx, item):
        self.track = track
        self.index = idx
        self.item = item
        self.name = item.GetName()
        self.start = item.GetStart()
        self.end = item.GetEnd()
        self.color = item.GetClipColor()
        self.enabled = item.GetClipEnabled()
        
        mp = item.GetMediaPoolItem()
        self.media_pool_item = mp
        self.clip_type = mp.GetClipProperty("Type") if mp else None
        self.file_name = mp.GetClipProperty("File Name") if mp else None
        self.file_path = mp.GetClipProperty("File Path") if mp else None
        
        if mp:
            try:
                fps = float(mp.GetClipProperty("FPS") or 24)
                frames = int(mp.GetClipProperty("Frames") or 0)
                self.fps = fps
                self.duration = frames / fps if fps > 0 else 0
            except:
                self.fps = 24.0
                self.duration = 0.0
            try:
                self.resolution = mp.GetClipProperty("Resolution")
            except:
                self.resolution = None
        else:
            self.fps = 24.0
            self.duration = 0.0
            self.resolution = None
    
    def __repr__(self):
        dur = f" {self.duration:.1f}s" if self.duration else ""
        return f"<Clip V{self.track}[{self.index}] {self.name}{dur}>"
    
    @property
    def is_video(self):
        return self.clip_type and "视频" in (self.clip_type or "")
    
    @property
    def is_compound(self):
        return self.clip_type in ("复合", "Fusion", "VFX连接")


def scan_io(color_filter=None, skip_disabled=True, skip_compound=True):
    """扫描 IO 区间内所有片段，返回 ClipInfo 列表。
    
    Args:
      color_filter: 只返回指定颜色的片段（如 'Orange'），None=全部
      skip_disabled: 跳过禁用的片段
      skip_compound: 跳过复合/Fusion/VFX片段
    """
    tl = timeline()
    if not tl:
        return []
    io = get_io()
    if not io:
        return []
    i_in, i_out = io
    
    result = []
    seen = set()
    
    for t in range(1, tl.GetTrackCount("video") + 1):
        items = tl.GetItemListInTrack("video", t)
        if not items:
            continue
        for idx, item in enumerate(items):
            s, e = item.GetStart(), item.GetEnd()
            if s >= i_out or e <= i_in:
                continue
            
            c = ClipInfo(t, idx, item)
            
            # 去重（同名同色同位置的片段）
            key = (c.name, c.start, c.end, c.color)
            if key in seen:
                continue
            seen.add(key)
            
            if color_filter and c.color != color_filter:
                continue
            if skip_disabled and not c.enabled:
                continue
            if skip_compound and c.is_compound:
                continue
            
            result.append(c)
    
    return result


# ═══════════════════════════════════════════
# 余额查询
# ═══════════════════════════════════════════

def balance(adapter_config=None):
    """查询鬼手余额，返回 (points, error)。"""
    try:
        if adapter_config is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "config", "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕/config.py")
            config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config)
            adapter_config = deepcopy(config.ADAPTER_CONFIGS["ghostcut"])
        
        spec2 = importlib.util.spec_from_file_location(
            "ghostcut_adapter", "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕/adapters/ghostcut.py")
        ghostcut = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(ghostcut)
        
        adapter = ghostcut.GhostCutAdapter(adapter_config)
        bal = adapter.get_balance()
        now_ms = time.time() * 1000
        pts = sum(
            a["pointBalance"] for a in bal.get("pointAssets", [])
            if a["pointBalance"] > 0 and a.get("expireTime", now_ms + 1) > now_ms
        )
        return pts, None
    except Exception as e:
        return 0, str(e)


# ═══════════════════════════════════════════
# 快捷打印
# ═══════════════════════════════════════════

def status():
    """打印当前状态摘要"""
    r = resolve()
    pj = project()
    tl = timeline()
    io = get_io()
    pts, err = balance()
    
    lines = [
        f"Resolve:  {r.GetVersionString()}",
        f"Project:  {pj.GetName() if pj else '(无)'}",
        f"Timeline: {tl.GetName() if tl else '(无)'}",
    ]
    if io:
        lines.append(f"IO:       {io[0]}-{io[1]} ({io[1]-io[0]} frames)")
        clips = scan_io()
        lines.append(f"Clips:    {len(clips)} in IO")
        for c in clips[:5]:
            lines.append(f"          {c}")
    if pts:
        lines.append(f"Balance:  {pts:.1f} 点 (¥{pts*0.19:.2f})")
    elif err:
        lines.append(f"Balance:  查询失败 ({err[:50]})")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════
# 帧率映射（来自 Batch_io_Pro.py + 官方文档）
# ═══════════════════════════════════════════

FPS_MAP = {
    '16': 16.0, '18': 18.0,
    '23': 23.976, '23.976': 23.976, '24': 24.0, '24.0': 24.0,
    '25': 25.0, '29': 29.97, '29.97': 29.97,
    '30': 30.0, '30.0': 30.0, '47': 47.952, '47.952': 47.952,
    '48': 48.0, '50': 50.0,
    '59': 59.94, '59.94': 59.94, '60': 60.0,
    '72': 72.0, '95': 95.904, '95.904': 95.904,
    '96': 96.0, '100': 100.0,
    '119': 119.88, '119.88': 119.88, '120': 120.0,
}


def fps():
    """获取当前时间线帧率（float）。"""
    tl = timeline()
    if not tl:
        return 24.0
    try:
        fps_str = str(tl.GetSetting("timelineFrameRate"))
        return FPS_MAP.get(fps_str, float(fps_str))
    except:
        return 24.0


def frames_to_tc(frames, drop_frame=None):
    """帧号 → SMPTE 时码字符串 (HH:MM:SS:FF)。"""
    fr = fps()
    if drop_frame is None:
        try:
            drop_frame = bool(int(timeline().GetSetting("timelineDropFrameTimecode")))
        except:
            drop_frame = False
    
    fr_round = int(round(fr))
    frames = abs(int(frames))
    
    if drop_frame:
        drop = int(round(fr * 0.066666))
        frames_per_10min = int(round(fr * 600))
        frames_per_min = fr_round * 60 - drop
        d = frames // frames_per_10min
        m = frames % frames_per_10min
        if m > drop:
            frames += drop * 9 * d + drop * ((m - drop) // frames_per_min)
        else:
            frames += drop * 9 * d
    
    hr = frames // (fr_round * 3600)
    mn = (frames // (fr_round * 60)) % 60
    sc = (frames // fr_round) % 60
    fr2 = frames % fr_round
    
    sep = ";" if drop_frame else ":"
    return f"{hr:02d}:{mn:02d}:{sc:02d}{sep}{fr2:02d}"


# ═══════════════════════════════════════════
# 片段颜色（来自 Batch_io_Pro.py）
# ═══════════════════════════════════════════

CLIP_COLORS = {
    'Orange': (0, 110, 235), 'Apricot': (51, 168, 255),
    'Yellow': (28, 169, 226), 'Lime': (21, 198, 159),
    'Olive': (32, 153, 94), 'Green': (100, 143, 68),
    'Teal': (153, 152, 0), 'Navy': (119, 50, 31),
    'Blue': (161, 118, 67), 'Purple': (160, 115, 153),
    'Violet': (141, 87, 208), 'Pink': (181, 140, 233),
    'Tan': (151, 176, 185), 'Beige': (119, 160, 198),
    'Brown': (0, 102, 153), 'Chocolate': (63, 90, 140),
}


# ═══════════════════════════════════════════
# 设置持久化（来自 导出时间线标记.lua 的灵感）
# ═══════════════════════════════════════════

import json as _json

def load_settings(name="runner"):
    """读取持久化设置（JSON 文件，存于脚本同目录）。"""
    settings_path = os.path.join(_here, f".{name}_settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                return _json.load(f)
    except:
        pass
    return {}


def save_settings(data, name="runner"):
    """写入持久化设置。"""
    settings_path = os.path.join(_here, f".{name}_settings.json")
    try:
        with open(settings_path, "w") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass


# ═══════════════════════════════════════════
# 轨道操作（灵感来自 dvrctl）
# ═══════════════════════════════════════════

def lock_track(track_type="video", index=1, lock=True):
    """锁定/解锁指定轨道。"""
    tl = timeline()
    if not tl:
        return False
    return tl.SetTrackLock(track_type, index, lock)


def lock_all_tracks(track_type="video", lock=True):
    """锁定/解锁所有指定类型的轨道。"""
    tl = timeline()
    if not tl:
        return False
    count = tl.GetTrackCount(track_type)
    for i in range(1, int(count) + 1):
        tl.SetTrackLock(track_type, i, lock)
    return True


def delete_tracks(track_type="video", keep=1):
    """删除指定类型轨道，保留前 keep 条。"""
    tl = timeline()
    if not tl:
        return False
    count = int(tl.GetTrackCount(track_type))
    for i in range(count, keep, -1):
        tl.DeleteTrack(track_type, i)
    return True


if __name__ == "__main__":
    print(status())
