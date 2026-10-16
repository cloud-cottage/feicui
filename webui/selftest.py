#!/usr/bin/env python
# webui/selftest.py
"""「斐萃」本地电脑版 · **逻辑/API 层直测**（不依赖 GUI —— 主要验收面）。

做什么：
  ① 在 **scratch 临时目录**造一份 `feicui/` 夹具（三个标准子目录 ＋ 一份真 PDF 拷贝）；
  ② 直接 import `api.FeicuiApi` / `src/*.py` 逐方法调用：目录校验 / tab1 列 PDF ＋ 元数据读写 /
     tab2 产物列表 ＋ 生成入口参数面与预检 / tab3 子目录 ＋ tiff 列表 ＋ 测试 tiff；
  ③ **端到端**：用真引擎跑**一页** 1200dpi（≈10–70 s，随源页像素而定），断言产物落
     `<夹具>/2_HighRes_PDF/<目录键>/P<页>-1200dpi-48bit.tif` ＋ TIFF 魔数 ＋ 进度推送发生；
  ④ `--with-gui` 时另起 `app.py --test-exit-after N` 试窗口（**只报「已启动/异常退出」**，
     不断言「渲染正确」——无头环境看不见画面）；
  ⑤ 全部读数写 `webui/build/readings-webui.json`。

跑法：
    ./venv/bin/python webui/selftest.py                 # 逻辑面 ＋ 一页端到端
    ./venv/bin/python webui/selftest.py --no-e2e        # 跳过真渲染（秒回）
    ./venv/bin/python webui/selftest.py --with-gui      # 另加短超时窗口试起

注意：脚本会临时改写 `webui/.env` 的 `FEICUI_ROOT` 与 `webui/.session.json` 做夹具验证，
       **结束时原样还原**（两个文件本就不入库）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI_DIR))

from api import APP_VERSION, ENGINE_SCRIPT, VENV_PYTHON, FeicuiApi  # noqa: E402
from src import pdf_library as lib  # noqa: E402
from src import validator  # noqa: E402

REPO_ROOT = WEBUI_DIR.parent
#: tab1/tab2 预检用的小样本（2 MB）
SOURCE_PDF = REPO_ROOT / "output" / "1_Original_PDF" / "吴颐人篆刻作品展示.pdf"
#: 端到端渲染样本：内嵌图 ≈300 dpi（1200 = 300×4，满足引擎「整数倍上采样」硬断言），单页 ≈65 s
E2E_PDF = REPO_ROOT / "output" / "1_Original_PDF" / "tmp.pdf"
READINGS = WEBUI_DIR / "build" / "readings-webui.json"

ROWS: list[dict] = []


def record(name: str, status: str, detail: str = "", extra: dict | None = None) -> None:
    ROWS.append({"check": name, "status": status, "detail": detail, **(extra or {})})
    mark = {"PASS": "✅", "FAIL": "❌", "NOT_MEASURED": "⚠️"}.get(status, "?")
    print(f"{mark} {name}: {detail}", flush=True)


def expect(name: str, cond: bool, detail: str = "") -> bool:
    record(name, "PASS" if cond else "FAIL", detail)
    return bool(cond)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-e2e", action="store_true", help="跳过一页真渲染")
    ap.add_argument("--with-gui", action="store_true", help="另加短超时窗口试起")
    ap.add_argument("--gui-seconds", type=float, default=12.0)
    ap.add_argument("--e2e-timeout", type=float, default=420.0)
    args = ap.parse_args(argv)

    started = time.time()
    env_backup = {p: (p.read_text(encoding="utf-8") if p.exists() else None)
                  for p in (WEBUI_DIR / ".env", WEBUI_DIR / ".session.json")}
    scratch = Path(tempfile.mkdtemp(prefix="feicui-selftest-"))
    root = scratch / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (scratch / "not_feicui").mkdir(exist_ok=True)
    sample = root / lib.ORIGINAL_DIR / SOURCE_PDF.name
    shutil.copy2(SOURCE_PDF, sample)
    e2e_pdf = root / lib.ORIGINAL_DIR / E2E_PDF.name
    shutil.copy2(E2E_PDF, e2e_pdf)
    record("fixture", "PASS",
           f"夹具 {root}（含 2 份真 PDF：{sample.name} {sample.stat().st_size} B / "
           f"{e2e_pdf.name} {e2e_pdf.stat().st_size} B）")

    api = FeicuiApi()
    progress_events: list[dict] = []
    api.jobs.attach_pusher(lambda snap: progress_events.append(snap))

    try:
        # ── ① 目录校验（复用 src/pdf_library.verify_feicui_dir）──
        ok, msg = lib.verify_feicui_dir(scratch / "not_feicui")
        expect("dir/verify_reject_wrong_name", (not ok) and "feicui" in msg, msg)
        ok, msg = lib.verify_feicui_dir(root)
        expect("dir/verify_accept_fixture", ok, msg)
        r = api.verify_dir({"path": str(root)})
        expect("api/verify_dir", bool(r.get("ok")), str(r.get("msg")))
        expect("api/root_bound_to_fixture", api._root == str(root.resolve()),
               f"_root={api._root}")
        r = api.verify_dir({"path": str(scratch / "nope")})
        expect("api/verify_dir_missing", not r.get("ok"), str(r.get("msg")))

        # ── ② tab1：列 PDF / 探针 / 元数据读写 ──
        t1 = api.tab1_list({})
        expect("tab1/list_ok", bool(t1.get("ok")), f"rows={len(t1.get('rows', []))}")
        rows = t1.get("rows", [])
        expect("tab1/row_count", len(rows) == 2, f"count={len(rows)}")
        rec0 = (t1.get("items") or [{}])[0]
        expect("tab1/probe_pages", bool(rec0.get("page_count")),
               f"page_count={rec0.get('page_count')} page_mm=? scan_dpi={rec0.get('scan_dpi')}")
        expect("tab1/dynasty_options", len(t1.get("dynasty_options", [])) == 15,
               f"n={len(t1.get('dynasty_options', []))}")
        bad = api.tab1_save_meta({"filename": sample.name, "dynasty": "不是朝代"})
        expect("tab1/reject_bad_dynasty", not bad.get("ok"), str(bad.get("msg")))
        good = api.tab1_save_meta({"filename": sample.name, "dynasty": "漢",
                                   "author": "吴颐人", "notes": "selftest"})
        expect("tab1/save_meta", bool(good.get("ok")), str(good.get("msg")))
        t1b = api.tab1_list({})
        it = next((x for x in (t1b.get("items") or []) if x.get("filename") == sample.name), {})
        expect("tab1/meta_persisted",
               it.get("dynasty") == "漢" and it.get("author") == "吴颐人",
               f"dynasty={it.get('dynasty')} author={it.get('author')}")

        # ── ③ tab3：子目录 / tiff 列表 / 测试件 ──
        (root / lib.TIFF_DIR / "测试子目录").mkdir(parents=True, exist_ok=True)
        gen = api.tab3_generate_test({"subdir": "测试子目录"})
        expect("tab3/generate_test_tiff", bool(gen.get("ok")), str(gen.get("msg")))
        t3 = api.tab3_list({"subdir": "测试子目录"})
        expect("tab3/list_ok", bool(t3.get("ok")),
               f"subdirs={t3.get('subdirs')} files={len(t3.get('files', []))}")
        f0 = (t3.get("files") or [{}])[0]
        expect("tab3/filename_template",
               bool(f0) and validator.is_standard_tiff(f0.get("name", "")),
               f"name={f0.get('name')} standard={f0.get('standard')}")
        bad3 = api.tab3_list({"subdir": "不存在的子目录"})
        expect("tab3/unknown_subdir_fallback", bool(bad3.get("ok")) and bad3.get("current") == "测试子目录",
               f"current={bad3.get('current')}")

        # ── ④ tab2：产物列表 ＋ 生成入口（参数面 / 预检 / 引擎命令行）──
        t2 = api.tab2_list({})
        expect("tab2/list_ok", bool(t2.get("ok")),
               f"sources={len(t2.get('sources', []))} dirs={len(t2.get('dirs', []))}")
        src = (t2.get("sources") or [{}])[0]
        expect("tab2/dir_key_resolved", bool(src.get("dir_key")),
               f"dir_key={src.get('dir_key')}（复用 server/app/naming.py）")
        e2e_row = next((s for s in (t2.get("sources") or []) if s.get("filename") == E2E_PDF.name), {})
        expect("tab2/e2e_source_present", bool(e2e_row),
               f"{E2E_PDF.name} dir_key={e2e_row.get('dir_key')}")
        miss = api.tab2_generate({"filename": "不存在.pdf", "page": 1, "dpi": 1200})
        expect("tab2/reject_missing_pdf", not miss.get("ok"), str(miss.get("msg")))
        badd = api.tab2_generate({"filename": sample.name, "page": 1, "dpi": 999})
        expect("tab2/reject_bad_dpi", not badd.get("ok"), str(badd.get("msg")))
        badp = api.tab2_generate({"filename": sample.name, "page": 0, "dpi": 1200})
        expect("tab2/reject_bad_page", not badp.get("ok"), str(badp.get("msg")))
        engine_missing = not ENGINE_SCRIPT.exists()
        record("tab2/engine_script_present", "PASS" if not engine_missing else "FAIL",
               f"{ENGINE_SCRIPT} exists={not engine_missing}")

        dir_key = src.get("dir_key") or sample.stem
        sample_row = next((s for s in (t2.get("sources") or []) if s.get("filename") == sample.name), {})
        sample_dir_key = sample_row.get("dir_key") or sample.stem
        out_path = root / lib.HIGHRES_DIR / sample_dir_key / "P1-1200dpi-48bit.tif"
        cmd = api.jobs.engine_cmd(sample, 1, 1200, out_path,
                                  scratch / "p.jsonl", out_path.parent / "readings.json")
        joined = " ".join(cmd)
        expect("tab2/engine_cmd_shape",
               cmd[0].endswith("python") and str(ENGINE_SCRIPT) in joined
               and "--dpi 1200" in joined and "--page 1" in joined
               and f"--out {out_path}" in joined,
               f"argv[0]={cmd[0]} len={len(cmd)}")
        expect("tab2/engine_cmd_python_exists", Path(cmd[0]).exists(), cmd[0])

        # 预检 A：扫描 dpi 非整数倍 ⇒ 提前拒绝（引擎硬断言；避免白跑 ≈80 s）
        nm = api.tab2_generate({"filename": sample.name, "page": 1, "dpi": 1200})
        expect("tab2/precheck_dpi_multiple",
               (not nm.get("ok")) and bool(nm.get("retryable_with_force")),
               f"scan_dpi={nm.get('scan_dpi')} msg={(nm.get('msg') or '')[:90]}")
        # 预检 B：产物已存在 ⇒ 拒绝覆盖（除非 overwrite）
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"placeholder")
        dup = api.tab2_generate({"filename": sample.name, "page": 1, "dpi": 1200, "force": True})
        expect("tab2/reject_existing_output",
               (not dup.get("ok")) and bool(dup.get("exists")), str(dup.get("msg")))
        out_path.unlink()
        # 预检 C：force 绕过 dpi 预检 ⇒ 真起引擎并让其自行失败（证明 bypass 生效）
        fj = api.tab2_generate({"filename": sample.name, "page": 1, "dpi": 1200, "force": True})
        jid = (fj.get("job") or {}).get("job_id")
        expect("tab2/force_bypasses_precheck", bool(fj.get("ok")) and bool(jid),
               str(fj.get("msg")))
        t_f = time.time()
        fstate = {}
        while jid and time.time() - t_f < 60:
            fstate = (api.tab2_job({"job_id": jid}).get("job") or {})
            if fstate.get("state") in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)
        record("tab2/force_then_engine_asserts",
               "PASS" if fstate.get("state") == "error" else "FAIL",
               f"state={fstate.get('state')} err={fstate.get('error')}"
               f"（引擎对非整数倍 dpi 的硬断言，与预检一致）")

        # ── ⑤ 端到端：真引擎跑一页 1200dpi（异步 + 进度）──
        e2e_dir_key = e2e_row.get("dir_key") or "tmp"
        e2e_out = root / lib.HIGHRES_DIR / e2e_dir_key / "P1-1200dpi-48bit.tif"
        if args.no_e2e:
            record("e2e/render_one_page_1200dpi", "NOT_MEASURED", "--no-e2e 跳过")
        else:
            t0 = time.time()
            gen = api.tab2_generate({"filename": E2E_PDF.name, "page": 1, "dpi": 1200})
            job_id = (gen.get("job") or {}).get("job_id")
            expect("e2e/submit_job", bool(gen.get("ok")) and bool(job_id), str(gen.get("msg")))
            final = {}
            while job_id and time.time() - t0 < args.e2e_timeout:
                st = api.tab2_job({"job_id": job_id})
                final = st.get("job") or {}
                if final.get("state") in ("done", "error", "cancelled"):
                    break
                time.sleep(1.0)
            secs = round(time.time() - t0, 1)
            if final.get("state") == "done":
                size_mb = round(e2e_out.stat().st_size / 1024 / 1024, 1) if e2e_out.exists() else 0
                magic = e2e_out.read_bytes()[:4] if e2e_out.exists() else b""
                record("e2e/render_one_page_1200dpi", "PASS",
                       f"{secs}s state=done out={e2e_out.name} size={size_mb} MB",
                       {"seconds": secs, "out": str(e2e_out), "size_mb": size_mb,
                        "progress_pushes": len(progress_events),
                        "max_percent": max([p.get("percent", 0) for p in progress_events] or [0]),
                        "log_tail": (final.get("log_tail") or "")[-400:]})
                expect("e2e/tiff_magic", magic in (b"II*\x00", b"MM\x00*"), f"magic={magic!r}")
                expect("e2e/progress_pushed", len(progress_events) > 0,
                       f"pushes={len(progress_events)}（native 下同一路径＝window.evaluate_js）")
            else:
                record("e2e/render_one_page_1200dpi", "FAIL",
                       f"{secs}s state={final.get('state')} err={final.get('error')}",
                       {"seconds": secs, "log_tail": (final.get("log_tail") or "")[-800:]})

        # ── ⑥ 取消路径（不依赖渲染时长：起一个再立刻取消）──
        if not args.no_e2e:
            cancel_out = root / lib.HIGHRES_DIR / e2e_dir_key / "P2-1200dpi-48bit.tif"
            cj = api.tab2_generate({"filename": E2E_PDF.name, "page": 2, "dpi": 1200}).get("job") or {}
            time.sleep(1.5)
            cres = api.tab2_cancel({"job_id": cj.get("job_id", "")})
            expect("tab2/cancel_requested", bool(cres.get("ok")), str(cres.get("msg")))
            t1_ = time.time()
            st: dict = {}
            while time.time() - t1_ < 60:
                st = (api.tab2_job({"job_id": cj.get("job_id", "")}).get("job") or {})
                if st.get("state") in ("cancelled", "error", "done"):
                    break
                time.sleep(1.0)
            record("tab2/cancel_effect", "PASS" if st.get("state") == "cancelled" else "FAIL",
                   f"state={st.get('state')} rc={st.get('returncode')} "
                   f"out_exists={cancel_out.exists()}")

        # ── ⑦ 未选目录时的护栏 ──
        api2 = FeicuiApi()
        guard = api2.tab1_list({})
        expect("guard/no_root_blocks_tab1",
               (not guard.get("ok")) and bool(guard.get("need_dir")), str(guard.get("msg")))

        # ── ⑧ GUI 短超时试起（只报「已启动/异常退出」）──
        if args.with_gui:
            cmd = [str(VENV_PYTHON), str(WEBUI_DIR / "app.py"),
                   "--test-exit-after", str(args.gui_seconds)]
            t0 = time.time()
            try:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=args.gui_seconds + 40)
                rc, out, err = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as exc:
                rc, out, err = "TIMEOUT", exc.stdout or "", exc.stderr or ""
            secs = round(time.time() - t0, 1)
            launched = ("WEBUI_START" in (out or ""))
            status = "PASS" if (launched and rc == 0) else ("FAIL" if launched else "FAIL")
            record("gui/window_launch", status,
                   f"rc={rc} {secs}s（**只证「已启动并可关窗」，不证画面渲染**）",
                   {"rc": rc, "seconds": secs, "stdout": (out or "")[-600:],
                    "stderr": (err or "")[-900:]})
        else:
            record("gui/window_launch", "NOT_MEASURED", "未加 --with-gui（无头/无人看画面）")

    finally:
        for p, content in env_backup.items():
            try:
                if content is None:
                    if p.exists():
                        p.unlink()
                else:
                    p.write_text(content, encoding="utf-8")
            except Exception:
                pass
        shutil.rmtree(scratch, ignore_errors=True)

    summary = {
        "schema": "feicui.webui.selftest.v1",
        "app_version": APP_VERSION,
        "at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.executable,
        "engine_python": str(VENV_PYTHON),
        "engine_script": str(ENGINE_SCRIPT),
        "counts": {s: sum(1 for r in ROWS if r["status"] == s)
                   for s in ("PASS", "FAIL", "NOT_MEASURED")},
        "elapsed_s": round(time.time() - started, 1),
        "checks": ROWS,
    }
    READINGS.parent.mkdir(parents=True, exist_ok=True)
    READINGS.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n读数已落盘：{READINGS}\n计数：{summary['counts']} 用时 {summary['elapsed_s']}s")
    return 1 if summary["counts"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
