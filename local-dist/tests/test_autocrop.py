#!/usr/bin/env python
# local-dist/tests/test_autocrop.py
"""tab2 **一键全自动**（`src/autocrop.py`）单测 —— 零新依赖（unittest ＋ PyMuPDF ＋ 既有 cv2）。

被测契约（`src/autocrop.run_autocrop`）：

1. **全量跑完**：3 页合成 PDF（红块 1/2/1 枚）⇒ `pages_done=3`、`seals_total=4`、
   产物逐件落 `<根>/3_Cropped_Tiff/<目录键>/`、进度文件 schema 正确；
2. **断点续跑**：删掉第 3 页产物（**保留进度**）⇒ `resume=True` 只补第 3 页
   （`pages_skipped=2 / pages_done=1`），前两页不重写（mtime 不变）；
3. **取消**：第 1 页裁完后置取消 flag ⇒ `cancelled=True`、第 1 页产物在、第 2/3 页没裁、
   进度里 `cropped` 只有第 1 页（⇒ 可续跑）；
4. **失败容忍**：第 2 页渲页抛异常（monkeypatch）⇒ `pages_failed=1`、第 1/3 页照常完成、
   `failed_pages` 指明第 2 页、进度 `failed["2"]` 有原因 —— **整批不中断**；
5. **进度原子性**：写完后磁盘上只有 `.autocrop_progress.json`（**没有 `.part` 残件**），
   JSON 可解析、`schema=feicui.autocrop.v1`、`cropped` 升序、`pdf_mtime` 与 PDF 实际 mtime 一致；
6. 参数非法 ⇒ `{ok:false, reason:'BAD_PARAM'}`（**不抛**）。

跑法：
    ./venv/bin/python local-dist/tests/test_autocrop.py
    ./venv/bin/python -m unittest discover -s local-dist/tests
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]           # local-dist/
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from src import autocrop as ac  # noqa: E402

SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-autocrop-"))
PAGES = {1: 1, 2: 2, 3: 1}                                # 页号 ⇒ 红块枚数（合计 4）
#: 测试用 300dpi 裁切（默认 1200 太慢/太吃内存；逻辑同一路径，只差 scale）
TEST_DPI = 300


def build_pdf(path: Path) -> None:
    """合成 3 页 PDF：白底 + 红块（1/2/1 枚）——检测算法真能吃到的「印章」。"""
    import pymupdf
    doc = pymupdf.open()
    for page_no, n_blocks in PAGES.items():
        pg = doc.new_page(width=300.0, height=400.0)
        pg.insert_text((30, 40), f"PAGE {page_no}", fontsize=14)
        for i in range(n_blocks):
            x = 40.0 + i * 130.0
            y = 90.0 + i * 20.0
            pg.draw_rect(pymupdf.Rect(x, y, x + 70.0, y + 70.0),
                         color=(1, 0, 0), fill=(1, 0, 0), width=0.5)
    doc.save(str(path))
    doc.close()


class AutoCrop(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pdf_dir = SCRATCH / "1_Original_PDF"
        cls.pdf_dir.mkdir(parents=True, exist_ok=True)
        cls.pdf = cls.pdf_dir / "合成书.pdf"
        build_pdf(cls.pdf)

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="root-"))
        (self.root / "3_Cropped_Tiff").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # ── 助手 ─────────────────────────────────────────────────────
    def _run(self, **kw):
        kw.setdefault("dpi", TEST_DPI)
        return ac.run_autocrop(self.pdf, self.root, **kw)

    def _dir(self, r=None) -> Path:
        r = r or {}
        dk = r.get("dir_key") or "合成书"
        return self.root / "3_Cropped_Tiff" / dk

    def _tiffs(self, page: int | None = None) -> list[str]:
        d = self._dir()
        if not d.is_dir():
            return []
        names = sorted(p.name for p in d.glob("*.tiff"))
        if page is None:
            return names
        return [n for n in names if n.startswith(f"P{page}-") or n.startswith(f"P{page}_")]

    def _prog(self) -> dict:
        d = self._dir()
        f = d / ac.PROGRESS_NAME
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}

    # ── ① 全量 ───────────────────────────────────────────────────
    def test_full_run(self) -> None:
        r = self._run()
        self.assertTrue(r.get("ok"), r)
        self.assertFalse(r.get("cancelled"))
        self.assertEqual(r["pages_total"], 3)
        self.assertEqual(r["pages_done"], 3, r)
        self.assertEqual(r["pages_skipped"], 0)
        self.assertEqual(r["pages_failed"], 0)
        self.assertEqual(r["seals_total"], 4, r)
        self.assertEqual(r["dir_key"], "合成书")
        self.assertEqual(r["dir_key_source"], "filename-fallback")
        for page, n in PAGES.items():
            self.assertEqual(len(self._tiffs(page)), n, f"第 {page} 页：{self._tiffs()}")
        self.assertTrue(any(p.name.endswith(".tiff") for p in self._dir().iterdir()))

    # ── ② 断点续跑 ───────────────────────────────────────────────
    def test_resume_only_redoes_missing_page(self) -> None:
        r1 = self._run()
        self.assertEqual(r1["pages_done"], 3, r1)
        keep = {p.name: p.stat().st_mtime_ns for p in self._dir().glob("*.tiff")}
        for f in list(self._dir().glob("P3*")):
            f.unlink()
        self.assertTrue(self._prog().get("cropped"), "进度必须落盘")
        r2 = self._run(resume=True)
        self.assertTrue(r2.get("ok"), r2)
        self.assertEqual(r2["pages_skipped"], 2, r2)
        self.assertEqual(r2["pages_done"], 1, r2)
        self.assertEqual(len(self._tiffs(3)), 1, "只补第 3 页")
        after = {p.name: p.stat().st_mtime_ns for p in self._dir().glob("*.tiff")}
        for name, mt in keep.items():                       # 前两页**没被重写**
            if name.startswith("P1") or name.startswith("P2"):
                self.assertEqual(after.get(name), mt, name)
        self.assertEqual(sorted(self._prog()["cropped"]), [1, 2, 3])

    def test_resume_false_reruns_everything(self) -> None:
        self._run()
        r2 = self._run(resume=False)
        self.assertEqual(r2["pages_skipped"], 0, r2)
        self.assertEqual(r2["pages_done"], 3, r2)

    # ── ③ 取消 ───────────────────────────────────────────────────
    def test_cancel_after_first_page_keeps_products(self) -> None:
        state = {"cancel": False}

        def cb(rec):                                        # 第 1 页收工 ⇒ 置取消
            if rec.get("stage") == "done" and rec.get("page") == 1:
                state["cancel"] = True

        r = self._run(progress_cb=cb, cancel_flag=lambda: state["cancel"])
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(r.get("cancelled"), r)
        self.assertEqual(r["pages_done"], 1, r)
        self.assertEqual(len(self._tiffs(1)), 1, "第 1 页产物必须保留")
        self.assertEqual(self._tiffs(2), [])
        self.assertEqual(self._tiffs(3), [])
        self.assertEqual(self._prog()["cropped"], [1], "取消也必须落盘")
        # 取消后能续跑完
        r2 = self._run(resume=True)
        self.assertFalse(r2.get("cancelled"))
        self.assertEqual(r2["pages_skipped"], 1, r2)
        self.assertEqual(r2["pages_done"], 2, r2)

    # ── ④ 失败容忍 ───────────────────────────────────────────────
    def test_single_page_failure_does_not_stop_batch(self) -> None:
        real = ac.sd.render_page

        def flaky(pdf, page, dpi=ac.DETECT_DPI):
            if int(page) == 2:
                raise RuntimeError("合成故障：第 2 页渲染失败")
            return real(pdf, page, dpi)

        ac.sd.render_page = flaky
        try:
            r = self._run()
        finally:
            ac.sd.render_page = real
        self.assertTrue(r.get("ok"), r)
        self.assertFalse(r.get("cancelled"))
        self.assertEqual(r["pages_failed"], 1, r)
        self.assertEqual(r["pages_done"], 2, r)
        self.assertEqual([f["page"] for f in r["failed_pages"]], [2], r)
        self.assertIn("合成故障", r["failed_pages"][0]["reason"])
        self.assertEqual(len(self._tiffs(1)), 1)
        self.assertEqual(len(self._tiffs(3)), 1, "第 3 页必须照跑（不许中断）")
        prog = self._prog()
        self.assertIn("2", prog["failed"])
        self.assertEqual(sorted(prog["cropped"]), [1, 3])

    # ── ⑤ 进度文件：原子性 + schema ──────────────────────────────
    def test_progress_atomic_and_schema(self) -> None:
        r = self._run()
        d = self._dir(r)
        self.assertEqual([p.name for p in d.glob("*.part")], [], "不得留 .part 残件")
        f = d / ac.PROGRESS_NAME
        prog = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(prog["schema"], "feicui.autocrop.v1")
        self.assertEqual(prog["schema"], ac.SCHEMA)
        self.assertEqual(prog["cropped"], sorted(prog["cropped"]))
        self.assertEqual(prog["cropped"], [1, 2, 3])
        self.assertEqual(prog["detected"], [1, 2, 3])
        self.assertEqual(prog["failed"], {})
        self.assertEqual(prog["pages_total"], 3)
        self.assertAlmostEqual(float(prog["pdf_mtime"]), round(self.pdf.stat().st_mtime, 3), places=3)
        self.assertEqual(Path(prog["pdf"]), self.pdf)
        for k in ("started_at", "updated_at", "elapsed_s"):
            self.assertIn(k, prog)
        # 进度文件自己也是原子写（直调 save_progress）：写完即完整可解析
        tmp = d / "probe.json"
        self.assertTrue(ac.save_progress(tmp, {"cropped": [2, 1]}))
        self.assertFalse((d / "probe.json.part").exists())
        self.assertEqual(json.loads(tmp.read_text(encoding="utf-8"))["schema"], ac.SCHEMA)

    def test_pdf_mtime_change_archives_old_progress(self) -> None:
        r1 = self._run()
        self.assertEqual(r1["pages_done"], 3, r1)
        prog_f = self._dir() / ac.PROGRESS_NAME
        self.assertTrue(prog_f.is_file())
        self.pdf.touch()                                     # 改 mtime ＝ 换了 PDF
        r2 = self._run(resume=True)
        self.assertEqual(r2["pages_skipped"], 0, "新任务不得跳过旧进度")
        self.assertEqual(r2["pages_done"], 3, r2)
        self.assertTrue((self._dir() / (ac.PROGRESS_NAME + ".bak")).is_file(), "旧进度应归档 .bak")

    # ── ⑥ 参数非法 ───────────────────────────────────────────────
    def test_bad_params_structured_never_raise(self) -> None:
        r = ac.run_autocrop(self.pdf_dir / "不存在.pdf", self.root)
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("reason"), "BAD_PARAM")
        r = self._run(page_from=3, page_to=1)
        self.assertEqual(r.get("reason"), "BAD_PARAM", r)
        r = self._run(dpi=137)
        self.assertEqual(r.get("reason"), "BAD_PARAM", r)
        r = self._run(page_from=9)
        self.assertEqual(r.get("reason"), "BAD_PARAM", r)


def tearDownModule() -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
