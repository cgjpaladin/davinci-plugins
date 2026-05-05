"""
无痕AI V2.1 适配器 (api.wuhenai.com)

API 文档: https://suiyu-network.feishu.cn/wiki/WUvXwI5vziT24qkAVdDcxTzLnef
Base URL: https://api.wuhenai.com/v2/
认证: API Key → Bearer access_token (7天有效)
交互: POST 创建任务 → 轮询状态 → 从 OSS 下载结果

V2.1 新架构:
  1. 本地文件 → 上传到自己的 OSS → 生成预签名 URL
  2. POST /video_removal (指定 video_url + upload_url)
  3. 无痕AI 从 video_url 拉取视频，处理完 PUT 到 upload_url
  4. 轮询 GET /status 直到完成
  5. 从 OSS 下载结果

依赖: 仅 Python 标准库（urllib + hashlib + json + os + time + secrets）
      全国几千个剪辑师拿到就能跑，零 pip install

日志注入: 通过 wuhenai_set_logger(callback) 切换输出目标。
  默认 print → stdout（CLI 模式）
  UI 模式注入 UILogger callback → 界面日志区
"""

import hashlib
import hmac
import json
import os
import secrets
import ssl
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional, Any
from urllib.parse import urlparse, quote
from email.utils import formatdate

from . import BaseAdapter, WatermarkTask, WatermarkResult, TaskStatus

_SSL_CTX = ssl.create_default_context()

# ── 日志注入 ──
_log = print  # 默认 stdout

def wuhenai_set_logger(callback):
    """注入自定义日志回调。callback(msg: str) -> None"""
    global _log
    _log = callback if callback else print

# 任务状态
_TASK_STATUS_MAP = {
    "created": "已创建",
    "queued": "排队中",
    "processing": "处理中",
    "success": "已完成",
    "failed": "失败",
    "paused": "已暂停",
}


class WuhenAIV21Adapter(BaseAdapter):
    """无痕AI 2.1 适配器"""

    BASE_URL = "https://api.wuhenai.com/v2"
    OSS_REGION = "cn-hangzhou"
    OSS_ENDPOINT_TEMPLATE = "{bucket}.oss-{region}.aliyuncs.com"

    def __init__(self, config: dict):
        super().__init__("无痕AI 2.1", config)
        self.api_key = config.get("api_key", "")
        self.access_key_id = config.get("oss_access_key_id", "")
        self.access_key_secret = config.get("oss_access_key_secret", "")
        self.bucket = config.get("oss_bucket", "")
        self.oss_region = config.get("oss_region", self.OSS_REGION)

        self._access_token: Optional[str] = None
        self._token_expires: float = 0

        # 去字幕参数
        self.default_model = config.get("model", "video_removal_std")
        self.default_method = config.get("method", "all_area")

        if not self.api_key:
            raise ValueError("无痕AI 2.1 需要 api_key")
        if not all([self.access_key_id, self.access_key_secret, self.bucket]):
            raise ValueError("需要 OSS 凭证: oss_access_key_id, oss_access_key_secret, oss_bucket")

    @staticmethod
    def _get_video_resolution(video_path: str) -> tuple[int, int]:
        """用 ffprobe 获取视频宽高，返回 (width, height)"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, timeout=10,
            )
            w, h = result.stdout.strip().split(",")
            return int(w), int(h)
        except Exception:
            return 1920, 1080  # fallback

    # ── 通用请求 ──────────────────────────────────────────────

    def _common_params(self) -> str:
        return f"nonce={secrets.token_hex(6)}&t={int(time.time())}"

    def _ensure_token(self):
        if self._access_token and time.time() < self._token_expires:
            return
        url = f"{self.BASE_URL}/user/access_token?{self._common_params()}&api_key={self.api_key}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {data.get('message')}")
        self._access_token = data["data"]["access_token"]
        self._token_expires = data["data"]["expired"] - 3600  # 提前1小时刷新
        # token 获取是内部操作，不打扰用户

    def _api_post(self, path: str, body: dict) -> dict:
        self._ensure_token()
        url = f"{self.BASE_URL}/{path}?{self._common_params()}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._access_token}",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {err_body[:300]}") from e

        if result.get("code") != 0:
            raise RuntimeError(f"API 错误: {result.get('message', 'unknown')}")
        return result.get("data", {})

    def _api_get(self, path: str, params: dict = None) -> dict:
        self._ensure_token()
        query = self._common_params()
        if params:
            for k, v in params.items():
                query += f"&{k}={v}"
        url = f"{self.BASE_URL}/{path}?{query}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {err_body[:300]}") from e

        if result.get("code") != 0:
            raise RuntimeError(f"API 错误: {result.get('message', 'unknown')}")
        return result.get("data", {})

    # ── OSS 操作 ──────────────────────────────────────────────

    def _oss_endpoint(self) -> str:
        return self.OSS_ENDPOINT_TEMPLATE.format(
            bucket=self.bucket, region=self.oss_region
        )

    def _oss_sign(self, method: str, object_key: str, headers: dict) -> str:
        """OSS Signature V1"""
        content_type = headers.get("Content-Type", "")
        date = headers.get("Date", "")
        string_to_sign = f"{method}\n\n{content_type}\n{date}\n/{self.bucket}/{object_key}"
        signing_key = hmac.new(
            self.access_key_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
        import base64
        signature = base64.b64encode(signing_key).decode()
        return f"OSS {self.access_key_id}:{signature}"

    def _oss_request(self, method: str, object_key: str, data: bytes = None,
                     content_type: str = "", timeout: int = 300) -> Any:
        date = formatdate(time.time(), usegmt=True)
        headers = {"Date": date}
        if content_type:
            headers["Content-Type"] = content_type
        auth = self._oss_sign(method, object_key, headers)
        headers["Authorization"] = auth

        url = f"https://{self._oss_endpoint()}/{quote(object_key)}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OSS {e.code}: {err_body[:200]}") from e

    def _oss_put(self, object_key: str, data: bytes, content_type: str = "application/octet-stream"):
        resp = self._oss_request("PUT", object_key, data=data, content_type=content_type)
        if resp.status not in (200, 201):
            raise RuntimeError(f"OSS PUT 失败, HTTP {resp.status}")

    def _oss_exists(self, object_key: str) -> bool:
        """HEAD 检查 OSS 对象是否存在，用于跳过重复上传"""
        try:
            self._oss_request("HEAD", object_key)
            return True
        except RuntimeError:
            return False

    def _oss_get(self, object_key: str) -> bytes:
        resp = self._oss_request("GET", object_key)
        return resp.read()

    def _oss_delete(self, object_key: str):
        resp = self._oss_request("DELETE", object_key)
        if resp.status not in (200, 204):
            raise RuntimeError(f"OSS DELETE 失败, HTTP {resp.status}")

    def _oss_presigned_url(self, object_key: str, method: str, expires_sec: int = 172800,
                           content_type: str = "") -> str:
        """生成 OSS 预签名 URL，可指定 Content-Type 用于 PUT 签名"""
        expires = int(time.time()) + expires_sec
        endpoint = self._oss_endpoint()

        # OSS Signature V1 pre-signed URL
        string_to_sign = f"{method}\n\n{content_type}\n{expires}\n/{self.bucket}/{object_key}"
        signing_key = hmac.new(
            self.access_key_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
        import base64
        signature = quote(base64.b64encode(signing_key).decode(), safe="")

        return (
            f"https://{endpoint}/{quote(object_key)}"
            f"?OSSAccessKeyId={self.access_key_id}"
            f"&Expires={expires}"
            f"&Signature={signature}"
        )

    def _upload_to_oss(self, local_path: str, object_key: str):
        """上传本地文件到 OSS（已存在则跳过）"""
        filename = os.path.basename(local_path)
        size = os.path.getsize(local_path)
        if self._oss_exists(object_key):
            _log(f"[无痕AI 2.1] OSS 已存在，跳过上传: {filename}")
            return
        _log(f"[无痕AI 2.1] 上传到 OSS: {filename} ({size/1024/1024:.1f}MB) → {object_key}")
        with open(local_path, "rb") as f:
            self._oss_put(object_key, f.read())
        _log(f"[无痕AI 2.1] OSS 上传完成")
        # 追踪 OSS 用量
        from pricing import oss_tracker
        oss_tracker.track_upload(size)

    def _download_from_oss(self, object_key: str, local_path: str):
        """从 OSS 下载文件"""
        _log(f"[无痕AI 2.1] 从 OSS 下载: {object_key} → {local_path}")
        data = self._oss_get(object_key)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        _log(f"[无痕AI 2.1] 下载完成: {os.path.getsize(local_path)} bytes")
        # 追踪 OSS 用量
        from pricing import oss_tracker
        oss_tracker.track_download(len(data))

    # ── 核心接口 ──────────────────────────────────────────────

    def submit(self, task: WatermarkTask) -> str:
        """
        提交去字幕任务 (V2.1 一步式)

        流程:
        1. 上传文件到 OSS
        2. 生成 video_url (GET预签名) 和 upload_url (PUT预签名)
        3. POST /video_removal
        4. 返回 task_id
        """
        video_path = task.video_path

        # 生成唯一文件名（路径哈希 → 同文件同 key，支持 OSS 去重）
        filename = os.path.basename(video_path)
        base, ext = os.path.splitext(filename)
        fhash = hashlib.md5(video_path.encode()).hexdigest()[:8]
        input_key = f"input/{fhash}_{base}{ext}"
        output_key = f"output/{fhash}_{base}_clean{ext}"

        # Step 1: 上传到 OSS
        t_upload_start = time.time()
        self._upload_to_oss(video_path, input_key)
        t_upload_done = time.time()
        upload_sec = t_upload_done - t_upload_start
        upload_mb = os.path.getsize(video_path) / (1024 * 1024)

        # Step 2: 生成预签名 URL（48小时有效）
        # upload_url 签名必须包含 Content-Type，与 upload_headers 一致
        video_url = self._oss_presigned_url(input_key, "GET", 172800)
        upload_url = self._oss_presigned_url(output_key, "PUT", 172800,
                                             content_type="application/octet-stream")

        # Step 3: 构建请求
        body = {
            "video_url": video_url,
            "upload_url": upload_url,
            "upload_headers": {"Content-Type": "application/octet-stream"},
            "model": self.default_model,
            "method": self.default_method,
        }

        # 如果指定了框选区域（sel_area 模式必须传 rect）
        if self.default_method == "sel_area":
            regions = task.mask_regions
            vid_w, vid_h = self._get_video_resolution(video_path)
            if regions and isinstance(regions[0], dict) and "x" in regions[0]:
                r = regions[0]
                body["rect"] = {
                    "x1": int(r["x"] * vid_w),
                    "y1": int(r["y"] * vid_h),
                    "x2": int((r["x"] + r["w"]) * vid_w),
                    "y2": int((r["y"] + r["h"]) * vid_h),
                }
            else:
                # 无指定区域 → 默认底部 23%（≤480000px rect限制，Seedance 字幕区域）
                body["rect"] = {
                    "x1": 0, "y1": int(vid_h * 0.77),
                    "x2": vid_w, "y2": vid_h,
                }
            _log(f"[无痕AI 2.1] sel_area 框选: {vid_w}x{vid_h} → "
                  f"({body['rect']['x1']},{body['rect']['y1']})-({body['rect']['x2']},{body['rect']['y2']})")

        # Step 4: 提交
        data = self._api_post("video_removal", body)
        task_id = data["task_id"]
        _log(f"[无痕AI 2.1] 任务已提交: {task_id}")

        # 保存映射关系（轮询和下载用）
        if not hasattr(self, "_task_map"):
            self._task_map = {}
        self._task_map[task_id] = {
            "input_key": input_key,
            "output_key": output_key,
            "t_submit": time.time(),
            "upload_sec": upload_sec,
            "upload_mb": upload_mb,
            "clip_name": os.path.basename(video_path),
        }

        return task_id

    def wait_for_result(self, task_id: str, timeout: int = 600, cancel_check=None) -> WatermarkResult:
        """
        轮询任务结果，完成后从 OSS 下载

        状态: queued → processing → complete / failed
        
        cancel_check: 可选回调，返回 True 时取消当前任务并调用 cancel()
        """
        start_time = time.time()
        poll_interval = 5
        task_info = getattr(self, "_task_map", {}).get(task_id, {})
        last_status = None  # 状态变化时才打日志

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return WatermarkResult(
                    success=False,
                    task_id=task_id,
                    error_message=f"任务超时 ({timeout}秒)",
                )

            # 检查取消标志
            if cancel_check and cancel_check():
                if self.cancel(task_id):
                    return WatermarkResult(
                        success=False,
                        task_id=task_id,
                        error_message="用户取消",
                    )
                # 取消失败（任务已开始处理）→ 继续等结果

            try:
                data = self._api_get("status", {"task_id": task_id})
                status = data.get("status", "")
                progress = data.get("progress", 0)

                if status == "success":
                    # 记录子步骤耗时
                    t_result = time.time()
                    api_sec = t_result - task_info.get("t_submit", t_result)
                    
                    # 从 OSS 下载结果
                    output_key = task_info.get("output_key", f"output/{task_id}.mp4")
                    download_path = self._output_path

                    if download_path:
                        t_dl_start = time.time()
                        self._download_from_oss(output_key, download_path)
                        download_sec = time.time() - t_dl_start
                        output = download_path
                    else:
                        download_sec = 0
                        output = self._oss_presigned_url(output_key, "GET", 3600)

                    # 写入操作日志
                    try:
                        from ops_logger import task_detail
                        dl_mb = os.path.getsize(download_path) / (1024*1024) if download_path and os.path.exists(download_path) else 0
                        task_detail(
                            task_info.get("clip_name", ""), task_id,
                            upload_sec=task_info.get("upload_sec", 0),
                            api_sec=api_sec,
                            download_sec=download_sec,
                            upload_mb=task_info.get("upload_mb", 0),
                            download_mb=dl_mb,
                        )
                    except: pass

                    # 清理 OSS 上的输入文件（输出保留供 pipeline 下载）
                    try:
                        input_key = task_info.get("input_key", "")
                        if input_key:
                            self._oss_delete(input_key)
                        # 输出不删，OSS 生命周期 1 天自动清理
                    except Exception:
                        pass

                    return WatermarkResult(
                        success=True,
                        task_id=task_id,
                        output_path=output,
                        metadata={"status": status, "progress": progress},
                    )

                elif status == "failed":
                    return WatermarkResult(
                        success=False,
                        task_id=task_id,
                        error_message=data.get("description", "任务处理失败"),
                    )

                # queued / processing → 继续等待（仅状态变化时打日志）
                current = f"{status}:{progress}"
                if current != last_status:
                    last_status = current
                    status_name = _TASK_STATUS_MAP.get(status, status)
                    progress_str = f", 进度: {progress}" if status == "processing" else f", 排队: {progress}个任务"
                    _log(f"[无痕AI 2.1] 状态: {status_name}{progress_str}")

            except (urllib.error.URLError, OSError) as e:
                _log(f"[无痕AI 2.1] 网络错误: {e}，{poll_interval}秒后重试...")

            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 30)

    def check_health(self) -> bool:
        try:
            self._ensure_token()
            data = self._api_get("user/me")
            balance = data.get("balance", 0)
            _log(f"[无痕AI 2.1] 健康检查通过, 余额: {balance} 积分")
            return True
        except Exception as e:
            _log(f"[无痕AI 2.1] 健康检查失败: {e}")
            return False

    def check_oss(self) -> bool:
        """检查 OSS 是否可用（预检，避免处理到一半才报错）。"""
        try:
            date = formatdate(time.time(), usegmt=True)
            headers = {"Date": date}
            auth = self._oss_sign("GET", "healthcheck", headers)
            headers["Authorization"] = auth
            url = f"https://{self._oss_endpoint()}/"
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
                return resp.status in (200, 403)  # 403 可能是权限但桶存在
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if "UserDisable" in body:
                _log(f"[无痕AI 2.1] ⚠ OSS 桶已被禁用（可能欠费），请登录阿里云控制台处理")
                return False
            return True  # 其他 HTTP 错误可能只是权限问题
        except Exception as e:
            _log(f"[无痕AI 2.1] ⚠ OSS 连接失败: {e}")
            return False

    # ── 批量处理 ──────────────────────────────────────────────

    def process_batch(self, tasks: list[WatermarkTask], timeout: int = 600) -> list[WatermarkResult]:
        """
        批量处理：所有片段一起上传、一起提交、一起等、一起下载。

        GPU 服务器并行处理，总耗时 ≈ 最慢那个片段 + 上传/下载开销。
        不需要 Python 多线程——全部是 HTTP I/O，顺序扔上去就行。

        Returns:
            与 tasks 顺序对应的结果列表
        """
        n = len(tasks)
        _log(f"[无痕AI 2.1] 批量处理 {n} 个片段")

        # ── Phase 1: 上传所有 → OSS ──
        records = []  # [{input_key, output_key, video_path, output_path, task_id?, result?}]
        for i, task in enumerate(tasks):
            video_path = task.video_path
            filename = os.path.basename(video_path)
            base, ext = os.path.splitext(filename)
            fhash = hashlib.md5(video_path.encode()).hexdigest()[:8]
            input_key = f"input/{fhash}_{i}_{base}{ext}"
            output_key = f"output/{fhash}_{i}_{base}_clean{ext}"

            self._upload_to_oss(video_path, input_key)
            records.append({
                "input_key": input_key,
                "output_key": output_key,
                "video_path": video_path,
                "output_path": task.output_path,
                "task_id": None,
                "result": None,
            })

        # ── Phase 2: 提交所有 → 获取 task_id ──
        video_dims = {}  # 缓存视频分辨率，避免重复 ffprobe
        for i, rec in enumerate(records):
            video_path = rec["video_path"]
            task = tasks[i]

            # 获取分辨率（缓存）
            if video_path not in video_dims:
                video_dims[video_path] = self._get_video_resolution(video_path)
            vid_w, vid_h = video_dims[video_path]

            input_key = rec["input_key"]
            output_key = rec["output_key"]

            video_url = self._oss_presigned_url(input_key, "GET", 172800)
            upload_url = self._oss_presigned_url(output_key, "PUT", 172800,
                                                 content_type="application/octet-stream")

            body = {
                "video_url": video_url,
                "upload_url": upload_url,
                "upload_headers": {"Content-Type": "application/octet-stream"},
                "model": self.default_model,
                "method": self.default_method,
            }

            if self.default_method == "sel_area":
                regions = task.mask_regions
                vid_w, vid_h = self._get_video_resolution(task.video_path)
                if regions and isinstance(regions[0], dict) and "x" in regions[0]:
                    r = regions[0]
                    body["rect"] = {
                        "x1": int(r["x"] * vid_w),
                        "y1": int(r["y"] * vid_h),
                        "x2": int((r["x"] + r["w"]) * vid_w),
                        "y2": int((r["y"] + r["h"]) * vid_h),
                    }
                else:
                    body["rect"] = {
                        "x1": 0, "y1": int(vid_h * 0.77),
                        "x2": vid_w, "y2": vid_h,
                    }

            data = self._api_post("video_removal", body)
            rec["task_id"] = data["task_id"]
            _log(f"[无痕AI 2.1] [{i+1}/{n}] 已提交: {rec['task_id']}")

        # ── Phase 3: 一起轮询 ──
        pending = [r for r in records if r["result"] is None]
        start_time = time.time()
        poll_interval = 5

        while pending:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                for rec in pending:
                    rec["result"] = WatermarkResult(
                        success=False,
                        task_id=rec["task_id"],
                        error_message=f"任务超时 ({timeout}秒)",
                    )
                break

            still_pending = []
            for rec in pending:
                try:
                    status_data = self._api_get("status", {"task_id": rec["task_id"]})
                    status = status_data.get("status", "")
                    progress = status_data.get("progress", 0)

                    if status == "success":
                        output_path = rec["output_path"]
                        if output_path:
                            self._download_from_oss(rec["output_key"], output_path)
                            rec["result"] = WatermarkResult(
                                success=True,
                                task_id=rec["task_id"],
                                output_path=output_path,
                                metadata={"status": status, "progress": progress},
                            )
                        else:
                            download_url = self._oss_presigned_url(rec["output_key"], "GET", 3600)
                            rec["result"] = WatermarkResult(
                                success=True,
                                task_id=rec["task_id"],
                                output_path=download_url,
                                metadata={"status": status, "progress": progress},
                            )
                        # 清理 OSS 输入（输出保留供 pipeline 下载）
                        try:
                            self._oss_delete(rec["input_key"])
                        except Exception:
                            pass

                    elif status == "failed":
                        rec["result"] = WatermarkResult(
                            success=False,
                            task_id=rec["task_id"],
                            error_message=status_data.get("description", "任务处理失败"),
                        )
                    else:
                        # queued / processing → 继续等
                        still_pending.append(rec)
                        status_name = _TASK_STATUS_MAP.get(status, status)
                        progress_str = f", {progress}%" if status == "processing" else f", 排队{progress}"
                        # 只在状态变化时打印（避免刷屏）
                        last_status = rec.get("_last_status", "")
                        if status != last_status or (status == "processing" and progress % 20 < 5):
                            _log(f"[无痕AI 2.1] {rec['task_id'][-8:]}: {status_name}{progress_str}")
                            rec["_last_status"] = status

                except (urllib.error.URLError, OSError) as e:
                    still_pending.append(rec)

            pending = still_pending
            if pending:
                done = n - len(pending)
                _log(f"[无痕AI 2.1] 进度: {done}/{n} 完成, {len(pending)} 处理中")
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, 30)

        # ── Phase 4: 返回结果 ──
        results = [rec["result"] for rec in records]
        success_count = sum(1 for r in results if r.success)
        total_elapsed = time.time() - start_time
        _log(f"[无痕AI 2.1] 批量完成: {success_count}/{n} 成功, 总耗时 {total_elapsed:.0f}s")
        return results

    def get_balance(self) -> dict:
        self._ensure_token()
        return self._api_get("user/me")

    def cancel(self, task_id: str) -> bool:
        """取消排队中的任务。不扣积分。已开始处理的任务取消失败。
        Returns: True=取消成功, False=取消失败（可能已开始处理）
        """
        self._ensure_token()
        try:
            self._api_post("cancel", {"task_id": task_id})
            _log(f"[无痕AI 2.1] 任务已取消: {task_id}")
            return True
        except RuntimeError as e:
            _log(f"[无痕AI 2.1] 取消失败: {task_id} — {e}")
            return False
