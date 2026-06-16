"""QR 码展示 — 使用 qrcode 库预计算矩阵（零运行时依赖）。

MANUAL_URL 变更时，运行 _gen_qr_matrix.py 重新生成。
"""

import base64

# 预计算的 QR 矩阵（version 5, EC M, 37x37, base64 打包）
_MATRIX_B64 = (
    "/oj1k/wXq2NQbq0DPLt0rbjV267VBK7BGTalB/qqqq/gC3CfAJ+Wrby/TsJxP5D8"
    "mS8zKHbEGfaxY4g0pOrxqG0dX1lb8y1MAqwbx81LPixVTMo70kNV4jLEBakVtfgr"
    "+Bj9i6hRTD+PTT4428K9no3lqhZFtOLOOrymd2cRElZg62SKrfwAX8kEU/v2fqow"
    "XVxvE7qzB7+N14UHMK6Sdl8nBDWwSf/q3JrygA=="
)

_SIZE = 37  # 37x37


def _decode():
    """解码预计算矩阵→ list[list[int]]"""
    packed = base64.b64decode(_MATRIX_B64)
    bits = "".join(f"{b:08b}" for b in packed)
    matrix = []
    for r in range(_SIZE):
        row = [int(bits[r * _SIZE + c]) for c in range(_SIZE)]
        matrix.append(row)
    return matrix


def generate(data=None, version=None):
    """兼容旧接口，忽略参数，返回预计算矩阵。

    Returns:
        (matrix, size) — matrix 是 list[list[int]]，1=黑 0=白
    """
    _ = data, version  # unused — pre-computed
    return _decode(), _SIZE
