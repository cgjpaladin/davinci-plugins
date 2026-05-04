"""
无痕AI (Clipflow) 适配器

API 文档: https://suiyu-network.feishu.cn/wiki/FruuwE5iEiOx4pkBEUwc0ACMns5
Base URL: https://app.clipflow.cn
认证: API Key → access_token (Bearer Token)
交互: 多步异步任务 + 轮询

依赖: 仅 Python 标准库（urllib + json + os + time + secrets）
      全国几千个剪辑师拿到就能跑，零 pip install

Clipflow 去字幕流程:
  1. partner/:access_key → 获取 access_token
  2. asset/prepare_put_object → 获取 OSS 上传凭证
  3. PUT 文件到 OSS
  4. task/create → 创建去字幕任务 (type=0)
  5. task/rule/:task_id → 设置擦除规则
  6. task/add_asset → 添加素材
  7. task/start → 启动任务
  8. task/:task_id → 轮询状态
  9. task/asset/:asset_id → 获取 download_url
"""

import json
import os
import secrets
import ssl
import time
import urllib.request
import urllib.error
from typing import Optional
from urllib.parse import urlparse

from . import BaseAdapter, WatermarkTask, WatermarkResult, TaskStatus

# 达芬奇内置 Python 可能缺 SSL 证书 — 全局宽松 context
_SSL_CTX = ssl.create_default_context()

# 任务状态码
_TASK_STATUS = {
    0: "已创建",
    20: "已中止",
    100: "排队中",
    400: "有错误",
    1000: "处理中",
    2000: "已完成",
}


class ClipflowAdapter(BaseAdapter):
    """无痕AI (Clipflow) 去水印适配器"""

    BASE_URL = "https://app.clipflow.cn"
    API_PREFIX = "/api/v1"

    def __init__(self, config: dict):
        super().__init__("Clipflow", config)
        self.api_key = config.get("api_key")
        self._access_token = config.get("access_token")  # 可选，直接提供 token
        self._user_id = None
        self._token_expires = 0

        if not self.api_key and not self._access_token:
            raise ValueError("Clipflow 适配器需要 api_key 或 access_token")

        # 默认去字幕模式: 无痕模式 (algorithm=1)
        self.default_algorithm = config.get("algorithm", 1)
        # 默认使用智能识别字幕区域
        self.default_rect_type = config.get("rect_type", 1)  # 1=智能识别

    # ── 通用请求 ──────────────────────────────────────────────

    def _common_params(self) -> dict:
        """公共查询参数"""
        return {
            "version": "1.0",
            "t": str(int(time.time())),
            "nonce": secrets.token_hex(6),
        }

    def _ensure_token(self):
        """确保 access_token 有效"""
        # 直接提供了 token 且未过期 → 直接用
        if self._access_token and (self._token_expires == 0 or time.time() < self._token_expires):
            return

        if self.api_key:
            # 通过 API Key 获取 access_token（直接请求，不走 _api_request 避免递归）
            params = self._common_params()
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{self.BASE_URL}{self.API_PREFIX}/partner/{self.api_key}?{query}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") != 200:
                raise RuntimeError(f"获取 token 失败: {result.get('msg')}")
            data = result["data"]
            self._access_token = data["access_token"]
            self._user_id = data["user_id"]
            self._token_expires = data.get("expired", 0) - 300  # 提前5分钟刷新
            print(f"[Clipflow] Token 获取成功, user_id={self._user_id}")
        else:
            raise RuntimeError("无可用的 access_token，请提供 api_key")

    def _api_request(self, method: str, path: str, params: dict = None,
                     body: dict = None) -> dict:
        """通用 API 请求"""
        self._ensure_token()

        if params is None:
            params = self._common_params()
        params["access_token"] = self._access_token

        # 构建 URL
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE_URL}{self.API_PREFIX}/{path}?{query}"

        headers = {"Content-Type": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Clipflow API {e.code}: {err_body[:300]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}") from e

        if result.get("code") != 200:
            raise RuntimeError(
                f"Clipflow API 错误: code={result.get('code')}, msg={result.get('msg')}"
            )
        return result.get("data", {})

    def _api_get(self, path: str, params: dict = None) -> dict:
        return self._api_request("GET", path, params=params)

    def _api_post(self, path: str, body: dict = None, params: dict = None) -> dict:
        return self._api_request("POST", path, params=params, body=body)

    def _api_put(self, path: str, body: dict = None, params: dict = None) -> dict:
        return self._api_request("PUT", path, params=params, body=body)

    # ── 文件上传 ──────────────────────────────────────────────

    def _upload_file(self, local_path: str) -> str:
        """
        上传本地文件到 Clipflow OSS，返回 object_key

        流程:
        1. prepare_put_object → 获取 OSS 上传地址 + headers
        2. PUT 文件到 OSS
        3. 返回 object_key (后续 add_asset 用)
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        filename = os.path.basename(local_path)
        ext = os.path.splitext(filename)[1] or ".mp4"

        # Step 1: 获取上传凭证
        prepare = self._api_post("asset/prepare_put_object", body={"ext": ext})
        upload_url = prepare["url"]
        object_key = prepare["object_key"]
        oss_headers = prepare.get("headers", {})

        print(f"[Clipflow] 上传文件: {filename} → {object_key}")

        # Step 2: PUT 文件到 OSS
        with open(local_path, "rb") as f:
            file_data = f.read()

        put_headers = {"Content-Type": oss_headers.get("Content-Type", "application/octet-stream")}
        if "X-Oss-Object-Acl" in oss_headers:
            put_headers["x-oss-object-acl"] = oss_headers["X-Oss-Object-Acl"]

        req = urllib.request.Request(
            upload_url,
            data=file_data,
            headers=put_headers,
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=300, context=_SSL_CTX) as resp:
                status = resp.status
                if status not in (200, 201):
                    raise RuntimeError(f"OSS 上传失败, HTTP {status}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OSS 上传失败 {e.code}: {err_body[:200]}") from e

        print(f"[Clipflow] 上传完成: {object_key}")
        return object_key

    # ── 核心接口实现 ──────────────────────────────────────────

    def submit(self, task: WatermarkTask) -> str:
        """
        提交去字幕任务

        完整流程:
        1. 上传文件 (如果是本地文件)
        2. 创建任务 (type=0, 去字幕)
        3. 设置规则 (无痕/极速模式)
        4. 添加素材
        5. 启动任务

        Returns:
            task_id: Clipflow 任务ID
        """
        video_path = task.video_path

        # Step 1: 上传文件
        parsed = urlparse(video_path)
        if not parsed.scheme.startswith("http"):
            print(f"[Clipflow] 检测到本地文件，自动上传: {os.path.basename(video_path)}")
            object_key = self._upload_file(video_path)
            use_object_key = True
        else:
            # 公网 URL，直接用 video_url
            object_key = None
            use_object_key = False

        # Step 2: 创建任务
        task_name = os.path.basename(video_path) if not parsed.scheme.startswith("http") else "clipflow_task"
        create_data = self._api_post("task/create", body={
            "name": task_name,
            "type": 0,  # 0=视频去字幕
        })
        clipflow_task_id = create_data["id"]
        print(f"[Clipflow] 任务创建成功: {clipflow_task_id}")

        # Step 3: 设置规则
        algorithm = self.default_algorithm
        rule_body = self._build_rule(task, algorithm)
        self._api_put(f"task/rule/{clipflow_task_id}", body=rule_body)
        print(f"[Clipflow] 规则设置完成: algorithm={algorithm}")

        # Step 4: 添加素材
        asset_body = {"task_id": clipflow_task_id}
        if use_object_key:
            asset_body["object_key"] = object_key
        else:
            asset_body["video_url"] = video_path

        asset_data = self._api_post("task/add_asset", body=asset_body)
        asset_id = asset_data["id"]
        print(f"[Clipflow] 素材添加成功: asset_id={asset_id}")

        # 保存 asset_id 到任务映射，轮询时用
        if not hasattr(self, '_task_assets'):
            self._task_assets = {}
        self._task_assets[clipflow_task_id] = asset_id

        # Step 5: 启动任务
        self._api_post("task/start", body={"task_id": clipflow_task_id})
        print(f"[Clipflow] 任务已启动: {clipflow_task_id}")

        return clipflow_task_id

    def _build_rule(self, task: WatermarkTask, algorithm: int) -> dict:
        """
        构建去字幕规则

        无痕模式 (algorithm=1):
          - type=1 (统一擦除)
          - 仅支持 1 个擦除区域
          - 支持智能识别 (type=1) 或人工框选 (type=0)

        极速模式 (algorithm=0):
          - type=0 (片头片尾) / type=1 (统一擦除) / type=3 (时间分段)
          - 支持 1-3 个擦除区域
        """
        if algorithm == 1:
            # 无痕模式
            if task.mask_regions:
                # 用户指定了区域
                rects = []
                for region in task.mask_regions:
                    if isinstance(region, dict) and "x" in region:
                        rects.append({
                            "type": 0,  # 人工框选
                            "x": region["x"],
                            "y": region["y"],
                            "w": region["w"],
                            "h": region["h"],
                        })
                    elif isinstance(region, (list, tuple)) and len(region) == 4:
                        # [x, y, w, h] 格式
                        rects.append({
                            "type": 0,
                            "x": region[0],
                            "y": region[1],
                            "w": region[2],
                            "h": region[3],
                        })
            else:
                # 默认智能识别
                rects = [{"type": 1, "x": 0, "y": 0, "w": 0, "h": 0}]

            return {
                "algorithm": 1,
                "type": 1,  # 统一擦除
                "content": {"rects": rects},
            }
        else:
            # 极速模式
            if task.mask_regions:
                rects = []
                for region in task.mask_regions[:3]:  # 最多3个
                    if isinstance(region, dict) and "x" in region:
                        rects.append({
                            "type": 0,
                            "x": region["x"],
                            "y": region["y"],
                            "w": region["w"],
                            "h": region["h"],
                        })
                    elif isinstance(region, (list, tuple)) and len(region) == 4:
                        rects.append({
                            "type": 0,
                            "x": region[0],
                            "y": region[1],
                            "w": region[2],
                            "h": region[3],
                        })
            else:
                # 默认智能识别
                rects = [{"type": 1, "x": 0, "y": 0, "w": 0, "h": 0}]

            return {
                "algorithm": 0,
                "type": 1,  # 统一擦除
                "content": {"rects": rects},
            }

    def wait_for_result(self, task_id: str, timeout: int = 600) -> WatermarkResult:
        """
        轮询任务结果

        任务状态码:
          0=已创建, 20=已中止, 100=排队中, 400=有错误
          1000=处理中, 2000=已完成
        """
        start_time = time.time()
        poll_interval = 5

        asset_id = self._task_assets.get(task_id) if hasattr(self, '_task_assets') else None

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return WatermarkResult(
                    success=False,
                    task_id=task_id,
                    error_message=f"任务超时 ({timeout}秒)"
                )

            try:
                task_data = self._api_get(f"task/{task_id}")
                status = task_data.get("status", 0)
                progress = task_data.get("progress", 0)

                if status == 2000:
                    # 任务完成，获取素材结果
                    download_path = self._output_path

                    if asset_id:
                        asset_data = self._api_get(
                            f"task/asset/{asset_id}",
                            params={**self._common_params(), "task_id": task_id}
                        )
                        download_url = asset_data.get("download_url", "")
                        output_url = asset_data.get("output_url", "")

                        # 下载到本地
                        if download_path and download_url:
                            print(f"[Clipflow] 下载处理结果到: {download_path}")
                            urllib.request.urlretrieve(download_url, download_path)
                            output = download_path
                        else:
                            output = download_url or output_url or download_path

                        return WatermarkResult(
                            success=True,
                            task_id=task_id,
                            output_path=output,
                            metadata={
                                "download_url": download_url,
                                "output_url": output_url,
                                "cost": task_data.get("cost", 0),
                                "assets_duration": task_data.get("succeeded_assets_duration", 0),
                            }
                        )
                    else:
                        # 没有 asset_id，返回任务级别的信息
                        return WatermarkResult(
                            success=True,
                            task_id=task_id,
                            output_path=download_path,
                            metadata={
                                "cost": task_data.get("cost", 0),
                                "succeeded_assets": task_data.get("succeeded_assets", 0),
                            }
                        )

                elif status == 400:
                    return WatermarkResult(
                        success=False,
                        task_id=task_id,
                        error_message=f"任务处理出错 (status=400)"
                    )
                elif status == 20:
                    return WatermarkResult(
                        success=False,
                        task_id=task_id,
                        error_message="任务已被中止"
                    )
                # else: 0/100/1000 → 继续等待

                status_name = _TASK_STATUS.get(status, f"未知({status})")
                print(f"[Clipflow] 状态: {status_name}, 进度: {progress:.1f}%")

            except (urllib.error.URLError, OSError) as e:
                print(f"[Clipflow] 网络错误: {e}，{poll_interval}秒后重试...")

            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 30)

    def check_health(self) -> bool:
        """检查 API 凭证是否有效"""
        try:
            self._ensure_token()
            # 查询用户信息验证 token
            user_data = self._api_get(f"user/{self._user_id}")
            balance = user_data.get("amount", 0)
            print(f"[Clipflow] 健康检查通过, 余额: {balance} 积分")
            return True
        except Exception as e:
            print(f"[Clipflow] 健康检查失败: {e}")
            return False

    def get_balance(self) -> dict:
        """查询账户余额"""
        self._ensure_token()
        user_data = self._api_get(f"user/{self._user_id}")
        return {
            "amount": user_data.get("amount", 0),
            "user_type": user_data.get("type", 0),
            "nickname": user_data.get("nickname", ""),
        }
