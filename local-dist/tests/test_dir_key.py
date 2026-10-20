#!/usr/bin/env python
# local-dist/tests/test_dir_key.py
"""目录键改造（2026-10-20）单测 —— **零新依赖**（stdlib `unittest` + `tempfile`）。

口径（Kevin 裁定）：目录键**只认 tab1 人工确认的书名**（`manual`）；没确认 ⇒ 文件名主名
（`filename-fallback`）。`config/book_dir_keys.json` 已退场，**不再参与任何命名**；旧目录
＝ tab1 保存书名那一刻**自动改名迁移**（回读校验 ＋ 冲突不覆盖 ＋ 失败回滚 ＋ 留痕）。

本文件断言：
  1. `validate_book_name`：空/`None` 放行（⇒ 回落文件名）、`.`/`..`/含 `/`、`\\`/含控制字符
     **一律拒绝**、长度 1 与 80 放行、81 拒绝；
  2. `resolve_dir_key`：合法书名 ⇒ `manual`；留空 ⇒ `filename-fallback`（用 PDF 主名）；
     `legacy_map` **不参与**命名；`book=None` ⇒ 走 `resolve_book_meta`（五级键回落）；**永不抛**；
  3. `migrate_dir_key`：无旧目录 ⇒ `ok=True`；新旧同键 ⇒ no-op（**不改 mtime**）；旧在新无 ⇒
     move 且旧目录消失；新已存在 ⇒ **合并**，同名不同内容加 `-dupN`**两侧都保留**；幂等；
     真迁后**文件数/总字节一致**且抽样 sha256 一致；`dir_key_migrations` 有追加；
  4. **回滚**：monkeypatch 校验函数强制失败 ⇒ 文件全部回原位、新目录不残留；
  5. **真实形**：`3_Cropped_Tiff/9787550847224/`（3 个 TIFF + `_fields.json`）＋
     `book_name='秦印类编 检索版'` ⇒ 迁到新目录、旧目录不存在。

跑法：`./venv/bin/python local-dist/tests/test_dir_key.py`
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import pdf_library as lib  # noqa: E402

PDF_NAME = "秦印类编 检索版.pdf"
OLD_KEY = "9787550847224"
NEW_KEY = "秦印类编 检索版"


# ─────────────────────── 夹具 ───────────────────────
class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="feicui-dirkey-"))
        self.root = self.tmp / "feicui"
        for sub in lib.SUB_DIRS:
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.store = self.tmp / "var" / "pdf_meta.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --
    def tiff_dir(self, key: str) -> Path:
        return self.root / lib.TIFF_DIR / key

    def put(self, key: str, name: str, data: bytes) -> Path:
        d = self.tiff_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def files(self, key: str) -> dict[str, bytes]:
        d = self.tiff_dir(key)
        if not d.is_dir():
            return {}
        return {p.relative_to(d).as_posix(): p.read_bytes()
                for p in sorted(d.rglob("*")) if p.is_file()}

    def pdf(self, name: str = PDF_NAME) -> Path:
        p = self.root / lib.ORIGINAL_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4\n%fake\n")
        return p

    def sha(self, path: Path) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ─────────────────── ① validate_book_name ───────────────────
class ValidateBookName(unittest.TestCase):
    def test_none_and_empty_pass_as_no_name(self):
        for v in (None, "", "   ", "\t\n"):
            with self.subTest(v=repr(v)):
                self.assertEqual(lib.validate_book_name(v), (True, None))

    def test_normal_name_trimmed(self):
        self.assertEqual(lib.validate_book_name("  秦印类编 检索版  "), (True, "秦印类编 检索版"))

    def test_dot_and_dotdot_rejected(self):
        for v in (".", ".."):
            with self.subTest(v=v):
                ok, msg = lib.validate_book_name(v)
                self.assertFalse(ok)
                self.assertIn(v, str(msg))

    def test_path_separators_rejected(self):
        for v in ("a/b", "a\\b", "/abs", "..\\x", "x/y/z"):
            with self.subTest(v=v):
                ok, msg = lib.validate_book_name(v)
                self.assertFalse(ok, f"应拒绝 {v!r}")
                self.assertIn("路径分隔符", str(msg))

    def test_control_chars_rejected(self):
        for v in ("a\x00b", "a\nb", "a\rb", "a\tb", "a\x7fb"):
            with self.subTest(v=v):
                ok, msg = lib.validate_book_name(v)
                self.assertFalse(ok, f"应拒绝 {v!r}")
                self.assertIn("控制字符", str(msg))

    def test_length_boundaries(self):
        self.assertEqual(lib.validate_book_name("秦"), (True, "秦"))          # 1 字
        eighty = "书" * 80
        self.assertEqual(lib.validate_book_name(eighty), (True, eighty))     # 80 字
        ok, msg = lib.validate_book_name("书" * 81)                          # 81 字
        self.assertFalse(ok)
        self.assertIn("80", str(msg))

    def test_never_raises(self):
        class Weird:
            def __str__(self):
                raise RuntimeError("boom")
        ok, msg = lib.validate_book_name(Weird())
        self.assertFalse(ok)
        self.assertIn("不合法", str(msg))


# ───────────────────── ② resolve_dir_key ─────────────────────
class ResolveDirKey(Base):
    def test_manual_when_book_name_valid(self):
        p = self.pdf()
        key, src = lib.resolve_dir_key(p, book={"book_name": NEW_KEY})
        self.assertEqual((key, src), (NEW_KEY, "manual"))

    def test_filename_fallback_when_book_name_empty(self):
        p = self.pdf("随便 一本书.pdf")
        for book in ({}, {"book_name": ""}, {"book_name": "   "}, {"book_name": None}):
            with self.subTest(book=book):
                key, src = lib.resolve_dir_key(p, book=book)
                self.assertEqual((key, src), ("随便 一本书", "filename-fallback"))

    def test_filename_fallback_strips_extension_only(self):
        key, src = lib.resolve_dir_key("/x/2_HighRes_PDF/k/秦印类编 检索版.pdf", book={})
        self.assertEqual((key, src), ("秦印类编 检索版", "filename-fallback"))

    def test_filename_fallback_strips_highres_suffix(self):
        """高清化 PDF 且无 book_name ⇒ 目录键**不带** `-HighRes`（与原始 PDF 同键）。

        回落目录名带后缀会让用户困惑（对不上 `1_Original_PDF/<书名>.pdf`）。
        """
        key, src = lib.resolve_dir_key(
            str(self.root / "2_HighRes_PDF" / "9787550847224" / "秦印类编 检索版-HighRes.pdf"),
            book={},
        )
        self.assertEqual((key, src), ("秦印类编 检索版", "filename-fallback"))

    def test_filename_fallback_strips_each_suffix_variant(self):
        """四个后缀变体口径一致：`-HighRes` / `_HighRes` / `-高清` / `_高清`（大小写不敏感）。"""
        for name in ("秦印类编 检索版-HighRes", "秦印类编 检索版_HighRes",
                     "秦印类编 检索版-highres", "秦印类编 检索版-高清",
                     "秦印类编 检索版_高清"):
            with self.subTest(name=name):
                key, src = lib.resolve_dir_key("/x/2_HighRes_PDF/k/%s.pdf" % name, book={})
                self.assertEqual((key, src), ("秦印类编 检索版", "filename-fallback"))

    def test_filename_fallback_suffix_only_keeps_original_stem(self):
        """剥完为空（文件名就是 `-HighRes.pdf`）⇒ 回原 stem，不产出空键。"""
        key, src = lib.resolve_dir_key("/x/-HighRes.pdf", book={})
        self.assertEqual((key, src), ("-HighRes", "filename-fallback"))

    def test_legacy_map_never_used_for_naming(self):
        p = self.pdf()
        key, src = lib.resolve_dir_key(p, book={}, legacy_map={"a.pdf": OLD_KEY,
                                                             PDF_NAME: OLD_KEY})
        self.assertEqual((key, src), ("秦印类编 检索版", "filename-fallback"))
        self.assertNotEqual(key, OLD_KEY)                  # 旧映射**不得**参与命名

    def test_book_none_reads_sidecar(self):
        with mock.patch.object(lib, "DEFAULT_META_PATH", self.store):
            lib.save_meta({"books": {PDF_NAME: {"book_name": NEW_KEY}}}, self.store)
            key, src = lib.resolve_dir_key(self.pdf(), root=self.root)
        self.assertEqual((key, src), (NEW_KEY, "manual"))

    def test_book_none_no_sidecar_falls_back(self):
        with mock.patch.object(lib, "DEFAULT_META_PATH", self.store):
            key, src = lib.resolve_dir_key(self.pdf(), root=self.root)
        self.assertEqual((key, src), ("秦印类编 检索版", "filename-fallback"))

    def test_never_raises_on_garbage(self):
        for bad in (None, "", object(), 12345):
            with self.subTest(bad=type(bad).__name__):
                key, src = lib.resolve_dir_key(bad, book={"book_name": "../逃逸"})
                self.assertIsInstance(key, str)
                self.assertEqual(src, "filename-fallback")

    def test_source_in_documented_domain(self):
        self.assertEqual(lib.DIR_KEY_SOURCES, ("manual", "filename-fallback"))


# ─────────────────---- ③ migrate_dir_key ─────────────────────
class MigrateNoLegacy(Base):
    def test_no_legacy_dir_is_ok(self):
        ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertTrue(ok)
        self.assertEqual(stats["status"], "no-legacy")
        self.assertIn("无旧目录", msg)
        self.assertFalse(self.tiff_dir(NEW_KEY).exists())

    def test_same_key_is_noop_and_keeps_mtime(self):
        p = self.put(OLD_KEY, "a.tiff", b"AAA")
        before = p.stat().st_mtime_ns
        ok, _msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, OLD_KEY, store=self.store)
        self.assertTrue(ok)
        self.assertEqual(stats["status"], "noop-same")
        self.assertEqual(p.stat().st_mtime_ns, before)                      # 不碰文件
        self.assertEqual(self.files(OLD_KEY), {"a.tiff": b"AAA"})

    def test_invalid_new_key_rejected(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, "坏/键", store=self.store)
        self.assertFalse(ok)
        self.assertEqual(stats["status"], "invalid")
        self.assertEqual(self.files(OLD_KEY), {"a.tiff": b"AAA"})


class MigrateMove(Base):
    def test_move_old_to_new(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        self.put(OLD_KEY, "sub/b.tiff", b"BBBB")
        before = self.files(OLD_KEY)
        n_before, b_before = lib._dir_file_stats(self.tiff_dir(OLD_KEY))
        sample = self.tiff_dir(OLD_KEY) / "a.tiff"
        sha_before = self.sha(sample)

        ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertTrue(ok, msg)
        self.assertEqual(stats["status"], "moved")
        self.assertFalse(self.tiff_dir(OLD_KEY).exists())                   # 旧目录消失
        self.assertEqual(self.files(NEW_KEY), before)                       # 内容一字不差
        n_after, b_after = lib._dir_file_stats(self.tiff_dir(NEW_KEY))
        self.assertEqual((n_after, b_after), (n_before, b_before))
        self.assertEqual(self.sha(self.tiff_dir(NEW_KEY) / "a.tiff"), sha_before)

    def test_merge_same_name_different_content_keeps_both(self):
        self.put(OLD_KEY, "a.tiff", b"OLD-CONTENT")
        self.put(OLD_KEY, "b.tiff", b"OLD-B")
        self.put(NEW_KEY, "a.tiff", b"NEW-CONTENT")
        old_sha = self.sha(self.tiff_dir(OLD_KEY) / "a.tiff")

        ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertTrue(ok, msg)
        self.assertEqual(stats["status"], "merged")
        self.assertGreaterEqual(stats["dup_renamed"], 1)
        got = self.files(NEW_KEY)
        self.assertEqual(set(got), {"a.tiff", "a-dup1.tiff", "b.tiff"})     # 两侧都保留
        self.assertEqual(got["a.tiff"], b"NEW-CONTENT")                     # 目标件不被覆盖
        self.assertEqual(got["a-dup1.tiff"], b"OLD-CONTENT")                # 旧件改名保留
        self.assertEqual(hashlib.sha256(got["a-dup1.tiff"]).hexdigest(), old_sha)
        self.assertFalse(self.tiff_dir(OLD_KEY).exists())

    def test_merge_identical_file_is_dropped_once(self):
        self.put(OLD_KEY, "same.tiff", b"SAME")
        self.put(OLD_KEY, "only.tiff", b"ONLY-OLD")
        self.put(NEW_KEY, "same.tiff", b"SAME")
        ok, msg, _stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertTrue(ok, msg)
        self.assertEqual(self.files(NEW_KEY), {"same.tiff": b"SAME", "only.tiff": b"ONLY-OLD"})
        self.assertFalse(self.tiff_dir(OLD_KEY).exists())
        self.assertFalse(any(self.tiff_dir(NEW_KEY).glob(".migrate-holding")))  # 暂存清掉

    def test_idempotent_second_run_is_noop(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        self.put(OLD_KEY, "b.tiff", b"BBBB")
        lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        snapshot = self.files(NEW_KEY)
        p = self.tiff_dir(NEW_KEY) / "a.tiff"
        mtime = p.stat().st_mtime_ns
        ok, _msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertTrue(ok)
        self.assertEqual(stats["status"], "no-legacy")                      # 旧已不在 ⇒ 无事可做
        self.assertEqual(self.files(NEW_KEY), snapshot)                     # 文件数/内容不变
        self.assertEqual(p.stat().st_mtime_ns, mtime)

    def test_migration_recorded_in_sidecar(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        with mock.patch.object(lib, "DEFAULT_META_PATH", self.store):
            ok, msg, _ = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY,
                                             book_key=PDF_NAME, store=self.store)
        self.assertTrue(ok, msg)
        rows = lib.load_meta(self.store)["books"][PDF_NAME]["dir_key_migrations"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["from"], row["to"]), (OLD_KEY, NEW_KEY))
        self.assertEqual(row["status"], "moved")
        self.assertEqual(row["files"], 1)
        self.assertEqual(row["bytes"], 3)
        self.assertTrue(row["ts"])


class MigrateRollback(Base):
    """校验函数被强制弄坏 ⇒ 必须**全部回原位**，新目录不残留。"""

    def test_rollback_on_bad_stats(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        self.put(OLD_KEY, "b.tiff", b"BBBB")
        before = self.files(OLD_KEY)
        with mock.patch.object(lib, "_dir_file_stats", return_value=(999, 999999)):
            ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertFalse(ok)
        self.assertEqual(stats["status"], "verify-failed")
        self.assertIn("回滚", msg)
        self.assertFalse(self.tiff_dir(NEW_KEY).exists())                   # 新目录不残留
        self.assertEqual(self.files(OLD_KEY), before)                        # 文件全部回原位

    def test_rollback_on_bad_sha(self):
        self.put(OLD_KEY, "a.tiff", b"AAA")
        before = self.files(OLD_KEY)
        calls = {"n": 0}

        def fake_sha(path):
            calls["n"] += 1
            return "pre" if calls["n"] == 1 else "post"      # 抽样前/后不一致

        with mock.patch.object(lib, "_sha256", side_effect=fake_sha):
            ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertFalse(ok)
        self.assertIn("抽样", msg)
        self.assertEqual(stats["status"], "verify-failed")
        self.assertFalse(self.tiff_dir(NEW_KEY).exists())
        self.assertEqual(self.files(OLD_KEY), before)

    def test_rollback_merge_case(self):
        """合并分支（新目录已存在）也要回滚：旧件回到旧目录，新目录只留原有件。"""
        self.put(OLD_KEY, "a.tiff", b"OLD")
        self.put(NEW_KEY, "a.tiff", b"NEW")
        with mock.patch.object(lib, "_dir_file_stats", return_value=(0, 0)):
            ok, _msg, _stats = lib.migrate_dir_key(self.root, OLD_KEY, NEW_KEY, store=self.store)
        self.assertFalse(ok)
        self.assertEqual(self.files(OLD_KEY), {"a.tiff": b"OLD"})
        self.assertEqual(self.files(NEW_KEY), {"a.tiff": b"NEW"})


# ───────────────── ④ 真实形（用户那本书） ─────────────────
class RealShape(Base):
    """`3_Cropped_Tiff/9787550847224/`（3 TIFF + `_fields.json`）⇒ tab1 书名 ⇒ 自动迁移。"""

    def setUp(self) -> None:
        super().setUp()
        d = self.tiff_dir(OLD_KEY)
        d.mkdir(parents=True, exist_ok=True)
        for i, name in enumerate(("0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff",
                                  "0425_P371_C1_R1_长乐未央_汉_陈巨来.tiff",
                                  "0426_P372_C2_R1_吉祥如意_汉_NA.tiff"), start=1):
            (d / name).write_bytes(b"TIFF" + bytes([i]) * (100 * i))
        (d / "_fields.json").write_text(json.dumps({
            "pdf_name": PDF_NAME, "page": 370,
            "items": [{"页": 370, "列": 1, "行": 1, "释文": "中羞行府"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.pdf(PDF_NAME)

    def test_legacy_key_found_by_fields_json(self):
        self.assertEqual(lib.find_legacy_dir_key(self.root, self.pdf()), OLD_KEY)

    def test_full_flow_manual_name_migrates(self):
        pdf = self.pdf()
        key, src = lib.resolve_dir_key(pdf, book={"book_name": NEW_KEY})
        self.assertEqual((key, src), (NEW_KEY, "manual"))
        n_before, b_before = lib._dir_file_stats(self.tiff_dir(OLD_KEY))
        sha_before = self.sha(self.tiff_dir(OLD_KEY) / "_fields.json")

        ok, msg, stats = lib.migrate_dir_key(self.root, OLD_KEY, key, store=self.store)
        self.assertTrue(ok, msg)
        self.assertFalse(self.tiff_dir(OLD_KEY).exists())                   # 旧目录不存在
        d = self.tiff_dir(NEW_KEY)
        names = sorted(p.name for p in d.iterdir())
        self.assertEqual(len(names), 4)                                     # 3 TIFF + _fields.json
        self.assertIn("_fields.json", names)
        self.assertEqual(sum(1 for n in names if n.endswith(".tiff")), 3)
        n_after, b_after = lib._dir_file_stats(d)
        self.assertEqual((n_after, b_after), (n_before, b_before))           # 件数/字节一致
        self.assertEqual(self.sha(d / "_fields.json"), sha_before)           # 抽样 sha256 一致
        self.assertEqual(stats["files"], 4)

    def test_dir_key_not_from_legacy_config(self):
        """索引里的旧键**不得**再被当新键用（`resolve_dir_key` 与 `book_dir_keys.json` 脱钩）。"""
        cfg = WEBUI_DIR.parent / "config" / "book_dir_keys.json"
        self.assertTrue(cfg.is_file())
        key, src = lib.resolve_dir_key(self.pdf(), book={})
        self.assertEqual(src, "filename-fallback")
        self.assertNotEqual(key, OLD_KEY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
