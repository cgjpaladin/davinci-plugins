# -*- coding: utf-8 -*-
"""
SMPTE 时码 ↔ 帧数 双向转换工具。

v2.0: 底层切换 DFTT Timecode（北电影视技术系，Fraction 精度）
v1.0: Batch_io_Pro.py (张来吃)，Duncan/Heidelberger 算法
"""

from mappings import RESOLVE_FPS_MAPPING  # noqa: F401 — 向后兼容
from dftt_timecode import DfttTimecode as _DTC


class SMPTE:
    """Frames to SMPTE timecode converter and reverse.

    Usage:
        smpte = SMPTE()
        smpte.fps = 23.976
        smpte.df = False

        frames = smpte.getframes("01:23:45:12")  # timecode -> frames
        tc     = smpte.gettc(12345)               # frames -> timecode
    """

    def __init__(self):
        self.fps = 24.0
        self.df = False  # drop-frame flag

    def getframes(self, tc: str) -> int:
        """Convert SMPTE timecode string to frame count."""
        # 保留旧版帧号取值范围校验
        if int(tc[9:]) > self.fps:
            raise ValueError(
                f"SMPTE timecode to frame rate mismatch: tc={tc}, fps={self.fps}"
            )
        return _DTC(tc, fps=self.fps, drop_frame=self.df).framecount

    def gettc(self, frames: int) -> str:
        """Convert frame count to SMPTE timecode string."""
        frames = abs(int(frames))
        return _DTC(str(frames), fps=self.fps,
                    timecode_type="frame",
                    drop_frame=self.df).smpte


# ══════════════════════════════════════
# v1.0 旧算法存档（2026-05-13 替换为 DFTT）
# 如需回退，取消注释下方并删除 DFTT import
# ══════════════════════════════════════
# class _OldSMPTE:
#     def __init__(self):
#         self.fps = 24.0
#         self.df = False
#     def getframes(self, tc):
#         if int(tc[9:]) > self.fps:
#             raise ValueError(f"Mismatch: tc={tc}, fps={self.fps}")
#         hours = int(tc[:2]); minutes = int(tc[3:5])
#         seconds = int(tc[6:8]); frames = int(tc[9:])
#         totalMinutes = int(60 * hours + minutes)
#         if self.df:
#             dropFrames = int(round(self.fps * 0.066666))
#             timeBase = int(round(self.fps))
#             hourFrames = int(timeBase * 60 * 60)
#             minuteFrames = int(timeBase * 60)
#             frm = int((hourFrames*hours+minuteFrames*minutes+timeBase*seconds+frames)
#                       -(dropFrames*(totalMinutes-(totalMinutes//10))))
#         else:
#             self.fps = int(round(self.fps))
#             frm = int((totalMinutes * 60 + seconds) * self.fps + frames)
#         return frm
#     def gettc(self, frames):
#         frames = abs(frames)
#         if self.df:
#             spacer, spacer2 = ':', ';'
#             dropFrames = int(round(self.fps * 0.066666))
#             framesPerHour = int(round(self.fps * 3600))
#             framesPer24Hours = framesPerHour * 24
#             framesPer10Minutes = int(round(self.fps * 600))
#             framesPerMinute = int(round(self.fps) * 60 - dropFrames)
#             frames = frames % framesPer24Hours
#             d = frames // framesPer10Minutes
#             m = frames % framesPer10Minutes
#             if m > dropFrames:
#                 frames = frames + (dropFrames*9*d) + dropFrames*((m-dropFrames)//framesPerMinute)
#             else:
#                 frames = frames + dropFrames * 9 * d
#             frRound = int(round(self.fps))
#             hr = int(frames//frRound//60//60)
#             mn = int((frames//frRound//60)%60)
#             sc = int((frames//frRound)%60)
#             fr = int(frames % frRound)
#         else:
#             self.fps = int(round(self.fps))
#             spacer = spacer2 = ':'
#             frHour = self.fps * 3600; frMin = self.fps * 60
#             hr = int(frames // frHour)
#             mn = int((frames - hr*frHour) // frMin)
#             sc = int((frames - hr*frHour - mn*frMin) // self.fps)
#             fr = int(round(frames - hr*frHour - mn*frMin - sc*self.fps))
#         return (str(hr).zfill(2)+spacer+str(mn).zfill(2)+spacer+
#                 str(sc).zfill(2)+spacer2+str(fr).zfill(2))
