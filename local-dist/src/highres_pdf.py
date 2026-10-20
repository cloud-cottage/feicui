#!/usr/bin/env python
# local-dist/src/highres_pdf.py
"""tab1 一键高清化：**PDF → 高清页图 PDF**（逐页 1200dpi · 8bit · PNG 流直接嵌入）。

## 干什么

`render_pdf_to_pdf(src_pdf, out_pdf, dpi=1200, …)`：把源 PDF **逐页**用 pymupdf 渲染成
位图 ⇒ **RGB 8bit** ⇒ 编码成 **PNG（zlib）** ⇒ 用 `page.insert_image` 把 **PNG 流**塞进
**同尺寸**的新 PDF 页 ⇒ 整本落 `…/<书名>-HighRes.pdf`。

* **不落中间 JPEG**（红线）：页图只以 PNG 形态存在于内存 / 页缓存目录；
  最终 PDF 里每页是一张 `/FlateDecode` 8bit RGB 图（`/DCTDecode` 一律不出现）。
* **页尺寸保真**：新页宽高逐页取自 `src.page.rect`（pt）⇒ 输出页与原页**同 pt 尺寸**
  ⇒ 下游 400dpi 坐标系（`stamps` bbox）与 1200dpi 裁切**同一比例尺**。
* **断点续跑**：`<out>.progress.json` ＋ 逐页 PNG 页缓存（默认 `<out 同目录>/.pages-<书名>/P0001.png`）
  ⇒ 中断后重跑**只补未完成的页**，已完成页直接从缓存 PNG 重嵌（不重渲）。
* **体积告警**：累计 PNG 字节超 `size_limit_bytes`（默认 15 GiB）⇒ 结构化
  `{"ok": False, "reason": "SIZE_LIMIT", …}`（**不静默继续**，也不删已有产物/进度）。
* **可取消**：`cancel_event.is_set()` ⇒ 结构化 `{"ok": False, "reason": "CANCELLED", …}`。
* **永不抛**：任何异常都变成 `{"ok": False, "reason": "ERROR", "msg": …}`（js_api 桥不许断）。

## dpi 白名单（Kevin 2026-10-20 补充口径）

**只接受 300 / 600 / 1200**（默认 **1200**）；非法值 ⇒ `{"ok": False, "reason": "BAD_DPI",
"allowed": [300, 600, 1200]}`，**一页都不渲**（先校验再开文档）。

## ⚠️ 反直觉：**1200dpi 的 PNG 比 600dpi 更小**（实测，别"优化"成 600）

白底黑字红印的印谱（`秦印类编 检索版.pdf` 第 370 页，510×734 pt）实测，同一页三档：

| dpi | 像素 | PNG 字节 | 折合 Mpx |
| --- | --- | --- | --- |
| 300 | 2125×3059 | 5.36 MB | 6.5 |
| 600 | 4250×6118 | 15.5 MB | 26.0 |
| **1200** | **8500×12236** | **13.3 MB** | **104.0** |

**1200 反而比 600 小 14%**：600dpi 正落在扫描件墨边/网点的"半软"频段，抗锯齿灰阶多、
熵高；1200dpi 已完全解析原扫描点的硬边，二值化倾向强、大片同色 ⇒ zlib 压得更好。
⇒ **别把默认档从 1200 降到 600**（体积更大、清晰度更低，双输）；父级在另一页量到
1200dpi 7.4 MB/页，量级一致（页内容不同，绝对值会浮动）。

## 耗时（macOS 本机，venv/PyMuPDF 1.28.2，p370 实测）

**拆开量**：渲染 1200dpi **0.21 s/页**（MuPDF 只解码）＋ **PNG 编码 2.85 s/页**（zlib 是瓶颈）
＋ 组装 PDF ≈ 1.2 s/页（含 13 MB 落盘）⇒ **端到端 ≈ 6 s/页**
（3 页 p370–372 全流程实测 **18.5 s**，含组装与落盘）。
851 页的书 ≈ **80–90 分钟**（父级估 1 小时，同量级；本机单页 ±20% 浮动）。
**批量跑前务必先跑 3 页量一次本机**；PNG 编码是单线程纯 CPU，多页并行收益有限（磁盘会成瓶颈）。

## 返回（全部 JSON 可序列化；**永不抛**）

成功：`{"ok": True, "out", "bytes", "pages_done", "pages_total", "pages": [...], "dpi",
"elapsed_s", "resumed_from", "page_bytes_dir", "note"}`

失败：`{"ok": False, "reason": <BAD_DPI|BAD_RANGE|SRC_MISSING|SIZE_LIMIT|CANCELLED|ERROR>,
…, "pages_done", "pages_total"}` —— `SIZE_LIMIT` / `CANCELLED` **保留进度与页缓存**，可续跑。

## 红线

纯逻辑层：**不 import webview / streamlit / ui**、不读写 DB、不发网络；只碰 `src_pdf` /
`out_pdf` / 页缓存目录 / 进度文件。页缓存目录由本模块创建时，成功收尾会**删掉**（除非
`page_bytes_dir` 是调用方显式给的 —— 那是给 tab2 切图复用的，**不删**）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

try:                                    # PyMuPDF ≥1.24 新名；旧包回落 `fitz`
    import pymupdf as fitz
except ImportError:                     # pragma: no cover
    import fitz  # type: ignore

__all__ = [
    "ALLOWED_DPI",
    "DEFAULT_DPI",
    "DEFAULT_SIZE_LIMIT_BYTES",
    "PROGRESS_SCHEMA",
    "progress_path",
    "render_pdf_to_pdf",
    "read_progress",
]

#: dpi 白名单（Kevin 2026-10-20：**只三档**，不是任意整数）。顺序即 UI 档位顺序。
ALLOWED_DPI = (300, 600, 1200)
#: 默认档（1200：清晰度最高、体积反而最小，见模块 docstring 实测表）。
DEFAULT_DPI = 1200
#: 体积告警阈值（15 GiB）：851 页 × ~13 MB ≈ 11 GB，留余量；超了先报警而不是撑爆盘。
DEFAULT_SIZE_LIMIT_BYTES = 15 * 1024 ** 3
#: 进度文件 schema（加法字段随时加，不改既有键）。
PROGRESS_SCHEMA = "feicui.highres.progress.v1"


def progress_path(out_pdf) -> Path:
    """`<out>.progress.json`（**逐字**：输出 PDF 全路径后面直接接 `.progress.json`）。"""
    return Path(str(out_pdf) + ".progress.json")


def read_progress(out_pdf) -> dict:
    """读进度（无文件 / 坏 JSON ⇒ 空 dict，**不抛**）。"""
    p = progress_path(out_pdf)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    """原子写（同目录 tmp → replace）：避免取消/断电留下半截 JSON 让续跑误判。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _fail(reason: str, **kw) -> dict:
    out = {"ok": False, "reason": reason}
    out.update(kw)
    return out


def _page_cache_dir(out_pdf: Path, page_bytes_dir) -> tuple[Path, bool]:
    """⇒ `(页缓存目录, 是否本模块自建)`。显式给了 `page_bytes_dir` ⇒ 不自建（不删）。"""
    if page_bytes_dir:
        return Path(page_bytes_dir), False
    return out_pdf.parent / f".pages-{out_pdf.stem}", True


def _render_png(page, dpi: int) -> tuple[bytes, int, int]:
    """渲一页 ⇒ `(png_bytes, w_px, h_px)`。RGB 8bit，无 alpha（印谱是白底，alpha 只会增熵）。"""
    pix = page.get_pixmap(dpi=int(dpi), alpha=False, colorspace=fitz.csRGB)
    if pix.n != 3:                                   # 兜底：理论上 csRGB+alpha=False 恒为 3
        pix = page.get_pixmap(dpi=int(dpi), alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


def render_pdf_to_pdf(src_pdf, out_pdf, dpi: int = DEFAULT_DPI, page_from: int = 1,
                      page_to: int | None = None, page_bytes_dir=None,
                      progress_cb=None, cancel_event=None,
                      size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES) -> dict:
    """源 PDF 逐页渲成 PNG 再嵌进新 PDF（**断点续跑 / 体积告警 / 可取消**）。

    参数
    ----
    src_pdf : 源 PDF 路径（`output/1_Original_PDF/<书名>.pdf`）
    out_pdf : 目标 PDF 路径（`output/2_HighRes_PDF/<目录键>/<书名>-HighRes.pdf`）
    dpi     : **只接受 300 / 600 / 1200**（默认 1200）；非法 ⇒ `BAD_DPI`，不渲一页
    page_from / page_to : **1-based 闭区间**（`page_to=None` ⇒ 到末页）
    page_bytes_dir : 逐页 PNG 缓存目录（给了 ⇒ **保留**，供 tab2 切图直接复用；
                     不给 ⇒ 自建隐藏目录 `<out 同目录>/.pages-<书名>/`，成功后删除）
    progress_cb : `callable(dict)`，每页完成后回调
                  `{page, pages_total, pages_done, bytes, png_bytes, reused, msg}`（异常被吞）
    cancel_event: `threading.Event`；`is_set()` ⇒ 停（当前页渲完即停，不写半页）
    size_limit_bytes : 累计 PNG 字节上限（超过 ⇒ `SIZE_LIMIT`）

    返回：见模块 docstring「返回」。**永不抛。**
    """
    t_start = time.time()
    # ── 1. 参数校验（全部前置：别渲了 300 页才发现 dpi 非法）──────────────────
    try:
        dpi = int(dpi)
    except Exception:
        return _fail("BAD_DPI", dpi=dpi, allowed=list(ALLOWED_DPI))
    if dpi not in ALLOWED_DPI:
        return _fail("BAD_DPI", dpi=dpi, allowed=list(ALLOWED_DPI),
                     msg=f"dpi 只支持 {list(ALLOWED_DPI)}")
    src = Path(src_pdf)
    if not src.is_file():
        return _fail("SRC_MISSING", src=str(src), msg=f"源 PDF 不存在：{src}")
    out = Path(out_pdf)
    try:
        page_from = int(page_from or 1)
    except Exception:
        return _fail("BAD_RANGE", msg=f"page_from 必须是整数：{page_from!r}")
    try:
        if page_from < 1:
            return _fail("BAD_RANGE", msg="page_from 从 1 开始")
        page_to_i = None if page_to in (None, "") else int(page_to)
    except Exception:
        return _fail("BAD_RANGE", msg=f"page_to 必须是整数：{page_to!r}")
    if page_to_i is not None and page_to_i < page_from:
        return _fail("BAD_RANGE", msg=f"page_to({page_to_i}) < page_from({page_from})")

    cache_dir, cache_owned = _page_cache_dir(out, page_bytes_dir)
    prog_file = progress_path(out)

    try:
        doc = fitz.open(src)
    except Exception as exc:
        return _fail("ERROR", msg=f"打不开源 PDF：{exc.__class__.__name__}: {exc}", src=str(src))
    try:
        total_pages = doc.page_count
        last = total_pages if page_to_i is None else min(page_to_i, total_pages)
        if page_from > total_pages:
            return _fail("BAD_RANGE", msg=f"page_from({page_from}) 超出总页数({total_pages})",
                         pages_total=total_pages)
        want = list(range(page_from, last + 1))
        # ── 2. 进度：只在「同一本书 + 同一 dpi + 同一区间」时续跑，否则丢弃重来 ──
        prog = read_progress(out)
        resume_ok = (
            prog.get("schema") == PROGRESS_SCHEMA
            and int(prog.get("dpi") or 0) == dpi
            and str(prog.get("src") or "") == str(src)
            and list(prog.get("pages") or [])[:len(want)] == want[:len(want)]
        )
        done: dict[int, dict] = {}
        if resume_ok:
            for pno, rec in (prog.get("done") or {}).items():
                try:
                    pno_i = int(pno)
                except Exception:
                    continue
                png_file = cache_dir / str((rec or {}).get("png") or f"P{pno_i:04d}.png")
                # 缓存 PNG 必须还在（否则这页算没做完 ⇒ 重渲）
                if pno_i in want and png_file.is_file() and png_file.stat().st_size > 0:
                    done[pno_i] = dict(rec, png=png_file.name, path=str(png_file))
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 目标 PDF 已存在且进度显示整段做完 ⇒ 直接返回（幂等，不重渲）
        if len(done) == len(want):
            return {"ok": True, "out": str(out), "bytes": out.stat().st_size if out.is_file() else 0,
                    "pages_done": len(done), "pages_total": len(want), "pages": [],
                    "dpi": dpi, "elapsed_s": round(time.time() - t_start, 2),
                    "resumed_from": len(done), "page_bytes_dir": str(cache_dir),
                    "note": "整段已完成（进度文件 + 页缓存齐备），未重渲"}

        state = {
            "schema": PROGRESS_SCHEMA, "src": str(src), "out": str(out), "dpi": dpi,
            "pages": want, "done": {str(k): v for k, v in sorted(done.items())},
            "bytes": sum(int((v or {}).get("png_bytes") or 0) for v in done.values()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        pages_meta: list[dict] = []
        bytes_total = int(state["bytes"])
        reused = len(done)
        rendered = 0

        # ── 3. 逐页：渲 ⇒ PNG 落缓存 ⇒ 记进度 ─────────────────────────────────
        for pno in want:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                _write_json(prog_file, state)
                return _fail("CANCELLED", pages_done=len(done), pages_total=len(want),
                             bytes=bytes_total, page_bytes_dir=str(cache_dir),
                             out=str(out), dpi=dpi,
                             elapsed_s=round(time.time() - t_start, 2),
                             msg=f"已取消（完成 {len(done)}/{len(want)} 页，可续跑）")
            if pno in done:
                rec = done[pno]
                pages_meta.append({"page": pno, "px": rec.get("px"), "png_bytes": rec.get("png_bytes"),
                                   "png": rec.get("png"), "reused": True})
                continue
            png, w_px, h_px = _render_png(doc[pno - 1], dpi)
            png_file = cache_dir / f"P{pno:04d}.png"
            png_file.write_bytes(png)
            rec = {"px": [w_px, h_px], "png_bytes": len(png), "png": png_file.name,
                   "pt": [round(float(doc[pno - 1].rect.width), 3),
                          round(float(doc[pno - 1].rect.height), 3)]}
            done[pno] = rec
            rendered += 1
            bytes_total += len(png)
            state["done"][str(pno)] = rec
            state["bytes"] = bytes_total
            state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _write_json(prog_file, state)
            pages_meta.append({"page": pno, "px": [w_px, h_px], "png_bytes": len(png),
                               "png": png_file.name, "reused": False})
            if progress_cb is not None:
                try:
                    progress_cb({"page": pno, "pages_total": len(want),
                                 "pages_done": len(done), "bytes": bytes_total,
                                 "png_bytes": len(png), "reused": False,
                                 "msg": f"第 {pno} 页 {w_px}×{h_px}"})
                except Exception:
                    pass
            # 体积告警：**渲完这页就停**（进度留着，用户可换盘/清空间后续跑）
            if size_limit_bytes and bytes_total > int(size_limit_bytes):
                _write_json(prog_file, state)
                return _fail("SIZE_LIMIT", bytes=bytes_total, limit_bytes=int(size_limit_bytes),
                             pages_done=len(done), pages_total=len(want),
                             out=str(out), dpi=dpi, page_bytes_dir=str(cache_dir),
                             elapsed_s=round(time.time() - t_start, 2),
                             msg=(f"体积已超阈值（{bytes_total/1024**3:.2f} GiB > "
                                  f"{int(size_limit_bytes)/1024**3:.2f} GiB），已停在第 {pno} 页；"
                                  f"进度与页缓存已保留，可续跑"))

        # ── 4. 组装 PDF：页尺寸取源页 pt；PNG 流**原样嵌入**（MuPDF 存 /FlateDecode，不重压）──
        out.parent.mkdir(parents=True, exist_ok=True)
        built = fitz.open()
        tmp_out = out.with_name(out.name + ".part")
        for pno in want:
            rec = done[pno]
            w_pt, h_pt = rec.get("pt") or [doc[pno - 1].rect.width, doc[pno - 1].rect.height]
            np_page = built.new_page(width=float(w_pt), height=float(h_pt))
            np_page.insert_image(np_page.rect, stream=(cache_dir / rec["png"]).read_bytes())
        built.save(str(tmp_out), deflate=True)   # deflate=True：未压缩流压掉；图像流已是 Flate
        built.close()
        tmp_out.replace(out)

        out_bytes = out.stat().st_size
        prog = dict(state, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    out_bytes=out_bytes, status="done")
        _write_json(prog_file, prog)
        # 自建缓存目录且不是给 tab2 复用的 ⇒ 清掉（不给用户留几个 GB 的隐藏目录）
        if cache_owned:
            try:
                for f in cache_dir.glob("P*.png"):
                    f.unlink()
                cache_dir.rmdir()
            except Exception:
                pass
        note = ("高清化完成" if rendered else "全部命中缓存，未重渲")
        return {"ok": True, "out": str(out), "bytes": out_bytes,
                "pages_done": len(done), "pages_total": len(want), "pages": pages_meta,
                "dpi": dpi, "elapsed_s": round(time.time() - t_start, 2),
                "resumed_from": reused, "rendered_pages": rendered,
                "page_bytes_dir": str(cache_dir) if not cache_owned else None,
                "page_png_bytes": bytes_total, "note": note}
    except Exception as exc:                       # 兜底：桥不许断
        return _fail("ERROR", msg=f"{exc.__class__.__name__}: {exc}", src=str(src), out=str(out),
                     pages_done=len(locals().get("done") or {}),
                     elapsed_s=round(time.time() - t_start, 2))
    finally:
        try:
            doc.close()
        except Exception:
            pass
