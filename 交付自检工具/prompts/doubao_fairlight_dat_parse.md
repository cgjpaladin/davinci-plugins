# 豆包提示词：逆向 DaVinci Resolve Fairlight 预设 .dat 文件

## 背景

我是一名影视后期总监，使用 DaVinci Resolve Studio 20.3.2。我在 Fairlight 混音页面配置了一套音频总线预设（4 条总线：Dialogue/Music/SFX/Ambience + 主输出 Bus），保存为 Console Flexi 预设文件：

```
~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Presets/CONSOLE_FLEXI/交付总线设置.dat
```

这个 .dat 文件是 BMD（Blackmagic Design）的私有二进制格式，420KB 大小。

## 目标

请帮助我分析这个 .dat 文件的二进制结构，目标是能够用 Python 解析它，提取出所有的设置项（不止是我当前设置了的，而是这个格式里所有可能出现的字段）。

已知文件中包含的字符串：
- 总线名称：Dialogue, Music, SFX, Ambience
- FX 链路：Clean, De-ess, Levelling, EQ, Dynamics, Duck, Instrumental, Maximize, Spread (Stereo Width)
- 宏 FX ID：bmd:De-Esser:1112360051, bmd:Multiband Compressor:1112360043, bmd:Stereo Width:1112360051
- 归一化级别：AutoMixNormalize:1/2/3/4
- 混音级别：MixLevel:Mix Level:1/2/3/4
- 轨道名称：VO 1, VO 2, OS 3, SFX 4-7, BGM 8-10
- 空间音频：Ambisonics, Dolby Atmos, Room Simulation 相关参数
- Console 映射：Mapping 1-72
- 总线处理：FadeAndCrossFade, OptimizeBusLevel, FadeOut, Multiband Compressor

## 我能提供的信息

1. **文件头**（hex）：
   ```
   0006 6943 6688 6677 0100 0000 3769 0600
   ```
   - `66886677` 在文件中反复出现，可能是类型标记/magic number
   - 文件大小 420167 字节，头部的 `3769 0600`(LE) = 420151，接近文件大小

2. **数据结构模式**：文件中混合了：
   - 4 字节整数（小端序）
   - null-terminated UTF-8 字符串
   - 浮点数（疑似 float32）
   - 大段二进制数据（可能是浮点数组/参数块）

3. **已知结构**：文件似乎包含多个 section：
   - AdrDatabase → 总线数据库
   - AutoMix → 自动混音设置
   - FLTimelineViewPresets → 时间线视图预设
   - LastClient → 上次客户端设置
   - EffectContext → 效果上下文（含大量参数）

## 研究建议

1. 先尝试识别文件的分段结构（section markers）
2. 分析 `66886677` 魔数的含义（可能是 BMD 序列化格式的 type tag）
3. 对比多个同格式 .dat 文件（如果有）来推断可变 vs 固定部分
4. 查看 BMD 的其他产品是否使用类似格式（Fusion .comp 文件？Resolve .drp 文件？）
5. 搜索是否有开源的 BMD 文件格式解析项目

## 输出要求

请输出：
1. 你能推断出的文件结构（分段、字段类型、编码方式）
2. 一个初步的 Python 解析脚本框架
3. 你不确定的区域以及需要更多样本验证的地方
4. 是否有可能从 BMD SDK 或其他渠道获取格式文档
