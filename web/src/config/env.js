// 运行期配置：只读 import.meta.env，不依赖任何外链资源。
//
// API 基址（阶段 1c 修复 G-2）：必须**随 base 走**，不能写死相对根的 '/api'。
//   base 为 '/feicui/' ⇒ API_BASE = '/feicui/api'。
// 这样**同一份 API 路径在两种访问方式下都通**，且不需要再动 shu/web：
//   - 直连 5195：/feicui/api/** 命中 feicui dev 的 '/feicui/api' 代理键
//                （rewrite 剥掉 /feicui）→ http://127.0.0.1:5196/api/**；
//   - 经 5164  ：shu/web 的 '/feicui' 代理键**不带 rewrite**、原样透传到 5195，
//                到达后命中同一 '/feicui/api' 键 → 同上。
// 原先写死的 '/api'（相对根）经 5164 时既不带 /feicui 前缀、也不在 5164 的代理键里
// ⇒ 落到 5164 的 SPA 兜底，返回 200 text/html，页面对该响应体「原样展示」
// （宿主节点 <PRE>，见 evidence-proxy/README.md §G-2）。
// VITE_API_BASE 覆盖能力保留（显式设置时优先，一律以显式值为准）。
const BASE_URL = import.meta.env.BASE_URL || '/'
const API_BASE_FROM_BASE = `${BASE_URL.replace(/\/+$/, '')}/api`
export const API_BASE = import.meta.env.VITE_API_BASE || API_BASE_FROM_BASE

// 后端连通性探测路径 —— **dev-only**，由本前端 dev server 提供（见 vite.config.js
// backendProbe 插件）。spec §3 无 /api/health，故不要求后端新增端点。
//
// 阶段 1c 修复（G-1：探针必须**与 API 同源**）：原写死相对根的 '/__feicui/backend-probe'
// 经 5164 时落在 shu/web 的代理键之外 ⇒ 命中 SPA 兜底返回 200 text/html，
// probeAvailable=false ⇒ 后端真在线时横幅仍停在「连通性未知」。
// 现改为**随 base 走**（与上面的 API_BASE 同口径）：
//   base '/feicui/' ⇒ '/feicui/__feicui/backend-probe'
// 两种访问方式都通（与 API 完全同构）：
//   - 直连 5195：命中本 dev server 的 base 感知注册路径；
//   - 经 5164  ：shu/web 的 '/feicui' 代理键不带 rewrite、原样透传到 5195 → 同一注册路径。
// spec §3.9 要求「探针与代理 503 必须同源」，本改动即为该条的落地。
export const BACKEND_PROBE_PATH = `${BASE_URL.replace(/\/+$/, '')}/__feicui/backend-probe`

// 显式 dev fixture 开关：**默认关闭**。关闭时页面不展示任何一个示例条目。
export const FIXTURE_ENABLED = import.meta.env.VITE_FEICUI_DEV_FIXTURE === 'true'

export const API_TARGET_DISPLAY = 'http://127.0.0.1:5196'
