# 阶段 1c（代码侧）：`/feicui` 直达代理 —— 自测证据

- 角色：Kong（工程师）· 阶段 1c 代码侧，**不含 ctrl 面板登记**（另开一轮）。
- 目标：`http://localhost:5164/feicui` 直达 feicui 前端；不动 ctrl，不动 shu/web 其它任何东西。
- 证据目录：`/Users/kevin/bistro/shu/feicui/web/evidence-proxy/`
- 时间：2026-09-20 12:00–12:10 CST

## 0. 改动清单（仅 2 个文件）

| 文件 | md5 改前 | md5 改后 |
|---|---|---|
| `shu/web/vite.config.js` | `9b3717baf56b8431a8a9626a88468d23` | `28277d3c02e49ef8c6e042269f9766a5` |
| `feicui/web/vite.config.js` | `9978148140ffd3fcbec81477b43e8b88` | `2db8739ed7b36d58a2f6ebe20447cb15` |

改动语义（逐条对齐硬口径）：

1. `feicui/web/vite.config.js`：`+ base: '/feicui/'`（dev/preview 同 base）、`+ server.hmr.clientPort: 5195`；
   `host '127.0.0.1'` / `port 5195` / `strictPort: true` / `server.proxy['/api']` **未动**。
2. `shu/web/vite.config.js`：`server.proxy` 与 `preview.proxy` **各**加 `'/feicui'`，
   target `http://127.0.0.1:5195`、`changeOrigin: true`、**无 rewrite**；`consoleEntryRewrite` 中间件、端口、双入口
   `build.rollupOptions` 均未动。
3. **未向任何 Vue 路由表新增路由**：`shu/web/src/router/*` md5 改前＝改后（见 §4）。
4. 未改 `shu/web` 其它任何文件（见 §5 时间戳窗口）。

## 1. 证据文件

| 文件 | 内容 |
|---|---|
| `routes-5164.txt` | 14 条对外路由状态码表（含入口 HTML 特征） |
| `npm-scripts.txt` | `shu/web` 的 `check:pricing` / `smoke` / `build` 真实输出 |
| `resolve-config-check.mjs` + `.txt` | **不绑端口**读回生效配置（证明 server+preview 两条代理都在） |
| `diff-shu-web-vite.config.js.txt` | `diff -u` 改前→改后 |
| `diff-feicui-web-vite.config.js.txt` | `diff -u` 改前→改后 |
| `dom-check.py` + `dom-check-5164.txt` | 自建 headless Chrome 取 5164/feicui 真实 DOM |
| `dom-check-5164-jobs.txt` | 深路径 `/feicui/jobs` 的 DOM |
| `feicui-build.txt` | feicui `npm run build`（base 生效）输出 |
| `_pristine/*.before` | 两个 `vite.config.js` 的改前原件（可复算 diff） |

## 2. ① 直连 5195

```
http://127.0.0.1:5195/                302   （baseMiddleware：/ -> /feicui/）
http://127.0.0.1:5195/feicui/         200
http://127.0.0.1:5195/feicui/src/main.js 200
```

## 3. ② 经 5164 代理

5164 上**已有他人在跑的 vite dev（PID 93523）**——按规定在其上验证，**未 kill 任何进程**。
Vite 会在 `vite.config.js` 变更时自动重启 dev server，故该进程已被动加载新配置。

```
http://localhost:5164/feicui/            200
http://localhost:5164/feicui/src/main.js 200
http://localhost:5164/feicui/jobs        200
```

**返回体是 feicui 页面特征（不是 5164 的 SPA 兜底/404 页）**——同一次抓取对照：

| | 5164/feicui/ | 5164/（营销兜底） |
|---|---|---|
| `<title>` | `feicui ｜ 印谱解析任务台` | `印索｜兆级玺印数字引擎` |
| 挂载点 | `<div id="app">` | `<div id="marketing-app">` |
| 入口 | `/feicui/src/main.js` | `/src/marketing/main.js` |
| vite client | `/feicui/@vite/client` | `/@vite/client` |

浏览器层（自建 headless Chrome，`dom-check.py`）：feicui 前端**确实挂载**在 5164 上——

```json
{"target":"http://localhost:5164/feicui/","title":"feicui ｜ 印谱解析任务台",
 "app_mount_text_len":647, "app_html_len":3407,
 "h_tags":"任务页 | 新建 job（E1） | job 列表（后端） | 本浏览器本地记录（localStorage）",
 "script_srcs":"/feicui/@vite/client , /feicui/src/main.js", "console_errors":"[]"}
```

HMR：`/feicui/@vite/client` 内注入 `const hmrPort = 5195;`，证明 `clientPort` 生效、热更走直连 5195。

## 4. ③ 14 条对外路由（5164）与 ⑥ 路由表冻结

14 条具名路由取自 `src/router/{marketing,console}.js`（各 7 条，排除 2 条 catch-all）：
`/ /pricing /docs /docs/quickstart /org /demo /help`（营销）＋
`/console /console/login /console/register /console/overview /console/keys /console/usage /console/billing`（控制台）。

结果：**14/14 = 200**，且每条返回的入口 HTML 正确（营销 7 条 → `src/marketing/main.js`；控制台 7 条 → `src/console/main.js`），
说明 `consoleEntryRewrite` 中间件未被代理影响。明细见 `routes-5164.txt`。

> 附注：`yinsuo-web-foundation` 技能里的 curl 配方只列了 13 条，**漏了 `/console/register`**。
> 本次以路由表为准取 14 条。

路由表冻结：`shu/web/src/router/*` md5 改前＝改后——

```
MD5 (web/src/router/console.js)   = 248a286cd33e30b9215cf3395cdc1b2e   （改前＝改后）
MD5 (web/src/router/marketing.js) = 5421e4f046055f62d2059233292c0770   （改前＝改后）
```

## 5. ④ 三个 npm 脚本（`shu/web`）

| 脚本 | 结果 |
|---|---|
| `npm run check:pricing` | EXIT=0，「✓ 价格字面量静态检查通过（spec §4.3 / AC-19）」 |
| `npm run smoke` | EXIT=0，「✓ 全部通过（132 项断言）」 |
| `npm run build` | EXIT=0，产出 `dist/index.html` + `dist/console.html`，`✓ built in 824ms` |

## 6. 未改其它文件的取证

- `find web feicui/web -type f -newermt "2026-09-20 11:59:00" -not -path "*/node_modules/*"` 结果中，
  **源码树只有 `web/vite.config.js`、`feicui/web/vite.config.js`**；其余为 `web/dist/**`（`npm run build` 重建）、
  `feicui/web/dist/**`（重建后 md5 与改前**逐一相同**）与本证据目录。
- 无外来写手迹象（我的首次落笔 11:59:00 之后无第三方源文件被动）。

## 7. 已知缺口（需 Zang 裁定，未擅自改动）

### G-1（阻塞「一个地址直达」的真实体验）feicui 的 vue-router 未带 base

- 现象：浏览器打开 `http://localhost:5164/feicui/` 后，**地址栏立刻变成 `http://localhost:5164/`**；
  打开 `/feicui/jobs` 同样被归一化到 5164 根。页面本身能渲染 feicui，但**刷新即落回印索营销页**，
  站内跳转（`/jobs/...`）会跳出版 `/feicui` 前缀。
- 根因：`feicui/web/src/router/index.js:13` 用 `createWebHistory()`（无 base），
  配合 `{ path: '/:pathMatch(.*)*', redirect: '/' }` 把 `/feicui/**` 视为未匹配 → `replaceState('/')`。
- 已用**临时实验**证明修复有效，随后**按精确字节回退**（`src/router/*` 属「一律不动」，故不落地）：
  | 状态 | `location`（打开 `/feicui/`） |
  |---|---|
  | 原样（已回退） | `http://localhost:5164/` |
  | 临时改为 `createWebHistory(import.meta.env.BASE_URL)` | `http://localhost:5164/feicui/` ✅ |
  | 临时态打开 `/feicui/jobs` | `http://localhost:5164/feicui/` ✅（留在前缀内） |
- 回退后 md5 复原：`src/router/index.js = 5a2d0082ccb1d93a11dc296b10926609`＝改前。
- 建议（**不在本单范围内**）：`createWebHistory()` → `createWebHistory(import.meta.env.BASE_URL)`，
  **一行、不新增路由**。需 Zang 授权后由 feicui 侧单子落地。

### G-2 `/feicui/api/**` 不落 feicui 的 API 代理

`feicui/web/src/config/env.js` 的 `API_BASE = '/api'`（相对根），
故经 5164 访问时页面发出的 `/api/...` 既不是 `/feicui` 前缀、也不在 5164 的代理键里，实测：

| 请求 | 状态码 | content-type | 说明 |
|---|---|---|---|
| `5164/feicui/api/jobs` | 200 | `text/html` | 命中 feicui SPA 兜底，**非 JSON** |
| `5195/feicui/api/jobs` | 200 | `text/html` | 同上（baseMiddleware 剥前缀后 `/api` 已错过代理匹配） |
| `5195/api/jobs` | 503 | `application/json` | feicui dev 代理正常（503＝后端起不来时的 dev 代理守卫） |

即：**页面壳可达，但代理路径下的 `/api` 取数不可达**。可选口径（需裁定，本单未动）：
(a) feicui 的 `API_BASE` 改为 base 感知（`import.meta.env.BASE_URL + 'api'`）且 `feicui` 代理键改 `/feicui/api`；
(b) 或在 `shu/web` 增第二条代理键 `/feicui/api` → `http://127.0.0.1:5196`（超出本单硬口径，未做）。

**DOM 层同一缺陷的三层佐证**（比 curl 更硬）：feicui 任务页会「原样展示」列表接口的响应体，
于是在 5164 上打开 `/feicui/` 时，`document.body` 里出现一段**印索营销页 HTML**，其宿主节点为 `<PRE>`：

```
yinsuo_host_element = "PRE."
notice_text = "… job 列表（后端） 刷新 列表接口报错（原样展示） HTTP 200 200 但响应体既不是数组、也没有 items 数组 原始响应体（原样展示，未改写） …"

$ curl -s -D- -o /dev/null http://localhost:5164/api/jobs
HTTP/1.1 200 OK
Content-Type: text/html
<title>印索｜兆级玺印数字引擎</title>
```

> 说明：`dom-check.py` 里的 `has_yinsuo_marker=YES` **不是**「渲染到了印索页面」的假阳性——
> 它是「feicui 页面把误路由的 `/api` 响应体（印索营销 HTML）当数据展示」的直接证据；
> 佐证同一份 DOM 的 `title`＝`feicui ｜ 印谱解析任务台`、`script_srcs`＝`/feicui/src/main.js`。
> 该探针已加 `yinsuo_host_element` / `notice_text` 两项以消歧。

### G-3 preview 侧只做了配置层取证

5164 被他人 dev 进程占用（不得 kill），无法起 preview 实测。
`resolve-config-check.mjs` 用 Vite `resolveConfig` 读回生效配置，证明 `preview.proxy['/feicui']` 存在、
target/changeOrigin 正确且无 rewrite；**preview 运行时行为未实测**。

### G-4 端口依赖

`5164/feicui` 依赖 feicui dev（5195）在线；5195 停掉时该路径返回 500（dev 代理层
`ECONNREFUSED`，Vite 内置代理错误）——这不是 feicui API 的码族。日常「一个地址」需要两个服务同时在跑，
这属 ctrl 面板登记轮的职责（本单未动 ctrl）。

## 8. 复现命令

```bash
# 直连与代理
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5195/feicui/
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5164/feicui/
# 配置层读回（不绑端口）
node feicui/web/evidence-proxy/resolve-config-check.mjs
# 14 条路由
for p in / /pricing /docs /docs/quickstart /org /demo /help /console/login /console/register /console /console/overview /console/keys /console/usage /console/billing; do printf "%-22s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5164$p)"; done
# DOM 层（自建 headless Chrome，profile 落 /tmp 并自动清理）
/usr/bin/python3 feicui/web/evidence-proxy/dom-check.py "http://localhost:5164/feicui/"
```

## 9. 收尾状态

- 测试用 feicui dev（5195）**按精确 PID 停掉，端口已放开**；未使用 `pkill -f` / `killall`。
- 停前 kill 有身份校验：PID 1329 且 `lsof -d cwd` ＝ `/Users/kevin/bistro/shu/feicui/web` 且命令行含
  `vite/bin/vite.js` 三重确认后才 `kill`（首次校验因命令行是相对路径而**拒绝执行**，改用 cwd 判据）。
- 停后实测（见 `final-state.txt`）：5195 无监听；**14/14 路由仍 200**；
  `5164/feicui/` → **500**（dev 代理层 ECONNREFUSED，非 feicui API 码族，见 G-4）。
- 5164 上他人在跑的 dev（PID 93523）**始终存活**——未 kill 任何非本人进程。
- 未占用 5173 / 5174 / 5555。
- 临时实验产物（headless profile、`/tmp/*.orig`）已清理。
- **性能/耗时类断言：未做**（按硬约束）。
