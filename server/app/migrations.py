"""幂等迁移入口（`python -m app.migrations`）——Kong / 阶段 1a。

设计要点（规范 §4「只许加法」+ §2.3「断点必须落盘」）：
  * **只建新物**：`jobs` / `job_pages` / `schema_migrations` + 若干索引；
    **不改写** `stamps` 的任何列与任何一行（D-2 只**加索引**，不重建表）。
  * **可重复执行**：全部语句 `IF NOT EXISTS`；且每条迁移在 `schema_migrations` 记账，
    已应用则跳过。第二次运行的 stdout 会打印 `applied=0 skipped=N`，
    并且 `sqlite_master` 指纹（sha256）与前次**一致**——这就是幂等证据。
  * **WAL（D-1）**：执行 `PRAGMA journal_mode=WAL` 并**校验返回值**；仅当返回 `wal` 时设
    `synchronous=NORMAL`。
  * **安全闸**：解析到的 DB 若是仓库内正式 `yinpu.db` ⇒ **默认拒绝执行**
    （除非 `FEICUI_ALLOW_PROD_MIGRATE=1`）。正式库是唯一真源，本单所有自测一律用临时副本。

用法：
    FEICUI_DB=/tmp/feicui_copy.db ./.venv/bin/python -m app.migrations            # 迁移副本
    FEICUI_DB=/tmp/feicui_copy.db ./.venv/bin/python -m app.migrations --status   # 只读体检
"""
from __future__ import annotations

import sqlite3
import sys

from . import db
from .config import get_settings

VERSION = "1a-0001"

# 迁移按 version 升序应用；每条 = 一组语句（全部幂等）。
MIGRATIONS: list[tuple[str, str, list[str]]] = [
    (
        "1a-0001-jobs",
        "新增侧表 jobs / job_pages 及其幂等约束与索引（规范 §2.1–§2.4 / §4.1）",
        [
            # ---- jobs：一本书 = 一个 job（§2.1） ----
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id          TEXT PRIMARY KEY,
                pdf_path        TEXT NOT NULL,
                pdf_name        TEXT NOT NULL,
                book_key        TEXT,
                page_from       INTEGER,
                page_to         INTEGER,
                chunk_size      INTEGER NOT NULL DEFAULT 8,
                total_pages     INTEGER NOT NULL DEFAULT 0,
                state           TEXT NOT NULL,
                cursor_chunk_lo INTEGER,
                cursor_chunk_hi INTEGER,
                rerun           INTEGER NOT NULL DEFAULT 0,
                error           TEXT,
                created_at      TEXT NOT NULL,
                started_at      TEXT,
                finished_at     TEXT,
                updated_at      TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_jobs_pdf_path_state ON jobs(pdf_path, state)",
            # 库级兜底：同一 pdf_path 至多一个活跃 job（§3.2 S-5）
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_pdf_path
                ON jobs(pdf_path)
             WHERE state IN ('QUEUED','RUNNING','PAUSED')
            """,
            # ---- job_pages：页级断点游标落盘（§2.3） ----
            """
            CREATE TABLE IF NOT EXISTS job_pages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                pdf_name    TEXT NOT NULL,
                page        INTEGER NOT NULL,
                chunk_index INTEGER,
                state       TEXT NOT NULL,
                detected    INTEGER NOT NULL DEFAULT 0,
                inserted    INTEGER NOT NULL DEFAULT 0,
                updated     INTEGER NOT NULL DEFAULT 0,
                skipped     INTEGER NOT NULL DEFAULT 0,
                ocr_empty   INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                started_at  TEXT,
                finished_at TEXT,
                updated_at  TEXT NOT NULL,
                UNIQUE(job_id, page)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_job_pages_job_state ON job_pages(job_id, state)",
            "CREATE INDEX IF NOT EXISTS idx_job_pages_job_chunk ON job_pages(job_id, chunk_index)",
        ],
    ),
    (
        "1a-0002-stamps-indexes",
        "stamps 加索引与行级幂等唯一索引（规范 §4.1 D-2 / §2.4）——只加索引，不改列不改行",
        [
            "CREATE INDEX IF NOT EXISTS idx_stamps_pdf_page ON stamps(pdf_name, page)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stamps_pdf_page_idx ON stamps(pdf_name, page, idx)",
        ],
    ),
    (
        "1a-0003-stamps-naming-columns",
        "stamps 加法新增列 col / row / img_path_tiff（影像命名 P-C-R 回填落库；规范 §3.22/§3.23）"
        "——只加列，不改既有列、不改任何行（旧 webp 线并存）",
        [
            "ALTER TABLE stamps ADD COLUMN col INTEGER",
            "ALTER TABLE stamps ADD COLUMN row INTEGER",
            "ALTER TABLE stamps ADD COLUMN img_path_tiff TEXT",
        ],
    ),
]


def _migration_table_sql() -> str:
    return """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            note       TEXT
        )
    """


def _applied(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}


def run(skip_wal: bool = False) -> int:
    st = get_settings()
    if not st.db_path.is_file():
        print(f"✗ DB 不存在：{st.db_path}")
        return 2

    if st.is_prod_db and not st.allow_prod_migrate:
        print("✗ 拒绝：解析到的 DB 是仓库内正式库 yinpu.db（唯一真源，不得被本层写入）。")
        print(f"  解析路径 = {st.db_path}")
        print("  若确需对正式库执行，请显式设 FEICUI_ALLOW_PROD_MIGRATE=1（须 Kevin/Zang 明示）；")
        print("  自测请用副本：cp yinpu.db /tmp/feicui_copy.db && FEICUI_DB=/tmp/feicui_copy.db …")
        return 3

    with db.tx(st.db_path) as conn:
        conn.execute(_migration_table_sql())
        done = _applied(conn)
        applied = 0
        skipped = 0
        for version, note, statements in MIGRATIONS:
            if version in done:
                skipped += 1
                continue
            for sql in statements:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as exc:
                    # 幂等兜底：`ALTER TABLE … ADD COLUMN` 无 `IF NOT EXISTS`，
                    # 若列已存在（如首次事务中途尽力写入过）则视为已应用、不重复加。
                    if "duplicate column name" in str(exc).lower():
                        continue
                    raise
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, note) VALUES (?,?,?)",
                (version, db.now_iso(), note),
            )
            applied += 1
        fingerprint = db.schema_fingerprint(conn)

    wal_result = None
    if not skip_wal:
        conn = db.connect(st.db_path)
        try:
            wal_result = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(wal_result).lower() == "wal":
                conn.execute("PRAGMA synchronous=NORMAL")
        finally:
            conn.close()

    print(f"db           = {st.db_path}")
    print(f"prod_db      = {st.is_prod_db}")
    print(f"applied      = {applied}")
    print(f"skipped      = {skipped}")
    print(f"journal_mode = {wal_result}")
    print(f"schema_sha256= {fingerprint}")
    print(f"tables       = {','.join(_table_names(st.db_path))}")
    return 0


def _table_names(path) -> list[str]:
    conn = db.connect(path)
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    finally:
        conn.close()


def status() -> int:
    st = get_settings()
    if not st.db_path.is_file():
        print(f"✗ DB 不存在：{st.db_path}")
        return 2
    conn = db.connect(st.db_path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        indexes = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")]
        applied = sorted(_applied(conn)) if db.table_exists(conn, "schema_migrations") else []
        print(f"db            = {st.db_path}")
        print(f"prod_db       = {st.is_prod_db}")
        print(f"journal_mode  = {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
        print(f"schema_sha256 = {db.schema_fingerprint(conn)}")
        print(f"tables        = {','.join(tables)}")
        print(f"indexes       = {','.join(indexes)}")
        print(f"applied       = {','.join(applied) if applied else '(none)'}")
        for t in ("jobs", "job_pages"):
            if db.table_exists(conn, t):
                print(f"count[{t}]    = {conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0]}")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"--status", "status"}:
        return status()
    if argv and argv[0] in {"--help", "-h"}:
        print(__doc__)
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
