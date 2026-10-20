#!/usr/bin/env python
# local-dist/tests/test_ocr_fallback.py
"""**无 OCR 能力时的优雅降级**单测（`斐萃_lite` / 阶段 1 包）。

用户实测（2026-10-20，`斐萃_lite.app` 选第 99 页点「自动检测」）：红色横幅
`字段提取失败: ModuleNotFoundError: No module named 'rapidocr'`。根因是分层设计——
`feicui.spec` 阶段 1 把 `rapidocr`/`onnxruntime` 全进 `excludes`，lite 包**天生**不能做字段识别；
不可接受的是「点一下就抛」。本文件锁住降级契约：

1. `field_extract.ocr_capable()` 只**探测**（`find_spec`，不加载模型）：缺 `rapidocr` ⇒ False；
2. `extract_fields()` 在无 OCR 时**仍 `ok: True`**，只做红印检测，`seals` 三字段为空串、
   三个 `*_score` 为 None、`ocr_available=False`、`note` 指向手动填写/`斐萃_pro`，
   `reading_order` 回落 `ltr-ttb` / `order_source='fallback'`；
3. 有 OCR（注入 `ocr_fn`）时行为**不变**：字段照常抽取、`order_source='code-sequence'`；
4. `api.tab2_extract` 同样降级（`ok: True` + `ocr_available=False` + `fields_manual=True`），
   书级元数据有阅读顺序时 `order_source='book-meta'`；`api.tab3_ocr` 结构化拒绝
   `{ok:false, reason:'OCR_UNAVAILABLE'}`，**都不抛 `ModuleNotFoundError`**。

跑法：
    ./venv/bin/python local-dist/tests/test_ocr_fallback.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

import numpy as np  # noqa: E402

from src import field_extract as fe  # noqa: E402

#: 两枚「印章」框（不需要真红印：传 boxes ⇒ 跳过 detect_seals，只验降级逻辑）
BOXES = [{"x1": 80, "y1": 80, "x2": 280, "y2": 280},
         {"x1": 420, "y1": 80, "x2": 620, "y2": 280}]


def _page():
    """白底页图（1200×900，BGR）＋ 两枚**真红印**（`seal_detect` 可检出）。"""
    img = np.full((1200, 900, 3), 255, dtype=np.uint8)
    for b in BOXES:
        img[b["y1"]:b["y2"], b["x1"]:b["x2"]] = (0, 0, 255)
    return img


def _fake_ocr(_bgr):
    """假 OCR：每枚印右侧给「释文＋状态＋编号」（编号 ⇒ 可推断 code-sequence）。"""
    return {
        "texts": ["中司馬印", "官", "0421", "中候", "蟫", "0422"],
        "scores": [0.99, 0.98, 0.97, 0.96, 0.95, 0.94],
        "boxes": [
            [[300, 100], [400, 100], [400, 140], [300, 140]],
            [[300, 150], [330, 150], [330, 190], [300, 190]],
            [[300, 200], [370, 200], [370, 240], [300, 240]],
            [[640, 100], [740, 100], [740, 140], [640, 140]],
            [[640, 150], [670, 150], [670, 190], [640, 190]],
            [[640, 200], [710, 200], [710, 240], [640, 240]],
        ],
    }


class Probe(unittest.TestCase):
    """能力探测：只 find_spec，不加载模型。"""

    def test_missing_rapidocr_is_false(self):
        with mock.patch("importlib.util.find_spec", side_effect=lambda _n, *a, **k: None):
            self.assertFalse(fe.ocr_capable())

    def test_injected_ocr_fn_always_true(self):
        self.assertTrue(fe.ocr_capable(_fake_ocr))

    def test_missing_adapter_is_false(self):
        """`rapidocr` 在、适配层 `src.ocr_rapid` 缺 ⇒ 也不可用（lite 包两种形态都要挡住）。"""
        real = __import__("importlib.util", fromlist=["find_spec"]).find_spec

        def fake(name, *a, **k):
            return None if name == "src.ocr_rapid" else real(name, *a, **k)

        with mock.patch("importlib.util.find_spec", side_effect=fake):
            self.assertFalse(fe.ocr_capable())


class ExtractFieldsFallback(unittest.TestCase):
    """`extract_fields`：无 OCR 不抛、字段留空；有 OCR 行为不变。"""

    def test_no_ocr_returns_ok_with_blank_fields(self):
        with mock.patch.object(fe, "ocr_capable", return_value=False), \
                mock.patch.object(fe, "_ocr_items",
                                  side_effect=AssertionError("无 OCR 时不得调用 OCR")):
            r = fe.extract_fields(_page(), BOXES)
        self.assertTrue(r.get("ok"), r)
        self.assertIs(r.get("ocr_available"), False)
        self.assertEqual(len(r["seals"]), 2)
        for s in r["seals"]:
            self.assertEqual(s["inscription"], "")
            self.assertEqual(s["status"], "")
            self.assertEqual(s["code"], "")
            self.assertIsNone(s["inscription_score"])
            self.assertIsNone(s["status_score"])
            self.assertIsNone(s["code_score"])
            # 空字段仍参与命名（不得因「无释文」被剔除），C/R 照给
            self.assertIn("read_order", s)
            self.assertTrue(s["c"] >= 1 and s["r"] >= 1)
        self.assertEqual(r["reading_order"], "ltr-ttb")       # 无编号 ⇒ 兜底
        self.assertEqual(r["order_source"], "fallback")
        self.assertIn("斐萃_pro", r.get("note") or "")
        self.assertIn("手动", r.get("note") or "")

    def test_with_ocr_behaviour_unchanged(self):
        r = fe.extract_fields(_page(), BOXES, ocr_fn=_fake_ocr)
        self.assertTrue(r.get("ok"), r)
        self.assertIs(r.get("ocr_available"), True)
        got = {s["code"]: (s["inscription"], s["status"]) for s in r["seals"]}
        self.assertEqual(got, {"0421": ("中司馬印", "官"), "0422": ("中候", "蟫")})
        self.assertEqual(r["order_source"], "code-sequence")
        self.assertNotIn("note", r)                            # 可用时不多塞提示

    def test_error_path_still_never_raises(self):
        r = fe.extract_fields(None)
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("reason"), "NO_IMAGE")


try:                                                       # api.py 依赖面板/引擎，缺则跳过
    import api as api_mod
    API_ERR = ""
except Exception as exc:                                   # pragma: no cover
    api_mod, API_ERR = None, f"{exc.__class__.__name__}: {exc}"


@unittest.skipUnless(api_mod is not None, f"api.py 导入失败：{API_ERR}")
class ApiTab2Fallback(unittest.TestCase):
    """`tab2_extract`：lite 包点「自动检测」⇒ `ok:true` + 空字段 + `ocr_available:false`。"""

    def setUp(self):
        self.api = api_mod.FeicuiApi()
        self.tmp = Path(tempfile.mkdtemp(prefix="feicui-lite-"))
        self.api._root = str(self.tmp)
        self.pdf = self.tmp / "斐萃样书.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")               # 渲页被 mock，不需真 PDF

    def _run(self, book=None):
        book = book if book is not None else {}
        with mock.patch.object(api_mod, "ocr_available", return_value=False), \
                mock.patch.object(fe, "ocr_capable", return_value=False), \
                mock.patch.object(fe, "render_page", return_value=_page()), \
                mock.patch.object(api_mod.lib, "resolve_book_meta",
                                  return_value=(book, "none", None)), \
                mock.patch.object(api_mod.FeicuiApi, "_preview_with_fields",
                                  return_value=("", 0, 0)):
            return self.api.tab2_extract({"pdf": str(self.pdf), "page": 99})

    def test_lite_page99_ok_not_raise(self):
        r = self._run()
        self.assertTrue(r.get("ok"), r)
        self.assertIs(r.get("ocr_available"), False)
        self.assertIs(r.get("fields_manual"), True)
        self.assertEqual(r.get("page"), 99)
        self.assertEqual(r.get("count"), 2)
        self.assertEqual(len(r.get("boxes") or []), 2)
        self.assertEqual(r.get("order_source"), "fallback")
        self.assertEqual(r.get("reading_order"), "ltr-ttb")
        for s in r["seals"]:
            self.assertEqual((s["inscription"], s["status"], s["code"]), ("", "", ""))
        self.assertIn("斐萃_pro", r.get("note") or "")
        self.assertIn("红印检测", r.get("note") or "")
        self.assertNotIn("ModuleNotFoundError", str(r))

    def test_book_meta_orders_when_no_codes(self):
        r = self._run(book={"reading_order": "rtl-ttb"})
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r.get("reading_order"), "rtl-ttb")
        self.assertEqual(r.get("order_source"), "book-meta")

    def test_tab3_ocr_structured_rejection(self):
        sub = self.tmp / "3_Cropped_Tiff" / "test"
        sub.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(api_mod, "ocr_available", return_value=False):
            r = self.api.tab3_ocr({"subdir": "test", "name": "x.tif"})
        self.assertIs(r.get("ok"), False)
        self.assertEqual(r.get("reason"), "OCR_UNAVAILABLE")
        self.assertIn("斐萃_pro", r.get("msg") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
