#!/usr/bin/env python
"""`app/colorcal.py` 语料 A/B 对照 —— **默认（双锚点仿射）vs V1b（纸→纯白白平衡）**。

跑法（**只读**，用 worker venv）：
    /Users/kevin/bistro/xiai/feicui/venv/bin/python \
        /Users/kevin/bistro/xiai/feicui/ops/image-colorcal/corpus_ab_v1b.py

抽样方式（**确定性、可复现、与上单纯等距系统抽样同口径**）：对 `var/seal_images_tiff/**/*.tiff`
全 N 件**按路径排序**后取等距系统抽样 `idx_i = round(i·N/n)`（`i=0..n-1`，`n=120`）。
**只读**：不写 TIFF、不写 DB、不建 job。

三列口径（同一 120 张）：
  * `default`      —— **默认路径**：双锚点仿射；纸锚点集合 ＝ **非印泥 ∧ V≥p90**（★ v0.1 修订 3）；
                      印泥核心质心（S≥p75）→ `#C95021`。
  * `v1b`          —— **可选口径**：只做**纸 → `#FFFFFF`** 的白平衡（对角增益 `k = white_lin/W_lin`、
                      限幅 `k∈[0.5,3]`），**不咬印泥靶色**。
  * `default_no_excl`（**对照，非口径**）—— 同 `default` 但纸锚点**不排除印泥**（revision 前形态），
                      用于量化「采纳项」在语料上的效果。
另附观察项 `v1b_no_ink_gate`：V1b **不设 `ink_ratio` 闸**时能多覆盖多少张（**不是口径**）。

判据口径（Zang 裁定）：`ΔE_core`（核心质心→`#C95021`）＝ CA-1；`paper_de_white`（纸→`#FFFFFF`）＝ CA-2；
`ΔE_all`（掩膜全体质心）**只作观察项**。
输出：`ops/image-colorcal/corpus_ab_v1b.json`（聚合 ＋ 逐张，不 dump 全量像素）。
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

OUT = Path(__file__).resolve().parent / "corpus_ab_v1b.json"
TIFF_GLOB = str(REPO / "var" / "seal_images_tiff" / "**" / "*.tiff")
N_SAMPLE = 120
GRAY_TILES = (90, 128, 180, 220)


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


def gray_after(rep, kind):
    """灰瓦 90/128/180/220 校正后色；未施加（skipped）⇒ 原值。"""
    out = {}
    for g in GRAY_TILES:
        if rep["mode"] != "applied":
            out[str(g)] = [float(g), float(g), float(g)]
            continue
        if kind == "affine":
            c = cc.apply_affine_color((g, g, g), {"a": rep["a"], "b": rep["b"]})
        else:
            c = cc.apply_gains_color((g, g, g), rep["gains"])
        out[str(g)] = [float(x) for x in c]
    return out


def block_from_report(rep, kind, pmask, core_mask, m_all):
    """把一次 `correct_image*` 的报告 + 目标图读数整理成对照用的扁平块。"""
    return {
        "mode": rep["mode"], "marker": rep["marker"], "skip_reason": rep["skip_reason"],
        "a": list(rep["a"]) if rep.get("a") else None,
        "b": list(rep["b"]) if rep.get("b") else None,
        "gains": list(rep["gains"]) if rep.get("gains") else None,
        "raw_a": list(rep["raw_a"]) if rep.get("raw_a") else None,
        "raw_gains": list(rep["raw_gains"]) if rep.get("raw_gains") else None,
        "clamped": rep["clamped"], "clamped_channels": rep["clamped_channels"],
        "min_lin_component": rep.get("min_lin_component"),
        "centroid_core_after": rep["centroid_core_after"],
        "centroid_all_after": rep["centroid_all_after"],
        "paper_after": rep["paper_after_rgb"],
        "delta_e_core_after": rep["delta_e_after"],
        "delta_e_all_after": rep["delta_e_all_after"],
        "paper_de_white_after": rep["paper_delta_e_after"],
        "paper_hue_shift": rep["paper_hue_shift"],
        "gray_after": gray_after(rep, kind),
    }


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
        total = int(arr.shape[0]) * int(arr.shape[1]) or 1
        ratio = int(m_all.sum()) / total
        core = cc.ink_core_centroid(arr)
        core_mask = core["mask"]
        paper = cc.paper_centroid(arr)          # 默认（排除印泥）
        pmask = paper["mask"]
        c_core_before = core["rgb"]
        c_all_before = cc.region_mean_rgb(arr, m_all)
        paper_before = paper["rgb"]

        corr_d, rep_d = cc.correct_image(arr)                        # 默认：双锚点仿射（排除印泥）
        corr_o, rep_o = cc.correct_image(arr, paper_exclude_ink=False)   # 对照：不排除印泥
        corr_w, rep_w = cc.correct_image_whitebalance(arr)           # V1b：纸→白白平衡
        corr_g, rep_g = cc.correct_image_whitebalance(arr, ink_ratio_min=0.0)  # 观察：V1b 不设印泥闸

        def suite(corr):
            cc_a = cc.region_mean_rgb(corr, core_mask)
            ca_a = cc.region_mean_rgb(corr, m_all)
            pw_a = cc.region_mean_rgb(corr, pmask)
            return (cc.delta_e2000(cc_a, cc.TARGET_RGB) if cc_a else None,
                    cc.delta_e2000(ca_a, cc.TARGET_RGB) if ca_a else None,
                    cc.delta_e2000(pw_a, cc.WHITE_RGB) if pw_a else None)

        de_d, deall_d, pw_d = suite(corr_d)
        de_o, deall_o, pw_o = suite(corr_o)
        de_w, deall_w, pw_w = suite(corr_w)

        rows.append({
            "path": os.path.relpath(p, REPO), "sha": os.path.basename(p)[:-5],
            "wh": [int(arr.shape[1]), int(arr.shape[0])], "ink_ratio": ratio,
            "core_pixels": core["pixels"], "core_sat_threshold": core["sat_threshold"],
            "paper_pixels": int(pmask.sum()), "paper_v_threshold": paper["v_threshold"],
            "centroid_core_before": c_core_before, "centroid_all_before": c_all_before,
            "paper_before": paper_before,
            "delta_e_core_before": cc.delta_e2000(c_core_before, cc.TARGET_RGB) if c_core_before else None,
            "delta_e_all_before": cc.delta_e2000(c_all_before, cc.TARGET_RGB) if c_all_before else None,
            "paper_de_white_before": cc.delta_e2000(paper_before, cc.WHITE_RGB) if paper_before else None,
            "default": dict(block_from_report(rep_d, "affine", pmask, core_mask, m_all),
                            delta_e_core_after=de_d, delta_e_all_after=deall_d,
                            paper_de_white_after=pw_d),
            "default_no_excl": dict(block_from_report(rep_o, "affine", pmask, core_mask, m_all),
                                    delta_e_core_after=de_o, delta_e_all_after=deall_o,
                                    paper_de_white_after=pw_o),
            "v1b": dict(block_from_report(rep_w, "gains", pmask, core_mask, m_all),
                        delta_e_core_after=de_w, delta_e_all_after=deall_w,
                        paper_de_white_after=pw_w),
            "v1b_no_ink_gate": {"mode": rep_g["mode"], "skip_reason": rep_g["skip_reason"],
                                "gains": list(rep_g["gains"]) if rep_g.get("gains") else None},
        })
        if (j + 1) % 30 == 0:
            print(f"  ... {j + 1}/{len(sample)}")

    ok = [r for r in rows if "error" not in r]

    def collect(side):
        applied = [r for r in ok if r[side]["mode"] == "applied"]
        skipped = [r for r in ok if r[side]["mode"] == "skipped"]
        buckets = {}
        for r in skipped:
            buckets[r[side]["skip_reason"]] = buckets.get(r[side]["skip_reason"], 0) + 1
        return applied, skipped, buckets

    def side_block(side, kind):
        applied, skipped, buckets = collect(side)
        n_ok = len(ok) or 1
        block = {
            "counts": {
                "sampled_ok": len(ok), "applied": len(applied), "skipped": len(skipped),
                "skip_rate": len(skipped) / n_ok,
                "skip_buckets": {
                    "ink_ratio": buckets.get("ink_ratio", 0),
                    "degenerate": buckets.get("degenerate", 0),
                    "limiting": buckets.get("limiting", 0),
                },
                "skip_rate_ink_ratio": buckets.get("ink_ratio", 0) / n_ok,
                "skip_rate_degenerate": buckets.get("degenerate", 0) / n_ok,
                "skip_rate_limiting": buckets.get("limiting", 0) / n_ok,
                "clamped_of_all": sum(1 for r in ok if r[side]["clamped"]),
            },
            "delta_e_core_before_all": dist([r["delta_e_core_before"] for r in ok]),
            "delta_e_all_before_all": dist([r["delta_e_all_before"] for r in ok]),
            "delta_e_core_after_applied": dist([r[side]["delta_e_core_after"] for r in applied]),
            "delta_e_all_after_applied": dist([r[side]["delta_e_all_after"] for r in applied]),
            "paper_de_white_before_all": dist([r["paper_de_white_before"] for r in ok]),
            "paper_de_white_after_applied": dist([r[side]["paper_de_white_after"] for r in applied]),
            "paper_hue_shift_applied": dist([r[side]["paper_hue_shift"] for r in applied]),
            "paper_after_median_applied": med3(applied, lambda r: r[side]["paper_after"]),
            "paper_before_median_all": med3(ok, lambda r: r["paper_before"]),
            "gray_after_median_applied": {
                str(g): [float(np.median([r[side]["gray_after"][str(g)][i] for r in applied]))
                         for i in range(3)] for g in GRAY_TILES} if applied else {},
            "gray_after_median_all": {
                str(g): [float(np.median([r[side]["gray_after"][str(g)][i] for r in ok]))
                         for i in range(3)] for g in GRAY_TILES} if ok else {},
            "delta_e_core_after_le2_applied": sum(1 for r in applied if (r[side]["delta_e_core_after"] or 9e9) <= 2),
            "delta_e_core_after_le5_applied": sum(1 for r in applied if (r[side]["delta_e_core_after"] or 9e9) <= 5),
        }
        if kind == "affine":
            block["a_by_channel"] = {c: dist([r[side]["a"][i] for r in applied if r[side]["a"]])
                                     for i, c in enumerate("rgb")}
            block["b_by_channel"] = {c: dist([r[side]["b"][i] for r in applied if r[side]["b"]])
                                     for i, c in enumerate("rgb")}
            block["a_median_applied"] = med3(applied, lambda r: r[side]["a"])
            block["b_median_applied"] = med3(applied, lambda r: r[side]["b"])
        else:
            block["gains_by_channel"] = {c: dist([r[side]["gains"][i] for r in applied if r[side]["gains"]])
                                         for i, c in enumerate("rgb")}
            block["gains_median_applied"] = med3(applied, lambda r: r[side]["gains"])
        return block

    b_default = side_block("default", "affine")
    b_noexcl = side_block("default_no_excl", "affine")
    b_v1b = side_block("v1b", "gains")

    # 观察项：V1b 不设 ink 闸能覆盖多少
    gate_extra = sum(1 for r in ok if r["v1b"]["mode"] == "skipped"
                     and r["v1b"]["skip_reason"] == "ink_ratio"
                     and r["v1b_no_ink_gate"]["mode"] == "applied")
    gate_blocked = sum(1 for r in ok if r["v1b"]["mode"] == "skipped"
                       and r["v1b"]["skip_reason"] == "ink_ratio"
                       and r["v1b_no_ink_gate"]["mode"] != "applied")

    # 采纳项效果（语料）：旧口径 limiting → 新口径 applied 的张数
    fixed = sum(1 for r in ok if r["default_no_excl"]["mode"] == "skipped"
                and r["default_no_excl"]["skip_reason"] == "limiting"
                and r["default"]["mode"] == "applied")
    still_limiting = sum(1 for r in ok if r["default"]["skip_reason"] == "limiting")

    def per_image(side, kind, r):
        b = r[side]
        return {
            "sha8": r["sha"][:8], "wh": r["wh"], "ink_ratio": round(r["ink_ratio"], 4),
            "mode": b["mode"], "marker": b["marker"], "skip_reason": b["skip_reason"],
            "centroid_core_before": r["centroid_core_before"],
            "centroid_core_after": b["centroid_core_after"],
            "delta_e_core_before": r["delta_e_core_before"],
            "delta_e_core_after": b["delta_e_core_after"],
            "centroid_all_before": r["centroid_all_before"],
            "centroid_all_after": b["centroid_all_after"],
            "delta_e_all_before": r["delta_e_all_before"],
            "delta_e_all_after": b["delta_e_all_after"],
            "paper_before": r["paper_before"], "paper_after": b["paper_after"],
            "paper_de_white_before": r["paper_de_white_before"],
            "paper_de_white_after": b["paper_de_white_after"],
            "paper_hue_shift": b["paper_hue_shift"],
            "a_or_gains": b["a"] if kind == "affine" else b["gains"],
            "b": b["b"] if kind == "affine" else None,
            "gray_after": b["gray_after"],
        }

    applied_rows = [r for r in ok if r["default"]["mode"] == "applied"]
    detail_src = (applied_rows or ok)[:5]
    detail5 = {
        "note": "前 5 张**两口径均生效**（按抽样顺序；与上单同一抽样 ⇒ sha8 可逐行对照）；"
                "若两口径均生效者不足 5 张则顺延",
        "shas": [r["sha"][:8] for r in detail_src],
        "default": [per_image("default", "affine", r) for r in detail_src],
        "v1b": [per_image("v1b", "gains", r) for r in detail_src],
    }

    def shas(pred):
        return [r["sha"][:8] for r in ok if pred(r)]

    res = {
        "generated_by": "ops/image-colorcal/corpus_ab_v1b.py",
        "algorithms": {
            "default": "affine-2anchor（纸[非印泥∧V≥p90]→#FFFFFF、印泥核心质心[S≥p75]→#C95021）",
            "v1b": "whitebalance-diagonal（纸[非印泥∧V≥p90]→#FFFFFF，k=white_lin/W_lin，不咬印泥靶色）",
            "default_no_excl": "affine-2anchor，纸锚点**不排除印泥**（对照，非口径）",
        },
        "target": {"rgb": list(cc.TARGET_RGB), "hex": cc.TARGET_HEX},
        "white": {"rgb": list(cc.WHITE_RGB), "hex": "#FFFFFF"},
        "params": {"a_min": cc.A_MIN, "a_max": cc.A_MAX, "b_min": cc.B_MIN, "b_max": cc.B_MAX,
                   "wb_k_min": cc.WB_K_MIN, "wb_k_max": cc.WB_K_MAX,
                   "paper_quantile": cc.PAPER_QUANTILE, "core_sat_quantile": cc.INK_CORE_SAT_QUANTILE,
                   "degenerate_min_lin": cc.DEGENERATE_MIN_LIN, "ink_ratio_min": cc.INK_RATIO_MIN,
                   "gray_tiles": list(GRAY_TILES)},
        "corpus": {"glob": "var/seal_images_tiff/**/*.tiff", "N_total": N, "n_sampled": len(sample),
                   "sampling": "按路径排序后等距系统抽样 idx=round(i*N/n)，n=120（与上单同口径）",
                   "load_errors": load_err},
        "ab_table": {"default_affine": b_default, "v1b_whitebalance": b_v1b,
                     "reference_no_ink_exclusion": b_noexcl},
        "adoption_effect": {
            "note": "★ v0.1 修订 3 的语料效果：旧口径（不排除印泥）判定 limiting 而新口径判 applied 的张数",
            "fixed_limiting_to_applied": fixed,
            "still_limiting_under_new": still_limiting,
            "limiting_before": b_noexcl["counts"]["skip_buckets"]["limiting"],
            "limiting_after": b_default["counts"]["skip_buckets"]["limiting"],
            "applied_before": b_noexcl["counts"]["applied"],
            "applied_after": b_default["counts"]["applied"],
            "saved_by_adoption_shas": shas(lambda r: r["default_no_excl"]["mode"] == "skipped"
                                           and r["default_no_excl"]["skip_reason"] == "limiting"
                                           and r["default"]["mode"] == "applied"),
            "still_limiting_shas": shas(lambda r: r["default"]["skip_reason"] == "limiting"),
            "degenerate_shas": shas(lambda r: r["default"]["skip_reason"] == "degenerate"),
        },
        "v1b_gate_observation": {
            "note": "**观察项，非口径**：V1b 若**不设 `ink_ratio` 闸**能多覆盖的张数",
            "extra_applied_without_ink_gate": gate_extra,
            "still_not_applicable_without_ink_gate": gate_blocked,
            "applied_with_gate": b_v1b["counts"]["applied"],
            "applied_without_gate": b_v1b["counts"]["applied"] + gate_extra,
        },
        "five_image_detail": detail5,
        "rows": rows,
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

    # ---------------- 人读对照表 ----------------
    def f3(d, ks=("p50", "p90", "max")):
        if not d or d.get("p50") is None:
            return "n/a"
        return " ".join(f"{k}={d[k]:.2f}" for k in ks)

    def rgb3(v):
        return "n/a" if not v else f"({v[0]:.1f},{v[1]:.1f},{v[2]:.1f})"

    def line(name, dm, vb, n=34):
        print(f"{name:<28}{dm:>{n}}{vb:>{n}}")

    print("\n" + "=" * 100)
    print(f"抽样 {len(ok)} 件（load_err={load_err}）｜目标色 {cc.TARGET_HEX}｜白点 #FFFFFF｜"
          f"灰瓦 {list(GRAY_TILES)}")
    print("=" * 100)
    print(f"{'指标':<28}{'① 默认：双锚点仿射':>34}{'② V1b：纸→白白平衡':>34}")
    print("-" * 100)
    cd, cv = b_default["counts"], b_v1b["counts"]
    line("生效张数 applied", f"{cd['applied']}/{len(ok)}", f"{cv['applied']}/{len(ok)}")
    line("跳过率 skip_rate", f"{cd['skip_rate']:.3f}", f"{cv['skip_rate']:.3f}")
    line("  子因 ink_ratio",
         f"{cd['skip_buckets']['ink_ratio']} ({cd['skip_rate_ink_ratio']:.3f})",
         f"{cv['skip_buckets']['ink_ratio']} ({cv['skip_rate_ink_ratio']:.3f})")
    line("  子因 degenerate",
         f"{cd['skip_buckets']['degenerate']} ({cd['skip_rate_degenerate']:.3f})",
         f"{cv['skip_buckets']['degenerate']} ({cv['skip_rate_degenerate']:.3f})")
    line("  子因 limiting",
         f"{cd['skip_buckets']['limiting']} ({cd['skip_rate_limiting']:.3f})",
         f"{cv['skip_buckets']['limiting']} ({cv['skip_rate_limiting']:.3f})")
    print("-" * 100)
    line("ΔE_core→#C95021 前(全体ok)", f3(b_default["delta_e_core_before_all"]),
         f3(b_v1b["delta_e_core_before_all"]))
    line("ΔE_core→#C95021 后(applied)", f3(b_default["delta_e_core_after_applied"]),
         f3(b_v1b["delta_e_core_after_applied"]))
    line("  命中 ≤2 / ≤5 (applied)",
         f"{b_default['delta_e_core_after_le2_applied']} / {b_default['delta_e_core_after_le5_applied']}",
         f"{b_v1b['delta_e_core_after_le2_applied']} / {b_v1b['delta_e_core_after_le5_applied']}")
    line("ΔE 纸→#FFFFFF 前(全体ok)", f3(b_default["paper_de_white_before_all"]),
         f3(b_v1b["paper_de_white_before_all"]))
    line("ΔE 纸→#FFFFFF 后(applied)", f3(b_default["paper_de_white_after_applied"]),
         f3(b_v1b["paper_de_white_after_applied"]))
    line("ΔE_all(观察) 前(全体ok)", f3(b_default["delta_e_all_before_all"]),
         f3(b_v1b["delta_e_all_before_all"]))
    line("ΔE_all(观察) 后(applied)", f3(b_default["delta_e_all_after_applied"]),
         f3(b_v1b["delta_e_all_after_applied"]))
    print("-" * 100)
    line("系数中位 a / k", rgb3(b_default["a_median_applied"]), rgb3(b_v1b["gains_median_applied"]))
    line("系数中位 b", rgb3(b_default["b_median_applied"]), "—（对角增益无 b）")
    for ch in "rgb":
        line(f"  {ch}: a/k p50 / p90 / max",
             f"{b_default['a_by_channel'][ch]['p50']:.3f} / {b_default['a_by_channel'][ch]['p90']:.3f} / "
             f"{b_default['a_by_channel'][ch]['max']:.3f}",
             f"{b_v1b['gains_by_channel'][ch]['p50']:.3f} / {b_v1b['gains_by_channel'][ch]['p90']:.3f} / "
             f"{b_v1b['gains_by_channel'][ch]['max']:.3f}")
    print("-" * 100)
    print("【★ 变冷量化：灰瓦在两口径下校正后的 RGB（中位）】")
    print(f"{'灰瓦':<12}{'原值':>16}{'① 默认（applied）':>28}{'② V1b（applied）':>26}"
          f"{'① 全语料':>24}{'② 全语料':>22}")
    for g in GRAY_TILES:
        k = str(g)
        print(f"{'gray '+k:<12}{f'({g},{g},{g})':>16}"
              f"{rgb3(b_default['gray_after_median_applied'].get(k)):>28}"
              f"{rgb3(b_v1b['gray_after_median_applied'].get(k)):>26}"
              f"{rgb3(b_default['gray_after_median_all'].get(k)):>24}"
              f"{rgb3(b_v1b['gray_after_median_all'].get(k)):>22}")
    print("-" * 100)
    print("【纸区质心（中位）】")
    line("纸 前（全体 ok）", rgb3(b_default["paper_before_median_all"]), rgb3(b_v1b["paper_before_median_all"]))
    line("纸 后（applied）", rgb3(b_default["paper_after_median_applied"]),
         rgb3(b_v1b["paper_after_median_applied"]))
    line("纸区色相偏移°(applied)", f3(b_default["paper_hue_shift_applied"]),
         f3(b_v1b["paper_hue_shift_applied"]))
    print("-" * 100)
    print(f"【采纳项（★ v0.1 修订 3）语料效果】旧口径(不排除印泥) applied="
          f"{b_noexcl['counts']['applied']} limiting={b_noexcl['counts']['skip_buckets']['limiting']} "
          f"⇒ 新口径 applied={cd['applied']} limiting={cd['skip_buckets']['limiting']}"
          f"（limiting→applied 救回 {fixed} 张；仍未生效 {still_limiting} 张）")
    print(f"【观察项（非口径）】V1b 不设 ink_ratio 闸 ⇒ 可覆盖 "
          f"{b_v1b['counts']['applied']} + {gate_extra} = "
          f"{b_v1b['counts']['applied'] + gate_extra}/{len(ok)}（另有 {gate_blocked} 张仍不可用）")
    print(f"【默认口径 limiting 仍存 {still_limiting} 张】sha8="
          f"{', '.join(res['adoption_effect']['still_limiting_shas'])}")
    print(f"【默认口径 degenerate {len(res['adoption_effect']['degenerate_shas'])} 张】sha8="
          f"{', '.join(res['adoption_effect']['degenerate_shas'])}")

    print(f"\n--- 前 {len(detail_src)} 张逐张读数（两口径均生效；与上单同一抽样）---")
    for i, r in enumerate(detail_src, 1):
        print(f"\n  #{i} sha8={r['sha'][:8]} {r['wh'][0]}x{r['wh'][1]} "
              f"ink_ratio={r['ink_ratio']*100:.2f}%  core_px={r['core_pixels']}")
        print(f"    纸色 前={rgb3(r['paper_before'])}  ΔE→#FFFFFF 前={r['paper_de_white_before']:.2f}")
        for side, kind, label in (("default", "affine", "默认仿射"), ("v1b", "gains", "V1b 白平衡")):
            b = r[side]
            coef = (f"a={tuple(round(x,3) for x in b['a'])}" if kind == "affine" and b["a"]
                    else (f"k={tuple(round(x,4) for x in b['gains'])}" if b["gains"] else ""))
            print(f"    [{label}] mode={b['mode']} marker={b['marker']} {coef}")
            print(f"        核心质心 前={rgb3(r['centroid_core_before'])} 后={rgb3(b['centroid_core_after'])}  "
                  f"ΔE→#C95021: {r['delta_e_core_before']:.2f} → {b['delta_e_core_after']:.2f}"
                  f"   |  全体质心 ΔE(观察): {r['delta_e_all_before']:.2f} → {b['delta_e_all_after']:.2f}")
            print(f"        纸色 后={rgb3(b['paper_after'])}  ΔE→#FFFFFF 后={b['paper_de_white_after']:.2f}"
                  f"   灰瓦 后: 90={rgb3(b['gray_after']['90'])} 128={rgb3(b['gray_after']['128'])} "
                  f"180={rgb3(b['gray_after']['180'])} 220={rgb3(b['gray_after']['220'])}")

    print(f"\n写出 {OUT}")


if __name__ == "__main__":
    main()
