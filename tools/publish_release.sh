#!/bin/bash
# publish_release.sh — 发布新版本到 GitHub
# 用法: bash tools/publish_release.sh 2.2.2 "修复xxx + 新增yyy"
set -e

REPO_OWNER="cgjpaladin"
REPO_NAME="davinci-plugins"
CDN_BASE="https://cdn.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main"
API_BASE="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}"
RAW_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main"
PURGE_BASE="https://purge.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@main"

VERSION="${1:?用法: bash tools/publish_release.sh <版本号> <更新日志>}"
NOTES="${2:-修复与优化}"

WS="$(cd "$(dirname "$0")/.." && pwd)"

UPDATE_ZIP="$HOME/Desktop/交付自检工具_更新包.zip"

# ═══ 硬拦截 1：dev 环境禁止发布 ═══
DELIVERY_DIR="$WS/交付自检工具"
DEV_CHK=$(python3 -c "import sys; sys.path.insert(0,'$DELIVERY_DIR'); from config import __channel__; print(__channel__)" 2>/dev/null || echo "")
if [ -n "$DEV_CHK" ]; then
    echo "⛔ 当前处于开发环境（__channel__='$DEV_CHK'），禁止发布到 GitHub！"
    echo "   请先运行 cd 交付自检工具 && ./channel.sh prod 切换到生产环境。"
    exit 1
fi

# ═══ 硬拦截 2：版本号一致性校验 ═══
CONFIG_VER=$(python3 -c "import sys; sys.path.insert(0,'$DELIVERY_DIR'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
if [ "$VERSION" != "$CONFIG_VER" ]; then
    echo "❌ 版本号不一致！参数=$VERSION  config.py=$CONFIG_VER"
    echo "   发布前请确保 VERSION_BUMP 已运行，或手动对齐版本号。"
    exit 1
fi

if [ ! -f "$UPDATE_ZIP" ]; then
    echo "❌ 找不到 $UPDATE_ZIP，请先运行 bash build_personal.sh --all"
    exit 1
fi

SHA256=$(shasum -a 256 "$UPDATE_ZIP" | awk '{print $1}')
echo "═══ 发布 v$VERSION ═══"
echo "  SHA256: $SHA256"
echo "  日志: $NOTES"

# 1. 上传 zip 到 GitHub（必须先于 version.json，避免竞态）
echo "  → 上传更新包..."
CURRENT_SHA=$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" --jq .sha 2>/dev/null || true)
if [ -n "$CURRENT_SHA" ]; then
    gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" \
        -f message="release v$VERSION" \
        -f content="$(base64 -i "$UPDATE_ZIP")" \
        -f sha="$CURRENT_SHA" \
        -f branch=main || { echo "❌ zip 上传失败"; exit 1; }
else
    gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" \
        -f message="release v$VERSION" \
        -f content="$(base64 -i "$UPDATE_ZIP")" \
        -f branch=main || { echo "❌ zip 上传失败"; exit 1; }
fi
echo "  ✅ update_latest.zip"

# 2. 更新 version.json（保留历史，追加新条目）
python3 -c "
import json, sys

# 读现存的 version.json（如果有）
try:
    with open('$WS/version.json') as f:
        old = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    old = {}

cfg = old.get('delivery_checker', {})
history = cfg.get('history', [])

# 追加当前版本到历史
history.append({
    'version': '$VERSION',
    'notes': '''$NOTES'''
})

new = {
    'version': '$VERSION',
    'urls': [
        'https://ghproxy.net/https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/v$VERSION/update_v$VERSION.zip',
        'https://cdn.jsdelivr.net/gh/${REPO_OWNER}/${REPO_NAME}@v$VERSION/update_latest.zip',
        'https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/v$VERSION/update_v$VERSION.zip',
    ],
    'sha256': '$SHA256',
    'notes': '$NOTES',
    'history': history,
}

with open('/tmp/_publish_v.json', 'w') as f:
    json.dump({'delivery_checker': new}, f, indent=2, ensure_ascii=False)
"

# 写入 repo 根目录（参与 git 版本管理）
cp /tmp/_publish_v.json "$WS/version.json"

echo "  → 上传 version.json..."
gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" \
    -f message="release v$VERSION" \
    -f content="$(base64 -i /tmp/_publish_v.json)" \
    -f sha="$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" --jq .sha)" \
    -f branch=main --silent
echo "  ✅ version.json"

# 3. 刷新 CDN 缓存
echo "  → 刷新 jsDelivr 缓存..."
PURGE_V=$(curl -s -o /dev/null -w "%{http_code}" "${PURGE_BASE}/version.json")
PURGE_Z=$(curl -s -o /dev/null -w "%{http_code}" "${PURGE_BASE}/update_latest.zip")
if [ "$PURGE_V" = "200" ] || [ "$PURGE_V" = "202" ]; then
    echo "  ✅ CDN version.json (HTTP $PURGE_V)"
else
    echo "  ⚠ CDN version.json 返回 $PURGE_V（缓存可能延迟）"
fi
if [ "$PURGE_Z" = "200" ] || [ "$PURGE_Z" = "202" ]; then
    echo "  ✅ CDN update_latest.zip (HTTP $PURGE_Z)"
else
    echo "  ⚠ CDN update_latest.zip 返回 $PURGE_Z（缓存可能延迟）"
fi

echo "═══ v$VERSION 发布完成 ═══"
echo "用户下次启动自动检测更新。"
