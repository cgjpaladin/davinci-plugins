"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash。也可单独运行用于浏览器预览。

用法:
    python3 _splice.py           # 卡片版 (默认)
    python3 _splice.py table     # 表格版
"""
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# 检测版本
variant = 'table' if len(sys.argv) > 1 and sys.argv[1] == 'table' else 'card'

if variant == 'table':
    css  = open('app_table.css', encoding='utf-8').read()
    js   = open('app_table.js', encoding='utf-8').read()
    html = open('renamer_table.html', encoding='utf-8').read()
    out_name = 'renamer_table.html'
else:
    css  = open('card/app.css', encoding='utf-8').read()
    js   = open('card/app.js', encoding='utf-8').read()
    html = open('card/renamer_web.html', encoding='utf-8').read()
    out_name = 'renamer_web.html'

# 注入 git hash + branch + 构建时间
from datetime import datetime
try:
    h = subprocess.check_output(['git','-C','..','rev-parse','--short','HEAD']).decode().strip()
    b = subprocess.check_output(['git','-C','..','rev-parse','--abbrev-ref','HEAD']).decode().strip()
except:
    h = 'dev'; b = '?'
ts = datetime.now().strftime('%m-%d %H:%M')
js = js.replace("const APP_VERSION='DEV'", f"const APP_VERSION='{h}'")
js = js.replace("const APP_BRANCH=''", f"const APP_BRANCH='{b}'")
js = js.replace("const APP_BUILD_TIME=''", f"const APP_BUILD_TIME='{ts}'")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)

os.makedirs('_build', exist_ok=True)
open(f'_build/{out_name}', 'w', encoding='utf-8').write(html)
print(f'✅ Spliced [{variant}] → _build/{out_name} (v{h})')
