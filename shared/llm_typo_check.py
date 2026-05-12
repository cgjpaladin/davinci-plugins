#!/usr/bin/env python3
"""LLM 错别字校对 — 多供应商自动降级 + 缓存。

用法:
    from llm_typo_check import check_typos, check_typos_cached
    r = check_typos(asr_lines, characters, context_lines)
"""

import json
import os
import hashlib
import time
from llm_providers import call_with_fallback

_MAX_BATCH = 60
_MAX_CONTEXT = 60


def check_typos(asr_lines: list[str], characters: list[str],
                context_lines: list[str] = None) -> dict:
    """校对一批 ASR 字幕。超长自动分批。

    Returns:
        {"ok": True, "corrections": [{index, original, correction, reason}]}
    """
    if not asr_lines or all(not t.strip() for t in asr_lines):
        return {"ok": True, "corrections": [], "provider": "none"}

    context_lines = context_lines or []
    characters = characters or []

    if len(asr_lines) > _MAX_BATCH:
        all_c = []
        for start in range(0, len(asr_lines), _MAX_BATCH):
            batch = asr_lines[start:start + _MAX_BATCH]
            r = _single(batch, characters, context_lines, offset=start)
            if r.get("ok"):
                all_c.extend(r.get("corrections", []))
            else:
                return r
        return {"ok": True, "corrections": all_c,
                "provider": r.get("provider"), "model": r.get("model")}

    return _single(asr_lines, characters, context_lines, offset=0)


def _single(asr_lines, characters, context_lines, offset=0):
    asr_list = "\n".join(f"[{offset + i + 1}] {t}" for i, t in enumerate(asr_lines))
    char_list = "、".join(characters) if characters else "（无人物信息）"
    context = "\n".join(context_lines[:_MAX_CONTEXT]) if context_lines else "（无剧本上下文）"

    messages = [
        {"role": "system", "content": (
            "你是短剧字幕校对专家。只找字幕里的错别字。\n\n"
            "铁律：\n"
            "1. 逐条检查每条字幕，找其中的错别字。\n"
            "2. 只报明显的错别字（同音字/形近字/方言错写），如「在→再」「的→得」。\n"
            "3. 人名写错是最高优先级。参考人名：" + char_list + "\n"
            "4. 字幕怎么写的就怎么报。不要把字幕改写成剧本里的台词。\n"
            "5. original 和 correction 必须不同，且只改错的那个字。\n"
            "6. 「嗯」「啊」「哎」「诶」等语气词不算错。多余空格不报。\n\n"
            "same_show 含义：字幕中的人名、情节是否与剧本来自同一部剧。\n"
            "same_show=false 表示明显不是同一部剧。\n"
            "输出 JSON：{\"same_show\": true/false, \"corrections\": [{index, original, correction, reason}]}。只输出 JSON。"
        )},
        {"role": "user", "content": (
            f"剧本（仅用于判断是否同一部剧，不逐行对比字幕）：\n{context}\n\n"
            f"字幕：\n{asr_list}\n\n逐条检查每条字幕的错别字。不要改写，只报错字。"
        )},
    ]

    result = call_with_fallback(messages, max_tokens=1024, temperature=0.1)
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
            same_show = data.get("same_show", True)
            corrections = data.get("corrections", [])
        elif isinstance(data, list):
            same_show = True
            corrections = data
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
        # 硬过滤：纠正只是在去空格/加标点 → 跳过
        if orig.replace(" ", "") == corr.replace(" ", "").replace("……", "").replace("...", ""):
            continue
        # 硬过滤：纠正差异超过原句 50% → 不是错别字是改写
        if len(corr) > len(orig) * 1.5 or len(orig) > len(corr) * 1.5:
            continue
        valid.append({
            "index": idx, "original": orig,
            "correction": corr,
            "reason": str(c.get("reason", "")),
        })

    return {"ok": True, "corrections": valid,
            "same_show": same_show,
            "provider": result["provider"], "model": result["model"]}


# ── 缓存 ──

def _hash_lines(lines):
    return hashlib.sha256("\n".join(t.strip() for t in lines).encode()).hexdigest()[:16]


def check_typos_cached(asr_lines, characters, context_lines=None):
    cache_dir = os.path.expanduser("~/Library/Application Support/交付自检")
    cache_file = os.path.join(cache_dir, "typo_cache.json")
    h = _hash_lines(asr_lines)
    cache = {}
    try:
        os.makedirs(cache_dir, exist_ok=True)
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                cache = json.load(f) or {}
    except Exception:
        pass
    if h in cache:
        return cache[h]
    result = check_typos(asr_lines, characters, context_lines)
    if result.get("ok"):
        cache[h] = result
        try:
            if len(cache) > 500:
                oldest = sorted(cache, key=lambda k: cache[k].get("_ts", 0))[:100]
                for k in oldest:
                    del cache[k]
            result["_ts"] = time.time()
            with open(cache_file, "w") as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass
    return result
