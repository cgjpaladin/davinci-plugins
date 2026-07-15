# -*- coding: utf-8 -*-
"""
UI 抽象接口 — CLI 和 GUI 各自实现同一套方法。

目的：管道代码不关心输出目标是 print 还是达芬奇控件，
     只调用 interface.info() / interface.progress() 等。
     你可以在命令行测 90% 的逻辑，不用打开达芬奇。
"""


class PipelineUI:
    """管道输出接口。子类实现具体渲染方式。"""

    def log_info(self, msg: str):
        """普通信息"""
        raise NotImplementedError

    def log_ok(self, msg: str):
        """成功信息"""
        raise NotImplementedError

    def log_warn(self, msg: str):
        """警告信息"""
        raise NotImplementedError

    def log_fail(self, msg: str):
        """失败/错误信息"""
        raise NotImplementedError

    def set_progress(self, ratio: float):
        """更新进度条 0.0 ~ 1.0"""
        raise NotImplementedError

    def set_status(self, text: str):
        """更新状态栏文字"""
        raise NotImplementedError

    def confirm(self, question: str) -> bool:
        """用户确认。CLI 用 input，UI 弹对话框。"""
        raise NotImplementedError

    def notify(self, title: str, body: str):
        """系统通知。CLI 打印，UI 发 macOS 通知。"""
        raise NotImplementedError


# ── CLI 实现 ──

class CLIPipelineUI(PipelineUI):
    """文本输出实现（print到stdout）。用于自动化测试/远程SSH/调试。不是交互式CLI。"""

    def log_info(self, msg: str):
        print(f"  {msg}")

    def log_ok(self, msg: str):
        print(f"  ✅ {msg}")

    def log_warn(self, msg: str):
        print(f"  ⚠ {msg}")

    def log_fail(self, msg: str):
        print(f"  ❌ {msg}")

    def set_progress(self, ratio: float):
        pct = int(ratio * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)
        if ratio >= 1.0:
            print()

    def set_status(self, text: str):
        print(f"  [{text}]")

    def confirm(self, question: str) -> bool:
        answer = input(f"  {question} (y/N): ").strip().lower()
        return answer == "y"

    def notify(self, title: str, body: str):
        print(f"  📢 {title}: {body}")


# ── 达芬奇 UI 实现 ──

class DaVinciPipelineUI(PipelineUI):
    """输出到达芬奇控件（通过 ui_widgets 提供的 itm/_st/_pg 等）"""

    def __init__(self, itm, _st, _pg, dlg, _event_log):
        from ui_widgets import LOG_LB, ST_LB, PG_BAR
        self._itm = itm
        self._st = _st
        self._pg = _pg
        self._dlg = dlg
        self._event_log = _event_log
        self._LOG_LB = LOG_LB
        self._ST_LB = ST_LB
        self._PG_BAR = PG_BAR

    def set_phase(self, text: str):
        """更新进度阶段标签（ST_LB）"""
        self._st(text)

    def log_info(self, msg: str):
        from ui_widgets import _ui_write
        _ui_write(f"  {msg}")

    def log_ok(self, msg: str):
        from ui_widgets import _ui_write
        _ui_write(f"  ✅ {msg}")

    def log_warn(self, msg: str):
        from ui_widgets import _ui_write
        _ui_write(f"  ⚠ {msg}")

    def log_fail(self, msg: str):
        from ui_widgets import _ui_write
        _ui_write(f"  ❌ {msg}")

    def set_progress(self, ratio: float):
        self._pg(ratio)

    def set_status(self, text: str):
        self._st(text)

    def confirm(self, question: str) -> bool:
        from macos_utils import confirm
        return confirm(question)

    def notify(self, title: str, body: str):
        from macos_utils import notify
        notify(title, body)
