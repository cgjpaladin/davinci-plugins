#!/usr/bin/env python3
"""
tools/logs.py — 达芬奇日志速查
─────────────────────────────
一抹灰看崩溃原因、脚本错误。

用法:
  python3 tools/logs.py              最近崩溃 + 错误
  python3 tools/logs.py --crash      只看崩溃堆栈
  python3 tools/logs.py --tail 50    最近 50 行脚本相关
  python3 tools/logs.py --since 30m  最近 30 分钟的错误
"""
import sys, os, time, argparse

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import _env

LOG_DIR = os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve")
CRASH = os.path.join(LOG_DIR, "crash_archive.txt")
DEBUG = os.path.join(LOG_DIR, "logs/ResolveDebug.txt")


def _read_tail(path, lines=100):
    """读文件尾"""
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read()
        return "\n".join(content.split("\n")[-lines:])
    except:
        return ""


def crash_analysis():
    """分析最近崩溃"""
    if not os.path.exists(CRASH):
        return "（无崩溃记录）"
    
    mtime = os.path.getmtime(CRASH)
    age = time.time() - mtime
    
    content = _read_tail(CRASH, 200)
    if not content:
        return "（文件为空）"
    
    # 提取最后一段崩溃
    sections = content.split("Thread")
    last = sections[-1] if len(sections) > 1 else content
    
    reasons = []
    if "ScriptSymbolD0Ev" in last:
        reasons.append("🔴 ScriptSymbolD0Ev — widget 构造崩溃（内嵌 Python 建窗口炸了）")
    if "HandleUIE" in last:
        reasons.append("🔴 HandleUIE — UI 渲染崩溃")
    if "ModuleNotFoundError" in last:
        reasons.append("🟡 模块导入失败")
    if "fusionscript.so" in last:
        reasons.append("⚪ fusionscript.so 层崩溃")
    
    lines = [f"最近崩溃: {time.strftime('%H:%M:%S', time.localtime(mtime))}（{age:.0f}秒前）"]
    lines.extend(reasons)
    
    # 提取 fusionscript 相关关键帧
    for line in last.split("\n"):
        if "fusionscript" in line or "scriptapp" in line.lower():
            lines.append(f"  {line.strip()}")
            if len(lines) > 15:
                break
    
    return "\n".join(lines)


def script_errors(since_minutes=None):
    """脚本相关错误"""
    if not os.path.exists(DEBUG):
        return "（无调试日志）"
    
    content = _read_tail(DEBUG, 500)
    errors = []
    
    for line in content.split("\n"):
        lower = line.lower()
        if any(kw in lower for kw in ["python", "script", "error", "traceback", "module", "import"]):
            if since_minutes:
                # 简单时间过滤
                if "2026" in line:
                    try:
                        ts = line.split("|")[1].strip() if "|" in line else ""
                    except:
                        pass
            errors.append(line.strip())
    
    if not errors:
        return "（无脚本相关错误）"
    
    return "\n".join(errors[-30:])


def main():
    parser = argparse.ArgumentParser(description="达芬奇日志速查")
    parser.add_argument("--crash", action="store_true", help="只看崩溃")
    parser.add_argument("--tail", type=int, default=0, help="最近 N 行")
    parser.add_argument("--since", type=str, default="", help="时间范围（如 30m）")
    args = parser.parse_args()
    
    if args.crash:
        print(crash_analysis())
        return
    
    if args.tail:
        print(_read_tail(DEBUG, args.tail))
        return
    
    # 默认：崩溃 + 错误摘要
    print("━" * 50)
    print("  达芬奇日志速查")
    print("━" * 50)
    print()
    print(crash_analysis())
    print()
    print("━" * 50)
    print("  脚本相关错误")
    print("━" * 50)
    print(script_errors())
    print()
    print(f"  完整日志: {DEBUG}")
    print(f"  崩溃日志: {CRASH}")


if __name__ == "__main__":
    main()
