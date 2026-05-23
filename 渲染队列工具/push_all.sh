#!/bin/bash
# push_all.sh — 渲染队列工具 推全公司
# 用法: bash push_all.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_NAME="$(basename "$SCRIPT_DIR")"
_VERIFY_MODE="light"
source "$SCRIPT_DIR/../tools/publish.sh"
publish_push_all
