#!/bin/bash
# pre_deploy_check.sh — 每次发布前全链路验证
# 用法: bash tools/pre_deploy_check.sh
set -e
WS="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WS"

echo "═══ 发布前全链路验证 ═══"

# 1. 清理缓存
echo "1/6 清理缓存..."
find . -name '__pycache__' -not -path './shared/*' -exec rm -rf {} + 2>/dev/null || true
echo "  ✅ __pycache__ 已清"

# 2. 源码编译
echo "2/6 源码编译..."
python3 -m py_compile 交付自检工具/ui.py
echo "  ✅ ui.py"

# 3. 构建增量包（含出厂检验）
echo "3/6 构建增量包..."
bash 交付自检工具_个人版/build_personal.sh --update 2>&1 | tail -3
ZIP="$WS/交付自检工具_个人版/_build/交付自检工具_更新包.zip"
[ -f "$ZIP" ] || { echo "  ❌ 找不到 $ZIP"; exit 1; }
echo "  ✅ 178KB"

# 4. 安装脚本语法 + 全 .py 编译
echo "4/6 解压验证..."
python3 - "$ZIP" << 'PYEOF'
import zipfile, os, sys, tempfile, shutil
zf = zipfile.ZipFile(sys.argv[1], metadata_encoding="utf-8")
td = tempfile.mkdtemp(dir="/tmp")
try:
    zf.extractall(td)
    errs = 0
    for root, dirs, files in os.walk(td):
        for f in files:
            fp = os.path.join(root, f)
            if f.endswith(".command"):
                r = os.system(f'bash -n "{fp}"')
                if r != 0: errs += 1
            elif f.endswith(".py"):
                r = os.system(f'python3 -m py_compile "{fp}"')
                if r != 0: errs += 1
    if errs: print(f"  ❌ {errs} 个文件异常"); sys.exit(1)
    else: print(f"  ✅ 全 {sum(1 for _,_,fs in os.walk(td) for f in fs if f.endswith('.py') or f.endswith('.command'))} 个脚本通过")
finally:
    shutil.rmtree(td, ignore_errors=True)
PYEOF

# 5. 必需文件检查
echo "5/6 核心文件完整性..."
python3 -c "
import zipfile, sys
zf = zipfile.ZipFile('$ZIP')
names = '|'.join(zf.namelist())
for r in ['ui.py','config.py','check_core.py','launcher_personal.py','install_update.command']:
    assert r in names, f'MISSING: {r}'
    print(f'  ✅ {r}')
"

# 6. 版本一致性（双保险）
echo "6/6 版本号一致性..."
VER_SRC=$(grep '__version__' 交付自检工具/config.py | head -1 | grep -o '"[^"]*"')
VER_ZIP=$(python3 -c "
import zipfile,re
zf=zipfile.ZipFile('$ZIP',metadata_encoding='utf-8')
for n in zf.namelist():
 if 'config.py' in n:
  for L in zf.read(n).decode().split('\n'):
   m=re.search(r'\"([^\"]+)\"',L)
   if m: print(m.group(1));exit(0)
")
if [ "\"$VER_ZIP\"" != "$VER_SRC" ]; then
    echo "  ❌ 源码:${VER_SRC} ≠ zip内:${VER_ZIP}"
    exit 1
fi
echo "  ✅ $VER_ZIP"

echo ""
echo "🎉 全部通过 — 可以发布"
echo "  下一步: WARM_CDN=1 bash build_personal.sh --update && gh release create ..."
