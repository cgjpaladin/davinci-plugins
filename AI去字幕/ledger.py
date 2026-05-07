# -*- coding: utf-8 -*-
"""
processing_ledger.py — 追加型 JSONL 处理账本

一条记录 = 一行 JSON。所有操作都是追加（append），不读-改-写。
SMB 上 open(f, "a").write(一行 + "\n") 是原子的 → 多机器安全。

记录动作:
  - "original"   → 扫描到的原片
  - "submitted"  → 已提交 API
  - "completed"  → 处理完成 + 已替换
  - "reverted"   → 已撤销替换

查询: 扫文件找 file_name 匹配的最新记录。
"""

import json
import os
import time
from typing import Any, Optional

from config import get_output_dir, hide_path

_ledger_file: Optional[str] = None
_machine: str = "unknown"


def init(project_root: str = None) -> None:
    """初始化账本路径。在 pick_project 时调用。"""
    global _ledger_file, _machine
    import socket
    _machine = socket.gethostname()
    if project_root:
        state_dir = get_output_dir(project_root)
        _ledger_file = os.path.join(state_dir, "processing_ledger.jsonl")
        hide_path(_ledger_file)


def _append(action: str, file_name: str, **extra) -> None:
    """追加一条记录到账本。"""
    if not _ledger_file:
        return
    record = {
        "file_name": file_name,
        "action": action,
        "machine": _machine,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    try:
        os.makedirs(os.path.dirname(_ledger_file), exist_ok=True)
        with open(_ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _scan() -> list[dict[str, Any]]:
    """读完整个账本（JSONL 通常很小）。"""
    if not _ledger_file or not os.path.exists(_ledger_file):
        return []
    records = []
    try:
        with open(_ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return records


# ── 写入 ──

def record_original(file_name: str, original_path: str) -> None:
    _append("original", file_name, original_path=original_path)


def record_submitted(file_name: str, strategy: str, resolution: str) -> None:
    _append("submitted", file_name, strategy=strategy, resolution=resolution)


def record_completed(file_name: str, output_path: str, original_path: str = "",
                     strategy: str = "", resolution: str = "",
                     points: int = 0, cost_yuan: float = 0.0) -> None:
    _append("completed", file_name,
            original_path=original_path, output_path=output_path,
            strategy=strategy, resolution=resolution,
            points=points, cost_yuan=cost_yuan)


def record_reverted(file_name: str) -> None:
    _append("reverted", file_name)


# ── 查询 ──

def find_latest(file_name: str, action: str = "completed") -> Optional[dict[str, Any]]:
    """查找 file_name 最新的一条指定 action 的记录。"""
    best = None
    for r in _scan():
        if r.get("file_name") == file_name and r.get("action") == action:
            if best is None or r.get("time", "") > best.get("time", ""):
                best = r
    return best


def find_output(file_name: str) -> Optional[str]:
    """
    查缓存：看有没有对这个 file_name 处理完成过，且输出文件还存在。
    返回 output_path 或 None。
    """
    r = find_latest(file_name, "completed")
    if r:
        path = r.get("output_path", "")
        if path and os.path.exists(path):
            return path
    return None


def get_original_path(file_name: str) -> Optional[str]:
    """根据 file_name 查找原始路径（用于撤销）。"""
    # 优先看有没有 reverted（已撤销过）
    r = find_latest(file_name, "completed")
    if r:
        return r.get("original_path")
    return None


def was_reverted(file_name: str) -> bool:
    """上次操作是不是撤销。"""
    for r in reversed(_scan()):
        if r.get("file_name") == file_name:
            return r.get("action") == "reverted"
    return False


# ── 自动清理 ──

_CLEANUP_SIZE_MB = 10      # JSONL 超 10MB 触发清理
_CLEANUP_DAYS = 180         # 保留最近 180 天的记录


def maybe_cleanup() -> None:
    """如果账本超过阈值，裁剪掉旧记录。保留 30 天内 + 每个 clip_name 最新一条。"""
    if not _ledger_file or not os.path.exists(_ledger_file):
        return
    size_mb = os.path.getsize(_ledger_file) / (1024 * 1024)
    if size_mb < _CLEANUP_SIZE_MB:
        return

    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - _CLEANUP_DAYS * 86400))
    records = _scan()
    # 找每个 clip_name 的最新记录时间
    latest = {}
    for r in records:
        cn = r.get("file_name", "")
        t = r.get("time", "")
        if cn not in latest or t > latest[cn]:
            latest[cn] = t

    # 保留：30天内 OR 是该 clip_name 的最新记录
    kept = []
    for r in records:
        t = r.get("time", "")
        cn = r.get("file_name", "")
        if t >= cutoff or t == latest.get(cn, ""):
            kept.append(r)

    if len(kept) == len(records):
        return  # 无可裁剪

    try:
        tmp = _ledger_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in kept:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _ledger_file)
    except Exception:
        pass  # 清理失败不阻塞主流程
