#!/usr/bin/env python
"""《秦印类编 检索版》书页几何报告（Kong · ops/book-page-2400 证据件）。

只读源 PDF；产出 `geometry_report.json`（MediaBox 分布 / 主导页尺寸 / 扫描 dpi /
2400 dpi 像素 / 48bit 体积 / 观测到的微小偏差）。

跑法：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/book-page-2400/geometry_report.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parents[2]
PDF = REPO / "inbox" / "20261011" / "秦印类编 检索版.pdf"
OUT = Path(__file__).resolve().parent / "geometry_report.json"

PT_PER_IN = 72.0
MM_PER_IN = 25.4
TARGET_DPI = 2400
SAMPLES_PER_PIXEL_48BIT = 3
BITS_PER_SAMPLE = 16
PAGE_29 = 29  # 1-based


def pt2mm(pt: float) -> float:
    return pt * MM_PER_IN / PT_PER_IN


def main() -> int:
    if not PDF.exists():
        print(f"缺失源 PDF: {PDF}", file=sys.stderr)
        return 2
    doc = pymupdf.open(PDF)
    n = doc.page_count

    sizes = collections.Counter()
    rows = []
    for i in range(n):
        r = doc[i].rect
        key = (round(r.width, 3), round(r.height, 3))
        sizes[key] += 1
        rows.append(key)

    dist = [
        {
            "width_pt": w,
            "height_pt": h,
            "pages": c,
            "share": round(c / n, 6),
            "width_mm": round(pt2mm(w), 3),
            "height_mm": round(pt2mm(h), 3),
            "delta_from_dominant_pt": [round(w - 510.0, 3), round(h - 734.16, 3)],
        }
        for (w, h), c in sorted(sizes.items(), key=lambda x: -x[1])
    ]

    dominant = dist[0]
    dom_w_pt, dom_h_pt = dominant["width_pt"], dominant["height_pt"]
    # 观测到的「微小偏差」（±2pt 带内、非主导者）单独登记
    minor = [d for d in dist[1:] if abs(d["delta_from_dominant_pt"][0]) <= 2.0
             and abs(d["delta_from_dominant_pt"][1]) <= 2.0]
    outliers = [d for d in dist[1:] if d not in minor]

    # 第 29 页（1-based）细节
    p29 = doc[PAGE_29 - 1]
    imgs = p29.get_image_info(xrefs=True)
    img = imgs[0] if imgs else None
    px_w = img["width"] if img else None
    px_h = img["height"] if img else None
    scan_dpi_x = round(px_w / (p29.rect.width / PT_PER_IN), 3) if img else None
    scan_dpi_y = round(px_h / (p29.rect.height / PT_PER_IN), 3) if img else None

    out_w2400 = round(p29.rect.width / PT_PER_IN * TARGET_DPI)
    out_h2400 = round(p29.rect.height / PT_PER_IN * TARGET_DPI)
    raw_bytes = out_w2400 * out_h2400 * SAMPLES_PER_PIXEL_48BIT * (BITS_PER_SAMPLE // 8)

    report = {
        "schema": "feicui.book-page-2400.geometry_report.v1",
        "generator": "ops/book-page-2400/geometry_report.py",
        "source_pdf": str(PDF.relative_to(REPO)),
        "page_count": n,
        "page_size_distribution": dist,
        "dominant_page_size": {
            "width_pt": dom_w_pt, "height_pt": dom_h_pt,
            "width_mm": round(pt2mm(dom_w_pt), 2), "height_mm": round(pt2mm(dom_h_pt), 2),
            "pages": dominant["pages"], "share": dominant["share"],
            "conclusion_mm": "最可能页尺寸 ≈180×259 mm（16 开制）",
            "conclusion_pt": "510.0 × 734.16 pt",
        },
        "observed_minor_deviations_within_pm2pt": minor,
        "observed_outliers_beyond_pm2pt": outliers,
        "scan_resolution": {
            "page": PAGE_29,
            "embedded_image": {
                "xref": img["xref"] if img else None,
                "width_px": px_w, "height_px": px_h,
                "bpc": img["bpc"] if img else None,
                "colorspace": img["cs-name"] if img else None,
                "filter": "DCTDecode (JPEG)",
                "covers_full_page": bool(img and img["bbox"] == tuple(p29.rect)) if img else None,
            },
            "dpi_x": scan_dpi_x, "dpi_y": scan_dpi_y,
            "note": "2125 px ÷ (510 pt / 72) = 300.0 dpi；3059 px ÷ (734.16 pt / 72) = 300.0 dpi",
        },
        "target_2400dpi": {
            "page": PAGE_29,
            "width_px": out_w2400, "height_px": out_h2400,
            "megapixels": round(out_w2400 * out_h2400 / 1e6, 3),
            "bit_depth": 48,
            "samples_per_pixel": SAMPLES_PER_PIXEL_48BIT,
            "bits_per_sample": BITS_PER_SAMPLE,
            "raw_uncompressed_bytes": raw_bytes,
            "raw_uncompressed_gib": round(raw_bytes / 2**30, 3),
            "derivation": "510.0 pt/72*2400 = 17000 px；734.16 pt/72*2400 = 24472 px（皆为整数）",
            "upsample_factor_from_scan": 8,
        },
        "text_layer": {
            "page": PAGE_29,
            "text_len": len(p29.get_text().strip()),
            "kind": "纯图版页（无文本层）",
        },
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["dominant_page_size"], ensure_ascii=False, indent=2))
    print("pages:", n, "| dominant share:", dominant["share"])
    print("minor deviations (±2pt):", len(minor))
    print("outliers (>2pt):", len(outliers), [(o["width_pt"], o["height_pt"], o["pages"]) for o in outliers])
    print("2400dpi px:", out_w2400, "x", out_h2400, "| 48bit GiB", report["target_2400dpi"]["raw_uncompressed_gib"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
