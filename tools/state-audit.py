#!/usr/bin/env python3
"""state-audit.py — 检查 .watermark_state.json 一致性：找出孤键、脏数据、无原片记录等"""
import json, os, sys

SF = sys.argv[1] if len(sys.argv) > 1 else ""
if not SF:
    # 自动找
    for root in [
        "/Volumes/MYJC/08_AI_Project/20260407_让你当保安你把九个女总带回家/04_素材/03_去字幕/.watermark_state.json"
    ]:
        if os.path.exists(root):
            SF = root
            break

if not SF or not os.path.exists(SF):
    print("用法: python3 state-audit.py [.watermark_state.json]")
    sys.exit(1)

data = json.load(open(SF, encoding="utf-8"))
print(f"文件: {SF}")
print(f"总记录: {len(data)}\n")

issues = []
done_keys = [k for k, v in data.items() if v.get("status", "").endswith("_done")]
clean_keys = [k for k, v in data.items() if v.get("status") == "original"]

for k, v in data.items():
    orig = v.get("original_path", "")
    cur = v.get("current_path", "")
    status = v.get("status", "?")

    # 检查原始路径
    if status != "original" and orig and not os.path.exists(orig):
        issues.append(f"原片丢失: {k} → {orig}")

    # 检查孤键（done 但没有 original_path）
    if status.endswith("_done") and not v.get("original_path"):
        issues.append(f"无原片记录: {k}")

    # 检查 current_path
    if cur and not os.path.exists(cur):
        issues.append(f"current_path 不存在: {k} → {cur}")

print(f"已处理: {len(done_keys)} 个")
print(f"仅记录: {len(clean_keys)} 个")
print(f"问题: {len(issues)} 个")
if issues:
    for i in issues[:20]:
        print(f"  ⚠ {i}")
    if len(issues) > 20:
        print(f"  ... 共 {len(issues)} 个问题")
