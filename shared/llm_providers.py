#!/usr/bin/env python3
"""LLM 调用 — DeepSeek V4 Pro 单供应商。

用法:
    from llm_providers import call_with_fallback
    result = call_with_fallback(messages)
    # → {"ok": True, "content": "...", "model": "deepseek-v4-pro"}
"""

import json
import os
import ssl
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_SSL_CTX = ssl._create_unverified_context()

# ══════════════════════════════════════
# 供应商配置
# ══════════════════════════════════════

_providers = [
    # DeepSeek V4 Pro（唯一主力；关 thinking mode，校对是确定性任务）
    {"name": "deepseek-v4-pro", "priority": 1, "vendor": "deepseek",
     "url": "https://api.deepseek.com/v1/chat/completions",
     "key_env": "DEEPSEEK_API_KEY", "format": "openai",
     "extra_body": {"thinking": {"type": "disabled"}}},
]

# 重试错误码
_RETRY_CODES = {"Throttling.User", "Throttling.Allocation", "Arrearage",
                "rate_limit_exceeded", "insufficient_quota"}
_FATAL_CODES = {"InvalidApiKey", "DataInspectionFailed", "invalid_api_key"}


def _get_key(env_name: str) -> str:
    """读环境变量 → SMB .env → 本地 .env。"""
    # 环境变量优先（兼容个人版）
    v = os.environ.get(env_name, "")
    if v and v != "sk-xxxxxxxx":
        return v
    paths = [
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.startswith(f"{env_name}="):
                        v = line.split("=", 1)[1].strip().strip('"')
                        if v and v != "sk-xxxxxxxx":
                            return v
        except OSError:
            continue
    return ""


def _call_openai_compat(cfg: dict, messages: list[dict],
                        max_tokens: int, temperature: float,
                        response_format: dict = None) -> dict:
    """OpenAI 兼容格式（智谱、DeepSeek）。"""
    api_key = _get_key(cfg["key_env"])
    if not api_key:
        return {"error": "no_key"}

    body_dict = {
        "model": cfg["name"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        body_dict["response_format"] = response_format
    # 合并供应商额外参数（如 DeepSeek thinking disabled）
    body_dict.update(cfg.get("extra_body", {}))

    body = json.dumps(body_dict).encode("utf-8")
    req = Request(cfg["url"], data=body)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=300, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"error": f"http_{e.code}"}
    except URLError as e:
        reason = str(e)
        if "timeout" in reason.lower() or "timed out" in reason.lower():
            return {"error": "network_timeout", "message": "AI 接口响应超时（>300秒），请检查网络或稍后重试"}
        return {"error": "network", "message": reason[:200]}

    # OpenAI 兼容格式：choices[0].message.content
    try:
        content = data["choices"][0]["message"]["content"]
        return {"ok": True, "content": content, "model": cfg["name"]}
    except (KeyError, IndexError):
        pass

    # 智谱/DeepSeek 错误格式
    err = data.get("error", {})
    if err:
        return {"error": "api_error",
                "code": err.get("code", err.get("type", "unknown")),
                "message": err.get("message", "")[:200]}

    return {"error": "parse", "raw": str(data)[:200]}


def call_with_fallback(messages: list[dict], max_tokens: int = 2048,
                       temperature: float = 0.1,
                       response_format: dict = None) -> dict:
    """多供应商自动降级调用。

    Returns:
        {"ok": True, "content": "...", "provider": "qwen", "model": "qwen-turbo"}
        或 {"error": "all_failed", "attempts": [...]}
    """
    attempts = []
    for p in sorted(_providers, key=lambda x: x["priority"]):
        result = _call_openai_compat(p, messages, max_tokens, temperature,
                                     response_format=response_format)

        attempts.append({"model": p["name"], "result": result.get("error", "ok")})

        if result.get("ok"):
            return {"ok": True, "content": result["content"],
                    "provider": p["vendor"], "model": p["name"]}

        code = result.get("code", "")
        if code in _FATAL_CODES:
            continue  # key 废了，试下一个
        if code in _RETRY_CODES:
            continue  # 限流/欠费，试下一个
        # 其他错误（网络/解析），也试下一个

    return {"error": "all_failed", "attempts": attempts}
