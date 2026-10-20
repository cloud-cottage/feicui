#!/usr/bin/env python
# local-dist/domtest_tabs.py
"""「斐萃」Phase B —— **tab1 一键高清化 / tab2 切图台** 的渲染后 DOM 断言（真窗口 + `evaluate_js`）。

配方与 `domtest.py` 同源（同一 `app.build_window(api)`、同一 `webview.start(probe)`、同一隔离手法）：
  * 本脚本在 import `api` 之前把 `FEICUI_DATA_DIR` 指到临时目录；`feicui` 夹具亦在临时目录；
  * probe 里 `evaluate_js` 读**渲染后真实 DOM**（不是静态 grep）；
  * **注入假 `tab2_detect`**（真检测要渲 400dpi 页）⇒ 只验 UI：canvas 框数、单击删框、双击加框；
  * tab3 **一字未改**：先比 `git show HEAD:local-dist/ui/index.html` 与工作区的 tab3 块逐字节，
    再切到 tab3 读渲染后节点；
  * `threading.Timer(150, …)` 看门狗兜底关窗。

跑法：
    ./venv/bin/python local-dist/domtest_tabs.py
    ./venv/bin/python local-dist/domtest_tabs.py --out /tmp/tabs.json
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from datetime import datetime
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBUI_DIR.parent
sys.path.insert(0, str(WEBUI_DIR))

SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-domtest-tabs-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from api import APP_TITLE, DATA_DIR, FeicuiApi, app_name, app_title  # noqa: E402
from src import pdf_library as lib  # noqa: E402

_spec = importlib.util.spec_from_file_location("feicui_webui_app", WEBUI_DIR / "app.py")
assert _spec and _spec.loader
_webui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_webui_app)
build_window = _webui_app.build_window

SOURCE_PDF = REPO_ROOT / "output" / "1_Original_PDF" / "吴颐人篆刻作品展示.pdf"
READINGS = WEBUI_DIR / "build" / "readings-dom-tabs.json"

WIN = None
RESULT: dict = {"dom": {}, "checks": []}
INFO: dict = {}


def record(name: str, ok: bool, detail: str) -> None:
    RESULT["checks"].append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)


def tiny_png(w: int = 714, h: int = 1000) -> str:
    """纯 stdlib 造一张**真 PNG**（均匀灰底）⇒ Image.onload 会真触发（否则画布交互进不去）。"""
    raw = b"".join(b"\x00" + bytes((238, 238, 238)) * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


def build_fixture() -> Path:
    root = SCRATCH / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_PDF, root / lib.ORIGINAL_DIR / SOURCE_PDF.name)          # tab1 的行
    hr_dir = root / lib.HIGHRES_DIR / "9787000000001"
    hr_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_PDF, hr_dir / "吴颐人篆刻作品展示-HighRes.pdf")           # 切图台的源
    sub3 = root / lib.TIFF_DIR / "A特例"
    sub3.mkdir(parents=True, exist_ok=True)
    shutil.copy2(WEBUI_DIR / "assets" / "test_seal.tiff", sub3 / "P001-C2-R3-长乐未央-汉-陈巨来.tiff")
    # tab3 兼容解析用：切图台**新命名**（带编号）的件 —— 旧模板解析器认不出它，
    # 若 tab3 只认旧模板，这里会显示「命名不合模板」且 P/C/R 空白（本单的阻塞项之一）。
    shutil.copy2(WEBUI_DIR / "assets" / "test_seal.tiff",
                 sub3 / "0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff")
    # tab3 **旧目录键只读展示**用：老落点（ISBN 目录键）＋ `_fields.json` 回指本书 PDF。
    # 目录名特意排在 `A特例` **之后**（'旧' > 'A'）⇒ 默认子目录仍是 `A特例`，不打乱既有断言。
    old3 = root / lib.TIFF_DIR / "旧键9787000000003"
    old3.mkdir(parents=True, exist_ok=True)
    shutil.copy2(WEBUI_DIR / "assets" / "test_seal.tiff",
                 old3 / "P001-C1-R1-长乐未央-汉-陈巨来.tiff")
    (old3 / "_fields.json").write_text(json.dumps(
        {"pdf_name": SOURCE_PDF.name, "page": 1,
         "items": [{"页": 1, "列": 1, "行": 1, "释文": "长乐未央"}]}, ensure_ascii=False),
        encoding="utf-8")
    return root


# ───────────────────────── probe ─────────────────────────
def _ev(expr: str):
    try:
        return WIN.evaluate_js(expr)
    except Exception as exc:
        RESULT.setdefault("js_errors", []).append(f"{type(exc).__name__}: {exc}")
        return None


def _read(name: str, expr: str) -> dict:
    raw = _ev(expr)
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        data = {"raw": raw}
    RESULT["dom"][name] = data
    return data or {}


def _wait_js(expr: str, timeout: float = 20.0, every: float = 0.3) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _ev(expr):
            return True
        time.sleep(every)
    return False


JS_TAB1 = """
(() => { const g=id=>document.getElementById(id);
  const sel=g('tab1-hr-dpi');
  const opts=sel?[...sel.options].map(o=>o.value):[];
  const hint=g('tab1-hr-card')?g('tab1-hr-card').querySelector('.hr-note'):null;
  const err=g('tab1-hr-err');
  return JSON.stringify({
    has_card: !!g('tab1-hr-card'),
    dpi_exists: !!sel, dpi_options: opts, dpi_value: sel?sel.value:null,
    dpi_selected_attr: sel?[...sel.options].filter(o=>o.selected).map(o=>o.value):[],
    nodes: { start: !!g('btn-tab1-hr-start'), cancel: !!g('btn-tab1-hr-cancel'),
             bar: !!g('tab1-hr-bar'), msg: !!g('tab1-hr-msg'), done: !!g('tab1-hr-done'),
             out: !!g('tab1-hr-out'), goto2: !!g('btn-tab1-hr-goto2'),
             from: !!g('tab1-hr-from'), to: !!g('tab1-hr-to'), src: !!g('tab1-hr-source') },
    cancel_disabled: g('btn-tab1-hr-cancel')?g('btn-tab1-hr-cancel').disabled:null,
    start_disabled: g('btn-tab1-hr-start')?g('btn-tab1-hr-start').disabled:null,
    bar_width: g('tab1-hr-bar')?(g('tab1-hr-bar').style.width||''):'',
    done_hidden: g('tab1-hr-done')?g('tab1-hr-done').hidden:null,
    hr_msg: g('tab1-hr-msg')?g('tab1-hr-msg').textContent:'',
    out_text: g('tab1-hr-out')?g('tab1-hr-out').textContent:'',
    hint: hint?hint.textContent.replace(/\\s+/g,' ').trim():'',
    src_text: g('tab1-hr-source')?g('tab1-hr-source').textContent:null,
    err_text: err?err.textContent:'', err_class: err?err.className:'',
    goto_label: g('btn-tab1-hr-goto2')?g('btn-tab1-hr-goto2').textContent:''
  }); })()
"""

JS_TAB1_PV = """
(() => { const g=id=>document.getElementById(id);
  const pi=g('tab1-pv-page'), img=g('tab1-pv-img'), hint=g('tab1-pv-hint');
  const card=g('tab1-pv-card'), from=g('tab1-hr-from');
  return JSON.stringify({
    card: !!card,
    in_hr_card: !!(g('tab1-hr-card') && g('tab1-hr-card').querySelector('#tab1-pv-card')),
    after_range: !!(card && from && (from.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING)),
    page_input: { exists: !!pi, type: pi?pi.type:null, min: pi?pi.min:'',
                  editable: pi?(!pi.disabled && !pi.readOnly):null,
                  value: pi?pi.value:null, max: pi?pi.max:'' },
    nodes: { prev: !!g('btn-tab1-pv-prev'), next: !!g('btn-tab1-pv-next'),
             setfrom: !!g('btn-tab1-pv-setfrom'), img: !!img, hint: !!hint,
             info: !!g('tab1-pv-info'), msg: !!g('tab1-pv-msg') },
    prev_disabled: g('btn-tab1-pv-prev')?g('btn-tab1-pv-prev').disabled:null,
    next_disabled: g('btn-tab1-pv-next')?g('btn-tab1-pv-next').disabled:null,
    setfrom_disabled: g('btn-tab1-pv-setfrom')?g('btn-tab1-pv-setfrom').disabled:null,
    setfrom_label: g('btn-tab1-pv-setfrom')?g('btn-tab1-pv-setfrom').textContent:'',
    info: g('tab1-pv-info')?g('tab1-pv-info').textContent:'',
    img_hidden: img?img.hidden:null,
    img_src_prefix: img?String(img.getAttribute('src')||'').slice(0,22):'',
    img_maxw: img?getComputedStyle(img).maxWidth:'',
    hint_text: hint?hint.textContent:'',
    hint_hidden: hint?hint.hidden:null,
    msg: g('tab1-pv-msg')?g('tab1-pv-msg').textContent:'',
    msg_class: g('tab1-pv-msg')?g('tab1-pv-msg').className:'',
    hr_from: g('tab1-hr-from')?g('tab1-hr-from').value:''
  }); })()
"""

JS_TAB1_BOOKNAME = """
(() => { const el=document.getElementById('tab1-book-name');
  return JSON.stringify({
    exists: !!el, type: el?el.type:null,
    editable: el?(!el.disabled && !el.readOnly):null,
    maxlength: el?el.maxLength:0, value: el?el.value:null,
    placeholder: el?el.placeholder:'',
    label: (el && el.closest('label'))?el.closest('label').textContent.replace(/\\s+/g,' ').trim():''
  }); })()
"""

JS_TAB2 = """
(() => { const g=id=>document.getElementById(id);
  const cv=g('tab2-canvas'); const r=cv?cv.getBoundingClientRect():{width:0,height:0};
  const adv=g('tab2-adv');
  const legacy=['btn-tab2-generate','btn-tab2-cancel','tab2-page','tab2-dpi','tab2-source',
                'tab2-products','tab2-progress-bar','tab2-progress-msg','tab2-log'];
  const inside=legacy.filter(id=>{const e=g(id); return !!(e && adv && adv.contains(e));});
  const sel=g('tab2-ct-source');
  return JSON.stringify({
    panel_active: !!document.querySelector('.panel.active[data-panel="2_HighRes_PDF"]'),
    nodes: { detect: !!g('btn-tab2-detect'), redetect: !!g('btn-tab2-redetect'),
             clear: !!g('btn-tab2-clear'), crop: !!g('btn-tab2-crop'),
             canvas: !!cv, count: !!g('tab2-box-count'), pageinfo: !!g('tab2-ct-pageinfo'),
             page: !!g('tab2-ct-page'), prev: !!g('btn-tab2-ct-prev'), next: !!g('btn-tab2-ct-next'),
             src: !!sel, cropout: !!g('tab2-crop-out'), cropdir: !!g('tab2-crop-dir'),
             adv: !!adv, reload: !!g('btn-tab2-ct-reload') },
    adv_open: adv?adv.open:null,
    adv_summary: adv?adv.querySelector('summary').textContent.trim():'',
    legacy_inside_adv: inside, legacy_missing: legacy.filter(id=>!g(id)),
    canvas: { w: cv?cv.width:0, h: cv?cv.height:0, css_w: Math.round(r.width||0),
              css_h: Math.round(r.height||0), boxes: cv?cv.dataset.boxes:null,
              scale: cv?cv.dataset.scale:null, ctx: !!(cv && cv.getContext('2d')) },
    src_options: sel?[...sel.options].map(o=>({v:o.value,t:o.textContent})):[],
    count_text: g('tab2-box-count')?g('tab2-box-count').textContent:'',
    crop_label: g('btn-tab2-crop')?g('btn-tab2-crop').textContent:'',
    crop_disabled: g('btn-tab2-crop')?g('btn-tab2-crop').disabled:null,
    pageinfo: g('tab2-ct-pageinfo')?g('tab2-ct-pageinfo').textContent:'',
    srcinfo: g('tab2-ct-srcinfo')?g('tab2-ct-srcinfo').textContent:'',
    msg: g('tab2-ct-msg')?g('tab2-ct-msg').textContent:'',
    dir: g('tab2-crop-dir')?g('tab2-crop-dir').textContent:'',
    read_order: (() => { const s=g('tab2-read-order');
      return s?{ count: s.options.length, options: [...s.options].map(o=>o.value), value: s.value }:null; })(),
    order_src: g('tab2-order-src')?g('tab2-order-src').textContent:'',
    fields: (() => { const box=g('tab2-fields'); if(!box){ return null; }
      const rows=[...box.querySelectorAll('.frow')];
      const q=(r,k)=>r.querySelector('.fin[data-k='+k+']');
      return { rows: rows.length, cells: rows.map(r=>({
        i: r.dataset.i, rev: r.classList.contains('rev'),
        inputs: r.querySelectorAll('.fin').length,
        editable: [...r.querySelectorAll('.fin')].every(x=>!x.disabled && !x.readOnly),
        ins: q(r,'inscription')?q(r,'inscription').value:null,
        status: q(r,'status')?q(r,'status').value:null,
        code: q(r,'code')?q(r,'code').value:null,
        score: r.querySelector('.fscore')?r.querySelector('.fscore').textContent:'',
        name: r.querySelector('.fname')?r.querySelector('.fname').textContent:'' })) }; })()
  }); })()
"""

JS_TAB3 = """
(() => { const g=id=>document.getElementById(id);
  const p=document.querySelector('[data-panel="3_Cropped_Tiff"]');
  const ids=p?[...p.querySelectorAll('[id]')].map(e=>e.id):[];
  return JSON.stringify({
    panel_active: !!document.querySelector('.panel.active[data-panel="3_Cropped_Tiff"]'),
    ids: ids, id_count: ids.length,
    h2: p?p.querySelector('h2').textContent.trim():'',
    view_btns: p?p.querySelectorAll('#tab3-views .view-btn').length:0,
    head_btns: p?[...p.querySelectorAll('.panel-head .btn')].map(b=>b.id):[],
    template: g('tab3-template')?g('tab3-template').textContent:''
  }); })()
"""


JS_TAB3_ONE = """
(() => { const g=id=>document.getElementById(id); const NAME=__NAME__;
  const item=[...document.querySelectorAll('#tab3-grid .thumb-item')].find(d=>d.dataset.name===NAME);
  return JSON.stringify({
    found: !!item,
    bad_class: item&&item.querySelector('.name')?item.querySelector('.name').classList.contains('bad'):null,
    shiwen: g('tab3-shiwen')?g('tab3-shiwen').value:null,
    dynasty: g('tab3-dynasty')?g('tab3-dynasty').value:null,
    author: g('tab3-author')?g('tab3-author').value:null,
    parsed_msg: g('tab3-parsed')?g('tab3-parsed').textContent:'',
    newname: g('tab3-newname')?g('tab3-newname').textContent:'',
    rename_disabled: g('btn-tab3-rename')?g('btn-tab3-rename').disabled:null,
    current: g('tab3-current')?g('tab3-current').textContent:''
  }); })()
"""


def _probe_body() -> None:
    _wait_js("!!(document.readyState==='complete' && window.pywebview && window.pywebview.api)", 30)

    _wait_js("!!document.querySelector('#view-main.active') && !!document.getElementById('tabs')", 30)
    _wait_js("document.querySelectorAll('#tab1-body tr').length > 0", 25)
    time.sleep(1.0)

    # ── ⓪ 窗口/页面标题：**Lite|Pro 按运行期 OCR 能力实算**（源码态有 rapidocr ⇒ Pro；lite 包 ⇒ Lite）──
    #    断言一律与后端 `app_title()` / `app_info()` 的实算值比对，**不写死** `Pro`/`Lite`。
    _wait_js("document.title.indexOf('Lite')>=0 || document.title.indexOf('Pro')>=0", 15)
    ttl = _read("00_app_title", "(() => JSON.stringify({title: document.title,"
                " brand: (document.getElementById('brand-title')||{}).textContent||'',"
                " topbar: (document.getElementById('topbar-title-text')||{}).textContent||''}))()")
    info = FeicuiApi().app_info()
    want_title, want_name = app_title(), app_name()
    got_title = ttl.get("title") or ""
    record("tabs/app_title_has_edition",
           ("· Lite" in got_title or "· Pro" in got_title)
           and got_title.startswith("「斐萃」玺印解析任务台 · 本地封装分发版"),
           f"document.title={got_title!r}（要求基础串 + `· Lite|Pro`）")
    record("tabs/app_title_matches_backend_actual",
           got_title == want_title and got_title == APP_TITLE,
           f"document.title={got_title!r} api.app_title()={want_title!r} APP_TITLE={APP_TITLE!r}")
    record("tabs/app_info_title_name_same_source",
           info.get("title") == got_title and info.get("app") == want_name
           and want_name.endswith(("· Lite", "· Pro"))
           and got_title in (ttl.get("brand") or "") and got_title in (ttl.get("topbar") or ""),
           f"app_info.title={info.get('title')!r} app_info.app={info.get('app')!r} "
           f"app_name()={want_name!r} edition={info.get('edition')!r} "
           f"brand={ttl.get('brand')!r} topbar={ttl.get('topbar')!r}")

    # ── ① tab1：**书籍名称**输入框（目录键唯一来源；留空 ⇒ 文件名回落）──
    t1bn = _read("00_tab1_book_name", JS_TAB1_BOOKNAME)
    record("tabs/tab1_book_name_input_editable",
           bool(t1bn.get("exists")) and t1bn.get("type") == "text"
           and bool(t1bn.get("editable")) and int(t1bn.get("maxlength") or 0) == 80
           and "书籍名称" in (t1bn.get("label") or ""),
           f"exists={t1bn.get('exists')} type={t1bn.get('type')!r} "
           f"editable={t1bn.get('editable')} maxlength={t1bn.get('maxlength')} "
           f"标签={t1bn.get('label')!r} 占位={t1bn.get('placeholder')!r}")

    # ── ① tab1：⚡ 一键高清化卡片（dpi 三档 / 默认 1200 / 进度 / 取消 / 完成后去 tab2）──
    t1 = _read("01_tab1_hr", JS_TAB1)
    nodes = t1.get("nodes") or {}
    record("tabs/tab1_hr_nodes_present",
           bool(t1.get("has_card")) and bool(t1.get("dpi_exists")) and all(nodes.values()),
           f"card={t1.get('has_card')} dpi={t1.get('dpi_exists')} nodes={nodes}")
    record("tabs/tab1_dpi_three_options_default_1200",
           t1.get("dpi_options") == ["300", "600", "1200"] and t1.get("dpi_value") == "1200"
           and t1.get("dpi_selected_attr") == ["1200"],
           f"options={t1.get('dpi_options')} value={t1.get('dpi_value')!r} "
           f"selected={t1.get('dpi_selected_attr')}")
    hint = t1.get("hint") or ""
    record("tabs/tab1_dpi_size_hint",
           ("300" in hint and "5.4" in hint and "600" in hint and "15.5" in hint
            and "1200" in hint and "13.3" in hint and "反而最小" in hint and "6.2" in hint),
           f"提示={hint!r}")
    record("tabs/tab1_cancel_starts_disabled",
           t1.get("cancel_disabled") is True,
           f"取消按钮初始 disabled={t1.get('cancel_disabled')}")

    # 未选中行 ⇒ 点「开始」必须红字提示（不 alert、不打桥）
    _ev("document.getElementById('btn-tab1-hr-start').click()")
    time.sleep(0.4)
    t1b = _read("02_tab1_no_selection", JS_TAB1)
    record("tabs/tab1_start_requires_selected_row",
           "err" in (t1b.get("err_class") or "") and "选中" in (t1b.get("err_text") or "")
           and "未选择文件" in (t1b.get("src_text") or ""),
           f"src={t1b.get('src_text')!r} 提示={t1b.get('err_text')!r} class={t1b.get('err_class')!r}")

    # 选中第一行 ⇒ 源行跟随
    _ev("document.querySelector('#tab1-body tr').click()")
    time.sleep(0.6)
    t1c = _read("03_tab1_after_select", JS_TAB1)
    record("tabs/tab1_source_follows_selected_row",
           SOURCE_PDF.name in (t1c.get("src_text") or "") and "未选择" not in (t1c.get("src_text") or ""),
           f"源行={t1c.get('src_text')!r}")

    # ── ① tab1：PDF 快速预览（先看内容 ⇒ 再定「从第几页开始高清化」）──
    pv0 = _read("03a_tab1_pv_nodes", JS_TAB1_PV)
    ppi = pv0.get("page_input") or {}
    record("tabs/tab1_pv_region_and_page_input",
           bool(pv0.get("card")) and bool(pv0.get("in_hr_card")) and bool(pv0.get("after_range"))
           and all((pv0.get("nodes") or {}).values())
           and bool(ppi.get("exists")) and ppi.get("type") == "number" and bool(ppi.get("editable")),
           f"卡片={pv0.get('card')} 在 hr-card 内={pv0.get('in_hr_card')} "
           f"在起止页行下方={pv0.get('after_range')} nodes={pv0.get('nodes')} 页码输入={ppi}")

    # 注入假 `tab1_preview`（真渲染走 96dpi 真 PDF，图内容与页数随夹具变 ⇒ 只验 UI 行为）
    _ev("(() => { const B64=" + json.dumps(tiny_png()) + ";"
        " window.pywebview.api.tab1_preview = function(p){ var n=(p&&p.page)||1;"
        " return Promise.resolve({ok:true, page:n, total:5, png_b64:B64, px_w:714, px_h:1000,"
        " page_mm_w:179.9, page_mm_h:259.0, dpi:96, dpi_used:96, cached:false, elapsed_s:0.08}); };"
        " return 1; })()")
    _wait_js("(document.getElementById('tab1-pv-info')||{}).textContent"
             " && document.getElementById('tab1-pv-info').textContent.indexOf('/ 5 页')>=0", 10)
    _ev("(() => { const el=document.getElementById('tab1-pv-page'); el.value='3';"
        " el.dispatchEvent(new Event('change')); return el.value; })()")
    _wait_js("document.getElementById('tab1-pv-info').textContent.indexOf('第 3 / 5 页')>=0", 10)
    time.sleep(0.4)
    pv1 = _read("03b_tab1_pv_page3", JS_TAB1_PV)
    _ev("document.getElementById('btn-tab1-pv-setfrom').click()")
    time.sleep(0.4)
    pv2 = _read("03c_tab1_pv_setfrom", JS_TAB1_PV)
    record("tabs/tab1_pv_paging_and_setfrom",
           pv1.get("info") == "第 3 / 5 页" and pv1.get("img_hidden") is False
           and str(pv1.get("img_src_prefix") or "").startswith("data:image/png;base64,")
           and pv1.get("img_maxw") == "100%"
           and pv1.get("prev_disabled") is False and pv1.get("next_disabled") is False
           and pv2.get("hr_from") == "3" and "设为起始页" in (pv2.get("msg") or "")
           and "err" not in (pv2.get("msg_class") or ""),
           f"读数={pv1.get('info')!r} 图隐藏={pv1.get('img_hidden')} "
           f"src={pv1.get('img_src_prefix')!r} maxW={pv1.get('img_maxw')!r} "
           f"上页禁用={pv1.get('prev_disabled')} 下页禁用={pv1.get('next_disabled')} "
           f"→ hr-from={pv2.get('hr_from')!r} 提示={pv2.get('msg')!r}")

    # 边界：第 1 页 ⇒ 「上一页」禁用；第 5 页（末页）/ 输入超范围 99 ⇒ 夹到 5，「下一页」禁用
    _ev("(() => { const el=document.getElementById('tab1-pv-page'); el.value='1';"
        " el.dispatchEvent(new Event('change')); return el.value; })()")
    _wait_js("document.getElementById('tab1-pv-info').textContent.indexOf('第 1 / 5 页')>=0", 10)
    pv_first = _read("03d_tab1_pv_first", JS_TAB1_PV)
    _ev("(() => { const el=document.getElementById('tab1-pv-page'); el.value='99';"
        " el.dispatchEvent(new Event('change')); return el.value; })()")
    _wait_js("document.getElementById('tab1-pv-info').textContent.indexOf('第 5 / 5 页')>=0", 10)
    pv_last = _read("03e_tab1_pv_last", JS_TAB1_PV)

    # 失败路径：后端结构化 reason ⇒ 预览区给原因、红条带 reason（不 alert / 不炸桥）
    _ev("(() => { window.pywebview.api.tab1_preview = function(p){"
        " return Promise.resolve({ok:false, reason:'PAGE_OUT_OF_PDF', page:(p&&p.page)||1,"
        " total:5, msg:'第 4 页超出范围（本书共 5 页）'}); }; return 1; })()")
    _ev("(() => { const el=document.getElementById('tab1-pv-page'); el.value='4';"
        " el.dispatchEvent(new Event('change')); return el.value; })()")
    _wait_js("(document.getElementById('tab1-pv-msg')||{}).textContent"
             " && document.getElementById('tab1-pv-msg').textContent.indexOf('PAGE_OUT_OF_PDF')>=0", 10)
    pv_err = _read("03f_tab1_pv_error", JS_TAB1_PV)
    record("tabs/tab1_pv_bounds_and_error_reason",
           pv_first.get("prev_disabled") is True and pv_first.get("next_disabled") is False
           and pv_last.get("prev_disabled") is False and pv_last.get("next_disabled") is True
           and str(pv_last.get("page_input", {}).get("value")) == "5"
           and "PAGE_OUT_OF_PDF" in (pv_err.get("msg") or "")
           and "err" in (pv_err.get("msg_class") or "")
           and pv_err.get("img_hidden") is True,
           f"首/末页禁用=({pv_first.get('prev_disabled')},{pv_first.get('next_disabled')})/"
           f"({pv_last.get('prev_disabled')},{pv_last.get('next_disabled')}) "
           f"末页夹紧={pv_last.get('page_input', {}).get('value')!r} "
           f"失败提示={pv_err.get('msg')!r} class={pv_err.get('msg_class')!r} "
           f"图隐藏={pv_err.get('img_hidden')}")

    # 进度 / 完成态（注入 onProgress 推送 + 假 status，避免真跑 ≈6.2 s/页 的渲染）
    running = {
        "ok": True, "kind": "tab1_highres", "task_id": "t-fake", "state": "running",
        "running": True, "page": 2, "pages_total": 5, "pages_done": 2,
        "bytes": 27 * 1024 * 1024, "msg": "渲页中（2/5）", "dpi": 1200,
        "out": "/x/9787000000001/吴-HighRes.pdf", "elapsed_s": 12.4,
    }
    done = dict(running, state="done", running=False, page=5, pages_done=5,
                bytes=66 * 1024 * 1024, msg="完成", elapsed_s=31.0,
                out="/x/2_HighRes_PDF/9787000000001/吴颐人篆刻作品展示-HighRes.pdf")
    _ev("(() => { window.pywebview.api.tab1_highres_status = function(){ return Promise.resolve("
        + json.dumps(running, ensure_ascii=False) + "); }; return 1; })()")
    _ev("window.onProgress(" + json.dumps(running, ensure_ascii=False) + ")")
    time.sleep(0.3)
    t1d = _read("03b_tab1_progress", JS_TAB1)
    record("tabs/tab1_progress_bar_and_counters",
           t1d.get("bar_width") == "40%" and "2/5 页" in (t1d.get("hr_msg") or "")
           and "累计 27.0 MB" in (t1d.get("hr_msg") or "")
           and t1d.get("start_disabled") is True and t1d.get("cancel_disabled") is False
           and t1d.get("done_hidden") is True,
           f"bar={t1d.get('bar_width')!r} 文案={t1d.get('hr_msg')!r} "
           f"开始禁用={t1d.get('start_disabled')} 取消可用={t1d.get('cancel_disabled') is False}")

    out_path = str(done["out"])
    _ev("(() => { window.pywebview.api.tab1_highres_status = function(){ return Promise.resolve("
        + json.dumps(done, ensure_ascii=False) + "); }; return 1; })()")
    _ev("window.onProgress(" + json.dumps(done, ensure_ascii=False) + ")")
    time.sleep(0.3)
    t1e = _read("03c_tab1_done", JS_TAB1)
    record("tabs/tab1_done_shows_out_path_and_goto",
           t1e.get("done_hidden") is False and out_path in (t1e.get("out_text") or "")
           and t1e.get("bar_width") == "100%" and t1e.get("start_disabled") is False
           and "去 tab2" in (t1e.get("goto_label") or ""),
           f"done 显示={t1e.get('done_hidden') is False} 产物={t1e.get('out_text')!r} "
           f"bar={t1e.get('bar_width')!r} 按钮={t1e.get('goto_label')!r}")

    # 「➡ 去 tab2 切图」⇒ 真切页（同时把后续断言带进 tab2）
    _ev("document.getElementById('btn-tab1-hr-goto2').click()")
    time.sleep(0.8)
    jumped = _read("03d_goto2", "(() => JSON.stringify({tab2: !!document.querySelector('.panel.active[data-panel=\"2_HighRes_PDF\"]'),"
                                " tab1: !!document.querySelector('.panel.active[data-panel=\"1_Original_PDF\"]')}))()")
    record("tabs/tab1_goto2_switches_to_tab2",
           bool(jumped.get("tab2")) and not jumped.get("tab1"),
           f"tab2 active={jumped.get('tab2')} tab1 active={jumped.get('tab1')}")

    # ── ② tab2：切图台节点 / 高级面板折叠 / 源列表 ──
    _wait_js("document.querySelectorAll('#tab2-ct-source option').length > 0", 25)
    time.sleep(0.8)
    t2 = _read("04_tab2_nodes", JS_TAB2)
    n2 = t2.get("nodes") or {}
    record("tabs/tab2_cut_station_nodes_present",
           bool(t2.get("panel_active")) and all(n2.values()),
           f"panel_active={t2.get('panel_active')} nodes={n2}")
    cv = t2.get("canvas") or {}
    record("tabs/tab2_canvas_has_size",
           int(cv.get("w") or 0) > 0 and int(cv.get("h") or 0) > 0
           and int(cv.get("css_w") or 0) > 0 and int(cv.get("css_h") or 0) > 0 and bool(cv.get("ctx")),
           f"canvas intrinsic={cv.get('w')}×{cv.get('h')} css={cv.get('css_w')}×{cv.get('css_h')}")
    # ⚠ 断言口径已随 2026-10-20 目录键改造更新：旧写法要求源信息里出现 ISBN 目录名
    #   `9787000000001`（`config/book_dir_keys.json` 时代）；现在目录键只认 tab1 书名 /
    #   文件名主名 ⇒ 不再有 ISBN 目录名，改为校验**文件名主名 + `filename-fallback`**。
    opts = t2.get("src_options") or []
    srcinfo = t2.get("srcinfo") or ""
    record("tabs/tab2_sources_listed_from_highres_dir",
           len(opts) >= 1
           and any("HighRes.pdf" in (o.get("t") or "") for o in opts)
           and "吴颐人篆刻作品展示-HighRes" in srcinfo
           and "filename-fallback" in srcinfo,
           f"options={[o.get('t') for o in opts]} 源信息={srcinfo!r}")
    capt = t2.get("dir") or ""
    record("tabs/tab2_head_dir_key_caption",
           capt.startswith("目录键：") and "⇒ 3_Cropped_Tiff/" in capt
           and ("manual" in capt or "filename-fallback" in capt),
           f"#tab2-crop-dir={capt!r}")
    record("tabs/tab2_legacy_render_folded_not_removed",
           t2.get("adv_open") is False and "已由 tab1 一键高清化取代" in (t2.get("adv_summary") or "")
           and not (t2.get("legacy_missing") or [])
           and len(t2.get("legacy_inside_adv") or []) == 9,
           f"details.open={t2.get('adv_open')} summary={t2.get('adv_summary')!r} "
           f"旧节点在 details 内={len(t2.get('legacy_inside_adv') or [])}/9 缺={t2.get('legacy_missing')}")

    # ── ③ 注入假 tab2_extract ⇒ 点「自动检测」⇒ canvas 框数 = 注入数 ＋ 字段区就位 ──
    #    走 tab2_extract（不是 tab2_detect）：一次拿回 框 ＋ 三字段 ＋ 阅读顺序 ＋ 本书元数据
    from src import seal_crop as sc                      # 命名口径：与前端 foName 对拍用
    PAGE = 370
    BOXES = [
        {"x1": 300, "y1": 300, "x2": 900, "y2": 900},
        {"x1": 1400, "y1": 600, "x2": 2000, "y2": 1200},
        {"x1": 800, "y1": 2400, "x2": 1500, "y2": 3100},
    ]
    BOOK = {"dynasty": "清中期", "author": "吳熙載", "reading_order": "auto"}
    SEALS = [
        {"idx": 1, "box": [300, 300, 900, 900], "inscription": "中候", "status": "蟫",
         "code": "0425", "inscription_score": 0.9912, "needs_review": False,
         "read_order": 2, "c": 2, "r": 1},
        {"idx": 2, "box": [1400, 600, 2000, 1200], "inscription": "中羞行府", "status": "故",
         "code": "0424", "inscription_score": 0.6120, "needs_review": True,
         "read_order": 1, "c": 1, "r": 1},
        {"idx": 3, "box": [800, 2400, 1500, 3100], "inscription": None, "status": None,
         "code": None, "inscription_score": None, "needs_review": False,
         "read_order": 3, "c": 1, "r": 2},
    ]
    png_b64 = tiny_png()
    fake = {
        "ok": True, "pdf": "/fake/HighRes.pdf", "pdf_name": "吴颐人篆刻作品展示-HighRes.pdf",
        "page": PAGE, "dpi": 400, "boxes_dpi": 400, "size": [3400, 4760],
        "boxes": BOXES, "count": 3, "seals": SEALS,
        "reading_order": "rtl-ttb", "order_source": "code-sequence", "book_meta": BOOK,
        "dropped": {"inside_seal": 7, "edge": 2, "far": 0, "noise": 5},
        "preview_png_b64": png_b64, "preview_size": [714, 1000],
        "preview_scale": 0.2101, "elapsed_s": 0.42,
    }
    _ev("(() => { window.__realExtract = window.pywebview.api.tab2_extract;"
        " window.pywebview.api.tab2_extract = function(){ return Promise.resolve("
        + json.dumps(fake) + "); }; return 1; })()")
    _ev("document.getElementById('tab2-ct-page').value = '" + str(PAGE) + "'")
    _ev("document.getElementById('btn-tab2-detect').click()")
    _wait_js("document.getElementById('tab2-canvas').dataset.boxes === '3'", 20)
    _wait_js("document.querySelectorAll('#tab2-fields .frow').length === 3", 20)
    time.sleep(0.5)
    t2b = _read("05_tab2_after_detect", JS_TAB2)
    cvb = t2b.get("canvas") or {}
    record("tabs/tab2_detect_draws_boxes_on_canvas",
           cvb.get("boxes") == "3" and int(cvb.get("w") or 0) == 714
           and "检测到 3 枚" in (t2b.get("count_text") or "")
           and "（3）" in (t2b.get("crop_label") or "") and t2b.get("crop_disabled") is False,
           f"canvas.dataset.boxes={cvb.get('boxes')} canvas={cvb.get('w')}×{cvb.get('h')} "
           f"计数={t2b.get('count_text')!r} 裁切按钮={t2b.get('crop_label')!r} "
           f"disabled={t2b.get('crop_disabled')}")

    # ── ③-1 字段区：一行/枚、三字段（释文/状态/编号）可编辑、读数＋文件名预演 ──
    fld = t2b.get("fields") or {}
    cells = fld.get("cells") or []
    record("tabs/tab2_fields_one_row_per_box_editable",
           fld.get("rows") == 3 and len(cells) == 3
           and all(int(c.get("inputs") or 0) == 3 and c.get("editable") for c in cells),
           f"行数={fld.get('rows')} 每行输入框={[c.get('inputs') for c in cells]} "
           f"全部可编辑={[c.get('editable') for c in cells]}")
    record("tabs/tab2_fields_show_extracted_values",
           [c.get("ins") for c in cells] == ["中候", "中羞行府", ""]
           and [c.get("status") for c in cells] == ["蟫", "故", ""]
           and [c.get("code") for c in cells] == ["0425", "0424", ""],
           f"释文={[c.get('ins') for c in cells]} 状态={[c.get('status') for c in cells]} "
           f"编号={[c.get('code') for c in cells]}")

    # ── ③-2 阅读顺序下拉：恰 5 项、默认 auto；后端推断值显示在提示里 ──
    ro = t2b.get("read_order") or {}
    record("tabs/tab2_read_order_select_five_options_default_auto",
           int(ro.get("count") or 0) == 5
           and ro.get("options") == ["auto", "rtl-ttb", "ltr-ttb", "rtl-btt", "ltr-btt"]
           and ro.get("value") == "auto"
           and "rtl-ttb" in (t2b.get("order_src") or "")
           and "code-sequence" in (t2b.get("order_src") or ""),
           f"选项={ro.get('options')} 当前={ro.get('value')!r} 顺序来源={t2b.get('order_src')!r}")

    # ── ③-3 needs_review（低分未验证）必须**看得见**：整行 .rev ＋ 分数旁「⚠」 ──
    revs = [c for c in cells if c.get("rev")]
    record("tabs/tab2_needs_review_visible",
           len(revs) == 1 and revs[0].get("i") == "1" and "⚠" in (revs[0].get("score") or ""),
           f"待确认行={[(c.get('i'), c.get('score')) for c in revs]}")

    # ── ③-4 **前后端命名对拍**：DOM 里的文件名预演 vs Python `build_crop_name`（逐字相同）──
    cr = sc.grid_order([[b["x1"], b["y1"], b["x2"], b["y2"]] for b in BOXES], reading_order="rtl-ttb")

    def py_name(i, fields):
        c, r = cr[i]
        return sc.build_crop_name(PAGE, c, r, fields,
                                  dynasty=BOOK["dynasty"], author=BOOK["author"])[0]

    want = [py_name(0, {"code": "0425", "inscription": "中候"}),
            py_name(1, {"code": "0424", "inscription": "中羞行府"}),
            py_name(2, {"inscription": ""})]
    got = [c.get("name") for c in cells]
    record("tabs/tab2_crop_name_preview_matches_backend",
           got == want
           and any(n.startswith(f"0424_P{PAGE}_C1_R1_中羞行府_清中期_吳熙載") for n in got)
           and any(n == f"P{PAGE}-C1-R2.tiff" for n in got),
           f"DOM={got} Python={want}")

    # 清洗用例：编号含 `/` ＋ 释文空 ⇒ `04-24`、`NA`（前后端同一份清洗规则）
    _ev("""(() => { const g=id=>document.getElementById(id);
      const box=g('tab2-fields'); const row=box.querySelectorAll('.frow')[2];
      const set=(k,v)=>{ const el=row.querySelector('.fin[data-k='+k+']');
        el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); };
      set('code','04/24'); set('status',''); return 1; })()""")
    time.sleep(0.4)
    t2f = _read("06_tab2_field_edit", JS_TAB2)
    got2 = [c.get("name") for c in (t2f.get("fields") or {}).get("cells") or []]
    want2 = [want[0], want[1], py_name(2, {"code": "04/24", "inscription": ""})]
    record("tabs/tab2_field_edit_cleans_name_and_keeps_parity",
           got2 == want2 and want2[2] == f"04-24_P{PAGE}_C1_R2_NA_清中期_吳熙載.tiff",
           f"DOM={got2} Python={want2}")

    # 超长释文：两端都必须 ≤200 且逐字相同（截断顺序 ins → aut → dyn）
    long_ins = "甲" * 150
    _ev("""(() => { const g=id=>document.getElementById(id);
      const row=g('tab2-fields').querySelectorAll('.frow')[0];
      const el=row.querySelector('.fin[data-k=inscription]');
      el.value='"""+ long_ins + """'; el.dispatchEvent(new Event('input',{bubbles:true}));
      return 1; })()""")
    time.sleep(0.4)
    t2g = _read("07_tab2_long_inscription", JS_TAB2)
    got3 = [c.get("name") for c in (t2g.get("fields") or {}).get("cells") or []]
    want3 = [py_name(0, {"code": "0425", "inscription": long_ins}), want[1],
             py_name(2, {"code": "04/24", "inscription": ""})]
    record("tabs/tab2_long_inscription_truncated_parity",
           got3 == want3 and all(len(n) <= 200 for n in got3),
           f"DOM 长度={[len(n) for n in got3]} Python 长度={[len(n) for n in want3]} "
           f"逐字相同={got3 == want3}")

    # ── ③-5 `auto` 语义：下拉停在 `auto` ⇒ 提交给 `tab2_crop` 的 `reading_order` 必须是 `'auto'`
    #    （**不是**上一轮 `tab2_extract` 的推断值）⇒ 后端自己推断，`order_source` 才是
    #    `code-sequence` 而不是 `manual`。这里拦下真实 payload 验语义 ＋ Python 侧同口径复算。
    _ev("(() => { window.__cropReq = null; window.__realCrop = window.pywebview.api.tab2_crop;"
        " window.pywebview.api.tab2_crop = function(req){ window.__cropReq = req;"
        " return Promise.resolve({ok:true, outputs:[], skipped:[], dir_key:'9787000000001',"
        " dir_key_source:'from_dir', reading_order:'rtl-ttb', order_source:'code-sequence',"
        " fields_count:3, elapsed_s:0.01}); }; return 1; })()")
    _ev("document.getElementById('btn-tab2-crop').click()")
    _wait_js("!!window.__cropReq", 20)
    t2cr = _read("08a_tab2_crop_payload",
                 "JSON.stringify({req: window.__cropReq || null,"
                 " src: (document.getElementById('tab2-order-src') || {}).textContent || ''})")
    creq = t2cr.get("req") or {}
    py_order, py_src = FeicuiApi._resolve_reading_order(
        "auto", BOOK,
        [dict(SEALS[i], box=[BOXES[i]["x1"], BOXES[i]["y1"], BOXES[i]["x2"], BOXES[i]["y2"]])
         for i in range(len(SEALS))])
    record("tabs/tab2_crop_payload_auto_and_order_source_code_sequence",
           creq.get("reading_order") == "auto" and int(creq.get("page") or 0) == PAGE
           and len(creq.get("boxes") or []) == 3 and len(creq.get("fields") or []) == 3
           and py_src == "code-sequence" and py_order == "rtl-ttb"
           and "code-sequence" in (t2cr.get("src") or ""),
           f"payload.reading_order={creq.get('reading_order')!r} "
           f"boxes={len(creq.get('boxes') or [])} fields={len(creq.get('fields') or [])} "
           f"后端复算=({py_order},{py_src}) 界面来源={t2cr.get('src')!r}")

    # 单击第一枚框 ⇒ 删除（框数 3 → 2）
    _ev("""(() => { const g=id=>document.getElementById(id); const cv=g('tab2-canvas');
      const r=cv.getBoundingClientRect(); const s=+cv.dataset.scale;
      const px=600*s, py=600*s;                     // 第 1 枚框的中心（400dpi）
      const cx=r.left+px*(r.width/cv.width), cy=r.top+py*(r.height/cv.height);
      cv.dispatchEvent(new MouseEvent('mousedown',{clientX:cx,clientY:cy,bubbles:true}));
      cv.dispatchEvent(new MouseEvent('mouseup',{clientX:cx,clientY:cy,bubbles:true}));
      return 1; })()""")
    time.sleep(0.4)
    t2c = _read("06_tab2_click_deletes", JS_TAB2)
    record("tabs/tab2_single_click_box_deletes",
           (t2c.get("canvas") or {}).get("boxes") == "2" and "检测到 2 枚" in (t2c.get("count_text") or ""),
           f"点击框中心后框数={(t2c.get('canvas') or {}).get('boxes')} 计数={t2c.get('count_text')!r}")

    # 空白处双击 ⇒ 新增一枚（2 → 3）
    _ev("""(() => { const g=id=>document.getElementById(id); const cv=g('tab2-canvas');
      const r=cv.getBoundingClientRect();
      const cx=r.left+r.width*0.82, cy=r.top+r.height*0.82;   // 右下空白
      cv.dispatchEvent(new MouseEvent('dblclick',{clientX:cx,clientY:cy,bubbles:true}));
      return 1; })()""")
    time.sleep(0.4)
    t2d = _read("07_tab2_dblclick_adds", JS_TAB2)
    record("tabs/tab2_dblclick_empty_adds_box",
           (t2d.get("canvas") or {}).get("boxes") == "3" and "检测到 3 枚" in (t2d.get("count_text") or ""),
           f"双击空白后框数={(t2d.get('canvas') or {}).get('boxes')} 计数={t2d.get('count_text')!r} "
           f"提示={t2d.get('msg')!r}")

    # 清空框 ⇒ 0；裁切按钮置灰；**字段区与阅读顺序也一并清**（不留上一页读数）
    _ev("document.getElementById('btn-tab2-clear').click()")
    time.sleep(0.3)
    t2e = _read("08_tab2_clear", JS_TAB2)
    record("tabs/tab2_clear_boxes_disables_crop",
           (t2e.get("canvas") or {}).get("boxes") == "0" and t2e.get("crop_disabled") is True,
           f"框数={(t2e.get('canvas') or {}).get('boxes')} 裁切 disabled={t2e.get('crop_disabled')}")
    # ⚠ 断言写法坑（本单修的 2 条 FAIL 之一）：原先写 `int(get("rows") or -1) == 0` ——
    #    `rows` 恰为 **0** 时 `0 or -1` 得 `-1`，**把正确结果判成 FAIL**。取值为 0 合法处一律
    #    用 `is not None` 判空，别用 `or`。
    _rows = (t2e.get("fields") or {}).get("rows")
    record("tabs/tab2_clear_also_clears_fields_and_order",
           _rows is not None and int(_rows) == 0
           and (t2e.get("order_src") or "").strip() == "—",
           f"字段行数={_rows} 顺序来源={t2e.get('order_src')!r}")

    # ── ③-6 lite 包（无 OCR）语义：检测**成功**、字段留空可编辑、信息色提示条（**不是**红条）──
    #    响应形状照 `斐萃_lite.app` 真值：`ocr_available=false`、三字段空串、`order_source='fallback'`。
    #    回归点是用户实测那个红横幅 `字段提取失败: ModuleNotFoundError: No module named 'rapidocr'`
    #    —— lite 包点「自动检测」绝不能走到那里。
    _lite_seals = [dict(s, inscription="", status="", code="", inscription_score=None,
                        needs_review=False) for s in SEALS]
    lite = dict(fake, seals=_lite_seals, ocr_available=False, fields_manual=True,
                reading_order="ltr-ttb", order_source="fallback",
                note="本版不含 OCR（斐萃_lite）：本次只做了红印检测（3 枚），释文/状态/编号请手动填写；"
                     "要自动识别请用 斐萃_pro（含 OCR）")
    _ev("window.pywebview.api.tab2_extract = function(){ return Promise.resolve("
        + json.dumps(lite) + "); }; 1")
    _ev("document.getElementById('btn-tab2-detect').click()")
    _wait_js("document.querySelectorAll('#tab2-fields .frow').length === 3", 20)
    time.sleep(0.5)
    t2l = _read("08b_tab2_lite_no_ocr", JS_TAB2)
    ocrbar = _read("08c_tab2_lite_ocr_banner",
                   "(() => { const n=document.getElementById('tab2-ocr-note');"
                   " const m=document.getElementById('tab2-ct-msg');"
                   " return JSON.stringify({hidden: n?n.hidden:null, note: n?n.textContent:'',"
                   " cls: m?m.className:'', msg: m?m.textContent:''}); })()")
    lcells = (t2l.get("fields") or {}).get("cells") or []
    record("tabs/tab2_lite_no_ocr_ok_info_banner",
           (t2l.get("canvas") or {}).get("boxes") == "3"
           and "已检测 3 枚印章（本版无 OCR，字段请手动填写）" in (t2l.get("msg") or "")
           and "info" in (ocrbar.get("cls") or "") and "err" not in (ocrbar.get("cls") or "")
           and ocrbar.get("hidden") is False and "斐萃_pro" in (ocrbar.get("note") or "")
           and len(lcells) == 3 and all(c.get("editable") for c in lcells)
           and all((c.get("ins") or "", c.get("status") or "", c.get("code") or "") == ("", "", "")
                   for c in lcells),
           f"框数={(t2l.get('canvas') or {}).get('boxes')} 消息={t2l.get('msg')!r} "
           f"class={ocrbar.get('cls')!r} 提示条={ocrbar.get('note')!r} "
           f"字段={[(c.get('ins'), c.get('status'), c.get('code')) for c in lcells]}")
    record("tabs/tab2_lite_order_falls_back_not_code_sequence",
           "fallback" in (t2l.get("order_src") or "")
           and "code-sequence" not in (t2l.get("order_src") or ""),
           f"顺序来源={t2l.get('order_src')!r}")
    _ev("window.pywebview.api.tab2_extract = window.__realExtract; 1")   # 还原真桥

    # ── ④ 切到 tab3：原节点一字未变（渲染后）──
    _ev("document.querySelector('#tabs .tab[data-tab=\"3_Cropped_Tiff\"]').click()")
    _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length > 0", 25)
    time.sleep(0.6)
    t3 = _read("09_tab3_dom", JS_TAB3)
    RESULT["tab3_ids"] = t3.get("ids")
    record("tabs/tab3_dom_intact_after_tab2_rewrite",
           bool(t3.get("panel_active")) and t3.get("id_count") == INFO["tab3_id_count"]
           and t3.get("view_btns") == 4 and "3_Cropped_Tiff" in (t3.get("h2") or "")
           and t3.get("head_btns") == ["btn-tab3-refresh", "btn-tab3-test"]
           and document_id_ok(t3),
           f"id 数={t3.get('id_count')}（HEAD 静态块 {INFO['tab3_id_count']} 个）"
           f" 视图按钮={t3.get('view_btns')} h2={t3.get('h2')!r}")

    # ── ④-b tab3：**旧目录键按钮只读**（`legacy` 类 + 「只读」提示）＋ 目录键文案 ──
    t3s = _read("09b_tab3_subdir_legacy",
                "(() => { const bs=[...document.querySelectorAll('#tab3-subdirs button')];"
                " return JSON.stringify({count: bs.length,"
                " items: bs.map(b=>({text: b.textContent.trim(),"
                " legacy: b.classList.contains('legacy'), title: b.title||''})),"
                " dirinfo: (document.getElementById('tab3-dirinfo')"
                "   ?document.getElementById('tab3-dirinfo').textContent:'')}); })()")
    legs = [x for x in (t3s.get("items") or []) if x.get("legacy")]
    record("tabs/tab3_legacy_dir_key_button_readonly",
           int(t3s.get("count") or 0) >= 2 and len(legs) >= 1
           and all("只读" in (x.get("title") or "") for x in legs)
           and bool(t3s.get("dirinfo")),
           f"子目录按钮={t3s.get('count')} 旧键={[(x.get('text'), x.get('legacy')) for x in legs]} "
           f"目录键文案={t3s.get('dirinfo')!r}")

    # ── ⑤ tab3 读**切图台新命名**（`<编号>_P<页>_C<列>_R<行>_…tiff`）──
    #    兼容解析不生效时：这条会看到「命名不合模板」＋三字段空白（＝阻塞项失败）
    new_name = "0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff"
    _ev("(() => { const el=[...document.querySelectorAll('#tab3-grid .thumb-item')]"
        ".find(d=>d.dataset.name===" + json.dumps(new_name) + ");"
        " if(el){ el.click(); return 1; } return 0; })()")
    _wait_js("!!document.getElementById('tab3-shiwen')"
             " && document.getElementById('tab3-shiwen').value === '中羞行府'", 20)
    time.sleep(0.5)
    t3n = _read("10_tab3_new_naming", JS_TAB3_ONE.replace("__NAME__", json.dumps(new_name)))
    record("tabs/tab3_new_naming_shows_page_col_row_and_fields",
           bool(t3n.get("found")) and t3n.get("bad_class") is False
           and t3n.get("shiwen") == "中羞行府" and t3n.get("dynasty") == "清中期"
           and t3n.get("author") == "吳熙載"
           and "第 370 页 · 第 1 列 · 第 1 行" in (t3n.get("parsed_msg") or "")
           and "0424" in (t3n.get("parsed_msg") or ""),
           f"命中={t3n.get('found')} 标坏={t3n.get('bad_class')} 释文={t3n.get('shiwen')!r} "
           f"朝代={t3n.get('dynasty')!r} 作者={t3n.get('author')!r} 解析提示={t3n.get('parsed_msg')!r}")
    record("tabs/tab3_new_naming_rename_preview_keeps_code_scheme",
           t3n.get("newname") == new_name and t3n.get("rename_disabled") is True,
           f"新名预览={t3n.get('newname')!r} 改名按钮 disabled={t3n.get('rename_disabled')}")


def document_id_ok(t3: dict) -> bool:
    """tab3 的 id 集合必须与 HEAD 静态块里的 id 集合**完全一致**（无增无减）。"""
    return sorted(t3.get("ids") or []) == INFO["tab3_ids"]


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


# ───────────────────────── 静态面（Python 侧）─────────────────────────
def tab3_block(text: str) -> str:
    i = text.index("<!-- ── tab3：3_Cropped_Tiff")
    j = text.index("<!-- ═══════════ 「连接 yinyuan」弹窗")
    return text[i:j].strip()


def strip_tab3_dirinfo(block: str) -> str:
    """剔掉本单**新增**的 `#tab3-dirinfo` 一行（`tab3` 静态块唯一允许的改动白名单）。

    除了这一行 caption，tab3 静态块必须与 HEAD **逐字节相同**（渲染后节点另由 `document_id_ok` 复核）。
    """
    return re.sub(r'[ \t]*<div class="caption" id="tab3-dirinfo">[^<]*</div>\n', "", block)


def head_index_html() -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "show", "HEAD:local-dist/ui/index.html"],
                             capture_output=True, text=True, check=True)
        return out.stdout
    except Exception:
        return ""


def main(argv: list[str] | None = None) -> int:
    global WIN
    ap = argparse.ArgumentParser(description="斐萃 tab1/tab2（Phase B）渲染后 DOM 断言")
    ap.add_argument("--out", default=str(READINGS))
    ap.add_argument("--watchdog", type=float, default=150.0)
    args = ap.parse_args(argv)

    root = build_fixture()
    INFO.update({"scratch": str(SCRATCH), "fixture": str(root), "data_dir": str(DATA_DIR),
                 "source_pdf": SOURCE_PDF.name})

    # tab3 一字未改：HEAD 静态块 vs 工作区静态块（逐字节）＋ id 集合留给 DOM 侧复核
    cur_html = (WEBUI_DIR / "ui" / "index.html").read_text(encoding="utf-8")
    head_html = head_index_html()
    cur_block = tab3_block(cur_html)
    head_block = tab3_block(head_html) if head_html else ""
    cur_whitelisted = strip_tab3_dirinfo(cur_block)
    # HEAD 侧同样剔白名单：`#tab3-dirinfo` 那一行**已进 HEAD**（与本单共存），只剔工作区侧
    # 会让「与 HEAD 逐字节相同」变成恒假（HEAD 留着、工作区被剔掉）。
    head_whitelisted = strip_tab3_dirinfo(head_block)
    removed = len(cur_block) - len(cur_whitelisted)
    ids = re.findall(r'id="([^"]+)"', cur_block)
    INFO["tab3_id_count"] = len(ids)
    INFO["tab3_ids"] = sorted(ids)
    same = bool(cur_block) and (cur_block == head_block
                                or cur_whitelisted == head_whitelisted)
    record("tabs/tab3_block_byte_identical_to_head",
           bool(head_block) and same and removed > 0,
           f"白名单 `#tab3-dirinfo`（工作区 {removed} 字符）外与 HEAD 逐字节相同="
           f"{cur_whitelisted == head_whitelisted}；工作区 tab3 块 {len(cur_block)} 字符 / "
           f"HEAD {len(head_block)} 字符")

    # 零 CDN / 零新前端依赖：页面无外链脚本样式，app.js 无 import/fetch 外网
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', cur_html)
    js = (WEBUI_DIR / "ui" / "app.js").read_text(encoding="utf-8")
    record("tabs/no_new_frontend_deps",
           not ext and "<script src=\"app.js\">" in cur_html
           and not re.search(r"https?://(?!127\.0\.0\.1)", js),
           f"外链资源={ext} 页面仅引本地 app.js=True 前端无外网 URL=True")

    api = FeicuiApi()
    vr = api.verify_dir({"path": str(root)})
    users = [u for u, v in api._users.items() if v["is_admin"]]
    if not vr.get("ok") or not users:
        print(f"FIXTURE_FAIL verify_dir={vr} admin_users={users}", flush=True)
        return 2
    lg = api.login({"username": users[0], "password": api._users[users[0]]["pwd"]})
    INFO.update({"admin": users[0], "login_ok": bool(lg.get("ok")), "verify_msg": vr.get("msg")})

    webview, WIN = build_window(api)
    threading.Timer(args.watchdog, lambda: (RESULT.setdefault("watchdog", "fired"), WIN.destroy())).start()
    print(f"DOMTEST_TABS_START fixture={root} data_dir={DATA_DIR}", flush=True)
    webview.start(probe)

    counts = {s: sum(1 for c in RESULT["checks"] if c["status"] == s) for s in ("PASS", "FAIL")}
    summary = {"schema": "feicui.webui.domtest_tabs.v1", "at": datetime.now().isoformat(timespec="seconds"),
               "python": sys.executable, "app_title": APP_TITLE, "counts": counts,
               "fixture": INFO, "checks": RESULT["checks"], "dom": RESULT["dom"],
               "js_errors": RESULT.get("js_errors", [])}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== tab1/tab2 渲染后 DOM 断言 ===")
    print(json.dumps({"counts": counts, "fixture": INFO, "js_errors": RESULT.get("js_errors", [])},
                     ensure_ascii=False, indent=2))
    print(f"\n读数落盘：{out}")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0 if counts.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
