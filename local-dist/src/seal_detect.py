#!/usr/bin/env python
# local-dist/src/seal_detect.py
"""tab2 切图台：**红印自动检测**（400dpi 渲染 + HSV 双区间 + 形态学 + 连通域几何过滤）。

## 来历

移植自本机 PoC `/Users/kevin/.hermes/profiles/zang/cache/scratch/poc_seal_detect.py`（算法逐字保留），
测样：`output/1_Original_PDF/秦印类编 检索版.pdf` 第 370 页（白底黑字红印的印谱）。

**PoC 读数（真值＝库内 `stamps` bbox，400dpi 坐标系）**：真值 7 枚 ⇒ 检测 12 框 ⇒
**召回 7/7 = 100%**、命中平均 IoU **0.774**；另 5 框经目视确认为「页面上真实存在、
库内未标注」的印章 ⇒ **实际精度近 100%**（报告：`scratch/sealdetect/report_p370.json`）。

## 坐标系统（关键，别换算错）

**默认 400dpi** —— 与库内 `stamps.x1..y2` **同一坐标系**（`processor.render_page` 生产口径）。
裁切阶段再按 `目标dpi / 400` **等比放大** bbox（见 `seal_crop.py`），不要在这里换系。

## 算法（照 PoC，参数全部可覆盖）

1. `cv2.COLOR_BGR2HSV` ⇒ 双区间取并：`(0,70,40)-(12,255,255)` ∪ `(160,70,40)-(180,255,255)`
   （红在 HSV 色环两端；S≥70 / V≥40 滤掉纸黄与灰网）。
2. 椭圆核 9×9 **闭运算 ×2**（补印文笔画断口、把环内碎块连成整枚）。
3. 3×3 **开运算 ×1**（去孤立噪点）。
4. `connectedComponentsWithStats(connectivity=8)` ⇒ 逐域过滤：
   面积 ≥ 页面积 × `min_area_ratio`(0.0004)、宽高 ≥ `min_side`(40px)、
   长宽比 ∈ `ar_range`(0.25–4.0)、填充率 ≥ `fill_min`(0.12)、
   **排除贴页边且跨页 80% 的长条**（书框/装饰线）。
5. 可选 `merge_near_boxes()`：合并同印被笔画断开产生的碎片（默认开）。

## 红线

纯逻辑层：**不 import webview/streamlit/ui**、不写盘、不落库、不联网。
`render_page` 只读 PDF；`detect_page` 只返回框（预览图由 api 层画）。
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

try:                                    # PyMuPDF ≥1.24 新名；旧包回落 `fitz`
    import pymupdf as fitz
except ImportError:                     # pragma: no cover
    import fitz  # type: ignore

__all__ = [
    "DETECT_DPI",
    "DEFAULT_PARAMS",
    "render_page",
    "detect_seals",
    "detect_page",
    "merge_near_boxes",
    "boxes_as_tuples",
    "box_iou",
]

#: 检测默认 dpi —— **必须 400**（＝库内 `stamps` bbox 坐标系；改了就对不上库）。
DETECT_DPI = 400

#: PoC 默认参数（**单点可改**；`detect_seals` / `detect_page` 的关键字覆盖它）。
DEFAULT_PARAMS = {
    "min_area_ratio": 0.0004,     # 面积下限（页面积占比）
    "min_side": 40,               # 宽/高下限（400dpi px）
    "ar_range": (0.25, 4.0),      # 长宽比容区间
    "fill_min": 0.12,             # 填充率下限（面积 / 外接框）
    "merge": True,                # 合并同印碎片
    "merge_gap_ratio": 0.35,      # 合并间隙阈值 ＝ 两框较短边 × 本因子
    "hsv_lo_1": (0, 70, 40),      # 红（色环低端）
    "hsv_hi_1": (12, 255, 255),
    "hsv_lo_2": (160, 70, 40),    # 红（色环高端）
    "hsv_hi_2": (180, 255, 255),
    "close_ksize": 9,             # 闭运算核（椭圆）
    "close_iters": 2,
    "open_ksize": 3,              # 开运算核（矩形）
}


def render_page(pdf, page: int, dpi: int = DETECT_DPI) -> np.ndarray:
    """渲一页 ⇒ **BGR uint8** ndarray（`(h, w, 3)`）。`page` 为 **1-based**。

    PyMuPDF 给的是 RGB（`csRGB`、无 alpha）⇒ 转 BGR 以配合 OpenCV 的 HSV/BGR 习惯。
    打不开 / 页号越界 ⇒ 抛（调用方 `detect_page` 兜成结构化错误；本函数是薄封装）。
    """
    doc = fitz.open(Path(pdf))
    try:
        idx = int(page) - 1
        if idx < 0 or idx >= doc.page_count:
            raise IndexError(f"页号越界：page={page}（共 {doc.page_count} 页）")
        pix = doc[idx].get_pixmap(dpi=int(dpi), alpha=False, colorspace=fitz.csRGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        if pix.n == 1:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    finally:
        doc.close()


def _as_box(b) -> tuple[int, int, int, int]:
    """入参宽容：`{x1,y1,x2,y2}` dict / `(x1,y1,x2,y2)` 序列 ⇒ 整数四元组。"""
    if isinstance(b, dict):
        vals = [b.get(k) for k in ("x1", "y1", "x2", "y2")]
    else:
        vals = list(b)[:4]
    if any(v is None for v in vals):
        raise ValueError(f"框缺字段：{b!r}")
    x1, y1, x2, y2 = (int(round(float(v))) for v in vals)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _box_dicts(boxes) -> list[dict]:
    """四元组序列 ⇒ `{x1,y1,x2,y2,w,h,area,idx}`（**阅读序**：先 y 中心后 x 中心）。"""
    rows = []
    for b in boxes:
        x1, y1, x2, y2 = _as_box(b)
        rows.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                     "w": x2 - x1, "h": y2 - y1, "area": (x2 - x1) * (y2 - y1)})
    rows.sort(key=lambda r: ((r["y1"] + r["y2"]) / 2.0, (r["x1"] + r["x2"]) / 2.0))
    for i, r in enumerate(rows):
        r["idx"] = i + 1                     # 1-based，与 P-C-R 命名口径一致（不补零）
    return rows


def box_iou(a, b) -> float:
    """两框 IoU（宽容入参；退化框 ⇒ 0.0）。"""
    ax1, ay1, ax2, ay2 = _as_box(a)
    bx1, by1, bx2, by2 = _as_box(b)
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def merge_near_boxes(boxes, gap_ratio: float = DEFAULT_PARAMS["merge_gap_ratio"]) -> list[tuple]:
    """合并**同印碎片**：两框「间隙 ≤ 较短边 × `gap_ratio`」且**在外接矩形上真重叠/贴合** ⇒ 并成一框。

    触发场景：印文断裂 / 印泥淡 ⇒ 同一枚印被连通域拆成两三块（PoC 里表现为 IoU 偏低的重复框）。
    迭代到收敛（一遍合并可能让新框又够得着邻框）。返回四元组列表（**不保序**，调用方自行排序）。
    """
    work = [_as_box(b) for b in boxes]
    changed = True
    while changed and len(work) > 1:
        changed = False
        out: list[tuple] = []
        for box in work:
            for i, other in enumerate(out):
                ox1, oy1, ox2, oy2 = other
                x1, y1, x2, y2 = box
                short = min(min(ox2 - ox1, oy2 - oy1), min(x2 - x1, y2 - y1))
                gap = max(0.0, short * float(gap_ratio))
                # 各自外扩 gap 后仍相交 ⇒ 视为同一枚印的碎片
                if (x1 - gap <= ox2 and ox1 <= x2 + gap
                        and y1 - gap <= oy2 and oy1 <= y2 + gap):
                    out[i] = (min(ox1, x1), min(oy1, y1), max(ox2, x2), max(oy2, y2))
                    changed = True
                    break
            else:
                out.append(box)
        work = out
    return work


def detect_seals(bgr: np.ndarray, *, min_area_ratio: float = DEFAULT_PARAMS["min_area_ratio"],
                 min_side: int = DEFAULT_PARAMS["min_side"],
                 ar_range: tuple = DEFAULT_PARAMS["ar_range"],
                 fill_min: float = DEFAULT_PARAMS["fill_min"],
                 merge: bool = DEFAULT_PARAMS["merge"],
                 merge_gap_ratio: float = DEFAULT_PARAMS["merge_gap_ratio"],
                 return_mask: bool = False):
    """在 BGR 页图上检测红印 ⇒ **框列表**（阅读序、`idx` 从 1）。

    返回 `[{"x1","y1","x2","y2","w","h","area","idx"}, …]`；`return_mask=True` ⇒
    `(boxes, mask)`（调试用掩膜，与 PoC 三联图同源）。
    """
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return ([], np.zeros((1, 1), np.uint8)) if return_mask else []
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, DEFAULT_PARAMS["hsv_lo_1"], DEFAULT_PARAMS["hsv_hi_1"])
    m2 = cv2.inRange(hsv, DEFAULT_PARAMS["hsv_lo_2"], DEFAULT_PARAMS["hsv_hi_2"])
    mask = cv2.bitwise_or(m1, m2)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                  (int(DEFAULT_PARAMS["close_ksize"]),) * 2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=int(DEFAULT_PARAMS["close_iters"]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            np.ones((int(DEFAULT_PARAMS["open_ksize"]),) * 2, np.uint8), iterations=1)

    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
    H, W = bgr.shape[:2]
    page_area = float(H * W)
    ar_lo, ar_hi = float(ar_range[0]), float(ar_range[1])
    found: list[tuple] = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < page_area * float(min_area_ratio):
            continue
        if w < int(min_side) or h < int(min_side):
            continue
        ar = w / max(h, 1)
        if ar < ar_lo or ar > ar_hi:
            continue
        if area / max(w * h, 1) < float(fill_min):
            continue
        # 排除贴页边的长条（书框 / 装饰线 / 扫描仪黑边）
        if (x <= 2 or y <= 2 or x + w >= W - 2 or y + h >= H - 2) and (w > W * 0.8 or h > H * 0.8):
            continue
        found.append((x, y, x + w, y + h))

    if merge:
        found = merge_near_boxes(found, gap_ratio=merge_gap_ratio)
    boxes = _box_dicts(found)
    if return_mask:
        return boxes, mask
    return boxes


def detect_page(pdf, page: int, dpi: int = DETECT_DPI, **kw) -> dict:
    """渲页 + 检测 ⇒ 结构化结果（**永不抛**）。

    `{"ok": True, "pdf", "page", "dpi", "size": [w, h], "boxes": [...], "count", "elapsed_s"}`
    失败：`{"ok": False, "reason": <BAD_PAGE|ERROR>, "msg": …}`。
    """
    t0 = time.time()
    try:
        img = render_page(pdf, page, dpi)
    except IndexError as exc:
        return {"ok": False, "reason": "BAD_PAGE", "msg": str(exc),
                "pdf": str(pdf), "page": int(page)}
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "pdf": str(pdf), "page": int(page),
                "msg": f"{exc.__class__.__name__}: {exc}"}
    try:
        boxes = detect_seals(img, **kw)
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "pdf": str(pdf), "page": int(page),
                "msg": f"检测失败：{exc.__class__.__name__}: {exc}"}
    return {"ok": True, "pdf": str(pdf), "page": int(page), "dpi": int(dpi),
            "size": [int(img.shape[1]), int(img.shape[0])],
            "boxes": boxes, "count": len(boxes),
            "elapsed_s": round(time.time() - t0, 2)}


def boxes_as_tuples(boxes) -> list[tuple]:
    """`[{x1,y1,x2,y2,…}]` ⇒ `[(x1,y1,x2,y2), …]`（**保持入参顺序**；给裁切/对拍用）。"""
    return [_as_box(b) for b in (boxes or [])]
