#!/usr/bin/env python
"""出「300dpi 8bit 经典 TIFF/PNG 预览件」：从既有 BigTIFF 48bit 页图**只读**转换。

用途：macOS（Preview / Quick Look）不支持 BigTIFF 48bit —— `sips` 读数全 `<nil>`、
`qlmanage -t` 卡死。本脚本另出**几何对应**的 8bit 经典容器预览件：
   尺寸 = 原件 ÷8（2400dpi → 300dpi）：17000/8 = 2125 高、24472/8 = 3059 宽
   位深 = 项目既有约定 q8（(u16+128)//257，同 render_page_2400.py / crop_c2r1.py 逐字同式）
   降采样 = cv2.INTER_AREA（整数 ÷8，8×8 块均值）

内存纪律：整页 u16 = 2.5 GB，**禁止一次 asarray()**。按 strip 级流式解码
（rowsperstrip=256）→ 逐 strip q8 写入 scratch 里的 uint8 memmap（1.25 GB，
不驻留内存），最后对 memmap 做一次 INTER_AREA ÷8。

只读保证：源文件只 open('rb')，不改动、不重跑渲染；输出目录仅 output/2_HighRes_PDF/。

用法：
    ./venv/bin/python ops/book-page-2400/make_preview_8bit.py            # 两件 BigTIFF 全出
    ./venv/bin/python ops/book-page-2400/make_preview_8bit.py <SRC.tif>  # 单件（可多次）
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time

import cv2
import numpy as np
import tifffile
from PIL import Image

REPO = pathlib.Path("/Users/kevin/bistro/feicui")
PAGE_DIR = REPO / "output/2_HighRes_PDF/9787550847224"
DEFAULT_SRCS = [
    PAGE_DIR / "P29-2400dpi-48bit.tif",
    PAGE_DIR / "P29-2400dpi-48bit-frozen.tif",
]
READINGS = REPO / "ops/book-page-2400/readings-previews-8bit.json"
SCRATCH = pathlib.Path(
    os.environ.get("FEICUI_PREVIEW_SCRATCH", "/Users/kevin/.hermes/profiles/zang/cache/scratch")
) / "preview-8bit-memmap"

UP = 8  # 2400 dpi → 300 dpi
PREVIEW_DPI = 300


def q8(u16: np.ndarray) -> np.ndarray:
    """48bit→8bit 固定可逆约定（render_page_2400.py::q8 / crop_c2r1.py::q8 逐字同式）。"""
    return np.clip((u16.astype(np.uint32) + 128) // 257, 0, 255).astype(np.uint8)


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_u16(page: tifffile.TiffPage, s: int) -> np.ndarray:
    """解码第 s 条 strip → (rows, w, 3) uint16（不整页解码）。"""
    fh = page.parent.filehandle
    fh.seek(page.dataoffsets[s])
    return page.decode(fh.read(page.databytecounts[s]), s)[0][0]


def extract_region_u16(page: tifffile.TiffPage, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """只解码覆盖 [y0,y1) 的 strip，拼出 (y1-y0, x1-x0, 3) uint16（crop_c2r1.py 同一先例）。"""
    rps = int(page.rowsperstrip)
    assert rps > 0 and not page.is_tiled and page.dtype == np.uint16 and page.shape[2] == 3
    s0, s1 = y0 // rps, (y1 - 1) // rps
    out = np.empty((y1 - y0, x1 - x0, 3), dtype=np.uint16)
    for s in range(s0, s1 + 1):
        band = strip_u16(page, s)
        ry0, ry1 = max(y0, s * rps), min(y1, (s + 1) * rps)
        out[ry0 - y0:ry1 - y0] = band[ry0 - s * rps:ry1 - s * rps, x0:x1]
    return out


def magic_bytes(p: pathlib.Path) -> str:
    return p.open("rb").read(4).hex(" ")


def build_preview(src: pathlib.Path, scratch: pathlib.Path) -> dict:
    t0 = time.time()
    st = src.stat()
    stem = src.name[: -len("".join(src.suffixes))] if src.suffixes else src.stem
    out_tif = src.with_name(f"{stem}-preview300-8bit.tiff")
    out_png = src.with_name(f"{stem}-preview300-8bit.png")

    with tifffile.TiffFile(src) as tf:
        page = tf.pages[0]
        src_tags = {
            "bigtiff": bool(tf.is_bigtiff), "shape": [int(v) for v in page.shape],
            "dtype": str(page.dtype), "compression": int(page.compression),
            "predictor": int(page.predictor), "bits_per_sample": int(page.bitspersample),
            "samples_per_pixel": int(page.samplesperpixel), "photometric": int(page.photometric),
            "rows_per_strip": int(page.rowsperstrip), "is_tiled": bool(page.is_tiled),
            "resolution": [int(v) for v in page.tags["XResolution"].value],
            "resolution_unit": str(page.tags["ResolutionUnit"].value),
        }
        ph, pw = int(page.shape[0]), int(page.shape[1])
        assert ph % UP == 0 and pw % UP == 0, (ph, pw)
        oh, ow = ph // UP, pw // UP
        rps = int(page.rowsperstrip)
        assert rps > 0 and not page.is_tiled

        # 逐 strip 流式解码 + q8 → uint8 memmap（不整页驻留内存）
        scratch.mkdir(parents=True, exist_ok=True)
        mm_path = scratch / f"{stem}.u8.mmap"
        if mm_path.exists():
            mm_path.unlink()
        page_u8 = np.memmap(mm_path, dtype=np.uint8, mode="w+", shape=(ph, pw, 3))
        n_strips_read = 0
        for s in range(len(page.dataoffsets)):
            band = strip_u16(page, s)
            y0 = s * rps
            y1 = min(ph, y0 + band.shape[0])
            page_u8[y0:y1] = q8(band)
            n_strips_read += 1
        page_u8.flush()

        # INTER_AREA ÷8（几何对应：2125 × 3059）
        small = cv2.resize(page_u8, (ow, oh), interpolation=cv2.INTER_AREA)
        assert small.shape == (oh, ow, 3) and small.dtype == np.uint8, small.shape

        # ⑤ 抽 1 个 strip 级区域：预览件 vs 原件同区域 q8 + INTER_AREA ÷8 一致性
        #    取输出 (400,1000) 起 32×32 ⇒ 原件 (3200,8000) 起 256×256（跨 strip 12–13）
        oy, ox, n = 400, 1000, 32
        sy, sx = oy * UP, ox * UP
        ref_u16 = extract_region_u16(page, sy, sy + n * UP, sx, sx + n * UP)
        ref_small = cv2.resize(q8(ref_u16), (n, n), interpolation=cv2.INTER_AREA)
        got_small = small[oy:oy + n, ox:ox + n]
        diff = np.abs(got_small.astype(np.int16) - ref_small.astype(np.int16))
        geom_check = {
            "region_out_px": [ox, oy, n, n], "region_src_px": [sx, sy, n * UP, n * UP],
            "strips": sorted({sy // rps, (sy + n * UP - 1) // rps}),
            "pixel_mismatch": int(np.count_nonzero(got_small != ref_small)),
            "max_abs_diff_u8": int(diff.max()), "mean_abs_diff_u8": round(float(diff.mean()), 6),
            "consistent": bool(int(np.count_nonzero(got_small != ref_small)) == 0),
        }
    src_mtime_after = src.stat().st_mtime

    # 写经典 TIFF（RGB 8bit + Deflate + Predictor=2，容器家法；显式 bigtiff=False）
    part = out_tif.with_name(out_tif.name + ".part")
    if part.exists():
        part.unlink()
    with tifffile.TiffWriter(part, bigtiff=False) as tw:
        tw.write(small, photometric="rgb", planarconfig="contig",
                 compression=8, predictor=2, rowsperstrip=32,
                 resolution=((PREVIEW_DPI, 1), (PREVIEW_DPI, 1)), resolutionunit="INCH",
                 software="feicui ops/book-page-2400/make_preview_8bit.py (300dpi 8bit preview)")
    os.replace(part, out_tif)

    # 写 PNG（8bit RGB，带 300dpi 元数据）
    Image.fromarray(small, mode="RGB").save(out_png, format="PNG", compress_level=6,
                                            dpi=(PREVIEW_DPI, PREVIEW_DPI))

    # 读回校验容器
    with tifffile.TiffFile(out_tif) as tf2:
        pg2 = tf2.pages[0]
        out_tags = {
            "bigtiff": bool(tf2.is_bigtiff), "shape": [int(v) for v in pg2.shape],
            "dtype": str(pg2.dtype), "compression": int(pg2.compression),
            "predictor": int(pg2.predictor), "bits_per_sample": int(pg2.bitspersample),
            "samples_per_pixel": int(pg2.samplesperpixel), "photometric": int(pg2.photometric),
            "rows_per_strip": int(pg2.rowsperstrip),
            "resolution": [int(v) for v in pg2.tags["XResolution"].value],
            "resolution_unit": str(pg2.tags["ResolutionUnit"].value),
        }
        back = pg2.asarray()
    tif_roundtrip_equal = bool(back.shape == small.shape and np.array_equal(back, small))
    with Image.open(out_png) as im:
        png_tags = {"mode": im.mode, "size": [int(v) for v in im.size],
                    "dpi": [round(float(v), 3) for v in (im.info.get("dpi") or (0, 0))]}
        png_equal = bool(np.array_equal(np.asarray(im.convert("RGB")), small))
    del page_u8
    mm_path.unlink(missing_ok=True)

    return {
        "source": {
            "path": str(src), "bytes": st.st_size, "sha256": sha256_file(src),
            "mtime": st.st_mtime, "mtime_unchanged": bool(src_mtime_after == st.st_mtime),
            "strips_decoded": n_strips_read, "container": src_tags,
            "note": "只读：仅 open('rb')，未改动 mtime",
        },
        "previews": [
            {"path": str(out_tif), "bytes": out_tif.stat().st_size, "sha256": sha256_file(out_tif),
             "magic_hex": magic_bytes(out_tif), "container": out_tags,
             "roundtrip_pixel_equal": tif_roundtrip_equal},
            {"path": str(out_png), "bytes": out_png.stat().st_size, "sha256": sha256_file(out_png),
             "magic_hex": magic_bytes(out_png), "container": png_tags,
             "roundtrip_pixel_equal": png_equal},
        ],
        "geometry": {
            "src_px": [pw, ph], "preview_px": [ow, oh], "factor": UP,
            "exact_division": bool(ow * UP == pw and oh * UP == ph),
            "src_dpi": 2400, "preview_dpi": PREVIEW_DPI,
            "mm_at_src_dpi": [round(pw / 2400 * 25.4, 3), round(ph / 2400 * 25.4, 3)],
            "mm_at_preview_dpi": [round(ow / PREVIEW_DPI * 25.4, 3), round(oh / PREVIEW_DPI * 25.4, 3)],
        },
        "geometry_check": geom_check,
        "intermediate": {
            "memmap_path": str(mm_path), "memmap_removed": bool(not mm_path.exists()),
            "u8_full_bytes": int(ph * pw * 3), "peak_hint": "逐 strip q8 写盘 memmap，未整页 float/asarray",
        },
        "elapsed_seconds": round(time.time() - t0, 2),
    }


def main(argv: list[str]) -> int:
    t0 = time.time()
    srcs = [pathlib.Path(a).resolve() for a in argv] or DEFAULT_SRCS
    for s in srcs:
        assert s.is_file(), s
    out = {
        "schema": "feicui.book-page-2400.previews-8bit.v1",
        "task": "Kong：BigTIFF 48bit 页图 → 300dpi 8bit 经典 TIFF/PNG 预览件（macOS Preview 可开）",
        "convention": {
            "bits": "q8 = clip((u16 + 128) // 257, 0, 255)（render_page_2400.py / crop_c2r1.py 同式）",
            "downsample": "cv2.INTER_AREA，整数 ÷8（2400dpi → 300dpi）",
            "memory": "strip 级流式解码（rowsperstrip=256）→ uint8 memmap，禁止整页 asarray",
            "containers": "TIFF 经典（II*）、RGB 8bit、Deflate+Predictor2、300dpi；PNG 8bit RGB 300dpi",
        },
        "items": [build_preview(s, SCRATCH) for s in srcs],
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    READINGS.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = all(
        it["source"]["mtime_unchanged"] and it["geometry"]["exact_division"]
        and it["geometry_check"]["consistent"]
        and all(p["roundtrip_pixel_equal"] for p in it["previews"])
        and not it["previews"][0]["container"]["bigtiff"]
        and it["previews"][0]["container"]["bits_per_sample"] == 8
        and it["previews"][0]["container"]["samples_per_pixel"] == 3
        for it in out["items"]
    )
    print(json.dumps({"readings": str(READINGS), "all_ok": ok,
                      "items": [{"src": it["source"]["path"], "elapsed": it["elapsed_seconds"],
                                 "previews": [{"path": p["path"], "bytes": p["bytes"],
                                               "magic": p["magic_hex"]} for p in it["previews"]],
                                 "geometry": it["geometry"], "check": it["geometry_check"]}
                                for it in out["items"]]},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
