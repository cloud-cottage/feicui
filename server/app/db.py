"""feicui API 层数据访问基础设施（Kong / 阶段 1a）。

只做「连接 / 事务 / 只读查询」三件事，不含任何业务语义（业务语义在 repository.py）。

规范锚点：§4.1 D-1（WAL 由迁移入口设置并校验）、§4.3（写路径必须串行化：
本层不做并发写，接口层只在 E1 的单事务内写 `jobs` + `job_pages`）。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

_TZ = None


def now_iso() -> str:
    """ISO8601 带上本机时区偏移（Asia/Shanghai，规范 §0.2 时点戳口径）。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def connect(db_path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    path = str(db_path)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30.0)
    else:
        conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


@contextmanager
def tx(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """写事务：一个事务内完成 E1 的 `jobs` + `job_pages` 写入（§4.3 页内记录与影像同批生效的落库侧）。"""
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def ro(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """只读连接（E2 / E5 的复算一律走这里）。

    注意：若库不存在，sqlite 的 `mode=ro` 会直接抛错——这是希望的（不静默建空库）。
    """
    conn = connect(db_path, readonly=True)
    try:
        yield conn
    finally:
        conn.close()


def query_all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, tuple(params)))


def query_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    cur = conn.execute(sql, tuple(params))
    row = cur.fetchone()
    return row


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        query_one(
            conn,
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','index') AND name=?",
            (name,),
        )
        is not None
    )


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    """`sqlite_master` 内容的稳定指纹——用于证明迁移幂等（第二次不重复建表）。"""
    import hashlib

    rows = query_all(conn, "SELECT type, name, COALESCE(sql,'') FROM sqlite_master ORDER BY type, name")
    blob = "\n".join(f"{r[0]}|{r[1]}|{r[2]}" for r in rows)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
