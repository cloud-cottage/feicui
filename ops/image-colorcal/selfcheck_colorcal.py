#!/usr/bin/env python
"""`app/colorcal.py` 自检（Kong 地基单 · 口径件 §2.2 / §4）。

跑法（**必须用 worker venv**，含 numpy/PIL）：
    /Users/kevin/bistro/xiai/feicui/venv/bin/python \
        /Users/kevin/bistro/xiai/feicui/ops/image-colorcal/selfcheck_colorcal.py

至少断言（与派单 ② 一一对应）：
  (a) `ciede2000_lab` 对 **Sharma, Wu & Dalal (2005)** 的 34 组业界已知 Lab 色对在容差 1e-4 内
      （`delta_e2000` 的 sRGB 入口共用同一核心，另附一组 sRGB 往返对照）；
  (b) 人工合成图（给定印泥色＋纸色）校正后**质心 → 靶色 ΔE2000 ≤ 2**（无 clamp ⇒ 应≈0）；
  (c) 纸区**色相偏移读数**（CA-2 口径，如实回报，不硬断零）；
  (d) `ink_ratio < 阈值` 走 `skipped` 分支、返回 `skipped(ink_ratio=…)` 标记、且图**未被改动**。
另附：`ink_mask` 逐像素判据、`apply_correction` 恒等性、两侧 import 形态（server/.venv 无 numpy）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

from app import colorcal as cc          # noqa: E402

RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(cond)))
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  | " + detail) if detail else ""))
    return bool(cond)


# ======================================================================================
# (a) CIEDE2000 业界已知色对（Sharma et al. 2005 官方 34 组补充测试数据）
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


def test_ciede2000():
    print("\n=== (a) CIEDE2000 业界已知色对（Sharma 2005 官方 34 组）===")
    worst = 0.0
    worst_i = -1
    for i, (L1, a1, b1, L2, a2, b2, exp) in enumerate(SHARMA_PAIRS, 1):
        got = cc.ciede2000_lab((L1, a1, b1), (L2, a2, b2))
        err = abs(got - exp)
        if err > worst:
            worst, worst_i = err, i
        if err > 1e-4:
            print(f"      pair#{i}: got={got:.6f} exp={exp:.4f} err={err:.2e}")
    check("ciede2000_lab: 34/34 Sharma 色对 |Δ| ≤ 1e-4",
          worst <= 1e-4, f"最大误差={worst:.2e} @pair#{worst_i}")
    # sRGB 入口（共用同一核心）：全等色 ⇒ 0；黑↔白 ⇒ 100（L 差）
    check("delta_e2000(rgb,rgb) == 0", abs(cc.delta_e2000((201, 80, 33), (201, 80, 33))) < 1e-9)
    de_bw = cc.delta_e2000((0, 0, 0), (255, 255, 255))
    check("delta_e2000(黑,白) ≈ 100", abs(de_bw - 100.0) < 1.0, f"= {de_bw:.4f}")
    # 已知色对：目标色 vs 现图典型印泥均值 rgb(206,130,110) 的 ΔE（口径件 §1.2 读数）
    de_typ = cc.delta_e2000((206, 130, 110), cc.TARGET_RGB)
    print(f"      [读数] ΔE2000(典型印泥均值 (206,130,110) , 靶色 #C95021) = {de_typ:.4f}")


# ======================================================================================
# (b) / (c) 人工合成图：给定印泥色 ＋ 纸色
# ======================================================================================
PAPER_RGB = (234, 224, 200)   # 纸色（暖白、低饱和 ⇒ 原图不入选印泥掩膜）
INK_RGB = (200, 95, 45)       # 印泥色（偏淡红橙：需提饱和才到 #C95021，且增益仍在 [0.5,2.0]）


def make_synthetic(ink_ratio: float, h: int = 240, w: int = 240) -> "np.ndarray":
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = PAPER_RGB
    side = int(round((ink_ratio * h * w) ** 0.5))
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    img[y0:y0 + side, x0:x0 + side] = INK_RGB
    return img


def test_ink_mask_basic():
    print("\n=== 附：ink_mask 逐像素判据（§2.2.1）===")
    px = np.array([[[201, 80, 33],      # 靶色：r>g+15✓ r>b+15✓ S=0.836✓ ⇒ 入选
                    [234, 224, 200],    # 纸：r-b=34✓ 但 S=0.145✗ ⇒ 不入选
                    [206, 130, 110],    # 典型印泥：r-g=76✓ r-b=96✓ S=0.466✓ ⇒ 入选
                    [200, 190, 180],    # 近中性：S=0.10✗ ⇒ 不入选
                    [60, 40, 20],       # 暗印泥：r-g=20✓ r-b=40✓ S=0.667✓ ⇒ 入选
                    [0, 0, 0]]], np.uint8)   # 纯黑：S 记 0 ⇒ 不入选
    m = cc.ink_mask(px)[0]
    check("ink_mask 靶色/纸/印泥/中性/暗/黑 = T,F,T,F,T,F",
          list(m) == [True, False, True, False, True, False], f"mask={list(m)}")


def test_synthetic():
    print("\n=== (b)/(c) 人工合成图（印泥 %s ＋ 纸 %s）===" % (INK_RGB, PAPER_RGB))
    img = make_synthetic(0.25)
    c_before, ratio = cc.ink_centroid(img)
    print(f"      原图：印泥占比={ratio:.4f}  质心={tuple(round(x,1) for x in c_before)}  "
          f"HSV={tuple(round(x,3) for x in cc.rgb_to_hsv(c_before))}")
    de_before = cc.delta_e2000(c_before, cc.TARGET_RGB)

    corrected, rep = cc.correct_image(img, target=cc.TARGET_RGB)

    print(f"      mark={rep['marker']}  gains={tuple(round(x,4) for x in rep['gains'])}  "
          f"raw={tuple(None if x is None else round(x,4) for x in rep['raw_gains'])}  "
          f"clamped={rep['clamped']}{rep['clamped_channels']}")
    print(f"      校正前质心={tuple(round(x,1) for x in rep['centroid_before'])} ΔE={de_before:.4f}")
    print(f"      校正后质心={tuple(round(x,1) for x in rep['centroid_after'])} "
          f"ΔE={rep['delta_e_after']:.4f}")

    check("(b) 合成图校正后 质心→靶色 ΔE2000 ≤ 2",
          rep["delta_e_after"] is not None and rep["delta_e_after"] <= 2.0,
          f"ΔE_after={rep['delta_e_after']:.4f}（前 {de_before:.4f}）")
    check("(b) 校正确实降低 ΔE（后 < 前）", rep["delta_e_after"] < de_before)
    check("(b) 合成案例未触发 clamp（增益都在 [0.5,2.0]）", rep["clamped"] is False)

    # (c) 纸区色相偏移读数
    print(f"      [读数] 纸区色相：前 {rep['paper_hue_before']:.3f}° → 后 "
          f"{rep['paper_hue_after']:.3f}°  偏移 {rep['paper_hue_shift']:+.3f}° "
          f"(纸像素 {rep['paper_pixels']})")
    check("(c) 纸区色相偏移为有限读数（如实回报，不硬断零）",
          rep["paper_hue_shift"] is not None and abs(rep["paper_hue_shift"]) < 180.0,
          f"{rep['paper_hue_shift']:+.3f}°")

    # 恒等性：全等增益不改图；白点在校正后为同一变换
    white = np.full((8, 8, 3), 255, np.uint8)
    same = np.array_equal(cc.apply_correction(white, (1.0, 1.0, 1.0)), white)
    check("apply_correction(k=1,1,1) 恒等（白 255 保持）", same)


def test_skip():
    print("\n=== (d) 低印泥占比 → skipped 分支 ===")
    img = make_synthetic(0.01)                    # ≈1% < 2%
    corr, rep = cc.correct_image(img, target=cc.TARGET_RGB, ink_ratio_min=0.02)
    print(f"      ink_ratio={rep['ink_ratio']:.4f}  mode={rep['mode']}  marker={rep['marker']}")
    check("(d) mode == 'skipped'", rep["mode"] == "skipped")
    check("(d) marker 形如 skipped(ink_ratio=…)",
          isinstance(rep["marker"], str) and rep["marker"].startswith("skipped(ink_ratio=")
          and rep["marker"].endswith(")"))
    check("(d) 图未被改动（逐字节相等）", np.array_equal(corr, img))
    check("(d) delta_e_after == delta_e_before（未校正）",
          rep["delta_e_after"] == rep["delta_e_before"])
    # 边界：阈值以上走 applied
    img_ok = make_synthetic(0.03)
    _, rep_ok = cc.correct_image(img_ok, ink_ratio_min=0.02)
    check("(d) 3% > 阈值 ⇒ applied", rep_ok["mode"] == "applied")


# ======================================================================================
# 两侧 import 形态（口径件 §2.5 红线 3：两侧共用同一份实现）
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
        "assert abs(cc.delta_e2000((206,130,110),(201,80,33)) - %.6f) < 1e-6\n"
        "g = cc.gains_for((206,130,110))\n"
        "assert g['clamped'] is True and 'b' in g['clamped_channels']\n"
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
    ) % (str(REPO / "server"), cc.delta_e2000((206, 130, 110), cc.TARGET_RGB))
    r = subprocess.run([str(api_py), "-c", code], capture_output=True, text=True, cwd=str(REPO))
    ok = (r.returncode == 0) and ("API_OK" in r.stdout)
    check("接口层 server/.venv（无 numpy）可 import colorcal：常量 ✓ 色差 ✓ 增益 ✓ 像素函数抛错 ✓",
          ok, (r.stdout.strip() + r.stderr.strip())[-400:])


def main():
    print(f"colorcal 自检  |  python={sys.executable}")
    print(f"repo={REPO}")
    test_ink_mask_basic()
    test_ciede2000()
    test_synthetic()
    test_skip()
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
