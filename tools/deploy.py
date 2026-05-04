#!/usr/bin/env python3
"""
tools/deploy.py — 一键部署到 DaVinci
──────────────────────────────────
把 launcher 脚本复制到达芬奇 Edit 目录，Workspace → Scripts 直接可见。

用法:
  python3 tools/deploy.py AI去字幕              # 部署 AI去字幕 的 launcher
  python3 tools/deploy.py AI去字幕 --ui          # 部署 UI 版 launcher
  python3 tools/deploy.py AI去字幕 --all         # 同时部署 CLI + UI
  python3 tools/deploy.py 换口型                  # 部署其他项目
  python3 tools/deploy.py --list                 # 列出所有项目
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
        if not os.path.isdir(path) or name.startswith(".") or name in ("tools",):
            continue
        has_cli = os.path.exists(os.path.join(path, "launcher.py"))
        has_ui = os.path.exists(os.path.join(path, "launcher_ui.py"))
        if has_cli or has_ui:
            types = []
            if has_cli: types.append("CLI")
            if has_ui: types.append("UI")
            projects.append((name, types))
    return projects


def deploy(project_name, ui=False, cli=False, dry_run=False):
    """部署项目的 launcher 到达芬奇"""
    project_dir = os.path.join(_project_root, project_name)
    
    if not os.path.isdir(project_dir):
        print(f"❌ 项目不存在: {project_dir}")
        return False
    
    if not os.path.isdir(DAVINCI_EDIT):
        print(f"❌ 达芬奇 Edit 目录不存在: {DAVINCI_EDIT}")
        print(f"   请先启动一次 DaVinci Resolve")
        return False
    
    deployed = []
    
    def _copy(src_name, dst_name):
        src = os.path.join(project_dir, src_name)
        if not os.path.exists(src):
            print(f"  ⚠ {src_name} 不存在，跳过")
            return
        dst = os.path.join(DAVINCI_EDIT, dst_name)
        if dry_run:
            print(f"  [DRY RUN] {src} → {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  ✅ {src_name} → {dst_name}")
        deployed.append(dst_name)
    
    if cli or (not ui and not cli):
        _copy("launcher.py", f"{project_name}.py")
    
    if ui:
        _copy("launcher_ui.py", f"{project_name}_UI.py")
    
    if deployed:
        print(f"\n🎉 已部署到 Workspace → Scripts:")
        for name in deployed:
            print(f"   {name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="部署到达芬奇 Edit 目录")
    parser.add_argument("project", nargs="?", help="项目名")
    parser.add_argument("--ui", action="store_true", help="部署 UI 版")
    parser.add_argument("--all", action="store_true", help="同时部署 CLI + UI")
    parser.add_argument("--list", action="store_true", help="列出所有项目")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.list:
        projects = list_projects()
        print("可部署项目:")
        for name, types in projects:
            print(f"  {name} ({'/'.join(types)})")
        return
    
    if not args.project:
        parser.print_help()
        return
    
    deploy(args.project, ui=args.ui or args.all, cli=args.all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
