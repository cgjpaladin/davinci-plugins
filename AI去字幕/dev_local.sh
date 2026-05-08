#!/bin/bash
# dev_local.sh — 本地验证，不同步 SMB
# 用法: ./dev_local.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 自动更新 launcher 文件名 ──
VERSION=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import __version__; print(__version__)")
LAUNCHER_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/本地版"

# dev 版本号检查：本地版和公司版一样 → 该升了
COMPANY_LAUNCHER=$(ls "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/公司版"/AI去字幕_*.py 2>/dev/null | head -1)
if [ -n "$COMPANY_LAUNCHER" ]; then
    COMPANY_VER=$(basename "$COMPANY_LAUNCHER" | sed 's/AI去字幕_v//' | sed 's/\.py$//')
    if [ "$VERSION" = "$COMPANY_VER" ]; then
        echo "WARNING: local version ($VERSION) == company version ($COMPANY_VER)"
        echo "  New dev cycle? Bump version first, e.g.:"
        echo "    __version__ = \"1.3.0-dev\""
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

# pre-commit
echo ""
echo "═══ pre-commit ═══"
bash ../tools/pre-commit.sh 2>&1 | grep -v "^$"

# 语法编译
echo ""
echo "═══ 语法编译 ═══"
FAIL=0
for f in *.py adapters/*.py; do
    [ -f "$f" ] || continue
    python3 -m py_compile "$f" 2>&1 && echo "  ✅ $f" || { echo "  ❌ $f"; FAIL=1; }
done
[ $FAIL -eq 0 ] && echo "✅ 全部通过" || { echo "❌ 有语法错误"; exit 1; }

# 导入链
echo ""
echo "═══ 导入链 ═══"
python3 -c "
import sys; sys.path.insert(0, '.')
import config, pricing, logger, mappings
print('  ✅ config/pricing/logger/mappings')
from timecode import SMPTE
print('  ✅ timecode')
from resolution import parse, name_from_str, classify, calc_output_dimensions
print('  ✅ resolution')
from pipeline_utils import validate_task, calc_cache_savings
print('  ✅ pipeline_utils')
from interface import CLIPipelineUI, DaVinciPipelineUI
print('  ✅ interface')
from xml_utils import get_aspect_ratio
print('  ✅ xml_utils')
from render_utils import get_current_render_settings
print('  ✅ render_utils')
print('✅ 全部导入链通过')
"

echo ""
echo "════════════════════"
echo "✅ 本地验证完成（未同步 SMB）"
echo "   确认没问题后运行 ./dev.sh 推送到全公司"
