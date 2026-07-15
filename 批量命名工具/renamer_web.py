"""
批量命名工具 · 极简启动壳（永不修改，差分更新覆盖 app_core.py）
"""
import sys, os

_MEIPASS = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 先注册 bundle 路径，再叠加 delta——这样 delta 排在 sys.path 更前面，真正覆盖 Python 文件
if _MEIPASS not in sys.path:
    sys.path.insert(0, _MEIPASS)

# 增量覆盖目录
_DELTA_DIR = os.path.expanduser('~/.config/renamer/delta')
if os.path.isdir(_DELTA_DIR):
    for sub in sorted(os.listdir(_DELTA_DIR)):
        sub_path = os.path.join(_DELTA_DIR, sub)
        if os.path.isdir(sub_path) and sub_path not in sys.path:
            sys.path.insert(0, sub_path)
    if _DELTA_DIR not in sys.path:
        sys.path.insert(0, _DELTA_DIR)

from app_core import main
main()
