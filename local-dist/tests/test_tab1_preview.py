#!/usr/bin/env python
# local-dist/tests/test_tab1_preview.py
"""tab1 **PDF 快速预览**（`api.FeicuiApi.tab1_preview`）单测 —— 零新依赖（unittest ＋ 既有 PyMuPDF）。

被测契约（`local-dist/api.py::tab1_preview` / `tab1_preview_batch`）：
  * 单页：`{pdf, page=1, dpi=96, max_w=760}` ⇒ `{ok, page, total, png_b64, px_w, px_h,
    page_mm_w, page_mm_h, dpi, dpi_used, cached, elapsed_s}`；
  * 批量：`{pdf, page_from=1, count=10, dpi=72, max_w=240}` ⇒ `{ok, total, start_page,
    count, count_returned, pages:[{page, png_b64, px_w, px_h, cached, …}], dpi, cached,
    elapsed_s}`（一「屏」最多 10 张；越界自动截到 total，不补占位）；
  * **失败一律结构化**：`PDF_NOT_FOUND` / `PAGE_OUT_OF_PDF` / `RENDER_FAILED`（绝不抛）；
  * dpi 夹紧 24–200（超范围不报错）；宽度超 `max_w` ⇒ 等比缩（`px_w <= max_w`）；
  * **内存 LRU 24 张、单页/批量共池**（key=pdf路径+page+dpi+max_w）：同参第二次
    `cached:true` 且几乎零耗时，超出容量 ⇒ 最久未用的那张被淘汰；
  * 96 dpi 单页渲染 < 0.3 s、72 dpi × 10 页批量 < 1.5 s（预热后计时；合成 PDF，非真书）。

跑法：
    ./venv/bin/python local-dist/tests/test_tab1_preview.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

# `api` 在 import 期就按 `FEICUI_DATA_DIR` 派生数据根 ⇒ **必须先指到临时目录**再 import
SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-pv-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from api import FeicuiApi  # noqa: E402

PAGES = 10
MM_W, MM_H = 179.9, 259.0                    # 510 × 734.16 pt（真书同款页面尺寸）
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def build_pdf(path: Path, pages: int = PAGES) -> None:
    """合成一份 N 页 PDF（真书页面尺寸；文字只用来让页面非空）。"""
    import pymupdf
    doc = pymupdf.open()
    for i in range(pages):
        pg = doc.new_page(width=510.0, height=734.16)
        pg.insert_text((72, 120), f"PAGE {i + 1}", fontsize=36)
    doc.save(str(path))
    doc.close()


def strip(payload: dict) -> dict:
    """去掉 base64 主体，便于失败信息可读。"""
    return {k: v for k, v in payload.items() if k != "png_b64"}


class Tab1Preview(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = SCRATCH / "feicui"
        (root / "1_Original_PDF").mkdir(parents=True, exist_ok=True)
        cls.root = root
        cls.pdf = root / "1_Original_PDF" / "合成书.pdf"
        build_pdf(cls.pdf)
        # 坏 PDF：后缀是 .pdf 但内容不是 ⇒ 打开/解析失败必须变成 RENDER_FAILED
        cls.broken = root / "1_Original_PDF" / "坏文件.pdf"
        cls.broken.write_bytes(b"this is definitely not a pdf\n")

    def setUp(self) -> None:
        self.api = FeicuiApi()
        self.api._root = str(self.root)      # 直接钉 root（免走登录 / 校验目录流程）

    # ── ① 正常渲染 ────────────────────────────────────────────────
    def test_render_page_ok(self) -> None:
        r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 3})
        self.assertTrue(r.get("ok"), strip(r))
        self.assertEqual(r["page"], 3)
        self.assertEqual(r["total"], PAGES)
        self.assertEqual(r["dpi"], 96)
        self.assertLessEqual(r["px_w"], 760)
        self.assertGreater(r["px_h"], 0)
        self.assertAlmostEqual(r["page_mm_w"], MM_W, delta=0.3)
        self.assertAlmostEqual(r["page_mm_h"], MM_H, delta=0.3)
        self.assertIs(r["cached"], False)
        png = base64.b64decode(r["png_b64"])
        self.assertTrue(png.startswith(PNG_MAGIC), "不是 PNG")
        self.assertGreater(len(png), 1000)
        for key in ("elapsed_s", "px_w", "px_h", "page_mm_w", "page_mm_h", "png_b64"):
            self.assertIn(key, r)
        json.dumps(strip(r), ensure_ascii=False)      # 只回 JSON 可序列化对象

    def test_max_w_scales_down(self) -> None:
        r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 1, "max_w": 300})
        self.assertTrue(r.get("ok"), strip(r))
        self.assertLessEqual(r["px_w"], 300)
        self.assertLess(r["dpi_used"], 96)            # 限宽靠降有效 dpi 实现

    def test_dpi_clamped_not_error(self) -> None:
        hi = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 1, "dpi": 5000})
        self.assertTrue(hi.get("ok"), strip(hi))
        self.assertEqual(hi["dpi"], 200)              # 夹紧到上界
        lo = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 2, "dpi": 1})
        self.assertTrue(lo.get("ok"), strip(lo))
        self.assertEqual(lo["dpi"], 24)               # 夹紧到下界（36⇒24，本单放宽）
        self.assertGreaterEqual(lo["px_w"], 1)

    def test_single_page_under_300ms(self) -> None:
        self.api.tab1_preview({"pdf": "合成书.pdf", "page": 3, "dpi": 36})  # 预热（import PyMuPDF）
        r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 4})
        self.assertTrue(r.get("ok"), strip(r))
        self.assertLess(r["elapsed_s"], 0.3, f"96dpi 单页 {r['elapsed_s']} s")

    # ── ② 结构化失败（不抛）──────────────────────────────────────
    def test_page_out_of_pdf(self) -> None:
        r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 99})
        self.assertFalse(r.get("ok"))
        self.assertEqual(r["reason"], "PAGE_OUT_OF_PDF")
        self.assertEqual(r["total"], PAGES)
        self.assertEqual(r["page"], 99)
        self.assertEqual(r.get("png_b64"), None)
        self.assertIn("超出范围", r.get("msg") or "")

    def test_page_zero_and_negative(self) -> None:
        for bad in (0, -3):
            r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": bad})
            self.assertFalse(r.get("ok"), bad)
            self.assertEqual(r["reason"], "PAGE_OUT_OF_PDF")
            self.assertEqual(r["total"], PAGES)

    def test_pdf_not_found(self) -> None:
        for raw in ("不存在.pdf", "/tmp/绝对路径不存在.pdf", ""):
            r = self.api.tab1_preview({"pdf": raw, "page": 1})
            self.assertFalse(r.get("ok"), raw)
            self.assertEqual(r["reason"], "PDF_NOT_FOUND")
            self.assertIn("找不到 PDF", r.get("msg") or "")

    def test_render_failed_on_broken_pdf(self) -> None:
        r = self.api.tab1_preview({"pdf": "坏文件.pdf", "page": 1})
        self.assertFalse(r.get("ok"), strip(r))
        self.assertEqual(r["reason"], "RENDER_FAILED")
        self.assertTrue(r.get("msg"))

    def test_empty_req_never_raises(self) -> None:
        for req in (None, {}, {"pdf": None}):
            r = self.api.tab1_preview(req)
            self.assertFalse(r.get("ok"))
            self.assertEqual(r["reason"], "PDF_NOT_FOUND")

    # ── ③ LRU 缓存（8 张）────────────────────────────────────────
    def test_cache_hit_same_params(self) -> None:
        first = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 2})
        second = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 2})
        self.assertIs(first["cached"], False)
        self.assertIs(second["cached"], True)
        self.assertEqual(first["png_b64"], second["png_b64"])   # 同一张图（没重渲）
        self.assertLessEqual(second["elapsed_s"], first["elapsed_s"])
        self.assertLess(second["elapsed_s"], 0.05)

    def test_cache_key_includes_dpi_and_max_w(self) -> None:
        a = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 5, "dpi": 96, "max_w": 760})
        b = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 5, "dpi": 120, "max_w": 760})
        c = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 5, "dpi": 96, "max_w": 400})
        self.assertIs(a["cached"], False)
        self.assertIs(b["cached"], False)          # 换 dpi ⇒ 不同 key
        self.assertIs(c["cached"], False)          # 换 max_w ⇒ 不同 key
        self.assertNotEqual(a["px_w"], c["px_w"])

    def test_lru_evicts_oldest_beyond_24(self) -> None:
        # 25 个不同 key（10 页 × dpi96 ＋ 10 页 × dpi72 ＋ 5 页 × dpi48）⇒ 只留最近 24 张
        for page in range(1, 11):
            self.api.tab1_preview({"pdf": "合成书.pdf", "page": page, "dpi": 96})
        for page in range(1, 11):
            self.api.tab1_preview({"pdf": "合成书.pdf", "page": page, "dpi": 72})
        for page in range(1, 6):
            self.api.tab1_preview({"pdf": "合成书.pdf", "page": page, "dpi": 48})
        self.assertEqual(len(self.api._pv_cache), FeicuiApi.PREVIEW_CACHE_SIZE)
        keys = list(self.api._pv_cache.keys())
        self.assertNotIn(f"{self.pdf}|1|96|760", keys)      # 第 1 个 key（最久未用）已被淘汰
        self.assertIn(f"{self.pdf}|5|48|760", keys)         # 最新进的留在池里
        back = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 1, "dpi": 96})
        self.assertIs(back["cached"], False)                # 淘汰后必须重渲


class Tab1PreviewBatch(unittest.TestCase):
    """`api.FeicuiApi.tab1_preview_batch`：一「屏」1–10 张、dpi 24–200、共池 LRU、越界截断。"""

    @classmethod
    def setUpClass(cls) -> None:
        root = SCRATCH / "feicui"
        (root / "1_Original_PDF").mkdir(parents=True, exist_ok=True)
        cls.root = root
        cls.pdf = root / "1_Original_PDF" / "合成书.pdf"
        if not cls.pdf.exists():
            build_pdf(cls.pdf)
        # 851 页大部头：与真书《秦印类编 检索版》同规模 ⇒ 849 + 10 越界 ⇒ 只剩 3 张
        cls.big = root / "1_Original_PDF" / "大部头851页.pdf"
        if not cls.big.exists():
            build_pdf(cls.big, pages=851)
        cls.broken = root / "1_Original_PDF" / "坏文件.pdf"
        if not cls.broken.exists():
            cls.broken.write_bytes(b"this is definitely not a pdf\n")

    def setUp(self) -> None:
        self.api = FeicuiApi()
        self.api._root = str(self.root)      # 直接钉 root（免走登录 / 校验目录流程）

    @staticmethod
    def strip_all(payload: dict) -> dict:
        """去掉 base64 主体（含 pages 里每张的），失败信息可读。"""
        out = dict(payload)
        out["pages"] = [{k: v for k, v in p.items() if k != "png_b64"}
                        for p in (payload.get("pages") or [])]
        return out

    # ── ① 正常批量 ────────────────────────────────────────────────
    def test_batch_ok_10_pages(self) -> None:
        r = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 1,
                                         "count": 10, "dpi": 72, "max_w": 240})
        self.assertTrue(r.get("ok"), self.strip_all(r))
        self.assertEqual(r["total"], PAGES)
        self.assertEqual(r["start_page"], 1)
        self.assertEqual(r["count"], 10)
        self.assertEqual(r["count_returned"], 10)
        self.assertEqual([p["page"] for p in r["pages"]], list(range(1, 11)))
        for p in r["pages"]:
            png = base64.b64decode(p["png_b64"])
            self.assertTrue(png.startswith(PNG_MAGIC), "不是 PNG")
            self.assertLessEqual(p["px_w"], 240)
            self.assertGreater(p["px_h"], 0)
        self.assertIs(r["cached"], False)
        self.assertLess(r["elapsed_s"], 1.5, f"10 页 72dpi 批量 {r['elapsed_s']} s")
        for key in ("total", "start_page", "pages", "count_returned", "elapsed_s"):
            self.assertIn(key, r)
        json.dumps(self.strip_all(r), ensure_ascii=False)    # 只回 JSON 可序列化对象

    def test_batch_count_clamped(self) -> None:
        hi = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 1, "count": 15})
        self.assertTrue(hi.get("ok"), self.strip_all(hi))
        self.assertEqual(hi["count"], 10)                    # 15 ⇒ 夹到单屏上限 10
        self.assertEqual(hi["count_returned"], 10)
        lo = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 1, "count": 0})
        self.assertTrue(lo.get("ok"), self.strip_all(lo))
        self.assertEqual(lo["count"], 1)                     # 0 ⇒ 夹到 1
        self.assertEqual(lo["count_returned"], 1)

    def test_batch_dpi_clamped_and_24dpi_renders(self) -> None:
        lo = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 3,
                                          "count": 2, "dpi": 10})
        self.assertTrue(lo.get("ok"), self.strip_all(lo))
        self.assertEqual(lo["dpi"], 24)                      # 10 ⇒ 夹到新下限 24
        self.assertGreaterEqual(lo["pages"][0]["px_w"], 1)
        png = base64.b64decode(lo["pages"][0]["png_b64"])
        self.assertTrue(png.startswith(PNG_MAGIC))           # 24dpi 可正常渲染
        hi = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 3,
                                          "count": 2, "dpi": 5000})
        self.assertTrue(hi.get("ok"), self.strip_all(hi))
        self.assertEqual(hi["dpi"], 200)                     # 上界不变

    def test_batch_truncated_at_total(self) -> None:
        r = self.api.tab1_preview_batch({"pdf": "大部头851页.pdf", "page_from": 849,
                                         "count": 10, "dpi": 72, "max_w": 240})
        self.assertTrue(r.get("ok"), self.strip_all(r))
        self.assertEqual(r["total"], 851)
        self.assertEqual(r["start_page"], 849)
        self.assertEqual(r["count_returned"], 3)             # 849/850/851，不足不补占位
        self.assertEqual([p["page"] for p in r["pages"]], [849, 850, 851])

    def test_batch_page_from_beyond_total_gives_empty(self) -> None:
        r = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 99, "count": 10})
        self.assertTrue(r.get("ok"), self.strip_all(r))
        self.assertEqual(r["count_returned"], 0)             # 整窗越出 ⇒ 空列表（不抛）
        self.assertEqual(r["pages"], [])

    def test_batch_zero_and_negative_page_from(self) -> None:
        for bad in (0, -5):
            r = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": bad, "count": 3})
            self.assertTrue(r.get("ok"), bad)
            self.assertEqual(r["start_page"], 1)             # 非法起点 ⇒ 收敛到 1

    # ── ② 缓存：与单页端点共池 ────────────────────────────────────
    def test_batch_cache_hit_same_params(self) -> None:
        req = {"pdf": "合成书.pdf", "page_from": 1, "count": 10, "dpi": 72, "max_w": 240}
        first = self.api.tab1_preview_batch(req)
        second = self.api.tab1_preview_batch(req)
        self.assertIs(first["cached"], False)
        self.assertIs(second["cached"], True)                # 同参二跑 ⇒ 整屏命中
        self.assertTrue(all(p["cached"] for p in second["pages"]))
        self.assertEqual(first["pages"][0]["png_b64"], second["pages"][0]["png_b64"])
        self.assertLess(second["elapsed_s"], 0.05)

    def test_cache_shared_between_single_and_batch(self) -> None:
        one = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 6, "dpi": 96, "max_w": 240})
        self.assertIs(one["cached"], False)
        bat = self.api.tab1_preview_batch({"pdf": "合成书.pdf", "page_from": 1,
                                           "count": 10, "dpi": 96, "max_w": 240})
        self.assertTrue(bat["pages"][5]["cached"])           # 第 6 页直接命中单页端点的缓存
        self.assertFalse(bat["pages"][0]["cached"])
        back = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 1, "dpi": 96, "max_w": 240})
        self.assertIs(back["cached"], True)                  # 反向：批量渲过的单页也命中
        self.assertLessEqual(len(self.api._pv_cache), FeicuiApi.PREVIEW_CACHE_SIZE)

    # ── ③ 结构化失败（不抛）──────────────────────────────────────
    def test_batch_errors_never_raise(self) -> None:
        for raw in ("不存在.pdf", "", None):
            r = self.api.tab1_preview_batch({"pdf": raw, "page_from": 1})
            self.assertFalse(r.get("ok"), raw)
            self.assertEqual(r["reason"], "PDF_NOT_FOUND")
        r = self.api.tab1_preview_batch({"pdf": "坏文件.pdf", "page_from": 1})
        self.assertFalse(r.get("ok"), self.strip_all(r))
        self.assertEqual(r["reason"], "RENDER_FAILED")
        self.assertTrue(r.get("msg"))
        for req in (None, {}, {"pdf": None}):
            r = self.api.tab1_preview_batch(req)
            self.assertFalse(r.get("ok"))
            self.assertEqual(r["reason"], "PDF_NOT_FOUND")

    def test_single_endpoint_dpi_floor_now_24(self) -> None:
        r = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 2, "dpi": 24})
        self.assertTrue(r.get("ok"), strip(r))
        self.assertEqual(r["dpi"], 24)                       # 单页端点同步放宽，不报错
        self.assertGreater(r["px_w"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
