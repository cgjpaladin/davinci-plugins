"""
主题引擎 — 从 theme.json 生成 UIManager QSS 和 HTML CSS
所有工具统一 import 即可
"""
import json
import os

_THEME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.json")

with open(_THEME_FILE, "r") as f:
    _t = json.load(f)

C = _t["colors"]
F = _t["fonts"]
S = _t["spacing"]
R = _t["radius"]


def qss() -> str:
    """为 UIManager 窗口生成暗色 QSS 样式表"""
    return f"""
* {{ color: {C['text']}; }}
QWidget {{ background: {C['bg']}; }}

QLabel {{
    font-size: {F['size_body']};
    font-family: "{F['ui'].split(',')[0].strip().strip("'")}";
}}

QLineEdit {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    border-radius: {R['sm']};
    padding: 3px 5px;
    font-size: {F['size_body']};
    color: {C['text_bright']};
    font-family: "{F['mono'].split(',')[0].strip().strip("'")}";
}}
QLineEdit:focus {{ border-color: {C['accent']}; }}

QComboBox {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    border-radius: {R['sm']};
    padding: 3px 5px;
    font-size: {F['size_body']};
    color: {C['text_bright']};
}}
QComboBox:focus {{ border-color: {C['accent']}; }}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox QAbstractItemView {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    color: {C['text']};
    selection-background-color: {C['accent_dim']};
}}

QPushButton {{
    border: none; border-radius: {R['sm']};
    padding: 6px 14px; font-size: {F['size_body']};
    font-weight: bold;
}}

QTreeView {{
    background: {C['bg']}; color: {C['text']};
    border: none; font-size: 9px;
    font-family: "{F['mono'].split(',')[0].strip().strip("'")}";
}}
QTreeView::item:selected {{
    background: {C['accent_dim']};
}}

QScrollBar:vertical {{
    background: transparent; width: 5px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']}; border-radius: 3px; min-height: 20px;
}}
"""


def css_vars() -> str:
    """生成 HTML :root CSS 变量块"""
    lines = [":root {"]
    for k, v in C.items():
        lines.append(f"  --{k}: {v};")
    for k, v in F.items():
        lines.append(f"  --font-{k}: {v};")
    for k, v in S.items():
        lines.append(f"  --{k}: {v};")
    for k, v in R.items():
        lines.append(f"  --radius-{k}: {v};")
    lines.append("}")
    return "\n".join(lines)


# 快捷：直接可 import 使用的颜色字典
bg = C["bg"]
surface = C["surface"]
surface2 = C["surface2"]
border = C["border"]
text = C["text"]
text_dim = C["text_dim"]
accent = C["accent"]
green = C["green"]
