# DR 20.3.2 新增 API（相对 20.0.0）

> 来源：对比 `README.txt`（2025.05.07 → 2025.10.07）

## 增量的 8 个 API

1. **`GetFairlightPresets()`** — 返回 Fairlight 预设名称列表 `[presetNames...]`

2. **`CreateProject(projectName, mediaLocationPath)`** — 签名扩展，新增可选参数 `mediaLocationPath` 指定媒体存储路径

3. **`ApplyFairlightPresetToCurrentTimeline(name)`** — 对当前时间线应用 Fairlight 预设，返回 Bool

4. **`SetName(name)` in MediaPoolItem** — 媒体池片段改名，返回 Bool

5. **`GetVoiceIsolationState(trackIndex)`** — 音频轨道的语音隔离状态 `{isEnabled, amount}`

6. **`SetVoiceIsolationState(trackIndex, {isEnabled, amount})`** — 设置音频轨道语音隔离，`amount` 范围 [0,100]

7. **`GetVoiceIsolationState()` / `SetVoiceIsolationState({...})` in TimelineItem** — 片段级别的语音隔离

8. **`ResetAllNodeColors()`** — 重置当前版本所有调色节点颜色，返回 Bool

## 渲染选项新增
- `ExportSubtitle`: Bool
- `SubtitleFormat`: string（"BurnIn" / "EmbeddedCaptions" / "SeparateFile"）

## 检查清单
请对照交付自检 `core.py` 和 `main.py`，搜索以下调用：
- `CreateProject` — 是否依赖新参数
- `SetName` — 是否在 MediaPoolItem 上调用
- `ExportSubtitle` / `SubtitleFormat` — 字幕导出功能
- `GetVoiceIsolationState` / `SetVoiceIsolationState` — 语音隔离
