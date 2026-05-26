"""
shared/naming_createone.py — 创壹特供版命名规则
命名格式: EP{ep}_SC{sc}_SH{shot}[/{shot2}/...]_TK{tk}_{desc}_{type}_{author}_V{ver}_{status}.{ext}
"""
import os, re, unicodedata

# ============================================================
# 字段配置
# ============================================================
FIELD_CONFIG = [
    {"key":"ep",     "name":"EP",  "label":"集数",    "def":"",   "regex":r"^\d{2,3}$",           "hint":"01"},
    {"key":"sc",     "name":"SC",  "label":"场次",    "def":"",   "regex":r"^\d{2}$",             "hint":"01"},
    {"key":"shot",   "name":"SH",  "label":"镜号",    "def":"",   "regex":r"^\d{2}(/\d{2})*$",    "hint":"01"},
    {"key":"tk",     "name":"TK",  "label":"次数",    "def":"",   "regex":r"^\d{2}$",   "inc":True,"hint":"01"},
    {"key":"desc",   "name":"",    "label":"镜头描述", "def":"",   "desc_only":True,               "hint":"仅图片"},
    {"key":"type",   "name":"",    "label":"类型",    "def":"",   "auto":True},
    {"key":"author", "name":"",    "label":"制作者",  "def":"",                                    "hint":"请输入姓名"},
    {"key":"ver",    "name":"V",   "label":"版本号",  "def":"01", "regex":r"^\d{2}$",             "hint":"01"},
    {"key":"status", "name":"",    "label":"状态",    "def":"",   "dv":["请选择","OK","KP","NG"],  "required":True},
]

DISPLAY_FIELDS = [fd for fd in FIELD_CONFIG if fd["key"] != "tk"]

# 扩展名分类 — 用于 type 自动判定
VIDEO_EXT = {".mp4",".mxf",".mov",".avi",".r3d",".braw",
             ".mts",".m2t",".mpg",".mpeg",".m4v",".mkv",
             ".wmv",".flv",".webm",".ts",".3gp",".ari"}

IMAGE_EXT = {".png",".jpg",".jpeg",".tiff",".tif",".bmp",
             ".dpx",".exr",".psd",".tga",".targa"}

MEDIA_EXT = VIDEO_EXT | IMAGE_EXT

def ext_to_type(ext: str) -> str:
    """根据扩展名返回 AIPIC 或 AIVID"""
    e = ext.lower()
    if e in IMAGE_EXT: return "AIPIC"
    if e in VIDEO_EXT: return "AIVID"
    return ""


# ============================================================
# 描述清洗 — 只保留中英文数字
# ============================================================
_DESC_KEEP_RE = re.compile(r'[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]')

def sanitize_desc(text: str) -> str:
    """只保留中文、英文、数字，其余字符删除"""
    return _DESC_KEEP_RE.sub('', text)


# ============================================================
# 输入清洗 (同 naming.py，从井水计划继承)
# ============================================================
_FS_UNSAFE_REPLACE = str.maketrans({
    ':': '\uff1a', '?': '\uff1f', '*': '\u2731', '"': "'",
    '<': '\u300a', '>': '\u300b', '|': '\uff5c', '/': '&', '\\': '&',
})

_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060\uFEFF]')

_WIN_RESERVED = {n.upper() for n in [
    "CON","PRN","AUX","NUL","CLOCK$",
    *("COM%d"%i for i in range(1,10)),
    *("LPT%d"%i for i in range(1,10)),
    *(f"{n}{s}" for n in ("COM","LPT") for s in ("¹","²","³")),
]}

_MAX_FILENAME_BYTES = 250

def _truncate_bytes(s: str, max_bytes: int) -> str:
    b = s.encode('utf-8')
    if len(b) <= max_bytes:
        return s
    truncated = b[:max_bytes]
    while True:
        try:
            return truncated.decode('utf-8')
        except UnicodeDecodeError:
            truncated = truncated[:-1]

def sanitize_text(text: str, for_filename: bool = False) -> tuple:
    warnings = []
    if not text.strip():
        return "", ["不能为空"]
    cleaned = _CONTROL_RE.sub('', text)
    if cleaned != text:
        warnings.append("已移除控制字符")
    cleaned = unicodedata.normalize('NFC', cleaned)
    before = cleaned
    cleaned = cleaned.translate(_FS_UNSAFE_REPLACE)
    if cleaned != before:
        warnings.append("已替换文件系统禁字")
    before = cleaned
    cleaned = _truncate_bytes(cleaned, _MAX_FILENAME_BYTES)
    if cleaned != before:
        warnings.append("已截断过长文件名")
    cleaned = cleaned.strip(' .')
    if for_filename:
        if cleaned.upper() in _WIN_RESERVED:
            warnings.append("使用了 Windows 保留名")
            cleaned = "_" + cleaned
    return cleaned, warnings


# ============================================================
# 文件名构建
# ============================================================

def build_filename(fields):
    """从字段字典构建文件名 (不含扩展名)
    格式: EP{ep}_SC{sc}_SH{shot}_TK{tk}_{desc}_{type}_{author}_V{ver}_{status}
    """
    parts = []
    for fd in FIELD_CONFIG:
        v = fields.get(fd["key"], fd["def"])
        nm = fd["name"]; k = fd["key"]
        if nm == "EP":   parts.append(f"EP{v}")
        elif nm == "SC": parts.append(f"SC{v}")
        elif nm == "SH": parts.append(f"SH{v}")
        elif nm == "TK": parts.append(f"TK{v}")
        elif nm == "V":  parts.append(f"V{v}")
        elif k == "status": parts.append(v)
        else:            parts.append(v.replace("/","_").replace(" ",""))
    return "_".join(parts) if parts else "unnamed"


# ============================================================
# 文件名解析正则 (从 FIELD_CONFIG 自动生成)
# ============================================================

def _build_filename_re():
    segments = []
    desc_seen = False
    desc_trail = 0
    for fd in FIELD_CONFIG:
        if not desc_seen and fd["key"] == "desc":
            desc_seen = True; continue
        if desc_seen and fd["name"] == "V":
            break
        if desc_seen:
            desc_trail += 1

    for fd in FIELD_CONFIG:
        nm = fd["name"]; k = fd["key"]
        if nm == "EP":
            segments.append(f"EP(?P<{k}>\\d{{2,3}})")
        elif nm == "SC":
            segments.append(f"SC(?P<{k}>\\d{{2}})")
        elif nm == "SH":
            segments.append(f"SH(?P<{k}>\\d{{2}}(?:/\\d{{2}})*)")
        elif nm == "TK":
            segments.append(f"TK(?P<{k}>\\d{{2}})")
        elif nm == "V":
            segments.append(f"V(?P<{k}>\\d{{2}})")
        elif k == "status":
            segments.append(f"(?P<{k}>\\w*)")
        elif k == "desc":
            trailing = "_".join(["[^_]*"] * desc_trail) if desc_trail else ""
            lookahead = f"(?=_{trailing}_V\\d)" if trailing else "(?=_V\\d)"
            segments.append(f"(?P<{k}>.*?){lookahead}")
        else:
            segments.append(f"(?P<{k}>[^_]*)")
    return re.compile(r"^" + "_".join(segments) + r"(?P<ext>\.[^.]+)$")

FILENAME_RE = _build_filename_re()

# Fallback: 只认 EP/SC/SH/TK 前缀 + V/status 后缀
FALLBACK_RE = re.compile(
    r"^EP(?P<ep>\d{2,3})_SC(?P<sc>\d{2})_SH(?P<shot>\d{2}(?:/\d{2})*)_TK(?P<tk>\d{2})_"
    r".*"
    r"_V(?P<ver>\d{2})_(?P<status>\w+)(?P<ext>\.[^.]+)$")


def parse_filename(path):
    """解析已命名文件 → {field_key: value}，失败返回 None"""
    name = os.path.basename(path)
    m = FILENAME_RE.match(name) or FALLBACK_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    result = {}
    for fd in FIELD_CONFIG:
        k = fd["key"]
        if k in d:
            result[k] = d[k]
    # type 从文件名读取
    if result.get("type"):
        result["type"] = result["type"]
    return result
