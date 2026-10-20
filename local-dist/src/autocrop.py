#!/usr/bin/env python
# local-dist/src/autocrop.py
"""tab2 **一键全自动**：逐页「红印检测 → 字段提取(OCR) → 1200dpi 裁切」，批处理不进 UI 线程。

给用户的语义（tab2「🚀 开始全自动」）：**一本书/一段页，点一下就全裁完**，途中可取消、可断点续跑，
单页出错只记一笔、绝不中断整批（851 页跑 40 分钟，一页脏页不该把前面 700 页作废）。

## 口径（**复用**，不自造）

* 检测：`src.seal_detect.render_page(pdf, page, detect_dpi)` ＋ `detect_seals`（400dpi 坐标系）；
* 字段：`src.field_extract.extract_fields`（编号/释文/状态 + 阅读顺序；**lite 无 OCR ⇒ 自动降级**，
  只检测、三字段空串、`ocr_available=False`，绝不抛 `ModuleNotFoundError`）；
* 裁切：`src.seal_crop.crop_page`（命名规则**一字未改**；`fields` 与 `boxes` 同序 ⇒ 写 `_fields.json`）；
* 目录键：`src.pdf_library.resolve_dir_key`（tab1 人工确认书名 ⇒ `manual`；否则文件名 ⇒
  `filename-fallback`）；朝代/作者/`true_dpi` 走 `resolve_book_meta` 五级键回落。

## 进度（每页必落盘 ⇒ 断点续跑的唯一真源）

`<根>/3_Cropped_Tiff/<目录键>/.autocrop_progress.json`，**原子写**（`.part` → `os.replace`）：

```json
{"schema": "feicui.autocrop.v1", "pdf": "…/秦印类编 检索版-HighRes.pdf", "pdf_mtime": 1763600000.123,
 "pages_total": 851, "detected": [98, 99], "cropped": [98, 99], "failed": {"100": "IndexError: …"},
 "ocr_available": true, "reading_order": "rtl-ttb", "order_source": "code-sequence",
 "seals_total": 14, "started_at": "…", "updated_at": "…", "elapsed_s": 12.4}
```

* `cropped` ＝ **本页已完整裁完**（含「检测到 0 枚」的页）⇒ `resume=True` 时跳过；
* `outputs` ＝ `{页号: [产物文件名]}` ⇒ 续跑时**再核一遍盘上文件**：用户手工删掉某页 TIFF 后
  重跑，那一页会被补回来（只删文件、没动进度也不会被「已裁」骗过去）；
* `pdf_mtime` 变了（同一路径换了 PDF）⇒ 旧进度归档为 `.autocrop_progress.json.bak`，当新任务跑；
* `failed` 不阻挡重跑：下一次 `resume=True` 只跳过 `cropped`，失败页会**再试**。

## 红线

纯逻辑层：**不 import webview / ui / api**、不联网、不落库。`run_autocrop` **永不抛**
（参数非法 ⇒ `{ok:false, reason:'BAD_PARAM'}`；单页异常 ⇒ 记 `failed` 继续）。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

try:                                    # PyMuPDF ≥1.24 新名；旧包回落 `fitz`
    import pymupdf as fitz
except ImportError:                     # pragma: no cover
    import fitz  # type: ignore

from . import field_extract as fe
from . import pdf_library as lib
from . import seal_crop as sc
from . import seal_detect as sd

__all__ = [
    "SCHEMA",
    "PROGRESS_NAME",
    "DEFAULT_DPI",
    "DETECT_DPI",
    "progress_path",
    "load_progress",
    "save_progress",
    "run_autocrop",
]

#: 进度文件 schema（改结构必须换版本号：UI/外部脚本按它判读）
SCHEMA = "feicui.autocrop.v1"
#: 进度文件名（点开头 ⇒ 与 TIFF 产物区分，tab3 列表不会当印章图）
PROGRESS_NAME = ".autocrop_progress.json"

#: 切图 dpi 默认 1200（与 tab2 人工裁切一致）；检测固定 400（＝库内 bbox 坐标系）
DEFAULT_DPI = 1200
DETECT_DPI = 400
DPI_MIN, DPI_MAX = 150, 2400


# ============================================================
# 进度文件
# ============================================================
def progress_path(root, dir_key: str) -> Path:
    """`<根>/3_Cropped_Tiff/<目录键>/.autocrop_progress.json`（不建目录）。"""
    return Path(str(root)) / lib.TIFF_DIR / str(dir_key) / PROGRESS_NAME


def load_progress(path) -> dict | None:
    """读进度（不存在/损坏/schema 不符 ⇒ `None`，**不抛**）。"""
    p = Path(str(path))
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    # 列表/字典字段的宽容归一（手改过的进度文件也不该把批处理搞崩）
    for k in ("detected", "cropped"):
        vals = data.get(k)
        data[k] = sorted({int(v) for v in vals if isinstance(v, (int, float, str))
                          and str(v).strip().lstrip("-").isdigit()}) if isinstance(vals, list) else []
    if not isinstance(data.get("failed"), dict):
        data["failed"] = {}
    return data


def save_progress(path, data: dict) -> bool:
    """**原子写**进度（`.part` → `os.replace`）；失败只返回 False（**不抛**）。

    为什么必须原子：851 页 ≈40 分钟，任何时刻被 kill / 断电，进度文件都不能是半截 JSON
    —— 半截 JSON 读不回来 ⇒ 整个断点续跑失效（用户视角就是「白跑 40 分钟」）。
    """
    p = Path(str(path))
    tmp = p.with_name(p.name + ".part")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data["schema"] = SCHEMA
        data["updated_at"] = _now()
        blob = json.dumps(data, ensure_ascii=False, indent=1)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


# ============================================================
# 小工具
# ============================================================
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _bad(msg: str, **extra) -> dict:
    return {"ok": False, "reason": "BAD_PARAM", "msg": str(msg), **extra}


def _cancelled(cancel_flag) -> bool:
    """`cancel_flag` 宽容：可调用对象（`threading.Event.is_set` / lambda）或 Event 本身。"""
    if cancel_flag is None:
        return False
    try:
        if callable(cancel_flag):
            return bool(cancel_flag())
        return bool(getattr(cancel_flag, "is_set", lambda: False)())
    except Exception:                   # 取消探测器自己炸了 ⇒ 当成「没取消」（别误杀整批）
        return False


def _emit(cb, rec: dict) -> None:
    """进度回调**不许抛**（回调炸不能把批处理带走）。"""
    if cb is None:
        return
    try:
        cb(rec)
    except Exception:
        pass


def _page_count(pdf) -> int:
    doc = fitz.open(Path(str(pdf)))
    try:
        return int(doc.page_count)
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ============================================================
# 主流程
# ============================================================
def run_autocrop(pdf, root, *, dpi: int = DEFAULT_DPI, detect_dpi: int = DETECT_DPI,
                 page_from: int = 1, page_to: int | None = None, resume: bool = True,
                 progress_cb=None, cancel_flag=None, authoritative=None,
                 dir_key: str | None = None, dir_key_source: str | None = None) -> dict:
    """一本书（或页段）一键全自动：逐页检测 → 字段 → 裁切，**每页落盘**。

    返回（**永不抛**）：
      `{ok, cancelled, pages_total, pages_done, pages_skipped, pages_failed, seals_total,
        dir_key, dir_key_source, reading_order, order_source, ocr_available, elapsed_s,
        failed_pages:[{page, reason}], out_dir, progress_path}`

    * `pages_done` ＝ 本轮**实际裁完**的页数（不含续跑跳过的 `pages_skipped`，不含失败页）；
    * `page_to=None` ⇒ 到末页；`page_to` 超页数 ⇒ 夹到末页；
    * `progress_cb(rec)` 每页至少两次（开工 / 收工），字段见 `_emit` 处；
    * `cancel_flag()` 每页开头（以及渲页+OCR 之后、写盘之前）检 ⇒ 干净退出：
      已裁页保留、进度落盘、`cancelled=True`。
    """
    t0 = time.monotonic()
    started_iso = _now()

    # ---------- 参数校验（唯一允许「不干活就返回」的路径） ----------
    try:
        pdf_p = Path(str(pdf)).expanduser()
        root_p = Path(str(root)).expanduser()
        dpi = int(dpi)
        detect_dpi = int(detect_dpi)
        page_from = int(page_from)
        page_to = None if page_to in (None, "") else int(page_to)
    except Exception as exc:
        return _bad(f"参数类型不合法：{exc.__class__.__name__}: {exc}")
    if not pdf_p.is_file():
        return _bad(f"PDF 不存在：{pdf_p}")
    if not root_p.is_dir():
        return _bad(f"数据根不存在：{root_p}")
    if dpi < DPI_MIN or dpi % 50 != 0 or dpi > DPI_MAX:
        return _bad(f"裁切 dpi 须为 {DPI_MIN}–{DPI_MAX} 且是 50 的倍数：{dpi}")
    if detect_dpi < 72 or detect_dpi % 50 != 0:
        return _bad(f"检测 dpi 须 ≥72 且是 50 的倍数：{detect_dpi}")
    if page_from < 1:
        return _bad(f"起始页从 1 开始：{page_from}")
    if page_to is not None and page_to < page_from:
        return _bad(f"页区间不合法：{page_from}–{page_to}")

    # ---------- 目录键 / 书级元数据 / 落点 ----------
    if not dir_key:
        dir_key, dir_key_source = lib.resolve_dir_key(pdf_p, root=root_p)
    dir_key = str(dir_key or "").strip() or pdf_p.stem
    dir_key_source = str(dir_key_source or "manual")
    book, meta_source, meta_key = lib.resolve_book_meta(pdf_p, root=root_p)
    tiff_root = root_p / lib.TIFF_DIR
    out_dir = tiff_root / dir_key
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return _bad(f"建目录失败 {out_dir}：{exc.__class__.__name__}: {exc}")

    try:
        total_doc = _page_count(pdf_p)
    except Exception as exc:
        return _bad(f"打不开 PDF：{exc.__class__.__name__}: {exc}")
    page_to_eff = total_doc if page_to is None else min(page_to, total_doc)
    if page_to_eff < page_from:
        return _bad(f"页区间 {page_from}–{page_to} 超出 PDF 页数（共 {total_doc} 页）")
    pages_total = page_to_eff - page_from + 1

    # ---------- 进度：读旧 / 判 mtime / 归档 ----------
    prog_file = progress_path(root_p, dir_key)
    try:
        mtime = round(pdf_p.stat().st_mtime, 3)
    except Exception:
        mtime = 0.0
    prog = load_progress(prog_file) if resume else None
    if prog is not None:
        try:
            old_mtime = round(float(prog.get("pdf_mtime") or 0), 3)
        except Exception:
            old_mtime = 0.0
        if old_mtime != mtime:                      # 同名换了 PDF ⇒ 旧进度归档，当新任务
            _archive(prog_file)
            prog = None
    if prog is None:
        prog = {
            "schema": SCHEMA, "pdf": str(pdf_p), "pdf_mtime": mtime,
            "pages_total": pages_total, "detected": [], "cropped": [], "failed": {},
            "ocr_available": None, "reading_order": "", "order_source": "",
            "seals_total": 0, "started_at": started_iso, "updated_at": started_iso,
            "elapsed_s": 0.0, "dpi": dpi, "detect_dpi": detect_dpi, "outputs": {},
        }
        save_progress(prog_file, prog)
    else:
        prog["pages_total"] = pages_total
        prog["pdf"] = str(pdf_p)
        prog.setdefault("seals_total", 0)
        save_progress(prog_file, prog)

    cropped_set = {int(p) for p in prog.get("cropped") or []}
    if not isinstance(prog.get("outputs"), dict):
        prog["outputs"] = {}

    def _page_done(p: int) -> bool:
        """「这页算完了吗」＝ 进度在 `cropped` **且** 它记录的产物都还在盘上。

        只信 `cropped` 不够：用户手工删掉某页 TIFF（或清理了空页产物）后重跑，
        那页得补回来 —— 否则「断点续跑」会安静地少一页。
        """
        if p not in cropped_set:
            return False
        outs = prog["outputs"].get(str(p))
        if outs is None:                      # 老进度没有 outputs 明细 ⇒ 按 cropped 认（后向兼容）
            return True
        try:
            return all((out_dir / str(n)).is_file() for n in outs)
        except Exception:
            return True

    skipped = sum(1 for p in range(page_from, page_to_eff + 1) if _page_done(p))

    # ---------- 能力 / 阅读顺序口径（与 api.tab2_extract 同一条） ----------
    ocr_ok = prog.get("ocr_available")
    if ocr_ok is None:
        ocr_ok = fe.ocr_capable()
    ocr_ok = bool(ocr_ok)
    book_order = fe.normalize_reading_order(book.get("reading_order") or "")
    extract_order = "auto" if ocr_ok else (book_order or "auto")
    order_final = str(prog.get("reading_order") or "")
    source_final = str(prog.get("order_source") or "")

    done = 0
    seals_total = 0
    failed_pages: list[dict] = []
    cancelled = False
    processed = 0                                # 本轮真跑过的页（算 ETA 的平均耗时）

    def _eta() -> float | None:
        try:
            left = pages_total - skipped - done - len(failed_pages)
            if processed <= 0 or left <= 0:
                return 0.0 if left <= 0 else None
            avg = (time.monotonic() - t0) / processed
            return round(avg * left, 1)
        except Exception:
            return None

    def _progress(page: int, per_page_s: float, stage: str) -> dict:
        return {"page": int(page), "pages_total": pages_total, "pages_done": done,
                "pages_skipped": skipped, "pages_failed": len(failed_pages),
                "seals_total": seals_total, "current_page_elapsed_s": round(per_page_s, 2),
                "eta_s": _eta(), "stage": stage, "dir_key": dir_key, "dpi": dpi,
                "msg": f"第 {int(page)}/{pages_total} 页 · 已裁 {seals_total} 枚"}

    def _persist() -> None:
        prog["detected"] = sorted({int(p) for p in prog.get("detected") or []})
        prog["cropped"] = sorted({int(p) for p in prog.get("cropped") or []})
        # 枚数**按产物明细重算**（续跑重裁某页不该把总数加两遍）
        prog["seals_total"] = int(sum(len(v or []) for v in (prog.get("outputs") or {}).values()))
        prog["ocr_available"] = ocr_ok
        prog["reading_order"] = order_final
        prog["order_source"] = source_final
        prog["elapsed_s"] = round(time.monotonic() - t0, 1)
        prog["pages_total"] = pages_total
        save_progress(prog_file, prog)

    _emit(progress_cb, {**_progress(page_from, 0.0, "queued"),
                        "pages_total": pages_total, "pages_skipped": skipped})

    # ---------- 逐页 ----------
    for page in range(page_from, page_to_eff + 1):
        if _cancelled(cancel_flag):                     # 每页开头：取消 ⇒ 干净退出
            cancelled = True
            break
        if _page_done(page):                            # 断点续跑：已裁页 + 产物在盘 ⇒ 跳过
            continue
        t_page = time.monotonic()
        _emit(progress_cb, _progress(page, 0.0, "detect"))
        n_out = 0
        names: list[str] = []
        try:
            img = sd.render_page(pdf_p, page, detect_dpi)
            fields = fe.extract_fields(img, None, reading_order=extract_order,
                                       authoritative=authoritative)
            if not isinstance(fields, dict) or not fields.get("ok"):
                raise RuntimeError(str((fields or {}).get("msg") or "字段提取失败"))
            seals = fields.get("seals") or []
            if fields.get("ocr_available") is not None:
                ocr_ok = bool(fields.get("ocr_available"))
            _emit(progress_cb, _progress(page, time.monotonic() - t_page, "crop"))
            if _cancelled(cancel_flag):                 # 渲页/OCR 已完成，但还没写盘 ⇒ 取消
                cancelled = True
                break
            if seals:
                res = sc.crop_page(pdf_p, page, [s.get("box") for s in seals], tiff_root,
                                   pdf_name=pdf_p.name, dpi=dpi,
                                   reading_order=fields.get("reading_order"),
                                   fields=seals,
                                   order_source=fields.get("order_source"),
                                   dynasty=book.get("dynasty"),
                                   author=book.get("author"),
                                   true_dpi=book.get("true_dpi"),
                                   dir_key=dir_key, dir_key_source=dir_key_source)
                if not isinstance(res, dict) or not res.get("ok"):
                    raise RuntimeError(str((res or {}).get("msg") or "裁切失败"))
                outputs = res.get("outputs") or []
                n_out = len(outputs)
                names = [str(o.get("name") or "") for o in outputs if o.get("name")]
            # 0 枚也算「本页已处理」：否则下次续跑会反复重渲同一张空白页
        except Exception as exc:                        # noqa: BLE001 —— 单页失败绝不中断全批
            reason = f"{exc.__class__.__name__}: {exc}"
            prog["failed"][str(page)] = reason
            failed_pages.append({"page": int(page), "reason": reason})
            processed += 1
            _persist()
            _emit(progress_cb, _progress(page, time.monotonic() - t_page, "failed"))
            continue

        if int(page) not in prog["cropped"]:
            prog["cropped"] = list(prog.get("cropped") or []) + [int(page)]
        if int(page) not in prog["detected"]:
            prog["detected"] = list(prog.get("detected") or []) + [int(page)]
        prog["failed"].pop(str(page), None)
        prog["seals_total"] = int(prog.get("seals_total") or 0) + int(n_out)
        prog["outputs"][str(page)] = names
        seals_total += int(n_out)
        order_final = str(fields.get("reading_order") or order_final)
        source_final = str(fields.get("order_source") or source_final)
        cropped_set.add(int(page))
        done += 1
        processed += 1
        _persist()                                      # **每页裁完立即落盘**
        _emit(progress_cb, _progress(page, time.monotonic() - t_page, "done"))

    _persist()
    elapsed = round(time.monotonic() - t0, 1)
    # 本次页区间内的裁片总数（含续跑跳过的页；比「本轮跑了几枚」更贴合用户直觉）
    seals_in_range = int(sum(len(prog["outputs"].get(str(p)) or [])
                             for p in range(page_from, page_to_eff + 1)))
    _emit(progress_cb, {"page": page_to_eff, "pages_total": pages_total, "pages_done": done,
                        "pages_skipped": skipped, "pages_failed": len(failed_pages),
                        "seals_total": seals_total, "current_page_elapsed_s": 0.0,
                        "eta_s": 0.0, "stage": "cancelled" if cancelled else "finished",
                        "dir_key": dir_key, "dpi": dpi,
                        "msg": ("已取消：完成 %d 页（进度已保存，可续跑）" % done) if cancelled
                               else ("完成：裁 %d 页 / 跳过 %d 页 / 失败 %d 页"
                                     % (done, skipped, len(failed_pages)))})
    return {
        "ok": True, "cancelled": bool(cancelled),
        "pages_total": pages_total, "pages_done": done, "pages_skipped": skipped,
        "pages_failed": len(failed_pages), "seals_total": seals_in_range,
        "dir_key": dir_key, "dir_key_source": dir_key_source,
        "reading_order": order_final, "order_source": source_final,
        "ocr_available": bool(ocr_ok), "elapsed_s": elapsed,
        "failed_pages": failed_pages,
        "out_dir": str(out_dir), "progress_path": str(prog_file),
        "meta_source": meta_source, "meta_key": meta_key,
        "page_from": page_from, "page_to": int(page_to_eff), "dpi": dpi,
        "detect_dpi": detect_dpi, "started_at": started_iso,
    }


def _archive(prog_file: Path) -> None:
    """旧进度（PDF 变了那份）归档成 `.bak`；失败不影响本批。"""
    try:
        bak = prog_file.with_name(prog_file.name + ".bak")
        os.replace(prog_file, bak)
    except Exception:
        try:
            prog_file.unlink()
        except Exception:
            pass
