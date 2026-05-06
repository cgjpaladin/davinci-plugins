#!/bin/bash
# 批量安装 Python 3.13.13 + SSL 证书到所有 Mac mini
# 用法: ./install_python313.sh [mini101 mini102 ...]
# 不传参数 = 安装到所有 SSH 配置过的机器

set -e

PY_VERSION="3.13.13"
PY_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-macos11.pkg"
PY_PKG="/tmp/python-${PY_VERSION}.pkg"
PY_PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
CERT_CMD="/Applications/Python 3.13/Install Certificates.command"
PASSWORD="123456"

# 目标机器列表
if [ $# -eq 0 ]; then
    TARGETS=(101 102 103 104 105 106 107 108 109 110 131 132 133 134 136 137 138 140)
else
    TARGETS=("$@")
fi

echo "=== Python ${PY_VERSION} 批量安装 ==="
echo "目标: ${TARGETS[*]}"
echo ""

# 1. 本地下载 pkg（如未缓存）
if [ ! -f "$PY_PKG" ]; then
    echo "📥 下载 ${PY_URL} ..."
    curl -L -o "$PY_PKG" "$PY_URL"
    echo "✅ 下载完成 ($(du -h "$PY_PKG" | cut -f1))"
else
    echo "📦 使用缓存: $PY_PKG"
fi

# 2. 逐台安装
for id in "${TARGETS[@]}"; do
    echo ""
    echo "── mini${id} ──"

    # 检查在线
    if ! ssh -o ConnectTimeout=3 -o BatchMode=yes mini${id} 'echo online' 2>/dev/null | grep -q online; then
        echo "  ⏭ OFFLINE"
        continue
    fi

    # 检查是否已安装
    if ssh mini${id} "ls '$PY_PATH' 2>/dev/null" 2>/dev/null | grep -q python3; then
        VER=$(ssh mini${id} "'$PY_PATH' --version" 2>/dev/null)
        echo "  ✅ 已安装: $VER"
        continue
    fi

    # 推送 pkg
    echo "  📤 推送安装包..."
    scp -q "$PY_PKG" mini${id}:"$PY_PKG" || { echo "  ❌ scp 失败"; continue; }

    # 安装
    echo "  📦 安装中..."
    ssh mini${id} "echo '$PASSWORD' | sudo -S installer -pkg '$PY_PKG' -target / 2>&1" \
        | grep -v "Password:" | tail -1 || echo "  ⚠ installer 返回非零"

    # SSL 证书
    echo "  🔐 安装 SSL 证书..."
    ssh mini${id} "bash '$CERT_CMD' 2>&1" | tail -1 || echo "  ⚠ 证书安装失败"

    # 验证
    VER=$(ssh mini${id} "'$PY_PATH' --version 2>/dev/null" || echo "FAIL")
    echo "  ✅ $VER"

    # 清理远程 pkg
    ssh mini${id} "rm -f '$PY_PKG'" 2>/dev/null
done

echo ""
echo "=== 完成 ==="
