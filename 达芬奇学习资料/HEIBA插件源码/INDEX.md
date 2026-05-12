# HEIBA（黑靶）插件源码

> 裁缝老师说「看看黑靶是怎么写的」→ 这里。

HEIBA 所有插件均使用 DaVinci Resolve 的 **Lua Fusion UI**（`fu.UIManager` + `bmd.UIDispatcher`），
属于达芬奇原生插件架构的标杆参考。

解密密钥均为硬编码：`heiba` / `HEIBA-2025` / `HEIBA-2026`。
解密脚本：`../../tools/decrypt_heiba_xor.py`

## 插件清单

| 文件 | 行数 | 功能 | 值得参考的 |
|------|------|------|-----------|
| `DaVinci Sub Editor_明文.lua` | 4602 | 字幕编辑面板 | Fusion UI 复杂布局、FileDialog、多语言、付费激活 |
| `DaVinci TTS_明文.lua` | 13596 | 文字转语音 | 模块化架构（Config/Storage/Utils/UI）、JSON 配置持久化 |
| `批量替换片段-完全匹配_明文.lua` | 358 | 按完整文件名批量 ReplaceClip | 媒体池遍历、ReplaceClip API |
| `批量替换片段-匹配前n位_明文.lua` | 405 | 按文件名前缀批量 ReplaceClip | 同上 + 字符串前缀匹配 |

## 可复用的设计模式

| 模式 | 来源 | 适用产品 | 状态 |
|------|------|---------|:--:|
| **Loading 独立窗口** — 异步操作时开小窗防 UI 卡死 | TTS (line 3419) | AI去字幕（鬼手/无痕处理时） | 📋 待实施 |
| **HTTP 重试+超时** — `https.request` + retry + timeout | TTS (line 631-676) | AI去字幕 API 调用 | 📋 待实施 |
| **模块命名空间** — `App.Config / Storage / Services / UI` + `do...end` 隔离 | TTS | 交付自检（检查函数增多时） | 💭 远期 |
| **JSON 持久化** — `dkjson` + `_save()` 模式 | TTS (line 578-600) | 交付自检 config.json 改进 | 💭 远期 |
| **Tab 式 UI** — 编辑/翻译/设置三 Tab | Sub Editor | 交付自检（分组即隐式 Tab） | ✅ 已有 |
| **多 LLM 提供者** — 统一接口对接多个 AI 后端 | Sub Editor | AI换口型/AI校对 | 💭 远期 |
| **双语 UI** | Sub Editor | — | ❌ 跳过 |
| **免费/付费分层** | Sub Editor | — | ❌ 跳过 |
