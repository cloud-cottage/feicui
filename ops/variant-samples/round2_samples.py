#!/usr/bin/env python
"""C2 修正版样张（Kong · ops/variant-samples/round2_samples.py）。

【本单两条硬修正（Kevin 定 C 为方向后）】
  修正 1 纹理按**物理尺度（mm）**定义、按目标 dpi 换算；升级为**多尺度带限噪声**（4 octave：
        成形云斑/粗纤维/细纤维/颗粒；弱各向异性、极低对比、无重复）；出 3 组候选；
        600 与 2400dpi **1:1 并排**做 dpi 对齐硬判据（自相关长度/谱质心/峰值波长换算 mm 后必须相等）。
  修正 2 印泥校准由「向全页印泥均色收敛」改为**向基准色 `#C95021` 靠**：
        复用 `server/app/colorcal.py` 的 V3 前景色度函数（保 L*），单一真源、只 import。
【第三、四条输入（Kevin 追加）】
  豆包参照图 #1（纸纹理/印泥色/晕染过渡）＋ #2（**只看印泥质感**）⇒ 候选参数据此**标定**（不再盲目梯度）。
  「钤盖均匀」≠ 平涂一致 ⇒ 保边平滑改**可调档**，并新增语义浓淡/颗粒/半透/毛糙/窄晕染/哑光算子；
  出**严格档（只动色度、保 L*）**与**观感档（允许按语义调制 L*）**两套样张。
  硬限制：豆包图为生成式输出、已重绘印文 ⇒ **只对标纸纹理/印泥色彩/晕染过渡**，**不对标字形与线条锐度**。

不等式口径：结构算子（印泥校准/平滑/语义/颗粒/半透/毛糙）**只写红墨区**；白线区（白文印白线，在掩膜内）
与掩膜外对「本版观感基线」逐像素差＝0；红墨掩膜本身**逐像素不变**（毛糙/半透只通过近边**颜色**实现，
不移动掩膜 ⇒ 字形/结构零改动）；同参重跑逐像素一致。

红线：不写 yinpu.db／不建 job／2_HighRes_PDF 与 output/books 只读／样张只落
output/samples/book-page-2400-variants/round2/／可入库件只落 ops/variant-samples/／
生产常量与实现一律 import 复用（`render_page_2400`、`app.seal_canvas`、`app.colorcal`、
`variants_samples`、`doubao_ink_reference`），不复制第二份。

跑法：cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/variant-samples/round2_samples.py
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
sys.path.insert(0, str(REPO / "server"))
sys.path.insert(0, str(REPO / "ops" / "book-page-2400"))
sys.path.insert(0, str(REPO / "ops" / "variant-samples"))
import render_page_2400 as rp                                     # noqa: E402  生产整页实现（只读复用）
from app import seal_canvas as sc                                 # noqa: E402  宣纸色域/种子常量单一真源
from app import colorcal as cc                                    # noqa: E402  靶色 / V3 色度函数单一真源
import variants_samples as vs                                     # noqa: E402  上轮 C 版与工具（只读复用）
import doubao_ink_reference as dr                                 # noqa: E402  印泥特征度量（与豆包图同一套）
from crop_c2r1 import extract_region_u16                          # noqa: E402  strip 级解码先例

# ══════════════════════════════════════════════════════════════════════════════════════
# 0. 几何 / 路径
# ══════════════════════════════════════════════════════════════════════════════════════
PDF = REPO / "output" / "1_Original_PDF" / "秦印类编 检索版.pdf"
PAGE, XREF = 29, 112
SCAN_DPI = 300
SRC_W, SRC_H = 2125, 3059
COMP_DPI = 600
PROD_DPI = 2400
MAIN_TIF = REPO / "output/2_HighRes_PDF/9787550847224/P29-2400dpi-48bit.tif"
PROD_READINGS = REPO / "ops/book-page-2400/readings-P29-2400dpi-48bit.json"
ROUND1_READINGS = REPO / "ops/variant-samples/readings.json"
DOUBAO_PAPER = REPO / "ops/variant-samples/doubao-reference-features.json"
DOUBAO_INK = REPO / "ops/variant-samples/doubao-ink-reference-features.json"
SAMPLES_DIR = REPO / "output/samples/book-page-2400-variants/round2"
OPS_DIR = Path(__file__).resolve().parent
READINGS_PATH = OPS_DIR / "readings-round2.json"
SCALE_TABLE_PATH = OPS_DIR / "scale-table-round2.md"

MM_PER_IN = 25.4
SEED = sc.BG_SEED_DEFAULT
DPI_TABLE = (300, 600, 1200, 2400)

C1_BBOX = (533, 555, 798, 823)
C2_BBOX = (1422, 560, 1565, 820)

# 我们的 2400dpi 标尺（C1-R1 白文大方印印面）
W_O_PX, W_O_MM = 2120, 22.437

DARK_CORE, TEXT_PROTECT_PX = 150, 2
THUMB_W, PANEL_GAP, LABEL_H, LEFT_W = 800, 10, 22, 210


def mm2px(mm, dpi):
    return float(mm) / MM_PER_IN * float(dpi)


def px2mm(px, dpi):
    return float(px) * MM_PER_IN / float(dpi)


def mm2px_int(mm, dpi):
    return max(1, int(round(mm2px(mm, dpi))))


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. 豆包标定（唯一路径：读两份证据件；不手抄第二份常量）
# ══════════════════════════════════════════════════════════════════════════════════════
def load_calibration() -> dict:
    """读豆包证据件 → 标定参数（算式全部登记在案）。"""
    assert DOUBAO_PAPER.is_file() and DOUBAO_INK.is_file(), \
        f"缺证据件：{DOUBAO_PAPER} / {DOUBAO_INK}（先跑 doubao_reference.py / doubao_ink_reference.py）"
    P = json.loads(DOUBAO_PAPER.read_text())
    I = json.loads(DOUBAO_INK.read_text())
    pt, ft = P["paper_texture"], I["features"]
    W_d = P["ruler"]["W_d_px"]
    f_d = pt["f_d_px"]
    band_pk = pt["band_peak_wavelength_px_median"]
    band_rms = pt["band_rms_median_0_255"]
    pk2mm = lambda px: px * W_O_MM / W_d                   # noqa: E731  归一化 → 我们 2400dpi 的 mm
    ratios = np.array([band_rms["coarse"], band_rms["fine"], band_rms["grain"]], np.float64)
    ratios = ratios / ratios.max()
    # 4 octave 幅度比：mottle 未能在参照图量出（其低频段 δ > 0.1·W_d 被剔除）⇒ 取 coarse 的一半（登记为假设）
    amp_ratio = np.array([0.5 * ratios[0], ratios[0], ratios[1], ratios[2]], np.float64)
    amp_unit = amp_ratio / float(np.linalg.norm(amp_ratio))
    ac = pt["autocorr_half_decay_px"]
    aniso = float(ac["y"] / ac["x"]) if (ac["x"] and ac["y"]) else 2.0
    sem = ft["semantic_lightness"]
    bins = sem["L_bins"]
    dn_centers = [0.5 * (b["d_over_d_p90"][0] + b["d_over_d_p90"][1]) for b in bins]
    L_vals = [b["L_mean"] for b in bins]
    S_vals = [b["S_mean"] for b in bins]
    cal = {
        "source_files": {"paper": str(DOUBAO_PAPER.relative_to(REPO)), "ink": str(DOUBAO_INK.relative_to(REPO)),
                         "paper_sha256": P["source"]["sha256"], "ink_sha256": I["source"]["sha256"]},
        "ruler": {"paper_W_d_px": W_d, "ink_W_d_px": I["ruler"]["W_d_px"], "ours_W_o_px": W_O_PX,
                  "ours_W_o_mm": W_O_MM,
                  "formula": "目标尺度(mm) = W_o_mm × (f_d/W_d)；目标尺度(px@2400) = W_o_px × (f_d/W_d)"},
        # ① 纤维长度（尺度标定）
        "fiber_coarse_len_mm": round(pk2mm(band_pk["coarse"]), 4),
        "fiber_fine_len_mm": round(pk2mm(band_pk["fine"]), 4),
        "grain_diam_mm": round(pk2mm(band_pk["grain"]), 4),
        "fiber_peak_mm_from_fd": round(pk2mm(f_d), 4),
        "aniso_ratio_measured": round(aniso, 4),
        # ② 幅度标定
        "band_rms_coarse_fine_grain": [float(r) for r in band_rms.values()],
        "amp_unit_vector_mottle_coarse_fine_grain": [round(float(v), 5) for v in amp_unit],
        "paper_total_rms_0_255_target": float(pt["texture_rms_0_255_median"]),
        "paper_mean_rgb_target": P["paper_color"]["mean_rgb"],
        "paper_lum_deciles_target": P["paper_color"]["lum_deciles"],
        # ③ 印泥标定
        "ink_semantic_dn_centers": [round(float(v), 4) for v in dn_centers],
        "ink_semantic_L_curve": [round(float(v), 4) for v in L_vals],
        "ink_semantic_S_curve": [round(float(v), 4) for v in S_vals],
        "ink_semantic_L_wide_minus_thin": sem["L_wide_minus_thin"],
        "ink_d_p90_over_W_d": sem["d_p90_over_W_d"],
        "ink_grain_lum_highpass_sigma_target": ft["grain"]["lum_highpass_sigma_2px"],
        "ink_grain_scale_mm": round(I["targets_for_us_px_at_2400"]["edge_transition_width_mm"], 5),
        "ink_edge_transition_mm": round(I["targets_for_us_px_at_2400"]["edge_transition_width_mm"], 5),
        "ink_halo_transition_mm": round(I["targets_for_us_px_at_2400"]["halo_transition_width_mm"], 5),
        "ink_halo_outer_band_mm": round(ft["halo"]["outer_band_of_overlap_px"]
                                        * I["ruler"]["mm_per_px_equiv"], 4),
        "ink_translucency_share_light_inside": ft["translucency"]["share_light_inside"],
        "ink_median_rgb": ft["color"]["median_rgb"],
        "ink_sat_p50": ft["color"]["sat_p50"],
        "ink_delta_e_to_target": ft["color"]["delta_e2000_median_to_target"],
        "ink_L_std": ft["lstar"]["std"],
        "ink_grain_blur_sigma_px_at_equiv": 2.0,
        "ink_grain_blur_mm": round(2.0 * I["ruler"]["mm_per_px_equiv"], 6),
        "ink_equiv_dpi": I["ruler"]["equiv_dpi"],
        "assumptions": [
            "目标 mm 值成立的前提＝「豆包印面实物宽 ＝ C1-R1 的 22.437 mm」（显式假设，证据件已写死）",
            "mottle（云斑）octave 幅度在参照图中不可测（其频段被 0.1·W_d 低切剔除）⇒ 取 coarse 的 0.5 倍（假设）",
            "scale 梯度（CONS/OBV）在标定中心 ±15~18% 内微调；幅度档 ×1.0/×1.25 供对比",
        ],
    }
    cal["ink_grain_blur_sigma_px_at_ours"] = round(2.0 * PROD_DPI / float(I["ruler"]["equiv_dpi"]), 3)
    return cal


CAL = load_calibration()

# 纹理真源（**唯一 mm 定义**；由豆包标定给中心值）
TEX_ANISO_RATIO = round(CAL["aniso_ratio_measured"], 3)      # 弱各向异性（由参照图自相关 x:y 实测）
TEX_MOTTLE_MM = 11.0                                        # 成形云斑（参照图不可测 ⇒ 沿用，幅度按假设比）
TEX_FIB_COARSE_MM = CAL["fiber_coarse_len_mm"]              # ← 标定：粗纤维长轴
TEX_FIB_FINE_MM = CAL["fiber_fine_len_mm"]                  # ← 标定：细纤维长轴
TEX_GRAIN_MM = CAL["grain_diam_mm"]                         # ← 标定：颗粒直径
AMP_UNIT = CAL["amp_unit_vector_mottle_coarse_fine_grain"]  # ← 标定：octave 幅度比（酉矢）
TEX_RMS_TARGET = CAL["paper_total_rms_0_255_target"]        # ← 标定：纸底总 RMS（0–255）

# 3 组候选（尺度 × 幅度；中心＝豆包标定值，梯度 ±15~18%）
CANDIDATES = {
    "CONS": {"label": "保守", "scale": 0.85, "k": 1.35},
    "MID": {"label": "中（标定中心）", "scale": 1.00, "k": 2.30},
    "OBV": {"label": "明显（＝豆包幅度）", "scale": 1.18, "k": round(TEX_RMS_TARGET, 3)},
}
CAND_ORDER = ("CONS", "MID", "OBV")
AMP_LEVELS = (1.0, 1.25)
TEX_FIELD_MM = 8.0
TEX_STAT_FIELD_MM = 12.0

# 观感算子尺度（mm；600dpi 下与上轮 C 一致）
FIELD_SIGMA_MM = px2mm(vs.FIELD_SIGMA_600, COMP_DPI)
FIELD_GAIN_LO, FIELD_GAIN_HI = vs.FIELD_GAIN_LO, vs.FIELD_GAIN_HI
SCURVE_T = vs.SCURVE_T
MICRO_AMOUNT, MICRO_SIGMA_MM = vs.MICRO_AMOUNT, px2mm(vs.MICRO_SIGMA_600, COMP_DPI)
PAPER_MICRO_AMOUNT = vs.PAPER_MICRO_AMOUNT
GUIDE_RADIUS_MM = px2mm(vs.GUIDE_RADIUS_600, COMP_DPI)
GUIDE_EPS = vs.GUIDE_EPS
CALIB_STRENGTH_LEGACY = vs.CALIB_STRENGTH
# 晕染：强段＝极窄（对标豆包过渡宽度），尾段＝淡（对标豆包可见外沿）
HALO_STRONG_MM = max(CAL["ink_halo_transition_mm"], 0.06)
HALO_ALPHA_MAX = sc.HALO_ALPHA_MAX
HALO_TAIL_MM = min(CAL["ink_halo_outer_band_mm"], 0.65)
HALO_TAIL_ALPHA = 0.02
PEN_ALPHA_MAX, PEN_TAU_MM = vs.PEN_ALPHA_MAX, px2mm(vs.PEN_TAU_600, COMP_DPI)
# 印泥语义/颗粒/毛糙尺度（对标豆包）
INK_EDGE_MM = CAL["ink_edge_transition_mm"]
INK_GRAIN_MM = CAL["ink_grain_scale_mm"]
INK_ROUGH_MM = CAL["ink_edge_transition_mm"]
INK_MIN_DPI_FINE = 1200                 # 颗粒/毛糙（0.06mm 级）可表示下限
SMOOTH_LEVELS = {"0": 0.0, "mid": 0.55, "strong": 1.0}

OLD_TEX = {"long_px": vs.FIBER_CELL_LONG_600, "short_px": vs.FIBER_CELL_SHORT_600,
           "long2_px": vs.FIBER_CELL_LONG2_600, "short2_px": vs.FIBER_CELL_SHORT2_600,
           "sigma_f1": sc.BG_FIBER_SIGMA, "sigma_f2": vs.FIBER2_SIGMA,
           "sigma_grain": sc.BG_GRAIN_SIGMA, "dpi_defined_at": COMP_DPI}


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. 多尺度带限噪声（mm 空间位置哈希）
# ══════════════════════════════════════════════════════════════════════════════════════
def vnoise_mm(rows_mm, cols_mm, cl_mm, cs_mm, seed, salt):
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

    def corner(dy, dx):
        return rp._u(rp._hash64(uy + dy, ux + dx, seed, salt + dy * 2 + dx), 0, 21)[ry][:, cx]
    v00, v01, v10, v11 = corner(0, 0), corner(0, 1), corner(1, 0), corner(1, 1)
    top = v00 + (v01 - v00) * fx[None, :]
    bot = v10 + (v11 - v10) * fx[None, :]
    return top + (bot - top) * fy[:, None]


_STD_CACHE: dict = {}


def octave_std_ref(cl_mm, cs_mm, seed, salt) -> float:
    key = (round(cl_mm, 6), round(cs_mm, 6), seed, salt)
    if key not in _STD_CACHE:
        dens, ncell = 12, 64
        rows = np.arange(0, ncell * dens, dtype=np.float64) / dens * cs_mm
        cols = np.arange(0, ncell * dens, dtype=np.float64) / dens * cl_mm
        _STD_CACHE[key] = float((vnoise_mm(rows, cols, cl_mm, cs_mm, seed, salt) - 0.5).std())
    return _STD_CACHE[key]


def octave_spec(cand: str, dpi: int, scale_extra: float = 1.0, k_extra: float = 1.0) -> list[dict]:
    cfg = CANDIDATES[cand]
    s = float(cfg["scale"]) * float(scale_extra)
    k = float(cfg["k"]) * float(k_extra)
    raw = [("mottle", TEX_MOTTLE_MM * s, TEX_MOTTLE_MM * s, 71),
           ("fiber_coarse", TEX_FIB_COARSE_MM * s, TEX_FIB_COARSE_MM * s / TEX_ANISO_RATIO, 113),
           ("fiber_fine", TEX_FIB_FINE_MM * s, TEX_FIB_FINE_MM * s / TEX_ANISO_RATIO, 157),
           ("grain", TEX_GRAIN_MM, TEX_GRAIN_MM, 199)]
    out = []
    for i, (name, cl, cs, salt) in enumerate(raw):
        amp = float(AMP_UNIT[i]) * k
        out.append({"name": name, "long_mm": cl, "short_mm": cs, "salt": salt, "amp": amp,
                    "long_px": round(mm2px(cl, dpi), 3), "short_px": round(mm2px(cs, dpi), 3),
                    "resolvable_2px": bool(mm2px(cs, dpi) >= 2.0)})
    return out


def paper_field_mm(rows, cols, dpi, cand, amp_level=1.0, scale_extra=1.0):
    r_mm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    c_mm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    lum = np.zeros((r_mm.size, c_mm.size), np.float32)
    for o in octave_spec(cand, dpi, scale_extra, amp_level):
        n = vnoise_mm(r_mm, c_mm, o["long_mm"], o["short_mm"], SEED, o["salt"])
        ref = octave_std_ref(o["long_mm"], o["short_mm"], SEED, o["salt"])
        lum += (np.float32(o["amp"] / ref) * (n.astype(np.float32) - np.float32(0.5)))
    h2 = rp._hash64(rows, cols, SEED, 1)
    chroma = np.stack([rp._u(h2, 0, 21) - 0.5, rp._u(h2, 21, 21) - 0.5, rp._u(h2, 42, 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    out = (np.asarray(sc.BG_BASE_RGB, np.float32)[None, None, :] + lum[:, :, None]
           + np.float32(sc.BG_CHROMA_SIGMA) * chroma)
    return np.clip(out, np.asarray(sc.BG_MIN_RGB, np.float32)[None, None, :],
                   np.asarray(sc.BG_MAX_RGB, np.float32)[None, None, :])


def old_paper_field(rows, cols, dpi):
    """反例对照：上轮 C 的**像素常量**纹理（16/2＋64/8px＋像素白噪声）在目标 dpi 上原样复用。"""
    lum = np.zeros((rows.size, cols.size), np.float32)
    h1 = rp._hash64(rows, cols, SEED, 0)
    u1 = np.maximum(rp._u(h1, 0, 31), 1e-9)
    u2 = rp._u(h1, 31, 31)
    lum += np.float32(OLD_TEX["sigma_grain"]) * (
        np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)).astype(np.float32)
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


def paper_patch_rows(cand, dpi, field_mm, amp_level=1.0, scale_extra=1.0, origin_mm=(40.0, 25.0)):
    n = mm2px_int(field_mm, dpi)
    rows = np.arange(mm2px_int(origin_mm[1], dpi), mm2px_int(origin_mm[1], dpi) + n, dtype=np.int64)
    cols = np.arange(mm2px_int(origin_mm[0], dpi), mm2px_int(origin_mm[0], dpi) + n, dtype=np.int64)
    f = (paper_field_mm(rows, cols, dpi, cand, amp_level, scale_extra) if cand
         else old_paper_field(rows, cols, dpi))
    return f


def paper_for(mode: str, h: int, w: int, dpi: int) -> np.ndarray:
    bg = VARIANTS[mode]["bg"]
    cols = np.arange(0, w, dtype=np.int64)
    out = np.empty((h, w, 3), np.uint8)
    for y0 in range(0, h, 384):
        y1 = min(y0 + 384, h)
        rows = np.arange(y0, y1, dtype=np.int64)
        f = (paper_field_mm(rows, cols, dpi, bg) if bg in CANDIDATES else old_paper_field(rows, cols, dpi))
        out[y0:y1] = vs.to_u8(f)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. dpi 对齐读数
# ══════════════════════════════════════════════════════════════════════════════════════
TEX_BANDS_MM = ((0.45, 1.35), (0.134, 0.449), (0.045, 0.134))     # 与参照图分带口径一致
# 径向 PSD 的**固定物理频率网格**：上限 10.6 cyc/mm ＜ 600dpi Nyquist(11.81) ⇒ 600/2400 同格可比
F_COMMON_MAX_CYC_MM = 10.6
F_BIN_CYC_MM = 0.2
# 掩膜翻转率容差：守卫按 float32 掩膜判定，uint8 量化会让极少数边界像素跨过 r>g+15 阈值
# （实测量级 ~5e-4 全图；且**两向**都可翻）。这是任何 uint8 管线都有的量化效应，非算子外泄；
# 外泄判据是 freeze.assert_ok（白线区/掩膜外对观感基线逐像素差＝0），那是**硬 0**。
MASK_FLIP_RATE_TOL = 1e-3


def _half_decay(prof):
    below = np.where(prof < 0.5)[0]
    if below.size == 0:
        return None
    i = int(below[0])
    if i == 0:
        return 0.0
    x0, x1 = float(prof[i - 1]), float(prof[i])
    fr = (x0 - 0.5) / (x0 - x1) if x0 != x1 else 0.0
    return (i - 1) + float(np.clip(fr, 0.0, 1.0))


def tex_readout(lum_res, dpi, field_mm) -> dict:
    a = np.asarray(lum_res, np.float64)
    a = a - a.mean()
    h, w = a.shape
    ph, pw = 1 << int(np.ceil(np.log2(2 * h))), 1 << int(np.ceil(np.log2(2 * w)))
    ac = np.fft.fftshift(np.fft.irfft2(np.abs(np.fft.rfft2(a, s=(ph, pw))) ** 2, s=(ph, pw)))
    ac = ac / ac[ph // 2, pw // 2]
    lx = _half_decay(ac[ph // 2, pw // 2:pw // 2 + w // 2])
    ly = _half_decay(ac[ph // 2:ph // 2 + h // 2, pw // 2])
    mmx = px2mm(1.0, dpi)
    win = np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.rfft2(a * win)) ** 2
    FY, FX = np.meshgrid(np.fft.fftfreq(h, d=mmx), np.fft.rfftfreq(w, d=mmx), indexing="ij")
    fr = np.sqrt(FY ** 2 + FX ** 2)
    # ★ 径向 PSD 用**固定物理频率网格**（cyc/mm），且只算**两 dpi 共同可比频带**：
    #   上限 10.6 cyc/mm ＜ 600dpi 的 Nyquist(11.81) ⇒ 600/2400 在同一物理格上取质心/峰值。
    f_lo = 1.0 / (2.0 * field_mm)
    edges = np.arange(f_lo, F_COMMON_MAX_CYC_MM + F_BIN_CYC_MM, F_BIN_CYC_MM)
    idx = np.clip(np.digitize(fr.ravel(), edges) - 1, 0, edges.size - 2)
    psd = np.bincount(idx, weights=P.ravel(), minlength=edges.size - 1) / \
        np.maximum(np.bincount(idx, minlength=edges.size - 1), 1)
    fcen = 0.5 * (edges[:-1] + edges[1:])
    m = (fcen >= f_lo) & (fcen <= F_COMMON_MAX_CYC_MM)
    bands = {}
    for lo_mm, hi_mm in TEX_BANDS_MM:
        sel = (fcen >= 1.0 / hi_mm) & (fcen <= 1.0 / lo_mm)
        band = cv2.GaussianBlur(a.astype(np.float32), (0, 0), hi_mm / (2 * np.pi) / mmx) - \
            cv2.GaussianBlur(a.astype(np.float32), (0, 0), lo_mm / (2 * np.pi) / mmx)
        bands[f"{lo_mm}-{hi_mm}mm"] = {
            "peak_wavelength_mm": (round(1.0 / float(fcen[sel][int(np.argmax(psd[sel]))]), 4)
                                   if sel.any() else None),
            "rms_0_255": round(float(band.std()), 4),
            "energy_share": round(float(psd[sel].sum() / max(psd[m].sum(), 1e-30)), 5) if sel.any() else None}
    return {"dpi": dpi, "field_mm": field_mm, "px": [w, h], "px_per_mm": round(1.0 / mmx, 3),
            "psd_frequency_grid": {"bin_cyc_per_mm": F_BIN_CYC_MM,
                                   "band_cyc_per_mm": [round(f_lo, 4), F_COMMON_MAX_CYC_MM],
                                   "why_common_band": "上限＜600dpi Nyquist(11.81 cyc/mm) ⇒ 600/2400 同物理格可比"},
            "autocorr_half_decay_mm": {"x": None if lx is None else round(px2mm(lx, dpi), 4),
                                       "y": None if ly is None else round(px2mm(ly, dpi), 4)},
            "autocorr_half_decay_px": {"x": None if lx is None else round(lx, 3),
                                       "y": None if ly is None else round(ly, 3)},
            "psd_centroid_cyc_per_mm": round(float((fcen[m] * psd[m]).sum() / max(psd[m].sum(), 1e-30)), 5),
            "psd_peak_wavelength_mm": round(1.0 / float(fcen[m][int(np.argmax(psd[m]))]), 4),
            "bands": bands, "rms_0_255": round(float(a.std()), 4)}


def cross_dpi_sim(p2400_rgb, p600_rgb) -> dict:
    a = cv2.resize(p2400_rgb.astype(np.float32), (p600_rgb.shape[1], p600_rgb.shape[0]),
                   interpolation=cv2.INTER_AREA)
    b = p600_rgb.astype(np.float32)
    dg = a.mean(axis=2) - b.mean(axis=2)
    return {"mean_abs_diff_lum": round(float(np.abs(dg).mean()), 4),
            "p99_abs_diff_lum": round(float(np.percentile(np.abs(dg), 99)), 4),
            "pearson_r_lum": round(float(np.corrcoef(a.mean(2).ravel(), b.mean(2).ravel())[0, 1]), 6)}


def _ratio(a, b):
    if a is None or b is None or float(b) == 0.0:
        return None
    return round(float(a) / float(b), 4)


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. 印泥算子（严格档 / 观感档）
# ══════════════════════════════════════════════════════════════════════════════════════
TARGET_LAB = cc.srgb_to_lab(cc.TARGET_RGB)


def delta_e_stats(rgb_px, max_px=400000) -> dict:
    px = np.asarray(rgb_px, np.float64)
    n_all = px.shape[0]
    stride = 1
    if n_all > max_px:
        stride = int(np.ceil(n_all / max_px))
        px = px[::stride]
    if px.shape[0] == 0:
        return {"pixels": 0, "median": None, "p90": None, "leq5_rate": None, "stride": stride}
    lab = cc._srgb_to_lab_arr(px)
    de = np.fromiter((cc.ciede2000_lab(lab[i], TARGET_LAB) for i in range(lab.shape[0])),
                     dtype=np.float64, count=lab.shape[0])
    return {"pixels": int(n_all), "sampled": int(px.shape[0]), "stride": stride,
            "median": round(float(np.median(de)), 4), "p90": round(float(np.percentile(de, 90)), 4),
            "mean": round(float(de.mean()), 4),
            "leq5_rate": round(float((de <= 5.0).mean()), 5), "leq3_rate": round(float((de <= 3.0).mean()), 5)}


def lab_stats(px, max_px=400000) -> dict:
    px = np.asarray(px, np.float64)
    if px.shape[0] > max_px:
        px = px[:: int(np.ceil(px.shape[0] / max_px))]
    if px.shape[0] == 0:
        return {}
    lab = cc._srgb_to_lab_arr(px)
    L, A, B = lab[:, 0], lab[:, 1], lab[:, 2]
    return {"L_mean": round(float(L.mean()), 3), "L_std": round(float(L.std()), 3),
            "L_p10": round(float(np.percentile(L, 10)), 3), "L_p50": round(float(np.percentile(L, 50)), 3),
            "L_p90": round(float(np.percentile(L, 90)), 3),
            "a_std": round(float(A.std()), 3), "b_std": round(float(B.std()), 3),
            "a_mean": round(float(A.mean()), 3), "b_mean": round(float(B.mean()), 3)}


def rgb_mean(px):
    a = np.asarray(px, np.float64)
    if a.ndim == 1:
        return [round(float(v), 3) for v in a]
    return [round(float(v), 3) for v in a.mean(axis=0)]


def _semantic_curves():
    """豆包语义曲线 → 插值函数（L* 偏移相对 p50 箱；色度倍率相对平台区）。"""
    dn = np.asarray(CAL["ink_semantic_dn_centers"], np.float64)
    L = np.asarray(CAL["ink_semantic_L_curve"], np.float64)
    S = np.asarray(CAL["ink_semantic_S_curve"], np.float64)
    L0 = float(L[np.argmin(np.abs(dn - 0.5))])
    S0 = float(S[-2:].mean())
    return dn, (L - L0), (S / S0)


def ink_chroma_v3(img, red_m, smooth_level, tier, ops, dpi: int = PROD_DPI):
    """印泥算子：① 靶色（colorcal V3）② 平滑档 ③ 语义浓淡/半透 ④ 毛糙 ⑤ 颗粒 ⑥ 哑光（不加高光）。

    顺序：**先靶色 → 再平滑 → 再语义/颗粒** —— 靶色用 colorcal 的色域自适应二分，语义/颗粒在其后；
    任何一步都只写红墨区；结尾做**掩膜守卫**（若某像素会掉出 ink 掩膜则回退原值）⇒ 掩膜逐像素不变。
    颗粒/毛糙的物理尺度在 <1200dpi 下不足 2px ⇒ **不可表示**，自动停用并登记（不画假纹理）。
    """
    info: dict = {"smooth_level": float(smooth_level), "tier": tier, "ops": list(ops), "dpi": dpi,
                  "target_hex": cc.TARGET_HEX, "chroma_strength": float(cc.V3_FG_CHROMA_STRENGTH),
                  "chroma_impl": "colorcal.apply_foreground_chroma（V3）"}
    if dpi < INK_MIN_DPI_FINE:
        dropped = [o for o in ops if o in ("grain", "roughness")]
        if dropped:
            ops = tuple(o for o in ops if o not in ("grain", "roughness"))
            info["dropped_underresolved_ops"] = {
                "ops": dropped, "at_dpi": dpi, "min_dpi": INK_MIN_DPI_FINE,
                "scale_mm": INK_GRAIN_MM, "px_at_dpi": round(mm2px(INK_GRAIN_MM, dpi), 3),
                "reason": "物理尺度 <2px 不可表示 ⇒ 停用（避免画与 dpi 不匹配的假纹理）"}
        info["ops"] = list(ops)
    px_before = (img[..., :3][red_m].astype(np.float64) if red_m.any() else None)
    img, fg = cc.apply_foreground_chroma(img, red_m)
    info["fg_gamut_clip_rate"] = round(float(fg["gamut_clip_rate"]), 6)
    info["fg_chroma_reduced_rate"] = round(float(fg["chroma_reduced_rate"]), 6)
    info["fg_iou_raw"] = round(float(fg["iou_raw"]), 6)
    info["fg_mask_reverted_px"] = int(fg["mask_reverted_pixels"])
    rad = mm2px_int(GUIDE_RADIUS_MM, dpi)
    # ② 保边平滑（可调档：0＝保留原斑驳；mid＝规整扫描噪点；strong＝平滑）
    if smooth_level > 0 and red_m.any():
        y = vs.lum(img)
        sm = vs.guided_smooth_color(img, y, rad, GUIDE_EPS)
        blend = float(smooth_level)
        img = img.copy()
        img[red_m] = img[red_m] * (1.0 - blend) + sm[red_m] * blend
        del sm
    if tier != "aesthetic":
        _lstar_delta(info, px_before, img, red_m)
        return img, info
    # ③④ 语义浓淡（L* 按豆包曲线）＋ 半透（色度按豆包曲线）＋ 毛糙（近边抖动）
    _dpi = dpi
    d = cv2.distanceTransform(red_m.astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)
    d_p90 = float(np.percentile(d[red_m], 90.0))
    dn = d / max(d_p90, 1e-6)
    if "roughness" in ops:
        rows = np.arange(img.shape[0], dtype=np.int64)
        cols = np.arange(img.shape[1], dtype=np.int64)
        cm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / _dpi
        rm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / _dpi
        jit = vnoise_mm(rm, cm, INK_ROUGH_MM, INK_ROUGH_MM, SEED, 311).astype(np.float32) - np.float32(0.5)
        amp_norm = (2.0 * INK_ROUGH_MM) / max(px2mm(d_p90, _dpi), 1e-6)
        dn = np.clip(dn + jit * np.float32(amp_norm), 0.0, None)
        info["roughness"] = {"scale_mm": INK_ROUGH_MM, "jitter_amplitude_mm": round(2.0 * INK_ROUGH_MM, 4),
                             "amp_in_dn_units": round(amp_norm, 5), "mask_moved": False,
                             "impl": "位置哈希噪声扰动距离场 ⇒ L* 等值线毛糙；**掩膜逐像素不动**"}
    dn = np.clip(dn, 0.0, 1.0)
    dn_lookup, dL_curve, s_curve = _semantic_curves()
    dL = np.interp(dn, dn_lookup, dL_curve).astype(np.float64)
    cscale = np.interp(dn, dn_lookup, s_curve).astype(np.float64)
    lab = cc._srgb_to_lab_arr(img[..., :3][red_m].astype(np.float64))
    L = lab[:, 0] + dL[red_m]
    ab = lab[:, 1:] * cscale[red_m][:, None]
    new_rgb = cc._lab_to_srgb_arr(np.stack([L, ab[:, 0], ab[:, 1]], axis=-1))
    if "grain" in ops:
        # ★ 先量后补：在**已平滑**的红墨区内部量当前高通 σ（高斯半径＝参照物的物理等价换算），
        #   再补 σ_add = sqrt(max(target² − current², 0)) ⇒ 颗粒幅度对齐参照物，且不叠乘扫描噪点。
        er = cv2.erode(red_m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        g_blur = mm2px(CAL["ink_grain_blur_mm"], _dpi)
        lum_now = vs.lum(img)
        hp = (lum_now - cv2.GaussianBlur(lum_now, (0, 0), g_blur))[er] if er.any() else np.zeros(1)
        cur = float(hp.std())
        sig = float(np.sqrt(max(CAL["ink_grain_lum_highpass_sigma_target"] ** 2 - cur ** 2, 0.0)))
        rows = np.arange(img.shape[0], dtype=np.int64)
        cols = np.arange(img.shape[1], dtype=np.int64)
        cm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / _dpi
        rm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / _dpi
        g = vnoise_mm(rm, cm, INK_GRAIN_MM, INK_GRAIN_MM, SEED, 401).astype(np.float32)
        g = (g - float(g.mean())) / max(float(g.std()), 1e-6)
        new_rgb = new_rgb + np.float32(sig) * g[red_m][:, None]
        info["grain"] = {"scale_mm": INK_GRAIN_MM, "blur_sigma_mm": round(CAL["ink_grain_blur_mm"], 5),
                         "blur_sigma_px": round(g_blur, 2), "px_eroded": int(er.sum()),
                         "doubao_target_sigma_0_255": CAL["ink_grain_lum_highpass_sigma_target"],
                         "current_sigma_after_smooth_0_255": round(cur, 4),
                         "sigma_added_0_255": round(sig, 4),
                         "expected_result_0_255": round(float(np.sqrt(cur ** 2 + sig ** 2)), 4),
                         "impl": "位置哈希噪声（mm 空间，零均值单位方差）×σ_add，加在 L* 域；"
                                 "掩膜守卫保证掉出 ink 掩膜的像素回退原值"}
    out = img.copy()
    cand_rgb = np.clip(np.rint(new_rgb), 0, 255).astype(out[..., :3].dtype)
    tmp = out.copy()
    tmp[..., :3][red_m] = cand_rgb
    keep = cc.ink_mask(tmp.astype(np.float64))[red_m]
    final = cand_rgb.copy()
    final[~keep] = out[..., :3][red_m][~keep]
    out[..., :3][red_m] = final
    info["semantic"] = {"L_curve_dn": [round(float(v), 4) for v in dL_curve],
                        "dL_wide_minus_thin_target": CAL["ink_semantic_L_wide_minus_thin"],
                        "chroma_scale_curve": [round(float(v), 4) for v in s_curve],
                        "curve_source": "豆包参照图#2（doubao-ink-reference-features.json）",
                        "translucency_share_target": CAL["ink_translucency_share_light_inside"],
                        "L_star_allowed_to_change": tier == "aesthetic"}
    info["mask_guard_dropped_and_reverted_px"] = int((~keep).sum())
    _lstar_delta(info, px_before, out, red_m)
    return out, info


def _lstar_delta(info: dict, px_before, img_after, red_m) -> None:
    """印泥算子**自身**造成的 L* 逐像素变化（红墨区；不含全局色调算子）——严格档判据。"""
    if px_before is None or px_before.shape[0] == 0:
        return
    Lb = cc._srgb_to_lab_arr(px_before)[:, 0]
    La = cc._srgb_to_lab_arr(img_after[..., :3][red_m].astype(np.float64))[:, 0]
    d = La - Lb
    info["lstar_preservation"] = {
        "definition": "本算子自身造成的 L* 逐像素变化（红墨区；不含全局色调算子）",
        "L_mean_delta": round(float(d.mean()), 6),
        "L_mean_abs_delta": round(float(np.abs(d).mean()), 6),
        "L_p90_abs_delta": round(float(np.percentile(np.abs(d), 90)), 6),
        "L_max_abs_delta": round(float(np.abs(d).max()), 6),
        "L_std_before": round(float(Lb.std()), 4), "L_std_after": round(float(La.std()), 4),
        "verdict": ("L* 逐像素保留（仅 uint8 量化级）" if float(np.abs(d).max()) <= 0.25
                    else "L* 被有意调制（观感档）")}


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. 版本表与管线
# ══════════════════════════════════════════════════════════════════════════════════════
VARIANTS: dict[str, dict] = {
    "C_old":        {"bg": "old", "ink": "legacy", "tier": "legacy", "label": "C旧（上轮 C，px 常量纹理＋向均色校准）"},
    "C2_strict":    {"bg": "MID", "ink": "v3", "tier": "strict", "smooth": 0.0, "ops": (),
                     "label": "严格档（靶色 #C95021，保 L*，平滑 0）"},
    "C2_smoothmid": {"bg": "MID", "ink": "v3", "tier": "strict", "smooth": 0.55, "ops": (),
                     "label": "靶色＋平滑中（规整扫描噪点）"},
    "C2_smoothstr": {"bg": "MID", "ink": "v3", "tier": "strict", "smooth": 1.0, "ops": (),
                     "label": "靶色＋平滑强"},
    "C2_semantic":  {"bg": "MID", "ink": "v3", "tier": "aesthetic", "smooth": 0.55, "ops": ("semantic",),
                     "label": "＋语义浓淡（宽处浓/细处淡）"},
    "C2_semgrain":  {"bg": "MID", "ink": "v3", "tier": "aesthetic", "smooth": 0.55,
                     "ops": ("semantic", "grain"), "label": "＋语义浓淡＋颗粒"},
    "C2_aes":       {"bg": "MID", "ink": "v3", "tier": "aesthetic", "smooth": 0.55,
                     "ops": ("semantic", "grain", "roughness"), "label": "观感档全开（语义＋颗粒＋半透＋毛糙）"},
    "C2_aes_cons":  {"bg": "CONS", "ink": "v3", "tier": "aesthetic", "smooth": 0.55,
                     "ops": ("semantic", "grain", "roughness"), "label": "观感档（纸纹理 CONS）"},
    "C2_aes_obv":   {"bg": "OBV", "ink": "v3", "tier": "aesthetic", "smooth": 0.55,
                     "ops": ("semantic", "grain", "roughness"), "label": "观感档（纸纹理 OBV）"},
}


def run_variant(mode, src, mk, dpi, paper, ink_ops_on=True, grain_sigma_add=None, smooth_level=None):
    """跑一版。

    `C_old` ＝**上轮 C 的实现原样**（`variants_samples.run_variant("C", …)`，只读复用）——像素常量纹理
    ＋向全页均色校准；在同一 dpi 上跑，正好当「像素常量 ⇒ 物理尺度随 dpi 漂移」的反例对照。
    其余版本走本轮实现（mm 尺度 ＋ colorcal V3 靶色 ＋ 严格/观感档）。
    """
    t0 = time.time()
    cfg = VARIANTS[mode]
    if mode == "C_old":
        mk_vs = dict(mk)
        mk_vs["paper_up"] = paper
        mk_vs["paper_base"] = paper
        out, rd = vs.run_variant("C", src, mk_vs, ink_ops=ink_ops_on)
        rd.update({"mode": "C_old", "label": cfg["label"], "dpi": dpi, "bg_source": "old",
                   "tier": "legacy", "ops": [], "elapsed_s": round(time.time() - t0, 2)})
        return out, rd
    img = src.astype(np.float32).copy()
    red_m = mk["red"]
    rd = {"mode": mode, "label": cfg["label"], "dpi": dpi, "bg_source": cfg["bg"],
          "tier": cfg["tier"], "ops": list(cfg["ops"])}
    img, rd["light_field"] = field_gain_mm(img, mk["paper_rule"], dpi)
    img, rd["tone_map"] = tone_map_mm(img, mk["paper_rule"], dpi)
    img[mk["bg_zone"]] = paper.astype(np.float32)[mk["bg_zone"]]
    blur = cv2.GaussianBlur(img, (0, 0), mm2px(MICRO_SIGMA_MM, dpi))
    img[mk["bg_zone"]] = img[mk["bg_zone"]] + np.float32(PAPER_MICRO_AMOUNT) * (img - blur)[mk["bg_zone"]]
    del blur
    ink_mean = img[red_m].astype(np.float64).mean(axis=0) if red_m.any() else None
    if ink_mean is not None:                          # 渗透感
        d_out = mk["dist_outside"]
        b, o, tau = mm2px(HALO_STRONG_MM, dpi), mm2px(1.016, dpi), mm2px(PEN_TAU_MM, dpi)
        a = np.where((d_out > b) & (d_out <= o), PEN_ALPHA_MAX * np.exp(-(d_out - b) / tau), 0.0).astype(np.float32)
        a = a * (mk["bg_zone"] & (~red_m)).astype(np.float32)
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        rd["penetration"] = {"alpha_max": PEN_ALPHA_MAX, "tau_mm": round(PEN_TAU_MM, 4),
                             "band_mm": [round(HALO_STRONG_MM, 4), 1.016], "px": int((a > 0).sum())}
        del a
    if ink_mean is not None:                          # 晕染（强段极窄 ＋ 淡尾段，对标豆包）
        d_out = mk["dist_outside"]
        b, tail = mm2px(HALO_STRONG_MM, dpi), mm2px(HALO_TAIL_MM, dpi)
        a = np.where(~mk["body"] & (d_out <= b),
                     np.clip((b + 1.0 - d_out) / b, 0.0, 1.0) * HALO_ALPHA_MAX, 0.0)
        a = np.where(~mk["body"] & (d_out > b) & (d_out <= tail),
                     HALO_TAIL_ALPHA * np.clip((tail - d_out) / max(tail - b, 1.0), 0.0, 1.0), a)
        a = a.astype(np.float32)
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        rd["halo"] = {"strong_mm": round(HALO_STRONG_MM, 4), "strong_alpha_max": HALO_ALPHA_MAX,
                      "tail_mm": round(HALO_TAIL_MM, 4), "tail_alpha_max": HALO_TAIL_ALPHA,
                      "doubao_halo_transition_mm": CAL["ink_halo_transition_mm"],
                      "doubao_outer_band_mm": CAL["ink_halo_outer_band_mm"], "px": int((a > 0).sum())}
        del a
    if ink_ops_on and red_m.any():
        lvl = cfg["smooth"] if smooth_level is None else smooth_level
        if cfg["tier"] == "aesthetic":
            rd["grain_target"] = {"doubao_sigma_0_255": CAL["ink_grain_lum_highpass_sigma_target"],
                                  "added_sigma_0_255": (None if grain_sigma_add is None
                                                        else round(float(grain_sigma_add), 4)),
                                  "calibrated_for_dpi": PROD_DPI,
                                  "note": "σ_add 在 2400dpi 上标定；600dpi 下颗粒/毛糙自动停用（<2px 不可表示）"}
        img, rd["ink_ops"] = ink_chroma_v3(img, red_m, lvl, cfg["tier"], cfg["ops"], dpi)
    out = vs.to_u8(img)
    del img
    rd["elapsed_s"] = round(time.time() - t0, 2)
    return out, rd


def field_gain_mm(img, paper_m, dpi):
    sig = mm2px(FIELD_SIGMA_MM, dpi)
    y = vs.lum(img)
    pm = paper_m.astype(np.float32)
    field = (cv2.GaussianBlur(y * pm, (0, 0), sig) /
             np.maximum(cv2.GaussianBlur(pm, (0, 0), sig), np.float32(1e-6)))
    ref = float(np.percentile(field[paper_m], 90.0))
    gain = np.clip(ref / np.maximum(field, np.float32(1e-6)),
                   np.float32(FIELD_GAIN_LO), np.float32(FIELD_GAIN_HI)).astype(np.float32)
    return img * gain[:, :, None], {"sigma_mm": round(FIELD_SIGMA_MM, 4), "sigma_px": round(sig, 2),
                                    "gain_min_paper": round(float(gain[paper_m].min()), 4),
                                    "gain_max_paper": round(float(gain[paper_m].max()), 4)}


def tone_map_mm(img, paper_m, dpi):
    paper_rgb = img[paper_m].astype(np.float64).mean(axis=0)
    g = cc.whitebalance_gains_for(tuple(float(v) for v in paper_rgb))
    k = np.asarray(g["gains"], np.float32)
    img = vs.lin_srgb_f32(vs.srgb_lin_f32(img / np.float32(255.0)) * k) * np.float32(255.0)
    x = np.clip(img, 0.0, 255.0) / np.float32(255.0)
    s = (np.float32(1.0 - SCURVE_T)) * x + np.float32(SCURVE_T) * (
        np.float32(0.5) - np.float32(0.5) * np.cos(np.float32(np.pi) * x))
    img = s * np.float32(255.0)
    blur = cv2.GaussianBlur(img, (0, 0), mm2px(MICRO_SIGMA_MM, dpi))
    img = img + np.float32(MICRO_AMOUNT) * (img - blur)
    return img, {"wb_gains": [round(float(v), 5) for v in g["gains"]], "wb_clamped": g["clamped"],
                 "paper_rgb_before": rgb_mean(paper_rgb)}


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. 掩膜 / 源区域
# ══════════════════════════════════════════════════════════════════════════════════════
def page_masks(src300, dpi):
    U = dpi // SCAN_DPI
    seg = sc.seal_mask(src300)
    red300, body300 = seg["raw"], (seg["mask"] | seg["holes"])
    paper300, ink300 = rp.build_masks(src300)
    assert np.array_equal(ink300, red300)
    h, w = SRC_H * U, SRC_W * U
    red, body = rp.upsample_mask(red300, (w, h)), rp.upsample_mask(body300, (w, h))
    pr = rp.upsample_mask(paper300, (w, h)) & ~body
    return {"red": red, "white": body & ~red, "body": body, "outside": ~body, "paper_rule": pr,
            "bg_zone": pr, "red_u8": red.astype(np.uint8),
            "dist_outside": cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)}


def region_masks(src300, box300, dpi, margin=8):
    U = dpi // SCAN_DPI
    x0, y0, x1, y1 = box300
    sx0, sy0 = max(0, x0 - margin), max(0, y0 - margin)
    sx1, sy1 = min(SRC_W, x1 + margin), min(SRC_H, y1 + margin)
    seg = sc.seal_mask(src300)
    red300, body300 = seg["raw"], (seg["mask"] | seg["holes"])
    paper300, _ = rp.build_masks(src300)
    size = ((sx1 - sx0) * U, (sy1 - sy0) * U)
    osl = (slice((y0 - sy0) * U, (y0 - sy0) * U + (y1 - y0) * U),
           slice((x0 - sx0) * U, (x0 - sx0) * U + (x1 - x0) * U))
    red = rp.upsample_mask(red300[sy0:sy1, sx0:sx1], size)[osl]
    body = rp.upsample_mask(body300[sy0:sy1, sx0:sx1], size)[osl]
    pr = rp.upsample_mask(paper300[sy0:sy1, sx0:sx1], size)[osl] & ~body
    return {"red": red, "white": body & ~red, "body": body, "outside": ~body, "paper_rule": pr,
            "bg_zone": pr, "red_u8": red.astype(np.uint8),
            "dist_outside": cv2.distanceTransform((~body).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)}


def source_region(src300, box300, dpi, margin=8):
    U = dpi // SCAN_DPI
    x0, y0, x1, y1 = box300
    sx0, sy0 = max(0, x0 - margin), max(0, y0 - margin)
    sx1, sy1 = min(SRC_W, x1 + margin), min(SRC_H, y1 + margin)
    up = rp.lanczos_up(src300[sy0:sy1, sx0:sx1], ((sx1 - sx0) * U, (sy1 - sy0) * U))
    return up[(y0 - sy0) * U: (y0 - sy0) * U + (y1 - y0) * U,
              (x0 - sx0) * U: (x0 - sx0) * U + (x1 - x0) * U].astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════════════
# 7. 拼板
# ══════════════════════════════════════════════════════════════════════════════════════
def panel_grid(rows, row_labels, col_labels, path, gap=PANEL_GAP, label_h=LABEL_H,
               left_w=LEFT_W, bg=38) -> dict:
    """网格拼板。`col_labels` 可为「一行标签」或「逐行各自的标签列表」（len == len(rows)）。"""
    per_row = bool(col_labels) and isinstance(col_labels[0], (list, tuple))
    ncol = max(len(r) for r in rows)
    widths = [max((r[i].shape[1] for r in rows if i < len(r) and r[i] is not None), default=1)
              for i in range(ncol)]
    heights = [max((p.shape[0] for p in r if p is not None), default=1) for r in rows]
    W = left_w + sum(widths) + gap * ncol
    y = 0
    y_off = []
    if not per_row:
        y = label_h
    for h in heights:
        if per_row:
            y += label_h
        y_off.append(y)
        y += h + gap
    Hh = y + (0 if per_row else 0)
    canvas = np.full((Hh, W, 3), bg, np.uint8)
    for r, yo in zip(rows, y_off):
        x = left_w + gap
        for i, p in enumerate(r):
            if p is not None:
                p3 = p if p.ndim == 3 else np.repeat(p[:, :, None], 3, axis=2)
                canvas[yo:yo + p3.shape[0], x:x + p3.shape[1]] = p3
            x += widths[i] + gap
    im = Image.fromarray(canvas)
    d = ImageDraw.Draw(im)
    for ri, yo in enumerate(y_off):
        labs = col_labels[ri] if per_row else col_labels
        x = left_w + gap
        for i, c in enumerate(labs):
            d.text((x + 4, (yo - label_h + 5) if per_row else 5), str(c), fill=(255, 255, 255))
            x += widths[i] + gap
    for r, h, yo in zip(row_labels, heights, y_off):
        d.text((6, yo + min(h // 2, 200) - 6), str(r), fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="PNG", compress_level=6)
    return {"path": str(path), "bytes": int(path.stat().st_size), "sha256": vs.sha256_file(path),
            "size_px": [im.width, im.height]}


def paper_lum_res(patch_u8):
    y = vs.lum(patch_u8.astype(np.float32))
    return y - float(y.mean())


def paper_metrics(patch_u8) -> dict:
    """纸底实测：色域/明度直方图/总 RMS/分带 RMS —— 与参照图同一套口径。"""
    g = patch_u8.astype(np.float32)
    lum = vs.lum(g)
    return {"mean_rgb": rgb_mean(patch_u8.reshape(-1, 3)),
            "std_rgb": [round(float(v), 3) for v in g.reshape(-1, 3).std(0)],
            "rms_lum_0_255": round(float(paper_lum_res(patch_u8).std()), 4),
            "lum_deciles": [round(float(np.percentile(lum, p)), 2) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)],
            "clip255_share": round(float((g.max(axis=2) >= 255.0).mean()), 5),
            "min_rgb": [int(v) for v in g.reshape(-1, 3).min(0)],
            "max_rgb": [int(v) for v in g.reshape(-1, 3).max(0)]}


# ══════════════════════════════════════════════════════════════════════════════════════
# 8. 主流程
# ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t00 = time.time()
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    samples: dict = {}

    md5 = rp.source_jpeg_md5(PDF, XREF)
    prod = json.loads(PROD_READINGS.read_text())
    r1 = json.loads(ROUND1_READINGS.read_text())
    assert md5 == prod["source"]["embedded_jpeg_md5"] == r1["source"]["embedded_jpeg_md5"]
    src300 = rp.load_scan(PDF, XREF)
    print(f"[0] provenance ok; calibration: coarse={TEX_FIB_COARSE_MM}mm fine={TEX_FIB_FINE_MM}mm "
          f"grain={TEX_GRAIN_MM}mm aniso={TEX_ANISO_RATIO} rms_target={TEX_RMS_TARGET}", flush=True)

    # ── 1) 纸纹理对比板（600 vs 2400 vs 2400÷4；3 候选 × 幅度档 ＋ 旧口径反例）────────
    rows_board, row_labels, board = [], [], {}
    statF = TEX_STAT_FIELD_MM

    def board_row(tag, cand, amp_level, scale_extra=1.0):
        p600 = vs.to_u8(paper_patch_rows(cand, 600, TEX_FIELD_MM, amp_level, scale_extra))
        p2400 = vs.to_u8(paper_patch_rows(cand, 2400, TEX_FIELD_MM, amp_level, scale_extra))
        p2400_4 = cv2.resize(p2400, (p2400.shape[1] // 4, p2400.shape[0] // 4), interpolation=cv2.INTER_AREA)
        rows_board.append([p600, p2400, p2400_4])
        row_labels.append(tag)
        s600 = vs.to_u8(paper_patch_rows(cand, 600, statF, amp_level, scale_extra))
        s2400 = vs.to_u8(paper_patch_rows(cand, 2400, statF, amp_level, scale_extra))
        r6 = tex_readout(paper_lum_res(s600), 600, statF)
        r24 = tex_readout(paper_lum_res(s2400), 2400, statF)
        board[tag] = {"candidate": cand, "amp_level": amp_level,
                      "readout_600": r6, "readout_2400": r24,
                      "measured_600": paper_metrics(s600), "measured_2400": paper_metrics(s2400),
                      "cross_dpi_2400_div4_vs_600": cross_dpi_sim(s2400, s600),
                      "mm_consistency_2400_over_600": {
                          "autocorr_x": _ratio(r24["autocorr_half_decay_mm"]["x"], r6["autocorr_half_decay_mm"]["x"]),
                          "autocorr_y": _ratio(r24["autocorr_half_decay_mm"]["y"], r6["autocorr_half_decay_mm"]["y"]),
                          "psd_centroid": _ratio(r24["psd_centroid_cyc_per_mm"], r6["psd_centroid_cyc_per_mm"]),
                          "psd_peak_wavelength": _ratio(r24["psd_peak_wavelength_mm"], r6["psd_peak_wavelength_mm"])},
                      "octaves_600": octave_spec(cand, 600, scale_extra, amp_level) if cand else None,
                      "octaves_2400": octave_spec(cand, 2400, scale_extra, amp_level) if cand else None}
        print(f"[board] {tag}: ac_mm {r6['autocorr_half_decay_mm']}→{r24['autocorr_half_decay_mm']} "
              f"cen {r6['psd_centroid_cyc_per_mm']}→{r24['psd_centroid_cyc_per_mm']} "
              f"rms {r6['rms_0_255']}→{r24['rms_0_255']}", flush=True)

    board_row("旧·像素常量(反例)", None, 1.0)
    for c in CAND_ORDER:
        for al in AMP_LEVELS:
            board_row(f"C2·{c}×{al:g}", c, al)
    samples["tex_board"] = panel_grid(
        rows_board, row_labels,
        ["600dpi 1:1（8mm 视野）", "2400dpi 1:1（同一 8mm）", "2400dpi ÷4（回到 600 像素密度）"],
        SAMPLES_DIR / "tex-board-round2.png")
    print(f"[board] {samples['tex_board']['size_px']} {samples['tex_board']['bytes']}B", flush=True)

    # ── 2) 页面 @600dpi：源 / 掩膜 / 各版 ────────────────────────────────────────────
    src600 = rp.lanczos_up(src300, (SRC_W * 2, SRC_H * 2))
    src600_u8 = vs.to_u8(src600)
    mk = page_masks(src300, COMP_DPI)
    H6, W6 = SRC_H * 2, SRC_W * 2
    gray6, sat6 = vs.lum(src600_u8), vs.sat_of(src600_u8)
    dark_core = mk["outside"] & (gray6 < DARK_CORE)
    text_protect = cv2.dilate(dark_core.astype(np.uint8),
                              np.ones((2 * TEXT_PROTECT_PX + 1,) * 2, np.uint8)) > 0
    print(f"[masks600] red={int(mk['red'].sum())} white={int(mk['white'].sum())}", flush=True)

    c1 = (C1_BBOX[0] - 60, C1_BBOX[1] - 60, C1_BBOX[2] + 60, C1_BBOX[3] + 60)
    c2 = (C2_BBOX[0] - 60, C2_BBOX[1] - 60, C2_BBOX[2] + 60, C2_BBOX[3] + 60)
    step, pp = 20, 600
    S = cv2.boxFilter((mk["red"] | dark_core | mk["body"]).astype(np.float32), -1, (pp, pp),
                      normalize=False, borderType=cv2.BORDER_CONSTANT)
    valid = S[(pp // 2):(H6 - pp + pp // 2):step, (pp // 2):(W6 - pp + pp // 2):step]
    iy, ix = np.unravel_index(int(np.argmin(valid)), valid.shape)
    cy, cx = int(iy) * step + pp // 2, int(ix) * step + pp // 2
    paper_reg600 = (cx - pp // 2, cy - pp // 2, cx + pp // 2, cy + pp // 2)
    regions = {"P29-C1R1": c1, "P29-C2R1": c2,
               "P29-paper": tuple(v // 2 for v in paper_reg600)}

    core = cc.ink_core_centroid(src600_u8)
    core_mask = core["mask"]
    core_px_src = src600_u8[core_mask].astype(np.float64)
    print(f"[ink] core_px={int(core_mask.sum())} centroid={rgb_mean(core_px_src)} "
          f"ΔE={cc.delta_e2000(rgb_mean(core_px_src), cc.TARGET_RGB):.4f} "
          f"(seed≈{cc.ink_core_centroid(src600_u8)['sat_threshold']})", flush=True)

    # 颗粒标定：在 **2400dpi 源窗口**上量红墨区高通 σ（高斯半径＝参照物的**物理等价**换算），
    # 再补差值到参照物水平：σ_add = sqrt(max(target² − current², 0))
    _s = source_region(src300, C1_BBOX, PROD_DPI)
    _m = region_masks(src300, C1_BBOX, PROD_DPI)["red"]
    _er = cv2.erode(_m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    _lum = vs.lum(_s)
    src_grain_sigma = float((_lum - cv2.GaussianBlur(
        _lum, (0, 0), CAL["ink_grain_blur_sigma_px_at_ours"]))[_er].std())
    grain_target = float(CAL["ink_grain_lum_highpass_sigma_target"])
    grain_add = float(np.sqrt(max(grain_target ** 2 - src_grain_sigma ** 2, 0.0)))
    del _s, _m, _er, _lum
    print(f"[grain] 2400dpi 源窗口（未平滑）HF σ={src_grain_sigma:.3f} 0–255；豆包目标 "
          f"{grain_target:.3f}；★实际是**先平滑后量再补**：见各版 ink_ops.grain（σ_add 在管线内现算）",
          flush=True)

    # ── 3) 页面各版（观感档/严格档）＋ 冻结/确定性断言 ─────────────────────────────
    page_modes = ("C_old", "C2_strict", "C2_aes")
    variants: dict = {}
    vread: dict = {}
    for mode in page_modes:
        t = time.time()
        paper = paper_for(mode, H6, W6, COMP_DPI)
        v, rd = run_variant(mode, src600, mk, COMP_DPI, paper, grain_sigma_add=grain_add)
        v2, _ = run_variant(mode, src600, mk, COMP_DPI, paper, grain_sigma_add=grain_add)
        ref, _ = run_variant(mode, src600, mk, COMP_DPI, paper, ink_ops_on=False)
        d_out = int(((v != ref) & (~mk["red"])[:, :, None]).sum())
        d_white = int(((v != ref) & mk["white"][:, :, None]).sum())
        rd["determinism_rerun_bit_equal"] = bool(np.array_equal(v, v2))
        mv = np.asarray(cc.ink_mask(v.astype(np.float64)), bool)
        mr = np.asarray(cc.ink_mask(ref.astype(np.float64)), bool)
        n_flip = int((mv != mr).sum())
        rd["freeze"] = {"rule": "结构算子只写红墨区；白线区（掩膜内白文印白线）/掩膜外 对观感基线逐像素差=0",
                        "white_line_px": int(mk["white"].sum()), "white_line_mismatch_px": d_white,
                        "outside_px": int(mk["outside"].sum()), "outside_mismatch_px": d_out,
                        "assert_ok": bool(d_white == 0 and d_out == 0),
                        "red_mask_vs_own_baseline_diff_px": n_flip,
                        "red_mask_vs_own_baseline_diff_rate": round(float(n_flip) / float(mv.size), 10),
                        "red_mask_vs_own_baseline_unchanged": bool(n_flip == 0),
                        "mask_note": ("口径＝与**本版观感基线（ink_ops=False）**比；全局观感算子（光场/色调）"
                                      "两侧一致，故掩膜差异只可能来自结构算子。守卫按 float32 掩膜判定，"
                                      "uint8 量化可能翻转极少数边界像素（rate < 1e-4 视为逐像素不变）；"
                                      "C_old（上轮口径）无掩膜守卫 ⇒ 掩膜可变")}
        variants[mode] = v
        vread[mode] = rd
        del paper, v2, ref
        print(f"[{mode}] {rd['elapsed_s']}s rerun={rd['determinism_rerun_bit_equal']} "
              f"freeze={rd['freeze']['assert_ok']} "
              f"mask_kept={rd['freeze']['red_mask_vs_own_baseline_unchanged']}", flush=True)

    p_a, p_b = paper_for("C2_strict", 256, 256, COMP_DPI), paper_for("C2_strict", 256, 256, COMP_DPI)
    paper_determinism = bool(np.array_equal(p_a, p_b))
    del p_a, p_b

    # ── 4) 印泥读数（核心像素 → #C95021；ΔE/S 走 colorcal）─────────────────────────
    ink = {"target": {"hex": cc.TARGET_HEX, "rgb": list(cc.TARGET_RGB),
                      "lab": [round(v, 4) for v in TARGET_LAB],
                      "source_of_truth": "server/app/colorcal.py TARGET_RGB/TARGET_HEX（单一真源）"},
           "core_pixel_set": {"pixels": int(core_mask.sum()), "definition": "colorcal.ink_core_centroid（源图）",
                              "centroid_rgb": rgb_mean(core_px_src)},
           "delta_e_impl": "colorcal：Lab=colorcal._srgb_to_lab_arr；ΔE2000=colorcal.ciede2000_lab",
           "per_version": {}}
    chk = core_px_src[:200]
    lab_chk = cc._srgb_to_lab_arr(chk)
    d_chk = max(abs(cc.ciede2000_lab(lab_chk[i], TARGET_LAB) - cc.delta_e2000(chk[i], cc.TARGET_RGB))
                for i in range(chk.shape[0]))
    ink["delta_e2000_public_vs_batch_max_abs_diff"] = float(d_chk)
    for mode, img in (("SRC", src600_u8), *[(m, variants[m]) for m in page_modes]):
        px = img[core_mask].astype(np.float64)
        ink["per_version"][mode] = {"delta_e_to_target": delta_e_stats(px), "lab": lab_stats(px),
                                    "centroid_rgb": rgb_mean(px),
                                    "centroid_delta_e": round(float(cc.delta_e2000(rgb_mean(px), cc.TARGET_RGB)), 4)}
        s = ink["per_version"][mode]["delta_e_to_target"]
        print(f"[ink {mode}] ΔE med={s['median']} p90={s['p90']} ≤5={s['leq5_rate']} "
              f"L_std={ink['per_version'][mode]['lab'].get('L_std')}", flush=True)
    ink["doubao_ink_reference"] = {"targets_from": str(DOUBAO_INK.relative_to(REPO)),
                                   "median_rgb": CAL["ink_median_rgb"], "sat_p50": CAL["ink_sat_p50"],
                                   "delta_e_to_same_target": CAL["ink_delta_e_to_target"],
                                   "L_std": CAL["ink_L_std"],
                                   "note": "★ 参照图自身距 #C95021 就有 7.7 ΔE（其印泥比靶色更鲜）——"
                                           "我们的严格档应**明显小于**该值；豆包值仅作「参照物自身距离」登记"}
    # 平滑档位 / 算子顺序对照（C1 区 @2400dpi 窗口）
    outer_cmp: dict = {}

    # ── 5) 2400dpi 局部 1:1：档位阶梯（C1）＋ 四联（C2）＋ 纸底候选 ─────────────────
    def pick_window(mk_r, win):
        h, w = mk_r["red"].shape
        win = int(min(win, w - 20, h - 20))
        win -= win % 2
        dens = cv2.boxFilter((mk_r["red"] | mk_r["white"]).astype(np.float32), -1, (win, win),
                             normalize=False, borderType=cv2.BORDER_CONSTANT)
        v = dens[win // 2:h - win // 2:4, win // 2:w - win // 2:4]
        if v.size == 0:
            return (slice(0, h), slice(0, w))
        iy, ix = np.unravel_index(int(np.argmax(v)), v.shape)
        cy, cx = int(iy) * 4 + win // 2, int(ix) * 4 + win // 2
        return (slice(cy - win // 2, cy + win // 2), slice(cx - win // 2, cx + win // 2))

    ladder_txt = ("①原 2400dpi", "②C旧(px常量纹理)", "③严格档(靶色/平滑0)", "④＋平滑中",
                  "⑤＋平滑强", "⑥＋语义浓淡", "⑦＋语义＋颗粒", "⑧观感档全开(＋半透＋毛糙＋窄晕染)")
    reg2400: dict = {}
    for rn, box, win in (("P29-C1R1", C1_BBOX, 1400), ("P29-C2R1", C2_BBOX, 1300)):
        t = time.time()
        src_r = source_region(src300, box, PROD_DPI)
        mk_r = region_masks(src300, box, PROD_DPI)
        sl = pick_window(mk_r, win)
        srcw = src_r[sl]
        mk_w = {k: (v[sl] if isinstance(v, np.ndarray) and v.ndim == 2 and v.shape == mk_r["red"].shape
                    else v) for k, v in mk_r.items()}
        core_w = cc.ink_core_centroid(vs.to_u8(srcw))["mask"]
        p_mid = paper_for("C2_strict", srcw.shape[0], srcw.shape[1], PROD_DPI)
        ladder = (("C_old", "C2_strict", "C2_smoothmid", "C2_smoothstr", "C2_semantic", "C2_semgrain",
                   "C2_aes") if rn == "P29-C1R1" else ("C_old", "C2_strict", "C2_aes"))
        panels, reads = [vs.to_u8(srcw)], {}
        for mode in ladder:
            v, rd = run_variant(mode, srcw, mk_w, PROD_DPI, p_mid, grain_sigma_add=grain_add)
            panels.append(v)
            px = v[core_w].astype(np.float64)
            reads[mode] = {"label": VARIANTS[mode]["label"],
                           "delta_e_to_target": delta_e_stats(px), "lab": lab_stats(px),
                           "features_vs_doubao": dr.ink_features(
                               v, W_d=W_O_PX, mm_per_px=px2mm(1.0, PROD_DPI), label=mode,
                               grain_blur_sigma_px=CAL["ink_grain_blur_sigma_px_at_ours"]),
                           "ink_ops": rd["ink_ops"]}
            del v
        del p_mid
        if rn == "P29-C1R1":
            rows = [panels[0:4], panels[4:8]]
            labs = [list(ladder_txt[0:4]), list(ladder_txt[4:8])]
            fp = panel_grid(rows, [f"@{rn} 1:1"] * 2, labs,
                            SAMPLES_DIR / f"{rn}-2400-1to1-ladder-round2.png", left_w=190)
            samples[f"{rn}_2400_ladder"] = fp
            fp2 = panel_grid([rows[0]], [f"@{rn} 1:1"], labs[0],
                             SAMPLES_DIR / f"{rn}-2400-1to1-tier-round2.png", left_w=250)
            samples[f"{rn}_2400_tier"] = fp2
        else:
            fp = panel_grid([panels], [f"@{rn} 1:1"], list(ladder_txt)[0:4],
                            SAMPLES_DIR / f"{rn}-2400-1to1-round2.png", left_w=250)
            samples[f"{rn}_2400_1to1"] = fp
        reg2400[rn] = {"window_px": [win, win], "window_mm": round(px2mm(win, PROD_DPI), 3),
                       "window_origin_px": [int(sl[1].start), int(sl[0].start)],
                       "ink_readouts": reads,
                       "doubao_ink_reference": json.loads(DOUBAO_INK.read_text())["features"],
                       "elapsed_s": round(time.time() - t, 1)}
        print(f"[2400 {rn}] {fp['size_px']} done {time.time()-t:.1f}s", flush=True)
        del src_r, mk_r, mk_w, panels

    # 纸底区域 @2400dpi 1:1：旧口径 ＋ 3 候选（纯纸底 ⇒ 直接用生成器，逐像素可复现）
    winp = 1300
    prow = [_paper_patch_page(None, regions["P29-paper"], winp)] + \
        [_paper_patch_page(c, regions["P29-paper"], winp) for c in CAND_ORDER]
    samples["P29-paper_2400_1to1"] = panel_grid(
        [prow], ["@paper 1:1"], ["①旧·px常量", "②C2·CONS", "③C2·MID", "④C2·OBV"],
        SAMPLES_DIR / "P29-paper-2400-1to1-round2.png", left_w=170)
    paper_cand_metrics = {"old_px_const": paper_metrics(prow[0])}
    for i, c in enumerate(CAND_ORDER):
        paper_cand_metrics[c] = paper_metrics(prow[i + 1])
    paper_cand_metrics["note"] = ("1:1 实测于 2400dpi 纸底区域（1300×1300px ≈13.8mm），"
                                 "口径与豆包参照图同（亮度直方图/总 RMS/255 截顶占比）")

    # ── 6) 印面四联 @600dpi ＋ 整页缩略 ─────────────────────────────────────────────
    for rn in ("P29-C1R1", "P29-C2R1"):
        x0, y0, x1, y1 = [v * 2 for v in regions[rn]]
        reg = (slice(y0, y1), slice(x0, x1))
        fp = panel_grid([[src600_u8[reg], variants["C_old"][reg], variants["C2_strict"][reg],
                          variants["C2_aes"][reg]]], [f"@{rn}"],
                        ["①原 600dpi", "②C旧(上轮C)", "③C2严格档(靶色)", "④C2观感档(靶色＋mm纹理)"],
                        SAMPLES_DIR / f"{rn}-fourpanel-round2.png")
        samples[f"{rn}_fourpanel"] = fp
        print(f"[四联 {rn}] {fp['size_px']}", flush=True)

    th = (THUMB_W, round(H6 * THUMB_W / W6))
    thumbs = [np.asarray(Image.fromarray(p).resize(th, Image.Resampling.LANCZOS)) for p in
              (src600_u8, variants["C_old"], variants["C2_strict"], variants["C2_aes"])]
    samples["thumb"] = panel_grid([thumbs], ["@整页800px"],
                                  ["①原(600dpi)", "②C旧(上轮C)", "③C2严格档", "④C2观感档"],
                                  SAMPLES_DIR / "P29-thumb-round2.png", left_w=150)

    # ── 7) 换算表 + 读数落盘 ───────────────────────────────────────────────────────
    scale_rows = []
    for lbl, mm in (("云斑 mottle", TEX_MOTTLE_MM), ("粗纤维长轴", TEX_FIB_COARSE_MM),
                    ("粗纤维短轴", TEX_FIB_COARSE_MM / TEX_ANISO_RATIO),
                    ("细纤维长轴", TEX_FIB_FINE_MM), ("细纤维短轴", TEX_FIB_FINE_MM / TEX_ANISO_RATIO),
                    ("颗粒 grain", TEX_GRAIN_MM), ("印泥颗粒", INK_GRAIN_MM),
                    ("印泥边缘过渡", INK_EDGE_MM), ("晕染强段", HALO_STRONG_MM), ("晕染尾段", HALO_TAIL_MM),
                    ("保边平滑半径", GUIDE_RADIUS_MM), ("光场 σ", FIELD_SIGMA_MM),
                    ("微对比 σ", MICRO_SIGMA_MM), ("渗透 τ", PEN_TAU_MM),
                    ("（参照）真实纤维长 下沿", 0.5), ("（参照）真实纤维长 上沿", 3.0),
                    ("（参照）真实纤维宽 下沿", 0.02), ("（参照）真实纤维宽 上沿", 0.08)):
        row = {"item": lbl, "mm": round(mm, 5)}
        for d in DPI_TABLE:
            row[f"px@{d}"] = round(mm2px(mm, d), 3)
        row["≥2px"] = "".join("O" if mm2px(mm, d) >= 2 else "x" for d in DPI_TABLE)
        scale_rows.append(row)
    for lbl, pxv in (("旧·粗纤维长轴(px常量)", OLD_TEX["long_px"]), ("旧·粗纤维短轴", OLD_TEX["short_px"]),
                     ("旧·粗纤维2长轴", OLD_TEX["long2_px"]), ("旧·粗纤维2短轴", OLD_TEX["short2_px"])):
        row = {"item": lbl, "mm_at_600": round(px2mm(pxv, 600), 5)}
        for d in DPI_TABLE:
            row[f"mm@{d}"] = round(px2mm(pxv, d), 5)
        row["≥2px"] = "像素常量 ⇒ 物理尺度随 dpi 变（反例）"
        scale_rows.append(row)

    def md_table(rows, cols):
        return ("| " + " | ".join(cols) + " |\n| " + " | ".join("---" for _ in cols) + " |\n"
                + "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows))

    cand_rows = []
    for c in CAND_ORDER:
        s6 = octave_spec(c, 600)
        cand_rows.append({"候选": c, "档": CANDIDATES[c]["label"], "尺度×": CANDIDATES[c]["scale"],
                          "标称 RMS k": CANDIDATES[c]["k"],
                          "云斑 mm": round(s6[0]["long_mm"], 3),
                          "粗纤维长/短 mm": f"{s6[1]['long_mm']:.3f} / {s6[1]['short_mm']:.3f}",
                          "细纤维长/短 mm": f"{s6[2]['long_mm']:.3f} / {s6[2]['short_mm']:.3f}",
                          "颗粒 mm": round(s6[3]["long_mm"], 3),
                          "octave 幅度": " / ".join(f"{o['amp']:.3f}" for o in s6),
                          "实测纸底 RMS": paper_cand_metrics[c]["rms_lum_0_255"],
                          "255 截顶占比": paper_cand_metrics[c]["clip255_share"]})
    md = ["# C2 纹理换算表（mm ↔ px @300/600/1200/2400）\n",
          "> 真源：`ops/variant-samples/round2_samples.py` 顶部常量（**一律 mm**，单点可改）；",
          "> 尺度中心由豆包参照图标定（`doubao-reference-features.json` / `doubao-ink-reference-features.json`）。\n",
          "## 0. 豆包标定算式\n",
          f"- 纸纹理：`f_d = {CAL['fiber_peak_mm_from_fd']}mm`（＝W_o × f_d/W_d）；粗纤维带峰值 "
          f"{TEX_FIB_COARSE_MM}mm、细纤维带 {TEX_FIB_FINE_MM}mm、颗粒带 {TEX_GRAIN_MM}mm；"
          f"各向异性 长/短＝{TEX_ANISO_RATIO}（由参照图自相关 x:y 实测）\n",
          f"- 幅度：octave 幅度比（酉矢）＝mottle {AMP_UNIT[0]} / coarse {AMP_UNIT[1]} / "
          f"fine {AMP_UNIT[2]} / grain {AMP_UNIT[3]}（由参照图分带 RMS 比 "
          f"{CAL['band_rms_coarse_fine_grain']}）；纸底总 RMS 目标 {TEX_RMS_TARGET}（0–255）\n",
          f"- 印泥：语义 L* 曲线 {CAL['ink_semantic_L_curve']} @ dn {CAL['ink_semantic_dn_centers']}；"
          f"颗粒高通 σ 目标 {CAL['ink_grain_lum_highpass_sigma_target']}；边缘过渡 "
          f"{CAL['ink_edge_transition_mm']}mm；晕染过渡 {CAL['ink_halo_transition_mm']}mm / 外沿 "
          f"{CAL['ink_halo_outer_band_mm']}mm\n",
          "\n## 1. 尺度换算\n", md_table(scale_rows, ["item", "mm", "px@300", "px@600", "px@1200", "px@2400", "≥2px"]),
          "\n## 2. 旧口径（像素常量）的物理尺度漂移（反例）\n",
          md_table([r for r in scale_rows if "旧·" in r["item"]],
                   ["item", "mm_at_600", "mm@300", "mm@600", "mm@1200", "mm@2400", "≥2px"]),
          "\n## 3. 三组候选（豆包标定中心 ± 梯度）\n",
          md_table(cand_rows, ["候选", "档", "尺度×", "标称 RMS k", "云斑 mm", "粗纤维长/短 mm",
                               "细纤维长/短 mm", "颗粒 mm", "octave 幅度", "实测纸底 RMS", "255 截顶占比"]),
          "\n## 4. dpi 对齐读数（同一物理视野 12mm）\n"]
    for tag, br in board.items():
        r6, r24 = br["readout_600"], br["readout_2400"]
        md.append(f"\n**{tag}**：自相关半衰(mm) 600dpi x={r6['autocorr_half_decay_mm']['x']} / "
                  f"y={r6['autocorr_half_decay_mm']['y']} ↦ 2400dpi x={r24['autocorr_half_decay_mm']['x']} / "
                  f"y={r24['autocorr_half_decay_mm']['y']}（比值 "
                  f"{br['mm_consistency_2400_over_600']['autocorr_x']} / "
                  f"{br['mm_consistency_2400_over_600']['autocorr_y']}）；谱质心 "
                  f"{r6['psd_centroid_cyc_per_mm']} ↦ {r24['psd_centroid_cyc_per_mm']} cyc/mm（比值 "
                  f"{br['mm_consistency_2400_over_600']['psd_centroid']}）；峰值波长 "
                  f"{r6['psd_peak_wavelength_mm']} ↦ {r24['psd_peak_wavelength_mm']} mm；"
                  f"2400÷4 vs 600 逐像素 MAE(lum) {br['cross_dpi_2400_div4_vs_600']['mean_abs_diff_lum']}；"
                  f"RMS {r6['rms_0_255']} ↦ {r24['rms_0_255']}\n")
    SCALE_TABLE_PATH.write_text("".join(md) + "\n", encoding="utf-8")

    readings = {
        "schema": "feicui.variant-samples.readings-round2.v1",
        "generator": "ops/variant-samples/round2_samples.py",
        "page": PAGE,
        "intent": "C 修正版：①纹理改 mm 物理尺度＋多尺度带限噪声（豆包标定，3 候选×幅度档，600/2400 双对齐）"
                  "②印泥改向 #C95021 靠（复用 colorcal V3、保 L*）③严格档/观感档两套（语义浓淡/颗粒/半透/毛糙）",
        "doubao_calibration": CAL,
        "source": {"pdf": str(PDF.relative_to(REPO)), "xref": XREF, "embedded_jpeg_md5": md5,
                   "matches_production_and_round1": True, "size_px": [SRC_W, SRC_H], "dpi": SCAN_DPI},
        "geometry": {"compare_dpi": COMP_DPI, "prod_dpi": PROD_DPI,
                     "regions_300dpi": {k: list(v) for k, v in regions.items()},
                     "ours_ruler": {"W_o_px": W_O_PX, "W_o_mm": W_O_MM}},
        "target_hex_confirm": {"TARGET_HEX": cc.TARGET_HEX, "TARGET_RGB": list(cc.TARGET_RGB),
                               "hex_to_rgb_roundtrip": list(cc.hex_to_rgb(cc.TARGET_HEX)),
                               "from": "server/app/colorcal.py（import，不复制）"},
        "dpi_alignment": {"board": samples["tex_board"]["path"],
                          "visible_field_mm": TEX_FIELD_MM, "statistics_field_mm": TEX_STAT_FIELD_MM,
                          "criterion": "同物理尺度纹理在 600/2400dpi 上 自相关半衰长度(mm)/谱质心(cyc/mm)/"
                                       "峰值波长(mm) 换算后相等（比值≈1）；另做 2400÷4 vs 600 逐像素对照",
                          "rows": board},
        "ink_color": ink,
        "ink_grain_calibration": {"doubao_target_sigma_0_255": grain_target,
                                  "source_at_600_sigma": round(src_grain_sigma, 4),
                                  "added_sigma": round(grain_add, 4),
                                  "ours_blur_sigma_px_at_2400": CAL["ink_grain_blur_sigma_px_at_ours"],
                                  "formula": "σ_add = sqrt(max(target² − current², 0))（先量后补，幅度对齐参照物）"},
        "masks_600dpi": {"red_ink_px": int(mk["red"].sum()), "white_line_px": int(mk["white"].sum()),
                         "outside_px": int(mk["outside"].sum()), "paper_rule_px": int(mk["paper_rule"].sum()),
                         "mask_flip_rate_tolerance": MASK_FLIP_RATE_TOL,
                         "mask_flip_criterion": ("掩膜翻转率 ≤ 容差（uint8 量化级）；"
                                                 "**硬判据**是 freeze.assert_ok：白线区/掩膜外对观感基线逐像素差＝0"),
                         "impl": "colorcal.ink_mask → seal_canvas.seal_mask → ×2 Lanczos(≥128)"},
        "params": {"texture_mm": {"mottle": TEX_MOTTLE_MM, "fiber_coarse": TEX_FIB_COARSE_MM,
                                  "fiber_fine": TEX_FIB_FINE_MM, "grain": TEX_GRAIN_MM,
                                  "aniso_ratio": TEX_ANISO_RATIO},
                   "ink_mm": {"grain": INK_GRAIN_MM, "edge": INK_EDGE_MM,
                              "halo_strong": HALO_STRONG_MM, "halo_tail": HALO_TAIL_MM},
                   "smooth_levels": SMOOTH_LEVELS, "guide_radius_mm": GUIDE_RADIUS_MM,
                   "v3_fg_chroma_strength": float(cc.V3_FG_CHROMA_STRENGTH), "seed": SEED},
        "variants": vread,
        "paper_candidate_metrics_600dpi": paper_cand_metrics,
        "paper_generation_determinism_bit_equal": paper_determinism,
        "region_2400_1to1": reg2400,
        "samples": samples,
        "scale_table_md": str(SCALE_TABLE_PATH),
        "elapsed_s": round(time.time() - t00, 1),
    }
    READINGS_PATH.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = (all(vread[m]["freeze"]["assert_ok"] and vread[m]["determinism_rerun_bit_equal"]
              and vread[m]["freeze"]["red_mask_vs_own_baseline_diff_rate"] <= MASK_FLIP_RATE_TOL
              for m in page_modes)
          and paper_determinism and abs(d_chk) < 1e-12)
    print(json.dumps({"ok": ok, "freeze": {m: vread[m]["freeze"]["assert_ok"] for m in page_modes},
                      "rerun": {m: vread[m]["determinism_rerun_bit_equal"] for m in page_modes},
                      "mask_kept": {m: vread[m]["freeze"]["red_mask_vs_own_baseline_unchanged"]
                                    for m in page_modes},
                      "paper_det": paper_determinism, "dE_public_eq_batch": float(d_chk),
                      "elapsed_s": readings["elapsed_s"]}, ensure_ascii=False, indent=2), flush=True)
    return 0 if ok else 1


def _paper_patch_page(cand, reg300, win_px):
    """纸底区域 @2400dpi 的 1:1 片段（纯纸底 ⇒ 直接用生成器，不跑整页）。"""
    if cand is None:
        y0, x0 = reg300[1] * 8, reg300[0] * 8
        rows = np.arange(y0, y0 + win_px, dtype=np.int64)
        cols = np.arange(x0, x0 + win_px, dtype=np.int64)
        return vs.to_u8(old_paper_field(rows, cols, PROD_DPI))
    y0, x0 = reg300[1] * 8, reg300[0] * 8
    rows = np.arange(y0, y0 + win_px, dtype=np.int64)
    cols = np.arange(x0, x0 + win_px, dtype=np.int64)
    return vs.to_u8(paper_field_mm(rows, cols, PROD_DPI, cand))


if __name__ == "__main__":
    raise SystemExit(main())
