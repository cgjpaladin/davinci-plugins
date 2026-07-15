#!/bin/bash
# ═══ v3.8 提交前自检 — 防止模块加载崩 / JS 自引用 / replace_all 污染 ═══
set -e
cd "$(dirname "$0")/.."
FAIL=0

echo "═══ 1. Python import (mock webview) ═══"
python3 -c "
import sys; sys.path.insert(0,'批量命名工具'); sys.path.insert(0,'shared')
# mock webview — it's only available at runtime in the app bundle
import types; wv=types.ModuleType('webview'); sys.modules['webview']=wv
from app_core import RenamerAPI, _LOG_NAME, _DELTA_DIR, THUMB_SIZE
api=RenamerAPI(); cfg=api.get_config()
print(f'OK: {len(cfg[\"video_formats\"])} video, {len(cfg[\"image_formats\"])} image')
" 2>&1 || { echo "❌ Python import failed"; FAIL=1; }

echo "═══ 2. Python AST ═══"
python3 -c "import py_compile; py_compile.compile('批量命名工具/app_core.py', doraise=True); print('OK')" 2>&1 || { echo "❌ app_core.py syntax error"; FAIL=1; }

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
python3 << 'PYEOF' || FAIL=1
import re; py_lines=open('批量命名工具/app_core.py').readlines()
defined=set(); issues=[]
for i,l in enumerate(py_lines,1):
    m=re.match(r'^(\w+)\s*=',l.strip())
    if m and not l.strip().startswith(('def ','class ','import ','from ','#','try:','except','if ')) and not re.match(r'^\s+',l):
        defined.add(m.group(1))
    for ref in re.findall(r'\b(_LOG_NAME|_DELTA_DIR|THUMB_SIZE|THUMB_MAX)\b', l):
        if ref not in defined and i < 50:
            print(f'❌ L{i}: {ref} used before definition')
            issues.append(ref)
if issues: exit(1)
print('OK')
PYEOF

echo "═══ 6. naming.py 命名逻辑 ═══"
python3 -c "
import sys; sys.path.insert(0,'批量命名工具'); sys.path.insert(0,'shared')
from naming import build_filename, FIELD_CONFIG
fields = {f['key']: '01' for f in FIELD_CONFIG if f['key'] not in ('method','desc','status')}
fields.update({'method':'双轨版','desc':'测试镜头','status':'OK'})
result = build_filename(fields)
assert '_' in result, f'bad filename: {result}'
for k in fields:
    assert str(fields[k]) in result or k in ('method','desc','status','tk'), f'{k} value not in filename'
print('OK: ' + result[:50])
" || FAIL=1

echo "═══ 7. 字符串字面量污染（replace_all 误伤检测） ═══"
python3 -c "
import re, sys
files = ['批量命名工具/app_table.js', '批量命名工具/app_core.py']
# 已知常量名 — 不应出现在普通字符串内（f-string / const def 除外）
consts = ['THUMB_SIZE', '_DELTA_DIR', '_LOG_NAME', 'HINT_NO_METHOD', 'HINT_DESC',
          'FIELD_SANITIZE', 'METHOD_OPTIONS', 'STATUS_OPTIONS']
issues = 0
for fn in files:
    lines = open(fn).readlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for c in consts:
            if c in stripped:
                # allow: const/var/let definitions, f-strings, code references (no quotes around the name)
                if f\"'{c}'\" in stripped or f'\"{c}\"' in stripped:
                    # it's inside a plain string — only allow if it's a const definition
                    if not re.match(r'(const|var|let)\s+' + c + r'\s*=', stripped):
                        print(f'❌ {fn} L{i}: {c} in string literal: {stripped[:80]}')
                        issues += 1
if issues: exit(1)
print('OK')
" || FAIL=1

echo "═══ 8. 构建验证 ═══"
cd 批量命名工具 && python3 _splice.py table >/dev/null 2>&1 && echo "OK" || { echo "❌ _splice.py failed"; FAIL=1; }

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "✅ ALL CHECKS PASSED — safe to commit"
else
    echo ""
    echo "❌ $FAIL check(s) failed — fix before commit"
    exit 1
fi
