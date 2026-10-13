#!/usr/bin/env python
"""O 件（红掩膜 bbox ＋ 20px 留白裁切）＋ 1200px 成品（seal_canvas A 口径 × 两版背景）批跑。

- O 件核心图像 ＝ `seal_canvas.seal_mask`（colorcal.ink_mask V2 ＋ 闭运算 ＋ 软边收编）外接框；
  四周各留 20px（clamp 到原图界）⇒ **原始像素裁切，零色彩处理**，TIFF RGB8 ＋ Deflate ＋ Predictor=2。
- 成品 ＝ `seal_canvas.compose(caliber="A")` 两版：`paper`（宣纸底纹）⇒ `…-canvas.png`；
  `plain_white`（纯白 #FFFFFF）⇒ `…-canvas-white.png`（Kevin 2026-10-13 追加）。
- 命名：`无信息-无信息-无信息-无信息-戰國-佚名-{seq}`（P/C/R/釋文无信息；书的编号未指定 ⇒ 目录「无信息」，
  可随 Kevin 补书号重命名）；O 件 `…-O.tiff`。同目录下 12 件按 Kevin 规则会同名 ⇒ 尾部 seq 去重（待他定）。

跑法：`feicui/venv/bin/python ops/seal-uploads/make_o_and_canvas.py`（幂等：产物确定性重算覆盖）。
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


if __name__ == "__main__":
    raise SystemExit(main())
