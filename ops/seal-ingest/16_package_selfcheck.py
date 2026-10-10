#!/usr/bin/env python3
"""就绪包自检（第二段 · ③）：双向一一对应 / sha256 重算 / 逐行 TIFF 魔数 /
尺寸档位 / 台账 width-height / manifest.image_policy / report 三态与前缀聚合。

只读：不改包、不改库。输出 JSON 至 17_package_selfcheck.json 并打印关键读数。
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
PKG = REPO / "exports" / "seal_import_seal_20261010_01"
DB = REPO / "var" / "seal_ingest.db"
XIAI_STORED_MAX = 4 * 1024 * 1024
XIAI_INPUT_MAX = 1 * 1024 * 1024
MAGIC = (b"II*\x00", b"MM\x00*")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    manifest_lines = (PKG / "images_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in manifest_lines if x.strip()]
    row_shas = [r["sha256"] for r in rows]
    tree = [p for p in (PKG / "images").rglob("*.tiff") if p.is_file()]
    tree_by_stem = {p.stem: p for p in tree}

    # ① 双向一一对应
    ss_rows = set(row_shas)
    ss_tree = set(tree_by_stem)
    orphan = sorted(ss_tree - ss_rows)          # 树上有、清单无
    rows_wo = sorted(ss_rows - ss_tree)         # 清单有、树上无
    dup_rows = len(row_shas) - len(ss_rows)
    check1 = {
        "manifest_lines": len(manifest_lines),
        "manifest_rows": len(rows),
        "row_unique_sha": len(ss_rows),
        "duplicate_sha_lines": dup_rows,
        "tree_file_count": len(tree),
        "orphan_files(count)": len(orphan),
        "rows_without_file(count)": len(rows_wo),
        "one_to_one": (len(rows) == len(tree) == len(ss_rows) == 6347 and not orphan and not rows_wo),
    }

    # ② 随机 20 行 sha256 重算自洽
    rng = random.Random(20261010)
    sample = rng.sample(rows, 20)
    recalc = []
    for r in sample:
        p = PKG / "images" / r["sha256"][:2] / f"{r['sha256']}.tiff"
        real = sha256_file(p) if p.is_file() else None
        recalc.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": r["sha256"],
                       "recomputed": real, "match": real == r["sha256"]})
    check2 = {"n": len(recalc), "all_match": all(x["match"] for x in recalc), "samples": recalc}

    # ③ 逐行 TIFF 魔数
    magic_fail = []
    for r in rows:
        p = PKG / "images" / r["sha256"][:2] / f"{r['sha256']}.tiff"
        try:
            with p.open("rb") as fh:
                head = fh.read(4)
        except OSError:
            head = b""
        if head not in MAGIC:
            magic_fail.append({"seqid": r["seqid"], "kind": r["kind"], "head": head.hex()})
    check3 = {"checked": len(rows), "magic_fail_count": len(magic_fail), "magic_fail": magic_fail[:50],
              "all_ok": len(magic_fail) == 0}

    # ④ 尺寸档位
    over_stored, over_input = [], []
    sizes = []
    for r in rows:
        p = PKG / "images" / r["sha256"][:2] / f"{r['sha256']}.tiff"
        n = p.stat().st_size
        sizes.append(n)
        if n > XIAI_STORED_MAX:
            over_stored.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": r["sha256"], "bytes": n})
        if n > XIAI_INPUT_MAX:
            over_input.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": r["sha256"], "bytes": n})
    check4 = {
        "stored_max": XIAI_STORED_MAX, "input_max": XIAI_INPUT_MAX,
        "over_stored_count": len(over_stored), "over_input_count": len(over_input),
        "min_bytes": min(sizes), "max_bytes": max(sizes),
        "over_stored": over_stored, "over_input_sample": over_input[:20],
    }

    # ⑤ 台账/清单每行有 width/height
    no_wh = [r["seqid"] for r in rows if r.get("width") is None or r.get("height") is None]
    # 同时校 DB 台账 ok 行
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    db_nowh = [dict(x) for x in conn.execute(
        "SELECT seqid,kind FROM seal_images WHERE status='ok' AND (width IS NULL OR height IS NULL)")]
    db_ok = conn.execute("SELECT COUNT(*) FROM seal_images WHERE status='ok'").fetchone()[0]
    conn.close()
    check5 = {"manifest_rows_missing_wh": len(no_wh), "db_ok_rows": db_ok,
              "db_ok_missing_wh": len(db_nowh), "all_have_wh": (not no_wh and not db_nowh)}

    # ⑥ manifest.image_policy 关键面
    m = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    ip = m["image_policy"]
    have_reasons = set(ip.get("no_source_reasons", {}))
    check6 = {
        "no_source_reasons_keys": sorted(have_reasons),
        "has_three_subreasons": have_reasons == {"nan_ref", "http_500", "bad_bytes"},
        "no_image_rule_mentions_three": all(t in ip["no_image_rule"] for t in ("NaN_", "HTTP 500", "bad_bytes")),
        "upscale_probe_present": "upscale_probe" in ip,
        "upscale_verdict": ip.get("upscale_probe", {}).get("verdict"),
        "source_missing_compact_present": "source_missing" in ip and "rows" not in ip["source_missing"],
        "source_missing_compact_total": ip.get("source_missing", {}).get("total"),
        "packaged_checks_present": "packaged_checks" in ip,
        "packaged_one_to_one": ip.get("packaged_checks", {}).get("one_to_one"),
        "packaged_sha256_ok": ip.get("packaged_checks", {}).get("sha256_equals_tiff_bytes"),
        "packaged_magic_ok": ip.get("packaged_checks", {}).get("tiff_magic_all_ok"),
    }

    # ⑦ report.json 三态 + source_no_image 按 ref 前缀聚合
    r = json.loads((PKG / "report.json").read_text(encoding="utf-8"))
    im = r["counts"]["images"]
    sm = r["source_missing"]
    prefix_sum = sum(g["count"] for g in sm["by_prefix"])
    check7 = {
        "counts_images": im,
        "three_state_ok": (im["ok"] == 6347 and im["failed"] == 0 and im["source_no_image"] == 418),
        "source_no_image_by_reason": sm["by_reason"],
        "by_prefix_groups": len(sm["by_prefix"]),
        "by_prefix_count_sum": prefix_sum,
        "by_prefix_sum_equals_total": prefix_sum == sm["total"],
        "failures": r["failures"],
        "sample_prefix_group": sm["by_prefix"][0],
    }

    # ⑧ source_bytes / source_sha256 逐行自洽（抽样 20；对盘 + 对台账）
    SRC = REPO / "var" / "seal_images"
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    ledger = {f"{x['seqid']}|{x['kind']}": (x["bytes"], x["sha256"]) for x in conn.execute(
        "SELECT seqid,kind,bytes,sha256 FROM seal_images WHERE status='ok'")}
    conn.close()
    rng2 = random.Random(20261010)
    sample_src = rng2.sample(rows, 20)
    src_recalc = []
    for r2 in sample_src:
        jpg = SRC / r2["kind"] / f"{r2['seqid']}.jpg"
        d_disk_sha = sha256_file(jpg) if jpg.is_file() else None
        d_disk_bytes = jpg.stat().st_size if jpg.is_file() else None
        led = ledger.get(f"{r2['seqid']}|{r2['kind']}")
        row_sha, row_bytes = r2.get("source_sha256"), r2.get("source_bytes")
        src_recalc.append({
            "seqid": r2["seqid"], "kind": r2["kind"],
            "row_source_sha256": row_sha, "row_source_bytes": row_bytes,
            "disk_sha256": d_disk_sha, "disk_bytes": d_disk_bytes,
            "ledger_sha256": led[1] if led else None, "ledger_bytes": led[0] if led else None,
            "sha_match": (d_disk_sha == row_sha == (led[1] if led else None)),
            "bytes_match": (d_disk_bytes == row_bytes == (led[0] if led else None)),
        })
    miss_src = [x["seqid"] for x in rows if not x.get("source_sha256") or x.get("source_bytes") is None]
    check8 = {
        "n": len(src_recalc),
        "all_self_consistent": all(x["sha_match"] and x["bytes_match"] for x in src_recalc),
        "rows_missing_source_fields": len(miss_src),
        "source_bytes_sha256_present_all": len(miss_src) == 0,
        "samples": src_recalc,
    }

    # ⑨ 超档清单计数 ＝ 6 且逐条可核（> xiai STORED_MAX_BYTES）
    over_flagged = [x for x in rows if x.get("oversize_for_xiai_store") is True]
    m_ov = m.get("oversize_for_xiai_store") or {}
    list_rows = m_ov.get("rows", [])
    ip_ov = (ip.get("oversize_for_xiai_store") or {})
    per_row = []
    for o in list_rows:
        p = PKG / "images" / o["sha256"][:2] / f"{o['sha256']}.tiff"
        nb = p.stat().st_size if p.is_file() else None
        mrow = next((x for x in rows if x["seqid"] == o["seqid"] and x["kind"] == o["kind"]), None)
        per_row.append({
            "seqid": o["seqid"], "kind": o["kind"],
            "bytes": o["bytes"], "width": o.get("width"), "height": o.get("height"),
            "gt_4MiB": o["bytes"] > XIAI_STORED_MAX,
            "pkg_tiff_bytes": nb, "bytes_match": nb == o["bytes"],
            "sha256": o["sha256"],
            "matches_manifest_row": bool(mrow) and mrow["sha256"] == o["sha256"],
            "marked_true_in_manifest": bool(mrow) and mrow.get("oversize_for_xiai_store") is True,
        })
    expected_seqids = {"3353", "3366", "3367", "3464", "3506", "3510"}
    check9 = {
        "expected_count": 6,
        "cited_seqids": sorted(o["seqid"] for o in list_rows),
        "seqid_set_matches": set(o["seqid"] for o in list_rows) == expected_seqids,
        "manifest_flagged_true_count": len(over_flagged),
        "top_bucket_count": m.get("oversize_count"),
        "image_policy_bucket_count": ip_ov.get("count"),
        "report_bucket_count": r.get("oversize_count"),
        "all_counts_equal_6": (len(over_flagged) == len(list_rows) == m.get("oversize_count")
                               == ip_ov.get("count") == r.get("oversize_count") == 6),
        "all_verified": all(x["gt_4MiB"] and x["bytes_match"] and x["matches_manifest_row"]
                            and x["marked_true_in_manifest"] for x in per_row),
        "rows": per_row,
    }

    out = {"check1_two_way": check1, "check2_sha20": check2, "check3_tiff_magic": check3,
           "check4_size": check4, "check5_width_height": check5,
           "check6_manifest_image_policy": check6, "check7_report": check7,
           "check8_source_bytes_sha256": check8, "check9_oversize": check9}
    (REPO / "ops" / "seal-ingest" / "17_package_selfcheck.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "c1": {k: v for k, v in check1.items()},
        "c2_all_match": check2["all_match"], "c2_n": check2["n"],
        "c3_magic_fail": check3["magic_fail_count"], "c3_ok": check3["all_ok"],
        "c4_over_stored": check4["over_stored_count"], "c4_over_input": check4["over_input_count"],
        "c4_min_max": (check4["min_bytes"], check4["max_bytes"]),
        "c5_all_have_wh": check5["all_have_wh"],
        "c6": check6, "c7": check7,
        "c8_all_self_consistent": check8["all_self_consistent"],
        "c8_present_all": check8["source_bytes_sha256_present_all"], "c8_n": check8["n"],
        "c9_counts_equal_6": check9["all_counts_equal_6"],
        "c9_seqid_set_matches": check9["seqid_set_matches"],
        "c9_all_verified": check9["all_verified"],
        "c9_cited_seqids": check9["cited_seqids"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
