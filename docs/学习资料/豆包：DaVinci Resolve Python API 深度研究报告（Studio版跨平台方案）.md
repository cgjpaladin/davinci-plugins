# DaVinci Resolve Python API 深度研究报告（Studio 版跨平台方案）

## 摘要与核心建议

本报告针对 DaVinci Resolve Studio Python API 的**5 个关键技术维度**展开深度研究，覆盖插件架构、大文件云传输、Apple Silicon 优化、非开发者分发与自动化测试，所有方案均适配 Windows 10 + 与 macOS 14+（含 Apple Silicon M4）双平台。

**核心发现与建议速览**：



1. **插件架构**：Resolve Python 环境仅支持线程级并发（子进程无法访问 Resolve 对象），商业级异步需通过「本地 FastAPI 中间层 + 线程池」实现；跨会话状态建议用`fusion:SetData()`或 SQLite，避免全局变量。

2. **大文件传输**：100MB-2GB 视频需采用分块上传（10-50MB / 块），优先直接调用渲染缓存文件，后台运行可通过 NSSM（Windows）或 LaunchDaemon（macOS）实现。

3. **Apple Silicon 优化**：M4 的 IO 密集型多线程效率比单线程高 3-5 倍，但 Python API 未开放 Metal 直接调用；16GB 统一内存需限制 Resolve 内存占比≤75%。

4. **非开发者分发**：采用「PyInstaller 打包 + 批处理 / Shell 安装脚本」，依赖需部署到 Resolve 专属模块目录；许可证建议用「邮箱 + 硬件指纹」离线激活。

5. **自动化测试**：无官方 Mock 库，需手动模拟`DaVinciResolveScript`对象；CI 需用 Rocky Linux 容器部署 Resolve，日志优先用标准`logging`模块。



***

## 1. 实际插件架构模式：构建多云 API 调用插件

### 1.1 商业插件异步 API 调用架构

DaVinci Resolve 的 Python API 运行在独立于主 GUI 的解释器进程中 —— 这是官方为避免脚本阻塞 UI 渲染设计的隔离机制，但也导致脚本无法直接访问主进程的实时状态[(351)](https://blog.csdn.net/weixin_35835030/article/details/156931756)。商业插件（如 HunyuanVideo-Foley）普遍采用「本地中间 API 层隔离」架构解决异步调用阻塞问题：核心逻辑是通过 FastAPI/Flask 在本地启动轻量级 Web 服务，将云 API 调用（去水印、唇形同步等）转发至该服务，而非直接在 Resolve 脚本中执行网络请求[(41)](https://blog.csdn.net/weixin_42284380/article/details/156885642)。

该架构的核心价值在于：中间层服务作为独立进程，可通过`concurrent.futures.ThreadPoolExecutor`或`asyncio`处理高并发 IO，完全规避 Resolve 主线程的阻塞风险；即使 Resolve 因渲染任务占用资源，中间层仍能独立调度网络请求[(4)](https://www.iesdouyin.com/share/video/7596914291085728064)。例如 HunyuanVideo-Foley 插件的中间层，通过 WebSocket 与 Resolve 脚本通信，既保证了异步调用的效率，又能实时将云 API 的进度反馈给 Resolve UI[(351)](https://blog.csdn.net/weixin_35835030/article/details/156931756)。

### 1.2 Resolve Python 环境的线程 / 多进程限制

#### 线程支持

Resolve Python 环境原生支持`threading`模块与`concurrent.futures.ThreadPoolExecutor`，且在 IO 密集型任务（如多云 API 调用）中性能表现优异 —— 这是因为 Python GIL（全局解释器锁）在 IO 等待时会主动释放，Apple Silicon 的多核心架构可充分利用空闲资源，实测多线程效率比单线程高 3-5 倍[(258)](https://blog.csdn.net/qq_34252622/article/details/157729092)。

#### 多进程限制

**关键限制**：子进程无法访问 Resolve 对象（`scriptapp("Resolve")`返回`None`），推测是官方为保障状态一致性设计的进程级对象隔离机制[(367)](https://ask.csdn.net/questions/8964429)。因此，多进程仅适用于完全脱离 Resolve API 的纯计算任务（如视频帧预处理），且需通过文件或套接字实现进程间通信[(140)](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)。

**跨平台差异**：Windows 与 macOS 的线程调度逻辑无明显差异，但环境变量配置路径不同 ——Windows 需设置`RESOLVE_SCRIPT_API`为`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting`，macOS 为`/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting`[(399)](https://blog.51cto.com/u_16099239/14307371)。

### 1.3 插件跨会话保持状态的方式

Resolve 脚本是无状态的，跨会话（重启 Resolve）保持状态需通过以下方案：

#### 方案 1：Fusion 内置 API（官方推荐）

通过`fusion:SetData(key, value)`存储键值对，支持跨会话读取，但**仅支持基础类型**（字符串、数字、布尔值），无法存储复杂对象（如类实例、字典）[(73)](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)。其 Python 调用示例如下：



```
fusion = resolve.Fusion()

\# 存储状态（如已完成的云API任务ID）

fusion:SetData("LastWatermarkTaskID", "task\_12345")

\# 读取状态

task\_id = fusion:GetData("LastWatermarkTaskID")
```

> 注：该 API 为 Fusion 兼容接口，即使当前未打开 Fusion 页面也可调用，但值会全局存储在 Resolve 配置文件中，不同项目共享同一状态空间
>
> [(73)](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)
>
> 。

#### 方案 2：本地数据库（复杂状态）

对于需要存储复杂状态（如多任务进度、用户偏好设置）的场景，建议使用 SQLite 数据库 ——Python 标准库自带`sqlite3`模块，无需额外安装，且性能足以支撑小体量状态存储[(19)](https://www.bilibili.com/opus/1038987515597422594)。例如，可创建`plugin_state.db`文件，记录每个云 API 任务的状态、参数与结果，重启 Resolve 后通过查询数据库恢复状态。

#### 不推荐方案



* **全局变量**：Resolve 重启后会被重置，仅适用于单会话临时状态存储[(19)](https://www.bilibili.com/opus/1038987515597422594)。

* **环境变量**：仅支持字符串类型，且系统级环境变量易与其他应用冲突，不建议用于插件状态管理[(19)](https://www.bilibili.com/opus/1038987515597422594)。

### 1.4 真实商业插件架构示例（伪代码）

以下是调用 4 个云 API 的插件核心架构伪代码，参考自 HunyuanVideo-Foley 的开源实现[(351)](https://blog.csdn.net/weixin_35835030/article/details/156931756)：



```
\# Resolve端脚本（UI交互+任务触发）

import DaVinciResolveScript as dvr

import requests

resolve = dvr.scriptapp("Resolve")

fusion = resolve.Fusion()

def trigger\_cloud\_tasks():

&#x20;   \# 1. 获取当前时间线的选中片段路径

&#x20;   project = resolve.GetProjectManager().GetCurrentProject()

&#x20;   timeline = project.GetCurrentTimeline()

&#x20;   selected\_clips = timeline.GetSelectedClips()

&#x20;   if not selected\_clips:

&#x20;       print("未选中任何片段")

&#x20;       return

&#x20;   clip\_path = selected\_clips\[0].GetMediaPoolItem().GetClipProperty("File Path")

&#x20;   \# 2. 调用本地中间层API，转发云处理任务

&#x20;   \# 中间层默认监听127.0.0.1:8000，避免跨网络安全风险

&#x20;   payload = {

&#x20;       "clip\_path": clip\_path,

&#x20;       "tasks": \["remove\_watermark", "lip\_sync", "voice\_clone", "super\_resolution"]

&#x20;   }

&#x20;   try:

&#x20;       response = requests.post("http://127.0.0.1:8000/process", json=payload)

&#x20;       response.raise\_for\_status()

&#x20;       task\_id = response.json()\["task\_id"]

&#x20;       \# 3. 存储任务ID到跨会话状态

&#x20;       fusion:SetData("CurrentCloudTaskID", task\_id)

&#x20;       print(f"任务已启动，ID: {task\_id}")

&#x20;   except requests.exceptions.RequestException as e:

&#x20;       print(f"调用中间层失败: {e}")

\# 注册到Resolve菜单（需放置在指定脚本目录）

trigger\_cloud\_tasks()
```



```
\# 本地中间层服务（FastAPI+线程池）

from fastapi import FastAPI

from concurrent.futures import ThreadPoolExecutor

import requests

app = FastAPI()

executor = ThreadPoolExecutor(max\_workers=4)  # 对应4个云API任务

\# 模拟云API调用

def call\_cloud\_api(task\_type, clip\_path):

&#x20;   \# 实际场景需替换为对应云服务的API密钥与端点

&#x20;   api\_endpoints = {

&#x20;       "remove\_watermark": "https://api.example.com/remove-watermark",

&#x20;       "lip\_sync": "https://api.example.com/lip-sync",

&#x20;       "voice\_clone": "https://api.example.com/voice-clone",

&#x20;       "super\_resolution": "https://api.example.com/super-resolution"

&#x20;   }

&#x20;   try:

&#x20;       with open(clip\_path, "rb") as f:

&#x20;           response = requests.post(

&#x20;               api\_endpoints\[task\_type],

&#x20;               files={"file": f},

&#x20;               headers={"Authorization": "Bearer YOUR\_API\_KEY"}

&#x20;           )

&#x20;       response.raise\_for\_status()

&#x20;       return response.json()

&#x20;   except Exception as e:

&#x20;       return {"error": str(e)}

@app.post("/process")

def process\_clip(clip\_path: str, tasks: list):

&#x20;   \# 并行执行多个云API任务

&#x20;   futures = \[executor.submit(call\_cloud\_api, task, clip\_path) for task in tasks]

&#x20;   results = \[future.result() for future in futures]

&#x20;   return {"task\_id": "unique\_task\_id", "results": results}
```



***

## 2. 外部 API 集成：文件上传与下载模式

### 2.1 大视频文件传输瓶颈分析

100MB-2GB 视频文件的传输瓶颈主要包括：



* **内存限制**：一次性读取大文件会导致 Resolve 内存溢出 ——16GB 内存的系统无法直接加载 2GB 视频到内存中，必须通过分块机制规避。

* **带宽波动**：大文件单次上传易因网络波动失败，需支持断点续传的分块传输协议[(181)](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/)。

* **Resolve API 限制**：MediaStorage API 仅支持导入 / 导出媒体，未提供流式读取接口，无法直接从 Resolve 内部实现流式上传[(168)](https://tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOop2ClGpV_Q6WXD-f9Iy7twGD6BNtHM53QEUhQrmH1bPKLaoAoZA)。

### 2.2 从 Resolve 流式上传与缓存利用

#### 分块上传实现

**最优实践**：采用分块上传策略，块大小需同时满足云服务要求与内存效率 —— 建议设置为 10-50MB（需为 256KiB 的整数倍），既减少请求开销，又避免内存占用过高[(181)](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/)。

以下是分块上传的核心代码示例，已适配 Resolve 环境的路径规则[(181)](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/)：



```
import os

import requests

def upload\_large\_file(file\_path, chunk\_size=10\*1024\*1024):  # 10MB分块

&#x20;   \# 1. 初始化分块上传（需替换为目标云服务的初始化接口）

&#x20;   init\_url = "https://api.example.com/initiate-upload"

&#x20;   file\_name = os.path.basename(file\_path)

&#x20;   file\_size = os.path.getsize(file\_path)

&#x20;  &#x20;

&#x20;   init\_response = requests.post(init\_url, json={

&#x20;       "file\_name": file\_name,

&#x20;       "file\_size": file\_size,

&#x20;       "chunk\_size": chunk\_size

&#x20;   })

&#x20;   upload\_id = init\_response.json()\["upload\_id"]

&#x20;   part\_count = (file\_size + chunk\_size - 1) // chunk\_size  # 计算分块数量

&#x20;   \# 2. 逐块上传

&#x20;   upload\_url = "https://api.example.com/upload-part"

&#x20;   with open(file\_path, "rb") as f:

&#x20;       for part\_num in range(1, part\_count + 1):

&#x20;           chunk = f.read(chunk\_size)

&#x20;           if not chunk:

&#x20;               break

&#x20;           \# 调用云服务分块上传接口

&#x20;           response = requests.post(

&#x20;               f"{upload\_url}?upload\_id={upload\_id}\&part\_num={part\_num}",

&#x20;               files={"chunk": chunk}

&#x20;           )

&#x20;           response.raise\_for\_status()

&#x20;           print(f"分块 {part\_num}/{part\_count} 上传完成")

&#x20;   \# 3. 完成上传（需替换为目标云服务的完成接口）

&#x20;   complete\_url = "https://api.example.com/complete-upload"

&#x20;   requests.post(complete\_url, json={"upload\_id": upload\_id})

&#x20;   print("文件上传完成")
```

#### 渲染缓存利用

Resolve 的渲染缓存文件是已完成解码 / 渲染的媒体文件，直接上传可避免重复编码，节省时间与资源。其默认路径为：



* Windows：`C:\Users\<User>\AppData\Roaming\Blackmagic Design\DaVinci Resolve\CacheClip`

* macOS：`~/Library/Caches/Blackmagic Design/DaVinci Resolve/CacheClip`

> 注：缓存路径可在 Resolve 偏好设置中修改，但当前 Python API 无法直接获取自定义路径，需引导用户手动配置或硬编码（需适配不同系统）
>
> [(168)](https://tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOop2ClGpV_Q6WXD-f9Iy7twGD6BNtHM53QEUhQrmH1bPKLaoAoZA)
>
> 。

### 2.3 上传 / 下载进度显示

#### 方案 1：控制台打印（简单易用）

通过轮询云 API 的进度接口或分块上传的完成比例，将进度实时打印到 Resolve 控制台。例如，在分块上传时，每完成一个分块就计算当前完成百分比并打印：



```
\# 分块上传时的进度计算

progress = (part\_num / part\_count) \* 100

print(f"上传进度: {progress:.2f}%")
```

该方案无需额外依赖，适配所有平台，但仅能在控制台查看进度，适合技术用户或调试场景。

#### 方案 2：Fusion UI 组件（原生体验）

Resolve 内置基于 Qt 的 UI 组件（通过`fusion.UIManager`访问），可构建原生风格的进度条窗口。以下是核心代码示例，参考自开源项目 resolve-batch-exporter[(196)](https://smartanimation.xyz/davincibuilding-gui/)：



```
fu = resolve.Fusion()

ui = fu.UIManager

disp = bmd.UIDispatcher(ui)

\# 创建进度窗口

dlg = disp.AddWindow({

&#x20;   "WindowTitle": "云API处理进度",

&#x20;   "ID": "ProgressWindow",

&#x20;   "Geometry": \[100, 100, 400, 100],  # x, y, width, height

&#x20;   "Widgets": \[

&#x20;       {

&#x20;           "Type": "QLabel",

&#x20;           "ID": "ProgressLabel",

&#x20;           "Text": "正在处理...",

&#x20;           "Geometry": \[20, 20, 360, 20]

&#x20;       },

&#x20;       {

&#x20;           "Type": "QProgressBar",

&#x20;           "ID": "ProgressBar",

&#x20;           "Geometry": \[20, 50, 360, 20],

&#x20;           "Maximum": 100

&#x20;       }

&#x20;   ]

})

\# 更新进度的函数

def update\_progress(percent):

&#x20;   dlg.Find("ProgressBar").Value = percent

&#x20;   dlg.Find("ProgressLabel").Text = f"处理进度: {percent:.2f}%"

&#x20;   disp.ProcessEvents()  # 强制刷新UI

\# 使用示例（需在分块上传循环中调用）

update\_progress(50)  # 更新为50%进度
```

该方案的优势是完全原生，无需额外安装工具，但需要编写较多 UI 代码，且进度更新频率受限于云 API 的轮询间隔。

### 2.4 用户关闭控制台后脚本持续运行

Resolve 的脚本默认与控制台进程绑定，关闭控制台会终止脚本。需通过以下方案实现后台运行：

#### Windows 方案：NSSM（Non-Sucking Service Manager）

NSSM 是一款开源工具，可将任意可执行文件注册为 Windows 系统服务，即使关闭控制台或用户注销，脚本仍能持续运行。其核心步骤为：



1. 下载 NSSM 并添加到系统环境变量；

2. 执行`nssm install ResolveCloudPlugin`，在弹出的界面中配置：

* **Path**：Python 可执行文件路径（如`C:\Python39\python.exe`）；

* **Arguments**：插件脚本的完整路径（如`C:\Plugins\resolve_cloud_plugin.py`）；

1. 启动服务：`net start ResolveCloudPlugin`。

> 注：需确保 Resolve 已启动，或在脚本中添加自动启动 Resolve 的逻辑
>
> [(99)](https://www.muyanru.com/en/davinci/api/)
>
> 。

#### macOS 方案：LaunchDaemon

LaunchDaemon 是 macOS 原生的守护进程管理工具，可在系统启动时自动运行脚本。其核心步骤为：



1. 创建`com.resolve.cloudplugin.plist`文件，放置于`~/Library/LaunchAgents/`目录：



```
\<?xml version="1.0" encoding="UTF-8"?>

\<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">

\<plist version="1.0">

\<dict>

&#x20;   \<key>Label\</key>

&#x20;   \<string>com.resolve.cloudplugin\</string>

&#x20;   \<key>ProgramArguments\</key>

&#x20;   \<array>

&#x20;       \<string>/usr/bin/python3\</string>

&#x20;       \<string>/Users/\<User>/Plugins/resolve\_cloud\_plugin.py\</string>

&#x20;   \</array>

&#x20;   \<key>RunAtLoad\</key>

&#x20;   \<true/>

&#x20;   \<key>KeepAlive\</key>

&#x20;   \<true/>

\</dict>

\</plist>
```



1. 加载配置：`launchctl load ~/Library/LaunchAgents/com.resolve.cloudplugin.plist`；

2. 启动服务：`launchctl start com.resolve.cloudplugin`。

> 注：需将
>
> `<User>`
>
> 替换为实际用户名，并确保脚本路径正确
>
> [(99)](https://www.muyanru.com/en/davinci/api/)
>
> 。



***

## 3. Apple Silicon（M4）特定优化

### 3.1 Python 线程在 Apple Silicon 上的表现

Apple Silicon 采用 ARM 架构，其多核心效率在 IO 密集型任务中优势显著 ——Python 的 GIL 在 IO 等待（如网络请求、文件读写）时会主动释放，允许其他线程执行，因此多线程在这类任务中的效率比单线程高 3-5 倍[(258)](https://blog.csdn.net/qq_34252622/article/details/157729092)。

#### 实测数据（参考自通用 Python 基准测试）



| 任务类型          | 单线程耗时  | 4 线程耗时 | 加速比   |
| ------------- | ------ | ------ | ----- |
| 网络请求（4 个并行）   | 12.5 秒 | 3.2 秒  | 3.9 倍 |
| 文件读写（1GB 大文件） | 8.7 秒  | 2.1 秒  | 4.1 倍 |

> 注：上述数据为通用 Python 基准测试结果，Resolve 环境下的实际加速比可能因 Resolve 自身的资源占用略有降低，但整体趋势一致
>
> [(258)](https://blog.csdn.net/qq_34252622/article/details/157729092)
>
> 。

### 3.2 Resolve 脚本利用 Apple GPU 预处理的可行性

Resolve Studio 针对 Apple Silicon 的 Metal 框架做了深度优化，AI 降噪、Super Scale 等核心功能均可通过 Metal 调用 Apple GPU，但**Python API 未暴露直接调用 Metal 的接口**[(236)](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)。开发者无法通过脚本主动触发 GPU 预处理，仅能通过以下间接方式利用 Apple GPU：



* 调用 Resolve 内置的 GPU 加速功能（如`project.SetRenderSettings`中的 Super Scale 选项）；

* 使用支持 Metal 的第三方库（如`torch.backends.mps`），但需确保库与 Resolve 的 Python 版本兼容（Resolve 18 + 支持 Python 3.9+）[(236)](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)。

### 3.3 内存管理方法（针对 16GB 统一内存）

Apple Silicon 采用统一内存架构（CPU、GPU 共享同一块物理内存），内存管理需同时兼顾 CPU 与 GPU 的需求，避免内存 contention（资源竞争）。以下是针对 16GB 内存的优化建议：

#### 1. 限制 Resolve 内存占比

在 Resolve 偏好设置中，将「Limit Resolve Memory Usage」设置为系统内存的 75%（即 12GB），预留 25%（4GB）给系统与其他应用，避免 Resolve 占用过多内存导致系统卡顿[(278)](https://o-sidemedia.com/davinci-resolve-system-preferences-performance-settings/)。

#### 2. 优化缓存设置



* 媒体缓存大小限制为 100GB，避免缓存文件占用过多磁盘空间；

* 勾选「启用缓存压缩」（Resolve 18.5 + 支持），可将缓存文件大小压缩至原大小的 60% 左右，节省磁盘空间的同时，对性能影响极小[(274)](https://blog.csdn.net/sinat_41617212/article/details/153050394)。

#### 3. 代码层优化



* 使用生成器替代列表推导式，避免一次性加载大量数据到内存 —— 例如，分块读取文件时，用生成器逐块返回数据，而非将所有块存储到列表中；

* 手动触发垃圾回收：在处理完大文件或复杂对象后，调用`gc.collect()`释放未被引用的内存；

* 避免全局变量：全局变量的生命周期与脚本一致，会长期占用内存，建议使用局部变量或类成员变量替代[(247)](https://cloud.tencent.com/developer/article/2661345?frompage=seopage)。

### 3.4 M 系列芯片上的性能基准数据

#### 整机性能对比（Resolve 19.1.3）



| 指标                         | Mac mini M4（10 核 CPU，10 核 GPU，16GB） | Intel i5-1135G7（4 核 8 线程，16GB） |
| -------------------------- | ----------------------------------- | ------------------------------ |
| 4K 60fps H.265 导出耗时（10 分钟） | 8 分 15 秒                            | 35 分 22 秒                      |
| 启动时间                       | 12 秒                                | 28 秒                           |
| 内存带宽                       | 102.4 GB/s                          | 41.6 GB/s                      |

> 注：上述数据来自 PugetBench for DaVinci Resolve 1.1.1 基准测试，M4 的导出耗时比 i5-1135G7 低 77%，内存带宽高 146%，核心优势来自统一内存架构与更高的单核心效率
>
> [(263)](https://news.ycombinator.com/item?id=42120859)
>
> 。

#### Python 脚本性能对比

M4 的单线程性能比 Intel i7-1360P 高约 40%，多线程性能高约 2.5 倍 —— 这是因为 Apple Silicon 的单核心 IPC（每周期指令数）更高，且多核心调度更高效。例如，批量处理 100 个视频文件的元数据时，M4 的处理时间仅为 i7-1360P 的 30% 左右[(237)](https://dev.larryjordan.com/articles/performance-test-davinci-resolve-19-1/)。



***

## 4. 面向非开发者用户的打包与分发

### 4.1 一键安装与依赖管理

目标用户为不懂 Python 的视频编辑，需实现**零命令行操作**的安装体验。

#### 打包工具选择



* **推荐**：PyInstaller—— 支持将 Python 脚本与依赖打包为单可执行文件（Windows 为`.exe`，macOS 为`.app`），无需用户安装 Python 环境。需注意，打包时需通过`.spec`文件声明 Resolve 专属依赖（如`DaVinciResolveScript`），避免打包失败[(448)](https://github.com/Polabiel/DaVinciRPC)。

* **备选**：Nuitka—— 将 Python 代码编译为 C 语言可执行文件，性能更高，但编译时间较长，且对第三方库的兼容性略低于 PyInstaller[(315)](https://www.iesdouyin.com/share/video/7515002603589537084)。

#### 依赖管理

Resolve 的 Python 环境是独立的，第三方库需安装到 Resolve 专属模块目录，而非系统 Python 目录。核心步骤为：



1. 获取 Resolve 的模块目录路径：

* Windows：`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`

* macOS：`/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules`

1. 使用`pip install --target`命令将依赖安装到该目录：



```
\# 示例：安装requests库到Resolve模块目录

pip install requests --target "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
```

> 注：需确保 pip 版本与 Resolve 的 Python 版本兼容（Resolve 18 + 支持 Python 3.9+）
>
> [(486)](https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8)
>
> 。

#### 一键安装脚本

通过批处理（Windows）或 Shell 脚本（macOS）自动化完成依赖安装、文件复制与环境变量配置。例如，Windows 的`install.bat`脚本：



```
@echo off

echo 正在安装Resolve云插件...

:: 1. 复制插件文件到Resolve脚本目录

xcopy /s /i "plugin\_files" "%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Comp"

:: 2. 安装依赖到Resolve模块目录

pip install requests --target "%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"

echo 安装完成！请重启DaVinci Resolve。

pause
```

该脚本会自动复制插件文件到 Resolve 的脚本目录，并安装所需依赖，用户只需双击运行即可[(415)](https://dxt.services:8443/mcp/davinci-resolve-mcp/)。

### 4.2 自动更新机制

#### 方案：GitHub Releases API

通过检查 GitHub Releases 的最新版本，自动下载并替换旧版本插件。核心逻辑为：



1. 脚本启动时，调用 GitHub API 获取最新版本号；

2. 与本地版本号对比，若有更新则提示用户；

3. 下载最新版本的压缩包，自动解压并替换旧文件；

4. 重启 Resolve 完成更新。

> 注：需处理权限问题 ——Windows 需管理员权限才能修改
>
> `ProgramData`
>
> 目录下的文件，macOS 需输入密码才能修改
>
> `/Library`
>
> 目录下的文件。可在安装脚本中添加权限请求逻辑，或引导用户手动授权
>
> [(325)](https://blog.csdn.net/gitblog_00655/article/details/151297844)
>
> 。

### 4.3 商业插件的许可证密钥 / 激活

针对 20 人规模的团队，需实现轻量级、安全的许可证管理。

#### 推荐方案：离线激活（邮箱 + 硬件指纹）

该方案无需部署复杂的许可证服务器，适合小团队使用，核心流程为：



1. 用户安装插件后，插件自动生成硬件指纹（基于 CPU ID、主板 ID 或磁盘 ID，避免单一硬件信息导致的激活失败）；

2. 用户将硬件指纹发送给管理员，管理员生成激活码（基于 RSA 加密，确保激活码无法伪造）；

3. 用户输入激活码，插件验证通过后保存激活状态（存储在`fusion:SetData()`或本地加密文件中）。

> 注：硬件指纹生成需跨平台兼容 ——Windows 可通过
>
> `wmic cpu get ProcessorId`
>
> 获取 CPU ID，macOS 可通过
>
> `sysctl -n machdep.cpu.brand_string`
>
> 获取 CPU 信息。需避免使用会随硬件变更的信息（如 IP 地址）
>
> [(319)](https://blog.productlogz.com/faq)
>
> 。

#### 备选方案：在线激活（Blackmagic Cloud ID）

使用 Blackmagic 官方的 Cloud ID 进行激活，用户只需登录自己的 Blackmagic 账户即可激活插件，无需额外生成激活码。但该方案需要用户联网，且需依赖 Blackmagic 的云服务，适合需要频繁切换设备的用户[(322)](https://www.coremicro.com/blogs/news/rent-davinci-resolve-studio-blackmagic-cloud)。

### 4.4 Reactor 分发

Reactor 是 Resolve 社区最流行的插件包管理器，支持一键安装、更新与管理插件，适合开源或免费插件的分发。

#### 分发步骤



1. 遵循 Reactor 的包结构规范：



```
ReactorPackage/

├── .atom（包描述文件，包含包名、版本、作者、依赖等信息）

├── Scripts/（插件脚本文件）

└── README.md（插件说明文档）
```



1. 将包提交到 Reactor 的 GitHub 仓库（[https://github.com/WeSuckLess/Reactor](https://github.com/WeSuckLess/Reactor)）；

2. 等待审核通过后，用户即可在 Reactor 中搜索并安装插件。

> 注：Reactor 主要支持 Fusion 插件，但也兼容 Resolve 脚本。需确保包结构符合 Reactor 的要求，否则审核会失败
>
> [(333)](https://www.techadron.com/blog/details/reactor-3-il-plugin-gratuito-per-davinci-resolve-fusion/14)
>
> 。



***

## 5. Resolve 脚本的单元测试与 CI

### 5.1 模拟 DaVinciResolveScript 对象

Resolve 的 Python API 必须在 Resolve 运行时才能调用，无法直接在常规 Python 环境中测试。需通过模拟对象实现单元测试。

#### 方案 1：手动模拟（无额外依赖）

使用 Python 标准库的`unittest.mock`模块，手动模拟`DaVinciResolveScript`对象及其方法。例如，模拟`resolve.GetProjectManager()`方法：



```
from unittest.mock import Mock, patch

import DaVinciResolveScript as dvr

def test\_get\_current\_project():

&#x20;   \# 模拟Resolve对象

&#x20;   mock\_resolve = Mock()

&#x20;   mock\_project\_manager = Mock()

&#x20;   mock\_project = Mock()

&#x20;   mock\_project.GetName.return\_value = "Test Project"

&#x20;  &#x20;

&#x20;   mock\_project\_manager.GetCurrentProject.return\_value = mock\_project

&#x20;   mock\_resolve.GetProjectManager.return\_value = mock\_project\_manager

&#x20;  &#x20;

&#x20;   \# 替换实际的resolve对象

&#x20;   with patch('dvr.scriptapp', return\_value=mock\_resolve):

&#x20;       resolve = dvr.scriptapp("Resolve")

&#x20;       project\_manager = resolve.GetProjectManager()

&#x20;       current\_project = project\_manager.GetCurrentProject()

&#x20;      &#x20;

&#x20;       assert current\_project.GetName() == "Test Project"

&#x20;       mock\_project\_manager.GetCurrentProject.assert\_called\_once()
```

该方案无需额外依赖，灵活性高，但需手动编写大量模拟代码，适合小型项目或简单功能的测试[(482)](https://blog.csdn.net/2501_93893367/article/details/153978262)。

#### 方案 2：类型存根（类型提示）

使用`fusionscript-stubs`（PyPI 包）提供 Resolve API 的类型提示与存根，方便在 IDE 中编写测试代码，但无法直接运行测试。需配合`unittest.mock`使用，才能实现完整的单元测试[(480)](https://pypi.org/project/fusionscript-stubs/)。

### 5.2 自动化测试的 CI 策略

#### GitHub Actions 配置

GitHub Actions 支持在云端运行 Resolve 测试，但需注意以下限制：



* 仅支持 Linux（Ubuntu）与 Windows runners，macOS runners 无 GPU 支持，无法运行 Resolve；

* 需安装 Resolve Studio 并激活（需将激活码存储为 GitHub Secrets，避免泄露）；

* 测试需在无 GUI 环境下运行（添加`-nogui`参数启动 Resolve）。

以下是 GitHub Actions 的核心配置示例（`.github/workflows/test.yml`），参考自开源项目 DaVinciRPC[(444)](https://github.com/DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC/actions)：



```
name: Resolve Script Tests

on: \[push, pull\_request]

jobs:

&#x20; test:

&#x20;   runs-on: ubuntu-latest

&#x20;   steps:

&#x20;     \- name: Checkout code

&#x20;       uses: actions/checkout@v4

&#x20;     \- name: Install Resolve Studio

&#x20;       run: |

&#x20;         \# 下载Resolve Studio安装包（需替换为官方下载链接）

&#x20;         wget https://download.blackmagicdesign.com/DaVinciResolve/DaVinci\_Resolve\_Studio\_19.1.3\_Linux.run

&#x20;         chmod +x DaVinci\_Resolve\_Studio\_19.1.3\_Linux.run

&#x20;         \# 无GUI安装

&#x20;         ./DaVinci\_Resolve\_Studio\_19.1.3\_Linux.run --nogui --accept-license

&#x20;     \- name: Activate Resolve Studio

&#x20;       run: |

&#x20;         \# 使用GitHub Secrets存储的激活码激活

&#x20;         resolve --activate-key \${{ secrets.RESOLVE\_ACTIVATION\_KEY }} --nogui

&#x20;     \- name: Run tests

&#x20;       run: |

&#x20;         \# 启动Resolve无GUI模式

&#x20;         resolve --nogui &

&#x20;         \# 等待Resolve启动完成

&#x20;         sleep 30

&#x20;         \# 运行单元测试

&#x20;         pytest tests/ -v
```

### 5.3 Docker/VM 设置

为保证测试环境的一致性，建议使用 Docker 容器部署 Resolve。

#### 推荐镜像



* **fat-tire/resolve**：基于 Rocky Linux 8.6（Resolve 官方推荐的 Linux 发行版），预安装 Resolve Studio 与 NVIDIA GPU 驱动，支持 GPU 加速渲染与测试。可通过 Docker Hub 直接拉取：`docker pull fat-tire/resolve:19.1.3`[(493)](https://github.com/fat-tire/resolve)。

* **通用 Linux 容器**：若无需 GPU 加速，可使用 Ubuntu 或 CentOS 容器，但需手动安装 Resolve 与依赖，配置复杂，不推荐用于频繁测试。

#### 容器启动命令



```
docker run -d \\

&#x20; \--name resolve-test \\

&#x20; \--gpus all \  # 传递GPU设备（需安装NVIDIA Container Toolkit）

&#x20; -v \$(pwd)/tests:/root/tests \  # 挂载测试脚本目录

&#x20; fat-tire/resolve:19.1.3 \\

&#x20; resolve --nogui
```

> 注：需安装 NVIDIA Container Toolkit 才能让容器访问 GPU，否则无法运行 GPU 加速的测试任务
>
> [(494)](https://blog.csdn.net/weixin_35370061/article/details/160537256)
>
> 。

### 5.4 日志记录库

Resolve 的 Python 环境对第三方库的支持有限，日志记录需优先选择轻量级、无额外依赖的方案。

#### 推荐方案：标准`logging`模块

Python 标准库的`logging`模块无需额外安装，支持文件日志与控制台日志，可满足大多数场景的需求。以下是核心配置示例，参考自 DEV Community 的教程[(486)](https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8)：



```
import logging

import os

def setup\_logging():

&#x20;   \# 日志文件路径（适配Windows与macOS）

&#x20;   if os.name == 'nt':

&#x20;       log\_path = os.path.join(os.environ\['APPDATA'], 'ResolveCloudPlugin', 'plugin.log')

&#x20;   else:

&#x20;       log\_path = os.path.join(os.path.expanduser('\~'), 'Library', 'Logs', 'ResolveCloudPlugin', 'plugin.log')

&#x20;  &#x20;

&#x20;   \# 创建日志目录（若不存在）

&#x20;   os.makedirs(os.path.dirname(log\_path), exist\_ok=True)

&#x20;  &#x20;

&#x20;   \# 配置日志格式

&#x20;   logging.basicConfig(

&#x20;       filename=log\_path,

&#x20;       level=logging.DEBUG,

&#x20;       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',

&#x20;       datefmt='%Y-%m-%d %H:%M:%S'

&#x20;   )

&#x20;  &#x20;

&#x20;   return logging.getLogger(\_\_name\_\_)

\# 使用示例

logger = setup\_logging()

logger.info("插件启动成功")

logger.error("云API调用失败")
```

该方案的优势是无需额外依赖，适配所有平台，且日志格式清晰，便于排查问题。

#### 备选方案：`loguru`

`loguru`是一个第三方日志库，提供更简洁的 API 与更丰富的功能（如自动日志轮转、彩色输出），但需安装到 Resolve 的模块目录。若需更高级的日志功能，可选择该方案，但需确保与 Resolve 的 Python 版本兼容[(489)](https://developer.aliyun.com/article/1692066)。



***

## 6. 总结

DaVinci Resolve Studio 的 Python API 是功能强大的自动化工具，但受限于单线程 / 进程模型、跨平台差异与有限的文档，开发复杂插件需遵循特定的架构模式与优化策略。本报告覆盖的 5 个维度，每个维度的核心结论与最佳实践如下：



| 维度                   | 核心结论                                                                                 | 最佳实践                                                                           |
| -------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| **实际插件架构模式**         | Resolve Python 环境仅支持线程级并发，子进程无法访问 Resolve 对象；跨会话状态需通过`fusion:SetData()`或 SQLite 存储。  | 采用「本地中间层 + 线程池」实现异步云 API 调用；优先使用`fusion:SetData()`存储轻量状态，复杂状态使用 SQLite。        |
| **外部 API 集成**        | 大文件传输需分块上传，直接利用渲染缓存可节省资源；进度显示可通过控制台或 Fusion UI 实现；后台运行需通过系统服务工具。                     | 分块大小设置为 10-50MB；优先上传渲染缓存文件；Windows 用 NSSM、macOS 用 LaunchDaemon 实现后台运行。         |
| **Apple Silicon 优化** | M4 的 IO 密集型多线程效率比单线程高 3-5 倍；Python API 未开放 Metal 直接调用；16GB 统一内存需限制 Resolve 内存占比≤75%。 | 多线程任务设置`max_workers=4-8`；通过 Resolve 内置功能间接利用 Apple GPU；限制 Resolve 内存占比，优化缓存设置。 |
| **非开发者分发**           | 打包需用 PyInstaller，依赖需安装到 Resolve 专属模块目录；许可证建议用离线激活；Reactor 是社区分发的最佳渠道。                | 用 PyInstaller 打包为单可执行文件；采用「邮箱 + 硬件指纹」离线激活；遵循 Reactor 包结构规范提交插件。                |
| **单元测试与 CI**         | 无官方 Mock 库，需手动模拟 Resolve 对象；CI 需用 GitHub Actions 配合 Resolve 激活码；Docker 容器保证测试环境一致性。  | 用`unittest.mock`手动模拟 Resolve 对象；CI 配置无 GUI 测试；使用`fat-tire/resolve`容器部署测试环境。    |

未来，随着 Resolve 的版本更新，官方可能会开放更多的多进程 / 线程功能与 GPU 调用接口，进一步提升 Python API 的性能与灵活性。开发者应持续关注官方文档的更新，以便及时调整开发策略，充分利用新功能提升插件的性能与用户体验。

**参考资料&#x20;**

\[1] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[2] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio)

\[3] HunyuanVideo-Foley 插件开发:为DaVinci Resolve制作扩展-CSDN博客[ https://blog.csdn.net/weixin\_35835030/article/details/156931756](https://blog.csdn.net/weixin_35835030/article/details/156931756)

\[4] Python异步编程核心模式与高效开发实践解析[ https://www.iesdouyin.com/share/video/7596914291085728064](https://www.iesdouyin.com/share/video/7596914291085728064)

\[5] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[6] HunyuanVideo-Foley插件开发:为DaVinci Resolve打造扩展-CSDN博客[ https://blog.csdn.net/weixin\_42284380/article/details/156885642](https://blog.csdn.net/weixin_42284380/article/details/156885642)

\[7] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[8] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[9] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[10] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[11] Python 中的并发 —— 多进程-CSDN博客[ https://blog.csdn.net/zl811103/article/details/159161056](https://blog.csdn.net/zl811103/article/details/159161056)

\[12] Python3.14去除全局锁后性能下降原因分析及C[ https://www.iesdouyin.com/share/video/7523581502438903083](https://www.iesdouyin.com/share/video/7523581502438903083)

\[13] 大显存 8K 剪辑软件参数实战:DaVinci Resolve/Pr 参数调试与工业化落地指南(一)\_8k视频剪辑软件-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153050394](https://blog.csdn.net/sinat_41617212/article/details/153050394)

\[14] Python 多任务编程:进程与线程全解-CSDN博客[ https://blog.csdn.net/qq\_38673558/article/details/160437186](https://blog.csdn.net/qq_38673558/article/details/160437186)

\[15] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[16] HunyuanVideo-Foley 插件开发:为DaVinci Resolve制作扩展-CSDN博客[ https://blog.csdn.net/weixin\_35835030/article/details/156931756](https://blog.csdn.net/weixin_35835030/article/details/156931756)

\[17] davinci\_resolve\_matching\_subtitles/Davinci\_UI\_References.txt at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Davinci\_UI\_References.txt](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Davinci_UI_References.txt)

\[18] 油管 热门 镜头 画面 拖 影 效果 模拟 达芬奇 插件 预设 + 达芬奇 节点 Time shift Effect – And rik Lang field # 摄影 # 剪辑 # 视频 剪辑 # 达芬奇 插件 # 达芬奇 教程[ https://www.iesdouyin.com/share/video/7611004030902362531](https://www.iesdouyin.com/share/video/7611004030902362531)

\[19] 【中译】DaVinci Resolve 19.1 CTL README文件 - 哔哩哔哩[ https://www.bilibili.com/opus/1038987515597422594](https://www.bilibili.com/opus/1038987515597422594)

\[20] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[21] Wan2.2-V2影视级嵌入式集成方案(达芬奇Resolve 19.1 API桥接实录):时间线元数据毫秒级同步+ACES色彩空间穿透误差＜0.3% - CSDN文库[ https://wenku.csdn.net/column/q54gtw2hwu](https://wenku.csdn.net/column/q54gtw2hwu)

\[22] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[23] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[24] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[25] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[26] 达芬奇文本布局功能详解：排版、动画与路径应用[ https://www.iesdouyin.com/share/video/7501525175377136911](https://www.iesdouyin.com/share/video/7501525175377136911)

\[27] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[28] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[29] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[30] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[31] DaVinci Resolve API Limitations & Workarounds[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Limitations.md)

\[32] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[33] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[34] Python 并发 编程 # python # 编程 # 程序员[ https://www.iesdouyin.com/share/video/6889731202572471560](https://www.iesdouyin.com/share/video/6889731202572471560)

\[35] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[36] Python最多能开多少个进程?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/9140460](https://ask.csdn.net/questions/9140460)

\[37] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[38] HunyuanVideo-Foley 插件开发:为DaVinci Resolve制作扩展-CSDN博客[ https://blog.csdn.net/weixin\_35835030/article/details/156931756](https://blog.csdn.net/weixin_35835030/article/details/156931756)

\[39] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)

\[40] MainConcept Codec插件for DaVinci Resolve Studio实现高效视频[ https://www.iesdouyin.com/share/video/7417477028854730010](https://www.iesdouyin.com/share/video/7417477028854730010)

\[41] HunyuanVideo-Foley插件开发:为DaVinci Resolve打造扩展-CSDN博客[ https://blog.csdn.net/weixin\_42284380/article/details/156885642](https://blog.csdn.net/weixin_42284380/article/details/156885642)

\[42] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[43] DaVinci Resolve | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/?swcfpc=1](https://www.blackmagicdesign.com/cn/products/davinciresolve/?swcfpc=1)

\[44] DaVinci Resolve MCP Server[ https://glama.fly.dev/mcp/servers/Tooflex/davinci-resolve-mcp?locale=ko-KR](https://glama.fly.dev/mcp/servers/Tooflex/davinci-resolve-mcp?locale=ko-KR)

\[45] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[46] 达芬奇Mac系统导出视频发灰问题的Rec.709-A[ https://www.iesdouyin.com/share/video/7542078291486821658](https://www.iesdouyin.com/share/video/7542078291486821658)

\[47] 达芬奇API实战:用Python脚本自动创建项目并导入素材，搭建你的自动化工作流起点 - CSDN文库[ https://wenku.csdn.net/column/623gkl2upgw](https://wenku.csdn.net/column/623gkl2upgw)

\[48] Scripting API | DaVinci Resolve Wiki[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[49] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[50] DaVinci Resolve AI编辑工具 - 腾讯云[ https://cloud.tencent.com/developer/mcp/server/11461](https://cloud.tencent.com/developer/mcp/server/11461)

\[51] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[52] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[53] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[54] 达芬奇Fusion制作人物起飞特效教程[ https://www.iesdouyin.com/share/video/7542822553954667786](https://www.iesdouyin.com/share/video/7542822553954667786)

\[55] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[56] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[57] Petfactory | DaVinci Resolve - Python[ https://www.petfactory.se/notes/davinci-resolve-python/](https://www.petfactory.se/notes/davinci-resolve-python/)

\[58] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[59] Basic Usage Examples[ https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples](https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples)

\[60] concurrent.futures --- 並列タスク実行[ https://docs.python.org/ja/3.13/library/concurrent.futures.html](https://docs.python.org/ja/3.13/library/concurrent.futures.html)

\[61] concurrent.futures --- 启动并行任务 — Python 3.14.4 文档[ https://docs.python.org/zh-cn/3/library/concurrent.futures.html](https://docs.python.org/zh-cn/3/library/concurrent.futures.html)

\[62] concurrent.futures — Launching parallel tasks[ https://docs.python.org/es/dev/library/concurrent.futures.html](https://docs.python.org/es/dev/library/concurrent.futures.html)

\[63] PYTHON-From-Scratch/31. Advance Python Series-Asynchronous Execution(Parallel Execution) With Thread Using Python.ipynb at main · sehgalnaval/PYTHON-From-Scratch · GitHub[ https://github.com/sehgalnaval/PYTHON-From-Scratch/blob/main/31.%20Advance%20Python%20Series-Asynchronous%20Execution(Parallel%20Execution)%20With%20Thread%20Using%20Python.ipynb](https://github.com/sehgalnaval/PYTHON-From-Scratch/blob/main/31.%20Advance%20Python%20Series-Asynchronous%20Execution\(Parallel%20Execution\)%20With%20Thread%20Using%20Python.ipynb)

\[64] concurrent.futures — 병렬 작업 실행하기[ https://docs.python.org/ko/3.9/library/concurrent.futures.html](https://docs.python.org/ko/3.9/library/concurrent.futures.html)

\[65] 17.4.  concurrent.futures -- 並列タスク実行 ¶[ https://docs.python.org/ja/3.6/library/concurrent.futures.html](https://docs.python.org/ja/3.6/library/concurrent.futures.html)

\[66] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[67] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[68] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[69] Python类成员访问权限控制机制解析[ https://www.iesdouyin.com/share/video/7373894582234303753](https://www.iesdouyin.com/share/video/7373894582234303753)

\[70] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[71] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[72] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/next/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/next/intro)

\[73] DaVinci Resolve 自動化ナレッジベース[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API\_Reference.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/API_Reference.md)

\[74] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[75] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[76] 达芬奇 剪辑 面板 自带 的 Fusion 特效 挨个 做 个 介绍 新手 剪辑 别 浪费 ！ 达芬奇 自带 Fusion 特效 保姆 级 速 览 ✅ # 达芬奇 # 达芬奇 fusion # 达芬奇 剪辑[ https://www.iesdouyin.com/share/video/7620445839030717349](https://www.iesdouyin.com/share/video/7620445839030717349)

\[77] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[78] Pythonスクリプトを使って DaVinci Resolve の Fusion ページでアニメーションの制御を行う[ https://trev16.hatenablog.com/entry/2025/02/15/154707](https://trev16.hatenablog.com/entry/2025/02/15/154707)

\[79] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[80] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[81] davinci-resolve-automation/Docs/Troubleshooting.md at main · nobphotographr/davinci-resolve-automation · GitHub[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Troubleshooting.md)

\[82] Python return语句的作用与应用解析[ https://www.iesdouyin.com/share/video/7481150077164129572](https://www.iesdouyin.com/share/video/7481150077164129572)

\[83] DavinciResolve無償版 スクリプト実行時にResolveオブジェクトがNoneを返してくるとき[ https://qiita.com/taisatol/items/7569b4f2c6125ab948b8](https://qiita.com/taisatol/items/7569b4f2c6125ab948b8)

\[84] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[85] python写一个多线程请求接口实现-腾讯云开发者社区-腾讯云[ https://cloud.tencent.com.cn/developer/article/2585475](https://cloud.tencent.com.cn/developer/article/2585475)

\[86] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[87] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[88] resolve-assistant 0.1.5[ https://pypi.org/project/resolve-assistant/](https://pypi.org/project/resolve-assistant/)

\[89] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[90] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[91] Basic Usage Examples[ https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples](https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples)

\[92] GitHub - aagedal/resolve\_python\_export\_ftp: DaVinci Resolve python script to render and upload file to an FTP-server. · GitHub[ https://github.com/aagedal/resolve\_python\_export\_ftp](https://github.com/aagedal/resolve_python_export_ftp)

\[93] python如何在gui显示进度[ https://docs.pingcode.com/insights/lm5qrjrfsiqu4f4s3p54wect](https://docs.pingcode.com/insights/lm5qrjrfsiqu4f4s3p54wect)

\[94] 分别 用 go 和 python 实现 进度 条 效果 # python # go 语言 # golang[ https://www.iesdouyin.com/share/video/7612197455584627987](https://www.iesdouyin.com/share/video/7612197455584627987)

\[95] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[96] python 如何显示进度 – PingCode[ https://docs.pingcode.com/ask/ask-ask/936313.html](https://docs.pingcode.com/ask/ask-ask/936313.html)

\[97] 为用户增加上传窗口，显示进度 - CSDN文库[ https://wenku.csdn.net/answer/42x63ek2iv](https://wenku.csdn.net/answer/42x63ek2iv)

\[98] python运行时显示进度 - CSDN文库[ https://wenku.csdn.net/answer/6xp3xazbsc](https://wenku.csdn.net/answer/6xp3xazbsc)

\[99] Script API Docs[ https://www.muyanru.com/en/davinci/api/](https://www.muyanru.com/en/davinci/api/)

\[100] 达芬奇软件全功能界面解析与后期制作教程[ https://www.iesdouyin.com/share/video/7506513798867586341](https://www.iesdouyin.com/share/video/7506513798867586341)

\[101] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[102] DaVinci Resolve[ https://wiki.archlinuxcn.org/wiki/DaVinci\_Resolve](https://wiki.archlinuxcn.org/wiki/DaVinci_Resolve)

\[103] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[104] auto-subs/Docs/ResolveDocs.txt at a39e861afbe578f86156286adedcedfb72614f8d · tmoroney/auto-subs · GitHub[ https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt](https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt)

\[105] GitHub - aagedal/resolve\_python\_export\_ftp: DaVinci Resolve python script to render and upload file to an FTP-server. · GitHub[ https://github.com/aagedal/resolve\_python\_export\_ftp](https://github.com/aagedal/resolve_python_export_ftp)

\[106] 大显存 8K 剪辑软件参数实战:DaVinci Resolve/Pr 参数调试与工业化落地指南(一)\_8k视频剪辑软件-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153050394](https://blog.csdn.net/sinat_41617212/article/details/153050394)

\[107] 达芬奇预览优化技巧：代理媒体与渲染缓存设置解析[ https://www.iesdouyin.com/share/video/7511344843562421545](https://www.iesdouyin.com/share/video/7511344843562421545)

\[108] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[109] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[110] PythonでDavinciResolveのタイムラインを自動生成する【無料版・XML】[ https://qiita.com/alysunk/items/33b5b118368ffce4aab7](https://qiita.com/alysunk/items/33b5b118368ffce4aab7)

\[111] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[112] Blackmagic Cloud Store Mini/Max | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/blackmagiccloudstoremini](https://www.blackmagicdesign.com/cn/products/blackmagiccloudstoremini)

\[113] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)

\[114] 达芬奇视频导出设置详解与正确步骤指南[ https://www.iesdouyin.com/share/video/7557305576867368243](https://www.iesdouyin.com/share/video/7557305576867368243)

\[115] python下载视频上传到服务器 - CSDN文库[ https://wenku.csdn.net/answer/2t8z7adkav](https://wenku.csdn.net/answer/2t8z7adkav)

\[116] 达芬奇API实战:用Python脚本自动创建项目并导入素材，搭建你的自动化工作流起点 - CSDN文库[ https://wenku.csdn.net/column/623gkl2upgw](https://wenku.csdn.net/column/623gkl2upgw)

\[117] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[118] DaVinci Resolve[ https://antigravity.codes/mcp/davinci-resolve](https://antigravity.codes/mcp/davinci-resolve)

\[119] DaVinci Resolve AAC Workaround 🎬[ https://github.com/TryCoffee/DaVinci-Resolve-AAC-workaround](https://github.com/TryCoffee/DaVinci-Resolve-AAC-workaround)

\[120] Progress Bar Pack V2[ https://adobe-panel-api.motionarray.com/davinci-resolve-macros/progress-bar-pack-v2-908872/](https://adobe-panel-api.motionarray.com/davinci-resolve-macros/progress-bar-pack-v2-908872/)

\[121] python如何设置进度条[ https://docs.pingcode.com/insights/fguo136w354ueafwp4xmxcx6](https://docs.pingcode.com/insights/fguo136w354ueafwp4xmxcx6)

\[122] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[123] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[124] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[125] Unlocking Dynamic UI Animations in DaVinci Resolve's Fusion Page[ https://ithy.com/article/davinci-resolve-ui-animation-guide-oh49gxld](https://ithy.com/article/davinci-resolve-ui-animation-guide-oh49gxld)

\[126] MediaStorage[ https://www.muyanru.com/en/davinci/api/mediastorage](https://www.muyanru.com/en/davinci/api/mediastorage)

\[127] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[128] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[129] Blackmagic Cloud Store Mini/Max | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/blackmagiccloudstoremini](https://www.blackmagicdesign.com/cn/products/blackmagiccloudstoremini)

\[130] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[131] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[132] ResolveAPI[ https://deepwiki.com/apvlv/davinci-resolve-mcp/3.2-resolveapi](https://deepwiki.com/apvlv/davinci-resolve-mcp/3.2-resolveapi)

\[133] How to: Upload[ https://developer.adobe.com/frameio/guides/How%20To:%20Upload/](https://developer.adobe.com/frameio/guides/How%20To:%20Upload/)

\[134] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[135] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[136] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[137] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[138] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[139] 运行以后结果直接消失了 - CSDN文库[ https://wenku.csdn.net/answer/893135pe5c](https://wenku.csdn.net/answer/893135pe5c)

\[140] Untitled[ http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline\_version\_manager.lua](http://raw.githubusercontent.com/wotography/DVR-timeline-version-manager/main/timeline_version_manager.lua)

\[141] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[142] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[143] Ability to add custom directory path inputs to cache/proxies/gallery stills/powergrades/captures #39[ https://github.com/pedrolabonia/pydavinci/issues/39](https://github.com/pedrolabonia/pydavinci/issues/39)

\[144] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[145] Rendering and Grading (Python)[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.3-rendering-and-grading-(python)](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.3-rendering-and-grading-\(python\))

\[146] DaVinci\_Resolve\_API\_Docs/scripting\_API/v18/scripting\_API-v18.md at main · leoweyr/DaVinci\_Resolve\_API\_Docs · GitHub[ https://github.com/leoweyr/DaVinci\_Resolve\_API\_Docs/blob/main/scripting\_API/v18/scripting\_API-v18.md?plain=1](https://github.com/leoweyr/DaVinci_Resolve_API_Docs/blob/main/scripting_API/v18/scripting_API-v18.md?plain=1)

\[147] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[148] Step printing.py[ https://www.mycompiler.io/view/FrRiYBdQgLZ](https://www.mycompiler.io/view/FrRiYBdQgLZ)

\[149] Unlocking Dynamic UI Animations in DaVinci Resolve's Fusion Page[ https://ithy.com/article/davinci-resolve-ui-animation-guide-oh49gxld](https://ithy.com/article/davinci-resolve-ui-animation-guide-oh49gxld)

\[150] Animated Progress Bar for DaVinci Resolve[ https://store.sualvi.com/en-usd/products/animated-progress-bar-for-da-vinci-resolve](https://store.sualvi.com/en-usd/products/animated-progress-bar-for-da-vinci-resolve)

\[151] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[152] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[153] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[154] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[155] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[156] DaVinci Resolve – Fusion | Blackmagic Design[ http://www.blackmagicdesign.com/ca/products/davinciresolve/fusion](http://www.blackmagicdesign.com/ca/products/davinciresolve/fusion)

\[157] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[158] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[159] resolve-assistant 0.1.5[ https://pypi.org/project/resolve-assistant/](https://pypi.org/project/resolve-assistant/)

\[160] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[161] \[python] 파이썬에서 큰 파일을 읽는 게으른 방법?[ http://daplus.net/python-%ED%8C%8C%EC%9D%B4%EC%8D%AC%EC%97%90%EC%84%9C-%ED%81%B0-%ED%8C%8C%EC%9D%BC%EC%9D%84-%EC%9D%BD%EB%8A%94-%EA%B2%8C%EC%9C%BC%EB%A5%B8-%EB%B0%A9%EB%B2%95/](http://daplus.net/python-%ED%8C%8C%EC%9D%B4%EC%8D%AC%EC%97%90%EC%84%9C-%ED%81%B0-%ED%8C%8C%EC%9D%BC%EC%9D%84-%EC%9D%BD%EB%8A%94-%EA%B2%8C%EC%9C%BC%EB%A5%B8-%EB%B0%A9%EB%B2%95/)

\[162] 如何在Python中高效地读写大型文件?-腾讯云开发者社区-腾讯云[ https://cloud.tencent.com.cn/developer/article/2490334](https://cloud.tencent.com.cn/developer/article/2490334)

\[163] PythonでDavinciResolveのタイムラインを自動生成する【無料版・XML】[ https://qiita.com/alysunk/items/33b5b118368ffce4aab7](https://qiita.com/alysunk/items/33b5b118368ffce4aab7)

\[164] Using Chunks[ http://realpython.org/lessons/using-chunks/](http://realpython.org/lessons/using-chunks/)

\[165] Ability to add custom directory path inputs to cache/proxies/gallery stills/powergrades/captures #39[ https://github.com/pedrolabonia/pydavinci/issues/39](https://github.com/pedrolabonia/pydavinci/issues/39)

\[166] Project settings[ https://pedrolabonia.github.io/pydavinci/settings/project/](https://pedrolabonia.github.io/pydavinci/settings/project/)

\[167] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[168] How to Render Cache in DaVinci Resolve?[ https://tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOop2ClGpV\_Q6WXD-f9Iy7twGD6BNtHM53QEUhQrmH1bPKLaoAoZA](https://tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOop2ClGpV_Q6WXD-f9Iy7twGD6BNtHM53QEUhQrmH1bPKLaoAoZA)

\[169] macOS硬盘垃圾临时文件清理教程\_final cut backups目录-CSDN博客[ https://blog.csdn.net/weixin\_40078683/article/details/147292094](https://blog.csdn.net/weixin_40078683/article/details/147292094)

\[170] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[171] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[172] DaVinci Resolve Render Cache - einfach & übersichtlich erklärt[ https://lightingandthunder.com/blog/davinci-resolve-render-cache---einfach-ubersichtlich-erklart](https://lightingandthunder.com/blog/davinci-resolve-render-cache---einfach-ubersichtlich-erklart)

\[173] DaVinci Resolve MCP Server[ https://glama.ai/mcp/servers/@hnethery/davinci-resolve-mcp](https://glama.ai/mcp/servers/@hnethery/davinci-resolve-mcp)

\[174] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[175] DaVinci Resolve MCP server[ https://playbooks.com/mcp/samuel-gursky-davinci-resolve](https://playbooks.com/mcp/samuel-gursky-davinci-resolve)

\[176] How scripting in DaVinci Resolve actually saves hours of work[ https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques](https://www.toxigon.com/advanced-davinci-resolve-scripting-techniques)

\[177] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[178] Rendering and Grading (Python)[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.3-rendering-and-grading-(python)](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.3-rendering-and-grading-\(python\))

\[179] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[180] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[181] Resumable and large files (tus)[ https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/](https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/)

\[182] 大文件切片上传时切片数量的考量因素\_文件切片大小计算-CSDN博客[ https://blog.csdn.net/qq\_40576344/article/details/156146703](https://blog.csdn.net/qq_40576344/article/details/156146703)

\[183] Multipart Upload[ https://docs.ignite.video/api-reference/videos/upload/multipart](https://docs.ignite.video/api-reference/videos/upload/multipart)

\[184] cloud-projects/aws/optimizing-large-file-uploads/optimizing-large-file-uploads.md at main · mzazon/cloud-projects · GitHub[ https://github.com/mzazon/cloud-projects/blob/main/aws/optimizing-large-file-uploads/optimizing-large-file-uploads.md](https://github.com/mzazon/cloud-projects/blob/main/aws/optimizing-large-file-uploads/optimizing-large-file-uploads.md)

\[185] How to Upload Files via Cloud Video Kit API[ https://docs.videokit.cloud/developers/guides/upload-file-via-api/](https://docs.videokit.cloud/developers/guides/upload-file-via-api/)

\[186] chunked-uploader-sdk[ https://www.npmjs.com/package/chunked-uploader-sdk](https://www.npmjs.com/package/chunked-uploader-sdk)

\[187] Upload Queue System[ https://github.com/nlvcodes/payload-storage-cloudinary/blob/main/docs/upload-queue.md](https://github.com/nlvcodes/payload-storage-cloudinary/blob/main/docs/upload-queue.md)

\[188] Progressive video upload[ https://docs.api.video/vod/progressive-upload](https://docs.api.video/vod/progressive-upload)

\[189] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[190] NSSM 完全指南:如何将任意程序部署为 Windows 服务-CSDN博客[ https://blog.csdn.net/weixin\_46146718/article/details/147744917](https://blog.csdn.net/weixin_46146718/article/details/147744917)

\[191] GitHub - oxylabs/python-script-service-guide: A guide on running a Python script as a service on Windows & Linux. · GitHub[ https://github.com/oxylabs/python-script-service-guide](https://github.com/oxylabs/python-script-service-guide)

\[192] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[193] xixilys/davinci\_resolve\_driver[ https://github.com/xixilys/davinci\_resolve\_driver](https://github.com/xixilys/davinci_resolve_driver)

\[194] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[195] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[196] \[Davinci17]GUIの作成 With Fusion’s UI Manager[ https://smartanimation.xyz/davincibuilding-gui/](https://smartanimation.xyz/davincibuilding-gui/)

\[197] resolve-batch-exporter/Batch\_Exporter\_chs.py at main · laciechang/resolve-batch-exporter · GitHub[ https://github.com/laciechang/resolve-batch-exporter/blob/main/Batch\_Exporter\_chs.py](https://github.com/laciechang/resolve-batch-exporter/blob/main/Batch_Exporter_chs.py)

\[198] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[199] Python进度条动画演示脚本-CSDN博客[ https://blog.csdn.net/a11111a1111a/article/details/148357139](https://blog.csdn.net/a11111a1111a/article/details/148357139)

\[200] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[201] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[202] Ability to add custom directory path inputs to cache/proxies/gallery stills/powergrades/captures #39[ https://github.com/pedrolabonia/pydavinci/issues/39](https://github.com/pedrolabonia/pydavinci/issues/39)

\[203] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[204] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[205] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[206] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[207] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[208] DaVinci Resolve CLEAR Cache (Find, Delete & Save Space!)[ https://beginnersapproach.com/davinci-resolve-delete-render-cache](https://beginnersapproach.com/davinci-resolve-delete-render-cache)

\[209] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)

\[210] GPUなどによる処理対応とOSの関係[ https://asteriscus.jp/davinci-resolve/2266](https://asteriscus.jp/davinci-resolve/2266)

\[211] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[212] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[213] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[214] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[215] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[216] Windows用户实测M4 Mac Mini：视频剪辑性能与游戏兼容性深度[ https://www.iesdouyin.com/share/video/7491503145013529865](https://www.iesdouyin.com/share/video/7491503145013529865)

\[217] Base Model M4 Mac Mini: Is 16GB RAM Enough? - Geeky Gadgets[ https://www.geeky-gadgets.com/base-model-m4-mac-mini-is-16gb-ram-enough/](https://www.geeky-gadgets.com/base-model-m4-mac-mini-is-16gb-ram-enough/)

\[218] DaVinci Resolve System Preferences – Performance Settings[ https://o-sidemedia.com/davinci-resolve-system-preferences-performance-settings/](https://o-sidemedia.com/davinci-resolve-system-preferences-performance-settings/)

\[219] DaVinci Resolve 映像編集PC メモリ容量はどこまで必要か？[ https://pctier.com/creators-pc-k1020495/](https://pctier.com/creators-pc-k1020495/)

\[220] 大显存硬件实战系列二:8K调色与特效合成的性能突破指南\_达芬奇如何设置省显存-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153473223](https://blog.csdn.net/sinat_41617212/article/details/153473223)

\[221] 硬核干货!达芬奇软件之偏好设置\_标签\_视频\_勾选[ https://www.sohu.com/a/759562251\_121124372](https://www.sohu.com/a/759562251_121124372)

\[222] DaVinci Resolve – 技术规格 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/techspecs](https://www.blackmagicdesign.com/cn/products/davinciresolve/techspecs)

\[223] Apple配备 M4 Max 的 MacBook Pro 16 是最适合视频剪辑的笔记本电脑 - Notebookcheck-cn.com News[ https://www.notebookcheck-cn.com/Apple-M4-Max-MacBook-Pro-16.933962.0.html](https://www.notebookcheck-cn.com/Apple-M4-Max-MacBook-Pro-16.933962.0.html)

\[224] >The Mac mini M4 performance is around 4-5x in DaVinci Resolve for me - compared...[ https://news.ycombinator.com/item?id=42120859](https://news.ycombinator.com/item?id=42120859)

\[225] PugetBench Results[ https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538](https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538)

\[226] PugetBench List[ https://benchmarks.pugetsystems.com/benchmarks/?age=30\&benchmark=\&application=resolve\&specs=](https://benchmarks.pugetsystems.com/benchmarks/?age=30\&benchmark=\&application=resolve\&specs=)

\[227] PugetBench Results[ https://benchmarks.pugetsystems.com/benchmarks/view.php?id=208245](https://benchmarks.pugetsystems.com/benchmarks/view.php?id=208245)

\[228] Benchmark Result[ https://benchmarks.pugetsystems.com/benchmarks/view.php?id=231956](https://benchmarks.pugetsystems.com/benchmarks/view.php?id=231956)

\[229] Puget Bench for DaVinci Resolve[ https://www.pugetsystems.com/pugetbench/creators/davinci-resolve/](https://www.pugetsystems.com/pugetbench/creators/davinci-resolve/)

\[230] DaVinci Resolve – Studio | Blackmagic Design[ https://www.blackmagicdesign.com/products/davinciresolve/studio](https://www.blackmagicdesign.com/products/davinciresolve/studio)

\[231] Python多线程与多进程性能对比:从原理到实战的深度解析\_python线程与进程的性能差异有哪些?-CSDN博客[ https://blog.csdn.net/2508\_92671967/article/details/150955546](https://blog.csdn.net/2508_92671967/article/details/150955546)

\[232] 用RTX4090显卡剪辑4K视频是一种什么体验-CSDN博客[ https://blog.csdn.net/weixin\_42613360/article/details/152056703](https://blog.csdn.net/weixin_42613360/article/details/152056703)

\[233] Python 进阶 教学 ： 协程 函数 与 多 线程 技术 （ 下篇 ） # Python # 编程 # 学习 # 多 线程 # 教学[ https://www.iesdouyin.com/share/video/7602238773729162074](https://www.iesdouyin.com/share/video/7602238773729162074)

\[234] Python 多线程 / 多进程 / 异步 IO 选型指南:高并发场景下的 8 组性能实测-CSDN博客[ https://blog.csdn.net/qq\_34252622/article/details/157729092](https://blog.csdn.net/qq_34252622/article/details/157729092)

\[235] 别再乱用 Python 多线程了\_程序员潘子[ http://m.toutiao.com/group/7594504919923655218/](http://m.toutiao.com/group/7594504919923655218/)

\[236] DaVinci Resolve – Studio版 | Blackmagic Design[ https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek](https://www.blackmagicdesign.com/cn/products/davinciresolve/studio?ref=renaissance-geek)

\[237] Performance Tests: DaVinci Resolve 19.1[ https://dev.larryjordan.com/articles/performance-test-davinci-resolve-19-1/](https://dev.larryjordan.com/articles/performance-test-davinci-resolve-19-1/)

\[238] PugetBench Results[ https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538](https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538)

\[239] Lawrence Systems Davinci Resolve Results[ https://forum.level1techs.com/t/lawrence-systems-davinci-resolve-results/240394](https://forum.level1techs.com/t/lawrence-systems-davinci-resolve-results/240394)

\[240] Apple M4 (10-CPU) vs Intel Core i5-14400 - Benchmark, comparison and differences[ https://www.cpu-monkey.com/en/compare\_cpu-apple\_m4\_10\_cpu-vs-intel\_core\_i5\_14400](https://www.cpu-monkey.com/en/compare_cpu-apple_m4_10_cpu-vs-intel_core_i5_14400)

\[241] 大显存硬件实战系列二:8K调色与特效合成的性能突破指南\_达芬奇如何设置省显存-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153473223](https://blog.csdn.net/sinat_41617212/article/details/153473223)

\[242] 大显存硬件实战:应对8K剪辑、AI训练的高效秘籍\_py8k-CSDN博客[ https://blog.csdn.net/m0\_68113040/article/details/152115899](https://blog.csdn.net/m0_68113040/article/details/152115899)

\[243] 大显存硬件实战系列一:8K剪辑从卡顿到流畅的全栈优化指南\_xavc s-i 硬件解码-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153471445](https://blog.csdn.net/sinat_41617212/article/details/153471445)

\[244] 达芬奇调色低配电脑优化设置技巧[ https://www.iesdouyin.com/share/video/7524916655835925820](https://www.iesdouyin.com/share/video/7524916655835925820)

\[245] 大显存 8K 剪辑软件参数实战:DaVinci Resolve/Pr 参数调试与工业化落地指南(一)\_8k视频剪辑软件-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153050394](https://blog.csdn.net/sinat_41617212/article/details/153050394)

\[246] 如何调整使python运行内存 | PingCode智库[ https://docs.pingcode.com/baike/897931](https://docs.pingcode.com/baike/897931)

\[247] Python内存优化:从内存泄漏到瘦身50%，6种实战策略指南-腾讯云开发者社区-腾讯云[ https://cloud.tencent.com/developer/article/2661345?frompage=seopage](https://cloud.tencent.com/developer/article/2661345?frompage=seopage)

\[248] Python内存优化7大技巧:普通人也能做到，内存直接省75%\_知识大胖[ http://m.toutiao.com/group/7621937584435905024/](http://m.toutiao.com/group/7621937584435905024/)

\[249] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[250] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[251] 【亲测免费】 pydavinci 使用教程-CSDN博客[ https://blog.csdn.net/gitblog\_00772/article/details/141746746](https://blog.csdn.net/gitblog_00772/article/details/141746746)

\[252] 你 需要 这个 免费 Davinci . Resolve 插件[ https://www.iesdouyin.com/share/video/7528442497492667686](https://www.iesdouyin.com/share/video/7528442497492667686)

\[253] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[254] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[255] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[256] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[257] Python的线程池居然会卡住IO?这个坑差点让我加班到凌晨\_qq64e8a4b3748d0的技术博客\_51CTO博客[ https://blog.51cto.com/itchenhan/14550639](https://blog.51cto.com/itchenhan/14550639)

\[258] Python 多线程 / 多进程 / 异步 IO 选型指南:高并发场景下的 8 组性能实测-CSDN博客[ https://blog.csdn.net/qq\_34252622/article/details/157729092](https://blog.csdn.net/qq_34252622/article/details/157729092)

\[259] python 线程 、 进程 、 协程 区别 和 各自 的 应用 场景 # 并发 编程[ https://www.iesdouyin.com/share/video/7562016755661524258](https://www.iesdouyin.com/share/video/7562016755661524258)

\[260] 告别 Python 低效运行!掌握多进程、多线程、协程让程序速度提升 10 倍\_python读写文件 需要cpu性能还是cpu线程数量-CSDN博客[ https://blog.csdn.net/qq\_28372005/article/details/159998834](https://blog.csdn.net/qq_28372005/article/details/159998834)

\[261] Python中的多线程效率分析\_python 多线程 效率测试-CSDN博客[ https://blog.csdn.net/weixin\_43822401/article/details/143502421](https://blog.csdn.net/weixin_43822401/article/details/143502421)

\[262] python脚本如何多线程运行时间[ https://docs.pingcode.com/insights/ymyu7thskzvc93bg4se7rvip](https://docs.pingcode.com/insights/ymyu7thskzvc93bg4se7rvip)

\[263] >The Mac mini M4 performance is around 4-5x in DaVinci Resolve for me - compared...[ https://news.ycombinator.com/item?id=42120859](https://news.ycombinator.com/item?id=42120859)

\[264] Intel Core i7-1360P vs Apple M4 (10-CPU) - Benchmark, comparison and differences[ https://www.cpu-monkey.com/en/compare\_cpu-intel\_core\_i7\_1360p-vs-apple\_m4\_10\_cpu](https://www.cpu-monkey.com/en/compare_cpu-intel_core_i7_1360p-vs-apple_m4_10_cpu)

\[265] M4 raw performance compilation from the article for my future self. Sorted by re...[ https://news.ycombinator.com/item?id=42129995](https://news.ycombinator.com/item?id=42129995)

\[266] GitHub - alexdedyura/cpu-benchmark: CPU benchmark by calculating Pi, powered by Python3 · GitHub[ https://github.com/alexdedyura/cpu-benchmark](https://github.com/alexdedyura/cpu-benchmark)

\[267] Speed Up Python Performance to 100x (& More) with Intel® AI Tools[ https://www.intel.com/content/www/us/en/developer/videos/supercharging-python-performance.html](https://www.intel.com/content/www/us/en/developer/videos/supercharging-python-performance.html)

\[268] Boost Your Python Performance by up to 37x with the Intel Distribution for Python[ https://cdrdv2-public.intel.com/832329/xeon-w-boost-python-performance-solution-brief.pdf](https://cdrdv2-public.intel.com/832329/xeon-w-boost-python-performance-solution-brief.pdf)

\[269] Python的线程池差点让我熬通宵，原来问题出在这\_mb6900529f6798c的技术博客\_51CTO博客[ https://blog.51cto.com/miro/14535765](https://blog.51cto.com/miro/14535765)

\[270] 苹果 最新 款 M4Air , 高温 高 负载 情况 下 能否 流畅 运行 ？ 苹果 最新 款 M4Air ， 室外 高温 暴晒 环境 后台 同时 运行 ！&#x20;

&#x20;配置 ： M4 + 24G + 512G （ 天蓝色 ）&#x20;

&#x20;1 . DaVinci Resolve ： 导入 5 段 8K 30 帧 Pro Res 422 延时 素材 ， 共 14G 。&#x20;

&#x20;2 . Lightroom ： 导出 10[ https://www.iesdouyin.com/share/video/7531621666980400418](https://www.iesdouyin.com/share/video/7531621666980400418)

\[271] PugetBench Results[ https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538](https://benchmarks.pugetsystems.com/benchmarks/view.php?id=261538)

\[272] 8K视频剪辑选CPU，核心数、频率和编解码支持哪个更重要?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/9257666](https://ask.csdn.net/questions/9257666)

\[273] M5剪4K真能早下班?实测告诉你哪些人该冲，哪些人别乱花冤枉钱\_CPU\_什么值得买[ https://post.m.smzdm.com/p/avg8ggw4/](https://post.m.smzdm.com/p/avg8ggw4/)

\[274] 大显存 8K 剪辑软件参数实战:DaVinci Resolve/Pr 参数调试与工业化落地指南(一)\_8k视频剪辑软件-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153050394](https://blog.csdn.net/sinat_41617212/article/details/153050394)

\[275] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[276] 显存容量共享系统内存 可以部署深度学习 显存共享系统内存设置\_mob64ca1414098d的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16213699/8041651](https://blog.51cto.com/u_16213699/8041651)

\[277] 别 再 浪费 你 的 高性能 电脑 ！ 达芬奇 用户 定义 缓存 的 正确 用法 # 达芬奇 # 曲 多多 # 音乐 素材 # AI 相似 音乐[ https://www.iesdouyin.com/share/video/7612897666468531482](https://www.iesdouyin.com/share/video/7612897666468531482)

\[278] DaVinci Resolve System Preferences – Performance Settings[ https://o-sidemedia.com/davinci-resolve-system-preferences-performance-settings/](https://o-sidemedia.com/davinci-resolve-system-preferences-performance-settings/)

\[279] 大显存硬件实战系列二:8K调色与特效合成的性能突破指南\_达芬奇如何设置省显存-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153473223](https://blog.csdn.net/sinat_41617212/article/details/153473223)

\[280] How to Render Cache in DaVinci Resolve?[ https://www.tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOopzfvUcH4Q4Spdo0aTOOV5dZc9BWHemJysr0xZcy5PsEBt7RUz5](https://www.tourboxtech.com/en/news/davinci-resolve-render-cache.html?srsltid=AfmBOopzfvUcH4Q4Spdo0aTOOV5dZc9BWHemJysr0xZcy5PsEBt7RUz5)

\[281] DaVinci Resolve macOS 数据库迁移专业指南\_达芬奇数据库-CSDN博客[ https://blog.csdn.net/weixin\_40078683/article/details/147344569](https://blog.csdn.net/weixin_40078683/article/details/147344569)

\[282] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[283] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[284] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[285] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[286] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[287] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[288] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[289] Pythonスクリプトを使って DaVinci Resolve の Fusion ページでアニメーションの制御を行う[ https://trev16.hatenablog.com/entry/2025/02/15/154707](https://trev16.hatenablog.com/entry/2025/02/15/154707)

\[290] DaVinci Resolve Scripting API - Documentation[ https://extremraym.com/cloud/resolve-scripting-doc/](https://extremraym.com/cloud/resolve-scripting-doc/)

\[291] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[292] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[293] DaVinci Resolve MCP[ https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp](https://mcpservers.org/servers/github-com-samuelgursky-davinci-resolve-mcp)

\[294] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[295] Basic Resolve API[ https://resolvedevdoc.readthedocs.io/en/latest/API\_basic.html](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)

\[296] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[297] Python API Integration[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration](https://deepwiki.com/deric/DaVinciResolve-API-Docs/3.2.5-python-api-integration)

\[298] M4-methods/ML\_benchmarks.py at master · Mcompetitions/M4-methods · GitHub[ https://github.com/Mcompetitions/M4-methods/blob/master/ML\_benchmarks.py](https://github.com/Mcompetitions/M4-methods/blob/master/ML_benchmarks.py)

\[299] \[M4-Python] Issue 14: Implement Memory and Performance Tests #310[ https://github.com/pmcfadin/cqlite/issues/310](https://github.com/pmcfadin/cqlite/issues/310)

\[300] Keras on Mac (M4) is giving inconsistent results compared to running on NVIDIA GPUs[ https://developer.apple.com/forums/thread/778640](https://developer.apple.com/forums/thread/778640)

\[301] GitHub - alexdedyura/cpu-benchmark: CPU benchmark by calculating Pi, powered by Python3 · GitHub[ https://github.com/alexdedyura/cpu-benchmark](https://github.com/alexdedyura/cpu-benchmark)

\[302] M4 Pro Benchmark Suite - Deliverables Summary[ https://github.com/subtract0/AgencyOS/blob/main/BENCHMARK\_DELIVERABLES\_SUMMARY.md](https://github.com/subtract0/AgencyOS/blob/main/BENCHMARK_DELIVERABLES_SUMMARY.md)

\[303] Journal Comparatif : 6 LLMs locaux face à un exercice Python simple[ https://linuxfr.org/users/jobpilot/journaux/comparatif-6-llms-locaux-face-a-un-exercice-python-simple](https://linuxfr.org/users/jobpilot/journaux/comparatif-6-llms-locaux-face-a-un-exercice-python-simple)

\[304] Feature Request: Add Option to Enable Metal Backend in macOS OFX Plugin #33[ https://github.com/gyroflow/gyroflow-plugins/issues/33](https://github.com/gyroflow/gyroflow-plugins/issues/33)

\[305] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[306] DaVinci Resolve – Studio | Blackmagic Design[ https://www.blackmagicdesign.com/pt/products/davinciresolve/studio](https://www.blackmagicdesign.com/pt/products/davinciresolve/studio)

\[307] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[308] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[309] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[310] 大显存硬件实战系列二:8K调色与特效合成的性能突破指南\_达芬奇如何设置省显存-CSDN博客[ https://blog.csdn.net/sinat\_41617212/article/details/153473223](https://blog.csdn.net/sinat_41617212/article/details/153473223)

\[311] PythonでDavinciResolveのタイムラインを自動生成する【無料版・XML】[ https://qiita.com/alysunk/items/33b5b118368ffce4aab7](https://qiita.com/alysunk/items/33b5b118368ffce4aab7)

\[312] GitHub - minghe36/vinci-subtitle-man: 达芬奇剪辑软件AI 自动生成字幕插件 · GitHub[ https://github.com/minghe36/vinci-subtitle-man](https://github.com/minghe36/vinci-subtitle-man)

\[313] HunyuanVideo-Foley 插件开发:为DaVinci Resolve制作扩展-CSDN博客[ https://blog.csdn.net/weixin\_35835030/article/details/156931756](https://blog.csdn.net/weixin_35835030/article/details/156931756)

\[314] 【亲测免费】 pydavinci 使用教程-CSDN博客[ https://blog.csdn.net/gitblog\_00772/article/details/141746746](https://blog.csdn.net/gitblog_00772/article/details/141746746)

\[315] Python智能打包工具：新手友好的多平台发布解决方案[ https://www.iesdouyin.com/share/video/7515002603589537084](https://www.iesdouyin.com/share/video/7515002603589537084)

\[316] 手把手教你用PyInstaller打包Python程序，轻松生成EXE文件-腾讯云开发者社区-腾讯云[ https://cloud.tencent.com/developer/article/2659296?frompage=seopage](https://cloud.tencent.com/developer/article/2659296?frompage=seopage)

\[317] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[318] DaVinci Resolve AI编辑工具 - 腾讯云[ https://cloud.tencent.com/developer/mcp/server/11461](https://cloud.tencent.com/developer/mcp/server/11461)

\[319] Frequently Asked Questions[ https://blog.productlogz.com/faq](https://blog.productlogz.com/faq)

\[320] End User License Agreement – LumiMakr Video[ https://lumimakr.com/end-user-license-agreement/](https://lumimakr.com/end-user-license-agreement/)

\[321] 达芬奇 BCC 插件 汉化 特效 转场 BCC 2025 v18 . 5 # 影视 后期 系统 教学 # BCC 插件 汉化 # 达芬奇 插件[ https://www.iesdouyin.com/share/video/7531399051359554867](https://www.iesdouyin.com/share/video/7531399051359554867)

\[322] Rent DaVinci Resolve Studio Licenses via Blackmagic Cloud: A Flexible Option for Creators[ https://www.coremicro.com/blogs/news/rent-davinci-resolve-studio-blackmagic-cloud](https://www.coremicro.com/blogs/news/rent-davinci-resolve-studio-blackmagic-cloud)

\[323] DaVinci Resolve Activation Key – Info & How To Activate[ https://macmyths.com/davinci-resolve-activation-key-info-how-to-activate/](https://macmyths.com/davinci-resolve-activation-key-info-how-to-activate/)

\[324] Licença DaVinci Resolve Studio – Guia definitivo sobre compra e uso[ https://proclass.com.br/home/2025/05/licenca-davinci-resolve-studio-guia-definitivo-sobre-compra-e-uso/](https://proclass.com.br/home/2025/05/licenca-davinci-resolve-studio-guia-definitivo-sobre-compra-e-uso/)

\[325] DaVinci Resolve插件安装指南:Gyroflow无缝工作流-CSDN博客[ https://blog.csdn.net/gitblog\_00655/article/details/151297844](https://blog.csdn.net/gitblog_00655/article/details/151297844)

\[326] DaVinci Resolve Plugins & Extensions[ https://davinciresolvecentral.com/davinci-resolve-plugins](https://davinciresolvecentral.com/davinci-resolve-plugins)

\[327] How to Update DaVinci Resolve: What You Need to Know[ https://tourboxtech.com/en/news/how-to-update-davinci-resolve.html](https://tourboxtech.com/en/news/how-to-update-davinci-resolve.html)

\[328] 达芬奇 专用 运镜 转场 插件 ， 视频 变速 运镜 转场 必备 V2 版本 # 影视 后期 系统 教学 # 达芬奇 教程 # 达芬奇 插件 # 转场[ https://www.iesdouyin.com/share/video/7522849685019610377](https://www.iesdouyin.com/share/video/7522849685019610377)

\[329] DaVinci Resolve陀螺仪防抖插件终极指南:从安装到精通-CSDN博客[ https://blog.csdn.net/gitblog\_00300/article/details/157240684](https://blog.csdn.net/gitblog_00300/article/details/157240684)

\[330] DaVinci Resolve 18.6 New Featu[ https://documents.blackmagicdesign.com/SupportNotes/DaVinci\_Resolve\_18.6\_New\_Features\_Guide.pdf?\_v=1695106811000#:\~:text=DaVinci%20Resolve%2018.6%20includes%20a,functionality%20of%20the%20Media%20page.\&text=You%20can%20now%20import%20and,files%2C%20just%20like%20normal%20bins.](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_18.6_New_Features_Guide.pdf?_v=1695106811000#:~:text=DaVinci%20Resolve%2018.6%20includes%20a,functionality%20of%20the%20Media%20page.\&text=You%20can%20now%20import%20and,files%2C%20just%20like%20normal%20bins.)

\[331] 2

Dehancer OFX plugin

for DaVi[ https://cdn-files.dehancer.com/c45cc6cb-2c5b-4571-850d-66f5d2a7a98a\_README%21+DaVinci+OFX+SETUP+Linux.pdf](https://cdn-files.dehancer.com/c45cc6cb-2c5b-4571-850d-66f5d2a7a98a_README%21+DaVinci+OFX+SETUP+Linux.pdf)

\[332] 🧩 rupdate.sh[ https://github.com/Ben6219/rupdate/](https://github.com/Ben6219/rupdate/)

\[333] Reactor 3: il plugin gratuito per DaVinci Resolve Fusion[ https://www.techadron.com/blog/details/reactor-3-il-plugin-gratuito-per-davinci-resolve-fusion/14](https://www.techadron.com/blog/details/reactor-3-il-plugin-gratuito-per-davinci-resolve-fusion/14)

\[334] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[335] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[336] 达芬奇Python脚本助力剪辑效率提升[ https://www.iesdouyin.com/share/video/7529857493657259306](https://www.iesdouyin.com/share/video/7529857493657259306)

\[337] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[338] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[339] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/20.1.0/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/20.1.0/intro)

\[340] Python项目打包与部署(四):项目依赖管理\_python项目依赖包管理-CSDN博客[ https://blog.csdn.net/captain5339/article/details/136230363](https://blog.csdn.net/captain5339/article/details/136230363)

\[341] DaVinci Resolve Installation[ https://github.com/ryzendew/Linux-Tips-and-Tricks/wiki/DaVinci-Resolve-Installation/822834f1715e9449dd061cbc06d55afd37ed86b6](https://github.com/ryzendew/Linux-Tips-and-Tricks/wiki/DaVinci-Resolve-Installation/822834f1715e9449dd061cbc06d55afd37ed86b6)

\[342] Mac系统达芬奇外部插件安装步骤与方法解析[ https://www.iesdouyin.com/share/video/7601057017234574601](https://www.iesdouyin.com/share/video/7601057017234574601)

\[343] 【亲测免费】 pydavinci 使用教程-CSDN博客[ https://blog.csdn.net/gitblog\_00772/article/details/141746746](https://blog.csdn.net/gitblog_00772/article/details/141746746)

\[344] Use pip packages in DaVinci Resolve scripts[ https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8](https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8)

\[345] DaVinci Resolve MCP Server[ https://glama.fly.dev/mcp/servers/Tooflex/davinci-resolve-mcp?locale=ko-KR](https://glama.fly.dev/mcp/servers/Tooflex/davinci-resolve-mcp?locale=ko-KR)

\[346] End-User License Agreement (EULA)[ https://www.seedgrade.io/license](https://www.seedgrade.io/license)

\[347] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[348] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[349] 手把手教你用PyInstaller打包Python程序，轻松生成EXE文件-腾讯云开发者社区-腾讯云[ https://cloud.tencent.com/developer/article/2659296?frompage=seopage](https://cloud.tencent.com/developer/article/2659296?frompage=seopage)

\[350] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[351] HunyuanVideo-Foley 插件开发:为DaVinci Resolve制作扩展-CSDN博客[ https://blog.csdn.net/weixin\_35835030/article/details/156931756](https://blog.csdn.net/weixin_35835030/article/details/156931756)

\[352] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[353] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315841](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315841)

\[354] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[355] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[356] Unofficial DaVinci Resolve Scripting Documentation[ https://deric.github.io/DaVinciResolve-API-Docs/](https://deric.github.io/DaVinciResolve-API-Docs/)

\[357] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[358] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[359] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[360] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[361] DaVinci Resolve MCP Server[ https://glama.ai/mcp/servers/@apvlv/davinci-resolve-mcp](https://glama.ai/mcp/servers/@apvlv/davinci-resolve-mcp)

\[362] DaVinci Resolve Random Video Switcher[ https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/README.md](https://github.com/mojonobu/davinci-resolve-random-video-switcher/blob/main/README.md)

\[363] auto-subs/Docs/ResolveDocs.txt at a39e861afbe578f86156286adedcedfb72614f8d · tmoroney/auto-subs · GitHub[ https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt](https://github.com/tmoroney/auto-subs/blob/a39e861a/Docs/ResolveDocs.txt)

\[364] DaVinci Resolve – Studio | Blackmagic Design[ http://www.blackmagicdesign.com/it/products/davinciresolve/studio](http://www.blackmagicdesign.com/it/products/davinciresolve/studio)

\[365] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[366] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[367] 达芬奇Python脚本如何调用Resolve API?\_编程语言-CSDN问答[ https://ask.csdn.net/questions/8964429](https://ask.csdn.net/questions/8964429)

\[368] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[369] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[370] 达芬奇DaVinci Resolve插件合集 for Mac-蒲公英[ https://8023design.com/530.html](https://8023design.com/530.html)

\[371] Codebook Creator[ https://cs.editingtools.io/resolve/codebook/](https://cs.editingtools.io/resolve/codebook/)

\[372] Python script to create GitHub release[ https://gist.github.com/mcguffin/7fbe709a624f672f60c770c080cbc41a](https://gist.github.com/mcguffin/7fbe709a624f672f60c770c080cbc41a)

\[373] Davinci-Resolve-Python-Scripts/Relink Selected to Latest Version.py at main · TuesdayPoetry/Davinci-Resolve-Python-Scripts · GitHub[ https://github.com/TuesdayPoetry/Davinci-Resolve-Python-Scripts/blob/main/Relink%20Selected%20to%20Latest%20Version.py](https://github.com/TuesdayPoetry/Davinci-Resolve-Python-Scripts/blob/main/Relink%20Selected%20to%20Latest%20Version.py)

\[374] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[375] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4289758](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4289758)

\[376] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[377] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[378] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[379] davinci-rest 0.2.5[ https://pypi.org/project/davinci-rest/](https://pypi.org/project/davinci-rest/)

\[380] 【亲测免费】 pydavinci 使用教程-CSDN博客[ https://blog.csdn.net/gitblog\_00772/article/details/141746746](https://blog.csdn.net/gitblog_00772/article/details/141746746)

\[381] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[382] davinci\_resolve\_matching\_subtitles/Matching Subtitles.py at master · StevenBaby/davinci\_resolve\_matching\_subtitles · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/Matching%20Subtitles.py](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/Matching%20Subtitles.py)

\[383] GitHub - jashanmak/Davinci-Resolve-Scripts: Scripts for Davinci Resolve · GitHub[ https://github.com/jashanmak/Davinci-Resolve-Scripts](https://github.com/jashanmak/Davinci-Resolve-Scripts)

\[384] BMD Docs[ https://wheheohu.github.io/bmd\_doc/ResolveAPI/next/intro](https://wheheohu.github.io/bmd_doc/ResolveAPI/next/intro)

\[385] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest](https://github.com/dev-beluck/davinci-rest)

\[386] DRSorter[ https://github.com/a-tak/DRSorter](https://github.com/a-tak/DRSorter)

\[387] GitHub - diop/davinci-resolve-api: Davinci Resolve Python Api Documentation · GitHub[ https://github.com/diop/davinci-resolve-api](https://github.com/diop/davinci-resolve-api)

\[388] Using Spec Files[ https://www.pyinstaller.org/en/v4.4/spec-files.html](https://www.pyinstaller.org/en/v4.4/spec-files.html)

\[389] 【Python从入门到精通】第030篇:Python 应用打包与部署——PyInstaller + Docker 实战-CSDN博客[ https://blog.csdn.net/xyghehehehe/article/details/160078124](https://blog.csdn.net/xyghehehehe/article/details/160078124)

\[390] pyi-makespec[ https://pyinstaller.org/en/latest/man/pyi-makespec.html](https://pyinstaller.org/en/latest/man/pyi-makespec.html)

\[391] pyinstaller[ https://pyinstaller.org/en/stable/man/pyinstaller.html](https://pyinstaller.org/en/stable/man/pyinstaller.html)

\[392] Using PyInstaller[ https://pyinstaller.org/en/latest/usage.html?highlight=--exclude-module](https://pyinstaller.org/en/latest/usage.html?highlight=--exclude-module)

\[393] Using PyInstaller[ https://pyinstaller.org/en/v6.18.0/usage.html](https://pyinstaller.org/en/v6.18.0/usage.html)

\[394] Using PyInstaller[ https://pyinstaller.org/en/v4.4/usage.html](https://pyinstaller.org/en/v4.4/usage.html)

\[395] Using PyInstaller[ https://pyinstaller.org/en/v4.8/usage.html](https://pyinstaller.org/en/v4.8/usage.html)

\[396] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[397] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[398] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[399] python官方文档汉化版\_mob6454cc6bf0b7的技术博客\_51CTO博客[ https://blog.51cto.com/u\_16099239/14307371](https://blog.51cto.com/u_16099239/14307371)

\[400] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[401] DaVinci Resolve API Reference[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference](https://deepwiki.com/deric/DaVinciResolve-API-Docs/2-davinci-resolve-api-reference)

\[402] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[403] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[404] Workflow Integration Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_workflow.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_workflow.html)

\[405] GitHub - jashanmak/Davinci-Resolve-Scripts: Scripts for Davinci Resolve · GitHub[ https://github.com/jashanmak/Davinci-Resolve-Scripts](https://github.com/jashanmak/Davinci-Resolve-Scripts)

\[406] DaVinci Resolve[ https://dxt.services:8443/mcp/davinci-resolve-mcp/](https://dxt.services:8443/mcp/davinci-resolve-mcp/)

\[407] GitHub - AssoDIT/Davinci-Resolve-Stills-Markers: A script that allows you to grab stills from timeline markers and optionally export them to a folder. Converted to python from lua script created by Ro[ https://github.com/AssoDIT/Davinci-Resolve-Stills-Markers](https://github.com/AssoDIT/Davinci-Resolve-Stills-Markers)

\[408] Davinci Resolve Matching Subtitles[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/README.md](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/README.md)

\[409] DaVinci Resolve AI编辑工具 - 腾讯云[ https://cloud.tencent.com/developer/mcp/server/11461](https://cloud.tencent.com/developer/mcp/server/11461)

\[410] Codebook Creator[ https://uk.editingtools.io/resolve/codebook/](https://uk.editingtools.io/resolve/codebook/)

\[411] catdv-resolve 1.3.7[ https://pypi.org/project/catdv-resolve/1.3.7/](https://pypi.org/project/catdv-resolve/1.3.7/)

\[412] CatDVResolve[ https://github.com/Lordfirespeed/CatDVResolve](https://github.com/Lordfirespeed/CatDVResolve)

\[413] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[414] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4699310](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4699310)

\[415] DaVinci Resolve[ https://dxt.services:8443/mcp/davinci-resolve-mcp/](https://dxt.services:8443/mcp/davinci-resolve-mcp/)

\[416] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[417] DaVinci Resolve Automation[ https://github.com/nobphotographr/davinci-resolve-automation](https://github.com/nobphotographr/davinci-resolve-automation)

\[418] GitHub - StevenBaby/davinci\_resolve\_matching\_subtitles: Matching · GitHub[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles](https://github.com/StevenBaby/davinci_resolve_matching_subtitles)

\[419] 【亲测免费】 pydavinci 使用教程-CSDN博客[ https://blog.csdn.net/gitblog\_00772/article/details/141746746](https://blog.csdn.net/gitblog_00772/article/details/141746746)

\[420] GitHub - eric-with-a-c/resolve-otio: An OpenTimelineIO plugin for DaVinci Resolve · GitHub[ https://github.com/eric-with-a-c/resolve-otio](https://github.com/eric-with-a-c/resolve-otio)

\[421] GitHub - AssoDIT/Davinci-Resolve-Stills-Markers: A script that allows you to grab stills from timeline markers and optionally export them to a folder. Converted to python from lua script created by Ro[ https://github.com/AssoDIT/Davinci-Resolve-Stills-Markers](https://github.com/AssoDIT/Davinci-Resolve-Stills-Markers)

\[422] drremote 0.1.0.6[ https://pypi.org/project/drremote/0.1.0.6/](https://pypi.org/project/drremote/0.1.0.6/)

\[423] Davinci Resolve Matching Subtitles[ https://github.com/StevenBaby/davinci\_resolve\_matching\_subtitles/blob/master/README.md](https://github.com/StevenBaby/davinci_resolve_matching_subtitles/blob/master/README.md)

\[424] davinci-resolve-mcp 0.1.1[ https://pypi.org/project/davinci-resolve-mcp/](https://pypi.org/project/davinci-resolve-mcp/)

\[425] DaVinci Resolve[ https://dxt.services/mcp/davinci-resolve-mcp/](https://dxt.services/mcp/davinci-resolve-mcp/)

\[426] 达芬奇脚本 - CSDN文库[ https://wenku.csdn.net/answer/3c7btqspuf](https://wenku.csdn.net/answer/3c7btqspuf)

\[427] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)

\[428] AI Fusion Node Builder for DaVinci Resolve[ https://github.com/neezr/AI-Fusion-Node-Builder-for-DaVinci-Resolve](https://github.com/neezr/AI-Fusion-Node-Builder-for-DaVinci-Resolve)

\[429] Getting Started Tutorial[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting\_Started\_Tutorial.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Tutorials/Getting_Started_Tutorial.md)

\[430] davinci-resolve-api/Examples/3\_grade\_and\_render\_all\_timelines.py at master · diop/davinci-resolve-api · GitHub[ https://github.com/diop/davinci-resolve-api/blob/master/Examples/3\_grade\_and\_render\_all\_timelines.py](https://github.com/diop/davinci-resolve-api/blob/master/Examples/3_grade_and_render_all_timelines.py)

\[431] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[432] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[433] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[434] Type Safety and Modern Python Patterns for DaVinci Resolve[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type\_Safety\_and\_Best\_Practices.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type_Safety_and_Best_Practices.md)

\[435] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)

\[436] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[437] Basic Usage Examples[ https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples](https://deepwiki.com/apvlv/davinci-resolve-mcp/6-basic-usage-examples)

\[438] Use pip packages in DaVinci Resolve scripts[ https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8](https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8)

\[439] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix](https://github.com/facu041294/davinci-resolve-python-encoding-fix)

\[440] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[441] davinci developer 教程 - CSDN文库[ https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507](https://wenku.csdn.net/answer/d7b503ea102a11eea6c2fa163eeb3507)

\[442] Davinci Resolve Scripts[ https://github.com/NerRobDog/Davinci\_Resolve\_Scripts](https://github.com/NerRobDog/Davinci_Resolve_Scripts)

\[443] Advanced Operation Tools[ https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools](https://deepwiki.com/apvlv/davinci-resolve-mcp/5.5-advanced-operation-tools)

\[444] Actions · DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC · GitHub[ https://github.com/DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC/actions](https://github.com/DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC/actions)

\[445] davinci-resolve(-studio): install/fix auxillary applications and udev rules #508039[ https://github.com/NixOS/nixpkgs/pull/508039/checks](https://github.com/NixOS/nixpkgs/pull/508039/checks)

\[446] Update docker/build-push-action action to v7[ https://github.com/elliotmatson/Docker-Davinci-Resolve-Project-Server/pull/162](https://github.com/elliotmatson/Docker-Davinci-Resolve-Project-Server/pull/162)

\[447] CatDVResolve[ https://github.com/Lordfirespeed/CatDVResolve](https://github.com/Lordfirespeed/CatDVResolve)

\[448] GitHub - Polabiel/DaVinciRPC: Discord Rich Presence para DaVinci Resolve usando Python e RPC, exibindo status de edição em tempo real. · GitHub[ https://github.com/Polabiel/DaVinciRPC](https://github.com/Polabiel/DaVinciRPC)

\[449] GitHub - pobthebuilder/resolve-flatpak: Flatpak packaging for Blackmagicdesign DaVinci Resolve · GitHub[ https://github.com/pobthebuilder/resolve-flatpak/](https://github.com/pobthebuilder/resolve-flatpak/)

\[450] DaVinci Resolve[ https://deepwiki.com/ryzendew/AffinityOnLinux/15.1-davinci-resolve](https://deepwiki.com/ryzendew/AffinityOnLinux/15.1-davinci-resolve)

\[451] 在Linux容器中运行DaVinci Resolve:解决非CentOS系统兼容性难题-CSDN博客[ https://blog.csdn.net/weixin\_35370061/article/details/160537256](https://blog.csdn.net/weixin_35370061/article/details/160537256)

\[452] GitHub - fat-tire/resolve: Container scripts to build and run DaVinci Resolve \[Studio] for Linux using Docker or Podman · GitHub[ https://github.com/fat-tire/resolve](https://github.com/fat-tire/resolve)

\[453] resolve/Dockerfile at main · fat-tire/resolve · GitHub[ https://github.com/fat-tire/resolve/blob/main/Dockerfile](https://github.com/fat-tire/resolve/blob/main/Dockerfile)

\[454] DaVinci Resolve Setup Guide[ https://universal-blue.discourse.group/t/davinci-resolve-setup-guide/1197](https://universal-blue.discourse.group/t/davinci-resolve-setup-guide/1197)

\[455] DaVinci Resolve Installation Guide - Distrobox (Rocky Linux)[ https://github.com/tucktuckg00se/resolve-install-guide](https://github.com/tucktuckg00se/resolve-install-guide)

\[456] Davinci Resolve Project Server[ https://github.com/elliotmatson/Docker-Davinci-Resolve-Project-Server/blob/main/README.md](https://github.com/elliotmatson/Docker-Davinci-Resolve-Project-Server/blob/main/README.md)

\[457] Installation[ https://deepwiki.com/zelikos/davincibox/2.1-installation](https://deepwiki.com/zelikos/davincibox/2.1-installation)

\[458] fusionscript-stubs 20.2.2[ https://pypi.org/project/fusionscript-stubs/](https://pypi.org/project/fusionscript-stubs/)

\[459] Unofficial DaVinci Resolve Scripting Documentation[ https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md](https://github.com/deric/DaVinciResolve-API-Docs/blob/main/docs/index.md)

\[460] Scripting API[ https://wiki.dvresolve.com/developer-docs/scripting-api](https://wiki.dvresolve.com/developer-docs/scripting-api)

\[461] 【亲测免费】 推荐使用:pydavinci——DaVinci Resolve的轻量级Python封装-CSDN博客[ https://blog.csdn.net/gitblog\_00474/article/details/141697577](https://blog.csdn.net/gitblog_00474/article/details/141697577)

\[462] pybmd 2026.1.0[ https://pypi.org/project/pybmd/](https://pypi.org/project/pybmd/)

\[463] deric/DaVinciResolve-API-Docs | DeepWiki[ https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview](https://deepwiki.com/deric/DaVinciResolve-API-Docs/1-overview)

\[464] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[465] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[466] Davinci Resolve Scripting APIことはじめ[ https://kiyasu.hatenadiary.com/entry/2026/01/12/150721](https://kiyasu.hatenadiary.com/entry/2026/01/12/150721)

\[467] GitHub - IgorRidanovic/DaVinvciResolve\_API\_Test: This script tests if the DaVinci Resolve Studio V15 scripting API is responsive.[ https://github.com/IgorRidanovic/DaVinvciResolve\_API\_Test](https://github.com/IgorRidanovic/DaVinvciResolve_API_Test)

\[468] Unofficial DaVinci Resolve Scripting Documentation[ https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/](https://electron-rotoscope.github.io/DaVinciResolve-API-Docs/)

\[469] openai-cookbook/examples/Unit\_test\_writing\_using\_a\_multi-step\_prompt.ipynb at main · WeaponSmith/openai-cookbook · GitHub[ https://github.com/WeaponSmith/openai-cookbook/blob/main/examples/Unit\_test\_writing\_using\_a\_multi-step\_prompt.ipynb](https://github.com/WeaponSmith/openai-cookbook/blob/main/examples/Unit_test_writing_using_a_multi-step_prompt.ipynb)

\[470] GitHub Actions自动化测试实践:动作开发与验证流程 - CSDN文库[ https://wenku.csdn.net/doc/4y7xrb922c](https://wenku.csdn.net/doc/4y7xrb922c)

\[471] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[472] @toptal/davinci-workflow[ https://www.npmjs.com/package/@toptal/davinci-workflow](https://www.npmjs.com/package/@toptal/davinci-workflow)

\[473] davinci-resolve(-studio): install/fix auxillary applications and udev rules #508039[ https://github.com/NixOS/nixpkgs/pull/508039/checks](https://github.com/NixOS/nixpkgs/pull/508039/checks)

\[474] Actions · aman7mishra/DaVinci-Resolve-Python-Automation · GitHub[ https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation/actions](https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation/actions)

\[475] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp/](https://github.com/samuelgursky/davinci-resolve-mcp/)

\[476] Actions · DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC · GitHub[ https://github.com/DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC/actions/workflows/github-code-scanning/codeql](https://github.com/DeathScytheCoding/DaVinci-Resolve-Studio-Discord-RPC/actions/workflows/github-code-scanning/codeql)

\[477] X-Raym /DaVinci Resolve Scripting Doc.txt[ https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink\_comment\_id=4315832](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8?permalink_comment_id=4315832)

\[478] GitHub - znznzna/davinci-cli: DaVinci Resolve CLI & MCP server — agent-first design · GitHub[ https://github.com/znznzna/davinci-cli](https://github.com/znznzna/davinci-cli)

\[479] DaVinci Resolve MCP Server[ https://github.com/samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp)

\[480] fusionscript-stubs 20.2.2[ https://pypi.org/project/fusionscript-stubs/](https://pypi.org/project/fusionscript-stubs/)

\[481] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[482] 《Pytest-mock 插件全解析:模拟依赖对象的核心用法与场景》-CSDN博客[ https://blog.csdn.net/2501\_93893367/article/details/153978262](https://blog.csdn.net/2501_93893367/article/details/153978262)

\[483] GitHub - dev-beluck/davinci-rest: A REST API for DaVinci Resolve · GitHub[ https://github.com/dev-beluck/davinci-rest/](https://github.com/dev-beluck/davinci-rest/)

\[484] davinci-resolve-script[ https://diop.github.io/davinci-resolve-api/](https://diop.github.io/davinci-resolve-api/)

\[485] Troubleshooting Guide: DaVinci Resolve 19/20+ Crash on Startup (Fatal Python Error)[ https://github.com/facu041294/davinci-resolve-python-encoding-fix](https://github.com/facu041294/davinci-resolve-python-encoding-fix)

\[486] Use pip packages in DaVinci Resolve scripts[ https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8](https://dev.to/depsir/use-pip-packages-in-davinci-resolve-scripts-42m8)

\[487] drremote 0.1.0.6[ https://pypi.org/project/drremote/0.1.0.6/](https://pypi.org/project/drremote/0.1.0.6/)

\[488] Resolve API Readme[ https://resolvedevdoc.readthedocs.io/en/latest/readme\_resolveapi.html](https://resolvedevdoc.readthedocs.io/en/latest/readme_resolveapi.html)

\[489] Python日志模块(logging)最佳实践:让调试更高效-阿里云开发者社区[ https://developer.aliyun.com/article/1692066](https://developer.aliyun.com/article/1692066)

\[490] Type Safety and Modern Python Patterns for DaVinci Resolve[ https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type\_Safety\_and\_Best\_Practices.md](https://github.com/nobphotographr/davinci-resolve-automation/blob/main/Docs/Type_Safety_and_Best_Practices.md)

\[491] Guía completa de logs en Python: de novato a experto[ https://www.python.digibeatrix.com/es/exceptions-errors/python-logging-output-complete-guide/](https://www.python.digibeatrix.com/es/exceptions-errors/python-logging-output-complete-guide/)

\[492] resolve/Dockerfile at main · fat-tire/resolve · GitHub[ https://github.com/fat-tire/resolve/blob/main/Dockerfile](https://github.com/fat-tire/resolve/blob/main/Dockerfile)

\[493] GitHub - fat-tire/resolve: Container scripts to build and run DaVinci Resolve \[Studio] for Linux using Docker or Podman · GitHub[ https://github.com/fat-tire/resolve](https://github.com/fat-tire/resolve)

\[494] 在Linux容器中运行DaVinci Resolve:解决非CentOS系统兼容性难题-CSDN博客[ https://blog.csdn.net/weixin\_35370061/article/details/160537256](https://blog.csdn.net/weixin_35370061/article/details/160537256)

\[495] Container Images[ https://deepwiki.com/zelikos/davincibox/3.1-container-images](https://deepwiki.com/zelikos/davincibox/3.1-container-images)

\[496] GitHub - AmigaGod/davinci-project-server: DaVinci Resolve Project Server with GUI, PostgreSQL, automated scripts, and full backup/restore support. · GitHub[ https://github.com/AmigaGod/davinci-project-server/](https://github.com/AmigaGod/davinci-project-server/)

\[497] Install DaVinci Resolve in Any Linux Distro Using DavinciBox (2025)[ https://techhut.tv/install-davinci-resolve-linux-ubuntu-arch-fedora-davincibox](https://techhut.tv/install-davinci-resolve-linux-ubuntu-arch-fedora-davincibox)

\[498] Bug: Resolve seemingly uses software rendering for the UI #242[ https://github.com/zelikos/davincibox/issues/242](https://github.com/zelikos/davincibox/issues/242)

> （注：文档部分内容可能由 AI 生成）