#!/usr/bin/env python3
# 阶段 1c-修复 证据②③：用自建 headless Chrome 在 5164 上实测
#   ② location.href 必须停在 /feicui/（不跳回 5164 根）+ 页面必须显示「后端未启动」
#     且**不得**把 HTML 当接口响应体展示
#   ③ 刷新仍在 /feicui/；站内跳转保持 /feicui 前缀
# 另附：四页 DOM 文本（/、/jobs/:id、/jobs/:id/results、/jobs/:id/missing）
# 依赖：/usr/bin/python3 + websocket-client；临时 profile 落 /tmp，finally 里按 PID 收尾。
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

PORT = 9481
PROFILE = "/tmp/feicui-1c-fix-chrome"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ORIGIN = "http://localhost:5164"
OUTDIR = os.path.dirname(os.path.abspath(__file__))

import websocket  # noqa: E402


def port_open(p):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


shutil.rmtree(PROFILE, ignore_errors=True)
proc = subprocess.Popen(
    [
        CHROME,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--remote-allow-origins=*",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
results = []
steps_log = []

try:
    for _ in range(60):
        if port_open(PORT):
            break
        time.sleep(0.5)
    else:
        raise SystemExit("chrome devtools port never opened")

    ws_url = None
    for _ in range(40):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
            pages = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                ws_url = pages[0]["webSocketDebuggerUrl"]
                break
        except Exception:
            pass
        time.sleep(0.5)
    if not ws_url:
        raise SystemExit("no page target")

    ws = websocket.create_connection(ws_url, timeout=30)
    n = [0]

    def send(method, params=None):
        n[0] += 1
        mid = n[0]
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg

    def ev(expr):
        msg = send(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
        )
        r = msg.get("result", {})
        if "exceptionDetails" in r:
            return {"__error__": str(r["exceptionDetails"].get("text"))}
        return r.get("result", {}).get("value")

    # 收集本次导航窗口内的 console 错误（每文档重装一次探针）
    send(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": (
                "window.__errs=[];"
                "window.addEventListener('error',e=>window.__errs.push('error:'+(e.message||'')));"
                "window.addEventListener('unhandledrejection',e=>window.__errs.push('rejection:'+String(e.reason)));"
            )
        },
    )
    send("Page.enable")
    send("Runtime.enable")

    def settle(timeout=25.0, min_app=80):
        """等到文档就绪且 #app 有内容，再多等一点让 503 与横幅落定。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            rs = ev("document.readyState")
            applen = ev(
                "document.querySelector('#app') ? document.querySelector('#app').innerHTML.length : 0"
            )
            if rs == "complete" and isinstance(applen, int) and applen > min_app:
                break
            time.sleep(0.3)
        # 等 API 请求失败回流到状态（列表接口 + 横幅）
        deadline = time.time() + 6.0
        while time.time() < deadline:
            if ev("document.body.innerText.includes('后端未启动')") is True:
                break
            time.sleep(0.4)
        time.sleep(0.8)

    def snap(label, url, note=""):
        s = {
            "label": label,
            "requested_url": url,
            "note": note,
            "location_href": ev("location.href"),
            "location_pathname": ev("location.pathname"),
            "stays_in_feicui_prefix": ev("location.pathname.startsWith('/feicui/')"),
            "title": ev("document.title"),
            "has_backend_down_text": ev("document.body.innerText.includes('后端未启动')"),
            "has_not_connected_text": ev("document.body.innerText.includes('未连接')"),
            "shows_unknown_banner": ev(
                "document.body.innerText.includes('后端连通性未知')"
            ),
            "yinsuo_html_marker": ev(
                "document.documentElement.innerHTML.includes('\\u5370\\u7d22') ? 'YES' : 'NO'"
            ),
            "yinsuo_host_element": ev(
                "(() => { const i = document.documentElement.innerHTML.indexOf('\\u5370\\u7d22'); if (i < 0) return 'NOT_FOUND'; let n = document.body; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT); const hit = []; while (n) { if (n.innerHTML && n.innerHTML.includes('\\u5370\\u7d22') && !Array.from(n.children).some(c => c.innerHTML && c.innerHTML.includes('\\u5370\\u7d22'))) hit.push(n.tagName + '.' + (n.className || '')); n = w.nextNode(); } return hit.slice(0, 5).join(' | '); })()"
            ),
            "pre_texts": ev(
                "Array.from(document.querySelectorAll('pre')).map(p=>p.innerText.replace(/\\s+/g,' ').slice(0,160)).join(' ||| ')"
            ),
            "has_marketing_html_in_pre": ev(
                "Array.from(document.querySelectorAll('pre')).some(p=>p.innerHTML.includes('<!doctype')||p.innerHTML.includes('marketing')||p.innerHTML.includes('\\u5370\\u7d22'))"
            ),
            "app_text_len": ev(
                "document.querySelector('#app') ? document.querySelector('#app').innerText.trim().length : -1"
            ),
            "h_tags": ev(
                "Array.from(document.querySelectorAll('h1,h2,h3')).map(e=>e.innerText.trim()).filter(Boolean).slice(0,10).join(' | ')"
            ),
            "router_link_hrefs": ev(
                "Array.from(document.querySelectorAll('a[href]')).map(a=>a.getAttribute('href')).slice(0,14).join(' , ')"
            ),
            "script_srcs": ev(
                "Array.from(document.querySelectorAll('script[src]')).map(s=>s.getAttribute('src')).join(' , ')"
            ),
            "console_errors": ev("JSON.stringify(window.__errs || [])"),
            "body_text": ev("document.body.innerText.replace(/\\s+/g,' ').slice(0,500)"),
        }
        results.append(s)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        print("-" * 100)
        return s

    def nav_and_snap(label, url, note="", reload_after=False):
        ev("location.href")  # 预热一次 evaluate
        send("Page.navigate", {"url": url})
        settle()
        s = snap(label, url, note)
        if reload_after:
            send("Page.reload", {"ignoreCache": False})
            settle()
            r = snap(label + "-RELOAD", url, note + "（同地址刷新后）")
            r["_reload_of"] = s["label"]
            return s, r
        return s

    def dump_page_text(fname, label):
        txt = ev("document.body.innerText")
        with open(os.path.join(OUTDIR, fname), "w", encoding="utf-8") as f:
            f.write(f"# {label}\n# location: {ev('location.href')}\n\n{txt}\n")
        return txt

    # ── ② 打开 5164/feicui/ ────────────────────────────────────────────────
    nav_and_snap(
        "S1-open-5164-feicui",
        f"{ORIGIN}/feicui/",
        "② 打开直达地址：location 必须停在 /feicui/ 且显示「后端未启动」",
        reload_after=True,
    )

    # ── ③ 站内跳转（真实 router 客户端导航：点 nav 里的 RouterLink）────────
    send("Page.navigate", {"url": f"{ORIGIN}/feicui/jobs/abc"})
    settle()
    pre = snap("S2-open-deep-path", f"{ORIGIN}/feicui/jobs/abc", "③ 深路径直达，前缀必须保持")
    dump_page_text("dom-page-2-jobdetail.txt", "E2 /feicui/jobs/abc")
    clicked = ev(
        "(() => { const as = Array.from(document.querySelectorAll('a[href]'));"
        " const t = as.find(a => a.innerText.includes('结果页')) || as.find(a => a.innerText.includes('任务页'));"
        " if (!t) return 'NO_LINK_FOUND'; t.click(); return t.getAttribute('href'); })()"
    )
    time.sleep(2.5)
    send("Page.navigate", {"url": f"{ORIGIN}/feicui/jobs"})
    settle()
    snap(
        "S3-open-feicui-jobs",
        f"{ORIGIN}/feicui/jobs",
        "③ /feicui/jobs（无 :job_id ⇒ catch-all）必须仍在前缀内",
    )
    send("Page.navigate", {"url": f"{ORIGIN}/feicui/"})
    settle()
    inapp = ev(
        "(() => { const a = document.querySelector('nav a[href]'); if (!a) return 'NO_NAV_LINK';"
        " const before = location.pathname; const h = a.getAttribute('href'); a.click();"
        " return JSON.stringify({before, clicked_href: h}); })()"
    )
    time.sleep(2.0)
    snap(
        "S4-inapp-nav-click",
        f"{ORIGIN}/feicui/",
        f"③ 站内跳转取证（点 nav 的 RouterLink）：{inapp}；clicked_a_href={clicked}",
    )

    # ── 四页 DOM 文本 ──────────────────────────────────────────────────────
    pages = [
        (f"{ORIGIN}/feicui/", "dom-page-1-jobs.txt", "E1 /feicui/ 任务页"),
        (f"{ORIGIN}/feicui/jobs/abc", "dom-page-2-jobdetail.txt", "E2 /feicui/jobs/abc 任务详情"),
        (
            f"{ORIGIN}/feicui/jobs/abc/results",
            "dom-page-3-results.txt",
            "E3 /feicui/jobs/abc/results 结果页",
        ),
        (
            f"{ORIGIN}/feicui/jobs/abc/missing",
            "dom-page-4-missing.txt",
            "E5 /feicui/jobs/abc/missing 缺失清单",
        ),
    ]
    for url, fname, label in pages:
        send("Page.navigate", {"url": url})
        settle()
        dump_page_text(fname, label)
        snap(f"PAGE:{label}", url, "四页 DOM 文本（见同名 txt）")

    print("=== SUMMARY ===")
    print(
        json.dumps(
            [
                {
                    "label": r["label"],
                    "pathname": r["location_pathname"],
                    "stays": r["stays_in_feicui_prefix"],
                    "backend_down_text": r["has_backend_down_text"],
                    "yinsuo_html": r["yinsuo_html_marker"],
                    "marketing_in_pre": r["has_marketing_html_in_pre"],
                    "console_errors": r["console_errors"],
                }
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    with open(os.path.join(OUTDIR, "dom-fix-1c-raw.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ws.close()
finally:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    shutil.rmtree(PROFILE, ignore_errors=True)
    print(f"\n[cleanup] chrome pid={proc.pid} terminated; profile removed: {not os.path.exists(PROFILE)}")
