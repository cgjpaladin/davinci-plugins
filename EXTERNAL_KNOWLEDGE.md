# 外部知识索引

> 这不是文档抄本。这是「我需要查 X → 去哪找」的路标。
> 每当我需要验证任何规则、参数、限制，先翻这个文件。找不到再问裁缝老师。

---

## DaVinci Resolve

### 官方脚本 API

| 资源 | 位置 | 怎么读 |
|------|------|--------|
| README（官方 API 文档） | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/README.txt` | 本地文件 |
| CHANGELOG | 同上目录 `CHANGELOG.txt` | 本地文件 |
| 官方示例（11个 Python + Lua） | 同上 `Examples/` | 本地文件 |
| Fusion Fuse 示例（15个 Lua，含 UI 控件展示） | `Developer/Fusion Fuse/` | 本地文件 |
| Modules（DaVinciResolveScript） | 同上 `Modules/` | import |
| 本地文档入口 | Resolve 菜单 `Help > Documentation > Developer` | GUI |

### MediaPool 片段色彩

`GetClipColor()` 17 种标准色彩对照表 → 见 `davinci-api` skill > 返回值坑位 > GetClipColor() 返回值对照表。

项目使用: `check_core.py → _audio_color_detail()` 据此判断音频越轨。

### 社区

| 资源 | 位置 | 怎么读 |
|------|------|--------|
| We Suck Less Resolve Scripting | `https://www.steakunderwater.com/wesuckless/viewforum.php?f=35` | WebFetch |
| Blackmagic 官方论坛 | `https://forum.blackmagicdesign.com/` | WebFetch |
| dvresolve.com wiki | `https://wiki.dvresolve.com/developer-docs/scripting-api` | WebFetch |
| Stack Overflow (`[davinci-resolve]`标签) | ~100问题，60%已整理到WSL | WebFetch |
| Reddit r/davinciresolve | 不推荐，API讨论<5% | — |

### GitHub 开源项目

| 项目 | 仓库 | 价值 |
|------|------|------|
| davinci-resolve-mcp | `samuelgursky/davinci-resolve-mcp` | 98.5% API覆盖,MCP协议,AI集成 |
| pybmd | PyPI `pip install pybmd` | 版本兼容封装,自动处理v16.2.0参数变更 |
| nobphotographr/automation | `nobphotographr/davinci-resolve-automation` | Limitations.md+Advanced_Techniques.md权威参考 |
| Theia | `ming-qiu/theia` | VFX editorial GUI工具,仅Studio 18.6+ |
| Reactor | `github.com/WeSuckLess/Reactor` | 社区包管理器,内含48+UI示例 |

### 在线 API 文档

| 资源 | 链接 |
|------|------|
| X-Raym Gist | `gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8` |
| deric 非官方文档 | `deric.github.io/DaVinciResolve-API-Docs/` |
| resolvedevdoc (ReadTheDocs) | `resolvedevdoc.readthedocs.io` |

### 本地参考代码

| 资源 | 位置 |
|------|------|
| 张来吃 Batch_io_Pro.py（生产级 UI） | `/Volumes/MYJC/06_Software/达芬奇脚本/批量IO渲染/` |
| 批量替换片段 Lua 脚本 | `/Volumes/MYJC/06_Software/达芬奇脚本/批量替换片段/` |
| TTS 语音工具 | `/Volumes/MYJC/06_Software/达芬奇脚本/TTS语音工具/` |

### 学习资料

| 资源 | 位置 |
|------|------|
| AI 调研报告（GPT/MiniMax/豆包/千问） | `AI去字幕/外部调研报告/` (7份) |
| HEIBA 黑靶插件源码（Lua, 明文解密） | `达芬奇学习资料/HEIBA插件源码/` (4个脚本) |

---

## API 供应商

### 无痕AI 2.1（当前在用）

| 项目 | 值 |
|------|-----|
| 官方文档（唯一来源） | **飞书 Wiki** `https://suiyu-network.feishu.cn/wiki/WUvXwI5vziT24qkAVdDcxTzLnef` |
| 怎么读 | `lark-cli docs +fetch --doc WUvXwI5vziT24qkAVdDcxTzLnef --as bot` |
| Base URL | `https://api.wuhenai.com/v2/` |
| 代码 | `AI去字幕/adapters/wuhenai_v2.py` |
| 定价（来源：飞书文档计费表） | video_removal_std + sel_area = 1积分/秒 |
| point_to_yuan | 0.0091（¥1000→110000积分，裁缝老师实测 2026-05-05） |
| rect 面积上限 | 480,000 px² |

### 鬼手 GhostCut（备用）

| 项目 | 值 |
|------|-----|
| 官方文档 | **飞书文档** `https://jollytoday.feishu.cn/docx/U73qdBhWbozFdpx4eTvcIO4gn7e` |
| 怎么读 | `lark-cli docs +fetch --doc U73qdBhWbozFdpx4eTvcIO4gn7e --as bot` |
| 官网 | `https://cn.jollytoday.com/enterprise/` |
| API Base | `https://api.zhaoli.com` |
| 代码 | `AI去字幕/adapters/ghostcut.py` |
| GitHub | `https://github.com/JollyToday/GhostCut_Remove_Video_Text` |
| 认证 | AppKey + AppSecret → MD5 签名 |
| 定价（VIP4，当前） | 字幕擦除 Lite版=2点/30秒, Pro版=5点/30秒（来源：豆包翻译官方定价表，2026-05-12） |
| VIP 等级对照 | 见 `AI去字幕/外部调研报告/豆包：鬼手定价标准.md`（VIP1-VIP8 全表） |
| 注意 | GhostCut 字幕擦除无 pro_large/pro 全屏档——仅 Lite版 和 Pro框选两档 |
| point_to_yuan | 0.19（¥189/1000点） |

### 阿里云 OSS

| 项目 | 值 |
|------|-----|
| 官方文档 | `https://help.aliyun.com/zh/oss/` |
| REST API 签名 V1 | `https://help.aliyun.com/zh/oss/developer-reference/signature-v1-authorization` |
| 怎么读 | WebFetch |
| OSS Endpoint | `{bucket}.oss-cn-hangzhou.aliyuncs.com` |
| SDK GitHub | `https://github.com/aliyun/aliyun-oss-python-sdk` |

---

## 基础设施

### SMB 文件服务器

| 项目 | 值 |
|------|-----|
| 地址 | `192.168.1.154` |
| 挂载路径 | `/Volumes/MYJC/` |
| 脚本目录 | `/Volumes/MYJC/06_Software/达芬奇脚本/` |

### PostgreSQL（达芬奇协作数据库）

| 项目 | 值 |
|------|-----|
| 地址 | `192.168.1.154` |
| 数据库 | `MYJC_2026_A` (42项目), `MYJC_2025_A` |

### 飞书 CLI

| 项目 | 值 |
|------|-----|
| 工具 | `lark-cli` |
| 配置 | `~/.lark-cli/config.json` |
| 默认身份 | `--as bot` |

---

## 余额查询方法

### 无痕AI 2.1

| 项目 | 值 |
|------|-----|
| 接口 | `GET /user/me` |
| 认证 | Bearer token（从 API Key 换取，7天有效） |
| 返回 | `{"balance": int}` 积分余额 |
| 代码位置 | `core.py → query_balance()` → `adapter.get_balance()` |
| 汇率 | ¥0.0091/积分（裁缝老师实测充值） |
| 代码 | `pricing.py → point_to_yuan()` |

### 阿里云账户余额

| 项目 | 值 |
|------|-----|
| 接口 | `GET business.aliyuncs.com/?Action=QueryAccountBalance` |
| 认证 | OSS AccessKey + HMAC-SHA1 签名 V1（与 OSS 同一套凭证） |
| 返回 | `{"Data": {"AvailableCashAmount": "99.77", "Currency": "CNY"}}` |
| 代码位置 | `stable_ui.py → refresh_oss_bal()` |
| API文档 | `https://help.aliyun.com/zh/user-center/developer-reference/queryaccountbalance` |

> ⚠️ OSS AccessKey 需要有财务权限。当前 `OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET` 已有权限。
> 如果没有，需在 RAM 控制台给用户加 `AliyunBSSFullAccess` 权限。

### 鬼手 GhostCut（备用）

| 项目 | 值 |
|------|-----|
| 接口 | `GET /v-w-c/gateway/ve/point/query` |
| 认证 | AppKey + AppSign（MD5签名） |
| 返回 | `{"pointAssets": [{"pointBalance": xxx, "expireTime": xxx}]}` |
| 代码位置 | `core.py → query_balance(adapter_config=ADAPTER_CONFIGS['ghostcut'])` |
| 汇率 | ¥0.19/点（¥189/1000点） |

---

## 使用规则

1. **查规则先翻这个文件** — 找到对应供应商的行，按「怎么读」方式获取最新文档
2. **飞书文档用 lark-cli** — 不要 WebFetch，lark-cli 更快且带认证
3. **不确定的标注「需验证」** — 不要拿记忆里的东西当成权威
4. **新接入供应商** — 第一件事是把它的文档来源注册进这个表
