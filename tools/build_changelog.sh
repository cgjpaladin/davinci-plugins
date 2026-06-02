#!/bin/bash
# 写公告时把上一版历史也夹带上，避免跨版本用户丢更新内容
# 用法: bash tools/build_changelog.sh "v2.5.0的新内容" > release_body.md
set -e

NEW_NOTES="$1"
if [ -z "$NEW_NOTES" ]; then
  echo "用法: $0 '新版本公告内容'" >&2
  exit 1
fi

PREV_RELEASE=$(gh release list --repo cgjpaladin/davinci-plugins --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null)
PREV_BODY=""
if [ -n "$PREV_RELEASE" ]; then
  PREV_BODY=$(gh release view "$PREV_RELEASE" --repo cgjpaladin/davinci-plugins --json body --jq '.body' 2>/dev/null)
fi

if [ -n "$PREV_BODY" ]; then
  echo '## 往期更新'
  echo "$PREV_BODY" | grep -v "^## v[0-9]" | sed 's/^## /### /' | head -20
  echo ""
fi

echo "$NEW_NOTES"
