#!/bin/bash
clear

INSTALL_DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具"
FUSION_SCRIPTS="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/交付自检工具"

# ── 1. 检查解压完整性 ──
if [ ! -d "$SOURCE" ]; then
    osascript -e 'display dialog "找不到安装文件。\n\n请先将 zip 解压到文件夹，再双击「安装.command」。\n不要在压缩包里直接打开。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi

# ── 2. 找 Python ──
PYTHON=""
for p in /usr/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
    if [ -x "$p" ]; then PYTHON="$p"; break; fi
done
if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "需要先安装 Python 3\n\n下载地址: https://www.python.org/downloads/\n选择 macOS 版本，一路点继续即可。\n安装完成后再次双击「安装.command」。" buttons {"好的"} default button 1 with icon note'
    open "https://www.python.org/downloads/"
    exit 0
fi

cat <<BANNER
╔══════════════════════════════╗
║  交付自检工具 个人版安装      ║
╚══════════════════════════════╝

✅ Python: $($PYTHON --version 2>&1)
BANNER

# ── 3. 已安装？三选一 ──
if [ -d "$INSTALL_DIR" ]; then
    RESPONSE=$(osascript -e 'button returned of (display dialog "已安装过。\n\n请选择：" buttons {"更新 Key", "覆盖安装", "取消"} default button "覆盖安装" with icon caution)' 2>/dev/null || echo "取消")
    case "$RESPONSE" in
        "更新 Key")
            API_KEY=$(osascript -e 'text returned of (display dialog "输入 DeepSeek API Key（留空不修改）\n\n获取地址: platform.deepseek.com → API Keys" default answer "" buttons {"取消", "保存"} default button "保存" with icon note)' 2>/dev/null)
            if [ -n "$API_KEY" ]; then
                ESCAPED_KEY=$(echo "$API_KEY" | sed "s/'/'\"'\"'/g")
                osascript -e "do shell script \"sed -i '' 's|DEEPSEEK_KEY=.*|DEEPSEEK_KEY=$ESCAPED_KEY|' '$INSTALL_DIR/.env'\" with administrator privileges" 2>/dev/null && \
                    osascript -e 'display dialog "API Key 已更新！" buttons {"好的"} default button 1 with icon note' || \
                    osascript -e 'display dialog "更新失败。\n请检查管理员密码是否正确。" buttons {"好的"} default button 1 with icon stop'
            fi
            exit 0
            ;;
        "取消")
            exit 0
            ;;
    esac
fi

# ── 4. 输入 API Key ──
API_KEY=$(osascript -e 'text returned of (display dialog "请输入 DeepSeek API Key（没有可留空，以后补）\n\n获取地址: platform.deepseek.com → API Keys" default answer "" buttons {"跳过", "保存"} default button "保存" with icon note)' 2>/dev/null || echo "")

# ── 5. 中转 → /tmp（root 无法读用户目录）──
rm -rf /tmp/_deli_src 2>/dev/null
if ! cp -r "$SOURCE" /tmp/_deli_src 2>/dev/null; then
    osascript -e 'display dialog "准备安装失败。\n请检查磁盘空间或关闭其他程序后重试。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi

echo "→ 安装到 $INSTALL_DIR"

# ── 6. 管理员安装 ──
ESCAPED_KEY=$(echo "$API_KEY" | sed "s/'/'\"'\"'/g")
if osascript <<EOF 2>/tmp/_deli_install.log
do shell script "
    mkdir -p '$FUSION_SCRIPTS' &&
    if [ -f '$INSTALL_DIR/.env' ]; then cp '$INSTALL_DIR/.env' /tmp/_deli_env_bak; fi &&
    rm -rf '$INSTALL_DIR' && cp -r /tmp/_deli_src '$INSTALL_DIR' &&
    cp '$INSTALL_DIR/shell_personal.py' '$FUSION_SCRIPTS/交付自检工具.py' && chmod 755 '$FUSION_SCRIPTS/交付自检工具.py' &&
    if [ -f /tmp/_deli_env_bak ]; then
        cp /tmp/_deli_env_bak '$INSTALL_DIR/.env' && rm -f /tmp/_deli_env_bak
    else
        cp '$INSTALL_DIR/.env.example' '$INSTALL_DIR/.env'
    fi &&
    if [ -n '$ESCAPED_KEY' ]; then
        sed -i '' 's|DEEPSEEK_KEY=.*|DEEPSEEK_KEY=$ESCAPED_KEY|' '$INSTALL_DIR/.env'
    fi &&
    rm -rf /tmp/_deli_src
" with administrator privileges
EOF
then
    :
else
    rm -rf /tmp/_deli_src 2>/dev/null
    osascript -e 'display dialog "安装失败。\n详情: $(tail -3 /tmp/_deli_install.log 2>/dev/null)" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi

# ── 7. 验证 ──
if [ -f "$FUSION_SCRIPTS/交付自检工具.py" ] && [ -f "$INSTALL_DIR/ui.py" ]; then
    osascript -e 'display dialog "✅ 安装完成！\n\n使用方法：\n  打开达芬奇 → Workspace → Scripts → 交付自检工具" buttons {"好的"} default button "好的" with icon note'
else
    rm -rf /tmp/_deli_src 2>/dev/null
    osascript -e 'display dialog "验证失败。\n安装似乎未完成，请检查磁盘权限后重试。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi
