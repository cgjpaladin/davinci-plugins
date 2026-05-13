"""
环境变量加载 — 零依赖 .env 解析 + 多层加载策略。

从 config.py 抽离，保持纯函数无副作用（除了 os.environ）。
"""
import os


def load_dotenv(path: str):
    """手动解析 .env 文件（零依赖），加载到 os.environ。
    限制：不支持引号内等号（如 KEY="val=ue"），当前 .env 中无此类值。
    """
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


def load_all_env(plugin_dir: str, smb_env: str = ""):
    """按优先级加载全部 .env 文件（先加载的优先，后加载不覆盖已有 key）。

    加载顺序：
    1. {plugin_dir}/.env         — 本地
    2. {smb_env}                  — SMB 共享（可选，同路径时跳过）
    3. ~/.subtitle.env            — 个人备用
    4. ~/.watermark.env           — 旧名兼容
    """
    plugin_dir = os.path.abspath(plugin_dir)

    local_env = os.path.join(plugin_dir, ".env")

    load_dotenv(local_env)
    if smb_env and os.path.realpath(local_env) != os.path.realpath(smb_env):
        load_dotenv(smb_env)
    load_dotenv(os.path.expanduser("~/.subtitle.env"))
    load_dotenv(os.path.expanduser("~/.watermark.env"))
