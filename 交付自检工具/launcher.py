#!/usr/bin/env python3
# launcher.py — 交付自检 启动器（薄包装 → shared/launcher_router.py）
import sys, os
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', 'shared'))
sys.path.insert(0, '/Volumes/MYJC/06_Software/达芬奇脚本/shared')
from launcher_router import route
route("交付自检工具", ui_module="ui")
