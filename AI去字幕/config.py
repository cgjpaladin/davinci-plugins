"""
配置管理

集中管理所有 API 密钥、路径设置和适配器参数。
配置文件位置：与插件脚本同目录的 config.py

路径架构（生产模式）：
  {项目根}/04_素材/03_去水印/
  ├── EP01/
  │   └── EP01_g1_01_v01_clean_ghostcut_probox_box_v01.mp4
  ├── .watermark_state.json       # 片段状态
  ├── .ops_logs/                  # 操作日志
  └── .locks/                     # 并发锁
"""

import os
import time

# 全局版本号 — 所有模块引用这一个变量
__version__ = "0.5"

# ============================================================
# 调试模式
# ============================================================
# WATERMARK_DEBUG=1 → 固定 09_Engineering 测试目录（仅开发用）
DEBUG = os.environ.get("WATERMARK_DEBUG", "") == "1"

# ============================================================
# API 密钥
# ============================================================
GHOSTCUT_APP_KEY = os.environ.get("GHOSTCUT_APP_KEY", "4fec8e3a2bf949d0b478b4ca5f4159b4")
GHOSTCUT_APP_SECRET = os.environ.get("GHOSTCUT_APP_SECRET", "828b2c80bd3b46999b38b719d16c86ab")

WUHENAI_API_KEY = os.environ.get("WUHENAI_API_KEY", "")
CLIPFLOW_API_KEY = os.environ.get("CLIPFLOW_API_KEY", WUHENAI_API_KEY)  # Clipflow = 无痕AI = 岁羽网络
VOLCENGINE_ACCESS_KEY = os.environ.get("VOLCENGINE_ACCESS_KEY", "AKLTOTNmZDc4NDZiZDgwNDY5ODllNDhjZjNjMTgxMDRjNWI")
VOLCENGINE_SECRET_KEY = os.environ.get("VOLCENGINE_SECRET_KEY", "Tm1ZeE1EWmlOelprTlRFM05HTm1aRGxtWlRWaU1EZGhaamRsWVdFNE9Uaw==")
TENCENT_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
ALIYUN_ACCESS_KEY = os.environ.get("ALIYUN_ACCESS_KEY", "")
ALIYUN_SECRET_KEY = os.environ.get("ALIYUN_SECRET_KEY", "")

# ============================================================
# 达芬奇路径
# ============================================================
RESOLVE_SCRIPT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
RESOLVE_SCRIPT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
RESOLVE_SCRIPTS_DIR = os.path.expanduser(
    "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/"
)

# 插件自身路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# SMB 常量
# ============================================================
SMB_MOUNT = "/Volumes/MYJC"

# ============================================================
# 调试模式固定路径（仅 WATERMARK_DEBUG=1 时使用）
# ============================================================
DEBUG_MEDIA_DIR = os.path.join(SMB_MOUNT, "09_Engineering", "达芬奇去水印测试")
DEBUG_SOURCE_DIR = os.path.join(DEBUG_MEDIA_DIR, "01_素材")
DEBUG_OUTPUT_DIR = os.path.join(DEBUG_MEDIA_DIR, "02_结果")

for _d in (DEBUG_SOURCE_DIR, DEBUG_OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

# ============================================================
# 项目路径动态识别
# ============================================================

# 手动指定项目根目录（UI 模式下由用户选择，或环境变量覆盖）
PROJECT_ROOT = os.environ.get("WATERMARK_PROJECT", "")

# 项目内固定子路径
PROJECT_MATERIALS = "04_素材"
PROJECT_VIDEOS = os.path.join(PROJECT_MATERIALS, "02_视频")
PROJECT_WATERMARK = os.path.join(PROJECT_MATERIALS, "03_去字幕")


def get_project_root(clip_path: str = None) -> str:
    """
    获取项目根目录。
    优先级: WATERMARK_PROJECT > 从素材路径自动推导 > 调试固定路径
    
    自动推导: 从 /Volumes/MYJC/XX_.../项目名/04_素材/02_视频/...
              向上找到 04_素材 的父目录 = 项目根
    """
    if PROJECT_ROOT and os.path.isdir(PROJECT_ROOT):
        return PROJECT_ROOT
    
    if DEBUG:
        return DEBUG_MEDIA_DIR
    
    if clip_path and os.path.exists(clip_path):
        p = os.path.abspath(clip_path)
        # 往上找，直到遇到 04_素材 或 01_素材 目录
        while p and p != "/" and p != SMB_MOUNT:
            parent = os.path.dirname(p)
            if os.path.basename(p) == PROJECT_MATERIALS:
                return parent  # parent 是 04_素材 的父目录 = 项目根
            p = parent
    
    return ""


def get_output_dir(project_root: str = None, ep: str = None) -> str:
    """
    获取去水印输出目录。
    生产: {项目根}/04_素材/03_去水印/EP{XX}/
    调试: {DEBUG_OUTPUT_DIR}/
    """
    if DEBUG:
        return DEBUG_OUTPUT_DIR
    
    root = project_root or get_project_root()
    if not root:
        raise RuntimeError("无法确定项目根目录，请先选择项目文件夹")
    
    base = os.path.join(root, PROJECT_WATERMARK)
    if ep:
        base = os.path.join(base, ep)  # EP 编号来自正则，自动适配任意位数
    os.makedirs(base, exist_ok=True)
    return base


def get_state_dir(project_root: str = None) -> str:
    """状态文件和锁文件所在目录：{项目根}/04_素材/03_去水印/"""
    return get_output_dir(project_root)


def get_log_dir(project_root: str = None) -> str:
    """操作日志目录：{项目根}/04_素材/03_去水印/.ops_logs/"""
    out = get_output_dir(project_root)
    d = os.path.join(out, ".ops_logs")
    os.makedirs(d, exist_ok=True)
    # macOS 隐藏
    os.system(f'chflags hidden "{d}" 2>/dev/null')
    return d


def get_lock_dir(project_root: str = None) -> str:
    """并发锁目录：{项目根}/04_素材/03_去水印/.locks/"""
    out = get_output_dir(project_root)
    d = os.path.join(out, ".locks")
    os.makedirs(d, exist_ok=True)
    return d


# ============================================================
# 输出设置
# ============================================================
TEMP_DIR = os.path.join(PLUGIN_DIR, "temp")
EXPORT_FORMAT = "QuickTime"
EXPORT_CODEC = "ProRes 422 HQ"
COLOR_SPACE = "Rec.709"
API_TIMEOUT = 600
MAX_SOURCE_DURATION = 30  # 短剧片段通常 15-20 秒，30 秒足够覆盖
MAX_CONCURRENT = int(os.environ.get("WATERMARK_CONCURRENT", "5"))
SCAN_ONLY = os.environ.get("WATERMARK_SCAN_ONLY", "") == "1"
MAX_CONCURRENT = int(os.environ.get("WATERMARK_CONCURRENT", "5"))

# ============================================================
# 额度保护
# ============================================================
COST_PER_MODE = {
    "basic": 1,
    "lite": 2,
    "pro": 10,
    "pro_box": 5,
}
MIN_BALANCE = 0
NO_CONFIRM = os.environ.get("WATERMARK_NO_CONFIRM", "") == "1"

# 日志（生产模式用动态路径，这里给调试模式一个兜底）
_LOG_TS = time.strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(DEBUG_OUTPUT_DIR, f".watermark_log_{_LOG_TS}.log")
# 操作日志路径 — 生产模式由 get_log_dir() 动态计算；调试模式用固定路径
OPS_LOG_DIR = os.path.join(DEBUG_MEDIA_DIR, ".ops_logs")

# ============================================================
# 处理模式
# ============================================================
DEFAULT_MODE = os.environ.get("WATERMARK_MODE", "pro_box")  # basic / pro_box

# 模式显示名（UI 和 Console 用）
MODE_LABELS = {"basic": "快速预览", "pro_box": "正式出片"}

# 输出文件名标签（剪辑师看到的中文名，不含供应商）
MODE_FILE_TAGS = {"basic": "快速预览", "pro_box": "正式出片", "lite": "精修Lite", "pro": "精修Pro"}

# Seedance 字幕遮罩区域
DEFAULT_MASK_REGION = [[0, 0.62], [1, 0.62], [1, 0.88], [0, 0.88]]

# 片段颜色过滤
CLIP_COLOR = os.environ.get("WATERMARK_COLOR", "Orange")  # 裁缝老师用橘黄

# ============================================================
# 适配器注册表
# ============================================================
ADAPTER_CONFIGS = {
    "ghostcut": {
        "enabled": True,
        "app_key": GHOSTCUT_APP_KEY,
        "app_secret": GHOSTCUT_APP_SECRET,
        "model": DEFAULT_MODE,
    },
    "clipflow": {
        "enabled": False,
        "api_key": CLIPFLOW_API_KEY,
        "algorithm": 1,  # 1=无痕模式, 0=极速模式
    },
    "volcengine": {
        "enabled": False,
        "access_key": VOLCENGINE_ACCESS_KEY,
        "secret_key": VOLCENGINE_SECRET_KEY,
    },
    "tencent": {
        "enabled": False,
        "secret_id": TENCENT_SECRET_ID,
        "secret_key": TENCENT_SECRET_KEY,
    },
    "aliyun": {
        "enabled": False,
        "access_key": ALIYUN_ACCESS_KEY,
        "secret_key": ALIYUN_SECRET_KEY,
    },
}
