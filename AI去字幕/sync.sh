#!/bin/bash
# sync.sh — 将本地改动同步到 SMB（开发用，不是部署用）
# 用法: ./sync.sh
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"

if [ ! -d "$SMB" ]; then
    echo "❌ SMB 未挂载: $SMB"
    exit 1
fi

FILES=(
    "ui_external.py"
    "core.py"
    "remove_watermark.py"
    "config.py"
    "pricing.py"
    "logger.py"
    "ops_logger.py"
    "watermark_state.py"
    "launcher.py"
    "launcher_ui.py"
    "adapters/__init__.py"
    "adapters/wuhenai_v2.py"
    "adapters/ghostcut.py"
)

echo "同步到 SMB..."
for f in "${FILES[@]}"; do
    src="$PWD/$f"
    dst="$SMB/$f"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
    else
        echo "  ⚠ 跳过（不存在）: $f"
    fi
done

# 创建日志目录
mkdir -p "$SMB/logs"

# 语法检查
echo "语法检查..."
FAIL=0
for f in "${FILES[@]}"; do
    if [ -f "$SMB/$f" ] && [[ "$f" == *.py ]]; then
        python3 -m py_compile "$SMB/$f" || FAIL=1
    fi
done

if [ $FAIL -eq 0 ]; then
    echo "✅ 同步完成"
else
    echo "❌ 有语法错误"
    exit 1
fi
