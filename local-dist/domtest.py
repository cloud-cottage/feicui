#!/usr/bin/env python
# local-dist/domtest.py
"""「斐萃」tab3 —— **渲染后 DOM 断言**（真窗口 + `evaluate_js`，不是静态自证）。

做法（本会话实测配方）：
  * 真起 pywebview 原生窗口 ⇒ 复用 `app.build_window(api)`（**同一 UI、同一 js_api、同一启动路径**）；
  * `webview.start(probe)`（**必须主线程**，否则 `pywebview must be run on a main thread`），
    probe 里 `time.sleep` 等页面/异步桥，再用 `window.evaluate_js(...)` 读**渲染后的真实 DOM**；
  * 真交互：点 tab3 → 切四档视图 → 点缩略图格子 → 读右栏三输入框回填 → 改释文触发校验
    → 撞同名冲突 → 点「执行重命名」→ 点「生成测试 TIFF」→ 派发方向键；
  * `threading.Timer(180, …)` 看门狗兜底关窗，防挂死。

隔离（**不碰仓内/使用者真目录**）：
  * 本脚本在 import `api` **之前**把 `FEICUI_DATA_DIR` 指到临时目录 ⇒ `.env` / `.session.json` /
    `var/**`（本地 rename_log.jsonl、缩略图缓存）全落临时目录；
  * `feicui` 夹具根目录亦为临时目录，TIFF 拷贝自 `local-dist/assets/test_seal.tiff`（真图，缩略图真出图）。

跑法：
    ./venv/bin/python local-dist/domtest.py                  # 打印 JSON ＋ 落盘 local-dist/build/readings-dom.json
    ./venv/bin/python local-dist/domtest.py --out /tmp/x.json
"""
from __future__ import annotations

import argparse
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

#: ⚠️ 必须在 import api 之前设好：把所有可写路径挪到临时目录（见模块 docstring「隔离」）
SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-domtest-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from api import APP_TITLE, CLOUD_LOG_STATUS, DATA_DIR, RENAME_LOG, FeicuiApi  # noqa: E402
from src import pdf_library as lib  # noqa: E402

#: `app.py` 必须**按文件路径**加载：`api.py` 会把 `server/` 插到 sys.path[0]，
#: 那里也有一个名为 `app` 的包（老工程 `server/app/naming.py`）⇒ 直接 `from app import …`
#: 会撞名。按路径加载可确保拿到的是 `local-dist/app.py`（同一份窗口入口）。
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("feicui_webui_app", WEBUI_DIR / "app.py")
assert _spec and _spec.loader
_webui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_webui_app)
WINDOW_TITLE = _webui_app.WINDOW_TITLE
build_window = _webui_app.build_window

PLACEHOLDER = WEBUI_DIR / "assets" / "test_seal.tiff"
READINGS = WEBUI_DIR / "build" / "readings-dom.json"

WIN = None                      # pywebview window（probe 里用）
RESULT: dict = {"dom": {}, "checks": []}
FIXTURE_INFO: dict = {}


def record(name: str, ok: bool, detail: str) -> None:
    RESULT["checks"].append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)


def build_fixture() -> Path:
    """临时 feicui 夹具：A特例（解析/冲突/重命名）+ 分页B（25 个 ⇒ large 档 2 页）。"""
    root = SCRATCH / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    a = root / lib.TIFF_DIR / "A特例"
    a.mkdir(parents=True, exist_ok=True)
    for nm in ("P001-C2-R3-长乐未央-汉-陈巨来.tiff", "P005-C1-R1-待定-汉-丙.tiff",
               "P005-C1-R1-乙-汉-丙.tiff", "未命名副本.tiff"):
        (a / nm).write_bytes(PLACEHOLDER.read_bytes())
    pg = root / lib.TIFF_DIR / "分页B"
    pg.mkdir(parents=True, exist_ok=True)
    for i in range(1, 26):
        (pg / f"P{i:03d}-C1-R2-长乐-汉-陈巨来.tiff").write_bytes(PLACEHOLDER.read_bytes())
    return root


# ───────────────────────── probe（跑在 pywebview 自己的线程）─────────────────────────
def _ev(expr: str):
    """`evaluate_js` 包装：**永不抛**（JS 报错只记录；否则会打断整轮 probe）。"""
    try:
        return WIN.evaluate_js(expr)
    except Exception as exc:
        RESULT.setdefault("js_errors", []).append(f"{type(exc).__name__}: {exc}")
        return None


def _read(name: str, expr: str):
    try:
        raw = _ev(expr)
    except Exception as exc:
        RESULT["dom"][name] = {"error": f"{type(exc).__name__}: {exc}"}
        return {"error": str(exc)}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        data = {"raw": raw}
    RESULT["dom"][name] = data
    return data or {}


def _wait_js(expr: str, timeout: float = 20.0, every: float = 0.4) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if _ev(expr):
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


JS_READY = """
(() => { const g=id=>document.getElementById(id);
  const imgs=[...document.querySelectorAll('#tab3-grid .thumb-item img')];
  return JSON.stringify({
    ready: document.readyState,
    bridge: !!(window.pywebview && window.pywebview.api),
    title: document.title,
    main_active: !!document.querySelector('#view-main.active'),
    tabs: [...document.querySelectorAll('#tabs .tab')].map(e=>(e.textContent||'').trim()),
    brand: (g('brand-title')?g('brand-title').textContent:'') + ' | ' + (g('topbar-title')?g('topbar-title').textContent:''),
    nodes: {
      grid: !!g('tab3-grid'), subdirs: !!g('tab3-subdirs'), view_btns: document.querySelectorAll('#tab3-views .view-btn').length,
      pageinfo: !!g('tab3-pageinfo'), pager: !!(g('btn-tab3-prev') && g('btn-tab3-next')),
      edit_pane: !!g('tab3-edit'), inputs: ['tab3-shiwen','tab3-dynasty','tab3-author'].filter(id=>!!g(id)).length,
      counts: !!g('tab3-counts'), newname: !!g('tab3-newname'), rename_btn: !!g('btn-tab3-rename'),
      preview: !!g('tab3-preview'), log_body: !!g('tab3-log-body'), log_badge: !!g('tab3-log-badge')
    },
    notice_in_edit: (document.querySelector('#tab3-edit .notice')||{}).textContent || '',
    badge_text: (g('tab3-log-badge')||{}).textContent || '',
    body_len: (document.body.innerText||'').length,
    grid_items: document.querySelectorAll('#tab3-grid .thumb-item').length,
    grid_imgs_loaded: imgs.filter(i=>i.complete && i.naturalWidth>0).length
  }); })()
"""

JS_LOGO = """
(() => { const g=id=>document.getElementById(id);
  const b=g('brand-logo'), t=g('topbar-logo');
  const link=document.querySelector('link[rel="icon"]');
  const box = el => el ? {complete: el.complete, nw: el.naturalWidth, nh: el.naturalHeight,
                          src: el.getAttribute('src'), cur_src: el.currentSrc} : null;
  return JSON.stringify({
    brand_logo: box(b), topbar_logo: box(t),
    brand_logo_visible: b ? (getComputedStyle(b).display !== 'none' && b.getBoundingClientRect().width > 0) : false,
    icon_link_href: link ? link.getAttribute('href') : null,
    icon_link_abs: link ? link.href : null,
    svg_icon_link: !!document.querySelector('link[rel="alternate icon"]'),
    apple_touch_link: !!document.querySelector('link[rel="apple-touch-icon"]'),
    page_url: location.href,
    out_of_root_probe: window.__probe404 || 'pending'
  }); })()
"""

JS_GRID = """
(() => { const g=id=>document.getElementById(id);
  const grid=g('tab3-grid');
  const items=[...document.querySelectorAll('#tab3-grid .thumb-item')];
  const imgs=[...document.querySelectorAll('#tab3-grid .thumb-item img')];
  const cols = grid ? getComputedStyle(grid).gridTemplateColumns.trim().split(/\\s+/).length : 0;
  const sel = document.querySelector('#tab3-grid .thumb-item.selected');
  return JSON.stringify({
    view: grid ? grid.dataset.view : '', cols: cols,
    view_btns: [...document.querySelectorAll('#tab3-views .view-btn')].map(b=>b.dataset.view+(b.classList.contains('active')?'*':'')),
    items: items.length,
    names: items.slice(0,26).map(e=>e.dataset.name),
    imgs: imgs.length, imgs_loaded: imgs.filter(i=>i.complete&&i.naturalWidth>0).length,
    img_src_head: imgs.length ? imgs[0].src.slice(0,24) : '',
    img_dims: imgs.slice(0,3).map(i=>i.naturalWidth+'x'+i.naturalHeight),
    selected: sel ? sel.dataset.name : '',
    pageinfo: g('tab3-pageinfo').textContent, pageno: g('tab3-pageno').textContent,
    prev_disabled: g('btn-tab3-prev').disabled, next_disabled: g('btn-tab3-next').disabled,
    subdir_buttons: [...document.querySelectorAll('#tab3-subdirs button')].map(b=>b.textContent.trim()+(b.classList.contains('active')?'*':'')),
    msg: g('tab3-msg').textContent
  }); })()
"""

JS_PANEL = """
(() => { const g=id=>document.getElementById(id);
  const pv=g('tab3-preview');
  return JSON.stringify({
    edit_hidden: g('tab3-edit').hidden, noselect_hidden: g('tab3-noselect').hidden,
    current: g('tab3-current').textContent,
    shiwen: g('tab3-shiwen').value, dynasty: g('tab3-dynasty').value, author: g('tab3-author').value,
    counts: g('tab3-counts').textContent, newname: g('tab3-newname').textContent,
    valid: g('tab3-valid').textContent, rename_disabled: g('btn-tab3-rename').disabled,
    parsed: g('tab3-parsed').textContent,
    preview_src_head: (pv.getAttribute('src')||'').slice(0,24),
    preview_loaded: !!(pv.complete && pv.naturalWidth>0), preview_dims: pv.naturalWidth+'x'+pv.naturalHeight,
    rename_msg: g('tab3-rename-msg').textContent
  }); })()
"""

JS_LOG = """
(() => { const g=id=>document.getElementById(id);
  const rows=[...document.querySelectorAll('#tab3-log-body tr')];
  return JSON.stringify({
    rows: rows.length,
    first: rows.length ? [...rows[0].querySelectorAll('td')].map(td=>td.textContent) : [],
    path: g('tab3-log-path').textContent, badge: g('tab3-log-badge').textContent
  }); })()
"""

#: OCR 试试看 ＋ 纠错建议面板（右栏，渲染后读数）
JS_OCR = """
(() => { const g=id=>document.getElementById(id);
  const out=g('tab3-ocr-out'), corr=g('tab3-corr'), raw=g('tab3-ocr-raw');
  const btn=g('btn-tab3-ocr');
  return JSON.stringify({
    btn_exists: !!btn, btn_disabled: btn ? btn.disabled : null,
    out_hidden: out ? out.hidden : null,
    hint: g('tab3-ocr-hint') ? g('tab3-ocr-hint').textContent : '',
    raw: raw ? raw.textContent : '', segs: raw ? raw.querySelectorAll('.seg').length : 0,
    corr_hidden: corr ? corr.hidden : null,
    corr_head: g('tab3-corr-head') ? g('tab3-corr-head').textContent : '',
    corr_items: g('tab3-corr-list')
      ? [...g('tab3-corr-list').querySelectorAll('.corr-item')].map(e=>e.textContent) : [],
    apply_disabled: g('btn-tab3-corr-apply') ? g('btn-tab3-corr-apply').disabled : null,
    auto_checked: g('tab3-corr-auto') ? g('tab3-corr-auto').checked : null,
    shiwen: g('tab3-shiwen') ? g('tab3-shiwen').value : '',
    msg: g('tab3-ocr-msg') ? g('tab3-ocr-msg').textContent : ''
  }); })()
"""


def _probe_body() -> None:
    # 等页面 + 桥 + 会话恢复（boot() 里 250 ms 轮询 session_state）
    _wait_js("!!(document.readyState==='complete' && window.pywebview && window.pywebview.api)", 30)
    _wait_js("!!document.querySelector('#view-main.active') && !!document.getElementById('tabs')", 30)
    time.sleep(1.0)
    base = _read("01_initial", JS_READY)
    record("dom/loaded_title_and_brand",
           base.get("title") == APP_TITLE and APP_TITLE in (base.get("brand") or ""),
           f"document.title={base.get('title')!r} brand={base.get('brand')!r}（真源 api.APP_TITLE）")
    record("dom/three_tabs_rendered",
           base.get("tabs") == ["1_Original_PDF", "2_HighRes_PDF", "3_Cropped_Tiff"] and base.get("main_active"),
           f"tabs={base.get('tabs')} main_active={base.get('main_active')} bridge={base.get('bridge')}")
    nodes = base.get("nodes") or {}
    record("dom/tab3_nodes_present",
           bool(nodes.get("grid")) and bool(nodes.get("subdirs")) and nodes.get("view_btns") == 4
           and bool(nodes.get("pageinfo")) and bool(nodes.get("pager")) and bool(nodes.get("edit_pane"))
           and nodes.get("inputs") == 3 and bool(nodes.get("counts")) and bool(nodes.get("newname"))
           and bool(nodes.get("rename_btn")) and bool(nodes.get("preview")) and bool(nodes.get("log_body")),
           f"nodes={nodes}")
    record("dom/cloud_api_note_visible",
           ("腾讯文档" in (base.get("notice_in_edit") or "") and "未接入" in (base.get("notice_in_edit") or ""))
           and ("暂未接入" in (base.get("badge_text") or "")),
           f"编辑区提示={base.get('notice_in_edit')[:60]!r} 日志徽标={base.get('badge_text')[:40]!r}")

    # ── ⓪ 品牌区 logo（仓内 feicui.png 的 ui/ 副本）+ rel=icon：**真加载**断言 ──
    _ev("(() => { window.__probe404=null; const im=new Image();"
        "im.onload=()=>{window.__probe404='loaded('+im.naturalWidth+'x'+im.naturalHeight+')';};"
        "im.onerror=()=>{window.__probe404='error(404/不可达)';};"
        "im.src='../assets/feicui.png'; return 1; })()")   # server 根＝ui/ ⇒ 越根路径探针
    time.sleep(1.5)
    lg = _read("00_logo", JS_LOGO)
    bl, tl = lg.get("brand_logo") or {}, lg.get("topbar_logo") or {}
    # 品牌区 img 在**登录视图**里（探针时 view-main 处于 active ⇒ 该视图 display:none ⇒ rect 宽 0）
    # ⇒ 临时切到 view-login 量一次真实盒模型，随后**原样还原**视图状态
    box = _read("00b_brand_logo_box",
                "(() => { const l=document.getElementById('view-login'), m=document.getElementById('view-main');"
                "const was=l.classList.contains('active'); l.classList.add('active'); m.classList.remove('active');"
                "const el=document.getElementById('brand-logo'); const r=el.getBoundingClientRect();"
                "const cs=getComputedStyle(el);"
                "if(!was){ l.classList.remove('active'); m.classList.add('active'); }"
                "return JSON.stringify({w:Math.round(r.width), h:Math.round(r.height), display:cs.display,"
                "view_login_active_after: document.getElementById('view-login').classList.contains('active')}); })()")
    tbox = _read("00c_topbar_logo_box",
                 "(() => { const el=document.getElementById('topbar-logo'); const r=el.getBoundingClientRect();"
                 "return JSON.stringify({w:Math.round(r.width), h:Math.round(r.height)}); })()")
    record("dom/brand_logo_really_loaded",
           bl.get("complete") is True and int(bl.get("nw") or 0) == 480 and int(bl.get("nh") or 0) == 480
           and tl.get("complete") is True and int(tl.get("nw") or 0) == 480
           and int(box.get("w") or 0) > 0 and int(box.get("h") or 0) > 0
           and int(tbox.get("w") or 0) > 0,
           f"品牌区 img: complete={bl.get('complete')} naturalWidth×Height={bl.get('nw')}×{bl.get('nh')} "
           f"真实盒={box.get('w')}×{box.get('h')}px（display={box.get('display')}，量完已还原视图） "
           f"src={bl.get('src')!r} currentSrc={bl.get('cur_src')!r}；顶栏 img: {tl.get('nw')}×{tl.get('nh')} "
           f"盒={tbox.get('w')}×{tbox.get('h')}px")
    record("dom/icon_links_and_server_root",
           lg.get("icon_link_href") == "feicui.png" and lg.get("svg_icon_link") is True
           and "://127.0.0.1" in (lg.get("page_url") or "") and lg.get("apple_touch_link") is True,
           f"rel=icon href={lg.get('icon_link_href')!r} abs={lg.get('icon_link_abs')!r} "
           f"svg link={lg.get('svg_icon_link')} apple-touch={lg.get('apple_touch_link')} "
           f"page_url={lg.get('page_url')!r} ⇒ server 根＝ui/")
    record("dom/out_of_root_path_unreachable",
           "error" in str(lg.get("out_of_root_probe")),
           f"`../assets/feicui.png` 探针结果={lg.get('out_of_root_probe')!r}"
           f"（故图标**复制**进 ui/，与「assets 用复制不用软链」口径一致）")

    # ── ① 点开 tab3 ⇒ 缩略图真出图 ──
    _ev("document.querySelector('#tabs .tab[data-tab=\"3_Cropped_Tiff\"]').click()")
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length > 0", 25)
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item img').length > 0", 25)
    time.sleep(0.8)
    g1 = _read("02_grid_default", JS_GRID)
    record("dom/tab3_thumb_grid_rendered",
           g1.get("items") == 4 and g1.get("imgs") == 4 and g1.get("imgs_loaded") == 4,
           f"子目录 {g1.get('subdir_buttons')} items={g1.get('items')} imgs={g1.get('imgs')} "
           f"loaded={g1.get('imgs_loaded')} dims={g1.get('img_dims')}")
    record("dom/thumbs_are_inline_png_datauri",
           (g1.get("img_src_head") or "").startswith("data:image/png;base64,"),
           f"img.src 头={g1.get('img_src_head')}…（3_Cropped_Tiff 在 ui/ 静态根外 ⇒ 走 base64，与旧版一致）")
    record("dom/grid_view_cfg_shown",
           "视图 medium" in (g1.get("pageinfo") or "") and g1.get("cols") == 10,
           f"pageinfo={g1.get('pageinfo')!r} 网格列数={g1.get('cols')}")

    # ── ② 四档视图（列数 + 分页口径）──
    view_seen: dict = {}
    for v, want_cols in (("large", 5), ("medium", 10), ("small", 20), ("list", 1)):
        _ev(f"document.querySelector('#tab3-views .view-btn[data-view=\"{v}\"]').click()")
        time.sleep(1.2)
        r = _read(f"03_view_{v}", JS_GRID)
        view_seen[v] = {"cols": r.get("cols"), "items": r.get("items"), "loaded": r.get("imgs_loaded"),
                        "view": r.get("view"), "pageno": r.get("pageno"), "src_ok": (r.get("img_src_head") or "").startswith("data:image/png;base64,")}
    record("dom/four_views_cols",
           all(view_seen[v]["cols"] == c for v, c in (("large", 5), ("medium", 10), ("small", 20), ("list", 1)))
           and all(view_seen[v]["view"] == v for v in view_seen)
           and all(view_seen[v]["loaded"] >= 4 for v in view_seen),
           f"四档实测 cols/items/loaded={json.dumps(view_seen, ensure_ascii=False)}")

    # ── ③ 缩略图点击选中 ⇒ 右栏输入框出现且**预填**（解析回填）──
    _ev("document.querySelector('#tab3-grid .thumb-item[data-name=\"P001-C2-R3-长乐未央-汉-陈巨来.tiff\"]').click()")
    time.sleep(2.0)
    p1 = _read("04_after_select", JS_PANEL)
    record("dom/select_file_shows_panel_prefilled",
           p1.get("edit_hidden") is False and p1.get("shiwen") == "长乐未央"
           and p1.get("dynasty") == "汉" and p1.get("author") == "陈巨来",
           f"edit 显示={p1.get('edit_hidden') is False} 三输入框={p1.get('shiwen')!r}/{p1.get('dynasty')!r}/{p1.get('author')!r} "
           f"解析提示={p1.get('parsed')!r}")
    record("dom/big_preview_rendered",
           p1.get("preview_loaded") is True and (p1.get("preview_src_head") or "").startswith("data:image/png;base64,"),
           f"大图 dims={p1.get('preview_dims')} src 头={p1.get('preview_src_head')}…")
    record("dom/noop_name_greys_button",
           p1.get("rename_disabled") is True and "未变化" in (p1.get("valid") or ""),
           f"新名={p1.get('newname')!r} 按钮禁用={p1.get('rename_disabled')} 理由={p1.get('valid')!r}")

    # ── ④ 释文超限 ⇒ 计数 + 错误原文 + 按钮置灰（渲染后校验）──
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); e.value='一二三四五六七八九十十';"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    time.sleep(1.2)
    p2 = _read("05_over_limit", JS_PANEL)
    record("dom/over_limit_blocks_rename",
           p2.get("rename_disabled") is True and "最多 10 个汉字" in (p2.get("valid") or "")
           and "11/10" in (p2.get("counts") or ""),
           f"计数={p2.get('counts')!r} 错误原文={p2.get('valid')!r} 新名={p2.get('newname')!r}")

    # ── ⑤ 同名冲突 ⇒ 拒止（按钮仍灰 + 原文提示）──
    _ev("(() => { const s=document.getElementById('tab3-shiwen'); s.value='乙';"
        "s.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    _ev("document.querySelector('#tab3-grid .thumb-item[data-name=\"P005-C1-R1-待定-汉-丙.tiff\"]').click()")
    time.sleep(1.5)
    _ev("(() => { const s=document.getElementById('tab3-shiwen'); s.value='乙';"
        "s.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    time.sleep(1.2)
    p3 = _read("06_conflict", JS_PANEL)
    record("dom/conflict_rejected_in_ui",
           p3.get("rename_disabled") is True and "同目录已存在" in (p3.get("valid") or ""),
           f"新名={p3.get('newname')!r} 错误原文={p3.get('valid')!r} 按钮禁用={p3.get('rename_disabled')}")

    # ── ⑥ 真点「执行重命名」（非合规件 ⇒ 前缀留空，与旧版一致）──
    _ev("document.querySelector('#tab3-grid .thumb-item[data-name=\"未命名副本.tiff\"]').click()")
    time.sleep(1.5)
    _ev("(() => { const v={'tab3-shiwen':'清心','tab3-dynasty':'宋','tab3-author':'齐白石'};"
        "Object.keys(v).forEach(function(id){const e=document.getElementById(id);"
        "e.value=v[id]; e.dispatchEvent(new Event('input',{bubbles:true}));}); return 1; })()")
    time.sleep(1.3)
    p4 = _read("07_ready_to_rename", JS_PANEL)
    record("dom/valid_state_enables_button",
           p4.get("rename_disabled") is False and (p4.get("newname") or "") == "清心-宋-齐白石.tiff",
           f"新名预览={p4.get('newname')!r} 按钮可点={p4.get('rename_disabled') is False} 计数={p4.get('counts')!r}")
    _ev("document.getElementById('btn-tab3-rename').click()")
    time.sleep(2.0)
    # 结果提示是桥回调里异步写入的 ⇒ 短窗轮询抓一次（抓到即止）
    msg_seen = ""
    t_msg = time.time()
    while time.time() - t_msg < 6 and not msg_seen:
        v = _ev("document.getElementById('tab3-rename-msg').textContent")
        if isinstance(v, str) and v.strip():
            msg_seen = v
        else:
            time.sleep(0.3)
    _wait_js("!!document.querySelector('#tab3-grid .thumb-item[data-name=\"清心-宋-齐白石.tiff\"]')", 20)
    time.sleep(1.0)
    g2 = _read("08_after_rename_grid", JS_GRID)
    p5 = _read("09_after_rename_panel", JS_PANEL)
    lg = _read("10_local_log", JS_LOG)
    record("dom/rename_via_button_refreshed_grid",
           "清心-宋-齐白石.tiff" in (g2.get("names") or [])
           and "未命名副本.tiff" not in (g2.get("names") or [])
           and g2.get("selected") == "清心-宋-齐白石.tiff",
           f"选中={g2.get('selected')!r} names={g2.get('names')} 缩略图 loaded={g2.get('imgs_loaded')}")
    record("dom/rename_msg_marks_cloud_not_connected",
           "cloud_log=not_connected" in (msg_seen or "")
           and "cloud_lock=not_connected" in (msg_seen or ""),
           f"rename 提示（抓到的原文）={msg_seen[:130]!r}")
    record("dom/local_log_row_visible",
           lg.get("rows") == 1 and "清心-宋-齐白石.tiff" in " ".join(lg.get("first") or [])
           and "rename_log.jsonl" in (lg.get("path") or "") and "暂未接入" in (lg.get("badge") or ""),
           f"行数={lg.get('rows')} 首行={lg.get('first')} 路径={ (lg.get('path') or '')[:90]!r}")

    # ── ⑦ 分页 + 方向键（分页B：25 个 ⇒ large 档 20/页 ⇒ 2 页）──
    _ev("(() => { const b=[...document.querySelectorAll('#tab3-subdirs button')].find(x=>/分页B/.test(x.textContent)); b.click(); return 1; })()")
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length >= 20", 25)
    _ev("document.querySelector('#tab3-views .view-btn[data-view=\"large\"]').click()")
    time.sleep(1.5)
    pa = _read("11_page1", JS_GRID)
    _ev("document.getElementById('btn-tab3-next').click()")
    time.sleep(1.5)
    pb = _read("12_page2", JS_GRID)
    record("dom/pagination_20_per_page",
           pa.get("items") == 20 and pa.get("pageno") == "1 / 2" and pa.get("next_disabled") is False
           and pb.get("items") == 5 and pb.get("pageno") == "2 / 2" and pb.get("next_disabled") is True,
           f"第1页 items={pa.get('items')} pageno={pa.get('pageno')} / 第2页 items={pb.get('items')} "
           f"pageno={pb.get('pageno')} next禁用={pb.get('next_disabled')}")
    _ev("document.getElementById('btn-tab3-prev').click()")
    time.sleep(1.0)
    _ev("document.querySelector('#tab3-grid .thumb-item').click()")
    time.sleep(1.5)
    before = _read("13_kbd_before", JS_GRID).get("selected")
    _ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))")
    time.sleep(1.5)
    r_after = _read("14_kbd_right", JS_GRID)
    _ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))")
    time.sleep(1.5)
    d_after = _read("15_kbd_down", JS_GRID)
    names = r_after.get("names") or []
    b_idx = names.index(before) if before in names else -1
    idx_r = names.index(r_after.get("selected")) if r_after.get("selected") in names else -1
    idx_d = names.index(d_after.get("selected")) if d_after.get("selected") in names else -1
    record("dom/keyboard_nav_moves_selection",
           b_idx >= 0 and idx_r == b_idx + 1 and idx_d == idx_r + 5,
           f"起点={before!r}（idx {b_idx}）→→ {r_after.get('selected')!r}（idx {idx_r}，右=+1）"
           f" →↓ {d_after.get('selected')!r}（idx {idx_d}，large 档列数 5 ⇒ +5；list 档列数 1 ⇒ 等价旧版 ±1）")

    # ── ⑧ 生成测试 TIFF（管理员按钮真点）──
    _ev("(() => { const b=[...document.querySelectorAll('#tab3-subdirs button')].find(x=>/A特例/.test(x.textContent)); b.click(); return 1; })()")
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length >= 3", 25)
    time.sleep(0.8)
    g_pre = _read("16_before_generate", JS_GRID)
    gen_state = _ev("(() => { const b=document.getElementById('btn-tab3-test');"
                    "const dis=b.disabled; b.click(); return JSON.stringify({disabled:dis}); })()")
    time.sleep(3.0)
    g_post = _read("17_after_generate", JS_GRID)
    gd = {}
    try:
        gd = json.loads(gen_state or "{}")
    except Exception:
        gd = {}
    record("dom/generate_test_tiff_button",
           gd.get("disabled") is False
           and int(g_post.get("items") or 0) == int(g_pre.get("items") or 0) + 1
           and len(g_post.get("names") or []) == int(g_post.get("items") or 0),
           f"管理员按钮 disabled={gd.get('disabled')} "
           f"items {g_pre.get('items')}→{g_post.get('items')} msg={g_post.get('msg')!r}")

    # ── ⑨ OCR 试试看 ＋ 纠错建议（真后端跑一次 ⇒ 再注入假结果验交互逻辑）──
    _ev("document.querySelector('#tab3-grid .thumb-item[data-name=\\\"P001-C2-R3-长乐未央-汉-陈巨来.tiff\\\"]').click()")
    time.sleep(1.8)
    ocr0 = _read("18_ocr_before_click", JS_OCR)
    record("dom/ocr_button_present_and_enabled",
           ocr0.get("btn_exists") is True and ocr0.get("btn_disabled") is False
           and ocr0.get("out_hidden") is True and ocr0.get("corr_hidden") is True,
           f"按钮存在={ocr0.get('btn_exists')} 可点={ocr0.get('btn_disabled') is False} "
           f"结果面板初始隐藏={ocr0.get('out_hidden')} 纠错面板初始隐藏={ocr0.get('corr_hidden')} "
           f"auto 默认勾选={ocr0.get('auto_checked')}")

    # ⑨a 真后端：清空释文框 ⇒ 点按钮 ⇒ 等桥回来（**按钮必须复原**）
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); e.value='';"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    _ev("document.getElementById('btn-tab3-ocr').click()")
    _wait_js("(document.getElementById('tab3-ocr-msg').textContent || '').indexOf('正在识别') !== 0"
             " && (document.getElementById('tab3-ocr-msg').textContent || '').length > 0", 40)
    _wait_js("document.getElementById('btn-tab3-ocr').disabled === false", 20)
    time.sleep(0.6)
    ocr1 = _read("19_ocr_real_backend", JS_OCR)
    real_ok = (ocr1.get("btn_disabled") is False
               and ((ocr1.get("out_hidden") is False
                     and "不可靠" in (ocr1.get("hint") or "")
                     and "仅供参考" in (ocr1.get("hint") or ""))
                    or (ocr1.get("out_hidden") is True and bool(ocr1.get("msg")))))
    record("dom/ocr_real_backend_structured_and_button_restored", bool(real_ok),
           f"真后端读数：结果面板隐藏={ocr1.get('out_hidden')} 段数={ocr1.get('segs')} "
           f"释文框={ocr1.get('shiwen')!r} 提示={ (ocr1.get('msg') or '')[:60]!r} "
           f"按钮复原={ocr1.get('btn_disabled') is False} "
           f"诚实提示含「不可靠/仅供参考」={'不可靠' in (ocr1.get('hint') or '')}")
    FIXTURE_INFO["ocr_real_backend"] = {"shiwen": ocr1.get("shiwen"), "segs": ocr1.get("segs"),
                                        "hint_head": (ocr1.get("hint") or "")[:80],
                                        "msg": ocr1.get("msg")}

    # ⑨b 注入假 OCR 结果（只替换 tab3_ocr，tab3_correct 走真后端 ⇒ 纠错面板是真读数）
    inj = _ev("""(() => {
      window.__realTab3Ocr = window.pywebview.api.tab3_ocr;
      window.__fakeOcr = {ok:true, texts:['左軍丞錄'], scores:[0.91], text:'左軍丞錄',
        elapsed_s:0.12, engine:'FAKE-ENGINE（注入）', mean_score:0.91, n:1,
        hint:'印面篆书通用 OCR 不可靠、仅供参考：注入的测试读数'};
      window.pywebview.api.tab3_ocr = function(){ return Promise.resolve(window.__fakeOcr); };
      return JSON.stringify({injected: window.pywebview.api.tab3_ocr !== window.__realTab3Ocr});
    })()""")
    injd = {}
    try:
        injd = json.loads(inj or "{}")
    except Exception:
        injd = {}
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); e.value='';"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    _ev("document.getElementById('btn-tab3-ocr').click()")
    _wait_js("document.getElementById('tab3-shiwen').value === '左軍丞錄'"
             " && document.getElementById('tab3-ocr-out').hidden === false", 25)
    _wait_js("document.getElementById('tab3-corr').hidden === false", 25)
    time.sleep(0.5)
    ocr2 = _read("20_ocr_fake_filled", JS_OCR)
    record("dom/ocr_fills_empty_shiwen_only",
           injd.get("injected") is True and ocr2.get("shiwen") == "左軍丞錄"
           and "已填入释文框" in (ocr2.get("msg") or ""),
           f"假结果已注入={injd.get('injected')} 释文框={ocr2.get('shiwen')!r} "
           f"提示={ocr2.get('msg')!r}")
    record("dom/ocr_honest_hint_rendered",
           "印面" in (ocr2.get("hint") or "") and "不可靠" in (ocr2.get("hint") or "")
           and "仅供参考" in (ocr2.get("hint") or ""),
           f"诚实提示原文={ (ocr2.get('hint') or '')[:90]!r}")
    record("dom/ocr_raw_text_and_scores_rendered",
           "左軍丞錄" in (ocr2.get("raw") or "") and "分数 0.9100" in (ocr2.get("raw") or "")
           and "FAKE-ENGINE" in (ocr2.get("raw") or ""),
           f"原识别文本+分数区={ (ocr2.get('raw') or '')[:120]!r} 段数={ocr2.get('segs')}")
    record("dom/corrector_panel_shown_with_hit",
           ocr2.get("corr_hidden") is False and ocr2.get("apply_disabled") is False
           and any("錄" in it and "鈢" in it for it in (ocr2.get("corr_items") or []))
           and "已核定" in (ocr2.get("corr_head") or ""),
           f"面板显示={ocr2.get('corr_hidden') is False} 标题={ocr2.get('corr_head')!r} "
           f"条目={ocr2.get('corr_items')}")

    # ⑨c 释文框非空 ⇒ 不覆盖；且无命中时纠错面板**静默隐藏**
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); e.value='长乐';"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    _ev("document.getElementById('btn-tab3-ocr').click()")
    _wait_js("(document.getElementById('tab3-ocr-msg').textContent || '').indexOf('未覆盖') >= 0", 25)
    time.sleep(0.8)
    ocr3 = _read("21_ocr_nonempty_not_overwritten", JS_OCR)
    record("dom/ocr_does_not_overwrite_nonempty",
           ocr3.get("shiwen") == "长乐" and "未覆盖" in (ocr3.get("msg") or ""),
           f"释文框保持={ocr3.get('shiwen')!r} 提示={ocr3.get('msg')!r}")
    record("dom/corrector_panel_hidden_when_no_hits",
           ocr3.get("corr_hidden") is True and not (ocr3.get("corr_items") or []),
           f"无命中时面板隐藏={ocr3.get('corr_hidden')} 条目={ocr3.get('corr_items')}"
           f"（不显示空面板）")

    # ⑨d 「全部应用」⇒ **只改输入框**（文件不动）：再注一次 左軍丞錄，然后点应用
    _ev("(() => { const e=document.getElementById('tab3-shiwen'); e.value='';"
        "e.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()")
    _ev("document.getElementById('btn-tab3-ocr').click()")
    _wait_js("document.getElementById('tab3-corr').hidden === false"
             " && document.getElementById('tab3-shiwen').value === '左軍丞錄'", 25)
    time.sleep(0.4)
    _ev("document.getElementById('btn-tab3-corr-apply').click()")
    time.sleep(1.2)
    ocr4 = _read("22_after_apply_all", JS_OCR)
    g_after_apply = _read("23_grid_after_ocr_apply", JS_GRID)
    record("dom/corrector_apply_all_changes_input_only",
           ocr4.get("shiwen") == "左軍丞鈢" and ocr4.get("corr_hidden") is True
           and "已应用 1/1" in (ocr4.get("msg") or "")
           and "P001-C2-R3-长乐未央-汉-陈巨来.tiff" in (g_after_apply.get("names") or []),
           f"应用后释文框={ocr4.get('shiwen')!r} 面板收起={ocr4.get('corr_hidden')} "
           f"提示={ocr4.get('msg')!r} 网格文件名未变（未重命名）="
           f"{'P001-C2-R3-长乐未央-汉-陈巨来.tiff' in (g_after_apply.get('names') or [])}")

    # ⑨e 失败路径：结构化 {ok:false} ⇒ 提示错误 + 按钮复原（不得抛到 UI / 按钮卡死）
    _ev("""(() => { window.pywebview.api.tab3_ocr = function(){
        return Promise.resolve({ok:false, msg:'注入故障：OCR 引擎不可用'}); }; return 1; })()""")
    _ev("document.getElementById('btn-tab3-ocr').click()")
    _wait_js("(document.getElementById('tab3-ocr-msg').textContent || '').indexOf('注入故障') >= 0", 25)
    time.sleep(0.5)
    ocr5 = _read("24_ocr_failure_path", JS_OCR)
    record("dom/ocr_failure_structured_and_button_restored",
           "注入故障" in (ocr5.get("msg") or "") and ocr5.get("out_hidden") is True
           and ocr5.get("btn_disabled") is False and ocr5.get("corr_hidden") is True,
           f"错误提示={ocr5.get('msg')!r} 结果面板隐藏={ocr5.get('out_hidden')} "
           f"按钮复原={ocr5.get('btn_disabled') is False} 纠错面板隐藏={ocr5.get('corr_hidden')}")

    _ev("(() => { window.pywebview.api.tab3_ocr = window.__realTab3Ocr; return 1; })()")   # 还原桥

    # ── ⑩ 能力闸：模拟「本版不含 OCR 引擎」（阶段 1 包 s1）⇒ 刷新后按钮**先置灰** + 常驻可读提示 ──
    _ev("""(() => {
      window.__realTab3List = window.pywebview.api.tab3_list;
      window.pywebview.api.tab3_list = function(p){
        return window.__realTab3List(p || {}).then(function(r){
          r.ocr_available = false; r.ocr_note = '本版本未内置 OCR 引擎（注入模拟 s1 包）';
          return r;
        }); };
      return 1; })()""")
    _ev("document.getElementById('btn-tab3-refresh').click()")
    _wait_js("document.getElementById('btn-tab3-ocr').disabled === true", 25)
    time.sleep(0.8)
    ocr6 = _read("25_ocr_unavailable_gate", JS_OCR)
    _ev("document.getElementById('btn-tab3-ocr').click()")     # 置灰按钮点了不得有任何动静
    time.sleep(0.6)
    ocr6b = _read("26_ocr_unavailable_click_noop", JS_OCR)
    record("dom/ocr_button_disabled_when_engine_absent",
           ocr6.get("btn_disabled") is True and "未内置 OCR 引擎" in (ocr6.get("msg") or "")
           and ocr6.get("auto_checked") is False,
           f"按钮 disabled={ocr6.get('btn_disabled')} 提示={ocr6.get('msg')!r} "
           f"auto 复选框={ocr6.get('auto_checked')}（打开就置灰，不用点）")
    record("dom/ocr_disabled_click_is_noop",
           ocr6b.get("btn_disabled") is True and ocr6b.get("out_hidden") is True
           and "未内置 OCR 引擎" in (ocr6b.get("msg") or ""),
           f"点禁用按钮后：disabled={ocr6b.get('btn_disabled')} 结果面板隐藏={ocr6b.get('out_hidden')} "
           f"提示={ocr6b.get('msg')!r}（无异常、无假读数）")
    # 还原：拿回真 tab3_list ⇒ 再刷新一次，按钮必须恢复可点（不留下「永久禁用」）
    _ev("(() => { window.pywebview.api.tab3_list = window.__realTab3List; return 1; })()")
    _ev("document.getElementById('btn-tab3-refresh').click()")
    _wait_js("document.getElementById('btn-tab3-ocr').disabled === false", 25)
    time.sleep(0.6)
    ocr7 = _read("27_ocr_gate_restored", JS_OCR)
    record("dom/ocr_button_reenabled_when_engine_present",
           ocr7.get("btn_disabled") is False and "未内置" not in (ocr7.get("msg") or ""),
           f"还原后按钮 disabled={ocr7.get('btn_disabled')} 提示={ocr7.get('msg')!r}")


def probe() -> None:
    """pywebview 回调入口：**任何异常都不许吃掉后续步骤**；结束必关窗。"""
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


# ───────────────────────── main ─────────────────────────
def main(argv: list[str] | None = None) -> int:
    global WIN
    ap = argparse.ArgumentParser(description="斐萃 tab3 渲染后 DOM 断言（真窗口）")
    ap.add_argument("--out", default=str(READINGS))
    ap.add_argument("--watchdog", type=float, default=180.0)
    args = ap.parse_args(argv)

    root = build_fixture()
    FIXTURE_INFO.update({"scratch": str(SCRATCH), "fixture": str(root),
                         "data_dir": str(DATA_DIR),
                         "files": sum(1 for _ in root.rglob("*.tif*"))})
    api = FeicuiApi()
    vr = api.verify_dir({"path": str(root)})
    users = [u for u, v in api._users.items() if v["is_admin"]]
    if not vr.get("ok") or not users:
        print(f"FIXTURE_FAIL verify_dir={vr} admin_users={users}", flush=True)
        return 2
    lg = api.login({"username": users[0], "password": api._users[users[0]]["pwd"]})
    FIXTURE_INFO.update({"admin": users[0], "login_ok": bool(lg.get("ok")), "verify_msg": vr.get("msg")})

    webview, WIN = build_window(api)
    threading.Timer(args.watchdog, lambda: (RESULT.setdefault("watchdog", "fired"), WIN.destroy())).start()
    print(f"DOMTEST_START fixture={root} data_dir={DATA_DIR} window_title={WINDOW_TITLE!r}", flush=True)
    webview.start(probe)

    # ── 落盘面复核（Python 侧，与 DOM 读数互为证据）──
    post = {}
    a_dir = root / lib.TIFF_DIR / "A特例"
    post["renamed_exists"] = (a_dir / "清心-宋-齐白石.tiff").is_file()
    post["old_gone"] = not (a_dir / "未命名副本.tiff").exists()
    post["conflict_pair_intact"] = ((a_dir / "P005-C1-R1-待定-汉-丙.tiff").is_file()
                                    and (a_dir / "P005-C1-R1-乙-汉-丙.tiff").is_file())
    post["log_exists"] = RENAME_LOG.exists()
    rec = {}
    if RENAME_LOG.exists():
        lines = [ln for ln in RENAME_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
        post["log_lines"] = len(lines)
        rec = json.loads(lines[-1]) if lines else {}
    post["log_last"] = {k: rec.get(k) for k in ("old_filename", "new_filename", "operator",
                                                "印面释文", "朝代", "作者", "file_md5",
                                                "status", "cloud_log", "cloud_lock")}
    post["generated_files"] = sorted(p.name for p in a_dir.iterdir() if p.suffix.lower() in (".tif", ".tiff"))
    RESULT["post"] = post
    record("disk/renamed_and_logged",
           post["renamed_exists"] and post["old_gone"] and post["log_exists"] and post.get("log_lines") == 1
           and post["log_last"].get("new_filename") == "清心-宋-齐白石.tiff"
           and post["log_last"].get("operator") == users[0]
           and len(post["log_last"].get("file_md5") or "") == 32
           and post["log_last"].get("cloud_log") == CLOUD_LOG_STATUS
           and post["log_last"].get("cloud_lock") == "not_connected",
           f"改名后文件存在={post['renamed_exists']} 旧名已消失={post['old_gone']} "
           f"本地记录={post.get('log_lines')} 条 末条={post['log_last']}")
    record("disk/conflict_left_both_files",
           post["conflict_pair_intact"],
           f"A特例 现有文件={post['generated_files']}")
    # OCR「全部应用」只改输入框：被 OCR 的那件**文件名不变**（DOM 侧已断言网格名，这里再证盘面）
    post["ocr_apply_kept_filename"] = (a_dir / "P001-C2-R3-长乐未央-汉-陈巨来.tiff").is_file()
    record("disk/ocr_apply_did_not_rename_file", post["ocr_apply_kept_filename"],
           f"{'P001-C2-R3-长乐未央-汉-陈巨来.tiff'} 仍在盘上={post['ocr_apply_kept_filename']}"
           f"（纠错建议只落输入框，不触发重命名）")

    counts = {s: sum(1 for c in RESULT["checks"] if c["status"] == s) for s in ("PASS", "FAIL")}
    summary = {"schema": "feicui.webui.domtest.v1", "at": datetime.now().isoformat(timespec="seconds"),
               "python": sys.executable, "window_title": WINDOW_TITLE, "app_title": APP_TITLE,
               "counts": counts, "fixture": FIXTURE_INFO, "checks": RESULT["checks"],
               "dom": RESULT["dom"], "post": post}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== DOM 断言（渲染后实测）===")
    print(json.dumps({"counts": counts, "fixture": FIXTURE_INFO, "post": post},
                     ensure_ascii=False, indent=2))
    print(f"\n读数落盘：{out}")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
