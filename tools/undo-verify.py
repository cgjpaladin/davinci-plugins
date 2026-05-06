#!/usr/bin/env python3
"""undo-verify.py — 验证撤销链路：给定片段名，检查是否可撤销"""
import json, os, sys

SF = "/Volumes/MYJC/08_AI_Project/20260407_让你当保安你把九个女总带回家/04_素材/03_去字幕/.subtitle_state.json"
if not os.path.exists(SF):
    print(f"状态文件不存在: {SF}")
    sys.exit(1)

data = json.load(open(SF, encoding="utf-8"))

if len(sys.argv) > 1:
    # 指定 File Names
    targets = sys.argv[1:]
else:
    # 检查所有 done 记录
    targets = [k for k, v in data.items() if v.get("status", "").endswith("_done")]

ok, fail = 0, 0
for key in targets:
    # 模拟 undo 流程：去后缀 → 查表
    clean = key.split("_去字幕_")[0] + ".mp4" if "_去字幕_" in key else key
    entry = data.get(clean) or data.get(key)
    if entry and entry.get("status", "").endswith("_done"):
        orig = entry.get("original_path", "")
        if orig and os.path.exists(orig):
            ok += 1
        else:
            fail += 1
            print(f"  ❌ {key}: 原片丢失 → {orig}")
    else:
        fail += 1
        print(f"  ❌ {key}: 无状态记录")

print(f"\n可撤销: {ok}/{ok+fail}")
