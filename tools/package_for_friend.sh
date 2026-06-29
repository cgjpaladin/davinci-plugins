#!/bin/bash
# package_for_friend.sh — 打包达芬奇插件工坊给朋友
# 产出: _export/达芬奇插件工坊_YYYYMMDD.zip
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M)
EXPORT_DIR="$PROJECT_ROOT/_export/达芬奇插件工坊"
ZIP_NAME="达芬奇插件工坊_${TIMESTAMP}.zip"

echo "═══ 打包达芬奇插件工坊 — 外部发布版 ═══"
echo ""

# 清理旧的
rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"

# 1. 复制产品代码
echo "📦 复制产品代码..."
for prod in "AI去字幕" "交付自检工具"; do
    if [ -d "$PROJECT_ROOT/$prod" ]; then
        rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'tests/' \
            --exclude '.env' --exclude '*.log' \
            "$PROJECT_ROOT/$prod/" "$EXPORT_DIR/$prod/"
        echo "  ✅ $prod"
    fi
done

# 2. 复制 shared/ 模块（排除敏感文件）
echo "📦 复制共享模块..."
rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.env' --exclude '*.log' \
    "$PROJECT_ROOT/shared/" "$EXPORT_DIR/shared/"
echo "  ✅ shared/"

# 3. 复制安装工具
echo "📦 复制安装工具..."
cp "$SCRIPT_DIR/deploy.json.template" "$EXPORT_DIR/"
cp "$SCRIPT_DIR/.env.template" "$EXPORT_DIR/"
cp "$SCRIPT_DIR/install_friend.sh" "$EXPORT_DIR/install.sh"
chmod +x "$EXPORT_DIR/install.sh"
echo "  ✅ 安装脚本"

# 4. 创建 README
cat > "$EXPORT_DIR/README.txt" << 'HEREDOC'
裁缝老师的达芬奇插件工坊 ✂️

一、部署到共享盘（只需做一次）
  1. 把整个文件夹复制到你们的 SMB 共享盘
     目标路径例如: /Volumes/你们的共享名/达芬奇脚本/
  2. 编辑 .env.template，填入 API Key，重命名为 .env
     放到 /Volumes/你们的共享名/达芬奇脚本/.env

二、每台 Mac mini 安装（每台做一次）
  1. 编辑 deploy.json.template:
     - smb_root: 改成你们的 SMB 路径
     - dev_hosts: 改成开发人员机器名
  2. 确保 SMB 已挂载
  3. 运行: bash install.sh
  4. 重启 DaVinci Resolve

三、更新
  修改共享盘上的代码 → 所有机器自动生效

API 注册:
  鬼手剪辑: https://www.zhaoli.com
  无痕AI: 联系无痕AI客服
  DeepSeek: https://platform.deepseek.com
  DeepSeek: https://platform.deepseek.com

问题联系: b站 电影裁缝Bryan
HEREDOC

# 5. 打包
mkdir -p "$PROJECT_ROOT/_export"
cd "$EXPORT_DIR/.."
zip -r "$PROJECT_ROOT/_export/$ZIP_NAME" "达芬奇插件工坊" -x "*.DS_Store"
echo ""
echo "════════════════════"
echo "✅ 打包完成"
echo ""
echo "📦 $PROJECT_ROOT/_export/$ZIP_NAME"
echo ""
du -sh "$PROJECT_ROOT/_export/$ZIP_NAME"
echo ""

# 列出内容
echo "📋 包含文件:"
unzip -l "$PROJECT_ROOT/_export/$ZIP_NAME" | tail -5
