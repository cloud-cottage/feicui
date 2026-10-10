# 拖曳上传（`POST /api/jobs/upload`）· 实现与证据报告（Kong / feicui）

- 线：feicui（`/Users/kevin/bistro/xiai/feicui`，main）· 角色：Kong（实现）
- 需求（Kevin 2026-10-10）：「新建 job（E1）」页的 `pdf_path *` 输入框改为**拖曳文件**，不必手动键入路径。
- 已裁定两条口径：① **拖动上传为主 ＋ 保留折叠「高级：手输服务器路径」**（默认收起）；② 落点
  **`feicui/inbox/<yyyymmdd>/<原文件名>.pdf`，同名同内容复用**（幂等、不重复占盘）。
- 铁律（浏览器事实）：拖入的 `File` **不带本地路径** ⇒ 必须上传落盘拿服务器侧路径，才能调 E1。
- 起手 HEAD：`6696a3d`（与派单预期一致）；提交见 §7。

## 1. 改动面（新单；**只 additive**）

| 文件 | 性质 | 说明 |
| --- | --- | --- |
| `server/app/uploader.py` | **新增** | 落盘核心：文件名清毒 / `Request.stream()` 分块写盘 / `%PDF-` 魔数 / 上限中断 / sha256 / 幂等与同名异内容分流 |
| `server/app/routers/jobs.py` | 追加路由 | `POST /api/jobs/upload`（**additive**；E1〜E7 一字未改） |
| `server/app/config.py` | 追加常量＋Settings | `UPLOAD_MAX_BYTES_DEFAULT=512 MiB`、`UPLOAD_CHUNK_BYTES_DEFAULT=1 MiB`、`INBOX_DIRNAME="inbox"`；`inbox_dir` / `upload_max_bytes` / `upload_chunk_bytes`（`FEICUI_UPLOAD_MAX_BYTES` / `FEICUI_INBOX_DIR` / `server/config.json` 可覆盖） |
| `server/app/models.py` | 追加模型 | `JobUploadResponse`（7 字段，形状即契约） |
| `web/src/api/upload.js` | **新增** | XHR 上传（**fetch 给不了上传进度**）；`X-Filename` 走 URL-encoded UTF-8 |
| `web/src/pages/JobsPage.vue` | 改前端 | 拖放区（高亮 / 点击选文件）＋进度条＋只读回显＋**可见错误**＋折叠「高级：手输服务器路径」；`form.pdf_path` 仍走**原 E1** |
| `web/src/styles/base.css` | 追加样式 | `.dropzone` / `.uploadbox` / `.advanced`：**色值全走既有 token**，无新造色值、无自绘 SVG |
| `.gitignore` | 追加 | `inbox/`（用户源 PDF，运行时数据）＋ `ops/job-upload/fixtures/`（脚本运行时产物） |
| `ops/job-upload/**` | **新增证据** | 可复跑脚本＋原始读数（见 §6） |

**红线复核**：不碰 `docs/**`（Jing 并行）、`xiai/**`、`ctrl/**`、`var/**`、`exports/**`；**E1 契约零改动**
（只加路由）；未动 tabbar；未动 `yinpu.db` 与三采集库；未 `git add -A`；未 push。

## 2. 端点契约（**本单定义**；规范未定义该端点，落法已登记）

```
POST /api/jobs/upload          5196（经 5195/5164 的 /feicui/api 代理同构）
请求：裸字节流（**不走 multipart**）
  Content-Type: application/pdf（也容 application/octet-stream；缺失亦可 —— 真正的门是 %PDF- 魔数）
  X-Filename: <URL-encoded UTF-8 文件名>
      ⇒ 回退 Content-Disposition 的 filename* / filename ⇒ 再回退 upload.pdf
  Body: PDF 字节（**分块读，内存恒定**）
响应 201（新写入）/ 200（幂等复用），application/json：
  {pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}
错误（**一律结构化 JSON，绝不 HTML 错误页**）：
  400 {"error":"EMPTY_BODY","detail":…}                                  空体
  400 {"error":"NOT_A_PDF","detail":…,"magic"|"received_bytes":…}        首字节非 %PDF- / 短于 5 字节
  413 {"error":"PAYLOAD_TOO_LARGE","detail":…,"limit_bytes":…,
       "declared_bytes"|"received_bytes":…}                              超单文件上限（默认 512 MiB）
```

- **`pdf_path` ＝ 相对 `feicui/` 的路径**（例：`inbox/20261011/xxx.pdf`）——与 §3.1 E1 的
  「PDF 路径（绝对或相对 `feicui/`）」**同口径，可直接交给 E1**（实测：前端把它填进表单，E1 直接 201）。
- `rel_path` ＝ 相对 **inbox 根**（`<yyyymmdd>/<原文件名>.pdf`）。
- **落点**：`inbox/<yyyymmdd>/<清毒后文件名>.pdf`（同目录临时文件 ＋ 原子 `os.replace`；失败即清理，不留空目录／×`.part` 残留）。
- **上限两条路都挡**：声明 `Content-Length` 超限 ⇒ **未落盘即拒**；实收字节超限（无 Content-Length／chunked）⇒ **落盘过程中即中断**。
- **幂等**：同名同内容 ⇒ 不重写（`idempotent:true`，目标 mtime 不变）；同名异内容 ⇒ **绝不覆盖** ⇒
  `<stem>-<sha256[:8]>.pdf`（`dedup_suffix:true`）。
- **零 DB 写、不建 job**：`uploader.py` 不 import `repository`/`db`，端点无任何 SQL（实测见 §3-⑪）。

## 3. 服务端自测读数（`ops/job-upload/10_server_probe.py`，**exit 0**，`10_server_probe_raw.txt/.json`）

靶机＝**5196 活端点**（新 PID `23048`，启动 06:41:43；旧 `92929` 已按面板停）。共 **24 步全绿**：

| # | 用例 | 读数 |
| --- | --- | --- |
| ① | 首次上传（中文名 `probe-拖曳-*.pdf`，842 B 真 PDF） | **201**；`pdf_path=inbox/20261011/probe-拖曳-…pdf`；盘上 sha256 **＝响应 sha256**（`56db923d…`）、bytes 相符；`Content-Type: application/json`（非 HTML） |
| ② | 同内容再传 | **200 `idempotent:true`**；`mtime_ns` **1791672111476396074 → 1791672111476396074（不变）**；路径同 ① |
| ③ | 同名异内容（1219 B） | **201 `dedup_suffix:true`** ⇒ `probe-拖曳-…-c5296988.pdf`；**原文件 sha 未变**（`56db923d…`）；新文件 sha ＝ 源 sha |
| ④ | 文本内容冒充 `.pdf` | **400 `NOT_A_PDF`**（`magic:"this is "`），**未落盘** |
| ⑤ | 空体（0 字节） | **400 `EMPTY_BODY`** |
| ⑥ | 3 字节体（短于魔数） | **400 `NOT_A_PDF`**（`received_bytes:3`） |
| ⑦ | 文件名清毒 ×4 | `../../../etc/passwd.pdf`⇒`passwd.pdf`；`/tmp/abs-evil.pdf`⇒`abs-evil.pdf`；`..\..\win-evil.pdf`⇒`win-evil.pdf`；`ctl\x01\x02evil.pdf`⇒`ctlevil.pdf` ——**4/4 全部落在 `inbox/20261011/` 内**（`escapes_inbox:false`） |
| ⑦b | 300 字超长名 | stem 截到 **120** 字，后缀仍 `.pdf` |
| ⑧ | `X-Filename` 缺省 ⇒ `Content-Disposition` 回退 | `filename*=UTF-8''disp-回退名.pdf` ⇒ `filename` **＝ `disp-回退名.pdf`** |
| ⑨ | 上限＝65536（`server/config.json`，**per-request 生效、不重启**）+ 205642 B | **413 `PAYLOAD_TOO_LARGE`**，`detail="请求体声明 205642 B 超过上限 65536 B（未落盘即拒）"`；**未落盘**、`temp_residue:[]` |
| ⑨b | 声明 `Content-Length: 999999999`（实发 842 B） | **413**（`declared_bytes:999999999`）⇒ **未落盘即拒** |
| ⑨c | **chunked（无 Content-Length）** 64 KiB×4 | **413**，`detail="上传字节数超过上限 65536 B（**已在落盘过程中中断**，未写满盘）"`、`received_bytes:205642`；**未落盘**、无 `.part` 残留（该分句字符串证明走的是**中途中断**分支，而非声明检查分支） |
| ⑩ | 删掉测试配置后再传同尺寸 | **201**（205642 B）⇒ 证明限值确由配置生效、且已恢复 512 MiB 默认 |
| ⑪ | **零 DB 写** | `jobs 5→5`、`job_pages 32→32`、`stamps 89→89`、`stamps` 内容指纹 `915597ac…` **逐位不变** |
| ⑫ | 落点目录 | `inbox/20261011/` 9 个文件（本脚本自建，收尾已按名删除） |

> 诚实登记：⑨c 的 `received_bytes` 等于发满的 205642 —— 客户端把 4 块**一次性**交给了内核缓冲，
> 服务端读满即断；故「**比请求体更早停**」这一点靠 `detail` 的分支字符串＋**盘上零字节**来证，
> 不靠字节计数小于全量来证。

## 4. 真浏览器 drop 全链路读数（`ops/job-upload/03_drop_probe.js`，`03_browser_drop_raw.json`）

**两个源各跑一次**：`http://127.0.0.1:5195/feicui/`（直连 dev）与 `http://localhost:5164/feicui/`（印源反代）。
一律用 **JS 构造的 `DataTransfer` ＋ 真 `File`**（内容＝真 1 页 `%PDF-` 字节）派发 `drop` 事件；
网络状态码由页内包装 `XMLHttpRequest.prototype.send` / `window.fetch` **实测记录**（非推断）。

| 断言 | 5195 直连 | 5164 反代 |
| --- | --- | --- |
| 拖放区存在（`role=button` / `tabindex=0`）、内含 `input[type=file]`（`accept=application/pdf,.pdf`） | ✔ | ✔ |
| `pdf_path` 的**可见输入框已消失**：`<details>` 外的 `input[type=text]` ＝ **3 个**（`如 1` / `如 544` / `如 32`，即页范围与 chunk_size） | ✔ | ✔ |
| 折叠块存在、**默认收起**（`details.open === false`）、内含原输入框、摘要＝「高级：手输服务器路径（默认收起；兼容既有流程）」 | ✔ | ✔ |
| `dragover` ⇒ `.dropzone--over`；`dragleave` ⇒ 恢复 | ✔ / ✔ | ✔ / ✔（首次同步读为 false 系**探针同 tick 读数**所致；等待一个 tick 后复测 true） |
| `drop` ⇒ **`POST /feicui/api/jobs/upload` 201** | ✔ 201 | ✔ 201 |
| 表单拿到服务器侧 `pdf_path`（`inbox/20261011/拖曳测试-<port>-<ts>.pdf`） | ✔ | ✔ |
| 「已就绪」只读回显（文件名 ＋ 体积 842 B ＋ sha256 ＋ 新写入） | ✔ | ✔ |
| 点「建 job」⇒ **E1 `POST /feicui/api/jobs` 201** | ✔ `job-2c0f3b7f37a240779bd46ae83ac9cf4a`（total_pages 1） | ✔ `job-319ef7bb7e2744db9bbceb209d3117d4`（total_pages 1） |
| 本机记录 `localJobs.rememberLocalJob` 写入 | ✔（`{job_id, pdf_path}` 同源） | ✔ |
| 非 PDF 内容（名 `伪装成PDF的文本.pdf`）⇒ 服务器 **400 NOT_A_PDF** ＋ **可见**错误文案 | ✔ 400 | ✔ 400 |
| 非 `.pdf` 扩展名 ⇒ 前端拦下、**不发上传请求**（`txt_requests_sent=0`；5164 计入的唯一请求是周期探针 `/feicui/__feicui/backend-probe`） | ✔ | ✔ |
| 既有的 `page_from/page_to/chunk_size` 与 E1 提交流程 | ✔ 未变 | ✔ 未变 |

> 诚实登记：5164 **首次**跑时 `Runtime.evaluate` 在 5 s 等待窗口超时（探针侧限制），页面侧 JS 仍把链路走完了
> —— 盘上留下 `拖曳测试-5164-1791672175560.pdf`、库内多出对应 job（`job-1b316b7a…`）；随后**重跑**取得上述完整读数。
> 因此 5164 侧共产生 **2 个**探针 job（可解释、非重复缺陷）。

## 5. 重启与活端点（**单路**）

- 停：`POST http://127.0.0.1:5555/api/stop {"sid":"feicui-api"}` ⇒ `{"ok":true,"state":"stopped"}`；`lsof -iTCP:5196` ⇒ CLOSED。
- 起：`POST http://127.0.0.1:5555/api/start {"sid":"feicui-api"}` ⇒ `ok:true`、**新 PID `23048`**（lstart **Sun Oct 11 06:41:43 2026**）、5196 LISTEN；
  旧 PID `92929`（lstart Sat Oct 10 21:54:12）已退出。**未用 `startAll`、未用 `pkill`**（未动 5195 / 5164 / 5555 任何进程）。
- 活端点核验：`GET /api/health` ⇒ 200（`db_path=/Users/kevin/bistro/xiai/data/yinpu.db`、`journal_mode=wal`）；
  `POST /api/jobs/upload` 空体 ⇒ **400**（旧进程时该路径为 404 ⇒ 证明新代码确已生效）。

## 6. 证据文件（均在 `ops/job-upload/`，可复跑）

| 文件 | 内容 |
| --- | --- |
| `10_server_probe.py` | 服务端自测（手写 socket：控 Content-Length / chunked / 中途中断；退出码＝判据） |
| `10_server_probe_raw.txt` / `.json` | 上述 24 步的**原始输出**（脚本自身落盘） |
| `03_drop_probe.js` | 真浏览器 drop 探针的**页面内表达式**（可整段贴进 DevTools / 由 CDP `Runtime.evaluate(awaitPromise)` 执行） |
| `03_browser_drop_raw.json` | 两个源的原始读数（含逐请求状态码与响应体） |

复跑命令：

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/job-upload/10_server_probe.py 127.0.0.1:5196     # 服务端 24 步（会自建/自清 inbox 内测试文件）
# 浏览器：打开 http://127.0.0.1:5195/feicui/ 与 http://localhost:5164/feicui/，各执行 03_drop_probe.js 的内容
cd web && npm run build                                                 # EXIT=0（见 §7）
```

## 7. 构建与提交

- `npm run build` ⇒ **EXIT=0**；产物 `dist/assets/index-DrO3OyGX.js` 命中 `dropzone`×6、`/jobs/upload`×1、
  「高级：手输服务器路径」×1、「拖入 PDF 文件」×1、「只接受 .pdf 文件」×1；CSS `index-DOgS__22.css` 命中 `dropzone`×8。
- 提交：**见本文件所在提交之后的补记行**（首次提交哈希由下一提交登记，同仓既有做法）。

## 8. 未完成项 / 继续命令

- **规范未登记**：`docs/feicui.spec.md` 归 Jing 并行线，本单**未动**；该 additive 端点（§3.1 E1 的
  「上传入口」）与 `inbox/` 落点需由 Jing 在规范中登记（含错误码 `EMPTY_BODY` / `NOT_A_PDF` /
  `PAYLOAD_TOO_LARGE` 三值——它们是 §3.2 S-6 码族之外的**本端点自定义码**）。
- **大文件未真传**：372 MB 源 PDF 未跑（本单以「调小阈值 + 分块中断」证明机制；如需真传，命令见 §6）。
- **探针遗留数据（有意保留）**：`inbox/20261011/` 下 3 个 `拖曳测试-*.pdf`（各 842 B）＋ 库内 3 个探针 job
  （`job-2c0f3b7f…` / `job-319ef7bb…` / `job-1b316b7a…`）；它们是 E1 的输入，删除会让既有 job 的输入缺档。
  若要清理：先确认 job 终态再删文件（**不要**直接删 job 行）。
- 若要撤掉本单：删 `server/app/uploader.py` ＋ 回退 `routers/jobs.py` / `config.py` / `models.py` /
  `web/src/api/upload.js` / `JobsPage.vue` / `base.css`；`inbox/` 与 `.gitignore` 两行可一并撤。
