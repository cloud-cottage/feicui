#!/usr/bin/env python3
"""内容指纹（红线判据）：**禁用数据库文件 md5**（WAL 下会漂移）。

用法：python3 ops/seal-ingest/fingerprint_guard.py > ops/seal-ingest/<ts>_guard.json
对 yinpu.db / var/person_ingest.db / var/item_ingest.db 逐表取行级内容 sha256；
并列出 exports/person_* / exports/item_* 的目录清单指纹。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def db_content_fp(path: Path) -> dict:
    out: dict = {"exists": path.is_file(), "path": str(path)}
    if not path.is_file():
        return out
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        per: dict = {}
        for t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            order = ", ".join(cols) if cols else "rowid"
            h = hashlib.sha256()
            n = 0
            for row in conn.execute(f"SELECT {order} FROM {t} ORDER BY {order}"):
                h.update(("|".join("" if v is None else str(v) for v in row)).encode("utf-8"))
                h.update(b"\n")
                n += 1
            per[t] = {"rows": n, "sha256": h.hexdigest()}
        out["tables"] = per
        out["n_tables"] = len(tables)
    finally:
        conn.close()
    return out


def exports_fp(pattern: str) -> dict:
    out: dict = {}
    root = REPO / "exports"
    for d in sorted(root.glob(pattern)):
        if not d.is_dir():
            continue
        h = hashlib.sha256()
        files = sorted(p for p in d.rglob("*") if p.is_file())
        for p in files:
            h.update(str(p.relative_to(d)).encode("utf-8"))
            h.update(str(p.stat().st_size).encode("utf-8"))
        out[d.name] = {"n_files": len(files),
                       "sha256_names_sizes": h.hexdigest()}
    return out


def main() -> int:
    result = {
        "yinpu.db": db_content_fp(REPO.parent / "data" / "yinpu.db"),
        "var/person_ingest.db": db_content_fp(REPO / "var" / "person_ingest.db"),
        "var/item_ingest.db": db_content_fp(REPO / "var" / "item_ingest.db"),
        "exports/person_*": exports_fp("person_*"),
        "exports/item_*": exports_fp("item_*"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
