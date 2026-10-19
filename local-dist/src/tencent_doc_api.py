# src/tencent_doc_api.py
"""
腾讯文档日志表 API（占位实现）
真实接入时替换为腾讯文档 OpenAPI V3 调用。
当前为本地 mock：日志写到同目录 logs_local.json，便于离线调试。
"""
import os
import json
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DAILY_QUOTA = int(os.getenv("DAILY_QUOTA", "1000"))
LOCAL_LOG_PATH = Path(__file__).parent.parent / "logs_local.json"


def _load_logs():
    if not LOCAL_LOG_PATH.exists():
        return []
    try:
        return json.loads(LOCAL_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_logs(logs):
    LOCAL_LOG_PATH.write_text(
        json.dumps(logs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_today_write_count() -> int:
    """统计今日（本地时区）新增日志条数"""
    today = datetime.now().strftime("%Y-%m-%d")
    logs = _load_logs()
    return sum(1 for r in logs if r.get("operate_time", "").startswith(today))


def append_log_record(record: dict):
    """
    追加一条操作日志。
    返回 (ok, msg)
    """
    if get_today_write_count() >= DAILY_QUOTA:
        return False, f"已达今日日志上限 {DAILY_QUOTA} 条"

    record = dict(record)
    record.setdefault("record_id", str(uuid.uuid4()))
    record.setdefault("operate_time", datetime.now().isoformat(timespec="seconds"))

    logs = _load_logs()
    logs.append(record)
    _save_logs(logs)
    return True, "日志写入成功（本地mock）"


def fetch_log_page(page_size: int = 20, page: int = 1):
    """分页拉取日志（倒序，最新在前）"""
    logs = _load_logs()
    logs = list(reversed(logs))
    start = (page - 1) * page_size
    return logs[start:start + page_size]
