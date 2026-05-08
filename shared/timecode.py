# -*- coding: utf-8 -*-
"""
SMPTE 时码 ↔ 帧数 双向转换工具。

来源：Batch_io_Pro.py (张来吃 v2.0.4)
算法：Duncan/Heidelberger 丢帧时码方法
引用：https://github.com/IgorRidanovic/smpte
"""

from mappings import RESOLVE_FPS_MAPPING  # noqa: F401 — 向后兼容，其他模块可能直接 import 从此处


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
        if int(tc[9:]) > self.fps:
            raise ValueError(
                f"SMPTE timecode to frame rate mismatch: tc={tc}, fps={self.fps}"
            )

        hours = int(tc[:2])
        minutes = int(tc[3:5])
        seconds = int(tc[6:8])
        frames = int(tc[9:])

        totalMinutes = int(60 * hours + minutes)

        if self.df:
            dropFrames = int(round(self.fps * 0.066666))
            timeBase = int(round(self.fps))
            hourFrames = int(timeBase * 60 * 60)
            minuteFrames = int(timeBase * 60)
            frm = int(
                (
                    (hourFrames * hours)
                    + (minuteFrames * minutes)
                    + (timeBase * seconds)
                    + frames
                )
                - (dropFrames * (totalMinutes - (totalMinutes // 10)))
            )
        else:
            self.fps = int(round(self.fps))
            frm = int((totalMinutes * 60 + seconds) * self.fps + frames)

        return frm

    def gettc(self, frames: int) -> str:
        """Convert frame count to SMPTE timecode string."""
        frames = abs(frames)

        if self.df:
            spacer = ':'
            spacer2 = ';'

            dropFrames = int(round(self.fps * 0.066666))
            framesPerHour = int(round(self.fps * 3600))
            framesPer24Hours = framesPerHour * 24
            framesPer10Minutes = int(round(self.fps * 600))
            framesPerMinute = int(round(self.fps) * 60 - dropFrames)

            frames = frames % framesPer24Hours

            d = frames // framesPer10Minutes
            m = frames % framesPer10Minutes

            if m > dropFrames:
                frames = (
                    frames
                    + (dropFrames * 9 * d)
                    + dropFrames * ((m - dropFrames) // framesPerMinute)
                )
            else:
                frames = frames + dropFrames * 9 * d

            frRound = int(round(self.fps))
            hr = int(frames // frRound // 60 // 60)
            mn = int((frames // frRound // 60) % 60)
            sc = int((frames // frRound) % 60)
            fr = int(frames % frRound)
        else:
            self.fps = int(round(self.fps))
            spacer = ':'
            spacer2 = spacer

            frHour = self.fps * 3600
            frMin = self.fps * 60

            hr = int(frames // frHour)
            mn = int((frames - hr * frHour) // frMin)
            sc = int((frames - hr * frHour - mn * frMin) // self.fps)
            fr = int(round(frames - hr * frHour - mn * frMin - sc * self.fps))

        return (
            str(hr).zfill(2)
            + spacer
            + str(mn).zfill(2)
            + spacer
            + str(sc).zfill(2)
            + spacer2
            + str(fr).zfill(2)
        )
