#!/usr/bin/env python3
"""stamps 全表内容指纹（只读，可复算）——feicui 正式库迁移取证（Kong）。

用法：
    ./.venv/bin/python ops/prod_migrate_fingerprint.py /path/to/yinpu.db

口径（三套，互不依赖，迁移前后逐字比对）：
  A raw  : 等价于 `sqlite3 <db> "select * from stamps order by id" | md5`。
           逐行以 '|' 连接全部列（NULL -> 空串），行尾 '\n'，无表头。
           若任一文本值含 '|' 或换行，会打印 WARN（此时 A 有歧义，以 B/C 为准）。
  B canon: 每行 -> {"列名": 值} 的 JSON（ensure_ascii=False, sort_keys=True,
           separators=(',',':')），按 id 升序，行间 '\n' 连接，末尾补 '\n'；
           整体 md5 + sha256。
  C free : 把各行 canonical JSON 字符串升序排序后拼接的 md5 + sha256
           （与 id 顺序无关，用于交叉校验 B）。

同时输出：行数 / 列定义 / 逐列非空计数 / 逐书名计数。绝不写库（mode=ro 打开）。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def md5s(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def sha256s(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    db_path = Path(argv[0]).expanduser().resolve()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        cols = [(r[1], r[2]) for r in conn.execute("PRAGMA table_info(stamps)")]
        rows = list(conn.execute("SELECT * FROM stamps ORDER BY id"))
        names = [c[0] for c in cols]

        ambiguous = False
        raw_lines = []
        canon_lines = []
        for r in rows:
            vals = [r[n] for n in names]
            for v in vals:
                if isinstance(v, str) and ("|" in v or "\n" in v or "\r" in v):
                    ambiguous = True
            raw_lines.append("|".join("" if v is None else str(v) for v in vals))
            canon_lines.append(
                json.dumps(
                    {n: r[n] for n in names},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )

        a_blob = ("\n".join(raw_lines) + "\n").encode("utf-8") if rows else b""
        b_blob = ("\n".join(canon_lines) + "\n").encode("utf-8") if rows else b""
        c_blob = ("\n".join(sorted(canon_lines)) + "\n").encode("utf-8") if rows else b""

        print(f"db            = {db_path}")
        print(f"table         = stamps")
        print(f"columns       = {len(cols)} -> {','.join(names)}")
        print(f"rows          = {len(rows)}")
        print()
        print("---- 逐列非空计数 ----")
        for n in names:
            cnt = sum(1 for r in rows if r[n] is not None and str(r[n]) != "")
            print(f"  {n:9s} nonempty = {cnt}")
        print()
        print("---- 逐 pdf_name 计数 ----")
        for r in conn.execute(
            "SELECT pdf_name, count(*) c FROM stamps GROUP BY pdf_name ORDER BY pdf_name"
        ):
            print(f"  {r['pdf_name']}  ->  {r['c']}")
        print()
        print("---- 内容指纹（三套口径）----")
        if ambiguous:
            print("  WARN: 存在含 '|' 或换行的文本值，口径 A 有歧义，请以 B/C 为准")
        print(f"  A raw   md5    = {md5s(a_blob)}")
        print(f"  A raw   sha256 = {sha256s(a_blob)}")
        print(f"  B canon md5    = {md5s(b_blob)}")
        print(f"  B canon sha256 = {sha256s(b_blob)}")
        print(f"  C free  md5    = {md5s(c_blob)}")
        print(f"  C free  sha256 = {sha256s(c_blob)}")
        print()
        print("---- PRAGMA ----")
        print(f"  journal_mode = {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
        print(f"  integrity_check = {conn.execute('PRAGMA integrity_check').fetchone()[0]}")
        print(f"  user_version = {conn.execute('PRAGMA user_version').fetchone()[0]}")
        print(f"  foreign_key_check = {len(list(conn.execute('PRAGMA foreign_key_check')))} row(s)")
        print()
        print("---- sqlite_master ----")
        for r in conn.execute(
            "SELECT type, name FROM sqlite_master ORDER BY type, name"
        ):
            print(f"  {r[0]:5s} {r[1]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
