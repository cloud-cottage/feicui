// 显式 dev fixture（**默认关闭**：FIXTURE_ENABLED 为 false 时本文件永不生效）。
// 用途：仅离线自测 UI 骨架。启用后页面顶部显示醒目「DEV FIXTURE」横幅，
// 且每一条数据都带 _source:'fixture'。**不得**作为任何验收依据（README §2.2）。
const JOBS = {
  'fixture-job-0001': {
    job_id: 'fixture-job-0001',
    state: 'RUNNING',
    total_pages: 544,
    done_pages: 136,
    failed_pages: [],
    cursor: { chunk_lo: 128, chunk_hi: 136 },
    counters: { detected: 402, inserted: 400, updated: 2, skipped: 0, ocr_empty: 398 },
    started_at: '2026-09-20T11:00:00+08:00',
    updated_at: '2026-09-20T11:12:30+08:00',
    _source: 'fixture',
    pdf_path: 'fixture/示例-古玺汇编.pdf',
  },
}

export function getFixture(method, path, query) {
  if (method === 'POST' && path === '/jobs') {
    return {
      status: 201,
      body: {
        job_id: 'fixture-job-0001',
        state: 'QUEUED',
        total_pages: 544,
        created_at: '2026-09-20T11:00:00+08:00',
        _source: 'fixture',
      },
    }
  }
  if (method === 'GET' && path === '/jobs') {
    return { status: 200, body: { items: Object.values(JOBS), _source: 'fixture' } }
  }
  const m = /^\/jobs\/([^/]+)$/.exec(path)
  if (method === 'GET' && m) {
    const job = JOBS[decodeURIComponent(m[1])]
    return job
      ? { status: 200, body: job }
      : { status: 404, body: { detail: 'fixture 内无该 job_id' } }
  }
  const ms = /^\/jobs\/([^/]+)\/stamps$/.exec(path)
  if (method === 'GET' && ms) {
    const jobId = decodeURIComponent(ms[1])
    const page = Number((query && query.page) || 1)
    const limit = Number((query && query.limit) || 20)
    const all = Array.from({ length: Math.min(jobId === 'fixture-job-0001' ? 43 : 0, 1000) }, (_, i) => ({
      pdf_name: 'fixture/示例-古玺汇编.pdf',
      page: Math.floor(i / 3) + 1,
      idx: (i % 3) + 1,
      text: i % 5 === 0 ? '示例释文' : null,
      img_path: `output/faces/fixture/p${String(Math.floor(i / 3) + 1).padStart(4, '0')}_${String((i % 3) + 1).padStart(2, '0')}.webp`,
      x1: 100 + i,
      y1: 200 + i,
      x2: 300 + i,
      y2: 400 + i,
      _source: 'fixture',
    }))
    const start = (page - 1) * limit
    const items = all.slice(start, start + limit)
    const hasMore = start + limit < all.length
    return {
      status: 200,
      body: {
        items,
        page,
        limit,
        total: all.length,
        has_more: hasMore,
        next_cursor: hasMore ? String(start + limit) : null,
        _source: 'fixture',
      },
    }
  }
  const mm = /^\/jobs\/([^/]+)\/missing$/.exec(path)
  if (method === 'GET' && mm) {
    const kind = (query && query.kind) || 'image'
    const items =
      kind === 'text'
        ? [
            {
              pdf_name: 'fixture/示例-古玺汇编.pdf',
              page: 1,
              idx: 1,
              reason: 'text_empty',
              _source: 'fixture',
            },
          ]
        : []
    return { status: 200, body: { kind, count: items.length, items, _source: 'fixture' } }
  }
  return null
}
