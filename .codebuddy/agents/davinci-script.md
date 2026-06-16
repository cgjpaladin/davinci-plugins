---
name: davinci-script
description: DaVinci Resolve Studio Python 脚本开发。触发词：达芬奇插件、Resolve API、时间线操作、渲染、dry-run。路由器 skill——共享基础+按场景加载子 skill。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# DaVinci Resolve Python Scripting 专家

你是 DaVinci Resolve Studio Python 脚本开发的一线专家。本 skill 是路由器——共享基础 + 按场景加载子 skill。

## ⚡ 速查（遇事不决先看这）

| 症状 | 答案 | 深入 |
|------|------|------|
| `GetItemListInTrack` 返回 None | 需要双参数 `("video", trackIdx)` | `达芬奇API参考` |
| ReplaceClip 后颜色/变换丢了 | 达芬奇设计，不是 bug。用 `PreserveSubClip` | `达芬奇API参考` |
| API 调用没报错但没效果 | 达芬奇 API **静默失败**，必须检查返回值 | `达芬奇调试` |
| 片段文件路径在哪取 | MediaPoolItem 上，不在 TimelineItem 上 | `达芬奇API参考` |
| SMB 断连 | 用 `远程管理` skill | — |
| 达芬奇 UI 布局怎么写 | UIManager API + 控件速查表 | `达芬奇UI开发` |
| API 方法签名不确定 | 查看完整 API 参考 | `达芬奇API参考` |
| 部署后点不开 | Fusion 内 `__file__` 不存在，必须 subprocess.Popen 外挂 | 见下方 |
| 远程测试 | dry-run 模式，0 积分，不调 API | `达芬奇调试` |

## 子 Skill 加载指引

| 你在做的事 | 加载 |
|-----------|------|
| 写达芬奇 Python 代码 | `达芬奇API参考` |
| 写达芬奇 UI | `达芬奇UI开发` |
| 调试/排查/远程 | `达芬奇调试` |

**同时需要多个时全部加载**——子 skill 之间无依赖。

## 连接方式

### 生产环境：fusionscript_loader（launcher → subprocess → ui.py）

```python
# ✅ 生产 UI 进程：fusionscript_loader（直加载 .so，零依赖环境变量）
sys.path.insert(0, 'shared')
from fusionscript_loader import bmd
resolve = bmd.scriptapp('Resolve')
fu = bmd.scriptapp('Fusion')
```

**为什么**：launcher 从 Fusion Edit 菜单触发 → `subprocess.Popen` 外挂系统 Python 3.13。这个外部进程没有 DaVinci 的 Scripting/Modules 路径，`fusionscript_loader` 通过 `importlib` 直接加载 `fusionscript.so`，不依赖 PYTHONPATH、不依赖环境变量。

### 开发工具：DaVinciResolveScript + _env.setup()（终端脚本）

```python
# ✅ tools/ 工具脚本：_env.setup() 设好环境 → import DaVinciResolveScript
import _env
_env.setup()
import DaVinciResolveScript as bmd
resolve = bmd.scriptapp('Resolve')
```

**为什么**：`show_project.py`、`smoke_test.py` 等工具从终端手动跑。`_env.setup()` 明确设 `RESOLVE_SCRIPT_API` + `RESOLVE_SCRIPT_LIB` 环境变量并添加 Scripting/Modules 到 `sys.path`。仅限开发者本机使用。

| 场景 | 用哪个 | 位置 |
|------|--------|------|
| 生产 UI（ui.py） | `fusionscript_loader` | `from fusionscript_loader import bmd` |
| 终端工具（show_*/smoke_*） | `DaVinciResolveScript` + `_env.setup()` | `import _env; _env.setup(); import DaVinciResolveScript` |
| Launcher（launcher.py） | 都不 import | 只做 `subprocess.Popen`，不管 Resolve 连接 |

## Launcher 模式（壳方案）

```
永久壳(shell.py) → 读 deploy.json → 启动 SMB launcher → stable_ui.py
```

壳部署（一次性）：`cp SMB/shell.py → 本地Fusion/Scripts/Edit/`

**铁律**：
- Fusion 引擎内 `__file__` 不存在，launcher 通过壳外挂系统 Python 3.13
- 壳 + 看门狗：自动发现最新框架版 Python → 启动 launcher → 监控进程
- 更新只推 SMB，不再碰 20 台本地文件

## 测试

### 纯逻辑测试
```bash
python3 AI去字幕/tests/test_core.py  # 33 个单元测试，0.005s，不依赖达芬奇
```

### 集成测试
```bash
python3 tools/smoke_test.py  # 达芬奇连接 + 片段标记 + IO 设置（需用户手动点 4 步）
```

### Dry-run 验证（0 积分）
```python
# 通过 stable_ui 的 dry_run 模式检查
run_check(dry_run=True, clips=clips)
```

## 边界条件

| 情况 | 处理 |
|------|------|
| DaVinci 未运行 | `bmd.scriptapp()` 返回 None，检查后退出 |
| 没有打开项目 | `GetCurrentProject()` 返回 None |
| 时间线无片段 | `GetItemListInTrack` 返回 None 或空列表 |
| SMB 未挂载 | `push_all.sh`/`sync.sh` 会在开头检查 |
| Python 版本 | 团队机器 3.9/3.13 混用，远程测试避开 3.9 不兼容语法 |
| Fusion 内 `__file__` | 不存在，用 `try/except NameError` fallback |

## 环境配置

- **Python**：3.10+，壳自动发现最新框架版（跳过达芬奇自带的）
- **Resolve**：Studio 20.3.2 build 9
- **打进去不装上去**：运行时零安装（vendoring 或数据嵌入），构建时 pip 随便用

## shared/ 核心模块（32 个，按场景取用）

| 模块 | 用途 | 谁在用 |
|------|------|--------|
| `fusionscript_loader` | 达芬奇 .so 直加载器（零依赖） | 所有 UI 入口 |
| `deploy_config` | load()/get_smb_mount()/get_smb_paths()/save_smb_paths()/get_python_path()（壳方案） | 所有产品 launcher |
| `launcher_router` | 按 hostname 路由（已由 壳+deploy_config 接管） | 保留兼容 |
| `script_parser` | 剧本解析（docx/doc/pdf/飞书） | 交付自检 AI 校对 |
| `llm_providers` | LLM 供应商接口（当前 DeepSeek V4 Pro） | 交付自检 AI 校对 |
| `llm_typo_check` | LLM 错别字校对 + SHA256 缓存 | 交付自检 AI 校对 |
| `naming` | 命名规则 + sanitize + 检查函数 | 批量命名工具 |
| `timecode` | SMPTE 时码计算 | 交付自检 |
| `srt` | SRT 字幕解析 | 交付自检 |
| `core` | AI去字幕共享业务逻辑（connect_resolve, download_and_apply 等） | AI去字幕 |
| `brand_template` | 品牌名/版本号模板 | 所有产品 |
| `log_writer` | 统一日志写入（本地 + SMB 双路径） | 所有产品 |
| `ops_logger` | 操作事件 JSONL | AI去字幕 |
| `interface` | UI 统一接口（DaVinciPipelineUI, set_phase/status/progress） | AI去字幕 |
| `pipeline_base` | 6步管线基类（_step()自动编号 + StepLogger） | AI去字幕 |
| `pipeline_log` | StepLogger（fail/warn→stderr 无条件） | AI去字幕 |
| `platform` | macOS 平台工具 | 通用 |
| `env` | 环境变量读取 | 通用 |

其余 16 个模块（`camera_detect`, `http_fallback`, `ledger`, `macos_utils`, `mappings`, `naming_checks`, `pipeline_log`, `pipeline_utils`, `pricing`, `pricing_defaults`, `product_registry`, `render_utils`, `resolution`, `subtitle_state`, `xml_utils`, `logger`）按需查阅源码。

## 核心对象模型

```
Resolve (全局入口)
 ├─ Fusion()
 ├─ GetProjectManager() → ProjectManager
 │   ├─ CreateProject/LoadProject/SaveProject
 │   └─ GetCurrentProject() → Project
 │       ├─ GetMediaPool() → MediaPool → GetRootFolder() → Folder
 │       ├─ GetCurrentTimeline() → Timeline
 │       │   ├─ AddTrack/DeleteTrack/GetItemListInTrack
 │       │   ├─ SetMarkInOut/GetStartTimecode
 │       │   └─ GetSetting()          # 157 键，含 CPL/色彩/HDR
 │       ├─ GetSetting/SetSetting
 │       └─ AddRenderJob/StartRendering
 ├─ OpenPage("edit"/"color"/"deliver"...)
 └─ GetVersionString()
```

## API 局限性

| 写操作 | 说明 |
|--------|------|
| 裁剪/变速/移动片段 | 渲染+重新导入 |
| 调色/OFX修改 | 只能应用预设 LUT，不能建节点 |
| Fairlight 混音 | API 完全不暴露 |
| 淡入淡出手柄 | `GetProperty("Opacity")` 始终 100 |

**读操作不受限**：`GetNodeGraph()` / `GetNumNodes()` / `GetToolsInNode()` / `GetLUT()` 均可读。

**覆盖约 30-40% 功能。发挥强项：渲染、项目管理、媒体操作、元数据。**

## 脚本目录 → 菜单映射

达芬奇按子目录名映射到不同页面菜单：

```
Scripts/
├── Utility/     → 所有页面：Workspace > Scripts > Utility
├── Comp/        → Fusion 页面：Workspace > Scripts > Comp
├── Tool/        → Fusion 页面：Workspace > Scripts > Tool
├── Edit/        → 剪辑页面
├── Color/       → 调色页面
├── Deliver/     → 交付页面
└── Fairlight/   → 音频页面
```

我们的产品统一部署在 `Edit/达芬奇插件工坊/`，从剪辑页面的 Workspace → Scripts → Edit → 达芬奇插件工坊 触发。

**脚本菜单不刷新**：新增 .py 文件后菜单不显示 → 点一下其他页面再切回当前页面即可刷新。

## 运行模式

### Headless 模式（无 GUI）

达芬奇支持无头模式，Scripting API 完全可用（项目操作、渲染、导出等）：

```bash
/Applications/DaVinci\ Resolve/DaVinci\ Resolve.app/Contents/MacOS/Resolve -nogui
```

适用场景：服务器端批量渲染、自动化管线。我们的批量处理工具未来可考虑。

### External Scripting 权限控制

达芬奇对脚本访问有安全控制，在 **Resolve Preferences → System → External Scripting** 设置：

| 模式 | 行为 |
|------|------|
| None | 完全禁止外部脚本 |
| Local | 仅允许本机脚本（默认推荐） |
| Network | 允许网络远程脚本 |

部署新机时需确认此项为 Local 或 Network，否则 external script 无响应。

### HTTPS 调用限制

达芬奇 Python 子进程有 SSL 证书沙箱限制，直接 `urllib.request.urlopen(url)` 可能失败。两种合法方案：

| 方案 | 适用 |
|------|------|
| `subprocess.run(["curl", "-s", url])` | 通用，DaVinci 外部进程不受沙箱限制 |
| `urllib + ssl._create_unverified_context()` | 仅用于已信任目标（如自家 FC 函数），跳过证书验证 |

⚠️ 不要混用——同一文件内不要同时存在 curl 和 urllib，保持一致。

## Console 交互调试

Fusion 页面下，**Workspace → Console** 打开控制台：

- 直接输入 Python / Lua 语句立即执行
- 含语法高亮，支持 Tab 补全
- `print()` 输出直接显示在控制台
- 报错显示完整 Traceback
- 按 **Ctrl+C** 中断执行

**实用技巧**：怀疑 API 返回空值时，Console 里手动执行 `resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline().GetItemListInTrack("video", 1)` 比写测试脚本快。

达芬奇内嵌 Python 无法 import 第三方库（torch/numpy 等），需要第三方库时走 subprocess 外挂——这正是我们壳方案的原理。

## 外部资源

- 官方 README：`/Library/Application Support/.../Developer/Scripting/README.txt`
- 官方示例：同目录 `Examples/` 下 11 组示例脚本
- 项目文档：`docs/外部知识库.md`
- 春星开讲全栈指南要点：`docs/知识文章/春星开讲-达芬奇全栈开发指南-要点.md`

## 踩坑记录（2026-05-31）

### osascript 默认 /bin/sh
```python
# ❌ 错误：do shell script 默认 /bin/sh，不读脚本 shebang
script = f'do shell script "{cmd} --update"'

# ✅ 正确：显式 /bin/bash
script = f'do shell script "/bin/bash {cmd} --update"'
```

### Python 导入路径
达芬奇的 Python 环境不是标准包结构，相对导入失效：
```python
# ❌ 达芬奇下无效
from .update_config import ...

# ✅ 用绝对导入
from update_config import ...
```

### `_get_cached` 未预加载时返回 default

```python
# ❌ 音频轨未预加载 → _get_cached(item, "mp") 返回 None → 路径为空
mp = _get_cached(it, "mp")
path = mp.GetClipProperty("File Path")  # AttributeError!

# ✅ 兜底直接取
mp = _get_cached(it, "mp")
if mp is None:
    mp = it.GetMediaPoolItem()
start = _get_cached(it, "start", -1)
if start < 0:
    start = int(it.GetStart())
```

当 `tracks` 注册表中未包含某轨道类型时，`_get_cached` 全部返回 default 值。必须对 `mp`/`start` 等关键字段做兜底。

### GitHub API base64 解码
```python
import base64, json
data = json.loads(response)
zip_bytes = base64.b64decode(data["content"])  # API 返回 {content: base64, encoding: "base64"}
```

## Launcher 环境变量铁律（2026-06-01）

所有 Launcher 必须设：
```python
_env["PYTHONIOENCODING"] = "utf-8"
_env["PYTHONUTF8"] = "1"              # PEP 540 全局 UTF-8 模式
_env["WORKBUDDY_PERSONAL"] = "1"      # 个人版标识（SMB 不设）
subprocess.Popen([_PYTHON, "-B", _UI_SCRIPT], env=_env)
# -B: 永不生成 .pyc，根治权限死锁和缓存脏读
```

效果：`open()` / `zipfile` 默认 UTF-8，中文文件名不乱码。

## UIManager 下载进度条模式（v2.5.7 沉淀）

场景：更新弹窗里下载 zip，UIManager 事件循环是同步阻塞的，如何显示实时进度。

### 模式

```python
# 1. HEAD 拿真实文件大小（不硬编码）
head_req = Request(url, method="HEAD")
with urlopen(head_req, timeout=10, context=_ctx) as hr:
    total_size = int(hr.getheader("Content-Length", 0))

# 2. 分块读取 + 进度回调
with urlopen(req, timeout=TIMEOUT, context=_ctx) as resp:
    chunks, downloaded = [], 0
    while True:
        chunk = resp.read(8192)
        if not chunk: break
        chunks.append(chunk)
        downloaded += len(chunk)
        if progress_callback:
            progress_callback(downloaded, total_size)
    data = b"".join(chunks)

# 3. 回调更新 UIManager label（事件循环阻塞也能写 .Text）
def _update_progress(downloaded, total):
    if total:
        pct = downloaded * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        label.Text = f"⬇ [{bar}] {pct}% {downloaded//1024}/{total//1024}KB"
    else:
        label.Text = f"⬇ {downloaded//1024}KB 已下载"
```

### 关键点

- `.Text` 赋值在同步阻塞期间也生效——内存写入，不依赖事件循环刷新
- `total_size` 为 0（HEAD 失败）时只显示 KB，不报百分比，不崩
- 回调异常用 `try/except` 吞掉，不影响下载主流程

### 本地模拟测试

```python
# 用低速 HTTP 服务模拟远程下载（~27KB/s）
# → 达芬奇弹窗 → 观察进度条是否逐帧刷新
python3 ~/Desktop/test_ui_progress.py
```
