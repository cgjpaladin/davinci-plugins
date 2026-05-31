# -*- coding: utf-8 -*-
"""激活码管理 — 批量生成、存储、导出、赠送。

裁缝老师用自然语言操作：
  「生成 100 个 Key」   → gen_keys 100
  「送张三一个 Key」    → gift_key 张三
  「看看库存」          → status
"""
import csv
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

# 库存文件
KEYS_FILE = Path(__file__).parent.parent / "data" / "keys.json"

# 激活码格式：DV-XXXX-XXXX-XXXX（4 组 4 位 hex）
KEY_FORMAT = "DV-{a}-{b}-{c}-{d}"


def _ensure_dir():
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list:
    """加载现有 keys.json"""
    _ensure_dir()
    if KEYS_FILE.exists():
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return []


def _save(keys: list):
    """保存 keys.json"""
    _ensure_dir()
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)


def _gen_one() -> str:
    """生成一个激活码"""
    parts = [secrets.token_hex(2).upper() for _ in range(4)]
    return KEY_FORMAT.format(a=parts[0], b=parts[1], c=parts[2], d=parts[3])


def gen_keys(count: int) -> list:
    """批量生成激活码，返回新生成的 Key 列表。

    每个 Key：{key, status, created_at, gifted_to, notes}
    """
    keys = _load()
    existing = {k["key"] for k in keys}
    new_keys = []

    for _ in range(count):
        while True:
            key = _gen_one()
            if key not in existing:
                existing.add(key)
                break
        entry = {
            "key": key,
            "status": "available",     # available | sold | gifted | revoked
            "created_at": int(time.time()),
            "gifted_to": "",
            "notes": "",
        }
        keys.append(entry)
        new_keys.append(entry)

    _save(keys)
    print(f"✅ 生成 {count} 个 Key（总数: {len(keys)}）")
    for k in new_keys:
        print(f"   {k['key']}")
    return new_keys


def export_csv(path: str = None) -> str:
    """导出为发货100兼容的 CSV"""
    if path is None:
        path = str(Path.home() / "Desktop" / "activation_keys.csv")

    keys = _load()
    available = [k for k in keys if k["status"] == "available"]

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["卡密", "面值", "有效期", "备注"])
        for k in available:
            writer.writerow([k["key"], "99", "", "达芬奇交付自检工具"])

    print(f"✅ 导出 {len(available)} 个可用 Key → {path}")
    return path


def gift_key(to: str, key: str = None) -> Optional[str]:
    """赠送一个 Key。

    如果指定 key → 标记该 key。
    否则 → 从 available 中取第一个。
    """
    keys = _load()

    if key:
        for k in keys:
            if k["key"] == key:
                if k["status"] != "available":
                    print(f"❌ {key} 状态为 {k['status']}，不能赠送")
                    return None
                k["status"] = "gifted"
                k["gifted_to"] = to
                _save(keys)
                print(f"✅ {key} 已赠送给 {to}")
                return key
        print(f"❌ 未找到 {key}")
        return None

    # 自动选第一个 available
    for k in keys:
        if k["status"] == "available":
            k["status"] = "gifted"
            k["gifted_to"] = to
            _save(keys)
            print(f"✅ {k['key']} 已赠送给 {to}")
            return k["key"]

    print("❌ 没有可用的 Key")
    return None


def status():
    """打印库存统计"""
    keys = _load()
    counts = {}
    for k in keys:
        s = k["status"]
        counts[s] = counts.get(s, 0) + 1

    print(f"══════ 库存统计 ══════")
    print(f"  总计:   {len(keys)}")
    for s, c in sorted(counts.items()):
        label = {"available": "可用", "sold": "已售", "gifted": "已赠送", "revoked": "已吊销"}.get(s, s)
        print(f"  {label}: {c}")
    print(f"══════════════════════")


# ── CLI ──

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/gen_keys.py gen <数量>        生成 Key")
        print("  python3 tools/gen_keys.py export            导出 CSV")
        print("  python3 tools/gen_keys.py gift <姓名> [key] 赠送")
        print("  python3 tools/gen_keys.py status            库存")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "gen":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        gen_keys(count)
    elif cmd == "export":
        export_csv()
    elif cmd == "gift":
        to = sys.argv[2] if len(sys.argv) > 2 else "朋友"
        key = sys.argv[3] if len(sys.argv) > 3 else None
        gift_key(to, key)
    elif cmd == "status":
        status()
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
