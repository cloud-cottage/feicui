#!/usr/bin/env python
# local-dist/domtest_dir.py
"""「斐萃」目录初始化页 —— **渲染后 DOM 断言**（真窗口 + `evaluate_js`，不是静态自证）。

覆盖本单 6 项修复（P1 家目录 / P2 空目录成因 / P3 粘贴路径 / P4 自动发现 /
P5 失效 root 启动提示 / P6 校验原文 + 引导建子目录）：

 ⓪ 会话里的 root **已失效** + `.env` 的 FEICUI_ROOT **也不存在** ⇒ 启动**不得**静默进主界面：
    停在目录页、`#dir-hint` 明说「上次的目录已不存在：<路径>」、并**自动**跑一次自动发现；
 ① 先逛到 ~/Downloads，再点「🏠 家目录」⇒ `#dir-path == /Users/kevin`（修 `api.browse('')`
    只会刷新当前目录的老 bug）；
 ② 输入框粘贴 `/Users/kevin/Downloads/金石印源同步空间/feicui` + 回车 ⇒ 校验通过并**进主界面**；
 ③ 自动发现把该路径列为候选（`#dir-cand-list li[data-path]`）；
 ④ 启动提示原文（见 ⓪）逐字核对；
 ⑤ 浏览空壳 `/Users/kevin/Downloads/同步空间` ⇒ 列表区（不是只在小 msg 行）给出
    reason=all_hidden/empty + 可操作提示；
 ⑥ 另测 reason=permission / empty / all_hidden 三种成因，及校验失败时**原始 msg** +
    「🛠 创建标准子目录」引导（真点一次，闭环进主界面）。

隔离（**不碰仓内/使用者真目录**）：
  * 本脚本在 import `api` **之前**把 `FEICUI_DATA_DIR` 指到临时目录 ⇒ `.env` / `.session.json` /
    `var/**` 全落临时目录（`verify_dir` 回写的 FEICUI_ROOT 也只落临时 `.env`）；
  * 夹具目录（空目录 / 只有隐藏目录 / 无权限目录 / 缺子目录的 feicui）全在临时目录里建。

跑法：
    ./venv/bin/python local-dist/domtest_dir.py           # 打印 JSON ＋ 落盘 local-dist/build/readings-dom-dir.json
    ./venv/bin/python local-dist/domtest_dir.py --out /tmp/x.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI_DIR))

#: ⚠️ 必须在 import api 之前设好：所有可写路径挪到临时目录
SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-domtest-dir-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
DATA_DIR = Path(os.environ["FEICUI_DATA_DIR"])
DATA_DIR.mkdir(parents=True, exist_ok=True)

from api import ENV_FILE, FeicuiApi  # noqa: E402

#: `app.py` 必须按文件路径加载（`server/app` 同名包会撞车，见 domtest.py 注释）
_spec = importlib.util.spec_from_file_location("feicui_webui_app_dir", WEBUI_DIR / "app.py")
assert _spec and _spec.loader
_webui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_webui_app)
WINDOW_TITLE = _webui_app.WINDOW_TITLE
build_window = _webui_app.build_window

READINGS = WEBUI_DIR / "build" / "readings-dom-dir.json"

#: 使用者真实要选的同步目录（本单现场事实）
REAL = Path("/Users/kevin/Downloads/金石印源同步空间/feicui")
#: 旧 `.env` 里指向的**已不存在**的路径（父目录 同步空间/ 只剩 .cache 与 Icon\r）
STALE = Path("/Users/kevin/Downloads/同步空间/feicui")
SHELL_DIR = Path("/Users/kevin/Downloads/同步空间")
HOME = str(Path.home())

WIN = None
T0 = time.time()
RESULT: dict = {"dom": {}, "checks": [], "timeline": []}
INFO: dict = {}


def tick(step: str) -> None:
    RESULT["timeline"].append({"t": round(time.time() - T0, 2), "step": step})
    print(f"   … {step} (+{time.time() - T0:.1f}s)", flush=True)


def record(name: str, ok: bool, detail: str) -> None:
    RESULT["checks"].append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)


def _ev(expr: str):
    try:
        return WIN.evaluate_js(expr)
    except Exception as exc:
        RESULT.setdefault("js_errors", []).append(f"{type(exc).__name__}: {exc}")
        return None


def _read(name: str, expr: str):
    raw = _ev(expr)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        data = {"raw": raw}
    RESULT["dom"][name] = data
    return data or {}


def _wait_js(expr: str, timeout: float = 25.0, every: float = 0.3) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if _ev(expr):
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


JS_DIR = """
(() => { const g=id=>document.getElementById(id);
  const box=g('dir-entries'), hint=g('dir-hint'), cands=g('dir-cand-list');
  const lis=[...box.querySelectorAll('li')];
  const emp=box.querySelector('li.empty-state');
  return JSON.stringify({
    view_dir: !!document.querySelector('#view-dir.active'),
    view_main: !!document.querySelector('#view-main.active'),
    path: g('dir-path').textContent,
    entries: lis.filter(li=>li.dataset.name).map(li=>li.dataset.name),
    entries_total: lis.length,
    reason: box.dataset.reason || '',
    empty_text: emp ? (emp.innerText || emp.textContent) : '',
    empty_reason: emp ? (emp.dataset.reason || '') : '',
    hint_kind: hint ? hint.dataset.kind : null,
    hint_hidden: hint ? hint.hidden : null,
    hint: hint ? hint.textContent : '',
    hint_class: hint ? hint.className : '',
    cands_hidden: g('dir-cands') ? g('dir-cands').hidden : null,
    cands: cands ? [...cands.querySelectorAll('li')].map(li=>li.dataset.path) : [],
    cands_label: g('dir-cands-count') ? g('dir-cands-count').textContent : '',
    msg: g('dir-msg').textContent,
    input: g('dir-input').value,
    root_pill: g('root-pill').textContent,
    dir_user: g('dir-user').textContent,
    ensure_pulse: g('btn-ensure') ? g('btn-ensure').classList.contains('pulse') : null,
    buttons: ['btn-home','btn-up','btn-ensure','btn-discover','btn-goto','btn-verify','btn-input']
      .map(id=>(id==='btn-input')?('dir-input:'+(!!g('dir-input'))):(id+':'+(!!g(id))))
  }); })()
"""


def type_path(js_win, path: str) -> None:
    _ev("(() => { const e=document.getElementById('dir-input'); e.value=%s;"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()" % json.dumps(path))


def press_enter() -> None:
    _ev("(() => { const e=document.getElementById('dir-input');"
        "e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); return 1; })()")


def make_fixtures() -> dict:
    fx = SCRATCH / "fx"
    (fx / "empty_dir").mkdir(parents=True, exist_ok=True)
    (fx / "hidden_dir" / ".only_hidden").mkdir(parents=True, exist_ok=True)
    (fx / "perm_dir").mkdir(parents=True, exist_ok=True)
    (fx / "feicui").mkdir(parents=True, exist_ok=True)          # 名为 feicui 但无标准子目录
    os.chmod(fx / "perm_dir", 0o000)
    return {"root": str(fx), "empty_dir": str(fx / "empty_dir"),
            "hidden_dir": str(fx / "hidden_dir"), "perm_dir": str(fx / "perm_dir"),
            "feicui_nosub": str(fx / "feicui")}


# ───────────────────────── probe ─────────────────────────
def _probe_body() -> None:
    tick("wait_bridge")
    _wait_js("!!(document.readyState==='complete' && window.pywebview && window.pywebview.api)", 40)
    # 等 boot() 拿到 session_state（失效 root ⇒ 目录页 + 提示 + 自动发现）
    _wait_js("!!document.getElementById('dir-path')", 30)
    _wait_js("(document.getElementById('dir-path').textContent||'').length > 0"
             " || !!document.querySelector('#view-login.active')", 30)
    time.sleep(1.2)
    tick("boot_read")
    d0 = _read("01_boot_stale_root", JS_DIR)
    record("dom/P5_boot_shows_stale_root_notice_and_stays_on_dir_page",
           d0.get("view_dir") is True and d0.get("view_main") is False
           and str(STALE) in (d0.get("hint") or "")
           and "上次的目录已不存在" in (d0.get("hint") or "")
           and d0.get("hint_kind") == "stale_root",
           f"view_dir={d0.get('view_dir')} view_main={d0.get('view_main')} "
           f"hint_kind={d0.get('hint_kind')!r} 提示原文={ (d0.get('hint') or '')[:120]!r}")
    record("dom/boot_dir_page_starts_at_home",
           (d0.get("path") or "").rstrip("/") == HOME,
           f"#dir-path={d0.get('path')!r}（启动即家目录，不再是「上次浏览过的路径」）")
    record("dom/buttons_present",
           all((d0.get("buttons") or [])[i].endswith(":true") for i in (0, 1, 2, 3, 4, 5, 6)),
           f"控件={d0.get('buttons')}")

    # 自动发现（P5 触发的一次 + 后面手动再点一次都走同一函数）
    tick("wait_discovery")
    _wait_js("document.querySelectorAll('#dir-cand-list li').length > 0", 40)
    time.sleep(0.5)
    tick("discovery_read")
    d1 = _read("02_autodiscover_after_boot", JS_DIR)
    record("dom/P5_boot_autorun_discovery_lists_candidates",
           bool(d1.get("cands")) and d1.get("cands_hidden") is False
           and int(d1.get("cands_label") or 0) >= 1
           and str(STALE) in (d1.get("hint") or ""),   # 失效横幅不许被结果顶掉，只作追加
           f"候选={d1.get('cands')} 计数={d1.get('cands_label')} 隐藏={d1.get('cands_hidden')} "
           f"提示=({d1.get('hint_kind')}) {(d1.get('hint') or '')[:120]!r}")
    record("dom/P4_discovery_finds_real_feicui_dir",
           str(REAL) in (d1.get("cands") or []),
           f"候选里含 {REAL} ⇒ {str(REAL) in (d1.get('cands') or [])}；全部候选={d1.get('cands')}")

    # ── P1：先逛去 ~/Downloads，再点「🏠 家目录」 ──
    tick("P1_navigate")
    type_path(WIN, str(Path(HOME) / "Downloads"))
    press_enter()
    _wait_js(f"(document.getElementById('dir-path').textContent||'').endsWith('/Downloads')", 25)
    dw = _read("03_at_downloads", JS_DIR)
    record("dom/P3_paste_path_enter_navigates",
           (dw.get("path") or "").rstrip("/") == str(Path(HOME) / "Downloads"),
           f"#dir-path={dw.get('path')!r} 条目数={len(dw.get('entries') or [])} "
           f"（输入框+回车进入，path={dw.get('input')!r}）")
    tick("P1_click_home")
    _ev("document.getElementById('btn-home').click()")
    _wait_js(f"(document.getElementById('dir-path').textContent||'').replace(/\\/$/,'')==={json.dumps(HOME)}", 25)
    time.sleep(0.6)
    h1 = _read("04_after_home_click", JS_DIR)
    want_entries = INFO["home_entries"]
    record("dom/P1_home_button_goes_home",
           (h1.get("path") or "").rstrip("/") == HOME
           and sorted(h1.get("entries") or []) == sorted(want_entries),
           f"点「🏠 家目录」后 #dir-path={h1.get('path')!r}（期望 {HOME}）"
           f" 条目 {len(h1.get('entries') or [])} 项，与后端 browse(home) {len(want_entries)} 项一致="
           f"{sorted(h1.get('entries') or []) == sorted(want_entries)}")

    # ── P2：空壳同步目录（/Users/kevin/Downloads/同步空间）──
    tick("P2_shell")
    type_path(WIN, str(SHELL_DIR))
    press_enter()
    _wait_js(f"(document.getElementById('dir-path').textContent||'')==={json.dumps(str(SHELL_DIR))}", 25)
    time.sleep(0.6)
    sh1 = _read("05_shell_dir", JS_DIR)
    record("dom/P2_empty_shell_dir_reason_in_list_area",
           sh1.get("reason") in ("all_hidden", "empty")
           and sh1.get("empty_reason") == sh1.get("reason")
           and ("自动发现" in (sh1.get("empty_text") or "")
                or "隐私与安全性" in (sh1.get("empty_text") or ""))
           and "（无子目录）" not in (sh1.get("empty_text") or ""),
           f"reason={sh1.get('reason')!r} 列表区提示={ (sh1.get('empty_text') or '')[:150]!r} "
           f"（已不再是干瘪的「（无子目录）」）")

    # ── P2：三种成因（empty / all_hidden / permission）夹具逐个真走一遍 ──
    # ⚠️ 夹具在 /var/folders 下，macOS 会把 /var 解析成 /private/var ⇒ 断言只看
    #    `#dir-entries[data-reason]`（browse 成功/失败两条路都会写它），不比对路径字符串
    fx = INFO["fixtures"]
    for key, want_reason, want_word in (("empty_dir", "empty", "没有任何子目录"),
                                        ("hidden_dir", "all_hidden", "隐藏目录"),
                                        ("perm_dir", "permission", "隐私与安全性")):
        tick(f"P2_reason_{key}")
        type_path(WIN, fx[key])
        press_enter()
        _wait_js(f"(document.getElementById('dir-entries').dataset.reason||'')==={json.dumps(want_reason)}", 20)
        time.sleep(0.4)
        rr = _read(f"06_reason_{key}", JS_DIR)
        record(f"dom/P2_reason_{key}",
               rr.get("reason") == want_reason and want_word in (rr.get("empty_text") or ""),
               f"reason={rr.get('reason')!r}（期望 {want_reason}）列表区提示="
               f"{(rr.get('empty_text') or '')[:110]!r}")

    # ── P6：名为 feicui 但缺标准子目录 ⇒ 原文 + 引导「🛠 创建标准子目录」（真点，闭环进主界面）──
    tick("P6_verify_fail")
    type_path(WIN, fx["feicui_nosub"])
    _ev("document.getElementById('btn-verify').click()")
    _wait_js("!!(document.getElementById('dir-msg').textContent||'').length"
             " && (document.getElementById('dir-hint').dataset.kind||'')==='need_subdirs'", 25)
    time.sleep(0.4)
    v1 = _read("07_verify_missing_subdirs", JS_DIR)
    record("dom/P6_verify_failure_shows_raw_msg_and_guides_ensure",
           "必须恰好包含" in (v1.get("msg") or "")
           and v1.get("hint_kind") == "need_subdirs"
           and "创建标准子目录" in (v1.get("hint") or "")
           and v1.get("view_main") is False,
           f"#dir-msg 原文={ (v1.get('msg') or '')[:120]!r} hint_kind={v1.get('hint_kind')!r} "
           f"引导={ (v1.get('hint') or '')[:110]!r} 按钮高亮={v1.get('ensure_pulse')}")
    tick("P6_click_ensure")
    _ev("document.getElementById('btn-ensure').click()")
    _wait_js("(document.querySelectorAll('#dir-entries li[data-name]').length||0) >= 3", 25)
    time.sleep(0.6)
    v2 = _read("08_after_ensure_subdirs", JS_DIR)
    record("dom/P6_ensure_subdirs_then_verify_enters_main",
           v2.get("entries") == ["1_Original_PDF", "2_HighRes_PDF", "3_Cropped_Tiff"],
           f"建完子目录后列表={v2.get('entries')} msg={(v2.get('msg') or '')[:80]!r}")
    tick("P6_verify_again")
    _ev("document.getElementById('btn-verify').click()")
    _wait_js("!!document.querySelector('#view-main.active')", 30)
    time.sleep(0.8)
    v3 = _read("09_entered_main_fixture", JS_DIR)
    record("dom/P6_verify_after_ensure_enters_main",
           v3.get("view_main") is True and fx["feicui_nosub"] in (v3.get("root_pill") or ""),
           f"view_main={v3.get('view_main')} root_pill={(v3.get('root_pill') or '')[:80]!r}")

    # ── P3 + 主场景：粘贴使用者真同步目录 + 回车 ⇒ 校验通过并进主界面 ──
    tick("P3_real_dir")
    _ev("(() => { const b=[...document.querySelectorAll('[data-action=\\\"change-dir\\\"]')][0];"
        " b.click(); return 1; })()")
    _wait_js("!!document.querySelector('#view-dir.active')", 25)
    time.sleep(0.8)
    type_path(WIN, str(REAL))
    press_enter()
    tick("P3_wait_main")
    _wait_js("!!document.querySelector('#view-main.active')", 40)
    time.sleep(1.0)
    r1 = _read("10_real_dir_entered", JS_DIR)
    record("dom/P3_paste_real_sync_dir_verifies_and_enters_main",
           r1.get("view_main") is True and str(REAL) in (r1.get("root_pill") or ""),
           f"view_main={r1.get('view_main')} root_pill={(r1.get('root_pill') or '')[:90]!r}"
           f"（输入框={r1.get('input')!r} 回车后校验进入）")

    # 回到目录页看主界面里「🔄 目录」也可用（不改 tab 逻辑）
    tick("P_change_dir_back")
    _ev("(() => { const b=[...document.querySelectorAll('[data-action=\\\"change-dir\\\"]')][0];"
        " b.click(); return 1; })()")
    _wait_js("!!document.querySelector('#view-dir.active')", 25)
    time.sleep(0.8)
    c1 = _read("11_change_dir_back", JS_DIR)
    record("dom/change_dir_button_reopens_dir_page",
           c1.get("view_dir") is True and (c1.get("path") or "").endswith("/feicui"),
           f"view_dir={c1.get('view_dir')} #dir-path={c1.get('path')!r}")


def probe() -> None:
    try:
        _probe_body()
    except Exception as exc:
        RESULT["probe_error"] = f"{type(exc).__name__}: {exc}"
        print(f"❌ probe 异常（已记录，继续收尾）：{type(exc).__name__}: {exc}", flush=True)
    finally:
        try:
            WIN.destroy()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    global WIN
    ap = argparse.ArgumentParser(description="斐萃 目录初始化页 渲染后 DOM 断言（真窗口）")
    ap.add_argument("--out", default=str(READINGS))
    ap.add_argument("--watchdog", type=float, default=420.0)
    args = ap.parse_args(argv)

    fixtures = make_fixtures()
    # 现场事实复刻：`.env` 的 FEICUI_ROOT 指向已不存在路径；会话里也存着同一个失效 root
    ENV_FILE.write_text(f"FEICUI_ROOT={STALE}\n", encoding="utf-8")
    api = FeicuiApi()
    admin = [u for u, v in api._users.items() if v["is_admin"]][0]
    (DATA_DIR / ".session.json").write_text(json.dumps({
        "username": admin,
        "expire": "2099-01-01T00:00:00",
        "feicui_root": str(STALE),
    }, ensure_ascii=False), encoding="utf-8")

    INFO.update({"scratch": str(SCRATCH), "data_dir": str(DATA_DIR), "fixtures": fixtures,
                 "real": str(REAL), "stale": str(STALE), "shell_dir": str(SHELL_DIR),
                 "admin": admin, "env_file": str(ENV_FILE),
                 "real_verify": list(_verify(str(REAL))),
                 "shell_verify": list(_verify(str(SHELL_DIR)))})
    # 家目录条目（DOM 断言对照值）；⚠️ 会在后端套用 _nav_root，故在起窗前取
    INFO["home_entries"] = list(api.browse({"home": True}).get("entries") or [])

    webview, WIN = build_window(api)
    threading.Timer(args.watchdog, lambda: (RESULT.setdefault("watchdog", "fired"), WIN.destroy())).start()
    print(f"DOMTEST_START fixtures={fixtures} data_dir={DATA_DIR} window_title={WINDOW_TITLE!r}", flush=True)
    webview.start(probe)

    # ── 后端契约复核（**向后兼容** + 自动发现读数，与 DOM 互为证据）──
    post: dict = {}
    post["browse_legacy_semantics"] = {
        "after_browse_downloads": api.browse({"path": str(Path(HOME) / "Downloads")}).get("path"),
        "then_no_path": api.browse({}).get("path"),
        "home_flag": api.browse({"home": True}).get("path"),
        "tilde": api.browse({"path": "~"}).get("path"),
    }
    post["browse_legacy_ok"] = (post["browse_legacy_semantics"]["then_no_path"]
                               == post["browse_legacy_semantics"]["after_browse_downloads"]
                               and post["browse_legacy_semantics"]["home_flag"] == HOME
                               and post["browse_legacy_semantics"]["tilde"] == HOME)
    findr = api.find_feicui_dirs({})
    post["find"] = {k: findr.get(k) for k in ("count", "scanned_dirs", "elapsed_s", "truncated", "roots")}
    post["find"]["candidates"] = [c["path"] for c in findr.get("candidates") or []]
    post["find"]["candidate_msgs"] = [(c["path"], c["msg"]) for c in findr.get("candidates") or []]
    post["env_after"] = ENV_FILE.read_text(encoding="utf-8").strip()
    post["session_after"] = (DATA_DIR / ".session.json").read_text(encoding="utf-8").strip()
    record("api/browse_backward_compatible",
           post["browse_legacy_ok"],
           f"无 path ⇒ 上次浏览路径（{post['browse_legacy_semantics']['then_no_path']!r}）；"
           f"home=true / path=~ ⇒ {HOME}；读数={post['browse_legacy_semantics']}")
    record("api/find_feicui_dirs_backend",
           post["find"]["count"] >= 1 and str(REAL) in post["find"]["candidates"],
           f"count={post['find']['count']} 扫 {post['find']['scanned_dirs']} 个目录 / "
           f"{post['find']['elapsed_s']}s truncated={post['find']['truncated']} "
           f"候选={post['find']['candidates']}")

    counts = {s: sum(1 for c in RESULT["checks"] if c["status"] == s) for s in ("PASS", "FAIL")}
    summary = {"schema": "feicui.webui.domtest.dir.v1",
               "at": datetime.now().isoformat(timespec="seconds"),
               "python": sys.executable, "window_title": WINDOW_TITLE,
               "counts": counts, "info": INFO, "checks": RESULT["checks"],
               "dom": RESULT["dom"], "post": post,
               "js_errors": RESULT.get("js_errors", []), "probe_error": RESULT.get("probe_error")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 目录初始化页 DOM 断言（渲染后实测）===")
    print(json.dumps({"counts": counts, "info": {k: v for k, v in INFO.items() if k != "home_entries"},
                      "post": post}, ensure_ascii=False, indent=2))
    print(f"\n读数落盘：{out}")
    try:
        os.chmod(fixtures["perm_dir"], 0o755)
    except Exception:
        pass
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if counts["FAIL"] else 0


def _verify(path: str):
    from src import pdf_library as lib
    return lib.verify_feicui_dir(Path(path))


if __name__ == "__main__":
    raise SystemExit(main())
