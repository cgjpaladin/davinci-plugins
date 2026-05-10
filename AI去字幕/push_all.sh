#!/bin/bash
# push_all.sh — AI去字幕 推送到全公司（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="AI去字幕"
LAUNCHER_PREFIX="AI去字幕"
VERIFY_MODE=full

# 自动 commit
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
HASH=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "none")
git -C "$ROOT" add -A
git -C "$ROOT" commit -m "push_all: AI去字幕 (from $HASH)" 2>/dev/null && echo "📦 auto-commit" || true

source "$SCRIPT_DIR/../tools/publish.sh"
publish_push_all
