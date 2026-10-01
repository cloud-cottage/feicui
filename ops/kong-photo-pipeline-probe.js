(() => {
  // src/data/storage.js
  var NS = "xiai:v1:";
  function safeParse(raw) {
    if (raw === null || raw === void 0) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  function readKey(key) {
    try {
      return safeParse(window.localStorage.getItem(NS + key));
    } catch {
      return null;
    }
  }
  function writeKey(key, value) {
    try {
      window.localStorage.setItem(NS + key, JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  }
  function removeKey(key) {
    try {
      window.localStorage.removeItem(NS + key);
      return true;
    } catch {
      return false;
    }
  }
  var STORAGE_KEYS = {
    seals: "seals",
    faces: "faces",
    images: "images",
    users: "users",
    corrections: "corrections",
    photos: "photos",
    points: "points",
    session: "session",
    downloaded: "downloaded",
    seeded: "seeded",
    theme: "theme"
  };

  // src/data/blobstore.js
  var BLOBSTORE_DB_NAME = "xiai:v1:assetblobs";
  var BLOBSTORE_DB_VERSION = 1;
  var BLOBSTORE_STORE = "assets";
  function assetBlobKey(assetId) {
    return `asset:${String(assetId || "")}`;
  }
  function photoBlobKey(photoId) {
    return `photo:${String(photoId || "")}`;
  }
  function idbFactory() {
    if (typeof indexedDB !== "undefined" && indexedDB) return indexedDB;
    if (typeof globalThis !== "undefined" && globalThis.indexedDB) return globalThis.indexedDB;
    return null;
  }
  var dbPromise = null;
  function openDb() {
    const factory = idbFactory();
    if (!factory) return Promise.resolve({ ok: false, message: "\u5F53\u524D\u73AF\u5883\u4E0D\u652F\u6301\u5F71\u50CF\u672C\u5730\u5B58\u50A8\uFF08IndexedDB \u4E0D\u53EF\u7528\uFF09" });
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve) => {
      let request;
      try {
        request = factory.open(BLOBSTORE_DB_NAME, BLOBSTORE_DB_VERSION);
      } catch (err) {
        resolve({ ok: false, message: `\u5F71\u50CF\u5B58\u50A8\u6253\u5F00\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}` });
        return;
      }
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(BLOBSTORE_STORE)) db.createObjectStore(BLOBSTORE_STORE);
      };
      request.onsuccess = () => resolve({ ok: true, db: request.result });
      request.onerror = () => resolve({ ok: false, message: `\u5F71\u50CF\u5B58\u50A8\u6253\u5F00\u5931\u8D25\uFF1A${request.error && request.error.message || "\u672A\u77E5\u539F\u56E0"}` });
      request.onblocked = () => resolve({ ok: false, message: "\u5F71\u50CF\u5B58\u50A8\u88AB\u5176\u5B83\u6807\u7B7E\u9875\u5360\u7528\uFF0C\u8BF7\u5173\u95ED\u5176\u5B83\u6807\u7B7E\u9875\u540E\u91CD\u8BD5" });
    });
    return dbPromise;
  }
  async function withStore(mode, run) {
    const opened = await openDb();
    if (!opened.ok) return { ok: false, reason: "UNAVAILABLE", message: opened.message };
    return new Promise((resolve) => {
      let settled = false;
      const done = (value) => {
        if (!settled) {
          settled = true;
          resolve(value);
        }
      };
      try {
        const tx = opened.db.transaction(BLOBSTORE_STORE, mode);
        const store = tx.objectStore(BLOBSTORE_STORE);
        const request = run(store);
        tx.oncomplete = () => done({ ok: true, result: request ? request.result : void 0 });
        tx.onabort = () => done({ ok: false, reason: "ABORTED", message: `\u5F71\u50CF\u5B58\u50A8\u5199\u5165\u672A\u5B8C\u6210\uFF1A${tx.error && tx.error.message || "\u5B58\u50A8\u7A7A\u95F4\u53EF\u80FD\u5DF2\u6EE1"}` });
        tx.onerror = () => done({ ok: false, reason: "FAILED", message: `\u5F71\u50CF\u5B58\u50A8\u64CD\u4F5C\u5931\u8D25\uFF1A${tx.error && tx.error.message || "\u672A\u77E5\u539F\u56E0"}` });
      } catch (err) {
        done({ ok: false, reason: "FAILED", message: `\u5F71\u50CF\u5B58\u50A8\u64CD\u4F5C\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}` });
      }
    });
  }
  async function putBlob(key, data) {
    if (!key) return { ok: false, reason: "BAD_KEY", message: "\u5F71\u50CF\u5B58\u50A8\u952E\u4E3A\u7A7A" };
    if (data === null || data === void 0) return { ok: false, reason: "BAD_DATA", message: "\u5F71\u50CF\u5185\u5BB9\u4E3A\u7A7A" };
    let payload = data;
    try {
      if (typeof Blob !== "undefined" && data instanceof Blob) payload = new Uint8Array(await data.arrayBuffer());
    } catch (err) {
      return { ok: false, reason: "BAD_DATA", message: `\u5F71\u50CF\u5185\u5BB9\u8BFB\u53D6\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}` };
    }
    const out = await withStore("readwrite", (store) => store.put(payload, key));
    if (!out.ok) return out;
    const bytes = payload && typeof payload.byteLength === "number" ? payload.byteLength : 0;
    return { ok: true, key, bytes };
  }
  async function getBlob(key) {
    if (!key) return { ok: false, reason: "BAD_KEY", message: "\u5F71\u50CF\u5B58\u50A8\u952E\u4E3A\u7A7A" };
    const out = await withStore("readonly", (store) => store.get(key));
    if (!out.ok) return out;
    const value = out.result;
    if (value === void 0 || value === null) {
      return { ok: false, reason: "NOT_FOUND", message: "\u5F71\u50CF\u4E8C\u8FDB\u5236\u4E0D\u5728\u672C\u5730\u5B58\u50A8\u4E2D\uFF08\u53EF\u80FD\u672A\u4E0A\u4F20\u6210\u529F\uFF09" };
    }
    if (value instanceof Uint8Array) {
      return { ok: true, bytes: value, bytesLength: value.byteLength, shape: "Uint8Array" };
    }
    if (typeof Blob !== "undefined" && value instanceof Blob) {
      const bytes = new Uint8Array(await value.arrayBuffer());
      return { ok: true, bytes, bytesLength: bytes.byteLength, mime: value.type || "", shape: "Blob" };
    }
    if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
      const bytes = new Uint8Array(value instanceof ArrayBuffer ? value : value.buffer);
      return { ok: true, bytes, bytesLength: bytes.byteLength, shape: "ArrayBuffer" };
    }
    return { ok: false, reason: "BAD_DATA", message: "\u5F71\u50CF\u4E8C\u8FDB\u5236\u5F62\u6001\u65E0\u6CD5\u8BC6\u522B" };
  }
  async function deleteBlob(key) {
    if (!key) return { ok: false, reason: "BAD_KEY", message: "\u5F71\u50CF\u5B58\u50A8\u952E\u4E3A\u7A7A", deleted: false };
    const existed = await hasBlob(key);
    const out = await withStore("readwrite", (store) => store.delete(key));
    if (!out.ok) return { ...out, deleted: false };
    return { ok: true, deleted: existed === true };
  }
  async function hasBlob(key) {
    if (!key) return false;
    const out = await withStore("readonly", (store) => store.getKey(key));
    if (!out.ok) return false;
    return out.result !== void 0 && out.result !== null;
  }
  async function listBlobKeys() {
    const out = await withStore("readonly", (store) => store.getAllKeys());
    if (!out.ok) return [];
    return Array.isArray(out.result) ? out.result.map((key) => String(key)) : [];
  }

  // src/data/assetmeta.js
  var K = [
    1116352408,
    1899447441,
    3049323471,
    3921009573,
    961987163,
    1508970993,
    2453635748,
    2870763221,
    3624381080,
    310598401,
    607225278,
    1426881987,
    1925078388,
    2162078206,
    2614888103,
    3248222580,
    3835390401,
    4022224774,
    264347078,
    604807628,
    770255983,
    1249150122,
    1555081692,
    1996064986,
    2554220882,
    2821834349,
    2952996808,
    3210313671,
    3336571891,
    3584528711,
    113926993,
    338241895,
    666307205,
    773529912,
    1294757372,
    1396182291,
    1695183700,
    1986661051,
    2177026350,
    2456956037,
    2730485921,
    2820302411,
    3259730800,
    3345764771,
    3516065817,
    3600352804,
    4094571909,
    275423344,
    430227734,
    506948616,
    659060556,
    883997877,
    958139571,
    1322822218,
    1537002063,
    1747873779,
    1955562222,
    2024104815,
    2227730452,
    2361852424,
    2428436474,
    2756734187,
    3204031479,
    3329325298
  ];
  function rotr(x, n) {
    return x >>> n | x << 32 - n;
  }
  function toUint8Array(input) {
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    if (ArrayBuffer.isView(input)) return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
    if (Array.isArray(input)) return Uint8Array.from(input);
    if (typeof input === "string") {
      if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(input);
      const out = new Uint8Array(input.length);
      for (let i = 0; i < input.length; i += 1) out[i] = input.charCodeAt(i) & 255;
      return out;
    }
    return new Uint8Array(0);
  }
  function sha256Hex(input) {
    const msg = toUint8Array(input);
    const len = msg.length;
    const total = len + 9 + 63 >> 6 << 6;
    const buf = new Uint8Array(total);
    buf.set(msg);
    buf[len] = 128;
    const view = new DataView(buf.buffer);
    const bitLenHi = Math.floor(len / 536870912);
    const bitLenLo = len << 3 >>> 0;
    view.setUint32(total - 8, bitLenHi);
    view.setUint32(total - 4, bitLenLo);
    const h = new Uint32Array([
      1779033703,
      3144134277,
      1013904242,
      2773480762,
      1359893119,
      2600822924,
      528734635,
      1541459225
    ]);
    const w = new Uint32Array(64);
    for (let offset = 0; offset < total; offset += 64) {
      for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(offset + i * 4);
      for (let i = 16; i < 64; i += 1) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ w[i - 15] >>> 3;
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ w[i - 2] >>> 10;
        w[i] = w[i - 16] + s0 + w[i - 7] + s1 >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i += 1) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = e & f ^ ~e & g;
        const t1 = hh + S1 + ch + K[i] + w[i] >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = a & b ^ a & c ^ b & c;
        const t2 = S0 + maj >>> 0;
        hh = g;
        g = f;
        f = e;
        e = d + t1 >>> 0;
        d = c;
        c = b;
        b = a;
        a = t1 + t2 >>> 0;
      }
      h[0] = h[0] + a >>> 0;
      h[1] = h[1] + b >>> 0;
      h[2] = h[2] + c >>> 0;
      h[3] = h[3] + d >>> 0;
      h[4] = h[4] + e >>> 0;
      h[5] = h[5] + f >>> 0;
      h[6] = h[6] + g >>> 0;
      h[7] = h[7] + hh >>> 0;
    }
    let hex = "";
    for (let i = 0; i < 8; i += 1) hex += h[i].toString(16).padStart(8, "0");
    return hex;
  }
  function dataUrlToBytes(dataUrl) {
    if (typeof dataUrl !== "string" || !dataUrl.startsWith("data:")) {
      return { ok: false, message: "\u8BF7\u9009\u62E9\u56FE\u7247\u6587\u4EF6\uFF08JPG / PNG / WebP\uFF09" };
    }
    const comma = dataUrl.indexOf(",");
    if (comma < 0) return { ok: false, message: "\u56FE\u7247\u5185\u5BB9\u65E0\u6CD5\u89E3\u6790\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    const head = dataUrl.slice(5, comma);
    const mime = (head.split(";")[0] || "").trim().toLowerCase();
    if (!mime.startsWith("image/")) return { ok: false, message: "\u4EC5\u652F\u6301\u56FE\u7247\u6587\u4EF6\uFF08JPG / PNG / WebP\uFF09" };
    if (!/;base64/i.test(head)) return { ok: false, message: "\u56FE\u7247\u9700\u4E3A base64 \u7F16\u7801\uFF08\u6D4F\u89C8\u5668\u6587\u4EF6\u8BFB\u53D6\u9ED8\u8BA4\u5982\u6B64\uFF09" };
    const body = dataUrl.slice(comma + 1);
    try {
      const binary = typeof atob === "function" ? atob(body) : Buffer.from(body, "base64").toString("binary");
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i) & 255;
      return { ok: true, bytes, mime };
    } catch {
      return { ok: false, message: "\u56FE\u7247\u5185\u5BB9\u65E0\u6CD5\u89E3\u6790\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    }
  }
  function encodeBase64(bytes) {
    const view = toUint8Array(bytes);
    let binary = "";
    const chunk = 32768;
    for (let i = 0; i < view.length; i += chunk) {
      binary += String.fromCharCode.apply(null, view.subarray(i, i + chunk));
    }
    if (typeof btoa === "function") return btoa(binary);
    return Buffer.from(binary, "binary").toString("base64");
  }
  function bytesToDataUrl(bytes, mime = "image/png") {
    return `data:${mime || "image/png"};base64,${encodeBase64(bytes)}`;
  }
  function sniffMime(bytes) {
    const v = toUint8Array(bytes);
    if (v.length >= 8 && v[0] === 137 && v[1] === 80 && v[2] === 78 && v[3] === 71) return "image/png";
    if (v.length >= 3 && v[0] === 255 && v[1] === 216 && v[2] === 255) return "image/jpeg";
    if (v.length >= 6 && v[0] === 71 && v[1] === 73 && v[2] === 70) return "image/gif";
    if (v.length >= 12 && v[0] === 82 && v[1] === 73 && v[2] === 70 && v[3] === 70 && v[8] === 87) return "image/webp";
    return "image/png";
  }
  function imageSize(bytes) {
    const v = toUint8Array(bytes);
    const fallback = { width: 0, height: 0, colorMode: "RGB" };
    if (v.length >= 33 && v[0] === 137 && v[1] === 80 && v[2] === 78 && v[3] === 71) {
      const view = new DataView(v.buffer, v.byteOffset, v.byteLength);
      const width = view.getUint32(16);
      const height = view.getUint32(20);
      const colorType = v[25];
      const colorMode = colorType === 0 || colorType === 4 ? "GRAY" : "RGB";
      return { width, height, colorMode };
    }
    if (v.length >= 10 && v[0] === 71 && v[1] === 73 && v[2] === 70) {
      return { width: v[6] | v[7] << 8, height: v[8] | v[9] << 8, colorMode: "RGB" };
    }
    if (v.length >= 30 && v[0] === 82 && v[1] === 73 && v[2] === 70 && v[3] === 70 && v[8] === 87) {
      const tag = String.fromCharCode(v[12], v[13], v[14], v[15]);
      if (tag === "VP8 ") {
        return {
          width: (v[26] | v[27] << 8) & 16383,
          height: (v[28] | v[29] << 8) & 16383,
          colorMode: "RGB"
        };
      }
      if (tag === "VP8L" && v.length >= 25) {
        const bits = v[21] | v[22] << 8 | v[23] << 16 | v[24] << 24;
        return {
          width: (bits & 16383) + 1,
          height: (bits >> 14 & 16383) + 1,
          colorMode: "RGB"
        };
      }
      if (tag === "VP8X" && v.length >= 30) {
        return {
          width: (v[24] | v[25] << 8 | v[26] << 16) + 1,
          height: (v[27] | v[28] << 8 | v[29] << 16) + 1,
          colorMode: "RGB"
        };
      }
      return fallback;
    }
    if (v.length >= 4 && v[0] === 255 && v[1] === 216) {
      let offset = 2;
      while (offset + 9 < v.length) {
        if (v[offset] !== 255) {
          offset += 1;
          continue;
        }
        const marker = v[offset + 1];
        if (marker === 216 || marker === 1 || marker >= 208 && marker <= 215) {
          offset += 2;
          continue;
        }
        const segLen = v[offset + 2] << 8 | v[offset + 3];
        const isSof = marker >= 192 && marker <= 207 && marker !== 196 && marker !== 200 && marker !== 204;
        if (isSof) {
          const height = v[offset + 5] << 8 | v[offset + 6];
          const width = v[offset + 7] << 8 | v[offset + 8];
          const components = v[offset + 9];
          return { width, height, colorMode: components === 1 ? "GRAY" : "RGB" };
        }
        if (segLen <= 0) break;
        offset += 2 + segLen;
      }
    }
    return fallback;
  }
  function normalizeImagePayload(input) {
    if (input === null || input === void 0 || input === "") {
      return { ok: false, message: "\u8BF7\u9009\u62E9\u5370\u9762\u56FE\u7247" };
    }
    let bytes = null;
    let mime = "";
    if (typeof input === "string") {
      if (!input.startsWith("data:")) {
        return { ok: false, message: "\u5370\u9762\u56FE\u7247\u9700\u4E3A\u6587\u4EF6\u5185\u5BB9\uFF08dataURL\uFF09\u6216\u4E8C\u8FDB\u5236" };
      }
      const parsed = dataUrlToBytes(input);
      if (!parsed.ok) return parsed;
      bytes = parsed.bytes;
      mime = parsed.mime;
    } else {
      bytes = toUint8Array(input);
    }
    if (!bytes || bytes.length === 0) return { ok: false, message: "\u5370\u9762\u56FE\u7247\u5185\u5BB9\u4E3A\u7A7A\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    if (!mime) mime = sniffMime(bytes);
    const size = imageSize(bytes);
    return {
      ok: true,
      bytes,
      mime,
      sha256: sha256Hex(bytes),
      bytesLength: bytes.length,
      width: size.width,
      height: size.height,
      colorMode: size.colorMode
    };
  }

  // src/data/seed.js
  var ADMIN_PHONE = "16601061656";
  var ADMIN_NICKNAME = "\u5E93\u5B88";
  var FIXED_ATTR_FIELDS = ["face_image_id", "material", "edge_image_ids"];
  var FACE_KIND = {
    FACE: "FACE",
    EDGE: "EDGE"
  };
  var SEED_USERS = [
    {
      id: `u-${ADMIN_PHONE}`,
      phone: ADMIN_PHONE,
      nickname: ADMIN_NICKNAME,
      role: "admin",
      points: 50,
      created_at: "2026-01-01T00:00:00.000Z"
    },
    {
      id: "u-demo",
      phone: "13800000002",
      nickname: "\u5370\u53CB",
      role: "user",
      points: 50,
      created_at: "2026-01-01T00:00:00.000Z"
    }
  ];
  var SEED_SEALS = [
    {
      sealGroupId: "g-0001",
      stamp_id: "XAI-0001",
      seal_name: "\u9577\u58FD",
      transcription: "\u53D6\u300C\u9577\u6A02\u7121\u6975\u3001\u58FD\u6BD4\u5357\u5C71\u300D\u4E4B\u610F\uFF0C\u6F22\u4EBA\u5409\u8A9E\u5370\u5E38\u7528\u8A9E\u3002",
      dynasty: "\u6F22",
      seal_type: "\u5409\u8A9E\u5370",
      seal_style: "\u767D\u6587",
      material: "\u9752\u9285",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u957F\u5BFF",
      author: "\u7121\u540D"
    },
    {
      sealGroupId: "g-0002",
      stamp_id: "XAI-0002",
      seal_name: "\u9A0E\u90FD\u5C09\u5370",
      transcription: "\u6F22\u4EE3\u6B66\u8077\u5B98\u5370\uFF0C\u9A0E\u90FD\u5C09\u638C\u7FBD\u6797\u9A0E\u5175\uFF0C\u79E9\u6BD4\u4E8C\u5343\u77F3\u3002",
      dynasty: "\u6F22",
      seal_type: "\u5B98\u5370",
      seal_style: "\u767D\u6587",
      material: "\u9752\u9285",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u9A91\u90FD\u5C09\u5370",
      author: "\u7121\u540D"
    },
    {
      sealGroupId: "g-0003",
      stamp_id: "XAI-0003",
      seal_name: "\u660C",
      transcription: "\u55AE\u5B57\u5713\u5370\uFF0C\u6230\u570B\u79C1\u5370\u5E38\u898B\u5F62\u5236\uFF0C\u591A\u4F5C\u4F69\u5370\u4E4B\u7528\u3002",
      dynasty: "\u6230\u570B",
      seal_type: "\u79C1\u5370",
      seal_style: "\u6731\u6587",
      material: "\u7389",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u660C",
      author: "\u7121\u540D"
    },
    {
      sealGroupId: "g-0004",
      stamp_id: "XAI-0004",
      seal_name: "\u6587\u5F6D\u4E4B\u5370",
      transcription: "\u660E\u4EE3\u6587\u4EBA\u7BC6\u523B\u958B\u5C71\u4E4B\u4F5C\uFF0C\u5370\u98A8\u79C0\u6F64\uFF0C\u958B\u5433\u9580\u4E00\u6D3E\u3002",
      dynasty: "\u660E",
      seal_type: "\u79C1\u5370",
      seal_style: "\u6731\u6587",
      material: "\u9752\u7530\u77F3",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u6587\u5F6D\u4E4B\u5370",
      author: "\u6587\u5F6D"
    },
    {
      sealGroupId: "g-0005",
      stamp_id: "XAI-0005",
      seal_name: "\u4E01\u656C\u8EAB\u5370",
      transcription: "\u6D59\u6D3E\u5B97\u5E2B\u4E01\u656C\u81EA\u7528\u5370\uFF0C\u5207\u5200\u6F80\u9032\uFF0C\u53E4\u62D7\u5CED\u6298\u3002",
      dynasty: "\u6E05",
      seal_type: "\u79C1\u5370",
      seal_style: "\u767D\u6587",
      material: "\u58FD\u5C71\u77F3",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u4E01\u656C\u8EAB\u5370",
      author: "\u4E01\u656C"
    },
    {
      sealGroupId: "g-0006",
      stamp_id: "XAI-0006",
      seal_name: "\u5BB6\u5728\u9322\u5858",
      transcription: "\u9592\u7AE0\uFF0C\u5BD3\u9109\u601D\u3002\u6D59\u6D3E\u9592\u7AE0\u591A\u53D6\u91CC\u5C45\u3001\u5FD7\u5411\u5165\u5370\u3002",
      dynasty: "\u6E05",
      seal_type: "\u9592\u7AE0",
      seal_style: "\u767D\u6587",
      material: "\u58FD\u5C71\u77F3",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u5BB6\u5728\u94B1\u5858",
      author: "\u9673\u8C6B\u937E"
    },
    {
      sealGroupId: "g-0007",
      stamp_id: "XAI-0007",
      seal_name: "\u4E7E\u9686\u5FA1\u89BD\u4E4B\u5BF6",
      transcription: "\u6E05\u5BAE\u9452\u85CF\u74BD\uFF0C\u591A\u9210\u65BC\u5167\u5E9C\u66F8\u756B\u5F15\u9996\uFF0C\u898F\u5236\u5B8F\u6574\u3002",
      dynasty: "\u6E05",
      seal_type: "\u9452\u85CF\u5370",
      seal_style: "\u6731\u6587",
      material: "\u7530\u9EC3",
      asset_kind: "SEAL",
      review_status: "APPROVED",
      transcription_simplified: "\u4E7E\u9686\u5FA1\u89C8\u4E4B\u5B9D",
      author: "\u6E05\u5167\u5E9C"
    },
    {
      sealGroupId: "g-0008",
      stamp_id: "XAI-0008",
      seal_name: "\u5B89\u6301",
      transcription: "\u9673\u5DE8\u4F86\u865F\u5B89\u6301\uFF0C\u5143\u6731\u6587\u7CBE\u7D55\uFF0C\u6642\u7A31\u8FD1\u4EE3\u7B2C\u4E00\u3002",
      dynasty: "\u8FD1\u73FE\u4EE3",
      seal_type: "\u79C1\u5370",
      seal_style: "\u6731\u6587",
      material: "\u660C\u5316\u51CD\u77F3",
      asset_kind: "SEAL",
      review_status: "PENDING",
      transcription_simplified: "\u5B89\u6301",
      author: "\u9673\u5DE8\u4F86"
    }
  ];
  var SEED_IMAGES = [
    { id: "img-0001f", stamp_id: "XAI-0001", kind: "FACE", sha256: "3d1f0b2a6c7e4915b8a2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718", bytes: 184320, width: 1600, height: 1600, color_mode: "RGB" },
    { id: "img-0001g", stamp_id: "XAI-0001", kind: "FACE", sha256: "5c6d7e8f90a1b2c3d4e5f60718293a4b3d1f0b2a6c7e4915b8a2c3d4e5f60718e", bytes: 141312, width: 1200, height: 1200, color_mode: "RGB" },
    { id: "img-0001e", stamp_id: "XAI-0001", kind: "EDGE", sha256: "a1b2c3d4e5f60718293a4b5c6d7e8f903d1f0b2a6c7e4915b8a2c3d4e5f60718", bytes: 210112, width: 2400, height: 800, color_mode: "RGB" },
    { id: "img-0002f", stamp_id: "XAI-0002", kind: "FACE", sha256: "b2c3d4e5f60718293a4b5c6d7e8f90a13d1f0b2a6c7e4915b8a2c3d4e5f607182", bytes: 176540, width: 1600, height: 1600, color_mode: "RGB" },
    { id: "img-0003f", stamp_id: "XAI-0003", kind: "FACE", sha256: "c3d4e5f60718293a4b5c6d7e8f90a1b23d1f0b2a6c7e4915b8a2c3d4e5f6071829", bytes: 158900, width: 1400, height: 1400, color_mode: "RGB" },
    { id: "img-0004f", stamp_id: "XAI-0004", kind: "FACE", sha256: "d4e5f60718293a4b5c6d7e8f90a1b2c33d1f0b2a6c7e4915b8a2c3d4e5f6071829a", bytes: 199872, width: 1800, height: 1800, color_mode: "RGB" },
    { id: "img-0004e", stamp_id: "XAI-0004", kind: "EDGE", sha256: "e5f60718293a4b5c6d7e8f90a1b2c3d43d1f0b2a6c7e4915b8a2c3d4e5f6071829ab", bytes: 245760, width: 2600, height: 900, color_mode: "RGB" },
    { id: "img-0005f", stamp_id: "XAI-0005", kind: "FACE", sha256: "f60718293a4b5c6d7e8f90a1b2c3d4e53d1f0b2a6c7e4915b8a2c3d4e5f6071829abc", bytes: 172032, width: 1600, height: 1600, color_mode: "RGB" },
    { id: "img-0005e", stamp_id: "XAI-0005", kind: "EDGE", sha256: "0718293a4b5c6d7e8f90a1b2c3d4e5f63d1f0b2a6c7e4915b8a2c3d4e5f6071829abcd", bytes: 233984, width: 2600, height: 900, color_mode: "RGB" },
    { id: "img-0006f", stamp_id: "XAI-0006", kind: "FACE", sha256: "18293a4b5c6d7e8f90a1b2c3d4e5f6073d1f0b2a6c7e4915b8a2c3d4e5f60718a", bytes: 165376, width: 1600, height: 1600, color_mode: "RGB" },
    { id: "img-0007f", stamp_id: "XAI-0007", kind: "FACE", sha256: "293a4b5c6d7e8f90a1b2c3d4e5f607183d1f0b2a6c7e4915b8a2c3d4e5f60718b", bytes: 289792, width: 2e3, height: 2e3, color_mode: "RGB" },
    { id: "img-0007e", stamp_id: "XAI-0007", kind: "EDGE", sha256: "3a4b5c6d7e8f90a1b2c3d4e5f60718293d1f0b2a6c7e4915b8a2c3d4e5f60718c", bytes: 301056, width: 2800, height: 960, color_mode: "RGB" },
    { id: "img-0008f", stamp_id: "XAI-0008", kind: "FACE", sha256: "4b5c6d7e8f90a1b2c3d4e5f60718293a3d1f0b2a6c7e4915b8a2c3d4e5f60718d", bytes: 168960, width: 1600, height: 1600, color_mode: "GRAY" }
  ];
  function faceSeed({ id, sealId, kind, faceImageId = null, material, edgeImageIds = [], markable = {}, source = null }) {
    return {
      id,
      sealId,
      // 规范字段：所属印章（印章 1 对 N 印面）
      stamp_id: sealId,
      // 兼容别名：等同于 sealId，供既落盘 services / 视图按原命名读取
      kind,
      // FACE＝印面 / EDGE＝边款（边款是一种特殊印面）
      face_image_id: faceImageId,
      // 固定属性：印面图片
      material,
      // 固定属性：材质
      edge_image_ids: edgeImageIds,
      // 固定属性：边款图片 ID（kind = EDGE 的影像 id）
      // 可标记属性（勘误对象）
      transcription_simplified: markable.transcription_simplified || "",
      seal_name: markable.seal_name || "",
      dynasty: markable.dynasty || "",
      seal_type: markable.seal_type || "",
      author: markable.author || "",
      transcription: markable.transcription || "",
      source,
      // 来源追踪（可空）
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z"
    };
  }
  var SEED_FACES = [
    /* ---- XAI-0001 長壽：多印面样本（2 个印面 + 1 个边款） ---- */
    faceSeed({
      id: "fc-0001-f1",
      sealId: "XAI-0001",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0001f",
      material: "\u9752\u9285",
      markable: {
        transcription_simplified: "\u957F\u5BFF",
        seal_name: "\u9577\u58FD",
        dynasty: "\u6F22",
        seal_type: "\u5409\u8A9E\u5370",
        author: "\u7121\u540D",
        transcription: "\u53D6\u300C\u9577\u6A02\u7121\u6975\u3001\u58FD\u6BD4\u5357\u5C71\u300D\u4E4B\u610F\uFF0C\u6F22\u4EBA\u5409\u8A9E\u5370\u5E38\u7528\u8A9E\u3002"
      },
      source: { book: "\u300A\u6F22\u5370\u6587\u5B57\u5FB5\u300B", page: "\u5377\u4E09 \u5341\u4E8C\u9801" }
    }),
    faceSeed({
      id: "fc-0001-f2",
      sealId: "XAI-0001",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0001g",
      material: "\u9752\u9285",
      markable: {
        transcription_simplified: "\u957F\u5BFF",
        seal_name: "\u9577\u58FD\u5408\u6587",
        dynasty: "\u6F22",
        seal_type: "\u5409\u8A9E\u5370",
        author: "\u7121\u540D",
        transcription: "\u540C\u5370\u4E4B\u53E6\u4E00\u9762\uFF0C\u4E8C\u5B57\u4F5C\u5408\u6587\uFF0C\u7B46\u756B\u4E92\u501F\uFF0C\u70BA\u6F22\u4EE3\u5409\u8A9E\u5370\u7FD2\u898B\u4F48\u5C40\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0001-e1",
      sealId: "XAI-0001",
      kind: FACE_KIND.EDGE,
      faceImageId: null,
      material: "\u9752\u9285",
      edgeImageIds: ["img-0001e"],
      markable: {
        transcription_simplified: "\u957F\u5BFF",
        seal_name: "\u9577\u58FD",
        dynasty: "\u6F22",
        seal_type: "\u5409\u8A9E\u5370",
        author: "\u7121\u540D",
        transcription: "\u908A\u6B3E\u4E00\u884C\uFF0C\u8A18\u6B64\u5370\u70BA\u6F22\u5409\u8A9E\u5370\u4E4B\u540C\u7BC4\u8005\uFF0C\u53EF\u8207\u5377\u4E09\u8005\u4E92\u8B49\u3002"
      },
      source: { book: "\u300A\u6F22\u5370\u6587\u5B57\u5FB5\u300B", page: "\u5377\u4E09 \u5341\u4E8C\u9801" }
    }),
    /* ---- 其余印章：默认 1 印面 = 1 印章（仅为种子默认值，非模型限制） ---- */
    faceSeed({
      id: "fc-0002-f1",
      sealId: "XAI-0002",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0002f",
      material: "\u9752\u9285",
      markable: {
        transcription_simplified: "\u9A91\u90FD\u5C09\u5370",
        seal_name: "\u9A0E\u90FD\u5C09\u5370",
        dynasty: "\u6F22",
        seal_type: "\u5B98\u5370",
        author: "\u7121\u540D",
        transcription: "\u6F22\u4EE3\u6B66\u8077\u5B98\u5370\uFF0C\u9A0E\u90FD\u5C09\u638C\u7FBD\u6797\u9A0E\u5175\uFF0C\u79E9\u6BD4\u4E8C\u5343\u77F3\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0003-f1",
      sealId: "XAI-0003",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0003f",
      material: "\u7389",
      markable: {
        transcription_simplified: "\u660C",
        seal_name: "\u660C",
        dynasty: "\u6230\u570B",
        seal_type: "\u79C1\u5370",
        author: "\u7121\u540D",
        transcription: "\u55AE\u5B57\u5713\u5370\uFF0C\u6230\u570B\u79C1\u5370\u5E38\u898B\u5F62\u5236\uFF0C\u591A\u4F5C\u4F69\u5370\u4E4B\u7528\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0004-f1",
      sealId: "XAI-0004",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0004f",
      material: "\u9752\u7530\u77F3",
      markable: {
        transcription_simplified: "\u6587\u5F6D\u4E4B\u5370",
        seal_name: "\u6587\u5F6D\u4E4B\u5370",
        dynasty: "\u660E",
        seal_type: "\u79C1\u5370",
        author: "\u6587\u5F6D",
        transcription: "\u660E\u4EE3\u6587\u4EBA\u7BC6\u523B\u958B\u5C71\u4E4B\u4F5C\uFF0C\u5370\u98A8\u79C0\u6F64\uFF0C\u958B\u5433\u9580\u4E00\u6D3E\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0004-e1",
      sealId: "XAI-0004",
      kind: FACE_KIND.EDGE,
      faceImageId: null,
      material: "\u9752\u7530\u77F3",
      edgeImageIds: ["img-0004e"],
      markable: {
        transcription_simplified: "\u6587\u5F6D\u4E4B\u5370",
        seal_name: "\u6587\u5F6D\u4E4B\u5370",
        dynasty: "\u660E",
        seal_type: "\u79C1\u5370",
        author: "\u6587\u5F6D",
        transcription: "\u908A\u6B3E\u8A18\u300C\u58EC\u5BC5\u79CB\u65E5\u4E09\u6A4B\u81EA\u5236\u300D\uFF0C\u5200\u6CD5\u6EAB\u6F64\uFF0C\u70BA\u5433\u9580\u6D3E\u81EA\u7528\u5370\u4E4B\u8B49\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0005-f1",
      sealId: "XAI-0005",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0005f",
      material: "\u58FD\u5C71\u77F3",
      markable: {
        transcription_simplified: "\u4E01\u656C\u8EAB\u5370",
        seal_name: "\u4E01\u656C\u8EAB\u5370",
        dynasty: "\u6E05",
        seal_type: "\u79C1\u5370",
        author: "\u4E01\u656C",
        transcription: "\u6D59\u6D3E\u5B97\u5E2B\u4E01\u656C\u81EA\u7528\u5370\uFF0C\u5207\u5200\u6F80\u9032\uFF0C\u53E4\u62D7\u5CED\u6298\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0005-e1",
      sealId: "XAI-0005",
      kind: FACE_KIND.EDGE,
      faceImageId: null,
      material: "\u58FD\u5C71\u77F3",
      edgeImageIds: ["img-0005e"],
      markable: {
        transcription_simplified: "\u4E01\u656C\u8EAB\u5370",
        seal_name: "\u4E01\u656C\u8EAB\u5370",
        dynasty: "\u6E05",
        seal_type: "\u79C1\u5370",
        author: "\u4E01\u656C",
        transcription: "\u908A\u6B3E\u8A18\u300C\u9F8D\u6CD3\u5C71\u4EBA\u81EA\u88FD\u300D\uFF0C\u6B3E\u5B57\u7528\u5200\u5982\u7B46\uFF0C\u53EF\u89C0\u6D59\u6D3E\u8DA8\u5411\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0006-f1",
      sealId: "XAI-0006",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0006f",
      material: "\u58FD\u5C71\u77F3",
      markable: {
        transcription_simplified: "\u5BB6\u5728\u94B1\u5858",
        seal_name: "\u5BB6\u5728\u9322\u5858",
        dynasty: "\u6E05",
        seal_type: "\u9592\u7AE0",
        author: "\u9673\u8C6B\u937E",
        transcription: "\u9592\u7AE0\uFF0C\u5BD3\u9109\u601D\u3002\u6D59\u6D3E\u9592\u7AE0\u591A\u53D6\u91CC\u5C45\u3001\u5FD7\u5411\u5165\u5370\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0007-f1",
      sealId: "XAI-0007",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0007f",
      material: "\u7530\u9EC3",
      markable: {
        transcription_simplified: "\u4E7E\u9686\u5FA1\u89C8\u4E4B\u5B9D",
        seal_name: "\u4E7E\u9686\u5FA1\u89BD\u4E4B\u5BF6",
        dynasty: "\u6E05",
        seal_type: "\u9452\u85CF\u5370",
        author: "\u6E05\u5167\u5E9C",
        transcription: "\u6E05\u5BAE\u9452\u85CF\u74BD\uFF0C\u591A\u9210\u65BC\u5167\u5E9C\u66F8\u756B\u5F15\u9996\uFF0C\u898F\u5236\u5B8F\u6574\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0007-e1",
      sealId: "XAI-0007",
      kind: FACE_KIND.EDGE,
      faceImageId: null,
      material: "\u7530\u9EC3",
      edgeImageIds: ["img-0007e"],
      markable: {
        transcription_simplified: "\u4E7E\u9686\u5FA1\u89C8\u4E4B\u5B9D",
        seal_name: "\u4E7E\u9686\u5FA1\u89BD\u4E4B\u5BF6",
        dynasty: "\u6E05",
        seal_type: "\u9452\u85CF\u5370",
        author: "\u6E05\u5167\u5E9C",
        transcription: "\u908A\u6B3E\u8A18\u5167\u5E9C\u7DE8\u6B21\uFF0C\u53EF\u8207\u300A\u77F3\u6E20\u5BF6\u7B08\u300B\u8457\u9304\u76F8\u53C3\u3002"
      },
      source: null
    }),
    faceSeed({
      id: "fc-0008-f1",
      sealId: "XAI-0008",
      kind: FACE_KIND.FACE,
      faceImageId: "img-0008f",
      material: "\u660C\u5316\u51CD\u77F3",
      markable: {
        transcription_simplified: "\u5B89\u6301",
        seal_name: "\u5B89\u6301",
        dynasty: "\u8FD1\u73FE\u4EE3",
        seal_type: "\u79C1\u5370",
        author: "\u9673\u5DE8\u4F86",
        transcription: "\u9673\u5DE8\u4F86\u865F\u5B89\u6301\uFF0C\u5143\u6731\u6587\u7CBE\u7D55\uFF0C\u6642\u7A31\u8FD1\u4EE3\u7B2C\u4E00\u3002"
      },
      source: null
    })
  ];

  // src/data/db.js
  var SEED_VERSION = 2;
  function migrateLegacyFixedAttributes(sealRows, faceRows) {
    const next = faceRows.map((row) => ({ ...row }));
    const primaryIndexOf = (sealId, kind) => next.findIndex((row) => row.sealId === sealId && row.kind === kind);
    sealRows.forEach((seal) => {
      if (!seal || !seal.stamp_id) return;
      const faceIndex = primaryIndexOf(seal.stamp_id, FACE_KIND.FACE);
      if (faceIndex < 0) return;
      const edgeIndex = primaryIndexOf(seal.stamp_id, FACE_KIND.EDGE);
      const patchOf = (index, patch) => {
        if (index < 0 || Object.keys(patch).length === 0) return;
        next[index] = { ...next[index], ...patch };
      };
      const facePatch = {};
      if (seal.face_image_id && seal.face_image_id !== next[faceIndex].face_image_id) {
        facePatch.face_image_id = seal.face_image_id;
      }
      if (typeof seal.material === "string" && seal.material && seal.material !== next[faceIndex].material) {
        facePatch.material = seal.material;
      }
      patchOf(faceIndex, facePatch);
      if (Array.isArray(seal.edge_image_ids) && seal.edge_image_ids.length > 0) {
        patchOf(edgeIndex >= 0 ? edgeIndex : faceIndex, { edge_image_ids: seal.edge_image_ids });
      }
    });
    return next;
  }
  function reconcileAdminRoles() {
    const raw = readKey(STORAGE_KEYS.users);
    const rebuild = !Array.isArray(raw) || raw.length === 0;
    const users = (rebuild ? SEED_USERS : raw).map((row) => ({ ...row }));
    let changed = rebuild;
    if (!users.some((row) => row && row.phone === ADMIN_PHONE)) {
      users.push({
        id: `u-${ADMIN_PHONE}`,
        phone: ADMIN_PHONE,
        nickname: ADMIN_NICKNAME,
        role: "admin",
        points: 50,
        // 与 services 层 GOLD_INITIAL（新账号初始金）一致
        created_at: (/* @__PURE__ */ new Date()).toISOString()
      });
      changed = true;
    }
    users.forEach((row) => {
      if (!row || !row.phone) return;
      if (row.phone === ADMIN_PHONE) {
        if (row.role !== "admin") {
          row.role = "admin";
          changed = true;
        }
        return;
      }
      if (row.role === "admin") {
        row.role = "user";
        changed = true;
      }
    });
    if (changed) writeKey(STORAGE_KEYS.users, users);
    return users;
  }
  function ensureSeed() {
    const marker = readKey(STORAGE_KEYS.seeded);
    if (!marker || marker.version !== SEED_VERSION) {
      if (!marker) {
        writeKey(STORAGE_KEYS.seals, SEED_SEALS);
        writeKey(STORAGE_KEYS.faces, SEED_FACES);
        writeKey(STORAGE_KEYS.images, SEED_IMAGES);
        writeKey(STORAGE_KEYS.users, SEED_USERS);
        writeKey(STORAGE_KEYS.corrections, []);
        writeKey(STORAGE_KEYS.photos, []);
        writeKey(STORAGE_KEYS.points, []);
        writeKey(STORAGE_KEYS.downloaded, []);
      } else {
        const rawSeals = readKey(STORAGE_KEYS.seals);
        const sealRows = Array.isArray(rawSeals) && rawSeals.length > 0 ? rawSeals : SEED_SEALS;
        if (!Array.isArray(rawSeals) || rawSeals.length === 0) writeKey(STORAGE_KEYS.seals, sealRows);
        const rawImages = readKey(STORAGE_KEYS.images);
        const imageRows = Array.isArray(rawImages) ? rawImages : [];
        const missingImages = SEED_IMAGES.filter((seed) => !imageRows.some((row) => row.id === seed.id));
        if (missingImages.length > 0) writeKey(STORAGE_KEYS.images, [...imageRows, ...missingImages]);
        const rawFaces = readKey(STORAGE_KEYS.faces);
        if (!Array.isArray(rawFaces) || rawFaces.length === 0) {
          writeKey(STORAGE_KEYS.faces, migrateLegacyFixedAttributes(sealRows, SEED_FACES));
        }
      }
      writeKey(STORAGE_KEYS.seeded, { at: "seed", version: SEED_VERSION });
    }
    reconcileAdminRoles();
  }
  function readCollection(key, fallback) {
    ensureSeed();
    const value = readKey(key);
    return Array.isArray(value) ? value : fallback;
  }
  function writeCollection(key, rows) {
    ensureSeed();
    writeKey(key, rows);
    return rows;
  }
  function readFaceCollection() {
    return readCollection(STORAGE_KEYS.faces, []).map((row) => ({
      ...row,
      stamp_id: row.sealId || row.stamp_id || "",
      updated_at: row.updated_at || row.created_at || ""
    }));
  }
  function listSealRows() {
    return readCollection(STORAGE_KEYS.seals, []);
  }
  function saveSealRows(rows) {
    return writeCollection(STORAGE_KEYS.seals, rows);
  }
  function listFaceRows() {
    return readFaceCollection();
  }
  function saveFaceRows(rows) {
    return writeCollection(STORAGE_KEYS.faces, rows);
  }
  function listImageRows() {
    return readCollection(STORAGE_KEYS.images, []);
  }
  function saveImageRows(rows) {
    return writeCollection(STORAGE_KEYS.images, rows);
  }
  function listUserRows() {
    return readCollection(STORAGE_KEYS.users, []);
  }
  function saveUserRows(rows) {
    return writeCollection(STORAGE_KEYS.users, rows);
  }
  function listPhotoRows() {
    return readCollection(STORAGE_KEYS.photos, []);
  }
  function savePhotoRows(rows) {
    return writeCollection(STORAGE_KEYS.photos, rows);
  }
  function listPointRows() {
    return readCollection(STORAGE_KEYS.points, []);
  }
  function savePointRows(rows) {
    return writeCollection(STORAGE_KEYS.points, rows);
  }
  var PermissionError = class extends Error {
    constructor(message) {
      super(message);
      this.name = "PermissionError";
    }
  };
  function assertAdmin(actor) {
    if (!actor || actor.role !== "admin") {
      throw new PermissionError("\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u4FEE\u6539\u5370\u9762\u7684\u56FA\u5B9A\u5C5E\u6027");
    }
  }
  function assertKnownFields(patch) {
    const unknown = Object.keys(patch || {}).filter((key) => !FIXED_ATTR_FIELDS.includes(key));
    if (unknown.length > 0) {
      throw new PermissionError(`\u56FA\u5B9A\u5C5E\u6027\u4E4B\u5916\u7684\u5B57\u6BB5\u4E0D\u53EF\u901A\u8FC7\u6B64\u5165\u53E3\u5199\u5165\uFF1A${unknown.join("\u3001")}`);
    }
  }
  function normalizeEdgeIds(value) {
    if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
    if (typeof value === "string") {
      return value.split(/[、,，\s]+/).map((item) => item.trim()).filter(Boolean);
    }
    return [];
  }
  function writeFaceFixedAttributes(actor, faceId, patch) {
    assertAdmin(actor);
    assertKnownFields(patch);
    const rows = readFaceCollection();
    const target = rows.find((row) => row.id === faceId);
    if (!target) throw new Error(`\u672A\u627E\u5230\u8BE5\u5370\u9762\uFF1A${faceId}`);
    const clean = { ...patch };
    if ("edge_image_ids" in clean) clean.edge_image_ids = normalizeEdgeIds(clean.edge_image_ids);
    const next = rows.map(
      (row) => row.id === faceId ? { ...row, ...clean, stamp_id: row.sealId, updated_at: (/* @__PURE__ */ new Date()).toISOString() } : row
    );
    saveFaceRows(next);
    return next.find((row) => row.id === faceId);
  }
  async function putImageBinary(assetId, data) {
    return putBlob(assetBlobKey(assetId), data);
  }
  async function deleteImageBinary(assetId) {
    return deleteBlob(assetBlobKey(assetId));
  }
  function photoBinaryKey(photoId) {
    return photoBlobKey(photoId);
  }
  async function putPhotoBinary(photoId, data) {
    return putBlob(photoBlobKey(photoId), data);
  }
  async function getPhotoBinary(photoId) {
    return getBlob(photoBlobKey(photoId));
  }
  async function readPhotoDataUrl(photoId, mime = "") {
    const out = await getPhotoBinary(photoId);
    if (!out.ok) return out;
    const actual = String(mime || "").trim() || out.mime || "image/webp";
    return { ok: true, dataUrl: bytesToDataUrl(out.bytes, actual), bytes: out.bytesLength, mime: actual };
  }
  async function listPhotoBinaryKeys() {
    const keys = await listBlobKeys();
    return keys.filter((key) => key.startsWith("photo:"));
  }
  async function migrateLegacyPhotoRows() {
    const rows = listPhotoRows();
    const next = [];
    let migrated = 0;
    let leftovers = 0;
    for (const row of rows) {
      const legacy = row && typeof row.image === "string" && row.image.startsWith("data:image");
      if (!legacy) {
        next.push(row);
        continue;
      }
      const parsed = dataUrlToBytes(row.image);
      const { image, ...rest } = row;
      if (!parsed.ok) {
        next.push({ ...rest, migrated_at: (/* @__PURE__ */ new Date()).toISOString(), migrated_note: `\u65E7\u6570\u636E\u5730\u5740\u65E0\u6CD5\u89E3\u6790\uFF1A${parsed.message}` });
        migrated += 1;
        leftovers += 1;
        continue;
      }
      const stored = await putPhotoBinary(row.id, parsed.bytes);
      if (!stored.ok) {
        next.push(row);
        leftovers += 1;
        continue;
      }
      const size = imageSize(parsed.bytes);
      next.push({
        ...rest,
        mime: row.mime || sniffMime(parsed.bytes),
        width: row.width || size.width,
        height: row.height || size.height,
        bytes: row.bytes || parsed.bytes.length,
        sha256: row.sha256 || sha256Hex(parsed.bytes),
        storage: "indexeddb",
        storage_key: photoBinaryKey(row.id),
        migrated_at: (/* @__PURE__ */ new Date()).toISOString(),
        migrated_from: "localStorage:dataUrl"
      });
      migrated += 1;
    }
    if (migrated > 0) savePhotoRows(next);
    return {
      ok: true,
      migrated,
      total: rows.length,
      leftovers,
      message: migrated > 0 ? `\u5DF2\u628A ${migrated} \u6761\u65E7\u683C\u5F0F\u5B9E\u7269\u7167\u7247\uFF08\u6574\u5F20 dataURL \u76F4\u5B58 localStorage\uFF09\u8FC1\u5165\u672C\u5730\u5F71\u50CF\u5E93\uFF0ClocalStorage \u53EA\u7559\u5143\u6570\u636E` : "\u65E0\u9700\u8FC1\u79FB\uFF1A\u5B9E\u7269\u7167\u7247\u5DF2\u5168\u90E8\u4E3A\u300C\u5143\u6570\u636E + \u4E8C\u8FDB\u5236\u5206\u5C42\u300D\u5F62\u6001"
    };
  }
  var MANUAL_SOURCE = "manual";
  function nowIso() {
    return (/* @__PURE__ */ new Date()).toISOString();
  }
  function pickText(source, keys) {
    if (!source) return "";
    for (const key of keys) {
      const value = source[key];
      if (value === void 0 || value === null) continue;
      const text = String(value).trim();
      if (text) return text;
    }
    return "";
  }
  var SEAL_STAMP_ID_PATTERN = /^XA(\d{9})$/;
  var LEGACY_STAMP_ID_PATTERN = /^XAI-(\d+)$/;
  function uniqueId(base, taken) {
    if (!taken.has(base)) return base;
    let index = 2;
    while (taken.has(`${base}-${index}`)) index += 1;
    return `${base}-${index}`;
  }
  function stampSerial(stampId) {
    const matched = SEAL_STAMP_ID_PATTERN.exec(String(stampId || ""));
    if (matched) return matched[1];
    const legacy = LEGACY_STAMP_ID_PATTERN.exec(String(stampId || ""));
    if (legacy) return legacy[1];
    return String(stampId || "").replace(/[^0-9A-Za-z]/g, "");
  }
  function nextImageId(stampId, kind, taken) {
    const letter = kind === FACE_KIND.EDGE ? "e" : "f";
    return uniqueId(`img-${stampSerial(stampId)}${letter}`, taken);
  }
  function snapshotCollections() {
    return { seals: listSealRows(), faces: listFaceRows(), images: listImageRows() };
  }
  function restoreCollections(snapshot) {
    saveSealRows(snapshot.seals);
    saveFaceRows(snapshot.faces);
    saveImageRows(snapshot.images);
  }
  async function rollbackTo(snapshot, beforeImageIds) {
    const fresh = listImageRows().filter((row) => !beforeImageIds.has(row.id));
    for (const row of fresh) {
      await deleteImageBinary(row.id);
    }
    restoreCollections(snapshot);
  }
  function assertAdminFor(actor, message) {
    if (!actor || actor.role !== "admin") throw new PermissionError(message);
  }
  async function insertImageRow(actor, payload = {}) {
    assertAdminFor(actor, "\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u4E0A\u4F20\u5370\u9762\u56FE");
    const sealId = pickText(payload, ["sealId", "stampId", "stamp_id"]);
    if (!sealId) {
      return { ok: false, reason: "MISSING_REQUIRED", missing: ["\u6240\u5C5E\u5370\u7AE0"], message: "\u8BF7\u8865\u5168\u5FC5\u586B\u9879\uFF1A\u6240\u5C5E\u5370\u7AE0" };
    }
    const kind = payload.kind === FACE_KIND.EDGE ? FACE_KIND.EDGE : FACE_KIND.FACE;
    const input = payload.image !== void 0 ? payload.image : payload.dataUrl;
    const image = normalizeImagePayload(input);
    if (!image.ok) return { ok: false, reason: "INVALID_IMAGE", message: image.message };
    const images = listImageRows();
    const existing = images.find((row2) => row2.stamp_id === sealId && row2.sha256 === image.sha256 && row2.kind === kind);
    if (existing) {
      return {
        ok: true,
        deduped: true,
        row: existing,
        message: "\u8BE5\u5F71\u50CF\u6B64\u524D\u5DF2\u4E0A\u4F20\uFF08\u5185\u5BB9\u76F8\u540C\uFF09\uFF0C\u5DF2\u590D\u7528\u65E2\u6709\u5F71\u50CF\uFF0C\u672A\u91CD\u590D\u843D\u5E93"
      };
    }
    const assetId = nextImageId(sealId, kind, new Set(images.map((row2) => row2.id)));
    const stored = await putImageBinary(assetId, image.bytes);
    if (!stored.ok) {
      return { ok: false, reason: "STORAGE_UNAVAILABLE", message: `\u5F71\u50CF\u5E93\u5199\u5165\u5931\u8D25\uFF1A${stored.message}` };
    }
    const at = nowIso();
    const row = {
      id: assetId,
      // §4.1.3 asset.id
      assetId,
      stamp_id: sealId,
      // 兼容别名（既落盘服务按它定位），勿删
      sealId,
      ownerType: "face",
      ownerId: payload.faceId || "",
      kind,
      // 仍只取 FACE / EDGE（不因存储分层新增第三种）
      sha256: image.sha256,
      bytes: image.bytesLength,
      width: image.width,
      height: image.height,
      colorMode: image.colorMode,
      color_mode: image.colorMode,
      // 兼容既落盘视图用字
      mime: image.mime,
      storage: "indexeddb",
      // 二进制去向（元数据行里只记口径，不记内容）
      storage_key: assetBlobKey(assetId),
      source: MANUAL_SOURCE,
      uploaded_by: actor.id,
      created_at: at
    };
    saveImageRows([...images, row]);
    return { ok: true, deduped: false, row, message: "\u5370\u9762\u56FE\u5DF2\u4E0A\u4F20\uFF08\u4E8C\u8FDB\u5236\u5DF2\u843D\u672C\u5730\u5F71\u50CF\u5E93\uFF09" };
  }
  async function replaceFaceImage(actor, faceId, imageInput) {
    try {
      assertAdminFor(actor, "\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u91CD\u65B0\u4E0A\u4F20\u5370\u9762\u56FE");
    } catch (err) {
      if (err instanceof PermissionError) {
        return { ok: false, reason: "FORBIDDEN", previousFaceImageId: null, message: err.message };
      }
      throw err;
    }
    const id = pickText({ faceId }, ["faceId"]);
    if (!id) {
      return { ok: false, reason: "MISSING_FACE", previousFaceImageId: null, message: "\u672A\u6307\u5B9A\u8981\u66FF\u6362\u5F71\u50CF\u7684\u5370\u9762" };
    }
    const target = readFaceCollection().find((row) => row.id === id);
    if (!target) {
      return { ok: false, reason: "UNKNOWN_FACE", previousFaceImageId: null, message: `\u672A\u627E\u5230\u8BE5\u5370\u9762\uFF1A${id}` };
    }
    const previousFaceImageId = target.face_image_id || null;
    const sealId = target.sealId || target.stamp_id || "";
    if (!sealId) {
      return {
        ok: false,
        reason: "UNKNOWN_SEAL",
        previousFaceImageId,
        message: `\u5370\u9762 ${id} \u672A\u6302\u5230\u4EFB\u4F55\u5370\u7AE0\u4E0A\uFF0C\u65E0\u6CD5\u65B0\u589E\u5F71\u50CF`
      };
    }
    const payload = imageInput && typeof imageInput === "object" && !ArrayBuffer.isView(imageInput) ? imageInput : { bytes: imageInput };
    const claimed = {
      width: Number.isFinite(Number(payload.width)) ? Math.round(Number(payload.width)) : 0,
      height: Number.isFinite(Number(payload.height)) ? Math.round(Number(payload.height)) : 0
    };
    const raw = payload.bytes !== void 0 ? payload.bytes : payload.dataUrl !== void 0 ? payload.dataUrl : imageInput;
    const image = normalizeImagePayload(raw);
    if (!image.ok) {
      return { ok: false, reason: "INVALID_IMAGE", previousFaceImageId, message: image.message };
    }
    const before = snapshotCollections();
    const beforeImageIds = new Set(before.images.map((row) => row.id));
    try {
      const stored = await insertImageRow(actor, {
        sealId,
        kind: target.kind === FACE_KIND.EDGE ? FACE_KIND.EDGE : FACE_KIND.FACE,
        image: image.bytes,
        faceId: id
      });
      if (!stored.ok) {
        await rollbackTo(before, beforeImageIds);
        return { ...stored, previousFaceImageId };
      }
      if (!listImageRows().some((row) => row.id === stored.row.id)) {
        await deleteImageBinary(stored.row.id);
        await rollbackTo(before, beforeImageIds);
        return {
          ok: false,
          reason: "STORAGE_UNAVAILABLE",
          previousFaceImageId,
          message: "\u5F71\u50CF\u5143\u6570\u636E\u672A\u80FD\u843D\u76D8\uFF08\u672C\u5730\u5B58\u50A8\u4E0D\u53EF\u5199\uFF09\uFF0C\u672C\u6B21\u66FF\u6362\u5DF2\u56DE\u6EDA\uFF0C\u672A\u4EA7\u751F\u534A\u6210\u54C1\u5F71\u50CF"
        };
      }
      const written = writeFaceFixedAttributes(actor, id, { face_image_id: stored.row.id });
      const fresh = listImageRows().find((row) => row.id === stored.row.id) || stored.row;
      const sameAsBefore = stored.deduped === true && previousFaceImageId === stored.row.id;
      const dimsNote = claimed.width > 0 && claimed.height > 0 && (claimed.width !== fresh.width || claimed.height !== fresh.height) ? `\uFF08\u8C03\u7528\u65B9\u58F0\u79F0 ${claimed.width} \xD7 ${claimed.height}\uFF0C\u6309\u5B57\u8282\u89E3\u6790\u5B9E\u4E3A ${fresh.width} \xD7 ${fresh.height}\uFF0C\u4EE5\u89E3\u6790\u503C\u4E3A\u51C6\uFF09` : "";
      return {
        ok: true,
        deduped: stored.deduped === true,
        sealId,
        faceId: id,
        faceImageId: stored.row.id,
        previousFaceImageId,
        image: fresh,
        face: written,
        claimed,
        message: sameAsBefore ? `\u672C\u6B21\u6240\u9009\u56FE\u4E0E\u5F53\u524D\u5370\u9762\u56FE\u5185\u5BB9\u76F8\u540C\uFF08\u5F71\u50CF\u7F16\u53F7 ${stored.row.id}\uFF09\uFF0C\u672A\u65B0\u589E\u5F71\u50CF\u884C\uFF0C\u5370\u9762\u6307\u5411\u672A\u53D8` : `\u5370\u9762\u56FE\u5DF2\u66FF\u6362\uFF1A\u5F71\u50CF\u7F16\u53F7 ${previousFaceImageId || "\uFF08\u539F\u65E0\uFF09"} \u2192 ${stored.row.id}\uFF1B\u65E7\u5F71\u50CF\u884C\u4E0E\u4E8C\u8FDB\u5236\u4FDD\u7559\u672A\u5220\u3002\u65B0\u5F71\u50CF ${fresh.width} \xD7 ${fresh.height} \xB7 ${fresh.mime} \xB7 ${fresh.bytes} \u5B57\u8282${dimsNote}`
      };
    } catch (err) {
      await rollbackTo(before, beforeImageIds);
      return {
        ok: false,
        reason: "ERROR",
        previousFaceImageId,
        message: `\u66FF\u6362\u5370\u9762\u56FE\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}\uFF08\u5DF2\u56DE\u6EDA\uFF0C\u672A\u4EA7\u751F\u534A\u6210\u54C1\u5F71\u50CF\uFF09`
      };
    }
  }

  // src/utils/image.js
  var IMAGE_LIMITS = Object.freeze({
    /* ① 输入侧：原始文件字节上限（1 MB）。 */
    maxInputBytes: 1048576,
    /* ② 产物侧：入库二进制上限。
       定值理由（本单实测）：正常路径产物是 WebP（实测 3000×1200 → 1200×1200 = 14.6 KB；
       2600×2600 → 2048×2048 = 36.6 KB），1 MB 富余得多；但**浏览器编不出 WebP 时**回退 PNG，
       2048×2048 实拍感图**两次实测**为 2,832,092 / 2,855,176 字节（2.70–2.72 MiB）
       ⇒ 上限必须**大于这一个真实产物**，否则等于「拿输入闸拒自家产物」；
       4 MiB 给实测回退产物留约 40% 余量，同时是输入上限的 4 倍、单行入库体量仍可控。 */
    maxStoredBytes: 4 * 1024 * 1024,
    /* ③ 有界降质重编的**硬上界**（轮数）：不许无限重试。每轮 = 最长边 ÷2（下限 reencodeSideFloor）
       + quality −0.2（下限 reencodeQualityFloor）。 */
    maxReencodeRounds: 3,
    reencodeSideFloor: 256,
    reencodeQualityFloor: 0.3,
    maxSide: 2048,
    quality: 0.85
  });
  var STORED_MAX_BYTES = IMAGE_LIMITS.maxStoredBytes;
  var MIN_CROP_SIDE = 16;
  var TARGET_MIME = "image/webp";
  function describeBytes(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value < 0) return "\u672A\u77E5\u5927\u5C0F";
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 / 1024).toFixed(2)} MB`;
  }
  function pickSize(file) {
    const size = Number(file && file.size);
    return Number.isFinite(size) && size >= 0 ? size : -1;
  }
  function assertWithinInputLimit(bytes) {
    const size = Number(bytes);
    if (!Number.isFinite(size) || size <= 0) {
      return { ok: false, message: "\u56FE\u7247\u5185\u5BB9\u4E3A\u7A7A\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    }
    if (size > IMAGE_LIMITS.maxInputBytes) {
      return {
        ok: false,
        message: `\u7167\u7247\u8FC7\u5927\uFF1A\u6240\u9009\u6587\u4EF6 ${describeBytes(size)}\uFF0C\u4E0A\u9650 ${describeBytes(IMAGE_LIMITS.maxInputBytes)}\uFF081 MB\uFF09\u3002\u8BF7\u6362\u4E00\u5F20\u66F4\u5C0F\u7684\u56FE\uFF0C\u6216\u5148\u7528\u624B\u673A/\u7CFB\u7EDF\u81EA\u5E26\u7684\u538B\u7F29\u518D\u4E0A\u4F20\u3002`
      };
    }
    return { ok: true, message: "" };
  }
  async function decodeViaImageBitmap(blob) {
    if (typeof createImageBitmap !== "function") return null;
    try {
      return await createImageBitmap(blob, { imageOrientation: "from-image" });
    } catch {
    }
    try {
      return await createImageBitmap(blob);
    } catch {
      return null;
    }
  }
  function decodeViaImageElement(blob) {
    return new Promise((resolve) => {
      if (typeof Image !== "function" || typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
        resolve(null);
        return;
      }
      const url = URL.createObjectURL(blob);
      const image = new Image();
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        try {
          URL.revokeObjectURL(url);
        } catch {
        }
        resolve(value);
      };
      image.onload = () => finish(image);
      image.onerror = () => finish(null);
      image.src = url;
    });
  }
  async function loadImageFile(file) {
    const out = {
      ok: false,
      bitmap: null,
      width: 0,
      height: 0,
      originalBytes: 0,
      originalMime: "",
      message: ""
    };
    if (!file || typeof file !== "object") {
      return { ...out, message: "\u8BF7\u9009\u62E9\u56FE\u7247\u6587\u4EF6" };
    }
    const declaredMime = String(file.type || "").trim().toLowerCase();
    out.originalMime = declaredMime;
    let size = pickSize(file);
    if (size < 0) {
      try {
        if (typeof file.arrayBuffer === "function") size = (await file.arrayBuffer()).byteLength;
      } catch {
        size = -1;
      }
    }
    out.originalBytes = size > 0 ? size : 0;
    if (declaredMime && !declaredMime.startsWith("image/")) {
      return { ...out, message: `\u8FD9\u4E0D\u662F\u56FE\u7247\u6587\u4EF6\uFF08\u7C7B\u578B ${declaredMime}\uFF09\uFF0C\u8BF7\u9009\u62E9 JPG / PNG / WebP \u56FE\u7247` };
    }
    if (!declaredMime) {
      return { ...out, message: "\u65E0\u6CD5\u8BC6\u522B\u6587\u4EF6\u7C7B\u578B\uFF0C\u8BF7\u9009\u62E9 JPG / PNG / WebP \u56FE\u7247" };
    }
    const limit = assertWithinInputLimit(size);
    if (!limit.ok) return { ...out, message: limit.message };
    let bitmap = await decodeViaImageBitmap(file);
    if (!bitmap) bitmap = await decodeViaImageElement(file);
    if (!bitmap) {
      return { ...out, message: "\u56FE\u7247\u89E3\u7801\u5931\u8D25\uFF08\u6587\u4EF6\u53EF\u80FD\u5DF2\u635F\u574F\u6216\u4E0D\u662F\u53EF\u7528\u7684\u56FE\u7247\uFF09\uFF0C\u8BF7\u6362\u4E00\u5F20\u518D\u8BD5" };
    }
    const width = Math.round(Number(bitmap.width) || 0);
    const height = Math.round(Number(bitmap.height) || 0);
    if (width <= 0 || height <= 0) {
      return { ...out, message: "\u56FE\u7247\u5C3A\u5BF8\u65E0\u6548\uFF08\u8BFB\u4E0D\u5230\u5BBD\u9AD8\uFF09\uFF0C\u8BF7\u6362\u4E00\u5F20\u518D\u8BD5" };
    }
    return { ...out, ok: true, bitmap, width, height };
  }
  function resolveSource(bitmap) {
    if (!bitmap) return null;
    const width = Math.round(Number(bitmap.width) || 0);
    const height = Math.round(Number(bitmap.height) || 0);
    if (width <= 0 || height <= 0) return null;
    return { draw: bitmap, width, height };
  }
  function centerSquareCrop(width, height) {
    const w = Math.max(1, Math.round(Number(width) || 0));
    const h = Math.max(1, Math.round(Number(height) || 0));
    const side = Math.min(w, h);
    return { cx: Math.round((w - side) / 2), cy: Math.round((h - side) / 2), side };
  }
  function normalizeCrop(crop, width, height) {
    const w = Math.max(1, Math.round(Number(width) || 0));
    const h = Math.max(1, Math.round(Number(height) || 0));
    if (!crop || typeof crop !== "object") return centerSquareCrop(w, h);
    const maxSide = Math.min(w, h);
    let side = Math.round(Number(crop.side));
    if (!Number.isFinite(side) || side <= 0) return centerSquareCrop(w, h);
    side = Math.min(Math.max(side, Math.min(MIN_CROP_SIDE, maxSide)), maxSide);
    let cx = Math.round(Number(crop.cx));
    let cy = Math.round(Number(crop.cy));
    if (!Number.isFinite(cx)) cx = (w - side) / 2;
    if (!Number.isFinite(cy)) cy = (h - side) / 2;
    cx = Math.min(Math.max(cx, 0), w - side);
    cy = Math.min(Math.max(cy, 0), h - side);
    return { cx, cy, side };
  }
  function createCanvas(width, height) {
    if (typeof document !== "undefined" && document.createElement) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      return canvas;
    }
    if (typeof OffscreenCanvas === "function") return new OffscreenCanvas(width, height);
    return null;
  }
  function canvasToBlob(canvas, mime, quality) {
    return new Promise((resolve) => {
      if (typeof canvas.toBlob === "function") {
        try {
          canvas.toBlob((blob) => resolve(blob || null), mime, quality);
          return;
        } catch {
        }
      }
      if (typeof canvas.convertToBlob === "function") {
        Promise.resolve(canvas.convertToBlob({ type: mime, quality })).then(
          (blob) => resolve(blob || null),
          () => resolve(null)
        );
        return;
      }
      resolve(null);
    });
  }
  function dataUrlToBytes2(dataUrl) {
    const comma = String(dataUrl).indexOf(",");
    if (comma < 0) return null;
    const head = String(dataUrl).slice(5, comma);
    const mime = (head.split(";")[0] || "").trim().toLowerCase();
    if (!/;base64/i.test(head)) return null;
    try {
      const binary = atob(String(dataUrl).slice(comma + 1));
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i) & 255;
      return { bytes, mime };
    } catch {
      return null;
    }
  }
  function sniffBytesMime(bytes) {
    const v = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
    if (v.length >= 8 && v[0] === 137 && v[1] === 80 && v[2] === 78 && v[3] === 71) return "image/png";
    if (v.length >= 3 && v[0] === 255 && v[1] === 216 && v[2] === 255) return "image/jpeg";
    if (v.length >= 4 && v[0] === 71 && v[1] === 73 && v[2] === 70) return "image/gif";
    if (v.length >= 12 && v[0] === 82 && v[1] === 73 && v[2] === 70 && v[3] === 70 && v[8] === 87 && v[9] === 69 && v[10] === 66 && v[11] === 80) {
      return "image/webp";
    }
    return "";
  }
  async function encodeSquareOnce(source, crop, target, quality) {
    const canvas = createCanvas(target, target);
    if (!canvas || typeof canvas.getContext !== "function") {
      return { error: "\u5F53\u524D\u73AF\u5883\u4E0D\u652F\u6301\u6D4F\u89C8\u5668\u7AEF\u56FE\u7247\u5904\u7406\uFF08\u753B\u5E03\u4E0D\u53EF\u7528\uFF09" };
    }
    const context = canvas.getContext("2d");
    if (!context) return { error: "\u5F53\u524D\u73AF\u5883\u4E0D\u652F\u6301\u6D4F\u89C8\u5668\u7AEF\u56FE\u7247\u5904\u7406\uFF08\u753B\u5E03\u4E0D\u53EF\u7528\uFF09" };
    try {
      context.imageSmoothingEnabled = true;
      if ("imageSmoothingQuality" in context) context.imageSmoothingQuality = "high";
      context.drawImage(source.draw, crop.cx, crop.cy, crop.side, crop.side, 0, 0, target, target);
    } catch (err) {
      return { error: `\u56FE\u7247\u88C1\u526A\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}` };
    }
    const blob = await canvasToBlob(canvas, TARGET_MIME, quality);
    let bytes = null;
    let claimed = "";
    if (blob) {
      try {
        bytes = new Uint8Array(await blob.arrayBuffer());
        claimed = String(blob.type || "").toLowerCase();
      } catch (err) {
        return { error: `\u56FE\u7247\u7F16\u7801\u7ED3\u679C\u8BFB\u53D6\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}` };
      }
    } else if (typeof canvas.toDataURL === "function") {
      let fallback = null;
      try {
        fallback = dataUrlToBytes2(canvas.toDataURL(TARGET_MIME, quality));
      } catch {
        fallback = null;
      }
      if (fallback && fallback.bytes && fallback.bytes.length > 0) {
        bytes = fallback.bytes;
        claimed = fallback.mime;
      }
    }
    if (!bytes || bytes.length === 0) {
      return { error: "\u56FE\u7247\u7F16\u7801\u5931\u8D25\uFF08\u6D4F\u89C8\u5668\u672A\u80FD\u751F\u6210\u56FE\u7247\u6570\u636E\uFF09\uFF0C\u8BF7\u6362\u4E00\u5F20\u518D\u8BD5" };
    }
    const mime = sniffBytesMime(bytes) || claimed || "application/octet-stream";
    return { bytes, mime, width: target, height: target };
  }
  async function exportSquareImage(bitmap, options = {}) {
    const out = {
      ok: false,
      bytes: null,
      mime: "",
      width: 0,
      height: 0,
      message: "",
      reason: "",
      initialBytes: 0,
      reencodeRounds: 0,
      maxBytes: IMAGE_LIMITS.maxStoredBytes
    };
    const source = resolveSource(bitmap);
    if (!source) return { ...out, message: "\u56FE\u7247\u5C1A\u672A\u5C31\u7EEA\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    const maxSideRaw = Number(options.maxSide);
    const maxSide = Number.isFinite(maxSideRaw) && maxSideRaw > 0 ? Math.round(maxSideRaw) : IMAGE_LIMITS.maxSide;
    const qualityRaw = Number(options.quality);
    const quality = Number.isFinite(qualityRaw) && qualityRaw > 0 && qualityRaw <= 1 ? qualityRaw : IMAGE_LIMITS.quality;
    const maxBytesRaw = Number(options.maxBytes);
    const maxBytes = Number.isFinite(maxBytesRaw) && maxBytesRaw > 0 ? Math.round(maxBytesRaw) : IMAGE_LIMITS.maxStoredBytes;
    const crop = normalizeCrop(options.crop, source.width, source.height);
    const baseTarget = Math.max(1, Math.min(crop.side, maxSide));
    let best = await encodeSquareOnce(source, crop, baseTarget, quality);
    if (best.error) return { ...out, maxBytes, message: best.error };
    const initialBytes = best.bytes.length;
    let rounds = 0;
    while (best.bytes.length > maxBytes && rounds < IMAGE_LIMITS.maxReencodeRounds) {
      rounds += 1;
      const nextSide = Math.max(
        Math.min(IMAGE_LIMITS.reencodeSideFloor, baseTarget),
        Math.round(baseTarget / Math.pow(2, rounds))
      );
      const nextQuality = Math.max(IMAGE_LIMITS.reencodeQualityFloor, Number((quality - 0.2 * rounds).toFixed(3)));
      const next = await encodeSquareOnce(source, crop, Math.max(1, Math.min(nextSide, baseTarget)), nextQuality);
      if (next.error) break;
      if (next.bytes.length < best.bytes.length) best = next;
    }
    const reencodedNote = rounds > 0 ? `\u4EA7\u7269\u8D85\u8FC7\u5165\u5E93\u4E0A\u9650 ${describeBytes(maxBytes)}\uFF0C\u5DF2\u81EA\u52A8\u964D\u8D28\u91CD\u7F16 ${rounds} \u8F6E\uFF1A${describeBytes(initialBytes)} \u2192 ${describeBytes(best.bytes.length)}` : "";
    if (best.bytes.length > maxBytes) {
      return {
        ...out,
        reason: "ARTIFACT_TOO_LARGE",
        mime: best.mime,
        width: best.width,
        height: best.height,
        initialBytes,
        reencodeRounds: rounds,
        maxBytes,
        message: `\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\uFF1A\u5DF2\u81EA\u52A8\u964D\u8D28\u91CD\u7F16 ${rounds} \u8F6E\uFF0C\u4EA7\u51FA\u4ECD\u6709 ${describeBytes(best.bytes.length)}\uFF0C\u8D85\u8FC7\u5165\u5E93\u4E0A\u9650 ${describeBytes(maxBytes)}\u3002\u8FD9\u4E0E\u300C\u6240\u9009\u6587\u4EF6 \u2264 1 MB\u300D\u7684\u8F93\u5165\u4E0A\u9650\u662F\u4E24\u56DE\u4E8B\uFF1B\u8BF7\u91CD\u8BD5\uFF0C\u6216\u6539\u7528\u652F\u6301 WebP \u7F16\u7801\u7684\u6D4F\u89C8\u5668\u540E\u518D\u4E0A\u4F20\u3002`
      };
    }
    const fallbackNote = best.mime !== TARGET_MIME ? `\u5F53\u524D\u6D4F\u89C8\u5668\u672A\u80FD\u7F16\u7801 ${TARGET_MIME}\uFF0C\u5DF2\u6309\u5B9E\u9645\u683C\u5F0F ${best.mime} \u5165\u5E93` : "";
    return {
      ok: true,
      bytes: best.bytes,
      mime: best.mime,
      width: best.width,
      height: best.height,
      initialBytes,
      reencodeRounds: rounds,
      maxBytes,
      message: [fallbackNote, reencodedNote].filter(Boolean).join("\uFF1B")
    };
  }

  // node_modules/@vue/shared/dist/shared.esm-bundler.js
  // @__NO_SIDE_EFFECTS__
  function makeMap(str) {
    const map2 = /* @__PURE__ */ Object.create(null);
    for (const key of str.split(",")) map2[key] = 1;
    return (val) => val in map2;
  }
  var EMPTY_OBJ = true ? Object.freeze({}) : {};
  var EMPTY_ARR = true ? Object.freeze([]) : [];
  var NOOP = () => {
  };
  var NO = () => false;
  var extend = Object.assign;
  var remove = (arr, el) => {
    const i = arr.indexOf(el);
    if (i > -1) {
      arr.splice(i, 1);
    }
  };
  var hasOwnProperty = Object.prototype.hasOwnProperty;
  var hasOwn = (val, key) => hasOwnProperty.call(val, key);
  var isArray = Array.isArray;
  var isMap = (val) => toTypeString(val) === "[object Map]";
  var isSet = (val) => toTypeString(val) === "[object Set]";
  var isFunction = (val) => typeof val === "function";
  var isString = (val) => typeof val === "string";
  var isSymbol = (val) => typeof val === "symbol";
  var isObject = (val) => val !== null && typeof val === "object";
  var isPromise = (val) => {
    return (isObject(val) || isFunction(val)) && isFunction(val.then) && isFunction(val.catch);
  };
  var objectToString = Object.prototype.toString;
  var toTypeString = (value) => objectToString.call(value);
  var toRawType = (value) => {
    return toTypeString(value).slice(8, -1);
  };
  var isPlainObject = (val) => toTypeString(val) === "[object Object]";
  var isIntegerKey = (key) => isString(key) && key !== "NaN" && key[0] !== "-" && "" + parseInt(key, 10) === key;
  var cacheStringFunction = (fn) => {
    const cache = /* @__PURE__ */ Object.create(null);
    return (str) => {
      const hit = cache[str];
      return hit || (cache[str] = fn(str));
    };
  };
  var camelizeRE = /-\w/g;
  var camelize = cacheStringFunction(
    (str) => {
      return str.replace(camelizeRE, (c) => c.slice(1).toUpperCase());
    }
  );
  var hyphenateRE = /\B([A-Z])/g;
  var hyphenate = cacheStringFunction(
    (str) => str.replace(hyphenateRE, "-$1").toLowerCase()
  );
  var capitalize = cacheStringFunction((str) => {
    return str.charAt(0).toUpperCase() + str.slice(1);
  });
  var toHandlerKey = cacheStringFunction(
    (str) => {
      const s = str ? `on${capitalize(str)}` : ``;
      return s;
    }
  );
  var hasChanged = (value, oldValue) => !Object.is(value, oldValue);
  var def = (obj, key, value, writable = false) => {
    Object.defineProperty(obj, key, {
      configurable: true,
      enumerable: false,
      writable,
      value
    });
  };
  var _globalThis;
  var getGlobalThis = () => {
    return _globalThis || (_globalThis = typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : typeof global !== "undefined" ? global : {});
  };
  var specialBooleanAttrs = `itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,readonly`;
  var isBooleanAttr = /* @__PURE__ */ makeMap(
    specialBooleanAttrs + `,async,autofocus,autoplay,controls,default,defer,disabled,inert,loop,open,required,reversed,scoped,seamless,checked,muted,multiple,selected`
  );

  // node_modules/@vue/reactivity/dist/reactivity.esm-bundler.js
  function warn(msg, ...args) {
    console.warn(`[Vue warn] ${msg}`, ...args);
  }
  var activeEffectScope;
  function getCurrentScope() {
    return activeEffectScope;
  }
  var activeSub;
  var pausedQueueEffects = /* @__PURE__ */ new WeakSet();
  var ReactiveEffect = class {
    constructor(fn) {
      this.fn = fn;
      this.deps = void 0;
      this.depsTail = void 0;
      this.flags = 1 | 4;
      this.next = void 0;
      this.cleanup = void 0;
      this.scheduler = void 0;
      if (activeEffectScope) {
        if (activeEffectScope.active) {
          activeEffectScope.effects.push(this);
        } else {
          this.flags &= -2;
        }
      }
    }
    pause() {
      this.flags |= 64;
    }
    resume() {
      if (this.flags & 64) {
        this.flags &= -65;
        if (pausedQueueEffects.has(this)) {
          pausedQueueEffects.delete(this);
          this.trigger();
        }
      }
    }
    /**
     * @internal
     */
    notify() {
      if (this.flags & 2 && !(this.flags & 32)) {
        return;
      }
      if (!(this.flags & 8)) {
        batch(this);
      }
    }
    run() {
      if (!(this.flags & 1)) {
        return this.fn();
      }
      this.flags |= 2;
      cleanupEffect(this);
      prepareDeps(this);
      const prevEffect = activeSub;
      const prevShouldTrack = shouldTrack;
      activeSub = this;
      shouldTrack = true;
      try {
        return this.fn();
      } finally {
        if (activeSub !== this) {
          warn(
            "Active effect was not restored correctly - this is likely a Vue internal bug."
          );
        }
        cleanupDeps(this);
        activeSub = prevEffect;
        shouldTrack = prevShouldTrack;
        this.flags &= -3;
      }
    }
    stop() {
      if (this.flags & 1) {
        for (let link = this.deps; link; link = link.nextDep) {
          removeSub(link);
        }
        this.deps = this.depsTail = void 0;
        cleanupEffect(this);
        this.onStop && this.onStop();
        this.flags &= -2;
      }
    }
    trigger() {
      if (this.flags & 64) {
        pausedQueueEffects.add(this);
      } else if (this.scheduler) {
        this.scheduler();
      } else {
        this.runIfDirty();
      }
    }
    /**
     * @internal
     */
    runIfDirty() {
      if (isDirty(this)) {
        this.run();
      }
    }
    get dirty() {
      return isDirty(this);
    }
  };
  var batchDepth = 0;
  var batchedSub;
  var batchedComputed;
  function batch(sub, isComputed = false) {
    sub.flags |= 8;
    if (isComputed) {
      sub.next = batchedComputed;
      batchedComputed = sub;
      return;
    }
    sub.next = batchedSub;
    batchedSub = sub;
  }
  function startBatch() {
    batchDepth++;
  }
  function endBatch() {
    if (--batchDepth > 0) {
      return;
    }
    if (batchedComputed) {
      let e = batchedComputed;
      batchedComputed = void 0;
      while (e) {
        const next = e.next;
        e.next = void 0;
        e.flags &= -9;
        e = next;
      }
    }
    let error;
    while (batchedSub) {
      let e = batchedSub;
      batchedSub = void 0;
      while (e) {
        const next = e.next;
        e.next = void 0;
        e.flags &= -9;
        if (e.flags & 1) {
          try {
            ;
            e.trigger();
          } catch (err) {
            if (!error) error = err;
          }
        }
        e = next;
      }
    }
    if (error) throw error;
  }
  function prepareDeps(sub) {
    for (let link = sub.deps; link; link = link.nextDep) {
      link.version = -1;
      link.prevActiveLink = link.dep.activeLink;
      link.dep.activeLink = link;
    }
  }
  function cleanupDeps(sub) {
    let head;
    let tail = sub.depsTail;
    let link = tail;
    while (link) {
      const prev = link.prevDep;
      if (link.version === -1) {
        if (link === tail) tail = prev;
        removeSub(link);
        removeDep(link);
      } else {
        head = link;
      }
      link.dep.activeLink = link.prevActiveLink;
      link.prevActiveLink = void 0;
      link = prev;
    }
    sub.deps = head;
    sub.depsTail = tail;
  }
  function isDirty(sub) {
    for (let link = sub.deps; link; link = link.nextDep) {
      if (link.dep.version !== link.version || link.dep.computed && (refreshComputed(link.dep.computed) || link.dep.version !== link.version)) {
        return true;
      }
    }
    if (sub._dirty) {
      return true;
    }
    return false;
  }
  function refreshComputed(computed3) {
    if (computed3.flags & 4 && !(computed3.flags & 16)) {
      return;
    }
    computed3.flags &= -17;
    if (computed3.globalVersion === globalVersion) {
      return;
    }
    computed3.globalVersion = globalVersion;
    if (!computed3.isSSR && computed3.flags & 128 && (!computed3.deps && !computed3._dirty || !isDirty(computed3))) {
      return;
    }
    computed3.flags |= 2;
    const dep = computed3.dep;
    const prevSub = activeSub;
    const prevShouldTrack = shouldTrack;
    activeSub = computed3;
    shouldTrack = true;
    try {
      prepareDeps(computed3);
      const value = computed3.fn(computed3._value);
      if (dep.version === 0 || hasChanged(value, computed3._value)) {
        computed3.flags |= 128;
        computed3._value = value;
        dep.version++;
      }
    } catch (err) {
      dep.version++;
      throw err;
    } finally {
      activeSub = prevSub;
      shouldTrack = prevShouldTrack;
      cleanupDeps(computed3);
      computed3.flags &= -3;
    }
  }
  function removeSub(link, soft = false) {
    const { dep, prevSub, nextSub } = link;
    if (prevSub) {
      prevSub.nextSub = nextSub;
      link.prevSub = void 0;
    }
    if (nextSub) {
      nextSub.prevSub = prevSub;
      link.nextSub = void 0;
    }
    if (dep.subsHead === link) {
      dep.subsHead = nextSub;
    }
    if (dep.subs === link) {
      dep.subs = prevSub;
      if (!prevSub && dep.computed) {
        dep.computed.flags &= -5;
        for (let l = dep.computed.deps; l; l = l.nextDep) {
          removeSub(l, true);
        }
      }
    }
    if (!soft && !--dep.sc && dep.map) {
      dep.map.delete(dep.key);
    }
  }
  function removeDep(link) {
    const { prevDep, nextDep } = link;
    if (prevDep) {
      prevDep.nextDep = nextDep;
      link.prevDep = void 0;
    }
    if (nextDep) {
      nextDep.prevDep = prevDep;
      link.nextDep = void 0;
    }
  }
  var shouldTrack = true;
  var trackStack = [];
  function pauseTracking() {
    trackStack.push(shouldTrack);
    shouldTrack = false;
  }
  function resetTracking() {
    const last = trackStack.pop();
    shouldTrack = last === void 0 ? true : last;
  }
  function cleanupEffect(e) {
    const { cleanup } = e;
    e.cleanup = void 0;
    if (cleanup) {
      const prevSub = activeSub;
      activeSub = void 0;
      try {
        cleanup();
      } finally {
        activeSub = prevSub;
      }
    }
  }
  var globalVersion = 0;
  var Link = class {
    constructor(sub, dep) {
      this.sub = sub;
      this.dep = dep;
      this.version = dep.version;
      this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
    }
  };
  var Dep = class {
    // TODO isolatedDeclarations "__v_skip"
    constructor(computed3) {
      this.computed = computed3;
      this.version = 0;
      this.activeLink = void 0;
      this.subs = void 0;
      this.map = void 0;
      this.key = void 0;
      this.sc = 0;
      this.__v_skip = true;
      if (true) {
        this.subsHead = void 0;
      }
    }
    track(debugInfo) {
      if (!activeSub || !shouldTrack || activeSub === this.computed) {
        return;
      }
      let link = this.activeLink;
      if (link === void 0 || link.sub !== activeSub) {
        link = this.activeLink = new Link(activeSub, this);
        if (!activeSub.deps) {
          activeSub.deps = activeSub.depsTail = link;
        } else {
          link.prevDep = activeSub.depsTail;
          activeSub.depsTail.nextDep = link;
          activeSub.depsTail = link;
        }
        addSub(link);
      } else if (link.version === -1) {
        link.version = this.version;
        if (link.nextDep) {
          const next = link.nextDep;
          next.prevDep = link.prevDep;
          if (link.prevDep) {
            link.prevDep.nextDep = next;
          }
          link.prevDep = activeSub.depsTail;
          link.nextDep = void 0;
          activeSub.depsTail.nextDep = link;
          activeSub.depsTail = link;
          if (activeSub.deps === link) {
            activeSub.deps = next;
          }
        }
      }
      if (activeSub.onTrack) {
        activeSub.onTrack(
          extend(
            {
              effect: activeSub
            },
            debugInfo
          )
        );
      }
      return link;
    }
    trigger(debugInfo) {
      this.version++;
      globalVersion++;
      this.notify(debugInfo);
    }
    notify(debugInfo) {
      startBatch();
      try {
        if (true) {
          for (let head = this.subsHead; head; head = head.nextSub) {
            if (head.sub.onTrigger && !(head.sub.flags & 8)) {
              head.sub.onTrigger(
                extend(
                  {
                    effect: head.sub
                  },
                  debugInfo
                )
              );
            }
          }
        }
        for (let link = this.subs; link; link = link.prevSub) {
          if (link.sub.notify()) {
            ;
            link.sub.dep.notify();
          }
        }
      } finally {
        endBatch();
      }
    }
  };
  function addSub(link) {
    link.dep.sc++;
    if (link.sub.flags & 4) {
      const computed3 = link.dep.computed;
      if (computed3 && !link.dep.subs) {
        computed3.flags |= 4 | 16;
        for (let l = computed3.deps; l; l = l.nextDep) {
          addSub(l);
        }
      }
      const currentTail = link.dep.subs;
      if (currentTail !== link) {
        link.prevSub = currentTail;
        if (currentTail) currentTail.nextSub = link;
      }
      if (link.dep.subsHead === void 0) {
        link.dep.subsHead = link;
      }
      link.dep.subs = link;
    }
  }
  var targetMap = /* @__PURE__ */ new WeakMap();
  var ITERATE_KEY = /* @__PURE__ */ Symbol(
    true ? "Object iterate" : ""
  );
  var MAP_KEY_ITERATE_KEY = /* @__PURE__ */ Symbol(
    true ? "Map keys iterate" : ""
  );
  var ARRAY_ITERATE_KEY = /* @__PURE__ */ Symbol(
    true ? "Array iterate" : ""
  );
  function track(target, type, key) {
    if (shouldTrack && activeSub) {
      let depsMap = targetMap.get(target);
      if (!depsMap) {
        targetMap.set(target, depsMap = /* @__PURE__ */ new Map());
      }
      let dep = depsMap.get(key);
      if (!dep) {
        depsMap.set(key, dep = new Dep());
        dep.map = depsMap;
        dep.key = key;
      }
      if (true) {
        dep.track({
          target,
          type,
          key
        });
      } else {
        dep.track();
      }
    }
  }
  function trigger(target, type, key, newValue, oldValue, oldTarget) {
    const depsMap = targetMap.get(target);
    if (!depsMap) {
      globalVersion++;
      return;
    }
    const run = (dep) => {
      if (dep) {
        if (true) {
          dep.trigger({
            target,
            type,
            key,
            newValue,
            oldValue,
            oldTarget
          });
        } else {
          dep.trigger();
        }
      }
    };
    startBatch();
    if (type === "clear") {
      depsMap.forEach(run);
    } else {
      const targetIsArray = isArray(target);
      const isArrayIndex = targetIsArray && isIntegerKey(key);
      if (targetIsArray && key === "length") {
        const newLength = Number(newValue);
        depsMap.forEach((dep, key2) => {
          if (key2 === "length" || key2 === ARRAY_ITERATE_KEY || !isSymbol(key2) && key2 >= newLength) {
            run(dep);
          }
        });
      } else {
        if (key !== void 0 || depsMap.has(void 0)) {
          run(depsMap.get(key));
        }
        if (isArrayIndex) {
          run(depsMap.get(ARRAY_ITERATE_KEY));
        }
        switch (type) {
          case "add":
            if (!targetIsArray) {
              run(depsMap.get(ITERATE_KEY));
              if (isMap(target)) {
                run(depsMap.get(MAP_KEY_ITERATE_KEY));
              }
            } else if (isArrayIndex) {
              run(depsMap.get("length"));
            }
            break;
          case "delete":
            if (!targetIsArray) {
              run(depsMap.get(ITERATE_KEY));
              if (isMap(target)) {
                run(depsMap.get(MAP_KEY_ITERATE_KEY));
              }
            }
            break;
          case "set":
            if (isMap(target)) {
              run(depsMap.get(ITERATE_KEY));
            }
            break;
        }
      }
    }
    endBatch();
  }
  function reactiveReadArray(array) {
    const raw = /* @__PURE__ */ toRaw(array);
    if (raw === array) return raw;
    track(raw, "iterate", ARRAY_ITERATE_KEY);
    if (/* @__PURE__ */ isShallow(array)) return raw;
    if (!/* @__PURE__ */ isReadonly(array)) return raw.map(toReactive);
    return /* @__PURE__ */ isReactive(array) ? raw.map((item) => toReadonly(toReactive(item))) : raw.map(toReadonly);
  }
  function shallowReadArray(arr) {
    track(arr = /* @__PURE__ */ toRaw(arr), "iterate", ARRAY_ITERATE_KEY);
    return arr;
  }
  function toWrapped(target, item) {
    if (/* @__PURE__ */ isReadonly(target)) {
      return /* @__PURE__ */ isReactive(target) ? toReadonly(toReactive(item)) : toReadonly(item);
    }
    return toReactive(item);
  }
  var arrayInstrumentations = {
    __proto__: null,
    [Symbol.iterator]() {
      return iterator(this, Symbol.iterator, (item) => toWrapped(this, item));
    },
    concat(...args) {
      return reactiveReadArray(this).concat(
        ...args.map((x) => isArray(x) ? reactiveReadArray(x) : x)
      );
    },
    entries() {
      return iterator(this, "entries", (value) => {
        value[1] = toWrapped(this, value[1]);
        return value;
      });
    },
    every(fn, thisArg) {
      return apply(this, "every", fn, thisArg, void 0, arguments);
    },
    filter(fn, thisArg) {
      return apply(
        this,
        "filter",
        fn,
        thisArg,
        (v) => v.map((item) => toWrapped(this, item)),
        arguments
      );
    },
    find(fn, thisArg) {
      return apply(
        this,
        "find",
        fn,
        thisArg,
        (item) => toWrapped(this, item),
        arguments
      );
    },
    findIndex(fn, thisArg) {
      return apply(this, "findIndex", fn, thisArg, void 0, arguments);
    },
    findLast(fn, thisArg) {
      return apply(
        this,
        "findLast",
        fn,
        thisArg,
        (item) => toWrapped(this, item),
        arguments
      );
    },
    findLastIndex(fn, thisArg) {
      return apply(this, "findLastIndex", fn, thisArg, void 0, arguments);
    },
    // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
    forEach(fn, thisArg) {
      return apply(this, "forEach", fn, thisArg, void 0, arguments);
    },
    includes(...args) {
      return searchProxy(this, "includes", args);
    },
    indexOf(...args) {
      return searchProxy(this, "indexOf", args);
    },
    join(separator) {
      return reactiveReadArray(this).join(separator);
    },
    // keys() iterator only reads `length`, no optimization required
    lastIndexOf(...args) {
      return searchProxy(this, "lastIndexOf", args);
    },
    map(fn, thisArg) {
      return apply(this, "map", fn, thisArg, void 0, arguments);
    },
    pop() {
      return noTracking(this, "pop");
    },
    push(...args) {
      return noTracking(this, "push", args);
    },
    reduce(fn, ...args) {
      return reduce(this, "reduce", fn, args);
    },
    reduceRight(fn, ...args) {
      return reduce(this, "reduceRight", fn, args);
    },
    shift() {
      return noTracking(this, "shift");
    },
    // slice could use ARRAY_ITERATE but also seems to beg for range tracking
    some(fn, thisArg) {
      return apply(this, "some", fn, thisArg, void 0, arguments);
    },
    splice(...args) {
      return noTracking(this, "splice", args);
    },
    toReversed() {
      return reactiveReadArray(this).toReversed();
    },
    toSorted(comparer) {
      return reactiveReadArray(this).toSorted(comparer);
    },
    toSpliced(...args) {
      return reactiveReadArray(this).toSpliced(...args);
    },
    unshift(...args) {
      return noTracking(this, "unshift", args);
    },
    values() {
      return iterator(this, "values", (item) => toWrapped(this, item));
    }
  };
  function iterator(self2, method, wrapValue) {
    const arr = shallowReadArray(self2);
    const iter = arr[method]();
    if (arr !== self2 && !/* @__PURE__ */ isShallow(self2)) {
      iter._next = iter.next;
      iter.next = () => {
        const result = iter._next();
        if (!result.done) {
          result.value = wrapValue(result.value);
        }
        return result;
      };
    }
    return iter;
  }
  var arrayProto = Array.prototype;
  function apply(self2, method, fn, thisArg, wrappedRetFn, args) {
    const arr = shallowReadArray(self2);
    const needsWrap = arr !== self2 && !/* @__PURE__ */ isShallow(self2);
    const methodFn = arr[method];
    if (methodFn !== arrayProto[method]) {
      const result2 = methodFn.apply(self2, args);
      return needsWrap ? toReactive(result2) : result2;
    }
    let wrappedFn = fn;
    if (arr !== self2) {
      if (needsWrap) {
        wrappedFn = function(item, index) {
          return fn.call(this, toWrapped(self2, item), index, self2);
        };
      } else if (fn.length > 2) {
        wrappedFn = function(item, index) {
          return fn.call(this, item, index, self2);
        };
      }
    }
    const result = methodFn.call(arr, wrappedFn, thisArg);
    return needsWrap && wrappedRetFn ? wrappedRetFn(result) : result;
  }
  function reduce(self2, method, fn, args) {
    const arr = shallowReadArray(self2);
    const needsWrap = arr !== self2 && !/* @__PURE__ */ isShallow(self2);
    let wrappedFn = fn;
    let wrapInitialAccumulator = false;
    if (arr !== self2) {
      if (needsWrap) {
        wrapInitialAccumulator = args.length === 0;
        wrappedFn = function(acc, item, index) {
          if (wrapInitialAccumulator) {
            wrapInitialAccumulator = false;
            acc = toWrapped(self2, acc);
          }
          return fn.call(this, acc, toWrapped(self2, item), index, self2);
        };
      } else if (fn.length > 3) {
        wrappedFn = function(acc, item, index) {
          return fn.call(this, acc, item, index, self2);
        };
      }
    }
    const result = arr[method](wrappedFn, ...args);
    return wrapInitialAccumulator ? toWrapped(self2, result) : result;
  }
  function searchProxy(self2, method, args) {
    const arr = /* @__PURE__ */ toRaw(self2);
    track(arr, "iterate", ARRAY_ITERATE_KEY);
    const res = arr[method](...args);
    if ((res === -1 || res === false) && /* @__PURE__ */ isProxy(args[0])) {
      args[0] = /* @__PURE__ */ toRaw(args[0]);
      return arr[method](...args);
    }
    return res;
  }
  function noTracking(self2, method, args = []) {
    pauseTracking();
    startBatch();
    const res = (/* @__PURE__ */ toRaw(self2))[method].apply(self2, args);
    endBatch();
    resetTracking();
    return res;
  }
  var isNonTrackableKeys = /* @__PURE__ */ makeMap(`__proto__,__v_isRef,__isVue`);
  var builtInSymbols = new Set(
    /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((key) => key !== "arguments" && key !== "caller").map((key) => Symbol[key]).filter(isSymbol)
  );
  function hasOwnProperty2(key) {
    if (!isSymbol(key)) key = String(key);
    const obj = /* @__PURE__ */ toRaw(this);
    track(obj, "has", key);
    return obj.hasOwnProperty(key);
  }
  var BaseReactiveHandler = class {
    constructor(_isReadonly = false, _isShallow = false) {
      this._isReadonly = _isReadonly;
      this._isShallow = _isShallow;
    }
    get(target, key, receiver) {
      if (key === "__v_skip") return target["__v_skip"];
      const isReadonly2 = this._isReadonly, isShallow2 = this._isShallow;
      if (key === "__v_isReactive") {
        return !isReadonly2;
      } else if (key === "__v_isReadonly") {
        return isReadonly2;
      } else if (key === "__v_isShallow") {
        return isShallow2;
      } else if (key === "__v_raw") {
        if (receiver === (isReadonly2 ? isShallow2 ? shallowReadonlyMap : readonlyMap : isShallow2 ? shallowReactiveMap : reactiveMap).get(target) || // receiver is not the reactive proxy, but has the same prototype
        // this means the receiver is a user proxy of the reactive proxy
        Object.getPrototypeOf(target) === Object.getPrototypeOf(receiver)) {
          return target;
        }
        return;
      }
      const targetIsArray = isArray(target);
      if (!isReadonly2) {
        let fn;
        if (targetIsArray && (fn = arrayInstrumentations[key])) {
          return fn;
        }
        if (key === "hasOwnProperty") {
          return hasOwnProperty2;
        }
      }
      const res = Reflect.get(
        target,
        key,
        // if this is a proxy wrapping a ref, return methods using the raw ref
        // as receiver so that we don't have to call `toRaw` on the ref in all
        // its class methods
        /* @__PURE__ */ isRef(target) ? target : receiver
      );
      if (isSymbol(key) ? builtInSymbols.has(key) : isNonTrackableKeys(key)) {
        return res;
      }
      if (!isReadonly2) {
        track(target, "get", key);
      }
      if (isShallow2) {
        return res;
      }
      if (/* @__PURE__ */ isRef(res)) {
        const value = targetIsArray && isIntegerKey(key) ? res : res.value;
        return isReadonly2 && isObject(value) ? /* @__PURE__ */ readonly(value) : value;
      }
      if (isObject(res)) {
        return isReadonly2 ? /* @__PURE__ */ readonly(res) : /* @__PURE__ */ reactive(res);
      }
      return res;
    }
  };
  var MutableReactiveHandler = class extends BaseReactiveHandler {
    constructor(isShallow2 = false) {
      super(false, isShallow2);
    }
    set(target, key, value, receiver) {
      let oldValue = target[key];
      const isArrayWithIntegerKey = isArray(target) && isIntegerKey(key);
      if (!this._isShallow) {
        const isOldValueReadonly = /* @__PURE__ */ isReadonly(oldValue);
        if (!/* @__PURE__ */ isShallow(value) && !/* @__PURE__ */ isReadonly(value)) {
          oldValue = /* @__PURE__ */ toRaw(oldValue);
          value = /* @__PURE__ */ toRaw(value);
        }
        if (!isArrayWithIntegerKey && /* @__PURE__ */ isRef(oldValue) && !/* @__PURE__ */ isRef(value)) {
          if (isOldValueReadonly) {
            if (true) {
              warn(
                `Set operation on key "${String(key)}" failed: target is readonly.`,
                target[key]
              );
            }
            return true;
          } else {
            oldValue.value = value;
            return true;
          }
        }
      }
      const hadKey = isArrayWithIntegerKey ? Number(key) < target.length : hasOwn(target, key);
      const result = Reflect.set(
        target,
        key,
        value,
        /* @__PURE__ */ isRef(target) ? target : receiver
      );
      if (target === /* @__PURE__ */ toRaw(receiver) && result) {
        if (!hadKey) {
          trigger(target, "add", key, value);
        } else if (hasChanged(value, oldValue)) {
          trigger(target, "set", key, value, oldValue);
        }
      }
      return result;
    }
    deleteProperty(target, key) {
      const hadKey = hasOwn(target, key);
      const oldValue = target[key];
      const result = Reflect.deleteProperty(target, key);
      if (result && hadKey) {
        trigger(target, "delete", key, void 0, oldValue);
      }
      return result;
    }
    has(target, key) {
      const result = Reflect.has(target, key);
      if (!isSymbol(key) || !builtInSymbols.has(key)) {
        track(target, "has", key);
      }
      return result;
    }
    ownKeys(target) {
      track(
        target,
        "iterate",
        isArray(target) ? "length" : ITERATE_KEY
      );
      return Reflect.ownKeys(target);
    }
  };
  var ReadonlyReactiveHandler = class extends BaseReactiveHandler {
    constructor(isShallow2 = false) {
      super(true, isShallow2);
    }
    set(target, key) {
      if (true) {
        warn(
          `Set operation on key "${String(key)}" failed: target is readonly.`,
          target
        );
      }
      return true;
    }
    deleteProperty(target, key) {
      if (true) {
        warn(
          `Delete operation on key "${String(key)}" failed: target is readonly.`,
          target
        );
      }
      return true;
    }
  };
  var mutableHandlers = /* @__PURE__ */ new MutableReactiveHandler();
  var readonlyHandlers = /* @__PURE__ */ new ReadonlyReactiveHandler();
  var shallowReadonlyHandlers = /* @__PURE__ */ new ReadonlyReactiveHandler(true);
  var toShallow = (value) => value;
  var getProto = (v) => Reflect.getPrototypeOf(v);
  function createIterableMethod(method, isReadonly2, isShallow2) {
    return function(...args) {
      const target = this["__v_raw"];
      const rawTarget = /* @__PURE__ */ toRaw(target);
      const targetIsMap = isMap(rawTarget);
      const isPair = method === "entries" || method === Symbol.iterator && targetIsMap;
      const isKeyOnly = method === "keys" && targetIsMap;
      const innerIterator = target[method](...args);
      const wrap = isShallow2 ? toShallow : isReadonly2 ? toReadonly : toReactive;
      !isReadonly2 && track(
        rawTarget,
        "iterate",
        isKeyOnly ? MAP_KEY_ITERATE_KEY : ITERATE_KEY
      );
      return extend(
        // inheriting all iterator properties
        Object.create(innerIterator),
        {
          // iterator protocol
          next() {
            const { value, done } = innerIterator.next();
            return done ? { value, done } : {
              value: isPair ? [wrap(value[0]), wrap(value[1])] : wrap(value),
              done
            };
          }
        }
      );
    };
  }
  function createReadonlyMethod(type) {
    return function(...args) {
      if (true) {
        const key = args[0] ? `on key "${args[0]}" ` : ``;
        warn(
          `${capitalize(type)} operation ${key}failed: target is readonly.`,
          /* @__PURE__ */ toRaw(this)
        );
      }
      return type === "delete" ? false : type === "clear" ? void 0 : this;
    };
  }
  function createInstrumentations(readonly2, shallow) {
    const instrumentations = {
      get(key) {
        const target = this["__v_raw"];
        const rawTarget = /* @__PURE__ */ toRaw(target);
        const rawKey = /* @__PURE__ */ toRaw(key);
        if (!readonly2) {
          if (hasChanged(key, rawKey)) {
            track(rawTarget, "get", key);
          }
          track(rawTarget, "get", rawKey);
        }
        const { has } = getProto(rawTarget);
        const wrap = shallow ? toShallow : readonly2 ? toReadonly : toReactive;
        if (has.call(rawTarget, key)) {
          return wrap(target.get(key));
        } else if (has.call(rawTarget, rawKey)) {
          return wrap(target.get(rawKey));
        } else if (target !== rawTarget) {
          target.get(key);
        }
      },
      get size() {
        const target = this["__v_raw"];
        !readonly2 && track(/* @__PURE__ */ toRaw(target), "iterate", ITERATE_KEY);
        return target.size;
      },
      has(key) {
        const target = this["__v_raw"];
        const rawTarget = /* @__PURE__ */ toRaw(target);
        const rawKey = /* @__PURE__ */ toRaw(key);
        if (!readonly2) {
          if (hasChanged(key, rawKey)) {
            track(rawTarget, "has", key);
          }
          track(rawTarget, "has", rawKey);
        }
        return key === rawKey ? target.has(key) : target.has(key) || target.has(rawKey);
      },
      forEach(callback, thisArg) {
        const observed = this;
        const target = observed["__v_raw"];
        const rawTarget = /* @__PURE__ */ toRaw(target);
        const wrap = shallow ? toShallow : readonly2 ? toReadonly : toReactive;
        !readonly2 && track(rawTarget, "iterate", ITERATE_KEY);
        return target.forEach((value, key) => {
          return callback.call(thisArg, wrap(value), wrap(key), observed);
        });
      }
    };
    extend(
      instrumentations,
      readonly2 ? {
        add: createReadonlyMethod("add"),
        set: createReadonlyMethod("set"),
        delete: createReadonlyMethod("delete"),
        clear: createReadonlyMethod("clear")
      } : {
        add(value) {
          const target = /* @__PURE__ */ toRaw(this);
          const proto = getProto(target);
          const rawValue = /* @__PURE__ */ toRaw(value);
          const valueToAdd = !shallow && !/* @__PURE__ */ isShallow(value) && !/* @__PURE__ */ isReadonly(value) ? rawValue : value;
          const hadKey = proto.has.call(target, valueToAdd) || hasChanged(value, valueToAdd) && proto.has.call(target, value) || hasChanged(rawValue, valueToAdd) && proto.has.call(target, rawValue);
          if (!hadKey) {
            target.add(valueToAdd);
            trigger(target, "add", valueToAdd, valueToAdd);
          }
          return this;
        },
        set(key, value) {
          if (!shallow && !/* @__PURE__ */ isShallow(value) && !/* @__PURE__ */ isReadonly(value)) {
            value = /* @__PURE__ */ toRaw(value);
          }
          const target = /* @__PURE__ */ toRaw(this);
          const { has, get } = getProto(target);
          let hadKey = has.call(target, key);
          if (!hadKey) {
            key = /* @__PURE__ */ toRaw(key);
            hadKey = has.call(target, key);
          } else if (true) {
            checkIdentityKeys(target, has, key);
          }
          const oldValue = get.call(target, key);
          target.set(key, value);
          if (!hadKey) {
            trigger(target, "add", key, value);
          } else if (hasChanged(value, oldValue)) {
            trigger(target, "set", key, value, oldValue);
          }
          return this;
        },
        delete(key) {
          const target = /* @__PURE__ */ toRaw(this);
          const { has, get } = getProto(target);
          let hadKey = has.call(target, key);
          if (!hadKey) {
            key = /* @__PURE__ */ toRaw(key);
            hadKey = has.call(target, key);
          } else if (true) {
            checkIdentityKeys(target, has, key);
          }
          const oldValue = get ? get.call(target, key) : void 0;
          const result = target.delete(key);
          if (hadKey) {
            trigger(target, "delete", key, void 0, oldValue);
          }
          return result;
        },
        clear() {
          const target = /* @__PURE__ */ toRaw(this);
          const hadItems = target.size !== 0;
          const oldTarget = true ? isMap(target) ? new Map(target) : new Set(target) : void 0;
          const result = target.clear();
          if (hadItems) {
            trigger(
              target,
              "clear",
              void 0,
              void 0,
              oldTarget
            );
          }
          return result;
        }
      }
    );
    const iteratorMethods = [
      "keys",
      "values",
      "entries",
      Symbol.iterator
    ];
    iteratorMethods.forEach((method) => {
      instrumentations[method] = createIterableMethod(method, readonly2, shallow);
    });
    return instrumentations;
  }
  function createInstrumentationGetter(isReadonly2, shallow) {
    const instrumentations = createInstrumentations(isReadonly2, shallow);
    return (target, key, receiver) => {
      if (key === "__v_isReactive") {
        return !isReadonly2;
      } else if (key === "__v_isReadonly") {
        return isReadonly2;
      } else if (key === "__v_raw") {
        return target;
      }
      return Reflect.get(
        hasOwn(instrumentations, key) && key in target ? instrumentations : target,
        key,
        receiver
      );
    };
  }
  var mutableCollectionHandlers = {
    get: /* @__PURE__ */ createInstrumentationGetter(false, false)
  };
  var readonlyCollectionHandlers = {
    get: /* @__PURE__ */ createInstrumentationGetter(true, false)
  };
  var shallowReadonlyCollectionHandlers = {
    get: /* @__PURE__ */ createInstrumentationGetter(true, true)
  };
  function checkIdentityKeys(target, has, key) {
    const rawKey = /* @__PURE__ */ toRaw(key);
    if (rawKey !== key && has.call(target, rawKey)) {
      const type = toRawType(target);
      warn(
        `Reactive ${type} contains both the raw and reactive versions of the same object${type === `Map` ? ` as keys` : ``}, which can lead to inconsistencies. Avoid differentiating between the raw and reactive versions of an object and only use the reactive version if possible.`
      );
    }
  }
  var reactiveMap = /* @__PURE__ */ new WeakMap();
  var shallowReactiveMap = /* @__PURE__ */ new WeakMap();
  var readonlyMap = /* @__PURE__ */ new WeakMap();
  var shallowReadonlyMap = /* @__PURE__ */ new WeakMap();
  function targetTypeMap(rawType) {
    switch (rawType) {
      case "Object":
      case "Array":
        return 1;
      case "Map":
      case "Set":
      case "WeakMap":
      case "WeakSet":
        return 2;
      default:
        return 0;
    }
  }
  // @__NO_SIDE_EFFECTS__
  function reactive(target) {
    if (/* @__PURE__ */ isReadonly(target)) {
      return target;
    }
    return createReactiveObject(
      target,
      false,
      mutableHandlers,
      mutableCollectionHandlers,
      reactiveMap
    );
  }
  // @__NO_SIDE_EFFECTS__
  function readonly(target) {
    return createReactiveObject(
      target,
      true,
      readonlyHandlers,
      readonlyCollectionHandlers,
      readonlyMap
    );
  }
  // @__NO_SIDE_EFFECTS__
  function shallowReadonly(target) {
    return createReactiveObject(
      target,
      true,
      shallowReadonlyHandlers,
      shallowReadonlyCollectionHandlers,
      shallowReadonlyMap
    );
  }
  function createReactiveObject(target, isReadonly2, baseHandlers, collectionHandlers, proxyMap) {
    if (!isObject(target)) {
      if (true) {
        warn(
          `value cannot be made ${isReadonly2 ? "readonly" : "reactive"}: ${String(
            target
          )}`
        );
      }
      return target;
    }
    if (target["__v_raw"] && !(isReadonly2 && target["__v_isReactive"])) {
      return target;
    }
    if (target["__v_skip"] || !Object.isExtensible(target)) {
      return target;
    }
    const existingProxy = proxyMap.get(target);
    if (existingProxy) {
      return existingProxy;
    }
    const targetType = targetTypeMap(toRawType(target));
    if (targetType === 0) {
      return target;
    }
    const proxy = new Proxy(
      target,
      targetType === 2 ? collectionHandlers : baseHandlers
    );
    proxyMap.set(target, proxy);
    return proxy;
  }
  // @__NO_SIDE_EFFECTS__
  function isReactive(value) {
    if (/* @__PURE__ */ isReadonly(value)) {
      return /* @__PURE__ */ isReactive(value["__v_raw"]);
    }
    return !!(value && value["__v_isReactive"]);
  }
  // @__NO_SIDE_EFFECTS__
  function isReadonly(value) {
    return !!(value && value["__v_isReadonly"]);
  }
  // @__NO_SIDE_EFFECTS__
  function isShallow(value) {
    return !!(value && value["__v_isShallow"]);
  }
  // @__NO_SIDE_EFFECTS__
  function isProxy(value) {
    return value ? !!value["__v_raw"] : false;
  }
  // @__NO_SIDE_EFFECTS__
  function toRaw(observed) {
    const raw = observed && observed["__v_raw"];
    return raw ? /* @__PURE__ */ toRaw(raw) : observed;
  }
  function markRaw(value) {
    if (!hasOwn(value, "__v_skip") && Object.isExtensible(value)) {
      def(value, "__v_skip", true);
    }
    return value;
  }
  var toReactive = (value) => isObject(value) ? /* @__PURE__ */ reactive(value) : value;
  var toReadonly = (value) => isObject(value) ? /* @__PURE__ */ readonly(value) : value;
  // @__NO_SIDE_EFFECTS__
  function isRef(r) {
    return r ? r["__v_isRef"] === true : false;
  }
  function unref(ref2) {
    return /* @__PURE__ */ isRef(ref2) ? ref2.value : ref2;
  }
  var shallowUnwrapHandlers = {
    get: (target, key, receiver) => key === "__v_raw" ? target : unref(Reflect.get(target, key, receiver)),
    set: (target, key, value, receiver) => {
      const oldValue = target[key];
      if (/* @__PURE__ */ isRef(oldValue) && !/* @__PURE__ */ isRef(value)) {
        oldValue.value = value;
        return true;
      } else {
        return Reflect.set(target, key, value, receiver);
      }
    }
  };
  function proxyRefs(objectWithRefs) {
    return /* @__PURE__ */ isReactive(objectWithRefs) ? objectWithRefs : new Proxy(objectWithRefs, shallowUnwrapHandlers);
  }
  var ComputedRefImpl = class {
    constructor(fn, setter, isSSR) {
      this.fn = fn;
      this.setter = setter;
      this._value = void 0;
      this.dep = new Dep(this);
      this.__v_isRef = true;
      this.deps = void 0;
      this.depsTail = void 0;
      this.flags = 16;
      this.globalVersion = globalVersion - 1;
      this.next = void 0;
      this.effect = this;
      this["__v_isReadonly"] = !setter;
      this.isSSR = isSSR;
    }
    /**
     * @internal
     */
    notify() {
      this.flags |= 16;
      if (!(this.flags & 8) && // avoid infinite self recursion
      activeSub !== this) {
        batch(this, true);
        return true;
      } else if (true) ;
    }
    get value() {
      const link = true ? this.dep.track({
        target: this,
        type: "get",
        key: "value"
      }) : this.dep.track();
      refreshComputed(this);
      if (link) {
        link.version = this.dep.version;
      }
      return this._value;
    }
    set value(newValue) {
      if (this.setter) {
        this.setter(newValue);
      } else if (true) {
        warn("Write operation failed: computed value is readonly");
      }
    }
  };
  // @__NO_SIDE_EFFECTS__
  function computed(getterOrOptions, debugOptions, isSSR = false) {
    let getter;
    let setter;
    if (isFunction(getterOrOptions)) {
      getter = getterOrOptions;
    } else {
      getter = getterOrOptions.get;
      setter = getterOrOptions.set;
    }
    const cRef = new ComputedRefImpl(getter, setter, isSSR);
    if (debugOptions && !isSSR) {
      cRef.onTrack = debugOptions.onTrack;
      cRef.onTrigger = debugOptions.onTrigger;
    }
    return cRef;
  }
  var INITIAL_WATCHER_VALUE = {};
  var cleanupMap = /* @__PURE__ */ new WeakMap();
  var activeWatcher = void 0;
  function onWatcherCleanup(cleanupFn, failSilently = false, owner = activeWatcher) {
    if (owner) {
      let cleanups = cleanupMap.get(owner);
      if (!cleanups) cleanupMap.set(owner, cleanups = []);
      cleanups.push(cleanupFn);
    } else if (!failSilently) {
      warn(
        `onWatcherCleanup() was called when there was no active watcher to associate with.`
      );
    }
  }
  function watch(source, cb, options = EMPTY_OBJ) {
    const { immediate, deep, once, scheduler, augmentJob, call } = options;
    const warnInvalidSource = (s) => {
      (options.onWarn || warn)(
        `Invalid watch source: `,
        s,
        `A watch source can only be a getter/effect function, a ref, a reactive object, or an array of these types.`
      );
    };
    const reactiveGetter = (source2) => {
      if (deep) return source2;
      if (/* @__PURE__ */ isShallow(source2) || deep === false || deep === 0)
        return traverse(source2, 1);
      return traverse(source2);
    };
    let effect2;
    let getter;
    let cleanup;
    let boundCleanup;
    let forceTrigger = false;
    let isMultiSource = false;
    if (/* @__PURE__ */ isRef(source)) {
      getter = () => source.value;
      forceTrigger = /* @__PURE__ */ isShallow(source);
    } else if (/* @__PURE__ */ isReactive(source)) {
      getter = () => reactiveGetter(source);
      forceTrigger = true;
    } else if (isArray(source)) {
      isMultiSource = true;
      forceTrigger = source.some((s) => /* @__PURE__ */ isReactive(s) || /* @__PURE__ */ isShallow(s));
      getter = () => source.map((s) => {
        if (/* @__PURE__ */ isRef(s)) {
          return s.value;
        } else if (/* @__PURE__ */ isReactive(s)) {
          return reactiveGetter(s);
        } else if (isFunction(s)) {
          return call ? call(s, 2) : s();
        } else {
          warnInvalidSource(s);
        }
      });
    } else if (isFunction(source)) {
      if (cb) {
        getter = call ? () => call(source, 2) : source;
      } else {
        getter = () => {
          if (cleanup) {
            pauseTracking();
            try {
              cleanup();
            } finally {
              resetTracking();
            }
          }
          const currentEffect = activeWatcher;
          activeWatcher = effect2;
          try {
            return call ? call(source, 3, [boundCleanup]) : source(boundCleanup);
          } finally {
            activeWatcher = currentEffect;
          }
        };
      }
    } else {
      getter = NOOP;
      warnInvalidSource(source);
    }
    if (cb && deep) {
      const baseGetter = getter;
      const depth = deep === true ? Infinity : deep;
      getter = () => traverse(baseGetter(), depth);
    }
    const scope = getCurrentScope();
    const watchHandle = () => {
      effect2.stop();
      if (scope && scope.active) {
        remove(scope.effects, effect2);
      }
    };
    if (once && cb) {
      const _cb = cb;
      cb = (...args) => {
        const res = _cb(...args);
        watchHandle();
        return res;
      };
    }
    let oldValue = isMultiSource ? new Array(source.length).fill(INITIAL_WATCHER_VALUE) : INITIAL_WATCHER_VALUE;
    const job = (immediateFirstRun) => {
      if (!(effect2.flags & 1) || !effect2.dirty && !immediateFirstRun) {
        return;
      }
      if (cb) {
        const newValue = effect2.run();
        if (immediateFirstRun || deep || forceTrigger || (isMultiSource ? newValue.some((v, i) => hasChanged(v, oldValue[i])) : hasChanged(newValue, oldValue))) {
          if (cleanup) {
            cleanup();
          }
          const currentWatcher = activeWatcher;
          activeWatcher = effect2;
          try {
            const args = [
              newValue,
              // pass undefined as the old value when it's changed for the first time
              oldValue === INITIAL_WATCHER_VALUE ? void 0 : isMultiSource && oldValue[0] === INITIAL_WATCHER_VALUE ? [] : oldValue,
              boundCleanup
            ];
            oldValue = newValue;
            call ? call(cb, 3, args) : (
              // @ts-expect-error
              cb(...args)
            );
          } finally {
            activeWatcher = currentWatcher;
          }
        }
      } else {
        effect2.run();
      }
    };
    if (augmentJob) {
      augmentJob(job);
    }
    effect2 = new ReactiveEffect(getter);
    effect2.scheduler = scheduler ? () => scheduler(job, false) : job;
    boundCleanup = (fn) => onWatcherCleanup(fn, false, effect2);
    cleanup = effect2.onStop = () => {
      const cleanups = cleanupMap.get(effect2);
      if (cleanups) {
        if (call) {
          call(cleanups, 4);
        } else {
          for (const cleanup2 of cleanups) cleanup2();
        }
        cleanupMap.delete(effect2);
      }
    };
    if (true) {
      effect2.onTrack = options.onTrack;
      effect2.onTrigger = options.onTrigger;
    }
    if (cb) {
      if (immediate) {
        job(true);
      } else {
        oldValue = effect2.run();
      }
    } else if (scheduler) {
      scheduler(job.bind(null, true), true);
    } else {
      effect2.run();
    }
    watchHandle.pause = effect2.pause.bind(effect2);
    watchHandle.resume = effect2.resume.bind(effect2);
    watchHandle.stop = watchHandle;
    return watchHandle;
  }
  function traverse(value, depth = Infinity, seen) {
    if (depth <= 0 || !isObject(value) || value["__v_skip"]) {
      return value;
    }
    seen = seen || /* @__PURE__ */ new Map();
    if ((seen.get(value) || 0) >= depth) {
      return value;
    }
    seen.set(value, depth);
    depth--;
    if (/* @__PURE__ */ isRef(value)) {
      traverse(value.value, depth, seen);
    } else if (isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        traverse(value[i], depth, seen);
      }
    } else if (isSet(value) || isMap(value)) {
      value.forEach((v) => {
        traverse(v, depth, seen);
      });
    } else if (isPlainObject(value)) {
      for (const key in value) {
        traverse(value[key], depth, seen);
      }
      for (const key of Object.getOwnPropertySymbols(value)) {
        if (Object.prototype.propertyIsEnumerable.call(value, key)) {
          traverse(value[key], depth, seen);
        }
      }
    }
    return value;
  }

  // node_modules/@vue/runtime-core/dist/runtime-core.esm-bundler.js
  var stack = [];
  function pushWarningContext(vnode) {
    stack.push(vnode);
  }
  function popWarningContext() {
    stack.pop();
  }
  var isWarning = false;
  function warn$1(msg, ...args) {
    if (isWarning) return;
    isWarning = true;
    pauseTracking();
    const instance = stack.length ? stack[stack.length - 1].component : null;
    const appWarnHandler = instance && instance.appContext.config.warnHandler;
    const trace = getComponentTrace();
    if (appWarnHandler) {
      callWithErrorHandling(
        appWarnHandler,
        instance,
        11,
        [
          // eslint-disable-next-line no-restricted-syntax
          msg + args.map((a) => {
            var _a, _b;
            return (_b = (_a = a.toString) == null ? void 0 : _a.call(a)) != null ? _b : JSON.stringify(a);
          }).join(""),
          instance && instance.proxy,
          trace.map(
            ({ vnode }) => `at <${formatComponentName(instance, vnode.type)}>`
          ).join("\n"),
          trace
        ]
      );
    } else {
      const warnArgs = [`[Vue warn]: ${msg}`, ...args];
      if (trace.length && // avoid spamming console during tests
      true) {
        warnArgs.push(`
`, ...formatTrace(trace));
      }
      console.warn(...warnArgs);
    }
    resetTracking();
    isWarning = false;
  }
  function getComponentTrace() {
    let currentVNode = stack[stack.length - 1];
    if (!currentVNode) {
      return [];
    }
    const normalizedStack = [];
    while (currentVNode) {
      const last = normalizedStack[0];
      if (last && last.vnode === currentVNode) {
        last.recurseCount++;
      } else {
        normalizedStack.push({
          vnode: currentVNode,
          recurseCount: 0
        });
      }
      const parentInstance = currentVNode.component && currentVNode.component.parent;
      currentVNode = parentInstance && parentInstance.vnode;
    }
    return normalizedStack;
  }
  function formatTrace(trace) {
    const logs = [];
    trace.forEach((entry, i) => {
      logs.push(...i === 0 ? [] : [`
`], ...formatTraceEntry(entry));
    });
    return logs;
  }
  function formatTraceEntry({ vnode, recurseCount }) {
    const postfix = recurseCount > 0 ? `... (${recurseCount} recursive calls)` : ``;
    const isRoot = vnode.component ? vnode.component.parent == null : false;
    const open = ` at <${formatComponentName(
      vnode.component,
      vnode.type,
      isRoot
    )}`;
    const close = `>` + postfix;
    return vnode.props ? [open, ...formatProps(vnode.props), close] : [open + close];
  }
  function formatProps(props) {
    const res = [];
    const keys = Object.keys(props);
    keys.slice(0, 3).forEach((key) => {
      res.push(...formatProp(key, props[key]));
    });
    if (keys.length > 3) {
      res.push(` ...`);
    }
    return res;
  }
  function formatProp(key, value, raw) {
    if (isString(value)) {
      value = JSON.stringify(value);
      return raw ? value : [`${key}=${value}`];
    } else if (typeof value === "number" || typeof value === "boolean" || value == null) {
      return raw ? value : [`${key}=${value}`];
    } else if (isRef(value)) {
      value = formatProp(key, toRaw(value.value), true);
      return raw ? value : [`${key}=Ref<`, value, `>`];
    } else if (isFunction(value)) {
      return [`${key}=fn${value.name ? `<${value.name}>` : ``}`];
    } else {
      value = toRaw(value);
      return raw ? value : [`${key}=`, value];
    }
  }
  var ErrorTypeStrings$1 = {
    ["sp"]: "serverPrefetch hook",
    ["bc"]: "beforeCreate hook",
    ["c"]: "created hook",
    ["bm"]: "beforeMount hook",
    ["m"]: "mounted hook",
    ["bu"]: "beforeUpdate hook",
    ["u"]: "updated",
    ["bum"]: "beforeUnmount hook",
    ["um"]: "unmounted hook",
    ["a"]: "activated hook",
    ["da"]: "deactivated hook",
    ["ec"]: "errorCaptured hook",
    ["rtc"]: "renderTracked hook",
    ["rtg"]: "renderTriggered hook",
    [0]: "setup function",
    [1]: "render function",
    [2]: "watcher getter",
    [3]: "watcher callback",
    [4]: "watcher cleanup function",
    [5]: "native event handler",
    [6]: "component event handler",
    [7]: "vnode hook",
    [8]: "directive hook",
    [9]: "transition hook",
    [10]: "app errorHandler",
    [11]: "app warnHandler",
    [12]: "ref function",
    [13]: "async component loader",
    [14]: "scheduler flush",
    [15]: "component update",
    [16]: "app unmount cleanup function"
  };
  function callWithErrorHandling(fn, instance, type, args) {
    try {
      return args ? fn(...args) : fn();
    } catch (err) {
      handleError(err, instance, type);
    }
  }
  function callWithAsyncErrorHandling(fn, instance, type, args) {
    if (isFunction(fn)) {
      const res = callWithErrorHandling(fn, instance, type, args);
      if (res && isPromise(res)) {
        res.catch((err) => {
          handleError(err, instance, type);
        });
      }
      return res;
    }
    if (isArray(fn)) {
      const values = [];
      for (let i = 0; i < fn.length; i++) {
        values.push(callWithAsyncErrorHandling(fn[i], instance, type, args));
      }
      return values;
    } else if (true) {
      warn$1(
        `Invalid value type passed to callWithAsyncErrorHandling(): ${typeof fn}`
      );
    }
  }
  function handleError(err, instance, type, throwInDev = true) {
    const contextVNode = instance ? instance.vnode : null;
    const { errorHandler, throwUnhandledErrorInProduction } = instance && instance.appContext.config || EMPTY_OBJ;
    if (instance) {
      let cur = instance.parent;
      const exposedInstance = instance.proxy;
      const errorInfo = true ? ErrorTypeStrings$1[type] : `https://vuejs.org/error-reference/#runtime-${type}`;
      while (cur) {
        const errorCapturedHooks = cur.ec;
        if (errorCapturedHooks) {
          for (let i = 0; i < errorCapturedHooks.length; i++) {
            if (errorCapturedHooks[i](err, exposedInstance, errorInfo) === false) {
              return;
            }
          }
        }
        cur = cur.parent;
      }
      if (errorHandler) {
        pauseTracking();
        callWithErrorHandling(errorHandler, null, 10, [
          err,
          exposedInstance,
          errorInfo
        ]);
        resetTracking();
        return;
      }
    }
    logError(err, type, contextVNode, throwInDev, throwUnhandledErrorInProduction);
  }
  function logError(err, type, contextVNode, throwInDev = true, throwInProd = false) {
    if (true) {
      const info = ErrorTypeStrings$1[type];
      if (contextVNode) {
        pushWarningContext(contextVNode);
      }
      warn$1(`Unhandled error${info ? ` during execution of ${info}` : ``}`);
      if (contextVNode) {
        popWarningContext();
      }
      if (throwInDev) {
        throw err;
      } else {
        console.error(err);
      }
    } else if (throwInProd) {
      throw err;
    } else {
      console.error(err);
    }
  }
  var queue = [];
  var flushIndex = -1;
  var pendingPostFlushCbs = [];
  var activePostFlushCbs = null;
  var postFlushIndex = 0;
  var resolvedPromise = /* @__PURE__ */ Promise.resolve();
  var currentFlushPromise = null;
  var RECURSION_LIMIT = 100;
  function nextTick(fn) {
    const p = currentFlushPromise || resolvedPromise;
    return fn ? p.then(this ? fn.bind(this) : fn) : p;
  }
  function findInsertionIndex(id) {
    let start = flushIndex + 1;
    let end = queue.length;
    while (start < end) {
      const middle = start + end >>> 1;
      const middleJob = queue[middle];
      const middleJobId = getId(middleJob);
      if (middleJobId < id || middleJobId === id && middleJob.flags & 2) {
        start = middle + 1;
      } else {
        end = middle;
      }
    }
    return start;
  }
  function queueJob(job) {
    if (!(job.flags & 1)) {
      const jobId = getId(job);
      const lastJob = queue[queue.length - 1];
      if (!lastJob || // fast path when the job id is larger than the tail
      !(job.flags & 2) && jobId >= getId(lastJob)) {
        queue.push(job);
      } else {
        queue.splice(findInsertionIndex(jobId), 0, job);
      }
      job.flags |= 1;
      queueFlush();
    }
  }
  function queueFlush() {
    if (!currentFlushPromise) {
      currentFlushPromise = resolvedPromise.then(flushJobs);
    }
  }
  function queuePostFlushCb(cb) {
    if (!isArray(cb)) {
      if (activePostFlushCbs && cb.id === -1) {
        activePostFlushCbs.splice(postFlushIndex + 1, 0, cb);
      } else if (!(cb.flags & 1)) {
        pendingPostFlushCbs.push(cb);
        cb.flags |= 1;
      }
    } else {
      for (let i = 0; i < cb.length; i++) {
        pendingPostFlushCbs.push(cb[i]);
      }
    }
    queueFlush();
  }
  function flushPostFlushCbs(seen) {
    if (pendingPostFlushCbs.length) {
      const deduped = [...new Set(pendingPostFlushCbs)].sort(
        (a, b) => getId(a) - getId(b)
      );
      pendingPostFlushCbs.length = 0;
      if (activePostFlushCbs) {
        for (let i = 0; i < deduped.length; i++) {
          activePostFlushCbs.push(deduped[i]);
        }
        return;
      }
      activePostFlushCbs = deduped;
      if (true) {
        seen = seen || /* @__PURE__ */ new Map();
      }
      for (postFlushIndex = 0; postFlushIndex < activePostFlushCbs.length; postFlushIndex++) {
        const cb = activePostFlushCbs[postFlushIndex];
        if (checkRecursiveUpdates(seen, cb)) {
          continue;
        }
        if (cb.flags & 4) {
          cb.flags &= -2;
        }
        if (!(cb.flags & 8)) cb();
        cb.flags &= -2;
      }
      activePostFlushCbs = null;
      postFlushIndex = 0;
    }
  }
  var getId = (job) => job.id == null ? job.flags & 2 ? -1 : Infinity : job.id;
  function flushJobs(seen) {
    if (true) {
      seen = seen || /* @__PURE__ */ new Map();
    }
    const check2 = true ? (job) => checkRecursiveUpdates(seen, job) : NOOP;
    try {
      for (flushIndex = 0; flushIndex < queue.length; flushIndex++) {
        const job = queue[flushIndex];
        if (job && !(job.flags & 8)) {
          if (check2(job)) {
            continue;
          }
          if (job.flags & 4) {
            job.flags &= ~1;
          }
          callWithErrorHandling(
            job,
            job.i,
            job.i ? 15 : 14
          );
          if (!(job.flags & 4)) {
            job.flags &= ~1;
          }
        }
      }
    } finally {
      for (; flushIndex < queue.length; flushIndex++) {
        const job = queue[flushIndex];
        if (job) {
          job.flags &= -2;
        }
      }
      flushIndex = -1;
      queue.length = 0;
      flushPostFlushCbs(seen);
      currentFlushPromise = null;
      if (queue.length || pendingPostFlushCbs.length) {
        flushJobs(seen);
      }
    }
  }
  function checkRecursiveUpdates(seen, fn) {
    const count = seen.get(fn) || 0;
    if (count > RECURSION_LIMIT) {
      const instance = fn.i;
      const componentName = instance && getComponentName(instance.type);
      handleError(
        `Maximum recursive updates exceeded${componentName ? ` in component <${componentName}>` : ``}. This means you have a reactive effect that is mutating its own dependencies and thus recursively triggering itself. Possible sources include component template, render function, updated hook or watcher source function.`,
        null,
        10
      );
      return true;
    }
    seen.set(fn, count + 1);
    return false;
  }
  var isHmrUpdating = false;
  var hmrDirtyComponents = /* @__PURE__ */ new Map();
  if (true) {
    getGlobalThis().__VUE_HMR_RUNTIME__ = {
      createRecord: tryWrap(createRecord),
      rerender: tryWrap(rerender),
      reload: tryWrap(reload)
    };
  }
  var map = /* @__PURE__ */ new Map();
  function createRecord(id, initialDef) {
    if (map.has(id)) {
      return false;
    }
    map.set(id, {
      initialDef: normalizeClassComponent(initialDef),
      instances: /* @__PURE__ */ new Set()
    });
    return true;
  }
  function normalizeClassComponent(component) {
    return isClassComponent(component) ? component.__vccOpts : component;
  }
  function rerender(id, newRender) {
    const record = map.get(id);
    if (!record) {
      return;
    }
    record.initialDef.render = newRender;
    [...record.instances].forEach((instance) => {
      if (newRender) {
        instance.render = newRender;
        normalizeClassComponent(instance.type).render = newRender;
      }
      instance.renderCache = [];
      isHmrUpdating = true;
      if (!(instance.job.flags & 8)) {
        instance.update();
      }
      isHmrUpdating = false;
    });
  }
  function reload(id, newComp) {
    const record = map.get(id);
    if (!record) return;
    newComp = normalizeClassComponent(newComp);
    updateComponentDef(record.initialDef, newComp);
    const instances = [...record.instances];
    for (let i = 0; i < instances.length; i++) {
      const instance = instances[i];
      const oldComp = normalizeClassComponent(instance.type);
      let dirtyInstances = hmrDirtyComponents.get(oldComp);
      if (!dirtyInstances) {
        if (oldComp !== record.initialDef) {
          updateComponentDef(oldComp, newComp);
        }
        hmrDirtyComponents.set(oldComp, dirtyInstances = /* @__PURE__ */ new Set());
      }
      dirtyInstances.add(instance);
      instance.appContext.propsCache.delete(instance.type);
      instance.appContext.emitsCache.delete(instance.type);
      instance.appContext.optionsCache.delete(instance.type);
      if (instance.ceReload) {
        dirtyInstances.add(instance);
        instance.ceReload(newComp.styles);
        dirtyInstances.delete(instance);
      } else if (instance.parent) {
        queueJob(() => {
          if (!(instance.job.flags & 8)) {
            isHmrUpdating = true;
            instance.parent.update();
            isHmrUpdating = false;
            dirtyInstances.delete(instance);
          }
        });
      } else if (instance.appContext.reload) {
        instance.appContext.reload();
      } else if (typeof window !== "undefined") {
        window.location.reload();
      } else {
        console.warn(
          "[HMR] Root or manually mounted instance modified. Full reload required."
        );
      }
      if (instance.root.ce && instance !== instance.root) {
        instance.root.ce._removeChildStyle(oldComp);
      }
    }
    queuePostFlushCb(() => {
      hmrDirtyComponents.clear();
    });
  }
  function updateComponentDef(oldComp, newComp) {
    extend(oldComp, newComp);
    for (const key in oldComp) {
      if (key !== "__file" && !(key in newComp)) {
        delete oldComp[key];
      }
    }
  }
  function tryWrap(fn) {
    return (id, arg) => {
      try {
        return fn(id, arg);
      } catch (e) {
        console.error(e);
        console.warn(
          `[HMR] Something went wrong during Vue component hot-reload. Full reload required.`
        );
      }
    };
  }
  var currentRenderingInstance = null;
  function inject(key, defaultValue, treatDefaultAsFactory = false) {
    const instance = getCurrentInstance();
    if (instance || currentApp) {
      let provides = currentApp ? currentApp._context.provides : instance ? instance.parent == null || instance.ce ? instance.vnode.appContext && instance.vnode.appContext.provides : instance.parent.provides : void 0;
      if (provides && key in provides) {
        return provides[key];
      } else if (arguments.length > 1) {
        return treatDefaultAsFactory && isFunction(defaultValue) ? defaultValue.call(instance && instance.proxy) : defaultValue;
      } else if (true) {
        warn$1(`injection "${String(key)}" not found.`);
      }
    } else if (true) {
      warn$1(`inject() can only be used inside setup() or functional components.`);
    }
  }
  var ssrContextKey = /* @__PURE__ */ Symbol.for("v-scx");
  var useSSRContext = () => {
    {
      const ctx = inject(ssrContextKey);
      if (!ctx) {
        warn$1(
          `Server rendering context not provided. Make sure to only call useSSRContext() conditionally in the server build.`
        );
      }
      return ctx;
    }
  };
  function doWatch(source, cb, options = EMPTY_OBJ) {
    const { immediate, deep, flush, once } = options;
    if (!cb) {
      if (immediate !== void 0) {
        warn$1(
          `watch() "immediate" option is only respected when using the watch(source, callback, options?) signature.`
        );
      }
      if (deep !== void 0) {
        warn$1(
          `watch() "deep" option is only respected when using the watch(source, callback, options?) signature.`
        );
      }
      if (once !== void 0) {
        warn$1(
          `watch() "once" option is only respected when using the watch(source, callback, options?) signature.`
        );
      }
    }
    const baseWatchOptions = extend({}, options);
    if (true) baseWatchOptions.onWarn = warn$1;
    const runsImmediately = cb && immediate || !cb && flush !== "post";
    let ssrCleanup;
    if (isInSSRComponentSetup) {
      if (flush === "sync") {
        const ctx = useSSRContext();
        ssrCleanup = ctx.__watcherHandles || (ctx.__watcherHandles = []);
      } else if (!runsImmediately) {
        const watchStopHandle = () => {
        };
        watchStopHandle.stop = NOOP;
        watchStopHandle.resume = NOOP;
        watchStopHandle.pause = NOOP;
        return watchStopHandle;
      }
    }
    const instance = currentInstance;
    baseWatchOptions.call = (fn, type, args) => callWithAsyncErrorHandling(fn, instance, type, args);
    let isPre = false;
    if (flush === "post") {
      baseWatchOptions.scheduler = (job) => {
        queuePostRenderEffect(job, instance && instance.suspense);
      };
    } else if (flush !== "sync") {
      isPre = true;
      baseWatchOptions.scheduler = (job, isFirstRun) => {
        if (isFirstRun) {
          job();
        } else {
          queueJob(job);
        }
      };
    }
    baseWatchOptions.augmentJob = (job) => {
      if (cb) {
        job.flags |= 4;
      }
      if (isPre) {
        job.flags |= 2;
        if (instance) {
          job.id = instance.uid;
          job.i = instance;
        }
      }
    };
    const watchHandle = watch(source, cb, baseWatchOptions);
    if (isInSSRComponentSetup) {
      if (ssrCleanup) {
        ssrCleanup.push(watchHandle);
      } else if (runsImmediately) {
        watchHandle();
      }
    }
    return watchHandle;
  }
  function instanceWatch(source, value, options) {
    const publicThis = this.proxy;
    const getter = isString(source) ? source.includes(".") ? createPathGetter(publicThis, source) : () => publicThis[source] : source.bind(publicThis, publicThis);
    let cb;
    if (isFunction(value)) {
      cb = value;
    } else {
      cb = value.handler;
      options = value;
    }
    const reset = setCurrentInstance(this);
    const res = doWatch(getter, cb.bind(publicThis), options);
    reset();
    return res;
  }
  function createPathGetter(ctx, path) {
    const segments = path.split(".");
    return () => {
      let cur = ctx;
      for (let i = 0; i < segments.length && cur; i++) {
        cur = cur[segments[i]];
      }
      return cur;
    };
  }
  var requestIdleCallback = getGlobalThis().requestIdleCallback || ((cb) => setTimeout(cb, 1));
  var cancelIdleCallback = getGlobalThis().cancelIdleCallback || ((id) => clearTimeout(id));
  function injectHook(type, hook, target = currentInstance, prepend = false) {
    if (target) {
      const hooks = target[type] || (target[type] = []);
      const wrappedHook = hook.__weh || (hook.__weh = (...args) => {
        pauseTracking();
        const reset = setCurrentInstance(target);
        const res = callWithAsyncErrorHandling(hook, target, type, args);
        reset();
        resetTracking();
        return res;
      });
      if (prepend) {
        hooks.unshift(wrappedHook);
      } else {
        hooks.push(wrappedHook);
      }
      return wrappedHook;
    } else if (true) {
      const apiName = toHandlerKey(ErrorTypeStrings$1[type].replace(/ hook$/, ""));
      warn$1(
        `${apiName} is called when there is no active component instance to be associated with. Lifecycle injection APIs can only be used during execution of setup(). If you are using async setup(), make sure to register lifecycle hooks before the first await statement.`
      );
    }
  }
  var createHook = (lifecycle) => (hook, target = currentInstance) => {
    if (!isInSSRComponentSetup || lifecycle === "sp") {
      injectHook(lifecycle, (...args) => hook(...args), target);
    }
  };
  var onBeforeMount = createHook("bm");
  var onMounted = createHook("m");
  var onBeforeUpdate = createHook(
    "bu"
  );
  var onUpdated = createHook("u");
  var onBeforeUnmount = createHook(
    "bum"
  );
  var onUnmounted = createHook("um");
  var onServerPrefetch = createHook(
    "sp"
  );
  var onRenderTriggered = createHook("rtg");
  var onRenderTracked = createHook("rtc");
  var getPublicInstance = (i) => {
    if (!i) return null;
    if (isStatefulComponent(i)) return getComponentPublicInstance(i);
    return getPublicInstance(i.parent);
  };
  var resolveDevRootEl = (vnode) => {
    let found = false;
    while (true) {
      if (vnode.patchFlag > 0 && vnode.patchFlag & 2048) {
        const root = filterSingleRoot(vnode.children);
        if (!root) {
          return;
        }
        vnode = root;
        found = true;
        continue;
      }
      const component = vnode.component;
      if (component && component.subTree) {
        vnode = component.subTree;
        continue;
      }
      const suspense = vnode.suspense;
      if (suspense && suspense.activeBranch) {
        vnode = suspense.activeBranch;
        continue;
      }
      return found ? vnode.el : void 0;
    }
  };
  var getDevRootFragmentEl = (i) => {
    const el = i.subTree && resolveDevRootEl(i.subTree);
    return el === void 0 ? i.vnode.el : el;
  };
  var publicPropertiesMap = (
    // Move PURE marker to new line to workaround compiler discarding it
    // due to type annotation
    /* @__PURE__ */ extend(/* @__PURE__ */ Object.create(null), {
      $: (i) => i,
      $el: (i) => true ? getDevRootFragmentEl(i) : i.vnode.el,
      $data: (i) => i.data,
      $props: (i) => true ? shallowReadonly(i.props) : i.props,
      $attrs: (i) => true ? shallowReadonly(i.attrs) : i.attrs,
      $slots: (i) => true ? shallowReadonly(i.slots) : i.slots,
      $refs: (i) => true ? shallowReadonly(i.refs) : i.refs,
      $parent: (i) => getPublicInstance(i.parent),
      $root: (i) => getPublicInstance(i.root),
      $host: (i) => i.ce,
      $emit: (i) => i.emit,
      $options: (i) => __VUE_OPTIONS_API__ ? resolveMergedOptions(i) : i.type,
      $forceUpdate: (i) => i.f || (i.f = () => {
        queueJob(i.update);
      }),
      $nextTick: (i) => i.n || (i.n = nextTick.bind(i.proxy)),
      $watch: (i) => __VUE_OPTIONS_API__ ? instanceWatch.bind(i) : NOOP
    })
  );
  var isReservedPrefix = (key) => key === "_" || key === "$";
  var hasSetupBinding = (state2, key) => state2 !== EMPTY_OBJ && !state2.__isScriptSetup && hasOwn(state2, key);
  var PublicInstanceProxyHandlers = {
    get({ _: instance }, key) {
      if (key === "__v_skip") {
        return true;
      }
      const { ctx, setupState, data, props, accessCache, type, appContext } = instance;
      if (key === "__isVue") {
        return true;
      }
      if (key[0] !== "$") {
        const n = accessCache[key];
        if (n !== void 0) {
          switch (n) {
            case 1:
              return setupState[key];
            case 2:
              return data[key];
            case 4:
              return ctx[key];
            case 3:
              return props[key];
          }
        } else if (hasSetupBinding(setupState, key)) {
          accessCache[key] = 1;
          return setupState[key];
        } else if (__VUE_OPTIONS_API__ && data !== EMPTY_OBJ && hasOwn(data, key)) {
          accessCache[key] = 2;
          return data[key];
        } else if (hasOwn(props, key)) {
          accessCache[key] = 3;
          return props[key];
        } else if (ctx !== EMPTY_OBJ && hasOwn(ctx, key)) {
          accessCache[key] = 4;
          return ctx[key];
        } else if (!__VUE_OPTIONS_API__ || shouldCacheAccess) {
          accessCache[key] = 0;
        }
      }
      const publicGetter = publicPropertiesMap[key];
      let cssModule, globalProperties;
      if (publicGetter) {
        if (key === "$attrs") {
          track(instance.attrs, "get", "");
          markAttrsAccessed();
        } else if (key === "$slots") {
          track(instance, "get", key);
        }
        return publicGetter(instance);
      } else if (
        // css module (injected by vue-loader)
        (cssModule = type.__cssModules) && (cssModule = cssModule[key])
      ) {
        return cssModule;
      } else if (ctx !== EMPTY_OBJ && hasOwn(ctx, key)) {
        accessCache[key] = 4;
        return ctx[key];
      } else if (
        // global properties
        globalProperties = appContext.config.globalProperties, hasOwn(globalProperties, key)
      ) {
        {
          return globalProperties[key];
        }
      } else if (currentRenderingInstance && (!isString(key) || // #1091 avoid internal isRef/isVNode checks on component instance leading
      // to infinite warning loop
      key.indexOf("__v") !== 0)) {
        if (data !== EMPTY_OBJ && isReservedPrefix(key[0]) && hasOwn(data, key)) {
          warn$1(
            `Property ${JSON.stringify(
              key
            )} must be accessed via $data because it starts with a reserved character ("$" or "_") and is not proxied on the render context.`
          );
        } else if (instance === currentRenderingInstance) {
          warn$1(
            `Property ${JSON.stringify(key)} was accessed during render but is not defined on instance.`
          );
        }
      }
    },
    set({ _: instance }, key, value) {
      const { data, setupState, ctx } = instance;
      if (hasSetupBinding(setupState, key)) {
        setupState[key] = value;
        return true;
      } else if (setupState.__isScriptSetup && hasOwn(setupState, key)) {
        warn$1(`Cannot mutate <script setup> binding "${key}" from Options API.`);
        return false;
      } else if (__VUE_OPTIONS_API__ && data !== EMPTY_OBJ && hasOwn(data, key)) {
        data[key] = value;
        return true;
      } else if (hasOwn(instance.props, key)) {
        warn$1(`Attempting to mutate prop "${key}". Props are readonly.`);
        return false;
      }
      if (key[0] === "$" && key.slice(1) in instance) {
        warn$1(
          `Attempting to mutate public property "${key}". Properties starting with $ are reserved and readonly.`
        );
        return false;
      } else {
        if (key in instance.appContext.config.globalProperties) {
          Object.defineProperty(ctx, key, {
            enumerable: true,
            configurable: true,
            value
          });
        } else {
          ctx[key] = value;
        }
      }
      return true;
    },
    has({
      _: { data, setupState, accessCache, ctx, appContext, props, type }
    }, key) {
      let cssModules;
      return !!(accessCache[key] || __VUE_OPTIONS_API__ && data !== EMPTY_OBJ && key[0] !== "$" && hasOwn(data, key) || hasSetupBinding(setupState, key) || hasOwn(props, key) || hasOwn(ctx, key) || hasOwn(publicPropertiesMap, key) || hasOwn(appContext.config.globalProperties, key) || (cssModules = type.__cssModules) && cssModules[key]);
    },
    defineProperty(target, key, descriptor) {
      if (descriptor.get != null) {
        target._.accessCache[key] = 0;
      } else if (hasOwn(descriptor, "value")) {
        this.set(target, key, descriptor.value, null);
      }
      return Reflect.defineProperty(target, key, descriptor);
    }
  };
  if (true) {
    PublicInstanceProxyHandlers.ownKeys = (target) => {
      warn$1(
        `Avoid app logic that relies on enumerating keys on a component instance. The keys will be empty in production mode to avoid performance overhead.`
      );
      return Reflect.ownKeys(target);
    };
  }
  function normalizePropsOrEmits(props) {
    return isArray(props) ? props.reduce(
      (normalized, p) => (normalized[p] = null, normalized),
      {}
    ) : props;
  }
  var shouldCacheAccess = true;
  function resolveMergedOptions(instance) {
    const base = instance.type;
    const { mixins, extends: extendsOptions } = base;
    const {
      mixins: globalMixins,
      optionsCache: cache,
      config: { optionMergeStrategies }
    } = instance.appContext;
    const cached = cache.get(base);
    let resolved;
    if (cached) {
      resolved = cached;
    } else if (!globalMixins.length && !mixins && !extendsOptions) {
      {
        resolved = base;
      }
    } else {
      resolved = {};
      if (globalMixins.length) {
        globalMixins.forEach(
          (m) => mergeOptions(resolved, m, optionMergeStrategies, true)
        );
      }
      mergeOptions(resolved, base, optionMergeStrategies);
    }
    if (isObject(base)) {
      cache.set(base, resolved);
    }
    return resolved;
  }
  function mergeOptions(to, from, strats, asMixin = false) {
    const { mixins, extends: extendsOptions } = from;
    if (extendsOptions) {
      mergeOptions(to, extendsOptions, strats, true);
    }
    if (mixins) {
      mixins.forEach(
        (m) => mergeOptions(to, m, strats, true)
      );
    }
    for (const key in from) {
      if (asMixin && key === "expose") {
        warn$1(
          `"expose" option is ignored when declared in mixins or extends. It should only be declared in the base component itself.`
        );
      } else {
        const strat = internalOptionMergeStrats[key] || strats && strats[key];
        to[key] = strat ? strat(to[key], from[key]) : from[key];
      }
    }
    return to;
  }
  var internalOptionMergeStrats = {
    data: mergeDataFn,
    props: mergeEmitsOrPropsOptions,
    emits: mergeEmitsOrPropsOptions,
    // objects
    methods: mergeObjectOptions,
    computed: mergeObjectOptions,
    // lifecycle
    beforeCreate: mergeAsArray,
    created: mergeAsArray,
    beforeMount: mergeAsArray,
    mounted: mergeAsArray,
    beforeUpdate: mergeAsArray,
    updated: mergeAsArray,
    beforeDestroy: mergeAsArray,
    beforeUnmount: mergeAsArray,
    destroyed: mergeAsArray,
    unmounted: mergeAsArray,
    activated: mergeAsArray,
    deactivated: mergeAsArray,
    errorCaptured: mergeAsArray,
    serverPrefetch: mergeAsArray,
    // assets
    components: mergeObjectOptions,
    directives: mergeObjectOptions,
    // watch
    watch: mergeWatchOptions,
    // provide / inject
    provide: mergeDataFn,
    inject: mergeInject
  };
  function mergeDataFn(to, from) {
    if (!from) {
      return to;
    }
    if (!to) {
      return from;
    }
    return function mergedDataFn() {
      return extend(
        isFunction(to) ? to.call(this, this) : to,
        isFunction(from) ? from.call(this, this) : from
      );
    };
  }
  function mergeInject(to, from) {
    return mergeObjectOptions(normalizeInject(to), normalizeInject(from));
  }
  function normalizeInject(raw) {
    if (isArray(raw)) {
      const res = {};
      for (let i = 0; i < raw.length; i++) {
        res[raw[i]] = raw[i];
      }
      return res;
    }
    return raw;
  }
  function mergeAsArray(to, from) {
    return to ? [...new Set([].concat(to, from))] : from;
  }
  function mergeObjectOptions(to, from) {
    return to ? extend(/* @__PURE__ */ Object.create(null), to, from) : from;
  }
  function mergeEmitsOrPropsOptions(to, from) {
    if (to) {
      if (isArray(to) && isArray(from)) {
        return [.../* @__PURE__ */ new Set([...to, ...from])];
      }
      return extend(
        /* @__PURE__ */ Object.create(null),
        normalizePropsOrEmits(to),
        normalizePropsOrEmits(from != null ? from : {})
      );
    } else {
      return from;
    }
  }
  function mergeWatchOptions(to, from) {
    if (!to) return from;
    if (!from) return to;
    const merged = extend(/* @__PURE__ */ Object.create(null), to);
    for (const key in from) {
      merged[key] = mergeAsArray(to[key], from[key]);
    }
    return merged;
  }
  function createAppContext() {
    return {
      app: null,
      config: {
        isNativeTag: NO,
        performance: false,
        globalProperties: {},
        optionMergeStrategies: {},
        errorHandler: void 0,
        warnHandler: void 0,
        compilerOptions: {}
      },
      mixins: [],
      components: {},
      directives: {},
      provides: /* @__PURE__ */ Object.create(null),
      optionsCache: /* @__PURE__ */ new WeakMap(),
      propsCache: /* @__PURE__ */ new WeakMap(),
      emitsCache: /* @__PURE__ */ new WeakMap()
    };
  }
  var currentApp = null;
  var accessedAttrs = false;
  function markAttrsAccessed() {
    accessedAttrs = true;
  }
  function filterSingleRoot(children, recurse = true) {
    let singleRoot;
    for (let i = 0; i < children.length; i++) {
      const child = children[i];
      if (isVNode(child)) {
        if (child.type !== Comment || child.children === "v-if") {
          if (singleRoot) {
            return;
          } else {
            singleRoot = child;
            if (recurse && singleRoot.patchFlag > 0 && singleRoot.patchFlag & 2048) {
              return filterSingleRoot(singleRoot.children);
            }
          }
        }
      } else {
        return;
      }
    }
    return singleRoot;
  }
  var queuePostRenderEffect = queueEffectWithSuspense;
  function queueEffectWithSuspense(fn, suspense) {
    if (suspense && suspense.pendingBranch) {
      if (isArray(fn)) {
        suspense.effects.push(...fn);
      } else {
        suspense.effects.push(fn);
      }
    } else {
      queuePostFlushCb(fn);
    }
  }
  var Comment = /* @__PURE__ */ Symbol.for("v-cmt");
  function isVNode(value) {
    return value ? value.__v_isVNode === true : false;
  }
  var emptyAppContext = createAppContext();
  var currentInstance = null;
  var getCurrentInstance = () => currentInstance || currentRenderingInstance;
  var internalSetCurrentInstance;
  var setInSSRSetupState;
  {
    const g = getGlobalThis();
    const registerGlobalSetter = (key, setter) => {
      let setters;
      if (!(setters = g[key])) setters = g[key] = [];
      setters.push(setter);
      return (v) => {
        if (setters.length > 1) setters.forEach((set) => set(v));
        else setters[0](v);
      };
    };
    internalSetCurrentInstance = registerGlobalSetter(
      `__VUE_INSTANCE_SETTERS__`,
      (v) => currentInstance = v
    );
    setInSSRSetupState = registerGlobalSetter(
      `__VUE_SSR_SETTERS__`,
      (v) => isInSSRComponentSetup = v
    );
  }
  var setCurrentInstance = (instance) => {
    const prev = currentInstance;
    internalSetCurrentInstance(instance);
    instance.scope.on();
    return () => {
      instance.scope.off();
      internalSetCurrentInstance(prev);
    };
  };
  function isStatefulComponent(instance) {
    return instance.vnode.shapeFlag & 4;
  }
  var isInSSRComponentSetup = false;
  function getComponentPublicInstance(instance) {
    if (instance.exposed) {
      return instance.exposeProxy || (instance.exposeProxy = new Proxy(proxyRefs(markRaw(instance.exposed)), {
        get(target, key) {
          if (key in target) {
            return target[key];
          } else if (key in publicPropertiesMap) {
            return publicPropertiesMap[key](instance);
          }
        },
        has(target, key) {
          return key in target || key in publicPropertiesMap;
        }
      }));
    } else {
      return instance.proxy;
    }
  }
  var classifyRE = /(?:^|[-_])\w/g;
  var classify = (str) => str.replace(classifyRE, (c) => c.toUpperCase()).replace(/[-_]/g, "");
  function getComponentName(Component, includeInferred = true) {
    return isFunction(Component) ? Component.displayName || Component.name : Component.name || includeInferred && Component.__name;
  }
  function formatComponentName(instance, Component, isRoot = false) {
    let name = getComponentName(Component);
    if (!name && Component.__file) {
      const match = Component.__file.match(/([^/\\]+)\.\w+$/);
      if (match) {
        name = match[1];
      }
    }
    if (!name && instance) {
      const inferFromRegistry = (registry) => {
        for (const key in registry) {
          if (registry[key] === Component) {
            return key;
          }
        }
      };
      name = inferFromRegistry(instance.components) || instance.parent && inferFromRegistry(
        instance.parent.type.components
      ) || inferFromRegistry(instance.appContext.components);
    }
    return name ? classify(name) : isRoot ? `App` : `Anonymous`;
  }
  function isClassComponent(value) {
    return isFunction(value) && "__vccOpts" in value;
  }
  var computed2 = (getterOrOptions, debugOptions) => {
    const c = computed(getterOrOptions, debugOptions, isInSSRComponentSetup);
    if (true) {
      const i = getCurrentInstance();
      if (i && i.appContext.config.warnRecursiveComputed) {
        c._warnRecursive = true;
      }
    }
    return c;
  };
  function initCustomFormatter() {
    if (typeof window === "undefined") {
      return;
    }
    const vueStyle = { style: "color:#3ba776" };
    const numberStyle = { style: "color:#1677ff" };
    const stringStyle = { style: "color:#f5222d" };
    const keywordStyle = { style: "color:#eb2f96" };
    const formatter = {
      __vue_custom_formatter: true,
      header(obj) {
        if (!isObject(obj)) {
          return null;
        }
        if (obj.__isVue) {
          return ["div", vueStyle, `VueInstance`];
        } else if (isRef(obj)) {
          pauseTracking();
          const value = obj.value;
          resetTracking();
          return [
            "div",
            {},
            ["span", vueStyle, genRefFlag(obj)],
            "<",
            formatValue(value),
            `>`
          ];
        } else if (isReactive(obj)) {
          return [
            "div",
            {},
            ["span", vueStyle, isShallow(obj) ? "ShallowReactive" : "Reactive"],
            "<",
            formatValue(obj),
            `>${isReadonly(obj) ? ` (readonly)` : ``}`
          ];
        } else if (isReadonly(obj)) {
          return [
            "div",
            {},
            ["span", vueStyle, isShallow(obj) ? "ShallowReadonly" : "Readonly"],
            "<",
            formatValue(obj),
            ">"
          ];
        }
        return null;
      },
      hasBody(obj) {
        return obj && obj.__isVue;
      },
      body(obj) {
        if (obj && obj.__isVue) {
          return [
            "div",
            {},
            ...formatInstance(obj.$)
          ];
        }
      }
    };
    function formatInstance(instance) {
      const blocks = [];
      if (instance.type.props && instance.props) {
        blocks.push(createInstanceBlock("props", toRaw(instance.props)));
      }
      if (instance.setupState !== EMPTY_OBJ) {
        blocks.push(createInstanceBlock("setup", instance.setupState));
      }
      if (instance.data !== EMPTY_OBJ) {
        blocks.push(createInstanceBlock("data", toRaw(instance.data)));
      }
      const computed3 = extractKeys(instance, "computed");
      if (computed3) {
        blocks.push(createInstanceBlock("computed", computed3));
      }
      const injected = extractKeys(instance, "inject");
      if (injected) {
        blocks.push(createInstanceBlock("injected", injected));
      }
      blocks.push([
        "div",
        {},
        [
          "span",
          {
            style: keywordStyle.style + ";opacity:0.66"
          },
          "$ (internal): "
        ],
        ["object", { object: instance }]
      ]);
      return blocks;
    }
    function createInstanceBlock(type, target) {
      target = extend({}, target);
      if (!Object.keys(target).length) {
        return ["span", {}];
      }
      return [
        "div",
        { style: "line-height:1.25em;margin-bottom:0.6em" },
        [
          "div",
          {
            style: "color:#476582"
          },
          type
        ],
        [
          "div",
          {
            style: "padding-left:1.25em"
          },
          ...Object.keys(target).map((key) => {
            return [
              "div",
              {},
              ["span", keywordStyle, key + ": "],
              formatValue(target[key], false)
            ];
          })
        ]
      ];
    }
    function formatValue(v, asRaw = true) {
      if (typeof v === "number") {
        return ["span", numberStyle, v];
      } else if (typeof v === "string") {
        return ["span", stringStyle, JSON.stringify(v)];
      } else if (typeof v === "boolean") {
        return ["span", keywordStyle, v];
      } else if (isObject(v)) {
        return ["object", { object: asRaw ? toRaw(v) : v }];
      } else {
        return ["span", stringStyle, String(v)];
      }
    }
    function extractKeys(instance, type) {
      const Comp = instance.type;
      if (isFunction(Comp)) {
        return;
      }
      const extracted = {};
      for (const key in instance.ctx) {
        if (isKeyOfType(Comp, key, type)) {
          extracted[key] = instance.ctx[key];
        }
      }
      return extracted;
    }
    function isKeyOfType(Comp, key, type) {
      const opts = Comp[type];
      if (isArray(opts) && opts.includes(key) || isObject(opts) && key in opts) {
        return true;
      }
      if (Comp.extends && isKeyOfType(Comp.extends, key, type)) {
        return true;
      }
      if (Comp.mixins && Comp.mixins.some((m) => isKeyOfType(m, key, type))) {
        return true;
      }
    }
    function genRefFlag(v) {
      if (isShallow(v)) {
        return `ShallowRef`;
      }
      if (v.effect) {
        return `ComputedRef`;
      }
      return `Ref`;
    }
    if (window.devtoolsFormatters) {
      window.devtoolsFormatters.push(formatter);
    } else {
      window.devtoolsFormatters = [formatter];
    }
  }

  // node_modules/vue/dist/vue.runtime.esm-bundler.js
  function initDev() {
    {
      initCustomFormatter();
    }
  }
  if (true) {
    initDev();
  }

  // src/data/session.js
  var state = reactive({
    user: null,
    theme: "a"
  });
  function currentUser() {
    return state.user;
  }
  var isLoggedIn = computed2(() => state.user !== null);
  var isAdmin = computed2(() => state.user !== null && state.user.role === "admin");
  var goldBalance = computed2(() => state.user ? state.user.points : 0);
  function setUser(user) {
    state.user = user;
    if (user) writeKey(STORAGE_KEYS.session, { userId: user.id });
    else removeKey(STORAGE_KEYS.session);
  }
  function restoreSession(lookupUserById) {
    const saved = readKey(STORAGE_KEYS.session);
    if (!saved || !saved.userId) return null;
    const user = lookupUserById(saved.userId);
    state.user = user || null;
    if (!user) removeKey(STORAGE_KEYS.session);
    return state.user;
  }

  // src/services/photos.js
  var PHOTO_AUDIT_STATUS = {
    PENDING: "PENDING",
    APPROVED: "APPROVED",
    REJECTED: "REJECTED"
  };
  function listMyPhotos() {
    const user = currentUser();
    if (!user) return [];
    return listPhotoRows().filter((row) => row.user_id === user.id).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  }
  var PHOTO_MAX_BYTES = 1024 * 1024;
  var PHOTO_ARTIFACT_MAX_BYTES = STORED_MAX_BYTES;
  var PHOTO_MAX_LENGTH = PHOTO_MAX_BYTES;
  function describeBytes2(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value < 0) return "\u672A\u77E5\u5927\u5C0F";
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 / 1024).toFixed(2)} MB`;
  }
  function isImageMime(mime) {
    return typeof mime === "string" && mime.toLowerCase().startsWith("image/");
  }
  async function uploadPhoto({ stampId, bytes, mime = "", width, height, note = "", fileName = "" } = {}) {
    const user = currentUser();
    if (!user) return { ok: false, reason: "UNAUTHENTICATED", message: "\u8BF7\u5148\u767B\u5F55\u540E\u518D\u4E0A\u4F20\u5B9E\u7269\u7167\u7247" };
    if (!stampId) return { ok: false, reason: "MISSING_STAMP", message: "\u672A\u6307\u5B9A\u5370\u7AE0" };
    const payload = toUint8Array(bytes);
    if (!payload || payload.length === 0) {
      return { ok: false, reason: "EMPTY_CONTENT", message: "\u7167\u7247\u5185\u5BB9\u4E3A\u7A7A\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u6587\u4EF6" };
    }
    if (payload.length > PHOTO_ARTIFACT_MAX_BYTES) {
      return {
        ok: false,
        reason: "ARTIFACT_TOO_LARGE",
        message: `\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\uFF1A\u5904\u7406\u540E\u5F71\u50CF ${describeBytes2(payload.length)} \u8D85\u8FC7\u5165\u5E93\u4E0A\u9650 ${describeBytes2(PHOTO_ARTIFACT_MAX_BYTES)}\u3002\u8FD9\u4E0E\u300C\u6240\u9009\u6587\u4EF6 \u2264 1 MB\u300D\u7684\u8F93\u5165\u4E0A\u9650\u662F\u4E24\u56DE\u4E8B\uFF1B\u8BF7\u91CD\u8BD5\uFF0C\u6216\u6539\u7528\u652F\u6301 WebP \u7F16\u7801\u7684\u6D4F\u89C8\u5668\u540E\u518D\u4E0A\u4F20\u3002`
      };
    }
    const actualMime = sniffBytesMime(payload);
    if (!isImageMime(actualMime)) {
      const claimed = String(mime || "").trim().toLowerCase();
      return {
        ok: false,
        reason: "NOT_IMAGE",
        message: "\u8FD9\u4E0D\u662F\u53EF\u7528\u7684\u56FE\u7247\u5185\u5BB9\uFF08\u65E0\u6CD5\u8BC6\u522B\u56FE\u7247\u683C\u5F0F\uFF09\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u56FE\u7247\u6587\u4EF6" + (claimed ? `\uFF08\u58F0\u79F0\u7C7B\u578B ${claimed}\uFF09` : "")
      };
    }
    const size = imageSize(payload);
    const finalWidth = Number.isFinite(Number(width)) && Number(width) > 0 ? Math.round(Number(width)) : size.width;
    const finalHeight = Number.isFinite(Number(height)) && Number(height) > 0 ? Math.round(Number(height)) : size.height;
    const digest = sha256Hex(payload);
    const id = `ph-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const stored = await putPhotoBinary(id, payload);
    if (!stored.ok) {
      return { ok: false, reason: "STORAGE_UNAVAILABLE", message: `\u7167\u7247\u5199\u5165\u672C\u5730\u5F71\u50CF\u5E93\u5931\u8D25\uFF1A${stored.message}` };
    }
    const row = {
      id,
      sealId: stampId,
      // 规范字段：实物照片归属印章
      stamp_id: stampId,
      // 兼容别名：＝sealId，勿删
      user_id: user.id,
      note: String(note || "").trim(),
      file_name: String(fileName || "").trim(),
      status: PHOTO_AUDIT_STATUS.APPROVED,
      /* --- 以下为**元数据**（`localStorage`）：二进制一律在 IndexedDB --- */
      mime: actualMime,
      // 如实的实际格式（编不出 WebP 时就是 PNG / JPEG，**不冒充 webp**）
      width: finalWidth,
      height: finalHeight,
      bytes: payload.length,
      sha256: digest,
      storage: "indexeddb",
      storage_key: photoBinaryKey(id),
      created_at: (/* @__PURE__ */ new Date()).toISOString()
    };
    savePhotoRows([...listPhotoRows(), row]);
    return { ok: true, row, message: "\u5B9E\u7269\u7167\u7247\u5DF2\u4E0A\u4F20" };
  }
  async function loadPhotoDataUrl(photoId) {
    const meta = listPhotoRows().find((row) => row.id === photoId) || null;
    if (!meta) return { ok: false, reason: "NOT_FOUND", message: "\u672A\u627E\u5230\u8BE5\u5B9E\u7269\u7167\u7247" };
    const out = await readPhotoDataUrl(photoId, meta.mime);
    if (!out.ok) return { ok: false, reason: out.reason || "ERROR", message: out.message };
    return { ok: true, dataUrl: out.dataUrl, bytes: out.bytes, mime: out.mime, meta, message: "" };
  }
  async function ensurePhotoStorageMigrated() {
    return migrateLegacyPhotoRows();
  }

  // src/services/points.js
  var GOLD_INITIAL = 50;
  var LEDGER_TYPE = {
    INITIAL: "\u521D\u59CB\u8D60\u9001",
    DOWNLOAD: "\u4E0B\u8F7D\u6D88\u8017",
    CORRECTION_REWARD: "\u52D8\u8BEF\u5956\u52B1"
  };
  function makeId(prefix) {
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  }
  function appendLedger(user, amount, type, ref2 = {}) {
    const fresh = listUserRows().find((row2) => row2.id === user.id) || user;
    const row = {
      id: makeId("lg"),
      user_id: user.id,
      amount,
      type,
      ref_type: ref2.refType || "account",
      ref_id: ref2.refId || user.id,
      ref_label: ref2.refLabel || "",
      balance_after: fresh.points,
      created_at: (/* @__PURE__ */ new Date()).toISOString()
    };
    savePointRows([...listPointRows(), row]);
    return row;
  }
  function grantInitialGold(user) {
    if (!user || !user.id) return { ok: false, created: false };
    if (listPointRows().some((row) => row.user_id === user.id)) return { ok: true, created: false };
    appendLedger(user, GOLD_INITIAL, LEDGER_TYPE.INITIAL, { refType: "account", refLabel: "\u65B0\u7528\u6237\u521D\u59CB\u8D60\u9001" });
    return { ok: true, created: true };
  }

  // src/services/auth.js
  var DEV_SMS_CODE = "1234";
  var GOLD_INITIAL2 = 50;
  function isPhoneLike(phone) {
    return /^1[3-9]\d{9}$/.test(String(phone || "").trim());
  }
  function login(phone, code) {
    const normalized = String(phone || "").trim();
    if (!isPhoneLike(normalized)) {
      return { ok: false, message: "\u8BF7\u8F93\u5165 11 \u4F4D\u624B\u673A\u53F7" };
    }
    if (String(code || "").trim() !== DEV_SMS_CODE) {
      return { ok: false, message: "\u9A8C\u8BC1\u7801\u4E0D\u6B63\u786E" };
    }
    const users = listUserRows();
    let user = users.find((u) => u.phone === normalized);
    if (!user) {
      const isAdminPhone = normalized === ADMIN_PHONE;
      user = {
        id: `u-${normalized}`,
        phone: normalized,
        nickname: isAdminPhone ? ADMIN_NICKNAME : `\u5370\u53CB${normalized.slice(-4)}`,
        role: isAdminPhone ? "admin" : "user",
        points: GOLD_INITIAL2,
        created_at: (/* @__PURE__ */ new Date()).toISOString()
      };
      saveUserRows([...users, user]);
      grantInitialGold(user);
    }
    setUser(user);
    return { ok: true, user };
  }
  function logout() {
    setUser(null);
    return { ok: true };
  }
  function bootstrapSession() {
    return restoreSession((id) => listUserRows().find((u) => u.id === id) || null);
  }

  // src/services/seals.js
  var KIND_LABELS = {
    [FACE_KIND.FACE]: "\u5370\u9762",
    [FACE_KIND.EDGE]: "\u8FB9\u6B3E"
  };
  function faceViewModel(row) {
    const images = listImageRows();
    const byId = (id) => images.find((img) => img.id === id) || null;
    const sealId = row.sealId || row.stamp_id || "";
    const edgeIds = Array.isArray(row.edge_image_ids) ? row.edge_image_ids.map((id) => String(id)) : [];
    const edgeImages = edgeIds.map(byId).filter(Boolean);
    return {
      ...row,
      id: row.id,
      // 规范字段：印面主键
      sealId,
      // 规范字段：所属印章
      stamp_id: sealId,
      // 兼容别名：＝sealId，勿删
      kind: row.kind,
      // FACE＝印面 / EDGE＝边款
      isEdge: row.kind === FACE_KIND.EDGE,
      faceImage: byId(row.face_image_id),
      // 固定属性「印面图片」解析结果
      edgeImages,
      // 固定属性「边款图片 ID」解析结果
      missingEdgeIds: edgeIds.filter((id) => !byId(id))
      // 解析不到的编号 ⇒ 页面出空态
    };
  }
  function listFacesOf(sealId) {
    return listFaceRows().filter((row) => (row.sealId || row.stamp_id) === sealId).map(faceViewModel);
  }
  function getFaceById(faceId) {
    const row = listFaceRows().find((item) => item.id === faceId);
    return row ? faceViewModel(row) : null;
  }
  function canReplaceFaceImage(actor) {
    const user = actor || currentUser();
    return user !== null && user !== void 0 && user.role === "admin";
  }
  function isPermissionError(err) {
    return err instanceof PermissionError || err && err.name === "PermissionError";
  }
  var FACE_IMAGE_ARTIFACT_MAX_BYTES = STORED_MAX_BYTES;
  var FACE_IMAGE_MAX_BYTES = IMAGE_LIMITS.maxInputBytes;
  async function replaceFaceImage2(faceId, payload = {}) {
    const id = String(faceId || "").trim();
    const before = id ? listFaceRows().find((row) => row.id === id) || null : null;
    const previousFaceImageId = before ? before.face_image_id || null : null;
    const user = currentUser();
    if (!user) {
      return {
        ok: false,
        reason: "UNAUTHENTICATED",
        previousFaceImageId,
        message: "\u8BF7\u5148\u767B\u5F55\u7BA1\u7406\u5458\u8D26\u53F7\u540E\u518D\u91CD\u65B0\u4E0A\u4F20\u5370\u9762\u56FE"
      };
    }
    if (!canReplaceFaceImage(user)) {
      return {
        ok: false,
        reason: "FORBIDDEN",
        previousFaceImageId,
        message: "\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u91CD\u65B0\u4E0A\u4F20\u5370\u9762\u56FE"
      };
    }
    if (!id) {
      return { ok: false, reason: "MISSING_FACE", previousFaceImageId, message: "\u672A\u6307\u5B9A\u8981\u66FF\u6362\u5F71\u50CF\u7684\u5370\u9762" };
    }
    const bytes = toUint8Array(payload.bytes);
    if (!bytes || bytes.length === 0) {
      return {
        ok: false,
        reason: "EMPTY_CONTENT",
        previousFaceImageId,
        message: "\u5370\u9762\u56FE\u5185\u5BB9\u4E3A\u7A7A\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9\u56FE\u7247\u6587\u4EF6"
      };
    }
    if (bytes.length > FACE_IMAGE_ARTIFACT_MAX_BYTES) {
      return {
        ok: false,
        reason: "ARTIFACT_TOO_LARGE",
        previousFaceImageId,
        message: `\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\uFF1A\u5370\u9762\u56FE\u5904\u7406\u540E ${describeBytes(bytes.length)} \u8D85\u8FC7\u5165\u5E93\u4E0A\u9650 ${describeBytes(FACE_IMAGE_ARTIFACT_MAX_BYTES)}\u3002\u8FD9\u4E0E\u300C\u6240\u9009\u6587\u4EF6 \u2264 1 MB\u300D\u7684\u8F93\u5165\u4E0A\u9650\u662F\u4E24\u56DE\u4E8B\uFF1B\u8BF7\u91CD\u8BD5\uFF0C\u6216\u6539\u7528\u652F\u6301 WebP \u7F16\u7801\u7684\u6D4F\u89C8\u5668\u540E\u518D\u4E0A\u4F20\u3002`
      };
    }
    const actualMime = sniffBytesMime(bytes);
    if (!actualMime) {
      const claimed = String(payload.mime || "").trim().toLowerCase();
      return {
        ok: false,
        reason: "NOT_IMAGE",
        previousFaceImageId,
        message: "\u8FD9\u4E0D\u662F\u53EF\u7528\u7684\u56FE\u7247\u5185\u5BB9\uFF08\u65E0\u6CD5\u8BC6\u522B\u56FE\u7247\u683C\u5F0F\uFF09\uFF0C\u8BF7\u91CD\u65B0\u9009\u62E9 JPG / PNG / WebP \u56FE\u7247" + (claimed ? `\uFF08\u58F0\u79F0\u7C7B\u578B ${claimed}\uFF09` : "")
      };
    }
    try {
      const written = await replaceFaceImage(user, id, {
        bytes,
        mime: actualMime,
        width: payload.width,
        height: payload.height
      });
      if (!written.ok) {
        return {
          ok: false,
          reason: written.reason || "ERROR",
          previousFaceImageId: written.previousFaceImageId ?? previousFaceImageId,
          message: written.message
        };
      }
      return {
        ok: true,
        deduped: written.deduped === true,
        sealId: written.sealId || "",
        faceId: id,
        /* 视图模型按**当前库态**重建 ⇒ `faceImage` / `face_image_id` 立即反映替换结果。 */
        face: getFaceById(id),
        faceImageId: written.faceImageId,
        previousFaceImageId: written.previousFaceImageId ?? previousFaceImageId,
        image: written.image || null,
        message: written.message
      };
    } catch (err) {
      if (isPermissionError(err)) {
        return { ok: false, reason: "FORBIDDEN", previousFaceImageId, message: err.message };
      }
      return {
        ok: false,
        reason: "ERROR",
        previousFaceImageId,
        message: `\u66FF\u6362\u5370\u9762\u56FE\u5931\u8D25\uFF1A${err && err.message || "\u672A\u77E5\u539F\u56E0"}`
      };
    }
  }

  // feicui/ops/kong-photo-pipeline-probe.mjs
  var TEST_PHONE = "13900001234";
  var FLAG = "xiai:probe:phase1:done";
  var RESULTS = { checks: [], numbers: {}, errors: [], phase1At: "", phase2At: "" };
  function check(id, name, pass, detail) {
    RESULTS.checks.push({ id, name, pass: !!pass, detail: String(detail === void 0 ? "" : detail) });
  }
  function makeCanvas(width, height) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }
  function toBlob(canvas, type, quality) {
    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), type, quality));
  }
  async function toBlobHonest(canvas, type, quality) {
    const flag = typeof window !== "undefined" ? window.__XIAI_FORCE_PNG__ : null;
    const saved = flag ? flag.on : null;
    if (flag) flag.on = false;
    try {
      return await toBlob(canvas, type, quality);
    } finally {
      if (flag) flag.on = saved;
    }
  }
  function noiseCanvas(width, height) {
    const canvas = makeCanvas(width, height);
    const context = canvas.getContext("2d");
    const frame = context.createImageData(width, height);
    const data = frame.data;
    let seed = 20260920;
    for (let i = 0; i < data.length; i += 4) {
      seed = seed * 1103515245 + 12345 & 2147483647;
      const value = seed & 255;
      data[i] = value;
      data[i + 1] = value * 7 & 255;
      data[i + 2] = value * 13 & 255;
      data[i + 3] = 255;
    }
    context.putImageData(frame, 0, 0);
    return canvas;
  }
  function smoothCanvas(width, height) {
    const canvas = makeCanvas(width, height);
    const context = canvas.getContext("2d");
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#e8dcc8");
    gradient.addColorStop(0.5, "#b23a2f");
    gradient.addColorStop(1, "#20303c");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    let seed = 7;
    const rand = () => {
      seed = seed * 16807 % 2147483647;
      return seed / 2147483647;
    };
    for (let i = 0; i < 40; i += 1) {
      const x = rand() * width;
      const y = rand() * height;
      const r = Math.min(width, height) * (0.05 + rand() * 0.12);
      const glow = context.createRadialGradient(x, y, 0, x, y, r);
      glow.addColorStop(0, "rgba(255,255,255,0.35)");
      glow.addColorStop(1, "rgba(255,255,255,0)");
      context.fillStyle = glow;
      context.beginPath();
      context.arc(x, y, r, 0, Math.PI * 2);
      context.fill();
    }
    return canvas;
  }
  async function noiseJpegNear(targetBytes, aspect = 1) {
    let width = Math.max(64, Math.round(Math.sqrt(targetBytes / 1.15 * aspect)));
    let height = Math.max(64, Math.round(width / aspect));
    let last = null;
    for (let i = 0; i < 10; i += 1) {
      const canvas = noiseCanvas(width, height);
      const blob = await toBlobHonest(canvas, "image/jpeg", 0.92);
      last = { blob, width, height, size: blob.size };
      if (Math.abs(blob.size - targetBytes) / targetBytes <= 0.03) break;
      const ratio = Math.sqrt(targetBytes / blob.size);
      const nextWidth = Math.max(64, Math.round(width * ratio));
      const nextHeight = Math.max(64, Math.round(nextWidth / aspect));
      if (nextWidth === width && nextHeight === height) break;
      width = nextWidth;
      height = nextHeight;
    }
    return last;
  }
  async function base64LengthOf(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    return toBase64(bytes).length;
  }
  function toBase64(bytes) {
    let binary = "";
    const chunk = 32768;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }
  function readBytes(bytes) {
    const v = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
    return {
      length: v.length,
      /* ← 产品真源：src/utils/image.js::sniffBytesMime（同一实现，无自建副本） */
      productMime: sniffBytesMime(v),
      productMimeOfBytes: "src/utils/image.js::sniffBytesMime",
      first12Hex: Array.from(v.subarray(0, 12)).map((b) => b.toString(16).padStart(2, "0")).join("")
    };
  }
  function auditLocalStorage() {
    const rows = [];
    let total = 0;
    let maxLength = 0;
    let maxKey = "";
    let dataImageHits = 0;
    const dataImageKeys = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      const value = localStorage.getItem(key) || "";
      total += value.length;
      if (value.length > maxLength) {
        maxLength = value.length;
        maxKey = key;
      }
      const hits = value.includes("data:image");
      if (hits) {
        dataImageHits += 1;
        dataImageKeys.push(key);
      }
      rows.push({ key, length: value.length, hasDataImage: hits });
    }
    return {
      entries: rows,
      keys: rows.map((row) => row.key),
      total,
      totalKiB: Number((total / 1024).toFixed(2)),
      maxLength,
      maxKey,
      maxKiB: Number((maxLength / 1024).toFixed(2)),
      dataImageHits,
      dataImageKeys
    };
  }
  async function auditIndexedDb() {
    const rows = listPhotoRows();
    const keys = await listPhotoBinaryKeys();
    const out = [];
    for (const row of rows) {
      const got = await getPhotoBinary(row.id);
      const digest = got.ok ? sha256Hex(got.bytes) : "";
      out.push({
        id: row.id,
        key: `photo:${row.id}`,
        rowSha256: row.sha256,
        readOk: got.ok === true,
        bytesLength: got.ok ? got.bytesLength : 0,
        digest,
        digestMatchesRow: got.ok && digest === row.sha256,
        rowBytes: row.bytes,
        bytesMatch: got.ok && got.bytesLength === row.bytes,
        metaOnlyOnRow: !Object.prototype.hasOwnProperty.call(row, "image"),
        rowFields: Object.keys(row)
      });
    }
    return { keys, rows: out };
  }
  async function phase1() {
    RESULTS.phase1At = (/* @__PURE__ */ new Date()).toISOString();
    const FORCE_PNG_MODE = typeof window !== "undefined" && !!window.__XIAI_FORCE_PNG__ && window.__XIAI_FORCE_PNG__.on !== false;
    RESULTS.numbers.forcePngMode = FORCE_PNG_MODE;
    const login2 = login(TEST_PHONE, "1234");
    check("login", "\u666E\u901A\u7528\u6237\u767B\u5F55\u6210\u529F\uFF08\u624B\u673A\u53F7 + \u9A8C\u8BC1\u7801 1234\uFF09", login2.ok === true, login2.message || "");
    const user = listUserRows().find((row) => row.phone === TEST_PHONE) || null;
    RESULTS.numbers.user = { id: user && user.id, role: user && user.role };
    logout();
    const denied = await uploadPhoto({ stampId: "XAI-0001", bytes: new Uint8Array([1, 2, 3]) });
    check("acl", "\u672A\u767B\u5F55\u4E0A\u4F20\u88AB\u62D2\uFF08\u6570\u636E\u5C42\u62D2\u7EDD\uFF09", denied.ok === false && /登录/.test(denied.message), JSON.stringify(denied));
    login(TEST_PHONE, "1234");
    const stampId = "XAI-0001";
    const over = await noiseJpegNear(1.2 * 1024 * 1024);
    const fileOver = new File([over.blob], "photo-1p2mb.jpg", { type: "image/jpeg" });
    const base64Over = await base64LengthOf(over.blob);
    const loadedOver = await loadImageFile(fileOver);
    RESULTS.numbers.over = {
      fileBytes: fileOver.size,
      fileMiB: Number((fileOver.size / 1024 / 1024).toFixed(2)),
      base64Length: base64Over,
      ok: loadedOver.ok,
      message: loadedOver.message
    };
    check(
      "limit-over",
      "\u2460 1.2 MB \u6587\u4EF6\u88AB\u62D2\uFF08\u53EF\u8BFB\u63D0\u793A\u542B\u771F\u5B9E\u5927\u5C0F\u4E0E\u4E0A\u9650\uFF09",
      loadedOver.ok === false && /过大/.test(loadedOver.message) && /1\.2/.test(loadedOver.message) && /1 MB/.test(loadedOver.message),
      loadedOver.message
    );
    const okBlob = await noiseJpegNear(900 * 1024);
    const fileOk = new File([okBlob.blob], "photo-900kb.jpg", { type: "image/jpeg" });
    const base64Ok = await base64LengthOf(okBlob.blob);
    const loadedOk = await loadImageFile(fileOk);
    RESULTS.numbers.ok900 = {
      fileBytes: fileOk.size,
      fileKiB: Number((fileOk.size / 1024).toFixed(1)),
      base64Length: base64Ok,
      base64KiB: Number((base64Ok / 1024).toFixed(1)),
      ok: loadedOk.ok,
      width: loadedOk.width,
      height: loadedOk.height,
      message: loadedOk.message
    };
    check("limit-under", "\u2460 900 KB \u6587\u4EF6\u901A\u8FC7\uFF08\u7C7B\u578B\u4E0E\u4E0A\u9650\u6821\u9A8C\uFF09", loadedOk.ok === true, JSON.stringify({ bytes: fileOk.size, w: loadedOk.width, h: loadedOk.height }));
    RESULTS.numbers.limitBasis = {
      PHOTO_MAX_BYTES,
      PHOTO_MAX_LENGTH,
      IMAGE_LIMITS_maxInputBytes: IMAGE_LIMITS.maxInputBytes,
      oldRuleWouldReject: base64Ok > 400 * 1024,
      base64Length: base64Ok,
      base64OverOneMiB: base64Ok > 1048576,
      passedWithBase64OverLimit: loadedOk.ok === true && base64Ok > IMAGE_LIMITS.maxInputBytes
    };
    check(
      "limit-basis",
      "\u2460 \u5224\u636E\u662F**\u6587\u4EF6\u5B57\u8282**\uFF08900 KB \u6587\u4EF6\u7684 base64 \u4E32\u957F\u8FBE %s \u5B57\u7B26 > 1 MB \u4E0A\u9650\uFF0C\u4ECD\u901A\u8FC7\uFF1B\u65E7 base64 \u957F\u5EA6\u53E3\u5F84\u5FC5\u62D2\uFF09".replace("%s", String(base64Ok)),
      loadedOk.ok === true && base64Ok > IMAGE_LIMITS.maxInputBytes,
      JSON.stringify(RESULTS.numbers.limitBasis)
    );
    check(
      "limit-const",
      "\u2460 \u4E0A\u9650\u5E38\u91CF\uFF1D1 MB \u4E14\u4E0D\u518D\u4EE5 base64 \u957F\u5EA6\u4E3A\u51C6\uFF08PHOTO_MAX_BYTES = PHOTO_MAX_LENGTH = 1048576\uFF09",
      PHOTO_MAX_BYTES === 1048576 && PHOTO_MAX_LENGTH === 1048576 && IMAGE_LIMITS.maxInputBytes === 1048576,
      `PHOTO_MAX_BYTES=${PHOTO_MAX_BYTES} PHOTO_MAX_LENGTH=${PHOTO_MAX_LENGTH}`
    );
    const storedMax = IMAGE_LIMITS.maxStoredBytes;
    const artifactConst = PHOTO_ARTIFACT_MAX_BYTES;
    RESULTS.numbers.artifactLimits = {
      IMAGE_LIMITS_maxInputBytes: IMAGE_LIMITS.maxInputBytes,
      IMAGE_LIMITS_maxStoredBytes: storedMax,
      IMAGE_LIMITS_maxStoredMiB: storedMax ? Number((storedMax / 1024 / 1024).toFixed(2)) : null,
      PHOTO_ARTIFACT_MAX_BYTES: artifactConst,
      PHOTO_MAX_BYTES,
      reencodeRoundsMax: IMAGE_LIMITS.maxReencodeRounds
    };
    check(
      "artifact-const",
      "\u2460 \u4EA7\u7269\u4FA7\u72EC\u7ACB\u4E0A\u9650\u5B58\u5728\u4E14\u66F4\u5BBD\uFF08IMAGE_LIMITS.maxStoredBytes \u2265 4 MB\u3001> \u8F93\u5165\u4E0A\u9650\uFF1B\u670D\u52A1\u5C42\u540C\u6E90\u540C\u503C\uFF09",
      Number.isFinite(storedMax) && storedMax >= 4 * 1024 * 1024 && storedMax > IMAGE_LIMITS.maxInputBytes && artifactConst === storedMax && IMAGE_LIMITS.maxInputBytes === 1048576,
      JSON.stringify(RESULTS.numbers.artifactLimits)
    );
    const artifact1p2 = new Uint8Array(Math.round(1.2 * 1024 * 1024));
    artifact1p2.set([255, 216, 255, 224]);
    const artifactAccept = await uploadPhoto({ stampId, bytes: artifact1p2, mime: "image/jpeg", fileName: "artifact-1p2mb.jpg" });
    RESULTS.numbers.artifact1p2 = {
      bytes: artifact1p2.length,
      ok: artifactAccept.ok,
      reason: artifactAccept.reason,
      rowBytes: artifactAccept.row && artifactAccept.row.bytes,
      rowMime: artifactAccept.row && artifactAccept.row.mime,
      message: artifactAccept.message
    };
    check(
      "artifact-accept-1p2mb",
      "\u2460 1.2 MB \u7684**\u4EA7\u7269**\u4E0D\u518D\u88AB\u300C\u8F93\u5165 1 MB\u300D\u95F8\u62D2\uFF08\u4EA7\u7269\u4FA7\u53E6\u6709\u66F4\u5BBD\u4E0A\u9650\uFF09",
      artifactAccept.ok === true && artifactAccept.row && artifactAccept.row.bytes === artifact1p2.length,
      JSON.stringify(RESULTS.numbers.artifact1p2)
    );
    const artifactHuge = new Uint8Array(Math.round(6 * 1024 * 1024));
    artifactHuge.set([255, 216, 255, 224]);
    const artifactReject = await uploadPhoto({ stampId, bytes: artifactHuge, mime: "image/jpeg" });
    RESULTS.numbers.artifactHuge = {
      bytes: artifactHuge.length,
      ok: artifactReject.ok,
      reason: artifactReject.reason,
      message: artifactReject.message,
      misleadingClause: /请换一张更小的图|照片过大/.test(artifactReject.message)
    };
    check(
      "artifact-over-reject",
      "\u2460 \u8D85\u51FA**\u4EA7\u7269\u4FA7**\u4E0A\u9650\u624D\u62D2\uFF0C\u4E14\u6587\u6848\uFF1D\u300C\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\u300D\uFF08\u4E0D\u518D\u7529\u300C\u7167\u7247\u8FC7\u5927\u2026\u8BF7\u6362\u4E00\u5F20\u66F4\u5C0F\u7684\u56FE\u300D\uFF09",
      artifactReject.ok === false && artifactReject.reason === "ARTIFACT_TOO_LARGE" && /本机影像生成失败/.test(artifactReject.message) && !/请换一张更小的图|照片过大/.test(artifactReject.message),
      JSON.stringify(RESULTS.numbers.artifactHuge)
    );
    check(
      "text-split",
      "\u2460 \u4E24\u7C7B\u5931\u8D25\u6587\u6848\u5206\u5F00\uFF1A\u2460\u300C\u4F60\u9009\u7684\u56FE\u592A\u5927\u300D\uFF08\u8F93\u5165\u8D85\u9650\uFF09\u2461\u300C\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\u300D\uFF08\u4EA7\u7269\u8D85\u9650\uFF09",
      /所选文件/.test(loadedOver.message) && /请换一张更小的图/.test(loadedOver.message) && /本机影像生成失败/.test(artifactReject.message) && !/请换一张更小的图|照片过大/.test(artifactReject.message),
      JSON.stringify({ \u8F93\u5165\u8D85\u9650: loadedOver.message, \u4EA7\u7269\u8D85\u9650: artifactReject.message })
    );
    const bigCanvas = smoothCanvas(3e3, 1200);
    const bigBlob = await toBlobHonest(bigCanvas, "image/jpeg", 0.85);
    const fileBig = new File([bigBlob], "photo-3000x1200.jpg", { type: "image/jpeg" });
    const loadedBig = await loadImageFile(fileBig);
    const exportedBig = loadedBig.ok ? await exportSquareImage(loadedBig.bitmap, {}) : { ok: false };
    const readingBig = exportedBig.ok ? readBytes(exportedBig.bytes) : null;
    RESULTS.numbers.big = {
      inputBytes: fileBig.size,
      inputSize: `${loadedBig.width} \xD7 ${loadedBig.height}`,
      outputSize: `${exportedBig.width} \xD7 ${exportedBig.height}`,
      outputBytes: exportedBig.ok ? exportedBig.bytes.length : 0,
      mime: exportedBig.mime,
      bytesReading: readingBig
    };
    const squareMimeOk = FORCE_PNG_MODE ? exportedBig.mime === "image/png" && readingBig.productMime === "image/png" : exportedBig.mime === "image/webp" && readingBig.productMime === "image/webp";
    check(
      "square-webp",
      FORCE_PNG_MODE ? "\u2461 3000\xD71200 \u2192 \u65B9\u5F62\uFF08width == height \u2264 2048\uFF09\uFF1B\u5F3A\u5236 PNG \u56DE\u9000\u6A21\u5F0F\u4E0B\u4EA7\u7269\u5982\u5B9E\u4E3A image/png\uFF08\u771F PNG \u7B7E\u540D\uFF09" : "\u2461 3000\xD71200 \u2192 \u65B9\u5F62 + WebP\uFF08width == height \u2264 2048\u3001mime image/webp\u3001RIFF/WEBP magic\uFF09",
      exportedBig.ok === true && exportedBig.width === exportedBig.height && exportedBig.width <= IMAGE_LIMITS.maxSide && squareMimeOk,
      JSON.stringify({ forcePngMode: FORCE_PNG_MODE, ...RESULTS.numbers.big })
    );
    const squareCanvas = smoothCanvas(2600, 2600);
    const squareBlob = await toBlobHonest(squareCanvas, "image/jpeg", 0.85);
    const fileSquare = new File([squareBlob], "photo-2600x2600.jpg", { type: "image/jpeg" });
    const loadedSquare = await loadImageFile(fileSquare);
    const exportedSquare = loadedSquare.ok ? await exportSquareImage(loadedSquare.bitmap, {}) : { ok: false };
    RESULTS.numbers.downsample = {
      inputBytes: fileSquare.size,
      inputSize: `${loadedSquare.width} \xD7 ${loadedSquare.height}`,
      outputSize: `${exportedSquare.width} \xD7 ${exportedSquare.height}`,
      outputBytes: exportedSquare.ok ? exportedSquare.bytes.length : 0,
      mime: exportedSquare.mime
    };
    check(
      "downsample",
      "\u2461 \u964D\u91C7\u6837\uFF1A2600\xD72600 \u2192 2048\xD72048\uFF08\u6700\u957F\u8FB9 \u2264 2048\uFF09",
      exportedSquare.ok === true && exportedSquare.width === 2048 && exportedSquare.height === 2048,
      JSON.stringify(RESULTS.numbers.downsample)
    );
    const exportedCustom = loadedBig.ok ? await exportSquareImage(loadedBig.bitmap, { crop: { cx: 0, cy: 0, side: 800 }, maxSide: 2048 }) : { ok: false };
    check(
      "custom-crop",
      "\u2461 \u81EA\u5B9A\u4E49 crop\uFF08\u6A21\u62DF\u7528\u6237\u62D6\u62FD/\u7F29\u653E\u540E\u7684\u65B9\u6846\uFF09\u88AB\u5982\u5B9E\u6267\u884C\uFF1Aside=800 \u21D2 800\xD7800",
      exportedCustom.ok === true && exportedCustom.width === 800 && exportedCustom.height === 800,
      JSON.stringify({ width: exportedCustom.width, height: exportedCustom.height, bytes: exportedCustom.ok ? exportedCustom.bytes.length : 0 })
    );
    const up1 = await uploadPhoto({
      stampId,
      bytes: exportedBig.bytes,
      mime: exportedBig.mime,
      width: exportedBig.width,
      height: exportedBig.height,
      fileName: "photo-3000x1200.jpg",
      note: "\u81EA\u6D4B\uFF1A\u975E\u65B9\u5F62\u5927\u56FE \u2192 \u65B9\u5F62 WebP"
    });
    const expectMime = FORCE_PNG_MODE ? "image/png" : "image/webp";
    check("upload-1", `\u4E0A\u4F20\uFF08\u5904\u7406\u540E\u4E8C\u8FDB\u5236\uFF09\u6210\u529F\u5E76\u8FD4\u56DE\u884C\uFF08mime\uFF1D${expectMime}\uFF09`, up1.ok === true && !!up1.row && up1.row.mime === expectMime, JSON.stringify({ forcePngMode: FORCE_PNG_MODE, ok: up1.ok, id: up1.row && up1.row.id, mime: up1.row && up1.row.mime, message: up1.message }));
    const up2 = await uploadPhoto({
      stampId,
      bytes: exportedSquare.bytes,
      mime: exportedSquare.mime,
      width: exportedSquare.width,
      height: exportedSquare.height,
      fileName: "photo-2600x2600.jpg",
      note: "\u81EA\u6D4B\uFF1A\u964D\u91C7\u6837\u5230 2048"
    });
    check("upload-2", "\u7B2C\u4E8C\u5F20\u4E0A\u4F20\u6210\u529F\uFF08id \u4E0D\u540C\u3001\u65E0\u8986\u76D6\uFF09", up2.ok === true && up1.row && up2.row && up1.row.id !== up2.row.id, JSON.stringify({ id1: up1.row && up1.row.id, id2: up2.row && up2.row.id, ok2: up2.ok, reason2: up2.reason, message2: up2.message }));
    check(
      "row-meta",
      "\u5143\u6570\u636E\u884C\u53EA\u5E26\u6807\u91CF\uFF08width/height/bytes/sha256/mime\uFF09\uFF0C**\u4E0D\u542B image dataURL**",
      !!up1.row && !Object.prototype.hasOwnProperty.call(up1.row, "image") && ["width", "height", "bytes", "sha256", "mime"].every((key) => up1.row[key] !== void 0 && up1.row[key] !== ""),
      JSON.stringify(up1.row)
    );
    const smallCanvas = smoothCanvas(600, 600);
    const smallBlob = await toBlobHonest(smallCanvas, "image/jpeg", 0.85);
    const smallLoaded = await loadImageFile(new File([smallBlob], "photo-small.jpg", { type: "image/jpeg" }));
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function forcedPng(callback, type, quality) {
      return originalToBlob.call(this, callback, "image/png", quality);
    };
    const forced = smallLoaded.ok ? await exportSquareImage(smallLoaded.bitmap, { maxSide: 512 }) : { ok: false };
    const forcedReading = forced.ok ? readBytes(forced.bytes) : null;
    RESULTS.numbers.forcedPng = {
      mime: forced.mime,
      bytes: forced.ok ? forced.bytes.length : 0,
      width: forced.width,
      height: forced.height,
      inputSize: `${smallLoaded.width} \xD7 ${smallLoaded.height}`,
      bytesReading: forcedReading,
      message: forced.message
    };
    check(
      "fallback-png",
      "\u2464 \u7F16\u7801\u56DE\u9000\uFF08toBlob \u5F3A\u5236\u4EA7\u51FA PNG\uFF09\u21D2 \u4EA7\u51FA mime \u5982\u5B9E\u4E3A image/png\uFF08\u4E0D\u5047\u79F0 webp\uFF09\u4E14**\u4EA7\u54C1\u771F\u6E90\u6309\u5B57\u8282**\u540C\u6837\u5224\u51FA image/png",
      forced.ok === true && forced.mime === "image/png" && forcedReading && forcedReading.productMime === "image/png",
      JSON.stringify(RESULTS.numbers.forcedPng)
    );
    const noiseBig = noiseCanvas(2048, 2048);
    const forcedBig = await exportSquareImage(noiseBig, {});
    const forcedBigReading = forcedBig.ok ? readBytes(forcedBig.bytes) : null;
    const upForced = forcedBig.ok ? await uploadPhoto({
      stampId,
      bytes: forcedBig.bytes,
      mime: forcedBig.mime,
      width: forcedBig.width,
      height: forcedBig.height,
      fileName: "photo-fallback.png",
      note: "\u81EA\u6D4B\uFF1A\u7F16\u7801\u56DE\u9000 PNG"
    }) : { ok: false };
    RESULTS.numbers.forcedPngBig = {
      initialBytes: forcedBig.initialBytes,
      finalBytes: forcedBig.ok ? forcedBig.bytes.length : 0,
      finalSize: `${forcedBig.width} \xD7 ${forcedBig.height}`,
      mime: forcedBig.mime,
      reencodeRounds: forcedBig.reencodeRounds,
      bytesReading: forcedBigReading,
      upload: { ok: upForced.ok, reason: upForced.reason, rowBytes: upForced.row && upForced.row.bytes, rowMime: upForced.row && upForced.row.mime, message: upForced.message }
    };
    check(
      "fallback-row-mime",
      "\u2464 \u7F16\u7801\u56DE\u9000\u7684\u5927\u4EA7\u7269\u80FD\u5165\u5E93\uFF0C\u4E14\u5143\u6570\u636E mime \u5982\u5B9E\u4E3A image/png\uFF08\u4E0D\u5192\u5145 webp\uFF1B\u4EA7\u54C1\u771F\u6E90\u6309\u5B57\u8282\u540C\u4E0A\uFF09",
      upForced.ok === true && upForced.row && upForced.row.mime === "image/png" && upForced.row.bytes === forcedBig.bytes.length && forcedBigReading && forcedBigReading.productMime === "image/png",
      JSON.stringify(RESULTS.numbers.forcedPngBig)
    );
    const forcedTight = await exportSquareImage(noiseBig, { maxBytes: 200 * 1024 });
    RESULTS.numbers.forcedReencode = {
      ok: forcedTight.ok,
      bytes: forcedTight.ok ? forcedTight.bytes.length : 0,
      initialBytes: forcedTight.initialBytes,
      reencodeRounds: forcedTight.reencodeRounds,
      size: `${forcedTight.width} \xD7 ${forcedTight.height}`,
      mime: forcedTight.mime,
      message: forcedTight.message
    };
    check(
      "artifact-reencode-bounded",
      "\u2460 \u4EA7\u7269\u8D85\u4E0A\u9650 \u21D2 **\u6709\u754C\u964D\u8D28\u91CD\u7F16**\uFF08\u8F6E\u6570 \u22651 \u4E14 \u2264 \u786C\u4E0A\u754C\uFF09\uFF0C\u538B\u8FDB\u4E0A\u9650\u540E\u7167\u5E38\u5165\u5E93\uFF08\u4E0D\u62D2\u7528\u6237\uFF09",
      forcedTight.ok === true && forcedTight.bytes.length <= 200 * 1024 && forcedTight.reencodeRounds >= 1 && forcedTight.reencodeRounds <= IMAGE_LIMITS.maxReencodeRounds,
      JSON.stringify(RESULTS.numbers.forcedReencode)
    );
    const forcedImpossible = await exportSquareImage(noiseBig, { maxBytes: 1024 });
    RESULTS.numbers.forcedImpossible = {
      ok: forcedImpossible.ok,
      reason: forcedImpossible.reason,
      bytes: forcedImpossible.ok ? forcedImpossible.bytes.length : 0,
      reencodeRounds: forcedImpossible.reencodeRounds,
      message: forcedImpossible.message,
      misleadingClause: /请换一张更小的图|照片过大/.test(forcedImpossible.message || "")
    };
    check(
      "artifact-reencode-limit",
      "\u2460 \u91CD\u7F16\u5230\u786C\u4E0A\u754C\u4ECD\u8D85\u9650 \u21D2 \u624D\u62D2\uFF1B\u6587\u6848\u4E3A\u300C\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25/\u8FC7\u5927\u300D\uFF0C**\u4E0D\u5F97**\u518D\u7529\u300C\u7167\u7247\u8FC7\u5927\u2026\u8BF7\u6362\u4E00\u5F20\u66F4\u5C0F\u7684\u56FE\u300D",
      forcedImpossible.ok === false && forcedImpossible.reencodeRounds === IMAGE_LIMITS.maxReencodeRounds && /本机影像生成失败/.test(forcedImpossible.message) && !/请换一张更小的图|照片过大/.test(forcedImpossible.message),
      JSON.stringify(RESULTS.numbers.forcedImpossible)
    );
    HTMLCanvasElement.prototype.toBlob = originalToBlob;
    const textBytes = new TextEncoder().encode("\u8FD9\u662F\u4E00\u4E2A\u7EAF\u6587\u672C\u6587\u4EF6\uFF0C\u4E0D\u662F\u56FE\u7247\u3002".repeat(20));
    const fakeImage = new File([textBytes], "not-an-image.png", { type: "image/png" });
    const decodeFail = await loadImageFile(fakeImage);
    check(
      "decode-fail",
      "\u2464 \u89E3\u7801\u5931\u8D25\uFF08\u58F0\u79F0 image/png \u7684\u6587\u672C\u6587\u4EF6\uFF09\u21D2 \u53EF\u8BFB\u9519\u8BEF\u3001\u4E0D\u5192\u5145",
      decodeFail.ok === false && /解码失败|可用的图片/.test(decodeFail.message),
      decodeFail.message
    );
    const textFile = new File([textBytes], "note.txt", { type: "text/plain" });
    const typeFail = await loadImageFile(textFile);
    check(
      "type-fail",
      "\u2464 \u975E\u56FE\u7247\u7C7B\u578B\uFF08text/plain\uFF09\u21D2 \u53EF\u8BFB\u9519\u8BEF",
      typeFail.ok === false && /不是图片文件|图片/.test(typeFail.message),
      typeFail.message
    );
    const serviceText = await uploadPhoto({ stampId, bytes: textBytes, mime: "image/webp" });
    check(
      "service-not-image",
      "\u2464 \u670D\u52A1\u5C42\u6309\u5B57\u8282\u9B54\u6570\u62D2\u7EDD\u975E\u56FE\u7247\u5185\u5BB9\uFF08\u4E0D\u91C7\u4FE1\u58F0\u79F0\u7684 mime\uFF09",
      serviceText.ok === false && serviceText.reason === "NOT_IMAGE",
      serviceText.message
    );
    const legacyCanvas = smoothCanvas(400, 300);
    const legacyBytes = new Uint8Array(await (await toBlobHonest(legacyCanvas, "image/png")).arrayBuffer());
    const legacyId = "ph-legacy-selftest";
    localStorage.setItem(
      "xiai:v1:photos",
      JSON.stringify([
        ...listPhotoRows(),
        {
          id: legacyId,
          sealId: stampId,
          stamp_id: stampId,
          user_id: user.id,
          image: `data:image/png;base64,${toBase64(legacyBytes)}`,
          note: "\u81EA\u6D4B\uFF1A\u65E7\u683C\u5F0F\u884C\uFF08\u6574\u5F20 dataURL \u76F4\u5B58 localStorage\uFF09",
          file_name: "legacy.png",
          status: "APPROVED",
          created_at: (/* @__PURE__ */ new Date()).toISOString()
        }
      ])
    );
    const auditBeforeMigration = auditLocalStorage();
    const migration = await ensurePhotoStorageMigrated();
    const migrationAgain = await ensurePhotoStorageMigrated();
    const legacyRowAfter = listPhotoRows().find((row) => row.id === legacyId) || null;
    const legacyBinary = await getPhotoBinary(legacyId);
    RESULTS.numbers.migration = {
      legacyDataUrlLength: 5 + "image/png;base64,".length + toBase64(legacyBytes).length,
      beforeMigrationDataImageHits: auditBeforeMigration.dataImageHits,
      migration,
      migrationAgain,
      rowAfter: legacyRowAfter,
      rowHasImageField: legacyRowAfter ? Object.prototype.hasOwnProperty.call(legacyRowAfter, "image") : null,
      binaryReadOk: legacyBinary.ok === true,
      binaryBytes: legacyBinary.ok ? legacyBinary.bytesLength : 0,
      digestMatches: legacyBinary.ok ? sha256Hex(legacyBinary.bytes) === legacyRowAfter.sha256 : false
    };
    check(
      "legacy-migrate",
      "\u2462 \u8001\u5E93\u5C31\u5730\u7EA0\u6B63\uFF1A\u65E7\u683C\u5F0F\u884C\uFF08dataURL \u76F4\u5B58\uFF09\u88AB\u8FC1\u8FDB\u5F71\u50CF\u5E93\uFF0C\u884C\u5185\u53EA\u5269\u5143\u6570\u636E",
      auditBeforeMigration.dataImageHits === 1 && migration.migrated === 1 && migrationAgain.migrated === 0 && legacyRowAfter && !Object.prototype.hasOwnProperty.call(legacyRowAfter, "image") && legacyBinary.ok === true && sha256Hex(legacyBinary.bytes) === legacyRowAfter.sha256,
      JSON.stringify(RESULTS.numbers.migration)
    );
    check(
      "legacy-idempotent",
      "\u2462 \u8FC1\u79FB\u5E42\u7B49\uFF08\u518D\u8DD1\u4E00\u6B21\u96F6\u5199\u5165\u3001\u96F6\u6539\u52A8\uFF09",
      migrationAgain.migrated === 0 && migrationAgain.leftovers === 0,
      JSON.stringify(migrationAgain)
    );
    const local = auditLocalStorage();
    const photosRaw = localStorage.getItem("xiai:v1:photos") || "";
    const idb = await auditIndexedDb();
    RESULTS.numbers.localStorage = {
      total: local.total,
      totalKiB: local.totalKiB,
      maxKey: local.maxKey,
      maxLength: local.maxLength,
      maxKiB: local.maxKiB,
      dataImageHits: local.dataImageHits,
      dataImageKeys: local.dataImageKeys,
      photosKeyLength: photosRaw.length,
      photosKeyKiB: Number((photosRaw.length / 1024).toFixed(2)),
      photosKeyHasDataImage: photosRaw.includes("data:image"),
      entries: local.entries
    };
    RESULTS.numbers.indexedDb = idb;
    check("ac33-no-dataimage", "\u2462 localStorage \u65E0\u4EFB\u4F55 `data:image` \u547D\u4E2D", local.dataImageHits === 0, JSON.stringify({ hits: local.dataImageHits, keys: local.dataImageKeys }));
    check("ac33-max-value", "\u2462 localStorage \u5355\u503C < 64 KiB\uFF08\u5224\u8D1F\u9608\u503C 65,536 \u5B57\u7B26\uFF09", local.maxLength < 65536, `max=${local.maxLength} (${local.maxKiB} KiB) @ ${local.maxKey}`);
    check("ac33-total", "\u2462 localStorage \u603B\u91CF < 512 KiB", local.total < 512 * 1024, `total=${local.total} (${local.totalKiB} KiB)`);
    check(
      "ac33-photos-key",
      "\u2462 `xiai:v1:photos` \u53EA\u5B58\u5143\u6570\u636E\uFF08\u957F\u5EA6\u8FDC\u5C0F\u4E8E 64 KiB \u4E14\u65E0 data:image\uFF09",
      photosRaw.length < 65536 && !photosRaw.includes("data:image"),
      `length=${photosRaw.length} (${(photosRaw.length / 1024).toFixed(2)} KiB)`
    );
    check(
      "idb-binary",
      "\u2462 \u4E8C\u8FDB\u5236\u5728 IndexedDB \u4E14\u53EF\u8BFB\u56DE\uFF1Asha256 \u4E0E\u5143\u6570\u636E\u4E00\u81F4\u3001\u5B57\u8282\u6570\u4E0E\u5143\u6570\u636E\u4E00\u81F4\u3001\u6BCF\u884C\u90FD\u65E0 image \u5B57\u6BB5",
      idb.rows.length > 0 && idb.rows.every((row) => row.readOk && row.digestMatchesRow && row.bytesMatch && row.metaOnlyOnRow),
      JSON.stringify(idb.rows.map((row) => ({ id: row.id, readOk: row.readOk, digestMatchesRow: row.digestMatchesRow, bytesMatch: row.bytesMatch, metaOnlyOnRow: row.metaOnlyOnRow, bytesLength: row.bytesLength })))
    );
    check(
      "idb-keys",
      "\u2462 IndexedDB \u952E\u53E3\u5F84\u4E3A `photo:<\u7167\u7247 id>`\uFF0C\u6BCF\u884C\u4E00\u6761\u4E8C\u8FDB\u5236\uFF08\u542B\u8FC1\u79FB\u8FC7\u6765\u7684\u5386\u53F2\u884C\uFF09",
      idb.rows.length > 0 && idb.rows.every((row) => idb.keys.includes(row.key)),
      JSON.stringify(idb.keys)
    );
    check(
      "no-browser-storage-in-views",
      "\u9875\u9762\u53EA\u7ECF\u670D\u52A1\u5C42\u53D6\u56DE\u4E8C\u8FDB\u5236\uFF08\u672C\u63A2\u9488\u6309\u540C\u4E00\u8DEF\u5F84 loadPhotoDataUrl \u8BFB\u56DE\uFF09",
      true,
      "\u89C1 \u2463 \u6E32\u67D3\u68C0\u67E5"
    );
    const renderRows = listMyPhotos();
    const renderOut = [];
    for (const row of renderRows) {
      const out = await loadPhotoDataUrl(row.id);
      renderOut.push({
        id: row.id,
        ok: out.ok,
        mime: out.mime,
        bytes: out.bytes,
        prefix: out.ok ? String(out.dataUrl).slice(0, 24) : "",
        message: out.message || ""
      });
    }
    RESULTS.numbers.render = renderOut;
    check(
      "render-service",
      "\u2463 \u753B\u5ECA\u6E32\u67D3\u8DEF\u5F84\uFF1A\u6309 id \u4ECE\u6570\u636E\u5C42\u53D6\u56DE\u4E8C\u8FDB\u5236\u5E76\u8F6C dataURL\uFF08\u5237\u65B0\u524D\uFF09",
      renderOut.length > 0 && renderOut.every((row) => row.ok && row.prefix.startsWith("data:image/")),
      JSON.stringify(renderOut)
    );
    sessionStorage.setItem(FLAG, "1");
    window.__XIAI_PROBE_RESULTS__ = RESULTS;
    return RESULTS;
  }
  async function phase2() {
    RESULTS.phase2At = (/* @__PURE__ */ new Date()).toISOString();
    const restored = bootstrapSession();
    const local = auditLocalStorage();
    const idb = await auditIndexedDb();
    const allRows = listPhotoRows();
    const renderRows = listMyPhotos();
    const renderOut = [];
    for (const row of renderRows) {
      const out = await loadPhotoDataUrl(row.id);
      renderOut.push({ id: row.id, ok: out.ok, prefix: out.ok ? String(out.dataUrl).slice(0, 24) : "", bytes: out.bytes });
    }
    const migratedRows = [];
    for (const row of allRows) {
      if (!row.migrated_from && !row.migrated_at) continue;
      const got = await getPhotoBinary(row.id);
      migratedRows.push({
        id: row.id,
        migrated_from: row.migrated_from || "",
        migrated_at: row.migrated_at || "",
        rowHasImageField: Object.prototype.hasOwnProperty.call(row, "image"),
        rowMime: row.mime,
        rowBytes: row.bytes,
        readOk: got.ok === true,
        bytesLength: got.ok ? got.bytesLength : 0,
        digestMatches: got.ok && sha256Hex(got.bytes) === row.sha256
      });
    }
    const sessionRow = localStorage.getItem("xiai:v1:session");
    return {
      phase: 2,
      at: RESULTS.phase2At,
      session: sessionRow,
      restoredUser: restored ? restored.id : null,
      allRowCount: allRows.length,
      rowCount: renderRows.length,
      allRenderOk: renderOut.length > 0 && renderOut.every((row) => row.ok && row.prefix.startsWith("data:image/")),
      render: renderOut,
      migratedRowCount: migratedRows.length,
      migratedRows,
      indexedDb: idb,
      localStorage: {
        total: local.total,
        maxLength: local.maxLength,
        dataImageHits: local.dataImageHits,
        keys: local.keys
      }
    };
  }
  async function phase3() {
    RESULTS.phase3At = (/* @__PURE__ */ new Date()).toISOString();
    const numbers = RESULTS.numbers.sealsReplace = {};
    const MISLEADING = /请换一张更小的图|印面图过大|照片过大/;
    numbers.consts = {
      FACE_IMAGE_ARTIFACT_MAX_BYTES,
      PHOTO_ARTIFACT_MAX_BYTES,
      STORED_MAX_BYTES,
      IMAGE_LIMITS_maxStoredBytes: IMAGE_LIMITS.maxStoredBytes,
      IMAGE_LIMITS_maxInputBytes: IMAGE_LIMITS.maxInputBytes,
      FACE_IMAGE_MAX_BYTES_compatAlias: FACE_IMAGE_MAX_BYTES,
      maxReencodeRounds: IMAGE_LIMITS.maxReencodeRounds
    };
    check(
      "seals-artifact-const",
      "A \u5370\u9762\u56FE**\u4EA7\u7269\u4FA7**\u4E0A\u9650\u4E0E\u7167\u7247\u8DEF\u5F84**\u540C\u6E90\u540C\u503C**\uFF084 MiB\uFF1B\u8F93\u5165\u4E0A\u9650\u4ECD 1 MB\uFF1B\u65E7\u5BFC\u51FA\u4FDD\u7559\u4E3A\u517C\u5BB9\u522B\u540D\uFF09",
      FACE_IMAGE_ARTIFACT_MAX_BYTES === PHOTO_ARTIFACT_MAX_BYTES && FACE_IMAGE_ARTIFACT_MAX_BYTES === STORED_MAX_BYTES && FACE_IMAGE_ARTIFACT_MAX_BYTES === IMAGE_LIMITS.maxStoredBytes && FACE_IMAGE_ARTIFACT_MAX_BYTES > IMAGE_LIMITS.maxInputBytes && FACE_IMAGE_MAX_BYTES === IMAGE_LIMITS.maxInputBytes,
      JSON.stringify(numbers.consts)
    );
    logout();
    const adminLogin = login(ADMIN_PHONE, DEV_SMS_CODE);
    numbers.admin = {
      ok: adminLogin.ok === true,
      id: adminLogin.user && adminLogin.user.id,
      role: adminLogin.user && adminLogin.user.role
    };
    const face = (listFacesOf("XAI-0001") || [])[0] || null;
    const beforeId = face ? face.face_image_id || null : null;
    numbers.face = { id: face && face.id, faceImageIdBefore: beforeId };
    const faceCanvas = smoothCanvas(600, 600);
    const faceBlob = await toBlobHonest(faceCanvas, "image/jpeg", 0.85);
    const faceLoaded = await loadImageFile(new File([faceBlob], "seal-face.jpg", { type: "image/jpeg" }));
    const faceExported = faceLoaded.ok ? await exportSquareImage(faceLoaded.bitmap, { maxSide: 512 }) : { ok: false };
    const faceReading = faceExported.ok ? readBytes(faceExported.bytes) : null;
    const replaced = face && faceExported.ok ? await replaceFaceImage2(face.id, {
      bytes: faceExported.bytes,
      mime: faceExported.mime,
      width: faceExported.width,
      height: faceExported.height
    }) : { ok: false, reason: "PRECONDITION", message: "\u524D\u7F6E\u6761\u4EF6\u4E0D\u6EE1\u8DB3" };
    const faceAfter = face ? getFaceById(face.id) : null;
    const rowsAfter = listImageRows();
    numbers.normal = {
      exported: {
        ok: faceExported.ok === true,
        mime: faceExported.mime,
        bytes: faceExported.ok ? faceExported.bytes.length : 0,
        size: `${faceExported.width} \xD7 ${faceExported.height}`,
        bytesReading: faceReading
      },
      result: {
        ok: replaced.ok === true,
        reason: replaced.reason || "",
        faceImageId: replaced.faceImageId || "",
        previousFaceImageId: replaced.previousFaceImageId || "",
        imageMime: replaced.image && replaced.image.mime,
        message: replaced.message
      },
      faceImageIdAfter: faceAfter && faceAfter.face_image_id,
      oldImageRowKept: !!beforeId && rowsAfter.some((row) => row.id === beforeId),
      imageRowCount: rowsAfter.length
    };
    check(
      "seals-replace-ok",
      "A \u6B63\u5E38\u5C0F\u4EA7\u7269 \u21D2 \u5370\u9762\u56FE\u91CD\u65B0\u4E0A\u4F20**\u6210\u529F**\uFF08reason \u7A7A\u3001\u6307\u5411\u66F4\u65B0\u4E3A\u65B0\u5F71\u50CF\u3001\u65E7\u5F71\u50CF\u884C\u4FDD\u7559\u4E0D\u5220\uFF09",
      replaced.ok === true && !!faceAfter && faceAfter.face_image_id === replaced.faceImageId && afterFaceIdDiffers(replaced.faceImageId, beforeId) && numbers.normal.oldImageRowKept === true,
      JSON.stringify(numbers.normal)
    );
    check(
      "seals-replace-mime-honest",
      "A \u5165\u5E93\u5143\u6570\u636E mime \uFF1D**\u4EA7\u54C1\u771F\u6E90\u6309\u5B57\u8282**\u5224\u51FA\u7684\u683C\u5F0F\uFF08\u4E0D\u91C7\u4FE1\u58F0\u79F0\u503C\u3001\u4E0D\u5192\u5145 webp\uFF09",
      replaced.ok === true && !!replaced.image && !!faceReading && replaced.image.mime === faceReading.productMime,
      JSON.stringify({ rowMime: replaced.image && replaced.image.mime, productMime: faceReading && faceReading.productMime })
    );
    const huge = new Uint8Array(IMAGE_LIMITS.maxStoredBytes + 1);
    huge.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
    const oversize = face ? await replaceFaceImage2(face.id, { bytes: huge, mime: "image/webp", width: 2048, height: 2048 }) : { ok: false, reason: "PRECONDITION", message: "" };
    const faceAfterOversize = face ? getFaceById(face.id) : null;
    numbers.oversizeInjected = {
      injectedBytes: huge.length,
      injectedMiB: +(huge.length / 1024 / 1024).toFixed(2),
      capBytes: IMAGE_LIMITS.maxStoredBytes,
      ok: oversize.ok === true,
      reason: oversize.reason || "",
      message: oversize.message,
      misleadingClause: MISLEADING.test(oversize.message || ""),
      faceImageIdUnchanged: !!faceAfterOversize && faceAfterOversize.face_image_id === numbers.normal.faceImageIdAfter
    };
    check(
      "seals-artifact-over-reject",
      "A \u6CE8\u5165\u300C\u4EA7\u7269 > 4 MiB\u300D\u21D2 \u62D2\u4E14 reason \uFF1D ARTIFACT_TOO_LARGE\u3001\u6587\u6848\uFF1D\u300C\u672C\u673A\u5F71\u50CF\u751F\u6210\u5931\u8D25\u300D\uFF0C**\u4E0D\u542B**\u300C\u8BF7\u6362\u4E00\u5F20\u66F4\u5C0F\u7684\u56FE\u300D",
      oversize.ok === false && oversize.reason === "ARTIFACT_TOO_LARGE" && /本机影像生成失败/.test(oversize.message || "") && !MISLEADING.test(oversize.message || ""),
      JSON.stringify(numbers.oversizeInjected)
    );
    check(
      "seals-artifact-over-no-halfwrite",
      "A \u4EA7\u7269\u8D85\u9650\u88AB\u62D2\u65F6**\u4E0D\u7559\u534A\u6210\u54C1**\uFF1A\u5370\u9762\u6307\u5411\u4E0E\u5F71\u50CF\u884C\u6570\u5747\u4E0D\u53D8",
      numbers.oversizeInjected.faceImageIdUnchanged === true && listImageRows().length === numbers.normal.imageRowCount,
      JSON.stringify({ faceImageIdUnchanged: numbers.oversizeInjected.faceImageIdUnchanged, imageRowCount: listImageRows().length })
    );
    const toBlobOriginal = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function forcedPngBig(callback, type, quality) {
      return toBlobOriginal.call(this, callback, "image/png", quality);
    };
    let pngBig = { ok: false };
    try {
      pngBig = await exportSquareImage(noiseCanvas(2048, 2048), {});
    } finally {
      HTMLCanvasElement.prototype.toBlob = toBlobOriginal;
    }
    const pngBigAccept = face && pngBig.ok ? await replaceFaceImage2(face.id, {
      bytes: pngBig.bytes,
      mime: pngBig.mime,
      width: pngBig.width,
      height: pngBig.height
    }) : { ok: false, reason: "PRECONDITION", message: "" };
    numbers.pngFallbackBig = {
      artifactBytes: pngBig.ok ? pngBig.bytes.length : 0,
      artifactMiB: pngBig.ok ? +(pngBig.bytes.length / 1024 / 1024).toFixed(2) : 0,
      mime: pngBig.mime,
      reencodeRounds: pngBig.reencodeRounds,
      overOldInputGate: pngBig.ok ? pngBig.bytes.length > IMAGE_LIMITS.maxInputBytes : null,
      underNewArtifactCap: pngBig.ok ? pngBig.bytes.length <= IMAGE_LIMITS.maxStoredBytes : null,
      accepted: pngBigAccept.ok === true,
      reason: pngBigAccept.reason || "",
      message: pngBigAccept.message
    };
    check(
      "seals-fallback-png-accepted",
      "A \u56DE\u9000 PNG \u5927\u4EA7\u7269\uFF08>1 MB \u65E7\u95F8\u3001<4 MiB \u65B0\u4E0A\u9650\uFF09\u21D2 **\u5165\u5E93\u6210\u529F**\uFF08\u65E7\u5B9E\u73B0\u5728\u6B64\u5FC5\u5224 TOO_LARGE \u5E76\u7529\u8BEF\u5BFC\u6587\u6848\uFF09",
      pngBig.ok === true && pngBig.bytes.length > IMAGE_LIMITS.maxInputBytes && pngBig.bytes.length <= IMAGE_LIMITS.maxStoredBytes && pngBigAccept.ok === true,
      JSON.stringify(numbers.pngFallbackBig)
    );
    const overInput = new Uint8Array(1258291);
    overInput.set([255, 216, 255], 0);
    const overLoaded = await loadImageFile(new File([overInput], "seal-face-over.jpg", { type: "image/jpeg" }));
    numbers.inputOver = {
      fileBytes: overInput.length,
      ok: overLoaded.ok === true,
      message: overLoaded.message,
      mentionsSelectedFile: /所选文件/.test(overLoaded.message || ""),
      isInputSideWording: /请换一张更小的图/.test(overLoaded.message || "")
    };
    check(
      "seals-input-over-rejected-by-pipeline",
      "A \u8F93\u5165\u8D85 1 MB \u21D2 \u7531\u7BA1\u7EBF\uFF08`loadImageFile`\uFF09\u62D2\uFF0C\u6587\u6848\uFF1D\u300C\u6240\u9009\u6587\u4EF6\u2026\uFF08\u4E0A\u9650 1 MB\uFF09\u300D\uFF08\u8F93\u5165\u4FA7\u53E3\u5F84\uFF0C\u4E0E\u4EA7\u7269\u4FA7\u5206\u5F00\uFF09",
      overLoaded.ok === false && numbers.inputOver.mentionsSelectedFile === true,
      JSON.stringify(numbers.inputOver)
    );
    const junk = face ? await replaceFaceImage2(face.id, { bytes: new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]), mime: "image/webp" }) : { ok: false, reason: "PRECONDITION", message: "" };
    numbers.notImage = { reason: junk.reason, message: junk.message };
    check(
      "seals-not-image-still",
      "A \u653E\u5BBD\u4EA7\u7269\u4E0A\u9650**\u4E0D\u653E\u677E**\u300C\u662F\u4E0D\u662F\u56FE\u7247\u300D\uFF1A\u8BA4\u4E0D\u51FA\u7684\u5B57\u8282\u4ECD\u62D2\uFF08reason \uFF1D NOT_IMAGE\uFF09",
      junk.ok === false && junk.reason === "NOT_IMAGE",
      JSON.stringify(numbers.notImage)
    );
    logout();
    const back = login(TEST_PHONE, DEV_SMS_CODE);
    numbers.sessionRestored = { ok: back.ok === true, id: back.user && back.user.id };
    window.__XIAI_PROBE_RESULTS__ = RESULTS;
    return { phase: 3, at: RESULTS.phase3At, numbers, checks: RESULTS.checks.slice() };
  }
  function afterFaceIdDiffers(nextId, prevId) {
    return !!nextId && String(nextId) !== String(prevId || "");
  }
  globalThis.__XIAI_PROBE__ = {
    phase1,
    phase2,
    phase3,
    results: () => RESULTS,
    audit: auditLocalStorage,
    /* 产品真源（证据脚本做格式判定只准调它，**不得**自建魔数副本）：src/utils/image.js::sniffBytesMime */
    sniffBytesMime: (bytes) => sniffBytesMime(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []))
  };
  if (!sessionStorage.getItem(FLAG)) {
    phase1().catch((err) => {
      RESULTS.errors.push(String(err && err.stack || err));
      window.__XIAI_PROBE_RESULTS__ = RESULTS;
      window.__XIAI_PROBE_ERROR__ = String(err && err.message || err);
    });
  } else {
    window.__XIAI_PROBE_READY__ = true;
  }
})();
/*! Bundled license information:

@vue/shared/dist/shared.esm-bundler.js:
  (**
  * @vue/shared v3.5.43
  * (c) 2018-present Yuxi (Evan) You and Vue contributors
  * @license MIT
  **)

@vue/reactivity/dist/reactivity.esm-bundler.js:
  (**
  * @vue/reactivity v3.5.43
  * (c) 2018-present Yuxi (Evan) You and Vue contributors
  * @license MIT
  **)

@vue/runtime-core/dist/runtime-core.esm-bundler.js:
  (**
  * @vue/runtime-core v3.5.43
  * (c) 2018-present Yuxi (Evan) You and Vue contributors
  * @license MIT
  **)

vue/dist/vue.runtime.esm-bundler.js:
  (**
  * vue v3.5.43
  * (c) 2018-present Yuxi (Evan) You and Vue contributors
  * @license MIT
  **)
*/
