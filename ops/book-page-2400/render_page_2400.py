#!/usr/bin/env python
"""整页高分辨率处理（**dpi 参数化**：1200 / 2400）→ 48bit RGB TIFF（Kong · ops/book-page-2400）。

口径（= Kevin 的「之前的提示词」在**整页尺度**的落地；映射表见 README §1）：

  ① 内容面（非纸底）**全冻结**：唯一像素变化 ＝ **N× Lanczos 上采样**
     （源 = PDF 内嵌 JPEG（页 29 为 xref112, 2125×3059 @300 dpi）
      ⇒ 1200 dpi ＝ 8500×12236（4×）／ 2400 dpi ＝ 17000×24472（8×））；
     印刷黑字亦冻结（**不当背景抹掉**）。
  ② 纸底类像素（近白、低饱和、非印泥）→ **程序化白色宣纸底纹**
     （固定种子、位置哈希噪声 ⇒ 与分块顺序无关、可逐像素复现；色域 `#FAFAF7`–`#FFFFFF`）。
  ③ 光影：背景**纯均匀**（无渐晕/无投影）；不对印章做光影。
  ④ 印泥微晕染：**仅掩膜外缘环带**（0.1693 mm；2400 dpi ⇒ 16 px、1200 dpi ⇒ 8 px）、α≤8%、
     取全页印泥均色；
     仅落在**新纸底**像素上（内容像素一律不动）。
  ⑤ 色彩校准：**仅印泥红像素**做色度均匀度调整（归一化色度域、保 R+G+B）
     —— 与 ① 「零色彩改动」**直接冲突**（原提示词内部矛盾，登记为待裁）；
     `--color-calib 0` 一句话关掉，默认 0.35（弱）。

**v2 实现纪律（本单收口）**：
  处理仍是**水平 strip 流式**（源流 → Lanczos → 合成），但**压缩不手写**：
  逐条 strip 结果先落一块**整页 uint16 中间缓冲**（scratch 里的 memmap ⇒ RSS 不随整页增长），
  再整块交给 `tifffile.TiffWriter.write(ndarray, compression=8, predictor=2, rowsperstrip=…)`，
  由 **tifffile 自己**切 strip、做 Predictor=2 + Deflate（多线程）。

  **为什么不再自己编码**：tifffile 2026.3.3 的 `write()` **不支持**「迭代器 yield strip 数组」
  （源码 docstring：*"Iterators of strip ndarrays are not supported"*；实测 yield (256,17000,3)
  抛 `ValueError: cannot reshape array of size … into shape (1,1,24472,17000,3)`），
  它只接受「迭代器 yield 整页数组」或「迭代器 yield 已编码 bytes」。
  而 v1 手写编码器把 Predictor 与 stripsize 契约写歪 ⇒ 块解码不匹配、文件只 379 MB。
  ⇒ 正解＝让 tifffile 独占「切 strip + predictor + deflate」这一段，本脚本只供**原始 uint16 像素**。

**v3（Kevin 2026-10-16 指令 ①）**：
  * `--dpi` 白名单 `{1200, 2400}`、**缺省 1200**；文件名 / `ImageDescription` / 读数落点 /
    分辨率 tag / 输出像素全随参数走（`P29-1200dpi-48bit.tif`）。旧版把 2400 与
    `output/book-pages/…` 写死在常量里（该目录已被拆，路径早已失效）。
  * 纹理与环带**按 mm 物理尺度定义**（`FIBER_CELL_LONG_MM` / `FIBER_CELL_SHORT_MM` /
    `HALO_BAND_MM`），由 `configure_geometry()` 按目标 dpi 换算成 px ⇒ 同一物理尺度在
    1200 与 2400 下一致（旧像素常量会让低 dpi 过密 / 高 dpi 过稀）。
  * **整本禁止**：1200 dpi 48bit 整页未压缩 ＝ 8500×12236×6 B ＝ 624 MB（deflate ≈475 MB）
    ⇒ 851 页 ≈ **404 GB**、单页 ≈27 s ⇒ **≈6.4 h**（实测算账）。本脚本**只做页级**，
    **不提供** `--pages` / 整本循环。
  * 裁件（页 29 C1-R1）改**可选**：须显式 `--crop --crop-out <路径>`；缺省只出整页图。

跑法：
    cd /Users/kevin/bistro/feicui
    ./venv/bin/python ops/book-page-2400/render_page_2400.py              # 页 29 @1200dpi（≈27 s）
    ./venv/bin/python ops/book-page-2400/render_page_2400.py --dpi 2400   # 旧产线 dpi（≈108 s）
    ./venv/bin/python ops/book-page-2400/render_page_2400.py --page 40    # 任意页（页级）
    ./venv/bin/python ops/book-page-2400/render_page_2400.py --smoke      # 小合成页自检（两 dpi）
    ./venv/bin/python ops/book-page-2400/render_page_2400.py --verify-only   # 只验证既有产物
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import resource
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf
import tifffile
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))  # `app.*` ⇒ server/app（不被仓根 app.py 遮蔽）

from app.colorcal import ink_mask as _ink_mask  # noqa: E402
from app import naming as _naming  # noqa: E402  （目录键＝config/book_dir_keys.json 唯一实现）
from app import seal_canvas as _sc  # noqa: E402  （只取常量：色域 / 种子 / α 上限，单一真源）

# ── 常量（皆单点可改）──────────────────────────────────────────────────────────────
PDF = REPO / "output" / "1_Original_PDF" / "秦印类编 检索版.pdf"   # 取阅唯一入口（旧版指 inbox/，已不存在）
PAGE = 29

#: 目标 dpi 白名单（Kevin 2026-10-16：**整页缺省 1200**，2400 保留为可选旧产线 dpi）。
#: **整本禁止**：1200dpi 48bit 整页未压缩 ＝ 8500×12236×6 B ＝ 624 MB（deflate ≈475 MB）
#: ⇒ 851 页 ≈ 404 GB、单页 ≈27 s ⇒ ≈6.4 h。页级才是可用的粒度。
DPI_WHITELIST: tuple[int, ...] = (1200, 2400)
DPI_DEFAULT = 1200                           # 缺省目标 dpi（--dpi 2400 回到旧产线）
TARGET_DPI = DPI_DEFAULT                     # 运行时当前值（configure_geometry 覆盖）
SCAN_DPI = 300                               # 源内嵌 JPEG 的实扫 dpi（由页几何派生，见 load_scan）

# —— 下列几何量由 `configure_geometry()` 按目标 dpi 现场重算（模块级可变全局）——
UP = TARGET_DPI // SCAN_DPI                  # 唯一几何变换的倍率（1200 ⇒ 4、2400 ⇒ 8）
SRC_W, SRC_H = 2125, 3059                    # 源内嵌 JPEG 像素（页 29 初值；其它页由 load_scan 现场取）
OUT_W, OUT_H = SRC_W * UP, SRC_H * UP        # 1200 ⇒ 8500×12236；2400 ⇒ 17000×24472
STRIP_OUT_ROWS = 256                         # 输出 strip 高（configure_geometry 里按 UP 对齐）
MARGIN_SRC = 8                               # 源侧重叠边（> Lanczos 核半径 3）

# 纸底判据（源分辨率）
PAPER_MIN_GRAY = 210.0
PAPER_MAX_SAT = 0.15

# ★ 物理尺度（mm）定义 —— Kevin 2026-10-16 明确批评「像素常量 ⇒ 低 dpi 过密 / 高 dpi 过稀」：
#   凡纹理 / 环带一律**以 mm 定义**，再按目标 dpi 换算成 px。锚点＝2400 dpi 下的既有像素常量
#   （纤维长轴 66 px ≈ 0.70 mm、短轴 7 px ≈ 0.07 mm、晕染环带 16 px）⇒ 换算到 mm 后，
#   任何 dpi 下都是**同一物理尺度**（1200 dpi ＝ 33 px / 3.5 px / 8 px）。
MM_PER_INCH = 25.4
FIBER_CELL_LONG_MM = 66 * MM_PER_INCH / 2400      # = 0.698550 mm
FIBER_CELL_SHORT_MM = 7 * MM_PER_INCH / 2400      # = 0.074083 mm
HALO_BAND_MM = 16 * MM_PER_INCH / 2400            # = 0.169333 mm（原 2400dpi 的 2 px × UP）

# 运行时换算值（configure_geometry 覆盖；此处初值＝缺省 dpi 下的值；float 即物理自洽，
# 晶格用浮点步长 ⇒ 1200dpi 下 3.5 px 也无取整误差）
FIBER_CELL_LONG = FIBER_CELL_LONG_MM / MM_PER_INCH * TARGET_DPI    # 2400 ⇒ 66.0；1200 ⇒ 33.0
FIBER_CELL_SHORT = FIBER_CELL_SHORT_MM / MM_PER_INCH * TARGET_DPI  # 2400 ⇒ 7.0；1200 ⇒ 3.5
HALO_BAND_OUT_PX = max(1, round(HALO_BAND_MM / MM_PER_INCH * TARGET_DPI))  # 2400 ⇒ 16；1200 ⇒ 8
HALO_ALPHA_MAX = _sc.HALO_ALPHA_MAX         # 0.08

# 宣纸底纹：色域 / 种子 / 幅度常量**复用 seal_canvas**（单一真源）
BG_SEED = _sc.BG_SEED_DEFAULT
BG_MIN_RGB = _sc.BG_MIN_RGB                 # #FAFAF7
BG_MAX_RGB = _sc.BG_MAX_RGB                 # #FFFFFF
BG_BASE_RGB = _sc.BG_BASE_RGB
BG_GRAIN_SIGMA = _sc.BG_GRAIN_SIGMA
BG_FIBER_SIGMA = _sc.BG_FIBER_SIGMA
BG_CHROMA_SIGMA = _sc.BG_CHROMA_SIGMA

COLOR_CALIB_DEFAULT = 0.35
# Σ(R+G+B) 不变量的判据容差（**浮点 0–255 域**；< 0.0039 u16 LSB）。
# 不变量在代数上恒成立，残差只是 float32 末位（相对 1e-7 × Σ ≤ 765 ⇒ ≤ 1e-4）；
# 另见 color_uniformity 对「振铃越界像素」的跳过（那些像素根本不参与换算）。
SUM_INVARIANT_TOL = 1e-3

TIFF_COMPRESSION_TAG = 8                    # Deflate（与既有 O 件同容器）
TIFF_PREDICTOR = 2
TIFF_MAXWORKERS = 4                         # 本机空闲内存偏紧 ⇒ 限 4 条压缩线程
# BigTIFF 判据（Kevin 2026-10-16）：**只有 >4 GiB 才必要**（经典 TIFF 的上限）。
#   1200dpi 整页未压缩 624 MB ⇒ 写**经典 TIFF**（macOS `sips`/`qlmanage` 能读几何、Finder 认容器）；
#   2400dpi 整页未压缩 2.33 GiB 也 < 4 GiB ⇒ 同样写经典 TIFF（实测压缩后 1.77 GiB，物理上放得下）。
BIGTIFF_THRESHOLD_BYTES = 4 * 2**30
BIGTIFF_RULE_NOTE = "auto: bigtiff = (未压缩字节 > 4 GiB)；None ⇒ 按此规则（单点可改）"


def image_description(page: int = PAGE, dpi: int | None = None) -> str:
    """TIFF `ImageDescription`：**页号与 dpi 随参数走**（旧版把 p29/2400dpi 写死在常量里）。"""
    return (f"feicui Qin Yin Lei Bian p{int(page)} {int(dpi or TARGET_DPI)}dpi 48bit RGB "
            "(ops/book-page-2400 render_page_2400.py v3)")


# 产物落点：`output/2_HighRes_PDF/<目录键>/P<页>-<dpi>dpi-48bit.tif`
#   旧常量 `output/book-pages/…` 已失效（该目录已被拆）；实际产物家＝2_HighRes_PDF/。
HIGHRES_ROOT = Path("output/2_HighRes_PDF")
CROP_BOX_300DPI = (533, 555, 798, 823)      # 页 29 的 C1-R1（**仅显式 --crop 时用**，不再默认出裁件）
SAMPLES_DIR = Path("output/samples/book-page-2400")
OPS_DIR = Path(__file__).resolve().parent


def out_rel(dir_key: str, page: int, dpi: int | None = None) -> Path:
    """产物相对路径（文件名含 dpi ⇒ 1200/2400 两版可并存、互不覆盖）。"""
    return HIGHRES_ROOT / dir_key / f"P{int(page)}-{int(dpi or TARGET_DPI)}dpi-48bit.tif"


def dir_key_of(pdf_name: str) -> str:
    """目录键（ISBN 优先）＝`config/book_dir_keys.json` 单点真源（复用 `naming.dir_key_for`）。"""
    return _naming.dir_key_for(pdf_name, _naming.load_dir_keys())


def configure_geometry(dpi: int, src_w: int, src_h: int, strip_rows: int | None = None,
                       scan_dpi: float | None = None) -> dict[str, Any]:
    """按目标 dpi 现场重算**全部几何全局量**（含 mm→px 的纹理 / 环带换算）。

    本模块唯一的几何入口：凡「随 dpi 变」的量都只能在这里被改，别处一律读全局。
    `scan_dpi` 由调用方从页几何派生（`load_scan` 的 meta）—— **别把 300 当常数**。
    返回一份 geometry 读数（进 readings JSON）。
    """
    global TARGET_DPI, UP, OUT_W, OUT_H, SRC_W, SRC_H, STRIP_OUT_ROWS, SCAN_DPI
    global FIBER_CELL_LONG, FIBER_CELL_SHORT, HALO_BAND_OUT_PX
    dpi = int(dpi)
    assert dpi in DPI_WHITELIST, f"dpi 不在白名单 {list(DPI_WHITELIST)} 内：{dpi}"
    if scan_dpi is not None:
        SCAN_DPI = int(round(float(scan_dpi)))
    assert dpi % SCAN_DPI == 0, f"目标 dpi 须为扫描 dpi({SCAN_DPI}) 的整数倍：{dpi}（只做整数倍上采样）"
    TARGET_DPI = dpi
    SRC_W, SRC_H = int(src_w), int(src_h)
    UP = TARGET_DPI // SCAN_DPI
    OUT_W, OUT_H = SRC_W * UP, SRC_H * UP
    rows = int(strip_rows or STRIP_OUT_ROWS)
    STRIP_OUT_ROWS = max(UP, (rows // UP) * UP)          # strip 高须为 UP 的整数倍
    FIBER_CELL_LONG = FIBER_CELL_LONG_MM / MM_PER_INCH * TARGET_DPI
    FIBER_CELL_SHORT = FIBER_CELL_SHORT_MM / MM_PER_INCH * TARGET_DPI
    HALO_BAND_OUT_PX = max(1, round(HALO_BAND_MM / MM_PER_INCH * TARGET_DPI))
    return {
        "target_dpi": TARGET_DPI, "scan_dpi": SCAN_DPI, "upsample_factor": UP,
        "src_px": [SRC_W, SRC_H], "out_px": [OUT_W, OUT_H], "strip_out_rows": STRIP_OUT_ROWS,
        "fiber_cell_px": [round(FIBER_CELL_LONG, 6), round(FIBER_CELL_SHORT, 6)],
        "fiber_cell_mm": [round(FIBER_CELL_LONG_MM, 6), round(FIBER_CELL_SHORT_MM, 6)],
        "halo_band_out_px": HALO_BAND_OUT_PX, "halo_band_mm": round(HALO_BAND_MM, 6),
        "raw_uncompressed_bytes": OUT_W * OUT_H * 3 * 2,
    }

M1 = np.uint64(0xBF58476D1CE4E5B9)
M2 = np.uint64(0x94D049BB133111EB)


# ── 位置哈希噪声（固定种子 ⇒ 逐像素可复现；与分块顺序无关 ⇒ 无 strip 接缝）────────────
def _mix64(x: np.ndarray) -> np.ndarray:
    x = x ^ (x >> np.uint64(30))
    x = x * M1
    x = x ^ (x >> np.uint64(27))
    x = x * M2
    return x ^ (x >> np.uint64(31))


def _hash64(rows: np.ndarray, cols: np.ndarray, seed: int, salt: int) -> np.ndarray:
    r = np.asarray(rows, dtype=np.uint64)[:, None]
    c = np.asarray(cols, dtype=np.uint64)[None, :]
    ks = (int(seed) * 0x165667B19E3779F9) % (1 << 64)
    kt = (int(salt) * 0x27D4EB2F165667C5) % (1 << 64)
    x = r * np.uint64(0x9E3779B97F4A7C15)
    x = x ^ (c * np.uint64(0xC2B2AE3D27D4EB4F))
    x = x ^ np.uint64(ks)
    x = x ^ np.uint64(kt)
    return _mix64(x)


def _u(x: np.ndarray, shift: int, bits: int) -> np.ndarray:
    return ((x >> np.uint64(shift)) & np.uint64((1 << bits) - 1)).astype(np.float64) / float(1 << bits)


# ── 处理上下文 ────────────────────────────────────────────────────────────────────
@dataclass
class Ctx:
    src: np.ndarray                     # (3059, 2125, 3) uint8
    paper_src: np.ndarray               # 源分辨率纸底掩膜
    ink_src: np.ndarray                 # 源分辨率印泥掩膜
    ink_mean_rgb: tuple[float, float, float]
    ink_chroma_mean: tuple[float, float]
    fiber_std: float
    color_calib: float
    seed: int = BG_SEED
    counters: dict[str, float] = field(default_factory=dict)


def load_scan(pdf: Path | None = None, page: int = PAGE) -> tuple[np.ndarray, int, dict[str, Any]]:
    """取该页的内嵌扫描图（纯图版页）⇒ `(src_rgb_uint8, xref, meta)`。

    旧版把 `XREF=112` 与 `2125×3059` 写死 ⇒ 只对页 29 成立。本版按页现场取：
    `page.get_images()` 的首枚 xref ＋ `doc.extract_image()` 的像素尺寸；实扫 dpi 由
    「图像宽 /(页宽 pt/72)」派生（本项目约定：只做整数倍上采样，见 configure_geometry）。
    """
    p = Path(pdf or PDF)
    doc = pymupdf.open(p)
    try:
        pg = doc[int(page) - 1]
        imgs = pg.get_images(full=True)
        if not imgs:
            raise RuntimeError(f"第 {page} 页没有内嵌图像（非纯图版页？）：{p}")
        xref = int(imgs[0][0])
        raw = doc.extract_image(xref)["image"]
        src = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
        rect = pg.rect
        meta: dict[str, Any] = {
            "pdf": str(p), "page": int(page), "xref": xref,
            "page_pt": [round(rect.width, 3), round(rect.height, 3)],
            "page_mm": [round(rect.width / 72 * 25.4, 3), round(rect.height / 72 * 25.4, 3)],
            "scan_dpi": round(src.shape[1] / (rect.width / 72.0), 6),
            "src_px": [int(src.shape[1]), int(src.shape[0])],
            "embedded_jpeg_md5": hashlib.md5(raw).hexdigest(),
            "text_layer": ("无（纯图版页）" if not pg.get_text().strip() else "有文本层"),
        }
        return src, xref, meta
    finally:
        doc.close()


def _sat_uint8(rgb: np.ndarray) -> np.ndarray:
    a = rgb.astype(np.float32)
    mx, mn = a.max(axis=2), a.min(axis=2)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)


def build_masks(src: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """返回 (paper_src, ink_src)。纸底 ＝ 近白 ∧ 低饱和 ∧ 非印泥；其余＝内容（含黑字）。"""
    ink = np.asarray(_ink_mask(src), dtype=bool)
    gray = src.astype(np.float32).mean(axis=2)
    sat = _sat_uint8(src)
    paper = (~ink) & (gray >= PAPER_MIN_GRAY) & (sat <= PAPER_MAX_SAT)
    return paper, ink


def _fiber_lattice(rows: np.ndarray, cols: np.ndarray, seed: int) -> np.ndarray:
    """各向异性 value-noise：粗晶格（短轴 FIBER_CELL_SHORT、长轴 FIBER_CELL_LONG）+ 平滑插值。"""
    gy = (rows.astype(np.float64) + 0.5) / FIBER_CELL_SHORT
    gx = (cols.astype(np.float64) + 0.5) / FIBER_CELL_LONG
    iy0 = np.floor(gy).astype(np.int64)
    ix0 = np.floor(gx).astype(np.int64)
    fy = gy - iy0
    fx = gx - ix0
    fy = fy * fy * (3.0 - 2.0 * fy)          # smoothstep ⇒ 无晶格棱
    fx = fx * fx * (3.0 - 2.0 * fx)
    # 晶格四角完全由 (iy, ix) 决定 ⇒ 与 strip 无关、逐像素可复现
    uy = np.unique(iy0)
    ux = np.unique(ix0)
    ry = np.searchsorted(uy, iy0)
    cx = np.searchsorted(ux, ix0)

    def corner(dy: int, dx: int) -> np.ndarray:
        v = _u(_hash64(uy + dy, ux + dx, seed, 7 + dy * 2 + dx), 0, 21)
        return v[ry][:, cx]
    v00, v01 = corner(0, 0), corner(0, 1)
    v10, v11 = corner(1, 0), corner(1, 1)
    top = v00 + (v01 - v00) * fx[None, :]
    bot = v10 + (v11 - v10) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def paper_strip(rows: np.ndarray, cols: np.ndarray, ctx: Ctx) -> np.ndarray:
    """程序化宣纸底纹（float32, [0,255] 域）：基色 + 纤维 + 颗粒 + 微色偏，逐通道限幅。"""
    h1 = _hash64(rows, cols, ctx.seed, 0)
    u1 = np.maximum(_u(h1, 0, 31), 1e-9)
    u2 = _u(h1, 31, 31)
    grain = (np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)).astype(np.float32)
    h2 = _hash64(rows, cols, ctx.seed, 1)
    chroma = np.stack([_u(h2, 0, 21) - 0.5, _u(h2, 21, 21) - 0.5, _u(h2, 42, 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    fiber = (_fiber_lattice(rows, cols, ctx.seed).astype(np.float32) - 0.5) / np.float32(ctx.fiber_std)
    lum = BG_FIBER_SIGMA * fiber + BG_GRAIN_SIGMA * grain
    out = (np.asarray(BG_BASE_RGB, np.float32)[None, None, :] + lum[:, :, None]
           + BG_CHROMA_SIGMA * chroma)
    lo = np.asarray(BG_MIN_RGB, np.float32)[None, None, :]
    hi = np.asarray(BG_MAX_RGB, np.float32)[None, None, :]
    return np.clip(out, lo, hi)


def lanczos_up(sub8: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """float32 域 Lanczos 上采样（逐通道 'F' 模式）⇒ 保留 8-bit 以下的中间精度。"""
    out = []
    for ch in range(sub8.shape[2]):
        im = Image.fromarray(np.ascontiguousarray(sub8[:, :, ch]).astype(np.float32), mode="F")
        out.append(np.asarray(im.resize(size, Image.Resampling.LANCZOS), dtype=np.float32))
    return np.stack(out, axis=-1)


def upsample_mask(mask8: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """二值掩膜上采样（Lanczos 后 ≥128 为 True）——与 seal_canvas.resize_mask_bool 同口径。"""
    im = Image.fromarray((mask8.astype(np.uint8) * 255), mode="L")
    return np.asarray(im.resize(size, Image.Resampling.LANCZOS)) >= 128


def halo_alpha(mask: np.ndarray, band_px: int | None = None,
               alpha_max: float = HALO_ALPHA_MAX) -> np.ndarray:
    """掩膜**外侧**环带 alpha（内 0、外 0；贴边满幅、向外线性衰减到 0）。

    `band_px` 缺省取当下的 `HALO_BAND_OUT_PX`（**调用时**解析 —— 老写法把它写成默认实参，
    在 def 那一刻就冻结成 2400dpi 的 16 px，换成 1200 dpi 会静默沿用错值）。
    """
    band_px = int(HALO_BAND_OUT_PX if band_px is None else band_px)
    inv = (~mask).astype(np.uint8)
    dist = cv2.distanceTransform(inv, cv2.DIST_L2, 3)
    a = np.where(mask, 0.0, np.clip((band_px + 1.0 - dist) / float(band_px), 0.0, 1.0) * alpha_max)
    return a.astype(np.float32)


def color_uniformity(rgb: np.ndarray, sel: np.ndarray, chroma_mean: tuple[float, float],
                     strength: float, cap: float = 255.0
                     ) -> tuple[np.ndarray, np.ndarray, int]:
    """仅 `sel`（印泥）像素：归一化色度向全页印泥均值收敛，**严格保 R+G+B**。

    **逐像素有界强度**：`t ≤ strength`，且取「不使任一通道越出 [0, cap]」的最大可行值
    ⇒ ① 不会把通道推过 255（否则裁剪会破坏 R+G+B 守恒）；② 方向不变（仍是向均色收敛），
    只是对偏离均色过远的浅色印泥像素自动减弱。

    **有效域闸（v2.1 修）**：归一化色度 `c = px/Σpx` 只在「各通道 ∈ [0, cap] ∧ Σ > 0」的像素上
    有定义。8× Lanczos 在强边缘**振铃越界**（通道 >255 或 <0，Σ 甚至可为负 —— 实测 smoke
    合成页最坏像素 `(-24.5, -26.9, 16.1)`，Σ = −35.4）⇒ 旧写法把 Σ 夹到 1e-6 后 `c` 放大到
    ~1e7，float32 精度崩掉、Σ 守恒从 ~1e-4 恶化到 **12.39**（实测）。这类像素**不参与换算**
    （`t = 0`、逐像素原样返回），并在读数里单独计数。
    返回 (rgb, 各像素实际强度 t, 被跳过（有效域外）的像素数)。
    """
    if strength <= 0 or not sel.any():
        return rgb, np.zeros(0, dtype=np.float32), 0
    px = rgb[sel].astype(np.float32)
    s0 = px.sum(axis=1, keepdims=True)
    valid = (px >= 0.0).all(axis=1) & (px <= cap).all(axis=1) & (s0[:, 0] > 1e-6)
    n_invalid = int((~valid).sum())
    s = np.where(valid[:, None], s0, np.float32(1.0))     # 无效像素：s=1 ⇒ c=px ⇒ 输出恒等
    c = px / s
    tgt = np.asarray([chroma_mean[0], chroma_mean[1], 1.0 - chroma_mean[0] - chroma_mean[1]],
                     np.float32)
    tgt = np.clip(tgt, 0.0, None)
    tgt = tgt / max(float(tgt.sum()), 1e-9)
    d = tgt[None, :] - c
    t = np.full((px.shape[0], 1), np.float32(strength))
    with np.errstate(divide="ignore", invalid="ignore"):
        hib = np.where(d > 0, (cap - s * c) / (s * d), np.inf)      # 上界：c + t·d ≤ cap/s
        lob = np.where(d < 0, c / (-d), np.inf)                     # 下界：c + t·d ≥ 0
    t = np.minimum(t, np.minimum(hib, lob).min(axis=1, keepdims=True))
    t = np.clip(t, 0.0, float(strength))
    t = np.where(valid[:, None], t, 0.0)
    out = (s * (c + t * d)).astype(np.float32)
    rgb = rgb.copy()
    rgb[sel] = out
    return rgb, t[:, 0].astype(np.float32), n_invalid


def to_u16(f: np.ndarray) -> np.ndarray:
    """float32 [0,255] → uint16（×257 满量程；唯一量化式，全脚本共用）。"""
    return np.rint(np.clip(f, 0.0, 255.0) * np.float32(257.0)).astype(np.uint16)


def q8(u16: np.ndarray) -> np.ndarray:
    """48bit → 8bit 的**固定可逆约定**：q8 = round(v / 257)（|v/257 − q8| ≤ 0.5）。"""
    return np.clip((u16.astype(np.uint32) + 128) // 257, 0, 255).astype(np.uint8)


def _strip_span(y0: int, y1: int, src_h: int, up: int | None = None,
                margin: int = MARGIN_SRC) -> tuple[int, int, int]:
    """输出行 [y0,y1)（须 UP 对齐）⇒ 源行窗口 [s0,s1) 与其在窗口内的输出偏移。"""
    up = int(UP if up is None else up)      # **调用时**解析（默认实参会在 def 时冻结成 2400dpi 的 8）
    s0 = max(0, y0 // up - margin)
    s1 = min(src_h, -(-y1 // up) + margin)
    return s0, s1, (y0 // up - s0) * up


def strip_layers(y0: int, y1: int, ctx: Ctx) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """输出行 [y0,y1) 的 (lanczos_f32, paper, ink, halo_alpha)。

    **邻域运算全在扩展窗口上做**（窗口 = 目标行 ± `MARGIN_SRC` 源行 = ±64 输出行 > 晕染环带
    16 px），**切到目标行之后**再返回 ⇒ 与 strip 切分无关、无接缝（`--smoke` 自证）。
    halo ＝ 掩膜**外侧**环带 alpha，且只落在纸底像素上（`paper` 为 0 处恒 0）。
    """
    s0, s1, off = _strip_span(y0, y1, ctx.src.shape[0])
    sub = ctx.src[s0:s1]
    oh, ow = (s1 - s0) * UP, OUT_W
    inner = slice(off, off + (y1 - y0))
    lun = lanczos_up(sub, (ow, oh))
    paper_ext = upsample_mask(ctx.paper_src[s0:s1], (ow, oh))
    ink_ext = upsample_mask(ctx.ink_src[s0:s1], (ow, oh))
    # 掩膜**互斥化**：印泥优先（两枚掩膜各自 Lanczos 上采样后可在同一像素同时为真）
    paper_ext &= ~ink_ext
    halo_ext = np.where(paper_ext, halo_alpha(ink_ext, HALO_BAND_OUT_PX), np.float32(0.0))  # ← 窗口上算，再切
    return lun[inner], paper_ext[inner], ink_ext[inner], halo_ext[inner]


def synthesize(y0: int, y1: int, ctx: Ctx,
               layers: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None,
               collect: bool = False
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """量化前的合成结果 ⇒ (big_f32, paper, ink, halo, t_calib)。

    ② 纸底像素写程序化宣纸底纹；④ 外缘环带微晕染（仅落在纸底）；⑤ 印泥色度校准（逐像素有界）。
    非纸底 ∧ 非印泥像素**原样**返回 clip 前的 Lanczos 值（唯一变更＝8× Lanczos）。
    """
    if layers is None:
        layers = strip_layers(y0, y1, ctx)
    lun, paper, ink, halo = layers
    big = lun.copy()
    rows_idx = np.arange(y0, y1, dtype=np.int64)
    np.copyto(big, paper_strip(rows_idx, np.arange(OUT_W, dtype=np.int64), ctx),
              where=paper[:, :, None])
    if halo.any():
        col = np.asarray(ctx.ink_mean_rgb, np.float32)[None, None, :]
        big *= (1.0 - halo[:, :, None])
        big += col * halo[:, :, None]
    t = np.zeros(0, dtype=np.float32)
    if ctx.color_calib > 0 and ink.any():
        big, t, n_invalid = color_uniformity(big, ink, ctx.ink_chroma_mean, ctx.color_calib)
        ctx.counters["calib_skipped_invalid_px"] = (
            ctx.counters.get("calib_skipped_invalid_px", 0.0) + float(n_invalid))
    if collect:
        ctx.counters["paper_px"] = ctx.counters.get("paper_px", 0) + float(paper.sum())
        ctx.counters["ink_px"] = ctx.counters.get("ink_px", 0) + float(ink.sum())
        ctx.counters["content_px"] = ctx.counters.get("content_px", 0) + float((~paper & ~ink).sum())
        ctx.counters["out_px"] = ctx.counters.get("out_px", 0) + float(paper.size)
        if t.size:
            at_cap = float((t >= ctx.color_calib - 1e-6).sum())
            ctx.counters["calib_px"] = ctx.counters.get("calib_px", 0) + float(t.size)
            ctx.counters["calib_t_sum"] = ctx.counters.get("calib_t_sum", 0.0) + float(t.sum())
            ctx.counters["calib_t_at_cap"] = ctx.counters.get("calib_t_at_cap", 0.0) + at_cap
            ctx.counters["calib_t_max"] = max(ctx.counters.get("calib_t_max", 0.0), float(t.max()))
    return big, paper, ink, halo, t


def process_strip(y0: int, y1: int, ctx: Ctx,
                  crop_box: tuple[int, int, int, int] | None = None
                  ) -> tuple[np.ndarray, int | None, np.ndarray | None]:
    """处理输出行 [y0,y1) ⇒ (u16, oy0, overlap_u16)。

    `overlap_u16` ＝ 本 strip 与裁件行带 [cy0,cy1) 的**交集**（**16bit 原样**，裁件的 8bit 量化
    由调用方按同一 `q8()` 式做 ⇒ 裁件与页图逐像素可核）；`oy0` ＝ 该交集的全局首行。
    无交集 ⇒ `(u16, None, None)`。

    **接缝无关性**：所有邻域运算（掩膜上采样、晕染）都在**扩展窗口**上做，
    窗口比目标行多 `MARGIN_SRC` 源行（= 64 输出行 > 晕染环带 16 px）⇒
    结果与「整幅一次算」逐像素相等（`--smoke` 自证）。
    """
    big, _paper, ink, _halo, _t = synthesize(y0, y1, ctx, collect=True)
    u16 = to_u16(big)
    oy0: int | None = None
    overlap = None
    if crop_box is not None:
        cy0, cy1, cx0, cx1 = crop_box
        iy0, iy1 = max(y0, cy0), min(y1, cy1)
        if iy0 < iy1:
            oy0 = iy0
            overlap = u16[iy0 - y0:iy1 - y0, cx0:cx1]
    return u16, oy0, overlap


# ── 写盘（唯一写 TIFF 的入口）───────────────────────────────────────────────────────
def write_tiff(arr: np.ndarray, path: Path, *, rowsperstrip: int, description: str,
               resolution_dpi: int | None = None, predictor: int = TIFF_PREDICTOR,
               bigtiff: bool | None = None) -> dict[str, Any]:
    """tifffile 独占「切 strip + Predictor + Deflate」；原子写（`*.part` → `os.replace`）。

    `resolution_dpi` 缺省取当下的 `TARGET_DPI`（**调用时**解析；老写法把 2400 冻结在默认实参里）。

    **BigTIFF 按尺寸自动**（Kevin 2026-10-16）：`bigtiff=None` ⇒
    `未压缩字节 > 4 GiB`（经典 TIFF 的 4 GiB 上限）才用 BigTIFF，否则写**经典 TIFF**。
    为什么在意：BigTIFF 在 macOS Finder/Preview **一律不认**（旧版无故把 1200dpi 也写成 BigTIFF），
    而经典 TIFF 至少能被 `sips`/`qlmanage` 读到几何 —— 1200dpi 产物体积只有 ~0.45 GiB，远不需要 BigTIFF。
    """
    resolution_dpi = int(TARGET_DPI if resolution_dpi is None else resolution_dpi)
    if bigtiff is None:
        bigtiff = bool(arr.nbytes > BIGTIFF_THRESHOLD_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    if part.exists():
        part.unlink()
    t0 = time.time()
    with tifffile.TiffWriter(part, bigtiff=bool(bigtiff)) as tw:
        tw.write(arr, shape=arr.shape, dtype=arr.dtype, photometric="rgb", planarconfig="contig",
                 compression=TIFF_COMPRESSION_TAG, predictor=predictor, rowsperstrip=rowsperstrip,
                 resolution=((resolution_dpi, 1), (resolution_dpi, 1)), resolutionunit="INCH",
                 software="feicui ops/book-page-2400 render_page_2400.py",
                 description=description, maxworkers=TIFF_MAXWORKERS)
    os.replace(part, path)
    return {"path": str(path), "bytes": int(path.stat().st_size), "bigtiff": bool(bigtiff),
            "bigtiff_rule": BIGTIFF_RULE_NOTE, "write_seconds": round(time.time() - t0, 2)}


def read_segment(page: tifffile.TiffPage, index: int) -> np.ndarray:
    """按段解码（**不**手写逆 predictor；走 tifffile 自己的 decode）。"""
    fh = page.parent.filehandle
    fh.seek(page.dataoffsets[index])
    raw = fh.read(page.databytecounts[index])
    return page.decode(raw, index)[0][0]


def container_tags(path: Path) -> dict[str, Any]:
    with tifffile.TiffFile(path) as tf:
        pg = tf.pages[0]
        t = pg.tags
        return {
            "shape": list(pg.shape), "dtype": str(pg.dtype),
            "bits_per_sample": int(pg.bitspersample),
            "bits_per_pixel": int(pg.bitspersample) * int(pg.samplesperpixel),
            "samples_per_pixel": int(pg.samplesperpixel),
            "compression": int(pg.compression), "predictor": int(pg.predictor),
            "photometric": int(pg.photometric), "planarconfig": int(pg.planarconfig),
            "rowsperstrip": int(pg.rowsperstrip), "tiled": bool(pg.is_tiled),
            "strips": int(len(pg.dataoffsets)), "bigtiff": bool(tf.is_bigtiff),
            "software": str(t["Software"].value) if "Software" in t else None,
            "description": str(pg.description).strip(),
            "x_resolution": (list(t["XResolution"].value) if "XResolution" in t else None),
            "resolution_unit": int(t["ResolutionUnit"].value) if "ResolutionUnit" in t else None,
            "page_count": int(len(tf.pages)),
        }


# ── 主流程 ────────────────────────────────────────────────────────────────────────
def render_page(ctx: Ctx, out_path: Path, *, strip_rows: int | None = None,
                crop_box: tuple[int, int, int, int] | None = None, crop_bits: int = 8,
                scratch_dir: Path | None = None, progress_path: Path | None = None,
                description: str | None = None,
                ) -> dict[str, Any]:
    """流式处理整页 → scratch memmap → tifffile 自压 → 原子换入；同时取裁件与预览。"""
    strip_rows = int(STRIP_OUT_ROWS if strip_rows is None else strip_rows)   # 调用时解析（别冻结 dpi 相关量）
    total_h = OUT_H
    bounds = [(y, min(y + strip_rows, total_h)) for y in range(0, total_h, strip_rows)]
    t0 = time.time()
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    scratch = Path(tempfile.mkdtemp(prefix="p29-2400-", dir=str(scratch_dir) if scratch_dir else None))
    raw_path = scratch / "page-u16.raw"
    progress = open(progress_path, "a", encoding="utf-8") if progress_path else None

    crop = None
    filled = None
    if crop_box is not None:
        cy0, cy1, cx0, cx1 = crop_box
        crop = np.zeros((cy1 - cy0, cx1 - cx0, 3), dtype=np.uint8 if crop_bits == 8 else np.uint16)
        filled = np.zeros(cy1 - cy0, dtype=bool)

    prev_rows: list[np.ndarray] = []
    strip_stats: list[dict[str, Any]] = []
    mm = np.memmap(raw_path, dtype=np.uint16, mode="w+", shape=(total_h, OUT_W, 3))
    try:
        for i, (y0, y1) in enumerate(bounds):
            ts = time.time()
            u16, oy0, overlap = process_strip(y0, y1, ctx, crop_box if crop is not None else None)
            mm[y0:y1] = u16                                    # 原始 uint16 落中间缓冲
            if overlap is not None and crop is not None:
                s = oy0 - crop_box[0]
                band = q8(overlap) if crop_bits == 8 else overlap
                assert s >= 0 and s + band.shape[0] <= crop.shape[0], (y0, y1, oy0, band.shape)
                crop[s:s + band.shape[0]] = band               # 裁件按交集落位
                filled[s:s + band.shape[0]] = True
            prev_rows.append(u16[::16, ::16].copy())
            dt = round(time.time() - ts, 3)
            strip_stats.append({"strip": i, "y0": y0, "y1": y1, "seconds": dt})
            if progress:
                progress.write(json.dumps({"strip": i, "of": len(bounds), "y0": y0, "y1": y1,
                                           "seconds": dt, "elapsed_s": round(time.time() - t0, 1),
                                           "crop_rows_filled": int(filled.sum()) if filled is not None else None}
                                          , ensure_ascii=False) + "\n")
                progress.flush()
            del u16, overlap
        mm.flush()
        proc_seconds = round(time.time() - t0, 2)
        del mm
        # tifffile 自己切 strip + Predictor=2 + Deflate（多线程）
        page_w = write_tiff(np.memmap(raw_path, dtype=np.uint16, mode="r", shape=(total_h, OUT_W, 3)),
                            out_path, rowsperstrip=strip_rows,
                            description=description or image_description())
    finally:
        if progress:
            progress.close()
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)

    res: dict[str, Any] = {
        "out_path": page_w["path"], "out_bytes": page_w["bytes"],
        "shape": [total_h, OUT_W, 3], "dtype": "uint16", "bits_per_pixel": 48,
        "rowsperstrip": strip_rows, "strips": len(bounds), "strip_stats": strip_stats,
        "processing_seconds": proc_seconds, "write_seconds": page_w["write_seconds"],
        "elapsed_s": round(time.time() - t0, 2),
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "peak_rss_bytes_before_write": int(rss0),
        "scratch": str(scratch),
    }
    if crop is not None:
        res["crop"] = crop
        res["crop_rows_filled"] = int(filled.sum())
        res["crop_rows_total"] = int(filled.size)
        res["crop_fully_covered"] = bool(filled.all())
    if prev_rows:
        res["preview"] = np.concatenate(prev_rows, axis=0)
    return res


def build_ctx(src: np.ndarray, color_calib: float) -> Ctx:
    paper, ink = build_masks(src)
    ink_px = src[ink].astype(np.float64)
    ink_mean = tuple(float(v) for v in ink_px.mean(axis=0)) if ink_px.size else (0.0, 0.0, 0.0)
    tot = np.maximum(ink_px.sum(axis=1, keepdims=True), 1.0)
    ch = (ink_px / tot).mean(axis=0)[:2] if ink_px.size else (1 / 3, 1 / 3)
    probe_rows = np.arange(0, 1024, dtype=np.int64)
    probe_cols = np.arange(0, 1024, dtype=np.int64)
    fib = _fiber_lattice(probe_rows, probe_cols, BG_SEED).astype(np.float64) - 0.5
    return Ctx(src=src, paper_src=paper, ink_src=ink,
               ink_mean_rgb=ink_mean, ink_chroma_mean=(float(ch[0]), float(ch[1])),
               fiber_std=float(fib.std()), color_calib=color_calib)


def mm_from_px(px: float, dpi: float) -> float:
    return px / dpi * 25.4


# ── 验证（读回：只走 tifffile 自己的解码）──────────────────────────────────────────
def verify(out_path: Path, crop_path: Path | None, ctx: Ctx, *, crop_bits: int = 8,
           limit: int | None = None, seed: int = 20261013,
           crop_box: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
    tags = container_tags(out_path)
    H, W = tags["shape"][0], tags["shape"][1]
    nstrips = tags["strips"]
    idxs = list(range(nstrips)) if limit in (None, 0) else sorted(
        np.random.default_rng(seed).choice(nstrips, size=min(limit, nstrips), replace=False).tolist())

    tot_px = 0
    eq_mismatch = 0
    # 计数（realized_strength / 面积占比）只反映**本次验证重算**：全 96 strip ⇒ 整页口径
    ctx.counters.clear()
    max_abs = 0
    content_px = 0
    content_mismatch = 0
    content_max_abs = 0
    ink_px = 0
    ink_max_abs = 0
    ink_sum_jump_max = 0
    ink_sum_float_jump_max = 0.0
    ring_px = 0
    ring_max = 0.0
    paper_px = 0
    paper_out_of_range = 0
    paper_out_of_range_outside_halo = 0
    paper_min = [255, 255, 255]
    paper_max = [0, 0, 0]
    ink_changed = 0
    ink_over: dict[str, int] = {}
    checked_rows = 0
    with tifffile.TiffFile(out_path) as tf:
        page = tf.pages[0]
        for i in idxs:
            got = read_segment(page, i)
            y0, y1 = i * tags["rowsperstrip"], min((i + 1) * tags["rowsperstrip"], H)
            n = got.shape[0]
            layers = strip_layers(y0, min(y1, H), ctx)
            big, paper, ink, halo_raw, _t = synthesize(y0, min(y1, H), ctx, layers=layers, collect=True)
            want = to_u16(big)[:n]                                  # 同一代码路径的重算
            diff = np.abs(got.astype(np.int32) - want.astype(np.int32))
            eq_mismatch += int((diff != 0).sum())
            max_abs = max(max_abs, int(diff.max()))
            # 独立冻结判据：非纸底 ∧ 非印泥 ⇒ 必须逐像素 == clip(8× Lanczos)
            lun_f = layers[0][:n]
            paper = paper[:n]
            ink = ink[:n]
            halo = halo_raw[:n] > 0
            lun = to_u16(lun_f)
            content = ~paper & ~ink
            d2 = np.abs(got.astype(np.int32) - lun.astype(np.int32))
            content_px += int(content.sum())
            content_mismatch += int((d2[content] != 0).sum())
            if content.any():
                content_max_abs = max(content_max_abs, int(d2[content].max()))
            # Lanczos 振铃越界（源 8bit 饱和 ⇒ 浮点越出 [0,255]，量化时必须裁剪）——登记项
            ring = (lun_f < 0.0) | (lun_f > 255.0)
            ring_px += int(ring.any(axis=2).sum())
            if ring.any():
                excess = np.maximum(0.0, lun_f - 255.0).max() if (lun_f > 255.0).any() else 0.0
                below = abs(min(0.0, float(lun_f.min())))
                ring_max = max(ring_max, float(excess), float(below))
            # 印泥：只允许 ⑤ 色度校准 ⇒ 逐通道最大偏差、浮点域 Σ 守恒、store 域 Σ 差
            if ink.any():
                gi = got[ink].astype(np.int32)
                wi = lun[ink].astype(np.int32)
                di = np.abs(gi - wi)
                ink_px += int(ink.sum())
                ink_max_abs = max(ink_max_abs, int(di.max()))
                ink_sum_jump_max = max(ink_sum_jump_max,
                                       int(np.abs(gi.sum(axis=1) - wi.sum(axis=1)).max()))
                # ⑤ 的代数不变量：逐像素 Σ(R,G,B) 在**浮点域**严格不变
                ink_sum_float_jump_max = max(ink_sum_float_jump_max, float(np.abs(
                    big[ink].astype(np.float64).sum(axis=1) - lun_f[ink].astype(np.float64).sum(axis=1)).max()))
                ink_changed += int((di.max(axis=1) != 0).sum())
                for thr in (257, 1285, 2570, 5140, 10280):
                    ink_over[f"{thr}"] = ink_over.get(f"{thr}", 0) + int((di > thr).any(axis=1).sum())
            # 纸底：色域应落 #FAFAF7–#FFFFFF（晕染环带内的像素是设计内的例外，单独计）
            if paper.any():
                gp = got[paper]
                paper_px += int(paper.sum())
                paper_min = [min(paper_min[c], int(gp[:, c].min())) for c in range(3)]
                paper_max = [max(paper_max[c], int(gp[:, c].max())) for c in range(3)]
                lo = np.asarray(BG_MIN_RGB, np.int32) * 257
                hi = np.asarray(BG_MAX_RGB, np.int32) * 257
                out_of = ((gp.astype(np.int32) < lo) | (gp.astype(np.int32) > hi)).any(axis=1)
                paper_out_of_range += int(out_of.sum())
                paper_out_of_range_outside_halo += int((out_of & ~halo[paper]).sum())
            tot_px += int(got.size // 3)
            checked_rows += int(got.shape[0])
            del got, want, lun, paper, ink

    out: dict[str, Any] = {
        "container": tags,
        "out_bytes": int(out_path.stat().st_size),
        "out_gib": round(out_path.stat().st_size / 2**30, 3),
        "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest() if False else _sha256_file(out_path),
        "strips_checked": len(idxs), "strips_total": nstrips, "rows_checked": checked_rows,
        "pixels_checked": tot_px,
        "roundtrip": {"decode_vs_recompute_mismatch_px": eq_mismatch, "max_abs_diff_u16": max_abs},
        "freeze": {
            "rule": "非纸底 ∧ 非印泥（含印刷黑字/图形）⇒ 逐像素 == clip(8× Lanczos)",
            "pixels": content_px, "mismatch_px": content_mismatch,
            "max_abs_diff_u16": content_max_abs,
            "lanczos_ringing": {
                "pixels_float_out_of_8bit_range": ring_px,
                "max_overshoot_8bit_units": round(ring_max, 3),
                "note": ("8× Lanczos 在源 8bit 饱和处产生振铃越界（>255 或 <0）⇒ 量化进 16bit "
                         "（v = round(c·257)）时按通道裁剪；属『Lanczos + 量化』固有，非额外处理"),
            },
        },
        "ink_colorcalib": {
            "rule": ("仅印泥像素、归一化色度向全页均值收敛、逐像素有界强度；⑤ 与 ①「内容零色彩改动」"
                     "冲突 · 登记为待裁"),
            "strength_requested": round(float(ctx.color_calib), 4),
            "pixels": ink_px, "changed_px": ink_changed,
            "max_abs_diff_u16": ink_max_abs,
            "max_abs_diff_8bit_equiv": round(ink_max_abs / 257.0, 2),
            "max_abs_sum_RGB_jump_float": ink_sum_float_jump_max,
            "sum_invariant_tolerance_float": SUM_INVARIANT_TOL,
            "skipped_invalid_domain_px": int(ctx.counters.get("calib_skipped_invalid_px", 0)),
            "skipped_invalid_domain_note": (
                "Lanczos 振铃越界像素（任一通道 >255 或 <0，Σ 可 ≤0）不参与色度换算 "
                "⇒ 归一化不是良定义；这些像素 t=0、逐像素原样保留"),
            "max_abs_sum_RGB_jump_u16_store": ink_sum_jump_max,
            "sum_jump_u16_note": ("store 域 Σ 差只出现在『Lanczos 振铃越界被裁剪』的像素上："
                                  "裁剪后 R 已顶 65535/G,B 已触 0，再叠加校准必然改变 Σ —— "
                                  "浮点域 Σ 在有效域像素上代数恒成立（|Δ| ≤ tol，残差＝float32 末位）"),
            "px_over_abs_diff_u16": ink_over,
            "realized_strength": {
                "mean": round(ctx.counters.get("calib_t_sum", 0.0) / max(1.0, ctx.counters.get("calib_px", 1)), 5),
                "max": round(ctx.counters.get("calib_t_max", 0.0), 5),
                "px_at_cap": int(ctx.counters.get("calib_t_at_cap", 0)),
                "note": "逐像素 t ≤ strength；t 取『不使任一通道越出 [0,255]』的最大可行值",
            },
        },
        "paper_background": {
            "declared_range_rgb": [list(BG_MIN_RGB), list(BG_MAX_RGB)],
            "observed_min_u16": paper_min, "observed_max_u16": paper_max,
            "observed_min_u8_round": [int(round(v / 257)) for v in paper_min],
            "observed_max_u8_round": [int(round(v / 257)) for v in paper_max],
            "pixels": paper_px,
            "outside_declared_range_px": paper_out_of_range,
            "outside_declared_range_and_outside_halo_px": paper_out_of_range_outside_halo,
            "note": "晕染环带（外缘 16 px、α≤8%、向印泥均色收敛）内的纸底像素**按设计**可越出 #FAFAF7–#FFFFFF 下限",
        },
    }
    if crop_path is not None and crop_path.exists() and crop_box is not None:
        cy0, cy1, cx0, cx1 = crop_box
        ctags = container_tags(crop_path)
        crop_img = tifffile.imread(crop_path)
        mism = 0
        rows = []
        with tifffile.TiffFile(out_path) as tf:
            page = tf.pages[0]
            rps = tags["rowsperstrip"]
            for i in range(cy0 // rps, (cy1 - 1) // rps + 1):
                y0, y1 = i * rps, min((i + 1) * rps, H)
                got = read_segment(page, i)
                iy0, iy1 = max(y0, cy0), min(y1, cy1)
                if iy0 >= iy1:
                    continue
                ref = got[iy0 - y0:iy1 - y0, cx0:cx1]
                ref = q8(ref) if crop_bits == 8 else ref
                mine = crop_img[iy0 - cy0:iy1 - cy0]
                d = (mine.astype(np.int32) - ref.astype(np.int32))
                mism += int((d != 0).sum())
                rows.append({"strip": i, "rows": int(ref.shape[0]), "max_abs_diff": int(np.abs(d).max())})
                del got, ref
        out["crop"] = {
            "path": str(crop_path), "bytes": int(crop_path.stat().st_size),
            "sha256": _sha256_file(crop_path),
            "container": ctags,
            "quantizer": ("q8 = round(page_u16 / 257)（固定、可逆：|page/257 − q8| ≤ 0.5）"
                          if crop_bits == 8 else "16bit 原样拷贝（与页图逐位相同）"),
            "vs_page_mismatch_px": mism,
            "pixels": int(crop_img.shape[0] * crop_img.shape[1]),
            "per_strip": rows,
            "bbox_2400dpi": [cx0, cy0, cx1, cy1],
            "size_px": [int(crop_img.shape[1]), int(crop_img.shape[0])],
            "size_mm_from_target_dpi": [round(mm_from_px(crop_img.shape[1], TARGET_DPI), 3),
                                        round(mm_from_px(crop_img.shape[0], TARGET_DPI), 3)],
            "size_mm_from_300dpi_bbox": [
                round(mm_from_px(CROP_BOX_300DPI[2] - CROP_BOX_300DPI[0], SCAN_DPI), 3),
                round(mm_from_px(CROP_BOX_300DPI[3] - CROP_BOX_300DPI[1], SCAN_DPI), 3)],
        }
    return out


def _sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ── CLI ───────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(PDF), help="源 PDF（缺省＝output/1_Original_PDF/秦印类编 检索版.pdf）")
    ap.add_argument("--page", type=int, default=PAGE, help="PDF 页号（1-based，↔ stamps.page）")
    ap.add_argument("--dpi", type=int, default=DPI_DEFAULT, choices=list(DPI_WHITELIST),
                    help=f"目标 dpi，白名单 {list(DPI_WHITELIST)}（缺省 {DPI_DEFAULT}）")
    ap.add_argument("--out", default=None,
                    help="产物落点（缺省 output/2_HighRes_PDF/<目录键>/P<页>-<dpi>dpi-48bit.tif）")
    ap.add_argument("--strip-rows", type=int, default=STRIP_OUT_ROWS, help="输出 strip 高（按 UP 对齐）")
    ap.add_argument("--color-calib", type=float, default=COLOR_CALIB_DEFAULT,
                    help="印泥色度均匀度强度（0 = 完全冻结，不跑色彩校准）")
    ap.add_argument("--crop", action="store_true",
                    help="另出页 29 C1-R1 裁件（**须同时给 --crop-out**；缺省不出裁件）")
    ap.add_argument("--crop-out", default=None, help="裁件落点（--crop 时必给）")
    ap.add_argument("--crop-box-300dpi", type=int, nargs=4, default=list(CROP_BOX_300DPI),
                    metavar=("X1", "Y1", "X2", "Y2"), help="裁件 bbox（**300dpi 源坐标**）")
    ap.add_argument("--crop-bits", type=int, default=8, choices=(8, 16),
                    help="裁件位深：8 = 与既有 O 件同容器；16 = 与页图逐位相同")
    ap.add_argument("--scratch", default=None, help="中间缓冲目录（默认系统临时目录）")
    ap.add_argument("--progress", default=None, help="进度 JSONL 落点（长跑用）")
    ap.add_argument("--readings", default=None,
                    help="读数 JSON 落点（缺省 ops/book-page-2400/readings-P<页>-<dpi>dpi-48bit.json）")
    ap.add_argument("--samples", action="store_true", help="另存人看预览（缩略/裁件/1:1 窗口）")
    ap.add_argument("--verify-strips", type=int, default=0, help="验证抽样条数（0 = 全页逐条）")
    ap.add_argument("--verify-seed", type=int, default=20261013)
    ap.add_argument("--verify-only", action="store_true", help="不渲染，只验证既有产物")
    ap.add_argument("--smoke", action="store_true", help="小合成页自检（不读 PDF、不出正式产物；两 dpi 各一遍）")
    args = ap.parse_args(argv)

    if args.smoke:
        return _smoke()

    # ---- 源 / 几何 / 落点（**页级**：页与 dpi 都从参数来，不再写死页 29 / 2400）----
    pdf_path = Path(args.pdf)
    page = int(args.page)
    src, xref, src_meta = load_scan(pdf_path, page)
    geom = configure_geometry(args.dpi, src_meta["src_px"][0], src_meta["src_px"][1],
                              args.strip_rows, src_meta["scan_dpi"])
    dir_key = dir_key_of(pdf_path.name)
    out_path = Path(args.out) if args.out else REPO / out_rel(dir_key, page, args.dpi)
    readings_path = (Path(args.readings) if args.readings
                     else OPS_DIR / f"readings-P{page}-{args.dpi}dpi-48bit.json")
    if args.crop and not args.crop_out:
        raise SystemExit("--crop 必须同时给 --crop-out（缺省不出裁件：旧落点 output/book-pages/ 已被拆）")
    crop_path = Path(args.crop_out) if args.crop_out else None
    crop_box = None
    crop_px: list[int] = []
    if crop_path is not None:
        cx0, cy0, cx1, cy1 = (args.crop_box_300dpi[0] * UP, args.crop_box_300dpi[1] * UP,
                              args.crop_box_300dpi[2] * UP, args.crop_box_300dpi[3] * UP)
        crop_box = (cy0, cy1, cx0, cx1)
        crop_px = [cx0, cy0, cx1, cy1]
    ctx = build_ctx(src, args.color_calib)

    readings: dict[str, Any] = {
        "schema": "feicui.book-page-2400.readings.v3",
        "generator": "ops/book-page-2400/render_page_2400.py",
        "page": page,
        "dir_key": dir_key, "out_path": str(out_path),
        "out_rel": (str(out_path.relative_to(REPO)) if str(out_path).startswith(str(REPO)) else str(out_path)),
        "source": dict(src_meta, pdf=str(pdf_path), dpi=SCAN_DPI, size_px=src_meta["src_px"]),
        "geometry": geom,
        "params": {
            "scan_dpi": SCAN_DPI, "target_dpi": TARGET_DPI, "upsample_factor": UP,
            "source_px": [SRC_W, SRC_H], "output_px": [OUT_W, OUT_H],
            "bit_depth": 48, "samples_per_pixel": 3, "bits_per_sample": 16,
            "container": {"compression_tag": TIFF_COMPRESSION_TAG, "predictor": TIFF_PREDICTOR,
                          "photometric": "rgb", "planarconfig": "contig", "bigtiff": True},
            "encoder": "tifffile 自带 deflate+predictor（本脚本只供原始 uint16 像素）",
            "strip_out_rows": STRIP_OUT_ROWS, "margin_src_rows": MARGIN_SRC,
            "paper_rule": {"min_gray": PAPER_MIN_GRAY, "max_sat": PAPER_MAX_SAT},
            "paper_texture": {"seed": BG_SEED, "colour_range_rgb": [list(BG_MIN_RGB), list(BG_MAX_RGB)],
                              "base_rgb": list(BG_BASE_RGB), "grain_sigma": BG_GRAIN_SIGMA,
                              "fiber_sigma": BG_FIBER_SIGMA, "chroma_sigma": BG_CHROMA_SIGMA,
                              "fiber_cell_px": [FIBER_CELL_LONG, FIBER_CELL_SHORT],
                              "fiber_cell_mm": [FIBER_CELL_LONG_MM, FIBER_CELL_SHORT_MM],
                              "scale_rule": ("纹理一律 **mm 物理尺度**定义、按目标 dpi 换算 px "
                                             "（Kevin 2026-10-16：旧的像素常量会让低 dpi 过密 / 高 dpi 过稀）"),
                              "fiber_std_probe": round(ctx.fiber_std, 6),
                              "noise": "numpy uint64 splitmix64 位置哈希（与分块顺序无关）"},
            "halo": {"band_out_px": HALO_BAND_OUT_PX, "band_mm": HALO_BAND_MM,
                     "alpha_max": HALO_ALPHA_MAX,
                     "colour_rgb": [round(v, 3) for v in ctx.ink_mean_rgb],
                     "restricted_to_paper": True},
            "color_calib": {"strength": args.color_calib,
                            "mode": "归一化色度向全页印泥均值收敛（保 R+G+B 不变）",
                            "chroma_mean": [round(v, 6) for v in ctx.ink_chroma_mean],
                            "conflict": "与『内容零色彩改动』冲突 ⇒ 待裁；--color-calib 0 即完全冻结"},
            "crop": ({"bits": args.crop_bits, "box_300dpi": list(args.crop_box_300dpi),
                      "box_out_px": [crop_px[0], crop_px[1], crop_px[2], crop_px[3]],
                      "out": str(crop_path),
                      "quantizer": "q8 = round(page_u16 / 257)" if args.crop_bits == 8 else "16bit 原样"}
                     if crop_box is not None else "（缺省不出裁件；须显式 --crop --crop-out）"),
        },
    }

    if not args.verify_only:
        res = render_page(ctx, out_path, strip_rows=STRIP_OUT_ROWS, crop_box=crop_box,
                          crop_bits=args.crop_bits, scratch_dir=Path(args.scratch) if args.scratch else None,
                          progress_path=Path(args.progress) if args.progress else None,
                          description=image_description(page, TARGET_DPI))
        if crop_box is not None and crop_path is not None:
            crop = res.pop("crop")
            assert res.pop("crop_fully_covered"), (
                f"裁件行未被 strip 全覆盖：{res['crop_rows_filled']}/{res['crop_rows_total']}")
            if args.crop_bits == 8:
                from PIL import Image as _I
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                _I.fromarray(crop).save(str(crop_path) + ".part", format="TIFF", compression="tiff_deflate",
                                        tiffinfo={_sc.TIFF_TAG_PREDICTOR: TIFF_PREDICTOR})
                os.replace(str(crop_path) + ".part", crop_path)
            else:
                write_tiff(crop.astype(np.uint16).copy(), crop_path,
                           rowsperstrip=crop.shape[0], description=f"p{page} C1-R1 crop 48bit")
            res["crop_bytes"] = int(crop_path.stat().st_size)
            if args.samples:
                SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
                Image.fromarray(crop.astype(np.uint8) if crop.dtype == np.uint8 else q8(crop)).save(
                    SAMPLES_DIR / f"P{page}-C1-R1-crop-preview.png")
                half = crop.shape[0] // 2
                Image.fromarray(q8(crop[half - 512:half + 512, 0:1024])).save(
                    SAMPLES_DIR / f"P{page}-C1-R1-1to1-window.png")
        readings["render"] = {k: v for k, v in res.items() if k != "preview"}
        if args.samples:
            SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
            pv = res["preview"]
            Image.fromarray(np.rint(pv / 257.0).astype(np.uint8)).save(
                SAMPLES_DIR / f"P{page}-{TARGET_DPI}dpi-preview-x16.png")

    readings["verification"] = verify(out_path,
                                      (crop_path if (crop_path is not None and crop_path.exists()) else None),
                                      ctx, crop_bits=args.crop_bits, limit=args.verify_strips,
                                      seed=args.verify_seed, crop_box=crop_box)
    readings["measured"] = {
        "out_bytes": readings["verification"]["out_bytes"],
        "out_gib": readings["verification"]["out_gib"],
        "out_sha256": readings["verification"]["sha256"],
        "raw_uncompressed_bytes": OUT_W * OUT_H * 3 * 2,
        "paper_px_share": round(ctx.counters.get("paper_px", 0) / max(1.0, ctx.counters.get("out_px", 1)), 6),
        "ink_px_share": round(ctx.counters.get("ink_px", 0) / max(1.0, ctx.counters.get("out_px", 1)), 6),
        "cpu_seconds": round(time.process_time(), 2),
    }
    readings_path.parent.mkdir(parents=True, exist_ok=True)
    readings_path.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    v = readings["verification"]
    check = {
        "shape_ok": v["container"]["shape"] == [OUT_H, OUT_W, 3],
        "bits_ok": v["container"]["bits_per_sample"] == 16 and v["container"]["samples_per_pixel"] == 3,
        "compression_ok": v["container"]["compression"] == TIFF_COMPRESSION_TAG
        and v["container"]["predictor"] == TIFF_PREDICTOR,
        "bigtiff_auto_ok": bool(v["container"]["bigtiff"] == (OUT_W * OUT_H * 3 * 2 > BIGTIFF_THRESHOLD_BYTES)),
        "classic_tiff_for_1200_ok": bool(v["container"]["bigtiff"] is False) if TARGET_DPI <= 1200 else True,
        "resolution_tag_ok": (v["container"]["x_resolution"] == [TARGET_DPI, 1]
                              and v["container"]["resolution_unit"] == 2),
        "description_dpi_ok": f"{TARGET_DPI}dpi" in (v["container"]["description"] or ""),
        "roundtrip_ok": v["roundtrip"]["decode_vs_recompute_mismatch_px"] == 0,
        "freeze_ok": v["freeze"]["mismatch_px"] == 0,
        "halo_out_of_range_ok": v["paper_background"]["outside_declared_range_and_outside_halo_px"] == 0,
        "ink_sum_preserved_ok": (v["ink_colorcalib"]["max_abs_sum_RGB_jump_float"]
                                 <= SUM_INVARIANT_TOL),
        "ink_strength_bounded_ok": (v["ink_colorcalib"]["realized_strength"]["max"]
                                    <= v["ink_colorcalib"]["strength_requested"] + 1e-6),
    }
    if crop_box is not None:
        check["crop_ok"] = (v.get("crop", {}).get("vs_page_mismatch_px") == 0
                            and v.get("crop", {}).get("size_px") == [crop_px[2] - crop_px[0],
                                                                     crop_px[3] - crop_px[1]])
    readings["checks"] = check
    readings_path.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": check,
                      "measured": readings["measured"],
                      "roundtrip": v["roundtrip"], "freeze": v["freeze"],
                      "ink_colorcalib": v["ink_colorcalib"],
                      "paper_background": {k: v["paper_background"][k] for k in
                                           ("observed_min_u8_round", "observed_max_u8_round",
                                            "outside_declared_range_px",
                                            "outside_declared_range_and_outside_halo_px")},
                      "crop": {k: v["crop"][k] for k in ("size_px", "size_mm_from_2400dpi",
                                                         "size_mm_from_300dpi_bbox",
                                                         "vs_page_mismatch_px", "container")}
                      if "crop" in v else None},
                     ensure_ascii=False, indent=2))
    return 0 if all(check.values()) else 1


def _smoke() -> int:
    """小合成页自检：**strip 流式 ≡ 整幅**、tifffile 写读逐像素一致、容器 tags 正确。"""
    rng = np.random.default_rng(11)
    src = rng.integers(0, 256, (200, 150, 3)).astype(np.uint8)
    src[40:120, 30:110] = 250
    src[50:110, 40:100] = (200, 60, 55)
    full_h = src.shape[0] * UP
    ctx = build_ctx(src, COLOR_CALIB_DEFAULT)
    whole, _, _ = process_strip(0, full_h, ctx, None)
    sr = 64
    parts = [process_strip(y, min(y + sr, full_h), build_ctx(src, COLOR_CALIB_DEFAULT), None)[0]
             for y in range(0, full_h, sr)]
    strip = np.concatenate(parts, axis=0)
    same = bool(np.array_equal(whole, strip))
    print("strip==whole:", same, "| maxdiff", int(np.abs(whole.astype(int) - strip.astype(int)).max()))

    # 冻结自证：非纸底 ∧ 非印泥像素 == clip(8× Lanczos)
    lun_f, paper, ink, _halo = strip_layers(0, full_h, build_ctx(src, COLOR_CALIB_DEFAULT))
    lun = to_u16(lun_f)
    content = ~paper & ~ink
    d = np.abs(whole.astype(np.int32) - lun.astype(np.int32))
    frz = int(d[content].max()) if content.any() else 0
    print("freeze maxdiff(non-paper,non-ink):", frz, "content px", int(content.sum()))

    # 掩膜互斥 ∧ ⑤ 代数不变量（浮点域 Σ 守恒 ∧ t ≤ strength）
    c2 = build_ctx(src, COLOR_CALIB_DEFAULT)
    lay = strip_layers(0, full_h, c2)
    big, paper2, ink2, _h2, t2 = synthesize(0, full_h, c2, layers=lay, collect=True)
    disjoint = int((paper2 & ink2).sum()) == 0
    sum_jump = float(np.abs(big[ink2].astype(np.float64).sum(1)
                            - lay[0][ink2].astype(np.float64).sum(1)).max()) if ink2.any() else 0.0
    t_ok = bool(t2.size == 0 or float(t2.max()) <= COLOR_CALIB_DEFAULT + 1e-6)
    sum_ok = sum_jump <= SUM_INVARIANT_TOL
    skipped = int(c2.counters.get("calib_skipped_invalid_px", 0))
    print("masks disjoint:", disjoint, "| ink float-sum jump:", round(sum_jump, 6),
          "(tol", SUM_INVARIANT_TOL, ") | skipped invalid-domain px:", skipped,
          "| t<=strength:", t_ok)

    with tempfile.TemporaryDirectory() as td:
        pth = Path(td) / "smoke.tif"
        arr = np.ascontiguousarray(whole)
        w = write_tiff(arr, pth, rowsperstrip=sr, description="smoke")
        tags = container_tags(pth)
        back = tifffile.imread(pth)
        rt = bool(np.array_equal(back, arr))
        # 裁件交集落位：小页中点一小块
        cb = (100, 400, 40, 300)   # (cy0, cy1, cx0, cx1)
        crop = np.zeros((cb[1] - cb[0], cb[3] - cb[2], 3), dtype=np.uint8)
        filled = np.zeros(cb[1] - cb[0], dtype=bool)
        for y in range(0, full_h, sr):
            _, oy0, ov = process_strip(y, min(y + sr, full_h),
                                       build_ctx(src, COLOR_CALIB_DEFAULT), cb)
            if ov is not None:
                s = oy0 - cb[0]
                crop[s:s + ov.shape[0]] = q8(ov)
                filled[s:s + ov.shape[0]] = True
        crop_ok = bool(filled.all() and np.array_equal(crop, q8(arr[cb[0]:cb[1], cb[2]:cb[3]])))
        print("container:", {k: tags[k] for k in ("shape", "bits_per_pixel", "compression", "predictor",
                                                  "rowsperstrip", "bigtiff", "strips", "resolution_unit",
                                                  "x_resolution")}, "| bytes", w["bytes"])
        print("readback equal:", rt, "| crop-by-intersection equal:", crop_ok)
    ok = same and frz == 0 and rt and crop_ok and disjoint and sum_ok and t_ok \
        and tags["compression"] == TIFF_COMPRESSION_TAG \
        and tags["predictor"] == TIFF_PREDICTOR and tags["bits_per_pixel"] == 48
    # v3：两个白名单 dpi 的几何自证（纹理的 mm 不变性另由
    #     ops/book-page-2400/probe_texture_mm_invariance.py 出判据读数）
    for dpi in DPI_WHITELIST:
        print(f"geometry@{dpi}:", json.dumps(configure_geometry(dpi, 150, 200), ensure_ascii=False))
    configure_geometry(DPI_DEFAULT, 150, 200)          # 还原缺省几何
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
