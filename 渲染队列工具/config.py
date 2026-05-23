# -*- coding: utf-8 -*-
"""渲染队列工具 — 配置."""

PRODUCT_NAME = "渲染队列工具"
BRAND_NAME = "达芬奇插件工坊"
__version__ = "0.0.6"
__channel__ = "dev"


def version_string():
    return f"{__version__}{'-' + __channel__ if __channel__ else ''}"
