# -*- coding: utf-8 -*-
"""
通过导出时间线 XML 获取 API 不直接暴露的属性。

来源技巧：filenameGenerator.py 张来吃 — 导出 XML 解析 ImageAspectRatio
"""

import tempfile
from xml.etree import ElementTree as ET


def get_aspect_ratio(timeline):
    """获取时间线的画幅比（ImageAspectRatio vs CanvasAspectRatio）。

    Args:
        timeline: DaVinci Resolve Timeline 对象

    Returns:
        dict 或 None:
          {"image": float, "canvas": float, "mismatch": bool}
          — mismatch=True 表示像素比 ≠ 画布比（变形宽银幕等）
    """
    tmp_file = None
    try:
        import fusionscript_loader
        dvr = fusionscript_loader.bmd
        tmp_file = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
        tmp_file.close()

        timeline.Export(tmp_file.name, dvr.EXPORT_DOLBY_VISION_VER_2_9)
        tree = ET.parse(tmp_file.name)
        root = tree.getroot()

        image = float(root.find("./Outputs/Output/ImageAspectRatio").text)
        canvas = float(root.find("./Outputs/Output/CanvasAspectRatio").text)

        return {
            "image": image,
            "canvas": canvas,
            "mismatch": image != canvas,
        }
    except Exception:
        # XML导出/解析/元素缺失/达芬奇导出失败 → 降级返回None
        return None
    finally:
        if tmp_file:
            import os
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass
