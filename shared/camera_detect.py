# -*- coding: utf-8 -*-
"""
camera_detect.py — 摄影机实拍素材检测

双路径检测：
  1. 达芬奇媒体池元数据（ISO/Camera Model/Lens/Gamma/Color Space）
  2. 文件名模式匹配（10品牌12种命名规范，2026-05-11 豆包调研核实）

跨项目通用：AI去字幕 / 交付自检 / 未来所有插件。
"""

import re

# ═══════════════════════════════════════════
# 文件名正则（拦截所有镜头记录的素材）
# ═══════════════════════════════════════════

_CAM_FNAME_RE = re.compile(
    r'DJI'                          # DJI 无人机/运动相机
    r'|IMG_\d{4}'                   # iPhone
    r'|VID_\d{8}'                   # 三星/华为/小米/OPPO
    r'|DSC[F_]?\d{4}'               # Nikon DSC_ / Fuji DSCF
    r'|MVI_\d{4}'                   # Canon 消费级
    r'|GOPR\d{4}'                   # GoPro 主文件
    r'|GP\d{2}\d{4}'                # GoPro 分段
    r'|INSTA_\d'                    # Insta360
    r'|P\d{7}'                      # 松下 LUMIX
    r'|L\d{7}'                      # 徕卡
    r'|[A-Z]\d{3,4}'                # 通用: 所有专业机(Sony/Canon/ARRI/RED/BMD等)
)

# ═══════════════════════════════════════════
# 达芬奇媒体池元数据字段（fukco/media-metadata 校验）
# ═══════════════════════════════════════════

_CAM_META_FIELDS = (
    # 摄影机身份
    "Camera Type", "Camera Manufacturer", "Camera Serial #", "Camera ID",
    "Camera Notes", "Camera Format", "Camera Firmware",
    # 镜头
    "Lens Type", "Lens Number", "Lens Notes",
    # 曝光
    "ISO", "Shutter Type", "Shutter Angle", "Shutter", "Shutter Speed",
    "Camera Aperture Type", "Camera Aperture",
    # 色彩
    "White Point (Kelvin)", "White Balance Tint",
    "Gamma", "Color Space", "Gamma Notes", "Color Space Notes",
    # 其他
    "Camera FPS", "Focal Point (mm)", "Distance",
    "Filter", "ND Filter", "Compression Ratio", "Codec Bitrate",
    "Sensor Area Captured", "Time-lapse Interval",
)


def is_camera_footage(mp_item) -> bool:
    """判断 MediaPoolItem 是否为摄影机实拍素材。

    Args:
        mp_item: DaVinci Resolve MediaPoolItem 对象

    Returns:
        True = 实拍素材，不应处理
    """
    # ── 路径1: 媒体池元数据 ──
    try:
        for f in _CAM_META_FIELDS:
            if mp_item.GetClipProperty(f):
                return True
    except Exception:
        pass

    # ── 路径2: 文件名模式 ──
    try:
        fname = mp_item.GetClipProperty("File Name") or ""
        if _CAM_FNAME_RE.search(fname):
            return True
    except Exception:
        pass

    return False
