#!/bin/bash
# logs.sh — 一键查看某产品所有日志（文件名含日期+主机名，按行含时间戳）
# 用法: bash tools/logs.sh [产品名] [--tail N]
#       bash tools/logs.sh --list          # 列出所有有日志的产品

set -euo pipefail
LOG_ROOT="$HOME/.workbuddy/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAP="$ROOT/shared/machine_map.json"

TAIL="${2:-20}"
PRODUCT="${1:-}"

# ── 辅助: hostname → 人名 ──
_host_to_name() {
    local h="$1"
    if [ -f "$MAP" ]; then
        python3 -c "
import json, sys
m = json.load(open('$MAP'))
# hostname 里提取标识: Mac-mini-104.local → 104
h = '$h'.replace('.local','').replace('Mac-mini-','')
# 特例: BryandeMac-mini → bryan
if h.lower().startswith('bryan'):
    h = 'bryan'
# 找 short 匹配或 id 匹配
for k,v in m.items():
    if v.get('short','') == h or k == h:
        print(f\"{v['name']}(mini{k})\")
        sys.exit(0)
# 没匹配到也显示 hostname
print('$h'.split('.')[0])
" 2>/dev/null || echo "$h"
    else
        echo "$h"
    fi
}

# ── 辅助: 文件大小和时间 ──
_file_info() {
    local f="$1"
    if [ -f "$f" ]; then
        SIZE=$(du -h "$f" | cut -f1)
        MTIME=$(stat -f "%Sm" -t "%m-%d %H:%M" "$f" 2>/dev/null || echo "?")
        echo "$SIZE | $MTIME"
    fi
}

# ── 从文件名提取 hostname ──
_extract_host() {
    # 文件名格式: ui_BryandeMac-mini.local_2026-05-11.log → BryandeMac-mini.local
    # 旧格式: launcher_2026-05-11.log → 本地
    local fn="$1"
    # 去掉前缀 (ui_/launcher_/ops_)
    local rest="${fn#*_}"
    # 如果剩下是 4 位数字开头(日期)，说明无 hostname
    if [[ "$rest" =~ ^[0-9]{4}- ]]; then
        echo "local"
        return
    fi
    # 去掉日期后缀 _YYYY-MM-DD.ext
    echo "$rest" | sed -E 's/_[0-9]{4}-[0-9]{2}-[0-9]{2}\.(log|jsonl)$//'
}

if [ "$PRODUCT" = "--list" ]; then
    echo "=== 有日志的产品 ==="
    ls "$LOG_ROOT" 2>/dev/null || echo "(无本地日志)"
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
    # 按文件分组显示（同一天不同类型）
    for f in "$LOCAL_DIR"/*; do
        if [ -f "$f" ]; then
            FN=$(basename "$f")
            HOST=$(_extract_host "$FN")
            PERSON=$(_host_to_name "$HOST")
            INFO=$(_file_info "$f")
            printf "  %-50s %-20s %s\n" "$FN" "$PERSON" "$INFO"
        fi
    done
else
    echo "  (无本地日志)"
fi

echo ""
echo "--- 远程查看说明 ---"
echo "  SMB 日志已废弃（达芬奇 subprocess 隔离，不可写入）"
echo "  查看其他机器日志: ssh miniXXX tail ~/.workbuddy/logs/$PRODUCT/ui_*.log"
echo "  查看 ops 日志:     ssh miniXXX tail ~/.workbuddy/logs/ops/*.log"

# 如果有 --tail 参数，显示最新日志文件尾部
if [ -n "${3:-}" ] && [ "$2" = "--tail" ]; then
    LATEST=$(ls -t "$LOCAL_DIR"/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        echo ""
        echo "--- 最新本地日志 ($(basename "$LATEST")) 最近 $TAIL 行 ---"
        tail -"$TAIL" "$LATEST"
    fi
fi
