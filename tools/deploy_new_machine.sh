#!/bin/bash
# deploy_new_machine.sh — 新机器一键部署（SSH + 改名 + 插件 launcher + machine_map）
# 用法: ./deploy_new_machine.sh <IP末段> <短名> <姓名> [全名]
set -e

if [ $# -lt 3 ]; then
    echo "用法: ./deploy_new_machine.sh <IP末段> <短名> <姓名> [全名]"
    echo "示例: ./deploy_new_machine.sh 141 macmini14 张三 'Mac mini 14'"
    exit 1
fi

IP_SEG="$1"
SHORT="$2"
NAME="$3"
FULL="${4:-Mac mini $IP_SEG}"
IP="192.168.1.$IP_SEG"
SSH_KEY="/Users/bryan/.ssh/id_ed25519_nopass"

# 路径
SCRIPTS_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
COMPANY_DIR="$SCRIPTS_DIR/公司版"
LAUNCHER_SRC="$COMPANY_DIR/AI去字幕_v1.5.0.py"
LAUNCHER_DST="$(basename "$LAUNCHER_SRC")"
MAP_FILE="/Users/bryan/WorkBuddy/达芬奇插件工坊/AI去字幕/machine_map.json"

echo "════ 新机器部署: mini${IP_SEG} (${IP}) ════"

# ── 1. SSH config ──
echo ""
echo "═══ 1. SSH config ═══"
SSH_CONFIG="$HOME/.ssh/config"
HOST_ENTRY="
Host mini${IP_SEG}
    HostName ${IP}
    User ${SHORT}
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no
    IdentitiesOnly yes
"
if grep -q "mini${IP_SEG}" "$SSH_CONFIG" 2>/dev/null; then
    echo "  ⏭  mini${IP_SEG} 已存在，跳过"
else
    echo "$HOST_ENTRY" >> "$SSH_CONFIG"
    echo "  ✅ 已添加 mini${IP_SEG}"
fi

# ── 2. SSH key ──
echo ""
echo "═══ 2. SSH 密钥部署 ═══"
PUBKEY=$(cat "${SSH_KEY}.pub" | tr -d '\n')
expect -c "
set timeout 20
spawn ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=keyboard-interactive -o PubkeyAuthentication=no -o IdentityFile=/dev/null ${SHORT}@${IP} {mkdir -p ~/.ssh && echo \"$PUBKEY\" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo KEY_DONE}
expect {
    \"assword:\" {send \"123456\r\"; exp_continue}
    \"KEY_DONE\" {exit 0}
    eof
}
"
echo ""
# 验证
if ssh -o ConnectTimeout=5 -o BatchMode=yes mini${IP_SEG} 'echo OK' 2>/dev/null | grep -q OK; then
    echo "  ✅ 免密登录成功"
else
    echo "  ⚠️ 免密失败，试试交互式方法..."
    expect -c "
    set timeout 15
    spawn ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=keyboard-interactive -o PubkeyAuthentication=no -o IdentityFile=/dev/null ${SHORT}@${IP}
    expect \"assword:\" {send \"123456\r\"}
    expect \"% \" {send \"mkdir -p ~/.ssh\r\"}
    expect \"% \" {send \"echo '$PUBKEY' >> ~/.ssh/authorized_keys\r\"}
    expect \"% \" {send \"chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo KEY_DONE\r\"}
    expect \"KEY_DONE\" {send \"exit\r\"}
    expect eof
    "
    if ssh -o ConnectTimeout=3 -o BatchMode=yes mini${IP_SEG} 'echo OK' 2>/dev/null | grep -q OK; then
        echo "  ✅ 免密登录成功（交互式）"
    else
        echo "  ❌ 免密部署失败，请手动检查"
        exit 1
    fi
fi

# ── 3. 改名 ──
echo ""
echo "═══ 3. 统一命名 ═══"
ssh mini${IP_SEG} "echo '123456' | sudo -S scutil --set ComputerName '${FULL}' 2>/dev/null; echo '123456' | sudo -S scutil --set LocalHostName 'Mac-mini-${IP_SEG}' 2>/dev/null"
echo "  ✅ ComputerName: ${FULL}"
echo "  ✅ LocalHostName: Mac-mini-${IP_SEG}"

# ── 4. 安装 Python 3.13 + SSL ──
echo ""
echo "═══ 4. Python 3.13 + SSL ═══"
PY_PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if ssh mini${IP_SEG} "[ -f '$PY_PATH' ] && echo OK" 2>/dev/null | grep -q OK; then
    echo "  ⏭  Python 3.13 已安装"
else
    echo "  安装中..."
    cd /Users/bryan/WorkBuddy/达芬奇插件工坊
    bash tools/install_python313.sh "mini${IP_SEG}"
    echo "  ✅ Python 3.13 + SSL 安装完成"
fi

# ── 5. 部署插件 launcher ──
echo ""
echo "═══ 5. 插件 launcher ═══"
ssh mini${IP_SEG} "mkdir -p '${COMPANY_DIR}'"
scp "$LAUNCHER_SRC" "mini${IP_SEG}:${COMPANY_DIR}/${LAUNCHER_DST}"
echo "  ✅ ${LAUNCHER_DST} → mini${IP_SEG}:${COMPANY_DIR}"

# ── 6. machine_map.json ──
echo ""
echo "═══ 6. machine_map ═══"
python3 -c "
import json
with open('${MAP_FILE}') as f:
    mm = json.load(f)
mm['${IP_SEG}'] = {
    'name': '${NAME}',
    'short': '${SHORT}',
    'full': '${FULL}',
    'status': '在职',
    'ip': '${IP}'
}
with open('${MAP_FILE}', 'w') as f:
    json.dump(mm, f, ensure_ascii=False, indent=2)
print(f'  ✅ 已添加 mini${IP_SEG} → ${NAME}')
"

# ── 6. 验证 ──
echo ""
echo "════ 部署完成 ════"
echo "  mini${IP_SEG} | ${IP} | ${NAME} | ${SHORT}"
echo ""
echo "下一步：更新 Macmini远程登录 skill 的机器清单"