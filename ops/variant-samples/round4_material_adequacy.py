#!/usr/bin/env python
"""① 素材充足性评估（Kong · ops/variant-samples/round4_material_adequacy.py）。

问题：豆包参照图（1536×1536，只读）的**纸底**够不够生成 8500×12236（1200dpi 整页）的
示例纹理合成（exemplar-based）产物而不出现可见重复？

本脚本只做**量化盘点**，不做合成：
1. 纸底掩膜：排除印泥（`colorcal.ink_mask`）∧ 排除深色（文字/水印/暗角）∧ 排除晕染带
   （到印泥距离 < 0.4mm）∧ 排除外框 6px；
2. patch 盘点：池内可完整落下的正方形 patch（按边长分档）数量与总面积 → 可拼贴素材面；
3. 纹理单元：云斑/粗纤维带的峰波长（mm）；独立单元数 = 有效面积 / 单元面积²；
4. 需要多少独立素材：目标页面积 / 单元面积²；**重复倍数 R ＝ 页面积 / 有效面积**（与尺度无关）；
5. 明暗梯度（照明不匀）与逐条带均匀性：素材内部是否平稳（可当一张平稳纹理用）。

尺度口径（硬纪律，沿用 `doubao_reference.py`）：共同标尺＝印面宽 W_d=923px，
`mm_per_px = 22.437 / 923`（明示假设：豆包印面实物宽 = C1-R1 的 22.437mm）。
证据件：`readings-round4-material-adequacy.json`。

跑法：cd /Users/kevin/bistro/feicui && ./venv/bin/python ops/variant-samples/round4_material_adequacy.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))
from app import colorcal as cc                                     # noqa: E402  印泥掩膜单一真源

SRC = Path("/Users/kevin/Library/Application Support/Hermes/composer-images/image_673b34.png")
OUT = Path(__file__).resolve().parent / "readings-round4-material-adequacy.json"

W_D_PX = 923                                    # 印面宽（doubao_reference.py ruler.W_d_px）
W_O_MM = 22.437                                 # C1-R1 印面实物宽（我们 2400dpi 侧 2120px）
MM_PER_PX = W_O_MM / W_D_PX                     # 0.02430878 mm/px（豆包图等效 1044.9 dpi）
TARGET_W_PX, TARGET_H_PX, TARGET_DPI = 8500, 12236, 1200
PAGE_W_MM = TARGET_W_PX / TARGET_DPI * 25.4
PAGE_H_MM = TARGET_H_PX / TARGET_DPI * 25.4
BORDER_TRIM_PX = 6                              # 外框/暗角：一律排除
DARK_V = 0.75                                   # V < 0.75 且非印泥 ⇒ 文字/水印/暗角
HALO_DIST_MM = 0.4                              # 到印泥距离 < 0.4mm ⇒ 晕染带（豆包晕宽 0.0985mm+余量）
BLEED_MAX = 12.0                                # redness = R − 0.5(G+B) 超过 ⇒ 溅红/渗色像素
MIN_BLOCK_MM = 3.0                              # 可用 patch 最小边长（mm）
PATCH_GRID_MM = (3.0, 4.0, 5.0, 6.0)            # patch 边长分档
# 频带（mm，波长）——与 doubao_reference.BAND_FRAC × W_d 完全一致
BANDS_MM = {"cloud": (1.3463, 3.0), "coarse": (0.4487, 1.3463),
            "fine": (0.1346, 0.4487), "grain": (0.0449, 0.1346)}
SEED = 20261016


def lum(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    return f[..., 0] * np.float32(0.299) + f[..., 1] * np.float32(0.587) + f[..., 2] * np.float32(0.114)


def band_rms(res: np.ndarray, lo_mm: float, hi_mm: float, mm_per_px: float) -> float:
    """带通（波长 [lo_mm, hi_mm]）后 RMS（0–255 标度）。DoG：G(hi) − G(lo)（σ=λ/2π）。"""
    lo_px, hi_px = lo_mm / mm_per_px, hi_mm / mm_per_px
    return float((cv2.GaussianBlur(res, (0, 0), hi_px / (2 * np.pi)) -
                  cv2.GaussianBlur(res, (0, 0), lo_px / (2 * np.pi))).std())


def radial_psd_mm(res: np.ndarray, mm_per_px: float, nb: int = 200) -> dict:
    """径向功率谱，横轴一律 **cyc/mm**（跨 dpi 可比）。"""
    a = res.astype(np.float64)
    a -= a.mean()
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.rfft2(a * win)) ** 2
    fy = np.fft.fftfreq(h, d=mm_per_px)
    fx = np.fft.rfftfreq(w, d=mm_per_px)
    FY, FX = np.meshgrid(fy, fx, indexing="ij")
    fr = np.sqrt(FY ** 2 + FX ** 2)
    edges = np.linspace(0.0, float(fr.max()), nb + 1)
    idx = np.clip(np.digitize(fr.ravel(), edges) - 1, 0, nb - 1)
    psum = np.bincount(idx, weights=P.ravel(), minlength=nb)
    cnt = np.bincount(idx, minlength=nb)
    fcen = 0.5 * (edges[:-1] + edges[1:])
    psd = psum / np.maximum(cnt, 1)
    return {"f_cyc_per_mm": fcen.tolist(), "psd": psd.tolist(), "count": cnt.tolist()}


def band_energy_share(fc: np.ndarray, psd: np.ndarray, cnt: np.ndarray) -> dict:
    """按 BANDS_MM（波长 → 频率区间 [1/hi, 1/lo] cyc/mm）给能量占比与峰值波长（mm）。"""
    tot = float(psd[cnt > 0].sum())
    out = {}
    for name, (lo, hi) in BANDS_MM.items():
        f_lo, f_hi = 1.0 / hi, 1.0 / lo
        sel = (fc >= f_lo) & (fc <= f_hi) & (cnt > 0)
        if sel.any() and tot > 0:
            pk = float(fc[sel][int(np.argmax(psd[sel]))])
            out[name] = {"wavelength_mm_range": [lo, hi],
                         "energy_share": round(float(psd[sel].sum() / tot), 6),
                         "peak_wavelength_mm": round(1.0 / pk, 4)}
        else:
            out[name] = None
    return out


def ac_profile_x(res: np.ndarray, max_lag_px: int) -> np.ndarray:
    """1D 自相关（x 方向，滞后 0..max_lag），归一化 ac[0]=1。"""
    a = res.astype(np.float64)
    a -= a.mean()
    c = np.fft.irfft(np.abs(np.fft.rfft(a, axis=1)) ** 2, axis=1).mean(axis=0)
    return c[:max_lag_px + 1] / c[0]


def half_decay(prof: np.ndarray) -> float:
    below = np.where(prof < 0.5)[0]
    if below.size == 0:
        return float(len(prof))
    i = int(below[0])
    if i == 0:
        return 0.0
    x0, x1 = float(prof[i - 1]), float(prof[i])
    frac = (x0 - 0.5) / (x0 - x1) if x0 != x1 else 0.0
    return (i - 1) + float(np.clip(frac, 0.0, 1.0))


def build_masks(rgb: np.ndarray) -> dict:
    """印泥/暗部/渗红/纸底池掩膜（①②共用单源；规则与阈值见模块常量）。"""
    ink = cc.ink_mask(rgb.astype(np.float64))
    v = rgb.max(axis=2).astype(np.float32) / 255.0
    redness = rgb[..., 0].astype(np.float32) - 0.5 * (rgb[..., 1].astype(np.float32) +
                                                      rgb[..., 2].astype(np.float32))
    dist_ink = cv2.distanceTransform((~ink.astype(bool)).astype(np.uint8), cv2.DIST_L2, 3)
    dark = (~ink) & (v < DARK_V)
    inner = np.zeros(rgb.shape[:2], bool)
    H, W = rgb.shape[:2]
    inner[BORDER_TRIM_PX:H - BORDER_TRIM_PX, BORDER_TRIM_PX:W - BORDER_TRIM_PX] = True
    bleed = redness > BLEED_MAX
    pool = inner & (~ink) & (~dark) & (~bleed) & (dist_ink >= HALO_DIST_MM / MM_PER_PX)
    return {"ink": ink, "dark": dark, "bleed": bleed, "pool": pool,
            "redness": redness, "dist_ink": dist_ink, "v": v}


def main() -> int:
    assert SRC.is_file(), SRC
    raw = SRC.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rgb = np.asarray(Image.open(SRC))[..., :3].astype(np.uint8).copy()
    H, W = rgb.shape[:2]
    print(f"[load] {W}×{H} sha256={sha[:16]}… mm_per_px={MM_PER_PX:.8f} (等效 {1/MM_PER_PX*25.4:.1f} dpi)")
    print(f"[page] 目标 1200dpi {TARGET_W_PX}×{TARGET_H_PX} = {PAGE_W_MM:.1f}×{PAGE_H_MM:.1f} mm "
          f"= {PAGE_W_MM*PAGE_H_MM:.0f} mm²")

    mk = build_masks(rgb)
    ink, dark, bleed, pool, redness, v = (mk["ink"], mk["dark"], mk["bleed"], mk["pool"],
                                          mk["redness"], mk["v"])
    dist_ink = mk["dist_ink"]
    print(f"[mask] ink={int(ink.sum())} dark={int(dark.sum())} bleed={int(bleed.sum())} "
          f"pool={int(pool.sum())} ({pool.mean()*100:.1f}%) = {pool.sum()*MM_PER_PX**2:.1f} mm²")

    # ── 连通块盘点 ──────────────────────────────────────────────────────────────────
    nb_lab, lab, st, _ = cv2.connectedComponentsWithStats(pool.astype(np.uint8), 8)
    min_side_px = int(round(MIN_BLOCK_MM / MM_PER_PX))
    comps = []
    for i in range(1, nb_lab):
        x, y, w, h, area = (int(t) for t in st[i])
        if w >= min_side_px and h >= min_side_px and area >= min_side_px ** 2:
            comps.append({"label": i, "bbox_px": [x, y, w, h], "area_px": area,
                          "bbox_mm": [round(w * MM_PER_PX, 2), round(h * MM_PER_PX, 2)]})
    comps.sort(key=lambda c: -c["area_px"])
    print(f"[components] ≥{MIN_BLOCK_MM}mm 连通块 = {len(comps)}")

    # ── patch 盘点：池内可完整落下的正方形 patch（两口径：重叠网格/不重叠网格）──────
    patch_inventory = {}
    for pmm in PATCH_GRID_MM:
        p = int(round(pmm / MM_PER_PX))
        counts = {}
        for tag, st_ in (("grid_half_overlap", max(p // 2, 1)), ("disjoint", p)):
            n_ok, sum_area = 0, 0
            for oy in range(0, H - p + 1, st_):
                for ox in range(0, W - p + 1, st_):
                    if pool[oy:oy + p, ox:ox + p].all():
                        n_ok += 1
                        sum_area += p * p
            counts[tag] = {"n_patches": n_ok, "total_area_px": int(sum_area),
                           "total_area_mm2": round(sum_area * MM_PER_PX ** 2, 1)}
        patch_inventory[f"{pmm:g}mm"] = {"side_px": p, **counts}
        print(f"[patch {pmm}mm] 重叠网格 {counts['grid_half_overlap']['n_patches']} 位 / "
              f"不重叠 {counts['disjoint']['n_patches']} 块"
              f"（不重叠合计 {counts['disjoint']['total_area_mm2']} mm²）")

    # ── 纹理读数：取「有 patch 的最大档」内若干位置 ────────────────────────────────
    tier = None
    for pmm in sorted(PATCH_GRID_MM, reverse=True):
        if patch_inventory[f"{pmm:g}mm"]["disjoint"]["n_patches"] >= 4:
            tier = pmm
            break
    p = int(round(tier / MM_PER_PX))
    spots = [(ox, oy) for oy in range(0, H - p + 1, p) for ox in range(0, W - p + 1, p)
             if pool[oy:oy + p, ox:ox + p].all()]
    per_patch = []
    for k, (ox, oy) in enumerate(spots[:12]):
        sub = rgb[oy:oy + p, ox:ox + p]
        res = lum(sub) - float(lum(sub).mean())
        rp = radial_psd_mm(res, MM_PER_PX)
        fc, psd, cnt = np.array(rp["f_cyc_per_mm"]), np.array(rp["psd"]), np.array(rp["count"])
        shares = band_energy_share(fc, psd, cnt)
        brms = {k2: round(band_rms(res, lo, hi, MM_PER_PX), 4) for k2, (lo, hi) in BANDS_MM.items()}
        acx = ac_profile_x(res, int(round(1.5 / MM_PER_PX)))
        per_patch.append({"origin_px": [int(ox), int(oy)], "side_mm": tier,
                          "lum_std": round(float(res.std()), 4), "band_rms": brms,
                          "half_decay_mm": round(half_decay(acx) * MM_PER_PX, 4),
                          "peak_wavelength_mm": {k2: (v["peak_wavelength_mm"] if v else None)
                                                 for k2, v in shares.items()},
                          "energy_share": {k2: (v["energy_share"] if v else None)
                                           for k2, v in shares.items()}})
    # 合并读数（中位）
    def med(key):
        vals = [pp_[key] for pp_ in per_patch if pp_[key] is not None]
        return round(float(np.median(vals)), 4) if vals else None
    all_brms = {k2: round(float(np.median([pp_["band_rms"][k2] for pp_ in per_patch])), 4)
                for k2 in BANDS_MM}
    all_peaks = {k2: (None if all(pp_["peak_wavelength_mm"][k2] is None for pp_ in per_patch)
                      else round(float(np.median([pp_["peak_wavelength_mm"][k2] for pp_ in per_patch
                                                  if pp_["peak_wavelength_mm"][k2] is not None])), 4))
                 for k2 in BANDS_MM}
    all_shares = {k2: (None if all(pp_["energy_share"][k2] is None for pp_ in per_patch)
                       else round(float(np.median([pp_["energy_share"][k2] for pp_ in per_patch
                                                   if pp_["energy_share"][k2] is not None])), 6))
                  for k2 in BANDS_MM}
    print(f"[texture] {len(per_patch)} patches @{tier}mm：std={med('lum_std')} "
          f"half_decay={med('half_decay_mm')}mm band_rms={all_brms}")
    print(f"[texture] 峰波长(mm)={all_peaks}")
    print(f"[texture] 能量占比={all_shares}")

    # ── 照明梯度（防泄漏口径：非池像素先填充为池均值，再低通；池内缩 3mm 后取值）──
    lum_full = lum(rgb).astype(np.float32)
    filled = lum_full.copy()
    filled[~pool] = float(lum_full[pool].mean())
    lp = cv2.GaussianBlur(filled, (0, 0), 3.0 / MM_PER_PX / (2 * np.pi))
    lp8 = cv2.GaussianBlur(filled, (0, 0), 8.0 / MM_PER_PX / (2 * np.pi))
    deep = cv2.erode(pool.astype(np.uint8), np.ones((3, 3), np.uint8),
                     iterations=int(round(3.0 / MM_PER_PX))).astype(bool)
    grad3 = lp[deep]
    grad8 = lp8[deep]
    grad_stats = {
        "rule": "非池像素填池均值后低通；池内缩 3mm 取值（防印泥暗部泄漏）",
        "lp3mm_p1_p99": round(float(np.percentile(grad3, 99) - np.percentile(grad3, 1)), 3),
        "lp3mm_std": round(float(grad3.std()), 3),
        "lp8mm_p1_p99": round(float(np.percentile(grad8, 99) - np.percentile(grad8, 1)), 3),
        "lp8mm_std": round(float(grad8.std()), 3),
    }
    print(f"[gradient] {grad_stats}")

    # ── 文字/水印定位（dark 像素连通域）────────────────────────────────────────────
    dlab, dstats = [], []
    if dark.any():
        dn, dlab_, dst_, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), 8)
        for i in range(1, dn):
            x, y, w, h, area = (int(t) for t in dst_[i])
            if area >= 8:
                dstats.append({"bbox_px": [x, y, w, h], "area_px": area})
        dstats.sort(key=lambda d: -d["area_px"])
    print(f"[dark] {len(dstats)} 个 ≥8px 暗连通域（前 5）: {dstats[:5]}")

    # ── 均匀性：池的分区（左/上/右/下框带）统计 ────────────────────────────────────
    n_l, labp, stp, _ = cv2.connectedComponentsWithStats(pool.astype(np.uint8), 8)
    zcs = []
    for i in range(1, n_l):
        x, y, w, h, area = (int(t) for t in stp[i])
        if area < 5000:
            continue
        sub_mask = labp == i
        sub = rgb[sub_mask].astype(np.float32)
        zcs.append({"component": i, "bbox_px": [x, y, w, h], "area_px": area,
                    "mean_rgb": [round(float(c), 2) for c in sub.mean(0)],
                    "lum_std": round(float(lum(rgb)[sub_mask].std()), 3),
                    "grad3mm_p1_p99_leakfree": grad_stats["lp3mm_p1_p99"]})
    for z in zcs:
        print(f"[uniform] comp{z['component']} bbox={z['bbox_px']} mean={z['mean_rgb']} "
              f"std={z['lum_std']}")

    # ── 纸色与逐通道 σ ────────────────────────────────────────────────────────────
    pp = rgb[pool].astype(np.float32)
    pmean = [round(float(x), 3) for x in pp.mean(0)]
    pstd = [round(float(x), 4) for x in pp.std(0)]
    print(f"[paper_color] mean={pmean} std={pstd}")

    # ── 充足性判据 ────────────────────────────────────────────────────────────────
    pool_px = int(pool.sum())
    pool_mm2 = pool_px * MM_PER_PX ** 2
    page_mm2 = PAGE_W_MM * PAGE_H_MM
    repeat_factor = page_mm2 / pool_mm2
    unit_mm = all_peaks["coarse"] or 1.22          # 独立纹理单元取粗纤维带峰波长
    cloud_mm = all_peaks["cloud"]
    n_unit_material = pool_mm2 / unit_mm ** 2
    n_unit_page = page_mm2 / unit_mm ** 2
    L_VIS_MM = 10.5                                # 30cm 观读、2° 视角的可辨重复尺度
    n_vis_page = page_mm2 / L_VIS_MM ** 2
    n_vis_material = pool_mm2 / L_VIS_MM ** 2
    biggest_inv = patch_inventory[f"{tier:g}mm"]
    page_patches_needed = int(np.ceil(PAGE_W_MM / tier)) * int(np.ceil(PAGE_H_MM / tier))
    print(f"[verdict-inputs] 纹理读数档 {tier}mm：不重叠 {biggest_inv['disjoint']['n_patches']} 块；"
          f"页需 {page_patches_needed} 块（复用 {page_patches_needed / max(biggest_inv['disjoint']['n_patches'], 1):.0f}×）")
    print(f"\n[verdict-inputs] 有效素材池 {pool_mm2:.1f} mm² / 页 {page_mm2:.0f} mm² ⇒ 平均复用 R={repeat_factor:.1f}×")
    print(f"[verdict-inputs] 独立单元 λ={unit_mm}mm ⇒ 素材 {n_unit_material:.0f} 个 / 页需 {n_unit_page:.0f} 个"
          f"（复用 {n_unit_page/max(n_unit_material,1):.0f}×）")
    print(f"[verdict-inputs] 视觉可辨重复尺度 {L_VIS_MM}mm ⇒ 素材 {n_vis_material:.1f} 个 / 页 {n_vis_page:.0f} 个"
          f"（复用 {n_vis_page/max(n_vis_material,0.01):.0f}×）")

    doc = {
        "schema": "feicui.texture-mimic-round4.adequacy.v1",
        "generator": "ops/variant-samples/round4_material_adequacy.py",
        "role": "① 素材充足性评估（豆包纸底用于 1200dpi 整页示例纹理合成）",
        "source": {"path": str(SRC), "copied_into_repo": False, "size_px": [W, H],
                   "sha256": sha, "read_only": True},
        "scale": {"ruler": "共同标尺＝印面宽 W_d（doubao_reference.py 同源）",
                  "W_d_px": W_D_PX, "W_o_mm": W_O_MM, "mm_per_px": MM_PER_PX,
                  "equiv_dpi": round(1 / MM_PER_PX * 25.4, 1),
                  "equiv_assumption": "假设豆包印面实物宽 ＝ C1-R1 印面 22.437 mm"},
        "target": {"dpi": TARGET_DPI, "px": [TARGET_W_PX, TARGET_H_PX],
                   "mm": [round(PAGE_W_MM, 2), round(PAGE_H_MM, 2)],
                   "area_mm2": round(page_mm2, 1), "mpx": 104.0},
        "masks": {"ink_px": int(ink.sum()), "dark_px": int(dark.sum()),
                  "dark_rule": f"非印泥 ∧ V < {DARK_V}（文字/水印/暗角）",
                  "bleed_rule": "redness = R−0.5(G+B) > 12 ⇒ 溅红/渗色像素剔除",
                  "bleed_px": int(bleed.sum()),
                  "border_trim_px": BORDER_TRIM_PX,
                  "halo_exclusion_mm": HALO_DIST_MM,
                  "halo_rule": "到印泥掩膜距离 ≥ 0.4mm（豆包晕宽 0.0985mm + 余量）",
                  "pool_px": pool_px, "pool_mm2": round(pool_mm2, 1),
                  "pool_fraction_of_image": round(pool.mean(), 4)},
        "components": comps,
        "patch_inventory": patch_inventory,
        "patch_counting": "grid_half_overlap＝步长边长/2（位置数）；disjoint＝步长＝边长（不重叠块数）",
        "illum_gradient": grad_stats,
        "dark_components": dstats[:10],
        "texture": {"patch_side_mm": tier, "n_patches_measured": len(per_patch),
                    "per_patch": per_patch,
                    "lum_std_0_255_median": med("lum_std"),
                    "band_rms_0_255_mm_bands_median": all_brms,
                    "band_shares_median": all_shares,
                    "band_peak_wavelength_mm_median": all_peaks,
                    "half_decay_mm_median": med("half_decay_mm"),
                    "bands_mm": BANDS_MM,
                    "bands_note": "与 doubao_reference.BAND_FRAC×W_d 一致；cloud 上限 3.0mm"
                                  "（素材最大纯纸补丁 ~5.3mm，>3mm 波长不可测，标注测量上限）"},
        "uniformity": {"components": zcs},
        "paper_color": {"mean_rgb": pmean, "std_rgb": pstd},
        "adequacy": {
            "effective_material_mm2": round(pool_mm2, 1),
            "effective_material_px": pool_px,
            "avg_reuse_factor_area_ratio": round(repeat_factor, 2),
            "texture_unit_wavelength_mm": unit_mm,
            "independent_units_material": round(n_unit_material, 1),
            "independent_units_page_needed": round(n_unit_page, 1),
            "reuse_factor_units": round(n_unit_page / max(n_unit_material, 1), 1),
            "visual_repeat_scale_mm": L_VIS_MM,
            "visual_cells_material": round(n_vis_material, 2),
            "visual_cells_page": round(n_vis_page, 1),
            "visual_cells_reuse_factor": round(n_vis_page / max(n_vis_material, 0.01), 1),
            "patch_inventory_biggest": biggest_inv,
            "criteria_note": ("(a) 平均复用 R ＝ 页面积/有效素材面积（与尺度无关）；"
                              "(b) 独立单元数 ＝ 面积/单元λ²；(c) 视觉可辨重复尺度取 10.5mm"
                              "（30cm 观读、2° 视角）"),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[out] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
