#!/usr/bin/env python
# local-dist/src/seal_crop.py
"""tab2 切图台：**按检测框（或人工微调框）裁切 → 1200dpi TIFF 件**。

## 流程

`crop_page(pdf, page, boxes, out_dir, pdf_name=None, dpi=1200, cr_from_boxes=None)`

1. **渲页一次**（默认 **1200dpi** —— 切片质量优先；检测/bbox 是 400dpi 系，这里按
   `scale = dpi / boxes_dpi` **等比放大 bbox**，不是重测）。
2. 逐框裁（`numpy` 切片，越界自动夹到页内）⇒ **RGB 8bit** ⇒ `tifffile` 写
   **TIFF＋Deflate**（与老工程 `backfill_book_images.py` 同容器口径；`tifffile` 是打包既有依赖）。
3. 命名 `P<页>-C<列>-R<行>.tiff`（**大写、短横、不补零**）：页＝`page`（1-based，同 `stamps.page`）。
4. 落点 `out_dir/<目录键>/`：目录键取 `config/book_dir_keys.json`（真源 `server/app/naming.py`）；
   未登记 ⇒ **回落到书名自身**（去扩展名、压空白）并标 `dir_key_source: "fallback"`（不静默）。

## C/R 排序规则（本模块自定，写死在这里）

检测框来自图像，不是库内 `stamps`，所以不能沿用 `naming.assign_cr` 的「按列聚类」——
切图台按**页面网格**读法排：

* **行带（R，自上而下 1 起）**：框按 **y 中心**升序；与当前行带「**垂直重叠 ≥ 较矮框高度的 50%**」
  ⇒ 归同一带，否则开新带（同一带即"同一行印章"，允许基线略有参差）。
* **列（C，带内自左向右 1 起）**：带内按 **x 中心**升序编号。
* 构造上 `(C,R)` 页内唯一（每带内 C 互异、带间 R 互异）⇒ 名不撞。
* 调用方可传 `cr_from_boxes=[(c, r), …]`（**与 `boxes` 同序**）覆盖，供人工微调后用库内口径命名。

## 返回（**永不抛**）

成功：`{"ok": True, "outputs": [{"name","path","bytes","page","c","r","box","size","dpi"}],
"skipped": [{"box","reason"}], "dir_key", "dir_key_source", "dir", "dpi", "scale", "elapsed_s"}`
失败：`{"ok": False, "reason": <BAD_DPI|BAD_PAGE|NO_BOXES|ERROR>, "msg": …}`。

## 红线

纯逻辑层：不 import webview/streamlit/ui；只读 PDF、只写 `out_dir` 下的 TIFF；不落库、不联网。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

try:                                    # PyMuPDF ≥1.24 新名；旧包回落 `fitz`
    import pymupdf as fitz
except ImportError:                     # pragma: no cover
    import fitz  # type: ignore

__all__ = [
    "CROP_DPI",
    "BOX_DPI",
    "TIFF_COMPRESSION",
    "grid_order",
    "crop_page",
    "resolve_dir_key",
]

#: 裁切渲页 dpi（切片质量优先；1200dpi 下 400dpi bbox ×3 ⇒ 每枚印面 ~800–1200 px）。
CROP_DPI = 1200
#: 检测框坐标系 dpi（＝库内 `stamps` bbox 系；**别改**）。
BOX_DPI = 400
#: TIFF 容器（RGB 8bit ＋ Deflate；与老工程校正件/O 件同口径）。
TIFF_COMPRESSION = "deflate"

_naming_mod = None
_naming_tried = False


def _repo_root() -> Path:
    """源码态：`local-dist/src/seal_crop.py` → 仓根；打包态：`FEICUI_WEBUI_DIR` 的父级。"""
    env = os.environ.get("FEICUI_WEBUI_DIR")
    if env:
        return Path(env).resolve().parent
    return Path(__file__).resolve().parents[2]


def _naming():
    """拿 `server/app/naming.py`（纯 stdlib 模块）；拿不到 ⇒ `None`（调用方回落本地实现）。"""
    global _naming_mod, _naming_tried
    if _naming_tried:
        return _naming_mod
    _naming_tried = True
    for base in (_repo_root(), Path(__file__).resolve().parents[2],
                 Path(os.environ.get("FEICUI_WEBUI_DIR") or ".")):
        server = Path(base) / "server"
        if (server / "app" / "naming.py").is_file():
            if str(server) not in sys.path:
                sys.path.insert(0, str(server))
            try:
                from app import naming as _n  # noqa: WPS433（延迟导入）
                _naming_mod = _n
            except Exception:
                _naming_mod = None
            return _naming_mod
    return None


def _normalize_book_name(pdf_name: str) -> str:
    """书名规范化（与 `naming.normalize_book_name` 同口径：去扩展名、压空白、去首尾空白）。"""
    stem = os.path.splitext(os.path.basename(str(pdf_name)))[0]
    return re.sub(r"\s+", " ", stem).strip()


def resolve_dir_key(pdf_name: str, dir_keys_path=None) -> tuple[str, str]:
    """⇒ `(目录键, 来源)`。来源 ∈ `{ISBN, chinese_title, pdf_name_unconfirmed, fallback}`。

    已登记 ⇒ 表内 `dir_key` / `dir_key_source`；**未登记 ⇒ 回落书名自身**并返回 `"fallback"`
    （派单口径；`naming` 原值 `fallback_unregistered` 一并映射成 `fallback`，UI 只需认一个词）。
    """
    naming = _naming()
    if naming is not None:
        try:
            keys = naming.load_dir_keys(dir_keys_path)
            key, src = naming.dir_key_entry(pdf_name, keys)
            src = str(src or "")
            if src.startswith("fallback"):
                return key, "fallback"
            return key, src
        except Exception:
            pass
    # 兜底：直接读表（不依赖 naming 能否 import）
    try:
        p = Path(dir_keys_path) if dir_keys_path else _repo_root() / "config" / "book_dir_keys.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        books = data.get("books") if isinstance(data.get("books"), dict) else data
        entry = books.get(str(pdf_name)) or {}
        if isinstance(entry, dict) and entry.get("dir_key"):
            src = str(entry.get("dir_key_source") or "unspecified")
            return str(entry["dir_key"]), ("fallback" if src.startswith("fallback") else src)
    except Exception:
        pass
    return _normalize_book_name(pdf_name), "fallback"


def _as_box(b) -> tuple[int, int, int, int]:
    """宽容入参 ⇒ 整数 `(x1,y1,x2,y2)`（自动排序左上/右下）。"""
    if isinstance(b, dict):
        vals = [b.get(k) for k in ("x1", "y1", "x2", "y2")]
    else:
        vals = list(b)[:4]
    if len(vals) < 4 or any(v is None for v in vals):
        raise ValueError(f"框缺字段：{b!r}")
    x1, y1, x2, y2 = (int(round(float(v))) for v in vals)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def grid_order(boxes, row_overlap: float = 0.5) -> list[tuple[int, int]]:
    """页面网格排序 ⇒ **与入参同序**的 `(C, R)`（规则见模块 docstring「C/R 排序规则」）。"""
    boxes = [_as_box(b) for b in boxes]
    n = len(boxes)
    if n == 0:
        return []
    info = [{"i": i, "x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3],
             "cx": (b[0] + b[2]) / 2.0, "cy": (b[1] + b[3]) / 2.0,
             "h": max(1, b[3] - b[1])} for i, b in enumerate(boxes)]
    bands: list[list[dict]] = []
    for it in sorted(info, key=lambda d: (d["cy"], d["cx"], d["i"])):
        placed = False
        for band in bands:                      # 自上而下第一个"够得着"的带
            top = min(x["y1"] for x in band)
            bot = max(x["y2"] for x in band)
            od = min(bot, it["y2"]) - max(top, it["y1"])
            short = min(min(x["h"] for x in band), it["h"])
            if od >= row_overlap * short:
                band.append(it)
                placed = True
                break
        if not placed:
            bands.append([it])
    out: list = [None] * n
    for r, band in enumerate(bands, start=1):
        for c, it in enumerate(sorted(band, key=lambda d: (d["cx"], d["i"])), start=1):
            out[it["i"]] = (c, r)
    return out  # type: ignore[return-value]


def _cr_from_arg(cr_from_boxes, n: int) -> list[tuple[int, int]] | None:
    """归一 `cr_from_boxes`（`[(c,r)]` / `[{c,r}]`）；长度不符 ⇒ `None`（回落网格排序）。"""
    if not cr_from_boxes:
        return None
    pairs: list[tuple[int, int]] = []
    for item in cr_from_boxes:
        if isinstance(item, dict):
            pairs.append((int(item.get("c") or item.get("col") or 0),
                          int(item.get("r") or item.get("row") or 0)))
        else:
            c, r = list(item)[:2]
            pairs.append((int(c), int(r)))
    if len(pairs) != n or any(c < 1 or r < 1 for c, r in pairs):
        return None
    return pairs


def crop_page(pdf, page: int, boxes, out_dir, pdf_name: str | None = None,
              dpi: int = CROP_DPI, cr_from_boxes=None, *, boxes_dpi: int = BOX_DPI,
              dir_keys_path=None) -> dict:
    """渲页 ⇒ 按框裁 ⇒ 写 `P<页>-C<列>-R<行>.tiff`（**永不抛**，返回结构化 dict）。

    `boxes` 在 `boxes_dpi`（默认 400，＝库内 bbox 系）坐标系；`dpi` 只影响**切图渲页分辨率**
    （bbox 按 `dpi/boxes_dpi` 等比放大）。`pdf_name` 缺省取 PDF 文件名（算目录键用）。
    """
    t0 = time.time()
    try:
        dpi = int(dpi)
    except Exception:
        return {"ok": False, "reason": "BAD_DPI", "msg": f"dpi 必须是整数：{dpi!r}"}
    if dpi < 150 or dpi % 50 != 0:
        return {"ok": False, "reason": "BAD_DPI",
                "msg": f"裁切 dpi 须 ≥150 且为 50 的倍数：{dpi}"}
    try:
        page = int(page)
        if page < 1:
            raise ValueError
    except Exception:
        return {"ok": False, "reason": "BAD_PAGE", "msg": f"页号须为 >=1 的整数：{page!r}"}
    if not boxes:
        return {"ok": False, "reason": "NO_BOXES", "msg": "没有可裁的框（先检测或手动画框）"}
    try:
        norm = [_as_box(b) for b in boxes]
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "msg": f"框格式不对：{exc}"}

    name = str(pdf_name or Path(str(pdf)).name)
    dir_key, dir_key_source = resolve_dir_key(name, dir_keys_path)
    target_dir = Path(out_dir) / dir_key
    scale = float(dpi) / float(boxes_dpi)
    pairs = _cr_from_arg(cr_from_boxes, len(norm)) or grid_order(norm)

    try:
        doc = fitz.open(Path(pdf))
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "msg": f"打不开 PDF：{exc.__class__.__name__}: {exc}"}
    try:
        if page > doc.page_count:
            return {"ok": False, "reason": "BAD_PAGE",
                    "msg": f"页号越界：{page}（共 {doc.page_count} 页）"}
        pix = doc[page - 1].get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
        page_img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n != 3:
            page_img = np.repeat(page_img[:, :, :1], 3, axis=2) if pix.n == 1 else page_img[:, :, :3]
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "msg": f"渲页失败：{exc.__class__.__name__}: {exc}"}
    finally:
        try:
            doc.close()
        except Exception:
            pass

    H, W = page_img.shape[:2]
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict] = []
    skipped: list[dict] = []
    for (x1, y1, x2, y2), (c, r) in zip(norm, pairs):
        sx1, sy1 = int(round(x1 * scale)), int(round(y1 * scale))
        sx2, sy2 = int(round(x2 * scale)), int(round(y2 * scale))
        cx1, cy1 = max(0, sx1), max(0, sy1)
        cx2, cy2 = min(W, sx2), min(H, sy2)
        if cx2 - cx1 < 8 or cy2 - cy1 < 8:
            skipped.append({"box": [x1, y1, x2, y2], "c": c, "r": r,
                            "reason": "OUT_OF_PAGE" if (cx2 <= cx1 or cy2 <= cy1) else "TOO_SMALL"})
            continue
        crop = np.ascontiguousarray(page_img[cy1:cy2, cx1:cx2, :3])   # RGB 8bit
        fname = f"P{page}-C{c}-R{r}.tiff"
        fpath = target_dir / fname
        try:
            tifffile.imwrite(str(fpath), crop, photometric="rgb", compression=TIFF_COMPRESSION)
        except Exception as exc:
            skipped.append({"box": [x1, y1, x2, y2], "c": c, "r": r,
                            "reason": f"WRITE_FAILED: {exc.__class__.__name__}: {exc}"})
            continue
        outputs.append({"name": fname, "path": str(fpath), "bytes": fpath.stat().st_size,
                        "page": page, "c": c, "r": r, "box": [x1, y1, x2, y2],
                        "size": [int(crop.shape[1]), int(crop.shape[0])], "dpi": dpi})
    return {"ok": True, "outputs": outputs, "skipped": skipped,
            "dir_key": dir_key, "dir_key_source": dir_key_source, "dir": str(target_dir),
            "dpi": dpi, "boxes_dpi": int(boxes_dpi), "scale": round(scale, 3),
            "page_size": [int(W), int(H)],
            "count": len(outputs), "elapsed_s": round(time.time() - t0, 2)}
