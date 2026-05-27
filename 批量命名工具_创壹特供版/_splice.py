"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash。创壹特供版 — 仅卡片版"""
import subprocess, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

css  = open('app.css', encoding='utf-8').read()
js   = open('app.js', encoding='utf-8').read()
html = open('renamer_web.html', encoding='utf-8').read()
out_name = 'renamer_web.html'

# 注入 git hash + branch + 构建时间
from datetime import datetime
try:
    h = subprocess.check_output(['git','-C','..','rev-parse','--short','HEAD']).decode().strip()
    b = subprocess.check_output(['git','-C','..','rev-parse','--abbrev-ref','HEAD']).decode().strip()
except:
    h = 'dev'; b = '?'
ts = datetime.now().strftime('%m-%d %H:%M')
js = re.sub(r"const APP_VERSION='[^']*'", f"const APP_VERSION='{h}'", js)
js = js.replace("const APP_BRANCH=''", f"const APP_BRANCH='{b}'")
js = js.replace("const APP_BUILD_TIME=''", f"const APP_BUILD_TIME='{ts}'")
js = js.replace("const IS_PRODUCTION=false", "const IS_PRODUCTION=true")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)

os.makedirs('_build', exist_ok=True)
open(f'_build/{out_name}', 'w', encoding='utf-8').write(html)
print(f'✅ Spliced [创壹特供版] → _build/{out_name} (v{h})')
