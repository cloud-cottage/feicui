#!/usr/bin/env python3
"""玺爱（xiai）· D-2 侧栏登录态 —— 真机 DOM 取证（Kong，本单）

自建 headless Chrome + 独立 profile + --remote-allow-origins=*（不动用户自己的 Chrome，
不停 5163）。流程：访问 / → 读侧栏页脚文本（游客）→ 经登录页登录管理员 →
读侧栏页脚文本（登录后）。两次读数逐字打印，供改前 / 改后对比。

用法：python3 kong_xiai_k3_domcheck.py [pre|post]
"""
import json
import sys
import time
import urllib.parse
import urllib.request
import subprocess

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UDD = "/tmp/xiai-kong3-prof"
PORT = 9433
BASE = "http://127.0.0.1:5163"
PHONE = "16601061656"
CODE = "1234"


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
        "--disable-gpu", "--remote-allow-origins=*", "--window-size=1440,900",
        "about:blank",
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
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    started = ensure_chrome()
    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    tab.goto(f"{BASE}/", wait=2.0)

    out = {"mode": mode, "chrome": started, "profile": UDD, "port": PORT}

    def snapshot(tag):
        return tab.js(
            "(() => { const f = document.querySelector('.app-sidebar__foot');"
            " return { foot: f ? f.innerText.replace(/\\s+/g,' ').trim() : null,"
            "   foot_html: f ? f.innerHTML.trim() : null,"
            "   header: (document.querySelector('.app-header') || {}).innerText || '' ,"
            "   path: location.pathname }; })()"
        )

    # 游客态（先确保未登录：直接清登录态键后重载，避免沿用上一轮 profile 登录态）
    tab.js("(() => { try { localStorage.removeItem('xiai:v1:session'); } catch(e) {} return 1; })()")
    tab.goto(f"{BASE}/", wait=1.8)
    guest = snapshot("guest")
    out["guest"] = guest

    # 登录（管理员：唯一管理员手机号 + 演示验证码 1234）
    tab.goto(f"{BASE}/login", wait=1.5)
    tab.js(
        "(() => { const p = document.querySelector('#login-phone');"
        " const c = document.querySelector('#login-code');"
        " if (!p || !c) return 'no-form';"
        " const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); };"
        f" set(p, '{PHONE}'); set(c, '{CODE}');"
        " const form = document.querySelector('form.login__form');"
        " form.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));"
        " return 'submitted'; })()"
    )
    time.sleep(1.8)
    out["after_login_path"] = tab.js("location.pathname")
    out["logged_in_user"] = tab.js(
        "(() => { try { const raw = localStorage.getItem('xiai:v1:session');"
        " return raw ? JSON.parse(raw) : null; } catch(e) { return String(e); } })()"
    )
    logged = snapshot("logged")
    out["logged"] = logged
    out["changed"] = (guest.get("foot") != logged.get("foot"))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
