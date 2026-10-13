#!/usr/bin/env python
"""seal-uploads 批 1 终验（独立复算；Kevin 2026-10-13 单）——真读数，不采信批跑自报。

核：① seals 计数＋12 行逐项＋既有行指纹 before≡after；② O 件 12 件（容器/尺寸＝bbox+40px clamp/
解码像素≡源裁区/四边留白 20px 数值验证）；③ canvas 24 件（1200/62% 居中/角部色域/掩膜外无印泥，
paper 与 plain_white 各一份判据）；④ 12 张原件 sha 未动；⑤ yinpu.db 一字未写（scratch 副本指纹）；
⑥ 生产 API 活读数（5196）。结果 → `verify.json`；判据全过退出 0。

跑法：`feicui/venv/bin/python ops/seal-uploads/verify.py`
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))
from app import seal_canvas  # noqa: E402

OPS = REPO / "ops" / "seal-uploads"
GUARD = json.loads((OPS / "guard_before.json").read_text(encoding="utf-8"))
SUMMARY = json.loads((OPS / "make_o_canvas_summary.json").read_text(encoding="utf-8"))
OUT_DIR = REPO / "output" / "seals" / "无信息"
DB = REPO / "var" / "seal_ingest.db"
SCR = Path("/Users/kevin/.hermes/profiles/zang/cache/scratch/seal-uploads-20261013")

FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> bool:
    if not ok:
        FAILS.append(f"{name}: {detail}")
    return bool(ok)


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def dump_hash(cols: list[str], where: str = "") -> str:
    con = sqlite3.connect(DB)
    h = hashlib.sha256()
    for row in con.execute(f"SELECT {', '.join(cols)} FROM seals {where} ORDER BY source_seal_id"):
        h.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
    con.close()
    return h.hexdigest()


def main() -> int:
    res: dict = {"generated_at": seal_canvas.__name__ and __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")}
    cols_before = [c for c, _ in GUARD["seal_ingest"]["schemas"]["seals"]]

    # ── ① DB ──────────────────────────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("seals", "seal_links", "seal_images", "seal_import_batches", "seal_uploads")}
    con.close()
    res["db_counts"] = counts
    check("seals=3691", counts["seals"] == 3691, counts)
    check("seal_uploads=12", counts["seal_uploads"] == 12, counts)
    check("seal_links=8964 不变", counts["seal_links"] == 8964, counts)
    check("seal_images=6765 不变", counts["seal_images"] == 6765, counts)
    check("batches=2（原1＋本批1）", counts["seal_import_batches"] == 2, counts)

    h_after = dump_hash(cols_before, "WHERE source_kind='fudan_api'")
    res["existing_rows_fingerprint"] = {"sha256": h_after, "before": GUARD["seal_ingest"]["sha256"]["seals_before"]}
    check("既有 3679 行指纹 before≡after",
          h_after == GUARD["seal_ingest"]["sha256"]["seals_before"], h_after[:16])

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = {r["source_seal_id"]: dict(r) for r in con.execute(
        "SELECT * FROM seals WHERE source_kind='local_upload' ORDER BY source_seal_id")}
    ups = {r["seq"]: dict(r) for r in con.execute("SELECT * FROM seal_uploads ORDER BY seq")}
    con.close()
    check("local_upload 行数=12", len(rows) == 12, len(rows))
    row_checks = []
    for item in GUARD["source_images"]:
        seq = int(item["seq"])
        sid = f"local_upload_20261013_{seq:02d}"
        r = rows.get(sid)
        up = ups.get(seq)
        ok = (r is not None and up is not None
              and r["dynasty"] == "戰國" and r["dynasty_source"] == "kevin_2026-10-13 指定"
              and r["author_name"] == "佚名" and r["seal_wen"] == ""
              and r["audit_status"] == "UNREVIEWED_PENDING_HUMAN_REVIEW"
              and r["source_kind"] == "local_upload" and r["batch_id"] == "seal_upload_20261013_01"
              and up["sha256"] == item["sha256"] and up["source_seal_id"] == sid
              and Path(up["source_path"]).is_file()
              and sha_file(Path(up["source_path"])) == item["sha256"])
        row_checks.append({"seq": item["seq"], "source_seal_id": sid, "ok": bool(ok)})
        check(f"行{item['seq']} {sid} 逐项断言", bool(ok))
    res["rows"] = row_checks

    # ── ② O 件 ─────────────────────────────────────────────────────────────────────
    o_checks = []
    for it in SUMMARY["items"]:
        seq = it["seq"]
        o_path = OUT_DIR / it["o"]["name"]
        src = Path(it["source"])
        arr = np.asarray(Image.open(src).convert("RGB"))
        H, W = arr.shape[0], arr.shape[1]
        x0, y0, x1, y1 = it["core_bbox_in_source"]
        cx0, cy0, cx1, cy1 = it["o"]["crop_box"]
        ok_exist = o_path.is_file()
        im = Image.open(o_path) if ok_exist else None
        comp = {"compression": im.tag_v2.get(259), "predictor": im.tag_v2.get(317),
                "bits": im.tag_v2.get(258), "photometric": im.tag_v2.get(262)} if im else {}
        o_arr = np.asarray(im.convert("RGB")) if im else None
        size_ok = ok_exist and list(o_arr.shape[:2][::-1]) == [cx1 - cx0, cy1 - cy0]
        expect_size = [min(W, x1 + 20) - max(0, x0 - 20), min(H, y1 + 20) - max(0, y0 - 20)]
        size_expect_ok = list(o_arr.shape[:2][::-1]) == expect_size if o_arr is not None else False
        pixel_ok = o_arr is not None and bool(np.array_equal(o_arr, arr[cy0:cy1, cx0:cx1]))
        in_bounds = 0 <= cx0 < cx1 <= W and 0 <= cy0 < cy1 <= H
        seg_o = seal_canvas.seal_mask(o_arr) if o_arr is not None else None
        bx0, by0, bx1, by1 = seg_o["bbox"] if seg_o else (0, 0, 0, 0)
        margins = {"left": bx0, "top": by0, "right": int(o_arr.shape[1] - bx1), "bottom": int(o_arr.shape[0] - by1)}
        margin_ok = all(m == 20 for m in margins.values()) if seg_o else False
        row = {"seq": seq, "file": o_path.name, "exists": ok_exist, "container": comp,
               "container_ok": comp.get("compression") in (8, 32946) and comp.get("predictor") == 2
                              and comp.get("bits") == (8, 8, 8) and comp.get("photometric") == 2,
               "size": [int(o_arr.shape[1]), int(o_arr.shape[0])] if o_arr is not None else None,
               "expected_size_bbox_plus_40_clamped": expect_size,
               "size_ok": bool(size_ok and size_expect_ok),
               "pixels_equal_source_crop": bool(pixel_ok), "crop_in_source_bounds": bool(in_bounds),
               "ink_margins_px": margins, "margin_20px_ok": bool(margin_ok)}
        o_checks.append(row)
        check(f"O{seq} 容器", row["container_ok"], comp)
        check(f"O{seq} 尺寸=bbox+40 clamp", row["size_ok"], row["size"])
        check(f"O{seq} 像素≡源裁区（零色彩处理）", pixel_ok)
        check(f"O{seq} 在原图界内", in_bounds)
        check(f"O{seq} 距核心 20px（四边数值）", margin_ok, margins)
    res["o_pieces"] = o_checks

    # ── ③ canvas 24 件 ─────────────────────────────────────────────────────────────
    # 注：批跑后 Kevin 本人把 12 张 paper 版 canvas 移入 `异形印章 1200px/` 子目录（sha 未变）——
    # 验证对 paper 版接受「规范位置 ∨ 用户子目录」两处，如实记录 relocate 状态，不代移回。
    cv_checks = []
    for it in SUMMARY["items"]:
        for key, suffix, white in (("canvas_paper", "-canvas.png", False),
                                   ("canvas_plain_white", "-canvas-white.png", True)):
            canonical = OUT_DIR / Path(it[key]["png"]).name
            relocated = OUT_DIR / "异形印章 1200px" / Path(it[key]["png"]).name
            p = canonical if canonical.is_file() else relocated
            data = p.read_bytes()
            png_magic = data[:8] == b"\x89PNG\r\n\x1a\n"
            im = Image.open(p)
            w, h = im.size
            arr = np.asarray(im.convert("RGB"))
            corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
            if white:
                corner_ok = all(tuple(c) == (255, 255, 255) for c in corners)
            else:
                # 色域 #FAFAF7–#FFFFFF：R≥250 ∧ G≥250 ∧ B≥247 ∧ 全 ≤255（通道各自下限）
                corner_ok = all(int(c[0]) >= 250 and int(c[1]) >= 250 and int(c[2]) >= 247
                                and int(max(c)) <= 255 for c in corners)
            seg = seal_canvas.seal_mask(arr)
            sx0, sy0, sx1, sy1 = seg["bbox"]
            subj_long = max(sx1 - sx0, sy1 - sy0)
            ratio = subj_long / float(max(w, h))
            ratio_ok = abs(ratio - 0.62) <= 0.01
            off = (abs((sx0 + (sx1 - sx0) / 2.0) - w / 2.0), abs((sy0 + (sy1 - sy0) / 2.0) - h / 2.0))
            center_ok = off[0] <= 2.0 and off[1] <= 2.0
            long_ok = max(w, h) == 1200
            ink = seal_canvas.ink_mask(arr)
            from app import colorcal  # noqa: F401  (ink_mask 唯一实现)
            halo_zone = seal_canvas.resize_mask_bool(
                __import__("cv2").dilate(seg["mask"].astype(np.uint8),
                                         __import__("cv2").getStructuringElement(
                                             __import__("cv2").MORPH_ELLIPSE, (9, 9))) > 0, (w, h))
            ink_outside = int((ink & ~halo_zone).sum())
            row = {"seq": it["seq"], "version": "plain_white" if white else "paper", "file": p.name,
                   "path": str(p), "at_canonical_path": p == canonical,
                   "png_magic": png_magic, "size": [w, h], "long_side_1200": long_ok,
                   "subject_ratio": round(ratio, 6), "ratio_62pct": ratio_ok,
                   "center_offset_px": [round(off[0], 2), round(off[1], 2)], "center_ok": center_ok,
                   "corners": [list(map(int, c)) for c in corners],
                   "corner_gamut_ok": corner_ok, "ink_px_outside_seal_and_halo": ink_outside,
                   "bg_no_ink": ink_outside == 0}
            cv_checks.append(row)
            check(f"canvas{it['seq']}{suffix} PNG+1200", png_magic and long_ok, (w, h))
            check(f"canvas{it['seq']}{suffix} 62% 居中", ratio_ok and center_ok, (ratio, off))
            check(f"canvas{it['seq']}{suffix} 角部色域", corner_ok, corners[0])
            check(f"canvas{it['seq']}{suffix} 掩膜外无印泥", ink_outside == 0, ink_outside)
    res["canvases"] = cv_checks

    # ── ④ 原件 sha ─────────────────────────────────────────────────────────────────
    src_ok = []
    for item in GUARD["source_images"]:
        ok = sha_file(Path(item["source_path"])) == item["sha256"]
        src_ok.append({"file": item["source_filename"], "unchanged": ok})
        check(f"原件未动 {item['source_filename']}", ok)
    res["sources_unchanged"] = src_ok

    # ── ⑤ yinpu.db 未写 ────────────────────────────────────────────────────────────
    yp = GUARD["yinpu"]["path"]
    ydir = SCR / "yinpu_verify"
    ydir.mkdir(parents=True, exist_ok=True)
    for ext in ("", "-wal", "-shm"):
        if Path(yp + ext).exists():
            shutil.copy2(yp + ext, ydir / ("yinpu.db" + ext))
    ycon = sqlite3.connect(f"file:{ydir}/yinpu.db?mode=ro", uri=True)
    hh = hashlib.sha256()
    for row in ycon.execute("SELECT * FROM stamps ORDER BY id"):
        hh.update(json.dumps(list(row), ensure_ascii=False).encode("utf-8"))
        hh.update(b"\n")
    ycounts = {t: ycon.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("stamps", "jobs", "job_pages")}
    ycon.close()
    stat_now = {p: {"size": Path(yp + p).stat().st_size} for p in ("", "-wal") if Path(yp + p).exists()}
    yinpu_ok = hh.hexdigest() == GUARD["yinpu"]["stamps_dump_sha256"] and \
        ycounts == GUARD["yinpu"]["counts"] and \
        stat_now[""]["size"] == GUARD["yinpu"]["stat_before"][""]["size"]
    res["yinpu"] = {"counts": ycounts, "stamps_dump_sha256": hh.hexdigest(),
                    "before_sha": GUARD["yinpu"]["stamps_dump_sha256"],
                    "main_db_size_unchanged": stat_now[""]["size"] == GUARD["yinpu"]["stat_before"][""]["size"],
                    "ok": bool(yinpu_ok)}
    check("yinpu.db 一字未写（内容指纹＋主库 size）", yinpu_ok)

    # ── ⑥ 生产 API 活读数（5196，零写入探针）────────────────────────────────────────
    api = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:5196/api/seals?limit=1", timeout=10) as resp:
            d = json.loads(resp.read())
            api["list_total"] = d["total"]
            api["list_has_new_fields"] = "dynasty" in d["items"][0]
        with urllib.request.urlopen("http://127.0.0.1:5196/api/seals/local_upload_20261013_01", timeout=10) as resp:
            d = json.loads(resp.read())
            api["upload_row"] = {k: d.get(k) for k in ("dynasty", "author_name", "seal_wen", "audit_status", "source_kind")}
        req = urllib.request.Request("http://127.0.0.1:5196/api/seals/uploads", data=b"", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            api["uploads_route_rejects_non_multipart"] = False
        except urllib.error.HTTPError as e:
            api["uploads_route_rejects_non_multipart"] = e.code == 400
    except Exception as exc:  # noqa: BLE001
        api["error"] = repr(exc)
    res["api"] = api
    check("API total=3691", api.get("list_total") == 3691, api.get("list_total"))
    check("API 列表带新字段", bool(api.get("list_has_new_fields")))
    check("API 上传行可读", api.get("upload_row", {}).get("dynasty") == "戰國")
    check("API uploads 路由活（400 拒非 multipart）", bool(api.get("uploads_route_rejects_non_multipart")))

    res["fails"] = FAILS
    res["all_pass"] = not FAILS
    (OPS / "verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"all_pass": res["all_pass"], "fail_count": len(FAILS), "fails": FAILS[:10]},
                     ensure_ascii=False, indent=2))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
