#!/bin/bash
# cleanup_machine_id.sh — 批量删除所有机器上的 machine_id.txt（旧路由残留）
# 用法: bash tools/cleanup_machine_id.sh [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAP="$ROOT/shared/machine_map.json"
DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

TARGET="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/machine_id.txt"

echo "═══ machine_id.txt 清理 ═══"
echo ""

TOTAL=0
DELETED=0
SKIPPED=0

for mid in $(python3 -c "
import json
m = json.load(open('$MAP'))
for k in sorted(m.keys(), key=int):
    if k != '200':  # 跳过裁缝老师本机（已手动清理）
        print(k)
"); do
    TOTAL=$((TOTAL + 1))
    IP=$(python3 -c "import json; print(json.load(open('$MAP'))['$mid']['ip'])")
    NAME=$(python3 -c "import json; print(json.load(open('$MAP'))['$mid']['name'])")

    # 检查在线
    if ! ssh -o ConnectTimeout=3 -o BatchMode=yes "mini$mid" 'echo online' &>/dev/null 2>&1; then
        echo "  mini$mid ($NAME): 不在线，跳过"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # 检查文件是否存在
    if ssh -o ConnectTimeout=3 "mini$mid" "test -f '$TARGET'" 2>/dev/null; then
        if $DRY_RUN; then
            echo "  mini$mid ($NAME): [DRY RUN] 将删除 $TARGET"
        else
            ssh -o ConnectTimeout=3 "mini$mid" "rm -f '$TARGET'" 2>/dev/null && {
                echo "  mini$mid ($NAME): ✅ 已删除"
                DELETED=$((DELETED + 1))
            } || {
                echo "  mini$mid ($NAME): ❌ 删除失败"
            }
        fi
    else
        echo "  mini$mid ($NAME): 无此文件，跳过"
        SKIPPED=$((SKIPPED + 1))
    fi
done

echo ""
echo "════════════════════"
echo "  在线: $TOTAL | 已删: $DELETED | 跳过: $SKIPPED"
if $DRY_RUN; then
    echo "  (dry-run 模式，未实际删除)"
fi
