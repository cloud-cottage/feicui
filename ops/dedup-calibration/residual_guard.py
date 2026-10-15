#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""残墨守卫（**备选口径**）标定（Kong / 去重收口单 2026-10-11）— 只读、不写库、不重出图。

## 目的

对 R2 的**同一候选集**（同页 A 包含 B、容差 8 px、`area(B)/area(A) < T2` ⇒ A ＝ 候选大框）
并联算「残墨守卫」口径，与派单裁定的收窄口径「**仅 ≥2 子框才丢**」逐行对照：

* 候选大框 A 的红掩膜面积 `A_red`（HSV 红 ／ `MORPH_CLOSE(3×3)`，与 `processor.detect_stamp_regions` 同式）；
* 子框红面积之和 `K_red = Σ B_red`（子框互不重叠 ⇒ 用和；B_red 取 A 内该子框切片）；
* **残墨比** `residual = max(A_red − K_red, 0) / A_red`：
  * `residual <= thr` ⇒ A 自身几乎无独立墨（框里的墨全部由子框解释）⇒ **纯假框，丢 A 正确**；
  * `residual > thr` ⇒ A 自带墨 ⇒ 可能是「真大印面 / 单子框真印」⇒ 丢 A 有误杀风险。

「残墨守卫」口径 ＝ `residual <= thr 才丢`；与「≥2 子框」口径在同一候选集上比。

**不重出图**：只读渲染页面在内存里算掩膜，不写 `output/books/` 任何切片。
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import cv2
import pymupdf

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_DB = Path("/Users/kevin/bistro/data/yinpu.db")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


de = _load(HERE / "dedup_eval.py", "dedup_eval_for_guard")
ink = _load(HERE / "ink_check.py", "ink_check_for_guard")


def build_candidates(db: Path, t2: float) -> dict:
    """⇒ `{(book,page): [(big_box, [child_box, ...]), ...]}`（t2 内候选大框）。"""
    boxes = de.load_rows(db)
    pages = de.group_pages(boxes)
    out: dict = collections.defaultdict(list)
    for pk, bs in pages.items():
        kids: dict = collections.defaultdict(list)
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                for big, small in ((a, b), (b, a)):
                    if de.contains(big, small, de.TOL_PX) and 0.0 < de.area_ratio(small, big) < t2:
                        kids[big.id].append(small)
        by_id = {b.id: b for b in bs}
        for bid, cs in kids.items():
            out[pk].append((by_id[bid], sorted(cs, key=lambda b: b.idx)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--t2", type=float, default=0.60, help="候选口径（默认推荐版 0.60）")
    ap.add_argument("--out", default=str(HERE / "residual_guard.json"))
    ap.add_argument("--thresholds", default="0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.50")
    args = ap.parse_args()

    thr_list = [float(x) for x in args.thresholds.split(",")]
    cand = build_candidates(Path(args.db), args.t2)
    paths = ink.pdf_paths(Path(args.db))
    tpl = json.loads((REPO / "config" / "templates.json").read_text(encoding="utf-8"))

    docs: dict = {}
    rows: list = []
    for (book, page), items in sorted(cand.items()):
        p = paths.get(book)
        if book not in docs:
            docs[book] = pymupdf.open(p) if (p and p.exists()) else None
        doc = docs[book]
        if doc is None:
            print(f"[skip] 无 PDF {book}")
            continue
        img = ink.processor.render_page(doc[page - 1])
        t = tpl.get(book, ink.DEFAULT_TPL)
        mask = ink.red_mask(img, t["hsv_low"], t["hsv_high"])
        mae = t.get("min_area", 800) * ink.AREA_SCALE
        del img
        for big, cs in items:
            abox = (big.x1, big.y1, big.x2, big.y2)
            a_red = ink.red_area(mask, abox)
            k_red = sum(ink.red_area(mask, (c.x1, c.y1, c.x2, c.y2)) for c in cs)
            residual = max(a_red - k_red, 0) / a_red if a_red else 0.0
            fs = ink.frame_stats(mask, abox, mae)
            rows.append({
                "book": book, "page": page, "id": big.id, "idx": big.idx,
                "big_size": [round(big.w()), round(big.h())],
                "n_children": len(cs),
                "children_idx": ",".join(str(c.idx) for c in cs),
                "frame_red_area": a_red, "children_red_area": k_red,
                "residual_ratio": round(residual, 4),
                "n_sig": fs["n_sig"], "red_ratio": fs["red_ratio"],
                "largest_cc_coverage": fs["largest_cc_coverage"],
            })
        print(f"[page] {book[:18]} p{page} candidates={len(items)}")
    for d in docs.values():
        if d is not None:
            d.close()

    # ---- 汇总：残墨守卫 vs ≥2 子框 ----
    ge2 = [r for r in rows if r["n_children"] >= 2]
    sweep = []
    for thr in thr_list:
        guard = [r for r in rows if r["residual_ratio"] <= thr]
        g_ids = {r["id"] for r in guard}
        c_ids = {r["id"] for r in ge2}
        sweep.append({
            "residual_thr": thr,
            "guard_drops": len(guard),
            "ge2_drops": len(ge2),
            "both": len(g_ids & c_ids),
            "guard_only": len(g_ids - c_ids),
            "ge2_only": len(c_ids - g_ids),
            "agreement": round(len(g_ids & c_ids) / max(len(g_ids | c_ids), 1), 3),
        })
    by_children = {}
    for n in sorted({r["n_children"] for r in rows}):
        sub = [r for r in rows if r["n_children"] == n]
        resid_ = sorted(r["residual_ratio"] for r in sub)
        pure = sum(1 for r in sub if r["residual_ratio"] <= 0.15)
        by_children[n] = {
            "candidates": len(sub),
            "residual_min": resid_[0], "residual_median": resid_[len(resid_) // 2],
            "residual_max": resid_[-1],
            "pure_le_0.15": pure, "pure_pct": round(100.0 * pure / len(sub), 1),
        }
    out = {
        "caliber": ("残墨守卫（备选口径）：residual = (frame_red − Σ children_red)/frame_red；"
                    "residual <= thr ⇒ 纯假框丢。对照派单收窄口径『仅 ≥2 子框才丢』。"),
        "params": {"t2": args.t2, "tol_px": de.TOL_PX},
        "n_candidates": len(rows),
        "sweep": sweep,
        "by_n_children": by_children,
        "candidates": rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[out] {args.out} candidates={len(rows)}")
    print(f"{'thr':>5} {'guard':>6} {'ge2':>5} {'both':>5} {'g_only':>7} {'2_only':>7} {'agree':>6}")
    for s in sweep:
        print(f"{s['residual_thr']:>5} {s['guard_drops']:>6} {s['ge2_drops']:>5} {s['both']:>5} "
              f"{s['guard_only']:>7} {s['ge2_only']:>7} {s['agreement']:>6}")
    print("by n_children:", json.dumps(by_children, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
