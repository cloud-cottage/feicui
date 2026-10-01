(() => {
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

  // feicui/ops/kong-image-truth-bridge.mjs
  globalThis.__XIAI_IMG_TRUTH__ = {
    source: "src/utils/image.js::sniffBytesMime",
    note: "\u8BC1\u636E\u811A\u672C\u505A\u683C\u5F0F\u5224\u5B9A\u53EA\u51C6\u8C03\u8FD9\u91CC\uFF08\u4EA7\u54C1\u771F\u6E90\uFF09\uFF0C\u4E0D\u5F97\u81EA\u5EFA\u9B54\u6570\u526F\u672C",
    sniffBytesMime: (bytes) => sniffBytesMime(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []))
  };
})();
