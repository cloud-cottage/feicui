#!/usr/bin/env python
"""批次汇总 —— Kong / biblio-metadata 单 · 2026-10-11。

Zang 的「逐书各起一进程」跑法为**每本书**生成**一条**批次行（`biblio_import_batches`，`source_total=1`）。
本脚本把这些**成员批次**归并成**一条汇总批次**（一个 `batch_id` 总括 7 本），供审计与后续「重出轮」引用。

**幂等**：汇总 `batch_id` 由成员批次集合的 sha1 前缀派生 ⇒ 同一成员集合重跑得同一 id（`INSERT OR REPLACE`）。
**只写 `var/biblio_ingest.db`（`biblio_import_batches` 一行）**；不写 `yinpu.db`、不改 `book_biblio` 列值、
不切目录键、不建 job。同时落 `ops/biblio-metadata/batch_summary.json` / `batch_summary.md`。

    cd /Users/kevin/bistro/feicui
    python3 ops/biblio-metadata/summarize_batches.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "ops" / "biblio-metadata"
DB = REPO / "var" / "biblio_ingest.db"


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--no-write", action="store_true", help="只算不写库（预览）")
    args = ap.parse_args()
    db = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db), timeout=30.0)
    conn.row_factory = sqlite3.Row
    books = [dict(r) for r in conn.execute("select * from book_biblio order by book_ref")]
    bcols = {r[1] for r in conn.execute("PRAGMA table_info(biblio_import_batches)")}
    batches = {r["batch_id"]: dict(r) for r in conn.execute("select * from biblio_import_batches")}
    conn.close()

    # 成员批次 ＝ 每本书当前指向的批次（去重）
    member_ids = sorted({b.get("batch_id") for b in books if b.get("batch_id")
                         and b["batch_id"] in batches})
    members = [batches[i] for i in member_ids]
    books_ok = sum(1 for b in books if b.get("verify_state") == "ok")
    candidates_ok = sum(1 for b in books if b.get("isbn13") or b.get("isbn10"))
    book_refs = [b["book_ref"] for b in books]

    fingerprint = hashlib.sha1("\n".join(member_ids).encode("utf-8")).hexdigest()[:12]
    summary_id = f"biblio-summary-{fingerprint}"

    summary = {
        "batch_id": summary_id,
        "created_at": _now(),
        "status": "aggregated",
        "kind": "summary",
        "books_total": len(books),
        "member_batch_count": len(member_ids),
        "member_batches": member_ids,
        "books_ok": books_ok,
        "candidates_ok": candidates_ok,
        "books": book_refs,
        "notes": (f"汇总批次：总括 {len(books)} 本（成员批次 {len(member_ids)} 条，"
                  "Zang 逐书各起一进程）。本行为归并视图，不改 book_biblio 任何列值。"),
    }
    (out_dir / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 批次汇总（Kong · biblio-metadata）", "",
             f"汇总 `batch_id` ＝ `{summary_id}`（由成员批次集合的 sha1 派生，**幂等**）。",
             f"总括 **{len(books)}** 本；成员批次 **{len(member_ids)}** 条（每书一条，逐书独立进程）。",
             f"`books_ok`={books_ok}；`candidates_ok`（识别到 ISBN）={candidates_ok}。", "",
             "> 注：下表 `识别 ISBN` / `建议目录键` 取自库中**收口前**的旧值（Zang 逐书跑的原读数）；",
             "> **收口后**的复算推荐见 `seven_book_table.md`（秦印类编落 9787550847224、福庵假号被拒、黄牧甫落中文书名）。", "",
             "| 书（PDF 名） | 自证态 | 识别 ISBN | 建议目录键 | 成员批次 |",
             "| --- | --- | --- | --- | --- |"]
    for b in books:
        lines.append("| {r} | {v} | {i} | {k} | {b} |".format(
            r=b["book_ref"], v=b.get("verify_state"),
            i=b.get("isbn13") or b.get("isbn10") or "—",
            k=b.get("dir_key_recommended") or "—", b=b.get("batch_id") or "—"))
    (out_dir / "batch_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    if args.no_write:
        print("\n[no-write] 预览，未写库。")
        return 0

    # 写汇总批次行（幂等 INSERT OR REPLACE；只此一行）
    vals = {
        "batch_id": summary_id, "created_at": _now(), "updated_at": _now(),
        "status": "aggregated", "source_total": len(members), "fetched": len(members),
        "books_ok": books_ok, "candidates_ok": candidates_ok, "failed_count": 0,
        "elapsed_s": round(sum((m.get("elapsed_s") or 0) for m in members), 2),
        "package_dir": str(out_dir), "report_path": str(out_dir / "batch_summary.json"),
        "content_fingerprint": fingerprint,
        "params_json": json.dumps({"kind": "summary", "member_batches": member_ids,
                                   "books": book_refs}, ensure_ascii=False),
        "notes": summary["notes"], "last_run_kind": "summary",
        "last_run_fetched": len(members), "last_run_skipped": 0,
        "last_run_elapsed_s": round(sum((m.get("elapsed_s") or 0) for m in members), 2),
        "last_run_at": _now(),
    }
    use = {k: v for k, v in vals.items() if k in bcols}
    conn = sqlite3.connect(str(db), timeout=30.0)
    try:
        conn.execute(f"INSERT OR REPLACE INTO biblio_import_batches ({','.join(use)}) "
                     f"VALUES ({','.join('?' for _ in use)})", list(use.values()))
        conn.commit()
    finally:
        conn.close()
    print(f"\n[wrote] batch_summary.json / batch_summary.md; 汇总批次 {summary_id} ⇒ {db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
