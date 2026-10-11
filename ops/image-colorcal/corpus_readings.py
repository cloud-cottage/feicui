#!/usr/bin/env python
"""`app/colorcal.py` 语料实测读数（Kong 地基单 · 派单 ③）。

跑法（**只读**，用 worker venv）：
    /Users/kevin/bistro/xiai/feicui/venv/bin/python \
        /Users/kevin/bistro/xiai/feicui/ops/image-colorcal/corpus_readings.py

抽样方式（**确定性、可复现**）：对 `var/seal_images_tiff/**/*.tiff` 全 6347 件**按路径排序**后，
取 **等距系统抽样** `idx_i = round(i·N/n)`（`i=0..n-1`，`n=120`）——覆盖首尾、跨 256 个 sha 前缀目录。
**只读**：不写 TIFF、不写 DB、不建 job。

输出：`ops/image-colorcal/corpus_readings.json`（**聚合 ＋ 逐张抽样**，不 dump 全量 6347）。
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

OUT = Path(__file__).resolve().parent / "corpus_readings.json"
TIFF_GLOB = str(REPO / "var" / "seal_images_tiff" / "**" / "*.tiff")
N_SAMPLE = 120


def pct(vals, q):
    if not vals:
        return None
    return float(np.percentile(np.asarray(vals, dtype=np.float64), q))


def dist(vals):
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "min": min(vals), "p05": pct(vals, 5), "p25": pct(vals, 25),
        "p50": pct(vals, 50), "p75": pct(vals, 75), "p90": pct(vals, 90), "p95": pct(vals, 95),
        "max": max(vals), "mean": float(np.mean(vals)),
    }


def main():
    paths = sorted(glob.glob(TIFF_GLOB, recursive=True))
    N = len(paths)
    n = min(N_SAMPLE, N)
    idx = sorted({min(int(round(i * N / n)), N - 1) for i in range(n)})
    sample = [paths[i] for i in idx]
    print(f"全量 N={N}；抽样 n={len(sample)}（等距系统抽样 idx=round(i*N/n)）")

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
        _, rep = cc.correct_image(arr, target=cc.TARGET_RGB, ink_ratio_min=cc.INK_RATIO_MIN)
        cb = rep["centroid_before"]
        hsv = cc.rgb_to_hsv(cb) if cb else None
        # counterfactual：只 clamp 上限（放开下限 k_min）—— 量「下限 clamp 是否为未达标阻因」
        de_after_nolow = None
        if rep["mode"] == "applied":
            raw = [1e-6 if k is None else k for k in rep["raw_gains"]]
            gains_cf = tuple(min(max(k, 1e-6), cc.K_MAX) for k in raw)
            mask = cc.ink_mask(arr)
            corr_cf = cc.apply_correction(arr, gains_cf)
            c_cf = cc.region_mean_rgb(corr_cf, mask)
            de_after_nolow = cc.delta_e2000(c_cf, cc.TARGET_RGB) if c_cf else None
        rows.append({
            "path": os.path.relpath(p, REPO),
            "sha": os.path.basename(p)[:-5],
            "wh": [int(arr.shape[1]), int(arr.shape[0])],
            "ink_ratio": rep["ink_ratio"],
            "ink_ratio_after": rep.get("ink_ratio_after"),
            "centroid_before": cb,
            "centroid_after": rep.get("centroid_after"),
            "centroid_hsv": hsv,
            "mode": rep["mode"],
            "marker": rep["marker"],
            "clamped": rep["clamped"],
            "clamped_channels": rep["clamped_channels"],
            "gains": list(rep["gains"]) if rep["gains"] else None,
            "raw_gains": list(rep["raw_gains"]) if rep.get("raw_gains") else None,
            "delta_e_before": rep["delta_e_before"],
            "delta_e_after": rep["delta_e_after"],
            "delta_e_after_no_kmin": de_after_nolow,
            "paper_hue_before": rep.get("paper_hue_before"),
            "paper_hue_after": rep.get("paper_hue_after"),
            "paper_hue_shift": rep.get("paper_hue_shift"),
            "paper_pixels": rep.get("paper_pixels"),
        })
        if (j + 1) % 30 == 0:
            print(f"  ... {j + 1}/{len(sample)}")

    ok = [r for r in rows if "error" not in r]
    applied = [r for r in ok if r["mode"] == "applied"]
    skipped = [r for r in ok if r["mode"] == "skipped"]
    clamped = [r for r in applied if r["clamped"]]

    hsv = [r["centroid_hsv"] for r in ok if r["centroid_hsv"]]
    ch = {"h": [v[0] for v in hsv], "s": [v[1] for v in hsv], "v": [v[2] for v in hsv]}
    raw_r = [r["raw_gains"][0] for r in applied if r.get("raw_gains") and r["raw_gains"][0] is not None]
    raw_g = [r["raw_gains"][1] for r in applied if r.get("raw_gains") and r["raw_gains"][1] is not None]
    raw_b = [r["raw_gains"][2] for r in applied if r.get("raw_gains") and r["raw_gains"][2] is not None]

    res = {
        "generated_by": "ops/image-colorcal/corpus_readings.py",
        "target": {"rgb": list(cc.TARGET_RGB), "hex": cc.TARGET_HEX},
        "params": {"k_min": cc.K_MIN, "k_max": cc.K_MAX, "ink_ratio_min": cc.INK_RATIO_MIN},
        "corpus": {
            "glob": "var/seal_images_tiff/**/*.tiff",
            "N_total": N,
            "n_sampled": len(sample),
            "sampling": "按路径排序后等距系统抽样 idx=round(i*N/n)，n=120，覆盖首尾",
            "load_errors": load_err,
        },
        "aggregates": {
            "counts": {
                "sampled_ok": len(ok), "applied": len(applied), "skipped": len(skipped),
                "clamped": len(clamped),
                "skip_rate": (len(skipped) / len(ok)) if ok else None,
                "clamp_rate_of_applied": (len(clamped) / len(applied)) if applied else None,
                "clamp_rate_of_all": (len(clamped) / len(ok)) if ok else None,
            },
            "ink_ratio": dist([r["ink_ratio"] for r in ok]),
            "ink_ratio_after": dist([r["ink_ratio_after"] for r in ok]),
            "centroid_hsv": {k: dist(v) for k, v in ch.items()},
            "delta_e_before": dist([r["delta_e_before"] for r in ok if r["delta_e_before"] is not None]),
            "delta_e_after_applied": dist([r["delta_e_after"] for r in applied if r["delta_e_after"] is not None]),
            "delta_e_after_no_kmin_applied": dist([
                r["delta_e_after_no_kmin"] for r in applied if r["delta_e_after_no_kmin"] is not None
            ]),
            "delta_e_improvement_applied": dist([
                (r["delta_e_before"] - r["delta_e_after"])
                for r in applied if r["delta_e_before"] is not None and r["delta_e_after"] is not None
            ]),
            "paper_hue_shift_deg_applied": dist([
                r["paper_hue_shift"] for r in applied if r["paper_hue_shift"] is not None
            ]),
            "paper_hue_shift_deg_all": dist([r["paper_hue_shift"] for r in ok if r["paper_hue_shift"] is not None]),
            "raw_gains_applied": {"r": dist(raw_r), "g": dist(raw_g), "b": dist(raw_b)},
            "clamped_channel_hits": {
                "r": sum(1 for r in applied if "r" in r["clamped_channels"]),
                "g": sum(1 for r in applied if "g" in r["clamped_channels"]),
                "b": sum(1 for r in applied if "b" in r["clamped_channels"]),
            },
            "CA1_like": {
                "note": "口径件 §4 CA-1 候选：未跳过行 校正后质心→靶色 ΔE2000 ≤ 5 的占比",
                "le5": sum(1 for r in applied if (r["delta_e_after"] or 9e9) <= 5),
                "le2": sum(1 for r in applied if (r["delta_e_after"] or 9e9) <= 2),
                "of_applied": len(applied),
                "no_kmin_le5": sum(1 for r in applied if (r["delta_e_after_no_kmin"] or 9e9) <= 5),
                "no_kmin_le2": sum(1 for r in applied if (r["delta_e_after_no_kmin"] or 9e9) <= 2),
            },
        },
        "samples_detail": applied[:5],
        "extremes": {
            "max_ink_ratio": max(ok, key=lambda r: r["ink_ratio"])["path"] if ok else None,
            "max_ink_ratio_value": max((r["ink_ratio"] for r in ok), default=None),
            "min_nonzero_ink_ratio": min((r["ink_ratio"] for r in ok if r["ink_ratio"] > 0), default=None),
        },
        "rows": rows,
    }

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("\n" + "=" * 72)
    a = res["aggregates"]
    print(f"抽样 {len(ok)} 件：applied={len(applied)} skip={len(skipped)} "
          f"clamped={len(clamped)} (clamp_rate/applied={a['counts']['clamp_rate_of_applied']:.3f}, "
          f"skip_rate={a['counts']['skip_rate']:.3f})")
    print(f"印泥占比    : p50={a['ink_ratio']['p50']:.4f}  [{a['ink_ratio']['min']:.4f}, "
          f"{a['ink_ratio']['max']:.4f}]")
    print(f"质心 HSV    : H p50={a['centroid_hsv']['h']['p50']:.1f}° "
          f"S p50={a['centroid_hsv']['s']['p50']:.3f} V p50={a['centroid_hsv']['v']['p50']:.3f}")
    print(f"ΔE 前       : p50={a['delta_e_before']['p50']:.3f} p90={a['delta_e_before']['p90']:.3f} "
          f"max={a['delta_e_before']['max']:.3f}")
    d = a["delta_e_after_applied"]
    print(f"ΔE 后(appl.): p50={d['p50']:.3f} p90={d['p90']:.3f} max={d['max']:.3f}")
    dn = a["delta_e_after_no_kmin_applied"]
    print(f"ΔE 后(放开下限 k_min 反事实) : p50={dn['p50']:.3f} p90={dn['p90']:.3f} max={dn['max']:.3f}")
    rg = a["raw_gains_applied"]
    print(f"raw 增益(前 clamp): r p50={rg['r']['p50']:.3f} g p50={rg['g']['p50']:.3f} b p50={rg['b']['p50']:.3f}")
    print(f"ΔE 改善(appl.): p50={a['delta_e_improvement_applied']['p50']:.3f}")
    ps = a["paper_hue_shift_deg_applied"]
    print(f"纸区色相偏移(applied): p50={ps['p50']:.2f}° p90={ps['p90']:.2f}° "
          f"max|{max(abs(ps['min']), abs(ps['max'])):.2f}|°")
    print(f"clamp 命中通道: {a['clamped_channel_hits']}")
    print(f"CA-1 候选 (≤5): {a['CA1_like']['le5']}/{a['CA1_like']['of_applied']}  (≤2: {a['CA1_like']['le2']})"
          f"   [放开下限: ≤5 → {a['CA1_like']['no_kmin_le5']}, ≤2 → {a['CA1_like']['no_kmin_le2']}]")

    print("\n--- 抽样 5 张（applied）逐张读数 ---")
    print(f"{'sha8':8} {'wh':11} {'ink%':>6} {'C_before':16} {'C_after':16} {'ΔE_bef':>7} {'ΔE_aft':>7} {'纸偏移°':>8}")
    for r in applied[:5]:
        c = r["centroid_before"]
        ca = r["centroid_after"]
        cs = f"({c[0]:.0f},{c[1]:.0f},{c[2]:.0f})" if c else "None"
        cas = f"({ca[0]:.0f},{ca[1]:.0f},{ca[2]:.0f})" if ca else "None"
        print(f"{r['sha'][:8]:8} {str(r['wh']):11} {r['ink_ratio']*100:6.2f} {cs:16} "
              f"{cas:16} {r['delta_e_before']:7.2f} {r['delta_e_after']:7.2f} "
              f"{r['paper_hue_shift']:8.2f}")
    print(f"\n写出 {OUT}")


if __name__ == "__main__":
    main()
