# 阶段 1c-修复（G-1 路由 base / G-2 API 路径随 base 走）—— 自测证据

- 角色：Kong（工程师）· 阶段 1c-**修复**单。
- 目标：让「一个地址直达」`http://localhost:5164/feicui` **完整**——刷新不掉回 5164 根、API 不把 HTML 当响应体展示。
- 证据目录：`/Users/kevin/bistro/shu/feicui/web/evidence-proxy/fix-1c/`
- 时间：2026-09-20 12:11–12:16 CST
- 上游依据：上一轮 `evidence-proxy/README.md` §7 的 G-1 / G-2（本单按 Zang 写死的修复口径落地，未自行改设计）。

---

## 0. 改动清单（**仅 3 个文件，全在 `feicui/web`**）

| 文件 | md5 改前 | md5 改后 | 改动语义 |
|---|---|---|---|
| `feicui/web/src/router/index.js` | `5a2d0082ccb1d93a11dc296b10926609` | `ab4cb29b25a0908a0d9bee6de1785384` | `createWebHistory()` → `createWebHistory(import.meta.env.BASE_URL)`（**仅此一处**） |
| `feicui/web/src/config/env.js` | `b7fe920d2cbeba46c5c51a8b9b1c0023` | `ec0a060247cebce4a7f4a468208b554e` | `API_BASE` 改为 base 感知：`BASE_URL` 去尾斜杠 + `/api`；保留 `VITE_API_BASE` 覆盖 |
| `feicui/web/vite.config.js` | `2db8739ed7b36d58a2f6ebe20447cb15` | `c5ad905e1cc3e2040bfb7e255c74f38f` | proxy **保留** `'/api'` 键，**新增** `'/feicui/api'` → `API_TARGET`（默认 `http://127.0.0.1:5196`）＋ `rewrite: p => p.replace(/^\/feicui/, '')` |

原件留存（可复算 diff）：`index.js.before` / `env.js.before` / `vite.config.js.before`；
逐文件 `diff -u`：`diff-router-index.js.txt` / `diff-config-env.js.txt` / `diff-vite.config.js.txt`。
改前/改后哈希：`md5-before.txt` / `md5-after.txt`。

### 0.1 冻结面取证（硬约束）

- **`shu/web` 一个字节都没改**（本轮）：
  ```
  MD5 (web/vite.config.js)          = 28277d3c02e49ef8c6e042269f9766a5   ← 与上一轮改后值逐字相同
  MD5 (web/src/router/console.js)   = 248a286cd33e30b9215cf3395cdc1b2e   ← 同上
  MD5 (web/src/router/marketing.js) = 5421e4f046055f62d2059233292c0770   ← 同上
  find web -type f -newermt "2026-09-20 12:11:00" -not -path "*/node_modules/*" -not -path "*/dist/*"
    → 空
  ```
  （`web/dist/**` 因 §4 的 `npm run build` 重建而变，属构建产物，非源码。）
- **路由表逐字未动**（G-1 只允许改 base）——只取 `{ path: ` 开头的实际条目行做比对：
  ```
  diff <(grep -E "^\s*\{ path: " index.js.before) <(grep -E "^\s*\{ path: " src/router/index.js)  → 空
  grep -E "^\s*\{ path: " ... | md5  改前=5559c7fc728ca2d3bf1ef07a256389b3  改后=5559c7fc728ca2d3bf1ef07a256389b3
  ```
  5 条（4 具名 + 1 catch-all）逐字相同。
- **未改 `feicui/server/**`**：我落笔时点 = `12:12:02 / 12:12:06`；
  `feicui/server/{app,worker}/*.py`、`REPORT_1b-i.md` 的 mtime = `12:13:47 ~ 12:14:37`，
  **晚于**我落笔、且我的工具从未写过该目录 ⇒ 系**另一路并行任务**所写。
- 未动 `spike-ocr/` `qa-baseline/` `qa-recheck/` `ops/` `labeling/`；未写 `yinpu.db`。

---

## 1. ① API 路径的响应体类型对照（真跑，`http-api-type-check.sh` / `.txt`）

前置：**5196 未启动**（本单不得占 5196）⇒ 期望「代理层 503 JSON」，**绝不得是 HTML**。

| 请求 | status | content-type | body | `<title>印索` 命中 |
|---|---|---|---|---|
| `http://localhost:5164/feicui/api/jobs`（**页面实际走的路径**） | **503** | `application/json; charset=utf-8` | **JSON** | 0 |
| `http://127.0.0.1:5195/feicui/api/jobs`（直连对照，同一路径） | **503** | `application/json; charset=utf-8` | **JSON** | 0 |
| `http://127.0.0.1:5195/api/jobs`（旧兼容键仍通） | **503** | `application/json; charset=utf-8` | **JSON** | 0 |
| `http://localhost:5164/api/jobs`（**旧缺陷路径对照**） | 200 | `text/html` | NOT_JSON | **1** |
| `http://localhost:5164/feicui/`（页面壳，应仍是 html） | 200 | `text/html` | NOT_JSON | 0 |

经 5164 与直连 5195 的响应体**逐字相同**：

```json
{"error":"backend_unreachable","target":"http://127.0.0.1:5196","code":"ECONNREFUSED",
 "note":"此响应由 Vite dev 代理产生（后端连接失败），非 feicui API 响应"}
```

即：`/feicui/api/**` 已**确实落到 feicui dev 的 API 代理**（503 是 dev 代理层守卫，非 feicui API 码族），
而旧配置打进 5164 根 `/api` 时的 `200 text/html`（印索营销页）对照仍在，说明缺陷机理未变、只是路径已修正。

**为什么同一份 API 路径两种访问方式都通**（本单的设计要点，写死口径照做）：

1. 直连 5195：`/feicui/api/jobs` → 命中 `'/feicui/api'` 键 → rewrite 剥 `/feicui` → `http://127.0.0.1:5196/api/jobs`。
2. 经 5164：`shu/web` 的 `'/feicui'` 键**不带 rewrite**、原样透传到 5195 → 到达后命中**同一个** `'/feicui/api'` 键 → 同上。

⇒ 因此 **`shu/web` 侧无需再加第二条代理键**（冻结面最小，本轮确实没动它）。
为什么必须显式 `rewrite`：Vite 代理**不会**自动剥掉匹配到的 context，且 **proxy 中间件早于 baseMiddleware 执行**——
这正是 G-2 的机理：旧配置下 `/feicui/api/jobs` 在代理阶段不匹配 `'/api'`，过了代理阶段才被剥掉 base，于是落到 SPA 兜底返回 200 text/html。

---

## 2. ② 真实浏览器取证（自建 headless Chrome + CDP，`dom-fix-1c-check.py` / `.txt` / `dom-fix-1c-raw.json`）

启动参数含 `--remote-allow-origins=*`；临时 profile 落 `/tmp`，`finally` 里按 PID 收尾并删除。

| 步骤 | `location.pathname` | 停在 `/feicui/` 前缀 | 页面含「后端未启动」 | 页面含「印索」HTML | `<pre>` 里有营销 HTML | console 错误 |
|---|---|---|---|---|---|---|
| S1 打开 `http://localhost:5164/feicui/` | `/feicui/` | ✅ true | ✅ true | **NO** | false | `[]` |
| S1-RELOAD 同地址刷新 | `/feicui/` | ✅ true | ✅ true | **NO** | false | `[]` |
| S2 深路径 `/feicui/jobs/abc` | `/feicui/jobs/abc` | ✅ true | ✅ true | **NO** | false | `[]` |
| S3 `/feicui/jobs`（无 `:job_id` ⇒ catch-all） | `/feicui/` | ✅ true | ✅ true | **NO** | false | `[]` |
| S4 站内跳转：点 `<nav>` 的 `RouterLink` | `/feicui/` | ✅ true | ✅ true | **NO** | false | `[]` |
| 页面 E1 `/feicui/` | `/feicui/` | ✅ true | ✅ true | **NO** | false | `[]` |
| 页面 E2 `/feicui/jobs/abc` | `/feicui/jobs/abc` | ✅ true | ✅ true | **NO** | false | `[]` |
| 页面 E3 `/feicui/jobs/abc/results` | `/feicui/jobs/abc/results` | ✅ true | ✅ true | **NO** | false | `[]` |
| 页面 E5 `/feicui/jobs/abc/missing` | `/feicui/jobs/abc/missing` | ✅ true | ✅ true | **NO** | false | `[]` |

S1（`location.href` 取证 + 不再展示 HTML）原文：

```json
{"label":"S1-open-5164-feicui","location_href":"http://localhost:5164/feicui/",
 "location_pathname":"/feicui/","stays_in_feicui_prefix":true,
 "title":"feicui ｜ 印谱解析任务台","has_backend_down_text":true,
 "yinsuo_html_marker":"NO","yinsuo_host_element":"NOT_FOUND","pre_texts":"",
 "has_marketing_html_in_pre":false,
 "script_srcs":"/feicui/@vite/client , /feicui/src/main.js","console_errors":"[]",
 "body_text":"feicui 印谱解析任务台 · 端口 5195 · API 5196 任务页 后端未启动 / 未连接 目标 http://127.0.0.1:5196 连不上（ ECONNREFUSED ）。本页不展示任何示例或估算数据。 启动提示：cd /Users/kevin/bistro/shu/feicui && ./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196 最后探测时点：2026-09-20 12:12:5x 任务页 新建 job（E1） …"}
```

**对照上一轮的缺陷形态**（`evidence-proxy/README.md` §7）：当时 `yinsuo_host_element = "PRE."`、
`notice_text` 里出现「列表接口报错（原样展示）… 原始响应体（原样展示，未改写）」。
本轮同位置为 `yinsuo_host_element = NOT_FOUND`、`pre_texts = ""`、`has_marketing_html_in_pre = false`，
列表区文案改为 **「后端未启动 / 未连接：列表无法获取 · 判负细节 ECONNREFUSED」**
（`kind='backend-down'` 分支，非「原样展示」分支）⇒ **不再把 HTML 当接口响应体展示**，且未编造任何数据。

## 3. ③ 刷新 / 站内跳转保持前缀

- 刷新：S1-RELOAD 行 —— `location.pathname` 仍 `/feicui/`（上一轮会掉回 5164 根）。
- 站内跳转：S4 —— 点 `<nav>` 的 `RouterLink`（`clicked_href="/feicui/"`，`before="/feicui/"`），
  跳转后仍 `http://localhost:5164/feicui/`；深路径 E3 的 `<a href>` 亦为 `/feicui/`（`router_link_hrefs` 字段）。
- 深路径直达 + 四页 DOM 文本：`dom-page-1-jobs.txt` / `dom-page-2-jobdetail.txt` /
  `dom-page-3-results.txt` / `dom-page-4-missing.txt`。

## 4. ④ 14 条对外路由 + `shu/web` 三个 npm 脚本（复跑）

`routes-5164.txt`：**14/14 = 200**，入口 HTML 特征正确（营销 7 条 → `/src/marketing/main.js`，
控制台 7 条 → `/src/console/main.js`），说明 5164 的 `consoleEntryRewrite` 与新增代理未互相干扰。

```
/                      200  src=/src/marketing/main.js
/pricing               200  src=/src/marketing/main.js
/docs                  200  src=/src/marketing/main.js
/docs/quickstart       200  src=/src/marketing/main.js
/org                   200  src=/src/marketing/main.js
/demo                  200  src=/src/marketing/main.js
/help                  200  src=/src/marketing/main.js
/console               200  src=/src/console/main.js
/console/login         200  src=/src/console/main.js
/console/register      200  src=/src/console/main.js
/console/overview      200  src=/src/console/main.js
/console/keys          200  src=/src/console/main.js
/console/usage         200  src=/src/console/main.js
/console/billing       200  src=/src/console/main.js
```

`npm-scripts.txt`（`shu/web`，三个脚本 **EXIT=0**）：

| 脚本 | 结果 |
|---|---|
| `npm run check:pricing` | EXIT=0「✓ 价格字面量静态检查通过（spec §4.3 / AC-19）」（共豁免 1 处命中） |
| `npm run smoke` | EXIT=0「✓ 全部通过（132 项断言）」 |
| `npm run build` | EXIT=0，`dist/index.html` + `dist/console.html` 产出，`✓ built in 911ms` |

## 5. 复现命令

```bash
# 起 feicui dev（5195）
cd /Users/kevin/bistro/shu/feicui/web && npm run dev &
# ① API 响应体类型对照
/Users/kevin/bistro/shu/feicui/web/evidence-proxy/fix-1c/http-api-type-check.sh
# ②③ 浏览器取证 + 四页 DOM 文本
/usr/bin/python3 /Users/kevin/bistro/shu/feicui/web/evidence-proxy/fix-1c/dom-fix-1c-check.py
# ④ 14 条路由
for p in / /pricing /docs /docs/quickstart /org /demo /help \
         /console /console/login /console/register /console/overview /console/keys /console/usage /console/billing; do
  printf '%-22s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5164$p)"; done
```

## 6. 规范缺口 / 已知项（**未擅自动，待裁定**）

### G-5（本轮新发现，非本单口径内）dev 探针端点 `BACKEND_PROBE_PATH` 未随 base 走

`src/config/env.js` 的 `BACKEND_PROBE_PATH = '/__feicui/backend-probe'`（相对根），
经 5164 时打到 5164 自己的 SPA 兜底，实测（`http-api-type-check.txt` ①-7）：

| 请求 | status | content-type | body |
|---|---|---|---|
| `http://127.0.0.1:5195/__feicui/backend-probe`（直连） | 200 | `application/json` | `{"reachable":false,"target":"http://127.0.0.1:5196","detail":"ECONNREFUSED"}` |
| `http://localhost:5164/__feicui/backend-probe`（经 5164） | 200 | `text/html` | 5164 的营销页 HTML（非 JSON） |

后果：经 5164 访问时 `probeAvailable=false`，探针不再参与判定。
**但硬要求②仍然满足**——「后端未启动」是由**页面的 API 请求**失败触发的
（503 `backend_unreachable` → `BackendUnreachableError` → `markBackendDown` → 横幅 `isDown`），
实测 `has_backend_down_text=true`。另实测 `shows_unknown_banner=false`，未留下「未知」态。
**代价是（仅当 5196 真的在线时）**：经 5164 时横幅可能停在「后端连通性未知」而非「后端已连接」
（`JobsPage` 成功分支不调用 `markBackendUp`）。本单口径只授权改上述 3 处，故**未改**；
如要收口，需同时把 `BACKEND_PROBE_PATH` 改为 base 感知**并**在 `vite.config.js` 的
`backendProbe` 里按 base 注册中间件（≥2 处改动，属设计变更）。

### G-6 `5164/feicui` 依赖 feicui dev（5195）在线

5195 停掉时该路径不是「直达可用」，需两个服务同时在跑；日常「一个地址」的登记属 ctrl 面板轮的职责（本单未动 ctrl）。上报口径同上一轮 G-4。

### G-7 preview 侧仍未做运行时实测

`shu/web` 的 5164 被他人 dev（PID 93523）占用，不得 kill，故 `preview` 的代理行为只有配置层依据（上一轮 G-3）。本单未复测 preview。

### 未做项（如实列出）

- `feicui/web` 的 `npm run build` **未跑**：该命令会 `emptyOutDir` 重建 `feicui/web/dist/**`，
  而本单改动只涉及 dev 路径（`import.meta.env.BASE_URL` 在 dev 已由真实浏览器执行验证），
  为避免动到可能被别的并行任务消费的构建产物，**主动不做**。若需构建产物级别的证据，需先确认 `dist/` 无其他消费者。
- 未做性能/耗时类断言（按硬约束）。
- 未测 `VITE_API_BASE` 显式覆盖的分支（口径要求保留能力，源码保留 `import.meta.env.VITE_API_BASE || …`，未构造环境变量实测）。

## 7. 收尾状态（`final-state.txt`，2026-09-20 12:15:12 CST）

- 测试用 feicui dev（5195）**按精确 PID（26345）停掉**，端口已放开。
  停前有三重身份校验：`PID=26345`、`lsof -d cwd = /Users/kevin/bistro/shu/feicui/web`、
  `ps -o command=` 含 `node_modules/.bin/vite`；**三重全过才 kill**（否则脚本 `exit 9` 拒绝执行）。
  未使用 `pkill -f` / `killall`；未占用 5173 / 5174 / 5555 / 5196；未 kill 任何非本人进程
  （5164 上他人的 dev **PID 93523 全程存活**，停后仍在）。
- npm 包装进程 25964 已随之退出；临时 headless Chrome profile（`/tmp/feicui-1c-fix-chrome`）已删除，无残留。

停后实测：

| 项 | 结果 |
|---|---|
| 5195 | 无监听（已放开） |
| 14 条对外路由 | **14/14 仍 200** |
| `http://127.0.0.1:5195/feicui/` | 000（unreachable，服务已停） |
| `http://localhost:5164/feicui/` | 500 `text/plain`（**5164 dev 代理层** ECONNREFUSED，非 feicui API 码族；见 G-6） |
| `http://localhost:5164/feicui/api/jobs` | 500 `text/plain`（同上；注意**不是 `text/html`** ⇒ 即便 5195 掉线，页面也拿不到营销页 HTML 去「原样展示」） |
