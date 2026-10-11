#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R1/R2 判词的 **像素级核验**（Kong / 去重标定单 2026-10-11）— 只读、不写库、不重出图。

为什么必须做这一层：R2 只用「bbox 包含（容差 8 px）＋ 面积比 < T2」判「大框＝假组框」。
bbox 判据**看不见框里的墨**，故两类错误都可能发生。本脚本用 `MORPH_CLOSE(3×3)` 后的
红掩膜（与 `processor.detect_stamp_regions` 同式、按各书模板 HSV）判：

* **R2 帧框 A**：
  - `residual_ratio` ＝ `(A 的红面积 − 各子框红面积之和) / A 的红面积`
    （子框互不重叠，故用和；子框红面积按 A∩子框取）。
    · `<= 0.15` ⇒ **纯假框**：A 自身几乎没有墨（框里的墨全部由子框解释）⇒ 丢 A 正确。
    · `> 0.15` ⇒ **A 自带墨**：可能是「真大印面里嵌了一枚小印」⇒ 丢 A 有误杀风险，须人看。
  - `n_sig` ＝ A 内面积 ≥ `max(0.25×min_area_eff,1500)` 的红连通域个数（≥2 与「桥接」一致）。
* **R1 近重复对**：**红掩膜 IoU（页面坐标）**——比 bbox IoU 更贴真相；
  `>= 0.5` ⇒ 同墨（真重复）⇒ 丢一枚正确；否则标 `distinct_ink_suspect`（须人看）。
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
import numpy as np
import pymupdf

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")

AREA_SCALE = (400.0 / 144.0) ** 2          # 与 processor 同式（144dpi 基准 → 400dpi）
DEFAULT_TPL = {"hsv_low": [0, 120, 70], "hsv_high": [10, 255, 255], "min_area": 800}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


processor = _load(REPO / "processor.py", "feicui_processor_cc")


def pdf_paths(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out: dict = {}
    for r in conn.execute("SELECT pdf_name, pdf_path, COUNT(*) c FROM jobs "
                          "GROUP BY pdf_name, pdf_path ORDER BY c DESC"):
        out.setdefault(r["pdf_name"], Path(r["pdf_path"]))
    names = [r[0] for r in conn.execute("SELECT DISTINCT pdf_name FROM stamps")]
    conn.close()
    # 回落：inbox 上传落盘 → 仓根（书名逐字，与 templates.json 同源）
    for name in sorted(set(list(out) + names)):
        p = out.get(name)
        if p is not None and p.exists():
            continue
        for cand in (REPO / "inbox" / "20261011" / name, REPO / name):
            if cand.exists():
                out[name] = cand
                break
        else:
            out.pop(name, None)
    return out


def load_boxes(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute("SELECT id,pdf_name,page,idx,x1,y1,x2,y2 FROM stamps"))
    conn.close()
    return {r["id"]: dict(r) for r in rows}


def red_mask(img, low, high):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, np.array(low), np.array(high))
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def _box_slice(mask, box):
    H, W = mask.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, max(x2, x1 + 1)), min(H, max(y2, y1 + 1))
    return mask[y1:y2, x1:x2], (x1, y1, x2, y2)


def frame_stats(mask, box, min_area_eff):
    sub, _ = _box_slice(mask, box)
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(sub, 8)
    comp_min = max(0.25 * min_area_eff, 1500.0)
    areas = sorted((int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)
                    if stats[i, cv2.CC_STAT_AREA] >= comp_min), reverse=True)
    box_area = max(sub.shape[0] * sub.shape[1], 1)
    return {
        "n_components": int(n - 1),
        "n_sig": len(areas),
        "sig_areas_top": areas[:6],
        "largest_cc_area": areas[0] if areas else 0,
        "largest_cc_coverage": round((areas[0] / box_area) if areas else 0.0, 4),
        "red_area": int(cv2.countNonZero(sub)),
        "red_ratio": round(float(cv2.countNonZero(sub)) / box_area, 4),
        "box_area": box_area,
    }


def red_area(mask, box):
    sub, _ = _box_slice(mask, box)
    return int(cv2.countNonZero(sub))


def mask_iou_page(mask, box_a, box_b):
    """页面坐标系下的红掩膜 IoU（两框须同页同帧）。"""
    H, W = mask.shape[:2]
    ma = np.zeros((H, W), np.uint8)
    mb = np.zeros((H, W), np.uint8)
    for m, b in ((ma, box_a), (mb, box_b)):
        x1, y1, x2, y2 = [int(v) for v in b]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W, max(x2, x1 + 1)), min(H, max(y2, y1 + 1))
        m[y1:y2, x1:x2] = mask[y1:y2, x1:x2]
    inter = int(np.count_nonzero(cv2.bitwise_and(ma, mb)))
    union = int(np.count_nonzero(cv2.bitwise_or(ma, mb)))
    return round(inter / union, 4) if union else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--indir", default=str(HERE))
    ap.add_argument("--out", default=str(HERE / "ink_check.json"))
    args = ap.parse_args()

    boxes = load_boxes(Path(args.db))
    paths = pdf_paths(Path(args.db))
    tpl = json.loads((REPO / "config" / "templates.json").read_text(encoding="utf-8"))

    variants = {}
    for label in ("conservative", "aggressive"):
        f = Path(args.indir) / f"variant_{label}.json"
        if f.exists():
            variants[label] = json.loads(f.read_text(encoding="utf-8"))
    assert variants

    needed: dict = {}
    for label, v in variants.items():
        for m in v["marked_rows"]:
            needed.setdefault((m["book"], m["page"]), []).append((label, m))

    docs: dict = {}
    rows: list = []
    slot = {(b["pdf_name"], b["page"], b["idx"]): bid for bid, b in boxes.items()}
    for (book, page), items in sorted(needed.items()):
        if book not in docs:
            p = paths.get(book)
            docs[book] = pymupdf.open(p) if (p and p.exists()) else None
        doc = docs[book]
        if doc is None:
            print(f"[skip] 无 PDF {book}")
            continue
        img = processor.render_page(doc[page - 1])
        t = tpl.get(book, DEFAULT_TPL)
        mask = red_mask(img, t["hsv_low"], t["hsv_high"])
        mae = t.get("min_area", 800) * AREA_SCALE
        del img
        for label, m in items:
            A = boxes[m["id"]]
            B = boxes[m["partner_id"]]
            abox = (A["x1"], A["y1"], A["x2"], A["y2"])
            bbox = (B["x1"], B["y1"], B["x2"], B["y2"])
            if m["reason"] == "R2":
                fs = frame_stats(mask, abox, mae)
                child_idx = sorted({int(x) for x in str(m.get("children_idx") or "").split(",") if x.strip()})
                kids_red = 0
                kids_found = 0
                for ci in child_idx:
                    bid = slot.get((book, page, ci))
                    if bid is None:
                        continue
                    kids_found += 1
                    cb = boxes[bid]
                    kids_red += red_area(mask, (cb["x1"], cb["y1"], cb["x2"], cb["y2"]))
                a_red = fs["red_area"]
                residual = max(a_red - kids_red, 0) / a_red if a_red else 0.0
                info = {
                    "reason": "R2",
                    "children_idx": ",".join(str(c) for c in child_idx),
                    "n_children_declared": len(child_idx),
                    "n_children_found": kids_found,
                    "frame_red_area": a_red,
                    "children_red_area": kids_red,
                    "residual_ratio": round(residual, 4),
                    "partner_red_area": red_area(mask, bbox),
                    "verdict": ("pure_frame_ok" if residual <= 0.15 else "frame_has_own_ink_review"),
                }
                info.update({f"frame_{k}": v for k, v in fs.items()})
            else:
                aa = max(int(A["x2"] - A["x1"]) * int(A["y2"] - A["y1"]), 1)
                ba = max(int(B["x2"] - B["x1"]) * int(B["y2"] - B["y1"]), 1)
                mi = mask_iou_page(mask, abox, bbox)
                info = {
                    "reason": "R1",
                    "mask_iou_page": mi,
                    "red_ratio_a": round(red_area(mask, abox) / aa, 4),
                    "red_ratio_b": round(red_area(mask, bbox) / ba, 4),
                    "verdict": "same_ink_ok" if mi >= 0.5 else "distinct_ink_suspect",
                }
            rows.append({"variant": label, "id": m["id"], "book": book, "page": page,
                         "idx": m["idx"], "metric": m["metric"], "partner_id": m["partner_id"],
                         "partner_idx": m["partner_idx"], **info})
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[out] {args.out} rows={len(rows)}")
    for d in docs.values():
        if d is not None:
            d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
