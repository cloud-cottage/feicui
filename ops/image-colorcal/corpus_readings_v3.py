#!/usr/bin/env python
"""`app/colorcal.py` 语料实测读数 —— **V3 双色分层处理（默认）** vs **V1a 双锚点仿射** vs **V1b 纸白平衡**
（Kong 地基单 · V3 · 派单 ⑤）。

跑法（**只读**，用 worker venv）：
    /Users/kevin/bistro/xiai/feicui/venv/bin/python \
        /Users/kevin/bistro/xiai/feicui/ops/image-colorcal/corpus_readings_v3.py

抽样方式（**确定性、可复现、与 V1a/V1b 同口径**）：对 `var/seal_images_tiff/**/*.tiff` 全 N 件
**按路径排序**后取 **等距系统抽样** `idx_i = round(i·N/n)`（`i=0..n-1`，`n=120`）。**只读**。

每张给：前景核心 ΔE→`#C95021`（前/后）、背景→`#FFFFFF` 的 ΔE（前/后）、前景掩膜 IoU、`L*` 保持读数、
三桶像素占比、`other` 桶不变率、跳过分桶计数。输出 `ops/image-colorcal/corpus_readings_v3.json`。
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

from app import colorcal as cc          # noqa: E402

OUT = Path(__file__).resolve().parent / "corpus_readings_v3.json"
TIFF_GLOB = str(REPO / "var" / "seal_images_tiff" / "**" / "*.tiff")
N_SAMPLE = 120


def pct(vals, q):
    vals = [float(v) for v in vals if v is not None]
    return float(np.percentile(np.asarray(vals), q)) if vals else None


def dist(vals):
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": min(vals), "p05": pct(vals, 5), "p25": pct(vals, 25),
            "p50": pct(vals, 50), "p75": pct(vals, 75), "p90": pct(vals, 90), "p95": pct(vals, 95),
            "max": max(vals), "mean": float(np.mean(vals))}


def med3(rows, getter):
    vals = [getter(r) for r in rows]
    vals = [v for v in vals if v]
    if not vals:
        return None
    return [float(np.median([v[i] for v in vals])) for i in range(3)]


def main():
    paths = sorted(glob.glob(TIFF_GLOB, recursive=True))
    N = len(paths)
    n = min(N_SAMPLE, N)
    idx = sorted({min(int(round(i * N / n)), N - 1) for i in range(n)})
    sample = [paths[i] for i in idx]
    print(f"全量 N={N}；抽样 n={len(sample)}（等距系统抽样 idx=round(i*N/n)，与 V1a/V1b 同口径）")

    rows = []
    load_err = 0
    for j, p in enumerate(sample):
        try:
            with Image.open(p) as im:
                arr = np.asarray(im.convert("RGB"))
        except Exception as e:  # 只读语料，异常只记不吞
            load_err += 1
            rows.append({"path": os.path.relpath(p, REPO), "error": f"{type(e).__name__}: {e}"})
            continue

        # --- V3（默认口径）---
        out3, r3 = cc.correct_image_v3(arr)
        # --- V1a（双锚点仿射）---
        out_a, r_a = cc.correct_image(arr)
        # --- V1b（纸白平衡）---
        out_b, r_b = cc.correct_image_whitebalance(arr)

        rows.append({
            "path": os.path.relpath(p, REPO), "sha": os.path.basename(p)[:-5],
            "wh": [int(arr.shape[1]), int(arr.shape[0])],
            "ink_ratio": r3["ink_ratio"], "paper_ratio": r3["paper_ratio"], "other_ratio": r3["other_ratio"],
            "centroid_core_before": r3["centroid_core_before"],
            "delta_e_core_before": r3["delta_e_before"],
            "paper_before": r3["paper_before_rgb"],
            "v3": {
                "mode": r3["mode"], "marker": r3["marker"], "skip_reason": r3["skip_reason"],
                "centroid_core_after": r3["centroid_core_after"],
                "delta_e_core_after": r3["delta_e_after"],
                "paper_after": r3["paper_after_rgb"],
                "bg_de_before": r3["bg_delta_e_before"], "bg_de_after": r3["bg_delta_e_after"],
                "iou": r3["iou"], "iou_raw": r3["iou_raw"],
                "mask_reverted_rate": r3["mask_reverted_rate"],
                "lstar_before": r3["lstar_before"], "lstar_after": r3["lstar_after"],
                "lstar_mean_delta": r3["lstar_mean_delta"],
                "lstar_p50_delta": r3["lstar_p50_delta"], "lstar_p90_delta": r3["lstar_p90_delta"],
                "other_unchanged_rate": r3["other_unchanged_rate"],
                "fg_gamut_clip_rate": r3["fg_gamut_clip_rate"],
                "other_pixels": r3["other_pixels"], "core_pixels": r3["core_pixels"],
            },
            "v1a": {
                "mode": r_a["mode"], "marker": r_a["marker"], "skip_reason": r_a["skip_reason"],
                "delta_e_core_after": r_a["delta_e_after"],
                "bg_de_after": r_a["paper_delta_e_after"],
                "gray180_after": (list(r_a["gray180_after"]) if r_a.get("gray180_after") else None),
            },
            "v1b": {
                "mode": r_b["mode"], "marker": r_b["marker"], "skip_reason": r_b["skip_reason"],
                "delta_e_core_after": r_b["delta_e_after"],
                "bg_de_after": r_b["paper_delta_e_after"],
                "gray180_after": (list(r_b["gray180_after"]) if r_b.get("gray180_after") else None),
            },
        })
        if (j + 1) % 30 == 0:
            print(f"  ... {j + 1}/{len(sample)}")

    ok = [r for r in rows if "error" not in r]

    def block(side, applied_only_de=True):
        applied = [r for r in ok if r[side]["mode"] == "applied"]
        skipped = [r for r in ok if r[side]["mode"] == "skipped"]
        buckets = {}
        for r in skipped:
            buckets[r[side]["skip_reason"]] = buckets.get(r[side]["skip_reason"], 0) + 1
        return applied, skipped, buckets

    def core_hits(applied, side, thr):
        return sum(1 for r in applied if (r[side]["delta_e_core_after"] or 9e9) <= thr)

    a_applied, a_skip, a_buckets = block("v1a")
    b_applied, b_skip, b_buckets = block("v1b")
    v3_applied, v3_skip, v3_buckets = block("v3")

    def side_summary(side, applied, skip, buckets):
        return {
            "counts": {
                "sampled_ok": len(ok), "applied": len(applied), "skipped": len(skip),
                "skip_rate": len(skip) / len(ok) if ok else None, "skip_buckets": buckets,
            },
            "delta_e_core_before": dist([r["delta_e_core_before"] for r in ok]),
            "delta_e_core_after_applied": dist([r[side]["delta_e_core_after"] for r in applied]),
            "bg_de_after_applied": dist([r[side]["bg_de_after"] for r in applied]),
            "delta_e_core_le2": core_hits(applied, side, 2.0),
            "delta_e_core_le5": core_hits(applied, side, 5.0),
            "gray180_after_median_applied": med3(applied, lambda r: r[side].get("gray180_after")),
        }

    res = {
        "generated_by": "ops/image-colorcal/corpus_readings_v3.py",
        "algorithms": {"v3": "dual-layer-v3 (默认)", "v1a": "affine-2anchor", "v1b": "whitebalance-diagonal"},
        "target": {"rgb": list(cc.TARGET_RGB), "hex": cc.TARGET_HEX},
        "white": {"rgb": list(cc.WHITE_RGB), "hex": "#FFFFFF"},
        "v3_params": {
            "light_v_min": cc.V3_LIGHTNESS_V_MIN, "fg_chroma_strength": cc.V3_FG_CHROMA_STRENGTH,
            "paper_mode": cc.V3_PAPER_MODE, "clean": cc.V3_CLEAN, "fg_preserve_mask": cc.V3_FG_PRESERVE_MASK,
            "ink_ratio_min": cc.INK_RATIO_MIN,
        },
        "corpus": {"glob": "var/seal_images_tiff/**/*.tiff", "N_total": N, "n_sampled": len(sample),
                   "sampling": "按路径排序后等距系统抽样 idx=round(i*N/n)，n=120（与 V1a/V1b 同口径）",
                   "load_errors": load_err},
        "v3": {
            **side_summary("v3", v3_applied, v3_skip, v3_buckets),
            "v3_specific": {
                "iou_applied": dist([r["v3"]["iou"] for r in v3_applied]),
                "iou_raw_applied": dist([r["v3"]["iou_raw"] for r in v3_applied]),
                "iou_lt_098_raw": sum(1 for r in v3_applied if r["v3"]["iou_raw"] < cc.V3_FG_IOU_MIN),
                "lstar_mean_delta_applied": dist([r["v3"]["lstar_mean_delta"] for r in v3_applied]),
                "lstar_p90_delta_applied": dist([r["v3"]["lstar_p90_delta"] for r in v3_applied]),
                "other_unchanged_rate_applied": dist([r["v3"]["other_unchanged_rate"] for r in v3_applied]),
                "other_unchanged_all_100pct": all(
                    (r["v3"]["other_unchanged_rate"] == 1.0) for r in (v3_applied + v3_skip)),
                "fg_gamut_clip_rate_applied": dist([r["v3"]["fg_gamut_clip_rate"] for r in v3_applied]),
                "mask_reverted_rate_applied": dist([r["v3"]["mask_reverted_rate"] for r in v3_applied]),
                "ink_ratio_median_all": pct([r["ink_ratio"] for r in ok], 50),
                "paper_ratio_median_all": pct([r["paper_ratio"] for r in ok], 50),
                "other_ratio_median_all": pct([r["other_ratio"] for r in ok], 50),
                "bucket_ratios_median_applied": med3(v3_applied, lambda r: (r["ink_ratio"], r["paper_ratio"], r["other_ratio"])),
            },
        },
        "v1a": side_summary("v1a", a_applied, a_skip, a_buckets),
        "v1b": side_summary("v1b", b_applied, b_skip, b_buckets),
        "samples_detail": v3_applied[:5],
        "rows": rows,
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

    # ---------------- 人读汇总 ----------------
    def f3(d):
        return " ".join(f"{k}={d[k]:.2f}" for k in ("p50", "p90", "max") if d.get("n"))

    print("\n" + "=" * 96)
    print(f"抽样 {len(ok)} 件（load_err={load_err}）")
    print("\n【V3 三桶占比（全体中位）】"
          f" ink={res['v3']['v3_specific']['ink_ratio_median_all']*100:.1f}%"
          f" paper={res['v3']['v3_specific']['paper_ratio_median_all']*100:.1f}%"
          f" other={res['v3']['v3_specific']['other_ratio_median_all']*100:.1f}%")
    print("\n【skip 触发率 / 子因分桶】")
    for side, label in (("v3", "V3(双色分层)"), ("v1a", "V1a(双锚点仿射)"), ("v1b", "V1b(纸白平衡)")):
        c = res[side]["counts"]
        print(f"  {label:16} applied={c['applied']:3} skipped={c['skipped']:3} skip_rate={c['skip_rate']:.3f}"
              f"  分桶={c['skip_buckets']}")

    print("\n【★ 三口径对照表】（ΔE＝CIEDE2000；core＝核心质心→#C95021；bg＝背景→#FFFFFF）")
    hdr = f"{'指标':<34}{'V3(双色分层)':>22}{'V1a(双锚点)':>22}{'V1b(纸白平衡)':>22}"
    print(hdr)
    def g(side, key):
        return f3(res[side][key])
    print(f"{'ΔE_core 前(全体 ok)':<34}{g('v3','delta_e_core_before'):>22}{g('v1a','delta_e_core_before'):>22}{g('v1b','delta_e_core_before'):>22}")
    print(f"{'ΔE_core 后(applied)':<34}{g('v3','delta_e_core_after_applied'):>22}{g('v1a','delta_e_core_after_applied'):>22}{g('v1b','delta_e_core_after_applied'):>22}")
    print(f"{'bg→#FFFFFF ΔE 后(applied)':<34}{g('v3','bg_de_after_applied'):>22}{g('v1a','bg_de_after_applied'):>22}{g('v1b','bg_de_after_applied'):>22}")
    print(f"{'ΔE_core ≤2 / ≤5 命中(applied)':<34}"
          f"{str(res['v3']['delta_e_core_le2'])+'/'+str(len(v3_applied))+' , '+str(res['v3']['delta_e_core_le5'])+'/'+str(len(v3_applied)):>22}"
          f"{str(res['v1a']['delta_e_core_le2'])+'/'+str(len(a_applied))+' , '+str(res['v1a']['delta_e_core_le5'])+'/'+str(len(a_applied)):>22}"
          f"{str(res['v1b']['delta_e_core_le2'])+'/'+str(len(b_applied))+' , '+str(res['v1b']['delta_e_core_le5'])+'/'+str(len(b_applied)):>22}")
    print(f"{'中灰180 校正后(中位,applied)':<34}"
          f"{str(res['v3']['gray180_after_median_applied']):>22}{str(res['v1a']['gray180_after_median_applied']):>22}{str(res['v1b']['gray180_after_median_applied']):>22}")

    v3s = res["v3"]["v3_specific"]
    print("\n【V3 前景保真 / other 硬口径】")
    print(f"  前景 IoU(applied,含保形兜底): {f3(v3s['iou_applied'])}")
    print(f"  前景 IoU_raw(未兜底):        {f3(v3s['iou_raw_applied'])}  （<{cc.V3_FG_IOU_MIN}: {v3s['iou_lt_098_raw']}/{len(v3_applied)}）")
    print(f"  前景 L* 均值变化:            {f3(v3s['lstar_mean_delta_applied'])}")
    print(f"  前景 L* p90 变化:            {f3(v3s['lstar_p90_delta_applied'])}")
    print(f"  前景越色域裁剪率:            {f3(v3s['fg_gamut_clip_rate_applied'])}")
    print(f"  other 桶逐像素不变率:        {f3(v3s['other_unchanged_rate_applied'])}  ⇒ 全 100%: {v3s['other_unchanged_all_100pct']}")

    print("\n--- 抽样 5 张（V3 applied）逐张读数 ---")
    print(f"{'sha8':9}{'ink%':>7}{'pap%':>7}{'oth%':>7}  {'C_core前':>15}{'C_core后':>15}{'ΔE前':>7}{'ΔE后':>7}{'IoU':>8}{'L*Δ':>7}{'oth率':>7}")
    for r in v3_applied[:5]:
        c, cn = r["centroid_core_before"], r["v3"]["centroid_core_after"]
        cs = f"({c[0]:.0f},{c[1]:.0f},{c[2]:.0f})" if c else "None"
        cns = f"({cn[0]:.0f},{cn[1]:.0f},{cn[2]:.0f})" if cn else "None"
        print(f"{r['sha'][:8]:9}{r['ink_ratio']*100:6.1f}{r['paper_ratio']*100:7.1f}{r['other_ratio']*100:7.1f}  "
              f"{cs:>15}{cns:>15}{r['delta_e_core_before']:7.2f}{r['v3']['delta_e_core_after']:7.2f}"
              f"{r['v3']['iou']:8.4f}{r['v3']['lstar_mean_delta']:7.3f}{r['v3']['other_unchanged_rate']:7.4f}")
    print(f"\n写出 {OUT}")


if __name__ == "__main__":
    main()
