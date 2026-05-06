#!/bin/bash
# gray.sh — 灰度发布管理工具
# 用法:
#   gray.sh add 101          → 将 101 加入灰度
#   gray.sh add 101 102 103  → 批量加入灰度
#   gray.sh remove 101       → 将 101 移出灰度（回退稳定版）
#   gray.sh status           → 查看当前灰度状态
#   gray.sh promote          → 全量发布：灰度目录覆盖稳定版，清空灰度配置
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本"
STABLE_DIR="$SMB/AI去字幕"
GRAY_CFG="$STABLE_DIR/gray.json"

[ ! -d "$SMB" ] && echo "❌ SMB 未挂载: $SMB" && exit 1

_usage() {
    echo "灰度发布管理 — gray.sh"
    echo ""
    echo "  gray.sh add <id> [id...]    加入灰度"
    echo "  gray.sh remove <id> [id...] 移出灰度"
    echo "  gray.sh status               查看状态"
    echo "  gray.sh promote              全量发布"
    echo ""
    exit 1
}

_status() {
    echo "═══════════════════════════════════════"
    echo "  灰度发布状态"
    echo "═══════════════════════════════════════"
    if [ ! -f "$GRAY_CFG" ]; then
        echo "  gray.json 不存在 — 无灰度配置"
        return
    fi
    python3 -c "
import json, os
cfg = json.load(open('$GRAY_CFG'))
print(f'  灰度版本: {cfg[\"version\"]}')
print(f'  灰度目录: {cfg[\"gray_dir\"]}')
targets = cfg.get('targets', [])
print(f'  灰度机器: {targets if targets else \"(无 — 全员稳定版)\"}')
note = cfg.get('note', '')
if note:
    print(f'  备注: {note}')

gray_path = os.path.join('$SMB', cfg['gray_dir'])
if os.path.isdir(gray_path):
    import subprocess
    r = subprocess.run(['python3', '-c', 'import config; print(config.__version__)'],
                       cwd=gray_path, capture_output=True, text=True)
    print(f'  灰度版本号: {r.stdout.strip() if r.returncode == 0 else \"读取失败\"}')
else:
    print(f'  ⚠️  灰度目录不存在: {gray_path}')
"
}

_add() {
    [ $# -eq 0 ] && _usage
    python3 -c "
import json, sys
cfg = json.load(open('$GRAY_CFG'))
targets = set(cfg.get('targets', []))
new = set(a for a in sys.argv[1:] if a != '--')
added = new - targets
targets |= new
cfg['targets'] = sorted(targets)
json.dump(cfg, open('$GRAY_CFG', 'w'), indent=2, ensure_ascii=False)
print(f'✅ 已加入灰度: {sorted(added)}')
print(f'   当前灰度机器: {cfg[\"targets\"]}')
" -- "$@"
}

_remove() {
    [ $# -eq 0 ] && _usage
    python3 -c "
import json, sys
cfg = json.load(open('$GRAY_CFG'))
targets = set(cfg.get('targets', []))
remove = set(a for a in sys.argv[1:] if a != '--')
removed = targets & remove
targets -= remove
cfg['targets'] = sorted(targets)
json.dump(cfg, open('$GRAY_CFG', 'w'), indent=2, ensure_ascii=False)
print(f'✅ 已移出灰度: {sorted(removed)}')
print(f'   当前灰度机器: {cfg[\"targets\"]}')
" -- "$@"
}

_promote() {
    echo "⚠️  全量发布：将灰度版本覆盖到稳定版"
    echo ""
    
    GRAY_DIR=$(python3 -c "import json; print(json.load(open('$GRAY_CFG'))['gray_dir'])")
    GRAY_PATH="$SMB/$GRAY_DIR"
    
    if [ ! -d "$GRAY_PATH" ]; then
        echo "❌ 灰度目录不存在: $GRAY_PATH"
        exit 1
    fi
    
    echo "  灰度目录: $GRAY_PATH"
    echo "  稳定目录: $STABLE_DIR"
    echo ""
    
    # 确认
    read -p "  确认覆盖？输入 yes 继续: " confirm
    [ "$confirm" != "yes" ] && echo "  已取消" && exit 0
    
    # 保留稳定版的关键文件
    echo "  备份 gray.json..."
    cp "$GRAY_CFG" /tmp/gray.json.bak 2>/dev/null || true
    
    echo "  清理稳定版旧文件..."
    find "$STABLE_DIR" -name "*.py" -maxdepth 1 -delete
    find "$STABLE_DIR/adapters" -name "*.py" -delete 2>/dev/null || true
    
    echo "  复制灰度版 → 稳定版..."
    cp "$GRAY_PATH"/*.py "$STABLE_DIR/"
    [ -d "$GRAY_PATH/adapters" ] && cp "$GRAY_PATH/adapters"/*.py "$STABLE_DIR/adapters/"
    
    # 复制 routing shim 和 stable_ui.py（灰度版可能没有这些）
    if [ -f "$STABLE_DIR/stable_ui.py" ]; then
        echo "  ⚠️  覆盖了 stable_ui.py — 需要重建路由层"
        # 灰度版的 ui_external.py 需要重命名为 stable_ui.py
        cp "$STABLE_DIR/ui_external.py" "$STABLE_DIR/stable_ui.py"
    fi
    
    # 更新 gray.json: 清空 targets
    python3 -c "
import json
cfg = json.load(open('$GRAY_CFG'))
cfg['targets'] = []
cfg['note'] = '已全量发布 — 灰度结束'
json.dump(cfg, open('$GRAY_CFG', 'w'), indent=2, ensure_ascii=False)
"
    
    echo ""
    echo "✅ 全量发布完成"
    echo "   gray.json 已清空 targets，所有机器回稳定版"
    
    # 建议：灰度目录可以保留作为备份
    echo ""
    echo "  💡 灰度目录保留在: $GRAY_PATH"
    echo "     下次灰度前可以删除或用新版本覆盖"
}

case "${1:-}" in
    add)    shift; _add "$@" ;;
    remove) shift; _remove "$@" ;;
    status) _status ;;
    promote) _promote ;;
    *) _usage ;;
esac
