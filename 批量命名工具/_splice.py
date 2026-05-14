"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash。也可单独运行（python3 _splice.py）用于浏览器预览。"""
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

css = open('app.css').read()
js  = open('app.js').read()
html = open('renamer_web.html').read()

# 注入 git hash + 构建时间
from datetime import datetime
try:
    h = subprocess.check_output(['git','-C','..','rev-parse','--short','HEAD']).decode().strip()
except:
    h = 'dev'
ts = datetime.now().strftime('%m-%d %H:%M')
js = js.replace("const APP_VERSION='DEV'", f"const APP_VERSION='{h}'")
js = js.replace("const APP_BUILD_TIME=''", f"const APP_BUILD_TIME='{ts}'")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)

os.makedirs('_build', exist_ok=True)
open('_build/renamer_web.html', 'w').write(html)
print(f'✅ Spliced → _build/renamer_web.html (v{h})')
