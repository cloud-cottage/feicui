#!/usr/bin/env python
"""选型样张（Kong · ops/variant-samples）：《秦印类编》页 29 局部 A/B/C/D 四版确定性算法变体。

需求真源＝Kevin 原始提示词（逐字存于技能 feicui-ingest `references/kevin-prompt-original.md`）。
冻结边界读法：**结构（字形/白线/轮廓）冻结、观感（背景/光场/印泥色彩）可调**；
白文印白线在红掩膜内部 ⇒ 掩膜分「红墨区/白线区」，平滑与校准只作用红墨区、白线区逐像素冻结。

统一几何：对比全部在 **600 dpi 等效**（源渲染 600 dpi＝内嵌 JPEG 300dpi 原生 ×2 Lanczos，
与产线 2400 dpi＝×8 同一重采样链；另以 pymupdf 600dpi 位图渲染作旁证观察项）。
A 底＝**产线真产物** `output/2_HighRes_PDF/9787550847224/P29-2400dpi-48bit.tif`（主版，校准 0.35）
裁区 ÷4（cv2 INTER_AREA）——不是重实现。

四版口径：
  A｜现行基线复刻：产线 2400dpi 主版页图 ÷4（产线真产物，含宣纸换底＋晕染＋色度校准 0.35）。
  B｜钤盖均匀版：源渲染底图＋宣纸换底（复用 seal_canvas 色域/种子常量＋render_page_2400
     位置哈希机制）＋印泥色度校准（colorcal 口径、0.35）＋【新增】红墨区保边平滑
     （guided filter，guide=亮度；顺序＝先校准后平滑，实测三项方差同时下降；
     白线区/掩膜外逐像素冻结）。
  C｜实拍观感版＝B＋【新增】①低频光场估计与去除（全局，先于换底——扫平扫描光照不均）
     ②全局色调映射（白平衡 gains=colorcal 真源＋轻柔 S 曲线＋微对比）③宣纸纹理升级
     （双层纤维＋颗粒＋极轻渗透感 α≤5%）。①②为全局观感算子（提示词②「全局均匀柔和
     微距实拍光线」）；结构算子仍只作用红墨区，白线区/掩膜外对「本版观感基线」逐像素冻结。
  D｜重质感版＝C＋【新增】红墨区重质感渲染（距白线/边缘距离场浓淡渐变：边缘浓中心自然
     ＋确定性微噪声）＋纸底彻底净化（净化圈大于 B/C 的生产纸底判据、但保护文字及其抗锯齿圈）。
     最接近豆包生成观感；全部确定性算子、字形结构零改动。

读数（ops/variant-samples/readings.json）：结构冻结校验（白线区/掩膜外对观感基线逐像素差=0
断言＋计数）、印泥区色度/明度方差（Lab）before→after、同参重跑逐像素一致性、A 产线溯源。

红线：不写 yinpu.db／不建 job／2_HighRes_PDF 与 output/books 只读／样张只落
output/samples/book-page-2400-variants/／可入库件只落 ops/variant-samples/／
render_page_2400.py 与 crop_c2r1.py 只读不改（import 复用）／生产常量只 import 不复制。

跑法：cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/variant-samples/variants_samples.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import tifffile
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))            # app.* ⇒ server/app（不被仓根 app.py 遮蔽）
sys.path.insert(0, str(REPO / "ops" / "book-page-2400"))
import render_page_2400 as rp                       # noqa: E402  生产整页实现（只读复用）
from app import seal_canvas as sc                   # noqa: E402  宣纸常量单一真源
from app import colorcal as cc                      # noqa: E402  色度/白平衡口径单一真源
from crop_c2r1 import extract_region_u16            # noqa: E402  既有 strip 级解码先例（只读复用）

# ── 常量（皆单点可改）──────────────────────────────────────────────────────────────
PDF = REPO / "output" / "1_Original_PDF" / "秦印类编 检索版.pdf"
PAGE = 29
XREF = 112
SCAN_DPI, COMP_DPI = 300, 600
U2 = COMP_DPI // SCAN_DPI                            # 2（源渲染 600dpi ＝ 300dpi 原生 ×2 Lanczos）
SRC_W, SRC_H = 2125, 3059
W6, H6 = SRC_W * U2, SRC_H * U2                      # 4250 × 6118

MAIN_TIF = REPO / "output/2_HighRes_PDF/9787550847224/P29-2400dpi-48bit.tif"
PROD_READINGS = REPO / "ops/book-page-2400/readings-P29-2400dpi-48bit.json"
SAMPLES_DIR = REPO / "output/samples/book-page-2400-variants"
OPS_DIR = Path(__file__).resolve().parent
READINGS_PATH = OPS_DIR / "readings.json"

# 页 29 印面 bbox（@300dpi，first_seal_probe 既有探测值；x0,y0,x1,y1）
C1_BBOX = (533, 555, 798, 823)                       # C1-R1 白文大方印（考验白线保护）
C2_BBOX = (1422, 560, 1565, 820)                     # C2-R1 细长条印
PAD300 = 60                                          # 外扩（含周边纸底）
THUMB_W = 800                                        # 整页缩略宽

# 宣纸（B 单层＝seal_canvas 常量 + render_page_2400 位置哈希机制；晶格按 600dpi 换算）
FIBER_CELL_LONG_600 = 16                             # 2400dpi 66px ÷4 ≈ 16.5 ⇒ ≈0.68mm
FIBER_CELL_SHORT_600 = 2                             # 2400dpi 7px ÷4 = 1.75 ⇒ 2
FIBER_CELL_LONG2_600 = 64                            # C/D 第二层粗纤维（≈2.7mm）
FIBER_CELL_SHORT2_600 = 8
FIBER2_SIGMA = 1.10
SEED = sc.BG_SEED_DEFAULT                            # 20261013（seal_canvas 单一真源）

CALIB_STRENGTH = 0.35                                # 与产线 --color-calib 默认一致
GUIDE_RADIUS_600 = 8                                 # B 保边平滑（≈0.34mm）
GUIDE_EPS = 1500.0                                   # 实测标定：红墨区斑驳方差量级 ⇒ 有效压平且保边
PAPER_MICRO_AMOUNT = 0.12                            # C/D 新纸底微对比（③ 纹理升级；作用于换底后、平滑前）
FIELD_SIGMA_600 = 25.0                               # C① 低频光场估计尺度（≈1mm）
FIELD_GAIN_LO, FIELD_GAIN_HI = 0.85, 1.15
SCURVE_T = 0.15                                      # C② 轻柔 S 曲线混合比
MICRO_AMOUNT, MICRO_SIGMA_600 = 0.10, 6.0            # C② 微对比
HALO_BAND_600 = 4                                    # ④ 晕染环带（2400dpi 16px ÷4；同 seal_canvas α≤8%）
PEN_ALPHA_MAX = 0.05                                 # C/D 极轻渗透感 α 上限
PEN_TAU_600 = 6.0                                    # 渗透衰减尺度
RELIEF_D0_600 = 12                                   # D 浓淡渐变作用半径（≈0.51mm）
RELIEF_STRENGTH = 0.15                               # 边缘增浓幅度（视觉复核后轻度下调）
NOISE_AMP = 1.8                                      # D 红墨区微噪声幅度（0–255）
DARK_CORE = 150                                      # 文字核心判据（< 此值）
D_PAPER_GRAY_MIN, D_PAPER_SAT_MAX = 165, 0.30        # D 净化圈（比生产纸底判据宽）
TEXT_PROTECT_PX = 2                                  # 文字抗锯齿圈保护半径（×2 dilate）
PANEL_GAP = 8

M1 = np.uint64(0xBF58476D1CE4E5B9)                   # 与 render_page_2400 同款位置哈希（本地别名）
M2 = np.uint64(0x94D049BB133111EB)


# ── 小工具 ────────────────────────────────────────────────────────────────────────
def lum(img: np.ndarray) -> np.ndarray:
    """亮度 Y（float32；Rec.601 系数，与扫描图像处理惯例一致）。"""
    f = img.astype(np.float32)
    return f[..., 0] * np.float32(0.299) + f[..., 1] * np.float32(0.587) + f[..., 2] * np.float32(0.114)


def sat_of(img: np.ndarray) -> np.ndarray:
    """逐像素饱和度 S=(max−min)/max（与 colorcal._sat_array 同式，float32）。"""
    f = img.astype(np.float32)
    mx, mn = f.max(axis=2), f.min(axis=2)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)


def srgb_lin_f32(c: np.ndarray) -> np.ndarray:
    """sRGB→线性（IEC 61966-2-1，与 colorcal.srgb_to_linear 同式；float32 域防整页 float64 峰值）。"""
    c = np.clip(c, 0.0, None).astype(np.float32)
    return np.where(c <= np.float32(0.04045), c / np.float32(12.92),
                    np.power((c + np.float32(0.055)) / np.float32(1.055), np.float32(2.4)))


def lin_srgb_f32(c: np.ndarray) -> np.ndarray:
    """线性→sRGB（与 colorcal.linear_to_srgb 同式；float32 域）。"""
    c = np.clip(c, 0.0, None).astype(np.float32)
    return np.where(c <= np.float32(0.0031308), c * np.float32(12.92),
                    np.float32(1.055) * np.power(c, np.float32(1.0 / 2.4)) - np.float32(0.055))


def to_u8(img_f32: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(img_f32, 0.0, 255.0)).astype(np.uint8)


def sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 宣纸生成（seal_canvas 常量 + render_page_2400 位置哈希机制；逐像素可复现、与分块无关）──
def _fiber_lattice_p(rows: np.ndarray, cols: np.ndarray, cell_long: int, cell_short: int,
                     seed: int, salt: int) -> np.ndarray:
    """各向异性 value-noise（机制同 render_page_2400._fiber_lattice，晶格常数参数化）。"""
    gy = (rows.astype(np.float64) + 0.5) / cell_short
    gx = (cols.astype(np.float64) + 0.5) / cell_long
    iy0, ix0 = np.floor(gy).astype(np.int64), np.floor(gx).astype(np.int64)
    fy, fx = gy - iy0, gx - ix0
    fy = fy * fy * (3.0 - 2.0 * fy)
    fx = fx * fx * (3.0 - 2.0 * fx)
    uy, ux = np.unique(iy0), np.unique(ix0)
    ry, cx = np.searchsorted(uy, iy0), np.searchsorted(ux, ix0)

    def corner(dy: int, dx: int) -> np.ndarray:
        h = rp._hash64(uy + dy, ux + dx, seed, salt + dy * 2 + dx)
        v = ((h >> np.uint64(0)) & np.uint64((1 << 21) - 1)).astype(np.float64) / float(1 << 21)
        return v[ry][:, cx]
    v00, v01, v10, v11 = corner(0, 0), corner(0, 1), corner(1, 0), corner(1, 1)
    top = v00 + (v01 - v00) * fx[None, :]
    bot = v10 + (v11 - v10) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def _paper_band(rows: np.ndarray, cols: np.ndarray, seed: int, upgraded: bool) -> np.ndarray:
    """宣纸底纹（float32 0–255）：基色＋纤维（B 单层 / C·D 双层）＋颗粒＋微色偏，clip 到色域。

    常量全部来自 seal_canvas（BG_*，单一真源）；噪声机制＝render_page_2400 位置哈希
    （与分块顺序无关）。晶格常数按 600dpi 物理尺度换算（见顶部常量）。
    """
    h1 = rp._hash64(rows, cols, seed, 0)
    u1 = np.maximum(((h1 >> np.uint64(0)) & np.uint64((1 << 31) - 1)).astype(np.float64)
                    / float(1 << 31), 1e-9)
    u2 = ((h1 >> np.uint64(31)) & np.uint64((1 << 31) - 1)).astype(np.float64) / float(1 << 31)
    grain = (np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)).astype(np.float32)
    h2 = rp._hash64(rows, cols, seed, 1)
    chroma = np.stack([((h2 >> np.uint64(0)) & np.uint64((1 << 21) - 1)).astype(np.float64) / float(1 << 21) - 0.5,
                       ((h2 >> np.uint64(21)) & np.uint64((1 << 21) - 1)).astype(np.float64) / float(1 << 21) - 0.5,
                       ((h2 >> np.uint64(42)) & np.uint64((1 << 21) - 1)).astype(np.float64) / float(1 << 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    fiber1 = (_fiber_lattice_p(rows, cols, FIBER_CELL_LONG_600, FIBER_CELL_SHORT_600, seed, 7).astype(np.float32)
              - np.float32(0.5)) / np.float32(_fiber_std_probe(FIBER_CELL_LONG_600, FIBER_CELL_SHORT_600, seed))
    lum_term = sc.BG_FIBER_SIGMA * fiber1 + sc.BG_GRAIN_SIGMA * grain
    if upgraded:
        fiber2 = (_fiber_lattice_p(rows, cols, FIBER_CELL_LONG2_600, FIBER_CELL_SHORT2_600, seed, 17)
                  .astype(np.float32) - np.float32(0.5)) / np.float32(
            _fiber_std_probe(FIBER_CELL_LONG2_600, FIBER_CELL_SHORT2_600, seed, 17))
        lum_term = lum_term + FIBER2_SIGMA * fiber2
    out = (np.asarray(sc.BG_BASE_RGB, np.float32)[None, None, :] + lum_term[:, :, None]
           + sc.BG_CHROMA_SIGMA * chroma)
    lo = np.asarray(sc.BG_MIN_RGB, np.float32)[None, None, :]
    hi = np.asarray(sc.BG_MAX_RGB, np.float32)[None, None, :]
    return np.clip(out, lo, hi)


_FIBER_STD_CACHE: dict[tuple, float] = {}


def _fiber_std_probe(cl: int, cs: int, seed: int, salt: int = 7) -> float:
    key = (cl, cs, seed, salt)
    if key not in _FIBER_STD_CACHE:
        r = np.arange(0, 1024, dtype=np.int64)
        _FIBER_STD_CACHE[key] = float(
            (_fiber_lattice_p(r, r, cl, cs, seed, salt).astype(np.float64) - 0.5).std())
    return _FIBER_STD_CACHE[key]


def gen_paper(h: int, w: int, seed: int, upgraded: bool, band: int = 512) -> np.ndarray:
    """整页宣纸（uint8）：按行带生成（位置哈希 ⇒ 与分块无关、内存有界）。"""
    out = np.empty((h, w, 3), np.uint8)
    for y0 in range(0, h, band):
        y1 = min(y0 + band, h)
        rows = np.arange(y0, y1, dtype=np.int64)
        cols = np.arange(0, w, dtype=np.int64)
        out[y0:y1] = to_u8(_paper_band(rows, cols, seed, upgraded))
    return out


# ── 算子 ──────────────────────────────────────────────────────────────────────────
def guided_smooth_color(img: np.ndarray, guide_y: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """联合 guided filter（guide=亮度，box-filter 实现；各通道共享导向⇒色相一致）。"""
    k = 2 * radius + 1
    meanI = cv2.boxFilter(guide_y, -1, (k, k), normalize=True)
    meanI2 = cv2.boxFilter(guide_y * guide_y, -1, (k, k), normalize=True)
    varI = meanI2 - meanI * meanI
    out = np.empty_like(img)
    for ch in range(3):
        c = img[:, :, ch]
        meanC = cv2.boxFilter(c, -1, (k, k), normalize=True)
        covIC = cv2.boxFilter(guide_y * c, -1, (k, k), normalize=True) - meanI * meanC
        a = covIC / (varI + np.float32(eps))
        b = meanC - a * meanI
        out[:, :, ch] = cv2.boxFilter(a, -1, (k, k), normalize=True) * guide_y \
            + cv2.boxFilter(b, -1, (k, k), normalize=True)
    return out


def field_gain(img: np.ndarray, paper_m: np.ndarray) -> tuple[np.ndarray, dict]:
    """C① 低频光场估计与去除：纸区低频亮度场归一到其 p90，逐像素增益（限幅）。"""
    y = lum(img)
    pm = paper_m.astype(np.float32)
    num = cv2.GaussianBlur(y * pm, (0, 0), FIELD_SIGMA_600)
    den = cv2.GaussianBlur(pm, (0, 0), FIELD_SIGMA_600)
    field = num / np.maximum(den, np.float32(1e-6))
    ref = float(np.percentile(field[paper_m], 90.0))
    gain = np.clip(ref / np.maximum(field, np.float32(1e-6)),
                   np.float32(FIELD_GAIN_LO), np.float32(FIELD_GAIN_HI)).astype(np.float32)
    stats = {"field_ref_p90": round(ref, 3),
             "gain_min": round(float(gain[paper_m].min()), 4),
             "gain_max": round(float(gain[paper_m].max()), 4),
             "gain_mean_paper": round(float(gain[paper_m].mean()), 5)}
    return img * gain[:, :, None], stats


def tone_map(img: np.ndarray, paper_m: np.ndarray) -> tuple[np.ndarray, dict]:
    """C② 全局色调映射：白平衡（gains＝colorcal 真源）＋轻柔 S 曲线＋微对比。"""
    paper_rgb = img[paper_m].astype(np.float64).mean(axis=0)
    g = cc.whitebalance_gains_for(tuple(float(v) for v in paper_rgb))
    k = np.asarray(g["gains"], np.float32)
    lin = srgb_lin_f32(img / np.float32(255.0)) * k
    img = lin_srgb_f32(lin) * np.float32(255.0)
    x = np.clip(img, 0.0, 255.0) / np.float32(255.0)
    s = (np.float32(1.0 - SCURVE_T)) * x + np.float32(SCURVE_T) * (
        np.float32(0.5) - np.float32(0.5) * np.cos(np.float32(np.pi) * x))
    img = s * np.float32(255.0)
    blur = cv2.GaussianBlur(img, (0, 0), MICRO_SIGMA_600)
    img = img + np.float32(MICRO_AMOUNT) * (img - blur)
    stats = {"wb_paper_rgb_before": [round(float(v), 2) for v in paper_rgb],
             "wb_gains": [round(float(v), 5) for v in g["gains"]],
             "wb_clamped": g["clamped"], "s_curve_t": SCURVE_T,
             "micro_amount": MICRO_AMOUNT, "micro_sigma_px600": MICRO_SIGMA_600}
    return img, stats


def ink_chroma_mean(img: np.ndarray, red_m: np.ndarray) -> tuple[float, float]:
    """印泥归一化色度均值（与 render_page_2400.build_ctx 同式）。"""
    px = img[red_m].astype(np.float64)
    tot = np.maximum(px.sum(axis=1, keepdims=True), 1.0)
    ch = (px / tot).mean(axis=0)
    return float(ch[0]), float(ch[1])


def ink_lab_stats(img_u8: np.ndarray, red_m: np.ndarray) -> dict:
    """印泥区 Lab 读数（L*/a*/b* 均值与标准差——色度/明度方差口径）。"""
    if not red_m.any():
        return {"l_mean": None, "l_std": None, "a_std": None, "b_std": None}
    lab = cv2.cvtColor(img_u8[:, :, ::-1], cv2.COLOR_BGR2LAB).astype(np.float64)
    L, A, B = lab[..., 0][red_m], lab[..., 1][red_m], lab[..., 2][red_m]
    return {"l_mean": round(float(L.mean()), 3), "l_std": round(float(L.std()), 3),
            "a_std": round(float(A.std()), 3), "b_std": round(float(B.std()), 3)}


# ── 变体管线 ──────────────────────────────────────────────────────────────────────
def run_variant(name: str, src600: np.ndarray, mk: dict, *, ink_ops: bool) -> tuple[np.ndarray, dict]:
    """单版全页管线（float32 域；返回 uint8 页图与读数）。

    结构冻结实现：结构算子（平滑/校准/重质感/噪声）只写红墨区 red_m；
    白线区 white_m 与掩膜外 outside_m 只受观感算子（换底/光场/色调/晕染/渗透）作用，
    且这些算子的参数（晕染/渗透色＝换底后、平滑前印泥均值）在 ink_ops 开关两侧一致
    ⇒「白线区/掩膜外 对 本版观感基线 逐像素差=0」可断言。
    """
    t0 = time.time()
    img = src600.astype(np.float32).copy()
    red_m, white_m, outside_m = mk["red"], mk["white"], mk["outside"]
    readings: dict = {"version": name}
    # ①② 全局观感算子（提示词②）：作用于**扫描态**、先于换底 ⇒ 扫平扫描光照/色温/色调，
    #   新纸底不受影响（换底后是程序化宣纸，本就不带扫描光照不均）
    if name in ("C", "D"):
        img, fstat = field_gain(img, mk["paper_rule"])
        img, tstat = tone_map(img, mk["paper_rule"])
        readings["light_field"] = fstat
        readings["tone_map"] = tstat
    # ① 背景替换（B：单层宣纸 seal_canvas 口径；C/D：双层纤维＋颗粒，③ 升级）
    bg_zone = mk["d_zone"] if name == "D" else mk["paper_rule"]
    paper = mk["paper_base"] if name == "B" else mk["paper_up"]
    img[bg_zone] = paper[bg_zone]
    if name in ("C", "D"):
        # ③ 宣纸纹理升级（微对比）：只落新纸底；在 ink_ops 之前 ⇒ 冻结参考两侧一致
        blur = cv2.GaussianBlur(img, (0, 0), MICRO_SIGMA_600)
        img[bg_zone] = img[bg_zone] + np.float32(PAPER_MICRO_AMOUNT) * (img - blur)[bg_zone]
    readings["background"] = {
        "mode": ("single_layer_seal_canvas" if name == "B" else "double_layer_fiber_grain"),
        "zone": ("paper_rule_prod(gray>=210,sat<=0.15,non-ink)" if name != "D"
                 else f"purified(gray>={D_PAPER_GRAY_MIN},sat<={D_PAPER_SAT_MAX},~text_protect)"),
        "zone_px": int(bg_zone.sum()),
        "constants_from": "server/app/seal_canvas.py (BG_* 单一真源)",
    }
    # 观感算子参数锚点：换底后、平滑前的印泥均值（ink_ops 开关两侧一致 ⇒ 冻结断言成立）
    ink_mean = img[red_m].astype(np.float64).mean(axis=0) if red_m.any() else None
    # C/D 渗透感（换底区上的外缘环带；色＝锚点印泥均值）
    if name in ("C", "D") and ink_mean is not None:
        d_out = mk["dist_outside"]
        a = np.where((d_out > HALO_BAND_600) & (d_out <= 24.0),
                     PEN_ALPHA_MAX * np.exp(-(d_out - HALO_BAND_600) / PEN_TAU_600), 0.0).astype(np.float32)
        a = a * bg_zone.astype(np.float32)          # 只落换底纸底，不碰文字/白线/本体
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        readings["penetration"] = {"alpha_max": PEN_ALPHA_MAX, "tau_px600": PEN_TAU_600,
                                   "band_px600": [HALO_BAND_600, 24], "px": int((a > 0).sum())}
    # ④ 晕染（各版同规：掩膜外侧环带、α≤8%、线性衰减；色＝锚点印泥均值）
    if ink_mean is not None:
        d_out = mk["dist_outside"]
        a = np.where(~mk["body"], np.clip(
            (HALO_BAND_600 + 1.0 - d_out) / float(HALO_BAND_600), 0.0, 1.0) * sc.HALO_ALPHA_MAX,
            0.0).astype(np.float32)
        img = img * (1.0 - a[:, :, None]) + np.asarray(ink_mean, np.float32)[None, None, :] * a[:, :, None]
        readings["halo"] = {"band_px600": HALO_BAND_600, "alpha_max": sc.HALO_ALPHA_MAX,
                            "alpha_inside_mask_max": 0.0, "px": int((a > 0).sum()),
                            "color_rgb": [round(float(v), 2) for v in ink_mean]}
    if ink_ops and red_m.any():
        pre = img.copy()
        # 印泥色度校准（render_page_2400.color_uniformity 同一实现；保 ΣRGB）——先校准
        cm = ink_chroma_mean(img, red_m)
        img, _t, n_inv = rp.color_uniformity(img, red_m, cm, CALIB_STRENGTH)
        # B/C/D 新增·红墨区保边平滑（guided，guide=亮度；白线区/掩膜外不写）——后平滑
        #   实测（ops/variant-samples 探针）：先校准后平滑 ⇒ L*/a*/b* 三项方差相对源图同时下降
        y = lum(img)
        sm = guided_smooth_color(img, y, GUIDE_RADIUS_600, GUIDE_EPS)
        img[red_m] = sm[red_m]
        del sm
        readings["ink_ops"] = {"guided": {"radius_px600": GUIDE_RADIUS_600, "eps": GUIDE_EPS,
                                          "guide": "luminance", "order": "after_calib"},
                               "calib": {"strength": CALIB_STRENGTH,
                                         "chroma_mean": [round(v, 6) for v in cm],
                                         "skipped_invalid_domain_px": int(n_inv),
                                         "impl": "render_page_2400.color_uniformity（单一真源复用）"}}
        if name == "D":
            # 重质感：距白线/边缘距离场浓淡渐变（边缘浓中心自然）＋确定性微噪声
            d_in = cv2.distanceTransform(mk["red_u8"], cv2.DIST_L2, 3).astype(np.float32)
            w = np.clip(d_in / np.float32(RELIEF_D0_600), 0.0, 1.0)
            factor = 1.0 - np.float32(RELIEF_STRENGTH) * (1.0 - w)
            rows = np.arange(img.shape[0], dtype=np.int64)
            cols = np.arange(img.shape[1], dtype=np.int64)
            n = (rp._u(rp._hash64(rows, cols, SEED, 9), 0, 20) - 0.5) * (2.0 * NOISE_AMP)
            sel = red_m
            img[sel] = img[sel] * factor[sel][:, None] + n[sel][:, None].astype(np.float32)
            readings["ink_ops"]["relief"] = {
                "distance_field": "dist_to_non_ink(L2)", "d0_px600": RELIEF_D0_600,
                "strength": RELIEF_STRENGTH, "noise_amp": NOISE_AMP,
                "noise_impl": "render_page_2400 位置哈希（seed 固定）",
                "edge_darken_mean_pct": round(float((1.0 - factor[red_m]).mean() * 100), 3)}
        fin_red = np.rint(np.clip(img[red_m], 0, 255))
        pre_red = np.rint(np.clip(pre[red_m], 0, 255))
        readings["ink_ops"]["changed_px_vs_pre"] = int((fin_red != pre_red).any(axis=1).sum())
        del pre, fin_red, pre_red
    out = to_u8(img)
    del img
    readings["elapsed_s"] = round(time.time() - t0, 2)
    return out, readings


# ── A 底：产线 2400dpi 主版 ÷4（流式 strip 解码，整页不驻留 16bit）──────────────────
def build_a600() -> np.ndarray:
    out = np.empty((H6, W6, 3), np.uint8)
    with tifffile.TiffFile(MAIN_TIF) as tf:
        page = tf.pages[0]
        assert page.shape == (H6 * 4, W6 * 4, 3) and page.dtype == np.uint16, page.shape
        rps = int(page.rowsperstrip)
        fh = page.parent.filehandle
        n = len(page.dataoffsets)
        for s in range(n):
            fh.seek(page.dataoffsets[s])
            band16 = page.decode(fh.read(page.databytecounts[s]), s)[0][0]
            y0, y1 = s * rps, min((s + 1) * rps, H6 * 4)
            small = cv2.resize(band16, (W6, (y1 - y0) // 4), interpolation=cv2.INTER_AREA)
            out[y0 // 4: y1 // 4] = rp.q8(small)
            del band16, small
    return out


# ── 五联并排 ──────────────────────────────────────────────────────────────────────
LABELS = ("SRC 600dpi", "A prod/4", "B even", "C photo", "D texture")


def five_panel(panels: list[np.ndarray], path: Path) -> dict:
    h = max(p.shape[0] for p in panels)
    w = sum(p.shape[1] for p in panels) + PANEL_GAP * (len(panels) - 1)
    canvas = np.full((h + 22, w, 3), 32, np.uint8)
    x = 0
    for p in panels:
        canvas[22:22 + p.shape[0], x:x + p.shape[1]] = p
        x += p.shape[1] + PANEL_GAP
    im = Image.fromarray(canvas)
    d = ImageDraw.Draw(im)
    x = 0
    for lab, p in zip(LABELS, panels):
        d.text((x + 4, 4), lab, fill=(255, 255, 255))
        x += p.shape[1] + PANEL_GAP
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="PNG", compress_level=6)
    return {"path": str(path), "bytes": int(path.stat().st_size),
            "sha256": sha256_file(path), "size_px": [im.width, im.height]}


# ── 主流程 ────────────────────────────────────────────────────────────────────────
def main() -> int:
    t00 = time.time()
    # 0) 溯源自证：内嵌 JPEG md5 ＝ 产线读数记录值（源同一性）
    md5 = rp.source_jpeg_md5(PDF, XREF)
    prod = json.loads(PROD_READINGS.read_text())
    prod_md5 = prod["source"]["embedded_jpeg_md5"]
    assert md5 == prod_md5, f"内嵌 JPEG md5 不一致: {md5} vs 产线 {prod_md5}"

    # 1) 源与掩膜
    src300 = rp.load_scan(PDF, XREF)
    seg = sc.seal_mask(src300)
    red300, body300 = seg["raw"], (seg["mask"] | seg["holes"])
    paper300, ink300 = rp.build_masks(src300)
    assert np.array_equal(ink300, red300), "rp.build_masks 与 seal_canvas.seal_mask 印泥掩膜不一致"
    up = lambda m: rp.upsample_mask(m, (W6, H6))  # noqa: E731
    red600, body600, paper_rule600 = up(red300), up(body300), up(paper300) & ~up(body300)
    white600, outside600 = body600 & ~red600, ~body600
    src600 = rp.lanczos_up(src300, (W6, H6))
    src600_u8 = to_u8(src600)
    gray6, sat6 = lum(src600_u8), sat_of(src600_u8)
    dark_core = outside600 & (gray6 < DARK_CORE)
    text_protect = cv2.dilate(dark_core.astype(np.uint8),
                              np.ones((2 * TEXT_PROTECT_PX + 1,) * 2, np.uint8)) > 0
    mk = {
        "red": red600, "white": white600, "outside": outside600, "body": body600,
        "paper_rule": paper_rule600, "red_u8": red600.astype(np.uint8),
        "dist_outside": cv2.distanceTransform((~body600).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32),
        "d_zone": outside600 & ~text_protect & (gray6 >= D_PAPER_GRAY_MIN) & (sat6 <= D_PAPER_SAT_MAX),
    }
    mk["paper_base"] = gen_paper(H6, W6, SEED, upgraded=False)   # B：单层（seal_canvas 口径）
    mk["paper_up"] = gen_paper(H6, W6, SEED, upgraded=True)      # C/D：双层纤维＋颗粒
    print(f"[masks] red={red600.sum()} white={white600.sum()} outside={outside600.sum()} "
          f"paper_rule={paper_rule600.sum()} d_zone={mk['d_zone'].sum()}", flush=True)

    # 2) A 底（产线 ÷4）＋ 区域坐标
    t = time.time()
    a600 = build_a600()
    print(f"[A] production ÷4 built in {time.time()-t:.1f}s", flush=True)
    c1 = (473, 495, 858, 883)                        # C1 bbox 外扩 60（@300dpi）
    c2 = (1362, 500, 1625, 880)                      # C2 bbox 外扩 60（@300dpi）
    # 纯纸底补丁：确定性搜索 600×600（@600dpi）＝300×300@300——积分图（boxFilter）求
    # 「印泥∪文字∪掩膜」像素数最少的窗口，平局取扫描序首个（行优先）
    step, pp = 20, 600
    indicator = (red600 | dark_core | body600).astype(np.float32)
    S = cv2.boxFilter(indicator, -1, (pp, pp), normalize=False, borderType=cv2.BORDER_CONSTANT)
    valid = S[(pp // 2):(H6 - pp + pp // 2):step, (pp // 2):(W6 - pp + pp // 2):step]
    iy, ix = np.unravel_index(int(np.argmin(valid)), valid.shape)
    cy, cx = int(iy) * step + pp // 2, int(ix) * step + pp // 2        # boxFilter 锚点＝窗口中心
    wx0, wy0 = cx - pp // 2, cy - pp // 2                              # 窗口左上角（已在页内）
    best = float(S[cy, cx])
    paper_reg = (wx0 // 2, wy0 // 2, wx0 // 2 + pp // 2, wy0 // 2 + pp // 2)   # @300dpi 300×300
    print(f"[paper patch] @300dpi {paper_reg} score={best}", flush=True)

    regions = {
        "P29-C1R1": {"crop600": (c1[0] * 2, c1[1] * 2, c1[2] * 2, c1[3] * 2), "crop300": c1},
        "P29-C2R1": {"crop600": (c2[0] * 2, c2[1] * 2, c2[2] * 2, c2[3] * 2), "crop300": c2},
        "P29-paper": {"crop600": (wx0, wy0, wx0 + pp, wy0 + pp), "crop300": paper_reg},
    }

    # 3) 变体全页（×2 重跑判一致性；ink_ops=False 为冻结参考）
    variants: dict[str, np.ndarray] = {}
    vread: dict[str, dict] = {}
    for name in ("B", "C", "D"):
        t = time.time()
        v, rd = run_variant(name, src600, mk, ink_ops=True)
        v2, _ = run_variant(name, src600, mk, ink_ops=True)
        ref, _ = run_variant(name, src600, mk, ink_ops=False)
        d_leak = int(((v != ref) & (~red600)[:, :, None]).sum())
        d_white = int(((v != ref) & white600[:, :, None]).sum())
        rd["determinism_rerun_bit_equal"] = bool(np.array_equal(v, v2))
        rd["freeze"] = {
            "rule": "白线区/掩膜外 对 本版观感基线（ink_ops=False）逐像素差=0",
            "white_line_px": int(white600.sum()), "white_line_mismatch_px": d_white,
            "outside_px": int(outside600.sum()), "outside_mismatch_px": d_leak,
            "assert_ok": bool(d_white == 0 and d_leak == 0),
            "note": ("白线区/掩膜外允许被全局观感算子（光场/色调，提示词②）作用；冻结断言针对"
                     "结构算子（平滑/校准/重质感）——其只写红墨区、不得外泄"),
        }
        variants[name] = v
        vread[name] = rd
        print(f"[{name}] done {time.time()-t:.1f}s | rerun_equal={rd['determinism_rerun_bit_equal']} "
              f"| freeze_ok={rd['freeze']['assert_ok']}", flush=True)

    # 4) pymupdf 600dpi 渲染旁证（观察项：与 ×2 Lanczos 链的差异）
    import pymupdf
    doc = pymupdf.open(PDF)
    pm = doc[PAGE - 1].get_pixmap(dpi=COMP_DPI, colorspace=pymupdf.csRGB, alpha=False)
    ren = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, 3).copy()  # pymupdf RGB
    if (pm.height, pm.width) != (H6, W6):                # 页尺寸 ±1pt 容差 ⇒ 归一到同一几何
        ren = cv2.resize(ren, (W6, H6), interpolation=cv2.INTER_AREA)
    prov = {}
    for rn, r in regions.items():
        x0, y0, x1, y1 = r["crop600"]
        a, b = src600_u8[y0:y1, x0:x1].astype(np.int16), ren[y0:y1, x0:x1].astype(np.int16)
        prov[rn] = {"mean_abs_diff": round(float(np.abs(a - b).mean()), 3),
                    "max_abs_diff": int(np.abs(a - b).max())}
    print("[pymupdf600 provenance]", prov, flush=True)

    # 5) 区域五联样张＋印泥方差读数
    samples: dict[str, dict] = {}
    for rn, r in regions.items():
        x0, y0, x1, y1 = r["crop600"]
        reg = (slice(y0, y1), slice(x0, x1))
        reg_red = red600[reg]
        panels = [src600_u8[reg], a600[reg], variants["B"][reg], variants["C"][reg], variants["D"][reg]]
        ink_stats = {"before_src600": ink_lab_stats(panels[0], reg_red),
                     "A_prod": ink_lab_stats(panels[1], reg_red),
                     "B_even": ink_lab_stats(panels[2], reg_red),
                     "C_photo": ink_lab_stats(panels[3], reg_red),
                     "D_texture": ink_lab_stats(panels[4], reg_red)}
        fp = five_panel(panels, SAMPLES_DIR / f"{rn}-fivepanel.png")
        samples[rn] = {"crop300dpi": list(r["crop300"]), "crop600dpi": [x1 - x0, y1 - y0],
                       "ink_px": int(reg_red.sum()), "ink_lab_before_after": ink_stats, "panel": fp,
                       "dark_text_core_px": int(dark_core[reg].sum()),
                       "seal_body_px": int(body600[reg].sum()),
                       "white_line_px": int(white600[reg].sum())}
        print(f"[panel {rn}] {fp['size_px']} {fp['bytes']}B | L*std {ink_stats['before_src600']['l_std']}"
              f"→B{ink_stats['B_even']['l_std']}→C{ink_stats['C_photo']['l_std']}→D{ink_stats['D_texture']['l_std']}",
              flush=True)

    # 纸底补丁读数（各版：均值/标准差/极值/高频纹理能量/255 截顶占比）
    def paper_readout(u8: np.ndarray) -> dict:
        x0, y0, x1, y1 = regions["P29-paper"]["crop600"]
        g = u8[y0:y1, x0:x1].astype(np.float32)
        hp = g - cv2.GaussianBlur(g, (0, 0), MICRO_SIGMA_600)
        flat = g.reshape(-1, 3)
        return {"mean_rgb": [round(float(v), 2) for v in flat.mean(0)],
                "std_rgb": [round(float(v), 2) for v in flat.std(0)],
                "min_rgb": [int(v) for v in flat.min(0)], "max_rgb": [int(v) for v in flat.max(0)],
                "highpass_std": round(float(hp.std()), 3),
                "clip255_share": round(float((g >= 255.0).mean()), 4)}

    paper_ro = {"SRC": paper_readout(src600_u8), "A_prod": paper_readout(a600)}
    for n in ("B", "C", "D"):
        paper_ro[n] = paper_readout(variants[n])
        vread[n]["paper_extract_readout"] = paper_ro[n]
    print("[paper readout]", json.dumps(paper_ro, ensure_ascii=False), flush=True)

    # 整页尺度纸底读数：候选背景＝掩膜外 ∧ 非文字核心 ∧ 非文字保护圈；
    # 额外报「未换底残点」（＝候选背景中不满足本版换底判据者）——B/C 用生产判据、D 用净化圈
    bg_all = outside600 & ~dark_core & ~text_protect

    def page_bg_readout(u8: np.ndarray, zone_used: np.ndarray | None = None) -> dict:
        g = u8[bg_all].astype(np.float32)
        gmax, gmin = g.max(axis=1), g.min(axis=1)
        sat = np.where(gmax > 0, (gmax - gmin) / np.maximum(gmax, 1.0), 0.0)
        out = {"px": int(g.shape[0]), "mean_rgb": [round(float(v), 2) for v in g.mean(0)],
               "std_rgb": [round(float(v), 2) for v in g.std(0)],
               "share_gray_lt_248": round(float((g.mean(axis=1) < 248).mean()), 4),
               "share_sat_gt_0.10": round(float((sat > 0.10).mean()), 4)}
        if zone_used is not None:
            left = bg_all & ~zone_used
            gl = u8[left].astype(np.float32) if left.any() else np.zeros((0, 3), np.float32)
            out["not_replaced_px"] = int(left.sum())
            out["not_replaced_share"] = round(float(left.sum()) / max(1, int(bg_all.sum())), 4)
            out["not_replaced_mean_rgb"] = ([round(float(v), 2) for v in gl.mean(0)] if len(gl) else None)
        return out

    page_bg = {"SRC": page_bg_readout(src600_u8), "A_prod": page_bg_readout(a600)}
    for n, zn in (("B", mk["paper_rule"]), ("C", mk["paper_rule"]), ("D", mk["d_zone"])):
        page_bg[n] = page_bg_readout(variants[n], zn)
        vread[n]["page_scale_background"] = page_bg[n]
    print("[page-scale bg]", json.dumps(page_bg, ensure_ascii=False), flush=True)

    # 整页缩略（800px 宽）五联
    th = (THUMB_W, round(H6 * THUMB_W / W6))
    thumbs = [np.asarray(Image.fromarray(p).resize(th, Image.Resampling.LANCZOS)) for p in
              (src600_u8, a600, variants["B"], variants["C"], variants["D"])]
    tp = five_panel(thumbs, SAMPLES_DIR / "P29-thumb-fivepanel.png")
    print(f"[panel thumb] {tp['size_px']} {tp['bytes']}B", flush=True)

    # A 区域抽检：A600 切片 ≡ strip 级独立裁取 ÷4（C1 区）
    x0, y0, x1, y1 = regions["P29-C1R1"]["crop600"]
    with tifffile.TiffFile(MAIN_TIF) as tf:
        ref16 = extract_region_u16(tf.pages[0], y0 * 4, y1 * 4, x0 * 4, x1 * 4)
    ref8 = rp.q8(cv2.resize(ref16, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA))
    a_spot = bool(np.array_equal(a600[y0:y1, x0:x1], ref8))

    readings = {
        "schema": "feicui.variant-samples.readings.v1",
        "generator": "ops/variant-samples/variants_samples.py",
        "page": PAGE,
        "source": {"pdf": str(PDF.relative_to(REPO)), "xref": XREF,
                   "embedded_jpeg_md5": md5, "embedded_jpeg_md5_matches_production": bool(md5 == prod_md5),
                   "size_px": [SRC_W, SRC_H], "dpi": SCAN_DPI},
        "geometry": {"compare_dpi": COMP_DPI,
                     "src_render_600": "内嵌 JPEG 300dpi 原生 ×2 Lanczos（与产线 2400dpi=×8 同一重采样链）",
                     "a_base": "P29-2400dpi-48bit.tif（主版，校准0.35）÷4 cv2.INTER_AREA → q8",
                     "regions_300dpi": {rn: r["crop300"] for rn, r in regions.items()},
                     "pymupdf600_vs_lanczos2_observation": prov},
        "a_note": ("A＝产线真产物复刻：底图直接取自 output/2_HighRes_PDF/9787550847224/"
                   "P29-2400dpi-48bit.tif（render_page_2400.py 主版：宣纸换底＋晕染＋色度校准0.35），"
                   "非重实现；区域抽检 strip 级独立裁取 ÷4 与整页流式 ÷4 逐像素一致="
                   f"{a_spot}；★生产脚本 render_page_2400.py 的 PDF 常量仍指向 inbox/20261011/"
                   "（已不存在，四总目录迁移后源件在 output/1_Original_PDF/）——本次以内嵌 JPEG "
                   "md5 与产线读数记录一致证同源，脚本未改。"),
        "a_spotcheck_strip_crop_equal": a_spot,
        "masks_600dpi": {"red_ink_px": int(red600.sum()), "white_line_px": int(white600.sum()),
                         "outside_px": int(outside600.sum()),
                         "paper_rule_px": int(paper_rule600.sum()), "d_purified_zone_px": int(mk["d_zone"].sum()),
                         "impl": "colorcal.ink_mask（单一真源）→ seal_canvas.seal_mask 闭运算/孔洞 → ×2 Lanczos≥128"},
        "params": {"calib_strength": CALIB_STRENGTH, "guided": [GUIDE_RADIUS_600, GUIDE_EPS],
                   "field_sigma600": FIELD_SIGMA_600, "s_curve_t": SCURVE_T,
                   "halo_band600": HALO_BAND_600, "relief": [RELIEF_D0_600, RELIEF_STRENGTH, NOISE_AMP],
                   "seed": SEED},
        "variants": vread,
        "paper_extract_readout": paper_ro,
        "page_scale_background": page_bg,
        "samples": samples,
        "thumb_panel": tp,
        "elapsed_s": round(time.time() - t00, 1),
    }
    READINGS_PATH.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = all(vread[n]["freeze"]["assert_ok"] and vread[n]["determinism_rerun_bit_equal"]
             for n in ("B", "C", "D")) and a_spot
    print(json.dumps({"a_spotcheck": a_spot,
                      "freeze_ok": {n: vread[n]["freeze"]["assert_ok"] for n in ("B", "C", "D")},
                      "rerun_equal": {n: vread[n]["determinism_rerun_bit_equal"] for n in ("B", "C", "D")},
                      "panels": {rn: samples[rn]["panel"]["path"] for rn in samples}},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
