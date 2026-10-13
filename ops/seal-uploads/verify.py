#!/usr/bin/env python
"""seal-uploads 批 1＋批 2 终验（独立复算；Kevin 2026-10-13 单）——真读数，不采信批跑自报。

批 1＝12 张（戰國）；批 2＝2 张（Kevin 2026-10-13 追加，朝代＝**當代**、作者＝佚名、释文留空，
每张一个批次 `seal_upload_20261013_13/_14`）。现共 **14 件**，判据：
① seals 计数（3693）＋ 14 行逐项 ＋ 既有行指纹 before≡after（批 1 口径：fudan 3679 行；
   批 2 口径：写前全量 **3691 行**，`WHERE source_seal_id NOT IN (两个新 id)`，guard_before_02.json）；
② O 件 14 件（容器/尺寸＝bbox+40px clamp/解码像素≡源裁区/四边留白 20px 数值验证）；
③ canvas 28 件（1200/62% 居中/角部色域/掩膜外无印泥，paper 与 plain_white 各一份判据）；
③b canvas 第三版（white-20px）14 件（长边 1200/四周留白恰 20px/主体 0.9667/冻结 bit_exact/
   背景纯白 std=0/晕染 α≤8% 且掩膜内≡0/居中偏差 ≤1px/同参复算可复现/成品像素≡独立复算）；
③c **批 1 既有产物 36 文件 sha 未动**（O 件 12＋两版 canvas 24；批 2 新件另经 ②/③/③b 断言）；
④ 14 张原件 sha 未动（批 1 十二张＋批 2 两张源图与 var 副本）；⑤ yinpu.db 一字未写（scratch 副本指纹）；
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
GUARD2 = json.loads((OPS / "guard_before_02.json").read_text(encoding="utf-8"))
SPEC2 = json.loads((OPS / "batch_spec_02.json").read_text(encoding="utf-8"))
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
    check("seals=3693", counts["seals"] == 3693, counts)
    check("seal_uploads=14", counts["seal_uploads"] == 14, counts)
    check("seal_links=8964 不变", counts["seal_links"] == 8964, counts)
    check("seal_images=6765 不变", counts["seal_images"] == 6765, counts)
    check("batches=4（fudan1＋批1 1＋批2 2）", counts["seal_import_batches"] == 4, counts)

    h_after = dump_hash(cols_before, "WHERE source_kind='fudan_api'")
    res["existing_rows_fingerprint"] = {"sha256": h_after, "before": GUARD["seal_ingest"]["sha256"]["seals_before"]}
    check("既有 fudan 3679 行指纹 before≡after（批 1 guard）",
          h_after == GUARD["seal_ingest"]["sha256"]["seals_before"], h_after[:16])

    # 批 2 口径：写前全量 3691 行（＝批 1 后状态）零改动（guard_before_02.json）
    con_n = sqlite3.connect(DB)
    n_existing = con_n.execute(
        "SELECT COUNT(*) FROM seals WHERE source_seal_id NOT IN "
        "('local_upload_20261013_13','local_upload_20261013_14')").fetchone()[0]
    con_n.close()
    h_existing2 = dump_hash(cols_before, "WHERE source_seal_id NOT IN "
                                          "('local_upload_20261013_13','local_upload_20261013_14')")
    res["existing_rows_fingerprint_b2"] = {"rows": n_existing, "sha256": h_existing2,
                                           "before": GUARD2["seal_ingest"]["sha256"]["seals_before"]}
    check("既有 3691 行指纹 before≡after（批 2 guard；＝fudan 3679＋批1 12）",
          n_existing == 3691 and h_existing2 == GUARD2["seal_ingest"]["sha256"]["seals_before"],
          (n_existing, h_existing2[:16]))
    check("批 2 guard 自洽：fudan 子集指纹 ≡ 批 1 guard",
          GUARD2["seal_ingest"]["sha256"]["fudan_rows_before"] == GUARD["seal_ingest"]["sha256"]["seals_before"])

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = {r["source_seal_id"]: dict(r) for r in con.execute(
        "SELECT * FROM seals WHERE source_kind='local_upload' ORDER BY source_seal_id")}
    ups = {r["seq"]: dict(r) for r in con.execute("SELECT * FROM seal_uploads ORDER BY seq")}
    con.close()
    check("local_upload 行数=14（批1 12＋批2 2）", len(rows) == 14, len(rows))
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

    # 批 2（Kevin 2026-10-13 追加 2 张：朝代＝當代；每张一个批次，目录与 batch_id 同名）
    row_checks2 = []
    for item in SPEC2["items"]:
        seq = int(item["seq"])
        sid = item["source_seal_id"]
        r = rows.get(sid)
        up = ups.get(seq)
        ok = (r is not None and up is not None
              and r["dynasty"] == SPEC2["dynasty"] and r["dynasty_source"] == "kevin_2026-10-13 指定"
              and r["author_name"] == "佚名" and r["seal_wen"] == ""
              and r["audit_status"] == "UNREVIEWED_PENDING_HUMAN_REVIEW"
              and r["source_kind"] == "local_upload" and r["batch_id"] == item["batch_id"]
              and up["sha256"] == item["sha256"] and up["source_seal_id"] == sid
              and Path(up["source_path"]).is_file()
              and Path(up["source_path"]).parent.name == item["batch_id"]
              and sha_file(Path(up["source_path"])) == item["sha256"])
        row_checks2.append({"seq": seq, "source_seal_id": sid, "batch_id": item["batch_id"], "ok": bool(ok)})
        check(f"行{seq} {sid} 逐项断言（當代）", bool(ok))
    res["rows_batch2"] = row_checks2

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

    # ── ③b canvas 第三版（white-20px）12 件（Kevin 2026-10-13 追加；独立复算，不采信批跑自报）──
    # 判据：长边 1200；几何四周留白恰 20px（独立复算 compose ⇒ 与成品逐像素相等，构图量即成品的量）；
    # 主体/画布＝0.9667；冻结 bit_exact；背景纯白 std=0；晕染 α≤8% 且掩膜内≡0；居中偏差 ≤1px；
    # 同参复算逐像素可复现；掩膜外无印泥；角部纯白；成品像素口径（掩膜/非白 bbox 留白）如实登记。
    # 注：批 1 的 12 张 white20 已被 Kevin 本人移入子目录 `异形印章 1200px 裁切原图/`（sha 未变）——
    # 与 paper 版同法，验证接受「规范位置 ∨ 用户子目录」两处，如实记录 relocate 状态（06 曾在搬移中
    # 遗失，已按批 1 记录的确定性参数重算重建，sha256 位级同一件，见 README）。
    w20_checks = []
    W20_PAD = 20
    for it in SUMMARY["items"]:
        b = it.get("canvas_white_20px")
        seq = it["seq"]
        name20 = Path(it["canvas_plain_white"]["png"]).name.replace("-canvas-white.png",
                                                                    "-canvas-white-20px.png")
        canonical20 = OUT_DIR / name20
        relocated20 = OUT_DIR / "异形印章 1200px 裁切原图" / name20
        p = canonical20 if canonical20.is_file() else relocated20
        name_ok = b is not None and Path(b["png"]).name == name20
        ok_have = b is not None and p.is_file()
        data = p.read_bytes() if ok_have else b""
        png_magic = data[:8] == b"\x89PNG\r\n\x1a\n"
        arr = np.asarray(Image.open(p).convert("RGB")) if ok_have else None
        w, h = (int(arr.shape[1]), int(arr.shape[0])) if ok_have else (0, 0)
        # 独立复算（本脚本自己的两次 compose：与批跑互不为同一次计算）
        sarr = np.asarray(Image.open(Path(it["source"])).convert("RGB"))
        cx0, cy0, cx1, cy1 = it["o"]["crop_box"]
        crop = np.ascontiguousarray(sarr[cy0:cy1, cx0:cx1])
        re1 = seal_canvas.compose(crop, caliber="A", background="plain_white", padding_px=W20_PAD)
        re2 = seal_canvas.compose(crop, caliber="A", background="plain_white", padding_px=W20_PAD)
        comp = re1["readings"]["composition"]
        rc = re1["readings"]
        pad_sides = comp["padding_px_per_side"]
        pixels_equal_recompute = ok_have and bool(np.array_equal(arr, re1["canvas"]))
        repro_bit = bool(np.array_equal(re1["canvas"], re2["canvas"]))
        pad_ok = bool(comp["padding_ok"] and comp["padding_px"] == W20_PAD
                      and all(s == W20_PAD for s in pad_sides))
        long_ok = bool(comp["canvas_long_side"] == 1200 and max(w, h) == 1200)
        ratio_ok = abs(comp["subject_ratio_actual"] - 1160 / 1200) <= 0.0001
        center_ok = max(comp["center_offset_px"]) <= 1.0
        freeze_ok = bool(rc["freeze"]["bit_exact_no_color_processing"])
        bg = rc["reproducibility"]
        bg_ok = bool(bg["bg_is_pure_white"] and max(bg["bg_stats"]["std"]) == 0.0)
        halo = rc["halo"]
        halo_ok = bool(halo["ok"] and halo["alpha_inside_mask_max"] == 0.0
                       and halo["alpha_band_max"] <= 0.08)
        if ok_have:
            seg_cv = seal_canvas.seal_mask(arr)
            mx0, my0, mx1, my1 = seg_cv["bbox"]
            mask_pad_px = {"left": int(mx0), "top": int(my0), "right": int(w - mx1), "bottom": int(h - my1)}
            ys, xs = np.where((arr != 255).any(axis=2))
            nonwhite_pad_px = {"left": int(xs.min()), "top": int(ys.min()),
                               "right": int(w - 1 - xs.max()), "bottom": int(h - 1 - ys.max())}
            corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
            corners_white = all(tuple(c) == (255, 255, 255) for c in corners)
            ink = seal_canvas.ink_mask(arr)
            halo_zone = seal_canvas.resize_mask_bool(
                __import__("cv2").dilate(seg_cv["mask"].astype(np.uint8),
                                         __import__("cv2").getStructuringElement(
                                             __import__("cv2").MORPH_ELLIPSE, (9, 9))) > 0, (w, h))
            ink_outside = int((ink & ~halo_zone).sum())
            mask_pad_ok = all(20 <= v <= 22 for v in mask_pad_px.values())
            nonwhite_ok = all(16 <= v <= 20 for v in nonwhite_pad_px.values())
            subj_long = max(mx1 - mx0, my1 - my0)
            ratio_px_val = round(subj_long / float(max(w, h)), 6)
            ratio_px_ok = abs(subj_long / float(max(w, h)) - 1160 / 1200) <= 0.01
            moff = (abs((mx0 + (mx1 - mx0) / 2.0) - w / 2.0), abs((my0 + (my1 - my0) / 2.0) - h / 2.0))
            center_px_ok = max(moff) <= 1.0
        else:
            mask_pad_px = nonwhite_pad_px = {}
            corners_white = mask_pad_ok = nonwhite_ok = ratio_px_ok = center_px_ok = False
            ink_outside = -1
            ratio_px_val = None
            moff = (0.0, 0.0)
        sha_ok = bool(ok_have and hashlib.sha256(data).hexdigest() == b["png_sha256"])
        row = {"seq": seq, "file": name20, "naming_ok": name_ok, "exists": ok_have,
               "at_canonical_path": p == canonical20, "path": str(p),
               "png_magic": png_magic, "size": [w, h], "long_side_1200": long_ok,
               "padding_rect_px": pad_sides, "padding_rect_ok": pad_ok,
               "padding_mask_bbox_px": mask_pad_px, "padding_mask_bbox_ok": mask_pad_ok,
               "padding_nonwhite_bbox_px": nonwhite_pad_px, "padding_nonwhite_ok": nonwhite_ok,
               "subject_ratio": comp["subject_ratio_actual"], "ratio_0_9667": ratio_ok,
               "subject_ratio_pixel_bbox": ratio_px_val, "ratio_pixel_ok": ratio_px_ok,
               "center_offset_px": comp["center_offset_px"], "center_ok": center_ok,
               "center_offset_pixel_bbox": [round(moff[0], 2), round(moff[1], 2)],
               "center_pixel_ok": center_px_ok,
               "freeze_bit_exact": freeze_ok, "bg_pure_white_std0": bg_ok,
               "halo_ok": halo_ok, "halo_alpha_band_max": halo["alpha_band_max"],
               "corners_white": corners_white, "ink_px_outside_seal_and_halo": ink_outside,
               "bg_no_ink": ink_outside == 0,
               "canvas_recompose_bit_exact": repro_bit,
               "pixels_equal_independent_recompute": pixels_equal_recompute,
               "png_sha256_matches_summary": sha_ok}
        w20_checks.append(row)
        check(f"w20{seq} 命名规范", name_ok, name20)
        check(f"w20{seq} 存在＋PNG", ok_have and png_magic, name20)
        check(f"w20{seq} 长边1200", long_ok, (w, h))
        check(f"w20{seq} 四周留白恰20（几何）", pad_ok, pad_sides)
        check(f"w20{seq} 主体/画布=0.9667", ratio_ok, comp["subject_ratio_actual"])
        check(f"w20{seq} 居中偏差≤1px", center_ok, comp["center_offset_px"])
        check(f"w20{seq} 冻结 bit_exact", freeze_ok)
        check(f"w20{seq} 背景纯白 std=0", bg_ok)
        check(f"w20{seq} 晕染 α≤8% 且掩膜内≡0", halo_ok,
              (halo["alpha_band_max"], halo["alpha_inside_mask_max"]))
        check(f"w20{seq} 同参复算逐像素可复现", repro_bit)
        check(f"w20{seq} 成品像素≡独立复算", pixels_equal_recompute)
        check(f"w20{seq} 角部纯白", corners_white)
        check(f"w20{seq} 掩膜外无印泥", ink_outside == 0, ink_outside)
        check(f"w20{seq} 掩膜bbox留白20–22", mask_pad_ok, mask_pad_px)
        check(f"w20{seq} 非白bbox留白16–20（晕染≤2px）", nonwhite_ok, nonwhite_pad_px)
        check(f"w20{seq} 像素口径 0.9667±0.01", ratio_px_ok, ratio_px_val)
        check(f"w20{seq} 像素口径居中≤1px", center_px_ok, moff)
        check(f"w20{seq} sha256≡summary", sha_ok)
    res["canvases_white20"] = w20_checks
    _w20_names = ({p.name for p in OUT_DIR.glob("*-canvas-white-20px.png")}
                  | {p.name for p in (OUT_DIR / "异形印章 1200px 裁切原图").glob("*-canvas-white-20px.png")})
    check("white20 恰 14 张（批1 12 在 Kevin 子目录＋批2 2 规范位）", len(_w20_names) == 14, len(_w20_names))

    # ── ③c 既有产物 sha 未动（**批 1 的 36 件**＝O 12＋两版 canvas 24 是冻结锚；批 2 新件另经 ②/③/③b）──
    unchanged = []
    for it in SUMMARY["items"]:
        batch_no = 1 if int(it["seq"]) <= 12 else 2
        o_p = OUT_DIR / it["o"]["name"]
        ok_o = o_p.is_file() and sha_file(o_p) == it["o"]["tiff_sha256_file"]
        unchanged.append({"seq": it["seq"], "batch": batch_no, "what": it["o"]["name"], "ok": bool(ok_o)})
        check(f"既有 {it['o']['name']} sha 未动", ok_o)
        for key in ("canvas_paper", "canvas_plain_white"):
            canonical = OUT_DIR / Path(it[key]["png"]).name
            relocated = OUT_DIR / "异形印章 1200px" / Path(it[key]["png"]).name
            cp = canonical if canonical.is_file() else relocated
            ok_c = cp.is_file() and sha_file(cp) == it[key]["png_sha256"]
            unchanged.append({"seq": it["seq"], "batch": batch_no, "what": Path(it[key]["png"]).name,
                              "ok": bool(ok_c), "at_canonical_path": cp == canonical})
            check(f"既有 {Path(it[key]['png']).name} sha 未动", ok_c)
    res["existing_outputs_unchanged"] = unchanged
    b1_rows = [u for u in unchanged if u.get("batch") == 1]
    check("批 1 既有 36 文件 sha 全部未动（O 12＋两版 canvas 24）",
          len(b1_rows) == 36 and all(u["ok"] for u in b1_rows), len(b1_rows))

    # ── ④ 原件 sha ─────────────────────────────────────────────────────────────────
    src_ok = []
    for item in GUARD["source_images"]:
        ok = sha_file(Path(item["source_path"])) == item["sha256"]
        src_ok.append({"batch": 1, "file": item["source_filename"], "unchanged": ok})
        check(f"原件未动 {item['source_filename']}", ok)
    for item in SPEC2["items"]:
        p_orig = Path(item["source_original"])
        p_copy = Path(item["source_path"])
        ok_orig = p_orig.is_file() and sha_file(p_orig) == item["sha256"]
        ok_copy = p_copy.is_file() and sha_file(p_copy) == item["sha256"]
        src_ok.append({"batch": 2, "file": item["source_filename"], "unchanged": bool(ok_orig and ok_copy),
                       "original_still_on_disk": bool(ok_orig), "var_copy_ok": bool(ok_copy)})
        check(f"原件未动 {item['source_filename']}（源＋var 副本）", bool(ok_orig and ok_copy))
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
        with urllib.request.urlopen("http://127.0.0.1:5196/api/seals/local_upload_20261013_13", timeout=10) as resp:
            d = json.loads(resp.read())
            api["upload_row_b2"] = {k: d.get(k) for k in ("dynasty", "author_name", "seal_wen",
                                                          "audit_status", "source_kind", "batch_id")}
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
    check("API total=3693", api.get("list_total") == 3693, api.get("list_total"))
    check("API 列表带新字段", bool(api.get("list_has_new_fields")))
    check("API 批 1 上传行可读（戰國）", api.get("upload_row", {}).get("dynasty") == "戰國")
    check("API 批 2 上传行可读（當代）", api.get("upload_row_b2", {}).get("dynasty") == "當代")
    check("API uploads 路由活（400 拒非 multipart）", bool(api.get("uploads_route_rejects_non_multipart")))

    res["fails"] = FAILS
    res["all_pass"] = not FAILS
    (OPS / "verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"all_pass": res["all_pass"], "fail_count": len(FAILS), "fails": FAILS[:10]},
                     ensure_ascii=False, indent=2))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
