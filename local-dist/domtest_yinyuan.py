#!/usr/bin/env python
# local-dist/domtest_yinyuan.py
"""「斐萃 → yinyuan」入口 —— **渲染后 DOM 断言**（真窗口 + `evaluate_js`，不是静态自证）。

配方沿用 `local-dist/domtest.py`（同一套实测结论）：
  * 复用 `app.build_window(api)`（**同一 UI、同一 js_api、同一启动路径**）；
  * `webview.start(probe)` **必须主线程**，probe 里 `time.sleep` 等桥就绪，再 `evaluate_js` 读渲染后 DOM；
  * `threading.Timer` 看门狗兜底关窗。

本次断言（**不打真实网络、不注册、不真登录**）：
  ① 顶栏「连接 yinyuan」入口存在且可见（`#btn-yy-open`，文案含 yinyuan）；
  ② 点击后弹窗出现、**登录框出现**（手机/邮箱 + 口令 两个输入 + 连接按钮）；
  ③ 在 DOM 里填表并点「连接」⇒ 走真桥 `yinyuan_connect` ⇒ 假 transport 应答：
     弹窗切到已连接面、显示 **key 前缀**、顶栏 pill 亮起；**整页 DOM 里不出现完整明文 key**；
     且 transport 收到的口令带前后空格**原样未 trim**（B1 口径穿透到最外层）；
  ④ 断开 ⇒ 回到登录框；
  ⑤ tab3 候选补全：作者输入弹候选并点击回填；释文输入弹候选；
  ⑥ tab1 朝代下拉：连接后取到 yinyuan 缓存值域（`远1/远2`）。

隔离：`FEICUI_DATA_DIR` 在 import `api` 前指到临时目录；`feicui` 夹具根亦为临时目录；
密钥文件 / 缓存 / rename_log 全落 tmp，真实用户目录一概不动。

跑法：
    ./venv/bin/python local-dist/domtest_yinyuan.py            # 打印读数 + 落盘 local-dist/build/readings-yinyuan-dom.json
    ./venv/bin/python local-dist/domtest_yinyuan.py --out /tmp/x.json --watchdog 180
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI_DIR))

#: ⚠️ 必须在 import api 之前设好（隔离）
SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-yy-dom-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from api import DATA_DIR, FeicuiApi  # noqa: E402
from src import pdf_library as lib  # noqa: E402
from src import yinyuan_client as yc  # noqa: E402
from selftest_yinyuan import PLAIN, FakeTransport, jresp, routes_ok  # noqa: E402

#: `app.py` 必须**按文件路径**加载（`api.py` 把 `server/` 插到 sys.path[0]，那里也有 `app` 包）
_spec = importlib.util.spec_from_file_location("feicui_webui_app_dom", WEBUI_DIR / "app.py")
assert _spec and _spec.loader
_webui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_webui_app)
build_window = _webui_app.build_window

PLACEHOLDER = WEBUI_DIR / "assets" / "test_seal.tiff"
READINGS = WEBUI_DIR / "build" / "readings-yinyuan-dom.json"

WIN = None
TRANSPORT = None
CLIENT = None
RESULT: dict = {"dom": {}, "checks": []}


def record(name: str, ok: bool, detail: str) -> None:
    RESULT["checks"].append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)


def _ev(expr: str):
    try:
        return WIN.evaluate_js(expr)
    except Exception as exc:
        RESULT.setdefault("js_errors", []).append(f"{type(exc).__name__}: {exc}")
        return None


def _read(name: str, expr: str) -> dict:
    raw = _ev(expr)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        data = {"raw": raw}
    RESULT["dom"][name] = data
    return data or {}


def _wait_js(expr: str, timeout: float = 20.0, every: float = 0.35) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _ev(expr):
            return True
        time.sleep(every)
    return False


JS_VIS = "const vis=el=>!!el&&!el.hidden&&el.offsetParent!==null;"


def build_fixture() -> Path:
    root = SCRATCH / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    a = root / lib.TIFF_DIR / "A特例"
    a.mkdir(parents=True, exist_ok=True)
    (a / "P001-C2-R3-长乐未央-汉-陈巨来.tiff").write_bytes(PLACEHOLDER.read_bytes())
    return root


def seed_caches(client: yc.YinyuanClient) -> dict:
    """预置作者/印文/朝代缓存（**不建 key** ⇒ 弹窗初始为未连接面）。"""
    client._write_secure(client._cache_path("dynasties"),
                         {"schema": yc.CACHE_SCHEMA, "name": "dynasties", "base_url": client.base_url,
                          "fetched_at": datetime.now().isoformat(), "fetched_ts": time.time(),
                          "count": 2,
                          "payload": {"total": 2, "items": [{"seq": 1, "value": "远1"},
                                                            {"seq": 2, "value": "远2"}],
                                      "counts": {}, "unrecorded": {}}})
    client._cache_write("authors", {"total": 2, "items": [
        {"id": "p0", "name": "作者0000", "courtesy_names": ["字0000"], "art_names": ["号0000"],
         "dynasty": "清中期"},
        {"id": "p1", "name": "作者0001", "courtesy_names": ["字0001"], "art_names": ["号0001"],
         "dynasty": "民國"}]}, count=2)
    client._cache_write("inscriptions", {"total": 3, "items": [
        {"id": "s0", "seal_name": "白文印0000", "transcription": "长乐未央", "author": "作者0000",
         "dynasty": "漢"},
        {"id": "s1", "seal_name": "白文印0001", "transcription": "长乐", "author": "作者0000",
         "dynasty": "漢"},
        {"id": "s2", "seal_name": "朱文印0002", "transcription": "未央", "author": "作者0001",
         "dynasty": "漢"}]}, count=3)
    return {"dynasty_values": ["远1", "远2"]}


# ───────────────────────── probe ─────────────────────────
def _probe_body() -> None:
    assert _wait_js("!!(window.pywebview && window.pywebview.api)", timeout=25), "桥未就绪"
    _wait_js("document.getElementById('view-main') && document.getElementById('view-main').classList.contains('active')",
             timeout=20)

    # ① 入口存在且可见
    entry = _read("entry", "(() => {" + JS_VIS + """
      const b=document.getElementById('btn-yy-open');
      return JSON.stringify({exists:!!b, visible:vis(b), text:b?b.textContent.trim():null,
        tag:b?b.tagName:null, modalHidden:document.getElementById('yinyuan-modal').hidden});
    })()""")
    record("dom/entry_visible",
           entry.get("exists") is True and entry.get("visible") is True
           and "yinyuan" in (entry.get("text") or "")
           and entry.get("modalHidden") is True,
           f"存在={entry.get('exists')} 可见={entry.get('visible')} 文案={entry.get('text')!r} "
           f"弹窗初始隐藏={entry.get('modalHidden')}")

    # ② 点击 ⇒ 登录框出现
    _ev("document.getElementById('btn-yy-open').click(); 1")
    opened = _wait_js("!document.getElementById('yinyuan-modal').hidden", timeout=8)
    form = _read("form", "(() => {" + JS_VIS + """
      const g=id=>document.getElementById(id);
      return JSON.stringify({modalOpen:!g('yinyuan-modal').hidden,
        formVisible:vis(g('yy-form')), connectedVisible:vis(g('yy-connected')),
        identType:g('yy-identifier').type, pwdType:g('yy-password').type,
        connectBtn:!!g('btn-yy-connect'), connectText:(g('btn-yy-connect')||{}).textContent,
        closeBtn:!!g('btn-yy-close')});
    })()""")
    record("dom/click_opens_login_form",
           opened and form.get("formVisible") is True and form.get("connectedVisible") is False
           and form.get("identType") == "text" and form.get("pwdType") == "password"
           and form.get("connectBtn") is True,
           f"弹窗打开={opened} 登录框可见={form.get('formVisible')} "
           f"已连接面可见={form.get('connectedVisible')} 输入类型={form.get('identType')}/"
           f"{form.get('pwdType')} 连接按钮={form.get('connectText')!r}")

    # ③ DOM 填表 → 点连接（口令故意带前后空格；不真登录，假 transport）
    _ev("""(() => {
      const i=document.getElementById('yy-identifier'); i.value='a@b.com';
      i.dispatchEvent(new Event('input',{bubbles:true}));
      const p=document.getElementById('yy-password'); p.value=' p@ss word ';
      p.dispatchEvent(new Event('input',{bubbles:true}));
      return 1; })()""")
    _ev("document.getElementById('btn-yy-connect').click(); 1")
    ok_conn = _wait_js("!document.getElementById('yy-connected').hidden", timeout=20)
    connected = _read("connected", "(() => {" + JS_VIS + """
      const g=id=>document.getElementById(id);
      const html=document.documentElement.outerHTML;
      const opts=[...document.querySelectorAll('#tab1-dynasty option')].map(o=>o.value);
      return JSON.stringify({connectedVisible:vis(g('yy-connected')), formHidden:g('yy-form').hidden,
        prefix:g('yy-prefix').textContent.trim(), label:g('yy-label').textContent.trim(),
        pillText:g('yy-pill').textContent.trim(), pillHidden:g('yy-pill').hidden,
        msg:g('yy-msg').textContent.trim(), tab1Options:opts,
        bodyLen:html.length});
    })()""")
    pwd_seen = [c["json"].get("password") for c in TRANSPORT.calls
                if c["path"] == "/api/v1/auth/login" and isinstance(c.get("json"), dict)]
    record("dom/connect_switches_to_connected_face",
           ok_conn and connected.get("connectedVisible") is True and connected.get("formHidden") is True
           and connected.get("prefix") == PLAIN[:11] and connected.get("pillHidden") is False
           and PLAIN[:11] in (connected.get("pillText") or ""),
           f"已连接面={connected.get('connectedVisible')} 前缀={connected.get('prefix')!r} "
           f"顶栏={connected.get('pillText')!r} 提示={connected.get('msg')!r}")
    record("dom/password_not_trimmed_through_bridge",
           pwd_seen == [" p@ss word "],
           f"transport 收到口令={pwd_seen!r}（原样 11 字符）")
    key_file = Path(CLIENT._key_path)
    html_has_plain = _ev(f"document.documentElement.outerHTML.indexOf({json.dumps(PLAIN)}) >= 0")
    record("dom/full_key_never_in_dom",
           html_has_plain is False and "plain" not in (connected.get("msg") or ""),
           f"整页 DOM 含完整明文={html_has_plain} DOM 长度={connected.get('bodyLen')}")
    record("dom/key_file_600",
           key_file.is_file() and stat.S_IMODE(os.stat(key_file).st_mode) == 0o600,
           f"{key_file} mode=" + (oct(stat.S_IMODE(os.stat(key_file).st_mode)) if key_file.exists() else "—"))

    # ⑥ tab1 朝代下拉：连接后取到 yinyuan 缓存值域
    record("dom/tab1_dynasty_from_yinyuan_cache",
           connected.get("tab1Options") == ["", "远1", "远2"],
           f"#tab1-dynasty options={connected.get('tab1Options')}")

    # ④ 断开 ⇒ 回登录框
    _ev("document.getElementById('btn-yy-disconnect').click(); 1")
    ok_disc = _wait_js("!document.getElementById('yy-form').hidden", timeout=15)
    after = _read("after_disconnect", "(() => {" + JS_VIS + """
      const g=id=>document.getElementById(id);
      return JSON.stringify({formVisible:vis(g('yy-form')), connectedVisible:vis(g('yy-connected')),
        pillHidden:g('yy-pill').hidden, keyExists:true}); })()""")
    record("dom/disconnect_back_to_form",
           ok_disc and after.get("formVisible") is True and after.get("connectedVisible") is False
           and after.get("pillHidden") is True and not key_file.exists(),
           f"登录框回到可见={after.get('formVisible')} 密钥文件已删={not key_file.exists()}")
    _ev("document.getElementById('btn-yy-close').click(); 1")

    # ⑤ tab3 候选补全（作者 / 释文）
    _ev("""(() => { const t=[...document.querySelectorAll('#tabs .tab')]
        .find(b=>b.dataset.tab==='3_Cropped_Tiff'); if(t){t.click();} return 1; })()""")
    grid_ok = _wait_js("document.querySelectorAll('#tab3-grid .thumb-item').length > 0", timeout=20)
    _ev("(() => { const d=document.querySelector('#tab3-grid .thumb-item'); if(d){d.click();} return 1; })()")
    edit_ok = _wait_js("!document.getElementById('tab3-edit').hidden", timeout=15)

    _ev("""(() => { const i=document.getElementById('tab3-author'); i.value='作者';
      i.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()""")
    pop = _wait_js("""(() => { const b=document.getElementById('tab3-author-suggest');
      return !b.hidden && b.querySelectorAll('.suggest-item').length > 0; })()""", timeout=15)
    sug = _read("author_suggest", """(() => {
      const b=document.getElementById('tab3-author-suggest');
      const items=[...b.querySelectorAll('.suggest-item')].map(x=>({v:x.dataset.value,t:x.textContent}));
      return JSON.stringify({hidden:b.hidden, count:items.length, items:items,
        firstValue:(b.querySelector('.suggest-item')||{}).dataset?b.querySelector('.suggest-item').dataset.value:null});
    })()""")
    record("dom/tab3_author_suggest_populated",
           grid_ok and edit_ok and pop and sug.get("count", 0) >= 1
           and (sug.get("items") or [{}])[0].get("v") == "作者0000",
           f"网格={grid_ok} 编辑面={edit_ok} 候选数={sug.get('count')} "
           f"首项={((sug.get('items') or [{}])[0]).get('t')!r}")

    _ev("(() => { const x=document.querySelector('#tab3-author-suggest .suggest-item'); if(x){x.click();} return 1; })()")
    picked = _read("author_picked", """(() => {
      const i=document.getElementById('tab3-author');
      const b=document.getElementById('tab3-author-suggest');
      return JSON.stringify({value:i.value, boxHidden:b.hidden, newname:document.getElementById('tab3-newname').textContent});
    })()""")
    record("dom/tab3_author_suggest_click_fills_input",
           picked.get("value") == "作者0000" and picked.get("boxHidden") is True,
           f"输入框={picked.get('value')!r} 候选框收起={picked.get('boxHidden')} "
           f"新名预览={picked.get('newname')!r}")

    _ev("""(() => { const i=document.getElementById('tab3-shiwen'); i.value='长乐';
      i.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()""")
    pop2 = _wait_js("""(() => { const b=document.getElementById('tab3-shiwen-suggest');
      return !b.hidden && b.querySelectorAll('.suggest-item').length > 0; })()""", timeout=15)
    sug2 = _read("shiwen_suggest", """(() => {
      const b=document.getElementById('tab3-shiwen-suggest');
      const items=[...b.querySelectorAll('.suggest-item')].map(x=>x.dataset.value);
      return JSON.stringify({count:items.length, items:items}); })()""")
    record("dom/tab3_shiwen_suggest_populated",
           pop2 and sug2.get("count", 0) >= 1 and "长乐未央" in (sug2.get("items") or []),
           f"候选={sug2.get('items')}")


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
    global WIN, TRANSPORT, CLIENT
    ap = argparse.ArgumentParser(description="斐萃 × yinyuan 连接入口 —— 渲染后 DOM 断言")
    ap.add_argument("--out", default=str(READINGS))
    ap.add_argument("--watchdog", type=float, default=180.0)
    args = ap.parse_args(argv)

    root = build_fixture()
    api = FeicuiApi()
    vr = api.verify_dir({"path": str(root)})
    users = [u for u, v in api._users.items() if v["is_admin"]]
    if not vr.get("ok") or not users:
        print(f"FIXTURE_FAIL verify_dir={vr} admin={users}", flush=True)
        return 2
    api.login({"username": users[0], "password": api._users[users[0]]["pwd"]})

    # 假上游：朝代值域用 `远1/远2`（与本地 15 类可区分），印文带「长乐未央」便于断言候选
    routes = routes_ok(dyn_values=("远1", "远2"), total_authors=2, total_inscriptions=3)
    routes[("GET", "/api/v1/inscriptions")] = lambda path, headers, body: jresp(200, {"ok": True, "data": {
        "total": 3, "limit": 200, "offset": 0, "items": [
            {"id": "s0", "collection": "seals", "seal_name": "白文印0000",
             "transcription": "长乐未央", "author": "作者0000", "dynasty": "漢", "seal_type": "白文"},
            {"id": "s1", "collection": "seals", "seal_name": "白文印0001",
             "transcription": "长乐", "author": "作者0000", "dynasty": "漢", "seal_type": "白文"},
            {"id": "s2", "collection": "faces", "seal_name": "朱文印0002",
             "transcription": "未央", "author": "作者0001", "dynasty": "漢", "seal_type": "朱文"}]}})
    TRANSPORT = FakeTransport(routes)
    CLIENT = yc.YinyuanClient(transport=TRANSPORT, data_dir=SCRATCH / "yy", label="斐萃-domtest")
    seeded = seed_caches(CLIENT)
    api.yinyuan = CLIENT
    RESULT["fixture"] = {"root": str(root), "data_dir": str(DATA_DIR), "yy_dir": str(SCRATCH / "yy"),
                         "seeded": seeded, "admin": users[0]}

    webview, WIN = build_window(api)
    threading.Timer(args.watchdog, lambda: (RESULT.setdefault("watchdog", "fired"), WIN.destroy())).start()
    print(f"DOMTEST_YINYUAN_START fixture={root} yy_dir={SCRATCH / 'yy'}", flush=True)
    webview.start(probe)

    counts = {s: sum(1 for c in RESULT["checks"] if c["status"] == s) for s in ("PASS", "FAIL")}
    payload = {"schema": "feicui.yinyuan.domtest.v1",
               "generated_at": datetime.now().isoformat(timespec="seconds"),
               "counts": counts, "checks": RESULT["checks"],
               "dom": RESULT.get("dom", {}), "fixture": RESULT.get("fixture"),
               "js_errors": RESULT.get("js_errors", []), "probe_error": RESULT.get("probe_error"),
               "watchdog": RESULT.get("watchdog")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"READINGS → {out}", flush=True)
    print(f"SUMMARY pass={counts['PASS']} fail={counts['FAIL']}", flush=True)
    if not os.environ.get("FEICUI_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
