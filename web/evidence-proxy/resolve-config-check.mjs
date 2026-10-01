// 阶段 1c 证据脚本：**不绑定任何端口**，只用 Vite 的 resolveConfig 读回生效配置，
// 证明 shu/web 的 server.proxy 与 preview.proxy 都带 '/feicui'（5164 被他人 dev 进程占用，
// 无法起 preview 实测，故以配置解析层取证）。
// 运行：node feicui/web/evidence-proxy/resolve-config-check.mjs
const SHU_WEB = '/Users/kevin/bistro/shu/web'
const FEICUI_WEB = '/Users/kevin/bistro/shu/feicui/web'

const load = async (dir) => {
  const vite = await import(`file://${dir}/node_modules/vite/dist/node/index.js`)
  const r = await vite.resolveConfig({ configFile: `${dir}/vite.config.js` }, 'serve')
  return r
}

const shu = await load(SHU_WEB)
const feicui = await load(FEICUI_WEB)

const pick = (proxy) =>
  proxy ? Object.fromEntries(Object.entries(proxy).map(([k, v]) => [k, { target: v.target, changeOrigin: v.changeOrigin, hasRewrite: typeof v.rewrite === 'function' }])) : null

console.log('=== shu/web (5164) ===')
console.log('base        =', JSON.stringify(shu.base))
console.log('server.port =', shu.server.port, '| strictPort =', shu.server.strictPort)
console.log('server.proxy =', JSON.stringify(pick(shu.server.proxy)))
console.log('preview.port =', shu.preview.port, '| strictPort =', shu.preview.strictPort)
console.log('preview.proxy=', JSON.stringify(pick(shu.preview.proxy)))

console.log('=== feicui/web (5195) ===')
console.log('base         =', JSON.stringify(feicui.base))
console.log('server.host  =', feicui.server.host, '| port =', feicui.server.port, '| strictPort =', feicui.server.strictPort)
console.log('server.hmr   =', JSON.stringify(feicui.server.hmr))
console.log('preview.host =', feicui.preview.host, '| port =', feicui.preview.port, '| strictPort =', feicui.preview.strictPort)
console.log('feicui base applied to preview =', feicui.preview.base ?? '(继承 config.base)')

const ok =
  shu.base === '/' &&
  shu.server.port === 5164 && shu.server.strictPort === true &&
  shu.server.proxy?.['/feicui']?.target === 'http://127.0.0.1:5195' &&
  shu.server.proxy?.['/feicui']?.changeOrigin === true &&
  typeof shu.server.proxy?.['/feicui']?.rewrite !== 'function' &&
  shu.preview.port === 5164 && shu.preview.strictPort === true &&
  shu.preview.proxy?.['/feicui']?.target === 'http://127.0.0.1:5195' &&
  typeof shu.preview.proxy?.['/feicui']?.rewrite !== 'function' &&
  Object.keys(shu.server.proxy).length === 1 &&
  Object.keys(shu.preview.proxy).length === 1 &&
  feicui.base === '/feicui/' &&
  feicui.server.host === '127.0.0.1' && feicui.server.port === 5195 && feicui.server.strictPort === true &&
  feicui.server.hmr?.clientPort === 5195 &&
  feicui.server.proxy?.['/api']?.target === 'http://127.0.0.1:5196'

console.log('=== VERDICT ===', ok ? 'PASS' : 'FAIL')
process.exit(ok ? 0 : 1)
