#!/usr/bin/env python3
"""交付缝机械校验（证据⑧）：§3.15.10 + §7 AC-21 / AC-22，对批次包逐项断言。

只读批次包四文件，不触库、不联网。输出 JSON（ok + 每项读数）。
用法：python3 verify_delivery_seam.py [批次包目录]   # 默认 exports/person_20261010_01

**本版新增（本单）**：字 / 号 / 别名六字段（`courtesy_names` / `courtesy_names_chs` /
`art_names` / `art_names_chs` / `alias_names` / `alias_names_chs`）必须是**真 JSON 数组**
（`isinstance(v, list)`），每个元素必须是 `dict` 且 `element['extraction'] == 'rule-based'`
且 `element['value']` 非空；空值恒为 `[]`（**不得**为 `''`）。**任一不满足 ⇒ FAIL**。
并把「旧形态（JSON 字符串）」当回归样本跑同一判据，**证明该判据能对旧形态判负**。
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

# 必须是真数组（元素＝dict）的六个字段（交付缝 §3.15.10 / xiai §3.54.3）
NAME_LIST_FIELDS = ("courtesy_names", "courtesy_names_chs", "art_names", "art_names_chs",
                    "alias_names", "alias_names_chs")


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


def scan_name_lists(persons: list[dict]) -> dict:
    """对六字段逐行断言「真数组」。返回 {violations, extraction_counter, items_total}。

    判负条件（任一命中即记违规）：
      * 字段值**不是 `list`**（尤其：是 `str`／`None`／其它）⇒ `not_a_list`；
      * 元素**不是 `dict`** ⇒ `element_not_dict`；
      * 元素 `extraction != 'rule-based'` ⇒ `bad_extraction`；
      * 元素 `value` 为空（`None`／`''`／非字符串） ⇒ `empty_value`；
      * 空值**不是 `[]`**（例如 `''` / `None` / `'[]'` 字符串）⇒ `bad_empty`。
    """
    violations: list[dict] = []
    extraction = Counter()
    items_total = 0
    for p in persons:
        pid = p.get("source_person_id")
        for col in NAME_LIST_FIELDS:
            v = p.get(col)
            if not isinstance(v, list):
                violations.append({"kind": "not_a_list", "id": pid, "field": col,
                                   "got_type": type(v).__name__, "sample": str(v)[:80]})
                continue
            if len(v) == 0:
                # 空必须是 Python 空列表（JSON `[]`）——已由 isinstance(list) 保证；非空串形态已在上面拦下
                continue
            for it in v:
                items_total += 1
                if not isinstance(it, dict):
                    violations.append({"kind": "element_not_dict", "id": pid, "field": col,
                                       "got_type": type(it).__name__})
                    continue
                extraction[str(it.get("extraction"))] += 1
                if it.get("extraction") != "rule-based":
                    violations.append({"kind": "bad_extraction", "id": pid, "field": col,
                                       "got": it.get("extraction")})
                val = it.get("value")
                if not (isinstance(val, str) and val.strip()):
                    violations.append({"kind": "empty_value", "id": pid, "field": col, "got": val})
    # 空值形态：统计「非数组」里是否出现空串（对应旧形态空值）
    bad_empty = [v for v in violations if v["kind"] == "not_a_list" and v.get("sample") in ("", "None")]
    return {"violations": violations, "extraction_counter": extraction,
            "items_total": items_total, "bad_empty_count": len(bad_empty)}


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

    # ── 本单新增硬判据：六字段必须是真数组（元素为 dict、extraction=rule-based、value 非空）──
    scan = scan_name_lists(persons)
    viol = scan["violations"]
    check("AC22.name_lists_are_arrays", not viol,
          {"violations": viol[:10], "violation_count": len(viol),
           "fields": list(NAME_LIST_FIELDS), "items_total": scan["items_total"],
           "empty_string_forms": scan["bad_empty_count"]})
    check("AC22.extraction_rule_based",
          extraction_ok and scan["items_total"] > 0 and set(scan["extraction_counter"]) <= {"rule-based"},
          {"name_extraction_all_rule_based": extraction_ok,
           "item_extraction": dict(scan["extraction_counter"]),
           "items_total": scan["items_total"]})

    check("AC22.no_bom", not _bom(PKG / "persons.jsonl") and not _bom(PKG / "relations.jsonl"),
          {"persons_bom": _bom(PKG / "persons.jsonl"), "relations_bom": _bom(PKG / "relations.jsonl")})

    # 失败项只进 report.json：persons.jsonl 里不得出现失败占位（源键缺）。
    check("AC21.failures_not_in_persons", all(ids), f"persons_rows={len(persons)}")

    # ── 回归自证：同判据对「旧形态」（六字段＝JSON 字符串）必须判负 ──────────────
    old_form = {
        "source_person_id": "__REGRESSION_OLD_FORM__",
        "courtesy_names": json.dumps([{"value": "容光", "kind": "字", "extraction": "rule-based", "from": "personBm"}],
                                     ensure_ascii=False),
        "courtesy_names_chs": "",          # 旧形态的「空串」形态
        "art_names": "[]",                  # 旧形态把空写成字符串 "[]"
        "art_names_chs": json.dumps([], ensure_ascii=False),
        "alias_names": json.dumps([{"value": "郭容光", "kind": "名", "extraction": "rule-based", "from": "personBm"}],
                                  ensure_ascii=False),
        "alias_names_chs": None,
    }
    old_scan = scan_name_lists([old_form])
    res["regression_selftest"] = {
        "purpose": "证明本判据能对**旧形态（六字段＝JSON 字符串 / '' / '[]' / null）**判负",
        "old_form_value_types": {k: type(old_form[k]).__name__ for k in NAME_LIST_FIELDS},
        "old_form_verdict": "FAIL" if old_scan["violations"] else "PASS",
        "old_form_violations": old_scan["violations"],
        "new_form_verdict": "PASS" if not viol else "FAIL",
    }
    check("AC22.regression_selftest_detects_old_string_form",
          bool(old_scan["violations"]) and not viol,
          {"old_form_verdict": res["regression_selftest"]["old_form_verdict"],
           "old_form_violation_kinds": sorted({v["kind"] for v in old_scan["violations"]}),
           "new_form_verdict": res["regression_selftest"]["new_form_verdict"]})

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
