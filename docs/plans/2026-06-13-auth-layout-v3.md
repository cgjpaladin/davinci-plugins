# 授权区重构 v3：三行固定布局 + 同位置变色

> 设计已确认 | 2026-06-13

## 核心原则

- **三行不跳**：永远占相同高度，只改文字/颜色/启用态
- **状态行合一**：行 1 兼做状态 + 错误 + 结果反馈
- **无 cfg_auth_hint**：删掉独立提示 Label

## 布局

```
▸ 授权管理

  [状态行]  ⏳ 剩余 18 天        ← cfg_auth_status（Label）
  [输入行]  ____ - ____ - ____   ← cfg_trial_code_grp（HGroup，3个Password LineEdit）
  [按钮行]  [激活] / [停用]       ← 两个 Button，互斥 Visibility

── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
```

## 控件 ID

| ID | 类型 | 说明 |
|----|------|------|
| cfg_auth_status | Label | 状态/错误/结果，一行兼用 |
| cfg_trial_code_1/2/3 | LineEdit | Password 模式，占位 XXXX |
| cfg_trial_code_grp | HGroup | 包三个输入框，统一设 Enabled |
| cfg_activate_btn | Button | "激活" |
| cfg_deactivate_btn | Button | "停用" |

删除本版中的：cfg_trial_status、cfg_auth_activated_label、cfg_auth_hint

## 状态表

### 试用（初始）
| 控件 | 值 | 样式 |
|------|-----|------|
| cfg_auth_status | "⏳ 试用剩余 N 天" | color:rgb(200,180,60);font-size:12px |
| cfg_trial_code_grp | Enabled=True, Text="" | — |
| cfg_activate_btn | Visible=True | — |
| cfg_deactivate_btn | Visible=False | — |

### 激活中
| 控件 | 值 | 样式 |
|------|-----|------|
| cfg_auth_status | "⏳ 正在连接服务器…" | color:rgb(220,160,40);font-size:12px |
| cfg_trial_code_grp | Enabled=False | — |
| cfg_activate_btn | Visible=False | — |
| cfg_deactivate_btn | Visible=False | — |

### 激活成功
| 控件 | 值 | 样式 |
|------|-----|------|
| cfg_auth_status | "✅ 已激活 · 永久授权" | color:rgb(80,200,100);font-size:13px |
| cfg_trial_code_grp | Enabled=False, Text="" | — |
| cfg_activate_btn | Visible=False | — |
| cfg_deactivate_btn | Visible=True | — |

### 激活失败
| 控件 | 值 | 样式 |
|------|-----|------|
| cfg_auth_status | "⚠ {msg}" | color:rgb(220,80,60);font-size:12px |
| cfg_trial_code_grp | Enabled=True | — |
| cfg_activate_btn | Visible=True | — |
| cfg_deactivate_btn | Visible=False | — |

### 停用中（同激活中）
### 停用成功（同试用，重新算天数）
### 停用失败
| 控件 | 值 | 样式 |
|------|-----|------|
| cfg_auth_status | "⚠ {msg}" | color:rgb(220,80,60);font-size:12px |
| cfg_deactivate_btn | Visible=True | — |

## 改动点

### 1. 删「配置」标题
body_widgets 首行 Label 删除。

### 2. 重写 _build_auth_section
创建上述 6 个控件（header + status + grp + 2 buttons），所有控件始终可见（按钮互斥除外）。

### 3. 重写 _do_activate
- 读 cfg_trial_code_1/2/3
- 校验 → 失败：cfg_auth_status 红字
- 连接中 → cfg_auth_status 黄字 + 禁用输入 + 隐藏按钮
- 成功 → cfg_auth_status 绿字 + 禁用输入 + 切换按钮
- 失败 → cfg_auth_status 红字 + 恢复输入 + 恢复按钮

### 4. 重写 _do_deactivate
- 连接中 → 隐藏按钮
- 成功 → cfg_auth_status 试剩余天数 + 启用输入 + 切换按钮
- 失败 → cfg_auth_status 红字 + 恢复按钮

### 5. 删旧代码
- 删除 _build_activation_code 和 _build_deactivate（已无引用）
- 删除 cfg_trial_status、cfg_auth_activated_label build 代码

### 6. 冒烟
- 试用 → 激活成功 → 停止 → 试用
- 失败重试（错误码）
