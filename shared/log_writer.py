#!/usr/bin/env python3
"""
log_writer.py — 统一文件日志系统（持久化，永不覆盖）

用法:
    from log_writer import get_logger
    log = get_logger("AI去字幕")
    log.ui("按钮点击")
    log.launcher("外部进程启动")
    log.ops({"action": "scan", "count": 3})
    log.smb("远程操作记录")

路径:
    ~/.workbuddy/logs/{产品名}/ui_{date}.log
    ~/.workbuddy/logs/{产品名}/launcher_{date}.log
    ~/.workbuddy/logs/{产品名}/ops_{date}.jsonl
    /Volumes/MYJC/.../日志/{产品名}/{hostname}_{date}.log  (SMB)
"""

import json, os, socket, threading
from datetime import datetime


class _DailyWriter:
    """天级日志文件写入器。文件名含日期，只追加不覆盖。"""

    def __init__(self, base_dir: str, suffix: str, product: str, fmt: str = "log"):
        """
        Args:
            base_dir: 日志根目录（如 ~/.workbuddy/logs/ 或 SMB 路径）
            suffix:   文件名后缀（如 ui / launcher / ops / {hostname}）
            product:  产品名
            fmt:      文件格式 "log" 或 "jsonl"
        """
        self._dir = os.path.join(base_dir, product)
        self._suffix = suffix
        self._fmt = fmt
        self._lock = threading.Lock()
        self._date = None
        self._path = None

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def write(self, msg: str):
        today = self._today()
        if today != self._date:
            self._date = today
            self._path = os.path.join(self._dir, f"{self._suffix}_{today}.{self._fmt}")
        os.makedirs(self._dir, exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                if self._fmt == "jsonl":
                    if isinstance(msg, dict):
                        msg["_ts"] = ts
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                else:
                    f.write(f"[{ts}] {msg}\n")

    def __call__(self, msg):
        """log.ui('msg') 快捷写法"""
        self.write(msg)

    @property
    def path(self) -> str:
        return self._path or os.path.join(self._dir, f"{self._suffix}_{self._today()}.{self._fmt}")


class LogWriter:
    """产品级日志写入器。"""

    def __init__(self, product: str):
        _local_root = os.path.join(os.path.expanduser("~"), ".workbuddy", "logs")
        _smb_root = "/Volumes/MYJC/06_Software/达芬奇脚本/日志"

        self.ui =       _DailyWriter(_local_root, "ui",       product, "log")
        self.launcher = _DailyWriter(_local_root, "launcher", product, "log")
        self.ops =      _DailyWriter(_local_root, "ops",      product, "jsonl")
        self.smb =      _DailyWriter(_smb_root,  socket.gethostname(), product, "log")

    def all_paths(self) -> list:
        """返回当前所有日志路径（用于 tools/logs.sh）。"""
        return [("本地-UI",       self.ui.path),
                ("本地-Launcher", self.launcher.path),
                ("本地-事件",     self.ops.path),
                ("SMB-远程",      self.smb.path)]


# ── 工厂 ──

def get_logger(product: str) -> LogWriter:
    return LogWriter(product)
