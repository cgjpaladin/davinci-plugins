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
class WatermarkTask:
    """
    去字幕任务描述
    
    Attributes:
        video_path: 输入视频的本地路径或公网URL
        output_path: 期望的输出本地路径（适配器负责下载）
        language: 字幕语言代码，默认 "zh"
        mask_regions: 可选，手动指定的擦除区域坐标
        model: 可选，指定擦除模型（lite/pro/full）
    """
    video_path: str
    output_path: Optional[str] = None
    language: str = "zh"
    mask_regions: Optional[list] = None
    model: Optional[str] = None


@dataclass
class WatermarkResult:
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
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def submit(self, task: WatermarkTask) -> str:
        """
        提交去字幕任务
        
        Returns:
            task_id: 服务商返回的任务标识符
        """
        ...

    @abstractmethod
    def wait_for_result(self, task_id: str, timeout: int = 600) -> WatermarkResult:
        """
        等待任务完成并获取结果
        
        Args:
            task_id: submit() 返回的任务ID
            timeout: 最大等待时间（秒）
            
        Returns:
            WatermarkResult: 包含处理结果
        """
        ...

    def process(self, task: WatermarkTask, timeout: int = 600,
                output_path: str = None, cancel_check=None) -> WatermarkResult:
        """
        一键处理：提交 → 等待 → 下载

        Args:
            task: 去字幕任务描述
            timeout: 最大等待时间（秒）
            output_path: 结果下载路径。None 则不下载，返回远程 URL。
        """
        self._output_path = output_path
        try:
            task_id = self.submit(task)
            return self.wait_for_result(task_id, timeout, cancel_check=cancel_check)
        except Exception as e:
            return WatermarkResult(
                success=False,
                error_message=str(e)
            )

    def check_health(self) -> bool:
        """健康检查：验证 API 凭证是否有效"""
        return True  # 子类可选覆盖
