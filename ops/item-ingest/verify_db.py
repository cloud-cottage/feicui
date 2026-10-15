#!/usr/bin/env python3
"""印谱独立库**全量落库自检**（IT-2 / IT-3 / IT-4 / IT-5）——只读。

判据：
  * 全量落库 1742 / 1742（与源 total 相符）；
  * 幂等键 source_item_id 非空且唯一 = 行数；as_book_id 唯一（1742）；
  * 抽样锚点：seqid=2214（0307 龍泓山人印譜）→ 卷 8 / 清宣統二年 / 1910 / hasImage=1；
              seqid=3547（1817 楊仲子印存）→ 本体取自 list（title 命中）；**donor 默认缺失**（detail 关，见 detail_policy）；
  * 关联锚点（graph/book）：seqid=2214 ⇒ 吳隱(辑) ＋ 丁敬(刻印)（source_face='book_graph'）；
  * 数值负向：volume_count / date_year 无 0 / 空串；
  * 覆盖统计与 sidecar 来源面计数。

用法：python3 verify_db.py --db <item_ingest.db> [--out x.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Users/kevin/bistro/feicui/var/item_ingest.db")
    ap.add_argument("--batch", default=None)
    ap.add_argument("--source-total", type=int, default=1742)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    def one(sql, *p):
        return conn.execute(sql, p).fetchone()

    out: dict = {"db": args.db, "batch_filter": args.batch}
    out["tables"] = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    items_n = one("SELECT COUNT(*) c FROM items")["c"]
    creators_n = one("SELECT COUNT(*) c FROM item_creators")["c"]
    out["counts"] = {"items": items_n, "creators": creators_n,
                     "source_total": args.source_total, "items_match_source_total": items_n == args.source_total}

    out["idempotency"] = {
        "non_null": one("SELECT COUNT(*) c FROM items WHERE source_item_id IS NOT NULL AND source_item_id<>''")["c"],
        "unique": one("SELECT COUNT(DISTINCT source_item_id) c FROM items")["c"],
        "total": items_n,
    }
    out["idempotency"]["all_non_null_and_unique"] = (
        out["idempotency"]["non_null"] == items_n == out["idempotency"]["unique"])
    out["as_book_id_unique"] = one(
        "SELECT COUNT(DISTINCT as_book_id) c FROM items WHERE as_book_id IS NOT NULL AND as_book_id<>''")["c"]

    # 数值负向
    out["volume_count_special"] = [r[0] for r in conn.execute(
        "SELECT source_item_id FROM items WHERE volume_count = 0 OR volume_count = ''")]
    out["date_year_special"] = [r[0] for r in conn.execute(
        "SELECT source_item_id FROM items WHERE date_year = 0 OR date_year = ''")]
    out["numeric_special_free"] = (len(out["volume_count_special"]) == 0 and len(out["date_year_special"]) == 0)

    # 抽样锚点
    anchors = {}
    for sid in ("2214", "3547"):
        r = one("SELECT source_item_id, as_book_id, title, volume_count, date_text, date_year, donor, "
                "has_image, has_annotation, category FROM items WHERE source_item_id=?", sid)
        anchors[sid] = dict(r) if r else None
    out["anchors"] = anchors
    a = anchors.get("2214") or {}
    b = anchors.get("3547") or {}
    out["anchor_checks"] = {
        "2214_seqid_asbookid": a.get("as_book_id") == "0307",
        "2214_title": a.get("title") == "龍泓山人印譜",
        "2214_volume_8": a.get("volume_count") == 8,
        "2214_date_text": a.get("date_text") == "清宣統二年",
        "2214_date_year_1910": a.get("date_year") == 1910,
        "2214_has_image_1": a.get("has_image") == 1,
        "3547_seqid_asbookid": b.get("as_book_id") == "1817",
        "3547_title": b.get("title") == "楊仲子印存",
        # 本体取自 book/list；detail 默认关 ⇒ bookDonor（详情独有）按口径缺失
        "3547_donor_missing_detail_off": b.get("donor") is None,
    }
    # 关联锚点（graph/book）：seqid=2214 ⇒ 吳隱(辑) + 丁敬(刻印)
    names_2214 = sorted({r["creator_name"] for r in conn.execute(
        "SELECT creator_name FROM item_creators WHERE source_item_id='2214' AND source_face='book_graph'")})
    out["association_anchor_2214"] = names_2214
    out["association_anchor_checks"] = {
        "2214_has_wuyin": "吳隱" in names_2214,
        "2214_has_dingjing": "丁敬" in names_2214,
    }
    out["anchors_ok"] = all(out["anchor_checks"].values()) and all(out["association_anchor_checks"].values())

    # sidecar 来源面
    faces = {r[0]: r[1] for r in conn.execute(
        "SELECT source_face, COUNT(*) FROM item_creators GROUP BY source_face")}
    out["creators_by_source_face"] = faces
    out["creators_distinct_items_person_graph"] = one(
        "SELECT COUNT(DISTINCT source_item_id) c FROM item_creators WHERE source_face='person_graph'")["c"]
    out["creators_orphan"] = [r[0] for r in conn.execute(
        "SELECT DISTINCT c.source_item_id FROM item_creators c "
        "LEFT JOIN items i ON i.source_item_id=c.source_item_id WHERE i.source_item_id IS NULL")]

    # 覆盖统计
    out["coverage"] = {
        "has_image_true": one("SELECT COUNT(*) c FROM items WHERE has_image=1")["c"],
        "has_image_false": one("SELECT COUNT(*) c FROM items WHERE has_image=0 OR has_image IS NULL")["c"],
        "has_date_year": one("SELECT COUNT(*) c FROM items WHERE date_year IS NOT NULL")["c"],
        "has_volume_count": one("SELECT COUNT(*) c FROM items WHERE volume_count IS NOT NULL")["c"],
        "has_donor": one("SELECT COUNT(*) c FROM items WHERE donor IS NOT NULL AND donor<>''")["c"],
        "has_abstract": one("SELECT COUNT(*) c FROM items WHERE abstract IS NOT NULL AND abstract<>''")["c"],
    }

    # 批次
    batches = [dict(r) for r in conn.execute(
        "SELECT batch_id, status, source_total, items_ok, creators_ok, failed_count, fetched, "
        "content_fingerprint, last_run_kind FROM item_import_batches ORDER BY batch_id DESC")]
    out["batches"] = batches

    out["pass"] = (out["counts"]["items_match_source_total"] and out["idempotency"]["all_non_null_and_unique"]
                   and out["as_book_id_unique"] == args.source_total and out["numeric_special_free"]
                   and out["anchors_ok"] and len(out["creators_orphan"]) == 0)
    conn.close()

    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
