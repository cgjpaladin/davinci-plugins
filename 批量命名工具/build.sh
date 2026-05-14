#!/bin/bash
# 批量命名工具 — 打包脚本
# 每次执行自动 commit 变更 + 重建 app 并放到桌面
set -e
cd "$(dirname "$0")"

# 预览改动
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "=== 改动预览 ==="
  git diff --stat -- . ':(exclude)*.icns' ':(exclude)*.png' ':(exclude)*.spec'
  echo "================"
fi

# 自动 commit 变更
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A && git commit -m "build: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || true
fi

# Node 语法检查
/opt/homebrew/bin/node --check app.js || { echo "❌ JS 语法错误"; exit 1; }

rm -rf build dist *.spec _build

# 拼接 CSS + HTML 模板 + JS → _build/renamer_web.html
mkdir -p _build
python3 -c "
css=open('app.css').read();js=open('app.js').read()
html=open('renamer_web.html').read()
html=html.replace('/* CSS_PLACEHOLDER */',css)
js=js.replace("const APP_VERSION='DEV'","const APP_VERSION='"+__import__('subprocess').check_output(['git','-C','..','rev-parse','--short','HEAD']).decode().strip()+"'")
html=html.replace('// JS_PLACEHOLDER',js)
open('_build/renamer_web.html','w').write(html)
"

/Library/Frameworks/Python.framework/Versions/3.13/bin/pyinstaller \
  --onedir --windowed \
  --name "批量命名工具" \
  --icon app_icon.icns \
  --add-data "_build/renamer_web.html:." \
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

# 验证打包完整性
BUNDLE="$HOME/Desktop/批量命名工具.app/Contents/Resources/renamer_web.html"
if python3 -c "
h=open('$BUNDLE').read()
assert ':root' in h, 'CSS missing'
assert 'DIGIT_RULES' in h, 'JS missing'
" 2>/dev/null; then
  echo "✅ 批量命名工具.app 已更新到桌面（CSS+JS 验证通过）"
else
  echo "❌ 打包异常：CSS/JS 未嵌入！"; exit 1
fi
