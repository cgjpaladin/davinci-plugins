"""
pricing.py — 去字幕计费模块

所有供应商定价集中管理，换 API = 改一行 ACTIVE_PROVIDER。
上游代码只调 estimate_cost() / point_to_yuan()，不关心底层计费模型。

定价来源：
  无痕AI 2.1: wuhenapi_2_1.md 计费表（2026-04-20）
  鬼手: GhostCut API 官方定价 VIP3
  OSS: 阿里云官方定价页（2026-05-05），杭州区域折扣价
"""

import math
import threading

from config import ADAPTER_CONFIGS

# ═══════════════════════════════════════════
# 供应商定价表
# ═══════════════════════════════════════════

PRICING = {
    "wuhenai": {
        # 计费模型：按秒，向上取整
        "models": {
            "video_removal_std": {"sel_area": 1, "all_area": 1.5},  # 积分/秒
            "video_removal_pro":  {"sel_area": 2, "all_area": 3},
        },
        "point_to_yuan": 0.0091,  # ¥1000→110000积分，裁缝老师实测（2026-05-05）
    },
    "ghostcut": {
        # 计费模型：按30秒单位
        "unit_seconds": 30,
        "modes": {"basic": 1, "lite": 4, "pro_box": 5, "pro": 10},  # 点/30秒
        "point_to_yuan": 0.19,    # ¥189/1000点
    },
}

# 当前活跃供应商
ACTIVE_PROVIDER = "wuhenai"


# ═══════════════════════════════════════════
# OSS 费用（杭州区域，官网折扣价，2026-05-05）
# ═══════════════════════════════════════════

OSS_PRICING = {
    "storage_per_gb_month": 0.09,     # 标准存储 元/GB/月
    "traffic_out_per_gb": 0.50,       # 外网流出(忙时，保守估计) 元/GB
    "traffic_out_offpeak_per_gb": 0.25,  # 闲时 00:00-08:00
    "put_per_10k": 0.01,              # PUT请求 元/万次（超出500万后）
    "get_per_10k": 0.01,              # GET请求 元/万次（超出2000万后）
}


class OSSCostTracker:
    """OSS 使用量追踪（线程安全）。

    适配器和下载函数各自记录操作，最后汇总计费。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.bytes_uploaded = 0
            self.bytes_downloaded = 0
            self.put_count = 0
            self.get_count = 0

    def track_upload(self, size_bytes: int):
        with self._lock:
            self.bytes_uploaded += size_bytes
            self.put_count += 1

    def track_download(self, size_bytes: int):
        with self._lock:
            self.bytes_downloaded += size_bytes
            self.get_count += 1

    def snapshot(self) -> dict:
        """返回当前使用量和费用估算"""
        with self._lock:
            traffic_gb = self.bytes_downloaded / (1024 ** 3)
            traffic_cost = traffic_gb * OSS_PRICING["traffic_out_per_gb"]
            # 请求费用：免费额度内均为0
            return {
                "upload_bytes": self.bytes_uploaded,
                "download_bytes": self.bytes_downloaded,
                "traffic_gb": round(traffic_gb, 4),
                "traffic_cost": round(traffic_cost, 4),
                "put_requests": self.put_count,
                "get_requests": self.get_count,
                "total_cost": round(traffic_cost, 4),
            }


# 全局单例
oss_tracker = OSSCostTracker()

# ═══════════════════════════════════════════
# 公共接口
# ═══════════════════════════════════════════

def estimate_cost(tasks: list, mode: str, provider: str = None) -> tuple:
    """
    统一计费估算入口。

    Args:
        tasks: TaskRecord 列表
        mode: 处理模式（basic/lite/pro_box/pro）
        provider: 供应商名称，默认 ACTIVE_PROVIDER

    Returns:
        (total_units, total_points, unit_cost, yuan)
        - total_units: 计费单位数（秒 or 30秒块）
        - total_points: 预估积分数
        - unit_cost: 单价（积分/单位）
        - yuan: 人民币估算
    """
    provider = provider or ACTIVE_PROVIDER
    pricing = PRICING.get(provider)
    if not pricing:
        raise ValueError(f"未知供应商: {provider}")

    pt_yuan = pricing["point_to_yuan"]

    if provider == "wuhenai":
        # 从适配器配置动态读取当前 model/method，与 config.py 保持同步
        wu_cfg = ADAPTER_CONFIGS.get("wuhenai_v21", {})
        current_model = wu_cfg.get("model", "video_removal_std")
        current_method = wu_cfg.get("method", "sel_area")
        model = pricing["models"].get(current_model, pricing["models"]["video_removal_std"])
        unit_cost = model.get(current_method, 1)
        total_units = sum(math.ceil(t.duration) for t in tasks)
        total_points = math.ceil(total_units * unit_cost)

    elif provider == "ghostcut":
        # 按30秒单位计费
        unit_sec = pricing["unit_seconds"]
        unit_cost = pricing["modes"].get(mode, 1)
        total_units = sum(max(1, math.ceil(t.duration / unit_sec)) for t in tasks)
        total_points = total_units * unit_cost

    else:
        raise ValueError(f"未实现的供应商计费: {provider}")

    yuan = round(total_points * pt_yuan, 2)
    return total_units, total_points, unit_cost, yuan


def point_to_yuan(points: float, provider: str = None) -> float:
    """积分 → 人民币"""
    provider = provider or ACTIVE_PROVIDER
    rate = PRICING.get(provider, {}).get("point_to_yuan", 0.19)
    return round(points * rate, 2)


def get_provider_rate(provider: str = None) -> float:
    """查询当前供应商的积分汇率"""
    provider = provider or ACTIVE_PROVIDER
    return PRICING.get(provider, {}).get("point_to_yuan", 0.19)
