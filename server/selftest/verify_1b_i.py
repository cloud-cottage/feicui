#!/usr/bin/env python
"""阶段 1b-i 独立复算 / 对账工具（Kong）。

**为什么单独写**：AC-01/AC-03/AC-04/AC-05/AC-11 都要求「**独立复算**」——不能用被测代码的读数
自证。本工具**只读** DB / 文件系统，自己写 SQL 与文件遍历，不 import `app.*`（只依赖标准库 +
`hashlib`），从而与接口层、池的实现完全解耦。

用法（全部只读；`db` 一律是**副本**库）：
    verify_1b_i.py recompute  <db> <job_id>
    verify_1b_i.py e2check    <db> <job_id> <e2.json>      # E2 响应 vs 库内复算（逐字段 MATCH/DIFF）
    verify_1b_i.py export     <db> <pdf_name> <lo> <hi> <out.csv>
    verify_1b_i.py rowsig     <db> <pdf_name> [lo] [hi]
    verify_1b_i.py counts     <db> <pdf_name> [lo] [hi]
    verify_1b_i.py pages      <db> <job_id>
    verify_1b_i.py imgman     <dir>
    verify_1b_i.py diffcsv    <a.csv> <b.csv>
    verify_1b_i.py subset     <断点时.csv> <终态.csv>   # 断点行须逐字节仍在终态里
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROW_COLS = ("pdf_name", "page", "idx", "text", "x1", "y1", "x2", "y2")
CSV_COLS = ROW_COLS  # AC-04 的导出列：(pdf_name,page,idx,text,x1,y1,x2,y2) 全字段


def connect(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _range_sql(pdf_name: str, lo: int | None, hi: int | None) -> tuple[str, tuple]:
    if lo is None or hi is None:
        return "pdf_name = ?", (pdf_name,)
    return "pdf_name = ? AND page BETWEEN ? AND ?", (pdf_name, int(lo), int(hi))


def recompute(db: str, job_id: str) -> dict:
    """E2 的全部字段**独立复算**（逐条 SQL，不看接口层）。"""
    conn = connect(db)
    try:
        job = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job is None:
            raise SystemExit(f"✗ job 不存在：{job_id}")
        agg = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN state='DONE' THEN 1 ELSE 0 END) AS done,
                      COALESCE(SUM(detected),0)  AS detected,
                      COALESCE(SUM(inserted),0)  AS inserted,
                      COALESCE(SUM(updated),0)   AS updated,
                      COALESCE(SUM(skipped),0)   AS skipped,
                      COALESCE(SUM(ocr_empty),0) AS ocr_empty,
                      MIN(CASE WHEN state <> 'DONE' THEN chunk_index END) AS chunk_lo,
                      MAX(CASE WHEN state =  'DONE' THEN chunk_index END) AS chunk_hi,
                      SUM(CASE WHEN state='PENDING' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN state='RUNNING' THEN 1 ELSE 0 END) AS running,
                      SUM(CASE WHEN state='FAILED'  THEN 1 ELSE 0 END) AS failed
                 FROM job_pages WHERE job_id = ?""",
            (job_id,),
        ).fetchone()
        failed_pages = [
            int(r[0])
            for r in conn.execute(
                "SELECT page FROM job_pages WHERE job_id=? AND state='FAILED' ORDER BY page", (job_id,)
            )
        ]
        out = {
            "job_id": job_id,
            "state": job["state"],
            "total_pages": int(agg["total"] or 0),
            "done_pages": int(agg["done"] or 0),
            "failed_pages": failed_pages,
            "cursor": {"chunk_lo": agg["chunk_lo"], "chunk_hi": agg["chunk_hi"]},
            "counters": {
                "detected": int(agg["detected"]),
                "inserted": int(agg["inserted"]),
                "updated": int(agg["updated"]),
                "skipped": int(agg["skipped"]),
                "ocr_empty": int(agg["ocr_empty"]),
            },
            "page_states": {
                "pending": int(agg["pending"] or 0),
                "running": int(agg["running"] or 0),
                "failed": int(agg["failed"] or 0),
            },
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
        }
    finally:
        conn.close()
    # S-2 兜底（与接口层同口径，但这里是自己算的）
    if out["state"] == "DONE" and out["failed_pages"]:
        out["state"] = "FAILED_PARTIAL"
    return out


def e2check(db: str, job_id: str, e2_json: str) -> int:
    e2 = json.loads(Path(e2_json).read_text(encoding="utf-8"))
    rc = recompute(db, job_id)
    fields = {
        "state": (e2.get("state"), rc["state"]),
        "total_pages": (e2.get("total_pages"), rc["total_pages"]),
        "done_pages": (e2.get("done_pages"), rc["done_pages"]),
        "failed_pages": (e2.get("failed_pages"), rc["failed_pages"]),
        "cursor": (e2.get("cursor"), rc["cursor"]),
        "counters": (e2.get("counters"), rc["counters"]),
    }
    bad = 0
    for name, (got, want) in fields.items():
        ok = got == want
        bad += not ok
        print(f"{'MATCH' if ok else 'DIFF '} {name}: api={got!r} recompute={want!r}")
    print(f"jobs.state(库内原始)={rc['state']} started_at={rc['started_at']} finished_at={rc['finished_at']}")
    print("E2CHECK =", "MATCH" if bad == 0 else f"{bad} FIELD(S) DIFF")
    return 0 if bad == 0 else 1


def export_csv(db: str, pdf_name: str, lo: int, hi: int, out_csv: str) -> int:
    conn = connect(db)
    try:
        where, params = _range_sql(pdf_name, lo, hi)
        rows = conn.execute(
            f"SELECT {','.join(ROW_COLS)} FROM stamps WHERE {where} ORDER BY page, idx", params
        ).fetchall()
    finally:
        conn.close()
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for r in rows:
            w.writerow([r[c] for c in CSV_COLS])
    print(f"{out_csv}: {len(rows)} 行（{pdf_name} {lo}-{hi}）")
    return 0


def rowsig(db: str, pdf_name: str, lo: int | None = None, hi: int | None = None) -> int:
    """行集指纹：按 (page,idx) 排序后逐行序列化再 sha256 —— 重跑前后必须**完全一致**。"""
    conn = connect(db)
    try:
        where, params = _range_sql(pdf_name, lo, hi)
        rows = conn.execute(
            f"SELECT {','.join(ROW_COLS)} FROM stamps WHERE {where} ORDER BY page, idx", params
        ).fetchall()
    finally:
        conn.close()
    blob = "\n".join("|".join("" if r[c] is None else str(r[c]) for c in ROW_COLS) for r in rows)
    print(json.dumps({"pdf_name": pdf_name, "lo": lo, "hi": hi, "rows": len(rows),
                      "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}, ensure_ascii=False))
    return 0


def counts(db: str, pdf_name: str, lo: int | None = None, hi: int | None = None) -> int:
    conn = connect(db)
    try:
        where, params = _range_sql(pdf_name, lo, hi)
        total = conn.execute(f"SELECT COUNT(*) FROM stamps WHERE {where}", params).fetchone()[0]
        distinct = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT pdf_name,page,idx FROM stamps WHERE {where})", params
        ).fetchone()[0]
        dups = [
            dict(r)
            for r in conn.execute(
                f"""SELECT pdf_name,page,idx,COUNT(*) n FROM stamps WHERE {where}
                    GROUP BY pdf_name,page,idx HAVING n > 1""",
                params,
            )
        ]
        allrows = conn.execute("SELECT COUNT(*) FROM stamps").fetchone()[0]
        alldistinct = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT pdf_name,page,idx FROM stamps)"
        ).fetchone()[0]
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "scope_rows": total,
                "scope_distinct_keys": distinct,
                "scope_dup_groups": dups,
                "scope_unique_ok": total == distinct and not dups,
                "table_rows": allrows,
                "table_distinct_keys": alldistinct,
                "table_unique_ok": allrows == alldistinct,
            },
            ensure_ascii=False,
        )
    )
    return 0 if (total == distinct and not dups) else 1


def pages(db: str, job_id: str) -> int:
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT page,state,detected,inserted,updated,skipped,ocr_empty,error FROM job_pages "
            "WHERE job_id=? ORDER BY page",
            (job_id,),
        ).fetchall()
        chunks = conn.execute(
            "SELECT chunk_index, COUNT(*) n, SUM(state='DONE') d FROM job_pages WHERE job_id=? "
            "GROUP BY chunk_index ORDER BY chunk_index",
            (job_id,),
        ).fetchall()
        print(json.dumps({
            "job_id": job_id,
            "pages": [dict(r) for r in rows],
            "chunks": [dict(c) for c in chunks],
            "chunks_done": sum(1 for c in chunks if c["d"] == c["n"]),
            "chunks_total": len(chunks),
        }, ensure_ascii=False, indent=1))
    finally:
        conn.close()
    return 0


def imgman(root: str) -> int:
    """影像清单（路径 + sha256，排序），用于 AC-02 的「文件数不变 + 各文件 sha256 不变」。"""
    base = Path(root)
    lines = []
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.name.endswith(".tmp"):
                h = hashlib.sha256()
                with p.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                lines.append(f"{h.hexdigest()}  {p.relative_to(base)}  {p.stat().st_size}")
    print("\n".join(lines))
    print(f"# files={len(lines)} root={base}")
    return 0


def subset(small: str, big: str) -> int:
    """**断点续跑的关键判据**：断点时已提交的行，必须在终态里**逐字节原样存在**（未被重写）。

    只比数据行（跳过表头）；每行一次精确匹配（不是「字段相近」）。
    """
    s = [ln for ln in Path(small).read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
    bset = set(ln for ln in Path(big).read_text(encoding="utf-8").splitlines()[1:] if ln.strip())
    missing = [ln for ln in s if ln not in bset]
    print(f"断点行数={len(s)} 终态行数={len(bset)} 未原样保留={len(missing)}")
    for ln in missing[:20]:
        print("  MISSING/CHANGED:", ln)
    print("SUBSET =", "IDENTICAL(断点前已提交行零改写)" if not missing else "CHANGED")
    return 0 if not missing else 1


def diffcsv(a: str, b: str) -> int:
    ra = Path(a).read_text(encoding="utf-8").splitlines()
    rb = Path(b).read_text(encoding="utf-8").splitlines()
    import difflib

    if ra == rb:
        print(f"DIFFCSV = IDENTICAL（{len(ra) - 1} 行数据逐字节相同）")
        return 0
    diff = list(difflib.unified_diff(ra, rb, fromfile=a, tofile=b, lineterm="", n=1))
    print("\n".join(diff[:80]))
    print(f"DIFFCSV = {sum(1 for d in diff if d.startswith(('+', '-')) and not d.startswith(('+++', '---')))} 处差异行")
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "recompute":
            print(json.dumps(recompute(rest[0], rest[1]), ensure_ascii=False, indent=1))
            return 0
        if cmd == "e2check":
            return e2check(rest[0], rest[1], rest[2])
        if cmd == "export":
            return export_csv(rest[0], rest[1], int(rest[2]), int(rest[3]), rest[4])
        if cmd == "rowsig":
            lo = int(rest[2]) if len(rest) > 2 else None
            hi = int(rest[3]) if len(rest) > 3 else None
            return rowsig(rest[0], rest[1], lo, hi)
        if cmd == "counts":
            lo = int(rest[2]) if len(rest) > 2 else None
            hi = int(rest[3]) if len(rest) > 3 else None
            return counts(rest[0], rest[1], lo, hi)
        if cmd == "pages":
            return pages(rest[0], rest[1])
        if cmd == "imgman":
            return imgman(rest[0])
        if cmd == "diffcsv":
            return diffcsv(rest[0], rest[1])
        if cmd == "subset":
            return subset(rest[0], rest[1])
    except IndexError:
        print(f"✗ 参数不足：{cmd}", file=sys.stderr)
        return 2
    print(f"✗ 未知子命令：{cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
