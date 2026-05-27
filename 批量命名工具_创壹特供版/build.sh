#!/bin/bash
# 批量命名工具 · 创壹特供版 — 打包脚本 (macOS)
# 用法: bash build.sh
set -e
cd "$(dirname "$0")"
SYSPY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

APP_NAME="批量命名工具-创壹特供版"
HTML_FILE="renamer_web.html"
HTML_BUNDLE="_build/renamer_web.html"

# 预览改动
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "=== 改动预览 ==="
  git diff --stat -- . ':(exclude)*.icns' ':(exclude)*.png'
  echo "================"
fi

# 自动 commit
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A && git commit -m "build(createone): $(date '+%H:%M')" 2>/dev/null || true
fi

rm -rf build dist *.spec _build

# 拼接三文件 + 注入 git hash
mkdir -p _build
python3 _splice.py

# 打包（使用系统 Python，避开沙箱限制）
$SYSPY -m PyInstaller \
  --onedir --windowed \
  --name "批量命名工具-创壹特供版" \
  --icon app_icon.icns \
  --add-data "$HTML_BUNDLE:." \
  --add-data "../shared:shared" \
  --add-binary "/opt/homebrew/bin/ffmpeg:." \
  --add-binary "/opt/homebrew/bin/ffprobe:." \
  --collect-data webview \
  --hidden-import webview \
  --hidden-import bottle \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL.ImageOps \
  --hidden-import openpyxl \
  --hidden-import openpyxl.drawing.image \
  --hidden-import openpyxl.utils.units \
  --noconfirm \
  renamer_web.py

# 用 ditto 原子替换桌面 app
DESK="$HOME/Desktop/$APP_NAME.app"
if [ -d "$DESK" ]; then rm -rf "$DESK" 2>/dev/null || true; fi
ditto "dist/批量命名工具-创壹特供版.app" "$DESK"

# Ad-hoc 签名（移除 Gatekeeper 隔离标记，方便分发）
codesign --force --deep --sign - "$DESK" 2>/dev/null || true

# 验证打包完整性
BUNDLE="$DESK/Contents/Resources/$HTML_FILE"
if python3 -c "
h=open('$BUNDLE').read()
assert ':root' in h, 'CSS missing'
assert 'DIGIT_RULES' in h, 'JS missing'
" 2>/dev/null; then
  echo "✅ $APP_NAME.app 已更新到桌面（CSS+JS 验证通过）"
else
  echo "❌ 打包异常：CSS/JS 未嵌入！"; exit 1
fi
