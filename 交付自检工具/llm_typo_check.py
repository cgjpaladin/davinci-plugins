#!/usr/bin/env python3
"""LLM 错别字校对 — 多供应商自动降级。

用法:
    from llm_typo_check import check_typos
    r = check_typos(asr_lines, context_lines)

注意: AI 结果不做缓存。剧本解析的缓存由 script_parser 管理。
"""

import json
import os
from llm_providers import call_with_fallback

# (硬过滤暂关，等模型稳定后再启用)
# _FUZZY_PAIRS = {...}


def check_typos(asr_lines: list[str],
                context_lines: list[str] = None,
                timeline_name: str = "", episode: str = "",
                system_candidates: str = "", cpl: int = 0) -> dict:
    """校对 ASR 字幕。分任务双跑：P1 查 8 类错误（不含断句），P2 专注断句。

    DS V4 Pro 200K 上下文，不截断不分批。
    cpl: 达芬奇字幕单行字数上限（0=无限制）

    Returns:
        {"ok": True, "corrections": [{index, original, correction, reason}]}
    """
    if not asr_lines or all(not t.strip() for t in asr_lines):
        return {"ok": True, "corrections": [], "provider": "none", "same_show": True}

    context_lines = context_lines or []

    # P1: 8 类错误，temp=0.2（0.15以下过于保守，模型会忽略系统候选）
    r1 = _single(asr_lines, context_lines, offset=0,
                 timeline_name=timeline_name, episode=episode,
                 system_candidates=system_candidates, cpl=cpl, temperature=0.2,
                 rules_subset=[1,2,3,4,5,6,7,8])
    # P2: 仅断句，temp=0.25（0.2有1/3概率跑出空结果）
    r2 = _single(asr_lines, context_lines, offset=0,
                 timeline_name=timeline_name, episode=episode,
                 system_candidates=system_candidates, cpl=cpl, temperature=0.25,
                 rules_subset=[9])

    if not r1.get("ok") and not r2.get("ok"):
        return r1

    # 并集去重
    c1 = r1.get("corrections", []) if r1.get("ok") else []
    c2 = r2.get("corrections", []) if r2.get("ok") else []
    seen = set()
    merged = []
    for c in c1:
        key = (c.get("index"), c.get("original"))
        if key not in seen:
            seen.add(key)
            c["_pass"] = 1
            merged.append(c)
    for c in c2:
        key = (c.get("index"), c.get("original"))
        if key not in seen:
            seen.add(key)
            c["_pass"] = 2
            merged.append(c)

    return {"ok": True, "corrections": merged,
            "same_show": r1.get("same_show", True),
            "provider": r1.get("provider") or r2.get("provider", "?"),
            "model": r1.get("model") or r2.get("model", "?"),
            "_passes": 2,
            "usage": {
                "total_tokens": (r1.get("usage", {}).get("total_tokens", 0) +
                                 r2.get("usage", {}).get("total_tokens", 0)),
                "prompt_tokens": (r1.get("usage", {}).get("prompt_tokens", 0) +
                                  r2.get("usage", {}).get("prompt_tokens", 0)),
                "completion_tokens": (r1.get("usage", {}).get("completion_tokens", 0) +
                                     r2.get("usage", {}).get("completion_tokens", 0)),
            },
            "_raw1": r1.get("_raw", ""),
            "_raw2": r2.get("_raw", "")}


def _single(asr_lines, context_lines, offset=0, timeline_name="", episode="", system_candidates="", cpl=0, temperature=0, rules_subset=None):
    asr_list = "\n".join(f"[{offset + i + 1}] {t}" for i, t in enumerate(asr_lines))
    context = "\n".join(context_lines) if context_lines else ""

    if rules_subset is None:
        rules_subset = list(range(1, 10))

    # ── 规则文本（按编号）──
    _rules = {
        1: ("1. 人名写错\n"
            "    从剧本人物小传提取角色名。字幕出现同音/形近错误时修正：\n"
            "    • 叶珠校长宣布 → 叶姝校长宣布（剧本角色名是「叶姝」）\n"
            "    • 肖寒教授的研究 → 萧寒教授的研究（剧本角色名是「萧寒」）\n"
            "    • 江念念的新项链 → 姜念念的新项链（剧本角色名是「姜念念」）\n"),
        2: ("2. 的/地/得 混用\n"
            "    • 他轻而易举的救了她 → 他轻而易举地救了她（副词修饰动词用「地」）\n"
            "    • 我哪里做的不够好 → 我哪里做得不够好（动词后补语用「得」）\n"
            "    • 她轻轻的拍了拍他肩膀 → 她轻轻地拍了拍他肩膀（副词修饰动词用「地」）\n"
            "    • 这是我妈妈包的饺子 → 不改（名词前定语用「的」是对的）\n"),
        3: ("3. 他/她/它 性别错配\n"
            "    根据上下文/剧本人物小传确定性别：\n"
            "    • 她是我的前男友 → 他是我的前男友（前男友是男性）\n"
            "    • 他好大的胆子 → 她好大的胆子（根据上下文指姜念念，姜念念是女主）\n"),
        4: ("4. 英文缩写。例：NBA→美国职业篮球联赛、ICU→重症监护室\n"
            "    • 韩经理觉得OK → 不改（OK 已融入日常汉语）\n"),
        5: ("5. 标点或空格缺失\n"
            "    • 《》用于书籍、影视作品名、项目名（如《修罗血玉》）\n"
            "    • 「」用于引述话语、特定命名、口号：\n"
            "      那块牌匾上写着妙手回春 → 那块牌匾上写着「妙手回春」（牌匾刻字）\n"
            "      她送我一块刻着如意的玉佩 → 她送我一块刻着「如意」的玉佩（器物命名）\n"
            "      我等你这句话我等了足足三年 → 「我等你」这句话我等了足足三年（直接引语）\n"
            "      这就是他说的重要项目 → 这就是他说的「重要项目」（间接引述）\n"
            "    • 短剧字幕不应出现逗号句号问号感叹号顿号分号，去掉即可：\n"
            "      好的吧。→ 好的吧（去掉句号）\n"
            "      你干什么？→ 你干什么（去掉问号）\n"
            "      这，这就算了 → 这 这就算了（去掉逗号，停顿用空格代替）\n"),
        6: ("6. 中国境内真实地名（省/市/县/区）\n"
            "   系统词典已覆盖全国 390+ 城市名，候选列表中已标出。\n"
            "   correction 写「应替换为架空地名」，不编造具体名字。\n"
            "   外国地名不报（短剧里通常是剧情需要）。\n"),
        7: ("7. 错别字/多字/漏字\n"
            "    常见错别字（音近/形近字）：\n"
            "    • 有什么事情咱们回去在说 → 有什么事情咱们回去再说（在=位置，再=重复）\n"
            "    • 你们两之间的事 → 你们俩之间的事（两=数字，俩=两个人）\n"
            "    • 他把戒指带在手上炫耀 → 他把戒指戴在手上炫耀（带=携带，戴=佩戴）\n"
            "    • 她拿我项链带了几天 → 她拿我项链戴了几天（带=携带，戴=佩戴）\n"
            "    • 你先上后头座会吧 → 你先上后头坐会吧（座=座位，坐=动词）\n"
            "    • 她象个没事人一样回来了 → 她像个没事人一样回来了（象=动物，像=相似）\n"
            "    • 叶姝侯在办公室等着他 → 叶姝候在办公室等着他（侯=姓氏，候=等待）\n"
            "    • 你先管好自已在说 → 你先管好自己再说（己=自己，已=已经）\n"
            "    • 数你嘴甜就知道哄我 → 属你嘴甜就知道哄我（数=数学，属=属于/算是）\n"
            "    • 我们即然已经决定了 → 我们既然已经决定了（即=当即，既=已经）\n"
            "    • 你以为末来还很远 → 你以为未来还很远（未=没有，末=结尾）\n"
            "    • 你先分辩清楚再说 → 你先分辨清楚再说（辨=区分，辩=争论）\n"
            "    • 全场商品全部打拆 → 全场商品全部打折（折=折扣，拆=拆卸）\n"
            "    • 你鬼鬼崇崇在干什么 → 你鬼鬼祟祟在干什么（祟=作祟，崇=崇高）\n"
            "    • 你做的一切都是为了他 → 不改（做=执行，此处正确）\n"
            "    • 忘带门禁卡了 → 不改（带=携带，此处正确）\n"
            "    多字：\n"
            "    • 她到底为什什么这样 → 她到底为什么这样（重复字）\n"
            "    • 你别太过分了了 → 你别太过分了（重复字）\n"
            "    漏字：\n"
            "    • 萧教迟早受不了她 → 萧教授迟早受不了她（缺字）\n"
            "    • 们先出去等着我要单独谈 → 我们先出去等着我要单独谈（缺人称，根据上下文此处是「我们」）\n"),
        8: ("8. 脏话/涉政词\n"
            "    系统候选列表中的违禁词全部报出，具体过滤规则见下方「审查系统候选」。\n"),
        9: ("断句错误。\n"
            "    只报两字词被换行切开的情况。\n\n"
            "    应报（两字是一个词被拆）：\n"
            "    •「她慢慢地拿起桌上的文|件签下了名字」→「文件」是一个词\n"
            "    •「叶姝发|呆了好一阵才回过神来」→「发呆」是一个词\n"
            "    •「我就是要让他被学术界永|远除名」→「永远」是一个词\n"
            "    •「刚才念念把咖啡洒在座|位上了」→「座位」是一个词\n"
            "    •「董事们面面相觑却不|敢出声反对」→「不敢」是一个词\n"
            "    •「姜念念假装不经意地靠|近萧寒的驾驶座」→「靠近」是一个词\n"
            "    •「这个项目的进展已经来|不及挽回」→「来不及」是一个词\n\n"
            "    不应报（断点在子句/语法边界，各自通顺）：\n"
            "    •「今天召集各位董事开会｜是要宣布一件事」→因果句读\n"
            "    •「我们结婚七年｜你的副驾驶除了我｜还坐过别人吗」→排比停顿\n"
            "    •「项目一团乱麻｜你也病成这个样子｜这个结果你满意了」→并列短句\n"
            "    •「这是你亲手烧制的｜我们的第一个对杯」→同位语\n"
            "    •「现在我要收回属于我的东西｜需要向你解释吗」→反问\n"
            "    •「说拿走就拿走了｜没有我的资金」→语义转接\n"
            "    •「如果｜你愿意回来」→如+果各自独立成词\n\n"
            "    宁可保守：吃不准就不报。\n"
            + (f"    若修正后某句字数 >{cpl}且无法再分，则不报。\n" if cpl > 0 else "") +
            "    original 和 correction 都写两句，用 ｜ 分隔。\n"),
    }
    rules_section = "\n".join(_rules[r] for r in rules_subset if r in _rules)

    # ── JSON 示例（按规则过滤）──
    _examples = {
        1: '  {"index": 21, "original": "冰言给我出来", "correction": "冰颜给我出来", "reason": "冰言→冰颜，剧本角色是冰颜"},\n'
           '  {"index": 22, "original": "林页轻而易举的救了她", "correction": "林野轻而易举地救了她", "reason": "林页→林野，的地得"},\n',
        2: '  {"index": 55, "original": "他轻而易举的救了她", "correction": "他轻而易举地救了她", "reason": "的地得"},\n',
        3: '  {"index": 28, "original": "他是我的妻子", "correction": "她是我的妻子", "reason": "他是她——性别不对"},\n',
        4: '  {"index": 12, "original": "他是NBA球员", "correction": "他是美国职业篮球联赛球员", "reason": "NBA——建议用中文全称"},\n',
        5: '  {"index": 36, "original": "修罗血玉是本好书", "correction": "《修罗血玉》是本好书", "reason": "去掉句号"},\n'
           '  {"index": 45, "original": "你干什么？", "correction": "你干什么", "reason": "去掉句号"},\n',
        6: '  {"index": 42, "original": "我来自北京", "correction": "应替换为架空地名", "reason": "北京——应替换为架空地名"},\n',
        7: '  {"index": 14, "original": "他要五仟万", "correction": "他要五千万", "reason": "在当作再用——在指位置"},\n',
        8: '  {"index": 1, "original": "习近平", "correction": "请结合剧情自行判断", "reason": "他妈的——违禁词"},\n'
           '  {"index": 2, "original": "你他妈敢打老子", "correction": "你敢打我", "reason": "他妈的——违禁词"},\n',
        9: '  {"index": 10, "original": "我时常幻想如果｜我是一个亿万富翁", "correction": "我时常幻想｜如果我是一个亿万富翁", "reason": "两字词被换行切开"},\n'
           '  {"index": 30, "original": "我知道你今｜天救了我们两次", "correction": "我知道你｜今天救了我们两次", "reason": "两字词被换行切开"},\n'
           '  {"index": 3, "original": "她慢慢地拿起桌上的文｜件签下了名字", "correction": "她慢慢地拿起桌上的｜文件签下了名字", "reason": "两字词被换行切开"}\n',
    }
    examples_section = "".join(_examples[r] for r in rules_subset if r in _examples)

    # ── 系统候选段（P1 包含，P2 不需要）──
    system_section = ""
    if 1 in rules_subset:  # P1 才显示系统候选
        system_section = (
            "### 3. 审查系统候选\n"
            "用户消息末尾有候选列表，含两类：\n"
            "① 违禁词：系统词典已检出。**全部报出**（reason=违禁词），仅排除以下误报：\n"
            "- 候选含「逼」→ 原文是「逼我/逼迫/逼供」→ 不报（强迫义）\n"
            "  原文是「逼人/死逼/傻逼」→ 报（骂人义）\n"
            "- 候选含「奶」→ 原文是「姑奶奶」→ 不报（称呼）\n"
            "- 候选含「八九」→ 在计数中（一二三四五六七八九十）→ 不报\n"
            "- 候选含「你妈」→ 原文是「你妈妈最近身体如何」→ 不报（称呼）\n"
            "② 真实地名：系统词典覆盖全国 390+ 城市名。\n"
            "   标出即是中国真实地名，直接报，reason「真实地名」，\n"
            "   correction 写「应替换为架空地名」。\n"
            "   虚构地名（如苏城、王家庄）不会出现在候选里。\n"
        )

    # ── reason 字段说明 ──
    reason_line = ("- reason: 用一句 5-15 字的简短中文说明错误原因，如「什字重复」「的地得」「叶珠→叶姝」。\n"
                    "  不写标签，写错误本身。\n")

    messages = [
        {"role": "system", "content": (
            "你是短剧字幕校对专家。输出 JSON 格式。\n"
            "只找字幕里真正的语文错误。\n\n"
            "## 剧本怎么用\n"
            "剧本只帮你做三件事：①知道角色名和性别 ②理解剧情大纲和故事背景\n"
            "③理解当前这场戏以及上下文在讲什么。\n"
            "除此之外，不要拿剧本和字幕逐字比对。演员不一定按剧本念台词。\n"
            "所有修正理由只能来自字幕本身——错字、不通顺、词用错了、断句坏了。\n\n"
            "## 你会收到什么\n\n"
            "用户消息包含：\n"
            "① 剧本全文 — 用于理解故事背景、人物关系、语境\n"
            "② 时间线名称 — 用于自动判断当前剧集\n"
            "③ 字幕行 — [序号] 文本格式\n"
            "④ 系统检测候选 — 可能为空（系统词典的关键词匹配结果）\n\n"
            "## 你要做什么（以下列为准，无其他隐藏规则）\n\n"
            "### 1. 先判断 same_show（必须第一步完成）\n"
            "严格比对：\n"
            "- 提取字幕中所有人名\n"
            "- 提取剧本中所有人名\n"
            "- 至少 2 个名字同时出现 → same_show=true\n"
            "- 剧本不含人物故事（技术文档/表格/笔记/代码/README等）→ false\n"
            "- 剧本标题与字幕时间线主题明显不同且无人名重叠 → false\n"
            "- 不确定 → false。宁可漏判，不可误判。\n"
            "⚠ 无论 same_show 结果，之后仍须逐行校对字幕。\n\n"
            "### 2. 读角色背景（same_show=true 才有意义）\n"
            "剧本开头一般有「人物小传」或「人物简介」段落，从中提取角色名和性别。\n"
            "剧本为全文纯文本，以「第N集」段落标题自然分隔各集。根据时间线名称判断集号\n"
            "（如 EP03_剪辑_v01 → 第3集）。\n"
            "除匹配集外也读前后各一集（第3集→也读第2、4集），理解剧情连贯性。\n\n"
            "### 3. 逐行检查字幕\n"
            "找出以下语文错误（reason 必须是括号内的精确值）：\n\n"
            + rules_section +
            "\n注意：换行/轨间分隔属于系统检测范畴，你不需处理。\n"
            "correction 中可以添加《》「」，但不要添加逗号句号等标点。\n\n"
            + system_section +
            "\n### 4. 这些情况不报\n"
            "- 相邻字幕内容相同（连续两声「姐妹们」）→ 口语重复\n\n"
            "## 输出字段说明\n\n"
            "- index: 字幕行号（从1开始）\n"
            "- original: 完整字幕文本（整句）\n"
            "- correction: 修正后的完整字幕文本（整句）\n"
            + reason_line +
            "- same_show: 必须输出。\n"
            "  ① 在剧本和字幕中分别找到至少 1 个共同人物名 → true\n"
            "  ② 剧本不是人物故事（技术文档/表格/笔记/代码等）→ false\n"
            "  ③ 不确定或条件不足 → false。宁可漏判不可误判。\n"
            "  ⚠ 即使 same_show=false，仍须逐字校对字幕错别字，不可跳过。same_show 仅作参考标志。\n\n"



            "## 输出格式\n\n"
            '{"same_show": true, "corrections": [\n'
            + examples_section +
            "]}\n"
            "无错误：{\"same_show\": true, \"corrections\": []}"
        )},
        {"role": "user", "content": (
            "剧本全文：\n__C__\n\n"
            "时间线：__T__\n\n"
            "字幕（[序号]）：\n__A__"
        ).replace("__C__", context).replace("__T__", timeline_name)
         .replace("__A__", asr_list)
         + ("" if not system_candidates else (
            "\n\n## 系统候选\n\n"
            "以下被系统词典标出。结合上下文判断：\n"
            + system_candidates
         ))},
    ]

    result = call_with_fallback(messages, max_tokens=16384, temperature=temperature,
                                response_format={"type": "json_object"})
    if not result.get("ok"):
        return result

    try:
        raw = result["content"].strip()
        # 清理 markdown 代码块
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        # 从第一个 { 到最后一个 }，忽略前后文字
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
        data = json.loads(raw)
        # 对象格式 {same_show, corrections} 或数组 [{...}]
        if isinstance(data, dict):
            same_show = data.get("same_show")
            if same_show is None:
                same_show = True  # null → 默认true
            corrections = data.get("corrections", [])
        elif isinstance(data, list):
            same_show = True
            corrections = data
    except json.JSONDecodeError:
        # 截断容错：尝试补全缺失的括号
        raw_stripped = raw.strip()
        open_braces = raw_stripped.count("{") - raw_stripped.count("}")
        open_brackets = raw_stripped.count("[") - raw_stripped.count("]")
        try:
            fixed = raw_stripped + "}" * open_braces + "]" * open_brackets
            data = json.loads(fixed)
            corrections = data.get("corrections", data if isinstance(data, list) else [])
        except Exception:
            return {"error": "json_parse", "raw_tail": raw[-80:]}
        else:
            raise ValueError
        if not isinstance(corrections, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": "json_parse",
                "raw": result["content"][:300],
                "raw_tail": result["content"][-100:],
                "detail": str(e)}

    valid = []
    max_idx = offset + len(asr_lines)
    for c in corrections:
        idx = c.get("index", -1)
        if not isinstance(idx, int) or idx < offset + 1 or idx > max_idx:
            continue
        orig = str(c.get("original", ""))
        corr = str(c.get("correction", ""))
        if orig == corr:
            continue
        ## 硬过滤（暂关，先看模型能力）
        # def _norm(s): return s.replace(" ", "").replace("……", "").replace("...", "")
        # if _norm(orig) == _norm(corr):
        #     continue
        # if (orig, corr) in _FUZZY_PAIRS or (corr, orig) in _FUZZY_PAIRS:
        #     continue
        # full = asr_lines[idx - offset - 1] if idx - offset - 1 < len(asr_lines) else ""
        # if corr and corr in full:
        #     continue
        reason = str(c.get("reason", "")).strip()
        # 归一化: AI 偶尔把「错别字」写成「错字」
        reason = reason.replace("错字", "错别字")
        valid.append({
            "index": idx, "original": orig,
            "correction": corr,
            "reason": reason,
        })

    return {"ok": True, "corrections": valid,
            "same_show": same_show if same_show is not None else True,
            "provider": result["provider"], "model": result["model"],
            "usage": result.get("usage", {}),
            "_raw": result["content"][:500]}
