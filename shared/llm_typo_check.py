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
            "你是短剧字幕校对专家。检查 ASR 字幕中的错别字和不合理字词。\n\n"
            "规则：\n"
            "1. 先判断字幕是否来自剧本中的同一部剧。如果角色名、场景、情节完全不匹配，"
            "在 reason 中注明「⚠ 疑似不同剧集，请检查剧本」。\n"
            "2. 只报确实有错的。同音字是重点。\n"
            "3. 人名写错是最高优先级。正确人名：" + char_list + "\n"
            "4. 不要因和剧本不一致就报错——剧组可能改过台词。\n"
            "5. 忽略标点/断句差异/语气词增减。\n"
            "6. 方言/口音如果不是明显错字，不报。\n\n"
            "输出 JSON 数组 [{index, original, correction, reason}]。"
            "无错误输出 []。只输出 JSON。"
        )},
        {"role": "user", "content": (
            f"剧本上下文（仅供语义参考，不逐字比对）：\n{context}\n\n"
            f"ASR 字幕：\n{asr_list}\n\n找出错别字。"
            "如字幕与剧本明显非同一部剧，在第一个结果的 reason 中注明。"
        )},
    ]

    result = call_with_fallback(messages, max_tokens=512, temperature=0.1)
    if not result.get("ok"):
        return result

    try:
        raw = result["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        corrections = json.loads(raw)
        if not isinstance(corrections, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return {"error": "json_parse", "raw": result["content"][:500]}

    valid = []
    max_idx = offset + len(asr_lines)
    for c in corrections:
        idx = c.get("index", -1)
        if not isinstance(idx, int) or idx < offset + 1 or idx > max_idx:
            continue
        valid.append({
            "index": idx, "original": str(c.get("original", "")),
            "correction": str(c.get("correction", "")),
            "reason": str(c.get("reason", "")),
        })

    return {"ok": True, "corrections": valid,
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
