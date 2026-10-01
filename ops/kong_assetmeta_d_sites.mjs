/**
 * D 项取证（Kong，2026-09-20）：`src/data/assetmeta.js::sniffMime` 的「认不出 ⇒ 回落 image/png」
 * 在**真实调用点**上的行为读数。只读，不改任何产品文件。
 *
 * 构建 + 跑：
 *   ./node_modules/.bin/esbuild feicui/ops/kong_assetmeta_d_sites.mjs --bundle --format=esm \
 *     --platform=node --outfile=/tmp/kong_d_sites.mjs && node /tmp/kong_d_sites.mjs
 */
import { sniffMime, normalizeImagePayload, bytesToDataUrl, imageSize } from '../../src/data/assetmeta.js'

/* 一个**最小合法 PNG 头 + IHDR**（byte-exact，用来对照「认得出的字节」）。 */
const png = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, // PNG 签名
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52, // IHDR 长度 + 类型
  0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, // 宽 256 高 256
  0x08, 0x02, 0x00, 0x00, 0x00,                   // 位深/色彩/压缩/滤波/隔行
  0x00, 0x00, 0x00, 0x00                          // CRC 占位（本取样不校验）
])
/* 「认不出」的字节：既不是 PNG/JPEG/GIF/WEBP 的任何签名。 */
const junk = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b])

const out = {
  'call-site-0（真源本体）': {
    'sniffMime(png)': sniffMime(png),
    'sniffMime(junk)': sniffMime(junk),
    'imageSize(junk)': imageSize(junk)
  },
  'call-site-1 assetmeta.js:259 `normalizeImagePayload`（创建印章/印面图入库用）': {
    'normalizeImagePayload(png).mime': normalizeImagePayload(png).mime,
    'normalizeImagePayload(junk).mime': normalizeImagePayload(junk).mime,
    'normalizeImagePayload(junk).ok': normalizeImagePayload(junk).ok,
    '※ 认不出的字节被落成什么 mime': normalizeImagePayload(junk).mime
  },
  'call-site-2 db.js:502 `migrateLegacyPhotoRows`（旧行迁移）': {
    '源码形态': 'mime: row.mime || sniffMime(parsed.bytes)',
    '关键事实 1': '`parsed.mime`（dataURL 头里**真实**的 MIME）被忽略，回落是这一支唯一的 mime 来源',
    '关键事实 2': '落在 db.js（本单**禁改**清单内）',
    '认不出的字节会落成 mime': sniffMime(junk),
    '渲染侧兜底（assetmeta.js:146 bytesToDataUrl 默认参数）': bytesToDataUrl(junk, '').slice(0, 24)
  }
}
console.log(JSON.stringify(out, null, 2))
