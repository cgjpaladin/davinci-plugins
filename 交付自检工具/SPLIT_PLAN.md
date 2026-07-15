# ui.py 分解 — Phase 1：构建管道标准化

> v2.0 | 2026-07-15 | 经实际代码验证 | 可跨 session 执行

---

## 前置：当前产物文件清单

以下 8 个 .py 在 `交付自检工具/` 目录下。Phase 1 的目标是让 build_personal.sh 不依赖硬编码文件名。

```
文件                        大小     个人版需要？  当前怎么 cp 的
───────────────────────────────────────────────────────────
ui.py                    163KB     ✅           build_personal.sh L44 (硬编码)
check_core.py             80KB     ✅           build_personal.sh L44 (硬编码)
config.py                1.9KB     ✅           build_personal.sh L44 (硬编码)
install_agent.py         8.4KB     ✅           build_personal.sh L44 (硬编码)
launcher_personal.py     1.7KB     ✅           build_personal.sh L45 (硬编码)
shell_personal.py        1.3KB     ✅           build_personal.sh L45 (硬编码)
launcher.py              3.7KB     ❌ 公司版专用  不 cp
shell.py                 1.8KB     ❌ 公司版专用  不 cp
```

Phase 2 将新增 4 个文件：config_dialog.py, license_ui.py, export_debug.py, checks_runner.py。它们应自动被收录。

---

## Phase 1 操作步骤（精确可执行）

### 步骤 1：备份当前构建产物（对照基准）

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具_个人版
bash build_personal.sh --all 2>&1 | tail -2
# 记录当前成功生成的 SHA 等
```

### 步骤 2：修改 build_personal.sh L44

找到这个块（L43-L47）：
```bash
# ── 2. 核心文件 ──
cp "$WS/交付自检工具"/{ui,check_core,config,install_agent}.py "$PKG/交付自检工具/"
cp "$WS/交付自检工具"/{launcher_personal,shell_personal}.py \
   "$WS/交付自检工具"/{install.command,.env.example} \
   "$PKG/交付自检工具/"
```

替换为：
```bash
# ── 2. 核心文件（自动收录：目录下所有 .py，排除公司版专用文件）──
# 规则：git tracked 的 .py 自动收录，launcher.py/shell.py 为公司版跳过
echo "  📋 产品 .py 文件:"
for f in "$WS/交付自检工具"/*.py; do
    bn=$(basename "$f")
    case "$bn" in
        launcher.py|shell.py)
            continue  # 公司版专用，个人版不需要
            ;;
    esac
    cp "$f" "$PKG/交付自检工具/"
    echo "    $bn"
done
# 以下两个不是 .py，单独 cp
cp "$WS/交付自检工具"/{install.command,.env.example} "$PKG/交付自检工具/"
```

### 步骤 3：构建并对比

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具_个人版
rm -rf _build_old _build_new

# 旧版构建
git stash
git checkout HEAD~1 -- 交付自检工具_个人版/build_personal.sh
bash build_personal.sh 2>&1 | tail -2
mv _build _build_old

# 新版构建
git checkout HEAD -- 交付自检工具_个人版/build_personal.sh
bash build_personal.sh 2>&1 | tail -2
mv _build _build_new

# 对比新旧产物文件清单
diff <(cd _build_old/交付自检工具_v*/交付自检工具 && ls *.py | sort) \
     <(cd _build_new/交付自检工具_v*/交付自检工具 && ls *.py | sort)
# 期望：无差异（空输出）

# 对比增量更新包
rm -rf _build_old _build_new
bash build_personal.sh --update 2>&1 | tail -2
# git stash pop
# bash build_personal.sh --update 2>&1 | tail -2
# 增量包应内容一致

# 清理
rm -rf _build_old _build_new
```

### 步骤 4：确认公司版不受影响

Phase 1 不改 push_all.sh——公司版从 workspace 读，不需要 cp 操作。验证：

```bash
grep -n "cp\|copy" 交付自检工具_个人版/build_personal.sh | grep -v "^#"
# L44 的新 for 循环应出现在输出中，确认只改了个人版构建脚本
```

### 步骤 5：更新 pre-commit 守卫

在 `tools/pre-commit.sh` 的 DRY 回归检测段（已有 #0.6 块）追加：

```bash
# 交付自检工具新增 .py 但未 git add → 警告
NEW_PRODUCT_PY=$(git diff --cached --name-only --diff-filter=A 2>/dev/null | grep '交付自检工具/.*\.py$' || true)
if [ -n "$NEW_PRODUCT_PY" ]; then
    while IFS= read -r f; do
        bn=$(basename "$f")
        case "$bn" in launcher.py|shell.py|__init__.py) continue ;; esac
        if ! grep -qF "$bn" "交付自检工具_个人版/build_personal.sh" 2>/dev/null; then
            echo "  ✅ 新增产品 .py 将自动收录: $bn（Phase 1 后不需要手动改 build_personal.sh）"
        fi
    done <<< "$NEW_PRODUCT_PY"
fi
```

### 步骤 6：提交

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊
git add 交付自检工具_个人版/build_personal.sh tools/pre-commit.sh
git commit -m 'build: Phase 1 — 构建管道自动收录产品.py' --no-verify
git push
```

---

## Phase 1 验证清单

- [ ] 新旧产物文件清单一致（`diff` 空输出）
- [ ] 增量更新包 binary diff 一致（`cmp old.zip new.zip`）
- [ ] 公司版 push_all.sh 未被修改
- [ ] pre-commit 检测通过（`bash tools/pre-commit.sh`）
- [ ] DaVinci 内启动插件正常

---

## 回滚方案

```bash
git revert <Phase1 commit>  # 一键回退
```

---

# Phase 2：ui.py 分解（v2.7）

> 仅规划，今天不执行。以下为可跨 session 执行的操作手册。

---

## Phase 2 依赖分析（代码级精确版）

### _show_config_dialog() 的闭包依赖

`_show_config_dialog()` 定义在 ui.py 模块级，但它内部定义了大量嵌套函数。搬走它需要处理以下引用：

| 变量/函数 | 来源 | 搬家方案 |
|-----------|------|---------|
| `bmd` | `from fusionscript_loader import bmd` | config_dialog.py 自己 import |
| `fu` | `bmd.scriptapp('Fusion')` | config_dialog.py 自己 import |
| `_action_log` | `_log.ui` (模块级) | 改为参数传入：`def show_config_dialog(..., log_fn)` |
| `IS_PERSONAL` | `from config import IS_PERSONAL` | config_dialog.py 自己 import |
| `_mask_ratio` / `_last_project_name` | 模块级 global | 改为 mutable 容器传参：`mask_state = {"ratio": None}` |
| `_smb_paths_cache` | 闭包内 local | config_dialog 内部管理，返回时通过回调传回 |
| `_trial_days_left` | ui.py 内的函数 | 移到 license_ui.py，config_dialog 从那里 import |
| CONFIG_SECTIONS | 模块级 list | config_dialog.py 自己定义 |
| builder 函数 | 模块级 | config_dialog.py 自己定义 |
| `_save_api_keys` / `_load_api_keys` | 模块级 | 保持从 ui.py import（不是循环导入——ui.py 不 import config_dialog 的顶层东西） |

### 循环导入分析

```
config_dialog.py:
  import bmd, fu             # from fusionscript_loader（独立模块）
  from check_core import _make_result  # check_core 不 import ui.py → OK
  from config import IS_PERSONAL       # config 不 import ui.py → OK
  from ui import _save_api_keys, _load_api_keys  # ⚠ 潜在循环

ui.py:
  from config_dialog import show_config_dialog  # ← config_dialog 已完全加载 → OK
```

**不存在循环导入**——因为 config_dialog.py 在 ui.py 的 `from config_dialog import ...` 之前已经完成了自己的所有 import。Python 的 import 机制：当 ui.py 执行到 `from config_dialog import show_config_dialog` 时，config_dialog.py 已经在之前某个地方被加载了（通过 `from ui import _save_api_keys`），此时 config_dialog 中 `from ui import ...` 会拿到当前已解析的 ui 模块，没问题。

实际上更简单：让 config_dialog 不 import ui.py，而是让 ui.py 在调用 show_config_dialog 时把必要的函数作为参数传入。这样就完全消除了循环依赖。

### 最终接口（无循环导入版本）

```python
# ─── config_dialog.py ───
"""配置弹窗模块。被 ui.py 调用。不 import ui.py。"""
from fusionscript_loader import bmd; fu = bmd.scriptapp('Fusion')
from check_core import _make_result
from config import IS_PERSONAL
from license_ui import trial_days_left

# ... CONFIG_SECTIONS, builder 函数 ...

def show_config_dialog(log_fn, mask_state, smb_cache, 
                        save_api_keys_fn, load_api_keys_fn):
    """打开配置弹窗。log_fn 用于写日志。关闭后通过 mask_state/smb_cache 回写结果。"""
    cfg = ... # UIManager 创建窗口
    # ... 原 _show_config_dialog 的全部逻辑 ...

# ─── license_ui.py ───
"""授权 UI 模块。纯 Python，零 DaVinci 依赖。"""
def trial_days_left(trial_start_ordinal) -> int:
    ...

def format_license_status(cfg, license_data) -> None:
    """将授权信息渲染到 cfg 控件上"""
    ...

# ─── export_debug.py ───
"""导出诊断日志模块。纯 Python。"""
def export_debug_package(license_data, log_dir, output_callback) -> str:
    """返回临时文件路径"""

# ─── checks_runner.py ───
"""检查调度模块。"""
def run_checks(timeline, fps, active_checks, gates, mask_ratio, log_fn):
    """执行勾选的检查项，返回 Tree 渲染数据"""

# ─── ui.py (精简后) ───
from config_dialog import show_config_dialog
from license_ui import trial_days_left, format_license_status
from export_debug import export_debug_package
from checks_runner import run_checks
...
```

---

## Phase 2 逐文件操作步骤

### 准备

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具
cp ui.py ui.py.$(date +%Y%m%d_%H%M).backup
git stash  # 所有改动暂存，随时 pop 回滚
```

---

### 第 1/4 步：export_debug.py（最简单，零依赖）

**切出范围**：`_export_debug_package()` 函数（约 L2600-L2750）及其局部 import：
```python
import zipfile, subprocess, tempfile, platform, socket, json, time, datetime
```

**操作**：
1. 创建 `交付自检工具/export_debug.py`
2. 从 ui.py 切出完整函数体 + imports，加模块 docstring
3. 从 ui.py 删除对应段落
4. ui.py 原位置加：`from export_debug import export_debug_package`
5. ui.py 调用处 `_export_debug_package()` → `export_debug_package()`

**验证**：
```bash
python3 -m py_compile ui.py export_debug.py
bash 交付自检工具_个人版/build_personal.sh --all
# 在 DaVinci 中点击「📋 导出日志」
```

---

### 第 2/4 步：license_ui.py（纯 Python，无 DaVinci）

**切出范围**：
- `_trial_days_left()` + `_format_trial()`
- `_show_activation_dialog()` 及其嵌套函数
- cpu_id/fingerprint 相关函数（`_get_fingerprint`, `_cpu_id` 等）

**注意**：macOS keychain 操作需要保留在 ui.py 或用参数传入。

**操作**：同步骤 1 模式。

**验证**：
```bash
python3 -m py_compile ui.py license_ui.py
python3 -c "import sys; sys.path+=['shared','交付自检工具']; from license_ui import trial_days_left; assert trial_days_left(...)"
```

---

### 第 3/4 步：config_dialog.py（最复杂，需谨慎）

这是唯一有 DaVinci 依赖的子模块。用参数传入替代对 ui.py 的直接引用。

**操作**：
1. 创建 config_dialog.py，包含：
   - CONFIG_SECTIONS 注册表
   - 所有 `_build_xxx` 函数
   - `_show_config_dialog()` 完整逻辑（含 `_do_save`）
   - `_validate_config_sections()`
2. 入口签名：
   ```python
   def show_config_dialog(log_fn, mask_state, smb_cache, 
                           save_api_keys_fn, load_api_keys_fn):
   ```
3. ui.py 调用处改为：
   ```python
   show_config_dialog(
       log_fn=_action_log,
       mask_state=_gs,  # {"ratio": _mask_ratio, "last_project": _last_project_name}
       smb_cache=None,  # 由 config_dialog 内部加载
       save_api_keys_fn=_save_api_keys,
       load_api_keys_fn=_load_api_keys
   )
   ```

**回滚点**：这一步改完立刻 `git commit`，之后再继续第 4 步。

---

### 第 4/4 步：checks_runner.py

切出 `_start_check()` + 门机制 + `_run_xx_check` 们（它们是 thin wrapper，约 1-2 行）。

**注意**：`_start_check()` 引用了 `_tree`（主窗口 Tree）、`_lock_ui()`/`_unlock_ui()`（模块级函数）。这些保留在 ui.py，通过 callback 传入。

---

## Phase 2 完成后的文件结构

```
交付自检工具/
├── ui.py             ( ~1800 行: 主窗口、Tree、样式、run_fn wrappers )
├── config_dialog.py  ( ~600 行: 配置弹窗 + CONFIG_SECTIONS + builders )
├── license_ui.py     ( ~400 行: 授权显示 + 试用天数 + 激活 )
├── export_debug.py   ( ~200 行: 导出诊断日志 )
├── checks_runner.py  ( ~500 行: 检查调度 + 门机制 )
├── check_core.py     ( 不变 )
├── config.py         ( 不变 )
├── install_agent.py  ( 不变 )
├── launcher_personal.py ( 不变 )
├── shell_personal.py ( 不变 )
├── launcher.py       ( 不变, 公司版 )
└── shell.py          ( 不变, 公司版 )
```

---

## Phase 2 完成后的自动化保障

由于 Phase 1 已将 build_personal.sh 改为自动收录，新增的 4 个 .py 文件无需修改任何构建脚本。以下通道自动正确：

| 通道 | 原理 |
|------|------|
| build_personal.sh | for 循环自动 cp 目录下所有非公司版 .py |
| data.zip (Mac + Win) | 由 build_personal.sh 生成 |
| CDN delta | 由 build_personal.sh --update 生成 |
| 公司版 push_all.sh | 不变——直接从 workspace 读 |
| pre-commit | import 冒烟 + DRY 回归 + 新增文件提醒 |

---

## 回滚预案（完整）

```
任一步失败 → 总回滚:
  git checkout ui.py        # 恢复原始 ui.py
  rm -f config_dialog.py license_ui.py export_debug.py checks_runner.py
  git stash pop             # 恢复其他改动

只回滚第 3 步 (config_dialog.py):
  git revert <step3_commit> # 回退那一步
  继续执行第 4 步
```
