#!/usr/bin/env python3
"""玺爱（xiai）· 本单 UI 端到端取证（Kong）：真浏览器 · 真登录 · 真上传

自建 headless Chrome（独立 profile /tmp/xiai-kong3-prof、--remote-allow-origins=*，
**不动用户自己的 Chrome**、**不停 5163**）。全部断言走真实 DOM：
  ① 登录后侧栏文案（D-2 修后）
  ② 管理员在广场点「上传印章」→ 印文留空 + 朝代/分类/印面图 ⇒ 创建成功，广场卡片与详情页显示「佚名」
  ③ 缺朝代 ⇒ 表单反馈为「请补全必填项：朝代」
  ④ 既有 XAI-0001 详情页仍显示原印文（未被改写）
输出 JSON（stdout）落盘到 feicui/ops/kong_xiai_k3_uiflow_raw.json。
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UDD = "/tmp/xiai-kong3-prof"
PORT = 9433
BASE = "http://127.0.0.1:5163"
PHONE = "16601061656"
CODE = "1234"
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="


def http(path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10).read())


def ensure_chrome():
    try:
        http("/json/version")
        return "already"
    except Exception:
        pass
    subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
        f"--user-data-dir={UDD}", "--no-first-run", "--no-default-browser-check",
        "--disable-gpu", "--remote-allow-origins=*", "--window-size=1440,900", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            http("/json/version")
            return "started"
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("chrome did not start")


def new_target(url="about:blank"):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


class Tab:
    def __init__(self, ws_url):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=30,
                                              suppress_origin=True, enable_multithread=True)
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            return {"__error__": r["exceptionDetails"].get("text"),
                    "desc": (r.get("result") or {}).get("description", "")[:400]}
        return (r.get("result") or {}).get("value")

    def goto(self, url, wait=1.6):
        self.send("Page.enable")
        self.send("Page.navigate", url=url)
        time.sleep(wait)
        return self.js("document.readyState")


def main():
    out = {"chrome": ensure_chrome(), "profile": UDD, "port": PORT, "checks": []}

    def check(name, ok, detail):
        out["checks"].append({"name": name, "pass": bool(ok), "detail": str(detail)})

    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    tab.goto(f"{BASE}/", wait=2.0)
    # 干净起点：清空本 profile 的应用存储（与用户自己的浏览器无关）
    tab.js("(() => { localStorage.clear(); return Object.keys(localStorage).length; })()")
    tab.goto(f"{BASE}/", wait=2.0)

    # ---------------- ① 登录前后侧栏文案 ----------------
    out["sidebar_guest"] = tab.js("document.querySelector('.app-sidebar__foot').innerText.trim()")
    tab.goto(f"{BASE}/login", wait=1.4)
    tab.js(
        "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('input',{bubbles:true}));};"
        f" set(document.querySelector('#login-phone'), '{PHONE}');"
        f" set(document.querySelector('#login-code'), '{CODE}');"
        " document.querySelector('form.login__form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));"
        " return 1; })()"
    )
    time.sleep(1.8)
    out["after_login_path"] = tab.js("location.pathname")
    out["sidebar_logged"] = tab.js("document.querySelector('.app-sidebar__foot').innerText.trim()")
    out["sidebar_logged_html"] = tab.js("document.querySelector('.app-sidebar__foot').innerHTML.trim()")
    check("⑤ 侧栏・游客文案（真实 DOM）", out["sidebar_guest"] == "游客可自由浏览印章与印面。", out["sidebar_guest"])
    check("⑤ 侧栏・登录后文案真实变化（真实 DOM）",
          out["sidebar_logged"] == "登录后可提交勘误、上传实物照片。", out["sidebar_logged"])
    check("⑤ 侧栏文案在登录前后确实不同", out["sidebar_guest"] != out["sidebar_logged"],
          f"{out['sidebar_guest']} -> {out['sidebar_logged']}")

    # ---------------- ② 真上传：印文留空 + 朝代/分类/印面图 ----------------
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal\"]').click()")
    time.sleep(0.8)
    out["dialog_open"] = tab.js("!!document.querySelector('[data-admin-dialog=\"upload-seal\"]')")
    tab.js(f"window.__px = 'data:image/png;base64,{PNG_B64}'; 1")
    out["file_set"] = tab.js(
        "(async () => {"
        "  const input = document.querySelector('#upload-seal-face');"
        "  const blob = await (await fetch(window.__px)).blob();"
        "  const file = new File([blob], 'selftest-face.png', { type: 'image/png' });"
        "  const dt = new DataTransfer(); dt.items.add(file);"
        "  input.files = dt.files;"
        "  input.dispatchEvent(new Event('change', { bubbles: true }));"
        "  return input.files.length + '|' + (document.querySelector('.field__hint') ? 'hint' : '');"
        "})()"
    )
    tab.js(
        "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('change',{bubbles:true}));};"
        " set(document.querySelector('#upload-seal-dynasty'), '清');"
        " set(document.querySelector('#upload-seal-type'), '私印');"
        " return document.querySelector('#upload-seal-name').value; })()"
    )
    out["name_field_value"] = tab.js("document.querySelector('#upload-seal-name').value")
    out["name_label"] = tab.js("document.querySelector('label[for=\"upload-seal-name\"]').innerText.trim()")
    check("② 印文字段标签＝「印文（选填）」（真实 DOM）", out["name_label"] == "印文（选填）", out["name_label"])
    check("② 印文字段留空即提交（未填任何值）", out["name_field_value"] == "", f"value={out['name_field_value']!r}")

    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(2.2)
    out["upload_feedback"] = tab.js(
        "(document.querySelector('[data-admin-feedback=\"square-upload\"]') || document.querySelector('[data-admin-feedback=\"upload-seal\"]') || {}).innerText || ''"
    )
    out["notice_html"] = tab.js("(() => { const n = document.querySelector('.square__notice'); return n ? n.innerText : null; })()")
    check("② 印文留空 + 朝代/分类/印面图齐备 ⇒ 真上传成功（反馈文案）",
          "已新增印章" in (out["upload_feedback"] or "") and "请补全必填项" not in (out["upload_feedback"] or ""),
          out["upload_feedback"])

    # 新建印章的卡片真读数（按编号定位卡片）
    out["new_card"] = tab.js(
        "(() => { const cards = [...document.querySelectorAll('.seal-card')];"
        " const card = cards.find(c => c.innerText.includes('XA000000001'));"
        " if (!card) return null;"
        " return { title: card.querySelector('.seal-card__title').innerText.trim(),"
        "   dds: [...card.querySelectorAll('dd')].map(d => d.innerText.trim()),"
        "   link: card.querySelector('.seal-card__title a').getAttribute('href') }; })()"
    )
    check("② 广场卡片：标题＝「佚名」、当前印文＝「佚名」、编号＝XA000000001（真实 DOM）",
          bool(out["new_card"]) and out["new_card"]["title"] == "佚名" and "XA000000001" in out["new_card"]["dds"]
          and "佚名" in out["new_card"]["dds"],
          json.dumps(out["new_card"], ensure_ascii=False))

    # ③ 缺朝代 ⇒ 表单反馈
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal\"]').click()")
    time.sleep(0.7)
    tab.js(
        "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('change',{bubbles:true}));};"
        " set(document.querySelector('#upload-seal-type'), '私印');"
        " document.querySelector('#upload-seal-dynasty').value = '';"
        " return 1; })()"
    )
    tab.js(
        "(async () => { const input = document.querySelector('#upload-seal-face');"
        f" const blob = await (await fetch('data:image/png;base64,{PNG_B64}')).blob();"
        " const file = new File([blob], 'selftest-face2.png', { type: 'image/png' });"
        " const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;"
        " input.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()"
    )
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(1.6)
    out["missing_dynasty_feedback"] = tab.js(
        "(document.querySelector('[data-admin-feedback=\"upload-seal\"]') || {}).innerText || ''"
    )
    out["seal_count_after_reject"] = tab.js(
        "(() => JSON.parse(localStorage.getItem('xiai:v1:seals') || '[]').length)()"
    )
    check("③ 缺朝代 ⇒ 真表单反馈为「请补全必填项：朝代」",
          "请补全必填项：朝代" in (out["missing_dynasty_feedback"] or ""), out["missing_dynasty_feedback"])
    check("③ 拒绝后印章总数仍为 9（8 枚既有 + 1 枚新建；无半成品）",
          out["seal_count_after_reject"] == 9, str(out["seal_count_after_reject"]))
    tab.js("(() => { const b = [...document.querySelectorAll('.upload-box__foot button')][0]; if (b) b.click(); return 1; })()")

    # ④ 详情页真读数 + 既有行未被改写
    tab.goto(f"{BASE}/seal/XA000000001", wait=2.0)
    out["detail_new"] = tab.js(
        "(() => ({ h1: (document.querySelector('h1') || {}).innerText,"
        "   faceName: (document.querySelector('.face-block__name') || {}).innerText,"
        "   stampTag: (document.querySelector('.detail__id') || {}).innerText,"
        "   body: document.body.innerText.includes('佚名') }))()"
    )
    check("② 详情页（真 DOM）h1＝「佚名」、印面名＝「佚名」、编号含 XA000000001",
          out["detail_new"]["h1"] == "佚名" and out["detail_new"]["faceName"] == "佚名"
          and "XA000000001" in (out["detail_new"]["stampTag"] or ""),
          json.dumps(out["detail_new"], ensure_ascii=False))

    tab.goto(f"{BASE}/seal/XAI-0001", wait=2.0)
    out["detail_legacy"] = tab.js(
        "(() => ({ h1: (document.querySelector('h1') || {}).innerText,"
        "   stampTag: (document.querySelector('.detail__id') || {}).innerText }))()"
    )
    check("① 既有 XAI-0001 详情页仍为「長壽」（既有行逐字未改写）",
          out["detail_legacy"]["h1"] == "長壽", json.dumps(out["detail_legacy"], ensure_ascii=False))

    out["passed"] = sum(1 for c in out["checks"] if c["pass"])
    out["failed"] = sum(1 for c in out["checks"] if not c["pass"])
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open("/Users/kevin/bistro/feicui/ops/kong_xiai_k3_uiflow_raw.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    sys.exit(0 if out["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
