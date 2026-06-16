---
name: subtitle-plugin
description: AI去字幕插件开发规则。写去字幕插件代码时自动加载，确保不违反行为契约。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# AI 去字幕插件行为契约（v1.11.3，2026-05-26）

代码改动必须与此同步。这是唯一行为准则。

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
- 错误消息统一走 stderr 双写 → ResolveDebug.txt 必可见

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
扫 IO → 遍历所有视频轨 → 同名片段去重（优先留 Orange 版本）
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

- 文件名含「正式出片」→ 跳过（已完成）
- **Pro 升级扫描**：正则 `_去字幕_快速预览_v\d+\.\w+$` 严格匹配格式，防止「快速预览.mp4」碰瓷
- 快速预览 + Pro模式 → 从状态文件(file_name key)/文件系统找原片 → 还原
- 普通原片 → 记录 File Name → path 到状态文件
- 时长 > 上限 → 跳过
- **时长 ≤ 0** → 跳过（防无效 API 调用，2026-05-05 新增）
- **空文件名** → 兜底 `clip_{start_frame}` 防止崩溃（2026-05-05 新增）
- 多片段结果处理：results 元组含 `path`（5元素），防止变量作用域泄漏

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

**多机协作陷阱：**
- 账本 (`processing_ledger.jsonl`) 在 SMB 输出目录，多机共享
- 别人删/改缓存文件 → 账本仍指向不存在的路径 → 扫描显示"可复用"但实际无效
- `find_output` 已加固：文件不存在/大小 0/Content-Length 不匹配一律不放行

## 替换策略

- `ReplaceClipPreserveSubClip`（保留子片段裁剪范围）
- 输出名从 `os.path.basename(path)` 提取
- 状态 key = `mp.GetClipProperty("File Name")`（非时间线名）
- 输出目录：`EP{XX}/{01_预览版|02_正式出片}/`

## 依赖

- 零 Runtime pip：运行时只依赖标准库 + 达芬奇。构建时 pip 生成数据 OK
- 零 ffprobe：用 `mp.GetClipProperty("Frames")/FPS` 算时长
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

## 日志系统

| 优先级 | 路径 | 内容 |
|:--:|------|------|
| 🔴 | ResolveDebug.txt | fail/warn 无条件写 stderr |
| 🔴 | `~/.workbuddy/logs/AI去字幕/ui_*.log` | 全部消息 |
| 🟡 | `~/.workbuddy/logs/{hostname}.log` | SSH 可见 ops |

**诊断工具**：`bash tools/check_logs.sh <hostname>` 四源全出。
**回归测试**：`python3 tools/_deep_test.py` 5轮76项。

**UI 日志防重复（2026-05-26）：**
连续相同消息自动折叠为 `… （以上重复 N 次）`。文件日志 + stderr 保留全量。

## ADAPTER_PRIORITY vs ADAPTER_CONFIGS key 空间不一致

**ADAPTER_PRIORITY**（pricing 用）：`["wuhenai", "ghostcut"]`
**ADAPTER_CONFIGS**（config 用）：`{"wuhenai_v21": ..., "ghostcut": ...}`

`"wuhenai" ≠ "wuhenai_v21"` → 所有 `ADAPTER_CONFIGS[key]` 调用必须经过 `_pricing_to_config()` 映射。
**新函数内用 ADAPTER_CONFIGS 必须先确认 key 来源——是 ADAPTER_PRIORITY 还是 ADAPTER_CONFIGS。**

## 防御式 UI（2026-05-26）

- **停止按钮防抖**：1 秒内重复点击忽略（UIManager 可能双火事件）
- **模块级函数**：不依赖其他函数的局部 import——每个函数自给自足
