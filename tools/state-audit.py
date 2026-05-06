#!/usr/bin/env python3
"""state-audit.py — 检查 .subtitle_state.json 一致性：找出孤键、脏数据、无原片记录等
   --clean: 清理 current_path 不存在且原片也不存在的脏记录"""
import json, os, sys

SF = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ""
CLEAN = "--clean" in sys.argv
if not SF:
    # 自动找
    for root in [
        "/Volumes/MYJC/08_AI_Project/20260407_让你当保安你把九个女总带回家/04_素材/03_去字幕/.subtitle_state.json"
    ]:
        if os.path.exists(root):
            SF = root
            break

if not SF or not os.path.exists(SF):
    print("用法: python3 state-audit.py [.subtitle_state.json]")
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

# 清理脏数据
if CLEAN:
    removed = 0
    for k, v in list(data.items()):
        cur = v.get("current_path", "")
        orig = v.get("original_path", "")
        if v.get("status", "").endswith("_done") and cur and not os.path.exists(cur):
            if not orig or not os.path.exists(orig):
                del data[k]
                removed += 1
    if removed > 0:
        json.dump(data, open(SF, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"\n🧹 清理 {removed} 条脏记录 → {SF}")
