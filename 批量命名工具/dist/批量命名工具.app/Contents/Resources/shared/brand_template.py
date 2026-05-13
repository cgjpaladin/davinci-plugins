# -*- coding: utf-8 -*-
"""
brand_template.py — 新产品品牌配置模板
复制到产品目录，按注释修改即可。
"""

# ── 基本信息 ──
PRODUCT_NAME = "产品名"
WINDOW_TITLE = "窗口标题"
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
WIN_ID = "com.myjc.product_name"  # 每个产品用唯一 ID

# ── 处理参数 ──
CLIP_COLOR = "Orange"
OUTPUT_SUBDIR = "03_输出"   # 相对于 04_素材

# ── SMB 路径 ──
SMB_SCRIPT_DIR = "/Volumes/MYJC/06_Software/达芬奇脚本/产品名"

# ═══════════════════════════════════════════
# 以下无需改动（由 BasePipeline + shared/ 统一管理）
# ═══════════════════════════════════════════
# - Adapter 优先级：pricing_defaults.py → ADAPTER_PRIORITY
# - 日志输出：BasePipeline → StepLogger
# - 缓存/账单/调试：shared/ 模块自动处理
