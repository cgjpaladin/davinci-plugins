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

try:
    from update_config import (
        VERSION_CHECK_URLS, TIMEOUT_VERSION_CHECK,
    )
except ImportError:
    from shared.update_config import (
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
    """依次尝试各 URL，返回版本号最高的 JSON dict（防止 CDN 过期）"""
    best = None
    best_version = ""
    for url in urls:
        try:
            raw = _fetch_text(url, timeout=timeout)
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("encoding") == "base64":
                data = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
            # 提取版本号比较，取最高的
            for k, v in data.items():
                if isinstance(v, dict) and "version" in v:
                    ver = v["version"]
                    if _ver_cmp(ver, best_version) > 0:
                        best = data
                        best_version = ver
        except Exception:
            continue
    if best is None:
        raise RuntimeError("所有更新链路均不可达")
    return best


def _ver_cmp(a, b):
    """比较 semver 字符串，a > b 返回 1"""
    try:
        aa = [int(x) for x in a.split('.')]
        bb = [int(x) for x in b.split('.')]
        for va, vb in zip(aa, bb):
            if va > vb: return 1
            if va < vb: return -1
        return len(aa) - len(bb)
    except Exception:
        return 0


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
    try:
        from update_config import VERSION_CHECK_URLS, TIMEOUT_VERSION_CHECK, DOWNLOAD_URLS
    except ImportError:
        from shared.update_config import VERSION_CHECK_URLS, TIMEOUT_VERSION_CHECK, DOWNLOAD_URLS
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
        import re
        tag = data["tag_name"]
        # 从 tag 提取版本号: "batch_renamer-v3.7.1" → "3.7.1", "v2.5.14" → "2.5.14"
        vm = re.search(r'(\d+\.\d+\.\d+)', tag)
        version = vm.group(1) if vm else tag.lstrip("v")
        notes = data.get("body", "")
        # 从 assets 找匹配产品的下载链接
        dl_urls = []
        # 尝试匹配 asset 名字中的产品标识
        for a in data.get("assets", []):
            name = a.get("name", "")
            url = a.get("browser_download_url", "")
            if not url: continue
            # 过滤：只取与当前 product 相关的 asset
            if product in name or product.replace('_win','').replace('_mac','') in name:
                dl_urls.append("https://ghproxy.net/" + url)
                dl_urls.append(url)  # 直连兜底
        if not dl_urls:
            # fallback: 全取
            for a in data.get("assets", []):
                url = a.get("browser_download_url", "")
                if not url: continue
                if "github.com" in url:
                    dl_urls.append("https://ghproxy.net/" + url)
                dl_urls.append(url)
        if not dl_urls:
            dl_urls = DOWNLOAD_URLS
        sha256 = None
        for a in data.get("assets", []):
            if a.get("name", "").endswith(".sha256"):
                pass
        data = {
            product: {
                "version": version,
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
    """比较两个 semver 版本号。a > b → 1, a == b → 0, a < b → -1。
    -dev/-alpha/-beta 后缀视为低于同版本号正式版。"""
    def _parse(v):
        v = v.strip().lstrip("v")
        parts = v.replace("-", ".").split(".")
        nums = []
        has_suffix = False
        for p in parts:
            try:
                nums.append(int(p))
            except ValueError:
                has_suffix = True
                break               # 后缀之后的非数字部分忽略
        nums.append(-1 if has_suffix else float("inf"))
        return nums

    try:
        return (_parse(a) > _parse(b)) - (_parse(a) < _parse(b))
    except Exception:
        return 0


def download_update(product: str, save_path: str,
                    progress_callback=None, timeout: float = 60.0) -> tuple:
    """下载更新包到本地。

    Args:
        product: 产品标识（"batch_renamer_mac" / "delivery_checker" 等）
        save_path: 保存路径（完整文件名）
        progress_callback: 回调 (downloaded_bytes, total_bytes)
        timeout: 每条链路超时秒数

    Returns:
        (success: bool, error_message: str)
    """
    try:
        from update_config import DOWNLOAD_URLS, MIN_DOWNLOAD_SIZE, TIMEOUT_DOWNLOAD_SINGLE
    except ImportError:
        from shared.update_config import DOWNLOAD_URLS, MIN_DOWNLOAD_SIZE, TIMEOUT_DOWNLOAD_SINGLE
    import hashlib

    # 获取 download URLs（复用 check 里的 version.json 解析逻辑）
    try:
        data = _fetch_json_across_links(VERSION_CHECK_URLS, timeout=10.0)
    except Exception as e:
        return False, f"无法获取版本信息: {e}"

    urls = None
    expected_sha256 = None

    # 从 version.json 提取 urls
    if isinstance(data, dict) and product in data:
        pinfo = data[product]
        raw = pinfo.get("urls") or pinfo.get("url", "")
        urls = raw if isinstance(raw, list) else ([raw] if raw else [])
        expected_sha256 = pinfo.get("sha256")

    if not urls:
        urls = DOWNLOAD_URLS

    timeout = timeout or TIMEOUT_DOWNLOAD_SINGLE
    errors = []

    for idx, dl_url in enumerate(urls):
        try:
            # 处理 URL 中的中文路径
            from urllib.parse import quote, urlparse, urlunparse
            p = urlparse(dl_url)
            safe = urlunparse(p._replace(path=quote(p.path, safe='/')))
            req = Request(safe, method="GET")
            req.add_header("User-Agent", f"DaVinciPlugin/{product}")
            with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                total = int(resp.getheader("Content-Length", 0))
                downloaded = 0
                chunks = []
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    chunks.append(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
                data_bytes = b"".join(chunks)
                if len(data_bytes) < MIN_DOWNLOAD_SIZE:
                    errors.append(f"{dl_url[:60]}: 文件过小({len(data_bytes)}B)")
                    continue

                # SHA256 校验
                if expected_sha256:
                    actual = hashlib.sha256(data_bytes).hexdigest()
                    if actual != expected_sha256:
                        errors.append(f"{dl_url[:60]}: SHA256 不匹配")
                        continue

                with open(save_path, "wb") as f:
                    f.write(data_bytes)
                return True, ""
        except Exception as e:
            errors.append(f"{dl_url[:60]}: {e}")
            continue

    return False, " · ".join(errors[-3:]) if errors else "所有链路均不可达"


def download_delta(save_path: str, progress_callback=None, timeout: float = 300.0) -> tuple:
    """下载差分更新包 update_latest.zip（<3MB）。
    走 CDN 多链路，失败自动切换。"""
    try:
        from update_config import DOWNLOAD_URLS, MIN_DOWNLOAD_SIZE
    except ImportError:
        from shared.update_config import DOWNLOAD_URLS, MIN_DOWNLOAD_SIZE

    import hashlib
    errors = []
    dl_urls = DOWNLOAD_URLS

    for idx, dl_url in enumerate(dl_urls):
        try:
            from urllib.parse import quote, urlparse, urlunparse
            p = urlparse(dl_url)
            safe = urlunparse(p._replace(path=quote(p.path, safe='/')))
            req = Request(safe, method="GET")
            req.add_header("User-Agent", f"DaVinciPlugin/delta")
            with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                total = int(resp.getheader("Content-Length", 0))
                downloaded = 0
                chunks = []
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    chunks.append(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
                data = b"".join(chunks)
                if len(data) < MIN_DOWNLOAD_SIZE:
                    errors.append(f"{dl_url[:60]}: 文件过小 ({len(data)}B)")
                    continue
                with open(save_path, "wb") as f:
                    f.write(data)
                return True, ""
        except Exception as e:
            errors.append(f"{dl_url[:60]}: {e}")
            continue

    return False, " · ".join(errors[-3:]) if errors else "所有链路均不可达"
