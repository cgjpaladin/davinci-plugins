# License 系统设计文档

> Superpowers Phase 2 — 设计方案，批准后进入实现计划

日期：2026-05-31 | 参考：豆包报告 v2 (HMAC-SHA256) + Downie 逆向分析

---

## 1. 产品策略

| 决策 | 结论 |
|------|------|
| 定价 | ¥99 个人买断 / ¥648 企业定制（价格存在云函数，可动态改） |
| 试用 | 30 天，从首次打开插件算。到期后强制购买（Downie 硬锁模式） |
| 多产品 | 一个 Key 解锁全部已购产品。后端返回 `{delivery_checker: true, ai_subtitle: false, ...}` |
| 企业版 | 第一阶段只做 SMB 部署（🅐）。Key 输入一次，写 SMB 共享目录 license.dat，全内网不连公网 |
| 退款 | 7 天无理由，写在发货100商品页 + 插件关于页面 |

## 2. 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                      用户侧                              │
│                                                          │
│  安装 → 首次打开 → 记录试用开始 (云函数) → 生成试用凭证    │
│                                                          │
│  日常: 本地3份备份交叉校验 → 月心跳 (30天宽限期)          │
│                                                          │
│  购买: 发货100 → 自动发Key → 插件输入 → 云函数激活        │
│         → 本地写凭证 → 重启即正式版                        │
│                                                          │
│  报错: 计数器 ⚠️N → 用户点发送 → 打包日志 → 飞书Bot        │
└─────────────────────────────────────────────────────────┘
                              ↕ HTTPS (纯 urllib)
┌─────────────────────────────────────────────────────────┐
│               腾讯云 SCF (apigw.tencentcs.com)            │
│                                                          │
│  HMAC-SHA256 签名 ←── 密钥在环境变量，客户端无            │
│  数据库: 激活码 + 设备指纹 + 授权记录 + 试用记录 + 价格     │
│  免费额度: 100万次/月 → 1000用户够用                       │
└─────────────────────────────────────────────────────────┘
```

### 安全原则
- **客户端不做任何验签**——所有校验在服务端完成（Downie 模式）
- 客户端仅检查本地凭证时间戳（离线宽限期）
- HMAC 密钥仅在云函数环境变量，泄露了云端改，不更新插件
- 三份备份交叉校验 + 自动恢复
- 月度心跳 + 连续失败 N 次自动吊销（Downie 同款 `XULicenseCheckFailCount`）

## 3. 加密方案

**HMAC-SHA256，纯标准库 `hmac` + `hashlib`。**

```python
# 服务端签名
sorted_items = sorted(payload.items(), key=lambda x: x[0])
sign_str = "&".join([f"{k}={quote(str(v), safe='')}" for k, v in sorted_items])
signature = hmac.new(HMAC_SECRET, sign_str.encode(), hashlib.sha256).hexdigest()

# 服务端验签（防时序攻击）
expected = hmac.new(HMAC_SECRET, sign_str.encode(), hashlib.sha256).hexdigest()
hmac.compare_digest(expected, received_signature)
```

### 凭证结构
```json
{
  "payload": {
    "activate_key": "DV-XXXX-XXXX-XXXX",
    "machine_fingerprint": "sha256 hex",
    "issue_time": 1717200000,
    "expire_time": 1717200001,
    "offline_grant_end": 1717200002,
    "nonce": "random hex",
    "platform": "macOS",
    "products": {"delivery_checker": true},
    "is_trial": false
  },
  "signature": "hmac hex string"
}
```

## 4. 激活码

| 决策 | 结论 |
|------|------|
| 格式 | `DV-XXXX-XXXX-XXXX`（16字符 hex，4组） |
| 管理 | 我（AI）写本地工具管理 keys.json，裁缝老师说人话操作 |
| 生成 | `tools/gen_keys.py` → 输出 CSV（导入发货100）+ keys.json |
| 赠送 | 在 keys.json 标记 `gifted_to` 字段 |
| 多产品 | 不区分——同一个 Key 对应 `products` 字段 |

## 5. 试用机制

- 首次打开 → 采集指纹 → 云函数记录 `trial_start` → 下发试用凭证（30天）
- 三路径存储：`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/license.dat` + 两备份
- 启动时交叉校验：一个被删了从其他恢复。三个全删 → 联网重试 → 云函数说「你试用过了」→ 不重开
- 试用到期 → 弹窗「试用已结束，请购买」→ 输入激活码

## 6. 离线宽限期

- 凭证含 `offline_grant_end = issue_time + 30天`
- 离线时只检查此时间戳
- 联网时云函数刷新 → 覆盖本地三份 → 宽限期顺延
- 超过宽限期 → 功能受限模式

## 7. 月度心跳

- 插件启动后延迟 5 分钟静默同步
- POST 本地凭证 + 最新指纹到云函数
- 云函数校验 → 重签新凭证 → 回传
- 连续 3 次失败 → `XULicenseCheckFailCount` → 自动吊销
- 频率：24 小时间隔

## 8. 设备绑定与迁移

- 激活码首次激活 → 绑定设备指纹（1:1）
- 换电脑/重装 → 旧指纹自动解绑（下次联网失效）
- 24 小时内最多 3 次迁移
- 企业版 Key 不限制迁移次数（`enterprise=true`）

## 9. 崩溃/报错上报

- 当前会话所有 `_action_log("❌ ...")` 计数
- UI 右下角「⚠️ N 个报错」+ 「📋 导出日志」按钮
- 用户点发送 → 打包 `~/.workbuddy/logs/` + 机器信息 → 飞书 Bot 发送

## 10. 企业版 (🅐 SMB)

- 同一安装包，Key 标记 `enterprise=true`
- 激活信息写入 SMB 共享目录 `license.dat`（位置可配）
- 所有机器启动时读同一个文件 → HMAC-SHA256 验签
- 不走公网、不月度心跳
- 后续企业类型（单机/混用）扩展时再加

## 11. 销售闭环

```
用户 → B站/微信看到 → 点链接 → 发货100页面
  → 微信/支付宝付 → 自动发 Key（短信/邮箱/站内信）
  → 插件输入 → 云函数校验 → 激活完成
```

- 主渠道：发货100（费率 1-3%）
- 备渠道：快发卡
- 手动赠送：裁缝老师说「送张三一个 Key」→ AI 标记 keys.json

## 12. 数据隐私

- 首次启动弹隐私说明：「本插件采集设备硬件标识用于激活验证，不上传任何隐私数据」
- 云函数只存：激活码状态、SHA256(设备指纹)、激活时间、试用开始时间
- 不存 email、IP、使用行为
- 不开源：插件代码闭源

## 13. 跨平台预留

- 机器指纹：macOS `IOPlatformUUID` + MAC + Volume UUID → Windows `MachineGuid` + MAC + 硬盘序列号
- 存储路径：macOS `~/Library/...` → Windows `%APPDATA%/...`
- 安装脚本：macOS `.command` → Windows `.bat`
- 云函数同一套代码，按 `platform` 字段区分

## 14. 安装包

- README.md（安装步骤）
- 隐私声明
- 开源组件声明文件（不含 GPL 代码）
- 飞书 Bot 回调地址（报错上报用）

## 15. 后续迭代（不做，仅预留）

| 项目 | 预留方式 |
|------|------|
| 促销 | 云函数 `price` 字段 |
| 多产品套装 | `products` 字段已支持多产品 |
| 强制更新 | version.json 已有 `force` 字段 |
| 售后 | 微信直接沟通 |

---

## 待建文件

| 文件 | 说明 |
|------|------|
| `shared/license.py` | 机器指纹采集 + 本地凭证读写 + HMAC 校验 + 网络请求封装 |
| `shared/key_manager.py` | 激活码批量生成 + keys.json 管理 |
| `cloud/activate.py` | 腾讯云 SCF 激活函数（HTTPS POST） |
| `cloud/verify.py` | 腾讯云 SCF 校验 + 心跳函数 |
| `交付自检工具/activate_ui.py` | 激活码输入 + 试用提示 UI |
| `tools/gen_keys.py` | 生成激活码工具 |
| `docs/商业/用户协议.md` | 隐私 + 退款 + 免责条款 |
