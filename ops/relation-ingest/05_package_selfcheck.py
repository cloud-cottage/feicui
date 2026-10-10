#!/usr/bin/env python3
"""④ 就绪包自检（含**旧形态 FAIL 对照**）—— 读包（只读），逐项判据。

判据面：
  ① 形态：一行一对象 / UTF-8 / 无 BOM / 键面恰为 §3.18.2 的 14 键 ＋ R-c 两标记 / `evidence` 为真数组。
  ② 计数一致：`relations.jsonl` 各 predicate 行数 ＝ `manifest.predicate_counts` ＝ `report.predicate_counts`。
  ③ 幂等键三元组唯一（＝ 行数）。
  ④ 去重算术自洽：`|A∪B| = |A|+|B|−|A∩B|`（逐项复算）。
  ⑤ 幽灵 / 未收录清单存在且可核（ghost ≥ 1 行、未收录印人 id ＝ 14）。
  ⑥ `key_face_status == "pending_xiai"`；manifest 必含项齐备（§3.18.5）。
  ⑦ A-3 可连键：抽样 person_to_item 的 object_id ∈ items.source_item_id（除 ghost 行）；
     每条印章边 subject_id ∈ seals.source_seal_id。
  ⑧ **旧形态 FAIL 对照**：把 `evidence` 改成字符串（旧形态）后，同一形态判据必须**判负**。

输出 `05_package_selfcheck.json`。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
PKG = REPO / "exports" / "relation_import_relation_20261010_01"
ITEM = REPO / "var" / "item_ingest.db"
SEAL = REPO / "var" / "seal_ingest.db"

EDGE_KEYS = ["predicate", "subject_type", "subject_id", "object_type", "object_id",
             "role", "role_note", "evidence", "source_ref", "image_ref",
             "name", "name_chs", "seq", "batch_id", "ghost", "person_resolved"]
ENUM = {"person_to_item", "item_to_person", "person_to_seal", "seal_to_item", "seal_to_person"}


def ro(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.execute("PRAGMA query_only=ON")
    return c


def check_form(rows: list[dict]) -> dict:
    key_mismatch = [i for i, r in enumerate(rows) if list(r.keys()) != EDGE_KEYS]
    ev_not_list = [i for i, r in enumerate(rows)
                   if not (isinstance(r.get("evidence"), list) and all(isinstance(x, str) for x in r["evidence"]))]
    ev_empty = [i for i, r in enumerate(rows) if not r.get("evidence")]
    enum_bad = sorted({r["predicate"] for r in rows} - ENUM)
    seq_bad = [i for i, r in enumerate(rows) if not isinstance(r.get("seq"), int)]
    return {
        "n": len(rows),
        "keys_exact": len(key_mismatch) == 0, "keys_mismatch_idx": key_mismatch[:10],
        "evidence_is_list_of_str": len(ev_not_list) == 0, "evidence_bad_idx": ev_not_list[:10],
        "evidence_non_empty": len(ev_empty) == 0,
        "predicate_all_in_enum": not enum_bad, "predicate_extra": enum_bad,
        "seq_all_int": len(seq_bad) == 0,
        "PASS": (len(key_mismatch) == 0 and len(ev_not_list) == 0 and not enum_bad and len(seq_bad) == 0),
    }


def main() -> int:
    raw = (PKG / "relations.jsonl").read_bytes()
    no_bom = raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    lines = text.splitlines()
    rows = [json.loads(x) for x in lines if x.strip()]
    manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((PKG / "report.json").read_text(encoding="utf-8"))

    # ① 形态
    form = check_form(rows)
    form["no_bom"] = no_bom
    form["one_object_per_line"] = (len(lines) == len(rows))

    # ② 计数一致
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["predicate"]] = counts.get(r["predicate"], 0) + 1
    manifest_files = {f["name"]: f for f in manifest["files"]}
    c2 = {
        "jsonl_counts": counts,
        "manifest_counts": manifest["predicate_counts"],
        "report_counts": report["predicate_counts"],
        "manifest_jsonl_rows_field": manifest_files["relations.jsonl"]["rows"],
        "all_equal": (counts == manifest["predicate_counts"] == report["predicate_counts"]
                      and manifest_files["relations.jsonl"]["rows"] == len(rows)),
    }

    # ③ 幂等键三元组唯一
    triples = [(r["predicate"], r["subject_id"], r["object_id"]) for r in rows]
    c3 = {"rows": len(rows), "unique_triples": len(set(triples)),
          "all_unique": len(triples) == len(set(triples)),
          "manifest_idempotency": manifest["idempotency"]}

    # ④ 去重算术复算
    da = report["dedup_arithmetic"]
    A, B, inter = da["sets"]["A"]["set"], da["sets"]["B"]["set"], da["intersection"]
    c4 = {"A": A, "B": B, "intersection": inter, "union_reported": da["union"],
          "recomputed_union": A + B - inter,
          "formula_ok": (A + B - inter == da["union"]),
          "only_item": da["only_item"], "only_person": da["only_person"],
          "check_only": (A - inter == da["only_item"] and B - inter == da["only_person"]),
          "dedup_before": report["dedup"]["before"], "dedup_after": report["dedup"]["after"]}

    # ⑤ 幽灵 / 未收录清单
    ghost_rows = [r for r in rows if r.get("ghost")]
    c5 = {
        "ghost_rows_in_jsonl": len(ghost_rows),
        "ghost_unique_source_ref": sorted({r["source_ref"] for r in ghost_rows}),
        "report_ghost_count": report["ghost"]["count"],
        "report_ghost_unique_as_book_id": report["ghost"]["unique_as_book_id"],
        "unresolved_person_ids": report["unresolved_person_ids"],
        "unresolved_count": len(report["unresolved_person_ids"]),
        "person_resolved_false_rows": sum(1 for r in rows if r.get("person_resolved") is False),
        "ghost_listed": len(ghost_rows) >= 1 and report["ghost"]["count"] == len(ghost_rows),
        "unresolved_listed_14": len(report["unresolved_person_ids"]) == 14,
    }

    # ⑥ manifest 必含项
    required = ["schema_version", "created_at", "source_tables", "files", "field_dict",
                "idempotency", "predicate_counts", "coverage", "key_face_status"]
    c6 = {"key_face_status": manifest.get("key_face_status"),
          "missing_required": [k for k in required if k not in manifest],
          "schema_version": manifest.get("schema_version"),
          "has_pending": manifest.get("key_face_status") == "pending_xiai",
          "PASS": (manifest.get("key_face_status") == "pending_xiai"
                   and all(k in manifest for k in required)
                   and manifest.get("schema_version") == 1)}

    # ⑦ A-3 可连键（全量，非抽样）
    ic = ro(ITEM); items_seq = {r[0] for r in ic.execute("SELECT source_item_id FROM items")}; ic.close()
    sc = ro(SEAL); seal_ids = {r[0] for r in sc.execute("SELECT source_seal_id FROM seals")}; sc.close()
    p2i_bad = [r for r in rows if r["predicate"] == "person_to_item"
               and r["object_id"] not in items_seq and not r["ghost"]]
    seal_bad = [r for r in rows if r["subject_type"] == "seal" and r["subject_id"] not in seal_ids]
    item_bad = [r for r in rows if r["object_type"] == "item" and r["object_id"] not in items_seq
                and not r["ghost"]]
    c7 = {"person_to_item_unresolved_non_ghost": len(p2i_bad),
          "seal_subject_not_in_seals": len(seal_bad), "sample_seal_bad": seal_bad[:5],
          "item_object_unresolved_non_ghost": len(item_bad),
          "PASS": (not p2i_bad and not seal_bad and not item_bad)}

    # ⑧ 旧形态 FAIL 对照（evidence 由真数组改成字符串 ⇒ 形态判据必须判负）
    legacy = [dict(rows[0])]
    legacy[0]["evidence"] = "person_graph"          # 旧形态：JSON 字符串，非真数组
    legacy_form = check_form(legacy)
    c8 = {"legacy_evidence_type": type(legacy[0]["evidence"]).__name__,
          "legacy_evidence_is_list_of_str": legacy_form["evidence_is_list_of_str"],
          "legacy_PASS_should_be_false": legacy_form["PASS"],
          "control_ok": legacy_form["PASS"] is False and legacy_form["evidence_is_list_of_str"] is False}

    out = {"check1_form": form, "check2_counts": c2, "check3_idempotency": c3,
           "check4_dedup_arithmetic": c4, "check5_ghost_unresolved": c5,
           "check6_manifest": c6, "check7_connA3": c7, "check8_legacy_fail_control": c8}
    (REPO / "ops" / "relation-ingest" / "05_package_selfcheck.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "c1_form_PASS": form["PASS"], "c1_no_bom": no_bom, "c1_one_obj_per_line": form["one_object_per_line"],
        "c2_all_equal": c2["all_equal"], "c2_counts": counts,
        "c3_all_unique": c3["all_unique"], "c3_unique": c3["unique_triples"],
        "c4_formula_ok": c4["formula_ok"], "c4_union": c4["recomputed_union"],
        "c5_ghost_rows": c5["ghost_rows_in_jsonl"], "c5_unresolved": c5["unresolved_count"],
        "c6_PASS": c6["PASS"], "c6_key_face": c6["key_face_status"],
        "c7_PASS": c7["PASS"], "c7_p2i_bad": c7["person_to_item_unresolved_non_ghost"],
        "c8_control_ok": c8["control_ok"], "c8_legacy_PASS": c8["legacy_PASS_should_be_false"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
