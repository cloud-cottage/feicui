#!/usr/bin/env python3
"""③ 门禁指纹 —— yinpu.db + 三 ingest 库（内容指纹：逐表行数 + 有序全字段 sha256）＋
三线既有就绪包（`exports/{person,item,seal}_*` 树指纹：文件名+大小+逐个 sha256）。**只读**。

用法：`03_guard.py before|after` ⇒ 写 `03_guard_before.json` / `04_guard_after.json`。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
YINPU = REPO.parent / "data" / "yinpu.db"          # xiai/data/yinpu.db
DBS = {
    "yinpu.db": YINPU,
    "var/person_ingest.db": REPO / "var" / "person_ingest.db",
    "var/item_ingest.db": REPO / "var" / "item_ingest.db",
    "var/seal_ingest.db": REPO / "var" / "seal_ingest.db",
}


def ro(p: Path) -> sqlite3.Connection:
    # WAL 库在无写权限 / -shm 受限时 `mode=ro` 会报「unable to open database file」⇒ 退回 immutable=1。
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        c.execute("SELECT 1").fetchone()
    except sqlite3.OperationalError:
        c = sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def db_fingerprint(p: Path) -> dict:
    out: dict = {"exists": p.is_file(), "path": str(p), "tables": {}}
    if not p.is_file():
        return out
    c = ro(p)
    try:
        tabs = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tabs:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
            h = hashlib.sha256()
            n = 0
            for row in c.execute(f"SELECT * FROM {t}"):
                h.update(json.dumps([row[cc] for cc in cols], ensure_ascii=False, default=str).encode("utf-8"))
                h.update(b"\n")
                n += 1
            out["tables"][t] = {"rows": n, "n_cols": len(cols), "sha256": h.hexdigest()}
    finally:
        c.close()
    out["n_tables"] = len(out["tables"])
    return out


def tree_fingerprint(p: Path) -> dict:
    """树指纹：文件名+大小+逐个 sha256 的聚合 sha256（**只存聚合值，不存逐文件明细**，控体积）。"""
    recs = []
    if p.is_dir():
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            h = hashlib.sha256()
            with f.open("rb") as fh:
                for c in iter(lambda: fh.read(1 << 16), b""):
                    h.update(c)
            recs.append((str(f.relative_to(p)), f.stat().st_size, h.hexdigest()))
    agg = hashlib.sha256()
    for name, size, sha in recs:
        agg.update(json.dumps([name, size, sha], ensure_ascii=False).encode("utf-8"))
        agg.update(b"\n")
    return {"path": str(p), "n_files": len(recs), "sha256_names_sizes": agg.hexdigest()}


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "before"
    out = {"stage": stage, "dbs": {k: db_fingerprint(p) for k, p in DBS.items()},
           "export_packages": {}}
    for prefix in ("person", "item", "seal"):
        for p in sorted((REPO / "exports").glob(f"{prefix}*")):
            if p.is_dir():
                out["export_packages"][p.name] = tree_fingerprint(p)
    fname = "03_guard_before.json" if stage == "before" else "04_guard_after.json"
    (REPO / "ops" / "relation-ingest" / fname).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{stage}] wrote {fname}")
    for k, v in out["dbs"].items():
        print(f"  {k}: n_tables={v.get('n_tables')} rows="
              + json.dumps({t: d['rows'] for t, d in v['tables'].items()}, ensure_ascii=False))
    for k, v in out["export_packages"].items():
        print(f"  pkg {k}: n_files={v['n_files']} sha={v['sha256_names_sizes'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
