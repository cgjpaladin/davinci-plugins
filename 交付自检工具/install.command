#!/bin/bash
clear

# ═══════════════════════════════════════
# 日志（仅写文件，用户看不到）
# ═══════════════════════════════════════
LOG_DIR="$HOME/Library/Logs/小裁缝工具"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/install_$(date +%Y%m%d_%H%M%S).log"
exec 3>&1 >"$LOG" 2>&1
# 自此：echo → 日志 | echo ... >&3 → 终端

echo "══════ 安装日志 $(date '+%Y-%m-%d %H:%M:%S') ══════"
echo "👤 $(whoami) @ $(hostname) | macOS $(sw_vers -productVersion 2>/dev/null || echo ?)"

IS_UPDATE=0
if [ "$1" = "--update" ]; then
    IS_UPDATE=1
    echo "🔄 更新模式"
fi

# ═══════════════════════════════════════
# 欢迎（终端可见）
# ═══════════════════════════════════════
echo >&3
echo "========================================" >&3
echo "  交付自检工具" >&3
echo "  针对 DaVinci Resolve 时间线的自动化检查插件" >&3
echo "  作者：电影裁缝 Bryan（微信 paladinpp / B站 电影裁缝Bryan）" >&3
echo "========================================" >&3
echo >&3
echo "  ⏳ 正在检测…" >&3

# ═══════════════════════════════════════
# 路径
# ═══════════════════════════════════════
INSTALL_DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具"
FUSION_SCRIPTS="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ZIP_SRC="$SCRIPT_DIR/data.zip"
SOURCE="$SCRIPT_DIR/交付自检工具"
if [ $IS_UPDATE -eq 1 ]; then
    if [ -d "$SCRIPT_DIR/交付自检工具" ]; then
        SOURCE="$SCRIPT_DIR/交付自检工具"
    else
        for d in "$SCRIPT_DIR"/*/; do
            if [ -d "${d}shared" ] && [ -f "${d}ui.py" ]; then
                SOURCE="${d%/}"; break
            fi
        done
    fi
fi
echo "📁 安装源: $([ $IS_UPDATE -eq 1 ] && echo "$SOURCE" || echo "$ZIP_SRC")"
echo "📁 安装目标: $INSTALL_DIR"

# ═══════════════════════════════════════
# 1. 文件完整性
# ═══════════════════════════════════════
if [ $IS_UPDATE -eq 0 ]; then
    if [ ! -f "$ZIP_SRC" ]; then
        osascript -e $'display dialog "找不到安装文件「data.zip」。\n\n请确保Mac安装.command和它位于同一文件夹内。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
else
    if [ ! -d "$SOURCE" ]; then
        osascript -e $'display dialog "找不到安装源文件。\n\n请重新下载更新包。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
fi

# 1.5 达芬奇检测
RESOLVE_SUPPORT="/Library/Application Support/Blackmagic Design/DaVinci Resolve"
if [ $IS_UPDATE -eq 0 ] && [ ! -d "$RESOLVE_SUPPORT" ]; then
    osascript -e $'display dialog "未检测到达芬奇 Resolve。\n\n请先安装达芬奇并至少打开一次，再运行本安装脚本。" buttons {"好的"} default button 1 with icon caution'
    exit 1
fi

# ═══════════════════════════════════════
# 2. Python 检测
# ═══════════════════════════════════════
PYTHON=""
NEED_PYTHON=0
if [ $IS_UPDATE -eq 0 ]; then
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then PYTHON="$p"; echo "✅ Python: $($PYTHON --version 2>&1)"; break; fi
    done
    if [ -z "$PYTHON" ]; then NEED_PYTHON=1; echo "⚠ 未找到 Python"; fi
else
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then PYTHON="$p"; break; fi
    done
    if [ -z "$PYTHON" ]; then echo "❌ 未找到 Python"; exit 1; fi
fi

# ═══════════════════════════════════════
# 2.5 用户协议（首次安装）
# ═══════════════════════════════════════
if [ $IS_UPDATE -eq 0 ]; then
    RESPONSE=$(osascript -e 'button returned of (display dialog "交付自检工具 安装协议\n\n本插件会采集公网IP地址（仅IP，非精准定位）用于防盗版验证。同一激活码在多地区使用时会被预警。\n\n不会上传任何项目文件、时间线内容或个人身份信息。\n\n点击「同意并安装」表示您已知悉并同意以上条款。" buttons {"取消", "同意并安装"} default button "同意并安装" with icon note)' 2>/dev/null || echo "取消")
    if [ "$RESPONSE" != "同意并安装" ]; then
        echo "用户未同意协议，安装终止"
        echo >&3 "  用户未同意安装协议，已取消。"
        exit 0
    fi
    echo >&3 "  已同意安装协议"
fi

# ═══════════════════════════════════════
# 3. 已有安装检测
# ═══════════════════════════════════════
if [ $IS_UPDATE -eq 0 ] && [ -d "$INSTALL_DIR" ]; then
    INSTALLED_VER="?"
    if [ -f "$INSTALL_DIR/config.py" ]; then
        INSTALLED_VER=$(grep '__version__' "$INSTALL_DIR/config.py" | head -1 | grep -o '"[^"]*"' | tr -d '"')
    fi
    NEW_VER="?"
    if [ -f "$ZIP_SRC" ]; then
        NEW_VER=$(unzip -p "$ZIP_SRC" "*/config.py" 2>/dev/null | grep '__version__' | head -1 | grep -o '"[^"]*"' | tr -d '"')
    fi
    echo "已安装: v${INSTALLED_VER} | 安装包: v${NEW_VER}"

    if [ "$INSTALLED_VER" = "$NEW_VER" ] && [ "$INSTALLED_VER" != "?" ]; then
        RESPONSE=$(osascript -e "button returned of (display dialog \"已安装相同版本（v${INSTALLED_VER}）。\n\n如果插件出现问题，可以选择重新安装。\" buttons {\"取消\", \"重新安装\"} default button \"取消\")" 2>/dev/null || echo "取消")
        if [ "$RESPONSE" != "重新安装" ]; then echo "用户取消"; exit 0; fi
    fi

    if [ "$NEW_VER" != "?" ] && [ "$INSTALLED_VER" != "?" ]; then
        LOWER=$(python3 -c "
a=tuple(int(x) for x in '$INSTALLED_VER'.split('.'))
b=tuple(int(x) for x in '$NEW_VER'.split('.'))
print('1' if a > b else '0')
" 2>/dev/null || echo 0)
        if [ "$LOWER" = "1" ]; then
            RESPONSE=$(osascript -e "button returned of (display dialog \"当前版本 v${INSTALLED_VER}，安装包版本 v${NEW_VER}。\n\n安装后将降级到旧版本。确认继续？\" buttons {\"取消\", \"降级安装\"} default button \"取消\" with icon caution)" 2>/dev/null || echo "取消")
            if [ "$RESPONSE" != "降级安装" ]; then echo "用户取消降级"; exit 0; fi
        else
            RESPONSE=$(osascript -e "button returned of (display dialog \"当前版本 v${INSTALLED_VER} → v${NEW_VER}\n\n选择「覆盖安装」将保留您的配置和词典。\" buttons {\"取消\", \"覆盖安装\"} default button \"覆盖安装\")" 2>/dev/null || echo "取消")
            if [ "$RESPONSE" != "覆盖安装" ]; then echo "用户取消"; exit 0; fi
        fi
    else
        RESPONSE=$(osascript -e $'button returned of (display dialog "检测到已有安装。\n\n选择「覆盖安装」将保留您的配置和词典。" buttons {"取消", "覆盖安装"} default button "覆盖安装")' 2>/dev/null || echo "取消")
        if [ "$RESPONSE" != "覆盖安装" ]; then echo "用户取消"; exit 0; fi
    fi
fi

# ═══════════════════════════════════════
# 4. 解压准备
# ═══════════════════════════════════════
rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
if [ $IS_UPDATE -eq 0 ]; then
    mkdir -p /tmp/_deli_temp
    if ! unzip -q "$ZIP_SRC" -d /tmp/_deli_temp 2>/dev/null; then
        osascript -e $'display dialog "安装包已损坏。\n\n请重新下载。" buttons {"好的"} default button 1 with icon stop'
        rm -rf /tmp/_deli_temp; exit 1
    fi
    if [ -d "/tmp/_deli_temp/交付自检工具" ]; then
        mv /tmp/_deli_temp/交付自检工具 /tmp/_deli_src
    else
        osascript -e $'display dialog "安装包结构异常。\n\n请重新下载。" buttons {"好的"} default button 1 with icon stop'
        rm -rf /tmp/_deli_temp; exit 1
    fi
    for f in /tmp/_deli_src/python-*-macos11.pkg; do
        [ -f "$f" ] && mv "$f" /tmp/_deli_python.pkg && break
    done
    rm -rf /tmp/_deli_temp
    echo "解压: $(find /tmp/_deli_src -type f | wc -l | tr -d ' ') files"
else
    if ! cp -r "$SOURCE" /tmp/_deli_src 2>/dev/null; then
        osascript -e $'display dialog "准备安装失败。\n请检查磁盘空间后重试。" buttons {"好的"} default button 1 with icon stop'
        exit 1
    fi
fi

# ═══════════════════════════════════════
# 5. 检测 External Scripting + 摘要（终端可见）
# ═══════════════════════════════════════

DR_CONFIG="$HOME/Library/Preferences/Blackmagic Design/DaVinci Resolve/config.dat"
DR_SCRIPTING_NEEDS_FIX=0
if [ -f "$DR_CONFIG" ] && grep -q "System.Scripting.Mode = 0" "$DR_CONFIG" 2>/dev/null; then
    DR_SCRIPTING_NEEDS_FIX=1
fi

# 终端摘要
echo >&3
echo "  将进行以下操作：" >&3
echo "    📂 安装插件" >&3
if [ $NEED_PYTHON -eq 1 ]; then
    echo "    🐍 安装 Python 3.13" >&3
fi
if [ $DR_SCRIPTING_NEEDS_FIX -eq 1 ]; then
    echo "    🔧 启用达芬奇外部脚本权限" >&3
fi
echo >&3
echo "  请在弹出的密码框中输入开机密码，确认以上操作。" >&3
echo >&3

# ═══════════════════════════════════════
# 5b. 执行安装
# ═══════════════════════════════════════
INSTALL_LOG="/tmp/_deli_install.log"

if [ $IS_UPDATE -eq 1 ]; then
    echo "→ backup full install" &&
    rm -rf /tmp/_deli_rollback &&
    cp -r "$INSTALL_DIR" /tmp/_deli_rollback || { echo "❌ 备份失败（磁盘满？）"; exit 1; } &&
    echo "→ mkdir" && mkdir -p "$FUSION_SCRIPTS" &&
    echo "→ backup .env" && [ ! -f "$INSTALL_DIR/.env" ] || (cp "$INSTALL_DIR/.env" /tmp/_deli_env_bak || { echo "❌ 备份 .env 失败"; exit 1; }) &&
    echo "→ backup dicts" && (rm -rf /tmp/_deli_dicts_bak; if [ -d "$INSTALL_DIR/dicts" ]; then cp -r "$INSTALL_DIR/dicts/" /tmp/_deli_dicts_bak/; fi) &&
    echo "→ cp new" && rm -rf "$INSTALL_DIR.new" && cp -r /tmp/_deli_src "$INSTALL_DIR.new" &&
    echo "→ rm old" && rm -rf "$INSTALL_DIR" &&
    echo "→ mv staging" && mv "$INSTALL_DIR.new" "$INSTALL_DIR" &&
    echo "→ restore dicts" && if [ -d /tmp/_deli_dicts_bak ]; then cp /tmp/_deli_dicts_bak/* "$INSTALL_DIR/dicts/" 2>/dev/null; rm -rf /tmp/_deli_dicts_bak; fi &&
    echo "→ verify" &&
    if [ -n "$PYTHON" ]; then
        $PYTHON -c "import sys; sys.path.insert(0,'$INSTALL_DIR'); sys.path.insert(0,'$INSTALL_DIR/shared'); import config; import check_core" 2>&1
    else
        false
    fi || {
        echo "❌ 更新后验证失败，回退旧版本"
        rm -rf "$INSTALL_DIR" &&
        cp -r /tmp/_deli_rollback "$INSTALL_DIR" &&
        rm -rf /tmp/_deli_rollback &&
        echo "⚠ 已恢复旧版本" >&3 &&
        osascript -e 'display dialog "更新未通过验证，已自动恢复旧版本。\n\n请稍后重试或联系微信 paladinpp" buttons {"好的"} default button 1 with icon caution' &&
        exit 1
    } &&
    rm -rf /tmp/_deli_rollback &&
    echo "→ deploy shell" && cp "$INSTALL_DIR/shell_personal.py" "$FUSION_SCRIPTS/交付自检工具.py" && chmod 755 "$FUSION_SCRIPTS/交付自检工具.py" &&
    echo "→ chown" && chown -R $USER "$INSTALL_DIR" &&
    echo "→ clean pyc" && find "$INSTALL_DIR" -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true &&
    echo "→ restore .env" && if [ -f /tmp/_deli_env_bak ]; then cp /tmp/_deli_env_bak "$INSTALL_DIR/.env"; rm -f /tmp/_deli_env_bak; else cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"; fi &&
    echo "→ write license" && "$PYTHON" "$INSTALL_DIR/shared/_write_env.py" && echo "✅ 安装完成"
    _UPDATE_OK=1
elif osascript <<EOF 2>"$INSTALL_LOG"
do shell script "
    echo '  → mkdir' >> '$INSTALL_LOG' &&
    mkdir -p '$FUSION_SCRIPTS' &&

    echo '  → python install' >> '$INSTALL_LOG' &&
    if [ -f /tmp/_deli_python.pkg ]; then
        installer -pkg /tmp/_deli_python.pkg -target / >> '$INSTALL_LOG' 2>&1 || {
            echo '  ❌ Python 安装失败' && exit 1
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
    chmod 755 '$FUSION_SCRIPTS' 2>/dev/null || true &&

    echo '  → restore .env' >> '$INSTALL_LOG' &&
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
    echo "✅ 系统安装完成"
else
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
    if grep -q "User canceled\|用户取消\|error.*-128" "$INSTALL_LOG" 2>/dev/null; then
        echo "用户取消密码输入"
        echo "  已取消" >&3
    else
        echo "❌ 安装失败 ($(tail -3 "$INSTALL_LOG" 2>/dev/null))"
        osascript -e "display dialog \"安装失败。\n\n请检查密码是否正确、磁盘是否已满。\n\n详情见: $INSTALL_LOG\" buttons {\"好的\"} default button 1 with icon stop"
    fi
    exit 1
fi
if [ "${_UPDATE_OK:-0}" -eq 1 ]; then
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
fi

# ═══════════════════════════════════════
# 5c. External Scripting 变更
# ═══════════════════════════════════════
DR_SCRIPTING_CHANGED=0
if [ $DR_SCRIPTING_NEEDS_FIX -eq 1 ]; then
    sed -i '' 's/System.Scripting.Mode = 0/System.Scripting.Mode = 1/' "$DR_CONFIG"
    DR_SCRIPTING_CHANGED=1
    echo "✅ External Scripting 已启用"
fi

# ═══════════════════════════════════════
# 6. 验证
# ═══════════════════════════════════════
PASS=1
[ -f "$FUSION_SCRIPTS/交付自检工具.py" ] || { echo "❌ 壳缺失"; PASS=0; }
[ -f "$INSTALL_DIR/ui.py" ] || { echo "❌ ui.py 缺失"; PASS=0; }
echo "shared: $(find "$INSTALL_DIR/shared" -name "*.py" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ') modules"
[ -f "$INSTALL_DIR/.env" ] || echo "⚠ .env 缺失"
# 子目录完整性
for _chk in dicts pypdf; do
    _cnt=$(find "$INSTALL_DIR/$_chk" -type f 2>/dev/null | wc -l | tr -d ' ')
    _min=5; [ "$_chk" = "pypdf" ] && _min=20
    if [ "$_cnt" -ge "$_min" ]; then
        :
    else
        echo "❌ $_chk/ 文件不全 ($_cnt < $_min)"
        PASS=0
    fi
done
# dftt_timecode
[ -f "$INSTALL_DIR/shared/dftt_timecode/core/dftt_timecode.py" ] || { echo "❌ dftt_timecode 缺失"; PASS=0; }
# .env 或 .env.example 至少一个存在
[ -f "$INSTALL_DIR/.env" ] || [ -f "$INSTALL_DIR/.env.example" ] || { echo "❌ .env 和 .env.example 均缺失"; PASS=0; }

if [ $NEED_PYTHON -eq 1 ] || [ -z "$PYTHON" ]; then
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then PYTHON="$p"; break; fi
    done
    [ -n "$PYTHON" ] || { echo "❌ Python 未安装"; PASS=0; }
fi
if [ -n "$PYTHON" ]; then
_PY_ERR=$(mktemp /tmp/_deli_verify.XXXXXX)
    $PYTHON -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
sys.path.insert(0, '$INSTALL_DIR/shared')
import config; import check_core
print(f'验证通过 v{config.version_string()}')
" >"$_PY_ERR" 2>&1
    if [ $? -ne 0 ]; then
        echo "❌ 导入失败"  # log
        cat "$_PY_ERR" >> "$LOG" 2>/dev/null  # full traceback → log
        _LAST_ERR=$(tail -1 "$_PY_ERR" 2>/dev/null | tr '\n' ' ')  # last line for UI
        _LAST_ERR=${_LAST_ERR:-未知错误}
        PASS=0
    else
        cat "$_PY_ERR" >> "$LOG" 2>/dev/null
    fi
    rm -f "$_PY_ERR"
fi

# ═══════════════════════════════════════
# 结果（终端可见）
# ═══════════════════════════════════════
if [ $PASS -eq 1 ]; then
    echo "✅ 安装完成"
    echo >&3
    echo "  ✅ 安装完成" >&3
    echo >&3
    echo "  使用方法：达芬奇 → 工作区 → 脚本 → 交付自检工具" >&3
    osascript -e $'display dialog "✅ 安装完成！\n\n使用方法：\n  工作区 → 脚本 → 交付自检工具" buttons {"好的"} default button "好的" with icon note'
else
    echo "❌ 验证失败"
    echo >&3
    echo "  ❌ 安装未通过验证" >&3
    if [ -n "${_LAST_ERR:-}" ] && [ "${_LAST_ERR}" != "未知错误" ]; then
        echo "  ${_LAST_ERR}" >&3
    fi
    echo "  如问题持续，截图终端窗口发给我（微信 paladinpp / B站 电影裁缝Bryan）" >&3
    rm -rf /tmp/_deli_src /tmp/_deli_python.pkg /tmp/_deli_temp 2>/dev/null
    osascript -e "display dialog \"安装验证未通过。${_LAST_ERR:-}\n\n如问题持续，截图终端窗口发给我（微信 paladinpp / B站 电影裁缝Bryan）\" buttons {\"好的\"} default button 1 with icon stop"
    exit 1
fi
