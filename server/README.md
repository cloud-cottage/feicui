# feicui API 薄接口层（FastAPI）+ 执行层 worker 池 · 阶段 1a / **1b-i**

> **角色**＝Kong（工程师）。**本目录**＝`/Users/kevin/bistro/shu/feicui/server/**`（阶段 1a 新建）。
> **唯一权威规范**＝`../docs/feicui.spec.md` **v1.1**（md5 `4264927baf24bb7f48e12366cd861fe7`，409 行）。
> 本文件只写**实现说明**；**口径冲突时以规范为准**（规范 §0.1）。**偏差与规范缺口**逐条列在 `REPORT_1a.md`。

## 1. 本单（1a）做了什么

| 项 | 规范锚点 | 实现 |
| --- | --- | --- |
| 数据层（**只加法**）：新增侧表 `jobs` / `job_pages` | §4.1（D-1 / D-2 的承载）＋ §2.2 / §2.3 | `app/migrations.py` |
| 幂等约束与索引 | §2.4 / §4.1 D-2 | `uq_jobs_active_pdf_path`（部分唯一索引）／`UNIQUE(job_id,page)`／`idx_stamps_pdf_page`／`uq_stamps_pdf_page_idx` |
| 独立迁移入口（可重复执行、幂等） | §4 | `app/migrations.py`：`python -m app.migrations`（`schema_migrations` 记账 + 全部 `IF NOT EXISTS`） |
| FastAPI 应用骨架（可启动、可停、分层清晰） | §1.1 / §3.2 S-4 | `app/main.py`（应用工厂）＋ `app/routers/jobs.py`（只做 HTTP 形状）＋ `app/repository.py`（库内真值） |
| E1 `POST /api/jobs` | §3.1 E1 / §3.2 S-5 / S-6 | `app/routers/jobs.py::create_job` |
| E2 `GET /api/jobs/{job_id}` | §3.1 E2 / §3.2 S-1 / S-2 | `app/routers/jobs.py::get_job` |
| E5 `GET /api/jobs/{job_id}/missing` | §3.1 E5 | `app/routers/jobs.py::missing` |

**本单不做**（留 1b）：worker 池 / 页级并行 / 真实 OCR 执行 / **E3 分页取结果** / **E4 触发导出** / Vue 前端。
**本单未写**任何 `feicui/web/**` 文件；**未改动** `app.py` / `processor.py` / `export.py` / `stamps` 现有 10 列 / 现有 79 条数据。

## 2. 解释器矩阵（谁用哪个 python，**必须分清**）

| 角色 | 解释器 | 装了什么 | 为什么 |
| --- | --- | --- | --- |
| **接口层 feicui-api（5196，本单）** | `server/.venv/bin/python` | `fastapi` / `uvicorn` / `pydantic`（**3 个包，13 行 freeze**） | 规范 §1.2 I-2：**UI/接口层不得进入热路径**；不装 OCR 栈 |
| **worker（阶段 1b）** | `feicui/venv/bin/python` | `pymupdf 1.28.2` / `paddleocr 3.7.0` / `paddlepaddle 3.3.1` / `numpy 2.3.5` / `opencv-python 5.0.0.93` / …（**86 行 freeze**） | §1.2 I-1：解析与 OCR 仍是**同一份 Python 实现**；§5.2：每 worker 一实例 |
| feicui Streamlit（退役中） | `feicui/venv/bin/python` | 同上（`streamlit 1.63.0`） | §1.4 退役边界 |

**硬约束（Zang 追加口径 1 / 2）**：**不得**把新依赖装进 `feicui/venv`，也**不得**升级/降级它里面任何既有包
（`spike-ocr/` 的性能基线全部依赖这套版本）。本单**未安装、未改动** `feicui/venv` 任何包
（证据：`selftest/evidence/02_main_venv_freeze.txt`，86 行；含 `fastapi` ⇒ 0 命中；`paddleocr` / `numpy` / `opencv-python` 版本未变；`paddleocr,paddle,fitz,numpy,cv2,streamlit` 均可 import）。

**为什么接口层不装 `pymupdf`**：`server/app/**` 内**没有静态** `import pymupdf`（自证：`grep -rnE '^\s*(import|from) (pymupdf|fitz)' server/app` ⇒ 0 命中）。
E1 需要 PDF 页数时，`app/pdfmeta.py` 先**动态可选导入**（装了才用），否则**子进程**调 worker 侧解释器
（`feicui/venv/bin/python`）的 PyMuPDF——即「PDF 解析能力留在 worker 侧环境，接口层保持精简」。

## 3. 分层（S-4：接口层不落业务真值）

```
routers/jobs.py     只做 HTTP：路径/查询参数校验、状态码、响应模型（pydantic 形状锁定）
      │
repository.py       只做业务真值：全部数据一律「每次请求新开连接 → 现查现算」
      │
db.py               sqlite 连接 / 事务 / 只读辅助
      │
migrations.py       侧表与索引的幂等落地（独立入口）
config.py           配置：默认值 < 配置文件 < 环境变量
```

- **没有任何进程内缓存 / 计数器**：重启接口层不丢 job、不丢进度（S-4 判负形态的反面）。
- `app/routers/jobs.py` 内**不含任何 SQL**；`app/repository.py` 内**不含任何 HTTP 概念**。

## 4. 数据模型（侧表字段）

### 4.1 `jobs`（一本书 = 一个 job，§2.1）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | TEXT PK | `job-<uuid4 hex>` |
| `pdf_path` | TEXT NOT NULL | **规范化绝对路径**（同书以不同写法传入时也能命中 S-5 冲突判定） |
| `pdf_name` | TEXT NOT NULL | 书名（＝`stamps.pdf_name` 语义口径：`pdf_path` 的 basename） |
| `book_key` | TEXT | 预留：`config/book_codes.json` 的本地简码（1a 不写，可空） |
| `page_from` / `page_to` | INTEGER | 生效页区间（`page_range`，1-based；未给则＝全书） |
| `chunk_size` | INTEGER NOT NULL | chunk＝页区间（§2.1 / §5.3），默认 8 |
| `total_pages` | INTEGER NOT NULL | **E1 时点快照**（＝已落 `job_pages` 行数）；**E2 一律复算，不读此列** |
| `state` | TEXT NOT NULL | `QUEUED` / `RUNNING` / `PAUSED` / `DONE` / `FAILED_PARTIAL`（§2.2） |
| `cursor_chunk_lo` / `cursor_chunk_hi` | INTEGER | 预留列；**E2 的 `cursor` 由 `job_pages` 复算，不读此列** |
| `rerun` | INTEGER NOT NULL | E1 入参 `rerun`（0/1） |
| `error` | TEXT | 失败原因 |
| `created_at` / `started_at` / `finished_at` / `updated_at` | TEXT | ISO8601 带时区（Asia/Shanghai） |

### 4.2 `job_pages`（页级断点游标落盘，§2.3）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` / `page` | — | **`UNIQUE(job_id,page)`**（页级唯一锚） |
| `pdf_name` | TEXT NOT NULL | 冗余存书名，便于按书复算 |
| `chunk_index` | INTEGER | `(page - page_from) // chunk_size`（0-based） |
| `state` | TEXT NOT NULL | `PENDING` / `RUNNING` / `DONE` / `FAILED` |
| `detected` / `inserted` / `updated` / `skipped` / `ocr_empty` | INTEGER NOT NULL DEFAULT 0 | **页级计数**；E2 的 `counters` ＝对这几列 `SUM()` 复算 |
| `error` / `started_at` / `finished_at` / `updated_at` | TEXT | — |

### 4.3 约束与索引

| 名称 | 对象 | 作用 |
| --- | --- | --- |
| `uq_jobs_active_pdf_path` | `jobs(pdf_path) WHERE state IN ('QUEUED','RUNNING','PAUSED')` | **部分唯一索引**：同书活跃 job 至多 1（§3.2 S-5 的库级兜底） |
| `idx_jobs_pdf_path_state` | `jobs(pdf_path,state)` | 冲突检查 |
| `uq_job_pages_job_page` | 表内 `UNIQUE(job_id,page)`（SQLite 自动索引 `sqlite_autoindex_job_pages_1`） | 页级幂等 |
| `idx_job_pages_job_state` / `idx_job_pages_job_chunk` | `job_pages` | 复算 / chunk 查询 |
| `idx_stamps_pdf_page` | `stamps(pdf_name,page)` | §4.1 **D-2** 要求 |
| `uq_stamps_pdf_page_idx` | `stamps(pdf_name,page,idx)` 唯一 | §2.4 行级幂等（D-2；落地前实测重复组＝**0**） |
| `schema_migrations` | 表 | 迁移记账（幂等证据） |

**WAL（§4.1 D-1）**：迁移入口执行 `PRAGMA journal_mode=WAL` 并**校验返回值**；仅在返回 `wal` 时设置 `synchronous=NORMAL`。
**其余已建对象**（`stamps` / `seals` / `images` / `export_batches` / `export_records`）本单**不触碰**。

## 5. 状态机与「进度真实」（S-1 / S-2）

- `state` 由 `jobs.state` 给出（1a 无 worker ⇒ 建 job 后恒为 `QUEUED`）。
- **`done_pages` 一律复算**：`SELECT COUNT(*) FROM job_pages WHERE job_id=? AND state='DONE'`——**不读任何进程内变量**（S-1）。
- **`total_pages` 一律复算**：`SELECT COUNT(*) FROM job_pages WHERE job_id=?`。
- **`failed_pages` 一律复算**：`state='FAILED'` 的 `page` 升序数组（空则 `[]`，**不省略**）。
- **`counters` 一律复算**：对 `job_pages` 的 5 个计数列 `SUM()`。
- **`cursor` 一律复算**：`chunk_lo` ＝「最小未完成 chunk」（无则 `null`）、`chunk_hi` ＝「最大已完成 chunk」（无则 `null`）。
- **S-2 兜底下行**：`failed_pages` 非空而 `jobs.state='DONE'` ⇒ 返回 `FAILED_PARTIAL`（并记一条 warning 日志）；**只降级、不升级**（绝不把 `QUEUED` 报成 `DONE`）。

**活跃 / 终态口径**（E1 冲突判定与部分唯一索引同源）：
`ACTIVE = {QUEUED, RUNNING, PAUSED}`；`TERMINAL = {DONE, FAILED_PARTIAL}`。
`FAILED_PARTIAL` 不算活跃 ⇒ 允许再次入队（新 `job_id`，旧行保留作审计）。

## 6. 端点

### E1 `POST /api/jobs`
请求：`{pdf_path, page_range?:[from,to], chunk_size?, rerun?}`
行为：校验 → 派生 `total_pages`（给了 `page_range` 取区间宽；否则读 PDF 页数）→ **一个事务内**写 `jobs` + 全部 `job_pages(PENDING)` → `201 {job_id,state,total_pages,created_at}`。
- 同 `pdf_path` **已有活跃 job** ⇒ **`409`**，响应体含**既有 `job_id`**（**绝不静默起第二个**）；并发下同样由部分唯一索引兜底 → 转 `409`。
- `total_pages` 无法派生（读不出 PDF 页数且未给 `page_range`）⇒ **`422`**，体含 `missing: ["total_pages"]`。
- `pdf_path` 不存在 ⇒ `400`（`error=PDF_NOT_FOUND`）；`page_range` 非法/越界 ⇒ `400`。

### E2 `GET /api/jobs/{job_id}`
逐字段（§3.1 E2）：`{job_id, state, total_pages, done_pages, failed_pages[], cursor:{chunk_lo,chunk_hi}, counters:{detected,inserted,updated,skipped,ocr_empty}, started_at, updated_at}`；未知 `job_id` ⇒ `404`。

### E5 `GET /api/jobs/{job_id}/missing?kind=image|text`
`{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}`；`kind` 缺失/非法 ⇒ `400`。
- `kind=image`：范围＝该 job 的 `pdf_name` × `[page_from,page_to]`，逐条 `os.path.exists(<FEICUI_ROOT>/<img_path>)`；`img_path` 空 ⇒ `reason=img_path_null`，文件不存在 ⇒ `reason=file_missing`。
- `kind=text`：同范围 `text IS NULL OR trim(text)=''` ⇒ `reason=text_empty`。
- 响应头 `x-feicui-scope` 暴露本次判定范围（**不进 JSON 体**，保持 §3.1 E5 形状不多不少）。
- **口径提醒**：E5 是 **job 内该书**口径；AC-07 的复算 SQL 是**全表**口径（无 `pdf_name` 过滤），两者仅在库里只有一本 书时相等 —— 见 `REPORT_1a.md` 规范缺口 **G-3**。

**未实现（1b，非本单验收）**：`E3 GET /api/jobs/{job_id}/stamps`、`E4 POST /api/jobs/{job_id}/export`——**未注册路由**（调用得 `404`）。

**非规范端点（新增，仅运维/自测）**：`GET /api/health`（存活探针）、`GET /api/meta/migrations`（迁移记账只读视图）。
规范 §3 只定义 E1–E5，**未禁止**额外元数据端点；如判定违规，删这两条即可（`app/main.py` 尾部）。

## 7. 配置

优先级：**默认值 < JSON 配置文件 < 环境变量**。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `FEICUI_DB` | `<repo>/yinpu.db` | **DB 路径** |
| `FEICUI_ROOT` | `feicui/`（`server/` 的上级） | 影像相对路径解析根（§4.2） |
| `FEICUI_API_HOST` | `127.0.0.1` | 绑定地址（PORTS.md 制度 d） |
| `FEICUI_API_PORT` / `PORT` | `5196` | 端口（规范 §6.1） |
| `FEICUI_CHUNK_SIZE` | `8` | 默认 chunk 页数 |
| `FEICUI_SERVER_CONFIG` | `server/config.json` | 可选 JSON 配置文件 |
| `FEICUI_PYTHON` | `feicui/venv/bin/python` | 子进程取 PDF 页数用的解释器 |
| `FEICUI_CORS_ORIGINS` | `http://127.0.0.1:5195,http://localhost:5195,http://127.0.0.1:5163,http://localhost:5163` | 允许的前端 origin（5195＝feicui-web；5163＝玺爱，`/api/tools/*` 的调用方）。**不放开 `*`**，见 §12.4 |
| `FEICUI_ALLOW_PROD_MIGRATE` | 未设 | **迁移安全闸**，见 §8 |

## 8. 安全闸（**正式库不可被本层写坏**）

```bash
cd /Users/kevin/bistro/shu/feicui/server
# 默认行为（安全）：FEICUI_DB 指到仓库内正式 yinpu.db ⇒ 直接 abort（exit=3）
./.venv/bin/python -m app.migrations
# 允许（仅当 Kevin/Zang 明示）
FEICUI_ALLOW_PROD_MIGRATE=1 ./.venv/bin/python -m app.migrations
# 自测一律用副本：
cp ../yinpu.db ./selftest/evidence/selftest.db && FEICUI_DB=./selftest/evidence/selftest.db ./.venv/bin/python -m app.migrations
```

## 9. 启动 / 停止 / 重建 venv

```bash
cd /Users/kevin/bistro/shu/feicui/server
# 起（前台；自测请自行后台化并记录精确 PID）
FEICUI_DB=<db> ./.venv/bin/python -m app.main          # host/port 取 FEICUI_API_HOST / FEICUI_API_PORT
# 停：只用精确 PID（本机多会话共用，**严禁** pkill / killall 宽匹配）
kill -TERM <pid>
```

**重建 `server/.venv`（可复现，Zang 追加口径 4）**：

```bash
cd /Users/kevin/bistro/shu/feicui/server
uv venv .venv --python 3.11                      # 本机 uv 0.11.26 实测
uv pip install --python .venv/bin/python -r requirements.txt
uv pip freeze --python .venv/bin/python | wc -l   # 实测 = 13 行
```

- `server/.venv` 已列入 `server/.gitignore`（`仓库当前不是 git 仓库`，本文件为将来入版本库预置）。
- 实测 freeze（13 行）：`annotated-doc 0.0.5 / annotated-types 0.8.0 / anyio 4.15.1 / click 8.5.0 / fastapi 0.141.1 / h11 0.16.0 / idna 3.20 / pydantic 2.13.5 / pydantic-core 2.46.5 / starlette 1.6.0 / typing-extensions 4.16.0 / typing-inspection 0.4.4 / uvicorn 0.53.0`
  （快照：`selftest/evidence/04_server_venv_freeze.txt`）

> **⚠ 偏离规范 §6.2 已登记启动命令（须规范角色收口到 v1.2）**：§6.2 写的是
> `./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196`（`cwd=feicui`，**形态草案**、明确「入口文件名与启动方式由 Kong 定」；
> 且 `feicui/venv/bin/*` 的 console script 因 shebang 失效、`feicui/venv` 内也无 fastapi）。
> 本单实际口径＝`cd feicui/server && ./.venv/bin/python -m app.main`（等价于 `uvicorn app.main:app`），
> **解释器与 cwd 均与 §6.2 草案不同**（好处：API 环境与 worker/OCR 环境**物理分离**，符合 §1.2 I-2）。
> 该偏差**不作静默处理**，已上报为实现登记项（见 `REPORT_1a.md`「登记项 R-1」），请规范角色按 §0.4 流程收口。

## 10. 自测

```bash
cd /Users/kevin/bistro/shu/feicui/server
bash selftest/selftest_1a.sh        # 全程临时 DB 副本；证据落 selftest/evidence/
```
覆盖：① 同书二次建 job ⇒ 409 + 既有 job_id；② `done_pages` 库内复算（手工插假 `job_pages` 行 + **同刻库快照**对账）；③ E5 形状与计数对账（影像 / 释文 / 非空样本）；④ 迁移脚本连跑两次幂等 + 正式库安全闸；⑤ 正式 `yinpu.db` md5/size/inode 前后一致；⑥ E1 的 `total_pages` 派生与 422；⑦ E3/E4 未注册（404）。

---

## 11. 执行层（**阶段 1b-i**）：常驻 worker 池 / 页级 chunk 并行 / 游标推进 / 断点续跑 / 幂等

### 11.1 进程形态（规范 §1.3 进程分离 / §4.3 单写者）

```
   feicui-api :5196      薄接口层：只做「入队 + 查询」（E1 / E2 / E5；1b-ii 补 E3/E4/E7）
        │ E1 单事务写 jobs(QUEUED) + job_pages(PENDING)
        ▼
   feicui-pool           常驻 worker 池 supervisor（**唯一写者**，无端口）
   （无端口、daemon）      ├─ 4 × worker 子进程：feicui/venv/bin/python worker/feicui_worker.py
        │                 │   渲染 / 检测 / 释文块匹配 / OCR / 写影像（**绝不碰 DB**）
        │                 └─ 主循环：认领 chunk → 派活 → 收回结果 → **单事务提交 chunk**
        ▼
   yinpu.db(WAL) + output/faces/<book_key>/p####_i##.webp
```

| 项 | 口径 | 依据 |
| --- | --- | --- |
| worker 数 | **4**（`FEICUI_WORKERS`，`--workers` 可覆盖）；**1 ＝ 串行基线臂**（AC-04 的对照臂） | AC-04 钉值 + spike 实测「w=4 到顶、w=8 无收益」 |
| 解释器 | 池＝`server/.venv/bin/python`（3 包，无 OCR）；worker＝`feicui/venv/bin/python` | 规范 §6.5 解释器矩阵 |
| 单写者 | **只有池进程写 DB**；worker 只回传结果；池用 `flock` 独占锁（`server/.run/pool.state.lock`）保证同库一个池实例 | §4.3「WAL 单写者 ⇒ 必须串行化写」 |
| 提交点 | **chunk 边界**（`commit_chunk` 单事务：`stamps` 行 + `job_pages` 状态 + 计数 + `jobs` 游标） | §4.3 / §2.3 |
| 页游标 | 落 `job_pages`（库），**内存里不存游标**；E2 一律由库复算 | §2.3 / §3.2 S-1 |
| 崩溃窗口 | 影像先写（临时文件 + `fsync` + 原子替换）→ 后提交 DB 行 ⇒ 只可能留**孤儿影像** | §4.3 |
| 进程分离 | 池与 worker **不是接口层的子进程**：kill 掉 5196 后池/worker 照跑、游标照推进；重启接口层后 E2 与库内复算一致 | §1.3 / AC-11 |

### 11.2 幂等

| 层 | 键 | 行为 | 开关 |
| --- | --- | --- | --- |
| 记录行 | `(pdf_name,page,idx)`（唯一索引 `uq_stamps_pdf_page_idx`） | 已存在 ⇒ **跳过、绝不改写旧行**（`counters.skipped++`、`inserted=0`） | `FEICUI_ON_CONFLICT=skip`（默认）/ `update`（内容有别才改，计 `updated`） |
| 影像 | 内容 `sha256` | 同路径同名 + 内容一致 ⇒ **不重写**；否则原子替换 | — |
| 影像命名 | `(book_key,page,idx)` | `output/faces/<book_key>/p<页4位>_<idx2位>.webp`（稳定、无时间戳） | `FEICUI_FACES_DIR` 可改根目录 |

### 11.3 启动 / 停止（**只用精确 PID**，严禁 `pkill` / `killall` 宽匹配）

```bash
cd /Users/kevin/bistro/shu/feicui/server
# 1) 接口层（5196，注册端口）
FEICUI_DB=<db> ./.venv/bin/python -m app.main
# 2) 池（常驻；4 worker；无端口）
FEICUI_DB=<db> ./.venv/bin/python -m app.pool --workers 4
#    串行基线臂（AC-04 对照）：  … --workers 1 --drain        # 跑完当前活跃 job 即退
#    只跑一个 job（调试）：      … --job <job_id>
#    只列活跃 job（只读）：      … --list
# 3) 停：池收到 SIGTERM 会「提交完当前 chunk 再退」并关掉全部 worker；也可按 state 文件里的精确 PID 停
kill -TERM <pool_pid>
```

**状态文件**（**自测 / 运维据此取精确 PID**）：`FEICUI_POOL_STATE`（默认 `server/.run/pool.state.json`），内含
`pool_pid` / 每个 worker 的 `pid`+`task` / 当前 job / 统计 / `updated_at`，每轮 tick 原子重写。

### 11.4 断点续跑（§2.3 / AC-03）

任一时点 SIGKILL 掉池与全部 worker → 重启同一个池：`claim_job` 会把该 job 残留的 `RUNNING` 页
**退回 `PENDING`**（已 `DONE` 的页**不重算**），从断点继续；重复性由唯一索引兜底。

### 11.5 新增配置（默认值＝规范/派单口径；**默认行为不变**）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `FEICUI_WORKERS` | `4` | worker 数（§5.1 草案 8 待裁；AC-04 钉 4） |
| `FEICUI_DOC_PREPROCESS` | `1`（**开**） | doc 预处理开关。**默认保持现状行为**；`0` ⇒ 显式关（spike 实测 1.78×，**会改变识别文本**，精度未定论 ⇒ 不得静默改默认） |
| `FEICUI_CPU_THREADS` | `2` | 每 worker 的 `cpu_threads` 上限（派单口径，防线程超订） |
| `FEICUI_ON_CONFLICT` | `skip` | 行级冲突策略 |
| `FEICUI_FACES_DIR` | `<feicui>/output/faces` | 交付影像根（§4.1 D-4②）；自测会指向 `server/selftest/evidence/…` 以免动 `output/` |
| `FEICUI_WORKER_PYTHON` | `<feicui>/venv/bin/python` | worker 解释器 |
| `FEICUI_POOL_STATE` / `FEICUI_WORKER_LOG_DIR` | `server/.run/pool.state.json` / `server/.run/worker-logs` | 状态文件 / worker 日志（诊断走 stderr，协议走 stdout） |

### 11.6 自测（1b-i）

```bash
cd /Users/kevin/bistro/shu/feicui/server
bash selftest/selftest_1b_i.sh     # 全程副本库 + 非登记端口 5301–5305；证据落 selftest/evidence/1b_i/
```
覆盖：② 池真执行 ⇒ E2 推进且与库内复算逐字段一致；③ 同书同区间重跑 ⇒ `inserted=0`、行集指纹与影像清单不变；
④ 空库副本上 **w=1 vs w=4** 全字段逐条 diff（0 差异）；① SIGKILL 全部 worker + 池 ⇒ 重启同一 job 续跑至结束、
终态行数 == 串行臂且断点前已提交行逐字节未变；⑤ SIGKILL 接口层 ⇒ worker 存活 + 游标仍推进 ⇒ 重启后 E2 == 库内复算。

## 12. 工具端点（**与 job 体系完全无关**）：`POST /api/tools/square-crop`

给玺爱（5163）新增印章时用：上传一张**印面影像**，拿回**方形化**后的候选（WebP + 内置 `sha256`）。
实现：`app/routers/tools.py`（路由）→ `app/square_client.py`（子进程桥）→ `app/square_runner.py`（worker 侧执行体）
→ `app/square.py`（**纯函数**：参数真源 + 方形化几何）。

### 12.1 请求

| 项 | 值 |
| --- | --- |
| 方法 / 路径 | `POST /api/tools/square-crop` |
| `Content-Type` | **必须** `multipart/form-data`（带 boundary）。别的类型 ⇒ `400 BAD_CONTENT_TYPE` |
| 文件字段名 | **`image`**（必填；字段名必须**逐字**为 `image`，否则 `400 NO_IMAGE`） |
| 体积上限 | `MAX_UPLOAD_BYTES = 32 MiB`（仅量 `Content-Length` 级别的原始 body；超限 ⇒ `400 UPLOAD_TOO_LARGE`，**不落任何临时文件**） |

可选**文本字段**（同一 multipart 里，非文件部分）：

| 字段 | 默认 | 取值范围 / 语义 |
| --- | --- | --- |
| `pad_ratio` | `0.15` | `[0.0, 1.0]`；bbox 外扩比例（沿用斐萃现口径，`processor.detect_stamp_regions` 参数） |
| `min_area_eff` | 不传 | `> 0`；**显式**给出有效像素面积阈值（调用方自负责 DPI 口径）。不传 ⇒ 走模板口径 `template.min_area × processor.AREA_SCALE`（`AREA_SCALE=(400/144)²≈7.716049`，与 `process_page` 逐字相同） |
| `quality` | `95` | `[1, 100]`；WebP 编码质量。`95` ⇒ **逐字复用** `worker.feicui_worker.encode_webp` |
| `max_side` | `0` | `>= 0`；`0`＝不缩放；`>0` 且 `side > max_side` ⇒ 用 `INTER_AREA` 缩到 `max_side×max_side`（**只缩不放**，缩放后仍是正方形） |

越界 / 非数字 ⇒ `400 BAD_PARAM`（`reason` 带可读原因）。

### 12.2 响应

`200`：`{ok:true, count, source:{width,height}, candidates:[…], params_used:{…}, degraded:bool}`

单个候选 `candidates[i]`：

| 字段 | 说明 |
| --- | --- |
| `idx` | 排序后的位次（0 起）。排序键＝**面积降序**，同面积按 `bbox` 的 `x1,y1` 升序 ⇒ 前端默认取第一个 |
| `bbox` | 检测到的**外扩后** bbox `[x1,y1,x2,y2]`（半开区间；**未方形化**，便于对比） |
| `square` | **方形化后**的 `[x1,y1,x2,y2]`：恒满足 `x2-x1 == y2-y1 == side` 且落在图像内 |
| `side` | 方形边长（＝ `max(bbox宽, bbox高)`，被图像短边夹过则如实降级） |
| `width` / `height` | **输出**影像尺寸（`max_side` 生效后；两者恒相等） |
| `mime` | 恒 `image/webp`（RIFF magic 自证） |
| `sha256` | 输出 WebP 字节的 sha256（客户端可自算比对） |
| `image_base64` | 输出 WebP 字节的 base64 |
| `area` / `aspect` | 检测阶段的原值（contour 面积 / 长宽比），**不因方形化改变** |
| `degraded` / `degraded_reasons` | 该候选是否降级；reasons ⊂ `{SHORT_SIDE_CLAMP, BOUNDARY_SHIFT}` |

`params_used`：`{hsv_low, hsv_high, min_area_eff, min_area_source, pad_ratio, quality, max_side, template_source}`。
其中 `min_area_eff` 是 **worker 侧真实生效值**（不是接口层复算值）。

**来源标签口径（如实标注，本单修正过一处失真）**：
`template_source` 与 `min_area_source` 由同一个来源派生（`app/square.py` 的 `load_template_params()` +
`min_area_source_label()`），**不可能互相矛盾**：

* `config/templates.json` 里**有** `default` 项 ⇒ `template_source="templates.json:default"`（真源）；
* **没有** `default` 项（**当前实况**）⇒ `template_source="builtin(corpus-identical·verified N/N·square.py:BUILTIN_TEMPLATE_PARAMS)"`
  —— 明说是**内建兜底常量**、常量在 `square.py` 的哪一行、并且已**就地核验**它与模板里现有 N 本书的
  `(hsv_low, hsv_high, min_area)` 逐字一致；各书之间不一致时改标 `builtin(corpus-DIVERGENT·…)`；
  文件缺失/读不出 ⇒ `builtin(no-template-file·…)` / `builtin(template-unreadable·…)`。
* `min_area_source` ＝ `<template_source>·min_area=<模板值>×processor.AREA_SCALE=<实际值>`；
  显式给了 `min_area_eff` 时为 `explicit(min_area_eff)`。
* **红线：绝不引用不存在的键**。历史缺陷：`min_area_source` 曾硬编码 `templates.json:default`，
  而 `config/templates.json` 顶层**只有三本书名**、并无 `default` 键 ⇒ 已修（详见 `ops/kong_square_crop_evidence.md`）。

### 12.3 错误码（**一律结构化 JSON**，绝不返回 HTML 错误页）

| 状态 | `error` | 触发 |
| --- | --- | --- |
| `400` | `BAD_CONTENT_TYPE` | 不是 `multipart/form-data` |
| `400` | `UPLOAD_TOO_LARGE` | body > 32 MiB |
| `400` | `BAD_MULTIPART` | boundary 缺失 / multipart 结构损坏 |
| `400` | `NO_IMAGE` | 缺字段 `image` 或该字段为空 |
| `400` | `BAD_PARAM` | `pad_ratio` / `min_area_eff` / `quality` / `max_side` 越界或非数字 |
| `400` | `DECODE_FAILED` | `cv2.imdecode` 解不出来（不是可解码图片） |
| `422` | `NO_CANDIDATE` | 能解码但**零候选**（附 `source` / `params_used` 便于排查） |
| `500` | `RUNNER_*` / `INTERNAL` | 子进程失败（`RUNNER_PYTHON_MISSING` / `RUNNER_TIMEOUT` / `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`）或未预期异常 |

错误体形状：`{ok:false, error, reason, detail}`（`reason` 是给前端的口径化原因；`422` 另带 `source`/`params_used`）。

### 12.4 CORS

* `FEICUI_CORS_ORIGINS` 默认 `http://127.0.0.1:5195,http://localhost:5195`（feicui-web）；**玺爱 5163**
  由 `app/main.py` 的 CORS 中间件按同一份白名单放行（实测：预检与实 POST 均回
  `access-control-allow-origin: http://127.0.0.1:5163`）。
* **不放开 `*`**；白名单外的 origin ⇒ **不回** `access-control-allow-origin`（负例已实测）。

### 12.5 红线：**零 DB 写**（本端点是纯函数）

* 无任何 SQL、无 `repository` 调用、**不读 `stamps`**、**不建 job**（`jobs` / `job_pages` 一个字都不碰）；
* 不碰 `exports/` `output/`：上传字节**只进不出**（进来 → base64 回去），全程**不落盘**、不建临时文件；
* 不复制检测算法：红掩膜口径一律走 `processor.detect_stamp_regions`（在 worker 子进程里跑），
  方形化只有一份实现（`app/square.py`），两侧共用；
* 因此它对 `yinpu.db` 是**只读旁观者**：`stamps` 行集指纹在调用前后**逐字节不变**。

### 12.6 解释器矩阵与冷启动（本单做了一次优化）

* 接口层 `server/.venv`（只有 fastapi/uvicorn/pydantic）**不 import cv2**；图像栈在
  `feicui/venv`（`FEICUI_PYTHON` 默认 `<root>/venv/bin/python`）。桥按规范 §6.5 走**一次性子进程**
  `venv/bin/python server/app/square_runner.py`（stdin 收一行 JSON；stdout 只认 `FEICUI_SQUARE=` 标记行；
  诊断走 stderr），进程用完即退，**无守护/无池/无进程内状态**。
* **冷启动优化**：`processor.py` 顶部 `from paddleocr import PaddleOCR` 会把整套推理栈拉起来
  （实测 `import paddleocr` ≈ 1.28 s），而本端点只走 `detect_stamp_regions`（纯 cv2/numpy）、**一次 OCR 都不做**。
  ⇒ `app/ocr_lazy.py` 在 `import processor` **之前**把 `sys.modules["paddleocr"]` 换成**惰性替身**：
  只有真正实例化 `PaddleOCR` 时才加载真包（真包缺失则如实抛 `ModuleNotFoundError`），构造参数**原样透传**、
  `_get_ocr()` 的缓存语义不变。**`processor.py` 一个字节都没改**。
  实测（同一输入、两模式交错各 3 次取中位数）：**1.429 s → 0.242 s**（−83%），候选 `sha256` **完全不变**。
  逃生开关：`FEICUI_SQUARE_NO_LAZY_OCR=1` ⇒ 不装替身（回到优化前行为）。

### 12.7 自测 / 证据

```bash
cd /Users/kevin/bistro/xiai/feicui
# 端点全量自测（真实影像 + 合成图 + 错误码 + CORS + 零 DB 写）
server/.venv/bin/python server/selftest/verify_tools_square_crop.py --base http://127.0.0.1:5196
# 冷启动 A/B 基准（惰性 OCR 生效 vs 关掉；含来源标签如实性断言）
server/.venv/bin/python server/selftest/bench_square_crop_coldstart.py --reps 3
# 惰性替身对 OCR 路径的语义等价（不加载真模型）
server/.venv/bin/python server/selftest/verify_square_lazy_ocr.py
```

改动清单 / 改前改后 md5 / 自测与实测结论索引：`ops/kong_square_crop_evidence.md`；
原始自测输出：`ops/kong_square_crop_selftest_raw.txt`。


