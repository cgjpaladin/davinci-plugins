#!/bin/bash
# deploy.sh — AI 去字幕插件 一键部署（Mac）
# 用法: ./deploy.sh
# 功能: 将启动器复制到达芬奇 Scripts 目录，主体代码通过 SMB 共享
# 灰度发布: hostname 自动识别（Mac-mini-{IP末段}），无需额外配置

RESOLVE_SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SMB_PLUGIN="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"

echo "=========================================="
echo "  AI 去字幕插件 — 部署工具"
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

# 清理旧版本（所有历史入口）
rm -f "$RESOLVE_SCRIPTS/AI去字幕.py" "$RESOLVE_SCRIPTS/AI去字幕_UI.py" "$RESOLVE_SCRIPTS/remove_watermark.py" "$RESOLVE_SCRIPTS/AI去水印.py" "$RESOLVE_SCRIPTS/machine_id.txt"

# 部署启动器 → 达芬奇菜单唯一入口: AI去字幕
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/launcher_ui.py" "$RESOLVE_SCRIPTS/AI去字幕.py"

if [ $? -eq 0 ]; then
    echo "✅ 部署成功"
    echo ""
    echo "   入口: 达芬奇 → Workspace → Scripts → AI去字幕"
    echo "   主体代码: $SMB_PLUGIN/（总监更新后全员自动同步）"
    echo ""
    echo "   依赖: macOS 自带 Python 3 + 系统 Python 3.13"
else
    echo "❌ 部署失败"
    exit 1
fi
