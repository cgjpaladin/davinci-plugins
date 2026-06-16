#!/bin/bash
# build_personal.sh — 构建交付自检工具个人版安装包
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"
# 从 config.py 读取版本号（唯一真相源）
VER=$(python3 -c "exec(open('$WS/交付自检工具/config.py', encoding='utf-8').read()); print(__version__)")
PKG="$SCRIPT_DIR/_build/交付自检工具_v${VER}"
INNER_ZIP_NAME="请勿直接解压此文件.zip"
# --all 模式：一次输出全量 + 增量两个包
if [ "$1" = "--all" ]; then
    bash "$0" && bash "$0" --update
    echo "═══ 全量包 + 增量包 完成 ═══"
    exit 0
fi
# 增量更新包用 ASCII 根目录名避免 zip 乱码
if [ "$1" = "--update" ]; then
    PKG="$SCRIPT_DIR/_build/davinci_plugin_update"
    ZIP="$SCRIPT_DIR/_build/update_latest.zip"
fi
INNER_ZIP="$PKG/$INNER_ZIP_NAME"

echo "═══ 构建个人版安装包 ═══"
echo "📦 版本: v$VER"

# 1. 清理
rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG/交付自检工具/shared/dftt_timecode/core" "$PKG/交付自检工具/dicts" "$PKG/交付自检工具/shared/ui"

# 2. 核心文件（从原版同步最新）
cp "$WS/交付自检工具"/ui.py "$WS/交付自检工具"/check_core.py "$WS/交付自检工具"/config.py "$PKG/交付自检工具/"
cp "$WS/交付自检工具"/launcher_personal.py "$WS/交付自检工具"/shell_personal.py "$WS/交付自检工具"/install.command "$WS/交付自检工具"/.env.example "$PKG/交付自检工具/"

# 个人版发布永远不带 dev 通道
sed -i '' 's/^__channel__ = ".*"/__channel__ = ""/' "$PKG/交付自检工具/config.py"
python3 -c "import sys; sys.path.insert(0,'$PKG/交付自检工具'); from config import version_string; print(f'  ✅ 个人版: {version_string()}')"

# 3. shared 模块（全套）
cp "$WS/shared"/{deploy_config,fusionscript_loader,log_writer,camera_detect,script_parser,llm_typo_check,llm_providers,timecode,mappings,launcher_router,subtitle_state,macos_utils,updater,update_config,license,_write_env,secure_store,cross_platform,tk_dialogs}.py "$PKG/交付自检工具/shared/"
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

# 6. 安装脚本（--update 模式只用 ASCII 名避免乱码）
chmod +x "$PKG/交付自检工具/install.command"
if [ "$1" = "--update" ]; then
    mv "$PKG/交付自检工具/install.command" "$PKG/install_update.command"
else
    mv "$PKG/交付自检工具/install.command" "$PKG/Mac安装.command"
fi

# 7. 清理缓存 + 清除 quarantine 属性（防下载后双击被拒）
find "$PKG" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -type f -exec xattr -c {} \; 2>/dev/null || true

echo "✅ $(find "$PKG" -type f | wc -l) 源文件"

# 8. 加入 Python 安装包（放在源码子目录内，一起打进内层 zip）
if [ "$1" != "--update" ]; then
    PY_NAME="python-3.13.13-macos11.pkg"
    if [ -f "$SCRIPT_DIR/$PY_NAME" ]; then
        cp "$SCRIPT_DIR/$PY_NAME" "$PKG/交付自检工具/$PY_NAME"
        echo "  含 Python 安装包"
    fi
else
    echo "  增量更新包（不含 Python）"
fi

# 8b. 首次安装包：将源码+Python.pkg打包为内层zip（二进制，百度不扫内容）
if [ "$1" != "--update" ]; then
    cd "$PKG" && zip -rq "$INNER_ZIP_NAME" "交付自检工具/"
    rm -rf "$PKG/交付自检工具/"
    echo "  📦 内层 zip 已创建"

    # 生成 README.txt（防 .command 权限丢失的指引）
    cat > "$PKG/先读我.txt" << 'READMEEOF'
═══════════════════════════
  交付自检工具 — 安装说明
═══════════════════════════

1. 双击「Mac安装.command」开始安装
   → 按提示输入开机密码（仅本次使用）

2. 如果双击没有反应或提示无法打开：
   打开「系统设置」→「隐私与安全性」
   向下滚动到「安全性」部分
   找到关于「Mac安装.command」的提示
   点击「仍要打开」
   → 然后再双击 Mac安装.command

3. 如果提示「没有正确的访问权限」：
   右键点击「Mac安装.command」→「打开方式」→「终端」

4. 安装完成后：
   打开达芬奇 → 工作区 → 脚本 → 交付自检工具

如有问题请联系：微信 paladinpp
READMEEOF
    echo "  📄 先读我.txt 已生成"
fi

# 9. 出厂检验（在内层 zip 上做，直接读 config.py）
if [ "$1" != "--update" ]; then
VER_SRC=$(grep '__version__' "$WS/交付自检工具/config.py" | head -1 | grep -o '"[^"]*"')
VER_ZIP=$(python3 -c "
import zipfile, sys
zf = zipfile.ZipFile('$INNER_ZIP', metadata_encoding='utf-8')
for n in zf.namelist():
    if 'config.py' in n:
        for L in zf.read(n).decode().split('\n'):
            if '__version__' in L:
                import re; m=re.search(r'\"([^\"]+)\"',L);
                if m: print(m.group(1)); sys.exit(0)
")
if [ "$VER_SRC" != "\"$VER_ZIP\"" ]; then
    echo "❌ 出厂检验失败: zip内=$VER_ZIP 源码=$VER_SRC"
    rm -rf "$PKG"; exit 1
fi
echo "✅ 出厂检验通过: $VER_ZIP"
fi

# --update 模式：打包为 update_latest.zip（ASCII 名，gh 不乱码）
if [ "$1" = "--update" ]; then
    cd "$SCRIPT_DIR/_build" && zip -rq "$ZIP" "$(basename "$PKG")/"
    ls -lh "$ZIP"
else
    # 首次安装：打包为分发 zip（百度网盘上传这一个文件）
    OUTER_ZIP="$SCRIPT_DIR/_build/交付自检工具_v${VER}.zip"
    cd "$SCRIPT_DIR/_build" && zip -rq "$OUTER_ZIP" "$(basename "$PKG")/"
    ls -lh "$OUTER_ZIP"
    echo "📂 百度网盘上传此 zip 即可"
fi
