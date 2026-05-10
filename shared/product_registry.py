# -*- coding: utf-8 -*-
"""
product_registry.py — 达芬奇插件工坊 产品注册表

所有产品在此注册。加新产品第一步：在此加一行。
参考交付自检 CHECKS 注册表模式：单一真相源，额外字段不破坏兼容性。

用途：
  1. 自动发现已安装产品（push_all.sh / install.sh）
  2. 版本兼容检查（产品要求 shared/ 最低版本 vs 实际版本）
  3. 售卖管理（客户买了哪几个，安装时只给对应的）
  4. 未来统一启动器 UI（根据注册表生成产品菜单）

字段说明：
  id:        唯一标识（snake_case，CLI --product 引用）
  name:      人类可读产品名
  dir:       产品目录名（push_all.sh 同步用）
  category:  产品类别（AI 处理 / 检查 / 音频 / 字幕）
  pipeline:  "模块:类名" 或 None（非 BasePipeline 产品填 None）
  status:    "active"=已上线 / "planned"=已调研待开发 / "stub"=仅占位
  min_shared: shared/ 最低版本要求
  description: 一句话介绍
"""

PRODUCTS = {
    # ── AI 处理类（BasePipeline 子类）──
    "subtitle": {
        "id": "subtitle",
        "name": "AI 去字幕",
        "dir": "AI去字幕",
        "category": "AI 处理",
        "pipeline": "AI去字幕.pipeline:SubtitlePipeline",
        "status": "active",
        "min_shared": "1.0",
        "description": "一键去除短剧字幕，支持无痕AI和鬼手",
    },
    "lipsync": {
        "id": "lipsync",
        "name": "AI 换口型",
        "dir": "AI换口型",
        "category": "AI 处理",
        "pipeline": None,  # 待开发
        "status": "planned",
        "min_shared": "1.0",
        "description": "AI 替换视频中人物口型",
    },
    "voice_clone": {
        "id": "voice_clone",
        "name": "AI 语音克隆",
        "dir": "AI语音克隆",
        "category": "AI 处理",
        "pipeline": None,
        "status": "planned",
        "min_shared": "1.0",
        "description": "克隆角色声音替换原片配音",
    },
    "super_resolution": {
        "id": "super_resolution",
        "name": "AI 超分辨率",
        "dir": "AI超分辨率",
        "category": "AI 处理",
        "pipeline": None,
        "status": "planned",
        "min_shared": "1.0",
        "description": "提升视频分辨率（720p→1080p/4K）",
    },
    "add_subtitle": {
        "id": "add_subtitle",
        "name": "AI 加字幕",
        "dir": "AI加字幕",
        "category": "AI 处理",
        "pipeline": None,
        "status": "stub",
        "min_shared": "1.0",
        "description": "AI 自动生成字幕",
    },

    # ── 检查类（非 BasePipeline 产品）──
    "delivery_checker": {
        "id": "delivery_checker",
        "name": "交付自检",
        "dir": "交付自检工具",
        "category": "检查",
        "pipeline": None,  # 检查类不走 BasePipeline
        "status": "active",
        "min_shared": "1.0",
        "description": "时间线交付前自检：轨道/字幕/黑帧/音频",
    },

    # ── 音频类 ──
    "audio_mood": {
        "id": "audio_mood",
        "name": "音频情绪分类",
        "dir": "音频情绪分类",
        "category": "音频",
        "pipeline": None,
        "status": "planned",
        "min_shared": "1.0",
        "description": "分析音频情绪标签辅助剪辑选曲",
    },
}


# ═══════════════════════════════════════════
# 查询函数
# ═══════════════════════════════════════════

def get_active_products(category: str = None) -> dict:
    """返回 status="active" 的产品列表。可选按 category 过滤。"""
    result = {}
    for pid, info in PRODUCTS.items():
        if info.get("status") != "active":
            continue
        if category and info.get("category") != category:
            continue
        result[pid] = info
    return result


def get_by_dir(dir_name: str) -> dict:
    """按产品目录名查找。找不到返回 None。"""
    for info in PRODUCTS.values():
        if info.get("dir") == dir_name:
            return info
    return None


def get_pipeline_products() -> dict:
    """返回所有 BasePipeline 子类产品（pipeline 字段非 None + status=active）。"""
    result = {}
    for pid, info in PRODUCTS.items():
        if info.get("pipeline") and info.get("status") == "active":
            result[pid] = info
    return result


def get_categories() -> list:
    """返回所有产品类别（去重，按注册顺序）。"""
    seen = set()
    cats = []
    for info in PRODUCTS.values():
        cat = info.get("category", "")
        if cat and cat not in seen:
            cats.append(cat)
            seen.add(cat)
    return cats
