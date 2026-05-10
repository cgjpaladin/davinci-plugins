#!/bin/bash
# sync.sh — 将本地改动同步到 SMB（开发用，不是部署用）
# 用法: ./sync.sh
set -e

SMB="/Volumes/MYJC/06_Software/达芬奇脚本/交付自检工具"

if [ ! -d "$SMB" ]; then
    echo "❌ SMB 未挂载: $SMB"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 版本检查（比纯数字，忽略 -dev 通道）──
SMB_RAW=$(python3 -c "import sys; sys.path.insert(0,'$SMB'); from config import __version__; print(__version__)" 2>/dev/null || echo "?")
LOCAL_RAW=$(python3 -c "from config import __version__; print(__version__)")
echo "🏷 本地: $(python3 -c 'from config import version_string; print(version_string())') | SMB: $(python3 -c "import sys; sys.path.insert(0,'$SMB'); from config import version_string; print(version_string())" 2>/dev/null || echo '?')"
if [ "$LOCAL_RAW" = "$SMB_RAW" ]; then
    read -p "改动值得升版本吗？(y/N) " BUMP
    if [ "$BUMP" = "y" ] || [ "$BUMP" = "Y" ]; then
        read -p "升大版本(1.x→2.0)还是小版本(1.1→1.2)？(M/m) " LEVEL
        if [ "$LEVEL" = "M" ] || [ "$LEVEL" = "M" ]; then
            python3 -c "import re; f=open('config.py'); c=f.read(); f.close(); c=re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"', lambda m: f'__version__ = \"{int(m.group(1))+1}.0.0\"', c); open('config.py','w').write(c)"
        else
            python3 -c "import re; f=open('config.py'); c=f.read(); f.close(); c=re.sub(r'__version__\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"', lambda m: f'__version__ = \"{m.group(1)}.{int(m.group(2))+1}.0\"', c); open('config.py','w').write(c)"
        fi
        python3 -c "from config import version_string; print(f'🏷 新版本: {version_string()}')"
    fi
fi

# ── 备份现有 SMB 文件 ──
BAK_DIR="$SMB/.bak_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BAK_DIR"
echo "备份 SMB → $BAK_DIR"

# ── 同步本产品文件 ──
FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(find . -maxdepth 1 \( -name '*.py' -o -name 'sync.sh' \) | sed 's|^\./||' | sort)

echo "同步到 SMB..."
for f in "${FILES[@]}"; do
    src="$PWD/$f"
    dst="$SMB/$f"
    if [ -f "$src" ]; then
        # 备份旧文件
        if [ -f "$dst" ]; then
            cp "$dst" "$BAK_DIR/$f" 2>/dev/null || true
        fi
        # 原子写入：先写临时文件再 rename
        cp "$src" "$dst.tmp" && mv "$dst.tmp" "$dst"
    fi
done

# ── 同步 dicts/ 词典 ──
DICTS_DIR="$SCRIPT_DIR/dicts"
if [ -d "$DICTS_DIR" ]; then
    SMB_DICTS="$SMB/dicts"
    mkdir -p "$SMB_DICTS"
    echo "同步 dicts/..."
    rsync -a "$DICTS_DIR/" "$SMB_DICTS/" 2>/dev/null
    echo "  ✅ dicts/ 同步完成"
fi

# 创建日志目录
mkdir -p "$SMB/logs"

# ── 语法检查 ──
echo "语法检查..."
FAIL=0
for f in "${FILES[@]}"; do
    if [ -f "$SMB/$f" ] && [[ "$f" == *.py ]]; then
        python3 -m py_compile "$SMB/$f" || FAIL=1
    fi
done

if [ $FAIL -eq 0 ]; then
    # ── 自动去通道（Python 靠变量引用，不是字符串匹配）──
    SMB_CFG="$SMB/config.py"
    python3 -c "
import re
with open('$SMB_CFG') as f: code = f.read()
code = re.sub(r'__channel__\s*=\s*\"[^\"]*\"', '__channel__ = \"\"', code)
with open('$SMB_CFG', 'w') as f: f.write(code)
" 2>/dev/null
    SMB_VER=$(python3 -c "import sys; sys.path.insert(0,'$SMB'); from config import version_string; print(version_string())")
    echo "🏷 SMB 版本: $SMB_VER"
    echo "✅ 同步完成"
else
    echo "❌ 有语法错误"
    exit 1
fi
