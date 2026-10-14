// feicui API 契约调用层 —— 逐条对应 feicui/docs/feicui.spec.md §3.1。
// 本文件**只做形状转发与形状校验**，不含业务真值、不做任何派生/估算。
import { request } from './client'

// ── E1  POST /api/jobs  建 job（spec §3.1 E1）
// 请求形状：{pdf_path, page_range?:[from,to], chunk_size?, rerun?:bool}
// 响应形状：201 {job_id, state, total_pages, created_at}
//          相同 pdf_path 已存在活跃 job ⇒ 409 + 既有 job_id（**不得**静默起第二个同书 job，S-5）
export function createJob(payload) {
  return request('/jobs', { method: 'POST', body: payload })
}

// ── E2  GET /api/jobs/{job_id}  查进度（真实进度，S-1）
// 响应形状：{job_id, state, total_pages, done_pages, failed_pages[],
//           cursor:{chunk_lo,chunk_hi},
//           counters:{detected,inserted,updated,skipped,ocr_empty}, started_at, updated_at}
export function getJob(jobId) {
  return request(`/jobs/${encodeURIComponent(jobId)}`)
}

// ── 列表：**spec §3 未定义** GET /api/jobs（见 README §4 G-2）。
// 本函数只是「试探性调用」，后端可完全不实现；404/405/501 一律由页面按
// 「后端尚未提供该接口」处理，并另列浏览器本地记录，不混淆来源。
export function listJobs() {
  return request('/jobs')
}

// ── E3  GET /api/jobs/{job_id}/stamps  分页取结果
// 入参 ?page=&limit=&cursor=；出参 = 6 字段信封 {items, page, limit, total, has_more, next_cursor}
export function listStamps(jobId, { page, limit, cursor } = {}) {
  return request(`/jobs/${encodeURIComponent(jobId)}/stamps`, { query: { page, limit, cursor } })
}

// ── E5  GET /api/jobs/{job_id}/missing  缺失清单（影像 / 释文）
// 出参 {kind, count, items[{pdf_name,page,idx,img_path?,reason}]}
export function listMissing(jobId, kind) {
  return request(`/jobs/${encodeURIComponent(jobId)}/missing`, { query: { kind } })
}

// ── inbox 清理策略（**additive**，R41）────────────────────────────────────────
// 口径真源 docs/inbox-gc-draft-v0.1.md：**默认 dry-run**、两段式、**永不自动删**。
// GET /api/jobs/inbox/summary —— 只读 plan（用量 / 将回收 / 豁免清单；不改盘、不改库）
export function inboxSummary() {
  return request('/jobs/inbox/summary')
}

// POST /api/jobs/inbox/gc —— **默认 dry-run**；`apply=true` 才真移入 inbox/.trash/
// 出参 = 与 CLI 同形的清单（usage / collect / collect_bytes / exempt / hard_delete / …）
export function inboxGc(apply = false) {
  return request('/jobs/inbox/gc', { method: 'POST', body: { apply: !!apply } })
}

// ── 书目旗标表（**additive**，2026-10；规范未定义 ⇒ 同 E8 先例登记为规范缺口）
// GET /api/jobs/book-flags → {books: {<pdf_name>: <print_size_1to1: bool>}}
// 真源 config/book_dir_keys.json；前端打开表单时按书名**默认勾选**【印刷尺寸即实物尺寸】。
export function bookFlags() {
  return request('/jobs/book-flags')
}

// ─────────────────────────────────────────────────────────────────────────────
// 形状校验：只报「与 spec 写死的形状不符」，**不**替后端补值
// ─────────────────────────────────────────────────────────────────────────────

/** E3 信封校验（spec §3.2 S-3：6 字段；items 不得为裸数组；has_more 与 next_cursor 须一致） */
export function checkE3Envelope(body) {
  const problems = []
  if (Array.isArray(body)) {
    return { ok: false, problems: ['items 为裸数组 —— S-3 明文判负形态（须为 6 字段信封对象）'] }
  }
  if (!body || typeof body !== 'object') {
    return { ok: false, problems: ['响应体不是对象（S-3 要求 6 字段信封对象）'] }
  }
  const required = ['items', 'page', 'limit', 'total', 'has_more', 'next_cursor']
  for (const k of required) {
    if (!(k in body)) problems.push(`缺字段 ${k}`)
  }
  if ('items' in body && !Array.isArray(body.items)) problems.push('items 不是数组')
  if ('has_more' in body && typeof body.has_more !== 'boolean') problems.push('has_more 不是布尔')
  if ('has_more' in body && 'next_cursor' in body) {
    const hasMore = body.has_more === true
    const hasCursor = body.next_cursor !== null && body.next_cursor !== undefined
    if (hasMore !== hasCursor) {
      problems.push(
        `has_more=${String(body.has_more)} 与 next_cursor=${JSON.stringify(body.next_cursor)} 互斥一致性不成立（S-3 判负形态）`
      )
    }
  }
  const extra = Object.keys(body).filter((k) => !required.includes(k) && !k.startsWith('_'))
  return { ok: problems.length === 0, problems, extraKeys: extra }
}

/** E2 形状提示：**只提示缺字段**，缺失时页面显示 `—`，**不用 0 或估算值顶替** */
export function checkE2Shape(body) {
  const notes = []
  if (!body || typeof body !== 'object') return { ok: false, notes: ['响应体不是对象'] }
  for (const k of ['job_id', 'state', 'total_pages', 'done_pages', 'failed_pages', 'cursor', 'counters']) {
    if (!(k in body)) notes.push(`缺字段 ${k}`)
  }
  if ('failed_pages' in body && !Array.isArray(body.failed_pages)) notes.push('failed_pages 不是数组')
  return { ok: notes.length === 0, notes }
}

/** E5 形状提示 */
export function checkE5Shape(body) {
  const notes = []
  if (!body || typeof body !== 'object') return { ok: false, notes: ['响应体不是对象'] }
  for (const k of ['kind', 'count', 'items']) {
    if (!(k in body)) notes.push(`缺字段 ${k}`)
  }
  if ('items' in body && !Array.isArray(body.items)) notes.push('items 不是数组')
  return { ok: notes.length === 0, notes }
}

// ─────────────────────────────────────────────────────────────────────────────
// E1 的 409 处理（spec 只写「409 + 既有 job_id」，**未定 body 形状** —— README §4 G-3）
// ─────────────────────────────────────────────────────────────────────────────
/** 启发式抽取既有 job_id；抽不到就返回 null（**不猜、不造**），页面只展示原始 body */
export function extractExistingJobId(body) {
  if (!body || typeof body !== 'object') return null
  const candidates = [
    body.job_id,
    body.existing_job_id,
    body.existingJobId,
    body.detail && typeof body.detail === 'object' ? body.detail.job_id : undefined,
    body.detail && typeof body.detail === 'object' ? body.detail.existing_job_id : undefined,
  ]
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim()
  }
  // detail 为字符串时，尝试从中认出形如 job_id 的片段（仅在能明确匹配时）
  if (typeof body.detail === 'string') {
    const m = /(?:job_id|jobId)\s*[:=]\s*"?([A-Za-z0-9._:-]+)"?/.exec(body.detail)
    if (m) return m[1]
  }
  return null
}
