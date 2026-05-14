"""
shared/naming.py — 命名规则单一事实来源
renamer_v3 和 checker 共用一个 FIELD_CONFIG，改一处全局生效
"""
import os, re

# ============================================================
# 字段配置
# ============================================================
FIELD_CONFIG = [
    {"key":"ep",     "name":"Ep",  "label":"Ep 集数",   "def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"sc",     "name":"Sc",  "label":"Sc 场次",   "def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"gr",     "name":"Gr",  "label":"Gr 小场次", "def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"tk",     "name":"Tk",  "label":"Tk 次数",   "def":"01","regex":r"^\d{2,3}$","inc":True,"hint":"01"},
    {"key":"desc",   "name":"",    "label":"镜头描述",   "def":"","hint":"由制作方式决定"},
    {"key":"author", "name":"",    "label":"制作者",     "def":"","hint":"张谭/温欣然"},
    {"key":"method", "name":"",    "label":"制作方式",   "def":"","dv":["请选择","智能分镜版","双轨版","角色专属版"]},
    {"key":"ver",    "name":"v",   "label":"v 版本号",   "def":"01","regex":r"^\d{2,3}(\.\d+)?$","hint":"01"},
    {"key":"status", "name":"",    "label":"通过情况",   "def":"","dv":["请选择","OK","KP","NG"]},
]

METHOD_DESC_MAP = {
    "智能分镜版": {"mode":"locked", "value":"全能分镜"},
    "双轨版":     {"mode":"dropdown","values":["请选择","幽灵角色","空镜","手动输入…"]},
    "角色专属版": {"mode":"text","hint":"温时雨过肩中景"},
}

DESC_TO_METHOD = {"全能分镜":"智能分镜版","幽灵角色":"双轨版","空镜":"双轨版"}

FIELD_RULES = [
    {"trigger":"method","targets":["desc"],"map":{
        "智能分镜版": {"desc":{"locked":"全能分镜"}},
        "双轨版":     {"desc":{"dropdown":["请选择","幽灵角色","空镜","手动输入…"]}},
        "角色专属版": {"desc":{"text_hint":"温时雨过肩中景"}},
    }},
]

DISPLAY_FIELDS = [fd for fd in FIELD_CONFIG if fd["key"] != "tk"]

# 媒体文件扩展名
MEDIA_EXT = {
    ".mp4",".mxf",".mov",".avi",".r3d",".braw",".ari",
    ".mts",".m2t",".mpg",".mpeg",".m4v",".mkv",
    ".wmv",".flv",".webm",".ts",".3gp",
    ".png",".jpg",".jpeg",".tiff",".tif",".bmp",
    ".dpx",".exr",".psd",".tga",".targa",
}

# ============================================================
# 输入清洗 (sanitize) — 参考井水计划 config.py
# ============================================================
import unicodedata

# 全角/变体 → ASCII 基准 (与井水计划 _CHAR_MAP 保持同步)
_FS_UNSAFE_REPLACE = str.maketrans({
    # 文件系统禁字 → 安全等价形式 (Windows + macOS)
    ':': '\uff1a',   # : → ：(全角冒号, 两个平台都禁止)
    '?': '\uff1f',   # ? → ？
    '*': '\u2731',   # * → ✱
    '"': "'",        # " → '
    '<': '\u300a',   # < → 《
    '>': '\u300b',   # > → 》
    '|': '\uff5c',   # | → ｜
    '/': '&',        # / → & (路径分隔符, 两个平台都禁止)
    '\\': '&',       # \ → &
})

# 控制字符 + BOM + 零宽 — 直接删除
_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060\uFEFF]')

# Windows 保留名 (大小写不敏感)
_WIN_RESERVED = {n.upper() for n in [
    "CON","PRN","AUX","NUL",
    *("COM%d"%i for i in range(1,10)),
    *("LPT%d"%i for i in range(1,10)),
]}

def sanitize_text(text: str, for_filename: bool = False) -> tuple:
    """清洗用户输入，返回 (cleaned: str, warnings: list)

    for_filename=True: 额外处理路径分隔符和保留名
    """
    warnings = []
    if not text.strip():
        return "", ["不能为空"]

    # 1. 控制字符 → 删除 + 警告
    cleaned = _CONTROL_RE.sub('', text)
    if cleaned != text:
        warnings.append("已移除控制字符")

    # 2. NFC 正规化 (统一全角/半角变体)
    cleaned = unicodedata.normalize('NFC', cleaned)

    # 3. 文件系统禁字 → 安全等价字符
    before = cleaned
    cleaned = cleaned.translate(_FS_UNSAFE_REPLACE)
    if cleaned != before:
        warnings.append("已替换文件系统禁字")

    # 4. 首尾空格/点 → 删除
    cleaned = cleaned.strip(' .')

    if for_filename:
        # 检查 Windows 保留名
        if cleaned.upper() in _WIN_RESERVED:
            warnings.append("使用了 Windows 保留名")
            cleaned = "_" + cleaned  # 前缀下划线绕过保留名

    return cleaned, warnings

# ============================================================
# 文件名构建 & 解析
# ============================================================

def build_filename(fields):
    """从字段字典构建文件名 (不含扩展名)"""
    parts = []
    for fd in FIELD_CONFIG:
        v = fields.get(fd["key"], fd["def"])
        nm = fd["name"]; k = fd["key"]
        if nm == "Ep":     parts.append(f"Ep{v}")
        elif nm == "Sc":   parts.append(f"Sc{v}")
        elif nm == "Gr":   parts.append(f"Gr{v}")
        elif nm == "Tk":   parts.append(f"Tk{v}")
        elif nm == "v":    parts.append(f"v{v}")
        elif k == "status": parts.append(v)
        else:              parts.append(v.replace("/","_").replace(" ",""))
    return "_".join(parts) if parts else "unnamed"


# 文件名解析正则 (自动从 FIELD_CONFIG 生成)
def _build_filename_re():
    """从 FIELD_CONFIG 生成解析正则"""
    segments = []
    for fd in FIELD_CONFIG:
        nm = fd["name"]
        k = fd["key"]
        if nm in ("Ep","Sc","Gr","Tk"):
            segments.append(f"{nm}(?P<{k}>\\d{{2,3}})")
        elif nm == "v":
            segments.append(f"v(?P<{k}>\\d{{2,3}}(?:\\.\\d+)?)")
        elif k == "status":
            segments.append(f"(?P<{k}>\\w+)")
        else:
            # desc, author, method — 动态部分
            if k == "desc":
                segments.append(f"(?P<{k}>.+?)(?=_[^_]+_[^_]+_v\\d|_[A-Z][A-Za-z]*_v\\d)")
            elif k == "author":
                segments.append(f"(?P<{k}>[^_]+)")
            elif k == "method":
                # method not in filename, skip
                pass
    # Simplified: use a single comprehensive regex
    return re.compile(
        r"^Ep(?P<ep>\d{2,3})_Sc(?P<sc>\d{2,3})_Gr(?P<gr>\d{2,3})_Tk(?P<tk>\d{2,3})_"
        r"(?P<desc>.+?)_(?P<author>[^_]+)_(?P<method>[^_]+)_v(?P<ver>\d{2,3}(?:\.\d+)?)_"
        r"(?P<status>\w+)(?P<ext>\.[^.]+)$")

FILENAME_RE = _build_filename_re()


def parse_filename(path):
    """解析已命名文件 → {field_key: value}，失败返回 None"""
    name = os.path.basename(path)
    m = FILENAME_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    result = {
        "ep": d["ep"], "sc": d["sc"], "gr": d["gr"], "tk": d["tk"],
        "desc": d["desc"], "author": d["author"], "ver": d["ver"],
        "status": d["status"],
    }
    result["method"] = DESC_TO_METHOD.get(d["desc"], "角色专属版")
    return result


def build_folder(root, entry):
    """构造归档路径: root/EP/EP_SC_GR_method_ver/filename"""
    f = entry.fields
    compound = "EP{ep}_SC{sc}_GR{gr}_{method}_v{ver}".format(**f)
    name = build_filename(f) + entry.ext if hasattr(entry, 'ext') else build_filename(f)
    return os.path.join(root, "EP" + f["ep"], compound, name)


# ============================================================
