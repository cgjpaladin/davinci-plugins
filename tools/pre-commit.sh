#!/bin/bash
# pre-commit.sh — 提交前检查（零 pip 依赖，纯 bash）
# 用法: bash tools/pre-commit.sh
# 集成: dev.sh 步骤1 自动调用，或 git pre-commit hook 自动触发
set -e

PLUGIN_DIR="$(cd "$(dirname "$0")/../AI去字幕" && pwd)"
FAIL=0

echo "═══ pre-commit 检查 ═══"

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
for pattern in "${BANNED_IMPORTS[@]}"; do
    HITS=$(grep -rn "$pattern" "$PLUGIN_DIR"/*.py "$PLUGIN_DIR"/adapters/*.py 2>/dev/null || true)
    if [ -n "$HITS" ]; then
        echo "  ❌ 检测到禁止的 pip 第三方包:"
        echo "$HITS"
        FAIL=1
    fi
done
[ $FAIL -eq 0 ] && echo "  ✅ 零 pip 依赖"

# ── 2. 禁止 SMB 全盘扫描 ──
echo "  🔍 检查: 禁止 SMB 全盘扫描..."
SMB_MOUNT="/Volumes/MYJC"
# 检测实际系统命令调用: find /Volumes/MYJC、grep -r /Volumes/MYJC、du -s /Volumes/MYJC
SMB_DANGER=$(grep -rnE \
    "(subprocess\.|os\.system\(|os\.popen\().*['\"](find|grep|du).*$SMB_MOUNT" \
    "$PLUGIN_DIR"/*.py "$PLUGIN_DIR"/adapters/*.py 2>/dev/null || true)
if [ -n "$SMB_DANGER" ]; then
    echo "  ❌ 检测到可能的 SMB 全盘扫描（会打挂 20 台机器）:"
    echo "$SMB_DANGER"
    FAIL=1
else
    echo "  ✅ 无 SMB 全盘扫描"
fi

# ── 3. 禁止硬编码密钥 ──
echo "  🔍 检查: 无硬编码密钥..."
KEY_LEAKS=$(grep -rn 'api_key\s*=\s*"[^"{]' "$PLUGIN_DIR"/*.py "$PLUGIN_DIR"/adapters/*.py 2>/dev/null || true)
if [ -n "$KEY_LEAKS" ]; then
    echo "  ❌ 检测到疑似硬编码密钥:"
    echo "$KEY_LEAKS"
    FAIL=1
else
    echo "  ✅ 无硬编码密钥"
fi

# ── 4. .env 在 .gitignore ──
echo "  🔍 检查: .env 在 .gitignore..."
GIT_ROOT="$(cd "$PLUGIN_DIR/.." && pwd)"
if [ -f "$GIT_ROOT/.gitignore" ]; then
    if grep -q '\.env' "$GIT_ROOT/.gitignore" 2>/dev/null; then
        echo "  ✅ .env 在 .gitignore"
    else
        echo "  ⚠️  .env 未在 .gitignore 中"
    fi
else
    echo "  💡 无 .gitignore 文件"
fi

# ── 5. mypy 类型检查（core.py）──
echo "  🔍 检查: mypy 类型..."
if command -v mypy &>/dev/null; then
    if mypy --no-implicit-optional --follow-imports=skip "$PLUGIN_DIR/core.py" 2>/dev/null; then
        echo "  ✅ mypy 通过"
    else
        echo "  ❌ mypy 类型错误"
        FAIL=1
    fi
else
    echo "  💡 mypy 未安装，跳过"
fi

echo "════════════════════════"
if [ $FAIL -ne 0 ]; then
    echo "❌ pre-commit 失败，请先修复"
    exit 1
else
    echo "✅ pre-commit 通过"
fi
