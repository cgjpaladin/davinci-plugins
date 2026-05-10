# LLM 字幕校对 — 方案设计

> 2026-05-10 | 待开工

## 场景

短剧字幕为语音转写（ASR）生成，常有同音字、漏字、多字。剪辑师拿到 ASR 字幕后需逐句校对，费时。

能提供剧本原文，将 ASR 产出与剧本对齐后送 LLM 比对，自动发现转录错误。

## 流程

```
达芬奇时间线
  ↓ GetName/GetStart/GetEnd
字幕文本列表 [{tc, text}, ...]
  ↓ 对齐（按文本相似度分到最近的剧本段落）
剧本段落 [{scene, text}, ...]
  ↓ 分批（每批 20 条字幕）
LLM API（千问 Max / 豆包 Pro）
  ↓ JSON 解析
[{tc, asr, correct, reason}, ...]
  ↓ 组装 check_core 结果
Tree: ❌ 00:01:23:05 | 在呼 → 在乎 | 同音字
```

## 核心模块

### 1. 字幕读取
- 遍历字幕轨，取 `GetName()` 得到文本
- 记录时码、轨道位置

### 2. 剧本对齐
- 剧本可以是 TXT 或飞书文档
- 对齐策略：用模糊匹配（difflib.SequenceMatcher）将每条 ASR 字幕匹配到最近的剧本行
- 匹配不到的行跳过（可能是即兴台词）

### 3. LLM 调用
- API：千问 Max（¥0.004/1K tok）或豆包 Pro
- 只用标准库 `urllib`，不引入 pip 依赖
- 请求体：system prompt + 剧本上下文 + ASR 字幕列表
- 要求 LLM 返回 `[{index, asr, correct, reason}]` JSON
- 关键 prompt 约束：
  - 只报确实有问题的
  - 不确定的不报
  - 忽略标点差异
  - 忽略合理同义改写

### 4. 缓存
- 按字幕文本 hash 缓存
- 同一时间线重跑不花钱
- 存 `~/Library/Application Support/交付自检/typo_cache.json`

### 5. check_core 集成
- `check_subtitle_typo()` 函数
- io_range 支持
- detail = `"{asr} → {correct}"`
- reason = `"{reason}"`
- CHECKS 注册：`"id": "typo", "section": "ASR校对", "group": "字幕"`

## 成本估算

| 场景 | 条数 | tokens | 费用 |
|------|------|--------|------|
| 200 条字幕 | 200 | ~4K | **¥0.016** |
| 500 条字幕 | 500 | ~10K | **¥0.040** |
| 1000 条字幕 | 1000 | ~20K | **¥0.080** |

一次检查 ≤ 一毛钱。

## API key 管理

- `.env` 文件，不提交 git
- `DASHSCOPE_API_KEY`（千问）或 `DOUBAO_API_KEY`（豆包）
- 启动时从 `.env` 加载

## 待定决策

| 问题 | 选项 | 建议 |
|------|------|------|
| 模型 | 千问 Max / 豆包 Pro / 混元 | 千问 Max（阿里云百炼节点稳） |
| 剧本来源 | 飞书文档链接 / 本地 TXT / 达芬奇 Marker | 先做本地 TXT |
| 对齐方式 | 模糊匹配 / LLM 对齐 / 时间码对齐 | 先做模糊匹配 |
| 默认启停 | 每次检查都跑 / CheckBox 独立控制 | 独立 CheckBox，默认不打勾 |

## 实施步骤

1. 写 `_call_typo_llm()` — urllib 调千问 API，20 行
2. 写 `_align_to_script()` — 模糊匹配，30 行
3. 写 `check_subtitle_typo()` — 组装结果，40 行
4. ui.py 加 runner + CHECKS 注册，5 行
5. 达芬奇实测，调 prompt
6. 上线
