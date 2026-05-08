# -*- coding: utf-8 -*-
"""
达芬奇渲染工具函数。

来源技巧：
  - get_current_render_settings() — filenameGenerator.py 张来吃（临时创建渲染任务读设置）
"""


def get_current_render_settings(resolve):
    """读取当前渲染预设的详细参数（不触发实际渲染）。

    原理：临时创建一个渲染任务 → 读取任务详情 → 立刻删除。
    拿到 VideoCodec / AudioCodec / FormatWidth/Height / FrameRate 等参数。

    Args:
        resolve: DaVinci Resolve 对象

    Returns:
        dict — 渲染任务详情（含 JobId / OutputFilename / VideoCodec 等）
    """
    pj = resolve.GetProjectManager().GetCurrentProject()
    if not pj:
        raise RuntimeError("没有打开的项目")

    media_storage = resolve.GetMediaStorage()
    temp_id = pj.AddRenderJob()

    if not temp_id:
        # 没设 TargetDir 时 AddRenderJob 返回空 → 补一个路径再试
        volumes = media_storage.GetMountedVolumeList()
        if volumes:
            pj.SetRenderSettings({"TargetDir": volumes[0]})
            temp_id = pj.AddRenderJob()

    if not temp_id:
        raise RuntimeError("无法创建临时渲染任务（检查渲染预设和输出路径）")

    renderqueue = pj.GetRenderJobList()
    current_detail = next(d for d in renderqueue if d["JobId"] == temp_id)
    pj.DeleteRenderJob(temp_id)
    return current_detail
