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
* **二轮复验（Neng F1–F4）**：t11 范围外页位图丢失必须**按原 dpi 重渲**（`repaired_pages`，
  四项计数闭合）；t12 **同尺寸**换页的脏缓存必须靠内容指纹抓出（不得静默错页）；
  t13 `_verify_saved_pdf` 抛异常时不留 `.part`、`out_pdf` 不变；t14 登记项缺 `px` ⇒
  缓存侧与旧 PDF 侧都不放行（走修复重渲）。
* **终验 medium（Neng 实测）**：t15 `SIZE_LIMIT` 必须按**真实总量**计 —— 升级重渲
  （300⇒600）会**覆盖**旧页登记，旧代码 `bytes_total += len(png)` 只加不减 ⇒ 报数虚高
  （实测真 49756 B 报 63954 B）、限额虚警。t15 断言回调/返回/progress 三处 `bytes` 恒等于
  `sum(units[*].png_bytes)`，并验「限量 = 真实总量 ±1」的边界行为。

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
from unittest import mock

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


def _make_src_uniform(path: Path, n: int = 3) -> None:
    """合成源 PDF：每页**同尺寸** 120×160 pt，但**内容不同**（左半黑 / 下半黑 / 一行文字）。

    专门用于「同尺寸换页」脏缓存：宽高完全一样，只有内容指纹（`png_sha256`）抓得住。
    """
    doc = fitz.open()
    for i in range(1, n + 1):
        page = doc.new_page(width=120, height=160)
        if i % 3 == 1:
            page.draw_rect(fitz.Rect(0, 0, 60, 160), color=(0, 0, 0), fill=(0, 0, 0))
            page.insert_text((10, 150), "AAA", fontsize=20)
        elif i % 3 == 2:
            page.draw_rect(fitz.Rect(0, 80, 120, 160), color=(0, 0, 0), fill=(0, 0, 0))
            page.insert_text((10, 40), "BBB", fontsize=20)
        else:
            page.insert_text((10, 20), f"PAGE-{i}", fontsize=8)
    doc.save(str(path))
    doc.close()


def _gray_px(path: Path, idx: int, dpi: int = 50) -> tuple[int, int, bytes]:
    """按 50dpi 渲一页成灰度 ⇒ `(w, h, samples)`（比像素用，不落盘）。"""
    doc = fitz.open(str(path))
    pix = doc[idx].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    out = (pix.width, pix.height, pix.samples)
    doc.close()
    return out


def _mad(a: tuple[int, int, bytes], b: tuple[int, int, bytes]) -> float:
    """两页灰度图逐像素平均绝对差（0–255）。尺寸不同 ⇒ 255（视作完全不同）。"""
    if a[:2] != b[:2] or not a[2]:
        return 255.0
    return sum(abs(x - y) for x, y in zip(a[2], b[2])) / len(a[2])


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

    # ── t8：页缓存被换成 10×10 假 PNG + 旧 out.pdf 删掉 ⇒ 必须重渲（不把错图当整页嵌）──
    def test_t8_poisoned_cache_png_is_re_rendered(self) -> None:
        args: dict = dict(dpi=300, page_from=1, page_to=10, page_bytes_dir=self.cache)
        r1 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["rendered_pages"], 10)
        px_before = [int(v) for v in read_progress(self.out)["units"]["1"]["px"]]
        self.assertNotEqual(px_before, [10, 10])

        self.out.unlink()                                  # 只能靠页缓存（旧 PDF 恢复路走不通）
        fake = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
        (self.cache / "P0001.png").write_bytes(fake.tobytes("png"))

        r2 = render_pdf_to_pdf(self.src, self.out, **args)
        self.assertTrue(r2["ok"], r2)
        self.assertGreaterEqual(r2["rendered_pages"], 1)   # 缓存不可信 ⇒ 不静默 skipped
        self.assertEqual(r2["pdf_pages_total"], N_PAGES)

        px_after = [int(v) for v in read_progress(self.out)["units"]["1"]["px"]]
        self.assertEqual(px_after, px_before)              # 登记表是重渲后的真尺寸
        doc = fitz.open(str(self.out))
        xref, _smask, w, h = doc[0].get_images(full=True)[0][:4]
        self.assertEqual([int(w), int(h)], px_after)       # 输出页位图 ≠ 10×10
        self.assertNotEqual([int(w), int(h)], [10, 10])
        doc.close()

    # ── t9：resumed_from 口径 = skipped（passthrough 不是「续跑」）──
    def test_t9_resumed_from_counts_only_skipped(self) -> None:
        src6 = self.tmp / "src6.pdf"
        out6 = self.tmp / "out6" / "b6-HighRes.pdf"
        _make_src(src6, n=6)
        res = render_pdf_to_pdf(src6, out6, dpi=300, page_from=2, page_to=3,
                                page_bytes_dir=self.tmp / "cache6")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["rendered_pages"], 2)
        self.assertEqual(res["skipped_pages"], 0)
        self.assertEqual(res["passthrough_pages"], 4)
        self.assertEqual(res["resumed_from"], 0)           # 全新首跑：没有「续跑」可言
        self.assertEqual(res["pdf_pages_total"], 6)

    # ── t10：落盘后复核不通过 ⇒ PAGE_COUNT_MISMATCH，且 out.pdf 逐字节不变、无 .part 残留 ──
    def test_t10_page_count_mismatch_after_save_keeps_artifact(self) -> None:
        r1 = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=1, page_to=10,
                               page_bytes_dir=self.cache)
        self.assertTrue(r1["ok"], r1)
        sha_before = _sha(self.out)

        fake_bad = {"expected_pages": N_PAGES, "actual_pages": N_PAGES - 1, "page": 0}
        with mock.patch("src.highres_pdf._verify_saved_pdf", return_value=fake_bad):
            r2 = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=1, page_to=10,
                                   page_bytes_dir=self.cache)
        self.assertFalse(r2["ok"], r2)
        self.assertEqual(r2["reason"], "PAGE_COUNT_MISMATCH")
        self.assertEqual(r2["expected_pages"], N_PAGES)
        self.assertEqual(r2["actual_pages"], N_PAGES - 1)
        self.assertEqual(_sha(self.out), sha_before)       # 一字节不变
        self.assertEqual(list(self.out.parent.glob("*.part")), [])   # 无残留

    # ── t11（F1）：范围外页位图彻底丢失 ⇒ **按原 dpi 重渲**（不许降级成 passthrough）──
    def test_t11_out_of_range_pages_with_lost_bitmap_are_repaired(self) -> None:
        src = self.tmp / "src4.pdf"
        out = self.tmp / "out4" / "b4-HighRes.pdf"
        cache = self.tmp / "cache4"
        _make_src(src, n=4)
        r1 = render_pdf_to_pdf(src, out, dpi=300, page_from=1, page_to=4, page_bytes_dir=cache)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["rendered_pages"], 4)
        prog = read_progress(out)
        px_before = {pno: [int(v) for v in prog["units"][str(pno)]["px"]] for pno in (1, 2)}

        for pno in (1, 2):                                  # 缓存截断成 0 字节
            (cache / f"P{pno:04d}.png").write_bytes(b"")
        out.unlink()                                        # 旧件位图也没了

        r2 = render_pdf_to_pdf(src, out, dpi=300, page_from=3, page_to=4,
                               page_bytes_dir=cache)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(r2["repaired_pages"], 2)            # 救回来，不是 passthrough
        self.assertEqual(r2["passthrough_pages"], 0)
        self.assertEqual(r2["skipped_pages"], 2)             # 3–4 页本身达标 ⇒ 跳过
        self.assertEqual(r2["rendered_pages"], 0)
        self.assertEqual(
            r2["rendered_pages"] + r2["repaired_pages"] + r2["skipped_pages"]
            + r2["passthrough_pages"], r2["pdf_pages_total"])   # 四项闭合
        self.assertEqual(r2["pdf_pages_total"], 4)
        self.assertIn("修复 2 页（缓存/旧件位图丢失，按原 dpi 重渲）", r2["note"])

        doc = fitz.open(str(out))
        for pno in (1, 2):
            imgs = doc[pno - 1].get_images(full=True)
            self.assertEqual(len(imgs), 1, f"第 {pno} 页位图丢了（被降级成源页复制）")
            self.assertEqual([int(imgs[0][2]), int(imgs[0][3])], px_before[pno])
        doc.close()

        prog = read_progress(out)
        for pno in (1, 2):
            self.assertEqual(int(prog["units"][str(pno)]["dpi"]), 300)   # 原档不降级
            self.assertTrue(prog["units"][str(pno)].get("png_sha256"))
        self.assertEqual(prog["run"]["repaired"], 2)

        # 修复完再跑一次同参数 ⇒ 不该反复修复（修复结果也该是「达标」）
        r3 = render_pdf_to_pdf(src, out, dpi=300, page_from=3, page_to=4,
                               page_bytes_dir=cache)
        self.assertTrue(r3["ok"], r3)
        self.assertEqual(r3["repaired_pages"], 0)
        self.assertEqual(r3["skipped_pages"], 4)

    # ── t12（F2）：两页**同尺寸**互换缓存 ⇒ 宽高相等也得抓出来 ⇒ 改按原 dpi 修复重渲 ──
    def test_t12_same_size_swapped_cache_is_detected_and_repaired(self) -> None:
        src = self.tmp / "src_u3.pdf"
        out = self.tmp / "out_u3" / "u3-HighRes.pdf"
        cache = self.tmp / "cache_u3"
        _make_src_uniform(src, n=3)
        r1 = render_pdf_to_pdf(src, out, dpi=300, page_from=1, page_to=2, page_bytes_dir=cache)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["rendered_pages"], 2)
        px = {int(k): [int(v) for v in v["px"]] for k, v in read_progress(out)["units"].items()}
        self.assertEqual(px[1], px[2], "本用前置：两页必须同尺寸，否则宽高校验也能抓住")

        out.unlink()                                        # 只剩页缓存可走
        p1, p2 = cache / "P0001.png", cache / "P0002.png"
        b1, b2 = p1.read_bytes(), p2.read_bytes()
        p1.write_bytes(b2)                                  # 互换（尺寸不变、内容换了）
        p2.write_bytes(b1)

        r2 = render_pdf_to_pdf(src, out, dpi=300, page_from=3, page_to=3, page_bytes_dir=cache)
        self.assertTrue(r2["ok"], r2)
        self.assertGreaterEqual(r2["repaired_pages"], 1)     # 不静默复用错页
        self.assertEqual(
            r2["rendered_pages"] + r2["repaired_pages"] + r2["skipped_pages"]
            + r2["passthrough_pages"], r2["pdf_pages_total"])

        out_p1 = _gray_px(out, 0)
        src_p1, src_p2 = _gray_px(src, 0), _gray_px(src, 1)
        d1, d2 = _mad(out_p1, src_p1), _mad(out_p1, src_p2)
        self.assertLess(d1, 8.0, f"输出第 1 页 ≠ 源第 1 页（mean|Δ|={d1:.2f}）")   # 实测 ≈2.0
        self.assertGreater(d2, 40.0, f"判别力不足：换页差只有 {d2:.2f}")            # 实测 ≈127

        doc = fitz.open(str(out))
        xref, _sm, w, h = doc[0].get_images(full=True)[0][:4]
        self.assertEqual([int(w), int(h)], px[1])            # 像素尺寸仍是原登记
        doc.close()

    # ── t13（F3）：`_verify_saved_pdf` 自己抛异常 ⇒ ERROR，且**不留 GB 级 .part** ──
    def test_t13_verify_exception_leaves_no_part_file(self) -> None:
        r1 = render_pdf_to_pdf(self.src, self.out, dpi=300, page_from=1, page_to=10,
                               page_bytes_dir=self.cache)
        self.assertTrue(r1["ok"], r1)
        sha_before = _sha(self.out)

        with mock.patch("src.highres_pdf._verify_saved_pdf",
                        side_effect=RuntimeError("verify boom")):
            r2 = render_pdf_to_pdf(self.src, self.out, dpi=600, page_from=1, page_to=10,
                                   page_bytes_dir=self.cache)
        self.assertFalse(r2["ok"], r2)
        self.assertEqual(r2["reason"], "ERROR")
        self.assertIn("verify boom", r2["msg"])               # 原错误没被「删 .part 失败」遮蔽
        self.assertEqual(_sha(self.out), sha_before)          # out_pdf 一字节不变
        self.assertEqual(list(self.out.parent.glob("*.part")), [])

    # ── t14（F4）：登记项缺 `px` ⇒ 两侧都不许放行 ⇒ 走修复重渲，且 ok ──
    def test_t14_unit_without_px_is_not_reused(self) -> None:
        src = self.tmp / "src_nopx.pdf"
        out = self.tmp / "out_nopx" / "nopx-HighRes.pdf"
        cache = self.tmp / "cache_nopx"
        _make_src_uniform(src, n=3)
        r1 = render_pdf_to_pdf(src, out, dpi=300, page_from=1, page_to=2, page_bytes_dir=cache)
        self.assertTrue(r1["ok"], r1)
        px1 = [int(v) for v in read_progress(out)["units"]["1"]["px"]]

        prog = read_progress(out)
        prog["units"]["1"].pop("px", None)                    # 手造：第 1 页登记项缺 px
        progress_path(out).write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")

        # out.pdf 还在（同页有位图）—— 旧 PDF 侧也必须拒收缺 px 的登记
        r2 = render_pdf_to_pdf(src, out, dpi=300, page_from=3, page_to=3, page_bytes_dir=cache)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(r2["repaired_pages"], 1)             # 没被静默复用
        self.assertEqual(r2["skipped_pages"], 1)              # 第 2 页 px 齐备 ⇒ 正常复用
        self.assertEqual(
            r2["rendered_pages"] + r2["repaired_pages"] + r2["skipped_pages"]
            + r2["passthrough_pages"], r2["pdf_pages_total"])

        doc = fitz.open(str(out))
        self.assertEqual(len(doc[0].get_images(full=True)), 1)   # 修复后第 1 页仍有位图
        doc.close()
        prog = read_progress(out)
        self.assertEqual([int(v) for v in prog["units"]["1"]["px"]], px1)   # 重渲回填真尺寸
        self.assertEqual(int(prog["units"]["1"]["dpi"]), 300)

    # ── t15（终验 medium）：SIZE_LIMIT 按**真实总量**（净增量）计 —— 升级重渲不得虚高 ──
    def test_t15_size_limit_counts_net_increase(self) -> None:
        """4 页书 @300 全渲 ⇒ 升 1–4 到 @600：报数恒等于 `sum(units[*].png_bytes)`，
        且「限量 = 真实总量 -1」必触发 SIZE_LIMIT、「= 真实总量」不得触发。

        旧代码坑：`render` 分支 `bytes_total += len(png)` 没扣掉被覆盖旧页的 `png_bytes`
        ⇒ 升级第 1 页就把 300 的那份也算上（真 49756 B 报 63954 B）⇒ 真体积远低于阈值
        却被叫停。这里第 1 页就做**逐值**对拍，虚高必然红。
        """
        def _units_sum(units: dict) -> int:
            return sum(int((u or {}).get("png_bytes") or 0) for u in (units or {}).values())

        def _fixture(tag: str) -> tuple[Path, Path, Path, dict[int, int]]:
            """4 页书 @300 全渲（页缓存保留）⇒ `(src, out, cache, {页号: png_bytes@300})`。"""
            src = self.tmp / f"src15{tag}.pdf"
            out = self.tmp / f"out15{tag}" / "hr15-HighRes.pdf"
            cache = self.tmp / f"cache15{tag}"
            _make_src(src, n=4)
            r = render_pdf_to_pdf(src, out, dpi=300, page_from=1, page_to=4,
                                  page_bytes_dir=cache)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["rendered_pages"], 4)
            units = read_progress(out)["units"]
            self.assertEqual(r["page_png_bytes"], _units_sum(units))     # 首跑：返回 = units 和
            return src, out, cache, {int(k): int(v["png_bytes"]) for k, v in units.items()}

        # ── ① 先量「600 档真实总量」（size_limit_bytes=0 ⇒ 关掉限额），逐页对拍累计值 ──
        src, out, cache, at300 = _fixture("a")
        true300 = sum(at300.values())
        seen: list[tuple[int, int, int]] = []          # (页号, 回调报的累计 B, units 真和 B)

        def _cb(rec: dict) -> None:
            # 回调前一轮 progress 已落盘 ⇒ 现场读真和（这就是「UI 累计 MB」的同源数据）
            seen.append((int(rec["page"]), int(rec["bytes"]),
                         _units_sum(read_progress(out)["units"])))

        r600 = render_pdf_to_pdf(src, out, dpi=600, page_from=1, page_to=4,
                                 page_bytes_dir=cache, progress_cb=_cb, size_limit_bytes=0)
        self.assertTrue(r600["ok"], r600)
        self.assertEqual(r600["rendered_pages"], 4)     # 4 页都升级重渲
        self.assertEqual([s[0] for s in seen], [1, 2, 3, 4])
        for pno, reported, truth in seen:
            self.assertEqual(reported, truth,
                             f"第 {pno} 页累计体积≠units 和（报 {reported} / 真 {truth}）")
        true600 = _units_sum(read_progress(out)["units"])
        self.assertEqual(r600["page_png_bytes"], true600)
        self.assertEqual(seen[-1][1], true600)          # 回调末值 = 返回 = units 和

        # 净增量口径（逐值）：第 1 页 = 真300 - 旧1 + 新1；旧口径会多算一整份「旧1」
        new1 = int(read_progress(out)["units"]["1"]["png_bytes"])
        self.assertEqual(seen[0][1], true300 - at300[1] + new1)
        self.assertLess(seen[0][1], true300 + new1, "升级第 1 页就把旧页字节算两遍（虚高）")
        self.assertGreater(new1, at300[1], "本用前置：600 档第 1 页必须比 300 大")
        self.assertGreater(true600 - true300, 0, "本用前置：升级必增体积")
        print(f"\n[t15] 真300={true300} 真600={true600} 第1页净增='{at300[1]}→{new1}' "
              f"回调='{seen}' 旧口径虚高值={true300 + new1}")

        # ── ② 限量 = 真实总量 - 1 ⇒ 必须 SIZE_LIMIT（且报数就是真实总量、产物不动）──
        src, out, cache, at300_b = _fixture("b")
        self.assertEqual(at300_b, at300)                # 同一合成书 ⇒ 逐页字节可复现
        sha300 = _sha(out)
        lim_low = true600 - 1
        r_low = render_pdf_to_pdf(src, out, dpi=600, page_from=1, page_to=4,
                                  page_bytes_dir=cache, size_limit_bytes=lim_low)
        self.assertFalse(r_low["ok"], r_low)
        self.assertEqual(r_low["reason"], "SIZE_LIMIT")
        self.assertEqual(r_low["limit_bytes"], lim_low)
        self.assertEqual(r_low["bytes"], _units_sum(read_progress(out)["units"]))
        self.assertEqual(r_low["bytes"], true600)       # 4 页都升级完才越线 ⇒ 恰好真总量
        self.assertGreater(r_low["bytes"], lim_low)
        self.assertEqual(r_low["pages_done"], 4)
        self.assertEqual(read_progress(out)["bytes"], true600)
        self.assertEqual(_sha(out), sha300)             # 失败不写半截
        print(f"[t15] limit={lim_low}（真{true600}-1）⇒ reason={r_low['reason']} "
              f"bytes={r_low['bytes']} pages_done={r_low['pages_done']}")

        # ── ③ 限量 = 真实总量 ⇒ 不得触发（`>` 严格比较；虚高口径在这里会误停）──
        src, out, cache, at300_c = _fixture("c")
        self.assertEqual(at300_c, at300)
        r_eq = render_pdf_to_pdf(src, out, dpi=600, page_from=1, page_to=4,
                                 page_bytes_dir=cache, size_limit_bytes=true600)
        self.assertTrue(r_eq["ok"], r_eq)
        self.assertIsNone(r_eq.get("reason"))
        self.assertEqual(r_eq["rendered_pages"], 4)
        self.assertEqual(r_eq["page_png_bytes"], true600)
        self.assertEqual(r_eq["page_png_bytes"], _units_sum(read_progress(out)["units"]))
        self.assertEqual(read_progress(out)["bytes"], true600)
        doc = fitz.open(str(out))                       # 产物本身正常（4 页、每页一张位图）
        self.assertEqual(doc.page_count, 4)
        for pno in range(4):
            self.assertEqual(len(doc[pno].get_images(full=True)), 1)
        doc.close()
        print(f"[t15] limit={true600}（=真总量）⇒ ok={r_eq['ok']} "
              f"page_png_bytes={r_eq['page_png_bytes']} rendered={r_eq['rendered_pages']}")

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
