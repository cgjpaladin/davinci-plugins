"""检查器 — 文件质量检测（从 naming.py 拆分）"""
import os, re, statistics

DOUBLE_EXT_RE = re.compile(r"\.(mp4|mov|mxf|avi|mkv)\.(mp4|mov|mxf|avi|mkv)$", re.IGNORECASE)

# 检查器
# ============================================================

def check_zero_byte(filepath):
    """零字节文件检测"""
    try:
        return os.path.getsize(filepath) == 0
    except OSError:
        return False


def check_double_ext(filename):
    """扩展名重复 .mp4.mp4"""
    return bool(DOUBLE_EXT_RE.search(filename.lower()))


def check_name_format(filename):
    """文件名是否符合命名规范"""
    return FILENAME_RE.match(os.path.basename(filename)) is not None


def check_field_completeness(fields):
    """检查必填字段完整性，返回缺失字段列表"""
    missing = []
    for fd in FIELD_CONFIG:
        if fd["key"] == "tk":
            continue  # Tk 自动生成
        v = fields.get(fd["key"], "").strip()
        if not v or v in ("请选择", ""):
            missing.append(fd["label"])
        rx = fd.get("regex")
        if rx and v and not re.match(rx, v):
            missing.append(f"{fd['label']}(格式错误)")
    return missing


def check_size_anomaly(filepaths):
    """检测文件大小异常 (变异系数 > 1.0 标警告)"""
    import statistics
    sizes = []
    for fp in filepaths:
        try:
            s = os.path.getsize(fp)
            if s > 0:
                sizes.append((fp, s))
        except OSError:
            continue
    if len(sizes) < 3:
        return []
    values = [s for _, s in sizes]
    try:
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev > 0 and mean > 0 and stdev / mean > 1.0:
            return [(fp, s) for fp, s in sizes if abs(s - mean) > 2 * stdev]
    except statistics.StatisticsError:
        pass
    return []
