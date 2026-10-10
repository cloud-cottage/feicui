#!/usr/bin/env python3
"""② 九行一致性对账 —— **独立重算**拆解件 §2 的九行（不 import app.relations；只读三库）。

对每一行给出：命中 / 未命中数 + 未命中清单（逐条）。输出 `02_recon.json`。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
PERSON = REPO / "var" / "person_ingest.db"
ITEM = REPO / "var" / "item_ingest.db"
SEAL = REPO / "var" / "seal_ingest.db"


def ro(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def main() -> int:
    pc, ic, sc = ro(PERSON), ro(ITEM), ro(SEAL)
    items_seq = {r[0] for r in ic.execute("SELECT source_item_id FROM items")}
    items_book = {r[0] for r in ic.execute("SELECT as_book_id FROM items")}
    persons = {r[0] for r in pc.execute("SELECT source_person_id FROM persons")}
    seal_ids = {r[0] for r in sc.execute("SELECT source_seal_id FROM seals")}
    seal_refs = {r[0] for r in sc.execute("SELECT source_ref FROM seal_images")}

    rows: list[dict] = []

    def line(n, join, uniq_src, target):
        u = sorted({x for x in uniq_src if x not in (None, "")})
        miss = [x for x in u if x not in target]
        rows.append({"#": n, "join": join, "unique": len(u),
                     "hit": len(u) - len(miss), "miss": len(miss), "miss_values": miss})

    pr_item_bk = [r["as_book_id"] for r in pc.execute("SELECT as_book_id FROM person_relations WHERE kind='印谱'")]
    pr_item_ref = [r["ref_id"] for r in pc.execute("SELECT ref_id FROM person_relations WHERE kind='印谱'")]
    pr_seal_ref = [r["ref_id"] for r in pc.execute("SELECT ref_id FROM person_relations WHERE kind='印章'")]
    pr_seal_img = [r["image_key"] for r in pc.execute("SELECT image_key FROM person_relations WHERE kind='印章'")]
    sl_book = [(r["ref_id"], r["bridge_item_id"]) for r in sc.execute(
        "SELECT ref_id, bridge_item_id FROM seal_links WHERE link_kind='book'")]
    ic_p = [r["person_grbsm"] for r in ic.execute("SELECT person_grbsm FROM item_creators")]
    sl_p = [r["ref_id"] for r in sc.execute("SELECT ref_id FROM seal_links WHERE link_kind LIKE 'person_%'")]

    line(1, "person_relations(印谱).as_book_id → items.as_book_id", pr_item_bk, items_book)
    line(2, "person_relations(印谱).ref_id → items.source_item_id", pr_item_ref, items_seq)
    line(3, "person_relations(印章).ref_id → seals.source_seal_id", pr_seal_ref, seal_ids)
    line(4, "person_relations(印章).image_key → seal_images.source_ref", pr_seal_img, seal_refs)
    line(5, "seal_links(book).ref_id → items.as_book_id", [x[0] for x in sl_book], items_book)
    line(6, "seal_links(book).bridge_item_id → items.source_item_id", [x[1] for x in sl_book], items_seq)
    line(7, "item_creators.person_grbsm → persons.source_person_id", ic_p, persons)
    line(8, "seal_links(person_*).ref_id → persons.source_person_id", sl_p, persons)

    # 行 9：去重面（A ＝ item_creators(book_graph) 对；B ＝ person_relations(印谱) 对；统一 (person,item)）
    A = {(r["person_grbsm"], r["source_item_id"]) for r in
         ic.execute("SELECT person_grbsm, source_item_id FROM item_creators WHERE source_face='book_graph'")}
    B = {(r["source_person_id"], r["ref_id"]) for r in
         pc.execute("SELECT source_person_id, ref_id FROM person_relations WHERE kind='印谱'")}
    Arows = ic.execute("SELECT COUNT(*) FROM item_creators WHERE source_face='book_graph'").fetchone()[0]
    Brows = pc.execute("SELECT COUNT(*) FROM person_relations WHERE kind='印谱'").fetchone()[0]
    inter = A & B
    rows.append({"#": 9, "join": "去重面：item_creators(book_graph) vs person_relations(印谱)",
                 "A_rows": Arows, "A_set": len(A), "B_rows": Brows, "B_set": len(B),
                 "intersection": len(inter), "only_item": len(A - B), "only_person": len(B - A),
                 "union": len(A | B),
                 "formula": f"|A∪B| = |A|+|B|−|A∩B| = {len(A)}+{len(B)}−{len(inter)} = {len(A)+len(B)-len(inter)}"})

    # 源侧额外读数（照 §3.18.1）
    scale = {
        "persons_total": len(persons),
        "persons_in_person_relations": len({r[0] for r in pc.execute("SELECT DISTINCT source_person_id FROM person_relations")}),
        "persons_in_item_creators": len({r[0] for r in ic.execute("SELECT DISTINCT person_grbsm FROM item_creators")}),
        "persons_in_seal_links_resolved": len({r[0] for r in sc.execute(
            "SELECT DISTINCT ref_id FROM seal_links WHERE link_kind LIKE 'person_%'")} & persons),
        "seal_person_unique_refs": len({r[0] for r in pc.execute(
            "SELECT DISTINCT ref_id FROM person_relations WHERE kind='印章'")}),
        "person_relations_seal_creator_types": sorted({r[0] for r in pc.execute(
            "SELECT DISTINCT creator_type FROM person_relations WHERE kind='印章'")}),
        "seal_refs_with_multi_person": pc.execute(
            "SELECT COUNT(*) FROM (SELECT ref_id FROM person_relations WHERE kind='印章' GROUP BY ref_id HAVING COUNT(*)>1)"
        ).fetchone()[0],
        "ghost_rows_as_book_id_test": pc.execute(
            "SELECT COUNT(*) FROM person_relations WHERE kind='印谱' AND as_book_id='test'").fetchone()[0],
    }

    pc.close(); ic.close(); sc.close()

    out = {"nine_lines": rows, "source_scale": scale,
           "note": "独立重算（raw sqlite、只读）；未 import app.relations。"}
    (REPO / "ops" / "relation-ingest" / "02_recon.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in rows:
        if r["#"] == 9:
            print(f"#9  A={r['A_set']} B={r['B_set']} ∩={r['intersection']} onlyItem={r['only_item']} "
                  f"onlyPerson={r['only_person']} ∪={r['union']}  {r['formula']}")
        else:
            print(f"#{r['#']}  unique={r['unique']} hit={r['hit']} miss={r['miss']}  {r['join']}"
                  + (f"  miss={r['miss_values']}" if r["miss"] else ""))
    print("scale:", json.dumps(scale, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
