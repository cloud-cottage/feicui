#!/usr/bin/env python3
"""玺爱（xiai）·「上传印章」印面图浏览器端处理管线 —— 自测留证（Kong）

自建 headless Chrome（独立 profile /tmp/xiai-kong4-prof-<ts>、
--remote-allow-origins=*，**不动用户自己的 Chrome**、**不停 5163**、**不占 5173/5174**）。
全部断言走真实 DOM / 真实存储读数，四条：
  ① 选 1.2 MB 图 ⇒ 拒 + 可读提示（含真实上限与所选体量）
  ② 选 3000×1200 非方形图 ⇒ 预览 + 可拖拽/缩放的方形框可见；
     拖框移动 + 拖手柄缩小 ⇒ 提交成功 ⇒ **IndexedDB/localStorage 读回 width == height 且 mime == image/webp**
  ③ 只填朝代/分类、印文留空 ⇒ 提交成功且编号形如 XA\\d{9}
  ④ 全程记录网络请求：**零 5196 / 零 square-crop / 零外链**（全部请求仅 127.0.0.1:5163）
输出 JSON 落盘 feicui/ops/kong_xiai_k4_image_pipeline_raw.json。
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UDD = f"/tmp/xiai-kong4-prof-{int(time.time())}"
PORT = 9444
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
        self.ws = websocket.create_connection(ws_url, timeout=60,
                                              suppress_origin=True, enable_multithread=True)
        self.n = 0
        self.events = []

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
                self.events.append(msg)

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

    # ---- 真实鼠标（→ Blink 会合成 pointer 事件，能真正驱动 pointerdown/move/up） ----
    def mouse(self, kind, x, y, buttons=1):
        self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left",
                  buttons=buttons, clickCount=1)

    def drag(self, x0, y0, x1, y1, steps=6):
        self.mouse("mousePressed", x0, y0, buttons=1)
        for i in range(1, steps + 1):
            self.mouse("mouseMoved", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, buttons=1)
            time.sleep(0.03)
        self.mouse("mouseReleased", x1, y1, buttons=0)
        time.sleep(0.4)

    def requests(self):
        urls = []
        for ev in self.events:
            if ev.get("method") == "Network.requestWillBeSent":
                urls.append(ev["params"]["request"]["url"])
        return urls


# ---------------------------------------------------------------- 页面内造图（真实 PNG）
MAKE_FILES = r"""
window.__mk = async function (kind) {
  const toFile = (canvas, name) => new Promise((res) =>
    canvas.toBlob((b) => res(new File([b], name, { type: 'image/png' })), 'image/png'));
  const noiseSized = async (lo, hi, dims) => {
    for (let i = 0; i < dims.length; i += 1) {
      const w = dims[i][0];
      const h = dims[i][1];
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      const ctx = c.getContext('2d');
      const img = ctx.createImageData(w, h);
      for (let k = 0; k < img.data.length; k += 4) {
        img.data[k] = Math.floor(Math.random() * 256);
        img.data[k + 1] = Math.floor(Math.random() * 256);
        img.data[k + 2] = Math.floor(Math.random() * 256);
        img.data[k + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      const f = await toFile(c, 'noise-' + w + 'x' + h + '.png');
      if (f.size >= lo && f.size <= hi) return f;
    }
    return null;
  };
  /* 超限探针：目标 ~1.05–1.30 MB（约 1.2 MB） */
  if (kind === 'over') return noiseSized(1050000, 1310720, [[700, 520], [680, 520], [720, 520], [660, 520]]);
  /* 边界内探针：目标 0.90–1.00 MB（刚好不超 1 MB 上限，应被接受）。
     实测标定（本机 headless Chrome）：canvas 噪声图 PNG 字节 ≈ 宽×高×4×0.86，
     故像素数取 ~282k ⇒ 文件 ~0.97 MB。 */
  if (kind === 'near') return noiseSized(900000, 1048576, [[640, 440], [650, 440], [630, 440], [660, 430], [620, 430]]);
  if (kind === 'wide') {
    const c = document.createElement('canvas');
    c.width = 3000; c.height = 1200;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#eee6d8'; ctx.fillRect(0, 0, 3000, 1200);
    const g = ctx.createLinearGradient(0, 0, 3000, 1200);
    g.addColorStop(0, '#c9b28a'); g.addColorStop(1, '#6d4b2e');
    ctx.fillStyle = g; ctx.fillRect(1380, 260, 860, 860);
    for (let i = 0; i < 8; i += 1) {
      ctx.fillStyle = ['#8b2f22', '#1f2f4a', '#3d6b4f'][i % 3];
      ctx.fillRect(80 + i * 90, 40, 40, 1120);
    }
    ctx.fillStyle = '#22201c'; ctx.fillRect(1200, 100, 40, 1000);
    return toFile(c, 'wide-3000x1200.png');
  }
  const c = document.createElement('canvas');
  c.width = 500; c.height = 900;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#f2ecdd'; ctx.fillRect(0, 0, 500, 900);
  ctx.fillStyle = '#8b2f22'; ctx.fillRect(90, 160, 320, 320);
  ctx.fillStyle = '#1f2f4a'; ctx.fillRect(140, 620, 220, 220);
  return toFile(c, 'portrait-500x900.png');
};
window.__pick = async function (kind) {
  const file = await window.__mk(kind);
  if (!file) return { ok: false, message: '造图失败' };
  const input = document.querySelector('#upload-seal-face');
  if (!input) return { ok: false, message: '找不到文件输入框' };
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, name: file.name, size: file.size, type: file.type };
};
window.__frame = function () {
  const f = document.querySelector('[data-crop-frame="seal-face"]');
  if (!f) return null;
  const r = f.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height, left: f.style.left, top: f.style.top,
           width: f.style.width, height: f.style.height };
};
window.__focusFrame = function () {
  const f = document.querySelector('[data-crop-frame="seal-face"]');
  if (!f) return null;
  f.scrollIntoView({ block: 'center', inline: 'center' });
  const r = f.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height, left: f.style.left, top: f.style.top,
           width: f.style.width, height: f.style.height,
           fullyInViewport: r.y >= 0 && r.bottom <= window.innerHeight
                             && r.x >= 0 && r.right <= window.innerWidth };
};
window.__handle = function () {
  const h = document.querySelector('[data-crop-handle="seal-face"]');
  if (!h) return null;
  const r = h.getBoundingClientRect();
  const view = h.closest('.cropper__view').getBoundingClientRect();
  const cx = r.x + r.width / 2;
  const cy = Math.min(Math.max(r.y + r.height / 2, r.y + 2), Math.min(r.y + r.height - 2, view.bottom - 3));
  return { x: cx, y: cy, viewBottom: view.bottom, handleTop: r.y, handleBottom: r.y + r.height };
};
window.__summary = function () {
  const el = document.querySelector('[data-upload-summary="seal-face"]');
  return el ? el.innerText.replace(/\s+/g, ' ').trim() : '';
};
window.__feedback = function () {
  const el = document.querySelector('[data-admin-feedback="upload-seal"]');
  return el ? el.innerText.trim() : '';
};
window.__db = function (stampId) {
  const rows = JSON.parse(localStorage.getItem('xiai:v1:images') || '[]');
  const row = stampId
    ? rows.filter((r) => r.stamp_id === stampId && r.kind === 'FACE').slice(-1)[0]
    : rows.slice(-1)[0];
  return row || null;
};
window.__seals = function () {
  return JSON.parse(localStorage.getItem('xiai:v1:seals') || '[]');
};
window.__blob = function (key) {
  return new Promise((resolve) => {
    const req = indexedDB.open('xiai:v1:assetblobs', 1);
    req.onerror = () => resolve({ ok: false, message: '打不开影像库' });
    req.onsuccess = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('assets')) { resolve({ ok: false, message: '无 assets 库' }); return; }
      const get = db.transaction('assets', 'readonly').objectStore('assets').get(key);
      get.onerror = () => resolve({ ok: false, message: '读失败' });
      get.onsuccess = async () => {
        const val = get.result;
        let bytes = null;
        if (val instanceof Blob) bytes = new Uint8Array(await val.arrayBuffer());
        else if (val instanceof ArrayBuffer) bytes = new Uint8Array(val);
        else if (val && val.buffer) bytes = new Uint8Array(val.buffer);
        if (!bytes) { resolve({ ok: false, message: '值不是二进制：' + Object.prototype.toString.call(val) }); return; }
        const head = Array.from(bytes.slice(0, 12));
        const riff = head[0] === 0x52 && head[1] === 0x49 && head[2] === 0x46 && head[3] === 0x46;
        const webp = head[8] === 0x57 && head[9] === 0x45 && head[10] === 0x42 && head[11] === 0x50;
        resolve({ ok: true, length: bytes.length, head: head, riff: riff, webp: webp,
                  valueType: Object.prototype.toString.call(val) });
      };
    };
  });
};
window.__setForm = function (dynasty, sealType, name) {
  const set = (sel, v) => {
    const el = document.querySelector(sel);
    el.value = v;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };
  set('#upload-seal-dynasty', dynasty);
  set('#upload-seal-type', sealType);
  set('#upload-seal-name', name);
  return { dynasty: document.querySelector('#upload-seal-dynasty').value,
           type: document.querySelector('#upload-seal-type').value,
           name: document.querySelector('#upload-seal-name').value };
};
1
"""


def main():
    out = {"chrome": ensure_chrome(), "profile": UDD, "debug_port": PORT, "base": BASE,
           "checks": [], "readings": {}}

    def check(name, ok, detail):
        out["checks"].append({"id": name, "pass": bool(ok), "detail": str(detail)})
        print(("PASS  " if ok else "FAIL  ") + name + " :: " + str(detail)[:300], flush=True)

    hydrations = {"count": 0}

    def prep(want_dialog):
        """每个用例块开工前把页面拉回已知态。

        Vite dev 的 HMR 整页刷新会清掉 window 上注入的取证脚本（并行单正在改
        `utils/image.js` ⇒ 会真的触发），故每块都重新核对并重注，**不靠上一块的状态**。
        登录态 / 已落库数据在 localStorage，刷新不受影响。
        """
        if tab.js("location.pathname") != "/":
            tab.goto(f"{BASE}/", wait=2.2)
        helpers = tab.js("typeof window.__pick === 'function'")
        if helpers is not True:
            hydrations["count"] += 1
            tab.js(MAKE_FILES)
            helpers = tab.js("typeof window.__pick === 'function'")
        open_now = tab.js("!!document.querySelector('[data-admin-dialog=\"upload-seal\"]')")
        if want_dialog and not open_now:
            tab.js("document.querySelector('button[data-admin-action=\"upload-seal\"]').click()")
            time.sleep(0.9)
        if not want_dialog and open_now:
            tab.js("(() => { const b=[...document.querySelectorAll('.upload-box__foot button')][0]; if(b) b.click(); return 1; })()")
            time.sleep(0.5)
        return {
            "path": tab.js("location.pathname"),
            "helpers_armed": tab.js("typeof window.__pick === 'function'"),
            "dialog_open": tab.js("!!document.querySelector('[data-admin-dialog=\"upload-seal\"]')")
        }

    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    tab.send("Network.enable")
    tab.goto(f"{BASE}/", wait=2.2)
    tab.js("(() => { localStorage.clear(); return 1; })()")
    tab.send("Network.enable")
    tab.goto(f"{BASE}/", wait=2.2)
    out["image_js_present"] = tab.js(
        "fetch('/src/utils/image.js', { cache: 'no-store' })"
        ".then(r => r.text()).then(t => t.includes('loadImageFile') && t.includes('exportSquareImage'))"
    )

    # ---------------- 登录（管理员 16601061656 + 1234） ----------------
    tab.goto(f"{BASE}/login", wait=1.5)
    tab.js(
        "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('input',{bubbles:true}));};"
        f" set(document.querySelector('#login-phone'), '{PHONE}');"
        f" set(document.querySelector('#login-code'), '{CODE}');"
        " document.querySelector('form.login__form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));"
        " return 1; })()"
    )
    time.sleep(1.8)
    out["readings"]["after_login_path"] = tab.js("location.pathname")
    out["readings"]["upload_button_visible"] = tab.js(
        "!!document.querySelector('button[data-admin-action=\"upload-seal\"]')")
    check("登录后（管理员）广场「上传印章」按钮可见", out["readings"]["upload_button_visible"] is True,
          out["readings"]["upload_button_visible"])

    # 登录完成、已在本站同源页面 ⇒ 现在注入取证用页面脚本（导航会清掉，故每次导航后重注）
    tab.js(MAKE_FILES)
    helpers_ok = tab.js(
        "['__mk','__pick','__frame','__focusFrame','__handle','__summary','__feedback','__db','__seals','__blob','__setForm']"
        ".every((k) => typeof window[k] === 'function')")
    check("取证脚本已注入（页面内造图 / 取景框读数 / 存储读数齐备）", helpers_ok is True, helpers_ok)

    out["readings"]["prep_1"] = prep(True)
    out["readings"]["dialog_open"] = tab.js("!!document.querySelector('[data-admin-dialog=\"upload-seal\"]')")
    out["readings"]["input_hint"] = tab.js(
        "(document.querySelector('label[for=\"upload-seal-face\"]').parentElement.querySelector('.field__hint')||{}).innerText || ''")
    check("① 选图入口就位（弹窗打开 + 印面图输入框存在）",
          out["readings"]["dialog_open"] is True and tab.js("!!document.querySelector('#upload-seal-face')") is True,
          out["readings"]["dialog_open"])
    check("① 入口文案写明了真实上限（1.00 MB / 1048576 字节）",
          "1.00 MB" in (out["readings"]["input_hint"] or "") and "1048576" in (out["readings"]["input_hint"] or ""),
          out["readings"]["input_hint"])

    # ---------------- ① 1.2 MB 图 ⇒ 拒 ----------------
    picked = tab.js("window.__pick('over')")
    time.sleep(1.0)
    out["readings"]["pick_over"] = picked
    out["readings"]["over_feedback"] = tab.js("window.__feedback()")
    out["readings"]["over_preview_exists"] = tab.js("!!document.querySelector('[data-upload-preview=\"seal-face\"]')")
    fb = out["readings"]["over_feedback"] or ""
    check("① 选 1.2 MB 图被拒（未生成预览 / 未进入取景）",
          bool(picked) and (picked.get("size") or 0) > 1048576 and out["readings"]["over_preview_exists"] is False,
          f"size={picked.get('size')} preview={out['readings']['over_preview_exists']}")
    check("① 拒绝提示可读（含真实上限 1.00 MB 与所选体量）",
          "1.00 MB" in fb and "照片过大" in fb and "1." in fb and "MB" in fb, fb)

    # ---------------- ② 3000×1200 非方形 ⇒ 预览 + 可拖拽/缩放的方形框 ⇒ 提交 ----------------
    out["readings"]["prep_2"] = prep(True)
    picked2 = tab.js("window.__pick('wide')")
    time.sleep(1.6)
    out["readings"]["pick_wide"] = picked2
    f0 = tab.js("window.__frame()")
    out["readings"]["frame_initial"] = f0
    out["readings"]["summary_initial"] = tab.js("window.__summary()")
    check("② 非方形原图选出后出现预览 + 方形取景框（框可见且为正方形）",
          bool(f0) and f0["w"] > 8 and abs(f0["w"] - f0["h"]) <= 1.5,
          json.dumps(f0, ensure_ascii=False))
    check("② 预览读数含原图尺寸 3000 × 1200 与入库 WebP 体量",
          "3000 × 1200" in (out["readings"]["summary_initial"] or "")
          and "image/webp" in (out["readings"]["summary_initial"] or ""),
          out["readings"]["summary_initial"])
    prev_img = tab.js(
        "(() => { const im = document.querySelector('.cropper__img');"
        " if (!im) return null;"
        " const r = im.getBoundingClientRect();"
        " return { complete: im.complete, naturalWidth: im.naturalWidth, naturalHeight: im.naturalHeight,"
        "          w: Math.round(r.width), h: Math.round(r.height), src: String(im.src).slice(0, 12) }; })()")
    out["readings"]["preview_img"] = prev_img
    check("② 预览图**真的解码可见**（<img> 已加载、非 0 尺寸、非破图）",
          bool(prev_img) and prev_img.get("complete") is True and (prev_img.get("naturalWidth") or 0) > 0
          and prev_img.get("w", 0) > 0 and prev_img.get("h", 0) > 0,
          json.dumps(prev_img, ensure_ascii=False))

    # 拖框移动：向右 +60px（真实鼠标事件；先把取景框滚进视口再按下）
    fv = tab.js("window.__focusFrame()")
    out["readings"]["frame_before_move_drag"] = fv
    check("② 拖动前取景框完整落在视口内（保证真实鼠标按到的是方框本身）",
          bool(fv) and fv.get("fullyInViewport") is True, json.dumps(fv, ensure_ascii=False))
    cx0 = fv["x"] + fv["w"] / 2
    cy0 = fv["y"] + fv["h"] / 2
    tab.drag(cx0, cy0, cx0 + 60, cy0)
    time.sleep(0.9)
    f1 = tab.js("window.__frame()")
    out["readings"]["frame_after_move"] = f1
    check("② 方形框可用拖动**移动**（left 真实变化）",
          bool(f1) and float(str(f1["left"]).replace("px", "")) > float(str(f0["left"]).replace("px", "")),
          f"left {f0['left']} -> {f1['left']}")

    # 拖手柄缩小：向上左 -45px（先滚进视口再取手柄实时坐标）
    fv1 = tab.js("window.__focusFrame()")
    h0 = tab.js("window.__handle()")
    out["readings"]["frame_before_resize_drag"] = fv1
    out["readings"]["handle_rect"] = h0
    tab.drag(h0["x"], h0["y"], h0["x"] - 45, h0["y"] - 45)
    time.sleep(1.0)
    f2 = tab.js("window.__frame()")
    out["readings"]["frame_after_resize"] = f2
    out["readings"]["summary_after_resize"] = tab.js("window.__summary()")
    check("② 方形框可用手柄**缩放**（宽高真实变小 ⇒ 用户取景真的进了导出）",
          bool(f2) and f2["w"] < f1["w"] - 1 and abs(f2["w"] - f2["h"]) <= 1.5,
          f"w {f1['w']} -> {f2['w']} / h {f2['h']} -> {f2['h']}")

    form2 = tab.js("window.__setForm('清', '私印', '')")
    out["readings"]["form2"] = form2
    seals_before = tab.js("window.__seals().length")
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(3.0)
    out["readings"]["feedback2"] = tab.js("window.__feedback()")
    out["readings"]["notice2"] = tab.js(
        "((document.querySelector('[data-admin-feedback=\"square-upload\"]')||{}).innerText||'').trim()")
    out["readings"]["dialog_still_open_2"] = tab.js("!!document.querySelector('[data-admin-dialog=\"upload-seal\"]')")
    out["readings"]["seals_after_2"] = tab.js("window.__seals().length")
    tab.js("(() => { const b=[...document.querySelectorAll('.upload-box__foot button')][0]; if(b) b.click(); return 1; })()")
    time.sleep(0.6)

    # 找最新一枚手工新建的印章（XA + 9 位）
    new_seal = tab.js(
        "(() => { const rows = window.__seals().filter(r => r.source === 'manual' && /^XA\\d{9}$/.test(r.stamp_id));"
        " rows.sort((a,b) => String(a.created_at).localeCompare(String(b.created_at)));"
        " return rows.length ? rows[rows.length-1] : null; })()")
    out["readings"]["new_seal"] = new_seal
    stamp_id = (new_seal or {}).get("stamp_id")
    img = tab.js(f"window.__db({json.dumps(stamp_id)})")
    out["readings"]["image_row"] = img
    check("② 提交成功（服务层 message 原文可读：已新增印章 + 编号 + 印面数）",
          "已新增印章" in (out["readings"]["notice2"] or "")
          and out["readings"]["seals_after_2"] == seals_before + 1
          and out["readings"]["dialog_still_open_2"] is False,
          f"{out['readings']['notice2']} | seals {seals_before} -> {out['readings']['seals_after_2']}")
    check("② 入库影像元数据 width == height", bool(img) and img.get("width") == img.get("height"),
          f"width={img.get('width')} height={img.get('height')} mime={img.get('mime')} bytes={img.get('bytes')}")
    check("② 入库影像元数据 mime === 'image/webp'", bool(img) and img.get("mime") == "image/webp",
          f"mime={img.get('mime')}")
    check("② 导出尺寸＝用户取景框边长（非默认中心方形 1200，证明取景真的进了导出）",
          bool(img) and isinstance(img.get("width"), int) and 16 <= img["width"] < 1200,
          f"width={img.get('width')}")

    blob = tab.js(f"window.__blob({json.dumps((img or {}).get('storage_key'))})") if img else None
    out["readings"]["blob_readback"] = blob
    check("② IndexedDB 读回二进制：真实 WebP（RIFF/WEBP 魔数）且字节数与元数据一致",
          bool(blob) and blob.get("ok") and blob.get("riff") and blob.get("webp")
          and blob.get("length") == (img or {}).get("bytes"),
          json.dumps(blob, ensure_ascii=False) if blob else "no row")

    # ---------------- ③ 英文字段只填朝代/分类、印文留空 ----------------
    out["readings"]["prep_3"] = prep(True)
    picked3 = tab.js("window.__pick('portrait')")
    time.sleep(1.6)
    f3 = tab.js("window.__frame()")
    out["readings"]["pick_portrait"] = picked3
    out["readings"]["frame3"] = f3
    check("③ 竖版原图（500×900）也出方形取景框（短边 500 为默认边长）",
          bool(f3) and f3["w"] > 8 and abs(f3["w"] - f3["h"]) <= 1.5,
          json.dumps(f3, ensure_ascii=False))
    form3 = tab.js("window.__setForm('漢', '官印', '')")
    out["readings"]["form3"] = form3
    seals_before3 = tab.js("window.__seals().length")
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(3.0)
    out["readings"]["feedback3"] = tab.js("window.__feedback()")
    out["readings"]["seals_after_3"] = tab.js("window.__seals().length")
    new_seal3 = tab.js(
        "(() => { const rows = window.__seals().filter(r => r.source === 'manual' && /^XA\\d{9}$/.test(r.stamp_id));"
        " rows.sort((a,b) => String(a.created_at).localeCompare(String(b.created_at)));"
        " return rows.length ? rows[rows.length-1] : null; })()")
    out["readings"]["new_seal3"] = new_seal3
    img3 = tab.js(f"window.__db({json.dumps((new_seal3 or {}).get('stamp_id'))})")
    out["readings"]["image_row3"] = img3
    import re as _re
    sid3 = (new_seal3 or {}).get("stamp_id") or ""
    check("③ 只填朝代/分类、印文留空 ⇒ 提交成功且编号形如 XA\\d{9}",
          bool(new_seal3) and bool(_re.fullmatch(r"XA\d{9}", sid3))
          and out["readings"]["seals_after_3"] == seals_before3 + 1,
          f"stamp_id={sid3} feedback={out['readings']['feedback3']}")
    check("③ 印文留空如实落库（seal_name 为空字符串，展示层归「佚名」）",
          (new_seal3 or {}).get("seal_name") == "", repr((new_seal3 or {}).get("seal_name")))
    check("③ 第二枚入库影像仍为正方形 WebP", bool(img3) and img3.get("width") == img3.get("height")
          and img3.get("mime") == "image/webp",
          f"width={img3.get('width')} height={img3.get('height')} mime={img3.get('mime')} bytes={img3.get('bytes')}")

    # ---------------- ⑤ 边界内（刚好 ≤ 1 MB）必须被接受 ----------------
    out["readings"]["prep_5"] = prep(True)
    picked5 = tab.js("window.__pick('near')")
    time.sleep(1.8)
    out["readings"]["pick_near"] = picked5
    out["readings"]["near_preview_exists"] = tab.js("!!document.querySelector('[data-upload-preview=\"seal-face\"]')")
    out["readings"]["near_feedback"] = tab.js("window.__feedback()")
    out["readings"]["near_summary"] = tab.js("window.__summary()")
    tab.js("window.__setForm('明', '私印', '')")
    seals_before5 = tab.js("window.__seals().length")
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(2.6)
    out["readings"]["seals_after_5"] = tab.js("window.__seals().length")
    out["readings"]["notice5"] = tab.js(
        "((document.querySelector('[data-admin-feedback=\"square-upload\"]')||{}).innerText||'').trim()")
    seal5 = tab.js(
        "(() => { const rows = window.__seals().filter(r => r.source === 'manual' && /^XA\\d{9}$/.test(r.stamp_id));"
        " rows.sort((a,b) => String(a.created_at).localeCompare(String(b.created_at)));"
        " return rows.length ? rows[rows.length-1] : null; })()")
    out["readings"]["new_seal5"] = seal5
    img5 = tab.js(f"window.__db({json.dumps((seal5 or {}).get('stamp_id'))})")
    out["readings"]["image_row5"] = img5
    check("⑤ 边界内探针（0.90–1.00 MB，≤ 上限）被**接受**并进入取景（上限不是一刀切拒绝）",
          bool(picked5) and 0 < (picked5.get("size") or 0) <= 1048576
          and out["readings"]["near_preview_exists"] is True
          and not (out["readings"]["near_feedback"] or "").strip(),
          f"size={picked5.get('size')} preview={out['readings']['near_preview_exists']} feedback={out['readings']['near_feedback']!r}")
    check("⑤ 边界内上传成功且入库影像仍为正方形 WebP",
          "已新增印章" in (out["readings"]["notice5"] or "")
          and out["readings"]["seals_after_5"] == seals_before5 + 1
          and bool(img5) and img5.get("width") == img5.get("height") and img5.get("mime") == "image/webp",
          f"{out['readings']['notice5']} | w={img5.get('width')} h={img5.get('height')} mime={img5.get('mime')} bytes={img5.get('bytes')}")

    # ---------------- ④ 缺必填仍由服务层拒（口径不变） ----------------
    out["readings"]["prep_4"] = prep(True)
    tab.js("window.__pick('portrait')")
    time.sleep(1.4)
    tab.js("window.__setForm('', '官印', '')")
    seals_before4 = tab.js("window.__seals().length")
    tab.js("document.querySelector('button[data-admin-action=\"upload-seal-submit\"]').click()")
    time.sleep(2.0)
    out["readings"]["feedback4_missing_dynasty"] = tab.js("window.__feedback()")
    out["readings"]["seals_after_4"] = tab.js("window.__seals().length")
    check("④ 缺朝代 ⇒ 服务层拒并展示其 message（口径未变）",
          "请补全必填项：朝代" in (out["readings"]["feedback4_missing_dynasty"] or "")
          and out["readings"]["seals_after_4"] == seals_before4,
          f"{out['readings']['feedback4_missing_dynasty']} | seals {seals_before4} -> {out['readings']['seals_after_4']}")

    # ---------------- ④ 网络：零 5196 / 零外链 ----------------
    urls = tab.requests()
    offline = [u for u in urls if not u.startswith(BASE) and not u.startswith("data:") and not u.startswith("blob:")]
    crop_calls = [u for u in urls if "5196" in u or "square-crop" in u]
    out["readings"]["request_count"] = len(urls)
    out["readings"]["non_base_requests"] = offline
    out["readings"]["square_crop_requests"] = crop_calls
    check("④ 全程零 5196 / 零 square-crop 调用", len(crop_calls) == 0, json.dumps(crop_calls))
    check("④ 全程零外链（除本机 5163 资源外无任何请求）", len(offline) == 0, json.dumps(offline[:8]))

    out["passed"] = sum(1 for c in out["checks"] if c["pass"])
    out["failed"] = sum(1 for c in out["checks"] if not c["pass"])
    out["re_hydrations_of_page_helpers"] = hydrations["count"]
    print(f"\n=== passed={out['passed']} failed={out['failed']} ===", flush=True)
    with open("/Users/kevin/bistro/xiai/feicui/ops/kong_xiai_k4_image_pipeline_raw.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
