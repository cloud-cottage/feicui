#!/usr/bin/env python
"""导入 12 张本地上传印面 → `var/seal_ingest.db`（seal-uploads 批 1，Kevin 2026-10-13）。

只加法：先核 guard_before 指纹，再 `ensure_schema`（seals 加法四列 ＋ seal_uploads 表）→
`record_upload` ×12（dynasty=戰國、author=佚名、seal_wen=''、audit_status=UNREVIEWED_PENDING_HUMAN_REVIEW、
source_kind='local_upload'）→ 批次行 → guard_after_import.json（既有行指纹 before≡after ＋ 12 行逐项断言）。

跑法：`feicui/venv/bin/python ops/seal-uploads/import_uploads.py`（幂等可重跑；重放＝skipped）。
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))  # server/ 优先（仓根 app.py 遮蔽陷阱）

from app import seal_uploads, seals  # noqa: E402

DB = REPO / "var" / "seal_ingest.db"
OPS = REPO / "ops" / "seal-uploads"
GUARD_BEFORE = json.loads((OPS / "guard_before.json").read_text(encoding="utf-8"))
BATCH_ID = "seal_upload_20261013_01"
DYNASTY = "戰國"
DYNASTY_SOURCE = "kevin_2026-10-13 指定"
AUTHOR = "佚名"
SOURCE_NOTE = ("Kevin 2026-10-13 指令：12 张本地印面图导入；朝代统一戰國、作者佚名、释文留空；"
               "「书的编号/页/列/行」本批无信息")

EXPECTED_SOURCES = [s["source_filename"] for s in GUARD_BEFORE["source_images"]]


def dump_hash(db: Path, cols: list[str], where: str = "") -> tuple[int, str]:
    con = sqlite3.connect(db)
    h = hashlib.sha256()
    n = 0
    for row in con.execute(f"SELECT {', '.join(cols)} FROM seals {where} ORDER BY source_seal_id"):
        h.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
        n += 1
    con.close()
    return n, h.hexdigest()


def table_dump_hash(db: Path, table: str, order: str, where: str = "1=1") -> tuple[int, str]:
    con = sqlite3.connect(db)
    h = hashlib.sha256()
    n = 0
    for row in con.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY {order}"):
        h.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
        n += 1
    con.close()
    return n, h.hexdigest()


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    cols_before = [c for c, _ in GUARD_BEFORE["seal_ingest"]["schemas"]["seals"]]
    sha_seals_before = GUARD_BEFORE["seal_ingest"]["sha256"]["seals_before"]
    sha_links_before = GUARD_BEFORE["seal_ingest"]["sha256"]["links_before"]
    sha_images_before = GUARD_BEFORE["seal_ingest"]["sha256"]["images_before"]
    sha_batches_before = GUARD_BEFORE["seal_ingest"]["sha256"]["batches_before"]

    # ── 0. 写前指纹（guard_before 复核）───────────────────────────────────────────
    n_seals, h_seals = dump_hash(DB, cols_before)
    assert n_seals == 3679 and h_seals == sha_seals_before, f"写前 seals 指纹不符：{n_seals} {h_seals}"
    _, h_links = table_dump_hash(DB, "seal_links", "source_seal_id, link_kind, ref_id, source_face, seq")
    _, h_images = table_dump_hash(DB, "seal_images", "seqid, kind")
    _, h_batches = table_dump_hash(DB, "seal_import_batches", "batch_id", where=f"batch_id != '{BATCH_ID}'")
    assert h_links == sha_links_before, "写前 seal_links 指纹不符"
    assert h_images == sha_images_before, "写前 seal_images 指纹不符"
    assert h_batches == sha_batches_before, "写前 seal_import_batches 指纹不符"
    print(f"[guard] 写前指纹一致：seals 3679 {h_seals[:12]}… links/images/batches ✓")

    # ── 1. 迁移（加法）＋ 开批 ────────────────────────────────────────────────────
    seal_uploads.ensure_schema(DB)
    seals.create_batch(DB, BATCH_ID, params={
        "kind": "local_upload", "dynasty": DYNASTY, "dynasty_source": DYNASTY_SOURCE,
        "author": AUTHOR, "transcription": "", "source_note": SOURCE_NOTE,
        "naming": "P?-C?-R?-印面釋文-朝代-作者-O；书的编号未指定 ⇒ 目录「无信息」（可改）",
    }, source_total=12)
    print(f"[migrate] ensure_schema + create_batch({BATCH_ID}) ✓")

    # ── 2. 12 张导入（幂等）───────────────────────────────────────────────────────
    results = []
    for item in GUARD_BEFORE["source_images"]:
        p = Path(item["source_path"])
        assert p.name in EXPECTED_SOURCES
        data = p.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], f"源图漂移：{p}"
        res = seal_uploads.record_upload(
            DB, data=data, filename=p.name, batch_id=BATCH_ID, seq=int(item["seq"]),
            dynasty=DYNASTY, dynasty_source=DYNASTY_SOURCE, author_name=AUTHOR,
            transcription="", uploads_root=REPO / "var" / "seal_uploads", source_note=SOURCE_NOTE)
        res["expected_seq"] = item["seq"]
        results.append(res)
        print(f"[import] {item['seq']} {p.name} → {res['status']} {res['source_seal_id']}")
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    assert len(ok) + len(skipped) == 12, f"导入数不对：{len(ok)}+{len(skipped)}"

    seals.finish_batch(DB, BATCH_ID, status="DONE", fetched=12, seals_ok=len(ok),
                       failed_count=0, links_ok=0,
                       last_run_kind="local_upload", last_run_fetched=len(ok), last_run_skipped=len(skipped),
                       notes="12 张本地上传印面导入（Kevin 2026-10-13）；O 件与 1200px 成品见 ops/seal-uploads/README.md")

    # ── 3. 12 行逐项断言 ──────────────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = {r["source_seal_id"]: dict(r) for r in con.execute(
        "SELECT * FROM seals WHERE batch_id=? AND source_kind='local_upload'", (BATCH_ID,))}
    up_rows = {r["seq"]: dict(r) for r in con.execute(
        "SELECT * FROM seal_uploads WHERE batch_id=?", (BATCH_ID,))}
    con.close()
    assertions = []
    for r in results:
        sid = r["source_seal_id"]
        row = rows.get(sid)
        assert row is not None, f"seals 缺行：{sid}"
        up = up_rows.get(r["seq"])
        assert up is not None and up["source_seal_id"] == sid, f"seal_uploads 台账缺行/错位：seq={r['seq']}"
        assertions.append({
            "seq": r["seq"], "source_seal_id": sid, "upload_id": r["upload_id"],
            "dynasty": row["dynasty"], "dynasty_source": row["dynasty_source"],
            "author_name": row["author_name"], "seal_wen": row["seal_wen"],
            "audit_status": row["audit_status"], "source_kind": row["source_kind"],
            "batch_id": row["batch_id"],
            "upload_sha256": up["sha256"], "upload_source_path": up["source_path"],
            "upload_width": up["width"], "upload_height": up["height"],
            "checks": {
                "dynasty_is_戰國": row["dynasty"] == "戰國",
                "dynasty_source_ok": row["dynasty_source"] == DYNASTY_SOURCE,
                "author_is_佚名": row["author_name"] == "佚名",
                "seal_wen_empty": row["seal_wen"] == "",
                "audit_status_ok": row["audit_status"] == "UNREVIEWED_PENDING_HUMAN_REVIEW",
                "source_kind_ok": row["source_kind"] == "local_upload",
                "batch_id_ok": row["batch_id"] == BATCH_ID,
                "sha256_matches_source": up["sha256"] == next(
                    s["sha256"] for s in GUARD_BEFORE["source_images"] if s["seq"] == r["expected_seq"]),
                "original_copied_on_disk": Path(up["source_path"]).is_file()
                    and sha_file(Path(up["source_path"])) == up["sha256"],
            },
        })
    all_ok = all(all(a["checks"].values()) for a in assertions)
    assert all_ok, "12 行逐项断言存在 FAIL"

    # ── 4. 写后指纹（既有行 before≡after）────────────────────────────────────────
    n_after, h_seals_after = dump_hash(DB, cols_before, where="WHERE source_kind='fudan_api'")
    _, h_links_after = table_dump_hash(DB, "seal_links", "source_seal_id, link_kind, ref_id, source_face, seq")
    _, h_images_after = table_dump_hash(DB, "seal_images", "seqid, kind")
    _, h_batches_after = table_dump_hash(DB, "seal_import_batches", "batch_id", where=f"batch_id != '{BATCH_ID}'")
    con = sqlite3.connect(DB)
    counts_after = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("seals", "seal_links", "seal_images", "seal_import_batches", "seal_uploads")}
    con.close()
    assert n_after == 3679 and h_seals_after == sha_seals_before, "既有 3679 行 seals 指纹漂移！"
    assert h_links_after == sha_links_before and h_images_after == sha_images_before \
        and h_batches_after == sha_batches_before, "links/images/batches 既有行指纹漂移！"
    print(f"[guard] 写后指纹一致：既有 3679 行 {h_seals_after[:12]}… ＋ links/images/batches ✓")

    out = {
        "batch_id": BATCH_ID,
        "generated_at": seals._now(),
        "migration": {"seals_added_columns": [c for c, _ in seals.SEALS_EXTRA_COLUMNS],
                      "new_table": "seal_uploads",
                      "existing_rows_source_kind_default": "fudan_api"},
        "counts_after": counts_after,
        "expected_counts": {"seals": 3691, "seal_links": 8964, "seal_images": 6765,
                            "seal_import_batches": 2, "seal_uploads": 12},
        "import": {"ok": len(ok), "skipped_replay": len(skipped), "failed": 0},
        "rows": assertions,
        "guards": {
            "seals_existing_before": sha_seals_before, "seals_existing_after": h_seals_after,
            "links_before": sha_links_before, "links_after": h_links_after,
            "images_before": sha_images_before, "images_after": h_images_after,
            "batches_before": sha_batches_before, "batches_after": h_batches_after,
        },
        "all_checks_pass": bool(all_ok and counts_after["seals"] == 3691),
    }
    (OPS / "guard_after_import.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (OPS / "batch_spec.json").write_text(json.dumps({
        "batch_id": BATCH_ID, "dynasty": DYNASTY, "author": AUTHOR,
        "dir_key": "无信息",
        "items": [{"seq": a["seq"], "source_seal_id": a["source_seal_id"], "upload_id": a["upload_id"],
                   "source_path": a["upload_source_path"], "sha256": a["upload_sha256"],
                   "width": a["upload_width"], "height": a["upload_height"]} for a in assertions],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] guard_after_import.json ＋ batch_spec.json 已写；all_checks_pass =", out["all_checks_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
