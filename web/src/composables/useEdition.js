// 版本（edition）后缀判定 —— v1.41 关键设计：同一套 `web/` 代码部署两处
//   ① feicui-local-private（创始人私有版）：`web/`(:5195) ＋ `server/`(:5196) 本地跑
//      ⇒ document.title 与顶栏 brand 均带「 · 本地服务私有版」后缀；
//   ② feicui-web（线上公网版）：Vercel 公网域名 ⇒ 一律无后缀。
// 判定按 **hostname 运行时判断**（spec §0.5.4 v1.41：local-dist / local-private 各带
// 自己后缀、feicui-web 无后缀）。`editionSuffix()` 为**纯函数**（无 DOM 依赖、可单测，
// 见 `web/scripts/edition.test.mjs`）；本文件不引任何依赖。

// 展示名全串（不含后缀）＝ §0.5.2 V-1 统一口径（逐字，不得自换）
export const BASE_TITLE = '「斐萃」玺印解析任务台'

// feicui-local-private 后缀（间隔号沿用全站「 · 」口径）
export const EDITION_LOCAL_PRIVATE = ' · 本地服务私有版'

/**
 * hostname ⇒ 版本后缀（纯函数）。
 * 本地判定族（命中 ⇒ 带后缀）：`localhost` / `*.localhost` / `127.0.0.1` / `::1`（IPv6 环回）/
 * `*.local`（mDNS 本机名）。其余（公网域名，如 `yinyuan2026.vercel.app`）⇒ ''（无后缀）。
 * 大小写不敏感；容忍 IPv6 字面量方括号（`[::1]`）与首尾空白。
 * @param {string|null|undefined} hostname
 * @returns {string} ' · 本地服务私有版' 或 ''
 */
export function editionSuffix(hostname) {
  if (typeof hostname !== 'string') return ''
  const h = hostname.trim().toLowerCase().replace(/^\[|\]$/g, '')
  if (!h) return ''
  if (h === 'localhost' || h.endsWith('.localhost')) return EDITION_LOCAL_PRIVATE
  if (h === '127.0.0.1' || h === '::1') return EDITION_LOCAL_PRIVATE
  if (h.endsWith('.local')) return EDITION_LOCAL_PRIVATE
  return ''
}

/**
 * 组合式：运行时取当前 hostname 的后缀与全串标题（组件里一次解构使用）。
 * 仅在浏览器环境读 `window.location.hostname`（非浏览器 ⇒ 无后缀，便于 SSR / 单测兜底）。
 */
export function useEdition() {
  const host =
    typeof window !== 'undefined' && window.location ? window.location.hostname : ''
  const suffix = editionSuffix(host)
  return { hostname: host, suffix, fullTitle: BASE_TITLE + suffix }
}
