#!/bin/bash
# deploy.sh — AI 去水印插件 一键部署（Mac）
# 用法: ./deploy.sh
# 依赖: Python 3 (macOS 自带)

RESOLVE_SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SMB_PLUGIN="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"

echo "=========================================="
echo "  AI 去水印插件 — 部署工具"
echo "=========================================="

# 检查 SMB 挂载
if [ ! -d "$SMB_PLUGIN" ]; then
    echo "❌ SMB 未挂载或插件目录不存在:"
    echo "   $SMB_PLUGIN"
    echo ""
    echo "   请先挂载 SMB: smb://192.168.1.154/MYJC"
    exit 1
fi

# 创建 Scripts 目录（如果不存在）
mkdir -p "$RESOLVE_SCRIPTS"

# 部署启动器
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/AI去字幕.py" "$RESOLVE_SCRIPTS/AI去字幕.py"
rm -f "$RESOLVE_SCRIPTS/remove_watermark.py" "$RESOLVE_SCRIPTS/AI去水印.py"

if [ $? -eq 0 ]; then
    echo "✅ 部署成功"
    echo ""
    echo "   入口: 达芬奇 → Workspace → Scripts → AI去字幕"
    echo "   代码: $SMB_PLUGIN/（总监更新后全员自动同步）"
    echo ""
    echo "   macOS 自带 Python，无需额外安装。"
else
    echo "❌ 部署失败"
    exit 1
fi
