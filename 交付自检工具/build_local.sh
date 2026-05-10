#!/bin/bash
# build_local.sh — 交付自检工具 本地验证（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
LAUNCHER_PREFIX="交付自检"
VERIFY_MODE=full

# 自动 commit
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
HASH=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "none")
git -C "$ROOT" add -A
git -C "$ROOT" commit -m "build_local: 交付自检工具 (from $HASH)" 2>/dev/null && echo "📦 auto-commit" || true

source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
