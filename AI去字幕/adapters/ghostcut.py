"""
鬼手剪辑 (GhostCut) 适配器

API 文档: https://jollytoday.feishu.cn/docx/U73qdBhWbozFdpx4eTvcIO4gn7e
Base URL: https://api.zhaoli.com
认证: AppKey + AppSign (双重 MD5 签名)
交互: 异步任务 + 轮询

依赖: 仅 Python 标准库（urllib + hashlib + json + os + time）
      全国几千个剪辑师拿到就能跑，零 pip install
"""

import hashlib
import json
import os
import secrets
import ssl
import time
import urllib.request
import urllib.error

from log_writer import get_logger
_log_ops = get_logger("AI去字幕")
from typing import Optional
from urllib.parse import urlparse

from . import BaseAdapter, SubtitleTask, SubtitleResult, TaskStatus

# macOS 上 ssl.create_default_context() 在不同 Python 版本间行为不一致
# (3.13 正常, 3.14 SSL CERTIFICATE_VERIFY_FAILED)，改用 _create_unverified。
_SSL_CTX = ssl._create_unverified_context()

_RESOLUTION_MAP = {
    "1920x1080": "1080p", "1080x1920": "1080p",
    "1280x720":  "720p",  "720x1280":  "720p",
    "854x480":   "480p",  "480x854":   "480p",
    "640x480":   "480p",  "480x640":   "480p",
}

def _get_resolution(task: SubtitleTask) -> str:
    """返回 GhostCut API 的 resolution 字段（1080p/720p）。
    优先 task.resolution，fallback ffprobe，最后默认 1080p。
    """
    if task.resolution:
        for k, v in _RESOLUTION_MAP.items():
            if task.resolution in k or k in task.resolution:
                return v
    try:
        from platform import ffprobe_path
        import subprocess
        ffprobe = ffprobe_path()
        r = subprocess.run(
            [ffprobe, "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", task.video_path],
            capture_output=True, text=True, timeout=10)
        w, h = r.stdout.strip().split(",")
        res_key = f"{w}x{h}"
        for k, v in _RESOLUTION_MAP.items():
            if res_key in k or k in res_key:
                return v
    except Exception:
        pass
    return "1080p"


def _auto_mask(task: SubtitleTask):
    """根据分辨率自动选择鬼手处理策略（参考无痕AI设计）。

    Returns:
        (model_name: str, masks: list | None, cut_y: float | None)
    """
    from resolution import parse as _parse_res, is_portrait

    if task.resolution:
        w, h = _parse_res(task.resolution)
    else:
        # fallback: 假设竖屏（Seedance 默认）
        w, h = 720, 1280

    # 鬼手字幕擦除仅两档：Lite版(basic) 和 Pro版·框选(pro_box)
    # 无 pro_large/pro 全屏档——统一用 pro_box，mask 大小不影响计费
    cut_y = 0.50  # 底部 50%，覆盖竖屏字幕(>90%)和横屏字幕(57-80%)
    return "pro_box", [{"type": "remove_only_ocr",
                         "region": [[0, cut_y], [1, cut_y], [1, 1.0], [0, 1.0]]}], cut_y


class GhostCutAdapter(BaseAdapter):
    """鬼手去字幕适配器"""

    BASE_URL = "https://api.zhaoli.com"
    CREATE_TASK = "/v-w-c/gateway/ve/work/free"
    CHECK_STATUS = "/v-w-c/gateway/ve/work/status"
    UPLOAD_POLICY = "/v-w-c/gateway/ve/file/upload/policy/apply"
    
    # 擦除模型映射
    MODEL_MAP = {
        "basic": "",                     # 快速模式（测试用，无额外参数）
        "pro": "advanced_full",          # 精修 Pro（全屏）
        "pro_box": "advanced",           # 精修 Pro（小框）
        "pro_large": "advanced_large_box", # 精修 Pro（大框）
    }

    def __init__(self, config: dict):
        super().__init__("ghostcut", config)
        self.app_key = config.get("app_key")
        self.app_secret = config.get("app_secret")
        self.default_model = config.get("model", "pro")
        self._crf = config.get("crf")  # None=默认17, 15=更高画质
        
        if not self.app_key or not self.app_secret:
            raise ValueError(f"{self.name} 适配器需要 app_key 和 app_secret")

    def _build_extra_options(self, extra_inpaint_config: dict) -> str:
        """构建 extraOptions JSON。CRF 开关：None=跳过, 15=高画质。"""
        opts = {"extra_inpaint_config": extra_inpaint_config}
        if self._crf is not None:
            opts["write_options"] = {"crf": self._crf}
        return json.dumps(opts)

    def _sign(self, body: dict) -> str:
        """双重 MD5 签名: md5(md5(body_json) + AppSecret)"""
        body_str = json.dumps(body, ensure_ascii=False)
        body_md5 = hashlib.md5(body_str.encode()).hexdigest()
        return hashlib.md5((body_md5 + self.app_secret).encode()).hexdigest()

    def _api_post(self, path: str, payload: dict) -> dict:
        """带签名的 API POST 请求（urllib，SSL 失败时 curl fallback）"""
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "AppKey": self.app_key,
            "AppSign": self._sign(payload),
        }
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            data=body_bytes,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {body[:200]}") from e
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            # SSL/网络错误 → curl fallback
            reason = str(e.reason) if hasattr(e, 'reason') else str(e)
            _log_ops.ops({"event": "http_fallback", "adapter": self.name,
                           "reason": reason[:100]})
            from http_fallback import curl_post
            return curl_post(f"{self.BASE_URL}{path}", headers, body_bytes)

    def submit(self, task: SubtitleTask) -> str:
        """
        提交去字幕任务
        
        自动处理本地文件上传：如果 video_path 是本地文件，
        自动上传到 GhostCut OSS 获取临时 URL 后再提交任务。
        """
        # video_path 前置校验（与 wuhenai 对齐）
        if not task.video_path or not task.video_path.strip():
            raise ValueError("video_path 为空")
        if not os.path.exists(task.video_path):
            raise FileNotFoundError(f"文件不存在: {task.video_path}")
        fsize = os.path.getsize(task.video_path)
        if fsize == 0:
            raise ValueError("零字节文件")
        if fsize > 500 * 1024 * 1024:
            raise ValueError(f"文件过大 ({fsize/1024/1024:.0f}MB > 500MB)")
        
        video_url = task.video_path
        
        parsed = urlparse(video_url)
        if not parsed.scheme.startswith("http"):
            # 本地文件 → 自动上传
            self._log("info", f"检测到本地文件，自动上传: {os.path.basename(video_url)}")
            video_url = self._upload_file(video_url)
            self._log("info", f"上传完成: {video_url}")
        
        model_name = task.model or self.default_model
        # 分辨率自适应 mask（参考无痕AI设计）
        auto_model, auto_masks, _ = _auto_mask(task) if not task.mask_regions else (model_name, task.mask_regions, None)
        if not task.mask_regions:
            task.mask_regions = auto_masks
            model_name = auto_model
        
        base_name = os.path.splitext(os.path.basename(task.video_path))[0] if task.video_path else "unknown"
        resolution = _get_resolution(task)
        
        if model_name == "basic":
            payload = {
                "urls": [video_url],
                "names": [base_name],
                "resolution": resolution,
                "needChineseOcclude": 3,
                "videoInpaintLang": task.language,
            }
        elif model_name in ("pro_box", "pro_large"):
            # Pro 框选：必须传 mask, needChineseOcclude=2, lang=zh
            masks = task.mask_regions
            if not masks:
                raise ValueError(f"{model_name} 模式必须指定 mask_regions")
            model_value = self.MODEL_MAP.get(model_name, "advanced")
            payload = {
                "urls": [video_url],
                "names": [base_name],
                "resolution": resolution,
                "needChineseOcclude": 2,
                "videoInpaintLang": task.language,
                "videoInpaintMasks": json.dumps(masks),
                "extraOptions": self._build_extra_options({"model": model_value}),
            }
        else:  # pro — 全屏精修
            payload = {
                "urls": [video_url],
                "names": [base_name],
                "resolution": resolution,
                "needChineseOcclude": 1,
                "videoInpaintLang": task.language,
                "extraOptions": self._build_extra_options({"model": "advanced_full"}),
            }
        
        resp = self._api_post(self.CREATE_TASK, payload)
        
        # 解析任务ID
        try:
            work_id = resp["body"]["dataList"][0]["id"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"鬼手 返回异常: {json.dumps(resp, ensure_ascii=False)}") from e
        
        return str(work_id)

    def _upload_file(self, local_path: str) -> str:
        """
        上传本地文件到 GhostCut OSS，返回临时下载 URL
        
        使用纯 urllib 构建 multipart/form-data，不依赖 requests 库。
        上传流程：
        1. 获取上传凭证 (policy)
        2. 手动构建 multipart body 直传文件到 OSS
        3. 拼接 CDN URL 返回
        
        注意：URL 有效期会员 30 天，非会员 14 天
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        # 大文件保护：短剧片段通常 < 500MB，超过则警告但不阻断
        file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
        if file_size_mb > 500:
            self._log("warn", f"文件较大 ({file_size_mb:.0f}MB)，上传可能耗时较长")
        
        filename = os.path.basename(local_path)
        
        # Step 1: 获取上传凭证
        nonce = secrets.token_hex(16)
        policy_resp = self._api_post(self.UPLOAD_POLICY, {
            "nonce": nonce,
            "materialFileType": "video",
        })
        
        policy = policy_resp["body"]
        
        # Step 2: 读取文件 + 手动构建 multipart/form-data
        with open(local_path, "rb") as f:
            file_data = f.read()
        
        boundary = "--GhostCut" + secrets.token_hex(16)
        
        # OSS 表单字段（字符串类型）
        form_fields = [
            ("key", policy["dir"] + filename),
            ("OSSAccessKeyId", policy["accessid"]),
            ("policy", policy["policy"]),
            ("signature", policy["signature"]),
            ("callback", policy["base64CallbackBody"]),
            ("success_action_status", "200"),
        ]
        
        # 构建 multipart body
        body_parts = []
        for name, value in form_fields:
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n".encode("utf-8")
            )
        
        # 文件字段
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n".encode("utf-8")
        )
        body_parts.append(file_data)
        body_parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        
        body_data = b"".join(body_parts)
        
        req = urllib.request.Request(
            policy["host"],
            data=body_data,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
            resp_text = resp.read().decode()
        
        if resp_text.strip() != '{"Status":"OK"}':
            raise RuntimeError(f"文件上传失败: {resp_text}")
        
        # Step 3: 拼接 CDN URL
        cdn_url = policy["urlPrefix"] + filename
        return cdn_url

    def wait_for_result(self, task_id: str, timeout: int = 300, cancel_check=None) -> SubtitleResult:
        """
        轮询任务结果
        
        processStatus 含义:
          1  = 成功
          >1 = 失败
          0/-1 = 处理中
        
        cancel_check: 可选回调，返回 True 时取消任务并返回取消结果
        """
        start_time = time.time()
        poll_interval = 5  # 首次快速轮询
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return SubtitleResult(
                    success=False,
                    task_id=task_id,
                    error_message=f"任务超时 ({timeout}秒)"
                )

            # 检查取消标志 (与 wuhenai_v2 对齐)
            if cancel_check and cancel_check():
                try:
                    self.cancel(task_id)
                except Exception:
                    self._log("warn", f"cancel() 失败(task={task_id[-8:]})，非阻塞")
                return SubtitleResult(
                    success=False,
                    task_id=task_id,
                    error_message="用户取消",
                )
            
            try:
                resp = self._api_post(self.CHECK_STATUS, {"idWorks": [int(task_id)]})
                content = resp["body"]["content"][0]
                status = content["processStatus"]
                
                if status == 1:
                    # 成功
                    video_url = content.get("videoUrl", "") or ""
                    
                    # 如果指定了 output_path，自动下载
                    download_path = self._output_path
                    if download_path and video_url:
                        self._log("debug", f"下载处理结果到: {download_path}")
                        with urllib.request.urlopen(video_url, context=_SSL_CTX, timeout=120) as resp:
                            with open(download_path, 'wb') as f:
                                while True:
                                    chunk = resp.read(8192)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                    
                    return SubtitleResult(
                        success=True,
                        task_id=task_id,
                        output_path=download_path or video_url,
                        metadata={
                            "video_url": video_url,
                            "name": content.get("name", ""),
                            "duration": content.get("duration", 0),
                        }
                    )
                elif status > 1:
                    # 失败
                    return SubtitleResult(
                        success=False,
                        task_id=task_id,
                        error_message=content.get("errorDetail", f"处理失败，状态码: {status}")
                    )
                # else: status == 0 或 -1，继续等待
                
            except (urllib.error.URLError, OSError) as e:
                # 网络错误不立即失败，重试
                self._log("warn", f"网络错误: {e}，{poll_interval}秒后重试...")
            
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 30)  # 逐渐拉长到30秒

    def _process_impl(self, tasks: list, timeout: int = 300,
                       cancel_check=None, progress_callback=None) -> list:
        """
        批量处理：上传全部 → 一次提交 → 一起轮询 → 逐个下载。

        GhostCut API 原生支持：
        - urls[] 接受多文件
        - idWorks[] 接受多任务查询
        总耗时 ≈ 最慢那个片段 + 上传开销（GPU 并行）。

        Args:
            tasks: [SubtitleTask, ...]
            timeout: 总超时（秒）
            cancel_check: 可选回调，返回 True 时取消所有排队任务

        Returns:
            与 tasks 顺序对应的 [SubtitleResult, ...]
        """
        n = len(tasks)
        self._log("info", f"批量处理 {n} 个片段")

        # ── Phase 1: 上传所有文件 → CDN URLs ──
        records = []
        for i, task in enumerate(tasks):
            if cancel_check and cancel_check():
                self._log("warn", f"上传阶段收到停止，已上传 {i}/{n}")
                break
            video_url = task.video_path
            parsed = urlparse(video_url)
            if not parsed.scheme.startswith("http"):
                base = os.path.basename(video_url)
                self._log("info", f"[{i+1}/{n}] 上传: {base}")
                try:
                    video_url = self._upload_file(video_url)
                except Exception as e:
                    self._log("error", f"上传失败: {base} — {e}")
                    records.append({
                        "video_url": "",
                        "base_name": base,
                        "task": task,
                        "task_id": None,
                        "result": SubtitleResult(success=False, error_message=f"上传失败: {e}"),
                    })
                    continue
            base_name = os.path.splitext(os.path.basename(task.video_path))[0] if task.video_path else f"clip_{i}"
            records.append({
                "video_url": video_url,
                "base_name": base_name,
                "task": task,
                "task_id": None,
                "result": None,
            })
        self._log("info", "上传完成")
        if progress_callback:
            progress_callback("upload", 0.2)

        # ── Phase 2: 一次提交所有任务 ──
        if cancel_check and cancel_check():
            self._log("warn", "提交阶段收到停止")
            # 补齐未提交的结果
            for rec in records:
                if rec.get("result") is None:
                    rec["result"] = SubtitleResult(success=False, error_message="用户取消（未提交）")
            return [r.get("result", SubtitleResult(success=False)) for r in records]

        model_name = self.default_model
        # 分辨率自适应（取第一个任务的mask，批量统一策略）
        if tasks and not tasks[0].mask_regions:
            auto_model, auto_masks, _ = _auto_mask(tasks[0])
            for t in tasks:
                t.mask_regions = auto_masks
            model_name = auto_model
        
        urls = [r["video_url"] for r in records]
        names = [r["base_name"] for r in records]
        resolution = _get_resolution(tasks[0]) if tasks else "1080p"

        if model_name == "basic":
            payload = {
                "urls": urls,
                "names": names,
                "resolution": resolution,
                "needChineseOcclude": 3,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
            }
        elif model_name in ("pro_box", "pro_large"):
            masks = tasks[0].mask_regions if tasks else None
            if not masks:
                masks = [{"type": "remove_only_ocr",
                          "region": [[0, 0.50], [1, 0.50], [1, 1.0], [0, 1.0]]}]
            model_value = self.MODEL_MAP.get(model_name, "advanced")
            payload = {
                "urls": urls,
                "names": names,
                "resolution": resolution,
                "needChineseOcclude": 2,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
                "videoInpaintMasks": json.dumps(masks),
                "extraOptions": self._build_extra_options({"model": model_value}),
            }
        elif model_name == "pro":
            payload = {
                "urls": urls,
                "names": names,
                "resolution": resolution,
                "needChineseOcclude": 1,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
                "extraOptions": self._build_extra_options({"model": "advanced_full"}),
            }
        else:  # pro — 全屏精修
            payload = {
                "urls": urls,
                "names": names,
                "resolution": resolution,
                "needChineseOcclude": 1,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
                "extraOptions": self._build_extra_options({"model": "advanced_full"}),
            }

        resp = self._api_post(self.CREATE_TASK, payload)
        data_list = resp["body"]["dataList"]

        if len(data_list) != n:
            self._log("warn", f"返回 {len(data_list)} 个任务，期望 {n} 个")

        for i, item in enumerate(data_list):
            if i < len(records):
                records[i]["task_id"] = str(item["id"])
        self._log("info", f"已提交 {len(data_list)} 个任务，等待处理...")

        # ── Phase 3: 一起轮询 ──
        all_ids = [int(r["task_id"]) for r in records if r["task_id"]]
        start_time = time.time()
        poll_interval = 5
        pending_ids = set(all_ids)
        id_to_idx = {int(r["task_id"]): i for i, r in enumerate(records) if r["task_id"]}

        while pending_ids:
            # 检查取消
            if cancel_check and cancel_check():
                self._log("warn", f"停止：取消 {len(pending_ids)} 个排队任务...")
                for tid in pending_ids:
                    idx = id_to_idx.get(tid)
                    if idx is not None:
                        records[idx]["result"] = SubtitleResult(
                            success=False, task_id=str(tid),
                            error_message="用户取消",
                        )
                break

            elapsed = time.time() - start_time
            if elapsed > timeout:
                for tid in pending_ids:
                    idx = id_to_idx[tid]
                    try:
                        self.cancel(str(tid))  # 尝试取消（API 不支持，但标记记录）
                    except Exception:
                        pass
                    records[idx]["result"] = SubtitleResult(
                        success=False, task_id=str(tid),
                        error_message=f"任务超时 ({timeout}秒)",
                    )
                break

            try:
                status_resp = self._api_post(
                    self.CHECK_STATUS,
                    {"idWorks": list(pending_ids)},
                )
                contents = status_resp["body"].get("content", [])

                for content in contents:
                    tid = content.get("id")
                    if tid is None:
                        continue
                    status = content.get("processStatus", -1)

                    if status == 1:  # 成功
                        pending_ids.discard(tid)
                        idx = id_to_idx.get(tid)
                        if idx is not None:
                            video_url = content.get("videoUrl", "")
                            records[idx]["result"] = SubtitleResult(
                                success=True, task_id=str(tid),
                                output_path=video_url,  # 远程 URL，调用者自行下载
                                metadata={"video_url": video_url, "name": content.get("name", "")},
                            )
                    elif status > 1:  # 失败
                        pending_ids.discard(tid)
                        idx = id_to_idx.get(tid)
                        if idx is not None:
                            records[idx]["result"] = SubtitleResult(
                                success=False, task_id=str(tid),
                                error_message=content.get("errorDetail", f"处理失败，状态码: {status}"),
                            )

                if pending_ids:
                    done = n - len(pending_ids)
                    self._log("debug", f"进度: {done}/{n} 完成, {len(pending_ids)} 处理中")
                    if progress_callback:
                        progress_callback("processing", 0.2 + done / n * 0.6)

            except (urllib.error.URLError, OSError) as e:
                self._log("warn", f"网络错误: {e}，{poll_interval}秒后重试...")

            if pending_ids:
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, 30)

        # ── Phase 4: 返回结果 ──
        results = []
        for r in records:
            if r["result"] is None:
                r["result"] = SubtitleResult(
                    success=False, task_id=r.get("task_id", ""),
                    error_message="未知错误",
                )
            final = r["result"]
            results.append(final)

        success_count = sum(1 for r in results if r.success)
        total_elapsed = time.time() - start_time
        self._log("info", f"批量完成: {success_count}/{n} 成功, 总耗时 {total_elapsed:.0f}s")
        return results

    def check_health(self) -> bool:
        """测试 API 凭证有效性（查询余额）"""
        try:
            resp = self._api_post("/v-w-c/gateway/ve/point/query", {})
            return "body" in resp
        except Exception:
            # 健康检查失败（网络不通/认证过期/API变更），
            # 返回 False 由上层决定是否继续或切换适配器
            return False

    def get_balance(self) -> dict:
        """查询账户余额"""
        resp = self._api_post("/v-w-c/gateway/ve/point/query", {})
        return resp.get("body", {})

    def cancel(self, task_id: str) -> bool:
        """取消排队中的任务（GhostCut API 当前未提供取消接口）。
        Returns: True（取消结果由上层 try/except 兜底）
        """
        self._log("debug", f"取消请求已记录: {task_id}")
        return True
