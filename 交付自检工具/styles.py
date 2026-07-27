# -*- coding: utf-8 -*-
"""UI 样式常量：字体 / 间距 / 尺寸 / 按钮样式。被 ui.py + config_dialog.py 共用。"""

FONT_H1 = "font-size:13px"
FONT_H2 = "font-size:15px"
FONT_BODY = "font-size:12px"
FONT_SM = "font-size:11px"
FONT_XS = "font-size:10px"
FONT_DIV = "font-size:18px"
FONT_BOLD = "font-weight:bold"

SPACE_NONE = 0
SPACE_TIGHT = 2
SPACE_COMPACT = 3
SPACE_SM = 4
SPACE_NORMAL = 6
SPACE_RELAXED = 8
SPACE_WIDE = 10

SIZE_BTN_H = 20
SIZE_BTN_SM_W = 28
SIZE_BTN_MD_W = 60
SIZE_BTN_LG_W = 84
SIZE_BTN_XL_W = 100
SIZE_BTN_XL_H = 95
SIZE_TOGGLE = [44, 22]
SIZE_LINE_H = 22
SIZE_CHECK_W = 28
SIZE_GAP_TINY = [8, 0]
SIZE_GAP_SM = [20, 0]

PAD_BTN = "padding:2px 8px"
PAD_PANEL = "padding:4px 10px"
PAD_PANEL_WIDE = "padding:4px 12px"

RAD_BTN = "3px"
RAD_PANEL = "4px"
DIVIDER_BARS = 6

# ── 复合样式 ──
STYLE_HEADING = "font-size:15px;font-weight:bold;color:#fff"
STYLE_ACCENT = f"{FONT_H2};{FONT_BOLD};color:#ccc"
STYLE_DIM = f"color:rgb(130,130,130);font-size:{FONT_XS}"
STYLE_HINT = f"color:rgb(130,130,130);{FONT_XS}"
STYLE_FOOTER = f"color:rgb(100,100,100);{FONT_XS}"
STYLE_DIVIDER = f"{FONT_DIV};color:#666"
STYLE_CHECK_ROW = f"{FONT_H1};color:rgb(220,220,220)"
STYLE_WARN = f"color:red;{FONT_BODY}"

# ── 按钮样式 ──
BTN_STYLE = (
    "QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
BTN_ICON = (
    "QPushButton{max-height:20px;max-width:24px;background-color:transparent;color:rgb(150,150,150);"
    "border:1px solid transparent;border-radius:3px;padding:0px}"
    "QPushButton:hover{background-color:rgb(60,60,60);color:rgb(220,220,220)}"
)
BTN_STYLE_SM = (
    "QPushButton{max-height:22px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:2px 8px;text-align:left}"
    "QPushButton:hover{background-color:rgb(72,72,72)}"
    "QPushButton:pressed{background-color:rgb(45,45,45)}"
)
BTN_PRIMARY = (
    "QPushButton{max-height:28px;background-color:rgb(50,120,220);color:rgb(255,255,255);"
    "border:1px solid rgb(70,140,240);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(65,135,235)}"
    "QPushButton:pressed{background-color:rgb(40,100,200)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
BTN_DANGER = (
    "QPushButton{max-height:28px;background-color:rgb(200,50,50);color:rgb(255,255,255);"
    "border:1px solid rgb(220,70,70);border-radius:4px;padding:4px 12px;font-weight:bold}"
    "QPushButton:hover{background-color:rgb(220,65,65)}"
    "QPushButton:pressed{background-color:rgb(160,40,40)}"
    "QPushButton:disabled{color:rgb(100,100,100);background-color:rgb(40,40,40)}"
)
