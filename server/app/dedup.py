#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""印面检测去重 —— **方案 A 的生产单一实现**（Kong / 去重方案 A 落地，2026-10-11）。

**口径真源**：`ops/dedup-calibration/README.md`（规则定义 / R2 收窄理由 / 两误杀锚点），
**标定 commit `f5b901f`**（离线读数：全量 8708 行 ⇒ 保留 8440 / 标记 268，其中 R1 143 / R2 125）。

**唯一实现声明**：本模块是去重规则的**唯一实现**。三处消费方一律从此取规则、**不得另存第二份**：
  1. worker（`server/worker/feicui_worker.py`）—— **新 job** 检测后去重（写盘/返回之前）；
  2. 历史标记（`server/app/dedup_apply.py`）—— 历史 `stamps` 行加法列标记；
  3. 离线标定器（`ops/dedup-calibration/dedup_eval.py`）—— 委托本模块的几何/规则核。
本模块**纯 stdlib**（无 cv2 / numpy / sqlite）⇒ 接口层 `server/.venv` 与 worker 侧 `feicui/venv` 都可加载。

## 规则（方案 A，逐字照标定件）

* **R1 近重复**：同页两框 **bbox IoU ≥ T1** ⇒ 只留一枚（同页 union-find 传递成簇，每簇留 1 枚）。
  代表选取 `tie_break="area_max"`（留面积较大者，并列再按面积、原 idx 定序）。
* **R2 组框**：同页 A **包含** B（四边容差 `TOL_PX=8 px`）且 `area(B)/area(A) < T2`
  **且 A 桥接 ≥ `R2_MIN_CHILDREN=2` 个已检出子框** ⇒ 丢 A（组框、留子框）。
  **单子框（不足阈值）一律不动** —— 已实测：单子框里 93% 是「完整大印＋其碎片」，删大框＝误杀
  （两误杀锚点：福庵 p110 idx0 / p74 idx0，见标定件 §1.1）。
* **合成顺序 `r2_first`**（默认）：先丢组框，再在幸存者上做 R1 聚类。

阈值一律**单点可改**常量（下方 `#:` 行），改动即改变 `ALGO_VERSION` 记账签名。
"""
from __future__ import annotations

import statistics

# --------------------------------------------------------------------------- 单点可改常量（方案 A）
#: 算法 / 口径版本（幂等重算记账用；规则或阈值一变即应升版）。
ALGO_VERSION = "dedup-A-v1"

#: **R1** 近重复阈值：同页两框 bbox IoU ≥ 此值 ⇒ 只留一枚（标定件 A 推荐版 T1=0.5）。
T1_DEFAULT = 0.50

#: **R2** 组框：包含判定四边容差（px）——标定件给定。
TOL_PX = 8.0

#: **R2** 收窄口径：大框须桥接 **≥ 此数** 个已检出子框才丢（标定件收窄结论＝2；1＝已作废旧口径）。
R2_MIN_CHILDREN = 2

#: **R2** 面积比上限：`area(child)/area(frame) < 此值` 才算「组框候选」。
T2_DEFAULT = 0.60

#: 簇代表选取（`area_max` ＝ 留面积较大者；`area_median` ＝ 留最接近页内中位者）。
TIE_BREAK_DEFAULT = "area_max"

#: 合成顺序（`r2_first` ＝ 先 R2 后 R1，推荐；`r1_first` 仅作风险对照）。
ORDER_DEFAULT = "r2_first"

#: 标签值域（写入 `stamps.dup_kind`）——**两类分开**，可分别回溯。
KIND_NEAR_DUPLICATE = "near_duplicate"   # R1
KIND_GROUP_FRAME = "group_frame"         # R2


def algo_signature(t1: float = T1_DEFAULT, t2: float = T2_DEFAULT, tol: float = TOL_PX,
                   r2_min_children: int = R2_MIN_CHILDREN) -> str:
    """算法版本 ＋ 阈值的记账签名（写 `stamps.dup_algo`；幂等重算据此判「是否同一口径」）。"""
    return f"{ALGO_VERSION};t1={t1};t2={t2};tol={tol};minc={r2_min_children}"


# --------------------------------------------------------------------------- 几何（纯函数）
def _xyxy(o) -> tuple[float, float, float, float]:
    """`Box` / `dict{id,x1,y1,x2,y2}` → `(x1,y1,x2,y2)`。"""
    if isinstance(o, dict):
        return (o["x1"], o["y1"], o["x2"], o["y2"])
    return (o.x1, o.y1, o.x2, o.y2)


def _bid(o) -> int:
    return int(o["id"] if isinstance(o, dict) else o.id)


def _bidx(o) -> int:
    return int(o["idx"] if isinstance(o, dict) else o.idx)


def _area(o) -> float:
    x1, y1, x2, y2 = _xyxy(o)
    return max(x2 - x1, 0.0) * max(y2 - y1, 0.0)


def iou(a, b) -> float:
    """交并比（空并集 ⇒ 0.0）。支持 `Box` 或 `dict` 或裸 `(x1,y1,x2,y2)`。"""
    ax1, ay1, ax2, ay2 = a.xyxy() if hasattr(a, "xyxy") else (a if isinstance(a, tuple) else _xyxy(a))
    bx1, by1, bx2, by2 = b.xyxy() if hasattr(b, "xyxy") else (b if isinstance(b, tuple) else _xyxy(b))
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = aa + ba - inter
    return inter / union if union > 0 else 0.0


def contains(big, small, tol: float = TOL_PX) -> bool:
    """`big` 是否包含 `small`（四边容差 `tol` px）。"""
    ax1, ay1, ax2, ay2 = _xyxy(big)
    bx1, by1, bx2, by2 = _xyxy(small)
    return (ax1 - tol <= bx1 and ay1 - tol <= by1 and ax2 + tol >= bx2 and ay2 + tol >= by2)


def area_ratio(small, big) -> float:
    """`area(small)/area(big)`（big 面积为 0 ⇒ 0.0）。"""
    ba = _area(big)
    return _area(small) / ba if ba > 0 else 0.0


def _median(xs):
    return statistics.median(xs) if xs else 0.0


# --------------------------------------------------------------------------- 结果类型
# ★ **不用 `@dataclass`**（P0 修复 2026-10-11）：本模块由 worker / dedup_apply / dedup_eval
#   以**按文件路径**方式加载（`feicui/app.py` 遮蔽 `server/app` 包名）。`@dataclass` 在装饰期
#   会经 `dataclasses` → `sys.modules.get(cls.__module__).__dict__` 解析注解；若加载器未先把
#   模块注册进 `sys.modules`，`sys.modules.get()` 得 `None` ⇒
#   `AttributeError: 'NoneType' object has no attribute '__dict__'`，**worker 在导入阶段即崩**。
#   两道防线都做：① 加载器（`feicui_worker._load_by_path` / `dedup_apply._load_core` /
#   `dedup_eval._load_module`）先 `sys.modules[name] = mod` 再 `exec_module`；② 本模块用**普通类**
#   （不依赖 `sys.modules`），使本模块在任何加载器下都安全。字段与旧 dataclass 逐一对应。
class DedupMark:
    """一条「标记为重复」的行。"""

    __slots__ = ("box_id", "idx", "kind", "keeper_id", "keeper_idx", "metric",
                 "children_idx", "also")

    def __init__(self, box_id: int, idx: int, kind: str, keeper_id: int, keeper_idx: int,
                 metric: float, children_idx=None, also=None):
        self.box_id = box_id
        self.idx = idx
        self.kind = kind                 # near_duplicate(R1) | group_frame(R2)
        self.keeper_id = keeper_id       # 保留行 id（R1 ⇒ 簇代表；R2 ⇒ 桥接的最大子框）
        self.keeper_idx = keeper_idx
        self.metric = metric             # R1 ⇒ IoU；R2 ⇒ area(child)/area(frame)
        self.children_idx = list(children_idx) if children_idx else []   # R2：A 捕获的所有子框 idx
        self.also = list(also) if also else []                           # 同时满足另一规则（透明化）

    @property
    def reason(self) -> str:
        return "R1" if self.kind == KIND_NEAR_DUPLICATE else "R2"

    def __repr__(self) -> str:
        return (f"DedupMark(box_id={self.box_id}, idx={self.idx}, kind={self.kind!r}, "
                f"keeper_id={self.keeper_id}, metric={self.metric})")


class PageDedup:
    """单页去重结果（普通类，见上「不用 @dataclass」说明）。"""

    __slots__ = ("kept_ids", "marks", "clusters")

    def __init__(self, kept_ids: list, marks: list, clusters: list):
        self.kept_ids = kept_ids
        self.marks = marks
        self.clusters = clusters          # list[list[box_id]]（R1 簇，仅 size>1）

    def __repr__(self) -> str:
        return (f"PageDedup(kept={len(self.kept_ids)}, marks={len(self.marks)}, "
                f"clusters={len(self.clusters)})")


# --------------------------------------------------------------------------- 页内去重（纯函数）
def _pick_representative(cluster: list, page_median_area: float, tie_break: str):
    """簇代表：`area_max` ⇒ 面积最大；`area_median` ⇒ 面积最接近**页内中位面积**。

    并列时一律再按「面积较大 → 原 idx 较小」定序，保证确定性。
    """
    if tie_break == "area_median":
        return sorted(cluster, key=lambda b: (abs(_area(b) - page_median_area), -_area(b), _bidx(b)))[0]
    return sorted(cluster, key=lambda b: (-_area(b), _bidx(b)))[0]


def dedup_page(rects: list, *, t1: float | None = None, t2: float | None = None,
               tol: float = TOL_PX, r2_min_children: int = R2_MIN_CHILDREN,
               tie_break: str = TIE_BREAK_DEFAULT, order: str = ORDER_DEFAULT,
               r2_enabled: bool = True) -> PageDedup:
    """单页去重（纯函数）。`rects` ＝ 同页框列表（`Box` / `dict`，须含 id/idx/x1..y2）。

    返回 `PageDedup(kept_ids, marks, clusters)`：`kept_ids` 为保留框 id，`marks` 为标记框。
    `t1` / `t2` 缺省取单点常量。
    """
    t1 = T1_DEFAULT if t1 is None else t1
    t2 = T2_DEFAULT if t2 is None else t2
    boxes = list(rects)
    page_median_area = _median([_area(b) for b in boxes])
    marked: dict[int, DedupMark] = {}
    by_id = {_bid(b): b for b in boxes}

    r1_edges: list[tuple] = []   # (a, b, iou)
    r2_edges: list[tuple] = []   # (big, small, ratio)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            v = iou(a, b)
            if v >= t1:
                r1_edges.append((a, b, v))
            for big, small in ((a, b), (b, a)):
                if contains(big, small, tol) and 0.0 < area_ratio(small, big) < t2:
                    r2_edges.append((big, small, area_ratio(small, big)))

    def apply_r2(survivors: set) -> None:
        """在 `survivors` 上执行 R2：丢 A（组框），A 含多子只丢一次；单子框（< r2_min_children）不动。"""
        kids: dict[int, list] = {}
        for big, small, ratio in r2_edges:
            if _bid(big) in survivors and _bid(small) in survivors:
                kids.setdefault(_bid(big), []).append((small, ratio))
        for big_id, cs in kids.items():
            if len(cs) < r2_min_children:   # 收窄：单子框（不足阈值）一律不动
                continue
            big = by_id[big_id]
            partner = sorted(cs, key=lambda c: (-_area(c[0]), _bidx(c[0])))[0]
            marked[big_id] = DedupMark(
                box_id=big_id, idx=_bidx(big), kind=KIND_GROUP_FRAME,
                keeper_id=_bid(partner[0]), keeper_idx=_bidx(partner[0]), metric=partner[1],
                children_idx=[_bidx(c[0]) for c in sorted(cs, key=lambda x: _bidx(x[0]))],
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
            if _bid(a) in survivors and _bid(b) in survivors:
                union(_bid(a), _bid(b))
        groups: dict[int, list] = {}
        for bid in survivors:
            groups.setdefault(find(bid), []).append(bid)
        clusters = []
        for _root, members in groups.items():
            cluster = sorted((by_id[m] for m in members), key=lambda b: _bidx(b))
            if len(cluster) > 1:
                clusters.append([_bid(b) for b in cluster])
                rep = _pick_representative(cluster, page_median_area, tie_break)
                for b in cluster:
                    if _bid(b) == _bid(rep):
                        continue
                    v = max(iou(b, o) for o in cluster if _bid(o) != _bid(b))
                    marked[_bid(b)] = DedupMark(
                        box_id=_bid(b), idx=_bidx(b), kind=KIND_NEAR_DUPLICATE,
                        keeper_id=_bid(rep), keeper_idx=_bidx(rep), metric=v,
                    )
        return clusters

    remaining = {_bid(b) for b in boxes}
    if order == "r2_first":
        if r2_enabled:
            apply_r2(remaining)
        clusters = apply_r1(remaining)
    elif order == "r1_first":
        clusters = apply_r1(remaining)
        if r2_enabled:
            apply_r2({_bid(b) for b in boxes if _bid(b) not in marked})
    else:
        raise ValueError(f"order 须为 r2_first / r1_first：{order!r}")

    # 透明化：标记行「同时」满足的另一规则
    r1_ids = set()
    for a, b, _v in r1_edges:
        r1_ids.add(_bid(a))
        r1_ids.add(_bid(b))
    r2_all = {m.box_id for m in marked.values() if m.kind == KIND_GROUP_FRAME}
    for m in marked.values():
        if m.kind == KIND_NEAR_DUPLICATE and m.box_id in r2_all:
            m.also.append("R2")
        if m.kind == KIND_GROUP_FRAME and m.box_id in r1_ids:
            m.also.append("R1")

    kept_ids = [_bid(b) for b in boxes if _bid(b) not in marked]
    return PageDedup(kept_ids=kept_ids, marks=list(marked.values()), clusters=clusters)


def dedup_pages(pages: dict, **kw) -> dict:
    """`{(pdf_name,page): [框,...]}` → `{(pdf_name,page): PageDedup}`（便捷批量入口）。"""
    return {pk: dedup_page(bs, **kw) for pk, bs in pages.items()}
