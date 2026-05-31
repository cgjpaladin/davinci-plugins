# License 系统实施计划

> Superpowers Phase 2 — 逐任务实现计划

日期：2026-05-31 | 设计文档：`docs/plans/2026-05-31-license-system-design.md`

---

## 任务依赖图

```
T1: 机器指纹采集          ─┐
T2: 本地凭证读写 + 3备份   ─┤
T3: HTTP 请求封装          ─┤
                            ├─→ T5: license.py 集成
T4: 激活码生成工具          ─┘
                            │
T6: 云函数 activate        ─┼─→ T9: 端到端测试
T7: 云函数 verify+心跳     ─┘
                            │
T8: 激活 UI                ─┘

T10: 报错上报
T11: 用户协议文档
```

---

## T1: 机器指纹采集

**目标**：`shared/license.py` 中实现 `get_machine_fingerprint()`

**测试**：
1. 调用两次返回同一值（稳定性）
2. 指纹是 64 字符 hex（SHA256 长度）
3. 在 M4 Mac mini 上测试采集 IOPlatformUUID + MAC + Volume UUID

**实现文件**：`shared/license.py`（新建）

**验收**：`python3 -c "from shared.license import get_machine_fingerprint; print(get_machine_fingerprint())"` 输出稳定的 64 字符 hex

---

## T2: 本地凭证读写 + 三备份

**目标**：`shared/license.py` 中实现 `save_credential()` / `load_credential()` / `cross_validate_and_repair()`

**测试**：
1. 写入后三路径都存在 `license.dat`
2. 删除一个文件后 → `cross_validate_and_repair()` 自动恢复
3. 删除全部三个 → 返回 None
4. 文件权限 `0o600` + macOS chflags hidden

**实现文件**：`shared/license.py` (续)

**验收**：手动删文件后重启脚本自动恢复

---

## T3: HTTP 请求封装

**目标**：`shared/license.py` 中实现 `post_to_backend(endpoint, data)`

**测试**：
1. 模拟云函数返回 → 正确解析 JSON
2. 超时 10s 后有重试逻辑（最多 2 次）
3. SSL context 正确（`_create_unverified_context`）

**实现文件**：`shared/license.py` (续)

**验收**：`curl` 模拟一个 HTTPS 200 返回 → 函数正确解析

---

## T4: 激活码生成工具

**目标**：`tools/gen_keys.py` + `shared/key_manager.py`

**测试**：
1. `python3 tools/gen_keys.py 10` → 生成 10 个 `DV-XXXX-XXXX-XXXX` 格式码
2. 输出 `keys.json` + CSV（发货100导入格式）
3. `--gift-to 张三` → 标记赠送
4. `--status` → 打印库存统计

**实现文件**：`tools/gen_keys.py` + `shared/key_manager.py`

**验收**：生成 100 个 Key → 检查格式 → 导入发货100后台 → 导出发货成功

---

## T5: license.py 完整集成

**目标**：把 T1-T3 组装成对外接口：

```python
from shared.license import (
    get_machine_fingerprint,      # → str
    init_trial,                   # → dict (向云函数请求试用)
    activate,                     # → dict (向云函数激活)
    verify_local,                 # → bool (离线校验宽限期)
    heartbeat,                    # → bool (月度心跳)
    save_credential,              # → None
    load_credential,             # → dict or None
)
```

**测试**：每个函数独立单元测试

**实现文件**：`shared/license.py`（完稿）

---

## T6: 云函数 activate

**目标**：`cloud/activate.py` → 腾讯云 SCF 可部署的函数

**功能**：
- POST 接收 `{action: "init_trial"|"activate"|"heartbeat", machine_fingerprint, activate_key?, license_token?}`
- HMAC-SHA256 签名验证
- 数据库表：`keys`（激活码状态）, `licenses`（设备绑定）, `trials`（试用记录）
- 返回签名后的凭证 JSON

**测试**：curl POST 模拟请求 → 验证返回的签名能用 HMAC 密钥验证

---

## T7: 云函数 verify + 心跳

**目标**：`cloud/verify.py` → 合并到同一云函数，按 `action` 字段分流

- `init_trial`：查 trial 表 → 新设备建记录 → 已试用过返回拒绝
- `activate`：查 key 表 → 绑定设备指纹 → 签发正式凭证
- `heartbeat`：验签 → 刷新 `offline_grant_end` → 重签
- 防重放：`nonce` 字段 + 5 分钟窗口

---

## T8: 激活 UI

**目标**：`交付自检工具/activate_ui.py` → 独立激活弹窗

**UI 元素**：
- 标题：激活 达芬奇交付自检工具
- 输入框：激活码（`DV-XXXX-XXXX-XXXX`）
- 按钮：激活
- 状态提示：激活成功 / 激活失败 / 试用第 X/30 天

**测试**：
1. 试用期内：右下角显示「试用第 X/30 天」
2. 试用到期：弹激活窗口，核心功能禁用
3. 输入正确 Key → 显示「激活成功！重启生效」
4. 输入错误 Key → 显示「激活码无效」

---

## T9: 端到端测试

**测试流程**：
1. 本地启动插件 → 检测到未激活 → 自动初始化试用
2. 检查三路径 `license.dat` 存在
3. 删除一个 → 重启 → 自动恢复
4. 删除三个 → 重启 → 云函数拒绝重新试用（已记录）
5. 输入真实 Key → 激活 → 凭证由试用变为正式
6. 断网 → 仍可用（离线宽限期检查）

---

## T10: 报错上报

**目标**：UI 右下角加报错计数器 + 发送按钮

**实现**：
- `_action_log` 中 `❌` 行计数
- 计数器显示：`⚠️ N 个报错`
- 点击 → 打包 `~/.workbuddy/logs/` + 机器信息 → POST 飞书 Bot

---

## T11: 用户协议文档

**目标**：`docs/商业/用户协议.md` + 安装包内 README

**内容**：隐私声明、退款政策、免责条款、开源组件声明

---

## 执行顺序

1. **T1 → T2 → T3 → T4** 可并行
2. **T5** 集成前三者
3. **T6 → T7** 可并行（云函数）
4. **T8** 依赖 T5 + T7
5. **T9** 端到端
6. **T10 → T11** 收尾
