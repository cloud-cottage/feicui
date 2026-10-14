"""PDF 资料登记库（独立库 `var/pdf_registry.db`）—— Kong / output 四总目录落地单 · 2026-10-14。

口径真源：`docs/output-layout-v0.1.md`（Kevin 约定：output 四总目录
【1_Original_PDF】/【2_HighRes_PDF】/【3_Cropped_Tiff】/【4_WebP】；读 PDF 一律先取
`config/pdf_source.json` 的 `pdf_source_dir`）。

纪律（与全仓红线一致）：
* **独立库**：只读写 `var/pdf_registry.db`（`var/` 不入仓），**绝不碰 `data/yinpu.db`**；
* **幂等键＝sha256**：同一内容只占一行。文件搬移（sha 不变）⇒ **原行原地更新
  `rel_path`**；同内容多物理副本（如 `tmp.pdf` ≡ `黄牧甫印谱_*.pdf`）⇒ 只登记
  先到先得的一行（扫描按排序序），其余以 `duplicate` 记录在扫描日志，**不入册**；
* 朝代值域真源＝xiai `VALUE_DOMAINS.DYNASTY_OPTIONS`（15 值逐字同值，繁体口径）；
  **NULL 合法**（web 端人工补填），非枚举值在 API/CLI 两侧一律拒绝；
* 本模块**只依赖 stdlib**（sqlite3/pathlib/json），PyMuPDF 探测只在 ops CLI 里做，
  保证 API 进程（可能无 pymupdf）也能安全 import。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # <feicui>
DB_PATH = REPO / "var" / "pdf_registry.db"
CONFIG_PATH = REPO / "config" / "pdf_source.json"
DEFAULT_PDF_SOURCE_DIR = "output/【1_Original_PDF】"

#: 朝代值域（**逐字同值于 xiai `VALUE_DOMAINS.DYNASTY_OPTIONS`**，真源在其 `src/data/seed.js`）
DYNASTY_OPTIONS = (
    "春秋", "戰國", "秦", "漢", "魏晉", "隋唐", "宋元", "明早中期", "晚明",
    "清初", "清中期", "晚清", "民國", "新中國", "當代",
)

STATUS_PRESENT = "present"      # 文件在盘（rel_path 指向真实文件）
STATUS_MISSING = "missing"      # 已登记但盘上未寻获（sha256/rel_path 为 NULL）

_COLUMNS = (
    "id", "filename", "rel_path", "sha256", "size_bytes", "page_count", "page_mm",
    "scan_dpi", "dir_key", "isbn", "dynasty", "author", "notes", "status",
    "created_at", "updated_at",
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ddl() -> str:
    dyn = ", ".join("'" + v.replace("'", "''") + "'" for v in DYNASTY_OPTIONS)
    return f"""
CREATE TABLE IF NOT EXISTS pdf_records (
    id          INTEGER PRIMARY KEY,
    filename    TEXT    NOT NULL,                 -- 当前文件名（不含目录）
    rel_path    TEXT,                             -- 相对仓根的现路径（missing 时为 NULL）
    sha256      TEXT,                             -- 幂等键（missing 时为 NULL）
    size_bytes  INTEGER,
    page_count  INTEGER,
    page_mm     TEXT,                             -- 首页/众数页 "WxH"（毫米）
    scan_dpi    INTEGER,                          -- 由内嵌图像像素/页面盒估算；估不出为 NULL
    dir_key     TEXT,                             -- 书级目录键：真源目录下的直接子目录名（平铺为 NULL）
    isbn        TEXT,
    dynasty     TEXT CHECK (dynasty IS NULL OR dynasty IN ({dyn})),
    author      TEXT,                             -- 自由文本，人工补填
    notes       TEXT,
    status      TEXT    NOT NULL DEFAULT '{STATUS_PRESENT}',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pdf_records_sha
    ON pdf_records(sha256) WHERE sha256 IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_pdf_records_rel_path
    ON pdf_records(rel_path) WHERE rel_path IS NOT NULL;
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """现开连接（沿「接口层不缓存真值」惯例）；调用方负责 close。"""
    conn = sqlite3.connect(str(db_path or DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_ddl())
    conn.commit()


def ensure_db(db_path: Path | None = None) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    ensure_schema(conn)
    return conn


def pdf_source_dir() -> str:
    """取阅真源目录：`config/pdf_source.json.pdf_source_dir`（缺省【1_Original_PDF】）。

    读失败（文件缺失/字段非法）一律回落默认值，**绝不抛异常**（取阅口不容配置炸掉）。
    """
    try:
        val = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("pdf_source_dir")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return DEFAULT_PDF_SOURCE_DIR


def _rowdict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in _COLUMNS}


# ──────────────────────────────────────────────────────────────────────────────
# 读（GET /api/pdf-records）
# ──────────────────────────────────────────────────────────────────────────────
def list_records(
    conn: sqlite3.Connection, *, status: str | None = None, q: str | None = None,
    page: int = 1, limit: int = 50,
) -> dict:
    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    if q:
        like = f"%{q}%"
        where.append("(filename LIKE ? OR author LIKE ? OR notes LIKE ? OR isbn LIKE ?)")
        params += [like, like, like, like]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM pdf_records{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {','.join(_COLUMNS)} FROM pdf_records{clause} ORDER BY id LIMIT ? OFFSET ?",
        [*params, limit, (page - 1) * limit],
    ).fetchall()
    return {"total": total, "page": page, "limit": limit, "records": [_rowdict(r) for r in rows]}


def get_record(conn: sqlite3.Connection, record_id: int) -> dict | None:
    row = conn.execute(
        f"SELECT {','.join(_COLUMNS)} FROM pdf_records WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        return None
    return _rowdict(row)


def _get_or_raise(conn: sqlite3.Connection, record_id: int) -> dict:
    rec = get_record(conn, record_id)
    if rec is None:  # 并发删除的窄窗口；正常路径已在调用侧先查过
        raise KeyError(f"pdf_record 不存在：id={record_id}")
    return rec


# ──────────────────────────────────────────────────────────────────────────────
# 写（PATCH /api/pdf-records/{id}：朝代/作者/备注；updated_at 必刷）
# ──────────────────────────────────────────────────────────────────────────────
def validate_dynasty(value) -> str | None:
    """NULL 合法；非 15 枚举 ⇒ ValueError（API 侧转 400）。"""
    if value is None:
        return None
    if not isinstance(value, str) or value not in DYNASTY_OPTIONS:
        raise ValueError(f"朝代必须是 15 枚举之一或 null：{value!r}")
    return value


def patch_record(conn: sqlite3.Connection, record_id: int, fields: dict) -> dict:
    """fields 只接受 dynasty / author / notes（**缺省键＝不改**）；空串作者/备注 ⇒ NULL。"""
    row = conn.execute("SELECT id FROM pdf_records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise KeyError(f"pdf_record 不存在：id={record_id}")
    sets, params = [], []
    if "dynasty" in fields:
        sets.append("dynasty = ?")
        params.append(validate_dynasty(fields["dynasty"]))
    for key in ("author", "notes"):
        if key in fields:
            val = fields[key]
            if val is not None and not isinstance(val, str):
                raise ValueError(f"{key} 必须为文本或 null")
            sets.append(f"{key} = ?")
            params.append(val.strip() or None if isinstance(val, str) else None)
    if not sets:
        return _get_or_raise(conn, record_id)  # 空补丁＝原样读回
    sets.append("updated_at = ?")
    params += [_now(), record_id]
    conn.execute(f"UPDATE pdf_records SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return _get_or_raise(conn, record_id)


# ──────────────────────────────────────────────────────────────────────────────
# 扫描入库（ops/pdf-registry/scan_pdf_registry.py 调用；幂等 by sha256）
# ──────────────────────────────────────────────────────────────────────────────
def apply_scan_row(
    conn: sqlite3.Connection, *, filename: str, rel_path: str, sha256: str,
    size_bytes: int, page_count: int | None, page_mm: str | None,
    scan_dpi: int | None, dir_key: str | None, isbn: str | None = None,
    notes: str | None = None,
) -> tuple[str, dict]:
    """⇒ (action, row)。action ∈ insert / noop / update / moved / duplicate。

    * `insert`    新内容 ⇒ 新行；
    * `noop`      同路径同 sha 同派生值 ⇒ 什么都不改（幂等）；
    * `update`    同路径但内容/派生值变了 ⇒ 原地刷新；
    * `moved`     sha 已在册但旧 rel_path 已不在盘 ⇒ **原行原地更新 rel_path**（搬移）；
    * `duplicate` sha 在册且旧文件仍在盘（真·同内容多副本）⇒ 不建行，返回在册行供日志。
    """
    now = _now()
    derived = (size_bytes, page_count, page_mm, scan_dpi, dir_key)
    row = conn.execute("SELECT * FROM pdf_records WHERE rel_path = ?", (rel_path,)).fetchone()
    if row is not None:
        if row["sha256"] == sha256 and derived == (
            row["size_bytes"], row["page_count"], row["page_mm"], row["scan_dpi"], row["dir_key"]
        ):
            return "noop", _rowdict(row)
        conn.execute(
            "UPDATE pdf_records SET sha256=?, size_bytes=?, page_count=?, page_mm=?, "
            "scan_dpi=?, dir_key=?, filename=?, status=?, updated_at=? WHERE id=?",
            (sha256, *derived, filename, STATUS_PRESENT, now, row["id"]),
        )
        conn.commit()
        return "update", _get_or_raise(conn, row["id"])

    row2 = conn.execute("SELECT * FROM pdf_records WHERE sha256 = ?", (sha256,)).fetchone()
    if row2 is not None:
        old_abs = REPO / row2["rel_path"] if row2["rel_path"] else None
        if old_abs is not None and not old_abs.is_file():
            conn.execute(
                "UPDATE pdf_records SET rel_path=?, filename=?, size_bytes=?, page_count=?, "
                "page_mm=?, scan_dpi=?, dir_key=?, status=?, updated_at=? WHERE id=?",
                (rel_path, filename, *derived, STATUS_PRESENT, now, row2["id"]),
            )
            conn.commit()
            return "moved", _get_or_raise(conn, row2["id"])
        return "duplicate", _rowdict(row2)

    cur = conn.execute(
        "INSERT INTO pdf_records (filename, rel_path, sha256, size_bytes, page_count, page_mm, "
        "scan_dpi, dir_key, isbn, dynasty, author, notes, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (filename, rel_path, sha256, *derived, isbn, None, None, notes, STATUS_PRESENT, now, now),
    )
    conn.commit()
    return "insert", _get_or_raise(conn, int(cur.lastrowid or 0))


def register_missing(conn: sqlite3.Connection, filename: str, notes: str | None = None) -> tuple[str, dict]:
    """登记「已收录但盘上未寻获」的书：status=missing、sha/rel_path 为 NULL。

    同名（filename 逐字）missing 行已存在 ⇒ noop；同名内容已在册（present）⇒ already-present。
    """
    now = _now()
    hit = conn.execute(
        "SELECT * FROM pdf_records WHERE filename = ? AND status = ?",
        (filename, STATUS_MISSING),
    ).fetchone()
    if hit is not None:
        return "noop", _rowdict(hit)
    present = conn.execute(
        "SELECT * FROM pdf_records WHERE filename = ?", (filename,)
    ).fetchone()
    if present is not None:
        return "already-present", _rowdict(present)
    cur = conn.execute(
        "INSERT INTO pdf_records (filename, status, notes, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (filename, STATUS_MISSING, notes, now, now),
    )
    conn.commit()
    return "insert", _get_or_raise(conn, int(cur.lastrowid or 0))
