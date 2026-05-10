#!/usr/bin/env python3
# launcher.py — 交付自检 启动器（薄包装 → shared/launcher_router.py）
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from launcher_router import route
route("交付自检工具", ui_module="ui")
