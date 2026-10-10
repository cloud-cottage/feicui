#!/usr/bin/env python3
"""印谱采集全量跑（**分片续跑**；批 1）。逐片调 `app.items.run_sync`（每片最多新增 N 取数，可断点续跑），
输出逐片回执到 stdout（另 --log 落盘）。用于避开单次长跑超时，并让「分片」真实发生。

用法：
  cd .../feicui/server && ./.venv/bin/python ../ops/item-ingest/run_full.py --batch item_20261010_01 --shard 200 --delay 0.4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))

from app import items  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="item_20261010_01")
    ap.add_argument("--shard", type=int, default=200)
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--max-rounds", type=int, default=80)
    ap.add_argument("--log", default=str(REPO / "ops" / "item-ingest" / "01_full_ingest.log"))
    args = ap.parse_args()

    st = get_settings()
    logf = open(args.log, "a", encoding="utf-8")

    def emit(obj):
        line = json.dumps(obj, ensure_ascii=False)
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    emit({"event": "start", "batch": args.batch, "shard": args.shard, "delay": args.delay,
          "db": str(st.items_db_path), "export_root": str(st.items_export_root),
          "person_db": str(st.person_db_path), "at": items._now()})

    rounds = 0
    while True:
        rounds += 1
        t0 = time.time()
        s = items.run_sync(
            db_path=st.items_db_path, export_root=st.items_export_root, base=st.items_source_base,
            person_db_path=st.person_db_path, batch_id=args.batch, resume=True,
            delay=args.delay, limit=args.shard, timeout=st.items_fetch_timeout_s,
        )
        emit({"event": "shard", "round": rounds, "run_kind": s["run_kind"],
              "items_ok": s["items_ok"], "creators_ok": s["creators_ok"],
              "remaining": s["remaining"], "fetched_requests": s["fetched_requests"],
              "failed_count": s["failed_count"], "elapsed_s": round(time.time() - t0, 1),
              "content_fingerprint": s["content_fingerprint"]})
        if s["remaining"] <= 0:
            emit({"event": "done", "rounds": rounds, "items_ok": s["items_ok"],
                  "creators_ok": s["creators_ok"], "at": items._now()})
            break
        if s["fetched_requests"] == 0:
            emit({"event": "stalled_no_fetch", "remaining": s["remaining"],
                  "failures": s["failures"][:10]})
            break
        if rounds >= args.max_rounds:
            emit({"event": "max_rounds", "rounds": rounds, "remaining": s["remaining"]})
            break
    logf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
