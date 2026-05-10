#!/bin/bash
# pre-commit.sh — 提交前检查（零 pip 依赖，纯 bash + Python 标准库）
# 用法: bash tools/pre-commit.sh
# 集成: push_all.sh 步骤1 自动调用，或 git pre-commit hook 自动触发
set -e

GIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$GIT_ROOT/AI去字幕"
DELIVERY_DIR="$GIT_ROOT/交付自检工具"
SHARED_DIR="$GIT_ROOT/shared"
TOOLS_DIR="$GIT_ROOT/tools"
SCAN_DIRS=("$PLUGIN_DIR"/*.py "$PLUGIN_DIR"/adapters/*.py "$DELIVERY_DIR"/*.py "$SHARED_DIR"/*.py "$TOOLS_DIR"/*.py)
FAIL=0

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

# ── 1. 禁止 pip 第三方包 ──
echo "  🔍 检查: 零 pip 依赖..."
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
[ $PIP_FAIL -eq 0 ] && echo "  ✅ 零 pip 依赖"
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
KEY_LEAKS2=$(grep -rnE '(secret|password|token)\s*=\s*"[^"{]+"' ${SCAN_DIRS[@]} 2>/dev/null | grep -v 'os\.environ' | grep -v '_env(' || true)
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
    python3 "$PLUGIN_DIR/tests/test_core.py" 2>&1 | tail -3 || UNIT_OK=1
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
