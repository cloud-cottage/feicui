#!/usr/bin/env python
"""豆包参照图**定量特征提取**（Kong · ops/variant-samples/doubao_reference.py）。

输入＝Kevin 提供的豆包对话输出版参照图（**只读**，不复制进仓；路径与 sha256 记入证据件）。
输出＝`ops/variant-samples/doubao-reference-features.json`（可入库证据件）。

**共同标尺＝印面宽度**（不依赖任何实物尺寸假设）：豆包图印面宽 `W_d`（px），其纸纹理尺度 `f_d`（px）
⇒ 归一化尺度 `f_d / W_d`。我们的 2400dpi 图印面宽 `W_o`（C1-R1 ＝ 2120 px ↔ 22.437 mm）
⇒ **目标纤维长度 ＝ W_o × (f_d / W_d)**。只有在「豆包印面实物宽 ＝ C1-R1 的 22.437 mm」这一**明示假设**下，
才有 mm 值（本文件把假设写死在 `EQUIV_ASSMP_MM`）。

**对标限制（硬口径）**：豆包图是生成式输出，已确认**重绘了印文**（字形粘连/断裂/变形、笔画粗细不匀、
边缘毛糙）⇒ 只对标它的**纸纹理 / 印泥色彩 / 晕染过渡**三项；**严禁**对标字形与线条锐度
（我们守白字/字形冻结，该项不学）。

跑法：cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/variant-samples/doubao_reference.py
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
from app import colorcal as cc                                     # noqa: E402  靶色/ΔE 单一真源

SRC = Path("/Users/kevin/Library/Application Support/Hermes/composer-images/image_673b34.png")
OUT = Path(__file__).resolve().parent / "doubao-reference-features.json"

# 我们的 2400dpi 标尺（C1-R1 白文大方印）
W_O_PX, W_O_MM = 2120, 22.437
EQUIV_ASSUMP_MM = "假设豆包图印面实物宽 ＝ C1-R1 印面 22.437 mm（仅为把归一化尺度翻译成 mm 的显式假设）"

MM_PER_IN = 25.4
BAND_FRAC = {                       # 频带按**印面宽 W_d 归一化**（共同标尺；不依赖实物尺寸）
    "coarse": (0.020, 0.060),       # 粗纤维/束
    "fine": (0.006, 0.020),         # 细纤维
    "grain": (0.002, 0.006),        # 颗粒
}
PATCH = 300
PATCH_ORIGINS = ((16, 16), (1220, 16), (16, 1220))     # 避开右下角水印


def lum(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    return f[..., 0] * np.float32(0.299) + f[..., 1] * np.float32(0.587) + f[..., 2] * np.float32(0.114)


def _half_decay(prof: np.ndarray) -> float | None:
    below = np.where(prof < 0.5)[0]
    if below.size == 0:
        return None
    i = int(below[0])
    if i == 0:
        return 0.0
    x0, x1 = float(prof[i - 1]), float(prof[i])
    frac = (x0 - 0.5) / (x0 - x1) if x0 != x1 else 0.0
    return (i - 1) + float(np.clip(frac, 0.0, 1.0))


def radial_psd(res: np.ndarray, mm_per_px: float, W_d: int) -> dict:
    """径向功率谱（Hanning 窗）：谱质心 / 峰值波长 / 分带能量与峰值 —— 波长一律 **px**。

    分带按**印面宽 W_d 归一化**给出（`BAND_FRAC`＝波长 / W_d），换算成 px 再取频带成员
    （不依赖实物尺寸假设）。低于 `λ > 0.10·W_d` 的分量（照明不匀/云斑）**不计**，
    避免全局峰值落在最低频格上。
    """
    a = res.astype(np.float64)
    a = a - a.mean()
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.rfft2(a * win)) ** 2
    fy = np.fft.fftfreq(h, d=1.0)
    fx = np.fft.rfftfreq(w, d=1.0)
    FY, FX = np.meshgrid(fy, fx, indexing="ij")
    fr = np.sqrt(FY ** 2 + FX ** 2)
    nb = 160
    fmax = float(fr.max())
    edges = np.linspace(0.0, fmax, nb + 1)
    idx = np.clip(np.digitize(fr.ravel(), edges) - 1, 0, nb - 1)
    psum = np.bincount(idx, weights=P.ravel(), minlength=nb)
    cnt = np.bincount(idx, minlength=nb)
    fcen = 0.5 * (edges[:-1] + edges[1:])
    psd = psum / np.maximum(cnt, 1)
    f_cut = 1.0 / (0.10 * float(W_d))                       # cyc/px：剔除 λ > 0.10·W_d 的低频
    m = (fcen > f_cut) & (cnt > 0)
    out = {"n_bins": nb, "low_freq_cut_wavelength_px": round(0.10 * float(W_d), 3)}
    out["psd_centroid_cyc_per_px"] = (round(float((fcen[m] * psd[m]).sum() / max(psd[m].sum(), 1e-30)), 6)
                                      if m.any() else None)
    out["psd_peak_cyc_per_px"] = (round(float(fcen[m][int(np.argmax(psd[m]))]), 6) if m.any() else None)
    tot = float(psd[m].sum()) if m.any() else 0.0
    out["band"] = {}
    for name, (lo, hi) in BAND_FRAC.items():                # 波长 ＝ [lo·W_d, hi·W_d] px
        lam_lo, lam_hi = lo * float(W_d), hi * float(W_d)
        f_hi, f_lo = 1.0 / lam_lo, 1.0 / lam_hi             # cyc/px
        sel = (fcen >= f_lo) & (fcen <= f_hi) & (cnt > 0)
        if sel.any():
            pk = float(fcen[sel][int(np.argmax(psd[sel]))])
            out["band"][name] = {
                "wavelength_px_range": [round(lam_lo, 2), round(lam_hi, 2)],
                "peak_wavelength_px": round(1.0 / pk, 3),
                "energy_share": round(float(psd[sel].sum() / max(tot, 1e-30)), 5),
            }
        else:
            out["band"][name] = None
    if out["psd_peak_cyc_per_px"]:
        out["psd_peak_wavelength_px"] = round(1.0 / out["psd_peak_cyc_per_px"], 3)
    if out["psd_centroid_cyc_per_px"]:
        out["psd_centroid_wavelength_px"] = round(1.0 / out["psd_centroid_cyc_per_px"], 3)
        out["psd_centroid_cyc_per_mm"] = round(out["psd_centroid_cyc_per_px"] / mm_per_px, 6)
    return out


def bandpass_std(res: np.ndarray, lam_lo_px: float, lam_hi_px: float) -> float:
    """分带（波长区间 [lam_lo, lam_hi] px）滤波后的 RMS（0–255 标度）。"""
    band = cv2.GaussianBlur(res, (0, 0), lam_hi_px / (2.0 * np.pi)) - \
        cv2.GaussianBlur(res, (0, 0), lam_lo_px / (2.0 * np.pi))
    return round(float(band.std()), 4)


def main() -> int:
    assert SRC.is_file(), SRC
    raw = SRC.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    im = Image.open(SRC)
    arr = np.asarray(im)
    rgb = arr[..., :3].astype(np.uint8).copy()
    alpha = arr[..., 3] if arr.shape[2] == 4 else None
    H, W = rgb.shape[:2]
    print(f"[load] {im.mode} {im.size} sha256={sha[:16]}… alpha_min={None if alpha is None else int(alpha.min())}")

    # ── 印面宽度 W_d（最大印泥连通域 bbox）────────────────────────────────────────────
    m = cc.ink_mask(rgb.astype(np.float64))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    order = np.argsort(-stats[1:, 4]) + 1
    main_lab = int(order[0])
    x, y, w, h, area = (int(v) for v in stats[main_lab])
    W_d, H_d = w, h
    seal = labels == main_lab
    print(f"[seal] bbox=({x},{y},{w},{h}) area={area} ink_ratio={m.mean():.5f} W_d={W_d} H_d={H_d}")

    # ── 纸底（非印泥 ∧ 高亮度）────────────────────────────────────────────────────────
    g = rgb.astype(np.float32).mean(axis=2)
    v = rgb.max(axis=2).astype(np.float32) / 255.0
    nonink = ~m
    thr = float(np.percentile(v[nonink], 90.0))
    paper = nonink & (v >= thr)
    paper_px = rgb[paper].astype(np.float64)
    mm_per_px = W_O_MM / float(W_d)                 # 共同标尺换算（含明示假设）
    print(f"[paper] px={int(paper.sum())} mean_rgb={np.round(paper_px.mean(0),2)} "
          f"mm_per_px={mm_per_px:.6f} (≈{1/mm_per_px*25.4:.0f} dpi 等效)")

    hist, edges = np.histogram(lum(rgb)[paper], bins=16, range=(0, 256))
    paper_hist = {"bin_edges": [int(e) for e in edges], "counts": [int(c) for c in hist]}
    deciles = [round(float(np.percentile(lum(rgb)[paper], p)), 3) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)]

    # ── 纸纹理：确定性选取 3 块纯纸补丁 ───────────────────────────────────────────────
    patches = []
    for (ox, oy) in PATCH_ORIGINS:
        sl = (slice(oy, oy + PATCH), slice(ox, ox + PATCH))
        sub_rgb = rgb[sl]
        ink_px = int(m[sl].sum())
        res = lum(sub_rgb) - float(lum(sub_rgb).mean())
        patches.append({"origin_px": [ox, oy], "size": PATCH, "ink_px_in_patch": ink_px,
                        "raw_std": round(float(res.std()), 4),
                        "readout": radial_psd(res, mm_per_px, W_d),
                        "band_rms": {k: bandpass_std(res, BAND_FRAC[k][0] * W_d, BAND_FRAC[k][1] * W_d)
                                     for k in BAND_FRAC},
                        "autocorr": _ac(res)})
        print(f"[patch {ox},{oy}] std={patches[-1]['raw_std']} peakλ="
              f"{patches[-1]['readout'].get('psd_peak_wavelength_px')}px "
              f"ac={patches[-1]['autocorr']}")

    # 合并读数（3 补丁中位）
    def med(path):
        vals = []
        for p in patches:
            cur = p
            for k in path:
                cur = cur[k]
            if cur is not None:
                vals.append(float(cur))
        return round(float(np.median(vals)), 6) if vals else None

    peak_px = med(["readout", "psd_peak_wavelength_px"])
    cen_px = med(["readout", "psd_centroid_wavelength_px"])
    ac_x = med(["autocorr", "x_px"])
    ac_y = med(["autocorr", "y_px"])
    f_per_patch = [p["readout"].get("band", {}).get("coarse", {}).get("peak_wavelength_px")
                   for p in patches]
    f_d = float(np.median([v for v in f_per_patch if v is not None])) if any(
        v is not None for v in f_per_patch) else peak_px

    # ── 印泥色彩 ──────────────────────────────────────────────────────────────────────
    core = cc.ink_core_centroid(rgb.astype(np.float64))
    core_px = rgb[core["mask"]].astype(np.float64)
    ink_core_med = np.median(core_px, axis=0)
    ink_all_med = np.median(rgb[m].astype(np.float64), axis=0)
    hsv_core = cc.rgb_to_hsv(ink_core_med)
    de_core = float(cc.delta_e2000(ink_core_med, cc.TARGET_RGB))
    de_cent = float(cc.delta_e2000(core["rgb"], cc.TARGET_RGB))
    sat_core = np.array([cc.rgb_to_hsv(p)[1] for p in
                         rgb[core["mask"]][:: max(1, int(core["mask"].sum() / 4000))].astype(np.float64)])
    print(f"[ink] core_med={np.round(ink_core_med,2)} ΔE(med→#C95021)={de_core:.3f} "
          f"ΔE(centroid)={de_cent:.3f} sat_p50={np.median(sat_core):.3f}")

    # ── 晕染过渡宽度（掩膜外 redness 剖面 0.9→0.1）────────────────────────────────────
    halo = _halo_profile(rgb, m, mm_per_px)

    out = {
        "schema": "feicui.doubao-reference-features.v1",
        "generator": "ops/variant-samples/doubao_reference.py",
        "role": "外部对标参照（豆包对话版输出图）；**只对标纸纹理/印泥色彩/晕染过渡**三项",
        "hard_limit": ("豆包图系生成式输出，已确认**重绘印文**（字形粘连/断裂/变形、笔画粗细不匀、边缘毛糙）"
                       "⇒ 禁止对标其字形与线条锐度；我们守白字/字形冻结，该项**不学**"),
        "source": {"path": str(SRC), "copied_into_repo": False, "mode": im.mode,
                   "size_px": [W, H], "bytes": len(raw), "sha256": sha,
                   "note": "原件只读引用，不复制进仓（红线：样张只落 output/samples/）"},
        "ruler": {"definition": "共同标尺＝**印面宽度**（不依赖实物尺寸假设）",
                  "W_d_px": W_d, "H_d_px": H_d, "seal_bbox_px": [x, y, w, h],
                  "seal_method": "colorcal.ink_mask → 最大 8 邻连通域 bbox",
                  "ours_2400dpi": {"region": "P29-C1R1", "W_o_px": W_O_PX, "W_o_mm": W_O_MM},
                  "mm_per_px_equiv": round(mm_per_px, 8),
                  "equiv_dpi": round(25.4 / mm_per_px, 1),
                  "equiv_assumption": EQUIV_ASSUMP_MM},
        "paper_texture": {
            "patches": patches, "patch_origins_px": [list(o) for o in PATCH_ORIGINS], "patch_px": PATCH,
            "band_definition_normalized_to_W_d": {k: list(v) for k, v in BAND_FRAC.items()},
            "f_d_px": f_d, "f_d_over_W_d": round(f_d / W_d, 8),
            "psd_peak_wavelength_px": peak_px, "psd_peak_over_W_d": round(peak_px / W_d, 8),
            "psd_centroid_wavelength_px": cen_px,
            "autocorr_half_decay_px": {"x": ac_x, "y": ac_y},
            "autocorr_half_decay_over_W_d": {"x": None if ac_x is None else round(ac_x / W_d, 8),
                                             "y": None if ac_y is None else round(ac_y / W_d, 8)},
            "band_rms_median_0_255": {k: med(["band_rms", k]) for k in BAND_FRAC},
            "band_peak_wavelength_px_median": {k: med(["readout", "band", k, "peak_wavelength_px"])
                                               for k in BAND_FRAC},
            "texture_rms_0_255_median": med(["raw_std"]),
            "texture_highpass_rms_0_255": med(["band_rms", "grain"]),
        },
        "paper_color": {
            "mask": "非印泥 ∧ V ≥ p90(非印泥)", "px": int(paper.sum()),
            "mean_rgb": [round(float(v), 3) for v in paper_px.mean(0)],
            "median_rgb": [round(float(v), 3) for v in np.median(paper_px, axis=0)],
            "p5_p95_rgb": [[round(float(v), 2) for v in np.percentile(paper_px, 5, axis=0)],
                           [round(float(v), 2) for v in np.percentile(paper_px, 95, axis=0)]],
            "min_rgb": [int(v) for v in paper_px.min(0)], "max_rgb": [int(v) for v in paper_px.max(0)],
            "lum_deciles": deciles, "lum_hist16": paper_hist,
            "hue_deg_mean": round(float(cc.rgb_to_hsv(paper_px.mean(0))[0]), 3),
            "sat_mean": round(float(cc.rgb_to_hsv(paper_px.mean(0))[1]), 5),
        },
        "ink_color": {
            "mask": "colorcal.ink_mask", "ink_px": int(m.sum()), "ink_ratio": round(float(m.mean()), 5),
            "core_definition": "colorcal.ink_core_centroid（掩膜内 S ≥ p75）",
            "core_px": int(core["mask"].sum()),
            "median_rgb": [round(float(v), 3) for v in ink_core_med],
            "centroid_rgb": [round(float(v), 3) for v in core["rgb"]],
            "mask_all_median_rgb": [round(float(v), 3) for v in ink_all_med],
            "hsv_median": [round(float(v), 4) for v in hsv_core],
            "sat_p50": round(float(np.median(sat_core)), 4),
            "sat_p90": round(float(np.percentile(sat_core, 90)), 4),
            "delta_e2000_median_rgb_to_target": round(de_core, 4),
            "delta_e2000_centroid_to_target": round(de_cent, 4),
            "target": {"hex": cc.TARGET_HEX, "rgb": list(cc.TARGET_RGB)},
            "delta_e_impl": "colorcal.delta_e2000（单一真源）",
        },
        "halo_transition": halo,
        "targets_for_us": {
            "note": "把豆包读数换成**我们 2400dpi** 的标定值（目标纤维长度 ＝ W_o × (f_d/W_d)）",
            "fiber_len_px_at_2400": round(W_O_PX * f_d / W_d, 3),
            "fiber_len_mm_equiv": round(W_O_MM * f_d / W_d, 4),
            "fiber_len_source": "f_d ＝ 粗纤维带（0.020–0.060·W_d）峰值波长",
            "psd_peak_len_px_at_2400": round(W_O_PX * peak_px / W_d, 3),
            "psd_peak_len_mm_equiv": round(W_O_MM * peak_px / W_d, 4),
            "texture_rms_0_255": med(["raw_std"]),
            "band_rms_mm_bands": {k: med(["band_rms", k]) for k in BAND_FRAC},
            "paper_mean_rgb": [round(float(v), 3) for v in paper_px.mean(0)],
            "ink_median_rgb": [round(float(v), 3) for v in ink_core_med],
            "ink_delta_e_to_target": round(de_core, 4),
            "halo_transition_px_at_2400": (None if halo["transition_width_px"] is None
                                           else round(halo["transition_width_px"] * W_O_PX / W_d, 3)),
            "halo_transition_mm_equiv": (None if halo["transition_width_px"] is None
                                         else round(halo["transition_width_px"] * mm_per_px, 4)),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[out] {OUT} {OUT.stat().st_size}B")
    print(json.dumps({"W_d": W_d, "f_d_px": f_d, "f_d/W_d": round(f_d / W_d, 6),
                      "fiber_mm_equiv": out["targets_for_us"]["fiber_len_mm_equiv"],
                      "texture_rms": med(["raw_std"]), "paper_mean_rgb": out["paper_color"]["mean_rgb"],
                      "ink_delta_e": round(de_core, 3),
                      "halo_px": halo["transition_width_px"]}, ensure_ascii=False))
    return 0


def _ac(res: np.ndarray) -> dict:
    a = res.astype(np.float64)
    a = a - a.mean()
    h, w = a.shape
    ph, pw = 1 << int(np.ceil(np.log2(2 * h))), 1 << int(np.ceil(np.log2(2 * w)))
    F = np.fft.rfft2(a, s=(ph, pw))
    ac = np.fft.fftshift(np.fft.irfft2(np.abs(F) ** 2, s=(ph, pw)))
    ac = ac / ac[ph // 2, pw // 2]
    lx = _half_decay(ac[ph // 2, pw // 2:pw // 2 + w // 2])
    ly = _half_decay(ac[ph // 2:ph // 2 + h // 2, pw // 2])
    return {"x_px": None if lx is None else round(float(lx), 3),
            "y_px": None if ly is None else round(float(ly), 3)}


def _halo_profile(rgb: np.ndarray, m: np.ndarray, mm_per_px: float) -> dict:
    """掩膜外「红度」剖面 → 晕染过渡宽度（红度 0.9→0.1 的距离，px）。"""
    f = rgb.astype(np.float32)
    red = f[..., 0] - 0.5 * (f[..., 1] + f[..., 2])
    inside = red[m]
    ref = float(np.percentile(inside, 75.0)) if inside.size else 0.0
    dist = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 3)
    prof = []
    for d in range(1, 21):
        sel = (~m) & (dist >= d) & (dist < d + 1)
        prof.append(round(float(red[sel].mean() / max(ref, 1e-6)), 5) if sel.any() else None)
    width = None
    for i, v in enumerate(prof):
        if v is not None and v <= 0.10:
            if i == 0:
                width = 1.0
            else:
                v0 = prof[i - 1] if prof[i - 1] is not None else 0.0
                frac = (v0 - 0.10) / (v0 - v) if v0 != v else 0.0
                width = (i) + float(np.clip(frac, 0.0, 1.0))
            break
    return {"method": "掩膜外 redness 均值 / 掩膜内 p75，首个 ≤10% 的距离（px）",
            "ref_redness_p75_inside": round(ref, 3),
            "profile_d1_to_d20": prof,
            "transition_width_px": None if width is None else round(width, 3),
            "transition_width_mm_equiv": None if width is None else round(width * mm_per_px, 4),
            "half_decay_px": None if width is None else round(width, 3)}


if __name__ == "__main__":
    raise SystemExit(main())
