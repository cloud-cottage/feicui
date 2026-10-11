#!/usr/bin/env python3
"""「识别结果 vs 现目录键」对照表生成（Kong / biblio-metadata 单 · 2026-10-11）。

读 `scan_results.json`（扫描产物）＋ `config/book_dir_keys.json`（现目录键真源），
写出 `book_compare.json`（机读）与 `book_compare.md`（人读表）。**只读、不切键、不改配置。**

    python3 ops/biblio-metadata/compare_keys.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "ops" / "biblio-metadata"


def main() -> int:
    results = json.loads((OUT / "scan_results.json").read_text(encoding="utf-8"))
    keys = json.loads((REPO / "config" / "book_dir_keys.json").read_text(encoding="utf-8"))
    books = keys.get("books", {})

    rows = []
    for r in results:
        name = r["book_ref"]
        cur = books.get(name, {})
        cur_key = cur.get("dir_key")
        cur_src = cur.get("dir_key_source")
        rec_key = r.get("dir_key_recommended")
        rec_src = r.get("dir_key_source_recommended")
        isbn = r.get("isbn13") or r.get("isbn10")
        if isbn and r.get("isbn13") and r.get("isbn10_derived"):
            isbn_disp = f"{r['isbn13']}（⇒10 {r.get('isbn10')}）"
        else:
            isbn_disp = isbn
        needs_switch = None
        if rec_key is not None:
            needs_switch = (rec_key != cur_key)
        rows.append({
            "book_ref": name,
            "dir_key_current": cur_key,
            "dir_key_source_current": cur_src,
            "isbn13": r.get("isbn13"),
            "isbn10": r.get("isbn10"),
            "isbn10_derived": r.get("isbn10_derived"),
            "isbn_display": isbn_disp,
            "isbn_source": r.get("isbn_source"),
            "publisher_identified": r.get("publisher"),
            "verify_state": r.get("verify_state"),
            "verify_note": r.get("verify_note"),
            "dir_key_recommended": rec_key,
            "dir_key_source_recommended": rec_src,
            "needs_switch": needs_switch,
            "registered_isbn": cur.get("isbn"),
            "scan_pages": r.get("pages_scanned"),
            "pdf_sha256": r.get("pdf_sha256"),
        })

    (OUT / "book_compare.json").write_text(
        json.dumps({"generated_at": __import__("datetime").datetime.now().astimezone()
                    .replace(microsecond=0).isoformat(),
                    "source_results": "scan_results.json",
                    "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 「识别结果 vs 现目录键」对照表（Kong · biblio-metadata）", "",
             f"数据源：`scan_results.json` ＋ `config/book_dir_keys.json`；共 {len(rows)} 本。",
             "**本表只给建议：不切目录键、不改名、不改路径**（切键并入未来「重出轮」）。", "",
             "| 书（PDF 名） | 现目录键 | 现来源 | 识别 ISBN | 识别出版社 | 自证态 | 建议目录键 | 建议来源 | 需切键 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| {book_ref} | {dk} | {ds} | {isbn} | {pub} | {vs} | {rk} | {rs} | {sw} |".format(
            book_ref=r["book_ref"], dk=r["dir_key_current"], ds=r["dir_key_source_current"],
            isbn=r["isbn_display"] or "—", pub=r["publisher_identified"] or "—",
            vs=r["verify_state"], rk=r["dir_key_recommended"] or "—",
            rs=r["dir_key_source_recommended"] or "—",
            sw=("是" if r["needs_switch"] else ("否" if r["needs_switch"] is False else "—"))))
    (OUT / "book_compare.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"\n[wrote] {OUT/'book_compare.json'} / {OUT/'book_compare.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
