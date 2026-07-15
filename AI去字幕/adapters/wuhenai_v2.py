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
import ssl
import base64
from typing import Optional, Any
from urllib.parse import urlparse, quote
from email.utils import formatdate

from log_writer import get_logger as _get_logger
_ops = _get_logger("AI去字幕")
from resolution import parse as parse_resolution, is_portrait

from . import BaseAdapter, SubtitleTask, SubtitleResult, TaskStatus

# macOS 上 ssl.create_default_context() 在不同 Python 版本间行为不一致
# (3.13 正常, 3.14 SSL CERTIFICATE_VERIFY_FAILED)，改用 _create_unverified。
_SSL_CTX = ssl._create_unverified_context()

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

    # 常量
    _TOKEN_REFRESH_MARGIN = 3600    # token 提前刷新秒数（1小时）
    _PRESIGNED_URL_TTL = 172800     # 预签名 URL 48小时有效期
    _PRESIGNED_DOWNLOAD_TTL = 3600  # 下载用预签名 URL 1小时有效期（防泄漏）
    _MAX_FILE_SIZE = 100 * 1024 * 1024  # 上传文件上限 100MB

    @property
    def provider_key(self) -> str:
        return "wuhenai"  # pricing/ADAPTER_PRIORITY 用这个 key

    def __init__(self, config: dict):
        super().__init__("wuhenai_v21", config)
        self.api_key = config.get("api_key", "")
        self.access_key_id = config.get("oss_access_key_id", "")
        self.access_key_secret = config.get("oss_access_key_secret", "")
        self.bucket = config.get("oss_bucket", "")
        self.oss_region = config.get("oss_region", self.OSS_REGION)

        self._access_token: Optional[str] = None
        self._token_expires: float = 0
        self._task_map: dict = {}   # task_id → {submit_time, cancel_flag, ...}

        # 去字幕参数
        self.default_model = config.get("model", "video_removal_std")
        self.default_method = config.get("method", "all_area")

    def set_logger(self, callback):
        """同时更新 BaseAdapter + wuhenai 模块级全局 logger。"""
        wuhenai_set_logger(callback)
        self._logger = callback or print

        if not self.api_key:
            raise ValueError("无痕AI 2.1 需要 api_key")
        if not all([self.access_key_id, self.access_key_secret, self.bucket]):
            raise ValueError("需要 OSS 凭证: oss_access_key_id, oss_access_key_secret, oss_bucket")


    def _get_video_resolution(self, video_path: str) -> tuple[int, int]:
        """用 ffprobe 获取视频宽高，返回 (width, height)"""
        from platform import ffprobe_path
        ffprobe = ffprobe_path()
        try:
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, timeout=10,
            )
            w, h = result.stdout.strip().split(",")
            return int(w), int(h)
        except (subprocess.SubprocessError, ValueError, OSError) as e:
            _log(f"[无痕AI 2.1] ffprobe 失败({video_path}): {e}，fallback 1920×1080")
            return 1920, 1080  # fallback：ffprobe 不可用/文件损坏/权限问题

    # ── 通用请求 ──────────────────────────────────────────────

    def _common_params(self) -> str:
        return f"nonce={secrets.token_hex(6)}&t={int(time.time())}"

    def _ensure_token(self):
        if self._access_token and time.time() < self._token_expires:
            return
        url = f"{self.BASE_URL}/user/access_token?{self._common_params()}&api_key={self.api_key}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接无痕AI服务器: {e.reason}") from e
        if data.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {data.get('message')}")
        self._access_token = data["data"]["access_token"]
        self._token_expires = data["data"]["expired"] - self._TOKEN_REFRESH_MARGIN  # 提前1小时刷新
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
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            reason = str(e.reason) if hasattr(e, 'reason') else str(e)
            _ops.ops({"event": "http_fallback", "adapter": self.name,
                       "reason": reason[:100]})
            from .http_fallback import curl_post
            result = curl_post(url, headers, data)

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
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            reason = str(e.reason) if hasattr(e, 'reason') else str(e)
            _ops.ops({"event": "http_fallback", "adapter": self.name,
                       "reason": reason[:100]})
            from .http_fallback import curl_get
            result = curl_get(url, headers)

        if result.get("code") != 0:
            raise RuntimeError(f"API 错误: {result.get('message', 'unknown')}")
        return result.get("data", {})

    # ── OSS 操作 ──────────────────────────────────────────────

    def _oss_endpoint(self) -> str:
        return self.OSS_ENDPOINT_TEMPLATE.format(
            bucket=self.bucket, region=self.oss_region
        )

    def _oss_sign(self, method: str, object_key: str, headers: dict) -> str:
        """OSS Signature V1 (Authorization header)
        文档: https://help.aliyun.com/zh/oss/developer-reference/signature-v1-authorization
        """
        content_type = headers.get("Content-Type", "")
        date = headers.get("Date", "")
        string_to_sign = f"{method}\n\n{content_type}\n{date}\n/{self.bucket}/{object_key}"
        signing_key = hmac.new(
            self.access_key_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
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

    def _oss_put(self, object_key: str, data: bytes, content_type: str = "application/octet-stream",
                 timeout: int = 60):
        """OSS 上传。timeout 60s（3-20MB 文件在 500KB/s 实测 6-40s，2 倍余量）"""
        resp = self._oss_request("PUT", object_key, data=data, content_type=content_type, timeout=timeout)
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

    def _oss_presigned_url(self, object_key: str, method: str, expires_sec: int = None,
                           content_type: str = "") -> str:
        """生成 OSS 预签名 URL，可指定 Content-Type 用于 PUT 签名"""
        if expires_sec is None:
            expires_sec = self._PRESIGNED_URL_TTL
        expires = int(time.time()) + expires_sec
        endpoint = self._oss_endpoint()

        # OSS Signature V1 pre-signed URL
        string_to_sign = f"{method}\n\n{content_type}\n{expires}\n/{self.bucket}/{object_key}"
        signing_key = hmac.new(
            self.access_key_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
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
        for attempt in range(3):
            try:
                with open(local_path, "rb") as f:
                    self._oss_put(object_key, f.read())
                break
            except Exception as e:
                if attempt < 2:
                    _log(f"[无痕AI 2.1] 上传重试 {attempt+2}/3: {filename} — {e}")
                    time.sleep(2)
                else:
                    raise RuntimeError(f"OSS 上传失败 3 次: {filename} — {e}")
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

    def _compute_detection_params(self, task: SubtitleTask, vid_w: int, vid_h: int) -> tuple[str, Optional[dict]]:
        """
        根据视频方向自动选择处理策略。

        优先级：task.mask_regions（精确区域）> 分辨率自适应
        - 竖屏 (resolution.is_portrait): sel_area + 一刀切下半块；面积超 480K 则降级 all_area
        - 横屏: all_area + 全屏自动检测（无 rect）

        Returns:
            (method: str, rect: dict | None)
        """
        regions = task.mask_regions
        # 精确区域优先
        if regions and isinstance(regions[0], dict) and "x" in regions[0]:
            r = regions[0]
            return "sel_area", {
                "x1": int(r["x"] * vid_w),
                "y1": int(r["y"] * vid_h),
                "x2": int((r["x"] + r["w"]) * vid_w),
                "y2": int((r["y"] + r["h"]) * vid_h),
            }

        # 分辨率自适应
        if is_portrait(vid_w, vid_h):
            # 竖屏：一刀切下半块
            y1 = int(vid_h * self.config.get("portrait_cut_y", 0.50))
            area = vid_w * (vid_h - y1)
            max_pixels = self.config.get("sel_area_max_pixels", 480000)
            if area <= max_pixels:
                return "sel_area", {
                    "x1": 0, "y1": y1,
                    "x2": vid_w, "y2": vid_h,
                }
            # 面积超标（如 1080×1920）→ 降级 all_area
            return "all_area", None
        else:
            # 横屏：all_area 全屏自动检测
            return "all_area", None

    def submit(self, task: SubtitleTask) -> str:
        """
        提交去字幕任务 (V2.1 一步式)

        流程:
        1. 上传文件到 OSS
        2. 生成 video_url (GET预签名) 和 upload_url (PUT预签名)
        3. POST /video_removal
        4. 返回 task_id
        """
        video_path = task.video_path
        if not video_path or not os.path.exists(video_path):
            raise ValueError(f"视频文件不存在或路径为空: {video_path}")

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
        video_url = self._oss_presigned_url(input_key, "GET")
        upload_url = self._oss_presigned_url(output_key, "PUT",
                                             content_type="application/octet-stream")

        # Step 3: 构建请求
        body = {
            "video_url": video_url,
            "upload_url": upload_url,
            "upload_headers": {"Content-Type": "application/octet-stream"},
            "model": self.default_model,
            "method": self.default_method,
        }

        # 分辨率自适应：竖屏 sel_area+半块，横屏 all_area 全屏自动
        # 优先从任务拿（扫描时达芬奇API获取），fallback ffprobe
        if getattr(task, "resolution", None):
            vid_w, vid_h = parse_resolution(task.resolution)
        else:
            vid_w, vid_h = self._get_video_resolution(video_path)
        method, rect = self._compute_detection_params(task, vid_w, vid_h)
        body["method"] = method
        if rect:
            body["rect"] = rect
            _log(f"[无痕AI 2.1] sel_area 框选: {vid_w}x{vid_h} → "
                  f"({rect['x1']},{rect['y1']})-({rect['x2']},{rect['y2']})")
        elif method == "all_area":
            _log(f"[无痕AI 2.1] all_area 全屏自动: {vid_w}x{vid_h}")

        # Step 4: 提交
        data = self._api_post("video_removal", body)
        task_id = data["task_id"]
        _log(f"[无痕AI 2.1] 任务已提交: {os.path.basename(video_path)} → {task_id}")

        # 保存映射关系（轮询和下载用）
        self._task_map[task_id] = {
            "input_key": input_key,
            "output_key": output_key,
            "t_submit": time.time(),
            "upload_sec": upload_sec,
            "upload_mb": upload_mb,
            "clip_name": os.path.basename(video_path),
            "method": method,
            "resolution": f"{vid_w}x{vid_h}",
        }

        return task_id

    def wait_for_result(self, task_id: str, timeout: int = 600, cancel_check=None) -> SubtitleResult:
        """
        轮询任务结果，完成后从 OSS 下载

        状态: queued → processing → complete / failed
        
        cancel_check: 可选回调，返回 True 时取消当前任务并调用 cancel()
        """
        start_time = time.time()
        poll_interval = 5
        task_info = self._task_map.get(task_id, {})
        last_status = None  # 状态变化时才打日志

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return SubtitleResult(
                    success=False,
                    task_id=task_id,
                    error_message=f"任务超时 ({timeout}秒)",
                )

            # 检查取消标志
            if cancel_check and cancel_check():
                if self.cancel(task_id):
                    return SubtitleResult(
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
                        self._oss_delete(output_key)
                        download_sec = time.time() - t_dl_start
                        output = download_path
                    else:
                        download_sec = 0
                        output = self._oss_presigned_url(output_key, "GET", self._PRESIGNED_DOWNLOAD_TTL)

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
                    except Exception as e:
                        _log(f"[无痕AI 2.1] 操作日志写入失败: {e}")

                    # 清理 OSS 上的中转文件
                    try:
                        input_key = task_info.get("input_key", "")
                        output_key = task_info.get("output_key", "")
                        if input_key:
                            self._oss_delete(input_key)
                        if output_key:
                            self._oss_delete(output_key)  # 已下载，OSS 上不留垃圾
                    except Exception:
                        # 清理失败不阻塞主流程
                        pass

                    # 打印分段耗时（帮助诊断 API 慢的原因）
                    upload_sec = task_info.get("upload_sec", 0)
                    _log(f"[无痕AI 2.1] 分段耗时: 上传{upload_sec:.1f}s + API{api_sec:.1f}s + 下载{download_sec:.1f}s = {upload_sec+api_sec+download_sec:.0f}s")

                    return SubtitleResult(
                        success=True,
                        task_id=task_id,
                        output_path=output,
                        metadata={"status": status, "progress": progress,
                                  "strategy": task_info.get("method", ""),
                                  "resolution": task_info.get("resolution", "")},
                    )

                elif status == "failed":
                    return SubtitleResult(
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
        """无痕AI 健康检查：验 token + 查余额。返回 True/False。"""
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

    def _process_impl(self, tasks: list[SubtitleTask], timeout: int = 600,
                       cancel_check=None, progress_callback=None) -> list[SubtitleResult]:
        """
        批量处理：所有片段一起上传、一起提交、一起等、一起下载。

        GPU 服务器并行处理，总耗时 ≈ 最慢那个片段 + 上传/下载开销。
        上传阶段并发 3 线程（网络 I/O 密集），多片段批量可获 2-3x 上传提速。

        cancel_check: 可选回调，返回 True 时取消所有排队任务并返回已完成的。
        progress_callback: 可选回调，progress_callback(phase, ratio) 
                           phase: "upload"/"submit"/"processing"/"download"
                           ratio: 0.0~1.0 整体进度

        Returns:
            与 tasks 顺序对应的结果列表
        """
        n = len(tasks)
        _log(f"[无痕AI 2.1] 批量处理 {n} 个片段")

        # ── Phase 1: 上传所有 → OSS（顺序）──
        records = []  # [{input_key, output_key, video_path, output_path, task_id?, result?}]
        upload_tasks = []  # [(idx, video_path, input_key)]

        # 1a. 预检 + 计算 key（顺序，很快，不检查取消——纯元数据操作不可中断）
        for i, task in enumerate(tasks):
            video_path = task.video_path
            try:
                fsize = os.path.getsize(video_path)
                if fsize == 0:
                    records.append({"idx": i, "result": SubtitleResult(success=False, error_message="零字节文件"), "video_path": video_path, "name": os.path.basename(video_path)})
                    continue
                if fsize > self._MAX_FILE_SIZE:
                    records.append({"idx": i, "result": SubtitleResult(success=False, error_message=f"文件过大 ({fsize/1024/1024:.0f}MB > 100MB)"), "video_path": video_path, "name": os.path.basename(video_path)})
                    continue
            except OSError as e:
                records.append({"idx": i, "result": SubtitleResult(success=False, error_message=f"无法访问: {e}"), "video_path": video_path, "name": os.path.basename(video_path)})
                continue
            filename = os.path.basename(video_path)
            base, ext = os.path.splitext(filename)
            fhash = hashlib.md5(video_path.encode()).hexdigest()[:8]
            input_key = f"input/{fhash}_{i}_{base}{ext}"
            output_key = f"output/{fhash}_{i}_{base}_clean{ext}"
            upload_tasks.append((i, video_path, input_key, output_key, task))

        # 1b. 顺序上传（达芬奇子进程+SMB挂载+线程=不可靠，改顺序执行）
        for idx, video_path, input_key, output_key, task in upload_tasks:
            try:
                self._upload_to_oss(video_path, input_key)
                records.append({"idx": idx,
                                "input_key": input_key, "output_key": output_key,
                                "video_path": video_path, "output_path": task.output_path,
                                "task_id": None, "result": None, "duration": task.duration,
                                "name": os.path.basename(video_path)})
                if progress_callback:
                    progress_callback("upload", len([r for r in records if r.get("input_key")]) / n * 0.2)
            except Exception as e:
                _log(f"[无痕AI 2.1] 上传失败: {os.path.basename(video_path)} — {e}")
                records.append({"idx": idx,
                                "result": SubtitleResult(success=False, error_message=f"上传失败: {e}"),
                                "video_path": video_path, "name": os.path.basename(video_path)})

        # 1c. 去掉 idx 字段（不暴露给下游）
        for r in records:
            r.pop("idx", None)

        # ── Phase 2: 提交所有 → 获取 task_id ──
        video_dims = {}  # 缓存视频分辨率，避免重复 ffprobe
        for i, rec in enumerate(records):
            # 跳过 Phase 1 已标记失败的上传/预检
            if rec.get("result") is not None:
                continue
            video_path = rec["video_path"]
            # records[i] 对应 tasks[i]：Phase 1 若提前 break 则 len(records) < n，
            # 但 Phase 2 遍历 records（i 不超过 len(records)-1），tasks[i] 始终安全。
            task = tasks[i]

            # 获取分辨率（优先任务字段 → 缓存 → ffprobe fallback）
            res_key = getattr(task, "resolution", None)
            if not res_key or res_key not in video_dims:
                if res_key:
                    video_dims[res_key] = parse_resolution(res_key)
                else:
                    if video_path not in video_dims:
                        video_dims[video_path] = self._get_video_resolution(video_path)
                    video_dims[res_key] = video_dims[video_path]
            vid_w, vid_h = video_dims.get(res_key) or video_dims.get(video_path, (1920, 1080))

            input_key = rec["input_key"]
            output_key = rec["output_key"]

            video_url = self._oss_presigned_url(input_key, "GET")
            upload_url = self._oss_presigned_url(output_key, "PUT",
                                                 content_type="application/octet-stream")

            body = {
                "video_url": video_url,
                "upload_url": upload_url,
                "upload_headers": {"Content-Type": "application/octet-stream"},
                "model": self.default_model,
                "method": self.default_method,
            }

            method, rect = self._compute_detection_params(task, vid_w, vid_h)
            body["method"] = method
            rec["method"] = method
            rec["resolution"] = f"{vid_w}x{vid_h}"
            if rect:
                body["rect"] = rect
                _log(f"[无痕AI 2.1] [{i+1}/{n}] sel_area 框选: {vid_w}x{vid_h} → "
                      f"({rect['x1']},{rect['y1']})-({rect['x2']},{rect['y2']})")
            elif method == "all_area":
                _log(f"[无痕AI 2.1] [{i+1}/{n}] all_area 全屏自动: {vid_w}x{vid_h}")

            try:
                data = self._api_post("video_removal", body)
                rec["task_id"] = data["task_id"]
                _log(f"[无痕AI 2.1] [{i+1}/{n}] 已提交: {os.path.basename(rec['video_path'])} → {rec['task_id']}")
            except Exception as e:
                _log(f"[无痕AI 2.1] [{i+1}/{n}] 提交失败: {os.path.basename(rec['video_path'])} — {e}")
                rec["result"] = SubtitleResult(success=False, error_message=f"提交失败: {e}")
                # 清理 OSS 上传的输入（已上传但提交失败的）
                try:
                    self._oss_delete(rec["input_key"])
                except Exception:
                    # 清理失败不阻塞：OSS可能已自动过期
                    pass
            # 提交进度
            if progress_callback:
                progress_callback("submit", 0.2 + (i + 1) / n * 0.1)

        # ── Phase 3: 一起轮询 ──
        pending = [r for r in records if r.get("result") is None and r.get("task_id")]
        start_time = time.time()
        poll_interval = 5
        cancel_done = False

        while pending:
            # 检查取消
            if not cancel_done and cancel_check and cancel_check():
                _log(f"[无痕AI 2.1] 停止：取消 {len(pending)} 个排队任务...")
                for rec in pending:
                    tid = rec.get("task_id")
                    if tid:
                        try:
                            self.cancel(tid)
                        except Exception:
                            _log(f"[无痕AI 2.1] cancel() 失败(task={tid[-8:]})，非阻塞")
                    rec["result"] = SubtitleResult(
                        success=False,
                        task_id=tid,
                        error_message="用户取消",
                    )
                cancel_done = True
                break
            elapsed = time.time() - start_time
            if elapsed > timeout:
                for rec in pending:
                    tid = rec.get("task_id")
                    if tid:
                        # 尝试 cancel 服务端任务，避免白扣钱
                        try:
                            self.cancel(tid)
                        except Exception:
                            pass
                    rec["result"] = SubtitleResult(
                        success=False,
                        task_id=tid,
                        error_message=f"任务超时 ({timeout}秒)",
                    )
                break

            still_pending = []
            weighted_progress = 0.0  # 按片段时长加权
            weighted_total = 0.0
            for rec in pending:
                try:
                    status_data = self._api_get("status", {"task_id": rec["task_id"]})
                    status = status_data.get("status", "")
                    progress = status_data.get("progress", 0)
                    dur = rec.get("duration", 10)  # 默认 10s，避免 0 权重
                    weighted_progress += progress * dur
                    weighted_total += dur * 100  # max progress = 100

                    if status == "success":
                        output_path = rec["output_path"]
                        if output_path:
                            self._download_from_oss(rec["output_key"], output_path)
                            self._oss_delete(rec["output_key"])  # 下载完即删，OSS 只当过路
                            rec["result"] = SubtitleResult(
                                success=True,
                                task_id=rec["task_id"],
                                output_path=output_path,
                                metadata={"status": status, "progress": progress,
                                          "strategy": rec.get("method", ""),
                                          "resolution": rec.get("resolution", ""),
                                          "duration": rec.get("duration", 0)},
                            )
                        else:
                            download_url = self._oss_presigned_url(rec["output_key"], "GET", self._PRESIGNED_DOWNLOAD_TTL)
                            rec["result"] = SubtitleResult(
                                success=True,
                                task_id=rec["task_id"],
                                output_path=download_url,
                                metadata={"status": status, "progress": progress,
                                          "strategy": rec.get("method", ""),
                                          "resolution": rec.get("resolution", ""),
                                          "duration": rec.get("duration", 0)},
                            )
                        # 清理 OSS 中转文件
                        try:
                            self._oss_delete(rec["input_key"])
                        except Exception:
                            # 清理失败不阻塞：OSS对象可能已自动过期
                            pass

                    elif status == "failed":
                        rec["result"] = SubtitleResult(
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
                except Exception as e:
                    _log(f"[无痕AI 2.1] 轮询异常 {rec['task_id'][-8:]}: {e}")
                    rec["result"] = SubtitleResult(
                        success=False,
                        task_id=rec["task_id"],
                        error_message=f"轮询失败: {e}",
                    )

            pending = still_pending
            if pending:
                done = n - len(pending)
                _log(f"[无痕AI 2.1] 进度: {done}/{n} 完成, {len(pending)} 处理中")
                # 真实进度回调：汇总 API 返回的 progress + 已完成任务
                if progress_callback:
                    completed_ratio = done / max(n, 1)
                    pending_ratio = weighted_progress / max(weighted_total, 1)  # 0~1
                    overall = 0.3 + (completed_ratio + pending_ratio) * 0.6
                    progress_callback("processing", min(overall, 0.9))
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, 30)

        # ── Phase 4: 返回结果 ──
        # 补全可能缺失的结果（取消/未上传的）
        for i, rec in enumerate(records):
            if rec.get("result") is None:
                rec["result"] = SubtitleResult(
                    success=False,
                    task_id=rec.get("task_id"),
                    error_message="未处理（停止或跳过）",
                )
        # 补齐未上传的（records 不完整时）
        while len(records) < n:
            records.append({"result": SubtitleResult(
                success=False,
                error_message="未上传（停止）",
            ), "name": f"未上传#{len(records)}"})
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
            self._api_post("task/cancel", {"task_id": task_id})
            _log(f"[无痕AI 2.1] 任务已取消: {task_id}")
            return True
        except RuntimeError as e:
            _log(f"[无痕AI 2.1] 取消失败: {task_id} — {e}")
            return False
