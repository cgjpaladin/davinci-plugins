#!/bin/bash
# quick_verify.sh — 三步快速验证：pre-commit → 语法编译 → 导入链
# build_local.sh 和 push_all.sh 共享，避免重复代码
set -e
cd "$(dirname "$0")/../AI去字幕"

# 1. pre-commit
echo ""
echo "═══ pre-commit ═══"
bash ../tools/pre-commit.sh 2>&1 | grep -v "^$"

# 2. 语法编译
echo ""
echo "═══ 语法编译 ═══"
FAIL=0
for f in *.py adapters/*.py ../shared/*.py; do
    [ -f "$f" ] || continue
    python3 -m py_compile "$f" 2>&1 && echo "  ✅ $f" || { echo "  ❌ $f"; FAIL=1; }
done
[ $FAIL -eq 0 ] && echo "✅ 全部通过" || { echo "❌ 有语法错误"; exit 1; }

# 3. 导入链
echo ""
echo "═══ 导入链 ═══"
python3 -c "
import sys; sys.path.insert(0, '.'); sys.path.insert(0, '../shared')
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
