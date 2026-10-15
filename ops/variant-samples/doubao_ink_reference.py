#!/usr/bin/env python
"""豆包参照图 #2（**只看印泥质感**）定量特征提取 ＋ 可复用的印泥特征度量（Kong · ops/variant-samples）。

输入＝Kevin 提供的第二张豆包输出（**只读**，不复制进仓；路径与 sha256 记入证据件）。
输出＝`ops/variant-samples/doubao-ink-reference-features.json`。

**本文件同时是「印泥特征度量」的单一真源**：`ink_features()` 对豆包图与我们自己的 2400dpi 区域图
用**完全同一套度量**（同标尺 ⇒ 可比）。`round2_samples.py` 只 import 调用，不复制实现。

对标范围（硬口径）：**只取印泥质感三件事** —— 语义浓淡（L* 随距边距离的结构）、颗粒、边缘/半透/晕染；
**严禁**对标字形与线条锐度（豆包图为生成式输出，已重绘印文）。

跑法：cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/variant-samples/doubao_ink_reference.py
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

SRC = Path("/Users/kevin/Library/Application Support/Hermes/composer-images/"
           "21791e391694111a3dbb1d317749662b_3f2a2d.jpg")
OUT = Path(__file__).resolve().parent / "doubao-ink-reference-features.json"

W_O_PX, W_O_MM = 2120, 22.437          # 我们的 2400dpi 标尺（C1-R1 印面）
EQUIV_ASSUMP_MM = "假设豆包图印面实物宽 ＝ C1-R1 印面 22.437 mm（把归一化尺度翻成 mm 的显式假设）"


# ══════════════════════════════════════════════════════════════════════════════════════
# 印泥特征度量（豆包图 / 我们的图 **同一套**）
# ══════════════════════════════════════════════════════════════════════════════════════
def sat_of(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    mx, mn = f.max(axis=2), f.min(axis=2)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)


def lum_of(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    return f[..., 0] * np.float32(0.299) + f[..., 1] * np.float32(0.587) + f[..., 2] * np.float32(0.114)


def _lab_L(rgb_px: np.ndarray) -> np.ndarray:
    if rgb_px.size == 0:
        return np.zeros(0)
    return np.asarray(cc._srgb_to_lab_arr(rgb_px.astype(np.float64)), dtype=np.float64)[:, 0]


def _halo_profile(rgb: np.ndarray, m: np.ndarray, d_max: int = 24) -> dict:
    """掩膜外「红度」剖面 → 晕染过渡宽度（红度衰减到 10% 的距离）。"""
    f = rgb.astype(np.float32)
    red = f[..., 0] - 0.5 * (f[..., 1] + f[..., 2])
    ref = float(np.percentile(red[m], 75.0)) if m.any() else 0.0
    dist = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 3)
    prof = []
    for d in range(0, d_max + 1):
        sel = (~m) & (dist >= d) & (dist < d + 1)
        prof.append(round(float(red[sel].mean() / max(ref, 1e-6)), 5) if sel.any() else None)
    width = None
    for i, v in enumerate(prof):
        if v is not None and v <= 0.10:
            if i == 0:
                width = 0.0
            else:
                v0 = prof[i - 1] if prof[i - 1] is not None else 0.0
                frac = (v0 - 0.10) / (v0 - v) if v0 != v else 0.0
                width = float(i - 1) + float(np.clip(frac, 0.0, 1.0))
            break
    return {"method": "掩膜外 redness 均值 / 掩膜内 p75，首个 ≤10% 的距离（px）",
            "ref_redness_p75_inside": round(ref, 4),
            "profile_d0_to_d%d" % d_max: prof,
            "transition_width_px": None if width is None else round(width, 3)}


def ink_features(rgb: np.ndarray, W_d: int | None = None, mm_per_px: float | None = None,
                 label: str = "", grain_blur_sigma_px: float = 2.0) -> dict:
    """印泥区定量特征（对豆包图与我们的图**同一套度量**）。

    `grain_blur_sigma_px`：颗粒高通所用高斯半径（**像素**）。跨图比较时须换算成**同一物理尺度**：
    参照图 2px@812dpi（≈0.063mm）↔ 我们 2400dpi 用 5.9px（`CAL["ink_grain_blur_sigma_px_at_ours"]`）。

    * 覆盖/色彩：印泥占比、核心质心中位色、饱和度分位、ΔE2000→`#C95021`（colorcal 现算）
    * **语义浓淡**：到最近非印泥像素的距离（≈ 局部笔画半宽）分位箱 → 各箱 L* 均值；
      给出「宽处−细处」的 L* 反差与归一化斜率（L* / 归一化距离 d/d_p90）
    * **颗粒**：红墨区内（腐蚀掉边缘）高通残差 σ（L* 与 S 两个域）＋ 颗粒波长（径向谱峰值）
    * **半透/露白**：掩膜内「接近纸底亮/低饱和」像素占比
    * **边缘**：饱和度水平集 0.75→0.25 的过渡宽度（px）＋ 边界粗糙度代理（周长比）
    * **哑光**：掩膜内高光占比（亮斑）——哑光应≈0
    """
    m = np.asarray(cc.ink_mask(rgb.astype(np.float64)), bool)
    H, W = m.shape
    n_ink = int(m.sum())
    out: dict = {"label": label, "size_px": [W, H], "ink_px": n_ink,
                 "ink_ratio": round(n_ink / float(H * W), 5)}
    if n_ink == 0:
        return out
    n_lab, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    areas = stats[1:, 4]
    order = np.argsort(-areas) + 1
    bx, by, bw, bh, barea = (int(v) for v in stats[order[0]])
    out["components"] = int(n_lab - 1)
    out["largest_component"] = {"bbox_px": [bx, by, bw, bh], "area": barea,
                                "fill_ratio": round(barea / float(bw * bh), 4),
                                "component_count_ge_1pct_main": int((areas >= 0.01 * areas[0]).sum())}
    if W_d is None:
        W_d = bw
    out["ruler_W_d_px"] = int(W_d)
    if mm_per_px is None:
        mm_per_px = W_O_MM / float(W_d)
    out["mm_per_px_equiv"] = round(float(mm_per_px), 8)

    # ── 色彩 ────────────────────────────────────────────────────────────────────────
    core = cc.ink_core_centroid(rgb.astype(np.float64))
    core_px = np.asarray(rgb, np.float64)[core["mask"]]
    med = np.median(core_px, axis=0) if core_px.size else np.zeros(3)
    hsv = cc.rgb_to_hsv(med)
    sat = sat_of(rgb)[m]
    out["color"] = {
        "core_definition": "colorcal.ink_core_centroid（掩膜内 S ≥ p75）",
        "core_px": int(core["mask"].sum()),
        "median_rgb": [round(float(v), 3) for v in med],
        "centroid_rgb": [round(float(v), 3) for v in core["rgb"]] if core["rgb"] else None,
        "median_hsv": [round(float(v), 4) for v in hsv],
        "mask_median_rgb": [round(float(v), 3) for v in np.median(np.asarray(rgb, np.float64)[m], axis=0)],
        "sat_p50": round(float(np.percentile(sat, 50)), 4),
        "sat_p90": round(float(np.percentile(sat, 90)), 4),
        "sat_p10": round(float(np.percentile(sat, 10)), 4),
        "delta_e2000_median_to_target": round(float(cc.delta_e2000(med, cc.TARGET_RGB)), 4),
        "delta_e2000_centroid_to_target": (round(float(cc.delta_e2000(core["rgb"], cc.TARGET_RGB)), 4)
                                           if core["rgb"] else None),
        "target_hex": cc.TARGET_HEX, "delta_e_impl": "colorcal.delta_e2000（单一真源）",
    }

    # ── 语义浓淡（距离场 → L* 结构）─────────────────────────────────────────────────
    d_in = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3).astype(np.float64)
    d_p90 = float(np.percentile(d_in[m], 90.0))
    d_p50 = float(np.percentile(d_in[m], 50.0))
    rgb_m = np.asarray(rgb, np.float64)[m]
    L_m = _lab_L(rgb_m)
    edges = np.linspace(0.0, max(d_p90, 1e-6), 7)
    bins, Lbox, cent = [], [], []
    for i in range(6):
        sel = (d_in[m] >= edges[i]) & (d_in[m] <= edges[i + 1] if i == 5 else d_in[m] < edges[i + 1])
        if int(sel.sum()) > 30:
            bins.append({"d_px_range": [round(edges[i], 2), round(edges[i + 1], 2)],
                         "d_over_d_p90": [round(edges[i] / d_p90, 3), round(edges[i + 1] / d_p90, 3)],
                         "px": int(sel.sum()), "L_mean": round(float(L_m[sel].mean()), 3),
                         "S_mean": round(float(sat_of(rgb)[m][sel].mean()), 4)})
            Lbox.append(float(L_m[sel].mean()))
            cent.append(0.5 * (edges[i] + edges[i + 1]))
    dn = d_in[m] / max(d_p90, 1e-9)
    slope = float(np.polyfit(dn, L_m, 1)[0]) if L_m.size > 100 else None
    q_wide = float(np.percentile(dn, 80))
    q_thin = float(np.percentile(dn, 20))
    L_wide = float(L_m[dn >= q_wide].mean())
    L_thin = float(L_m[dn <= q_thin].mean())
    out["semantic_lightness"] = {
        "definition": "距离变换 d ＝ 到最近非印泥像素的距离（≈ 局部笔画半宽）；d_p90 归一",
        "d_p50_px": round(d_p50, 3), "d_p90_px": round(d_p90, 3),
        "d_p50_over_W_d": round(d_p50 / W_d, 6), "d_p90_over_W_d": round(d_p90 / W_d, 6),
        "L_bins": bins,
        "L_vs_dn_slope": None if slope is None else round(slope, 4),
        "L_wide_minus_thin": round(L_wide - L_thin, 3),
        "L_p80dn_mean": round(L_wide, 3), "L_p20dn_mean": round(L_thin, 3),
        "sign_convention": "L* 越大＝越亮（越薄/越淡）；宽处浓 ⇒ L_wide − L_thin < 0",
    }
    out["lstar"] = {"mean": round(float(L_m.mean()), 3), "std": round(float(L_m.std()), 3),
                    "p10": round(float(np.percentile(L_m, 10)), 3),
                    "p50": round(float(np.percentile(L_m, 50)), 3),
                    "p90": round(float(np.percentile(L_m, 90)), 3),
                    "L_over_dn": "见 semantic_lightness"}

    # ── 颗粒（腐蚀掉边缘后取内部高通残差）──────────────────────────────────────────
    er = cv2.erode(m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    lum = lum_of(rgb)
    S = sat_of(rgb)
    if er.any():
        hp_L = (lum - cv2.GaussianBlur(lum, (0, 0), grain_blur_sigma_px))[er]
        hp_S = (S - cv2.GaussianBlur(S, (0, 0), grain_blur_sigma_px))[er]
        res = (lum - cv2.GaussianBlur(lum, (0, 0), grain_blur_sigma_px))
        # 颗粒波长：内部残差的径向谱峰值
        y0, y1 = by, min(by + bh, H)
        x0, x1 = bx, min(bx + bw, W)
        sub = res[y0:y1, x0:x1] * er[y0:y1, x0:x1]
        lam_pk = _radial_peak_wavelength(sub)
        out["grain"] = {
            "domain": f"腐蚀 7×7 后的红墨区内部（避边）；高通高斯半径 {grain_blur_sigma_px}px",
            "grain_blur_sigma_px": float(grain_blur_sigma_px),
            "px_eroded": int(er.sum()),
            "lum_highpass_sigma_2px": round(float(hp_L.std()), 4),
            "sat_highpass_sigma_2px": round(float(hp_S.std()), 5),
            "L_highpass_p90_abs": round(float(np.percentile(np.abs(hp_L), 90)), 4),
            "peak_wavelength_px": lam_pk,
            "peak_wavelength_over_W_d": (None if lam_pk is None else round(lam_pk / W_d, 6)),
        }
    else:
        out["grain"] = None

    # ── 半透 / 露白 ＋ 哑光高光 ─────────────────────────────────────────────────────
    v = np.asarray(rgb, np.float32).max(axis=2) / 255.0
    nonink = ~m
    v_paper = float(np.percentile(v[nonink], 90.0)) if nonink.any() else 1.0
    light_in = m & (v >= v_paper)
    out["translucency"] = {
        "definition": f"掩膜内 V ≥ p90(V of 非印泥)={round(v_paper,4)} 的像素占比（露白/半透）",
        "share_light_inside": round(float(light_in.sum() / max(n_ink, 1)), 5),
        "share_sat_lt_0.25_inside": round(float((sat_of(rgb)[m] < 0.25).mean()), 5),
        "V_inside_p90": round(float(np.percentile(v[m], 90)), 4),
        "V_inside_p50": round(float(np.percentile(v[m], 50)), 4),
    }
    out["matte"] = {
        "definition": "哑光＝无高光/光泽；指标＝掩膜内亮斑（V > p99 of 非印泥）占比与最大 V",
        "highlight_share_V_gt_paperp99": round(float((v[m] > float(np.percentile(v[nonink], 99.0))).mean()), 6)
        if nonink.any() else None,
        "V_max_inside": round(float(v[m].max()), 4),
        "specular_added_by_us": None,
    }

    # ── 边缘：过渡宽度 ＋ 粗糙度代理 ────────────────────────────────────────────────
    Ss = cv2.GaussianBlur(sat_of(rgb), (0, 0), 1.0)
    Sref = float(np.percentile(Ss[m], 90.0))
    A = Ss >= 0.75 * Sref
    B = Ss >= 0.25 * Sref
    if (B & ~A).any():
        dA = cv2.distanceTransform((~A).astype(np.uint8), cv2.DIST_L2, 3)
        tw = dA[B & ~A]
        edge = {"method": "饱和度水平集 0.75→0.25 过渡带宽（px）",
                "transition_width_px_median": round(float(np.median(tw)), 3),
                "transition_width_px_mean": round(float(tw.mean()), 3),
                "transition_width_px_p90": round(float(np.percentile(tw, 90)), 3)}
    else:
        edge = {"method": "饱和度水平集 0.75→0.25 过渡带宽（px）", "transition_width_px_median": None}
    main_comp = (labels == order[0]).astype(np.uint8)
    per = float(cv2.arcLength(cv2.findContours(main_comp, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_NONE)[0][0], True))
    edge["boundary_roughness_proxy"] = {
        "definition": "周长²/(4π·面积)（等周比；〉1 越大越毛糙）与 周长/(2(w+h))",
        "isoperimetric_ratio": round(per * per / (4.0 * np.pi * max(barea, 1)), 4),
        "perimeter_over_bbox_perimeter": round(per / (2.0 * max(bw + bh, 1)), 4),
        "perimeter_px": round(per, 1)}
    out["edge"] = edge
    out["halo"] = _halo_profile(rgb, m)
    if out["halo"]["transition_width_px"] is not None:
        out["halo"]["transition_width_over_W_d"] = round(out["halo"]["transition_width_px"] / W_d, 6)
        out["halo"]["transition_width_mm_equiv"] = round(out["halo"]["transition_width_px"] * mm_per_px, 5)
    out["halo"]["outer_band_of_overlap_mm_equiv"] = None
    out["halo"]["outer_band_of_overlap_px"] = _outer_halo_band(rgb, m, 0.02)
    return out


def _outer_halo_band(rgb: np.ndarray, m: np.ndarray, thresh: float) -> float | None:
    """红度仍高于阈值(相对掩膜内 p75)的最远距离（px）——晕染「可见外沿」。"""
    f = rgb.astype(np.float32)
    red = f[..., 0] - 0.5 * (f[..., 1] + f[..., 2])
    ref = float(np.percentile(red[m], 75.0)) if m.any() else 0.0
    dist = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 3)
    last = None
    for d in range(0, 40):
        sel = (~m) & (dist >= d) & (dist < d + 1)
        if sel.any() and float(red[sel].mean()) / max(ref, 1e-6) >= thresh:
            last = d
    return None if last is None else float(last + 1)


def _radial_peak_wavelength(res: np.ndarray) -> float | None:
    """残差场的径向功率谱峰值波长（px）；剔除 λ > 1/4 视野的低频。"""
    a = np.asarray(res, np.float64)
    if a.shape[0] < 32 or a.shape[1] < 32 or not np.any(a):
        return None
    a = a - a.mean()
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.rfft2(a * win)) ** 2
    fy = np.fft.fftfreq(h, d=1.0)
    fx = np.fft.rfftfreq(w, d=1.0)
    FY, FX = np.meshgrid(fy, fx, indexing="ij")
    fr = np.sqrt(FY ** 2 + FX ** 2)
    nb = 120
    edges = np.linspace(0.0, float(fr.max()), nb + 1)
    idx = np.clip(np.digitize(fr.ravel(), edges) - 1, 0, nb - 1)
    psd = np.bincount(idx, weights=P.ravel(), minlength=nb) / np.maximum(np.bincount(idx, minlength=nb), 1)
    fcen = 0.5 * (edges[:-1] + edges[1:])
    m = fcen > 4.0 / min(h, w)
    if not m.any():
        return None
    return round(float(1.0 / fcen[m][int(np.argmax(psd[m]))]), 3)


# ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    assert SRC.is_file(), SRC
    raw = SRC.read_bytes()
    im = Image.open(SRC).convert("RGB")
    rgb = np.asarray(im).copy()
    feats = ink_features(rgb, W_d=None, mm_per_px=None, label="豆包参照图#2（只取印泥质感）")
    W_d = feats["ruler_W_d_px"]
    mpp = feats["mm_per_px_equiv"]
    feats["hard_limit"] = ("生成式输出，已重绘印文（字形粘连/断裂/变形、笔画粗细不匀、边缘毛糙）"
                           "⇒ 只取**印泥质感**（语义浓淡/颗粒/半透/边缘/晕染）；"
                           "**严禁**对标字形与线条锐度（我们守白字/字形冻结）")
    out = {
        "schema": "feicui.doubao-ink-reference-features.v1",
        "generator": "ops/variant-samples/doubao_ink_reference.py",
        "role": "第二张豆包参照图：**只看印泥质感**（Kevin 明确：不看纸纹理）",
        "source": {"path": str(SRC), "copied_into_repo": False, "mode": "RGB",
                   "size_px": list(im.size), "bytes": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest()},
        "ruler": {"definition": "共同标尺＝最大印泥连通域宽度（与图#1 同一套归一化思路）",
                  "W_d_px": W_d, "ours_2400dpi": {"W_o_px": W_O_PX, "W_o_mm": W_O_MM},
                  "mm_per_px_equiv": round(mpp, 8), "equiv_dpi": round(25.4 / mpp, 1),
                  "equiv_assumption": EQUIV_ASSUMP_MM},
        "features": feats,
        "targets_for_us_px_at_2400": {
            "note": "把豆包读数换成**我们 2400dpi** 的标定值（px@2400 ＝ 豆包 px × W_o/W_d）",
            "grain_peak_wavelength": (None if feats["grain"]["peak_wavelength_px"] is None
                                      else round(feats["grain"]["peak_wavelength_px"] * W_O_PX / W_d, 3)),
            "grain_peak_wavelength_mm": (None if feats["grain"]["peak_wavelength_px"] is None
                                         else round(feats["grain"]["peak_wavelength_px"] * W_O_MM / W_d, 4)),
            "edge_transition_width": (None if feats["edge"]["transition_width_px_median"] is None
                                      else round(feats["edge"]["transition_width_px_median"] * W_O_PX / W_d, 3)),
            "edge_transition_width_mm": (None if feats["edge"]["transition_width_px_median"] is None
                                         else round(feats["edge"]["transition_width_px_median"] * W_O_MM / W_d, 4)),
            "halo_transition_width": (None if feats["halo"]["transition_width_px"] is None
                                      else round(feats["halo"]["transition_width_px"] * W_O_PX / W_d, 3)),
            "halo_transition_width_mm": (None if feats["halo"]["transition_width_px"] is None
                                         else round(feats["halo"]["transition_width_px"] * W_O_MM / W_d, 4)),
            "semantic_L_wide_minus_thin": feats["semantic_lightness"]["L_wide_minus_thin"],
            "semantic_slope_per_dn": feats["semantic_lightness"]["L_vs_dn_slope"],
            "grain_lum_highpass_std_0_255": feats["grain"]["lum_highpass_sigma_2px"],
            "translucency_share_light_inside": feats["translucency"]["share_light_inside"],
            "ink_median_rgb": feats["color"]["median_rgb"],
            "ink_sat_p50": feats["color"]["sat_p50"],
            "ink_delta_e_to_target": feats["color"]["delta_e2000_median_to_target"],
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[out] {OUT} {OUT.stat().st_size}B")
    print(json.dumps({"W_d": W_d, "ink_ratio": feats["ink_ratio"],
                      "med_rgb": feats["color"]["median_rgb"], "sat_p50": feats["color"]["sat_p50"],
                      "dE": feats["color"]["delta_e2000_median_to_target"],
                      "L_std": feats["lstar"]["std"], "L_wide-thin": feats["semantic_lightness"]["L_wide_minus_thin"],
                      "slope": feats["semantic_lightness"]["L_vs_dn_slope"],
                      "grain_std": feats["grain"]["lum_highpass_sigma_2px"],
                      "grain_lam_px": feats["grain"]["peak_wavelength_px"],
                      "translucency": feats["translucency"]["share_light_inside"],
                      "edge_w": feats["edge"]["transition_width_px_median"],
                      "halo_w": feats["halo"]["transition_width_px"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
