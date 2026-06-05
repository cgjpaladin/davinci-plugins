#!/bin/bash
# build_personal.sh — 构建交付自检工具个人版安装包
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG="$SCRIPT_DIR/_build/交付自检工具_个人版"
ZIP="$SCRIPT_DIR/_build/交付自检工具_个人版.zip"
# --all 模式：一次输出全量 + 增量两个包
if [ "$1" = "--all" ]; then
    bash "$0" && bash "$0" --update
    echo "═══ 全量包 + 增量包 完成 ═══"
    exit 0
fi
# 增量更新包用 ASCII 根目录名避免 zip 乱码
if [ "$1" = "--update" ]; then
    PKG="$SCRIPT_DIR/_build/davinci_plugin_update"
    ZIP="$SCRIPT_DIR/_build/交付自检工具_更新包.zip"
fi
PY_PKG="$HOME/Desktop/交付自检工具_个人版/Python安装包.pkg"

echo "═══ 构建个人版安装包 ═══"

# 1. 清理
rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG/交付自检工具/shared/dftt_timecode/core" "$PKG/交付自检工具/dicts" "$PKG/交付自检工具/shared/ui"

# 2. 核心文件（从原版同步最新）
cp "$WS/交付自检工具"/ui.py "$WS/交付自检工具"/check_core.py "$WS/交付自检工具"/config.py "$PKG/交付自检工具/"
cp "$WS/交付自检工具"/launcher_personal.py "$WS/交付自检工具"/shell_personal.py "$WS/交付自检工具"/install.command "$WS/交付自检工具"/.env.example "$PKG/交付自检工具/"

# 3. shared 模块（全套）
cp "$WS/shared"/{deploy_config,fusionscript_loader,log_writer,camera_detect,script_parser,llm_typo_check,llm_providers,timecode,mappings,launcher_router,subtitle_state,macos_utils,updater,update_config,license,_write_env,secure_store}.py "$PKG/交付自检工具/shared/"
cp "$WS/shared/ui/theme.py" "$PKG/交付自检工具/shared/ui/"

# 4. pypdf（纯 Python PDF 提取 — 全量包含，增量包跳过）
if [ "$1" != "--update" ]; then
    cp -r "$WS/shared/pypdf" "$PKG/交付自检工具/shared/"
fi

# 5. dftt_timecode
cp "$WS/shared/dftt_timecode"/{__init__,error,pattern}.py "$PKG/交付自检工具/shared/dftt_timecode/"
cp "$WS/shared/dftt_timecode/core"/{dftt_timecode,dftt_timerange}.py "$PKG/交付自检工具/shared/dftt_timecode/core/"

# 5. 字典文件
if ls "$WS/交付自检工具/dicts"/*.{txt,csv} 1>/dev/null 2>&1; then
    cp "$WS/交付自检工具/dicts"/*.{txt,csv} "$PKG/交付自检工具/dicts/" || { echo "❌ 字典拷贝失败"; exit 1; }
fi

# 6. 安装脚本（--update 模式只用 ASCII 名避免乱码）
chmod +x "$PKG/交付自检工具/install.command"
if [ "$1" = "--update" ]; then
    mv "$PKG/交付自检工具/install.command" "$PKG/install_update.command"
else
    mv "$PKG/交付自检工具/install.command" "$PKG/安装.command"
fi

# 7. 清理缓存
find "$PKG" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

echo "✅ $(find "$PKG" -type f | wc -l) 源文件"

# 8. 加入 Python 安装包（--update 模式跳过）
if [ "$1" != "--update" ]; then
    PY_NAME="Python安装包.pkg"
    if [ -f "$SCRIPT_DIR/$PY_NAME" ]; then
        cp "$SCRIPT_DIR/$PY_NAME" "$PKG/$PY_NAME"
        echo "  含 Python 安装包"
    fi
else
    echo "  增量更新包（不含 Python）"
fi

# 9. 打包 zip
cd "$SCRIPT_DIR/_build"
zip -rq "$ZIP" "$(basename "$PKG")/"
rm -rf "$PKG"

ls -lh "$ZIP"

# 10. 出厂检验：zip 内版本号必须和源码一致
VER_SRC=$(grep '__version__' "$WS/交付自检工具/config.py" | head -1 | grep -o '"[^"]*"')
VER_ZIP=$(python3 -c "
import zipfile, sys
zf = zipfile.ZipFile('$ZIP', metadata_encoding='utf-8')
for n in zf.namelist():
    if 'config.py' in n:
        for L in zf.read(n).decode().split('\n'):
            if '__version__' in L:
                import re; m=re.search(r'\"([^\"]+)\"',L);
                if m: print(m.group(1)); sys.exit(0)
")
if [ "$VER_SRC" != "\"$VER_ZIP\"" ]; then
    echo "❌ 出厂检验失败: zip内=$VER_ZIP 源码=$VER_SRC"
    rm -f "$ZIP"
    exit 1
fi
echo "✅ 出厂检验通过: $VER_ZIP"

# 11. 预热 ghproxy 缓存（可选）
if [ "${WARM_CDN:-0}" = "1" ]; then
    GH_URL="https://ghproxy.net/https://github.com/cgjpaladin/davinci-plugins/releases/download/v${VER_ZIP}/update_latest.zip"
    echo "🔥 预热 CDN 缓存..."
    curl -sLo /dev/null -w "  ghproxy: %{time_total}s\n" "$GH_URL" || true
fi
