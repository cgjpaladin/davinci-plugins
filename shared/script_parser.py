#!/usr/bin/env python3
"""剧本解析器 — 从 .docx / .doc / 飞书文档提取人物 + 分集台词。

用法:
    from script_parser import parse_script, match_timeline

    # 从文件
    parsed = parse_script("/path/to/script.docx")

    # 从飞书文档 token（原生 docx）
    parsed = parse_script("feishu_docx:YoLLdUz01o3vrExQujLcauFJnyb")

    # 从飞书文件 token（上传的 .docx/.doc）
    parsed = parse_script("feishu_file:Eea1b5ml4oTquMx8D1Hc057dn5d")

    # 从飞书文件夹 token
    parsed = parse_script("feishu_folder:ImPbfIKWOlucaod8QJ5c3b73nIb",
                          filename_keyword="怪物妈妈")

    # 匹配时间线
    ctx = match_timeline(parsed, "EP04_剪辑_v03")
    # → {"characters": ["林野", ...], "lines": ["苏冰颜：...", ...]}
"""

import os
import re
import json
import shutil
import zipfile
import hashlib
import tempfile
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import URLError

CACHE_DIR = os.path.expanduser("~/Library/Application Support/交付自检/script_cache")
# Feishu API endpoints (tenant token based)
_FEISHU_AUTH = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_FEISHU_FILES = "https://open.feishu.cn/open-apis/drive/v1/files"
_FEISHU_EXPORT = "https://open.feishu.cn/open-apis/drive/v1/export"


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


# ── 文档提取 ──

def _extract_text_from_docx(path: str) -> list[str]:
    """从 .docx 提取纯文本行。"""
    lines = []
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        line = "".join(t.text or "" for t in p.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return lines


def _extract_text_from_doc(doc_path: str) -> list[str]:
    """.doc → LibreOffice 转换 → 提取文本。"""
    out = tempfile.mkdtemp()
    try:
        for soffice in ("/opt/homebrew/bin/soffice",
                        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                        "soffice"):
            try:
                subprocess.run([
                    soffice, "--headless", "--convert-to", "docx",
                    "--outdir", out, doc_path
                ], timeout=60, check=True, capture_output=True)
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        else:
            raise FileNotFoundError
        for f in os.listdir(out):
            if f.endswith(".docx"):
                return _extract_text_from_docx(os.path.join(out, f))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    finally:
        for f in os.listdir(out):
            os.remove(os.path.join(out))
        os.rmdir(out)
    # fallback: try python-docx or antiword
    raise RuntimeError(f"无法解析 .doc: {doc_path}，请安装 LibreOffice 或转为 .docx")


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
            return _clean_pdf_text(lines)
    except Exception:
        pass

    # 方法2: pdftotext（需要 poppler）
    for pdft in ("/opt/homebrew/bin/pdftotext", "/usr/local/bin/pdftotext", "pdftotext"):
        try:
            result = subprocess.run(
                [pdft, "-layout", path, "-"],
                capture_output=True, text=True, timeout=30)
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
    """去除 PDF 审阅标注噪音。"""
    cleaned = []
    for line in lines:
        # 跳过纯标注行
        if re.match(r'^(设置格式|删除|加粗|批注)\[', line):
            continue
        # 去除行内标注标记
        line = re.sub(r'(设置格式|删除|批注)\[[^]]+\][：:]?\s*', '', line)
        line = line.strip()
        if line:
            cleaned.append(line)
    return cleaned


# ── 飞书集成 ──

def _read_env_key(key: str) -> str:
    """读 SMB .env → 本地 .env（与 llm_providers 相同）。"""
    paths = [
        "/Volumes/MYJC/06_Software/达芬奇脚本/shared/.env",
        os.path.expanduser("~/.workbuddy/.env"),
    ]
    for p in paths:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip('"')
        except FileNotFoundError:
            continue
    return os.environ.get(key, "")


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
        with urlopen(req, timeout=10) as resp:
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
            with open(config_path) as f:
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
        with urlopen(req, timeout=30) as resp:
            return resp.read()
    except URLError:
        return None


def _download_feishu_file(token: str) -> str:
    """下载飞书文件，直调 API（bot token，无需 lark-cli）。"""
    _ensure_cache()
    cache_path = os.path.join(CACHE_DIR, f"file_{token}.docx")
    if os.path.exists(cache_path):
        return cache_path

    resp = _feishu_api(f"{_FEISHU_FILES}/{token}/download")
    if resp and len(resp) > 100:
        with open(cache_path, "wb") as fh:
            fh.write(resp)
        return cache_path

    raise RuntimeError(f"飞书文件下载失败: {token}")
def _export_feishu_docx(token: str) -> str:
    """导出飞书原生文档为 .docx，返回本地路径。直调 API，无需 lark-cli。"""
    _ensure_cache()
    cache_path = os.path.join(CACHE_DIR, f"docx_{token}.docx")
    if os.path.exists(cache_path):
        return cache_path

    resp = _feishu_api(f"{_FEISHU_EXPORT}/{token}?file_extension=docx")
    if not resp:
        raise RuntimeError(f"飞书文档导出失败: {token}")
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

_CHINESE_NUM = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
                7: "七", 8: "八", 9: "九", 10: "十",
                11: "十一", 12: "十二", 13: "十三", 14: "十四", 15: "十五",
                16: "十六", 17: "十七", 18: "十八", 19: "十九", 20: "二十",
                30: "三十", 40: "四十", 50: "五十"}
_CN_EP_RE = re.compile(r"^第([一二三四五六七八九十百千\d]+)集")
_ARABIC_EP_RE = re.compile(r"^第(\d+)集")


def _cn_to_int(s: str) -> int | None:
    """中文数字 → int。支持「一」到「九十九」「一百」等。"""
    try:
        return int(s)
    except ValueError:
        pass

    # 直接查表（常见组合）
    direct = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19,
        "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25, "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29,
        "三十": 30, "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35, "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39,
        "四十": 40, "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45, "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49,
        "五十": 50, "五十一": 51, "五十二": 52, "五十三": 53, "五十四": 54, "五十五": 55, "五十六": 56, "五十七": 57, "五十八": 58, "五十九": 59,
        "六十": 60, "六十一": 61, "六十二": 62, "六十三": 63, "六十四": 64, "六十五": 65, "六十六": 66, "六十七": 67, "六十八": 68, "六十九": 69,
        "七十": 70, "七十一": 71, "七十二": 72, "七十三": 73, "七十四": 74, "七十五": 75, "七十六": 76, "七十七": 77, "七十八": 78, "七十九": 79,
        "八十": 80, "八十一": 81, "八十二": 82, "八十三": 83, "八十四": 84, "八十五": 85, "八十六": 86, "八十七": 87, "八十八": 88, "八十九": 89,
        "九十": 90, "九十一": 91, "九十二": 92, "九十三": 93, "九十四": 94, "九十五": 95, "九十六": 96, "九十七": 97, "九十八": 98, "九十九": 99,
        "一百": 100, "百": 100,
    }
    if s in direct:
        return direct[s]
    return None


def _parse_episode_number(title: str) -> int | None:
    """从行文本提取集号。"""
    title = title.strip()
    m = _CN_EP_RE.match(title) or _ARABIC_EP_RE.match(title)
    if m:
        return _cn_to_int(m.group(1))
    return None


def _extract_characters(lines: list[str]) -> list[str]:
    """从「人物」段提取角色名列表。兼容多格式：
      - 林野（24岁）：修罗一脉...
      - 周子睿（子睿）：12岁，男主...
      - 怪物"元歌"：在古代...
    """
    in_bio = False
    chars = set()
    name_re = re.compile(
        r'^'
        r'(?:[\u4e00-\u9fff]+[\u201c\u300c])?'   # 可选前置描述"怪物""
        r'([\u4e00-\u9fff\u3007]{2,6})'           # 名字 2-6 中文字
        r'[\u201d\u300d]?'                         # 可选后引号
        r'(?:（[^）]{1,12}）)?'                    # 可选昵称/年龄
        r'(?:\d+岁)?'                              # 可选年龄
        r'\s*[：:]\s*'                              # 冒号
    )
    skip_starts = {"对标", "简介", "人物", "外", "出", "第", "剧", "姓", "年"}

    for line in lines:
        stripped = line.strip()
        # 人物段开始标记
        if stripped in ("人物简介", "人物介绍", "人物") or stripped.startswith("人物简介") or stripped.startswith("人物介绍"):
            in_bio = True
            continue
        # 紧凑格式「人物：A B C」（PDF 场景级角色列表）
        if "人物" in stripped and re.match(r'人物[：:]', stripped):
            in_bio = True
            m = re.match(r'人物[：:]\s*(.+)', stripped)
            if m:
                rest = m.group(1)
                # 去掉 PDF 格式残渣
                rest = re.sub(r'字体[：:].*', '', rest)
                rest = re.sub(r'(加粗|非突出|删除|批注).*', '', rest)
                rest = re.sub(r'（[^）]*）', '', rest)
                parts = re.split(r'[\s，,、]+', rest)
                noise = {"编号", "字体", "加粗", "四号", "宋体", "小四", "军人",
                         "人类", "仿生", "丧尸", "若干", "男女", "各自", "一半",
                         "两名", "三名", "名", "个", "左右", "背影", "指挥", "警卫",
                         "场景", "日内", "日外", "夜内", "夜外", "内", "全息"}
                for part in parts:
                    part = re.sub(r'\d+', '', part).strip()
                    if part in noise or len(part) < 2:
                        continue
                    if re.fullmatch(r'[\u4e00-\u9fff\u3007]+', part) and len(part) <= 6:
                        chars.add(part)
            continue
        if in_bio:
            ep = _parse_episode_number(stripped)
            if ep is not None:
                break
            if any(stripped.startswith(w) for w in skip_starts):
                continue
            m = name_re.match(stripped)
            if m:
                chars.add(m.group(1))
    return sorted(chars, key=lambda x: len(x), reverse=True)


def _split_episodes(lines: list[str]) -> dict[int, list[str]]:
    """按「第N集」分割，返回 {集号: [台词行]}。"""
    episodes: dict[int, list[str]] = {}
    current_ep = 0
    for line in lines:
        ep = _parse_episode_number(line)
        if ep is not None:
            current_ep = ep
            episodes.setdefault(current_ep, [])
            continue
        if current_ep > 0:
            if "：" in line or ":" in line:
                episodes[current_ep].append(line)
    return episodes


# ── 飞书链接标准化 ──

def _normalize_feishu_url(source: str) -> str:
    """飞书原始链接 → feishu_docx: / feishu_file: / feishu_folder: 格式。"""
    if not source.startswith(("http://", "https://")):
        return source
    if "feishu.cn" not in source:
        return source

    # 提取 token: /docx/TOKEN, /file/TOKEN, /folder/TOKEN, /docs/TOKEN
    m = re.search(r'feishu\.cn/(docx|file|folder|docs)/([A-Za-z0-9]+)', source)
    if not m:
        return source

    kind = m.group(1)
    token = m.group(2)

    if kind in ("docx", "docs"):
        return f"feishu_docx:{token}"
    elif kind == "file":
        return f"feishu_file:{token}"
    elif kind == "folder":
        return f"feishu_folder:{token}"
    return source


# ── 公开接口 ──

def parse_script(source: str, filename_keyword: str = "") -> dict:
    """解析剧本，返回 {characters, episodes}。

    Args:
        source: 本地路径 / smb://（自动转） / "feishu_docx:TOKEN" / "feishu_file:TOKEN" / "feishu_folder:TOKEN"
        filename_keyword: 飞书文件夹模式下，按文件名关键词筛选

    Returns:
        {"characters": ["林野", ...], "episodes": {1: [...], 2: [...]}}
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
        return _parse_docx_file(_export_feishu_docx(token))
    elif source.startswith("feishu_file:"):
        token = source.split(":", 1)[1]
        docx = _download_feishu_file(token)
        return _parse_docx_file_with_fallback(docx)
    else:
        return _parse_docx_file_with_fallback(source)


def _parse_docx_file(path: str) -> dict:
    lines = _extract_text_from_docx(path)
    return {
        "characters": _extract_characters(lines),
        "episodes": _split_episodes(lines),
    }


def _parse_docx_file_with_fallback(path: str) -> dict:
    """.docx / .doc / .pdf → parse。根据扩展名分派。"""
    lo = path.lower()
    if lo.endswith(".pdf"):
        lines = _extract_text_from_pdf(path)
        return {"characters": _extract_characters(lines),
                "episodes": _split_episodes(lines)}
    if lo.endswith(".doc"):
        lines = _extract_text_from_doc(path)
        return {"characters": _extract_characters(lines),
                "episodes": _split_episodes(lines)}
    try:
        return _parse_docx_file(path)
    except (zipfile.BadZipFile, KeyError):
        # 无扩展名或损坏 → 试 PDF
        try:
            lines = _extract_text_from_pdf(path)
            return {"characters": _extract_characters(lines),
                    "episodes": _split_episodes(lines)}
        except Exception:
            lines = _extract_text_from_doc(path)
        return {"characters": _extract_characters(lines),
                "episodes": _split_episodes(lines)}


def match_timeline(parsed: dict, tl_name: str, ep_override: str | None = None) -> dict:
    """从解析结果中匹配当前时间线对应的集。

    Args:
        parsed: parse_script() 返回值
        tl_name: 时间线名称，如 "EP04_剪辑_v03"
        ep_override: 手动指定集号 "7" 或范围 "7-9"，留空自动检测

    Returns:
        {"characters": [...], "lines": [...], "episode": int}
    """
    episodes = parsed.get("episodes", {})

    # 手动指定优先
    if ep_override:
        # 范围 "7-9"
        if "-" in ep_override:
            parts = ep_override.split("-")
            try:
                lo, hi = int(parts[0]), int(parts[1])
            except ValueError:
                raise RuntimeError(f"集号格式错误: {ep_override}")
            merged = []
            for ep in range(lo, hi + 1):
                merged.extend(episodes.get(ep, []))
            return {"characters": parsed["characters"],
                    "lines": merged, "episode": lo}
        # 单个数字 "7"
        try:
            ep = int(ep_override)
        except ValueError:
            raise RuntimeError(f"集号格式错误: {ep_override}")
        if ep not in episodes:
            avail = sorted(episodes.keys())
            raise RuntimeError(f"剧本无第 {ep} 集（可用: {avail[:5]}...）")
        return {"characters": parsed["characters"],
                "lines": episodes[ep], "episode": ep}

    # 策略1: EP04 → 4
    m = re.search(r"[Ee][Pp](\d+)", tl_name)
    if m:
        ep = int(m.group(1))
        if ep in episodes:
            return {"characters": parsed["characters"],
                    "lines": episodes[ep], "episode": ep}

    # 策略2: 第四集 → 4
    for num, lines in episodes.items():
        cn = _CHINESE_NUM.get(num, "")
        if cn and f"第{cn}集" in tl_name:
            return {"characters": parsed["characters"],
                    "lines": lines, "episode": num}

    # 策略3: 模糊匹配 "04" 或 "4"
    m_num = re.search(r"(\d+)", tl_name)
    if m_num:
        num = int(m_num.group(1))
        if num in episodes:
            return {"characters": parsed["characters"],
                    "lines": episodes[num], "episode": num}

    # 策略4: 取第一集
    if episodes:
        first = min(episodes)
        return {"characters": parsed["characters"],
                "lines": episodes[first], "episode": first}

    raise RuntimeError("匹配不到，请手动输入集号")
