#!/bin/bash
# bump_version.sh — 版本号 MINOR +0.1（1.0.0-dev → 1.1.0-dev）
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

old=$(python3 -c "from config import __version__; print(__version__)")
python3 << 'PYEOF'
import re
with open('config.py','r') as f: s = f.read()
new_s = re.sub(
    r'(__version__\s*=\s*)"(\d+)\.(\d+)\.(\d+)(-dev)?"',
    lambda m: f'{m.group(1)}"{m.group(2)}.{int(m.group(3))+1}.{m.group(4)}-dev"',
    s
)
with open('config.py','w') as f: f.write(new_s)
from config import __version__ as nv
print(nv)
PYEOF

new=$(python3 -c "from config import __version__; print(__version__)")
echo "  $old → $new"
python3 -c "
import json
cfg = json.load(open('gray.json'))
cfg['version'] = '$new'
cfg['gray_dir'] = 'AI去字幕_v' + '$new'
json.dump(cfg, open('gray.json','w'), indent=2, ensure_ascii=False)
"
echo "✅ 版本号已更新 + gray.json 同步"
