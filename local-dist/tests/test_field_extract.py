#!/usr/bin/env python
# local-dist/tests/test_field_extract.py
"""`local-dist/src/field_extract.py` ＋ 命名/解析口径单测 —— **零新依赖**（unittest；图像只用到
仓内已有的 `cv2`/`numpy`，OCR 走样本图上的真引擎或注入的假 `ocr_fn`）。

覆盖四件事（对齐 `docs/feicui.spec.md` 与 `src/seal_crop.py` docstring）：

1. **样本图真值对拍**（`tests/fixtures/sample_rtl_ttb.png`）：6 枚印的 编号/释文/状态 逐枚命中，
   阅读顺序 `rtl-ttb`、来源 `code-sequence`、四类过滤计数 `7/2/0/5`（inside/edge/far/noise）；
2. **反向断言**：`authoritative` 为空（`None` / `[]` / `set()` / `{}`）时**任何释文都不得被改动**
   —— 并且用「给了权威映射就会改」证明这条断言不是永远为真的空转；
3. **裁切命名**：`build_crop_name` 与文档示例逐字一致（`释文_朝代_作者` 段序）、无编号回落旧名、
   `/` 等非法字符清洗、空段 `NA`、超长 ≤200；
4. **tab3 兼容解析**：切图台新命名 `<编号>_P<页>_C<列>_R<行>_…tiff` 能被 `validator.parse_tiff_name`
   反解出 P/C/R 与三字段（旧模板仍照旧），且与 `build_crop_name` 互为逆运算。

跑法：
    ./venv/bin/python local-dist/tests/test_field_extract.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

import numpy as np  # noqa: E402

from src import field_extract as fe  # noqa: E402
from src import seal_crop as sc  # noqa: E402
from src import validator  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_rtl_ttb.png"
HAS_CV2 = importlib.util.find_spec("cv2") is not None
HAS_OCR = importlib.util.find_spec("rapidocr") is not None

#: 样本图真值（编号 ⇒ (释文, 状态)）；状态 `None` ⇒ 该印面上没有状态字
TRUTH = {
    "0421": ("中候", "蟫"),
    "0422": ("中司馬印", "官"),
    "0423": ("中司馬印", None),
    "0424": ("中羞行府", "故"),
    "0425": ("中羞行府", "官"),
    "0426": ("中羞行府", "全"),
}
#: 四类过滤计数（inside_seal / edge / far / noise）—— 与上一单实测读数一致
TRUTH_DROPPED = {"inside_seal": 7, "edge": 2, "far": 0, "noise": 5}


@unittest.skipUnless(FIXTURE.is_file() and HAS_CV2 and HAS_OCR,
                     "需要 tests/fixtures/sample_rtl_ttb.png ＋ cv2 ＋ rapidocr（缺则跳过真引擎对拍）")
class SampleImageTruth(unittest.TestCase):
    """样本图（右起竖排、6 枚印）逐枚真值对拍。"""

    @classmethod
    def setUpClass(cls):
        import cv2
        img = cv2.imread(str(FIXTURE))
        assert img is not None, f"读不到样本图：{FIXTURE}"
        cls.res = fe.extract_fields(img)                    # reading_order 缺省 auto
        cls.by_code = {(s.get("code") or ""): s for s in cls.res.get("seals") or []}

    def test_ok_and_six_seals(self):
        self.assertTrue(self.res.get("ok"))
        self.assertEqual(self.res.get("count"), 6)
        self.assertEqual(len(self.res.get("seals") or []), 6)
        self.assertEqual({s["code"] for s in self.res["seals"]}, set(TRUTH))

    def test_three_fields_per_seal(self):
        """**6/6 命中**：每枚的 释文 与 状态 都与真值一致（状态允许无 ⇒ None）。"""
        for code, (ins, status) in TRUTH.items():
            with self.subTest(code=code):
                s = self.by_code[code]
                self.assertEqual(s.get("inscription"), ins)
                self.assertEqual(s.get("status"), status)

    def test_reading_order_inferred_from_code_sequence(self):
        self.assertEqual(self.res.get("reading_order"), "rtl-ttb")
        self.assertEqual(self.res.get("order_source"), "code-sequence")

    def test_rtl_means_right_column_is_c1(self):
        """rtl ⇒ 右列 C1：0421（首枚、最右）在 C1-R1。"""
        s = self.by_code["0421"]
        self.assertEqual((s.get("c"), s.get("r")), (1, 1))
        self.assertEqual(s.get("read_order"), 1)

    def test_read_order_is_a_permutation(self):
        ranks = sorted(s.get("read_order") for s in self.res["seals"])
        self.assertEqual(ranks, [1, 2, 3, 4, 5, 6])

    def test_dropped_counts(self):
        self.assertEqual(self.res.get("dropped"), TRUTH_DROPPED)


class CorrectionPolicy(unittest.TestCase):
    """**反向断言**：`authoritative` 为空 ⇒ 一字不改；给了映射才改（证明断言不是空转）。

    用 900×900 纯黑图 ＋ 1 个手给框 ＋ 注入假 `ocr_fn`（不碰 OCR 引擎、不依赖样本图 ⇒ 任何机器都能跑）。
    """

    BOX = [[100, 100, 300, 300]]
    TEXT = "中候"

    def _run(self, authoritative):
        img = np.zeros((900, 900, 3), np.uint8)
        text = self.TEXT

        def ocr_fn(_img):
            return {"texts": [text], "scores": [0.42],
                    "boxes": [[[110, 420], [280, 420], [280, 470], [110, 470]]]}

        res = fe.extract_fields(img, self.BOX, ocr_fn=ocr_fn, authoritative=authoritative)
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(len(res["seals"]), 1, res)
        return res["seals"][0]

    def test_empty_authoritative_never_rewrites_inscription(self):
        for empty in (None, [], set(), {}, ()):
            with self.subTest(authoritative=empty):
                s = self._run(empty)
                self.assertEqual(s.get("inscription"), self.TEXT)
                self.assertNotIn("inscription_raw", s)          # 没被改过 ⇒ 不该有「原值」痕迹
                self.assertEqual(s.get("inscription_corrected_by"), None)

    def test_authoritative_mapping_would_rewrite(self):
        """对照组：`{原始: 核定}` 才允许改字（否则上一条断言可能只是「永远为真」）。"""
        s = self._run({self.TEXT: "中侯"})
        self.assertEqual(s.get("inscription"), "中侯")
        self.assertEqual(s.get("inscription_raw"), self.TEXT)
        self.assertEqual(s.get("inscription_corrected_by"), "authoritative")
        self.assertTrue(s.get("inscription_verified"))

    def test_low_score_marks_needs_review_only(self):
        """低分未验证 ⇒ 只标 `needs_review`（交人工），**不改字**。"""
        s = self._run(None)
        self.assertTrue(s.get("needs_review"))
        self.assertEqual(s.get("inscription"), self.TEXT)

    def test_verified_vocab_list_does_not_rewrite(self):
        """`authoritative` 只给「已核定词表」（list）时**只标 verified**，不改字。"""
        s = self._run([self.TEXT])
        self.assertEqual(s.get("inscription"), self.TEXT)
        self.assertTrue(s.get("inscription_verified"))
        self.assertFalse(s.get("needs_review"))


class CropNaming(unittest.TestCase):
    """`seal_crop.build_crop_name` —— 与模块 docstring / 前端预演 `foName` 同一口径。"""

    def test_documented_example_verbatim(self):
        name, naming = sc.build_crop_name(
            370, 1, 1, {"code": "0424", "inscription": "中羞行府"},
            dynasty="清中期", author="吳熙載")
        self.assertEqual(name, "0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff")
        self.assertEqual(naming, "with_code")

    def test_segment_order_is_inscription_dynasty_author(self):
        """段序＝释文_朝代_作者（不是 释文_作者_朝代）—— 文档/示例/前端三处必须同序。"""
        name, _ = sc.build_crop_name(1, 1, 1, {"code": "0001", "inscription": "甲"},
                                     dynasty="清", author="乙")
        self.assertEqual(name, "0001_P1_C1_R1_甲_清_乙.tiff")

    def test_legacy_name_when_no_code(self):
        name, naming = sc.build_crop_name(12, 3, 2, {"inscription": "中候"})
        self.assertEqual(name, "P12-C3-R2.tiff")
        self.assertEqual(naming, "legacy")

    def test_slash_and_empty_fields_cleaned_to_dash_and_na(self):
        name, _ = sc.build_crop_name(
            7, 2, 3, {"code": "04/24", "inscription": "", "dynasty": "", "author": ""})
        self.assertEqual(name, "04-24_P7_C2_R3_NA_NA_NA.tiff")
        self.assertNotIn("/", name)

    def test_book_meta_used_as_fallback(self):
        name, _ = sc.build_crop_name(5, 1, 1, {"code": "0002", "inscription": "中候"},
                                     dynasty="清中期", author="吳熙載")
        self.assertEqual(name, "0002_P5_C1_R1_中候_清中期_吳熙載.tiff")

    def test_long_name_fits_200(self):
        name, naming = sc.build_crop_name(
            1, 1, 1, {"code": "9999", "inscription": "甲" * 150},
            dynasty="清" * 40, author="乙" * 40)
        self.assertEqual(naming, "with_code")
        self.assertLessEqual(len(name), 200)
        self.assertTrue(name.startswith("9999_P1_C1_R1_"))
        # 三段都保留（各 ≥4 字），最坏情况才整名截断加 `~`
        self.assertIn("_", name)
        self.assertTrue(name.endswith(".tiff") or name.endswith("~"))


class GridOrder(unittest.TestCase):
    """`grid_order`：方向由 `reading_order` 决定（rtl ⇒ **右列 C1**）；缺省＝旧行为 ltr-ttb。"""

    BOXES = [[100, 100, 300, 300], [400, 100, 600, 300]]     # 左、右同带

    def test_rtl_puts_right_column_first(self):
        self.assertEqual(sc.grid_order(self.BOXES, reading_order="rtl-ttb"), [(2, 1), (1, 1)])

    def test_ltr_is_default(self):
        self.assertEqual(sc.grid_order(self.BOXES), [(1, 1), (2, 1)])
        self.assertEqual(sc.grid_order(self.BOXES, reading_order="ltr-ttb"), [(1, 1), (2, 1)])

    def test_btt_flips_row_numbering(self):
        boxes = [[100, 100, 300, 300], [100, 500, 300, 700]]  # 上、下两带
        self.assertEqual(sc.grid_order(boxes, reading_order="ltr-ttb"), [(1, 1), (1, 2)])
        self.assertEqual(sc.grid_order(boxes, reading_order="ltr-btt"), [(1, 2), (1, 1)])


class Tab3CompatParse(unittest.TestCase):
    """tab3 必须认**两套**名字（旧模板 ＋ 切图台新命名），否则新文件会显示「命名不合模板」。"""

    NEW = "0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff"
    OLD = "P370-C1-R1-中羞行府-清中期-吳熙載.tiff"

    def test_new_name_parses_page_col_row_and_fields(self):
        p = validator.parse_tiff_name(self.NEW)
        self.assertIsNotNone(p)
        self.assertEqual(p["naming"], "with_code")
        self.assertEqual((p["page"], p["col"], p["row"]), (370, 1, 1))
        self.assertEqual((p["shiwen"], p["dynasty"], p["author"]), ("中羞行府", "清中期", "吳熙載"))
        self.assertEqual(p["code"], "0424")

    def test_old_name_still_parses_as_legacy(self):
        p = validator.parse_tiff_name(self.OLD)
        self.assertEqual(p["naming"], "legacy")
        self.assertEqual((p["page"], p["col"], p["row"]), (370, 1, 1))
        self.assertEqual((p["shiwen"], p["dynasty"], p["author"]), ("中羞行府", "清中期", "吳熙載"))

    def test_both_are_standard(self):
        self.assertTrue(validator.is_standard_tiff(self.NEW))
        self.assertTrue(validator.is_standard_tiff(self.OLD))
        self.assertFalse(validator.is_standard_tiff("随手起的名字.tiff"))

    def test_round_trip_with_build_crop_name(self):
        """`build_crop_name` 产出 ⇒ `parse_tiff_name` 必须原样回来（新命名与旧名各一遍）。"""
        for code in ("0424", ""):
            name, naming = sc.build_crop_name(
                370, 2, 3, {"code": code, "inscription": "中羞行府"},
                dynasty="清中期", author="吳熙載")
            p = validator.parse_tiff_name(name)
            with self.subTest(name=name):
                self.assertIsNotNone(p)
                assert p is not None
                self.assertEqual(p["naming"], naming)
                self.assertEqual((p["page"], p["col"], p["row"]), (370, 2, 3))
                if naming == "with_code":
                    self.assertEqual((p["shiwen"], p["dynasty"], p["author"]),
                                     ("中羞行府", "清中期", "吳熙載"))
                else:                       # 无编号回落名只有 P/C/R（三字段留空 ⇒ 交人工填）
                    self.assertEqual((p["shiwen"], p["dynasty"], p["author"]), ("", "", ""))

    def test_bare_p_c_r_name_parses_without_fields(self):
        """`P370-C2-R3.tiff`（无编号回落名）也要能回填 P/C/R，否则 tab3 一律显示「命名不合模板」。"""
        p = validator.parse_tiff_name("P370-C2-R3.tiff")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p["naming"], "legacy")
        self.assertEqual((p["page"], p["col"], p["row"]), (370, 2, 3))
        self.assertEqual((p["shiwen"], p["dynasty"], p["author"]), ("", "", ""))
        self.assertTrue(validator.is_standard_tiff("P370-C2-R3.tiff"))

    def test_underscore_in_inscription_split_from_right(self):
        p = validator.parse_tiff_name("0001_P1_C1_R1_甲_乙_丙_清_吳.tiff")
        self.assertEqual((p["shiwen"], p["dynasty"], p["author"]), ("甲_乙_丙", "清", "吳"))

    def test_legacy_filename_builder_unchanged(self):
        self.assertEqual(validator.build_crop_filename(370, 1, 1, "中羞行府", "清中期", "吳熙載"),
                         self.OLD)
        self.assertEqual(validator.build_crop_filename(370, 1, 1, "中羞行府", "清中期", "吳熙載",
                                                       code="0424"), self.NEW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
