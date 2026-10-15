#!/usr/bin/env python
"""C2 修正版样张（Kong · ops/variant-samples/round2_samples.py）。

背景：上轮（commit 91b0e78）四版 A/B/C/D 已出，Kevin 选 **C（实拍观感）** 作方向，提两条硬修正：
  【修正 1】宣纸纹理必须按**物理尺度（mm）**定义、运行时按目标 dpi 换算 px；升级为**多尺度带限噪声**
            （fBm/噪声金字塔 ≥3 octave：成形云斑/粗纤维/细纤维/颗粒 ＋ ≥1200dpi 专属微纤维网）；
            弱各向异性、极低对比、无重复；出 3 组候选（保守/中/明显）；600 与 2400dpi **1:1 并排**做
            dpi 对齐硬判据（功率谱峰值/自相关长度换算 mm 后必须相等）。
  【修正 2】印泥校准从「向全页印泥均色收敛（color_uniformity，保 ΣRGB）」改为**向基准色 `#C95021` 靠拢**：
            复用 `server/app/colorcal.py` 的 V3 前景色度函数（`apply_foreground_chroma` / V3_FG_CHROMA_STRENGTH，
            单一真源、只 import 不复制常量），**保 L\\***；读数＝印泥核心质心→`#C95021` 的 **ΔE2000**
            （中位/p90/≤5 命中率，用 `colorcal` 现算）。

不变约束：结构冻结（结构算子只写红墨区，白线区/掩膜外逐像素零外泄；白文印白线＝掩膜内保护）；
同参重跑逐像素一致；只改观感不改结构。

红线：不写 yinpu.db／不建 job／2_HighRes_PDF 与 output/books 既有件只读（本单只在**区域裁取**时读它）／
样张只落 output/samples/book-page-2400-variants/round2/／可入库件只落 ops/variant-samples/／
生产常量与实现一律 import 复用（`render_page_2400`、`app.seal_canvas`、`app.colorcal`、
上轮 `variants_samples`），**不复制第二份**。

跑法：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/variant-samples/round2_samples.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))                        # app.* ⇒ server/app
sys.path.insert(0, str(REPO / "ops" / "book-page-2400"))
sys.path.insert(0, str(REPO / "ops" / "variant-samples"))
import render_page_2400 as rp                                    # noqa: E402  生产整页实现（只读复用）
from app import seal_canvas as sc                                # noqa: E402  宣纸色域/种子常量单一真源
from app import colorcal as cc                                   # noqa: E402  靶色 / V3 色度函数单一真源
import variants_samples as vs                                    # noqa: E402  上轮 C 版与工具（只读复用）
from crop_c2r1 import extract_region_u16                         # noqa: E402  既有 strip 级解码先例

# ══════════════════════════════════════════════════════════════════════════════════════
# 0. 几何 / 路径 / 常量
# ══════════════════════════════════════════════════════════════════════════════════════
PDF = REPO / "output" / "1_Original_PDF" / "秦印类编 检索版.pdf"
PAGE, XREF = 29, 112
SCAN_DPI = 300
SRC_W, SRC_H = 2125, 3059
COMP_DPI = 600                                   # 上轮对比几何（保留，作四联/缩略基准）
PROD_DPI = 2400                                  # 产线正式输出 dpi（本轮 1:1 局部样张基准）
MAIN_TIF = REPO / "output/2_HighRes_PDF/9787550847224/P29-2400dpi-48bit.tif"
PROD_READINGS = REPO / "ops/book-page-2400/readings-P29-2400dpi-48bit.json"
ROUND1_READINGS = REPO / "ops/variant-samples/readings.json"
SAMPLES_DIR = REPO / "output/samples/book-page-2400-variants/round2"
OPS_DIR = Path(__file__).resolve().parent
READINGS_PATH = OPS_DIR / "readings-round2.json"
SCALE_TABLE_PATH = OPS_DIR / "scale-table-round2.md"

MM_PER_IN = 25.4
SEED = sc.BG_SEED_DEFAULT                        # 20261013（seal_canvas 单一真源）
DPI_TABLE = (300, 600, 1200, 2400)               # 换算表口径（供人核）

C1_BBOX = (533, 555, 798, 823)                   # C1-R1 白文大方印（@300dpi）
C2_BBOX = (1422, 560, 1565, 820)                 # C2-R1 细长条印（@300dpi）
PAD300 = 60
DARK_CORE = 150                                  # 文字核心判据（同 round1）
TEXT_PROTECT_PX = 2
D_PAPER_GRAY_MIN, D_PAPER_SAT_MAX = 165, 0.30    # 纸底净化圈（同 round1 D 版；本单不用作换底判据）
THUMB_W = 800
PANEL_GAP = 10
LABEL_H = 22
LEFT_W = 210


def mm2px(mm: float, dpi: float) -> float:
    return float(mm) / MM_PER_IN * float(dpi)


def px2mm(px: float, dpi: float) -> float:
    return float(px) * MM_PER_IN / float(dpi)


def mm2px_int(mm: float, dpi: float) -> int:
    return max(1, int(round(mm2px(mm, dpi))))


def odd_px(mm: float, dpi: float) -> int:
    """给形态学/滤波核用：奇数 px（≥3）。"""
    k = mm2px_int(mm, dpi)
    return k if k % 2 == 1 else k + 1


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. 纹理真源（**一律 mm**；单一常量、单点可改）
# ══════════════════════════════════════════════════════════════════════════════════════
# 真实宣纸参考尺度（Kevin 给）：纤维长 0.5–3 mm、宽 0.02–0.08 mm；颗粒 0.05–0.2 mm。
TEX_ANISO_RATIO = 3.5          # 长轴/短轴（**弱各向异性**刻度；真实纤维 ~25–40 ⇒ 见 README 取舍说明）
TEX_MOTTLE_MM = 11.0           # 成形不匀（低频云斑；纸张"帘纹/厚薄"观感）
TEX_FIB_COARSE_LEN_MM = 1.60   # 粗纤维长轴（参考区间 0.5–3 mm）
TEX_FIB_FINE_LEN_MM = 0.55     # 细纤维长轴（参考区间 0.5–3 mm 下沿）
TEX_GRAIN_MM = 0.16            # 颗粒直径（参考区间 0.05–0.2 mm）
TEX_MICRO_FIB_MM = 0.070       # 微纤维网（∈ 真实纤维宽 0.02–0.08 mm；**仅 dpi ≥ 1200 启用**）
TEX_MICRO_MIN_DPI = 1200       # 微纤维网启用下限（600dpi 下 <2px，属采样不可表示）
# 各 octave 名义幅度（0–255 亮度标度；dpi 无关 = 反射率对比度，物理正确）
AMP_MOTTLE, AMP_FIB_COARSE, AMP_FIB_FINE, AMP_GRAIN = 0.55, 0.95, 0.55, 0.45
AMP_MICRO = 0.22
# 3 组候选：尺度梯度 × 幅度梯度（供 Kevin 对比选）
CANDIDATES = {
    "CONS": {"label": "保守", "scale": 0.80, "amp": 0.62},
    "MID": {"label": "中", "scale": 1.00, "amp": 0.85},
    "OBV": {"label": "明显", "scale": 1.25, "amp": 1.15},
}
CAND_ORDER = ("CONS", "MID", "OBV")
AMP_LEVELS = (1.0, 1.6)        # 幅度档（对比板用；1.0 = 候选标称）
TEX_FIELD_MM = 8.0             # 对比板视野（mm，正方形）
TEX_STAT_FIELD_MM = 12.0       # 统计读数视野（mm；比可见板大，容得下云斑自相关）

# 观感算子尺度（**mm**；数值＝上轮 600dpi px 常量的物理等价 ⇒ 600dpi 观感与上轮 C 保持一致）
FIELD_SIGMA_MM = px2mm(vs.FIELD_SIGMA_600, COMP_DPI)         # 1.058 mm
FIELD_GAIN_LO, FIELD_GAIN_HI = vs.FIELD_GAIN_LO, vs.FIELD_GAIN_HI
SCURVE_T = vs.SCURVE_T
MICRO_AMOUNT, MICRO_SIGMA_MM = vs.MICRO_AMOUNT, px2mm(vs.MICRO_SIGMA_600, COMP_DPI)   # 0.254 mm
PAPER_MICRO_AMOUNT = vs.PAPER_MICRO_AMOUNT
HALO_BAND_MM = px2mm(vs.HALO_BAND_600, COMP_DPI)             # 0.169 mm
HALO_BAND_OUTER_MM = 1.016                                   # 环带外沿（上轮 24px@600）
PEN_ALPHA_MAX, PEN_TAU_MM = vs.PEN_ALPHA_MAX, px2mm(vs.PEN_TAU_600, COMP_DPI)
GUIDE_RADIUS_MM = px2mm(vs.GUIDE_RADIUS_600, COMP_DPI)       # 0.339 mm（保边平滑半径）
GUIDE_EPS = vs.GUIDE_EPS                                     # 常数（亮度域方差量级）
CALIB_STRENGTH_LEGACY = vs.CALIB_STRENGTH                    # 上轮/产线 color_uniformity 强度（对照）

# 上轮 C 的**像素常量**纹理（反例对照：像素常量 ⇒ dpi 一变物理尺度就变）
OLD_TEX = {"long_px": vs.FIBER_CELL_LONG_600, "short_px": vs.FIBER_CELL_SHORT_600,
           "long2_px": vs.FIBER_CELL_LONG2_600, "short2_px": vs.FIBER_CELL_SHORT2_600,
           "sigma_f1": sc.BG_FIBER_SIGMA, "sigma_f2": vs.FIBER2_SIGMA,
           "sigma_grain": sc.BG_GRAIN_SIGMA, "dpi_defined_at": COMP_DPI}


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. 多尺度带限噪声（**mm 空间**位置哈希 ⇒ 与 dpi / 分块顺序无关、无重复周期）
# ══════════════════════════════════════════════════════════════════════════════════════
def vnoise_mm(rows_mm: np.ndarray, cols_mm: np.ndarray, cl_mm: float, cs_mm: float,
              seed: int, salt: int) -> np.ndarray:
    """各向异性 value-noise，晶格坐标在 **mm 空间** ⇒ 物理尺度与 dpi 无关。

    机制＝`render_page_2400._fiber_lattice`（smoothstep 双线性插值 ＋ 位置哈希晶格角点），
    但晶格常数由 **mm** 给出（生产那份是 600dpi 像素常量）⇒ 同一物理场在不同 dpi 上采样一致。
    """
    gy = rows_mm / float(cs_mm)
    gx = cols_mm / float(cl_mm)
    iy0 = np.floor(gy).astype(np.int64)
    ix0 = np.floor(gx).astype(np.int64)
    fy = (gy - iy0).astype(np.float64)
    fx = (gx - ix0).astype(np.float64)
    fy = fy * fy * (3.0 - 2.0 * fy)
    fx = fx * fx * (3.0 - 2.0 * fx)
    uy, ux = np.unique(iy0), np.unique(ix0)
    ry, cx = np.searchsorted(uy, iy0), np.searchsorted(ux, ix0)

    def corner(dy: int, dx: int) -> np.ndarray:
        return rp._u(rp._hash64(uy + dy, ux + dx, seed, salt + dy * 2 + dx), 0, 21)[ry][:, cx]
    v00, v01, v10, v11 = corner(0, 0), corner(0, 1), corner(1, 0), corner(1, 1)
    top = v00 + (v01 - v00) * fx[None, :]
    bot = v10 + (v11 - v10) * fx[None, :]
    return top + (bot - top) * fy[:, None]


_STD_CACHE: dict[tuple, float] = {}


def octave_std_ref(cl_mm: float, cs_mm: float, seed: int, salt: int) -> float:
    """octave 的**密集采样**标准差（归一化基准；mm 空间 ⇒ 与 dpi 无关的常数，可 memo）。"""
    key = (round(cl_mm, 6), round(cs_mm, 6), seed, salt)
    if key not in _STD_CACHE:
        dens = 12                                    # 每晶格 12 采样 ⇒ 接近连续域
        ncell = 64
        rows = np.arange(0, ncell * dens, dtype=np.float64) / dens * cs_mm
        cols = np.arange(0, ncell * dens, dtype=np.float64) / dens * cl_mm
        _STD_CACHE[key] = float((vnoise_mm(rows, cols, cl_mm, cs_mm, seed, salt) - 0.5).std())
    return _STD_CACHE[key]


def octave_spec(cand: str, dpi: int, scale_extra: float = 1.0) -> list[dict]:
    """候选 × dpi 的 octave 表（mm 真源 ＋ 换算 px ＋ dpi 可表示性判定）。"""
    cfg = CANDIDATES[cand]
    s = float(cfg["scale"]) * float(scale_extra)
    spec = [
        {"name": "mottle", "long_mm": TEX_MOTTLE_MM * s, "short_mm": TEX_MOTTLE_MM * s,
         "amp": AMP_MOTTLE, "salt": 71},
        {"name": "fiber_coarse", "long_mm": TEX_FIB_COARSE_LEN_MM * s,
         "short_mm": TEX_FIB_COARSE_LEN_MM * s / TEX_ANISO_RATIO, "amp": AMP_FIB_COARSE, "salt": 113},
        {"name": "fiber_fine", "long_mm": TEX_FIB_FINE_LEN_MM * s,
         "short_mm": TEX_FIB_FINE_LEN_MM * s / TEX_ANISO_RATIO, "amp": AMP_FIB_FINE, "salt": 157},
        {"name": "grain", "long_mm": TEX_GRAIN_MM, "short_mm": TEX_GRAIN_MM,
         "amp": AMP_GRAIN, "salt": 199},
    ]
    if dpi >= TEX_MICRO_MIN_DPI:
        spec.append({"name": "fiber_micro", "long_mm": TEX_MICRO_FIB_MM,
                     "short_mm": TEX_MICRO_FIB_MM, "amp": AMP_MICRO, "salt": 233})
    for o in spec:
        o["long_px"] = mm2px(o["long_mm"], dpi)
        o["short_px"] = mm2px(o["short_mm"], dpi)
        o["resolvable_2px"] = bool(o["short_px"] >= 2.0)
        o["amp_scaled"] = o["amp"] * float(cfg["amp"])
    return spec


def paper_field_mm(rows: np.ndarray, cols: np.ndarray, dpi: int, cand: str,
                   amp_level: float = 1.0, scale_extra: float = 1.0,
                   with_micro: bool = True) -> np.ndarray:
    """宣纸底纹（float32, 色域内）：**mm 定义的多尺度带限噪声** ＋ seal_canvas 基色/微色偏。

    * 亮度项 ＝ Σ octave `amp · (n − 0.5)/std_ref`（各 octave 按密集采样 std 归一 ⇒ 幅度可读、dpi 无关）；
    * 色偏项 ＝ `sc.BG_CHROMA_SIGMA · chroma`（seal_canvas 单一真源）；
    * 基色/色域 ＝ `sc.BG_BASE_RGB` / `BG_MIN_RGB` / `BG_MAX_RGB`（单一真源）；
    * **不含**上轮的像素白噪声颗粒（`BG_GRAIN_SIGMA·gaussian`）—— 那是 1px 相关长度的 dpi 依赖项，
      正是「高尺寸纹理过稀」的来源之一；本轮改由物理尺度 `grain` octave（0.16 mm）承担。
    """
    r_mm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    c_mm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    lum = np.zeros((r_mm.size, c_mm.size), np.float32)
    for o in octave_spec(cand, dpi, scale_extra):
        if o["name"] == "fiber_micro" and not with_micro:
            continue
        n = vnoise_mm(r_mm, c_mm, o["long_mm"], o["short_mm"], SEED, o["salt"])
        ref = octave_std_ref(o["long_mm"], o["short_mm"], SEED, o["salt"])
        lum += (np.float32(o["amp_scaled"] * amp_level / ref) *
                (n.astype(np.float32) - np.float32(0.5)))
    h2 = rp._hash64(rows, cols, SEED, 1)
    chroma = np.stack([rp._u(h2, 0, 21) - 0.5, rp._u(h2, 21, 21) - 0.5, rp._u(h2, 42, 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    out = (np.asarray(sc.BG_BASE_RGB, np.float32)[None, None, :] + lum[:, :, None]
           + np.float32(sc.BG_CHROMA_SIGMA) * chroma)
    return np.clip(out, np.asarray(sc.BG_MIN_RGB, np.float32)[None, None, :],
                   np.asarray(sc.BG_MAX_RGB, np.float32)[None, None, :])


def old_paper_field(rows: np.ndarray, cols: np.ndarray, dpi: int) -> np.ndarray:
    """反例对照：**上轮 C 的像素常量纹理**（16/2 ＋ 64/8 px ＋ 像素白噪声），按目标 dpi 直接复用像素常量。"""
    r_mm = rows.astype(np.float64)                      # 用 px 作"坐标"，即像素常量口径
    c_mm = cols.astype(np.float64)
    lum = np.zeros((rows.size, cols.size), np.float32)
    h1 = rp._hash64(rows, cols, SEED, 0)
    u1 = np.maximum(rp._u(h1, 0, 31), 1e-9)
    u2 = rp._u(h1, 31, 31)
    grain = (np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)).astype(np.float32)
    lum += np.float32(OLD_TEX["sigma_grain"]) * grain
    for (cl, cs, sig, salt) in ((OLD_TEX["long_px"], OLD_TEX["short_px"], OLD_TEX["sigma_f1"], 7),
                                (OLD_TEX["long2_px"], OLD_TEX["short2_px"], OLD_TEX["sigma_f2"], 17)):
        n = vs._fiber_lattice_p(rows, cols, cl, cs, SEED, salt).astype(np.float32)
        ref = np.float32(vs._fiber_std_probe(cl, cs, SEED, salt))
        lum += np.float32(sig) * (n - np.float32(0.5)) / ref
    h2 = rp._hash64(rows, cols, SEED, 1)
    chroma = np.stack([rp._u(h2, 0, 21) - 0.5, rp._u(h2, 21, 21) - 0.5, rp._u(h2, 42, 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    out = (np.asarray(sc.BG_BASE_RGB, np.float32)[None, None, :] + lum[:, :, None]
           + np.float32(sc.BG_CHROMA_SIGMA) * chroma)
    return np.clip(out, np.asarray(sc.BG_MIN_RGB, np.float32)[None, None, :],
                   np.asarray(sc.BG_MAX_RGB, np.float32)[None, None, :])


def gen_paper_mm(h: int, w: int, dpi: int, cand: str, amp_level: float = 1.0,
                 scale_extra: float = 1.0, with_micro: bool = True, band: int = 384) -> np.ndarray:
    """整幅宣纸（uint8）：按行带生成（位置哈希 ⇒ 与分块无关、内存有界）。"""
    out = np.empty((h, w, 3), np.uint8)
    cols = np.arange(0, w, dtype=np.int64)
    for y0 in range(0, h, band):
        y1 = min(y0 + band, h)
        rows = np.arange(y0, y1, dtype=np.int64)
        out[y0:y1] = vs.to_u8(paper_field_mm(rows, cols, dpi, cand, amp_level, scale_extra, with_micro))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. dpi 对齐读数（自相关长度 / 径向功率谱 / 频带能量，全部换算 mm）
# ══════════════════════════════════════════════════════════════════════════════════════
TEX_BANDS_MM = ((0.5, 3.0), (0.15, 0.6), (0.05, 0.30), (0.02, 0.12))     # 波长带（mm）


def _half_decay_len(prof: np.ndarray) -> float | None:
    """1D 归一化自相关剖面首个跌破 0.5 的滞后（样本数，线性插值）。"""
    below = np.where(prof < 0.5)[0]
    if below.size == 0:
        return None
    i = int(below[0])
    if i == 0:
        return 0.0
    x0, x1 = float(prof[i - 1]), float(prof[i])
    frac = (x0 - 0.5) / (x0 - x1) if x0 != x1 else 0.0
    return (i - 1) + float(np.clip(frac, 0.0, 1.0))


def tex_alignment_readout(lum_f32: np.ndarray, dpi: int, field_mm: float) -> dict:
    """单块纸底亮度残差的**物理尺度读数**（mm/cyc·mm⁻¹）——dpi 无关性判据。"""
    a = np.asarray(lum_f32, np.float64)
    a = a - a.mean()
    h, w = a.shape
    # ① 自相关（FFT，零填充到 ≥2× 以免环绕）
    ph, pw = 1 << int(np.ceil(np.log2(2 * h))), 1 << int(np.ceil(np.log2(2 * w)))
    F = np.fft.rfft2(a, s=(ph, pw))
    ac = np.fft.irfft2(np.abs(F) ** 2, s=(ph, pw))
    ac = np.fft.fftshift(ac)
    ac = ac / ac[ph // 2, pw // 2]
    cy, cx = ph // 2, pw // 2
    prof_x = ac[cy, cx:cx + w // 2]
    prof_y = ac[cy:cy + h // 2, cx]
    lx, ly = _half_decay_len(prof_x), _half_decay_len(prof_y)
    mmx = px2mm(1.0, dpi)
    # ② 径向功率谱（Hanning 窗；频率单位 cyc/mm）
    win = np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.rfft2(a * win)) ** 2
    fy = np.fft.fftfreq(h, d=mmx)                       # cyc/mm（沿行轴）
    fx = np.fft.rfftfreq(w, d=mmx)
    FY, FX = np.meshgrid(fy, fx, indexing="ij")
    fr = np.sqrt(FY ** 2 + FX ** 2)
    nb = 128
    fmax = float(fr.max())
    edges = np.linspace(0.0, fmax, nb + 1)
    idx = np.clip(np.digitize(fr.ravel(), edges) - 1, 0, nb - 1)
    psum = np.bincount(idx, weights=P.ravel(), minlength=nb)
    cnt = np.bincount(idx, minlength=nb)
    fcen = 0.5 * (edges[:-1] + edges[1:])
    psd = psum / np.maximum(cnt, 1)
    lo_cut = 1.0 / (2.0 * field_mm)                     # 忽略低于"半视野"频率的分量
    m = (fcen > lo_cut) & (cnt > 0)
    cen = float((fcen[m] * psd[m]).sum() / max(psd[m].sum(), 1e-30)) if m.any() else 0.0
    pk_f = float(fcen[m][int(np.argmax(psd[m]))]) if m.any() else 0.0
    tot = float(psd[m].sum()) if m.any() else 0.0
    bands = {}
    for lo_mm, hi_mm in TEX_BANDS_MM:
        f_lo, f_hi = 1.0 / hi_mm, 1.0 / lo_mm
        sel = (fcen >= f_lo) & (fcen < f_hi) & (cnt > 0)
        bands[f"{lo_mm}-{hi_mm}mm"] = (float(psd[sel].sum() / max(tot, 1e-30)) if sel.any() else 0.0)
    return {
        "dpi": dpi, "field_mm": field_mm, "px": [w, h], "px_per_mm": round(1.0 / mmx, 3),
        "autocorr_half_decay_mm": {"x": (None if lx is None else round(px2mm(lx, dpi), 4)),
                                   "y": (None if ly is None else round(px2mm(ly, dpi), 4))},
        "autocorr_half_decay_px": {"x": (None if lx is None else round(lx, 2)),
                                   "y": (None if ly is None else round(ly, 2))},
        "psd_centroid_cyc_per_mm": round(cen, 5),
        "psd_centroid_wavelength_mm": (round(1.0 / cen, 4) if cen > 0 else None),
        "psd_peak_cyc_per_mm": round(pk_f, 5),
        "psd_peak_wavelength_mm": (round(1.0 / pk_f, 4) if pk_f > 0 else None),
        "band_power_share": {k: round(v, 5) for k, v in bands.items()},
        "rms_0_255": round(float(a.std()), 4),
    }


def tex_cross_dpi_sim(paper2400_rgb: np.ndarray, paper600_rgb: np.ndarray) -> dict:
    """2400dpi 纸底 ÷4（cv2.INTER_AREA）与 600dpi 纸底**逐像素**对照（同一物理场 ⇒ 应近乎逐像素相同）。"""
    a = cv2.resize(paper2400_rgb.astype(np.float32),
                   (paper600_rgb.shape[1], paper600_rgb.shape[0]), interpolation=cv2.INTER_AREA)
    b = paper600_rgb.astype(np.float32)
    d = a - b
    dg = a.mean(axis=2) - b.mean(axis=2)
    return {"mean_abs_diff_rgb": round(float(np.abs(d).mean()), 4),
            "max_abs_diff_rgb": round(float(np.abs(d).max()), 3),
            "mean_abs_diff_lum": round(float(np.abs(dg).mean()), 4),
            "p99_abs_diff_lum": round(float(np.percentile(np.abs(dg), 99)), 4),
            "pearson_r_lum": round(float(np.corrcoef(a.mean(axis=2).ravel(), b.mean(axis=2).ravel())[0, 1]), 6)}


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. 印泥校准读数（ΔE2000 一律走 colorcal）
# ══════════════════════════════════════════════════════════════════════════════════════
TARGET_LAB = cc.srgb_to_lab(cc.TARGET_RGB)


def delta_e_stats(rgb_px: np.ndarray, max_px: int = 400000) -> dict:
    """掩膜内像素 → `#C95021` 的 CIEDE2000 分布（中位/p90/≤5/≤3 命中率）。

    ΔE 由 **`colorcal`** 现算：Lab 走 `colorcal._srgb_to_lab_arr`（colorcal 自己的数组实现），
    逐点色差走 `colorcal.ciede2000_lab`（即公开 `delta_e2000` 内部同一个函数）——**不手写**。
    超 `max_px` 时按**固定步长**等距抽样（系统性抽样，步长登记）。
    """
    px = np.asarray(rgb_px, np.float64)
    n_all = px.shape[0]
    stride = 1
    if n_all > max_px:
        stride = int(np.ceil(n_all / max_px))
        px = px[::stride]
    if px.shape[0] == 0:
        return {"pixels": 0, "sampled": 0, "stride": stride, "median": None, "p90": None,
                "leq5_rate": None, "leq3_rate": None, "mean": None}
    lab = cc._srgb_to_lab_arr(px)
    de = np.fromiter((cc.ciede2000_lab(lab[i], TARGET_LAB) for i in range(lab.shape[0])),
                     dtype=np.float64, count=lab.shape[0])
    return {
        "pixels": int(n_all), "sampled": int(px.shape[0]), "stride": stride,
        "median": round(float(np.median(de)), 4),
        "p90": round(float(np.percentile(de, 90.0)), 4),
        "mean": round(float(de.mean()), 4),
        "leq5_rate": round(float((de <= 5.0).mean()), 5),
        "leq3_rate": round(float((de <= 3.0).mean()), 5),
    }


def lab_stats(px: np.ndarray, max_px: int = 400000) -> dict:
    """掩膜内像素 Lab 统计（L* 均值/p10/p50/p90 ＋ a*/b* σ）——保 L* 判据。"""
    px = np.asarray(px, np.float64)
    if px.shape[0] > max_px:
        px = px[:: int(np.ceil(px.shape[0] / max_px))]
    if px.shape[0] == 0:
        return {}
    lab = cc._srgb_to_lab_arr(px)
    L, A, B = lab[:, 0], lab[:, 1], lab[:, 2]
    return {"L_mean": round(float(L.mean()), 3), "L_std": round(float(L.std()), 3),
            "L_p10": round(float(np.percentile(L, 10)), 3),
            "L_p50": round(float(np.percentile(L, 50)), 3),
            "L_p90": round(float(np.percentile(L, 90)), 3),
            "a_std": round(float(A.std()), 3), "b_std": round(float(B.std()), 3),
            "a_mean": round(float(A.mean()), 3), "b_mean": round(float(B.mean()), 3)}


def rgb_mean(px: np.ndarray) -> list[float]:
    return [round(float(v), 3) for v in np.asarray(px, np.float64).mean(axis=0)]


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. 算子（尺度参数一律 mm→px，dpi 自适应）
# ══════════════════════════════════════════════════════════════════════════════════════
def field_gain_mm(img: np.ndarray, paper_m: np.ndarray, dpi: int) -> tuple[np.ndarray, dict]:
    """C① 低频光场估计与去除（σ 由 mm 换算）。"""
    sig = mm2px(FIELD_SIGMA_MM, dpi)
    y = vs.lum(img)
    pm = paper_m.astype(np.float32)
    num = cv2.GaussianBlur(y * pm, (0, 0), sig)
    den = cv2.GaussianBlur(pm, (0, 0), sig)
    field = num / np.maximum(den, np.float32(1e-6))
    ref = float(np.percentile(field[paper_m], 90.0))
    gain = np.clip(ref / np.maximum(field, np.float32(1e-6)),
                   np.float32(FIELD_GAIN_LO), np.float32(FIELD_GAIN_HI)).astype(np.float32)
    return img * gain[:, :, None], {
        "sigma_mm": round(FIELD_SIGMA_MM, 4), "sigma_px": round(sig, 2),
        "field_ref_p90": round(ref, 3), "gain_min_paper": round(float(gain[paper_m].min()), 4),
        "gain_max_paper": round(float(gain[paper_m].max()), 4)}


def tone_map_mm(img: np.ndarray, paper_m: np.ndarray, dpi: int) -> tuple[np.ndarray, dict]:
    """C② 全局色调映射（白平衡 gains 由 colorcal 真源给出 ＋ 轻柔 S 曲线 ＋ 微对比，σ 由 mm 换算）。"""
    paper_rgb = img[paper_m].astype(np.float64).mean(axis=0)
    g = cc.whitebalance_gains_for(tuple(float(v) for v in paper_rgb))
    k = np.asarray(g["gains"], np.float32)
    lin = vs.srgb_lin_f32(img / np.float32(255.0)) * k
    img = vs.lin_srgb_f32(lin) * np.float32(255.0)
    x = np.clip(img, 0.0, 255.0) / np.float32(255.0)
    s = (np.float32(1.0 - SCURVE_T)) * x + np.float32(SCURVE_T) * (
        np.float32(0.5) - np.float32(0.5) * np.cos(np.float32(np.pi) * x))
    img = s * np.float32(255.0)
    blur = cv2.GaussianBlur(img, (0, 0), mm2px(MICRO_SIGMA_MM, dpi))
    img = img + np.float32(MICRO_AMOUNT) * (img - blur)
    return img, {"wb_paper_rgb_before": rgb_mean(paper_rgb),
                 "wb_gains": [round(float(v), 5) for v in g["gains"]], "wb_clamped": g["clamped"],
                 "micro_sigma_mm": round(MICRO_SIGMA_MM, 4), "micro_sigma_px": round(mm2px(MICRO_SIGMA_MM, dpi), 2)}


def ink_chroma_ops(img: np.ndarray, red_m: np.ndarray, dpi: int, order: str) -> tuple[np.ndarray, dict]:
    """【修正 2】印泥校准 ＝ `colorcal` V3 前景色度（向 `#C95021` 靠、保 L\\*）＋ 红墨区保边平滑。

    `order`：
      * `"smooth_then_chroma"` —— 先保边平滑、后咬靶色；
      * `"chroma_then_smooth"` —— 先咬靶色、后保边平滑（＝上轮 C 的算子顺序）。
    **两者都只写红墨区**（白线区/掩膜外逐像素不动）⇒ 结构冻结断言与顺序无关。
    靶色强度取 `colorcal.V3_FG_CHROMA_STRENGTH`（单一真源，不复制常量）。
    """
    rad = mm2px_int(GUIDE_RADIUS_MM, dpi)
    info: dict = {"order": order, "guide_radius_mm": round(GUIDE_RADIUS_MM, 4),
                  "guide_radius_px": rad, "guide_eps": GUIDE_EPS,
                  "chroma_impl": "colorcal.apply_foreground_chroma（V3 前景色度）",
                  "chroma_strength": float(cc.V3_FG_CHROMA_STRENGTH),
                  "target_hex": cc.TARGET_HEX, "target_rgb": list(cc.TARGET_RGB),
                  "lstar_preserved_by": "colorcal V3（只改 a*/b*，L* 逐像素精确保留）"}
    if order == "smooth_then_chroma":
        y = vs.lum(img)
        sm = vs.guided_smooth_color(img, y, rad, GUIDE_EPS)
        img = img.copy()
        img[red_m] = sm[red_m]
        del sm
        img, fg = cc.apply_foreground_chroma(img, red_m)
    else:
        img, fg = cc.apply_foreground_chroma(img, red_m)
        y = vs.lum(img)
        sm = vs.guided_smooth_color(img, y, rad, GUIDE_EPS)
        img = img.copy()
        img[red_m] = sm[red_m]
        del sm
    info.update({"gamut_clip_rate": round(float(fg["gamut_clip_rate"]), 6),
                 "chroma_reduced_rate": round(float(fg["chroma_reduced_rate"]), 6),
                 "mask_reverted_pixels": int(fg["mask_reverted_pixels"]),
                 "iou_raw": round(float(fg["iou_raw"]), 6),
                 "target_hue_deg": round(float(fg["target_hue_deg"]), 3),
                 "target_chroma": round(float(fg["target_chroma"]), 4)})
    return img, info


def legacy_calib_smooth(img: np.ndarray, red_m: np.ndarray, dpi: int) -> tuple[np.ndarray, dict]:
    """上轮 C 的印泥算子（对照）：`render_page_2400.color_uniformity`（保 ΣRGB 向全页均色）＋ 保边平滑。"""
    cm = vs.ink_chroma_mean(img, red_m)
    img, _t, n_inv = rp.color_uniformity(img, red_m, cm, CALIB_STRENGTH_LEGACY)
    rad = mm2px_int(GUIDE_RADIUS_MM, dpi)
    y = vs.lum(img)
    sm = vs.guided_smooth_color(img, y, rad, GUIDE_EPS)
    img = img.copy()
    img[red_m] = sm[red_m]
    del sm
    return img, {"impl": "render_page_2400.color_uniformity + guided（上轮 C 口径）",
                 "strength": CALIB_STRENGTH_LEGACY,
                 "chroma_mean": [round(v, 6) for v in cm], "skipped_invalid_domain_px": int(n_inv),
                 "guide_radius_px": rad}


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. 版本管线（页面尺度 / 区域尺度同一实现）
# ══════════════════════════════════════════════════════════════════════════════════════
INK_MODES = {
    "C_old":       {"bg": "old",  "ink": "legacy"},      # 上轮 C（反例 / 对照）
    "C2_chroma":   {"bg": "old",  "ink": "v3"},          # 只换印泥校准（纹理仍为像素常量）
    "C2_CONS":     {"bg": "CONS", "ink": "v3"},
    "C2_MID":      {"bg": "MID",  "ink": "v3"},
    "C2_OBV":      {"bg": "OBV",  "ink": "v3"},
}


def paper_for(mode: str, h: int, w: int, dpi: int, amp_level: float = 1.0) -> np.ndarray:
    bg = INK_MODES[mode]["bg"]
    if bg == "old":
        cols = np.arange(0, w, dtype=np.int64)
        out = np.empty((h, w, 3), np.uint8)
        for y0 in range(0, h, 384):
            y1 = min(y0 + 384, h)
            out[y0:y1] = vs.to_u8(old_paper_field(np.arange(y0, y1, dtype=np.int64), cols, dpi))
        return out
    return gen_paper_mm(h, w, dpi, bg, amp_level=amp_level)


def run_variant(mode: str, src: np.ndarray, mk: dict, dpi: int, paper: np.ndarray,
                ink_ops_on: bool = True, ink_order: str = "smooth_then_chroma") -> tuple[np.ndarray, dict]:
    """C2 版管线（float32 域；返回 uint8 图与读数）。与 dpi 无关（尺度参数全 mm→px）。

    结构冻结：结构算子（保边平滑 / 印泥校准）**只写红墨区**；白线区（白文印白线，在掩膜内）与
    掩膜外对「本版观感基线（`ink_ops_on=False`）」逐像素差＝0。
    """
    t0 = time.time()
    img = src.astype(np.float32).copy()
    red_m, white_m = mk["red"], mk["white"]
    rd: dict = {"mode": mode, "dpi": dpi, "bg_source": INK_MODES[mode]["bg"],
                "ink_source": INK_MODES[mode]["ink"]}
    if mode != "C_old":                                   # C_old 走 legacy（不再叠光场/色调），保持与上轮 C 一致
        img, rd["light_field"] = field_gain_mm(img, mk["paper_rule"], dpi)
        img, rd["tone_map"] = tone_map_mm(img, mk["paper_rule"], dpi)
    bg_zone = mk["bg_zone"]
    img[bg_zone] = paper.astype(np.float32)[bg_zone]
    blur = cv2.GaussianBlur(img, (0, 0), mm2px(MICRO_SIGMA_MM, dpi))
    img[bg_zone] = img[bg_zone] + np.float32(PAPER_MICRO_AMOUNT) * (img - blur)[bg_zone]
    del blur
    ink_mean = img[red_m].astype(np.float64).mean(axis=0) if red_m.any() else None
    # 渗透感（换底纸底上的外缘环带；色＝换底后、结构算子前的印泥均值 ⇒ 冻结参考两侧一致）
    if mode != "C_old" and ink_mean is not None:
        d_out = mk["dist_outside"]
        band_px, outer_px, tau_px = mm2px(HALO_BAND_MM, dpi), mm2px(HALO_BAND_OUTER_MM, dpi), mm2px(PEN_TAU_MM, dpi)
        a = np.where((d_out > band_px) & (d_out <= outer_px),
                     PEN_ALPHA_MAX * np.exp(-(d_out - band_px) / tau_px), 0.0).astype(np.float32)
        a = a * (bg_zone.astype(np.float32) & (~red_m))
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        rd["penetration"] = {"alpha_max": PEN_ALPHA_MAX, "tau_mm": round(PEN_TAU_MM, 4),
                             "tau_px": round(tau_px, 2), "band_mm": [round(HALO_BAND_MM, 4), round(HALO_BAND_OUTER_MM, 4)],
                             "band_px": [round(band_px, 2), round(outer_px, 2)], "px": int((a > 0).sum())}
        del a
    # 晕染（各版同规：掩膜外侧环带、α≤8%、线性衰减）
    if ink_mean is not None:
        band_px = mm2px(HALO_BAND_MM, dpi)
        d_out = mk["dist_outside"]
        a = np.where(~mk["body"], np.clip((band_px + 1.0 - d_out) / band_px, 0.0, 1.0) * sc.HALO_ALPHA_MAX,
                     0.0).astype(np.float32)
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        rd["halo"] = {"band_mm": round(HALO_BAND_MM, 4), "band_px": round(band_px, 2),
                      "alpha_max": sc.HALO_ALPHA_MAX, "px": int((a > 0).sum()),
                      "alpha_inside_mask_max": 0.0}
        del a
    if ink_ops_on and red_m.any():
        if INK_MODES[mode]["ink"] == "legacy":
            img, rd["ink_ops"] = legacy_calib_smooth(img, red_m, dpi)
        else:
            img, rd["ink_ops"] = ink_chroma_ops(img, red_m, dpi, ink_order)
    out = vs.to_u8(img)
    del img
    rd["elapsed_s"] = round(time.time() - t0, 2)
    return out, rd


# ══════════════════════════════════════════════════════════════════════════════════════
# 7. 掩膜（页面尺度 / 区域尺度）
# ══════════════════════════════════════════════════════════════════════════════════════
def page_masks(src300: np.ndarray, dpi: int) -> dict:
    """页面尺度掩膜（@dpi）。red/white/body/outside/paper_rule/bg_zone/dist_outside。"""
    U = dpi // SCAN_DPI
    seg = sc.seal_mask(src300)
    red300, body300 = seg["raw"], (seg["mask"] | seg["holes"])
    paper300, ink300 = rp.build_masks(src300)
    assert np.array_equal(ink300, red300), "rp.build_masks 与 seal_canvas.seal_mask 印泥掩膜不一致"
    h, w = SRC_H * U, SRC_W * U
    red = rp.upsample_mask(red300, (w, h))
    body = rp.upsample_mask(body300, (w, h))
    pr = rp.upsample_mask(paper300, (w, h)) & ~body
    white, outside = body & ~red, ~body
    mk = {"red": red, "white": white, "body": body, "outside": outside,
          "paper_rule": pr, "red_u8": red.astype(np.uint8),
          "dist_outside": cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)}
    mk["bg_zone"] = bg_zone_for(mk, src300, U)
    return mk


def bg_zone_for(mk: dict, src300: np.ndarray, U: int) -> np.ndarray:
    """上轮 C 的换底判据（生产纸底判据 ∧ 非掩膜体）——与 round1 一致，只是按 dpi 换算。"""
    return mk["paper_rule"]


def region_masks(src300: np.ndarray, box300: tuple[int, int, int, int], dpi: int,
                 margin: int = 8) -> tuple[dict, tuple[int, int, int, int]]:
    """区域尺度掩膜（@dpi）：源/掩膜都带 margin 上采样后裁到精确区域（避免边缘缺邻域）。"""
    U = dpi // SCAN_DPI
    x0, y0, x1, y1 = box300
    sx0, sy0 = max(0, x0 - margin), max(0, y0 - margin)
    sx1, sy1 = min(SRC_W, x1 + margin), min(SRC_H, y1 + margin)
    seg = sc.seal_mask(src300)
    red300, body300 = seg["raw"], (seg["mask"] | seg["holes"])
    paper300, _ = rp.build_masks(src300)
    size = ((sx1 - sx0) * U, (sy1 - sy0) * U)
    oslice = (slice((y0 - sy0) * U, (y0 - sy0) * U + (y1 - y0) * U),
              slice((x0 - sx0) * U, (x0 - sx0) * U + (x1 - x0) * U))
    red = rp.upsample_mask(red300[sy0:sy1, sx0:sx1], size)[oslice]
    body = rp.upsample_mask(body300[sy0:sy1, sx0:sx1], size)[oslice]
    pr = rp.upsample_mask(paper300[sy0:sy1, sx0:sx1], size)[oslice] & ~body
    white, outside = body & ~red, ~body
    mk = {"red": red, "white": white, "body": body, "outside": outside, "paper_rule": pr,
          "red_u8": red.astype(np.uint8),
          "dist_outside": cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)}
    mk["bg_zone"] = mk["paper_rule"]
    return mk, (sx0, sy0, sx1, sy1)


def source_region(src300: np.ndarray, box300: tuple[int, int, int, int], dpi: int,
                  margin: int = 8) -> np.ndarray:
    """区域源图（@dpi）：源带 margin 的 Lanczos 上采样后裁到精确区域（与产线同一重采样链）。"""
    U = dpi // SCAN_DPI
    x0, y0, x1, y1 = box300
    sx0, sy0 = max(0, x0 - margin), max(0, y0 - margin)
    sx1, sy1 = min(SRC_W, x1 + margin), min(SRC_H, y1 + margin)
    up = rp.lanczos_up(src300[sy0:sy1, sx0:sx1], ((sx1 - sx0) * U, (sy1 - sy0) * U))
    return up[(y0 - sy0) * U: (y0 - sy0) * U + (y1 - y0) * U,
              (x0 - sx0) * U: (x0 - sx0) * U + (x1 - x0) * U].astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════════════
# 8. 拼板
# ══════════════════════════════════════════════════════════════════════════════════════
def panel_grid(rows: list[list[np.ndarray]], row_labels: list[str], col_labels: list[str],
               path: Path, gap: int = PANEL_GAP, label_h: int = LABEL_H,
               left_w: int = LEFT_W, bg: int = 38) -> dict:
    ncol = max(len(r) for r in rows)
    widths = [max(p.shape[1] for p in r if p is not None and i < len(r) and r[i] is not None)
              for i in range(ncol)] if rows else []
    widths = []
    for i in range(ncol):
        widths.append(max((r[i].shape[1] for r in rows if i < len(r) and r[i] is not None), default=1))
    heights = [max((p.shape[0] for p in r if p is not None), default=1) for r in rows]
    W = left_w + sum(widths) + gap * ncol
    H = label_h + sum(h + gap for h in heights)
    canvas = np.full((H, W, 3), bg, np.uint8)
    y = label_h
    for r, h in zip(rows, heights):
        x = left_w + gap
        for i, p in enumerate(r):
            if p is not None:
                p3 = p if p.ndim == 3 else np.repeat(p[:, :, None], 3, axis=2)
                canvas[y:y + p3.shape[0], x:x + p3.shape[1]] = p3
            x += widths[i] + gap
        y += h + gap
    im = Image.fromarray(canvas)
    d = ImageDraw.Draw(im)
    x = left_w + gap
    for i, c in enumerate(col_labels):
        d.text((x + 4, 5), str(c), fill=(255, 255, 255))
        x += widths[i] + gap
    y = label_h
    for r, h in zip(row_labels, heights):
        d.text((6, y + h // 2 - 6), str(r), fill=(255, 255, 255))
        y += h + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="PNG", compress_level=6)
    return {"path": str(path), "bytes": int(path.stat().st_size), "sha256": vs.sha256_file(path),
            "size_px": [im.width, im.height]}


def patch_paper(cand: str | None, dpi: int, field_mm: float, amp_level: float = 1.0,
                scale_extra: float = 1.0, origin_mm: tuple[float, float] = (40.0, 25.0)) -> np.ndarray:
    """生成一块纯纸底（同一**物理原点** ⇒ 不同 dpi 是同一物理场的不同采样）。"""
    n = mm2px_int(field_mm, dpi)
    y0_px = mm2px_int(origin_mm[1], dpi)
    x0_px = mm2px_int(origin_mm[0], dpi)
    rows = np.arange(y0_px, y0_px + n, dtype=np.int64)
    cols = np.arange(x0_px, x0_px + n, dtype=np.int64)
    f = (paper_field_mm(rows, cols, dpi, cand, amp_level, scale_extra)
         if cand is not None else old_paper_field(rows, cols, dpi))
    return vs.to_u8(f)


def paper_lum_residual(patch_u8: np.ndarray) -> np.ndarray:
    """纸底亮度残差（去基色）——供谱/自相关读数。"""
    y = vs.lum(patch_u8.astype(np.float32))
    return y - float(y.mean())


# ══════════════════════════════════════════════════════════════════════════════════════
# 9. 主流程
# ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t00 = time.time()
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    readings: dict = {}
    samples: dict[str, dict] = {}

    # ── 0) 溯源自证 ───────────────────────────────────────────────────────────────────
    md5 = rp.source_jpeg_md5(PDF, XREF)
    prod = json.loads(PROD_READINGS.read_text())
    r1 = json.loads(ROUND1_READINGS.read_text())
    assert md5 == prod["source"]["embedded_jpeg_md5"] == r1["source"]["embedded_jpeg_md5"]
    print(f"[0] provenance md5={md5} ✓（产线 & 上轮同源）", flush=True)

    src300 = rp.load_scan(PDF, XREF)
    assert src300.shape[:2] == (SRC_H, SRC_W)

    # ── 1) 纹理对比板：600 vs 2400 vs 2400÷4（同一物理视野，1:1） ─────────────────────
    u4 = 4
    rows_board: list[list] = []
    row_labels: list[str] = []
    board_readouts: dict = {}
    stat_field = TEX_STAT_FIELD_MM

    def board_row(tag: str, cand: str | None, amp_level: float, scale_extra: float) -> None:
        p600 = patch_paper(cand, 600, TEX_FIELD_MM, amp_level, scale_extra)
        p2400 = patch_paper(cand, 2400, TEX_FIELD_MM, amp_level, scale_extra)
        p2400_4 = cv2.resize(p2400, (p2400.shape[1] // u4, p2400.shape[0] // u4),
                             interpolation=cv2.INTER_AREA)
        rows_board.append([p600, p2400, p2400_4])
        row_labels.append(tag)
        s600 = patch_paper(cand, 600, stat_field, amp_level, scale_extra)
        s2400 = patch_paper(cand, 2400, stat_field, amp_level, scale_extra)
        r600 = tex_alignment_readout(paper_lum_residual(s600), 600, stat_field)
        r2400 = tex_alignment_readout(paper_lum_residual(s2400), 2400, stat_field)
        board_readouts[tag] = {
            "candidate": cand, "amp_level": amp_level, "scale_extra": scale_extra,
            "readout_600": r600, "readout_2400": r2400,
            "cross_dpi_600_vs_2400": tex_cross_dpi_sim(s2400, s600),
            "mm_consistency": {
                "autocorr_x_ratio_2400_over_600": _ratio(r2400["autocorr_half_decay_mm"]["x"],
                                                         r600["autocorr_half_decay_mm"]["x"]),
                "autocorr_y_ratio_2400_over_600": _ratio(r2400["autocorr_half_decay_mm"]["y"],
                                                         r600["autocorr_half_decay_mm"]["y"]),
                "psd_centroid_ratio_2400_over_600": _ratio(r2400["psd_centroid_cyc_per_mm"],
                                                           r600["psd_centroid_cyc_per_mm"]),
                "psd_peak_wavelength_ratio_2400_over_600": _ratio(r2400["psd_peak_wavelength_mm"],
                                                                  r600["psd_peak_wavelength_mm"]),
            },
            "octaves_600": octave_spec(cand, 600, scale_extra) if cand else None,
            "octaves_2400": octave_spec(cand, 2400, scale_extra) if cand else None,
        }
        print(f"[board] {tag}: ac600={r600['autocorr_half_decay_mm']} ac2400="
              f"{r2400['autocorr_half_decay_mm']} cen600={r600['psd_centroid_cyc_per_mm']} "
              f"cen2400={r2400['psd_centroid_cyc_per_mm']}", flush=True)

    board_row("旧·像素常量(反例)", None, 1.0, 1.0)
    for c in CAND_ORDER:
        for al in AMP_LEVELS:
            board_row(f"C2·{c}({CANDIDATES[c]['label']})×{al:g}", c, al, 1.0)
    bp = panel_grid(rows_board, row_labels,
                    ["600dpi 1:1（8mm）", "2400dpi 1:1（同 8mm）", "2400dpi ÷4（回到 600 像素密度）"],
                    SAMPLES_DIR / "tex-board-round2.png")
    samples["tex_board"] = bp
    print(f"[board] {bp['size_px']} {bp['bytes']}B", flush=True)

    # ── 2) 页面尺度 @600dpi：源 / 掩膜 / 各版 ─────────────────────────────────────────
    src600 = rp.lanczos_up(src300, (SRC_W * 2, SRC_H * 2))
    src600_u8 = vs.to_u8(src600)
    mk = page_masks(src300, COMP_DPI)
    gray6, sat6 = vs.lum(src600_u8), vs.sat_of(src600_u8)
    dark_core = mk["outside"] & (gray6 < DARK_CORE)
    text_protect = cv2.dilate(dark_core.astype(np.uint8),
                              np.ones((2 * TEXT_PROTECT_PX + 1,) * 2, np.uint8)) > 0
    print(f"[masks600] red={int(mk['red'].sum())} white={int(mk['white'].sum())} "
          f"outside={int(mk['outside'].sum())} paper_rule={int(mk['paper_rule'].sum())}", flush=True)

    # 区域定义（@300dpi）：C1/C2 外扩 60；纯纸底补丁＝确定性搜索（同 round1 口径）
    c1 = (C1_BBOX[0] - 60, C1_BBOX[1] - 60, C1_BBOX[2] + 60, C1_BBOX[3] + 60)
    c2 = (C2_BBOX[0] - 60, C2_BBOX[1] - 60, C2_BBOX[2] + 60, C2_BBOX[3] + 60)
    step, pp = 20, 600
    indicator = (mk["red"] | dark_core | mk["body"]).astype(np.float32)
    S = cv2.boxFilter(indicator, -1, (pp, pp), normalize=False, borderType=cv2.BORDER_CONSTANT)
    H6, W6 = SRC_H * 2, SRC_W * 2
    valid = S[(pp // 2):(H6 - pp + pp // 2):step, (pp // 2):(W6 - pp + pp // 2):step]
    iy, ix = np.unravel_index(int(np.argmin(valid)), valid.shape)
    cy, cx = int(iy) * step + pp // 2, int(ix) * step + pp // 2
    paper_reg600 = (cx - pp // 2, cy - pp // 2, cx + pp // 2, cy + pp // 2)
    regions = {"P29-C1R1": c1, "P29-C2R1": c2,
               "P29-paper": (paper_reg600[0] // 2, paper_reg600[1] // 2,
                             paper_reg600[2] // 2, paper_reg600[3] // 2)}
    print(f"[regions] C1={c1} C2={c2} paper(300dpi)={regions['P29-paper']}", flush=True)

    # 印泥核心像素集合（**源图上**取，全版共用同一集合 ⇒ 可比）＋ 冻结基线
    core = cc.ink_core_centroid(src600_u8)
    core_mask = core["mask"]
    core_px_src = src600_u8[core_mask].astype(np.float64)
    print(f"[ink] core_px={int(core_mask.sum())} centroid={tuple(round(v,2) for v in core['rgb'])} "
          f"ΔE_to_target={cc.delta_e2000(core['rgb'], cc.TARGET_RGB):.4f}", flush=True)

    variants: dict[str, np.ndarray] = {}
    vread: dict[str, dict] = {}
    papers_meta: dict[str, dict] = {}
    for mode in ("C_old", "C2_chroma", "C2_CONS", "C2_MID", "C2_OBV"):
        t = time.time()
        paper = paper_for(mode, H6, W6, COMP_DPI)
        v, rd = run_variant(mode, src600, mk, COMP_DPI, paper)
        v2, _ = run_variant(mode, src600, mk, COMP_DPI, paper)
        ref, _ = run_variant(mode, src600, mk, COMP_DPI, paper, ink_ops_on=False)
        d_out = int(((v != ref) & (~mk["red"])[:, :, None]).sum())
        d_white = int(((v != ref) & mk["white"][:, :, None]).sum())
        rd["determinism_rerun_bit_equal"] = bool(np.array_equal(v, v2))
        rd["freeze"] = {"rule": "结构算子（印泥校准/保边平滑）只写红墨区；"
                                "白线区（白文印白线，在掩膜内）/掩膜外 对「本版观感基线」逐像素差=0",
                        "white_line_px": int(mk["white"].sum()), "white_line_mismatch_px": d_white,
                        "outside_px": int(mk["outside"].sum()), "outside_mismatch_px": d_out,
                        "assert_ok": bool(d_white == 0 and d_out == 0)}
        variants[mode] = v
        vread[mode] = rd
        papers_meta[mode] = {"bg_source": rd["bg_source"], "shape": list(paper.shape)}
        del paper, v2, ref
        print(f"[{mode}] {rd['elapsed_s']}s rerun_equal={rd['determinism_rerun_bit_equal']} "
              f"freeze_ok={rd['freeze']['assert_ok']}", flush=True)

    # 纸底生成确定性（同参重生成逐像素一致）
    p_a = paper_for("C2_MID", 256, 256, COMP_DPI)
    p_b = paper_for("C2_MID", 256, 256, COMP_DPI)
    paper_determinism = bool(np.array_equal(p_a, p_b))
    del p_a, p_b

    # ── 3) 印泥读数（核心像素 → #C95021；ΔE 走 colorcal）─────────────────────────────
    ink_readouts: dict = {
        "target": {"hex": cc.TARGET_HEX, "rgb": list(cc.TARGET_RGB), "lab": [round(v, 4) for v in TARGET_LAB],
                   "source_of_truth": "server/app/colorcal.py TARGET_RGB / TARGET_HEX（单一真源）"},
        "core_pixel_set": {"pixels": int(core_mask.sum()), "definition": "colorcal.ink_core_centroid（源图 @600dpi）",
                           "centroid_rgb_source": rgb_mean(core_px_src)},
        "delta_e_impl": "colorcal：Lab=colorcal._srgb_to_lab_arr；ΔE2000=colorcal.ciede2000_lab（同 delta_e2000 内部）",
        "per_version": {},
    }
    # 逐点复算自证：抽样 200 像素，cc.delta_e2000 与批量路径一致
    chk = core_px_src[:200]
    lab_chk = cc._srgb_to_lab_arr(chk)
    d_chk = max(abs(cc.ciede2000_lab(lab_chk[i], TARGET_LAB) - cc.delta_e2000(chk[i], cc.TARGET_RGB))
                for i in range(chk.shape[0]))
    ink_readouts["delta_e2000_public_vs_batch_max_abs_diff"] = float(d_chk)
    for mode, img in (("SRC", src600_u8), *[(m, variants[m]) for m in variants]):
        px = img[core_mask].astype(np.float64)
        ink_readouts["per_version"][mode] = {
            "delta_e_to_target": delta_e_stats(px),
            "lab": lab_stats(px),
            "core_centroid_rgb": rgb_mean(px),
            "core_centroid_delta_e_to_target": round(float(cc.delta_e2000(rgb_mean(px), cc.TARGET_RGB)), 4),
            "core_centroid_hsv": [round(v, 4) for v in cc.rgb_to_hsv(rgb_mean(px))],
        }
        print(f"[ink {mode}] ΔE med={ink_readouts['per_version'][mode]['delta_e_to_target']['median']} "
              f"p90={ink_readouts['per_version'][mode]['delta_e_to_target']['p90']} "
              f"≤5={ink_readouts['per_version'][mode]['delta_e_to_target']['leq5_rate']}", flush=True)
    ink_readouts["round1_baseline"] = {
        "note": "上轮 readings.json 未登记 ΔE→#C95021（仅 Lab 方差）；本轮补上源图与 C_old 的 ΔE 作基线",
        "src_core_centroid_rgb": list(r1.get("masks_600dpi", {}).keys())[:0] or None,
        "C_old_L_lab_stats_from_round1": None}

    # ── 4) 印面四联 @600dpi（原｜C旧｜C2靶色｜C2靶色＋纹理）───────────────────────────
    for rn in ("P29-C1R1", "P29-C2R1"):
        x0, y0, x1, y1 = [v * 2 for v in regions[rn]]
        reg = (slice(y0, y1), slice(x0, x1))
        panels = [src600_u8[reg], variants["C_old"][reg], variants["C2_chroma"][reg], variants["C2_MID"][reg]]
        fp = panel_grid([panels], ["@" + rn],
                        ["①原 600dpi", "②C旧（上轮 C）", "③C2靶色（#C95021）", "④C2靶色＋mm纹理(MID)"],
                        SAMPLES_DIR / f"{rn}-fourpanel-round2.png")
        samples[f"{rn}_fourpanel"] = fp
        x0s, y0s, x1s, y1s = regions[rn]
        sub = (slice(y0 * 2 // 2, y1 * 2 // 2), slice(x0 * 2 // 2, x1 * 2 // 2))
        samples[f"{rn}_fourpanel"]["ink_lab_round1_style"] = {
            m: vs.ink_lab_stats(variants[m][reg], mk["red"][reg])
            for m in ("C_old", "C2_chroma", "C2_MID")}
        print(f"[四联 {rn}] {fp['size_px']} {fp['bytes']}B", flush=True)

    # ── 5) 2400dpi 局部 1:1 样张（每区域；含 C旧 反例）──────────────────────────────
    win_px = 1300                                       # 1:1 窗口边长（@2400dpi ≈ 13.8 mm）
    reg2400: dict = {}
    for rn in ("P29-C1R1", "P29-C2R1"):
        t = time.time()
        box = C1_BBOX if rn == "P29-C1R1" else C2_BBOX
        src_r = source_region(src300, box, PROD_DPI)
        mk_r, _ = region_masks(src300, box, PROD_DPI)
        # 确定性选窗：印泥∪白线密度最高的 win_px 窗口（整区域尺度上取样）
        dens = cv2.boxFilter((mk_r["red"] | mk_r["white"]).astype(np.float32), -1, (win_px, win_px),
                             normalize=False, borderType=cv2.BORDER_CONSTANT)
        h, w = dens.shape
        valid = dens[win_px // 2: h - win_px // 2: 8, win_px // 2: w - win_px // 2: 8]
        iy, ix = np.unravel_index(int(np.argmax(valid)), valid.shape)
        cy, cx = int(iy) * 8 + win_px // 2, int(ix) * 8 + win_px // 2
        sl = (slice(cy - win_px // 2, cy + win_px // 2), slice(cx - win_px // 2, cx + win_px // 2))
        mk_w = {k: (v[sl] if isinstance(v, np.ndarray) and v.shape[:2] == dens.shape else v)
                for k, v in mk_r.items()}
        src_w = src_r[sl]
        red_m = mk_w["red"]
        core_w = cc.ink_core_centroid(src_w)["mask"]
        panels, reads = [], {}
        for mode in ("C_old", "C2_chroma", "C2_MID"):
            paper = paper_for(mode, src_w.shape[0], src_w.shape[1], PROD_DPI)
            v, rd = run_variant(mode, src_w, mk_w, PROD_DPI, paper)
            panels.append(v)
            px = v[core_w].astype(np.float64)
            reads[mode] = {"delta_e_to_target": delta_e_stats(px), "lab": lab_stats(px),
                           "chroma_ops": rd.get("ink_ops")}
            del paper, v
        srcw_u8 = vs.to_u8(src_w)
        fp = panel_grid([[srcw_u8] + panels], [f"@{rn} 1:1"],
                        ["①原 2400dpi", "②C旧·px常量纹理", "③C2靶色(#C95021)", "④C2靶色＋mm纹理(MID)"],
                        SAMPLES_DIR / f"{rn}-2400-1to1-round2.png", left_w=250)
        samples[f"{rn}_2400_1to1"] = fp
        reg2400[rn] = {"window_px": [win_px, win_px], "window_mm": round(px2mm(win_px, PROD_DPI), 3),
                       "window_origin_px_in_region": [int(sl[1].start), int(sl[0].start)],
                       "ink_lab_and_delta_e": reads, "src_delta_e_to_target": delta_e_stats(srcw_u8[core_w]),
                       "elapsed_s": round(time.time() - t, 1)}
        print(f"[2400 1:1 {rn}] {fp['size_px']} | ΔE(MID)="
              f"{reads['C2_MID']['delta_e_to_target']['median']} | {time.time()-t:.1f}s", flush=True)
        del src_r, mk_r, mk_w, panels

    # 纸底区域 @2400dpi：候选并列（1:1）
    x0, y0, x1, y1 = [v * 8 for v in regions["P29-paper"]]
    win = min(x1 - x0, y1 - y0, 1300)
    p_rows = []
    for lbl, mode in (("C旧·px常量", "C_old"), ("CONS", "C2_CONS"), ("MID", "C2_MID"), ("OBV", "C2_OBV")):
        x0, y0, x1, y1 = [v * 8 for v in regions["P29-paper"]]
        reg = (slice(y0, y0 + win), slice(x0, x0 + win))
        p_rows.append(variants[mode][reg])
    fp = panel_grid([p_rows], ["@paper 1:1"],
                    ["①C旧·px常量", "②C2·CONS", "③C2·MID", "④C2·OBV"],
                    SAMPLES_DIR / "P29-paper-2400-1to1-round2.png", left_w=170)
    samples["P29-paper_2400_1to1"] = fp
    print(f"[2400 1:1 paper] {fp['size_px']}", flush=True)

    # ── 6) 整页缩略（800px 宽）：原｜C旧｜C2 三候选 ─────────────────────────────────
    th = (THUMB_W, round(H6 * THUMB_W / W6))
    thumbs = [np.asarray(Image.fromarray(p).resize(th, Image.Resampling.LANCZOS)) for p in
              (src600_u8, variants["C_old"], variants["C2_CONS"], variants["C2_MID"], variants["C2_OBV"])]
    tp = panel_grid([thumbs], ["@整页"],
                    ["①原(600dpi)", "②C旧(上轮C)", "③C2·CONS", "④C2·MID", "⑤C2·OBV"],
                    SAMPLES_DIR / "P29-thumb-round2.png", left_w=150)
    samples["thumb"] = tp
    print(f"[thumb] {tp['size_px']} {tp['bytes']}B", flush=True)

    # ── 7) 换算表 + 读数落盘 ─────────────────────────────────────────────────────────
    scale_rows = []
    for lbl, mm in (("云斑 mottle", TEX_MOTTLE_MM), ("粗纤维长轴", TEX_FIB_COARSE_LEN_MM),
                    ("粗纤维短轴", TEX_FIB_COARSE_LEN_MM / TEX_ANISO_RATIO),
                    ("细纤维长轴", TEX_FIB_FINE_LEN_MM), ("细纤维短轴", TEX_FIB_FINE_LEN_MM / TEX_ANISO_RATIO),
                    ("颗粒 grain", TEX_GRAIN_MM), ("微纤维网 micro", TEX_MICRO_FIB_MM),
                    ("（参考）真实纤维宽上沿", 0.08), ("（参考）真实纤维宽下沿", 0.02),
                    ("保边平滑半径", GUIDE_RADIUS_MM), ("光场 σ", FIELD_SIGMA_MM),
                    ("微对比 σ", MICRO_SIGMA_MM), ("晕染环带", HALO_BAND_MM), ("渗透 τ", PEN_TAU_MM)):
        row = {"item": lbl, "mm": round(mm, 5)}
        for d in DPI_TABLE:
            row[f"px@{d}"] = round(mm2px(mm, d), 3)
        row["dpi_ok"] = "".join("O" if mm2px(mm, d) >= 2 else "x" for d in DPI_TABLE)
        scale_rows.append(row)
    for lbl, pxv in (("旧·粗纤维长轴(px常量)", OLD_TEX["long_px"]), ("旧·粗纤维短轴", OLD_TEX["short_px"]),
                     ("旧·粗纤维2长轴", OLD_TEX["long2_px"]), ("旧·粗纤维2短轴", OLD_TEX["short2_px"])):
        row = {"item": lbl, "mm_at_600": round(px2mm(pxv, 600), 5)}
        for d in DPI_TABLE:
            row[f"mm@{d}"] = round(px2mm(pxv, d), 5)
        row["dpi_ok"] = "像素常量 ⇒ 物理尺度随 dpi 变（反例）"
        scale_rows.append(row)

    def md_table(rows: list[dict], cols: list[str]) -> str:
        head = "| " + " | ".join(cols) + " |\n| " + " | ".join("---" for _ in cols) + " |\n"
        body = "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)
        return head + body

    cand_rows = []
    for c in CAND_ORDER:
        cfg = CANDIDATES[c]
        s600 = octave_spec(c, 600)
        cand_rows.append({
            "候选": c, "档": cfg["label"], "尺度×": cfg["scale"], "幅度×": cfg["amp"],
            "云斑 mm": round(s600[0]["long_mm"], 3),
            "粗纤维长/短 mm": f"{s600[1]['long_mm']:.3f} / {s600[1]['short_mm']:.3f}",
            "细纤维长/短 mm": f"{s600[2]['long_mm']:.3f} / {s600[2]['short_mm']:.3f}",
            "颗粒 mm": round(s600[3]["long_mm"], 3),
            "标称 RMS(0–255)": round(float(np.sqrt(sum((o["amp_scaled"]) ** 2 for o in s600))), 3),
        })
    scale_md = ["# C2 纹理换算表（mm ↔ px @300/600/1200/2400）\n",
                "> 真源：`ops/variant-samples/round2_samples.py` 顶部常量（**一律 mm**，单点可改）。",
                "> `dpi_ok`：O＝最短轴 ≥2px（可表示）；x＝<2px（该 dpi 下不可表示，观感自然退化）。\n",
                "## 1. 纹理/算子尺度\n", md_table(scale_rows, ["item", "mm", "px@300", "px@600", "px@1200", "px@2400", "dpi_ok"]),
                "\n## 2. 旧口径（像素常量）的物理尺度漂移（反例）\n",
                md_table([r for r in scale_rows if "旧·" in r["item"]],
                         ["item", "mm_at_600", "mm@300", "mm@600", "mm@1200", "mm@2400", "dpi_ok"]),
                "\n## 3. 三组候选（尺度与幅度梯度）\n",
                md_table(cand_rows, ["候选", "档", "尺度×", "幅度×", "云斑 mm", "粗纤维长/短 mm",
                                     "细纤维长/短 mm", "颗粒 mm", "标称 RMS(0–255)"]),
                "\n## 4. dpi 对齐读数（同一物理视野 12mm 的统计）\n"]
    for tag, br in board_readouts.items():
        r6, r24 = br["readout_600"], br["readout_2400"]
        scale_md.append(f"\n**{tag}**：自相关半衰 600dpi x={r6['autocorr_half_decay_mm']['x']}mm / "
                        f"y={r6['autocorr_half_decay_mm']['y']}mm ↦ 2400dpi x={r24['autocorr_half_decay_mm']['x']}mm / "
                        f"y={r24['autocorr_half_decay_mm']['y']}mm；谱质心 {r6['psd_centroid_cyc_per_mm']} ↦ "
                        f"{r24['psd_centroid_cyc_per_mm']} cyc/mm；峰值波长 {r6['psd_peak_wavelength_mm']} ↦ "
                        f"{r24['psd_peak_wavelength_mm']} mm；2400÷4 vs 600 逐像素 MAE "
                        f"{br['cross_dpi_600_vs_2400']['mean_abs_diff_lum']}\n")
    SCALE_TABLE_PATH.write_text("".join(scale_md) + "\n", encoding="utf-8")

    readings = {
        "schema": "feicui.variant-samples.readings-round2.v1",
        "generator": "ops/variant-samples/round2_samples.py",
        "page": PAGE,
        "intent": "C（实拍观感）修正版：①纹理改物理尺度(mm)定义＋多尺度带限噪声（3 候选×幅度档）"
                  "②印泥校准改向基准色 #C95021 靠（复用 colorcal V3 色度函数、保 L*）",
        "source": {"pdf": str(PDF.relative_to(REPO)), "xref": XREF, "embedded_jpeg_md5": md5,
                   "matches_production_and_round1": True, "size_px": [SRC_W, SRC_H], "dpi": SCAN_DPI},
        "geometry": {"compare_dpi": COMP_DPI, "prod_dpi": PROD_DPI, "regions_300dpi": {k: list(v) for k, v in regions.items()},
                     "src_render_600": "内嵌 JPEG 300dpi ×2 Lanczos；2400dpi = ×8（与产线同一重采样链）"},
        "target_hex_confirm": {"TARGET_HEX": cc.TARGET_HEX, "TARGET_RGB": list(cc.TARGET_RGB),
                               "from": "server/app/colorcal.py（import，不复制常量）",
                               "hex_to_rgb_roundtrip": list(cc.hex_to_rgb(cc.TARGET_HEX))},
        "texture_truth": {
            "unit": "mm", "aniso_ratio": TEX_ANISO_RATIO, "seed": SEED,
            "octaves_nominal_mm": {"mottle": TEX_MOTTLE_MM, "fiber_coarse_len": TEX_FIB_COARSE_LEN_MM,
                                   "fiber_fine_len": TEX_FIB_FINE_LEN_MM, "grain": TEX_GRAIN_MM,
                                   "fiber_micro": TEX_MICRO_FIB_MM,
                                   "micro_min_dpi": TEX_MICRO_MIN_DPI},
            "amp_nominal": {"mottle": AMP_MOTTLE, "fiber_coarse": AMP_FIB_COARSE,
                            "fiber_fine": AMP_FIB_FINE, "grain": AMP_GRAIN, "micro": AMP_MICRO},
            "candidates": {c: CANDIDATES[c] for c in CAND_ORDER},
            "amp_levels": list(AMP_LEVELS),
            "position_hash": "render_page_2400._hash64（位置哈希 ⇒ 无重复周期、与分块顺序无关）",
            "lattice_space": "mm（vnoise_mm）⇒ 物理尺度与 dpi 无关",
            "dropped_from_round1": "BG_GRAIN_SIGMA·白高斯颗粒（1px 相关长度＝dpi 依赖项）已由 0.16mm grain octave 取代",
        },
        "dpi_alignment": {"board": "output/samples/book-page-2400-variants/round2/tex-board-round2.png",
                          "field_mm_visible": TEX_FIELD_MM, "field_mm_statistics": TEX_STAT_FIELD_MM,
                          "criterion": "同一物理尺度纹理在 600 与 2400dpi 上：自相关半衰长度(mm)/谱质心(cyc/mm)/"
                                       "峰值波长(mm) 换算后必须相等（比值≈1）；另做 2400÷4 vs 600 逐像素对照",
                          "rows": board_readouts},
        "ink_color": ink_readouts,
        "masks_600dpi": {"red_ink_px": int(mk["red"].sum()), "white_line_px": int(mk["white"].sum()),
                         "white_line_inside_red_independent": True,
                         "outside_px": int(mk["outside"].sum()), "paper_rule_px": int(mk["paper_rule"].sum()),
                         "impl": "colorcal.ink_mask → seal_canvas.seal_mask → ×2 Lanczos(≥128)"},
        "params": {"guide_radius_mm": GUIDE_RADIUS_MM, "guide_eps": GUIDE_EPS,
                   "field_sigma_mm": FIELD_SIGMA_MM, "micro_sigma_mm": MICRO_SIGMA_MM,
                   "halo_band_mm": HALO_BAND_MM, "pen_tau_mm": PEN_TAU_MM, "scurve_t": SCURVE_T,
                   "paper_micro_amount": PAPER_MICRO_AMOUNT, "seed": SEED,
                   "v3_fg_chroma_strength": float(cc.V3_FG_CHROMA_STRENGTH)},
        "variants": vread,
        "papers_meta": papers_meta,
        "paper_generation_determinism_bit_equal": paper_determinism,
        "region_2400_1to1": reg2400,
        "samples": samples,
        "scale_table_md": str(SCALE_TABLE_PATH),
        "elapsed_s": round(time.time() - t00, 1),
    }
    READINGS_PATH.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = (all(vread[m]["freeze"]["assert_ok"] and vread[m]["determinism_rerun_bit_equal"] for m in variants)
          and paper_determinism and abs(d_chk) < 1e-12)
    print(json.dumps({"ok": ok, "freeze": {m: vread[m]["freeze"]["assert_ok"] for m in variants},
                      "rerun_equal": {m: vread[m]["determinism_rerun_bit_equal"] for m in variants},
                      "paper_determinism": paper_determinism,
                      "delta_e_public_eq_batch": float(d_chk),
                      "elapsed_s": readings["elapsed_s"]}, ensure_ascii=False, indent=2), flush=True)
    return 0 if ok else 1


def _ratio(a, b) -> float | None:
    if a is None or b is None or float(b) == 0.0:
        return None
    return round(float(a) / float(b), 4)


if __name__ == "__main__":
    raise SystemExit(main())
