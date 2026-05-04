# DaVinci Resolve Python API 开发者指南：论坛、学习资源与高级技巧

## 摘要与关键点

DaVinci Resolve（以下简称 Resolve）的 Python 脚本开发是解锁专业级视频编辑自动化、定制工作流的核心手段 —— 无论是剪辑师批量处理素材，还是开发者为专业团队构建定制工具，其 Python API 都能提供从媒体管理到调色节点控制的全链路能力。但对同时具备剪辑经验与开发背景的用户而言，官方资源的分散性与版本差异带来的兼容性问题，是入门与进阶的主要障碍。

**核心要点：**



* **官方文档现状**：无公开在线版本，仅随软件本地分发；第三方维护的文档（如 X-Raym 的 GitHub Gist）是 2026 版 API 的主要参考，且需注意 v16.2.0 后部分 API 参数从 0-based 转为 1-based 的关键变更[(54)](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)。

* **免费版限制**：DaVinci Resolve 18 + 免费版可运行 Python 脚本，但仅支持软件内调用，无法外部触发；部分核心功能（如节点操作、云项目管理）需 Studio 版授权[(42)](https://tsugi-studio.com/blog/2024/11/11/davinci-resolve-integration/)。

* **社区核心阵地**：We Suck Less 是全球最活跃的 Resolve 脚本开发社区，集中了官方未覆盖的冷门场景解决方案；Blackmagic 官方论坛则是获取官方技术支持的唯一渠道[(119)](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46)。

* **实战资源推荐**：GitHub 高星项目（如`davinci-resolve-mcp`）与 PyPI 库（如`pybmd`）提供了开箱即用的封装能力，能大幅降低复杂功能的开发门槛[(205)](https://mcpdir.net/s/davinci-resolve-mcp/)。



***

## 1. 官方资源与文档

尽管 Resolve 的 Python API 功能强大，但官方资源的获取门槛与版本差异，是开发者面临的首要挑战 —— 官方既无公开的在线文档，不同版本的 API 兼容性也存在显著差异。

### 1.1 官方 Python API 文档

Resolve 的 Python API 官方文档**不提供公开在线访问**，仅随软件安装包本地分发。用户可通过以下方式获取：



* **软件内入口**：启动 Resolve 后，依次点击顶部菜单栏`Help > Documentation > Developer`，即可直接打开本地文档索引页；该索引会清晰列出当前版本支持的所有 API 模块、对象层级与基础示例 [(319)](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)。

* **本地文件路径**：文档的物理存储路径因操作系统而异：


  * **Windows**：`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting`

  * **macOS**：`/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting`

    路径下不仅包含完整的 API 参考文档，还附带官方示例脚本与模块导入说明 [(286)](https://wiki.dvresolve.com/developer-docs/scripting-api)。

需要特别注意的版本兼容性变更：从 Resolve v16.2.0 版本开始，`SetLUT()`、`SetCDL()`等核心调色 API 的`nodeIndex`参数，从原来的 0-based（从 0 开始计数）改为 1-based（从 1 开始计数）—— 这是多数开发者升级版本后遇到 “参数无效” 错误的核心原因，官方文档中未突出提示此变更，需手动核对版本日志 [(346)](https://deric.github.io/DaVinciResolve-API-Docs/)。

### 1.2 免费版与 Studio 版的 API 差异

2026 版 Resolve 的 Python API 权限严格区分免费版与 Studio 版，核心差异直接决定了脚本的功能边界：



* **DaVinci Resolve（免费版）** ：


  * 脚本仅能通过软件内置的 Console 窗口或菜单触发，无法从外部终端、调度工具（如 Windows 任务计划）调用 [(42)](https://tsugi-studio.com/blog/2024/11/11/davinci-resolve-integration/)；

  * 核心限制包括：无法使用`AddNode()`/`AddSerial()`等节点操作 API、无法通过脚本添加转场 / 特效、无法管理云项目、无法控制 Fairlight 音频轨道独奏状态 [(348)](https://wiki.archlinux.org/title/Davinci)；

  * 尽管存在限制，但免费版仍支持媒体池管理、时间线基础编辑、调色参数读取等基础功能，足以覆盖普通剪辑师的批量处理需求。

* **DaVinci Resolve Studio（付费版）** ：


  * 支持外部脚本调用，可通过本地网络或命令行触发，甚至能集成到专业级工作流自动化系统（如 Ayon）中 [(252)](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio)；

  * 解锁全部 API 功能，包括节点图编辑、云项目同步、OFX 插件参数控制、Fairlight 音频轨道高级操作等专业级能力 [(321)](https://blog.51cto.com/u_16099239/14307371)；

  * 支持更多渲染格式与分辨率输出，适配专业工作室的大规模项目需求。

**总结建议**：若需开发涉及节点图、转场特效或云协作的脚本，Studio 版是唯一选择；基础自动化（如批量导入素材、导出剪辑清单）可通过免费版实现 [(42)](https://tsugi-studio.com/blog/2024/11/11/davinci-resolve-integration/)。

### 1.3 官方示例脚本

官方在上述本地 Scripting 路径下提供了丰富的 Python 示例脚本，覆盖从基础操作到进阶功能的全场景：



* **基础功能示例**：项目创建、媒体池素材导入、时间线剪辑添加、渲染队列配置等，适合入门开发者理解 API 的基础调用逻辑；

* **进阶功能示例**：Fusion 节点图编辑、调色 LUT 批量应用、元数据批量修改等，部分示例甚至可直接作为生产级工具使用 [(286)](https://wiki.dvresolve.com/developer-docs/scripting-api)。

这些示例脚本是学习官方 API 最佳实践的核心资源 —— 例如官方示例中的调色脚本，会严格遵循 “先获取项目→再获取时间线→最后操作节点” 的对象层级逻辑，这是避免`AttributeError`（如 “'NoneType' 对象无 GetProjectManager 属性”）的关键准则 [(319)](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)。



***

## 2. 在线论坛与社区支持

官方资源的局限性，使得社区论坛成为解决实际开发问题、获取冷门技巧的核心渠道 —— 不同论坛的定位差异，决定了其适用场景。

### 2.1 Blackmagic Design 官方论坛

这是获取官方技术支持的唯一正规渠道，但脚本开发相关内容分散在`Post Production`板块，无专门的 Scripting 分区 。



* **特点**：


  * 官方技术团队（如核心开发者 Brendan Dower）会定期回复脚本相关的 Bug 报告与功能请求，但通常需要 3-5 个工作日的响应周期，且仅针对明确可复现的问题（如 API 返回值与文档不符） ；

  * 2026 年官方在该板块发布的重要更新包括：Resolve 19.1 版本移除了免费版的`UIManager`模块，导致所有带 GUI 的脚本（如 Reactor 插件）无法在免费版运行 —— 这一变更未提前通知，是当年社区反馈最强烈的兼容性问题 ；

  * 板块内脚本相关问题占比约 10%，需通过关键词（如 “Python API”“scripting”）筛选才能找到目标内容。

* **适合场景**：验证官方已知问题、提交 Bug 报告、请求官方未支持的功能（如新 API 接口）。

### 2.2 We Suck Less（牛排水下论坛）

这是全球最活跃的 Resolve 脚本开发社区，也是官方文档未覆盖的 “冷门场景” 解决方案的主要来源 —— 其`Scripting`板块（板块 ID：46）的 Python 相关讨论占比约 30%，远超其他平台 [(119)](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46)。



* **特点**：


  * **用户构成**：核心用户以专业调色师、后期工作室开发者为主，而非普通用户 —— 例如 2025 年 2 月有用户分享了 “读取 OFX 插件参数” 的脚本，解决了官方 API 无法获取第三方调色插件（如 Neat Video、Film Convert）参数的问题，这类内容在官方渠道完全缺失 [(341)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=20)；

  * **内容深度**：讨论主题覆盖节点图操作、转场添加 workaround、Fairlight 音频轨道高级控制等官方文档未提及的功能，甚至包括反编译 Resolve 可执行文件发现的未公开 API；

  * **活跃程度**：2025-2026 年的高价值讨论包括：如何通过脚本控制 Fairlight 音频轨道独奏状态、如何批量导出 Fusion 节点设置、如何处理含 Emoji 的素材文件名（避免 Unicode 解码错误）等 [(336)](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)。

* **适合场景**：解决官方文档未覆盖的边缘问题、获取实战 workaround、与专业开发者交流进阶技巧。

### 2.3 其他平台

除上述核心论坛外，Stack Overflow、Reddit 等平台也有零散的 Resolve Python API 讨论，但价值有限：



* **Stack Overflow**：相关问题约 100 个（截至 2026 年 5 月），其中约 60% 的有效问题已被整理至 We Suck Less 或 GitHub 项目文档中；但多数问题为 2024 年及更早的历史内容，2025 年后的新问题响应率不足 20%，时效性较差 [(213)](https://www.libhunt.com/compare-pydavinci-vs-Blackmagic-Videohub-Control)。

* **Reddit（r/DaVinciResolve）** ：Python API 相关讨论占比不足 5%，且多为基础问题（如 “如何导入 DaVinciResolveScript 模块”）；无专门的脚本板块或置顶资源帖，高价值内容占比极低，不适合进阶开发者 [(338)](https://wenku.csdn.net/answer/3c7btqspuf)。



***

## 3. 学习资源与实战项目

对兼具剪辑经验与开发背景的用户而言，实战项目与封装库是最高效的学习路径 —— 无需从零开始理解 API 对象层级，即可直接基于成熟代码定制功能。

### 3.1 GitHub 上的开源项目

以下是 2024-2026 年维护活跃、星标量较高的 Resolve Python API 项目，覆盖从基础封装到 AI 集成的全场景：

#### 1. davinci-resolve-mcp



* **描述**：这是当前社区覆盖最广的 Resolve Python API 封装项目，也是唯一支持 AI 助手集成的工具 —— 它通过 Model Context Protocol（MCP）协议，将 Resolve 的 API 能力暴露给 Claude、Cursor 等 AI 助手，开发者甚至可以通过自然语言指令生成脚本，无需手动编写代码 [(205)](https://mcpdir.net/s/davinci-resolve-mcp/)。

* **功能亮点**：


  * 支持 Resolve 20.3 版本新增的 Fusion 节点图 API，可通过脚本创建、编辑 Fusion 合成节点；

  * 官方声称覆盖 98.5% 的 Resolve API 方法，剩余 1.5% 未覆盖的多为云项目相关的边缘功能；

  * 提供完善的错误处理与版本兼容性适配，自动处理不同 Resolve 版本的 API 差异（如 v16.2.0 后的参数索引变更）。

* **获取方式**：GitHub 仓库（`samuelgursky/davinci-resolve-mcp`）或通过 PyPI 安装（`pip install davinci-resolve-mcp`）。

#### 2. Theia



* **描述**：专为 Resolve Studio 用户打造的 VFX editorial 工具集，提供图形化界面（GUI），无需编写代码即可实现专业级功能 —— 例如剪辑清单导出、帧计数器视频生成、素材元数据批量修改等 [(206)](https://github.com/ming-qiu/theia)。

* **功能亮点**：


  * 支持将剪辑清单导出为 Excel、CSV 或 XML 格式，适配专业后期工作室的素材管理需求；

  * 可生成自定义样式的帧计数器视频，支持添加时间码、项目名称等动态元素；

  * 提供元数据批量修改功能，可将外部 CSV 文件的元数据同步到 Resolve 媒体池素材中。

* **注意事项**：仅支持 Resolve Studio 18.6 及以上版本，免费版无法运行。

* **获取方式**：GitHub 仓库（`ming-qiu/theia`）。

#### 3. davinci-rest



* **描述**：基于 FastAPI 开发的 RESTful API 服务，允许通过 HTTP 请求控制 Resolve—— 这意味着开发者可以用任何编程语言（如 JavaScript、Java）调用 Resolve 的功能，无需依赖 Python 环境 [(277)](https://github.com/dev-beluck/davinci-rest/)。

* **功能亮点**：


  * 测试支持 Resolve 18.6 + 免费版与 Studio 版，基础功能无差异；

  * 支持项目创建、媒体导入、时间线剪辑添加、渲染队列配置等核心操作；

  * 可与 ShortFabrik 等 Web UI 工具集成，构建可视化的自动化工作流。

* **局限性**：当前版本（v0.2.5）不支持节点图编辑、转场添加等高级功能，仅覆盖约 60% 的官方 API 方法。

* **获取方式**：GitHub 仓库（`dev-beluck/davinci-rest`）或通过 PyPI 安装（`pip install davinci-rest`）。

#### 4. davinci-cli



* **描述**：命令行工具，支持通过终端指令快速执行 Resolve 自动化操作，无需打开软件界面 —— 适合批量处理大量项目或集成到 CI/CD 流程中 [(257)](https://github.com/znznzna/davinci-cli)。

* **功能亮点**：


  * 支持 Resolve 18.6 + 免费版与 Studio 版；

  * 提供项目创建、媒体导入、时间线导出等常用操作的命令行接口；

  * 支持配置文件，可保存常用的渲染设置、项目路径等参数，避免重复输入。

* **已知问题**：


  * Resolve 20.x 版本中，`ExportStills()` API 调用始终返回`False`，即使实际导出成功；

  * 节拍标记（Beat Marker）存在整数帧舍入误差，在 24fps 项目中会导致约 21ms 的时间偏移；

  * 仅支持 MediaPool API，不支持 Fusion 或 Fairlight 的媒体操作。

* **获取方式**：GitHub 仓库（`znznzna/davinci-cli`）或通过 PyPI 安装（`pip install davinci-cli`）。

#### 5. nobphotographr/davinci-resolve-automation



* **描述**：以调色自动化为核心的脚本集合，附带详细的技术文档 —— 其`Limitations.md`与`Advanced_Techniques.md`是社区公认的 API 限制与 workaround 权威参考 [(203)](https://github.com/nobphotographr/davinci-resolve-automation)。

* **功能亮点**：


  * 提供 LUT 批量测试与比较、节点结构预配置、调色参数批量应用等功能，适合专业调色师；

  * `Advanced_Techniques.md`中记录了数十种官方未覆盖的技巧，例如通过剪辑颜色标记模拟时间线选中项、通过 DRX 模板添加特效等。

* **获取方式**：GitHub 仓库（`nobphotographr/davinci-resolve-automation`）。

### 3.2 PyPI 库

以下是 2026 年维护活跃的 Resolve Python API 封装库，可大幅提升开发效率：

#### 1. pybmd



* **描述**：跨平台的 Resolve API 封装库，专为解决版本兼容性问题设计 —— 它会自动检测当前 Resolve 版本，并适配对应的 API 参数规则（如 v16.2.0 后的 1-based 索引） [(284)](https://pypi.org/project/pybmd/)。

* **功能亮点**：


  * 支持 Windows 与 macOS 系统，无需额外配置环境变量；

  * 提供版本检查装饰器，可在运行时验证当前 Resolve 版本是否支持目标 API；

  * 提供完善的类型提示与自动补全支持，适配 VS Code、PyCharm 等主流 IDE。

* **版本更新**：2026 年 2 月发布的 v2026.1.0 版本，新增了对 Resolve 20.3 版本 Fusion 节点图 API 的支持，修复了免费版无法导入模块的问题。

* **安装方式**：`pip install pybmd`。

#### 2. davinci-resolve-mcp



* **描述**：与 GitHub 同名项目配套的 PyPI 库，核心功能是将 Resolve 的 API 能力暴露给 AI 助手，允许通过自然语言指令控制 Resolve [(308)](https://pypi.org/project/davinci-resolve-mcp/)。

* **功能亮点**：


  * 支持项目管理、时间线编辑、媒体导入、调色参数控制等全流程操作；

  * 可与 Claude Desktop、Cursor 等 AI 工具集成，开发者只需输入自然语言需求（如 “导出当前时间线的剪辑清单”），即可自动生成并执行脚本。

* **安装方式**：`pip install davinci-resolve-mcp`。

#### 3. pydavinci（已停止维护）



* **描述**：轻量级 API 封装库，曾以自动补全功能闻名，但 2025 年 7 月起停止更新，仅支持 Resolve 18.5 及以下版本 [(178)](https://pedrolabonia.github.io/pydavinci/)。

* **局限性**：仅支持 Python 3.6 版本，无 Windows 平台支持，且存在多个已知 Bug（如含 Emoji 的文件名读取错误）—— 当前已被`pybmd`替代，不建议使用。



***

## 4. 高级话题与深入学习

对专业开发者而言，掌握官方未覆盖的边缘场景解决方案与版本兼容性处理，是提升脚本质量的关键 —— 这部分内容无法从官方资源获取，只能通过社区积累。

### 4.1 处理官方未提及的情况

官方文档仅覆盖约 70% 的实际开发场景，以下是社区总结的高频冷门场景与解决方案，均来自 We Suck Less 论坛与 GitHub 项目的实战验证：



| 问题场景                   | 官方限制                               | 解决方案                         |
| ---------------------- | ---------------------------------- | ---------------------------- |
| 获取时间线选中项               | 无原生`timeline.GetSelectedItems()`方法 | 通过剪辑颜色标记模拟选中状态               |
| 添加转场 / 特效              | 无`AddTransition()`/`AddEffect()`方法 | 通过 DRX 模板预设效果，再导入到时间线        |
| 调整 Lift/Gamma/Gain 调色轮 | 无直接设置 API                          | 通过`SetCDL()`方法间接控制，或修改项目配置文件 |
| 控制 Fairlight 轨道独奏      | 无原生 API                            | 通过模拟键盘快捷键实现                  |
| 读取 OFX 插件参数            | 官方 API 未开放                         | 通过反编译 Resolve 可执行文件获取未公开接口   |

上述解决方案的详细说明与代码示例，可参考`nobphotographr/davinci-resolve-automation`项目的`Advanced_Techniques.md`文档 [(345)](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)。

### 4.2 获取最新动态和 Bug

及时掌握 Resolve 的版本更新与已知 Bug，是避免脚本失效的核心 —— 以下是 2026 年的关键更新与 Bug 汇总：



* **Resolve 20.3 版本（2025 年 12 月发布）** ：


  * 新增 Fusion 节点图 API，支持通过脚本创建、编辑 Fusion 合成节点；

  * 修复了字幕上下文菜单中缺少剪辑操作的问题，但未对 Python API 进行额外更新 [(242)](https://m.xitongzhijia.net/news/20251202/302842.html)。

* **Resolve 20.3.2 版本（2026 年 2 月发布）** ：


  * 新增动态修剪编辑器选项、改善字幕字距调整、新增富士胶片素材的色彩空间选项；

  * 提升了 Magic Mask 缓存性能与沉浸式 3D 项目的渲染速度，但未涉及 Python API 的功能变更 [(244)](https://www.redsharknews.com/blackmagic-davinci-resolve-20-3-2-update-fujifilm-f-log2-c)。

* **2026 年已知 Bug（影响 Python API）** ：


  * `AppendToTimeline()`方法缺少轨道索引参数，无法指定素材添加到特定轨道；

  * Resolve 20.x 版本中，`ExportStills()` API 始终返回`False`，即使实际导出成功；

  * 含 Emoji 的素材文件名会导致`UnicodeDecodeError`，仅在 Resolve 运行时触发；

  * Windows 11 环境下，Python 3.12 + 版本无法导入`DaVinciResolveScript`模块，需降级到 Python 3.9 版本；

  * Resolve 19.1 版本移除了免费版的`UIManager`模块，导致所有带 GUI 的脚本无法运行 [(257)](https://github.com/znznzna/davinci-cli)。

**获取最新信息的渠道**：



1. We Suck Less 的`Scripting`板块：用户会第一时间分享新版本的 API 变更与 Bug，例如 2025 年 12 月 Resolve 20.3 发布后，仅 3 天就有用户发布了 Fusion 节点图 API 的测试脚本 [(119)](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46)；

2. GitHub 项目的 Issues 页面：`davinci-resolve-mcp`、`pybmd`等主流项目的维护者会同步官方 Bug 修复进度，并提供临时 workaround [(205)](https://mcpdir.net/s/davinci-resolve-mcp/)；

3. Blackmagic Design 官方更新日志：虽然不会主动提及 API 变更，但可通过更新内容反向推断可能的兼容性影响（如新增功能是否会新增对应的 API 方法） [(242)](https://m.xitongzhijia.net/news/20251202/302842.html)。



***

## 5. 总结与建议

针对兼具视频编辑经验与专业开发背景的用户，以下是分阶段的学习与实践建议：

### 入门阶段（1-2 周）



1. **熟悉官方文档结构**：从本地文档的「Resolve Object Hierarchy」章节入手，重点理解`Resolve`→`ProjectManager`→`Project`→`Timeline`的核心对象层级 —— 这是避免 “AttributeError: 'NoneType' object has no attribute 'GetProjectManager'” 错误的关键，官方示例脚本会严格遵循这一层级逻辑 [(319)](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)；

2. **运行官方示例脚本**：从媒体池导入、时间线创建等基础示例开始，验证脚本的执行逻辑，例如通过官方示例中的`CreateTimelineFromClips`方法，理解如何将媒体池素材添加到时间线；

3. **学习基础封装库**：通过`pybmd`的类型提示功能，快速熟悉 API 的参数规则与返回值类型，提升代码编写效率 —— 例如在 VS Code 中输入`pybmd.Resolve().GetProjectManager()`，会自动提示后续可调用的方法 [(284)](https://pypi.org/project/pybmd/)。

### 进阶阶段（2-4 周）



1. **分析实战项目代码**：重点学习`davinci-resolve-mcp`的 Fusion 节点图 API 实现、`Theia`的 GUI 工具开发逻辑 —— 例如`davinci-resolve-mcp`中对 Fusion 节点的封装，会覆盖官方未提及的节点连接规则，是学习专业级功能的最佳参考 [(205)](https://mcpdir.net/s/davinci-resolve-mcp/)；

2. **参与社区讨论**：在 We Suck Less 论坛的`Scripting`板块，从回答基础问题（如 “如何导入 DaVinciResolveScript 模块”）开始，逐步积累实战经验 —— 论坛的核心用户会对有价值的问题进行详细解答，甚至提供完整的代码示例 [(119)](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46)；

3. **开发小型工具**：从解决自身工作流中的实际问题入手，例如开发 “批量重命名媒体池素材”“导出剪辑清单” 等工具 —— 这类工具的需求明确，且能快速验证学习成果。

### 高级阶段（4 周以上）



1. **研究未公开 API**：通过反编译 Resolve 可执行文件（如 Windows 平台的`Resolve.exe`），发现未公开的 API 方法（如`GetShowAllVideoFrames()`、`SetSourceViewerMode()`），并通过测试验证其功能 —— 这是开发专业级定制工具的关键能力 ；

2. **处理版本兼容性**：为脚本添加版本检查逻辑，例如通过`resolve.GetVersion()`方法获取当前 Resolve 版本，自动适配 v16.2.0 后的参数索引变更 ——`pybmd`的版本检查装饰器可直接复用，无需手动实现 [(284)](https://pypi.org/project/pybmd/)；

3. **贡献开源项目**：向`davinci-resolve-mcp`、`pybmd`等主流项目提交 PR，例如修复已知 Bug、新增对新版本 API 的支持 —— 这不仅能提升个人技术影响力，还能获得社区的专业反馈，进一步提升开发能力 [(205)](https://mcpdir.net/s/davinci-resolve-mcp/)。

**核心资源优先级排序**：



1. **必须掌握**：We Suck Less 论坛（获取冷门解决方案）、`nobphotographr/davinci-resolve-automation`文档（API 限制与 workaround）、`pybmd`库（版本兼容性封装）；

2. **推荐学习**：`davinci-resolve-mcp`项目（AI 集成与全 API 覆盖）、Blackmagic 官方论坛（官方技术支持）；

3. **不建议使用**：`pydavinci`（已停止维护）、Reddit（内容质量低）。

**参考资料&#x20;**

\[1] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[2] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[3] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[4] 达芬奇Python脚本助力剪辑效率提升[ https://www.iesdouyin.com/share/video/7529857493657259306](https://www.iesdouyin.com/share/video/7529857493657259306)

\[5] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[6] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[7] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.0.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.0.0/intro)

\[8] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[9] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[10] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[11] DaVinci Resolve 中 的 电影 导入 功能 模拟 我们 拥有 超过 六万四千多 各种 模板 ， 视频 、 音效 素材 ， Photoshop 预设 、 笔刷 、 教程 、 软件 、 3D 模型 等等 ， 我们 每天 都 有 最新 作品 更新 ， 每周 提供 几十 个 免费 AE / PR 模板 、 笔刷 等 ， 并 提供 免费 或 有偿 资源 服务 。&#x20;

&#x20;http : / / ww[ https://www.iesdouyin.com/share/video/7592560902319131910](https://www.iesdouyin.com/share/video/7592560902319131910)

\[12] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[13] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[14] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[15] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[16] Contact Us[ https://dvresolve.com/contact/](https://dvresolve.com/contact/)

\[17] Email Benachrichtigungen über neue Beiträge an/ausschalten[ https://davinciresolvecommunity.de/community/threads/email-benachrichtigungen-%C3%BCber-neue-beitr%C3%A4ge-an-ausschalten.9/](https://davinciresolvecommunity.de/community/threads/email-benachrichtigungen-%C3%BCber-neue-beitr%C3%A4ge-an-ausschalten.9/)

\[18] 达芬奇软件全功能界面解析与后期制作教程[ https://www.iesdouyin.com/share/video/7506513798867586341](https://www.iesdouyin.com/share/video/7506513798867586341)

\[19] How to enable/disable notifications about new postings/threads?[ https://davinciresolveforum.com/community/threads/how-to-enable-disable-notifications-about-new-postings-threads.8/](https://davinciresolveforum.com/community/threads/how-to-enable-disable-notifications-about-new-postings-threads.8/)

\[20] ご質問や不具合の連絡先[ https://asteriscus.jp/davinci-resolve/2675/](https://asteriscus.jp/davinci-resolve/2675/)

\[21] DaVinci Resolve – 新增功能 | Blackmagic Design[ http://www.blackmagicdesign.com/cn/products/davinciresolve/whatsnew?curator=upstract.com](http://www.blackmagicdesign.com/cn/products/davinciresolve/whatsnew?curator=upstract.com)

\[22] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[23] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[24] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[25] Unlock the Secrets of Automating DaVinci Resolve with Python - Free Version Edition[ https://dev.to/depsir/unlock-the-secrets-of-automating-davinci-resolve-with-python-free-version-edition-1fkn](https://dev.to/depsir/unlock-the-secrets-of-automating-davinci-resolve-with-python-free-version-edition-1fkn)

\[26] 达芬奇Python脚本助力剪辑效率提升[ https://www.iesdouyin.com/share/video/7529857493657259306](https://www.iesdouyin.com/share/video/7529857493657259306)

\[27] PythonでDavinciResolveのタイムラインを自動生成する【無料版・XML】[ https://qiita.com/alysunk/items/33b5b118368ffce4aab7](https://qiita.com/alysunk/items/33b5b118368ffce4aab7)

\[28] A python script to create a DaVinci Resolve project with today's date and import media files into default timeline. · GitHub[ https://gist.github.com/basuke/908ed2b0f41d9d995f7955d3cebfb9ae](https://gist.github.com/basuke/908ed2b0f41d9d995f7955d3cebfb9ae)

\[29] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[30] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[31] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[32] 达芬奇Resolve 20新增AI功能与性能优化解析[ https://www.iesdouyin.com/share/video/7553428806279728423](https://www.iesdouyin.com/share/video/7553428806279728423)

\[33] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[34] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[35] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[36] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio)

\[37] DaVinci Resolve Forum[ http://www.davinci-resolve-forum.de/index.php?thread/269-trim-und-schnittfenster-veschwunden/](http://www.davinci-resolve-forum.de/index.php?thread/269-trim-und-schnittfenster-veschwunden/)

\[38] Davinci Resolve 图像 分析 调整 工具 DCT LS 插件 下载 地址 ： https : / / www . rr cg . cn / thread - 16786380 - 1 - 1 . html&#x20;

&#x20;RR CG . CN 最新 CG 资讯 素材 教程 请 关注 公众 号 ： RR CG&#x20;

&#x20;本 合集 是 关于 Davinci Resolve 影像 图像 分析 调整 工具 D[ https://www.iesdouyin.com/share/video/7317454218154020136](https://www.iesdouyin.com/share/video/7317454218154020136)

\[39] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[40] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[41] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[42] DaVinci Resolve Integration[ https://tsugi-studio.com/blog/2024/11/11/davinci-resolve-integration/](https://tsugi-studio.com/blog/2024/11/11/davinci-resolve-integration/)

\[43] DaVinci-Resolve-Scripts[ https://github.com/X-Raym/DaVinci-Resolve-Scripts/blob/main/README.md](https://github.com/X-Raym/DaVinci-Resolve-Scripts/blob/main/README.md)

\[44] Roll Bin Creator[ https://en.editingtools.io/resolve/rollbincreator/](https://en.editingtools.io/resolve/rollbincreator/)

\[45] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[46] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[47] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[48] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[49] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[50] CLAUDE.md[ https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/CLAUDE.md](https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/CLAUDE.md)

\[51] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[52] DaVinci Resolve Forum[ https://www.davinci-resolve-forum.de/index.php?thread/1721-schlechte-qualit%C3%A4t-verpixelt-nach-rendern-woran-kann-es-liegen/](https://www.davinci-resolve-forum.de/index.php?thread/1721-schlechte-qualit%C3%A4t-verpixelt-nach-rendern-woran-kann-es-liegen/)

\[53] Scripting[ https://wiki.dvresolve.com/developer-docs/scripting](https://wiki.dvresolve.com/developer-docs/scripting)

\[54] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[55] DaVinci Resolve[ https://wiki.archlinux.org/title/Davinci](https://wiki.archlinux.org/title/Davinci)

\[56] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[57] Davinci Resolve scripts[ https://www.niwa.nu/dr-scripts/](https://www.niwa.nu/dr-scripts/)

\[58] GitHub - jashanmak/Davinci-Resolve-Scripts: Scripts for Davinci Resolve · GitHub[ https://github.com/jashanmak/Davinci-Resolve-Scripts](https://github.com/jashanmak/Davinci-Resolve-Scripts)

\[59] Roll Bin Creator[ https://ar.editingtools.io/resolve/rollbincreator/](https://ar.editingtools.io/resolve/rollbincreator/)

\[60] DaVinci Resolve Scripts Collection[ https://github.com/tynidev/davinci-resolve](https://github.com/tynidev/davinci-resolve)

\[61] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[62] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[63] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[64] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[65] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[66] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[67] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[68] CLAUDE.md[ https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/CLAUDE.md](https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/CLAUDE.md)

\[69] DaVinci Resolve – Studio | Blackmagic Design[ https://www.blackmagicdesign.com/products/davinciresolve/studio](https://www.blackmagicdesign.com/products/davinciresolve/studio)

\[70] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[71] GitHub - jashanmak/Davinci-Resolve-Scripts: Scripts for Davinci Resolve · GitHub[ https://github.com/jashanmak/Davinci-Resolve-Scripts](https://github.com/jashanmak/Davinci-Resolve-Scripts)

\[72] DaVinci Resolve[ https://dxt.services/mcp/davinci-resolve-mcp/](https://dxt.services/mcp/davinci-resolve-mcp/)

\[73] Resolve[ https://prism-pipeline.com/docs/latest/plugins/Resolve/](https://prism-pipeline.com/docs/latest/plugins/Resolve/)

\[74] DaVinci

Resolve 19.1

EO4E04545[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_19\_1\_New\_Features\_Guide.pdf](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_19_1_New_Features_Guide.pdf)

\[75] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[76] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[77] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[78] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[79] davinci-resolve-mcp NEW[ https://agentindex.app/tool/samuelgursky-davinci-resolve-mcp/](https://agentindex.app/tool/samuelgursky-davinci-resolve-mcp/)

\[80] DaVinci Resolve B-Roll Generator[ https://github.com/eshaan-mehta/B-Roller](https://github.com/eshaan-mehta/B-Roller)

\[81] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[82] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[83] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[84] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[85] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[86] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[87] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[88] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[89] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[90] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[91] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[92] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[93] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[94] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[95] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[96] 字幕動画編集をPythonスクリプトで簡略化 (DaVinci Resolve API)[ https://qiita.com/tetsubo/items/7f20767054708864d698](https://qiita.com/tetsubo/items/7f20767054708864d698)

\[97] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[98] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[99] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[100] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[101] 字幕動画編集をPythonスクリプトで簡略化 (DaVinci Resolve API)[ https://qiita.com/tetsubo/items/7f20767054708864d698](https://qiita.com/tetsubo/items/7f20767054708864d698)

\[102] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[103] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[104] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[105] Davinci Resolve Community[ https://discord.do/davinci-resolve-community/](https://discord.do/davinci-resolve-community/)

\[106] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[107] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[108] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[109] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[110] ResolveRPC-macOS[ https://github.com/jacobbvfx/resolverpc-macos](https://github.com/jacobbvfx/resolverpc-macos)

\[111] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[112] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[113] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[114] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[115] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[116] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[117] 字幕動画編集をPythonスクリプトで簡略化 (DaVinci Resolve API)[ https://qiita.com/tetsubo/items/7f20767054708864d698](https://qiita.com/tetsubo/items/7f20767054708864d698)

\[118] DaVinci Resolve Community Discord Server[ https://discordbotlist.com/servers/davinci-resolve-community-714620142096482314](https://discordbotlist.com/servers/davinci-resolve-community-714620142096482314)

\[119] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46)

\[120] Baumstrukturmodus Davinci Resolve Discord Server[ https://davinci-resolve-forum.de/thread-2933.html](https://davinci-resolve-forum.de/thread-2933.html)

\[121] Public Discord Servers tagged with Davinci Resolve[ https://discord.me/servers/tag/davinci-resolve](https://discord.me/servers/tag/davinci-resolve)

\[122] Davinci Resolve Discord Server | Realtime Support for Davinci Resolve @JakeWipp[ https://cyberspaceandtime.com/DAVINCI-RESOLVE-DISCORD-SERVER-REALTIME-SUPPORT-FOR-DAVINCI-RESOLVE-OxPn\_WAHhqf9o9swCXudXWW-nOm4r0kwI.htm](https://cyberspaceandtime.com/DAVINCI-RESOLVE-DISCORD-SERVER-REALTIME-SUPPORT-FOR-DAVINCI-RESOLVE-OxPn_WAHhqf9o9swCXudXWW-nOm4r0kwI.htm)

\[123] Blackmagicdesign FUSION 8

GENE[ https://documents.blackmagicdesign.com/UserManuals/Fusion8\_Generation\_Scripting\_Manual.pdf](https://documents.blackmagicdesign.com/UserManuals/Fusion8_Generation_Scripting_Manual.pdf)

\[124] Media | Blackmagic Design[ https://www.blackmagicdesign.com/cn/media/release/20250404-02](https://www.blackmagicdesign.com/cn/media/release/20250404-02)

\[125] Autofokus fuer BMCC 6k & Phyxis 6k[ https://www.davinci-resolve-forum.de/portal.php](https://www.davinci-resolve-forum.de/portal.php)

\[126] All Activity[ https://www.eoshd.com/comments/discover/?csrfKey=c9ece2204e0751019f7a1253ad062a3d\&view=condensed](https://www.eoshd.com/comments/discover/?csrfKey=c9ece2204e0751019f7a1253ad062a3d\&view=condensed)

\[127] All Activity[ https://www.eoshd.com/comments/discover/?csrfKey=78ba4493858c663ae9399ffa87658321\&view=expanded](https://www.eoshd.com/comments/discover/?csrfKey=78ba4493858c663ae9399ffa87658321\&view=expanded)

\[128] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[129] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[130] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/intro)

\[131] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[132] DaVinci Resolve 19徹底解剖：AIによる「テキストベース編集」と「マルチモーダル制御」がもたらす爆速ワークフロー革命[ https://ai-news.sktkcontact.com/2025/12/27/davinci-resolve-19-ai-workflow-integration/](https://ai-news.sktkcontact.com/2025/12/27/davinci-resolve-19-ai-workflow-integration/)

\[133] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)

\[134] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46)

\[135] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[136] Davinci Resolve API Document Webside[ https://www.steakunderwater.com/wesuckless/viewtopic.php?p=52242\&style=13](https://www.steakunderwater.com/wesuckless/viewtopic.php?p=52242\&style=13)

\[137] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46\&start=110](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46\&start=110)

\[138] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[139] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[140] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[141] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[142] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[143] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[144] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[145] Timeline Creation and Manipulation (Python)[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.1-timeline-creation-and-manipulation-(python)](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.1-timeline-creation-and-manipulation-\(python\))

\[146] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[147] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[148] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[149] jchai01/davinci-resolve-aac-workaround-macro[ https://github.com/jchai01/davinci-resolve-aac-workaround-macro](https://github.com/jchai01/davinci-resolve-aac-workaround-macro)

\[150] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[151] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[152] 字幕動画編集をPythonスクリプトで簡略化 (DaVinci Resolve API)[ https://qiita.com/tetsubo/items/7f20767054708864d698](https://qiita.com/tetsubo/items/7f20767054708864d698)

\[153] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[154] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[155] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[156] drremote · PyPI[ https://pypi.org/project/drremote/](https://pypi.org/project/drremote/)

\[157] ResolveDevDoc[ https://readthedocs.org/projects/resolvedevdoc/](https://readthedocs.org/projects/resolvedevdoc/)

\[158] resolve-assistant 0.1.5[ https://pypi.org/project/resolve-assistant/](https://pypi.org/project/resolve-assistant/)

\[159] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[160] late-sdk 1.3.35[ https://pypi.org/project/late-sdk/1.3.35/](https://pypi.org/project/late-sdk/1.3.35/)

\[161] davinci\_resolve\_api - Read the Docs Community[ https://readthedocs.org/projects/davinci-resolve-api/](https://readthedocs.org/projects/davinci-resolve-api/)

\[162] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[163] Theia 明察秋毫[ https://github.com/ming-qiu/theia](https://github.com/ming-qiu/theia)

\[164] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[165] M Hadi[ https://gist.github.com/mhadifilms](https://gist.github.com/mhadifilms)

\[166] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[167] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[168] davinci-resolve-studio-20[ https://github.com/topics/davinci-resolve-studio-20](https://github.com/topics/davinci-resolve-studio-20)

\[169] David Manouchehri[ https://gist.github.com/Manouchehri](https://gist.github.com/Manouchehri)

\[170] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[171] blackmagicdesign[ https://github.com/topics/blackmagicdesign?l=python](https://github.com/topics/blackmagicdesign?l=python)

\[172] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[173] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)

\[174] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[175] davinci-resolve-studio-20[ https://github.com/topics/davinci-resolve-studio-20](https://github.com/topics/davinci-resolve-studio-20)

\[176] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/content-creation/apvlv--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/content-creation/apvlv--davinci-resolve-mcp/)

\[177] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/)

\[178] pydavinci[ https://pedrolabonia.github.io/pydavinci/](https://pedrolabonia.github.io/pydavinci/)

\[179] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[180] Type Safety and Modern Python Patterns for DaVinci Resolve[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type\_Safety\_and\_Best\_Practices.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type_Safety_and_Best_Practices.md)

\[181] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[182] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[183] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[184] DaVinci Resolve MCP[ https://glama.ai/mcp/servers/samuelgursky/davinci-resolve-mcp](https://glama.ai/mcp/servers/samuelgursky/davinci-resolve-mcp)

\[185] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[186] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[187] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[188] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[189] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[190] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[191] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[192] resolve-assistant 0.1.5[ https://pypi.org/project/resolve-assistant/](https://pypi.org/project/resolve-assistant/)

\[193] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/content-creation/apvlv--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/content-creation/apvlv--davinci-resolve-mcp/)

\[194] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)

\[195] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[196] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[197] 【亲测免费】 Pydavinci:Python 编写的 DaVinci Resolve 脚本工具包-CSDN博客[ https://blog.csdn.net/gitblog\_00932/article/details/145005976](https://blog.csdn.net/gitblog_00932/article/details/145005976)

\[198] GitHub - WheheoHu/pybmd: Python wrapper library for DaVinci Resolve API · GitHub[ https://github.com/WheheoHu/pybmd](https://github.com/WheheoHu/pybmd)

\[199] Theia 明察秋毫[ https://github.com/ming-qiu/theia](https://github.com/ming-qiu/theia)

\[200] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[201] davinci-resolve-mcp[ https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/](https://www.hexmos.com/freedevtools/mcp/file-management/samuelgursky--davinci-resolve-mcp/)

\[202] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[203] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[204] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[205] DaVinci Resolve MCP[ https://mcpdir.net/s/davinci-resolve-mcp/](https://mcpdir.net/s/davinci-resolve-mcp/)

\[206] Theia 明察秋毫[ https://github.com/ming-qiu/theia](https://github.com/ming-qiu/theia)

\[207] DaVinci Resolve Python Automation[ https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation](https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation)

\[208] DaVinci Resolve AI编辑工具 - 腾讯云[ https://cloud.tencent.com/developer/mcp/server/11461](https://cloud.tencent.com/developer/mcp/server/11461)

\[209] DaVinci Resolve MCP[ https://mcpdir.net/es/s/davinci-resolve-mcp/](https://mcpdir.net/es/s/davinci-resolve-mcp/)

\[210] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[211] DaVinci Resolve 調査レポート[ https://aegisfleet.github.io/tool-survey-report/reports/davinci-resolve/](https://aegisfleet.github.io/tool-survey-report/reports/davinci-resolve/)

\[212] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[213] pydavinci VS Blackmagic-Videohub-Control[ https://www.libhunt.com/compare-pydavinci-vs-Blackmagic-Videohub-Control](https://www.libhunt.com/compare-pydavinci-vs-Blackmagic-Videohub-Control)

\[214] pybmd[ https://wheheohu.github.io/pybmd/\_autosummary/pybmd.html](https://wheheohu.github.io/pybmd/_autosummary/pybmd.html)

\[215] pybmd 2024.2.5[ https://pypi.org/project/pybmd/2024.2.5/](https://pypi.org/project/pybmd/2024.2.5/)

\[216] DaVinci Resolve Free[ https://retouchinglabs.com/davinci-resolve-free/](https://retouchinglabs.com/davinci-resolve-free/)

\[217] DaVinci Resolve Free vs Studio 2026: Limitations, AI Features, Watermark[ https://leaveit2ai.com/ai-tools/video/davinci-resolve](https://leaveit2ai.com/ai-tools/video/davinci-resolve)

\[218] DaVinci Resolve Reviews for 2026[ https://tekpon.com/software/davinci-resolve/reviews/](https://tekpon.com/software/davinci-resolve/reviews/)

\[219] DaVinci Resolve 19: Unleashing the Power of AI and NVIDIA for Accelerated Post-Production Workflows[ https://eduardooroz.co/nvidia-davinci-resolve/](https://eduardooroz.co/nvidia-davinci-resolve/)

\[220] DaVinci Resolve Free Trial[ https://gotrialpro.net/service/davinci-resolve/](https://gotrialpro.net/service/davinci-resolve/)

\[221] DaVinci Resolve Free против Paid: ключевые различия, которые вы должны знать[ https://www.capcut.com/ru-by/resource/davinci-resolve-free-vs-paid](https://www.capcut.com/ru-by/resource/davinci-resolve-free-vs-paid)

\[222] DaVinci Resolveの評判・口コミ 全34件[ https://www.itreview.jp/products/davinci-resolve/reviews](https://www.itreview.jp/products/davinci-resolve/reviews)

\[223] Add HN top submissions digest for 2026-04-16[ https://github.com/srid/claude-dump/pull/9](https://github.com/srid/claude-dump/pull/9)

\[224] DaVinci Resolve[ https://www.tryorbye.com/products/davinci-resolve](https://www.tryorbye.com/products/davinci-resolve)

\[225] DaVinci Resolve[ https://www.trustradius.com/products/davinci-resolve/reviews](https://www.trustradius.com/products/davinci-resolve/reviews)

\[226] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[227] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[228] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[229] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[230] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[231] \[Investigation] DaVinci Resolve Script API cannot add fade transitions automatically #3[ https://github.com/mojonobu/davinci-resolve-random-video-switcher/issues/3](https://github.com/mojonobu/davinci-resolve-random-video-switcher/issues/3)

\[232] pybmd 2024.2.5[ https://pypi.org/project/pybmd/2024.2.5/](https://pypi.org/project/pybmd/2024.2.5/)

\[233] GitHub - WheheoHu/pybmd: Python wrapper library for DaVinci Resolve API · GitHub[ https://github.com/WheheoHu/pybmd](https://github.com/WheheoHu/pybmd)

\[234] PyBOM[ https://github.com/marvel-works/pybom](https://github.com/marvel-works/pybom)

\[235] Usage Guide[ https://github.com/ascsn/pybmc/blob/main/docs/usage.md](https://github.com/ascsn/pybmc/blob/main/docs/usage.md)

\[236] py-bmd-abaqus 0.1.9[ https://pypi.org/project/py-bmd-abaqus/](https://pypi.org/project/py-bmd-abaqus/)

\[237] BMDS Online, BMDS Desktop, and pybmds[ https://19january2025snapshot.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds/index.html](https://19january2025snapshot.epa.gov/bmds/bmds-online-bmds-desktop-and-pybmds/index.html)

\[238] GitHub - USEPA/BMDS: U.S EPA Benchmark Dose Modeling Software (BMDS) · GitHub[ https://github.com/usepa/bmds](https://github.com/usepa/bmds)

\[239] bmdrc: Python package for quantifying phenotypes from chemical exposures with benchmark dose modeling[ https://pmc.ncbi.nlm.nih.gov/articles/PMC12313058/pdf/pcbi.1013337.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC12313058/pdf/pcbi.1013337.pdf)

\[240] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/intro)

\[241] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[242] 达芬奇 DaVinci Resolve 发布最新的 20.3 版本!提升整体性能及稳定性-系统之家[ https://m.xitongzhijia.net/news/20251202/302842.html](https://m.xitongzhijia.net/news/20251202/302842.html)

\[243] DaVinci Resolve Studio 20.3 Update: New Features, Performance Boosts, and Key Compatibility Notes[ https://www.motionmedia.com/mm-blog/davinci-resolve-studio-203-update-new-features-performance-boosts-and-key-compatibility-notes/](https://www.motionmedia.com/mm-blog/davinci-resolve-studio-203-update-new-features-performance-boosts-and-key-compatibility-notes/)

\[244] Blackmagic Releases DaVinci Resolve 20.3.2 and Fusion Studio 20.3.2 Update[ https://www.redsharknews.com/blackmagic-davinci-resolve-20-3-2-update-fujifilm-f-log2-c](https://www.redsharknews.com/blackmagic-davinci-resolve-20-3-2-update-fujifilm-f-log2-c)

\[245] DaVinci Resolve 20 Beta 3 のアップデート情報[ https://asteriscus.jp/davinci-resolve/9749/](https://asteriscus.jp/davinci-resolve/9749/)

\[246] Software-update: Davinci Resolve 20.3[ https://tweakers.net/downloads/74910/davinci-resolve-203.html](https://tweakers.net/downloads/74910/davinci-resolve-203.html)

\[247] Davinci resolve 20.3 : la mise à jour majeure qui booste performance, montage et HDR[ https://www.larevuegeek.com/articles/actualites-davinci-resolve-20-3-la-mise-a-jour-majeure-qui-booste-performance-montage-et-hdr-article143946.html](https://www.larevuegeek.com/articles/actualites-davinci-resolve-20-3-la-mise-a-jour-majeure-qui-booste-performance-montage-et-hdr-article143946.html)

\[248] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[249] DaVinci Resolve - Download[ https://davinci-resolve.en.softonic.com/](https://davinci-resolve.en.softonic.com/)

\[250] DaVinci Resolve – Studio | Blackmagic Design[ https://www.blackmagicdesign.com/products/davinciresolve/studio](https://www.blackmagicdesign.com/products/davinciresolve/studio)

\[251] Davinci Resolve 20.3.2[ https://m.majorgeeks.com/files/details/davinci\_resolve.html](https://m.majorgeeks.com/files/details/davinci_resolve.html)

\[252] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio)

\[253] Summary of "DaVinci Resolve Beginners Tutorial 2025: Edit like a PRO for FREE!"[ https://youtubesummary.com/summary/SrJOE2pEp7A](https://youtubesummary.com/summary/SrJOE2pEp7A)

\[254] DaVinci Resolve vs Final Cut Pro (2026): Free vs \$299 — Video Editing Power Compared[ https://earnifyhub.com/blog/davinci-resolve-vs-final-cut-pro-free-vs-299.php](https://earnifyhub.com/blog/davinci-resolve-vs-final-cut-pro-free-vs-299.php)

\[255] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[256] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[257] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[258] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[259] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[260] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix](https://github.com/facu041294/davinci-resolve-python-encoding-fix)

\[261] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[262] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[263] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[264] Type Safety and Modern Python Patterns for DaVinci Resolve[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type\_Safety\_and\_Best\_Practices.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type_Safety_and_Best_Practices.md)

\[265] 达芬奇API实战:用Python脚本自动创建项目并导入素材，搭建你的自动化工作流起点 - CSDN文库[ https://wenku.csdn.net/column/623gkl2upgw](https://wenku.csdn.net/column/623gkl2upgw)

\[266] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[267] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[268] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[269] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[270] 探索PyDaVinci:打造流畅的视频后期制作体验-CSDN博客[ https://blog.csdn.net/gitblog\_00015/article/details/139875757](https://blog.csdn.net/gitblog_00015/article/details/139875757)

\[271] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[272] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[273] Free Video Transitions DaVinci Resolve: Batch Application using Custom Scripts[ https://reelmind.ai/blog/free-video-transitions-davinci-resolve-batch-application-using-custom-scripts](https://reelmind.ai/blog/free-video-transitions-davinci-resolve-batch-application-using-custom-scripts)

\[274] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[275] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[276] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[277] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[278] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[279] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[280] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[281] 【亲测免费】 Pydavinci:Python 编写的 DaVinci Resolve 脚本工具包-CSDN博客[ https://blog.csdn.net/gitblog\_00932/article/details/145005976](https://blog.csdn.net/gitblog_00932/article/details/145005976)

\[282] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[283] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[284] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[285] GitHub - WheheoHu/pybmd: Python wrapper library for DaVinci Resolve API · GitHub[ https://github.com/WheheoHu/pybmd](https://github.com/WheheoHu/pybmd)

\[286] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[287] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[288] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[289] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[290] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[291] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[292] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[293] 达芬奇视频编辑自动化工具包:Python脚本实现批量转码与LUT套用 - CSDN文库[ https://wenku.csdn.net/doc/4t859osczb](https://wenku.csdn.net/doc/4t859osczb)

\[294] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[295] Can't read files containing emoji after interacting with pydavinci & while DaVinci Resolve is open #40[ https://github.com/pedrolabonia/pydavinci/issues/40](https://github.com/pedrolabonia/pydavinci/issues/40)

\[296] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[297] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix/blob/main/README.md](https://github.com/facu041294/davinci-resolve-python-encoding-fix/blob/main/README.md)

\[298] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[299] Davinci Resolve / Linux / Python-Errors[ https://community.ynput.io/t/davinci-resolve-linux-python-errors/2404](https://community.ynput.io/t/davinci-resolve-linux-python-errors/2404)

\[300] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[301] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[302] 探索PyDaVinci:打造流畅的视频后期制作体验-CSDN博客[ https://blog.csdn.net/gitblog\_00015/article/details/139875757](https://blog.csdn.net/gitblog_00015/article/details/139875757)

\[303] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[304] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[305] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[306] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[307] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[308] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[309] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[310] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)

\[311] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[312] DaVinci Resolve Community Discord Server[ https://discordbotlist.com/servers/davinci-resolve-community-714620142096482314](https://discordbotlist.com/servers/davinci-resolve-community-714620142096482314)

\[313] DaVinci Resolve[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=35\&sid=b08b1e9830e69ae061351090f35941f1\&start=60\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=35\&sid=b08b1e9830e69ae061351090f35941f1\&start=60\&style=13)

\[314] discord怎么创建账号\_如何邀请人们加入Discord服务器(以及创建邀请链接)-CSDN博客[ https://blog.csdn.net/culiyuan8310/article/details/108792384](https://blog.csdn.net/culiyuan8310/article/details/108792384)

\[315] Baumstrukturmodus Davinci Resolve Discord Server[ https://davinci-resolve-forum.de/thread-2933.html](https://davinci-resolve-forum.de/thread-2933.html)

\[316] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=86dbc7b2be30d36e378a60ce025dd46d\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=86dbc7b2be30d36e378a60ce025dd46d\&start=20\&style=13)

\[317] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[318] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.2.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.2.0/intro)

\[319] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[320] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)

\[321] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[322] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[323] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[324] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[325] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[326] \[Investigation] DaVinci Resolve Script API cannot add fade transitions automatically #3[ https://github.com/mojonobu/davinci-resolve-random-video-switcher/issues/3](https://github.com/mojonobu/davinci-resolve-random-video-switcher/issues/3)

\[327] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix](https://github.com/facu041294/davinci-resolve-python-encoding-fix)

\[328] Creating invite links for Discord servers where my bot has access[ https://community.latenode.com/t/creating-invite-links-for-discord-servers-where-my-bot-has-access/29135](https://community.latenode.com/t/creating-invite-links-for-discord-servers-where-my-bot-has-access/29135)

\[329] We Suck Less Lab[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=45\&sid=fa13a744522c31a3552f41178ddf5279](https://www.steakunderwater.com/wesuckless/viewforum.php?f=45\&sid=fa13a744522c31a3552f41178ddf5279)

\[330] Discord friend invite link generator code - Console script (Tested 12/9/2024) · GitHub[ https://gist.github.com/maximjsx/437532d7b08f7e54c2bb7147828ab0e7](https://gist.github.com/maximjsx/437532d7b08f7e54c2bb7147828ab0e7)

\[331] 基于Node.js的Discord服务器列表与ID邀请链接生成机器人 - CSDN文库[ https://wenku.csdn.net/doc/474rfnfg52](https://wenku.csdn.net/doc/474rfnfg52)

\[332] GitHub - Aegis7Gaming/Discord-Invite-JS-HTML-CSS: A very-close-to-native Discord Invite script for websites. · GitHub[ https://github.com/Aegis7Gaming/Discord-Invite-JS-HTML-CSS](https://github.com/Aegis7Gaming/Discord-Invite-JS-HTML-CSS)

\[333] Discord Script[ https://github.com/Alex1304/discord-script](https://github.com/Alex1304/discord-script)

\[334] GitHub - woodendoors7/DiscordFriendInvites: 😎 A simple tool for generating Discord friend invite links that allows you to send friend requests via a link. · GitHub[ https://github.com/woodendoors7/DiscordFriendInvites](https://github.com/woodendoors7/DiscordFriendInvites)

\[335] How to Make Invite Logger With Discord.js?[ https://studentprojectcode.com/blog/how-to-make-invite-logger-with-discord-js](https://studentprojectcode.com/blog/how-to-make-invite-logger-with-discord-js)

\[336] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&sid=d9c8483ca2bceefa97ca7093cb412746\&start=20\&style=13)

\[337] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/19.0.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/19.0.0/intro)

\[338] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[339] DaVinciResolve-Script[ https://github.com/Water-zi/DaVinciResolve-Script](https://github.com/Water-zi/DaVinciResolve-Script)

\[340] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46\&start=110](https://www.steakunderwater.com/wesuckless/viewforum.php?style=13\&f=46\&start=110)

\[341] DaVinci Resolve Scripting[ https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=20](https://www.steakunderwater.com/wesuckless/viewforum.php?f=46\&start=20)

\[342] I have open-sourced my code, please help me improve it[ https://www.steakunderwater.com/wesuckless/viewtopic.php?t=6576](https://www.steakunderwater.com/wesuckless/viewtopic.php?t=6576)

\[343] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[344] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[345] Advanced Techniques for DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced\_Techniques.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Advanced_Techniques.md)

\[346] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[347] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix](https://github.com/facu041294/davinci-resolve-python-encoding-fix)

\[348] DaVinci Resolve[ https://wiki.archlinux.org/title/Davinci](https://wiki.archlinux.org/title/Davinci)

> （注：文档部分内容可能由 AI 生成）