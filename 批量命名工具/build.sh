#!/bin/bash
# 批量命名工具 — 打包脚本
# 每次执行自动 commit 变更 + 重建 app 并放到桌面
set -e
cd "$(dirname "$0")"

# 自动 commit 变更
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A && git commit -m "build: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || true
fi

rm -rf build dist *.spec

/Library/Frameworks/Python.framework/Versions/3.13/bin/pyinstaller \
  --onedir --windowed \
  --name "批量命名工具" \
  --icon app_icon.icns \
  --add-data "renamer_web.html:." \
  --add-data "../shared:shared" \
  --collect-data webview \
  --collect-data bottle \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  --hidden-import bottle \
  --hidden-import proxy_tools \
  --hidden-import pyobjc \
  --noconfirm \
  renamer_web.py

rm -rf ~/Desktop/批量命名工具.app
cp -R dist/批量命名工具.app ~/Desktop/

echo "✅ 批量命名工具.app 已更新到桌面"
