# 达芬奇 Resolve Scripting API — 已知坑位参考卡

> 来源：AI去字幕 v1.7.0 开发过程中的实际踩坑记录 + PostgreSQL 协作模式测试
> 用途：开发新插件（AI换口型、AI语音克隆等）时逐项对照检查
> 最后更新：2026-05-09

---

## 快速检查清单

```
□ GetCurrentProject()        — 协作模式返回 None？判空抛异常
□ GetCurrentTimeline()       — 同上
□ GetClipProperty("Frames")  — 返回 None/""？or 0
□ GetClipProperty("FPS")     — 返回 None？or 24
□ GetClipProperty("File Path") — SMB 断连返回空？判空跳过
□ ReplaceClipPreserveSubClip() — 静默失败？下载→校验→替换三段式
□ SetClipColor()             — 协作模式偶发异常？try/except
□ GetMarkInOut()             — 可能 None？返回(0,0)兜底
□ TimelineItem ≠ MediaPoolItem — 两个数据源会不一致
□ SWIG类型转换               — 可能抛非预期异常
```

---

## 详细说明

### 1. `GetCurrentProject()` / `GetCurrentTimeline()` — 协作模式下返回 None

**触发条件**：PostgreSQL 协作数据库断开、网络波动、达芬奇启动后尚未完全加载项目

**实际发生过**：协作模式下，一台机器正在打开项目，另一台机器脚本执行时 `GetCurrentProject()` 返回 None → 后续调用 Crash

**正确写法**：
```python
resolve = bmd.scriptapp("Resolve")
if not resolve:
    raise RuntimeError("请先启动 DaVinci Resolve Studio")

project = resolve.GetProjectManager().GetCurrentProject()
if not project:
    raise RuntimeError("请先打开一个项目")

timeline = project.GetCurrentTimeline()
if not timeline:
    raise RuntimeError("请先打开一条时间线")
```

**错误写法**：
```python
project = resolve.GetProjectManager().GetCurrentProject()
name = project.GetName()  # ← project 可能是 None → AttributeError
```

**代码位置**：`shared/core.py → connect_resolve()`（已正确防御）

---

### 2. `GetClipProperty("Frames")` / `GetClipProperty("FPS")` — 返回 None 或空字符串

**触发条件**：媒体池项尚未完全加载、SMB 断连、某些格式的媒体文件

**实际发生过**：剪辑师导入一批素材后立即跑脚本，`GetClipProperty("Frames")` 返回 `""` → `int("")` → ValueError

**正确写法**：
```python
frames = int(mp_item.GetClipProperty("Frames") or 0)
fps = float(mp_item.GetClipProperty("FPS") or 24)
duration = frames / fps if fps > 0 else 0
```

**错误写法**：
```python
frames = int(mp_item.GetClipProperty("Frames"))  # None → TypeError
fps = mp_item.GetClipProperty("FPS")              # None → 后续除零
```

**代码位置**：`shared/core.py → get_video_duration()`（已正确防御）

---

### 3. `GetClipProperty("File Path")` — SMB 断连时返回空

**触发条件**：SMB 共享存储断开（网络故障、服务器重启）

**实际发生过**：SMB 服务器例行维护期间，剪辑师运行脚本，`GetClipProperty("File Path")` 返回空字符串 → `os.path.exists("")` → 误判为不存在

**正确写法**：
```python
path = mp_item.GetClipProperty("File Path")
if not path or not os.path.exists(path):
    # 跳过这个片段，记录警告
    stats["skipped_nopath"] += 1
    continue
```

**代码位置**：`shared/core.py → scan_io_clips()` L273-274（已正确防御）

---

### 4. `ReplaceClipPreserveSubClip()` — 最不稳定的 API

**这是达芬奇已知最坑的 API**。四种失败模式：

| 失败模式 | 表现 | 原因 |
|---------|------|------|
| 静默失败 | 返回 `True` 但没替换 | 路径格式不兼容、文件正在被其他进程写入 |
| 锁冲突 | 抛异常 | 另一台机器的用户正在操作同一个 MediaPoolItem |
| 路径不一致 | 替换后 `GetClipProperty("File Path")` ≠ 传入路径 | 达芬奇内部路径规范化 |
| 颜色重置 | 替换后 `TimelineItem` 颜色全部重置 | 已知 bug，ReplaceClip 会重置所有关联片段颜色 |

**正确写法（三段式防御）**：
```python
# 第1段：下载
urllib.request.urlretrieve(result_url, local_path)

# 第2段：校验（文件存在 + 大小>0），不合格不替换
if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
    fail_list.append({"error": "下载文件为空或不存在"})
    release_lock(name)
    continue  # ← 关键：不执行 ReplaceClip

# 第3段：替换 + 降级
try:
    replaced = mp_item.ReplaceClipPreserveSubClip(local_path)
except Exception:
    replaced = False
    _smb_log(f"ReplaceClip 异常（可能被其他用户锁定媒体池）: {name}")

# 降级策略：无论 ReplaceClip 是否成功，下载已完成就记入账本
# 下次可以直接缓存命中，不需要重新下载
ledger.record_completed(fn, local_path, ...)

if replaced:
    # 验证替换结果
    actual = mp_item.GetClipProperty("File Path") or local_path
    # 恢复颜色（ReplaceClip 会重置颜色）
    if mp_color:
        mp_item.SetClipColor(mp_color)
    if tl_color and tl_item:
        try: tl_item.SetClipColor(tl_color)
        except Exception: _smb_log("恢复 tl 颜色失败")
```

**代码位置**：`shared/core.py → download_and_apply()`（已正确实现三段式）

---

### 5. `SetClipColor()` — 协作模式下偶发异常

**触发条件**：PostgreSQL 协作模式 + 高并发（多台机器同时设置颜色）

**实际发生过**：两台机器同时处理不同片段时，`SetClipColor()` 偶尔抛 OSError。原因是 PostgreSQL 协作锁冲突。

**正确写法**：
```python
try:
    tl_item.SetClipColor(original_color)
except Exception:
    _smb_log(f"恢复 tl 颜色失败: {name}")
    # 颜色恢复失败不阻塞主流程，仅影响视觉标记
```

**代码位置**：`shared/core.py` L694-704（已正确防御）

---

### 6. `GetMarkInOut()` — 可能返回 None

**触发条件**：时间线上从未设置过入出点

**实际发生过**：新项目第一次使用时 IO 未设 → `GetMarkInOut()` 返回 None → `mk.get("video", {})` → AttributeError

**正确写法**：
```python
def get_io(timeline) -> tuple:
    mk = timeline.GetMarkInOut()
    if not mk:
        return (0, 0)
    v = mk.get("video", {})
    return (v.get("in", 0), v.get("out", 0))
```

**错误写法**：
```python
mk = timeline.GetMarkInOut()
in_point = mk["video"]["in"]  # mk 可能是 None
```

**代码位置**：`shared/core.py → get_io()`（已正确防御）

---

### 7. TimelineItem ≠ MediaPoolItem — 两个数据源会不一致

**这不是 API bug，是概念陷阱**。同一个视频文件在时间线上有多个 TimelineItem（多个片段），但只有一个 MediaPoolItem（媒体池中的文件）。

**踩过的坑**：
- `TimelineItem.GetClipColor()` ≠ `MediaPoolItem.GetClipColor()` — 颜色在两个层面独立设置
- `ReplaceClip` 作用于 MediaPoolItem → 会同时影响所有关联的 TimelineItem（包括同文件去重的其他片段）
- 颜色恢复必须同时恢复 MediaPoolItem 颜色 **和** TimelineItem 颜色（两者都要）

**正确写法**：
```python
# ClipEntry 同时记录两种颜色
class ClipEntry(NamedTuple):
    tl_color: str = ""       # TimelineItem 颜色
    mp_color: str = ""       # MediaPoolItem 颜色
    alt_tl_items: tuple = () # 同文件其他 TimelineItem（去重跳过，但需恢复颜色）

# ReplaceClip 后恢复颜色
if mp_color:
    mp_item.SetClipColor(mp_color)         # ← 恢复媒体池颜色
if tl_color and tl_item and tl_color != mp_color:
    try: tl_item.SetClipColor(tl_color)    # ← 恢复时间线颜色
    except Exception: _smb_log("...")

# 恢复同文件去重片段（ReplaceClip 会重置它们的颜色）
for alt_tl, alt_color in alt_tl_items:
    if alt_color:
        try: alt_tl.SetClipColor(alt_color)
        except Exception: _smb_log("...")
```

**代码位置**：`shared/core.py → ClipEntry.alt_tl_items`（已正确实现）

---

### 8. SWIG 类型转换 — 可能抛非预期异常

**触发条件**：达芬奇内部 SWIG 层从 C++ 到 Python 的类型转换失败

**实际发生过**：`GetClipProperty("Frames")` 偶尔不是返回 None，而是抛一个非预期的 SWIG 内部异常（`TypeError` 或 `RuntimeError`）

**正确写法**：
```python
try:
    frames = int(mp_item.GetClipProperty("Frames") or 0)
    fps = float(mp_item.GetClipProperty("FPS") or 24)
    return frames / fps if fps > 0 else 0
except Exception:
    # 达芬奇 GetClipProperty 可能抛非预期异常（SWIG类型转换失败），
    # 且视频时长获取不应阻塞扫描流程，降级返回0
    return 0
```

**代码位置**：`shared/core.py → get_video_duration()`（已正确防御）

---

## 新增 API 时的自检流程

每次在新插件中使用达芬奇 API 时：

1. **读返回值**：这个 API 文档说返回什么？实际可能返回什么（None/空/异常）？
2. **判空**：返回值判空后再使用
3. **默认值**：数值类属性用 `or 默认值` 兜底
4. **协作模式**：考虑 PostgreSQL 协作模式下的行为差异
5. **SMB 断连**：考虑共享存储断开时的表现
6. **查本参考卡**：这个 API 在上面列表中吗？已经有人踩过坑吗？

---

## API 来源

- 官方文档：`/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/README.txt`
- 社区：We Suck Less Resolve Scripting 论坛、GitHub pybmd 项目
- 本地代码：`shared/core.py`、`shared/subtitle_state.py`、`AI去字幕/ui_pipeline.py`
