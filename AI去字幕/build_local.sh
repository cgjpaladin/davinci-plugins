#!/bin/bash
# build_local.sh — AI去字幕 本地验证（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="AI去字幕"
VERIFY_MODE=full
_STAGE=build_local
source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
