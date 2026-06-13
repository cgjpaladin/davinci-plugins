#!/usr/bin/env python3
"""
url_ssl_test.py — 达芬奇插件 HTTPS 端到端诊断
用法:
  外面: python3 tools/url_ssl_test.py
  达芬奇内: python3 tools/url_ssl_test.py

每项测试：urllib（模拟 DaVinci 沙箱环境） → 失败则 curl fallback
区别 SSL 失败（证书/握手问题）vs HTTP 错误（401/404/502 等业务错误）
"""
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json, os, ssl, subprocess, sys, time

_SSL_CTX = ssl._create_unverified_context()
TIMEOUT = 10

TESTS = [
    # (name, url, method, data, headers, real_endpoint_ref)

    # ① FC 云函数 — 之前 urllib SSL 100% 失败，已迁移 curl
    ("① license.py → FC 云函数",
     None, "POST", {"action": "ping"}, {"Content-Type": "application/json"}),

    # ② DeepSeek API — llm_providers.py 实际调用 /v1/chat/completions
    ("② llm_providers.py → DeepSeek",
     "https://api.deepseek.com/v1/chat/completions",
     "POST", {"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
     {"Content-Type": "application/json", "Authorization": "Bearer sk-this_is_a_fake_key_for_ssl_test"}),

    # ③ jsDelivr CDN — updater.py 版本检查
    ("③ updater.py → jsDelivr CDN",
     "https://cdn.jsdelivr.net/gh/cgjpaladin/davinci-plugins@main/version.json",
     "GET", None,
     {"Accept": "application/json"}),

    # ④ GitHub API — updater.py 发布检查
    ("④ updater.py → GitHub API",
     "https://api.github.com/repos/cgjpaladin/davinci-plugins/releases/latest",
     "GET", None,
     {"Accept": "application/vnd.github+json", "User-Agent": "DaVinciPlugin/updater"}),

    # ⑤ 无痕AI — wuhenai_v2.py BASE_URL = https://api.wuhenai.com/v2
    ("⑤ wuhenai_v2.py → 无痕AI",
     "https://api.wuhenai.com/v2",
     "HEAD", None, {}),

    # ⑥ 鬼手 — ghostcut.py BASE_URL = https://api.zhaoli.com
    ("⑥ ghostcut.py → 鬼手",
     "https://api.zhaoli.com",
     "HEAD", None, {}),

    # ⑦ GitHub Release — _do_update_sync 下载更新包
    ("⑦ _do_update_sync → GitHub Release",
     "https://github.com/cgjpaladin/davinci-plugins/releases/download/v2.5.7/update_latest.zip",
     "HEAD", None, {"User-Agent": "DaVinciPlugin/updater"}),
]


def _get_fc_url():
    for p in [
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
        os.path.join(os.path.dirname(__file__), "..", "shared", ".env"),
        os.path.expanduser("~/.env"),
    ]:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if "WB_LICENSE_URL=" in line:
                        url = line.split("=", 1)[1].strip().strip("\"'")
                        return url + "/ping" if url else None
        except (FileNotFoundError, OSError):
            continue
    return None


def curl_request(method, url, data=None, headers=None):
    cmd = ["curl", "-sS", "--connect-timeout", str(TIMEOUT), "--max-time", str(TIMEOUT + 5)]
    if method == "HEAD":
        cmd.append("-I")
    for k, v in (headers or {}).items():
        cmd.extend(["-H", f"{k}: {v}"])
    if data is not None:
        cmd.extend(["-d", json.dumps(data)])
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 5)
        return {"ok": r.returncode == 0, "code": r.returncode,
                "body": r.stdout[:200], "error": r.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "超时"}
    except FileNotFoundError:
        return {"ok": False, "error": "curl 不可用"}


def classify_error(err_str):
    """区分 SSL 错误 vs HTTP 错误 vs 其它"""
    ssl_markers = ["SSL", "ssl", "certificate", "UNEXPECTED_EOF", "handshake",
                   "WRONG_VERSION_NUMBER", "DH_KEY_TOO_SMALL", "CERTIFICATE_VERIFY"]
    for m in ssl_markers:
        if m in err_str:
            return "SSL"
    if "HTTP Error" in err_str:
        return "HTTP"
    return "OTHER"


def urllib_request(method, url, data=None, headers=None):
    body_bytes = json.dumps(data).encode("utf-8") if data else None
    req = Request(url, data=body_bytes, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
            return {"ok": True, "code": resp.status, "ssl_ok": True,
                    "body": resp.read().decode("utf-8", errors="replace")[:200]}
    except HTTPError as e:
        return {"ok": False, "code": e.code, "ssl_ok": True, "type": "HTTP",
                "error": f"HTTP {e.code}"}
    except (URLError, OSError) as e:
        reason = str(e.reason) if hasattr(e, 'reason') else str(e)
        err_type = classify_error(reason)
        return {"ok": False, "ssl_ok": err_type != "SSL", "type": err_type,
                "error": reason[:200]}
    except ssl.SSLError as e:
        return {"ok": False, "ssl_ok": False, "type": "SSL",
                "error": str(e)[:200]}


def run_test(name, url, method, data, headers):
    if "FC" in name:
        url = _get_fc_url()
        if not url:
            return {"name": name, "url": "(无 FC URL)", "urllib": "skip",
                    "curl": "skip", "verdict": "⚠ 跳过：FC 后端未配置"}

    ur = urllib_request(method, url, data, headers)
    cr = curl_request(method, url, data, headers)

    # 判定逻辑
    if ur["ok"]:
        verdict = "✅ urllib OK — 无 SSL 问题"
    elif ur.get("ssl_ok") is False:
        # SSL 握手失败 — 核心问题
        if cr["ok"]:
            verdict = "⚠ SSL失败 curl成功 — 需要加fallback"
        else:
            verdict = "❌ SSL双失败 — 端点本身不通"
    else:
        # 非 SSL 失败（HTTP 401/404 等）
        if cr["ok"]:
            verdict = "✅ SSL握手成功 — HTTP错误是正常的"
        else:
            verdict = "⚠ 双失败（非SSL）"

    return {
        "name": name, "url": url[:80] + ("..." if len(url) > 80 else ""),
        "urllib_ssl": "✅" if ur.get("ssl_ok", False) else "❌",
        "curl": "✅" if cr["ok"] else "❌",
        "verdict": verdict,
        "urllib_detail": ur.get("error", ur.get("body", ""))[:100],
    }


def main():
    print("═" * 60)
    print("  达芬奇插件 HTTPS SSL 诊断")
    print(f"  环境: {'DaVinci 子进程' if 'DaVinci' in sys.executable else '外部 Python'}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  测试方法: urllib({'_create_unverified_context'}) vs curl")
    print("═" * 60)
    print()

    results = []
    for name, url, method, data, headers in TESTS:
        print(f"  {name}…", end=" ", flush=True)
        r = run_test(name, url, method, data, headers)
        icon = r["verdict"][0]
        print(icon, r["urllib_detail"][:60] if r["urllib_detail"] else "")
        results.append(r)

    print()
    print("═" * 60)
    print("  诊断结论")
    print("═" * 60)

    need_fallback = []
    for r in results:
        v = r["verdict"]
        print(f"  {v}")
        if "需要加fallback" in v:
            need_fallback.append(r["name"])
        print(f"     urllib SSL={r['urllib_ssl']}  curl={r['curl']}")
        print()

    if need_fallback:
        print(f"  🔴 {len(need_fallback)} 个需要加 curl fallback: {'  '.join(need_fallback)}")
    else:
        print("  🟢 所有端点 SSL 握手正常！无需改动。")

    # JSON 输出
    print()
    print("═" * 60)
    print(json.dumps([{"name": r["name"], "verdict": r["verdict"],
                       "urllib_ssl": r["urllib_ssl"], "curl": r["curl"]}
                      for r in results], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
