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
  APP_NAME="批量命名工具"
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

# 构建 dist/ → 验证 → zip → 桌面（一次打包一次清，就一个弹窗）
mkdir -p _build
python3 _splice.py "$VARIANT"

# 打包到临时 dist（每次 mktemp 全新目录，零删除）
BUILD_DIST=$(mktemp -d /tmp/renamer_build_XXXXXX)
$SYSPY -m PyInstaller \
  --onedir --windowed \
  --strip --noupx \
  --distpath "$BUILD_DIST" \
  --workpath "$BUILD_DIST/build" \
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
  --hidden-import PIL._webp \
  --hidden-import openpyxl \
  --hidden-import openpyxl.drawing.image \
  --hidden-import openpyxl.utils.units \
  --collect-all openpyxl \
  --noconfirm \
  renamer_web.py

# 清除旧构建 → ditto 新构建（ditto 原子替换，不嵌套，不多删）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_OUT="$SCRIPT_DIR/dist/$APP_NAME.app"
ditto "$BUILD_DIST/批量命名工具.app" "$APP_OUT" 2>/dev/null && echo "✅ $APP_NAME.app → dist/"

set +e  # 后续步骤可容忍失败（PlistBuddy 可能在 CI 不可用）

# 注入版本号到 Info.plist（原生 About 面板用）
VERSION=$(python3 -c "import re; m=re.search(r\"const APP_VERSION='([^']+)'\", open('$SCRIPT_DIR/app_table.js').read()); print(m.group(1) if m else '0.0.0')")
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP_OUT/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP_OUT/Contents/Info.plist" 2>/dev/null || true

rmdir "$BUILD_DIST" 2>/dev/null || true

# 验证打包完整性
BUNDLE="$APP_OUT/Contents/Resources/$HTML_FILE"
if python3 -c "
h=open('$BUNDLE').read()
assert ':root' in h, 'CSS missing'
assert 'DIGIT_RULES' in h or 'activateEdit' in h, 'JS missing'
" 2>&1; then
  echo \"✅ CSS+JS 验证通过\"
else
  echo \"❌ 打包异常：CSS/JS 未嵌入！$(ls "$BUNDLE" 2>&1 | head -1)\"
fi

# ═══ 更新包 ═══
# 全量（完整 .app，128MB，新装/大改时用）
FULL_ZIP="$HOME/WorkBuddy/达芬奇插件工坊/batch_renamer_mac.zip"
(cd "$SCRIPT_DIR/dist" && zip -rq "$FULL_ZIP" "$APP_NAME.app" 2>/dev/null)
if [ -f "$FULL_ZIP" ]; then
  SHA=$(shasum -a 256 "$FULL_ZIP" | cut -d' ' -f1)
  echo "✅ 全量包: $FULL_ZIP ($(du -h "$FULL_ZIP" | cut -f1)) SHA256=$SHA"
fi

# 差分（仅 shared/ Python 逻辑 + version.txt，<200KB，日常更新用）
DELTA_ZIP="$HOME/WorkBuddy/达芬奇插件工坊/update_latest.zip"
# 写入版本文件供运行时覆盖
echo "$VERSION" > "$APP_OUT/Contents/Resources/version.txt"
(cd "$APP_OUT/Contents/Resources" && \
 zip -rq "$DELTA_ZIP" \
  "$HTML_FILE" \
  "version.txt" \
  shared/ \
  -x "shared/__pycache__/*" "shared/*.pyc" \
     "shared/dftt_timecode/*" "shared/pypdf/*" \
     "shared/naming.py" "shared/script_parser.py" \
  2>/dev/null)
rm -f "$APP_OUT/Contents/Resources/version.txt"
if [ -f "$DELTA_ZIP" ]; then
  DSHA=$(shasum -a 256 "$DELTA_ZIP" | cut -d' ' -f1)
  echo "✅ 差分包: $DELTA_ZIP ($(du -h "$DELTA_ZIP" | cut -f1)) SHA256=$DSHA"
fi

# 同步到桌面（ditto 原子替换，不嵌套）
DESKTOP_APP="$HOME/Desktop/$APP_NAME.app"
ditto "$APP_OUT" "$DESKTOP_APP" 2>/dev/null && echo "✅ 桌面: $DESKTOP_APP"

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
