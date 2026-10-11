#!/usr/bin/env python
"""`app/colorcal.py` 自检 —— **V3 双色分层处理（默认口径）**（Kong 地基单 · V3）。

跑法（**必须用 worker venv**，含 numpy/PIL）：
    /Users/kevin/bistro/xiai/feicui/venv/bin/python \
        /Users/kevin/bistro/xiai/feicui/ops/image-colorcal/selfcheck_colorcal_v3.py

覆盖：派单 ④ 的 V3 断言 ＋ **Kevin 2026-10-11 已裁的硬口径**（`other` 桶逐像素不变）：
  (0) **既有自检全过**：子进程跑 `selfcheck_colorcal.py`（V1a 双锚点仿射 ＋ V1b 白平衡 ＋ **原有断言**）须 `ALL PASS`；
  (a) 合成图（纸 ＋ 淡红印 ＋ **黑墨字**）经 V3 后：
        **背景桶 → `#FFFFFF` 的 ΔE2000 ≤ 1**；**前景核心 → `#C95021` 的 ΔE2000 ≤ 2**；
        **黑墨（`other` 桶）像素逐字节不变**（不变率 100%）；
  (b) **前景保真**：前景掩膜前后 **IoU ≥ 0.98**（给读数）＋ 前景 `L*` 分布（均值 / p90）变化 ≤ 阈值；
  (c) 无印泥（`ink_ratio < 2%`）⇒ `skipped(ink_ratio=…)`、图未被改动；
  (d) 三桶互斥且穷尽整图；Lab 往返数值恒等；
  (e) **真样本**（120 抽样之一）：`other` 桶逐像素不变（不变率 100%）＋ IoU ≥ 0.98（给读数）。
另：解释「为何保 `L*` 必须配色域自适应」（V3 前景在 Lab 中只改色度、色度按 `L*` 裁到 sRGB 上限）。
"""
from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "server"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

from app import colorcal as cc          # noqa: E402

RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(cond)))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  | " + detail) if detail else ""))
    return bool(cond)


# 合成图：【纸】＋【淡红印（与靶色同明度、低色度）】＋【黑墨字（深色非印泥）】
PAPER_RGB = (234, 224, 200)          # 浅暖纸（非印泥、V=0.918 ≥ 0.70 ⇒ paper 桶）
INK_RGB = (162, 104, 82)             # 淡印泥（L*≈49.7 ≈ 靶色 L*≈49.8；S=0.49>0.25 ⇒ ink 桶）
BLACK_RGB = (20, 20, 20)             # 黑墨字（非印泥、V=0.078 < 0.70 ⇒ other 桶，须原样）


def make_synthetic(ink_ratio: float = 0.25, h: int = 240, w: int = 240):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = PAPER_RGB
    side = int(round((ink_ratio * h * w) ** 0.5))
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    img[y0:y0 + side, x0:x0 + side] = INK_RGB
    img[20:40, 20:100] = BLACK_RGB           # 黑墨字块（深色非印泥）
    return img


# ======================================================================================
# (0) 既有自检全过（不在本文件复制断言，直接跑既有脚本）
# ======================================================================================
def test_existing_selfcheck():
    print("\n=== (0) 既有自检 selfcheck_colorcal.py（V1a/V1b ＋ 原有断言）全过 ===")
    script = HERE / "selfcheck_colorcal.py"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(REPO))
    tail = [ln for ln in r.stdout.splitlines() if "合计" in ln]
    total = tail[-1].strip() if tail else "(无合计行)"
    ok = (r.returncode == 0) and ("ALL PASS" in r.stdout)
    check("既有自检 ALL PASS（原有断言全过）", ok, total)
    if not ok:
        print(r.stdout[-1500:])
        print(r.stderr[-800:])


# ======================================================================================
# (d) Lab 往返 + 三桶互斥穷尽
# ======================================================================================
def test_lab_roundtrip():
    print("\n=== (d) Lab 数组换算往返（sRGB→Lab→sRGB 恒等）===")
    rng = np.random.default_rng(0)
    px = rng.integers(0, 256, (4000, 3)).astype(np.uint8)
    back = cc._lab_to_srgb_arr(cc._srgb_to_lab_arr(px.astype(np.float64)))
    err = float(np.abs(np.clip(np.rint(back), 0, 255) - px).max())
    check("Lab 往返逐像素误差 = 0（数组↔标量同式）", err == 0.0, f"max|Δpx|={err:.0f}")


def test_buckets_partition():
    print("\n=== (d) V3 三桶：互斥且穷尽整图 ===")
    img = make_synthetic(0.25)
    bk = cc.v3_buckets(img)
    ink, paper, other = bk["ink"], bk["paper"], bk["other"]
    union_all = bool((ink | paper | other).all())
    disjoint = not bool((ink & paper).any() or (ink & other).any() or (paper & other).any())
    print(f"      ink={bk['ink_ratio']*100:.1f}% paper={bk['paper_ratio']*100:.1f}% other={bk['other_ratio']*100:.1f}%"
          f"（浅/深分界 V≥{cc.V3_LIGHTNESS_V_MIN}）")
    check("(d) 三桶互斥（两两不交）", disjoint)
    check("(d) 三桶穷尽整图（并集 = 全图）", union_all)


# ======================================================================================
# (a)(b) 合成图：背景→白 / 前景核心→靶色 / L* 保真 / IoU / other 不变（硬口径）
# ======================================================================================
def test_v3_synthetic():
    print(f"\n=== (a)(b) 合成图（纸 {PAPER_RGB} ＋ 淡印泥 {INK_RGB} ＋ 黑墨 {BLACK_RGB}）V3 ===")
    img = make_synthetic(0.25)
    out, rep = cc.correct_image_v3(img)
    bk = cc.v3_buckets(img)

    print(f"      mode={rep['mode']} marker={rep['marker']}  前景色度方向={rep['paper_mode']}"
          f"  三桶 前={rep['target_hex']}")
    print(f"      核心质心 前={tuple(round(x,1) for x in rep['centroid_core_before'])} ΔE={rep['delta_e_before']:.3f}"
          f" → 后={tuple(round(x,1) for x in rep['centroid_core_after'])} ΔE={rep['delta_e_after']:.4f}")
    print(f"      背景质心 前={tuple(round(x,1) for x in rep['paper_before_rgb'])} ΔE={rep['bg_delta_e_before']:.3f}"
          f" → 后={tuple(round(x,1) for x in rep['paper_after_rgb'])} ΔE={rep['bg_delta_e_after']:.4f}")
    print(f"      IoU={rep['iou']:.4f}  前景 L* 均值 Δ={rep['lstar_mean_delta']:.4f} p90 Δ={rep['lstar_p90_delta']:.4f}"
          f"  越色域裁剪率={rep['fg_gamut_clip_rate']:.4f}  other 不变率={rep['other_unchanged_rate']:.4f}")

    check("(a) 背景桶 → #FFFFFF 的 ΔE2000 ≤ 1",
          rep["bg_delta_e_after"] is not None and rep["bg_delta_e_after"] <= 1.0,
          f"ΔE={rep['bg_delta_e_after']:.4f}")
    check("(a) 背景像素 = 纯白 (255,255,255)，逐字节",
          bool((out[..., :3][bk["paper"]] == 255).all()))
    check("(a) 前景核心 → #C95021 的 ΔE2000 ≤ 2",
          rep["delta_e_after"] is not None and rep["delta_e_after"] <= 2.0,
          f"ΔE={rep['delta_e_after']:.4f}（前 {rep['delta_e_before']:.4f}）")

    # ★ Kevin 硬口径：other（深色非印泥）桶逐像素不变
    oth = bk["other"]
    eq = np.array_equal(out[..., :3][oth], img[..., :3][oth])
    check("★硬口径 other 桶像素逐像素不变（合成图·不变率）",
          eq and rep["other_unchanged_rate"] == 1.0,
          f"不变率={rep['other_unchanged_rate']*100:.2f}%（{int(oth.sum())} 像素）")
    check("★硬口径 黑墨字块逐字节不变", bool(np.array_equal(out[20:40, 20:100], img[20:40, 20:100])))

    check("(b) 前景掩膜前后 IoU ≥ 0.98", rep["iou"] >= cc.V3_FG_IOU_MIN, f"IoU={rep['iou']:.4f}")
    check("(b) 前景 L* 均值变化 ≤ 阈值(1.0)",
          rep["lstar_mean_delta"] is not None and rep["lstar_mean_delta"] <= cc.V3_LSTAR_MEAN_TOL,
          f"Δmean={rep['lstar_mean_delta']:.4f}")
    check("(b) 前景 L* p90 变化 ≤ 阈值(2.0)",
          rep["lstar_p90_delta"] is not None and rep["lstar_p90_delta"] <= cc.V3_LSTAR_P90_TOL,
          f"Δp90={rep['lstar_p90_delta']:.4f}")
    check("(b) 前景「保 L*」无越色域裁剪（裁剪率 = 0）",
          rep["fg_gamut_clip_rate"] == 0.0, f"clip_rate={rep['fg_gamut_clip_rate']:.4f}")


# ======================================================================================
# (c) 无印泥 ⇒ skipped(ink_ratio=…)
# ======================================================================================
def test_v3_skip():
    print("\n=== (c) 无印泥（ink_ratio < 2%）⇒ skipped(ink_ratio=…) ===")
    img = make_synthetic(0.01)
    out, rep = cc.correct_image_v3(img)
    print(f"      ink_ratio={rep['ink_ratio']:.4f}  mode={rep['mode']}  marker={rep['marker']}")
    check("(c) mode == 'skipped' 且 skip_reason == 'ink_ratio'",
          rep["mode"] == "skipped" and rep["skip_reason"] == "ink_ratio")
    check("(c) marker 形如 skipped(ink_ratio=…)",
          isinstance(rep["marker"], str) and rep["marker"].startswith("skipped(ink_ratio="))
    check("(c) 图未被改动（逐字节相等）", bool(np.array_equal(out, img)))


# ======================================================================================
# (e) 真样本：other 桶逐像素不变（硬口径）＋ IoU
# ======================================================================================
def test_v3_real_sample():
    print("\n=== (e) 真样本（120 等距系统抽样命中）V3：other 桶逐像素不变 ＋ IoU ===")
    paths = sorted(glob.glob(str(REPO / "var" / "seal_images_tiff" / "**" / "*.tiff"), recursive=True))
    if not paths:
        check("语料存在", False, "var/seal_images_tiff 未见 TIFF")
        return
    N = len(paths)
    n = 120
    idx = sorted({min(int(round(i * N / n)), N - 1) for i in range(n)})
    tested = 0
    rate_bad = 0
    iou_bad = 0
    for i in idx:
        arr = np.asarray(Image.open(paths[i]).convert("RGB"))
        out, rep = cc.correct_image_v3(arr)
        if rep["mode"] != "applied":
            continue
        bk = cc.v3_buckets(arr)
        oth = bk["other"]
        eqrate = rep["other_unchanged_rate"]
        byte_ok = bool(np.array_equal(out[..., :3][oth], arr[..., :3][oth])) if oth.any() else True
        if not (byte_ok and eqrate == 1.0):
            rate_bad += 1
        if rep["iou"] < cc.V3_FG_IOU_MIN:
            iou_bad += 1
        if tested < 3:
            print(f"      {Path(paths[i]).name[:8]} ink%={rep['ink_ratio']*100:5.1f} other%={rep['other_ratio']*100:5.2f}"
                  f" ΔEcore={rep['delta_e_after']:5.2f} IoU={rep['iou']:.4f}(raw {rep['iou_raw']:.4f})"
                  f" L*Δ={rep['lstar_mean_delta']:.3f} other不变率={eqrate:.4f} clip={rep['fg_gamut_clip_rate']:.4f}")
        tested += 1
    check(f"(e) 真样本 other 桶逐像素不变率 100%（{tested} 张 applied 全过）",
          tested > 0 and rate_bad == 0, f"违例 {rate_bad}/{tested}")
    check(f"(e) 真样本前景 IoU ≥ {cc.V3_FG_IOU_MIN}（{tested} 张 applied 全过）",
          tested > 0 and iou_bad == 0, f"违例 {iou_bad}/{tested}")


# ======================================================================================
# 附：背景去噪 / 形态学清理（可选；**只作用 paper 桶**）
# ======================================================================================
def test_v3_cleanup_options():
    print("\n=== 附：背景去噪 / 形态学清理（仅作用 paper 桶；可选）===")
    # v3_open3x3：大块 + 孤立点 ⇒ 只删孤立点，且结果 ⊆ 输入
    m = np.zeros((20, 20), bool)
    m[5:15, 5:15] = True
    m[2, 2] = True
    op = cc.v3_open3x3(m)
    check("v3_open3x3 结果 ⊆ 输入（只删、绝不新增 ⇒ 不会把非纸像素变白）",
          int((op & ~m).sum()) == 0)
    check("v3_open3x3 删孤立点、保留大块", (not bool(op[2, 2])) and bool(op[10, 10]))

    img = make_synthetic(0.25)
    bk = cc.v3_buckets(img)
    oth = bk["other"]

    out_c, rep_c = cc.correct_image_v3(img, clean=True)
    check("clean=True：other 桶仍逐像素不变（硬口径）",
          rep_c["other_unchanged_rate"] == 1.0 and bool(np.array_equal(out_c[..., :3][oth], img[..., :3][oth])))
    check("clean=True：背景仍向 #FFFFFF 靠（ΔE ≤ 1）",
          rep_c["bg_delta_e_after"] is not None and rep_c["bg_delta_e_after"] <= 1.0,
          f"ΔE={rep_c['bg_delta_e_after']:.4f} 移除纸点={rep_c['bg_cleaned_removed']}")

    out_k, rep_k = cc.correct_image_v3(img, paper_mode="curve")
    check("curve 模式（抬亮曲线 ＋ 中值去噪）可用且 other 不变",
          rep_k["mode"] == "applied" and rep_k["other_unchanged_rate"] == 1.0)
    med = cc.v3_median3x3(img)
    check("v3_median3x3 输出同 shape/dtype",
          med.shape == img.shape and med.dtype == img.dtype)


def main():
    print(f"colorcal V3 自检（双色分层处理：前景保 L* / 背景压平 / other 保留原样）  |  python={sys.executable}")
    print(f"repo={REPO}")
    test_existing_selfcheck()
    test_lab_roundtrip()
    test_buckets_partition()
    test_v3_synthetic()
    test_v3_skip()
    test_v3_cleanup_options()
    test_v3_real_sample()
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
