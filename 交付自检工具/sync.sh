#!/bin/bash
# sync.sh — 交付自检 同步到 SMB（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
SYNC_EXTRA_DIRS="dicts"  # 交付自检特有：违禁词典
source "$SCRIPT_DIR/../tools/publish.sh"
publish_sync
