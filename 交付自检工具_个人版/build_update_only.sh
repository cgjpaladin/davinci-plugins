#!/bin/bash
# build_personal.sh — 构建交付自检工具个人版安装包
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG="$SCRIPT_DIR/_build/交付自检工具_个人版"
ZIP="$HOME/Desktop/交付自检工具_个人版.zip"
PY_PKG="$HOME/Desktop/交付自检工具_个人版/Python安装包.pkg"

echo "═══ 构建个人版安装包 ═══"

# 1. 清理
rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG/交付自检工具/shared/dftt_timecode/core" "$PKG/交付自检工具/dicts" "$PKG/交付自检工具/shared/ui"

# 2. 核心文件（从原版同步最新）
cp "$WS/交付自检工具"/ui.py "$WS/交付自检工具"/check_core.py "$WS/交付自检工具"/config.py "$PKG/交付自检工具/"
cp "$WS/交付自检工具"/launcher_personal.py "$WS/交付自检工具"/shell_personal.py "$WS/交付自检工具"/install.command "$WS/交付自检工具"/.env.example "$PKG/交付自检工具/"

# 3. shared 模块（全套）
cp "$WS/shared"/{deploy_config,fusionscript_loader,log_writer,camera_detect,script_parser,llm_typo_check,llm_providers,timecode,mappings,launcher_router,subtitle_state,macos_utils,updater,update_config,license,_write_env}.py "$PKG/交付自检工具/shared/"
cp "$WS/shared/ui/theme.py" "$PKG/交付自检工具/shared/ui/"

# 4. pypdf（纯 Python PDF 提取）
cp -r "$WS/shared/pypdf" "$PKG/交付自检工具/shared/"

# 5. dftt_timecode
cp "$WS/shared/dftt_timecode"/{__init__,error,pattern}.py "$PKG/交付自检工具/shared/dftt_timecode/"
cp "$WS/shared/dftt_timecode/core"/{dftt_timecode,dftt_timerange}.py "$PKG/交付自检工具/shared/dftt_timecode/core/"

# 5. 字典文件
if ls "$WS/交付自检工具/dicts"/*.{txt,csv} 1>/dev/null 2>&1; then
    cp "$WS/交付自检工具/dicts"/*.{txt,csv} "$PKG/交付自检工具/dicts/" || { echo "❌ 字典拷贝失败"; exit 1; }
fi

# 6. 安装脚本 → 中文名
chmod +x "$PKG/交付自检工具/install.command"
mv "$PKG/交付自检工具/install.command" "$PKG/安装.command"

# 7. 清理缓存
find "$PKG" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

echo "✅ $(find "$PKG" -type f | wc -l) 源文件"

# 8. 加入 Python 安装包（如果项目目录有）
PY_NAME="Python安装包.pkg"
if [ -f "$SCRIPT_DIR/$PY_NAME" ]; then
    cp "$SCRIPT_DIR/$PY_NAME" "$PKG/$PY_NAME"
    echo "  含 Python 安装包"
fi

# 9. 打包 zip
cd "$SCRIPT_DIR/_build"
zip -rq "$ZIP" "$(basename "$PKG")/"
rm -rf "$PKG"

ls -lh "$ZIP"
