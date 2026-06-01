# 达芬奇插件工坊 — 产品开发章程

> 我是小裁缝的**插件分身**。
> 管 AI 去字幕/交付自检、灰度发布部署。❌ 不管 Mac mini 运维、SMB 存储。

> v2.7 | 2026-06-01 | v2.2.31 配置页重做 + 一机一码 + 自助停用 + PYTHONUTF8

## 终局

优先服务剧有文化 20 人内部。所有架构决策须兼容"未来全行业卖"——不写死公司路径、品牌名可替换、SMB 路径可配置。

## 产品线

| 产品 | 版本 | 状态 |
|------|------|------|
| AI去字幕 | v1.11.3 | ✅ |
| 交付自检 | v2.0.30 | ✅ |
| 批量命名工具 | v3.4 | ✅ 表格版，8字段(Ep/Sc/Gr/Tk/desc/method/author/v/status)，导表+硬编码消除 |
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

## 共享路径

- **SMB**: `/Volumes/MYJC/06_Software/达芬奇脚本/`
- **本机开发**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/{产品}/`
- **Launcher（壳方案）**: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/`（壳一次性部署，永不再改）
- **路径铁律**: 所有部署路径使用系统级 `/Library/Application Support/`，不用用户级 `~/Library/`。系统级路径 Finder 可见，用户级不可见。个人版同样遵循此规则。
- **零 pip**: 只用标准库，达芬奇连接用 `fusionscript_loader.py`

## 共享模块

| 模块 | 用途 |
|------|------|
| `shared/script_parser.py` | 剧本解析 → 人物+分集台词 |
| `shared/llm_providers.py` | 多供应商 LLM + 自动降级 |
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

## UIManager 已知限制（2026-05-24）

| 限制 | 影响 |
|------|------|
| 无 ScrollArea | 列表型 UI 不可行 |
| Tree 无 SetItemText/SetItemChecked | 只能纯展示，不能交互勾选 |
| VGroup 不裁剪溢出 | 控件多时窗口撑破屏幕 |

→ 交付自检的 20 项 CheckBox + Tree 结果是 UIManager 上限。更复杂交互应评估 PySide6/Qt。

## UI 设计规范

- **标题栏**：纯产品名，不带版本号。`"WindowTitle": PRODUCT_NAME`
- **右下角**：版本号。`f"{BRAND_NAME} | v{version_string()}"`

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
- AI 错别字：右侧独立面板，DeepSeek→千问 自动降级
- 路径检测：无 gate 永远先跑；中英文 Type 兼容
- 音量检测：API 限制，待达芬奇更新

## 参考

- **HEIBA（黑靶）**：`docs/学习资料/HEIBA插件源码/INDEX.md`
- **社区工具**：`Batch_Exporter_chs.py`（张来吃）、`DR-批量导出工具 v2.1.py`（派派的派）

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

**飞书文档**：
- `lark-cli docs +fetch --doc "<url或token>" --as bot` 读外部租户文档
- 配置文件 `~/.lark-cli/config.json` 已配 app cli_a940d087f9b89cc9

## 壳方案 + 部署架构 (2026-05-25)

- **永久壳**: shell.py(40行) 每台机器 Fusion Scripts 目录，永不更新。找 Python(数字排序)→deploy.json→SMB launcher+看门狗
- **launcher.py**: sys.executable，设 WORKBUDDY_PRODUCT 环境变量
- **deploy_config.py**: load()/get_smb_mount()/get_python_path()，取代 6 份拷贝
- **SSL**: 全仓 _create_unverified_context()，Python 3.14 兼容
- **日志**: tools/check_logs.sh 四源；stderr 双写确保 ResolveDebug.txt 可见

## 一键更新系统 (2026-05-31)

### 架构
- **版本检查**：多链路回退 jsDelivr CDN → GitHub API → GHProxy
- **下载**：多链路回退 + SHA256 校验，优先 GitHub API base64（国内可达）
- **安装**：`do shell script "/bin/bash install_update.command --update"` → 直接 root 覆盖
- **配置入口**：`shared/update_config.py`（仓库名、多链路 URL、超时、校验参数——换仓库只改这一个文件）
- **全 ASCII 铁律**：zip 根目录、URL 中的文件名、.command 文件名三者全部英文

### 分发四模式
| 模式 | 怎么用 |
|------|------|
| 本地 dev | python3 ui.py 直连达芬奇 |
| SMB 公司 | /Volumes/MYJC/06_Software/达芬奇脚本/ |
| 个人全量(67MB) | build_personal.sh → 含 Python pkg，新用户首次 |
| 个人增量(512KB) | build_personal.sh --update → 纯代码，点「⬆ 更新」用 |

### 发布（GitHub Release + ghproxy 加速）
```bash
bash build_personal.sh --update           # 出增量包
gh release create v2.2.x <zip> --title "v2.2.x"  # 上传 Release
# version.json 含 ghproxy/ghproxy CDN/直连 三路下载
git push --force  # 推 version.json + update_latest.zip
```

## macOS DMG 分发（2026-05-28 沉淀）

**问题**：PyInstaller 构建的 `.app` zip 发给别人后打不开。macOS Gatekeeper 检测到下载来源（`com.apple.quarantine`）→ 拒绝 ad-hoc 签名 app。

**Sequoia (15.x)**：右键→打开被砍，`spctl --master-disable` 被禁。

**方案**：DMG + 隔离清除脚本。详见 `macos-dmg-dist` skill。

**关键发现**：
- `xattr -d com.apple.quarantine App.app && open App.app` 是唯一可靠方式
- ARM64 only → Intel Mac 无法运行。用 `arch -x86_64 python3 -m PyInstaller` 构建 x86_64 可同时支持两者（Rosetta 只翻译 x86→ARM）
- PyInstaller 后必须 `codesign --force --deep --sign -` 重签
- `cp -R` 到被签名锁住的旧 app 会嵌套（220MB），必须先 `rm -rf`

**体积**：每个 app ~110MB（ffmpeg 54MB + Python 15MB + PIL/lxml 20MB + 其他 20MB）### 更新前端到端验证（2026-06-01 铁律）
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

### 一机一码 + 自助停用

- FC: `activate` 检查 key→FP→status，`max_devices=1` 强制唯一
- FC: `deactivate` 删 license + 重置 key 为 `sold`
- 插件：停用按钮试用期灰掉（`load_credential().get("is_trial")`）

### PYTHONUTF8=1

- 两 launcher（personal + SMB）都设 `PYTHONUTF8=1`
- `open()`/`zipfile` 默认 UTF-8，杜绝 ASCII 编码中文乱码

### 增量包优化

- build_personal.sh `--update` 模式跳过 pypdf（首次安装已含）
- 512KB → 179KB
- 出厂检验：zip 内版本号与源码不一致 → 硬拦截
- 版本 bump：用 `python3 tools/bump_version.py` 精确替换，不用 `sed`
- 发布后预热 ghproxy：`WARM_CDN=1 bash build_personal.sh --update`
