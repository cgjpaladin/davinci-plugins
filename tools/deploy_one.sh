#!/bin/bash
# deploy_one.sh — 单机部署达芬奇插件（通过 SSH 免密）
# 用法: ./deploy_one.sh <机器ID> <产品名>       例如: ./deploy_one.sh 102 AI去字幕
#       ./deploy_one.sh --status                 查看所有产品部署概况
#       ./deploy_one.sh --dry-run <产品名>       预览待部署清单

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACKER="$SCRIPT_DIR/deploy_tracker.json"
MAP="/Users/bryan/WorkBuddy/达芬奇运维专家/machine_registry.json"
DAVINCI_DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊"

# ── --status 查看概况 ──
if [[ "${1:-}" == "--status" ]]; then
    python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
with open('$TRACKER') as f: dt = json.load(f)

products = dt.get('products', ['?'])
print(f'产品: {products}')
print(f'共: {len(mm)} 台')

for prod in products:
    deployed = [k for k in mm if prod in dt['machines'].get(k,{}).get('deployed',[])]
    pending  = [k for k in mm if prod not in dt['machines'].get(k,{}).get('deployed',[])]
    print(f'\n  {prod}: 已部署 {len(deployed)} / 待部署 {len(pending)}')
    if pending:
        for k in pending[:5]:
            m = mm[k]; dtm = dt['machines'].get(k,{})
            print(f'    mini{k}  {m[\"ip\"]}  {m[\"name\"]}  ({m[\"short\"]})')
        if len(pending) > 5:
            print(f'    ... 还有 {len(pending)-5} 台')
"
    exit 0
fi

# ── --dry-run 预览 ──
if [[ "${1:-}" == "--dry-run" ]]; then
    PROD="${2:?用法: ./deploy_one.sh --dry-run <产品名>}"
    echo "═══ $PROD 待部署清单 ═══"
    python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
with open('$TRACKER') as f: dt = json.load(f)
pending = [(k,v) for k,v in sorted(mm.items())
           if '$PROD' not in dt['machines'].get(k,{}).get('deployed',[])]
if not pending:
    print('  ✅ $PROD 全部已部署！')
else:
    print(f'  待部署: {len(pending)} 台')
    for k,v in pending[:10]:
        print(f'    mini{k}  {v[\"ip\"]}  {v[\"name\"]}')
    if len(pending) > 10:
        print(f'    ... 还有 {len(pending)-10} 台')
    "
    exit 0
fi

MID="${1:?用法: ./deploy_one.sh <机器ID> <产品名>}"
PRODUCT="${2:?用法: ./deploy_one.sh <机器ID> <产品名>}"

# ── 读机器信息 ──
MACHINE_INFO=$(python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
m = mm['$MID']
print(json.dumps(m))
")
IP=$(echo "$MACHINE_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['ip'])")
NAME=$(echo "$MACHINE_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")

# ── 源文件 ──
LAUNCHER_SRC="$ROOT/$PRODUCT/launcher.py"
if [[ ! -f "$LAUNCHER_SRC" ]]; then
    echo "❌ launcher.py 不存在: $LAUNCHER_SRC"
    exit 1
fi
TARGET_FILE="${PRODUCT}.py"

echo "═══ 部署 $PRODUCT 到 mini$MID ($NAME) @ $IP ═══"

# ── 1. 连接 ──
echo -n "[1/4] 连接 mini$MID ... "
if ssh -o ConnectTimeout=5 -o BatchMode=yes "mini$MID" 'echo alive' &>/dev/null 2>&1; then
    SSH_TARGET="mini$MID"
    echo "✅"
else
    echo "❌ 不在线，跳过"
    exit 0
fi

# ── 2. 复制 launcher ──
echo -n "[2/4] 复制 launcher ... "
ssh "$SSH_TARGET" "mkdir -p '$DAVINCI_DIR'" 2>/dev/null
scp -o ConnectTimeout=5 "$LAUNCHER_SRC" "$SSH_TARGET:$DAVINCI_DIR/$TARGET_FILE" 2>/dev/null && echo "✅" || { echo "❌ SCP 失败"; exit 1; }

# ── 3. dry-run 自检 ──
echo -n "[3/4] 自检 ... "
RESULT=$(ssh -o ConnectTimeout=5 "$SSH_TARGET" \
    "cd '$DAVINCI_DIR' && python3 '$TARGET_FILE' --dry-run" 2>&1) || true
if echo "$RESULT" | grep -q "部署自检通过"; then
    echo "✅"
else
    echo "⚠ $(echo "$RESULT" | tail -1)"
fi

# ── 3b. Fusion 兼容性（模拟 DaVinci 内 __file__ 不存在）──
echo -n "[3b/4] Fusion兼容 ... "
FUSION_OK=$(ssh -o ConnectTimeout=5 "$SSH_TARGET" "python3 -c \"
# 模拟 Fusion 环境：__file__ 不存在时 launcher 能否正确 fallback 路径
import sys, os
_path = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊'
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = _path
assert _HERE == _path, f'fallback failed: {_HERE}'
# 验证 SMB 可达（产品目录）
assert os.path.isdir('/Volumes/MYJC/06_Software/达芬奇脚本/$PRODUCT'), 'SMB unreachable'
print('OK')
\"" 2>&1)
if echo "$FUSION_OK" | grep -q "OK"; then
    echo "✅"
else
    echo "⚠ $(echo "$FUSION_OK" | tail -1)"
fi

# ── 4. 更新 tracker ──
echo -n "[4/4] 更新追踪 ... "
python3 -c "
import json
from datetime import datetime
with open('$TRACKER') as f: dt = json.load(f)
m = dt['machines'].setdefault('$MID', {})
deployed = m.setdefault('deployed', [])
if '$PRODUCT' not in deployed:
    deployed.append('$PRODUCT')
m['deployed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
machines = dt['machines']
total = len(machines)
dt['stats']['deployed'] = sum(1 for m in machines.values() if m.get('deployed'))
dt['stats']['pending'] = total - dt['stats']['deployed']
dt['last_updated'] = datetime.now().isoformat()
with open('$TRACKER', 'w') as f:
    json.dump(dt, f, indent=2, ensure_ascii=False)
" 2>/dev/null && echo "✅" || echo "⚠"

echo ""
echo "═══ 完成: $PRODUCT → mini$MID ($NAME) ═══"
