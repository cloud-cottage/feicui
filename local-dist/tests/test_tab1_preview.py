#!/usr/bin/env python
# local-dist/tests/test_tab1_preview.py
"""tab1 **PDF 快速预览**（`api.FeicuiApi.tab1_preview`）单测 —— 零新依赖（unittest ＋ 既有 PyMuPDF）。

被测契约（`local-dist/api.py::tab1_preview`）：
  * 入参 `{pdf, page=1, dpi=96, max_w=760}` ⇒ `{ok, page, total, png_b64, px_w, px_h,
    page_mm_w, page_mm_h, dpi, dpi_used, cached, elapsed_s}`；
  * **失败一律结构化**：`PDF_NOT_FOUND` / `PAGE_OUT_OF_PDF` / `RENDER_FAILED`（绝不抛）；
  * dpi 夹紧 36–200（超范围不报错）；宽度超 `max_w` ⇒ 等比缩（`px_w <= max_w`）；
  * **内存 LRU 8 张**（key=pdf路径+page+dpi+max_w）：同参第二次 `cached:true` 且几乎零耗时，
    第 9 张不同页 ⇒ 最久未用的那张被淘汰；
  * 96 dpi 单页渲染 < 0.3 s（预热后计时；合成 PDF，非真书）。

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
        self.assertEqual(lo["dpi"], 36)               # 夹紧到下界
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

    def test_lru_evicts_oldest_beyond_eight(self) -> None:
        for page in range(1, 10):                  # 9 张不同页 ⇒ 只留最近 8 张
            self.api.tab1_preview({"pdf": "合成书.pdf", "page": page})
        self.assertEqual(len(self.api._pv_cache), FeicuiApi.PREVIEW_CACHE_SIZE)
        keys = list(self.api._pv_cache.keys())
        self.assertNotIn(f"{self.pdf}|1|96|760", keys)      # 第 1 页（最久未用）已被淘汰
        self.assertIn(f"{self.pdf}|9|96|760", keys)
        back = self.api.tab1_preview({"pdf": "合成书.pdf", "page": 1})
        self.assertIs(back["cached"], False)                # 淘汰后必须重渲


if __name__ == "__main__":
    unittest.main(verbosity=2)
