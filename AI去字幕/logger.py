"""
logger.py — 注入式日志系统
借鉴井水计划 PipelineLogger 模式。

用法：
  from logger import log, set_logger

  # 默认输出到 print（控制台模式）
  log.step("开始处理", "🚀")
  log.ok("3 个片段完成")
  log.warn("余额不足")
  log.fail("API 超时")

  # 静默模式（UI 不污染达芬奇控制台）
  set_logger(QuietLogger())

  # 自定义（UI 输出到界面文本框）
  class UILogger(Logger):
      def ok(self, msg): itm['log_lb'].Text += "✅ " + msg + "\n"
  set_logger(UILogger())
"""

from abc import ABC, abstractmethod


class Logger(ABC):
    """日志抽象基类。子类决定输出目标（print/文件/UI 文本框）。"""

    def step(self, msg: str, emoji: str = ""):
        """阶段标题"""
        if emoji:
            self._write(f"{emoji} {msg}")
        else:
            self._write(f"── {msg} ──")

    def ok(self, msg: str):
        self._write(f"  ✅ {msg}")

    def warn(self, msg: str):
        self._write(f"  ⚠ {msg}")

    def fail(self, msg: str):
        self._write(f"  ❌ {msg}")

    def info(self, msg: str):
        self._write(f"  {msg}")

    def title(self, msg: str):
        self._write("=" * 60)
        self._write(f"  {msg}")
        self._write("=" * 60)

    @abstractmethod
    def _write(self, msg: str):
        ...


class PrintLogger(Logger):
    """控制台日志器（默认）。"""
    def _write(self, msg: str):
        print(msg)


class QuietLogger(Logger):
    """静默日志器：只记不输出。"""
    def __init__(self):
        self.buffer = []

    def _write(self, msg: str):
        self.buffer.append(msg)


class UILogger(Logger):
    """UI 日志器：输出到回调函数（供 ui_external.py 使用）。"""

    def __init__(self, callback):
        """
        Args:
            callback: 单参数函数，接收日志字符串。如 lambda m: itm['log'].Text += m
        """
        self._cb = callback

    def _write(self, msg: str):
        self._cb(msg)


# ── 全局日志实例（默认 PrintLogger）──

_log: Logger = PrintLogger()


def set_logger(logger: Logger):
    """注入自定义日志器。"""
    global _log
    _log = logger


# ── 模块级便捷函数 ──

def step(msg: str, emoji: str = ""):
    _log.step(msg, emoji)


def ok(msg: str):
    _log.ok(msg)


def warn(msg: str):
    _log.warn(msg)


def fail(msg: str):
    _log.fail(msg)


def info(msg: str):
    _log.info(msg)


def title(msg: str):
    _log.title(msg)
