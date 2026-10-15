#!/usr/bin/env python3
"""范围指纹（红线判据②）：证明 feicui「印人采集」**只加法**——
  * `yinpu.db`（正式库，含 stamps / jobs / job_pages）内容**逐字节未变**；
  * 既有 `exports/fb_*` 批次包**未动**。

口径（拆解件 §6「红线判据」）：证明「数据未变」一律用**内容指纹**，
**禁用数据库文件 md5**（WAL 会使文件 md5 在内容无变化时漂移）。

用法：
  python3 fingerprint_scope.py                # 打印 JSON 到 stdout
  python3 fingerprint_scope.py --out a.json   # 另存
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

REPO = Path("/Users/kevin/bistro/feicui")
YINPU_DB = Path("/Users/kevin/bistro/data/yinpu.db")
EXPORTS = REPO / "exports"
_TMP_DIRS: list[Path] = []


def _copy_db(path: Path) -> Path:
    """把库（含 -wal / -shm）只读复制到临时目录再打开。

    为什么先复制：WAL 库上用 `file:...?mode=ro` 直接打开在本机实测会报
    `unable to open database file`（SQLite 对 WAL 的只读共享内存有额外要求）；
    复制副本（源侧只读）后以普通连接只做 SELECT ⇒ 对源库**零写入**。
    """
    tmp = Path(tempfile.mkdtemp(prefix="yinpu-fp-"))
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


def _norm(v):
    if isinstance(v, (bytes, bytearray)):
        return f"<bytes:{len(v)}:{hashlib.sha256(bytes(v)).hexdigest()}>"
    return v


def fb_exports_fingerprint() -> dict:
    out = {}
    if not EXPORTS.is_dir():
        return out
    for d in sorted(EXPORTS.iterdir()):
        if d.is_dir() and d.name.startswith("fb_"):
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

    result: dict = {"label": args.label, "yinpu_db": str(YINPU_DB), "exists": YINPU_DB.is_file()}
    if YINPU_DB.is_file():
        conn = _conn_ro(YINPU_DB)
        try:
            result["tables"] = [
                _table_fingerprint(conn, "stamps", ["id"]),
                _table_fingerprint(conn, "jobs", ["job_id"]),
                _table_fingerprint(conn, "job_pages", ["job_id", "page"]),
            ]
        finally:
            conn.close()
    result["exports_fb"] = fb_exports_fingerprint()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    for d in _TMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
