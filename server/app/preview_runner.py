#!/usr/bin/env python
"""E9 / E10「文档预览」（印谱解析线内）的 **worker 侧执行体**（子进程，stdin → stdout）——Kong。

**必须**由 `feicui/venv/bin/python` 运行（PyMuPDF / cv2 / numpy 只在该 venv 内；接口层
`server/.venv` **无**这三个包，见规范 §6.5 解释器矩阵 / 待裁项 R-1）。**cwd 必须是 `feicui/` 根**
（`processor.load_templates()` 等相对路径口径）。

它**只做纯计算**，与 jobs 体系无关（红线 §2.5：不写 DB、不读 `stamps`、不建 job、不碰
`output/` `exports/`，**PNG 只在内存里经 base64 走 stdout，不落盘**）：

  1. 从 stdin 读一行 JSON 请求（`pdf_path` / `page` / `dpi` / `png` / `detect`）；
  2. **复用**斐萃现状口径（**同一份实现，不复制**）：
       * 渲染 ⇒ `processor.render_page`（本单**不改** `processor.py` 一个字节：该函数的倍率取自
         模块全局 `RENDER_DPI`，故这里**临时**把它设成本次请求的 dpi、调完立刻还原，
         用的仍是 `processor.render_page` 的同一份源码 —— 与 `visualize_page` 内联渲染的
         `Matrix(scale,scale)` + `get_pixmap` 逐字同形）；
       * 印章框 ⇒ `processor.detect_stamp_regions`；
       * 边款框 ⇒ `processor.detect_edge_inscriptions`（参数 `ref_stamp_area` 取印章候选**面积均值**，
         与 `process_page` / `visualize_page` 同口径）；
       * 参数换算 ⇒ `visualize_page` 的公式（`min_area × ((scale*72/BASE_DPI)²)`，`scale = dpi/72`），
         **不得另立第二套**（口径件 §2.2）；
  3. 冷启动优化：在 `import processor` **之前**装 `app.ocr_lazy` 的惰性 paddleocr 替身
     （本脚本一次 OCR 都不做；替身只改「模块名→类」的解析，不参与任何计算，
     检测口径与输出字节零影响 —— 与 `square_runner.py` 同法）。

通信协议（**一行一个 JSON，带标记前缀**）：stdout 只输出一行 `FEICUI_PREVIEW=<json>`；
诊断一律走 stderr（stdout 可能混入第三方库提示行，故调用侧按**标记行**解析）。

请求：
  {"pdf_path": "<绝对或相对 feicui/ 的路径>", "page": 13, "dpi": 110, "png": true, "detect": false}
  * `page` **1-based**（↔ `stamps.page` / `job_pages.page`）；
  * `png=true`    ⇒ 回 `png_base64` / `png_sha256` / `png_bytes`（整页 PNG，**不落盘**）；
  * `detect=true` ⇒ 回 `boxes` / `counts` / `params_used` / `template_source`。

响应（失败一律 `{"ok": false, "error": ..., "detail": ...}`，调用侧映射成结构化错误体）：
  {"ok": true, "page": 13, "pdf_name": "tmp.pdf", "pdf_page_count": 132,
   "render": {"dpi": 110, "width": 797, "height": 1125, "scale": 1.527778},
   "template_source": "...", "params_used": {...}, "boxes": [...],
   "counts": {"stamp": 6, "edge": 1}, "notes": ["人读提示"],
   "png_base64": "...", "png_sha256": "...", "png_bytes": 123456}

错误码（**只出这几个**，与本单口径件的错误面一一对应）：
  `BAD_REQUEST`（缺字段 / 类型不对）· `PDF_MISSING`（`pdf_path` 不在盘上）·
  `PAGE_OUT_OF_PDF`（`page` > PDF 实际页数）· `RENDER_FAILED`（打开 / 渲图 / 编码失败，
  **含检测阶段抛异常**——本线渲染与检测在同一条流水线上，不做第二套错误码）· `INTERNAL`。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

MARKER = "FEICUI_PREVIEW="

HERE = Path(__file__).resolve()                      # <feicui>/server/app/preview_runner.py
SERVER_DIR = HERE.parents[1]                         # <feicui>/server
ROOT = Path(os.environ.get("FEICUI_ROOT") or SERVER_DIR.parent).resolve()
for _p in (str(ROOT), str(SERVER_DIR)):              # processor 在 ROOT；app.* 在 SERVER_DIR
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(ROOT)                                       # processor 相对路径口径（config/、output/）

import cv2  # noqa: E402
import numpy as np  # noqa: E402

# ---- 冷启动优化：在 `import processor` **之前**把 paddleocr 换成惰性替身（同 square_runner.py）----
from app.ocr_lazy import install_lazy_paddleocr  # noqa: E402

LAZY_OCR_INSTALLED = install_lazy_paddleocr()

import processor  # noqa: E402  —— 同一份渲染 + 同一份检测实现（§1.2 I-1）
from app.square import (  # noqa: E402  —— 内建兜底常量的**唯一真源**（与 square-crop 同一份）
    BUILTIN_PARAMS_LOCUS,
    BUILTIN_TEMPLATE_PARAMS,
)

# 渲染 dpi 白名单（口径件 §2.1/§2.6：默认 110；`dpi` 非白名单 ⇒ 接口层 400 BAD_PARAM）。
# 这里**再列一次**只为 worker 侧自证（真正的白名单判定在接口层，见 preview.py）；两处同源。
DPI_WHITELIST = (72, 110, 150)
DPI_DEFAULT = 110

# 未标定书的**人读提示**（口径件 §2.3 ②：UI 必须可见）
UNMARKED_BOOK_NOTE = "本书未标定：框由内建默认参数检出，可能不准"


def log(msg: str) -> None:
    print(f"[preview_runner {os.getpid()}] {msg}", file=sys.stderr, flush=True)


class PreviewError(RuntimeError):
    """worker 侧可读失败（调用侧映射成结构化错误体）。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------- 模板（三态，如实标注）
def resolve_template(pdf_name: str) -> tuple[dict | None, str, list[str]]:
    """解析本书的检测参数真源，返回 `(params, template_source, notes)`（口径件 §2.3 三态）。

    ① `config/templates.json` 命中本书名 ⇒ `book_template:<pdf_name>`（真源）；
    ② 未命中 ⇒ **内建兜底** `builtin_default(<源码位置>)`（常量与 `square-crop` 同一份：
       `app/square.py::BUILTIN_TEMPLATE_PARAMS`），并给出「本书未标定」人读提示；
    ③ 连兜底都不可用 ⇒ `none`（接口层据此只出图、`boxes: []`）。

    **绝不**把兜底说成 `templates.json:default` —— 该键在模板文件里并不存在（§3.14.6 的教训）。
    """
    templates: dict | list = {}
    try:
        templates = processor.load_templates()      # 复用 processor 的加载口径（cwd=ROOT 时读 config/templates.json）
    except Exception as exc:  # noqa: BLE001 - 读不到模板 ⇒ 走兜底，不抛
        log(f"templates.json 读取失败，改走内建兜底：{exc!r}")
        templates = {}
    entry = templates.get(pdf_name) if isinstance(templates, dict) else None
    if isinstance(entry, dict) and {"hsv_low", "hsv_high", "min_area"} <= set(entry):
        note = f"框参数来自本书模板（config/templates.json 键＝{pdf_name}）"
        return entry, f"book_template:{pdf_name}", [note]
    builtin = dict(BUILTIN_TEMPLATE_PARAMS)
    if {"hsv_low", "hsv_high", "min_area"} <= set(builtin):
        note = f"{UNMARKED_BOOK_NOTE}（内建兜底常量位于 {BUILTIN_PARAMS_LOCUS}）"
        return builtin, f"builtin_default({BUILTIN_PARAMS_LOCUS})", [note]
    return None, "none", [f"本书未标定（config/templates.json 无本书键＝{pdf_name}），且内建兜底不可用 ⇒ 只出图、不给框"]


def min_area_source(template_source: str, template_min_area: float, area_scale: float, expr: str) -> str:
    """`params_used.min_area_source` 的生成处 —— **与 `app/square.py::min_area_source_label` 同口径**
    （同一格式 `<template_source>·min_area=X×<换算表达式>=Y`，**由 `template_source` 派生** ⇒
    两者不可能互相矛盾；**绝不**引用不存在的来源键）。

    只把**换算表达式那一段**换成本线真实生效的那个：
      * `square-crop`（生产口径，渲染 400dpi）的表达式是 `processor.AREA_SCALE`（恒为 7.716049）；
      * 本线（预览，按**本次渲染 dpi**）的表达式是 `((dpi/72)×72/BASE_DPI)²`（＝`visualize_page` 的公式）。
    照抄该函数的字面量 `×processor.AREA_SCALE=` 会把 110dpi 的换算因子 0.583497 说成
    `processor.AREA_SCALE`（那是 400dpi 的 7.716049）⇒ **来源失真**；故此处复用其口径与格式，
    不复用那个会被读错名字的常量名。
    """
    return (
        f"{template_source}·min_area={float(template_min_area)}"
        f"×{expr}={float(area_scale):.6f}"
    )


# ---------------------------------------------------------------- 渲染（复用 processor.render_page）
def render_page_at_dpi(page, dpi: int):
    """按 `dpi` 渲染整页 BGR 图 —— **复用** `processor.render_page`（不复制渲染代码）。

    `processor.render_page` 的倍率取自模块全局 `RENDER_DPI`，故此处**临时**改写该全局再调用，
    调完 `finally` 还原（本进程是一次性的一次请求一进程，无并发读者；`processor.py` 一字未改）。
    返回 `(img, scale)`，`scale = dpi/72`（与 `visualize_page` 的 `Matrix(scale, scale)` 同口径）。
    """
    scale = float(dpi) / 72.0
    saved = processor.RENDER_DPI
    try:
        processor.RENDER_DPI = float(dpi)
        img = processor.render_page(page)
    finally:
        processor.RENDER_DPI = saved
    return np.ascontiguousarray(img), scale


def encode_png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise PreviewError("RENDER_FAILED", "PNG 编码失败（cv2.imencode 返回 False）")
    return bytes(buf.tobytes())


# ---------------------------------------------------------------- 检测（复用同一份实现）
def _box(kind: str, bbox, area: float, aspect: float, W: int, H: int) -> tuple[dict, bool]:
    """把检测候选折成响应里的框对象；坐标**防御性夹回画布**（PP-2：坐标 ⊂ [0,W]×[0,H]）。"""
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox)
    cx1, cy1 = max(0, min(W, x1)), max(0, min(H, y1))
    cx2, cy2 = max(cx1, min(W, x2)), max(cy1, min(H, y2))
    clamped = (cx1, cy1, cx2, cy2) != (x1, y1, x2, y2)
    return (
        {
            "kind": kind,
            "x1": cx1,
            "y1": cy1,
            "x2": cx2,
            "y2": cy2,
            "w": int(cx2 - cx1),
            "h": int(cy2 - cy1),
            "area": round(float(area), 4),
            "aspect": round(float(aspect), 4),
        },
        clamped,
    )


def detect_boxes(img, params: dict, min_area_eff: float, pad_ratio: float, edge_enabled: bool) -> tuple[list, dict, list]:
    """现场检测（**复用** `processor.detect_stamp_regions` / `detect_edge_inscriptions`）。

    顺序口径与 `processor.process_page` 一致：印章**从左到右**、边款**从上到下**
    （只影响输出次序，不改检测本身）。
    """
    H, W = img.shape[:2]
    stamps = processor.detect_stamp_regions(
        img, params["hsv_low"], params["hsv_high"], float(min_area_eff), float(pad_ratio)
    )
    stamps.sort(key=lambda c: (c["bbox"][0], c["bbox"][1]))

    edges: list = []
    if edge_enabled and stamps:
        avg_stamp_area = float(np.mean([c["area"] for c in stamps]))
        edges = processor.detect_edge_inscriptions(img, avg_stamp_area)
        edges.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))

    boxes: list[dict] = []
    notes: list[str] = []
    clamped = 0
    for c in stamps:
        b, was_clamped = _box("stamp", c["bbox"], c["area"], c["aspect"], W, H)
        clamped += int(was_clamped)
        boxes.append(b)
    for e in edges:
        b, was_clamped = _box("edge", e["bbox"], e["area"], e["aspect"], W, H)
        clamped += int(was_clamped)
        boxes.append(b)
    if clamped:
        notes.append(f"有 {clamped} 个框超出画布，已夹回边界内（坐标仍 ⊂ [0,{W}]×[0,{H}]）")
    return boxes, {"stamp": len(stamps), "edge": len(edges)}, notes


# ---------------------------------------------------------------- 主流程
def process(req: dict) -> dict:
    pdf_path = Path(str(req.get("pdf_path") or ""))
    if not str(pdf_path):
        raise PreviewError("BAD_REQUEST", "缺 pdf_path")
    if not pdf_path.is_absolute():
        pdf_path = (ROOT / pdf_path)
    # 口径件「判负 / 边界事实」：老 job 的 pdf_path 指向已不存在的文件 ⇒ **如实**报 PDF_MISSING，
    # **不得**用别的书顶替。
    if not pdf_path.is_file():
        raise PreviewError("PDF_MISSING", f"pdf_path 不在盘上：{pdf_path}")

    page = int(req.get("page"))
    if page < 1:
        raise PreviewError("BAD_REQUEST", f"page 必须 >= 1（1-based）：{page}")
    dpi = int(req.get("dpi", DPI_DEFAULT))
    if dpi not in DPI_WHITELIST:
        raise PreviewError("BAD_REQUEST", f"dpi 不在白名单 {list(DPI_WHITELIST)} 内：{dpi}")
    want_png = bool(req.get("png", False))
    want_detect = bool(req.get("detect", False))

    # ---- ① 打开 PDF（只读；绝不写、绝不上传）----
    try:
        doc = processor.pymupdf.open(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - 打开失败也必须是可读 JSON
        raise PreviewError("RENDER_FAILED", f"打开 PDF 失败：{type(exc).__name__}: {exc}") from exc

    out: dict = {}
    try:
        pdf_page_count = int(doc.page_count)
        # PAGE_OUT_OF_PDF **只按 PDF 实际页数判**；job 的 page_range **不是**硬边界（Kevin 要能翻整本）
        if page > pdf_page_count:
            raise PreviewError(
                "PAGE_OUT_OF_PDF", f"page={page} 超出 PDF 实际页数 {pdf_page_count}"
            )
        # ---- ② 渲染（复用 processor.render_page）----
        try:
            img, scale = render_page_at_dpi(doc[page - 1], dpi)
        except PreviewError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PreviewError("RENDER_FAILED", f"渲染失败：{type(exc).__name__}: {exc}") from exc
        H, W = img.shape[:2]

        out = {
            "ok": True,
            "page": page,
            "pdf_name": pdf_path.name,
            "pdf_page_count": pdf_page_count,
            "render": {"dpi": dpi, "width": int(W), "height": int(H), "scale": round(scale, 6)},
        }

        if want_png:
            png = encode_png(img)          # 内存里编码；**不落盘**
            out["png_base64"] = base64.b64encode(png).decode("ascii")
            out["png_sha256"] = hashlib.sha256(png).hexdigest()
            out["png_bytes"] = len(png)

        if want_detect:
            params, template_source, notes = resolve_template(pdf_path.name)
            if params is None:              # ③ 连兜底都不可用 ⇒ 只出图、boxes: []
                out.update(
                    {
                        "template_source": template_source,
                        "params_used": {},
                        "boxes": [],
                        "counts": {"stamp": 0, "edge": 0},
                        "notes": notes,
                    }
                )
            else:
                tmpl_min_area = float(params["min_area"])
                # min_area 按**本次渲染 dpi** 换算（visualize_page 的公式，不得另立第二套）
                area_scale = (scale * 72.0 / float(processor.BASE_DPI)) ** 2
                min_area_eff = tmpl_min_area * area_scale
                pad_ratio = float(params.get("pad_ratio", 0.15))
                edge_enabled = bool(params.get("edge_enabled", True))
                try:
                    boxes, counts, dnotes = detect_boxes(
                        img, params, min_area_eff, pad_ratio, edge_enabled
                    )
                except Exception as exc:  # noqa: BLE001
                    raise PreviewError(
                        "RENDER_FAILED", f"检测阶段抛异常：{type(exc).__name__}: {exc}"
                    ) from exc
                out.update(
                    {
                        "template_source": template_source,
                        "params_used": {
                            "hsv_low": list(params["hsv_low"]),
                            "hsv_high": list(params["hsv_high"]),
                            "min_area_eff": round(float(min_area_eff), 4),
                            "min_area_source": min_area_source(
                                template_source,
                                tmpl_min_area,
                                area_scale,
                                "((dpi/72)×72/BASE_DPI)²",
                            ),
                            "pad_ratio": pad_ratio,
                            "edge_enabled": edge_enabled,
                            "scale": round(scale, 6),
                        },
                        "boxes": boxes,
                        "counts": counts,
                        "notes": notes + dnotes,
                    }
                )
    finally:
        try:
            doc.close()
        except Exception:  # pragma: no cover
            pass
    return out


def main() -> int:
    payload: dict = {}
    try:
        req = json.loads(sys.stdin.read() or "{}")
        payload = process(req)
    except PreviewError as exc:
        payload = {"ok": False, "error": exc.code, "detail": exc.detail}
    except (KeyError, TypeError, ValueError) as exc:
        payload = {"ok": False, "error": "BAD_REQUEST", "detail": f"请求字段非法：{exc!r}"}
    except Exception as exc:  # noqa: BLE001 - 任何异常都必须是可解析的 JSON，不得让调用侧看到半截 stdout
        log(f"未预期异常：{exc!r}")
        payload = {"ok": False, "error": "INTERNAL", "detail": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(MARKER + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
