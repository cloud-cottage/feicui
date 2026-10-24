// 图片高清化（成品化）端点的取数层：`POST /api/tools/enhance`（multipart/form-data）。
//
// 为什么**不**复用 `client.js` 的 `request()`：那是按 JSON 设计的（自设 Content-Type、
// `JSON.stringify(body)`）；本端点要发**二进制 multipart**（浏览器自己带 boundary，
// 手写 Content-Type 反而会让后端解不出分段）。故本文件用 `fetch` + `FormData` 直发，
// 但**错误归一化与 client.js 完全同口径**：
//   ① 网络层失败 ⇒ 抛 `BackendUnreachableError`（页面据此显示「后端未启动」，横幅同步）；
//   ② dev 代理 503 `backend_unreachable` ⇒ 同上；
//   ③ 后端业务错误（400/422/500）⇒ **原样**放进返回值（`body.error` / `body.reason`），不吞不猜。
import { API_BASE } from '@/config/env'
import { BackendUnreachableError } from './client'

export const ENHANCE_PATH = `${API_BASE}/tools/enhance`

// 契约常量（与后端 `server/app/routers/tools.py` 的 ENHANCE_* 同名同值）
export const ENHANCE_WIDTH_DEFAULT = 1200
export const ENHANCE_WIDTH_MIN = 200
export const ENHANCE_WIDTH_MAX = 4000
export const ENHANCE_BACKGROUNDS = ['paper', 'plain_white']

/**
 * @param {File|Blob} file 单张图片（PIL 可解码即可）
 * @param {{width?: number, background?: 'paper'|'plain_white'}} [opts]
 * @returns {Promise<{ok:boolean, status:number, body:any, raw:string, url:string}>}
 * @throws {BackendUnreachableError} 仅在「连不上后端」时抛
 */
export async function enhanceImage(file, { width = ENHANCE_WIDTH_DEFAULT, background = 'paper' } = {}) {
  const form = new FormData()
  form.append('image', file, file.name || 'upload.png')
  form.append('width', String(width))
  form.append('background', String(background))

  let res
  let raw = ''
  try {
    // 不设 Content-Type：交给浏览器生成 `multipart/form-data; boundary=…`
    res = await fetch(ENHANCE_PATH, { method: 'POST', body: form })
    raw = await res.text()
  } catch (e) {
    throw new BackendUnreachableError(String((e && e.message) || e))
  }

  let body = null
  if (raw) {
    try {
      body = JSON.parse(raw)
    } catch {
      body = null // 非 JSON（如代理错误页）⇒ 页面按 raw 原文展示
    }
  }

  if (res.status === 503 && body && body.error === 'backend_unreachable') {
    // dev 代理层信号（非 feicui API 码族）。见 README §3。
    throw new BackendUnreachableError(body.code || null)
  }

  return { ok: res.ok, status: res.status, body, raw, url: ENHANCE_PATH }
}

/** base64（无 data: 前缀）→ Blob（下载 / 预览都走它，避免把 1.9 MB 字符串塞进 data: URL） */
export function base64ToBlob(b64, mime = 'image/png') {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}
