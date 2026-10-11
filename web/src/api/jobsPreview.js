// E9 / E10「文档预览」（印谱解析线内）—— **路径常量一处收口**（页面 / 组件不得硬编码这两个路径）。
//
// 口径真源：`feicui/docs/page-preview-draft-v0.1.md` §2.1 / §2.6（编号 E9 / E10 为**建议**编号，
// 终裁归 Jing；本文件的路径与字段按该件逐字）。
//
//   E9  GET /api/jobs/{job_id}/pages/{page}/preview.png   ⇒ 整页渲染（PNG 二进制）
//   E10 GET /api/jobs/{job_id}/pages/{page}/boxes         ⇒ 该页检测框（JSON，现场检测）
//
// 纪律（写死在此，便于一处收口）：
//   ① `{page}` **1-based**、查询参数白名单**只有 `dpi`**（`{72,110,150}`，默认 **110**）；
//   ② 两个端点的 `dpi` 必须**取同一个值** —— E10 的 `render.width/height` 与 E9 那张 PNG 的像素尺寸
//      必须是**同一像素空间**，覆盖层才可能对齐（PP-3）；本模块默认两处都显式带 `?dpi=`；
//   ③ 取图失败**如实显示**真实原因码（§2.1 错误面：BAD_PARAM / JOB_NOT_FOUND / PDF_MISSING /
//      PAGE_OUT_OF_PDF / RUNNER_* / RENDER_FAILED），**绝不用占位图冒充**；
//   ④ 只读：本模块不写库、不缓存影像字节（v0.1 **不做服务端缓存**，靠浏览器 `Cache-Control: private, max-age=600`）。
import { API_BASE } from '@/config/env'
import { decodeHeaderValue } from './stampsImage' // §3.13 头值还原：复用既有实现（不复制）

export { decodeHeaderValue }

/** E9 路径模板（前端唯一来源） */
export const PREVIEW_PNG_PATH_TEMPLATE = '/api/jobs/{job_id}/pages/{page}/preview.png'
/** E10 路径模板（前端唯一来源） */
export const PREVIEW_BOXES_PATH_TEMPLATE = '/api/jobs/{job_id}/pages/{page}/boxes'

/** `dpi` 白名单（§2.6：默认 110；非白名单 ⇒ 后端 400 BAD_PARAM） */
export const PREVIEW_DPI_WHITELIST = [72, 110, 150]
export const PREVIEW_DPI_DEFAULT = 110

/** 未标定书的人读提示前缀（§2.3 ②：与后端 `notes` 里的措辞同源） */
export const UNMARKED_BOOK_NOTE_PREFIX = '本书未标定'

/** §2.1 错误面 → 人读解释（**只解释、不改写**；未知码原样回吐） */
export const PREVIEW_ERROR_TEXT = {
  BAD_PARAM: '参数非法（page 须为 1-based 正整数；dpi 须在 {72,110,150} 内）',
  JOB_NOT_FOUND: 'job 不存在',
  PDF_MISSING: 'jobs.pdf_path 不在盘上（老 job 的输入文件已不存在）',
  PAGE_OUT_OF_PDF: 'page 超出 PDF 实际页数（**只按 PDF 页数判**，job 的页区间不是硬边界）',
  RUNNER_PYTHON_MISSING: 'worker 解释器（feicui/venv/bin/python）不存在',
  RUNNER_TIMEOUT: 'worker 子进程超时（每页 20 s）',
  RUNNER_EXIT_NONZERO: 'worker 子进程非零退出',
  RUNNER_NO_OUTPUT: 'worker 子进程未输出标记行',
  RUNNER_BAD_OUTPUT: 'worker 输出不可解析',
  RENDER_FAILED: '渲染 / 编码失败',
}

function _qs(dpi) {
  const d = dpi === undefined || dpi === null || dpi === '' ? PREVIEW_DPI_DEFAULT : Number(dpi)
  return `?dpi=${encodeURIComponent(String(d))}`
}

/** E9 的取图 URL（可直接给 `<img src>`） */
export function previewPngUrl(jobId, page, dpi = PREVIEW_DPI_DEFAULT) {
  return (
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/pages/${encodeURIComponent(page)}` +
    `/preview.png${_qs(dpi)}`
  )
}

/** E10 的取框 URL */
export function previewBoxesUrl(jobId, page, dpi = PREVIEW_DPI_DEFAULT) {
  return (
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/pages/${encodeURIComponent(page)}` +
    `/boxes${_qs(dpi)}`
  )
}

/** 从错误体里取原因码（**顶层 `error` ＋ `detail`**，§2.1 形态；兼容嵌套形态，不猜） */
export function previewErrorCode(body) {
  if (!body || typeof body !== 'object') return null
  if (typeof body.error === 'string' && body.error) return body.error
  const d = body.detail
  if (d && typeof d === 'object' && typeof d.error === 'string' && d.error) return d.error
  return null
}

/** 原因码 → 人读句（未知码原样返回码本身，**不臆造解释**） */
export function previewErrorText(code) {
  if (!code) return ''
  return PREVIEW_ERROR_TEXT[code] || code
}

/** 从错误体取 `detail`（顶层字符串优先；对象则原样 JSON，不改写） */
export function previewErrorDetail(body) {
  if (!body || typeof body !== 'object') return ''
  const d = body.detail
  if (typeof d === 'string') return d
  if (d === undefined || d === null) return ''
  try {
    return JSON.stringify(d)
  } catch (e) {
    return String(d)
  }
}

function _netFail(e) {
  return { state: 'unknown', status: 0, body: null, raw: '', code: null, detail: String((e && e.message) || e) }
}

/** E10：取该页检测框（现场检测）。**不吞不猜** —— 非 200 一律把真实码族回给页面。 */
export async function fetchPreviewBoxes(jobId, page, dpi = PREVIEW_DPI_DEFAULT) {
  const url = previewBoxesUrl(jobId, page, dpi)
  let res
  let raw = ''
  try {
    res = await fetch(url, { method: 'GET' })
    raw = await res.text()
  } catch (e) {
    return { ..._netFail(e), url }
  }
  let body = null
  try {
    body = raw ? JSON.parse(raw) : null
  } catch {
    body = null
  }
  const code = previewErrorCode(body)
  if (res.ok) {
    return { state: 'ok', status: res.status, url, body, raw, code: null, detail: '' }
  }
  return {
    state: res.status === 400 ? 'bad-param' : res.status === 404 ? 'not-found' : 'error',
    status: res.status,
    url,
    body,
    raw,
    code,
    detail: previewErrorDetail(body),
  }
}

/**
 * 探一次 E9（**只在 `<img>` 报错时调用**：`<img>` 拿不到状态码 ⇒ 用一次请求取真实原因码）。
 * 200 时只读响应头（**不把 PNG 字节当数据用**，本模块不缓存影像）。
 */
export async function probePreviewPng(jobId, page, dpi = PREVIEW_DPI_DEFAULT) {
  const url = previewPngUrl(jobId, page, dpi)
  let res
  let raw = ''
  try {
    res = await fetch(url, { method: 'GET' })
    if (!res.ok) raw = await res.text()
  } catch (e) {
    return { ..._netFail(e), url }
  }
  if (res.ok) {
    return {
      state: 'ok',
      status: res.status,
      url,
      contentType: res.headers.get('content-type') || '',
      renderDpi: res.headers.get('x-feicui-render-dpi') || '',
      renderSize: res.headers.get('x-feicui-render-size') || '',
      pdfPageCount: res.headers.get('x-feicui-pdf-page-count') || '',
      pdfName: decodeHeaderValue(res.headers.get('x-feicui-pdf-name') || ''),
      code: null,
      detail: '',
    }
  }
  let body = null
  try {
    body = raw ? JSON.parse(raw) : null
  } catch {
    body = null
  }
  return {
    state: res.status === 400 ? 'bad-param' : res.status === 404 ? 'not-found' : 'error',
    status: res.status,
    url,
    body,
    raw,
    code: previewErrorCode(body),
    detail: previewErrorDetail(body),
  }
}

/**
 * 框 → **绝对定位百分比**样式（§2.4：框用覆盖层、**不烧进图**）。
 * 分母是 E10 的 `render.width/height`（与 E9 PNG 同一像素空间）；越界 / 非有限值一律夹到 [0,100]。
 * 取不到 render 尺寸 ⇒ 返回 `{}`（页面据此判定「无法叠加」，**不**用猜的分母硬画）。
 */
export function boxPercentStyle(box, render) {
  if (!box || !render) return {}
  const W = Number(render.width)
  const H = Number(render.height)
  if (!Number.isFinite(W) || !Number.isFinite(H) || W <= 0 || H <= 0) return {}
  const clamp = (v) => Math.max(0, Math.min(100, v))
  const x1 = Number(box.x1)
  const y1 = Number(box.y1)
  const x2 = Number(box.x2)
  const y2 = Number(box.y2)
  if (![x1, y1, x2, y2].every(Number.isFinite)) return {}
  return {
    left: `${clamp((x1 / W) * 100)}%`,
    top: `${clamp((y1 / H) * 100)}%`,
    width: `${clamp(((x2 - x1) / W) * 100)}%`,
    height: `${clamp(((y2 - y1) / H) * 100)}%`,
  }
}

/** 框的来源徽标三态（§2.3）：未标定的书必须在 UI 可见提示 */
export function templateSourceBadge(templateSource) {
  const s = String(templateSource || '')
  if (!s) return { text: '（后端未给 template_source）', unmarked: false, kind: 'unknown' }
  if (s === 'none') {
    return { text: `${s} —— 只出图、不给框（连内建兜底都不可用）`, unmarked: true, kind: 'none' }
  }
  if (s.startsWith('book_template:')) {
    return { text: s, unmarked: false, kind: 'book' }
  }
  if (s.startsWith('builtin_default(')) {
    return { text: s, unmarked: true, kind: 'builtin' }
  }
  return { text: s, unmarked: false, kind: 'other' }
}
