# -*- coding: utf-8 -*-
"""
pricing_defaults.py — 供应商定价默认值

所有可调数值集中在此文件，修改后下次处理自动生效，无需改代码逻辑。
非程序员可直接打开此文件调整数值（注意保持 Python 字典格式）。

定价来源：
  无痕AI 2.1: wuhenapi_2_1.md 计费表（2026-04-20）
  鬼手: GhostCut 官方定价 VIP3（2026-05-11 线上验证）
  OSS: 阿里云官方定价页（2026-05-05），杭州区域折扣价
"""

# ── 供应商定价表 ──
# 每个供应商的定价模型不同，但都归一化为"积分/秒"或"积分/单位"
PRICING = {
    "wuhenai": {
        # 计费模型：按秒，向上取整
        # sel_area = 手动框选区域（省钱），all_area = 全屏处理
        "models": {
            "video_removal_std": {"sel_area": 1, "all_area": 1.5},  # 积分/秒
            "video_removal_pro":  {"sel_area": 2, "all_area": 3},
        },
        "point_to_yuan": 0.0091,  # 每积分折合人民币（¥1000=110000积分，实测 2026-05-05）
    },
    "ghostcut": {
        # 计费模型：按 30 秒为单位
        "unit_seconds": 30,               # 计费单位（秒）
        "modes": {"basic": 4, "pro_box": 6},  # 积分/30秒 (VIP3: Lite版=4, Pro框选=6)
        "point_to_yuan": 0.19,            # 每积分折合人民币（¥189=1000积分）
    },
}

# 当前活跃供应商（wuhenai / ghostcut）
# 改这里即可切换默认供应商，无需改其他代码
ACTIVE_PROVIDER = "wuhenai"

# 适配器优先顺序：["ghostcut", "wuhenai"] = 鬼手优先无痕备用
# 切换优先级只需改这一行
ADAPTER_PRIORITY = ["wuhenai", "ghostcut"]

# ── OSS 流量定价（阿里云）──
# 杭州区域折扣价，2026-05-05
OSS_PRICE_PER_GB = 0.12  # 人民币/GB（外网流出流量）
