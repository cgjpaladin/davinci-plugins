#!/bin/bash
# gray_verify.sh — 灰度部署后自检
DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/本地版"
echo "═══ 灰度自检 — $(hostname) ═══"
FAIL=0

for f in check_core.py config.py ui.py; do
    [ -f "$DIR/$f" ] && echo "  📁 $f ✅" || { echo "  📁 $f ❌ 缺失"; FAIL=1; }
done

LAUNCHER=$(ls "$DIR"/交付自检_*.py 2>/dev/null | head -1)
[ -n "$LAUNCHER" ] && echo "  🚀 launcher: $(basename $LAUNCHER) ✅" || { echo "  🚀 launcher ❌ 缺失"; FAIL=1; }

python3 -m py_compile "$DIR/check_core.py" 2>/dev/null && echo "  🔍 check_core.py 语法 ✅" || { echo "  🔍 check_core.py 语法 ❌"; FAIL=1; }
python3 -m py_compile "$DIR/ui.py" 2>/dev/null && echo "  🔍 ui.py 语法 ✅" || { echo "  🔍 ui.py 语法 ❌"; FAIL=1; }
python3 -m py_compile "$DIR/config.py" 2>/dev/null && echo "  🔍 config.py 语法 ✅" || { echo "  🔍 config.py 语法 ❌"; FAIL=1; }

VERSION=$(python3 -c "import sys; sys.path.insert(0,'$DIR'); from config import version_string; print(version_string())" 2>/dev/null || echo "?")
echo "  🏷 版本: $VERSION"

[ $FAIL -eq 0 ] && echo "✅ 灰度自检通过" || { echo "❌ 灰度自检失败"; exit 1; }
