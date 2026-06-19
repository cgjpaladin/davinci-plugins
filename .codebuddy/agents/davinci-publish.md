---
name: davinci-publish
description: 达芬奇插件发布全链路管理。触发词：版本号、bump版本、发布、灰度、扩量、全量发布、promote、回滚。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# 达芬奇插件工坊 — 插件发布管理

## 发布全链路

```
dev → bump版本 → channel prod → build_local → push SMB → 个人版构建 → 产品页更新
```

| 阶段 | 工具 | 说明 |
|------|------|------|
| bump版本 | `VERSION_BUMP=patch` | push_all.sh 自动传递 |
| channel | `./channel.sh prod` | dev→生产，否则 SMB 推送硬拦截 |
| build_local | `bash build_local.sh` | 本地验证 + launcher 部署 |
| push SMB | `GRAY_CHOICE=1 CONFIRM_PUSH=yes ./push_all.sh` | 推全公司 |
| 个人版全量 | `./build_personal.sh` | 产出 `交付自检工具_vX.Y.Z.zip`→桌面→裁缝老师传网盘 |
| 个人版增量 | `./build_personal.sh --update` | 产出 `update_latest.zip`→git push→jsDelivr CDN |
| 产品页 | 编辑 `docs/delivery/index.html` | 更新网盘链接+大小+提取码 |

## ⚠️ 发布铁律

1. **⏸️ 本地测完 → 展示 diff + 测试摘要 → 等裁缝老师说「推」** → 再 push_all。禁止未确认就推 SMB。
2. 推之前确认：本地版 `version_string()` 含有 `-dev` 后缀，SMB 不含。
3. `.env` 受 `--exclude` 保护，推完后验证 SMB `.env` 仍在。
4. **⏸️ promote 前展示灰度机器的验证结果 → 等裁缝老师说「全量」**。promote 不可逆。
5. **🚫 更新公告唯一来源：`交付自检工具/CHANGELOG.md`。**
   bump 版本后检查此文件是否有新版本条目。没有 → 不能发布，提示裁缝老师去写。有 → 从中读取内容写入 `version.json` 的 history。AI 永不自己写公告。
6. **⏸️ 公告内容必须和裁缝老师确认后再落地。** CHANGELOG.md → version.json → commit push 三步，中间必须有确认点。
7. **⏸️ 产品页（`docs/delivery/index.html`）更新后提醒裁缝老师检查线上。** GitHub Pages 自动部署，git push 即上线。
8. 全量包放桌面（`~/Desktop/交付自检工具_vX.Y.Z.zip`），裁缝老师传百度网盘。增量包 push 到 git repo（jsDelivr CDN）。
9. 百度网盘 zip 含 Windows `.exe` 必命中毒检 → build 时去掉 Win python installer。

## 分发避坑

| 坑 | 现象 | 解决 |
|----|------|------|
| GitHub Release 上传中文文件名 | `gh release create` 产出的文件名变成 `_.zip` → 下载 404 | 更新包固定 ASCII 名 `update_latest.zip` |
| 百度网盘下载文件夹 | 单个文件下载丢失 Unix `+x` 权限 → `.command` 双击无反应 | 分发单个 `.zip`，macOS Archive Utility 解压保留 `+x` |
| zip 时间戳非确定性 | 每次构建 SHA256 不同 → 构建时校验失效 | 不上传构建校验 SHA。发布后 curl 下载验证 |
| 删除 Release 旧资产 | 同名文件 `git release upload --clobber` 会留存旧资产 → CDN 可能路由到旧版 | `gh release delete-asset` 显式删旧文件 |

## 版本号规则

- **唯一真相源**：`config.py: __version__`
- 构建脚本自动读取版本号拼入文件名，不需要手动改
- `version.json` 需手动同步：version / urls / sha256 / history
- 同步时机：构建完→上传 GitHub→curl 下载验证 SHA→更新 version.json→推送

## 测试部署 — dd-mbp

开发中途改完代码，推到邓邓的 MBP（被借来当测试机）让裁缝老师测：

```bash
scp 交付自检工具/ui.py dd-mbp:'/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具/ui.py'
```

> dd-mbp 上 WORKBUDDY_PERSONAL=1，所以它能看到试用码激活/停用界面——这是本机 DEV 模式没有的。

## publish.sh 内部行为

`push_all.sh` 和 `build_local.sh` 都是 `publish.sh` 的壳。关键行为：

```bash
# auto-commit（line 46）—— 每次 push 自动提交当前改动
git -C "$_ROOT" commit --no-verify -m "${_STAGE}: $PRODUCT_NAME (from $_HASH)"

# SKIP_VERSION_BUMP=1 —— 跳过版本升级（紧急热修复等场景）
SKIP_VERSION_BUMP=1 bash push_all.sh

# GRAY_CHOICE=1/2/3 —— 非交互式灰度选择（CI/自动化场景）
GRAY_CHOICE=1 bash push_all.sh   # 灰度测试已确认 → 继续发布
GRAY_CHOICE=2 bash push_all.sh   # 跳过灰度 → 记录日志 → 强制发布
GRAY_CHOICE=3 bash push_all.sh   # 取消 → 退出（跟交互式选 3 一样）
```

**auto-commit 含义**：每次 push_all/build_local 会自动 `git commit --no-verify`。这意味着 push 后的 git log 就是发布历史——不需要手动 commit。

## 壳方案（2026-05-25）

**每个产品有一个永久壳 `shell.py`（~40行），部署到每台机器的 Fusion Scripts 目录后一次再也不更新。** 壳只做：找 Python → 读 deploy.json → 启动 SMB launcher + 看门狗。

以后更新流程：`dev → bump → build → SMB → 重启达芬奇`。不再碰 20 台机器的本地文件。

壳部署是一次性的：`cp SMB/shell.py → 本地Fusion目录`。

## 部署追踪（已废弃）

~~`tools/deploy_tracker.json`~~ — 壳方案后不再需要追踪 launcher 部署状态。每次更新只推 SMB。
~~`tools/deploy_one.sh`~~ — 壳一次性部署后不再需要。

---

## 版本号规则

```python
# config.py
__version__ = "1.9.0"        # 纯数字
__channel__ = "dev"           # dev / alpha / beta / rc1 / ""
```

- 本地：`__channel__ = "dev"` → 显示 `1.9.0-dev`
- SMB：push_all.sh 自动剥离 → 显示 `1.9.0`
- `version_string()` = `f"{__version__}{'-' + __channel__ if __channel__ else ''}"`

### 发布时升级版本

| 裁缝老师说 | VERSION_BUMP | 示例 |
|-----------|-------------|------|
| "推送补丁""推修复" | patch（默认） | 1.4.0 → 1.4.1 |
| "推送功能""推模块" | minor | 1.4.0 → 1.5.0 |
| "推送大版本" | major | 1.4.0 → 2.0.0 |

自动判断：小修→patch、新功能→minor、架构重构→major。`VERSION_BUMP=none` 不升级。

```bash
VERSION_BUMP=minor bash push_all.sh   # 推功能（minor 升级）
bash push_all.sh                       # 推补丁（默认 patch）
VERSION_BUMP=none bash push_all.sh    # 不升级
```

---

## 灰度发布

### gray.sh 命令

```bash
cd /Volumes/MYJC/06_Software/达芬奇脚本/<产品名>
./gray.sh add 101          # 加机器入灰度
./gray.sh remove 101       # 移出灰度
./gray.sh status           # 查看灰度状态
./gray.sh promote          # 灰度 → 全量
```

### 扩量流程

1. 部署壳（首次+一次性）：`ssh miniXXX 'cp SMB/shell.py → 本地'`
2. 加灰度：`gray.sh add <MID>`
3. 远程验证路由：`ssh miniXXX 'python3 <产品名>.py --dry-run'`
4. 请用户点菜单测试（唯一无法远程的步骤）
5. 远程调试排查 → 详见 `达芬奇调试` skill

### 安全兜底

- gray.json 不存在/格式错 → 全员走稳定版
- 灰度目录损坏 → 自动回稳定版
- promote 前必须确认（不可逆）

---

## 新机部署验证

新装机器或达芬奇更新后，逐项确认：

| # | 检查项 | 命令/方法 | 失败症状 |
|---|--------|-----------|----------|
| 1 | **External Scripting 权限** | Resolve → Preferences → System → External Scripting → Local | 所有插件黑屏、Launcher 报 `resolve is None` |
| 2 | Python 框架版在位 | `ls /Library/Frameworks/Python.framework/Versions/3.*/bin/python3` | 菜单不显示 .py 脚本 |
| 3 | SMB 挂载 | `ls /Volumes/MYJC/06_Software/` | Launcher 找不到 deploy.json |
| 4 | 壳文件在位 | `ls "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/"` | Workspace → Scripts 菜单空白 |

External Scripting 是最容易漏的一项——默认值是 Local，但达芬奇更新可能重置。排查「插件全挂」时第一个查这里。

## 全量与回滚

```bash
# 全量
cd /Volumes/MYJC/06_Software/达芬奇脚本/<产品名>
./gray.sh promote    # 备份→覆盖→清灰度

# 回滚（指定机器退出灰度）
./gray.sh remove <MID>
# 机器重启达芬奇后自动回稳定版
```

全量后 gray.json 自动清空，灰度目录移除。

---

## 发布安全网（2026-06-13 重构）

### 环境隔离锁

- `__channel__ = "dev"` = 开发（repo 默认态），`""` = 生产
- `channel.sh dev|prod` — 一键切换，写后校验
- `version_string()` = 纯版本号或 `X.Y.Z-dev`

### 四层硬拦截

| 操作 | 位置 | dev 行为 |
|------|------|---------|
| SMB 同步 | `publish_sync()` | 拒绝 |
| 灰度管理 | `gray.sh add/remove/promote` | 拒绝（status 放行） |
| 推全公司 | `publish_push_all()` | 拒绝 + `trap EXIT` 自动切回 dev |
| GitHub 发布 | `publish_release.sh` | 拒绝 + 版本一致性校验 + 历史保留 |

### 操作流程

```
裁缝老师说"发布"
  1. channel.sh prod              ← 唯一显式操作
  2. build → gray → push
  3. push_all 结束 → trap 自动切回 dev（崩溃/Ctrl+C 也触发）
  4. build_personal.sh 打包前去 channel → 个人版永不带 -dev
```

### 产品注册表

- `.precommit-products` — 一行一个产品目录名，`# 产品名` = 归档不扫描
- `pre-commit.sh` 启动双向校验：文件↔目录必须一致

---

## 关键命令速查

```bash
# 本地构建
bash build_local.sh                          # 验证不推 SMB

# 推 SMB + 升级版本
VERSION_BUMP=patch bash push_all.sh          # 补丁
VERSION_BUMP=minor bash push_all.sh          # 功能
VERSION_BUMP=major bash push_all.sh          # 大版本

# 灰度操作
cd /Volumes/MYJC/.../<产品名>
./gray.sh add 101
./gray.sh remove 101
./gray.sh status
./gray.sh promote

# 部署新机器
ssh miniXXX 'cp /Volumes/MYJC/.../shell.py → 本地' # 壳一次性部署

# 远程验证路由
ssh mini101 'python3 "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/<产品名>.py" --dry-run'
```

---

## GitHub 远程发布（个人版，2026-06-01 v2 更新）

### 发布流程（实战验证 2026-06-08）

```bash
# 1. 构建增量包
cd 交付自检工具_个人版 && rm -rf _build && bash build_personal.sh --update
# → _build/交付自检工具_更新包.zip（38 文件，~191KB）

# 2. 更新 version.json（version + sha256）
SHA=$(shasum -a 256 _build/交付自检工具_更新包.zip | awk '{print $1}')
# 手动编辑 version.json: version, urls, sha256, history

# 3. GitHub Release（unset GH_TOKEN 用 keyring auth 如果 PAT 无 repo 权限）
unset GH_TOKEN && gh release create v2.x.y _build/交付自检工具_更新包.zip \
  --repo cgjpaladin/davinci-plugins --title "v2.x.y" --notes "## v2.x.y\n\n📝 公告内容"
# 如果 GH_TOKEN 已有 repo 权限则不需 unset

# 4. 推送 version.json
git add version.json && git commit --no-verify -m "v2.x.y 发布" && git push origin main
```

### 认证注意事项

- `git remote` 必须 HTTPS（非 SSH）—— `https://github.com/cgjpaladin/davinci-plugins.git`
- `GH_TOKEN` 环境变量优先于 keyring
- `gh release create` 403 → 检查 GH_TOKEN 是否有 `repo` scope
- git push 以 `gh` 认证状态为准

### 发布铁律（v2.4.0 起）

1. **`bump_version.py` 精确替换**——不用 `sed`，写入后验证
2. **build_personal.sh 内置出厂检验**——zip 内版本号 ≠ 源码 → 硬拦截退出
3. **pre_deploy_check.sh 6 步全链路**——编译 + 构建 + 解压语法检查 + 核心文件 + 版本一致性
4. **release body = 更新公告**——用户点「⬆ 更新」弹窗显示的内容

### 更新公告模板

```markdown
## v2.x.y

📏 新功能名

| 条件 | 结果 | 说明 |
|------|:--:|------|
| ... | 🔴 | ... |
| ... | 🟢 | ... |
```

### download 链路（v2.5.7）

| 优先级 | 链路 | 说明 |
|:--:|------|------|
| 1 | GitHub Releases 直连 | `releases/download/vX.Y.Z/update_latest.zip` |
| 2 | jsDelivr CDN | `cdn.jsdelivr.net/gh/...`，国内可用 |

- 版本检查链路：`raw version.json(优先) → jsdelivr → ghproxy → GitHub API(兜底)`
- 下载链路超时：每条 60s，多链路自动回退

### 进度条本地测试

```bash
# 用慢速 HTTP 模拟远程下载（~27KB/s × 38MB ≈ 25秒）
python3 ~/Desktop/test_ui_progress.py
# → 达芬奇弹窗 → 点"开始下载" → 观察进度条是否逐帧刷新
```


### 增量包优化

- pypdf 从增量包移除（首次安装已含）
- Launcher `-B` 永不生成 pyc：根治缓存污染
- 增量包不含 Python 安装包，~191KB

### 个人版发布测试（必须在 dd-mbp 上验证）

本机是 DEV 模式，不触发更新链路。个人版测试机：

```bash
# 测试机：邓邓的 14 寸 MBP（ZT IP: 10.163.15.58）
ssh dd-mbp "hostname -s && whoami"
# → TTTTTdeMacBook-Pro / ttttt

# 验证更新检测
ssh dd-mbp "grep -E '更新|v2\.5|download|启动' ~/.workbuddy/logs/交付自检工具/ui_TTTTTdeMacBook-Pro.local_*.log | tail -5"

# 验证更新下载+安装
ssh dd-mbp "grep -E '下载|download|安装|完成|失败' ~/.workbuddy/logs/交付自检工具/ui_TTTTTdeMacBook-Pro.local_*.log | tail -10"
```

SSH 免密已配：`~/.ssh/id_ed25519_nopass`，SSH config → Host dd-mbp。

第二台测试机：ttdd（ZT 10.163.15.45，密码 1203）。

### 阿里云 FC 部署（2026-06-16 验证）

```bash
# 查看函数列表（FC v3 API）
aliyun fc GET /2023-03-30/functions

# 更新函数代码
cd /tmp/deploy_fc && cp cloud/license_fc.js . && zip -r code.zip license_fc.js
BODY_ZIP=$(base64 -i code.zip)
aliyun fc PUT /2023-03-30/functions/license-node --body "{\"code\":{\"zipFile\":\"$BODY_ZIP\"}}"

# 验证
curl -s -X POST 'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/license' \
  -H 'Content-Type: application/json' \
  -d '{"action":"init_trial","machine_fingerprint":"test_verify","version":"2.5.7"}'
```

**注意**：FC v3 API 路径 `/2023-03-30/functions`（不是 v2 的 `/2021-04-06/services`）。

### 分发避坑表（2026-06-16）

| 坑 | 表现 | 解法 |
|----|------|------|
| GitHub Release 中文文件名 | `交付自检工具_v2.5.7.zip` → `_` | 更新包固定 ASCII 名 `update_latest.zip` |
| 百度网盘下文件夹 | Unix `+x` 权限全丢 | 产出单个 .zip，macOS Archive Utility 解压保留权限 |
| macOS Gatekeeper | `安装.command` 被隔离无法执行 | `xattr -cr` 构建时清 quarantine |
| `_write_env.py` URL ≠ `license.py` 默认值 | 新用户走到破 FC | 全项目 grep 后统一（本次从 `license-yqvhkhvhgf` → `license-node-mtqaghwijy`） |
| zip 时间戳非确定性 | 每次构建 SHA256 不同 | 构建时不能校验 SHA，必须上传后用 curl 下载验证 |

### 安装脚本设计铁律（2026-06-16）

1. **先告知后执行**：终端显示变更清单 → 用户确认 → 输密码
2. **输出分流**：`exec 3>&1 >"$LOG" 2>&1`，终端仅看摘要，细节全进 `~/Library/Logs/小裁缝工具/`
3. **密码取消不报错**：`grep "User canceled"` → 静默 exit 0
4. **版本比较 3 分支**：`unzip -p` 读 zip 内版本 → 相同/升级/降级三弹窗
5. **External Scripting 自动启用**：`sed` 改 `config.dat`，DR 在跑时跳过并提醒
6. **osascript 换行**：必须 `$'...\n...'`（单引号不转义）
