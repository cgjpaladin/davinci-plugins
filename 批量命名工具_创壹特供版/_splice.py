"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash，同步版本号到 version_info.txt。
创壹特供版 — 表格版。版本号唯-来源：app.js 中的 const APP_VERSION='x.y'。
"""
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
js = re.sub(r"const APP_GIT_HASH=''", f"const APP_GIT_HASH='{h}'", js)
js = js.replace("const APP_BRANCH=''", f"const APP_BRANCH='{b}'")
js = js.replace("const APP_BUILD_TIME=''", f"const APP_BUILD_TIME='{ts}'")
js = js.replace("const IS_PRODUCTION=false", "const IS_PRODUCTION=true")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)

# ── 从 JS 提取版本号，自动同步 version_info.txt ──
m = re.search(r"const APP_VERSION='([^']+)'", js)
if m:
    ver = m.group(1)
    parts = ver.split('.')
    major, minor = parts[0], parts[1] if len(parts) > 1 else '0'
    patch = parts[2] if len(parts) > 2 else '0'
    with open(os.path.join(BASE, 'version_info.txt'), 'w', encoding='utf-8') as fv:
        fv.write(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'上海有点杰奏'),
           StringStruct(u'FileDescription', u'批量命名工具-创壹特供版'),
           StringStruct(u'FileVersion', u'{ver}.0'),
           StringStruct(u'InternalName', u'renamer-createone'),
           StringStruct(u'LegalCopyright', u'Copyright (c) 2026 西安幕屿剧创'),
           StringStruct(u'OriginalFilename', u'批量命名工具-创壹特供版.exe'),
           StringStruct(u'ProductName', u'批量命名工具-创壹特供版'),
           StringStruct(u'ProductVersion', u'{ver}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""")

os.makedirs('_build', exist_ok=True)
open(f'_build/{out_name}', 'w', encoding='utf-8').write(html)
print(f'✅ Spliced [创壹特供版] → _build/{out_name} (v{h})')
