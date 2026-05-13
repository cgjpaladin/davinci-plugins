# LLM 校对复盘流程

> 2026-05-14 小裁缝 编写
> 使用方法：新建 WorkBuddy 会话 → 粘贴本文 → 直接开始复盘

## 数据在哪

| 数据 | 路径 |
|------|------|
| LLM 存档 | `~/Library/Application Support/交付自检/typo_sessions/{项目}/{时间线}/{时间戳}.json` |
| 交付 SRT | SMB: `01_Project/{项目}/11_导出/{项目}_交付版本合集/10_SRT 字幕/*.srt` |
| 对比引擎 | `shared/typo_audit.py` |

## 执行步骤

### 1. 运行对比引擎

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊
python3 shared/typo_audit.py
```

输出：每个项目的差异报告（Markdown 表格）

### 2. 裁缝老师看报告

告诉小裁缝规律，例如：
- "XX 项目的人名总是被 LLM 误报"
- "的地得还是漏，这几集全都没报"

### 3. 小裁缝改提示词

修改 `shared/llm_typo_check.py` 中 `_single()` 的 prompt，提交本地 → 裁缝老师测 → 确认后 push

### 4. 重复

每个项目交付完跑一次对比，积攒规律。

## 技术细节

对比引擎做的事：
1. 扫描所有 typo_sessions
2. 按项目名匹配 SMB 的 10_SRT 字幕/ 文件夹
3. 按时间码对齐 LLM 结果和 SRT 条目
4. 分类统计：✅采纳 / ❌误报 / ⚠️漏报
5. 输出 Markdown 报告

## 边界处理

- 项目名 sanitize 匹配（存档去掉了特殊字符，SMB 路径有特殊字符）
- 时间码对齐（LLM 的 index 不可靠，用 start_frame 匹配 SRT 时间码）
- 外包项目无工程 → 不存 typo_sessions → 不参与复盘
