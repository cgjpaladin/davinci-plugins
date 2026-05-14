#!/bin/bash
# install_friend.sh — 达芬奇插件工坊 单机安装脚本
# 用法: 把 deploy.json.template 改好放在同级目录，然后运行:
#   bash install_friend.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══ 裁缝老师的达芬奇插件工坊 — 安装向导 ═══"
echo ""

# 1. 读取配置
CFG="$SCRIPT_DIR/deploy.json.template"
if [ ! -f "$CFG" ]; then
    CFG="$SCRIPT_DIR/deploy.json"
fi
if [ ! -f "$CFG" ]; then
    echo "❌ 找不到 deploy.json.template 或 deploy.json"
    echo "   请先把 tools/deploy.json.template 改好放在同目录"
    exit 1
fi

echo "📋 配置来源: $CFG"

# 读取 SMB 路径
SMB_ROOT=$(python3 -c "import json; print(json.load(open('$CFG'))['smb_root'])" 2>/dev/null)
if [ -z "$SMB_ROOT" ]; then
    echo "❌ deploy.json 中 smb_root 为空"
    exit 1
fi
echo "📁 SMB 根目录: $SMB_ROOT"

# 2. 检查 SMB 是否挂载
if [ ! -d "$SMB_ROOT" ]; then
    echo "⚠️  SMB 未挂载: $SMB_ROOT"
    echo "   请先挂载共享盘再运行"
    echo "   (Finder → 前往 → 连接服务器 → smb://服务器地址/共享名)"
    exit 1
fi

# 3. 部署 deploy.json 到 ~/达芬奇插件工坊/
LOCAL_CFG_DIR="$HOME/达芬奇插件工坊"
mkdir -p "$LOCAL_CFG_DIR"
cp "$CFG" "$LOCAL_CFG_DIR/deploy.json"
echo "✅ deploy.json → $LOCAL_CFG_DIR/deploy.json"

# 4. 检查达芬奇
DAVINCI_EDIT="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
DAVINCI_PLUGIN_DIR="$DAVINCI_EDIT/达芬奇插件工坊"
if [ ! -d "$DAVINCI_EDIT" ]; then
    echo "❌ 达芬奇未安装或未启动过"
    echo "   请先启动一次 DaVinci Resolve"
    exit 1
fi
mkdir -p "$DAVINCI_PLUGIN_DIR"

# 5. 部署 launcher
PRODUCTS=("AI去字幕:stable_ui.py" "交付自检工具:ui.py")
for entry in "${PRODUCTS[@]}"; do
    PROD="${entry%%:*}"
    SMB_PROD="$SMB_ROOT/$PROD"
    SMB_SHARED="$SMB_ROOT/shared"

    if [ ! -d "$SMB_PROD" ]; then
        echo "⚠️  产品目录不存在: $SMB_PROD，跳过 $PROD"
        continue
    fi

    # 检查 launcher.py
    LAUNCHER_SRC="$SMB_PROD/launcher.py"
    if [ ! -f "$LAUNCHER_SRC" ]; then
        echo "⚠️  launcher.py 不存在: $LAUNCHER_SRC，跳过 $PROD"
        continue
    fi

    # 读版本号
    VER=$(python3 -c "import sys; sys.path.insert(0,'$SMB_PROD'); sys.path.insert(0,'$SMB_SHARED'); from config import version_string; print(version_string())" 2>/dev/null || echo "")
    if [ -n "$VER" ]; then
        LAUNCHER_DST="$DAVINCI_PLUGIN_DIR/${PROD}_v${VER}.py"
    else
        LAUNCHER_DST="$DAVINCI_PLUGIN_DIR/${PROD}.py"
    fi

    # 清理旧版本
    for old in "$DAVINCI_PLUGIN_DIR/${PROD}"*.py; do
        [ "$old" = "$LAUNCHER_DST" ] && continue
        [ -f "$old" ] && rm "$old" && echo "  🗑 清理旧 launcher: $(basename "$old")"
    done

    cp "$LAUNCHER_SRC" "$LAUNCHER_DST"
    echo "✅ $PROD → $(basename "$LAUNCHER_DST")"

    # dry-run 自检
    echo -n "   自检... "
    /usr/bin/python3 "$LAUNCHER_DST" --dry-run 2>/dev/null && echo "✅" || echo "⚠️  自检失败（可能 Python 版本问题）"
done

# 6. 检查 Python
echo ""
echo "── Python 环境 ──"
if /usr/bin/python3 --version 2>/dev/null; then
    echo "✅ 系统 Python 可用"
elif /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 --version 2>/dev/null; then
    echo "✅ Python 3.13 可用"
else
    echo "⚠️  未检测到 Python"
    echo "   请从 https://www.python.org/downloads/ 下载安装 Python 3.12+"
fi

echo ""
echo "════════════════════"
echo "✅ 安装完成！"
echo ""
echo "📋 后续步骤:"
echo "   1. 在 $SMB_ROOT/ 下创建 .env 文件，填入 API Key"
echo "      (鬼手剪辑、无痕AI、DeepSeek、千问 等)"
echo "   2. 重启 DaVinci Resolve"
echo "   3. 达芬奇菜单 → 工作区 → 脚本 → 达芬奇插件工坊 → 选择插件"
echo ""
