#!/usr/bin/env python
# local-dist/tests/test_slice_size.py
"""切片**物理尺寸（mm）**口径单测 —— 零新依赖（unittest；TIFF 回读用既有 `tifffile`）。

被测（`local-dist/src/seal_crop.py`）：

  * `slice_size_mm()` —— 三级优先级 `manual-dpi` → `page-box` → `render-dpi` → `none`；
  * `slice_size_mm_raw()` —— **取整前**浮点（值域保护判它，避免「0.4mm 取整成 0」掩盖异常）；
  * `mm_half_up()` —— 四舍五入 **half-up**（不是银行家舍入：`2.5→3`、`0.5→1`、`3.5→4`）；
  * `mm_out_of_range()` —— `<0.5mm` / `>2000mm` ⇒ `size_suspect`；
  * `_write_tiff()` —— TIFF 里 `270` **只一条** ＋ `282/283/296` 正确（`sips` 读不出的历史坑）。

跑法：
    ./venv/bin/python local-dist/tests/test_slice_size.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import seal_crop as sc  # noqa: E402

# 真书页尺寸（秦印类编 检索版）：MediaBox 510.0 × 734.16 pt ＝ 179.9 × 259.0 mm
# 单测用「手算好对照」的取整尺寸：180.7 × 259.7 mm
PAGE_W_MM, PAGE_H_MM = 180.7, 259.7
PAGE_W_PT = PAGE_W_MM / 25.4 * 72.0                       # ≈ 512.22 pt
PAGE_H_PT = PAGE_H_MM / 25.4 * 72.0                       # ≈ 736.16 pt
RENDER_DPI = 1200
PAGE_PX_W = round(PAGE_W_PT * RENDER_DPI / 72.0)          # ≈ 8537 px
PAGE_PX_H = round(PAGE_H_PT * RENDER_DPI / 72.0)          # ≈ 12269 px


class SliceSizePriority(unittest.TestCase):
    """三级优先级 ＋ 全失败不造假。"""

    def test_page_box_matches_hand_calc(self):
        """1200dpi 页宽 ≈ 8537 px；切 300 px ⇒ 180.7/8537×300 ≈ 6.35 mm ⇒ **6**（整数）。"""
        self.assertEqual(PAGE_PX_W, 8537)
        w, h, src = sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (300, 300),
                                     page_px=(PAGE_PX_W, PAGE_PX_H))
        self.assertEqual(src, "page-box")
        self.assertEqual((w, h), (6, 6))
        # 取整前对照：6.349…（四舍五入 ⇒ 6）
        raw_w, _, _ = sc.slice_size_mm_raw((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (300, 300),
                                           page_px=(PAGE_PX_W, PAGE_PX_H))
        self.assertAlmostEqual(raw_w, 6.35, places=2)

    def test_manual_dpi_wins_and_is_4x(self):
        """`true_dpi=300` ⇒ 300/300×25.4 = 25.4 mm（＝**25**）；且仍是 page-box 值的 4 倍（1200/300）。"""
        w, h, src = sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (300, 300),
                                     true_dpi=300, page_px=(PAGE_PX_W, PAGE_PX_H))
        self.assertEqual(src, "manual-dpi")
        self.assertEqual((w, h), (25, 25))
        base_w, _, _ = sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (300, 300),
                                        page_px=(PAGE_PX_W, PAGE_PX_H))
        raw_manual, _, _ = sc.slice_size_mm_raw(None, RENDER_DPI, (300, 300), true_dpi=300)
        raw_page, _, _ = sc.slice_size_mm_raw((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (300, 300),
                                              page_px=(PAGE_PX_W, PAGE_PX_H))
        self.assertAlmostEqual(raw_manual / raw_page, 4.0, places=2)   # 1200/300
        self.assertEqual(base_w, 6)                                     # page-box 仍是 6

    def test_true_dpi_beats_page_box(self):
        """即使 page_rect 可用，`true_dpi` 也优先 ⇒ `manual-dpi`（用户意图优先）。"""
        _, _, src = sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), RENDER_DPI, (1200, 1200),
                                     true_dpi=1200, page_px=(PAGE_PX_W, PAGE_PX_H))
        self.assertEqual(src, "manual-dpi")

    def test_render_dpi_when_page_rect_missing(self):
        """页盒不可得（`None`）⇒ 回落 `render-dpi`：1200px/1200dpi×25.4 = 25.4 ⇒ 25。"""
        w, h, src = sc.slice_size_mm(None, 1200, (1200, 900))
        self.assertEqual(src, "render-dpi")
        self.assertEqual((w, h), (25, 19))

    def test_all_missing_is_none(self):
        """啥都没有 ⇒ `(None, None, 'none')`（**不造假**）。"""
        self.assertEqual(sc.slice_size_mm(None, None, (300, 300)), (None, None, "none"))
        self.assertEqual(sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), None, None),
                         (None, None, "none"))
        # 页盒给了但页像素缺失 ＋ render_dpi 缺失 ⇒ 仍 none（不瞎猜）
        self.assertEqual(sc.slice_size_mm((PAGE_W_PT, PAGE_H_PT), None, (300, 300)),
                         (None, None, "none"))

    def test_bad_dpi_rejected(self):
        """越界/非数值 dpi 一律不采用（`0`、`2401`、`'abc'`、bool）。"""
        for bad in (0, 49, 2401, "abc", True, None):
            _, _, src = sc.slice_size_mm(None, bad, (300, 300), true_dpi=bad)
            self.assertEqual(src, "none", msg=f"true_dpi/render_dpi={bad!r} 应被拒")


class HalfUpRounding(unittest.TestCase):
    """四舍五入 **half-up**（不是 Python 内置 `round()` 的银行家舍入）。"""

    def test_x5_rounds_up(self):
        self.assertEqual(sc.mm_half_up(2.5), 3)
        self.assertEqual(sc.mm_half_up(0.5), 1)
        self.assertEqual(sc.mm_half_up(3.5), 4)
        self.assertEqual(sc.mm_half_up(12.5), 13)
        # 对照：内置 round 是银行家舍入（这就是**不能**用它的证据）
        self.assertEqual(round(2.5), 2)
        self.assertEqual(round(0.5), 0)
        self.assertNotEqual(sc.mm_half_up(2.5), round(2.5))

    def test_x49_rounds_down(self):
        self.assertEqual(sc.mm_half_up(12.49), 12)
        self.assertEqual(sc.mm_half_up(6.35), 6)
        self.assertEqual(sc.mm_half_up(0.51), 1)

    def test_none_and_garbage(self):
        self.assertIsNone(sc.mm_half_up(None))
        self.assertIsNone(sc.mm_half_up("abc"))

    def test_returns_int(self):
        self.assertIsInstance(sc.slice_size_mm(None, 1200, (1200, 900))[0], int)


class ValueGuard(unittest.TestCase):
    """值域保护：判**取整前**浮点 ⇒ 极小值取整成 0 也仍标 suspect。"""

    def test_tiny_is_suspect_but_still_written(self):
        raw_w, raw_h, src = sc.slice_size_mm_raw(None, 1200, (10, 10), true_dpi=2400)
        self.assertEqual(src, "manual-dpi")
        self.assertLess(raw_w, 0.5)
        self.assertTrue(sc.mm_out_of_range(raw_w, raw_h))
        w, h, _ = sc.slice_size_mm(None, 1200, (10, 10), true_dpi=2400)
        self.assertEqual((w, h), (0, 0))                 # 取整成 0 —— 但 suspect 已标出异常
        self.assertFalse(sc.mm_out_of_range(6.0, 6.0))

    def test_huge_is_suspect(self):
        raw_w, raw_h, _ = sc.slice_size_mm_raw(None, 1200, (5000, 5000), true_dpi=50)
        self.assertGreater(raw_w, 2000)
        self.assertTrue(sc.mm_out_of_range(raw_w, raw_h))
        self.assertTrue(sc.mm_out_of_range(None, 2001.0))
        self.assertFalse(sc.mm_out_of_range(None, None))  # 没算出来 ≠ 异常

    def test_description_marks_suspect(self):
        self.assertEqual(sc.tiff_description(0, 0, 1200, "manual-dpi", suspect=True),
                         "feicui;width_mm=0;height_mm=0;dpi=1200;size_source=manual-dpi;suspect=1")


class ValidateTrueDpi(unittest.TestCase):
    """`pdf_library.validate_true_dpi`（50–2400 的整数；空＝不采用）。"""

    def test_positive(self):
        from src import pdf_library as lib
        self.assertEqual(lib.validate_true_dpi(None), (True, None))
        self.assertEqual(lib.validate_true_dpi(""), (True, None))
        self.assertEqual(lib.validate_true_dpi("  "), (True, None))
        self.assertEqual(lib.validate_true_dpi(300), (True, 300))
        self.assertEqual(lib.validate_true_dpi("300"), (True, 300))
        self.assertEqual(lib.validate_true_dpi("300.0"), (True, 300))
        self.assertEqual(lib.validate_true_dpi(50), (True, 50))
        self.assertEqual(lib.validate_true_dpi(2400), (True, 2400))

    def test_negative(self):
        from src import pdf_library as lib
        for bad in (49, 2401, 0, -1, "abc", "300.5"):
            ok, out = lib.validate_true_dpi(bad)
            self.assertFalse(ok, msg=f"{bad!r} 应被拒")
            self.assertIsInstance(out, str)
            self.assertTrue(out)


class TiffTags(unittest.TestCase):
    """TIFF 落盘：`270` **一条**、`282/283 = dpi`、`296 = 2(inch)`；回读能解析出 mm。"""

    def test_roundtrip(self):
        import numpy as np
        import tifffile

        arr = np.zeros((40, 60, 3), dtype=np.uint8)
        desc = sc.tiff_description(6, 6, 1200, "page-box")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "P99-C1-R1.tiff"
            sc._write_tiff(p, arr, dpi=1200, description=desc)     # noqa: SLF001（被测私有写入口径）
            with tifffile.TiffFile(p) as tf:
                page = tf.pages[0]
                tags270 = [t for t in page.tags.values() if t.code == 270]
                self.assertEqual(len(tags270), 1, "ImageDescription(270) 必须只有一条")
                got = tags270[0].value
                self.assertEqual(int(page.tags[282].value[0] / page.tags[282].value[1]), 1200)
                self.assertEqual(int(page.tags[283].value[0] / page.tags[283].value[1]), 1200)
                self.assertEqual(int(page.tags[296].value), 2)        # 2 = inch（3 是 cm）
                self.assertEqual((page.tags[256].value, page.tags[257].value), (60, 40))
            self.assertEqual(got, "feicui;width_mm=6;height_mm=6;dpi=1200;size_source=page-box")
            kv = dict(x.split("=", 1) for x in got.split(";") if "=" in x)
            self.assertEqual(kv["width_mm"], "6")
            self.assertEqual(kv["height_mm"], "6")
            self.assertEqual(kv["size_source"], "page-box")


if __name__ == "__main__":
    unittest.main(verbosity=2)
