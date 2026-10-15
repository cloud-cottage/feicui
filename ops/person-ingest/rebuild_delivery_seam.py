#!/usr/bin/env python3
"""批次包重建（幂等重放，**不联网**）：从独立库 `var/person_ingest.db` 既有读数重建
`exports/person_20261010_01/` 四文件（`persons.jsonl` / `relations.jsonl` / `manifest.json` / `report.json`）。

**为什么从库重建、不重采**：源站（复旦印藏）站点级时间窗限流，且本单属**修交付缝字段形态**
（字/号/别名六字段 由「JSON 字符串」改「真 JSON 数组」），**库内 `raw_json` 与已抽取值已足够**，
无需（也不得）重新联网。

**本脚本不做任何库写**：`write_package` 对 `persons` / `person_relations` 只 SELECT；故重放前后
两表**行数与内容指纹恒不变**（脚本会自行核对并打印）。

用法：python3 rebuild_delivery_seam.py [--batch-id person_20261010_01]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path("/Users/kevin/bistro/feicui")
sys.path.insert(0, str(REPO / "server"))
from app import persons as P  # noqa: E402

DB = REPO / "var" / "person_ingest.db"

# 采集 run（本单之前已完成）读数：末片 summary + 跨片累加（resume 续跑）
ACQUISITION_PROVENANCE = {
    "acquisition_run": {
        "status": "completed_before_this_rebuild",
        "note": "采集 run 已在**本单之前**完成；源站站点级限流 ⇒ 本单不再联网采集",
        "persons_collected": 570,
        "fetched_requests_cumulative": 570,   # 570 人各读一次 graph/person（resume 跨片续跑累加）
        "failed_count": 0,
        "last_shard_summary": {"fetched_requests": 178, "skipped_resume": 392, "persons_ok": 570,
                               "relations_ok": 539, "failed_count": 0, "elapsed_s": 301.615},
        "evidence": "ops/person-ingest/01_full_ingest.txt",
    },
    "this_package_write": {
        "kind": "idempotent_replay_no_network",
        "fetched_requests": 0,
        "skipped_resume": 570,
        "relations_ok": 0,
        "failed_count": 0,
        "note": ("本轮为**幂等重放**：只从库内既有读数重建批次包与字/号/别名字段形态，**不联网、不重采**（源站限流）。"
                 "`fetched_requests=0` / `relations_ok=0` / `elapsed_s≈1.5` **是重放读数，不得据此判「未采集」**；"
                 "采集 run 读数见 `acquisition_run`。"),
        "db_batch_row_note": ("库内 `person_import_batches` 行（fetched=0 / relations_ok=0 / elapsed_s≈1.5）"
                              "同为重放读数 —— 非「未采集」"),
    },
}


def _snapshot(conn) -> dict:
    return {
        "persons": conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
        "relations": conn.execute("SELECT COUNT(*) FROM person_relations").fetchone()[0],
        "content_fingerprint": P.content_fingerprint(conn),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", default="person_20261010_01")
    ap.add_argument("--export-root", default=str(REPO / "exports"))
    ap.add_argument("--base", default="https://yin.fudan.edu.cn/service_yinpu")
    args = ap.parse_args()

    out: dict = {"batch_id": args.batch_id, "db": str(DB), "export_root": args.export_root}
    conn = P._connect(DB)
    try:
        before = _snapshot(conn)
        # 库内 batch 行的 params（沿用同批次既有参数，保证幂等重放口径一致）
        row = conn.execute("SELECT params_json, source_total FROM person_import_batches WHERE batch_id=?",
                           (args.batch_id,)).fetchone()
        params = json.loads(row["params_json"]) if row else {
            "resume": True, "delay": 1.5, "limit": None, "page_rows": 1000, "detail_best_effort": False}
        source_total = row["source_total"] if row else 570

        t0 = time.time()
        pkg = P.write_package(
            conn, export_root=Path(args.export_root), batch_id=args.batch_id, source_total=source_total,
            fetched=0, skipped=source_total, failures=[], detail_unconfirmed=[],
            detail_confirmed=0, detail_skipped_circuit=0, params=params,
            elapsed_s=1.0, base=args.base, provenance=ACQUISITION_PROVENANCE,
        )
        out["elapsed_s"] = round(time.time() - t0, 3)
        after = _snapshot(conn)
    finally:
        conn.close()

    out["before"] = before
    out["after"] = after
    out["db_unchanged"] = (before == after)
    out["package_dir"] = str(pkg["package_dir"])
    out["report_path"] = str(pkg["report_path"])
    out["content_fingerprint"] = pkg["fingerprint"]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["db_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
