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

两条登记表（体例相同：version 去重 + `schema_migrations` 记账 + 已应用即跳过）：
  * `MIGRATIONS`：静态 SQL 语句组（既有）。
  * `DYNAMIC_MIGRATIONS`：须**现算 SQL** 的表重建类（既有表被 `CREATE TABLE IF NOT EXISTS`
    烘死了旧值域时用；详见该段注释）。

用法：
    FEICUI_DB=/tmp/feicui_copy.db ./.venv/bin/python -m app.migrations            # 迁移副本
    FEICUI_DB=/tmp/feicui_copy.db ./.venv/bin/python -m app.migrations --status   # 只读体检
    FEICUI_DB=/tmp/feicui_copy.db ./.venv/bin/python -m app.migrations \
        --only 1a-0006-dynasty-check-rebuild                                     # 只跑点名的那条
    （`--only` 可逗号分隔多条；默认不传＝跑全部，语义与既有版本一字相同）
"""
from __future__ import annotations

import re
import sqlite3
import sys
from typing import Callable, Sequence

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
    (
        "1a-0004-stamps-dedup-columns",
        "stamps 加法新增列 dup_kind / dup_of_id / dup_algo（印面去重方案 A 的历史行标记；"
        "口径真源 ops/dedup-calibration/ 标定 commit f5b901f）——只加列，不改既有列、不改任何行；"
        "值由 server/app/dedup_apply.py 幂等写入（新 job 在检测器侧去重、不写这三列）",
        [
            "ALTER TABLE stamps ADD COLUMN dup_kind TEXT",
            "ALTER TABLE stamps ADD COLUMN dup_of_id INTEGER",
            "ALTER TABLE stamps ADD COLUMN dup_algo TEXT",
            # 部分索引：只索引被标记行（命中 E3/导出侧「排除 dup_kind IS NULL」的过滤）
            "CREATE INDEX IF NOT EXISTS idx_stamps_dup_kind ON stamps(dup_kind) WHERE dup_kind IS NOT NULL",
        ],
    ),
    (
        "1a-0005-jobs-print-size",
        "jobs 加法新增列 print_size_1to1（「印刷尺寸即实物尺寸」勾选框落 job 记录；Kevin ② 2026-10）"
        "——只加列，不改既有列、不改任何行；NULL＝请求未指定（读面回退 config/book_dir_keys.json）",
        [
            "ALTER TABLE jobs ADD COLUMN print_size_1to1 INTEGER",
        ],
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# 动态迁移（须**现算 SQL** 的「表重建」类）——体例与 `MIGRATIONS` 完全相同：
#   同一份 `schema_migrations` 记账、同一趟事务（`db.tx`）、已应用即跳过 ⇒ 同样幂等。
# 差异只在 SQL 没法写成静态字面量（须读现存建表语句、比对值域），故用可调用体。
#
# 背景（本单）：`pdf_registry._ddl()` 用**当次值域**拼出建表语句里的
# `CHECK (dynasty IS NULL OR dynasty IN (…))`，而建表是 `CREATE TABLE IF NOT EXISTS`
# ⇒ **已存在的库不会跟着改约束**。朝代首值 `春秋` 更名为 `商周暨春秋` 后，库内约束仍是旧
# 值域：UI 写新值撞 `IntegrityError: CHECK constraint failed`，写旧值反而**仍然通过**
# （校验层只收新值 ⇒ 两侧互撑死）。
#
# 处置：把这类表的约束重建到当前值域。值域真源**单向取自** `pdf_registry.DYNASTY_OPTIONS`
# （本文件**不得**复制值域字面量——同一值域存两份正是本缺陷的成因）。
_DYN_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*dynasty\s+IS\s+NULL\s+OR\s+dynasty\s+IN\s*\((?P<vals>[^)]*)\)\s*\)",
    re.IGNORECASE,
)
#: 匹配 `CREATE TABLE <名>` 的表名（四种引号形态），用于把新表先建成临时名
_CREATE_TABLE_RE = re.compile(
    r"(?i)\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r'(?:"(?P<dq>[^"]+)"|\[(?P<bq>[^\]]+)\]|`(?P<btq>[^`]+)`|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))'
)
_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")
_REBUILD_SUFFIX = "__ckrebuild_new"


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def dynasty_domain() -> tuple[str, ...]:
    """朝代值域（斐萃侧单一真源）＝`app.pdf_registry.DYNASTY_OPTIONS`。

    延迟导入：避免 `app` 包内模块级循环依赖（`pdf_registry` 只依赖标准库）。
    """
    from . import pdf_registry

    return tuple(pdf_registry.DYNASTY_OPTIONS)


def _dynasty_check_clause(values: Sequence[str]) -> str:
    """按 `pdf_registry._ddl()` 的同款写法拼 CHECK 段（同一形状才好逐字替换）。"""
    return "CHECK (dynasty IS NULL OR dynasty IN (" + ", ".join(_lit(v) for v in values) + "))"


def _domain_of(clause: str) -> tuple[str, ...]:
    """从 CHECK 段里逐字取出值域（按 `'…'` 字面量切，逗号/空格的书写差异不影响判读）。"""
    m = _DYN_CHECK_RE.search(clause)
    raw = m.group("vals") if m else clause
    return tuple(v.replace("''", "'") for v in _LITERAL_RE.findall(raw))


def _dynasty_check_tables(conn) -> list[tuple[str, str, str]]:
    """库内所有带 `CHECK (dynasty …)` 的表 ⇒ (表名, 建表 SQL 原文, 现存 CHECK 段原文)。"""
    out: list[tuple[str, str, str]] = []
    for name, sql in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
    ):
        m = _DYN_CHECK_RE.search(sql)
        if m is not None:
            out.append((name, sql, m.group(0)))
    return out


def _table_columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % _q(table))]


def _incoming_fk(conn, table: str) -> list[str]:
    """其它表指向本表的外键。有则本层**拒绝重建**（`PRAGMA foreign_keys=ON` 下拆父表不安全），
    宁可显式报错也不静默改坏——本单目标表无入向外键。"""
    refs: list[str] = []
    for (other,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
    ).fetchall():
        if other == table:
            continue
        for fk in conn.execute("PRAGMA foreign_key_list(%s)" % _q(other)):
            if fk[2] == table:
                refs.append(f"{other}.{fk[3]}→{table}.{fk[4]}")
    return refs


def _rebuild_one(conn, table: str, stored_sql: str, clause: str, want: tuple[str, ...]) -> str:
    """SQLite 标准重建步骤：建新表 → 拷行 → 校验行集同值 → 删旧表 → 改名回原名 → 复原从属对象。
    全程在调用方的同一事务内（不做 `DROP`/`COMMIT`，失败即整体回滚）。"""
    if _incoming_fk(conn, table):
        raise RuntimeError(f"拒绝重建 {table}：存在指向它的外键 {_incoming_fk(conn, table)}")
    cols = _table_columns(conn, table)
    if not cols:
        raise RuntimeError(f"拒绝重建 {table}：取不到列清单（PRAGMA table_info 为空）")

    tmp = table + _REBUILD_SUFFIX
    # 从属对象（索引/触发器）与 `sqlite_sequence` 号位：DROP 旧表会连带删掉，故先取原文
    aux = [
        r[0]
        for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger')"
            " AND sql IS NOT NULL ORDER BY type, name",
            (table,),
        ).fetchall()
    ]
    seq = None
    if db.table_exists(conn, "sqlite_sequence"):
        row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
        seq = row[0] if row else None
    before = conn.execute("SELECT count(*) FROM %s" % _q(table)).fetchone()[0]

    new_sql = stored_sql.replace(clause, _dynasty_check_clause(want), 1)
    m = _CREATE_TABLE_RE.search(new_sql)
    if m is None:
        raise RuntimeError(f"拒绝重建 {table}：建表 SQL 里解析不出表名")
    tmp_sql = new_sql[: m.start()] + "CREATE TABLE " + _q(tmp) + new_sql[m.end():]

    conn.execute("DROP TABLE IF EXISTS %s" % _q(tmp))
    conn.execute(tmp_sql)
    collist = ", ".join(_q(c) for c in cols)
    conn.execute(f"INSERT INTO {_q(tmp)} ({collist}) SELECT {collist} FROM {_q(table)}")

    # 拷行后逐行同值：两个方向的 EXCEPT 都必须为空（列序一致 ⇒ `SELECT *` 可直比）
    miss = conn.execute(
        f"SELECT count(*) FROM (SELECT * FROM {_q(table)} EXCEPT SELECT * FROM {_q(tmp)})"
    ).fetchone()[0]
    extra = conn.execute(
        f"SELECT count(*) FROM (SELECT * FROM {_q(tmp)} EXCEPT SELECT * FROM {_q(table)})"
    ).fetchone()[0]
    if miss or extra:
        raise RuntimeError(f"拒绝重建 {table}：拷行后行集不一致 missing={miss} extra={extra}")

    conn.execute("DROP TABLE %s" % _q(table))
    conn.execute("ALTER TABLE %s RENAME TO %s" % (_q(tmp), _q(table)))
    for sql_aux in aux:
        conn.execute(sql_aux)
    if seq is not None:
        conn.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (seq, table))

    after = conn.execute("SELECT count(*) FROM %s" % _q(table)).fetchone()[0]
    if after != before:
        raise RuntimeError(f"拒绝重建 {table}：重建后行数 {after} ≠ 迁移前 {before}")
    return f"{table}: 值域 {len(_domain_of(clause))}→{len(want)} 值；行数 {before}→{after}；从属对象复原 {len(aux)}"


def migrate_dynasty_check(conn) -> str:
    """把库里凡 `dynasty` 约束**仍非当前值域**的表重建到当前值域；已是当前值域则逐表跳过。"""
    want = dynasty_domain()
    done: list[str] = []
    skipped: list[str] = []
    for table, stored_sql, clause in _dynasty_check_tables(conn):
        if _domain_of(clause) == want:
            skipped.append(table)
            continue
        done.append(_rebuild_one(conn, table, stored_sql, clause, want))
    if not done:
        who = ",".join(skipped) if skipped else "库内无 dynasty CHECK 表"
        return f"无需重建（{who}：已是当前值域 / 无约束）"
    tail = f"；跳过（已新）{','.join(skipped)}" if skipped else ""
    return "已重建 " + "; ".join(done) + tail


# ──────────────────────────────────────────────────────────────────────────────
# 动态迁移（**值域收敛**类：只改既有行的某个枚举列，不改表结构）——体例与上面完全相同：
# 同一份 `schema_migrations` 记账、同一趟 `db.tx` 事务、已应用即跳过 ⇒ 同样幂等。
#
# 背景（本单，规范 §3.53.5）：真库 `seals.dynasty` 里混着历史批次的旧写法
# （`战国` 23 行 / `秦汉` 26 行），与云侧已收敛的繁体口径不一致。处置：把该列**收敛**到
# 当前值域——点名的一条旧写法映射到新值；**其余非空且 ∉ 值域者一律清 NULL（未著錄）**，
# 绝不猜「秦汉 该算 秦 还是 漢」这类史料口径。值域真源**单向取自**同一处
# `pdf_registry.DYNASTY_OPTIONS`（本文件**不得**复制 15 类字面量）。
#: 点名映射表：**只登记有明示口径的旧写法**（§3.53.5 点名 `战国` ⇒ `戰國`）。
#: 不在此表的旧值**不得臆测**映射到某个新值——那是改写史料口径，不是归一化；
#: 一律走「清 NULL（未著錄）」这一条，且逐值报出被清行数。
_DYNASTY_RENAMES: dict[str, str] = {
    "战国": "戰國",
}


def converge_seals_dynasty(conn: sqlite3.Connection) -> str:
    """把 `seals.dynasty` 收敛到当前值域（**只改这一列**，`record_json`/`dynasty_source`/其它列一字不动）。

    规则（顺序即优先级）：
      1. `dynasty IS NULL` ⇒ 不动（未著錄本就合法）；
      2. `dynasty ∈ 值域`（`pdf_registry.DYNASTY_OPTIONS`）⇒ 不动（已是目标态）；
      3. `dynasty ∈ _DYNASTY_RENAMES`（点名旧写法）⇒ 改为映射的新值；
      4. 其余非空且 ∉ 值域 ⇒ 清 `NULL`（逐值报出行数）。
    幂等判据：无第 3/4 类值即「无需改动」（重跑 changed=0）。
    护栏（任一不成立 ⇒ 抛错 ⇒ 调用方 `db.tx` **整体回滚**，库保持原样）：
      * `seals` 表或 `dynasty` 列取不到；
      * 映射目标本身不在值域内（真源与映射表打架）；
      * 某值的实改行数 ≠ 迁移前按该值点出的行数（意外多行影响）。
    """
    want = dynasty_domain()
    if not db.table_exists(conn, "seals"):
        raise RuntimeError("拒绝 1a-0007：库内取不到 seals 表（本迁移只作用于 yinpu schema）")
    cols = _table_columns(conn, "seals")
    if "dynasty" not in cols:
        raise RuntimeError("拒绝 1a-0007：seals 取不到 dynasty 列（PRAGMA table_info 里没有）")

    total = conn.execute("SELECT count(*) FROM seals").fetchone()[0]
    rows = conn.execute(
        "SELECT dynasty, count(*) FROM seals WHERE dynasty IS NOT NULL GROUP BY dynasty ORDER BY dynasty"
    ).fetchall()
    plan = [(v, n) for v, n in rows if v not in want]
    if not plan:
        return f"无需改动（seals.dynasty 全为当前值域或 NULL；{total} 行）"

    detail: list[str] = []
    changed = 0
    for value, n in plan:
        target = _DYNASTY_RENAMES.get(value)  # 未登记 ⇒ None ⇒ 清 NULL
        if target is not None and target not in want:
            raise RuntimeError(
                f"拒绝 1a-0007：映射 {value!r}→{target!r} 的目标不在值域内（真源 DYNASTY_OPTIONS）"
            )
        cur = conn.execute("UPDATE seals SET dynasty=? WHERE dynasty=?", (target, value))
        got = cur.rowcount
        if got != n:
            raise RuntimeError(
                f"拒绝 1a-0007：值 {value!r} 迁移前为 {n} 行、实改 {got} 行（意外多行影响）"
            )
        changed += got
        label = repr(target) if target is not None else "NULL"
        detail.append(f"{value!r}⇒{label} {got} 行")

    after = conn.execute("SELECT count(*) FROM seals").fetchone()[0]
    left = conn.execute(
        "SELECT count(*) FROM seals WHERE dynasty IS NOT NULL AND dynasty NOT IN (%s)"
        % ", ".join("?" * len(want)),
        want,
    ).fetchone()[0]
    if after != total or left:
        raise RuntimeError(f"拒绝 1a-0007：收敛后自检不过（行数 {total}→{after}；残余越域非空 {left} 行）")
    return f"changed={changed}（{'；'.join(detail)}）；seals 共 {total} 行，收敛后越域非空 0 行"


DYNAMIC_MIGRATIONS: list[tuple[str, str, Callable[[sqlite3.Connection], str]]] = [
    (
        "1a-0006-dynasty-check-rebuild",
        "把库内烘焙了旧值域的 dynasty CHECK 约束重建为当前值域（朝代首值 春秋 ⇒ 商周暨春秋；"
        "真源 app/pdf_registry.DYNASTY_OPTIONS）——标准重建 建新表→拷行→删旧表→改名，"
        "列/行/id 与索引触发器全保；已是当前值域或无该约束则跳过",
        migrate_dynasty_check,
    ),
    (
        "1a-0007-yinpu-dynasty-convergence",
        "seals.dynasty 收敛到当前值域（规范 §3.53.5）：点名 战国⇒戰國；其余非空且 ∉ 值域"
        "（如 秦汉）一律清 NULL（未著錄）——只改 dynasty 一列，record_json/dynasty_source 等一字不动；"
        "真源 app/pdf_registry.DYNASTY_OPTIONS；逐值报行数、护栏不成立即整体回滚；重跑 changed=0",
        converge_seals_dynasty,
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


def run(skip_wal: bool = False, only: Sequence[str] | None = None) -> int:
    st = get_settings()
    if not st.db_path.is_file():
        print(f"✗ DB 不存在：{st.db_path}")
        return 2

    # `only`：只跑点名的迁移（静态/动态皆可）——**默认行为一字不动**（不传＝全跑）。
    # 用途：feicui 侧已是多库（pdf_registry / seal_ingest / person_ingest …），
    # 非 yinpu schema 的库跑不动早期面向 `stamps` 的静态迁移（`no such table: main.stamps`），
    # 此时按 version 点名执行，既不改既有语义、也不对别的库做任何事。
    wanted = set(only or ())
    if wanted:
        known = {v for v, _n, _s in MIGRATIONS} | {v for v, _n, _f in DYNAMIC_MIGRATIONS}
        unknown = sorted(wanted - known)
        if unknown:
            print(f"✗ 未知迁移 version：{','.join(unknown)}（可选：{','.join(sorted(known))}）")
            return 4

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
            if wanted and version not in wanted:
                continue
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
        # 动态迁移：同一份记账、同一趟事务；`fn` 自带幂等判据（已新/无约束即免动）
        for version, note, fn in DYNAMIC_MIGRATIONS:
            if wanted and version not in wanted:
                continue
            if version in done:
                skipped += 1
                print(f"[{version}] skipped（已记账，未执行）")
                continue
            detail = fn(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, note) VALUES (?,?,?)",
                (version, db.now_iso(), note),
            )
            applied += 1
            print(f"[{version}] {detail}")
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
    print(f"only         = {','.join(sorted(wanted)) if wanted else '(all)'}")
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
        for table, _stored, clause in _dynasty_check_tables(conn):
            cur = _domain_of(clause)
            state = "已是当前值域" if cur == dynasty_domain() else "旧值域（需迁移）"
            print(f"dynasty_check[{table}] = {state}（{len(cur)} 值）")
        for t in ("jobs", "job_pages"):
            if db.table_exists(conn, t):
                print(f"count[{t}]    = {conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0]}")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            i += 1
            if i >= len(argv):
                print("✗ --only 需要一个 version 参数（可逗号分隔多个）")
                return 4
            only += [v.strip() for v in argv[i].split(",") if v.strip()]
        elif a.startswith("--only="):
            only += [v.strip() for v in a[len("--only="):].split(",") if v.strip()]
        else:
            rest.append(a)
        i += 1
    argv = rest
    if argv and argv[0] in {"--status", "status"}:
        return status()
    if argv and argv[0] in {"--help", "-h"}:
        print(__doc__)
        return 0
    return run(only=only or None)


if __name__ == "__main__":
    raise SystemExit(main())
