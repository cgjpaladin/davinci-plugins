#!/usr/bin/env python3
"""
无痕AI (Clipflow) 适配器测试脚本

用法:
  1. 设置 API Key:   export CLIPFLOW_API_KEY="your_key_here"
  2. 设置测试视频:    export TEST_VIDEO="/path/to/test.mp4"
  3. 运行:           python3 test_clipflow.py

测试项:
  - 健康检查 (token 获取 + 余额查询)
  - 上传文件
  - 去字幕任务全流程
"""

import os
import sys
import time

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.clipflow import ClipflowAdapter


def main():
    # ── 配置 ──
    api_key = os.environ.get("CLIPFLOW_API_KEY", "")
    access_token = os.environ.get("CLIPFLOW_ACCESS_TOKEN", "")
    test_video = os.environ.get("TEST_VIDEO", "")

    if not api_key and not access_token:
        print("❌ 请设置 CLIPFLOW_API_KEY 或 CLIPFLOW_ACCESS_TOKEN 环境变量")
        print("   export CLIPFLOW_API_KEY='your_key_here'")
        sys.exit(1)

    if not test_video:
        print("❌ 请设置 TEST_VIDEO 环境变量")
        print("   export TEST_VIDEO='/path/to/test.mp4'")
        sys.exit(1)

    if not os.path.exists(test_video):
        print(f"❌ 测试视频不存在: {test_video}")
        sys.exit(1)

    print("=" * 60)
    print("无痕AI (Clipflow) 适配器测试")
    print("=" * 60)
    print(f"API Key: {api_key[:8]}..." if api_key else "API Key: (未设置)")
    print(f"测试视频: {test_video}")
    print()

    # ── 初始化适配器 ──
    config = {}
    if api_key:
        config["api_key"] = api_key
    if access_token:
        config["access_token"] = access_token

    # 使用无痕模式 (默认)
    config["algorithm"] = 1

    adapter = ClipflowAdapter(config)

    # ── 测试 1: 健康检查 ──
    print("-" * 40)
    print("测试 1: 健康检查")
    print("-" * 40)
    healthy = adapter.check_health()
    if not healthy:
        print("❌ 健康检查失败，请检查 API Key")
        sys.exit(1)

    balance = adapter.get_balance()
    print(f"  余额: {balance['amount']} 积分")
    print(f"  用户类型: {balance['user_type']} (0=L0试用, 1=L1体验, 2=L2高级, 3=L3企业)")
    print()

    # ── 测试 2: 去字幕全流程 ──
    print("-" * 40)
    print("测试 2: 去字幕任务 (无痕模式)")
    print("-" * 40)

    from adapters import WatermarkTask

    output_path = os.path.join(
        os.path.dirname(test_video),
        f"clipflow_output_{int(time.time())}.mp4"
    )

    task = WatermarkTask(
        video_path=test_video,
        output_path=output_path,
        language="zh",
        model="traceless",  # 无痕模式
    )

    print(f"  输入: {test_video}")
    print(f"  输出: {output_path}")
    print(f"  模式: 无痕 (algorithm=1, 智能识别)")
    print()

    start = time.time()

    try:
        result = adapter.process(task, timeout=600)
    except Exception as e:
        print(f"❌ 任务异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start

    print()
    print("=" * 60)
    print("测试结果")
    print("=" * 60)
    print(f"  成功: {'✅' if result.success else '❌'}")
    print(f"  耗时: {elapsed:.1f}秒")

    if result.success:
        print(f"  输出路径: {result.output_path}")
        print(f"  任务ID: {result.task_id}")
        if result.metadata:
            cost = result.metadata.get("cost", 0)
            if cost:
                print(f"  消耗积分: {cost}")
            duration = result.metadata.get("assets_duration", 0)
            if duration:
                print(f"  视频时长: {duration}秒")
    else:
        print(f"  错误: {result.error_message}")

    print()

    # ── 再次检查余额 ──
    balance_after = adapter.get_balance()
    print(f"  处理前余额: {balance['amount']} 积分")
    print(f"  处理后余额: {balance_after['amount']} 积分")
    consumed = balance['amount'] - balance_after['amount']
    if consumed > 0:
        print(f"  本次消耗: {consumed} 积分")


if __name__ == "__main__":
    main()
