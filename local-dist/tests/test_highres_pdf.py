#!/usr/bin/env python
# local-dist/tests/test_highres_pdf.py
"""`local-dist/src/highres_pdf.py` **v2 契约**单测 —— **零新依赖**（unittest；只读 PyMuPDF）。

覆盖 Kevin 2026-10-21 两项变更（Zang 定口径 A–G）：

* **A 全页输出**：输出 PDF 恒含源 PDF 全部页，第 i 页 ≡ 源第 i 页（页数 / 顺序 / pt 尺寸）；
* **B 角色三分**：`highres`（跳过渲染）/ `render`（渲本次档位）/ `passthrough`（原样复制页对象，
  保留文字层与页尺寸）；曾经高清化过、本次不在范围内的页**保持高清不降级**；
* **C 页级 dpi 登记表**：进度 schema v2（`units`），并**兼容读 v1**（`done` ＋ `prog.dpi` 迁移）；
* **D 位图可得性**：① 页缓存 → ② 旧 `out_pdf` 同页 `extract_image`（校验 px）→ ③ 重渲；
* **E/F/G**：新字段、失败不动 `out_pdf`、同参数幂等（第二次 `rendered_pages=0`）、
  旧 range-only 输出被重建为全页数且已达标页不重渲。

用**合成 PDF**（页宽 60+i × 高 80 pt，页内只有一行文字 `PAGE-i`）⇒ 300dpi 渲一页约 10 ms，
整套 < 10 s。**不碰 output/ 真实数据**（`tempfile.mkdtemp`）。

跑法：
    ./venv/bin/python local-dist/tests/test_highres_pdf.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

try:
    import pymupdf as fitz
except ImportError:                                       # pragma: no cover
    import fitz  # type: ignore

from src.highres_pdf import (                             # noqa: E402
    PROGRESS_SCHEMA,
    progress_path,
    read_progress,
    render_pdf_to_pdf,
)

N_PAGES = 10


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _make_src(path: Path, n: int = N_PAGES) -> None:
    """合成源 PDF：第 i 页尺寸 `60+i × 80` pt（尺寸逐页不同 ⇒ 能验「顺序/尺寸不变」），
    页内一行 `PAGE-i`（能验 passthrough 是否保留文字层）。"""
    doc = fitz.open()
    for i in range(1, n + 1):
        page = doc.new_page(width=60 + i, height=80)
        page.insert_text((5, 20), f"PAGE-{i}", fontsize=8)
    doc.save(str(path))
    doc.close()


def _legacy_png(path: Path, src: Path, pno: int, dpi: int) -> tuple[int, int]:
    """按老代码路径渲一页落 PNG（造 v1 进度用的页缓存）⇒ `(w_px, h_px)`。"""
    doc = fitz.open(str(src))
    pix = doc[pno - 1].get_pixmap(dpi=int(dpi), alpha=False, colorspace=fitz.csRGB)
    path.write_bytes(pix.tobytes("png"))
    w, h = pix.width, pix.height
    doc.close()
    return w, h


def _src_rects(path: Path) -> list[tuple[float, float]]:
    doc = fitz.open(str(path))
    rects = [(round(p.rect.width, 2), round(p.rect.height, 2)) for p in doc]
    doc.close()
    return rects


def _texts(path: Path) -> list[str]:
    doc = fitz.open(str(path))
    out = [p.get_text().strip() for p in doc]
    doc.close()
    return out


def _write_v1_progress(out: Path, src: Path, dpi: int, pages: list[int],
                       done: dict[str, dict]) -> None:
    prog = {"schema": "feicui.highres.progress.v1", "src": str(src), "out": str(out),
            "dpi": int(dpi), "pages": list(pages), "done": done,
            "bytes": sum(int((r or {}).get("png_bytes") or 0) for r in done.values()),
            "updated_at": "2026-10-20T00:00:00"}
    progress_path(out).parent.mkdir(parents=True, exist_ok=True)
    progress_path(out).write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")


class HighResV2Test(unittest.TestCase):
    """v2 口径（A–G）逐条对拍。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="feicui-hr-"))
        self.src = self.tmp / "src.pdf"
        self.out = self.tmp / "2_HighRes_PDF" / "9787000000001" / "b-HighRes.pdf"
        self.cache = self.tmp / "var" / "highres_pages" / "b"
        _make_src(self.src)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── t1：范围 4–6@300 ⇒ 输出 10 页 · 顺序/尺寸不变 · 第 1 页仍有文字层 · 第 4 页变位图 ──
    def test_t1_range_keeps_all_pages_and_passthrough_text(self) -> None:
        res = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=4, page_to=6,
                                page_bytes_dir=self.cache)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["pdf_pages_total"], N_PAGES)
        self.assertEqual(res["pages_total"], 3)            # 进度条分母＝本次范围内页数
        self.assertEqual(res["rendered_pages"], 3)
        self.assertEqual(res["passthrough_pages"], 7)
        self.assertEqual(res["skipped_pages"], 0)
        self.assertEqual(res["pages_done"], 3)

        src_rects, out_rects = _src_rects(self.src), _src_rects(self.out)
        self.assertEqual(len(out_rects), N_PAGES)
        self.assertEqual(src_rects, out_rects)             # 顺序 + pt 尺寸逐页一致

        texts = _texts(self.out)
        self.assertEqual(texts[0], "PAGE-1")               # passthrough 保留文字层
        self.assertEqual(texts[2], "PAGE-3")
        self.assertEqual(texts[3], "")                     # 第 4 页已变位图（无文字层）
        self.assertEqual(texts[6], "PAGE-7")
        self.assertEqual(texts[9], "PAGE-10")

        doc = fitz.open(str(self.out))
        self.assertEqual(len(doc[3].get_images(full=True)), 1)   # 位图页
        self.assertEqual(len(doc[0].get_images(full=True)), 0)   # 原样页
        doc.close()

        prog = read_progress(self.out)
        self.assertEqual(prog["schema"], PROGRESS_SCHEMA)
        self.assertEqual(sorted(prog["units"], key=int), ["4", "5", "6"])

    # ── t2：先 4–6@1200，再 1–10@600 ⇒ 4–6 跳过（不降级）、其余 7 页渲 ──
    def test_t2_second_run_skips_pages_already_at_higher_dpi(self) -> None:
        r1 = render_pdf_to_pdf(self.src, self.out, dpi=1200, page_from=4, page_to=6,
                               page_bytes_dir=self.cache)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["rendered_pages"], 3)

        r2 = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=1, page_to=10,
                               page_bytes_dir=self.cache)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(r2["rendered_pages"], 7)
        self.assertEqual(r2["skipped_pages"], 3)
        self.assertEqual(r2["passthrough_pages"], 0)
        self.assertEqual(r2["pdf_pages_total"], N_PAGES)
        self.assertEqual(r2["units_best_dpi"], 1200)

        prog = read_progress(self.out)
        dpi_by_page = {int(k): int(v["dpi"]) for k, v in prog["units"].items()}
        for pno in (4, 5, 6):
            self.assertEqual(dpi_by_page[pno], 1200)        # 已达标页**不降级**
        for pno in (1, 2, 3, 7, 8, 9, 10):
            self.assertEqual(dpi_by_page[pno], 600)
        self.assertEqual(prog["run"]["dpi"], 600)
        self.assertEqual(prog["run"]["rendered"], 7)
        self.assertEqual(prog["run"]["skipped"], 3)

        doc = fitz.open(str(self.out))
        self.assertEqual(doc.page_count, N_PAGES)
        doc.close()

    # ── t3：同参数再跑 ⇒ rendered=0 / skipped=10 / 页数 10 / 进度 JSON 不损坏 ──
    def test_t3_identical_rerun_is_idempotent(self) -> None:
        args = dict(dpi=600, page_from=1, page_to=10, page_bytes_dir=self.cache)
        r1 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["rendered_pages"], 10)
        sha1 = _sha(self.out)

        r2 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(r2["rendered_pages"], 0)
        self.assertEqual(r2["skipped_pages"], 10)
        self.assertEqual(r2["passthrough_pages"], 0)
        self.assertEqual(r2["pdf_pages_total"], N_PAGES)
        self.assertEqual(_sha(self.out), sha1)             # 校验通过 ⇒ 连重建都不必

        prog = read_progress(self.out)                     # 坏 JSON ⇒ {}
        self.assertEqual(prog.get("schema"), PROGRESS_SCHEMA)
        self.assertEqual(len(prog.get("units") or {}), 10)
        self.assertEqual(prog.get("status"), "done")
        self.assertEqual(prog["run"]["rendered"], 0)

    # ── t4：清空页缓存 PNG ⇒ 靠旧 out_pdf 同页位图恢复，rendered 仍为 0（D②）──
    def test_t4_recovers_from_existing_out_pdf_when_cache_gone(self) -> None:
        args = dict(dpi=600, page_from=1, page_to=10, page_bytes_dir=self.cache)
        r1 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r1["ok"], r1)
        shutil.rmtree(self.cache)                          # 页缓存整个清掉
        self.assertFalse(self.cache.exists())

        r2 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(r2["rendered_pages"], 0)
        self.assertEqual(r2["skipped_pages"], 10)
        self.assertEqual(r2["pdf_pages_total"], N_PAGES)
        doc = fitz.open(str(self.out))
        self.assertEqual(doc.page_count, N_PAGES)
        self.assertEqual(len(doc[0].get_images(full=True)), 1)   # 位图还在，没被 passthrough 掉
        doc.close()

    # ── t5：v1 进度文件可迁移（v1 JSON + 页缓存 ⇒ 不重渲）──
    def test_t5_v1_progress_migrates_without_rerender(self) -> None:
        self.cache.mkdir(parents=True, exist_ok=True)
        done: dict[str, dict] = {}
        doc = fitz.open(str(self.src))
        for pno in (4, 5, 6):
            w, h = _legacy_png(self.cache / f"P{pno:04d}.png", self.src, pno, 300)
            done[str(pno)] = {"px": [w, h], "png_bytes": (self.cache / f"P{pno:04d}.png").stat().st_size,
                              "png": f"P{pno:04d}.png",
                              "pt": [round(float(doc[pno - 1].rect.width), 3),
                                     round(float(doc[pno - 1].rect.height), 3)]}
        doc.close()
        _write_v1_progress(self.out, self.src, 300, [4, 5, 6], done)

        res = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=4, page_to=6,
                                page_bytes_dir=self.cache)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["rendered_pages"], 0)         # v1 做过的 3 页没白扔
        self.assertEqual(res["skipped_pages"], 3)
        self.assertEqual(res["passthrough_pages"], 7)
        self.assertEqual(res["pdf_pages_total"], N_PAGES)

        prog = read_progress(self.out)                     # 写完升 v2
        self.assertEqual(prog["schema"], PROGRESS_SCHEMA)
        for pno in (4, 5, 6):
            self.assertEqual(int(prog["units"][str(pno)]["dpi"]), 300)

        texts = _texts(self.out)
        self.assertEqual(texts[0], "PAGE-1")
        self.assertEqual(texts[3], "")                     # 4–6 是位图

    # ── t6：旧 range-only 输出（页数 < 源页数）被重建为全页数，已达标页不重渲 ──
    def test_t6_legacy_range_only_out_is_rebuilt_to_full_page_count(self) -> None:
        # 造旧代码的产物：out.pdf 只有 4–6 三页（位图），进度 v1 记 pages=[4,5,6]、无页缓存
        self.out.parent.mkdir(parents=True, exist_ok=True)
        src_doc, old = fitz.open(str(self.src)), fitz.open()
        done: dict[str, dict] = {}
        for pno in (4, 5, 6):
            page = src_doc[pno - 1]
            rect = page.rect
            pix = page.get_pixmap(dpi=300, alpha=False, colorspace=fitz.csRGB)
            png = pix.tobytes("png")
            np_page = old.new_page(width=float(rect.width), height=float(rect.height))
            np_page.insert_image(np_page.rect, stream=png)
            done[str(pno)] = {"px": [pix.width, pix.height], "png_bytes": len(png),
                              "png": f"P{pno:04d}.png",
                              "pt": [round(float(rect.width), 3), round(float(rect.height), 3)]}
        old.save(str(self.out))
        old.close()
        src_doc.close()
        self.assertEqual(fitz.open(str(self.out)).page_count, 3)
        _write_v1_progress(self.out, self.src, 300, [4, 5, 6], done)

        res = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=4, page_to=6,
                                page_bytes_dir=self.cache)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["rendered_pages"], 0)          # 靠旧 out_pdf 同页位图恢复（页映射）
        self.assertEqual(res["skipped_pages"], 3)
        self.assertEqual(res["passthrough_pages"], 7)
        self.assertEqual(res["pdf_pages_total"], N_PAGES)

        doc = fitz.open(str(self.out))
        self.assertEqual(doc.page_count, N_PAGES)           # 重建为全页数
        doc.close()
        texts = _texts(self.out)
        self.assertEqual(texts[0], "PAGE-1")                # 顺序没被 4–6 顶掉
        self.assertEqual(texts[9], "PAGE-10")
        self.assertEqual(texts[3], "")

    # ── t7：CANCELLED 时 out_pdf 不变、units 保留；BAD_DPI / BAD_RANGE 仍前置拒绝 ──
    def test_t7_cancel_keeps_out_pdf_and_units(self) -> None:
        r1 = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=1, page_to=10,
                               page_bytes_dir=self.cache)
        self.assertTrue(r1["ok"], r1)
        sha_before = _sha(self.out)
        units_before = len(read_progress(self.out)["units"])

        class _Ev:
            def is_set(self) -> bool:
                return True

        res = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=1, page_to=10,
                                page_bytes_dir=self.cache, cancel_event=_Ev())
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "CANCELLED")
        self.assertEqual(_sha(self.out), sha_before)        # 不写半截、不覆盖上一版
        prog = read_progress(self.out)
        self.assertEqual(len(prog["units"]), units_before)  # 登记表保留
        self.assertEqual(sorted(int(k) for k in prog["units"]), list(range(1, 11)))
        self.assertEqual({int(v["dpi"]) for v in prog["units"].values()}, {300})

        bad_dpi = render_pdf_to_pdf(self.src, self.out, dpi=999, page_from=1, page_to=10,
                                    page_bytes_dir=self.cache)
        self.assertEqual(bad_dpi["reason"], "BAD_DPI")
        self.assertEqual(bad_dpi["allowed"], [300, 600, 1200])
        bad_range = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=8, page_to=3,
                                      page_bytes_dir=self.cache)
        self.assertEqual(bad_range["reason"], "BAD_RANGE")
        over = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=99, page_to=None,
                                 page_bytes_dir=self.cache)
        self.assertEqual(over["reason"], "BAD_RANGE")
        self.assertEqual(_sha(self.out), sha_before)        # 前置拒绝也不动产物


if __name__ == "__main__":
    unittest.main(verbosity=2)
