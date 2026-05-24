# -*- coding: utf-8 -*-
"""
HTTP curl fallback — urllib 失败时自动切 curl 子进程。

达芬奇内置 Python 在某些环境下 SSL 链有问题（Unexpected EOF / certificate verify failed）。
curl 的子进程调用绕过 Python SSL 栈，作为兜底。
"""

import json
import os
import subprocess
from log_writer import get_logger

_log = get_logger(os.environ.get("WORKBUDDY_PRODUCT", "AI去字幕"))


def curl_post(url: str, headers: dict, data_bytes: bytes, timeout: int = 30) -> dict:
    """curl POST fallback。返回 JSON dict。"""
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-X", "POST", url]
    for k, v in headers.items():
        cmd.extend(["-H", f"{k}: {v}"])
    cmd.extend(["-d", "@-"])

    try:
        r = subprocess.run(
            cmd, input=data_bytes, capture_output=True,
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("curl fallback 超时")
    except FileNotFoundError:
        raise RuntimeError("curl 未安装（达芬奇环境无 curl）")

    if r.returncode != 0:
        raise RuntimeError(f"curl 失败({r.returncode}): {r.stderr.decode()[:200]}")

    try:
        return json.loads(r.stdout.decode())
    except json.JSONDecodeError:
        raise RuntimeError(f"curl 返回非 JSON: {r.stdout.decode()[:200]}")


def curl_get(url: str, headers: dict, timeout: int = 30) -> dict:
    """curl GET fallback。"""
    cmd = ["curl", "-sS", "--max-time", str(timeout), url]
    for k, v in headers.items():
        cmd.extend(["-H", f"{k}: {v}"])

    try:
        r = subprocess.run(
            cmd, capture_output=True,
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("curl fallback 超时")
    except FileNotFoundError:
        raise RuntimeError("curl 未安装（达芬奇环境无 curl）")

    if r.returncode != 0:
        raise RuntimeError(f"curl 失败({r.returncode}): {r.stderr.decode()[:200]}")

    try:
        return json.loads(r.stdout.decode())
    except json.JSONDecodeError:
        raise RuntimeError(f"curl 返回非 JSON: {r.stdout.decode()[:200]}")
