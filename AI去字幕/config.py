"""
配置管理

集中管理所有 API 密钥、路径设置和适配器参数。
密钥通过环境变量或 .env 文件注入，不硬编码。

.env 文件位置（按优先级）：
  1. {PLUGIN_DIR}/.env          — 部署在 SMB，团队共享
  2. ~/.watermark.env           — 个人覆盖

路径架构（生产模式）：
  {项目根}/04_素材/03_去字幕/
  ├── EP01/
  │   └── EP01_g1_01_v01_clean_ghostcut_probox_box_v01.mp4
  ├── .watermark_state.json       # 片段状态
  ├── .ops_logs/                  # 操作日志
  └── .locks/                     # 并发锁
"""

import os
import subprocess
import time

# 全局版本号 — 所有模块引用这一个变量
__version__ = "0.7.2"

# ============================================================
# .env 加载（优先 SMB 共享，其次个人）
# ============================================================
def _load_dotenv(path: str):
    """手动解析 .env 文件（零依赖），加载到 os.environ"""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception:
        pass

# 加载顺序：本地优先 → SMB 共享 → 个人覆盖（三层兜底，SMB 断了也能跑）
_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
_load_dotenv("/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕/.env")
_load_dotenv(os.path.expanduser("~/.watermark.env"))

# ============================================================
# 调试模式
# ============================================================
# WATERMARK_DEBUG=1 → 固定 09_Engineering 测试目录（仅开发用）
DEBUG = os.environ.get("WATERMARK_DEBUG", "") == "1"

# ============================================================
# API 密钥 — 通过环境变量或 .env 注入，不设硬编码默认值
# ============================================================
GHOSTCUT_APP_KEY = os.environ.get("GHOSTCUT_APP_KEY", "")
GHOSTCUT_APP_SECRET = os.environ.get("GHOSTCUT_APP_SECRET", "")

WUHENAI_API_KEY = os.environ.get("WUHENAI_API_KEY", "")
WUHENAI_V2_API_KEY = os.environ.get("WUHENAI_V2_API_KEY", "")

OSS_ACCESS_KEY_ID = os.environ.get("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.environ.get("OSS_ACCESS_KEY_SECRET", "")
OSS_BUCKET = os.environ.get("OSS_BUCKET", "wuhenai-clipflow")
OSS_REGION = os.environ.get("OSS_REGION", "cn-hangzhou")
VOLCENGINE_ACCESS_KEY = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
VOLCENGINE_SECRET_KEY = os.environ.get("VOLCENGINE_SECRET_KEY", "")
TENCENT_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
ALIYUN_ACCESS_KEY = os.environ.get("ALIYUN_ACCESS_KEY", "")
ALIYUN_SECRET_KEY = os.environ.get("ALIYUN_SECRET_KEY", "")

# ============================================================
# 工具函数
# ============================================================

def hide_path(path: str):
    """macOS 隐藏文件/目录（SMB 兼容）。所有模块统一用这个。"""
    if not os.path.exists(path):
        return
    try:
        subprocess.run(["chflags", "hidden", path], capture_output=True)
    except Exception:
        pass


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
DEBUG_MEDIA_DIR = os.path.join(SMB_MOUNT, "09_Engineering", "达芬奇AI测试")
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
    获取去字幕输出目录。
    生产: {项目根}/04_素材/03_去字幕/EP{XX}/
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
    """状态文件和锁文件所在目录：{项目根}/04_素材/03_去字幕/"""
    return get_output_dir(project_root)


def get_log_dir(project_root: str = None) -> str:
    """操作日志目录：{项目根}/04_素材/03_去字幕/.ops_logs/"""
    out = get_output_dir(project_root)
    d = os.path.join(out, ".ops_logs")
    os.makedirs(d, exist_ok=True)
    hide_path(d)
    return d


def get_lock_dir(project_root: str = None) -> str:
    """并发锁目录：{项目根}/04_素材/03_去字幕/.locks/"""
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

# ============================================================
# 额度保护
# ============================================================
# 定价集中管理在 pricing.py，换供应商只改那一行 ACTIVE_PROVIDER。

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

# Seedance 字幕遮罩区域（底部23%，适配无痕AI 480000px rect限制）
DEFAULT_MASK_REGION = [[0, 0.77], [1, 0.77], [1, 1.0], [0, 1.0]]

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
    "wuhenai_v21": {
        "enabled": True,
        "api_key": WUHENAI_V2_API_KEY,
        "oss_access_key_id": OSS_ACCESS_KEY_ID,
        "oss_access_key_secret": OSS_ACCESS_KEY_SECRET,
        "oss_bucket": OSS_BUCKET,
        "oss_region": OSS_REGION,
        "model": "video_removal_std",
        "method": "sel_area",  # Seedance 字幕固定底部，sel_area 省33%积分
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
