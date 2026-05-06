#!/usr/bin/env python3
"""
tools/new.py — 插件项目脚手架
──────────────────────────────
一键生成新插件项目骨架，目录结构、launcher、config 全配好。

用法:
  python3 tools/new.py 换口型
  python3 tools/new.py 语音克隆
  python3 tools/new.py 超分辨率 --dry-run    # 预览不创建
"""
import sys, os, argparse

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)

TEMPLATE = """# -*- coding: utf-8 -*-
# {name} — 本地启动器（部署后永不更新）
# 部署时复制到: ~/Library/Application Support/.../Fusion/Scripts/Edit/
import sys
sys.path.insert(0, "/Volumes/MYJC/06_Software/达芬奇脚本/{dir_name}")
from main import run
run()
"""

TEMPLATE_UI = """# -*- coding: utf-8 -*-
# {name} UI — 外部进程启动器
# 达芬奇插件工坊 ✂️
import subprocess
subprocess.Popen([
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
    "/Volumes/MYJC/06_Software/达芬奇脚本/{dir_name}/ui.py"
])
"""

TEMPLATE_MAIN = """# -*- coding: utf-8 -*-
\"\"\"
{name} — 主逻辑
\"\"\"
import sys, os

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_here), "tools"))
from dvr import resolve, project, timeline, scan_io, balance


def run():
    \"\"\"入口函数\"\"\"
    print(f"[{name}] v0.1")
    print(f"  项目: {project().GetName() if project() else '(无)'}")
    
    clips = scan_io()
    print(f"  IO 内片段: {len(clips)}")
    for c in clips[:5]:
        print(f"    {c}")


if __name__ == "__main__":
    run()
"""

TEMPLATE_UI_MAIN = """# -*- coding: utf-8 -*-
\"\"\"
{name} UI — 外部进程版
\"\"\"
import sys, os
os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.append(_RESOLVE_MODULES)
sys.path.insert(0, "/Users/bryan/WorkBuddy/达芬奇插件工坊")

import DaVinciResolveScript as bmd
from tools.dvr import resolve, project, timeline, scan_io

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

WIN_ID = "com.myjc.{machine_name}"

dlg = disp.AddWindow({{
    "WindowTitle": "{name}",
    "ID": WIN_ID,
    "Geometry": [800, 300, 400, 300],
}}, [
    ui.VGroup({{"Spacing": 10}}, [
        ui.Label({{"ID": "lb", "Text": "{name} v0.1"}}),
        ui.Button({{"ID": "btn", "Text": "运行"}}),
    ]),
])

itm = dlg.GetItems()

def _close(ev):
    disp.ExitLoop()

dlg.On[WIN_ID].Close = _close
dlg.On["btn"].Clicked = _close

def main():
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()

if __name__ == "__main__":
    main()
"""


def new_project(name, dry_run=False):
    """创建新插件项目"""
    ws = os.path.join(_project_root, name)
    
    if os.path.exists(ws):
        print(f"❌ {ws} 已存在")
        return False
    
    if dry_run:
        print(f"[DRY RUN] 将创建: {ws}/")
        for f in ["launcher.py", "launcher_ui.py", "main.py", "ui.py", "config.py"]:
            print(f"  {f}")
        return True
    
    os.makedirs(ws, exist_ok=True)
    
    machine_name = name.lower().replace(" ", "_")
    dir_name = name  # SMB 目录名
    
    files = {
        "launcher.py": TEMPLATE.format(name=name, dir_name=dir_name),
        "launcher_ui.py": TEMPLATE_UI.format(name=name, dir_name=dir_name),
        "main.py": TEMPLATE_MAIN.format(name=name),
        "ui.py": TEMPLATE_UI_MAIN.format(name=name, machine_name=machine_name),
        "config.py": f"# {name} 配置文件\n__version__ = \"0.1\"\n",
    }
    
    for filename, content in files.items():
        path = os.path.join(ws, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    
    print(f"✅ 已创建 {ws}/")
    for f in files:
        print(f"   {f}")
    print(f"\n  下一步:")
    print(f"  1. cd {ws}")
    print(f"  2. 编辑 main.py 实现核心逻辑")
    print(f"  3. 编辑 ui.py 定制界面")
    print(f"  4. python3 tools/runner.py all 测试")
    return True


def main():
    parser = argparse.ArgumentParser(description="插件项目脚手架")
    parser.add_argument("name", help="项目名（中文）")
    parser.add_argument("--dry-run", action="store_true", help="预览不创建")
    args = parser.parse_args()
    new_project(args.name, args.dry_run)


if __name__ == "__main__":
    main()
