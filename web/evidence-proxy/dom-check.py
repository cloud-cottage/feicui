#!/usr/bin/env python3
# 阶段 1c 证据：用自建 headless Chrome 在 http://localhost:5164/feicui/ 上取真实 DOM，
# 证明「直达后 feicui 前端确实挂载」（不是 5164 的 SPA 兜底页）。
# 依赖：/usr/bin/python3 + websocket-client。临时 profile 放 /tmp，退出时按精确 PID 收尾。
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

PORT = 9479
PROFILE = "/tmp/feicui-1c-chrome"
TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5164/feicui/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

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

    def ev(expr):
        n[0] += 1
        ws.send(
            json.dumps(
                {
                    "id": n[0],
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
                }
            )
        )
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == n[0]:
                r = msg.get("result", {})
                if "exceptionDetails" in r:
                    return {"error": str(r["exceptionDetails"].get("text"))}
                return r.get("result", {}).get("value")

    ev("location.href")
    ws.send(json.dumps({"id": 900, "method": "Page.navigate", "params": {"url": TARGET_URL}}))
    time.sleep(5)

    out = {
        "target": TARGET_URL,
        "location": ev("location.href"),
        "title": ev("document.title"),
        "app_mount_text_len": ev(
            "document.querySelector('#app') ? document.querySelector('#app').innerText.trim().length : -1"
        ),
        "app_html_len": ev("document.querySelector('#app') ? document.querySelector('#app').innerHTML.length : -1"),
        "h_tags": ev(
            "Array.from(document.querySelectorAll('h1,h2,h3')).map(e=>e.innerText.trim()).filter(Boolean).slice(0,8).join(' | ')"
        ),
        "links": ev(
            "Array.from(document.querySelectorAll('a')).map(a=>a.getAttribute('href')).slice(0,12).join(' , ')"
        ),
        "has_yinsuo_marker": ev(
            "document.documentElement.innerHTML.includes('印索') ? 'YES' : 'NO'"
        ),
        "yinsuo_context": ev(
            "(() => { const h = document.documentElement.innerHTML; const i = h.indexOf('\\u5370\\u7d22'); return i < 0 ? 'NOT_FOUND' : JSON.stringify(h.slice(Math.max(0, i - 90), i + 90)); })()"
        ),
        "yinsuo_host_element": ev(
            "(() => { const i = document.documentElement.innerHTML.indexOf('\\u5370\\u7d22'); if (i < 0) return 'NOT_FOUND'; let n = document.body; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT); const hit = []; while (n) { if (n.innerHTML && n.innerHTML.includes('\\u5370\\u7d22') && !Array.from(n.children).some(c => c.innerHTML && c.innerHTML.includes('\\u5370\\u7d22'))) hit.push(n.tagName + '.' + (n.className || '')); n = w.nextNode(); } return hit.slice(0, 5).join(' | '); })()"
        ),
        "notice_text": ev(
            "(() => { const t = document.body.innerText.replace(/\\s+/g, ' '); const i = t.indexOf('响应体'); return i < 0 ? 'NOT_FOUND' : t.slice(Math.max(0, i - 120), i + 160); })()"
        ),
        "has_feicui_marker": ev(
            "document.documentElement.innerHTML.includes('feicui') || document.documentElement.innerHTML.includes('印谱') ? 'YES' : 'NO'"
        ),
        "script_srcs": ev("Array.from(document.querySelectorAll('script[src]')).map(s=>s.getAttribute('src')).join(' , ')"),
        "body_text_head": ev("document.body.innerText.replace(/\\s+/g,' ').slice(0,300)"),
        "console_errors": ev(
            "JSON.stringify(window.__errs || [])"
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ws.close()
finally:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    for leftover in (PROFILE,):
        shutil.rmtree(leftover, ignore_errors=True)
    print(f"\n[cleanup] chrome pid={proc.pid} terminated; profile removed: {not os.path.exists(PROFILE)}")
