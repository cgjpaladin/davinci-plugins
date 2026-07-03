---
name: davinci-ui
description: 达芬奇 UIManager 完整开发指南。包含窗口创建、控件速查、TabBar+Stack、进度条、样式、已知坑位、37 条预检规则。触发词：达芬奇UI、UIManager、窗口、按钮、控件、界面、弹窗。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
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
| **`threading.Thread` 不执行** | DaVinci Fusion 子进程中 `Thread(target=fn).start()` 静默失效 | **后台任务必须用 `subprocess.Popen`**，结果经临时文件传递 |
| **`sys.executable` in DaVinci** | 内嵌 Python 路径不可靠 | launcher 已选定正确 Python，插件子进程直接用 `sys.executable` |

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

## 开发预检清单

> 写 UI 代码前逐条过。每条有症状、有解法、有来源。来源标注：🧪=交付自检代码 / ✂️=AI去字幕代码 / 📝=裁缝老师反馈。

### 🔴 布局

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 1 | 控件粘在一起 | **Spacing vs 显式 VGap**。父容器 `Spacing: N` = 所有子控件间距统一。需要不均匀间距时必须 `Spacing: SPACE_NONE` + 逐个 `ui.VGap(N)` | 🧪 15 处 VGap/HGap |
| 2 | 闪退 | **Label 不可设 `MinimumSize`**。用 HGroup Weight 代替 | 📝#30 |
| 3 | 窗口撑破屏幕 | **VGroup 不裁剪溢出**。用 `Weight: 1` 驱动弹性伸缩，不写死 height | 🧪 Tree 区域 |
| 4 | 初始化控件被截断 | **`RecalcLayout()` 必须在 `Show()` 之后**。进度条 `GetGeometry()` 前也要先 RecalcLayout | 🧪+✂️ |
| 5 | 右上角空白 | **`VGap({"Weight": 1})`** 填充剩余空间，推底部到窗底 | 🧪 1062 行 |
| 6 | 按钮不居中 | **`HGap({"Weight": 1})`** 放按钮左右两侧，推按钮到中间 | 🧪 1067 行 |
| 7 | 竖线/分隔渲染异常 | **分割线用 `Label({"Text": "┃", "StyleSheet": STYLE_DIVIDER})`**，设 `MinimumSize:[0,SIZE_LINE_H]` | 🧪 789 行 |

### 🔴 控件创建

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 8 | 不生效/崩溃 | `ui.Widget({"ID": "id", ...})` 不是 `("id", {...})` | 🧪+✂️ |
| 9 | 回调不触发 | `win.On["ID"].Clicked` 不是 `win.On.ID.Clicked` | 🧪+✂️ |
| 10 | AttributeError | `_items = dlg.GetItems()` — 唯一稳定访问。没有 `.Find()`、不支持 `dlg["ID"]` | 📝#24 |
| 11 | 控件初始化崩溃 | Stack/Label 构造时不设 `Visible:False` | 📝 |
| 12 | `_items["ID"].Enabled = False` 不生效 | Button `Enabled:False` 不要在构造参数里设，构造后通过 GetItems() 赋值 | 📝#7 |

### 🔴 输入安全

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 13 | SIGSEGV 闪退 | **禁止 LineEdit + CJK**。`Fusion::RemoteApp::FindLocalObject`。涉密/激活码输入用 osascript 或 tkinter 子进程 | 📝#7 |
| 14 | Dock 图标 | **文件选择用 `fu.RequestFile()` / `fu.RequestDir()`**，不用 tkinter 子进程 | 📝#35 |
| 15 | 激活码混入中文 | `isascii() and isalnum()` 双重校验。`"中".isalnum()=True` | 📝#8 |
| 16 | 公网 IP 泄露 | Label 设 `TextInteractionFlags: 3`（可选中复制），不设 13（可编辑） | 🧪 |

### 🔴 按钮状态

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 17 | 按钮永灰 | `Enabled=False` 在 `try` 前，`Enabled=True` 在 `finally`。任何提前 `return`/`raise` 不可恢复按钮 | 📝#8 |
| 18 | 按钮跳动 | **互斥用 `Enabled`，禁用 `Visible`**。Visible=False 释放布局空间 | 🧪 设计规范 |
| 19 | N 次点击=N 个弹窗 | **防连点**：`busy_flag` + `try/finally` 恢复。UIManager Clicked 在 subprocess 阻塞期间排队 | 📝#35 |
| 20 | 漏一个控件 | `_lock_ui()` / `_unlock_ui()` 成对，改控件后必须两边都改 | 🧪 75 处 .Enabled |

### 🔴 线程安全

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 21 | 不定时崩溃 | **子线程禁止操作 UI 控件**。UIManager 不是线程安全的 | ✂️+📝 |
| 22 | UI 冻结 | 跨线程：`_ui_lock` + `_ui_pending` 队列 + 主线程轮询 `_apply_ui_state()`。子线程写入队列，主线程在 StepLoop 中消费 | ✂️ stable_ui.py |
| 23 | 事件循环阻塞 | `disp.StepLoop(100)` 保持 UI 响应，同时消费队列 | ✂️ stable_ui.py |
| 24 | 启动失败 | `disp.RunLoop()` 前所有控件初始化完成 | 🧪+✂️ |

### 🟡 窗口生命周期

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 25 | C++ SIGSEGV | 退出用 `os._exit(0)`，跳过 fusionscript.so C++ 析构 | 🧪+✂️ |
| 26 | 重复窗口 | PID 锁文件 `~/.ui_instance.lock` 防多开 | 🧪+✂️ |
| 27 | 子窗口失控 | 子窗口 = 新 `bmd.UIDispatcher()` + 新 `AddWindow` + 新 `RunLoop` | 🧪 config窗口 |
| 28 | 模态窗口不响应 | 不用 `WindowModality`，自己管理 show/hide | 📝 |

### 🟡 Tree 系统

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 29 | 颜色不显示 | Tree TextColor/BackgroundColor v20.3.2 不渲染，纯文字替代 | 🧪 |
| 30 | 列错乱 | COLUMNS 定义表头+宽度，FIELD_TO_COLUMN 映射字段→列，启动时 `_validate_field_map()` 双向校验 | 🧪 |
| 31 | 点击无响应 | `ev.get("Item") or tree.CurrentItem()` 双重回退。导航 Tree 用 `item.Text[1]` 存父组名消歧义 | 🧪 |

### 🟡 样式

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 32 | 按钮样式不统一 | **6 种按钮 CSS**：BTN_STYLE（灰）/ BTN_PRIMARY（蓝）/ BTN_DANGER（红）/ BTN_STYLE_SM（小灰）/ BTN_ICON（图标）。定义在文件顶部常量 | 🧪 232 行 |
| 33 | 字体大小混乱 | **5 档字体**：FONT_H1(13px) / FONT_H2(15px) / FONT_BODY(12px) / FONT_SM(11px) / FONT_XS(10px)。FONT_BOLD 单独叠加 | 🧪 184 行 |
| 34 | 间距不一致 | **6 档间距**：SPACE_NONE(0) / TIGHT(2) / COMPACT(3) / SM(4) / NORMAL(6) / RELAXED(8) / WIDE(10)。按钮尺寸 5 档 SIZE_BTN_* | 🧪 192 行 |
| 35 | CSS double-expand | `STYLE_DIM` 写了 `font-size:{FONT_XS}` 得 `font-size:font-size:10px`——因为 `FONT_XS="font-size:10px"` 是完整属性，不能用 `{}` 拼。样式常量分两类：值型（直接拼）和属性型（独立用） | 🧪 222 行 |

### 🟡 错误处理

| # | 忘了会怎样 | 规则 | 来源 |
|----|----------|------|------|
| 35 | 一个检查崩，全流程死 | 单检查 `try/except` → `_make_result_passthrough("warn")`，不阻断其他 | 🧪 check_core |
| 36 | 结果不显示在 Tree | `is_summary: True` 必须是每个 check 函数第一条返回。没有这条 = UI 跳过渲染 | 📝#6，三次犯 |
| 37 | RecursionError 杀线程 | `sys.stderr` 重定向前保存 `_real_stderr`。所有内部写 stderr 用 `_real_stderr.write()` | 🧪 2026-06-27 |
| 38 | 报错按钮无感知 | `_UI_ERROR_COUNT` 全局计数器 + `_update_err_counter()` 动态更新按钮文案：`"📋 导出日志"` → `"⚠️ 3 个报错"` | 🧪 676 行 |

### 🟡 注册表驱动架构

> 这是达芬奇插件最核心的架构模式。新插件必须遵循。

一条原则：**加功能不改 UI 代码，只改注册表**。三种注册表，每种有自己的格式和规则：

| 注册表 | 产品 | 格式 | 加新项 |
|--------|------|------|--------|
| `CHECKS` | 交付自检 | `[{id, section, group, subgroup, chk_id, run_fn, tracks, gate, hidden}]` | 加一个 dict + 写 `_run_xxx_check()` |
| `CONFIG_SECTIONS` | 交付自检 | `[{id, label, type}]` | 加一个 dict + 写 `_build_xxx()` + `_save_xxx()` |
| `ADAPTER_CONFIGS` | AI去字幕 | `{adapter_name: {url, region, bucket, ...}}` | 加一个 key + 写 `adapters/xxx.py` |

**CHECKS 约定**：
- `"tracks": []` = 不预加载轨道（路径/脱机检测类，无 gate）
- `"tracks": ["video", "audio"]` = 预加载指定轨道
- `run_fn: None` = 暂不可用的检查，UI 显示灰色「待开发」
- `hidden: True` = 永久隐藏（不在 UI 生成控件）
- `gate: ""` = 不受门控制永远先跑。非空 = 受 `gates_ok` 控制
- 调顺序 = 移动注册表位置；删检查 = 注释整行（留注释说明原因）
- 启动时 `_validate_checks()` 校验 `run_fn` 可调用，用完 `del _validate_checks`

**COLUMNS + FIELD_TO_COLUMN 约定**：
```python
COLUMNS = [{"header": "轨道", "width": 48, "key": "track", "enabled": True}, ...]
FIELD_TO_COLUMN = {"track": "track", "timecode": "tc", "detail": "msg", "reason": "reason"}
```
- 加字段：FIELD_TO_COLUMN 加一行 → COLUMNS 加对应列 → `_validate_field_map()` 启动双向校验
- 删字段：两边对应删
- `check_core` 输出 `{track, timecode, detail, reason}` → 映射到 Tree 的 `{track, tc, msg, reason}`

**CONFIG_SECTIONS 约定**：
- `type: "api_key"` = 显示遮罩值 + 编辑按钮（osascript 弹窗 `with hidden answer`）
- `type: "smb_paths"` = ComboBox 多选路径
- `type: "censor_personal"` = Finder 定位按钮
- `_SECTION_BUILDERS` dict 路由 type → builder 函数
- 每个 `_build_xxx()` 返回一组 widget，`_save_xxx()` 负责持久化

---

### 代码模板

#### 防连点模式

```python
_busy = False
def _handler(ev):
    nonlocal _busy
    if _busy: return                 # 快速拒绝
    _busy = True
    btn.Enabled = False              # try 前灰显
    try:
        r = subprocess.run(["osascript", ...], timeout=60)
    finally:
        _busy = False
        btn.Enabled = True           # 唯一恢复点
```

#### tkinter 三框弹窗（激活码输入）

```python
r = subprocess.run([sys.executable, "-c", r'''
import tkinter as tk
root = tk.Tk()
root.attributes("-topmost", True)
root.withdraw()                     # 先隐藏，防左上角闪现

def _validate(new):
    return new == "" or (len(new) <= 4 and all(c.isascii() and c.isalnum() for c in new))

frame = tk.Frame(root); frame.pack(pady=5)
entries = []; svars = []
for i in range(3):
    sv = tk.StringVar(); svars.append(sv)
    e = tk.Entry(frame, width=6, font=("Menlo", 16), justify="center",
                 textvariable=sv, validate="key",
                 validatecommand=(root.register(_validate), "%P"))
    e.pack(side="left", padx=2); entries.append(e)
    if i < 2: tk.Label(frame, text="—", font=("", 14), fg="#888").pack(side="left")

def _on_change(idx):
    val = ''.join(c for c in svars[idx].get() if c.isascii() and c.isalnum()).upper()
    svars[idx].set(val)
    if len(val) == 4 and idx < 2: entries[idx + 1].focus_set()
    elif len(val) == 0 and idx > 0: entries[idx - 1].focus_set()

for i in range(3):
    svars[i].trace_add("write", lambda *a, idx=i: _on_change(idx))

btn_frame = tk.Frame(root); btn_frame.pack(pady=(15, 10))
result = [""]
def _ok():
    parts = [sv.get().strip().upper() for sv in svars]
    if all(len(p) == 4 for p in parts):
        result[0] = f"{parts[0]}-{parts[1]}-{parts[2]}"; root.destroy()

tk.Button(btn_frame, text="取消", width=8, command=root.destroy).pack(side="left", padx=5)
tk.Button(btn_frame, text="确定", width=8, command=_ok).pack(side="left", padx=5)

root.update_idletasks()
w, h = root.winfo_width(), root.winfo_height()
root.geometry(f"+{(root.winfo_screenwidth()-w)//2}+{(root.winfo_screenheight()-h)//2}")
root.deiconify()
entries[0].focus_set()
root.mainloop()
print(result[0])
'''], capture_output=True, text=True, timeout=120)
code = r.stdout.strip()
```

#### osascript 弹窗

```python
# 单行输入（API Key 等）
r = subprocess.run(["osascript", "-e",
    f'text returned of (display dialog "{prompt}"'
    f' default answer "{default_val}" with title "{title}"'
    f'{" with hidden answer" if is_secret else ""}'
    ' buttons {"取消", "确定"} default button "确定")'],
    capture_output=True, text=True, timeout=60)
val = r.stdout.strip()
```

> `with hidden answer` 前面必须有空格。换行必须用 `$'...\n...'`（单引号不转义 `\n`）。

#### 模块启动自检 + 自毁

```python
def _validate_field_map():
    """启动时校验 FIELD_TO_COLUMN ↔ COLUMNS 一致。不通过抛 AssertionError。"""
    col_keys = {c["key"] for c in COLUMNS if c.get("enabled", True)}
    field_keys = set(FIELD_TO_COLUMN.values())
    assert col_keys == field_keys, f"Mismatch: COLUMNS={col_keys}, FIELD_TO_COLUMN values={field_keys}"

_validate_field_map()
del _validate_field_map          # 用完即焚，不污染模块命名空间
```
模式：`_validate_xxx()` 启动时调用一次 → `del` 消除。所有注册表都应配对应的 validator。

#### 日志重复折叠

```python
_LOG_MAX_LINES = 200            # 防止 TextEdit 无限涨内存
_last_ui_msg = ""
_last_ui_count = 0

def _write_log(msg):
    if msg == _last_ui_msg:
        _last_ui_count += 1     # 累计重复
        return
    if _last_ui_count > 1:
        te.PlainText += f"  ↑ repeated {_last_ui_count} times\n"
    _last_ui_msg = msg
    _last_ui_count = 1
    te.PlainText += msg + "\n"
    # 行超上限时修剪：
    if _log_line_count > _LOG_MAX_LINES:
        lines = te.PlainText.split("\n")
        te.PlainText = "\n".join(lines[-_LOG_MAX_LINES:])
    te.MoveCursor("End", "MoveAnchor")  # 滚动到底部
```
用途：AI去字幕引擎轮询时每秒输出相同消息 → 不刷屏。

## 插件设计规范

跨所有插件的 UI 约定——改窗口布局时必须遵守。

### 窗口布局

- **标题栏**：纯产品名，不带版本号。`"WindowTitle": PRODUCT_NAME`
- **右下角**：品牌名 + 版本号。`f"{BRAND_NAME} | v{version_string()}"`
- **窗口尺寸**：交付自检 900×520（右上角），AI去字幕 880×560（居中）

### 分区规则

- **金区（TRIAL_LB）** = 授权状态和购买引导。只放试用天数、激活码输入、购买链接。永不混入功能指引。
- **灰区（HINT_LB）** = 功能操作指引。只放检查结果、进度提示、使用说明。永不混入授权信息。
- 金区灰区永不对调或越界。

### 按钮

- **互斥用 `Enabled`，禁用 `Visible`**。Visible=False 释放布局空间 → 按钮跳动。Enabled=False 只改视觉，占位不变。
- **弹窗按钮必须防连点**：`subprocess.run` 阻塞期间 UIManager 事件排队 → N 次点击 = N 个弹窗。标准解法：`Enabled=False` 在 `try` 前 + `finally` 统一恢复。
- **间距**：按钮之间至少 5 字符宽度（`MinimumSize: [20,0]`）。

### Label / Text

- **禁止 LineEdit + CJK 输入法**：`Fusion::RemoteApp::FindLocalObject` SIGSEGV 闪退。替代：osascript `display dialog`（单行）或 tkinter 子进程（多框）。
- **Tree 样式不可靠**：BackgroundColor/TextColor 在 20.3.2 可能不渲染。先上纯文字分隔，不依赖颜色。
- **含中文/特殊字符的文本**：用 Python/Bash 写文件后设 `Label.Text`，不要用正则批量编辑。

### 事件与 API

- **事件绑定**：`win.On["ID"].Clicked`，不是 `win.On.ID.Clicked`
- **控件创建**：`ui.Widget({"ID": "id", ...})`，不是 `("id", {...})`
- **非默认事件**：必须 `Events:{Name:True}` 声明——仅 Clicked/Close 默认启用。FocusIn/KeyPress/SliderMoved 等需显式启用。
- **`SetFocus()` 需 `Events:{FocusIn:True}` 前置**。
- **`config_dlg.RecalcLayout()` 必须在 `Show()` 后调用**。

### UIManager 已知限制

| 限制 | 影响 | 替代方案 |
|------|------|---------|
| LineEdit + CJK 输入法 | macOS 26+ DR 20.3.2 SIGSEGV 闪退 | osascript `display dialog` 或 tkinter 子进程 |
| 无通用 ScrollArea | VGroup/HGroup 内容超出截断 | Tree 有滚动 (VerticalScrollMode + ScrollToItem) |
| Tree TextColor/BackgroundColor | v20.3.2 不渲染，API 存在 | 纯文字分隔替代 |
| Tree 无 SetItemText/SetItemChecked | 只能纯展示，不能交互勾选 | TreeItem 有 CheckState[0]（需验证） |
| VGroup 不裁剪溢出 | 控件多时窗口撑破屏幕 | 拆分页面或用 TabBar+Stack |
| `SetFocus()` 不生效 | 需要 `Events:{FocusIn:True}` 启用 | 初始化时 SetFocus 在 RunLoop 前 |
| 无 Timer / Idle 回调 | 不能启动后延迟执行 | 所有初始化在 `disp.RunLoop()` 前同步完成 |
| subprocess 阻塞 + Clicked 排队 | 弹窗按钮连点出多个窗口 | `Enabled=False` 在 try 前 + finally 恢复 |
| urlopen 在子进程无限挂 | timeout 被忽略，线程/子进程超时均无效 | 文件选择→fu.RequestFile/Dir；网络调用→主shell线程/curl subprocess |
| tkinter 子进程生 Dock 图标 | macOS 独立 Python 进程占据 Dock | 文件/文件夹选择→fu.RequestFile/Dir（Fusion 原生） |
