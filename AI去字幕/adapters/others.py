"""
待实现的适配器占位

无痕AI (Clipflow) 已有独立适配器: adapters/clipflow.py
"""

from . import BaseAdapter, WatermarkTask, WatermarkResult


class VolcengineAdapter(BaseAdapter):
    """火山引擎 VOD 字幕擦除适配器（待实现）"""
    
    def __init__(self, config: dict):
        super().__init__("火山引擎", config)

    def submit(self, task: WatermarkTask) -> str:
        raise NotImplementedError("火山引擎适配器待 API 申请后实现")

    def wait_for_result(self, task_id: str, timeout: int = 600) -> WatermarkResult:
        raise NotImplementedError("火山引擎适配器待 API 申请后实现")


class TencentAdapter(BaseAdapter):
    """腾讯云 MPS 智能擦除适配器（待实现）"""
    
    def __init__(self, config: dict):
        super().__init__("腾讯云", config)

    def submit(self, task: WatermarkTask) -> str:
        raise NotImplementedError("腾讯云适配器待 API 申请后实现")

    def wait_for_result(self, task_id: str, timeout: int = 600) -> WatermarkResult:
        raise NotImplementedError("腾讯云适配器待 API 申请后实现")


class AliyunAdapter(BaseAdapter):
    """阿里云 IMS 视频擦除适配器（待实现）"""
    
    def __init__(self, config: dict):
        super().__init__("阿里云", config)

    def submit(self, task: WatermarkTask) -> str:
        raise NotImplementedError("阿里云适配器待 API 申请后实现")

    def wait_for_result(self, task_id: str, timeout: int = 600) -> WatermarkResult:
        raise NotImplementedError("阿里云适配器待 API 申请后实现")
