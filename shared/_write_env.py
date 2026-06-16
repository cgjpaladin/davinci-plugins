#!/usr/bin/env python3
"""更新安装后写入凭证配置"""
import os, sys

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

# 确保 WB_LICENSE_URL 存在
LICENSE_URL = "https://license-node-mtqaghwijy.cn-hangzhou.fcapp.run"

try:
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
except FileNotFoundError:
    lines = []

has_license = any("WB_LICENSE_URL" in l for l in lines)
if not has_license:
    with open(ENV_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n# License 后端（阿里云 FC）\nWB_LICENSE_URL={LICENSE_URL}\n")
    print(f"  ✓ WB_LICENSE_URL added to .env")
else:
    print(f"  ✓ WB_LICENSE_URL already present")
