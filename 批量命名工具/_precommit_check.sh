#!/bin/bash
# ═══ v3.8 提交前自检 — 防止模块加载崩 / JS 自引用 / replace_all 污染 ═══
set -e
cd "$(dirname "$0")/.."
FAIL=0

echo "═══ 1. Python import (mock webview) ═══"
python3 -c "
import sys; sys.path.insert(0,'shared')
# mock webview — it's only available at runtime in the app bundle
import types; wv=types.ModuleType('webview'); sys.modules['webview']=wv
from app_core import RenamerAPI, _LOG_NAME, _DELTA_DIR, THUMB_SIZE
api=RenamerAPI(); cfg=api.get_config()
print(f'OK: {len(cfg[\"video_formats\"])} video, {len(cfg[\"image_formats\"])} image')
" 2>&1 || { echo "❌ Python import failed"; FAIL=1; }

echo "═══ 2. Python AST ═══"
python3 -c "import py_compile; py_compile.compile('shared/app_core.py', doraise=True); print('OK')" 2>&1 || { echo "❌ app_core.py syntax error"; FAIL=1; }

echo "═══ 3. JS syntax ═══"
node --check 批量命名工具/app_table.js 2>&1 && echo "OK" || { echo "❌ JS syntax error"; FAIL=1; }

echo "═══ 4. JS 自引用检测 ═══"
python3 -c "
import re; js=open('批量命名工具/app_table.js').read()
for m in re.finditer(r'const (\w+)\s*=\s*\1\s*[;\n]', js):
    print(f'❌ self-ref: {m.group(1)} = {m.group(1)}')
    exit(1)
print('OK')
" || FAIL=1

echo "═══ 5. Python 常量先于使用 ═══"
python3 << 'PYEOF'
import re; py_lines=open('shared/app_core.py').readlines()
defined=set(); issues=[]
for i,l in enumerate(py_lines,1):
    m=re.match(r'^(\w+)\s*=',l.strip())
    if m and not l.strip().startswith(('def ','class ','import ','from ','#','try:','except','if ')) and not re.match(r'^\s+',l):
        defined.add(m.group(1))
    for ref in re.findall(r'\b(_LOG_NAME|_DELTA_DIR|THUMB_SIZE|THUMB_MAX)\b', l):
        if ref not in defined and i < 50:
            if not any(x in l for x in ['def ','class ','import ','from ']):
                issues.append((ref,i))
if issues:
    for ref,i in issues: print(f'  L{i}: {ref} used before definition')
    exit(1)
print('OK')
PYEOF
[[ $? -ne 0 ]] && FAIL=1

echo "═══ 6. 构建验证 ═══"
cd 批量命名工具 && python3 _splice.py table >/dev/null 2>&1 && echo "OK" || { echo "❌ _splice.py failed"; FAIL=1; }

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "✅ ALL CHECKS PASSED — safe to commit"
else
    echo ""
    echo "❌ $FAIL check(s) failed — fix before commit"
    exit 1
fi
