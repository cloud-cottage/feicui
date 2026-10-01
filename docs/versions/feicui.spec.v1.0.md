# feicui 侧规范（feicui.spec.md）

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **feicui（印谱 PDF 解析工具）的独立侧规范**。本文件**只约束 feicui 自身**（`/Users/kevin/bistro/shu/feicui/**`）；**平台侧（印索）规范一字不改**，跨界处**只作引用**（引用对象＝`/Users/kevin/bistro/shu/docs/yinsuo-web.spec.md`，下称「平台规范」）。 |
| 端口真源 | 跨项目端口唯一真源＝**`/Users/kevin/bistro/ctrl/PORTS.md`**；运行时真源＝**`/Users/kevin/bistro/ctrl/index.js` 的 `services` 表**。本文件第 6 节是**登记口径**，端口数值以 PORTS.md 为准。 |
| 版本 | **v1.0**（2026-09-20｜Jing 建立） |
| 维护人 | **Jing**（制度 / 口径）。**实现属 Kong**：`feicui/**` 下任何 `.py` / 前端工程 / `index.js` 改动**一律不由 Jing 执行**。裁定人＝**Zang**（派单方）/**Kevin**（拍板方）。 |
| 范围 | `feicui/` 的目标形态、任务模型、API 契约形状、数据层演进、并发与资源、端口登记、验收判据、现状纪律、待裁清单。 |
| 本版硬约束（写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` 或数据文件**（Jing 只写本文档与 PORTS.md 登记行）；② **未改动 `shu/web/**`**（对外站 M1 已封版冻结，改它会作废另一角色的验收结论）；③ **未改动平台规范任何历史版本行**（`shu/docs/yinsuo-web.spec.md` 只在**追加**变更行时按 §0.4 流程处理）；④ **未 kill / 停 / 重启任何进程**、**未占用任何端口**（含 8501 上的 Streamlit 实例，见 §9-R2）；⑤ **PORTS.md 只加行 / 追加状态行**，未重写任何历史行。 |

---

## 0. 文档约定

### 0.1 与其他文档的关系（防混淆）

| 文档 | 角色 | 与本文件的关系 |
| --- | --- | --- |
| `shu/docs/yinsuo-web.spec.md` | **平台侧规范**（印索 Web / 数据模型 / 计费 / 汇入契约） | 本文件**只引用**其 §9（引「汇入契约」），**不改其任何一字**；平台侧需求变更**不回写**本文件，只同步引用点。 |
| `ctrl/PORTS.md` | **端口文档真源** | 本文件 §6 的数值与其**逐条一致**；不一致时**以 PORTS.md 为准**并当场修本文件。 |
| `ctrl/index.js` | **端口运行时真源** | `services` 表五要素为登记目标；落地由 **Kong** 执行（§6.3）。 |
| `feicui/README.md` | feicui 工程说明 | 工程实现细节（使用方式 / 历史版本）以 README 为准；**口径冲突时以本规范为准**。 |
| 本文件 | **feicui 侧规范** | 唯一。 |

### 0.2 现状读数的纪律（**硬约束**）

1. **一切「现状 / 实测 / 当前」类读数必须自带时点戳与证据来源**，格式：`核验时点 YYYY-MM-DD HH:MM（Asia/Shanghai）；证据＝<命令或文件路径>`。
2. **派单 / 聊天 / 口头转述与磁盘事实不一致时，一律以磁盘事实为准**；差异**就地登记**（本文件 §9 待裁清单或 §10 变更记录），**不得为迁就转述而编造原句**。
3. 本纪律与平台规范 **§0.2 / §0.4 第 8 条**同源（该条即「现状类段落以磁盘实测为准」，依据＝平台规范 §9.1 在 v1.23 及更早的六条事实错误全部源于转述）。

### 0.3 本文撰写时的磁盘事实基线（**本节即 §0.2 的实例**）

> **核验时点＝2026-09-20 10:38–10:45（Asia/Shanghai）**；核验人＝**Jing**。
> **统一证据来源**：① `wc -l feicui/{app,processor,export,selfcheck_export}.py`；② `feicui/venv/bin/python` 直连 `feicui/yinpu.db` 的 `sqlite_master` / `stamps` / `PRAGMA` 查询；③ `find feicui/output -name '*.webp'`、`du -sh`；④ `lsof -nP -iTCP -sTCP:LISTEN`、`nc -z 127.0.0.1 <port>`、`ps -o pid,ppid,pgid,lstart,command -p <pid>`；⑤ `sysctl -n hw.physicalcpu hw.logicalcpu hw.memsize`、`df -h /Users/kevin`；⑥ `feicui/f2_report.json`（Kong 侧 F2 报告，`generatedAt=2026-09-20T10:10:00+08:00`）。

| 项 | 实测读数（**核验时点 2026-09-20 10:38–10:45**） | 证据 |
| --- | --- | --- |
| 代码规模 | `app.py` **378** 行（Streamlit UI 层）／`processor.py` **517** 行（解析逻辑）／`export.py` **1270** 行／`selfcheck_export.py` **398** 行 | `wc -l` |
| UI 现状 | **Streamlit**（`app.py` 第 1 行 `import streamlit as st`） | `grep -n '^import' app.py` |
| 主表 `stamps` | **79 行 / 10 列**（`id` `pdf_name` `page` `idx` `text` `img_path` `x1` `y1` `x2` `y2`） | 直连 DB 查询 |
| 分书条数 | `tmp.pdf` **30** ／`古玺汇编 文物出版社 罗福颐  ok.pdf` **23** ／`秦汉印典 上海书画 金怀英  1997 ok.pdf` **26**（合计 79） | `select pdf_name,count(*) from stamps group by pdf_name` |
| `text` 非空 | **2 / 79** | `select count(*) from stamps where text is not null and trim(text)<>''` |
| 影像缺失 | **0 / 79**（逐条 `os.path.exists(img_path)` 全命中） | 直连 DB 逐条 `os.path.exists` |
| `output/` 影像 | **49 个 `.webp`**，目录形态 `output/<书名>/…` + `output/pairs/pNN_i/…`；`du -sh output` ＝ **3.4 M** | `find` / `du` |
| 侧表 | **4 张**：`seals`(79) / `images`(79) / `export_batches`(12) / `export_records`(49) | `sqlite_master` |
| 库文件 | `yinpu.db` **576 K**；备份 `yinpu.db.bak-f2` **466944 B** | `du -sh` / `ls -l` |
| **无** WAL | `PRAGMA journal_mode` → **`delete`**（**非 WAL**） | 直连 DB `PRAGMA` |
| **无**索引 / 唯一约束 | `sqlite_master` 内的 index 仅 4 条 `sqlite_autoindex_*`（**全部属侧表**）；**`stamps` 上无任何索引、无唯一约束** | `sqlite_master` 查询 |
| 写库形态 | `process_pdf` **逐页** `sqlite3.connect("yinpu.db")` → `commit()` → `close()`（**每页一次**，非批量事务） | `grep -n 'connect(\|commit()\|close()' processor.py` → 行 **432 / 440 / 441** |
| OCR 实例 | **全局单例**：`_get_ocr()` 用 `global _ocr_instance` 缓存（`processor.py` 行 **20–23**） | `grep -n '_get_ocr\|global ' processor.py` |
| PaddleOCR 单实例开销 | **init ≈ 1.8 s；常驻 RSS ≈ 0.70 GB；峰值 RSS ≈ 0.81 GB**（PP-OCRv6_medium_det + rec） | 本人实测：`./venv/bin/python -c "from paddleocr import PaddleOCR; …"`（`ru_maxrss` 与 `ps -o rss` 双读） |
| 单页渲染 | 古玺汇编 **544** 页、400 dpi 渲染 2106×3160 px、单页渲染 **66 ms**（沿用派单已核基线，本文件不重测） | 派单基线（Jing 未独立复测，**如实标注**） |
| 解析吞吐 | `process_pdf` 实测 **2 页 = 8.8 s** ⇒ 544 页 ≈ **40 min**／132 页 ≈ **10 min**／807 页 ≈ **59 min**（**单进程串行**） | `feicui/f2_report.json` → `3_ocr_feasibility.cost_estimate` |
| OCR 可用性 | **印面（篆书）直 OCR 不可用**：4 个印面样本 3 个 `max_score=0.0` 无字、1 个仅 2 字（0.23）；**边款 / 整页影像可用**（`max_score=0.9989`，41 框） | `feicui/f2_report.json` → `3_ocr_feasibility.verdict` |
| OCR 空释文机械根因 | `processor.ocr_text()` 以 `getattr(item,'rec_texts')` 读 PaddleOCR 3.x 的 `OCRResult`，该对象**无此属性**（字段在 `.json['res']` 下）⇒ 任何输入恒返回 `''`（**已由 Kong 最小修复**） | `feicui/f2_report.json` → `3_ocr_feasibility.root_cause_found` |
| 机器资源 | **10 物理核 / 10 逻辑核 / 16 GB RAM / 可用磁盘 169 GB（使用 60%）** | `sysctl` / `df -h` |
| 端口现况 | **5195 空闲**、**5196 空闲**、**5200 / 5201 / 5202 空闲**；**8501 被占**（见 §9-R2） | `lsof -nP -iTCP:<p> -sTCP:LISTEN` + `nc -z 127.0.0.1 <p>` |
| 已有前端**无** `/feicui` 代理 | `shu/web/vite.config.js` 内 `grep -n proxy` **零命中** | `grep` |

### 0.4 变更流程（本文件）

1. **提出**（Zang 派单 / Kevin 拍板 / Jing 自检发现）；
2. 若属未决，先登记 **§9 待裁清单**；
3. 裁定（Zang / Kevin）；
4. **升版本号**并在 **§10 变更记录**新增一行（**历史行原文保留、不重写**，数值性事实可原位替换并注明「已被 vX.Y 取代」）；
5. 同步受影响的小节与 **§6 端口登记**（端口变更须同时改 PORTS.md，见 PORTS.md §1(b)）。

---

## 1. 目标形态：Streamlit 退役 → 薄接口层 + 独立前端 + worker 池

### 1.1 目标形态（结构）

```
  浏览器
    │  HTTP
    ▼
  [Vue 前端站点]  feicui-web   :5195   ← 独立进程、独立生死、纯静态/纯前端
    │  HTTP (JSON)
    ▼
  [FastAPI 薄接口层]  feicui-api :5196  ← 只做：参数校验 / 入队 / 查进度 / 分页取数 / 触发导出
    │  任务队列（进程内队列或本地持久队列，形态由 Kong 定）
    ▼
  [worker 池]  N 个独立计算进程        ← 复用同一份 Python 解析库（processor 路径）
    │  写
    ▼
  SQLite(yinpu.db, WAL)  +  影像外置目录
```

**依据**：① **Kevin 已拍板方向＝三选一的 C**，原话「**如果换 FastAPI + Vue 不影响数据处理效率，那么选 C**」；② **Zang 已裁定「不影响」**——理由：**计算路径是同一份 Python 库（PyMuPDF / OpenCV / PaddleOCR / Pillow），UI 框架不在热路径**。故本节不再论证可行性，只定形态与不变量。

### 1.2 硬不变量（换 UI 不得动的东西）

| # | 不变量 | 依据 / 判负形态 |
| --- | --- | --- |
| I-1 | **解析与 OCR 仍是同一份 Python 实现**（`processor.py` 的渲染 / 检测 / OCR / bbox 口径） | Zang 裁定前提。判负：为「提速」改写检测阈值、坐标口径或 DPI 口径而未走 §0.4 变更流程。 |
| I-2 | **UI 框架不得进入热路径**（前端与接口层不得参与逐页像素运算） | 同上。判负：逐页图像处理出现在 FastAPI 进程内且与 worker 争 CPU。 |
| I-3 | **`stamps` 的既有语义字段不变**（`pdf_name` / `page` / `idx` / `text` / `img_path` / `x1y1x2y2`）；演进只允许**加列 / 加侧表** | 平台规范 §9.3 / §9.4 依赖这些字段的语义（bbox 单位、页号 1-based）。 |
| I-4 | **FEICUI 侧不得改平台规范的任何一字**；跨界字段口径以平台规范 §9 为**唯一真源** | 本文 §3.4 引用纪律。 |

### 1.3 进程分离口径（计算进程与 UI 进程各自生死）

| 角色 | 独立进程 | 生死口径 |
| --- | --- | --- |
| 前端（5195） | ✅ | 死掉**只影响可视**，**不得**中断任何已入队的 job。 |
| 接口层（5196） | ✅ | 重启**不得**丢 job 列表与进度（进度以**库 / 持久队列**为准，不以内存为准）。 |
| worker（N 个） | ✅ | 单个 worker 崩溃 ⇒ **该 job 停在其页级游标**，可**续跑**（§2.3），**不得**产生半条记录或孤儿影像。 |
| OCR 运行时 | 随 worker | 见 §5.2（**每 worker 一实例**，不再全局单例）。 |

**判据（可判负）**：见 §7 **AC-11**。

### 1.4 Streamlit 退役边界（**只定边界，不定时点**）

- **退役对象**：`app.py`（378 行，Streamlit UI 层）与其依赖的 Streamlit 运行方式。
- **退役后不得**：`feicui` 主入口再依赖 8501（改由 **5195** 承担，见 §6.1）。
- **8501 上的存量实例**：**属处置中事项**——本文件**不写状态定论**，见 **§9-R2**（**Jing 不动进程**）。
- **`requirements.txt` / venv 的清理**属实现侧动作（Kong）；本文件只登记目标：**退役完成时 `streamlit` 不得再是 feicui 的运行依赖**（判据：`requirements.txt` 无 `streamlit`，且 venv 内不再需要它）。

---

## 2. 任务模型

### 2.1 粒度

| 层级 | 单位 | 说明 |
| --- | --- | --- |
| **job** | **一本书 = 一个 job** | 一本书 = 一个 `job_id`（可重跑，重跑**不换 `job_id` 语义**，见 §2.4）。 |
| chunk | job 内的**页区间** | 一本书的页区间切若干 chunk（切法见 §5.3），chunk 为**并行单位**与**断点单位**。 |
| 记录 | 一页内一个印面（`idx`） | 落 `stamps` 一行（语义不变）。 |

**依据**：① 规模口径＝Kevin 原话「**单书数千页 × 数千本书分次执行**」；② 平台规范 **§9.6**「**交付单位：一本书 = 一个批次（`batch_id`）**」——feicui 侧 job 粒度与之**同构**（1 job ↔ 1 批），避免汇入侧再切分。

### 2.2 job 状态机（口径，形态由 Kong 定）

`QUEUED → RUNNING → (PAUSED) → DONE`；异常分支 `FAILED_PARTIAL`（部分页失败、已成功页**不丢**）。

- **`FAILED_PARTIAL` 不得**被当作 `DONE` 上报（**假完成**判负，见 §7 AC-05）。
- 每个 job 必须有：`total_pages` / `done_pages` / `failed_pages[]`（可为空数组，**不得省略**）。

### 2.3 页级断点游标（可续跑）

- **游标粒度＝页**（chunk 完成时提交，见 §4.3）；**断点信息必须落盘**（库或持久队列），**不得只存内存**。
- **续跑语义**：重启后从**未完成页**继续；**已提交页不得重算重写**（重算可接受与否由 §7 AC-03 判定）。
- **崩溃窗口约束**：任意时刻 SIGKILL worker，**不得**留下「半页记录」（页内多印要么全落、要么全不落）。

### 2.4 同书重跑幂等（不得产生重复记录 / 重复影像）

| 层 | 幂等键（feicui 侧） | 行为 |
| --- | --- | --- |
| **记录行** | **`(pdf_name, page, idx)` 唯一** | 已存在 ⇒ **upsert 或跳过**；**不得新增行**。当前 DB **无该唯一约束**（§0.3 实测），属**本规范的落地要求**。 |
| **影像文件** | **内容 `sha256`** | 内容相同 ⇒ **不重写、不另存**；路径相同 ⇒ 覆盖须**内容一致的校验后**才允许（或写临时文件 + 原子替换）。 |
| **导出批次** | `batch_id` | 与平台规范 **§9.4**「同一 `batch_id` 重复汇入 → 幂等跳过（`skipped_count`）」**对齐**。 |

**与平台幂等键的关系（必须分清）**：feicui 侧行级幂等键是 `(pdf_name,page,idx)`（**落库不重复**）；平台侧幂等键是 **§9.4 的 `dedupe_key`**（**跨系统去重**）。**两者都要**，**不得互相替代**；平台键**必须**按 §9.4 的公式与 DPI 归一化前置计算（见 §3.4）。

---

## 3. API 契约草案（**只定形状与语义，不定实现**）

> 纪律：① 本文只定**形状 / 语义 / 状态码族**，**不定**具体框架内部结构、不定线程模型、不定序列化库；② **不得**因本节的形状设计与平台规范 §9 冲突——冲突时**以平台规范为准**并改本节。

### 3.1 端点一览（草案）

| # | 方法 / 路径 | 语义 | 请求要点（形状） | 响应要点（形状） |
| --- | --- | --- | --- | --- |
| E1 | `POST /api/jobs` | **建 job**（一本书 = 一个 job，入队） | `{pdf_path, page_range?:[from,to], chunk_size?, rerun?:bool}` | `201 {job_id, state, total_pages, created_at}`；相同 `pdf_path` 已存在活跃 job ⇒ **`409` + 既有 `job_id`**（**不得**静默起第二个同书 job） |
| E2 | `GET /api/jobs/{job_id}` | **查进度**（真实进度） | — | `{job_id, state, total_pages, done_pages, failed_pages[], cursor:{chunk_lo,chunk_hi}, counters:{detected,inserted,updated,skipped,ocr_empty}, started_at, updated_at}` |
| E3 | `GET /api/jobs/{job_id}/stamps` | **分页取结果** | `?page=&limit=&cursor=` | **分页信封**：`{items[], page, limit, total, has_more, next_cursor}` |
| E4 | `POST /api/jobs/{job_id}/export` | **触发导出** | `{batch_id?, book_code?, dry_run?}` | `{batch_id, package_dir, counts:{formal,draft,rejected}, selfcheck_ref}` |
| E5 | `GET /api/jobs/{job_id}/missing` | **缺失清单**（影像 / 释文） | `?kind=image\|text` | `{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}` |

**E5 的依据**：派单要求「**影像/释文缺失清单可查**」（§7 AC-06 / AC-07）；现状缺口的**规模已实测**：影像缺失 **0/79**、`text` 非空 **2/79**（§0.3）。

### 3.2 语义纪律（可判负）

| # | 纪律 | 判负形态 |
| --- | --- | --- |
| S-1 | **进度必须真实**：E2 的 `done_pages` 必须是**已完成页的复算值**，不得由前端计时器 / 估算推进 | 进度与库内复算不一致（§7 AC-05） |
| S-2 | **不得假完成**：有 `failed_pages` 时 `state` **不得**为 `DONE` | `failed_pages` 非空而 `state=DONE`（§7 AC-05） |
| S-3 | **分页信封形状与平台一致取向**：`{items, page, limit, total, has_more, next_cursor}`（引用平台规范 §3.1「分页信封」口径） | 缺字段 / `has_more` 与实际不符 |
| S-4 | **接口层不落业务真值**：E2/E3 的数据**以库为准**；接口层内存缓存**不得**成为唯一真源 | 重启接口层丢 job / 丢进度（§7 AC-11） |
| S-5 | **同书并发上限 1**：同一 `pdf_path` 同时只能有一个 `RUNNING` job | 同书两 job 并行写（§7 AC-01） |
| S-6 | **错误码族**：`400` 参数非法 / `404` 资源不存在 / `409` 冲突（同书重复起 job） / `422` 必填字段不可派生 / `500` 内部错误。**枚举三值即可，不多造** | 出现未定义码族或语义倒挂 |

### 3.3 与平台侧汇入契约的对齐（**引用，不改平台规范一字**）

| 平台规范锚点 | 平台侧原文要点（**照录引用，不改**） | 本文件对其的**承接** |
| --- | --- | --- |
| **§9.3 必填 11 项** | 必填项＝上表第 **1 / 2 / 4 / 6 / 7 / 8 / 9 / 10 / 11 / 13 / 14** 行，即 `seal_name` / `dynasty` / `seal_type` / `asset_kind` / `source_book` / `source_page_no` / `seal_code` / `sha256` / `image_bytes`·`width`·`height`·`color_mode` / `review_status` / `batch_id`；「**必填项缺失即不得进入平台正式库**，只能作为 `review_status=DRAFT` 暂存」 | feicui 侧 E3 / E4 的**每条记录**必须能给出这 11 项（**缺失时**必须附带**可解释的缺失原因**，与 `feicui/exports/selfcheck_report.json` 的 `requiredCoverage` 口径一致）。**现状**：`seal_name` **2/79**、`seal_code` **0/79**、`seal_type` **全部 UNKNOWN 哨兵**（§0.3 与 `f2_report.json` `5_selfcheck_before_after`） |
| **§9.4 幂等键** | `dedupe_key = sha256(sourceBook + '\|' + sourcePageNo + '\|' + quantize(bbox, 1pt) + '\|' + assetKind)`；**且** `sealCode` 为业务唯一键（`UNIQUE`）；图片以 `sha256` 幂等；写入语义＝**upsert** | feicui 侧必须**可独立复算**该键；`bbox` 输入一律为 **pt** |
| **§9.4 DPI 归一化前置（v1.24 限定）** | `bbox` **须先按该书 `coord_dpi` 归一化为 pt**，**再**作 `quantize(·, 1pt)`；**不得**以像素原值直接量化 | feicui 侧 `stamps.x1y1x2y2` 为**像素**且 **DPI 逐书不同**（实测 古玺汇编 **400** / 秦汉印典 **144** / `tmp.pdf` **144**，证据 `feicui/config/book_geometry.json`）⇒ **归一化是硬前置**，已在 `seals.coord_dpi` / `bbox_unit='pt'` / `bbox_pt_*` 落列 |
| **§9.6 通道** | **首版：本地目录投递**（平台侧导入器读取）；后续可换对象存储 + 队列；**交付单位**＝一本书 = 一个批次（`batch_id`）；**回滚**＝按 `batch_id` 整批撤销；**校验清单** 6 项 | feicui 侧 E4 产物**首版仍走本地目录**（`feicui/exports/fb_…/`，实测 12 个批次目录）；**不得**在平台侧未开对象存储前改用远端通道 |

> **纪律（重复声明）**：上表**只是引用**。**平台规范一字不改**；若平台规范升版改了口径，**由平台侧按 §0.4 流程改**，feicui 侧按新口径**同步本表的引用点**（同步记录写入 §10）。

---

## 4. 数据层演进

### 4.1 演进项（SQLite 保留 + 四项改造）

| # | 改造 | 现状（核验时点 2026-09-20 10:38） | 目标 / 口径 |
| --- | --- | --- | --- |
| D-1 | **开 WAL** | `PRAGMA journal_mode` → **`delete`** | `PRAGMA journal_mode=WAL`（进程启动即设并**校验返回值**）；`synchronous=NORMAL` **仅在** WAL 下采用 |
| D-2 | **建索引 `(pdf_name,page)`** | `stamps` 上**无任何索引** | 建 `idx_stamps_pdf_page(pdf_name,page)`；**并**建 `UNIQUE(pdf_name,page,idx)` 承载 §2.4 行级幂等（**唯一约束是本规范要求，现状不存在**） |
| D-3 | **批量事务**（替换每页一次 connect/commit/close） | `processor.py` 行 **432 / 440 / 441**：**每页** `connect → commit → close` | **按 chunk（或按页内全部记录）一次事务提交**；单页内**不得**多次开合连接。**判据见 §7 AC-10** |
| D-4 | **影像外置目录规则** | 影像散在 `output/<书名>/…` 与 `output/pairs/pNN_i/…`（49 个 `.webp`，`du=3.4 M`） | ① **DB 只存路径 / `sha256` / `bytes` / `width`·`height`·`color_mode`，不得存影像 BLOB**；② 影像统一落 **`feicui/output/faces/<book_key>/p<页4位>_<idx2位>.<ext>`**（`book_key` 取 `config/book_codes.json` 的本地简码）；③ **迁移旧路径须留映射**（`images.src_path` 与 `images.package_path` 已分列，沿用） |

### 4.2 影像目录规则（细则）

1. **路径一律相对 `feicui/`**（不写绝对路径入 DB；现状 `img_path` 为 `output/...` 相对形态，**保持**）。
2. **文件名稳定**：同 `(pdf_name,page,idx)` 重跑 ⇒ **同一路径**（便于 §2.4 幂等比对）。
3. **不得**在热路径生成新命名（如带时间戳 / 随机后缀），否则幂等判定失效。
4. 中间产物（如 `output/pairs/**/stamp.png`）与**交付影像**分层：交付影像以 `faces/` 为唯一口径，中间产物**可清理**（清理须记录）。

### 4.3 事务与断点的耦合口径

- **提交点 = chunk 边界**（也是断点粒度，§2.3）；**页内记录与页内影像必须同批生效**（先写影像文件 + `fsync`，后提交 DB 行；崩溃窗口允许**孤儿影像**，**不允许孤儿 DB 行**——**孤儿影像由重跑覆盖，不产生重复**）。
- **多 worker 写同一 SQLite 文件**：**WAL 单写者** ⇒ **必须串行化写**（唯一写者进程 / 写队列）。**不得**让 N 个 worker 各自直连 `yinpu.db` 并发 `INSERT`（**这会触发 `database is locked` 或假成功**）。**依据**：WAL 语义 + 现状「每页 connect/commit/close」已是最坏形态（§0.3 D-3）。

### 4.4 未来扩展的边界条件（**阈值＝Jing 拟定门槛，待 Zang 裁定**）

> **诚实标注**：下述阈值**不是既有事实、也不是派单口径**，是 **Jing 依据本机实测资源与现状规模提出的门槛草案**；**须 Zang 裁定**（登记 §9-R3）。**落地前不得当作正式口径引用**。**锚点（实测）**：现状 `stamps` **79 行**、影像 **79 个**、`output` **3.4 MB**、库 **576 KB**、可用磁盘 **169 GB**、RAM **16 GB**。

| 触发条件（**任一命中**） | 必须换成什么 | 为什么（依据） |
| --- | --- | --- |
| **① 影像文件数 > 2 万** 或 **影像总量 > 50 GB** | 影像 ⇒ **对象存储**（content-addressed，**以 `sha256` 命名 / 去重**） | 单机目录在**数万文件**量级后 `ls`/备份/迁移成本陡增；且 §9.6 已预留「后续可换对象存储 + 队列」。以 `sha256` 命名为**唯一可行**的幂等锚（§9.4 图片幂等同源）。 |
| **② 主表（`stamps` + `seals`）合计 > 20 万行** | 著录表 ⇒ **PostgreSQL** | 规模口径「数千本 × 数千页」（Kevin 原话）在**页级**即到数十万～百万级；SQLite **单写者**不满足并行写与远程访问。> 20 万行为**保守**阈值，取的是「单库备份窗口与写并发开始难受」的经验点。 |
| **③ 需要 ≥ 2 个写者进程 / 写者跨主机** 或 **需要远程 / 多机读** | ⇒ **PostgreSQL**（写入者从 1 变 N） | WAL 只允许**一个写者**（§4.3）；跨机访问 SQLite 文件是反模式。**此条一旦成立，与行数无关，必须换。** |
| **④ 单库全量备份窗口 > 5 分钟** | ⇒ **PostgreSQL**（+ 增量 / PITR） | 备份窗口是运维硬指标；现库 576 KB（**秒级**），余量充分。 |

**换的时候的迁移锚（必须先具备，才能谈换）**：

1. **`sha256`**（影像内容）——对象存储去重键与迁移完整性校验（现有 `images.sha256` 列已具备）；
2. **`(pdf_name,page,idx)`**——记录行唯一锚（§2.4；**须先补唯一约束**）；
3. **`dedupe_key`（§9.4 口径）**——跨系统去重锚（现有 `seals.dedupe_key` 列已具备）；
4. **`batch_id`**——批次回滚锚（§9.6；现有 `export_batches` 已具备）。

**边界纪律**：**在上述触发条件命中前，不得提前引入对象存储 / PostgreSQL**（避免为了「以后」而牺牲现在——§1.2 I-1/I-2 的效率前提是现阶段的实测结论）。

---

## 5. 并发与资源

### 5.1 worker 数口径

| 项 | 口径 | 依据 |
| --- | --- | --- |
| 硬件基线 | **10 物理核 / 10 逻辑核**（`sysctl -n hw.physicalcpu hw.logicalcpu`） | §0.3 实测 |
| **默认 worker 数** | **8**（**草案，待 Zang 裁定**；登记 §9-R4） | 留 **1 核**给接口层 / 前端 / 系统，留 **1 核**给 OCR 峰值与 I/O 抖动。**不得**把 10 核全部分给 worker。 |
| 上限 | **10**（= 物理核数）；**超过物理核数须 Zang 明示** | 单页渲染/OCR 均为 **CPU 密集**（§0.3：单页渲染 66 ms、PaddleOCR init 1.8 s） |
| 下限 | **1**（1 即「串行基线」，§7 AC-04 的对照臂） | 并行必须能与串行**逐条一致**，故串行模式**必须保留可跑** |
| 队列形态 | **进程内队列**或**本地持久队列**（形态由 Kong 定） | 本文件只约束**可见行为**（§3 S-4/C 的 E5 与 §2.3 断点必须落盘） |

### 5.2 OCR 实例：全局单例 → **每 worker 一实例**

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 实例数 | **1 个全局单例**：`processor.py` 行 **20–23** `_get_ocr()`（`global _ocr_instance`） | **每 worker 进程内 1 个实例**（**进程内单例、跨进程不共享**） |
| 为什么必须改 | 全局单例在**多进程**下**不成立**（每进程有独立内存空间，「全局」只是**进程内**的全局）；且现状「单核串行」下它就是**唯一实例**，扩 worker 后自然要**每 worker 一份** | —— |
| 单实例代价（**实测**） | **init ≈ 1.8 s**；**常驻 RSS ≈ 0.70 GB**；**峰值 RSS ≈ 0.81 GB** | 8 个 worker ⇒ **≈ 6.5 GB**（按峰值 0.81 GB × 8 ≈ 6.5 GB），**占 16 GB RAM 的 ≈ 41 %** |
| 初始化时机 | 现状在首次 OCR 时 lazy init | **worker 启动即预热**（避免首个 chunk 承担 1.8 s 抖动）；**不得**在每页 / 每 chunk 重新 init |
| 模型与联网 | PP-OCRv6_medium_det + rec，**模型本地缓存**（`~/.paddlex/official_models`），**全程不联网下载、不上传** | **保持**（feicui 定位为本地工具；与平台规范 §9.1「本地运行，不上传外网」一致） |

### 5.3 内存上限与单 job 并发上限

| 项 | 口径 | 依据 |
| --- | --- | --- |
| **单 job 并发上限＝1** | **同一本书同时只允许 1 个 `RUNNING` job** | 防同书双写、防重复影像（§2.4 / §3.2 S-5） |
| **全局 job 并发上限＝worker 数** | 同时在跑的 job 数 ≤ worker 数（**默认 8**），超出的 job 排队 `QUEUED` | 队列语义，非资源浪费 |
| **单 job 页内并发上限＝1** | 页内多印**串行**处理（同一页不并发） | 现状 `stamps.idx` 的顺序语义 + bbox 依赖（页内先检测后切图） |
| **不得全量累积内存** | **现状问题**：`process_pdf` 把结果**全量累积在 `all_results` 内存里**，最后一并落库（派单基线） | ⇒ 目标形态必须**按 chunk 流式落库**（§4.3）；判负形态＝「页数增长而内存线性增长、且末尾才提交」 |
| **内存预算（草案，待裁定）** | 全机可用 **16 GB**；`worker 池（8 × 0.81 GB ≈ 6.5 GB）` + 接口层/前端 + 系统 ⇒ **worker 池 RSS 上限 ≈ 8 GB**（约 50 % RAM）；超限时**降 worker 数**而非降协议 | 峰值 RSS 为实测值（§0.3）；**阈值同属 Jing 草案**（§9-R3/R4 一并裁定） |
| **磁盘预算** | `output` 现 **3.4 MB** / 可用 **169 GB** | §4.4 阈值 ① 以 50 GB 为换栈触发点 |

---

## 6. 端口与登记口径

### 6.1 端口分配（本规范口径）

| 服务 | 端口 | 说明 | 实测空闲证据 |
| --- | --- | --- | --- |
| **feicui 前端（Vue）** | **5195** | **主入口**（Kevin 裁定）；`strictPort:true`，**不得**静默回退 | `lsof -nP -iTCP:5195 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5195` → **CLOSED**（核验时点 2026-09-20 10:38） |
| **feicui API（FastAPI）** | **5196** | **本文件新分配**（PORTS.md 内**无 5196 条目**，非占用、非保留） | `lsof -nP -iTCP:5196 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5196` → **CLOSED**（同一时点） |

**为何选 5196**：① **实测空闲**（上表）；② **不在保留段**（PORTS.md §1(c)：保留仅 **5173 / 5174**）；③ **不与既有条目相邻冲突**（5195 前端 / 5197-5198 为 jiazu legacy 退役中 / 5199 jiazu H5）；④ **与前端 5195 同段**便于辨识。**同时实测 5200 / 5201 / 5202 亦空闲**（留作后备；`jiazu/README.md` 示例曾用 5201，故**优先 5196**）。

### 6.2 与 `ctrl/index.js` `services` 表五要素的对应（**登记形态，落地由 Kong**）

| 五要素 | `feicui`（前端） | `feicui-api`（后端） |
| --- | --- | --- |
| **sid** | `feicui` | `feicui-api` |
| **端口** | `5195` | `5196` |
| **启动命令** | `npm run dev`（Vite，`server.port=5195` + `strictPort:true`） | `./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196`（**形态草案**，入口文件名由 Kong 定） |
| **cwd** | `/Users/kevin/bistro/shu/feicui/web`（**计划路径**） | `/Users/kevin/bistro/shu/feicui` |
| **env** | **无**（端口写 `vite.config.*`，不依赖 env） | `PORT=5196`（如需）；**须继承 `PATH`**（面板 spawn 语义，PORTS.md §3 排错要点） |
| **`group`**（必填） | `shu`（**与 5164 同组**——feicui 属印索项目族、位于 `bistro/shu/` 之下） | `shu` |
| **`directUrl`**（可选） | `http://localhost:5195`（**与 §2 既有 6 条同形**；若 Kong 落地时采用 `127.0.0.1` 字面，则按 PORTS.md 制度 (d) 更新本表并登记） | **无**（后端服务不设 directUrl，与 `jiazu-api` / `jinli-api` / `liwu-proxy` 同例） |

> **⚠ 落地顺序纪律（必须先读）**：**在 `feicui/web` 前端工程目录真实存在并可 `npm run dev` 之前，`feicui` 行不得写入 `index.js` 的 `services` 表**——否则面板**批量启动 / `startAll`** 会因 cwd 不存在而失败，**破坏「面板托管 N/N 全监听」的既有判据**（PORTS.md §3.1 / §4-P6 的口径）。**登记顺序＝先登记（本文件 + PORTS.md）、再落地工程、最后入 `services` 表**（Kong）。

### 6.3 真源与同步责任

| 真源 | 内容 | 同步责任 |
| --- | --- | --- |
| `ctrl/PORTS.md` | **端口文档真源** | **Jing** 本版已追加登记行（含端口 / 启动命令 / cwd / group / directUrl + 变更记录），并注明**运行时真源由实现侧 Kong 同步落地** |
| `ctrl/index.js` `services` 表 | **运行时真源** | **Kong**（Jing 不改代码）；落地后本文件 §6.2 与 PORTS.md **按实况回填** |
| 本文件 §6 | feicui 侧端口口径 | **Jing** |
| `feicui/web/vite.config.*` | 前端端口配置 | **Kong**（`strictPort:true`，**不得**回退 5173/5174——PORTS.md §1(c)） |

**三处同步纪律**（沿用 PORTS.md §1(b)）：任何端口变更必须**一次改齐** —— ① 项目自身配置 ② `PORTS.md` ③ 本文件（feicui 的 spec）。**只改其一即为口径漂移**。

---

## 7. 验收判据（AC）——**逐条可机械判负**

> **用法**：每条给出「**判据**（可机械复算）」＋「**证据形式**（须落盘留档）」＋「**判负形态**」。**判负形态命中即 FAIL**，不做「偶发 / 轻微 / 人工点测已确认」类豁免。**证据目录口径**沿用平台侧：留档于项目内证据目录（**不得**以 `/tmp` 临时物作证据）。

| AC | 判据（可机械复算） | 证据形式 | 判负形态（命中即 FAIL） |
| --- | --- | --- | --- |
| **AC-01 同书重跑幂等（行级）** | 同一 `pdf_path`、同一 `page_range` **连跑两次**；第二次结束后 `select count(*) from stamps where pdf_name=?` **不变**，且第二次的 `counters.inserted == 0` | 两次跑前/跑后的 `count(*)` + 逐字段 diff（对旧行） + E2 的 `counters` 快照 | 条数增加；或 `inserted > 0`；或旧行任一字段被改写 |
| **AC-02 同书重跑幂等（影像级）** | 两次跑后，影像目录**文件数不变**，且各文件 `sha256` **逐一不变** | 跑后 `find … -type f \| sort` + `sha256sum` 清单两次对比 | 文件数增加；或同名文件内容变；或出现同内容不同名的新文件 |
| **AC-03 断点续跑不重复** | job 跑到 **X %**（0 < X < 100）后 **SIGKILL** 全部 worker → 重启同一 job 续跑至结束；最终行数 == **串行一次跑完**的行数，且 `count(*) == count(distinct pdf_name\|\|'\|\|'\|\|page\|\|'\|\|'\|\|idx)` | 事件时序（kill 时点 + 续跑起止）、行数复算、重复性复算 SQL 输出 | 行数不等；或重复性复算不等；或断点之前的页**被重写**（字段 diff 非空） |
| **AC-04 并行 == 串行逐条一致（含 bbox）** | 同一本书、同一模板，在**空库**上分别以 **worker=1** 与 **worker=N** 各跑一次；导出 `(pdf_name,page,idx,text,x1,y1,x2,y2)` 全字段、按 `(page,idx)` 排序后 **diff** | 两臂的导出文件（CSV/JSONL）+ `diff` 原始输出（须 **0 差异**） | 任一行**任一字段**不同；或行数不同；**特别地 `x1y1x2y2` 任一分量不同即 FAIL**（bbox 必须逐条一致） |
| **AC-05 进度真实（不得假进度）** | 任意时刻 E2 的 `done_pages` **必须**等于「按已完成 chunk 记录复算的页数」；`state=DONE` 时 `failed_pages` **必须**为空；`progress_ratio = done_pages / total_pages` 与复算值**误差 ≤ 1 页** | E2 响应快照（含时间戳）+ 同刻库内 chunk 状态复算输出（**两者并排给出**） | 进度与复算不一致；或 `failed_pages` 非空而 `state=DONE`；或进度由计时器/估算推进（无法与库内复算对齐） |
| **AC-06 影像缺失清单可查** | E5 `?kind=image` 返回的 `count` **必须**等于「逐条 `os.path.exists(img_path)` 为假的记录数」的独立复算值 | E5 响应 + 独立复算脚本输出（同刻） | 两者不等；或该端点不存在 / 无法按此复算 |
| **AC-07 释文缺失清单可查** | E5 `?kind=text` 的 `count` **必须**等于 `select count(*) from stamps where text is null or trim(text)=''` 的独立复算值（**现状基线 77，核验时点 2026-09-20 10:38**） | E5 响应 + 复算 SQL 输出 | 两者不等；或端点不存在 |
| **AC-08 必备 11 项覆盖可查** | E3 每条记录**必须**给出平台规范 **§9.3 的 11 项必填字段**（或明确给出 `missing_required[]` 原因）；**不得**静默缺字段 | E3 分页响应样本 + `missing_required` 逐条清单 | 缺字段且无 `missing_required`；或字段名与 §9.3 不一致（**以平台规范为准**） |
| **AC-09 幂等键可独立复算** | 记录中的 `dedupe_key` **必须**等于按平台规范 **§9.4 公式**独立复算的值，**且** `bbox` **先按该书 `coord_dpi` 归一化为 pt** 再 `quantize(·,1pt)` | 独立复算脚本输出 + 逐条 diff（须 0 差异）+ 该书 `coord_dpi` 取值来源（`config/book_geometry.json`） | 复算不等；或直接用像素原值量化；或未使用该书 `coord_dpi` |
| **AC-10 批量事务（无每页一次 connect/commit/close）** | 静态：解析链路内**不再存在**「每页一次 `connect` + `commit` + `close`」的形态（现状证据＝`processor.py` 行 432/440/441）；动态：单页写库的**连接开合次数**必须为 **0**（按 chunk 提交） | 静态检查输出（文件 + 行号 + 片段）+ 动态计数（连接开合计数或 DB 层 hook 日志） | 每页仍开合连接；或未按 chunk 提交（逐页 commit） |
| **AC-11 进程分离（计算 / UI 各自生死）** | **SIGKILL 接口层进程**后：① 正在跑的 job 的 worker **仍存活并继续推进** cursor（或按策略落为**可续跑**状态）；② 重启接口层后 E2 能报出**与库内复算一致**的进度 | kill 前后的进程表（`ps`） + cursor 推进证据 + 重启后 E2 响应与复算对比 | 接口层死 ⇒ 丢 job / 丢进度 / 库内出现半页记录 |
| **AC-12 影像外置与库不膨胀** | DB 内**无影像 BLOB 列**、库体积**不随影像线性增长**；`img_path` 为**相对路径** | `PRAGMA table_info` 输出 + 库体积对照（现状 576 KB）+ 抽样路径取值 | 出现 BLOB 列；或库随影像线性增长；或入库绝对路径 |
| **AC-13 端口纪律** | 前端 **5195** / API **5196** 启动后 `lsof` 确认为**新起进程**占用；**未回退** 5173/5174；**未占用** PORTS.md 既有端口 | `lsof -nP -iTCP:<port> -sTCP:LISTEN` + `ps -o pid,lstart,command -p <pid>` | 回退 5173/5174；或占用既有端口；或静默换端口（`strictPort` 失效） |

**AC 计数＝13 条**（**v1.0**）。**每条均为可机械判负**；**证据未留档即视为未通过**。

---

## 8. 现状时点纪律（**本文件范围的强制口径**）

1. **原文**：凡写「现状 / 事实 / 实测 / 当前 / 已核对」类段落，**① 内容必须来自磁盘实测或可复算的命令输出**；**② 必须标注核验时点与证据来源**（格式：`核验时点 YYYY-MM-DD HH:MM（Asia/Shanghai）；证据＝<命令或文件路径>`）；**③ 派单 / 聊天 / 转述与磁盘事实不一致时以磁盘事实为准**，并把差异登记（本文件 **§9** 或 **§10**）。
2. **适用范围（非穷举，示例即示例）**：§0.3 基线表、§3.3 的现状数字、§4.x 的「现状」列、§5.x 的实测代价、§6.1 的空闲证据、§7 AC 里写死的基线值（如 AC-07 的 **77**）。
3. **时点戳是证据的一部分**：**无时点戳的现状读数 = 无效读数**；复检时须**重测并刷新时点**，**不得**沿用旧时点。
4. **不得跨文件外推**：本文件的实测结论**只对 feicui 有效**；平台侧现状（如平台规范 §9.1）**以平台规范为准且由平台侧按 §0.4 流程维护**。
5. **已知的转述 ↔ 磁盘差异（本版登记）**：平台规范 **§9.1 现状表**（v1.24 时点 2026-09-20 的读数：**65 行 / 影像缺失 42-65 / `text` 非空 0-65**）与**本文件核验时点 2026-09-20 10:38 的磁盘实测**（**79 行 / 影像缺失 0-79 / `text` 非空 2-79**）**已漂移**——**差异原因＝Kong 侧 F2 数据恢复与增量重跑**（`feicui/f2_report.json`，`generatedAt=2026-09-20T10:10:00+08:00`）。**处置**：平台侧 §9.1 的更正**属平台规范范围内的动作**（须按其 §0.4 流程：先快照 `docs/versions/` → 升版本 → 写 §0.5 变更记录 → **不动历史行**），**本文件只登记差异、不改平台规范**；登记项见 **§9-R9**。

---

## 9. 待 Kevin / Zang 裁定清单

> 口径：本表**只登记事实与选项**，**不带倾向性结论**；未裁定前**不得**据本表执行实现。**编号 R#**（本文件独立编号，与平台规范 §11.3 的 GB-# 不混用）。

| # | 事项 | 现状（**事实 + 时点 + 证据**） | 待裁选项（一句话可改） | 影响面 |
| --- | --- | --- | --- | --- |
| **R1** | **5164 是否加一条 dev 代理 `/feicui → 5195`** | 已定：feicui 前端**独立端口 5195 为主入口**。**实测**：`shu/web/vite.config.js` 内 `grep -n proxy` **零命中**（核验时点 2026-09-20 10:38；证据＝`grep`）——**该代理目前不存在**。**性质＝待确认项，不得写成已定**。 | ① 不做（5195 独立入口为准）；② 做（须由 Kong 在 `shu/web/vite.config.js` 加 **dev 代理**） | ⚠ **`shu/web/**` 属 M1 已封版冻结**：若选 ②，**必须先由 Zang/Kevin 明确解除该文件的冻结口径**（改它会作废另一角色的验收结论）；且代理只限 **dev**，不得进构建产物 |
| **R2** | **8501 上的 Streamlit 实例处置** | **实测观察（不改状态判定）**：`lsof -nP -iTCP -sTCP:LISTEN` → `Python 71267 *:8501`；`ps -o pid,ppid,pgid,lstart,command -p 71267` → **PID 71267 / PPID 1（已 reparent）/ PGID 71267**，`lstart = Fri Sep 18 09:51:16 2026`，命令＝`…/Python -m streamlit run app.py --server.port 8501 --server.headless false`；RSS **1546448 KB ≈ 1.47 GB**（核验时点 2026-09-20 10:45）。**该实例的状态与处置＝「处置中，见 Kong 报告」——本文件不写状态定论。** Jing **未 kill、未停、未重启、未占用**该进程 | 由 **Kong** 报告处置结论（是否退役 / 何时退役）；Kevin / Zang 确认退役时点 | feicui 退役时序（§1.4）；**阻塞 §1.4「退役完成」判据的最后一环** |
| **R3** | **§4.4 的「必须换栈」阈值草案是否采纳** | §4.4 的 4 条触发条件与量级（**2 万影像 / 50 GB / 20 万行 / 2 写者 / 5 min 备份窗口**）系 **Jing 拟定草案**，**无既有出处**；锚点实测＝现状 **79 行 / 79 影像 / 3.4 MB / 576 KB 库 / 169 GB 可用 / 16 GB RAM** | ① 采纳；② 改数值（给值）；③ 不设阈值（到时再议） | 数据层演进路线、是否引入对象存储 / PostgreSQL 的时点 |
| **R4** | **worker 默认数** | §5.1 拟 **默认 8 / 上限 10**（物理核 10，实测）；§5.3 据此推 worker 池 RSS ≈ **6.5 GB**（单实例峰值 **0.81 GB** 实测）、内存预算 ≈ **8 GB** | ① 采纳 8；② 改值（给值）；③ 按书自动（小书单 worker / 大书多 worker） | 吞吐与内存占用；AC-04 的 N 取值 |
| **R5** | **`group` 归属** | §6.2 拟 `group = shu`（feicui 位于 `bistro/shu/` 下、属印索项目族；PORTS.md §2 既有分组无 `feicui`） | ① `shu`；② 新建独立分组 `feicui`（面板会多一个分组标题） | 面板分组显示、批量启停范围 |
| **R6** | **`feicui` / `feicui-api` 何时写入 `index.js` `services` 表** | 现状：`index.js` `services` 表**无 feicui 条目**（实测 `grep -n feicui index.js` **零命中**，核验时点 2026-09-20 10:40）；且 **`feicui/web` 前端工程目录尚不存在**（`ls feicui/docs` → No such file；`feicui/web` 同） | ① 先落地工程再入表（**本规范 §6.2 的落地顺序纪律**）；② 先入表（**有风险**：`startAll` 会因 cwd 不存在失败，破坏「面板托管 N/N 全监听」判据） | 面板托管范围、批量启停可靠性 |
| **R7** | **feicui 前端工程目录位置与形态** | **缺口：磁盘上不存在**（核验时点 2026-09-20 10:37；证据＝`ls /Users/kevin/bistro/shu/feicui/` 无 `web/`、无 `docs/`）。§6.2 的 `cwd` 写作**计划路径** `/Users/kevin/bistro/shu/feicui/web` | ① `feicui/web`（默认草案）；② 其他路径（给路径） | §6.2 登记值、§7 AC-13 的启动判据 |
| **R8** | **释文（`seal_name`）补齐路线** | **实测**：印面（篆书）直 OCR **不可用**（4 样本 3 个 `max_score=0.0`）；**边款 / 整页影像可用**（0.9989，41 框）；`ocr_text()` 的读取缺陷**已由 Kong 最小修复**；现状 `text` 非空 **2/79**（核验时点 2026-09-20 10:38）。证据＝`f2_report.json` → `3_ocr_feasibility` | ① 继续 OCR 路线（须加**分数阈值 + 去重**，Kong 侧）；② 改人工 / 半人工编目；③ 先解决 **§9.3 `seal_type` 章节映射**（无映射 ⇒ 必填项仍缺） | AC-08 必备项覆盖；平台侧汇入可否开正式包 |
| **R9** | **平台规范 §9.1 现状段落已与磁盘漂移，是否登记更正** | **漂移对照（双向时点）**：平台 §9.1（**其自记核验时点 2026-09-20，v1.24**）＝`stamps` **65 行** / 3 个 `pdf_name` 分别 **30/23/12** / `text` 非空 **0-65** / 影像缺失 **42-65**；**本文件磁盘实测（核验时点 2026-09-20 10:38）**＝**79 行** / **30/23/26** / `text` 非空 **2-79** / 影像缺失 **0-79**。**成因**＝Kong 侧 F2 恢复 + 增量重跑（`f2_report.json`：`2_image_recovery.copied=42 / still_missing=0`、`4_additive_rerun.rows_added=14`（页 7–8）、`5_selfcheck_before_after.rows 65 → 79`） | ① 由 Jing 按平台规范 **§0.4** 流程登记更正（**先快照 `docs/versions/` → 升版本号 → 写 §0.5 变更记录 → 不动任何历史行**）；② 保持现状、只在平台侧 §0.7/§9.1 挂差异化登记 | 平台规范 §9.1 / §9.6「存量」行 / §0.6 证据行的**事实准确性**；**不影响**任何 AC 判据实质（AC-57 等不受影响） |

---

## 10. 变更记录

| 日期 | 版本 | 变更 | 变更人 |
| --- | --- | --- | --- |
| 2026-09-20 | **v1.0** | **建立 feicui 侧独立规范（只写文档，未动 `feicui/**` 任何 `.py` / 数据文件、未动 `shu/web/**`、未动平台规范）**：① **§1 目标形态**——Streamlit UI 退役 → **FastAPI 薄接口层 + 独立 Vue 前端 + 任务队列 / worker 池**，进程分离（计算与 UI 各自生死），并列 **4 条硬不变量**（依据＝Kevin 拍板方向 C + Zang 裁定「UI 框架不在热路径」）；② **§2 任务模型**——**一本书 = 一个 job**、job 内按页 chunk 并行、**页级断点游标**、**同书重跑幂等**（行级 `(pdf_name,page,idx)` + 影像 `sha256`）；③ **§3 API 契约草案**（E1 建 job / E2 查进度 / E3 分页取结果 / E4 触发导出 / E5 缺失清单）＋ **6 条语义纪律**，并与平台规范 **§9.3 必填 11 项 / §9.4 幂等键与 DPI 归一化前置 / §9.6 通道**对齐（**只引用，不动平台规范一字**）；④ **§4 数据层演进**——SQLite 保留 + **WAL** + **索引 `(pdf_name,page)`** + **批量事务**（替换现状**每页一次 connect/commit/close**，证据 `processor.py` 行 432/440/441）＋ 影像外置目录规则 ＋ **对象存储 / PostgreSQL 的四条换栈边界（草案，待裁定）**；⑤ **§5 并发与资源**——worker 数口径（**10 物理核实测**、默认 8 待裁定）、**OCR 由全局单例（`processor.py` 行 20–23）改为每 worker 一实例**（单实例实测 **init 1.8 s / 常驻 0.70 GB / 峰值 0.81 GB**）、单 job 并发上限 1、内存预算；⑥ **§6 端口与登记口径**——前端 **5195**、API **5196**（**实测空闲证据**：`lsof` 无监听 + `nc -z` CLOSED，核验时点 2026-09-20 10:38），`index.js` `services` **五要素对应**（sid / 端口 / 启动命令 / cwd / env + group `shu` + directUrl）与**落地顺序纪律**；⑦ **§7 验收判据 AC-01～AC-13**（**逐条可机械判负**，覆盖同书重跑幂等、断点续跑不重复、**并行与串行含 bbox 逐条一致**、进度真实、影像/释文缺失清单可查、必备 11 项、幂等键复算、批量事务、进程分离、影像外置、端口纪律）；⑧ **§8 现状时点纪律**（自带时点戳与证据来源；**派单转述与磁盘冲突以磁盘为准**）；⑨ **§9 待裁清单 R1–R9**（5164 `/feicui` 代理、8501 实例处置、§4.4 阈值、worker 数、group 归属、入 `services` 表时点、前端工程目录缺口、释文路线、平台规范 §9.1 漂移更正）；⑩ **§0.3 磁盘事实基线**（核验时点 **2026-09-20 10:38–10:45**，含 `stamps` **79 行 / 10 列**、3 个 `pdf_name` **30/23/26**、`text` 非空 **2/79**、影像缺失 **0/79**、`journal_mode=delete`、`stamps` 无索引、机器 **10 核 / 16 GB / 169 GB 可用**、**8501 被占**）。**同时**在 `ctrl/PORTS.md` 追加 feicui 登记行（§2 表 + §5 变更记录），**未重写任何历史行**。 | Jing |
