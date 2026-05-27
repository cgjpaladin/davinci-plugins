#!/usr/bin/env python3
"""拼接 HTML + CSS + JS → _build/table_v02.html"""
import sys, os, subprocess
from datetime import datetime

cd = os.path.dirname(os.path.abspath(__file__))
os.chdir(cd)

# 读取源文件
css = open('table_v02.css', encoding='utf-8').read()
js = open('table_v02.js', encoding='utf-8').read()
ht_css = open('handsontable.min.css', encoding='utf-8').read()
ht_js = open('handsontable.min.js', encoding='utf-8').read()
html = open('table_v02.html', encoding='utf-8').read()

# Git hash
try:
    h = subprocess.check_output(['git', 'rev-parse', '--short=7', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
except Exception:
    h = 'dev'

ts = datetime.now().strftime('%m-%d %H:%M')
js = js.replace("const APP_VERSION='4.0'", f"const APP_VERSION='{h}'")
js = js.replace("const APP_BUILD_TIME='';", f"const APP_BUILD_TIME='{ts}';")

# 拼接 Handsontable + CSS + JS
full_css = ht_css + '\n' + css
full_js = ht_js + '\n' + js

html = html.replace('/* CSS_PLACEHOLDER */', full_css)
html = html.replace('// JS_PLACEHOLDER', full_js)

os.makedirs('_build', exist_ok=True)
with open('_build/table_v02.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'✅ Spliced v4.0 → _build/table_v02.html (v{h})')
