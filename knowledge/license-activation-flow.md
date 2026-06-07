# 许可证激活系统全链路

> 2026-06-08 摸底，距生产就绪差 3 步。

## 架构

```
卖家生成激活码(本地脚本) → INSERT cloud DB keys 表
         ↓ 微信发给用户
用户输入激活码 → 客户端 activate() → POST SCF → 验证+签名 → 返回 token
         ↓
客户端 save_credential(token) → heartbeat 确认 → UI 实时恢复按钮
```

## 文件清单

| 文件 | 角色 | 状态 |
|------|------|:--:|
| `shared/license.py` | 客户端（指纹采集/凭证读写/HTTP 请求） | ✅ |
| `cloud/license_server.py` | 腾讯云 SCF 后端（验证/签名/心跳） | ⚠️ 未部署 |
| `tools/license_test_server.py` | 本地测试服务器（端口 18999） | ✅ |

## 数据库表

### keys（激活码库存）

| 字段 | 类型 | 说明 |
|------|------|------|
| `activate_key` | TEXT PK | 格式 `XXXX-XXXX-XXXX` |
| `status` | TEXT | `available` → `sold` → `activated` |
| `max_devices` | INTEGER | 默认 1 |
| `created_at` | INTEGER | Unix timestamp |

### licenses（授权记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| `activate_key` | TEXT | 关联 keys 表 |
| `machine_fingerprint` | TEXT | 64 字符 SHA256 |
| `expire_time` | INTEGER | 正式版 10 年买断 |
| `is_trial` | BOOL | 试用=True |

## 激活码格式

`XXXX-XXXX-XXXX`（12 位大写字母数字，分 3 组）

生成规则：`uuid.uuid4().hex[:12].upper()` 插入 `-`，确保不重复。

## 客户端状态机

```
启动 → load_credential()
  ├─ 无凭证 → init_trial() → 30 天试用
  ├─ 有凭证 → verify_local() → 检查宽限期
  │   ├─ trial + 到期 → _ai_allowed=False → 按钮灰 + 提示购买
  │   ├─ trial + 有效 → _ai_allowed=True → 正常使用
  │   └─ 已激活 → _ai_allowed=True → 正常使用
  └─ 异常 → _ai_allowed=False

用户激活 → activate(code) → heartbeat → _ai_allowed=True → 按钮立即恢复
用户停用 → deactivate() → _ai_allowed=False → 按钮灰 + 提示重启试用
```

## 安全边界

- 客户端不做验签：`verify_local()` 只检查时间戳，不验证 HMAC 签名
- 签名校验在服务端心跳时完成
- 离线宽限期 30 天：网络断开仍可用，到期后必须联网心跳

## 待完成

1. 部署 `license_server.py` 到腾讯云 SCF
2. 写激活码生成脚本（`tools/gen_activation_codes.py`）
3. 补 `deactivate` 路由（`ROUTES` 缺此 handler）
4. 替换 SQLite 为 CloudBase（SCF 冷启动不保数据）
