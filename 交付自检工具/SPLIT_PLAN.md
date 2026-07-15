# ui.py 分解方案 — 端到端完整计划

> v1.0 | 2026-07-15 | 吴八哥（高级开发工程师）

---

## 一、当前部署管道全景

```
公司版 (20台 Mac mini, SMB)
  push_all.sh  →  /Volumes/MYJC/.../交付自检工具/
    各机 launcher.py 从 SMB 读 → sys.path 自动包含所有 .py

个人版 Mac
  build_personal.sh  →  _build/交付自检工具_vX.Y.Z/
    data.zip  →  Mac安装.command 解压 → 本地安装
    增量 update.zip  →  jsDelivr CDN → 插件内自动下载覆盖

个人版 Windows
  build_personal.sh  →  同一个 data.zip
    Win安装.bat  →  zipfile.extractall → 本地安装
    增量 update.zip  →  同 CDN
```

**关键发现**：四条路径中，三条（个人版 Mac、个人版 Win、CDN 增量）都从 `build_personal.sh` 派生。公司版直接从 workspace 读。**只有一个文件需要改**——`build_personal.sh`。

---

## 二、Phase 1：标准化构建管道（今天，零破坏性）

### 目标
新增一个 `.py` 文件到 `交付自检工具/` 目录后，自动被所有部署路径收录，无需手改任何构建脚本。

### 现状
```bash
# build_personal.sh L44：硬编码文件名
cp "$WS/交付自检工具"/{ui,check_core,config,install_agent}.py "$PKG/交付自检工具/"
```

### 改造
```bash
# 自动收录：目录下所有产品 .py，排除启动器/公司版专用文件
for f in "$WS/交付自检工具"/*.py; do
    bn=$(basename "$f")
    case "$bn" in
        launcher.py|shell.py|shell_personal.py)
            ;;  # 跳过——公司版/启动器专用
        *)
            cp "$f" "$PKG/交付自检工具/"
            ;;
    esac
done
```

### 验证点
- [ ] 现有文件列表完全一致（`diff <(ls old_build) <(ls new_build)`）
- [ ] 个人版 Mac 安装包生成成功
- [ ] 个人版 Win 安装包生成成功
- [ ] CDN delta 生成成功
- [ ] 公司版不受影响（cp 命令不在推公司版的 push_all.sh 中）

### 配套 pre-commit 守卫
```bash
# 新增 .py 但没在 git add 里 → 提醒检查构建脚本
git diff --cached --name-only | grep '交付自检工具/.*\.py$' | while read f; do
    bn=$(basename "$f")
    case "$bn" in launcher.py|shell*.py) continue ;; esac
    echo "  ⚠ 新增产品文件: $bn — 确认已 git add"
done
```

---

## 三、Phase 2：ui.py 分解（v2.7，纯搬家不改行为）

### 依赖关系分析

ui.py 当前模块级的依赖：

```
ui.py
  ├─ from check_core import ...    （所有检查函数）
  ├─ from config import ...        （版本号、常量、预设）
  ├─ from fusionscript_loader import bmd  （DaVinci 连接）
  ├─ 模块级：WIN_ID, CHECKS, COLUMNS, FIELD_TO_COLUMN
  ├─ 模块级：_track_values, _clamp_value, _mask_ratio（全局状态）
  └─ 内部函数间：_action_log（日志）, cfg（UIManager 实例）
```

### 分解方案

分解原则：**被调用方不收口到调用方**。每个新文件只 import 需要的，不反过来。

```
新结构：

交付自检工具/
├── ui.py              ← 主窗口 + 检查调度 + Tree 渲染（~1800行）
│                       保持 import check_core, config, bmd
│                       保持模块级 WIN_ID, CHECKS, COLUMNS, 全局状态
│                       从子模块 import 函数调用
│
├── config_dialog.py   ← _show_config_dialog() + CONFIG_SECTIONS + builders（~600行）
│  暴露：show_config_dialog(cfg_parent)   # 由 ui.py 调用
│  import：check_core 的 _make_result（已有）
│  依赖：_action_log → 通过参数传入 或 import log_writer
│
├── license_ui.py      ← 授权显示 + 试用天数 + 激活（~400行）
│  暴露：render_license_section(cfg), _trial_days_left(tsd)
│  纯函数，无 DaVinci 依赖
│
├── export_debug.py    ← _export_debug_package()（~200行）
│  暴露：export_debug_package(cfg, license_data)
│  纯 Python，无 DaVinci 依赖
│
├── checks_runner.py   ← _start_check() + 门机制 + run_fn 调度（~500行）
│  暴露：run_all_checks(timeline, fps, gates, io_range) → 结果列表
│  import：check_core 全部检查函数
│  依赖：_action_log → 参数传入
│
├── check_core.py      ← 不变
├── config.py          ← 不变
└── launcher_personal.py, install_agent.py, ...
```

### 接口设计

```
config_dialog.py:
  def show_config_dialog(fu, bmd, parent_tree, log_fn, personal_mode, 
                          mask_ratio_ref, smb_cache_ref) -> None:
      """打开配置弹窗。关闭后通过可变参数回写 mask_ratio / smb_cache"""

license_ui.py:
  def trial_days_left(trial_start_ordinal) -> int:
  def build_license_buttons(cfg) -> list:
  def check_activation() -> dict:

export_debug.py:
  def export_debug_package(license_data, log_dir) -> str:

checks_runner.py:
  def run_checks(timeline, fps, active_checks, gates, log_fn, 
                 mask_ratio=None) -> list:

ui.py 调用:
  from config_dialog import show_config_dialog
  from license_ui import trial_days_left, build_license_buttons
  from export_debug import export_debug_package  
  from checks_runner import run_checks
```

### 每个文件的爆炸半径

| 改什么 | 旧：需要翻的文件 | 新：需要翻的文件 |
|--------|:--:|:--:|
| 加配置项 | 1个（ui.py，但 3500 行里找插入点） | 1个（config_dialog.py，600 行一目了然） |
| 改授权逻辑 | 1个（ui.py） | 1个（license_ui.py） |
| 改检查调度 | 1个（ui.py） | 1个（checks_runner.py） |
| 改导出逻辑 | 1个（ui.py） | 1个（export_debug.py） |

---

## 四、Phase 2 实施步骤

### 步骤 1：Git stash 安全网
```bash
cd 交付自检工具 && cp ui.py ui.py.backup
```

### 步骤 2：逐模块搬家
顺序：按依赖关系从外到内——先搬被调用最少的模块。

1. **export_debug.py**（最独立，零依赖）
   - 切出 `_export_debug_package()` 和相关 import
   - ui.py 加 `from export_debug import export_debug_package`
   - build + 运行验证

2. **license_ui.py**（只依赖 config.py 和 datetime）
   - 切出 `_trial_days_left()`, 授权渲染, 激活逻辑
   - ui.py 加 import
   - 验证

3. **config_dialog.py**（依赖 bmd, fu, CONFIG_SECTIONS, builders）
   - 切出 `_show_config_dialog()`, CONFIG_SECTIONS, builders, savers
   - `_do_save` 跟着一起搬（它是 `_show_config_dialog` 的内嵌函数）
   - 验证——这是最危险的一步，先单独 git commit

4. **checks_runner.py**（依赖 check_core 全部函数 + 门机制）
   - 切出 `_start_check()`, gate 逻辑, run_fn 调度表
   - 验证

### 步骤 3：每步验证
```bash
# 语法
python3 -m py_compile ui.py config_dialog.py license_ui.py export_debug.py checks_runner.py

# import 链（check_core + shared 可脱离 DaVinci）
python3 -c "import sys; sys.path+=['shared','交付自检工具']; from check_core import *; from license_ui import *"

# 全量 build
cd 交付自检工具_个人版 && bash build_personal.sh --all

# DaVinci 实测（裁缝老师手动）
```

### 步骤 4：回滚预案
任一步失败：`git checkout ui.py` + 删掉刚创建的新文件 → 回到步骤 1 前状态。

---

## 五、所有部署路径验证清单

| 验证项 | Mac 公司版 | Mac 个人版 | Win 个人版 | CDN 增量 |
|--------|:--:|:--:|:--:|:--:|
| ui.py 能启动 | □ | □ | □ | □ |
| 配置页能打开 | □ | □ | □ | □ |
| 检查能跑 | □ | □ | □ | □ |
| 授权显示正常 | □ | □ | □ | □ |
| 导出日志正常 | □ | □ | □ | □ |
| 更新检测正常 | □ | □ | □ | ■ 增量更新文件完整 |
| build 脚本无新文件遗漏 | — | □ | □ | □ |

> ■ = 需在 Mac 上验，Win 上是同文件 CDN 拉取

---

## 六、不做的事

- **不重构任何业务逻辑**：纯搬家，不改一行逻辑代码
- **不改变函数签名**：除非原签名引用了移走的内嵌变量（如 `cfg`），此时改为参数传入
- **不拆分共享模块**：shared/ 已经合理，不动
- **不碰 check_core.py**：已经 1979 行，但组织良好，每个检查函数独立

---

## 七、时间估算

| 阶段 | 内容 | 预估 |
|------|------|:--:|
| Phase 1 | build_personal.sh 自动收录化 | 15 分钟 |
| Phase 2 步骤 1 | 备份 | 1 分钟 |
| Phase 2 步骤 2-1 | export_debug.py | 15 分钟 |
| Phase 2 步骤 2-2 | license_ui.py | 20 分钟 |
| Phase 2 步骤 2-3 | config_dialog.py | 30 分钟 |
| Phase 2 步骤 2-4 | checks_runner.py | 25 分钟 |
| Phase 2 步骤 3 | 全量验证 | 20 分钟 |
| **合计** | | **~2 小时** |
