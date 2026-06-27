# -*- coding: utf-8 -*-
"""
pipeline_log.py — Pipeline 步骤日志器

每个 pipeline 步骤通过此模块输出结构化日志。
自动编号、统一格式、adapter 无关。

设计原则：
  - 自动编号：begin() 调用时自动递增，加步骤只需加 begin() 调用
  - 统一格式：所有产品、所有 adapter 看到的日志区输出完全一致
  - 分层输出：日志区只给用户关心的；SMB/CLI 保留完整数据
  - 步骤独立：每个步骤的日志逻辑集中在步骤代码中，不在 UI monkey-patch 里

使用示例：
    log = StepLogger(ui)
    log.begin("缓存复用")
    log.info("无可复用缓存")
    log.ok(f"缓存命中 {n} 个，直接替换")
    log.progress(1, 3, "EP02_g1_01.mp4", "处理中")
"""

import sys

from interface import PipelineUI


class StepLogger:
    """Pipeline 步骤日志器。

    注入到 BasePipeline 后，每个步骤通过此对象输出日志区内容。
    自动编号、统一格式。
    """

    # 圈号映射（Unicode ①②③...⑳），超出范围用 "(N)"
    _CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

    def __init__(self, ui: PipelineUI, start_at: int = 1):
        self.ui = ui
        self._step_num = start_at - 1
        self._first_section = True

    # ── 步骤生命周期 ──

    def skip(self, count: int = 1):
        """跳过编号（不输出标题）。UI 预扫描已由 scan_io() 单独展示 ①。"""
        self._step_num += count

    def begin(self, name: str, skip: bool = False):
        """开始一个步骤。自动编号 + 打印分割标题。
        
        skip=True 时显示「(跳过)」标记——用于全缓存路径，让用户知道跳过了什么。
        """
        if not self._first_section:
            self.ui.log_info("")
        self._first_section = False

        self._step_num += 1
        num = self._CIRCLED[self._step_num - 1] if self._step_num <= len(self._CIRCLED) else f"({self._step_num})"
        suffix = "（跳过）" if skip else ""
        self.ui.log_info(f"── {num} {name}{suffix} ──")

    @property
    def step_num(self) -> int:
        return self._step_num

    # ── 格式化输出 ──

    def info(self, msg: str):
        # PipelineUI 自行加前缀（CLI: 2空格，达芬奇：_ui_write不加）
        self.ui.log_info(msg)

    def ok(self, msg: str):
        self.ui.log_ok(msg)

    def fail(self, msg: str):
        self.ui.log_fail(msg)

    def warn(self, msg: str):
        self.ui.log_warn(msg)

    # ── 专用格式 ──

    def progress(self, idx: int, total: int, name: str, status: str = "处理中"):
        """片段处理进度。格式: → [1/3] name — 处理中"""
        width = len(str(total))
        self.info(f"→ [{idx:0{width}d}/{total}] {name} — {status}")

    def replace_result(self, idx: int, total: int, filename: str):
        """替换结果。格式: ✅ [1/3] name — 已替换"""
        width = len(str(total))
        self.ok(f"[{idx:0{width}d}/{total}] {filename} — 已替换")

    def cost_info(self, balance: float, points: int, yuan: float):
        """余额和费用信息。"""
        self.info(f"余额: {balance:.1f} 积分 | 预估: {points} 积分 (¥{yuan})")

    def cache_savings(self, count: int, yuan: float, secs: int):
        """缓存省钱统计。"""
        if yuan > 0.01:
            self.info(f"📦 缓存命中 {count} 个，直接替换")
            self.info(f"💰 省了约 ¥{yuan:.1f} ({secs}秒)")

    def scan_clip(self, name: str, tc: str, duration: float, cached: bool):
        """扫描结果 - 单个片段。"""
        label = "🟢可复用" if cached else "🟡需处理"
        self.info(f"{name} | 位置：{tc} | 长度：{duration:.0f}秒 | {label}")

    def scan_summary(self, total: int, need: int, io_info: str = None):
        """扫描结果汇总。"""
        if io_info:
            self.info(f"🎬 {io_info}: {total} 个片段，{need} 个需处理")
        else:
            self.info(f"🎬 扫描到 {total} 个片段")

    def adapter_message(self, msg: str):
        """适配器推送的关键消息（已提交/全部完成等）。adapter 无关。"""
        self.info(msg)

    def post_check_result(self, total: int, fail: int, problems: list = None):
        """校验结果。pass 不报，fail 才报。"""
        if fail > 0 and problems:
            self.warn(f"校验异常: {total - fail}/{total} 通过, {fail} 失败")
            for p in problems:
                self.warn(f"  ❌ {p['file']}: {', '.join(p['issues'])}")

    def completion_summary(self, success: int, total: int, total_secs: int, yuan: float):
        """最终完成摘要。0成功=失败，部分=部分完成，全部=成功。"""
        mins = total_secs // 60
        secs = total_secs % 60
        time_str = f"总耗时 {mins}分{secs}秒" if mins > 0 else f"耗时 {secs}秒"

        if success == 0 and total > 0:
            self.fail(f"处理失败: {total} 个片段全部失败  {time_str}")
        elif success < total:
            self.warn(f"⚠ 部分完成: {success}/{total} 个处理完成  {time_str}  ·  ¥{yuan:.2f}")
        elif success > 0:
            self.ok(f"🎉 处理完成: {success} 个处理完成  {time_str}  ·  ¥{yuan:.2f}")
        else:
            self.info(f"无任务  {time_str}")

    def oss_traffic(self, gb: float, cost: float):
        """OSS 流量统计（仅后端记录，不展示给用户）。"""
        pass  # OSS 数据已在 _report 和 ops_logger 中保存
