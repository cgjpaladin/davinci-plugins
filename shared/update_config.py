# -*- coding: utf-8 -*-
"""更新分发的统一配置。换仓库/用户名只改这一个文件。"""

# ── GitHub 仓库 ──
REPO_OWNER = "cgjpaladin"
REPO_NAME = "davinci-plugins"
REPO_FULL = f"{REPO_OWNER}/{REPO_NAME}"

# ── 版本检查多链路（按优先级） ──
VERSION_CHECK_URLS = [
    f"https://raw.githubusercontent.com/{REPO_FULL}/main/version.json",
    f"https://cdn.jsdelivr.net/gh/{REPO_FULL}@main/version.json",
    f"https://ghproxy.net/https://raw.githubusercontent.com/{REPO_FULL}/main/version.json",
    f"https://api.github.com/repos/{REPO_FULL}/releases/latest",
]

# ── 下载多链路 ──
UPDATE_FILE = "update_latest.zip"
DOWNLOAD_URLS = [
    f"https://cdn.jsdelivr.net/gh/{REPO_FULL}@main/update_latest.zip",
    f"https://ghproxy.net/https://raw.githubusercontent.com/{REPO_FULL}/main/update_latest.zip",
    f"https://raw.githubusercontent.com/{REPO_FULL}/main/update_latest.zip",
]

# ── 超时（秒） ──
TIMEOUT_VERSION_CHECK = 10      # 每条版本检查链路（国内 GitHub API 需更长）
TIMEOUT_DOWNLOAD_SINGLE = 1800  # 每条下载链路（128MB @ 77KB/s ≈ 28min）
TIMEOUT_INSTALL = 180          # osascript 安装（含用户输入密码时间）

# ── 下载校验 ──
MIN_DOWNLOAD_SIZE = 1000       # 小于此字节数的响应视为无效
