#!/usr/bin/env python3
"""HEIBA XOR 自解密 Lua 插件还原脚本。
用法: python3 decrypt_heiba_xor.py <输入.lua> <输出.lua>
"""
import base64, re, sys


def lua_bxor(a: int, b: int) -> int:
    """模拟 Lua 5.1 的 bxor 函数（32位逐位异或）"""
    r = 0
    for i in range(32):
        if (a // 2 + b // 2) != (a / 2 + b / 2):
            r += 1 << i
        a = a // 2
        b = b // 2
    return r


def decrypt(encrypted: str, key: str) -> bytes:
    """Base64 解码 → 逐字节 XOR（密钥循环）"""
    decoded = base64.b64decode(encrypted)
    key_bytes = key.encode("utf-8")
    return bytes(d ^ key_bytes[i % len(key_bytes)] for i, d in enumerate(decoded))


def main():
    if len(sys.argv) != 3:
        print(f"用法: {sys.argv[0]} <加密文件路径> <输出路径>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 encrypted_code（最小匹配，避免贪到后面中文注释）
    m = re.search(r'encrypted_code\s*=\s*"([^"]+)"', content)
    if not m:
        print("❌ 未找到 encrypted_code 变量")
        sys.exit(1)
    encrypted = m.group(1)

    # 提取 key
    km = re.search(r'local\s+key\s*=\s*"(.+)"', content)
    if not km:
        print("❌ 未找到密钥")
        sys.exit(1)
    key = km.group(1)

    print(f"密钥: {key}  密文长: {len(encrypted)} 字符")

    plain = decrypt(encrypted, key)
    out = sys.argv[2]
    with open(out, "w", encoding="utf-8") as f:
        f.write(plain.decode("utf-8"))

    print(f"✅ 解密完成 → {out}  ({len(plain)} 字节, {len(plain.decode('utf-8').splitlines())} 行)")


if __name__ == "__main__":
    main()
