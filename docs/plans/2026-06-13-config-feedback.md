# 配置页激活/停用反馈优化

> 设计：窗口不自动关闭，结果页原地呈现 | 2026-06-13

## 修改文件

`交付自检工具/ui.py`

## 任务

### Task 1: 取消→关闭（基线改动）
- 行 1050 `cfg_cancel` 按钮 `Text` 从 `"取消"` 改为 `"关闭"`
- 行 1334 关闭回调保持 `lambda ev: config_disp.ExitLoop()` 不变
- **验证**：打开配置 → 点「关闭」→ 窗口正常退出

### Task 2: 激活成功残り页
- 行 1210-1218 的 `if ok:` 分支，在现有 `itm[...]` 写主窗口之后，**删掉** `config_dlg.Hide(); config_disp.ExitLoop()`
- 追加：
  ```python
  cfg["cfg_activation_1"].Visible = False
  cfg["cfg_activation_2"].Visible = False
  cfg["cfg_activation_3"].Visible = False
  cfg["cfg_save"].Visible = False
  cfg["cfg_hint"].Text = f"✅ 激活成功\n已绑定本机 | {code}\n永久有效"
  cfg["cfg_hint"]["StyleSheet"] = "color:rgb(30,160,80);font-size:14px;font-weight:bold"
  ```
- **验证**：输入码 → 激活成功 → 三格消失，绿色结果出现 → 点「关闭」退出 → 重启看「已激活 ✓」

### Task 3: 激活失败保持改写
- 行 1220-1223 的 `else:` 分支，将 `cfg["cfg_hint"]` 样式加入可选的颜色切换：
  ```python
  cfg["cfg_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
  cfg["cfg_hint"].Text = f"⚠ {msg}"
  ```
  确保从绿色/黄色恢复为错误红色
- **验证**：输错误码 → 红字错误 → 输入区保留 → 可重试 → 点「关闭」退出

### Task 4: 停用成功残り页
- 行 1346-1356 的 `if ok:` 分支，**删掉** `config_dlg.Hide(); config_disp.ExitLoop()`
- 追加：
  ```python
  cfg["cfg_deactivate_btn"].Visible = False
  cfg["cfg_hint"].Text = "🔓 已停用\n激活码已释放，可在其他设备激活\n本机恢复试用模式"
  cfg["cfg_hint"]["StyleSheet"] = "color:rgb(30,160,80);font-size:14px;font-weight:bold"
  ```
- **验证**：已激活状态 → 点停用 → 按钮消失，绿色结果 → 点「关闭」退出 → 主窗口显示试用

### Task 5: 停用失败保持改写
- 行 1358 失败分支，加样式重置：
  ```python
  cfg["cfg_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
  cfg["cfg_hint"].Text = f"⚠ {msg}"
  ```
- **验证**：未激活状态点停用 → 红字 → 窗口不关

### Task 6: 全链路冒烟
- 启动（试用）→ 配置：输入码 → 激活成功 → 关窗 → 重启 → 已激活
- 已激活 → 配置 → 停用成功 → 关窗 → 重启 → 试用
- 已激活 → 配置 → 停用 + 输入码 → 激活成功 → 关窗 → 重启 → 已激活
