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
#: 五类过滤计数（inside_seal / edge / far / noise / **noise_text**＝释文污染）—— 与实测读数一致
TRUTH_DROPPED = {"inside_seal": 7, "edge": 2, "far": 0, "noise": 5, "noise_text": 0}


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


def _ocr(texts, boxes, scores=None):
    """注入式假 OCR（**不碰引擎**）：`texts/boxes` 等长。"""
    scores = scores or [0.99] * len(texts)
    return lambda _img: {"texts": list(texts), "scores": list(scores),
                         "boxes": [list(b) for b in boxes]}


def _run(texts, boxes, *, size=(2400, 1600), seal_boxes=None, **kw):
    """900 行×1600 列 纯黑页 ＋ 注入 OCR ＋ 手给印章框 ⇒ `extract_fields` 结果。"""
    img = np.zeros((size[0], size[1], 3), np.uint8)
    return fe.extract_fields(img, seal_boxes, ocr_fn=_ocr(texts, boxes), **kw)


class NoiseTextRules(unittest.TestCase):
    """**释文污染判定**（`is_noise_text`）——页码 / 类目标题 / 纯编号。"""

    def test_chinese_numeral_page_numbers(self):
        for t in ("〇〇三", "〇七二", "二七二", "〇", "一二", "三百二十", "〇九二"):
            with self.subTest(text=t):
                self.assertTrue(fe.is_noise_text(t), t)

    def test_category_titles(self):
        for t in ("單姓單名字印", "複姓單名字印", "官印目錄", "姓名印表"):
            with self.subTest(text=t):
                self.assertTrue(fe.is_noise_text(t), t)

    def test_two_char_words_not_noise(self):
        """2 字 `官印`/`私印` 可能是**真释文** ⇒ 不得当类目标题剔掉（只剔 ≥4 字标题）。"""
        for t in ("官印", "私印", "中候", "中羞行府", "都司馬印"):
            with self.subTest(text=t):
                self.assertFalse(fe.is_noise_text(t), t)

    def test_pure_code_is_noise_text_but_kept_as_code(self):
        """纯编号命中「污染」，但归属时按 `code` 走 ⇒ 编号字段照旧填上（防回流成释文）。"""
        self.assertTrue(fe.is_noise_text("0424"))
        res = _run(["0424"], [[[520, 760], [680, 760], [680, 820], [520, 820]]],
                   seal_boxes=[[500, 500, 700, 700]])
        s = res["seals"][0]
        self.assertEqual(s.get("code"), "0424")
        self.assertIsNone(s.get("inscription"))
        self.assertEqual(res["dropped"].get("noise_text"), 0)

    def test_custom_words_whitelist(self):
        self.assertFalse(fe.is_noise_text("本書索引"))
        self.assertTrue(fe.is_noise_text("本書索引", extra_words=("本書索引",)))

    def test_empty_is_not_noise(self):
        for t in ("", None, "   "):
            self.assertFalse(fe.is_noise_text(t))


class NoiseTextFiltering(unittest.TestCase):
    """污染在**归属前**剔掉；剔完无释文 ⇒ 留空 ＋ `needs_review`。"""

    SEAL = [[500, 500, 700, 700]]

    def test_page_number_does_not_become_inscription(self):
        res = _run(["〇七二"], [[[560, 740], [640, 740], [640, 800], [560, 800]]],
                   seal_boxes=self.SEAL)
        s = res["seals"][0]
        self.assertIsNone(s.get("inscription"))
        self.assertEqual(res["dropped"].get("noise_text"), 1)
        self.assertIn("〇七二", res["dropped_texts"]["noise_text"])
        self.assertTrue(s.get("needs_review"))

    def test_category_title_does_not_become_inscription(self):
        res = _run(["單姓單名字印"], [[[500, 200], [700, 200], [700, 460], [500, 460]]],
                   seal_boxes=self.SEAL)
        s = res["seals"][0]
        self.assertIsNone(s.get("inscription"))
        self.assertEqual(res["dropped_texts"]["noise_text"], ["單姓單名字印"])
        self.assertTrue(s.get("needs_review"))

    def test_clean_inscription_survives(self):
        res = _run(["中羞行府"], [[[560, 300], [640, 300], [640, 460], [560, 460]]],
                   seal_boxes=self.SEAL)
        self.assertEqual(res["seals"][0].get("inscription"), "中羞行府")
        self.assertEqual(res["dropped"].get("noise_text"), 0)


class StatusPositionRule(unittest.TestCase):
    """状态字：**位置窗口**（本格左侧字栏/编号行）＋ 一对一贪心；抢不到留空。"""

    SEAL = [[500, 500, 700, 700]]          # 200×200

    def test_in_window_left_of_seal_is_assigned(self):
        self.assertEqual(fe.status_window(self.SEAL[0], 200)[0], 500 - 1.6 * 200)
        res = _run(["官"], [[[390, 750], [410, 750], [410, 810], [390, 810]]],
                   seal_boxes=self.SEAL)      # 中心 (400,780)：左下字栏
        self.assertEqual(res["seals"][0].get("status"), "官")

    def test_out_of_window_is_left_empty_even_if_nearest(self):
        """右侧的单字**虽最近**也不得归它（旧口径就是在这里串格）。"""
        res = _run(["故"], [[[900, 750], [920, 750], [920, 810], [900, 810]]],
                   seal_boxes=self.SEAL)
        s = res["seals"][0]
        self.assertIsNone(s.get("status"))
        self.assertEqual(s.get("status_legacy"), "故")      # 旧口径会拿它 ⇒ 对照证据
        self.assertIsNone(s.get("status_score"))

    def test_above_seal_is_not_a_status_candidate(self):
        """印章**上方**的单字（上一格的字）同样不归它：y 窗口只认底边下方。"""
        res = _run(["風"], [[[560, 380], [640, 380], [640, 480], [560, 480]]],
                   seal_boxes=self.SEAL)
        self.assertIsNone(res["seals"][0].get("status"))

    def test_one_to_one_greedy_gives_nearest_only(self):
        """两印章争一个字 ⇒ **只给近者**，另一枚留空（不重复、不猜）。"""
        seals = [[200, 500, 400, 700], [500, 500, 700, 700]]     # 相邻两印
        res = _run(["官"], [[[390, 750], [410, 750], [410, 810], [390, 810]]],
                   seal_boxes=seals)                              # 中心 (400,780) 在两者窗口内
        got = [s.get("status") for s in res["seals"]]
        self.assertEqual(got, ["官", None])

    def test_strict_false_restores_legacy_behaviour(self):
        """`strict_status=False` ⇒ **完全回落旧口径**：不看位置、取最近单字（本例右侧那个 `故`）。"""
        texts, boxes = ["故"], [[[900, 750], [920, 750], [920, 810], [900, 810]]]
        strict = _run(texts, boxes, seal_boxes=self.SEAL)
        legacy = _run(texts, boxes, seal_boxes=self.SEAL, strict_status=False)
        self.assertIsNone(strict["seals"][0].get("status"))          # 新口径：窗口外 ⇒ 留空
        self.assertEqual(legacy["seals"][0].get("status"), "故")      # 旧口径：照拿最近单字
        self.assertFalse(legacy.get("strict_status"))
        self.assertTrue(strict.get("strict_status"))

    def test_status_legacy_kept_for_comparison(self):
        res = _run(["官"], [[[390, 750], [410, 750], [410, 810], [390, 810]]],
                   seal_boxes=self.SEAL)
        self.assertEqual(res["seals"][0].get("status_legacy"), "官")


class ReadingOrderSources(unittest.TestCase):
    """阅读顺序四级：编号 > 书级元数据（`book-meta`）> 兜底（切图台传 `rtl-ttb`）。"""

    SEALS = [[600, 400, 800, 600], [600, 1400, 800, 1600]]        # 两枚、**无编号**

    def test_book_meta_used_when_no_codes(self):
        res = _run(["中候"], [[[560, 260], [640, 260], [640, 380], [560, 380]]],
                   seal_boxes=self.SEALS, book_reading_order="rtl-ttb")
        self.assertEqual(res.get("reading_order"), "rtl-ttb")
        self.assertEqual(res.get("order_source"), "book-meta")

    def test_fallback_order_defaults_to_unchanged_ltr(self):
        res = _run(["中候"], [[[560, 260], [640, 260], [640, 380], [560, 380]]],
                   seal_boxes=self.SEALS)
        self.assertEqual(res.get("reading_order"), "ltr-ttb")     # 老行为一字不改
        self.assertEqual(res.get("order_source"), "fallback")

    def test_caller_fallback_order_is_honoured(self):
        res = _run(["中候"], [[[560, 260], [640, 260], [640, 380], [560, 380]]],
                   seal_boxes=self.SEALS, fallback_order="rtl-ttb")
        self.assertEqual(res.get("reading_order"), "rtl-ttb")
        self.assertEqual(res.get("order_source"), "fallback")

    def test_code_sequence_beats_book_meta(self):
        res = _run(["0601", "0602"],
                   [[[560, 260], [640, 260], [640, 380], [560, 380]],
                    [[560, 1260], [640, 1260], [640, 1380], [560, 1380]]],
                   seal_boxes=self.SEALS, book_reading_order="ltr-ttb")
        self.assertEqual(res.get("order_source"), "code-sequence")


class OrderAudit(unittest.TestCase):
    """`audit_order`：编号升序 vs (C,R) 字典序升序（**只审计、不阻断裁切**）。"""

    def test_consistent(self):
        a = fe.audit_order([{"code": "0001", "c": 1, "r": 1}, {"code": "0002", "c": 1, "r": 2}])
        self.assertEqual(a["status"], "consistent")

    def test_inconsistent_lists_violations(self):
        a = fe.audit_order([{"code": "0001", "c": 1, "r": 2}, {"code": "0002", "c": 1, "r": 1}])
        self.assertEqual(a["status"], "inconsistent")
        self.assertEqual(a["violations"][0]["code"], "0002")

    def test_no_code(self):
        self.assertEqual(fe.audit_order([{"code": "", "c": 1, "r": 1}])["status"], "no-code")
        self.assertEqual(fe.audit_order([])["status"], "no-code")

    def test_page_audit_is_flagged_but_cropping_not_blocked(self):
        """编号逆序的一页：`order_audit=inconsistent`，但印章数/裁切字段照旧齐全。"""
        seals = [[600, 200, 800, 400], [600, 700, 800, 900]]
        res = _run(["0002", "0001"],
                   [[[660, 440], [740, 440], [740, 500], [660, 500]],
                    [[660, 940], [740, 940], [740, 1000], [660, 1000]]],
                   seal_boxes=seals)
        self.assertEqual(res["count"], 2)
        self.assertEqual(res.get("order_audit", {}).get("status"), "inconsistent")
        self.assertEqual(sorted(s.get("code") for s in res["seals"]), ["0001", "0002"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
