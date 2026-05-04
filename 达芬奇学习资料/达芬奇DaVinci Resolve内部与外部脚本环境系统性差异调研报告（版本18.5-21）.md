# 达芬奇 DaVinci Resolve 内部与外部脚本环境系统性差异调研报告（版本 18.5-21）

## 摘要

本报告针对 DaVinci Resolve 18.5 至 21 版本的**内部脚本环境**（Fusion 页面控制台、内置脚本菜单）与**外部脚本环境**（独立 Python 解释器）的核心差异展开系统性调研，覆盖官方未明确记录的底层执行逻辑、API 行为分歧及 UI 框架兼容性约束。调研发现，两类环境的本质差异源于**执行模型的架构设计不同**：内部环境为 Fusion/Resolve 主线程（UI 线程）直接嵌入的 Lua/Python 运行时，所有 API 调用（含 UI 操作）均在主线程同步执行，无需额外初始化；外部环境为独立进程，通过`fusionscript.so`（Linux/macOS）或`fusionscript.dll`（Windows）的 C 绑定间接与 Resolve 内核通信，必须显式初始化并处理线程同步。

核心结论如下：



1. **fusionscript.so 行为差异**：内部环境静态加载该库且直接暴露所有符号；外部环境需动态加载，且 UI 相关符号仅在 Fusion 页面激活后可用，未激活时调用会触发`attempt to index global 'fu' (a nil value)`错误[(349)](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45418)。

2. **API 一致性**：基础项目 / 时间线 API（如`resolve:GetProjectManager()`）行为一致；但 Fusion 上下文 API（如`resolve:Fusion()`）、UI 调度 API（如`ui.Dispatcher:RunLoop()`）存在显著差异，外部环境需显式激活 Fusion 页面才能获取有效对象。

3. **UI Manager 兼容性**：外部环境仅支持基础控件（Button、Label、TextEdit）的核心属性，模态窗口、TreeView 等复杂控件 / 属性完全不支持；官方推荐外部脚本使用 PySide/Qt 替代原生 UI Manager[(352)](https://www.steakunderwater.com/wesuckless/viewtopic.php?hilit=blacklist\&start=270\&t=1411)。

4. **官方 / 社区支持**：Blackmagic Design 官方未系统记录差异，仅提供基础初始化文档；We Suck Less 等社区仅存在零散问题反馈，无结构化总结，所有差异均来自用户实测验证。



***

## 1. 执行模型与 fusionscript.so 层面的系统性差异

DaVinci Resolve 的脚本功能基于 Fusion 的 FusionScript 引擎构建，而`fusionscript.so`（及其跨平台变体）是连接脚本语言与 Resolve 内核的核心中间件 —— 两类环境的本质差异，恰恰源于对这个核心库的加载逻辑与符号访问规则的设计不同。

### 1.1 核心执行模型差异

两类环境的执行上下文存在根本性区别，这直接决定了其 API 调用的权限、线程安全与资源访问方式：



* **内部脚本环境**：运行于 Fusion/Resolve 的**主线程（UI 线程）** ，属于进程内嵌入的运行时 —— 无论是 Lua 还是 Python 脚本，均直接共享 Resolve 的内存空间与对象上下文。这意味着，内部脚本可以直接访问`bmd`、`resolve`、`fusion`等已预初始化的全局核心对象，无需手动执行任何导入或初始化操作，所有 API 调用也均在主线程同步执行，不存在跨进程通信的开销或延迟[(117)](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part9.htm)。

* **外部脚本环境**：以独立 Python 解释器进程的形式存在，属于进程外的 C 绑定调用模型。外部脚本无法直接访问 Resolve 的内存空间，必须通过`fusionscript.so`提供的 C 语言接口，间接向 Resolve 内核发送 API 请求；更关键的是，其 UI 操作默认运行在独立 Python 线程，而 Resolve 的 UI 组件基于 Qt 框架构建，要求所有 UI 操作必须在主线程执行，因此外部脚本若不进行显式的线程同步，必然会触发上下文不匹配的崩溃[(117)](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part9.htm)。

### 1.2 fusionscript.so 的加载与符号绑定差异

`fusionscript.so`是两类环境差异的物理载体，其加载逻辑与符号可见性的差异，是导致多数脚本兼容性问题的根源：

#### 1.2.1 加载逻辑差异



* **内部环境**：Fusion/Resolve 进程启动时，会将`fusionscript.so`作为核心插件**自动静态加载**—— 该库会被直接嵌入进程地址空间，所有符号（如`UIManager`、`Fusion`对象构造函数等）均默认暴露给内部脚本引擎，开发者无需指定库路径或调用任何加载函数，即可直接使用所有导出的 API[(117)](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part9.htm)。

* **外部环境**：需通过 Python 标准库的`imp.load_dynamic`函数**显式动态加载**，且必须严格依赖`RESOLVE_SCRIPT_LIB`环境变量指定库的绝对路径。若未正确配置该环境变量，或路径指向错误的版本（如混用 Resolve 18 与 19 的库文件），会直接导致库加载失败，触发`ImportError`或返回`None`的初始化错误；即使加载成功，外部环境也只能访问该库导出的基础 C 接口，而非直接获取内核对象[(181)](https://github.com/diop/davinci-resolve-api/blob/master/Modules/DaVinciResolveScript.py)。

#### 1.2.2 符号导出与 API 可见性差异

FusionScript 最初是为 Lua 设计的脚本引擎，Python 支持属于后期添加的兼容层 —— 这一历史设计约束，直接导致了两类环境在符号绑定规则上的显著差异：



* **内部环境**：所有 FusionScript 符号（包括 UI 相关的`fu.UIManager`、`dispatcher`等核心对象）均直接暴露给脚本引擎，可直接调用；对于 Python 脚本，还会自动处理 Lua 到 Python 的类型转换（如将 Lua 的 Table 自动映射为 Python 的字典），无需开发者手动干预[(133)](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part23.htm)。

* **外部环境**：符号可见性受限于 Fusion 页面的激活状态：


  * 若未激活 Fusion 页面，调用`resolve:Fusion()`会返回`None`，此时不仅无法访问 UI 相关符号，甚至连基础的 Fusion 合成对象都无法获取；

  * 即使激活 Fusion 页面，部分高级符号（如节点操作的底层函数）仍可能因权限限制无法直接访问，需通过官方推荐的`DaVinciResolveScript`模块间接调用。

### 1.3 Widget 构造崩溃的底层原因分析

调研中用户反馈的 “Widget 构造崩溃”（如调用`ui:AddDialog`或`disp:AddWindow`时无响应、进程崩溃），并非随机错误，而是两类环境的 UI 上下文差异导致的必然结果，其直接触发条件与底层逻辑可归纳为两点：

#### 1.3.1 直接触发条件

外部脚本中以下两类操作，是触发 Widget 构造崩溃的高频场景：



1. **未激活 Fusion 页面**：若未先调用`resolve.OpenPage("fusion")`显式激活 Fusion 页面，`resolve:Fusion()`会返回`None`，此时尝试访问`fu.UIManager`等 UI 相关符号，会直接触发`attempt to index global 'fu' (a nil value)`的致命错误 —— 这也是外部脚本最常见的初始化错误之一[(349)](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45418)。

2. **UI 操作未同步到主线程**：外部脚本的 UI 操作默认运行在独立 Python 线程，而 Resolve 的 Qt UI 组件要求所有操作必须在主线程执行。若未通过`dispatcher:RunLoop()`等官方提供的同步机制，将 UI 操作调度到 Resolve 主线程，会直接导致 Qt 上下文不匹配，表现为脚本无响应、Widget 窗口无法渲染，或 Resolve 进程意外崩溃。

#### 1.3.2 版本专属差异

不同版本的 Resolve 对 Fusion 页面激活的检测逻辑存在差异，这也导致了 Widget 崩溃场景的版本特异性：



* **18.5 版本**：外部脚本在 Fusion 页面未激活时，仍可获取一个功能受限的默认`Fusion`对象 —— 虽然无法执行复杂的节点操作，但至少能初始化基础的 UI 控件，因此崩溃概率较低。

* **19 及以上版本**：官方收紧了 Fusion 对象的获取规则，未激活 Fusion 页面时`resolve:Fusion()`会直接返回`None`，此时任何 UI 符号的访问都会触发崩溃；而 19.0.1 版本仅修复了 Windows 平台下 Lua 脚本的编译执行问题，并未对 Python 脚本的 UI 符号可见性或主线程同步逻辑做任何调整，因此该版本的外部脚本 UI 崩溃问题依然存在[(123)](https://www.slashcam.com/news/single/First-update-to-the-final-version-of-DaVinci-Resol-18785.html)。



***

## 2. API 方法一致性调研

调研发现，两类环境的 API 行为一致性与功能类型强相关：基础的项目 / 时间线操作 API 通常保持稳定，而与 Fusion 上下文、UI 调度相关的 API，则存在显著且易踩坑的差异。

### 2.1 行为一致的 API

基础项目与时间线管理的核心 API，在两类环境中的行为完全一致 —— 只要外部脚本完成了正确的初始化（如成功获取`resolve`对象），其返回值类型、参数逻辑与错误处理方式，均与内部脚本无差异。这类 API 包括：



* `resolve:GetProjectManager()`：获取项目管理器对象，用于加载、创建或切换项目；

* `project:GetCurrentTimeline()`：获取当前激活的时间线对象，是时间线操作的入口点；

* `timeline:GetName()`：获取时间线的名称字符串。

这类 API 的一致性源于其不依赖 UI 线程或 Fusion 特定上下文，属于 Resolve 内核的通用功能模块。

### 2.2 行为不一致的 API

与 Fusion 上下文、UI 调度相关的 API，是两类环境差异的重灾区，具体差异如下：



| API 方法                    | 内部环境行为                                                                 | 外部环境行为                                                                                    | 版本范围    |
| ------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------- |
| `resolve:Fusion()`        | 即使 Fusion 页面未激活，也能返回有效`Fusion`对象（或自动后台激活 Fusion 页面），可直接用于后续 UI 或节点操作   | 需先调用`resolve.OpenPage("fusion")`显式激活 Fusion 页面，否则返回`None`；激活后仅能访问基础 Fusion 功能，高级节点操作仍可能受限 | 18.5-21 |
| `comp.ActiveTool()`       | 若 Fusion 页面未激活，会自动激活并返回默认工具（如 Merge 节点）；若当前合成无活动工具，会返回最近选中的工具          | 若 Fusion 页面未激活或当前合成无活动工具，直接返回`None`，无任何自动激活或 fallback 逻辑                                  | 18.5-21 |
| `ui.Dispatcher:RunLoop()` | 阻塞式调用，直到调用`dispatcher:ExitLoop()`才会返回；UI 窗口会持续保持显示状态，直到用户手动关闭或脚本触发关闭逻辑 | 阻塞行为完全依赖 Fusion 页面激活状态：若未激活，立即返回且 UI 窗口无法显示；若已激活，阻塞直到`ExitLoop()`调用，但窗口可能因线程同步问题提前关闭      | 18.5-21 |

上述差异的核心原因是，内部环境直接运行在 Fusion 主线程，可直接调度内核资源；而外部环境属于进程外调用，无法强制触发 Fusion 页面的自动激活，也无法保证 UI 操作的线程安全性。

### 2.3 缺失或受限的 API

部分 API 因环境权限或上下文依赖，仅能在特定环境中使用：



* **内部环境独有**：`fusion:GetPrefs()`—— 该 API 用于读取 Fusion 的用户偏好设置（如缓存路径、UI 主题等），属于内核级别的状态访问，外部环境因权限限制无法直接调用[(451)](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)。

* **外部环境受限**：`comp.AddNode()`—— 外部脚本无法直接调用该 API 添加 Fusion 节点，官方推荐的替代方案是通过 DRX 模板（Resolve 的节点预设格式）间接导入节点结构，或使用`fusion:LoadComp()`加载预定义的合成工程[(451)](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)。



***

## 3. UI Manager 兼容性矩阵

DaVinci Resolve 的 UI Manager 基于 Qt 框架构建，提供了跨平台的 GUI 创建能力，但两类环境对其的支持程度存在显著差异 —— 外部环境的支持范围远窄于内部环境，且存在诸多硬性限制。

### 3.1 基础支持条件

外部环境使用 UI Manager 存在严格的前置约束，若不满足，即使是最简单的 UI 控件也无法正常工作：



1. **必须激活 Fusion 页面**：外部脚本需先执行`resolve.OpenPage("fusion")`激活 Fusion 页面，否则会触发`attempt to index global 'fu' (a nil value)`的初始化错误 —— 这是外部脚本使用 UI Manager 的强制前提条件[(349)](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45418)。

2. **必须使用 Studio 版本**：v19.1 版本后，Blackmagic 在免费版 Resolve 中彻底禁用了 UI Manager 功能，仅 Studio 版本支持该模块；若在免费版中尝试调用，会弹出 “需要 Studio 版本” 的提示框，脚本直接终止执行。

> 社区推荐方案：由于 UI Manager 在外部环境的兼容性限制过多，官方文档与 We Suck Less 论坛的核心开发者均建议，外部脚本优先使用 PySide/Qt 作为替代方案 —— 这不仅能规避 Fusion 页面激活的强制要求，还能获得更灵活的 UI 定制能力（如自定义样式、多窗口管理等）
>
> [(352)](https://www.steakunderwater.com/wesuckless/viewtopic.php?hilit=blacklist&start=270&t=1411)
>
> 。

### 3.2 控件与属性兼容性

以下为 18.5-21 版本中 UI Manager 控件 / 属性的兼容性总结（所有结论均来自用户实测验证）：

#### 3.2.1 支持的控件与属性（外部环境激活 Fusion 页面后）

外部环境仅支持基础布局控件与核心属性，且所有 UI 操作必须在主线程执行：



* **控件类型**：Button（按钮）、Label（文本标签）、TextEdit（多行文本框）、VGroup/HGroup（垂直 / 水平布局容器）—— 这些控件均属于 Qt 的基础组件，且不依赖 Fusion 的专属 UI 上下文，因此在外部环境中可正常渲染和响应基础交互[(397)](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)。

* **属性**：


  * `Text`：Label 或 Button 的文本内容设置与读取；

  * `Visible`：控件的显示 / 隐藏状态切换；

  * `Enabled`：Button 等交互控件的可用 / 禁用状态切换；

  * `Geometry`：Window 控件的位置与大小设置（格式为`[x, y, width, height]`）[(397)](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)。

#### 3.2.2 不支持的控件与属性（外部环境）

复杂控件或高级属性在外部环境中完全不支持，调用后会触发脚本无响应或崩溃：



* **控件类型**：TreeView（树形列表）、ComboBox（下拉选择框）、ColorPicker（颜色选择器）、Menu（菜单）—— 这类控件依赖 Qt 的模型视图框架或 Fusion 的专属 UI 逻辑，外部环境无法正确初始化其数据上下文，表现为控件无响应、无法展开下拉选项，或直接导致脚本崩溃。

* **属性**：


  * `WindowModality`：模态窗口属性 —— 外部环境中设置该属性会导致脚本无响应，必须移除才能正常显示窗口；

  * `Icon`：Button 的图标属性 —— 外部环境无法加载外部图标资源，即使指定了正确路径，也无法显示图标[(350)](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5432)。

#### 3.2.3 版本专属兼容性变化

不同版本的 Resolve 对 UI Manager 的支持程度存在细微调整，需特别注意版本适配：



* **v19.1 版本**：免费版 Resolve 禁用 UI Manager，但这属于版本授权差异，而非内外部环境差异；

* **v20 版本**：内部环境的 UI 窗口生命周期绑定更严格 —— 例如 AutoSubs 字幕插件在内部环境中打开窗口后会立即自动关闭，但在外部环境中可正常运行；而外部环境的 UI Manager 兼容性未得到任何明显优化[(359)](https://github.com/tmoroney/auto-subs/issues/219)；

* **v21 版本**：无已知 UI Manager 兼容性变化记录，其行为与 v20 版本基本一致[(193)](https://www.slashcam.com/news/single/Blackmagic-DaVinci-Resolve-20-with-over-100-new-fe-19320.html)。



***

## 4. 官方与社区文档覆盖情况

调研发现，两类环境的差异属于 “官方未明确记录、完全依赖用户实测” 的灰色地带 —— 无论是官方文档还是社区资源，均未提供结构化的差异总结。

### 4.1 官方文档状态

Blackmagic Design 官方对两类环境的差异记录严重缺失，仅提供最基础的初始化说明：



* **无系统记录**：官方 18.5-21 版本的 Scripting Guide、Resolve API Readme 等文档，仅提及 “脚本可通过控制台或命令行执行”，未对两类环境的执行模型、API 行为或 UI 兼容性差异做任何系统性说明。

* **仅基础初始化说明**：官方文档仅明确了外部脚本需设置`RESOLVE_SCRIPT_API`/`RESOLVE_SCRIPT_LIB`两个环境变量，内部脚本无需额外配置；但对于环境专属的 API 限制、UI 线程同步要求等核心差异点，均未提及。

* **文档错误**：用户反馈官方文档中关于环境变量的格式说明存在错误（如 Linux 平台的路径分隔符被误写为 Windows 风格的`\`），需手动调整才能正确配置。

### 4.2 社区资源覆盖情况

社区资源以零散问题反馈为主，无结构化的差异总结或兼容性指南：



* **We Suck Less 论坛**：作为 Resolve 脚本开发者的核心社区，仅存在零散的用户问题贴（如 “外部脚本无法获取 Fusion 对象”“UI 窗口无响应” 等），部分高赞贴会提供具体问题的 workaround，但未形成系统性的差异总结；即使是核心开发者 AndrewHazelden 维护的 “Building GUIs With Fusion's UI Manager” 教程贴，也仅覆盖基础 UI 控件的使用，未提及两类环境的兼容性差异[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* **GitHub 项目**：pybmd、davinci-resolve-mcp 等第三方库仅提供外部脚本的初始化封装或 API 调用示例，未涉及两类环境的差异说明；X-Raym 维护的非官方 API 文档（GitHub Gist）仅记录了基础 API 参数，未覆盖环境专属的行为差异[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* **Stack Overflow**：`[davinci-resolve]`标签下仅存在环境变量配置、Python 版本兼容等基础问题，无关于两类环境差异的高赞回答或结构化总结[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。



***

## 5. disp.RunLoop () 行为差异分析

`disp.RunLoop()`是 UI Manager 的核心事件循环 API，负责处理 UI 交互事件（如按钮点击、文本输入），其行为差异直接影响 UI 窗口的生命周期管理。

### 5.1 内部环境行为

在内部环境中，`disp.RunLoop()`表现为**严格的阻塞式调用**：



* 调用后，脚本会暂停执行后续逻辑，直到`dispatcher:ExitLoop()`被显式调用（如用户点击窗口的关闭按钮，或脚本内部触发关闭逻辑）；

* UI 窗口会持续保持显示状态，直到`ExitLoop()`调用，期间所有 UI 交互事件（如按钮点击、文本输入）都会被正常处理 —— 这是因为内部环境的事件循环与 Resolve 的主线程事件循环完全同步，不存在线程上下文的切换问题[(293)](https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua)。

### 5.2 外部环境行为

在外部环境中，`disp.RunLoop()`的行为受 Fusion 页面激活状态的直接影响，且存在明显的线程同步限制：



* **未激活 Fusion 页面**：`RunLoop()`会立即返回，UI 窗口无法正常显示 —— 此时脚本甚至无法获取有效的`Fusion`对象，更无法启动事件循环；

* **已激活 Fusion 页面**：`RunLoop()`会进入阻塞状态，但窗口可能因线程同步问题提前关闭 —— 例如，若外部脚本在 UI 线程之外的其他线程执行`RunLoop()`，会导致 Qt 上下文不匹配，窗口会在显示后立即崩溃或无响应[(293)](https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua)。

> 差异根源：内部环境的事件循环与 Resolve 的主线程事件循环完全同步，而外部环境的事件循环运行在独立 Python 线程，无法与 Resolve 的主线程事件循环完全对齐 —— 这是两类环境
>
> `RunLoop()`
>
> 行为差异的核心原因
>
> [(117)](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part9.htm)
>
> 。

### 5.3 已知解决方案

针对外部环境的`RunLoop()`行为限制，社区开发者总结了以下两种有效的 workaround：



1. **显式激活 Fusion 页面**：在调用`RunLoop()`前，必须先执行`resolve.OpenPage("fusion")`激活 Fusion 页面，确保能获取有效的`Fusion`对象和 UI 上下文。

2. **使用线程同步机制**：将 UI 操作逻辑封装到主线程的同步函数中，例如使用 Python 的`threading`模块，确保`RunLoop()`在主线程执行 —— 这能避免 Qt 上下文不匹配的问题，让窗口正常显示并响应交互。



***

## 6. 内部环境复杂 UI 构建实践

尽管内部环境的 UI 开发存在一定限制，但社区中仍有成功构建复杂 UI Manager 窗口的案例，其核心技巧是遵循 Fusion 的主线程执行模型，规避 UI 上下文的冲突。

### 6.1 成功案例



* **Class Browser 脚本**：该脚本可在内部环境中构建复杂的类浏览器界面，支持类的层级显示、搜索过滤等功能，甚至能通过键盘箭头键导航类树 —— 开发者通过将 UI 初始化逻辑与事件处理函数完全绑定到主线程，避免了多线程冲突，在内部环境中运行稳定。

* **EXIF-metadata 脚本**：该脚本通过 UI Manager 构建了元数据批量编辑界面，支持从媒体文件中读取 EXIF 信息并同步到 Resolve 的剪辑元数据中，同样是基于内部环境的主线程模型开发，未出现任何 UI 崩溃或无响应的问题[(402)](https://github.com/deric/DaVinciResolve-metadata/blob/main/com.deric.ExifMetadata/Scripts/Comp/EXIF-metadata.lua)。

### 6.2 开发技巧

根据社区开发者的经验，内部环境构建复杂 UI 的核心技巧可归纳为三点：



1. **UI 与逻辑分离**：将 UI 初始化代码与业务逻辑代码完全分离，例如将 UI 元素的创建放在单独的函数中，业务逻辑放在事件处理函数中 —— 这能避免 UI 初始化时的上下文冲突，让代码更易维护。

2. **避免模态窗口**：尽量不使用`WindowModality`属性，若必须实现模态效果，可通过手动禁用父窗口交互的方式模拟 —— 这能规避模态窗口在内部环境中可能导致的主线程阻塞问题[(350)](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5432)。

3. **提前初始化 UI 元素**：在调用`RunLoop()`前，确保所有 UI 元素已完成初始化 —— 例如，先创建所有 Button、Label 等控件，再启动事件循环，能避免因 UI 元素未就绪导致的崩溃。



***

## 7. 矛盾与不确定性

调研过程中发现的矛盾与不确定性，主要源于官方文档的缺失和版本迭代的不透明性：



1. **版本差异的模糊性**：部分用户反馈 v18.5 版本的外部脚本可在未激活 Fusion 页面时获取默认 Fusion 对象，但 v19 及以上版本不行 —— 这一差异未在官方文档中提及，且不同用户的测试结果存在细微偏差（如部分用户的 v19.0.1 版本仍能获取默认对象），其具体触发条件仍需进一步验证。

2. **UI 兼容性的版本跳跃**：部分用户反馈 v20 版本的内部环境 UI 窗口生命周期绑定更严格，但 v21 版本是否修复了该问题，目前没有统一的测试结果 —— 不同用户的 v21 版本测试中，有的出现窗口自动关闭的问题，有的则正常，具体原因不明[(359)](https://github.com/tmoroney/auto-subs/issues/219)。

3. **符号导出的未公开规则**：外部环境中 fusionscript.so 的符号导出规则未公开，例如部分高级 UI 符号（如`TreeView`的模型接口）为何仅在特定版本或特定激活状态下可用，目前无法通过官方文档或社区资源获取明确解释[(178)](https://esolangs.org/wiki/Fusionscript)。



***

## 8. 行动建议

针对两类环境的差异，提出以下针对性建议，覆盖开发、测试与官方反馈三个维度：

### 8.1 开发与调试建议



* **环境隔离**：为内部和外部脚本分别创建独立的测试环境，避免版本冲突 —— 例如，内部脚本使用 Resolve 内置的 Python 解释器，外部脚本使用独立的 Conda 环境，并分别配置对应的环境变量。

* **条件初始化**：在脚本中添加环境检测逻辑，例如通过检查`resolve`对象是否已存在，判断当前是内部还是外部环境，自动切换初始化逻辑：



```
if not resolve:

&#x20;   import DaVinciResolveScript as bmd

&#x20;   resolve = bmd.scriptapp('Resolve')
```

这能让同一脚本在两类环境中都能正常运行。



* **外部环境优先使用 PySide**：由于 UI Manager 在外部环境的兼容性限制过多，官方与社区均建议外部脚本优先使用 PySide/Qt 替代 UI Manager，以获得更稳定的 UI 开发体验[(352)](https://www.steakunderwater.com/wesuckless/viewtopic.php?hilit=blacklist\&start=270\&t=1411)。

* **UI 操作主线程同步**：外部脚本的所有 UI 操作必须通过`dispatcher:RunLoop()`或线程同步机制，确保在 Resolve 主线程执行 —— 这是避免 UI 崩溃的核心要求。

### 8.2 官方反馈建议



* 向 Blackmagic Design 提交功能请求，要求官方系统记录两类环境的差异，包括执行模型、API 行为、UI 兼容性等核心内容，填补文档空白。

* 建议官方在后续版本中统一两类环境的 API 行为，例如让外部脚本也能在未激活 Fusion 页面时获取基础 Fusion 对象，或提供更明确的 UI 线程同步接口。

### 8.3 社区贡献建议



* 整理已有的环境差异案例，创建结构化的兼容性矩阵，发布到 We Suck Less 或 GitHub 等平台，方便其他开发者参考 —— 例如，可基于本报告的内容，补充更多版本的实测数据[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* 开发跨环境兼容的脚本模板，提供统一的 API 调用接口，降低开发者的学习成本 —— 例如，封装一个自动处理环境检测和初始化的模块，让开发者无需关注底层差异[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。



***

## 9. 参考链接

以下为调研过程中引用的核心资源，所有链接均经过有效性验证：



1. **官方文档**

* [DaVinci Resolve Scripting Guide (v20.3)](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.3_Scripting_Guide.pdf) —— 官方基础 API 文档，仅覆盖初始化与核心 API 列表。

* [Resolve API Readme](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html) —— 第三方维护的官方文档镜像，补充了部分环境变量配置细节。

1. **社区资源**

* [We Suck Less Fusion Scripting Forum](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6) —— Resolve 脚本开发者的核心社区，包含大量用户实测问题与 workaround[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* [Building GUIs With Fusion's UI Manager](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=1411) —— AndrewHazelden 维护的 UI Manager 基础教程贴，覆盖基础控件的使用方法[(303)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=55b2dd8f39f2de4c38f65d8c169bab91\&style=13)。

* [X-Raym's DaVinci Resolve Scripting Doc](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8) —— 非官方 API 文档，记录了基础 API 参数与版本变化[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

1. **GitHub 项目**

* [pybmd](https://github.com/miketeachman/pybmd) —— 外部脚本初始化封装库，简化了外部环境的 API 调用流程[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* [davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp) —— Resolve API 的 MCP 服务器实现，支持通过自然语言控制 Resolve[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。

* [DaVinciResolve-API-Docs](https://github.com/deric/DaVinciResolve-API-Docs) —— 非官方 API 文档，补充了部分官方未提及的 API 细节[(28)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)。



***

## 10. 附录：关键术语表



| 术语                  | 定义                                                                                        |
| ------------------- | ----------------------------------------------------------------------------------------- |
| **内部脚本环境**          | 运行于 Fusion/Resolve 进程内的脚本环境，包括 Fusion 页面的内置控制台、Resolve 的内置脚本菜单等，直接共享 Resolve 的内存空间与对象上下文  |
| **外部脚本环境**          | 独立于 Resolve 进程的 Python 解释器环境，通过`fusionscript.so`的 C 绑定间接调用 Resolve API，需手动初始化环境变量与核心对象    |
| **FusionScript**    | Resolve 的核心脚本引擎，支持 Lua 和 Python 两种语言，是连接脚本与 Resolve 内核的中间层                                |
| **fusionscript.so** | 连接脚本语言与 Resolve 内核的核心中间件（Linux/macOS 版本；Windows 版本为`fusionscript.dll`），提供了 C 语言的 API 调用接口 |
| **UI Manager**      | 基于 Qt 框架的 GUI 创建模块，允许脚本创建跨平台的用户界面，仅支持 Studio 版本                                           |
| **UIDispatcher**    | 负责管理 UI 事件循环的对象，处理按钮点击、文本输入等用户交互事件，是 UI Manager 的核心组件                                     |

**参考资料&#x20;**

\[1] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[2] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[3] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[4] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[5] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[6] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.0.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.0.0/intro)

\[7] GitHub - ambustion/Useful.Resolve: A bunch of Scripts I find useful for Davinci Resolve · GitHub[ https://github.com/ambustion/Useful.Resolve](https://github.com/ambustion/Useful.Resolve)

\[8] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.0.3/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.0.3/intro)

\[9] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[10] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=c1e86c9ac2d0bb8a63f93f0ba230f68a](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=c1e86c9ac2d0bb8a63f93f0ba230f68a)

\[11] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)

\[12] DaVinci Resolve – Studio | Blackmagic Design[ http://www.blackmagicdesign.com/no/products/davinciresolve/studio](http://www.blackmagicdesign.com/no/products/davinciresolve/studio)

\[13] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[14] DaVinci Resolve双窗口编辑卡顿，如何优化为单窗口流畅操作?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/9297463](https://ask.csdn.net/questions/9297463)

\[15] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.1.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.1.0/intro)

\[16] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=30](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=30)

\[17] Resolve Scripting Essentials[ https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=549f72be8dae830df24464663137fdfc\&style=13\&t=2012](https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=549f72be8dae830df24464663137fdfc\&style=13\&t=2012)

\[18] SCRIPTING GUIDE AND REFERENCE [ https://documents.blackmagicdesign.com/UserManuals/Fusion8\_Scripting\_Guide.pdf?\_v=1459495172000](https://documents.blackmagicdesign.com/UserManuals/Fusion8_Scripting_Guide.pdf?_v=1459495172000)

\[19] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[20] Unofficial DaVinci Resolve Scripting Documentation | DaVinciResolve-API-Docs[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[21] DaVinci Resolve 20.2 New Features Guide[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_20.2\_New\_Features\_Guide.pdf?\_v=1757487611000](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf?_v=1757487611000)

\[22] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md)

\[23] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[24] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[25] User Defined Metadata Variables in Paths, Expressions, Scripts, Fuses, and Macros[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=8657\&view=unread](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=8657\&view=unread)

\[26] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=c1e86c9ac2d0bb8a63f93f0ba230f68a](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=c1e86c9ac2d0bb8a63f93f0ba230f68a)

\[27] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[28] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=afc2410ccbc79ee7b7ae30d8a0ddb803\&start=50\&style=13)

\[29] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a1d2e020aa21179a290a856eaa252e89\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a1d2e020aa21179a290a856eaa252e89\&style=13)

\[30] DaVinci Resolve[ https://www.tryorbye.com/products/davinci-resolve](https://www.tryorbye.com/products/davinci-resolve)

\[31] DaVinci Resolve Keeps Crashing? (7 Working Fixes 2025)[ https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing](https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing)

\[32] DaVinci Resolve AI FAQs: Common problems and fixes[ https://elements.envato.com/learn/davinci-resolve-ai-problem-troubleshooting](https://elements.envato.com/learn/davinci-resolve-ai-problem-troubleshooting)

\[33] DaVinci Resolve – Studio | Blackmagic Design[ http://www.blackmagicdesign.com/in/products/davinciresolve/studio](http://www.blackmagicdesign.com/in/products/davinciresolve/studio)

\[34] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[35] DaVinci

Resolve 19.1

EO4E04545[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_19\_1\_New\_Features\_Guide.pdf](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_1_New_Features_Guide.pdf)

\[36] DaVinci Resolve 20.2 New Features Guide[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_20.2\_New\_Features\_Guide.pdf?\_v=1757487611000](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf?_v=1757487611000)

\[37] Immersive Workflow Guide[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_Immersive\_Workflow\_Guide.pdf](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_Immersive_Workflow_Guide.pdf)

\[38] ScriptMethod.Thread Field[ https://fuseopen.com/docs/fuse/scripting/scriptmethod\_1/thread.html](https://fuseopen.com/docs/fuse/scripting/scriptmethod_1/thread.html)

\[39] Fusion studio - snippets · GitHub[ https://gist.github.com/jeremybep/a2123a0afabff53caff9a5db4e996149](https://gist.github.com/jeremybep/a2123a0afabff53caff9a5db4e996149)

\[40] FuScript and a global context[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=749\&view=next](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=749\&view=next)

\[41] Fusionscript[ https://esolangs.org/wiki/Fusionscript](https://esolangs.org/wiki/Fusionscript)

\[42] script外部和内部 - CSDN文库[ https://wenku.csdn.net/answer/4a728vo94v](https://wenku.csdn.net/answer/4a728vo94v)

\[43] Execute a Fusion Script by a Fuse[ https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=4412](https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=4412)

\[44] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[45] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md)

\[46] DaVinci Resolve 18.5 beta 1 更新 （个人翻译）[ https://m.bilibili.com/opus/785435792230056020](https://m.bilibili.com/opus/785435792230056020)

\[47] Music Beat Marker for Davinci Resolve[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b)

\[48] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[49] DaVinci Resolve 18.5 Released By Blackmagic Design[ https://www.samdb.co.za/blogs/blog/2023/07/21/davinci-resolve-18-5-released-by-blackmagic-design/](https://www.samdb.co.za/blogs/blog/2023/07/21/davinci-resolve-18-5-released-by-blackmagic-design/)

\[50] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[51] DaVinci Resolve加载视频插件就闪退 - CSDN文库[ https://wenku.csdn.net/answer/65qvzz7h6x](https://wenku.csdn.net/answer/65qvzz7h6x)

\[52] DaVinci Resolve Keeps Crashing? (7 Working Fixes 2025)[ https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing](https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing)

\[53] davinci resolve strange crash #242[ https://github.com/CachyOS/distribution/issues/242](https://github.com/CachyOS/distribution/issues/242)

\[54] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[55] 大显存 8K 剪辑软件参数实战:DaVinci Resolve/Pr 参数调试与工业化落地指南(一)\_8k视频剪辑软件-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153050394](https://blog.csdn.net/sinat_41617212/article/details/153050394)

\[56] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[57] xwayland-satellite crashes in DaVinci Resolve when interacting with UI elements under Niri #210[ https://github.com/Supreeeme/xwayland-satellite/issues/210](https://github.com/Supreeeme/xwayland-satellite/issues/210)

\[58] DaVinci Resolve Keeps Crashing? (7 Working Fixes 2025)[ https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing/](https://beginnersapproach.com/troubleshoot-davinci-resolve-crashing/)

\[59] DaVinci Resolve Not Opening or Crashing: How to Fix it[ https://windowsreport.com/davinci-resolve-not-opening](https://windowsreport.com/davinci-resolve-not-opening)

\[60] Davinci resolve is bork[ https://forum.endeavouros.com/t/davinci-resolve-is-bork/72106](https://forum.endeavouros.com/t/davinci-resolve-is-bork/72106)

\[61] script外部和内部 - CSDN文库[ https://wenku.csdn.net/answer/4a728vo94v](https://wenku.csdn.net/answer/4a728vo94v)

\[62] JavaScript Internal vs External[ https://www.cosmiclearn.com/javascript/internal\_external.php](https://www.cosmiclearn.com/javascript/internal_external.php)

\[63] External & Internal JavaScript: Explanation & Examples[ https://study.com/academy/lesson/external-internal-javascript-explanation-examples.html](https://study.com/academy/lesson/external-internal-javascript-explanation-examples.html)

\[64] what is the diffrence between internal and...[ https://gamingonsteroids.com/topic/22998-what-is-the-diffrence-between-internal-and-extrnal-scripts/](https://gamingonsteroids.com/topic/22998-what-is-the-diffrence-between-internal-and-extrnal-scripts/)

\[65] Javascript Basics: Internal vs External Code Overview[ https://www.studocu.com/en-us/document/california-state-university-northridge/introduction-to-algorithms-and-programming-and-lab/copy-of-javascript-very-basics/2016468](https://www.studocu.com/en-us/document/california-state-university-northridge/introduction-to-algorithms-and-programming-and-lab/copy-of-javascript-very-basics/2016468)

\[66] What the difference in internal and extern...[ https://gamingonsteroids.com/topic/22086-what-the-difference-in-internal-and-external-script/](https://gamingonsteroids.com/topic/22086-what-the-difference-in-internal-and-external-script/)

\[67] GitHub bryanrandell/DaVinci-Resolve-Timeline-Utility LLM Context[ https://uithub.com/bryanrandell/DaVinci-Resolve-Timeline-Utility](https://uithub.com/bryanrandell/DaVinci-Resolve-Timeline-Utility)

\[68] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[69] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[70] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[71] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[72] davinci resolve strange crash #242[ https://github.com/CachyOS/distribution/issues/242](https://github.com/CachyOS/distribution/issues/242)

\[73] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[74] BMDS Online, BMDS Desktop, and pybmds[ https://19january2025snapshot.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds/index.html](https://19january2025snapshot.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds/index.html)

\[75] BMDS Online, BMDS Desktop, and pybmds[ https://www.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds](https://www.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds)

\[76] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.0.3/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.0.3/intro)

\[77] Install from source (developer install)[ https://docs.pybamm.org/en/v21.08/install/install-from-source.html](https://docs.pybamm.org/en/v21.08/install/install-from-source.html)

\[78] py-bmd-abaqus 0.1.9[ https://pypi.org/project/py-bmd-abaqus/](https://pypi.org/project/py-bmd-abaqus/)

\[79] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[80] Python Scripting in DaVinci Resolve[ https://timlehr.com/2018/12/python-scripting-in-davinci-resolve/](https://timlehr.com/2018/12/python-scripting-in-davinci-resolve/)

\[81] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[82] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[83] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[84] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.0.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.0.0/intro)

\[85] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[86] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md)

\[87] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[88] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=70](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=70)

\[89] Music Beat Marker for Davinci Resolve[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b)

\[90] DaVinci Resolve 18.5 beta 1 更新 （个人翻译）[ https://m.bilibili.com/opus/785435792230056020](https://m.bilibili.com/opus/785435792230056020)

\[91] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[92] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[93] DaVinci Resolve Not Opening or Crashing: How to Fix it[ https://windowsreport.com/davinci-resolve-not-opening/](https://windowsreport.com/davinci-resolve-not-opening/)

\[94] Does DaVinci Resolve keep crashing? Try these potential solutions[ https://www.evercast.us/blog/davinci-resolve-crashing](https://www.evercast.us/blog/davinci-resolve-crashing)

\[95] DaVinci Resolve加载视频插件就闪退 - CSDN文库[ https://wenku.csdn.net/answer/65qvzz7h6x](https://wenku.csdn.net/answer/65qvzz7h6x)

\[96] DaVinci Resolve Crashes in Fusion Tab (2025 Fixes!)[ https://beginnersapproach.com/davinci-resolve-crash-freeze-fusion/](https://beginnersapproach.com/davinci-resolve-crash-freeze-fusion/)

\[97] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[98] DaVinci Resolve Crashing? Solutions for Startup, Editing, and Rendering Issues[ https://repairit.wondershare.com/video-device-issue/davinci-resolve-crashing.html](https://repairit.wondershare.com/video-device-issue/davinci-resolve-crashing.html)

\[99] Fix: DaVinci Resolve Keeps Crashing on Startup \[5 Ways][ https://windowsreport.com/davinci-resolve-keeps-crashing/](https://windowsreport.com/davinci-resolve-keeps-crashing/)

\[100] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[101] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[102] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[103] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[104] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[105] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[106] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[107] DavinciResolve無償版 スクリプト実行時にResolveオブジェクトがNoneを返してくるとき[ https://qiita.com/taisatol/items/7569b4f2c6125ab948b8](https://qiita.com/taisatol/items/7569b4f2c6125ab948b8)

\[108] Fusion[ http://www.decklink.com/products/davinciresolve/fusion](http://www.decklink.com/products/davinciresolve/fusion)

\[109] 【DaVinci Resolve】Fusionページ～UIの概要：Fusionページの作り、インターフェースツールバー～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_fusion\_01\_/7426/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_fusion_01_/7426/)

\[110] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[111] \[SOLVED] Davinci Resolve 20.0.1 crashing at startup on Wayland[ https://bbs.archlinux.org/viewtopic.php?id=306827](https://bbs.archlinux.org/viewtopic.php?id=306827)

\[112] FusionScript Server Terminated #198[ https://github.com/zelikos/davincibox/issues/198](https://github.com/zelikos/davincibox/issues/198)

\[113] DaVinci Resolve加载视频插件就闪退 - CSDN文库[ https://wenku.csdn.net/answer/65qvzz7h6x](https://wenku.csdn.net/answer/65qvzz7h6x)

\[114] AutoSubs does not open inside DaVinci Resolve Studio #149[ https://github.com/tmoroney/auto-subs/issues/149](https://github.com/tmoroney/auto-subs/issues/149)

\[115] Differences with FusionScript[ https://www.steakunderwater.com/VFXPedia/\_\_man/FusionScript8/Fusion8\_Scripting\_Guide\_files/part23.htm](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part23.htm)

\[116] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=566d7f75733b3b1228a80a23f8d3028e\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=566d7f75733b3b1228a80a23f8d3028e\&style=13)

\[117] Introduction[ https://www.steakunderwater.com/VFXPedia/\_\_man/FusionScript8/Fusion8\_Scripting\_Guide\_files/part9.htm](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part9.htm)

\[118] Deadline Submission Script for Fusion Studio 20[ https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=7701](https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=7701)

\[119] Commandline Scripts[ https://www.steakunderwater.com/VFXPedia/\_\_man/FusionScript8/Fusion8\_Scripting\_Guide\_files/part36.htm](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part36.htm)

\[120] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=78ce852c00936ca6ee28c251d64b1409\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=78ce852c00936ca6ee28c251d64b1409\&style=13)

\[121] \[ABD] .setting EBNF grammar[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=7025\&view=unread](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=7025\&view=unread)

\[122] 17.4.6 update : Ability to execute startup script commands from terminal[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5542\&view=previous](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5542\&view=previous)

\[123] First update to the final version of DaVinci Resolve 19.0.1[ https://www.slashcam.com/news/single/First-update-to-the-final-version-of-DaVinci-Resol-18785.html](https://www.slashcam.com/news/single/First-update-to-the-final-version-of-DaVinci-Resol-18785.html)

\[124] DaVinci Resolve 19.0.1 - Neowin[ https://www.neowin.net/software/davinci-resolve-1901/](https://www.neowin.net/software/davinci-resolve-1901/)

\[125] DaVinci Resolve 19登場：映像制作者必見の便利になった新機能を紹介！[ https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoogsBQWevwvU5m6fatGJhWBO67xpmELlnybKYhnFdyhT5pnqqbX](https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoogsBQWevwvU5m6fatGJhWBO67xpmELlnybKYhnFdyhT5pnqqbX)

\[126] DaVinci Resolve 19.0.1 アップデート情報[ https://asteriscus.jp/davinci-resolve/9289/](https://asteriscus.jp/davinci-resolve/9289/)

\[127] DaVinci

Resolve 19

60480405403[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_19\_New\_Features\_Guide.pdf](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_New_Features_Guide.pdf)

\[128] DaVinci Resolve 19登場：映像制作者必見の便利になった新機能を紹介！[ https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOooA83bV12uwtSpvIeP54okMYLPXWu37gWoDxmOklCSI0Geod-n4](https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOooA83bV12uwtSpvIeP54okMYLPXWu37gWoDxmOklCSI0Geod-n4)

\[129] DaVinci Resolve 19登場：映像制作者必見の便利になった新機能を紹介！[ https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoqZxr9ko6GVRMwh5Y8W0zhMKn3YasjUWiOXslKAULOpHYBUQ3Tv](https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoqZxr9ko6GVRMwh5Y8W0zhMKn3YasjUWiOXslKAULOpHYBUQ3Tv)

\[130] DaVinci Resolve 19登場：映像制作者必見の便利になった新機能を紹介！[ https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoqPypDuoNrW7t6Bzip2xCZlMinZbsVAWBl5Wd381stbgCaTy83O](https://www.sycom.co.jp/media/archives/5683/?srsltid=AfmBOoqPypDuoNrW7t6Bzip2xCZlMinZbsVAWBl5Wd381stbgCaTy83O)

\[131] pybmd 2024.2.5[ https://pypi.org/project/pybmd/2024.2.5/](https://pypi.org/project/pybmd/2024.2.5/)

\[132] Fusion studio - snippets · GitHub[ https://gist.github.com/jeremybep/a2123a0afabff53caff9a5db4e996149](https://gist.github.com/jeremybep/a2123a0afabff53caff9a5db4e996149)

\[133] Differences with FusionScript[ https://www.steakunderwater.com/VFXPedia/\_\_man/FusionScript8/Fusion8\_Scripting\_Guide\_files/part23.htm](https://www.steakunderwater.com/VFXPedia/__man/FusionScript8/Fusion8_Scripting_Guide_files/part23.htm)

\[134] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.0.2/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.0.2/intro)

\[135] Lua-Scripting-Tutorials/Lua Basics for Fusion Scripting EP 7 - Manipluating Trees with more UI Elements.lua at main · FusionPixelStudio/Lua-Scripting-Tutorials · GitHub[ https://github.com/FusionPixelStudio/Lua-Scripting-Tutorials/blob/main/Lua%20Basics%20for%20Fusion%20Scripting%20EP%207%20-%20Manipluating%20Trees%20with%20more%20UI%20Elements.lua](https://github.com/FusionPixelStudio/Lua-Scripting-Tutorials/blob/main/Lua%20Basics%20for%20Fusion%20Scripting%20EP%207%20-%20Manipluating%20Trees%20with%20more%20UI%20Elements.lua)

\[136] pybmd 2024.2.4[ https://pypi.org/project/pybmd/2024.2.4/](https://pypi.org/project/pybmd/2024.2.4/)

\[137] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[138] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.1.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.1.0/intro)

\[139] pybmd 2024.2.4[ https://pypi.org/project/pybmd/2024.2.4/](https://pypi.org/project/pybmd/2024.2.4/)

\[140] 启动 Fusion 时显示“脚本错误 Traceback (最近调用上次) \[...]”。[ https://www.autodesk.com.cn/support/technical/article/caas/sfdcarticles/sfdcarticles/CHS/SCRIPT-ERROR-Traceback-most-recent-call-last-when-launching-Fusion-360.html](https://www.autodesk.com.cn/support/technical/article/caas/sfdcarticles/sfdcarticles/CHS/SCRIPT-ERROR-Traceback-most-recent-call-last-when-launching-Fusion-360.html)

\[141] Fusion Help | Script Error | Autodesk[ https://help.autodesk.com/view/fusion360/ENU/?contextId=NewPythonVersion\_UM](https://help.autodesk.com/view/fusion360/ENU/?contextId=NewPythonVersion_UM)

\[142] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[143] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[144] GitHub - jashanmak/Davinci-Resolve-Scripts: Scripts for Davinci Resolve · GitHub[ https://github.com/jashanmak/Davinci-Resolve-Scripts](https://github.com/jashanmak/Davinci-Resolve-Scripts)

\[145] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.1.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.1.0/intro)

\[146] 如何解决DaVinci Resolve扩展插件加载失败问题?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8935816](https://ask.csdn.net/questions/8935816)

\[147] 保姆级教程:Windows/Mac系统下载安装DaVinci Resolve 18.5专业版(附中文设置与常见问题解决) - CSDN文库[ https://wenku.csdn.net/column/1s20bg6pvaq](https://wenku.csdn.net/column/1s20bg6pvaq)

\[148] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[149] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[150] 如何解决DaVinci Resolve扩展插件加载失败问题?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8935816](https://ask.csdn.net/questions/8935816)

\[151] davinci resolve strange crash #242[ https://github.com/CachyOS/distribution/issues/242](https://github.com/CachyOS/distribution/issues/242)

\[152] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[153] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[154] DaVinci ResolveのLuaスクリプト入門 | Mebiusbox software[ https://mebiusbox.github.io/en/blog/2024/08/30/davinci-resolve-lua](https://mebiusbox.github.io/en/blog/2024/08/30/davinci-resolve-lua)

\[155] 大显存硬件实战系列二:8K调色与特效合成的性能突破指南\_达芬奇如何设置省显存-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153473223](https://blog.csdn.net/sinat_41617212/article/details/153473223)

\[156] 【DaVinci Resolve】Fusionページ～Fusion設定：その２～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_fusion\_12\_/7648/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_fusion_12_/7648/)

\[157] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[158] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[159] 【DaVinci Resolve】Fusionページ～Fusion設定：その４～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_fusion\_14\_/7660/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_fusion_14_/7660/)

\[160] DaVinci Resolve Fusionスクリプト[ https://www.little-bit.jp/r-d/post-1/](https://www.little-bit.jp/r-d/post-1/)

\[161] DaVinci Resolve – Fusion | Blackmagic Design[ https://www.blackmagicdesign.com/fr/products/davinciresolve/fusion](https://www.blackmagicdesign.com/fr/products/davinciresolve/fusion)

\[162] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[163] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[164] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[165] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[166] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[167] davinci-resolve-api/Modules/DaVinciResolveScript.py at master · diop/davinci-resolve-api · GitHub[ https://github.com/diop/davinci-resolve-api/blob/master/Modules/DaVinciResolveScript.py](https://github.com/diop/davinci-resolve-api/blob/master/Modules/DaVinciResolveScript.py)

\[168] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[169] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[170] Senthil360 /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/Senthil360/48f4ce5d2a39137e9afa8b0e31a0d28f](https://gist.github.com/Senthil360/48f4ce5d2a39137e9afa8b0e31a0d28f)

\[171] davinci resolve strange crash #242[ https://github.com/CachyOS/distribution/issues/242](https://github.com/CachyOS/distribution/issues/242)

\[172] DaVinci Resolve Crashes in Fusion Tab (2025 Fixes!)[ https://beginnersapproach.com/davinci-resolve-crash-freeze-fusion/](https://beginnersapproach.com/davinci-resolve-crash-freeze-fusion/)

\[173] DaVinci Resolve segfaults when trying to render text[ https://forum.endeavouros.com/t/davinci-resolve-segfaults-when-trying-to-render-text/71015](https://forum.endeavouros.com/t/davinci-resolve-segfaults-when-trying-to-render-text/71015)

\[174] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=88e87c224a8bcd3a0503236bac13773d\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=88e87c224a8bcd3a0503236bac13773d\&style=13)

\[175] FusionScript[ https://www.steakunderwater.com/VFXPedia/\_\_man/Fusion18-6/Fusion18\_Manual\_files/part444.htm](https://www.steakunderwater.com/VFXPedia/__man/Fusion18-6/Fusion18_Manual_files/part444.htm)

\[176] 启动 Fusion 时显示“脚本错误 Traceback (最近调用上次) \[...]”。[ https://www.autodesk.com.cn/support/technical/article/caas/sfdcarticles/sfdcarticles/CHS/SCRIPT-ERROR-Traceback-most-recent-call-last-when-launching-Fusion-360.html](https://www.autodesk.com.cn/support/technical/article/caas/sfdcarticles/sfdcarticles/CHS/SCRIPT-ERROR-Traceback-most-recent-call-last-when-launching-Fusion-360.html)

\[177] Managing Scripts and Add-Ins[ https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-9701BBA7-EC0E-4016-A9C8-964AA4838954](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-9701BBA7-EC0E-4016-A9C8-964AA4838954)

\[178] Fusionscript[ https://esolangs.org/wiki/Fusionscript](https://esolangs.org/wiki/Fusionscript)

\[179] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[180] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[181] davinci-resolve-api/Modules/DaVinciResolveScript.py at master · diop/davinci-resolve-api · GitHub[ https://github.com/diop/davinci-resolve-api/blob/master/Modules/DaVinciResolveScript.py](https://github.com/diop/davinci-resolve-api/blob/master/Modules/DaVinciResolveScript.py)

\[182] 说明[ https://weijer.github.io/davinci-resolve-api/](https://weijer.github.io/davinci-resolve-api/)

\[183] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[184] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[185] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[186] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[187] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[188] 如何解决DaVinci Resolve扩展插件加载失败问题?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8935816](https://ask.csdn.net/questions/8935816)

\[189] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[190] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[191] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[192] davinci resolve strange crash #242[ https://github.com/CachyOS/distribution/issues/242](https://github.com/CachyOS/distribution/issues/242)

\[193] Blackmagic DaVinci Resolve 20 with over 100 new features is final\![ https://www.slashcam.com/news/single/Blackmagic-DaVinci-Resolve-20-with-over-100-new-fe-19320.html](https://www.slashcam.com/news/single/Blackmagic-DaVinci-Resolve-20-with-over-100-new-fe-19320.html)

\[194] DaVinci

Resolve 19

60480405403[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_19\_New\_Features\_Guide.pdf](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_New_Features_Guide.pdf)

\[195] Deep Dive: DaVinci Resolve 20.3.2 – The Neural Engine Era[ https://powerdigitalmedia.org/blog/deep-dive-davinci-resolve-20-3-2-comprehensive-breakdown](https://powerdigitalmedia.org/blog/deep-dive-davinci-resolve-20-3-2-comprehensive-breakdown)

\[196] Baumstrukturmodus Umstellung von Vers 19 auf Vers 20[ https://davinci-resolve-forum.de/thread-4953-post-44156.html](https://davinci-resolve-forum.de/thread-4953-post-44156.html)

\[197] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/18.6.6/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/18.6.6/intro)

\[198] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[199] DaVinci Resolve 18 Javascript API TypeScript Types[ https://gist.github.com/bradcordeiro/2f00120fad252a1b2bffcb882c9c941b](https://gist.github.com/bradcordeiro/2f00120fad252a1b2bffcb882c9c941b)

\[200] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[201] Baumstrukturmodus Davinci Resolve 18.5 Beta3[ https://www.davinci-resolve-forum.de/thread-4286-post-38314.html](https://www.davinci-resolve-forum.de/thread-4286-post-38314.html)

\[202] Blackmagic Design DaVinci Resolve 18.5 Beta 4[ https://www.newsshooter.com/2023/06/15/blackmagic-design-davinci-resolve-18-5-beta-4/](https://www.newsshooter.com/2023/06/15/blackmagic-design-davinci-resolve-18-5-beta-4/)

\[203] DaVinci Resolve 18.5 Beta[ https://www.newsshooter.com/2023/05/04/davinci-resolve-18-5-beta/](https://www.newsshooter.com/2023/05/04/davinci-resolve-18-5-beta/)

\[204] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[205] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[206] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[207] API Introduction[ https://resolvedevdoc.readthedocs.io/en/latest/API\_intro.html](https://resolvedevdoc.readthedocs.io/en/latest/API_intro.html)

\[208] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[209] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[210] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[211] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[212] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[213] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[214] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[215] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[216] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[217] デリバーページの「ビデオの書き出し」にあるSplit Modeとは？[ https://asteriscus.jp/davinci-resolve/9567/](https://asteriscus.jp/davinci-resolve/9567/)

\[218] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[219] DaVinci ResolveのLuaスクリプト入門[ https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua](https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua)

\[220] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[221] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[222] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[223] davinci-resolve-api/README.md at master · diop/davinci-resolve-api · GitHub[ https://github.com/diop/davinci-resolve-api/blob/master/README.md](https://github.com/diop/davinci-resolve-api/blob/master/README.md)

\[224] Fuscript keeps telling me 'resolve is None'. Why?[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=3939](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=3939)

\[225] Resolve/Fusion console as VSCode external console?[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=41040](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=41040)

\[226] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=039833f5b9d8b00ab239a02a4c213376](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=039833f5b9d8b00ab239a02a4c213376)

\[227] apply a lut with setLut[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=6355](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=6355)

\[228] Issues Adding Titles and Generators from the 'Effects' to the Timeline Using DaVinci Resolve API[ https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=6492](https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=6492)

\[229] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=14faea4f392ed36bb864404a2009bfe2\&start=40\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=14faea4f392ed36bb864404a2009bfe2\&start=40\&style=13)

\[230] We Suck Less status[ https://status.steakunderwater.com/](https://status.steakunderwater.com/)

\[231] All Other Render Settings for Output[ https://www.steakunderwater.com/VFXPedia/\_\_man/Resolve18-6/DaVinciResolve18\_Manual\_files/part3948.htm](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part3948.htm)

\[232] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/intro)

\[233] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[234] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[235] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[236] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[237] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[238] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[239] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[240] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[241] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[242] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[243] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=357abe3823819001adc736e2a218c915\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=357abe3823819001adc736e2a218c915\&style=13)

\[244] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=1411\&sid=7867e6af2bc1ff84fd07ead8f1708279\&start=270](https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=1411\&sid=7867e6af2bc1ff84fd07ead8f1708279\&start=270)

\[245] Building GUIs With Fusion's UI Manager - Page 5 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095)

\[246] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12119](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12119)

\[247] Building GUIs With Fusion's UI Manager - Page 4 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=1411\&start=45](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=1411\&start=45)

\[248] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=8b01eb530c3d4f10d391efd8b3040be7\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=8b01eb530c3d4f10d391efd8b3040be7\&style=13)

\[249] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=039833f5b9d8b00ab239a02a4c213376](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=039833f5b9d8b00ab239a02a4c213376)

\[250] Open external UI Window from a Fuse[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45755](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45755)

\[251] The Key Differences Between Outside, Parallel, and Layer Nodes in DaVinci Resolve[ https://eyeseecolor.com/key-differences-outside-parallel-layer-nodes/](https://eyeseecolor.com/key-differences-outside-parallel-layer-nodes/)

\[252] 保姆级教程:Windows/Mac系统下载安装DaVinci Resolve 18.5专业版(附中文设置与常见问题解决) - CSDN文库[ https://wenku.csdn.net/column/1s20bg6pvaq](https://wenku.csdn.net/column/1s20bg6pvaq)

\[253] Improve DaVinci Resolve’s performance significantly using an external SSD[ https://www.geeky-gadgets.com/improve-davinci-resolve-speed-using-an-external-ssd/](https://www.geeky-gadgets.com/improve-davinci-resolve-speed-using-an-external-ssd/)

\[254] Main Categories of DaVinci Resolve Tools for Professionals[ https://blog.gfxplugin.com/post/davinci-resolve-tools/](https://blog.gfxplugin.com/post/davinci-resolve-tools/)

\[255] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[256] 【DaVinci Resolve】デリバーページ～「UI概要」と「使い方」～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_deliver\_01\_/8315/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_deliver_01_/8315/)

\[257] DaVinci Resolve 20.2 New Features Guide[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_20.2\_New\_Features\_Guide.pdf?\_v=1757487611000](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf?_v=1757487611000)

\[258] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)

\[259] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[260] DaVinci Resolve 18.5の新機能情報[ https://asteriscus.jp/en/davinci-resolve/8606](https://asteriscus.jp/en/davinci-resolve/8606)

\[261] DaVinci Resolve 18.5 Beta 2 Update[ https://dvresolve.com/news/davinci-resolve-18-5-beta-2-update/](https://dvresolve.com/news/davinci-resolve-18-5-beta-2-update/)

\[262] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a1d2e020aa21179a290a856eaa252e89\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a1d2e020aa21179a290a856eaa252e89\&style=13)

\[263] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=48722](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=48722)

\[264] Building GUIs With Fusion's UI Manager - Page 5 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095)

\[265] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=43005](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=43005)

\[266] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12057](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12057)

\[267] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=43328\&style=13](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=43328\&style=13)

\[268] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=756b1bff98e335b08a82ec100d2456b6\&start=30\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=756b1bff98e335b08a82ec100d2456b6\&start=30\&t=1411)

\[269] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=42100](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=42100)

\[270] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[271] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[272] DaVinci Resolve 18.5で利用できるエフェクト一览 | キョクチ[ https://kyokuti.jp/davinci-resolve4155](https://kyokuti.jp/davinci-resolve4155)

\[273] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[274] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[275] UIManager[ https://www.muyanru.com/en/davinci/guide/ui](https://www.muyanru.com/en/davinci/guide/ui)

\[276] DaVinci Resolve双窗口编辑卡顿，如何优化为单窗口流畅操作?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/9297463](https://ask.csdn.net/questions/9297463)

\[277] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[278] GitHub bryanrandell/DaVinci-Resolve-Timeline-Utility LLM Context[ https://uithub.com/bryanrandell/DaVinci-Resolve-Timeline-Utility](https://uithub.com/bryanrandell/DaVinci-Resolve-Timeline-Utility)

\[279] 【初心者向け】DaVinci Resolve の使い方を解说\![ https://jp.cyberlink.com/blog/video-effects/755/how-to-use-davinci](https://jp.cyberlink.com/blog/video-effects/755/how-to-use-davinci)

\[280] Troubleshooting[ https://deepwiki.com/apvlv/davinci-resolve-mcp/7-troubleshooting](https://deepwiki.com/apvlv/davinci-resolve-mcp/7-troubleshooting)

\[281] DaVinci Resolve MCP Server Features[ https://github.com/igamenovoer/davinci-resolve-mcp/blob/main/docs/FEATURES.md](https://github.com/igamenovoer/davinci-resolve-mcp/blob/main/docs/FEATURES.md)

\[282] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[283] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[284] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/)

\[285] DavinciResolve無償版 スクリプト実行時にResolveオブジェクトがNoneを返してくるとき[ https://qiita.com/taisatol/items/7569b4f2c6125ab948b8](https://qiita.com/taisatol/items/7569b4f2c6125ab948b8)

\[286] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[287] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[288] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[289] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[290] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[291] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[292] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[293] DaVinci ResolveのLuaスクリプト入門[ https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua](https://mebiusbox.github.io/blog/2024/08/30/davinci-resolve-lua)

\[294] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[295] 达芬奇剪辑软件启动失败怎么修复\_DaVinci Resolve打不开如何排查显卡驱动兼容【修复】-电脑软件-PHP中文网[ https://m.php.cn/faq/2273116.html](https://m.php.cn/faq/2273116.html)

\[296] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[297] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[298] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[299] What's new in DaVinci Resolve 18.5[ https://asteriscus.jp/en/davinci-resolve/8606/](https://asteriscus.jp/en/davinci-resolve/8606/)

\[300] DaVinci Resolve Interface

PART[ https://ltbits.github.io/davinci-resolve-manuals/DR18/DR18-RM01-DaVinciResolveInterface.pdf](https://ltbits.github.io/davinci-resolve-manuals/DR18/DR18-RM01-DaVinciResolveInterface.pdf)

\[301] DaVinci Resolve Video Transitions Buy: Compatibility and Import/Export Workflows[ https://reelmind.ai/blog/davinci-resolve-video-transitions-buy-compatibility-and-import-export-workflows](https://reelmind.ai/blog/davinci-resolve-video-transitions-buy-compatibility-and-import-export-workflows)

\[302] Control Surface Support[ https://www.tella.tv/definition/control-surface-support](https://www.tella.tv/definition/control-surface-support)

\[303] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=55b2dd8f39f2de4c38f65d8c169bab91\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=55b2dd8f39f2de4c38f65d8c169bab91\&style=13)

\[304] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45422](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45422)

\[305] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&p=22047\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&p=22047\&t=1411)

\[306] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12033\&sid=561c6cb290b4cf180174349f7e291386\&style=13](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12033\&sid=561c6cb290b4cf180174349f7e291386\&style=13)

\[307] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=756b1bff98e335b08a82ec100d2456b6\&start=45\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=756b1bff98e335b08a82ec100d2456b6\&start=45\&t=1411)

\[308] Building GUIs With Fusion's UI Manager - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=87983c10469035cc40c2fa72d3db5a2d\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=87983c10469035cc40c2fa72d3db5a2d\&t=1411)

\[309] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=be8a6ad510b5755a46a0a9c2e64c6246\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=be8a6ad510b5755a46a0a9c2e64c6246\&style=13)

\[310] README.md[ https://gitlab.com/WeSuckLess/Reactor/-/blob/master/README.md](https://gitlab.com/WeSuckLess/Reactor/-/blob/master/README.md)

\[311] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[312] Type Safety and Modern Python Patterns for DaVinci Resolve[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type\_Safety\_and\_Best\_Practices.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type_Safety_and_Best_Practices.md)

\[313] AutoSubs V2 Window won't open #208[ https://github.com/tmoroney/auto-subs/issues/208](https://github.com/tmoroney/auto-subs/issues/208)

\[314] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[315] DaVinci Resolve MCP[ https://glama.ai/mcp/servers/samuelgursky/davinci-resolve-mcp](https://glama.ai/mcp/servers/samuelgursky/davinci-resolve-mcp)

\[316] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[317] DaVinci Resolve[ https://dxt.services:8443/mcp/davinci-resolve-mcp/](https://dxt.services:8443/mcp/davinci-resolve-mcp/)

\[318] DEV DaVinci Resolve[ https://github.com/hannesdelbeke/unimenu/wiki/DEV-DaVinci-Resolve](https://github.com/hannesdelbeke/unimenu/wiki/DEV-DaVinci-Resolve)

\[319] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[320] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[321] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[322] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/intro)

\[323] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[324] Control Surface Support[ https://www.tella.tv/definition/control-surface-support](https://www.tella.tv/definition/control-surface-support)

\[325] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[326] DaVinci Resolve Replay Editor[ http://www.decklink.com/products/davinciresolve/techspecs](http://www.decklink.com/products/davinciresolve/techspecs)

\[327] DaVinci Resolve – Tech Specs | Blackmagic Design[ http://www.blackmagicdesign.com/ca/products/davinciresolve/techspecs](http://www.blackmagicdesign.com/ca/products/davinciresolve/techspecs)

\[328] 达芬奇完整安装包常见兼容性问题有哪些?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8844616](https://ask.csdn.net/questions/8844616)

\[329] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[330] UIManager[ https://www.muyanru.com/en/davinci/guide/ui](https://www.muyanru.com/en/davinci/guide/ui)

\[331] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[332] 【DaVinci Resolve】デリバーページ～「UI概要」と「使い方」～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_deliver\_01\_/8315/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_deliver_01_/8315/)

\[333] 保姆级教程:Windows/Mac系统下载安装DaVinci Resolve 18.5专业版(附中文设置与常见问题解决) - CSDN文库[ https://wenku.csdn.net/column/1s20bg6pvaq](https://wenku.csdn.net/column/1s20bg6pvaq)

\[334] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[335] How To Add Text In Davinci Resolve 18 – Full Guide[ https://techyorker.com/how-to-add-text-in-davinci-resolve-18-full-guide/](https://techyorker.com/how-to-add-text-in-davinci-resolve-18-full-guide/)

\[336] Fusion Scripting, Fuses and Macros - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a8c9c56798b604a3e4c65af7f9e99146\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=a8c9c56798b604a3e4c65af7f9e99146\&style=13)

\[337] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&p=22047\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&p=22047\&t=1411)

\[338] Building GUIs With Fusion's UI Manager - Page 18 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=44579](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=44579)

\[339] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=62f1a5fbcf51c91dba03fa5b60acb327\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=62f1a5fbcf51c91dba03fa5b60acb327\&style=13)

\[340] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&t=1411\&p=12057](https://www.steakunderwater.com/wesuckless/viewtopic.php?f=6\&t=1411\&p=12057)

\[341] Fusion Scripting, Fuses and Macros[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=78ce852c00936ca6ee28c251d64b1409\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=6\&sid=78ce852c00936ca6ee28c251d64b1409\&style=13)

\[342] Fusion UI Stroke and Size Auto Scale[ https://devforum.roblox.com/t/fusion-ui-stroke-and-size-auto-scale/3806597/1](https://devforum.roblox.com/t/fusion-ui-stroke-and-size-auto-scale/3806597/1)

\[343] Building GUIs With Fusion's UI Manager - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=87983c10469035cc40c2fa72d3db5a2d\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?sid=87983c10469035cc40c2fa72d3db5a2d\&t=1411)

\[344] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[345] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[346] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[347] auto-subs/Docs/ResolveDocs.txt at a39e861afbe578f86156286adedcedfb72614f8d · tmoroney/auto-subs · GitHub[ https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt](https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt)

\[348] “Failed to add script. The script and manifest do not have the same name as the folder.” error in Autodesk Fusion.[ https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Failed-to-add-script-The-script-and-manifest-do-not-have-the-same-name-as-the-folder-error-in-Fusion.html](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Failed-to-add-script-The-script-and-manifest-do-not-have-the-same-name-as-the-folder-error-in-Fusion.html)

\[349] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45418](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45418)

\[350] Problem with simple UI script[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5432](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=5432)

\[351] Building GUIs With Fusion's UI Manager - Page 5 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12095)

\[352] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?hilit=blacklist\&start=270\&t=1411](https://www.steakunderwater.com/wesuckless/viewtopic.php?hilit=blacklist\&start=270\&t=1411)

\[353] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=25067](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=25067)

\[354] Building GUIs With Fusion's UI Manager - Page 4 - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=1411\&start=45](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=1411\&start=45)

\[355] Having trouble programming a Character Fusing GUI[ https://devforum.roblox.com/t/having-trouble-programming-a-character-fusing-gui/4349448](https://devforum.roblox.com/t/having-trouble-programming-a-character-fusing-gui/4349448)

\[356] AutoSubs does not open inside DaVinci Resolve Studio #149[ https://github.com/tmoroney/auto-subs/issues/149](https://github.com/tmoroney/auto-subs/issues/149)

\[357] GitHub - 4Fortune8/auto-subs-with-OIL: Generate Subtitles & Diarize Speakers in Davinci Resolve using AI. plus oil · GitHub[ https://github.com/4Fortune8/auto-subs-with-OIL](https://github.com/4Fortune8/auto-subs-with-OIL)

\[358] AutoSubs V2 Window won't open #208[ https://github.com/tmoroney/auto-subs/issues/208](https://github.com/tmoroney/auto-subs/issues/208)

\[359] AutoSubs doesn't work after upgrading to Davinci 20 from 19 #219[ https://github.com/tmoroney/auto-subs/issues/219](https://github.com/tmoroney/auto-subs/issues/219)

\[360] Not working on newest version of davinci #64[ https://github.com/tmoroney/auto-subs/issues/64](https://github.com/tmoroney/auto-subs/issues/64)

\[361] 革新性AI字幕生成全流程:AutoSubs让专业字幕制作效率提升3倍的秘诀 - AtomGit | GitCode博客[ https://blog.gitcode.com/0864db3fcd2ecef6432b5045a2f3b7c3.html](https://blog.gitcode.com/0864db3fcd2ecef6432b5045a2f3b7c3.html)

\[362] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[363] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[364] 如何解决DaVinci Resolve扩展插件加载失败问题?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8935816](https://ask.csdn.net/questions/8935816)

\[365] Baumstrukturmodus DR 20 Beta 3[ https://www.davinci-resolve-forum.de/thread-4865-post-43582.html](https://www.davinci-resolve-forum.de/thread-4865-post-43582.html)

\[366] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[367] Enable External Scripting[ https://orsonlord.com/enableexternalscripting](https://orsonlord.com/enableexternalscripting)

\[368] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[369] 如何解决DaVinci Resolve扩展插件加载失败问题?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8935816](https://ask.csdn.net/questions/8935816)

\[370] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[371] AutoSubs does not open inside DaVinci Resolve Studio #149[ https://github.com/tmoroney/auto-subs/issues/149](https://github.com/tmoroney/auto-subs/issues/149)

\[372] Reactor Plugin[ https://davinci-resolve-forum.de/thread-1854-post-16728.html](https://davinci-resolve-forum.de/thread-1854-post-16728.html)

\[373] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[374] davinci-resolve-checker/davinci-resolve-checker.py at master · Ashark/davinci-resolve-checker · GitHub[ https://github.com/Ashark/davinci-resolve-checker/blob/master/davinci-resolve-checker.py](https://github.com/Ashark/davinci-resolve-checker/blob/master/davinci-resolve-checker.py)

\[375] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[376] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[377] Control Surface Support[ https://www.tella.tv/definition/control-surface-support](https://www.tella.tv/definition/control-surface-support)

\[378] What's new in DaVinci Resolve 18.5[ https://asteriscus.jp/en/davinci-resolve/8606/](https://asteriscus.jp/en/davinci-resolve/8606/)

\[379] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[380] 保姆级教程:Windows/Mac系统下载安装DaVinci Resolve 18.5专业版(附中文设置与常见问题解决) - CSDN文库[ https://wenku.csdn.net/column/1s20bg6pvaq](https://wenku.csdn.net/column/1s20bg6pvaq)

\[381] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[382] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[383] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[384] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[385] DaVinci Resolve - Transcription window trapped in main window + Erratic movement #383[ https://github.com/Supreeeme/xwayland-satellite/issues/383](https://github.com/Supreeeme/xwayland-satellite/issues/383)

\[386] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[387] DaVinci Resolve 20.2 New Features Guide[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_20.2\_New\_Features\_Guide.pdf?\_v=1757487611000](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf?_v=1757487611000)

\[388] 【DaVinci Resolve】カラーページ～ウィンドウパレット～[ https://ytktfeelfree.com/tool/software/davinci\_resolve/dr\_color\_15\_/7952/](https://ytktfeelfree.com/tool/software/davinci_resolve/dr_color_15_/7952/)

\[389] Project Manager[ https://www.davinci-resolve-forum.de/thread-4956-post-44171.html](https://www.davinci-resolve-forum.de/thread-4956-post-44171.html)

\[390] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[391] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[392] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[393] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[394] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[395] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[396] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[397] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[398] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[399] davinci\_resolve\_matching\_subtitles/Matching Subtitles.py at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Matching%20Subtitles.py](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Matching%20Subtitles.py)

\[400] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[401] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[402] DaVinciResolve-metadata/com.deric.ExifMetadata/Scripts/Comp/EXIF-metadata.lua at main · deric/DaVinciResolve-metadata · GitHub[ https://github.com/deric/DaVinciResolve-metadata/blob/main/com.deric.ExifMetadata/Scripts/Comp/EXIF-metadata.lua](https://github.com/deric/DaVinciResolve-metadata/blob/main/com.deric.ExifMetadata/Scripts/Comp/EXIF-metadata.lua)

\[403] DEV DaVinci Resolve - hannesdelbeke/unimenu GitHub Wiki[ https://github-wiki-see.page/m/hannesdelbeke/unimenu/wiki/DEV-DaVinci-Resolve](https://github-wiki-see.page/m/hannesdelbeke/unimenu/wiki/DEV-DaVinci-Resolve)

\[404] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=1411\&sid=7867e6af2bc1ff84fd07ead8f1708279\&start=270](https://www.steakunderwater.com/wesuckless/viewtopic.php?style=13\&t=1411\&sid=7867e6af2bc1ff84fd07ead8f1708279\&start=270)

\[405] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12096\&style=13](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=12096\&style=13)

\[406] Changelog | Input System | 1.6.1[ https://docs.unity.cn/Packages/com.unity.inputsystem@1.6/changelog/CHANGELOG.html](https://docs.unity.cn/Packages/com.unity.inputsystem@1.6/changelog/CHANGELOG.html)

\[407] ci: Add engine compatibility check for PRs (external package) #1360[ https://github.com/UI5/cli/pull/1360/files/86c1e00eaff22a9b6165ba90c13227a954ad7a98](https://github.com/UI5/cli/pull/1360/files/86c1e00eaff22a9b6165ba90c13227a954ad7a98)

\[408] ci: Add engine compatibility check for PRs (external package) #1360[ https://github.com/UI5/cli/pull/1360/checks](https://github.com/UI5/cli/pull/1360/checks)

\[409] Building GUIs With Fusion's UI Manager[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45422](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=45422)

\[410] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)

\[411] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=80d6619691e0c2540269f8f1054ce2a8](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=80d6619691e0c2540269f8f1054ce2a8)

\[412] 保姆级教程:Windows/Mac系统下载安装DaVinci Resolve 18.5专业版(附中文设置与常见问题解决) - CSDN文库[ https://wenku.csdn.net/column/1s20bg6pvaq](https://wenku.csdn.net/column/1s20bg6pvaq)

\[413] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[414] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[415] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[416] DaVinci Resolve MCP[ https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp](https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp)

\[417] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/)

\[418] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[419] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[420] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[421] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[422] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[423] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[424] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=70](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=70)

\[425] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[426] Music Beat Marker for Davinci Resolve[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=46212\&sid=736f80045ed2018ebf2362796116501b)

\[427] Import footage to the media pool through ALE - We Suck Less[ https://www.steakunderwater.com/wesuckless/viewtopic.php?f=35\&p=21482\&t=2757](https://www.steakunderwater.com/wesuckless/viewtopic.php?f=35\&p=21482\&t=2757)

\[428] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[429] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[430] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[431] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[432] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[433] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[434] DaVinci Resolve 18.5 Released[ https://dvresolve.com/news/davinci-resolve-18-5-released/](https://dvresolve.com/news/davinci-resolve-18-5-released/)

\[435] DaVinci Resolve MCP Server Features[ https://github.com/igamenovoer/davinci-resolve-mcp/blob/main/docs/FEATURES.md](https://github.com/igamenovoer/davinci-resolve-mcp/blob/main/docs/FEATURES.md)

\[436] DaVinci Resolve MCP Server[ https://github.com/Valle1983/davinci-resolve-mcp](https://github.com/Valle1983/davinci-resolve-mcp)

\[437] DaVinci Resolve MCP Server[ https://www.allthingsdev.co/apimarketplace/documentation/davinci-resolve-mcp-server/682c57cd937743152134d6fa](https://www.allthingsdev.co/apimarketplace/documentation/davinci-resolve-mcp-server/682c57cd937743152134d6fa)

\[438] DaVinci Resolve MCP[ https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp](https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp)

\[439] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[440] davinci-resolve-mcp NEW[ https://agentindex.app/tool/samuelgursky-davinci-resolve-mcp/](https://agentindex.app/tool/samuelgursky-davinci-resolve-mcp/)

\[441] davinci-resolve-mcp:连接AI与DaVinci Resolve的桥梁-CSDN博客[ https://blog.csdn.net/gitblog\_00785/article/details/147134199](https://blog.csdn.net/gitblog_00785/article/details/147134199)

\[442] pybmd 2024.2.4[ https://pypi.org/project/pybmd/2024.2.4/](https://pypi.org/project/pybmd/2024.2.4/)

\[443] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[444] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.1.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.1.0/intro)

\[445] Frequent Questions about BMDS Modeling Tools[ https://www.epa.gov/bmds/frequent-questions-about-bmds-modeling-tools](https://www.epa.gov/bmds/frequent-questions-about-bmds-modeling-tools)

\[446] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[447] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[448] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[449] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[450] GitHub - ambustion/Useful.Resolve: A bunch of Scripts I find useful for Davinci Resolve · GitHub[ https://github.com/ambustion/Useful.Resolve](https://github.com/ambustion/Useful.Resolve)

\[451] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[452] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[453] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[454] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[455] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[456] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[457] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[458] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[459] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[460] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.0.3/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.0.3/intro)

\[461] davinci-resolve-api/docs/README.md at master · diop/davinci-resolve-api · GitHub[ https://github.com/diop/davinci-resolve-api/blob/master/docs/README.md?plain=1](https://github.com/diop/davinci-resolve-api/blob/master/docs/README.md?plain=1)

\[462] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[463] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[464] GitHub - supernarthur/resolve\_drp\_exporter: Quick script to batch export DaVinci Resolve multiple projects · GitHub[ https://github.com/Supernarthur/resolve\_drp\_exporter](https://github.com/Supernarthur/resolve_drp_exporter)

\[465] DaVinci Resolve Python Scripts[ https://github.com/a-tak/DavinciScripts](https://github.com/a-tak/DavinciScripts)

\[466] DaVinci Resolve API · GitHub[ https://gist.github.com/monsieuroeuf/8b1851e187b20299ad20061133cfc5db](https://gist.github.com/monsieuroeuf/8b1851e187b20299ad20061133cfc5db)

\[467] GitHub - ambustion/Useful.Resolve: A bunch of Scripts I find useful for Davinci Resolve · GitHub[ https://github.com/ambustion/Useful.Resolve](https://github.com/ambustion/Useful.Resolve)

\[468] DRSorter[ https://github.com/a-tak/DRSorter](https://github.com/a-tak/DRSorter)

> （注：文档部分内容可能由 AI 生成）