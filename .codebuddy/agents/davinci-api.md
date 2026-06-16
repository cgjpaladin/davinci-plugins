---
name: davinci-api
description: 达芬奇 Resolve Scripting API 详细参考。触发词：达芬奇API、Resolve API、时间线操作、媒体池、渲染、ReplaceClip。
tools: Read, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# 达芬奇 API 详细参考

> `达芬奇脚本开发` 的子 skill。加载前确保已加载主 skill。

## 连接 Resolve

```python
# ✅ 项目标准：fusionscript_loader（已验证 20.3.2）
sys.path.insert(0, 'shared')
from fusionscript_loader import bmd
resolve = bmd.scriptapp('Resolve')
fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)
```

**不推荐** `import DaVinciResolveScript` — 依赖环境变量，版本升级路径可能断裂。

## Timeline 操作

```python
timeline = project.GetCurrentTimeline()

# 轨道
timeline.AddTrack("video")    # / "audio" / "subtitle"
items = timeline.GetItemListInTrack("video", 1)  # 必须两个参数！

# 导出
timeline.Export("/path/to/output.aaf", resolve.EXPORT_AAF, resolve.EXPORT_AAF_NEW)
```

## 媒体池

```python
clip = mediaPool.ImportMedia("/path/to/file.mp4")
mediaPool.AppendToTimeline(clip)
rootFolder = mediaPool.GetRootFolder()
clips = rootFolder.GetClipList()
newTimeline = mediaPool.CreateEmptyTimeline("新时间线")

# 片段属性
clip.GetClipProperty("File Name")    # 磁盘名（最稳 ✅）
clip.GetClipProperty("Clip Name")    # 媒体池名
clip.GetClipProperty("Duration")
clip.GetClipProperty("FPS")
clip.GetClipProperty("File Path")    # 完整路径（MediaPoolItem 上才有）
```

## TimelineItem

```python
item = items[0]

# 变换
item.SetProperty("ZoomX", 1.2)
item.SetProperty("RotationAngle", 90.0)
item.SetProperty("Opacity", 50.0)
item.SetProperty("CompositeMode", "COMPOSITE_MULTIPLY")

# 帧级
it.GetDuration(True)           # 子帧精度
it.GetSourceStartFrame()
it.GetSourceEndFrame()
it.GetTrackTypeAndIndex()      # → ['video', 1]
it.GetLinkedItems()            # → [] / [{linked_item}]
it.GetClipEnabled()
```

## 渲染

```python
proj.SetCurrentRenderFormatAndCodec("mov", "ProRes422HQ")
proj.SetRenderSettings({"SelectAllFrames": 1, "TargetDir": "/path/to/output"})
jobId = proj.AddRenderJob()
proj.StartRendering()
while proj.IsRenderingInProgress():
    time.sleep(1)
proj.DeleteAllRenderJobs()
```

> ⚠️ `SetRenderSettings` + `AddRenderJob` 在 20.3.2 可能触发崩溃。来自张来吃 filenameGenerator.py，旧版可用，20.x 慎用。

## ReplaceClip

```python
mp.ReplaceClip(path)                    # 裁剪范围可能偏移
mp.ReplaceClipPreserveSubClip(path)     # 保留子片段裁剪 ✅ 推荐
```

| 属性 | 替换后 | 备注 |
|------|:--:|------|
| 变速/链接音频/标记/合成/不透明度/调色版本 | ✅ | 保留 |
| **片段颜色** | ❌ | 需手动恢复 |
| **变换(Zoom/Pan)** | ❌ | 跟随新媒体 |
| 自定义元数据 | ❌ | 被清空 |

> ReplaceClip 换的是媒体源，颜色/变换丢失是达芬奇设计，不是插件 bug。

## PostgreSQL 协作

环境：5 台 Mac mini + PG 192.168.1.154 + 同一项目库。

```python
pm.SetCurrentDatabase({"DbType": "PostgreSQL", "DbName": "MYJC_2026_A"})
proj = pm.LoadProject("项目名")
```

**已验证**：dry-run/处理/撤销行为一致，Bin 锁互不干扰，SMB 并发锁安全，ReplaceClip 实时可见。

## 标记系统

```python
clip.AddMarker(frameId, "Red", "处理中", "去字幕任务", 1, '{"task_id":"xxx"}')
clip.GetMarkers()          # {frameId: {color, name, note, duration, customData}}
clip.DeleteMarkersByColor("Red")
```

`customData` 可放任意 JSON。

## 项目设置

```python
proj.GetSetting("timelineFrameRate")
proj.GetSetting("timelineResolutionWidth")
proj.SetSetting("superScale", 2)
proj.GetUniqueId()         # 项目 UUID
tl.GetUniqueId()           # 时间线 UUID
```

### 四个项目存储路径

| 设置 | 键 | GetSetting / SetSetting |
|------|-----|------------------------|
| 项目媒体位置 | `projectMediaLocation` | ✅ 可读可写 |
| 代理生成位置 | `perfProxyDir` | ✅ 可读可写（需先开启 `perfProxyMediaMode: 1`） |
| 缓存文件位置 | `perfCacheClipsLocation` | ✅ 可读可写 |
| 画廊静帧位置 | `colorGalleryStillsLocation` | ✅ 可读可写 |

```python
# 读
media  = proj.GetSetting("projectMediaLocation")
proxy  = proj.GetSetting("perfProxyDir")
cache  = proj.GetSetting("perfCacheClipsLocation")
stills = proj.GetSetting("colorGalleryStillsLocation")

# 改
proj.SetSetting("colorGalleryStillsLocation", "/Users/bryan/Desktop")
```

**代理相关补充**：

```python
proj.GetSetting("perfProxyMediaMode")        # 0=关闭, 1=开启
proj.GetSetting("perfProxyResolutionRatio")  # "original" / "half" / "quarter"
proj.GetSetting("perfOptimisedMediaOn")      # 0/1 优化媒体开关
```

> 代理路径只在 `perfProxyMediaMode=1` 时生效。SetSetting 在达芬奇 20.3.2 GUI 模式下验证通过。项目间可通过 `pm.LoadProject()` 切换后批量改。

## 帧级 + IO

```python
tl.GetStartFrame()
tl.SetMarkInOut(s, e)      # ✅ 正确（不是 SetInOut）
tl.GetMarkInOut()          # → {'video': {'in': N, 'out': N}, 'audio': {...}}
tl.ClearMarkInOut()
tl.SetCurrentTimecode(ts)  # 跳转播放头
project.ExportCurrentFrameAsStill("/tmp/frame.png")
```

> SetMarkInOut 不持久，每次脚本启动需重新设置。

## 颜色/变速

```python
item.SetLUT(1, "/path/to/lut.cube")    # 应用 LUT (1-based)
item.ExportLUT(resolve.EXPORT_LUT_33PTCUBE, "/path/to/output.cube")
```

**CompositeMode**: 0=正常 1=添加 2=减去 3=差值 4=正片叠底 5=滤色 6=叠加 … 31=反向亮度

**RetimeProcess**: 0=项目设置 1=邻近 2=帧混合 3=光流

**变速检测**：`source_sec / timeline_sec`，偏差 > 2% 算变速，源时长 < 0.08s 过滤静帧。

## 常见坑位速查

| 错误 | 现象 | 正确 |
|------|------|------|
| `GetItemListInTrack(1)` | None | `("video", 1)` —— 必须双参数 |
| `GetItemListInTrack("video", N)` 空轨 | None | 所有遍历必须 `or []` |
| `GetTrackCount()` | 错误值 | `GetTrackCount("video")` |
| `TimelineItem.GetClipProperty("File Path")` | 空 | 走 `GetMediaPoolItem()` |
| `tl.SetInOut(s, e)` | NoneType | `SetMarkInOut(s, e)` |
| `item.GetClipColor()` | None/""/[] | 都要当"无颜色"处理 |
| `GetCurrentTimeline()` | None（新项目）| 遍历 `GetTimelineByIndex` |
| `GetCurrentProject()` 协作 | None | 判空 + 抛明确异常 |
| `GetClipProperty("Frames"/"FPS")` | None/"" | `int(x or 0)` / `float(x or 24)` |
| `GetClipProperty("File Path")` SMB断 | 空 | 判空 + skip |
| `ReplaceClipPreserveSubClip` | 四种失败 | 下详 |
| `SetClipColor()` 协作 | 偶发异常 | try/except 不阻塞 |
| `GetMarkInOut()` 未设 | None | `or (0,0)` 兜底 |
| TimelineItem ≠ MediaPoolItem | 颜色不一致 | 两个层面分别恢复 |
| SWIG 类型转换 | TypeError | `except Exception` 包裹 |
| `GetFairlightPresets()` 返回值 | 文档写 `[names...]` 但实际是 `{0: "name"}` dict | 遍历用 `.items()` 不用索引 |
| `ApplyFairlightPresetToCurrentTimeline(name)` | 挂在 Project 对象上，不是 Resolve/Timeline | `project.ApplyFairlightPresetToCurrentTimeline("name")` |

### Fairlight API（v20.3.2+）

- `resolve.GetFairlightPresets()` → `{0: 'name1', 1: 'name2'}` dict（⚠ 不是 list）
- `project.ApplyFairlightPresetToCurrentTimeline("name")` → Bool
- 无「查询当前时间线用了哪个预设」的 API（写操作有，读操作缺）

### ReplaceClip 四种失败模式

| 失败模式 | 表现 | 对策 |
|---------|------|------|
| 静默失败 | 返回 True 但没替换 | 下载→校验→替换三段式，校验不过不执行 |
| 锁冲突 | 抛异常 | try/except，降级记录 |
| 路径不一致 | 替换后 GetClipProperty ≠ 传入路径 | 以实际路径为准 |
| 颜色重置 | 所有关联 TimelineItem 颜色丢失 | 同时恢复 MediaPoolItem + TimelineItem + 去重片段颜色 |

### 协作模式额外防御

- `GetCurrentProject()` / `GetCurrentTimeline()` → PG 断连时返回 None，必须判空
- `SetClipColor()` → 高并发偶发异常，try/except 不阻塞
- `ReplaceClip` → 另一台机器锁定媒体池时抛异常，不阻塞账本写入

### 新增 API 自检清单

每次在新插件中用达芬奇 API：①读返回值（可能 None/空/异常）→ ②判空 → ③数值用 `or 默认值` → ④考虑 PG 协作差异 → ⑤考虑 SMB 断连 → ⑥查本表是否已有坑

### GetClipColor() 返回值对照表

API 返回英文名，以下为官方 17 种标准色彩：

| # | 返回值 | 中文名 | RGB |
|---|--------|--------|-----|
| 1 | `""` (空) | 默认颜色 | (62, 62, 62) |
| 2 | `"Orange"` | 橘色 | (253, 100, 0) |
| 3 | `"Apricot"` | 杏色 | (255, 163, 0) |
| 4 | `"Yellow"` | 黄色 | (236, 166, 0) |
| 5 | `"Lime"` | 青柠色 | (148, 199, 0) |
| 6 | `"Olive"` | 橄榄绿 | (74, 155, 0) |
| 7 | `"Green"` | 绿色 | (24, 145, 97) |
| 8 | `"Teal"` | 蓝绿色 | (0, 155, 154) |
| 9 | `"Navy"` | 藏青色 | (0, 84, 123) |
| 10 | `"Blue"` | 蓝色 | (47, 120, 165) |
| 11 | `"Purple"` | 紫色 | (160, 112, 163) |
| 12 | `"Violet"` | 紫罗兰色 | (225, 75, 143) |
| 13 | `"Pink"` | 粉红色 | (248, 134, 183) |
| 14 | `"Tan"` | 棕褐色 | (187, 175, 148) |
| 15 | `"Beige"` | 米黄色 | (203, 158, 119) |
| 16 | `"Brown"` | 棕色 | (162, 99, 0) |
| 17 | `"Chocolate"` | 巧克力色 | (148, 87, 57) |

> 项目使用: `check_core.py → _audio_color_detail()` 据此判断音频素材是否正确归类。

## 代码模板

```python
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, 'shared')
from fusionscript_loader import bmd

resolve = bmd.scriptapp('Resolve')
if not resolve:
    exit('请先启动 DaVinci Resolve')

proj = resolve.GetProjectManager().GetCurrentProject()
if not proj:
    exit('请先打开项目')

tl = proj.GetCurrentTimeline()
print(f"项目: {proj.GetName()} / 时间线: {tl.GetName()} / 版本: {resolve.GetVersionString()}")
```

## 无头模式

```bash
nohup "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve" -nogui > /tmp/dvr_nogui.log 2>&1 &
```

- 退出：`r.Quit()`（仅无头模式有效；GUI 模式用 `osascript`）

## UIManager 控件访问（2026-06-01 验证）

```python
# ✅ 唯一正确：GetItems() dict
_items = dlg.GetItems()
_items["widget_id"].Text = "新文字"
_items["widget_id"].Enabled = False

# ❌ 全部错误
dlg.Find("widget_id")     # 不存在
dlg["widget_id"]          # KeyError
widget_obj.Enabled = False # widget_obj 是蓝图 dict，改不动 UI
```

### 窗口置顶
```python
"WindowFlags": {"Window": True, "WindowStaysOnTopHint": True}
```

### 注意事项
- `ProcessEvents()` 可能阻塞 UI——下载前别调
- 事件绑定：`dlg.On["widget_id"].Clicked = handler`
- `nonlocal` 只用于外层变量重新绑定，读取无需
- 禁止 `kill`/`pkill`：会触发 Fairlight SIGABRT 崩溃
