#!/usr/bin/env python3
"""玺爱（xiai）· K5b：「重新上传印面图」只对 FACE（印面）呈现 —— 真浏览器取证（Kong）

背景：K5 给每个印面块都加了管理员按钮，边款（EDGE）块也出现（点击改的是该边款印面的
face_image_id，画面不变）。本单把条件收紧为 `canReplaceFaceImage && !face.isEdge`。

自建 headless Chrome（独立 profile /tmp/xiai-kong5b-prof，端口 9444，--remote-allow-origins=*）：
**不动用户自己的 Chrome（9434）**、**不停 5163**、**不占 5173/5174**。

覆盖：
  ① 管理员 /seal/XAI-0001：face-block 总数 / FACE 块数 / EDGE 块数 / 按钮计数，逐块映射
     （块 → 类型 → 是否有按钮 → data-face-id）；按钮数必须 == FACE 块数（修复前 3，修复后 2）
  ①′ 管理员扫全部含边款样本（XAI-0004 / 0005 / 0007）：EDGE 块上按钮 DOM 零命中
  ② 数据层探针（只读语义，不写入）：对 EDGE 印面 fc-0001-e1 调 replaceFaceImage 空内容
     ⇒ 返回 EMPTY_CONTENT（而非按 kind 拒绝）＝ 数据层未按 kind 拦 EDGE（如实登记）
  ③ 普通用户（13800000001）：按钮计数 0 + 按钮文案（body 文本）零命中
  ④ 游客（未登录）：同上全零
输出：feicui/ops/kong_k5b_edge_*_raw.json / .txt
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UDD = "/tmp/xiai-kong5b-prof"
PORT = 9444
BASE = "http://127.0.0.1:5163"
ADMIN = "16601061656"
NORMAL = "13800000001"
CODE = "1234"
SEAL = "XAI-0001"
EDGE_SEALS = ["XAI-0001", "XAI-0004", "XAI-0005", "XAI-0007"]
OUT_PREFIX = "/Users/kevin/bistro/xiai/feicui/ops/kong_k5b_edge_"
OUT_JSON = OUT_PREFIX + "selftest_raw.json"
OUT_TXT = OUT_PREFIX + "selftest_raw.txt"

ROLE_PROBE = """
(async () => {
  const s = await import('/src/data/session.js');
  const u = s.currentUser();
  return { loggedIn: !!u, role: u ? u.role : null, phone: u ? (u.phone || null) : null,
           isAdmin: !!s.isAdmin.value };
})()
"""

# 逐块读数：块的 kind（按徽标文案）/ 是否有「重新上传印面图」按钮 / 该按钮的 data-face-id
BLOCK_SCAN = """
(() => {
  const blocks = Array.from(document.querySelectorAll('.face-block'));
  const mk = (b) => {
    const badge = b.querySelector('.face-block__badge');
    const isEdge = !!(badge && badge.classList.contains('face-block__badge--edge'));
    return { label: badge ? badge.textContent.trim() : '', isEdge };
  };
  const rows = blocks.map((b, i) => {
    const { label, isEdge } = mk(b);
    const btn = b.querySelector('[data-admin-action="replace-face-image"]');
    return {
      index: i,
      label,
      isEdge,
      kind: isEdge ? '边款' : '印面',
      faceId: b.querySelector('.face-block__id') ? b.querySelector('.face-block__id').textContent.trim() : '',
      hasReplaceBtn: !!btn,
      btnFaceId: btn ? (btn.getAttribute('data-face-id') || '') : null
    };
  });
  const btnSel = '[data-admin-action="replace-face-image"]';
  const bodyText = document.body.innerText || '';
  const html = document.documentElement.outerHTML || '';
  const ctx = [];
  let from = 0;
  while (ctx.length < 4) {
    const at = html.indexOf('重新上传印面图', from);
    if (at < 0) break;
    ctx.push(html.slice(Math.max(0, at - 90), at + 30));
    from = at + 1;
  }
  return {
    faceBlocks: blocks.length,
    faceCount: rows.filter((r) => !r.isEdge).length,
    edgeCount: rows.filter((r) => r.isEdge).length,
    replaceBtnCount: document.querySelectorAll(btnSel).length,
    editBtnCount: document.querySelectorAll('[data-admin-action="edit-fixed-attributes"]').length,
    edgeBlocksWithReplaceBtn: rows.filter((r) => r.isEdge && r.hasReplaceBtn).length,
    faceBlocksWithReplaceBtn: rows.filter((r) => !r.isEdge && r.hasReplaceBtn).length,
    textHits: bodyText.split('重新上传印面图').length - 1,
    htmlHits: html.split('重新上传印面图').length - 1,
    htmlHitContexts: ctx,
    rows
  };
})()
"""

# 数据层探针：**空内容**（不产生任何写入）——若按 kind 拦 EDGE，应当在 kind 处先拒；
# 实返回 EMPTY_CONTENT ⇒ 数据层放行到内容校验，即未按 kind 拦 EDGE。
DATA_PROBE_EDGE = """
(async () => {
  const seals = await import('/src/services/seals.js');
  const before = (await import('/src/data/db.js')).listFaceRows().find((r) => r.id === 'fc-0001-e1');
  const res = await seals.replaceFaceImage('fc-0001-e1', {});
  const after = (await import('/src/data/db.js')).listFaceRows().find((r) => r.id === 'fc-0001-e1');
  return {
    edgeFaceRowKind: before ? before.kind : null,
    edgeFaceImageIdBefore: before ? before.face_image_id : null,
    result: { ok: res.ok, reason: res.reason || null, message: res.message },
    edgeFaceImageIdAfter: after ? after.face_image_id : null,
    wroteAnything: JSON.stringify(before) !== JSON.stringify(after)
  };
})()
"""


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
        self.ws = websocket.create_connection(ws_url, timeout=40,
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
                    "desc": ((r.get("exceptionDetails") or {}).get("exception") or {}).get("description", "")[:600]}
        return (r.get("result") or {}).get("value")

    def goto(self, url, wait=2.0):
        self.send("Page.enable")
        self.send("Page.navigate", url=url)
        time.sleep(wait)
        return self.js("document.readyState")

    def wait_for(self, expr, timeout=12.0, step=0.25):
        end = time.time() + timeout
        while time.time() < end:
            v = self.js(expr)
            if v:
                return v
            time.sleep(step)
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    out = {"meta": {
        "task": "k5b: replace-face-image button restricted to FACE blocks",
        "base": BASE, "chrome_profile": UDD, "port": PORT,
        "admin": ADMIN, "normal": NORMAL, "code": CODE,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }, "checks": []}

    def check(name, ok, detail):
        out["checks"].append({"name": name, "pass": bool(ok), "detail": detail})

    out["chrome"] = ensure_chrome()
    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    try:
        tab.goto(f"{BASE}/", wait=2.0)
        tab.js("(() => { localStorage.clear(); return 1; })()")
        tab.goto(f"{BASE}/", wait=2.2)

        def login(phone):
            tab.goto(f"{BASE}/login", wait=1.5)
            tab.js(
                "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('input',{bubbles:true}));};"
                f" set(document.querySelector('#login-phone'), '{phone}');"
                f" set(document.querySelector('#login-code'), '{CODE}');"
                " document.querySelector('form.login__form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));"
                " return 1; })()"
            )
            time.sleep(1.9)
            return tab.js("location.pathname")

        def logout():
            tab.js("(async () => { const a = await import('/src/services/auth.js'); a.logout(); return 1; })()")
            tab.goto(f"{BASE}/", wait=1.6)

        # ---------------- 游客 ----------------
        tab.goto(f"{BASE}/seal/{SEAL}", wait=2.2)
        out["guest_role"] = tab.js(ROLE_PROBE)
        out["guest"] = tab.js(BLOCK_SCAN)
        g = out["guest"]
        check("guest: replace 按钮全页面零命中",
              g["replaceBtnCount"] == 0,
              f"replaceBtnCount={g['replaceBtnCount']} faceBlocks={g['faceBlocks']}")
        check("guest: body 文本零命中「重新上传印面图」",
              g["textHits"] == 0, f"textHits={g['textHits']} htmlHits={g['htmlHits']}")

        # ---------------- 普通用户 ----------------
        out["normal_login_path"] = login(NORMAL)
        out["normal_role"] = tab.js(ROLE_PROBE)
        tab.goto(f"{BASE}/seal/{SEAL}", wait=2.2)
        out["normal"] = tab.js(BLOCK_SCAN)
        n = out["normal"]
        check("normal: replace 按钮全页面零命中",
              n["replaceBtnCount"] == 0,
              f"replaceBtnCount={n['replaceBtnCount']} role={out['normal_role']}")
        check("normal: body 文本零命中「重新上传印面图」",
              n["textHits"] == 0, f"textHits={n['textHits']} htmlHits={n['htmlHits']}")

        # ---------------- 管理员 ----------------
        logout()
        out["admin_login_path"] = login(ADMIN)
        out["admin_role"] = tab.js(ROLE_PROBE)
        tab.goto(f"{BASE}/seal/{SEAL}", wait=2.4)
        out["admin_0001"] = tab.js(BLOCK_SCAN)
        a = out["admin_0001"]
        check("admin XAI-0001: 按钮数 == FACE 块数",
              a["replaceBtnCount"] == a["faceCount"],
              f"replaceBtnCount={a['replaceBtnCount']} faceCount={a['faceCount']} edgeCount={a['edgeCount']}")
        check("admin XAI-0001: EDGE 块上按钮零命中",
              a["edgeBlocksWithReplaceBtn"] == 0,
              f"edgeBlocksWithReplaceBtn={a['edgeBlocksWithReplaceBtn']} edgeCount={a['edgeCount']}")
        check("admin XAI-0001: 每个 FACE 块都有按钮",
              a["faceBlocksWithReplaceBtn"] == a["faceCount"],
              f"faceBlocksWithReplaceBtn={a['faceBlocksWithReplaceBtn']} faceCount={a['faceCount']}")

        # ---------------- 其它含边款样本 ----------------
        per_seal = {}
        for sid in EDGE_SEALS:
            tab.goto(f"{BASE}/seal/{sid}", wait=2.0)
            r = tab.js(BLOCK_SCAN)
            per_seal[sid] = {k: r[k] for k in
                             ("faceBlocks", "faceCount", "edgeCount", "replaceBtnCount",
                              "edgeBlocksWithReplaceBtn", "faceBlocksWithReplaceBtn")}
            per_seal[sid]["rows"] = [{"kind": x["kind"], "faceId": x["faceId"], "hasReplaceBtn": x["hasReplaceBtn"]}
                                     for x in r["rows"]]
        out["admin_edge_seals"] = per_seal
        tot_face = sum(v["faceCount"] for v in per_seal.values())
        tot_btn = sum(v["replaceBtnCount"] for v in per_seal.values())
        tot_edge_btn = sum(v["edgeBlocksWithReplaceBtn"] for v in per_seal.values())
        check("admin 全含边款样本: Σ按钮 == ΣFACE 块 且 EDGE 块按钮零命中",
              tot_btn == tot_face and tot_edge_btn == 0,
              f"Σface={tot_face} Σbtn={tot_btn} ΣedgeBtn={tot_edge_btn}")

        # ---------------- 数据层探针（EDGE，不写入） ----------------
        tab.goto(f"{BASE}/seal/{SEAL}", wait=2.0)
        out["data_probe_edge"] = tab.js(DATA_PROBE_EDGE)
        dp = out["data_probe_edge"]
        check("数据层未按 kind 拦 EDGE（如实登记：空内容 ⇒ EMPTY_CONTENT 而非按 kind 拒）",
              dp is not None and not dp.get("wroteAnything"),
              json.dumps(dp, ensure_ascii=False)[:400])

        out["meta"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        out["all_pass"] = all(c["pass"] for c in out["checks"])
    finally:
        tab.close()

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    lines = [f"# K5b 真浏览器取证（管理员 / 普通用户 / 游客）{out['meta']['started_at']}",
             f"chrome={out['chrome']} profile={UDD} port={PORT}",
             f"admin role={out.get('admin_role')} normal role={out.get('normal_role')}",
             ""]
    for c in out["checks"]:
        lines.append(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['name']} :: {c['detail']}")
    a = out.get("admin_0001") or {}
    lines += ["", "## 管理员 /seal/XAI-0001 逐块映射",
              f"faceBlocks={a.get('faceBlocks')} FACE={a.get('faceCount')} EDGE={a.get('edgeCount')} "
              f"replaceBtn={a.get('replaceBtnCount')} editBtn={a.get('editBtnCount')}"]
    for r in (a.get("rows") or []):
        lines.append(f"  #{r['index']} kind={r['kind']} faceId={r['faceId']} "
                     f"hasReplaceBtn={r['hasReplaceBtn']} btnFaceId={r['btnFaceId']}")
    lines += ["", "## 全含边款样本",
              json.dumps(out.get("admin_edge_seals"), ensure_ascii=False, indent=2),
              "", "## 数据层探针",
              json.dumps(out.get("data_probe_edge"), ensure_ascii=False),
              "", "## 游客 / 普通用户",
              f"guest: {json.dumps({k: v for k, v in (out.get('guest') or {}).items() if k != 'rows'}, ensure_ascii=False)}",
              "guest role: " + json.dumps(out.get('guest_role'), ensure_ascii=False),
              "guest htmlHitContexts: " + json.dumps((out.get('guest') or {}).get('htmlHitContexts'), ensure_ascii=False),
              "normal role: " + json.dumps(out.get('normal_role'), ensure_ascii=False),
              f"normal: {json.dumps({k: v for k, v in (out.get('normal') or {}).items() if k != 'rows'}, ensure_ascii=False)}",
              "normal htmlHitContexts: " + json.dumps((out.get('normal') or {}).get('htmlHitContexts'), ensure_ascii=False),
              "", f"all_pass={out.get('all_pass')}"]
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
