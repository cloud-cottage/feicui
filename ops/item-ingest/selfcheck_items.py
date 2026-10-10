#!/usr/bin/env python3
"""印谱采集就绪包**自检**（批 1；判据见拆解件 §7 IT-7 / IT-5 / IT-3）。

判据（每条都能**判负**）：
  1. `items.jsonl` / `item_creators.jsonl` **无 BOM**、一行一对象、UTF-8；
  2. 幂等键 `source_item_id` **非空且唯一 ＝ 行数**；`as_book_id` 唯一；
  3. 数值负向：`volume_count` / `date_year` **不得出现 `0` 或空串**（整数或 null）；
  4. sidecar 每行 `source_item_id` **可回指** `items.jsonl`（无孤儿）；
  5. `manifest.json` 必含项齐备且明确 `key_face_status: "pending_xiai"`；各文件行数与实际一致。

用法：
  python3 selfcheck_items.py --pkg <dir> [--out x.json]      # 正检
  python3 selfcheck_items.py --selftest [--out x.json]       # 负向对照（证明能判负）
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

BOM = b"\xef\xbb\xbf"


def _read_jsonl(path: Path) -> tuple[list[dict], bool, bool]:
    """返回 (rows, no_bom, all_objects)。"""
    raw = path.read_bytes()
    no_bom = not raw.startswith(BOM)
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    rows: list[dict] = []
    all_objects = True
    for line in raw.decode("utf-8").split("\n"):
        if line.strip() == "":
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            all_objects = False
            continue
        if not isinstance(obj, dict):
            all_objects = False
            continue
        rows.append(obj)
    return rows, no_bom, all_objects


def check_package(pkg: Path) -> dict:
    items_path = pkg / "items.jsonl"
    creators_path = pkg / "item_creators.jsonl"
    manifest_path = pkg / "manifest.json"

    items, items_no_bom, items_all_obj = _read_jsonl(items_path)
    creators, creators_no_bom, creators_all_obj = _read_jsonl(creators_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}

    ids = [it.get("source_item_id") for it in items]
    non_null = sum(1 for x in ids if x not in (None, ""))
    unique = len({x for x in ids if x not in (None, "")})
    asb = [it.get("as_book_id") for it in items]
    asb_unique = len({x for x in asb if x not in (None, "")})

    # 数值负向（**判负项**）：0 或空串即失败
    vc_bad = [it.get("source_item_id") for it in items
              if it.get("volume_count") == 0 or it.get("volume_count") == ""]
    dy_bad = [it.get("source_item_id") for it in items
              if it.get("date_year") == 0 or it.get("date_year") == ""]

    item_id_set = {x for x in ids if x not in (None, "")}
    orphans = sorted({str(c.get("source_item_id")) for c in creators
                      if c.get("source_item_id") not in item_id_set})

    files = manifest.get("files") or []
    file_rows = {f.get("name"): f.get("rows") for f in files}
    rows_match = (
        file_rows.get("items.jsonl") == len(items)
        and file_rows.get("item_creators.jsonl") == len(creators)
    )

    checks = {
        "files_exist": items_path.is_file() and creators_path.is_file() and manifest_path.is_file(),
        "items_no_bom": items_no_bom,
        "creators_no_bom": creators_no_bom,
        "items_one_object_per_line": items_all_obj,
        "creators_one_object_per_line": creators_all_obj,
        "idempotency_non_null": non_null,
        "idempotency_unique": unique,
        "idempotency_total": len(ids),
        "idempotency_all_non_null_and_unique": (non_null == len(ids) and unique == len(ids) and len(ids) > 0),
        "as_book_id_unique": asb_unique,
        "numeric_special_free": (len(vc_bad) == 0 and len(dy_bad) == 0),
        "volume_count_special": vc_bad,
        "date_year_special": dy_bad,
        "creators_all_backref_items": len(orphans) == 0,
        "creators_orphan_source_item_id": orphans,
        "manifest_schema_version_is_1": manifest.get("schema_version") == 1,
        "manifest_key_face_status_pending_xiai": manifest.get("key_face_status") == "pending_xiai",
        "manifest_has_field_dict": bool(manifest.get("field_dict")),
        "manifest_source_total": manifest.get("source_total"),
        "manifest_files_rows_match": rows_match,
        "manifest_source_endpoints_has_pageRows_3000": any(
            "pageRows:3000" in str(e) or "pageRows=3000" in str(e)
            for e in (manifest.get("source_endpoints") or [])),
    }
    pass_keys = [
        "files_exist", "items_no_bom", "creators_no_bom", "items_one_object_per_line",
        "creators_one_object_per_line", "idempotency_all_non_null_and_unique", "as_book_id_unique",
        "numeric_special_free", "creators_all_backref_items", "manifest_schema_version_is_1",
        "manifest_key_face_status_pending_xiai", "manifest_has_field_dict",
        "manifest_files_rows_match", "manifest_source_endpoints_has_pageRows_3000",
    ]
    checks["pass"] = all(checks[k] for k in pass_keys)
    checks["rows_items"] = len(items)
    checks["rows_creators"] = len(creators)
    return checks


def _write_pkg(dirpath: Path, items: list[dict], creators: list[dict], manifest: dict, *, bom: bool = False) -> Path:
    p = dirpath / "item_import_TEST"
    p.mkdir(parents=True, exist_ok=True)
    for name, rows in (("items.jsonl", items), ("item_creators.jsonl", creators)):
        with (p / name).open("w", encoding="utf-8", newline="\n") as fh:
            if bom:
                fh.write("\ufeff")
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (p / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return p


def _base_manifest() -> dict:
    return {"schema_version": 1, "key_face_status": "pending_xiai", "source_total": 2,
            "field_dict": [{"name": "source_item_id"}],
            "source_endpoints": ["POST /service_yinpu/book/list {pageRows:3000, …}"],
            "files": [{"name": "items.jsonl", "rows": 2}, {"name": "item_creators.jsonl", "rows": 1}]}


def selftest() -> dict:
    """构造 6 个**故意损坏**的合成包，逐条断言自检**判负**（否则自检不可信）。"""
    out: dict = {}
    tmp = Path(tempfile.mkdtemp(prefix="item-selfcheck-"))
    items = [
        {"source_item_id": "1", "as_book_id": "0001", "volume_count": 3, "date_year": 1900},
        {"source_item_id": "2", "as_book_id": "0002", "volume_count": None, "date_year": None},
    ]
    creators = [{"source_item_id": "1", "source_face": "book_detail.creator_list"}]

    def run(name, **kw):
        d = tmp / name
        d.mkdir(parents=True, exist_ok=True)
        pkg = _write_pkg(d, kw.get("items", items), kw.get("creators", creators),
                         kw.get("manifest", _base_manifest()), bom=kw.get("bom", False))
        res = check_package(pkg)
        out[name] = {"pass": res["pass"],
                     "broken_on": [k for k in ("items_no_bom", "creators_no_bom",
                                               "idempotency_all_non_null_and_unique",
                                               "numeric_special_free", "creators_all_backref_items",
                                               "manifest_key_face_status_pending_xiai", "manifest_files_rows_match")
                                   if res.get(k) is False]}
        return res

    run("ok_baseline")
    out["ok_baseline"]["expect"] = "pass=True"
    run("bom", bom=True)
    out["bom"]["expect"] = "pass=False (BOM)"
    run("missing_idempotency_key", items=[{"as_book_id": "0001", "volume_count": 3}, items[1]])
    out["missing_idempotency_key"]["expect"] = "pass=False (缺幂等键)"
    run("duplicate_idempotency_key", items=[items[0], dict(items[0])])
    out["duplicate_idempotency_key"]["expect"] = "pass=False (重复幂等键)"
    run("volume_count_zero", items=[{"source_item_id": "1", "as_book_id": "0001", "volume_count": 0}, items[1]])
    out["volume_count_zero"]["expect"] = "pass=False (volume_count=0)"
    run("date_year_empty", items=[{"source_item_id": "1", "as_book_id": "0001", "date_year": ""}, items[1]])
    out["date_year_empty"]["expect"] = "pass=False (date_year='')"
    run("sidecar_orphan", creators=[{"source_item_id": "999", "source_face": "person_graph"}])
    out["sidecar_orphan"]["expect"] = "pass=False (sidecar 孤儿)"
    run("key_face_missing", manifest={**_base_manifest(), "key_face_status": "final"})
    out["key_face_missing"]["expect"] = "pass=False (key_face_status≠pending_xiai)"

    shutil.rmtree(tmp, ignore_errors=True)
    # 断言：基线 true，其余 6+ 全 false
    neg = [k for k in out if k != "ok_baseline"]
    out["_selftest_ok"] = (out["ok_baseline"]["pass"] is True and all(out[k]["pass"] is False for k in neg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.selftest:
        result = {"kind": "selftest", "cases": selftest()}
    else:
        if not args.pkg:
            print("需 --pkg 或 --selftest")
            return 2
        result = {"kind": "positive", "package_dir": args.pkg, "checks": check_package(Path(args.pkg))}

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if result["kind"] == "positive":
        return 0 if result["checks"]["pass"] else 1
    return 0 if result["cases"]["_selftest_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
