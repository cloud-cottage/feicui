#!/usr/bin/env python
# local-dist/tests/test_meta_path.py
"""`local-dist/src/pdf_library.py` 的**侧车路径单一真源** ＋ 一次性迁移 ＋ 防回退闸门单测。

背景（P1 事故，2026-10-20）：侧车路径曾是
`Path(os.environ.get("FEICUI_DATA_DIR") or Path(__file__).resolve().parents[1]) / "var" / "pdf_meta.json"`
⇒ **源码态**读仓内 `local-dist/var/pdf_meta.json`，而打包态 / UI 写数据根
`~/Library/Application Support/斐萃/var/pdf_meta.json`：
用户填的朝代/作者在源码态读不到，切图仍出 `NA_NA`；且违反 `src/paths.py` 文件头的约定
（「所有平台派生只在本文件，其余模块一律调用 `data_dir()`」）。

本文件断言四件事（**零新依赖**：unittest ＋ 标准库）：
  1. `DEFAULT_META_PATH` ＝ `data_dir()/var/pdf_meta.json`（`FEICUI_DATA_DIR` 注入生效、空串按未设）；
  2. 三平台（darwin / win32 / linux）同一套派生（靠 `default_meta_path(platform=…)` 注入）；
  3. `migrate_legacy_meta()`：数据根优先、键并集、不覆盖已有、旧件改名 `.migrated`、**幂等**；
  4. **防回退闸门**：`local-dist/src/*.py`（`paths.py` 除外）不得再出现 `parents[1]` 当数据根
     —— 迁移用的旧落点那一行带 `# gate-allow: legacy-meta` 白名单注释。

跑法：
    ./venv/bin/python local-dist/tests/test_meta_path.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
SRC_DIR = WEBUI_DIR / "src"
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import paths  # noqa: E402
from src import pdf_library as lib  # noqa: E402

NAME = paths.APP_DIRNAME                                   # 斐萃
HOME = Path("/fake/home")
DATA_ENV = paths.DATA_ENV


def _env_with(value: str | None) -> dict:
    """`FEICUI_DATA_DIR` 设成 `value`（None ⇒ 删掉）后的**完整** environ（供注入/重载）。"""
    env = {k: v for k, v in os.environ.items() if k != DATA_ENV}
    if value is not None:
        env[DATA_ENV] = value
    return env


def _reload_with_env(value: str | None):
    """把 `FEICUI_DATA_DIR` 设成 `value`（None ⇒ 删掉）后重载模块 ⇒ module（环境已复原）。

    模块级常量在**重载那一刻**算好 ⇒ 断言直接用 `mod.DEFAULT_META_PATH`；
    需要按当前环境重新求值时用 `mod.default_meta_path(environ=_env_with(value))`。
    """
    with mock.patch.dict(os.environ, _env_with(value), clear=True):
        return importlib.reload(lib)


class MetaPathResolution(unittest.TestCase):
    """`DEFAULT_META_PATH` 必须落在**数据根**（不再是仓内 `local-dist/var/`）。"""

    def setUp(self):
        self._saved = {k: v for k, v in os.environ.items() if k == DATA_ENV}

    def tearDown(self):
        os.environ.pop(DATA_ENV, None)
        os.environ.update(self._saved)
        importlib.reload(lib)                              # 复原模块态（常量按真实环境重算）

    def test_env_override_points_into_injected_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload_with_env(tmp)
            self.assertEqual(mod.DEFAULT_META_PATH, Path(tmp) / "var" / "pdf_meta.json")
            self.assertEqual(mod.default_meta_path(environ=_env_with(tmp)).parent.parent, Path(tmp))
            # 读写都落在注入的数据根（源码态不再碰仓内 var/）
            with mock.patch.dict(os.environ, _env_with(tmp), clear=True):
                mod.save_meta({"schema": mod.META_SCHEMA, "books": {"a.pdf": {"dynasty": "秦"}}})
                self.assertEqual(mod.load_meta()["books"]["a.pdf"]["dynasty"], "秦")
            self.assertTrue((Path(tmp) / "var" / "pdf_meta.json").is_file())
            self.assertEqual(mod.load_meta()["books"]["a.pdf"]["dynasty"], "秦")

    def test_no_env_falls_back_to_data_dir(self):
        mod = _reload_with_env(None)
        want = paths.data_dir(environ=_env_with(None)) / "var" / "pdf_meta.json"
        self.assertEqual(mod.DEFAULT_META_PATH, want)
        # **防回退**：绝不能又落回仓内 `local-dist/var/`（P1 事故形态）
        self.assertNotIn(WEBUI_DIR, mod.DEFAULT_META_PATH.parents)
        self.assertNotEqual(mod.DEFAULT_META_PATH, WEBUI_DIR / "var" / "pdf_meta.json")

    def test_empty_env_is_treated_as_unset(self):
        mod = _reload_with_env("")
        self.assertEqual(mod.DEFAULT_META_PATH,
                         paths.data_dir(environ=_env_with("")) / "var" / "pdf_meta.json")

    def test_three_platforms_same_derivation(self):
        """darwin / win32 / linux 都只是 `data_dir()` 后的 `var/pdf_meta.json`（无平台分支）。"""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload_with_env(None)
            expect = {
                "darwin": HOME / "Library" / "Application Support" / NAME,
                "linux": HOME / ".local" / "share" / NAME,
                "win32": Path(tmp) / "Roaming" / NAME,
            }
            for plat, root in expect.items():
                env = {"APPDATA": str(Path(tmp) / "Roaming")} if plat == "win32" else {}
                with self.subTest(platform=plat):
                    got = mod.default_meta_path(platform=plat, environ=env, home=HOME)
                    self.assertEqual(got, paths.data_dir(platform=plat, environ=env, home=HOME)
                                     / "var" / "pdf_meta.json")
                    self.assertEqual(got, root / "var" / "pdf_meta.json")


class MigrateLegacyMeta(unittest.TestCase):
    """一次性迁移：数据根优先、键并集、不覆盖、留痕 `.migrated`、幂等。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.target = self.root / "data" / "var" / "pdf_meta.json"
        self.legacy = self.root / "repo" / "var" / "pdf_meta.json"
        self.target.parent.mkdir(parents=True)
        self.legacy.parent.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path: Path, books: dict):
        path.write_text(json.dumps({"schema": lib.META_SCHEMA, "books": books},
                                   ensure_ascii=False, indent=2), encoding="utf-8")

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_creates_when_data_root_has_no_meta(self):
        self._write(self.legacy, {"吴颐人篆刻作品展示.pdf": {"dynasty": "漢", "author": "吴颐人"}})
        out = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        self.assertEqual(out["action"], "created")
        self.assertTrue(out["changed"])
        self.assertEqual(self._read(self.target)["books"]["吴颐人篆刻作品展示.pdf"]["dynasty"], "漢")
        # 旧件**不删**，改名 `.migrated` 留痕
        self.assertFalse(self.legacy.exists())
        self.assertTrue(Path(out["archived"]).is_file())
        self.assertTrue(out["archived"].endswith("pdf_meta.json.migrated"))

    def test_never_overwrites_data_root_and_fills_missing_fields(self):
        self._write(self.target, {"秦印类编 检索版.pdf": {"dynasty": "秦", "author": "佚名", "notes": None}})
        self._write(self.legacy, {
            "秦印类编 检索版.pdf": {"dynasty": "漢", "author": "别人", "notes": "repo 备注"},
            "tmp.pdf": {"dynasty": "清", "page_count": 132},
        })
        before = self._read(self.target)["books"]["秦印类编 检索版.pdf"]
        out = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        books = self._read(self.target)["books"]
        self.assertEqual(out["action"], "merged")
        # 同键**数据根优先**（秦/佚名不被覆盖）
        self.assertEqual(books["秦印类编 检索版.pdf"]["dynasty"], "秦")
        self.assertEqual(books["秦印类编 检索版.pdf"]["author"], "佚名")
        # 数据根缺的字段由旧件补（notes 为 null ⇒ 补）
        self.assertEqual(books["秦印类编 检索版.pdf"]["notes"], "repo 备注")
        self.assertEqual(before["dynasty"], "秦")
        # 键并集：旧件独有的书加进来
        self.assertIn("tmp.pdf", books)
        self.assertIn("tmp.pdf", out["added_books"])
        self.assertTrue(Path(out["archived"]).is_file())

    def test_idempotent_second_run_is_noop(self):
        self._write(self.target, {"a.pdf": {"dynasty": "秦"}})
        self._write(self.legacy, {"b.pdf": {"dynasty": "漢"}})
        first = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        snapshot = self._read(self.target)
        mtime = self.target.stat().st_mtime_ns
        second = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        self.assertEqual(first["action"], "merged")
        self.assertEqual(second["action"], "noop")
        self.assertEqual(second["reason"], "no_legacy")
        self.assertFalse(second["changed"])
        self.assertEqual(self._read(self.target), snapshot)      # 0 变更
        self.assertEqual(self.target.stat().st_mtime_ns, mtime)  # 连写都没写

    def test_missing_or_empty_legacy_is_noop(self):
        out = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        self.assertEqual((out["action"], out["reason"]), ("noop", "no_legacy"))
        self.assertFalse(self.target.exists())
        self._write(self.legacy, {})
        out2 = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        self.assertEqual((out2["action"], out2["reason"]), ("noop", "legacy_empty"))
        self.assertTrue(self.legacy.exists())                    # 空件不归档、不动
        self.assertFalse(self.target.exists())

    def test_existing_archived_file_is_not_overwritten(self):
        self._write(self.legacy, {"b.pdf": {"dynasty": "漢"}})
        keep = self.legacy.with_name(self.legacy.name + ".migrated")
        keep.write_text('{"keep": true}', encoding="utf-8")
        out = lib.migrate_legacy_meta(target=self.target, legacy=self.legacy)
        self.assertEqual(json.loads(keep.read_text(encoding="utf-8")), {"keep": True})
        self.assertNotEqual(Path(out["archived"]), keep)
        self.assertTrue(Path(out["archived"]).is_file())


class NoParentsOneGate(unittest.TestCase):
    """**防回退闸门**：数据根（`var/` / 侧车）只许由 `src/paths.py` 派生。

    实现口径：AST 扫 `Subscript(... parents[1])`（**不含注释/docstring**），只看**数据根语境**的行
    （行内含 `var` / `pdf_meta` / `FEICUI_DATA_DIR` / `DATA_DIR`）。包内**资源**路径
    （例 `ocr_corrector.DEFAULT_MAP_PATH` 指向仓内 `data/guxi_variant_map.json`）不是数据根，不算违规。
    唯一白名单：`pdf_library._LEGACY_META_PATH`（迁移用的旧落点），行尾带 `# gate-allow: legacy-meta`。
    """

    ALLOW_COMMENT = "gate-allow: legacy-meta"
    #: 数据根语境（**引号包住 `var`** 才对：`guxi_variant_map.json` 里的 `var` 不算）
    DATA_ROOT_HINTS = ('"var"', "'var'", "pdf_meta", "FEICUI_DATA_DIR", "DATA_DIR")

    @staticmethod
    def _parents_index_nodes(tree) -> list:
        """所有 `...parents[1]` 这类下标节点（`ast` 层面，注释与字符串天然不参与）。"""
        import ast
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            val = node.value
            if not (isinstance(val, ast.Attribute) and val.attr == "parents"):
                continue
            idx = getattr(node.slice, "value", None)               # `parents[1]` ⇒ Constant(1)
            if idx == 1:
                out.append(node)
        return out

    def test_no_module_derives_data_root_from_parents(self):
        import ast
        offenders = []
        for py in sorted(SRC_DIR.glob("*.py")):
            if py.name == "paths.py":                        # 平台派生的唯一合法处
                continue
            text = py.read_text(encoding="utf-8")
            lines = text.splitlines()
            for node in self._parents_index_nodes(ast.parse(text)):
                line = lines[node.lineno - 1]
                if not any(h in line for h in self.DATA_ROOT_HINTS):
                    continue                                  # 资源路径，不是数据根
                if self.ALLOW_COMMENT in line:
                    continue
                offenders.append(f"{py.relative_to(WEBUI_DIR)}:{node.lineno}: {line.strip()}")
        self.assertEqual(offenders, [],
                         "数据根必须走 `paths.data_dir()`；以下行仍在用 parents[1] 拼数据根：\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main(verbosity=2)
