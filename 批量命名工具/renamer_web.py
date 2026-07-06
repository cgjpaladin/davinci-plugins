"""
批量命名工具 · 极简启动壳（永不修改，差分更新覆盖 app_core.py）
"""
import sys, os

# PyInstaller onedir: _MEIPASS = Contents/Resources，shared/ 在其下
_MEIPASS = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
if _MEIPASS not in sys.path:
    sys.path.insert(0, _MEIPASS)

from shared.app_core import main
main()
