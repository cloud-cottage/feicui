#!/usr/bin/env python3
"""玺爱（xiai）· 「重新上传印面图」端到端取证（Kong）：真浏览器 · 真登录 · 真上传 · 真替换

自建 headless Chrome（独立 profile /tmp/xiai-kong5-prof、--remote-allow-origins=*，
**不动用户自己的 Chrome**、**不停 5163**、**不占 5173/5174**）。

覆盖：
  ① 权限两道门（DOM）：管理员每个印面块都有按钮；普通用户 / 游客 DOM 命中数 = 0
  ①′ 权限两道门（数据层，绕过 UI，页内直调真实模块）：普通用户调 ⇒ FORBIDDEN 且库零变化
  ② 端到端替换：3000×1200 非方形图 ⇒ 方形 WebP 入库；印面指向改；旧影像行与二进制仍在；**不刷新即显示新图**
  ②′ 第二次替换：第一次的二进制仍在且字节一致（旧图不删）
  ③ 回滚 / 原子（浏览器内注入 IDB 写失败）⇒ 无半成品行、指向不变、无孤儿二进制
  ④ 持久化：关标签重开（Page.navigate 全新加载）后新图仍显示
  ⑤ 全量网络捕获：不得出现 5196 / square-crop / 任何外部 URL

输出 JSON 到 feicui/ops/kong_xiai_k5_replace_face_image_uiflow_raw.json（+ 文本纪要 .txt）。
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UDD = "/tmp/xiai-kong5-prof"
PORT = 9434
BASE = "http://127.0.0.1:5163"
ADMIN = "16601061656"
NORMAL = "13800000001"  # 旧管理员号，现已是普通用户
CODE = "1234"
SEAL = "XAI-0001"
FACE = "fc-0001-f1"
OUT_JSON = "/Users/kevin/bistro/feicui/ops/kong_xiai_k5_replace_face_image_uiflow_raw.json"
OUT_TXT = "/Users/kevin/bistro/feicui/ops/kong_xiai_k5_replace_face_image_uiflow_raw.txt"

# 页内造一张 **3000 × 1200** 的非方形图（canvas → JPEG），全程本机、不访问外部地址
MAKE_IMAGE = """
(async () => {
  const c = document.createElement('canvas');
  c.width = 3000; c.height = 1200;
  const g = c.getContext('2d');
  const grad = g.createLinearGradient(0, 0, 3000, 1200);
  grad.addColorStop(0, '#b0301a'); grad.addColorStop(0.5, '#d8c7a5'); grad.addColorStop(1, '#2a3f6b');
  g.fillStyle = grad; g.fillRect(0, 0, 3000, 1200);
  for (let i = 0; i < 240; i++) {
    g.fillStyle = i % 2 ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.30)';
    g.fillRect((i * 37) % 3000, (i * 91) % 1200, 26, 26);
  }
  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.9));
  window.__made = { bytes: blob.size };
  return blob.size;
})()
"""

SET_FILE = """
(async (name) => {
  const input = document.querySelector('[data-replace-face-input]');
  const blob = await new Promise((res) => {
    const c = document.createElement('canvas');
    c.width = 3000; c.height = 1200;
    const g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 3000, 1200);
    grad.addColorStop(0, '#b0301a'); grad.addColorStop(0.5, '#d8c7a5'); grad.addColorStop(1, '#2a3f6b');
    g.fillStyle = grad; g.fillRect(0, 0, 3000, 1200);
    for (let i = 0; i < 240; i++) {
      g.fillStyle = i % 2 ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.30)';
      g.fillRect((i * 37) % 3000, (i * 91) % 1200, 26, 26);
    }
    c.toBlob(res, 'image/jpeg', 0.9);
  });
  const file = new File([blob], name, { type: 'image/jpeg' });
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { name, bytes: file.size, type: file.type };
})
"""

MAKE_OTHER_IMAGE = """
(async () => {
  const c = document.createElement('canvas');
  c.width = 1280; c.height = 320;   // 另一张非方形图（内容不同 ⇒ 摘要不同）
  const g = c.getContext('2d');
  g.fillStyle = '#1d7a4e'; g.fillRect(0, 0, 1280, 320);
  g.fillStyle = '#f2e9d8';
  for (let i = 0; i < 60; i++) g.fillRect(i * 21, i * 5, 18, 18);
  const blob = await new Promise((res) => c.toBlob(res, 'image/png'));
  const input = document.querySelector('[data-replace-face-input]');
  const dt = new DataTransfer();
  dt.items.add(new File([blob], 'second-face.png', { type: 'image/png' }));
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return blob.size;
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
        self.network = []

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
            if "method" in msg:
                self._event(msg)

    def _event(self, msg):
        m = msg.get("method")
        if m == "Network.requestWillBeSent":
            self.network.append(msg["params"]["request"]["url"])

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


SNAPSHOT = """
(async () => {
  const db = await import('/src/data/db.js');
  const faces = db.listFaceRows();
  const images = db.listImageRows();
  const face = faces.find((r) => r.id === '%s') || null;
  const meta = (id) => {
    const r = images.find((x) => x.id === id);
    return r ? { id: r.id, kind: r.kind, stamp_id: r.stamp_id, width: r.width, height: r.height,
                 bytes: r.bytes, mime: r.mime, color_mode: r.color_mode, sha256: r.sha256 } : null;
  };
  const keys = await db.listImageBinaryKeys();
  const sizes = {};
  for (const k of keys) {
    const out = await db.getImageBinary(String(k).replace(/^asset:/, ''));
    sizes[k] = out.ok ? out.bytesLength : ('ERR:' + out.message);
  }
  return {
    face_image_id: face ? face.face_image_id : null,
    face_row: face,
    image_count: images.length,
    image_ids: images.map((r) => r.id),
    new_meta: meta(face ? face.face_image_id : null),
    old_meta: meta('%s'),
    blob_keys: keys,
    blob_sizes: sizes
  };
})()
""" % (FACE, "img-0001f")


def main():
    out = {"chrome": ensure_chrome(), "profile": UDD, "port": PORT, "base": BASE,
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": []}

    def check(name, ok, detail):
        out["checks"].append({"name": name, "pass": bool(ok), "detail": str(detail)})

    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    tab.send("Network.enable")
    tab.goto(f"{BASE}/", wait=2.0)
    tab.js("(() => { localStorage.clear(); return 1; })()")
    tab.goto(f"{BASE}/", wait=2.2)

    # ---------------- 登录助手 ----------------
    def login(phone):
        tab.goto(f"{BASE}/login", wait=1.5)
        tab.js(
            "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('input',{bubbles:true}));};"
            f" set(document.querySelector('#login-phone'), '{phone}');"
            f" set(document.querySelector('#login-code'), '{CODE}');"
            " document.querySelector('form.login__form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));"
            " return 1; })()"
        )
        time.sleep(1.8)
        return tab.js("location.pathname")

    def logout():
        tab.js("(async () => { const a = await import('/src/services/auth.js'); a.logout(); return 1; })()")
        tab.goto(f"{BASE}/", wait=1.6)

    # ---------------- 游客（未登录）DOM 零命中 ----------------
    tab.goto(f"{BASE}/seal/{SEAL}", wait=2.0)
    out["guest"] = tab.js(
        "(() => ({ blocks: document.querySelectorAll('.face-block').length,"
        " replace: document.querySelectorAll('[data-admin-action=\"replace-face-image\"]').length,"
        " edit: document.querySelectorAll('[data-admin-action=\"edit-fixed-attributes\"]').length,"
        " text_hit: document.body.innerText.includes('重新上传印面图') }))()"
    )
    check("① 游客（未登录）DOM：印面块 3 个、替换按钮 0 个、文案零命中",
          out["guest"]["blocks"] == 3 and out["guest"]["replace"] == 0 and out["guest"]["text_hit"] is False,
          json.dumps(out["guest"], ensure_ascii=False))

    # ---------------- 管理员登录 ----------------
    out["login_admin_path"] = login(ADMIN)
    out["who_admin"] = tab.js(
        "(async () => { const s = await import('/src/data/session.js'); const u = s.currentUser();"
        " return { phone: u.phone, role: u.role }; })()"
    )
    check("① 管理员登录成功（16601061656 / role = admin）",
          out["who_admin"]["role"] == "admin", json.dumps(out["who_admin"], ensure_ascii=False))

    tab.goto(f"{BASE}/seal/{SEAL}", wait=2.2)
    out["admin_dom"] = tab.js(
        "(() => { const btns = [...document.querySelectorAll('[data-admin-action=\"replace-face-image\"]')];"
        " return { blocks: document.querySelectorAll('.face-block').length,"
        "   replace: btns.length,"
        "   face_ids: btns.map((b) => b.getAttribute('data-face-id')),"
        "   labels: btns.map((b) => b.innerText.trim()),"
        "   edit_buttons: document.querySelectorAll('[data-admin-action=\"edit-fixed-attributes\"]').length,"
        "   block_ids: [...document.querySelectorAll('.face-block__id')].map((e) => e.innerText.trim()) }; })()"
    )
    check("① 管理员 DOM：**每个印面块**各一个「重新上传印面图」按钮（3/3，与「编辑固定属性」同粒度）",
          out["admin_dom"]["blocks"] == 3 and out["admin_dom"]["replace"] == 3
          and out["admin_dom"]["replace"] == out["admin_dom"]["edit_buttons"]
          and out["admin_dom"]["face_ids"] == out["admin_dom"]["block_ids"],
          json.dumps(out["admin_dom"], ensure_ascii=False))
    check("① 按钮文案正确（「重新上传印面图」）",
          all(t == "重新上传印面图" for t in out["admin_dom"]["labels"]), json.dumps(out["admin_dom"]["labels"], ensure_ascii=False))

    # ---------------- 基线读数 ----------------
    base = tab.js(SNAPSHOT)
    out["baseline"] = base
    check("基线：印面 fc-0001-f1 当前影像编号 = img-0001f",
          base["face_image_id"] == "img-0001f", json.dumps(base["face_image_id"]))

    # ---------------- 打开弹窗 + 选图（3000 × 1200 非方形） ----------------
    tab.js(f"document.querySelector('[data-face-id=\"{FACE}\"]').click()")
    tab.js("window.__marker = 'no-reload-' + Date.now(); 1")  # 用于证明「未刷新」
    opened = tab.wait_for("!!document.querySelector('[data-admin-dialog=\"replace-face-image\"]')")
    out["dialog"] = tab.js(
        "(() => { const d = document.querySelector('[data-admin-dialog=\"replace-face-image\"]');"
        " return d ? { title: d.querySelector('h3').innerText.trim(),"
        "   lede: d.querySelector('.replace-face-box__lede').innerText.replace(/\\s+/g,' ').trim(),"
        "   has_input: !!d.querySelector('[data-replace-face-input]'),"
        "   has_submit: !!d.querySelector('[data-admin-action=\"replace-face-image-submit\"]') } : null; })()"
    )
    check("② 管理员点按钮 ⇒ 打开取景弹窗（标题含印面类别、含选图输入与确认按钮）",
          bool(opened) and out["dialog"] and out["dialog"]["has_input"] and out["dialog"]["has_submit"],
          json.dumps(out["dialog"], ensure_ascii=False))

    out["file"] = tab.js(SET_FILE + "('selftest-3000x1200.jpg')")
    time.sleep(1.2)
    out["preview"] = tab.js(
        "(() => { const d = document.querySelector('[data-admin-dialog=\"replace-face-image\"]');"
        " const s = d.querySelector('[data-replace-face-summary]');"
        " const f = d.querySelector('[data-crop-frame=\"replace-face-image\"]');"
        " const img = d.querySelector('[data-replace-face-preview=\"seal-face\"] img');"
        " return { summary: s ? s.innerText.replace(/\\s+/g,' ').trim() : null,"
        "   hint: (d.querySelector('.field__hint') || {}).innerText ? d.querySelector('.field__hint').innerText.replace(/\\s+/g,' ').trim() : null,"
        "   frame: f ? { w: f.style.width, h: f.style.height, left: f.style.left, top: f.style.top } : null,"
        "   preview_ok: !!img && img.naturalWidth > 0,"
        "   handle: !!d.querySelector('[data-crop-handle=\"replace-face-image\"]') }; })()"
    )
    check("② 选图后进入**方形取景**：预览已出图 + 取景框 + 可拖拽手柄 + 1 MB 上限提示 + 最长边读数",
          out["preview"]["preview_ok"] and out["preview"]["frame"] and out["preview"]["handle"]
          and ("1.00 MB" in (out["preview"]["hint"] or "") or "1.0 MB" in (out["preview"]["hint"] or ""))
          and "2048px" in (out["preview"]["summary"] or ""),
          json.dumps(out["preview"], ensure_ascii=False))
    check("② 非方形原图（3000 × 1200）已在预览读数中如实显示，且入库印面为正方形（1200 × 1200 · WebP）",
          "3000 × 1200" in (out["preview"]["summary"] or "")
          and "1200 × 1200" in (out["preview"]["summary"] or "")
          and "image/webp" in (out["preview"]["summary"] or ""),
          out["preview"]["summary"])

    # 取景框**真拖拽**：用 CDP Input 域派发真鼠标事件（不是合成 PointerEvent）⇒ 方框真的会动，且仍是正方形
    rect = tab.js(
        "(() => { const f = document.querySelector('[data-crop-frame=\"replace-face-image\"]');"
        " f.scrollIntoView({ block: 'center' });"
        " const r = f.getBoundingClientRect();"
        " return { x: r.x + r.width / 2, y: r.y + r.height / 2, rect: { x: r.x, y: r.y, w: r.width, h: r.height },"
        "   left: f.style.left, top: f.style.top, w: f.style.width, h: f.style.height }; })()"
    )
    out["drag_rect"] = rect
    tab.send("Input.dispatchMouseEvent", type="mousePressed", x=rect["x"], y=rect["y"], button="left", clickCount=1)
    tab.send("Input.dispatchMouseEvent", type="mouseMoved", x=rect["x"] + 30, y=rect["y"] + 6, button="left", buttons=1)
    tab.send("Input.dispatchMouseEvent", type="mouseMoved", x=rect["x"] + 42, y=rect["y"] + 10, button="left", buttons=1)
    tab.send("Input.dispatchMouseEvent", type="mouseReleased", x=rect["x"] + 42, y=rect["y"] + 10, button="left", clickCount=1)
    time.sleep(1.0)
    out["drag"] = tab.js(
        "(() => { const f = document.querySelector('[data-crop-frame=\"replace-face-image\"]');"
        " const s = document.querySelector('[data-replace-face-summary]');"
        " return { after: { left: f.style.left, top: f.style.top, w: f.style.width, h: f.style.height },"
        "   summary: s ? s.innerText.replace(/\\s+/g,' ').trim() : null }; })()"
    )
    out["drag"]["before"] = rect
    check("② 取景框可**真拖拽**（CDP 真鼠标事件）：拖动后位置变化、宽高仍相等（正方形），导出读数仍为方形 WebP",
          out["drag"]["after"]["left"] != rect["left"] and out["drag"]["after"]["w"] == out["drag"]["after"]["h"]
          and "1200 × 1200" in (out["drag"]["summary"] or "") and "image/webp" in (out["drag"]["summary"] or ""),
          json.dumps(out["drag"], ensure_ascii=False))

    # ---------------- 提交替换 ----------------
    tab.js("document.querySelector('[data-admin-action=\"replace-face-image-submit\"]').click()")
    fb = tab.wait_for(
        "(() => { const n = document.querySelector('[data-admin-feedback=\"replace-face-image\"]');"
        " return n && n.innerText.trim() ? n.innerText.trim() : null; })()", timeout=15)
    out["feedback_1"] = fb
    after1 = tab.js(SNAPSHOT)
    out["after_replace_1"] = after1
    check("② 提交后有可读反馈（含「影像编号 旧 → 新」）",
          bool(fb) and "影像编号 img-0001f →" in fb, fb)
    check("② 印面 face_image_id 已改指向新影像",
          after1["face_image_id"] not in (None, "img-0001f") and after1["face_image_id"] == (after1["new_meta"] or {}).get("id"),
          json.dumps({k: after1[k] for k in ("face_image_id", "new_meta")}, ensure_ascii=False))
    check("② 新影像：**方形**（width == height）、mime = image/webp、体量如实 > 0",
          after1["new_meta"] and after1["new_meta"]["width"] == after1["new_meta"]["height"]
          and after1["new_meta"]["mime"] == "image/webp" and after1["new_meta"]["bytes"] > 0,
          json.dumps(after1["new_meta"], ensure_ascii=False))
    check("② 新影像 kind = FACE 且与印面同一印章（XAI-0001）",
          after1["new_meta"] and after1["new_meta"]["kind"] == "FACE" and after1["new_meta"]["stamp_id"] == "XAI-0001",
          json.dumps({k: after1["new_meta"][k] for k in ("kind", "stamp_id")}, ensure_ascii=False))
    check("② 影像行数 = 前 + 1（旧行不删）",
          after1["image_count"] == base["image_count"] + 1,
          f"{base['image_count']} → {after1['image_count']}")
    check("② 旧影像行逐字未改（img-0001f 元数据与基线一致）",
          json.dumps(after1["old_meta"], sort_keys=True) == json.dumps(base["old_meta"], sort_keys=True),
          json.dumps({"before": base["old_meta"], "after": after1["old_meta"]}, ensure_ascii=False))
    check("② 二进制已落影像库（键 asset:新影像编号，字节数 = 行内 bytes）",
          f"asset:{after1['face_image_id']}" in after1["blob_keys"]
          and after1["blob_sizes"].get(f"asset:{after1['face_image_id']}") == after1["new_meta"]["bytes"],
          json.dumps(after1["blob_sizes"], ensure_ascii=False))

    # ---------------- 「不刷新即显示新图」 ----------------
    dom_now = tab.js(
        "(() => { const fig = document.querySelector('.face-block__figure');"
        " const img = document.querySelector('img[data-face-image]');"
        " return { same_page: window.__marker || null,"
        "   figcaption: fig ? fig.querySelector('figcaption').innerText.trim() : null,"
        "   img_ok: !!img && img.naturalWidth > 0,"
        "   first_dd: (document.querySelector('.detail__fixed dd') || {}).innerText || null,"
        "   summary: (document.querySelector('.face-block__figure p:not(.detail__sha)') || {}).innerText || null }; })()"
    )
    out["dom_after_replace"] = dom_now
    check("② **无需刷新**即显示新图（页内标记未丢 ⇒ 未发生导航/刷新；图已加载；图注＝新影像编号）",
          dom_now and dom_now["same_page"] and dom_now["img_ok"]
          and dom_now["figcaption"] == f"印面影像 {after1['face_image_id']}"
          and dom_now["first_dd"] == f"影像编号 {after1['face_image_id']}",
          json.dumps(dom_now, ensure_ascii=False))

    # ---------------- ②′ 第二次替换：第一次的二进制必须仍在 ----------------
    first_id = after1["face_image_id"]
    first_bytes = after1["new_meta"]["bytes"]
    tab.js(f"document.querySelector('[data-face-id=\"{FACE}\"]').click()")
    tab.wait_for("!!document.querySelector('[data-admin-dialog=\"replace-face-image\"]')")
    out["second_file_bytes"] = tab.js(MAKE_OTHER_IMAGE)
    time.sleep(1.2)
    tab.js("document.querySelector('[data-admin-action=\"replace-face-image-submit\"]').click()")
    fb2 = tab.wait_for(
        "(() => { const n = document.querySelector('[data-admin-feedback=\"replace-face-image\"]');"
        " return n && n.innerText.includes('影像编号') ? n.innerText.trim() : null; })()", timeout=15)
    out["feedback_2"] = fb2
    after2 = tab.js(SNAPSHOT)
    out["after_replace_2"] = after2
    check("②′ 第二次替换成功且反馈含「旧 → 新」（旧＝第一次的新编号）",
          bool(fb2) and f"影像编号 {first_id} →" in fb2, fb2)
    check("②′ 第一次的影像**行**仍在库且逐字未改",
          after2["old_meta"] is not None
          and json.dumps(after2["old_meta"], sort_keys=True) == json.dumps(base["old_meta"], sort_keys=True)
          and first_id in after2["image_ids"],
          json.dumps({"image_ids": after2["image_ids"], "first": first_id}, ensure_ascii=False))
    check("②′ 第一次的影像**二进制**仍在且字节一致（替换不删旧图）",
          after2["blob_sizes"].get(f"asset:{first_id}") == first_bytes,
          json.dumps({"expect": first_bytes, "got": after2["blob_sizes"].get(f"asset:{first_id}"), "keys": after2["blob_keys"]}, ensure_ascii=False))
    check("②′ 影像行数 = 前 + 1（只增不删）",
          after2["image_count"] == after1["image_count"] + 1,
          f"{after1['image_count']} → {after2['image_count']}")

    # ---------------- ④ 持久化：关标签重开（全新加载）后新图仍在 ----------------
    tab.goto(f"{BASE}/seal/{SEAL}", wait=2.5)
    persisted = tab.js(SNAPSHOT)
    dom_reload = tab.js(
        "(() => { const img = document.querySelector('img[data-face-image]');"
        " return { marker_gone: typeof window.__marker === 'undefined',"
        "   figcaption: (document.querySelector('.face-block__figure figcaption') || {}).innerText || null,"
        "   img_ok: !!img && img.naturalWidth > 0,"
        "   img_is_data_url: !!img && String(img.getAttribute('src')).startsWith('data:image/') }; })()"
    )
    out["persist"] = {"db": persisted, "dom": dom_reload}
    check("④ 持久化：全新加载后印面指向 / 影像行 / 二进制三者一致",
          persisted["face_image_id"] == after2["face_image_id"]
          and persisted["new_meta"] == after2["new_meta"]
          and persisted["blob_sizes"] == after2["blob_sizes"],
          json.dumps({"face_image_id": persisted["face_image_id"], "meta": persisted["new_meta"]}, ensure_ascii=False))
    check("④ 持久化：新图在**重新打开**的页面里仍显示（页内标记已丢 ⇒ 确为全新加载）",
          dom_reload["marker_gone"] and dom_reload["img_ok"] and dom_reload["img_is_data_url"]
          and dom_reload["figcaption"] == f"印面影像 {after2['face_image_id']}",
          json.dumps(dom_reload, ensure_ascii=False))

    # ---------------- ③ 回滚 / 原子（浏览器内注入 IDB 写失败） ----------------
    rollback = tab.js("""
    (async () => {
      const db = await import('/src/data/db.js');
      const seals = await import('/src/services/seals.js');
      const FACE = 'fc-0001-f1';
      const before = {
        face_image_id: (db.listFaceRows().find((r) => r.id === FACE) || {}).face_image_id,
        image_count: db.listImageRows().length,
        blob_keys: (await db.listImageBinaryKeys()).slice()
      };
      const c = document.createElement('canvas');
      c.width = 900; c.height = 300;
      const g = c.getContext('2d');
      g.fillStyle = '#7a5cff'; g.fillRect(0, 0, 900, 300);
      const blob = await new Promise((res) => c.toBlob(res, 'image/png'));
      const bytes = new Uint8Array(await blob.arrayBuffer());

      const origPut = IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put = function () { throw new Error('注入故障：影像库写入失败'); };
      let result;
      try {
        result = await seals.replaceFaceImage(FACE, { bytes, mime: 'image/png', width: 900, height: 300 });
      } finally {
        IDBObjectStore.prototype.put = origPut;
      }
      await new Promise((r) => setTimeout(r, 300));
      const after = {
        face_image_id: (db.listFaceRows().find((r) => r.id === FACE) || {}).face_image_id,
        image_count: db.listImageRows().length,
        blob_keys: (await db.listImageBinaryKeys()).slice()
      };
      return { before, injected: 'IDBObjectStore.prototype.put 抛错', result: { ok: result.ok, reason: result.reason, message: result.message }, after };
    })()
    """)
    out["rollback"] = rollback
    check("③ 注入影像库写失败 ⇒ 结构化失败（reason = STORAGE_UNAVAILABLE，未抛异常）",
          rollback and rollback["result"]["ok"] is False and rollback["result"]["reason"] == "STORAGE_UNAVAILABLE",
          json.dumps(rollback and rollback["result"], ensure_ascii=False))
    check("③ 回滚：影像行数不变 + 印面指向不变 + 影像库键集合不变（无半成品行 / 无孤儿二进制）",
          rollback and rollback["after"]["image_count"] == rollback["before"]["image_count"]
          and rollback["after"]["face_image_id"] == rollback["before"]["face_image_id"]
          and rollback["after"]["blob_keys"] == rollback["before"]["blob_keys"],
          json.dumps(rollback and {"before": rollback["before"], "after": rollback["after"]}, ensure_ascii=False))

    # ---------------- ①′ 普通用户：DOM 零命中 + 数据层拒绝 ----------------
    logout()
    out["normal_login_path"] = login(NORMAL)
    out["who_normal"] = tab.js(
        "(async () => { const s = await import('/src/data/session.js'); const u = s.currentUser();"
        " return { phone: u.phone, role: u.role }; })()"
    )
    check("① 普通用户登录（13800000001 / role = user）", out["who_normal"]["role"] == "user",
          json.dumps(out["who_normal"], ensure_ascii=False))

    tab.goto(f"{BASE}/seal/{SEAL}", wait=2.2)
    out["normal_dom"] = tab.js(
        "(() => ({ blocks: document.querySelectorAll('.face-block').length,"
        " replace: document.querySelectorAll('[data-admin-action=\"replace-face-image\"]').length,"
        " any_admin_action: document.querySelectorAll('[data-admin-action]').length,"
        " dialog: document.querySelectorAll('[data-admin-dialog=\"replace-face-image\"]').length,"
        " text_hit: document.body.innerText.includes('重新上传印面图'),"
        " html_hit: document.body.innerHTML.includes('replace-face-image') }))()"
    )
    check("① 普通用户 DOM：替换按钮命中数 = 0 且文案 / 属性零命中",
          out["normal_dom"]["replace"] == 0 and out["normal_dom"]["text_hit"] is False
          and out["normal_dom"]["html_hit"] is False and out["normal_dom"]["blocks"] == 3,
          json.dumps(out["normal_dom"], ensure_ascii=False))

    bypass = tab.js("""
    (async () => {
      const db = await import('/src/data/db.js');
      const seals = await import('/src/services/seals.js');
      const FACE = 'fc-0001-f1';
      const count = async () => ({
        face_image_id: (db.listFaceRows().find((r) => r.id === FACE) || {}).face_image_id,
        image_count: db.listImageRows().length,
        blob_keys: (await db.listImageBinaryKeys()).slice()
      });
      const before = await count();
      const c = document.createElement('canvas');
      c.width = 640; c.height = 200;
      const g = c.getContext('2d'); g.fillStyle = '#ff9f1c'; g.fillRect(0, 0, 640, 200);
      const blob = await new Promise((res) => c.toBlob(res, 'image/png'));
      const bytes = new Uint8Array(await blob.arrayBuffer());
      const service = await seals.replaceFaceImage(FACE, { bytes, mime: 'image/png', width: 640, height: 200 });
      const dataLayer = await db.replaceFaceImage({ id: 'u-13800000001', phone: '13800000001', role: 'user' }, FACE, bytes);
      return { before, service: { ok: service.ok, reason: service.reason, message: service.message },
               dataLayer: { ok: dataLayer.ok, reason: dataLayer.reason, message: dataLayer.message },
               after: await count() };
    })()
    """)
    out["normal_bypass"] = bypass
    check("①′ 普通用户**绕过 UI** 直调服务层 ⇒ FORBIDDEN",
          bypass and bypass["service"]["ok"] is False and bypass["service"]["reason"] == "FORBIDDEN",
          json.dumps(bypass and bypass["service"], ensure_ascii=False))
    check("①′ 普通用户**绕过服务层**直调数据层 ⇒ FORBIDDEN（数据层独立拒绝）",
          bypass and bypass["dataLayer"]["ok"] is False and bypass["dataLayer"]["reason"] == "FORBIDDEN",
          json.dumps(bypass and bypass["dataLayer"], ensure_ascii=False))
    check("①′ 越权调用后库零变化（印面指向 / 影像行数 / 二进制键集合）",
          bypass and bypass["before"] == bypass["after"],
          json.dumps(bypass and {"before": bypass["before"], "after": bypass["after"]}, ensure_ascii=False))

    # ---------------- ⑤ 网络捕获 ----------------
    urls = list(dict.fromkeys(tab.network))
    bad = [u for u in urls if "5196" in u or "square-crop" in u]
    external = [u for u in urls if not (u.startswith(BASE) or u.startswith("data:") or u.startswith("blob:") or u.startswith("about:"))]
    out["network"] = {"total": len(urls), "bad": bad, "external": external, "sample": urls[:12]}
    check("⑤ 网络捕获中不得出现 5196 / square-crop", not bad, json.dumps(bad, ensure_ascii=False))
    check("⑤ 网络捕获中不得出现任何外部 URL（全部为 127.0.0.1:5163 / data: / blob:）",
          not external, json.dumps(external, ensure_ascii=False))
    out["network_all"] = urls

    out["passed"] = sum(1 for c in out["checks"] if c["pass"])
    out["failed"] = sum(1 for c in out["checks"] if not c["pass"])
    out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    with open(OUT_TXT, "w") as fh:
        fh.write(f"# 玺爱 · 「重新上传印面图」端到端取证（真浏览器）{out['started_at']} → {out['finished_at']}\n")
        fh.write(f"# profile={UDD} port={PORT} base={BASE}\n")
        for c in out["checks"]:
            fh.write(f"{'PASS' if c['pass'] else 'FAIL'} | {c['name']} | {c['detail']}\n")
        fh.write(f"\n# 网络请求共 {len(urls)} 条；bad={bad} external={external}\n")
    print(json.dumps({"passed": out["passed"], "failed": out["failed"],
                      "failed_checks": [c for c in out["checks"] if not c["pass"]]}, ensure_ascii=False, indent=2))
    sys.exit(0 if out["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
