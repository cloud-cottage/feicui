// 后端连通性状态（模块级单例，供横幅与各页面共用）。
// 判定来源：① dev server 的 /__feicui/backend-probe（dev-only，见 vite.config.js）；
//           ② 任一 /api 请求抛 BackendUnreachableError 时由页面调用 markBackendDown()。
// 本模块**不**产生任何业务数据。
import { computed, ref } from 'vue'
import { API_TARGET_DISPLAY, BACKEND_PROBE_PATH } from '@/config/env'

const state = ref({
  status: 'unknown', // unknown | up | down
  detail: null,
  lastCheck: null,
  probeAvailable: null, // null=未探过 true/false=探测端点是否可用（生产构建内无此端点）
  target: null, // 探测端点回报的**实际**代理目标（与 vite.config.js 的 API_TARGET 同源）
})

let timer = null

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes()
  )}:${p(d.getSeconds())}`
}

export function markBackendDown(detail) {
  state.value = {
    ...state.value,
    status: 'down',
    detail: detail || null,
    lastCheck: stamp(),
  }
}

export function markBackendUp() {
  state.value = {
    ...state.value,
    status: 'up',
    detail: null,
    lastCheck: stamp(),
  }
}

export async function probeOnce() {
  try {
    const res = await fetch(BACKEND_PROBE_PATH, { headers: { Accept: 'application/json' } })
    if (!res.ok) {
      // 探测端点不存在（如 preview / 生产构建）⇒ 不据此判定后端状态
      state.value = { ...state.value, probeAvailable: false, lastCheck: stamp() }
      return
    }
    const body = await res.json()
    state.value = {
      ...state.value,
      probeAvailable: true,
      status: body && body.reachable ? 'up' : 'down',
      detail: body && body.detail ? body.detail : null,
      target: (body && body.target) || state.value.target,
      lastCheck: stamp(),
    }
  } catch {
    state.value = { ...state.value, probeAvailable: false, lastCheck: stamp() }
  }
}

export function startBackendWatch(intervalMs = 5000) {
  if (timer) return
  probeOnce()
  timer = setInterval(probeOnce, intervalMs)
}

export function stopBackendWatch() {
  if (timer) clearInterval(timer)
  timer = null
}

export function useBackendStatus() {
  return {
    state,
    status: computed(() => state.value.status),
    isDown: computed(() => state.value.status === 'down'),
    isUp: computed(() => state.value.status === 'up'),
    // 实际探测目标优先（dev 下由 /__feicui/backend-probe 回报，与 vite.config.js 的
    // API_TARGET 同源）；探测端点不可用时退回登记口径 http://127.0.0.1:5196
    target: computed(() => state.value.target || API_TARGET_DISPLAY),
    markBackendDown,
    markBackendUp,
    probeOnce,
  }
}
