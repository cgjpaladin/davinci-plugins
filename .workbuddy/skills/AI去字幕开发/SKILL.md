---
name: subtitle-plugin
description: AI去字幕插件开发规则。写去字幕插件代码时自动加载，确保不违反行为契约。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
---
# AI 去字幕插件行为契约（v1.11.4，2026-07-02）

代码改动必须与此同步。这是唯一行为准则。

> 写 UI 前加载 `达芬奇UI开发`（39 条预检清单），发布前加载 `达芬奇发布管理`。

## 适配器架构（2026-05-26 重构）

**key/name/provider_key 分离：**
```python
# BaseAdapter.__init__(key, config)
self.key = "ghostcut"          # 内部标识，永不变
self.name = config["name"]      # 显示名，从config来（"鬼手"/"无痕AI 2.1"）
self.provider_key = "ghostcut"  # 定价/ADAPTER_PRIORITY key

# 改名只改 config.py "name" 字段，代码零改动
```

**适配器降级链：**
```
默认: 无痕AI 2.1
  ├─ check_health()=False → ⚠ 提示切备选（手动模式不自动切）
  ├─ 余额不足 → ⚠ 提示充值
  └─ ↓
鬼手
  ├─ 同上
  └─ ✅ 处理
```
- 手动模式：引擎挂了提示具体备选名（如"请切换到 无痕AI 2.1 重试"）
- 自动模式：全部失败自动 fallback（provider_key 映射确保正确跳过）
- **兜底保护**：`create_preferred_adapter(exclude=key)` 全部排除后返回 `None`（不返回已排除引擎→防递归死循环）
- 错误消息统一走 `_real_stderr.write()` — 不经过 `_UIStderr`（阻止死循环）。ResolveDebug.txt 仍可见。

**OSS 上传架构**：
- 无痕AI：阿里云 OSS `wuhenai-clipflow`（REST API 直传，Signature V1）
- 鬼手：自有 OSS（通过 API 获取上传凭证→直传鬼手 OSS→CDN URL）
- 两个引擎的 OSS 完全独立，切换引擎不解决 OSS 网络问题

## 批量处理规范

- 批量模式：上传全部 → 一次提交 → 一起轮询 → 逐个下载
- GhostCut: process_batch() 15x加速 (17片段 660s→43s)
- 无痕AI: process_batch() 8x 加速 (18片段 ~1600s→217s，GPU天然并行)
- 串行模式默认，批量模式需显式开启
- 批量模式中任一失败不进 fail_list，继续处理其余

## 使用者铁律（改代码前必读）

| 规则 | 说明 |
|------|------|
| **core.py 只返回数据** | 不在 core.py 里 print/log/ui，调用者决定展示方式 |
| **新增依赖只能放 core/adapters** | 不给 launcher 加 import |
| **不破坏默认行为** | 不加参数=达芬奇菜单入口，跟原来一模一样 |
| **人类路径始终有 ops_logger + 重试 + traceback** | 不能偷懒 |

## 扫描过滤链

```
扫 IO → 遍历所有视频轨 → 同文件路径去重（按时间线位置排序，首段进入，其余入 alt_tl_items）
  ❌ 摄影机素材（ISO/Lens/Gamma等元数据存在）→ skipped_camera（静默跳过）
  ❌ display_name 含 "_去字幕" → 静默跳过（避免处理已有输出文件）
  ❌ GetClipEnabled()==False → skipped_disabled（不警告）
  ❌ 颜色≠Orange           → 静默跳过
  ❌ MediaPoolItem==None    → skipped_nomp + ⚠警告
  ❌ Type in (复合,Fusion,VFX连接) → skipped_compound + ⚠警告
  ❌ Type 不含"视频"         → skipped_nonvideo + ⚠警告
  ❌ File Path 空/不存在     → skipped_nopath + ⚠警告
  ✅ → 进入任务列表
```

**关键规则**：
- 禁用的不处理不警告——用户主动禁的
- 打了 Orange 但被跳的必须打印原因
- 没打颜色的静默跳过

## 前置校验

- 时长 > 上限 → 跳过（`MAX_SOURCE_DURATION = 30` 秒，定义在 `config.py` 但当前代码未消费——待实现）
- **时长 ≤ 0** → 跳过（防无效 API 调用）

## 缓存复用

```
非 force 模式下:
  ledger.find_output(path) → 查 completed 记录
    → output_path 存在 + getsize > 0 → ReplaceClip（跳过API）
    任一条件不满足 → 视为无缓存 → 走 API
SUBTITLE_FORCE=1 → 强制重新处理
```

**三层下载校验（2026-05-26 加固）：**
1. `urlopen` 异常 → 不放行
2. `getsize == 0` → 不放行
3. `Content-Length` 与实收大小不一致 → 不放行

## stderr 约束（2026-06-27 新增，不可违反）

ui_widgets.py 中 `sys.stderr` 被替换为 `_UIStderr()`（捕获子进程 stderr → 入 UI 日志）。**任何 `print(msg, file=sys.stderr)` 都会走 `_UIStderr.write → _ui_write → _ui_write_direct` 形成死循环，最终 RecursionError 杀线程。**

```python
# ✅ 正确：文件顶保存真实 stderr，内部直写
_real_stderr = sys.stderr
def _ui_write_direct(msg):
    if is_error(msg):
        _real_stderr.write(msg + "\n")  # 直写真实 fd，不经过 _UIStderr

# ❌ 错误：写 sys.stderr（此时已被替换为 _UIStderr）
def _ui_write_direct(msg):
    print(msg, file=sys.stderr)  # ← 死循环入口
```

**影响面**：`_ui_write_direct`、`_event_log`、`StepLogger.fail`、`StepLogger.warn` — 这四处都不能写 `sys.stderr`。
**审查命令**：`grep -n "file=sys.stderr" ai去字幕/ shared/` + `grep -n "sys.stderr =" ai去字幕/` 交叉验证回环已断。

**多机协作陷阱：**
- 账本 (`processing_ledger.jsonl`) 在 SMB 输出目录，多机共享
- `find_output` 检查文件存在 + `getsize > 0`。Content-Length 验证仅在下载路径（`download_and_apply`），不在缓存查找

## 替换策略

- `ReplaceClipPreserveSubClip`（保留子片段裁剪范围）
- **同文件多片段颜色保持**：去重后存入 `alt_tl_items: [(TimelineItem, color)]`，替换后 `restore_clip_colors()` 恢复颜色
- **链接音频颜色保持**：`GetLinkedItems()` 捕获颜色 → ReplaceClip → 逐一恢复
- 输出名从 `os.path.basename(path)` 提取
- 状态 key = `mp.GetClipProperty("File Name")`（非时间线名）
- 输出路径：`EP{XX}/{文件}_去字幕.mp4`

## 依赖

- 打进去不装上去：运行时零安装，构建时 pip 随便用
- ffprobe 仅用于分辨率检测（fallback），时长用 `mp.GetClipProperty("Frames")/FPS` 计算
- SMB 部署，本地 5 行壳

## 架构

```
shell.py(本地,一次性,~50行) → launcher.py(SMB) → stable_ui.py
                        壳: 找Python+看门狗           └── shared/core.py
                                                        └── shared/pipeline_base.py(6步模板)
```

**6 步流水线**（`_step()` 自动编号）：
```
① 扫描 (UI)  →  ② 上传  →  ③ AI去字幕  →  ④ 下载  →  ⑤ 替换  →  ⑥ 完成
```
全缓存时 ②~⑤ 全部显示「（跳过）」。

## 进度条（SubtitlePipeline）

覆盖 `_get_progress_callback()`，统一映射两个 adapter 的 phase→绿条+阶段标签：

| phase | 标签 | 绿条区间 |
|-------|------|:--:|
| upload | ⬆ 上传中 | 0.10→0.17 |
| submit | 📤 提交中 | 0.17→0.20 |
| processing | 🤖 AI处理中 | 0.20→0.75 |
| (pipeline) | ⬇ 下载中 | 0.75→0.90 |
| (pipeline) | 🔧 替换中 | 0.90→1.00 |

无痕含 upload/submit/processing，鬼手含 upload/processing，共用同一映射表。砍掉倒计时，改阶段标签。

## 日志系统

| 优先级 | 路径 | 内容 |
|:--:|------|------|
| 🔴 | ResolveDebug.txt | 关键错误/警告通过 `_real_stderr.write()` 直写真实 stderr，**不走 `_UIStderr`**（防回环） |
| 🔴 | `~/.workbuddy/logs/AI去字幕/ui_*.log` | 全部消息 |
| 🟡 | `~/.workbuddy/logs/AI去字幕/ops_*.jsonl` | 结构化操作日志 |

**日志重复折叠（2026-06-27 修复）：** `_write_to_te` 统一处理主线程直写 + `_flush_log` 队列消费两路径。连续相同消息折叠为 `… （以上重复 N 次）`，文件日志保留全量。
**OPS 追踪**：`shared/pipeline_base.py` L75 `"oss_tracking": True` 控制是否记录 OSS 上传/下载字节数。

## 状态文件管理（subtitle_state.py）

项目级状态 `.subtitle_state.json`，放 SMB `04_素材/03_去字幕/`，团队共享。三层路径替换：

1. 处理前：记录原片 `File Name` → path 到状态
2. Basic/Lite 完：ReplaceClip → 标记 `basic_done`/`lite_done`
3. Pro 跑前：读状态 → 当前指向非原片 → ReplaceClip 还原 → 跑 Pro

**并发安全**：`os.mkdir()` 原子锁——SMB 上两机同时建同名目录只有一个成功，失败者自旋等待 5 次退避。写入持有锁保护。

## 引擎模式（手动/自动）

- **自动（默认）**：按 `ADAPTER_PRIORITY` 依次 fallback
- **手动**：用户选引擎 → `manual_engine` 透传 pipeline → 跳过自动选择。挂了提示具体备选名

## 自动遮罩（GhostCut）

`_auto_mask()` 根据片段属性生成除字幕区域，竖屏/横屏自适应。CRF 参数随 `extra_inpaint_config` 传入。

## ADAPTER_PRIORITY vs ADAPTER_CONFIGS key 空间不一致

**ADAPTER_PRIORITY**（pricing 用）：`["wuhenai", "ghostcut"]`
**ADAPTER_CONFIGS**（config 用）：`{"wuhenai_v21": ..., "ghostcut": ...}`

`"wuhenai" ≠ "wuhenai_v21"` → 所有 `ADAPTER_CONFIGS[key]` 调用必须经过 `_pricing_to_config()` 映射。
**新函数内用 ADAPTER_CONFIGS 必须先确认 key 来源——是 ADAPTER_PRIORITY 还是 ADAPTER_CONFIGS。**
**ui_pipeline.py 使用 ADAPTER_CONFIGS 必须在文件头 `from config import ADAPTER_CONFIGS`，隐式引用不负存在。**

## 防御式 UI（2026-07-02 更新）

- **停止按钮防抖**：1 秒内重复点击忽略（UIManager 可能双火事件）
- **模块级函数**：不依赖其他函数的局部 import——每个函数自给自足
- **button 状态 finally 一致性**：`process()` 的 `finally` 块重置 `undo/stop/warn/start` 四个按钮。scan/pick/color 由外层的 `start_process` 事件循环恢复（不可放在 process finally 中——process 结束 ≠ 整个处理结束）
- **引擎失败提示**：`_flag_engine_error(engine, other)` 依赖 `ADAPTER_CONFIGS`，缺 import = NameError（2026-06-27 fix）
