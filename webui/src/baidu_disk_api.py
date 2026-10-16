# src/baidu_disk_api.py
"""
百度网盘企业版（小微团队版）文件锁 API（占位实现）
真实接入时替换为百度企业网盘开放API调用。
当前为本地 mock：锁状态写到同目录 locks_local.json。
"""
import os
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOCK_PATH = Path(__file__).parent.parent / "locks_local.json"


def _load_locks():
    if not LOCK_PATH.exists():
        return {}
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_locks(locks):
    LOCK_PATH.write_text(
        json.dumps(locks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_file_lock_status(cloud_path: str) -> str:
    """返回 'locked' 或 'idle'"""
    locks = _load_locks()
    info = locks.get(cloud_path)
    if info and info.get("status") == "locked":
        return "locked"
    return "idle"


def lock_file(cloud_path: str, operator: str = ""):
    """
    锁定云端文件。
    返回 (ok, msg)
    """
    locks = _load_locks()
    info = locks.get(cloud_path)
    if info and info.get("status") == "locked":
        return False, f"文件已被 {info.get('operator','他人')} 锁定"

    locks[cloud_path] = {
        "status": "locked",
        "operator": operator,
        "time": _now_iso(),
    }
    _save_locks(locks)
    return True, "锁定成功"


def unlock_file(cloud_path: str):
    """解锁文件"""
    locks = _load_locks()
    if cloud_path in locks:
        locks[cloud_path] = {"status": "idle", "operator": "", "time": _now_iso()}
        _save_locks(locks)
    return True, "解锁成功"


def _now_iso():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
