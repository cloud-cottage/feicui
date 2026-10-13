#!/usr/bin/env python
"""O 件（红掩膜 bbox ＋ 20px 留白裁切）＋ 1200px 成品（seal_canvas A 口径 × 两版背景）批跑。

- O 件核心图像 ＝ `seal_canvas.seal_mask`（colorcal.ink_mask V2 ＋ 闭运算 ＋ 软边收编）外接框；
  四周各留 20px（clamp 到原图界）⇒ **原始像素裁切，零色彩处理**，TIFF RGB8 ＋ Deflate ＋ Predictor=2。
- 成品 ＝ `seal_canvas.compose(caliber="A")` 两版：`paper`（宣纸底纹）⇒ `…-canvas.png`；
  `plain_white`（纯白 #FFFFFF）⇒ `…-canvas-white.png`（Kevin 2026-10-13 追加）。
- 第三版（Kevin 2026-10-13 追加，`--variant white20`）：`plain_white` ＋ `padding_px=20`
  ⇒ `…-canvas-white-20px.png`（长边 1200、四周各留恰 20px、主体长边 1160＝画布 96.67%、居中偏差 0）；
  **只新增 12 张 PNG ＋ 回填 summary 第三变体块——不重写 O 件、不重算另两版、不写 seal_ingest.db**；
  动笔前先与既有 O 件**只读**逐像素核对（源裁区 ≡ O 件解码像素）。
- 命名：`无信息-无信息-无信息-无信息-戰國-佚名-{seq}`（P/C/R/釋文无信息；书的编号未指定 ⇒ 目录「无信息」，
  可随 Kevin 补书号重命名）；O 件 `…-O.tiff`。同目录下 12 件按 Kevin 规则会同名 ⇒ 尾部 seq 去重（待他定）。

跑法：`feicui/venv/bin/python ops/seal-uploads/make_o_and_canvas.py`（幂等：产物确定性重算覆盖）；
第三版只跑 `… --variant white20`（不写库、不动既有文件）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))

from app import seal_canvas  # noqa: E402  (seal_canvas: 纯函数，不写库)

OPS = REPO / "ops" / "seal-uploads"
SPEC = json.loads((OPS / "batch_spec.json").read_text(encoding="utf-8"))
OUT_DIR = REPO / "output" / "seals" / SPEC["dir_key"]  # output/seals/无信息
PAD = 20          # 距核心图像外围留白（Kevin 2026-10-13 指定）
WHITE20_PAD = 20  # 第三版成品四周留白（Kevin 2026-10-13 指定；⇒ 主体长边 1200−2×20=1160）
DYNASTY = SPEC["dynasty"]
AUTHOR = SPEC["author"]
WEN = "无信息"    # 释文本批留空 ⇒ 命名按「没信息就写无信息」
P = C = R = "无信息"  # 页/列/行本批无信息


def pixel_sha(arr) -> str:
    return hashlib.sha256(np.ascontiguousarray(np.asarray(arr, dtype=np.uint8)).tobytes()).hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items_out = []
    for item in SPEC["items"]:
        seq = int(item["seq"])
        src = Path(item["source_path"])
        arr = np.asarray(Image.open(src).convert("RGB"))
        H, W = int(arr.shape[0]), int(arr.shape[1])
        base = f"{P}-{C}-{R}-{WEN}-{DYNASTY}-{AUTHOR}-{seq:02d}"
        o_name = f"{base}-O.tiff"
        o_path = OUT_DIR / o_name

        seg = seal_canvas.seal_mask(arr)
        x0, y0, x1, y1 = seg["bbox"]
        cx0, cy0 = max(0, x0 - PAD), max(0, y0 - PAD)
        cx1, cy1 = min(W, x1 + PAD), min(H, y1 + PAD)
        crop = np.ascontiguousarray(arr[cy0:cy1, cx0:cx1])
        seal_canvas.write_tiff_lossless(o_path, crop)

        # O 件自证：解码像素 ≡ 源裁区（位级）；再在 O 件上复算掩膜，核对四边留白
        o_back = np.asarray(Image.open(o_path).convert("RGB"))
        assert o_back.shape == crop.shape and bool(np.array_equal(o_back, crop)), f"O 件像素不等：{o_name}"
        seg_o = seal_canvas.seal_mask(o_back)
        bx0, by0, bx1, by1 = seg_o["bbox"]
        margins = {"left": bx0, "top": by0, "right": int(o_back.shape[1] - bx1), "bottom": int(o_back.shape[0] - by1)}
        expected = {"left": x0 - cx0, "top": y0 - cy0, "right": cx1 - x1, "bottom": cy1 - y1}
        margin_diff = {k: margins[k] - expected[k] for k in margins}
        margin_ok = all(abs(v) <= (0 if v_expected == PAD else 2) for k, v in margin_diff.items()
                        for v_expected in [expected[k]])
        clamped = [k for k, v in {"left": cx0 == 0 and x0 < PAD, "top": cy0 == 0 and y0 < PAD,
                                  "right": cx1 == W and W - x1 < PAD, "bottom": cy1 == H and H - y1 < PAD}.items() if v]

        canvases = {}
        for bg, suffix in (("paper", ""), ("plain_white", "-white")):
            res = seal_canvas.compose(crop, caliber="A", background=bg)
            png_path = OUT_DIR / f"{base}-canvas{suffix}.png"
            Image.fromarray(res["canvas"]).save(png_path, format="PNG", optimize=False, compress_level=6)
            r = res["readings"]
            canvases[bg] = {
                "png": str(png_path), "png_bytes": png_path.stat().st_size,
                "png_sha256": hashlib.sha256(png_path.read_bytes()).hexdigest(),
                "canvas_size": r["composition"]["canvas_size"],
                "readings": r,
            }

        # 回填 seal_uploads 台账（o_path / canvas_path / meta_json——本批自有新行）
        from app import seals as seals_mod
        import sqlite3
        meta = {
            "naming": "P?-C?-R?-印面釋文-朝代-作者-O；书的编号未指定 ⇒ 目录「无信息」（可改）；同名冲突 ⇒ 尾部 -<seq> 去重（待 Kevin 定）",
            "o_name": o_name, "o_path": str(o_path),
            "canvas_png_paper": canvases["paper"]["png"], "canvas_png_plain_white": canvases["plain_white"]["png"],
            "core_bbox_in_source": [x0, y0, x1, y1], "o_crop_box": [cx0, cy0, cx1, cy1],
            "o_margins_px": margins, "o_margin_expected_px": expected, "o_clamped_edges": clamped,
            "core_mask": "seal_canvas.seal_mask（colorcal.ink_mask V2 ＋ close5 ＋ fringe2）",
        }
        con = sqlite3.connect(REPO / "var" / "seal_ingest.db")
        con.execute("UPDATE seal_uploads SET o_path=?, canvas_path=?, meta_json=? WHERE upload_id=?",
                    (str(o_path), canvases["paper"]["png"], json.dumps(meta, ensure_ascii=False, sort_keys=True),
                     item["upload_id"]))
        con.commit()
        con.close()

        items_out.append({
            "seq": f"{seq:02d}", "source_seal_id": item["source_seal_id"], "source": str(src),
            "source_size": [W, H], "core_bbox_in_source": [x0, y0, x1, y1],
            "core_mask_px": {"raw": int(seg["raw"].sum()), "closed": seg["closed_px"], "mask": seg["mask_px"],
                             "ink_ratio": round(seg["ink_ratio"], 6)},
            "o": {"name": o_name, "path": str(o_path), "crop_box": [cx0, cy0, cx1, cy1],
                  "size": [int(crop.shape[1]), int(crop.shape[0])],
                  "bytes": o_path.stat().st_size,
                  "tiff_sha256_file": hashlib.sha256(o_path.read_bytes()).hexdigest(),
                  "pixel_sha256": pixel_sha(crop),
                  "margins_px": margins, "expected_margins_px": expected,
                  "margin_diff_px": margin_diff, "margin_ok": bool(margin_ok), "clamped_edges": clamped},
            "canvas_paper": canvases["paper"], "canvas_plain_white": canvases["plain_white"],
        })
        cp = canvases["paper"]["readings"]["composition"]
        print(f"[ok] {seq:02d} bbox={x0},{y0},{x1},{y1} O={crop.shape[1]}x{crop.shape[0]} margins_ok={margin_ok} "
              f"canvas={cp['canvas_size']} ratio={cp['subject_ratio_actual']:.4f} "
              f"freeze={canvases['paper']['readings']['freeze']['bit_exact_no_color_processing']}")

    summary = {
        "module": "ops/seal-uploads/make_o_and_canvas.py",
        "constants": {"pad_px": PAD, "core_mask": "seal_canvas.seal_mask (close5+fringe2, fill_holes=False)",
                      "caliber": "A", "backgrounds": ["paper", "plain_white"],
                      "canvas_long_side": seal_canvas.CANVAS_LONG_SIDE,
                      "subject_ratio": seal_canvas.SUBJECT_LONG_SIDE_RATIO,
                      "bg_seed": seal_canvas.BG_SEED_DEFAULT, "dir_key": SPEC["dir_key"],
                      "naming_base": f"{P}-{C}-{R}-{WEN}-{DYNASTY}-{AUTHOR}-<seq>"},
        "items": items_out,
    }
    (OPS / "make_o_canvas_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    n_ok = sum(1 for i in items_out if i["o"]["margin_ok"])
    print(f"[done] O 件 12 ＋ canvas 24；留白判据 ok {n_ok}/12；汇总 → make_o_canvas_summary.json")
    return 0 if n_ok == 12 else 1


def main_white20() -> int:
    """第三版（Kevin 2026-10-13）：长边 1200 纯白底、四周各留恰 20px ⇒ `…-canvas-white-20px.png` ×12。

    只新增 12 张 PNG ＋ 回填 `make_o_canvas_summary.json` 第三变体块（`constants.white20` ＋
    每件 `canvas_white_20px`）；**不重写 O 件、不重算另两版 canvas、不写 seal_ingest.db**。
    主体输入与另两版同源（源图 core bbox 裁区），动笔前先与既有 O 件**只读**逐像素核对。
    """
    summary_path = OPS / "make_o_canvas_summary.json"
    if not summary_path.is_file():
        raise SystemExit("缺 make_o_canvas_summary.json——第三版回填以 full 变体的基线为底，先跑 full")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    idx_by_seq = {str(int(i["seq"])): k for k, i in enumerate(summary["items"])}
    n_ok = 0
    for item in SPEC["items"]:
        seq = int(item["seq"])
        key = str(seq)
        if key not in idx_by_seq:
            raise SystemExit(f"summary 基线缺 seq={seq}")
        srec = summary["items"][idx_by_seq[key]]
        arr = np.asarray(Image.open(Path(item["source_path"])).convert("RGB"))
        cx0, cy0, cx1, cy1 = srec["o"]["crop_box"]
        crop = np.ascontiguousarray(arr[cy0:cy1, cx0:cx1])
        o_path = OUT_DIR / srec["o"]["name"]
        if not o_path.is_file():
            raise SystemExit(f"缺既有 O 件（只读核对对象）：{o_path}")
        o_back = np.asarray(Image.open(o_path).convert("RGB"))
        if o_back.shape != crop.shape or not bool(np.array_equal(o_back, crop)):
            raise SystemExit(f"源裁区 ≢ 既有 O 件解码像素 ⇒ 拒绝出第三版（不动既有文件）：{o_path.name}")

        base = f"{P}-{C}-{R}-{WEN}-{DYNASTY}-{AUTHOR}-{seq:02d}"
        res = seal_canvas.compose(crop, caliber="A", background="plain_white", padding_px=WHITE20_PAD)
        res2 = seal_canvas.compose(crop, caliber="A", background="plain_white", padding_px=WHITE20_PAD)
        repro_bit = bool(np.array_equal(res["canvas"], res2["canvas"]))
        png_path = OUT_DIR / f"{base}-canvas-white-20px.png"
        Image.fromarray(res["canvas"]).save(png_path, format="PNG", optimize=False, compress_level=6)

        # 落盘 PNG 反测量：几何留白＝重算口径（恰值）；像素 bbox 两口径如实登记（含晕染/重采样边缘差）
        cv = np.asarray(Image.open(png_path).convert("RGB"))
        Hc, Wc = int(cv.shape[0]), int(cv.shape[1])
        ys, xs = np.where((cv != 255).any(axis=2))
        nonwhite_pad = {"left": int(xs.min()), "top": int(ys.min()),
                        "right": int(Wc - 1 - xs.max()), "bottom": int(Hc - 1 - ys.max())}
        bx0, by0, bx1, by1 = seal_canvas.seal_mask(cv)["bbox"]
        mask_pad = {"left": int(bx0), "top": int(by0), "right": int(Wc - bx1), "bottom": int(Hc - by1)}
        r = res["readings"]
        comp = r["composition"]
        bg_stats = r["reproducibility"]["bg_stats"]
        block = {
            "png": str(png_path), "png_bytes": png_path.stat().st_size,
            "png_sha256": hashlib.sha256(png_path.read_bytes()).hexdigest(),
            "canvas_size": comp["canvas_size"], "canvas_long_side": comp["canvas_long_side"],
            "subject_size": comp["subject_size"], "subject_ratio_actual": comp["subject_ratio_actual"],
            "padding_px": comp["padding_px"], "padding_px_per_side_rect": comp["padding_px_per_side"],
            "padding_ok": comp["padding_ok"],
            "padding_measured_mask_bbox_px": mask_pad,
            "padding_measured_nonwhite_bbox_px": nonwhite_pad,
            "center_offset_px": comp["center_offset_px"],
            "freeze_bit_exact": r["freeze"]["bit_exact_no_color_processing"],
            "bg_pure_white_std0": bool(r["reproducibility"]["bg_is_pure_white"] and max(bg_stats["std"]) == 0.0),
            "halo_ok": r["halo"]["ok"],
            "halo_alpha_band_max": r["halo"]["alpha_band_max"],
            "halo_alpha_inside_mask_max": r["halo"]["alpha_inside_mask_max"],
            "bg_reproducible_same_seed": r["reproducibility"]["bg_reproducible_same_seed"],
            "canvas_recompose_bit_exact": repro_bit,
            "canvas_sha256": r["reproducibility"]["canvas_sha256"],
            "readings": r,
        }
        summary["items"][idx_by_seq[key]]["canvas_white_20px"] = block
        ok = bool(comp["padding_ok"] and comp["canvas_long_side"] == 1200
                  and r["freeze"]["bit_exact_no_color_processing"] and block["bg_pure_white_std0"]
                  and r["halo"]["ok"] and repro_bit and max(comp["center_offset_px"]) <= 1.0
                  and abs(comp["subject_ratio_actual"] - 1160 / 1200) <= 0.0001)
        n_ok += 1 if ok else 0
        print(f"[ok] {seq:02d} canvas={comp['canvas_size']} subject={comp['subject_size']} "
              f"pad_rect={comp['padding_px_per_side']} pad_mask={mask_pad} pad_nonwhite={nonwhite_pad} "
              f"ratio={comp['subject_ratio_actual']:.4f} repro={repro_bit} ok={ok}")

    summary["constants"]["white20"] = {
        "background": "plain_white", "padding_px": WHITE20_PAD,
        "subject_long_px": seal_canvas.CANVAS_LONG_SIDE - 2 * WHITE20_PAD,
        "subject_ratio": round((seal_canvas.CANVAS_LONG_SIDE - 2 * WHITE20_PAD)
                               / seal_canvas.CANVAS_LONG_SIDE, 6),
        "note": "Kevin 2026-10-13 第三版：长边 1200 纯白底、四周各留恰 20px（不加 19% 宽留白）；"
                "只新增 PNG，不动 O 件／另两版／库",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] white20 12 件：判据 ok {n_ok}/12；summary 第三变体块已回填 → make_o_canvas_summary.json")
    return 0 if n_ok == 12 else 1


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser(description="O 件 ＋ 1200px 成品批跑（full＝O件＋两版 canvas；white20＝第三版纯白 20px 留白）")
    _ap.add_argument("--variant", choices=("full", "white20"), default="full",
                     help="full＝原行为（O 件＋paper/white 两版＋台账）；"
                          "white20＝只出第三版 …-canvas-white-20px.png（不写库、不动既有文件）")
    _args = _ap.parse_args()
    raise SystemExit(main() if _args.variant == "full" else main_white20())
