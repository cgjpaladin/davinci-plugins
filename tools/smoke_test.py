#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 去字幕 — 基础功能冒烟测试

选一个干净片段 → 设 IO → 标橙色 → 跑 5 步全流程 → 验证结果。

用法:
    # 在本机达芬奇里跑（需要达芬奇已启动 + 项目已打开 + 时间线有片段）
    python3 smoke_test.py

验证项:
    1. 扫描筛选 (IO 重叠 + 颜色过滤)
    2. API 提交 + 并行
    3. 下载 + ReplaceClip + 颜色恢复
    4. 缓存复用
    5. 批量撤销 + 颜色保留
"""
import os, sys, time, subprocess, json

_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
_DR_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.insert(0, _DR_MODULES)

import DaVinciResolveScript as dvr


# ── Step 0: 前置检查 ──
def check_env():
    r = dvr.scriptapp("Resolve")
    if not r:
        raise RuntimeError("达芬奇未启动")
    pj = r.GetProjectManager().GetCurrentProject()
    if not pj:
        raise RuntimeError("没有打开项目")
    tl = pj.GetCurrentTimeline()
    if not tl:
        raise RuntimeError("没有打开时间线")
    return r, pj, tl


# ── Step 1: 选一个干净片段 ──
def pick_clean_clip(tl):
    """找时间线上第一个 没被处理过 且 有 MediaPoolItem 的片段。"""
    for t in range(1, tl.GetTrackCount("video") + 1):
        for item in tl.GetItemListInTrack("video", t) or []:
            mp = item.GetMediaPoolItem()
            if not mp:
                continue
            path = mp.GetClipProperty("File Path") or ""
            if "_去字幕" in path:
                continue
            name = item.GetName()
            start = item.GetStart()
            end = item.GetEnd()
            return t, item, mp, name, start, end
    return None


# ── Step 2: 设 IO（包住片段，略大一圈） ──
def set_io(tl, item_start, item_end):
    margin = 5
    io_in = max(0, item_start - margin)
    io_out = item_end + margin
    tl.SetMarkInOut(io_in, io_out)
    return io_in, io_out


# ── Step 3: 标橙色 ──
def mark_orange(item, mp_item):
    item.SetClipColor("Orange")
    mp_item.SetClipColor("Orange")


# ── 主流程 ──
def main():
    print("═══ AI 去字幕 冒烟测试 ═══\n")

    r, pj, tl = check_env()
    print(f"✅ 环境: {pj.GetName()} / {tl.GetName()}")

    clip = pick_clean_clip(tl)
    if not clip:
        print("❌ 时间线上没有可用片段（都已处理或缺少媒体池项）")
        return 1
    track, item, mp, name, start, end = clip
    print(f"✅ 选中: [{track}] {name} ({start}→{end})")

    io_in, io_out = set_io(tl, start, end)
    print(f"✅ IO: {io_in}→{io_out}")

    mark_orange(item, mp)
    time.sleep(0.5)

    print(f"\n── 请手动操作 ──")
    print(f"   1. 点「扫描选区」→ 应找到 1 个片段、需处理 1、预估约 ¥0.15")
    print(f"   2. 点「开始处理」→ 应 API 提交 → 进度 10%→100% → 颜色恢复橙色")
    print(f"   3. 再点「开始处理」→ 应缓存命中 ¥0")
    print(f"   4. 点「撤销替换」→ 应撤销 1/1，颜色保持橙色")
    print(f"\n   片段: {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
