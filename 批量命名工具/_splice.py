"""build.sh 用：拼接 CSS + HTML + JS，注入 git hash，同步版本号到 version_info.txt。
也可单独运行用于浏览器预览。

版本号唯一来源：app_table.js 中的 const APP_VERSION='x.y'
改动版本号只需改这一处，splice 会自动同步 version_info.txt 和 HTML。

用法:
    python3 _splice.py           # 表格版 (默认)
    python3 _splice.py card      # 卡片版
"""
import subprocess, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# 检测版本
variant = 'card' if len(sys.argv) > 1 and sys.argv[1] == 'card' else 'table'
# 默认表格版；传 'card' 走卡片版

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
js = re.sub(r"const APP_GIT_HASH=''", f"const APP_GIT_HASH='{h}'", js)
js = js.replace("const APP_BRANCH=''", f"const APP_BRANCH='{b}'")
js = js.replace("const APP_BUILD_TIME=''", f"const APP_BUILD_TIME='{ts}'")

html = html.replace('/* CSS_PLACEHOLDER */', css)
html = html.replace('// JS_PLACEHOLDER', js)

# ── 从 JS 提取版本号，自动同步 version_info.txt ──
m = re.search(r"const APP_VERSION='([^']+)'", js)
if m:
    ver = m.group(1)
    parts = ver.split('.')
    major, minor = parts[0], parts[1] if len(parts) > 1 else '0'
    patch = parts[2] if len(parts) > 2 else '0'
    vi_path = os.path.join(BASE, 'version_info.txt')
    with open(vi_path, 'w', encoding='utf-8') as fv:
        fv.write(f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
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
           StringStruct(u'FileDescription', u'批量命名工具'),
           StringStruct(u'FileVersion', u'{ver}.0'),
           StringStruct(u'InternalName', u'renamer'),
           StringStruct(u'LegalCopyright', u'Copyright (c) 2026 上海有点杰奏'),
           StringStruct(u'OriginalFilename', u'批量命名工具.exe'),
           StringStruct(u'ProductName', u'批量命名工具'),
           StringStruct(u'ProductVersion', u'{ver}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
''')

os.makedirs('_build', exist_ok=True)
open(f'_build/{out_name}', 'w', encoding='utf-8').write(html)
print(f'✅ Spliced [{variant}] → _build/{out_name} (v{h})')
