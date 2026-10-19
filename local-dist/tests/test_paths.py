#!/usr/bin/env python
# local-dist/tests/test_paths.py
"""`local-dist/src/paths.py`（用户目录单一真源）跨平台单测 —— **纯 stdlib**（unittest），不引新依赖。

跑法（任意平台都能跑，三平台路径靠注入断言）：
    ./venv/bin/python local-dist/tests/test_paths.py            # 直接跑（verbosity=2）
    ./venv/bin/python -m unittest discover -s local-dist/tests  # 或走 discover
CI 里也在 `windows-latest` 上**真跑一遍**（见 `.github/workflows/windows.yml`）：那台机上的
`test_real_platform_matches_os` 断言的是真 `sys.platform`，能验到「Windows 真机是不是 `%APPDATA%`」。

为什么不用 pytest：本仓 `local-dist` 的历史自检（`selftest.py` / `domtest*.py`）都是「直接 python 跑」
的脚本，CI 里不想为一个路径单测多装一个包。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEBUI_DIR = Path(__file__).resolve().parents[1]          # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import paths  # noqa: E402

NAME = paths.APP_DIRNAME                                   # 斐萃
HOME = Path("/fake/home")                                  # 仅用于 darwin/linux 断言（posix 拼接）


class DarwinDefaults(unittest.TestCase):
    def test_data_root(self):
        self.assertEqual(paths.data_dir(platform="darwin", environ={}, home=HOME),
                         HOME / "Library" / "Application Support" / NAME)

    def test_log_dir(self):
        self.assertEqual(paths.log_dir(platform="darwin", environ={}, home=HOME),
                         HOME / "Library" / "Logs" / NAME)

    def test_env_override_wins(self):
        env = {"FEICUI_DATA_DIR": "~/fd", "FEICUI_LOG_DIR": "/tmp/fl"}
        self.assertEqual(paths.data_dir(platform="darwin", environ=env, home=HOME),
                         Path("~/fd").expanduser())
        self.assertEqual(paths.log_dir(platform="darwin", environ=env, home=HOME), Path("/tmp/fl"))

    def test_monkeypatched_sys_platform_and_env(self):
        """**真 monkeypatch**：改 `sys.platform` ＋ 清空环境变量（模拟一台干净的 Mac）。"""
        with mock.patch.object(sys, "platform", "darwin"), \
             mock.patch.dict(os.environ, {}, clear=True):
            d, lg = paths.user_dirs(home=HOME)
        self.assertEqual(d, HOME / "Library" / "Application Support" / NAME)
        self.assertEqual(lg, HOME / "Library" / "Logs" / NAME)


class WindowsDefaults(unittest.TestCase):
    ENV = {"APPDATA": "C:/Users/u/AppData/Roaming",
           "LOCALAPPDATA": "C:/Users/u/AppData/Local"}

    def test_data_root_is_roaming_appdata(self):
        self.assertEqual(paths.data_dir(platform="win32", environ=self.ENV, home=HOME),
                         Path("C:/Users/u/AppData/Roaming") / NAME)

    def test_log_dir_is_localappdata_logs(self):
        self.assertEqual(paths.log_dir(platform="win32", environ=self.ENV, home=HOME),
                         Path("C:/Users/u/AppData/Local") / NAME / "logs")

    def test_fallback_when_win_env_missing(self):
        """`%APPDATA%` / `%LOCALAPPDATA%` 缺失（服务账号 / 精简环境）⇒ 退回 `<home>/AppData/...`。"""
        self.assertEqual(paths.data_dir(platform="win32", environ={}, home=HOME),
                         HOME / "AppData" / "Roaming" / NAME)
        self.assertEqual(paths.log_dir(platform="win32", environ={}, home=HOME),
                         HOME / "AppData" / "Local" / NAME / "logs")

    def test_data_and_log_are_not_the_same_tree(self):
        d, lg = paths.user_dirs(platform="win32", environ=self.ENV, home=HOME)
        self.assertNotEqual(str(d).split(NAME)[0], str(lg).split(NAME)[0])

    def test_monkeypatched_sys_platform_and_env(self):
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.dict(os.environ, self.ENV, clear=True):
            d, lg = paths.user_dirs(home=HOME)
        self.assertEqual(d, Path("C:/Users/u/AppData/Roaming") / NAME)
        self.assertEqual(lg, Path("C:/Users/u/AppData/Local") / NAME / "logs")


class LinuxDefaults(unittest.TestCase):
    def test_xdg_defaults(self):
        self.assertEqual(paths.data_dir(platform="linux", environ={}, home=HOME),
                         HOME / ".local" / "share" / NAME)
        self.assertEqual(paths.log_dir(platform="linux", environ={}, home=HOME),
                         HOME / ".local" / "state" / NAME / "logs")

    def test_xdg_overrides(self):
        env = {"XDG_DATA_HOME": "/xdg/data", "XDG_STATE_HOME": "/xdg/state"}
        self.assertEqual(paths.data_dir(platform="linux", environ=env, home=HOME),
                         Path("/xdg/data") / NAME)
        self.assertEqual(paths.log_dir(platform="linux", environ=env, home=HOME),
                         Path("/xdg/state") / NAME / "logs")


class EnvPrecedence(unittest.TestCase):
    def test_blank_env_is_treated_as_unset(self):
        """`FEICUI_DATA_DIR=` （空串）**不能**把根目录变成 `Path('')` —— 三平台一致。"""
        blank = {"FEICUI_DATA_DIR": "", "FEICUI_LOG_DIR": "   ",
                 "APPDATA": "C:/R", "LOCALAPPDATA": "C:/L"}
        for plat, expect_data in (
            ("darwin", HOME / "Library" / "Application Support" / NAME),
            ("win32", Path("C:/R") / NAME),
            ("linux", HOME / ".local" / "share" / NAME),
        ):
            self.assertEqual(paths.data_dir(platform=plat, environ=blank, home=HOME), expect_data)

    def test_override_on_every_platform(self):
        env = {"FEICUI_DATA_DIR": "/data/feicui", "FEICUI_LOG_DIR": "/data/feicui-logs",
               "APPDATA": "C:/R", "LOCALAPPDATA": "C:/L"}
        for plat in ("darwin", "win32", "linux"):
            self.assertEqual(paths.data_dir(platform=plat, environ=env, home=HOME), Path("/data/feicui"))
            self.assertEqual(paths.log_dir(platform=plat, environ=env, home=HOME), Path("/data/feicui-logs"))

    def test_describe_marks_source(self):
        info = paths.describe(platform="win32", environ={"APPDATA": "C:/R"}, home=HOME)
        self.assertEqual(info["platform"], "windows")
        self.assertEqual(info["data_source"], "platform-default")
        info2 = paths.describe(platform="win32", environ={"FEICUI_DATA_DIR": "/d"}, home=HOME)
        self.assertEqual(info2["data_source"], "env:FEICUI_DATA_DIR")


class DerivedPaths(unittest.TestCase):
    def test_children_come_from_data_root(self):
        root = Path("/tmp/feicui-root")
        self.assertEqual(paths.var_dir(root), root / "var")
        self.assertEqual(paths.jobs_dir(root), root / "var" / "jobs")
        self.assertEqual(paths.env_file(root), root / ".env")
        self.assertEqual(paths.session_file(root), root / ".session.json")

    def test_children_follow_env_root(self):
        with mock.patch.dict(os.environ, {"FEICUI_DATA_DIR": "/tmp/feicui-env"}, clear=False):
            self.assertEqual(paths.jobs_dir(), Path("/tmp/feicui-env") / "var" / "jobs")

    def test_ensure_dirs_creates_four_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, lg = paths.ensure_dirs(Path(tmp) / "data", Path(tmp) / "logs")
            for p in (d, d / "var", d / "var" / "jobs", lg):
                self.assertTrue(p.is_dir(), f"未创建：{p}")

    def test_real_platform_matches_os(self):
        """真机自洽：不带注入时，`data_dir()` 必须落在本平台的默认位置（CI 上就是真 Windows 断言）。"""
        d, lg = paths.user_dirs(environ={})       # 清空环境变量，只看平台派生
        tag = paths.platform_tag()
        if sys.platform == "darwin":
            self.assertEqual(d, Path.home() / "Library" / "Application Support" / NAME)
            self.assertEqual(tag, "macos")
        elif sys.platform == "win32":
            self.assertEqual(d, Path(os.environ["APPDATA"]) / NAME)
            self.assertEqual(lg, Path(os.environ["LOCALAPPDATA"]) / NAME / "logs")
            self.assertEqual(tag, "windows")
        else:
            self.assertEqual(tag, "linux")


class NoScatteredHardcodes(unittest.TestCase):
    """**防回退**：除了 `paths.py`，`local-dist/**.py`（不含产物/构建缓存/文档）不得再写死
    macOS 用户目录字面量 —— 否则 Windows 上又会冒出 `...\\Library\\Application Support\\斐萃`。"""

    #: 只看**代码里的字符串字面量**（`Path.home() / "Library" / "Application Support"` 这种拼接）；
    #: 文档/注释里写 `~/Library/...` 说明口径是**允许**的（它们不是可执行路径来源）。
    PATTERNS = ('"Library"', "'Library'", '"Application Support"', "'Application Support'")

    def test_no_macos_literals_outside_paths(self):
        offenders = []
        self_paths = Path(paths.__file__).resolve()
        for p in sorted(WEBUI_DIR.rglob("*.py")):
            rel = p.relative_to(WEBUI_DIR).as_posix()      # as_posix：Windows 上是 `\` ⇒ 前缀判断会失效
            if rel.startswith(("build/dist/", "build/build/", "build/.venv-build/", "tests/")):
                continue
            if "__pycache__" in rel:
                continue
            if p.resolve() == self_paths:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue                     # 注释里提 macOS 路径是允许的（口径说明）
                for pat in self.PATTERNS:
                    if pat in line:
                        offenders.append(f"{rel}:{line_no}: {line.strip()[:100]}")
                        break
        self.assertEqual(offenders, [], "检测到散落的 macOS 路径拼接：\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main(verbosity=2)
