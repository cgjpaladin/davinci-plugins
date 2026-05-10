#!/bin/bash
# push_all.sh — 交付自检工具 推送到全公司（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
VERIFY_MODE=light
_STAGE=push_all
source "$SCRIPT_DIR/../tools/publish.sh"
publish_push_all
