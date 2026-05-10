#!/bin/bash
# deploy_one.sh — 单机部署 + 追踪更新（通过 SSH 免密）
# 用法: ./deploy_one.sh <机器ID>       例如: ./deploy_one.sh 102
#       ./deploy_one.sh --dry-run      预览待部署清单
#       ./deploy_one.sh --status       查看部署概况

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TRACKER="$SCRIPT_DIR/deploy_tracker.json"
MAP="$SCRIPT_DIR/../AI去字幕/machine_map.json"
LAUNCHER_SRC="/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具/launcher_router.py"
TARGET_DIR="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Edit"
TARGET_FILE="交付自检.py"

# ── --status 查看概况 ──
if [[ "${1:-}" == "--status" ]]; then
    python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
with open('$TRACKER') as f: dt = json.load(f)

active = {k:v for k,v in mm.items() if v['status']=='在职'}
deployed = [k for k in active if dt['machines'].get(k,{}).get('status')=='deployed']
pending  = [k for k in active if dt['machines'].get(k,{}).get('status')=='pending']

print(f'在职: {len(active)} | 已部署: {len(deployed)} | 待部署: {len(pending)}')
if deployed:
    print('\\n已部署:')
    for k in deployed:
        m = mm[k]; dtm = dt['machines'].get(k,{})
        print(f'  mini{k}  {m[\"ip\"]}  {m[\"name\"]}  ({dtm.get(\"deployed_at\",\"?\")})')
if pending:
    print('\\n待部署:')
    for k in pending:
        m = mm[k]
        print(f'  mini{k}  {m[\"ip\"]}  {m[\"name\"]}  ({m[\"short\"]})')
"
    exit 0
fi

# ── dry-run 预览 ──
if [[ "${1:-}" == "--dry-run" ]]; then
    echo "═══ 待部署清单 ═══"
    python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
with open('$TRACKER') as f: dt = json.load(f)
pending = [(k,v) for k,v in sorted(mm.items()) 
           if v['status']=='在职' and dt['machines'].get(k,{}).get('status')=='pending']
if not pending:
    print('  ✅ 全部已部署！')
else:
    print(f'  待部署: {len(pending)} 台')
    for k,v in pending:
        print(f'    mini{k}  {v[\"ip\"]}  {v[\"name\"]}  ({v[\"short\"]})')
    "
    exit 0
fi

MID="${1:?用法: ./deploy_one.sh <机器ID>}"

# ── 读机器信息 ──
MACHINE_INFO=$(python3 -c "
import json
with open('$MAP') as f: mm = json.load(f)
m = mm['$MID']
print(json.dumps(m))
")

IP=$(echo "$MACHINE_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['ip'])")
NAME=$(echo "$MACHINE_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
STATUS=$(echo "$MACHINE_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")

if [[ "$STATUS" != "在职" ]]; then
    echo "⚠ $MID ($NAME): 状态=$STATUS，跳过"
    exit 0
fi

# ── 检查 tracker ──
CUR_STATUS=$(python3 -c "
import json
with open('$TRACKER') as f: dt = json.load(f)
print(dt['machines']['$MID'].get('status','unknown'))
" 2>/dev/null || echo "unknown")

if [[ "$CUR_STATUS" == "deployed" ]]; then
    echo "⚠ mini$MID ($NAME): 已部署，跳过"
    exit 0
fi

echo "═══ 部署 mini$MID ($NAME) @ $IP ═══"

# ── 1. 确认在线（SSH 直试，不 ping） ──
echo -n "[1/5] 连接 mini$MID ... "
if ssh -o ConnectTimeout=5 -o BatchMode=yes "mini$MID" 'echo alive' &>/dev/null; then
    echo "✅ 在线"
else
    # 回退到 IP 直连
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "bryan@$IP" 'echo alive' &>/dev/null; then
        SSH_TARGET="bryan@$IP"
        echo "✅ 在线 (IP直连)"
    else
        echo "❌ 不在线，跳过"
        exit 0
    fi
fi
SSH_TARGET="${SSH_TARGET:-mini$MID}"

# ── 2. 建目录 ──
echo -n "[2/5] 创建目标目录 ... "
ssh -o ConnectTimeout=5 "$SSH_TARGET" "mkdir -p '$TARGET_DIR'" 2>/dev/null && echo "✅" || { echo "❌ SSH 失败"; exit 1; }

# ── 3. 复制 launcher ──
echo -n "[3/5] 复制 launcher ... "
if [[ -f "$LAUNCHER_SRC" ]]; then
    scp -o ConnectTimeout=5 "$LAUNCHER_SRC" "$SSH_TARGET:$TARGET_DIR/$TARGET_FILE" 2>/dev/null && echo "✅" || { echo "❌ SCP 失败"; exit 1; }
else
    echo "❌ 源文件不存在: $LAUNCHER_SRC"
    exit 1
fi

# ── 4. dry-run 自检 ──
echo -n "[4/5] 自检 ... "
RESULT=$(ssh -o ConnectTimeout=5 "$SSH_TARGET" \
    "cd '$TARGET_DIR' && python3 '$TARGET_FILE' --dry-run" 2>&1) || true

if echo "$RESULT" | grep -q "部署自检通过"; then
    echo "✅ 通过"
    echo "$RESULT" | grep -E "  (✅|❌)" || true
else
    echo "⚠ 异常："
    echo "$RESULT"
fi

# ── 5. 更新 tracker ──
echo -n "[5/5] 更新追踪 ... "
python3 -c "
import json
from datetime import datetime
with open('$TRACKER') as f: dt = json.load(f)
dt['machines']['$MID']['status'] = 'deployed'
dt['machines']['$MID']['deployed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
dt['machines']['$MID']['note'] = '脚本自动部署'
machines = dt['machines']
dt['stats']['deployed'] = sum(1 for m in machines.values() if m['status'] == 'deployed')
dt['stats']['pending'] = sum(1 for m in machines.values() if m['status'] == 'pending')
dt['last_updated'] = datetime.now().isoformat()
with open('$TRACKER', 'w') as f:
    json.dump(dt, f, indent=2, ensure_ascii=False)
print(json.dumps({'deployed': dt['stats']['deployed'], 'pending': dt['stats']['pending']}))
" 2>/dev/null && echo "✅" || echo "⚠ 更新失败"

echo ""
echo "═══ 完成: mini$MID ($NAME) ═══"
