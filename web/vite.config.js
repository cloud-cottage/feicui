import { fileURLToPath, URL } from 'node:url'
import net from 'node:net'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// ─────────────────────────────────────────────────────────────────────────────
// feicui 前端（阶段 1a 骨架）
// 端口真源：feicui/docs/feicui.spec.md §6.1（前端 5195 / API 5196），
//          跨项目端口真源 = /Users/kevin/bistro/ctrl/PORTS.md
//   - strictPort: true ⇒ 5195 被占时**直接报错退出**，不回退 5173/5174（spec §7 AC-13）
//   - preview 同样锁 5195
// ─────────────────────────────────────────────────────────────────────────────
const PORT = 5195
// 默认目标＝spec §6.1 的 API 端口 5196。
// FEICUI_API_TARGET 是**仅用于离线自测**的 dev 覆盖（指向一次性 stub），
// 默认不设置 ⇒ 行为与登记口径一致（http://127.0.0.1:5196）。
const API_TARGET = process.env.FEICUI_API_TARGET || 'http://127.0.0.1:5196'

// 后端未启动（连接失败）时，让 /api 的失败可与「后端真实 5xx」区分开。
// 注意：这里的 503 是 **dev 代理层** 产生的信号，**不是** feicui API 的错误码族
// （spec §3.2 S-6 的 400/404/409/422/500）；API 自身码族未被本前端改动。
function apiProxyErrorGuard(proxy) {
  proxy.on('error', (err, _req, res) => {
    if (!res || typeof res.end !== 'function') return
    if (!res.headersSent && typeof res.writeHead === 'function') {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
    }
    res.end(
      JSON.stringify({
        error: 'backend_unreachable',
        target: API_TARGET,
        code: (err && err.code) || 'UNKNOWN',
        note: '此响应由 Vite dev 代理产生（后端连接失败），非 feicui API 响应',
      })
    )
  })
}

// 后端连通性探测（**dev-only，非 API 契约**）：spec §3 无 /api/health，
// 故由本前端 dev server 自己探一次 TCP 连通性，供页面显示「后端未启动」。
// 该中间件不进构建产物，生产 / preview 无此路径。
//
// 阶段 1c 修复（G-1 同源）：spec §3.9 要求「探针与代理 503 必须同源」。
// 前端发起的探针路径 = src/config/env.js 的 BACKEND_PROBE_PATH，**随 base 走**，
// 故此处必须按同一口径注册 base 前缀（'/feicui/__feicui/backend-probe'），
// 否则经 5164 时落在 shu/web 代理键之外 → SPA 兜底返回 HTML → 横幅停在「连通性未知」。
// 旧的无前缀路径**保留兼容**（阶段 1a 起存在；直连 5195 的旧客户端/自测脚本仍可用）。
function backendProbe() {
  return {
    name: 'feicui-backend-probe',
    apply: 'serve',
    configureServer(server) {
      const u = new URL(API_TARGET)
      const handler = (_req, res) => {
        const host = u.hostname
        const port = Number(u.port || (u.protocol === 'https:' ? 443 : 80))
        const socket = net.connect({ host, port })
        let settled = false
        const finish = (reachable, detail) => {
          if (settled) return
          settled = true
          socket.destroy()
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          res.setHeader('Cache-Control', 'no-store')
          res.end(
            JSON.stringify({ reachable, target: API_TARGET, detail: detail || null })
          )
        }
        socket.setTimeout(800)
        socket.once('connect', () => finish(true, 'tcp-connect-ok'))
        socket.once('timeout', () => finish(false, 'timeout'))
        socket.once('error', (e) => finish(false, e.code || 'error'))
      }
      // ① base 感知路径（与 BACKEND_PROBE_PATH / API 代理同源）：/feicui/__feicui/backend-probe
      server.middlewares.use(`${BASE.replace(/\/+$/, '')}/__feicui/backend-probe`, handler)
      // ② 直连 5195 的旧路径兼容键（无前缀，本轮保留未动）
      server.middlewares.use('/__feicui/backend-probe', handler)
    },
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// URL base（阶段 1c）：feicui 前端被 shu/web（5164）以 `/feicui` 反代直达，
// 故以 `/feicui/` 为 base ⇒ 生成的 asset 绝对路径自带前缀，无需在 5164 侧 rewrite。
// dev 与 preview 同 base（预览与直连行为一致）。
// ─────────────────────────────────────────────────────────────────────────────
const BASE = '/feicui/'

export default defineConfig({
  base: BASE,
  plugins: [vue(), backendProbe()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // 绑定口径（**显式**，非默认）：依据 /Users/kevin/bistro/ctrl/PORTS.md §1 制度 (d)
    // 「本机非生产链路引用一律写 127.0.0.1，不写 localhost」。
    // 若只绑 IPv6 `::1`，则阶段 1c 在 shu/web/vite.config.js 里把 /feicui 代理指向
    // http://127.0.0.1:5195 时会 ECONNREFUSED（jiazu Gramps-Web ↔ ::1:5198 的同类坑，方向相反）。
    // 故此处**显式**绑 127.0.0.1，保证 127.0.0.1:5195 可达。
    host: '127.0.0.1',
    port: PORT,
    strictPort: true,
    // HMR（阶段 1c）：被 5164 反代时不依赖其 ws 代理，客户端直连 5195 的 ws。
    // 5164 侧未配 ws 代理，若沿用默认 clientPort 会出现「页面通、热更连不上」的静默降级，
    // 故显式钉死 5195（＝本服务端口）。
    hmr: { clientPort: PORT },
    proxy: {
      // 直连 5195 的旧路径兼容键（阶段 1a 起存在，**本轮保留未动**）。
      '/api': {
        target: API_TARGET,
        changeOrigin: false,
        configure: apiProxyErrorGuard,
      },
      // ── 阶段 1c 修复（G-2）：base 感知的 API 键 ─────────────────────────────
      // feicui 前端 base = '/feicui/'，故页面发出的 API 请求是 `/feicui/api/**`
      // （见 src/config/env.js 的 API_BASE）。这样**同一份 API 路径在两种访问方式下都通**：
      //   ① 直连 5195：/feicui/api/jobs → 本键 rewrite → /api/jobs → 5196
      //   ② 经 5164  ：shu/web 的 '/feicui' 键**不带 rewrite**、原样透传到 5195，
      //                到达后命中本键 → 同上（故 shu/web 侧**无需**再加第二条代理键，冻结面最小）
      //
      // 为什么必须显式 rewrite：Vite 的代理**不会**自动剥掉匹配到的 context，
      // 且 proxy 中间件早于 baseMiddleware 执行 —— 这正是 G-2 的机理：
      // 旧配置下 `/feicui/api/jobs` 既不匹配 '/api'（已在 base 之前），
      // 剥掉 base 后又已过了代理阶段 ⇒ 落到 SPA 兜底，返回 200 text/html。
      // rewrite 只剥开头的 `/feicui`（/feicui/api/jobs → /api/jobs），查询串原样保留。
      //
      // 目标默认 = http://127.0.0.1:5196（spec §6.1；FEICUI_API_TARGET 仅离线自测覆盖）。
      // 同样挂 apiProxyErrorGuard：5196 未启动时返回 **503 JSON**（backend_unreachable），
      // 使页面显示「后端未启动」，而不是把 HTML 当接口响应体展示。
      '/feicui/api': {
        target: API_TARGET,
        changeOrigin: false,
        rewrite: (p) => p.replace(/^\/feicui/, ''),
        configure: apiProxyErrorGuard,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: PORT,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
