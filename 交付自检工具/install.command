#!/bin/bash
clear

# ═══════════════════════════════════════
# 安装日志
# ═══════════════════════════════════════
LOG="/tmp/交付自检工具_安装.log"
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

echo "📁 安装源: $SOURCE"
echo "📁 安装目标: $INSTALL_DIR"
echo "📁 壳位置: $FUSION_SCRIPTS/交付自检工具.py"
echo "👤 当前用户: $(whoami)"
echo "💻 主机名: $(hostname)"
echo "🍎 macOS: $(sw_vers -productVersion 2>/dev/null || echo unknown)"
echo ""

# ═══════════════════════════════════════
# 1. 解压完整性
# ═══════════════════════════════════════
echo "→ [1/7] 检查安装文件..."
if [ ! -d "$SOURCE" ]; then
    echo "❌ 找不到 $SOURCE"
    echo "请将 zip 解压后再运行。不要在压缩包里直接双击。"
    osascript -e 'display dialog "找不到安装文件。\n\n请先将 zip 解压到文件夹，再双击「安装.command」。\n不要在压缩包里直接打开。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi
FILE_COUNT=$(find "$SOURCE" -type f | wc -l | tr -d ' ')
echo "   ✅ 找到 $FILE_COUNT 个文件"
echo ""

if [ $IS_UPDATE -eq 0 ]; then

# ═══════════════════════════════════════
# 2. Python 检测+安装
# ═══════════════════════════════════════
echo "→ [2/7] 检测 Python..."
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
        MSG="当前 Python 是 Xcode CLT 版本，达芬奇不识别。\n\n需要安装 python.org 的 Python 3。\n\n安装包已附带（双击打开、一路下一步即可）。\n安装完成后再次双击「安装.command」。"
        echo "   需要安装 Framework Python"
    else
        MSG="未找到 Python 3。\n\n安装包已附带（双击打开、一路下一步即可）。\n安装完成后再次双击「安装.command」。"
        echo "   未找到任何 Python"
    fi

    PKG_FILE="$SCRIPT_DIR/Python安装包.pkg"
    if [ ! -f "$PKG_FILE" ]; then
        echo "   ❌ 未找到 Python安装包.pkg（zip 不完整）"
        osascript -e 'display dialog "未找到 Python 安装包。\n请重新下载完整版 zip。" buttons {"好的"} with icon stop'
        exit 1
    fi

    echo "   → 打开 Python 安装包..."
    open "$PKG_FILE"
    osascript -e "display dialog \"$MSG\" buttons {\"好的\"} default button 1 with icon note"
    exit 0
else
    echo "   ✅ Python: $($PYTHON --version 2>&1)"
fi
echo ""

# ═══════════════════════════════════════
# 3. 已安装检测
# ═══════════════════════════════════════
echo "→ [3/7] 检查已有安装..."
if [ -d "$INSTALL_DIR" ]; then
    echo "   发现已有安装"
    RESPONSE=$(osascript -e 'button returned of (display dialog "已安装过。\n\n请选择：" buttons {"更新 Key", "覆盖安装", "取消"} default button "覆盖安装" with icon caution)' 2>/dev/null || echo "取消")
    echo "   用户选择: $RESPONSE"
    case "$RESPONSE" in
        "更新 Key")
            RESP=$(osascript -e 'button returned of (display dialog "更新哪种凭证？" buttons {"DeepSeek", "飞书", "取消"} default button "DeepSeek" with icon note)' 2>/dev/null)
            echo "   更新: $RESP"
            if [ "$RESP" = "DeepSeek" ] || [ -z "$RESP" ]; then
                API_KEY=$(osascript -e 'text returned of (display dialog "输入 DeepSeek API Key（留空不修改）\n\n获取地址: platform.deepseek.com → API Keys" default answer "" buttons {"取消", "保存"} default button "保存" with icon note)' 2>/dev/null)
                if [ -n "$API_KEY" ]; then
                    echo "   写入 DeepSeek Key..."
                    osascript -e "do shell script \"$PYTHON -c \\\"
p='$INSTALL_DIR/.env'
lines=[l.rstrip() for l in open(p)]
for i,l in enumerate(lines):
    if l.startswith('DEEPSEEK_API_KEY='): lines[i]='DEEPSEEK_API_KEY=$API_KEY'; break
else: lines.append('DEEPSEEK_API_KEY=$API_KEY')
open(p,'w').write(chr(10).join(lines))
\\\" with administrator privileges" 2>/dev/null
                    osascript -e 'display dialog "DeepSeek Key 已更新！" buttons {"好的"} default button 1 with icon note'
                fi
            elif [ "$RESP" = "飞书" ]; then
                FS_APP=$(osascript -e 'text returned of (display dialog "飞书 Bot App ID（留空不修改）" default answer "" buttons {"取消", "保存"} default button "保存" with icon note)' 2>/dev/null)
                if [ -n "$FS_APP" ]; then
                    FS_SEC=$(osascript -e 'text returned of (display dialog "飞书 Bot App Secret" default answer "" buttons {"取消", "保存"} default button "保存" with hidden answer with icon note)' 2>/dev/null)
                    if [ -n "$FS_SEC" ]; then
                        echo "   写入飞书凭证..."
                        osascript -e "do shell script \"$PYTHON -c \\\"
p='$INSTALL_DIR/.env'
lines=[l.rstrip() for l in open(p)]
for prefix,val in [('FEISHU_BOT_APP_ID=','$FS_APP'),('FEISHU_BOT_APP_SECRET=','$FS_SEC')]:
    for i,l in enumerate(lines):
        if l.startswith(prefix): lines[i]=prefix+val; break
    else: lines.append(prefix+val)
open(p,'w').write(chr(10).join(lines))
\\\" with administrator privileges" 2>/dev/null
                        osascript -e 'display dialog "飞书凭证已更新！" buttons {"好的"} default button 1 with icon note'
                    fi
                fi
            fi
            exit 0
            ;;
        "取消")
            echo "   用户取消"
            exit 0
            ;;
    esac
    echo "   将执行覆盖安装..."
else
    echo "   首次安装"
fi
echo ""

# ═══════════════════════════════════════
# 4. 凭证输入
# ═══════════════════════════════════════
echo "→ [4/7] 输入凭证（均可跳过）..."
API_KEY=$(osascript -e 'text returned of (display dialog "请输入 DeepSeek API Key（没有可留空，以后补）\n\n获取地址: platform.deepseek.com → API Keys" default answer "" buttons {"跳过", "保存"} default button "保存" with icon note)' 2>/dev/null || echo "")
if [ -n "$API_KEY" ]; then
    echo "   ✅ DeepSeek Key: ${API_KEY:0:10}..."
else
    echo "   ⏭ 跳过 DeepSeek Key"
fi

FEISHU_APP=$(osascript -e 'text returned of (display dialog "飞书 Bot App ID（可选，用于下载飞书文档）\n\n没有可留空，以后补" default answer "" buttons {"跳过", "保存"} default button "保存" with icon note)' 2>/dev/null || echo "")
FEISHU_SECRET=""
if [ -n "$FEISHU_APP" ]; then
    echo "   ✅ 飞书 App ID: $FEISHU_APP"
    FEISHU_SECRET=$(osascript -e 'text returned of (display dialog "飞书 Bot App Secret" default answer "" buttons {"跳过", "保存"} default button "保存" with hidden answer with icon note)' 2>/dev/null || echo "")
    if [ -n "$FEISHU_SECRET" ]; then
        echo "   ✅ 飞书 Secret: 已输入"
    else
        echo "   ⏭ 跳过飞书 Secret（只有 App ID 不够）"
        FEISHU_APP=""
    fi
else
    echo "   ⏭ 跳过飞书凭证"
fi
echo ""
fi  # IS_UPDATE 判断结束

# ═══════════════════════════════════════
# 5. 中转文件
# ═══════════════════════════════════════
echo "→ [5/7] 准备安装..."
rm -rf /tmp/_deli_src 2>/dev/null
if ! cp -r "$SOURCE" /tmp/_deli_src 2>/dev/null; then
    echo "   ❌ 复制到 /tmp 失败"
    osascript -e 'display dialog "准备安装失败。\n请检查磁盘空间或关闭其他程序后重试。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi
echo "   ✅ 源文件已复制到 /tmp/_deli_src ($(find /tmp/_deli_src -type f | wc -l | tr -d ' ') files)"
echo ""

# ═══════════════════════════════════════
# 6. 管理员安装
# ═══════════════════════════════════════
echo "→ [6/7] 安装到系统目录（请在弹出的窗口中输入密码）..."

# 用 tmp 文件安全传递凭证（避免 shell 注入）
echo "$API_KEY" > /tmp/_deli_apikey 2>/dev/null
echo "$FEISHU_APP" > /tmp/_deli_fsapp 2>/dev/null
echo "$FEISHU_SECRET" > /tmp/_deli_fssec 2>/dev/null

INSTALL_LOG="/tmp/_deli_install.log"
if osascript <<EOF 2>"$INSTALL_LOG"
do shell script "
    echo '  → mkdir' >> '$INSTALL_LOG' &&
    mkdir -p '$FUSION_SCRIPTS' &&

    echo '  → backup .env' >> '$INSTALL_LOG' &&
    if [ -f '$INSTALL_DIR/.env' ]; then cp '$INSTALL_DIR/.env' /tmp/_deli_env_bak; fi &&

    echo '  → rm old + cp new' >> '$INSTALL_LOG' &&
    rm -rf '$INSTALL_DIR' && cp -r /tmp/_deli_src '$INSTALL_DIR' &&

    echo '  → deploy shell' >> '$INSTALL_LOG' &&
    cp '$INSTALL_DIR/shell_personal.py' '$FUSION_SCRIPTS/交付自检工具.py' && chmod 755 '$FUSION_SCRIPTS/交付自检工具.py' &&

    echo '  → chown' >> '$INSTALL_LOG' &&
    chown -R $USER '$INSTALL_DIR' &&

    echo '  → restore/init .env' >> '$INSTALL_LOG' &&
    if [ -f /tmp/_deli_env_bak ]; then
        cp /tmp/_deli_env_bak '$INSTALL_DIR/.env' && rm -f /tmp/_deli_env_bak
    else
        cp '$INSTALL_DIR/.env.example' '$INSTALL_DIR/.env'
    fi &&

    if [ -f /tmp/_deli_apikey ] || [ -f /tmp/_deli_fsapp ]; then
        echo '  → write credentials' >> '$INSTALL_LOG' &&
        $PYTHON -c '
import os
p = \"$INSTALL_DIR/.env\"
lines = [l.rstrip() for l in open(p)]
for fname, prefix in [(\"/tmp/_deli_apikey\", \"DEEPSEEK_API_KEY=\"), 
                       (\"/tmp/_deli_fsapp\", \"FEISHU_BOT_APP_ID=\"),
                       (\"/tmp/_deli_fssec\", \"FEISHU_BOT_APP_SECRET=\")]:
    if os.path.exists(fname):
        val = open(fname).read().strip()
        if val:
            replaced = False
            for i, l in enumerate(lines):
                if l.startswith(prefix):
                    lines[i] = prefix + val
                    replaced = True
                    break
            if not replaced:
                lines.append(prefix + val)
open(p, \"w\").write(chr(10).join(lines))
' &&
        rm -f /tmp/_deli_apikey /tmp/_deli_fsapp /tmp/_deli_fssec
    fi &&

    echo '  → cleanup' >> '$INSTALL_LOG' &&
    rm -rf /tmp/_deli_src
" with administrator privileges
EOF
then
    echo "   ✅ 系统安装完成"
else
    rm -rf /tmp/_deli_src 2>/dev/null
    echo "   ❌ 安装失败"
    echo "   错误日志:"
    tail -5 "$INSTALL_LOG" 2>/dev/null
    osascript -e "display dialog \"安装失败。\n\n请检查：密码是否正确、磁盘是否已满。\n\n详情见: $INSTALL_LOG\" buttons {\"好的\"} default button 1 with icon stop"
    exit 1
fi
echo ""

# ═══════════════════════════════════════
# 7. 验证
# ═══════════════════════════════════════
echo "→ [7/7] 验证安装..."

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
    rm -rf /tmp/_deli_src 2>/dev/null
    osascript -e 'display dialog "安装验证失败。\n请截图安装日志后联系支持。" buttons {"好的"} default button 1 with icon stop'
    exit 1
fi
