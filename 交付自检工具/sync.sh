#!/bin/bash
# sync.sh — 将本产品文件同步到 SMB
# 用法: ./sync.sh
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具"

if [ ! -d "$SMB" ]; then
    mkdir -p "$SMB"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 同步本产品文件
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(find . -maxdepth 1 \( -name '*.py' -o -name 'sync.sh' \) | sed 's|^\./||' | sort)

echo "同步到 SMB..."
for f in "${FILES[@]}"; do
    src="$PWD/$f"
    dst="$SMB/$f"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
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
