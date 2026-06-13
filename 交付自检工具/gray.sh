#!/bin/bash
# gray.sh — 交付自检工具 灰度管理（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="交付自检工具"
SMB_DIR="/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具"
GRAY_CFG="$SMB_DIR/gray.json"

source "$SCRIPT_DIR/../tools/publish.sh"

# ═══ 硬拦截：dev 环境禁止灰度操作 ═══
_dev_chk=$(cd "$PRODUCT_DIR" && python3 -c "import sys; sys.path.insert(0,'.'); from config import __channel__; print(__channel__)" 2>/dev/null || echo "")
if [ -n "$_dev_chk" ] && [ "${1:-}" != "status" ]; then
    echo "⛔ 当前处于开发环境（__channel__='$_dev_chk'），禁止灰度操作！"
    echo "   请先运行 ./channel.sh prod 切换到生产环境。"
    exit 1
fi

_usage() {
    echo "灰度发布 — 交付自检工具"
    echo "  gray.sh add <id> [...]   加入灰度"
    echo "  gray.sh remove <id> [...] 移出灰度"
    echo "  gray.sh status            查看状态"
    echo "  gray.sh promote           全量发布"
    exit 1
}

case "${1:-}" in
    add)    shift; publish_gray_add "$@" ;;
    remove) shift; publish_gray_remove "$@" ;;
    status) publish_gray_status ;;
    promote) publish_gray_promote ;;
    *) _usage ;;
esac
