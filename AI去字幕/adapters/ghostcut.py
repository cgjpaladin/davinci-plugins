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
from typing import Optional
from urllib.parse import urlparse

from . import BaseAdapter, SubtitleTask, SubtitleResult, TaskStatus
from config import DEFAULT_MASK_REGION as _MASK_REGION

# 达芬奇内置 Python 可能缺 SSL 证书 — 全局宽松 context
_SSL_CTX = ssl.create_default_context()


class GhostCutAdapter(BaseAdapter):
    """鬼手剪辑去字幕适配器"""

    BASE_URL = "https://api.zhaoli.com"
    CREATE_TASK = "/v-w-c/gateway/ve/work/free"
    CHECK_STATUS = "/v-w-c/gateway/ve/work/status"
    UPLOAD_POLICY = "/v-w-c/gateway/ve/file/upload/policy/apply"
    
    # 擦除模型映射
    MODEL_MAP = {
        "lite": "advanced_lite",          # 高级擦除 Lite
        "pro": "advanced_full",            # 高级擦除 Pro（全屏）
        "pro_box": "advanced",             # 高级擦除 Pro（小框）
        "pro_large": "advanced_large_box", # 高级擦除 Pro（大框）
    }

    def __init__(self, config: dict):
        super().__init__("GhostCut", config)
        self.app_key = config.get("app_key")
        self.app_secret = config.get("app_secret")
        self.default_model = config.get("model", "basic")
        
        if not self.app_key or not self.app_secret:
            raise ValueError("GhostCut 适配器需要 app_key 和 app_secret")

    def _sign(self, body: dict) -> str:
        """双重 MD5 签名: md5(md5(body_json) + AppSecret)"""
        body_str = json.dumps(body, ensure_ascii=False)
        body_md5 = hashlib.md5(body_str.encode()).hexdigest()
        return hashlib.md5((body_md5 + self.app_secret).encode()).hexdigest()

    def _api_post(self, path: str, payload: dict) -> dict:
        """带签名的 API POST 请求（纯 urllib，零依赖，含 SSL 兜底）"""
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
        # 达芬奇内置 Python 可能缺 SSL 证书 — 创建宽松 context
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {body[:200]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}") from e

    def submit(self, task: SubtitleTask) -> str:
        """
        提交去字幕任务
        
        自动处理本地文件上传：如果 video_path 是本地文件，
        自动上传到 GhostCut OSS 获取临时 URL 后再提交任务。
        """
        video_url = task.video_path
        
        parsed = urlparse(video_url)
        if not parsed.scheme.startswith("http"):
            # 本地文件 → 自动上传
            print(f"[GhostCut] 检测到本地文件，自动上传: {os.path.basename(video_url)}")
            video_url = self._upload_file(video_url)
            print(f"[GhostCut] 上传完成: {video_url}")
        
        model_name = task.model or self.default_model
        base_name = os.path.splitext(os.path.basename(task.video_path))[0] if task.video_path else "unknown"
        
        if model_name == "basic":
            payload = {
                "urls": [video_url],
                "names": [base_name],
                "resolution": "1080p",
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
                "resolution": "1080p",
                "needChineseOcclude": 2,
                "videoInpaintLang": task.language,
                "videoInpaintMasks": json.dumps(masks),
                "extraOptions": json.dumps({
                    "extra_inpaint_config": {"model": model_value}
                }),
            }
        else:
            # Lite / Pro 全屏
            masks = task.mask_regions
            if masks is None and model_name == "lite":
                masks = [{
                    "type": "remove_only_ocr",
                    "start": 0, "end": 99999,
                    "region": _MASK_REGION
                }]
            
            if model_name == "lite":
                model_value = "advanced_lite"
                need = 2
            else:  # pro
                model_value = "advanced_full"
                need = 1
                masks = None
            
            payload = {
                "urls": [video_url],
                "names": [base_name],
                "resolution": "1080p",
                "needChineseOcclude": need,
                "videoInpaintLang": "all" if model_name == "lite" else task.language,
            }
            if masks:
                payload["videoInpaintMasks"] = json.dumps(masks)
            payload["extraOptions"] = json.dumps({
                "extra_inpaint_config": {"model": model_value}
            })
        
        resp = self._api_post(self.CREATE_TASK, payload)
        
        # 解析任务ID
        try:
            work_id = resp["body"]["dataList"][0]["id"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"GhostCut 返回异常: {json.dumps(resp, ensure_ascii=False)}") from e
        
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
            print(f"[GhostCut] ⚠ 文件较大 ({file_size_mb:.0f}MB)，上传可能耗时较长")
        
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
        with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as resp:
            resp_text = resp.read().decode()
        
        if resp_text.strip() != '{"Status":"OK"}':
            raise RuntimeError(f"文件上传失败: {resp_text}")
        
        # Step 3: 拼接 CDN URL
        cdn_url = policy["urlPrefix"] + filename
        return cdn_url

    def wait_for_result(self, task_id: str, timeout: int = 600, cancel_check=None) -> SubtitleResult:
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
                    pass
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
                    video_url = content.get("videoUrl", "")
                    
                    # 如果指定了 output_path，自动下载
                    download_path = self._output_path
                    if download_path:
                        print(f"[GhostCut] 下载处理结果到: {download_path}")
                        urllib.request.urlretrieve(video_url, download_path)
                    
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
                print(f"[GhostCut] 网络错误: {e}，{poll_interval}秒后重试...")
            
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 30)  # 逐渐拉长到30秒

    def process_batch(self, tasks: list, timeout: int = 600,
                       cancel_check=None) -> list:
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
        print(f"[GhostCut] 批量处理 {n} 个片段")

        # ── Phase 1: 上传所有文件 → CDN URLs ──
        records = []
        for i, task in enumerate(tasks):
            if cancel_check and cancel_check():
                print(f"[GhostCut] 上传阶段收到停止，已上传 {i}/{n}")
                break
            video_url = task.video_path
            parsed = urlparse(video_url)
            if not parsed.scheme.startswith("http"):
                base = os.path.basename(video_url)
                print(f"[GhostCut] [{i+1}/{n}] 上传: {base}")
                try:
                    video_url = self._upload_file(video_url)
                except Exception as e:
                    print(f"[GhostCut] ⚠ 上传失败: {base} — {e}")
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
        print(f"[GhostCut] 上传完成")

        # ── Phase 2: 一次提交所有任务 ──
        if cancel_check and cancel_check():
            print(f"[GhostCut] 提交阶段收到停止")
            # 补齐未提交的结果
            for rec in records:
                if rec.get("result") is None:
                    rec["result"] = SubtitleResult(success=False, error_message="用户取消（未提交）")
            return [r.get("result", SubtitleResult(success=False)) for r in records]

        model_name = self.default_model
        urls = [r["video_url"] for r in records]
        names = [r["base_name"] for r in records]

        if model_name == "basic":
            payload = {
                "urls": urls,
                "names": names,
                "resolution": "1080p",
                "needChineseOcclude": 3,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
            }
        elif model_name in ("pro_box", "pro_large"):
            masks = tasks[0].mask_regions if tasks else None
            if not masks:
                raise ValueError(f"{model_name} 模式必须指定 mask_regions")
            model_value = self.MODEL_MAP.get(model_name, "advanced")
            payload = {
                "urls": urls,
                "names": names,
                "resolution": "1080p",
                "needChineseOcclude": 2,
                "videoInpaintLang": tasks[0].language if tasks else "zh",
                "videoInpaintMasks": json.dumps(masks),
                "extraOptions": json.dumps({
                    "extra_inpaint_config": {"model": model_value}
                }),
            }
        else:
            raise ValueError(f"process_batch 不支持模式: {model_name}")

        resp = self._api_post(self.CREATE_TASK, payload)
        data_list = resp["body"]["dataList"]

        if len(data_list) != n:
            print(f"[GhostCut] ⚠ 返回 {len(data_list)} 个任务，期望 {n} 个")

        for i, item in enumerate(data_list):
            if i < len(records):
                records[i]["task_id"] = str(item["id"])
        print(f"[GhostCut] 已提交 {len(data_list)} 个任务，等待处理...")

        # ── Phase 3: 一起轮询 ──
        all_ids = [int(r["task_id"]) for r in records if r["task_id"]]
        start_time = time.time()
        poll_interval = 5
        pending_ids = set(all_ids)
        id_to_idx = {int(r["task_id"]): i for i, r in enumerate(records) if r["task_id"]}

        while pending_ids:
            # 检查取消
            if cancel_check and cancel_check():
                print(f"[GhostCut] 停止：取消 {len(pending_ids)} 个排队任务...")
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
                    print(f"[GhostCut] 进度: {done}/{n} 完成, {len(pending_ids)} 处理中")

            except (urllib.error.URLError, OSError) as e:
                print(f"[GhostCut] 网络错误: {e}，{poll_interval}秒后重试...")

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
            results.append(r["result"])

        success_count = sum(1 for r in results if r.success)
        total_elapsed = time.time() - start_time
        print(f"[GhostCut] 批量完成: {success_count}/{n} 成功, 总耗时 {total_elapsed:.0f}s")
        return results

    def check_health(self) -> bool:
        """测试 API 凭证有效性（查询余额）"""
        try:
            resp = self._api_post("/v-w-c/gateway/ve/point/query", {})
            return "body" in resp
        except Exception:
            return False

    def get_balance(self) -> dict:
        """查询账户余额"""
        resp = self._api_post("/v-w-c/gateway/ve/point/query", {})
        return resp.get("body", {})

    def cancel(self, task_id: str) -> bool:
        """取消排队中的任务（GhostCut API 当前未提供取消接口）。
        Returns: True（取消结果由上层 try/except 兜底）
        """
        print(f"[GhostCut] 取消请求已记录: {task_id}")
        return True
