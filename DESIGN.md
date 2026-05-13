# Design System: 达芬奇插件工坊

> 基于 DaVinci Resolve 原生界面风格 + WorkBuddy 现代暗色终端美学
> 目标：所有 Tkinter 工具保持一致的"专业视频编辑软件"质感

---

## 1. 视觉主题

**达芬奇路线**：暗色工具面板，扁平无阴影，高信息密度，橙色作为唯一品牌高亮
**WorkBuddy 路线**：更深黑底色，翠绿/暖灰信号，边界即层级

**混合策略**：主体走达芬奇（橙色、信息密度），暗度走 WorkBuddy（更深一级黑底）

---

## 2. 色彩系统

```python
# 直接复制到你的 Tkinter T = {} 里
T = {
    # 背景层级 (由深到浅)
    "bg":        "#151515",  # 最深底 (比达芬奇的 #1a1a1a 更深一级)
    "surface":   "#1e1e1e",  # 面板/卡片
    "surface2":  "#282828",  # 更高一级面板 (输入框、选中行)

    # 边框 — 达芬奇风格：细线分隔，不用阴影
    "border":    "#3d3d3d",  # 标准边框
    "border_hi": "#555555",  # 强调边框 (hover/active)

    # 文字
    "text":      "#c0c0c0",  # 主文字 (比纯白柔和)
    "text_bright":"#e8e8e8", # 高亮文字
    "text_dim":  "#707070",  # 次要文字/标签

    # 品牌色 — 达芬奇的橙色灵魂
    "accent":    "#e8870a",  # 主高亮 (按钮/选中/焦点)
    "accent_dim":"#8a5000",  # 暗橙色 (选中行背景)

    # 功能色
    "green":     "#6a9a3a",  # 成功/预览/通过
    "red":       "#c04040",  # 错误/NG/警告
    "yellow":    "#c0a040",  # 警告/待处理

    # 占位符
    "placeholder":"#505050",

    # 字体
    "ff_ui":    "Segoe UI",   # UI 文字 (Windows 原生)
    "ff_mono":  "Consolas",   # 等宽 (参数/代码)
}

# CSS 等效 (:root)
"""
:root {
  --bg:        #151515;
  --surface:   #1e1e1e;
  --surface2:  #282828;
  --border:    #3d3d3d;
  --border-hi: #555555;
  --text:      #c0c0c0;
  --text-bright:#e8e8e8;
  --text-dim:  #707070;
  --accent:    #e8870a;
  --accent-dim:#8a5000;
  --green:     #6a9a3a;
  --red:       #c04040;
  --yellow:    #c0a040;
}
"""
```

---

## 3. 排版规则

达芬奇的核心: **小字号 + 高密度**。界面被参数填满，几乎没有"留白"。

| 用途 | 字体 | 大小 | 字重 | 说明 |
|------|------|------|------|------|
| 窗口标题栏 | Segoe UI | 10px | normal | 小字，低调 |
| 参数标签 (Label) | Segoe UI | 8px | bold | 全大写，极紧凑 |
| 输入框文字 | Consolas | 10px | normal | 等宽对齐 |
| 预览文件名 | Consolas | 11-12px | normal | 绿色高亮 |
| 文件列表 | Consolas | 9-10px | normal | 密集列表 |
| 按钮文字 | Segoe UI | 10px | bold | 橙色/灰色 |
| 状态栏 | Segoe UI | 9px | normal | 最底层信息 |
| 弹窗标题 | Segoe UI | 11px | bold | 仅确认/警告时使用 |

### Tkinter 字号对照

```python
# Tkinter 用负数表示磅值（pt），正数表示像素
FONT_TITLEBAR = (T["ff_ui"], 10)       # 窗口标题
FONT_LABEL    = (T["ff_ui"], 8)        # 参数标签
FONT_INPUT    = (T["ff_mono"], 10)     # 输入框
FONT_PREVIEW  = (T["ff_mono"], 11)     # 预览
FONT_LIST     = (T["ff_mono"], 9)      # 文件列表
FONT_BUTTON   = (T["ff_ui"], 10, "bold")  # 按钮
FONT_STATUS   = (T["ff_ui"], 9)        # 状态栏
```

---

## 4. 间距系统

达芬奇的核心: **4px 为基本单位，极紧凑**。

| Token | 值 | 用途 |
|-------|-----|------|
| `gap-xs` | 2px | 同类元素间的微间距 |
| `gap-sm` | 4px | 标准内边距、元素间距 |
| `gap-md` | 6px | 组件组之间的间距 |
| `gap-lg` | 8px | 大区块间距 |
| `pad-x` | 8px | 水平内边距 |
| `pad-y` | 4px | 垂直内边距 (极紧凑) |

```python
# Tkinter padding
PAD_TIGHT = {"padx": 4, "pady": 2}   # 标签/小元素
PAD_NORMAL = {"padx": 8, "pady": 4}  # 输入框/按钮
PAD_SECTION = {"padx": 8, "pady": 6} # 区块间距
```

---

## 5. 圆角系统

达芬奇: **几乎无圆角 (2px)**，棱角分明，工程师感。

| Token | 值 | 用途 |
|-------|-----|------|
| `radius-none` | 0px | 面板、列表 |
| `radius-sm` | 2px | 输入框、按钮 |
| `radius-md` | 4px | 弹窗、卡片 (仅特殊场景) |

---

## 6. 层级 & 深度

达芬奇不用阴影，用**边框 + 颜色深度**区分层级。

| 层级 | 背景色 | 边框 | 用途 |
|------|--------|------|------|
| 0 (底) | `#151515` | 无 | 窗口背景 |
| 1 | `#1e1e1e` | `1px #3d3d3d` | 面板、卡片 |
| 2 | `#282828` | `1px #3d3d3d` | 输入框、选中行 |
| 3 (焦点) | `#282828` | `1px #e8870a` | 聚焦输入框 |

---

## 7. 组件规范

### 按钮

```python
# 主按钮 (橙色, 危险操作)
PRIMARY_BTN = {
    "bg": T["accent"], "fg": "#ffffff",
    "font": FONT_BUTTON, "relief": "flat",
    "borderwidth": 0, "padx": 14, "pady": 4
}

# 次要按钮 (灰色边框, 安全操作)
SECONDARY_BTN = {
    "bg": T["surface"], "fg": T["text_dim"],
    "font": FONT_BUTTON, "relief": "flat",
    "borderwidth": 1, "highlightbackground": T["border"],
    "highlightthickness": 1, "padx": 8, "pady": 2
}

# 禁用按钮
DISABLED_BTN = {
    "bg": "#3d3d3d", "fg": "#707070",
    "font": FONT_BUTTON, "relief": "flat"
}
```

### 输入框

```python
ENTRY_STYLE = {
    "font": FONT_INPUT,
    "fg": "#e0e0e0", "bg": T["surface2"],
    "insertbackground": T["text"],  # 光标颜色
    "relief": "flat", "borderwidth": 1,
    "highlightbackground": T["border"],
    "highlightthickness": 1
}
```

### 下拉框 (Combobox)

```python
# ttk.Combobox 用 style 控制
# 注意：Tkinter 原生 Combobox 很丑，强烈建议用 ttk + clam 主题
COMBO_STYLE = {
    "font": FONT_INPUT,
    "width": 8,
    "state": "readonly"
}
```

### 文件列表 (Treeview)

```python
TREE_STYLE = {
    "bg": T["bg"], "fg": T["text"],
    "fieldbg": T["bg"],  # 空白区域
    "rowheight": 22,     # 行高 (达芬奇风格：极紧凑)
    "font": FONT_LIST,
    "borderwidth": 0
}

# 选中行颜色
TREE_SELECTED_BG = "#2a1800"  # 极暗橙色，不是亮蓝
TREE_SELECTED_FG = T["text_bright"]
```

### 滚动条

```python
# 达芬奇的滚动条几乎不可见，超细
SCROLLBAR_WIDTH = 6  # px，默认是 16-20px
```

---

## 8. 布局原则

### 达芬奇式布局

```
┌─────────────────────────────────────────────┐
│ ● ● ●  批量文件命名工具          v3.0       │ ← 标题栏 (28px高)
├─────────────────────────────────────────────┤
│ Ep ▾  Sc ▾  Gr ▾  Tk ▾  镜头描述 ▾  ...   │ ← 参数区 (单行，紧凑)
├─────────────────────────────────────────────┤
│ ▸ Ep01_Sc03_Gr01_Tk01_全能分镜_v01_OK.mp4  │ ← 预览 Hero
│                             选中 4个  [重命名]│
├─────────────────────────────────────────────┤
│ 文件列表 · 6个              [+文件][+文件夹] │
│ ┃ ▶ Ep01_Sc03_...mp4 ← 镜头001.mp4        │ ← 列表区
│ ┃ ▶ Ep01_Sc03_...mp4 ← 镜头002.mp4        │   (最大区域)
│   ▶ Ep01_Sc03_...mp4 ← 镜头003.mp4        │
├─────────────────────────────────────────────┤
│ ● 就绪 · Ctrl+Z撤销 · Del移除   插件工坊 v3 │ ← 状态栏 (24px)
└─────────────────────────────────────────────┘
```

**关键原则**:
1. 标题栏和状态栏极窄 (24-28px)
2. 参数区单行铺满，不换行
3. 预览区紧凑 (40-50px)
4. 文件列表占剩余全部空间
5. 所有间距 ≤8px

---

## 9. 交互规范

| 交互 | 表现 |
|------|------|
| 按钮 hover | 亮度提升 15%，无缩放 |
| 输入框 focus | 边框变橙色 `#e8870a` |
| 列表行 hover | 背景微亮 `#252525` |
| 列表行选中 | 暗橙色背景 `#2a1800`，左边框 2px 橙色 |
| 列表行选中 + hover | 同选中 (不叠加) |
| 按钮点击 | 瞬间变暗 10%，无动画 |
| 弹窗 | 背景 `#1e1e1e`，边框 1px `#3d3d3d` |

---

## 10. Do's & Don'ts

### ✅ DO
- 用 8px 以内的间距，信息要"塞满"
- 所有输入框等宽字体，数字对齐
- 橙色只用于：按钮、焦点、选中状态——不要滥用
- 1px 细边框分隔，不要用阴影
- 状态栏放最底层信息，用 9px 小字
- 标题栏放窗口控制点和标题，28px 以内

### ❌ DON'T
- 不要用大圆角 (>4px)
- 不要加阴影/投影
- 不要用亮色背景 (白/浅灰)
- 不要用大字号 (>12px) 做 UI 文字
- 不要用超过 3 种颜色 (除了语义色)
- 不要留大面积空白
- 不要用系统默认的 Tkinter 样式 (蓝色选中条、凸起按钮)
- 不要让按钮之间有超过 4px 的间距

---

## 11. 快速上手：复制即用

### Python Tkinter 快速启动模板

```python
"""我的工具 - 达芬奇风格"""
import tkinter as tk
from tkinter import ttk

# ═══ 设计 Token ═══
T = {
    "bg":"#151515","surface":"#1e1e1e","surface2":"#282828",
    "border":"#3d3d3d","border_hi":"#555555",
    "text":"#c0c0c0","text_bright":"#e8e8e8","text_dim":"#707070",
    "accent":"#e8870a","accent_dim":"#8a5000",
    "green":"#6a9a3a","red":"#c04040","placeholder":"#505050",
    "ff_ui":"Segoe UI","ff_mono":"Consolas",
}

# ═══ 窗口 ═══
root = tk.Tk()
root.title("我的工具")
root.geometry("700x480")
root.minsize(500, 320)
root.configure(bg=T["bg"])

# ═══ ttk 样式 ═══
style = ttk.Style()
style.theme_use("clam")  # 必须用 clam，其他主题太丑

style.configure("App.TFrame", background=T["bg"])
style.configure("Surface.TFrame", background=T["surface"])
style.configure("Title.TLabel",
    background=T["surface"], foreground=T["text_dim"],
    font=(T["ff_ui"], 10))
style.configure("Param.TLabel",
    background=T["bg"], foreground=T["text_dim"],
    font=(T["ff_ui"], 8))
style.configure("Status.TLabel",
    background=T["bg"], foreground=T["text_dim"],
    font=(T["ff_ui"], 9))

# ═══ 标题栏 ═══
titlebar = ttk.Frame(root, style="Surface.TFrame")
titlebar.pack(fill="x")
ttk.Label(titlebar, text="  我的工具", style="Title.TLabel").pack(side="left")

# ═══ 参数区 ═══
params = ttk.Frame(root, style="App.TFrame")
params.pack(fill="x", padx=8, pady=(4, 0))

for label in ["Ep 集数", "Sc 场次", "Gr 小场", "Tk 次数"]:
    col = ttk.Frame(params, style="App.TFrame")
    col.pack(side="left", fill="x", expand=True, padx=2)
    ttk.Label(col, text=label, style="Param.TLabel").pack(anchor="w")
    e = tk.Entry(col,
        font=(T["ff_mono"], 10), fg="#e0e0e0", bg=T["surface2"],
        relief="flat", borderwidth=1,
        highlightbackground=T["border"], highlightthickness=1)
    e.pack(fill="x")

# ═══ 主要操作区 ═══
hero = ttk.Frame(root, style="Surface.TFrame")
hero.pack(fill="x", padx=8, pady=(4, 0))

ttk.Label(hero,
    text="▸ 预览文件名将显示在这里",
    background=T["surface"], foreground=T["green"],
    font=(T["ff_mono"], 11)).pack(side="left", padx=8, pady=6)

btn = tk.Button(hero,
    text="执行操作", bg=T["accent"], fg="#ffffff",
    font=(T["ff_ui"], 10, "bold"), relief="flat", borderwidth=0,
    padx=14, pady=4, cursor="hand2")
btn.pack(side="right", padx=6, pady=6)

# ═══ 内容区 (Treeview) ═══
content = ttk.Frame(root, style="App.TFrame")
content.pack(fill="both", expand=True, padx=8, pady=(4, 0))

tv = ttk.Treeview(content, columns=("c1","c2"), show="headings", height=12)
tv.heading("c1", text="新文件名"); tv.heading("c2", text="原文件名")
tv.column("c1", width=300); tv.column("c2", width=200)

# Treeview 样式 — 达芬奇暗色
style.configure("Treeview",
    background=T["bg"], foreground=T["text"],
    fieldbackground=T["bg"], rowheight=22,
    font=(T["ff_mono"], 9), borderwidth=0)
style.configure("Treeview.Heading",
    background=T["surface"], foreground=T["text_dim"],
    font=(T["ff_ui"], 9), borderwidth=0)
style.map("Treeview",
    background=[("selected", "#2a1800")],
    foreground=[("selected", T["text_bright"])])

tv.pack(side="left", fill="both", expand=True)

# 滚动条 (极细)
sb = ttk.Scrollbar(content, orient="vertical", command=tv.yview)
tv.configure(yscrollcommand=sb.set)
sb.pack(side="right", fill="y")

# ═══ 状态栏 ═══
status = ttk.Frame(root, style="App.TFrame")
status.pack(fill="x", padx=8, pady=(2, 3))
ttk.Label(status, text="● 就绪", style="Status.TLabel").pack(side="left")
ttk.Label(status, text="达芬奇插件工坊",
    style="Status.TLabel", foreground="#555").pack(side="right")

root.mainloop()
```

---

## 12. 浏览器原型设计流程

```
1. 在 design-a-davinci.html 里用 DevTools (Cmd+Option+I) 调 CSS 变量
2. 调满意后复制 :root {} 整段
3. 把颜色值复制到 Python T = {} 字典
4. Tkinter 用这些值配置 style / tk widget
```

---

*Design System v1.0 — 达芬奇插件工坊*
*更新: 2026-05-13*
