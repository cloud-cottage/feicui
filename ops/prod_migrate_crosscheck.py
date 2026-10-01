#!/usr/bin/env python3
"""迁移前备份 vs 迁移后现行库 —— 全表内容逐字比对（**全只读**）。

用法:
    ./.venv/bin/python ops/prod_migrate_crosscheck.py <before.db> <after.db>

为什么不用 `sqlite3 CLI` + `file:...?mode=ro`：
    现行库迁移后处于 **WAL** 模式，sqlite3 CLI 对 WAL 库的 `mode=ro` 打开会失败
    （`Error: in prepare, unable to open database file (14)`），此时 `| md5` 得到的是
    **空输入的 md5 `d41d8cd9...`**——会被误读成「数据变了」。本脚本用 Python sqlite3 的
    `mode=ro` URI（对 WAL 库可用，已实测）并把**行数**一并打印，避免空结果冒充结论。

口径 D（逐表）：
    `SELECT * FROM <t> ORDER BY rowid`，每行 -> {"列名":值} 的 JSON
    （ensure_ascii=False, sort_keys=True, separators=(',',':')），按行序 '\n' 连接、末尾补 '\n'，
    整体 md5 + sha256。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

EMPTY_MD5 = hashlib.md5(b"").hexdigest()


def ro_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def indexes(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%' ORDER BY name"
        )
    ]


def fingerprint(conn: sqlite3.Connection, table: str) -> tuple[int, str, str]:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    lines: list[str] = []
    rows = list(conn.execute(f"SELECT * FROM {table} ORDER BY rowid"))
    for r in rows:
        lines.append(
            json.dumps(
                {c: r[c] for c in cols},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    blob = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
    return len(rows), hashlib.md5(blob).hexdigest(), hashlib.sha256(blob).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    before_p, after_p = (Path(a).expanduser().resolve() for a in argv)
    b, a = ro_connect(before_p), ro_connect(after_p)
    try:
        tb, ta = tables(b), tables(a)
        ib, ia = indexes(b), indexes(a)
        print(f"before = {before_p}")
        print(f"after  = {after_p}")
        print()
        print("---- 库级 ----")
        for label, conn in (("before", b), ("after", a)):
            print(
                f"  {label:6s} journal_mode={conn.execute('PRAGMA journal_mode').fetchone()[0]:8s}"
                f" integrity={conn.execute('PRAGMA integrity_check').fetchone()[0]}"
                f" size={Path(before_p if label=='before' else after_p).stat().st_size}"
            )
        print(f"  tables  before = {','.join(tb)}")
        print(f"  tables  after  = {','.join(ta)}")
        print(f"  tables  NEW    = {','.join(sorted(set(ta) - set(tb))) or '(none)'}")
        print(f"  tables  GONE   = {','.join(sorted(set(tb) - set(ta))) or '(none)'}")
        print(f"  indexes before = {','.join(ib) or '(none)'}")
        print(f"  indexes after  = {','.join(ia) or '(none)'}")
        print(f"  indexes NEW    = {','.join(sorted(set(ia) - set(ib))) or '(none)'}")
        print(f"  indexes GONE   = {','.join(sorted(set(ib) - set(ia))) or '(none)'}")
        print()
        print("---- 逐表内容指纹（口径 D）----")
        diffs = []
        for t in sorted(set(tb) | set(ta)):
            rb = fingerprint(b, t) if t in tb else None
            ra = fingerprint(a, t) if t in ta else None
            sb = "n/a" if rb is None else rb[1]
            sa = "n/a" if ra is None else ra[1]
            if rb and ra:
                verdict = "SAME" if rb[1] == ra[1] else "DIFF"
            else:
                verdict = "NEW" if rb is None else "GONE"
            if verdict not in ("SAME", "NEW"):
                diffs.append(t)
            print(f"  {t:16s} rows {('?' if rb is None else rb[0]):>4}->{('?' if ra is None else ra[0]):<4}"
                  f" md5 {sb} -> {sa}  [{verdict}]")
            if rb is None:
                continue
            if ra is None:
                print(f"      sha256 {rb[2]} -> n/a")
            else:
                print(f"      sha256 {rb[2]} -> {ra[2]}")
        print()
        print("---- 判读 ----")
        if diffs:
            print(f"  ✗ 以下**既有表**内容发生变化：{','.join(diffs)}")
        else:
            print("  ✓ 所有迁移前既存表内容与迁移后**逐字相同**（无 DIFF）")
        for t in sorted(set(ta) - set(tb)):
            n = fingerprint(a, t)[0]
            print(f"  新增侧表 {t}: rows={n}")
    finally:
        b.close()
        a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
