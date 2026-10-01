#!/usr/bin/env python3
"""一次性 CDP 驱动：导航 + 执行 JS + 打印 console/异常/4xx 报告。

用法：cdp_drive.py <url> <js_file> [port=9711] [wait_ms=4000]
JS 文件内容为一个表达式；建议写成 async IIFE 并 return JSON.stringify(...)。
"""
import json
import sys
import time
import urllib.request

import websocket  # websocket-client

port = int(sys.argv[3]) if len(sys.argv) > 3 else 9711
wait_ms = int(sys.argv[4]) if len(sys.argv) > 4 else 4000
url = sys.argv[1]
js = open(sys.argv[2], "r", encoding="utf-8").read()

# 新建一个 tab（PUT /json/new?url），避免污染既有 tab
req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
target = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
ws_url = target["webSocketDebuggerUrl"]

ws = websocket.create_connection(ws_url, timeout=120, max_size=64 * 1024 * 1024)
mid = 0
events = []


def send(method, **params):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg
        events.append(msg)


for dom in ("Runtime.enable", "Page.enable", "Network.enable", "Log.enable"):
    send(dom)

send("Page.navigate", url=url)
time.sleep(wait_ms / 1000.0)

res = send("Runtime.evaluate", expression=js, awaitPromise=True, returnByValue=True,
           userGesture=True)
value = res.get("result", {}).get("result", {}).get("value")
exc = res.get("result", {}).get("exceptionDetails")

print("=== EVAL RESULT ===")
print(value if value is not None else json.dumps(exc, ensure_ascii=False)[:4000])

console, fails, bad = [], [], []
for ev in events:
    m = ev.get("method")
    p = ev.get("params", {})
    if m == "Runtime.consoleAPICalled":
        console.append({"type": p.get("type"),
                        "args": [a.get("value") or a.get("description") for a in p.get("args", [])]})
    elif m == "Runtime.exceptionThrown":
        console.append({"type": "EXCEPTION",
                        "args": [p.get("exceptionDetails", {}).get("text"),
                                 (p.get("exceptionDetails", {}).get("exception") or {}).get("description")]})
    elif m == "Network.loadingFailed":
        fails.append({"url": p.get("requestId"), "err": p.get("errorText")})
    elif m == "Network.responseReceived":
        r = p.get("response", {})
        if r.get("status", 200) >= 400:
            bad.append({"status": r.get("status"), "url": r.get("url")})

print("=== CONSOLE (%d) ===" % len(console))
for c in console[:40]:
    print(json.dumps(c, ensure_ascii=False)[:600])
print("=== NETWORK FAILED (%d) ===" % len(fails))
for f in fails[:20]:
    print(json.dumps(f, ensure_ascii=False))
print("=== HTTP >=400 (%d) ===" % len(bad))
for b in bad[:40]:
    print(json.dumps(b, ensure_ascii=False))
ws.close()
