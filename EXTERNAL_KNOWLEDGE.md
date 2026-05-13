# 外部知识索引

> 这不是文档抄本。这是「我需要查 X → 去哪找」的路标。
> 每当我需要验证任何规则、参数、限制，先翻这个文件。找不到再问裁缝老师。

> 最后验证: 2026-05-12

---

## DaVinci Resolve

### 官方脚本 API

| 资源 | 位置 | 状态 |
|------|------|:--:|
| README（官方 API 文档） | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/README.txt` | ✅ |
| 官方示例（21 个 Python + Lua） | 同上 `Examples/` | ✅ |
| Fusion Fuse 示例（Lua UI 控件展示） | `Developer/Fusion Fuse/` | ✅ |
| Modules（DaVinciResolveScript） | 同上 `Modules/` | ✅ |

### MediaPool 片段色彩

`GetClipColor()` 17 种标准色彩对照表 → `达芬奇API参考` skill。
项目使用: `check_core.py → _audio_color_detail()` 判断音频越轨。

### TimelineItem 属性发现

> 以下属性来自 `GetProperty()` 实测验证（非官方文档明列）。

#### 动态缩放 (`DynamicZoomEase`)

- **值**: 0=关闭/默认, 1=线性, 2=缓入, 3=缓出, 4=缓入缓出
- **盲区**: 开启开关但从未调整缓动 → 值为 0，无法与未开启区分
- **检测**：`it.GetProperty().get("DynamicZoomEase", 0) > 0`
- 验证日期: 2026-05-13

#### 其他 Inspector 属性

| 属性 | 类型 | 含义 |
|------|------|------|
| `ZoomX` / `ZoomY` | float | X/Y 缩放倍数（1.0=无缩放） |
| `ZoomGang` | bool | 等比缩放 |
| `CropLeft/Right/Top/Bottom` | float | 裁剪 |
| `RotationAngle` | float | 旋转角度 |
| `Opacity` | float | 不透明度（0-100） |
| `Pan` / `Tilt` | float | 平移/倾斜 |
| `RetimeProcess` | int | 变速处理模式（3=光流法） |
| `ResizeFilter` | int | 调整大小滤镜 |
| `Scaling` | int | 缩放模式 |
| `MotionEstimation` | int | 运动估计 |
| `FlipX` / `FlipY` | bool | 水平/垂直翻转 |

### 社区

| 资源 | 状态 |
|------|:--:|
| We Suck Less Resolve Scripting `steakunderwater.com/wesuckless/viewforum.php?f=35` | ✅ 活跃 |
| Blackmagic 官方论坛 `forum.blackmagicdesign.com` | ✅ |
| dvresolve.com wiki | ✅ |
| Reddit r/davinciresolve | ❌ API 讨论 < 5% |

### GitHub 开源项目

| 项目 | Stars | 最后更新 | 状态 |
|------|:--:|------|:--:|
| davinci-resolve-mcp `samuelgursky/davinci-resolve-mcp` | 1024 | 2026-05-09 | ⭐ 活跃 |
| X-Raym/DaVinci-Resolve-Scripts | 200+ | 2026-04-16 | ⭐ 活跃（Lua） |
| auto-subs `tmoroney/auto-subs` | 200+ | 2026 | 活跃（CLI） |
| Useful.Resolve `ambustion/Useful.Resolve` | ~30 | 2024 | ⭐ Python UI 脚本 |
| nobphotographr/automation | 3 | 2025-12-31 | 边缘 |
| theia `ming-qiu/theia` | 3 | 2026-05-07 | 边缘 |
| tynidev/davinci-resolve | ~50 | 2025-08 | Lua 脚本集 |
| Reactor `WeSuckLess/Reactor` | 1 | **2018** | ❌ 已死 |

### 社区知识（WSL 论坛）
| 资源 | 链接 | 状态 |
|------|------|:--:|
| Building GUIs With Fusion's UI Manager（18页神帖） | `steakunderwater.com/wesuckless/viewtopic.php?t=1411` | ✅ 活跃 |
| Resolve Scripting Essentials（7页置顶帖） | `steakunderwater.com/wesuckless/viewforum.php?f=46` | ✅ 活跃 |

### 在线 API 文档

| 资源 | 链接 | 状态 |
|------|------|:--:|
| X-Raym Gist | `gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8` | 未验证 |
| deric 非官方文档 | `deric.github.io/DaVinciResolve-API-Docs/` | 未验证 |

### 本地参考代码

| 资源 | 位置 | 状态 |
|------|------|:--:|
| SMB — 批量IO渲染 | `/Volumes/MYJC/06_Software/达芬奇脚本/批量IO渲染/Batch_io_Pro.py` | ✅ |
| SMB — 批量替换片段 | `/Volumes/MYJC/06_Software/达芬奇脚本/批量替换片段/批量替换片段.lua` | ✅ |
| SMB — 导出时间线标记 | `/Volumes/MYJC/06_Software/达芬奇脚本/时间线标记/导出时间线标记.lua` | ✅ |
| SMB — 字幕编辑器 | `/Volumes/MYJC/06_Software/达芬奇脚本/字幕编辑器/` (HEIBA) | ✅ |
| SMB — TTS语音工具 | `/Volumes/MYJC/06_Software/达芬奇脚本/TTS语音工具/` (HEIBA) | ✅ |
| GitHub — ExportCDL.py (Python UI) | `达芬奇学习资料/外部插件参考/Useful-Resolve/` | ✅ |
| GitHub — CDLConform.py (Python UI) | 同上 | ✅ |
| GitHub — GrabStillLabel.py (Python UI) | 同上 | ✅ |

### 学习资料（本地 Git）

| 资源 | 位置 |
|------|------|
| AI 调研报告（GPT/MiniMax/豆包/千问） | `AI去字幕/外部调研报告/` (7 份) |
| HEIBA 黑靶插件源码（Lua 明文） | `达芬奇学习资料/HEIBA插件源码/` (4 脚本) |
| 外部开源插件参考（GitHub 5 仓库） | `达芬奇学习资料/外部插件参考/` |
| BMD 官方示例（21 个 Python+Lua） | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Examples/` |
| 摄影机文件命名规范调研 | `达芬奇学习资料/摄影机文件命名规范调研.md` |
| fukco/media-metadata（Go 源码） | `达芬奇学习资料/media-metadata/` |

---

## API 供应商

### 无痕AI 2.1（当前在用）

| 项目 | 值 |
|------|-----|
| 官方文档 | 飞书 Wiki `suiyu-network.feishu.cn/wiki/WUvXwI5vziT24qkAVdDcxTzLnef` |
| 怎么读 | `lark-cli docs +fetch --doc WUvXwI5vziT24qkAVdDcxTzLnef --as bot` |
| Base URL | `https://api.wuhenai.com/v2/` |
| 代码 | `AI去字幕/adapters/wuhenai_v2.py` |
| 定价 | video_removal_std + sel_area = 1积分/秒 |
| point_to_yuan | 0.0091（¥1000→110000积分，裁缝老师实测 2026-05-05） |
| 余额接口 | `GET /user/me` → `adapter.get_balance()` |
| rect 面积上限 | 480,000 px² |

### 鬼手 GhostCut（备用）

| 项目 | 值 |
|------|-----|
| 官方文档 | 飞书文档 `jollytoday.feishu.cn/docx/U73qdBhWbozFdpx4eTvcIO4gn7e` |
| 怎么读 | `lark-cli docs +fetch --doc U73qdBhWbozFdpx4eTvcIO4gn7e --as bot` |
| API Base | `https://api.zhaoli.com` |
| 代码 | `AI去字幕/adapters/ghostcut.py` |
| 认证 | AppKey + AppSecret → 双重 MD5 签名 |
| 定价（VIP4） | Lite=2点/30秒，Pro=5点/30秒（2026-05-12 豆包翻译） |
| VIP 全表 | `AI去字幕/外部调研报告/豆包：鬼手定价标准.md` |
| point_to_yuan | 0.19（¥189/1000点） |
| 余额接口 | `GET /v-w-c/gateway/ve/point/query` → `adapter.get_balance()` |
| CRF 画质 | 默认 17，可设 15（`ADAPTER_CONFIGS["ghostcut"]["crf"] = 15`） |

### 阿里云 OSS

| 项目 | 值 |
|------|-----|
| 官方文档 | `help.aliyun.com/zh/oss/` |
| REST API 签名 V1 | `help.aliyun.com/zh/oss/developer-reference/signature-v1-authorization` |
| OSS Endpoint | `{bucket}.oss-cn-hangzhou.aliyuncs.com` |

---

## 其他产品线

### 交付自检工具

| 项目 | 值 |
|------|-----|
| 代码 | `交付自检工具/check_core.py` |
| TODO | `交付自检工具/TODO.md` |
| LLM 字幕校对方案 | `交付自检工具/外部调研报告/LLM字幕校对方案设计.md` |
| API 盲区 | 见 TODO.md > API 盲区（黑边/关键帧/Fairlight/轨道颜色等 8 项） |

### AI换口型（调研阶段）

| 调研报告 | 位置 |
|------|------|
| GPT deep research | `AI换口型/外部调研报告/gpt：deep-research-report.md` |
| MiniMax API 调研 | `AI换口型/外部调研报告/minimax：AI视频换口型_Lip-Sync_API调研报告.md` |
| 豆包 中文口型同步 | `AI换口型/外部调研报告/豆包：2026年中文AI口型同步API调研与技术评估报告.md` |
| 豆包 国内直连方案 | `AI换口型/外部调研报告/豆包：国内可直连AI视频换口型（Lip-Sync）API调研与方案对比报告.md` |

### AI语音克隆（调研阶段）

| 调研报告 | 位置 |
|------|------|
| GPT deep research | `AI语音克隆/外部调研报告/gpt：deep-research-report.md` |
| MiniMax API 调研 | `AI语音克隆/外部调研报告/minimax：ai_voice_clone_research_report.md` |
| 豆包 国内方案 | `AI语音克隆/外部调研报告/豆包：国内短剧后期配音场景AI声音克隆方案调研与适配评估报告.md` |

### AI超分辨率（调研阶段）

| 调研报告 | 位置 |
|------|------|
| MiniMax API 调研 | `AI超分辨率/外部调研报告/minimax：video-super-resolution-api-research.md` |
| 豆包 短剧场景 | `AI超分辨率/外部调研报告/豆包：短剧后期场景视频超分辨率API调研与实测报告.md` |

### AI加字幕

> 空目录，未启动。

---

## 基础设施

| 项目 | 值 |
|------|-----|
| SMB 服务器 | `192.168.1.154` `/Volumes/MYJC/` |
| 达芬奇脚本 | `/Volumes/MYJC/06_Software/达芬奇脚本/` |
| PG 协作数据库 | `192.168.1.154` `MYJC_2026_A` `MYJC_2025_A`（当前不可达） |
| 飞书 CLI | `lark-cli` `~/.lark-cli/config.json` `--as bot` |

---

## 余额查询

| 供应商 | 方法 | 位置 |
|------|------|------|
| 无痕AI | `adapter.get_balance()` → `{"balance": int}` | `wuhenai_v2.py` |
| 鬼手 | `adapter.get_balance()` → `pointAssets[].pointBalance` | `ghostcut.py` |
| 阿里云 OSS | `stable_ui.py → refresh_oss_bal()` | `stable_ui.py` |
| 积分→人民币 | `point_to_yuan(pts, provider)` | `pricing.py` |

---

## 使用规则

1. **查规则先翻这个文件** — 找到对应行，按「怎么读」获取最新文档
2. **飞书文档用 lark-cli** — 不要 WebFetch，lark-cli 更快且带认证
3. **不确定的标注「[待验证]」** — 不要拿记忆当权威
4. **新接入供应商** — 第一件事注册进这个表
5. **这个文件也别信** — 标注的时间超过 30 天的条目，验证后再用
