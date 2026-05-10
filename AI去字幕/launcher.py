#!/usr/bin/env python3
# launcher.py — AI去字幕 启动器（薄包装 → shared/launcher_router.py）
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from launcher_router import route
route("AI去字幕", ui_module="stable_ui")
