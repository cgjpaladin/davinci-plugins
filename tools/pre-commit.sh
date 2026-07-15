#!/bin/bash
# pre-commit.sh — 提交前检查（打进去不装上去——禁止运行时 pip 导入）
# 用法: bash tools/pre-commit.sh
# 集成: push_all.sh 步骤1 自动调用，或 git pre-commit hook 自动触发
set -e

GIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHARED_DIR="$GIT_ROOT/shared"
TOOLS_DIR="$GIT_ROOT/tools"
FAIL=0

# ═══ 产品目录一致性校验 ═══
# .precommit-products 是唯一真相源：列表 ↔ 磁盘双向校验
PRODUCTS_FILE="$GIT_ROOT/.precommit-products"
if [ ! -f "$PRODUCTS_FILE" ]; then
    echo "❌ 缺少 .precommit-products，请创建并写入产品目录名（一行一个）"
    exit 1
fi

PRODUCT_DIRS=()
MISSING=""
while IFS= read -r dir; do
    [[ -z "$dir" || "$dir" =~ ^# ]] && continue
    if [ -d "$GIT_ROOT/$dir" ]; then
        PRODUCT_DIRS+=("$GIT_ROOT/$dir")
    else
        MISSING+="  $dir"
    fi
done < "$PRODUCTS_FILE"
[ -n "$MISSING" ] && echo "❌ .precommit-products 中目录不存在:$MISSING" && FAIL=1

EXTRANEOUS=""
for d in "$GIT_ROOT"/*/; do
    d=$(basename "$d")
    # 跳过非产品目录
    [[ "$d" =~ ^(shared|tools|docs|tests|data|cloud|knowledge|_build|dist|\.) ]] && continue
    # 含 .py 文件的视为产品
    ls "$GIT_ROOT/$d"/*.py >/dev/null 2>&1 || continue
    # active 列表匹配
    grep -v '^[[:space:]]*#' "$PRODUCTS_FILE" | grep -qxF "$d" && continue
    # 归档标记（# 产品名 开头的注释行 = 保留代码但不扫描）
    grep -q "^#[[:space:]]*$d" "$PRODUCTS_FILE" && continue
    EXTRANEOUS+="  $d"
done
[ -n "$EXTRANEOUS" ] && echo "❌ 未注册产品目录，请加到 .precommit-products:$EXTRANEOUS" && FAIL=1

# 构建扫描目录（shared + tools + 所有产品 .py + adapters/）
SCAN_DIRS=("$SHARED_DIR"/*.py "$TOOLS_DIR"/*.py)
for f in "$TOOLS_DIR"/*.sh; do
    [ "$(basename "$f")" = "pre-commit.sh" ] && continue  # 不扫描自身
    [ -f "$f" ] && SCAN_DIRS+=("$f")
done
for pd in "${PRODUCT_DIRS[@]}"; do
    for f in "$pd"/*.py; do [ -f "$f" ] && SCAN_DIRS+=("$f"); done
    [ -d "$pd/adapters" ] && for f in "$pd"/adapters/*.py; do [ -f "$f" ] && SCAN_DIRS+=("$f"); done
done

# 向后兼容别名（mypy / 单元测试 使用）
PLUGIN_DIR="$GIT_ROOT/AI去字幕"
DELIVERY_DIR="$GIT_ROOT/交付自检工具"

# 收集所有 staged + unstaged 变更的 .py 文件
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | grep '\.py$' || true)
ALL_CHANGED=$(git diff --name-only --diff-filter=ACMR 2>/dev/null | grep '\.py$' || true)
CHECK_FILES=$(echo -e "$STAGED_FILES\n$ALL_CHANGED" | sort -u | grep -v '^$' || true)

echo "═══ pre-commit 检查 ═══"

# ── 0. 语法检查（Python 编译）──
echo "  🔍 检查: Python 语法..."
SYNTAX_FAIL=0
if [ -n "$CHECK_FILES" ]; then
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        python3 -m py_compile "$GIT_ROOT/$f" 2>/dev/null || {
            echo "  ❌ 语法错误: $f"
            SYNTAX_FAIL=1
        }
    done <<< "$CHECK_FILES"
fi
[ $SYNTAX_FAIL -eq 0 ] && echo "  ✅ 语法无误"

# ── Import 级冒烟 + DRY 回归 + CHANGELOG ──
echo "  🔍 检查: check_core import 完整性..."
SMOKE_FAIL=0
python3 -c "import sys; sys.path.insert(0,'$SHARED_DIR'); sys.path.insert(0,'$DELIVERY_DIR'); from check_core import _TAIL_KW,_check_track_empty,_make_result,_get_smpte; assert _TAIL_KW==('未完待续','定格转场','全剧终')" 2>/dev/null || { echo "  ❌ check_core 模块无法导入"; SMOKE_FAIL=1; }
[ $SMOKE_FAIL -eq 0 ] && echo "  ✅ check_core import 通过"
[ $SMOKE_FAIL -ne 0 ] && FAIL=1

echo "  🔍 检查: DRY 回归..."
DRY_FAIL=0
SMPTE_COUNT=$(grep -c "SMPTE()" "$DELIVERY_DIR/check_core.py" 2>/dev/null || echo 1)
[ "$SMPTE_COUNT" -eq 1 ] || { echo "  ❌ check_core.py 有 $SMPTE_COUNT 处 SMPTE() 绕过（应为1）"; DRY_FAIL=1; }
grep -q "_SECTION_BUILDERS" "$DELIVERY_DIR/ui.py" 2>/dev/null && { echo "  ❌ ui.py 仍有 _SECTION_BUILDERS"; DRY_FAIL=1; }
grep -q "_make_result_passthrough" "$DELIVERY_DIR/ui.py" 2>/dev/null && { echo "  ❌ ui.py 仍有 _make_result_passthrough"; DRY_FAIL=1; }
[ $DRY_FAIL -eq 0 ] && echo "  ✅ DRY 无回归" || FAIL=1

echo "  🔍 检查: CHANGELOG 版本..."
VER=$(grep "__version__" "$DELIVERY_DIR/config.py" | head -1 | grep -oE "[0-9]+\.[0-9]+")
if grep -q "## v$VER" "$DELIVERY_DIR/CHANGELOG.md" 2>/dev/null; then
    echo "  ✅ CHANGELOG 已更新 v$VER"
else
    echo "  ⚠ CHANGELOG.md 缺少 v$VER 条目（patch 版可忽略）"
fi


# ── 1. 禁止 pip 第三方包 ──
echo "  🔍 检查: 打进去不装上去（禁止运行时 pip 导入）..."
BANNED_IMPORTS=(
    "import requests"
    "from requests"
    "import aiohttp"
    "from aiohttp"
    "import httpx"
    "from httpx"
    "import urllib3"
    "from urllib3"
    "import pip"
    "import setuptools"
    "import pkg_resources"
)
PIP_FAIL=0
for pattern in "${BANNED_IMPORTS[@]}"; do
    HITS=$(grep -rn "$pattern" ${SCAN_DIRS[@]} 2>/dev/null || true)
    if [ -n "$HITS" ]; then
        echo "  ❌ 检测到禁止的 pip 第三方包:"
        echo "$HITS"
        PIP_FAIL=1
    fi
done
[ $PIP_FAIL -eq 0 ] && echo "  ✅ 打进去不装上去"
[ $PIP_FAIL -ne 0 ] && FAIL=1

# ── 2. 禁止 SMB 全盘扫描 ──
echo "  🔍 检查: 禁止 SMB 全盘扫描..."
SMB_MOUNT="/Volumes/MYJC"
SMB_DANGER=$(grep -rnE \
    "(subprocess\.|os\.system\(|os\.popen\().*['\"](find|grep|du).*$SMB_MOUNT" \
    ${SCAN_DIRS[@]} 2>/dev/null || true)
if [ -n "$SMB_DANGER" ]; then
    echo "  ❌ 检测到可能的 SMB 全盘扫描（会打挂 20 台机器）:"
    echo "$SMB_DANGER"
    FAIL=1
else
    echo "  ✅ 无 SMB 全盘扫描"
fi

# ── 3. 禁止硬编码密钥 ──
echo "  🔍 检查: 无硬编码密钥..."
KEY_LEAKS=$(grep -rn 'api_key\s*=\s*"[^"{]' ${SCAN_DIRS[@]} 2>/dev/null || true)
KEY_LEAKS2=$(grep -rnE '(secret|password|token)\s*=\s*"[^"{]+"' ${SCAN_DIRS[@]} 2>/dev/null | grep -v 'os\.environ' | grep -v '_env(' | grep -v '\" in ' || true)
if [ -n "$KEY_LEAKS" ] || [ -n "$KEY_LEAKS2" ]; then
    echo "  ❌ 检测到疑似硬编码密钥:"
    [ -n "$KEY_LEAKS" ] && echo "$KEY_LEAKS"
    [ -n "$KEY_LEAKS2" ] && echo "$KEY_LEAKS2"
    FAIL=1
else
    echo "  ✅ 无硬编码密钥"
fi

# ── 4. .env 在 .gitignore ──
echo "  🔍 检查: .env 在 .gitignore..."
if [ -f "$GIT_ROOT/.gitignore" ]; then
    if grep -q '\.env' "$GIT_ROOT/.gitignore" 2>/dev/null; then
        echo "  ✅ .env 在 .gitignore"
    else
        echo "  ⚠️  .env 未在 .gitignore 中"
    fi
else
    echo "  💡 无 .gitignore 文件"
fi

# ── 5. 禁止调试残留 ──
echo "  🔍 检查: 无调试残留..."
DEBUG_FAIL=0
# breakpoint() 调用
BP_HITS=$(grep -rn 'breakpoint()' ${SCAN_DIRS[@]} 2>/dev/null || true)
if [ -n "$BP_HITS" ]; then
    echo "  ❌ 检测到 breakpoint() 调试残留:"
    echo "$BP_HITS"
    DEBUG_FAIL=1
fi
# 裸 print() — 排除 logger 模块中的 print、docstrings、注释
PRINT_HITS=$(grep -rn '^\s*print(' ${SCAN_DIRS[@]} 2>/dev/null \
    | grep -v 'logger\.py' \
    | grep -v 'if __name__' \
    | grep -v '#.*print' \
    || true)
if [ -n "$PRINT_HITS" ]; then
    echo "  ⚠️  检测到 print() 调用（请使用 logger 模块）:"
    echo "$PRINT_HITS"
    # print 降级为警告，不阻断（有些是 CLI 工具的正常输出）
fi
[ $DEBUG_FAIL -eq 0 ] && echo "  ✅ 无调试残留"

# ── 6. 禁止裸 except ──
echo "  🔍 检查: 异常处理规范..."
BARE_EXCEPT=$(grep -rn '^\s*except\s*:' ${SCAN_DIRS[@]} 2>/dev/null || true)
# 检测 except: 下一行是 pass（吞异常）
SILENT_PASS=$(grep -rnA1 'except\(\s*\w*\)\?\s*:' ${SCAN_DIRS[@]} 2>/dev/null | grep -E '^\d+-(\s*pass|\s*#.*pass)' || true)
if [ -n "$BARE_EXCEPT" ]; then
    echo "  ⚠️  检测到 $(echo "$BARE_EXCEPT" | wc -l | tr -d ' ') 处裸 except:（请指定异常类型）"
fi
if [ -n "$SILENT_PASS" ]; then
    echo "  ⚠️  检测到 except: pass 吞异常（请至少打日志）"
    echo "$SILENT_PASS"
fi
[ -z "$BARE_EXCEPT" ] && [ -z "$SILENT_PASS" ] && echo "  ✅ 异常处理规范"

# ── 7. mypy 类型检查（可选，需要安装 mypy）──
echo "  🔍 检查: mypy 类型..."
if command -v mypy &>/dev/null; then
    CORE_FILE="$PLUGIN_DIR/core.py"
    CORE_FILE2="$DELIVERY_DIR/check_core.py"
    [ ! -f "$CORE_FILE" ] && CORE_FILE="$SHARED_DIR/core.py"
    MYPY_OK=0
    for cf in "$CORE_FILE" "$CORE_FILE2"; do
        if [ -f "$cf" ]; then
            MYPYPATH="$PLUGIN_DIR:$DELIVERY_DIR:$SHARED_DIR" mypy --no-implicit-optional --follow-imports=skip "$cf" 2>/dev/null || MYPY_OK=1
        fi
    done
    if [ $MYPY_OK -eq 0 ]; then
        echo "  ✅ mypy 通过"
    else
        echo "  ❌ mypy 类型错误"
        FAIL=1
    fi
else
    echo "  💡 mypy 未安装，跳过"
fi

# ── 8. 单元测试（纯逻辑，不依赖达芬奇）──
echo "  🔍 检查: 单元测试..."
UNIT_OK=0
if [ -f "$PLUGIN_DIR/tests/test_core.py" ]; then
    _result=$(python3 "$PLUGIN_DIR/tests/test_core.py" 2>&1); _exit=$?
    echo "$_result" | tail -3
    [ $_exit -ne 0 ] && UNIT_OK=1
    if [ $UNIT_OK -eq 0 ]; then
        echo "  ✅ 单元测试通过"
    else
        echo "  ❌ 单元测试失败"
        FAIL=1
    fi
else
    echo "  💡 无单元测试文件，跳过"
fi

echo "════════════════════════"
if [ $FAIL -ne 0 ]; then
    echo "❌ pre-commit 失败，请先修复以上问题"
    exit 1
else
    echo "✅ pre-commit 通过"
fi
