# feicui/web — feicui 前端站点骨架（阶段 1a）

feicui（印谱 PDF 解析工具）的**独立 Vue3 + Vite 前端站点**。Streamlit UI（`feicui/app.py`）按
`feicui/docs/feicui.spec.md` §1.4 退役后，主入口改由本站点承担。

| 项 | 值 |
| --- | --- |
| 端口 | **5195**（`strictPort: true`，**不得回退 5173/5174**）— spec §6.1 / §7 AC-13 |
| API 基址（dev） | `/api` → Vite proxy → **`http://127.0.0.1:5196`**（spec §6.1） |
| 后端 | 另一路并行开发的 FastAPI 薄接口层（`feicui/server/**`），**本工程不含任何后端逻辑** |
| 依赖 | 零 CDN、零外链字体、零外链图片（离线自洽） |
| Node / Vite | 本机 `node v18.19.0` ⇒ 选 **Vite 6.4.3**（`^18.0.0 \|\| ^20.0.0 \|\| >=22.0.0`，Node 18 可跑；同机 `xiai/web` 亦用 6.4.3 且已成功 build）。**未选 Vite 7**（其要求 Node ≥ 20.19） |

---

## 1. 起法与验证

| 项 | 值 |
| --- | --- |
| **实际监听（绑定）地址** | **`127.0.0.1:5195`**（IPv4，**显式**写在 `vite.config.js` 的 `server.host`；`preview.host` 同）。**依据**＝`/Users/kevin/bistro/ctrl/PORTS.md` **§1 制度 (d)**「本机非生产链路引用一律写 `127.0.0.1`，不写 `localhost`」 |
| 为何必须显式绑 IPv4 | 阶段 1c 要在 `shu/web/vite.config.js` 加 `server.proxy` 把 `/feicui` 指向 **`http://127.0.0.1:5195`**；若 dev server 只绑 IPv6 `::1`，该代理会 `ECONNREFUSED`（本机已有同类镜像坑：jiazu Gramps-Web 只绑 IPv4，上游用 `localhost` 被解析成 `::1` ⇒ `ECONNREFUSED ::1:5198`；此处方向相反，后果相同） |
| 对照 | `http://localhost:5195/` 亦可访问（浏览器解析到 127.0.0.1），但**登记/代理目标一律以 `127.0.0.1:5195` 为准** |

```bash
cd /Users/kevin/bistro/feicui/web
npm install
npm run dev      # → http://127.0.0.1:5195/feicui/   （strictPort，若 5195 被占会直接报错而非换端口；base '/feicui/'）
npm run build    # 生产构建（mode=production ⇒ 读 web/.env.production，base='/feicui/'）→ dist/
```

**URL base：本地与生产同一口径 `/feicui/`**（2026-10-19 两轮纠偏后的定稿）。
`vite.config.js` 用 `loadEnv(mode, envDir, 'VITE_')` 显式读 `VITE_BASE`（`vite.config`
跑在 Node，`.env.*` **不会**自动注入 `process.env`）：
- 未设置 ⇒ 默认 `'/feicui/'`：本地 dev、直连 5195、经 shu-web（5164）`/feicui` 反代；
- `web/.env.production`（入库）置 `'/feicui/'`：生产 Vercel 构建**同 base**，
  故 `dist/index.html` 引用 `/feicui/assets/*.js|css`，与本地一致（不会再出现「本地能跑、线上白屏」）；
- 需要别的 base 时显式覆盖：`VITE_BASE=/xxx/ npm run build`（参数化能力保留）。

**公网路径映射（`web/vercel.json`，权威）**：

| 公网 URL | 来源（`dist/` 产物） | 说明 |
| --- | --- | --- |
| `/`、`/index.html` | `dist/landing/index.html` | **公网引导页**（项目介绍 + GitHub Releases 下载）；源＝`web/public/landing/index.html` |
| `/landing/*` | `dist/landing/*` | 引导页自身资源（相对路径 `assets/feicui.png`），静态直出、不被任何规则改写 |
| `/feicui/`、`/feicui/:path*` | `dist/index.html` | **Vue 站**（SPA 深链回落） |
| `/feicui/assets/*` | `dist/assets/*` | 构建产物资源；带 base 前缀 ⇒ 需显式映射到 `assets/` |

为什么用 `routes` 而不是 `rewrites`：**Vercel 的静态文件（filesystem）优先于 `rewrites`**，
且 `@vercel/routing-utils` 会在 `rewrites` 前自动插入 `{"handle":"filesystem"}`。由于
`dist/index.html`（Vue 壳）就位于根路径，`{"source":"/","destination":"/landing/index.html"}`
**永远不会命中**（根路径被静态 `index.html` 抢先）。故改用有序 `routes`：把 `/` 的两条规则
放在 `handle: filesystem` **之前**，其余规则放在其后（未命中真实文件才回落 SPA）。
`routes` 与 `rewrites`/`redirects`/`headers` 互斥，本文件只用 `routes`。


后端（另一路）起法参考 spec §6.2：

```bash
cd /Users/kevin/bistro/xiai/feicui/server
./.venv/bin/python -m app.main
```

**后端未启动时的行为（硬约束）**：页面顶部显示「**后端未启动 / 未连接**」横幅 + 启动提示，
所有数据区**不展示任何示例 / 估算 / 缓存冒充值**，只显示「未连接」。**绝不**用假数据静默填充。

---

## 2. 页面与本单范围（对着 spec §3 契约做，不多做）

| 路由 | 页面 | 调用的契约 | 备注 |
| --- | --- | --- | --- |
| `/` | 任务页 | **E1** `POST /api/jobs` | 建 job（`pdf_path` / `page_range` / `chunk_size` / `rerun`）；**同书重复建 ⇒ 后端 409 + 既有 `job_id` 原样展示，不吞**。job 列表：见 §4 规范缺口 G-2 |
| `/jobs/:job_id` | 任务详情页 | **E2** `GET /api/jobs/{job_id}` | 轮询展示 `done_pages`/`total_pages`/`cursor`/`counters`/`failed_pages`；页内明确标注「**进度＝后端库内复算（S-1）**」 |
| `/jobs/:job_id/results` | 结果页（预留） | **E3** `GET /api/jobs/{job_id}/stamps` | 按 6 字段信封 `{items, page, limit, total, has_more, next_cursor}` 预留列表 + 分页；后端未提供该接口时显示「后端尚未提供该接口」 |
| `/jobs/:job_id/missing` | 缺失清单页 | **E5** `GET /api/jobs/{job_id}/missing?kind=image\|text` | 列影像 / 释文缺失项（`{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}`） |

**E4（触发导出）不在本单范围**（无页面）。

### 2.1 S-1：进度真实性（前端侧纪律）

- 进度条宽度**只**由 E2 返回的 `done_pages / total_pages` 计算；**没有任何** `setInterval`/`setTimeout`
  在本地推进百分比，也没有任何基于耗时/页数的估算（`grep -rn 'setInterval' src/` 只应出现在轮询取数处，
  且轮询只做「重新取数」，不自行改变进度值）。
- `total_pages` 缺失或为 0 时**不画进度**，显示 `—`。
- 每次取数都记录**取数时点**，界面上显示 `数据时点`；接口层挂掉时把上一次快照标为「**已过期**」并显示
  最后成功时点，而不是继续假装在推进。

### 2.2 离线自测用的显式 fixture 开关（**默认关闭**）

```bash
VITE_FEICUI_DEV_FIXTURE=true npm run dev
```

- **默认（未设置）＝关闭**：页面不展示任何一个示例条目。
- 打开后页面顶部有醒目红色横幅「**DEV FIXTURE 已启用 —— 以下为示例数据，非后端真实数据**」，
  且数据源标记为 `fixture`。仅用于离线自测 UI 骨架，**不得**作为任何验收依据。

---

## 3. 后端连通性判定（dev）

> **自测用代理目标覆盖（默认不设置）**：`FEICUI_API_TARGET=http://127.0.0.1:<port> npm run dev`
> 可把代理与探测目标一起指向一次性 stub（离线自测「未实现端点 / 409」等分支用）。
> **默认不设置 ⇒ 目标恒为登记口径 `http://127.0.0.1:5196`**；探测端点与代理目标同源，
> 不会出现「代理指向 A、横幅显示 B」的错报。

| 信号 | 来源 | 说明 |
| --- | --- | --- |
| `GET /__feicui/backend-probe` | **本前端 dev server 中间件**（`vite.config.js`） | dev-only：对 `API_TARGET`（**默认** `127.0.0.1:5196`，与代理目标同源）做一次 TCP 连通性探测，返回 `{reachable, target, detail}`。**不是 API 契约的一部分**，不由后端实现，不进构建产物，生产无此路径 |
| `503 {error:"backend_unreachable"}` | **Vite proxy 的 error 钩子** | 仅在后端连接失败（如 `ECONNREFUSED`）时由**代理层**产生，用于让 `/api` 失败与「后端真实 5xx」可区分。**注意**：该 503 **不是** feicui API 的错误码族（spec §3.2 S-6 的 400/404/409/422/500），它是 dev 代理产生的信号，API 自身码族未被改动 |

浏览器侧任何 `/api` 请求遇到「网络错误 / 503 backend_unreachable」⇒ 页面统一显示「后端未启动」。

---

## 4. 规范缺口（**如实上报，本工程未自行发明契约**）

> 按 spec §0.4，缺口**不改规范文件**（本工程未改 `feicui/docs/feicui.spec.md` 一字），只在此登记。

- **G-1（取印面裁图 = **E6**，**已收口为正式契约**）**：结果页展示裁图走 spec 的 **E6**，路径形状为 **3 段**
  （`page` 与 `idx` **都必给**）：

  ```
  GET /api/jobs/{job_id}/stamps/{page}/{idx}/image
  ```

  - **契约依据**：`feicui/docs/feicui.spec.md` **v1.3 §3.5（E6 全表）+ §3.1（E6 行）** ——
    **不再是**本前端单方面假设的形状，**无需待裁**。
  - `{page}` **1-based**（↔ `stamps.page`）、`{idx}` **0-based**（↔ `stamps.idx`）；**无查询参数**。
  - 状态码：`200` = 影像字节（`Content-Type` 取**文件实际类型**、`Content-Length` 必填、**不包 JSON 信封**）；
    `404` = **三类同码** `JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`；
    `400` = 参数非法；`500` = 读盘 / 解码异常、影像类型不可判定。
  - **已废止的 2 段形态**（`/api/jobs/{job_id}/stamps/{idx}/image`）自 spec v1.2 起**不是契约**：
    后端**不两套并存**（调用它返 `404`），前端**不得**再生成该路径，也**不留** 2 段兜底。
  - **为什么必须带 `page`**（§3.5 依据）：行级唯一锚是 **`(pdf_name, page, idx)`**，
    `idx` 单值在 job 内**不唯一**（每页都从 0 重排）⇒ 只用 `idx` 取不到确定的那枚印面。
  - 代码位置：`src/api/stampsImage.js` —— 取图路径的**唯一常量来源**；
    任何页面 / 组件**不得**硬编码该路径（一处收口）。
  - 取不到图时页面显示「**裁图不可用**」并给出**真实原因码**（`JOB_NOT_FOUND` /
    `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`），**绝不**用占位图 / 示例图冒充真实裁图。
- **G-2（缺 job 列表端点）**：spec §3 只有 E1（`POST /api/jobs` 建 job）而**无 `GET /api/jobs`（列 job）**，
  但任务页需要 job 列表。本工程处理口径（**不发明契约**）：
  1. 先尝试 `GET /api/jobs`；
  2. 若后端未提供（404/405/501/未连接）⇒ 明确显示「后端尚未提供该接口」，
     并**另列**一份「**本浏览器本地记录（localStorage）**」的已建 job（来源＝本机 E1 的 201 响应），
     两份数据在界面上分栏、来源标注清楚，**不混淆**。
- **G-3（E1 409 响应体形状未定）**：spec 只写「`409` + 既有 `job_id`」，**未定 body 形状**。
  本工程：把**原始 body 原样展示**（JSON 美化或纯文本），并**启发式**尝试从
  `body.job_id` / `body.detail.job_id` / `body.existing_job_id` 取既有 `job_id` 生成跳转链接；
  启发式取不到时只展示原始 body，**不猜、不造**。
- **G-4（无健康检查端点）**：spec §3 无 `/api/health`。故后端连通性判定走本工程 dev server 的
  `/__feicui/backend-probe`（见 §3），**不**要求后端新增任何端点。
- **G-5（E3 未实现时的状态码未定）**：spec 未规定「端点尚未实现」时返回什么（404？501？）。
  本工程对 **404 / 405 / 501** 三种都判为「后端尚未提供该接口」。**这不是规范口径**，仅为前端宽容处理。

---

## 5. 目录

```
feicui/web/
├── package.json / vite.config.js / index.html
├── README.md                     ← 本文件
├── src/
│   ├── main.js / App.vue / router/index.js
│   ├── api/        client.js（取数 + 错误/后端未启动归一化）/ jobs.js（E1/E2/E3/E5）
│   │               stampsImage.js（**E6 取图契约：3 段正式路径**）/ fixture.js（默认关闭）
│   ├── composables/useBackendStatus.js（连通性探测）/ usePolling.js（只重新取数，不推进进度）
│   ├── components/ BackendBanner.vue / StateNotice.vue / CountersTable.vue
│   ├── pages/      JobsPage.vue / JobDetailPage.vue / ResultsPage.vue / MissingPage.vue
│   └── styles/base.css（系统字体栈，无外链）
└── evidence/       自测证据（build 输出 / curl 首行 / DOM 文本 / lsof）
```

## 6. 边界（本单明确不做）

- 不实现任何后端逻辑（后端在另一路：`feicui/server/**`）。
- 不做鉴权、不做部署配置。
- **未改动** `shu/web/vite.config.js`（5164 的 `/feicui` 代理＝单独一轮任务；本工程只读参照，未写一字）。
- **未改动** spec、`shu/docs/**`、`ctrl/**`、`feicui/server/**` 及所有已验收证据目录。

## 7. 站内直链下载包（build 前自动取包，2026-10-20）

引导页 `public/landing/index.html` 的两个主按钮**不再跳 GitHub**，改指站内路径：

- `/downloads/feicui-mac-s1.dmg`（macOS 标准版，94.5 MB）
- `/downloads/feicui-win-s1.zip`（Windows x64 onedir，94.0 MB）

这两个文件由 `scripts/fetch-downloads.mjs` 在 `vite build` **之前**从 latest Release
（`cloud-cottage/feicui`，tag `v1.0.0`）拉到 `public/downloads/`（ASCII 文件名；该目录已 gitignore，不入库）。

| 开关 | 作用 |
|---|---|
| `FETCH_DOWNLOADS_SKIP=1` | 完全跳过下载（断网 / 只验前端 / CI） |
| `FETCH_DOWNLOADS_FORCE=1` | 忽略「> 50 MB 即缓存」判定，强制重下 |
| `GITHUB_TOKEN` | 私有仓库或 API 限流时使用（公开仓库不需要） |

**失败不阻断构建**：任何异常只打 `⚠️` 警告、退出码恒 0 ⇒ 页面按钮照旧渲染，但点击会 404。
所以每次部署后必须验：

```bash
curl -sI https://feicui.xiai.plus/downloads/feicui-mac-s1.dmg   # 200 + 99046046 + x-apple-diskimage
curl -sI https://feicui.xiai.plus/downloads/feicui-win-s1.zip   # 200 + 98524982
```

**150 MB 的 `feicui-mac-s2.dmg`（含 RapidOCR）刻意不进网页** —— 超 Vercel 单文件 100 MB 上限，
只留在 Release；页面小字只写「需要请联系」，不给外站链接。
