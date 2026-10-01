/**
 * 定性脚本：PNG 魔数「误判」在产品侧还是探针侧（2026-09-20 Kong）
 *
 * 输入：/tmp/kong-real.png（真 PNG，由 feicui/ops/kong_png_magic_defn.py 生成；`file` 可识别）
 * ① 调产品真源 `src/utils/image.js` 的 `sniffBytesMime`（服务层 uploadPhoto 入库判据用的就是它）
 * ② 调 `src/data/db.js` 链路上的 `sniffMime`（assetmeta.js，db.js 的第 502 行与 re-export 用它）
 * ③ 用**探针原样实现**的 `magicOf`（kong-photo-pipeline-probe.mjs 第 128–140 行逐字抄来）算 isPng
 * 跑法：node feicui/ops/kong_png_magic_defn.mjs
 */
import { readFileSync } from 'node:fs'

import { sniffBytesMime, IMAGE_LIMITS } from '../../src/utils/image.js'
import { sniffMime } from '../../src/data/assetmeta.js'

const PNG = '/tmp/kong-real.png'
const bytes = new Uint8Array(readFileSync(PNG))

/* ---- ③ 探针原样实现（逐字复制自 kong-photo-pipeline-probe.mjs:128–140）---- */
function probeMagicOf(src) {
  const v = src instanceof Uint8Array ? src : new Uint8Array(src)
  const tag = (index) => String.fromCharCode(v[index], v[index + 1], v[index + 2], v[index + 3])
  return {
    length: v.length,
    head4: tag(0),
    head12: tag(8),
    isRiff: tag(0) === 'RIFF',
    isWebp: tag(0) === 'RIFF' && tag(8) === 'WEBP',
    isPng: v[0] === 0x89 && tag(1) === 'PNG',
    first12Hex: Array.from(v.subarray(0, 12)).map((b) => b.toString(16).padStart(2, '0')).join('')
  }
}

/* ---- 参照：探针若按「读 3 字节」写，应该是这个样子 ---- */
function probeMagicOfFixed(src) {
  const v = src instanceof Uint8Array ? src : new Uint8Array(src)
  const tag3 = (i) => String.fromCharCode(v[i], v[i + 1], v[i + 2])
  return { isPng: v[0] === 0x89 && tag3(1) === 'PNG' }
}

const out = {
  sample: PNG,
  bytes: bytes.length,
  head12Hex: Array.from(bytes.subarray(0, 12)).map((b) => b.toString(16).padStart(2, '0')).join(''),
  product_sniffBytesMime_imagejs: sniffBytesMime(bytes),
  product_sniffMime_assetmeta: sniffMime(bytes),
  probe_magicOf_asis: probeMagicOf(bytes),
  probe_magicOf_if_3byte_tag: probeMagicOfFixed(bytes),
  image_limits: IMAGE_LIMITS,
  probe_tag_of_1_explained: {
    bytes_at_1_2_3_4: [bytes[1], bytes[2], bytes[3], bytes[4]],
    as_string: String.fromCharCode(bytes[1], bytes[2], bytes[3], bytes[4]),
    equals_PNG: String.fromCharCode(bytes[1], bytes[2], bytes[3], bytes[4]) === 'PNG'
  }
}
console.log(JSON.stringify(out, null, 2))
