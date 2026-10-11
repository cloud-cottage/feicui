#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""风险抽验拼图（Kong / 去重标定单 2026-10-11）— **只读**。

对每版阈值变体抽 ≥10 例「将被去掉的框」，出拼图：
每行 1 例 ＝〔整页缩略（红框＝将被去掉、绿框＝保留对手）｜被去框原大切片｜保留对手原大切片〕，
并把框内红像素占比打进标签（自证 bbox 与 400 dpi 渲染帧对齐）。

**不重出图**：只读渲染页面（与 `processor.render_page` 同式）在内存里做证据拼图，
不写 `output/books/` 任何切片。输出落 `ops/dedup-calibration/risk/`。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
HERE = Path(__file__).resolve().parent

RENDER_DPI = 400.0
HSV_LOW = (0, 120, 70)
HSV_HIGH = (10, 255, 255)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


processor = _load(REPO / "processor.py", "feicui_processor_for_montage")


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------

def pdf_paths(db: Path) -> dict:
    """pdf_name → 磁盘 PDF 路径（先取 jobs 表实证路径，再回落 inbox / 仓根）。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = {}
    for r in conn.execute("SELECT pdf_name, pdf_path, COUNT(*) c FROM jobs GROUP BY pdf_name, pdf_path ORDER BY c DESC"):
        if r["pdf_name"] in out:
            continue
        p = Path(r["pdf_path"])
        out[r["pdf_name"]] = p
    conn.close()
    for name in list(out):
        if not out[name].exists():
            alt = REPO / "inbox" / "20261011" / name
            if alt.exists():
                out[name] = alt
    return out


def load_boxes(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute("SELECT id,pdf_name,page,idx,x1,y1,x2,y2 FROM stamps"))
    conn.close()
    return {r["id"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# 抽样（确定性）
# ---------------------------------------------------------------------------

FOCUS = [  # Zang 已视觉确认的实例（在场则必抽）
    ("秦印类编 检索版.pdf", 749, 18), ("秦印类编 检索版.pdf", 749, 19),
    ("秦印类编 检索版.pdf", 572, 8), ("秦印类编 检索版.pdf", 572, 11),
    ("秦印类编 检索版.pdf", 51, 5),
]


def pick_samples(variant: dict, marked: list, all_marked_other: set, n: int, seed: int) -> list:
    chosen: list = []
    seen: set = set()

    def add(m, why):
        if m["id"] in seen:
            return
        seen.add(m["id"])
        chosen.append({**m, "why": why})

    # ① 已确认实例
    for book, page, idx in FOCUS:
        for m in marked:
            if m["book"] == book and m["page"] == page and m["idx"] == idx:
                add(m, "zang_confirmed")
    # ② R1 极端（IoU 最大）
    for m in sorted([x for x in marked if x["reason"] == "R1"], key=lambda x: -x["metric"])[:3]:
        add(m, "R1_top_iou")
    # ③ R2 极端：最小 ratio（最清楚组框）＋ 最大 ratio（最接近阈值 ⇒ 误杀风险最高）
    r2 = sorted([x for x in marked if x["reason"] == "R2"], key=lambda x: x["metric"])
    for m in r2[:2]:
        add(m, "R2_min_ratio")
    for m in r2[-3:]:
        add(m, "R2_borderline_max_ratio")
    # ④ 激进版新增行（只有激进版会去掉）
    for m in [x for x in marked if x["id"] not in all_marked_other]:
        add(m, "aggressive_only")
    # ⑤ 随机补足（跨书分层）
    rnd = random.Random(seed)
    rest = [m for m in marked if m["id"] not in seen]
    rnd.shuffle(rest)
    by_book: dict = {}
    for m in rest:
        by_book.setdefault(m["book"], []).append(m)
    for book in sorted(by_book):
        add(by_book[book][0], "random_stratified")
    rest = [m for m in marked if m["id"] not in seen]
    rnd.shuffle(rest)
    for m in rest:
        if len(chosen) >= n:
            break
        add(m, "random_fill")
    return chosen[:max(n, 12)]


# ---------------------------------------------------------------------------
# 拼图
# ---------------------------------------------------------------------------

def _fit(img, max_w, max_h):
    h, w = img.shape[:2]
    s = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
    if s < 1.0:
        img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    return img


def red_ratio(img, box) -> float:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(HSV_LOW), np.array(HSV_HIGH))
    H, W = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, max(x2, x1 + 1)), min(H, max(y2, y1 + 1))
    c = mask[y1:y2, x1:x2]
    return float(cv2.countNonZero(c)) / max(c.size, 1)


def crop(img, box, pad=0):
    H, W = img.shape[:2]
    x1, y1, x2, y2 = box
    x1, y1 = max(0, int(x1) - pad), max(0, int(y1) - pad)
    x2, y2 = min(W, int(x2) + pad), min(H, int(y2) + pad)
    return img[y1:y2, x1:x2]


PANEL_BG = (28, 28, 32)
ROW_H = 360
THUMB_W = 300
CROP_W = 380
LABEL_H = 34


def build_panel(page_img, drop_row, keep_row, title):
    H, W = page_img.shape[:2]
    thumb = _fit(page_img.copy(), THUMB_W, ROW_H)
    th, tw = thumb.shape[:2]
    sx, sy = tw / W, th / H

    def draw(thumb, box, color, thick=3):
        x1, y1, x2, y2 = [int(v) for v in box]
        cv2.rectangle(thumb, (int(x1 * sx), int(y1 * sy)), (int(x2 * sx), int(y2 * sy)), color, thick)

    keep_box = (keep_row["x1"], keep_row["y1"], keep_row["x2"], keep_row["y2"])
    drop_box = (drop_row["x1"], drop_row["y1"], drop_row["x2"], drop_row["y2"])
    draw(thumb, keep_box, (60, 220, 60), 3)
    draw(thumb, drop_box, (40, 40, 235), 3)

    d_crop = _fit(crop(page_img, drop_box), CROP_W, ROW_H)
    k_crop = _fit(crop(page_img, keep_box), CROP_W, ROW_H)

    panel_w = tw + CROP_W * 2 + 12
    panel = np.full((ROW_H + LABEL_H, panel_w, 3), PANEL_BG, dtype=np.uint8)
    panel[LABEL_H:LABEL_H + th, 0:tw] = thumb
    cv2.putText(panel, title, (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 1, cv2.LINE_AA)
    o = tw + 6
    panel[LABEL_H:LABEL_H + d_crop.shape[0], o:o + d_crop.shape[1]] = d_crop
    cv2.rectangle(panel, (o - 3, LABEL_H - 1), (o + d_crop.shape[1] + 2, LABEL_H + d_crop.shape[0] + 2), (40, 40, 235), 2)
    o2 = o + CROP_W + 6
    panel[LABEL_H:LABEL_H + k_crop.shape[0], o2:o2 + k_crop.shape[1]] = k_crop
    cv2.rectangle(panel, (o2 - 3, LABEL_H - 1), (o2 + k_crop.shape[1] + 2, LABEL_H + k_crop.shape[0] + 2), (60, 220, 60), 2)
    return panel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--indir", default=str(HERE))
    ap.add_argument("--outdir", default=str(HERE / "risk"))
    ap.add_argument("--per-variant", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20261011)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    indir = Path(args.indir)
    outdir.mkdir(parents=True, exist_ok=True)
    boxes = load_boxes(Path(args.db))
    paths = pdf_paths(Path(args.db))

    variants = {}
    for label in ("conservative", "aggressive"):
        f = indir / f"variant_{label}.json"
        if f.exists():
            variants[label] = json.loads(f.read_text(encoding="utf-8"))
    assert variants, "先跑 dedup_eval.py --both"

    all_marked = {lab: {m["id"] for m in v["marked_rows"]} for lab, v in variants.items()}
    docs: dict = {}
    page_cache: dict = {}
    index = []
    for label, v in variants.items():
        other = all_marked.get("conservative" if label == "aggressive" else "aggressive", set())
        samples = pick_samples(v, v["marked_rows"], other, args.per_variant, args.seed)
        rows = []
        for m in samples:
            book, page, idx = m["book"], m["page"], m["idx"]
            if (book, page) not in page_cache:
                if book not in docs:
                    p = paths.get(book)
                    docs[book] = pymupdf.open(p) if (p and p.exists()) else None
                doc = docs[book]
                img = processor.render_page(doc[page - 1]) if doc is not None else None
                page_cache[(book, page)] = img
            img = page_cache[(book, page)]
            if img is None:
                print(f"[skip] 无 PDF: {book}")
                continue
            drop = boxes[m["id"]]
            keep = boxes[m["partner_id"]]
            rr_d = red_ratio(img, (drop["x1"], drop["y1"], drop["x2"], drop["y2"]))
            rr_k = red_ratio(img, (keep["x1"], keep["y1"], keep["x2"], keep["y2"]))
            area_d = (drop["x2"] - drop["x1"]) * (drop["y2"] - drop["y1"])
            area_k = (keep["x2"] - keep["x1"]) * (keep["y2"] - keep["y1"])
            title = (f"{label} {m['reason']} id={m['id']} {m['book'][:12]} p{page} #{idx} "
                     f"metric={m['metric']:.3f} | DROP {int(drop['x2']-drop['x1'])}x{int(drop['y2']-drop['y1'])}"
                     f" red={rr_d:.2f} | KEEP #{keep['idx']} {int(keep['x2']-keep['x1'])}x{int(keep['y2']-keep['y1'])}"
                     f" red={rr_k:.2f} area_ratio={area_d/area_k if area_k else 0:.2f}")
            panel = build_panel(img, drop, keep, title)
            rows.append(panel)
            single = outdir / label / f"{label}_id{m['id']}_p{page}_{m['reason']}.png"
            single.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(single), panel)
            index.append({
                "variant": label, "why": m["why"], "reason": m["reason"], "id": m["id"],
                "book": book, "page": page, "idx": idx, "metric": m["metric"],
                "partner_id": m["partner_id"], "partner_idx": keep["idx"],
                "drop_box": [drop["x1"], drop["y1"], drop["x2"], drop["y2"]],
                "keep_box": [keep["x1"], keep["y1"], keep["x2"], keep["y2"]],
                "drop_red_ratio": round(rr_d, 4), "keep_red_ratio": round(rr_k, 4),
                "drop_size": [int(drop["x2"] - drop["x1"]), int(drop["y2"] - drop["y1"])],
                "keep_size": [int(keep["x2"] - keep["x1"]), int(keep["y2"] - keep["y1"])],
                "panel": str(single.relative_to(HERE)),
            })
            print(f"[panel] {label} {m['reason']} id={m['id']} p{page} #{idx} why={m['why']} "
                  f"metric={m['metric']:.3f} red={rr_d:.2f}/{rr_k:.2f}")
        if rows:
            w = max(r.shape[1] for r in rows)
            rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=28) for r in rows]
            montage = np.vstack(rows)
            out = outdir / f"montage_{label}.png"
            cv2.imwrite(str(out), montage)
            print(f"[montage] {out} {montage.shape} samples={len(rows)}")
    (outdir / "risk_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[index] {len(index)} panels → {outdir/'risk_index.json'}")
    for d in docs.values():
        if d is not None:
            d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
