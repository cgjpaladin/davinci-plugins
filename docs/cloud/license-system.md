# 阿里云 FC 许可证系统 — 端到端参考

> 裁缝老师的知识盲区补全手册。读完这篇就能自己管理 FC 函数。

## 太长了？30 秒速览

```
用户点「激活」→ 输入码 → Python 发 HTTPS 请求
  → 阿里云 FC 函数（Node.js，杭州）收到请求
  → 飞书多维表格查/写数据
  → 返回结果给 Python
  → Python 写本地凭证文件
```

4 个关键角色：
- **客户端**：`shared/license.py`（Python，跑在达芬奇子进程里）
- **FC 函数**：`cloud/license_fc.js`（Node.js，跑在阿里云杭州）
- **飞书表**：激活码表 + 试用指纹表（飞书多维表格 Base）
- **本地凭证**：`~/.config/dv_license/license.dat`（JSON 文件）

---

## 一、架构图

```
┌─────────────────────────────────────────────────┐
│                   用户电脑                        │
│  ┌──────────┐    ┌──────────────────────────┐   │
│  │ tkinter   │    │  license.py              │   │
│  │ 弹窗输入  │───→│  init_trial()            │   │
│  │ 激活码    │    │  activate()              │   │
│  └──────────┘    │  verify_activation()      │   │
│                  │  verify_local() (心跳)     │   │
│                  │  deactivate()             │   │
│                  └────────┬─────────────────┘   │
│                           │ HTTPS               │
│                  ┌────────▼─────────────────┐   │
│                  │  ~/.config/dv_license/   │   │
│                  │  license.dat (本地缓存)    │   │
│                  └──────────────────────────┘   │
└───────────────────────────┼─────────────────────┘
                            │
              ┌─────────────▼──────────────────────┐
              │        阿里云 FC (杭州)              │
              │  license-node-mtqaghwijy           │
              │  ┌────────────────────────────┐    │
              │  │  license_fc.js (Node.js)   │    │
              │  │                            │    │
              │  │  POST /license              │    │
              │  │  {"action":"activate",...}  │    │
              │  │  → handleActivate()        │    │
              │  │  → handleInitTrial()       │    │
              │  │  → handleVerifyStatus()    │    │
              │  │  → handleDeactivate()      │    │
              │  │  → handleHeartbeat()       │    │
              │  └────────────┬───────────────┘    │
              └───────────────┼────────────────────┘
                              │ 飞书 Open API
              ┌───────────────▼────────────────────┐
              │         飞书多维表格                  │
              │  ┌──────────────────────────────┐  │
              │  │  激活码表 (tbla9FSVEuuiayQH)  │  │
              │  │  激活码 | 状态 | 绑定指纹 | ... │  │
              │  ├──────────────────────────────┤  │
              │  │  试用表 (tblMAUMo8VQGPDZP)    │  │
              │  │  指纹 | 版本 | 达芬奇版本 | ...│  │
              │  └──────────────────────────────┘  │
              └────────────────────────────────────┘
```

---

## 二、FC 函数详情

### 基本信息

| 项目 | 值 |
|------|-----|
| 函数名 | `license-node` |
| 服务名 | `license-node-mtqaghwijy.cn-hangzhou` |
| 公开 URL | `https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run` |
| 运行时 | Node.js |
| 代码文件 | `cloud/license_fc.js`（本仓库） |
| 地域 | 杭州（cn-hangzhou） |

### 路由表

所有请求发到 `POST /license`，通过 body 中的 `action` 字段分发：

| action | 处理函数 | 输入的飞书表 | 说明 |
|--------|---------|:--:|------|
| `activate` | `handleActivate` | 激活码表 | 验证激活码 → 绑定指纹 → 返回 license_token |
| `init_trial` | `handleInitTrial` | 试用表 | 首次试用 → 新建记录（指纹+版本+达芬奇版本+macOS版本） |
| `verify_status` | `handleVerifyStatus` | 激活码表 | 查询激活码状态 |
| `deactivate` | `handleDeactivate` | 激活码表 | 解绑指纹，释放激活码 |
| `heartbeat` | `handleHeartbeat` | 试用表 | 更新版本号、达芬奇版本、最后活跃时间 |

### 环境变量（在阿里云控制台 → FC 函数 → 环境变量中配置）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_...` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | — |
| `BASE_TOKEN` | 飞书多维表格 token | `BRfGbDgaJa6ZYCsViuOcau2PnSe` |
| `TRIAL_TABLE_ID` | 试用指纹表 ID | `tblMAUMo8VQGPDZP` |
| `ACTIVATE_TABLE_ID` | 激活码表 ID | `tbla9FSVEuuiayQH` |
| `APPROVE_TABLE_ID` | 审批表 ID | — |

---

## 三、飞书 Base 表结构

### 激活码表（`tbla9FSVEuuiayQH`）

记录每个激活码的生命周期。

| 字段 | 类型 | 说明 |
|------|------|------|
| 激活码 | 文本 | `XXXX-XXXX-XXXX` |
| 状态 | 单选 | 可用 / 已激活 / 已停用 |
| 绑定指纹 | 文本 | SHA256 机器指纹 |
| 激活时间 | 日期 | — |
| 停用时间 | 日期 | — |
| 备注 | 文本 | — |

### 试用指纹表（`tblMAUMo8VQGPDZP`）

记录每台试用机器的信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| 机器指纹 | 文本 | SHA256，唯一标识一台机器 |
| 首次试用时间 | 日期 | — |
| 插件版本 | 文本 | 如 `2.5.7` |
| macOS版本 | 文本 | 如 `26.5.1` |
| 达芬奇版本 | 文本 | 如 `20.3.2`（2026-06-16 新增） |
| 最后活跃 | 时间戳 | 心跳更新，用于统计活跃用户 |

---

## 四、部署流程

### 何时需要部署

修改了 `cloud/license_fc.js` 之后（新增字段、修复 bug、加新路由等）。

### 部署命令

```bash
# 1. 打包
cd /tmp/deploy_fc
cp /Users/bryan/WorkBuddy/达芬奇插件工坊/cloud/license_fc.js .
zip -r code.zip license_fc.js

# 2. 上传（FC v3 API 路径）
BODY_ZIP=$(base64 -i code.zip)
aliyun fc PUT /2023-03-30/functions/license-node \
  --body "{\"code\":{\"zipFile\":\"$BODY_ZIP\"}}"

# 3. 验证
curl -s -X POST 'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/license' \
  -H 'Content-Type: application/json' \
  -d '{"action":"init_trial","machine_fingerprint":"test_verify","version":"2.5.7","os_version":"26.5.1","resolve_version":"20.3.2"}'
```

### RAM 用户权限

当前 CLI 使用的 RAM 用户：`power-application-user`（阿里云账号 `1698372966313504`），有 FC 读写权限（`AliyunFCFullAccess`）。

如果 CLI 连不上 FC：
```bash
# 验证身份
aliyun sts GetCallerIdentity

# 列出函数（确认有权限）
aliyun fc GET /2023-03-30/functions
```

---

## 五、客户端流程

### 5.1 首次试用（`init_trial`）

```
插件启动 → load_credential() → 无本地凭证
  → init_trial(fingerprint, version, os_version, resolve_version)
  → POST /license {"action":"init_trial", ...}
  → FC：addRecord(试用表)
  → 返回 trial_start_date (ordinal)
  → 写本地 license.dat
  → 显示"试用剩余 30 天"
```

如果 FC 返回 500 或网络不通：
- 回退到本地 30 天试用（纯本地时间计算）
- 试用表不收录（**所以必须保证 FC URL 正确**）

### 5.2 激活（`activate`）

```
用户点「激活」→ tkinter 三框弹窗
  → 格式化 XXXX-XXXX-XXXX
  → activate(key, fingerprint)
  → POST /license {"action":"activate", ...}
  → FC：查激活码表 → 验证状态 → 绑定指纹 → 返回 license_token
  → 写本地 license.dat（含签名）
  → 显示"已激活 ✓"
```

### 5.3 心跳（`verify_local`）

```
每次打开插件：
  → load_credential() → 读本地 license.dat
  → verify_local(fingerprint, version, os_version, resolve_version)
  → 发心跳 POST /license 更新最后活跃 + 版本号
  → 达芬奇版本/插件版本/macOS版本自动同步到飞书表
```

### 5.4 URL 配置

**3 个文件必须指向同一个正确 URL**：

| 文件 | 位置 | 用途 |
|------|------|------|
| `license.py` | 默认值 | 兜底。`install.command` 写入 `.env` 之前用这个 |
| `_write_env.py` | 写入 `.env` | 新用户安装后使用的 URL |
| `tools/gen_key.py` | 生成激活码 | 后台管理工具 |

2026-06-16 修复：`_write_env.py` 和 `gen_key.py` 曾指向 `license-yqvhkhvhgf`（已废弃），统一为 `license-node-mtqaghwijy`。

---

## 六、故障排查

### 6.1 "试用记录表没有新记录"

```bash
# 1. 查远程机器 .env
ssh machine "grep WB_LICENSE_URL '...交付自检工具/.env'"
# 期望：license-node-mtqaghwijy
# 如果是 license-yqvhkhvhgf → 错了，修掉

# 2. 测 FC 连通性（用真实指纹）
ssh machine "python3 -c \"
import json
with open('.config/dv_license/license.dat') as f:
    fp = json.load(f)['payload']['machine_fingerprint']
import subprocess
r = subprocess.run(['curl','-s','-X','POST',
    'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/license',
    '-H','Content-Type: application/json',
    '-d', json.dumps({'action':'init_trial','machine_fingerprint':fp})],
    capture_output=True, text=True)
print(r.stdout)
\""

# 3. 删凭证重试（强制重新 init_trial）
ssh machine "rm ~/.config/dv_license/license.dat"
# → 重开达芬奇插件 → 自动 init_trial
```

### 6.2 "激活失败"

```bash
# 查远程日志
ssh machine "grep -E '激活|activate|License' ~/.workbuddy/logs/交付自检工具/ui_*.log | tail -20"

# 手动测试（从远程）
ssh machine "curl -s -X POST '...fcapp.run/license' \
  -H 'Content-Type: application/json' \
  -d '{\"action\":\"verify_status\",\"activate_key\":\"DDDD-DDDD-0001\",\"machine_fingerprint\":\"...\"}'"
```

### 6.3 "FC 函数挂了"

```bash
# 看 FC 是否在线
curl -s 'https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run/' 
# 正常返回："License System OK"（或类似文本）
# 挂了：超时或 5xx

# 看阿里云日志
# 打开 https://fc.console.aliyun.com → 找到 license-node → 日志查询
```

### 6.4 "飞书表上没有达芬奇版本"

确认 3 件事：
1. FC 函数已部署最新 `license_fc.js`（含 `resolve_version` 字段）
2. 客户端 `license.py` 的 `_get_stats()` 有达芬奇版本检测
3. 飞书 Base 试用表有「达芬奇版本」列

---

## 七、活跃用户统计

每次打开插件 → `verify_local()` → 心跳 `POST /license` → FC 更新飞书表「最后活跃」字段。

要统计 DAU（日活）：去飞书 Base 试用表 → 筛选「最后活跃」= 今天。

---

## 八、版本历史

| 日期 | 改动 |
|------|------|
| 2026-06-10 | License v3 重构：试用/激活/停用三系统 |
| 2026-06-16 | +达芬奇版本字段；修复 `_write_env.py` URL（`license-yqvhkhvhgf` → `license-node-mtqaghwijy`）；FC v3 API 部署验证 |
