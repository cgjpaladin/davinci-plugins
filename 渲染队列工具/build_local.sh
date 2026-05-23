#!/bin/bash
# build_local.sh — 渲染队列工具 本地构建
# 用法: bash build_local.sh [VERSION_BUMP=patch|minor|major|none]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_NAME="$(basename "$SCRIPT_DIR")"
_VERIFY_MODE="light"
VERIFY_FILES="config.py render_batch.py"
source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
