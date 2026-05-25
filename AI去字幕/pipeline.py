# -*- coding: utf-8 -*-
"""
pipeline.py — AI去字幕 产品流水线

继承 shared/pipeline_base.py 的 BasePipeline，
只实现 3 个抽象方法（_scan / _prepare / _submit）+ 环境检查钩子。
"""

import os
import time
import math
import sys

# 路径初始化
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)
_shared_root = os.path.join(os.path.dirname(_plugin_root), 'shared')
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

from pipeline_base import BasePipeline, ResultItem
from interface import PipelineUI, DaVinciPipelineUI

from config import (
    __version__, version_string, DEFAULT_MODE, MODE_LABELS,
    CLIP_COLOR, API_TIMEOUT, SMB_MOUNT, DEBUG, SCAN_ONLY,
    get_output_dir, get_log_dir, PLUGIN_DIR, SMB_AI_PROJECT,
)
from core import (
    connect_resolve, scan_io_clips, prepare_tasks, get_io,
    download_and_apply, post_check,
)
from adapters import SubtitleTask, SubtitleResult, create_preferred_adapter
from log_writer import get_logger as _get_logger
_log_ops = _get_logger("AI去字幕")
from pricing import estimate_cost, point_to_yuan


class SubtitlePipeline(BasePipeline):
    """AI去字幕 流水线。"""

    PRODUCT_NAME = "AI去字幕"
    SECTION_AI_PROCESSING = "AI去字幕中"
    PHASE_LABELS = {
        "upload":     "⬆ 上传中",
        "submit":     "📤 提交中",
        "processing": "🤖 AI处理中",
    }
    PROGRESS_BASE = 0.10
    PROGRESS_SCALE = 0.78
    PHASE_DOWNLOAD = "⬇ 下载中"
    PHASE_REPLACE = "🔧 替换中"
    # 产品层进度里程碑
    MILESTONE_BEFORE_SUBMIT = 0.05  # _before_submit
    MILESTONE_ADAPTER_DONE   = 0.81  # adapter 完成后 (>= max: PROGRESS_BASE+0.9*PROGRESS_SCALE≈0.80)
    MILESTONE_REPLACE_DONE   = 0.92  # 替换完成
    # 倒计时阈值
    ETA_MIN_RATIO = 0.05      # ratio 超此值才显示倒计时
    ETA_MIN_ELAPSED = 3       # 至少过 3 秒才显示（避免早期波动）
    ETA_UPDATE_DELTA = 0.01   # ratio 变化 <1% 不更新倒计时
    ETA_NEARLY_DONE = 5       # 剩余 ≤5 秒显示"即将完成"

    def __init__(self):
        super().__init__()
        self._adapter = None
        self._scan_report = None
        self._io_info = None
        self.manual_engine = "auto"
        self.manual_engine_key = None  # config key, e.g. "ghostcut"
        self._engine_failed = False   # UI 用来标记引擎错误

    # ═══════════════════════════════════════
    # 适配器
    # ═══════════════════════════════════════

    def _get_adapter(self):
        if self._adapter is None:
            if self.manual_engine_key == "wuhenai_v21":
                from adapters import create_wuhenai_adapter
                self._adapter = create_wuhenai_adapter()
            elif self.manual_engine_key == "ghostcut":
                from adapters import create_ghostcut_adapter
                self._adapter = create_ghostcut_adapter()
            else:
                self._adapter = create_preferred_adapter()
            _log_ops.ops({"event": "engine_selected", "engine": self.manual_engine, "adapter": self._adapter.__class__.__name__})
        return self._adapter

    def _retry_with_fallback(self, tasks, batch):
        """引擎失败提示，不自动切（用户手动换）"""
        self._engine_failed = True
        self.log.fail(f"处理失败，引擎 '{self.manual_engine}' 不可用，请更换引擎后重试")
        return super()._retry_with_fallback(tasks, batch)

    # ═══════════════════════════════════════
    # 抽象方法实现
    # ═══════════════════════════════════════

    def _scan(self) -> list:
        """扫描时间线 IO 内标橙色的片段。"""
        clips, self._scan_report = scan_io_clips(self._timeline, CLIP_COLOR)
        io_in, io_out = get_io(self._timeline)
        self._io_info = {"in": io_in, "out": io_out}
        self._report["io"] = self._io_info
        if self._scan_report:
            self._report["scan"] = {
                "total": self._scan_report.total,
                "valid": self._scan_report.valid,
                "skipped": self._scan_report.skipped,
            }
        return clips

    def _show_scan_summary(self, clips: list):
        """展示扫描结果（含 IO 范围和扫描统计）。"""
        if not clips:
            self.ui.log_info("IO 内无符合筛选的片段")
            self.ui.set_status("无有效片段")
            return

        io_info = self._io_info or {}
        sr = self._scan_report
        if sr:
            self.ui.log_info(f"🎬 IO({io_info.get('in', '?')}→{io_info.get('out', '?')}): "
                           f"{sr.valid}/{sr.total} 符合筛选")
        else:
            self.ui.log_info(f"🎬 扫描到 {len(clips)} 个片段")
        self.ui.set_progress(self.MILESTONE_ENV_OK)  # 扫描完成进度 = 环境自检同级别
        self._report.setdefault("scan", {})["clips_count"] = len(clips)

        # 记录扫描结果到运营日志
        _log_ops.ops({"event": "clip_scan", "total": len(clips), "clips": [c.name for c in clips]})

    def _prepare(self, clips: list, mode: str) -> tuple:
        """任务准备（含缓存复用）。返回 (tasks, cache_hits, cache_hit_names)。"""
        from core import prepare_tasks as _prepare_tasks

        self._output_dir = get_output_dir(self._project_root)
        self._report["project_root"] = self._project_root
        self._report["output_dir"] = self._output_dir

        prepared = _prepare_tasks(
            clips, mode, self._output_dir,
            force=self._force,
            stop_check=self._get_stop_check(),
        )
        self._report["_tasks"] = prepared.tasks  # 存引用给 _final_report 用

        return prepared.tasks, prepared.cache_hits, prepared.cache_hit_names

    def _submit(self, tasks: list, batch: bool) -> list:
        """提交 API 处理。返回 [ResultItem, ...] 列表。"""
        adapter = self._get_adapter()
        # API 健康预检——手动模式不切备选，直接报错
        if hasattr(adapter, 'check_health') and not adapter.check_health():
            if self.manual_engine != "auto":
                self._engine_failed = True
                alt_key = "ghostcut" if self.manual_engine_key == "wuhenai_v21" else "wuhenai_v21"
                # 手动模式不自动切备选，只提示
                alt_name = ADAPTER_CONFIGS.get(alt_key, {}).get("name", alt_key)
                self.log.fail(f"引擎 '{self.manual_engine}' 不可用")
                self.log.warn(f"请切换到 {alt_name} 重试（若 {alt_name} 也不可用，则 API 可能暂时故障）")
                return [ResultItem(
                    mp_item=t.mp_item, name=t.name, path=t.path,
                    result=SubtitleResult(success=False, error_message=f"引擎不可用: {self.manual_engine}"),
                    elapsed=0, tl_item=t.tl_item, tl_color=t.tl_color,
                    mp_color=t.mp_color, alt_tl_items=t.alt_tl_items,
                ) for t in tasks]
            cls_name = adapter.__class__.__name__
            exclude = adapter.provider_key
            _log_ops.ops({"event": "adapter_health_fail", "adapter": cls_name})
            fallback = create_preferred_adapter(exclude=exclude)
            if fallback and hasattr(fallback, 'check_health') and fallback.check_health():
                adapter = fallback
                self._adapter = fallback
                _log_ops.ops({"event": "adapter_fallback", "from": cls_name,
                               "to": fallback.__class__.__name__})
            else:
                cls_name = adapter.__class__.__name__
                self._adapter = None
                _log_ops.ops({"event": "adapter_fallback", "from": cls_name, "to": "none"})
                self.log.fail(f"{cls_name} 不可用，备选也失败，API 可能暂时故障")
                return [ResultItem(
                    mp_item=t.mp_item, name=t.name, path=t.path,
                    result=SubtitleResult(success=False, error_message="API不可用"),
                    elapsed=0, tl_item=t.tl_item, tl_color=t.tl_color,
                    mp_color=t.mp_color, alt_tl_items=t.alt_tl_items,
                ) for t in tasks]
        api_tasks = [SubtitleTask(**t.kwargs) for t in tasks]
        provider = adapter.name

        # 显示处理开始
        for i, t in enumerate(tasks, 1):
            self.log.progress(i, len(tasks), t.name, "处理中")

        self.ui.set_status("AI 处理中...")

        t0 = time.time()
        api_results = adapter.process_batch(
            api_tasks, timeout=API_TIMEOUT,
            cancel_check=self._get_stop_check(),
            progress_callback=self._get_progress_callback(),
        )
        elapsed = time.time() - t0

        # 适配器处理完成
        self.log.info(f"全部完成，耗时 {elapsed:.0f} 秒")

        # 构造结果，task_id 只进后端
        results = []
        for t, r in zip(tasks, api_results):
            if r and r.success:
                self._log_action(f"✅ {t.name} (task_id={getattr(r, 'task_id', '')})")
            else:
                msg = getattr(r, 'error_message', '未知错误') if r else '处理失败'
                self.log.fail(f"{t.name}: {msg}")
                self._log_action(f"❌ {t.name}: {msg}")

            results.append(ResultItem(
                mp_item=t.mp_item, name=t.name, path=t.path,
                result=r, elapsed=time.time() - t0,
                tl_item=t.tl_item, tl_color=t.tl_color,
                mp_color=t.mp_color, alt_tl_items=t.alt_tl_items,
            ))

        self.ui.set_progress(self.MILESTONE_ADAPTER_DONE)
        self.ui.set_status("下载处理结果...")
        return results

    # ═══════════════════════════════════════
    # 进度回调：统一阶段映射 + 动态倒计时（覆盖基类）
    # ═══════════════════════════════════════

    def _get_progress_callback(self):
        """统一进度回调：adapter 全局 ratio→宽绿条 + 阶段标签 + 动态倒计时"""
        import time as _time
        labels = self.PHASE_LABELS
        base = self.PROGRESS_BASE
        scale = self.PROGRESS_SCALE

        _phase_start = [_time.time()]
        _last_label = [""]
        _last_ratio = [0.0]

        def cb(phase, ratio):
            self.ui.set_progress(base + ratio * scale)

            label = labels.get(phase, phase)
            if label != _last_label[0]:
                _last_label[0] = label
                _phase_start[0] = _time.time()

            elapsed = _time.time() - _phase_start[0]
            if ratio > self.ETA_MIN_RATIO and ratio > _last_ratio[0] + self.ETA_UPDATE_DELTA and elapsed > self.ETA_MIN_ELAPSED:
                _last_ratio[0] = ratio
                remaining = elapsed / ratio * (1 - ratio)
                if remaining < self.ETA_NEARLY_DONE:
                    self.ui.set_phase(f"{label} · 即将完成...")
                else:
                    mins, secs = divmod(int(remaining), 60)
                    eta_text = f"约剩 {mins}分{secs}秒" if mins > 0 else f"约剩 {secs}秒"
                    self.ui.set_phase(f"{label} · {eta_text}")
            else:
                self.ui.set_phase(label)

        return cb

    def _download_apply(self, results: list) -> list:
        """覆盖基类：加下载/替换步骤 + 状态栏标签"""
        self.ui.set_phase(self.PHASE_DOWNLOAD)
        self._step("下载")
        output_files = super()._download_apply(results)
        self.ui.set_phase(self.PHASE_REPLACE)
        self._step("替换")
        self.ui.set_progress(self.MILESTONE_REPLACE_DONE)
        return output_files

    # ═══════════════════════════════════════
    # CLI 专属：环境自检
    # ═══════════════════════════════════════

    def _check_env(self):
        """CLI 环境自检：SMB/API/OSS/DVR。UI 跳过（在 scan_io 中逐渐检查）。"""
        from config import WUHENAI_V2_API_KEY, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET

        checks = {
            "SMB 挂载": os.path.exists(SMB_MOUNT),
            "API Key (无痕AI 2.1)": bool(WUHENAI_V2_API_KEY),
            "OSS 凭证 (阿里云)": bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET),
            "达芬奇运行": os.path.exists("/Applications/DaVinci Resolve"),
        }

        all_ok = True
        for name, ok_flag in checks.items():
            if not ok_flag:
                self.ui.log_fail(f"环境自检失败: {name} 不可用")
                all_ok = False

        if not all_ok:
            self.ui.log_info("💡 请确保: SMB 已挂载 / .env 已配置 / 达芬奇已启动")
            self._report["error"] = "环境自检失败"
            self._report["checks"] = {n: f for n, f in checks.items()}
            return

        self.ui.log_info("✅ 环境自检通过 (SMB/API/OSS/DVR)")
        self.ui.set_progress(self.MILESTONE_BEFORE_SUBMIT)

    def _preflight(self):
        """CLI OSS 预检。"""
        try:
            adapter = self._get_adapter()
            if hasattr(adapter, 'check_oss') and not adapter.check_oss():
                self.ui.log_fail("无痕AI OSS 不可用，请检查阿里云账号状态")
                self._report["error"] = "OSS不可用"
        except Exception as e:
            self.ui.log_fail(f"OSS 预检失败: {e}")
            self._report["error"] = str(e)
