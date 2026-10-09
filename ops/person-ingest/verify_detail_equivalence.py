#!/usr/bin/env python3
"""detail ≡ list 等价性抽样（依据②）：证明「detail 主数据 ≡ 列表行（除 seqid / createdTime）」。

做法：从 `person/list` 取全 570，随机抽 15 人，逐个 `person/detail/<grbsm>` 取详情，
逐字段比对两条记录；输出差异字段清单。这是「detail 可降级为 best-effort」的实证依据。

用法：`server/.venv/bin/python ops/person-ingest/verify_detail_equivalence.py [--n 15] [--seed 20261010]`
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))
from app import persons as P  # noqa: E402

BASE = "https://yin.fudan.edu.cn/service_yinpu"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--seed", type=int, default=20261010)
    args = ap.parse_args()

    rows, total = P.fetch_list(BASE)
    rng = random.Random(args.seed)
    sample = rng.sample(rows, min(args.n, len(rows)))

    results = []
    all_same_except = True
    for r in sample:
        grbsm = str(r.get("personGrbsm"))
        entry = {"personGrbsm": grbsm, "name": r.get("personGrsxmc")}
        try:
            det = P.fetch_detail(BASE, grbsm, retries=3)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
            results.append(entry)
            continue
        keys = sorted(set(r) | set(det))
        diffs = [k for k in keys if r.get(k) != det.get(k)]
        entry["differing_fields"] = diffs
        entry["same_except_seqid_createdtime"] = set(diffs) <= {"seqid", "createdTime"}
        if not entry["same_except_seqid_createdtime"]:
            all_same_except = False
            entry["detail"] = {k: {"list": r.get(k), "detail": det.get(k)} for k in diffs}
        results.append(entry)
        time.sleep(0.6)

    out = {
        "claim": "person/detail 主数据与 person/list 行除 seqid / createdTime 外逐字节等价",
        "source_total": total,
        "sample_size": len(sample),
        "seed": args.seed,
        "all_same_except_seqid_createdtime": all_same_except,
        "results": results,
    }
    PATH = REPO / "ops" / "person-ingest" / "07_detail_equivalence.json"
    PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all_same_except else 1


if __name__ == "__main__":
    raise SystemExit(main())
