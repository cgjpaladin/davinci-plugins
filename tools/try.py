#!/usr/bin/env python3
"""
tools/try.py — API 即时探索器
─────────────────────────────
不写脚本，一句命令试 API。

用法:
  python3 tools/try.py "timeline.GetName()"
  python3 tools/try.py "scan_io()"
  python3 tools/try.py "dir(timeline)"                    # 看对象所有方法
  python3 tools/try.py "project.GetSetting('timelineFrameRate')"
  python3 tools/try.py "len(scan_io())"                   # IO 内片段数
  python3 tools/try.py                                     # 进交互 REPL

预载对象: resolve, project, timeline, fusion, scan_io, get_io, balance, ClipInfo
"""
import sys, os

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)

from dvr import (
    resolve, project, timeline, fusion,
    scan_io, get_io, balance, ClipInfo, status, dr, prj, tl
)


def main():
    if len(sys.argv) > 1:
        expr = " ".join(sys.argv[1:])
        try:
            result = eval(expr)
            print(repr(result))
        except Exception as e:
            print(f"❌ {type(e).__name__}: {e}")
    else:
        # 交互 REPL
        import code
        banner = (
            "╔" + "═" * 50 + "╗\n"
            "║  达芬奇 API 探索器                              ║\n"
            "╠" + "═" * 50 + "╣\n"
            "║  预载: resolve, project, timeline, fusion        ║\n"
            "║         scan_io(), get_io(), balance(), status()  ║\n"
            "║         短别名: dr, prj, tl                        ║\n"
            "╚" + "═" * 50 + "╝"
        )
        ns = {
            "resolve": resolve(), "project": project(), "timeline": timeline(),
            "fusion": fusion(), "scan_io": scan_io, "get_io": get_io,
            "balance": balance, "ClipInfo": ClipInfo, "status": status,
            "dr": dr, "prj": prj, "tl": tl,
        }
        code.interact(banner=banner, local=ns)


if __name__ == "__main__":
    main()
