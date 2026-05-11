# 交付自检工具 — TODO

> 2026-05-10 | 专属待办，不与全局 MEMORY.md 重复

## 待办

| # | 事项 | 状态 |
|---|------|------|
| D3 | 黑边检测完善（旋转归一化 + 跳过逻辑） | ⏳ |
| D6 | 脱机检测（离线片段 + 非 SMB 文件，当前时间线范围） | ✅ v1.6.0 |
| D8.1 | LLM 字幕校对（ASR错字检测+剧本对齐）→ 方案: `外部调研报告/LLM字幕校对方案设计.md` | 📋 待开工 |
| D8.2 | 「忽略」按钮——下次不检查指定条目。方向 B：`ignored.json` | ⏳ |
| D9 | ComboBox 实测可用（AddItems/Clear/CurrentText）— 后续可改用此控件 | ✅ |
| D10 | 推全公司验证 1.6.0 | ✅ v1.6.0 |
| D11 | delivery-checker-dev skill 更新：共享缓存 + 扩展名判定 | ✅ |
| D12 | `_clip_files_cache` 改成 per-session（防交叉污染） | ✅ 已隐式完成（preload 每次清缓存） |
| D13 | launcher 模板 skill（新产品的 launcher.py 骨架） | 💭 远期 |

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
