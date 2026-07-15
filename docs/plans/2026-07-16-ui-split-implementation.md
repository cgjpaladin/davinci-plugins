# ui.py 分解 — 逐模块实施计划

> Superpowers Phase 2：Writing Plans | 2026-07-16
> 每个任务 = 2-5 分钟 | 三步验证不可跳过

---

## 前置检查

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊
# 确认 Phase 1 已落地
grep "for f in.*交付自检工具.*\.py" 交付自检工具_个人版/build_personal.sh
# 应输出：for f in "$WS/交付自检工具"/*.py; do
```

---

## 任务 1：export_debug.py

**函数**：`_export_debug_package()` → `export_debug_package()`
**位置**：ui.py L2532-L2754（223行）
**调用者**：L2761 `dlg.On[BTN_ERR_SEND].Clicked = _on_err_report` → 链式调用

### 依赖分析

该函数访问了 10 个外部符号：

| 符号 | 来源 | 读写 | 处理方式 |
|------|------|:--:|---------|
| `_UI_ERROR_COUNT` | ui.py 全局 | RW | 参数：`error_ref = {"count": _UI_ERROR_COUNT}` mutable dict |
| `_action_log` | ui.py 模块级 | R | 参数：`log_fn` |
| `itm` | ui.py 模块级 dict | RW | 参数：`itm_dict` |
| `BTN_ERR_SEND` | ui.py 常量 | R | 参数：固定值，直接传 |
| `_DATA_DIR` | ui.py 模块级 | R | 参数：`data_dir` |
| `sys` | stdlib | R | 已在函数内作为局部变量引用，不改 |
| `version_string` | config.py | R | 参数：`version_fn` |
| `_trial_days_left` | ui.py/将来license_ui.py | R | 参数：`trial_days_fn` |
| `_load_api_keys` | ui.py 模块级 | R | 参数：`load_keys_fn` |
| `shared.*` | shared/ | R | 保持原路径 import，不动 |

### 实施

**Step 1：创建 `交付自检工具/export_debug.py`**

```python
# -*- coding: utf-8 -*-
"""导出诊断日志模块。被 ui.py 调用。"""

def export_debug_package(log_fn, data_dir, error_ref, itm_dict, btn_export,
                          trial_days_fn, load_keys_fn, version_fn):
    """打包完整诊断信息 → 用户选择目录 → zip → Finder 弹出"""
    import zipfile, subprocess, os, time, platform, socket, json
    import sys as _sys
    
    error_count = error_ref.get("count", 0)
    
    # ── 选目录 ──
    dest = ""
    if _sys.platform == "darwin":
        # ... [原代码，_action_log → log_fn, _UI_ERROR_COUNT → error_count, 
        #        itm[BTN_ERR_SEND] → itm_dict[btn_export], 
        #        _DATA_DIR → data_dir,
        #        _trial_days_left → trial_days_fn,
        #        _load_api_keys → load_keys_fn,
        #        version_string() → version_fn()]
    # ... [其余不变]
    
    # 函数末尾回写
    if success:
        error_ref["count"] = 0
    return None
```

**Step 2：修改 `交付自检工具/ui.py`**

```python
# 在 imports 区域末尾加：
from export_debug import export_debug_package

# 删除原 _export_debug_package() 函数（L2532-L2754）

# 修改调用处：
# 原：_export_debug_package()
# 改：export_debug_package(
#       _action_log, _DATA_DIR,
#       {"count": _UI_ERROR_COUNT}, itm, BTN_ERR_SEND,
#       _trial_days_left, _load_api_keys, version_string)
```

> **注意**：`error_ref` 是 mutable dict，函数内修改 `error_ref["count"] = 0` 会反映到调用方的后续引用。但原代码使用的是 `global _UI_ERROR_COUNT`，改成 dict 后需要在 ui.py 中把 `_UI_ERROR_COUNT` 的后续读取改为 `error_ref["count"]`。**此处有行为变化风险**——建议暂时保持 `from ui import _UI_ERROR_COUNT` 的直引用方式，等全部拆完再统一收敛。

**更安全的简化方案**：export_debug.py 直接 `from ui import _action_log, itm, BTN_ERR_SEND, _DATA_DIR, _UI_ERROR_COUNT, _trial_days_left, _load_api_keys`——完全不动函数体内部，只改位置。代价是子模块导入父模块，但 Python 允许且无循环依赖（ui.py 的 `from export_debug` 在模块末尾执行时全局变量已全部就绪）。

**推荐**：用简化方案——先拆后治。参数化放到 v3.0。

**验证**：
```bash
python3 -m py_compile export_debug.py ui.py
python3 tools/smoke_import.py
bash tools/pre-commit.sh
```

---

## 任务 2：license_ui.py

### 切出范围

1. `_trial_days_left()` — L652-656（5行，零依赖）
2. `_format_trial()` — 授权状态格式化
3. `_show_activation_dialog()` — 激活弹窗
4. `main()` 中的授权状态渲染（L3350-L3450 区域）

### 依赖分析

| 符号 | 来源 | 处理方式 |
|------|------|---------|
| `datetime` | stdlib | 函数内 import |
| `_action_log` | ui.py | `from ui import _action_log` |
| `itm` | ui.py | `from ui import itm` |
| `*_BTN_* / *_LBL_*` | ui.py 常量 | `from ui import BTN_ACTIVATE, LBL_LICENSE, ...` |
| `IS_PERSONAL` | config.py | 自己 import |
| `shared.license.*` | shared/ | 保持原路径 |

### 实施

同任务 1 模式——原样搬家，子模块 from ui import 全局变量。

**验证**：同任务 1。

---

## 任务 3：checks_runner.py

### 切出范围

1. `_start_check()` — 检查调度主函数
2. 门机制逻辑（`gates_ok` 计算、`_gate_labels`）
3. `_run_xx_check()` 包装函数们（thin wrappers）

> ⚠️ `_start_check()` 内部启动多线程，引用了 `_tree`（主窗口 Tree 控件）、`_lock_ui()`/`_unlock_ui()`。这些保留在 ui.py 并用参数传入。

### 依赖分析

| 符号 | 处理方式 |
|------|---------|
| `_tree` | 参数传入 |
| `_lock_ui` / `_unlock_ui` | 参数传入 |
| `_action_log` | `from ui import _action_log` |
| `CHECKS` / `itm` / `_*_CHK` 常量 | `from ui import ...` |

**验证**：同任务 1。

---

## 任务 4：config_dialog.py（最复杂）

### 切出范围

1. `CONFIG_SECTIONS` 注册表 + 所有 `_build_xxx` 函数
2. `_show_config_dialog()` 完整逻辑（含 `_do_save` 嵌套函数）
3. `_validate_config_sections()`
4. `_sec()`, `_sep()`, `_check_project_mask_reset()` 等辅助函数

### 依赖分析

config_dialog.py 需要自己 import `fusionscript_loader`（`bmd` 和 `fu`）。
`_do_save` 闭包引用了 `_api_values`、`_smb_paths_cache`、`_mask_ratio` 等——这些在函数内部定义，搬家后自然跟随。
需要从 ui.py 导入：`_action_log`、`IS_PERSONAL`（实际从 config.py 导入）、`SPACE_NORMAL`/`BTN_STYLE_SM` 等样式常量。

> ⚠️ `_trial_days_left` 已经搬到 license_ui.py（任务 2），config_dialog 中引用处改为 `from license_ui import trial_days_left`。

**验证**：同任务 1。**此步骤最危险——完成后立刻 git commit 独立提交。**

---

## 全量验证清单（四项全部完成时）

```bash
# 1. 编译
python3 -m py_compile ui.py config_dialog.py license_ui.py export_debug.py checks_runner.py

# 2. 模块级冒烟
python3 tools/smoke_import.py

# 3. 全 pre-commit
bash tools/pre-commit.sh

# 4. 个人版构建
cd 交付自检工具_个人版 && bash build_personal.sh --all

# 5. 手动 DaVinci 启动验证
#    裁缝老师：达芬奇 → 工作区 → 脚本 → 交付自检工具
#    测试：打开配置页、跑一次检查、导出日志、检查授权显示

# 6. 回滚
#    任一步失败：git checkout ui.py && rm -f config_dialog.py license_ui.py export_debug.py checks_runner.py
```

---

## 部署影响

- Phase 1 已确保 build_personal.sh 自动收录新文件 ✅
- 公司版 SMB：所有 .py 被 launcher.py 的 sys.path 自动发现 ✅
- 个人版 Win：同 data.zip，Win安装.bat 解压 ✅
- CDN delta：build_personal.sh --update 自动收录 ✅
