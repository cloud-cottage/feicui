# feicui API 阶段 1a 交付报告（Kong）

| 项 | 值 |
| --- | --- |
| 时点 | 2026-09-20 11:52–11:57（Asia/Shanghai） |
| 规范 | `../docs/feicui.spec.md` **v1.1**（md5 `4264927baf24bb7f48e12366cd861fe7`，409 行） |
| 交付目录 | `/Users/kevin/bistro/shu/feicui/server/**`（新建；**未写** `feicui/web/**`；**未改** `app.py` / `processor.py` / `export.py`） |
| 自测结论 | `server/selftest/evidence/90_summary.txt` ⇒ **FAILS=0 / ALL PASS**（`bash selftest/selftest_1a.sh` 退出码 **0**） |
| 正式库 | `yinpu.db` md5 **前后同为 `254d3ff132d3a8d14dcf8590f45c7232`**（size 577536 / inode 59624593 未变；无 `-wal`/`-shm` 残留） |

## 1. 落盘文件与 md5（实测）

| 文件 | 行数 | md5 |
| --- | --- | --- |
| `server/README.md` | 201 | `ef3f11b8b2051e972760f5ffa607e185` |
| `server/requirements.txt` | 12 | `12e9b9fa0377cab931998c6b9a93fb01` |
| `server/.gitignore` | 10 | `cdf7be367b821ce2bb8e6e1ea2e699fe` |
| `server/app/__init__.py` | 3 | `240962c7c226f7dc496afc5a9981d3b3` |
| `server/app/config.py` | 95 | `d89877c1f59acce90bd1092441f55ae4` |
| `server/app/db.py` | 91 | `2d3d2ac674b6b9deb9c99cf908928806` |
| `server/app/migrations.py` | 212 | `0061c6a1e97b6229b55a0860a453668c` |
| `server/app/models.py` | 94 | `8a4d113e9a1eda03bc90df75a4e19104` |
| `server/app/pdfmeta.py` | 74 | `4315254d6c122aa23374944dbe59ac2f` |
| `server/app/repository.py` | 269 | `377dccf86e69f7b4bed0ada78417746a` |
| `server/app/routers/__init__.py` | 5 | `34dee8e763d96bbf5885f6172a922dd9` |
| `server/app/routers/jobs.py` | 172 | `b6f12d4ad043ee06448c416521f6a25b` |
| `server/app/main.py` | 124 | `716c60b912c294d441b27d07b39d2038` |
| `server/selftest/selftest_1a.sh` | 335 | `117b4c002940d27c46d8e04019510040` |
| `server/selftest/verify_1a.py` | 253 | `8275a1f95c5162abe464574014140abd` |

证据目录（真跑产物）：`server/selftest/evidence/`（80+ 文件，含 6 份**响应同刻库快照** `state_*.db`）。

## 2. 派单五条必测：真实命令 + 输出摘要

> 运行命令（全量、可复跑）：`cd /Users/kevin/bistro/shu/feicui/server && bash selftest/selftest_1a.sh`
> 以下为其中关键片段（原文见 `selftest/evidence/`）。

**① 启服务 → 同书建 job 两次 ⇒ 第二次 409 + 既有 job_id**

```
$ FEICUI_DB=…/selftest.db ./.venv/bin/python -m app.main     # PID 95103, 127.0.0.1:5196 LISTEN
$ curl -s -o 30_e1_job1.json -w '%{http_code}' -X POST http://127.0.0.1:5196/api/jobs -H 'Content-Type: application/json' -d '{"pdf_path":"…/tmp.pdf","page_range":[13,19]}'
201        -> {"job_id":"job-…","state":"QUEUED","total_pages":7,"created_at":"2026-09-20T11:56:0…+08:00"}
$ curl … 同一条（同 pdf_path）第二次
409        -> {"error":"ACTIVE_JOB_EXISTS","job_id":"<与第一次同一个 job_id>","state":"QUEUED",…}
$ sqlite3 副本库 "select count(*) from jobs"  -> 1        # 未静默起第二个
$ curl … '{"pdf_path":"/no/such/book.pdf"}'   -> 400      # S-6 参数非法
```

**② 进度＝库内复算（手工插假 `job_pages` 行）**

```
$ sqlite3 副本库 "UPDATE job_pages SET state='DONE',… WHERE page IN (13,14); … state='FAILED' … page=15; UPDATE jobs SET state='DONE'"
$ curl http://127.0.0.1:5196/api/jobs/<job> | …
{"job_id":"…","state":"FAILED_PARTIAL","total_pages":7,"done_pages":2,"failed_pages":[15],
 "cursor":{"chunk_lo":0,"chunk_hi":0},
 "counters":{"detected":23,"inserted":20,"updated":0,"skipped":0,"ocr_empty":14},…}
同刻（快照 state_41.db）独立复算：total=7 done=2 failed=[15] counters=[23,20,0,0,14]   ⇒ 逐项相等
S-2：库内 jobs.state='DONE' 但 failed_pages 非空 ⇒ API 报 FAILED_PARTIAL（不得报 DONE）
再推一页：done_pages 2 → 3，与库内 DONE 行增量一致（非内存计数器 / 非估算）
```

**③ 缺失清单形状与计数（与副本库一致）**

```
$ curl '…/missing?kind=image' -> {"kind":"image","count":0,"items":[]}         # 独立复算 os.path.exists 缺失数=0
$ curl '…/missing?kind=text'  -> {"kind":"text","count":30,"items":[{"pdf_name":"tmp.pdf","page":13,"idx":0,
                                   "img_path":"output/pairs/p13_0/stamp.png","reason":"text_empty"}, …]}
                                 独立复算 SQL（同书名+页区间）＝30  ⇒ 相等
$ 插入 2 条 img_path 指向不存在文件的假 stamps 行后：count 0 → 2，reason=file_missing，独立复算=2
$ curl '…/missing'（kind 缺失）-> 400
响应头 x-feicui-scope: pdf_name=tmp.pdf;page_from=13;page_to=19;root=…   （不进 JSON 体）
```

**④ 迁移脚本连跑两次 ⇒ 幂等**

```
$ FEICUI_DB=…/selftest.db ./.venv/bin/python -m app.migrations
applied=2  skipped=0  journal_mode=wal  schema_sha256=d35d052b6aee2a195c6879009c2116b87578a357bbeed829176410ccffd608be
$ FEICUI_DB=…/selftest.db ./.venv/bin/python -m app.migrations        # 第二次
applied=0  skipped=2  journal_mode=wal  schema_sha256=d35d052b…08be  ⇒ 指纹不变、无重复建表
$ 安全闸：不带 FEICUI_DB 跑迁移（＝正式库）⇒ 拒绝、exit=3（正式库零写入）
```

**⑤ 正式 `yinpu.db` md5 前后一致**

```
前：MD5 (…/yinpu.db) = 254d3ff132d3a8d14dcf8590f45c7232  size=577536 mtime=Sep 20 10:08:36 2026 inode=59624593
后：MD5 (…/yinpu.db) = 254d3ff132d3a8d14dcf8590f45c7232  size=577536 inode=59624593   ⇒ 未变
（另：正式库旁无 -wal / -shm；临时副本 md5 与正式库逐字节一致）
```

**附加（超出必测、已自证）**：E1 无 `page_range` ⇒ `total_pages` 由 PDF 派生（秦汉印典 **807** 页，与独立读数一致，入队落 807 行 `job_pages`）；不可读文件 ⇒ **422**（`missing:["total_pages"]`）；E3/E4 ⇒ **404**（未注册，1b 交付）。

## 3. Zang 追加口径四条 · 逐条落实

| # | 要求 | 落实情况 |
| --- | --- | --- |
| 1 | 不得污染/改动 `feicui/venv` | **未装、未改任何包**。证据 `evidence/02_main_venv_freeze.txt`（86 行）+ `02_main_venv_key_versions.txt`：`paddleocr 3.7.0` / `paddlepaddle 3.3.1` / `pymupdf 1.28.2` / `numpy 2.3.5` / `opencv-python 5.0.0.93` / `streamlit 1.63.0` 原值；`fastapi` **0 命中**；`paddleocr,paddle,fitz,numpy,cv2,streamlit` 均可 import（`selftest_1a.sh` §0c 自动校验「主 venv 中不存在 fastapi」）。 |
| 2 | 写清「谁用哪个解释器」 | `README.md` §2「解释器矩阵」：**API＝`server/.venv/bin/python`**（fastapi/uvicorn/pydantic，13 行 freeze，**不含 OCR**）；**1b worker＝`feicui/venv/bin/python`**（PyMuPDF + PaddleOCR 栈）。另：`app/pdfmeta.py` 取 PDF 页数时正是**子进程调 worker 侧解释器**，与矩阵一致。 |
| 3 | 偏离 §6.2 须显式上报 | 见下 **登记项 R-1**（README §9 也挂了同一块警示）。 |
| 4 | `server/.venv` 可重建 | `requirements.txt`（3 个包）+ 确切命令（`uv venv .venv --python 3.11` → `uv pip install -r requirements.txt` → freeze **13 行**）+ `.gitignore` 已排除 `.venv/`；freeze 快照 `evidence/04_server_venv_freeze.txt`。 |

**关于 `pymupdf` 是否装（Zang 追加口径 1）**：**不装**。依据：`grep -rn "pymupdf" server/app` 只命中注释/字符串；`grep -rnE "^\s*(import|from) (pymupdf|fitz)" server/app` ⇒ **0 命中**（静态 import 无）。页数派生走 `feicui/venv` 侧 PyMuPDF 子进程。故 API 环境保持精简（3 包），23 MB 依赖不重复安装——该条并入 **R-1** 一并上报。

## 4. 未完成 / 未做（**如实标注**）

| 项 | 状态 |
| --- | --- |
| **E3** `GET /api/jobs/{job_id}/stamps`（分页信封 6 字段） | **未做**（派单划给 1b；路由未注册，实测 404） |
| **E4** `POST /api/jobs/{job_id}/export` | **未做**（同上，404） |
| worker 池 / 页级并行 / 真实 OCR 执行 / 断点续跑 | **未做**（1b）。1a 只做到「入队 + 页级游标落盘（`job_pages` 全 `PENDING`）」 |
| `jobs.state` 的推进（QUEUED→RUNNING→…） | **无生产者**（无 worker），故 1a 内 E2 恒报库内值；`FAILED_PARTIAL` 下行分支**已用插库样本验证** |
| `counters.*` 的真实写入 | 无生产者；**读路径已按库内 SUM() 复算**，用假行验证 |
| `book_key` 列、`cursor_chunk_lo/hi` 列 | **预留未写**（1a 无来源）；E2 的 `cursor` 由 `job_pages` 复算（不读这两列，已在 README 标注） |
| 前端联调（5195 ↔ 5196）、`ctrl/index.js` 入 `services` 表 | **未做**（不属本单；且 `shu/feicui/web/**` 是平行任务，本单未写一行） |
| AC-01～AC-13 的整链验收（并行=串行一致、断点续跑、幂等键复算…） | **未做**（依赖 worker 执行；本单只做 1a 的判据面） |
| 性能 / 耗时类断言 | **按纪律不做**（派单明令；本报告无任何性能结论） |

## 5. 规范缺口清单（我方观测；**不发明契约**，请规范角色裁定）

| # | 缺口 | 现状事实（证据） | 影响 |
| --- | --- | --- | --- |
| **G-1** | **409 响应体形状未定义**。§3.1 E1 只写「`409` + 既有 `job_id`」，未定字段集；而 §3.2 S-3 对信封类响应明文「多出未定义字段即判负」 | 本层自定 `{error, detail, job_id, state, total_pages, created_at}`（`app/models.py::JobConflictResponse`）；实测 409 体已含既有 `job_id` | 若把 S-3 的「不得多字段」纪律外推到 409 体，则任何实现都无法既「带上 job_id」又不「多出字段」 |
| **G-2** | **400 / 404 / 422 的响应体形状未定义**（S-6 只枚举码族） | 本层用 FastAPI 原生 `{"detail": {…}}`；`models.py::ErrorResponse` 定义后**未使用**（仅作形状参考） | 前端/验收脚本无法按固定形状解析错误体 |
| **G-3** | **E5 范围 vs AC-07 复算 SQL 口径不一致** | E5 是 **job＝1 本书**内口径；AC-07 的复算 SQL 是**全表**口径（无 `pdf_name` 过滤）。实测（快照 `state_50.db`）：全表＝**77**（正是规范基线 77），本次 job 区间口径＝**30**，差 47 | AC-07 无法在「1 书 = 1 job」模型下机械判负；建议 AC-07 的 SQL 加 `where pdf_name=? and page between ? and ?`，或明确 E5 用全表口径 |
| **G-4** | **§2.1「重跑不换 job_id 语义」歧义** | 本层取：活跃 job 存在 ⇒ 一律 409（**不看 `rerun`**）；无活跃 job 且 `rerun=true` ⇒ **新 `job_id`**、旧行保留作审计 | 若规范本意是「复用同一 job_id 并重置页游标」，本层需改；请裁定 |
| **G-5** | **`total_pages` 的来源未定义** | E1 请求无页数字段，§2.2 又要求 `total_pages` 必在。本层取：「`page_range` 宽度 → 否则读 PDF 页数 → 再否则 **422**」 | 若规范认为「读页数」属 worker 职责（§1.2 I-2 精神），则须规定 E1 **必须**带 `page_range` |
| **G-6** | **E1 对「非 PDF 文件」的判定口径未定义** | 实测 PyMuPDF 按**扩展名**分流：`.txt` 被当文档打开（**1 页**）⇒ E1 会接受；`.bin` 抛 `FileDataError` ⇒ 拒绝（证据 `evidence/5B_pymupdf_lenient.txt`） | 「读得出页数」不足以证明是 PDF；本层**未**做 `%PDF-` magic 校验。是否要校验请规范明确 |
| **G-7** | **§4.1 D-2 的 `UNIQUE(pdf_name,page,idx)` 落地形态** | SQLite 无法给既有表加约束，只能建**唯一索引**；本层落 `uq_stamps_pdf_page_idx`（幂等语义等价，`PRAGMA table_info` 内不出现约束行），且**先实测重复组＝0** 才建 | 若规范要求以「表约束」形态存在，须重建 `stamps`（与「只许加法」冲突） |
| **G-8** | **是否允许额外的非 §3 端点** | 本层新增 `GET /api/health`（存活探针，自测就绪判定用）与 `GET /api/meta/migrations`（迁移记账只读） | §3 只定义 E1–E5；若判定违规，删 `app/main.py` 尾部两段即可 |

## 6. 登记项（须规范角色按 §0.4 收口）

| # | 事项 | 事实（含命令） |
| --- | --- | --- |
| **R-1** | **偏离 §6.2 已登记启动命令 + API 环境与 worker 环境分离** | §6.2 写 `./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196`（cwd `feicui`，**形态草案**、注明「入口文件名与启动方式由 Kong 定」）。**实际**：`cd feicui/server && ./.venv/bin/python -m app.main`（等价 `uvicorn app.main:app`，端口 5196、host 127.0.0.1 **不变**）。三点差异：① **解释器**＝`server/.venv`（非 `feicui/venv`）——理由：`feicui/venv/bin/*` console script 因 shebang 失效、且其内无 fastapi，装进去还会威胁 spike 基线；② **cwd**＝`feicui/server`；③ **API 环境不含 OCR 栈/pymupdf**（3 包，13 行 freeze）。**未静默**：README §9 + 本表 + 报告均留痕。**待规范动作**：改 §6.2 启动命令/cwd 登记行（并与 `ctrl/PORTS.md` §2 的 5196 行同步），v1.2 收口 |

## 7. 复跑方式

```bash
cd /Users/kevin/bistro/shu/feicui/server
bash selftest/selftest_1a.sh                      # 全量自测（临时 DB 副本），证据落 selftest/evidence/
FEICUI_DB=/tmp/x.db ./.venv/bin/python -m app.migrations --status   # 迁移体检（只读）
```
