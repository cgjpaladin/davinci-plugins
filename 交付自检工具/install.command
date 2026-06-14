#!/bin/bash
clear

# ═══════════════════════════════════════
# 安装日志
# ═══════════════════════════════════════
LOG="$HOME/.workbuddy/logs/交付自检工具/install_$(hostname)_$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG")"
exec 2>&1 | tee "$LOG"
echo "══════ 交付自检工具 安装日志 $(date '+%Y-%m-%d %H:%M:%S') ══════"
echo ""

# ── --update 静默模式：跳过 Python/凭证，直接覆盖安装 ──
IS_UPDATE=0
if [ "$1" = "--update" ]; then
    IS_UPDATE=1
    echo "🔄 静默更新模式"
fi

# ═══════════════════════════════════════
# 路径
# ═══════════════════════════════════════
INSTALL_DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具"
FUSION_SCRIPTS="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ZIP_SRC="$SCRIPT_DIR/交付自检工具.zip"
SOURCE="$SCRIPT_DIR/交付自检工具"
# --update 模式：找 install.command 同级目录下的「交付自检工具」子目录
if [ $IS_UPDATE -eq 1 ]; then
    # 尝试标准路径
    if [ -d "$SCRIPT_DIR/交付自检工具" ]; then
        SOURCE="$SCRIPT_DIR/交付自检工具"
    else
        # zip 解压后中文目录名可能乱码，扫描找含 install.command 同级的源码目录
        for d in "$SCRIPT_DIR"/*/; do
            if [ -d "${d}shared" ] && [ -f "${d}ui.py" ]; then
                SOURCE="${d%/}"
                break
            fi
        done
    fi
fi

echo "📁 安装源: $([ $IS_UPDATE -eq 1 ] && echo "$SOURCE" || echo "$ZIP_SRC")"
echo "📁 安装目标: $INSTALL_DIR"
echo "📁 壳位置: $FUSION_SCRIPTS/交付自检工具.py"
echo "👤 当前用户: $(whoami)"
echo "💻 主机名: $(hostname)"
echo "🍎 macOS: $(sw_vers -productVersion 2>/dev/null || echo unknown)"
echo ""

# ═══════════════════════════════════════
# 1. 解压完整性
# ═══════════════════════════════════════
echo "→ [1/6] 检查安装文件..."
if [ $IS_UPDATE -eq 0 ]; then
    if [ ! -f "$ZIP_SRC" ]; then
        echo "❌ 找不到 $ZIP_SRC"
        osascript -e 'display dialog "找不到安装文件「交付自检工具.zip」。\n\n请确保安装.command和交付自检工具.zip在同一文件夹内。\n如果从百度网盘下载，请下载整个文件夹，不要只下载单个文件。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
    ZIP_SIZE=$(stat -f%z "$ZIP_SRC" 2>/dev/null || echo 0)
    echo "   ✅ zip 文件: $((ZIP_SIZE / 1048576))MB"
else
    if [ ! -d "$SOURCE" ]; then
        echo "❌ 找不到 $SOURCE"
        osascript -e 'display dialog "找不到安装文件。\n\n请重新下载更新包。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
    FILE_COUNT=$(find "$SOURCE" -type f | wc -l | tr -d ' ')
    echo "   ✅ 找到 $FILE_COUNT 个文件"
fi
echo ""

# ═══════════════════════════════════════
# 1.5. 达芬奇检测（仅首次安装）
# ═══════════════════════════════════════
RESOLVE_SUPPORT="/Library/Application Support/Blackmagic Design/DaVinci Resolve"
if [ $IS_UPDATE -eq 0 ] && [ ! -d "$RESOLVE_SUPPORT" ]; then
    echo "⚠ 未检测到达芬奇 Resolve"
    echo "   $RESOLVE_SUPPORT"
    echo "   请先安装并至少运行一次达芬奇，再安装本插件。"
    osascript -e 'display dialog "未检测到达芬奇 Resolve。\n\n请先安装达芬奇并至少打开一次，再运行本安装脚本。\n\n达芬奇首次启动会自动创建所需目录。" buttons {"好的"} default button 1 with icon caution'
    exit 1
fi

PYTHON=""
NEED_PYTHON=0

if [ $IS_UPDATE -eq 0 ]; then

# ═══════════════════════════════════════
# 2. Python 检测+安装
# ═══════════════════════════════════════
echo "→ [2/6] 检测 Python..."
PYTHON=""
FRAMEWORK_OK=""
HAS_CLT=0
xcode-select -p &>/dev/null && HAS_CLT=1

# 只查 Framework Python — /usr/bin/python3 是 Xcode CLT stub，无 CLT 时触碰会弹安装窗口
for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
    echo "   检查: $p"
    if [ -x "$p" ]; then
        VER=$("$p" --version 2>&1)
        echo "     → $VER (Framework ✅)"
        PYTHON="$p"
        FRAMEWORK_OK="yes"
        break
    fi
done

if [ -z "$FRAMEWORK_OK" ] && [ "$HAS_CLT" -eq 1 ] && [ -x "/usr/bin/python3" ]; then
    echo "   检查: /usr/bin/python3"
    echo "     → $(/usr/bin/python3 --version 2>&1) ⚠ 非 Framework，达芬奇不识别"
fi

if [ -z "$PYTHON" ] || [ -z "$FRAMEWORK_OK" ]; then
    if [ -n "$PYTHON" ] && [ -z "$FRAMEWORK_OK" ]; then
        echo "   ⚠ 当前 Python 是 Xcode CLT 版本，达芬奇不识别，将在安装时自动处理"
    else
        echo "   ⚠ 未找到 Python，将在安装时自动安装"
    fi
    NEED_PYTHON=1
else
    echo "   ✅ Python: $($PYTHON --version 2>&1)"
fi
echo ""

# ═══════════════════════════════════════
# 3. 已安装检测
# ═══════════════════════════════════════
echo "→ [3/6] 检查已有安装..."
if [ -d "$INSTALL_DIR" ]; then
    echo "   发现已有安装"
    RESPONSE=$(osascript -e 'button returned of (display dialog "已安装过。\n\n请选择：" buttons {"覆盖安装", "取消"} default button "取消" with icon caution)' 2>/dev/null || echo "取消")
    echo "   用户选择: $RESPONSE"
    case "$RESPONSE" in
        "覆盖安装")
            echo "   将执行覆盖安装..."
            ;;
        "取消")
            echo "   用户取消"
            exit 0
            ;;
    esac
else
    echo "   首次安装"
fi
echo ""


else
    # --update 模式：快速检测 Framework Python
    echo "→ 检测 Python..."
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then
            PYTHON="$p"; echo "   ✅ $($PYTHON --version 2>&1)"; break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "   ❌ 未找到 Framework Python，更新无法继续"
        exit 1
    fi
fi

# ═══════════════════════════════════════
# 4. 中转文件
# ═══════════════════════════════════════
echo "→ [4/6] 准备安装..."
rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
if [ $IS_UPDATE -eq 0 ]; then
    # 首次安装：解压内层 zip
    mkdir -p /tmp/_deli_temp
    if ! unzip -q "$ZIP_SRC" -d /tmp/_deli_temp 2>/dev/null; then
        echo "   ❌ zip 文件损坏，请重新下载"
        rm -rf /tmp/_deli_temp
        osascript -e 'display dialog "安装包已损坏。\n\n请重新下载。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
    # 重组：源码 → /tmp/_deli_src，Python.pkg 移出 → /tmp/_deli_python.pkg
    if [ -d "/tmp/_deli_temp/交付自检工具" ]; then
        mv /tmp/_deli_temp/交付自检工具 /tmp/_deli_src
    else
        echo "   ❌ zip 结构异常，缺少交付自检工具/ 目录"
        rm -rf /tmp/_deli_temp
        osascript -e 'display dialog "安装包结构异常。\n\n请重新下载。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
    mv /tmp/_deli_src/Python安装包.pkg /tmp/_deli_python.pkg 2>/dev/null || true
    rm -rf /tmp/_deli_temp
    echo "   ✅ zip 已解压: $(find /tmp/_deli_src -type f | wc -l | tr -d ' ') files"
    if [ $NEED_PYTHON -eq 1 ] && [ ! -f "/tmp/_deli_python.pkg" ]; then
        echo "   ⚠ 未找到 Python安装包.pkg，将跳过自动安装"
    fi
else
    # --update 模式：直接复制源码目录
    if ! cp -r "$SOURCE" /tmp/_deli_src 2>/dev/null; then
        echo "   ❌ 复制到 /tmp 失败"
        osascript -e 'display dialog "准备安装失败。\n请检查磁盘空间或关闭其他程序后重试。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
    echo "   ✅ 源文件已复制到 /tmp/_deli_src ($(find /tmp/_deli_src -type f | wc -l | tr -d ' ') files)"
fi
echo ""

# ═══════════════════════════════════════
# 5. 管理员安装
# ═══════════════════════════════════════
echo "→ [5/6] 安装到系统目录..."
echo ""
echo "   此工具需安装到达芬奇系统插件目录。"
echo "   macOS 会弹出窗口要求输入开机密码——这是正常的系统权限确认。"
echo "   密码仅用于本次安装，不会被记录或传输。"
echo ""
echo "→ [5/6] 安装到系统目录（请在弹出的窗口中输入密码）..."


INSTALL_LOG="/tmp/_deli_install.log"
if [ $IS_UPDATE -eq 1 ]; then
    # --update 模式：已在外层 root 下，直接安装
    echo "   以 root 身份直接安装..."
    echo "  → mkdir" && mkdir -p "$FUSION_SCRIPTS" &&
    echo "  → backup .env" && [ ! -f "$INSTALL_DIR/.env" ] || (cp "$INSTALL_DIR/.env" /tmp/_deli_env_bak || { echo "  ❌ 备份 .env 失败，中止更新"; exit 1; }) &&
    echo "  → backup dicts" && (rm -rf /tmp/_deli_dicts_bak; if [ -d "$INSTALL_DIR/dicts" ]; then cp -r "$INSTALL_DIR/dicts/" /tmp/_deli_dicts_bak/; fi) &&
    echo "  → cp new to staging" && rm -rf "$INSTALL_DIR.new" && cp -r /tmp/_deli_src "$INSTALL_DIR.new" &&
    echo "  → rm old" && rm -rf "$INSTALL_DIR" &&
    echo "  → mv staging" && mv "$INSTALL_DIR.new" "$INSTALL_DIR" &&
    echo "  → restore dicts" && if [ -d /tmp/_deli_dicts_bak ]; then cp /tmp/_deli_dicts_bak/* "$INSTALL_DIR/dicts/" 2>/dev/null; rm -rf /tmp/_deli_dicts_bak; fi &&
    echo "  → deploy shell" && cp "$INSTALL_DIR/shell_personal.py" "$FUSION_SCRIPTS/交付自检工具.py" && chmod 755 "$FUSION_SCRIPTS/交付自检工具.py" &&
    echo "  → chown" && chown -R $USER "$INSTALL_DIR" &&
    echo "  → clean pyc" && find "$INSTALL_DIR" -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true &&
    echo "  → restore/init .env" && if [ -f /tmp/_deli_env_bak ]; then cp /tmp/_deli_env_bak "$INSTALL_DIR/.env"; rm -f /tmp/_deli_env_bak; else cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"; fi &&
    echo "  → write license config" && "$PYTHON" "$INSTALL_DIR/shared/_write_env.py" && echo "  ✅ 安装完成"
    _UPDATE_OK=1
elif osascript <<EOF 2>"$INSTALL_LOG"
do shell script "
    echo '  → mkdir' >> '$INSTALL_LOG' &&
    mkdir -p '$FUSION_SCRIPTS' &&

    echo '  → python install' >> '$INSTALL_LOG' &&
    if [ -f /tmp/_deli_python.pkg ]; then
        installer -pkg /tmp/_deli_python.pkg -target / >> '$INSTALL_LOG' 2>&1 || {
            echo '  ❌ Python 安装失败，请查看日志' && exit 1
        }
    fi &&

    echo '  → backup .env' >> '$INSTALL_LOG' &&
    if [ -f '$INSTALL_DIR/.env' ]; then cp '$INSTALL_DIR/.env' /tmp/_deli_env_bak; fi &&

    echo '  → rm old + cp new' >> '$INSTALL_LOG' &&
    rm -rf '$INSTALL_DIR' && cp -r /tmp/_deli_src '$INSTALL_DIR' &&

    echo '  → deploy shell' >> '$INSTALL_LOG' &&
    cp '$INSTALL_DIR/shell_personal.py' '$FUSION_SCRIPTS/交付自检工具.py' && chmod 755 '$FUSION_SCRIPTS/交付自检工具.py' &&

    echo '  → chown' >> '$INSTALL_LOG' &&
    chown -R $USER '$INSTALL_DIR' &&
    echo '  → ensure script dir perms' >> '$INSTALL_LOG' &&
    chmod 755 '$FUSION_SCRIPTS' 2>/dev/null || true &&

    echo '  → restore/init .env' >> '$INSTALL_LOG' &&
    if [ -f /tmp/_deli_env_bak ]; then
        cp /tmp/_deli_env_bak '$INSTALL_DIR/.env' && rm -f /tmp/_deli_env_bak
    else
        cp '$INSTALL_DIR/.env.example' '$INSTALL_DIR/.env'
    fi &&

    echo '  → cleanup' >> '$INSTALL_LOG' &&
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg
" with administrator privileges
EOF
then
    echo "   ✅ 系统安装完成"
else
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
    echo "   ❌ 安装失败"
    echo "   错误日志:"
    tail -5 "$INSTALL_LOG" 2>/dev/null
    osascript -e "display dialog \"安装失败。\n\n请检查：密码是否正确、磁盘是否已满。\n\n详情见: $INSTALL_LOG\" buttons {\"好的\"} default button 1 with icon stop"
    exit 1
fi
if [ "${_UPDATE_OK:-0}" -eq 1 ]; then
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
    echo "   ✅ 静默安装完成"
fi
echo ""

# ═══════════════════════════════════════
# 6. 验证
# ═══════════════════════════════════════
echo "→ [6/6] 验证安装..."

PASS=1

# 壳
if [ -f "$FUSION_SCRIPTS/交付自检工具.py" ]; then
    SHELL_PERM=$(stat -f "%p" "$FUSION_SCRIPTS/交付自检工具.py")
    if [ "$SHELL_PERM" = "100755" ] || [ "$SHELL_PERM" = "40755" ]; then
        echo "   ✅ 壳: $FUSION_SCRIPTS/交付自检工具.py (perms=$SHELL_PERM)"
    else
        echo "   ⚠ 壳权限: $SHELL_PERM (期望 755)"
    fi
else
    echo "   ❌ 壳缺失!"
    PASS=0
fi

# ui.py
if [ -f "$INSTALL_DIR/ui.py" ]; then
    echo "   ✅ 核心: $INSTALL_DIR/ui.py"
else
    echo "   ❌ 核心缺失!"
    PASS=0
fi

# shared modules
SHARED_COUNT=$(find "$INSTALL_DIR/shared" -name "*.py" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
echo "   ✅ shared 模块: $SHARED_COUNT 个"

# .env
if [ -f "$INSTALL_DIR/.env" ]; then
    echo "   ✅ .env 配置文件"
else
    echo "   ⚠ .env 缺失 (已自动创建 .env.example)"
fi

# Python modules sanity check
echo ""
# 如果步骤5自动安装了Python，重新检测
if [ $NEED_PYTHON -eq 1 ] || [ -z "$PYTHON" ]; then
    echo "   🔍 重新检测 Python..."
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then
            PYTHON="$p"; echo "     ✅ $($PYTHON --version 2>&1)"; break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "   ❌ 仍未找到 Python。请从 python.org 下载安装 Python 3.13+"
        PASS=0
    fi
fi
if [ -n "$PYTHON" ]; then
echo "   🔍 Python 导入检测..."
$PYTHON -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
sys.path.insert(0, '$INSTALL_DIR/shared')
try:
    import config
    print(f'     ✅ config.py (IS_PERSONAL={config.IS_PERSONAL})')
    import check_core
    print(f'     ✅ check_core.py')
    import ui
    print(f'     ✅ ui.py (v{config.version_string()})')
except Exception as e:
    print(f'     ❌ 导入失败: {e}')
    sys.exit(1)
" 2>&1

if [ $? -eq 0 ]; then
    echo "   ✅ Python 模块全部可导入"
else
    echo "   ⚠ 模块导入有问题，请查看上方日志"
fi
else
    echo "   ⚠ 跳过 Python 导入检测（Python 未安装）"
fi

echo ""

# ═══════════════════════════════════════
# 结果
# ═══════════════════════════════════════
if [ $PASS -eq 1 ]; then
    echo "══════ 安装完成 ✅ ══════"
    echo ""
    echo "日志: $LOG"
    echo "安装目录: $INSTALL_DIR"
    echo ""
    osascript -e 'display dialog "✅ 安装完成！\n\n使用方法：\n  打开达芬奇 → Workspace → Scripts → 交付自检工具" buttons {"好的"} default button "好的" with icon note'
else
    echo "══════ 安装异常 ❌ ══════"
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
    osascript -e 'display dialog "安装验证失败。\n请截图安装日志后联系支持。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi
