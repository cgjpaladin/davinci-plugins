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

UPDATE_ZIP="$HOME/Desktop/交付自检工具_更新包.zip"

if [ ! -f "$UPDATE_ZIP" ]; then
    echo "❌ 找不到 $UPDATE_ZIP，请先运行 bash build_personal.sh --all"
    exit 1
fi

SHA256=$(shasum -a 256 "$UPDATE_ZIP" | awk '{print $1}')
echo "═══ 发布 v$VERSION ═══"
echo "  SHA256: $SHA256"
echo "  日志: $NOTES"

# 1. 更新 version.json
cat > /tmp/_publish_v.json << EOF
{"delivery_checker":{"version":"$VERSION","url":"${CDN_BASE}/update_latest.zip","urls":["${API_BASE}/contents/update_latest.zip","${CDN_BASE}/update_latest.zip"],"sha256":"$SHA256","notes":"$NOTES"}}
EOF

echo "  → 上传 version.json..."
gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" \
    -f message="release v$VERSION" \
    -f content="$(base64 -i /tmp/_publish_v.json)" \
    -f sha="$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/version.json" --jq .sha)" \
    -f branch=main --silent
echo "  ✅ version.json"

# 2. 上传 zip
echo "  → 上传更新包..."
gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" \
    -f message="release v$VERSION" \
    -f content="$(base64 -i "$UPDATE_ZIP")" \
    -f sha="$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" --jq .sha || echo '')" \
    -f branch=main || \
gh api --method PUT "repos/${REPO_OWNER}/${REPO_NAME}/contents/update_latest.zip" \
    -f message="release v$VERSION" \
    -f content="$(base64 -i "$UPDATE_ZIP")" \
    -f branch=main --silent
echo "  ✅ update_latest.zip"

# 3. 刷新 CDN 缓存
echo "  → 刷新 jsDelivr 缓存..."
curl -s "${PURGE_BASE}/version.json" >/dev/null
curl -s "${PURGE_BASE}/update_latest.zip" >/dev/null
echo "  ✅ CDN"

echo "═══ v$VERSION 发布完成 ═══"
echo "用户下次启动自动检测更新。"
