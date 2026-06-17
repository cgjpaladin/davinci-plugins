#!/usr/bin/env python3
"""剧本解析器 — 从文档/飞书提取纯文本行，喂给 AI 校对。

用法:
    from script_parser import parse_script

    # 从文件
    parsed = parse_script("/path/to/script.docx")

    # 从飞书文档 token（原生 docx）
    parsed = parse_script("feishu_docx:YoLLdUz01o3vrExQujLcauFJnyb")

    # 从飞书文件 token（上传的 .docx/.doc）
    parsed = parse_script("feishu_file:Eea1b5ml4oTquMx8D1Hc057dn5d")

    # 从飞书文件夹 token
    parsed = parse_script("feishu_folder:ImPbfIKWOlucaod8QJ5c3b73nIb",
                          filename_keyword="怪物妈妈")

    # → {"lines": ["苏冰颜：...", ...]}
"""

import os
import re
import sys
import json
import ssl
import shutil
import hashlib
import zipfile
import tempfile
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import URLError

_SSL_CTX = ssl._create_unverified_context()

if sys.platform == "darwin":
    CACHE_DIR = os.path.expanduser("~/Library/Application Support/交付自检/script_cache")
else:
    CACHE_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "交付自检", "script_cache")
# Feishu API endpoints (tenant token based)
_FEISHU_AUTH = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_FEISHU_FILES = "https://open.feishu.cn/open-apis/drive/v1/files"
_FEISHU_EXPORT = "https://open.feishu.cn/open-apis/drive/v1/export"

# ── 工具 ──

def _file_sha256(path: str) -> str:
    """计算文件 SHA256 前 16 位，用于哈希校验。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]

# ── 日志回调（由调用方如 ui.py 设置）──
_log_callback = None

def set_log_callback(fn):
    """设置外部日志回调，用于飞书下载/PDF 提取等操作记录。"""
    global _log_callback
    _log_callback = fn

def _log(msg: str):
    if _log_callback:
        _log_callback(msg)

def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)

# ── 文档提取 ──

def _extract_text_from_docx(path: str) -> list[str]:
    """从 .docx 提取纯文本行。纯标准库 zipfile + xml.etree，零依赖，跨平台。"""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    lines = []
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    for p in root.iter(f"{{{ns}}}p"):
        text = "".join(t.text or "" for t in p.iter(f"{{{ns}}}t"))
        stripped = text.strip()
        if stripped:
            lines.append(stripped)
    return lines

def _extract_text_from_doc(doc_path: str) -> list[str]:
    """.doc → textutil 直转 .txt（比转 .docx 再提取多保留 172 字符）。macOS 自带。"""
    out = tempfile.mkdtemp()
    try:
        txt_out = os.path.join(out, "converted.txt")
        subprocess.run(
            ["/usr/bin/textutil", "-convert", "txt", "-output", txt_out, doc_path],
            timeout=60, check=True, capture_output=True)
        with open(txt_out, encoding="utf-8", errors="replace") as f:
            text = f.read()
        _log(f"📄 DOC(textutil→txt): {len(text)//1024}KB")
        return [l.strip() for l in text.splitlines() if l.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    finally:
        try:
            for f in os.listdir(out):
                os.remove(os.path.join(out, f))
            os.rmdir(out)
        except OSError:
            pass
    raise RuntimeError(f"无法解析 .doc: {doc_path}，请转为 .docx 后重试")

def _extract_text_from_pdf(path: str) -> list[str]:
    """从 PDF 提取纯文本。优先 pypdf（纯 Python，零安装），其次 pdftotext。"""
    # 方法1: pypdf（纯 Python，所有机器可用）
    try:
        from pypdf import PdfReader
        lines = []
        reader = PdfReader(path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(line)
        if lines:
            _log(f"📄 PDF(pypdf): {len(reader.pages)}页, {len(lines)}行")
            return _clean_pdf_text(lines)
    except Exception:
        pass

    # 方法2: pdftotext（需要 poppler）
    for pdft in ("/opt/homebrew/bin/pdftotext", "/usr/local/bin/pdftotext", "pdftotext"):
        try:
            result = subprocess.run(
                [pdft, "-layout", path, "-"],
                capture_output=True, text=True, encoding="utf-8", timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return _clean_pdf_text(
                    [l.strip() for l in result.stdout.splitlines() if l.strip()])
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # 方法2: macOS AppKit PDFDocument
    try:
        import AppKit
        import Foundation
        pool = Foundation.NSAutoreleasePool.alloc().init()
        ns_pdf = AppKit.PDFDocument.alloc().initWithURL_(
            Foundation.NSURL.fileURLWithPath_(path))
        if ns_pdf:
            full_text = []
            for i in range(ns_pdf.pageCount()):
                page = ns_pdf.pageAtIndex_(i)
                if page and page.string_():
                    full_text.append(page.string_())
            del pool
            combined = "\n".join(full_text)
            return _clean_pdf_text(
                [l.strip() for l in combined.splitlines() if l.strip()])
    except (ImportError, Exception):
        pass

    raise RuntimeError(f"PDF 提取失败: {path}，请安装 poppler (brew install poppler) 或转为 .docx")

def _clean_pdf_text(lines: list[str]) -> list[str]:
    """去除 PDF 审阅标注噪音（Word 修订模式导出）。"""
    cleaned = []
    for line in lines:
        # 包含设置格式/批注的行 → 整行丢弃（纯噪音）
        if re.search(r'设置格式\[|批注\[', line):
            continue
        # 独立的删除行 → 整行丢弃
        if re.match(r'^\s*删除\[[^]]+\]:', line):
            continue
        # 行内删除标记：移除从句及其标记，保留分隔符
        line = re.sub(r'([，。；、！？：]|^)[^，。；、！？：]*?删除\[[^]]+\]:?\s*', r'\1', line)
        # 跳过纯格式指令行
        if re.match(r'^\s*(字体|行距|加粗|字号|颜色)[：:].*$', line):
            continue
        line = line.strip()
        # 清理后只剩单字虚词 → 跳过（删除标记产生的残留）
        if line and len(line) <= 2 and not any('\u4e00' <= c <= '\u9fff' and c not in '的了着过' for c in line):
            continue
        if line:
            cleaned.append(line)
    return cleaned

# ── 飞书集成 ──

def _read_env_key(key: str) -> str:
    """读环境变量 → SMB .env → 本地 .env。"""
    v = os.environ.get(key, "")
    if v:
        return v
    paths = [
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        v = line.split("=", 1)[1].strip().strip('"')
                        if v:
                            return v
        except OSError:
            continue
    return ""

def _get_tenant_token() -> str:
    """获取飞书 tenant_access_token（bot 凭据，无需 lark-cli）。"""
    app_id = _read_env_key("FEISHU_BOT_APP_ID")
    secret = _read_env_key("FEISHU_BOT_APP_SECRET")
    if not app_id or not secret:
        return ""
    body = json.dumps({"app_id": app_id, "app_secret": secret}).encode()
    req = Request(_FEISHU_AUTH, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
        return data.get("tenant_access_token", "")
    except Exception:
        return ""

def _feishu_api(path: str, method: str = "GET", data: bytes | None = None,
                as_user: bool = True) -> bytes | None:
    """调用飞书 API。优先 bot tenant token（免 lark-cli），fallback lark-cli user token。"""
    # 方案1: bot tenant token（所有机器可用）
    token = _get_tenant_token()
    prefix = "tenant"
    # 方案2: lark-cli user token
    if not token:
        config_path = os.path.expanduser("~/.lark-cli/config.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        token = cfg.get("user_access_token", "")
        prefix = "user"
    if not token:
        return None

    url = f"https://open.feishu.cn{path}" if path.startswith("/open-apis") else path
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return resp.read()
    except URLError:
        return None

def _feishu_doc_meta(token: str) -> str | None:
    """获取飞书原生文档的 revision_id（轻量调用，不下载）。
    返回 revision_id，不可访问返回 None。"""
    resp = _feishu_api(f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}")
    if not resp:
        return None
    try:
        data = json.loads(resp)
        if data.get("code") == 0:
            rev = data.get("data", {}).get("document", {}).get("revision_id")
            return str(rev) if rev else None
    except Exception:
        pass
    return None

def _feishu_file_meta(token: str) -> dict | None:
    """获取飞书文件元数据（轻量调用，不下载）。
    返回 {"name": ..., "modified_time": ...}，不可访问返回 None。"""
    resp = _feishu_api(f"{_FEISHU_FILES}/{token}")
    if not resp:
        return None
    try:
        data = json.loads(resp)
        if data.get("code") == 0:
            return data.get("data", {})
    except Exception:
        pass
    return None

def _feishu_display_name(normalized: str) -> str | None:
    """获取飞书链接的显示名称。失败返回 None。"""
    try:
        if normalized.startswith("feishu_file:"):
            token = normalized.split(":", 1)[1]
            # 试用 bot token
            meta = _feishu_file_meta(token)
            if meta and meta.get("name"):
                return meta["name"]
            # 回退 lark-cli user token（bot 可能缺少 drive:metadata scope）
            name = _feishu_file_name_user(token)
            if name:
                return name
        elif normalized.startswith("feishu_docx:"):
            token = normalized.split(":", 1)[1]
            resp = _feishu_api(f"/open-apis/wiki/v2/spaces/get_node?token={token}")
            if resp:
                data = json.loads(resp)
                if data.get("code") == 0:
                    title = data.get("data", {}).get("node", {}).get("title")
                    if title: return title
            resp = _feishu_api(f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}")
            if resp:
                data = json.loads(resp)
                if data.get("code") == 0:
                    return data.get("data", {}).get("document", {}).get("title")
    except Exception:
        pass
    return None

def _feishu_file_name_user(token: str) -> str | None:
    """从下载 API 响应头获取文件名（轻量请求，不读 body）。"""
    from urllib.request import Request
    import re
    try:
        req = Request(f"{_FEISHU_FILES}/{token}/download")
        token_str = _get_tenant_token()
        if not token_str:
            return None
        req.add_header("Authorization", f"Bearer {token_str}")
        with urlopen(req, timeout=5, context=_SSL_CTX) as resp:
            cd = resp.getheader("Content-Disposition", "")
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\s]+)"?', cd)
            if m:
                from urllib.parse import unquote
                return unquote(m.group(1))
    except Exception:
        pass
    return None

def _get_feishu_title(normalized: str) -> str | None:
    """公开接口：获取飞书文档/文件的实际标题。线程安全，3 秒内返回或 None。"""
    import threading
    result = [None]
    def _fetch():
        try:
            result[0] = _feishu_display_name(normalized)
        except Exception:
            pass
    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=3)
    return result[0]

def _download_feishu_file(token: str) -> str:
    """下载飞书文件，返回本地路径。
    缓存复用：查 modified_time，未变则直接返回。"""
    _ensure_cache()
    cache_path = os.path.join(CACHE_DIR, f"file_{{token}}.docx")
    meta_path = cache_path + ".meta"

    if os.path.exists(cache_path):
        meta = _feishu_file_meta(token)
        if meta:
            current_mtime = meta.get("modified_time", "")
            if os.path.exists(meta_path):
                with open(meta_path, encoding="utf-8") as f:
                    if f.read().strip() == current_mtime:
                        _log(f"📋 飞书缓存: {{os.path.basename(cache_path)}}")
                        return cache_path
            if current_mtime:
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(current_mtime)
            if os.path.getsize(cache_path) > 0:
                _log(f"📋 飞书缓存(首次): {{os.path.basename(cache_path)}}")
                return cache_path
        else:
            _log("⚠ 飞书元数据查询失败，使用旧缓存")
            return cache_path

    resp = _feishu_api(f"{_FEISHU_FILES}/{token}/download")
    _ensure_cache()
    cache_path = os.path.join(CACHE_DIR, f"file_{token}.docx")
    if os.path.exists(cache_path):
        return cache_path

    resp = _feishu_api(f"{_FEISHU_FILES}/{token}/download")
    if resp and len(resp) > 100:
        with open(cache_path, "wb") as fh:
            fh.write(resp)
        _log(f"📥 飞书下载: {len(resp)//1024}KB → {os.path.basename(cache_path)}")
        return cache_path

    raise RuntimeError(f"飞书文件下载失败: {token}")
def _export_feishu_docx(token: str) -> str:
    """导出飞书原生文档为 .docx，返回本地路径。
    缓存复用：检查文档 revision_id，未变则直接返回缓存。"""
    _ensure_cache()
    
    # wiki 节点 → 先解析为实际文档 token
    doc_token = token
    doc_title = None
    resp = _feishu_api(f"/open-apis/wiki/v2/spaces/get_node?token={token}")
    if resp:
        try:
            data = json.loads(resp)
            if data.get("code") == 0:
                node = data.get("data", {}).get("node", {})
                if node.get("obj_type") == "docx":
                    doc_token = node.get("obj_token", token)
                    doc_title = node.get("title")
        except Exception:
            pass

    cache_path = os.path.join(CACHE_DIR, f"docx_{doc_token}.docx")
    meta_path = cache_path + ".rev"

    if os.path.exists(cache_path):
        rev = _feishu_doc_meta(doc_token)
        if rev:
            if os.path.exists(meta_path):
                with open(meta_path, encoding="utf-8") as f:
                    if f.read().strip() == rev:
                        _log(f"📋 飞书缓存: {os.path.basename(cache_path)}")
                        return cache_path
                    # revision 变了 → 重新下载
            else:
                # 首次命中 → 写 revision，信任缓存
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(rev)
                _log(f"📋 飞书缓存(首次): {os.path.basename(cache_path)}")
                return cache_path
        else:
            _log("⚠ 飞书文档元数据查询失败，使用旧缓存")
            return cache_path

    resp = _feishu_api(f"{_FEISHU_EXPORT}/{doc_token}?file_extension=docx")
    if not resp:
        # export API 不可用（权限不足或无 drive:export scope）→ 用 raw_content
        raw = _feishu_api(f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/raw_content")
        if not raw:
            raise RuntimeError(f"飞书文档导出失败: {doc_token}")
        try:
            data = json.loads(raw)
            content = data.get("data", {}).get("content", "")
        except json.JSONDecodeError:
            raise RuntimeError(f"飞书 raw_content 响应异常: {raw[:200]}")
        if content:
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="feishu_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            _log(f"📄 飞书 raw_content: {len(content)} 字符")
            return path
        raise RuntimeError(f"飞书文档内容为空: {doc_token}")
    try:
        data = json.loads(resp)
        ticket = data.get("data", {}).get("ticket")
    except json.JSONDecodeError:
        raise RuntimeError(f"飞书导出响应异常: {resp[:200]}")
    if not ticket:
        raise RuntimeError(f"飞书导出无 ticket: {data}")

    return _download_feishu_file(ticket)

def _list_feishu_folder(folder_token: str) -> list[dict]:
    """列出飞书文件夹内容。"""
    resp = _feishu_api(f"{_FEISHU_FILES}?folder_token={folder_token}&page_size=50")
    if not resp:
        return []
    try:
        data = json.loads(resp)
        return data.get("data", {}).get("files", [])
    except json.JSONDecodeError:
        return []

# ── 剧本解析 ──

# ── 飞书链接标准化 ──

def _normalize_feishu_url(source: str) -> str:
    """飞书原始链接 → feishu_docx: / feishu_file: / feishu_folder: 格式。"""
    if not source.startswith(("http://", "https://")):
        return source
    if "feishu.cn" not in source:
        return source

    # 提取 token: /docx/TOKEN, /file/TOKEN, /folder/TOKEN, /docs/TOKEN
    m = re.search(r'feishu\.cn/(docx|file|folder|docs|wiki)/([A-Za-z0-9]+)', source)
    if not m:
        return source

    kind = m.group(1)
    token = m.group(2)

    if kind in ("docx", "docs", "wiki"):
        return f"feishu_docx:{token}"
    elif kind == "file":
        return f"feishu_file:{token}"
    elif kind == "folder":
        return f"feishu_folder:{token}"
    return source

# ── 公开接口 ──

def parse_script(source: str, filename_keyword: str = "") -> dict:
    """解析剧本，返回 {"lines": [...]}。

    Args:
        source: 本地路径 / smb://（自动转） / "feishu_docx:TOKEN" / "feishu_file:TOKEN" / "feishu_folder:TOKEN"
        filename_keyword: 飞书文件夹模式下，按文件名关键词筛选

    Returns:
        {"lines": [...]}
    """
    # smb:// → /Volumes/
    if source.startswith("smb://"):
        source = "/Volumes/" + source.split("smb://", 1)[1].split("/", 1)[1]

    # 飞书原始链接 → 自动识别类型
    source = _normalize_feishu_url(source)

    if source.startswith("feishu_folder:"):
        token = source.split(":", 1)[1]
        files = _list_feishu_folder(token)
        if filename_keyword:
            files = [f for f in files if filename_keyword in f.get("name", "")]
        if not files:
            raise RuntimeError(f"飞书文件夹为空或无匹配: {filename_keyword}")
        # 优先 .docx，其次 .doc/.pdf
        for f in files:
            fn = f.get("name", "")
            if fn.endswith(".docx"):
                return _parse_docx_file(_download_feishu_file(f["token"]))
        for f in files:
            fn = f.get("name", "")
            if fn.endswith((".doc", ".pdf")):
                ext = "pdf" if fn.endswith(".pdf") else "doc"
                path = _download_feishu_file(f["token"])
                if ext == "pdf":
                    os.rename(path, path + ".pdf")
                    path = path + ".pdf"
                return _parse_docx_file_with_fallback(path)
        raise RuntimeError("文件夹中未找到支持的文档格式 (.docx/.doc/.pdf)")
    elif source.startswith("feishu_docx:"):
        token = source.split(":", 1)[1]
        return _parse_docx_file_with_fallback(_export_feishu_docx(token))
    elif source.startswith("feishu_file:"):
        token = source.split(":", 1)[1]
        docx = _download_feishu_file(token)
        return _parse_docx_file_with_fallback(docx)
    else:
        return _parse_docx_file_with_fallback(source)

def _parse_docx_file(path: str) -> dict:
    lines = _extract_text_from_docx(path)
    return {"lines": lines}

def _parse_docx_file_with_fallback(path: str) -> dict:
    """.docx / .doc / .pdf / .txt / .md → parse。本地文件按 path+hash 缓存。"""
    if os.path.isdir(path):
        raise RuntimeError("请选择具体文件，不要选择文件夹")

    _ensure_cache()
    fhash = _file_sha256(path)
    cache_path = os.path.join(CACHE_DIR, f"local_{fhash}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("_cache_path") == path:
                _log(f"📋 本地缓存: {os.path.basename(path)} ({len(cached.get('lines',[]))}行)")
                return cached
        except Exception:
            pass

    lo = path.lower()
    if lo.endswith(".pdf"):
        lines = _extract_text_from_pdf(path)
        result = {"lines": lines}
    elif lo.endswith(".doc"):
        lines = _extract_text_from_doc(path)
        result = {"lines": lines}
    elif lo.endswith((".txt", ".md")):
        with open(path, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        result = {"lines": lines}
    else:
        try:
            result = _parse_docx_file(path)
        except (zipfile.BadZipFile, KeyError):
            try:
                lines = _extract_text_from_pdf(path)
                result = {"lines": lines}
            except Exception:
                lines = _extract_text_from_doc(path)
                result = {"lines": lines}

    result["_cache_path"] = path
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        pass
    return result

