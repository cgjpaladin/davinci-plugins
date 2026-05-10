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

DAVINCI_EDIT = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"


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
    
    # 读版本号，本地 launcher 带版本后缀
    ver = ""
    try:
        sys.path.insert(0, project_dir)
        sys.path.insert(0, os.path.join(project_dir, "..", "shared"))
        import config
        ver = config.version_string()
    except Exception:
        pass
    
    if ver:
        filename = f"{project_name}_v{ver}.py"
    else:
        filename = f"{project_name}.py"
    
    # 清理旧版本 launcher（同一个项目只留一个）
    for fname in os.listdir(DAVINCI_EDIT):
        if fname == filename:
            continue
        if (fname.startswith(f"{project_name}_v") or fname == f"{project_name}.py") and fname.endswith(".py"):
            os.remove(os.path.join(DAVINCI_EDIT, fname))
            print(f"  🗑 清理旧 launcher: {fname}")
    
    dst = os.path.join(DAVINCI_EDIT, filename)
    if dry_run:
        print(f"  [DRY RUN] {src} → {dst}")
    else:
        shutil.copy2(src, dst)
        print(f"  ✅ launcher.py → {filename}")
    
    print(f"\n🎉 已部署到 Workspace → Scripts:")
    print(f"   {filename}")
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
