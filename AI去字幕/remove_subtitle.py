#!/usr/bin/env python3
"""
remove_subtitle.py — 达芬奇 AI 去字幕插件

双入口：
  人类入口: 达芬奇 Workspace → Scripts → remove_subtitle
  AI入口:   python3 remove_subtitle.py --mode pro_box --dry-run --report-json report.json

Pipeline 逻辑已迁移至 pipeline.py (SubtitlePipeline → BasePipeline)
此文件仅保留 CLI 参数解析和入口调度。
"""

import argparse
import os
import sys

# 路径初始化
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)
_shared_root = os.path.join(os.path.dirname(_plugin_root), 'shared')
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

_RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if _RESOLVE_MODULES not in sys.path:
    sys.path.append(_RESOLVE_MODULES)

from config import (
    DEFAULT_MODE, __version__, version_string,
    PLUGIN_DIR, SMB_MOUNT,
)
from interface import CLIPipelineUI
from logger import title, step, ok, warn, fail, info

# ── 环境自检（CLI --check 模式用）──

def _run_env_checks() -> dict:
    """环境自检：SMB挂载/API Key/OSS凭证/达芬奇。"""
    from config import WUHENAI_V2_API_KEY, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
    return {
        "SMB 挂载": os.path.exists(SMB_MOUNT),
        "API Key (无痕AI 2.1)": bool(WUHENAI_V2_API_KEY),
        "OSS 凭证 (阿里云)": bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET),
        "达芬奇运行": os.path.exists("/Applications/DaVinci Resolve"),
    }


# ── Pipeline 入口（CLI）──

def run_pipeline(mode: str = None, dry_run: bool = False, force: bool = False,
                 scan_only: bool = False, report_json: str = "",
                 project_root: str = "") -> dict:
    """执行完整去字幕流程。内部委托给 SubtitlePipeline。"""

    from pipeline import SubtitlePipeline

    # CLI 停止信号：检查 SMB .stop 文件 或 本地 /tmp stop 文件
    stop_file = os.path.join(PLUGIN_DIR, ".stop")
    local_stop = os.path.join("/tmp", f"ai_subtitle.stop.{os.uname().nodename}")

    pipeline = SubtitlePipeline()
    return pipeline.run(
        ui=CLIPipelineUI(),
        mode=mode or DEFAULT_MODE,
        project_root=project_root,
        dry_run=dry_run,
        force=force,
        scan_only=scan_only,
        report_json=report_json,
        stop_check=lambda: os.path.exists(stop_file) or os.path.exists(local_stop),
    )


# ── 入口 ──

def main():
    """双入口：无参数=达芬奇菜单入口；有参数=CLI 开发者模式。"""
    if len(sys.argv) == 1 and sys.argv[0].endswith(".py"):
        info("请通过 AI去字幕 UI 使用，或传 --project-root 参数")
        return

    parser = argparse.ArgumentParser(
        description=f"AI 去字幕 v{version_string()}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python3 remove_subtitle.py --dry-run --report-json report.json\n"
               "  python3 remove_subtitle.py --mode basic --force"
    )
    parser.add_argument("--mode", choices=["basic", "pro_box"], default=DEFAULT_MODE,
                        help=f"处理模式 (默认: {DEFAULT_MODE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="完整诊断但不调 API，不花钱")
    parser.add_argument("--scan-only", action="store_true",
                        help="仅扫描 IO，不调 API")
    parser.add_argument("--force", action="store_true",
                        help="跳过可复用片段，强制重新处理")
    parser.add_argument("--report-json", default="",
                        help="结构化报告输出路径")
    parser.add_argument("--check", action="store_true",
                        help="仅环境自检 (SMB/API/OSS/DVR)，不处理")
    parser.add_argument("--project-root", default="",
                        help="项目根目录（含04_素材的文件夹），AI 传入，不推断")
    args = parser.parse_args()

    # ── 仅环境自检 ──
    if args.check:
        checks = _run_env_checks()
        title("🔍 环境自检")
        all_ok = True
        for name, ok_flag in checks.items():
            (ok if ok_flag else fail)(f"{name}: {'✅' if ok_flag else '❌'}")
            if not ok_flag:
                all_ok = False
        if all_ok:
            ok("全部通过 ✅")
        else:
            warn("存在问题，请先修复")
        return

    try:
        run_pipeline(
            mode=args.mode,
            dry_run=args.dry_run,
            force=args.force,
            scan_only=args.scan_only,
            report_json=args.report_json,
            project_root=args.project_root,
        )
    except Exception as e:
        fail(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
