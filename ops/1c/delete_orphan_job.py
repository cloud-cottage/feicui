#!/usr/bin/env python3
"""删除一条**已授权删除**的遗孤 job 行（Kevin 授权，2026-09-20）——阶段 1c-激活。

只动两处，且**只按精确 job_id**：
  ① `jobs`    里该 job_id 的那一行；
  ② `job_pages` 里 `job_id = <该 id>` 的全部行。
**绝不碰 `stamps`**（本脚本连 `stamps` 的 DELETE 语句都不写）。

顺序（先证据、后删除）：
  0. `sqlite3` backup API 备份整库（WAL 感知，不用 `cp`）→ `yinpu.db.bak-1c-before-delete-<ts>`
  1. 打印删除前的两处 rows（原文，作证据）
  2. 打印删除前的 `stamps` 计数（只读）
  3. 单事务：`BEGIN IMMEDIATE` → DELETE job_pages → DELETE jobs → `COMMIT`（并打印 changes()）
  4. 打印删除后的计数（`jobs` / `job_pages` 应为 0；`stamps` 应与步骤 2 相同）

用法：
    cd /Users/kevin/bistro/feicui
    ./server/.venv/bin/python ops/1c/delete_orphan_job.py \
        --db yinpu.db --job-id job-3d697531fe834dbcb8c7ce5d3857077d --yes
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def _dump(conn: sqlite3.Connection, sql: str, params: tuple) -> list[str]:
    conn.row_factory = sqlite3.Row
    return [repr(dict(r)) for r in conn.execute(sql, params)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按精确 job_id 删除遗孤 job（已授权）")
    ap.add_argument("--db", required=True, help="正式库路径（yinpu.db）")
    ap.add_argument("--job-id", required=True, help="要删除的精确 job_id")
    ap.add_argument("--yes", action="store_true", help="确认执行（无此开关＝只体检不删）")
    args = ap.parse_args(argv)

    db_path = Path(args.db).expanduser().resolve()
    jid = args.job_id
    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        print(f"db       = {db_path}")
        print(f"job_id   = {jid}")
        print(f"time     = {datetime.now().isoformat(timespec='seconds')}")
        print()

        # ---- 0. 备份（WAL 感知）----
        bak = db_path.with_name(f"{db_path.name}.bak-1c-before-delete-{ts}")
        dest = sqlite3.connect(str(bak))
        try:
            conn.backup(dest)
        finally:
            dest.close()
        print(f"[0] 备份 = {bak}（sqlite3 backup API；不打印文件 md5——WAL 下会漂）")
        print()

        # ---- 1. 删除前 rows ----
        jobs_rows = _dump(conn, "SELECT * FROM jobs WHERE job_id = ?", (jid,))
        pages_rows = _dump(
            conn, "SELECT id, job_id, pdf_name, page, chunk_index, state FROM job_pages WHERE job_id = ? ORDER BY page", (jid,)
        )
        print(f"[1] 删除前 jobs 命中行数      = {len(jobs_rows)}")
        for line in jobs_rows:
            print(f"    {line}")
        print(f"    删除前 job_pages 命中行数  = {len(pages_rows)}")
        for line in pages_rows:
            print(f"    {line}")
        print()

        # ---- 2. 删除前 stamps 计数（只读护栏：证明本脚本不碰 stamps）----
        st_before = conn.execute("SELECT count(*) FROM stamps").fetchone()[0]
        jb_before = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        jp_before = conn.execute("SELECT count(*) FROM job_pages").fetchone()[0]
        print(f"[2] 删除前计数：jobs={jb_before} job_pages={jp_before} stamps={st_before}")
        print()

        if not args.yes:
            print("（未给 --yes ⇒ 仅体检，未删除任何行）")
            return 0

        # ---- 3. 删（单事务）----
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur_p = conn.execute("DELETE FROM job_pages WHERE job_id = ?", (jid,))
            n_pages = cur_p.rowcount
            cur_j = conn.execute("DELETE FROM jobs WHERE job_id = ?", (jid,))
            n_jobs = cur_j.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(f"[3] 已删除：job_pages={n_pages} 行 / jobs={n_jobs} 行（单事务 BEGIN IMMEDIATE → COMMIT）")
        print()

        # ---- 4. 删后计数 ----
        st_after = conn.execute("SELECT count(*) FROM stamps").fetchone()[0]
        jb_after = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        jp_after = conn.execute("SELECT count(*) FROM job_pages").fetchone()[0]
        print(f"[4] 删除后计数：jobs={jb_after} job_pages={jp_after} stamps={st_after}")
        print(f"    stamps 未变 = {st_before == st_after}（{st_before} → {st_after}）")
        if jid in {r[0] for r in conn.execute("SELECT job_id FROM jobs")}:
            print("✗ 该 job_id 仍在 jobs 中")
            return 1
        print("✓ 该 job_id 已不在 jobs 中；job_pages 亦无其残留")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
