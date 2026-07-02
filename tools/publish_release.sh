#!/bin/bash
# publish_release.sh — 发布新版本到 GitHub，支持多产品
# 用法:
#   bash tools/publish_release.sh 2.5.13 "更新日志"                                    # delivery_checker（默认）
#   bash tools/publish_release.sh --product batch_renamer 3.7.0 "更新日志"              # 批量命名工具
set -e

REPO_OWNER="cgjpaladin"
REPO_NAME="davinci-plugins"
CDN_BASE="https://cdn.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main"
API_BASE="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}"
RAW_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main"
PURGE_BASE="https://purge.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main"

# ── 参数解析 ──
PRODUCT="delivery_checker"
while [[ "$1" == --* ]]; do
    case "$1" in
        --product) PRODUCT="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

VERSION="${1:?用法: bash tools/publish_release.sh [--product <name>] <版本号> <更新日志>}"
NOTES="${2:-修复与优化}"

WS="$(cd "$(dirname "$0")/.." && pwd)"

# ── 产品注册表 ──
declare -A PRODUCT_DIR
PRODUCT_DIR["delivery_checker"]="$WS/交付自检工具"
PRODUCT_DIR["batch_renamer"]="$WS/批量命名工具"

PRODUCT_DIR_RESOLVED="${PRODUCT_DIR[$PRODUCT]}"
if [ -z "$PRODUCT_DIR_RESOLVED" ]; then
    echo "❌ 未知产品: $PRODUCT（已知: ${!PRODUCT_DIR[@]}）"
    exit 1
fi

# ── 产品特定配置 ──
# 每个产品定义自己的 zip 列表 + version.json key 列表
declare -A ZIP_FILES  # key=本地路径, value=GitHub 文件名
declare -a ZIP_NAMES  # 用于 CDN purge
declare -a PRODUCT_KEYS  # version.json 中的 key

case "$PRODUCT" in
    delivery_checker)
        ZIP_FILES["$HOME/Desktop/交付自检工具_更新包.zip"]="update_latest.zip"
        ZIP_NAMES=("update_latest.zip")
        PRODUCT_KEYS=("delivery_checker")
        # 版本校验
        VERSION_SRC="$PRODUCT_DIR_RESOLVED/config.py"
        CHANNEL_CHK=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR_RESOLVED'); from config import __channel__; print(__channel__)" 2>/dev/null || echo "")
        CONFIG_VER=$(python3 -c "import sys; sys.path.insert(0,'$PRODUCT_DIR_RESOLVED'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
        if [ -n "$CHANNEL_CHK" ]; then
            echo "⛔ dev 环境（__channel__='$CHANNEL_CHK'），禁止发布！"
            echo "   请先运行 cd $PRODUCT_DIR_RESOLVED && ./channel.sh prod。"
            exit 1
        fi
        ;;
    batch_renamer)
        ZIP_FILES["$HOME/Desktop/batch_renamer_mac.zip"]="batch_renamer_mac.zip"
        ZIP_FILES["$HOME/Desktop/batch_renamer_win.zip"]="batch_renamer_win.zip"
        ZIP_NAMES=("batch_renamer_mac.zip" "batch_renamer_win.zip")
        PRODUCT_KEYS=("batch_renamer_mac" "batch_renamer_win")
        # 版本校验：读 app_table.js
        VERSION_SRC="$PRODUCT_DIR_RESOLVED/app_table.js"
        CONFIG_VER=$(python3 -c "
import re
with open('$VERSION_SRC') as f:
    m = re.search(r\"const APP_VERSION='([^']+)'\", f.read())
    print(m.group(1) if m else '?')
" 2>/dev/null || echo "?")
        ;;
esac

# ═══ 版本号校验 ═══
if [ "$VERSION" != "$CONFIG_VER" ]; then
    echo "❌ 版本号不一致！参数=$VERSION  源码=$VERSION_SRC:$CONFIG_VER"
    exit 1
fi

# ═══ 文件存在性检查 ═══
for LOCAL_PATH in "${!ZIP_FILES[@]}"; do
    if [ ! -f "$LOCAL_PATH" ]; then
        echo "❌ 找不到 $LOCAL_PATH"
        exit 1
    fi
done

echo "═══ 发布 $PRODUCT v$VERSION ═══"

# ═══ 1. 上传 zip 文件到 GitHub ═══
declare -A ZIP_SHA256
for LOCAL_PATH in "${!ZIP_FILES[@]}"; do
    GH_NAME="${ZIP_FILES[$LOCAL_PATH]}"
    SHA256=$(shasum -a 256 "$LOCAL_PATH" | awk '{print $1}')
    ZIP_SHA256["$GH_NAME"]="$SHA256"
    echo "  📦 $GH_NAME  SHA256=$SHA256"
    echo "  → 上传 $GH_NAME ..."

    CURRENT_SHA=$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/$GH_NAME" --jq .sha 2>/dev/null || true)
    if [ -n "$CURRENT_SHA" ]; then
        gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/$GH_NAME" \
            -f message="release $PRODUCT v$VERSION" \
            -f content="$(base64 -i "$LOCAL_PATH")" \
            -f sha="$CURRENT_SHA" \
            -f branch=main || { echo "❌ $GH_NAME 上传失败"; exit 1; }
    else
        gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/$GH_NAME" \
            -f message="release $PRODUCT v$VERSION" \
            -f content="$(base64 -i "$LOCAL_PATH")" \
            -f branch=main || { echo "❌ $GH_NAME 上传失败"; exit 1; }
    fi
    echo "  ✅ $GH_NAME"
done

# ═══ 2. 更新 version.json（合并模式——不抹掉其他产品） ═══
python3 -c "
import json

# 读当前线上 version.json
try:
    with open('$WS/version.json') as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}

# 产品映射：每个 product_key 对应一个 zip 文件
# delivery_checker: {delivery_checker: update_latest.zip}
# batch_renamer: {batch_renamer_mac: batch_renamer_mac.zip, batch_renamer_win: batch_renamer_win.zip}
product_map = {}
for local_path, gh_name in ${ZIP_SHA256@Q}.items():
    # local_path → gh_name 已在 ZIP_FILES 中，从 ZIP_SHA256 反查
    pass

# 手动构建——比动态推断更可靠
if '$PRODUCT' == 'batch_renamer':
    mac_sha = '${ZIP_SHA256[batch_renamer_mac.zip]}'
    win_sha = '${ZIP_SHA256[batch_renamer_win.zip]}'
    
    for pk in ['batch_renamer_mac', 'batch_renamer_win']:
        old_cfg = data.get(pk, {})
        history = old_cfg.get('history', [])
        history.append({'version': '$VERSION', 'notes': '$NOTES'})
        data[pk] = {
            'version': '$VERSION',
            'urls': [
                f'https://cdn.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main/${pk}.zip',
                f'https://ghproxy.net/https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/${pk}.zip',
                f'https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/${pk}.zip',
            ],
            'sha256': mac_sha if pk == 'batch_renamer_mac' else win_sha,
            'notes': '$NOTES',
            'history': history,
        }
elif '$PRODUCT' == 'delivery_checker':
    sha = '${ZIP_SHA256[update_latest.zip]}'
    old_cfg = data.get('delivery_checker', {})
    history = old_cfg.get('history', [])
    history.append({'version': '$VERSION', 'notes': '$NOTES'})
    data['delivery_checker'] = {
        'version': '$VERSION',
        'urls': [
            f'https://cdn.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main/update_latest.zip',
            f'https://ghproxy.net/https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/update_latest.zip',
            f'https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/update_latest.zip',
        ],
        'sha256': sha,
        'notes': '$NOTES',
        'history': history,
    }

with open('/tmp/_publish_v.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"

# 写入本地 repo + 上传
cp /tmp/_publish_v.json "$WS/version.json"

echo "  → 上传 version.json..."
gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" \
    -f message="release $PRODUCT v$VERSION" \
    -f content="$(base64 -i /tmp/_publish_v.json)" \
    -f sha="$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" --jq .sha)" \
    -f branch=main --silent
echo "  ✅ version.json"

# ═══ 3. 刷新 CDN 缓存 ═══
echo "  → 刷新 jsDelivr 缓存..."
PURGE_V=$(curl -s -o /dev/null -w "%{http_code}" "${PURGE_BASE}/version.json")
echo "  CDN version.json (HTTP $PURGE_V)"
for ZN in "${ZIP_NAMES[@]}"; do
    PZ=$(curl -s -o /dev/null -w "%{http_code}" "${PURGE_BASE}/${ZN}")
    echo "  CDN ${ZN} (HTTP $PZ)"
done

echo "═══ $PRODUCT v$VERSION 发布完成 ═══"
echo "用户下次启动自动检测更新。"
