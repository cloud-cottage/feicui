#!/usr/bin/env python3
"""交付缝机械校验（证据⑧）：§3.15.10 + §7 AC-21 / AC-22，对批次包逐项断言。

只读批次包四文件，不触库、不联网。输出 JSON（ok + 每项读数）。
用法：python3 verify_delivery_seam.py [批次包目录]   # 默认 exports/person_20261010_01
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
PKG = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "exports" / "person_20261010_01"

REQUIRED_CHS = ["name_full_chs", "courtesy_names_chs", "art_names_chs",
                "alias_names_chs", "native_place_chs", "biography_chs", "nationality_chs"]


def _load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _bom(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(3) == b"\xef\xbb\xbf"


def main() -> int:
    res: dict = {"package": str(PKG), "checks": {}, "ok": True}

    def check(name: str, passed: bool, detail):
        res["checks"][name] = {"pass": bool(passed), "detail": detail}
        if not passed:
            res["ok"] = False

    manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    res["manifest"] = manifest

    # ── AC-21 ───────────────────────────────────────────────────────────────
    check("AC21.schema_version==1", manifest.get("schema_version") == 1,
          f"value={manifest.get('schema_version')!r} type={type(manifest.get('schema_version')).__name__}")
    check("AC21.has_created_at", bool(manifest.get("created_at")), manifest.get("created_at"))
    eps = manifest.get("source_endpoints") or []
    check("AC21.endpoints_has_pageRows1000",
          any("pageRows" in str(e) and "1000" in str(e) for e in eps), eps)
    check("AC21.source_total==570", manifest.get("source_total") == 570, manifest.get("source_total"))

    files = manifest.get("files") or []
    fmap = {f.get("name"): f for f in files if isinstance(f, dict)}
    check("AC21.files_listed", {"persons.jsonl", "relations.jsonl"} <= set(fmap), list(fmap))

    persons = _load_jsonl(PKG / "persons.jsonl")
    relations = _load_jsonl(PKG / "relations.jsonl")
    pkeys = list(persons[0].keys()) if persons else []
    rkeys = list(relations[0].keys()) if relations else []
    check("AC21.persons_rows_match", fmap.get("persons.jsonl", {}).get("rows") == len(persons),
          f"manifest={fmap.get('persons.jsonl', {}).get('rows')} actual={len(persons)}")
    check("AC21.relations_rows_match", fmap.get("relations.jsonl", {}).get("rows") == len(relations),
          f"manifest={fmap.get('relations.jsonl', {}).get('rows')} actual={len(relations)}")
    pfields = list(fmap.get("persons.jsonl", {}).get("fields") or [])
    rfields = list(fmap.get("relations.jsonl", {}).get("fields") or [])
    check("AC21.persons_fieldlist_diff==0", pfields == pkeys,
          {"manifest_only": [x for x in pfields if x not in pkeys],
           "jsonl_only": [x for x in pkeys if x not in pfields], "equal": pfields == pkeys})
    check("AC21.relations_fieldlist_diff==0", rfields == rkeys,
          {"manifest_only": [x for x in rfields if x not in rkeys],
           "jsonl_only": [x for x in rkeys if x not in rfields], "equal": rfields == rkeys})

    # ── AC-22 ───────────────────────────────────────────────────────────────
    ids = [p.get("source_person_id") for p in persons]
    check("AC22.idempotent_key_nonnull", all(i not in (None, "") for i in ids),
          f"null_count={sum(1 for i in ids if i in (None, ''))}")
    uniq = len(set(ids))
    check("AC22.idempotent_key_unique", uniq == len(persons), f"unique={uniq} rows={len(persons)}")

    missing_chs = [k for k in REQUIRED_CHS if k not in pkeys]
    check("AC22.chs_subfields_present", not missing_chs,
          {"missing": missing_chs, "required": REQUIRED_CHS})

    bad_dates = []
    distinct_b, distinct_d = set(), set()
    for p in persons:
        for col, bag in (("birth_year", distinct_b), ("death_year", distinct_d)):
            v = p.get(col)
            bag.add(v if not isinstance(v, bool) else f"bool:{v}")
            if not (v is None or (isinstance(v, int) and not isinstance(v, bool))):
                bad_dates.append({"id": p.get("source_person_id"), col: v})
            if v == 0:
                bad_dates.append({"id": p.get("source_person_id"), col: "ZERO"})
    check("AC22.dates_int_or_null", not bad_dates, {"bad": bad_dates[:10], "count": len(bad_dates)})
    check("AC22.dates_no_special_values", 0 not in distinct_b and 0 not in distinct_d
          and "?" not in distinct_b and "?" not in distinct_d,
          {"birth_distinct": sorted(map(str, distinct_b)), "death_distinct": sorted(map(str, distinct_d))})

    extraction_ok = all(p.get("name_extraction") == "rule-based" for p in persons)
    # 抽取项数组里的逐项标注
    item_extraction = Counter()
    for p in persons:
        for col in ("courtesy_names", "art_names", "alias_names"):
            try:
                items = json.loads(p.get(col) or "[]")
            except Exception:
                items = []
            for it in items:
                item_extraction[str(it.get("extraction"))] += 1
    check("AC22.extraction_rule_based", extraction_ok and set(item_extraction) <= {"rule-based"},
          {"name_extraction_all_rule_based": extraction_ok, "item_extraction": dict(item_extraction)})

    check("AC22.no_bom", not _bom(PKG / "persons.jsonl") and not _bom(PKG / "relations.jsonl"),
          {"persons_bom": _bom(PKG / "persons.jsonl"), "relations_bom": _bom(PKG / "relations.jsonl")})

    # 失败项只进 report.json：persons.jsonl 里不得出现失败占位（源键缺）。
    check("AC21.failures_not_in_persons", all(ids), f"persons_rows={len(persons)}")

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
