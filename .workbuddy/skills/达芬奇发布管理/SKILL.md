---
name: davinci-publish
description: 达芬奇插件发布全链路管理。触发词：版本号、bump版本、发布、灰度、扩量、全量发布、promote、回滚。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
---
# 达芬奇插件工坊 — 插件发布管理

## 一、通用发布规则（所有插件）

### 全链路

```
dev → bump版本 → channel prod → build_local → push SMB → 产品分发
```

| 阶段 | 工具 | 说明 |
|------|------|------|
| bump版本 | `VERSION_BUMP=patch`（默认） | push_all.sh 自动传递 |
| channel | `./channel.sh prod` | dev→生产，SMB 推送硬拦截 |
| build_local | `bash build_local.sh` | 本地验证 + launcher 部署 |
| push SMB | `push_all.sh` | 灰度→全量，详见下方灰度流程 |
| 产品分发 | 飞书文档（人工）/ CDN（自动）/ Agent | 详见 二、交付自检特有 |

### 版本号

```python
# config.py —— 唯一真相源
__version__ = "2.5.11"        # 纯 semver
__channel__ = "dev"            # dev=""为生产，dev 绝不碰 SMB
```

- 本地：`__channel__ = "dev"` → 显示 `2.5.11-dev`
- SMB：push_all.sh 剥离 channel → 显示 `2.5.11`
- `version_string()` = `f"{__version__}{'-' + __channel__ if __channel__ else ''}"`

#### bump 升级

| 裁缝老师说 | VERSION_BUMP | 示例 |
|-----------|-------------|------|
| "推送补丁""推修复" | patch（默认） | 2.5.11 → 2.5.12 |
| "推送功能""推模块" | minor | 2.5.11 → 2.6.0 |
| "推送大版本" | major | 2.5.11 → 3.0.0 |

`VERSION_BUMP=none` 不升级。

```bash
VERSION_BUMP=minor bash push_all.sh   # 推功能
bash push_all.sh                       # 推补丁（默认）
VERSION_BUMP=none bash push_all.sh    # 不升级
```

### 环境隔离（四层硬拦截）

| 操作 | 位置 | dev 行为 |
|------|------|---------|
| SMB 同步 | `publish_sync()` | 拒绝 |
| 灰度管理 | `gray.sh add/remove/promote` | 拒绝（status 放行） |
| 推全公司 | `publish_push_all()` | 拒绝 + `trap EXIT` 自动切回 dev |
| GitHub 发布 | `publish_release.sh` | 拒绝 + 版本一致性校验 |

操作流程：`channel.sh prod` → build → gray → push → trap 自动切回 dev。

### 产品注册表

- `.precommit-products` — 一行一个产品目录名，`# 产品名` = 归档不扫描
- `pre-commit.sh` 启动双向校验：文件↔目录必须一致

### 灰度发布

```bash
cd /Volumes/MYJC/06_Software/达芬奇脚本/<产品名>
./gray.sh add 101          # 加机器入灰度
./gray.sh remove 101       # 移出灰度
./gray.sh status           # 查看灰度状态
./gray.sh promote          # 灰度 → 全量（不可逆）
```

灰度机器重启达芬奇走灰度代码，其余走稳定版。promote 后 gray.json 清空。

#### 扩量流程

1. 壳一次性部署：`ssh miniXXX 'cp SMB/shell.py → 本地Fusion目录'`
2. 加灰度：`gray.sh add <MID>`
3. 远程验证路由：`ssh miniXXX 'python3 <产品名>.py --dry-run'`
4. 用户点菜单测试（唯一无法远程的步骤）
5. 调试 → 详见 `插件排错诊断` skill

### 新机验证

| # | 检查项 | 失败症状 |
|---|--------|----------|
| 1 | External Scripting = Local | 所有插件黑屏 |
| 2 | Python 框架版在位 | 菜单不显示 .py 脚本 |
| 3 | SMB 挂载 `/Volumes/MYJC/` | Launcher 找不到 deploy.json |
| 4 | 壳文件在位（Fusion Scripts/Edit/达芬奇插件工坊/） | 菜单空白 |

### publish.sh 内部行为

`push_all.sh` 和 `build_local.sh` 都是 `publish.sh` 的壳：

```bash
# auto-commit：每次 push 自动提交（git log = 发布历史）
git -C "$_ROOT" commit --no-verify -m "${_STAGE}: $PRODUCT_NAME (from $_HASH)"

# SKIP_VERSION_BUMP=1：跳过版本升级（紧急热修复）
SKIP_VERSION_BUMP=1 bash push_all.sh

# GRAY_CHOICE=1/2/3：非交互式灰度（CI/自动化）
GRAY_CHOICE=1 bash push_all.sh   # 灰度已确认 → 继续
GRAY_CHOICE=2 bash push_all.sh   # 跳过灰度（强制）
GRAY_CHOICE=3 bash push_all.sh   # 取消（等同交互选 3）
```

### ⚠️ 发布铁律

1. **⏸️ 本地测完 → 展示 diff + 测试摘要 → 等裁缝老师说「推」**。禁止未确认推 SMB。
2. 推前确认：本地版带 `-dev`，SMB 不带。
3. `.env` 受 `--exclude` 保护，推完验证 SMB 端仍在。
4. **⏸️ promote 前展示灰度验证结果 → 等裁缝老师说「全量」**。promote 不可逆。
5. **🚫 更新公告唯一来源：`交付自检工具/CHANGELOG.md`。** bump 后无新版本条目 → 不能发布。AI 不代写公告。
6. **⏸️ 公告内容确认后落地。** CHANGELOG.md → version.json → commit push，三步必须有确认点。
7. SMB 推完后通知用户「关闭插件重开」——插件不热加载 SMB 代码。
8. `.env` AK/密钥更换后先本地全链路验证再推 SMB。通过才禁旧凭证。

### 壳方案

每个产品一个永久壳 `shell.py`（~40行），部署到每台机器 Fusion Scripts 目录后永不更新。壳功能：找 Python → 读 deploy.json → 启动 SMB launcher + 看门狗。更新流程：`dev → bump → build → SMB → 重启达芬奇`，不再碰 20 台本地文件。

---

## 二、交付自检特有

> 以下为交付自检工具的专属分发和构建流程。其他插件仅有 SMB 分发（通用规则已覆盖），无需个人版构建。

### 分发渠道

| 渠道 | 内容 | 安装方式 | 受众 |
|------|------|---------|------|
| 飞书文档 `T5D1d...an2g` | 95MB 全量 ZIP | 人类双击安装脚本 | 粉丝（唯一入口） |
| GitHub CDN | `update_latest.zip` ~550KB | 插件内「检查更新」 | 已装用户 |
| SMB | 源码同步 | 自动拉取 | 公司 20 台 |
| Agent | zip → AI 代装 | `install_agent.py` | AI agent 用户 |

裁缝老师手动上传全量 ZIP 到飞书文档。AI 不碰文档上传。百度网盘已放弃（可执行文件百审不过）。

### 构建

```bash
# 个人版全量（95MB ZIP，放桌面，裁缝老师传飞书）
cd 交付自检工具_个人版 && bash build_personal.sh

# 增量包（update_latest.zip → git push → CDN）
cd 交付自检工具_个人版 && bash build_personal.sh --update

# 版本号同步（先写 CHANGELOG.md → 再同步 version.json）
cd .. && cp 交付自检工具_个人版/_build/update_latest.zip .
SHA=$(shasum -a 256 update_latest.zip | awk '{print $1}')
# 手动更新 version.json: version, sha256, history（从 CHANGELOG.md 取公告）
git add version.json && git commit --no-verify -m "vX.Y.Z 发布" && git push origin main
```

- `build_personal.sh` 打包前自动去 channel，永不带 `-dev`
- 增量包不含 Python 安装器，仅代码文件
- `version.json` → `update_config.py` 多链路回退：jsDelivr CDN → ghproxy → GitHub raw → GitHub API

### Agent 安装

`install_agent.py`（`交付自检工具/` 源码目录，构建时随产品打包）：
1. 用户把 zip 丢给 AI → AI 解压 → 跑 `python install_agent.py`
2. 脚本输出 JSON 行 → 需要密码时输出 `need_sudo`/`need_admin`
3. AI 问用户要密码 → `--continue` 续装
4. 断点续装：状态文件 `~/.delivery_checker_install_state.json`
5. 全流程 AI 最多向用户要一次密码

### 打包规范

- 单 zip 全平台通用，`data.zip` 内含 macOS/Windows Python 安装器
- `先读我.txt`：人类看上半，AI agent 看 `# AGENT SECTION` 下半
- 产品文件（`install_agent.py`、`install.command` 等）放在 `交付自检工具/` 源码目录

### FC 部署

```bash
# 更新 FC 代码
cd /tmp/deploy_fc && cp cloud/license_fc.js . && zip -r code.zip license_fc.js
BODY_ZIP=$(base64 -i code.zip)
aliyun fc PUT /2023-03-30/functions/license-node --body "{\"code\":{\"zipFile\":\"$BODY_ZIP\"}}"

# 验证
curl -s -X POST 'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/license' \
  -H 'Content-Type: application/json' \
  -d '{"action":"init_trial","machine_fingerprint":"test","version":"2.5.11"}'
```

FC v3 API 路径 `/2023-03-30/functions`（非 v2 的 `/2021-04-06/services`）。

### 分发避坑

| 坑 | 现象 | 解决 |
|----|------|------|
| GitHub Release 中文文件名 | `交付自检工具_v2.5.7.zip` → `_` | 固定 ASCII 名 `update_latest.zip` |
| 百度网盘下文件夹 | Unix `+x` 权限全丢 | 产出单个 .zip |
| macOS Gatekeeper | `.command` 被隔离 | `xattr -cr` 构建时清 quarantine |
| zip 时间戳非确定性 | 每次 SHA256 不同 | 构建时不校验，发布后 curl 下载验证 |
| `_write_env.py` URL ≠ `license.py` 默认值 | 新用户走到破 FC（历史：`license-yqvhkhvhgf`→`license-node-mtqaghwijy`） | 全项目 grep 统一 FC URL |
| gh release 同名旧资产 | CDN 路由到旧版 | `gh release delete-asset` 显式删 |

### 安装脚本铁律

1. **先告知后执行**：终端显示变更清单 → 用户确认 → 输密码
2. **输出分流**：`exec 3>&1 >"$LOG" 2>&1`，终端仅摘要，细节进 `~/Library/Logs/小裁缝工具/`
3. **密码取消不报错**：`grep "User canceled"` → 静默 exit 0
4. **版本比较 3 分支**：`unzip -p` 读 zip 内版本 → 相同/升级/降级三弹窗

### git push 前置检查

推送前强制确认 `git branch --show-current` = `main`，不在 main 分支则拒绝。CDN 更新依赖 main 分支 push，推错分支 = 白干。
5. **External Scripting 自动启用**：`sed` 改 `config.dat`，DR 在跑时跳过
6. **osascript 换行**：必须 `$'...\n...'`（单引号不转义）

### 测试

本机 DEV 模式不触发更新链路。个人版测试机：**dd-mbp**（邓邓的 14 寸 MBP，ZT 10.163.15.58，SSH 免密）、**ttdd**（ZT 10.163.15.45）。

```bash
# 快速推代码到测试机
scp 交付自检工具/ui.py dd-mbp:'/Library/Application Support/.../交付自检工具/ui.py'

# 验证更新
ssh dd-mbp "grep '更新\|download\|完成' ~/.workbuddy/logs/交付自检工具/ui_*.log | tail -5"
```

---

## 关键命令速查

```bash
# 本地构建
bash build_local.sh

# 推 SMB + 升级版本
VERSION_BUMP=patch bash push_all.sh       # 补丁
VERSION_BUMP=minor bash push_all.sh       # 功能
VERSION_BUMP=major bash push_all.sh       # 大版本

# 灰度
cd /Volumes/MYJC/.../<产品名>
./gray.sh add 101 / remove 101 / status / promote

# 个人版构建（交付自检）
cd 交付自检工具_个人版
bash build_personal.sh                    # 全量 ZIP
bash build_personal.sh --update           # 增量包
```
