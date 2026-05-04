"""
watermark_state.py — 项目级去水印状态管理 + 并发锁

路径:
  生产: {项目}/04_素材/03_去水印/.watermark_state.json
  调试: {DEBUG_OUTPUT_DIR}/.watermark_state.json

三层路径替换策略：
  1. 处理前：记录原片路径
  2. Basic/Lite 处理完：ReplaceClip → 状态标记 basic_done/lite_done
  3. Pro 跑前：读状态 → 如果当前指向非原片 → ReplaceClip 还原原片 → 跑 Pro
  4. 跨用户：状态文件放 SMB，团队共享

并发安全:
  原子锁 via os.mkdir() — SMB 上创建目录是原子的，两人同时建同名目录只有一个成功
"""

import json
import os
import subprocess
import time
from typing import Optional

from config import get_state_dir, get_lock_dir, get_output_dir

# 状态文件路径 — 由 init() 设置
_state_file = None
_lock_dir = None


def init(project_root: str = None):
    """初始化状态系统，必须传入项目根目录"""
    global _state_file, _lock_dir
    state_dir = get_state_dir(project_root)
    _state_file = os.path.join(state_dir, ".watermark_state.json")
    _lock_dir = get_lock_dir(project_root)
    _ensure_hidden(_state_file)


def _ensure_hidden(filepath: str):
    if os.path.exists(filepath):
        try:
            subprocess.run(["chflags", "hidden", filepath], capture_output=True)
        except Exception:
            pass


def _load_state() -> dict:
    if not _state_file or not os.path.exists(_state_file):
        return {}
    try:
        with open(_state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_state(state: dict):
    if not _state_file:
        return
    os.makedirs(os.path.dirname(_state_file), exist_ok=True)
    # 写入前备份
    import shutil
    bak = _state_file + ".bak"
    if os.path.exists(_state_file):
        shutil.copy2(_state_file, bak)
    with open(_state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    _ensure_hidden(_state_file)


# ============================================================
# 原子并发锁（os.mkdir 在 SMB 上是原子的）
# 锁自动过期：10 分钟后视为失效，避免崩溃残留
# ============================================================

_LOCK_TTL = 600  # 10 分钟


def acquire_lock(clip_name: str) -> bool:
    """
    尝试获取片段的处理锁。
    SMB 上 os.mkdir() 是原子操作。
    如果锁已过期（>10分钟），自动抢占。
    Returns: True=抢到锁, False=别人正在处理
    """
    if not _lock_dir:
        return True
    lock_path = os.path.join(_lock_dir, f"{clip_name}.lock")
    
    # 如果锁存在但已过期 → 删除旧锁，重新抢
    if os.path.isdir(lock_path):
        try:
            mtime = os.path.getmtime(lock_path)
            if time.time() - mtime > _LOCK_TTL:
                os.rmdir(lock_path)
        except OSError:
            return False  # 删不掉 = 别人正在用
    
    try:
        os.mkdir(lock_path)
        return True
    except FileExistsError:
        return False


def release_lock(clip_name: str):
    """释放片段的处理锁"""
    if not _lock_dir:
        return
    lock_path = os.path.join(_lock_dir, f"{clip_name}.lock")
    try:
        os.rmdir(lock_path)
    except OSError:
        pass


def is_locked(clip_name: str) -> bool:
    """检查片段是否被锁定"""
    if not _lock_dir:
        return False
    return os.path.isdir(os.path.join(_lock_dir, f"{clip_name}.lock"))


# ============================================================
# 状态管理
# ============================================================

def record_original(clip_name: str, original_path: str):
    """记录原片路径（处理前调用）"""
    state = _load_state()
    entry = state.get(clip_name)
    
    if entry and entry.get("status") == "original":
        return
    
    state[clip_name] = {
        "original_path": original_path,
        "current_path": original_path,
        "status": "original",
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_state(state)


def mark_processed(clip_name: str, processed_path: str, mode: str):
    """标记处理完成"""
    state = _load_state()
    entry = state.get(clip_name, {})
    
    state[clip_name] = {
        "original_path": entry.get("original_path", processed_path),
        "current_path": processed_path,
        "status": f"{mode}_done",
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_state(state)


def need_restore(clip_name: str, target_mode: str) -> Optional[str]:
    """
    仅返回原片路径（如需升级），不做跳过判断。
    跳过逻辑由扫描层根据文件名判断。
    
    Returns: 原片路径 / None（无记录或无需还原）
    """
    state = _load_state()
    entry = state.get(clip_name)
    if not entry:
        return None
    
    current = entry.get("status", "")
    # 需要升级（低级 → 高级）→ 返回原片路径
    order = {"original": -1, "basic_done": 0, "lite_done": 1, "pro_done": 2, "pro_box_done": 3}
    if order.get(f"{target_mode}_done", -1) > order.get(current, -1):
        return entry.get("original_path")
    return None


def get_clip_status(clip_name: str) -> Optional[str]:
    state = _load_state()
    entry = state.get(clip_name)
    return entry.get("status") if entry else None


def get_all_entries() -> dict:
    return _load_state()
