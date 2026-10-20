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

from api import APP_TITLE, DATA_DIR, FeicuiApi  # noqa: E402
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
    dir: g('tab2-crop-dir')?g('tab2-crop-dir').textContent:''
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


def _probe_body() -> None:
    _wait_js("!!(document.readyState==='complete' && window.pywebview && window.pywebview.api)", 30)
    _wait_js("!!document.querySelector('#view-main.active') && !!document.getElementById('tabs')", 30)
    _wait_js("document.querySelectorAll('#tab1-body tr').length > 0", 25)
    time.sleep(1.0)

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
    record("tabs/tab2_sources_listed_from_highres_dir",
           len(t2.get("src_options") or []) >= 1
           and any("HighRes.pdf" in (o.get("t") or "") for o in (t2.get("src_options") or []))
           and "9787000000001" in (t2.get("srcinfo") or ""),
           f"options={[o.get('t') for o in (t2.get('src_options') or [])]} 源信息={t2.get('srcinfo')!r}")
    record("tabs/tab2_legacy_render_folded_not_removed",
           t2.get("adv_open") is False and "已由 tab1 一键高清化取代" in (t2.get("adv_summary") or "")
           and not (t2.get("legacy_missing") or [])
           and len(t2.get("legacy_inside_adv") or []) == 9,
           f"details.open={t2.get('adv_open')} summary={t2.get('adv_summary')!r} "
           f"旧节点在 details 内={len(t2.get('legacy_inside_adv') or [])}/9 缺={t2.get('legacy_missing')}")

    # ── ③ 注入假 tab2_detect ⇒ 点「自动检测」⇒ canvas 框数 = 注入数 ──
    png_b64 = tiny_png()
    fake = {
        "ok": True, "pdf": "/fake/HighRes.pdf", "pdf_name": "吴颐人篆刻作品展示-HighRes.pdf",
        "page": 1, "dpi": 400, "boxes_dpi": 400, "size": [3400, 4760],
        "boxes": [
            {"x1": 300, "y1": 300, "x2": 900, "y2": 900, "idx": 1},
            {"x1": 1400, "y1": 600, "x2": 2000, "y2": 1200, "idx": 2},
            {"x1": 800, "y1": 2400, "x2": 1500, "y2": 3100, "idx": 3},
        ],
        "count": 3, "preview_png_b64": png_b64, "preview_size": [714, 1000],
        "preview_scale": 0.2101, "elapsed_s": 0.31,
    }
    _ev("(() => { window.__realDetect = window.pywebview.api.tab2_detect;"
        " window.pywebview.api.tab2_detect = function(){ return Promise.resolve("
        + json.dumps(fake) + "); }; return 1; })()")
    _ev("document.getElementById('btn-tab2-detect').click()")
    _wait_js("document.getElementById('tab2-canvas').dataset.boxes === '3'", 20)
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

    # 清空框 ⇒ 0；裁切按钮置灰
    _ev("document.getElementById('btn-tab2-clear').click()")
    time.sleep(0.3)
    t2e = _read("08_tab2_clear", JS_TAB2)
    record("tabs/tab2_clear_boxes_disables_crop",
           (t2e.get("canvas") or {}).get("boxes") == "0" and t2e.get("crop_disabled") is True,
           f"框数={(t2e.get('canvas') or {}).get('boxes')} 裁切 disabled={t2e.get('crop_disabled')}")

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
    ids = re.findall(r'id="([^"]+)"', cur_block)
    INFO["tab3_id_count"] = len(ids)
    INFO["tab3_ids"] = sorted(ids)
    record("tabs/tab3_block_byte_identical_to_head",
           bool(head_block) and cur_block == head_block,
           f"工作区 tab3 块 {len(cur_block)} 字符 / HEAD {len(head_block)} 字符 "
           f"（逐字节相同={cur_block == head_block}）")

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
