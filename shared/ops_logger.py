"""
操作日志模块 — 项目级 JSONL 结构化 + 隐藏文件

设计原则：
- JSONL 格式：每行一个 JSON 对象，AI 直接解析
- 线程安全：threading.Lock 保护并发写入
- 项目级：日志跟项目走，{项目}/04_素材/03_去字幕/.ops_logs/
- 按 IP 地址 + 日期分文件，20 台机器互不冲突
- 隐藏文件：macOS chflags hidden
- 零依赖：仅 Python 标准库
  clip_scan      — 片段扫描
  balance_check  — 余额查询
  task_submit    — API 任务提交
  task_result    — API 任务完成
  task_error     — API 任务失败
  session_end    — 会话结束
"""

import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone

from config import hide_path, SMB_LOG_DIR

_lock = threading.Lock()
_log_dir = None
_session_id = None
_host_ip = None
_SMB_HOST = os.environ.get("SMB_HOST", "192.168.1.154")


def _get_ip() -> str:
    """获取本机局域网 IP（连 SMB 网关获取实际接口地址）"""
    global _host_ip
    if _host_ip:
        return _host_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect((_SMB_HOST, 1))
        _host_ip = s.getsockname()[0]
        s.close()
    except Exception:
        # 无法通过socket获取局域网IP（无网络/非局域网环境），
        # 降级尝试 gethostbyname(gethostname())
        try:
            _host_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            # 所有方式都失败，使用 "unknown" 标识。
            # 日志按IP分文件的设计在此场景下降级为单文件，不影响功能
            _host_ip = "unknown"
    return _host_ip


def init(log_dir: str):
    """初始化日志系统，创建隐藏目录"""
    global _log_dir
    _log_dir = log_dir
    os.makedirs(_log_dir, exist_ok=True)
    hide_path(_log_dir)


def _file_path(log_dir=None):
    """按 IP + 日期分文件，20 台机器互不冲突"""
    if log_dir is None:
        log_dir = _log_dir
    ip = _get_ip()
    date = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(log_dir, f"op_{ip}_{date}.jsonl")


def _write(entry: dict):
    log_dir = _log_dir
    if not log_dir:
        # fallback：没确认项目路径时写到 SMB 插件日志目录
        log_dir = SMB_LOG_DIR
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            # 连 SMB 兜底日志目录都创建不了（SMB完全断开/权限丢失），
            # 无路可写，静默放弃本条日志
            return
    with _lock:
        import random as _random
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        path = _file_path(log_dir)

        # SMB 多机并发写入加固：随机抖动 + 重试
        for attempt in range(3):
            try:
                time.sleep(_random.uniform(0.001, 0.05))  # 1-50ms 随机错峰
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
                hide_path(path)
                break
            except (IOError, OSError):
                if attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
                else:
                    # 3 次都失败，静默丢弃（不阻塞主流程）
                    pass


def session_start(project_name: str, timeline_name: str, mode: str, balance: float):
    """会话开始"""
    global _session_id
    _session_id = uuid.uuid4().hex[:12]
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "session_start",
        "session": _session_id,
        "project": project_name,
        "timeline": timeline_name,
        "mode": mode,
        "balance_before": round(balance, 1),
    })


def clip_scan(total: int, skipped: int, clips: list):
    """片段扫描结果"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "clip_scan",
        "session": _session_id,
        "total": total,
        "skipped": skipped,
        "to_process": total - skipped,
        "clips": clips,
    })


def balance_check(balance: float, estimated: float, action: str):
    """余额检查"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "balance_check",
        "session": _session_id,
        "balance": round(balance, 1),
        "estimated": estimated,
        "action": action,  # "proceed" | "blocked" | "unknown"
    })


def task_submit(clip_name: str, mode: str, duration: float, attempt: int = 0):
    """API 任务提交"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "task_submit",
        "session": _session_id,
        "clip": clip_name,
        "mode": mode,
        "duration_sec": round(duration, 1),
        "attempt": attempt,
    })


def task_result(clip_name: str, task_id: str, elapsed: float, success: bool):
    """API 任务结果"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "task_result",
        "session": _session_id,
        "clip": clip_name,
        "task_id": str(task_id),
        "elapsed_sec": round(elapsed, 1),
        "success": success,
    })


def task_detail(clip_name: str, task_id: str, upload_sec: float = 0,
                api_sec: float = 0, download_sec: float = 0,
                upload_mb: float = 0, download_mb: float = 0):
    """任务子步骤耗时（用于性能复盘）"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "task_detail",
        "session": _session_id,
        "clip": clip_name,
        "task_id": str(task_id),
        "upload_sec": round(upload_sec, 1),
        "api_sec": round(api_sec, 1),
        "download_sec": round(download_sec, 1),
        "upload_mb": round(upload_mb, 2),
        "download_mb": round(download_mb, 2),
    })


def task_error(clip_name: str, error_msg: str, attempt: int):
    """API 任务错误"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "task_error",
        "session": _session_id,
        "clip": clip_name,
        "error": error_msg[:200],
        "attempt": attempt,
    })


def session_end(ok: int, fail: int, total: int, balance_after: float = None,
                points_spent: int = 0, elapsed_sec: int = 0, cost_yuan: float = 0):
    """会话结束"""
    entry = {
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "session_end",
        "session": _session_id,
        "ok": ok,
        "fail": fail,
        "total": total,
        "points_spent": points_spent,
        "elapsed_sec": elapsed_sec,
        "cost_yuan": cost_yuan,
    }
    if balance_after is not None:
        entry["balance_after"] = round(balance_after, 1)
    _write(entry)


def cost_estimate(points: int, yuan: float, estimated_min: int, need: int, cache: int):
    """费用预估（扫描后）"""
    _write({
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "host": _get_ip(),
        "event": "cost_estimate",
        "session": _session_id,
        "est_points": points,
        "est_yuan": yuan,
        "est_minutes": estimated_min,
        "need_process": need,
        "cache_hits": cache,
    })


# ── 通用 SMB 日志（按主机名分文件，供运维排查）──

_SMB_LOG = os.path.join(os.path.dirname(__file__), "logs", f"{socket.gethostname()}.log")


def _smb_log(msg: str):
    """写一行文本到 SMB 日志（非 JSONL，供人类排查）"""
    try:
        ts = time.strftime("%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(_SMB_LOG), exist_ok=True)
        with open(_SMB_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        import sys as _sys
        print(f"[_smb_log FAIL] {msg}", file=_sys.stderr)
