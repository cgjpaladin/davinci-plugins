#!/bin/bash
# push_all.sh — 推送到全公司（SMB 同步 + 语法验证）
# 用法: ./push_all.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══ 推送到全公司 — 时间线检查 ═══"
echo ""

# 先跑本地验证
echo "第 1 步: 本地语法检查..."
FAIL=0
for f in config.py core.py check.py ui.py; do
    python3 -m py_compile "$f" && echo "  ✅ $f" || { echo "  ❌ $f"; FAIL=1; }
done
if [ $FAIL -ne 0 ]; then
    echo "❌ 语法错误, 停止推送"
    exit 1
fi
echo ""

# 同步 SMB
echo "第 2 步: 同步 shared/ 到 SMB..."
SHARED_DIR="$(cd "$SCRIPT_DIR/../shared" && pwd)"
SMB_SHARED="/Volumes/MYJC/06_Software/达芬奇脚本/shared"
if [ -d "$SMB_SHARED" ]; then
    rsync -av --delete "$SHARED_DIR/" "$SMB_SHARED/" 2>/dev/null
    echo "  ✅ shared/ 同步完成"
else
    echo "  ⚠ SMB 未挂载, shared/ 跳过"
fi
echo ""

echo "第 3 步: 同步本产品文件到 SMB..."
bash "$SCRIPT_DIR/sync.sh"
echo ""

echo "═══════════════════"
echo "✅ 全量推送完成"
