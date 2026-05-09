#!/bin/bash
# build_local.sh — 本地验证，不同步 SMB
# 用法: ./build_local.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 自动更新 launcher 文件名 ──
VERSION=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import version_string; print(version_string())")
LAUNCHER_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/本地版"

# dev 版本号检查：本地版和公司版一样 → 该升了
COMPANY_LAUNCHER=$(ls "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/公司版"/AI去字幕_*.py 2>/dev/null | head -1)
if [ -n "$COMPANY_LAUNCHER" ]; then
    COMPANY_VER=$(basename "$COMPANY_LAUNCHER" | sed 's/AI去字幕_v//' | sed 's/\.py$//')
    # 比较纯版本号（不含 channel）
    PURE_VER=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import __version__; print(__version__)")
    if [ "$PURE_VER" = "$COMPANY_VER" ]; then
        echo "WARNING: local version ($PURE_VER) == company version ($COMPANY_VER)"
        echo "  New dev cycle? Bump version first, e.g.:"
        echo "    __version__ = \"1.4.0\""
        echo ""
    fi
fi
if [ -d "$LAUNCHER_DIR" ]; then
    CURRENT=$(ls "$LAUNCHER_DIR"/AI去字幕_*.py 2>/dev/null | head -1)
    EXPECTED="$LAUNCHER_DIR/AI去字幕_v$VERSION.py"
    if [ "$CURRENT" != "$EXPECTED" ] && [ -n "$CURRENT" ]; then
        mv "$CURRENT" "$EXPECTED"
        echo "📝 launcher: $(basename "$CURRENT") → $(basename "$EXPECTED")"
    fi
fi

echo "═══ 本地验证模式 — 仅语法+导入链，不同步 SMB ═══"

# 三步快速验证（与 push_all.sh 共享）
bash ../tools/quick_verify.sh

echo ""
echo "════════════════════"
echo "✅ 本地验证完成（未同步 SMB）"
echo "   确认没问题后运行 ./push_all.sh 推送到全公司"
