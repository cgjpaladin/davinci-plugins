#!/bin/bash
# check_logs.sh — 查一台机器所有 AI去字幕 日志，全源无过滤
# 用法: bash tools/check_logs.sh <hostname> [today]
#       bash tools/check_logs.sh <hostname> today  # 只看今天
HOST=$1
MODE=${2:-all}
if [ -z "$HOST" ]; then echo "用法: check_logs.sh <hostname> [today]"; exit 1; fi

TODAY=$(date +%Y-%m-%d)

ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "bash -s" << 'HEREDOC' 2>/dev/null
TODAY=$1; MODE=$2
echo "🔍 $HOSTNAME | $TODAY"

# ═══ 1. 插件 UI 日志 ═══ (最重要——所有错误都在这里)
echo ''
echo '═══ 1/4 插件日志 ═══'
LOG_DIR="$HOME/.workbuddy/logs/AI去字幕"
for f in $(find "$LOG_DIR" -name "*.log" -type f -newer "$LOG_DIR/.." 2>/dev/null | sort -r | head -3; ls -t "$LOG_DIR"/*.log 2>/dev/null | head -3); do
    [ ! -f "$f" ] && continue
    count=$(grep -c "2026-" "$f" 2>/dev/null || echo 0)
    errors=$(grep -ci "Error\|error\|fail\|Fail\|❌" "$f" 2>/dev/null || echo 0)
    echo "  📄 $(basename $f) | $(stat -f%z "$f" 2>/dev/null)字节 | $count行 | ${errors}条错误"
    grep -n "❌\|Error\|error\|FAIL\|SSL\|Traceback" "$f" 2>/dev/null | tail -30
    echo ''
done

# ═══ 2. 达芬奇系统日志 ═══
echo '═══ 2/4 达芬奇系统日志 ═══'
DRD="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs"
if [ -f "$DRD/ResolveDebug.txt" ]; then
    count=$(grep -c "Traceback\|Error" "$DRD/ResolveDebug.txt" 2>/dev/null || echo 0)
    echo "  📄 ResolveDebug.txt | $(stat -f%z "$DRD/ResolveDebug.txt" 2>/dev/null)字节 | ${count}条错误"
    grep "Traceback\|Error" "$DRD/ResolveDebug.txt" 2>/dev/null | tail -10
fi
echo ''

# ═══ 3. Python 进程状态 ═══
echo '═══ 3/4 运行中的插件进程 ═══'
ps aux 2>/dev/null | grep -i "stable_ui\|launcher.py" | grep -v grep | head -5
echo ''

# ═══ 4. 崩溃报告 ═══
echo '═══ 4/4 Python 崩溃报告 ═══'
find "$HOME/Library/Logs/DiagnosticReports" -name "python*" -newer /tmp 2>/dev/null | head -3 | while read f; do
    echo "  📄 $(basename $f) | $(stat -f%z "$f" 2>/dev/null)字节"
done
find "/Library/Logs/DiagnosticReports" -name "python*" -newer /tmp 2>/dev/null | head -3 | while read f; do
    echo "  📄 $(basename $f) | $(stat -f%z "$f" 2>/dev/null)字节"
done
echo '✅ 完毕'
HEREDOC
" "$TODAY" "$MODE"
