# -*- coding: utf-8 -*-
"""
时间线检查 — 配置
"""

__version__ = "2.0.24"
__channel__ = "dev"

def version_string():
    return f"{__version__}{'-' + __channel__ if __channel__ else ''}"

# ── SMB 常量 ──
import os as _os
SMB_MOUNT = "/Volumes/MYJC"
SMB_SCRIPTS = _os.path.join(SMB_MOUNT, "06_Software", "达芬奇脚本")
SMB_PLUGIN = _os.path.join(SMB_SCRIPTS, "交付自检工具")

# ── 默认阈值 ──
DEFAULT_CLAMP_THRESHOLD = 5
DEFAULT_BLACK_FRAME_SEC = 1.0

# ── 轨道预设 ──
# 视频轨：5轨，全部启用
VIDEO_TRACK_PRESET = [
    {"name": "视频 1", "enabled": True},
    {"name": "视频 2", "enabled": True},
    {"name": "视频 3", "enabled": True},
    {"name": "视频 4", "enabled": True},
    {"name": "视频 5", "enabled": True},
]

# 字幕轨：1轨，名称固定，启用
SUBTITLE_TRACK_PRESET = [
    {"name": "字幕 1", "enabled": True},
]

# 音频轨预设（对应 Fairlight 交付总线设置）
AUDIO_TRACK_PRESET = [
    {"name": "VO 1",   "subtype": "stereo", "enabled": True},
    {"name": "VO 2",   "subtype": "stereo", "enabled": True},
    {"name": "OS 3",   "subtype": "stereo", "enabled": True},
    {"name": "SFX 4",  "subtype": "stereo", "enabled": True},
    {"name": "SFX 5",  "subtype": "stereo", "enabled": True},
    {"name": "SFX 6",  "subtype": "stereo", "enabled": True},
    {"name": "SFX 7",  "subtype": "stereo", "enabled": True},
    {"name": "BGM 8",  "subtype": "stereo", "enabled": True},
    {"name": "BGM 9",  "subtype": "stereo", "enabled": True},
    {"name": "BGM 10", "subtype": "stereo", "enabled": True},
]

# 向后兼容
DEFAULT_SUBTITLE_TRACKS = len(SUBTITLE_TRACK_PRESET)
DEFAULT_VIDEO_TRACKS = len(VIDEO_TRACK_PRESET)
DEFAULT_AUDIO_TRACKS = len(AUDIO_TRACK_PRESET)
