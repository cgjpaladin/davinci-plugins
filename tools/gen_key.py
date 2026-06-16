#!/usr/bin/env python3
"""gen_key — 生成激活码并导入 FC
用法: python3 tools/gen_key.py [数量] [--status sold|unused]
"""
import secrets, json, sys, os
from urllib.request import Request, urlopen

FC = "https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run"
ADMIN = os.environ.get("WB_LICENSE_ADMIN", "8a9b1ab04303ecd32115cb3eae39b62c")

def gen_one():
    h = secrets.token_hex(6).upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}"

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
status = "sold"
if "--status" in sys.argv:
    status = sys.argv[sys.argv.index("--status") + 1]

keys = [{"code": gen_one(), "status": status} for _ in range(n)]
data = json.dumps({"action": "import_keys", "admin_key": ADMIN, "keys": keys}).encode()
req = Request(FC, data=data, headers={"Content-Type": "application/json"})
resp = json.loads(urlopen(req).read())
print(resp.get("msg", resp))
if resp.get("status") == "ok":
    for k in keys:
        print(f"  {k['code']}")
