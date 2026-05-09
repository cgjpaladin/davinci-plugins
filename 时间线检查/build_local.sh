#!/bin/bash
# build_local.sh — 本地验证，不同步 SMB
# 用法: ./build_local.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══ 本地验证 — 时间线检查 ═══"
echo ""

echo "语法检查..."
FAIL=0
for f in config.py core.py check.py ui.py; do
    python3 -m py_compile "$f" && echo "  ✅ $f" || { echo "  ❌ $f"; FAIL=1; }
done
if [ $FAIL -ne 0 ]; then
    echo "❌ 语法错误"
    exit 1
fi

echo ""
echo "═══════════════════"
echo "✅ 本地验证完成（未同步 SMB）"
echo "   确认没问题后运行 ./push_all.sh 推送到全公司"
