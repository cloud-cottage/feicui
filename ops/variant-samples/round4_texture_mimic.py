#!/usr/bin/env python
"""② 三版示例纹理合成样张（Kong · ops/variant-samples/round4_texture_mimic.py）。

从豆包纸底（`round4_material_adequacy` 盘点：池 904.9mm²、4mm 不重叠 patch 仅 13 块、
平均复用 R=51.5×）学纹理形态，出三版样张与读数：

- **R2 patch quilting**（最可能像）：素材 4mm patch（含半步重叠窗口）按最小误差边界拼接
  （Efros-Freeman 风：重叠带 SSD 最小 → top-k 随机选一 → 羽化融合 → 局部均值对齐）；
- **R1 频谱匹配合成**：估豆包纸底分带（mm）幅度/峰波长/各向异性 → 固定种子随机相位
  （`round2_samples.vnoise_mm` 的 **mm 位置哈希**，跨 dpi 是同一场）重建 → 任意尺寸、不复制像素；
- **R3 混合**：低频（云斑带 1.35–3mm）取自豆包条带（池内 4.5mm 高条带、行高 3.5–6.5mm
  抖动拼铺＋1.5mm 羽化），高频（coarse/fine/grain ≤1.35mm）走 R1 机制。

纪律：纹理尺度一律 **mm 物理定义**（band 波长、patch 边长、重叠/羽化、窗与页尺寸全部 mm，
按输出 dpi 换算 px）；**确定性**（固定种子 SEED=20261016，同参重跑逐像素一致）；
豆包图**只读**；生产常量一字不动（只 import）。

尺度口径：`ma.MM_PER_PX = 22.437/923`（明示假设：豆包印面实物宽＝C1-R1 的 22.437mm）。
判据（每版）：① vs 豆包：分带能量占比 L1 / 自相关半衰(mm) / 总 RMS / 明度分位；
② 整页 600dpi 场自相关无异常周期峰（给峰位与幅度）；③ 同参重跑逐位一致；
④ 1200 vs 2400（2400→1200 下采样）mm 尺度 rel_diff。

跑法：cd /Users/kevin/bistro/feicui && ./venv/bin/python ops/variant-samples/round4_texture_mimic.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))
sys.path.insert(0, str(REPO / "ops" / "variant-samples"))
import round4_material_adequacy as ma                               # noqa: E402  素材盘点/掩膜单源
import round2_samples as r2                                         # noqa: E402  mm 位置哈希噪声单源

OUT_DIR = REPO / "output/samples/book-page-2400-variants/round4-texture-mimic"
READINGS = Path(__file__).resolve().parent / "readings-round4.json"
MM_PER_IN = 25.4
SRC_EQ_DPI = int(round(MM_PER_IN / ma.MM_PER_PX))  # 豆包图等效 dpi（1044.9）＝素材原生分辨率
SEED = 20261016                                    # 本轮固定种子（确定性判据用）
BAND_NAMES = ("cloud", "coarse", "fine", "grain")
BAND_SALTS = {"cloud": 4071, "coarse": 4113, "fine": 4157, "grain": 4199}
CHROMA_SALT = 9001
PATCH_MM = 4.0                                     # R2 patch 边长（mm；素材池最大可用档）
OVERLAP_MM = 0.68                                  # R2 重叠带宽度（mm）
TOPK = 8                                           # R2 最小误差候选里随机选一的范围
PAGE_DPI = 600                                     # 整页缩略的生成 dpi（4250×6118）
PAGE_W_MM, PAGE_H_MM = ma.PAGE_W_MM, ma.PAGE_H_MM  # 179.9×259.0 mm
WIN_W_MM, WIN_H_MM = 40.0, 26.0                    # 1:1 展示窗（mm）
WIN0_MM = (20.0, 30.0)                             # 窗口锚点（页 mm；纸场平稳，任取）
DDPI_MM = (24.0, 16.0)                             # 双 dpi 对齐窗（mm）
FEATHER_MM = 1.5                                   # R3 条带羽化（mm）
STRIP_H_MM = (3.5, 6.5)                            # R3 行高抖动范围（mm）
SLAB_ROWS = 384                                    # 逐 slab 渲染（内存）


def mm2px(mm: float, dpi: int) -> int:
    return max(1, int(round(mm * dpi / MM_PER_IN)))


def lum(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    return f[..., 0] * np.float32(0.299) + f[..., 1] * np.float32(0.587) + f[..., 2] * np.float32(0.114)


# ══════════════════════════════════════════════════════════════════════════════════════
# 读数（判据①；与 ma 同一套 band 定义/PSD，保证口径一致）
# ══════════════════════════════════════════════════════════════════════════════════════
def ac_2d_halfdecay(res: np.ndarray, mm_per_px: float, max_lag_mm: float = 6.0) -> dict:
    """2D 自相关（FFT）→ x/y 方向半衰长度（mm）。"""
    a = res.astype(np.float64)
    a -= a.mean()
    F = np.fft.rfft2(a)
    ac = np.fft.fftshift(np.fft.irfft2(np.abs(F) ** 2, s=a.shape))
    h, w = a.shape
    cy, cx = h // 2, w // 2
    lag = int(min(round(max_lag_mm / mm_per_px), cx - 2, cy - 2))
    acx = ac[cy - 1:cy + 2, cx:cx + lag + 1].mean(axis=0)
    acy = ac[cy:cy + lag + 1, cx - 1:cx + 2].mean(axis=1)
    return {"half_decay_x_mm": round(ma.half_decay(acx / acx[0]) * mm_per_px, 4),
            "half_decay_y_mm": round(ma.half_decay(acy / acy[0]) * mm_per_px, 4)}


def texture_readings(lumf: np.ndarray, mm_per_px: float) -> dict:
    res = lumf.astype(np.float32) - float(lumf.mean())
    rp = ma.radial_psd_mm(res, mm_per_px)
    fc, psd, cnt = (np.array(rp["f_cyc_per_mm"]), np.array(rp["psd"]), np.array(rp["count"]))
    shares = ma.band_energy_share(fc, psd, cnt)
    brms = {k: round(ma.band_rms(res, lo, hi, mm_per_px), 4) for k, (lo, hi) in ma.BANDS_MM.items()}
    ac = ac_2d_halfdecay(res, mm_per_px)
    return {"lum_std": round(float(res.std()), 4),
            "band_rms_0_255": brms,
            "band_energy_share": {k: (None if v is None else v["energy_share"]) for k, v in shares.items()},
            "peak_wavelength_mm": {k: (None if v is None else v["peak_wavelength_mm"]) for k, v in shares.items()},
            **ac,
            "lum_quantiles": {f"p{p}": round(float(np.percentile(lumf, p)), 3)
                              for p in (1, 5, 25, 50, 75, 90, 95, 99)}}


def band_l1(share_syn: dict, share_ref: dict) -> float:
    tot, n = 0.0, 0
    for k in BAND_NAMES:
        a, b = share_syn.get(k), share_ref.get(k)
        if a is not None and b is not None:
            tot += abs(float(a) - float(b))
            n += 1
    return round(tot, 6)


def vs_reference(syn_readings: dict, ref: dict) -> dict:
    """判据①的逐项对照（合成窗口 vs 豆包素材补丁中位）。"""
    return {
        "band_energy_share_L1": band_l1(syn_readings["band_energy_share"],
                                        ref["band_energy_share"]),
        "band_rms_0_255": {k: {"syn": syn_readings["band_rms_0_255"][k],
                               "ref": ref["band_rms_0_255"][k],
                               "rel_diff": round(abs(syn_readings["band_rms_0_255"][k] -
                                                     ref["band_rms_0_255"][k]) /
                                                 max(ref["band_rms_0_255"][k], 1e-9), 4)}
                           for k in BAND_NAMES},
        "lum_std": {"syn": syn_readings["lum_std"], "ref": ref["texture_rms_0_255"]},
        "half_decay_mm": {"syn": [syn_readings["half_decay_x_mm"], syn_readings["half_decay_y_mm"]],
                          "ref": [ref["half_decay_x_mm"], ref["half_decay_y_mm"]]},
        "peak_wavelength_mm": {k: {"syn": syn_readings["peak_wavelength_mm"][k],
                                   "ref": ref["peak_wavelength_mm"][k]} for k in BAND_NAMES},
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# 参照读数（豆包素材侧；同一套代码路径）
# ══════════════════════════════════════════════════════════════════════════════════════
def reference_readings(rgb: np.ndarray, pool: np.ndarray) -> dict:
    p = mm2px(4.0, SRC_EQ_DPI)
    spots = [(x, y) for y in range(0, rgb.shape[0] - p + 1, p)
             for x in range(0, rgb.shape[1] - p + 1, p) if pool[y:y + p, x:x + p].all()]
    per, means = [], []
    for (x, y) in spots:
        sub = rgb[y:y + p, x:x + p].astype(np.float32)
        res = lum(sub) - float(lum(sub).mean())
        rd = texture_readings(res, ma.MM_PER_PX)
        per.append(rd)
        means.append(float(lum(sub).mean()))
    med_of = lambda key: round(float(np.median([d[key] for d in per])), 6)  # noqa: E731
    res_c = np.stack([rgb[y:y + p, x:x + p].astype(np.float32) for (x, y) in spots])
    res_c = res_c - res_c.mean(axis=(1, 2), keepdims=True)
    sig = res_c.std(axis=(0, 1, 2)).astype(np.float64)
    corr = np.corrcoef(res_c.reshape(-1, 3).T)
    patch_med_rgb = np.median(np.stack(
        [np.median(rgb[y:y + p, x:x + p].astype(np.float32), axis=(0, 1)) for (x, y) in spots]), axis=0)
    return {
        "n_patches": len(spots), "patch_side_mm": 4.0,
        "patch_origins_px": [[int(x), int(y)] for (x, y) in spots],
        "texture_rms_0_255": med_of("lum_std"),
        "band_rms_0_255": {k: round(float(np.median([d["band_rms_0_255"][k] for d in per])), 4)
                           for k in BAND_NAMES},
        "band_energy_share": {k: round(float(np.median([d["band_energy_share"][k] for d in per
                                                        if d["band_energy_share"][k] is not None])), 6)
                              if any(d["band_energy_share"][k] is not None for d in per) else None
                              for k in BAND_NAMES},
        "peak_wavelength_mm": {k: round(float(np.median([d["peak_wavelength_mm"][k] for d in per
                                                         if d["peak_wavelength_mm"][k] is not None])), 4)
                               if any(d["peak_wavelength_mm"][k] is not None for d in per) else None
                               for k in BAND_NAMES},
        "half_decay_x_mm": med_of("half_decay_x_mm"),
        "half_decay_y_mm": med_of("half_decay_y_mm"),
        "lum_quantiles_median": {f"p{p}": round(float(np.median(
            [d["lum_quantiles"][f"p{p}"] + m for d, m in zip(per, means)])), 3)
            for p in (1, 5, 25, 50, 75, 90, 95, 99)},
        "per_channel_residual_sigma": [round(float(v), 4) for v in sig],
        "interchannel_corr_mean": round(float((corr[0, 1] + corr[0, 2] + corr[1, 2]) / 3.0), 4),
        "paper_mean_rgb": [round(float(v), 3) for v in rgb[pool].astype(np.float32).mean(axis=0)],
        "paper_base_rgb": [round(float(v), 3) for v in patch_med_rgb],
        "paper_base_note": "基色＝13 patch 各自中位 RGB 的中位（对齐明度分位 p50；池均值含 255 截顶偏置）",
        "anisotropy_y_over_x": None,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# R1 频谱匹配合成（mm 位置哈希；slab 流式）
# ══════════════════════════════════════════════════════════════════════════════════════
def octave_model(ref: dict, bands=BAND_NAMES) -> list[dict]:
    """octave 格距＝λ/2（value-noise 峰波长≈2×格距）；各向异性 a=y/x →
    cell_y/cell_x=a 且 √(cell_x·cell_y)=λ/2（径向等效峰不变）。"""
    aniso = float(ref["anisotropy_y_over_x"])
    out = []
    for k in bands:
        peak = float(ref["peak_wavelength_mm"][k])
        if k in ("coarse", "fine"):
            cl = peak / (2.0 * np.sqrt(aniso))
            cs = peak * np.sqrt(aniso) / 2.0
        else:
            cl = cs = peak / 2.0
        out.append({"name": k, "long_mm": round(cl, 6), "short_mm": round(cs, 6),
                    "salt": BAND_SALTS[k], "amp": float(ref["band_rms_0_255"][k])})
    return out


def r1_lum(rows: np.ndarray, cols: np.ndarray, dpi: int, model: list[dict],
           calib: dict | None = None) -> np.ndarray:
    r_mm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    c_mm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    out = np.zeros((rows.size, cols.size), np.float32)
    for o in model:
        n = r2.vnoise_mm(r_mm, c_mm, o["long_mm"], o["short_mm"], SEED, o["salt"])
        ref = r2.octave_std_ref(o["long_mm"], o["short_mm"], SEED, o["salt"])
        k = 1.0 if calib is None else float(calib.get(o["name"], 1.0))
        out += (np.float32(o["amp"] * k / ref) * (n.astype(np.float32) - np.float32(0.5)))
    return out


def calibrate_octaves(dpi: int, model: list[dict], tile_mm: float = 12.0) -> dict:
    """逐 octave **隔离标定**（单 octave 场实测其 DoG 带 RMS → factor＝目标/实测；无带间泄漏）
    ＋ 合成后联合实测（record-only）。确定性。"""
    n = mm2px(tile_mm, dpi)
    rows = np.arange(0, n, dtype=np.int64)
    cols = np.arange(0, n, dtype=np.int64)
    mmpp = MM_PER_IN / dpi
    factors, isolated = {}, []
    for o in model:
        f = r1_lum(rows, cols, dpi, [o])
        res = f - float(f.mean())
        meas = ma.band_rms(res, *ma.BANDS_MM[o["name"]], mmpp)
        factors[o["name"]] = round(float(o["amp"]) / max(meas, 1e-6), 6)
        isolated.append({"name": o["name"], "band_rms_measured": round(meas, 4),
                         "target": o["amp"], "factor": factors[o["name"]]})
    f = r1_lum(rows, cols, dpi, model, factors)
    res = f - float(f.mean())
    joint = {k: round(ma.band_rms(res, lo, hi, mmpp), 4) for k, (lo, hi) in ma.BANDS_MM.items()}
    return {"tile_mm": tile_mm, "method": "per-octave isolated（单 octave 场测带 RMS→factor）＋joint record",
            "factors": factors, "isolated": isolated, "joint_band_rms_after": joint}


def synth_rgb(lumf: np.ndarray, ref: dict, dpi: int, y0_px: int = 0,
              chroma_salt: int = CHROMA_SALT) -> np.ndarray:
    """基色 ＋ 亮度场（通道共享）＋ 独立通道残差（σ 与通道间相关按素材实测）。"""
    sig = np.asarray(ref["per_channel_residual_sigma"], np.float32)
    rho = float(np.clip(ref["interchannel_corr_mean"], 0.0, 0.999))
    h, w = lumf.shape
    sl = max(float(lumf.std()), 1e-6)
    base = np.asarray(ref.get("paper_base_rgb", ref["paper_mean_rgb"]), np.float32)
    shared = lumf / sl
    rows = np.arange(y0_px, y0_px + h, dtype=np.int64)
    cols = np.arange(0, w, dtype=np.int64)
    ind_sig = sig * np.float32(np.sqrt(max(1.0 - rho * rho, 0.0)))
    out = np.empty((h, w, 3), np.float32)
    mmp = MM_PER_IN / float(dpi)                       # 真 mm/px（通道残差场跨 dpi 同一场）
    rp = (rows.astype(np.float64) + 0.5) * mmp
    cp = (cols.astype(np.float64) + 0.5) * mmp
    for ci in range(3):
        n1 = r2.vnoise_mm(rp, cp, 0.09, 0.09, SEED, chroma_salt + ci)
        n2 = r2.vnoise_mm(rp, cp, 0.4, 0.4, SEED, chroma_salt + 10 + ci)
        ind = np.float32(0.5) * (n1.astype(np.float32) - np.float32(0.5)) + \
            np.float32(0.5) * (n2.astype(np.float32) - np.float32(0.5))
        ind = ind / max(float(ind.std()), 1e-6)
        out[..., ci] = base[ci] + sig[ci] * rho * shared + ind_sig[ci] * ind
    return out


def render_field(h: int, w: int, dpi: int, ref: dict, model: list[dict], calib: dict,
                 low_field: np.ndarray | None = None, low_gain: float = 1.0) -> np.ndarray:
    """slab 流式渲染（R1：model 全带；R3：model_high＋low_field）。"""
    cols = np.arange(0, w, dtype=np.int64)
    out = np.empty((h, w, 3), np.float32)
    for y0 in range(0, h, SLAB_ROWS):
        rows = np.arange(y0, min(y0 + SLAB_ROWS, h), dtype=np.int64)
        f = r1_lum(rows, cols, dpi, model, calib["factors"])
        rgbf = synth_rgb(f, ref, dpi, y0_px=y0)
        if low_field is not None:
            sig = np.asarray(ref["per_channel_residual_sigma"], np.float32)
            sl = max(float(f.std()), 1e-6)
            rgbf = rgbf + (low_field[y0:y0 + rows.size][..., None] *
                           (np.float32(low_gain) * sig / np.float32(sl))[None, None, :])
        out[y0:y0 + rows.size] = rgbf
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# R2 patch quilting（最小误差边界 ＋ 羽化融合 ＋ 局部均值对齐）
# ══════════════════════════════════════════════════════════════════════════════════════
def material_at_dpi(rgb: np.ndarray, pool: np.ndarray, dpi: int) -> tuple[np.ndarray, np.ndarray]:
    f = ma.MM_PER_PX * dpi / MM_PER_IN
    mat = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4)
    pool_r = cv2.resize(pool.astype(np.float32), None, fx=f, fy=f,
                        interpolation=cv2.INTER_AREA) >= 0.999
    return mat, pool_r


def patch_pool(mat: np.ndarray, pool_r: np.ndarray, p: int) -> list[tuple[int, int]]:
    h, w = pool_r.shape
    wins, seen = [], set()
    for step in (p, max(p // 2, 1)):
        for y in range(0, h - p + 1, step):
            for x in range(0, w - p + 1, step):
                if (x, y) not in seen and pool_r[y:y + p, x:x + p].all():
                    wins.append((x, y))
                    seen.add((x, y))
    return wins


def quilt(h: int, w: int, dpi: int, mat: np.ndarray, wins: list[tuple[int, int]],
          patch_mm: float = PATCH_MM, overlap_mm: float = OVERLAP_MM, seed: int = SEED,
          base_rgb: np.ndarray | None = None, progress: bool = False) -> np.ndarray:
    p, O = mm2px(patch_mm, dpi), max(8, mm2px(overlap_mm, dpi))
    C = p - O
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w, 3), np.float32)
    base = (np.asarray(base_rgb, np.float32) if base_rgb is not None
            else mat[wins[0][1]:wins[0][1] + 1, wins[0][0]:wins[0][0] + 1].reshape(3).astype(np.float32))

    def axis_bounds(n: int) -> list[int]:
        """抖动网格：步长 C×U(0.62,0.95)（C 由 mm 派生；固定种子 ⇒ 确定性）。
        打散规则格距的周期峰（实测规则格距在 3.3mm≈C 出 ac 0.65 峰）；重叠＝p−步长 ≥ 0.62C ≥ O。"""
        b = [0]
        while b[-1] < n:
            b.append(min(n, b[-1] + max(1, int(round(C * float(rng.uniform(0.62, 0.95)))))))
        return b

    ys, xs = axis_bounds(h), axis_bounds(w)
    ramp_x = np.linspace(0.0, 1.0, O, dtype=np.float32)
    t0, ncell = time.time(), 0
    for gy in ys[:-1]:
        for gx in xs[:-1]:
            ph, pw = min(p, h - gy), min(p, w - gx)
            tgt = out[gy:gy + ph, gx:gx + pw]
            left, top = gx > 0, gy > 0
            sel = np.zeros((ph, pw), bool)
            if left:
                sel[:, :O] = True
            if top:
                sel[:O, :] = True
            cands = np.empty((len(wins), ph, pw, 3), np.float32)
            scores = np.empty(len(wins), np.float64)
            for i, (wx, wy) in enumerate(wins):
                c = mat[wy:wy + ph, wx:wx + pw].astype(np.float32)
                cm = c.mean(axis=(0, 1))
                c -= cm
                tm = tgt[sel].mean(axis=0) if (left or top) else base
                c += tm
                cands[i] = c
                if left or top:
                    d = c[sel] - tgt[sel]
                    scores[i] = float(np.sum(d * d))
                else:
                    scores[i] = 0.0
            order = np.argsort(scores, kind="stable")[:TOPK]
            pick = int(rng.integers(0, order.size))
            cand = cands[order[pick]]
            wgt = np.ones((ph, pw), np.float32)
            if left:
                wgt[:, :O] *= ramp_x[:pw][None, :] if pw < O else ramp_x[None, :]
            if top:
                wgt[:O, :] *= ramp_x[:ph][:, None] if ph < O else ramp_x[:, None]
            reg = out[gy:gy + ph, gx:gx + pw]
            out[gy:gy + ph, gx:gx + pw] = reg * (1.0 - wgt[..., None]) + cand * wgt[..., None]
            ncell += 1
            if progress and ncell % 800 == 0:
                print(f"    [quilt] cell {ncell}  {time.time()-t0:.1f}s", flush=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# R3 混合（低频＝豆包条带抖动拼铺；高频＝R1 机制）
# ══════════════════════════════════════════════════════════════════════════════════════
def cloud_strips(rgb: np.ndarray, pool: np.ndarray) -> list[dict]:
    """池内水平条带（左右条带旋转 90°），DoG(1.35–3mm) 取云斑带，零均值。"""
    s_lo = (1.35 / (2 * np.pi)) / ma.MM_PER_PX
    s_hi = (3.0 / (2 * np.pi)) / ma.MM_PER_PX
    lf = lum(rgb).astype(np.float32)
    band = cv2.GaussianBlur(lf, (0, 0), s_lo) - cv2.GaussianBlur(lf, (0, 0), s_hi)
    min_side = mm2px(3.0, SRC_EQ_DPI)
    min_len = mm2px(10.0, SRC_EQ_DPI)

    def runs(idx: np.ndarray) -> list[tuple[int, int]]:
        out, s = [], None
        for i, v in enumerate(idx):
            if s is None:
                s = int(v)
            if i + 1 == len(idx) or idx[i + 1] != v + 1:
                out.append((s, int(v) + 1))
                s = None
        return out

    strips = []
    good_rows = np.where(pool.mean(axis=1) >= 0.95)[0]
    for (y0, y1) in [r for r in runs(good_rows) if r[1] - r[0] >= min_side]:
        xs = np.where(pool[y0:y1].all(axis=0))[0]
        for (x0, x1) in [c for c in runs(xs) if c[1] - c[0] >= min_len]:
            b = band[y0:y1, x0:x1].copy()
            strips.append({"kind": "row", "bbox_px": [x0, y0, x1 - x0, y1 - y0],
                           "band": b - float(b.mean())})
    good_cols = np.where(pool.mean(axis=0) >= 0.95)[0]
    for (x0, x1) in [c for c in runs(good_cols) if c[1] - c[0] >= min_side]:
        ys = np.where(pool[:, x0:x1].all(axis=1))[0]
        for (y0, y1) in [r for r in runs(ys) if r[1] - r[0] >= min_len]:
            b = band[y0:y1, x0:x1].T.copy()                  # 旋转 90° 成水平条带
            strips.append({"kind": "col(rot90)", "bbox_px": [x0, y0, x1 - x0, y1 - y0],
                           "band": b - float(b.mean())})
    strips.sort(key=lambda s: -(s["band"].shape[0] * s["band"].shape[1]))
    return strips


def r3_low_field(h: int, w: int, dpi: int, strips: list[dict]) -> np.ndarray:
    """条带拼铺：行高 3.5–6.5mm 抖动、x 向随机偏移、1.5mm 羽化（固定种子；mm 尺度精确）。"""
    rng = np.random.default_rng(SEED + 7)
    out = np.zeros((h, w), np.float32)
    wsum = np.zeros((h, w), np.float32)
    f_px = max(2, mm2px(FEATHER_MM, dpi))
    mm_per_px = MM_PER_IN / dpi
    y = 0
    i = 0
    while y < h:
        s = strips[i % len(strips)]
        i += 1
        src = s["band"]
        src_h_mm = src.shape[0] * ma.MM_PER_PX
        hi_mm = min(STRIP_H_MM[1], max(STRIP_H_MM[0], src_h_mm - 2 * FEATHER_MM))
        hh = max(2 * f_px + 2, mm2px(float(rng.uniform(STRIP_H_MM[0], hi_mm)), dpi))
        y1 = min(h, y + hh)
        ph = y1 - y
        sy = ma.MM_PER_PX / mm_per_px                        # 源px→目标px：保物理 mm（src_px·MM_PER_PX mm＝target_px·mm_per_px）
        sw = max(2, int(round(src.shape[1] * sy)))
        sh = max(2, int(round(src.shape[0] * sy)))
        tile = cv2.resize(src, (sw, sh), interpolation=cv2.INTER_LINEAR)
        if tile.shape[1] < w + 2 * f_px:
            reps = int(np.ceil((w + 2 * f_px) / tile.shape[1])) + 1
            tile = np.tile(tile, (1, reps))
        xoff = int(rng.integers(0, tile.shape[1] - w))
        yoff = int(rng.integers(0, max(1, tile.shape[0] - ph)))   # 行高 ≤ 条带物理高 ⇒ 行内取窗
        piece = np.ascontiguousarray(tile[yoff:yoff + ph, xoff:xoff + w])
        if piece.shape[1] < w:
            piece = np.pad(piece, ((0, 0), (0, w - piece.shape[1])), mode="wrap")
        ramp_n = min(f_px, ph // 2)
        wgt = np.ones((ph, w), np.float32)
        ramp = np.linspace(0.0, 1.0, ramp_n, dtype=np.float32)
        wgt[:ramp_n] *= ramp[:, None]
        wgt[-ramp_n:] *= ramp[::-1][:, None]
        out[y:y1] += piece * wgt
        wsum[y:y1] += wgt
        y = y1 - ramp_n if y1 < h else h
    return out / np.maximum(wsum, 1e-6)


# ══════════════════════════════════════════════════════════════════════════════════════
# 无重复性读数（判据②）
# ══════════════════════════════════════════════════════════════════════════════════════
def repeat_readings(lumf: np.ndarray, mm_per_px: float, min_lag_mm: float = 3.0,
                    far_lag_mm: float = 20.0) -> dict:
    a = lumf.astype(np.float64)
    a -= a.mean()
    F = np.fft.rfft2(a)
    ac = np.fft.irfft2(np.abs(F) ** 2, s=a.shape)
    ac /= ac[0, 0]
    h, w = a.shape
    minlag = int(round(min_lag_mm / mm_per_px))
    farlag = int(round(far_lag_mm / mm_per_px))

    def peaks_1d(prof: np.ndarray, lag0: int, topn: int = 5) -> list[dict]:
        seg = prof[lag0:]
        pk = [(float(seg[i]), lag0 + i) for i in range(1, seg.size - 1)
              if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] > 0]
        pk.sort(reverse=True)
        return [{"lag_mm": round(l * mm_per_px, 2), "ac": round(v, 5)} for v, l in pk[:topn]]

    acx, acy = ac[0, :w // 2], ac[:h // 2, 0]
    farlag_eff = min(farlag, max(1, w // 4), max(1, h // 4))     # 小场兜底（探针/窗口用）
    farx, fary = acx[farlag_eff:], acy[farlag_eff:]
    if farx.max() >= fary.max():
        far_val, far_lag, far_ax = float(farx.max()), farlag + int(np.argmax(farx)), "x"
    else:
        far_val, far_lag, far_ax = float(fary.max()), farlag + int(np.argmax(fary)), "y"
    return {"method": "整页 600dpi 场 2D 自相关（FFT，ac[0,0]=1）；x/y 各取 1D 剖面找峰",
            "min_lag_mm": min_lag_mm, "far_lag_mm": far_lag_mm,
            "peaks_x": peaks_1d(acx, minlag), "peaks_y": peaks_1d(acy, minlag),
            "max_ac_beyond_20mm": round(far_val, 5),
            "max_ac_beyond_20mm_lag_mm": round(far_lag * mm_per_px, 2),
            "max_ac_beyond_20mm_axis": far_ax,
            "ac_at_far_edge_x": round(float(acx[-1]), 5),
            "ac_at_far_edge_y": round(float(acy[-1]), 5)}


def dual_dpi_readings(d12: np.ndarray, d24: np.ndarray, d24d: np.ndarray, dpi_a: int = 1200) -> dict:
    """判据④：1200 vs 2400（2400→1200 INTER_AREA 下采样）同口径比，rel_diff ≈ 0。"""
    mma = MM_PER_IN / dpi_a
    ra, rb = texture_readings(lum(d12), mma), texture_readings(lum(d24d), mma)
    rel = {k: round(abs(ra[k] - rb[k]) / max(abs(ra[k]), 1e-9), 5)
           for k in ("lum_std", "half_decay_x_mm", "half_decay_y_mm")}
    rel_band = {k: round(abs(ra["band_rms_0_255"][k] - rb["band_rms_0_255"][k]) /
                         max(abs(ra["band_rms_0_255"][k]), 1e-9), 5) for k in BAND_NAMES}
    return {"a_1200dpi": ra, "b_2400dpi_downsampled": rb, "rel_diff": rel,
            "rel_diff_band_rms": rel_band,
            "max_rel_diff": round(max(list(rel.values()) + list(rel_band.values())), 5)}


# ══════════════════════════════════════════════════════════════════════════════════════
# 样张落盘
# ══════════════════════════════════════════════════════════════════════════════════════
def to_u8(rgbf: np.ndarray) -> np.ndarray:
    return np.clip(np.round(rgbf), 0, 255).astype(np.uint8)


def save_png(arr_u8: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr_u8).save(path, compress_level=6)


def longest_clean_rect(pool: np.ndarray) -> tuple[int, int, int, int]:
    """池内最长全净水平带（对比板用豆包裁块）。"""
    best = (0, 0, 0, 0)                                   # x, y, w, h
    rowfill = pool.mean(axis=1)
    good = rowfill >= 0.95
    y = 0
    H, W = pool.shape
    while y < H:
        if good[y]:
            y1 = y
            while y1 < H and good[y1]:
                y1 += 1
            xs = np.where(pool[y:y1].all(axis=0))[0]
            if xs.size:
                runs, s = [], int(xs[0])
                for i in range(xs.size):
                    if i + 1 == xs.size or xs[i + 1] != xs[i] + 1:
                        runs.append((s, int(xs[i]) + 1))
                        s = int(xs[i + 1]) if i + 1 < xs.size else s
                for (x0, x1) in runs:
                    if (x1 - x0) * (y1 - y) > best[2] * best[3]:
                        best = (x0, y, x1 - x0, y1 - y)
            y = y1
        else:
            y += 1
    return best



def save_version_files(tag: str, slug: str, win1200: np.ndarray, page600: np.ndarray,
                       rgb: np.ndarray, pool: np.ndarray, ref: dict,
                       d24: np.ndarray | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    p1200 = OUT_DIR / f"{tag}-{slug}-1200dpi-1to1-{int(WIN_W_MM)}x{int(WIN_H_MM)}mm.png"
    save_png(to_u8(win1200), p1200)
    out["window_1200dpi"] = str(p1200)
    w6, h6 = mm2px(WIN_W_MM, PAGE_DPI), mm2px(WIN_H_MM, PAGE_DPI)
    win600 = cv2.resize(win1200, (w6, h6), interpolation=cv2.INTER_AREA)
    p600 = OUT_DIR / f"{tag}-{slug}-600dpi-1to1-{int(WIN_W_MM)}x{int(WIN_H_MM)}mm.png"
    save_png(to_u8(win600), p600)
    out["window_600dpi"] = str(p600)
    Hp, Wp = page600.shape[:2]
    thumb = cv2.resize(page600, (800, int(round(Hp * 800 / Wp))), interpolation=cv2.INTER_AREA)
    pthumb = OUT_DIR / f"{tag}-{slug}-page600dpi-thumb800px.png"
    save_png(to_u8(thumb), pthumb)
    out["page_thumb_800px"] = str(pthumb)
    if d24 is not None:                                   # 双 dpi 对齐窗的 2400dpi 1:1 件
        w2, h2 = mm2px(DDPI_MM[0], 1200), mm2px(DDPI_MM[1], 1200)
        w4, h4 = mm2px(DDPI_MM[0], 2400), mm2px(DDPI_MM[1], 2400)
        p24 = OUT_DIR / f"{tag}-{slug}-2400dpi-1to1-{int(DDPI_MM[0])}x{int(DDPI_MM[1])}mm.png"
        save_png(to_u8(cv2.resize(d24, (w4, h4), interpolation=cv2.INTER_NEAREST)), p24)
        out["window_2400dpi_dualdpi"] = str(p24)
        p12d = OUT_DIR / f"{tag}-{slug}-1200dpi-1to1-{int(DDPI_MM[0])}x{int(DDPI_MM[1])}mm-dualdpi.png"
        save_png(to_u8(cv2.resize(d24, (w2, h2), interpolation=cv2.INTER_AREA)), p12d)
        out["window_1200dpi_dualdpi_downsampled"] = str(p12d)
    rect = longest_clean_rect(pool)
    src_mm = ma.MM_PER_PX
    for dpi_show in (600, 1200):
        x, y, w, h = rect
        ref_crop = rgb[y:y + h, x:x + w]
        px_per_mm = dpi_show / MM_PER_IN
        rw = max(2, int(round(w * src_mm * px_per_mm)))
        rh = max(2, int(round(h * src_mm * px_per_mm)))
        ref_r = cv2.resize(ref_crop, (rw, rh),
                           interpolation=cv2.INTER_AREA if rw <= w else cv2.INTER_CUBIC)
        syn_r = cv2.resize(page600 if dpi_show == PAGE_DPI else win1200, (rw, rh),
                           interpolation=cv2.INTER_AREA)
        cw, ch = min(rw, syn_r.shape[1]), min(rh, syn_r.shape[0])
        gap = 12
        board = np.full((ch, rw * 2 + gap, 3), 24, np.float32)
        board[:, :rw] = ref_r[:ch, :cw].astype(np.float32)
        board[:, rw + gap:] = syn_r[:ch, :cw].astype(np.float32)
        pb = OUT_DIR / f"{tag}-{slug}-vs-doubao-{dpi_show}dpi-1to1.png"
        save_png(to_u8(board), pb)
        out[f"vs_doubao_{dpi_show}dpi"] = str(pb)
    return out


def all_versions_board(ref: dict, pages: dict[str, np.ndarray], rgb: np.ndarray,
                       pool: np.ndarray) -> str:
    """四行并排总板：豆包｜R2｜R1｜R3（600dpi 1:1，同 mm 净带裁块；R 版取 WIN0 锚点窗）。"""
    rect = longest_clean_rect(pool)
    x, y, w, h = rect
    rows: list[tuple[str, np.ndarray, bool]] = [("doubao-ref", rgb[y:y + h, x:x + w].astype(np.float32), True)]
    x0p = mm2px(WIN0_MM[0], PAGE_DPI)
    y0p = mm2px(WIN0_MM[1], PAGE_DPI)
    for tag, page in pages.items():
        rows.append((tag, page[y0p:y0p + h * 2, x0p:x0p + w * 2].astype(np.float32), False))
    px_per_mm = PAGE_DPI / MM_PER_IN
    rw = max(2, int(round(w * ma.MM_PER_PX * px_per_mm)))
    rh = max(2, int(round(h * ma.MM_PER_PX * px_per_mm)))
    gap = 10
    board = np.full((rh * len(rows) + gap * (len(rows) - 1), rw, 3), 24, np.float32)
    yy = 0
    for _, img, _is_ref in rows:
        crop = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_AREA)
        board[yy:yy + rh, :rw] = crop
        yy += rh + gap
    f = OUT_DIR / "all-versions-vs-doubao-600dpi-1to1.png"
    save_png(to_u8(board), f)
    return str(f)


# ══════════════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t_all = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(ma.SRC))[..., :3].astype(np.uint8).copy()
    mk = ma.build_masks(rgb)
    pool = mk["pool"]
    print(f"[load] {rgb.shape[1]}×{rgb.shape[0]} pool={int(pool.sum())}px", flush=True)

    ref = reference_readings(rgb, pool)
    ad = ref["half_decay_y_mm"] / max(ref["half_decay_x_mm"], 1e-9)
    ref["anisotropy_y_over_x"] = round(ad, 3)
    print(f"[ref] {ref['n_patches']} patches rms={ref['texture_rms_0_255']} "
          f"band={ref['band_rms_0_255']} peak={ref['peak_wavelength_mm']} "
          f"ac=({ref['half_decay_x_mm']},{ref['half_decay_y_mm']})mm aniso={ad:.2f} "
          f"σ={ref['per_channel_residual_sigma']} ρ={ref['interchannel_corr_mean']}", flush=True)

    files: dict[str, dict[str, str]] = {}
    versions: dict[str, dict] = {}
    pages: dict[str, np.ndarray] = {}

    # ═══ R1 ═══════════════════════════════════════════════════════════════════════
    model1 = octave_model(ref)
    calib1 = calibrate_octaves(600, [dict(o) for o in model1])
    print(f"[R1] calib={calib1['factors']} joint={calib1['joint_band_rms_after']}", flush=True)
    w1, h1 = mm2px(WIN_W_MM, 1200), mm2px(WIN_H_MM, 1200)
    f1a = render_field(h1, w1, 1200, ref, model1, calib1)
    f1b = render_field(h1, w1, 1200, ref, model1, calib1)
    det1 = bool(hashlib.sha256(f1a.tobytes()).hexdigest() ==
                hashlib.sha256(f1b.tobytes()).hexdigest())
    Wp, Hp = mm2px(PAGE_W_MM, PAGE_DPI), mm2px(PAGE_H_MM, PAGE_DPI)
    page1 = render_field(Hp, Wp, PAGE_DPI, ref, model1, calib1)
    pages["R1"] = page1
    w2, h2 = mm2px(DDPI_MM[0], 1200), mm2px(DDPI_MM[1], 1200)
    w4, h4 = mm2px(DDPI_MM[0], 2400), mm2px(DDPI_MM[1], 2400)
    d12 = render_field(h2, w2, 1200, ref, model1, calib1)
    d14 = render_field(h4, w4, 2400, ref, model1, calib1)
    d14d = cv2.resize(d14, (w2, h2), interpolation=cv2.INTER_AREA)
    tex1 = texture_readings(lum(f1a), MM_PER_IN / 1200)
    versions["R1"] = {
        "name": "R1 频谱匹配合成",
        "method": "mm 带 octave（r2.vnoise_mm 位置哈希，跨 dpi 同一场）＋逐 octave 隔离幅度标定（12mm 试验片）",
        "octaves": model1, "calibration": calib1,
        "texture_readings_1200dpi": tex1,
        "vs_doubao": vs_reference(tex1, ref),
        "determinism_same_seed_bits_equal": det1,
        "dual_dpi": dual_dpi_readings(d12, d14, d14d),
        "repeat_page600": repeat_readings(lum(page1), MM_PER_IN / PAGE_DPI),
    }
    files["R1"] = save_version_files("R1", "spectral", f1a, page1, rgb, pool, ref, d24=d14)
    print(f"[R1] done tex_l1={versions['R1']['vs_doubao']['band_energy_share_L1']} "
          f"det={det1} maxrel={versions['R1']['dual_dpi']['max_rel_diff']}", flush=True)

    # ═══ R2 ═══════════════════════════════════════════════════════════════════════
    mat600, pool600 = material_at_dpi(rgb, pool, PAGE_DPI)
    wins600 = patch_pool(mat600, pool600, mm2px(PATCH_MM, PAGE_DPI))
    mat12, _pool12 = material_at_dpi(rgb, pool, 1200)
    wins12 = patch_pool(mat12, _pool12, mm2px(PATCH_MM, 1200))
    mat24, _pool24 = material_at_dpi(rgb, pool, 2400)
    wins24 = patch_pool(mat24, _pool24, mm2px(PATCH_MM, 2400))
    print(f"[R2] patch pool: 600dpi={len(wins600)} 1200dpi={len(wins12)} 2400dpi={len(wins24)}", flush=True)
    page2 = quilt(Hp, Wp, PAGE_DPI, mat600, wins600, base_rgb=ref["paper_base_rgb"], progress=True)
    pages["R2"] = page2
    f2a = quilt(h1, w1, 1200, mat12, wins12, base_rgb=ref["paper_base_rgb"])
    f2b = quilt(h1, w1, 1200, mat12, wins12, base_rgb=ref["paper_base_rgb"])
    det2 = bool(hashlib.sha256(f2a.tobytes()).hexdigest() ==
                hashlib.sha256(f2b.tobytes()).hexdigest())
    d22 = quilt(h2, w2, 1200, mat12, wins12, base_rgb=ref["paper_base_rgb"])
    d24 = quilt(h4, w4, 2400, mat24, wins24, base_rgb=ref["paper_base_rgb"])
    d24d = cv2.resize(d24, (w2, h2), interpolation=cv2.INTER_AREA)
    tex2 = texture_readings(lum(f2a), MM_PER_IN / 1200)
    versions["R2"] = {
        "name": "R2 patch quilting",
        "method": f"{PATCH_MM}mm patch 最小误差边界（重叠 {OVERLAP_MM}mm SSD＋top{TOPK} 随机）＋羽化＋"
                  f"全局基色对齐＋抖动网格（步长 0.62–0.95×格距，散格距周期峰）；"
                  f"镜像变体（×3 池）实测更差（远距 ac 0.64 vs 0.37）已弃",
        "patch_pool": {"600dpi": len(wins600), "1200dpi": len(wins12), "2400dpi": len(wins24)},
        "patch_mm": PATCH_MM, "overlap_mm": OVERLAP_MM,
        "texture_readings_1200dpi": tex2,
        "vs_doubao": vs_reference(tex2, ref),
        "determinism_same_seed_bits_equal": det2,
        "dual_dpi": dual_dpi_readings(d22, d24, d24d),
        "repeat_page600": repeat_readings(lum(page2), MM_PER_IN / PAGE_DPI),
    }
    files["R2"] = save_version_files("R2", "patch-quilt", f2a, page2, rgb, pool, ref, d24=d24)
    print(f"[R2] done peaks_x={versions['R2']['repeat_page600']['peaks_x'][:2]} det={det2}", flush=True)

    # ═══ R3 ═══════════════════════════════════════════════════════════════════════
    strips = cloud_strips(rgb, pool)
    print(f"[R3] strips={len(strips)} mm="
          f"{[[round(s['band'].shape[1]*ma.MM_PER_PX,1), round(s['band'].shape[0]*ma.MM_PER_PX,1)] for s in strips]}",
          flush=True)
    model3 = octave_model(ref, bands=("coarse", "fine", "grain"))
    calib3 = calibrate_octaves(600, [dict(o) for o in model3])
    low600 = r3_low_field(Hp, Wp, PAGE_DPI, strips)
    tgt = float(ref["band_rms_0_255"]["cloud"])
    meas = float(np.std(low600[Hp // 4: 3 * Hp // 4, Wp // 4: 3 * Wp // 4]))
    n_g = mm2px(12.0, PAGE_DPI)
    sl_g = float(r1_lum(np.arange(n_g, dtype=np.int64), np.arange(n_g, dtype=np.int64),
                        PAGE_DPI, model3, calib3["factors"]).std())
    s_lum = float(np.dot((0.299, 0.587, 0.114),
                         np.asarray(ref["per_channel_residual_sigma"], np.float64)))
    # render_field 里低频按 sig/sl 进各通道 ⇒ 亮度增益＝Σwσ/sl；增益预补偿使终图云斑带 RMS＝tgt
    low_gain = round(tgt * sl_g / max(meas * s_lum, 1e-9), 6)
    low600 *= np.float32(low_gain)
    page3 = render_field(Hp, Wp, PAGE_DPI, ref, model3, calib3, low_field=low600, low_gain=1.0)
    pages["R3"] = page3
    low12 = r3_low_field(h1, w1, 1200, strips) * np.float32(low_gain)
    f3a = render_field(h1, w1, 1200, ref, model3, calib3, low_field=low12, low_gain=1.0)
    low12b = r3_low_field(h1, w1, 1200, strips) * np.float32(low_gain)
    f3b = render_field(h1, w1, 1200, ref, model3, calib3, low_field=low12b, low_gain=1.0)
    det3 = bool(hashlib.sha256(f3a.tobytes()).hexdigest() ==
                hashlib.sha256(f3b.tobytes()).hexdigest())
    low_a = r3_low_field(h2, w2, 1200, strips) * np.float32(low_gain)
    low_b = r3_low_field(h4, w4, 2400, strips) * np.float32(low_gain)
    d32 = render_field(h2, w2, 1200, ref, model3, calib3, low_field=low_a, low_gain=1.0)
    d34 = render_field(h4, w4, 2400, ref, model3, calib3, low_field=low_b, low_gain=1.0)
    d34d = cv2.resize(d34, (w2, h2), interpolation=cv2.INTER_AREA)
    tex3 = texture_readings(lum(f3a), MM_PER_IN / 1200)
    versions["R3"] = {
        "name": "R3 混合",
        "method": "低频（云斑 1.35–3mm）＝豆包条带（池内 4.5mm 高）行高 3.5–6.5mm 抖动拼铺＋1.5mm 羽化；"
                  "高频（≤1.35mm）＝R1 机制",
        "cloud_strips": [{"kind": s["kind"], "bbox_px": s["bbox_px"],
                          "mm": [round(s["band"].shape[1] * ma.MM_PER_PX, 2),
                                 round(s["band"].shape[0] * ma.MM_PER_PX, 2)]} for s in strips],
        "low_gain_calibration": {"target_cloud_rms": tgt, "measured_tiled_rms": round(meas, 4),
                                 "gain": low_gain, "sl_high_field_600": round(sl_g, 4),
                                 "sigma_lum": round(s_lum, 4),
                                 "rule": "gain＝tgt·sl/(meas·Σwσ)：render_field 低频按 sig/sl 进通道，"
                                         "亮度增益 Σwσ/sl 预补偿 ⇒ 终图云斑带 RMS＝tgt"},
        "texture_readings_1200dpi": tex3,
        "vs_doubao": vs_reference(tex3, ref),
        "determinism_same_seed_bits_equal": det3,
        "dual_dpi": dual_dpi_readings(d32, d34, d34d),
        "repeat_page600": repeat_readings(lum(page3), MM_PER_IN / PAGE_DPI),
    }
    files["R3"] = save_version_files("R3", "hybrid", f3a, page3, rgb, pool, ref, d24=d34)
    print(f"[R3] done peaks_y={versions['R3']['repeat_page600']['peaks_y'][:2]} det={det3}", flush=True)

    board_all = all_versions_board(ref, pages, rgb, pool)

    doc = {
        "schema": "feicui.texture-mimic-round4.v1",
        "generator": "ops/variant-samples/round4_texture_mimic.py",
        "seed": SEED,
        "scale_rule": "mm 物理定义×输出 dpi 换算 px；r2.vnoise_mm 位置哈希（跨 dpi 同一场）",
        "windows": {"show_mm": [WIN_W_MM, WIN_H_MM], "show_origin_mm": list(WIN0_MM),
                    "dual_dpi_mm": list(DDPI_MM), "page_dpi": PAGE_DPI,
                    "page_mm": [round(PAGE_W_MM, 1), round(PAGE_H_MM, 1)],
                    "note": "样张窗口为纯纸场（不含印文/文字；本单只做纸纹理），窗口锚点任取"},
        "material_adequacy": json.loads((Path(__file__).parent /
                                         "readings-round4-material-adequacy.json").read_text()),
        "reference_doubao": ref,
        "versions": versions,
        "files": files,
        "board_all": board_all,
        "wall_seconds": round(time.time() - t_all, 1),
    }
    READINGS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[out] {READINGS}", flush=True)
    print(f"[done] {time.time()-t_all:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
