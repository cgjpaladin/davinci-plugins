"""
配置管理

集中管理所有 API 密钥、路径设置和适配器参数。
密钥通过环境变量或 .env 文件注入，不硬编码。

.env 文件位置（按加载顺序，先加载的优先，后加载不覆盖已有 key）：
  0. {PLUGIN_DIR}/.env          — 本地开发配置（仅开发机，优先于 SMB）
  1. {PLUGIN_DIR}/.env          — SMB 团队共享（生产机与上条同路径）
  2. ~/.subtitle.env            — 个人备用（SMB 断连时兜底，非覆盖）
  3. ~/.watermark.env           — 个人备用（旧名，兼容）

路径架构（生产模式）：
  {项目根}/04_素材/03_去字幕/
  ├── EP01/
  │   └── EP01_g1_01_v01_clean_ghostcut_probox_box_v01.mp4
  ├── .subtitle_state.json       # 片段状态
  ├── .ops_logs/                  # 操作日志
  └── .locks/                     # 并发锁
"""

import os
import subprocess
import time
import sys

# 确保 shared/ 模块可导入
_shared = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared')
if _shared not in sys.path:
    sys.path.insert(0, _shared)

from env import load_all_env

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
load_all_env(_PLUGIN_DIR, smb_env="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕/.env")

# 版本号 — 纯数字，不含后缀
__version__ = "1.11.3"
# 发布通道：""=稳定版, "dev"=开发版, 未来可扩展 "alpha"/"beta"/"rc1"
__channel__ = ""

# ── 品牌 ──
PRODUCT_NAME = "AI去字幕"
BRAND_NAME = "裁缝老师的达芬奇插件工坊 ✂️"

def version_string():
    """完整版本字符串，如 '1.8.0-dev' 或 '1.8.0'"""
    return f"{__version__}{'-' + __channel__ if __channel__ else ''}"

# ============================================================
# 调试模式
# ============================================================
# SUBTITLE_DEBUG=1 → 固定 09_Engineering 测试目录（仅开发用）
# 兼容: WATERMARK_DEBUG=1 仍然有效
def _env(key: str, fallback: str = ""):
    """读环境变量，新名优先，旧名兼容"""
    v = os.environ.get(f"SUBTITLE_{key}")
    if v is not None:
        return v
    return os.environ.get(f"WATERMARK_{key}", fallback)

DEBUG = _env("DEBUG") == "1"

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
RESOLVE_SCRIPTS_DIR = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊/"

# 插件自身路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# SMB 常量
# ============================================================
def _read_smb_mount():
    """从 deploy.json 读取 SMB 挂载点，不存在则用默认值。"""
    import json as _json
    cfg_path = os.path.expanduser("~/达芬奇插件工坊/deploy.json")
    try:
        with open(cfg_path) as f:
            return _json.load(f).get("smb_mount", "/Volumes/MYJC") or "/Volumes/MYJC"
    except Exception:
        return "/Volumes/MYJC"

SMB_MOUNT = _read_smb_mount()
SMB_SCRIPTS = os.path.join(SMB_MOUNT, "06_Software", "达芬奇脚本")
SMB_AI_SUBTITLE = os.path.join(SMB_SCRIPTS, "AI去字幕")
SMB_AI_PROJECT = os.path.join(SMB_MOUNT, "08_AI_Project")

# 日志路径（集中管理，避免散落在多个文件）
DEV_LOG_DIR = "/tmp/ai_subtitle_dev"                                  # dev 版本地日志目录

# ============================================================
# 调试模式固定路径（仅 SUBTITLE_DEBUG=1 时使用）
# ============================================================
DEBUG_MEDIA_DIR = os.path.join(SMB_MOUNT, "09_Engineering", "达芬奇AI测试")
DEBUG_SOURCE_DIR = os.path.join(DEBUG_MEDIA_DIR, "01_素材")
DEBUG_OUTPUT_DIR = os.path.join(DEBUG_MEDIA_DIR, "02_结果")

for _d in (DEBUG_SOURCE_DIR, DEBUG_OUTPUT_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass  # SMB 不可用或权限问题，非致命（调试模式路径不阻塞启动）

# ============================================================
# 项目路径动态识别
# ============================================================

# 手动指定项目根目录（UI 模式下由用户选择，或环境变量覆盖）
PROJECT_ROOT = _env("PROJECT")


def set_project_root(path: str):
    """显式设置项目根目录（UI 模式下用户选择后调用）。
    优先级高于 get_project_root() 的自动推导逻辑。
    """
    global PROJECT_ROOT
    PROJECT_ROOT = path

# 项目内固定子路径
PROJECT_MATERIALS = "04_素材"
PROJECT_VIDEOS = os.path.join(PROJECT_MATERIALS, "02_视频")
PROJECT_SUBTITLE = os.path.join(PROJECT_MATERIALS, "03_去字幕")


def get_project_root(clip_path: str = None) -> str:
    """
    获取项目根目录。
    优先级: SUBTITLE_PROJECT > 从素材路径自动推导 > 调试固定路径
    
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
    
    base = os.path.join(root, PROJECT_SUBTITLE)
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
API_TIMEOUT = 600
MAX_SOURCE_DURATION = 30  # 短剧片段通常 15-20 秒，30 秒足够覆盖
SCAN_ONLY = _env("SCAN_ONLY") == "1"

# ============================================================
# 额度保护
# ============================================================
# 定价集中管理在 pricing.py，换供应商只改那一行 ACTIVE_PROVIDER。

# 日志（生产模式用动态路径，这里给调试模式一个兜底）
_LOG_TS = time.strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(DEBUG_OUTPUT_DIR, f".subtitle_log_{_LOG_TS}.log")
# 操作日志路径 — 生产模式由 get_log_dir() 动态计算；调试模式用固定路径
OPS_LOG_DIR = os.path.join(DEBUG_MEDIA_DIR, ".ops_logs")

# ============================================================
# 处理模式
# ============================================================
DEFAULT_MODE = _env("MODE", "pro_box")  # pro_box

# 模式显示名（UI 和 Console 用）
MODE_LABELS = {"basic": "快速预览（测试用）", "pro_box": "正式出片"}

# 输出文件名标签（剪辑师看到的中文名，不含供应商）
MODE_FILE_TAGS = {"basic": "快速预览", "pro_box": "正式出片", "pro": "精修Pro"}


# 片段颜色过滤
CLIP_COLOR = _env("COLOR", "Orange")  # 裁缝老师用橘黄

# ============================================================
# 适配器注册表
# ============================================================
ADAPTER_CONFIGS = {
    "ghostcut": {
        "enabled": True,
        "app_key": GHOSTCUT_APP_KEY,
        "app_secret": GHOSTCUT_APP_SECRET,
        "model": DEFAULT_MODE,
        # "crf": 15,  # 取消注释启用高画质（默认17, 15≈视觉无损+）
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
        "sel_area_max_pixels": 480000,  # sel_area 面积上限（超过则降级 all_area）
        "portrait_cut_y": 0.50,         # 竖屏字幕区域起始比例（底部50%一刀切）
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
