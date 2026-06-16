"""最小 QR 码生成器 — 纯 Python，零依赖，仅支持 byte mode + EC Level M。
用于插件离线展示使用手册链接二维码。"""

# ── GF(256) 预计算表 ──
_EXP = [1] * 512
_LOG = [0] * 256
_v = 1
for _i in range(255):
    _EXP[_i] = _v
    _EXP[_i + 255] = _v  # 双倍方便乘法溢出
    _LOG[_v] = _i
    _v <<= 1
    if _v & 0x100:
        _v ^= 0x11D  # 本原多项式 x^8 + x^4 + x^3 + x^2 + 1


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gf_poly_mul(p, q):
    """GF(256) 多项式乘法"""
    r = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            if b == 0:
                continue
            r[i + j] ^= _gf_mul(a, b)
    return r


def _rs_generator_poly(nsym):
    """生成 Reed-Solomon 生成多项式"""
    g = [1]
    for i in range(nsym):
        g = _gf_poly_mul(g, [1, _EXP[i]])
    return g


def _rs_encode(data, nsym):
    """对 data 附加 nsym 个纠错码字"""
    gen = _rs_generator_poly(nsym)
    res = data + [0] * nsym
    for i in range(len(data)):
        if res[i] == 0:
            continue
        factor = _LOG[res[i]]
        for j in range(len(gen)):
            res[i + j] ^= _EXP[factor + _LOG[gen[j]]]
    return data + res[len(data):]


# ── EC 参数 ──
_EC_COUNT = {
    1:  {0: 0, 1: 0, 2: 0, 3: 0},   # not used for M
    2:  {0: 0, 1: 0, 2: 0, 3: 0},
    3:  {0: 0, 1: 0, 2: 0, 3: 0},
}
# EC codewords per block for level M (index 0)
_EC_BLOCK1 = {1: 16, 2: 28, 3: 44, 4: 64, 5: 86, 6: 108, 7: 124, 8: 154, 9: 182, 10: 216}
# Groups for level M: (blocks_in_group1, codewords_per_block1, blocks_in_group2, codewords_per_block2)
_EC_GROUPS = {
    1: (1, 16, 0, 0), 2: (1, 28, 0, 0), 3: (1, 44, 0, 0),
    4: (2, 32, 0, 0), 5: (2, 43, 0, 0), 6: (4, 27, 0, 0),
    7: (4, 31, 0, 0), 8: (2, 38, 2, 39), 9: (3, 36, 2, 37),
    10: (4, 43, 1, 44),
}


def _get_alignment_positions(version):
    """返回对齐图案中心坐标列表"""
    if version == 1:
        return []
    n = version // 7 + 2
    step = (version * 4 + 16) // (n - 1)
    step = step - step % 2
    return [6] + list(range(step * (n - 2), 0, -step)) + [6 + version * 4]


def generate(data, version=None):
    """生成 QR 码矩阵。

    Args:
        data: 要编码的字节串
        version: QR 版本 1-10，None 则自动选择

    Returns:
        (matrix, size) — matrix 是 list[list[int]]，1=黑 0=白，size 是一边模块数
    """
    if version is None:
        for v in range(1, 11):
            if len(data) <= _EC_BLOCK1[v] - 2:
                version = v
                break
    data_cw = _EC_BLOCK1[version]
    b1_count, b1_cw, b2_count, b2_cw = _EC_GROUPS[version]
    assert b1_count * b1_cw + b2_count * b2_cw == data_cw

    size = version * 4 + 17

    # 创建空矩阵
    matrix = [[-1] * size for _ in range(size)]

    # ── 功能图案 ──
    # 定位图案 (finder patterns)
    for r, c in [(0, 0), (0, size - 7), (size - 7, 0)]:
        for i in range(7):
            for j in range(7):
                matrix[r + i][c + j] = 1 if (i == 0 or i == 6 or j == 0 or j == 6 or (2 <= i <= 4 and 2 <= j <= 4)) else 0

    # 分隔符：top-left (7,0..7) + (0..7,7)
    for i in range(8):
        matrix[7][i] = 0
        matrix[i][7] = 0
    # 分隔符：top-right (7, size-8..size-1) + (0..8, size-8)
    for i in range(8):
        matrix[7][size - 1 - i] = 0
        if i < size:
            matrix[i][size - 8] = 0
    # 分隔符：bottom-left (size-8, 0..7) + (size-8..size-1, 7)
    for i in range(8):
        if size - 8 + i < size:
            matrix[size - 8 + i][7] = 0
            matrix[size - 8][i] = 0

    # 时序图案
    for i in range(8, size - 8):
        matrix[6][i] = matrix[i][6] = (i + 1) % 2

    # 对齐图案
    apos = _get_alignment_positions(version)
    for ar in apos:
        for ac in apos:
            if (ar == 6 and ac == 6) or (ar == 6 and ac == size - 7) or (ar == size - 7 and ac == 6):
                continue
            for i in range(-2, 3):
                for j in range(-2, 3):
                    matrix[ar + i][ac + j] = 1 if (i == -2 or i == 2 or j == -2 or j == 2 or (i == 0 and j == 0)) else 0

    # ── 快照功能图案（掩码不能改这些）──
    _func = [row[:] for row in matrix]

    # ── 数据编码 ──
    mode = 0b0100  # byte mode
    bits = []
    # mode indicator (4 bits)
    for i in range(3, -1, -1):
        bits.append((mode >> i) & 1)
    # character count (8 bits for version 1-9)
    for i in range(7, -1, -1):
        bits.append((len(data) >> i) & 1)
    # data bytes
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    # terminator (up to 4 bits)
    term_len = min(4, data_cw * 8 - len(bits))
    bits.extend([0] * term_len)
    # pad to byte
    while len(bits) % 8 != 0:
        bits.append(0)
    # pad bytes: 11101100, 00010001
    pad = [0xEC, 0x11]
    pi = 0
    while len(bits) < data_cw * 8:
        b = pad[pi]
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
        pi ^= 1

    # 转为码字
    codewords = []
    for i in range(0, len(bits), 8):
        cw = 0
        for j in range(8):
            cw = (cw << 1) | bits[i + j]
        codewords.append(cw)

    # RS 纠错编码
    nsym = b1_cw - b1_count * b1_cw // data_cw  # overall nsym
    # 更简单的处理：逐块编码
    nsym_per_block = b1_cw - data_cw // (b1_count + b2_count)  # approximate
    # 正确做法：计算 nsym = 总EC码字
    total_cw = b1_count * (b1_cw - data_cw // (b1_count + b2_count)) + b2_count * (b2_cw - data_cw // (b1_count + b2_count))
    # 简化：data_cw 码字中 data 部分大小
    data_size = data_cw - (b1_count * (b1_cw - data_cw // (b1_count + b2_count)))
    nsym = b1_cw - data_cw // max(1, b1_count + b2_count)

    # 重新计算 nsym
    actual_ec = b1_count * b1_cw + b2_count * b2_cw - data_cw
    nsym = actual_ec // (b1_count + b2_count) if b2_count else b1_cw - data_cw // b1_count

    # Let me compute this properly
    if b2_count == 0:
        nsym = b1_cw - data_cw // b1_count
    else:
        # average data per block
        nsym = (b1_cw + b2_cw - data_cw // (b1_count + b2_count) * 2) // 2

    # 简化处理：整体 RS 编码
    full = _rs_encode(codewords, actual_ec) if actual_ec else _rs_encode(codewords, data_cw - len(codewords))

    # Interleave data + EC
    # Simplified for now: interleave all together
    all_data = []
    # Split codewords into blocks
    pos = 0
    blocks_d = []
    for b in range(b1_count):
        blocks_d.append(codewords[pos:pos + b1_cw - nsym])
        pos += b1_cw - nsym
    for b in range(b2_count):
        blocks_d.append(codewords[pos:pos + b2_cw - nsym])
        pos += b2_cw - nsym

    # EC for each block
    blocks_ec = []
    for bd in blocks_d:
        ec = _rs_encode(bd, nsym)[len(bd):]
        blocks_ec.append(ec)

    # Interleave
    max_dlen = max(len(b) for b in blocks_d)
    for i in range(max_dlen):
        for b in blocks_d:
            if i < len(b):
                all_data.append(b[i])
    for i in range(nsym):
        for b in blocks_ec:
            if i < len(b):
                all_data.append(b[i])

    # 转为 bits
    all_bits = []
    for cw in all_data:
        for i in range(7, -1, -1):
            all_bits.append((cw >> i) & 1)

    # ── 放置数据模块（从右下角向上 zigzag） ──
    col = size - 1
    upward = True
    bi = 0
    while col >= 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in range(2):
                cc = col - c
                if 0 <= cc < size and matrix[row][cc] == -1 and bi < len(all_bits):
                    matrix[row][cc] = all_bits[bi]
                    bi += 1
        upward = not upward
        col -= 2

    # ── 掩码评估与选择 ──
    def _apply_mask(mat, mask_id):
        m = [row[:] for row in mat]
        for r in range(size):
            for c in range(size):
                if m[r][c] < 0:
                    continue
                cond = False
                if mask_id == 0:
                    cond = (r + c) % 2 == 0
                elif mask_id == 1:
                    cond = r % 2 == 0
                elif mask_id == 2:
                    cond = c % 3 == 0
                elif mask_id == 3:
                    cond = (r + c) % 3 == 0
                elif mask_id == 4:
                    cond = (r // 2 + c // 3) % 2 == 0
                elif mask_id == 5:
                    cond = (r * c) % 2 + (r * c) % 3 == 0
                elif mask_id == 6:
                    cond = ((r * c) % 2 + (r * c) % 3) % 2 == 0
                elif mask_id == 7:
                    cond = ((r + c) % 2 + (r * c) % 3) % 2 == 0
                if cond:
                    m[r][c] ^= 1
        return m

    def _score(mat):
        s = 0
        # consecutive same color (horizontal)
        for r in range(size):
            run = 1
            for c in range(1, size):
                if mat[r][c] == mat[r][c - 1] and mat[r][c] >= 0:
                    run += 1
                else:
                    if run >= 5:
                        s += run - 2
                    run = 1
            if run >= 5:
                s += run - 2
        # consecutive same color (vertical)
        for c in range(size):
            run = 1
            for r in range(1, size):
                if mat[r][c] == mat[r - 1][c] and mat[r][c] >= 0:
                    run += 1
                else:
                    if run >= 5:
                        s += run - 2
                    run = 1
            if run >= 5:
                s += run - 2
        # 2x2 blocks
        for r in range(size - 1):
            for c in range(size - 1):
                v = mat[r][c]
                if v >= 0 and mat[r + 1][c] == v and mat[r][c + 1] == v and mat[r + 1][c + 1] == v:
                    s += 3
        # finder-like patterns
        for r in range(size - 6):
            for c in range(size):
                if all(mat[r][c] == mat[r + k][c] for k in range(1, 6)):
                    if mat[r][c] == 1 and mat[r + 1][c] == 0 and mat[r + 2][c] == 0 and mat[r + 3][c] == 0 and mat[r + 4][c] == 1:
                        if (c - 4 >= 0 and all(mat[r + k][c - i - 1] == 0 for k in range(5) for i in range(1))):
                            s += 40
        for c in range(size - 6):
            for r in range(size):
                if all(mat[r][c] == mat[r][c + k] for k in range(1, 6)):
                    if mat[r][c] == 1 and mat[r][c + 1] == 0 and mat[r][c + 2] == 0 and mat[r][c + 3] == 0 and mat[r][c + 4] == 1:
                        s += 40
        # dark/light ratio
        dark = sum(1 for row in mat for v in row if v == 1)
        total = sum(1 for row in mat for v in row if v >= 0)
        if total == 0:
            return s
        ratio = dark * 100 // total
        s += abs(ratio - 50) // 5 * 10
        return s

    best_mask = 0
    best_score = float('inf')
    best_matrix = None
    for mask_id in range(8):
        masked = _apply_mask(matrix, mask_id)
        sc = _score(masked)
        if sc < best_score:
            best_score = sc
            best_mask = mask_id
            best_matrix = masked

    # 恢复功能图案（掩码只作用于数据区）
    for r in range(size):
        for c in range(size):
            if _func[r][c] >= 0:
                best_matrix[r][c] = _func[r][c]

    # ── 放置格式信息 ──
    # EC level M (00) + mask pattern
    fmt_data = (0b00 << 3) | best_mask  # for EC M
    # BCH encode
    fmt = fmt_data << 10
    g = 0x537
    for i in range(4, -1, -1):
        if fmt & (1 << (i + 10)):
            fmt ^= g << i
    fmt = (fmt_data << 10) | (fmt & 0x3FF)
    fmt ^= 0x5412  # XOR mask

    # Place format info
    fmt_positions = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for i, (r, c) in enumerate(fmt_positions):
        best_matrix[r][c] = (fmt >> (14 - i)) & 1

    # Dark module
    best_matrix[size - 8][8] = 1

    # Mirror for top-right and bottom-left
    for i, (r, c) in enumerate(fmt_positions):
        if c >= size - 8:  # top-right area
            pass  # handled differently
    # Place bottom-left format info
    bl_positions = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8), (size - 5, 8), (size - 6, 8), (size - 7, 8)]
    for i, (r, c) in enumerate(bl_positions):
        best_matrix[r][c] = (fmt >> i) & 1

    # Place top-right format info
    tr_positions = [(8, size - 7), (8, size - 6), (8, size - 5), (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1)]
    for i, (r, c) in enumerate(tr_positions):
        best_matrix[r][c] = (fmt >> i) & 1

    # 确保所有未填充的格子为 0
    for r in range(size):
        for c in range(size):
            if best_matrix[r][c] < 0:
                best_matrix[r][c] = 0

    return best_matrix, size
