#!/usr/bin/env python3
"""bump_version — 精确替换版本号（替代不可靠的 sed s/旧/新/）"""
import re, sys

def bump(filepath: str, new_ver: str) -> bool:
    with open(filepath) as f: src = f.read()
    new = re.sub(r'__version__\s*=\s*"[^"]*"', f'__version__ = "{new_ver}"', src)
    if new == src:
        print(f"❌ {filepath}: 未找到 __version__")
        return False
    with open(filepath, 'w') as f: f.write(new)
    # 验证
    with open(filepath) as f:
        if f'__version__ = "{new_ver}"' not in f.read():
            print(f"❌ {filepath}: 写入后验证失败")
            return False
    print(f"✅ {filepath}: {new_ver}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python3 tools/bump_version.py <config.py路径> <新版本号>")
        sys.exit(1)
    sys.exit(0 if bump(sys.argv[1], sys.argv[2]) else 1)
