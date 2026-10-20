#!/usr/bin/env python
# local-dist/tests/test_meta_resolve.py
"""`src/pdf_library.resolve_book_meta` 的**五级键回落**单测。

背景（用户实测 bug，2026-10-20）：tab1 写的侧车键是**原始名**
`{"秦印类编 检索版.pdf": {"dynasty": "秦", "author": "佚名"}}`；用户标准路径是 tab1 一键高清化
⇒ tab2 拿 `2_HighRes_PDF/<目录键>/秦印类编 检索版-HighRes.pdf` 切图。旧代码一律
`books.get(pdf.name)` ⇒ 恒空 ⇒ 文件名出 `0424_P99_C2_R1_中羞行府_NA_NA.tiff`。

本文件断言：
  1. 五级优先级各自命中：`exact` → `stripped-suffix` → `dir-key` → `stem-prefix` → `none`；
  2. 后缀形态：`-HighRes` / `_HighRes` / `-高清` / `_高清` / `-highres`（大小写不敏感、**只去一次**）；
  3. **歧义不猜**：多条 stem-prefix 命中 ⇒ `none`；
  4. **真实形还原例**（用户那本书）⇒ `(秦, 佚名, 'stripped-suffix')`；
  5. 只读：解析**不改**传入的 books、**不写**侧车（不新建 `-HighRes.pdf` 键）；永不抛。

跑法：`./venv/bin/python local-dist/tests/test_meta_resolve.py`
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import pdf_library as lib  # noqa: E402

QIN = {"dynasty": "秦", "author": "佚名"}
HAN = {"dynasty": "漢", "author": "吴颐人"}


class Exact(unittest.TestCase):
    def test_exact_name_hit(self):
        books = {"a.pdf": dict(QIN)}
        book, src, key = lib.resolve_book_meta("/x/1_Original_PDF/a.pdf", books=books)
        self.assertEqual((book, src, key), (QIN, "exact", "a.pdf"))


class StrippedSuffix(unittest.TestCase):
    def test_dash_highres(self):
        books = {"a.pdf": dict(QIN)}
        book, src, key = lib.resolve_book_meta("/x/2_HighRes_PDF/k/a-HighRes.pdf", books=books)
        self.assertEqual((book, src, key), (QIN, "stripped-suffix", "a.pdf"))

    def test_underscore_highres(self):
        books = {"a.pdf": dict(QIN)}
        book, src, key = lib.resolve_book_meta("/x/2_HighRes_PDF/k/a_HighRes.pdf", books=books)
        self.assertEqual((book, src, key), (QIN, "stripped-suffix", "a.pdf"))

    def test_chinese_suffixes_and_case_insensitive(self):
        for suffix in ("-高清", "_高清", "-highres", "-HIGHRES"):
            with self.subTest(suffix=suffix):
                books = {"a.pdf": dict(QIN)}
                book, src, key = lib.resolve_book_meta(f"/x/2_HighRes_PDF/k/a{suffix}.pdf",
                                                       books=books)
                self.assertEqual((src, key, book.get("dynasty")), ("stripped-suffix", "a.pdf", "秦"))

    def test_strip_only_once(self):
        """`a-HighRes-HighRes.pdf` 只去一次 ⇒ `a-HighRes.pdf`（命中就停，不连剥）。"""
        books = {"a.pdf": dict(QIN), "a-HighRes.pdf": dict(HAN)}
        book, src, key = lib.resolve_book_meta("/x/a-HighRes-HighRes.pdf", books=books)
        self.assertEqual((src, key, book.get("dynasty")), ("stripped-suffix", "a-HighRes.pdf", "漢"))

    def test_suffix_helper_keeps_empty_stem(self):
        """去完为空 ⇒ 原样返回（不拿空 stem 去撞键）。"""
        self.assertEqual(lib.strip_highres_suffix("-HighRes"), "-HighRes")
        self.assertEqual(lib.strip_highres_suffix("秦印类编 检索版-HighRes"), "秦印类编 检索版")
        self.assertEqual(lib.strip_highres_suffix("a_高清"), "a")


class DirKey(unittest.TestCase):
    def test_dir_key_hit(self):
        books = {"9787550847224.pdf": dict(QIN)}
        book, src, key = lib.resolve_book_meta(
            "/r/2_HighRes_PDF/9787550847224/某别的书名-HighRes.pdf", books=books)
        self.assertEqual((book, src, key), (QIN, "dir-key", "9787550847224.pdf"))

    def test_dir_key_bare_form(self):
        books = {"9787550847224": dict(QIN)}
        _, src, key = lib.resolve_book_meta(
            "/r/2_HighRes_PDF/9787550847224/某书.pdf", books=books)
        self.assertEqual((src, key), ("dir-key", "9787550847224"))

    def test_dir_key_requires_root_prefix_when_root_given(self):
        """给了 `root=` ⇒ 只有真在该 root 的 `2_HighRes_PDF/<键>/` 下才算 dir-key。"""
        books = {"9787550847224.pdf": dict(QIN)}
        path = Path("/r/2_HighRes_PDF/9787550847224/某书.pdf")
        ok, src, _ = lib.resolve_book_meta(path, root="/r", books=books)
        self.assertEqual((ok.get("dynasty"), src), ("秦", "dir-key"))
        _, src2, key2 = lib.resolve_book_meta(path, root="/other", books=books)
        self.assertEqual((src2, key2), ("none", ""))

    def test_stripped_suffix_beats_dir_key(self):
        """优先级：能按名去后缀命中就不必动用目录键（两键都在时取 stripped-suffix）。"""
        books = {"秦印类编 检索版.pdf": dict(QIN), "9787550847224.pdf": dict(HAN)}
        book, src, key = lib.resolve_book_meta(
            "/r/2_HighRes_PDF/9787550847224/秦印类编 检索版-HighRes.pdf", books=books)
        self.assertEqual((src, key), ("stripped-suffix", "秦印类编 检索版.pdf"))


class StemPrefix(unittest.TestCase):
    def test_unique_prefix_hit(self):
        # PDF 名比侧车键更长（如导出时追加了版本号）⇒ 唯一前缀命中
        books = {"秦印类编 检索版.pdf": dict(QIN)}
        book, src, key = lib.resolve_book_meta("/x/秦印类编 检索版 v2 印刷.pdf", books=books)
        self.assertEqual((book, src, key), (QIN, "stem-prefix", "秦印类编 检索版.pdf"))

    def test_ambiguous_prefix_is_not_guessed(self):
        """两条都能前缀匹配 ⇒ **不猜**，返回 none。"""
        books = {"秦印.pdf": dict(QIN), "秦印类编.pdf": dict(HAN)}
        book, src, key = lib.resolve_book_meta("/x/秦印类编 检索版.pdf", books=books)
        self.assertEqual((book, src, key), ({}, "none", ""))

    def test_none_when_nothing_matches(self):
        books = {"别的书.pdf": dict(QIN)}
        self.assertEqual(lib.resolve_book_meta("/x/某书-HighRes.pdf", books=books),
                         ({}, "none", ""))
        self.assertEqual(lib.resolve_book_meta("/x/某书.pdf", books={}), ({}, "none", ""))


class RealWorldShape(unittest.TestCase):
    """**用户实盘形态**：原始名入侧车 + 高清化产物切图 ⇒ 必须拿到 秦/佚名。"""

    def test_qin_yin_lei_bian_highres(self):
        books = {"秦印类编 检索版.pdf": dict(QIN)}
        path = ("/Users/kevin/Downloads/同步空间/feicui/2_HighRes_PDF/"
                "9787550847224/秦印类编 检索版-HighRes.pdf")
        book, src, key = lib.resolve_book_meta(path, books=books)
        self.assertEqual((book.get("dynasty"), book.get("author"), src),
                         ("秦", "佚名", "stripped-suffix"))
        self.assertEqual(key, "秦印类编 检索版.pdf")
        # 与该键所在 root 对得上时也仍走 stripped-suffix（优先级 2 < 3）
        _, src2, _ = lib.resolve_book_meta(
            path, root="/Users/kevin/Downloads/同步空间/feicui", books=books)
        self.assertEqual(src2, "stripped-suffix")


class ReadOnly(unittest.TestCase):
    def test_does_not_mutate_books_or_write_sidecar(self):
        books = {"秦印类编 检索版.pdf": dict(QIN)}
        snapshot = {k: dict(v) for k, v in books.items()}
        with mock.patch.object(lib, "load_meta", return_value={"books": books}), \
             mock.patch.object(lib, "save_meta") as fake_save:
            book, src, _ = lib.resolve_book_meta(
                "/r/2_HighRes_PDF/9787550847224/秦印类编 检索版-HighRes.pdf")
            book["dynasty"] = "漢"                          # 改返回值不得影响侧车
        self.assertEqual(src, "stripped-suffix")
        self.assertEqual(books, snapshot)                   # 侧车零污染（无 -HighRes.pdf 键）
        self.assertFalse(fake_save.called)

    def test_never_raises(self):
        for bad in (None, "", 0, object(), Path("/"), "\x00"):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(lib.resolve_book_meta(bad, books={"a.pdf": {}}),
                                 ({}, "none", ""))
        # 侧车读坏 / 读空 ⇒ 同样静默 none
        with mock.patch.object(lib, "load_meta", side_effect=RuntimeError("boom")):
            self.assertEqual(lib.resolve_book_meta("/x/a.pdf"), ({}, "none", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
