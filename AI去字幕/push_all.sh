#!/bin/bash
# push_all.sh — AI去字幕 推送到全公司（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="AI去字幕"
VERIFY_MODE=full
_STAGE=push_all
source "$SCRIPT_DIR/../tools/publish.sh"
publish_push_all
