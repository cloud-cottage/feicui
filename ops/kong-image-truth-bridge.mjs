/**
 * 玺爱 · 影像格式判定「产品真源」桥（Kong 证据脚本用，2026-09-20）
 * ----------------------------------------------------------------------------
 * 为什么存在（规范缺口③「尺子漂移」）：证据脚本**不得自建一份字节魔数判定** ——
 * 否则探针的尺子和产品不一致，就会把**真 PNG 判成非 PNG**、报出假警报
 * （CDP 侧原来那句 `isPngMagic: u8[0] === 0x89 && ...` 就是自建副本）。
 *
 * 本文件把 `src/utils/image.js` 的 `sniffBytesMime`（**产品真源，同一份实现**）
 * 由 esbuild 打进一个自包含 IIFE，挂到 `globalThis.__XIAI_IMG_TRUTH__`，
 * 供 CDP 用 `Runtime.evaluate` 注入到**任意页面**（App 页面没有探针 bundle 时也能用）。
 *
 * 构建（工程根，**不要**用全局 esbuild）：
 *   ./node_modules/.bin/esbuild feicui/ops/kong-image-truth-bridge.mjs \
 *     --bundle --format=iife --outfile=feicui/ops/kong-image-truth-bridge.js
 *
 * 本文件是**证据脚本**，不参与应用构建（不在 `src/**`），也不改任何产品文件。
 */
import { sniffBytesMime } from '../../src/utils/image.js'

globalThis.__XIAI_IMG_TRUTH__ = {
  source: 'src/utils/image.js::sniffBytesMime',
  note: '证据脚本做格式判定只准调这里（产品真源），不得自建魔数副本',
  sniffBytesMime: (bytes) => sniffBytesMime(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []))
}
