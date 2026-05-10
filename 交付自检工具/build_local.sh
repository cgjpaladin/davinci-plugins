#!/bin/bash
# build_local.sh — 交付自检工具 本地验证（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
VERIFY_MODE=light
_STAGE=build_local
source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
