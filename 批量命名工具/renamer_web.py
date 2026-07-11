"""
批量命名工具 · 极简启动壳（永不修改，差分更新覆盖 app_core.py）
"""
import sys, os

# PyInstaller onedir: _MEIPASS = Contents/Resources，shared/ 在其下
_MEIPASS = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 增量覆盖目录（macOS 禁止修改 .app bundle，delta 写入外部目录）
_DELTA_DIR = os.path.expanduser('~/.config/renamer/delta')
if os.path.isdir(_DELTA_DIR):
    # 遍历 delta 子目录插入 sys.path（如 shared/ -> ~/.config/renamer/delta/shared）
    for sub in sorted(os.listdir(_DELTA_DIR)):
        sub_path = os.path.join(_DELTA_DIR, sub)
        if os.path.isdir(sub_path) and sub_path not in sys.path:
            sys.path.insert(0, sub_path)
    # 顶级文件（如 renamer_table.html）通过 PYTHONPATH 注入
    if _DELTA_DIR not in sys.path:
        sys.path.insert(0, _DELTA_DIR)

if _MEIPASS not in sys.path:
    sys.path.insert(0, _MEIPASS)

from shared.app_core import main
main()
