#!/bin/bash
# channel.sh — 切换开发/生产环境
# 用法: ./channel.sh dev        → 开发模式（本地机器）
#       ./channel.sh prod       → 生产模式（全公司 SMB）
#       ./channel.sh            → 查看当前状态
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG="$SCRIPT_DIR/config.py"

case "${1:-}" in
    dev)
        EXPECTED="dev"
        MSG="✅ 开发环境 — 本地机器不受推送影响"
        ;;
    prod|"")
        EXPECTED=""
        MSG="✅ 生产环境 — 可以推送全公司"
        ;;
    *)
        echo "用法: ./channel.sh [dev|prod]"
        exit 1
        ;;
esac

# 写入
sed -i '' 's/^__channel__ = ".*"/__channel__ = "'"${EXPECTED}"'"/' "$CFG"

# 校验：读回确认写入生效
ACTUAL=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); from config import __channel__; print(__channel__)" 2>/dev/null)
if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "❌ channel 切换失败！期望='$EXPECTED' 实际='$ACTUAL'"
    exit 1
fi

echo "$MSG"
python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); from config import version_string; print(f'  版本: {version_string()}')"
