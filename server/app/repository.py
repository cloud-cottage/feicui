"""业务真值层 —— Kong / 阶段 1a。

**本层是唯一碰 SQL 的地方；所有数值一律「现开连接 → 现查现算」**（规范 §3.2 S-1 / S-4）：
没有任何进程内计数器、没有缓存、没有「估算推进」。接口层重启后 E2 的读数与重启前逐字相同。

规范锚点：§2.1（1 书 = 1 job）、§2.2（状态机 / FAILED_PARTIAL 不得当 DONE）、§2.3（页级游标）、
§2.4（行级 `(pdf_name,page,idx)` 幂等）、§3.2 S-1/S-2/S-4/S-5、§4.2（影像路径相对 feicui/）。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from . import db
from . import naming

log = logging.getLogger("feicui.repository")

# 状态机（§2.2 + §3.2 S-5）
ACTIVE_STATES = ("QUEUED", "RUNNING", "PAUSED")
TERMINAL_STATES = ("DONE", "FAILED_PARTIAL")
PAGE_STATES = ("PENDING", "RUNNING", "DONE", "FAILED")

# E5 缺失原因码（自由字符串，规范 §3.1 E5 只要求 `reason` 存在）
REASON_FILE_MISSING = "file_missing"
REASON_IMG_PATH_NULL = "img_path_null"
REASON_TEXT_EMPTY = "text_empty"


class JobNotFound(Exception):
    """E2 / E5：job_id 不存在 ⇒ 404（S-6）。"""


class ActiveJobExists(Exception):
    """E1：同 pdf_path 已有活跃 job ⇒ 409 + 既有 job_id（S-5）。"""

    def __init__(self, existing: dict[str, Any]) -> None:
        super().__init__(existing.get("job_id", ""))
        self.existing = existing


def new_job_id() -> str:
    return "job-" + uuid.uuid4().hex


def pdf_name_of(pdf_path: str | Path) -> str:
    """书名口径 ＝ PDF 文件名（与 `stamps.pdf_name` 的既有取值同形）。"""
    return os.path.basename(str(pdf_path).rstrip("/"))


# --------------------------------------------------------------------------- E1
def find_active_job(conn, pdf_path: str) -> dict[str, Any] | None:
    row = db.query_one(
        conn,
        f"""SELECT job_id, state, total_pages, created_at, updated_at, pdf_path
              FROM jobs
             WHERE pdf_path = ? AND state IN ({','.join('?' * len(ACTIVE_STATES))})
             ORDER BY created_at DESC LIMIT 1""",
        (pdf_path, *ACTIVE_STATES),
    )
    return dict(row) if row else None


def create_job(
    db_path: Path | str,
    *,
    pdf_path: str,
    pdf_name: str,
    page_from: int,
    page_to: int,
    chunk_size: int,
    rerun: bool,
    total_pages: int,
) -> dict[str, Any]:
    """一个事务内写 `jobs` + 全部 `job_pages(PENDING)`（§4.3 提交点 = chunk 边界的落库侧）。

    入库语义＝**入队**：`state='QUEUED'`；实际执行属 1b 的 worker 池（本单不做）。
    """
    job_id = new_job_id()
    now = db.now_iso()
    pages = [
        (job_id, pdf_name, page, (page - page_from) // chunk_size, "PENDING", now)
        for page in range(page_from, page_to + 1)
    ]
    try:
        with db.tx(db_path) as conn:
            conn.execute(
                """INSERT INTO jobs(
                       job_id, pdf_path, pdf_name, page_from, page_to, chunk_size,
                       total_pages, state, rerun, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    pdf_path,
                    pdf_name,
                    page_from,
                    page_to,
                    chunk_size,
                    total_pages,
                    "QUEUED",
                    1 if rerun else 0,
                    now,
                    now,
                ),
            )
            conn.executemany(
                """INSERT INTO job_pages(job_id, pdf_name, page, chunk_index, state, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                pages,
            )
    except Exception as exc:  # 并发下的库级兜底：uq_jobs_active_pdf_path 命中
        if "uq_jobs_active_pdf_path" in str(exc) or "UNIQUE constraint failed: jobs.pdf_path" in str(exc):
            with db.ro(db_path) as conn:
                existing = find_active_job(conn, pdf_path)
            if existing:
                raise ActiveJobExists(existing) from exc
        raise
    return {"job_id": job_id, "state": "QUEUED", "total_pages": total_pages, "created_at": now}


# --------------------------------------------------------------------------- E2
def get_job_row(conn, job_id: str) -> dict[str, Any]:
    row = db.query_one(conn, "SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    if row is None:
        raise JobNotFound(job_id)
    return dict(row)


def recompute_progress(conn, job_id: str) -> dict[str, Any]:
    """E2 的**全部**读数在这里由库内复算产生（S-1：不得用内存计数器 / 估算值）。"""
    agg = db.query_one(
        conn,
        """SELECT COUNT(*)                                    AS total_pages,
                  SUM(CASE WHEN state = 'DONE' THEN 1 ELSE 0 END) AS done_pages,
                  COALESCE(SUM(detected), 0)                  AS detected,
                  COALESCE(SUM(inserted), 0)                  AS inserted,
                  COALESCE(SUM(updated), 0)                   AS updated,
                  COALESCE(SUM(skipped), 0)                   AS skipped,
                  COALESCE(SUM(ocr_empty), 0)                 AS ocr_empty,
                  MIN(CASE WHEN state <> 'DONE' THEN chunk_index END) AS chunk_lo,
                  MAX(CASE WHEN state =  'DONE' THEN chunk_index END) AS chunk_hi
             FROM job_pages
            WHERE job_id = ?""",
        (job_id,),
    )
    failed_pages = [
        r[0]
        for r in db.query_all(
            conn,
            "SELECT page FROM job_pages WHERE job_id = ? AND state = 'FAILED' ORDER BY page",
            (job_id,),
        )
    ]
    return {
        "total_pages": int(agg["total_pages"] or 0),
        "done_pages": int(agg["done_pages"] or 0),
        "failed_pages": failed_pages,
        "cursor": {"chunk_lo": agg["chunk_lo"], "chunk_hi": agg["chunk_hi"]},
        "counters": {
            "detected": int(agg["detected"]),
            "inserted": int(agg["inserted"]),
            "updated": int(agg["updated"]),
            "skipped": int(agg["skipped"]),
            "ocr_empty": int(agg["ocr_empty"]),
        },
    }


def effective_state(stored_state: str, failed_pages: list[int]) -> str:
    """S-2：有 `failed_pages` 时 `state` **不得**为 `DONE` ⇒ 下行到 FAILED_PARTIAL。

    **只降级、不升级**：绝不把 QUEUED/RUNNING 报成 DONE（1a 无 worker，state 由库给出）。
    """
    if stored_state == "DONE" and failed_pages:
        return "FAILED_PARTIAL"
    return stored_state


def get_progress(db_path: Path | str, job_id: str) -> dict[str, Any]:
    """E2 完整读数（库内复算），返回形状＝§3.1 E2 逐字段。"""
    with db.ro(db_path) as conn:
        job = get_job_row(conn, job_id)
        progress = recompute_progress(conn, job_id)
    return {
        "job_id": job["job_id"],
        "state": effective_state(job["state"], progress["failed_pages"]),
        "total_pages": progress["total_pages"],
        "done_pages": progress["done_pages"],
        "failed_pages": progress["failed_pages"],
        "cursor": progress["cursor"],
        "counters": progress["counters"],
        "started_at": job["started_at"],
        "updated_at": job["updated_at"],
    }


# --------------------------------------------------------------------------- E5
def _job_scope(conn, job_id: str) -> tuple[str, int, int]:
    job = get_job_row(conn, job_id)
    row = db.query_one(
        conn,
        "SELECT MIN(page) AS lo, MAX(page) AS hi FROM job_pages WHERE job_id = ?",
        (job_id,),
    )
    lo = int(row["lo"]) if row and row["lo"] is not None else int(job["page_from"] or 1)
    hi = int(row["hi"]) if row and row["hi"] is not None else int(job["page_to"] or lo)
    return job["pdf_name"], lo, hi


def _original_rel_from_tiff(tiff_rel: str) -> str | None:
    """校正件相对路径 → **同目录同名 `-O.tiff`** 相对路径（口径件 §6 回落链第②段）。

    `output/books/<目录键>/P<页>-C<列>-R<行>.tiff` ⇒ `…/P<页>-C<列>-R<行>-O.tiff`
    （同目录；O 名字形由 `naming.original_name_from_corrected` 派生，**不落库、不加列**）。
    入参不合校正件名字形 ⇒ `None`（不臆造路径）。
    """
    d, base = os.path.split(str(tiff_rel))
    o_name = naming.original_name_from_corrected(base)
    if not o_name:
        return None
    return os.path.join(d, o_name) if d else o_name


def _stamp_image_on_disk(root_abs: Path, img_path: Any, img_path_tiff: Any) -> bool:
    """该行影像是否在盘上 —— **与 E6 同一解析顺序**：
    `img_path_tiff`（校正件）→ **同目录同名 `-O.tiff`**（原始切片）→ `img_path`（历史 webp）。

    越界 / 绝对路径（§3.5 纪律④）在此**只当作「不在盘上」**：E5 是只读清单，不得抛异常打断整表。
    """
    candidates: list[Any] = [img_path_tiff]
    if img_path_tiff is not None and str(img_path_tiff).strip():
        candidates.append(_original_rel_from_tiff(str(img_path_tiff).strip()))
    candidates.append(img_path)
    for raw in candidates:
        if raw is None or str(raw).strip() == "":
            continue
        rel = str(raw).strip()
        if os.path.isabs(rel):
            continue
        p = (root_abs / rel).resolve()
        if _is_within(p, root_abs) and p.is_file():
            return True
    return False


def missing_items(
    db_path: Path | str, job_id: str, kind: str, *, root: Path
) -> tuple[list[dict[str, Any]], tuple[str, int, int]]:
    """E5 复算（§3.1 E5）：范围＝该 job 的 `pdf_name` × `[page_from,page_to]`。

    `kind='image'`：逐条按 **E6 同一解析顺序**（优先 `img_path_tiff`、回退 `img_path`）
    `os.path.exists(<root>/<相对路径>)`（**只读文件系统，不写不建**）。
    —— webp 退场后新行的影像只落 TIFF（`img_path_tiff`）；若仍只看 `img_path`，新 job 会**整本**
    误报「影像缺失」，与 E6（能照常取图）自相矛盾。**`img_path` 取值一字未改**，此处只是读法对齐。
    `kind='text'` ：`text IS NULL OR trim(text)=''`。
    """
    if kind not in {"image", "text"}:
        raise ValueError(f"unsupported kind: {kind}")

    items: list[dict[str, Any]] = []
    with db.ro(db_path) as conn:
        pdf_name, lo, hi = _job_scope(conn, job_id)
        if kind == "image":
            rows = db.query_all(
                conn,
                """SELECT pdf_name, page, idx, img_path, img_path_tiff
                     FROM stamps
                    WHERE pdf_name = ? AND page BETWEEN ? AND ?
                    ORDER BY page, idx""",
                (pdf_name, lo, hi),
            )
            root_abs = Path(root).resolve()
            for r in rows:
                img_path = r["img_path"]
                tiff = r["img_path_tiff"]
                if (img_path is None or str(img_path).strip() == "") and (
                    tiff is None or str(tiff).strip() == ""
                ):
                    reason = REASON_IMG_PATH_NULL
                elif _stamp_image_on_disk(root_abs, img_path, tiff):
                    continue
                else:
                    reason = REASON_FILE_MISSING
                items.append(
                    {
                        "pdf_name": r["pdf_name"],
                        "page": int(r["page"]),
                        "idx": int(r["idx"]),
                        "img_path": img_path,
                        "reason": reason,
                    }
                )
        else:
            rows = db.query_all(
                conn,
                """SELECT pdf_name, page, idx, img_path
                     FROM stamps
                    WHERE pdf_name = ? AND page BETWEEN ? AND ?
                      AND (text IS NULL OR trim(text) = '')
                    ORDER BY page, idx""",
                (pdf_name, lo, hi),
            )
            for r in rows:
                items.append(
                    {
                        "pdf_name": r["pdf_name"],
                        "page": int(r["page"]),
                        "idx": int(r["idx"]),
                        "img_path": r["img_path"],
                        "reason": REASON_TEXT_EMPTY,
                    }
                )
    return items, (pdf_name, lo, hi)


# =========================================================================== 执行层（阶段 1b-i）
# 规范锚点：§2.3（页级断点游标**落盘**、可续跑）、§2.4（行级 `(pdf_name,page,idx)` 幂等）、
# §4.3（**提交点 = chunk 边界**；WAL 单写者 ⇒ **唯一写者进程**）、§5.3（单 job 页内串行）。
#
# **谁调用**：只有 `app/pool.py`（常驻 worker 池 supervisor）调用本节函数；
# 接口层（`routers/**`）**不**调用 —— 读写两条路径分开，接口层仍是「现查现算」。
# 本节的每个函数都是「一个事务」的粒度；池进程是唯一写者，故不存在多写者竞争。
ON_CONFLICT_SKIP = "skip"
ON_CONFLICT_UPDATE = "update"


def list_active_jobs(db_path: Path | str) -> list[dict[str, Any]]:
    """当前活跃（`QUEUED`/`RUNNING`/`PAUSED`）的 job，按建单时间升序（FIFO 取任务用）。"""
    with db.ro(db_path) as conn:
        rows = db.query_all(
            conn,
            f"""SELECT job_id, pdf_path, pdf_name, page_from, page_to, chunk_size,
                       total_pages, state, created_at
                  FROM jobs
                 WHERE state IN ({','.join('?' * len(ACTIVE_STATES))})
                 ORDER BY created_at, job_id""",
            ACTIVE_STATES,
        )
    return [dict(r) for r in rows]


def claim_job(db_path: Path | str, *, job_id: str | None = None) -> dict[str, Any] | None:
    """认领一个 job 并**把它置为 RUNNING**；同时把该 job 残留的 `RUNNING` 页**退回 PENDING**。

    后半句就是**断点续跑**的入口（§2.3）：进程被 SIGKILL 后，页游标（`job_pages`）留在库里，
    上次「在飞但未提交」的页状态可能是 `RUNNING` —— 重启后第一个动作就是让它们重新可派，
    而**已提交（`DONE`）的页不动**（§2.3「已提交页不得重算重写」）。
    """
    now = db.now_iso()
    with db.tx(db_path) as conn:
        if job_id:
            row = db.query_one(
                conn,
                f"""SELECT job_id, pdf_path, pdf_name, page_from, page_to, chunk_size, total_pages, state
                      FROM jobs WHERE job_id = ? AND state IN ({','.join('?' * len(ACTIVE_STATES))})""",
                (job_id, *ACTIVE_STATES),
            )
        else:
            row = db.query_one(
                conn,
                f"""SELECT job_id, pdf_path, pdf_name, page_from, page_to, chunk_size, total_pages, state
                      FROM jobs WHERE state IN ({','.join('?' * len(ACTIVE_STATES))})
                     ORDER BY created_at, job_id LIMIT 1""",
                ACTIVE_STATES,
            )
        if row is None:
            return None
        cur = conn.execute(
            """UPDATE job_pages
                  SET state = 'PENDING', started_at = NULL, error = NULL, updated_at = ?
                WHERE job_id = ? AND state = 'RUNNING'""",
            (now, row["job_id"]),
        )
        reset = cur.rowcount
        conn.execute(
            """UPDATE jobs
                  SET state = 'RUNNING',
                      started_at = COALESCE(started_at, ?),
                      updated_at = ?,
                      error = NULL
                WHERE job_id = ?""",
            (now, now, row["job_id"]),
        )
    out = dict(row)
    out["state"] = "RUNNING"
    out["reset_running_pages"] = int(reset)
    return out


def claim_next_chunk(db_path: Path | str, job_id: str) -> dict[str, Any] | None:
    """认领该 job 的下一个可派 chunk（**CAS**：`WHERE state='PENDING'` 防重复认领）。

    返回 `{job_id, chunk_index, pages:[…]}`；无待办 ⇒ `None`。
    """
    now = db.now_iso()
    with db.tx(db_path) as conn:
        row = db.query_one(
            conn,
            "SELECT MIN(chunk_index) AS ci FROM job_pages WHERE job_id = ? AND state = 'PENDING'",
            (job_id,),
        )
        if row is None or row["ci"] is None:
            return None
        chunk_index = int(row["ci"])
        cur = conn.execute(
            """UPDATE job_pages
                  SET state = 'RUNNING', started_at = ?, error = NULL, updated_at = ?
                WHERE job_id = ? AND chunk_index = ? AND state = 'PENDING'""",
            (now, now, job_id, chunk_index),
        )
        if cur.rowcount == 0:  # 竞态兜底（正常单写者不会命中）
            return None
        pages = [
            int(r["page"])
            for r in db.query_all(
                conn,
                "SELECT page FROM job_pages WHERE job_id = ? AND chunk_index = ? ORDER BY page",
                (job_id, chunk_index),
            )
        ]
    return {"job_id": job_id, "chunk_index": chunk_index, "pages": pages}


def requeue_pages(db_path: Path | str, *, job_id: str, pages: list[int], error: str | None = None) -> int:
    """把「在飞但没结果」的页退回 `PENDING`（worker 崩溃后**可续跑**，不是 FAILED）。"""
    if not pages:
        return 0
    now = db.now_iso()
    with db.tx(db_path) as conn:
        cur = conn.executemany(
            """UPDATE job_pages
                  SET state = 'PENDING', started_at = NULL, error = ?, updated_at = ?
                WHERE job_id = ? AND page = ? AND state <> 'DONE'""",
            [(error, now, job_id, int(p)) for p in pages],
        )
        n = cur.rowcount
        conn.execute("UPDATE jobs SET updated_at = ? WHERE job_id = ?", (now, job_id))
    return int(n)


def fail_pages(db_path: Path | str, *, job_id: str, pages: list[int], error: str) -> int:
    """页级失败落库（`FAILED` + 原因）⇒ E2 的 `failed_pages` 非空 ⇒ **不得报 DONE**（§2.2 / S-2）。"""
    if not pages:
        return 0
    now = db.now_iso()
    with db.tx(db_path) as conn:
        cur = conn.executemany(
            """UPDATE job_pages
                  SET state = 'FAILED', error = ?, finished_at = ?, updated_at = ?
                WHERE job_id = ? AND page = ? AND state <> 'DONE'""",
            [(error, now, now, job_id, int(p)) for p in pages],
        )
        n = cur.rowcount
        conn.execute("UPDATE jobs SET updated_at = ?, error = ? WHERE job_id = ?", (now, error, job_id))
    return int(n)


# 加法三列（migration `1a-0003-stamps-naming-columns`）：新行走库必须**一并落库**，
# 否则新 job 行的 `col`/`row`/`img_path_tiff` 恒为 NULL（P0 真缺陷，Neng 质检 F1）。
STAMP_NAMING_COLS = ("col", "row", "img_path_tiff")


def _upsert_stamp(conn, row: dict[str, Any], on_conflict: str) -> str:
    """行级幂等（§2.4）：已存在 ⇒ `skip`（默认，**绝不改写旧行**）或显式 `update`。

    返回 `inserted` / `updated` / `skipped`（写入 `job_pages` 的 5 个计数列）。
    依据：AC-01 的判负形态＝「旧行任一字段被改写」，故默认 arm 必须**只跳过不覆盖**。

    **影像列口径（2026-10-11「webp 退场」单）**：
      * **新行 `img_path` 写 NULL** —— 该列语义＝历史 webp 面、已退场；不再写「虚拟 webp 路径」；
      * **新行必须写 `col` / `row` / `img_path_tiff`**（新产物的真身在 TIFF 列，E6 首选它）；
      * **历史行的 `img_path` 值一字不改** —— `update` 分支里传入 `img_path` 为空时**保留既有值**，
        绝不把历史行已有的 webp 路径抹成 NULL（红线：现有 10 列内容指纹 before ≡ after）。
    """
    existing = db.query_one(
        conn,
        """SELECT text, img_path, x1, y1, x2, y2, col, row, img_path_tiff FROM stamps
            WHERE pdf_name = ? AND page = ? AND idx = ?""",
        (row["pdf_name"], int(row["page"]), int(row["idx"])),
    )
    img_path_in = row.get("img_path")  # 新写一律 None（webp 退场）；见下 `update` 分支的保护逻辑。
    if existing is None:
        conn.execute(
            """INSERT INTO stamps(pdf_name, page, idx, text, img_path, x1, y1, x2, y2,
                                  col, row, img_path_tiff)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pdf_name, page, idx) DO NOTHING""",
            (
                row["pdf_name"],
                int(row["page"]),
                int(row["idx"]),
                row["text"],
                None,                        # ★ 新行 img_path 落 NULL（该列＝历史 webp 面、已退场）
                row["x1"],
                row["y1"],
                row["x2"],
                row["y2"],
                row.get("col"),
                row.get("row"),
                row.get("img_path_tiff"),
            ),
        )
        return "inserted"
    if on_conflict == ON_CONFLICT_UPDATE:
        # `img_path` 已退场：传入为空 ⇒ 保留既有值（**历史行的 img_path 一字不改**，红线）。
        new_img_path = img_path_in if img_path_in is not None else existing["img_path"]
        same = (
            existing["text"] == row["text"]
            and existing["img_path"] == new_img_path
            and all(existing[k] == row.get(k) for k in STAMP_NAMING_COLS)
            and all(existing[k] == row[k] for k in ("x1", "y1", "x2", "y2"))
        )
        if same:
            return "skipped"
        conn.execute(
            """UPDATE stamps SET text = ?, img_path = ?, x1 = ?, y1 = ?, x2 = ?, y2 = ?,
                      col = ?, row = ?, img_path_tiff = ?
                WHERE pdf_name = ? AND page = ? AND idx = ?""",
            (
                row["text"],
                new_img_path,
                row["x1"],
                row["y1"],
                row["x2"],
                row["y2"],
                row.get("col"),
                row.get("row"),
                row.get("img_path_tiff"),
                row["pdf_name"],
                int(row["page"]),
                int(row["idx"]),
            ),
        )
        return "updated"
    return "skipped"


def commit_chunk(
    db_path: Path | str,
    *,
    job_id: str,
    chunk_index: int,
    page_results: list[dict[str, Any]],
    on_conflict: str = ON_CONFLICT_SKIP,
) -> dict[str, Any]:
    """**提交一个 chunk**（§4.3：提交点 = chunk 边界）——**单事务**内完成：

    1. 该 chunk 每页的记录行落 `stamps`（**行级幂等**，§2.4）；
    2. 每页 `job_pages` 置 `DONE`/`FAILED` 并写入 5 个页级计数；
    3. `jobs` 的 `updated_at` / `cursor_chunk_*` 推进（E2 的 `cursor` 仍由 `job_pages` **复算**，§3.2 S-1）。

    **页内多印与影像同批生效**：影像已由 worker 先落盘 + fsync，此处只提交 DB 行
    ⇒ 崩溃窗口最多留**孤儿影像**，不会留**孤儿 DB 行**（§4.3）。
    """
    now = db.now_iso()
    counters = {"detected": 0, "inserted": 0, "updated": 0, "skipped": 0, "ocr_empty": 0}
    failed_pages: list[int] = []
    with db.tx(db_path) as conn:
        for pr in page_results:
            page = int(pr["page"])
            if not pr.get("ok", False):
                failed_pages.append(page)
                conn.execute(
                    """UPDATE job_pages
                          SET state = 'FAILED', error = ?, finished_at = ?, updated_at = ?
                        WHERE job_id = ? AND page = ?""",
                    (str(pr.get("error") or "unknown"), now, now, job_id, page),
                )
                continue
            ins = upd = skip = 0
            for item in pr.get("items", []):
                verdict = _upsert_stamp(
                    conn,
                    {
                        "pdf_name": pr["pdf_name"],
                        "page": page,
                        "idx": item["idx"],
                        "text": item["text"],
                        # ★ 新行 `img_path` 写 NULL（该列＝历史 webp 面、已退场；不再写「虚拟 webp 路径」）。
                        #   worker 返回值里的 `img_path` 字符串仅供其它调用方复用，**不落库**。
                        "img_path": None,
                        # 加法三列：新产物的真身在 TIFF 列（`col`/`row` 为 P-C-R 命名坐标）。
                        "col": item.get("col"),
                        "row": item.get("row"),
                        "img_path_tiff": item.get("img_path_tiff"),
                        "x1": item["x1"],
                        "y1": item["y1"],
                        "x2": item["x2"],
                        "y2": item["y2"],
                    },
                    on_conflict,
                )
                ins += verdict == "inserted"
                upd += verdict == "updated"
                skip += verdict == "skipped"
            detected = int(pr.get("detected", len(pr.get("items", []))))
            ocr_empty = int(pr.get("ocr_empty", 0))
            conn.execute(
                """UPDATE job_pages
                      SET state = 'DONE', detected = ?, inserted = ?, updated = ?, skipped = ?,
                          ocr_empty = ?, error = NULL, finished_at = ?, updated_at = ?
                    WHERE job_id = ? AND page = ?""",
                (detected, ins, upd, skip, ocr_empty, now, now, job_id, page),
            )
            counters["detected"] += detected
            counters["inserted"] += ins
            counters["updated"] += upd
            counters["skipped"] += skip
            counters["ocr_empty"] += ocr_empty
        conn.execute(
            """UPDATE jobs
                  SET updated_at = ?,
                      cursor_chunk_lo = (SELECT MIN(chunk_index) FROM job_pages
                                          WHERE job_id = ? AND state <> 'DONE'),
                      cursor_chunk_hi = (SELECT MAX(chunk_index) FROM job_pages
                                          WHERE job_id = ? AND state = 'DONE')
                WHERE job_id = ?""",
            (now, job_id, job_id, job_id),
        )
    return {"job_id": job_id, "chunk_index": chunk_index, "counters": counters, "failed_pages": failed_pages}


def job_outstanding(db_path: Path | str, job_id: str) -> dict[str, int]:
    """该 job 各状态页数（池用 `PENDING`/`RUNNING` 判是否还有活；`DONE` 即已提交页）。"""
    with db.ro(db_path) as conn:
        row = db.query_one(
            conn,
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN state='PENDING' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN state='RUNNING' THEN 1 ELSE 0 END) AS running,
                      SUM(CASE WHEN state='DONE'    THEN 1 ELSE 0 END) AS done,
                      SUM(CASE WHEN state='FAILED'  THEN 1 ELSE 0 END) AS failed
                 FROM job_pages WHERE job_id = ?""",
            (job_id,),
        )
    return {k: int(row[k] or 0) for k in ("total", "pending", "running", "done", "failed")}


def maybe_finalize_job(db_path: Path | str, job_id: str, *, error: str | None = None) -> str | None:
    """所有页都到终态 ⇒ 收尾：无 FAILED 记 `DONE`，否则 `FAILED_PARTIAL`（§2.2）。

    `error` 为**本次收尾的原因覆盖**（缺省保持既有形态：`FAILED_PARTIAL` ⇒ `failed_pages=<n>`、
    `DONE` ⇒ `NULL`）——供池在「模板不可用」一类**由池直接落终态**的场景写明具体原因，
    避免 `jobs.error` 被压成泛化的 `failed_pages=`。
    """
    now = db.now_iso()
    st = job_outstanding(db_path, job_id)
    if st["pending"] or st["running"]:
        return None
    state = "FAILED_PARTIAL" if st["failed"] else "DONE"
    if error is None:
        error = f"failed_pages={st['failed']}" if state == "FAILED_PARTIAL" else None
    with db.tx(db_path) as conn:
        conn.execute(
            """UPDATE jobs
                  SET state = ?, finished_at = ?, updated_at = ?, error = ?
                WHERE job_id = ?""",
            (state, now, now, error, job_id),
        )
    return state


# =========================================================================== 读接口层（阶段 1b-ii）
# 规范锚点：§3.1 E3（分页取结果）/ E4（触发导出，落 `exporting.py`）/ E6（取印面裁图）/ E7（job 列表）、
# §3.2 S-3（6 字段信封）/ S-4（接口层不落业务真值）、§3.5（E6 只读、越界校验、不得读 BLOB）、§3.8（E7）。
#
# 纪律：本节全部**只读**（`db.ro`）、**每次现查现算**（无进程内缓存 / 无计数器）；`E6 不得触发解析 / OCR / 写库`。
CURSOR_RE_E3 = re.compile(r"^p(\d+)_i(\d+)$")


class BadCursor(ValueError):
    """E3 / E7：`cursor` 形态非法 ⇒ 400（§3.2 S-6 参数非法）。"""


def encode_cursor_e3(page: int, idx: int) -> str:
    """E3 游标：行级唯一锚 `(page, idx)` 的**不透明**编码（规范未定格式 ⇒ 本层定并登记缺口）。"""
    return f"p{int(page)}_i{int(idx)}"


def decode_cursor_e3(cursor: str) -> tuple[int, int]:
    m = CURSOR_RE_E3.match((cursor or "").strip())
    if not m:
        raise BadCursor(f"cursor 非法：{cursor!r}（E3 形态 = p<page>_i<idx>）")
    return int(m.group(1)), int(m.group(2))


def encode_cursor_e7(created_at: str, job_id: str) -> str:
    """E7 游标：排序键 `(created_at, job_id)` 的**URL-safe** 编码。

    **为什么必须 URL-safe**（实测踩坑）：`created_at` 形如 `2026-09-20T12:49:39+08:00`，含 `+` 与 `:`
    ——`+` 在 query string 里会被解码成空格 ⇒ 游标回到服务端已变样、第二页恒为空（首跑实测：4 个 job
    只翻出 2 个）。故用 `base64.urlsafe_b64encode` 输出**只含 `A–Za–z0–9-_` 的 token**（去尾部 `=`）。
    **E3 的游标不需要**这层：它只由整数构成（`p<page>_i<idx>`），天然 URL-safe。
    """
    raw = json.dumps([created_at, job_id], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor_e7(cursor: str) -> tuple[str, str]:
    raw = (cursor or "").strip()
    if not raw:
        raise BadCursor("cursor 为空（E7 形态 = urlsafe-base64(<created_at>,<job_id>)）")
    try:
        pad = "=" * (-len(raw) % 4)
        created_at, job_id = json.loads(base64.urlsafe_b64decode(raw + pad).decode("utf-8"))
    except Exception as exc:
        raise BadCursor(f"cursor 非法：{cursor!r}（E7 形态 = urlsafe-base64(<created_at>,<job_id>)）") from exc
    if not created_at or not job_id:
        raise BadCursor(f"cursor 非法：{cursor!r}（E7 形态 = urlsafe-base64(<created_at>,<job_id>)）")
    return str(created_at), str(job_id)


# --------------------------------------------------------------------------- E3
def _stamps_has_dup_kind(conn) -> bool:
    """`stamps` 是否有加法列 `dup_kind`（迁移 `1a-0004`）——用于**向后兼容**的过滤闸。"""
    return any(r[1] == "dup_kind" for r in conn.execute("PRAGMA table_info(stamps)"))


def stamps_page(
    db_path: Path | str,
    job_id: str,
    *,
    limit: int,
    cursor: str | None = None,
    page: int | None = None,
    include_duplicates: bool = False,
) -> dict[str, Any]:
    """E3 一页结果（§3.1 E3）。

    * 范围＝该 job 的 `pdf_name` × 该 job 的页区间（与 E5 / AC-07 **同口径**，由 `job_pages` 复算）；
    * 排序＝`(page, idx, id)` **稳定序** ⇒ 游标翻页无重叠 / 无遗漏（`(pdf_name,page,idx)` 有唯一索引兜底）；
    * `total`＝该范围全量条数（**不是**剩余条数）；`has_more`＝本页之后是否还有行；
    * `next_cursor`＝本页**最后一行**的游标；`has_more=false` ⇒ `None`（S-3 的互斥一致性）；
    * **去重标记排除（方案 A 落地 2026-10-11）**：`include_duplicates=False`（默认）⇒ 排除
      `dup_kind IS NOT NULL` 的行（方案 A 判定的近重复 / 组框，见 `server/app/dedup.py`）——「前端/导出侧
      隐藏」的展示面。`total` / `has_more` / `offset` 与行集**同口径**过滤（信封自洽）。置 True 可含被标记行
      （可回溯口径）。库无 `dup_kind` 列（未跑迁移 `1a-0004`）时**自动退化为不过滤**。**不删行、不改行**。
    """
    with db.ro(db_path) as conn:
        job = get_job_row(conn, job_id)
        pdf_name, lo, hi = _job_scope(conn, job_id)
        dup_filter = ""
        if not include_duplicates and _stamps_has_dup_kind(conn):
            dup_filter = " AND dup_kind IS NULL"
        total = int(
            db.query_one(
                conn,
                "SELECT COUNT(*) AS c FROM stamps WHERE pdf_name = ? AND page BETWEEN ? AND ?"
                + dup_filter,
                (pdf_name, lo, hi),
            )["c"]
        )
        if cursor is not None:
            cp, ci = decode_cursor_e3(cursor)
            offset = int(
                db.query_one(
                    conn,
                    """SELECT COUNT(*) AS c FROM stamps
                        WHERE pdf_name = ? AND page BETWEEN ? AND ?
                          AND (page < ? OR (page = ? AND idx <= ?))""" + dup_filter,
                    (pdf_name, lo, hi, cp, cp, ci),
                )["c"]
            )
            rows = db.query_all(
                conn,
                """SELECT id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2 FROM stamps
                    WHERE pdf_name = ? AND page BETWEEN ? AND ?
                      AND (page > ? OR (page = ? AND idx > ?))""" + dup_filter + """
                    ORDER BY page, idx, id LIMIT ?""",
                (pdf_name, lo, hi, cp, cp, ci, limit),
            )
        else:
            offset = max(0, (int(page or 1) - 1)) * limit
            rows = db.query_all(
                conn,
                """SELECT id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2 FROM stamps
                    WHERE pdf_name = ? AND page BETWEEN ? AND ?""" + dup_filter + """
                    ORDER BY page, idx, id LIMIT ? OFFSET ?""",
                (pdf_name, lo, hi, limit, offset),
            )
        rows = [dict(r) for r in rows]
        has_more = (offset + len(rows)) < total
        next_cursor = None
        if has_more and rows:
            next_cursor = encode_cursor_e3(rows[-1]["page"], rows[-1]["idx"])
        return {
            "rows": rows,
            "total": total,
            "offset": offset,
            "page": (offset // limit) + 1,
            "limit": limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "scope": {"pdf_name": pdf_name, "page_from": lo, "page_to": hi, "job_id": job["job_id"]},
        }


# --------------------------------------------------------------------------- E6
# **影像面口径（2026-10-11「webp 退场」单；Kevin 裁定「本地文件一律不再保存 webp」）**：
#   * 新产物**只有 TIFF**（`output/books/<目录键>/P<页>-C<列>-R<行>.tiff`，落 `stamps.img_path_tiff`）；
#   * `img_path` 列 **一字不改**（历史行仍是 webp；E6 的兼容回退就靠它）；
#   * ⇒ E6 取图**优先 `img_path_tiff`（校正件）→ 同目录同名 `-O.tiff`（原始切片）→ `img_path`（历史 webp）**。
#     口径真源 `docs/image-original-crop-draft-v0.1.md` **§6（校正件输出暂停，Kevin 2026-10-11）**：
#     校正件已停产、已产的 8708 件原样保留；新行影像面只有 O 件 ⇒ 校正件不在盘时**自动落 O 件**。
#     TIFF **不是浏览器可渲染容器**（§3.5 的 `Content-Type` 白名单也不含 `image/tiff`）
#     ⇒ 由**路由层**用 PIL 解码后回 **PNG**。
E6_SOURCE_TIFF = "img_path_tiff"
E6_SOURCE_ORIGINAL = "img_path_tiff/-O"
E6_SOURCE_LEGACY = "img_path"


def _resolve_img_rel(rel: str, root_abs: Path, *, column: str) -> Path:
    """DB 内**相对**影像路径 → 绝对路径（§3.5 纪律④：必须＝ `FEICUI_ROOT` ＋ 相对路径、不得逃出）。

    绝对路径 / 越出根 ⇒ `ImageUnavailable`（**拒绝**，不静默换用另一列）。
    """
    if os.path.isabs(rel):
        raise ImageUnavailable(f"{column} 为绝对路径，拒绝（须相对 feicui/）：{rel!r}")
    abs_path = (root_abs / rel).resolve()
    if not _is_within(abs_path, root_abs):
        raise ImageUnavailable(f"{column} 越出 FEICUI_ROOT，拒绝：{rel!r}")
    return abs_path


def find_stamp_image(
    db_path: Path | str, job_id: str, page: int, idx: int, *, root: Path
) -> tuple[str, str, str, str]:
    """E6 `(page, idx)` → 影像（§3.5）。返回 `(pdf_name, 服务用的相对路径, 绝对路径, 来源列)`。

    **来源列／回落链（口径件 `docs/image-original-crop-draft-v0.1.md` §6；校正件已暂停生产）**：
      ① `img_path_tiff`（**首选**，校正件）—— 有值且文件在盘 ⇒ 用之；
      ② **同目录同名 `-O.tiff`**（**原始切片**）—— 校正件不在盘时用之（O 路径由命名派生、不落库）；
      ③ `img_path`（**兼容回退**）—— 旧行未回填、且校正件与 O 都不在盘时用之。

    三类不存在（job / 记录 / 文件）由调用方统一落成 404（本函数分别抛 `JobNotFound` /
    `StampNotFound` / `ImageUnavailable`，路由层同码）。
    """
    with db.ro(db_path) as conn:
        get_job_row(conn, job_id)  # job 不存在 ⇒ JobNotFound（404）
        pdf_name, lo, hi = _job_scope(conn, job_id)
        row = db.query_one(
            conn,
            """SELECT pdf_name, page, idx, img_path, img_path_tiff FROM stamps
                WHERE pdf_name = ? AND page = ? AND idx = ?""",
            (pdf_name, int(page), int(idx)),
        )
        if row is None:
            raise StampNotFound(f"({page},{idx}) 在 job {job_id}（{pdf_name}，页 {lo}–{hi}）内不存在")
        legacy = str(row["img_path"]).strip() if row["img_path"] is not None else ""
        tiff = str(row["img_path_tiff"]).strip() if row["img_path_tiff"] is not None else ""

    root_abs = Path(root).resolve()
    # ① 首选（校正件）
    if tiff:
        abs_tiff = _resolve_img_rel(tiff, root_abs, column="img_path_tiff")
        if abs_tiff.is_file():
            return str(pdf_name), tiff, str(abs_tiff), E6_SOURCE_TIFF
        # ② 回落：校正件不在盘 ⇒ 试**同目录同名 `-O.tiff`**（原始切片；校正件停产后新行的影像面）
        o_rel = _original_rel_from_tiff(tiff)
        if o_rel:
            o_abs = (root_abs / o_rel).resolve()
            if _is_within(o_abs, root_abs) and o_abs.is_file():
                return str(pdf_name), o_rel, str(o_abs), E6_SOURCE_ORIGINAL
    # ③ 兼容回退（旧行未回填 / 校正件与 O 都不在盘 ⇒ 仍可服务）
    if legacy:
        abs_legacy = _resolve_img_rel(legacy, root_abs, column="img_path")
        if abs_legacy.is_file():
            return str(pdf_name), legacy, str(abs_legacy), E6_SOURCE_LEGACY
    # ④ 三处都拿不到文件 ⇒ 404 第三类（原因按实际形态分列，不臆造）
    if not tiff and not legacy:
        raise ImageUnavailable("img_path 与 img_path_tiff 均为空（§3.5 404 第三类）")
    raise ImageUnavailable(
        f"影像文件不在盘上：img_path_tiff={tiff!r}（含派生 -O）/ img_path={legacy!r}（§3.5 404 第三类）"
    )


def _is_within(path: Path, root: Path) -> bool:
    """`path` 是否在 `root` 之内（**符号链接已解析**：两侧都过 `resolve()`）。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class StampNotFound(Exception):
    """E6：`(page, idx)` 不存在（§3.5 404 第二类）。"""


class ImageUnavailable(Exception):
    """E6：`img_path` 缺失 / 越界 / 文件不在盘上（§3.5 404 第三类）。"""


# --------------------------------------------------------------------------- E7
# **有效态（effective_state，§3.2 S-2）的唯一 SQL 真源** —— E7 的 `state=` 过滤条件
# 与 `items[].state` 取值**必须同出一处**，否则「筛出来的集合」与「每条 items[].state」不一致。
#
# 本单修的真缺陷（质检 D-1，中危）：过滤原用 `WHERE j.state = ?`（**库内原始态**），而 items
# 展示的是复算后的**有效态** ⇒ ① `?state=DONE` 会把「库内 DONE 但含 FAILED 页」的 job 一并
# 返回（该 job 的 `items[].state` 却是 FAILED_PARTIAL）；② 反过来按 FAILED_PARTIAL 筛**会漏掉**
# 它。前端按状态筛选因此显示错误结果。
# 口径与 `repository.effective_state()`（E2 用）**逐字相同**：只降级、不升级。
E7_EFFECTIVE_STATE_SQL = (
    "CASE WHEN j.state = 'DONE' AND COALESCE(p.failed_pages, 0) > 0 "
    "THEN 'FAILED_PARTIAL' ELSE j.state END"
)

# `FROM` 子句（含 `job_pages` 复算的 LEFT JOIN）：`total` 的 COUNT、页码路径、游标路径**共用一份**，
# 保证三处看到的行集合完全相同。
E7_FROM_SQL = """jobs j
                    LEFT JOIN (SELECT job_id,
                                      SUM(CASE WHEN state = 'DONE'   THEN 1 ELSE 0 END) AS done_pages,
                                      SUM(CASE WHEN state = 'FAILED' THEN 1 ELSE 0 END) AS failed_pages
                                 FROM job_pages GROUP BY job_id) p ON p.job_id = j.job_id"""


def jobs_page(
    db_path: Path | str,
    *,
    state: str | None = None,
    limit: int,
    cursor: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    """E7 一页 job 列表（§3.1 E7 / §3.8）：**E3 同款 6 字段信封**。

    `done_pages` / `failed_pages_count` 由 `job_pages` **复算**（§3.2 S-1 的同一纪律），
    `state` 经 `effective_state`（有 `FAILED` 页 ⇒ 不得报 `DONE`，§3.2 S-2）。

    **`state=` 过滤用与 `items[].state` 同一套有效态口径**（`E7_EFFECTIVE_STATE_SQL`）——
    过滤与展示不再各算一套：`?state=DONE` 只回「有效态＝DONE」的 job（库内 DONE 但含 FAILED 页的
    job 不在其中），`?state=FAILED_PARTIAL` 恰好回它。**恒等式**：`items[].state == <过滤口径>`。

    **两条翻页路径（页码 / 游标），与 E3 同款口径**：`cursor` 给定走 keyset（`(created_at, job_id)`
    严格序），否则按 `page` 1-based 页码 + `OFFSET`；两路的 `ORDER BY j.created_at, j.job_id`
    是**全集序**（`job_id` 唯一 ⇒ 无并列），故两路 key 集合逐条相等、不重叠不遗漏。
    `has_more == (next_cursor is not None)` 恒成立（`has_more=true` ⇒ 本页必有行 ⇒ 必给游标）。

    **本单修的两处真缺陷（勿回退）**：
      ① 原函数**没有 `page` 形参** ⇒ 路由层 `?page=` 被 FastAPI 静默丢弃，page=1..N 永远返回同一份
         第一页数据（`page` 恒 1、`has_more` 恒真）⇒ 客户端按页码翻页会死循环；
      ② 游标分支**把 keyset `WHERE` 与 `OFFSET` 叠加**（`OFFSET` = 游标前已消费行数）⇒ 同一批行被
         跳过两次：第 2 页起恒返 0 条，而 `has_more` 仍按 `offset+len(items) < total` 算出真
         ⇒ `has_more=true` 且 `next_cursor=null` ⇒ 夹具死循环（上一轮 `verify_1b_ii.py` 54,347 行
         输出 / 54,254 条重复 FAIL 的机理）。故游标分支**只发 `LIMIT`**，`offset` 仅用于回填 `page`。
    """
    where, params = "", []
    if state:
        # **过滤口径＝有效态**（与 items[].state 同出一处）——不再用库内原始 `j.state`
        where = f"WHERE {E7_EFFECTIVE_STATE_SQL} = ?"
        params.append(state)
    with db.ro(db_path) as conn:
        total = int(db.query_one(conn, f"SELECT COUNT(*) AS c FROM {E7_FROM_SQL} {where}", params)["c"])
        sql = f"""SELECT j.job_id, j.pdf_name, j.pdf_path, j.total_pages, j.created_at, j.updated_at,
                         COALESCE(p.done_pages, 0)   AS done_pages,
                         COALESCE(p.failed_pages, 0) AS failed_pages_count,
                         {E7_EFFECTIVE_STATE_SQL}    AS state
                    FROM {E7_FROM_SQL}
                    {where}"""
        if cursor is not None:
            c_created, c_job = decode_cursor_e7(cursor)
            cond = "(j.created_at > ? OR (j.created_at = ? AND j.job_id > ?))"
            if where:
                sql += f" AND {cond}"
            else:
                sql += f" WHERE {cond}"
            params = params + [c_created, c_created, c_job]
            offset = int(
                db.query_one(
                    conn,
                    f"""SELECT COUNT(*) AS c FROM {E7_FROM_SQL} {where}
                        {'AND' if where else 'WHERE'} (j.created_at < ? OR (j.created_at = ? AND j.job_id <= ?))""",
                    (state, c_created, c_created, c_job) if state else (c_created, c_created, c_job),
                )["c"]
            )
            # **游标分支绝不叠加 OFFSET**：keyset 条件已把结果集定位到「游标行之后」，
            # 再按 `offset`（＝游标行之前的行数）跳过就是重复跳过 ⇒ 第 2 页起恒返 0 条
            # 而 `has_more` 仍为真、`next_cursor` 为 null ⇒ 客户端死循环（本单修的二号缺陷）。
            # `offset` 在游标路径**只用于回填 `page`**（该行数＝已消费行数，与 E3 同口径）。
            rows = db.query_all(conn, sql + " ORDER BY j.created_at, j.job_id LIMIT ?", params + [limit])
        else:
            # 页码路径：1-based `page` ⇒ OFFSET；`page` 超出末页 ⇒ OFFSET 越界 ⇒ 空 items（不是第一页）。
            offset = max(0, int(page or 1) - 1) * limit
            rows = db.query_all(
                conn, sql + " ORDER BY j.created_at, j.job_id LIMIT ? OFFSET ?", params + [limit, offset]
            )
    items = []
    for r in rows:
        item = dict(r)
        item["done_pages"] = int(item["done_pages"])
        item["failed_pages_count"] = int(item["failed_pages_count"])
        # `state` 已由 `E7_EFFECTIVE_STATE_SQL` 在 SQL 里复算（**与 `state=` 过滤同一表达式**）——
        # 此处**不得**再另算一套口径（两套口径曾造成「筛出来的集合」与「items[].state」不一致，即本单缺陷）。
        # 下列判据是该口径的**结构性不变量**：有效态为 DONE 的 job 不可能有 FAILED 页。
        if item["state"] == "DONE" and item["failed_pages_count"]:
            log.error(
                "E7 口径不变量被破坏：job=%s 有效态 DONE 却有 failed_pages_count=%s",
                item["job_id"],
                item["failed_pages_count"],
            )
        items.append(item)
    has_more = (offset + len(items)) < total
    # §3.2 S-3 的互斥一致性 `has_more == (next_cursor is not None)` 在此**结构性**成立：
    # 空 `items` 时给不出末行游标 ⇒ `has_more` 必须为 false。这道闸门就是上一轮死循环的根治点
    # （原实现给出 `has_more=true, next_cursor=null` ⇒ 客户端按「还有下一页」一直翻同一页）。
    if has_more and not items:
        has_more = False
    next_cursor = encode_cursor_e7(items[-1]["created_at"], items[-1]["job_id"]) if (has_more and items) else None
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "page": (offset // limit) + 1,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }
