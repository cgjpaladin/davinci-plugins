#!/bin/bash
# build_local.sh — 交付自检工具 本地验证（薄包装 → tools/publish.sh）
# 用法: ./build_local.sh [--save]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
LAUNCHER_PREFIX="交付自检"
VERIFY_MODE=full

if [ "$1" = "--save" ]; then
    HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo "none")
    git -C "$SCRIPT_DIR" add -A
    git -C "$SCRIPT_DIR" commit -m "checkpoint: 交付自检工具 (from $HASH)" 2>/dev/null && \
        echo "📦 checkpoint saved" || echo "📦 nothing to commit"
    echo ""
fi

source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
