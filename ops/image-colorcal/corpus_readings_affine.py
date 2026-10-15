#!/usr/bin/env python
"""`app/colorcal.py` 语料实测读数 —— **V2 双锚点仿射 vs V1 对角增益 对照**（Kong 地基单 · 派单 ③）。

跑法（**只读**，用 worker venv）：
    /Users/kevin/bistro/feicui/venv/bin/python \
        /Users/kevin/bistro/feicui/ops/image-colorcal/corpus_readings_affine.py

抽样方式（**确定性、可复现、与上单同口径**）：对 `var/seal_images_tiff/**/*.tiff` 全 N 件
**按路径排序**后取 **等距系统抽样** `idx_i = round(i·N/n)`（`i=0..n-1`，`n=120`）。
**只读**：不写 TIFF、不写 DB、不建 job。

判据口径（务必区分，Zang 裁定）：
  * `ΔE_core_*`：**核心质心**（掩膜内饱和度 ≥ p75 的像素均值）→ `#C95021`——**CA-1 判据**，预期 ≈ 0。
  * `ΔE_all_*` ：掩膜**全体**质心 → `#C95021`——**仅观察项**（纸→纯白使全图变冷，全体质心会变差）。
  * `paper_de_white_*`：纸区质心（亮度 ≥ p90 均值）→ `#FFFFFF`——锚点①判据。
输出：`ops/image-colorcal/corpus_readings_affine.json`（**聚合 ＋ 逐张抽样**，不 dump 全量）。
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

OUT = Path(__file__).resolve().parent / "corpus_readings_affine.json"
TIFF_GLOB = str(REPO / "var" / "seal_images_tiff" / "**" / "*.tiff")
N_SAMPLE = 120


def pct(vals, q):
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return None
    return float(np.percentile(np.asarray(vals, dtype=np.float64), q))


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


def hue_shift(h_before, rgb_after):
    if rgb_after is None or h_before is None:
        return None
    h_a = cc.rgb_to_hsv(rgb_after)[0]
    return (h_a - h_before + 180.0) % 360.0 - 180.0


def paper_excl_ink_centroid(arr):
    """反事实用：纸区取『非印泥 ∧ 亮度 V ≥ p90(非印泥)』的均值（**非本口径**，仅供诊断）。"""
    m = cc.ink_mask(arr)
    rgb = arr[..., :3].astype(np.float64)
    v = rgb.max(axis=2) / 255.0
    nonink = ~m
    if int(nonink.sum()) == 0:
        return None
    thr = float(np.percentile(v[nonink], 90.0))
    pm = nonink & (v >= thr)
    if int(pm.sum()) == 0:
        return None
    return cc.region_mean_rgb(arr, pm)


def main():
    paths = sorted(glob.glob(TIFF_GLOB, recursive=True))
    N = len(paths)
    n = min(N_SAMPLE, N)
    idx = sorted({min(int(round(i * N / n)), N - 1) for i in range(n)})
    sample = [paths[i] for i in idx]
    print(f"全量 N={N}；抽样 n={len(sample)}（等距系统抽样 idx=round(i*N/n)，与上单同口径）")

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

        m_all = cc.ink_mask(arr)
        ratio = int(m_all.sum()) / (int(arr.shape[0]) * int(arr.shape[1]) or 1)
        core = cc.ink_core_centroid(arr)
        cmask = core["mask"]
        paper = cc.paper_centroid(arr)
        pmask = paper["mask"]
        c_core_before = core["rgb"]
        c_all_before = cc.region_mean_rgb(arr, m_all)
        paper_before = paper["rgb"]
        hue_pb = cc.rgb_to_hsv(paper_before)[0] if paper_before else None

        corr_new, rep_new = cc.correct_image(arr, target=cc.TARGET_RGB, white=cc.WHITE_RGB)
        corr_old, rep_old = cc.correct_image_diagonal(arr, target=cc.TARGET_RGB)

        def suite(corr):
            cc_a = cc.region_mean_rgb(corr, cmask)
            ca_a = cc.region_mean_rgb(corr, m_all)
            pw_a = cc.region_mean_rgb(corr, pmask)
            return {
                "centroid_core_after": cc_a, "centroid_all_after": ca_a, "paper_after": pw_a,
                "delta_e_core_after": cc.delta_e2000(cc_a, cc.TARGET_RGB) if cc_a else None,
                "delta_e_all_after": cc.delta_e2000(ca_a, cc.TARGET_RGB) if ca_a else None,
                "paper_de_white_after": cc.delta_e2000(pw_a, cc.WHITE_RGB) if pw_a else None,
                "paper_hue_shift": hue_shift(hue_pb, pw_a),
            }

        sn, so = suite(corr_new), suite(corr_old)

        gray_new = cc.apply_affine_color((180, 180, 180), rep_new) if rep_new["mode"] == "applied" else (180.0, 180.0, 180.0)
        if rep_old["mode"] == "applied" and rep_old.get("gains"):
            g = cc.apply_correction(np.array([[[180, 180, 180]]], np.uint8), rep_old["gains"])[0, 0]
            gray_old = (float(g[0]), float(g[1]), float(g[2]))
        else:
            gray_old = (180.0, 180.0, 180.0)

        # 反事实：纸区排除印泥像素（仅诊断，非本口径）
        W2 = paper_excl_ink_centroid(arr)
        cf = {"paper_rgb": W2, "mode": None, "skip_reason": None, "delta_e_core_after": None}
        if c_core_before and W2 and ratio >= cc.INK_RATIO_MIN:
            aff2 = cc.affine_for(c_core_before, W2, target=cc.TARGET_RGB, white=cc.WHITE_RGB)
            if aff2["degenerate"]:
                cf.update({"mode": "skipped", "skip_reason": aff2["degenerate_reason"]})
            else:
                corr2 = cc.apply_affine(arr, aff2)
                c2 = cc.region_mean_rgb(corr2, cmask)
                cf.update({"mode": "applied", "skip_reason": None,
                           "delta_e_core_after": cc.delta_e2000(c2, cc.TARGET_RGB) if c2 else None})

        rows.append({
            "path": os.path.relpath(p, REPO), "sha": os.path.basename(p)[:-5],
            "wh": [int(arr.shape[1]), int(arr.shape[0])], "ink_ratio": ratio,
            "core_pixels": core["pixels"], "core_sat_threshold": core["sat_threshold"],
            "centroid_core_before": c_core_before, "centroid_all_before": c_all_before,
            "paper_before": paper_before,
            "delta_e_core_before": cc.delta_e2000(c_core_before, cc.TARGET_RGB) if c_core_before else None,
            "new": {"mode": rep_new["mode"], "marker": rep_new["marker"], "skip_reason": rep_new["skip_reason"],
                    "a": list(rep_new["a"]) if rep_new["a"] else None,
                    "b": list(rep_new["b"]) if rep_new["b"] else None,
                    "raw_a": list(rep_new["raw_a"]) if rep_new["raw_a"] else None,
                    "raw_b": list(rep_new["raw_b"]) if rep_new["raw_b"] else None,
                    "clamped": rep_new["clamped"], "clamped_channels": rep_new["clamped_channels"],
                    "min_lin_component": rep_new["min_lin_component"],
                    "gray180_after": list(gray_new), **sn},
            "old": {"mode": rep_old["mode"], "marker": rep_old["marker"], "skip_reason": rep_old["skip_reason"],
                    "gains": list(rep_old["gains"]) if rep_old.get("gains") else None,
                    "clamped": rep_old.get("clamped"), "clamped_channels": rep_old.get("clamped_channels"),
                    "gray180_after": list(gray_old), **so},
            "counterfactual_paper_excl_ink": cf,
        })
        if (j + 1) % 30 == 0:
            print(f"  ... {j + 1}/{len(sample)}")

    ok = [r for r in rows if "error" not in r]

    def collect(side):
        applied = [r for r in ok if r[side]["mode"] == "applied"]
        skipped = [r for r in ok if r[side]["mode"] == "skipped"]
        buckets = {"ink_ratio": 0, "degenerate": 0, "limiting": 0}
        for r in skipped:
            buckets[r[side]["skip_reason"]] = buckets.get(r[side]["skip_reason"], 0) + 1
        return applied, skipped, buckets

    def side_block(side):
        applied, skipped, buckets = collect(side)
        return {
            "counts": {
                "sampled_ok": len(ok), "applied": len(applied), "skipped": len(skipped),
                "skip_rate": len(skipped) / len(ok) if ok else None,
                "skip_buckets": buckets,
                "skip_rate_ink_ratio": buckets.get("ink_ratio", 0) / len(ok) if ok else None,
                "skip_rate_degenerate": buckets.get("degenerate", 0) / len(ok) if ok else None,
                "skip_rate_limiting": buckets.get("limiting", 0) / len(ok) if ok else None,
                "clamped_applied": sum(1 for r in applied if r[side]["clamped"]),
                "clamped_rate_of_all": sum(1 for r in ok if r[side]["clamped"]) / len(ok) if ok else None,
            },
            "delta_e_core_before": dist([r["delta_e_core_before"] for r in ok]),
            "delta_e_core_after_applied": dist([r[side]["delta_e_core_after"] for r in applied]),
            "delta_e_all_after_applied": dist([r[side]["delta_e_all_after"] for r in applied]),
            "paper_de_white_after_applied": dist([r[side]["paper_de_white_after"] for r in applied]),
            "paper_hue_shift_applied": dist([r[side]["paper_hue_shift"] for r in applied]),
            "gray180_after_median_applied": med3(applied, lambda r: r[side]["gray180_after"]),
            "gray180_after_median_all": med3(ok, lambda r: r[side]["gray180_after"]),
            "paper_after_median_applied": med3(applied, lambda r: r[side]["paper_after"]),
        }

    new_block = side_block("new")
    old_block = side_block("old")
    new_applied, _, new_buckets = collect("new")
    old_applied, _, old_buckets = collect("old")

    na, oa = new_block, old_block
    a_ch = {c: dist([r["new"]["a"][i] for r in new_applied if r["new"]["a"]]) for i, c in enumerate("rgb")}
    b_ch = {c: dist([r["new"]["b"][i] for r in new_applied if r["new"]["b"]]) for i, c in enumerate("rgb")}

    cf_rows = [r for r in ok if r["counterfactual_paper_excl_ink"]["mode"]]
    cf_applied = [r for r in cf_rows if r["counterfactual_paper_excl_ink"]["mode"] == "applied"]
    cf_lim = sum(1 for r in cf_rows if r["counterfactual_paper_excl_ink"]["skip_reason"] == "limiting")
    cf_deg = sum(1 for r in cf_rows if r["counterfactual_paper_excl_ink"]["skip_reason"] == "degenerate")

    res = {
        "generated_by": "ops/image-colorcal/corpus_readings_affine.py",
        "algorithms": {"new": "affine-2anchor (V2)", "old": "diagonal-gain (V1, 兼容)"},
        "target": {"rgb": list(cc.TARGET_RGB), "hex": cc.TARGET_HEX},
        "white": {"rgb": list(cc.WHITE_RGB), "hex": "#FFFFFF"},
        "params": {"a_min": cc.A_MIN, "a_max": cc.A_MAX, "b_min": cc.B_MIN, "b_max": cc.B_MAX,
                   "paper_quantile": cc.PAPER_QUANTILE, "core_sat_quantile": cc.INK_CORE_SAT_QUANTILE,
                   "degenerate_min_lin": cc.DEGENERATE_MIN_LIN, "ink_ratio_min": cc.INK_RATIO_MIN,
                   "k_min_legacy": cc.K_MIN, "k_max_legacy": cc.K_MAX},
        "corpus": {"glob": "var/seal_images_tiff/**/*.tiff", "N_total": N, "n_sampled": len(sample),
                   "sampling": "按路径排序后等距系统抽样 idx=round(i*N/n)，n=120（与上单同口径）",
                   "load_errors": load_err},
        "new_affine": {**na, "a_by_channel": a_ch, "b_by_channel": b_ch,
                       "min_lin_component": dist([r["new"]["min_lin_component"] for r in ok]),
                       "paper_before_median_all": med3(ok, lambda r: r["paper_before"])},
        "old_diagonal": oa,
        "counterfactual_paper_excl_ink": {
            "note": "**非本口径**、仅供诊断：纸区取『非印泥 ∧ V≥p90(非印泥)』的均值。",
            "evaluated": len(cf_rows), "applied": len(cf_applied),
            "skip_limiting": cf_lim, "skip_degenerate": cf_deg,
            "limiting_rate_of_evaluated": cf_lim / len(cf_rows) if cf_rows else None,
            "delta_e_core_after_applied": dist([r["counterfactual_paper_excl_ink"]["delta_e_core_after"] for r in cf_applied]),
        },
        "comparison_core": {
            "note": "判定口径 ΔE_core（核心质心→#C95021）＋ paper_de_white（纸区质心→#FFFFFF）",
            "delta_e_core_after": {
                "new": {"p50": pct([r["new"]["delta_e_core_after"] for r in new_applied], 50),
                        "p90": pct([r["new"]["delta_e_core_after"] for r in new_applied], 90),
                        "max": max([r["new"]["delta_e_core_after"] for r in new_applied], default=None)},
                "old": {"p50": pct([r["old"]["delta_e_core_after"] for r in old_applied], 50),
                        "p90": pct([r["old"]["delta_e_core_after"] for r in old_applied], 90),
                        "max": max([r["old"]["delta_e_core_after"] for r in old_applied], default=None)}},
            "delta_e_core_after_le2_of_applied": {
                "new": sum(1 for r in new_applied if (r["new"]["delta_e_core_after"] or 9e9) <= 2),
                "old": sum(1 for r in old_applied if (r["old"]["delta_e_core_after"] or 9e9) <= 2)},
            "delta_e_core_after_le5_of_applied": {
                "new": sum(1 for r in new_applied if (r["new"]["delta_e_core_after"] or 9e9) <= 5),
                "old": sum(1 for r in old_applied if (r["old"]["delta_e_core_after"] or 9e9) <= 5)},
            "paper_de_white": {
                "new": {"p50": pct([r["new"]["paper_de_white_after"] for r in new_applied], 50),
                        "p90": pct([r["new"]["paper_de_white_after"] for r in new_applied], 90),
                        "max": max([r["new"]["paper_de_white_after"] for r in new_applied], default=None)},
                "old": {"p50": pct([r["old"]["paper_de_white_after"] for r in old_applied], 50),
                        "p90": pct([r["old"]["paper_de_white_after"] for r in old_applied], 90),
                        "max": max([r["old"]["paper_de_white_after"] for r in old_applied], default=None)}},
        },
        "samples_detail": new_applied[:5],
        "rows": rows,
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

    # ---------------- 人读汇总 ----------------
    def f3(d, ks=("p50", "p90", "max")):
        return " ".join(f"{k}={d[k]:.2f}" for k in ks)

    print("\n" + "=" * 92)
    print(f"抽样 {len(ok)} 件（load_err={load_err}）")
    print("【skip 触发率 / 子因分桶】")
    print(f"  新(仿射) applied={na['counts']['applied']} skip={na['counts']['skipped']} "
          f"skip_rate={na['counts']['skip_rate']:.3f}")
    print(f"           └ ink_ratio={new_buckets.get('ink_ratio',0)} ({na['counts']['skip_rate_ink_ratio']:.3f}) "
          f"| degenerate(病态)={new_buckets.get('degenerate',0)} ({na['counts']['skip_rate_degenerate']:.3f}) "
          f"| limiting(越界)={new_buckets.get('limiting',0)} ({na['counts']['skip_rate_limiting']:.3f})")
    print(f"  旧(对角) applied={oa['counts']['applied']} skip={oa['counts']['skipped']} "
          f"skip_rate={oa['counts']['skip_rate']:.3f}（全部 ink_ratio）  "
          f"clamp 率 applied=1.000")
    print("\n【新旧对照表】（ΔE＝CIEDE2000；core＝核心质心→#C95021；all＝全体质心-观察）")
    print(f"{'指标':<26}{'新(仿射)':>33}{'旧(对角)':>33}")
    print(f"{'ΔE_core 前(全体 ok)':<26}{f3(na['delta_e_core_before']):>33}{f3(oa['delta_e_core_before']):>33}")
    print(f"{'ΔE_core 后(applied)':<26}{f3(na['delta_e_core_after_applied']):>33}{f3(oa['delta_e_core_after_applied']):>33}")
    print(f"{'ΔE_all  后(applied,观察)':<26}{f3(na['delta_e_all_after_applied']):>33}{f3(oa['delta_e_all_after_applied']):>33}")
    print(f"{'纸→#FFFFFF ΔE 后(applied)':<26}{f3(na['paper_de_white_after_applied']):>33}{f3(oa['paper_de_white_after_applied']):>33}")
    print(f"{'纸区色相偏移°(applied)':<26}{f3(na['paper_hue_shift_applied']):>33}{f3(oa['paper_hue_shift_applied']):>33}")
    print("\n【a / b 实际取值分布（新，applied）】")
    for ch in "rgb":
        print(f"    {ch}: a p50={a_ch[ch]['p50']:.3f} p90={a_ch[ch]['p90']:.3f} max={a_ch[ch]['max']:.3f} | "
              f"b p50={b_ch[ch]['p50']:.1f} p90={b_ch[ch]['p90']:.1f} min={b_ch[ch]['min']:.1f}")
    print(f"    新越界通道命中: {sum(1 for r in ok if r['new']['clamped'])}/{len(ok)}")
    mlc = res["new_affine"]["min_lin_component"]
    print(f"    min|C−W|_lin: p50={mlc['p50']:.4f} p90={mlc['p90']:.4f} min={mlc['min']:.4f}（病态阈 {cc.DEGENERATE_MIN_LIN}）")
    print("【纸区质心色（中位）】")
    print(f"    前(全体 ok)      = {res['new_affine']['paper_before_median_all']}")
    print(f"    后(新,applied)   = {na['paper_after_median_applied']}")
    print(f"    后(旧,applied)   = {oa['paper_after_median_applied']}")
    print("\n【中灰 180 校正后色（中位）——「整体变冷」量化】")
    print(f"    applied: 新={na['gray180_after_median_applied']}  旧={oa['gray180_after_median_applied']}")
    print(f"    全语料 : 新={na['gray180_after_median_all']}  旧={oa['gray180_after_median_all']}")
    print("\n【限幅 / 判据命中】")
    print(f"    ΔE_core ≤2 命中(applied): 新 {res['comparison_core']['delta_e_core_after_le2_of_applied']['new']}/{len(new_applied)}"
          f"  旧 {res['comparison_core']['delta_e_core_after_le2_of_applied']['old']}/{len(old_applied)}")
    print(f"    ΔE_core ≤5 命中(applied): 新 {res['comparison_core']['delta_e_core_after_le5_of_applied']['new']}/{len(new_applied)}"
          f"  旧 {res['comparison_core']['delta_e_core_after_le5_of_applied']['old']}/{len(old_applied)}")
    print(f"    新越界通道命中: {sum(1 for r in ok if r['new']['clamped'])}/{len(ok)}")
    print(f"\n【反事实（非口径，仅诊断）：纸区排除印泥像素】evaluated={len(cf_rows)} "
          f"limiting={cf_lim} ({res['counterfactual_paper_excl_ink']['limiting_rate_of_evaluated']}) "
          f"degenerate={cf_deg} applied={len(cf_applied)} "
          f"ΔE_core 后 p50={pct([r['counterfactual_paper_excl_ink']['delta_e_core_after'] for r in cf_applied],50)}")

    print("\n--- 抽样 5 张（新 applied）逐张读数 ---")
    print(f"{'sha8':9}{'ink%':>7}  {'C_core 前':17}{'C_core 后(新)':17}{'ΔE前':>7}{'ΔE后新':>8}{'ΔE后旧':>8}{'纸偏移新':>9}{'纸→白ΔE':>9}")
    for r in new_applied[:5]:
        c, cn = r["centroid_core_before"], r["new"]["centroid_core_after"]
        cs = f"({c[0]:.0f},{c[1]:.0f},{c[2]:.0f})" if c else "None"
        cns = f"({cn[0]:.0f},{cn[1]:.0f},{cn[2]:.0f})" if cn else "None"
        print(f"{r['sha'][:8]:9}{r['ink_ratio']*100:6.2f}  {cs:17}{cns:17}"
              f"{r['delta_e_core_before']:7.2f}{r['new']['delta_e_core_after']:8.2f}"
              f"{r['old']['delta_e_core_after']:8.2f}{r['new']['paper_hue_shift']:9.2f}"
              f"{r['new']['paper_de_white_after']:9.2f}")
    print(f"\n写出 {OUT}")


if __name__ == "__main__":
    main()
