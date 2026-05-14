"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash"""
import subprocess

css = open('app.css').read()
js  = open('app.js').read()
html = open('renamer_web.html').read()

# 注入 git hash
try:
    h = subprocess.check_output(['git','-C','..','rev-parse','--short','HEAD']).decode().strip()
except:
    h = 'unknown'
js = js.replace("const APP_VERSION='DEV'", f"const APP_VERSION='{h}'")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)
open('_build/renamer_web.html', 'w').write(html)
print(f'Spliced with version {h}')
