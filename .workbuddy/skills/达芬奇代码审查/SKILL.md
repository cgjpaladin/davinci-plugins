---
name: 达芬奇代码审查
description: 达芬奇插件工坊代码审查标准。改完代码自动对照此清单自查。触发词：代码审查、review、代码自查、检查代码规范。
tools: Read, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
---
# 达芬奇代码审阅标准

**何时用**：改完代码后、commit 前。按 R→S→N 顺序逐条过，R 级不过不能合。

**快速自检（10 秒）**：`git diff` → 看改动范围 → 确认无裸 `except:`、无 `dlg.Find`、无 `open()` 缺 encoding → R 级开始。

**产品标记**：ALL=全产品 | CS=AI去字幕 | DC=交付自检 | RN=批量命名。标记外的产品跳过该规则。

**审阅模式选择**：
```
改单文件/bug fix → 单人对照 R→S→N 表自查
改 shared/ 或大版本发布 → 双评委审阅
接手新项目/全量检查 → 项目级审计
```

## 🛑 绝对不要做

| # | 禁止行为 | 理由 |
|---|---------|------|
| 1 | R 级不过就合代码 | R 级 = 阻断，必须修完 |
| 2 | 只审 git diff 那行 | R13：关联文件也要查 |
| 3 | 用 `except:` 代替 `except Exception` | R12/R17：裸 except 吞信号 |
| 4 | 搬家后不执行双模式 grep | R21：两种 import 都要搜 |
| 5 | 辅助模块（非 ui.py/check_core）import fusionscript_loader | R22：UIManager 单例，widgets 会丢失 |
| 5 | 审 shared/ 不查所有产品的 import 链 | 搬走一个模块影响所有引用方 |

## ⏸️ 审查检查点

- **改 shared/ 或搬家后**：R21 双模式 grep
- **改 launcher.py 后**：R3 import 列表检查
- **commit 前**：R→S→N 全过

## 🔴 R：阻断（不过审不能合）

| # | 产品 | 规则 | 如何执行 |
|---|:--:|------|------|
| R1 | ALL | 公开函数必须有 docstring | `grep "def [a-z]" *.py` 看下一行 |
| R2 | ALL | 改数据流只改一端→两端对称验证 | `git diff` 找到改的函数 A → `grep -n "\bA\b" *.py` 找所有 caller → 确认调用方消费了修改后的输出 |
| R3 | ALL | launcher 自包含，不 import 外部模块 | 看 launcher.py import 列表是否含项目外路径 |
| R4 | CS | adapter 回调签名统一用 `*args` | 检查 adapters/ 下所有回调函数 |
| R5 | ALL | 特殊字符不用手动粘贴→写文件 | 正则/反斜杠/Unicode 检查 |
| R6 | ALL | 加新方法后检查附近缩进 | `python3 -m py_compile *.py` 不通过即有问题 |
| R7 | ALL | 配置字段不可信→推断前先问 | `grep "\.get(" *.py` 看每处有无 fallback 默认值 |
| R8 | ALL | 外部 API 前必须实测验证 | 代码里 `# TESTED: YYYY-MM-DD` 注释或日志文件有 API 成功记录 |
| R9 | CS | adapter 构造用 `super().__init__(key, config)` | 检查 adapter 类 `__init__` |
| R10 | ALL | 模块级新函数的所有全局符号必须在函数/模块级 import | `grep` 函数体内用的符号→追溯到文件顶部的 `import/from` |
| R11 | CS | `ADAPTER_PRIORITY` 与 `ADAPTER_CONFIGS` key 空间不同 | `grep "ADAPTER_PRIORITY\|ADAPTER_CONFIGS" *.py` 确认无直接混用 |
| R12 | ALL | `except:` → `except Exception` 或 `except OSError` | `grep "except:" *.py \| grep -v "Exception" \| grep -v "# noop"` |
| R13 | ALL | `git diff --name-only HEAD~1` 列出的所有文件 = 审阅范围。不得只盯着改过的那一行。改了 ui.py 也查 交付自检工具/llm_typo_check.py（v2.6.1已从 shared/ 搬入） | `git log --oneline --since="24 hours ago"` 确认范围 |
| R14 | CS | 任何含日志输出（`_ui_write_direct`/`_event_log`/`StepLogger`）的文件，必须 grep 确认 `print(file=sys.stderr)` 指向 `_real_stderr` 而非 `sys.stderr`。——此模式主要在 `AI去字幕开发` skill 的 stderr 约束章节中 | `grep -n "file=sys.stderr" 文件` + `grep -n "sys.stderr =" 文件` 交叉验证 |
| R15 | ALL | 类级 `set()`/`[]`/`{}` → 跨实例/跨批泄漏。用局部变量或 `__init__` 中初始化。——2026-05-24 批量命名去重泄漏教训 | `grep -n "^\s*self\.\w* = set()\|^\s*self\.\w* = \[\]" *.py` |
| R16 | ALL | **用户可见文案禁止暴露系统错误。** `raise`/`_action_log`/`itm[HINT_LB].Text`/`itm[...].Text` 中不得出现原始 stderr、异常栈、系统错误码。——2026-07-03 发布会暴露 `osascript -128` 的教训 | `grep -n "traceback\|format_exc\|stderr\|RuntimeError.*f\"\|HINT_LB.*Text.*=\|\.Text =.*\\b\{e\\b" *.py` |
| R17 | ALL | **裸 `except:` 禁止。** 吞掉 `KeyboardInterrupt`/`SystemExit` 导致进程不可控（Ctrl+C 无效）。至少用 `except Exception:`。——2026-07-06 实测确认 | `grep -rn "^\s*except:" --include="*.py" . \| grep -v "pycache\|\.app/"` |
| R18 | ALL | **`except Exception: pass` 必须带注释**说明为什么能安全跳过，否则加日志或改为 `raise`。——2026-07-06 164 处静默审计 | `grep -rn "except Exception: *pass" --include="*.py" . \| grep -v "#"` |
| R19 | ALL | **达芬奇 API 优先判 None。** `GetItemListInTrack` 等返回 `None` 而非抛异常，用 `or []` 代替 `try/except`。——2026-07-06 1666 次调用实测 | 审查新增代码中的 `except Exception` 是否可简化为 None 判断 |
| R20 | ALL | **`subprocess.run` 必须设 `timeout=`。** 缺 timeout → 网络/IO 卡住进程永久假死。`open`/`explorer` 等瞬发命令可用 `timeout=5`。——2026-07-06 跨平台审计 | `grep -rn "subprocess\.\(run\|check_output\)(" --include="*.py" . \| grep -v "timeout"` |
| R21 | ALL | **非标 import——`from X import` 而非 `from shared.X import`。** 依赖 `shared/` 在 sys.path 上，子进程中可能不可靠。新增/搬家后检查：`grep -rn "from (模块名) import" --include="*.py" . \| grep -v "from shared\." \| grep -v "from \."` ——2026-07-16 shared/净化审计发现系统性误判根因 | 改 shared/ 或搬家后执行双模式 grep |
| R22 | ALL | **UIManager 单例——辅助模块禁止 `from fusionscript_loader`。** widget 和 window 必须共用同一个 `fu.UIManager`，否则 `GetItems()` 找不到 widget → 窗口空白。2026-07-16 config_dialog 拆分踩坑 | `grep -rn "from fusionscript_loader" --include="*.py" . \| grep -v "ui.py" \| grep -v "check_core.py" \| grep -v "launcher"` |
| R23 | DC | **`dirname(dirname)` 在安装环境路径错。** 安装后 shared/ 在脚本**同级目录**，不在上层。`os.path.dirname(os.path.dirname(__file__))` → `Scripts/shared/`（❌），应改为 `os.path.dirname(__file__)` → `交付自检工具/shared/`（✅）。影响：更新检测子进程、FC 验证子进程全静默失败。——2026-07-28 上海用户诊断 | `grep -rn "dirname.*dirname" --include="*.py" .` |
| R24 | DC | **ComboBox.RecalcLayout() 不支持。** DaVinci UIManager 中 ComboBox 无此方法，调用抛 `'NoneType' object is not callable`。仅对话框/HGroup/VGroup 支持。——2026-07-28 上海用户诊断 | `grep -rn "combo.*RecalcLayout\|RecalcLayout.*combo" --include="*.py" .` |

🛑 **R 全部通过后暂停，展示结果，等裁缝老师确认再进入 S。**

## 🟡 S：建议

| # | 产品 | 规则 | 如何执行 |
|---|:--:|------|------|
| S1 | DC CS | 改 UI 后审阅完整调用链 | `git diff` 找到改的 widget → `grep` 该 ID 全文→确认所有引用处行为兼容 |
| S2 | ALL | 批量替换后 `git diff` 验证每条改动 | 跑 `git diff` → 逐条确认只有目标行变化 |
| S3 | ALL | 改完代码 grep 被改符号的所有引用 | `grep -n "\b函数名\b" *.py` 确认无遗漏 |
| S4 | ALL | 被打断后 `git diff` 自查 | 中断后第一件事：`git diff` 看当前状态 |
| S5 | ALL | 字符串比较前肉眼检查字符 | 复制原文到文本编辑器放大看，确认 `一カ`≠`一卡` |
| S6 | ALL | `from X import VAR` 拷贝原始类型→用 `import X as _x` + `_x.VAR` | `grep "from .* import" *.py` 检查导入的值是否为 str/int |
| S7 | ALL | 断言必须验证 | 说"文件存在"→`ls`路径 | 说"日志落盘"→`tail`日志文件 |
| S8 | DC CS | 达芬奇 API 返回值不可信 | `GetItemListInTrack` 遍历前加 `or []` |
| S9 | DC CS | `GetClipProperty('Type')` 中英文双值检查 | 同时 grep 英文名和中文本地化名 |
| S10 | DC CS | 壳方案：永久壳→SMB launcher | shell.py 只找 Python+启动 launcher，不含业务逻辑 |
| S11 | ALL | 类级变量泄漏→用局部变量 | `grep "= set()\|= \[\]\|= \{\}" *.py` 看 class 体内 |
| S12 | RN | `endswith` 误匹配→`startswith` + 精确字段解析 | 检查命名工具 js/py 中的文件后缀判断逻辑 |
| S13 | RN | 多选编辑值变化判断不能只看发起行 | 检查 `sel.size > 1` 时对所有选中行写入 |
| S14 | ALL | 缓存验证：`exists` + `getsize > 0` | `os.path.exists(f) and os.path.getsize(f) > 0` |
| S15 | ALL | 下载验证：记 Content-Length 对比 | 下载后对比实际文件大小与 HTTP 响应头 |
| S16 | ALL | DaVinci 子进程网络调用不可靠——失败一次就停，不反复重试 | `grep` 子进程代码有无无限重试逻辑 |
| S17 | DC | **子进程内 daemon 线程随进程 exit 被 kill。** `subprocess.Popen` 中的 `threading.Thread(daemon=True)` 无法存活——IP 采集等异步操作必须放在主进程。——2026-07-28 激活用户 IP 不更新根因 | 审查 `verify_activation()` 等子进程调用的函数 |
| S18 | DC | **`_start_check()` 必须用 `try/finally` 包所有退出路径。** 无项目/无时间线/无勾选/异常/正常五条路径必须统一 `_unlock_ui()`。`_run_ai_typo()` 已实现，`_start_check()` 曾缺失。——2026-07-24 dd-mbp 测试 | `grep "_start_check\|_lock_ui\|_unlock_ui" ui.py` 确认对称 |
| S19 | DC | **多级 API 调用链中关键字段必须逐层透传。** `_call_openai_compat` → `call_with_fallback` → `_single` → `check_typos` → ui。任一层 return 重建 dict 时漏传 → 后续全丢。——2026-07-28 token usage 采集发现 call_with_fallback + _single 两处断裂 | 遍历所有 `return {` 的 dict 构造，确认包含上层传入的全部关键字段 |

## 💭 N：优化

| # | 规则 | 如何执行 |
|---|------|------|
| N1 | git commit 不超过 30 分钟 | 大改动分批提交，每 30min 检查 `git status` |
| N2 | 收工前检查版本号 | `grep "__version__" config.py` 确认已 bump |
| N3 | 改完代码立刻跑 `py_compile` | `python3 -m py_compile *.py` |
| N4 | 复杂 UI 先写最小测试 | 新建 test_smoke.py 验证控件可见 |
| N5 | 共享遍历缓存中间结果 | 同一轮检查中，多个 check 函数共享一次 IPC 结果 |
| N6 | 运维脚本双路径留痕 | 日志同时写 `~/.workbuddy/logs/` + SMB 日志目录 |
| N7 | `os.walk()` 加计数上限 | `for root, dirs, files in os.walk(path): if n > 200: break` |

## 绝对禁止（独立黑名单）

| # | 禁止事项 |
|---|------|
| 1 | 用 `replace_all: true` 批量替换——分步 Edit，每步 `git diff` 验证 |
| 2 | 裸 `except: pass` 静默吞错——必须 `except Exception: _action_log(...)` |
| 3 | 双评委结论未经确认直接修——必须先展示共识报告等裁缝老师确认 |
| 4 | `w_go.Text = "x"` / `dlg["ID"]` 假 API——必须 `dlg.GetItems()` 后操作 |
| 5 | `open()` 文本模式无 `encoding="utf-8"` |
| 6 | Launcher 缺 `PYTHONUTF8=1` |
| 7 | 类级定义 `set()`/`[]`/`{}`——跨批泄漏反模式 |

## 机械检查（双评委扫这些）

| 规则 | grep 命令 |
|------|------|
| 裸 except | `grep -n "except:" *.py \| grep -v "Exception" \| grep -v "# noop"` |
| 假 API | `grep -n "dlg\.Find\|dlg\[" *.py` |
| `open()` 无 encoding | `grep -n "\bopen(" *.py \| grep -v "encoding=" \| grep -v '"rb"' \| grep -v '"wb"'` |
| Launcher 缺 `PYTHONUTF8=1` | 检查所有 launcher*.py shell*.py |
| 控件蓝图赋值 | 确认 `_items[...].Text/Enabled =` 前有 `dlg.GetItems()` |

## 双评委审阅（降低误报）

单 agent 75% 误报率（`~/.workbuddy/MEMORY.md` 铁律）。两人独立扫描 + 共识过滤可大幅降低。常规改代码 → 单人 R/S/N；改 shared/ 或大版本 → 双评委。

```
1. 建两支独立的 agent，投喂 git diff + 机械检查表
2. 各回报发现，对比共识
3. 两人都报 → 🔴 真问题 | 仅一人报 → 🟡 待确认 | 两人都无 → ✅ 通过
4. 🛑 HARD STOP：展示共识报告。必须等裁缝老师确认，不准跳过直接修
```

## 项目级审计（接手项目）

```
1. 人工端到端：画调用链（代码→构建→部署→运行时→更新）→ 逐层 grep 硬编码
2. agent 补扫：只信"指向"不信"判定"
3. 逐条验证：读代码 → git diff → git blame
4. 沉淀写入：项目事实 → workspace MEMORY，铁律 → `~/.workbuddy/MEMORY.md`，操作流程 → skill
```

## 导出标准

| 维度 | 🟢 通过 | 🔴 不通过 |
|------|---------|----------|
| 去重 | 局部变量+指纹 | 防抖+setTimeout |
| 校验 | 类型+范围+格式 | 无校验 |
| 错误处理 | 精确消息+恢复 | 裸 `except: pass` |
| 日志 | 逐条目可追溯 | 无日志 |
| 状态管理 | 无跨批泄漏 | 无意识泄漏 |
| 按钮状态 | `try/finally` 完整闭环 | 提前 return 漏恢复 |
| 网络调用 | curl fallback + 有限重试 | 无限重试 / 无 fallback |
| 版本号 | `tuple(int)` 比较 | `sorted(string)` 排序 |
| 文档同步 | MEMORY/Skill 无重复 | 同一事实写了两处 |
| 断言 | 每条有验证命令 | 「应该是」「估计是」 |
