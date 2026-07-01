# 达芬奇插件工坊 — 产品开发章程

> 我是小裁缝的**插件分身**。
> 管全系达芬奇插件（AI去字幕/交付自检/批量命名等）+ 授权系统 + 发布部署。
> ❌ 不管 Mac mini 运维、SMB 存储。

> v4.0 | 2026-07-02 | 单表授权+Fingerprint缓存+IP/地区/ISP+诊断包全面升级
> v3.1 | 2026-06-16 | 安装脚本重写+IME弹窗替代+FC URL修复+License重构

## 跨项目引用

- **机器清单**：`~/WorkBuddy/达芬奇运维专家/config/machine_registry.json`（21 台，SSH alias: mini101-mini200）
- **远程管理 skill**：`~/WorkBuddy/达芬奇运维专家/.workbuddy/skills/远程管理/SKILL.md`（SSH 免密/集群操作）
- **所有机器 SSH 免密已配**：`ssh mini{101..110} mini{130..138} mini140 mini200`，密码 123456，sudo 可用。

## 终局

优先服务剧有文化 20 人内部。所有架构决策须兼容"未来全行业卖"——不写死公司路径、品牌名可替换、SMB 路径可配置。

## 产品线

| 产品 | 版本 | 状态 |
|------|------|------|
| AI去字幕 | v1.11.3 | ✅ |
| 交付自检 | v2.5.11 | ✅ 单表授权+指纹缓存+IP/地区/ISP+诊断包7文件 |
| 批量命名工具 | v3.6 | ✅ 表格版，8字段(Ep/Sc/Gr/Tk/desc/method/author/v/status)，导表+硬编码消除+审查模式+DMG分发 |
| 批量命名工具_创壹特供版 | v1.1 | ✅ 表格版，9字段(EP/SC/SH/TK/desc/type/author/V/status)，导表+死代码清理 |
| AI换口型 | — | 待开发 |
| AI语音克隆 | — | 待开发 |
| AI超分 | — | 待开发 |

## 质量铁律

- **60 分才推全公司**。可用、不崩、用户不需要思考。
- UI 质量是核心指标。"闭着眼睛点"是设计目标。
- 推全公司前必须在达芬奇里跑完整集成测试。
- git commit 不超过 30 分钟，破坏性操作前先 stash。
- Session 收工前检查版本号，有实质性改动就 bump。
- 改完代码立刻跑全量对比验证，不凭感觉。
- **代码审查标准**：见 `达芬奇代码审阅` skill（L0-L3 分级）

## 部署三梯队

| 梯队 | 操作 |
|------|------|
| 本地 | `build_local.sh`（不同步 SMB） |
| 灰度 | 拷 SMB 灰度目录 → gray.json |
| 全量 | `push_all.sh` 同步 SMB + 清 gray.json |

推全公司前必须灰度至少一台。

## 发布安全网（2026-06-13 重构）

### 版本管理
- **唯一真相源**：`config.py.__version__`（纯 semver）+ `__channel__`（环境锁）
- **环境隔离**：`__channel__ = "dev"` = 本地开发，`""` = 生产。repo 默认 dev。
- **切换工具**：`交付自检工具/channel.sh dev|prod`，写后校验确认生效。
- **bump 入口**：`publish.sh VERSION_BUMP=patch|minor|major`。
- **dev 绝不碰 SMB**：`publish_push_all()` + `publish_sync()` 两处硬拦截 `__channel__` 非空即拒绝。sync.sh 新加 trap EXIT 自动切回 dev。2026-06-17 发现 SMB 历史残留 `channel=dev`，修复后全量验证通过。
- **SMB 修改后验证**：每次修改 SMB 文件后必须检查 `__channel__ = ""`、`IS_PERSONAL = False`、同事机器可读。

### 四层硬拦截（dev 代码永不碰到产线）
| 操作 | 拦截位置 | 行为 |
|------|---------|------|
| SMB 同步 | `publish_sync()` | dev → 拒绝 |
| 灰度管理 | `gray.sh add/remove/promote` | dev → 拒绝（status 放行） |
| 推全公司 | `publish_push_all()` | dev → 拒绝 + `trap EXIT` 自动切回 dev |
| GitHub 发布 | `publish_release.sh` | dev 拒绝 + 版本一致性校验 + 历史保留 |

### 产品注册表
- `.precommit-products`：唯一真相源，一行一个产品目录。`# 产品名` = 归档不扫描。
- `pre-commit.sh` 启动时双向校验：文件里写的必须存在目录，有 .py 的目录必须在文件里注册。

### 个人版
- `build_personal.sh` 打包前自动去 channel，永不带 `-dev` 后缀。

## 授权系统（v4.0 单表，2026-07-02）

- **表**：飞书 Base `授权记录`（`tblGfiUYR3UHQT08`），一行一指纹，13 字段
- **状态机**：试用中 → 可激活 → 已激活 → 已停用
- **FC**：`license-node-mtqaghwijy.cn-hangzhou.fcapp.run`，Node.js 四 handler
- **指纹缓存**：`~/.config/dv_license/fingerprint`，换主板/系统盘才变
- **IP/地区/ISP**：客户端自报，心跳刷新
- 详见 `交付自检开发` skill + `插件排错诊断` skill

## 共享路径

- **SMB**: `/Volumes/MYJC/06_Software/达芬奇脚本/`
- **本机开发**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/{产品}/`
- **Launcher（壳方案）**: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/`（壳一次性部署，永不再改）
- **路径铁律**: 所有部署路径使用系统级 `/Library/Application Support/`，不用用户级 `~/Library/`。系统级路径 Finder 可见，用户级不可见。个人版同样遵循此规则。
- **打进去不装上去**: 运行时零安装——任何依赖以文件形式 vendoring 或数据嵌入。构建时 pip 随便用，用户更新包永远只是解压→覆盖，无 `pip install`

## 分发体系（2026-06-20 重构）

| 渠道 | 内容 | 用途 |
|------|------|------|
| 飞书文档 `T5D1d...an2g` | 产品介绍 + 95MB ZIP 附件 | 唯一入口，人工下载 |
| GitHub `update_latest.zip` | 543KB 增量包 | 插件内「检查更新」自动拉 |
| SMB | `交付自检工具/` + `shared/` | 公司 20 台自动同步 |
| GitHub Pages | ❌ 已删除 | 飞书文档替代 |
| 百度网盘 | ❌ 已放弃 | 可执行文件百审不过 |

## 共享模块

| 模块 | 用途 |
|------|------|
| `shared/script_parser.py` | 剧本解析 → 人物+分集台词 |
| `shared/llm_providers.py` | LLM 供应商接口（当前仅 DeepSeek V4 Pro） |
| `shared/llm_typo_check.py` | 错别字校对 + SHA256 缓存 |
| `shared/pypdf/` | 纯标准库 PDF 提取 |
| `shared/dftt_timecode/` | DFTT Timecode（零依赖） |
| `shared/naming.py` | 命名规则 + 输入清洗 |
| `shared/.env` | LLM Key + 飞书 Bot，SMB 共享 |

## 开发规则

1. **launcher 用 subprocess.Popen 外挂 Python**。Fusion 内 `__file__` 不存在。
2. **达芬奇 API 返回值不可信**。`GetItemListInTrack` 空轨返 None，遍历必须 `or []`。
3. **跑测试直连 GUI**，不搞 nogui。达芬奇开着时 Python 直连 `bmd.scriptapp('Resolve')`。
4. **Tree 样式不可靠**，先上纯文字，BackgroundColor/TextColor 在 20.3.2 可能不渲染。
5. **UI 控件 API**: `ui.Widget({"ID": "id", ...})`，不是 `("id", {...})`
6. **事件绑定**: `win.On["ID"].Clicked`，不是 `win.On.ID.Clicked`
7. **中文版兼容**: GetClipProperty('Type') 返回「时间线」而非「Timeline」
8. **达芬奇内 HTTPS 调用禁止带证书验证的 urllib**。DaVinci 子进程 SSL 沙箱限制。两种合法方案：① `subprocess.run(["curl", ...])` ② `urllib + ssl._create_unverified_context()`（仅用于已信任目标如自家 FC）。
9. **sync 后必须重读凭证**。`verify_local` 写盘后 UI 须再次 `load_credential()`。
10. **日期计算只用序数减法**，不用 timestamp 整除 86400。
11. **`save()` 入口强制 str(value)**。macOS keychain 只接受字符串。
12. **按钮互斥用 `Enabled`，禁用 `Visible`**。Visible=False 释放布局空间→跳动。
13. **`config_dlg.RecalcLayout()` 必须在 `Show()` 后调用**。
14. **金区(TRIAL_LB)=授权、灰区(HINT_LB)=指引，永不越界**。
15. **UIManager 非默认事件必须 `Events:{Name:True}` 启用**。鬼猫猫文档确认仅 Clicked/Close 默认启用；FocusIn/KeyPress/SliderMoved 等必须控件定义时声明。——2026-06-13
16. **`SetFocus()` 需要 `Events:{FocusIn:True}` 前置**。待验证。——2026-06-13
17. **涉密/激活码输入禁止用 LineEdit**。LineEdit + CJK 输入法 → `Fusion::RemoteApp::FindLocalObject` SIGSEGV 闪退（2026-06-16 实测）。替代：osascript `display dialog`（单行）或 tkinter 子进程（多框）。——2026-06-13
18. **弹窗按钮必须防连点**。`subprocess.run` 阻塞期间 UIManager 事件排队 → N 次点击 = N 个弹窗。标准解法：`Enabled=False` 在 `try` 前 + `finally` 统一恢复。——2026-06-13
19. **`sys.stderr` 重定向前必保存 `_real_stderr`**。所有内部写 stderr 处用 `_real_stderr.write()`，禁止 `print(..., file=sys.stderr)`。`_UIStderr.write` → `_ui_write` → `_ui_write_direct` → `print(file=sys.stderr)` → 回环 → 无限递归 → RecursionError 杀线程。——2026-06-27 紧急排障修复

## UIManager 已知限制（2026-06-16 更新）

| 限制 | 影响 | 替代方案 |
|------|------|---------|
| LineEdit + CJK 输入法 | macOS 26+ DR 20.3.2 SIGSEGV 闪退 | osascript `display dialog` 或 tkinter 子进程 |
| 无通用 ScrollArea | VGroup/HGroup 内容超出截断 | Tree 有滚动 (VerticalScrollMode + ScrollToItem) |
| Tree TextColor/BackgroundColor | v20.3.2 不渲染，API 存在 | 纯文字分隔替代 |
| Tree 无 SetItemText/SetItemChecked | 只能纯展示，不能交互勾选 | TreeItem 有 CheckState[0]（需验证） |
| VGroup 不裁剪溢出 | 控件多时窗口撑破屏幕 |
| `SetFocus()` 不生效 | 需要 `Events:{FocusIn:True}` 在控件定义时启用 | 待验证 |
| 无 Timer / Idle 回调 | 不能启动后延迟执行 | 所有初始化在 `disp.RunLoop()` 前同步完成 |
| `Visible=False` 释放布局空间 | 隐藏后后续控件挤占空位 | 用 `Enabled=False` 替代，保持占位 |
| 非默认事件不触发 | Clicked/Close 之外需 `Events:{Name:True}` 显式启用 | 鬼猫猫文档 2026-06-13 确认 |
| subprocess 阻塞 + Clicked 排队 | 弹窗按钮连点出多个窗口 | `Enabled=False` 在 try 前 + finally 恢复 |
| urlopen 在子进程无限挂 | timeout 参数被忽略，线程/子进程超时均无效 | 文件选择→fu.RequestFile/Dir；网络调用→主shell线程/curl subprocess |
| tkinter 子进程生 Docker 图标 | macOS 独立 Python 进程占据 Dock | 文件/文件夹选择→fu.RequestFile/Dir（Fusion 原生）

## UI 设计规范

- **标题栏**：纯产品名，不带版本号。`"WindowTitle": PRODUCT_NAME`
- **右下角**：版本号。`f"{BRAND_NAME} | v{version_string()}"`
- 详情见 `达芬奇交付自检开发` skill

## 运维铁律

- **deploy_tracker 不可信** — 人工维护的元数据，部署后逐台扫描验证文件存在。
- **迁移/清理后全量验证** — 跑 verify.py 确认所有产品 launcher 在位。
- **auto-commit 加 `--no-verify`** — 绕过 pre-commit 阻塞。
- **SMB 统一配置**: `~/达芬奇插件工坊/deploy.json` → smb_mount，换公司改 JSON 不动代码。
- **publish.sh MD5 锁**: 推 SMB 前逐文件对比 MD5，不一致硬拦截。
- **更新发布前验证**: 改 install.command / ui.py 更新流程后，跑 `build → unzip → bash -n 安装脚本 → 模拟安装` 四步，确认再部署。2026-06-01 引入 3 轮连锁 bug 的教训。

## 关键 Skill

| Skill | 用途 |
|-------|------|
| `达芬奇脚本开发` | API + 冒烟测试 |
| `达芬奇UI开发` | UIManager |
| `达芬奇插件发布管理` | 版本号 + 灰度 + 全量 |
| `达芬奇交付自检开发` | 交付自检扩展约定 |

## 批量命名工具架构要点（2026-05-24 终版）

- 去重用局部 `seen_fp`，避开类级变量跨批泄漏
- 版本号唯一来源 `app_table.js` 第 1 行，改版只改一处
- 详见 `批量命名开发` skill

## 交付自检核心要点

- CHECKS 注册表驱动，更新到 22 项（v2.0.18）
- 门机制：并行四扇，严格/宽松两种模式
- 分级：warn 仅 5 类（夹帧/直通/异体字/系统词典/尾板），其余 fail
- AI 错别字：右侧独立面板，DeepSeek V4 Pro
- 路径检测：无 gate 永远先跑；中英文 Type 兼容
- 音量检测：API 限制，待达芬奇更新
## 安装体系（2026-06-16 确立）

### 四种分发方式

| 方式 | 用户 | 入口 |
|------|------|------|
| Mac 手动 | 双击 Mac安装.command → 输密码 | zip 网盘 |
| Win 手动 | 右键 Win安装.bat → 管理员 | zip 网盘 |
| Agent + GitHub | 发 repo 链接 | git clone → `python install_agent.py` |
| Agent + Zip | 拖 zip 给 agent | 解压 → 读 先读我.txt agent 区 → `python install_agent.py` |

### install_agent.py 设计
- JSON 行输出（每行一个对象），agent 逐行解析
- `need_sudo`/`need_admin` 回调 → agent 向用户要密码 → `--continue` 断点续装
- 状态文件 `~/.delivery_checker_install_state.json` 支持中断恢复
- 全流程 agent 最多向用户要一次密码

### 打包规范
- 单 zip 全平台通用，data.zip 内含双平台 Python 安装器（95MB）
- 先读我.txt 人类看上半、agent 看 `# AGENT SECTION` 下半
- README.md 同时服务 GitHub 人类 + agent 浏览

## 参考

- **外部参考**：`knowledge/davinci-reference.md`（鬼猫猫/张来吃/派派的派/HEIBA）






## 壳方案 + 部署架构 (2026-05-25)

- **永久壳**: shell.py(40行) 每台机器 Fusion Scripts 目录，永不更新。找 Python(数字排序)→deploy.json→SMB launcher+看门狗
- **launcher.py**: sys.executable，设 WORKBUDDY_PRODUCT 环境变量
- **deploy_config.py**: load()/get_smb_mount()/get_python_path()，取代 6 份拷贝
- **SSL**: 全仓 _create_unverified_context()，Python 3.14 兼容

## 一键更新系统 (2026-06-08 更新)

- 多链路回退：jsDelivr CDN → GitHub API → GHProxy
- 分块下载 + 进度条回调，60s 超时
- 全 ASCII 铁律：zip/URL/.command 文件名全部英文
- 配置入口：`shared/update_config.py`

## 配置页 + License 体系 (2026-06-01)

### 配置页结构（v2.2.31 终版）

| 项目 | 个人版可见 | SMB 可见 |
|------|:--:|:--:|
| 激活码 | ✅ | — |
| 转移授权（停用按钮） | ✅ | — |
| DeepSeek API Key | ✅ | — |
| 飞书 App ID | ✅ | — |
| 飞书 App Secret | ✅ | — |
| 个人词典（Finder 定位） | ✅ | ✅ |

- API Key 存储：`~/Library/Application Support/交付自检/api_keys.json`
- 首次打开从 `.env` 自动迁移（兼容 `FEISHU_BOT_APP_ID` 等旧变量名）
- 显示密文（`sk-ab…xyz`），保存时检测掩码保留真值
- SMB 用户过滤：`if not WORKBUDDY_PERSONAL` → 只渲染 `censor_personal`

### License / 激活系统 (v3 — 2026-06-10 重构)

#### 架构
- **试用纯本地**：`init_trial()` 写本地凭据，不调服务端。30 天一次性。
- **无心跳**：仅启动时 `verify_status` 校验激活码是否仍有效。
- **停用回归试用**：试用天数冻结（存 `trial_remain_secs`），停用时恢复剩余天数。
- **吊销保护**：启动时联网查激活码+指纹 → revoked → 写过期凭据（非清空），防止删除重拿试用。
- **凭证**：单文件 `~/.config/dv_license/license.dat`，隐藏 + 指纹校验。

#### 表结构（飞书 Base）
```
激活码 | 状态(待售/待激活/已激活) | 机器指纹 | 激活时间 | 用户 | 备注
```
gen_key → 待售。Admin 手动改待激活。激活 → 已激活 + 带第一次激活时间。

#### 状态机
```
启动 → 无凭证 → init_trial()（纯本地）→ 30 天试用
       有凭证 → is_trial=True  → 试用剩余 N 天 / 0 天（到期）
                 is_trial=False → verify_status → 已激活 ✓ / 吊销
激活 → 服务端 validate → 待激活→已激活 → is_trial=False
停用 → 服务端 deactivate → 已激活→待激活+清指纹 → is_trial=True（恢复试用天数）
```

#### 关键规则
- **`_ai_allowed` ≠ `is_trial`**。预填、保存跳过都应以 `load_credential().is_trial` 判断，不用 `_ai_allowed`。
- **用户输错码不记入错误计数器**：`_activation_failed` 机制。
- **黄字 = 许可证售卖**，**白字 = 功能指引**。
- **服务端直出人性化消息**，客户端零翻译。
- **tkinter 子进程三框弹窗（2026-06-16 替代 LineEdit）**：防 IME 崩溃，`isascii()` 双重校验。

#### 云函数（阿里云 FC）

| 项目 | 值 |
|------|-----|
| 函数名 | `license-node` |
| 服务 | `license-node-mtqaghwijy.cn-hangzhou` |
| 正确 URL | `https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run` |
| 运行时 | Node.js |
| 路由 | `POST /license {"action":"activate|deactivate|verify_status|init_trial|manage"}` |
| 部署方式 | `aliyun fc PUT /2023-03-30/functions/license-node` + base64 zip |
| FC 代码 | `cloud/license_fc.js` |

**环境变量**（在阿里云控制台 FC 函数配置中设置）：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` — 飞书应用凭证
- `BASE_TOKEN` — 飞书多维表格 token（`BRfGbDgaJa6ZYCsViuOcau2PnSe`）
- `TABLE_ID` — 单表「授权记录」（`tblGfiUYR3UHQT08`），v4.0 起替代旧双表

**授权记录表**（单表，一行一指纹）：
| 字段 | 说明 |
|------|------|
| 机器指纹、激活码、买家、状态 | 核心身份 + 生命周期 |
| 首次试用时间、激活时间、最后活跃 | 时间线 |
| 插件版本、系统版本、达芬奇版本 | 心跳刷新 |
| 最近IP、所属地区 | 心跳刷新（含 ISP） |

**故障排查**：
```bash
# 测试 FC 连通性
curl -s -X POST 'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/license' \
  -H 'Content-Type: application/json' \
  -d '{"action":"init_trial","machine_fingerprint":"test"}'

# 查看 FC 函数状态
aliyun fc GET /2023-03-30/functions/license-node

# 客户端验证（远程机器）
ssh machine "grep WB_LICENSE_URL '...交付自检工具/.env'"
ssh machine "cat ~/.config/dv_license/license.dat | python3 -c '...'"
```

**踩坑**：`_write_env.py` 和 `license.py` 默认值曾指向不同的 FC URL（2026-06-16 统一为 `license-node-mtqaghwijy`）。

#### 激活码格式
不分大小写，支持数字/字母/任意组合。gen_key 生成 `XXXX-XXXX-XXXX`。管理后台可手填。

### PYTHONUTF8=1 + -B

- 两 launcher（personal + SMB）都设 `PYTHONUTF8=1` + `-B`（不生成 pyc）
- `open()`/`zipfile` 默认 UTF-8，杜绝编码乱码。增量包 ~192KB

## 路径检测重构（2026-06-07）

- **配置驱动**：`deploy.json` 的 `smb_paths` 字段（数组），空 = 全放行，非空 = 白名单模式
- **与硬编码解耦**：全程不依赖 `/Volumes/MYJC`，旧 `smb_mount` 兼容已砍
- **注册表**：路径/脱机检测 `tracks` 必须含 `["video", "audio"]`（仅 `video` 会导致音频漏检）
- **懒加载**：`check_path_location()` 内部每次现场读 deploy.json，不缓存 `_SMB_PREFIXES`
- **缓存清理**：每次「开始检查」前调 `_clear_clip_files_cache()`，防止 I/O 范围变化返回旧数据
- **音频兜底**：音频轨未预加载时 `_get_cached(it, "mp")` 返回 None → 直接调 `it.GetMediaPoolItem()`

## 全半角检测（2026-06-07）

- **系统检测不通过 AI**：正则 `[\uff00-\uffef]`，`str.maketrans` 生成建议修正
- `status=fail`，分类「字幕 → 文本」（与换行/时长同类）
- **防重复**：`bad_char_ranges.txt` 中全角行 `U+FF01-U+FF5E` 已注释
- 异体字检测不再抓全角字符

## 个人版安装分发（2026-06-16）

### 构建产物
- 百度网盘上传单个 `.zip`（非文件夹）——Archive Utility 解压保留 `+x` 权限
- 文件名 `交付自检工具_v{VER}.zip`，版本号从 `config.py` 自动读取
- 内层 zip 固定名 `请勿直接解压此文件.zip`
- Python.pkg 保持官方原名 `python-3.13.13-macos11.pkg`
- `.command` 文件改名 `Mac安装.command`

### 更新包
- `--update` 模式产出 `update_latest.zip`（ASCII 名，GitHub Release 中文文件名会乱码成 `_`）
- 构建时 SHA 校验已移除——zip 时间戳非确定性，每次构建 SHA 不同

## 编码铁律（从 SOUL 下沉）

### 代码编辑
- 批替后 diff 验证每条改动，优先精确字符串替换不用 replace_all
- 禁止用正则批量编辑生产代码，删代码逐函数手动 Edit
- 跨平台适配后验证缩进，不只看逻辑，逐行确认
- 修完一处 bug → grep 全项目同款 → 一并修

### 调试与问题排查
- 先证代码无 bug 再归罪外部，审查调用链而非假设网络/服务器问题
- 模块级缓存每次操作前主动清（`_clear_*()`），不推断"上次清过了"
- 不在日志里猜 bug，`grep error` 的结论被用户确认前 = 幻觉

### UI 开发（tkinter）
- 改 UI/交互后审阅完整调用链——往前找三行谁设的值、往后看三步谁消费
- 防抖是补丁不是根治，`setTimeout` 只掩盖现象，找数据层面的根因

### 产品开发
- 新产品先讨论→画图→写代码，跳过前两步 = 白写
- 安装/配置类脚本先展示完整变更列表再等确认，密码 = 确认

### 部署与配置
- 部署后不验证 = 没部署，每次 push/scp 后跑自动化检查
- 同一资源只能有一个 URL/路径入口，新入口必须 grep 消除重复

### 算法与库
- QR/条形码/加密等不手写，用成熟库生成后嵌入常量
- `webbrowser.open()` 不判连通性，`socket.create_connection` 先测端口再决定
