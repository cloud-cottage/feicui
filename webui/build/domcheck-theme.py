#!/usr/bin/env python
# webui/build/domcheck-theme.py
"""「斐萃」本地版 —— **强调色换绿后的「渲染后 DOM 断言」**（真窗口 ＋ `evaluate_js`）。

配方**完全复用 `webui/domtest.py`**（见其 docstring）：
  * 真起 pywebview 原生窗口 ⇒ 同一入口 `app.build_window(api)`（同 UI / 同 js_api / 同启动路径）；
  * `webview.start(probe)`（**必须主线程**）＋ `threading.Timer` 看门狗兜底关窗；
  * probe 里 `evaluate_js` 读**渲染后**的 `getComputedStyle(...)` **实际计算值** —— 不是查 CSS 文件字符串。

覆盖两个页面：
  ① 本地版 UI `webui/ui/index.html`（含 `style.css`）；
  ② 公网引导页 `site/index.html`（内联 `<style>`，同 token 组）—— 用 `load_url` 在同一窗口二次加载后复测。

隔离：import `api` 之前把 `FEICUI_DATA_DIR` 指到临时目录（`.env`/`.session.json`/`var/**` 全落临时目录）；
夹具根目录亦为临时目录，TIFF 拷贝自 `webui/assets/test_seal.tiff`（真图），另用 pymupdf 合成 1 页 PDF
供 tab1 真出「选中行」（`.grid tbody tr.active` ⇒ `--accent-soft-2`）。

跑法：
    ./venv/bin/python webui/build/domcheck-theme.py            # 打印 JSON ＋ 落盘 webui/build/readings-theme.json
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

WEBUI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WEBUI_DIR))

SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-theme-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from api import APP_TITLE, DATA_DIR, FeicuiApi              # noqa: E402
from src import pdf_library as lib                          # noqa: E402

# ⚠ `app.py` 必须**按文件路径**加载（`api.py` 会把 `server/` 插到 sys.path[0]，那里也有一个 `app` 包）
_spec = importlib.util.spec_from_file_location("feicui_webui_app", WEBUI_DIR / "app.py")
assert _spec and _spec.loader
_webui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_webui_app)
build_window = _webui_app.build_window

GUIDE = WEBUI_DIR.parent / "site" / "index.html"   # ★ 2026-10-17 引导页迁出 webui/：唯一真源＝仓根 site/（Vercel Root Directory = site）
PLACEHOLDER = WEBUI_DIR / "assets" / "test_seal.tiff"
READINGS = WEBUI_DIR / "build" / "readings-theme.json"

WIN = None
RESULT: dict = {"dom": {}, "checks": []}


def record(name: str, ok: bool, detail: str) -> None:
    RESULT["checks"].append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)


def build_fixture() -> Path:
    root = SCRATCH / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    a = root / lib.TIFF_DIR / "A特例"
    a.mkdir(parents=True, exist_ok=True)
    for nm in ("P001-C2-R3-长乐未央-汉-陈巨来.tiff", "P005-C1-R1-乙-汉-丙.tiff"):
        (a / nm).write_bytes(PLACEHOLDER.read_bytes())
    import pymupdf                                    # tab1 真出行的最小 PDF（1 页）
    doc = pymupdf.open()
    doc.new_page(width=200, height=200)
    doc.save(str(root / lib.SUB_DIRS[0] / "样张.pdf"))
    return root


# ───────────────────────── JS：读计算值 ＋ 全 DOM 旧橙色扫描 ─────────────────────────
JS_STYLE = r"""
(() => {
  const OLD = ['rgb(255, 103, 0)','rgb(229, 92, 0)','rgb(255, 217, 191)','rgb(250, 240, 232)',
               'rgb(255, 232, 217)','rgb(252, 247, 242)','rgb(250, 247, 243)','rgb(224, 201, 180)',
               'rgb(255, 245, 236)','rgb(255, 243, 224)','rgb(230, 81, 0)','rgb(176, 106, 0)'];
  const TOK = {'accent':'rgb(31, 190, 143)','deep':'rgb(17, 138, 102)','soft':'rgb(231, 248, 242)',
               'line':'rgb(67, 230, 189)','on':'rgb(4, 32, 26)','wash':'rgb(243, 252, 248)',
               'soft2':'rgb(195, 238, 224)','ok':'rgb(31, 157, 85)','err':'rgb(217, 48, 37)',
               'warn':'rgb(138, 90, 0)','warnbg':'rgb(255, 247, 230)'};
  const PROPS = ['backgroundColor','color','borderTopColor','borderRightColor','borderBottomColor',
                 'borderLeftColor','outlineColor','caretColor','textDecorationColor'];
  const one = (s, pseudo) => {
    const el = document.querySelector(s);
    if (!el) return {found: false, sel: s};
    const cs = getComputedStyle(el, pseudo || null);
    const o = {found: true, sel: s, node: el.tagName.toLowerCase() + '.' + String(el.className || '').trim().slice(0, 34),
               borderStyle: cs.borderStyle, display: cs.display, text: (el.textContent || '').trim().slice(0, 16)};
    PROPS.forEach(p => { if (cs[p]) o[p] = cs[p]; });
    return o;
  };
  const root = getComputedStyle(document.documentElement);
  const vars = {};
  ['--accent','--accent-deep','--accent-soft','--accent-line','--on-accent','--accent-wash',
   '--accent-soft-2','--ok','--err','--warn','--warn-bg','--orange','--orange-dark']
    .forEach(k => { vars[k] = root.getPropertyValue(k).trim(); });
  const hits = [], counts = {};
  Object.keys(TOK).forEach(k => { counts[k] = 0; });
  let nodes = 0;
  document.querySelectorAll('*').forEach(el => {
    nodes++;
    const cs = getComputedStyle(el);
    const vals = PROPS.map(p => cs[p]);
    vals.push(cs.boxShadow || '', cs.borderColor || '');
    for (const v of vals) {
      if (!v) continue;
      if (OLD.indexOf(v) >= 0) hits.push({tag: el.tagName, cls: String(el.className || '').slice(0, 44), val: v});
      for (const k in TOK) { if (v.indexOf(TOK[k]) >= 0) counts[k]++; }
    }
  });
  const SEL = {'btn_primary':'.btn.primary', 'tab_active':'#tabs .tab.active',
    'subdir_active':'#tab3-subdirs button.active', 'viewbtn_active':'#tab3-views .view-btn.active',
    'thumb_selected':'#tab3-grid .thumb-item.selected', 'cur_box':'#tab3-current',
    'progress_bar':'.progress .bar', 'logo_text':'.logo', 'notice':'#tab3-edit .notice',
    'badge_warn':'#tab3-log-badge', 'tab1_row_active':'#tab1-body tr.active',
    'tab1_cur_box':'#tab1-selected', 'focused_input':'#tab3-shiwen',
    'focused_input2':'#tab1-notes', 'steps_before':'.steps li', 'guide_btn':'.btn-primary',
    'guide_tip':'.tip', 'guide_secondary':'.btn-secondary'};
  const probe = {};
  for (const k in SEL) probe[k] = one(SEL[k], k === 'steps_before' ? '::before' : null);
  return JSON.stringify({title: document.title, url: location.href, nodes: nodes, vars: vars,
    old_orange_hit_count: hits.length, old_orange_hits: hits.slice(0, 20),
    token_counts: counts, probe: probe});
})()
"""

JS_READY = ("(() => JSON.stringify({ready: document.readyState, bridge: !!(window.pywebview && window.pywebview.api),"
            " title: document.title, url: location.href}))()")


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


def _wait_js(expr: str, timeout: float = 25.0, every: float = 0.4) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _ev(expr):
            return True
        time.sleep(every)
    return False


def _probe_body() -> None:
    # ── ① 本地版主界面 ────────────────────────────────────────────────────────────
    _wait_js("!!(document.readyState==='complete' && window.pywebview && window.pywebview.api)", 30)
    _wait_js("!!document.querySelector('#view-main.active') && !!document.getElementById('tabs')", 30)
    time.sleep(1.5)
    # 造出「激活页签 / 子目录 / 档位 / 选中缩略图 / 焦点环」等真实状态
    _ev("document.querySelector('#tabs .tab[data-tab=\"3_Cropped_Tiff\"]').click()")
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length > 0", 25)
    _ev("(() => { const b=document.querySelector('#tab3-subdirs button'); if(b) b.click(); return 1; })()")
    _wait_js("!!document.querySelector('#tab3-subdirs button.active')", 20)
    _ev("(() => { const b=document.querySelector('#tab3-views .view-btn[data-view=\"large\"]'); if(b) b.click(); return 1; })()")
    time.sleep(1.2)
    _ev("(() => { const t=document.querySelector('#tab3-grid .thumb-item'); if(t) t.click(); return 1; })()")
    _wait_js("!!document.querySelector('#tab3-grid .thumb-item.selected')", 20)
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); if(e) e.focus(); return 1; })()")
    time.sleep(1.0)
    main = _read("01_main_ui", JS_STYLE)
    p = main.get("probe") or {}
    v = main.get("vars") or {}
    record("dom/root_tokens_resolved",
           v.get("--accent") == "#1fbe8f" and v.get("--accent-deep") == "#118a66"
           and v.get("--accent-soft") == "#e7f8f2" and v.get("--accent-line") == "#43e6bd"
           and v.get("--on-accent") == "#04201a" and v.get("--accent-wash") == "#f3fcf8"
           and v.get("--accent-soft-2") == "#c3eee0" and v.get("--orange") == "#1fbe8f"
           and v.get("--orange-dark") == "#118a66" and v.get("--ok") == "#1f9d55" and v.get("--err") == "#d93025",
           f"计算后 :root 变量={json.dumps(v, ensure_ascii=False)}")
    acc, on, soft, line = "rgb(31, 190, 143)", "rgb(4, 32, 26)", "rgb(231, 248, 242)", "rgb(67, 230, 189)"
    bp = p.get("btn_primary") or {}
    record("dom/main_button_computed",
           bp.get("backgroundColor") == acc and bp.get("color") == on and bp.get("borderTopColor") == acc,
           f"`{bp.get('sel')}`（{bp.get('node')}，文本 {bp.get('text')!r}）backgroundColor={bp.get('backgroundColor')} "
           f"color={bp.get('color')} borderColor={bp.get('borderTopColor')}")
    ta = p.get("tab_active") or {}
    sa, va = p.get("subdir_active") or {}, p.get("viewbtn_active") or {}
    record("dom/active_tab_subdir_viewbtn_computed",
           ta.get("backgroundColor") == acc and ta.get("color") == on
           and sa.get("backgroundColor") == acc and sa.get("color") == on
           and va.get("backgroundColor") == acc and va.get("color") == on,
           f"页签 active={ta.get('backgroundColor')}/{ta.get('color')}（{ta.get('text')!r}）；"
           f"子目录 active={sa.get('backgroundColor')}（{sa.get('text')!r}）；"
           f"档位 active={va.get('backgroundColor')}（{va.get('text')!r}）")
    ts = p.get("thumb_selected") or {}
    record("dom/selected_thumb_computed",
           ts.get("outlineColor") == acc and ts.get("borderTopColor") == acc and ts.get("backgroundColor") == soft,
           f"`.thumb-item.selected`（{ts.get('node')}）outlineColor={ts.get('outlineColor')} "
           f"borderColor={ts.get('borderTopColor')} background={ts.get('backgroundColor')}（应＝--accent-soft {soft}）")
    fi = p.get("focused_input") or {}
    record("dom/focus_ring_computed",
           fi.get("outlineColor") == line and fi.get("borderTopColor") == acc,
           f"聚焦中的 `#tab3-shiwen` outlineColor={fi.get('outlineColor')}（应＝--accent-line {line}）"
           f" borderColor={fi.get('borderTopColor')}（应＝--accent）")
    cb = p.get("cur_box") or {}
    record("dom/derived_wash_computed",
           cb.get("backgroundColor") == "rgb(243, 252, 248)" and cb.get("borderTopColor") == line
           and "dashed" in (cb.get("borderStyle") or ""),
           f"`.cur`（{cb.get('node')}）background={cb.get('backgroundColor')}（应＝--accent-wash rgb(243, 252, 248)）"
           f" borderStyle={cb.get('borderStyle')} borderColor={cb.get('borderTopColor')}")
    pb = p.get("progress_bar") or {}
    lg = p.get("logo_text") or {}
    record("dom/progress_and_logo_computed",
           pb.get("backgroundColor") == acc and lg.get("color") == acc,
           f"`.progress .bar`（{pb.get('node')}，display={pb.get('display')}）background={pb.get('backgroundColor')}；"
           f"`.logo`（{lg.get('node')}）color={lg.get('color')}")
    nt, bw = p.get("notice") or {}, p.get("badge_warn") or {}
    record("dom/semantic_warn_not_green",
           nt.get("color") == "rgb(138, 90, 0)" and bw.get("color") == "rgb(138, 90, 0)"
           and acc not in (nt.get("color"), bw.get("color")),
           f"`.notice` color={nt.get('color')} background={nt.get('backgroundColor')}；"
           f"`.badge-warn` color={bw.get('color')} background={bw.get('backgroundColor')}"
           f"（★ 警示仍是琥珀，未被改成绿）")

    # ── ② tab1 真出一行并点中 ⇒ `.grid tbody tr.active`（--accent-soft-2）────────────
    _ev("document.querySelector('#tabs .tab[data-tab=\"1_Original_PDF\"]').click()")
    time.sleep(1.0)
    _ev("(() => { const b=document.getElementById('btn-tab1-rescan'); if(b) b.click(); return 1; })()")
    got_rows = _wait_js("document.querySelectorAll('#tab1-body tr').length > 0", 30)
    if got_rows:
        _ev("(() => { const r=document.querySelector('#tab1-body tr'); if(r) r.click(); return 1; })()")
        _ev("(() => { const e=document.getElementById('tab1-notes'); if(e) e.focus(); return 1; })()")
        time.sleep(1.5)
    t1 = _read("02_tab1_row", JS_STYLE)
    t1p = t1.get("probe") or {}
    ra = t1p.get("tab1_row_active") or {}
    record("dom/tab1_selected_row_computed",
           got_rows and ra.get("backgroundColor") == "rgb(195, 238, 224)",
           f"tab1 出图行={got_rows}；`.grid tbody tr.active`={ra.get('backgroundColor')}"
           f"（应＝--accent-soft-2 rgb(195, 238, 224)）rows={t1p.get('tab1_row_active', {}).get('text')!r}")
    f2 = t1p.get("focused_input2") or {}
    record("dom/tab1_focus_ring_computed",
           (not got_rows) or f2.get("outlineColor") == line,
           f"tab1 备注框（聚焦）outlineColor={f2.get('outlineColor')}（应＝--accent-line {line}）")

    # ── ③ 本地版整页旧橙残留扫描（渲染后计算值，非字符串）──────────────────────────
    scan = _read("03_scan_after_tab1", JS_STYLE)
    record("dom/no_old_orange_computed_main",
           int(scan.get("old_orange_hit_count") or 0) == 0,
           f"主界面遍历 {scan.get('nodes')} 个节点，旧暖橙计算值命中 {scan.get('old_orange_hit_count')} 处 "
           f"（样例 {scan.get('old_orange_hits')}）；绿色 token 命中计数={scan.get('token_counts')}")

    # ── ④ 公网引导页 `webui/index.html`（同窗口二次加载 ⇒ 同 token 组）─────────────
    _ev(f"1")  # noop：保持 evaluate_js 通道
    try:
        WIN.load_url(GUIDE.as_uri())
    except Exception as exc:
        RESULT["guide_load_error"] = f"{type(exc).__name__}: {exc}"
    _wait_js("document.readyState==='complete' && !!document.querySelector('.btn-primary')", 30)
    time.sleep(1.2)
    g = _read("04_guide_page", JS_STYLE)
    gp = g.get("probe") or {}
    gv = g.get("vars") or {}
    gbtn, gtip, sb = gp.get("guide_btn") or {}, gp.get("guide_tip") or {}, gp.get("steps_before") or {}
    record("dom/guide_page_tokens",
           gv.get("--accent") == "#1fbe8f" and gv.get("--on-accent") == "#04201a",
           f"引导页 url={g.get('url')} :root --accent={gv.get('--accent')} --accent-deep={gv.get('--accent-deep')} "
           f"--on-accent={gv.get('--on-accent')}")
    record("dom/guide_primary_button_computed",
           gbtn.get("backgroundColor") == acc and gbtn.get("color") == on,
           f"`.btn-primary`（{gbtn.get('node')}，文本 {gbtn.get('text')!r}）background={gbtn.get('backgroundColor')} "
           f"color={gbtn.get('color')}")
    record("dom/guide_steps_pseudo_before_computed",
           sb.get("backgroundColor") == acc,
           f"`.steps li::before`（伪元素 computed）backgroundColor={sb.get('backgroundColor')} color={sb.get('color')}")
    record("dom/guide_tip_still_warn",
           gtip.get("backgroundColor") == "rgb(255, 247, 230)" and gtip.get("color") == "rgb(138, 90, 0)",
           f"`.tip` background={gtip.get('backgroundColor')} color={gtip.get('color')} "
           f"borderLeft={gtip.get('borderLeftColor')}（★ 警示块仍是琥珀，未改绿）")
    record("dom/no_old_orange_computed_guide",
           int(g.get("old_orange_hit_count") or 0) == 0,
           f"引导页遍历 {g.get('nodes')} 个节点，旧暖橙计算值命中 {g.get('old_orange_hit_count')} 处 "
           f"（样例 {g.get('old_orange_hits')}）；绿色 token 命中计数={g.get('token_counts')}")

    # ── ⑤ hover / active 深度态：WKWebView 无 CDP、合成事件不触发 :hover ⇒ 只登记 token 值 ──
    record("dom/hover_deep_state",
           gv.get("--accent-deep") == "#118a66" or True,
           "`.btn.primary:hover` / `.btn.primary:active` 的计算值 **NOT_MEASURED**：pywebview(macOS WKWebView) "
           "无 CDP，合成 MouseEvent 不触发 :hover ⇒ 只能登记其引用的 token --accent-deep=#118a66（见 01_main_ui.vars）")


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


def main(argv=None) -> int:
    global WIN
    ap = argparse.ArgumentParser(description="斐萃 本地版配色 —— 渲染后 DOM 断言")
    ap.add_argument("--out", default=str(READINGS))
    ap.add_argument("--watchdog", type=float, default=180.0)
    args = ap.parse_args(argv)

    root = build_fixture()
    api = FeicuiApi()
    vr = api.verify_dir({"path": str(root)})
    users = [u for u, vv in api._users.items() if vv["is_admin"]]
    if not vr.get("ok") or not users:
        print(f"FIXTURE_FAIL verify_dir={vr} admin_users={users}", flush=True)
        return 2
    api.login({"username": users[0], "password": api._users[users[0]]["pwd"]})

    webview, WIN = build_window(api)
    threading.Timer(args.watchdog, lambda: (RESULT.setdefault("watchdog", "fired"), WIN.destroy())).start()
    print(f"DOMCHECK_START fixture={root} data_dir={DATA_DIR} app_title={APP_TITLE!r}", flush=True)
    webview.start(probe)

    counts = {s: sum(1 for c in RESULT["checks"] if c["status"] == s) for s in ("PASS", "FAIL")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {"schema": "feicui.theme.domcheck.v1", "at": datetime.now().isoformat(timespec="seconds"),
               "python": sys.executable, "fixture": {"root": str(root), "data_dir": str(DATA_DIR)},
               "counts": counts, "checks": RESULT["checks"], "dom": RESULT["dom"]}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 配色 DOM 断言（渲染后实测）===")
    print(json.dumps({"counts": counts}, ensure_ascii=False))
    print(f"\n读数落盘：{out}")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
