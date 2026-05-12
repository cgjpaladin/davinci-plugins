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

`GetClipColor()` 17 种标准色彩对照表 → `davinci-api` skill。
项目使用: `check_core.py → _audio_color_detail()` 判断音频越轨。

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
| nobphotographr/automation `nobphotographr/davinci-resolve-automation` | 3 | 2025-12-31 | 边缘 |
| theia `ming-qiu/theia` | 3 | 2026-05-07 | 边缘 |
| Reactor `WeSuckLess/Reactor` | 1 | **2018** | ❌ 已死 |

### 在线 API 文档

| 资源 | 链接 | 状态 |
|------|------|:--:|
| X-Raym Gist | `gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8` | 未验证 |
| deric 非官方文档 | `deric.github.io/DaVinciResolve-API-Docs/` | 未验证 |

### 本地参考代码（SMB）

| 资源 | 位置 | 状态 |
|------|------|:--:|
| 张来吃 Batch_io_Pro.py | `/Volumes/MYJC/06_Software/达芬奇脚本/批量IO渲染/` | ✅ |
| 批量替换片段 Lua | `/Volumes/MYJC/06_Software/达芬奇脚本/批量替换片段/` | ✅ |
| TTS 语音工具 | `/Volumes/MYJC/06_Software/达芬奇脚本/TTS语音工具/` | ✅ |

### 学习资料（本地 Git）

| 资源 | 位置 |
|------|------|
| AI 调研报告（GPT/MiniMax/豆包/千问） | `AI去字幕/外部调研报告/` (7 份) |
| HEIBA 黑靶插件源码（Lua 明文） | `达芬奇学习资料/HEIBA插件源码/` (4 脚本) |
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
