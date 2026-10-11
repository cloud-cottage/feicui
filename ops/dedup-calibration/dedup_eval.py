#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线去重标定器（Kong / 去重标定单 2026-10-11）— 纯只读、无副作用。

**本模块不改检测器、不改 worker、不写库、不建 job、不删文件、不重出图。**

## 规则（派单逐字）

输入＝库内 `stamps` 行（`x1,y1,x2,y2`，400 dpi 渲染像素坐标系，与
`processor.render_page` 输出同帧；对齐已实测：见 `ops/dedup-calibration/README.md` §0）。
输出＝「**保留** / **标记为重复**」两类，标记理由分桶：

* **R1 近重复**：同页两框 `IoU >= T1` ⇒ 只留一枚。
  tie-break 两种并列报：`area_max`（留面积较大者）／`area_median`（留面积更接近页内中位者）。
  同一页可传递成簇（union-find），每簇只留 1 枚。
* **R2 组框**：同页 A 包含 B（容差 `TOL=8 px`）且 `area(B)/area(A) < T2`
  ⇒ **丢 A（组框）留 B**；A 含多个 B 时**只丢 A 一次**。

## 合成顺序（关键）

* `r2_first`（**默认、推荐**）：先丢组框，再在幸存者上做 R1 近重复聚类。
  ——理由：组框是假印面，若先做 R1 且 tie-break 取「面积较大者」，**组框会把真印章从簇里挤掉**
  （反例读数见 README §5.4）。
* `r1_first`（仅作风险对照）：先 R1 再 R2。与 `r2_first` 的标记差集＝错误顺序的代价。

注：**包含对的 IoU 恒等于面积比**（B ⊂ A ⇒ 交集＝area(B) ⇒ IoU = area(B)/area(A)），
所以 R1/R2 在阈值带上有交叠，合成顺序不是可有可无。

## 用法

    venv/bin/python ops/dedup-calibration/dedup_eval.py --both --outdir ops/dedup-calibration
    venv/bin/python ops/dedup-calibration/dedup_eval.py --t1 0.5 --t2 0.6 --label conservative

只读连接：`sqlite3.connect("file:<db>?mode=ro", uri=True)`。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sqlite3
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")

#: 包含判定容差（px）——派单给定。
TOL_PX = 8.0

#: **R2 收窄口径（Kong 去重收口单 2026-10-11）**：大框须桥接 **≥ 2 个已检出子框**
#: 才判为假组框而丢；**单子框一律不动**。理由：Zang 视觉复核两例（福庵 p110 idx0 /
#: p74 idx0）证明「单子框 + 完整边框大印」的 A 是**真印章**，其子框才是碎片；按旧口径
#: （≥1 子框即丢）会误杀。旧口径 = 1，保留可切换以复现旧读数做对照。
DEFAULT_R2_MIN_CHILDREN = 2

#: 两版阈值变体（派单给定；**R2 一律走收窄口径 ≥2 子框**）。
VARIANTS = {
    "conservative": {"t1": 0.50, "t2": 0.60, "r2_min_children": 2,
                     "note": "推荐版 A：R1=0.5 ＋ R2 仅 ≥2 子框"},
    "aggressive": {"t1": 0.35, "t2": 0.50, "r2_min_children": 2,
                   "note": "激进版：R1=0.35 ＋ R2 仅 ≥2 子框"},
}


# ---------------------------------------------------------------------------
# 命名模块（按文件路径加载；`feicui/app.py` 会遮蔽包名，故不 import 包）
# ---------------------------------------------------------------------------

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_naming():
    return _load_module(REPO / "server" / "app" / "naming.py", "feicui_naming_for_dedup")


# ---------------------------------------------------------------------------
# 纯几何
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    id: int
    pdf_name: str
    page: int
    idx: int
    x1: float
    y1: float
    x2: float
    y2: float
    img_path_tiff: str | None = None
    img_path: str | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.pdf_name, self.page, self.idx)

    def xyxy(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def area(self) -> float:
        return max(self.x2 - self.x1, 0.0) * max(self.y2 - self.y1, 0.0)

    def w(self) -> float:
        return self.x2 - self.x1

    def h(self) -> float:
        return self.y2 - self.y1


def iou(a: Box | tuple, b: Box | tuple) -> float:
    """交并比（空并集 ⇒ 0.0）。支持 Box 或 `(x1,y1,x2,y2)`。"""
    ax1, ay1, ax2, ay2 = a.xyxy() if isinstance(a, Box) else a
    bx1, by1, bx2, by2 = b.xyxy() if isinstance(b, Box) else b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = aa + ba - inter
    return inter / union if union > 0 else 0.0


def contains(a: Box, b: Box, tol: float = TOL_PX) -> bool:
    """`a` 是否包含 `b`（四边容差 `tol` px）。"""
    ax1, ay1, ax2, ay2 = a.xyxy()
    bx1, by1, bx2, by2 = b.xyxy()
    return (ax1 - tol <= bx1 and ay1 - tol <= by1 and ax2 + tol >= bx2 and ay2 + tol >= by2)


def area_ratio(small: Box, big: Box) -> float:
    """`area(small)/area(big)`（big 面积为 0 ⇒ 0.0）。"""
    ba = big.area()
    return small.area() / ba if ba > 0 else 0.0


def _median(xs):
    return statistics.median(xs) if xs else 0.0


# ---------------------------------------------------------------------------
# 页内去重（纯函数）
# ---------------------------------------------------------------------------

@dataclass
class Mark:
    """一条「标记为重复」的行。"""
    box_id: int
    book: str
    page: int
    idx: int
    reason: str            # "R1" | "R2"
    metric: float          # R1 ⇒ IoU；R2 ⇒ area(child)/area(frame)
    partner_idx: int       # R1 ⇒ 簇代表；R2 ⇒ 被桥接的最大子框
    partner_id: int
    also_qualifies: list = field(default_factory=list)  # 同时满足的另一规则（透明化）
    children: list = field(default_factory=list)        # R2：A 捕获的所有子框 idx

    def to_row(self, order: int) -> dict:
        return {
            "order": order,
            "id": self.box_id, "book": self.book, "page": self.page, "idx": self.idx,
            "reason": self.reason, "metric": round(self.metric, 6),
            "partner_id": self.partner_id, "partner_idx": self.partner_idx,
            "also_qualifies": ",".join(self.also_qualifies),
            "children_idx": ",".join(str(c) for c in self.children),
        }


@dataclass
class PageResult:
    kept: list
    marked: list
    clusters: list


def _pick_representative(cluster: list, page_median_area: float, tie_break: str) -> Box:
    """簇代表：`area_max` ⇒ 面积最大；`area_median` ⇒ 面积最接近**页内中位面积**。

    并列时一律再按「面积较大 → 原 idx 较小」定序，保证确定性。
    """
    if tie_break == "area_median":
        return sorted(cluster, key=lambda b: (abs(b.area() - page_median_area), -b.area(), b.idx))[0]
    return sorted(cluster, key=lambda b: (-b.area(), b.idx))[0]


def dedup_page(boxes: list, t1: float, t2: float, tol: float = TOL_PX,
               tie_break: str = "area_max", order: str = "r2_first",
               r2_min_children: int = DEFAULT_R2_MIN_CHILDREN,
               r2_enabled: bool = True) -> PageResult:
    """单页去重（纯函数）。返回「保留 / 标记」与 R1 簇信息。

    `r2_min_children`：R2 收窄口径——大框须桥接 **≥ 该数**个子框才丢（默认 2；1 ＝ 旧口径）。
    `r2_enabled=False`：整条 R2 关闭（仅做 R1；用于方案 C 对照）。
    """
    page_median_area = _median([b.area() for b in boxes])
    marked: dict[int, Mark] = {}
    by_id = {b.id: b for b in boxes}
    r1_edges: list[tuple] = []
    r2_edges: list[tuple] = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            v = iou(a, b)
            if v >= t1:
                r1_edges.append((a, b, v))
            for big, small in ((a, b), (b, a)):
                if contains(big, small, tol) and 0.0 < area_ratio(small, big) < t2:
                    r2_edges.append((big, small, area_ratio(small, big)))

    def apply_r2(survivors: set) -> None:
        """在 `survivors` 上执行 R2：丢 A（组框），A 含多子只丢一次。"""
        kids: dict[int, list] = {}
        for big, small, ratio in r2_edges:
            if big.id in survivors and small.id in survivors:
                kids.setdefault(big.id, []).append((small, ratio))
        for big_id, cs in kids.items():
            if len(cs) < r2_min_children:   # 收窄：单子框（不足阈值）一律不动
                continue
            big = by_id[big_id]
            partner = sorted(cs, key=lambda cs_: (-cs_[0].area(), cs_[0].idx))[0]
            marked[big_id] = Mark(
                box_id=big_id, book=big.pdf_name, page=big.page, idx=big.idx, reason="R2",
                metric=partner[1], partner_id=partner[0].id, partner_idx=partner[0].idx,
                children=[c[0].idx for c in sorted(cs, key=lambda x: x[0].idx)],
            )
            survivors.discard(big_id)

    def apply_r1(survivors: set) -> list:
        parent = {bid: bid for bid in survivors}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        for a, b, _v in r1_edges:
            if a.id in survivors and b.id in survivors:
                union(a.id, b.id)
        groups: dict[int, list] = {}
        for bid in survivors:
            groups.setdefault(find(bid), []).append(bid)
        clusters = []
        for root, members in groups.items():
            cluster = sorted((by_id[m] for m in members), key=lambda b: b.idx)
            if len(cluster) > 1:
                clusters.append(cluster)
                rep = _pick_representative(cluster, page_median_area, tie_break)
                for b in cluster:
                    if b.id == rep.id:
                        continue
                    v = max(iou(b, o) for o in cluster if o.id != b.id)
                    marked[b.id] = Mark(
                        box_id=b.id, book=b.pdf_name, page=b.page, idx=b.idx, reason="R1",
                        metric=v, partner_id=rep.id, partner_idx=rep.idx,
                    )
        return clusters

    remaining = {b.id for b in boxes}
    if order == "r2_first":
        if r2_enabled:
            apply_r2(remaining)
        clusters = apply_r1(remaining)
    elif order == "r1_first":
        clusters = apply_r1(remaining)
        # R2 只在 R1 幸存者上判（否则会把簇代表也丢掉、留下空簇）
        if r2_enabled:
            apply_r2({b.id for b in boxes if b.id not in marked})
    else:
        raise ValueError(f"order 须为 r2_first / r1_first：{order!r}")

    # 透明化：标记行「同时」满足的另一规则
    r1_ids = {a.id for a, _b, _v in r1_edges} | {b.id for _a, b, _v in r1_edges}
    r2_all = {m.box_id for m in marked.values() if m.reason == "R2"}
    for m in marked.values():
        if m.reason == "R1" and m.box_id in r2_all:
            m.also_qualifies.append("R2")
        if m.reason == "R2" and m.box_id in r1_ids:
            m.also_qualifies.append("R1")

    kept = [b for b in boxes if b.id not in marked]
    return PageResult(kept=kept, marked=list(marked.values()), clusters=clusters)


# ---------------------------------------------------------------------------
# 全库评估
# ---------------------------------------------------------------------------

def load_rows(db: Path, books: list | None = None, page_from: int | None = None,
              page_to: int | None = None) -> list:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = ("SELECT id, pdf_name, page, idx, x1, y1, x2, y2, img_path, img_path_tiff "
               "FROM stamps")
        params: list = []
        where = []
        if books:
            where.append("pdf_name IN (%s)" % ",".join("?" * len(books)))
            params += books
        if page_from is not None:
            where.append("page >= ?")
            params.append(page_from)
        if page_to is not None:
            where.append("page <= ?")
            params.append(page_to)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY pdf_name, page, idx"
        rows = list(conn.execute(sql, params))
    finally:
        conn.close()
    return [Box(id=r["id"], pdf_name=r["pdf_name"], page=r["page"], idx=r["idx"],
                x1=r["x1"], y1=r["y1"], x2=r["x2"], y2=r["y2"],
                img_path=r["img_path"], img_path_tiff=r["img_path_tiff"]) for r in rows]


def group_pages(boxes: list) -> dict:
    pages: dict = {}
    for b in boxes:
        pages.setdefault((b.pdf_name, b.page), []).append(b)
    return pages


def evaluate(boxes: list, t1: float, t2: float, tol: float = TOL_PX,
             tie_break: str = "area_max", order: str = "r2_first",
             r2_min_children: int = DEFAULT_R2_MIN_CHILDREN,
             r2_enabled: bool = True) -> dict:
    """全量评估 ⇒ 结构化读数（不落盘）。"""
    pages = group_pages(boxes)
    all_marks: list = []
    kept: list = []
    clusters_all: list = []
    pages_affected: set = set()
    for pk, bs in pages.items():
        pr = dedup_page(bs, t1=t1, t2=t2, tol=tol, tie_break=tie_break, order=order,
                        r2_min_children=r2_min_children, r2_enabled=r2_enabled)
        kept.extend(pr.kept)
        all_marks.extend(pr.marked)
        for cl in pr.clusters:
            clusters_all.append((pk, [b.idx for b in cl]))
        if pr.marked:
            pages_affected.add(pk)
    return {
        "params": {"t1": t1, "t2": t2, "tol": tol, "tie_break": tie_break, "order": order,
                   "r2_min_children": r2_min_children, "r2_enabled": r2_enabled},
        "kept": kept,
        "marked": all_marks,
        "clusters": clusters_all,
        "pages_affected": pages_affected,
        "n_pages": len(pages),
    }


# ---------------------------------------------------------------------------
# 统计 / 边界带 / 命名影响
# ---------------------------------------------------------------------------

def _book_of(name: str) -> str:
    return name


def summarize(res: dict, boxes: list) -> dict:
    marked = res["marked"]
    by_reason = {"R1": [m for m in marked if m.reason == "R1"],
                 "R2": [m for m in marked if m.reason == "R2"]}
    out = {
        "rows_total": len(boxes),
        "rows_kept": len(res["kept"]),
        "rows_marked": len(marked),
        "rows_marked_R1": len(by_reason["R1"]),
        "rows_marked_R2": len(by_reason["R2"]),
        "rows_marked_pct": round(100.0 * len(marked) / max(len(boxes), 1), 2),
        "pages_total": res["n_pages"],
        "pages_affected": len(res["pages_affected"]),
        "r1_clusters": len(res["clusters"]),
        "r1_cluster_size_hist": {},
        "both_qualify": sum(1 for m in marked if m.also_qualifies),
        "by_book": {},
    }
    hist: dict = {}
    for pk, idxs in res["clusters"]:
        hist[len(idxs)] = hist.get(len(idxs), 0) + 1
    out["r1_cluster_size_hist"] = dict(sorted(hist.items()))
    marked_ids = {m.box_id for m in marked}
    for b in boxes:
        d = out["by_book"].setdefault(b.pdf_name, {
            "rows_total": 0, "rows_marked": 0, "rows_marked_R1": 0, "rows_marked_R2": 0,
            "pages_affected": 0})
        d["rows_total"] += 1
        if b.id in marked_ids:
            d["rows_marked"] += 1
    for m in marked:
        d = out["by_book"].setdefault(m.book, {
            "rows_total": 0, "rows_marked": 0, "rows_marked_R1": 0, "rows_marked_R2": 0,
            "pages_affected": 0})
        d[f"rows_marked_{m.reason}"] += 1
    for book, d in out["by_book"].items():
        d["pages_affected"] = len({p for (bk, p) in res["pages_affected"] if bk == book})
        d["rows_marked_pct"] = round(100.0 * d["rows_marked"] / max(d["rows_total"], 1), 2)
    return out


def boundary_bands(boxes: list, tol: float = TOL_PX) -> dict:
    """边界带：IoU 候选对（同页两两）与 面积比 候选对（同页包含）逐带给数。"""
    pages = group_pages(boxes)
    iou_pairs, ratio_pairs = [], []
    for pk, bs in pages.items():
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                v = iou(a, b)
                if v > 0:
                    iou_pairs.append((v, pk, a.idx, b.idx))
                for big, small in ((a, b), (b, a)):
                    if contains(big, small, tol):
                        r = area_ratio(small, big)
                        if 0.0 < r < 1.0:
                            ratio_pairs.append((r, pk, big.idx, small.idx))

    def band_hist(pairs, edges):
        out = []
        for lo, hi in zip(edges, edges[1:]):
            sel = [p for p in pairs if lo <= p[0] < hi]
            out.append({
                "lo": lo, "hi": hi, "pairs": len(sel),
                "pages": len({p[1] for p in sel}),
            })
        return out

    iou_edges = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80, 0.90, 1.0001]
    ratio_edges = [0.10, 0.20, 0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 1.0]
    return {
        "iou_bands": band_hist(iou_pairs, iou_edges),
        "ratio_bands": band_hist(ratio_pairs, ratio_edges),
        "iou_pairs": [{"iou": round(v, 6), "book": k[0], "page": k[1], "idx_a": ia, "idx_b": ib}
                      for v, k, ia, ib in sorted(iou_pairs, reverse=True)],
        "ratio_pairs": [{"ratio": round(r, 6), "book": k[0], "page": k[1], "big_idx": bi, "small_idx": si}
                        for r, k, bi, si in sorted(ratio_pairs)],
        "focus": {
            "iou_in_[0.35,0.5)": sum(1 for v, *_ in iou_pairs if 0.35 <= v < 0.5),
            "iou_in_[0.4,0.5)": sum(1 for v, *_ in iou_pairs if 0.4 <= v < 0.5),
            "ratio_in_[0.5,0.7)": sum(1 for r, *_ in ratio_pairs if 0.5 <= r < 0.7),
        },
    }


def naming_impact(boxes: list, res: dict, dir_keys: dict) -> dict:
    """去重与命名的关系：页内 `(C,R)` 是否重排；多少 TIFF/O 件会变冗余。"""
    naming = load_naming()
    pages = group_pages(boxes)
    marked_ids = {m.box_id for m in res["marked"]}
    kept_ids = {b.id for b in res["kept"]}
    pages_cr_changed = []
    pages_cols_changed = []
    rows_cr_changed = 0
    marked_rows_with_tiff = 0
    marked_tiff_files_exist = 0
    marked_o_files_exist = 0
    cr_changed_tiff_exist = 0
    cr_changed_o_exist = 0
    for pk, bs in pages.items():
        before = naming.assign_cr([b.xyxy() for b in bs])
        after_boxes = [b for b in bs if b.id in kept_ids]
        if not after_boxes:
            continue
        after = naming.assign_cr([b.xyxy() for b in after_boxes])
        bmap = {b.id: before[i] for i, b in enumerate(bs)}
        amap = {b.id: after[i] for i, b in enumerate(after_boxes)}
        n_changed = sum(1 for bid, cr in amap.items() if bmap[bid] != cr)
        rows_cr_changed += n_changed
        if n_changed:
            pages_cr_changed.append({"book": pk[0], "page": pk[1], "rows_cr_changed": n_changed})
        nc_before = naming.n_columns(before)
        nc_after = naming.n_columns(after)
        if nc_before != nc_after:
            pages_cols_changed.append({"book": pk[0], "page": pk[1],
                                       "cols_before": nc_before, "cols_after": nc_after})
        for b in bs:
            if b.id in marked_ids and b.img_path_tiff:
                marked_rows_with_tiff += 1
                p = REPO / b.img_path_tiff
                if p.exists():
                    marked_tiff_files_exist += 1
                stem, dot, ext = str(p).rpartition(".")
                if Path(f"{stem}-O{dot}{ext}").exists():
                    marked_o_files_exist += 1
            if b.id in amap and bmap[b.id] != amap[b.id] and b.img_path_tiff:
                p = REPO / b.img_path_tiff
                if p.exists():
                    cr_changed_tiff_exist += 1
                stem, dot, ext = str(p).rpartition(".")
                if Path(f"{stem}-O{dot}{ext}").exists():
                    cr_changed_o_exist += 1
    return {
        "note": ("只读估算：不作结论式断言。`cr_changed_*` 行指去重后该行仍保留、但页内 "
                 "`(C,R)` 秩次变了 ⇒ 现有磁盘名与新命名不符 ⇒ 该 `X.tiff` 与 `X-O.tiff` 成为"
                 "「名不符实」件（冗余口径 = 需要改名的旧件，非删除）。"),
        "rows_kept_with_cr_changed": rows_cr_changed,
        "pages_with_cr_changed": len(pages_cr_changed),
        "pages_with_column_count_changed": len(pages_cols_changed),
        "cr_changed_sample": pages_cr_changed[:20],
        "columns_changed_sample": pages_cols_changed[:20],
        "marked_rows_with_tiff_path": marked_rows_with_tiff,
        "marked_tiff_on_disk": marked_tiff_files_exist,
        "marked_o_on_disk": marked_o_files_exist,
        "cr_changed_rows_tiff_on_disk": cr_changed_tiff_exist,
        "cr_changed_rows_o_on_disk": cr_changed_o_exist,
        "redundant_files_estimate": {
            "from_marked_rows": marked_tiff_files_exist + marked_o_files_exist,
            "from_renamed_rows": cr_changed_tiff_exist + cr_changed_o_exist,
            "total": (marked_tiff_files_exist + marked_o_files_exist
                      + cr_changed_tiff_exist + cr_changed_o_exist),
        },
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def run_variant(boxes: list, label: str, t1: float, t2: float, tol: float,
                tie_break: str, order: str, dir_keys: dict,
                r2_min_children: int = DEFAULT_R2_MIN_CHILDREN,
                r2_enabled: bool = True) -> dict:
    res = evaluate(boxes, t1, t2, tol=tol, tie_break=tie_break, order=order,
                   r2_min_children=r2_min_children, r2_enabled=r2_enabled)
    summary = summarize(res, boxes)
    summary["label"] = label
    summary["variant"] = {"t1": t1, "t2": t2, "tol": tol, "tie_break": tie_break,
                          "order": order, "r2_min_children": r2_min_children,
                          "r2_enabled": r2_enabled}
    summary["naming_impact"] = naming_impact(boxes, res, dir_keys)
    summary["marked_rows"] = [
        {**m.to_row(i), "id": m.box_id, "book": m.book, "page": m.page, "idx": m.idx}
        for i, m in enumerate(sorted(res["marked"], key=lambda m: (m.book, m.page, m.idx)))
    ]
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="离线去重标定（只读）")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--book", action="append", default=None)
    ap.add_argument("--page-from", type=int, default=None)
    ap.add_argument("--page-to", type=int, default=None)
    ap.add_argument("--tol", type=float, default=TOL_PX)
    ap.add_argument("--tie-break", default="area_max", choices=["area_max", "area_median"])
    ap.add_argument("--order", default="r2_first", choices=["r2_first", "r1_first"])
    ap.add_argument("--t1", type=float, default=None)
    ap.add_argument("--t2", type=float, default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--both", action="store_true", help="跑两版阈值变体（conservative / aggressive）")
    ap.add_argument("--r2-min-children", type=int, default=DEFAULT_R2_MIN_CHILDREN,
                    help="R2 收窄阈值：大框须桥接 ≥ 该数个已检出子框才丢（默认 2；1=旧口径）")
    ap.add_argument("--r2-off", action="store_true", help="整条关闭 R2（仅做 R1；用于方案 C 对照）")
    ap.add_argument("--no-sidecar", action="store_true",
                    help="只写 variant_<label>.json；不写 bands/diff/affected/summary（避免覆盖推荐版读数）")
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    boxes = load_rows(Path(args.db), args.book, args.page_from, args.page_to)
    print(f"[load] {args.db} rows={len(boxes)}")
    dir_keys = json.loads((REPO / "config" / "book_dir_keys.json").read_text(encoding="utf-8"))

    results = {}
    r2mc = args.r2_min_children
    r2on = not args.r2_off
    if args.both:
        variants = {k: dict(v) for k, v in VARIANTS.items()}
    else:
        if args.t1 is None or args.t2 is None:
            ap.error("非 --both 模式须同时给 --t1 与 --t2")
        variants = {args.label or f"t1_{args.t1}_t2_{args.t2}":
                    {"t1": args.t1, "t2": args.t2, "r2_min_children": r2mc}}

    for label, v in variants.items():
        summary = run_variant(boxes, label, v["t1"], v["t2"], args.tol, args.tie_break,
                              args.order, dir_keys,
                              r2_min_children=v.get("r2_min_children", r2mc),
                              r2_enabled=r2on)
        results[label] = summary
        r = json.dumps(summary, ensure_ascii=False)
        digest = hashlib.sha256(r.encode("utf-8")).hexdigest()[:16]
        summary["_sha256_16"] = digest
        (outdir / f"variant_{label}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.no_sidecar:
        for label, s in results.items():
            print(f"[no-sidecar] {label}: kept={s['rows_kept']} marked={s['rows_marked']} "
                  f"(R1={s['rows_marked_R1']} R2={s['rows_marked_R2']}) "
                  f"r2_min_children={s['variant']['r2_min_children']} enabled={s['variant']['r2_enabled']}")
        return 0

    # 两版差异（哪些行只有激进版会去掉）
    diff = {}
    if len(results) == 2:
        la, lb = list(results.keys())
        ma = {m["id"] for m in results[la]["marked_rows"]}
        mb = {m["id"] for m in results[lb]["marked_rows"]}
        only_b = sorted(mb - ma)
        only_a = sorted(ma - mb)
        meta = {b.id: b for b in boxes}
        diff = {
            "labels": [la, lb],
            "marked_only_in": {
                lb: [{"id": i, "book": meta[i].pdf_name, "page": meta[i].page, "idx": meta[i].idx}
                     for i in only_b],
                la: [{"id": i, "book": meta[i].pdf_name, "page": meta[i].page, "idx": meta[i].idx}
                     for i in only_a],
            },
            "counts": {f"only_{lb}": len(only_b), f"only_{la}": len(only_a)},
        }
        (outdir / "variant_diff.json").write_text(
            json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

    # 边界带（与阈值无关的两两候选，供 Kevin 选阈值）
    bands = boundary_bands(boxes, tol=args.tol)
    (outdir / "boundary_bands.json").write_text(
        json.dumps(bands, ensure_ascii=False, indent=2), encoding="utf-8")
    with (outdir / "iou_pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["iou", "book", "page", "idx_a", "idx_b"])
        for p in bands["iou_pairs"]:
            w.writerow([p["iou"], p["book"], p["page"], p["idx_a"], p["idx_b"]])
    with (outdir / "ratio_pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ratio", "book", "page", "big_idx", "small_idx"])
        for p in bands["ratio_pairs"]:
            w.writerow([p["ratio"], p["book"], p["page"], p["big_idx"], p["small_idx"]])
    print("[bands] IoU[0.35,0.5)=%d IoU[0.4,0.5)=%d ratio[0.5,0.7)=%d" % (
        bands["focus"]["iou_in_[0.35,0.5)"], bands["focus"]["iou_in_[0.4,0.5)"],
        bands["focus"]["ratio_in_[0.5,0.7)"]))
    for b in bands["iou_bands"]:
        if b["pairs"]:
            print("   IoU [%.2f,%.2f) pairs=%d pages=%d" % (b["lo"], b["hi"], b["pairs"], b["pages"]))
    for b in bands["ratio_bands"]:
        if b["pairs"]:
            print("   ratio [%.2f,%.2f) pairs=%d pages=%d" % (b["lo"], b["hi"], b["pairs"], b["pages"]))

    # 受影响行（双边口径：出现在任一候选对里的行）——用于与 Zang 的 1234 对账
    affected_ids = set()
    meta = {b.id: b for b in boxes}
    slot = {(b.pdf_name, b.page, b.idx): b.id for b in boxes}
    for p in bands["iou_pairs"]:
        if p["iou"] >= 0.4:
            for ix in (p["idx_a"], p["idx_b"]):
                if (p["book"], p["page"], ix) in slot:
                    affected_ids.add(slot[(p["book"], p["page"], ix)])
    for p in bands["ratio_pairs"]:
        if p["ratio"] < 0.42:
            for ix in (p["big_idx"], p["small_idx"]):
                if (p["book"], p["page"], ix) in slot:
                    affected_ids.add(slot[(p["book"], p["page"], ix)])
    per_book: dict = {}
    for i in affected_ids:
        per_book[meta[i].pdf_name] = per_book.get(meta[i].pdf_name, 0) + 1
    reconcile = {"affected_rows_two_sided": len(affected_ids), "by_book": per_book,
                 "pct": round(100.0 * len(affected_ids) / max(len(boxes), 1), 2)}
    (outdir / "affected_rows_reconcile.json").write_text(
        json.dumps(reconcile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[reconcile] 受影响行（双边）={len(affected_ids)} / {len(boxes)} = {reconcile['pct']}%")
    print("   ", {k[:14]: v for k, v in sorted(per_book.items(), key=lambda kv: -kv[1])})

    # 人读摘要（终端只打 top 几行；全量落盘）
    lines = []
    for label, s in results.items():
        lines.append(f"== {label} T1={s['variant']['t1']} T2={s['variant']['t2']} "
                     f"tie={s['variant']['tie_break']} order={s['variant']['order']}")
        lines.append(f"   rows {s['rows_total']} → kept {s['rows_kept']} / marked "
                     f"{s['rows_marked']} (R1={s['rows_marked_R1']}, R2={s['rows_marked_R2']}, "
                     f"{s['rows_marked_pct']}%)  pages {s['pages_affected']}/{s['pages_total']}"
                     f"  both-qualify={s['both_qualify']}")
        for book, d in sorted(s["by_book"].items(), key=lambda kv: -kv[1]["rows_marked"]):
            lines.append(f"     {book[:34]:34s} marked {d['rows_marked']:5d}/{d['rows_total']:5d} "
                         f"(R1={d['rows_marked_R1']:4d} R2={d['rows_marked_R2']:4d}) "
                         f"pages={d['pages_affected']}")
        ni = s["naming_impact"]
        lines.append(f"   naming: rows_kept_with_cr_changed={ni['rows_kept_with_cr_changed']} "
                     f"pages={ni['pages_with_cr_changed']} "
                     f"redundant_files≈{ni['redundant_files_estimate']['total']}")
    if diff:
        lines.append(f"== diff: {diff['counts']}")
    print("\n".join(lines))
    (outdir / "variant_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
