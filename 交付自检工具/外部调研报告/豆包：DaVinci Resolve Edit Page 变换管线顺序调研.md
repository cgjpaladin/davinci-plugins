# 调研任务：DaVinci Resolve Edit Page 变换管线精确顺序

## 背景

我们正在开发一个达芬奇交付自检工具，需要判断视频素材在时间线上是否有黑边（未覆盖区域）。当前方案通过读取达芬奇 Scripting API 的变换参数（ZoomX/Y、RotationAngle、Pan、Tilt），将时间线四角逆变换到素材坐标系进行覆盖判定。

但结果有误判。根因可能是我们对达芬奇内部的变换执行顺序理解有偏差。

## 核心问题

**DaVinci Resolve 的 Edit Page Inspector 中，变换参数以什么数学顺序执行？**

达芬奇 Inspector 面板提供这些参数：
- Anchor Point X/Y（锚点）
- Zoom X/Y（缩放）
- Rotation Angle（旋转角度）
- Position X/Y / Pan / Tilt（位置/位移）
- Pitch / Yaw（俯仰/偏航）
- Flip（翻转）

## 需要确认的事项

### 1. 变换顺序
达芬奇是按什么顺序执行这些变换的？是：
- A: Anchor → Scale → Rotate → Position（我们目前的假设）
- B: Scale → Anchor → Rotate → Position
- C: Anchor → Rotate → Scale → Position  
- D: 其他顺序？

### 2. "缩放至适配" (Scale to Fit) 的处理时机
当素材分辨率与时间线分辨率不匹配时，达芬奇有三类设置（Fit/Fill/Stretch/None）：
- 这些是在变换参数**之前**还是**之后**应用的？
- 这个基准缩放会被 Inspector 中的 Zoom 参数**叠乘**还是**替代**？

### 3. 旋转的基准点
Rotation 是绕 Anchor Point 旋转，还是绕图像中心？Anchor Point 改变后，Pan/Tilt 的坐标系原点跟着变吗？

### 4. 与 Fusion Transform 节点的关系
据说达芬奇 Edit Page 的变换底层用的是 Fusion 的 Transform 节点引擎。Fusion Transform 的官方文档是否明确写了执行顺序？如果有，请引用。

### 5. 你见过的"8 步或 16 步画面算法"图
有人说达芬奇内部有一个 8 步或 16 步的画面处理管线。如果你见过这张图或相关文档，请描述具体步骤。

## 我们实际的测试数据（辅助判断）

素材：3840×2160（16:9 横屏），时间线：2160×3840（9:16 竖屏）
- 用户设置了 Zoom = 1.78，Rotation = -90°
- API 返回 RotationAngle = -5156.6°（累计值）
- 经过逆变换计算，四角检查显示有"黑边"，但用户肉眼确认画面填满了屏幕

这暗示我们的逆变换顺序（Scale→Rotate→Translate）可能与达芬奇的实际正向顺序不匹配。

## 期望输出

请给出：
1. 确切的变换顺序（如有官方文档引用最好）
2. Scale to Fit 和用户 Zoom 的关系
3. 对 RotationAngle 返回大累计值（非 -90°）的解释
4. 如果可能，给出正解的正向变换矩阵公式
