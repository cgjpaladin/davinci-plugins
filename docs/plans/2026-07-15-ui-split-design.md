# ui.py 分解 — 架构设计文档

> Superpowers Phase 1 | 2026-07-15 | 吴八哥（高级开发工程师）
>
> **目标**：将 3500 行的 ui.py 按职责拆分为 5 个文件，降低修改爆炸半径。
> **约束**：不改业务逻辑，不引入循环导入，不影响四条部署路径（公司版/个人版 Mac/Win/CDN）。
> **决策**：先拆后治（原样搬家，不改全局状态访问模式）。

---

## 一、拆后文件结构

```
交付自检工具/
├── ui.py              主窗口 + 样式 + Tree 渲染 + 入口 main()     (~1600行)
├── config_dialog.py   配置弹窗 + CONFIG_SECTIONS + builders       (~600行)
├── license_ui.py      授权渲染 + 试用天数 + 激活码校验            (~350行)
├── export_debug.py    打包诊断 ZIP + 弹出 Finder                  (~200行)
├── checks_runner.py   检查调度 + 门机制 + 结果组装                (~400行)
├── check_core.py      不变
├── config.py          不变
└── (其余不变)
```

## 二、通信规则

- **ui.py 是唯一入口**：所有子模块由 ui.py import 和调用，子模块不 import 回 ui.py。
- **全局变量走参数**：子模块需要用 `_action_log`、`_DATA_DIR`、`itm` 等全局变量时，由 ui.py 通过函数参数传入，或者子模块从 ui.py import（无循环依赖）。
- **config_dialog.py 例外**：它需要 `bmd` 和 `fu`（DaVinci 连接），自己 import `fusionscript_loader`——不依赖 ui.py。

## 三、施工顺序（按风险递增）

| # | 模块 | 行数 | 全局依赖数 | 复杂度 | 主要风险 |
|:--:|------|:--:|:--:|:--:|------|
| 1 | export_debug.py | 223 | 5 | ⭐ | 纯函数搬家，无嵌套闭包 |
| 2 | license_ui.py | 350 | 8 | ⭐⭐ | 含 `_trial_days_left` 纯函数 |
| 3 | checks_runner.py | 500 | 12 | ⭐⭐⭐ | 门机制 + 多线程 + Tree 更新 |
| 4 | config_dialog.py | 600 | 15 | ⭐⭐⭐⭐ | `_do_save` 嵌套闭包 |

## 四、每步验证协议（不可跳过）

1. `python3 -m py_compile <新文件> ui.py`
2. `python3 tools/smoke_import.py`（ui.py 模块级冒烟）
3. `bash tools/pre-commit.sh`
4. 三项全通过 → 继续下一步。任一失败 → 回滚该步。

## 五、部署影响

- **Phase 1 已落地**：build_personal.sh 自动收录所有产品 .py（排除 launcher.py/shell.py）。新增 4 个文件零部署改动。
- 四条路径全部自动覆盖：公司版 SMB、个人版 Mac、个人版 Win、CDN 增量。
- 文件清单变化后 build_personal.sh 无需修改——for 循环自动收录。

## 六、不做的事

- **不重构全局状态**（`_action_log`、`itm`、`_UI_ERROR_COUNT` 等保持 `global` 访问模式）
- **不改变任何函数签名**（原样搬家，除非原函数引用了搬走后不在作用域的变量）
- **不拆分 check_core.py**（1979 行但组织良好，每个检查函数独立）
