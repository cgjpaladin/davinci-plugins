# 交付自检工具 — TODO

> 2026-05-10 | 专属待办，不与全局 MEMORY.md 重复

## 待办

| # | 事项 | 状态 |
|---|------|------|
| D3 | 黑边检测开发 | ⏳ |
| D5 | 30+ 检查项功能开发 | ⏳ |
| D6 | 建 `delivery-checker-dev` skill（检查函数模板/注册格式/扩展流程） | ✅ 2026-05-10 |
| D7 | 达芬奇 UI 实测本次重构（push_all 前必做） | ✅ 2026-05-10 |
| D8 | 「忽略」按钮——下次不检查指定条目。方向 B：`ignored.json` 按 check_id+clip_uid 存储。A=内存态、C=达芬奇Marker | ⏳ 先不开发 |
| D9 | 「配置」弹窗：轨道数量放开更多选项（字幕1-5/视频1-20/音频1-30），ComboBox 改 SpinBox | ⏳ 预留

## API 盲区

| 功能 | 状态 | 说明 |
|------|------|------|
| 黑边检测 | ⏳ | `run_fn=None`，UI已就位。可读属性：ZoomX/Y、Pan、Tilt、RotationAngle、DynamicZoomEase(0-3)、Opacity、CompositeMode（均为静态值） |
| Fairlight 总线/FX | 黑箱 | API 写-only，无法读取总线路由/FX链 |
| 轨道 Solo/Mute | 黑箱 | Timeline 无相关方法 |
| 轨道颜色 | 黑箱 | 无 GetTrackColor |
| 字幕文本修改 | 黑箱 | SetName 对纯文本字幕返回 False |
| 片段关键帧（不透明度/缩放/合成等） | 黑箱 | GetProperty 只返回静态值，不反映关键帧动态值（2026-05-10 实测 20.3.2） |
| 「使用项目设置」勾选 | 间接 | API 不暴露勾选状态，通过空字符串判断 |

## 已清

| # | 事项 | 版本/日期 |
|---|------|---------|
| D4 | 豆包 .dat 逆向结果跟进 | 2026-05-10 |
