#!/bin/bash
# sync.sh — 将本地改动同步到 SMB（开发用，不是部署用）
# 用法: ./sync.sh
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"

if [ ! -d "$SMB" ]; then
    echo "❌ SMB 未挂载: $SMB"
    exit 1
fi

# 自动发现所有 .py + gray.sh（排除 tests/ 和 dev 工具脚本）
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(find . -maxdepth 2 \( -name '*.py' -o -name 'gray.sh' \) \
    -not -path './tests/*' -not -name 'dev.sh' -not -name 'deploy.sh' -not -name 'sync.sh' \
    | sed 's|^\./||' | sort)

echo "同步到 SMB..."
for f in "${FILES[@]}"; do
    src="$PWD/$f"
    dst="$SMB/$f"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
    else
        echo "  ⚠ 跳过（不存在）: $f"
    fi
done

# 创建日志目录
mkdir -p "$SMB/logs"

# 语法检查
echo "语法检查..."
FAIL=0
for f in "${FILES[@]}"; do
    if [ -f "$SMB/$f" ] && [[ "$f" == *.py ]]; then
        python3 -m py_compile "$SMB/$f" || FAIL=1
    fi
done

if [ $FAIL -eq 0 ]; then
    echo "✅ 稳定版同步完成"
else
    echo "❌ 有语法错误"
    exit 1
fi

# ── 灰度目录同步 ──
_GRAY_CFG="$SMB/gray.json"
if [ -f "$_GRAY_CFG" ]; then
    GRAY_DIR=$(python3 -c "
import json, os
cfg = json.load(open('$_GRAY_CFG'))
targets = cfg.get('targets', [])
if targets:
    gray = os.path.join(os.path.dirname('$SMB'), cfg.get('gray_dir', ''))
    print(gray)
" 2>/dev/null)
    
    if [ -n "$GRAY_DIR" ] && [ -d "$GRAY_DIR" ]; then
        echo ""
        echo "灰度目录同步: $GRAY_DIR"
        for f in "${FILES[@]}"; do
            # 跳过灰度专有文件（路由 shim / 配置文件归 stable 目录管）
            case "$f" in
                ui_external.py|gray.sh|gray.json|launcher.py|launcher_ui.py) continue ;;
            esac
            src="$PWD/$f"
            dst="$GRAY_DIR/$f"
            if [ -f "$src" ]; then
                mkdir -p "$(dirname "$dst")"
                cp "$src" "$dst"
            fi
        done
        # 灰度版用自己的 ui_external.py 作为 stable_ui.py 入口
        if [ -f "$GRAY_DIR/ui_external.py" ]; then
            cp "$GRAY_DIR/ui_external.py" "$GRAY_DIR/stable_ui.py"
        fi
        echo "✅ 灰度版同步完成"
    fi
fi
