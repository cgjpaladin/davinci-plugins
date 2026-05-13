"""
macOS 系统工具 — osascript 调用集中管理。

用途：SMB 挂载、文件夹选择、系统通知、确认弹窗。
"""
import subprocess


def mount_smb(server: str = "192.168.1.154",
              share: str = "MYJC",
              timeout: int = 10) -> bool:
    """挂载 SMB 共享卷。返回 True=成功或已挂载。"""
    try:
        subprocess.run(
            ["osascript", "-e", f'mount volume "smb://{server}/{share}"'],
            timeout=timeout, capture_output=True
        )
        import time
        time.sleep(2)
        import os
        return os.path.exists("/Volumes/MYJC")
    except Exception:
        return False


def pick_folder(title: str = "选择文件夹",
                default_dir: str = "",
                timeout: int = 60) -> str:
    """弹出 macOS 文件夹选择对话框，返回路径（取消时返回 ""）。"""
    try:
        if default_dir:
            cmd = f'POSIX path of (choose folder with prompt "{title}" default location "{default_dir}")'
        else:
            cmd = f'POSIX path of (choose folder with prompt "{title}")'
        r = subprocess.run(
            ['osascript', '-e', cmd],
            capture_output=True, encoding="utf-8", timeout=timeout
        )
        path = r.stdout.strip()
        import os
        return path if path and os.path.isdir(path) else ""
    except Exception:
        return ""


def notify(title: str, body: str, timeout: int = 5):
    """发送 macOS 系统通知（非关键路径，失败静默）。"""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{body}" with title "{title}"'],
            timeout=timeout, capture_output=True
        )
    except Exception:
        pass


def confirm(question: str, timeout: int = 30) -> bool:
    """弹出 macOS 确认对话框。取消/失败返回 False。"""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             f'display dialog "{question}" buttons {{"取消", "确认"}} default button "确认"'],
            capture_output=True, text=True, timeout=timeout
        )
        return "确认" in r.stdout
    except Exception:
        return True  # 失败时默认通过，不阻塞（非关键路径）
