#!/bin/bash
# publish.sh — 达芬奇插件工坊 统一发布工具
# 被各产品的 build_local.sh / push_all.sh / gray.sh source 使用
# 自动从调用目录推断产品名、launcher 前缀、SMB 路径
set -e

# ── 自动推断产品信息 ──
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)}"
PRODUCT_DIR="${PRODUCT_DIR:-$SCRIPT_DIR}"
PRODUCT_NAME="${PRODUCT_NAME:-$(basename "$PRODUCT_DIR")}"
VERIFY_MODE="${VERIFY_MODE:-full}"  # full=AI产品 / light=自检工具

# Launcher 文件名前缀（从 PRODUCT_NAME 推断）
LAUNCHER_PREFIX="${LAUNCHER_PREFIX:-$PRODUCT_NAME}"

# SMB 路径
SMB_ROOT="/Volumes/MYJC/06_Software/达芬奇脚本"
SMB_DIR="${SMB_DIR:-$SMB_ROOT/$PRODUCT_NAME}"
SMB_SHARED="$SMB_ROOT/shared"
GRAY_CFG="$SMB_DIR/gray.json"

# 日志
LOG_DIR="$HOME/WorkBuddy/达芬奇插件工坊/logs"
LOG_FILE="$LOG_DIR/publish.log"

publish_log() {
    local stage="$1" action="$2" detail="${3:-}"
    mkdir -p "$LOG_DIR"
    local ts=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
    echo "[$ts] [$stage] [$action] [$PRODUCT_NAME] ${detail}" >> "$LOG_FILE"
}

log_local_start()     { publish_log "local"  "start"  "$*"; }
log_local_done()      { publish_log "local"  "done"   "$*"; }
log_gray_start()      { publish_log "gray"   "start"  "$*"; }
log_gray_done()       { publish_log "gray"   "done"   "$*"; }
log_gray_add()        { publish_log "gray"   "add"    "$*"; }
log_gray_remove()     { publish_log "gray"   "remove" "$*"; }
log_gray_promote()    { publish_log "gray"   "promote" "$*"; }
log_full_start()      { publish_log "full"   "start"  "$*"; }
log_full_done()       { publish_log "full"   "done"   "$*"; }
log_full_skip_gray()  { publish_log "full"   "skip_gray" "$*"; }
log_gray_confirm()    { publish_log "full"   "gray_confirmed" "$*"; }

# ── 核心：本地构建 ──
publish_build_local() {
    local ver=$(publish_get_version)
    log_local_start "v$ver"

    echo "═══ 本地验证 — $PRODUCT_NAME ═══"
    echo ""

    if [ "$VERIFY_MODE" = "full" ]; then
        # AI 产品：launcher 命名 + 版本号冲突检测 + quick_verify
        local launcher_dir="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/本地版"
        local version_str=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR'); from config import version_string; print(version_string())" 2>/dev/null || echo "$ver")

        # 版本号冲突检测
        local company_launcher=$(ls "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/公司版"/${LAUNCHER_PREFIX}_*.py 2>/dev/null | head -1)
        if [ -n "$company_launcher" ]; then
            local company_ver=$(basename "$company_launcher" | sed "s/${LAUNCHER_PREFIX}_v//" | sed 's/\.py$//')
            if [ "$ver" = "$company_ver" ]; then
                echo "WARNING: local version ($ver) == company version ($company_ver)"
                echo "  New dev cycle? Bump version first."
                echo ""
            fi
        fi

        # Launcher 自动命名
        if [ -d "$launcher_dir" ]; then
            local current=$(ls "$launcher_dir"/${LAUNCHER_PREFIX}_*.py 2>/dev/null | head -1)
            local expected="$launcher_dir/${LAUNCHER_PREFIX}_v$version_str.py"
            if [ "$current" != "$expected" ] && [ -n "$current" ]; then
                mv "$current" "$expected"
                echo "📝 launcher: $(basename "$current") → $(basename "$expected")"
            fi
        fi

        bash "$PRODUCT_DIR/../tools/quick_verify.sh"
    else
        # 轻量验证
        local ver_raw=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
        echo "📝 当前版本: $ver_raw"
        echo ""
        echo "语法检查..."
        local fail=0
        cd "$PRODUCT_DIR"
        for f in config.py check_core.py check.py ui.py; do
            python3 -m py_compile "$f" 2>/dev/null && echo "  ✅ $f" || { echo "  ❌ $f"; fail=1; }
        done
        [ $fail -ne 0 ] && echo "❌ 语法错误" && exit 1
    fi

    echo ""
    echo "════════════════════"
    echo "✅ 本地验证完成（未同步 SMB）"
    log_local_done "v$ver"
    echo "   确认没问题后运行 ./push_all.sh 推送到全公司"
}

# ── 核心：灰度检查（阻塞式交互）──
publish_gray_check() {
    echo ""
    echo "╌╌╌ 灰度检查 ╌╌╌"
    echo "  ⚠️  发布全公司之前，必须完成灰度测试！"
    echo ""
    echo "  选项:"
    echo "    [1] 已灰度测试通过 — 继续发布"
    echo "    [2] 跳过灰度检查 — 强制发布（有记录）"
    echo "    [3] 取消 — 去灰度测试后再回来"
    echo ""
    read -p "  请选择 [1/2/3]: " GRAY_CHOICE

    case "$GRAY_CHOICE" in
        1)
            echo "  ✅ 灰度测试已确认"
            GRAY_LOG_RESULT="已灰度确认"
            log_gray_confirm "$GRAY_LOG_RESULT"
            ;;
        2)
            echo "  ⚠️  跳过灰度 — 已记录，继续发布"
            GRAY_LOG_RESULT="跳过灰度"
            log_full_skip_gray "$GRAY_LOG_RESULT"
            ;;
        *)
            echo "  ❌ 已取消 — 请先完成灰度测试"
            log_full_done "用户取消（未灰度）"
            exit 1
            ;;
    esac
}

# ── 核心：推送到 SMB ──
publish_push_all() {
    local ver=$(publish_get_version)
    log_full_start "push_all v$ver"

    # 1. 验证
    echo "═══ 推送到全公司 — $PRODUCT_NAME ═══"
    echo ""
    echo "第 1 步: 语法验证..."

    if [ "$VERIFY_MODE" = "full" ]; then
        cd "$PRODUCT_DIR"
        bash ../tools/quick_verify.sh

        # SMB 安全提醒
        echo ""
        echo "═══ SMB 安全 ═══"
        local danger=0
        for hf in ~/.zsh_history ~/.bash_history; do
            [ ! -f "$hf" ] && continue
            local d=$(LC_ALL=C tail -200 "$hf" 2>/dev/null | LC_ALL=C sed 's/^: [0-9]*:0;//' | LC_ALL=C grep -iE 'find.*/(MYJC|Volumes)[[:space:]]|grep[[:space:]].*-r.*MYJC|find[[:space:]]+/Volumes' | tail -3 || true)
            if [ -n "$d" ]; then danger=1; fi
        done
        [ $danger -eq 1 ] && echo "  🚫 警告：shell 历史中检测到 SMB 根目录搜索！" || echo "  ✅ 最近无危险 SMB 搜索"

        # 高危硬编码扫描
        echo ""
        echo "═══ 高危硬编码 ═══"
        local risk=0
        cd "$PRODUCT_DIR"
        for f in adapters/*.py core.py config.py ui_pipeline.py; do
            [ ! -f "$f" ] && continue
            if grep -q 'vid_h \* [0-9]' "$f" 2>/dev/null | grep -qv 'y_top\|_compute_selarea'; then
                echo "  ⚠️  $f — 硬编码 'vid_h * 数字'"; risk=1
            fi
        done
        [ $risk -eq 0 ] && echo "  ✅ 未发现高危硬编码"

        # SMB 脏检
        echo ""
        echo "═══ SMB 脏检 ═══"
        local dirty=0
        cd "$PRODUCT_DIR"
        while IFS= read -r f; do
            [ ! -f "$f" ] && continue
            local smb_f="$SMB_DIR/$f"
            [ ! -f "$smb_f" ] && continue
            local lm=$(stat -f %m "$f" 2>/dev/null || echo 0)
            local sm=$(stat -f %m "$smb_f" 2>/dev/null || echo 0)
            if [ "$sm" -gt "$lm" ] 2>/dev/null; then
                if ! diff "$f" "$smb_f" > /dev/null 2>&1; then
                    echo "  ⚠️  $f — SMB 比本地新！"; dirty=1
                fi
            fi
        done < <(find . -maxdepth 2 -name '*.py' -not -path './tests/*' | sed 's|^\./||' | sort)
        [ $dirty -eq 0 ] && echo "  ✅ SMB 无脏数据"
    else
        cd "$PRODUCT_DIR"
        local fail=0
        for f in config.py check_core.py check.py ui.py; do
            python3 -m py_compile "$f" 2>/dev/null && echo "  ✅ $f" || { echo "  ❌ $f"; fail=1; }
        done
        [ $fail -ne 0 ] && echo "❌ 语法错误" && exit 1
    fi

    # 2. 灰度检查
    publish_gray_check

    # 3. 同步 shared/
    echo ""
    echo "第 2 步: 同步 shared/ 到 SMB..."
    local shared_src="$(cd "$PRODUCT_DIR/../shared" && pwd)"
    if [ -d "$SMB_SHARED" ]; then
        rsync -av --delete "$shared_src/" "$SMB_SHARED/" 2>/dev/null
        echo "  ✅ shared/ 同步完成"
    else
        echo "  ⚠ SMB 未挂载, shared/ 跳过"
    fi

    # 4. 同步产品文件
    echo ""
    echo "第 3 步: 同步 $PRODUCT_NAME 到 SMB..."

    # 去 channel（仅 AI 产品）
    if [ "$VERIFY_MODE" = "full" ]; then
        cd "$PRODUCT_DIR"
        local channel=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import __channel__; print(__channel__)" 2>/dev/null || echo "")
        if [ -n "$channel" ]; then
            echo "  去 channel: $channel → (空)"
            sed -i '' 's/^__channel__ = ".*"/__channel__ = ""/' config.py
            WAS_CHANNEL="$channel"
        fi
    fi

    bash "$PRODUCT_DIR/sync.sh"

    # 自动更新 gray.json：灰度目录指向当前稳定版
    if [ -f "$GRAY_CFG" ]; then
        local ver=$(publish_get_version)
        python3 -c "
import json
cfg = json.load(open('$GRAY_CFG'))
cfg['version'] = '$ver'
cfg['gray_dir'] = '$PRODUCT_NAME'
json.dump(cfg, open('$GRAY_CFG','w'), indent=2, ensure_ascii=False)
print(f'  gray.json → v$ver')
" 2>/dev/null || true
    fi

    # 恢复 channel
    if [ -n "${WAS_CHANNEL:-}" ]; then
        cd "$PRODUCT_DIR"
        sed -i '' "s/^__channel__ = \"\"/__channel__ = \"$WAS_CHANNEL\"/" config.py
        echo "  恢复 channel: $WAS_CHANNEL"
    fi

    # 5. diff 检查
    if [ "$VERIFY_MODE" = "full" ]; then
        echo ""
        echo "═══ diff 检查 ═══"
        cd "$PRODUCT_DIR"
        while IFS= read -r f; do
            [ ! -f "$f" ] && continue
            local smb_f="$SMB_DIR/$f"
            if [ -f "$smb_f" ]; then
                diff "$f" "$smb_f" > /dev/null 2>&1 && echo "  ✅ $f" || echo "  ❌ $f (本地≠SMB)"
            fi
        done < <(find . -maxdepth 2 -name '*.py' -not -path './tests/*' | sed 's|^\./||' | sort)
    fi

    echo ""
    echo "════════════════════"
    echo "✅ push_all.sh 完成"
    log_full_done "v$ver, ${GRAY_LOG_RESULT:-未记录}"
}

# ── 辅助 ──
publish_get_version() {
    cd "$PRODUCT_DIR"
    python3 -c "import sys; sys.path.insert(0,'.'); from config import __version__; print(__version__)" 2>/dev/null || echo "?"
}

# ── 灰度管理 ──
publish_gray_status() {
    echo "═══════════════════════════════"
    echo "  灰度发布状态 — $PRODUCT_NAME"
    echo "═══════════════════════════════"
    if [ ! -f "$GRAY_CFG" ]; then
        echo "  gray.json 不存在 — 无灰度配置"
        return
    fi
    python3 -c "
import json, os
cfg = json.load(open('$GRAY_CFG'))
print(f'  灰度版本: {cfg[\"version\"]}')
print(f'  灰度目录: {cfg[\"gray_dir\"]}')
targets = cfg.get('targets', [])
print(f'  灰度机器: {targets if targets else \"(无 — 全员稳定版)\"}')
"
}

publish_gray_add() {
    [ $# -eq 0 ] && echo "用法: gray.sh add <id> [id...]" && exit 1
    python3 -c "
import json, sys
cfg = json.load(open('$GRAY_CFG'))
targets = set(cfg.get('targets',[]))
new = set(a for a in sys.argv[1:] if a != '--')
added = new - targets; targets |= new
cfg['targets'] = sorted(targets)
json.dump(cfg, open('$GRAY_CFG','w'), indent=2, ensure_ascii=False)
print(f'✅ 已加入灰度: {sorted(added)}')
print(f'   当前: {cfg[\"targets\"]}')
" -- "$@"
    log_gray_add "targets=$*"
}

publish_gray_remove() {
    [ $# -eq 0 ] && echo "用法: gray.sh remove <id> [id...]" && exit 1
    python3 -c "
import json, sys
cfg = json.load(open('$GRAY_CFG'))
targets = set(cfg.get('targets',[]))
remove = set(a for a in sys.argv[1:] if a != '--')
removed = targets & remove; targets -= remove
cfg['targets'] = sorted(targets)
json.dump(cfg, open('$GRAY_CFG','w'), indent=2, ensure_ascii=False)
print(f'✅ 已移出灰度: {sorted(removed)}')
print(f'   当前: {cfg[\"targets\"]}')
" -- "$@"
    log_gray_remove "targets=$*"
}

publish_gray_promote() {
    echo "⚠️  全量发布：灰度版本 → 稳定版"
    local gray_dir=$(python3 -c "import json; print(json.load(open('$GRAY_CFG'))['gray_dir'])")
    local gray_path="$SMB_ROOT/$gray_dir"
    [ ! -d "$gray_path" ] && echo "❌ 灰度目录不存在: $gray_path" && exit 1
    echo "  灰度: $gray_path"
    echo "  稳定: $SMB_DIR"
    read -p "  确认覆盖？输入 yes: " confirm
    [ "$confirm" != "yes" ] && echo "已取消" && exit 0
    find "$SMB_DIR" -name "*.py" -maxdepth 1 -delete 2>/dev/null || true
    cp "$gray_path"/*.py "$SMB_DIR/" 2>/dev/null
    [ -d "$gray_path/adapters" ] && cp "$gray_path/adapters"/*.py "$SMB_DIR/adapters/" 2>/dev/null || true
    python3 -c "
import json
cfg = json.load(open('$GRAY_CFG'))
cfg['targets'] = []; cfg['note'] = '全量发布完成'
json.dump(cfg, open('$GRAY_CFG','w'), indent=2, ensure_ascii=False)
"
    echo "✅ 全量发布完成"
    log_gray_promote "全量发布完成"
}
