"""
平台检测工具 — Apple Silicon / Intel Mac 路径自适应。

未来扩展：Linux 渲染节点、M5 Mac、不同 Homebrew 版本。
"""
import os


def ffprobe_path() -> str:
    """返回 ffprobe 可执行文件路径，优先级：Apple Silicon > Intel Mac > PATH fallback"""
    candidates = [
        "/opt/homebrew/bin/ffprobe",    # Apple Silicon
        "/usr/local/bin/ffprobe",       # Intel Mac
        "ffprobe",                       # PATH fallback
    ]
    for p in candidates:
        if p == "ffprobe" or os.path.exists(p):
            return p
    return "ffprobe"  # 最后的 fallback
