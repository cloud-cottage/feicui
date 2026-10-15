#!/usr/bin/env python
"""第 29 页「第一枚印面」定位探针（Kong · ops/book-page-2400 证据件）。

复算 Zang 的侦查结论：300 dpi 源图（xref112, 2125×3059）→ `colorcal.ink_mask`
→ 15 px 椭圆核闭运算 → 连通域 → 6 枚候选（2 列 × 3 行）；按阅读序（上→下、左→右）
取第一枚，报 300 dpi bbox 与 2400 dpi 换算 bbox。

只读；产物 `first_seal_probe.json` ＋ `recon_p29_mask.png`（掩膜调试图，供人核对）。

跑法：
    cd /Users/kevin/bistro/feicui
    ./venv/bin/python ops/book-page-2400/first_seal_probe.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))  # 让 `app.colorcal` 指向 server/app（不被仓根 app.py 遮蔽）

from app.colorcal import ink_mask as _ink_mask  # noqa: E402

PDF = REPO / "inbox" / "20261011" / "秦印类编 检索版.pdf"
HERE = Path(__file__).resolve().parent
PAGE = 29
SCAN_DPI = 300.0
TARGET_DPI = 2400.0
CLOSE_PX = 15
MIN_AREA_300 = 4000          # 300 dpi 下印面候选最小面积（≈ 63×63 px）
MAX_ASPECT = 2.0   # 放宽到 2.0：上排右枚为长条印（143×260, ar=1.818），按 1.6 会被漏掉


def load_scan() -> np.ndarray:
    doc = pymupdf.open(PDF)
    img = doc[PAGE - 1].get_image_info(xrefs=True)[0]
    raw = doc.extract_image(img["xref"])["image"]
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))


def detect(rgb: np.ndarray) -> tuple[list[dict], np.ndarray, np.ndarray]:
    raw = np.asarray(_ink_mask(rgb), dtype=bool)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_PX, CLOSE_PX))
    closed = cv2.morphologyEx(raw.astype(np.uint8), cv2.MORPH_CLOSE, se) > 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats(closed.astype(np.uint8), 8)
    cand = []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < MIN_AREA_300:
            continue
        ar = max(w, h) / max(1, min(w, h))
        if not (1 / MAX_ASPECT < ar < MAX_ASPECT):
            continue
        cand.append({"x0": x, "y0": y, "x1": x + w, "y1": y + h,
                     "w": w, "h": h, "area": area, "aspect": round(ar, 3)})
    # 阅读序：上→下（行以 y 中心聚合），再左→右
    cand.sort(key=lambda c: (c["y0"], c["x0"]))
    return cand, raw, closed


def group_rows(cand: list[dict], tol_px: int = 60) -> list[tuple[dict, int]]:
    """把候选按 y 中心聚成行带，返回每枚的「(候选, 行序号)」（行序号 0-based，自上而下）。"""
    rows: list[float] = []
    labels: list[tuple[dict, int]] = []
    for c in sorted(cand, key=lambda c: (c["y0"] + c["y1"]) / 2):
        yc = (c["y0"] + c["y1"]) / 2
        for i, yc0 in enumerate(rows):
            if abs(yc - yc0) <= tol_px:
                rows[i] = (rows[i] + yc) / 2
                labels.append((c, i))
                break
        else:
            rows.append(yc)
            labels.append((c, len(rows) - 1))
    return labels


def main() -> int:
    rgb = load_scan()
    print("scan", rgb.shape)
    cand, raw, closed = detect(rgb)
    labels = group_rows(cand)
    # 重排：行优先、行内左→右
    ordered = [c for c, _ in sorted(labels, key=lambda t: (t[1], t[0]["x0"]))]
    for i, c in enumerate(ordered, 1):
        row = [r for cc, r in labels if cc is c][0] + 1
        c["read_order"] = i
        c["grid_row"] = row
    # 列号（按 x 中心）
    xs = sorted({round((c["x0"] + c["x1"]) / 2 / 200) for c in ordered})
    for c in ordered:
        c["grid_col"] = xs.index(round((c["x0"] + c["x1"]) / 2 / 200)) + 1
    first = ordered[0]
    scale = TARGET_DPI / SCAN_DPI
    bbox2400 = [round(first[k] * scale) for k in ("x0", "y0", "x1", "y1")]
    mm_per_px_300 = 25.4 / SCAN_DPI
    out = {
        "schema": "feicui.book-page-2400.first_seal_probe.v1",
        "page": PAGE,
        "scan": {"dpi": SCAN_DPI, "size_px": [int(rgb.shape[1]), int(rgb.shape[0])]},
        "detector": {
            "ink_mask": "server/app/colorcal.ink_mask (V2: r>g+15 ∧ r>b+15 ∧ S>0.25)",
            "close_px": CLOSE_PX, "min_area_300dpi": MIN_AREA_300, "max_aspect": MAX_ASPECT,
        },
        "candidates": ordered,
        "candidate_count": len(ordered),
        "reading_order_definition": "上→下（行带聚合）→ 行内左→右",
        "first_seal": {
            "read_order": 1,
            "grid": f"C{first['grid_col']}-R{first['grid_row']}",
            "bbox_300dpi": [first["x0"], first["y0"], first["x1"], first["y1"]],
            "size_px_300dpi": [first["x1"] - first["x0"], first["y1"] - first["y0"]],
            "bbox_2400dpi": bbox2400,
            "size_px_2400dpi": [bbox2400[2] - bbox2400[0], bbox2400[3] - bbox2400[1]],
            "size_mm": [round((first["x1"] - first["x0"]) * mm_per_px_300, 3),
                        round((first["y1"] - first["y0"]) * mm_per_px_300, 3)],
        },
        "ink_ratio": round(float(np.asarray(_ink_mask(rgb)).mean()), 6),
    }
    (HERE / "first_seal_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    vis = np.asarray(rgb).copy()
    for i, c in enumerate(ordered, 1):
        col = (0, 255, 0) if i == 1 else (0, 200, 255)
        cv2.rectangle(vis, (c["x0"], c["y0"]), (c["x1"] - 1, c["y1"] - 1), col, 6)
        cv2.putText(vis, str(i), (c["x0"] + 8, c["y0"] + 60), cv2.FONT_HERSHEY_SIMPLEX, 2, col, 5)
    Image.fromarray(vis).resize((531, 764)).save(HERE / "recon_p29_mask.png")

    print(json.dumps(out["first_seal"], ensure_ascii=False, indent=2))
    print("candidates:", len(ordered), "| ink_ratio", out["ink_ratio"])
    for c in ordered:
        print(" ", c["read_order"], c["grid_col"], c["grid_row"], c["x0"], c["y0"], c["x1"], c["y1"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
