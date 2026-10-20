#!/usr/bin/env python
# local-dist/src/seal_crop.py
"""tab2 切图台：**按检测框（或人工微调框）裁切 → 1200dpi TIFF 件**。

## 流程

`crop_page(pdf, page, boxes, out_dir, pdf_name=None, dpi=1200, cr_from_boxes=None)`

1. **渲页一次**（默认 **1200dpi** —— 切片质量优先；检测/bbox 是 400dpi 系，这里按
   `scale = dpi / boxes_dpi` **等比放大 bbox**，不是重测）。
2. 逐框裁（`numpy` 切片，越界自动夹到页内）⇒ **RGB 8bit** ⇒ `tifffile` 写
   **TIFF＋Deflate**（与老工程 `backfill_book_images.py` 同容器口径；`tifffile` 是打包既有依赖）。
3. 命名（**两层，2026-10-20 增补**）：
   * **无编号** ⇒ `P<页>-C<列>-R<行>.tiff`（大写、短横、不补零；页＝`page`，1-based，同 `stamps.page`）；
   * **有编号**（`src/field_extract.py` 从页上识别出编号）⇒
     `<编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff`
     （例 `0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff`；P/C/R **保留字母前缀**便于机器解析，
     编号只当前缀，**不改 C/R 方向**）。段清洗：`/ \ : * ? " < > |` 与换行 ⇒ `-`、连字符折叠、
     首尾去 `-`、空段写 `NA`、整名 >200 字符按「释文→作者→朝代」各留 ≥4 字截断（仍超则截 200 加 `~`）。
     朝代/作者优先级：**印级 fields > 本书元数据（tab1）> `NA`**（`build_crop_name`）。
4. 落点 `out_dir/<目录键>/`：目录键取 `config/book_dir_keys.json`（真源 `server/app/naming.py`）；
   未登记 ⇒ **回落到书名自身**（去扩展名、压空白）并标 `dir_key_source: "fallback"`（不静默）。

## C/R 排序规则（本模块自定，写死在这里）

检测框来自图像，不是库内 `stamps`，所以不能沿用 `naming.assign_cr` 的「按列聚类」——
切图台按**页面网格 ＋ 阅读顺序**排：

* **行带（R，1 起）**：框按 **y 中心**升序；与当前行带「**垂直重叠 ≥ 较矮框高度的 50%**」
  ⇒ 归同一带，否则开新带（同一带即"同一行印章"，允许基线略有参差）。
  `reading_order` 的 **vert** 决定 **R 的方向**：`ttb` ⇒ 最上带 R1；`btt` ⇒ 最下带 R1。
* **列（C，带内 1 起）**：`reading_order` 的 **horiz** 决定方向：`ltr` ⇒ 左列 C1；
  **`rtl` ⇒ 右列 C1**（印谱/竖排书的常见版式；此前一律按 x 升序把左列当 C1，那本书里是**反的**）。
* `reading_order` 取值 `rtl-ttb | ltr-ttb | rtl-btt | ltr-btt`（`ttb-rtl` 这类反向写法的
  `ttb-rtl` 也认，见 `field_extract.normalize_reading_order`）；缺省 **`ltr-ttb`**
  （＝改动前行为，**保持向后兼容**）。
  几何单一真源是 `field_extract.grid_positions()`（纯 stdlib），本模块只做委托 ＋ 兜底实现。
* 构造上 `(C,R)` 页内唯一（每带内 C 互异、带间 R 互异）⇒ 名不撞。
* 调用方可传 `cr_from_boxes=[(c, r), …]`（**与 `boxes` 同序**）覆盖，供人工微调后用库内口径命名。

## 字段 sidecar（可选）

`crop_page(..., fields=[…], reading_order=…)`：`fields` 与 `boxes` 同序（每项
`{inscription,status,code,…}`），裁完把「每枚 P-C-R ＋ 三字段 ＋ 分数 ＋ needs_review」
汇入 `out_dir/<目录键>/_fields.json`（按页合并，`pages.<页号>`）；`per_seal_json=True`
时另写每枚 `<名>.json`。返回里带 `fields_sidecar` / `reading_order` / `order_source`。

## 物理尺寸元数据（mm，2026-10-20 增补）

切片 TIFF 的**物理尺寸**（每枚印面宽/高，mm）按下列**优先级**算，并记录 `size_source`
（`manual-dpi` → `page-box` → `render-dpi` → `none`），见 `slice_size_mm()`：

1. **`manual-dpi`**：调用方给了合理 `true_dpi`（50–2400）⇒ `mm = px / true_dpi × 25.4`。
   用户意图优先：PDF 自带尺寸/dpi 不可信时，由 tab1「真实 dpi（人工）」手填；
2. **`page-box`**：否则用渲染页的**物理尺寸**（PyMuPDF `page.rect`，pt）折算 ——
   `mm = 切片px / 页px × (页pt × 25.4 / 72)`（不依赖 dpi，缺省最准）；
3. **`render-dpi`**：页面尺寸不可得 ⇒ `mm = px / render_dpi × 25.4`；
4. 全失败 ⇒ **不写** mm（不造假），`size_source="none"`。

**值域保护**：mm 取**整数**（四舍五入 half-up，**不用内置 `round()`** —— 它是银行家舍入）；
判定 `< 0.5mm` / `> 2000mm` 用**取整前**的浮点值（0.4mm 取整成 0 也不掩盖异常），越界 ⇒
`size_suspect=True`（仍写入，便于发现问题）。

TIFF 写入**同时**设 `XResolution=YResolution=render_dpi` ＋ `ResolutionUnit=INCH(2)`，
并把结构化摘要写进**单条** `ImageDescription(270)`：
`feicui;width_mm=12;height_mm=12;dpi=1200;size_source=page-box[;suspect=1]`。
⚠ `tifffile.imwrite(description=…)` 默认会**再追加**一条 270（`{"shape": …}`）⇒ `sips`/QuickLook
读不出 dpi；必须同时传 `metadata=None`（本模块 `_write_tiff` 已固定这一口径）。

## 返回（**永不抛**）

成功：`{"ok": True, "outputs": [{"name","path","bytes","page","c","r","box","size","dpi",
"width_mm","height_mm","size_source","size_suspect"}],
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
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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
    "NAME_MAX_LEN",
    "grid_order",
    "build_crop_name",
    "sanitize_name_part",
    "crop_page",
    "slice_size_mm",
    "slice_size_mm_raw",
    "mm_half_up",
    "mm_out_of_range",
    "tiff_description",
    "FIELDS_SCHEMA",
    "resolve_dir_key",
]

#: 裁切渲页 dpi（切片质量优先；1200dpi 下 400dpi bbox ×3 ⇒ 每枚印面 ~800–1200 px）。
CROP_DPI = 1200
#: 检测框坐标系 dpi（＝库内 `stamps` bbox 系；**别改**）。
BOX_DPI = 400
#: TIFF 容器（RGB 8bit ＋ Deflate；与老工程校正件/O 件同口径）。
TIFF_COMPRESSION = "deflate"
#: TIFF `ResolutionUnit`：**2 = inch**（TIFF 6.0 规范；**3 是 cm**，写成 3 会让 sips 报 3048dpi）。
TIFF_RESUNIT_INCH = 2
#: 物理尺寸合理区间（mm）；越界 ⇒ `size_suspect=True`（仍写入，不吞）。
MM_MIN, MM_MAX = 0.5, 2000.0
#: 人工/渲染 dpi 合理区间；越界一律不采用。
DPI_MIN, DPI_MAX = 50.0, 2400.0
#: `_fields.json` schema（v2 起每枚带 `width_mm/height_mm/size_source/size_suspect`；v1 只读兼容）。
FIELDS_SCHEMA = "feicui.fields.v2"


def _as_wh(v) -> tuple[float, float] | None:
    """把 `(w,h)` / `(x0,y0,x1,y1)` / PyMuPDF `Rect` 归一成 `(w,h)`；认不出 ⇒ `None`。"""
    if v is None:
        return None
    try:
        seq = tuple(v)
    except TypeError:
        seq = None
    try:
        if seq is not None:
            if len(seq) == 2:
                return float(seq[0]), float(seq[1])
            if len(seq) == 4:
                return float(seq[2]) - float(seq[0]), float(seq[3]) - float(seq[1])
        w = getattr(v, "width", None)
        h = getattr(v, "height", None)
        if w is not None and h is not None:
            return float(w), float(h)
    except Exception:                                      # noqa: BLE001 —— 归一失败不抛
        return None
    return None


def _ok_dpi(v) -> bool:
    """dpi 是否可用：数值且在 `[DPI_MIN, DPI_MAX]`（bool 不算）。"""
    if v is None or isinstance(v, bool):
        return False
    try:
        f = float(v)
    except Exception:
        return False
    return DPI_MIN <= f <= DPI_MAX


def slice_size_mm_raw(pdf_page_rect_pt=None, render_dpi=None, slice_px=None, *,
                      true_dpi=None, page_px=None) -> tuple[float | None, float | None, str]:
    """切片**物理尺寸**（mm，**取整前**的浮点）⇒ `(w_mm, h_mm, size_source)`；**纯函数、永不抛**。

    优先级（`size_source`）：
      1. `true_dpi` 合理（50–2400）⇒ `manual-dpi`：`mm = px / true_dpi × 25.4`（人工填的真值优先）；
      2. `pdf_page_rect_pt` ＋ `page_px` 可用 ⇒ `page-box`：
         `mm = px / page_px × (page_pt × 25.4 / 72)`（用页面物理尺寸，不依赖 dpi）；
      3. `render_dpi` 合理 ⇒ `render-dpi`：`mm = px / render_dpi × 25.4`；
      4. 全失败 ⇒ `(None, None, "none")`（**不造假**）。

    `pdf_page_rect_pt` 认 `(w,h)` / `(x0,y0,x1,y1)` / `pymupdf.Rect`；`slice_px`、`page_px` 同理。
    **值域保护用这层的原始浮点**（取整会掩盖 `<0.5mm` 的异常）。
    """
    try:
        px = _as_wh(slice_px)
        if px is None or px[0] <= 0 or px[1] <= 0:
            return None, None, "none"
        if _ok_dpi(true_dpi):
            s = 25.4 / float(true_dpi)
            return px[0] * s, px[1] * s, "manual-dpi"
        rect, ppx = _as_wh(pdf_page_rect_pt), _as_wh(page_px)
        if rect and ppx and rect[0] > 0 and rect[1] > 0 and ppx[0] > 0 and ppx[1] > 0:
            kx = (rect[0] * 25.4 / 72.0) / ppx[0]
            ky = (rect[1] * 25.4 / 72.0) / ppx[1]
            return px[0] * kx, px[1] * ky, "page-box"
        if _ok_dpi(render_dpi):
            s = 25.4 / float(render_dpi)
            return px[0] * s, px[1] * s, "render-dpi"
    except Exception:                                      # noqa: BLE001 —— never raise
        pass
    return None, None, "none"


def mm_half_up(v) -> int | None:
    """mm 取整：**四舍五入 half-up**（`6.35→6`、`6.5→7`、`12.5→13`、`2.5→3`）。

    ⚠ 不用内置 `round()` —— 银行家舍入（`round(2.5)==2`、`round(0.5)==0`）与「四舍五入」直觉不符。
    `None` ⇒ `None`；认不出 ⇒ `None`（不抛）。
    """
    if v is None:
        return None
    try:
        d = Decimal(str(float(v))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:                                      # noqa: BLE001
        return None
    return int(d)


def slice_size_mm(pdf_page_rect_pt=None, render_dpi=None, slice_px=None, *,
                  true_dpi=None, page_px=None) -> tuple[int | None, int | None, str]:
    """同 `slice_size_mm_raw`，但 mm 落**整数**（四舍五入 half-up）⇒ `(w_mm, h_mm, source)`。"""
    w, h, src = slice_size_mm_raw(pdf_page_rect_pt, render_dpi, slice_px,
                                  true_dpi=true_dpi, page_px=page_px)
    return mm_half_up(w), mm_half_up(h), src


def mm_out_of_range(w_mm: float | None, h_mm: float | None) -> bool:
    """尺寸是否异常（`< 0.5mm` 或 `> 2000mm`）—— **判原始浮点**；`None` 不算异常（＝没算出来）。"""
    for v in (w_mm, h_mm):
        if v is None:
            continue
        try:
            f = float(str(v))
        except Exception:
            return True
        if f < MM_MIN or f > MM_MAX:
            return True
    return False


def tiff_description(w_mm: int | None = None, h_mm: int | None = None,
                     dpi: int | float | None = None, size_source: str = "none", *,
                     suspect: bool = False) -> str:
    """`ImageDescription(270)` 的**单条**结构化文本（`;` 分隔，mm 为**整数**）。"""
    parts = ["feicui"]
    if w_mm is not None and h_mm is not None:
        parts += [f"width_mm={int(w_mm)}", f"height_mm={int(h_mm)}"]
    if dpi is not None:
        try:
            parts.append(f"dpi={int(float(dpi))}")
        except Exception:
            pass
    parts.append(f"size_source={size_source or 'none'}")
    if suspect:
        parts.append("suspect=1")
    return ";".join(parts)


def _write_tiff(path, arr, *, dpi, description: str) -> None:
    """写 TIFF 并**只写一条** 270（`metadata=None` 关掉 tifffile 自动的 shape 描述）。

    `XResolution/YResolution=dpi` ＋ `ResolutionUnit=INCH`；`metadata=None` 是关键 ——
    否则 tifffile 会**再追加一条** `ImageDescription`（`{"shape": …}`），
    `sips`/QuickLook 见到重复 270 就读不出 dpi（历史坑）。
    """
    tifffile.imwrite(
        str(path), arr, photometric="rgb", compression=TIFF_COMPRESSION,
        resolution=(float(dpi), float(dpi)), resolutionunit="INCH",
        description=description, metadata=None,
    )

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


def _grid_order_fallback(boxes, row_overlap: float = 0.5) -> list[tuple[int, int]]:
    """兜底实现（＝改动前的「ltr-ttb」口径；只在 `field_extract` 拿不到时用）。"""
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


def grid_order(boxes, row_overlap: float = 0.5,
               reading_order: str = "ltr-ttb") -> list[tuple[int, int]]:
    """页面网格 + 阅读顺序 ⇒ **与入参同序**的 `(C, R)`（规则见模块 docstring「C/R 排序规则」）。

    `reading_order` 的 `rtl` 让**右列＝C1**、`btt` 让**下行为 R1**；缺省 `ltr-ttb` ＝改动前行为。
    几何单一真源是 `field_extract.grid_positions()`；拿不到（打包异常等）⇒ 兜底实现（仅 ltr-ttb 口径）。
    """
    try:
        from .field_extract import grid_positions, normalize_reading_order  # 纯 stdlib
    except Exception:                                     # pragma: no cover —— 直跑 src/ 时回落
        try:
            from src.field_extract import grid_positions, normalize_reading_order  # type: ignore
        except Exception:
            return _grid_order_fallback(boxes, row_overlap=row_overlap)
    order = normalize_reading_order(reading_order) or "ltr-ttb"
    try:
        return [(int(p[0]), int(p[1])) for p in
                grid_positions(boxes, row_overlap=row_overlap, reading_order=order)]
    except Exception:                                     # pragma: no cover
        return _grid_order_fallback(boxes, row_overlap=row_overlap)


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


#: 含编号命名时整名上限（Windows 单段 255 / 全路径 260；留余量）。
NAME_MAX_LEN = 200
#: Windows / macOS 都不安全、且会让 `open()` 失败的字符 ⇒ 一律替成 `-`。
_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|\r\n\t]+')


def sanitize_name_part(value, default: str = "NA") -> str:
    """文件名段清洗：非法字符/换行 ⇒ `-`；连续 `-` 折叠；首尾 `-` 去除；空 ⇒ `default`（默认 `NA`）。"""
    s = "" if value is None else str(value)
    s = _ILLEGAL_CHARS.sub("-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip().strip("-").strip()
    return s or default


def _fit_name(prefix: str, ins: str, dyn: str, aut: str, limit: int = NAME_MAX_LEN) -> str:
    """超长整形：按「释文 → 作者 → 朝代」逐个截断（每段保留 ≥4 字），仍超 ⇒ 整名截到 `limit` 加 `~`。

    ⚠ 段顺序＝**释文\_朝代\_作者**（与模块 docstring / 示例 `0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff`
    一致）。此前这里把 `aut` 排在 `dyn` 前，产出 `…_吳熙載_清中期.tiff`，与文档/示例/前端预演**不一致**
    —— 2026-10-20 按文档口径改正（`test_field_extract.py` 有逐字对拍）。
    """
    vals = {"ins": ins, "aut": aut, "dyn": dyn}

    def build() -> str:
        return prefix + "_".join([vals["ins"], vals["dyn"], vals["aut"]]) + ".tiff"

    for key in ("ins", "aut", "dyn"):
        while len(build()) > limit and len(vals[key]) > 4:
            vals[key] = vals[key][:-1]
    name = build()
    if len(name) > limit:
        name = name[: limit - 1] + "~"
    return name


def build_crop_name(page: int, c: int, r: int, fields=None, *,
                    dynasty: str | None = None, author: str | None = None,
                    limit: int = NAME_MAX_LEN) -> tuple[str, str]:
    """⇒ `(文件名, naming)`；`naming ∈ {with_code, legacy}`。

    * **有编号**（`fields['code']` 非空）⇒ `<编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff`
      （例 `0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff`）：P/C/R 的**字母前缀保留**（便于机器解析），
      编号在前只影响前缀与排序，**不影响** C/R 方向；
    * **无编号** ⇒ 回落 `P<页>-C<列>-R<行>.tiff`（**保兼容**）；
    * 朝代/作者优先级：**印级 fields > 本书元数据（tab1）> `NA`**；空字段一律写 `NA`（位置稳定）；
    * 段内非法字符清洗见 `sanitize_name_part`；整名超 `limit` 见 `_fit_name`。
    """
    f = fields or {}
    code_raw = str(f.get("code") or "").strip()
    if not code_raw:
        return f"P{int(page)}-C{int(c)}-R{int(r)}.tiff", "legacy"
    prefix = "_".join([sanitize_name_part(code_raw), f"P{int(page)}", f"C{int(c)}", f"R{int(r)}"]) + "_"
    ins = sanitize_name_part(f.get("inscription"))
    dyn = sanitize_name_part(f.get("dynasty") or dynasty)
    aut = sanitize_name_part(f.get("author") or author)
    return _fit_name(prefix, ins, dyn, aut, limit=limit), "with_code"


def _norm_order(reading_order) -> str:
    """阅读顺序归一（`rtl-ttb|…`）；认不出 / 缺省 ⇒ `ltr-ttb`（＝改动前行为）。"""
    try:
        from .field_extract import normalize_reading_order
    except Exception:                                     # pragma: no cover
        try:
            from src.field_extract import normalize_reading_order  # type: ignore
        except Exception:
            return "ltr-ttb"
    return normalize_reading_order(reading_order) or "ltr-ttb"


def _norm_fields(fields, n: int) -> tuple[list[dict], bool]:
    """字段入参归一成**与 boxes 同序**的 `n` 项（缺项补空 dict）；⇒ `(rows, aligned)`。"""
    rows: list[dict] = []
    for f in list(fields or [])[:n]:
        rows.append(dict(f) if isinstance(f, dict) else {})
    aligned = (len(rows) == n)
    while len(rows) < n:
        rows.append({})
    return rows, aligned


def _write_fields_sidecar(target_dir: Path, *, page: int, dir_key: str, pdf_name: str,
                          reading_order: str, order_source: str, seals: list[dict],
                          per_seal_json: bool = False) -> tuple[str, int]:
    """把本页字段汇入 `<dir>/_fields.json`（按 `pages.<页号>` 合并）；可选每枚 `.json`。

    ⇒ `(sidecar_path, 写入枚数)`；**永不抛**（写不动就返回 `("", 0)`，裁切结果照样返回）。
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "_fields.json"
        data: dict = {"schema": FIELDS_SCHEMA, "dir_key": dir_key, "pdf_name": pdf_name}
        if path.is_file():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    data.update({k: v for k, v in old.items()
                                 if k not in ("pages", "schema", "schema_prev")})
                    data["pages"] = old.get("pages") if isinstance(old.get("pages"), dict) else {}
                    # v1（无 mm 字段）⇒ 只读兼容：pages 原样保留，不猜测、不改写既有枚
                    prev = str(old.get("schema") or "")
                    if prev and prev != FIELDS_SCHEMA:
                        data["schema_prev"] = prev
            except Exception:
                pass
        pages = data.get("pages")
        if not isinstance(pages, dict):
            pages = {}
        pages[str(int(page))] = {"page": int(page), "reading_order": reading_order,
                                 "order_source": order_source, "count": len(seals),
                                 "naming": ("with_code" if any(s.get("naming") == "with_code"
                                                               for s in seals) else "legacy"),
                                 "seals": seals}
        data["pages"] = pages
        data["schema"] = FIELDS_SCHEMA
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        n = 0
        if per_seal_json:
            for s in seals:
                stem = os.path.splitext(str(s.get("name") or ""))[0]
                if not stem:
                    continue
                (target_dir / f"{stem}.json").write_text(
                    json.dumps({**s, "pdf_name": pdf_name, "page": int(page),
                                "reading_order": reading_order,
                                "order_source": order_source},
                               ensure_ascii=False, indent=2), encoding="utf-8")
                n += 1
        return str(path), n
    except Exception:                                     # noqa: BLE001 —— never raise
        return "", 0


def crop_page(pdf, page: int, boxes, out_dir, pdf_name: str | None = None,
              dpi: int = CROP_DPI, cr_from_boxes=None, *, boxes_dpi: int = BOX_DPI,
              dir_keys_path=None, reading_order: str | None = None, fields=None,
              write_fields: bool = True, per_seal_json: bool = False,
              order_source: str | None = None, dynasty: str | None = None,
              author: str | None = None, true_dpi: int | None = None) -> dict:
    """渲页 ⇒ 按框裁 ⇒ 写 `P<页>-C<列>-R<行>.tiff`（**永不抛**，返回结构化 dict）。

    `boxes` 在 `boxes_dpi`（默认 400，＝库内 bbox 系）坐标系；`dpi` 只影响**切图渲页分辨率**
    （bbox 按 `dpi/boxes_dpi` 等比放大）。`pdf_name` 缺省取 PDF 文件名（算目录键用）。

    `reading_order`（`rtl-ttb|ltr-ttb|rtl-btt|ltr-btt`）决定 **C/R 方向**（`rtl` ⇒ 右列 C1）；
    缺省 `ltr-ttb` ＝改动前行为。`cr_from_boxes` 优先级更高（人工微调口径）。
    `fields`（与 `boxes` 同序）非空且 `write_fields` ⇒ 落 `_fields.json` sidecar。
    `true_dpi`（人工填的真实扫描 dpi）非空且合理 ⇒ mm 走 `manual-dpi` 口径（见 `slice_size_mm`）；
    缺省用页面物理尺寸（`page-box`）。每枚 TIFF 写 XResolution/YResolution/ResolutionUnit
    ＋ **单条** `ImageDescription(270)`（含 `width_mm/height_mm/size_source`）。
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
    order = _norm_order(reading_order)
    book_dynasty = str(dynasty).strip() if dynasty else None
    book_author = str(author).strip() if author else None
    pairs = _cr_from_arg(cr_from_boxes, len(norm)) or grid_order(norm, reading_order=order)

    try:
        doc = fitz.open(Path(pdf))
    except Exception as exc:
        return {"ok": False, "reason": "ERROR", "msg": f"打不开 PDF：{exc.__class__.__name__}: {exc}"}
    page_rect_pt = None                     # 页面物理尺寸（pt）—— mm 计算的 page-box 口径
    try:
        if page > doc.page_count:
            return {"ok": False, "reason": "BAD_PAGE",
                    "msg": f"页号越界：{page}（共 {doc.page_count} 页）"}
        pg = doc[page - 1]
        try:
            page_rect_pt = (float(pg.rect.width), float(pg.rect.height))
        except Exception:                   # 页盒异常 ⇒ 回落 render-dpi（不阻断裁切）
            page_rect_pt = None
        pix = pg.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
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
    field_rows, aligned = _norm_fields(fields, len(norm))
    for k, ((x1, y1, x2, y2), (c, r)) in enumerate(zip(norm, pairs)):
        sx1, sy1 = int(round(x1 * scale)), int(round(y1 * scale))
        sx2, sy2 = int(round(x2 * scale)), int(round(y2 * scale))
        cx1, cy1 = max(0, sx1), max(0, sy1)
        cx2, cy2 = min(W, sx2), min(H, sy2)
        if cx2 - cx1 < 8 or cy2 - cy1 < 8:
            skipped.append({"box": [x1, y1, x2, y2], "c": c, "r": r,
                            "reason": "OUT_OF_PAGE" if (cx2 <= cx1 or cy2 <= cy1) else "TOO_SMALL"})
            continue
        crop = np.ascontiguousarray(page_img[cy1:cy2, cx1:cx2, :3])   # RGB 8bit
        # 物理尺寸（mm）：manual-dpi > page-box > render-dpi；值域保护判**取整前**浮点
        raw_w, raw_h, size_source = slice_size_mm_raw(
            page_rect_pt, dpi, (int(crop.shape[1]), int(crop.shape[0])),
            true_dpi=true_dpi, page_px=(W, H))
        w_mm, h_mm = mm_half_up(raw_w), mm_half_up(raw_h)
        size_suspect = mm_out_of_range(raw_w, raw_h)
        fname, naming = build_crop_name(page, c, r, field_rows[k],
                                        dynasty=book_dynasty, author=book_author)
        fpath = target_dir / fname
        try:
            _write_tiff(fpath, crop, dpi=dpi,
                        description=tiff_description(w_mm, h_mm, dpi, size_source,
                                                     suspect=size_suspect))
        except Exception as exc:
            skipped.append({"box": [x1, y1, x2, y2], "c": c, "r": r,
                            "reason": f"WRITE_FAILED: {exc.__class__.__name__}: {exc}"})
            continue
        outputs.append({"name": fname, "path": str(fpath), "bytes": fpath.stat().st_size,
                        "page": page, "c": c, "r": r, "box": [x1, y1, x2, y2],
                        "size": [int(crop.shape[1]), int(crop.shape[0])], "dpi": dpi,
                        "width_mm": w_mm, "height_mm": h_mm,
                        "size_source": size_source, "size_suspect": size_suspect,
                        "naming": naming, "code": field_rows[k].get("code"),
                        "inscription": field_rows[k].get("inscription")})

    # 字段 sidecar（`fields` 与 boxes 同序；空 ⇒ 不写，不影响裁切结果）
    seals: list[dict] = []
    if any(field_rows):
        by_box = {tuple(int(round(v)) for v in norm[i]): field_rows[i] for i in range(len(norm))}
        for o in outputs:
            f = by_box.get(tuple(int(v) for v in o["box"]), {}) or {}
            seals.append({
                "name": o["name"], "naming": o.get("naming"), "c": o["c"], "r": o["r"],
                "read_order": f.get("read_order", f.get("readOrder")),
                "box": o["box"],
                "inscription": f.get("inscription"), "inscription_score": f.get("inscription_score"),
                "inscription_verified": f.get("inscription_verified"),
                "status": f.get("status"), "status_score": f.get("status_score"),
                "code": f.get("code"), "code_score": f.get("code_score"),
                "dynasty": f.get("dynasty") or book_dynasty,
                "author": f.get("author") or book_author,
                "needs_review": bool(f.get("needs_review")),
                "width_mm": o.get("width_mm"), "height_mm": o.get("height_mm"),
                "size_source": o.get("size_source"), "size_suspect": bool(o.get("size_suspect")),
            })
    sidecar, per_seal_n = ("", 0)
    if seals and write_fields:
        sidecar, per_seal_n = _write_fields_sidecar(
            target_dir, page=page, dir_key=dir_key, pdf_name=name,
            reading_order=order, order_source=str(order_source or "manual"),
            seals=seals, per_seal_json=bool(per_seal_json))
    return {"ok": True, "outputs": outputs, "skipped": skipped,
            "dir_key": dir_key, "dir_key_source": dir_key_source, "dir": str(target_dir),
            "dpi": dpi, "boxes_dpi": int(boxes_dpi), "scale": round(scale, 3),
            "page_size": [int(W), int(H)],
            "reading_order": order, "order_source": str(order_source or "manual"),
            "fields_sidecar": sidecar, "fields_count": len(seals),
            "fields_per_seal_json": per_seal_n, "fields_aligned": aligned,
            "count": len(outputs), "elapsed_s": round(time.time() - t0, 2)}
