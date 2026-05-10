#!/usr/bin/env python3
"""
tools/new.py — 达芬奇插件工坊项目脚手架
─────────────────────────────────────────
一键生成新插件项目骨架，所有文件均符合当前编码规范：
- 版本号 __version__ + __channel__ 解耦
- fusionscript_loader 连接达芬奇
- logger 模块输出
- SMB 常量集中管理
- env 加载自动化
- 适配器注入模式

用法:
  python3 tools/new.py 换口型
  python3 tools/new.py 语音克隆
  python3 tools/new.py 超分辨率 --dry-run
"""

import sys, os, argparse, re

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
_SMB_SCRIPTS = "/Volumes/MYJC/06_Software/达芬奇脚本"
_PYTHON13 = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"


# ══════════════════════════════════════════════════════════
# 模板（所有占位符 __NAME__ / __DIR__ / __MACHINE__）
# ══════════════════════════════════════════════════════════

CONFIG_PY = '''# -*- coding: utf-8 -*-
"""
__NAME__ — 配置文件
"""
import os
import sys

# shared/ 模块可导入
_shared = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared')
if _shared not in sys.path:
    sys.path.insert(0, _shared)

from env import load_all_env
load_all_env(os.path.dirname(os.path.abspath(__file__)))

# ── 版本号 ──
__version__ = "0.1.0"
__channel__ = "dev"

def version_string():
    """完整版本字符串，如 '0.1.0-dev'"""
    return f"{__version__}{'-' + __channel__ if __channel__ else ''}"

# ── SMB 常量 ──
SMB_MOUNT = "/Volumes/MYJC"
SMB_SCRIPTS = os.path.join(SMB_MOUNT, "06_Software", "达芬奇脚本")
SMB_PLUGIN = os.path.join(SMB_SCRIPTS, "__DIR__")

# ── 调试模式 ──
def _env(key: str, fallback: str = ""):
    """读环境变量，新名优先"""
    return os.environ.get(f"{name.upper().replace(' ', '_')}_{key}", fallback)

# TODO: 定义 API 密钥
# API_KEY = _env("API_KEY")

# TODO: 定义输出路径
# def get_output_dir(project_root: str) -> str:
#     return os.path.join(project_root, "04_素材", "输出目录名")
'''

MAIN_PY = '''# -*- coding: utf-8 -*-
"""
__NAME__ — CLI 入口 & 核心流水线

双入口：
  人类入口: 达芬奇 Workspace → Scripts → __MACHINE__
  AI入口:   python3 main.py --dry-run --report-json report.json
"""
import sys, os, time, argparse, json

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.join(os.path.dirname(_here), 'shared'))

from config import __version__, version_string
from fusionscript_loader import bmd
from logger import title, step, ok, warn, fail, info


def connect_resolve():
    """连接达芬奇，返回 (resolve, project, timeline) 或报错"""
    r = bmd.scriptapp("Resolve")
    if not r:
        raise RuntimeError("达芬奇未启动")
    pm = r.GetProjectManager()
    pj = pm.GetCurrentProject()
    if not pj:
        raise RuntimeError("请先打开一个项目")
    tl = pj.GetCurrentTimeline()
    if not tl:
        raise RuntimeError("请先打开一条时间线")
    return r, pj, tl


def run_pipeline(dry_run: bool = False, report_json: str = "") -> dict:
    """TODO: 实现核心流水线"""
    info(f"__NAME__ v{version_string()}")
    try:
        r, pj, tl = connect_resolve()
        info(f"项目: {pj.GetName()}")
        info(f"时间线: {tl.GetName()}")

        # TODO: 扫描 IO 片段
        # TODO: 调用适配器
        # TODO: 下载并替换

        report = {"ok": True, "project": pj.GetName(), "timeline": tl.GetName()}
    except Exception as e:
        fail(str(e))
        report = {"ok": False, "error": str(e)}

    if report_json:
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=f"__NAME__ v{version_string()}")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()
    return run_pipeline(args.dry_run, args.report_json)


if __name__ == "__main__":
    main()
'''

UI_MAIN_PY = '''# -*- coding: utf-8 -*-
"""
__NAME__ UI — 达芬奇外部进程版
"""
import sys, os

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.join(os.path.dirname(_here), 'shared'))

from fusionscript_loader import bmd
from brand_template import BrandConfig

brand = BrandConfig(
    name="__NAME__",
    button="开始处理",
    window_title="__NAME__",
)

# ── 达芬奇连接 ──
fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

# ── 窗口 ──
WIN_ID = "com.myjc.__MACHINE__"
dlg = disp.AddWindow({
    "WindowTitle": f"{brand.window_title} v{version_string()}",
    "ID": WIN_ID,
    "Geometry": [800, 300, 600, 400],
}, [
    ui.VGroup({"Spacing": 8}, [
        ui.Label({"ID": "title", "Text": f"裁缝老师的达芬奇插件工坊 ✂️ | v{version_string()}",
                  "Weight": 0, "StyleSheet": "font-size: 11px;"}),
        ui.HGroup({"Spacing": 4, "Weight": 0}, [
            ui.Label({"ID": "status", "Text": "就绪", "Weight": 0}),
        ]),
        ui.Label({"ID": "log", "Text": "", "Weight": 10}),
        ui.HGroup({"Spacing": 4, "Weight": 0}, [
            ui.Button({"ID": "scan_btn", "Text": "扫描选区"}),
            ui.Button({"ID": "start_btn", "Text": brand.button, "Enabled": False}),
        ]),
    ]),
])

itm = dlg.GetItems()

# ── 事件 ──
dlg.On[WIN_ID].Close = lambda ev: disp.ExitLoop()

# TODO: 实现业务逻辑
# dlg.On["scan_btn"].Clicked = scan_io
# dlg.On["start_btn"].Clicked = process

dlg.Show()
disp.RunLoop()
dlg.Hide()
'''

LAUNCHER_PY = '''#!/usr/bin/env python3
# launcher.py — __NAME__ 启动器（薄包装 → shared/launcher_router.py）
import sys, os
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', 'shared'))
sys.path.insert(0, '/Volumes/MYJC/06_Software/达芬奇脚本/shared')
from launcher_router import route
route("__DIR__", ui_module="ui")
'''

ADAPTER_INIT_PY = '''# -*- coding: utf-8 -*-
"""
__NAME__ — 适配器接口

换 API = 换一个适配器类，插件主体不动。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    """任务描述"""
    video_path: str
    output_path: Optional[str] = None
    duration: float = 10.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Result:
    """处理结果"""
    success: bool
    output_path: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """适配器抽象基类"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def submit(self, task: Task) -> str:
        """提交任务，返回 task_id"""
        ...

    @abstractmethod
    def wait_for_result(self, task_id: str, timeout: int = 600,
                        cancel_check=None) -> Result:
        """等待结果"""
        ...

    def process(self, task: Task, timeout: int = 600, cancel_check=None) -> Result:
        """一键：提交→等待→下载"""
        try:
            task_id = self.submit(task)
            return self.wait_for_result(task_id, timeout, cancel_check=cancel_check)
        except Exception as e:
            return Result(success=False, error_message=str(e))


def create_default_adapter() -> BaseAdapter:
    """TODO: 创建默认适配器"""
    from config import ADAPTER_CONFIGS
    from copy import deepcopy
    cfg = deepcopy(ADAPTER_CONFIGS.get("default", {}))
    # TODO: from adapters.your_provider import YourAdapter
    # return YourAdapter(cfg)
    raise NotImplementedError("请实现适配器: adapters/__init__.py → create_default_adapter()")
'''

BUILD_LOCAL_SH = '''#!/bin/bash
# build_local.sh — __NAME__ 本地验证（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="__DIR__"
source "$SCRIPT_DIR/../tools/publish.sh"
publish_build_local
'''

PUSH_ALL_SH = '''#!/bin/bash
# push_all.sh — __NAME__ 一键验证 + 同步 SMB + 自动升版本
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
SMB="__SMB__"

VERSION=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import __version__; print(__version__)")

echo "═══ push_all.sh — __NAME__ v$VERSION ═══"
echo ""

# ── 1. 语法 + 导入 ──
bash build_local.sh || exit 1

# ── 2. SMB 目录 ──
if [ ! -d "$SMB" ]; then
    echo "❌ SMB 目录不存在: $SMB"
    exit 1
fi

# ── 3. 去 channel → 同步 → 恢复 ──
echo "═══ 同步到 SMB ═══"
CHANNEL=$(python3 -c "import sys; sys.path.insert(0,'.'); from config import __channel__; print(__channel__)")
if [ -n "$CHANNEL" ]; then
    echo "  去 channel: $CHANNEL → (空)"
    sed -i '' 's/^__channel__ = ".*"/__channel__ = ""/' config.py
fi

# 同步所有 .py 文件
for f in *.py adapters/*.py; do
    [ -f "$f" ] || continue
    mkdir -p "$(dirname "$SMB/$f")"
    cp "$f" "$SMB/$f"
done
echo "  ✅ 同步完成"

if [ -n "$CHANNEL" ]; then
    sed -i '' "s/^__channel__ = \"\"/__channel__ = \"$CHANNEL\"/" config.py
    echo "  恢复 channel: $CHANNEL"
fi

# ── 4. 自动升版本号 ──
OLD_VER=$(grep '__version__' config.py | head -1 | sed 's/.*"\\(.*\\)".*/\\1/')
MAJOR=$(echo "$OLD_VER" | cut -d. -f1)
MINOR=$(echo "$OLD_VER" | cut -d. -f2)
NEW_MINOR=$((MINOR + 1))
NEW_VER="$MAJOR.$NEW_MINOR.0"
echo ""
echo "═══ 版本升号 ═══"
echo "  $OLD_VER → $NEW_VER-dev"
sed -i '' "s/__version__ = \"$OLD_VER\"/__version__ = \"$NEW_VER\"/" config.py
bash build_local.sh 2>&1 | grep "launcher"

echo ""
echo "✅ push_all.sh 完成 — 全公司已更新到 v$VERSION，本地已升到 v$NEW_VER-dev"
'''

SYNC_SH = '''#!/bin/bash
# sync.sh — __NAME__ 同步到 SMB（薄包装 → tools/publish.sh）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCT_DIR="$SCRIPT_DIR"
PRODUCT_NAME="__DIR__"
source "$SCRIPT_DIR/../tools/publish.sh"
publish_sync
'''


# ══════════════════════════════════════════════════════════
# 生成逻辑
# ══════════════════════════════════════════════════════════

def _chmod_x(path: str):
    os.chmod(path, 0o755)


def new_project(name: str, dry_run: bool = False):
    ws = os.path.join(_project_root, name)

    if os.path.exists(ws):
        print(f"❌ {ws} 已存在")
        return False

    dir_name = name
    machine_name = dir_name  # 用作 WIN_ID / 日志文件名，中文目录名即可
    smb_dir = f"{_SMB_SCRIPTS}/__DIR__"

    files = {
        "config.py": CONFIG_PY,
        "main.py": MAIN_PY,
        "ui.py": UI_MAIN_PY,
        "launcher.py": LAUNCHER_PY,
        "adapters/__init__.py": ADAPTER_INIT_PY,
        "build_local.sh": BUILD_LOCAL_SH,
        "push_all.sh": PUSH_ALL_SH,
        "sync.sh": SYNC_SH,
    }

    if dry_run:
        print(f"[DRY RUN] 将创建: {ws}/")
        for f in files:
            print(f"  {f}")
        print(f"\n变量:")
        print(f"  name: __NAME__")
        print(f"  machine_name: __MACHINE__")
        print(f"  smb_dir: __SMB__")
        return True

    # Create directories
    for sub in ["adapters"]:
        os.makedirs(os.path.join(ws, sub), exist_ok=True)

    # Generate files (use replace for safety: templates contain { } in f-strings)
    for filename, template in files.items():
        path = os.path.join(ws, filename)
        content = (template
                   .replace("__NAME__", name)
                   .replace("__DIR__", dir_name)
                   .replace("__MACHINE__", machine_name)
                   .replace("__SMB__", smb_dir))
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # Make scripts executable
    for script in ["build_local.sh", "push_all.sh", "sync.sh"]:
        _chmod_x(os.path.join(ws, script))

    print(f"✅ 已创建 {ws}/")
    for f in files:
        print(f"   {f}")
    print()
    print("  📋 下一步:")
    print(f"  1. 编辑 {name}/config.py     — 定义 API 密钥 + 输出路径")
    print(f"  2. 编辑 {name}/adapters/__init__.py — 实现 create_default_adapter()")
    print(f"  3. 编辑 {name}/main.py       — 实现 run_pipeline()")
    print(f"  4. 编辑 {name}/ui.py         — 实现 UI 业务逻辑")
    print(f"  5. cd {name} && ./build_local.sh — 本地验证")
    print()
    print("  🏗️ 骨架已符合当前全部规范：")
    print("     __version__ + __channel__ 解耦")
    print("     fusionscript_loader 连接达芬奇")
    print("     env 自动加载")
    print("     SMB 常量集中管理")
    print("     适配器注入模式")
    print("     build_local / push_all 自动版本管理")
    return True


def main():
    parser = argparse.ArgumentParser(description="达芬奇插件工坊 — 项目脚手架")
    parser.add_argument("name", help="项目名（中文，如 换口型）")
    parser.add_argument("--dry-run", action="store_true", help="预览不创建")
    args = parser.parse_args()
    new_project(args.name, args.dry_run)


if __name__ == "__main__":
    main()
