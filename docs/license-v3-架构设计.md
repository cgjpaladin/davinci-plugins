# License v3 架构设计

> 沉淀：2026-06-13 全链路调试

## 状态机

```
           init_trial()
        ┌───────────────┐
 无凭据 →│  首次试用      │→ is_trial=true, trial_start_date=FC返回值
        └───────┬───────┘
                │ verify_local() 每次启动
                ▼
        ┌───────────────┐
        │  试用中        │→ _sync_trial_start 从 FC 拉最新 trial_start_date
        └───┬───┬───┬───┘
    activate│   │   │ 试用到期
            ▼   │   ▼
        ┌───┐   │ ┌──────────────┐
        │激活│   │ │试用剩余 0 天   │
        └─┬─┘   │ └──────────────┘
  deactivate│   │
            ▼   │
        ┌───┐   │
        │停用│───┘→ 回到试用（恢复原 trial_start_date）
        └───┘
            │ verify_activation() 每次启动
            ▼
        ┌───────────────┐
        │  已激活        │→ FC 返回 revoked → 清凭据写过期标记
        └───────────────┘
            │ FC 不通 > 30天
            ▼
        ┌───────────────┐
        │  吊销/过期     │→ trial_used=true, 永久无法重新试用
        └───────────────┘
```

## 核心函数

| 函数 | 调用时机 | 作用 |
|------|---------|------|
| `init_trial()` | 无凭据 | 创建试用凭据，FC 返回 `trial_date_ordinal` |
| `verify_local()` | 有凭据 + 试用 | 校验离線宽限期 + 同步最新 `trial_start_date` |
| `verify_activation()` | 有凭据 + 已激活 | 校验激活码是否仍有效（吊销检测） |
| `activate(key)` | 用户输入 | 联网激活，写 `is_trial=false` |
| `deactivate()` | 用户操作 | 释放激活码回「待激活」，恢复试用 |
| `_sync_trial_start()` | `verify_local` 内 | 从 FC 拉最新 `trial_start_date`，管理员调表即时生效 |

## 凭据字段

```python
{
  "payload": {
    "activate_key": "DDDD-DDDD-DDDD",  # 空=试用
    "machine_fingerprint": "sha256...",
    "issue_time": 1780675200,          # Unix 时间戳
    "expire_time": 1783267201,         # 试用=issue+30d, 激活=now+100y
    "offline_grant_end": 1781593733,   # 离線宽限截止（每次成功校验刷新为 now+3d）
    "trial_start_date": 739773,        # Python date.toordinal() 序数
    "trial_used": false,               # 吊销后 true，禁止重新试用
    "is_trial": true,                  # true=试用, false=已激活
    "_last_verify": 1781337000,        # 最后成功校验时间（吊销 30 天宽限用）
    "_force_sync": false,              # sync 失败标记，触下次删凭据重走 init_trial
  },
  "signature": "hmac..."              # FC 签发时有效，local_trial 为本地假签名
}
```

## 日期计算铁律

- **只用序数减法**：`30 - (date.today() - date.fromordinal(tsd)).days`
- **禁止 timestamp 整除 86400**：`fromordinal().timestamp()` 受本地时区偏移污染
- **FC 序数必须 +8h**：Alibaba FC 运行在 UTC，飞书表存 UTC+8 → `new Date(ms + 28800000)` 后算序数

## 网络调用

- **全部走 curl 子进程**：`subprocess.run(["curl", "-s", "--connect-timeout", "10", ...])`
- **禁止 urllib.request**：DaVinci 子进程 SSL 沙箱限制即使 `_create_unverified_context()` 也失败
- **retry=3, timeout=10s**：覆盖 DaVinci 进程冷启动

## 飞书表结构

### `tblMAUMo8VQGPDZP`（试用记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| 机器指纹 | 文本 | SHA256，唯一索引 |
| 首次试用时间 | 日期 | Feishu 存 UTC+8 日期 |

### `tbla9FSVEuuiayQH`（激活码表）

| 字段 | 类型 | 说明 |
|------|------|------|
| 激活码 | 文本 | XXXX-XXXX-XXXX 格式 |
| 状态 | 单选 | 待激活/已激活/待售 |
| 机器指纹 | 文本 | 激活后填入 |
| 激活时间 | 日期 | 首次激活时间 |
