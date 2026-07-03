#!/bin/bash
# 批量命名工具 — 打包脚本
# 用法: bash build.sh         # 卡片版
#       bash build.sh table   # 表格版
set -e
cd "$(dirname "$0")"
VARIANT="${1:-table}"
SYSPY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3  # 系统 Python（有 PyInstaller，无沙箱）

if [ "$VARIANT" = "table" ]; then
  JS_FILE="app_table.js"
  HTML_FILE="renamer_table.html"
  HTML_BUNDLE="_build/renamer_table.html"
  APP_NAME="批量命名工具-表格版"
else
  JS_FILE="card/app.js"
  HTML_FILE="renamer_web.html"
  HTML_BUNDLE="_build/renamer_web.html"
  APP_NAME="批量命名工具-卡片版"
fi

# 预览改动
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "=== 改动预览 ==="
  git diff --stat -- . ':(exclude)*.icns' ':(exclude)*.png'
  echo "================"
fi

# 自动 commit
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A && git commit -m "build: $(date '+%H:%M')" 2>/dev/null || true
fi

# Node 语法检查
NODE=$(command -v node) || { echo "❌ Node.js 未安装"; exit 1; }
$NODE --check "$JS_FILE" || { echo "❌ JS 语法错误"; exit 1; }

rm -rf build dist *.spec _build

# 拼接三文件 + 注入 git hash
mkdir -p _build
python3 _splice.py "$VARIANT"

# 打包（使用系统 Python，避开沙箱限制）
$SYSPY -m PyInstaller \
  --onedir --windowed \
  --clean --strip --noupx \
  --name "批量命名工具" \
  --icon app_icon.icns \
  --add-data "$HTML_BUNDLE:." \
  --add-data "../shared:shared" \
  --add-binary "$(which ffmpeg || echo /opt/homebrew/bin/ffmpeg):." \
  --add-binary "$(which ffprobe || echo /opt/homebrew/bin/ffprobe):." \
  --collect-data webview \
  --hidden-import webview \
  --hidden-import bottle \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL.ImageOps \
  --hidden-import PIL.PngImagePlugin \
  --hidden-import openpyxl \
  --hidden-import openpyxl.drawing.image \
  --hidden-import openpyxl.utils.units \
  --collect-all openpyxl \
  --noconfirm \
  renamer_web.py

# 用 ditto 原子替换桌面 app（避免 cp -R 嵌套 + SIP 权限问题）
DESK="$HOME/Desktop/$APP_NAME.app"
if [ -d "$DESK" ]; then rm -rf "$DESK" 2>/dev/null || true; fi
ditto dist/批量命名工具.app "$DESK"

# 验证打包完整性
BUNDLE="$DESK/Contents/Resources/$HTML_FILE"
if python3 -c "
h=open('$BUNDLE').read()
assert ':root' in h, 'CSS missing'
assert 'DIGIT_RULES' in h or 'activateEdit' in h, 'JS missing'
" 2>/dev/null; then
  echo \"✅ $APP_NAME.app 已更新到桌面（CSS+JS 验证通过）\"
else
  echo \"❌ 打包异常：CSS/JS 未嵌入！\"; exit 1
fi

# ═══ 更新包（用于自动更新） ═══
UPDATE_ZIP="$HOME/WorkBuddy/达芬奇插件工坊/batch_renamer_mac.zip"
# 从桌面 app 打 zip（已经是最终名称）
cd "$HOME/Desktop"
zip -rq "$UPDATE_ZIP" "$APP_NAME.app" 2>/dev/null
cd "$OLDPWD"
if [ -f "$UPDATE_ZIP" ]; then
  SHA=$(shasum -a 256 "$UPDATE_ZIP" | cut -d' ' -f1)
  echo "✅ 更新包: $UPDATE_ZIP ($(du -h "$UPDATE_ZIP" | cut -f1)) SHA256=$SHA"
fi

# ══════════════════════════════════════════════════
# Windows 构建参考（在 PC 上执行）
# ══════════════════════════════════════════════════
# py -3.11 -m PyInstaller \
#   --onefile --noconsole --clean --strip --noupx \
#   --name "批量命名工具" \
#   --icon app_icon.ico --version-file version_info.txt \
#   --add-data "_build/renamer_table.html;." --add-data "../shared;shared" \
#   --hidden-import webview --hidden-import webview.platforms.edgechromium \
#   --hidden-import bottle \
#   --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageOps \
#   --hidden-import openpyxl --hidden-import openpyxl.utils --hidden-import openpyxl.drawing.image \
#   --collect-all webview --collect-all bottle --collect-all openpyxl \
#   --noconfirm renamer_web.py
