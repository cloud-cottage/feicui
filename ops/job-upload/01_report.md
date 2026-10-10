# 拖曳上传（`POST /api/jobs/upload`）· 实现与证据报告（Kong / feicui）

> **本文件的收口范围**：上一单（E8 拖曳上传）的**证据与报告回填** ＋ 本轮 **两件窄修复**
> （① E1 的 G-6 真缺陷；② 上传单文件上限 512 MiB ⇒ 5 GiB）。**原始读数一律从
> `ops/job-upload/*_raw.txt` / `*.json` 逐条转录，不改写**（凡与旧稿不一致处，就地标出并说明成因）。

- 线：feicui（`/Users/kevin/bistro/xiai/feicui`，main）· 角色：Kong（实现 / 窄修复）
- 需求（Kevin 2026-10-10）：「新建 job（E1）」页的 `pdf_path *` 输入框改为**拖曳文件**，不必手动键入。
- 已裁定两条口径：① **拖动上传为主 ＋ 保留折叠「高级：手输服务器路径」**（默认收起）；② 落点
  **`feicui/inbox/<yyyymmdd>/<原文件名>.pdf`，同名同内容复用**（幂等、不重复占盘）。
- 铁律（浏览器事实）：拖入的 `File` **不带本地路径** ⇒ 必须上传落盘拿服务器侧路径，才能调 E1。
- 追加裁定（Kevin 2026-10-11，本单同批收口）：**上传单文件上限默认值 512 MiB ⇒ 5 GiB（5368709120 B）**。
- 规范：`docs/feicui.spec.md` 现为 **v1.21（E8 落条）→ v1.22（2026-10-11，Jing 落 5 GiB 裁定）**；
  **本单未改 `docs/**` 一字**。
- 起手 HEAD：`d500c16`（E8 实现 ＋ 36 步服务端与两源 drop 证据）；本单提交见 §11。

## 0. 本单两件（窄修复）总览

| # | 件 | 性质 | 落点 | 读数锚 |
| --- | --- | --- | --- | --- |
| ① | **E1 的 G-6 真缺陷**：`pdf_path` 指向「**存在但非 PDF**」的文件 ⇒ 原回 **201（建了 job）**，规范（§3.1 G-6 ＋ §3.4 的 400 枚举）要求 **400 `NOT_A_PDF`** | **实现向契约对齐（E1 契约不变）** | `server/app/routers/jobs.py` | §6（四例自证 ＋ 修复前后对比） |
| ② | **上传单文件上限默认 512 MiB ⇒ 5 GiB** | **改数值**（「有上限 / 有默认值 / 可改」三件口径不变；§3.19.2 明写改数值不需升规范） | `server/app/config.py` | §7（三条真跑复验） |

> **红线复核**：不碰 `docs/**`（Jing v1.22 并行线）、`xiai/**`、`ctrl/**`、`web/**`、三采集库与三采集包；
> **E1 的成功响应形状与 409 语义一字未改**；未 `git add -A`；未 push。

## 1. 改动面

| 文件 | 性质 | 说明 |
| --- | --- | --- |
| `server/app/uploader.py` | **新增** | 落盘核心：文件名清毒 / `Request.stream()` 分块写盘 / `%PDF-` 魔数 / 上限中断 / sha256 / 幂等与同名异内容分流 |
| `server/app/routers/jobs.py` | 追加路由 ＋ **本单窄修** | `POST /api/jobs/upload`（**additive**）；**本单**：E1 提交路径加 **G-6 magic 校验**（建 job **之前**，见 §6） |
| `server/app/config.py` | 追加常量＋Settings ＋ **本单窄修** | `UPLOAD_MAX_BYTES_DEFAULT`（**本单 512 MiB ⇒ 5 GiB**）、`UPLOAD_CHUNK_BYTES_DEFAULT=1 MiB`、`INBOX_DIRNAME="inbox"` |
| `server/app/models.py` | 追加模型 | `JobUploadResponse`（7 字段，形状即契约） |
| `web/src/api/upload.js` | **新增** | XHR 上传（**fetch 给不了上传进度**）；`X-Filename` 走 URL-encoded UTF-8 |
| `web/src/pages/JobsPage.vue` | 改前端 | 拖放区（高亮 / 点击选文件）＋进度条＋只读回显＋**可见错误**＋折叠「高级：手输服务器路径」；`form.pdf_path` 仍走**原 E1** |
| `web/src/styles/base.css` | 追加样式 | `.dropzone` / `.uploadbox` / `.advanced`：**色值全走既有 token** |
| `.gitignore` | 追加 | `inbox/`（用户源 PDF，运行时数据）＋ `ops/job-upload/fixtures/`（脚本运行时产物） |
| `ops/job-upload/**` | **新增证据** | 可复跑脚本＋原始读数（见 §10） |

**本单（窄修复）只动两处**：`server/app/routers/jobs.py`（E1 的 G-6 校验）＋ `server/app/config.py`（上限默认值）。

## 2. 端点契约（§3.19 E8；**本单未改**）

```
POST /api/jobs/upload          （5196；经 5195/5164 的 /feicui/api 代理同构）
请求：裸字节流（**不走 multipart**）
  Content-Type: application/pdf（也容 application/octet-stream；缺失 / 其他 ⇒ 400 BAD_CONTENT_TYPE）
  X-Filename: <URL-encoded UTF-8 文件名>
      ⇒ 回退 Content-Disposition 的 filename* / filename ⇒ 再回退 upload.pdf（一律清毒）
  Body: PDF 字节（**分块读，内存恒定**）  ·  无查询参数（未白名单 ⇒ 400 UNSUPPORTED_PARAM）
响应 201（新写入）/ 200（幂等复用），application/json：
  {pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}
错误（**一律结构化 JSON，绝不 HTML 错误页**）：
  400 {"error":"BAD_CONTENT_TYPE",…}   非白名单 Content-Type
  400 {"error":"EMPTY_BODY",…}         空体（0 字节）
  400 {"error":"NOT_A_PDF",…}          首字节非 %PDF- / 短于 5 字节
  400 {"error":"UNSUPPORTED_PARAM",…}  未白名单查询参数
  413 {"error":"PAYLOAD_TOO_LARGE",…, limit_bytes, declared_bytes|received_bytes}  超单文件上限
       （**上限默认 5 GiB = 5368709120 B**，见 §7；`FEICUI_UPLOAD_MAX_BYTES` / config.json 可改）
```

- **`pdf_path` ＝ 绝对服务器侧路径**（`/…/feicui/inbox/<yyyymmdd>/<原名>.pdf`）；`rel_path` ＝ 相对 `FEICUI_ROOT`（`inbox/<yyyymmdd>/<原名>.pdf`）；两者都在 §3.1 E1 的「绝对或相对 `feicui/`」口径内、**可直接交给 E1**。
- **幂等**：同名同内容 ⇒ 不重写（`idempotent:true`，目标 `mtime` 不变）；同名异内容 ⇒ **绝不覆盖** ⇒ `<stem>-<sha256[:8]>.pdf`（`dedup_suffix:true`）。
- **零 DB 写、不建 job**：`uploader.py` 不 import `repository`/`db`，端点无任何 SQL（实测见 §3-⑪）。

## 3. 服务端自测读数（`ops/job-upload/10_server_probe.py`，**exit 0**，`10_server_probe_raw.txt/.json`）

靶机＝ **5196 活端点**（该轮 PID `23048`，启动 06:41:43）。**共 36 步，failed ＝ 0**（`summary.total_steps=36`）。

> **诚实登记（与旧稿不一致）**：旧稿本节写「共 **24** 步」且 ⑪ 记 `jobs 5→5`；**现行 raw（06:46 重跑）为
> 36 步**、⑪ 记 `jobs 8→8`（因重跑时库内已有前一轮的 3 条探针 job）。本节一律按**现行 raw 逐条转录**。

| # | step | 读数（转录 raw） |
| --- | --- | --- |
| 1 | `env` | target `127.0.0.1:5196`；python `feicui/venv/bin/python`；time `2026-10-11 06:46:03` |
| 2 | `fixtures` | `drop-probe.pdf` 841 B / sha `29ba9d62f02daaaf…`；`drop-probe-v2.pdf` 1219 B / sha `e177bd8f106ed944…` |
| 3 | `db_before` | `jobs 8` / `job_pages 35` / `stamps 89` / stamps 指纹 `915597acf0912febaeb8a6556f4b59450132d19ca5c517ca87f6ac78e89bf732` |
| 4 | `01_first_upload` | **201** `application/json`；`bytes 841`；`sha256 29ba9d62f02daaaf118a35d4499463f8030b9db7ed8ae315c9553dfe3caaf7fb`；`idempotent false` / `dedup_suffix false` |
| 5 | `01_target` | 盘上 `size 841`、`sha256_on_disk` **＝响应 sha256**（`sha256_match true`）；`bytes_match true`；`pdf_path` **绝对**且指向文件；`rel_path` 为 root 相对；`json_not_html true`；**`exactly_7_fields true`** |
| 6 | `02_idempotent_same` | **200** `idempotent true`；`same_path true`；`mtime_ns 1791672364201350628 → 1791672364201350628`（**不变**） |
| 7 | `03_same_name_diff_content` | **201** `dedup_suffix true` ⇒ `…-e177bd8f.pdf`；`original_sha_unchanged true` |
| 8 | `03_new_target` | 新文件 `sha256_on_disk` ＝ `sha_expected`（`content_match true`） |
| 9 | `04_not_a_pdf` | **400** `NOT_A_PDF`（`magic:"this is "`）；`landed false` |
| 10 | `05_empty_body` | **400** `EMPTY_BODY` |
| 11 | `06_short_body` | **400** `NOT_A_PDF`（`received_bytes:3`） |
| 12–15 | `07_sanitize` ×4 | `../../../etc/passwd.pdf`⇒`passwd.pdf`；`/tmp/abs-evil.pdf`⇒`abs-evil.pdf`；`..\..\win-evil.pdf`⇒`win-evil.pdf`；`ctl\x01\x02evil.pdf`⇒`ctlevil.pdf` —— **4/4 全部落在 `inbox/20261011/` 内**（`escapes_inbox false`） |
| 16 | `07_sanitize_long` | 300 字名 ⇒ 落成 70 字；stem **198 字节 ≤ 200**；后缀仍为单个 `.pdf` |
| 17 | `07c_bad_content_type` | **400** `BAD_CONTENT_TYPE`（`allowed:[application/octet-stream, application/pdf]`）；`landed false` |
| 18 | `07c_missing_content_type` | **400** `BAD_CONTENT_TYPE`；`landed false` |
| 19 | `07c_octet_stream_ok` | **201** `application/octet-stream` 放行（`probe-ct-ok.pdf`） |
| 20 | `07d_unsupported_query_param` | **400** `UNSUPPORTED_PARAM`（`{'foo':'1'}`）；`landed false` |
| 21 | `07e_sanitize_unit` | 单测清毒表（`../../etc/passwd.pdf`⇒`passwd.pdf`；``⇒`upload.pdf`；`..`⇒`upload.pdf`；`\x00\x01.pdf`⇒`pdf.pdf`）；`long_bytes 198` |
| 22 | `07e_containment_guard` | 强制越界被挡 ⇒ **400 `BAD_FILENAME`** |
| 23 | `08_content_disposition` | **201**；`filename*` 回退 ⇒ `disp-回退名.pdf`（`match true`） |
| 24 | `09_too_large_declared_content_length` | 上限 65536（config.json）；发 205642 B ⇒ **413** `…（**已在落盘过程中中断**，未写满盘）`、`received_bytes 205642`；`landed false`、`temp_residue []` |
| 25 | `09c_too_large_midstream_chunked` | **chunked（无 Content-Length）** ⇒ **413**；`received_bytes 205642`；`interrupted_before_full_body false`（**见下诚实登记**）；`landed false`、无残留 |
| 26 | `09d_midstream_abort_evidence` | **慢速 chunked**：`status 413`；`received_bytes 131072`、`sent_at_abort 131072` / `total 524288` ⇒ **`aborted_before_full_body true`**；临时件**峰值 65536 ≤ 上限**（`peak_within_limit true`） |
| 27 | `09b_declared_too_large` | 声明 `Content-Length: 999999999`（实发 842 B）⇒ **413**（`declared_bytes 999999999`）⇒ **未落盘即拒** |
| 28 | `10_after_config_removed` | 删掉测试 config 后再传同尺寸 ⇒ **201**（205642 B）⇒ 证明限值确由配置生效、且已恢复默认 |
| 29 | `db_after` | `jobs 8` / `job_pages 35` / `stamps 89` / stamps 指纹同上（**逐位不变**） |
| 30 | `11_zero_db_write` | `jobs_same true` / `job_pages_same true` / `stamps_rows_same true` / `stamps_fingerprint_same true`（8 / 35 / 89） |
| 31 | `12_inbox_listing` | `inbox/20261011/` 13 个文件（含本脚本自建、收尾按名删除者与上一轮遗留） |
| 32 | `13_e1_missing_file` | **400**；**顶层 `error` ＝ null**，`detail ＝ {error:"PDF_NOT_FOUND", detail:"…"}`（**码嵌于 `detail` 内**，§3.4 允许 `detail` 为 object） |
| 33 | `13_e1_existing_non_pdf` | **201** —— **⚠ 这就是 E1 的真缺陷**（建出 `job-29c550c740b14f7cb57f796f15b40700`，已成垃圾 job；**本单已修，见 §6**） |
| 34 | `13_e1_input_upload` | **201** ⇒ `inbox/20261011/probe-e1-keep-1791672365.pdf`（E1 的输入） |
| 35 | `13_e1_created` | **201** `{job_id: job-19e230fe32764c69981724ddd3f231ae, state: QUEUED, total_pages: 1, created_at: …}`；**`has_4_fields true`** |
| 36 | `13_e1_conflict` | **409** `ACTIVE_JOB_EXISTS`；`job_id job-19e230fe32764c69981724ddd3f231ae`（**＝既有活跃 job**，`same_job_id true`） |

> **诚实登记（⑨c）**：`09c` 的 `received_bytes` 等于发满的 205642 —— 客户端把 4 块**一次性**交给内核缓冲、
> 服务端读满即断；故「**比请求体更早停**」这一点靠 **`detail` 的分支字符串（「已在落盘过程中中断」）＋
> 盘上零字节**来证，**不靠**字节计数小于全量来证。**真正的「边写边判」直接证据在 `09d`**
> （响应早于整车收完到达 ＋ 临时件峰值 ≤ 上限）。

## 4. 真浏览器 drop 全链路读数（`ops/job-upload/03_drop_probe.js`，`03_browser_drop_raw.json`）

**两个源各跑一次**：`http://127.0.0.1:5195/feicui/`（直连 dev）与 `http://localhost:5164/feicui/`（印源反代）。
一律用 **JS 构造的 `DataTransfer` ＋ 真 `File`**（内容＝真 `%PDF-` 字节）派发 `drop`；网络状态码由页内包装
`XMLHttpRequest.prototype.send` / `window.fetch` **实测记录**（非推断）。

| 断言 | 5195 直连 | 5164 反代 |
| --- | --- | --- |
| 拖放区存在（`role=button` / `tabindex=0`）、内含 `input[type=file]`（`accept=application/pdf,.pdf`） | ✔ | ✔ |
| `pdf_path` 的**可见输入框已消失**：`<details>` 外的 `input[type=text]` ＝ **3 个**（`如 1` / `如 544` / `如 32`） | ✔ | ✔ |
| 折叠块存在、**默认收起**（`details_open_by_default false`）、摘要＝「高级：手输服务器路径」、内含原输入框 | ✔ | ✔ |
| `dragover` ⇒ 高亮；`dragleave` ⇒ 恢复 | ✔ / ✔ | ✔ / ✔ |
| `drop` ⇒ **`POST /feicui/api/jobs/upload` 201**（落盘 `拖曳测试-5195-1791672413.pdf` / `拖曳测试-5164-1791672417.pdf`，各 842 B） | ✔ 201 | ✔ 201 |
| 表单 `pdf_path` ＝ **响应里的服务器侧路径**（`form_pdf_path` 逐字等于响应 `pdf_path`） | ✔ | ✔ |
| 「已就绪」只读回显（文件名 ＋ 842 B ＋ sha256 `945e97c0…` ＋ 新写入） | ✔ | ✔ |
| 点「建 job」⇒ **E1 `POST /feicui/api/jobs` 201** | ✔ `job-b087ca00fcde43f9974e32a581507e1b`（`total_pages 1`） | ✔ `job-0366b502833a41d9a26ae8f25f725460`（`total_pages 1`） |
| 本机记录 `localJobs` 写入（`{job_id, pdf_path}` 同源） | ✔ | ✔ |
| 非 PDF 内容 ⇒ 服务器 **400 `NOT_A_PDF`** ＋ **可见**错误文案（`上传被拒：… NOT_A_PDF …`） | ✔ 400 | ✔ 400 |
| 非 `.pdf` 扩展名 ⇒ 前端拦下、**不发上传请求**（`txt_requests_sent 0`） | ✔ | ✔ |
| `net` 三条（upload 201 / jobs 201 / upload 400） | ✔ | ✔ |

> **诚实登记（与旧稿不一致）**：旧稿 §4 记的 job 为 `job-2c0f3b7f…`（5195）/ `job-319ef7bb…`（5164）；
> **现行 raw（06:47）记的是 `job-b087ca00…`（5195）/ `job-0366b502…`（5164）**（前一轮重跑所致）。本节按现行 raw 转录。

### 4.1 **100 MB 进度读数**（AC-71；`ac71_progress`，**5195 直连**）

| 项 | 读数 |
| --- | --- |
| 文件 | `进度测试-100MB-1791672428120.pdf`，`size 104858442` B（＝**100.0 MiB**），`magic %PDF-` |
| XHR 进度事件数 | **2** |
| XHR 不同百分比 | **`[38, 100]`**（`xhr_monotonic_nondecreasing true`） |
| UI 快照数 / UI 读数 | 2 / `[0]`（`ui_bar_widths_seen ["0%"]`） |
| 完成态文案 | `已就绪：源文件 进度测试-100MB-…pdf （100.0 MB）已落盘到服务器。…` |
| 上传请求 | **201**，`bytes 104858442`，`sha256 960b43f56b568853b0d7901a006878a8e308b827b440402b0be9f39b740550fd` |
| 实测耗时 | `elapsed_s 0.27` |

> **诚实登记**：AC-71 的判据（**≥ 2 个不同百分比、单调不降**）由 **XHR 层读数满足**（38 → 100）；
> UI 快照仅取到 2 次、且都在传输极早期，故 UI 侧只捕到 `0%`（**探针轮询太粗**，非实现缺进度——
> 实现用 `xhr.upload.onprogress` 绑定，见 `web/src/api/upload.js`）。

## 5. AC-62〜AC-71 逐条对应读数（§7 v1.21，逐条给出方给出的证据）

| AC | 判据（§7 摘要） | 本单对应读数 | 判定 |
| --- | --- | --- | --- |
| **AC-62** 拖曳上传全链路 | drop ⇒ `POST /api/jobs/upload` ⇒ 表单拿到服务器侧 `pdf_path` ⇒ E1 `201` | §4：两源均 upload **201** ＋ 表单 `pdf_path` ＝ 响应 `pdf_path` ＋ E1 **201**（`job-b087ca00…` / `job-0366b502…`） | **满足** |
| **AC-63** 非 PDF 判负（`400 NOT_A_PDF`） | 首字节非 `%PDF-` ⇒ `400` ＋ 机器码 `NOT_A_PDF`；`inbox/` 无新增 | §3-⑨：**400** `NOT_A_PDF`、`landed false`；§4：两源 upload **400** `NOT_A_PDF` | **满足** |
| **AC-64** 空体（`400 EMPTY_BODY`） | 0 字节体 ⇒ `400` ＋ `EMPTY_BODY` | §3-⑩：**400** `EMPTY_BODY` | **满足** |
| **AC-65** 超限（`413`，不得先写满盘） | 超上限 ⇒ `413 PAYLOAD_TOO_LARGE`；无残留；**边写边判** | §3-㉔/㉕/㉖/㉗：413 三路 ＋ `09d` **响应早于整车收完** ＋ 临时件**峰值 ≤ 上限**；§7：declared 6 GiB ⇒ 413 **未落盘** | **满足** |
| **AC-66** 同名同内容幂等 | 连传两次 ⇒ 二次 `200 idempotent:true`、`mtime`/`sha256` 不变、文件数不变 | §3-⑥：**200** `idempotent true`、`mtime_ns` **不变**、`same_path true` | **满足** |
| **AC-67** 同名异内容不覆盖 | 再传 ⇒ `201 dedup_suffix:true` 落 `-<sha8>`；原文件字节/mtime 不变 | §3-⑦/⑧：**201** `dedup_suffix true`、`original_sha_unchanged true`、新件 `content_match true` | **满足** |
| **AC-68** 零 DB 写 | 调 upload（成/败各 ≥1 次）前后三表行数＋有序全字段 sha256 不变 | §3-㉚：`jobs 8→8`/`job_pages 35→35`/`stamps 89→89`、指纹逐位不变；§7：700 MiB 真传后三表仍 **5/32/89** | **满足** |
| **AC-69** E1 契约未变 | ① 不存在 ⇒ `400 PDF_NOT_FOUND`；② 非 PDF 既有文件 ⇒ `400 NOT_A_PDF`；③ 同 `pdf_path` 活跃 ⇒ `409 ＋既有 job_id`；④ 正常新建 ⇒ `201`；且 E8 落盘路径喂 E1 走 ④ | §6 四例：①**400**`PDF_NOT_FOUND` ②**400**`NOT_A_PDF`（**本单修复后**）③**409**＋既有 `job_id` ④**201**（4 字段）；§3-㉟/㊱ 同款；§4 E8→E1 联调 **201** | **满足**（②原为 201，**本单修复**） |
| **AC-70** 折叠手输仍在且默认收起 | 标题逐字「高级：手输服务器路径」、默认收起；展开后可用 | §4：两源 `details_present true` / `details_open_by_default false` / `details_summary_text 「高级：手输服务器路径」` / `advanced_input_inside true` | **满足** |
| **AC-71** 上传进度可见 | ≥100 MB 传输中出现 **≥2 个不同百分比**、单调不降；`XMLHttpRequest` 进度事件 | §4.1：XHR **2 个不同百分比 `[38,100]`**、`monotonic true`；实现绑定见 `upload.js` | **满足**（UI 侧读数偏粗，见 §4.1 登记） |

## 6. **E1 的 G-6 真缺陷 —— 修复前后对比 ＋ 四例自证**（`11_e1_g6_fix_probe.py`，exit 0）

### 6.1 缺陷与契约依据

- **现象**：`POST /api/jobs` 给一个「**存在但非 PDF**」的 `pdf_path` ⇒ 原实现只查 `is_file()` ⇒ 被当 1 页 PDF
  **收下、建 job（201）**（§3-㉝ 实测：`job-29c550c7…`）。
- **规范（逐字）**：§3.1 表下注 **G-6**「**非 PDF 文件的判定…必须以内容为准——`%PDF-` magic 校验（文件
  **前 1024 字节内**出现 `%PDF-`）…校验不过 ⇒ **`400`**（`error = NOT_A_PDF`）」＋ §3.4 表 `400` 行枚举
  含 `PDF_NOT_FOUND` / `NOT_A_PDF`（`{detail: <string 或 object>, error?: <机器码>}`）。
- **与 E8 口的关系（防误用，§3.19.4 逐字）**：E8 收新字节用**首字节即须为** `%PDF-` 的**严**判定；
  E1 判既有文件用 G-6 的**宽松**判定（**前 1024 字节内**）——「**两者是不同口的不同严格度，不互相代替、
  本版不统一**」⇒ **本单照 G-6 实现 E1，不照搬 E8 判据**。

### 6.2 修复 diff 要点（`server/app/routers/jobs.py`，**只加不改**）

```python
# 新增（模块级常量 + 纯函数）
PDF_MAGIC = b"%PDF-"
PDF_MAGIC_SCAN_BYTES = 1024
def _pdf_has_magic(pdf_abs: Path) -> bool:      # G-6：前 1024 字节内含 %PDF- 即算 PDF
    try:
        with pdf_abs.open("rb") as fh:
            head = fh.read(PDF_MAGIC_SCAN_BYTES)
    except OSError:
        return False
    return PDF_MAGIC in head

# create_job() 内：is_file() 之后、**建 job / 读页数 / 冲突判定之前**
    if not _pdf_has_magic(pdf_abs):
        raise HTTPException(status_code=400,
            detail={"error": "NOT_A_PDF",
                    "detail": f"pdf_path 存在但非 PDF（前 {PDF_MAGIC_SCAN_BYTES} 字节内无 %PDF- magic）：{pdf_abs}"})
```

- **校验顺序**：① 路径存在性（既有 `400 PDF_NOT_FOUND`）→ ② **G-6 magic**——**两者都在建 job / 入队 / 写任何行之前**。
- **未改**：`201` 成功响应形状（4 字段）、`409` 语义与体、`page_range` / `422` 等既有分支、错误体风格
  （沿用本文件既有的 `HTTPException(detail={"error":…, "detail":…})`；§3.4 允许 `detail` 为 object）。

### 6.3 四例自证读数（活端点 `127.0.0.1:5196`，基线 `jobs 5 / job_pages 32 / stamps 89`）

| 例 | 请求 | HTTP | 体（原文） | 三表行数 |
| --- | --- | --- | --- | --- |
| ① 非 PDF（存在） | `pdf_path=ops/job-upload/fixtures/e1-fix-not-a-pdf.txt`（34 B，首 5 字节 `this `） | **400** | `{"detail":{"error":"NOT_A_PDF","detail":"pdf_path 存在但非 PDF（前 1024 字节内无 %PDF- magic）：…"}}` | **不变**（`jobs_same/job_pages_same/stamps_same` 全 true） |
| ② 不存在路径 | `pdf_path=…/fixtures/definitely-missing-e1-fix.pdf` | **400** | `{"detail":{"error":"PDF_NOT_FOUND","detail":"pdf_path 不存在或不是文件：…"}}` | **不变** |
| ③ 真 PDF | `pdf_path=ops/job-upload/fixtures/e1-fix-real.pdf`（842 B，`%PDF-` 头） | **201** | `{"job_id":"job-3c91b5cff4c141bbbcf5e009754aed54","state":"QUEUED","total_pages":1,"created_at":"2026-10-11T06:51:49+08:00"}`（`has_4_fields true`） | `jobs +1`（`stamps` 不变） |
| ④ 同 `pdf_path` 再提交 | 同 ③ | **409** | `{"error":"ACTIVE_JOB_EXISTS","detail":"…","job_id":"job-3c91b5cff4c141bbbcf5e009754aed54","state":"QUEUED",…}`（`same_job_id true`） | **不变** |

### 6.4 修复前后对比

| 用例 | **修复前**（`d500c16`） | **修复后**（本单） |
| --- | --- | --- |
| 存在但非 PDF 的文件 | **201**（建 job；§3-㉝ 留下垃圾 job `job-29c550c7…`） | **400** `NOT_A_PDF`（**不建 job、不写任何行**） |
| 不存在的路径 | 400 `PDF_NOT_FOUND`（原已正确） | **400** `PDF_NOT_FOUND`（不变） |
| 真 PDF | 201 | **201**（不变） |
| 同 `pdf_path` 活跃 job | 409 ＋既有 `job_id` | **409** ＋既有 `job_id`（不变） |

> 命令：`cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/job-upload/11_e1_g6_fix_probe.py 127.0.0.1:5196`
> → `[exit] 0`；raw 见 `11_e1_g6_fix_probe_raw.txt/.json`。

## 7. **上传单文件上限 512 MiB ⇒ 5 GiB** —— 三条真跑复验（`12_upload_limit_5gib_probe.py`，exit 0）

- **改动**：`server/app/config.py` 的 `UPLOAD_MAX_BYTES_DEFAULT`：`512 * 1024 * 1024` ⇒ **`5 * 1024 * 1024 * 1024`**（＝ **5368709120 B**）；覆盖机制（`FEICUI_UPLOAD_MAX_BYTES` / config.json `upload_max_bytes`）**不变**。
- **依据（Kevin 2026-10-11）**：实际拖入 `~/Downloads/秦印类编 检索版.pdf` ＝ **1.88 GiB / 851 页**（被现上限拒，
  `declared 2,019,683,630 B`）；`福庵印缀 原版 高清.pdf` ＝ **1.14 GiB / 236 页**；本机 `df` 余量 **191 GiB**。
  **下游代价**（按 8.67 s/页实测口径）：851 页 ⇒ 单核 ≈ **2.0 h**、`w=4` ≈ **0.8 h**。

| # | 复验 | 读数（转录 raw） | 判定 |
| --- | --- | --- | --- |
| ① | **活端点自报 `limit_bytes`** | 声明 `Content-Length: 6442450944`（6 GiB，实发 36 B）⇒ **413**，体 `{"error":"PAYLOAD_TOO_LARGE","detail":"请求体声明 6442450944 B 超过上限 5368709120 B（**未落盘即拒**）","limit_bytes":5368709120,"declared_bytes":6442450944}` | **满足**（`limit_bytes_is_5gib true`） |
| ② | **> 新上限 ⇒ 413 且未落盘** | 同上一次请求：`landed false`、`inbox_count_delta 0`（`inbox/20261011/` **零新增**） | **满足** |
| ③ | **≥512 MiB 且 < 5 GiB ⇒ 真的放行** | 造 **734003200 B（700 MiB）**、首 5 字节 `%PDF-` 的临时文件真上传 ⇒ **201**；`bytes 734003200`；源 sha ＝ 盘上 sha ＝ 响应 sha ＝ **`09275c67aa9e529b02e40e76f8443af5b7dd2de22d21c8b484c0e32cdca600f0`**（`sha_match true`）；`elapsed_s 0.78` | **满足** |

**收尾 / 磁盘**：源临时文件与 inbox 落盘件**均已删除**；`inbox/20261011/` 复原（9 → **9** 文件，`inbox_restored true`）。
**磁盘占用峰值**（源临时件 ＋ inbox 落盘件同点共存）＝ **1468006400 B ≈ 1400 MiB**（按两文件尺寸计），
**已回收 1468006400 B ≈ 1400 MiB**。`df` 读数（字节）：**before `204772085760` → 造源件后 `204038082560` → 收尾后 `204755439616`**。

> 命令：`cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/job-upload/12_upload_limit_5gib_probe.py 127.0.0.1:5196`
> → `[exit] 0`；raw 见 `12_upload_limit_5gib_probe_raw.txt/.json`。
> **未**用 1.88 GiB 真书跑全链路（会派生 851 页真 job 并触发 OCR）——按裁定不跑。

## 8. 重启与活端点（**单路**）

一律 `POST http://127.0.0.1:5555/api/stop|start {"sid":"feicui-api"}`；**未用 `startAll`、未用 `pkill`**（未动 5195 / 5164 / 5555 任何进程）。

| 次序 | 目的 | 停前 PID（lstart） | 面板 start 返回 | 起后 PID（lstart） | 活端点核验 |
| --- | --- | --- | --- | --- | --- |
| 第 1 次 | 载入 **E1 的 G-6 修复** | `30983`（Sun Oct 11 06:45:56） | `{"ok":true,"state":"running","pid":38257}` | **`38257`**（Sun Oct 11 06:50:18） | `GET /api/health` ⇒ `ok:true`、`journal_mode:wal`、`prod_db:true`；`POST /api/jobs/upload` 空体 ⇒ **400**（**新代码已生效**：旧进程此路径为 404） |
| 第 2 次 | 载入 **5 GiB 上限** | `38257` | `{"ok":true,"state":"running","pid":38847}` | **`38847`**（Sun Oct 11 06:50:38） | `GET /api/health` ⇒ `ok:true`；`limit_bytes` 由 §7-① 实测自报 **5368709120** |

## 9. 生产库现状交底 ＋ 探针清理

- **Kevin 已清理上一单遗留的 8 条探针 job**：`jobs **13 → 5**`、`job_pages **40 → 32**`、`stamps **89 行指纹未变**`；
  备份在
  **`/Users/kevin/.hermes/profiles/zang/cache/scratch/yinpu.backup.20261011_064809.db`**。
- **本单探针的 DB 影响（自己新建的、自己清理回）**：
  - `11_e1_g6_fix_probe.py`：③ 建 **1** 条 job（`job-3c91b5cff4c141bbbcf5e009754aed54`）⇒ 收尾**先备份**（`sqlite3` 在线备份
    `/Users/kevin/.hermes/profiles/zang/cache/scratch/yinpu.backup.20261011_065149.db`，647168 B）**再删**该 job
    （`deleted_pages 1`、`deleted_jobs 1`）。
  - `12_upload_limit_5gib_probe.py`：**零 DB 写**（E8 只落盘）。
- **三数（本单收尾，＝基线）**：`jobs **5**` / `job_pages **32**` / `stamps **89**`；stamps 指纹
  `915597acf0912febaeb8a6556f4b59450132d19ca5c517ca87f6ac78e89bf732` **逐位未变**（`db_final` 四项恢复标志全 true）。
- `inbox/20261011/` 现存 9 个文件**均非本单所建**（上一轮探针与 `zang_probe.pdf` 等）；
  **本单自建者已全部回收**（见 §7 收尾）。未动三采集库 / 三采集包。

## 10. 证据文件（均在 `ops/job-upload/`，可复跑）与复跑命令

| 文件 | 内容 |
| --- | --- |
| `10_server_probe.py` / `_raw.txt` / `_raw.json` | E8 服务端自测（**36 步**；手写 socket 控 Content-Length / chunked / 中途中断；退出码＝判据） |
| `03_drop_probe.js` / `03_browser_drop_raw.json` | 真浏览器 drop 探针的页面内表达式 ＋ 两源原始读数（含逐请求状态码与 100 MB 进度） |
| **`11_e1_g6_fix_probe.py` / `_raw.txt` / `_raw.json`** | **本单新增**：E1 的 G-6 四例自证（含自建 job 的清理与三表复位读数） |
| **`12_upload_limit_5gib_probe.py` / `_raw.txt` / `_raw.json`** | **本单新增**：5 GiB 上限三条复验（含 700 MiB 真上传与回收读数） |

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/job-upload/10_server_probe.py 127.0.0.1:5196    # E8 36 步（自建/自清 inbox 测试文件）
./venv/bin/python ops/job-upload/11_e1_g6_fix_probe.py 127.0.0.1:5196 # E1 四例（③ 会建 job→脚本自行清理）
./venv/bin/python ops/job-upload/12_upload_limit_5gib_probe.py 127.0.0.1:5196  # 413×2 + 700 MiB 真上传（自清）
# 浏览器：打开 http://127.0.0.1:5195/feicui/ 与 http://localhost:5164/feicui/，各执行 03_drop_probe.js 的内容
```

## 11. 构建与提交

- 前端**本单未动**；`npm run build` 读数（上一轮）⇒ **EXIT=0**；产物 `dist/assets/index-DrO3OyGX.js` 命中
  `dropzone`×6、`/jobs/upload`×1、「高级：手输服务器路径」×1；CSS `index-DOgS__22.css` 命中 `dropzone`×8。
- **本单提交（只暂存自己点名的文件；未 `git add -A`；未 push）**：
  - `server/app/routers/jobs.py`（E1 的 G-6 修复）＋ `server/app/config.py`（5 GiB）＋ 本报告 ＋ 4 个新证据文件。
  - **首次提交哈希由紧随的补记提交登记**（同仓既有做法）；**未**暂存 `docs/**`（Jing v1.22 并行线）。

## 12. 未完成项 / 继续命令

- **`inbox/` 清理策略**未定 ⇒ §9-R41（本版不实现清理）；本单自建件已自行回收。
- **大文件真书未跑全链路**：1.88 GiB 真书按裁定**不跑**（会派生 851 页真 job 并触发 OCR）；机制由 §7-③（700 MiB 真传）证。
- **AC-71 的 UI 侧读数偏粗**（§4.1 登记）：实现有 `xhr.upload.onprogress` 进度，探针轮询间隔过大只捕到 `0%`。
- 若要撤掉 E8：删 `server/app/uploader.py` ＋ 回退 `routers/jobs.py` / `config.py` / `models.py` /
  `web/src/api/upload.js` / `JobsPage.vue` / `base.css`；`inbox/` 与 `.gitignore` 两行可一并撤。
- 若要撤掉本单两件窄修复：回退 `routers/jobs.py` 的 `_pdf_has_magic` 与该处 400 分支；
  `config.py` 的 `UPLOAD_MAX_BYTES_DEFAULT` 改回 `512 * 1024 * 1024`。
