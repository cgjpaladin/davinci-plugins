#!/bin/bash
# sync.sh — 将本地改动同步到 SMB（开发用，不是部署用）
# 用法: ./sync.sh
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具"

if [ ! -d "$SMB" ]; then
    echo "❌ SMB 未挂载: $SMB"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 备份现有 SMB 文件 ──
BAK_DIR="$SMB/.bak_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BAK_DIR"
echo "备份 SMB → $BAK_DIR"

# ── 同步本产品文件 ──
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(find . -maxdepth 1 \( -name '*.py' -o -name 'sync.sh' \) | sed 's|^\./||' | sort)

echo "同步到 SMB..."
for f in "${FILES[@]}"; do
    src="$PWD/$f"
    dst="$SMB/$f"
    if [ -f "$src" ]; then
        # 备份旧文件
        if [ -f "$dst" ]; then
            cp "$dst" "$BAK_DIR/$f" 2>/dev/null || true
        fi
        # 原子写入：先写临时文件再 rename
        cp "$src" "$dst.tmp" && mv "$dst.tmp" "$dst"
    fi
done

# ── 同步 dicts/ 词典 ──
DICTS_DIR="$SCRIPT_DIR/dicts"
if [ -d "$DICTS_DIR" ]; then
    SMB_DICTS="$SMB/dicts"
    mkdir -p "$SMB_DICTS"
    echo "同步 dicts/..."
    rsync -a "$DICTS_DIR/" "$SMB_DICTS/" 2>/dev/null
    echo "  ✅ dicts/ 同步完成"
fi

# 创建日志目录
mkdir -p "$SMB/logs"

# ── 语法检查 ──
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
