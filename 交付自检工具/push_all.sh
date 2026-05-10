#!/bin/bash
# push_all.sh — 交付自检工具 推送到全公司（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
VERIFY_MODE=light

# 自动 commit
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
HASH=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "none")
git -C "$ROOT" add -A
git -C "$ROOT" commit -m "push_all: 交付自检工具 (from $HASH)" 2>/dev/null && echo "📦 auto-commit" || true

# ── 版本号未变警告 ──
SMB="/Volumes/MYJC/06_Software/达芬奇脚本"
if [ -d "$SMB" ] && [ "${SKIP_VERSION_WARN:-}" != "1" ]; then
    VERSION_FILE="$SMB/交付自检工具/.last_push_version"
    CURRENT_VER=$(grep '^__version__' "$SCRIPT_DIR/config.py" | grep -o '"[^"]*"' | tr -d '"')
    if [ -f "$VERSION_FILE" ]; then
        LAST_VER=$(cat "$VERSION_FILE")
        if [ "$CURRENT_VER" = "$LAST_VER" ]; then
            echo "⚠️  版本号未变 ($CURRENT_VER)，上次推送也是这个版本。"
            echo "   确定要继续推送吗？(y/N)"
            read -r CONFIRM
            if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
                echo "已取消。请先 bump 版本号: ./bump_version.sh"
                exit 1
            fi
        fi
    fi
fi

source "$SCRIPT_DIR/../tools/publish.sh"
publish_push_all

# 推送成功后记录版本号
if [ -d "$SMB" ]; then
    echo "$CURRENT_VER" > "$VERSION_FILE"
fi
