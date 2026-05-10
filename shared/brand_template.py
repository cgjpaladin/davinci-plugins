# -*- coding: utf-8 -*-
"""
brand.py — 产品品牌配置模板。每个产品在自身目录下创建 brand.py 覆写。
shared/ 代码通过 `import brand` 自动找到产品目录下的版本。
"""
# ── 基本信息 ──
PRODUCT_NAME = "产品名"
WINDOW_TITLE = "窗口标题"
FOOTER_TEXT = "底部文字"
__version__ = "0.1.0"

# ── UI 文案 ──
STEP1_TEXT = "① 请先选择项目路径"
STEP2_TEXT = "② 请选择筛选条件并扫描当前选区"
STEP3_TEXT = "③ 请点击开始处理"
BTN_CONFIRM_TEXT = "确认此路径"
BTN_PICK_TEXT = "选择项目路径"
BTN_SCAN_TEXT = "扫描当前选区"
BTN_START_TEXT = "开始处理"
BTN_STOP_TEXT = "停止"
BTN_UNDO_TEXT = "撤销替换"
PATH_PLACEHOLDER = "未指定项目路径"
WIN_ID = "com.myjc.ai_subtitle_ui"

# ── API 配置 ──
API_MODE = "pro_box"
CLIP_COLOR = "Orange"
API_PROVIDER = ""  # 由 adapters/preferred 自动选择
OUTPUT_MODE = "replace"      # replace | append
OUTPUT_SUBDIR = "03_去字幕"   # 相对于 04_素材

# ── 路径 ──
SMB_SCRIPT_DIR = "/Volumes/MYJC/06_Software/达芬奇脚本/产品名"

# ── Adapter 工厂 ──
def get_adapter():
    """返回适配器实例。每个产品实现自己的。"""
    raise NotImplementedError

def set_adapter_logger(log_fn):
    """设置适配器日志回调。"""
    pass
