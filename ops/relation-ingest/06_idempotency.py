#!/usr/bin/env python3
"""⑤ 重建幂等 + 门禁对照 —— 触发就绪包重建两次，判「仅时间戳变、`relations.jsonl` 字节不变」；
并比对 `03_guard_before.json` / `04_guard_after.json`（四库指纹 + 三线三包未变）。

输出 `06_idempotency.json`。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
SERVER = REPO / "server"
PKG = REPO / "exports" / "relation_import_relation_20261010_01"
BATCH = "relation_20261010_01"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def snapshot() -> dict:
    m = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    r = json.loads((PKG / "report.json").read_text(encoding="utf-8"))
    return {"jsonl_sha256": sha256_file(PKG / "relations.jsonl"),
            "jsonl_bytes": (PKG / "relations.jsonl").stat().st_size,
            "manifest_created_at": m.get("created_at"),
            "report_generated_at": r.get("generated_at")}


def rebuild() -> dict:
    cp = subprocess.run([str(SERVER / ".venv" / "bin" / "python"), "-m", "app.relations",
                         "package", "--batch-id", BATCH],
                        cwd=str(SERVER), capture_output=True, text=True)
    return {"rc": cp.returncode, "stderr_tail": cp.stderr[-300:] if cp.returncode else ""}


def main() -> int:
    run0 = snapshot()                       # 现状（CLI 首次出包后）
    steps = [rebuild(), rebuild()]
    run1 = snapshot()
    run2 = snapshot() if not steps[-1]["rc"] else None

    legacy_guard = json.loads((REPO / "ops" / "relation-ingest" / "03_guard_before.json").read_text())
    after_guard = json.loads((REPO / "ops" / "relation-ingest" / "04_guard_after.json").read_text())

    # 指纹对照（before vs after）
    dbs_ok, db_diff = True, {}
    for k in legacy_guard["dbs"]:
        b, a = legacy_guard["dbs"][k], after_guard["dbs"][k]
        same = (b.get("tables") == a.get("tables") and b.get("n_tables") == a.get("n_tables"))
        db_diff[k] = {"same": same}
        dbs_ok = dbs_ok and same
    pkgs_ok, pkg_diff = True, {}
    for k in set(legacy_guard["export_packages"]) | set(after_guard["export_packages"]):
        b = legacy_guard["export_packages"].get(k, {}).get("sha256_names_sizes")
        a = after_guard["export_packages"].get(k, {}).get("sha256_names_sizes")
        same = (b == a)
        pkg_diff[k] = {"before": b, "after": a, "same": same}
        pkgs_ok = pkgs_ok and same

    jsonl_stable = (run0["jsonl_sha256"] == run1["jsonl_sha256"])
    out = {
        "batch_id": BATCH,
        "rebuild_rcs": [s["rc"] for s in steps],
        "jsonl_sha256_run0": run0["jsonl_sha256"], "jsonl_sha256_run1": run1["jsonl_sha256"],
        "jsonl_bytes": run1["jsonl_bytes"],
        "jsonl_byte_stable": jsonl_stable,
        "manifest_created_at_run0": run0["manifest_created_at"],
        "manifest_created_at_run1": run1["manifest_created_at"],
        "report_generated_at_run0": run0["report_generated_at"],
        "report_generated_at_run1": run1["report_generated_at"],
        "timestamps_may_change": True,
        "verdict_jsonl_only_timestamps_change": jsonl_stable,
        "guard": {"dbs_unchanged": dbs_ok, "db_detail": db_diff,
                  "packages_unchanged": pkgs_ok, "package_detail": pkg_diff},
    }
    (REPO / "ops" / "relation-ingest" / "06_idempotency.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "rebuild_rcs": out["rebuild_rcs"],
        "jsonl_byte_stable": jsonl_stable,
        "manifest_created_at": f'{run0["manifest_created_at"]} -> {run1["manifest_created_at"]}',
        "report_generated_at": f'{run0["report_generated_at"]} -> {run1["report_generated_at"]}',
        "dbs_unchanged": dbs_ok, "packages_unchanged": pkgs_ok,
        "db_detail": {k: v["same"] for k, v in db_diff.items()},
        "pkg_detail": {k: v["same"] for k, v in pkg_diff.items()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
