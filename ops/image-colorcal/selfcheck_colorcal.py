#!/usr/bin/env python
"""`app/colorcal.py` 自检（Kong 地基单 · **V2 双锚点仿射**口径）。

跑法（**必须用 worker venv**，含 numpy/PIL）：
    /Users/kevin/bistro/feicui/venv/bin/python \
        /Users/kevin/bistro/feicui/ops/image-colorcal/selfcheck_colorcal.py

断言（与派单 ＋ Zang/Kevin 追加裁定一一对应）：
  (a) **纸集排除印泥（★ v0.1 修订 3）**：在**高印泥占比（40%）**合成图上，默认口径（纸集＝
      **非印泥 ∧ V≥p90**）**`a` 全在 [0,3] 内 ⇒ applied**；**对照**（`paper_exclude_ink=False`，
      旧口径）同一图**至少一通道 `raw_a > 3` ⇒ `skipped(limiting)`** —— 并附两条纸锚点 `W` 的读数；
  (b) **越界用例 ⇒ 独立标记 `skipped(limiting)`**（`skip_reason="limiting"`，**不再并入 `degenerate`**；
      默认**不放宽上限**）；
  (c) `ciede2000_lab` 对 **Sharma, Wu & Dalal (2005)** 官方 **34 组** Lab 色对，容差 1e-4（全过）；
  (d) 合成图（纸 `(234,224,200)` ＋ 印泥 `(200,95,45)`）校正后：
        **纸区质心 → `#FFFFFF` 的 ΔE2000 ≤ 3** **且** **印泥核心质心 → `#C95021` 的 ΔE2000 ≤ 2**
        （**两条同时成立**）；
  (e) 退化用例（纸≈印泥色 / **纸锚点不可得**）⇒ `skipped(degenerate)`（`skip_reason=degenerate`）；
  (f) `ink_ratio < 阈值` ⇒ `skipped(ink_ratio=…)`、图未被改动；
  (g) **V1b（可选口径）**：纸 → `#FFFFFF` 白平衡生效（纸区 ΔE ≤ 3）、核心质心 ΔE **如实不为 0**
      （它是「不咬靶色」的直接体现）、`k ≥ 1`、越界 ⇒ `skipped(limiting)`。
另附：`ink_mask` 逐像素判据、`apply_affine` 恒等性、核心质心定义、两侧 import 形态（server/.venv 无 numpy）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))

import numpy as np                      # noqa: E402

from app import colorcal as cc          # noqa: E402

RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(cond)))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  | " + detail) if detail else ""))
    return bool(cond)


# ======================================================================================
# (a)/(f) CIEDE2000 业界已知色对（Sharma et al. 2005 官方 34 组补充测试数据）
#   参考来源：G. Sharma, W. Wu, E. N. Dalal,
#   "The CIEDE2000 Color-Difference Formula: Implementation Notes,
#    Supplementary Test Data, and Mathematical Observations",
#   Color Res. Appl. 30(1):21–30, 2005 —— 表 1「34 组测试数据」。
#   期望值逐字照登；容差 1e-4（官方数据保留 4 位小数）。
# ======================================================================================
SHARMA_PAIRS = [
    # (L1, a1, b1, L2, a2, b2, dE00_expected)
    (50.0000, 2.6772, -79.7751, 50.0000, 0.0000, -82.7485, 2.0425),
    (50.0000, 3.1571, -77.2803, 50.0000, 0.0000, -82.7485, 2.8615),
    (50.0000, 2.8361, -74.0200, 50.0000, 0.0000, -82.7485, 3.4412),
    (50.0000, -1.3802, -84.2814, 50.0000, 0.0000, -82.7485, 1.0000),
    (50.0000, -1.1848, -84.8006, 50.0000, 0.0000, -82.7485, 1.0000),
    (50.0000, -0.9009, -85.5211, 50.0000, 0.0000, -82.7485, 1.0000),
    (50.0000, 0.0000, 0.0000, 50.0000, -1.0000, 2.0000, 2.3669),
    (50.0000, -1.0000, 2.0000, 50.0000, 0.0000, 0.0000, 2.3669),
    (50.0000, 2.4900, -0.0010, 50.0000, -2.4900, 0.0009, 7.1792),
    (50.0000, 2.4900, -0.0010, 50.0000, -2.4900, 0.0010, 7.1792),
    (50.0000, 2.4900, -0.0010, 50.0000, -2.4900, 0.0011, 7.2195),
    (50.0000, 2.4900, -0.0010, 50.0000, -2.4900, 0.0012, 7.2195),
    (50.0000, -0.0010, 2.4900, 50.0000, 0.0009, -2.4900, 4.8045),
    (50.0000, -0.0010, 2.4900, 50.0000, 0.0010, -2.4900, 4.8045),
    (50.0000, -0.0010, 2.4900, 50.0000, 0.0011, -2.4900, 4.7461),
    (50.0000, 2.5000, 0.0000, 50.0000, 0.0000, -2.5000, 4.3065),
    (50.0000, 2.5000, 0.0000, 73.0000, 25.0000, -18.0000, 27.1492),
    (50.0000, 2.5000, 0.0000, 61.0000, -5.0000, 29.0000, 22.8977),
    (50.0000, 2.5000, 0.0000, 56.0000, -27.0000, -3.0000, 31.9030),
    (50.0000, 2.5000, 0.0000, 58.0000, 24.0000, 15.0000, 19.4535),
    (50.0000, 2.5000, 0.0000, 50.0000, 3.1736, 0.5854, 1.0000),
    (50.0000, 2.5000, 0.0000, 50.0000, 3.2972, 0.0000, 1.0000),
    (50.0000, 2.5000, 0.0000, 50.0000, 1.8634, 0.5757, 1.0000),
    (50.0000, 2.5000, 0.0000, 50.0000, 3.2592, 0.3350, 1.0000),
    (60.2574, -34.0099, 36.2677, 60.4626, -34.1751, 39.4387, 1.2644),
    (63.0109, -31.0961, -5.8663, 62.8187, -29.7946, -4.0864, 1.2630),
    (61.2901, 3.7196, -5.3901, 61.4292, 2.2480, -4.9620, 1.8731),
    (35.0831, -44.1164, 3.7933, 35.0232, -40.0716, 1.5901, 1.8645),
    (22.7233, 20.0904, -46.6940, 23.0331, 14.9730, -42.5619, 2.0373),
    (36.4612, 47.8580, 18.3852, 36.2715, 50.5065, 21.2231, 1.4146),
    (90.8027, -2.0831, 1.4410, 91.1528, -1.6435, 0.0447, 1.4441),
    (90.9257, -0.5406, -0.9208, 88.6381, -0.8985, -0.7239, 1.5381),
    (6.7747, -0.2908, -2.4247, 5.8714, -0.0985, -2.2286, 0.6377),
    (2.0776, 0.0795, -1.1350, 0.9033, -0.0636, -0.5514, 0.9082),
]


def test_ciede2000() -> float:
    print("\n=== (a)/(f) CIEDE2000 业界已知色对（Sharma 2005 官方 34 组）===")
    worst = 0.0
    worst_i = -1
    for i, (L1, a1, b1, L2, a2, b2, exp) in enumerate(SHARMA_PAIRS, 1):
        got = cc.ciede2000_lab((L1, a1, b1), (L2, a2, b2))
        err = abs(got - exp)
        if err > worst:
            worst, worst_i = err, i
        if err > 1e-4:
            print(f"      pair#{i}: got={got:.6f} exp={exp:.4f} err={err:.2e}")
    check(f"ciede2000_lab: {len(SHARMA_PAIRS)}/{len(SHARMA_PAIRS)} Sharma 色对 |Δ| ≤ 1e-4",
          worst <= 1e-4, f"最大误差={worst:.2e} @pair#{worst_i}")
    check("delta_e2000(rgb,rgb) == 0", abs(cc.delta_e2000((201, 80, 33), (201, 80, 33))) < 1e-9)
    de_bw = cc.delta_e2000((0, 0, 0), (255, 255, 255))
    check("delta_e2000(黑,白) ≈ 100", abs(de_bw - 100.0) < 1.0, f"= {de_bw:.4f}")
    return worst


# ======================================================================================
# (b)(c)(d) 人工合成图
# ======================================================================================
PAPER_RGB = (234, 224, 200)   # 纸色（暖白、低饱和 ⇒ 不入印泥掩膜）
INK_RGB = (200, 95, 45)       # 印泥色（掩膜内，均匀 ⇒ 核心质心＝印泥色）


def make_synthetic(ink_ratio: float, paper=PAPER_RGB, ink=INK_RGB, h: int = 240, w: int = 240) -> "np.ndarray":
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = paper
    side = int(round((ink_ratio * h * w) ** 0.5))
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    img[y0:y0 + side, x0:x0 + side] = ink
    return img


def test_ink_mask_basic():
    print("\n=== 附：ink_mask 逐像素判据（§2.2.1）===")
    px = np.array([[[201, 80, 33],      # 靶色：r>g+15✓ r>b+15✓ S=0.836✓ ⇒ 入选
                    [234, 224, 200],    # 纸：S=0.145✗ ⇒ 不入选
                    [206, 130, 110],    # 典型印泥：r-g=76✓ r-b=96✓ S=0.466✓ ⇒ 入选
                    [200, 190, 180],    # 近中性：S=0.10✗ ⇒ 不入选
                    [60, 40, 20],       # 暗印泥：r-g=20✓ r-b=40✓ S=0.667✓ ⇒ 入选
                    [0, 0, 0]]], np.uint8)   # 纯黑：S 记 0 ⇒ 不入选
    m = cc.ink_mask(px)[0]
    check("ink_mask 靶色/纸/印泥/中性/暗/黑 = T,F,T,F,T,F",
          list(m) == [True, False, True, False, True, False], f"mask={list(m)}")


def test_synthetic():
    print(f"\n=== (b) 合成图（纸 {PAPER_RGB} ＋ 印泥 {INK_RGB}）双锚点仿射 ===")
    img = make_synthetic(0.25)

    # 锚点定义核对：核心质心＝印泥色；纸区质心＝纸色
    core = cc.ink_core_centroid(img)
    paper = cc.paper_centroid(img)
    print(f"      核心质心 C={tuple(round(x,2) for x in core['rgb'])}（像素 {core['pixels']}，"
          f"S≥{core['sat_threshold']:.3f}）")
    print(f"      纸区质心 W={tuple(round(x,2) for x in paper['rgb'])}（像素 {paper['pixels']}，"
          f"V≥{paper['v_threshold']:.3f}）")

    corrected, rep = cc.correct_image(img, target=cc.TARGET_RGB, white=cc.WHITE_RGB)

    print(f"      mark={rep['marker']}  a={tuple(round(x,3) for x in rep['a'])}  "
          f"b={tuple(round(x,1) for x in rep['b'])}  clamped={rep['clamped']}  "
          f"min|C−W|_lin={rep['min_lin_component']:.4f}")
    print(f"      核心质心 前={tuple(round(x,1) for x in rep['centroid_core_before'])} "
          f"ΔE={rep['delta_e_before']:.4f} → 后="
          f"{tuple(round(x,1) for x in rep['centroid_core_after'])} ΔE={rep['delta_e_after']:.4f}")
    print(f"      纸区质心 → #FFFFFF : 前 ΔE={rep['paper_delta_e_before']:.4f} "
          f"→ 后 ΔE={rep['paper_delta_e_after']:.4f}（纸色后={tuple(round(x,1) for x in rep['paper_after_rgb'])}）")
    print(f"      [观察项] 掩膜全体质心 前={tuple(round(x,1) for x in rep['centroid_all_before'])} "
          f"ΔE={rep['delta_e_all_before']:.3f} → 后="
          f"{tuple(round(x,1) for x in rep['centroid_all_after'])} ΔE={rep['delta_e_all_after']:.3f}")

    check("(b) 印泥核心质心 → #C95021 的 ΔE2000 ≤ 2",
          rep["delta_e_after"] is not None and rep["delta_e_after"] <= 2.0,
          f"ΔE_after={rep['delta_e_after']:.4f}（前 {rep['delta_e_before']:.4f}）")
    check("(b) 纸区质心 → #FFFFFF 的 ΔE2000 ≤ 3",
          rep["paper_delta_e_after"] is not None and rep["paper_delta_e_after"] <= 3.0,
          f"ΔE={rep['paper_delta_e_after']:.4f}（前 {rep['paper_delta_e_before']:.4f}）")
    check("(b) 两条同时成立（mode=applied、未退化）",
          rep["mode"] == "applied" and not rep["clamped"],
          f"a={tuple(round(x,3) for x in rep['a'])} ∈ [0,3]；|b|≤255")

    # 恒等性：a=1,b=0 ⇒ 不改图
    same = np.array_equal(cc.apply_affine(np.full((8, 8, 3), 200, np.uint8), ([1.0, 1.0, 1.0], [0.0, 0.0, 0.0])),
                          np.full((8, 8, 3), 200, np.uint8))
    check("apply_affine(a=1,b=0) 恒等", same)


def make_bands(paper=PAPER_RGB, ink=INK_RGB, pale=None,
               f_paper: float = 1.0, f_ink: float = 0.0, f_pale: float = 0.0,
               h: int = 240, w: int = 240) -> "np.ndarray":
    """按**面积占比**铺三块纯色（确定性、可复现）：纸 / 印泥核心 / 淡印泥。"""
    n = h * w
    n_ink = int(round(f_ink * n))
    n_pale = int(round(f_pale * n))
    n_paper = n - n_ink - n_pale
    flat = np.zeros((n, 3), np.uint8)
    flat[:n_ink] = ink
    flat[n_ink:n_ink + n_pale] = pale if pale is not None else ink
    flat[n_ink + n_pale:] = paper
    return flat.reshape(h, w, 3)


def test_paper_excludes_ink():
    print("\n=== (a) 纸集排除印泥（★ v0.1 修订 3）⇒ 高印泥占比图不再越界 ===")
    # 构造（机制同真实语料）：**淡印泥比纸更亮**（V 高）且**蓝通道低** ⇒ 全图 p90(V) 落到淡印泥上
    #   ⇒ 旧口径纸锚点 `W` ＝ 淡印泥色 ⇒ `a` 在 g/b 通道越界（limiting）
    #   排除印泥后 `W` ＝ 纸区（近中性、蓝通道高）⇒ `a` 全在界内
    PAPER3 = (225, 218, 205)   # 纸：V=0.882、S=0.089（**不入印泥掩膜**）、蓝 205
    INK3 = (200, 95, 45)       # 印泥核心：V=0.784、S=0.775 ⇒ 核心质心锚点
    PALE3 = (230, 170, 140)    # 淡印泥：V=0.902（> 全图 p90）、S=0.391、蓝 140（低）
    img = make_bands(paper=PAPER3, ink=INK3, pale=PALE3, f_ink=0.18, f_pale=0.12)

    p_old = cc.paper_centroid(img, exclude_ink=False)
    p_new = cc.paper_centroid(img, exclude_ink=True)
    print(f"      纸锚点 W 对照:  不排除印泥(exclude_ink=False) = {tuple(round(x,1) for x in p_old['rgb'])}"
          f"（像素 {p_old['pixels']}，V≥{p_old['v_threshold']:.3f}）")
    print(f"                      排除印泥(exclude_ink=True ) = {tuple(round(x,1) for x in p_new['rgb'])}"
          f"（像素 {p_new['pixels']}，V≥{p_new['v_threshold']:.3f}）")
    print(f"      [纸 {PAPER3} | 印泥核心 {INK3} | 淡印泥 {PALE3} | 掩膜占比 "
          f"{0.18 + 0.12:.0%}]")

    _, rep_old = cc.correct_image(img, paper_exclude_ink=False)
    _, rep_new = cc.correct_image(img, paper_exclude_ink=True)
    ra_old = [x for x in (rep_old["raw_a"] or ()) if x is not None]
    ra_new = [x for x in (rep_new["raw_a"] or ()) if x is not None]
    n_over_old = sum(1 for x in ra_old if x > cc.A_MAX or x < cc.A_MIN)
    n_over_new = sum(1 for x in ra_new if x > cc.A_MAX or x < cc.A_MIN)
    print(f"      不排除印泥: raw_a={tuple(round(x,3) for x in ra_old)} 越界通道={n_over_old} "
          f"⇒ mode={rep_old['mode']} marker={rep_old['marker']}")
    print(f"      排除印泥  : raw_a={tuple(round(x,3) for x in ra_new)} 越界通道={n_over_new} "
          f"⇒ mode={rep_new['mode']} a={tuple(round(x,3) for x in (rep_new['a'] or ()))}")

    check("(a) 两口径的纸锚点 W 确实不同（证明排除印泥生效）", p_old["rgb"] != p_new["rgb"])
    check("(a) 对照（不排除印泥）⇒ 至少一通道 raw_a 越界（旧口径的病态）",
          n_over_old >= 1, f"越界通道数={n_over_old}")
    check("(a) 对照（不排除印泥）⇒ skipped(limiting)", rep_old["skip_reason"] == "limiting"
          and rep_old["marker"] == "skipped(limiting)")
    check("(a) 默认（排除印泥）⇒ raw_a 全在界内且 a 全在 [0,3] ⇒ applied",
          rep_new["mode"] == "applied" and n_over_new == 0
          and all(cc.A_MIN <= x <= cc.A_MAX for x in rep_new["a"]),
          f"mode={rep_new['mode']} a={tuple(round(x, 3) for x in (rep_new['a'] or ()))}")

    # V1b（可选口径）同一图：只做纸→白，纸区 ΔE 小、核心 ΔE 如实不为 0
    corr_wb, rep_wb = cc.correct_image_whitebalance(img)
    k = rep_wb["gains"]
    print(f"      [V1b] k={None if k is None else tuple(round(x,4) for x in k)} mode={rep_wb['mode']} "
          f"marker={rep_wb['marker']}")
    if rep_wb["mode"] == "applied":
        print(f"      [V1b] 纸→#FFFFFF ΔE 前={rep_wb['paper_delta_e_before']:.4f} "
              f"后={rep_wb['paper_delta_e_after']:.4f} | 核心→#C95021 ΔE 前={rep_wb['delta_e_before']:.4f} "
              f"后={rep_wb['delta_e_after']:.4f}")


def test_v1b_whitebalance():
    print("\n=== (g) V1b（可选口径）：纸 → #FFFFFF 白平衡 ===")
    img = make_synthetic(0.25)
    corr, rep = cc.correct_image_whitebalance(img)
    k = rep["gains"]
    print(f"      k={tuple(round(x,4) for x in k)}  min k={min(k):.4f}  mode={rep['mode']}  "
          f"marker={rep['marker']}  clamped={rep['clamped']}")
    print(f"      纸→#FFFFFF ΔE: 前={rep['paper_delta_e_before']:.4f} → 后={rep['paper_delta_e_after']:.4f}")
    print(f"      核心→#C95021 ΔE: 前={rep['delta_e_before']:.4f} → 后={rep['delta_e_after']:.4f}"
          f"（**不咬靶色 ⇒ 不为 0**）")
    check("(g) V1b: mode=applied、未越界", rep["mode"] == "applied" and not rep["clamped"])
    check("(g) V1b: 纸区质心 → #FFFFFF 的 ΔE2000 ≤ 3",
          rep["paper_delta_e_after"] is not None and rep["paper_delta_e_after"] <= 3.0,
          f"ΔE={rep['paper_delta_e_after']:.4f}（前 {rep['paper_delta_e_before']:.4f}）")
    check("(g) V1b: k ≥ 1（几何必然：纸不可能比纯白更亮）", all(x >= 1.0 - 1e-12 for x in k),
          f"min k={min(k):.6f}")
    check("(g) V1b: 核心质心 ΔE 后 > 0.5（不咬靶色，与默认路径形成对照）",
          rep["delta_e_after"] is not None and rep["delta_e_after"] > 0.5,
          f"ΔE_after={rep['delta_e_after']:.4f}（默认双锚点同图 ≈0）")
    # 越界臂：纸很暗（但**不在印泥掩膜内**）⇒ k 爆 → skipped(limiting)
    dark_ink = (60, 40, 38)
    img_dark = make_synthetic(0.25, paper=(80, 78, 74), ink=dark_ink)
    corr_dark, rd = cc.correct_image_whitebalance(img_dark)
    print(f"      [越界臂] 纸(80,78,74)（不入掩膜）⇒ raw_gains="
          f"{tuple(None if x is None else round(x,3) for x in (rd['raw_gains'] or ()))} "
          f"min|W|_lin={rd['min_lin_component']} mode={rd['mode']} marker={rd['marker']}")
    check("(g) V1b 越界 ⇒ skipped(limiting)（独立标记）",
          rd["mode"] == "skipped" and rd["skip_reason"] == "limiting"
          and rd["marker"] == "skipped(limiting)",
          f"marker={rd['marker']}")
    check("(g) V1b 越界臂图未被改动", np.array_equal(corr_dark, img_dark))


def test_degenerate():
    print("\n=== (e) 退化用例：纸锚点不可得 ⇒ skipped(degenerate) ===")
    # 全图同一偏红色 ⇒ 印泥掩膜＝全图 ⇒ **非印泥集为空** ⇒ 纸锚点不可得（旧口径下此图 C＝W 亦退化）
    img = np.zeros((60, 60, 3), np.uint8)
    img[:, :] = (200, 120, 100)
    corr, rep = cc.correct_image(img)
    print(f"      ink_ratio={rep['ink_ratio']:.4f}  min|C−W|_lin={rep['min_lin_component']}  "
          f"paper_pixels={rep['paper_pixels']}  paper_anchor_unavailable={rep.get('paper_anchor_unavailable')}")
    print(f"      mode={rep['mode']}  marker={rep['marker']}  reason={rep['skip_reason']}")
    check("(e) mode == 'skipped'", rep["mode"] == "skipped")
    check("(e) marker == 'skipped(degenerate)'", rep["marker"] == "skipped(degenerate)")
    check("(e) skip_reason == 'degenerate'", rep["skip_reason"] == "degenerate")
    check("(e) 图未被改动（逐字节相等）", np.array_equal(corr, img))


def test_limiting():
    print("\n=== (b) 限幅越界用例 ⇒ 独立标记 skipped(limiting) ===")
    # R 通道纸/印泥线性距离小（未到病态 0.02）⇒ a_R 越上限 3 ⇒ limiting
    PAPER2 = (250, 240, 235)
    INK2 = (241, 100, 60)
    img = make_synthetic(0.25, paper=PAPER2, ink=INK2)
    corr, rep = cc.correct_image(img)
    print(f"      min|C−W|_lin={rep['min_lin_component']:.4f}  raw_a={tuple(None if x is None else round(x,3) for x in rep['raw_a'])}")
    print(f"      clamped={rep['clamped']} channels={rep['clamped_channels']}  "
          f"mode={rep['mode']}  marker={rep['marker']}  reason={rep['skip_reason']}")
    check("(b) 越界 ⇒ mode == 'skipped'", rep["mode"] == "skipped")
    check("(b) marker == 'skipped(limiting)'（★ 独立标记，不再并入 degenerate）",
          rep["marker"] == "skipped(limiting)")
    check("(b) marker != 'skipped(degenerate)'", rep["marker"] != "skipped(degenerate)")
    check("(b) skip_reason == 'limiting'", rep["skip_reason"] == "limiting")
    check("(b) 越界通道如实回报（clamped=True 且列出通道）",
          rep["clamped"] is True and len(rep["clamped_channels"]) >= 1,
          f"channels={rep['clamped_channels']}")
    check("(b) 图未被改动（未施加）", np.array_equal(corr, img))
    # **不放宽上限**：同时放开 a 与 b 的界 ⇒ 同一图变为 applied（证明 limiting 只由限幅触发）
    _, rep_wide = cc.correct_image(img, a_max=6.0, b_min=-3000.0, b_max=3000.0)
    print(f"      [对照] 放宽 a_max=6 / |b|≤3000 ⇒ mode={rep_wide['mode']} "
          f"marker={rep_wide['marker']} a={tuple(round(x,3) for x in (rep_wide['a'] or ()))}")
    check("(b) 默认不放宽上限（a_max=3、|b|≤255）；同时放宽 a/b 后同图 applied",
          rep_wide["mode"] == "applied")


def test_skip_ink_ratio():
    print("\n=== (f) 低印泥占比 → skipped(ink_ratio=…) ===")
    img = make_synthetic(0.01)                    # ≈1% < 2%
    corr, rep = cc.correct_image(img, target=cc.TARGET_RGB, ink_ratio_min=0.02)
    print(f"      ink_ratio={rep['ink_ratio']:.4f}  mode={rep['mode']}  marker={rep['marker']}")
    check("(f) mode == 'skipped' 且 skip_reason == 'ink_ratio'",
          rep["mode"] == "skipped" and rep["skip_reason"] == "ink_ratio")
    check("(f) marker 形如 skipped(ink_ratio=…)",
          isinstance(rep["marker"], str) and rep["marker"].startswith("skipped(ink_ratio=")
          and rep["marker"].endswith(")"))
    check("(f) 图未被改动（逐字节相等）", np.array_equal(corr, img))
    check("(f) delta_e_after == delta_e_before（未校正）", rep["delta_e_after"] == rep["delta_e_before"])
    img_ok = make_synthetic(0.03)
    _, rep_ok = cc.correct_image(img_ok, ink_ratio_min=0.02)
    check("(f) 3% > 阈值 ⇒ applied", rep_ok["mode"] == "applied")
    # V1b 同口径：低印泥占比同样跳过、标记同形
    _, rep_wb = cc.correct_image_whitebalance(img, ink_ratio_min=0.02)
    check("(f) V1b 同跳过口径 ⇒ skipped(ink_ratio=…)",
          rep_wb["mode"] == "skipped" and rep_wb["skip_reason"] == "ink_ratio"
          and rep_wb["marker"].startswith("skipped(ink_ratio="))


# ======================================================================================
# 两侧 import 形态（两侧共用同一份实现）
# ======================================================================================
def test_two_sided_import():
    print("\n=== 附：两侧 import 形态（server/.venv 无 numpy）===")
    api_py = REPO / "server" / ".venv" / "bin" / "python"
    if not api_py.exists():
        check("server/.venv 存在（可校验接口层 import）", False, str(api_py))
        return
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app import colorcal as cc\n"
        "assert cc.TARGET_RGB == (201, 80, 33), cc.TARGET_RGB\n"
        "assert cc.WHITE_RGB == (255, 255, 255), cc.WHITE_RGB\n"
        "assert abs(cc.delta_e2000((206,130,110),(201,80,33)) - %.6f) < 1e-6\n"
        "aff = cc.affine_for((206,130,110),(234,224,200))\n"
        "assert len(aff['a']) == 3 and len(aff['b']) == 3\n"
        "g = cc.gains_for((206,130,110))\n"
        "assert g['clamped'] is True and 'b' in g['clamped_channels']\n"
        "wb = cc.whitebalance_gains_for((234,224,200))\n"
        "assert len(wb['gains']) == 3 and min(wb['gains']) >= 1.0 and wb['clamped'] is False\n"
        "c2 = cc.apply_gains_color((180,180,180), wb)\n"
        "assert len(c2) == 3\n"
        "c = cc.apply_affine_color((180,180,180), aff)\n"
        "assert len(c) == 3\n"
        "try:\n"
        "    import numpy\n"
        "    raise SystemExit('numpy 不应存在于接口层')\n"
        "except ImportError:\n"
        "    pass\n"
        "try:\n"
        "    cc.ink_mask([[1,2,3]])\n"
        "    raise SystemExit('像素函数应在无 numpy 时抛错')\n"
        "except RuntimeError:\n"
        "    pass\n"
        "print('API_OK')\n"
    ) % (str(REPO / "server"), cc.delta_e2000((206, 130, 110), (201, 80, 33)))
    r = subprocess.run([str(api_py), "-c", code], capture_output=True, text=True, cwd=str(REPO))
    ok = (r.returncode == 0) and ("API_OK" in r.stdout)
    check("接口层 server/.venv（无 numpy）可 import colorcal：常量 ✓ 色差 ✓ 仿射系数 ✓ 标量仿射 ✓ 像素函数抛错 ✓",
          ok, (r.stdout.strip() + r.stderr.strip())[-400:])


def main():
    print(f"colorcal 自检（V2 双锚点仿射 ＋ V1b 白平衡）  |  python={sys.executable}")
    print(f"repo={REPO}")
    test_ink_mask_basic()
    test_ciede2000()
    test_synthetic()
    test_paper_excludes_ink()
    test_v1b_whitebalance()
    test_degenerate()
    test_limiting()
    test_skip_ink_ratio()
    test_two_sided_import()
    n = len(RESULTS)
    npass = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 72)
    print(f"合计 {npass}/{n} PASS")
    if npass != n:
        print("FAILED:")
        for name, ok in RESULTS:
            if not ok:
                print("  - " + name)
        sys.exit(1)
    print("ALL PASS ✅")


if __name__ == "__main__":
    main()
