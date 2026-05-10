#!/bin/bash
# logs.sh — 一键查看某产品所有日志
# 用法: bash tools/logs.sh [产品名] [--tail N]
#       bash tools/logs.sh --list          # 列出所有有日志的产品

set -euo pipefail
LOG_ROOT="$HOME/.workbuddy/logs"
SMB_LOG="/Volumes/MYJC/06_Software/达芬奇脚本/日志"

TAIL="${2:-20}"
PRODUCT="${1:-}"

if [ "$PRODUCT" = "--list" ]; then
    echo "=== 有日志的产品 ==="
    ls "$LOG_ROOT" 2>/dev/null || echo "(无本地日志)"
    ls "$SMB_LOG" 2>/dev/null || echo "(无 SMB 日志)"
    exit 0
fi

if [ -z "$PRODUCT" ]; then
    echo "用法: bash tools/logs.sh <产品名> [--tail N]"
    echo "      bash tools/logs.sh --list"
    exit 1
fi

# 处理 --tail 参数
if [[ "${2:-}" =~ ^--tail$ ]] && [ -n "${3:-}" ]; then
    TAIL="$3"
fi

echo "═══ $PRODUCT 日志 ═══"
echo ""
echo "--- 本地 (~/.workbuddy/logs/) ---"
LOCAL_DIR="$LOG_ROOT/$PRODUCT"
if [ -d "$LOCAL_DIR" ]; then
    for f in "$LOCAL_DIR"/*; do
        if [ -f "$f" ]; then
            SIZE=$(du -h "$f" | cut -f1)
            MTIME=$(stat -f "%Sm" -t "%m-%d %H:%M" "$f" 2>/dev/null || echo "?")
            echo "  $(basename "$f")  ($SIZE, $MTIME)"
        fi
    done
else
    echo "  (无本地日志)"
fi

echo ""
echo "--- SMB (/Volumes/MYJC/.../日志/) ---"
SMB_DIR="$SMB_LOG/$PRODUCT"
if [ -d "$SMB_DIR" ]; then
    for f in "$SMB_DIR"/*; do
        if [ -f "$f" ]; then
            SIZE=$(du -h "$f" | cut -f1)
            MTIME=$(stat -f "%Sm" -t "%m-%d %H:%M" "$f" 2>/dev/null || echo "?")
            echo "  $(basename "$f")  ($SIZE, $MTIME)"
        fi
    done
else
    echo "  (无 SMB 日志)"
fi

# 如果有 --tail 参数，显示最新日志文件尾部
if [ -n "${3:-}" ] && [ "$2" = "--tail" ]; then
    LATEST=$(ls -t "$LOCAL_DIR"/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        echo ""
        echo "--- 最新本地日志 ($(basename "$LATEST")) 最近 $TAIL 行 ---"
        tail -"$TAIL" "$LATEST"
    fi
fi
