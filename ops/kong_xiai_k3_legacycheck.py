#!/usr/bin/env python3
"""玺爱（xiai）· 本单补充取证：真浏览器里核对「既有 XAI-000x 未被改写 + 新编号格式」

复用自建 headless Chrome（独立 profile /tmp/xiai-kong3-prof、--remote-allow-origins=*）。
读真实 `localStorage`（键 `xiai:v1:seals`）逐行核对：
  - 8 行既有编号逐字为 XAI-0001…XAI-0008，且印文与种子一致；
  - 新行编号匹配 ^XA\\d{9}$ 且不与既有冲突；
  - 触一次写（再传一枚不同图）后前缀逐字比对，既有 8 行 JSON 完全不变。
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
SEED_LEGACY = [
    ("XAI-0001", "長壽"), ("XAI-0002", "騎都尉印"), ("XAI-0003", "昌"), ("XAI-0004", "文彭之印"),
    ("XAI-0005", "丁敬身印"), ("XAI-0006", "家在錢塘"), ("XAI-0007", "乾隆御覽之寶"), ("XAI-0008", "安持"),
]


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
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True,
                                              enable_multithread=True)
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
            return {"__error__": r["exceptionDetails"].get("text")}
        return (r.get("result") or {}).get("value")

    def goto(self, url, wait=1.6):
        self.send("Page.enable")
        self.send("Page.navigate", url=url)
        time.sleep(wait)
        return self.js("document.readyState")


def main():
    out = {"chrome": ensure_chrome(), "profile": UDD, "checks": []}

    def check(name, ok, detail):
        out["checks"].append({"name": name, "pass": bool(ok), "detail": str(detail)})

    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    tab.goto(f"{BASE}/", wait=2.2)

    out["seals_now"] = tab.js(
        "(async () => { const raw = JSON.parse(localStorage.getItem('xiai:v1:seals') || '[]');"
        " return raw.map(r => ({ stamp_id: r.stamp_id, seal_name: r.seal_name, source: r.source || null })); })()"
    )
    rows = out["seals_now"] or []
    legacy = [r for r in rows if r["stamp_id"].startswith("XAI-")]
    new = [r for r in rows if r["stamp_id"].startswith("XA") and not r["stamp_id"].startswith("XAI-")]
    check("既有 8 行编号与印文逐字一致（真 localStorage 读数）",
          [(r["stamp_id"], r["seal_name"]) for r in legacy] == SEED_LEGACY,
          json.dumps([(r["stamp_id"], r["seal_name"]) for r in legacy], ensure_ascii=False))
    check("新编号匹配 ^XA\\d{9}$（真 localStorage 读数）",
          all(len(r["stamp_id"]) == 11 and r["stamp_id"][:2] == "XA" and r["stamp_id"][2:].isdigit() for r in new) and len(new) >= 1,
          json.dumps([r["stamp_id"] for r in new], ensure_ascii=False))
    check("新编号不与既有冲突", len({r["stamp_id"] for r in rows}) == len(rows),
          f"rows={len(rows)} unique={len({r['stamp_id'] for r in rows})}")

    before = json.dumps(
        [r for r in (tab.js("(() => JSON.parse(localStorage.getItem('xiai:v1:seals') || '[]'))()") or [])
         if r["stamp_id"].startswith("XAI-")], ensure_ascii=False, sort_keys=True)
    # 再写一枚（不同图 ⇒ 不触发 dedupe），随后比对既有 8 行是否逐字未变
    out["second_write"] = tab.js(
        "(async () => {"
        " const seals = (await import('/src/services/index.js')).services.seals;"
        " const auth = (await import('/src/services/index.js')).services.auth;"
        " auth.login('16601061656','1234');"
        " const body = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==';"
        " const px = 'data:image/png;base64,' + btoa(body + '\\u0001\\u0002');"
        " const r = await seals.createSealWithFace(null, { seal_name: '', dynasty: '清', type: '鑒藏印', faceImage: px });"
        " return { ok: r.ok, deduped: r.deduped, stampId: r.stampId, message: r.message }; })()"
    )
    out["seals_after"] = tab.js(
        "(() => JSON.parse(localStorage.getItem('xiai:v1:seals') || '[]'))()"
    )
    rows2 = out["seals_after"] or []
    legacy2 = [r for r in rows2 if r["stamp_id"].startswith("XAI-")]
    after = json.dumps(legacy2, ensure_ascii=False, sort_keys=True)
    check("第二次写入后既有 8 行仍逐字未变（整行 JSON 逐字比对，含全部字段）",
          before == after, f"legacy_rows_json 长度 {len(before)} == {len(after)}；before[:80]={before[:80]}")
    check("第二次写入得到 XA000000002（递增不撞既有）",
          (out["second_write"] or {}).get("stampId") == "XA000000002",
          json.dumps(out["second_write"], ensure_ascii=False))

    out["passed"] = sum(1 for c in out["checks"] if c["pass"])
    out["failed"] = sum(1 for c in out["checks"] if not c["pass"])
    print(json.dumps(out, ensure_ascii=False, indent=2))
    path = "/Users/kevin/bistro/feicui/ops/kong_xiai_k3_legacycheck_raw.json"
    with open(path, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    sys.exit(0 if out["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
