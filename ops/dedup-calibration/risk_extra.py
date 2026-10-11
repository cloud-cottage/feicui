#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""收口单风险抽验拼图（Kong / 去重收口单 2026-10-11）— **只读**。

在**推荐版（T1=0.5 ＋ R2 仅 ≥2 子框）**上出三组证据拼图（落 `risk/`）：

* `risk/recommended/`  ≥10 例「仍会被删的 R2 组框」——按构造**全为 ≥2 子框**；
  按子框数 2/3/4 分层抽，并优先抽**残墨最低（最纯假框）**者；标题带 `residual` 自证。
* `risk/r1_borderline/` **21 行** `R1 掩膜 IoU ∈ [0.40,0.50)`（派单所称 [0.41,0.49)；
  实测下限 0.4089，故等价于掩膜 IoU < 0.5）——这是未来是否把 T1 降到 0.45 的依据。
* `risk/anchors/` Zang 已视觉复核的两例**旧口径误杀锚点**（福庵 p110 idx0 / p74 idx0）：
  收窄后**已保留**，逐例出「大框（今保留）＋ 曾被子框」证据。

每行 1 例 ＝〔整页缩略（红框＝将被去掉、绿框＝保留对手）｜红框原大切片｜绿框原大切片〕。
**不重出图**：只读渲染页面在内存里做证据拼图，不写 `output/books/` 任何切片。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rm = _load(HERE / "risk_montage.py", "risk_montage_for_extra")


def _panel_for(img, drop, keep, title):
    rr_d = rm.red_ratio(img, (drop["x1"], drop["y1"], drop["x2"], drop["y2"]))
    rr_k = rm.red_ratio(img, (keep["x1"], keep["y1"], keep["x2"], keep["y2"]))
    title = title + f" | red D={rr_d:.2f} K={rr_k:.2f}"
    return rm.build_panel(img, drop, keep, title), rr_d, rr_k


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--indir", default=str(HERE))
    ap.add_argument("--outdir", default=str(HERE / "risk"))
    ap.add_argument("--n-r2", type=int, default=14)
    args = ap.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    boxes = rm.load_boxes(Path(args.db))
    paths = rm.pdf_paths(Path(args.db))

    # ---- 数据源 ----
    reco = json.loads((indir / "variant_conservative.json").read_text(encoding="utf-8"))
    rg = json.loads((indir / "residual_guard.json").read_text(encoding="utf-8"))
    resid = {r["id"]: r for r in rg["candidates"]}
    ink = json.loads((indir / "ink_check.json").read_text(encoding="utf-8"))

    marks = reco["marked_rows"]
    r2 = [m for m in marks if m["reason"] == "R2"]
    assert all(len(str(m.get("children_idx") or "").split(",")) >= 2 for m in r2), "R2 应全为 ≥2 子框"
    max_resid = max(resid.get(m["id"], {}).get("residual_ratio", 1.0) for m in r2)
    print(f"[check] 推荐版 R2 标记 {len(r2)} 例，全 ≥2 子框；最差 residual={max_resid}")

    docs: dict = {}
    page_cache: dict = {}
    index: list = []

    def render(book, page):
        if (book, page) not in page_cache:
            if book not in docs:
                p = paths.get(book)
                docs[book] = pymupdf.open(p) if (p and p.exists()) else None
            doc = docs[book]
            page_cache[(book, page)] = (rm.processor.render_page(doc[page - 1])
                                        if doc is not None else None)
        return page_cache[(book, page)]

    def emit(label, sub, m_or_drop, keep, title):
        book, page = m_or_drop["book"], m_or_drop["page"]
        img = render(book, page)
        if img is None:
            print(f"[skip] 无 PDF {book}")
            return
        drop = boxes[m_or_drop["id"]]
        panel, rr_d, rr_k = _panel_for(img, drop, keep, title)
        single = outdir / sub / f"{sub}_{label}.png"
        single.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(single), panel)
        index.append({
            "group": sub, "label": label, "book": book, "page": page,
            "drop_id": m_or_drop["id"], "drop_idx": m_or_drop["idx"],
            "keep_id": keep["id"], "keep_idx": keep["idx"],
            "drop_red_ratio": round(rr_d, 4), "keep_red_ratio": round(rr_k, 4),
            "panel": str(single.relative_to(HERE)),
        })
        print(f"[panel] {sub}/{label} p{page} drop#{m_or_drop['idx']} keep#{keep['idx']} "
              f"red={rr_d:.2f}/{rr_k:.2f}")

    # ---- ① R2：≥10 例「仍会被删」的组框（按子框数分层，优先最纯） ----
    sel, seen = [], set()
    for n in (4, 3, 2):
        grp = [m for m in r2 if resid.get(m["id"], {}).get("n_children") == n]
        grp.sort(key=lambda m: resid.get(m["id"], {}).get("residual_ratio", 1.0))
        for m in grp:
            if len([x for x in sel if resid.get(x["id"], {}).get("n_children") == n]) >= 5:
                break
            if m["id"] not in seen:
                seen.add(m["id"])
                sel.append(m)
    # 补足：残墨最低者
    for m in sorted(r2, key=lambda m: resid.get(m["id"], {}).get("residual_ratio", 1.0)):
        if len(sel) >= args.n_r2:
            break
        if m["id"] not in seen:
            seen.add(m["id"])
            sel.append(m)
    sel = sel[:max(args.n_r2, 12)]
    for m in sel:
        r = resid.get(m["id"], {})
        keep = boxes[m["partner_id"]]
        title = (f"RECO R2 id={m['id']} {m['book'][:12]} p{m['page']} #{m['idx']} "
                 f"kids={r.get('n_children')}[{m.get('children_idx')}] resid={r.get('residual_ratio')} "
                 f"| DROP {int(boxes[m['id']]['x2']-boxes[m['id']]['x1'])}x"
                 f"{int(boxes[m['id']]['y2']-boxes[m['id']]['y1'])} KEEP #{keep['idx']}")
        emit(f"r2_id{m['id']}_p{m['page']}", "recommended", m, keep, title)

    # ---- ② R1 掩膜 IoU∈[0.40,0.50) 的 21 行 ----
    r1 = [r for r in ink if r["reason"] == "R1" and r["mask_iou_page"] < 0.5]
    byid = {}
    for r in r1:
        byid.setdefault(r["id"], r)
    r1_rows = [byid[i] for i in sorted(byid)]
    print(f"[check] R1 掩膜 IoU<0.5 的行 = {len(r1_rows)}（派单称 21）")
    for r in r1_rows:
        drop = boxes[r["id"]]
        keep = boxes[r["partner_id"]]
        title = (f"R1-BORDER id={r['id']} {r['book'][:12]} p{r['page']} #{r['idx']} "
                 f"bboxIoU={r['metric']:.3f} maskIoU={r['mask_iou_page']:.3f} -> KEEP #{keep['idx']}")
        emit(f"r1_id{r['id']}_p{r['page']}_m{r['mask_iou_page']:.3f}", "r1_borderline",
             {"id": r["id"], "idx": r["idx"], "book": r["book"], "page": r["page"]}, keep, title)

    # ---- ③ 旧口径误杀锚点（收窄后已保留） ----
    for bid in (7990, 7701):
        b = boxes[bid]
        # 取页内与该大框最贴的「子框」（面积次大且被包含者）
        page_boxes = [x for x in boxes.values() if x["pdf_name"] == b["pdf_name"] and x["page"] == b["page"]]
        inside = [x for x in page_boxes
                  if x["id"] != bid and b["x1"] - 8 <= x["x1"] and b["y1"] - 8 <= x["y1"]
                  and x["x2"] <= b["x2"] + 8 and x["y2"] <= b["y2"] + 8]
        inside.sort(key=lambda x: -((x["x2"] - x["x1"]) * (x["y2"] - x["y1"])))
        child = inside[0] if inside else b
        title = (f"ANCHOR(kept) id={bid} {b['pdf_name'][:10]} p{b['page']} #{b['idx']} "
                 f"{int(b['x2']-b['x1'])}x{int(b['y2']-b['y1'])} (旧口径曾误删，今保留)")
        emit(f"anchor_id{bid}_p{b['page']}", "anchors",
             {"id": bid, "idx": b["idx"], "book": b["pdf_name"], "page": b["page"]}, child, title)

    (outdir / "risk_extra_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 汇总拼图 ----
    for sub in ("recommended", "r1_borderline", "anchors"):
        paths_ = [p for p in index if p["group"] == sub]
        imgs = [cv2.imread(str(HERE / p["panel"])) for p in paths_]
        imgs = [im for im in imgs if im is not None]
        if not imgs:
            continue
        w = max(im.shape[1] for im in imgs)
        imgs = [np.pad(im, ((0, 0), (0, w - im.shape[1]), (0, 0)), constant_values=28) for im in imgs]
        cv2.imwrite(str(outdir / f"montage_{sub}.png"), np.vstack(imgs))
        print(f"[montage] montage_{sub}.png samples={len(imgs)}")
    for d in docs.values():
        if d is not None:
            d.close()
    print(f"[index] {len(index)} panels → risk/risk_extra_index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
