#!/bin/bash
# 批量命名工具 v4.0 — Handsontable 版 macOS 打包
set -e
cd "$(dirname "$0")"

SYSPY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

echo "=== Splicing ===" && $SYSPY _splice_v02.py

echo "=== Packing ==="
$SYSPY -m PyInstaller \
  --onedir --windowed \
  --name "批量命名工具-v4.0" \
  --icon app_icon.icns \
  --add-data "_build/table_v02.html:." \
  --hidden-import webview \
  --hidden-import bottle \
  --hidden-import tkinter \
  --noconfirm \
  renamer_v02.py

# Copy to desktop
rm -rf ~/Desktop/批量命名工具-v4.0.app
cp -R dist/批量命名工具-v4.0.app ~/Desktop/

echo "✅ 批量命名工具-v4.0.app 已输出到桌面"
