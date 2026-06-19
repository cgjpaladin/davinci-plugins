---
name: davinci-ui
description: 达芬奇 UIManager 完整开发指南。包含窗口创建、控件速查、TabBar+Stack、进度条、样式、已知坑位、37 条预检规则。触发词：达芬奇UI、UIManager、窗口、按钮、控件、界面、弹窗。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
> 本 skill 是 `达芬奇脚本开发` 的子 skill。加载前确保已加载主 skill。

# 达芬奇 UI 开发指南 + 预检规则

**来源**：BMD 官方 UIManager 文档 + Batch_io_Pro v2.0.4 + HEIBA Sub Editor/TTS 源码 + We Suck Less 论坛。UIManager 底层是 Qt。仅 Studio 版可用。

## 目录
1. [初始化与窗口创建](#初始化)
2. [控件速查](#控件速查)
3. [TabBar+Stack](#tabbar--stack-多页面切换)
4. [进度条](#进度条--两种方案)
5. [布局规则](#布局规则)
6. [已知坑位](#ui-已知坑位)
7. [内部 vs 外部环境](#内部-vs-外部-python-环境)
8. [37 条预检规则](#预检规则)

## 初始化

```python
import DaVinciResolveScript as bmd
fusion = bmd.scriptapp('Fusion')
ui = fusion.UIManager
disp = bmd.UIDispatcher(ui)
```

> ⚠️ **外部 subprocess 插件注意**：`ui.FindWindow()` 仅在**同一 dispatcher** 内有效，跨进程找不到另一进程的窗口。去重用 `subprocess.run(["pgrep", "-f", "ui_script.py"])` 或文件锁。

## 窗口创建

```python
win = disp.AddWindow({
    'WindowTitle': 'AI 去字幕',
    'ID': WIN_ID,
    'Geometry': [800, 500,   # 屏幕坐标 x, y
                 600, 400],  # 窗口宽, 高
    'WindowFlags': {
        'Window': True,
        'WindowStaysOnTopHint': True,
    },
}, [
    ui.VGroup({'Spacing': 10}, [
        ui.Label({'ID': 'label_title', 'Text': '选择去字幕选项'}),
        ui.HGroup({'Spacing': 10}, [
            ui.Button({'ID': 'btn_run', 'Text': 'Run', 'Weight': 7}),
            ui.Button({'ID': 'btn_cancel', 'Text': '取消', 'Weight': 0}),
        ]),
    ]),
])

itm = win.GetItems()  # 获取所有控件引用

# 事件绑定
def _exit(ev):
    disp.ExitLoop()
win.On[WIN_ID].Close = _exit

def _on_run(ev):
    print("执行去字幕...")
win.On['btn_run'].Clicked = _on_run

# 主循环
win.Show()
disp.RunLoop()
win.Hide()
```

### 窗口级全局 StyleSheet（来自 HEIBA）

```python
win = disp.AddWindow({
    'ID': WIN_ID,
    'StyleSheet': '*{font-size:14px;}',  # 窗口级全局字体
    ...
}, layout)
```
HEIBA Sub Editor 和 TTS 都在 Window 属性上设全局 `StyleSheet`，避免逐控件重复设置。

### Dialog 模态弹窗

```python
dlg = disp.AddDialog({'ID': 'myDialog'}, [ui.Label({'Text': '提示'})])
dlg.Exec()  # 模态执行，阻塞直到 Done()
```
官方文档确认 `Dialog` 支持 `Exec()` / `IsRunning()` / `Done()`。

## 控件速查

| 控件 | 创建 | 取值/设置 | 事件 |
|------|------|----------|------|
| Button | `ui.Button({'ID':'btn', 'Text':'运行'})` | — | `.On['btn'].Clicked` |
| ComboBox | `ui.ComboBox({'ID':'cb', 'Weight':7})` | `.AddItem()` / `.AddItems(list)` / `.CurrentText` | `.On['cb'].CurrentIndexChanged` |
| CheckBox | `ui.CheckBox({'ID':'chk', 'Text':'启用'})` | `.Checked` (bool) | `.On['chk'].Clicked` |
| LineEdit | `ui.LineEdit({'ID':'le', 'PlaceholderText':'输入路径'})` | `.Text` / `.GetText()` | `.On['le'].TextChanged` |
| SpinBox | `ui.SpinBox({'ID':'sp', 'Minimum':0, 'Maximum':100})` | `.Value` | `.On['sp'].ValueChanged` |
| Label | `ui.Label({'ID':'lb', 'Text':'标题'})` | `.Text` | — |
| Tree | `ui.Tree({'ID':'tree', 'Weight':0.5})` | `.NewItem()` → `.AddTopLevelItem()` / `.AddTopLevelItems(list)` | `.On['tree'].ItemClicked` |
| TabBar + Stack | 见下方详细说明 | | `.On[tab_id].CurrentChanged` |
| ProgressBar (自制) | Label Resize / Stack 叠加 | 见下方 | — |
| VGroup/HGroup | `ui.VGroup({'Spacing':5}, [...])` | 布局容器。**不支持滚动**，内容超出窗口高度会被截断 | — |
| HGap/VGap | `ui.HGap({'Spacing':20})` | 占位间隔 | — |

### 滚动能力（2026-06-13 实测验证 v20.3.2）

**UIManager 没有通用的 ScrollArea 控件。** 实测 `dir(UIManager)` 返回 15 个 Widget 类，0 个含 `scroll` 的属性。`ScrollArea` / `ScrollWidget` / `ScrollView` 全部不存在。

| 控件 | 自带滚动 | 滚动属性/方法 |
|------|:--:|------|
| TextEdit | ✅ | 内容超出自动滚动；`ScrollToAnchor()`、`MoveCursor()`+`EnsureCursorVisible()` |
| Tree | ✅ | `HorizontalScrollMode`、`VerticalScrollMode`、`ScrollToItem(item)`、`ScrollToBottom()` |
| VGroup/HGroup | ❌ | 无滚动，溢出被截断 |
| Label | ❌ | 无滚动，文本超出不显示 |

**结论**：
- 列表型滚动 → 用 **Tree**（HEIBA 字幕编辑器原型：`Tree + VerticalScrollMode + ScrollToItem`，几十行可滚）
- 文本型滚动 → 用 **TextEdit**（我们的日志区就是这样）
- 整个窗口内容过多需要滚动 → **做不到**，只能分 Tab 或用弹窗

### 批量构建方法（来自 Batch_io_Pro / BMD 官方文档）

```python
# ComboBox 批量添加
itm[cb].AddItems(["选项A", "选项B", "选项C"])  # 替代 for 循环逐条 AddItem

# Tree 批量添加行
rows = [tree.NewItem() for _ in items]
# 逐行设 Text[0], Text[1]...
reso_tree.AddTopLevelItems(rows)  # 一次加完
```

### 完整事件列表（来自 BMD 官方文档）

> 非默认事件需 `'Events': { 'EventName': True }` 显式启用。

| 控件 | 默认事件 | 扩展事件（默认关） |
|------|---------|-----------------|
| Button | Clicked | Toggled, Pressed, Released |
| CheckBox | Clicked | Toggled |
| ComboBox | CurrentIndexChanged | TextEdited, EditingFinished, ReturnPressed, CurrentTextChanged, Activated |
| SpinBox | ValueChanged | EditingFinished |
| Slider | ValueChanged | SliderMoved, SliderPressed, SliderReleased, ActionTriggered, RangeChanged |
| LineEdit | TextChanged | EditingFinished, ReturnPressed, TextEdited, SelectionChanged, CursorPositionChanged |
| TextEdit | TextChanged | SelectionChanged, CursorPositionChanged |
| ColorPicker | ColorChanged | — |
| TabBar | CurrentChanged | CloseRequested, TabMoved, TabBarClicked, TabBarDoubleClicked |
| Tree | ItemClicked, CurrentItemChanged | ItemDoubleClicked, ItemExpanded, ItemCollapsed, ItemPressed, ItemActivated, ItemEntered, ItemChanged, ItemSelectionChanged |
| Window | Close, Show | Resize, Hide, MousePress, MouseRelease, MouseDoubleClick, MouseMove, Wheel, KeyPress, KeyRelease, FocusIn, FocusOut, ContextMenu, Enter, Leave |

```python
# 启用非默认事件
ui.Button({'ID':'btn', 'Events': {'Pressed': True, 'Released': True}})
win.On['btn'].Pressed = lambda ev: print('down')
win.On['btn'].Released = lambda ev: print('up')
```

### 实用属性（来自 BMD 官方文档）

| 控件 | 属性 | 用途 |
|------|------|------|
| Label | `WordWrap`, `Alignment`, `Indent`, `Margin` | 文本自动换行 / 对齐 / 缩进 |
| Button | `Checkable`, `Checked`, `Down`, `Flat` | 切换按钮模式 / 无边框样式 |
| ComboBox | `Editable`, `Count`, `CurrentIndex`, `CurrentText` | 用户可输入 / 项数 |
| Window | `WindowOpacity` | 窗口透明度 |
| TabBar | `TabText[i]`, `TabToolTip[i]`, `TabTextColor[i]` | 动态改选项卡文本/颜色 |
| TreeItem | `Selected`, `Expanded`, `Hidden`, `Disabled` | 行状态控制 |
| TreeItem | `Text[i]`, `Icon[i]`, `TextColor[i]`, `BackgroundColor[i]`, `TextAlignment[i]`, `CheckState[i]`, `Font[i]` | 行内容/样式 |

> ⚠️ `TreeItem.TextColor[i]` 和 `BackgroundColor[i]`：BMD 官方文档明确列出，但 v20.3.2 实测不渲染。可能为 v20 版本回归 bug，建议随版本升级重新验证。

### 实用方法（来自 BMD 官方文档 + 实测）

| 控件 | 方法 | 用途 | 实测 |
|------|------|------|------|
| ComboBox | `AddItems(list)`, `InsertItems(int,list)` | 批量添加/插入 | ✅ Batch_io_Pro |
| ComboBox | `InsertSeparator(n)` | 加分隔线 | ✅ |
| ComboBox | `ShowPopup()`, `HidePopup()` | 控制下拉 | ⚠️ |
| ComboBox | `Count()` | 获取项数（方法非属性） | ✅ |
| TextEdit | `InsertHTML(s)` | HTML 格式化文本 | ✅ |
| TextEdit | `ScrollToAnchor(anchor)` | 滚动到锚点（BMD 文档） | ⚠️ 未实测 |
| Tree | `AddTopLevelItems(list)` | 批量添加行 | ✅ Batch_io_Pro |
| Tree | `SelectedItems()` | 多选列表 | ⚠️ |
| Tree | `SortItems(col, order)`, `FindItems(s, flags, col)` | 排序/搜索 | ⚠️ |
| Tree | `ScrollToItem(item)` | 滚动到指定行 | ⚠️ |
| TreeItem | `AddChild()`, `RemoveChild()` | 树层级操作 | ⚠️ |

### Timer 控件 + 多路复用模式（来自 HEIBA）

> Timer 事件绑定在 **dispatcher 级别**：`disp['On']['Timeout']`，非 `win.On[timer_id].Timeout`。

```python
tmr = ui.Timer({'ID': 'myTimer', 'Interval': 1000})  # ms
tmr.Start()
```

**HEIBA TTS 的多 Timer 路由模式**（13596 行商业插件验证）：
```python
# 多个 Timer 共享 disp.On.Timeout，通过 ev.who 区分
def on_timeout(ev):
    who = ev.get('who') or ev.get('ID') or ev.get('Name')
    if who == 'PlayheadTimer':
        follow_playhead()
    elif who == 'PreviewTimer':
        update_preview()

disp['On']['Timeout'] = on_timeout

playhead_tmr = ui.Timer({'ID': 'PlayheadTimer', 'Interval': 100})
preview_tmr = ui.Timer({'ID': 'PreviewTimer', 'Interval': 500, 'TimerType': 'CoarseTimer'})
```

属性：`Interval`(ms), `Singleshot`, `RemainingTime`, `IsActive`, `TimerType`
方法：`Start()`, `Stop()`

## TabBar + Stack 多页面切换

```python
class Tabs:
    def __init__(self):
        self.tabs = 'MyTabs'
        self.stack = 'MyStack'
        self.win = None
        self.items = None

    def get_ui(self):
        return ui.VGroup({'Weight': 0}, [
            ui.TabBar({'Weight': 0, 'ID': self.tabs}),
            ui.Stack({'Weight': 1.0, 'ID': self.stack}, [
                ui.HGroup([ui.Label({'Text': '页面1内容'})]),
                ui.HGroup([ui.Label({'Text': '页面2内容'})]),
            ]),
        ])

    def on_tab_change(self, ev):
        self.items[self.stack].CurrentIndex = ev['Index']
        if self.win:
            self.win.RecalcLayout()

    def connect(self, window):
        self.win = window
        self.items = window.GetItems()
        tab = self.items[self.tabs]
        tab.AddTab('选项A')
        tab.AddTab('选项B')
        self.items[self.stack].CurrentIndex = 0  # ⚠️ 默认 -1，必须手动设 0
        window.On[self.tabs].CurrentChanged = self.on_tab_change

# 关键陷阱：
# - 同一个类实例！Tabs().get_ui() 和 Tabs().connect(win) 用不同实例 → 事件失效
# - CurrentIndex 默认 -1，必须手动设为 0
# - HEIBA 实测：切换页面后需要 RecalcLayout()
```

## 进度条 — 两种方案

### 方案A：Label + Resize + Update（简单，AI去字幕 在用）

```python
# 布局 — ⚠️ 不要在构造里设 Visible: False（崩溃），运行时设
ui.Label({'ID': 'pg_bar',
          'StyleSheet': 'min-height:8px;max-height:8px;background-color:rgb(102,221,39)',
          'MinimumSize': [0, 8]}),

# 初始化时隐藏
itm['pg_bar'].Visible = False

# 更新
def update_progress(ratio, itm):
    bar_w = max(2, int(max_width * ratio))
    itm['pg_bar'].Resize([bar_w, 8])
    itm['pg_bar'].Visible = ratio > 0.005
    itm['pg_bar'].Update()
```

### 方案B：Stack 叠加（视觉更好，Batch_io_Pro 在用）

```python
# 布局 — ⚠️ 不要在构造里设 Visible: False（崩溃），运行时设
ui.Stack({'ID': 'pg_stack'}, [
    ui.Label({'ID': 'pg_bg',
              'StyleSheet': 'max-height:3px; background-color:rgb(37,37,37)'}),
    ui.Label({'ID': 'pg_bar',
    ui.Label({'ID': 'pg_bg',
              'StyleSheet': 'max-height:3px; background-color:rgb(37,37,37)'}),
    ui.Label({'ID': 'pg_bar',
              'StyleSheet': 'max-height:3px; background-color:rgb(102,221,39)'}),
])

# 初始化时隐藏
itm['pg_stack'].Visible = False

# 更新：只 Resize 前景条
def update_progress(ratio, itm):
    total_w = int(itm['pg_stack'].GetGeometry().get(3, 600))
    itm['pg_bar'].Resize([int(total_w * ratio), 3])
    itm['pg_bar'].Visible = ratio > 0
```

⚠️ **进度条不要用 `FixedSize`**——会锁死窗口最小宽度。

## 自定义按钮颜色（来自 Batch_io_Pro）

```python
def color_button_style(r, g, b):
    r, g, b = int(r/2)*2, int(g/2)*2, int(b/2)*2
    return (f"QPushButton {{max-height:16px; max-width:72px; "
            f"color:rgb(0,0,0); background-color:rgb({r},{g},{b}); "
            f"border:1px solid black; border-radius:8px}}")

itm['btn_color'].StyleSheet = color_button_style(255, 100, 50)
```

## 弹窗子窗口（Popup 模式）

```python
popup = disp.AddWindow({
    'WindowTitle': '选择项',
    'ID': 'popup_win',
    'WindowFlags': {'Popup': True},
    'Geometry': [parent_x, parent_y, 200, 400],
}, [ui.VGroup([...])])

def _on_select(ev):
    disp.ExitLoop()

popup.On[widget_id].Clicked = _on_select
popup.Show()
disp.RunLoop()  # 阻塞直到 ExitLoop()
popup.Hide()
```

## 文件/目录选择对话框

```python
# 文件选择 — Fusion 原生，零子进程，零 Dock 图标
path = fu.RequestFile()

# 目录选择
path = fu.RequestDir()
```

> 优先用这两个，不用 tkinter 子进程。macOS 上 tkinter 子进程会在 Dock 产生独立图标。

## UI 设计原则

1. **去重**（外部 subprocess）：用 `pgrep -f` 检查同名脚本是否已运行。`FindWindow` 仅同一 dispatcher 内有效。
2. **事件循环**：所有 UI 必须在 `disp.RunLoop()` 内运行，`disp.ExitLoop()` 退出
3. **关闭事件**：必须绑定 `win.On[WIN_ID].Close = _exit`
4. **控件引用**：`itm = win.GetItems()` 后用 `itm['ID']` 访问
5. **样式**：`StyleSheet` 使用 Qt 子集，不是完整 CSS。可设窗口级全局 `StyleSheet: '*{font-size:14px;}'`
6. **平台**：同一套代码在 Win/Mac 均可用
7. **布局**：靠 `Weight` + `Spacing` 控制比例，`FixedSize` / `MinimumSize` 仅作最后手段
8. **🚫 纯鼠标交互**：不设 `"Default": True` 按钮、不绑快捷键。剪辑师手指在剪辑键盘上，误触风险高。
9. **批量构建**：`AddItems(list)` / `AddTopLevelItems(list)` 优于 for 循环逐条添加

## UI 已知坑位

| 坑 | 现象 | 解决 |
|----|------|------|
| Edit 脚本目录无 DaVinciResolveScript | `ModuleNotFoundError` | `sys.path.append(RESOLVE_MODULES)` 放在所有 import 之前 |
| Stack 构造时 `"Visible": False` | 崩溃 (ScriptSymbolD0Ev) | 去掉构造时的 Visible，运行时用 `.Visible = True/False` |
| Label 构造时 `"Visible": False` | 同上 | 同上 |
| 从 SMB 加载脚本 | `__file__` 路径可能异常 | launcher 已处理 path，模块内不要操作 `__file__` |
| `GetGeometry()` 返回值 | 返回 **dict** `{1:x, 2:y, 3:w, 4:h}`，不是 list | 用 `geo.get(3, 0)` 取宽度，`geo.get(4, 0)` 取高度 |
| `qproperty-alignment:AlignRight` (StyleSheet) | 不生效 | 用 HTML：`"<div align='right'>文本</div>"` |
| TreeItem `BackgroundColor[i]` / `TextColor[i]` | v20.3.2 不渲染或文字消失 | BMD 官方文档支持，可能为 v20 回归。用纯文字分隔（空行、缩进）替代 |
| `_ui_pending` 存储格式化值 | 主线程直接设原始文本，丢失 HTML 对齐 | 存完整的最终格式化字符串 |
| ReplaceClip 颜色重置 | 同一 MediaPoolItem 的所有 TimelineItem 颜色被重置 | 扫描时收集 `alt_tl_items`，ReplaceClip 后批量恢复 |
| VGroup/HGroup 内容超出 | 窗口大小固定，溢出内容被截断，无滚动条 | 用 Tree（列表）或 TextEdit（文本）代替通用布局；或用 Tab 分页 |
| 按钮高于同行控件 → 视觉挤压 | VGroup Spacing=TIGHT 时，按钮与上方控件缺少呼吸感 | 加 `ui.VGap(SPACE_SM)` 在按钮前——**不让按钮缩高度** |

## 布局规则

1. **Weight 是主力**：`Weight: 0` = 最小尺寸；`Weight: 1` = 可伸缩。多数情况靠 Weight 就够了。
2. **FixedSize 是最后手段**：HEIBA / Batch_io_Pro 均不用它。仅在 Weight+Spacing 无法控制的极端情况使用。
3. **MinimumSize 适度用**：HEIBA 仅在少量按钮上设 `MinimumSize: [80, 28]`。
4. **右对齐唯 HTML**：`Alignment` 在 Label/Button 上可用（HEIBA 广泛使用），但 StyleSheet 的 `qproperty-alignment` 不生效。用 `<div align='right'>`。
5. **进度条不要 FixedSize**：用 `Resize + Update + MinimumSize`（方案A）或 `Stack` 叠加（方案B）。
6. **TextEdit auto-scroll**：`MoveCursor("End", "MoveAnchor")` + `EnsureCursorVisible()` 在 Append 后调用。
7. **子线程 UI 状态桥**：`_ui_pending` 存完整的格式化值，不能存原始值让主线程再格式化。
8. **窗口宽度**：通过 `GetGeometry()` 动态获取，不硬编码。
9. **VGap 节奏感**：VGroup 内 Spacing 是全局均分，但视觉重量不同的控件需要差异化间距。

### VGap 设计原则

| 场景 | 是否需要 VGap | 原因 |
|------|:--:|------|
| 同质控件（Label+LineEdit+Label 均匀排列） | ❌ | Spacing 足够 |
| 按钮前（高度 > 同行控件，或颜色突出） | ✅ | 按钮视觉重量大，需额外呼吸 |
| 分区前（_sep 分隔线后） | ✅ | 分隔线本身不占视觉空间 |
| 两个同样的按钮间 | ❌ | HGroup Spacing 足够 |

**为什么用 VGap 而非改按钮高度**：按钮高度由内容+padding 决定，降低高度=缩文字/挤 padding → 牺牲可读性。加 VGap 让按钮有自己的"领空"，不改自身尺寸。——2026-06-13 交付自检激活/停用、字幕检测两例验证

## 内部 vs 外部 Python 环境

> 来源：豆包深度调研报告（129KB）+ We Suck Less 论坛验证

**核心差异**：

| | 内部（Workspace菜单） | 外部（终端 scriptapp） |
|---|------|------|
| 执行线程 | 主 UI 线程 | 独立 Python 进程 |
| Fusion 对象 | 自动可用（v18.5）/ Resolve 19+ 未激活返回 None | 需 `resolve.OpenPage("fusion")` 激活 |
| UI Manager | 全控件可用但 v20 有窗口自动关闭 bug | 全控件可用 |
| DaVinciResolveScript | 不自动导入（需 sys.path） | 需 RESOLVE_SCRIPT_LIB 环境变量 |
| Python 版本 | 内嵌 Python（20.x=3.11, 旧版=3.6-3.9） | 外部 Python 3.8-3.13 |

**我们的结论**：
- 外部 subprocess 方案 ✅ = 规避了内嵌 Python 版本冲突 + 规避了 v20 内部环境窗口 bug
- 内部环境 Widget 崩溃根因：v20 窗口生命周期绑定更严格 + 可能的 Python 3.13/3.11 冲突
- 社区成功案例的关键：UI/逻辑分离 + 避免 `WindowModality` + 提前初始化所有控件

## 外部进程 subprocess 模式

- 启独立 Python 3.13 进程（系统安装版），不依赖达芬奇内嵌 Python
- 通过 `scriptapp("Resolve")` 连接，需 RESOLVE_SCRIPT_API 环境变量
- 规避 v20 内部窗口自动关闭 bug + Python 版本冲突
- **去重**：用 `subprocess.run(["pgrep", "-f", "ui_script.py"])` 检查是否已有实例

## API 关键版本差异

| 版本 | 变更 | 影响 |
|------|------|------|
| v20.1 | 移除 `InsertClip()`/`InsertClipIntoTrack()` | 用 `AppendToTimeline([{"recordFrame": N}])` 替代 |
| v20.0 | 内嵌 Python 升级到 3.11，系统 3.13+ 冲突 | 外部脚本用独立 Python 版本 |
| v19.1 | 免费版移除 UIManager | Studio 版无影响 |
| v19.0 | Fusion 合成 API 需激活页面 | 调 Fusion 前先 `OpenPage("fusion")` |
| v18.5+ | `SetMetadata` 对象差异 | MediaPoolItem 双参数 vs TimelineItem 单字典 |

---

## 弹窗/子窗口模式（来自 Batch_io_Pro）

达芬奇 UIDispatcher 不支持真正的非阻塞多窗口。标准做法是用二次事件循环创建"模态"弹窗：

```python
popup = disp.AddWindow({"WindowTitle": "选择颜色", "ID": "popup",
    "WindowFlags": {"Popup": True},  # 或 {"Window": True}
    "Geometry": [x, y, w, h]}, [ui.VGroup([...])])

popup.Show()
disp.RunLoop()   # 二次事件循环 — 阻塞主窗口直到弹窗关闭
popup.Hide()
```

**关键规则**：
- `Popup` flag：点击外部自动关闭，适合颜色选择器、下拉面板
- `Window` flag：独立窗口，需手动关闭
- `Show() + RunLoop() + Hide()` 三件套，缺一不可
- 弹窗内的事件绑定照样用 `popup.On[ID].Clicked = handler`
- handler 最后调 `disp.ExitLoop()` 关闭弹窗返回主循环

**定位相对主窗口**（来自 Batch_io_Pro）：
```python
bt_pos = itm[TriggerButton].GetGeometry()  # 触发按钮位置 → dict {1:x,2:y,3:w,4:h}
main_pos = dlg.GetGeometry()                # 主窗口位置
popup_x = main_pos.get(1, 0) + bt_pos.get(3, 0) + 20    # 按钮右侧
popup_y = main_pos.get(2, 0) + bt_pos.get(2, 0)         # 按钮底部对齐
```

## Tree 控件联动模式（来自 Batch_io_Pro） ✅ 已验证 20.3.2

> **20.3.2 实测**：`CurrentItem()` 是**方法**要加 `()`：`tree.CurrentItem()`。未选中时返回 `None`。`TopLevelItem(index)` 不存在，用 `AddTopLevelItems(list)` 批量构建。（2026-05-08 初测，2026-05-09+2026-05-13 补充更正）

左侧 Tree 选分辨率 → 右侧 Tree 显示该分辨率下的片段 → 点击片段跳转播放头：

```python
# 创建双栏 Tree
popup = [ui.HGroup({"Spacing": 5}, [
    ui.Tree({"ID": "reso_tree", "Weight": 0.3}),
    ui.Tree({"ID": "clip_tree", "Weight": 0.7})
])]

# 设表头
reso_head = reso_tree.NewItem()
reso_head.Text[0], reso_head.Text[1] = "Width", "Height"
reso_tree.SetHeaderItem(reso_head)
reso_tree.ColumnWidth[0], reso_tree.ColumnWidth[1] = 70, 70

# 联动：点击分辨率 → 更新右侧 Tree
def on_select_reso(ev):
    clip_tree.Clear()
    selected = reso_tree.CurrentItem()   # ⚠️ 方法，要加 ()
    if not selected:
        return
    w, h = int(selected.Text[0]), int(selected.Text[1])
    rows = []
    for clip in resolution_list[(w, h)]:
        row = clip_tree.NewItem()
        row.Text[0] = clip["Name"]
        row.Text[1] = clip["In"]
        rows.append(row)
    clip_tree.AddTopLevelItems(rows)     # 批量添加

# 跳转播放头
def on_click_clip(ev):
    item = clip_tree.CurrentItem()        # ⚠️ 方法
    if not item:
        return
    tc = item.Text[1]
    timeline.SetCurrentTimecode(tc)
```

---

## 预检规则（37 条，写代码前逐条过）

### 🔴 P0 — 线程安全
| # | 规则 |
|---|------|
| 1 | 子线程禁止操作 UI 控件 |
| 2 | UI 更新必须在主线程 |
| 3 | `disp.RunLoop()` 前所有控件初始化须完成 |

### 🟠 P1 — 构造器陷阱
| 4 | Stack 构造时不设 `Visible: False`（崩溃） |
| 5 | Label 构造时不设 `Visible: False`（同上） |
| 6 | `FindWindow()` 须 try/except — 部分版本不存在。外部 subprocess 用 `pgrep` |
| 7 | Button `Enabled:False` 不要在构造参数里设，构造后用 `itm[...].Enabled = False` |
| 8 | Stack `CurrentIndex` 默认 -1，须手动设 0 |
| 9 | TabBar+Stack 须用同一个类实例 |
| 10 | `TextInteractionFlags` 必须用数值（日志区 13，非日志区 3） |

### 🟠 P1.5 — 外部环境兼容
| 11 | 不用 TreeView/ColorPicker/Menu（外部不支持） |
| 12 | 不用 `WindowModality`（无响应） |
| 13 | `resolve.Fusion()` 可能返回 None，必须检查 |
| 14 | 文件名不含 Emoji（达芬奇 bug） |

### 🟡 P2 — API 签名
| 15 | `GetItemListInTrack("video", 1)` 不是 `(1)` |
| 16 | `GetTrackCount("video")` 必须带参数 |
| 17 | API 调用返回值必须检查 |
| 18 | `GetClipColor` 返回值可能是 None/""/[] |
| 19 | `GetTimelineByIndex` 可能返回 None |

### 🟢 P3 — 部署
| 20 | 改 core.py 后 dev.sh 自动跑 pre_flight |
| 21 | 部署后 diff 检查 SMB 同步 |
| 22 | launcher.py 永不更新 |
| 23 | 外部进程用系统 Python 3.13 |

### 🔵 P4 — 架构
| 24 | core.py 纯函数，不能 import logger |
| 25 | 打进去不装上去——运行时零安装，构建时 pip 生成数据 OK |
| 26 | Dry-run 0 元验证 |
| 27 | 所有 .py UTF-8 编码 |

### ⚫ P5 — 达芬奇已知 Bug
| 28 | `AppendToTimeline()` 缺轨道索引参数 |
| 29 | `ExportStills()` 20.x 始终返回 False |
| 30 | Emoji 文件名 → UnicodeDecodeError |
| 31 | v20.2.0 `GetSubtitleText()` 返回空（v20.2.1 已修） |
| 32 | LineEdit + CJK 输入法 → `Fusion::RemoteApp::FindLocalObject` SIGSEGV（2026-06-16 实测 macOS 26.5 + DR 20.3.2） |

### 🔵 P4 — 输入安全（2026-06-16 新增）
| # | 规则 |
|---|------|
| 33 | 涉密/激活码等高频输入 → 用 osascript 弹窗或 tkinter 子进程，不用 LineEdit |
| 34 | API key / secret 编辑 → Label + [编辑] 按钮 + osascript `display dialog`（`with hidden answer`） |
| 35 | 弹窗按钮前先 `Enabled=False`，`finally` 恢复，防排队重复弹窗 |
| 36 | osascript 弹窗换行用 `$'...\\n...'` 而非 `'...\\n...'`（单引号不转义） |
| 37 | UIManager 无通用 ToolTip 属性 → 替代：①按钮文案自带说明 ②独立 Hint Label |
| 38 | LineEdit→Label 替换模板：保持 ID 不变，`.Text` 读写兼容，编辑用 osascript 弹窗 |

### 新增 (v0.7.5 实战)
| 32 | `ReplaceClipPreserveSubClip` 在 **MediaPoolItem** 上，非 TimelineItem |
| 33 | mark_processed 取 fn 在替换**之前** |
| 34 | `hasattr` 陷阱 → 用 `getattr(x, 'a', None) is not None` |
| 35 | File Name 状态键以干净名（去掉 `_去字幕_` 后缀） |
| 36 | 🚫 禁止 SMB 全盘扫描 |
| 37 | 进度条不用 FixedSize |
| 38 | ❌ `dlg.Find("ID")` — UIManager 不存在此方法 |
| 39 | ❌ `dlg["ID"].Text = "x"` — 不支持下标访问 |
| 40 | ❌ `w_go.Enabled = False` — 蓝图 dict 改不动真实 UI |
| 41 | ❌ `ProcessEvents()` — 可能阻塞，别在下载前调用 |
| 42 | ✅ `_items = dlg.GetItems()` — 唯一正确获取控件的 |
| 43 | ✅ `_items["ID"].Text = "..."` — 修改控件属性 |
| 44 | ✅ `"WindowFlags": {"Window": True, "WindowStaysOnTopHint": True}` — 置顶 |

## UIManager 新窗口正确模式（v2.3.4 验证）

```python
_items = {}                                          # 空 dict
_items["btn"] = ui.Button({"ID": "btn", "Text": "..."})
_items["lbl"] = ui.Label({"ID": "lbl", "Text": "..."})
dlg = disp.AddWindow({"ID":"w", "WindowFlags":{"Window":True,"WindowStaysOnTopHint":True}},
      [..._items["btn"], _items["lbl"]...])
dlg.Show()
_items = dlg.GetItems()   # 蓝图 → 真控件（此行之后才能 .Text / .Enabled）
_items["btn"].Text = "下载中…"
_items["btn"].Enabled = False
dlg.On["btn"].Clicked = handler
disp.RunLoop()
```

详见同级别 skill: `davinci-ui-patterns`

## 弹窗防连点模式（2026-06-16 沉淀）

UIManager `Clicked` 事件在 `subprocess.run` / `subprocess.Popen` 阻塞期间会排队——用户点 N 次 = 出 N 个弹窗。标准解法：

```python
_busy = False
def _handler(ev):
    nonlocal _busy
    if _busy: return             # 1. 快速拒绝
    _busy = True
    cfg["btn"].Enabled = False   # 2. 灰显按钮，不接受点击
    try:
        r = subprocess.run(["osascript", ...], capture_output=True, text=True, timeout=60)
        # ... 处理结果 ...
    finally:
        _busy = False
        cfg["btn"].Enabled = True  # 3. 任何出口都恢复
```

**关键**：`Enabled=False` 必须在 `try` 之前（不是之内），`finally` 是唯一恢复点。所有 `return` / `except` 之前都不能恢复按钮——让 `finally` 统一处理。

## tkinter 子进程弹窗模式（2026-06-16 沉淀）

场景：需要三框分段输入（如激活码 `XXXX-XXXX-XXXX`），osascript 只支持单行。用 tkinter 独立进程弹窗——Cocoa 渲染，不碰 UIManager Qt 事件循环，IME 安全。

```python
r = subprocess.run([sys.executable, "-c", r'''
import tkinter as tk
root = tk.Tk()
root.attributes("-topmost", True)
root.withdraw()  # 先隐藏，计算位置后再 deiconify，防左上角闪现

# --- 函数必须先定义再使用 ---
def _validate(new):
    return new == "" or (len(new) <= 4 and all(c.isascii() and c.isalnum() for c in new))

# --- UI 构建 ---
frame = tk.Frame(root); frame.pack(pady=5)
entries = []; svars = []
for i in range(3):
    sv = tk.StringVar()
    svars.append(sv)
    e = tk.Entry(frame, width=6, font=("Menlo", 16), justify="center",
                 textvariable=sv, validate="key",
                 validatecommand=(root.register(_validate), "%P"))
    e.pack(side="left", padx=2); entries.append(e)
    if i < 2: tk.Label(frame, text="—", font=("", 14), fg="#888").pack(side="left")

def _on_change(idx):
    val = ''.join(c for c in svars[idx].get() if c.isascii() and c.isalnum()).upper()
    svars[idx].set(val)
    if len(val) == 4 and idx < 2: entries[idx + 1].focus_set()
    elif len(val) == 0 and idx > 0: entries[idx - 1].focus_set(); entries[idx - 1].icursor("end")

for i in range(3):
    svars[i].trace_add("write", lambda *a, idx=i: _on_change(idx))

btn_frame = tk.Frame(root); btn_frame.pack(pady=(15, 10))
result = [""]; err_lbl = tk.Label(root, text="", fg="#d04040", font=("", 11)); err_lbl.pack()

def _ok():
    parts = [sv.get().strip().upper() for sv in svars]
    if len(parts[0]) == 4 and len(parts[1]) == 4 and len(parts[2]) == 4:
        result[0] = f"{parts[0]}-{parts[1]}-{parts[2]}"; root.destroy()
    else:
        err_lbl.config(text="请输入完整 12 位")

tk.Button(btn_frame, text="取消", width=8, command=root.destroy).pack(side="left", padx=5)
tk.Button(btn_frame, text="确定", width=8, command=_ok).pack(side="left", padx=5)

# 居中 + 显示（withdraw→deiconify 消闪现）
root.update_idletasks()
w, h = root.winfo_width(), root.winfo_height()
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"+{int((sw-w)/2)}+{int((sh-h)/2)}")
root.deiconify()
entries[0].focus_set()
root.mainloop()
print(result[0])
'''], capture_output=True, text=True, timeout=120)
code = r.stdout.strip()  # 取消时为空，正常时 = "XXXX-XXXX-XXXX"
```

**踩坑**：
- `_validate` / `_on_change` 必须在 Entry 创建**之前**定义（Python 引用前必须存在）
- `"中".isalnum()=True` → 必须加 `isascii()` 双重拦截
- `withdraw/deiconify` 消左上角闪现；不用 `geometry` 预定位（尺寸未知时不准）
- `trace_add("write", lambda *a, idx=i: ...)` 的 `idx=i` 闭包捕获技巧

## osascript 弹窗换行语法（2026-06-16 沉淀）

```bash
# ❌ 单引号：\n 原样输出，弹窗显示 "行1\n行2"
osascript -e 'display dialog "行1\n行2" buttons {"取消","确定"}'

# ✅ $'...'：\n 解释为换行，弹窗正常分行
osascript -e $'display dialog "行1\n行2" buttons {"取消","确定"}'

# ✅ Python 内嵌：变量展开用 f-string + 外层单引号
subprocess.run(["osascript", "-e",
    f'text returned of (display dialog "{prompt}"'
    f' default answer "{default_val}" with title "{title}"'
    f'{" with hidden answer" if is_secret else ""}'
    ' buttons {"取消", "确定"} default button "确定")'])
```

注意 `with hidden answer` 前面必须有空格——`f'{" with hidden answer" if ... else ""}'`。

### 快速自查（10 秒版）
写 UI 代码前问：①子线程有itm吗 ②Visible:False在构造吗 ③FindWindow有try吗(外部用pgrep) ④TreeView/ColorPicker/Menu/Modal吗 ⑤GetItemListInTrack两个参数 ⑥跑过dev.sh吗 ⑦ReplaceClip在MediaPoolItem上 ⑧fn在替换前取了 ⑨hasattr?(用getattr) ⑩SMB全盘扫描?(禁止) ⑪弹窗按钮防连点了吗(Enabled+finally) ⑫中文输入法会崩LineEdit吗(用osascript/tkinter替代)
