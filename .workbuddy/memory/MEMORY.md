# 达芬奇插件工坊 — 产品开发章程

> 我是小裁缝的**插件分身**。
> 管 AI 去字幕/交付自检、灰度发布部署。❌ 不管 Mac mini 运维、SMB 存储。

> v3.1 | 2026-06-16 | 安装脚本重写+IME弹窗替代+FC URL修复+License重构
> 2026-06-12 | SMB 全量同步 + 个人版残留清理

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
| 交付自检 | v2.5.7 | ✅ |
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

## 共享路径

- **SMB**: `/Volumes/MYJC/06_Software/达芬奇脚本/`
- **本机开发**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/{产品}/`
- **Launcher（壳方案）**: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/`（壳一次性部署，永不再改）
- **路径铁律**: 所有部署路径使用系统级 `/Library/Application Support/`，不用用户级 `~/Library/`。系统级路径 Finder 可见，用户级不可见。个人版同样遵循此规则。
- **零 Runtime pip**: 运行时只用标准库 + `fusionscript_loader.py`。构建时可用 pip 库生成数据（QR 矩阵/字典/配置等），输出为纯数据文件，不打入 .whl/.egg。达芬奇连接用 `fusionscript_loader.py`。

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

### 去重机制
- `seen_fp`（`_process_paths` 局部变量）：size + 前 64KB MD5，**仅本批**。类级变量跨批泄漏是系统性反模式。
- `_sent_fps` 已删除——其防 evaluate_js 重放的职能被局部 `seen_fp` 接管
- JS 侧：`fp || path` 优先级，`result.duplicates` 优先于本地重算

### 文件结构
- 表格版（主）：`renamer_web.py` `app_table.js/css` `renamer_table.html`（根目录）
- 卡片版（备用）：`card/app.js` `card/app.css` `card/renamer_web.html`
- `_splice.py` 和 `build.sh` 均引用 `card/` 路径
- **版本号唯一来源**：`app_table.js` 第 1 行 `const APP_VERSION='x.y'`。`_splice.py` 自动从 JS 提取版本号生成 `version_info.txt`，HTML 运行时注入。改版只改一处。（2026-06-04 解耦）

### 解析系统
- `shared/naming.py`：`FILENAME_RE` 从 `FIELD_CONFIG` 自动生成（`_build_filename_re`）
- `FALLBACK_RE`：只匹配 `Ep/Sc/Gr/Tk` + `v/status`，中间不拆 desc/method/author
- `_EMPTY_KEYS = {'ep','sc','gr','tk','ver'}`：解析失败强制留空，信任解析器判定
- method 由 desc 反查（`DESC_TO_METHOD`），desc 为空时跳过推断

### 构建
- macOS：`build.sh table`，用系统 Python + `ditto`（托管 Python 无 PyInstaller）
- Windows：`build_win.bat table`，`--add-data` 用分号分隔，`--hidden-import webview.platforms.edgechromium`
- 打包图标：macOS `.icns`，Windows `.ico`

### 日志系统
- 逐文件 `_log.debug`：文件名、解析结果、字段值
- 汇总 `_log.info`：`{N} files, {M} parsed, {K} raw, {D} dup`
- `result()` 加 `call('debug_log', ...)` 确认持久结果写入

### pywebview 特殊约束
- `if(!window.pywebview)` 在注入前检查不可靠 → 用 `setTimeout + 再判断`
- `el.focus()` 不一定触发 WKWebView 原生 focus 事件 → 去 `_focused` 守卫
- `click.detail >= 2` 比自制 timer 可靠
- WKWebView 会双火 drop 事件 → 去重靠局部 `seen_fp`，不加防抖

### 字段校验
- `DIGIT_STRICT`：ep/sc/gr 拒 00（`/^(0[1-9]|[1-9]\d)/`），blur + Enter 双重校验
- `DIGIT_RULES`：输入时过滤非数字字符

## 交付自检核心要点

- CHECKS 注册表驱动，更新到 22 项（v2.0.18）
- 门机制：并行四扇，严格/宽松两种模式
- 分级：warn 仅 5 类（夹帧/直通/异体字/系统词典/尾板），其余 fail
- AI 错别字：右侧独立面板，DeepSeek V4 Pro
- 路径检测：无 gate 永远先跑；中英文 Type 兼容
- 音量检测：API 限制，待达芬奇更新
- **v2.5.7 重构**：`parse_script` 不再解析角色/分集，只返回 `{"lines": [...]}`；全量文本喂给 AI，AI 自行理解。支持 `.txt/.md/.docx/.doc/.pdf` 5 格式。集号手动输入已删除。
- **v2.5.7 LineEdit 清零**：所有输入框替换为 Label + osascript/tkinter 弹窗，彻底消除 CJK IME → SIGSEGV 崩溃路径。主窗口 3 处 + 配置页 3 处。
- **v2.5.7 文件守卫**：`>20MB` 拒绝，5 格式白名单拦截。
- **v2.5.7 死代码清理**：`_extract_characters`/`_split_episodes`/`match_timeline`/`_CHINESE_NUM`/`_cn_to_int`/`_parse_episode_number` 全部删除（~300 行）。根因：剧本是喂给 AI 的，不需要正则解析。
- **v2.5.7 按钮防连点**：8 按钮统一 `Enabled=False` + `finally` 恢复。配置窗口 `_config_open` 标志防重入。
- **v2.5.7 授权声明**：三处同步（`license.py` 注释 / `README.md` / `先读我.txt`）。语气：公益初衷（帮同行少扣绩效少熬夜）+ 99 元回本 + 欢迎读代码学习 + 只求别破解。

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

## 进度条重构方案 (2026-05-24)

**核心**: SubtitlePipeline 覆盖 `_get_progress_callback()`, 统一映射两个 adapter 的 phase→绿条+阶段标签

**映射表 (按phase名,不区分adapter)**:
| phase | 标签 | 绿条区间 |
|-------|------|:--:|
| upload | ⬆ 上传中 | 0.10→0.17 |
| submit | 📤 提交中 | 0.17→0.20 |
| processing | 🤖 AI处理中 | 0.20→0.75 |
| (pipeline) | ⬇ 下载中 | 0.75→0.90 |
| (pipeline) | 🔧 替换中 | 0.90→1.00 |

**兼容性**: 无痕有upload/submit/processing, 鬼手有upload/processing。共用同一映射表。
**倒计时**: 砍掉, 换阶段标签。
**完成态**: 已实现(绿条变绿+标题✅)。


## 飞书 CLI 配置 (2026-05-24)

`lark-cli config init` 已配好 app: cli_a940d087f9b89cc9。
读外部租户文档（jollytoday/suiyu-network）用 `--as bot`：
```bash
lark-cli docs +fetch --doc "<url或token>" --as bot
```
配置文件: ~/.lark-cli/config.json，不需要重新 OAuth。


## 跨产品可复用模式 (2026-05-24)

**进度条系统**（AI换口型/语音克隆等直接继承）：
- `BasePipeline` 已含 `MILESTONE_ENV_OK/PREPARE/DOWNLOAD/COMPLETE` 里程碑常量
- `interface.DaVinciPipelineUI.set_phase(text)` 直写 ST_LB
- `_get_progress_callback()` 模式：子类覆盖返回回调，映射 adapter ratio→绿条

**估值常量**：
- `pricing_defaults.EST_BASE_SECS / EST_PER_CLIP_SECS` — 目前基于无痕+鬼手数据
- 新工具可覆盖或追加自己的常量

## 壳方案 + 部署架构 (2026-05-25)

- **永久壳**: shell.py(40行) 每台机器 Fusion Scripts 目录，永不更新。找 Python(数字排序)→deploy.json→SMB launcher+看门狗
- **launcher.py**: sys.executable，设 WORKBUDDY_PRODUCT 环境变量
- **deploy_config.py**: load()/get_smb_mount()/get_python_path()，取代 6 份拷贝
- **SSL**: 全仓 _create_unverified_context()，Python 3.14 兼容
- **日志**: `tools/check_logs.sh <hostname>` 四源全出——插件日志 + 系统日志 + 进程状态 + 崩溃报告。**不加任何 grep 过滤，不预设关键词**。达芬奇系统日志只收 Traceback，插件的 UI 日志（~/.workbuddy/logs/）才收完整错误。别人报「用不了」，第一动作跑 check_logs.sh。
- **构建前 `rm -rf _build`**：`_splice.py` 写入 `_build/` 目录，不删旧目录会导致 splice 读旧缓存 → 打包产物和源码不一致。bug 修了但没生效，浪费多轮排查。

## 一键更新系统 (2026-06-08 更新)

### 架构
- **版本检查**：多链路回退 jsDelivr CDN → GitHub API → GHProxy
- **下载**：HEAD 拿文件大小 + 分块下载 + 进度条回调，60s 超时
- **安装**：`do shell script "/bin/bash install_update.command --update"` → 直接 root 覆盖
- **配置入口**：`shared/update_config.py`（仓库名、多链路 URL、超时、校验参数——换仓库只改这一个文件）
- **全 ASCII 铁律**：zip 根目录、URL 中的文件名、.command 文件名三者全部英文

### 个人版发布 (GitHub Release)

```bash
cd 交付自检工具_个人版 && rm -rf _build && bash build_personal.sh --update
SHA=$(shasum -a 256 _build/交付自检工具_更新包.zip | awk '{print $1}')
gh release create v2.x.y _build/交付自检工具_更新包.zip \
  --repo cgjpaladin/davinci-plugins --title "v2.x.y" --notes "公告"
git add version.json && git commit --no-verify -m "v2.x.y 发布" && git push
```

- git remote 必须 HTTPS, GH_TOKEN 有 repo scope
- 测试机：**dd-mbp**（ZT 10.163.15.58, User ttttt, SSH 免密），本机是 DEV 模式不触发更新
- 增量包 ~192KB（不含 Python/pkg）

## macOS DMG 分发（2026-05-28 沉淀）

**问题**：PyInstaller 构建的 `.app` zip 发给别人后打不开。macOS Gatekeeper 检测到下载来源（`com.apple.quarantine`）→ 拒绝 ad-hoc 签名 app。

**Sequoia (15.x)**：右键→打开被砍，`spctl --master-disable` 被禁。

**方案**：DMG + 隔离清除脚本。详见 `macos-dmg-dist` skill。

**关键发现**：
- `xattr -d com.apple.quarantine App.app && open App.app` 是唯一可靠方式
- ARM64 only → Intel Mac 无法运行。用 `arch -x86_64 python3 -m PyInstaller` 构建 x86_64 可同时支持两者（Rosetta 只翻译 x86→ARM）
- PyInstaller 后必须 `codesign --force --deep --sign -` 重签
- `cp -R` 到被签名锁住的旧 app 会嵌套（220MB），必须先 `rm -rf`

**体积**：每个 app ~110MB（ffmpeg 54MB + Python 15MB + PIL/lxml 20MB + 其他 20MB）

### 更新前端到端验证（2026-06-01 铁律）
```bash
bash 交付自检工具_个人版/build_personal.sh --update
python3 -c "解压zip→找install_update.command→bash -n语法→copytree到/tmp/_deli_src"
bash /tmp/_deli_src/install_update.command --update  # 模拟安装
```

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
- `TRIAL_TABLE_ID` — 试用指纹表（`tblMAUMo8VQGPDZP`）
- `ACTIVATE_TABLE_ID` — 激活码表（`tbla9FSVEuuiayQH`）
- `APPROVE_TABLE_ID` — 审批表

**两个 Base 表**：
| 表 | 用途 | 字段 |
|----|------|------|
| 试用指纹表 | 记录每台机器首次试用 | 机器指纹、插件版本、macOS版本、达芬奇版本、首次试用时间、最后活跃 |
| 激活码表 | 管理激活码生命周期 | 激活码、状态、绑定指纹、激活时间、停用时间 |

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

## 错别字提示词优化（2026-06-04）

- 7 条规则全补完整示例（original → correction + 原因），含不改反例
- 剧本用途三段论：角色名性别 / 剧情大纲 / 当前场戏上下文，禁止逐行比对
- 标点归并：「标点缺失或多余」，涵盖书名号《》和引号「」
- `reason` 归一化：AI 输出「错字」自动映射为「错别字」

## 配置页 SMB 路径编辑（2026-06-07）

- ComboBox 选择路径 + 删除按钮（`− 删除路径`）+ 文件夹选择器添加

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

### 安装脚本关键决策
- `exec 3>&1 >"$LOG" 2>&1` 输出分流：fd 1→日志，fd 3→终端
- 安装前摘要：列出所有变更→用户确认→输入密码→执行（不先斩后奏）
- 密码取消静默退出（`grep "User canceled"` 检测）
- osascript 弹窗换行用 `$'...\n...'` 而非 `'...\n...'`
- External Scripting 自动启用：`sed` 改 `config.dat` 中 `System.Scripting.Mode`

### 版本号
- 唯一真相源：`config.py: __version__`
- 构建脚本 + 文件夹/zip 名自动读取
- `version.json` 需手动同步 version + urls + sha256 + history
- 更新公告唯一来源：`CHANGELOG.md`（AI 不自己写）
- ComboBox API：`CurrentText`（非 `Text`）取值，`Clear()`+`AddItem()` 刷新
