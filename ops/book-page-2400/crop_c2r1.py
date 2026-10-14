#!/usr/bin/env python
"""Task A ③：页 29「第一枚」改中文阅读序右上首枚 ⇒ 新裁件 P29-C2-R1。

源＝**主版**页图 `output/book-pages/9787550847224/P29-2400dpi-48bit.tif`（含校准 0.35）。
bbox@2400dpi = (11376, 4480, 12520, 6560)（＝bbox@300dpi (1422,560,1565,820) × 8）。
容器同 O 件家法：RGB 8-bit（q8 = (u16+128)//257，render_page_2400.py 同一约定）＋ Deflate ＋ Predictor=2。
断言：保存件解码像素 ≡ 页图对应区域（同一 q8 域）逐像素相等；报 px 与 mm。
C1-R1 裁件**保留不删**（只读对照）。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time

import numpy as np
import tifffile

REPO = pathlib.Path("/Users/kevin/bistro/xiai/feicui")
PAGE_DIR = REPO / "output/book-pages/9787550847224"
SRC = PAGE_DIR / "P29-2400dpi-48bit.tif"
OUT = PAGE_DIR / "P29-C2-R1-无信息-戰國-佚名-O.tiff"
C1 = PAGE_DIR / "P29-C1-R1-无信息-戰國-佚名-O.tiff"  # 保留件（只读对照）
READINGS = REPO / "ops/book-page-2400/readings-P29-C2-R1-crop.json"

# bbox：300 dpi 探测值（first_seal_probe.json candidates[1]，grid C2-R1）×8 ⇒ 2400 dpi
BBOX_300 = (1422, 560, 1565, 820)
UP = 8
BBOX_2400 = tuple(v * UP for v in BBOX_300)  # (11376, 4480, 12520, 6560)
SCAN_DPI = 300.0
TARGET_DPI = 2400.0


def q8(u16: np.ndarray) -> np.ndarray:
    """48bit→8bit 固定可逆约定（render_page_2400.py::q8 逐字同式）。"""
    return np.clip((u16.astype(np.uint32) + 128) // 257, 0, 255).astype(np.uint8)


def mm_from_px(px: float, dpi: float) -> float:
    return px / dpi * 25.4


def extract_region_u16(page: tifffile.TiffPage, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """只解码覆盖 [y0,y1) 的 strip，拼出 (y1-y0, x1-x0, 3) uint16（不整页解码）。"""
    rps = int(page.rowsperstrip)
    assert rps > 0 and not page.is_tiled, (rps, page.is_tiled)
    assert page.shape[2] == 3 and page.dtype == np.uint16, (page.shape, page.dtype)
    s0, s1 = y0 // rps, (y1 - 1) // rps
    out = np.empty((y1 - y0, x1 - x0, 3), dtype=np.uint16)
    fh = page.parent.filehandle
    for s in range(s0, s1 + 1):
        fh.seek(page.dataoffsets[s])
        band = page.decode(fh.read(page.databytecounts[s]), s)[0][0]
        ry0, ry1 = max(y0, s * rps), min(y1, (s + 1) * rps)
        out[ry0 - y0: ry1 - y0] = band[ry0 - s * rps: ry1 - s * rps, x0:x1]
    return out


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    t0 = time.time()
    assert SRC.is_file(), SRC
    crop_u16 = None
    with tifffile.TiffFile(SRC) as tf:
        page = tf.pages[0]
        ph, pw = int(page.shape[0]), int(page.shape[1])
        x0, y0, x1, y1 = BBOX_2400
        assert 0 <= x0 < x1 <= pw and 0 <= y0 < y1 <= ph, (BBOX_2400, pw, ph)
        crop_u16 = extract_region_u16(page, y0, y1, x0, x1)
    crop_u8 = q8(crop_u16)
    assert crop_u8.shape == (2080, 1144, 3), crop_u8.shape

    # 写 O 件（原子：.part → os.replace；容器家法 RGB 8bit + Deflate(8) + Predictor=2）
    part = OUT.with_name(OUT.name + ".part")
    if part.exists():
        part.unlink()
    with tifffile.TiffWriter(part) as tw:
        tw.write(crop_u8, photometric="rgb", planarconfig="contig",
                 compression=8, predictor=2, rowsperstrip=32,
                 resolution=((int(TARGET_DPI), 1), (int(TARGET_DPI), 1)), resolutionunit="INCH",
                 software="feicui ops/book-page-2400 crop_c2r1.py (task A no.3 top-right first seal)")
    os.replace(part, OUT)

    # 逐像素断言：保存件解码 ≡ 页图同一区域（独立第二遍提取）
    with tifffile.TiffFile(OUT) as tf:
        pg = tf.pages[0]
        saved = pg.asarray()
        tags = {
            "shape": list(pg.shape), "dtype": str(pg.dtype), "compression": int(pg.compression),
            "predictor": int(pg.predictor), "photometric": int(pg.photometric),
            "rowsperstrip": int(pg.rowsperstrip), "bigtiff": bool(tf.is_bigtiff),
            "samples_per_pixel": int(pg.samplesperpixel), "bits_per_sample": int(pg.bitspersample),
        }
    ref_u8 = None
    with tifffile.TiffFile(SRC) as tf_src:
        ref_u8 = q8(extract_region_u16(tf_src.pages[0], y0, y1, x0, x1))
    mismatch = int(np.count_nonzero(saved.view(np.uint8) != ref_u8.view(np.uint8)))
    max_abs = int(np.abs(saved.astype(np.int16) - ref_u8.astype(np.int16)).max())

    w_px_300 = BBOX_300[2] - BBOX_300[0]
    h_px_300 = BBOX_300[3] - BBOX_300[1]
    readings = {
        "schema": "feicui.book-page-2400.crop-c2r1.v1",
        "task": "Kevin ③：《秦印类编》页 29「第一枚」改中文阅读序右上首枚 ⇒ 新裁件 C2-R1（C1-R1 保留）",
        "source": {"path": str(SRC), "bytes": SRC.stat().st_size, "sha256": sha256_file(SRC),
                   "note": "主版（校准 0.35）；冻结版未另出裁件"},
        "bbox_300dpi": list(BBOX_300), "upsample": f"{SCAN_DPI:.0f} dpi → {TARGET_DPI:.0f} dpi（×{UP} 整数上采样）",
        "bbox_2400dpi": list(BBOX_2400),
        "artifact": {"path": str(OUT), "bytes": OUT.stat().st_size, "sha256": sha256_file(OUT),
                     "container": tags},
        "verify": {
            "pixel_mismatch_vs_page_region": mismatch, "max_abs_diff_u8": max_abs,
            "region_px": [int(x1 - x0), int(y1 - y0)],
            "pixel_equal": bool(mismatch == 0 and max_abs == 0),
        },
        "size": {
            "px_2400dpi": [int(x1 - x0), int(y1 - y0)],
            "px_300dpi": [w_px_300, h_px_300],
            "mm_via_2400dpi": [round(mm_from_px(x1 - x0, TARGET_DPI), 3), round(mm_from_px(y1 - y0, TARGET_DPI), 3)],
            "mm_via_300dpi": [round(mm_from_px(w_px_300, SCAN_DPI), 3), round(mm_from_px(h_px_300, SCAN_DPI), 3)],
            "mm_consistent": True,
        },
        "kept_existing": {"path": str(C1), "exists": C1.is_file(),
                          "bytes": C1.stat().st_size if C1.is_file() else None,
                          "sha256": sha256_file(C1) if C1.is_file() else None},
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    readings["size"]["mm_consistent"] = (
        readings["size"]["mm_via_2400dpi"] == readings["size"]["mm_via_300dpi"]
    )
    READINGS.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(readings, ensure_ascii=False, indent=2))
    return 0 if readings["verify"]["pixel_equal"] and readings["size"]["mm_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
