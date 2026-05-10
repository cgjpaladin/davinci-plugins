#!/usr/bin/env python3
# launcher.py — AI去字幕 启动器（薄包装 → shared/launcher_router.py）
import sys, os
_here = os.path.dirname(os.path.abspath(__file__))
# 本地开发：../shared → 达芬奇插件工坊/shared/
# 部署后：  从 SMB shared/ 加载
sys.path.insert(0, os.path.join(_here, '..', 'shared'))
sys.path.insert(0, '/Volumes/MYJC/06_Software/达芬奇脚本/shared')
from launcher_router import route
route("AI去字幕", ui_module="stable_ui")
