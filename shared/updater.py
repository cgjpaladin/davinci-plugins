# -*- coding: utf-8 -*-
"""自动更新检查器 — 纯标准库，多链路回退。

启动时按优先级依次尝试多个 URL 获取 version.json，
检测到新版本时返回更新信息。与交付自检、批量命名等共用。
"""
import json
import os
import ssl
import base64
from urllib.request import Request, urlopen
from urllib.error import URLError

from update_config import (
    VERSION_CHECK_URLS, TIMEOUT_VERSION_CHECK,
)

# 可通过环境变量覆盖第一条链路
_env_url = os.environ.get("WB_VERSION_URL")
if _env_url:
    VERSION_CHECK_URLS = [_env_url] + VERSION_CHECK_URLS

_SSL_CTX = ssl._create_unverified_context()


def _fetch_text(url: str, timeout: float = 5.0) -> str:
    """GET 一个 URL，返回文本。失败抛异常。"""
    req = Request(url, method="GET")
    req.add_header("User-Agent", "DaVinciPlugin/updater")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read().decode("utf-8")


def _fetch_json_across_links(urls: list, timeout: float = 5.0) -> dict:
    """按优先级依次尝试各 URL，返回第一个成功解析的 JSON dict。"""
    for url in urls:
        try:
            raw = _fetch_text(url, timeout=timeout)
            data = json.loads(raw)
            # GitHub API 响应格式: {content: base64, encoding: "base64"}
            if isinstance(data, dict) and data.get("encoding") == "base64":
                data = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
            return data
        except Exception:
            continue
    raise RuntimeError("所有更新链路均不可达")


def check(product: str, current_version: str,
          on_update_found=None, timeout: float = None) -> dict:
    """检查更新。

    Args:
        product: 产品标识（"delivery_checker" / "batch_renamer"）
        current_version: 当前版本号，如 "2.1.1-dev"
        on_update_found: 回调 (latest_version, download_url, notes)
        timeout: 每条链路超时秒数

    Returns:
        {"update_available": bool, "latest": str, "url": [str, ...], "notes": str, "sha256": str|null}
    """
    from update_config import VERSION_CHECK_URLS, TIMEOUT_VERSION_CHECK, DOWNLOAD_URLS
    if timeout is None:
        timeout = TIMEOUT_VERSION_CHECK
    try:
        data = _fetch_json_across_links(VERSION_CHECK_URLS, timeout=timeout)
    except RuntimeError as e:
        return {"update_available": False, "reason": str(e)[:100]}
    except URLError as e:
        return {"update_available": False, "reason": f"网络不可达: {e}"}
    except json.JSONDecodeError:
        return {"update_available": False, "reason": "版本文件格式错误"}
    except Exception as e:
        return {"update_available": False, "reason": str(e)[:100]}

    # 兼容 Releases API 格式: {tag_name, body, assets, ...}
    if isinstance(data, dict) and "tag_name" in data and "assets" in data:
        tag = data["tag_name"].lstrip("v")
        notes = data.get("body", "")
        # 从 assets 找下载链接
        dl_urls = []
        for a in data.get("assets", []):
            url = a.get("browser_download_url", "")
            if not url: continue
            # ghproxy 优先
            if "github.com" in url:
                dl_urls.append("https://ghproxy.net/" + url)
            dl_urls.append(url)  # 直连兜底
        if not dl_urls:
            dl_urls = DOWNLOAD_URLS
        # 提取 SHA256（如果有）
        sha256 = None
        for a in data.get("assets", []):
            if a.get("name", "").endswith(".sha256"):
                # 有 .sha256 文件可尝试下载
                pass
        data = {
            product: {
                "version": tag,
                "notes": notes,
                "urls": dl_urls,
                "sha256": sha256,
            }
        }

    latest_info = data.get(product)
    if not latest_info:
        return {"update_available": False, "reason": f"产品 {product} 未找到"}

    latest_version = latest_info.get("version", "")
    if _version_compare(latest_version, current_version) > 0:
        dl_raw = latest_info.get("urls") or latest_info.get("url", "")
        dl_urls = dl_raw if isinstance(dl_raw, list) else ([dl_raw] if dl_raw else [])

        # 累积公告：从 notes/history 中过滤比当前版本新的所有公告
        notes = latest_info.get("notes", "")
        history = latest_info.get("history", [])
        if not history and notes:
            # 解析 notes 中的 "## vX.Y.Z" 标题来构建 history
            import re
            sections = re.split(r'(?=## v\d)', notes)
            history = []
            for sec in sections:
                m = re.search(r'v(\d+\.\d+\.\d+)', sec)
                if m:
                    history.append({"version": m.group(1), "notes": sec.strip()})
        if history:
            relevant = [h["notes"] for h in history
                        if _version_compare(h["version"], current_version) > 0]
            if relevant:
                notes = "\n\n".join(relevant)

        result = {
            "update_available": True,
            "latest": latest_version,
            "urls": dl_urls,
            "notes": notes,
            "sha256": latest_info.get("sha256"),
            "force": latest_info.get("force", False),
        }
        if on_update_found:
            try:
                on_update_found(latest_version, dl_urls[0] if dl_urls else "",
                                latest_info.get("notes", ""))
            except Exception:
                pass
        return result

    return {"update_available": False, "latest": latest_version}


def check_async(product: str, current_version: str, on_update_found=None):
    """后台线程中检查更新，不阻塞启动。"""
    import threading
    import logging

    def _run():
        result = check(product, current_version, on_update_found, timeout=5.0)
        if result.get("update_available"):
            log = logging.getLogger("WB.updater")
            log.info(f"新版本可用: {result['latest']}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _version_compare(a: str, b: str) -> int:
    """比较两个 semver 版本号。a > b → 1, a == b → 0, a < b → -1。"""
    def _parse(v):
        v = v.strip().lstrip("v")
        parts = v.replace("-", ".").split(".")
        nums = []
        for p in parts:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        return nums

    try:
        return (_parse(a) > _parse(b)) - (_parse(a) < _parse(b))
    except Exception:
        return 0
