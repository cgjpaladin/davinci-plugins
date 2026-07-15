# 交付自检工具 DRY 审计报告（已验证）

> 2026-07-15 | 审计人：小裁缝 | 全部经过代码逐条验证

---

## 🔴 高危 (H1-H7)

| # | 问题 | 验证结果 | 实际影响 |
|:--:|------|:--:|------|
| H1 | 产品名"交付自检工具"硬编码 | ✅ 确认 | 源码级~10文件（不含build cache）。最大头：`build_personal.sh`(35次)、`install.command`(15次)、`ui.py`(12次) |
| H2 | 产品ID"delivery_checker"硬编码 | ✅ 确认 | ui.py 6处（WIN_ID/CONFIG_WIN_ID/更新/UA头/子进程代码字符串）+ install_agent.py 2处 |
| H3 | SMPTE 3处绕过_get_smpte缓存 | ✅ 确认 | check_core.py:582,644,785 直接`SMPTE()`。`_get_smpte`已定义缓存但3处未用 |
| H4 | 试用天数30天4次 | ✅ 确认 | ui.py:1132,1466,2622,3443 完全相同的`max(0,30-(today-tsd).days)`公式 |
| H5 | 违禁词CSV路径5次重复 | ✅ 确认 | ui.py:391,435,452,1561,1575（比报告多1次） |
| H6 | .env解析3文件独立实现 | ✅ 确认 | ui.py(3313-3347), launcher_personal.py(31-42), install_agent.py(196-204) |
| H7 | CONFIG_SECTIONS加项需改3处 | ✅ 确认 | list(6项)+builder dict(4项)+save elif(4种type)——添加须同时改3个位置，漏任一处即静默bug |

---

## 🟡 中危 (M1-M8)

| # | 问题 | 验证结果 | 实际影响 |
|:--:|------|:--:|------|
| M1 | 尾板关键词3处独立定义 | ✅ 确认 | check_core.py:1275(inline tuple),1334(inline),1719(变量`_tail_kw`)。三处完全相同的("未完待续","定格转场","全剧终") |
| M2 | _make_result_passthrough重复签名 | ✅ 确认 | check_core.py _make_result()与ui.py _make_result_passthrough()签名完全相同 |
| M3 | IS_PERSONAL已import却2处重读env | ✅ 确认 | ui.py:39读`os.environ.get("WORKBUDDY_PERSONAL")`，1069读`bool(os.environ.get(...))`，但已import `IS_PERSONAL` |
| M4 | config save/load手动双表 | ✅ 确认 | save/load字段一致(5项)，但新增字段需两处同步。当前同步性好——风险低 |
| M5 | ui.py SMPTE直接构造3次 | ✅ 确认 | ui.py:308,1986,2008-2010，均未用check_core的`_get_smpte` |
| M6 | 轨道为空检查模式重复 | ✅ 确认 | check_core.py多处`if track_count==0: return fail("无X轨道")`模式重复 |
| M7 | /Volumes/MYJC路径5文件散布 | ✅ 确认 | ui.py/launcher.py/shell.py/gray.sh/deploy_config.py |
| M8 | DaVinci系统路径前缀重复 | ✅ 确认 | 6+文件各自拼"Blackmagic Design/DaVinci Resolve" |

---

## 🟢 低危 (L1-L5)

| # | 问题 | 验证结果 |
|:--:|------|:--:|
| L1 | is_secret双重定义 | ✅ 确认 |
| L2 | _SCRIPT_DIR两模块各自定义 | ✅ 确认 |
| L3 | launcher Popen模式重复 | ✅ 确认 |
| L4 | _get_clip_name有函数未尽用 | ✅ 确认 |
| L5 | summary+extend模式多样 | ✅ 确认 |

---

## 结论

**20项全部经过代码验证，均真实存在。** 最紧迫的三项：H7（今天加遮幅时亲身踩过）、H4（改试用天数会漏改）、H1（改名是噩梦）。
