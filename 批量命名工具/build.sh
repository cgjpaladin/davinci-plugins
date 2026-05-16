#!/bin/bash
# 批量命名工具 — 打包脚本
# 用法: bash build.sh         # 卡片版
#       bash build.sh table   # 表格版
set -e
cd "$(dirname "$0")"
VARIANT="${1:-card}"

if [ "$VARIANT" = "table" ]; then
  JS_FILE="app_table.js"
  HTML_FILE="renamer_table.html"
  HTML_BUNDLE="_build/renamer_table.html"
else
  JS_FILE="app.js"
  HTML_FILE="renamer_web.html"
  HTML_BUNDLE="_build/renamer_web.html"
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

# 冒烟测试
if [ -f "test_smoke.py" ]; then
  python3 test_smoke.py || { echo "❌ 冒烟测试失败"; exit 1; }
fi

rm -rf build dist *.spec _build

# 拼接三文件 + 注入 git hash
mkdir -p _build
python3 _splice.py "$VARIANT"

python3 -m PyInstaller \
  --onedir --windowed \
  --name "批量命名工具" \
  --icon app_icon.icns \
  --add-data "$HTML_BUNDLE:." \
  --add-data "../shared:shared" \
  --collect-data webview \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  --hidden-import bottle \
  --noconfirm \
  renamer_web.py

rm -rf ~/Desktop/批量命名工具.app
cp -R dist/批量命名工具.app ~/Desktop/

# 验证打包完整性
BUNDLE="$HOME/Desktop/批量命名工具.app/Contents/Resources/$HTML_FILE"
if python3 -c "
h=open('$BUNDLE').read()
assert ':root' in h, 'CSS missing'
assert 'DIGIT_RULES' in h or 'activateEdit' in h, 'JS missing'
" 2>/dev/null; then
  echo \"✅ 批量命名工具.app [$VARIANT] 已更新到桌面（CSS+JS 验证通过）\"
else
  echo \"❌ 打包异常：CSS/JS 未嵌入！\"; exit 1
fi
