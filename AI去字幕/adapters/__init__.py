"""
适配器抽象基类 —— API 无关的接口定义。

所有去字幕服务商必须实现此接口。
换 API = 换一个适配器类，插件主体不动。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    """异步任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class SubtitleTask:
    """
    去字幕任务描述
    
    Attributes:
        video_path: 输入视频的本地路径或公网URL
        output_path: 期望的输出本地路径（适配器负责下载）
        language: 字幕语言代码，默认 "zh"
        mask_regions: 可选，手动指定的擦除区域坐标
        model: 可选，指定擦除模型（lite/pro/full）
        duration: 可选，视频时长（秒），用于进度加权
    """
    video_path: str
    output_path: Optional[str] = None
    language: str = "zh"
    mask_regions: Optional[list] = None
    model: Optional[str] = None
    duration: float = 10.0
    resolution: Optional[str] = None  # "720x1280" 等，扫描时从达芬奇API获取


@dataclass
class SubtitleResult:
    """
    去字幕处理结果
    
    Attributes:
        success: 是否成功
        output_path: 处理后的视频本地路径
        task_id: 服务商返回的任务ID
        error_message: 失败时的错误信息
        metadata: 服务商返回的额外元数据（如处理耗时、费用等）
    """
    success: bool
    output_path: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """
    去字幕适配器抽象基类
    
    所有服务商适配器必须实现 submit() 和 wait_for_result()。
    如果服务商是同步模式，wait_for_result() 可直接返回结果。

    契约:
      - wait_for_result() 必须接受 cancel_check 参数
      - cancel_check 为可选回调: () -> bool, 返回 True 时取消任务
      - 不需要取消的适配器接受参数但不使用即可
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self._output_path: Optional[str] = None  # process() 设置，wait_for_result() 消费
        self._logger = print  # 默认 stdout；外部可注入 set_logger(callback)

    def set_logger(self, callback):
        """注入日志回调。callback(level: str, msg: str) — level: info/warn/error/debug。
        
        所有适配器通过此回调输出，不直接 print()。
        回调负责路由：UI 日志区 / SMB ops log / CLI stdout。
        """
        self._logger = callback or print

    def _log(self, level: str, msg: str):
        """统一日志输出。不直接 print()，通过注入的回调分发。"""
        if self._logger:
            self._logger(level, msg)

    @abstractmethod
    def submit(self, task: SubtitleTask) -> str:
        """
        提交去字幕任务
        
        Returns:
            task_id: 服务商返回的任务标识符
        """
        ...

    @abstractmethod
    def wait_for_result(self, task_id: str, timeout: int = 600,
                        cancel_check=None) -> SubtitleResult:
        """
        等待任务完成并获取结果
        
        Args:
            task_id: submit() 返回的任务ID
            timeout: 最大等待时间（秒）
            cancel_check: 可选回调 () -> bool，返回 True 时取消任务
            
        Returns:
            SubtitleResult: 包含处理结果
        """
        ...

    def process(self, task: SubtitleTask, timeout: int = 600,
                output_path: str = None, cancel_check=None) -> SubtitleResult:
        """
        一键处理：提交 → 等待 → 下载

        Args:
            task: 去字幕任务描述
            timeout: 最大等待时间（秒）
            output_path: 结果下载路径。None 则不下载，返回远程 URL。
            cancel_check: 可选回调 () -> bool，传递给 wait_for_result()
        """
        self._output_path = output_path
        try:
            task_id = self.submit(task)
            return self.wait_for_result(task_id, timeout, cancel_check=cancel_check)
        except Exception as e:
            # 把任何适配器错误封装成 SubtitleResult，不向上抛异常
            # 调用者检查 result.success 即可判断成功/失败
            return SubtitleResult(
                success=False,
                error_message=str(e)
            )

    def check_health(self) -> bool:
        """健康检查：验证 API 凭证是否有效"""
        return True  # 子类可选覆盖

    def process_batch(self, tasks: list, timeout: int = 600,
                      cancel_check=None, progress_callback=None) -> list:
        """批量处理多片段。默认实现：逐个调用 process()。

        适配器可以覆写以提供更高效的批量流水线（如并发上传、批量提交、统一轮询）。
        覆写时签名保持一致，调用方只依赖本接口。
        """
        results = []
        for task in tasks:
            if cancel_check and cancel_check():
                break
            r = self.process(task, timeout=timeout, cancel_check=cancel_check)
            results.append(r)
        return results


def create_wuhenai_adapter(mode: str = "pro_box") -> "WuhenAIV21Adapter":
    """创建标准配置的无痕AI 2.1 适配器。
    CLI 和 UI 统一入口，保证行为一致。

    TODO(2026-05): mode 参数预留，将来支持不同模式（如 basic→all_area）。
    """
    from copy import deepcopy
    from config import ADAPTER_CONFIGS
    from adapters.wuhenai_v2 import WuhenAIV21Adapter

    _ = mode
    adapter_cfg = deepcopy(ADAPTER_CONFIGS["wuhenai_v21"])
    adapter_cfg["model"] = "video_removal_std"
    adapter_cfg["method"] = "sel_area"
    return WuhenAIV21Adapter(adapter_cfg)


def create_ghostcut_adapter(mode: str = "pro_box") -> "GhostCutAdapter":
    """创建鬼手适配器。默认 pro_box（正式出片）模式。"""
    from copy import deepcopy
    from config import ADAPTER_CONFIGS
    from adapters.ghostcut import GhostCutAdapter

    _ = mode
    adapter_cfg = deepcopy(ADAPTER_CONFIGS["ghostcut"])
    return GhostCutAdapter(adapter_cfg)


def create_preferred_adapter():
    """按 ADAPTER_PRIORITY 依次尝试，返回第一个有余额的适配器。"""
    from pricing_defaults import ADAPTER_PRIORITY
    for key in ADAPTER_PRIORITY:
        try:
            if key == "ghostcut":
                a = create_ghostcut_adapter()
                bal = a.get_balance()
                pts = sum(x["pointBalance"] for x in bal.get("pointAssets", []) if x["pointBalance"] > 0)
            else:
                a = create_wuhenai_adapter()
                pts = float(a.get_balance().get("balance", 0))
            if pts >= 5:
                return a
        except Exception:
            continue
    return create_wuhenai_adapter()  # 兜底
