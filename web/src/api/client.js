// 取数客户端：**所有** /api 请求都过这里，统一把两类失败归一化：
//   ① BackendUnreachableError —— 后端未启动 / dev 代理连不上（页面据此显示「后端未启动」）
//   ② 返回信封 —— 后端真实响应（含 400/404/409/422/500，原样透传给页面，**不吞不猜**）
// 本文件不含任何业务真值、不做任何进度推算。
import { API_BASE, FIXTURE_ENABLED } from '@/config/env'
import { getFixture } from './fixture'

export class BackendUnreachableError extends Error {
  constructor(detail) {
    super('后端未启动 / 未连接')
    this.name = 'BackendUnreachableError'
    this.code = 'BACKEND_UNREACHABLE'
    this.detail = detail || null
  }
}

function buildUrl(path, query) {
  const qs = []
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === '') continue
      qs.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    }
  }
  return `${API_BASE}${path}${qs.length ? `?${qs.join('&')}` : ''}`
}

/**
 * @returns {Promise<{ok:boolean, status:number, body:any, raw:string, url:string, method:string, fixture?:boolean}>}
 * @throws  {BackendUnreachableError} 仅当「连不上后端」时抛（网络错误 / 代理 503 backend_unreachable）
 */
export async function request(path, { method = 'GET', body, query } = {}) {
  const url = buildUrl(path, query)

  // 显式 fixture（默认关闭）：仅在 VITE_FEICUI_DEV_FIXTURE=true 时生效，
  // 页面会同时显示「DEV FIXTURE 已启用」横幅，条目一律标记来源＝fixture。
  if (FIXTURE_ENABLED) {
    const fx = getFixture(method, path, query)
    if (fx) {
      return {
        ok: fx.status >= 200 && fx.status < 300,
        status: fx.status,
        body: fx.body,
        raw: JSON.stringify(fx.body),
        url,
        method,
        fixture: true,
      }
    }
    return {
      ok: false,
      status: 501,
      body: { detail: 'fixture 未覆盖该请求（dev fixture 已启用）' },
      raw: '',
      url,
      method,
      fixture: true,
    }
  }

  let res
  let raw = ''
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    raw = await res.text()
  } catch (e) {
    // 后端未启动时，dev 代理会返回 503（见 vite.config.js apiProxyErrorGuard），
    // 一般不会走到这里；走到这里＝真的连不上 dev server 自身。
    throw new BackendUnreachableError(String((e && e.message) || e))
  }

  let parsed = null
  if (raw) {
    try {
      parsed = JSON.parse(raw)
    } catch {
      parsed = null // 非 JSON 响应体（如代理错误页）→ 页面按 raw 文本展示
    }
  }

  if (res.status === 503 && parsed && parsed.error === 'backend_unreachable') {
    // **dev 代理层**信号（非 feicui API 码族）。见 README §3。
    throw new BackendUnreachableError(parsed.code || null)
  }

  return { ok: res.ok, status: res.status, body: parsed, raw, url, method }
}

/** 统一把异常转成页面可直接渲染的状态对象（不做任何编造） */
export function describeFailure(err) {
  if (err instanceof BackendUnreachableError) {
    return { kind: 'backend-down', message: err.message, detail: err.detail }
  }
  return {
    kind: 'error',
    message: String((err && err.message) || err),
    detail: (err && err.code) || null,
  }
}
