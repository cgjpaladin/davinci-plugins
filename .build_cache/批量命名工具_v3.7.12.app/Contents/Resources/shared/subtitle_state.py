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
from ops_logger import _event_log

# 本机局域网 IP — 锁和状态里记录，方便排查
def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        # socket.connect 在无网络/SMB不通时抛 OSError，降级用主机名
        return socket.gethostname()
_HOST_IP = _get_lan_ip()
_HOST_NICK = f"{_HOST_IP}的同事"  # 192.168.1.200 → 192.168.1.200的同事（模块加载时固定，会话期间IP不变）

# 状态文件路径 — 由 init() 设置
_state_file = None
_lock_dir = None


def init(project_root: str = None):
    """初始化状态系统，必须传入项目根目录。"""
    global _state_file, _lock_dir
    state_dir = get_state_dir(project_root)
    _state_file = os.path.join(state_dir, ".subtitle_state.json")
    _lock_dir = get_lock_dir(project_root)
    hide_path(_state_file)


def _load_state() -> dict:
    if not _state_file or not os.path.exists(_state_file):
        return {}
    try:
        with open(_state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_state(state: dict, _locked: bool = False):
    """写入状态文件。
    
    Args:
        state: 要写入的完整状态字典
        _locked: True=调用者已持有写锁，跳过自获取
    """
    if not _state_file:
        return
    sdir = os.path.dirname(_state_file)
    os.makedirs(sdir, exist_ok=True)

    # 如果调用者已持锁，跳过自获取；否则自己获取
    acquired = False
    if not _locked:
        acquired = _acquire_state_lock()

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
                # 旧备份删除失败不阻塞状态写入（SMB权限变化/文件被占用）
                pass

        with open(_state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        hide_path(_state_file)
    finally:
        if acquired:
            _release_state_lock()


# ============================================================
# 原子并发锁（os.mkdir 在 SMB 上是原子的）
# 锁自动过期：10 分钟后视为失效，避免崩溃残留
# ============================================================

_LOCK_TTL = 600  # 锁 TTL（秒）
_BAK_KEEP = 7      # 备份保留天数


def _acquire_state_lock() -> bool:
    """获取状态文件的写锁（os.mkdir 原子，5 次退避重试）。
    返回 True=成功，False=5 次都失败。"""
    lock_path = _state_file + ".writelock"
    for attempt in range(5):
        try:
            os.mkdir(lock_path)
            return True
        except FileExistsError:
            time.sleep(0.2 * (attempt + 1))
    return False


def _release_state_lock():
    """释放状态文件的写锁"""
    lock_path = _state_file + ".writelock"
    try:
        os.rmdir(lock_path)
    except OSError:
        # 锁目录可能已被其他人清理，或从未创建，删不掉是正常情况
        pass


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
    回收条件：同机（IP 匹配）→ 立即回收；超时 > 10 分钟 → 自动回收。
    Returns: True=抢到锁, "reclaimed"=旧锁被回收, False=别人正在处理
    """
    lock_path = _safe_lock_path(clip_name)
    if not lock_path:
        return True  # 无锁目录 = 不需要锁

    # 如果锁存在，判断是否可回收
    reclaimed = False
    if os.path.isdir(lock_path):
        try:
            can_reclaim = False
            # 同机锁：自己的残留锁立即回收
            info_file = os.path.join(lock_path, ".info")
            if os.path.isfile(info_file):
                with open(info_file, encoding="utf-8") as f:
                    owner_ip = json.load(f).get("ip", "")
                if owner_ip == _HOST_IP:
                    can_reclaim = True
            # 超时锁
            mtime = os.path.getmtime(lock_path)
            if time.time() - mtime > _LOCK_TTL:
                can_reclaim = True

            if can_reclaim:
                # os.rmdir 只能删空目录，锁目录含 .info，用 rmtree
                shutil.rmtree(lock_path)
                reclaimed = True
        except OSError:
            return False  # 删不掉 = 别人正在用

    try:
        os.mkdir(lock_path)
        try:
            with open(os.path.join(lock_path, ".info"), "w") as f:
                json.dump({"ip": _HOST_IP, "user": _HOST_NICK, "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
        except OSError:
            # 锁 .info 文件写入失败不阻塞锁获取（SMB瞬时不可用），
            # 缺少 .info 仅影响 is_locked() 显示用户名，不影响并发正确性
            pass
    except FileExistsError:
        return False

    return "reclaimed" if reclaimed else True


def release_lock(clip_name: str):
    """释放片段的处理锁"""
    lock_path = _safe_lock_path(clip_name)
    if not lock_path:
        return
    try:
        os.rmdir(lock_path)
    except OSError:
        # 锁可能已被其他人/超时回收清理，删不掉是正常情况
        pass


def is_locked(clip_name: str) -> Optional[str]:
    """检查片段是否被锁定。返回用户标识（如'192.168.1.200的同事'），未锁返回 None。"""
    lock_path = _safe_lock_path(clip_name)
    if not lock_path or not os.path.isdir(lock_path):
        return None
    try:
        info_file = os.path.join(lock_path, ".info")
        if os.path.isfile(info_file):
            with open(info_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            ip = data.get("ip", "")
            return f"{ip}的同事" if ip else "未知同事"
    except Exception:
        # 锁 .info 文件损坏或 SMB 瞬时不可读，降级返回"未知同事"
        # 不影响并发正确性，仅影响UI上锁提示的用户名显示
        _event_log(f"[subtitle_state] is_locked 读锁信息失败: {clip_name}")
    return "未知同事"


# ============================================================
# 状态管理
# ============================================================

def record_original(clip_name: str, original_path: str):
    """记录原片路径（处理前调用）。持写锁完成，防止多机竞态。"""
    if not _acquire_state_lock():
        _event_log(f"[subtitle_state] record_original 获取写锁失败: {clip_name}")
        return
    try:
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
        _save_state(state, _locked=True)
    finally:
        _release_state_lock()


def mark_processed(clip_name: str, processed_path: str, mode: str):
    """标记处理完成。持写锁完成，防止多机竞态。"""
    if not _acquire_state_lock():
        _event_log(f"[subtitle_state] mark_processed 获取写锁失败: {clip_name}")
        return
    try:
        state = _load_state()
        entry = state.get(clip_name, {})
        
        state[clip_name] = {
            "original_path": entry.get("original_path", processed_path),
            "current_path": processed_path,
            "status": f"{mode}_done",
            "ip": _HOST_IP,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_state(state, _locked=True)
    finally:
        _release_state_lock()


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
    """查询片段当前处理状态（original / basic_done / lite_done / pro_done）"""
    state = _load_state()
    entry = state.get(clip_name)
    return entry.get("status") if entry else None


def get_all_entries() -> dict:
    """返回完整状态字典（调试/审计用）"""
    return _load_state()
