#!/usr/bin/env python3
"""`stamps` 内容指纹（只读，可复算）——阶段 1c-激活取证；**禁用库文件 md5**（WAL 下会漂）。

用法：
    ./server/.venv/bin/python ops/1c/fingerprint_rows.py <db> [--id-max N]

口径与 `../prod_migrate_fingerprint.py` **逐字同源**（A raw / B canon / C free，三套互不依赖），
另加 `--id-max`：只对 `id <= N` 的行取指纹 —— 用于证明「**原有行逐字未变**」而新行（id > N）被排除。

    A raw  : 等价 `sqlite3 <db> "select * from stamps order by id" | md5`（逐行 '|' 连接全部列，
             NULL→空串，行尾 '\\n'，无表头）
    B canon: 每行 → {"列名": 值} 的 canonical JSON（ensure_ascii=False, sort_keys=True,
             separators=(',',':')），按 id 升序，行间 '\\n'
    C free : 各行 canonical JSON **升序排序**后拼接（与 id 顺序无关，交叉校验 B）
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def fingerprints(rows, names) -> dict:
    raw, canon = [], []
    for r in rows:
        raw.append("|".join("" if r[n] is None else str(r[n]) for n in names))
        canon.append(json.dumps({n: r[n] for n in names}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    a = ("\n".join(raw) + "\n").encode("utf-8") if rows else b""
    b = ("\n".join(canon) + "\n").encode("utf-8") if rows else b""
    c = ("\n".join(sorted(canon)) + "\n").encode("utf-8") if rows else b""
    return {
        "A_raw_md5": hashlib.md5(a).hexdigest(),
        "A_raw_sha256": hashlib.sha256(a).hexdigest(),
        "B_canon_md5": hashlib.md5(b).hexdigest(),
        "B_canon_sha256": hashlib.sha256(b).hexdigest(),
        "C_free_md5": hashlib.md5(c).hexdigest(),
        "C_free_sha256": hashlib.sha256(c).hexdigest(),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    db_path = Path(argv[0]).expanduser().resolve()
    id_max: int | None = None
    if "--id-max" in argv:
        id_max = int(argv[argv.index("--id-max") + 1])

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        names = [r[1] for r in conn.execute("PRAGMA table_info(stamps)")]
        where = f" WHERE id <= {id_max}" if id_max is not None else ""
        rows = list(conn.execute(f"SELECT * FROM stamps{where} ORDER BY id"))
        print(f"db       = {db_path}")
        print(f"filter   = {'id <= %d' % id_max if id_max is not None else '(全表)'}")
        print(f"columns  = {len(names)} -> {','.join(names)}")
        print(f"rows     = {len(rows)}")
        for r in conn.execute(
            f"SELECT pdf_name, count(*) c FROM stamps{where} GROUP BY pdf_name ORDER BY pdf_name"
        ):
            print(f"  {r['pdf_name']}  ->  {r['c']}")
        fp = fingerprints(rows, names)
        for k, v in fp.items():
            print(f"  {k} = {v}")
        print(f"  total_stamps_rows_in_db = {conn.execute('SELECT count(*) FROM stamps').fetchone()[0]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
