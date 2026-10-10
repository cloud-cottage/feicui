#!/usr/bin/env python3
"""两库指纹比对（IT-6）：证明采集全程**只写** `var/item_ingest.db`。

比对 `fingerprint_scope.py` 的 before / after 两份 JSON：
  * `yinpu.db` 各表 `content_sha256` **逐表未变**；
  * `var/person_ingest.db` 各表 `content_sha256` **逐表未变**（印谱/印人分库隔离）；
  * `exports/fb_*` 与 `exports/person_*` 批次包文件 sha256 **未变**。

用法：python3 compare_scope.py --before 00_scope_before.json --after 04_scope_after.json [--out x.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _db_diff(before: dict | None, after: dict | None) -> dict:
    b_tab = {t["table"]: t.get("content_sha256") for t in (before or {}).get("tables", [])}
    a_tab = {t["table"]: t.get("content_sha256") for t in (after or {}).get("tables", [])}
    changed = {k: [b_tab.get(k), a_tab.get(k)] for k in sorted(set(b_tab) | set(a_tab)) if b_tab.get(k) != a_tab.get(k)}
    return {"before_tables": len(b_tab), "after_tables": len(a_tab), "changed": changed, "unchanged": not changed}


def _dirs_diff(before: dict, after: dict) -> dict:
    changed = {}
    for name in sorted(set(before) | set(after)):
        if before.get(name) != after.get(name):
            changed[name] = True
    return {"dirs": sorted(set(before) | set(after)), "changed": changed, "unchanged": not changed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    b = json.loads(Path(args.before).read_text(encoding="utf-8"))
    a = json.loads(Path(args.after).read_text(encoding="utf-8"))

    out = {
        "before_label": b.get("label"), "after_label": a.get("label"),
        "yinpu_db": _db_diff(b.get("yinpu_db"), a.get("yinpu_db")),
        "person_ingest_db": _db_diff(b.get("person_ingest_db"), a.get("person_ingest_db")),
        "exports_fb": _dirs_diff(b.get("exports_fb") or {}, a.get("exports_fb") or {}),
        "exports_person": _dirs_diff(b.get("exports_person") or {}, a.get("exports_person") or {}),
    }
    out["pass"] = (out["yinpu_db"]["unchanged"] and out["person_ingest_db"]["unchanged"]
                   and out["exports_fb"]["unchanged"] and out["exports_person"]["unchanged"])
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
