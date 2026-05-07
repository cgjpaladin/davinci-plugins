#!/bin/bash
# deploy.sh — AI 去字幕插件 一键部署（Mac）
# 用法: ./deploy.sh
# 功能: 将启动器复制到达芬奇 Scripts 目录，主体代码通过 SMB 共享
# 灰度发布: hostname 自动识别（Mac-mini-{IP末段}），无需额外配置

RESOLVE_SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
SMB_PLUGIN="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"

echo "=========================================="
echo "  AI 去字幕插件 — 部署工具"
echo "=========================================="

# 检查 SMB 挂载
if [ ! -d "$SMB_PLUGIN" ]; then
    echo "❌ SMB 未挂载或插件目录不存在:"
    echo "   $SMB_PLUGIN"
    echo ""
    echo "   请先挂载 SMB: smb://192.168.1.154/MYJC"
    exit 1
fi

# 创建 Scripts 目录（如果不存在）
mkdir -p "$RESOLVE_SCRIPTS"

# 清理旧版本（所有历史入口）
rm -f "$RESOLVE_SCRIPTS/AI去字幕.py" "$RESOLVE_SCRIPTS/AI去字幕_UI.py" "$RESOLVE_SCRIPTS/remove_watermark.py" "$RESOLVE_SCRIPTS/AI去水印.py" "$RESOLVE_SCRIPTS/machine_id.txt"

# 部署启动器 → 达芬奇菜单唯一入口: AI去字幕
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/launcher_ui.py" "$RESOLVE_SCRIPTS/AI去字幕.py"

if [ $? -eq 0 ]; then
    echo "✅ 部署成功"
    echo ""
    echo "   入口: 达芬奇 → Workspace → Scripts → AI去字幕"
    echo "   主体代码: $SMB_PLUGIN/（总监更新后全员自动同步）"
    echo ""
    echo "   依赖: macOS 自带 Python 3 + 系统 Python 3.13"
else
    echo "❌ 部署失败"
    exit 1
fi

# ── SSL 证书检查 ──
echo ""
echo "═══ SSL 证书检查 ═══"
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
echo "  Python 版本: $PY_VER"

# 只检查 Python 3.13+（老版本系统自带证书 OK）
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 13 ] 2>/dev/null; then
    echo "  检测 Python 3.13+ → 验证 SSL 证书..."
    SSL_OK=$(python3 -c '
import urllib.request, ssl
try:
    ctx = ssl.create_default_context()
    urllib.request.urlopen("https://api.wuhenai.com/v2/", timeout=10, context=ctx)
    print("OK")
except Exception as e:
    if "CERT" in str(e).upper():
        print("FAIL")
    else:
        print("OK")  # 404 等非证书错误 = SSL 正常
' 2>/dev/null)

    if [ "$SSL_OK" = "FAIL" ]; then
        echo "  ⚠️  SSL 证书缺失 → 尝试修复..."
        # 按版本找 Install Certificates.command
        CERT_CMD=$(ls -d "/Applications/Python ${MAJOR}.${MINOR}/Install Certificates.command" 2>/dev/null || \
                    ls -d "/Applications/Python ${MAJOR}.${MINOR}"*/Install* 2>/dev/null | head -1)
        if [ -f "$CERT_CMD" ]; then
            "$CERT_CMD" 2>&1 | tail -1
            echo "  ✅ SSL 证书已修复"
        else
            echo "  ❌ 未找到 Install Certificates.command"
            echo "  💡 请手动运行 Python ${MAJOR}.${MINOR} 安装目录下的 Install Certificates.command"
        fi
    else
        echo "  ✅ SSL 证书正常"
    fi
else
    echo "  ✅ Python < 3.13，系统证书 OK（无需额外操作）"
fi
