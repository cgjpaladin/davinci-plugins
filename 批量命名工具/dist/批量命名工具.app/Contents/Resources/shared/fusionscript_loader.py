# -*- coding: utf-8 -*-
"""
fusionscript 加载器 — 通过 load_dynamic() 手动加载 .so，不依赖 PYTHONPATH。
所有模块统一 `from fusionscript_loader import bmd`，不直接 import DaVinciResolveScript。
"""
import importlib.machinery
import os
import sys


def _load_dynamic(module, path):
    loader = importlib.machinery.ExtensionFileLoader(module, path)
    return loader.load_module()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_FUSION_SO = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

bmd = _load_dynamic("fusionscript", _FUSION_SO)
