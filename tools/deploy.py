#!/usr/bin/env python3
"""
tools/deploy.py — 一键部署到达芬奇

把 launcher.py 复制到达芬奇 Edit 目录，Workspace → Scripts 直接可见。
launcher.py 内部通过 shared/launcher_router.py 按主机名自动路由。

用法:
  python3 tools/deploy.py AI去字幕
  python3 tools/deploy.py 交付自检工具
  python3 tools/deploy.py --list
"""
import sys, os, shutil, argparse

_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)

DAVINCI_EDIT = os.path.expanduser(
    "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
)


def list_projects():
    """列出所有可部署项目"""
    projects = []
    for name in os.listdir(_project_root):
        path = os.path.join(_project_root, name)
        if not os.path.isdir(path) or name.startswith(".") or name in ("tools", "shared"):
            continue
        if os.path.exists(os.path.join(path, "launcher.py")):
            projects.append(name)
    return projects


def deploy(project_name, dry_run=False):
    """部署项目的 launcher 到达芬奇"""
    project_dir = os.path.join(_project_root, project_name)
    
    if not os.path.isdir(project_dir):
        print(f"❌ 项目不存在: {project_dir}")
        return False
    
    if not os.path.isdir(DAVINCI_EDIT):
        print(f"❌ 达芬奇 Edit 目录不存在: {DAVINCI_EDIT}")
        print(f"   请先启动一次 DaVinci Resolve")
        return False
    
    src = os.path.join(project_dir, "launcher.py")
    if not os.path.exists(src):
        print(f"❌ launcher.py 不存在: {src}")
        return False
    
    dst = os.path.join(DAVINCI_EDIT, f"{project_name}.py")
    if dry_run:
        print(f"  [DRY RUN] {src} → {dst}")
    else:
        shutil.copy2(src, dst)
        print(f"  ✅ launcher.py → {project_name}.py")
    
    print(f"\n🎉 已部署到 Workspace → Scripts:")
    print(f"   {project_name}.py")
    return True


def main():
    parser = argparse.ArgumentParser(description="部署到达芬奇 Edit 目录")
    parser.add_argument("project", nargs="?", help="项目名")
    parser.add_argument("--list", action="store_true", help="列出所有项目")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.list:
        projects = list_projects()
        print("可部署项目:")
        for name in projects:
            print(f"  {name}")
        return
    
    if not args.project:
        parser.print_help()
        return
    
    deploy(args.project, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
