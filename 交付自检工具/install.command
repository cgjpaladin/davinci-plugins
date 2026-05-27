#!/bin/bash
set -e
clear

# ── 找 Python ──
PYTHON=""
for p in /usr/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
    if [ -x "$p" ]; then PYTHON="$p"; break; fi
done

if [ -z "$PYTHON" ]; then
    osascript <<EOF
display dialog "需要先安装 Python 3

请打开文件夹里的 「Python安装包.pkg」，一路点「继续」即可完成安装。安装完成后再次双击「安装.command」。" \
buttons {"好的"} default button 1 \
with icon note
EOF
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    open "$SCRIPT_DIR"
    exit 0
fi

cat <<EOF
╔══════════════════════════════╗
║  交付自检工具 个人版安装      ║
╚══════════════════════════════╝

✅ Python: $($PYTHON --version 2>&1)
EOF

INSTALL_DIR="$HOME/Documents/交付自检工具"
FUSION_SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "→ 安装到 $INSTALL_DIR"
rm -rf "$INSTALL_DIR" 2>/dev/null
cp -r "$SCRIPT_DIR/交付自检工具" "$INSTALL_DIR"
echo "  ✅ 文件安装完成"

mkdir -p "$FUSION_SCRIPTS"
cp "$INSTALL_DIR/shell_personal.py" "$FUSION_SCRIPTS/交付自检工具.py"
echo "  ✅ 达芬奇菜单注册完成"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" 2>/dev/null || true
fi

# ── 输入 API Key ──
API_KEY=$(osascript -e 'text returned of (display dialog "请输入 DeepSeek API Key（没有可留空，以后补）\n\n获取地址: platform.deepseek.com → API Keys" default answer "" buttons {"跳过", "保存"} default button "保存" with icon note)' 2>/dev/null)
if [ -n "$API_KEY" ]; then
    sed -i '' "s/DEEPSEEK_KEY=.*/DEEPSEEK_KEY=$API_KEY/" "$INSTALL_DIR/.env"
    echo "  ✅ API Key 已保存"
fi

osascript -e 'display dialog "安装完成！\n\n1. 重启达芬奇\n2. 菜单 Workspace → Scripts → 交付自检工具" buttons {"好的"} default button 1 with icon note'

open "$INSTALL_DIR"
