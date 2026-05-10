#!/bin/bash
# sync.sh — AI去字幕 同步到 SMB（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="AI去字幕"
source "$SCRIPT_DIR/../tools/publish.sh"
publish_sync
