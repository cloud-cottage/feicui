#!/usr/bin/env python
"""导入批 2（Kevin 2026-10-13 追加 2 张）→ `var/seal_ingest.db`。

与批 1（import_uploads.py）同型；本批差异：
- 源图 2 张：`image_91eca8.png`（816×1164）与 `image_827d80.png`（886×1400）；
- 朝代＝**`當代`**（xiai 枚举形，同「戰國」繁体口径）、作者＝佚名、释文留空；
- **每张一个批次**：`batch_id=seal_upload_20261013_13 / _14`（与 source_seal_id 同名）
  ⇒ 原件由 `record_upload` 落 `var/seal_uploads/seal_upload_20261013_13/`、`_14/`
  （Kevin 指定目录形，沿批 1 的 `<batch_id>/` 目录家法）；`seq=13/14` ⇒
  `source_seal_id=local_upload_20261013_13 / _14`；`seal_import_batches` 各 +1 行（共 4）。
- guard：`guard_before_02.json` ＝ 批 1 后状态（seals **3691 行全量**指纹）；写后
  **既有 3691 行零改动**（`WHERE source_seal_id NOT IN (两个新 id)` 复算全等）；
  links / images / batches（除 2 个新 batch 行）同法全等。只 INSERT，绝不 UPDATE 既有行。

跑法（两步）：
  feicui/venv/bin/python ops/seal-uploads/import_uploads_02.py --emit-guard  # ① 产写前指纹（只读库）
  feicui/venv/bin/python ops/seal-uploads/import_uploads_02.py               # ② 导入＋写后断言（幂等：重放＝skipped）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))  # server/ 优先（仓根 app.py 遮蔽陷阱）

from app import seal_uploads, seals  # noqa: E402

DB = REPO / "var" / "seal_ingest.db"
OPS = REPO / "ops" / "seal-uploads"
GUARD1 = json.loads((OPS / "guard_before.json").read_text(encoding="utf-8"))
GUARD_PATH = OPS / "guard_before_02.json"
NEW_IDS = ("local_upload_20261013_13", "local_upload_20261013_14")
NEW_BATCH_IDS = ("seal_upload_20261013_13", "seal_upload_20261013_14")
DYNASTY = "當代"
DYNASTY_SOURCE = "kevin_2026-10-13 指定"
AUTHOR = "佚名"
SOURCE_NOTE = ("Kevin 2026-10-13 追加指令：2 张本地印面图导入（批 2）；朝代統一當代、作者佚名、释文留空；"
               "「书的编号/页/列/行」本批无信息")
SOURCES = [
    {"seq": 13, "batch_id": "seal_upload_20261013_13", "filename": "image_91eca8.png",
     "source_path": "/Users/kevin/Library/Application Support/Hermes/composer-images/image_91eca8.png"},
    {"seq": 14, "batch_id": "seal_upload_20261013_14", "filename": "image_827d80.png",
     "source_path": "/Users/kevin/Library/Application Support/Hermes/composer-images/image_827d80.png"},
]

COLS = [c for c, _ in GUARD1["seal_ingest"]["schemas"]["seals"]]  # 54 列，与批 1 guard 同一口径


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


WHERE_EXISTING = (f"WHERE source_seal_id NOT IN ({', '.join(repr(i) for i in NEW_IDS)})")
COND_BATCH_EXISTING = (f"batch_id NOT IN ({', '.join(repr(b) for b in NEW_BATCH_IDS)})")


def emit_guard() -> int:
    """写前指纹（只读库＋读源图；唯一写入＝本 guard 文件）。"""
    n_seals, h_seals = dump_hash(DB, COLS)
    n_fudan, h_fudan = dump_hash(DB, COLS, "WHERE source_kind='fudan_api'")
    _, h_links = table_dump_hash(DB, "seal_links", "source_seal_id, link_kind, ref_id, source_face, seq")
    _, h_images = table_dump_hash(DB, "seal_images", "seqid, kind")
    n_batches, h_batches = table_dump_hash(DB, "seal_import_batches", "batch_id")
    con = sqlite3.connect(DB)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("seals", "seal_links", "seal_images", "seal_import_batches", "seal_uploads")}
    con.close()
    assert n_seals == 3691 and counts["seals"] == 3691, f"批 2 写前 seals 应为 3691 行：{n_seals}"
    assert n_fudan == 3679 and h_fudan == GUARD1["seal_ingest"]["sha256"]["seals_before"], \
        "批 1 后 fudan 3679 行指纹与 guard_before.json 不符"
    assert counts["seal_uploads"] == 12 and counts["seal_import_batches"] == 2, counts
    for nid in NEW_IDS:
        con = sqlite3.connect(DB)
        assert con.execute("SELECT 1 FROM seals WHERE source_seal_id=?", (nid,)).fetchone() is None, \
            f"新 id 已存在，guard 口径失效：{nid}"
        con.close()

    sources = []
    for s in SOURCES:
        p = Path(s["source_path"])
        data = p.read_bytes()
        sources.append({"seq": s["seq"], "source_filename": s["filename"], "source_path": str(p),
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})

    out = {
        "generated_at": seals._now(),
        "note": "seal-uploads 批 2 写前指纹（＝批 1 导入后的库状态：seals 3691 行全量）；"
                "「既有行」判据＝WHERE source_seal_id NOT IN (两个新 id)",
        "algorithm": GUARD1["algorithm"],
        "seal_ingest": {
            "db_path": str(DB),
            "backup": "/Users/kevin/.hermes/profiles/zang/cache/scratch/seal-uploads-20261013-b2/"
                      "seal_ingest.backup-20261013-b2.db",
            "counts": counts,
            "sha256": {"seals_before": h_seals, "fudan_rows_before": h_fudan,
                       "links_before": h_links, "images_before": h_images, "batches_before": h_batches},
            "schemas": {"seals": GUARD1["seal_ingest"]["schemas"]["seals"]},
        },
        "yinpu": dict(GUARD1["yinpu"], note="沿批 1 guard_before.json 原文（本批红线：一字不写）"),
        "source_images": sources,
        "batch_plan": [{"seq": s["seq"], "batch_id": s["batch_id"],
                        "source_seal_id": f"local_upload_20261013_{s['seq']:02d}",
                        "dynasty": DYNASTY, "dynasty_source": DYNASTY_SOURCE, "author": AUTHOR} for s in SOURCES],
    }
    GUARD_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[guard] guard_before_02.json 已写：seals {n_seals} {h_seals[:12]}… fudan {n_fudan} ✓ "
          f"links/images/batches({n_batches}) ✓；源图 2 张 sha 已录")
    return 0


def main() -> int:
    GUARD = json.loads(GUARD_PATH.read_text(encoding="utf-8"))
    g = GUARD["seal_ingest"]["sha256"]

    # ── 0. 写前指纹（复核 guard_before_02；重放容忍：判据本就排除两个新 id）────────────
    n_pre, h_pre = dump_hash(DB, COLS, WHERE_EXISTING)
    assert n_pre == 3691 and h_pre == g["seals_before"], f"写前既有 3691 行指纹不符：{n_pre} {h_pre[:12]}"
    _, h_links = table_dump_hash(DB, "seal_links", "source_seal_id, link_kind, ref_id, source_face, seq")
    _, h_images = table_dump_hash(DB, "seal_images", "seqid, kind")
    _, h_batches = table_dump_hash(DB, "seal_import_batches", "batch_id", COND_BATCH_EXISTING)
    assert h_links == g["links_before"] and h_images == g["images_before"] and h_batches == g["batches_before"], \
        "写前 links/images/batches 指纹不符"
    print(f"[guard] 写前指纹一致：既有 3691 行 {h_pre[:12]}… ＋ links/images/batches ✓")

    # ── 1. 迁移（幂等 no-op）＋ 开两批 ─────────────────────────────────────────────
    seal_uploads.ensure_schema(DB)
    for s in SOURCES:
        seals.create_batch(DB, s["batch_id"], params={
            "kind": "local_upload", "dynasty": DYNASTY, "dynasty_source": DYNASTY_SOURCE,
            "author": AUTHOR, "transcription": "", "source_note": SOURCE_NOTE,
            "naming": "P?-C?-R?-印面釋文-朝代-作者-O；书的编号未指定 ⇒ 目录「无信息」（可改）；"
                      "本批每张一个批次（batch_id 与 source_seal_id 同名）",
        }, source_total=1)
    print(f"[migrate] ensure_schema + create_batch({NEW_BATCH_IDS[0]}, {NEW_BATCH_IDS[1]}) ✓")

    # ── 2. 2 张导入（幂等；原件由 record_upload 落 var/seal_uploads/<batch_id>/）────
    results = []
    for s in SOURCES:
        p = Path(s["source_path"])
        data = p.read_bytes()
        rec = next(x for x in GUARD["source_images"] if x["seq"] == s["seq"])
        assert hashlib.sha256(data).hexdigest() == rec["sha256"], f"源图漂移：{p}"
        res = seal_uploads.record_upload(
            DB, data=data, filename=s["filename"], batch_id=s["batch_id"], seq=int(s["seq"]),
            dynasty=DYNASTY, dynasty_source=DYNASTY_SOURCE, author_name=AUTHOR,
            transcription="", uploads_root=REPO / "var" / "seal_uploads", source_note=SOURCE_NOTE)
        res["expected_seq"] = s["seq"]
        results.append(res)
        print(f"[import] {s['seq']} {s['filename']} → {res['status']} {res['source_seal_id']} "
              f"dir={Path(res['source_path']).parent.name}")
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    assert len(ok) + len(skipped) == 2, f"导入数不对：{len(ok)}+{len(skipped)}"
    # 原件目录形（Kevin 指定）：var/seal_uploads/seal_upload_20261013_13/、_14/
    for r in results:
        assert Path(r["source_path"]).parent.name == f"seal_upload_20261013_{r['expected_seq']:02d}", \
            f"落盘目录形不符：{r['source_path']}"

    for r in results:
        batch_id = next(s["batch_id"] for s in SOURCES if s["seq"] == r["expected_seq"])
        seals.finish_batch(DB, batch_id,
                           status="DONE", fetched=1, seals_ok=1 if r["status"] == "ok" else 0,
                           failed_count=0, links_ok=0,
                           last_run_kind="local_upload", last_run_fetched=1 if r["status"] == "ok" else 0,
                           last_run_skipped=1 if r["status"] == "skipped" else 0,
                           notes="批 2 单张导入（Kevin 2026-10-13 追加）；O 件与三版成品见 ops/seal-uploads/README.md")

    # ── 3. 2 行逐项断言 ─────────────────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = {r["source_seal_id"]: dict(r) for r in con.execute(
        f"SELECT * FROM seals WHERE source_seal_id IN ({', '.join('?' for _ in NEW_IDS)})", NEW_IDS)}
    up_rows = {r["source_seal_id"]: dict(r) for r in con.execute(
        f"SELECT * FROM seal_uploads WHERE source_seal_id IN ({', '.join('?' for _ in NEW_IDS)})", NEW_IDS)}
    con.close()
    assertions = []
    for r in results:
        sid = r["source_seal_id"]
        row = rows.get(sid)
        up = up_rows.get(sid)
        assert row is not None and up is not None, f"新行缺：{sid}"
        rec = next(x for x in GUARD["source_images"] if x["seq"] == r["expected_seq"])
        assertions.append({
            "seq": r["expected_seq"], "source_seal_id": sid, "batch_id": row["batch_id"],
            "upload_id": r["upload_id"],
            "dynasty": row["dynasty"], "dynasty_source": row["dynasty_source"],
            "author_name": row["author_name"], "seal_wen": row["seal_wen"],
            "audit_status": row["audit_status"], "source_kind": row["source_kind"],
            "upload_sha256": up["sha256"], "upload_source_path": up["source_path"],
            "upload_width": up["width"], "upload_height": up["height"],
            "checks": {
                "dynasty_is_當代": row["dynasty"] == "當代",
                "dynasty_source_ok": row["dynasty_source"] == DYNASTY_SOURCE,
                "author_is_佚名": row["author_name"] == "佚名",
                "seal_wen_empty": row["seal_wen"] == "",
                "audit_status_ok": row["audit_status"] == "UNREVIEWED_PENDING_HUMAN_REVIEW",
                "source_kind_ok": row["source_kind"] == "local_upload",
                "batch_id_is_per_seal": row["batch_id"] == f"seal_upload_20261013_{r['expected_seq']:02d}",
                "sha256_matches_source": up["sha256"] == rec["sha256"],
                "width_height_ok": (up["width"], up["height"]) == (
                    816, 1164) if r["expected_seq"] == 13 else (up["width"], up["height"]) == (886, 1400),
                "original_copied_on_disk": Path(up["source_path"]).is_file()
                    and sha_file(Path(up["source_path"])) == up["sha256"],
            },
        })
    all_ok = all(all(a["checks"].values()) for a in assertions)
    assert all_ok, "2 行逐项断言存在 FAIL"

    # ── 4. 写后指纹（既有 3691 行 before≡after）────────────────────────────────────
    n_after, h_seals_after = dump_hash(DB, COLS, WHERE_EXISTING)
    _, h_links_after = table_dump_hash(DB, "seal_links", "source_seal_id, link_kind, ref_id, source_face, seq")
    _, h_images_after = table_dump_hash(DB, "seal_images", "seqid, kind")
    _, h_batches_after = table_dump_hash(DB, "seal_import_batches", "batch_id", COND_BATCH_EXISTING)
    con = sqlite3.connect(DB)
    counts_after = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("seals", "seal_links", "seal_images", "seal_import_batches", "seal_uploads")}
    con.close()
    assert n_after == 3691 and h_seals_after == g["seals_before"], "既有 3691 行 seals 指纹漂移！"
    assert h_links_after == g["links_before"] and h_images_after == g["images_before"] \
        and h_batches_after == g["batches_before"], "links/images/batches 既有行指纹漂移！"
    print(f"[guard] 写后指纹一致：既有 3691 行 {h_seals_after[:12]}… ＋ links/images/batches ✓")

    out = {
        "batch_ids": list(NEW_BATCH_IDS),
        "generated_at": seals._now(),
        "counts_after": counts_after,
        "expected_counts": {"seals": 3693, "seal_links": 8964, "seal_images": 6765,
                            "seal_import_batches": 4, "seal_uploads": 14},
        "import": {"ok": len(ok), "skipped_replay": len(skipped), "failed": 0},
        "rows": assertions,
        "guards": {
            "seals_existing_before": g["seals_before"], "seals_existing_after": h_seals_after,
            "links_before": g["links_before"], "links_after": h_links_after,
            "images_before": g["images_before"], "images_after": h_images_after,
            "batches_before": g["batches_before"], "batches_after": h_batches_after,
        },
        "all_checks_pass": bool(all_ok and counts_after["seals"] == 3693),
    }
    (OPS / "guard_after_import_02.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (OPS / "batch_spec_02.json").write_text(json.dumps({
        "spec_id": "seal_upload_20261013_13_14",
        "batch_ids": list(NEW_BATCH_IDS),
        "dynasty": DYNASTY, "author": AUTHOR,
        "dir_key": "无信息",
        "source_note": SOURCE_NOTE,
        "items": [{"seq": a["seq"], "batch_id": a["batch_id"], "source_seal_id": a["source_seal_id"],
                   "upload_id": a["upload_id"],
                   "source_filename": Path(a["upload_source_path"]).name,
                   "source_original": next(s["source_path"] for s in SOURCES if s["seq"] == a["seq"]),
                   "source_path": a["upload_source_path"], "sha256": a["upload_sha256"],
                   "width": a["upload_width"], "height": a["upload_height"]} for a in assertions],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] guard_after_import_02.json ＋ batch_spec_02.json 已写；all_checks_pass =",
          out["all_checks_pass"])
    return 0 if out["all_checks_pass"] else 1


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description="seal-uploads 批 2 导入（--emit-guard 先产写前指纹）")
    _ap.add_argument("--emit-guard", action="store_true", help="只产 guard_before_02.json（只读库），不导入")
    _args = _ap.parse_args()
    if _args.emit_guard:
        raise SystemExit(emit_guard())
    raise SystemExit(main())
