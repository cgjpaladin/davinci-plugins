#!/usr/bin/env python3
"""多供应商 LLM 调用 — 统一接口 + 自动降级。

供应商配置为纯数据，新增只用加一行。

用法:
    from llm_providers import call_with_fallback
    result = call_with_fallback(messages)
    # → {"ok": True, "content": "...", "provider": "qwen", "model": "qwen-turbo"}
"""

import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ══════════════════════════════════════
# 供应商配置（新增供应商只加这里）
# ══════════════════════════════════════

_providers = [
    # DeepSeek V4 Flash（优先，纠错强 + 指令跟随好）
    {"name": "deepseek-v4-flash", "priority": 1, "vendor": "deepseek",
     "url": "https://api.deepseek.com/v1/chat/completions",
     "key_env": "DEEPSEEK_API_KEY", "format": "openai",
     "extra_body": {"thinking": {"type": "disabled"}}},

    # 千问 Plus（备用）
    {"name": "qwen-plus",      "priority": 2, "vendor": "qwen",
     "url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
     "key_env": "DASHSCOPE_API_KEY", "format": "dashscope"},

    # 智谱 GLM-4-Flash（第三备用，免费额度）
    {"name": "glm-4-flash",    "priority": 3, "vendor": "zhipu",
     "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
     "key_env": "ZHIPU_API_KEY", "format": "openai"},
]

# 重试错误码
_RETRY_CODES = {"Throttling.User", "Throttling.Allocation", "Arrearage",
                "rate_limit_exceeded", "insufficient_quota"}
_FATAL_CODES = {"InvalidApiKey", "DataInspectionFailed", "invalid_api_key"}


def _get_key(env_name: str) -> str:
    """读 SMB .env → 本地 .env → 环境变量。"""
    paths = [
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
        os.path.expanduser("~/.workbuddy/.env"),
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{env_name}="):
                        return line.split("=", 1)[1].strip().strip('"')
        except FileNotFoundError:
            continue
    return os.environ.get(env_name, "")


def _call_dashscope(cfg: dict, messages: list[dict],
                    max_tokens: int, temperature: float) -> dict:
    """千问 DashScope 格式。"""
    api_key = _get_key(cfg["key_env"])
    if not api_key:
        return {"error": "no_key", "vendor": "qwen"}

    body = json.dumps({
        "model": cfg["name"],
        "input": {"messages": messages},
        "parameters": {
            "result_format": "message",
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    }).encode("utf-8")

    req = Request(_providers[0]["url"], data=body)  # same URL for all qwen
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"error": f"http_{e.code}"}
    except URLError as e:
        return {"error": "network", "message": str(e)[:200]}

    code = data.get("code", "")
    if code:
        return {"error": "api_error", "code": code, "message": data.get("message", "")[:200]}

    try:
        content = data["output"]["choices"][0]["message"]["content"]
        return {"ok": True, "content": content, "model": cfg["name"]}
    except (KeyError, IndexError):
        return {"error": "parse"}


def _call_openai_compat(cfg: dict, messages: list[dict],
                        max_tokens: int, temperature: float) -> dict:
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
    # 合并供应商额外参数（如 DeepSeek thinking disabled）
    body_dict.update(cfg.get("extra_body", {}))

    body = json.dumps(body_dict).encode("utf-8")
    req = Request(cfg["url"], data=body)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"error": f"http_{e.code}"}
    except URLError as e:
        return {"error": "network", "message": str(e)[:200]}

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


def call_with_fallback(messages: list[dict], max_tokens: int = 512,
                       temperature: float = 0.1) -> dict:
    """多供应商自动降级调用。

    Returns:
        {"ok": True, "content": "...", "provider": "qwen", "model": "qwen-turbo"}
        或 {"error": "all_failed", "attempts": [...]}
    """
    attempts = []
    for p in sorted(_providers, key=lambda x: x["priority"]):
        if p["format"] == "dashscope":
            result = _call_dashscope(p, messages, max_tokens, temperature)
        else:
            result = _call_openai_compat(p, messages, max_tokens, temperature)

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
