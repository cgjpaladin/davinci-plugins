#!/bin/bash
# install.command — 交付自检工具个人版 一键安装
set -e

INSTALL_DIR="$HOME/Documents/交付自检工具"
FUSION_SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"

echo "═══ 交付自检工具 个人版安装 ═══"
echo ""

# 1. 拷贝文件
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "→ 安装到 $INSTALL_DIR"
rm -rf "$INSTALL_DIR"
cp -r "$SCRIPT_DIR" "$INSTALL_DIR"
echo "  ✅ 文件拷贝完成"

# 2. 创建 Fusion Scripts 壳
mkdir -p "$FUSION_SCRIPTS"
cp "$INSTALL_DIR/shell_personal.py" "$FUSION_SCRIPTS/交付自检工具.py"
echo "  ✅ 达芬奇菜单注册完成"

# 3. 配置 .env（如不存在）
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" 2>/dev/null || true
    echo "  ⚠ 请编辑 $INSTALL_DIR/.env 填入 DeepSeek API Key"
fi

echo ""
echo "═══════════════════════════════"
echo "✅ 安装完成！"
echo ""
echo "使用方法："
echo "  1. 重启达芬奇"
echo "  2. 菜单 Workspace → Scripts → 交付自检工具"
echo ""
echo "AI 校对需要 DeepSeek Key:"
echo "  → 打开 $INSTALL_DIR/.env"
echo "  → 写入 DEEPSEEK_KEY=sk-你的密钥"
echo ""

# 打开安装目录
open "$INSTALL_DIR"
