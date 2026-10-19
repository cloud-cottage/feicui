#!/usr/bin/env python
# webui/selftest.py
"""「斐萃」本地封装分发版 · **逻辑/API 层直测**（不依赖 GUI —— 主要验收面）。

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

隔离（不污染仓库与使用者数据）：
  * 脚本在 import `api` **之前**把 `FEICUI_DATA_DIR` 指到临时目录 ⇒ `.env` / `.session.json` /
    `var/**`（本地 rename_log.jsonl、缩略图缓存、tab2 任务日志）**全落临时目录**；
  * `feicui` 夹具根目录同样是临时目录（`tempfile.mkdtemp`），跑完删除 ⇒ 仓内 `webui/var/**`、
    `webui/.env`、`webui/.session.json` 一概**不写不动**。

跑法：
    ./venv/bin/python webui/selftest.py                 # 逻辑面 ＋ 一页端到端
    ./venv/bin/python webui/selftest.py --no-e2e        # 跳过真渲染（秒回）
    ./venv/bin/python webui/selftest.py --with-dom      # 另加「渲染后 DOM 断言」（起真窗口，≈2 min）
    ./venv/bin/python webui/selftest.py --with-gui      # 另加短超时窗口试起
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI_DIR))

#: ⚠️ **隔离**：在 import `api` **之前**把可写目录（`.env` / `.session.json` / `var/**`：本地
#: rename_log.jsonl、缩略图缓存、tab2 任务日志）挪到临时目录 ⇒ 跑自检**不再写仓内 webui/var**、
#: 也不动仓内 `.env` / `.session.json`。（`FEICUI_DATA_DIR` 是 `api.py` 已有的打包态开关。）
_SELFTEST_DATA = Path(tempfile.mkdtemp(prefix="feicui-selftest-data-"))
os.environ["FEICUI_DATA_DIR"] = str(_SELFTEST_DATA)

from api import APP_VERSION, DATA_DIR, ENGINE_SCRIPT, SESSION_FILE, VENV_PYTHON, FeicuiApi  # noqa: E402
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
    ap.add_argument("--with-dom", action="store_true",
                    help="另跑 webui/domtest.py：渲染后 DOM 断言（evaluate_js，真窗口）")
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

        # ── ③b tab3 补全面（**逻辑层直测**）：缩略图真出图 / 解析回填 / 三字段边界 /
        #        重命名幂等与冲突拒止 / 本地记录落盘 / 云依赖如实上报 ──
        PLACEHOLDER = WEBUI_DIR / "assets" / "test_seal.tiff"
        sub = "测试子目录"
        subdir_path = root / lib.TIFF_DIR / sub
        # 嵌套子目录（旧版口径：3_Cropped_Tiff 只允许一级；列举须忽略目录）
        (subdir_path / "嵌套子").mkdir(parents=True, exist_ok=True)
        (subdir_path / "嵌套子" / "inner.tiff").write_bytes(PLACEHOLDER.read_bytes())
        # 真 TIFF 夹具：2 个合规名 + 1 个非合规名 + 1 个 .tif 后缀
        fixture_names = {
            "合规一": "P001-C2-R3-长乐未央-汉-陈巨来.tiff",
            "合规二": "P002-C4-R5-吉祥如意-唐-吴昌硕.tiff",
            "非合规": "未命名副本.tiff",
            "tif后缀": "P003-C6-R7-清心-宋-齐白石.tif",
        }
        for key, nm in fixture_names.items():
            (subdir_path / nm).write_bytes(PLACEHOLDER.read_bytes())
        t3 = api.tab3_list({"subdir": sub})
        names = [f["name"] for f in t3.get("files", [])]
        expect("tab3b/list_counts_files_only",
               all(nm in names for nm in fixture_names.values()) and "inner.tiff" not in names,
               f"files={len(names)} names={names}")
        expect("tab3b/standard_flag",
               any(f["name"] == fixture_names["合规一"] and f["standard"] for f in t3["files"])
               and any(f["name"] == fixture_names["非合规"] and not f["standard"] for f in t3["files"]),
               f"standard 面：{[(f['name'][:12], f['standard']) for f in t3['files']]}")
        expect("tab3b/view_cfg_matches_old",
               t3.get("view_cfg") == {"large": {"cols": 5, "per_page": 20},
                                      "medium": {"cols": 10, "per_page": 50},
                                      "small": {"cols": 20, "per_page": 100},
                                      "list": {"cols": 1, "per_page": 30}},
               f"view_cfg={t3.get('view_cfg')} limits={t3.get('limits')}")
        expect("tab3b/cloud_flags_not_connected",
               t3.get("cloud_log") == "not_connected" and t3.get("cloud_lock") == "not_connected",
               f"cloud_log={t3.get('cloud_log')} cloud_lock={t3.get('cloud_lock')}")

        # 解析回填
        p1 = api.tab3_parse({"name": fixture_names["合规一"]})
        expect("tab3b/parse_backfill",
               bool(p1.get("ok")) and p1.get("fields") == {"shiwen": "长乐未央", "dynasty": "汉",
                                                           "author": "陈巨来"}
               and p1.get("prefix") == "P001-C2-R3-" and (p1.get("page"), p1.get("col"), p1.get("row")) == (1, 2, 3),
               f"fields={p1.get('fields')} prefix={p1.get('prefix')} "
               f"page/col/row={p1.get('page')}/{p1.get('col')}/{p1.get('row')}")
        p2 = api.tab3_parse({"name": fixture_names["非合规"]})
        expect("tab3b/parse_nonstandard_empty_prefix",
               bool(p2.get("ok")) and p2.get("standard") is False and p2.get("prefix") == ""
               and p2.get("fields") == {"shiwen": "", "dynasty": "", "author": ""},
               f"standard={p2.get('standard')} prefix={p2.get('prefix')!r} note={p2.get('note')}")

        # 新名预览 + 三字段边界（**不产生副作用**）
        ck = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                             "shiwen": "长乐未央", "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/check_same_name_noop",
               bool(ck.get("ok")) and ck.get("can_rename") is False and ck.get("reason") == "文件名未变化",
               f"new_name={ck.get('new_name')} reason={ck.get('reason')}")
        ck = api.tab3_check({"subdir": sub, "name": fixture_names["非合规"],
                             "shiwen": "清心", "dynasty": "宋", "author": "齐白石"})
        expect("tab3b/check_preview_prefix_from_old_name",
               ck.get("new_name") == "P003-C6-R7-清心-宋-齐白石.tiff" or ck.get("new_name") == "清心-宋-齐白石.tiff",
               f"new_name={ck.get('new_name')}（非合规 ⇒ 前缀留空，与旧版一致）")
        over = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                               "shiwen": "一二三四五六七八九十十", "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/reject_shiwen_over_limit",
               over.get("can_rename") is False and "最多 10 个汉字" in (over.get("reason") or ""),
               f"reason={over.get('reason')} counts={over.get('counts')}")
        empty = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                                "shiwen": "", "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/reject_empty_shiwen",
               empty.get("can_rename") is False and empty.get("reason") == "印面释文不能为空",
               f"reason={empty.get('reason')}")
        au = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                             "shiwen": "长乐", "dynasty": "汉", "author": "一二三四五"})
        expect("tab3b/reject_author_over_limit",
               au.get("can_rename") is False and "最多 4 个汉字" in (au.get("reason") or ""),
               f"reason={au.get('reason')}")
        inval = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                                "shiwen": "长乐:未央", "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/reject_invalid_char",
               inval.get("can_rename") is False and "非法字符" in (inval.get("reason") or ""),
               f"reason={inval.get('reason')}")
        # 非汉字输入：现有 validator **不校验字符类别**（只限长度 + 非法字符）⇒ 如实记录现状
        latin = api.tab3_check({"subdir": sub, "name": fixture_names["合规一"],
                                "shiwen": "abc", "dynasty": "Han", "author": "CHEN"})
        record("tab3b/non_chinese_input_behavior",
               "PASS" if latin.get("can_rename") is True else "FAIL",
               f"can_rename={latin.get('can_rename')} counts={latin.get('counts')} "
               f"⚠️ 现状：validator 只查长度/非法字符，**不校验非汉字**（旧版同此口径）")

        # 缩略图 / 大图：**真出图**（PNG 魔数 + 尺寸 + 引擎）
        th = api.tab3_thumbs({"subdir": sub, "names": [fixture_names["合规一"],
                                                       fixture_names["非合规"]], "size": 150})
        png_ok, dims = {}, {}
        for nm, uri in (th.get("thumbs") or {}).items():
            raw = base64.b64decode(uri.split(",", 1)[1])
            png_ok[nm] = raw[:8] == b"\x89PNG\r\n\x1a\n"
            try:
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as im:
                    dims[nm] = im.size
            except Exception as exc:
                dims[nm] = f"PIL:{exc.__class__.__name__}"
        expect("tab3b/thumbs_real_png",
               bool(th.get("ok")) and len(png_ok) == 2 and all(png_ok.values())
               and all(isinstance(v, tuple) and max(v) <= 150 and min(v) > 0 for v in dims.values()),
               f"count={th.get('count')} engines={th.get('engines')} dims={dims} png={png_ok} "
               f"failed={th.get('failed')}")
        pv = api.tab3_preview({"subdir": sub, "name": fixture_names["合规一"], "size": 400})
        pv_dims = None
        if pv.get("ok"):
            try:
                from PIL import Image
                with Image.open(io.BytesIO(base64.b64decode(pv["data_uri"].split(",", 1)[1]))) as im:
                    pv_dims = im.size
            except Exception as exc:
                pv_dims = f"PIL:{exc.__class__.__name__}"
        expect("tab3b/preview_400_max",
               bool(pv.get("ok")) and isinstance(pv_dims, tuple) and max(pv_dims) <= 400,
               f"size={pv.get('size')} bytes={pv.get('bytes')} engine={pv.get('engine')} dims={pv_dims}")
        miss_pv = api.tab3_preview({"subdir": sub, "name": "不存在.tiff"})
        expect("tab3b/preview_missing_file", not miss_pv.get("ok"), str(miss_pv.get("msg")))
        trav = api.tab3_preview({"subdir": sub, "name": "../../assets/test_seal.tiff"})
        expect("tab3b/path_traversal_blocked", not trav.get("ok"),
               f"msg={trav.get('msg')}（_safe_seg 压成单段名 ⇒ 出不了 3_Cropped_Tiff）")

        # 重命名：幂等 / 冲突拒止 / 记录落盘
        rec_before = len(api.tab3_log({"limit": 200}).get("rows", []))
        rn = api.tab3_rename({"subdir": sub, "name": fixture_names["非合规"],
                              "shiwen": "清心", "dynasty": "宋", "author": "齐白石",
                              "operator": "selftest"})
        newp = subdir_path / "清心-宋-齐白石.tiff"
        md5_src = hashlib.md5(PLACEHOLDER.read_bytes()).hexdigest()
        expect("tab3b/rename_ok_and_file_moved",
               bool(rn.get("ok")) and newp.is_file() and not (subdir_path / fixture_names["非合规"]).exists(),
               f"msg={rn.get('msg')} new={rn.get('new_name')} md5_record={bool(rn.get('record', {}).get('file_md5'))}")
        expect("tab3b/rename_record_md5_matches",
               (rn.get("record") or {}).get("file_md5") == md5_src and (rn.get("record") or {}).get("status") == "success",
               f"file_md5={(rn.get('record') or {}).get('file_md5')} == 占位图 md5 {md5_src}")
        recs = api.tab3_log({"limit": 200})
        last = (recs.get("rows") or [{}])[-1]
        expect("tab3b/local_log_written",
               len(recs.get("rows", [])) == rec_before + 1 and last.get("old_filename") == fixture_names["非合规"]
               and last.get("new_filename") == "清心-宋-齐白石.tiff" and last.get("operator") == "selftest"
               and last.get("印面释文") == "清心" and last.get("cloud_log") == "not_connected"
               and last.get("cloud_lock") == "not_connected",
               f"rows={len(recs.get('rows', []))} last={ {k: last.get(k) for k in ('old_filename','new_filename','operator','印面释文','cloud_log','cloud_lock')} }")
        rn2 = api.tab3_rename({"subdir": sub, "name": newp.name, "shiwen": "清心",
                               "dynasty": "宋", "author": "齐白石"})
        expect("tab3b/rename_idempotent_noop",
               (not rn2.get("ok")) and rn2.get("code") == "noop", f"code={rn2.get('code')} msg={rn2.get('msg')}")
        # 冲突：目标名已存在 ⇒ 拒（且原文件不动）
        # 注意：新名前缀来自**被改名文件自身**的 P/C/R ⇒ 冲突件必须同前缀
        src_for_conflict = "P010-C1-R2-翰墨-元-赵之谦.tiff"
        conflict_target = "P010-C1-R2-得自在-明-邓石如.tiff"
        (subdir_path / conflict_target).write_bytes(PLACEHOLDER.read_bytes())
        (subdir_path / src_for_conflict).write_bytes(PLACEHOLDER.read_bytes())
        rn3 = api.tab3_rename({"subdir": sub, "name": src_for_conflict, "shiwen": "得自在",
                               "dynasty": "明", "author": "邓石如"})
        expect("tab3b/rename_conflict_rejected",
               (not rn3.get("ok")) and rn3.get("code") == "conflict"
               and (subdir_path / src_for_conflict).is_file()
               and (subdir_path / conflict_target).read_bytes() == PLACEHOLDER.read_bytes(),
               f"code={rn3.get('code')} msg={rn3.get('msg')} 原文件仍在={ (subdir_path / src_for_conflict).is_file() }")
        rn4 = api.tab3_rename({"subdir": sub, "name": src_for_conflict, "shiwen": "一二三四五六七八九十十",
                               "dynasty": "明", "author": "邓石如"})
        expect("tab3b/rename_invalid_rejected",
               (not rn4.get("ok")) and rn4.get("code") == "invalid", f"code={rn4.get('code')} msg={rn4.get('msg')}")
        rn5 = api.tab3_rename({"subdir": sub, "name": "不存在.tiff", "shiwen": "长乐",
                               "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/rename_missing_rejected",
               (not rn5.get("ok")) and rn5.get("code") == "missing", f"code={rn5.get('code')}")
        rn6 = api.tab3_rename({"subdir": "不存在子目录", "name": src_for_conflict, "shiwen": "长乐",
                               "dynasty": "汉", "author": "陈巨来"})
        expect("tab3b/rename_bad_subdir_rejected", not rn6.get("ok"), str(rn6.get("msg")))
        # 管理员门禁：会话为非管理员 ⇒ 生成测试件被拒
        sess_backup = SESSION_FILE.read_text(encoding="utf-8") if SESSION_FILE.exists() else None
        try:
            SESSION_FILE.write_text(json.dumps({
                "username": "pan", "expire": (datetime.now() + timedelta(days=1)).isoformat(),
                "feicui_root": str(root.resolve())}), encoding="utf-8")
            api._users = dict(api._users)          # 保持用户表
            named = [u for u, v in api._users.items() if not v["is_admin"]]
            expect("tab3b/admin_guard_active",
                   bool(named) and not api.tab3_generate_test({"subdir": sub}).get("ok"),
                   f"非管理员会话（{named[:1]}）⇒ {api.tab3_generate_test({'subdir': sub}).get('msg')}")
        finally:
            if sess_backup is None:
                SESSION_FILE.unlink(missing_ok=True)
            else:
                SESSION_FILE.write_text(sess_backup, encoding="utf-8")
        # 红线：api.py / src/*.py（**不含**保留的旧 Streamlit 页面 src/webui.py）不得 import
        # webview/streamlit；且 api.py 不得 import 旧页面（**AST 判定**，非 grep）
        offenders = []
        scan = [WEBUI_DIR / "api.py"] + [p for p in sorted((WEBUI_DIR / "src").glob("*.py"))
                                         if p.name != "webui.py"]
        for pf in scan:
            tree = ast.parse(pf.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = ([al.name for al in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for m in mods:
                    head = m.split(".")[0]
                    if head in ("webview", "streamlit"):
                        offenders.append(f"{pf.name}:{m}")
                    if pf.name == "api.py" and head == "webui":
                        offenders.append(f"{pf.name}:{m}（不得引用旧 Streamlit 页面）")
        expect("tab3b/no_gui_import_in_logic_layer", not offenders,
               f"扫描 {[p.name for p in scan]}；offenders={offenders}")
        legacy = (WEBUI_DIR / "src" / "webui.py").read_text(encoding="utf-8")
        expect("tab3b/legacy_streamlit_page_retained",
               "DEPRECATED" in legacy and "def generate_test_tiff" in legacy,
               "旧版 Streamlit 页 webui.py 仍在仓（需求真源，保留）")

        # ── ③c tab3 OCR 试试看 ＋ 纠错建议（逻辑层直测；**临时目录造图**，不碰仓/生产）──
        ocr_sub = "OCR子目录"
        (root / lib.TIFF_DIR / ocr_sub).mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageDraw, ImageFont
            png = root / lib.TIFF_DIR / ocr_sub / "printed.png"
            im = Image.new("RGB", (640, 260), "white")
            dr = ImageDraw.Draw(im)
            fnt = None
            for cand in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                         "/System/Library/Fonts/Supplemental/Arial.ttf",
                         "/System/Library/Fonts/Helvetica.ttc"):
                try:
                    fnt = ImageFont.truetype(cand, 110)
                    break
                except Exception:
                    continue
            fnt = fnt or ImageFont.load_default(110)
            dr.text((30, 40), "FEICUI", fill="black", font=fnt)   # 印刷体（①②类口径）
            dr.text((30, 150), "123", fill="black", font=fnt)
            im.save(png)
            img_ok = True
        except Exception as exc:
            img_ok = False
            record("tab3ocr/fixture_png_made", "FAIL",
                   f"PIL 造图失败：{exc.__class__.__name__}: {exc}")
        if img_ok:
            oc = api.tab3_ocr({"subdir": ocr_sub, "name": "printed.png"})
            texts = oc.get("texts") or []
            expect("tab3ocr/printed_png_returns_texts",
                   bool(oc.get("ok")) and len(texts) > 0
                   and len(oc.get("scores") or []) == len(texts)
                   and float(oc.get("elapsed_s") or 0) >= 0 and bool(oc.get("engine")),
                   f"texts={texts} scores={oc.get('scores')} elapsed_s={oc.get('elapsed_s')} "
                   f"engine={oc.get('engine')!r} mean={oc.get('mean_score')}")
            expect("tab3ocr/printed_scores_high",
                   bool(oc.get("scores")) and min(oc["scores"]) >= 0.9,
                   f"min_score={min(oc.get('scores') or [0])}（①②类印刷体应高分）")
            hint = str(oc.get("hint") or "")
            expect("tab3ocr/honest_hint_present",
                   "印面" in hint and "不可靠" in hint and "仅供参考" in hint
                   and "一键" not in hint,
                   f"hint={hint[:110]}…")
            expect("tab3ocr/ocr_does_not_touch_file",
                   png.is_file() and png.read_bytes()[:4] == b"\x89PNG",
                   f"{png.name} 原样在位（OCR 只读）：size={png.stat().st_size}")

        miss_ocr = api.tab3_ocr({"subdir": ocr_sub, "name": "不存在.png"})
        expect("tab3ocr/missing_file_structured",
               (not miss_ocr.get("ok")) and bool(miss_ocr.get("msg"))
               and miss_ocr.get("texts") == [],
               f"ok={miss_ocr.get('ok')} code={miss_ocr.get('code')} msg={miss_ocr.get('msg')}")
        bad_png = root / lib.TIFF_DIR / ocr_sub / "broken.png"
        bad_png.write_bytes(b"not an image at all")
        bad_ocr = api.tab3_ocr({"subdir": ocr_sub, "name": "broken.png"})
        expect("tab3ocr/invalid_image_structured",
               (not bad_ocr.get("ok")) and bool(bad_ocr.get("msg"))
               and bad_ocr.get("texts") == [],
               f"ok={bad_ocr.get('ok')} code={bad_ocr.get('code')} msg={(bad_ocr.get('msg') or '')[:110]}")
        sub_bad = api.tab3_ocr({"subdir": "不存在子目录", "name": "printed.png"})
        expect("tab3ocr/bad_subdir_rejected", not sub_bad.get("ok"), str(sub_bad.get("msg")))

        # 纠错：suggest 只给候选（不改字）；auto 必须显式传；无命中 ⇒ 空面板
        cs = api.tab3_correct({"text": "左軍丞錄", "mode": "suggest"})
        hits = cs.get("hits") or []
        hit_brief = [(h.get("from"), h.get("to"), h.get("source"), h.get("confidence")) for h in hits]
        expect("corrector/suggest_hits_錄_to_鈢",
               bool(cs.get("ok")) and len(hits) == 1
               and hits[0].get("from") == "錄" and hits[0].get("to") == "鈢"
               and hits[0].get("verified") is True and hits[0].get("applied") is False,
               f"mode={cs.get('mode')} hits={hit_brief}")
        expect("corrector/suggest_does_not_rewrite",
               cs.get("corrected") == "左軍丞錄" and cs.get("raw") == "左軍丞錄",
               f"raw={cs.get('raw')!r} corrected={cs.get('corrected')!r}（suggest 不得改写）")
        ca = api.tab3_correct({"text": "左軍丞錄", "mode": "auto"})
        expect("corrector/auto_only_when_explicit",
               ca.get("corrected") == "左軍丞鈢"
               and (ca.get("stats") or {}).get("n_applied") == 1,
               f"mode={ca.get('mode')} corrected={ca.get('corrected')!r} "
               f"n_applied={(ca.get('stats') or {}).get('n_applied')}")
        expect("corrector/map_review_state_reported",
               (cs.get("map") or {}).get("n_verified") == 2
               and bool((cs.get("map") or {}).get("review_status")),
               f"map={cs.get('map')}（字表 2 条已核定 —— UI 必须显示，别让人以为审完了）")
        cnone = api.tab3_correct({"text": "长乐未央", "mode": "suggest"})
        expect("corrector/no_hits_when_no_rule",
               bool(cnone.get("ok")) and (cnone.get("hits") or []) == [],
               f"hits={cnone.get('hits')}（UI 此时**静默不显示空面板**）")
        cbad = api.tab3_correct({"text": "錄", "mode": "乱来"})
        expect("corrector/bad_mode_structured_failure",
               (not cbad.get("ok")) and bool(cbad.get("msg")),
               f"msg={(cbad.get('msg') or '')[:90]}")

        # 能力探测 ＋ 模拟「本版不含 OCR 引擎」（阶段 1 包 s1 不带 rapidocr）：
        #   ⇒ 必须**打开 tab3 就能看出不可用**（ocr_available=false）＋ tab3_ocr 结构化拒绝（不抛）
        import api as api_mod
        tl = api.tab3_list({"subdir": ocr_sub})
        expect("ocrui/capability_exposed",
               api_mod.ocr_available() is True and tl.get("ocr_available") is True
               and (tl.get("ocr_note") or "") == "" and tl.get("corrector_available") is True,
               f"本机 ocr_available={api_mod.ocr_available()} 列表里 ocr_available={tl.get('ocr_available')} "
               f"ocr_note={tl.get('ocr_note')!r}")
        _orig_probe = api_mod.ocr_available
        try:
            api_mod.ocr_available = lambda: False           # 模拟 s1 包（引擎不随包）
            un = api.tab3_ocr({"subdir": ocr_sub, "name": "printed.png"})
            ul = api.tab3_list({"subdir": ocr_sub})
            cc = api.tab3_correct({"text": "左軍丞錄"})
        finally:
            api_mod.ocr_available = _orig_probe
        expect("ocrui/unavailable_is_structured_not_raise",
               (not un.get("ok")) and un.get("reason") == "OCR_UNAVAILABLE"
               and "本版本不含 OCR 引擎" in (un.get("msg") or "") and un.get("texts") == [],
               f"ok={un.get('ok')} reason={un.get('reason')} msg={(un.get('msg') or '')[:80]}")
        expect("ocrui/unavailable_reported_in_list",
               ul.get("ocr_available") is False and bool(ul.get("ocr_note")),
               f"ocr_available={ul.get('ocr_available')} ocr_note={ul.get('ocr_note')!r}"
               f"（UI 据此置灰按钮并给可读提示）")
        expect("ocrui/corrector_works_without_engine",
               bool(cc.get("ok")) and len(cc.get("hits") or []) == 1,
               "纠错层纯 stdlib ⇒ 缺 OCR 引擎时仍可对手输释文给建议（面板不依赖引擎）")

        # UI 静态面（渲染后断言的补充：节点/桥方法名必须在文件里）
        html = (WEBUI_DIR / "ui" / "index.html").read_text(encoding="utf-8")
        appjs = (WEBUI_DIR / "ui" / "app.js").read_text(encoding="utf-8")
        need_ids = ["btn-tab3-ocr", "tab3-ocr-out", "tab3-ocr-hint", "tab3-ocr-raw",
                    "tab3-corr", "tab3-corr-list", "btn-tab3-corr-apply", "tab3-corr-auto"]
        missing = [i for i in need_ids if f'id="{i}"' not in html]
        expect("ocrui/static_nodes_present", not missing,
               f"缺={missing}；有={[i for i in need_ids if i not in missing]}")
        expect("ocrui/auto_toggle_default_off",
               'id="tab3-corr-auto" checked' not in html
               and 'id="tab3-corr-auto" checked=' not in html,
               "自动纠错复选框**默认未勾选**（auto 不默认生效）")
        expect("ocrui/js_wires_ocr_and_corrector",
               "'tab3_ocr'" in appjs and "'tab3_correct'" in appjs
               and "mode: auto ? 'auto' : 'suggest'" in appjs
               and "btn.disabled = (ST.tab3.ocrAvailable === false)" in
               appjs.split("function doOcr")[1].split("function renderLog")[0],
               "前端调 tab3_ocr / tab3_correct；suggest 为默认，auto 仅勾选后；按钮成败都复原（但缺引擎时保持禁用）")
        expect("ocrui/js_gates_on_ocr_available",
               "r.ocr_available !== false" in appjs and "ocrAvailable === false" in appjs
               and "ocrBtn.disabled = !ST.tab3.ocrAvailable" in appjs,
               "前端按 tab3_list.ocr_available 置灰按钮 / 禁用 auto 复选框并常驻提示（不点才炸）")

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

        # ── ⑧b 渲染后 DOM 断言（真窗口；由 webui/domtest.py 自己起窗/关窗）──
        if args.with_dom:
            dom_json = Path(tempfile.mkdtemp(prefix="feicui-dom-")) / "dom.json"
            cmd = [str(VENV_PYTHON), str(WEBUI_DIR / "domtest.py"), "--out", str(dom_json)]
            t0 = time.time()
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
                rc, out, err = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as exc:
                rc, out, err = "TIMEOUT", exc.stdout or "", exc.stderr or ""
            secs = round(time.time() - t0, 1)
            dom = {}
            try:
                dom = json.loads(dom_json.read_text(encoding="utf-8"))
            except Exception:
                dom = {}
            dc = dom.get("counts") or {}
            dom_ok = (rc == 0 and dc.get("PASS", 0) >= 15 and not dc.get("FAIL"))
            record("dom/rendered_dom_assertions",
                   "PASS" if dom_ok else "FAIL",
                   f"rc={rc} {secs}s checks={dc} probe_error={dom.get('probe_error')} "
                   f"js_errors={len(dom.get('js_errors') or [])}",
                   {"dom_readings": str(dom_json), "stdout_tail": (out or "")[-1200:],
                    "stderr_tail": (err or "")[-800:]})
            for c in (dom.get("checks") or []):
                if c["status"] == "FAIL":
                    record(f"dom/{c['check']}", False, c["detail"][:300])
        else:
            record("dom/rendered_dom_assertions", "NOT_MEASURED",
                   "未加 --with-dom（渲染后 DOM 断言需真窗口）")

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
        "data_dir": str(DATA_DIR),          # 临时目录（隔离；不再写仓内 webui/var）
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
