# -*- coding: utf-8 -*-
"""
pipeline_base.py — AI 处理类产品基类

所有 AI 处理产品（去字幕/换口型/语音克隆/降噪/超分）共用此基类。
子类只需实现 3 个抽象方法（_scan / _prepare / _submit），其余步骤继承。

设计原则：
- 模板方法模式：run() 定义标准流程，子类覆盖可变步骤
- 所有输出通过 PipelineUI 接口，不直接 print/控件
- 钩子（before_submit / restore_colors / stop_check / on_progress）解决 CLI/UI 差异
- 产品独立部署：每个产品有独立 pipeline.py，共享此基类

使用示例（AI去字幕）：
    class SubtitlePipeline(BasePipeline):
        PRODUCT_NAME = "AI 去字幕"
        def _scan(self): ...
        def _prepare(self, clips, mode): ...
        def _submit(self, tasks, batch): ...

    pipeline = SubtitlePipeline()
    pipeline.run(ui, project_root, mode, clips=..., stop_check=...)
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Optional, NamedTuple, Callable, Any

from interface import PipelineUI, CLIPipelineUI
from pricing import estimate_cost, point_to_yuan, oss_tracker
from pipeline_utils import validate_task, calc_cache_savings
from pipeline_log import StepLogger
import ops_logger


# ═══════════════════════════════════════════
# 标准化结果类型（替换 CLI 5元组 / UI 9元组）
# ═══════════════════════════════════════════

class ResultItem(NamedTuple):
    """统一的 API 处理结果条目。CLI 填前 5 个字段，UI 填全部 9 个。"""
    mp_item: object           # MediaPoolItem
    name: str                 # 片段名
    path: str                 # 磁盘路径
    result: object            # SubtitleResult
    elapsed: float            # 处理耗时（秒）
    tl_item: object = None    # TimelineItem（颜色恢复用）
    tl_color: str = ""        # TimelineItem 原始颜色
    mp_color: str = ""        # MediaPoolItem 原始颜色
    alt_tl_items: tuple = ()  # ((TimelineItem, color), ...) 同文件其他片段


# ═══════════════════════════════════════════
# BasePipeline
# ═══════════════════════════════════════════

class BasePipeline(ABC):
    """AI 处理类产品基类。

    子类 MUST 实现: _scan() / _prepare() / _submit()
    子类 MAY 覆盖: _check_env() / _preflight() / _before_submit() / 钩子方法
    """

    # ── 产品常量（子类覆写）──
    PRODUCT_NAME: str = "AI 处理"
    SECTION_AI_PROCESSING: str = "AI 处理中"  # 子类可改为 "AI去字幕中" / "AI换口型中"

    # ── 特性开关（子类可覆写以按需关闭）──
    # True=启用，False=跳过该步骤。未来可按客户/版本差异化。
    FEATURES = {
        "balance_check": True,         # 余额查询 + 不足拦截 + 二次校验
        "post_check": True,            # 输出文件完整性校验
        "oss_tracking": True,          # OSS 流量统计
        "phase_timing": True,          # 阶段耗时日志
        "ops_logging": True,           # 运营日志（session_start/end）
    }

    def __init_subclass__(cls, **kwargs):
        """模块加载时自动校验子类完整性（参考交付自检 _validate_field_map 模式）。

        校验时机: import 时（早于实例化），错误在开发阶段立刻暴露。
        """
        super().__init_subclass__(**kwargs)

        # 跳过基类自身
        if cls.__name__ == "BasePipeline":
            return

        errors = []

        # 1. PRODUCT_NAME 必须覆写
        if cls.PRODUCT_NAME == "AI 处理":
            errors.append(f"PRODUCT_NAME 未覆写（仍是默认值 {cls.PRODUCT_NAME!r}）")

        # 2. 抽象方法必须覆写（Python ABC 在实例化时也会检查，这里是双重保障 + 更早暴露）
        for method_name in ("_scan", "_prepare", "_submit"):
            child_method = getattr(cls, method_name, None)
            base_method = getattr(BasePipeline, method_name, None)
            if child_method is base_method:
                errors.append(f"抽象方法 {method_name}() 未覆写")

        if errors:
            msg = f"{cls.__name__} 校验失败:\n  " + "\n  ".join(errors)
            raise TypeError(msg)

    def __init__(self):
        self.ui: PipelineUI = None
        self.log: StepLogger = None
        self._project_root: str = ""
        self._mode: str = ""
        self._output_dir: str = ""
        self._force: bool = False
        self._report: dict = {}
        self._resolve = None
        self._project = None
        self._timeline = None
        # 时间戳（阶段耗时统计）
        self._t_start: float = 0
        self._t_prep_end: float = 0

    # ═══════════════════════════════════════
    # 模板方法
    # ═══════════════════════════════════════

    def run(self,
            ui: PipelineUI,
            project_root: str,
            mode: str,
            clips: Optional[list] = None,
            dry_run: bool = False,
            force: bool = False,
            batch: bool = True,
            scan_only: bool = False,
            report_json: str = "",
            adapter=None,
            **hooks) -> dict:
        """执行完整 AI 处理流水线。"""
        self._init_state(ui, project_root, mode, force, hooks)
        oss_tracker.reset()

        # ── 0. 环境自检 ──
        self._check_env()
        self._preflight()
        if self._report.get("error"):
            return self._report

        # ── 1. 连接达芬奇 ──
        if not self._connect_resolve():
            return self._report

        # ── 2. 扫描 ──
        if clips is None:
            clips = self._scan()
        else:
            self.log.skip()  # UI 预扫描已展示 ①，pipeline 从 ② 开始
        self._show_scan_summary(clips)
        if scan_only or not clips:
            return self._report

        # ── 3. 初始化项目状态 ──
        self._init_project_state()

        # ── 4. 复用缓存 ──
        self.log.begin("复用缓存")
        tasks, all_cache = self._do_prepare(clips, mode)
        if all_cache:
            self.log.skip(2)  # 跳过 ③AI处理、④替换，直接到 ⑤最终报告
            self.log.begin("最终报告")
            self._all_cache_report()
            return self._report

        # ── 5. Dry-run ──
        if dry_run:
            self._handle_dry_run(tasks)
            return self._report

        # ── 6. AI 处理 ──
        self.log.begin(self.SECTION_AI_PROCESSING)

        if not self._check_balance(tasks, mode):
            return self._report

        tasks = self._validate_tasks(tasks)

        tasks = self._before_submit(tasks)
        if self._get_stop_check()() or not tasks:
            return self._report

        results = self._submit(tasks, batch)
        self._t_prep_end = time.time()

        if not results:
            return self._report

        self.log.info("下载中...")

        # ── 替换回时间线 ──
        output_files = self._download_apply(results)
        self.log.begin("替换回时间线")

        # ── 校验输出 ──
        self._show_replace_summary(output_files, len(results))
        self._do_post_check(output_files)

        # ── 最终报告 ──
        self.log.begin("最终报告")
        self._final_report(results, output_files)

        if report_json:
            self._write_report_json(report_json)

        return self._report

    # ═══════════════════════════════════════
    # 内部初始化
    # ═══════════════════════════════════════

    def _init_state(self, ui, project_root, mode, force, hooks):
        self.ui = ui
        self.log = StepLogger(ui)
        self._project_root = project_root
        self._mode = mode
        self._force = force
        self._hooks = hooks
        self._t_start = time.time()
        self._report = {"version": "", "mode": mode, "dry_run": False}

    def _init_project_state(self):
        """初始化项目级别的状态/日志/账本。子类可覆盖以使用不同模块。"""
        from subtitle_state import init as state_init
        import ledger
        state_init(self._project_root)
        ledger.init(self._project_root)
        from config import get_log_dir
        ops_logger.init(get_log_dir(self._project_root))
        ops_logger.session_start(
            self._project.GetName() if self._project else "",
            self._timeline.GetName() if self._timeline else "",
            self._mode, 0,
        )

    # ═══════════════════════════════════════
    # 通用步骤（基类实现）
    # ═══════════════════════════════════════

    def _connect_resolve(self) -> bool:
        """连接达芬奇 + 获取项目/时间线信息。失败则填充 report 并返回 False。"""
        try:
            from core import connect_resolve
            self._resolve, self._project, self._timeline = connect_resolve()
            self._report["resolve"] = self._resolve.GetVersionString()
            self._report["project"] = self._project.GetName()
            self._report["timeline"] = self._timeline.GetName()
            self._log_action(f"已连接: {self._report['resolve']} / {self._report['project']} / {self._report['timeline']}")
            self.ui.set_progress(0.10)
            return True
        except Exception as e:
            self._report["error"] = str(e)
            self.ui.log_fail(f"连接达芬奇失败: {e}")
            return False

    @staticmethod
    def _parse_balance(bal: dict) -> float:
        """解析余额：兼容 wuhenai {"balance": N} 和 ghostcut {"pointAssets": [...]}"""
        if "balance" in bal:
            return float(bal["balance"])
        return sum(
            a["pointBalance"] for a in bal.get("pointAssets", [])
            if a["pointBalance"] > 0
        )

    def _check_balance(self, tasks: list, mode: str) -> bool:
        """余额查询 + 不足拦截 + 二次校验。通过返回 True，失败填充 report 返回 False。"""
        if not self.FEATURES.get("balance_check", True):
            return True

        adapter = self._get_adapter()
        if not adapter:
            return True  # 无适配器 → 跳过余额检查

        # 统一日志回调：所有 adapter 输出通过此回调分发（不泄漏到 UI 日志区）
        self._wire_adapter_logger(adapter)

        _, total_est, _, yuan = estimate_cost(tasks, mode)
        self._report["cost"] = {"points": total_est, "yuan": yuan}

        # 首次余额查询
        try:
            bal = adapter.get_balance()
            pts = self._parse_balance(bal)
        except Exception:
            self.log.warn("余额查询失败，跳过保护")
            self._report["balance"] = 0
            return True

        self._report["balance"] = round(pts, 1)
        # 余额仅后端记录，不推日志区（用户已在面板手动刷新过）

        if pts > 0 and pts < total_est:
            self.log.fail(f"余额不足: {pts:.1f} < {total_est}")
            self._report["error"] = "余额不足"
            ops_logger.balance_check(pts, total_est, "blocked")
            return False

        ops_logger.balance_check(pts, total_est, "proceed")

        # 二次余额校验（防多机器超支）
        try:
            bal2 = adapter.get_balance()
            pts_now = self._parse_balance(bal2)
            if pts_now < total_est:
                self.log.fail(f"余额不足: 当前{pts_now} < 需要{total_est}（可能被其他机器消费）")
                self._report["error"] = "余额不足（二次校验）"
                return False
        except Exception:
            pass  # 网络波动，不阻塞

        return True

    def _validate_tasks(self, tasks: list) -> list:
        """过滤无效任务（文件大小/时长校验）。"""
        valid = []
        for t in tasks:
            ok_flag, err = validate_task(t)
            if ok_flag:
                valid.append(t)
            else:
                self.log.warn(f"⚠ {t.name}: {err}，跳过")
        return valid

    def _handle_dry_run(self, tasks: list):
        """Dry-run 模式：列出任务但不调 API。"""
        self.ui.set_status("Dry-run 完成")
        self.log.info(f"🔍 Dry-run — 共 {len(tasks)} 个片段，未调 API")
        for i, t in enumerate(tasks, 1):
            self.log.info(f"  {i}. {t.name} ({t.path})")
        self._report["dry_run_completed"] = True

    def _download_apply(self, results: list) -> list:
        """下载 + ReplaceClip + 颜色恢复。self-contained：日志进度在内部管理。"""
        from core import download_and_apply

        total = len(results)
        self.ui.set_progress(0.65)

        # 逐文件进度（进日志区，不只是状态栏）
        downloaded = [0]  # 闭包捕获

        def _on_start(name: str):
            downloaded[0] += 1
            self.ui.set_status(f"下载中... {name}")
            self.log.info(f"下载中... ({downloaded[0]}/{total}) {name}")

        def _on_done(ep, subdir, name):
            self.log.ok(f"已下载 ({downloaded[0]}/{total}) {name}")

        def _on_fail(name, err):
            self.log.fail(f"下载失败: {name} — {err}")

        success_count, fail_list, output_files = download_and_apply(
            results, self._output_dir, self._mode,
            check_stop=self._get_stop_check(),
            provider=getattr(self, '_cached_pricing_key', '') or 'wuhenai',
            on_start=_on_start,
            on_done=_on_done,
            on_fail=_on_fail,
        )

        self._report["results"] = {
            "total": total, "success": success_count,
            "failed": total - success_count, "fail_details": fail_list,
            "output_files": output_files,
        }
        return output_files

    def _all_cache_report(self):
        """全部缓存完成时的简化报告。"""
        cache_hits = self._report.get("cache_hits", 0)
        elapsed = int(time.time() - self._t_start)
        self.log.ok(f"🎉 全部完成！（{cache_hits}个缓存命中）  耗时 {elapsed} 秒")
        self.ui.set_progress(1.0)
        self.ui.set_status("完成（缓存）")
        self.ui.notify(self.PRODUCT_NAME, f"全部由缓存完成（{cache_hits}个片段）")
        self.ui.log_info("")  # 章节尾部空行

    def _do_post_check(self, output_files: list):
        """校验输出文件完整性。"""
        if not self.FEATURES.get("post_check", True):
            return
        from core import post_check

        self.ui.set_status("校验输出...")
        pc = post_check(output_files)
        self.log.post_check_result(pc["total"], pc["fail"], pc.get("problems"))

    def _final_report(self, results: list, output_files: list):
        """最终报告：阶段耗时 + OSS 统计 + 运营日志 + 通知。"""
        t_done = time.time()
        total_success = self._report.get("results", {}).get("success", 0)
        total_all = len(results)

        # 阶段耗时
        t_api = round(self._t_prep_end - self._t_start, 1)
        t_dl = round(t_done - self._t_prep_end, 1)
        self._report["phase_timing"] = {
            "api_secs": t_api,
            "download_secs": t_dl,
            "total_processing_secs": round(t_done - self._t_start, 1),
        }

        # OSS 统计
        if self.FEATURES.get("oss_tracking", True):
            oss_cost = oss_tracker.snapshot()
            self._report["oss_cost"] = oss_cost
            self.log.oss_traffic(oss_cost.get("traffic_gb", 0), oss_cost.get("total_cost", 0))
            oss_tracker.reset()

        # 完成通知
        yuan = self._report.get("cost", {}).get("yuan", 0)
        self.log.completion_summary(total_success, total_all, int(t_done - self._t_start), yuan)
        self.ui.set_progress(1.0)
        self.ui.set_status("完成")
        self.ui.notify(self.PRODUCT_NAME, f"{total_success}个片段处理完成")
        self.ui.log_info("")  # 章节尾部空行

        # 运营日志
        if self.FEATURES.get("ops_logging", True):
            fail_count = total_all - total_success
            pts_before = self._report.get("balance", 0)
            total_est = self._report.get("cost", {}).get("points", 0)
            total_proc = t_done - self._t_start
            ops_logger.session_end(total_success, fail_count, total_all, pts_before, total_est, int(total_proc), yuan)

    # ═══════════════════════════════════════
    # 抽象方法（子类 MUST 实现）
    # ═══════════════════════════════════════

    @abstractmethod
    def _scan(self) -> list:
        """扫描时间线，返回片段列表。"""
        ...

    @abstractmethod
    def _prepare(self, clips: list, mode: str) -> tuple:
        """准备任务。返回 (tasks: list, cache_hits: int, cache_hit_names: list)。"""
        ...

    @abstractmethod
    def _submit(self, tasks: list, batch: bool) -> list:
        """提交 API 处理。返回 [ResultItem, ...] 列表。"""
        ...

    # ═══════════════════════════════════════
    # 钩子（子类按需覆盖）
    # ═══════════════════════════════════════

    def _get_adapter(self):
        """获取适配器实例。子类必须覆盖。"""
        return None

    def _check_env(self):
        """环境自检（SMB/API/OSS/DVR）。CLI 覆盖，UI 跳过。"""
        pass

    def _preflight(self):
        """API/OSS 探活。子类可覆盖。"""
        pass

    def _show_scan_summary(self, clips: list):
        """展示扫描结果。子类可覆盖以自定义格式。"""
        if clips:
            self.ui.log_info(f"🎬 扫描到 {len(clips)} 个片段")
            self.ui.set_progress(0.20)
        else:
            self.ui.log_info("IO 内无符合筛选的片段")
            self.ui.set_status("无有效片段")

    def _do_prepare(self, clips: list, mode: str) -> tuple:
        """包装 _prepare()，处理缓存统计和全部缓存完成的情况。
        Returns: (tasks, all_cache_done) — all_cache_done=True 表示全部命中缓存无需处理
        """
        tasks, cache_hits, cache_hit_names = self._prepare(clips, mode)

        self._report["cache_hits"] = cache_hits
        self._report["task_count"] = len(tasks)

        if cache_hits:
            savings = calc_cache_savings(clips, cache_hit_names)
            self.log.cache_savings(cache_hits, savings.get("yuan", 0), savings.get("secs", 0))
            self._report["cache_saved_yuan"] = savings["yuan"]
        else:
            self.log.info("无可复用缓存")

        if not tasks:
            self.log.ok(f"全部由缓存完成！({cache_hits}个)")
            self.ui.set_progress(1.0)
            self.ui.set_status("完成（缓存）")
            ops_logger.session_end(cache_hits, 0, cache_hits)
            return [], True

        self.ui.set_progress(0.25)
        return tasks, False

    def _before_submit(self, tasks: list) -> list:
        """提交前钩子。UI 在此抢锁并过滤任务，CLI 原样返回。
        Returns: 过滤后的任务列表（可能变短）。"""
        return tasks

    def _show_replace_summary(self, output_files: list, total: int):
        """展示替换结果。"""
        for i, of in enumerate(output_files, 1):
            self.log.replace_result(i, total, os.path.basename(of))

    def _get_stop_check(self) -> Callable:
        """获取停止检查函数。子类覆盖（CLI=stop file, UI=_state["stop"]）。"""
        return self._hooks.get("stop_check", lambda: False)

    def _get_progress_callback(self) -> Optional[Callable]:
        """获取进度回调。子类覆盖（UI 有，CLI 无）。"""
        return self._hooks.get("on_progress")

    # ═══════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════

    def _write_report_json(self, path: str):
        """写 JSON 报告到磁盘（CLI 独有）。"""
        import json
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._report, f, indent=2, ensure_ascii=False)
            self.ui.log_info(f"📋 报告已输出: {path}")
        except Exception as e:
            self.ui.log_warn(f"报告写入失败: {e}")

    def _wire_adapter_logger(self, adapter):
        """注入适配器日志回调。兼容两种签名：
        - GhostCut: self._log(level, msg)
        - WuhenAI:  _log(msg)  [单参数]
        """
        if getattr(adapter, '_logger_wired', False):
            return

        def _log_callback(*args):
            # 兼容单参数 (_log(msg)) 和双参数 (_log(level, msg))
            if len(args) == 1:
                level, msg = "info", args[0]
            else:
                level, msg = args[0], args[1]
            # 后端
            self._log_action(msg)
            # UI：仅 warn/error
            if level == "warn":
                self.ui.log_warn(f"  {msg}")
            elif level == "error":
                self.ui.log_fail(f"  {msg}")

        adapter.set_logger(_log_callback)
        adapter._logger_wired = True

    def _log_action(self, msg: str):
        """写 SMB 运维日志。"""
        try:
            from ops_logger import _smb_log
            _smb_log(f"[{self.PRODUCT_NAME}] {msg}")
        except Exception:
            pass
