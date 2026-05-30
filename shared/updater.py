# -*- coding: utf-8 -*-
"""自动更新检查器 — 纯标准库，零 pip。

启动时后台 GET version.json，检测到新版本时记录日志并通知 UI。
与交付自检、批量命名工具等共用同一个模块。
"""
import json
import os
import ssl
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError

# 版本检查 URL — GitHub API（api.github.com 在国内可达，且无缓存）
_VERSION_JSON_URL = os.environ.get(
    "WB_VERSION_URL",
    "https://api.github.com/repos/cgjpaladin/davinci-plugins/contents/version.json"
)

_SSL_CTX = ssl._create_unverified_context()


def check(product: str, current_version: str,
          on_update_found=None, timeout: float = 5.0) -> dict:
    """检查更新（后台线程调用）。

    Args:
        product: 产品标识（"delivery_checker" / "batch_renamer"）
        current_version: 当前版本号，如 "2.1.1-dev"
        on_update_found: 回调 (latest_version, download_url, notes)
        timeout: HTTP 超时秒数

    Returns:
        {"update_available": bool, "latest": str, "url": str, "notes": str}
    """
    if not _VERSION_JSON_URL:
        return {"update_available": False, "reason": "未配置更新地址"}

    try:
        req = Request(_VERSION_JSON_URL, method="GET")
        req.add_header("User-Agent", f"DaVinciPlugin/{product}")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read().decode("utf-8")
            resp_data = json.loads(raw)
        # GitHub API 返回 {content: base64, encoding: "base64"}
        if isinstance(resp_data, dict) and resp_data.get("encoding") == "base64":
            import base64
            data = json.loads(base64.b64decode(resp_data["content"]).decode("utf-8"))
        else:
            data = resp_data
    except URLError as e:
        return {"update_available": False, "reason": f"网络不可达: {e}"}
    except json.JSONDecodeError:
        return {"update_available": False, "reason": "版本文件格式错误"}
    except Exception as e:
        return {"update_available": False, "reason": str(e)[:100]}

    # version.json 格式: {"delivery_checker": {"version": "2.2.0", "url": "...", "notes": "..."}, ...}
    latest_info = data.get(product)
    if not latest_info:
        return {"update_available": False, "reason": f"产品 {product} 未找到"}

    latest_version = latest_info.get("version", "")
    if _version_compare(latest_version, current_version) > 0:
        result = {
            "update_available": True,
            "latest": latest_version,
            "url": latest_info.get("url", ""),
            "notes": latest_info.get("notes", ""),
            "force": latest_info.get("force", False),
        }
        if on_update_found:
            try:
                on_update_found(latest_version, latest_info.get("url", ""),
                                latest_info.get("notes", ""))
            except Exception:
                pass
        return result

    return {"update_available": False, "latest": latest_version}


def check_async(product: str, current_version: str, on_update_found=None):
    """后台线程中检查更新，不阻塞启动。"""
    def _run():
        result = check(product, current_version, on_update_found, timeout=5.0)
        if result.get("update_available"):
            import logging
            log = logging.getLogger("WB.updater")
            log.info(f"新版本可用: {result['latest']} → {result.get('url','')}")

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
