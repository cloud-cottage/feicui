// 页级「生成 HighRes」（整页 dpi 参数化大图）—— **路径常量与口径一处收口**（页面不得硬编码）。
//
//   GET  /api/jobs/{job_id}/pages/{page}/highres           ⇒ 估读 + 存在性（不渲染）
//   POST /api/jobs/{job_id}/pages/{page}/highres?force=…   ⇒ 生成（**页级**，幂等）
//
// 口径（Kevin 2026-10-16）：整页渲染 dpi **缺省 1200**（2400 保留为可选）；**只做页级**；
//   **禁无限制整本生成**（整本不可行：1200dpi 48bit 整页 ≈475 MB deflate ⇒ 851 页 ≈ 404 GB / ≈6.4 h）。
// 纪律：
//   ① `{page}` **1-based**；查询参数白名单只有 `dpi`（{1200,2400}）与 `force`（仅 POST）；
//   ② 失败**必须可见**：非 200 一律把后端真实码族回给页面（不做占位、不静默）；
//   ③ 幂等：产物已在盘 ⇒ 后端不重写并回 `written:false / exists:true`；要重出必须显式 `force`；
//   ④ 只读须知：GET 会起一次性子进程读页几何（≈1–3 s）；POST 是长跑（1200dpi 单页 ≈27 s、2400dpi ≈108 s）。
import { API_BASE } from '@/config/env'

/** 路径模板（前端唯一来源） */
export const HIGHRES_PATH_TEMPLATE = '/api/jobs/{job_id}/pages/{page}/highres'

/** `dpi` 白名单与默认（与后端 `app/highres.py` 同源；非白名单 ⇒ 后端 400 BAD_PARAM） */
export const HIGHRES_DPI_WHITELIST = [1200, 2400]
export const HIGHRES_DPI_DEFAULT = 1200

/** 口径文案（页面直接展示；**必须可见**，含「整本禁止」的算账） */
export const HIGHRES_SCOPE_NOTE = '页级生成：一次一页'
export const HIGHRES_WHOLE_BOOK_NOTE =
  '整本生成已禁用 —— 1200dpi 48bit 整页未压缩 8500×12236×6 B = 624 MB（deflate ≈475 MB）' +
  '⇒ 851 页 ≈ 404 GB / 单页 ≈27 s ⇒ ≈6.4 h'

/** 后端错误面 → 人读解释（**只解释、不改写**；未知码原样回吐） */
export const HIGHRES_ERROR_TEXT = {
  BAD_PARAM: '参数非法（page 须为 1-based 正整数；dpi 须在 {1200,2400} 内）',
  JOB_NOT_FOUND: 'job 不存在',
  PDF_MISSING: 'jobs.pdf_path 不在盘上（老 job 的输入文件已不存在）',
  PAGE_OUT_OF_PDF: 'page 超出 PDF 实际页数',
  PDF_NO_IMAGE: '该页没有内嵌扫描图（非纯图版页）',
  DISK_INSUFFICIENT: '磁盘空闲空间不足（容量闸：需 ≥ 预估体积 × 1.5）',
  RUNNER_PYTHON_MISSING: 'worker 解释器（feicui/venv/bin/python）不存在',
  RUNNER_TIMEOUT: 'worker 子进程超时（单页 1200dpi ≈27 s / 2400dpi ≈108 s；超时上限 900 s）',
  RUNNER_EXIT_NONZERO: 'worker 子进程非零退出',
  RUNNER_NO_OUTPUT: 'worker 子进程未输出标记行',
  RUNNER_BAD_OUTPUT: 'worker 输出不可解析',
  RENDER_FAILED: '渲染失败',
}

export function highresErrorCode(body) {
  if (!body || typeof body !== 'object') return null
  if (typeof body.error === 'string' && body.error) return body.error
  const d = body.detail
  if (d && typeof d === 'object' && typeof d.error === 'string' && d.error) return d.error
  return null
}

export function highresErrorText(code) {
  if (!code) return ''
  return HIGHRES_ERROR_TEXT[code] || code
}

export function highresErrorDetail(body) {
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

export function highresUrl(jobId, page, dpi = HIGHRES_DPI_DEFAULT) {
  const d = dpi === undefined || dpi === null || dpi === '' ? HIGHRES_DPI_DEFAULT : Number(dpi)
  return (
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/pages/${encodeURIComponent(page)}` +
    `/highres?dpi=${encodeURIComponent(String(d))}`
  )
}

function _netFail(e) {
  return { state: 'unknown', status: 0, body: null, raw: '', code: null, detail: String((e && e.message) || e) }
}

async function _request(url, method) {
  let res
  let raw = ''
  try {
    res = await fetch(url, { method })
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
  if (res.ok) {
    return { state: 'ok', status: res.status, url, body, raw, code: null, detail: '' }
  }
  return {
    state: res.status === 400 ? 'bad-param' : res.status === 404 ? 'not-found' : 'error',
    status: res.status,
    url,
    body,
    raw,
    code: highresErrorCode(body),
    detail: highresErrorDetail(body),
  }
}

/** GET：估读（目标像素 / 预估体积 / 预估耗时 / 是否已在盘）。**不起渲染**。 */
export function fetchHighresStatus(jobId, page, dpi = HIGHRES_DPI_DEFAULT) {
  return _request(highresUrl(jobId, page, dpi), 'GET')
}

/** POST：真的生成（长跑）。`force=true` 才会覆盖既有产物。 */
export function generateHighres(jobId, page, dpi = HIGHRES_DPI_DEFAULT, force = false) {
  const url = `${highresUrl(jobId, page, dpi)}&force=${force ? 'true' : 'false'}`
  return _request(url, 'POST')
}

export function formatBytes(n) {
  const v = Number(n)
  if (!Number.isFinite(v) || v < 0) return '—'
  if (v >= 2 ** 30) return `${(v / 2 ** 30).toFixed(3)} GiB`
  if (v >= 2 ** 20) return `${(v / 2 ** 20).toFixed(1)} MiB`
  if (v >= 2 ** 10) return `${(v / 2 ** 10).toFixed(1)} KiB`
  return `${v} B`
}

export function formatSeconds(s) {
  const v = Number(s)
  if (!Number.isFinite(v) || v < 0) return '—'
  if (v < 60) return `${v.toFixed(1)} s`
  const m = Math.floor(v / 60)
  return `${m} min ${(v - m * 60).toFixed(0)} s`
}

/** 预估行（页面直接显示；字段缺一个就显示「—」，不臆造） */
export function estimateText(est) {
  if (!est || typeof est !== 'object') return '—'
  const px = Array.isArray(est.out_px) ? `${est.out_px[0]}×${est.out_px[1]}px` : '—'
  return (
    `预估 ${formatBytes(est.expected_bytes)} / ${formatSeconds(est.expected_seconds)}` +
    ` · ${px} · 48bit（Deflate+Predictor2）`
  )
}

/** 整本算账（后端给的数；没有则回退到本地口径常量，**标注为口径值**） */
export function wholeBookText(est) {
  const wb = est && typeof est === 'object' ? est.whole_book_refusal : null
  if (wb && Number.isFinite(Number(wb.gib))) {
    return `整本 ${wb.pages} 页 ≈ ${Number(wb.gib).toFixed(1)} GiB / ≈${Number(wb.hours).toFixed(1)} h —— 已禁用`
  }
  return HIGHRES_WHOLE_BOOK_NOTE
}
