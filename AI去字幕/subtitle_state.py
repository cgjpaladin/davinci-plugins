"""
subtitle_state.py — 项目级去字幕状态管理 + 并发锁

路径:
  生产: {项目}/04_素材/03_去字幕/.subtitle_state.json
  调试: {DEBUG_OUTPUT_DIR}/.subtitle_state.json

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
import shutil
import socket
import time
from typing import Optional

from config import get_state_dir, get_lock_dir, get_output_dir, hide_path

# 本机局域网 IP — 锁和状态里记录，方便排查
def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return socket.gethostname()
_HOST_IP = _get_lan_ip()
_HOST_NICK = f"{_HOST_IP}的同事"  # 192.168.1.200 → 192.168.1.200的同事（模块加载时固定，会话期间IP不变）

# 状态文件路径 — 由 init() 设置
_state_file = None
_lock_dir = None


def init(project_root: str = None):
    """初始化状态系统，必须传入项目根目录。
    自动迁移旧的 .watermark_state.json → .subtitle_state.json。"""
    global _state_file, _lock_dir
    state_dir = get_state_dir(project_root)
    _state_file = os.path.join(state_dir, ".subtitle_state.json")
    _lock_dir = get_lock_dir(project_root)

    # 迁移旧状态文件（只做一次）
    _old_file = os.path.join(state_dir, ".watermark_state.json")
    if os.path.exists(_old_file) and not os.path.exists(_state_file):
        try:
            shutil.copy2(_old_file, _state_file)
        except Exception:
            pass

    hide_path(_state_file)


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
    sdir = os.path.dirname(_state_file)
    os.makedirs(sdir, exist_ok=True)

    # 原子写锁 — os.mkdir 在 SMB 上原子，防多机同时写覆盖
    lock_path = _state_file + ".writelock"
    acquired = False
    for attempt in range(5):
        try:
            os.mkdir(lock_path)
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.2 * (attempt + 1))  # 退避: 0.2s, 0.4s, 0.6s...
    if not acquired:
        # 5 次都失败，最后尝试一次裸写（宁写不丢）
        pass

    try:
        # 轮转备份：保留最近 N 份
        if os.path.exists(_state_file):
            ts = time.strftime("%Y%m%d")
            bak = f"{_state_file}.{ts}.bak"
            if not os.path.exists(bak):
                shutil.copy2(_state_file, bak)
            # 清理旧备份
            try:
                backups = sorted(
                    [f for f in os.listdir(sdir)
                     if f.startswith(".subtitle_state.json.") and f.endswith(".bak")],
                    reverse=True,
                )
                for old in backups[_BAK_KEEP:]:
                    os.remove(os.path.join(sdir, old))
            except Exception:
                pass

        with open(_state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        hide_path(_state_file)
    finally:
        if acquired:
            try:
                os.rmdir(lock_path)
            except OSError:
                pass


# ============================================================
# 原子并发锁（os.mkdir 在 SMB 上是原子的）
# 锁自动过期：10 分钟后视为失效，避免崩溃残留
# ============================================================

_LOCK_TTL = 600  # 锁 TTL（秒）
_BAK_KEEP = 7      # 备份保留天数


def _safe_lock_path(clip_name: str) -> str:
    """构建锁路径并校验在 lock_dir 内部（防止路径穿越）"""
    if not _lock_dir:
        return ""
    lock_path = os.path.realpath(os.path.join(_lock_dir, f"{clip_name}.lock"))
    real_lock_dir = os.path.realpath(_lock_dir)
    if not lock_path.startswith(real_lock_dir + os.sep):
        return ""
    return lock_path


def acquire_lock(clip_name: str) -> bool:
    """
    尝试获取片段的处理锁。
    SMB 上 os.mkdir() 是原子操作。
    如果锁已过期（>10分钟），自动抢占。
    Returns: True=抢到锁, "reclaimed"=过期锁被回收, False=别人正在处理
    """
    lock_path = _safe_lock_path(clip_name)
    if not lock_path:
        return True  # 无锁目录 = 不需要锁

    # 如果锁存在但已过期 → 删除旧锁，重新抢
    reclaimed = False
    if os.path.isdir(lock_path):
        try:
            mtime = os.path.getmtime(lock_path)
            if time.time() - mtime > _LOCK_TTL:
                os.rmdir(lock_path)
                reclaimed = True
        except OSError:
            return False  # 删不掉 = 别人正在用

    try:
        os.mkdir(lock_path)
        # 写锁信息：谁锁的，什么时候
        try:
            with open(os.path.join(lock_path, ".info"), "w") as f:
                json.dump({"ip": _HOST_IP, "user": _HOST_NICK, "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
        except OSError:
            pass
        return "reclaimed" if reclaimed else True
    except FileExistsError:
        return False


def release_lock(clip_name: str):
    """释放片段的处理锁"""
    lock_path = _safe_lock_path(clip_name)
    if not lock_path:
        return
    try:
        os.rmdir(lock_path)
    except OSError:
        pass


def is_locked(clip_name: str) -> Optional[str]:
    """检查片段是否被锁定。返回用户标识（如'192.168.1.200的同事'），未锁返回 None。"""
    lock_path = _safe_lock_path(clip_name)
    if not lock_path or not os.path.isdir(lock_path):
        return None
    try:
        info_file = os.path.join(lock_path, ".info")
        if os.path.isfile(info_file):
            with open(info_file, "r") as f:
                data = json.load(f)
            ip = data.get("ip", "")
            return f"{ip}的同事" if ip else "未知同事"
    except: pass
    return "未知同事"


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
        "ip": _HOST_IP,
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
        "ip": _HOST_IP,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_state(state)


def get_original_path(file_name: str) -> Optional[str]:
    """根据 File Name 查找处理前的原始路径。"""
    state = _load_state()
    entry = state.get(file_name)
    if entry and entry.get("status", "").endswith("_done"):
        return entry.get("original_path")
    return None


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
