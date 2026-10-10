#!/usr/bin/env python3
"""范围指纹（IT-6 判据）：证明 feicui「印谱采集」**只加法**——

  * `yinpu.db`（正式库，含 stamps / jobs / job_pages）内容**逐字节未变**；
  * **独立库** `var/person_ingest.db` 内容**逐字节未变**（印谱线与印人线分库隔离）；
  * 既有 `exports/fb_*` 与 `exports/person_*` 批次包**未动**。

口径（拆解件 §6「判据用内容指纹，禁用数据库文件 md5」）：证明「数据未变」一律用**内容指纹**，
**禁用数据库文件 md5**（WAL 会使文件 md5 在内容无变化时漂移）。

用法：
  python3 fingerprint_scope.py                # 打印 JSON 到 stdout
  python3 fingerprint_scope.py --out a.json --label before
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
YINPU_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
PERSON_DB = REPO / "var" / "person_ingest.db"
EXPORTS = REPO / "exports"
_TMP_DIRS: list[Path] = []


def _copy_db(path: Path) -> Path:
    """把库（含 -wal / -shm）只读复制到临时目录再打开（WAL 只读共享内存要求，源侧零写入）。"""
    tmp = Path(tempfile.mkdtemp(prefix="fp-"))
    _TMP_DIRS.append(tmp)
    dst = tmp / path.name
    shutil.copy2(path, dst)
    for suffix in ("-wal", "-shm"):
        sib = path.with_name(path.name + suffix)
        if sib.is_file():
            shutil.copy2(sib, tmp / sib.name)
    return dst


def _conn_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_copy_db(path)), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _norm(v):
    if isinstance(v, (bytes, bytearray)):
        return f"<bytes:{len(v)}:{hashlib.sha256(bytes(v)).hexdigest()}>"
    return v


def _table_fingerprint(conn: sqlite3.Connection, table: str, order_cols: list[str]) -> dict:
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    except Exception as exc:  # noqa: BLE001
        return {"table": table, "error": str(exc)}
    if not cols:
        return {"table": table, "exists": False}
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    order = ", ".join(order_cols) if order_cols else cols[0]
    h = hashlib.sha256()
    for row in conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}"):
        h.update(json.dumps([_norm(v) for v in row], ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return {"table": table, "exists": True, "columns": cols, "rows": n, "content_sha256": h.hexdigest()}


def _db_scope(path: Path) -> dict | None:
    if not path.is_file():
        return None
    conn = _conn_ro(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        tables = []
        for name in names:
            if name.startswith("sqlite_"):
                continue
            tables.append(_table_fingerprint(conn, name, []))
        return {"path": str(path), "tables": tables}
    finally:
        conn.close()


def _dir_fingerprint(prefix: str) -> dict:
    out = {}
    if not EXPORTS.is_dir():
        return out
    for d in sorted(EXPORTS.iterdir()):
        if d.is_dir() and d.name.startswith(prefix):
            files = {}
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    files[str(f.relative_to(EXPORTS))] = hashlib.sha256(f.read_bytes()).hexdigest()
            out[d.name] = files
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    result: dict = {"label": args.label}
    result["yinpu_db"] = _db_scope(YINPU_DB)
    result["person_ingest_db"] = _db_scope(PERSON_DB)
    result["exports_fb"] = _dir_fingerprint("fb_")
    result["exports_person"] = {**_dir_fingerprint("person_")}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    for d in _TMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
