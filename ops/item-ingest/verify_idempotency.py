#!/usr/bin/env python3
"""幂等重跑证据（IT-8）：同批次重跑 ⇒ 行数与**内容指纹不变**。

做法：对同一 batch 连续跑两次 `run_sync`（resume=true）——
  第 1 次为常态重放（全部命中 resume 跳过，无网络取数），
  断言两次之间 `content_fingerprint` 与 items/creators 行数**恒定**。

用法：python3 verify_idempotency.py --batch item_20261010_01 [--out x.json] [--delay 0.3]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))

from app import items  # noqa: E402
from app.config import get_settings  # noqa: E402


def fp(db) -> str:
    conn = items._connect(db)
    try:
        return items.content_fingerprint(conn)
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="item_20261010_01")
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    st = get_settings()
    before_fp = fp(st.items_db_path)
    before_counts = items.db_counts(st.items_db_path)

    s1 = items.run_sync(db_path=st.items_db_path, export_root=st.items_export_root, base=st.items_source_base,
                        person_db_path=st.person_db_path, batch_id=args.batch, resume=True, delay=args.delay)
    mid_fp = fp(st.items_db_path)
    s2 = items.run_sync(db_path=st.items_db_path, export_root=st.items_export_root, base=st.items_source_base,
                        person_db_path=st.person_db_path, batch_id=args.batch, resume=True, delay=args.delay)
    after_fp = fp(st.items_db_path)
    after_counts = items.db_counts(st.items_db_path)

    out = {
        "batch_id": args.batch,
        "before": {"fingerprint": before_fp, "counts": before_counts},
        "run1": {"run_kind": s1["run_kind"], "fetched_requests": s1["fetched_requests"],
                 "skipped_resume": s1["skipped_resume"], "items_ok": s1["items_ok"], "creators_ok": s1["creators_ok"]},
        "run2": {"run_kind": s2["run_kind"], "fetched_requests": s2["fetched_requests"],
                 "skipped_resume": s2["skipped_resume"], "items_ok": s2["items_ok"], "creators_ok": s2["creators_ok"]},
        "after": {"fingerprint": after_fp, "counts": after_counts},
        "checks": {
            "fingerprint_unchanged_across_runs": before_fp == mid_fp == after_fp,
            "counts_unchanged_across_runs": before_counts == after_counts,
            "run1_is_idempotent_replay": s1["run_kind"] == "idempotent_replay" and s1["fetched_requests"] == 0,
            "run2_is_idempotent_replay": s2["run_kind"] == "idempotent_replay" and s2["fetched_requests"] == 0,
        },
    }
    out["pass"] = all(out["checks"].values())
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
