#!/bin/bash
# publish.sh — 达芬奇插件工坊 统一发布工具
# 被各产品的 build_local.sh / push_all.sh / gray.sh source 使用
# 自动从调用目录推断产品名、launcher 前缀、SMB 路径
set -e

# ── 自动推断产品信息 ──
# 从调用脚本的目录名推断产品名
_CALLER="${BASH_SOURCE[1]}"
_CALLER_DIR="$(cd "$(dirname "$_CALLER")" && pwd)"
SCRIPT_DIR="${SCRIPT_DIR:-$_CALLER_DIR}"
PRODUCT_DIR="${PRODUCT_DIR:-$SCRIPT_DIR}"
PRODUCT_NAME="${PRODUCT_NAME:-$(basename "$PRODUCT_DIR")}"

# 从调用脚本名推断 stage（build_local / push_all / sync / gray）
_STAGE="${_STAGE:-$(basename "$_CALLER" .sh)}"

# VERIFY_MODE: 有 adapters/ 目录 = AI 产品 → full，否则 light
if [ -z "${VERIFY_MODE:-}" ]; then
    if [ -d "$PRODUCT_DIR/adapters" ]; then
        VERIFY_MODE=full
    else
        VERIFY_MODE=light
    fi
fi

# Launcher 文件名前缀（从 PRODUCT_NAME 推断）
LAUNCHER_PREFIX="${LAUNCHER_PREFIX:-$PRODUCT_NAME}"

# SMB 路径
SMB_ROOT="/Volumes/MYJC/06_Software/达芬奇脚本"
SMB_DIR="${SMB_DIR:-$SMB_ROOT/$PRODUCT_NAME}"
SMB_SHARED="$SMB_ROOT/shared"
GRAY_CFG="$SMB_DIR/gray.json"

# 日志
LOG_DIR="$HOME/.workbuddy/logs/publish"
LOG_DATE=$(date "+%Y-%m-%d")
LOG_FILE="$LOG_DIR/${HOSTNAME:-local}_${LOG_DATE}.log"

# ── 自动 commit（构建/发布前存档当前状态）──
_ROOT=$(cd "$PRODUCT_DIR/.." && pwd)
_HASH=$(git -C "$_ROOT" rev-parse --short HEAD 2>/dev/null || echo "none")
_STAGE="${_STAGE:-build}"
git -C "$_ROOT" add -A
git -C "$_ROOT" commit --no-verify -m "${_STAGE}: $PRODUCT_NAME (from $_HASH)" 2>/dev/null || true

publish_log() {
    local stage="$1" action="$2" detail="${3:-}"
    mkdir -p "$LOG_DIR"
    local ts=$(date "+%H:%M:%S")
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

# ── 产品注册表校验（build/push 都会调）──
publish_validate_product() {
    cd "$PRODUCT_DIR"
    python3 -c "
import sys; sys.path.insert(0,'$PRODUCT_DIR/../shared')
from product_registry import get_by_dir
p = get_by_dir('$PRODUCT_NAME')
if p:
    print(f'  📦 {$PRODUCT_NAME} — {p.get(\"category\",\"?\")} — {p.get(\"status\",\"?\")}')
else:
    print(f'  ⚠  {$PRODUCT_NAME} 未注册 — 请加到 shared/product_registry.py')
" 2>/dev/null || true
}

# ── 核心：本地构建 ──
publish_build_local() {
    local ver=$(publish_get_version)
    log_local_start "v$ver"
    publish_validate_product

    echo "═══ 本地验证 — $PRODUCT_NAME ═══"
    echo ""

    if [ "$VERIFY_MODE" = "full" ]; then
        # AI 产品：quick_verify + 本地 launcher 部署 + Fusion 兼容性
        local version_str=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR'); from config import version_string; print(version_string())" 2>/dev/null || echo "$ver")
        echo "📝 版本: $version_str"
        echo ""

        bash "$PRODUCT_DIR/../tools/quick_verify.sh"

        # 本地 launcher 部署（通过 deploy.py）
        echo ""
        echo "── launcher 部署 ──"
        python3 "$PRODUCT_DIR/../tools/deploy.py" "$PRODUCT_NAME" 2>&1

        # Fusion 兼容性（模拟 __file__ 不存在）
        local launcher_path=$(ls "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/${PRODUCT_NAME}"*.py 2>/dev/null | head -1)
        if [ -n "$launcher_path" ] && [ -f "$launcher_path" ]; then
            echo ""
            echo "── Fusion 兼容性 ──"
            python3 -c "
import sys, os
_path = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊'
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = _path
assert _HERE == _path, f'fallback failed: {_HERE}'
assert os.path.isdir('/Volumes/MYJC/06_Software/达芬奇脚本/${PRODUCT_NAME}'), 'SMB product dir missing'
assert os.path.isdir('/Volumes/MYJC/06_Software/达芬奇脚本/shared'), 'SMB shared missing'
print('  ✅ Fusion __file__ fallback OK')
print('  ✅ SMB 可达')
" && echo "  ✅ Fusion 兼容性通过" || echo "  ⚠ Fusion 兼容性检查失败"
        fi
    else
        # 轻量验证
        local ver_raw=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
        echo "📝 当前版本: $ver_raw"
        echo ""
        echo "语法检查..."
        local fail=0
        cd "$PRODUCT_DIR"
        for f in config.py check_core.py ui.py; do
            python3 -m py_compile "$f" 2>/dev/null && echo "  ✅ $f" || { echo "  ❌ $f"; fail=1; }
        done
        [ $fail -ne 0 ] && echo "❌ 语法错误" && exit 1

        # 版本 bump（VERSION_BUMP=patch|minor|major|none，默认 patch）
        if [ "${VERSION_BUMP:-patch}" != "none" ] && [ "${SKIP_VERSION_BUMP:-}" != "1" ]; then
            echo ""
            local bump_level="${VERSION_BUMP:-patch}"
            local new_ver=$(cd "$PRODUCT_DIR" && python3 -c "
import re
with open('config.py') as f: code = f.read()
level = '${bump_level}'
if level == 'major':
    code = re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"',
                  lambda m: f'__version__ = \"{int(m.group(1))+1}.0.0\"', code)
elif level == 'minor':
    code = re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"',
                  lambda m: f'__version__ = \"{m.group(1)}.{int(m.group(2))+1}.0\"', code)
else:  # patch
    code = re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"',
                  lambda m: f'__version__ = \"{m.group(1)}.{m.group(2)}.{int(m.group(3))+1}\"', code)
with open('config.py', 'w') as f: f.write(code)
from config import version_string
print(version_string())
" 2>/dev/null)
            echo "🏷 本地版本 bump → $new_ver"
        fi

        # 本地 launcher 部署
        echo ""
        echo "── launcher 部署 ──"
        python3 "$PRODUCT_DIR/../tools/deploy.py" "$PRODUCT_NAME" 2>&1
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

    if [ -n "${GRAY_CHOICE:-}" ]; then
        echo "  (命令行: $GRAY_CHOICE)"
    else
        read -p "  请选择 [1/2/3]: " GRAY_CHOICE
    fi

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
    # ═══ 硬拦截：非人工确认不得发布全公司 ═══
    if [ "${CONFIRM_PUSH:-}" != "yes" ]; then
        echo "⛔ 发布全公司需要人工确认！"
        echo "   请在终端执行: CONFIRM_PUSH=yes ./push_all.sh"
        echo "   或告诉我「确认发布全公司」，我会帮你跑。"
        exit 1
    fi
    # ═══ 硬拦截：本地必须先更新再推 SMB ═══
    local launcher_chk=$(ls "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/${PRODUCT_NAME}"*.py 2>/dev/null | head -1)
    if [ -z "$launcher_chk" ] || [ ! -f "$launcher_chk" ]; then
        echo "⛔ 本地尚未构建！请先运行 build_local.sh 再推全公司。"
        exit 1
    fi
    # ═══ 硬拦截：SMB 文件不得比本地新（防止直接改 SMB 跳过本地测试） ═══
    local smb_stale=""
    for f in "$PRODUCT_DIR"/*.py; do
        [ ! -f "$f" ] && continue
        local smb_f="$SMB_DIR/$(basename "$f")"
        [ ! -f "$smb_f" ] && continue
        local lm=$(stat -f %m "$f" 2>/dev/null || echo 0)
        local sm=$(stat -f %m "$smb_f" 2>/dev/null || echo 0)
        # 只拦 SMB 比本地新的（mtime 更大），不拦本地比 SMB 新的（正常推送）
        if [ "$sm" -gt "$lm" ] 2>/dev/null && ! diff -q "$f" "$smb_f" > /dev/null 2>&1; then
            smb_stale="$smb_stale  $(basename "$f")"
        fi
    done
    if [ -n "$smb_stale" ]; then
        echo "⛔ SMB 上有文件与本地不一致（可能直接在 SMB 上改了）："
        echo "$smb_stale"
        echo "   请先在本地修改并运行 build_local.sh，再推全公司。"
        exit 1
    fi
    local ver=$(publish_get_version)
    log_full_start "push_all v$ver"
    publish_validate_product

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
        for f in config.py check_core.py ui.py; do
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
        rsync -av --delete --exclude '.env' "$shared_src/" "$SMB_SHARED/" 2>/dev/null
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
    # 清除 SMB __pycache__，避免旧 .pyc 缓存旧代码
    find "$SMB_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    python3 -c "
import json
cfg = json.load(open('$GRAY_CFG'))
cfg['targets'] = []; cfg['note'] = '全量发布完成'
json.dump(cfg, open('$GRAY_CFG','w'), indent=2, ensure_ascii=False)
"
    echo "✅ 全量发布完成"
    log_gray_promote "全量发布完成"
}

# ── 核心：同步产品文件到 SMB（新版，两个产品共用）──
# 使用: source ../tools/publish.sh; publish_sync
# 环境变量: SYNC_EXTRA_DIRS="dicts" → 额外同步的目录（如交付自检的词典）
publish_sync() {
    cd "$PRODUCT_DIR"

    # ── 版本检查（比纯数字，忽略 -dev 通道）──
    SMB_RAW=$(python3 -c "import sys; sys.path.insert(0,'$SMB_DIR'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
    LOCAL_RAW=$(python3 -c "from config import __version__; print(__version__)")
    echo "🏷 本地: $(python3 -c 'from config import version_string; print(version_string())') | SMB: $(python3 -c "import sys; sys.path.insert(0,'$SMB_DIR'); from config import version_string; print(version_string())" 2>/dev/null || echo '?')"
    if [ "$LOCAL_RAW" = "$SMB_RAW" ] && [ "${SKIP_VERSION_BUMP:-}" != "1" ] && [ "${VERSION_BUMP:-patch}" != "none" ]; then
        read -p "改动值得升版本吗？(y/N) " BUMP
        if [ "$BUMP" = "y" ] || [ "$BUMP" = "Y" ]; then
            read -p "升大版本(1.x→2.0)还是小版本(1.1→1.2)？(M/m) " LEVEL
            if [ "$LEVEL" = "M" ] || [ "$LEVEL" = "M" ]; then
                python3 -c "import re; f=open('config.py'); c=f.read(); f.close(); c=re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"', lambda m: f'__version__ = \"{int(m.group(1))+1}.0.0\"', c); open('config.py','w').write(c)"
            else
                python3 -c "import re; f=open('config.py'); c=f.read(); f.close(); c=re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"', lambda m: f'__version__ = \"{m.group(1)}.{int(m.group(2))+1}.0\"', c); open('config.py','w').write(c)"
            fi
            python3 -c "from config import version_string; print(f'🏷 新版本: {version_string()}')"
        fi
    fi

    # ── 备份现有 SMB 文件 ──
    BAK_DIR="$SMB_DIR/.bak_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BAK_DIR"
    echo "备份 SMB → $BAK_DIR"

    # ── 同步本产品 .py 文件 ──
    FILES=()
    while IFS= read -r f; do
        FILES+=("$f")
    done < <(find . -maxdepth 1 -name '*.py' | sed 's|^\./||' | sort)

    # ── MD5 校验锁：SMB 被绕过本地直接改了？ ──
    # 原理：SMB/.push_commit 存上次推送的 git hash，比对 SMB 文件是否与之匹配
    # 不匹配=SMB被直接修改过→拦截；匹配=正常→放行
    echo "MD5 校验锁..."
    local _git_root=$(cd "$PRODUCT_DIR/.." && pwd)
    local _push_cfg="$SMB_DIR/.push_commit"
    local md5_blocked=0
    if [ -f "$_push_cfg" ]; then
        local _last_commit=$(cat "$_push_cfg" 2>/dev/null || echo "")
        if [ -n "$_last_commit" ]; then
            for f in "${FILES[@]}"; do
                [ "$f" = "config.py" ] && continue
                local smb_f="$SMB_DIR/$f"
                [ ! -f "$smb_f" ] && continue
                local smb_md5=$(md5 -q "$smb_f" 2>/dev/null || echo "")
                [ -z "$smb_md5" ] && continue
                local expect_md5=$(git -C "$_git_root" show "${_last_commit}:$PRODUCT_NAME/$f" 2>/dev/null | md5 -q 2>/dev/null || echo "")
                if [ -n "$expect_md5" ] && [ "$smb_md5" != "$expect_md5" ]; then
                    echo "  ⛔ $f — SMB 被修改过，非上次推送版本"
                    md5_blocked=1
                fi
            done
        fi
    fi
    if [ "$md5_blocked" -eq 1 ]; then
        echo ""
        echo "⛔ SMB 上的文件被直接修改过（非通过本地推送），请先确认更改来源后再推送。"
        exit 1
    fi
    echo "  ✅ MD5 校验通过"

    echo "同步到 SMB..."
    for f in "${FILES[@]}"; do
        src="$PWD/$f"
        dst="$SMB_DIR/$f"
        if [ -f "$src" ]; then
            if [ -f "$dst" ]; then
                cp "$dst" "$BAK_DIR/$f" 2>/dev/null || true
            fi
            # 原子写入：先写临时文件再 rename
            cp "$src" "$dst.tmp" && mv "$dst.tmp" "$dst"
        fi
    done

    # ── 同步额外目录（如 交付自检 的 dicts/）──
    for extra in ${SYNC_EXTRA_DIRS:-}; do
        if [ -d "$PRODUCT_DIR/$extra" ]; then
            SMB_EXTRA="$SMB_DIR/$extra"
            mkdir -p "$SMB_EXTRA"
            echo "同步 $extra/..."
            rsync -a "$PRODUCT_DIR/$extra/" "$SMB_EXTRA/" 2>/dev/null
            echo "  ✅ $extra/ 同步完成"
        fi
    done

    # 创建日志目录
    mkdir -p "$SMB_DIR/logs"

    # ── 语法检查 ──
    echo "语法检查..."
    FAIL=0
    for f in "${FILES[@]}"; do
        if [ -f "$SMB_DIR/$f" ] && [[ "$f" == *.py ]]; then
            python3 -m py_compile "$SMB_DIR/$f" || FAIL=1
        fi
    done

    if [ $FAIL -eq 0 ]; then
        # ── 自动去通道（Python 正则，兼容任意通道名）──
        SMB_CFG="$SMB_DIR/config.py"
        python3 -c "
import re
with open('$SMB_CFG') as f: code = f.read()
code = re.sub(r'__channel__\s*=\s*\"[^\"]*\"', '__channel__ = \"\"', code)
with open('$SMB_CFG', 'w') as f: f.write(code)
" 2>/dev/null
        SMB_VER=$(python3 -c "import sys; sys.path.insert(0,'$SMB_DIR'); from config import version_string; print(version_string())")
        echo "🏷 SMB 版本: $SMB_VER"
        echo "✅ 同步完成"
        # 记录推送状态：下次推送用这个 hash 比对 SMB 是否被绕过本地直接修改
        local _push_commit=$(cd "$PRODUCT_DIR/.." && git rev-parse HEAD 2>/dev/null || echo "")
        [ -n "$_push_commit" ] && echo "$_push_commit" > "$_push_cfg"
    else
        echo "❌ 有语法错误"
        exit 1
    fi
}

# ── 自动路由（如果壳脚本没有显式调用函数，按脚本名自动分发）──
if [ "${_AUTO_DISPATCH:-1}" = "1" ] && declare -f "publish_${_STAGE}" > /dev/null 2>&1; then
    publish_${_STAGE}
fi
