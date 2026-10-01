# feicui 侧规范（feicui.spec.md）

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **feicui（印谱 PDF 解析工具）的独立侧规范**。本文件**只约束 feicui 自身**（`/Users/kevin/bistro/shu/feicui/**`）；**平台侧（印索）规范一字不改**，跨界处**只作引用**（引用对象＝`/Users/kevin/bistro/shu/docs/yinsuo-web.spec.md`，下称「平台规范」）。 |
| 端口真源 | 跨项目端口唯一真源＝**`/Users/kevin/bistro/ctrl/PORTS.md`**；运行时真源＝**`/Users/kevin/bistro/ctrl/index.js` 的 `services` 表**。本文件第 6 节是**登记口径**，端口数值以 PORTS.md 为准。 |
| 版本 | **v1.3**（2026-09-20｜Jing：按本文件 **§0.4 流程**一次性收口**阶段 1b-i（执行层）+ 1b-ii（E3/E4/E6/E7）**交回的全部规范缺口与 Zang 已裁定口径（**只写文档：本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未启停任何服务、未占端口**）——**① E7 入参补 `page` 并定「`page` 与 `cursor` 互斥（同给 ⇒ `400 BAD_PARAM`）」**（§3.1 E7 行 + **新增 §3.10**；依据＝真实事故：`page` 被框架静默丢弃 ⇒ `has_more` 恒真 ⇒ 客户端死循环）；**② 新增红线判据纪律：凡「数据未变」判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条；依据＝WAL 下 `yinpu.db` **文件** md5 在内容无变化时漂移 `254d3ff1…` → `56cbf7af…`）；**③ AC-03 点位定义钉定为 `done_pages / total_pages`**、`{25%, 50%}` 两点各 ≥1 次、允许 ±1 页容差但证据须写明实际百分比（§7 AC-03）；**④ worker 数口径对齐：§5.1 草案「默认 8」原位更正为 4**（与 AC-04 已钉的 `N=4` 一致，依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽）并留痕（§5.1 / §5.3 / §9-R4 收口）；**⑤ 池的进程形态定案＝独立进程**（池管理器用 `server/.venv`、worker 用 `feicui/venv`；**接口层不含业务真值**）——**AC-11 进程分离的形态依据**（§1.3 表 + §6.2）；**⑥ E7 排序键 `ORDER BY created_at, job_id` 与游标 URL-safe base64 定案**（§3.10）；**⑦ 响应头判据：`x-feicui-scope` 等含非 ASCII 书名时须百分号编码**，并写成**可机械判负**的判据（§3.13；依据＝原写法对中国书名**已真实发生 500**）；**⑧ E4 请求语义定案**（`batch_id` 非空 ⇒ 400、`dry_run=true` ⇒ 400、`book_code` 仅一致性校验、`selfcheck_ref` 口径、`counts` 映射登记；§3.11）；**⑨ E6 错误码定案**（`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`，HTTP 同 404；无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`，**不得**以 `application/octet-stream` 冒充；§3.5 v1.3 块）；**⑩ E3 records 形状与 AC-08 必填 11 项键路径冻结**（顶层平台字段名 + `assets[]` + `feicui` 子对象 + 顶层 `missing_required`；§3.12）；**⑪ `limit` 默认 50 / 上限 500 / 越界或非法 ⇒ 400**、`total` ＝该范围全量条数、`has_more == (next_cursor is not None)` **恒成立**（§3.10）；**⑫ G-e「同区间重解析行数 ≠ 库内行数」写为「待定性」挂账**——AC-01 幂等判据改「**键集合与内容不变**」，**「行数不变」不作判据**（§7 AC-01 + §2.4 + §9-R12）；**⑬ `REPORT_1b-i.md` §6 的 G-1～G-9 逐条判定「本轮已裁 / 仍待裁」并入账**（§3.10 / §5.2 / §5.4 / §7 / §9）；**⑭ 新增 §7.1 验收夹具纪律**（六条护栏 + 断言总数闸门 + 折叠计数 + 版本身份钉；依据＝54,347 行失控与「假绿」两起实测事故）；**⑮ §6.2 按磁盘实测原位更正 sid / directUrl 并登记「面板托管已落地」**（`ctrl/index.js` 实测含 `feicui-api` / `feicui-web` 两条）；**⑯ 平台侧报冲突一项**（§9.3 与 §3.8 对 `sourceBook` / `sourcePageNo` 的必填性不一致 ⇒ §9-R17，**不自行改平台口径**）。**AC 计数仍 13 条**（只改写 AC-01 / AC-03 / AC-08 / AC-10 的判据表述，未增减 AC）；**被取代的原句一律就地留痕「已被 v1.3 取代」**）｜**v1.2**（2026-09-20｜Jing：按本文件 **§0.4 流程**一次性收口阶段 1a 暴露的全部规范缺口与登记项（**只写文档，未动任何代码**）——**① 取图端点正式定契约并定编号 E6**（§3.1 表 + §3.5 全文），**并规定临时路径的收口规则**（原前端单方面假设的 `/api/jobs/{job_id}/stamps/{idx}/image` **已废止**）；**② 后端 8 条缺口 G-1～G-8 全部入账**——G-1 / G-2 错误响应体形状（**新增 §3.4**）、G-3（**AC-07 加书名 × 页区间过滤**，本版最重要）、G-4（**§2.1 表下注**：重跑不换 `job_id` 的真义＝审计锚，非游标容器）、G-5（`total_pages` 派生顺序，§3.1 表下注）、G-6（**非 PDF 以 `%PDF-` magic 为准**，§3.1 表下注）、G-7（**唯一约束落地形态＝唯一索引** `uq_stamps_pdf_page_idx`，§4.1 D-2）、G-8（**允许的额外端点**，**新增 §3.6**）；**③ 前端 5 条缺口全部入账**——G-1（E6，§3.5）、G-2（**新增 E7 `GET /api/jobs`** + 前端过渡形态，§3.1 / §3.8）、G-3（同 ②-G-1/G-2 的 §3.4）、G-4（`/api/health` 定性，§3.6）、G-5（**未实现端点＝`404`**，**新增 §3.7**）；**前端附注**（Vite dev 代理 503 **不属 API 错误码族**、「后端不可达」信号口径）**新增 §3.9**；**④ 登记项 R-1 按 §0.4 收口为正式口径**——§6.2 启动命令 / cwd 原位更正 + **新增 §6.5 解释器矩阵**（API＝`server/.venv`，13 行 freeze；worker＝`feicui/venv`）；**⑤ Neng 复核的 OBS-1 / OBS-2 原位更正**——**AC-11 判负形态列改取反式**（判据实质未改）、**§9-R6 / R7 的「`feicui/web` 不存在」作废**（该目录 **birth 2026-09-20 11:35:25** 已存在）；**⑥ 1c 代理口径按 Zang 原文照录入 §6.4**（`feicui/web` 侧 `base:'/feicui/'` + `hmr.clientPort:5195`；`shu/web` 侧 `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 14 条、AC-88 / AC-89 扫描面不变；生产须网关同构改写；四项验收判据）；**⑦ §0.3 两条现状读数按磁盘实测原位更正**（5195 已被占用 / `shu/web` 的 `/feicui` 代理已落地）。**AC 计数仍 13 条**（只改写 AC-07 / AC-11 的判据表述，未增减 AC）；**被取代的原句一律就地留痕「已被 v1.2 取代」**）｜**v1.1**（2026-09-20｜Jing：**v1.1**（2026-09-20｜Jing：按本文件 **§0.4 流程**修 **Neng 复检 7 项缺陷 D-1～D-7**——**D-1** E3/S-3 分页信封改为「**扩展自**平台 §3.1 信封 + 逐项列差异」（§3.1 表下注 / §3.2 S-3）；**D-2** §6.1 的 5196 口径改为「本文件与 `PORTS.md` v1.8 同轮新分配」（与 §6.3 拉齐）；**D-3** AC-12 改**可复算式**（测量点 / 样本量 / 阈值 / 判定式）并拆出「无 BLOB」独立子项；**D-4** AC-11 钉为**二值判定**；**D-5** AC-03 钉 X 值集 / AC-04 钉 `N=4`（**依据 2026-09-20 实测**）；**D-7** §9-R6/R7 证据句收敛。**并登记**：**8501 已按 Kevin 授权停止的收口（R2 / §1.4 / §0.3）**、**5164 `/feicui` dev 代理已定口径与落地时点（R1 / §6.4）**、**性能基线口径（§5.4，实测 / 推断分离）**。**被取代的原句一律就地留痕「已被 v1.1 取代」，未被取代的原文一律保留**，逐条见 §10）｜**v1.0**（2026-09-20｜Jing 建立） |
| 维护人 | **Jing**（制度 / 口径）。**实现属 Kong**：`feicui/**` 下任何 `.py` / 前端工程 / `index.js` 改动**一律不由 Jing 执行**。裁定人＝**Zang**（派单方）/**Kevin**（拍板方）。 |
| 范围 | `feicui/` 的目标形态、任务模型、API 契约形状、数据层演进、并发与资源、端口登记、验收判据、现状纪律、待裁清单。 |
| 本版硬约束（写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` 或数据文件**（Jing 只写本文档与 PORTS.md 登记行）；② **未改动 `shu/web/**`**（对外站 M1 已封版冻结，改它会作废另一角色的验收结论）；③ **未改动平台规范任何历史版本行**（`shu/docs/yinsuo-web.spec.md` 只在**追加**变更行时按 §0.4 流程处理）；④ **未 kill / 停 / 重启任何进程**、**未占用任何端口**（含 8501 上的 Streamlit 实例，见 §9-R2）；⑤ **PORTS.md 只加行 / 追加状态行**，未重写任何历史行。 |
| 本版硬约束（**v1.1**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / 数据文件 / `config/**` / `output/**` / `exports/**`**，亦**未动** `spike-ocr/**`、`qa-baseline/**`、`qa-recheck/**`（属其它角色已验收证据，改了就要重开验收）；② **未改动 `shu/web/**`**、`shu/mockups/**`、`shu/index.html`、`ctrl/index.js`；③ **未 kill / 停 / 重启任何进程、未占用任何端口**——**8501 的停止系 Kong 于 2026-09-20 10:57:50 按 Kevin 授权执行，非 Jing 动作**（§9-R2 收口）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.26 变更行**，**未改其任何历史行（§0.5 历史行 / 表头「最近修订」历史行 / 页脚历史叙述）**；⑤ **`PORTS.md` 只加行 / 追加状态行**。 |
| 本版硬约束（**v1.2**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**（本轮只写**本文件 + 平台规范 + `ctrl/PORTS.md`**，并各自留快照）；② **未改动 `shu/web/**` 任何代码文件**（含 `vite.config.js`——1c 的该文件改动**系 Kong 执行**，见 §6.4）；③ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 2026-09-20 12:00 运行中的 5195 / 5164 dev server **未受影响**）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.27 行**，**未改其任何历史行**；⑤ **`PORTS.md` 只加行 / 追加状态行**，并按**新采纳的快照纪律**先存 `ctrl/versions/PORTS.v1.9.md`（md5 `6d2eaa6a2dd784615d2e1011611733f8`）；⑥ **不写任何「本轮已实现」句**——凡涉实现侧的状态**一律写「已定、落地中（由 Kong 执行）」并自带时点戳**。 |
| 本版硬约束（**v1.3**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**（本轮只写**本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11**，三处均先存快照：`feicui/docs/versions/feicui.spec.v1.2.md`（md5 `6dbe0b3c915d7f8ed43576a00122dcf1`，521 行）、`shu/docs/versions/yinsuo-web.spec.v1.27.md`（md5 `a32215a4c5efedd069657be24b581933`，1624 行）、`ctrl/versions/PORTS.v1.10.md`（md5 `05f8fce4f075c14df918e6cc4cda7092`，173 行））；② **未改动 `shu/web/**` 任何代码文件**；③ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 **2026-09-20 13:08** 实测：**5195 / 5196 / 8501 均无监听**、5555 / 5164 照常监听，**未受影响**）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.28 行**，**未改其任何历史行**（**AC-01 ～ AC-90 判据实质一字未改、AC 计数仍 90 条、§2.2 路由表仍 14 条**）；⑤ **`PORTS.md` 只加行 / 追加状态行**，并按制度 (e) 先存 `ctrl/versions/PORTS.v1.10.md`；⑥ **不写任何「本轮已实现」句**——凡涉实现侧的状态**一律写「已定、落地中（由 Kong 执行）」或按磁盘实测写读数并自带时点戳**。 |

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
| 端口现况 | **5195 空闲**、**5196 空闲**、**5200 / 5201 / 5202 空闲**；**8501 空闲**（**v1.1 原位更正**：核验时点 2026-09-20 11:29，`lsof -nP -iTCP:8501 -sTCP:LISTEN` **无监听**；原记「**8501 被占**（见 §9-R2）」**已被 v1.1 取代**——存量实例已于 2026-09-20 10:57:50 按 Kevin 授权停止，见 §9-R2 收口注）（**v1.2 原位更正 + 留痕**：核验时点 **2026-09-20 12:00**——**5195 已被占用**（`node` PID **1329**，`TCP 127.0.0.1:5195 (LISTEN)`）、**5196 仍空闲**、**8501 仍空闲**；本行原记「**5195 空闲**」**已被 v1.2 取代**——成因＝**feicui 前端 dev server（阶段 1a 产物）已起**，**非端口纪律问题**（§7 AC-13 照常适用））（**v1.3 原位更正 + 留痕**：核验时点 **2026-09-20 13:08**——**5195 / 5196 / 8501 均无监听**（阶段 1a 的前端 dev server 与 1b 的接口层**当前均未运行**）；**本行 v1.2 的「5195 已被占用」属 12:00 时点读数、现已漂移**，**原句保留、不改写**；另：`ctrl/index.js` **已含 feicui 两条托管条目**，见 §6.2 / §9-R6） | `lsof -nP -iTCP:<p> -sTCP:LISTEN` + `nc -z 127.0.0.1 <p>` |
| 已有前端**无** `/feicui` 代理 | `shu/web/vite.config.js` 内 `grep -n proxy` **零命中**（核验时点 2026-09-20 10:38；**v1.1 复核 2026-09-20 11:29 仍零命中**——落地时点＝feicui 前端骨架起来那一刻，见 §6.4）（**v1.2 原位更正 + 留痕**：核验时点 **2026-09-20 12:01**——`shu/web/vite.config.js` 内 **4 处 `proxy` 命中**（`server.proxy` / `preview.proxy` **各含** `'/feicui'`，**第 48 / 53 行**）⇒ **1c 已落地**；原「**零命中 / 该代理目前不存在**」**已被 v1.2 取代**；口径与验收判据见 **§6.4**；**Jing 未改 `shu/web/**` 任何文件**（改动系 Kong 执行）） | `grep` |

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
| **池管理器（`feicui-pool`）** | ✅（**v1.3 定案**：**独立常驻进程**、**无端口**、**不是接口层的子进程**） | 由运维 / 脚本拉起（`cd feicui/server && ./.venv/bin/python -m app.pool --workers 4`）；**池管理器用 `server/.venv/bin/python`、worker 用 `feicui/venv/bin/python`**（§6.5 解释器矩阵）；**池是唯一写者**（WAL 单写者落地的承载者，§4.3）。**依据（实测）**：AC-11 的「kill 接口层后 worker 继续推进 cursor」**只在「池为独立进程」这一形态下成立**——若改为「接口层拉起池」，则 **AC-11 与该形态互斥**；1b-i 自测 ⑤ 已用 SIGKILL 5196 反证（`REPORT_1b-i.md` §2.1）。**判负**：池出现在接口层的进程树内（接口层死 ⇒ 池死）。 |

**判据（可判负）**：见 §7 **AC-11**。

### 1.4 Streamlit 退役边界（**只定边界，不定时点**）

- **退役对象**：`app.py`（378 行，Streamlit UI 层）与其依赖的 Streamlit 运行方式。
- **退役后不得**：`feicui` 主入口再依赖 8501（改由 **5195** 承担，见 §6.1）。
- **8501 上的存量实例**：**（v1.1 收口）已停**——该实例（`Python -m streamlit run app.py --server.port 8501`，PID **71267**、PGID 71267、PPID 1 孤儿）**已于 2026-09-20 10:57:50 由 Kong 按 Kevin 授权、以进程组 `TERM` 停止**（1 秒内释放、**未用 `KILL`**、无邻接误伤；**证据**＝`feicui/ops/8501_stop_evidence.md` + `feicui/ops/8501_stop_before_after.txt`）；**8501 现已空闲**（§0.3 端口现况行已同步）。**原句「属处置中事项——本文件不写状态定论」已被 v1.1 取代**；**Jing 本人始终未 kill / 未停 / 未重启任何进程**。详见 **§9-R2** 收口注。
- **`requirements.txt` / venv 的清理**属实现侧动作（Kong）；本文件只登记目标：**退役完成时 `streamlit` 不得再是 feicui 的运行依赖**（判据：`requirements.txt` 无 `streamlit`，且 venv 内不再需要它）。

---

## 2. 任务模型

### 2.1 粒度

| 层级 | 单位 | 说明 |
| --- | --- | --- |
| **job** | **一本书 = 一个 job** | 一本书 = 一个 `job_id`（可重跑，重跑**不换 `job_id` 语义**，见 §2.4）。 |
| chunk | job 内的**页区间** | 一本书的页区间切若干 chunk（切法见 §5.3），chunk 为**并行单位**与**断点单位**。 |
| 记录 | 一页内一个印面（`idx`） | 落 `stamps` 一行（语义不变）。 |

**表下注（v1.2 收口｜G-4：「重跑不换 `job_id` 语义」的正解）**：`job_id` 是**审计锚**，**不是**可复用的游标容器。语义固定为五条——① **同一本书的历史 job 记录一律保留**（旧行不删、不重置，其 `job_pages` 保持终态），**重跑＝新 job**；② **`pdf_path` 存在活跃 job（`ACTIVE = {QUEUED, RUNNING, PAUSED}`）⇒ 一律 `409`**（**不看 `rerun`**，§3.1 E1；`409` 体形状见 §3.4）；③ **终态**（`DONE` / `FAILED_PARTIAL`）**不算活跃** ⇒ 允许再次入队，**得新 `job_id`**；④ **不得**复用 / 重置旧 `job_id` 的页游标（这会让 §2.3 的断点锚与 §7 AC-03「断点之前的页不被重写」**失去唯一锚**）；⑤ 任务模型不变（**1 书 = 1 job**）——「不换 `job_id`」的正确读法是「**同一本书的 job 身份由 `pdf_path` 唯一确定**」，**不是**「重跑复用同一行」。
**依据 / 证据**：`feicui/server/README.md` §5「活跃 / 终态口径」（`ACTIVE` / `TERMINAL` 定义、`FAILED_PARTIAL` 不算活跃）+ `REPORT_1a.md` G-4（实测：同 `pdf_path` 第二次 ⇒ **409 + 既有 `job_id`**；`FAILED_PARTIAL` 后可再入队**新 `job_id`**、旧行保留作审计）。**留痕**：§2.1 表内「（可重跑，重跑**不换 `job_id` 语义**，见 §2.4）」一句**原文保留不改**，其**歧义由本注消解**（本注为 v1.2 收口口径）。

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

**表下注（v1.3 收口｜G-e 待定性的口径边界）**：行级幂等的作用面是「**同一 `(pdf_name,page,idx)` 键**」——**同键命中 ⇒ 不得改写既有行、不得新增行**（默认 `skipped`）；**未命中的新键**（该页解析出了原库没有的 `idx`）**允许新增行**。**故「重跑后行数不变」不是本节的语义**——行数是否相等取决于「解析是否稳定复现同一 `idx` 集合」，该问题**已作 §9-R12「待定性」挂账**（Zang 已另派质检定性）；**在定性前，幂等判据一律写成「键集合与内容不变」（§7 AC-01）**。

**与平台幂等键的关系（必须分清）**：feicui 侧行级幂等键是 `(pdf_name,page,idx)`（**落库不重复**）；平台侧幂等键是 **§9.4 的 `dedupe_key`**（**跨系统去重**）。**两者都要**，**不得互相替代**；平台键**必须**按 §9.4 的公式与 DPI 归一化前置计算（见 §3.4）。

---

## 3. API 契约草案（**只定形状与语义，不定实现**）

> 纪律：① 本文只定**形状 / 语义 / 状态码族**，**不定**具体框架内部结构、不定线程模型、不定序列化库；② **不得**因本节的形状设计与平台规范 §9 冲突——冲突时**以平台规范为准**并改本节。

### 3.1 端点一览（草案）

| # | 方法 / 路径 | 语义 | 请求要点（形状） | 响应要点（形状） |
| --- | --- | --- | --- | --- |
| E1 | `POST /api/jobs` | **建 job**（一本书 = 一个 job，入队） | `{pdf_path, page_range?:[from,to], chunk_size?, rerun?:bool}` | `201 {job_id, state, total_pages, created_at}`；相同 `pdf_path` 已存在活跃 job ⇒ **`409` + 既有 `job_id`**（**不得**静默起第二个同书 job） |
| E2 | `GET /api/jobs/{job_id}` | **查进度**（真实进度） | — | `{job_id, state, total_pages, done_pages, failed_pages[], cursor:{chunk_lo,chunk_hi}, counters:{detected,inserted,updated,skipped,ocr_empty}, started_at, updated_at}` |
| E3 | `GET /api/jobs/{job_id}/stamps` | **分页取结果** | `?page=&limit=&cursor=` | **分页信封（＝平台 §3.1 信封的「扩展形态」，v1.1 定性见本节表下注）**：`{items[], page, limit, total, has_more, next_cursor}`（**6 字段**；与平台 §3.1 的 **5 字段** `{items, total, page, pageSize, totalPages}` 的差异**逐项列在表下注**） |
| E4 | `POST /api/jobs/{job_id}/export` | **触发导出** | `{batch_id?, book_code?, dry_run?}` | `{batch_id, package_dir, counts:{formal,draft,rejected}, selfcheck_ref}`（**v1.3 定案**：响应**恰 4 字段**；`counts` 的**映射登记**见 §3.11；`batch_id` / `dry_run` / `book_code` 的请求语义与 `selfcheck_ref` 口径见 **§3.11**） |
| E5 | `GET /api/jobs/{job_id}/missing` | **缺失清单**（影像 / 释文） | `?kind=image\|text`（**v1.2 收口｜G-3**：E5 的口径＝**该 job 的书名 × 该 job 的页区间**——`pdf_name` 取该 job 的 `pdf_name`、`page ∈ [page_from, page_to]`，**不是全表口径**；`reason` 枚举＝`text_empty` / `file_missing` / `img_path_null`；实现**可另**以响应头 `x-feicui-scope` 暴露本次判定范围（**不进 JSON 体**，§3.2 S-3 形状不受影响；**该头含非 ASCII 书名时须按 §3.13 百分号编码**）；**判据见 §7 AC-06 / AC-07，两条已按本口径改写**） | `{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}` |
| **E6** | `GET /api/jobs/{job_id}/stamps/{page}/{idx}/image` | **取印面裁图（二进制）**（**v1.2 新增、正式编号**） | 路径参数：`{page}` **1-based**（↔ `stamps.page`）、`{idx}` **0-based**（↔ `stamps.idx`）；**无查询参数** | `200` **影像字节**（`Content-Type` ∈ {`image/webp`, `image/png`, `image/jpeg`}，**以文件实际类型为准**；`Content-Length` 必填；**不包 JSON 信封**）；`404`＝job 不存在 / `(page,idx)` 记录不存在 / `img_path` 缺失或文件不在盘上（**三类同码**）；`400`＝参数非法；`500`＝读盘 / 解码异常 / **影像类型不可判定**。**（v1.3 定案）**：三类 404 **同码、原因码分列**——`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`；**`img_path` 超出 `FEICUI_ROOT` 或为绝对路径 ⇒ `IMAGE_UNAVAILABLE`**；**无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`**（**不得**以 `application/octet-stream` 冒充）。**契约全文见 §3.5（含 v1.3 块）** |
| **E7** | `GET /api/jobs` | **列 job（分页）**（**v1.2 新增**；**归属 1b 落地**） | `?state=&page=&limit=&cursor=`（**v1.3 定案**：`page` **与** `cursor` **互斥**，同给 ⇒ **`400 BAD_PARAM`**；`page` 1-based、**越末页 ⇒ 空 `items` + `has_more=false`**、**绝不回吐第一页**） | **E3 同款 6 字段信封** `{items[], page, limit, total, has_more, next_cursor}`；`items[`job_id`, `pdf_name`, `pdf_path`, `state`, `total_pages`, `done_pages`, `failed_pages_count`, `created_at`, `updated_at`]`（**v1.3 冻结 9 字段**——原「**形状草案**，1b 落地时按 §0.4 回填」**已被 v1.3 取代**；已核平台规范 §9 与 §3.8，**不构成冲突**，详见 **§3.10**）。**口径与前端过渡形态见 §3.8** |

**E5 的依据**：派单要求「**影像/释文缺失清单可查**」（§7 AC-06 / AC-07）；现状缺口的**规模已实测**：影像缺失 **0/79**、`text` 非空 **2/79**（§0.3）。

**E3 分页信封的定性（v1.1｜D-1 收口）**：**采「扩展自平台 §3.1 信封」口径，并逐项列出差异**（原 v1.0 §3.2 S-3 写「**与平台一致取向**」而**未列差异**，**该表述已被 v1.1 取代**）。

- **平台真值**（平台规范 **§3.1「分页信封」** / §8.2 契约形状②）：`{items, total, page, pageSize, totalPages}`——**5 字段**，约束对象是**平台适配层的分页型方法**（A13 `listUsageRecords` / A21 `listRechargeOrders` / A24 `listLedgerEntries` / A25 `listSeals`）。
- **feicui E3 形态**：`{items[], page, limit, total, has_more, next_cursor}`——**6 字段**。
- **差异逐项**：① **`limit` ↔ 平台 `pageSize`**（**同义不同名**：本文件用 `limit`、平台用 `pageSize`）；② **`has_more`＝feicui 新增**（平台信封无此字段，其值可由 `page` / `totalPages` 推得）；③ **`next_cursor`＝feicui 新增的游标分页字段**（平台信封为纯页码分页、**无游标**）；④ `items` / `total` / `page` 三项**与平台语义一致**（`items` 为实体数组、**不返回裸数组**；`page` 1-based）。
- **为什么选「扩展」而不是直接采用平台 5 字段（理由）**：**(a) 约束面不同**——平台 §3.1 信封约束的是**平台侧适配层方法**，而 **E3 是 feicui 内部端点**，不与平台消费者直接对接；本文件 §3 引言所称「不得与平台规范 §9 冲突」的跨界义务**落在 §3.3 的汇入契约（§9.3 / §9.4 / §9.6）**上，分页信封不在其中；**(b) 取数场景需要游标**——E3 取的是**单个 job 的页级顺序结果集**（§2.1 chunk / §2.3 页级游标），结果集会随 worker 推进而增长，**页码分页在结果追加时会错位 / 重复 / 漏行**，**游标分页**（`cursor` 入参 + `next_cursor` 出参）才稳定；**(c)** `limit` / `has_more` 便于前端做无限滚动与增量拉取。
- **纪律（本条为 D-1 的收口口径，不得回退）**：① **不得再声称「与平台口径一致」而不说明差异**——凡引用本信封处，一律以本注的**明确定义的 6 字段形态**为准；② 若将来 E3 **需被平台侧直接消费**，或需与平台适配层形态互换，**必须先按 §0.4 变更流程改本节**，或在适配边界做**显式字段映射**（`limit→pageSize`、由 `has_more` 合成 `totalPages`、按需丢弃 `next_cursor`），**不得默认两者可互换**。

**E1 的两项派生态口径（v1.2 收口｜G-5 / G-6）**：

- **`total_pages` 的来源（G-5）**：**派生顺序固定**——① 给了 `page_range` ⇒ 取**区间宽度**（`to - from + 1`，1-based 闭区间）；② 未给 ⇒ **读 PDF 页数**；③ **两者皆不可得 ⇒ `422`**（体含缺失清单 `missing: ["total_pages"]`，形状见 **§3.4**）。`total_pages` 是 **E1 时点快照**（＝该 job 落下的 `job_pages` 行数），**E2 一律复算、不读快照**（§3.2 S-1）。**`page_range` 不得改为必填**（单书全量入队不该逼人肉数页）；**读页数属接口层的派生态职责**——§1.2 I-2 只禁「UI 框架进热路径」，**不禁**接口层读 PDF 元数据；读页数**必须**用 **worker 侧解释器**（`feicui/venv/bin/python`）**子进程**完成，**不得**为读页数而把 PyMuPDF 装进 `server/.venv`（§6.5 解释器矩阵 / R-1）。
- **非 PDF 文件的判定（G-6）**：**必须以内容为准**——**`%PDF-` magic 校验**（文件**前 1024 字节内**出现 `%PDF-`）；**不得**只按扩展名分流。**依据（实测）**：PyMuPDF 按扩展名宽松分流——`.txt` 被当文档打开并报 **1 页**（⇒ 不做校验会把纯文本当 1 页 PDF 收下），`.bin` 抛 `FileDataError`（证据 `server/selftest/evidence/5B_pymupdf_lenient.txt`；`REPORT_1a.md` G-6）。**判定归属**：校验不过 ⇒ **`400`**（`error = NOT_A_PDF`，形状见 §3.4）；**扩展名非 `.pdf` 而内容确为 PDF ⇒ 允许**（以内容为准）。**落地状态**＝**已定、落地中（由 Kong 执行）**：**1a 未做**（Kong 侧已如实登记 G-6），**1b 补**；**落地前不得声称已校验**。
- **S-3 的「字段封闭」不外推（G-1 收口的口径前提）**：§3.2 **S-3 的「字段缺失 / 多出未定义字段即判负」只适用于 §3.1 已明确定义字段集的成功响应体**（E2 / E3 / E5 / E6 / E7 的 200 形态），**不外推到错误响应体**——错误体形状见 **§3.4**。**理由**：§3.1 E1 只写「`409` + 既有 `job_id`」而**未定字段集**，若把 S-3 外推到 409 体，则任何实现都**无法既「带上既有 `job_id`」又不「多出字段」**（规范自相矛盾，`REPORT_1a.md` G-1）。

---

### 3.2 语义纪律（可判负）

| # | 纪律 | 判负形态 |
| --- | --- | --- |
| S-1 | **进度必须真实**：E2 的 `done_pages` 必须是**已完成页的复算值**，不得由前端计时器 / 估算推进 | 进度与库内复算不一致（§7 AC-05） |
| S-2 | **不得假完成**：有 `failed_pages` 时 `state` **不得**为 `DONE` | `failed_pages` 非空而 `state=DONE`（§7 AC-05） |
| S-3 | **分页信封形状＝平台 §3.1 信封的扩展形态**（**v1.1 定性**；原 v1.0 表述「**分页信封形状与平台一致取向**…（引用平台规范 §3.1「分页信封」口径）」**已被 v1.1 取代**——原句声称一致而未列差异，属 D-1 缺陷）：**判负形态绑定到本节明确定义的 6 字段形态** `{items[], page, limit, total, has_more, next_cursor}`——`items`＝实体数组（**不返回裸数组**）、`page`＝1-based 页码、`limit`＝页长（↔ 平台 `pageSize`）、`total`＝全量条数、`has_more`＝布尔、`next_cursor`＝下一页游标（**无下一页时为 `null`**）。**与平台 §3.1 的 5 字段差异逐项见 §3.1 表下注**（`limit` ↔ `pageSize`；`has_more` / `next_cursor` 为 **feicui 侧新增**） | **字段缺失 / 多出未定义字段 / 字段名与本行形态不符即判负**；**且**：`has_more=false` 而 `next_cursor` 非 `null`（或反之）、`has_more` 与实际是否还有下一页不符、`items` 为裸数组（§7 AC-08 的分页响应样本即证据） |
| S-4 | **接口层不落业务真值**：E2/E3 的数据**以库为准**；接口层内存缓存**不得**成为唯一真源 | 重启接口层丢 job / 丢进度（§7 AC-11） |
| S-5 | **同书并发上限 1**：同一 `pdf_path` 同时只能有一个 `RUNNING` job | 同书两 job 并行写（§7 AC-01） |
| S-6 | **错误码族**：`400` 参数非法 / `404` 资源不存在 / `409` 冲突（同书重复起 job） / `422` 必填字段不可派生 / `500` 内部错误。**枚举三值即可，不多造**（**v1.2 补注**：S-6 只管**码族与语义**，**不定响应体**——各码的**响应体形状见 §3.4**；S-6 的五码枚举**一字未改**） | 出现未定义码族或语义倒挂 |

### 3.3 与平台侧汇入契约的对齐（**引用，不改平台规范一字**）

| 平台规范锚点 | 平台侧原文要点（**照录引用，不改**） | 本文件对其的**承接** |
| --- | --- | --- |
| **§9.3 必填 11 项** | 必填项＝上表第 **1 / 2 / 4 / 6 / 7 / 8 / 9 / 10 / 11 / 13 / 14** 行，即 `seal_name` / `dynasty` / `seal_type` / `asset_kind` / `source_book` / `source_page_no` / `seal_code` / `sha256` / `image_bytes`·`width`·`height`·`color_mode` / `review_status` / `batch_id`；「**必填项缺失即不得进入平台正式库**，只能作为 `review_status=DRAFT` 暂存」 | feicui 侧 E3 / E4 的**每条记录**必须能给出这 11 项（**缺失时**必须附带**可解释的缺失原因**，与 `feicui/exports/selfcheck_report.json` 的 `requiredCoverage` 口径一致）。**现状**：`seal_name` **2/79**、`seal_code` **0/79**、`seal_type` **全部 UNKNOWN 哨兵**（§0.3 与 `f2_report.json` `5_selfcheck_before_after`） |
| **§9.4 幂等键** | `dedupe_key = sha256(sourceBook + '\|' + sourcePageNo + '\|' + quantize(bbox, 1pt) + '\|' + assetKind)`；**且** `sealCode` 为业务唯一键（`UNIQUE`）；图片以 `sha256` 幂等；写入语义＝**upsert** | feicui 侧必须**可独立复算**该键；`bbox` 输入一律为 **pt** |
| **§9.4 DPI 归一化前置（v1.24 限定）** | `bbox` **须先按该书 `coord_dpi` 归一化为 pt**，**再**作 `quantize(·, 1pt)`；**不得**以像素原值直接量化 | feicui 侧 `stamps.x1y1x2y2` 为**像素**且 **DPI 逐书不同**（实测 古玺汇编 **400** / 秦汉印典 **144** / `tmp.pdf` **144**，证据 `feicui/config/book_geometry.json`）⇒ **归一化是硬前置**，已在 `seals.coord_dpi` / `bbox_unit='pt'` / `bbox_pt_*` 落列 |
| **§9.6 通道** | **首版：本地目录投递**（平台侧导入器读取）；后续可换对象存储 + 队列；**交付单位**＝一本书 = 一个批次（`batch_id`）；**回滚**＝按 `batch_id` 整批撤销；**校验清单** 6 项 | feicui 侧 E4 产物**首版仍走本地目录**（`feicui/exports/fb_…/`，实测 12 个批次目录）；**不得**在平台侧未开对象存储前改用远端通道 |

> **纪律（重复声明）**：上表**只是引用**。**平台规范一字不改**；若平台规范升版改了口径，**由平台侧按 §0.4 流程改**，feicui 侧按新口径**同步本表的引用点**（同步记录写入 §10）。

---

### 3.4 错误响应体形状（**v1.2 新增**｜G-1 / G-2 收口）

> **依据**：§3.1 E1 只写「`409` + 既有 `job_id`」而未定字段集（`REPORT_1a.md` **G-1**）；S-6 只枚举码族而未定义体（**G-2**）。**本节形状为**冻结口径**，实现侧既有形态已对齐**（`server/app/models.py::JobConflictResponse`）。

| 码 | 语义 | 响应体（**冻结**） | 判负形态 |
| --- | --- | --- | --- |
| **409** | 冲突：同 `pdf_path` 已有活跃 job（§3.1 E1 / §3.2 S-5） | `{error: "ACTIVE_JOB_EXISTS", job_id: "<既有活跃 job 的 id>", state, total_pages, created_at}`——**`job_id` 必填**，且**必须是既有活跃 job 的 id**；`detail` **可选**（人类可读说明） | 缺 `job_id`；或 `job_id` 指向新 job / 为空；或**静默起第二个同书 job**（与 §7 AC-01 同源） |
| **400** | 参数非法（`pdf_path` 不存在 / 非 PDF、`page_range` 越界或非法、`kind` 缺失或非法、`page` / `idx` 非法） | `{detail: <string 或 object>, error?: <机器码>}`——**必须**含 `detail`；**允许**含 `error`（机器可读码，**推荐**，例 `PDF_NOT_FOUND` / `NOT_A_PDF`） | 无 `detail`；或 HTTP 码与语义倒挂（用 `200` 承载失败） |
| **404** | 资源不存在（未知 `job_id`；未注册的端点，见 §3.7） | 同上：**必须**含 `detail` | 用 `200` + 空对象 / 空数组冒充「没有」 |
| **422** | 必填字段不可派生（`total_pages` 既无 `page_range` 又读不出 PDF 页数） | `{detail: {...}}`，**且必须**给出**缺失项清单** `missing: ["total_pages"]`（可嵌于 `detail` 内） | 报 `422` 而**不说明缺哪一项** |
| **500** | 内部错误 | **必须**含 `detail`；**不得**回吐堆栈 / 绝对路径 / 库文件路径 | 吞异常返 `200`；或把内部路径写进响应体 |

**学科纪律（本节为 D-1/G-1 的收口口径，不得回退）**：
1. 上表**只约束错误体**；成功体的**字段封闭纪律**见 §3.2 **S-3**，**两者不得互相外推**（G-1 的规范自相矛盾的根源）。
2. **除 409 外，错误体允许额外字段**（如 `error` / `missing`）——**多出字段不判负**（明确豁免 S-3 的封闭校验）。
3. **任何错误不得以 `200` 承载**（假成功判负；与 §7 AC-05 同源）。
4. **前端对 409 的处置（v1.2 定）**：**原样展示原始 body**（JSON 美化或纯文本），并按本节口径取 **`body.job_id`** 生成跳转链接——**规范口径是 `body.job_id`**；`body.detail.job_id` / `body.existing_job_id` 之类**启发式探取不再是规范口径**，**仅可**作向后兼容兜底（`feicui/web/README.md` §4-G-3 的启发式范围**据此收窄**）。

### 3.5 E6 取印面裁图契约（**v1.2 新增｜正式编号**）

> **背景（前端阶段 1a 缺口 G-1）**：结果页需展示裁图，而 v1.1 §3 的 E1–E5 **无取图端点**；前端曾**单方面假设**临时路径 `GET /api/jobs/{job_id}/stamps/{idx}/image`（`feicui/web/README.md` §4-G-1；代码集中于 `src/api/stampsImage.js`）。**本版正式定契约、定编号＝ E6**（端点行见 §3.1）。

| 项 | 口径 |
| --- | --- |
| **路径** | `GET /api/jobs/{job_id}/stamps/{page}/{idx}/image`（**带页段**） |
| **为什么必须带 `{page}`** | 行级唯一锚是 **`(pdf_name, page, idx)`**（§2.4）——**`idx` 单值在 job 内不唯一**（同一本书的每一页各自有 `idx = 0..n`）⇒ 只给 `{idx}` 的路径**无法唯一定位一行**，故**必须**带页段；`{page}` **1-based**、`{idx}` **0-based** |
| **入参纪律** | 只有 3 个路径参数、**无查询参数**；**不接受**任何「文件路径」类入参（防目录穿越） |
| **200** | **影像字节**——`Content-Type` ∈ {`image/webp`, `image/png`, `image/jpeg`}（**以文件实际类型为准**）、`Content-Length` 必填、**不包 JSON 信封**；**可选**响应头 `x-feicui-img-path`（DB 内**相对**路径，供对账，**不进体**） |
| **404** | 三类**同码**：① `job_id` 不存在；② 该 `(page, idx)` 在 `stamps` 内不存在；③ 记录存在但 `img_path` 为空**或文件不在盘上**（`os.path.exists` 为假） |
| **400 / 500** | `page` / `idx` 非法（非整数、`page < 1`、`idx < 0`）／读盘或解码异常（**不得吞**，见 §3.4 500 纪律） |
| **纪律** | ① **只读**：不得触发解析 / OCR / 写库（§1.2 I-2）、不得写缓存文件；② **不得**以占位图 / 空白图冒充真图——**无图 ⇒ `404`**（与 §7 AC-06 分工：**缺失清单负责说缺什么、取图端点不伪造**）；③ **不得**从库里读影像 BLOB（§4.1 D-4 ①）；④ 路径**必须**＝`FEICUI_ROOT` + DB 相对路径，并做**越界校验**（不得逃出 `feicui/`）；⑤ 响应 `Cache-Control: no-store`（dev 口径，避免干扰 §2.4 重跑幂等比对） |
| **与 AC 的关系** | E6 **不单列 AC**（AC 计数仍 **13 条**）；其证据面落在 **AC-06**（影像缺失清单）+ **结果页裁图的人工可见性**上。**落地状态＝已定、落地中（由 Kong 执行）**——**落地前不得声称「取图已实现」**；前端结果页仍按现状显示「裁图不可用：临时取图端点未实现（待规范收口）」 |
| **临时路径的收口规则（**必须执行**）** | ① **废止**前端临时路径 `/api/jobs/{job_id}/stamps/{idx}/image`（**2 段之 `idx` 形态**）——**自 v1.2 起它不是契约**；② **后端不得两套并存**：临时路径**不实现**，被调用时返 `404` 即可，**无需**兼容；③ **前端收口为「一处常量」**：改 `feicui/web/src/api/stampsImage.js`（该文件即为此目的集中常量与注释），**不得**在多处硬编码路径；④ **收口完成的证据（须落盘）**：结果页对一条**影像存在**的记录显示**真实裁图**（非占位），对一条**影像缺失**的记录显示「不可用」且**不显示占位图** |

**§3.5 表下 v1.3 块 —— E6 错误码定案（Zang 已裁定；**原文口径写死**）**：

| 情形 | HTTP | 原因码（**机器可读**） | 判负形态 |
| --- | --- | --- | --- |
| `job_id` 不存在 | **404** | `JOB_NOT_FOUND` | 与另两类混用同码却**不区分原因**（客户无法区分「job 没了」与「这一行没图」） |
| `(page, idx)` 记录不存在 | **404** | `STAMP_NOT_FOUND` | 同上 |
| 记录存在但**影像不可得**（含：`img_path` 为空 / 文件不在盘上 / **路径超出 `FEICUI_ROOT`** / **绝对路径**） | **404** | `IMAGE_UNAVAILABLE` | 用占位图 / 空白图冒充真图（**与 §7 AC-06 分工：缺失清单负责说缺什么、取图端点不伪造**） |
| **无法判定影像类型**（既非 webp / png / jpeg，也判不出来） | **500** | `IMAGE_TYPE_UNKNOWN` | **以 `application/octet-stream` 冒充**（把「不知道」装成「知道」）；或吞异常返 200 |
| `page` / `idx` 非法（非整数、`page < 1`、`idx < 0`、小数、URL 编码穿越） | **400** | （参数非法族，§3.4） | 返 200 + 空体 |

- **纪律**：① **HTTP 码同 404、原因码分三类**——「同码」是可判定性 / 安全性的要求（不因区分原因而泄漏存在性以外的信息），「原因码分列」是**可诊断性**的要求（**二者不矛盾**）；② **越界路径一律 `IMAGE_UNAVAILABLE`**（**不得**回吐路径 / 不得尝试读取）；③ **不得**用 `application/octet-stream` 掩盖「类型未知」。
- **依据（实测）**：`REPORT_1b-ii.md` §3.4(b)(c)（三类 404 同码实测；fixture 四例越界：逃出 root 的相对路径 / `/etc/passwd` / 空 `img_path` / 盘上不存在的相对路径）；**同轮 E6 的 200 形态**：`Content-Type` 取**文件实际类型**（实测 `image/png`）、`Content-Length` == 盘上字节数、字节与盘上文件 **sha256 相同**、**不包 JSON 信封**（首字节非 `{`）、`Cache-Control: no-store`、`x-feicui-img-path` == DB 内相对路径（**该头按 §3.13 须百分号编码**）。**Jing 未复跑**（引其证据）。
- **落地状态＝已落地（由 Kong 执行）**；**已废止的两段临时路径** `/stamps/{idx}/image` 需返 **404**（后端**不两套并存**，实测合规）。


### 3.6 允许的额外端点（**v1.2 新增**｜后端 G-8 收口）

- **结论：允许**。§3 定义的 E1–E7 是**最小契约集**，**不是**端点白名单。允许存在**非契约端点**，条件四条：① 路径前缀限于 **`/api/health`**（存活探针）或 **`/api/meta/**`**（元数据 / 运维**只读**视图）；② **不得**与 E1–E7 语义重叠或改名重复（不得出现第二个「建 job」路径）；③ **不得**被任何 AC 的判据依赖（**验收面只用 E1–E7**；`/api/health` 见下条）；④ 新增 / 删除须在 `feicui/server/README.md` 登记（本文件只在**类别**上约束）。
- **现状登记（判定＝合规、保留）**：`GET /api/health`（存活探针）、`GET /api/meta/migrations`（迁移记账只读视图）——来源 `server/README.md` §6 末段 / `REPORT_1a.md` G-8；**实测**（核验时点 2026-09-20 12:00，证据＝`server/app/main.py` 第 **56** / **84** 行）两个路由**均已注册**。
- **`/api/health` 与前端连通性判定（前端 G-4 收口）**：**允许**后端提供 `/api/health`，但 **前端不得把「该端点存在」当作契约或验收依据**（后端**可以不提供**，也可以改变其体形状）；前端 dev 下的连通性判定**仍走 dev server 自己的探针**（`/__feicui/backend-probe`，见 §3.9），并**必须容忍 404**。

### 3.7 「端点尚未实现」的状态码（**v1.2 新增**｜前端 G-5 收口）

- **规范口径＝`404`**（路由未注册）。**依据**：Kong 阶段 1a 实测 **E3 / E4 未注册 ⇒ `404`**（`REPORT_1a.md` §4 与自测附件⑦）。
- **前端宽容面（允许，但须登记）**：前端出于兼容**可**把 **`404` / `405` / `501`** 一并判为「后端尚未提供该接口」——**这是前端宽容处理、不是规范口径**；**不得**把「尚未提供」渲染成空表 / 0 条 / 占位数据（**假数据判负**）。
- **不得**用 `200` + 空 `items` 冒充「接口未实现」（与 §3.4 纪律 3 同源）。
- **落地后语义**：E3 / E4 / E7 落地后本条**仍然成立**（未知 `job_id` 同为 `404`）；区分办法＝响应体形状（框架产生的未注册路由响应须与 §3.4 的 `detail` 形状同形）。

### 3.8 job 列表端点 E7 与前端 G-2 的处置（**v1.2 新增**）

- **缺口（前端 G-2）**：v1.1 §3 只有 E1（建 job）、**无「列 job」**，而任务页需要列表。
- **口径**：**新增 E7 `GET /api/jobs`**（端点行见 §3.1），**归属 1b**（与 E3 / E4 同批）；返回 **E3 同款 6 字段信封**（§3.2 S-3），`items` 字段集见 §3.1 E7 行（**形状草案**，1b 落地时按 §0.4 回填）。**E7 不新增 AC**。
- **E7 落地前的前端行为（现状，允许）**：先试 `GET /api/jobs`；未提供 ⇒ 明确显示「后端尚未提供该接口」，并**另列**一份「**本浏览器本地记录（localStorage；来源＝本机 E1 的 201 响应）**」——**两栏分开、来源标注清楚**（`feicui/web/README.md` §4-G-2）；**该现状不得作为任何验收依据**（过渡形态）。
- **纪律**：本地记录**不得**与后端数据混排、**不得**冒充后端数据；E7 落地后**一律以 E7 为准**，本地记录仅作「本机建过哪些 job」的辅助显示。

### 3.9 Vite dev 代理层的 503 与「后端不可达」信号（**v1.2 新增**｜前端附注收口）

- **事实**：`feicui/web` 的 Vite dev server 在后端不可达时（`ECONNREFUSED`）由**代理 error 钩子**产生 `503 {error:"backend_unreachable"}`（`feicui/web/README.md` §3）。
- **定性（本版定案）**：该 `503` **不属于 feicui API 的错误码族**（§3.2 S-6 的 `400 / 404 / 409 / 422 / 500`）——它是 **dev 代理层**产生的信号，**不由后端实现、不进构建产物、生产无此路径**；**API 自身码族未改动**（S-6 原文一字未改）。
- **「后端不可达」信号口径：定义，但仅限 dev / 前端侧**——允许**两个**信号并存，且**必须同源**：① dev server 探针 `GET /__feicui/backend-probe`（前端自有中间件，返回 `{reachable, target, detail}`）；② 代理 error 钩子的 `503 {error:"backend_unreachable"}`。**纪律**：① 探针目标与代理目标**必须同源**（同一 `API_TARGET`，默认 `http://127.0.0.1:5196`），**不得**出现「代理指向 A、横幅显示 B」；② 二者**均不属**后端 API 契约（后端**不需要**实现 `backend-probe`）；③ 前端在「网络错误 / `503 backend_unreachable`」时**统一**显示「后端未启动」——**不得**用示例 / 估算 / 缓存值填充（与「无假数据」硬约束同源）；④ 该 `503` **不得**被任何 AC 引用为后端错误语义。

### 3.10 E7 定案：入参 / 互斥 / 排序键 / 游标编码 / items 字段集（**v1.3 新增**｜G-a ～ G-d + 1b-ii §1 缺陷收口）

> **依据**：`REPORT_1b-ii.md` §1（**E7 两处真缺陷**：① 路由/仓库层**根本没有 `page` 形参** ⇒ `?page=N` 被框架**静默丢弃**；② 游标分支把 keyset `WHERE` 与 `OFFSET` **叠加** ⇒ 第 2 页起恒返 0 条而 `has_more` 仍为真 ⇒ 信封出现 `has_more=true, next_cursor=null` ⇒ **客户端死循环**，实测放大成 **54,347 行 / 54,254 条重复 FAIL**）+ §5-G-a ～ G-d。

| 项 | 定案（**v1.3 冻结**） | 依据 / 判负形态 |
| --- | --- | --- |
| **入参** | `?state=&page=&limit=&cursor=` | §3.1 E7 行**同步改写**（原写作 `?state=&limit=&cursor=`、**缺 `page`**，而 §3.2 S-3 的信封含 `page` ⇒ 该不一致即本单缺陷的温床） |
| **`page` 与 `cursor` 互斥** | **同给 ⇒ `400 BAD_PARAM`**（不静默取其一） | 判负：同给返回 200；或 `page` 被静默丢弃（**已真实发生**） |
| **`page` 语义** | **1-based**；**越末页 ⇒ 空 `items` + `has_more=false`**，**绝不回吐第一页** | 判负：越末页返回第一页数据 |
| **`limit`** | **默认 50、上限 500**；**越界或非法 ⇒ 400** | 判负：静默截断 / 静默放大 / 非法值返 200 |
| **`total`** | ＝**该 `state` 过滤范围内的全量 job 条数**（不是本页条数、不是全表） | 判负：`total` 随页变化 |
| **`has_more` 恒等式** | **`has_more == (next_cursor is not None)` 恒成立**（结构性保证：`has_more=true` 而本页无行 ⇒ 强制 `false`） | 判负：出现 `has_more=true, next_cursor=null`（**死循环前兆**）；或反之 |
| **排序键** | **`ORDER BY created_at, job_id`** | **实测依据**：4 个 job 的 `created_at` 常落**同一秒**（12:51:12 三个、13:0x 四个）⇒ **只按 `created_at` 排序无法保证「不重叠 / 不遗漏」**；`job_id` 唯一 ⇒ 全集序**无并列** |
| **游标编码** | **URL-safe base64**（载荷＝`[created_at, job_id]`） | **实测依据**：`created_at` 含 `+` 与 `:`，**直接进 query 会被解码成空格** ⇒ 第二页恒空（`repository.py::encode_cursor_e7` 已留痕）。E3 的 `p<page>_i<idx>` 只由整数构成、天然安全，**不改** |
| **两路一致性** | **页码路径与游标路径的 key 集合必须相等**（不重叠、不遗漏、不重复） | 证据形式：两路逐页 key 集合 + `page_path_equals_cursor_path = true` |

**`items[]` 字段集（**v1.3 冻结 9 字段**）**：`job_id` / `pdf_name` / `pdf_path` / `state` / `total_pages` / `done_pages` / `failed_pages_count` / `created_at` / `updated_at`。**原「形状草案（1b 落地时按 §0.4 回填）」表述已被 v1.3 取代**（G-b）。

- **与平台规范的核对（**必须先核，已核**；依据 Zang 口径「核不上的项列成待裁」）**：**E7 的 `items` 是 feicui 内部实体（job）**——平台规范 **§9** 只定义 **`Seal` + `ImageAsset` 著录模型**（§9.2）、**§3.8** 只定义 **`Seal` 字段集**；**平台规范中不存在「job」实体** ⇒ **无对应字段可核、不构成冲突**；命名风格沿用 **§3.1 E2 的 snake_case**（feicui 内部一致性优先，且 §3.8 的 camelCase 只约束汇入侧著录对象，**不约束 feicui 内部端点**）。
- **核不上的项 = 无**（既无同名冲突项，也无需平台侧裁定的映射项）；**唯一跨界项**是汇入侧的「1 job ↔ 1 批（`batch_id`）」同构关系（§2.1 依据②），**不在 E7 字段面**。
- **落地状态＝已落地（由 Kong 执行，1b-ii 修复轮）**；**Jing 未复跑**（引 `REPORT_1b-ii.md` §1.5 改后翻页全表 / §3.3 与派单方独立复核 §1.7 的照录）。

**G-5 / G-7 收口（v1.3）**：① **任务队列形态 ＝ 库即队列**——`jobs` + `job_pages` **就是持久队列**（断点、并发上限、进度全部由库给出）⇒ **不引入额外队列中间件**（Redis / 消息队列等）；**依据**：AC-11 实测「kill 接口层后 worker 继续推进 cursor」⇒ **队列不在接口层内存里**（§1.1 的「进程内队列或本地持久队列，形态由 Kong 定」**由本条定案为持久队列（库）**）。② **chunk 级「已完成数」不新增 E2 契约字段**——`REPORT_1b-i.md` G-7 指出「§3.1 E2 只给 `cursor:{chunk_lo,chunk_hi}`，而 AC-11 的判据要「已完成 chunk 数」」；**定案**：AC-11 的读数**直接查库**（`select count(distinct chunk_index) from job_pages where job_id=? and state='DONE'`）或取 **E2 的 `cursor.chunk_hi`**，**E2 响应形状不变**（**不得**为验收便利而扩契约）。

### 3.11 E4 请求语义定案（**v1.3 新增**｜E4 请求侧缺口收口）

| 入参 / 字段 | 定案（**v1.3 冻结**） | 为什么（**不得臆造**） |
| --- | --- | --- |
| `batch_id` | **非空 ⇒ 400** | 批次号由 **`export.py` 派生**（`fb_<date>_<book_key>_<NN>`），**不接受客户端指定**——若允许指定，会出现「客户端有、库内无」的假批次 |
| `dry_run` | **`true` ⇒ 400** | `export.py` **无 dry-run 模式** ⇒ **不假装跑过**（与 §3.2 S-6 / §3.4 纪律 3「不得以 200 承载失败」同源） |
| `book_code` | **仅作与 `config/book_codes.json` 的一致性校验**；不一致 ⇒ 400 | 书简码的签发权在平台侧（平台规范 §9.3 #9），**feicui 侧不得借此另立第二份真源**；`issued` 全 `false` 期间该入参**不改变产物命名** |
| 响应字段集 | **恰 4 字段**：`batch_id` / `package_dir` / `counts` / `selfcheck_ref` | 与 §3.1 E4 行一致；多字段即偏离 |
| `counts` | 键名＝`formal` / `draft` / `rejected`（**3 键**）；**映射登记**＝批包 `report.json` 的 `counts.feicuiDecidable` 的 `formal` / `draftStaged` / `rejectedRequiredMissing`（**逐项相等**） | 这是 feicui 内部唯一真值的三键投影；映射必须写明，否则「`draft` 到底等于哪个量」无从复算 |
| `selfcheck_ref` | **`<export_root>/selfcheck_report.json` 存在 ⇒ 给路径；否则 `null`** | **`export.py` 的 export 子命令本身不产生 selfcheck**——生成者是 **`selfcheck_export.py`**；故 **`null` 是正常态**，**不得据此判负** |
| 未知 `job_id` | **404**（体须含 `detail`，§3.4） | 与 §3.7 同源 |

### 3.12 E3 `records` 形状与 AC-08 必填 11 项键路径（**v1.3 冻结**）

> **形状真源＝F1 交付物** `feicui/export.py::build_record`（顶层**平台字段名** + 内嵌 `assets[]` + feicui 专有信息收在 `feicui` 子对象），新键路径由 `server/app/records.py::_shell_record` 对**未导出行**同形补壳。**本表即 AC-08 的判负绑定面**。

| §9.3 # | `missing_required` 取值（**feicui 语义名，snake_case**） | 记录内键路径（**平台字段名形态**） |
| --- | --- | --- |
| 1 | `seal_name` | 顶层 `sealName` |
| 2 | `dynasty` | 顶层 `dynasty` |
| 4 | `seal_type` | 顶层 `sealType` |
| 6 | `asset_kind` | `assets[].kind`（行级常量 `FACE`） |
| 7 | `source_book` | 顶层 `sourceBook` |
| 8 | `source_page_no` | 顶层 `sourcePageNo`（1-based） |
| 9 | `seal_code` | 顶层 `sealCode` |
| 10 | `sha256` | `assets[].sha256` |
| 11 | `image_metrics` | `assets[].bytes` + `assets[].width` + `assets[].height` + `assets[].colorMode`（**4 子键**） |
| 13 | `review_status` | 顶层 `reviewStatus` |
| 14 | `batch_id` | `assets[].batchId` |

- **顶层另有**（非必填项 / 载体字段）：`transcription`、`bbox`（`{x1,y1,x2,y2,unit}`）、`dedupeKey`、`assets[]`、`feicui{}`、**`missing_required[]`**。
- **`missing_required` 一律用 feicui 语义名**（与 `records.py::REQUIRED_KEYS` 与 `exports/selfcheck_report.json` 的 `requiredCoverage` **同名**）。**记录内的平台字段名与 `missing_required` 的语义名是两套命名，映射即本表**——**不得混用**（AC-08 判负绑定到本表的**键路径**，不再以「字段名与 §9.3 字面一致」为判负条件；**该字面一致的旧写法与实现形态冲突，已由 v1.3 取代**）。
- **§9.3 的语义名 → 平台字段名的对齐来源**：平台规范 **§9.3「对应平台字段」列**（`seal_name`→`Seal.sealName`、`sha256`→`ImageAsset.sha256`、`image_bytes`/`width`/`height`/`color_mode`→`ImageAsset` 度量字段、`batch_id`→`Seal.batchId`/`ImageAsset.batchId`）与 **§3.8 / §3.9 字段表**。
- **⚠ 报冲突（**不自行改平台口径**，依据 Zang 口径 10）**：平台规范 **§9.3** 把 `sourceBook` / `sourcePageNo` 列为**必填**，而 **§3.8** 的 `Seal` 字段表把 `sourceBook` / `sourcePageNo` 标为**否（非必填）** ⇒ **平台规范内部必填性不一致**。feicui 侧按 §9.3 执行（**冻结键路径不变**），**冲突登记为 §9-R17**，**转平台侧按 §0.4 裁定**；**本轮不改平台规范任何一字**。

### 3.13 响应头纪律：非 ASCII 值必须百分号编码（**v1.3 新增**｜G-h 收口）

| 项 | 定案（**v1.3 冻结**） |
| --- | --- |
| **适用面** | 凡以响应头承载**可能含非 ASCII 的值**（现存：`x-feicui-scope`（E3 / E5 / E7）、`x-feicui-img-path`（E6））——**头值必须 latin-1 可编码**，含中文书名等非 ASCII 时**必须百分号编码（RFC 3986 `%XX`，UTF-8 字节序）** |
| **可机械判负的判据（4 条，任一不成立即 FAIL）** | ① 头值可被 `str.encode('latin-1')` 编码（**不抛异常**）；② **原始非 ASCII 字符不得直接出现**（正则扫描头值，`[^\x00-\x7F]` 命中数须为 **0**）；③ **解码后与 DB 内字符串字面一致**（`urllib.parse.unquote` 逆变换后与 `stamps.pdf_name` **逐字节相等**）；④ **头不进 JSON 体**（§3.2 S-3 的字段封闭**不受影响**） |
| **判负形态** | 头值直接写中文 ⇒ **HTTP 头值 latin-1 编码失败 ⇒ 500**（**已真实发生**：含中文书名的建单曾被该写法拒掉）；或头值被截断 / 被框架丢弃而客户端拿到空值 |
| **证据形式** | 响应头原始字节 dump + 上述 4 条的复算输出（含 `unquote` 逆变换对照） |

---

## 4. 数据层演进

### 4.1 演进项（SQLite 保留 + 四项改造）

| # | 改造 | 现状（核验时点 2026-09-20 10:38） | 目标 / 口径 |
| --- | --- | --- | --- |
| D-1 | **开 WAL** | `PRAGMA journal_mode` → **`delete`** | `PRAGMA journal_mode=WAL`（进程启动即设并**校验返回值**）；`synchronous=NORMAL` **仅在** WAL 下采用 |
| D-2 | **建索引 `(pdf_name,page)`** | `stamps` 上**无任何索引**（**v1.2 收口｜G-7：落地形态＝唯一索引** `uq_stamps_pdf_page_idx`——SQLite **无法给既有表补表级约束**，只能建**唯一索引**，其幂等语义**等价**（`PRAGMA table_info` 内**不出现**约束行，**不算落地失败**）；**与 §4.1「只许加法」完全相容**；**判据**＝`PRAGMA index_list(stamps)` 含该索引 **且** `PRAGMA index_info(uq_stamps_pdf_page_idx)` 恰为 `(pdf_name, page, idx)` **且** `idx` 唯一性生效；**严禁**为落地「表约束形态」而**重建 `stamps`**（重建＝破坏「只许加法」与既有 79 条数据的判负动作）。**落地前置**＝建索引前**实测重复组为 0**（Kong 侧已实测 0，见 `server/README.md` §4.3）） | 建 `idx_stamps_pdf_page(pdf_name,page)`；**并**建 `UNIQUE(pdf_name,page,idx)` 承载 §2.4 行级幂等（**唯一约束是本规范要求，现状不存在**） |
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
| **默认 worker 数** | **4**（**v1.3 定案，原位更正**；**原「8（草案，待 Zang 裁定）」已被 v1.3 取代**，留痕见本行末注；原登记项 §9-R4 **已收口**） | **v1.3 依据（Zang 已裁定）**：阶段 0b 实测 **`w=4` 到顶、`w=8` 无收益**（单枚成本膨胀 **+114%**、效率 **40%**），且 **swap 近耗尽** ⇒ **以 4 为准**，与 **AC-04 已钉的 `N=4`** 对齐（**原 §5.1 草案值 8 与 AC-04 冲突，本节即该冲突的收口点**）。**留核口径（原文保留）**：留 **1 核**给接口层 / 前端 / 系统，留 **1 核**给 OCR 峰值与 I/O 抖动。**不得**把 10 核全部分给 worker。 |
| 上限 | **10**（= 物理核数）；**超过物理核数须 Zang 明示** | 单页渲染/OCR 均为 **CPU 密集**（§0.3：单页渲染 66 ms、PaddleOCR init 1.8 s） |
| 下限 | **1**（1 即「串行基线」，§7 AC-04 的对照臂） | 并行必须能与串行**逐条一致**，故串行模式**必须保留可跑** |
| 队列形态 | **进程内队列**或**本地持久队列**（形态由 Kong 定） | 本文件只约束**可见行为**（§3 S-4/C 的 E5 与 §2.3 断点必须落盘） |

### 5.2 OCR 实例：全局单例 → **每 worker 一实例**

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 实例数 | **1 个全局单例**：`processor.py` 行 **20–23** `_get_ocr()`（`global _ocr_instance`） | **每 worker 进程内 1 个实例**（**进程内单例、跨进程不共享**） |
| 为什么必须改 | 全局单例在**多进程**下**不成立**（每进程有独立内存空间，「全局」只是**进程内**的全局）；且现状「单核串行」下它就是**唯一实例**，扩 worker 后自然要**每 worker 一份** | —— |
| 单实例代价（**实测**） | **init ≈ 1.8 s**；**常驻 RSS ≈ 0.70 GB**；**峰值 RSS ≈ 0.81 GB** | 8 个 worker ⇒ **≈ 6.5 GB**（按峰值 0.81 GB × 8 ≈ 6.5 GB），**占 16 GB RAM 的 ≈ 41 %** |
| **`cpu_threads` 取值（v1.3 收口｜1b-i **G-9**）** | 规范未写（§5.2 只说「每 worker 一实例」） | **`cpu_threads=2`**（**≤2 上限**）；**不得**回归 `_common_args` 的默认 10。**依据**：§5.4 最优臂 `B_nodoc_w4_ct2`（单页 **2.481 s / 页、3.49×**）；`w=4` 到顶亦与该取值同源（PaddleOCR 内部线程 × 进程数超订） |
| 初始化时机 | 现状在首次 OCR 时 lazy init | **worker 启动即预热**（避免首个 chunk 承担 1.8 s 抖动）；**不得**在每页 / 每 chunk 重新 init |
| 模型与联网 | PP-OCRv6_medium_det + rec，**模型本地缓存**（`~/.paddlex/official_models`），**全程不联网下载、不上传** | **保持**（feicui 定位为本地工具；与平台规范 §9.1「本地运行，不上传外网」一致） |

### 5.3 内存上限与单 job 并发上限

| 项 | 口径 | 依据 |
| --- | --- | --- |
| **单 job 并发上限＝1** | **同一本书同时只允许 1 个 `RUNNING` job** | 防同书双写、防重复影像（§2.4 / §3.2 S-5） |
| **全局 job 并发上限＝worker 数** | 同时在跑的 job 数 ≤ worker 数（**默认 4**；**v1.3 原位更正**：原记「默认 8」**已被 v1.3 取代**，与 §5.1 同源），超出的 job 排队 `QUEUED` | 队列语义，非资源浪费 |
| **单 job 页内并发上限＝1** | 页内多印**串行**处理（同一页不并发） | 现状 `stamps.idx` 的顺序语义 + bbox 依赖（页内先检测后切图） |
| **不得全量累积内存** | **现状问题**：`process_pdf` 把结果**全量累积在 `all_results` 内存里**，最后一并落库（派单基线） | ⇒ 目标形态必须**按 chunk 流式落库**（§4.3）；判负形态＝「页数增长而内存线性增长、且末尾才提交」 |
| **内存预算（草案，待裁定）** | 全机可用 **16 GB**；`worker 池（**4** × 0.81 GB ≈ **3.3 GB**；**v1.3 原位更正**，原按默认 8 计 6.5 GB）` + 接口层/前端 + 系统 ⇒ **worker 池 RSS 上限 ≈ 8 GB**（约 50 % RAM；**该上限系 §9-R3 / R13 的 Jing 草案，v1.3 未改其数值**——按 `w=4` 实际约 3.3 GB，8 GB 为**宽松天花板**）；超限时**降 worker 数**而非降协议 | 峰值 RSS 为实测值（§0.3）；**阈值同属 Jing 草案**（§9-R3/R4 一并裁定） |
| **磁盘预算** | `output` 现 **3.4 MB** / 可用 **169 GB** | §4.4 阈值 ① 以 50 GB 为换栈触发点 |

### 5.4 性能基线口径（**v1.1 新增**｜**实测 / 推断必须分开标注**）

> **来源**：`feicui/spike-ocr/REPORT.md` + `feicui/spike-ocr/results.json`（阶段 0b「OCR 成本归因 spike」）。**该目录属其它角色已验收证据，本版只读引用、不得改动**；**Jing 未复跑该 spike**——下表「性质」列中「实测」项系**引自上列文件**、「推断」项系**本文件据实测换算**。**引用本表时必须连性质一起引用**（§0.2 / §8）。

| # | 口径 | 数值 | 性质 | 来源 |
| --- | --- | --- | --- | --- |
| 1 | **单页现状（单进程串行）** | **8.668 s / 页**——render **0.1587 s** / detect **0.0317 s** / **OCR 8.4777 s（占 97.80%）** | **实测**（引自 spike；Jing 未复跑） | `spike-ocr/REPORT.md` §7 成本模型 + `results.json` |
| 2 | **单页最优配置**（关 doc 预处理 + `w=4` / `cpu_threads=2`） | **2.481 s / 页（3.49×）**，OCR 占比降至 **92.33%** | **实测**（同源，权威臂 `B_nodoc_w4_ct2`） | 同上 |
| 3 | **并行收益与「到顶」** | `w=1 / 2 / 4 / 8` ＝ **1.00× / 1.82× / 2.72× / 3.20×**；**`w=4` 到顶、`w=8` 无收益**（单枚成本膨胀 **+114%**、效率 **40%**，疑 PaddleOCR 内部线程 × 进程数超订） | **实测**（同源） | 同上；**亦为 §7 AC-04 钉 `N=4` 的依据（依据 2026-09-20 实测）** |
| 4 | **900 万页外推** | 现状单核 **902.9 天**；最优配置（`w=4` / `ct=2`）**258.5 天** | **推断**（由实测单页成本 × 900 万页线性外推；**非实测端到端跑 900 万页**） | 本文件据 1 / 2 换算 |
| 5 | 单本换算 | 544 页 ≈ **78.6 分钟**；3000 页 ≈ **433 分钟** | **推断**（同 1 换算） | 本文件换算（与 §0.3 解析吞吐同源） |

**v1.3 收口｜doc 预处理开关（1b-i **G-8**）**：开关名 **`FEICUI_DOC_PREPROCESS`**，**默认 = 1（开）**＝PaddleOCR 默认＝**现状行为**（**默认不得静默变化**）；`=0` 需**显式**开启。**实测**：关闭后**识别文本会变**——但**是样本相关的**：页 20–21 样本 **1/8 条文本不同**、页 63–64 样本 **0/10 条不同**（质检侧独立复现，`qa-recheck/p1b-neng/REPORT.md` §5 / O-3）；**bbox 无一行不同**。**纪律**：**任何「改默认值」的动议都必须先补样本级精度验收**（否则省下的是时间、丢掉的是释文）。

**纪律**：① **性能类读数一律标「实测」或「推断」**（本表「性质」列即为此用）；**未标性质者视为未定义读数**；② **不得用渲染耗时（0.16 s/页 级）外推全量**——该做法会低估约 **60 倍**（瓶颈是 OCR、不是渲染；spike 结论）；③ 本表**只作口径登记**，**不构成换栈、调参或排期依据**（换栈阈值见 §4.4、worker 数见 §5.1，两者均**待裁定**）。

---

## 6. 端口与登记口径

### 6.1 端口分配（本规范口径）

| 服务 | 端口 | 说明 | 实测空闲证据 |
| --- | --- | --- | --- |
| **feicui 前端（Vue）** | **5195** | **主入口**（Kevin 裁定）；`strictPort:true`，**不得**静默回退 | `lsof -nP -iTCP:5195 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5195` → **CLOSED**（核验时点 2026-09-20 10:38） |
| **feicui API（FastAPI）** | **5196** | **本文件与 `PORTS.md` v1.8 同轮新分配**（**原表无 5196、非占用、非保留**；登记行见 **PORTS.md §2**——启动命令 / cwd / group / directUrl 五要素与本文件 §6.2 同源）。**原 v1.0 句「PORTS.md 内**无** 5196 条目」已被 v1.1 取代**：该句写成时 PORTS.md v1.8 的登记行尚未落盘（两文件 mtime 相差 28 秒），既与同文件 **§6.3**「Jing 本版已追加登记行」自相矛盾，也违反 §0.1「不一致时以 PORTS.md 为准并当场修本文件」（D-2） | `lsof -nP -iTCP:5196 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5196` → **CLOSED**（同一时点） |

**为何选 5196**：① **实测空闲**（上表）；② **不在保留段**（PORTS.md §1(c)：保留仅 **5173 / 5174**）；③ **不与既有条目相邻冲突**（5195 前端 / 5197-5198 为 jiazu legacy 退役中 / 5199 jiazu H5）；④ **与前端 5195 同段**便于辨识。**同时实测 5200 / 5201 / 5202 亦空闲**（留作后备；`jiazu/README.md` 示例曾用 5201，故**优先 5196**）。

### 6.2 与 `ctrl/index.js` `services` 表五要素的对应（**登记形态，落地由 Kong**）

| 五要素 | `feicui`（前端） | `feicui-api`（后端） |
| --- | --- | --- |
| **sid** | **`feicui-web`**（**v1.3 原位更正**：原记 `feicui` **已被 v1.3 取代**；核验时点 2026-09-20 13:08，证据＝`ctrl/index.js` 第 58 行） | `feicui-api`（与实测一致，未变） |
| **端口** | `5195` | `5196` |
| **启动命令** | `npm run dev`（Vite，`server.port=5195` + `strictPort:true`）（**v1.2 补充**：**1c 起 `feicui/web/vite.config.js` 另设 `base: '/feicui/'` 与 `server.hmr.clientPort: 5195`**——见 §6.4；端口 / `strictPort` **不变**） | `./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196`（**形态草案**，入口文件名由 Kong 定）**（v1.2 收口｜R-1）**：**实际口径**＝`cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python -m app.main`（等价 `uvicorn app.main:app`；host `127.0.0.1` / port `5196` **不变**）——**解释器＝`server/.venv/bin/python`、cwd＝`feicui/server`**；**原「`./venv/bin/uvicorn app:app`（形态草案）」已被 v1.2 取代**（理由：`feicui/venv/bin/*` console script 因 shebang 失效、且其中**无 fastapi**；完整依据与解释器矩阵见 **§6.5**） |
| **cwd** | `/Users/kevin/bistro/shu/feicui/web`（**计划路径**）（**v1.2 收口**：该工程目录**已建立**——核验时点 2026-09-20 12:00，`stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**；原「**计划路径 / 尚未建立**」表述**已被 v1.2 取代**。**但面板托管（`index.js` `services` 表）仍未落地**：同一时点 `grep -n feicui ctrl/index.js` **零命中** ⇒ 本行的**落地状态＝工程已建立 · 面板托管未落地**） | `/Users/kevin/bistro/shu/feicui`（**v1.2 收口｜R-1**：**实际 cwd ＝ `/Users/kevin/bistro/shu/feicui/server`**——原记 `feicui` 根目录**已被 v1.2 取代**，见 §6.5） |
| **env** | **无**（端口写 `vite.config.*`，不依赖 env） | `PORT=5196`（如需）；**须继承 `PATH`**（面板 spawn 语义，PORTS.md §3 排错要点） |
| **`group`**（必填） | `shu`（**与 5164 同组**——feicui 属印索项目族、位于 `bistro/shu/` 之下） | `shu` |
| **`directUrl`**（可选） **`http://localhost:5195/feicui/`**（**v1.3 按实况回填**：实际值**带 `/feicui/` 前缀**——因前端 `base: '/feicui/'`，直跳必须带前缀；核验时点 2026-09-20 13:08，证据＝`ctrl/index.js` `feicui-web.directUrl`。原记「`http://localhost:5195`（**与 §2 既有 6 条同形**）…」**已被 v1.3 取代**） | **无**（后端服务不设 directUrl，与 `jiazu-api` / `jinli-api` / `liwu-proxy` 同例） |

> **⚠ 落地顺序纪律（必须先读）**：**在 `feicui/web` 前端工程目录真实存在并可 `npm run dev` 之前，`feicui` 行不得写入 `index.js` 的 `services` 表**——否则面板**批量启动 / `startAll`** 会因 cwd 不存在而失败，**破坏「面板托管 N/N 全监听」的既有判据**（PORTS.md §3.1 / §4-P6 的口径）。**登记顺序＝先登记（本文件 + PORTS.md）、再落地工程、最后入 `services` 表**（Kong）。

> **§6.2 表下 v1.3 注 —— 落地实况与「池」的托管口径**：
> ① **落地实况（核验时点 2026-09-20 13:08；证据＝`ctrl/index.js`，md5 `55b101fc643ad06d4bfcb61e56d7710d`）**：`services` 表**已含** feicui 两条——**`feicui-api`**（`port: 5196`、`cmd: './.venv/bin/python'`、`args: ['-m','app.main']`、`cwd: /Users/kevin/bistro/shu/feicui/server`、`env: {PORT:'5196'}`、`group: 'shu'`、无 `directUrl`）与 **`feicui-web`**（`port: 5195`、`cmd: 'npm'`、`args: ['run','dev']`、`cwd: /Users/kevin/bistro/shu/feicui/web`、`group: 'shu'`、`directUrl: 'http://localhost:5195/feicui/'`）。**⇒ v1.2 所记「面板托管未落地（`grep` 零命中）」已被 v1.3 取代**（**改动系 Kong 执行；Jing 未改 `ctrl/index.js` 一字**）。**该文件的 mtime 在本轮核验窗口内仍在变化**（并行写入），**故本注只对该 md5 时点成立**。
> ② **「池」不进 `services` 表**（**v1.3 定案**）：`feicui-pool` 是**无端口**的常驻 daemon ⇒ **不在面板的「端口服务」托管语义内**；由**运维 / 脚本**拉起（`cd feicui/server && ./.venv/bin/python -m app.pool --workers 4`），**生命周期独立于接口层**（AC-11 的形态前提，§1.3 表）。**若将来要求面板托管池**，须先由 Zang 裁定「无端口服务是否入 `services` 表」（本文件不自行改该语义）。
> ③ **三处同步纪律仍适用**（§6.3）：端口 / 启动命令 / cwd 任何一处变化必须**一次改齐**①项目配置 ②`PORTS.md` ③本文件。

### 6.3 真源与同步责任

| 真源 | 内容 | 同步责任 |
| --- | --- | --- |
| `ctrl/PORTS.md` | **端口文档真源** | **Jing** 本版已追加登记行（含端口 / 启动命令 / cwd / group / directUrl + 变更记录），并注明**运行时真源由实现侧 Kong 同步落地** |
| `ctrl/index.js` `services` 表 | **运行时真源** | **Kong**（Jing 不改代码）；落地后本文件 §6.2 与 PORTS.md **按实况回填** |
| 本文件 §6 | feicui 侧端口口径 | **Jing** |
| `feicui/web/vite.config.*` | 前端端口配置 | **Kong**（`strictPort:true`，**不得**回退 5173/5174——PORTS.md §1(c)） |

**三处同步纪律**（沿用 PORTS.md §1(b)）：任何端口变更必须**一次改齐** —— ① 项目自身配置 ② `PORTS.md` ③ 本文件（feicui 的 spec）。**只改其一即为口径漂移**。

### 6.4 `5164 /feicui` dev 代理（**已定口径**，v1.1 登记｜原 §9-R1 待裁项收口）

| 项 | 口径 | 依据 / 落位 |
| --- | --- | --- |
| **要不要** | **要**（**Kevin 已拍板**） | §9-R1 收口（R1 行已同步） |
| **落地时点** | **feicui 前端骨架起来那一刻**——即 `feicui/web` 工程真实存在、可 `npm run dev` 时**同步**；**当前目标不存在**（§9-R7），**故本轮不落地**（**v1.2 补充**：**该前提已于 2026-09-20 11:35:25 满足**——`feicui/web` 工程目录已建立（§6.2 cwd 行 v1.2 注）；**1c 已定、落地中（由 Kong 执行）**，口径原文见本表下 **v1.2 块**） | 与 §6.2 落地顺序纪律同源 |
| **实现形态** | 由 `shu/web` 的 **Vite `server.proxy`** 拦截 `/feicui` → **`http://127.0.0.1:5195`**；**不落 SPA 路由** | 代理属 **dev / 构建服务层**的转发，**不进 `src/router/**`** |
| **对平台路由与判据的影响** | **零**——平台规范 **§2.2 路由表仍 14 条**、**AC-88 / AC-89 扫描面不变**（两条按 `document.body.innerText` 扫那 14 条对外路由；代理**不新增对外路由**、**不渲染任何文案**） | 平台规范 §2.2 / §12 AC-88 / AC-89 |
| **生产部署** | **必须在网关做同构改写**（与平台侧 `consoleEntryRewrite` 同类已知坑：dev 生效而生产不生效 ⇒ 直达 404） | 平台规范 §2.3-6 / 附录 B（环境硬约束） |
| **性质（防误读）** | 属 **M1 冻结面之外的基础设施登记**，**不得当作功能变更**；落地时改的是 `shu/web/vite.config.js` | 平台规范 §1.7 表下 v1.23 注（M1 冻结只禁「功能与门禁变更」，基础设施登记不在其内） |
| **谁写代码** | **Jing 不改任何 `.js` / `vite.config.*` / `index.js`**；落地由 **Kong** 执行，落地后如有形态差异**按实况回填本表**（§6.3 同步责任） | §0.1 / §6.3 |

---


**§6.4 表下 v1.2 块 —— 1c 代理口径（Zang 已定；**原文照录、一字未改**，给实现侧照此执行）**：

> **Zang 已定的 1c 代理口径（原文，v1.2 照录）**：
> - `feicui/web/vite.config.js` 增 `base: '/feicui/'`，并设 `server.hmr.clientPort: 5195`（保留 host `127.0.0.1` / port `5195` / strictPort）；preview 同 base。
> - `shu/web/vite.config.js` 在 `server.proxy` 与 `preview.proxy` 各加键 `'/feicui'` → target `http://127.0.0.1:5195`，`changeOrigin: true`，**不 rewrite 前缀**（因为 feicui 侧 base 已为 `/feicui/`）。
> - **不新增任何 SPA 路由** → 平台 §2.2 路由表仍 **14 条**、AC-88 / AC-89 扫描面不变。
> - 生产部署须网关同构改写（同 console 入口的已知坑）。
> - **验收判据**：① 直连 `http://127.0.0.1:5195/feicui/` 返回 200；② `http://localhost:5164/feicui/` 返回 200 且为 feicui 页面（不是 SPA 404）；③ 14 条对外路由逐一仍正常；④ `npm run check:pricing` + `npm run smoke` + `npm run build` 全通过。

**Jing 附注（口径边界，不改上列原文）**：

| 项 | 口径 |
| --- | --- |
| **1c 落地时点** | **已定、落地中（由 Kong 执行）**。原 v1.1 记「落地时点＝feicui 前端骨架起来那一刻」——该前提**已于 2026-09-20 11:35:25 满足**（`feicui/web` 目录 birth）；**落地状态的读数以磁盘实测为准**（§0.2 / §8），见下「实测」行 |
| **落地实测（核验时点 2026-09-20 12:00–12:01）** | ① `feicui/web/vite.config.js`：`base` 命中（**第 80 行** `base: BASE`，`BASE` 为其上注释所定义之 `/feicui/`）、`hmr: { clientPort: PORT }`（**第 97 行**）、`host: '127.0.0.1'` / `port` / `strictPort: true` **保留**；② `shu/web/vite.config.js`：`server.proxy` 与 `preview.proxy` **各含** `'/feicui'` → `FEICUI_PROXY = { target: 'http://127.0.0.1:5195', changeOrigin: true }`（**第 48 / 53 行**），**无 rewrite**；③ 判据 ① `curl -o /dev/null -w %{http_code} http://127.0.0.1:5195/feicui/` ⇒ **200**；判据 ② `… http://localhost:5164/feicui/` ⇒ **200**；④ 判据 ④ 的 `npm run check:pricing` / `smoke` / `build` **由 Kong / Neng 侧执行，Jing 未复跑（如实标注）**。**证据**＝`grep -n` 输出 + 三条 `curl` 状态码（本注即留档） |
| **性质（防误读）** | 属 **M1 冻结面之外的基础设施登记**（平台 §1.7 表下 v1.23 封版口径只禁「功能与门禁变更」），**不得当作功能变更** |
| **谁写代码** | **Jing 不改任何 `.js` / `vite.config.*` / `index.js`**；两处 `vite.config.js` 的改动系 **Kong** 执行（本版只登记口径与实测事实） |

### 6.5 解释器矩阵（**v1.2 新增**｜登记项 R-1 的正式口径）

> **收口来源**：`feicui/server/REPORT_1a.md`「登记项 R-1」+ `server/README.md` §2。**性质**＝**实现实际口径升为规范口径**（原 §6.2 为「形态草案 / 入口文件名由 Kong 定」；实际偏离**已显式上报**，本轮按 §0.4 收口；§6.2 原草案句**原文保留并留痕**）。

| 角色 | 解释器 | 装了什么 | 为什么 |
| --- | --- | --- | --- |
| **接口层 `feicui-api`（5196）** | **`server/.venv/bin/python`**（**不是** `feicui/venv`） | `fastapi` / `uvicorn` / `pydantic` 等——**3 个直接依赖、freeze 13 行** | §1.2 I-2：**接口层不进热路径、不装 OCR 栈**。**实测**（核验时点 2026-09-20 12:00，证据＝`server/.venv/lib/python3.11/site-packages` 计数）＝**13** |
| **worker（阶段 1b）** | **`feicui/venv/bin/python`** | `pymupdf` / `paddleocr` / `paddlepaddle` / `numpy` / `opencv-python` / …（**86 行 freeze**） | §1.2 I-1：解析与 OCR 仍是**同一份 Python 实现**；§5.2：每 worker 一实例 |
| **feicui Streamlit（退役中）** | `feicui/venv/bin/python` | 同上 + `streamlit 1.63.0` | §1.4 退役边界 |
| **接口层派生 `total_pages`（E1）** | **子进程调 `feicui/venv/bin/python`** | — | `server/app/**` 内**无静态** `import pymupdf` / `fitz`（实测 0 命中）；**不得**为读页数把 PyMuPDF 装进 `server/.venv`（§3.1 表下注 G-5） |

**硬约束（Zang 追加口径 1 / 2，本轮正式入规范）**：① **不得**把新依赖装进 `feicui/venv`，也**不得**升级 / 降级其中任何既有包（`spike-ocr/` 的性能基线全部依赖这套版本）；② `server/.venv` **可重建**，命令＝`uv venv .venv --python 3.11` → `uv pip install --python .venv/bin/python -r requirements.txt` → `uv pip freeze --python .venv/bin/python | wc -l`（实测 **13**）；③ `server/.venv` 已列入 `server/.gitignore`（仓库当前非 git 仓库，为将来预置）。
**判负形态**：接口层进程内出现 OCR 栈 / PyMuPDF；或 `feicui/venv` 被就地改包（与 §7 AC-13 的「环境不被污染」面同源）。

---

## 7. 验收判据（AC）——**逐条可机械判负**

> **用法**：每条给出「**判据**（可机械复算）」＋「**证据形式**（须落盘留档）」＋「**判负形态**」。**判负形态命中即 FAIL**，不做「偶发 / 轻微 / 人工点测已确认」类豁免。**证据目录口径**沿用平台侧：留档于项目内证据目录（**不得**以 `/tmp` 临时物作证据）。

| AC | 判据（可机械复算） | 证据形式 | 判负形态（命中即 FAIL） |
| --- | --- | --- | --- |
| **AC-01 同书重跑幂等（行级）** | 同一 `pdf_path`、同一 `page_range` **连跑两次**；第二次结束后 `select count(*) from stamps where pdf_name=?` **不变**，且第二次的 `counters.inserted == 0` | 两次跑前/跑后的 **键集合（`(pdf_name,page,idx)` 去重后集合）** + **逐字段内容指纹**（对该范围内全部行的有序全字段导出做 sha256）+ 独立复算的 `count(distinct …)` + E2 的 `counters` 快照 | 条数增加；或 `inserted > 0`；或旧行任一字段被改写。**（v1.3 原位改写｜G-e 待定性）**：**判据＝「键集合与内容不变」**，**「行数不变」不再作判据**——**理由**：实测存在「**同区间重解析行数 ≠ 库内行数**」（库 12 → 解析 13；库 30 → 解析 31）而**旧行零改写成立**的观测，其成因**未定性**（检测非确定性 vs 旧解析少一行，§9-**R12**，Zang 已另派质检定性）。**在定性前，判负形态只绑定「旧行被改写 / 新键产生重复行 / `inserted > 0`」**；**新增行数若源于新键，属允许面**（§2.4 表下注）。留痕：原 v1.2 判据的「第二次结束后 `count(*)` 不变」一句**已被 v1.3 取代**（该句仍作为**观测项**要求一并留档，**不作判负依据**） |
| **AC-02 同书重跑幂等（影像级）** | 两次跑后，影像目录**文件数不变**，且各文件 `sha256` **逐一不变** | 跑后 `find … -type f \| sort` + `sha256sum` 清单两次对比 | 文件数增加；或同名文件内容变；或出现同内容不同名的新文件 |
| **AC-03 断点续跑不重复** | job 跑到 **X ∈ {25, 50}**（**两个百分点各至少一次**；**v1.1 钉值**——原 v1.0 写「**X %（0 < X < 100）**」为自由变量，**已被 v1.1 取代**）后 **SIGKILL** 全部 worker → 重启同一 job 续跑至结束；最终行数 == **串行一次跑完**的行数，且 `count(*) == count(distinct pdf_name\|\|'\|\|'\|\|page\|\|'\|\|'\|\|idx)` | **（v1.3 钉定｜G-f 收口）** 点位口径＝**`done_pages / total_pages`**（**唯一**定义，**不采用**「连续已提交前缀」口径；两者在 `chunk_size>1` 且 `w>1` 时**结果不同**——实测 **42.9% / 57.1%（已提交页）vs 28.6%（连续前缀）**）；**`{25%, 50%}` 两点各至少一次**；**允许 ±1 页容差**，但**证据里必须写明实际百分比**（例：25% 点实测 42.9%、50% 点实测 57.1%，两点分别落 `chunk_size=2/w=4` 与 `chunk_size=1/w=2`，见 `REPORT_1b-i.md` §5-10 与 `evidence/1b_ii/46_reg_ac03_kill50_probe.json`）。事件时序（kill 时点 + 续跑起止）、键集合与内容指纹复算、重复性复算 SQL 输出 | 行数不等；或重复性复算不等；或断点之前的页**被重写**（字段 diff 非空） |
| **AC-04 并行 == 串行逐条一致（含 bbox）** | 同一本书、同一模板，在**空库**上分别以 **worker=1** 与 **worker=N=4**（**v1.1 钉值**；**依据 2026-09-20 实测**：阶段 0b 实测 `w=1/2/4/8` ＝ 1.00× / 1.82× / 2.72× / 3.20×，**`w=4` 到顶、`w=8` 无收益**——来源 `feicui/spike-ocr/REPORT.md` + `results.json`，见 §5.4；原 v1.0 写「worker=N」并依赖 §5.1 草案默认 **8** 与 §9-R4，属自由变量，**已被 v1.1 取代**）各跑一次；导出 `(pdf_name,page,idx,text,x1,y1,x2,y2)` 全字段、按 `(page,idx)` 排序后 **diff** | 两臂的导出文件（CSV/JSONL）+ `diff` 原始输出（须 **0 差异**） | 任一行**任一字段**不同；或行数不同；**特别地 `x1y1x2y2` 任一分量不同即 FAIL**（bbox 必须逐条一致） |
| **AC-05 进度真实（不得假进度）** | 任意时刻 E2 的 `done_pages` **必须**等于「按已完成 chunk 记录复算的页数」；`state=DONE` 时 `failed_pages` **必须**为空；`progress_ratio = done_pages / total_pages` 与复算值**误差 ≤ 1 页** | E2 响应快照（含时间戳）+ 同刻库内 chunk 状态复算输出（**两者并排给出**） | 进度与复算不一致；或 `failed_pages` 非空而 `state=DONE`；或进度由计时器/估算推进（无法与库内复算对齐） |
| **AC-06 影像缺失清单可查** | E5 `?kind=image` 返回的 `count` **必须**等于「逐条 `os.path.exists(img_path)` 为假的记录数」的独立复算值 | E5 响应 + 独立复算脚本输出（同刻） | 两者不等；或该端点不存在 / 无法按此复算 |
| **AC-07 释文缺失清单可查** | E5 `?kind=text` 的 `count` **必须**等于 `select count(*) from stamps where text is null or trim(text)=''` **同范围**的独立复算值——复算式固定为 `select count(*) from stamps where pdf_name=? and page between ? and ? and (text is null or trim(text)='')`（`pdf_name` 与页区间＝**该 job 的** `jobs.pdf_name` 与其 `[page_from, page_to]`）。**（v1.2 原位改写｜G-3 收口）**：原 v1.1 的复算式为**全表**口径（`select count(*) from stamps where text is null or trim(text)=''`，**无** `pdf_name` 过滤），**已被 v1.2 取代**——**理由**：E5 是 **job 内该书**口径，在「**1 书 = 1 job**」（§2.1）下，同库有 3 本书时**全表口径恒 ≠ 本 job 口径**，判据**无法机械判负**。**实测证据**（快照 `state_50.db`，核验时点 2026-09-20 11:56；来源 `feicui/server/REPORT_1a.md` G-3 / `server/README.md` §6）：**全表 ＝ 77**（正是 v1.1 所钉基线）、**本 job（`tmp.pdf`，页 13–19）＝ 30**，**差 47**。**全表读数仅作历史留痕，不再作判据** | E5 响应 + **同范围**复算 SQL 输出（**须含 `pdf_name` 与页区间字面量**） | 两者不等；或复算 SQL **未带** `pdf_name` / 页区间过滤（**即以全表口径复算**）；或端点不存在 |
| **AC-08 必备 11 项覆盖可查** | E3 每条记录**必须**给出平台规范 **§9.3 的 11 项必填字段**（或明确给出 `missing_required[]` 原因）；**不得**静默缺字段 | E3 分页响应样本 + `missing_required` 逐条清单 + **§3.12 键路径对照表** | 缺字段且无 `missing_required`；**或键路径与 §3.12 冻结表不符**。**（v1.3 原位改写｜G-10 收口）**：**判负绑定面改为 §3.12 的冻结键路径**（顶层平台字段名 + `assets[].sha256` / `assets[].width` / `assets[].height` / `assets[].colorMode` / `assets[].batchId` + 顶层 `missing_required[]`）；**原「字段名与 §9.3 不一致（以平台规范为准）即判负」的写法已被 v1.3 取代**——理由：§9.3 的字段名是 **feicui 侧需补字段的语义名（snake_case）**，而记录内是**平台字段名（camelCase，§3.8 / §3.9 形态）**，**两套命名并存是既成事实**，按字面比对会把正确实现判负。**`missing_required` 一律用 §3.12 的 feicui 语义名**；**缺项清单为空数组的写法（`[]`）＝「无缺失」，不是「未实现」** |
| **AC-09 幂等键可独立复算** | 记录中的 `dedupe_key` **必须**等于按平台规范 **§9.4 公式**独立复算的值，**且** `bbox` **先按该书 `coord_dpi` 归一化为 pt** 再 `quantize(·,1pt)` | 独立复算脚本输出 + 逐条 diff（须 0 差异）+ 该书 `coord_dpi` 取值来源（`config/book_geometry.json`） | 复算不等；或直接用像素原值量化；或未使用该书 `coord_dpi` |
| **AC-10 批量事务（无每页一次 connect/commit/close）** | 静态：解析链路内**不再存在**「每页一次 `connect` + `commit` + `close`」的形态（现状证据＝`processor.py` 行 432/440/441）；动态：单页写库的**连接开合次数**必须为 **0**（按 chunk 提交） | 静态检查输出（文件 + 行号 + 片段）+ 动态计数（连接开合计数或 DB 层 hook 日志） | 每页仍开合连接；或未按 chunk 提交（逐页 commit）。**（v1.3 钉定适用面｜1b-i **G-1** 收口）**：本条的**静态判据面 ＝「新增解析链路」（池 `app/pool.py` + `worker/feicui_worker.py`）**——该链路必须**按 chunk 一事务提交**且 **worker 进程 0 次 DB 连接**；**`processor.py` 行 432/440/441 的「每页一次 connect/commit/close」属 §1.4 的 Streamlit 退役边界内遗留形态**（1b-i 依派单硬约束「只许加法、默认行为不变」**未改其一个字节**）⇒ **legacy 形态不单独判负**，但**退役完成时须一并消除**（§1.4 退役判据）；**判负只针对新链路**。**留痕**：原判据的适用面**未被写明**（1b-i 自认会「仍会命中 `processor.py`」），**该歧义由 v1.3 消解**；如 Zang 另有裁定，**一句话可改**（把 `processor.py` 一并纳入判据面或维持本条） |
| **AC-11 进程分离（计算 / UI 各自生死）** | **SIGKILL 接口层进程**后：① **二值判定**——**worker 进程仍存活**（`kill -0 <worker_pid>` 退出码 **0**、被 kill 后首次采样即在进程表中）**且 cursor 单调推进**（相邻两次采样间隔 **≥ 5 s**，`chunk_hi` 或「已完成 chunk 数」**严格不减 / 增长**）——**两项同时成立＝通过，任一不成立＝FAIL**；② 重启接口层后 E2 能报出**与库内复算一致**的进度。**备注（v1.1）**：原 v1.0 的「**或按策略落为可续跑状态**」**已删除**（「按策略」未界定、复检者无法定判，属 D-4）；**「可续跑」能力不改由本条判定，由 AC-03 判定** | kill 前后的进程表（`ps`） + **可复算命令**：`kill -0 <worker_pid>; echo $?`（须为 `0`）、`ps -o pid,lstart,command -p <worker_pid>`、两次采样 `sqlite3 yinpu.db "select count(*) from <chunk 日志表>"`（或 E2 的 `cursor.chunk_hi`）× 间隔 ≥ 5 s 的取值 | **取反式（v1.2 原位等义替换｜Neng 复核 OBS-1）**：接口层 SIGKILL 后——① worker 进程**未存活**（`kill -0 <worker_pid>` 退出码 **≠ 0**，或被 kill 后**首次采样即不在进程表**）**或** ② cursor **未单调推进**（相邻两次采样间隔 **≥ 5 s**，`chunk_hi` 或「已完成 chunk 数」**减少或不变**）⇒ **任一成立即 FAIL**；**或**重启接口层后 E2 报出的进度与库内复算**不一致**；（可选，非判负项）库内出现半页记录。**留痕**：本列原 v1.1 叙述「接口层死 ⇒ 丢 job / 丢进度 / 库内出现半页记录」为**旧叙述**（与「判据」列已钉的**二值判定**不同构，故复检者无法据此定判），**已被 v1.2 取代**——**判据实质一字未改**，仅**判负形态改为该二值判据的取反式** |
| **AC-12 影像外置与库不膨胀** | **（v1.1 改为可复算式；原 v1.0「库体积**不随影像线性增长**」未给测量点 / 样本量 / 阈值 / 判定式，**已被 v1.1 取代**）**分三个**独立子项**，逐项二值判定：**① 无影像 BLOB 列**——`PRAGMA table_info(stamps)`（并查 `seals` / `images`）的 `type` 值**均不含 `BLOB`**；**② 库体积增量与影像字节不相关（斜率阈值）**——影像数 **N ∈ {0, 100, 1000}** 三档，各档导入后测 **`du -k feicui/yinpu.db`**（KB），**判定式＝斜率 `k = ΔKB / ΔN < 1 KB/影像` 判通过**（即 1000 个影像带来的库增长 **< 1 MB**）；**等价复算式（二选一，须在证据中写明选了哪个）**：**`PRAGMA page_count × PRAGMA page_size` 的增量 < 该批影像总字节 × 1%**；**③ `img_path` 为相对路径**——抽样 **≥ 10** 条记录，`img_path` **不以 `/` 开头**、**不含用户目录前缀**（须匹配 `^[^/]` 且不含 `/Users/`） | **①** `PRAGMA table_info` 原始输出（全文搜索 `BLOB`，**计数须为 0**）；**②** 三档 N 的 `du -k`（或 `page_count × page_size`）**原始读数 + 斜率复算过程**（须给出两次 N 与两次测值）；**③** `img_path` **抽样清单（≥10 条）+ 相对性校验输出** | **任一子项命中即 FAIL**：**①** 出现 `BLOB` 列；**②** 斜率 **≥ 1 KB/影像**（或 `page_count × page_size` 增量 **≥ 影像总字节 × 1%**）；**③** 入库绝对路径（`/` 开头或含 `/Users/`） |
| **AC-13 端口纪律** | 前端 **5195** / API **5196** 启动后 `lsof` 确认为**新起进程**占用；**未回退** 5173/5174；**未占用** PORTS.md 既有端口 | `lsof -nP -iTCP:<port> -sTCP:LISTEN` + `ps -o pid,lstart,command -p <pid>` | 回退 5173/5174；或占用既有端口；或静默换端口（`strictPort` 失效） |

**AC 计数＝13 条**（**v1.0** 建立；**v1.1 未增减任何 AC，仍 13 条**——本版只改写 **AC-11**（钉为二值判定）与 **AC-12**（改可复算式并拆出「无 BLOB」独立子项），并为 **AC-03 / AC-04** 钉值）。**v1.2 亦未增减任何 AC：仍 13 条**——本版只**改写** **AC-07**（加书名 × 页区间过滤）与 **AC-11**（判负形态列改取反式）两条的**判据表述**，**未新增、未删减 AC**；本版新增的 **E6 / E7 属端点**（不各设 AC），其证据面落在 **AC-06** 与结果页裁图的**人工可见性**上。**每条均为可机械判负**；**证据未留档即视为未通过**。**v1.3 亦未增减任何 AC：仍 13 条**——本版只**改写** **AC-01**（幂等判据改「键集合与内容不变」）、**AC-03**（点位口径钉定为 `done_pages/total_pages`，两点位 + ±1 页容差须写实际百分比）、**AC-08**（判负绑定 §3.12 键路径）、**AC-10**（适用面＝新增解析链路）四条**判据表述**，**未新增、未删减 AC**；本版新增的 **§7.1 验收夹具纪律**与 **§3.10–§3.13** 均为**口径 / 形状登记**，**不各设 AC**。**新增 AC 的动议须走 §0.4**（例：`has_more↔next_cursor` 一致性能否升格为独立 AC——本版按「已有 S-3 与 §3.10 承载，不单列」处置）。

### 7.1 验收夹具纪律（**v1.3 新增**｜由两起实测事故换来）

> **性质**：本节约束**验收 / 自测夹具本身**（不是被检产品）。**依据**：① **失控轮**——服务端给出「`has_more=true` 而 `next_cursor=null`」时，夹具的终止条件 `if not body["has_more"]: break` **永不成立** ⇒ 同一条 FAIL 打印 **54,254** 次、证据文件 2.8 MB、最终被 SIGTERM 杀掉，**那一轮结论全部作废**（`REPORT_1b-ii.md` §2.1）；② **假绿形态**——中途终止 / 漏挂子命令 / `$?` 被 `| tee` 吞掉时，汇总**可能少跑几条却仍报 `FAIL=0`**（`qa-recheck/p1b-neng/REPORT.md` §6.4、O-5）。

| # | 纪律（**硬约束**） | 判负形态 |
| --- | --- | --- |
| F-1 | **翻页循环必须有硬上界**（`ceil(total/limit)+2` 或常量上限 50），不得用 `while True` | 出现无上界循环 |
| F-2 | **夹具不得把「被测方的自洽」当作自己的终止条件**：游标推进须由**三条件**之一中止（`has_more` 为假 / `next_cursor` 为空 / 游标与上页重复），且**一条 FAIL 内收敛**（附两页原始报文） | 终止条件依赖服务端给出自洽信封 |
| F-3 | **重复 FAIL 折叠计数**：同一 `(断言名, 判据)` 打印 ≤3 次，其余只累加计数，**收尾必须出清单**（按命中次数降序）——**折叠 ≠ 静默** | 同一判据刷屏把其他证据挤出日志；或折叠后不再出现 |
| F-4 | **非信封 / 关键字段为空 ⇒ 显式 FAIL + 中止该子段**（不产级联 FAIL、不带脏值继续断言） | 一条前置异常把后续 N 条染成假 FAIL / 假 PASS |
| F-5 | **`finally` 清理**：停服务一律**精确 PID**（并做身份校验），删临时物**只删自己建的同名前缀目录**；**全程禁用 `pkill -f` / `killall` / 宽匹配 kill** | 残留服务占端口；或误删他人产物 |
| F-6 | **不写死端口**：动态探测空闲端口，开头断言无监听，硬跳过登记端口与保留段（5173 / 5174） | 与别人撞端口；或与既有验收判据端口对不上 |
| F-7 | **断言总数闸门**：收尾必须有「**实际运行的断言总数 == 预期常数**」一条断言（外加「跑到收尾」「子段齐全」「无未收敛护栏命中」三条） | 中途终止仍报 `FAIL=0`（**假绿**） |
| F-8 | **版本身份钉**：被检文件的 md5 **逐文件记录**（开工 / 收官两份）。**结论的适用范围随版本走**——若复检期内被检源码被并行改写，则**执行层结论可平移、接口层结论只对该 md5 版成立**，**不得反向盖章** | 用较新版的复检结果给较旧版的交付盖章 |
| F-9 | **辅助函数不得对调用点的类型做单方面假设**（如假定 `detail` 是 `str` 而调用点传 `list`） | 整轮脚本因 `TypeError` 异常终止 |
| F-10 | **断言「必须被执行」**：恒真判据（只在失败时调用的断言）不得充当「通过」证据——「通过」须由**总会运行**的收敛性断言或总数闸门承载 | 接口全对时该断言一次都没运行 |

---

## 8. 现状时点纪律
（**本文件范围的强制口径**）

1. **原文**：凡写「现状 / 事实 / 实测 / 当前 / 已核对」类段落，**① 内容必须来自磁盘实测或可复算的命令输出**；**② 必须标注核验时点与证据来源**（格式：`核验时点 YYYY-MM-DD HH:MM（Asia/Shanghai）；证据＝<命令或文件路径>`）；**③ 派单 / 聊天 / 转述与磁盘事实不一致时以磁盘事实为准**，并把差异登记（本文件 **§9** 或 **§10**）。
2. **适用范围（非穷举，示例即示例）**：§0.3 基线表、§3.3 的现状数字、§4.x 的「现状」列、§5.x 的实测代价、§6.1 的空闲证据、§7 AC 里写死的基线值（如 AC-07 的 **77**）。
3. **时点戳是证据的一部分**：**无时点戳的现状读数 = 无效读数**；复检时须**重测并刷新时点**，**不得**沿用旧时点。

6. **红线判据纪律：内容指纹，禁用库文件 md5（**v1.3 新增**｜Zang 已裁定口径）**——凡需证明「**数据未变**」的**现状读数**与**红线判据**，**一律使用内容口径**（例：`stamps` 的**列数 + 行数 + 三口径内容指纹**，或可复算 SQL 输出），**禁用数据库文件 md5**。
   **实测依据（本机）**：库处于 **WAL** 时，`yinpu.db` 的**文件** md5 会在**内容无任何变化**的情况下漂移——`254d3ff132d3a8d14dcf8590f45c7232`（1b-i 自测时点 12:29:26）→ `56cbf7afd124e86c6d9f810c0380c3eb`（文件 mtime **12:42:13**，**早于**该轮开工时点）；同刻 `stamps` 的**内容口径**（10 列 / 79 行 + 三口径指纹 `8a21e57d…` / `d7abe995…` / `22bdc0a7…`）**逐字节未变**。WAL 回拷 / 检查点会**重写文件而不改内容**。
   **判负形态**：① 以「库文件 md5 不等」为由判「数据被改」；② 要求复检者提交**库文件 md5** 作为通过判据；③ 用 `sqlite3` CLI + md5 在 WAL 库上取数（**会得到空输入的 md5 假结论**）。
   **同源纪律**：本条第 6 款在**平台规范 v1.28** 与 **`ctrl/PORTS.md` v1.11** 同步写入（跨文件一律适用）。

4. **不得跨文件外推**：本文件的实测结论**只对 feicui 有效**；平台侧现状（如平台规范 §9.1）**以平台规范为准且由平台侧按 §0.4 流程维护**。
5. **已知的转述 ↔ 磁盘差异（本版登记）**：平台规范 **§9.1 现状表**（v1.24 时点 2026-09-20 的读数：**65 行 / 影像缺失 42-65 / `text` 非空 0-65**）与**本文件核验时点 2026-09-20 10:38 的磁盘实测**（**79 行 / 影像缺失 0-79 / `text` 非空 2-79**）**已漂移**——**差异原因＝Kong 侧 F2 数据恢复与增量重跑**（`feicui/f2_report.json`，`generatedAt=2026-09-20T10:10:00+08:00`）。**处置**：平台侧 §9.1 的更正**属平台规范范围内的动作**（须按其 §0.4 流程：先快照 `docs/versions/` → 升版本 → 写 §0.5 变更记录 → **不动历史行**），**本文件只登记差异、不改平台规范**；登记项见 **§9-R9**。

---

## 9. 待 Kevin / Zang 裁定清单

> 口径：本表**只登记事实与选项**，**不带倾向性结论**；未裁定前**不得**据本表执行实现。**编号 R#**（本文件独立编号，与平台规范 §11.3 的 GB-# 不混用）。

| # | 事项 | 现状（**事实 + 时点 + 证据**） | 待裁选项（一句话可改） | 影响面 |
| --- | --- | --- | --- | --- |
| **R1** | **5164 是否加一条 dev 代理 `/feicui → 5195`** | 已定：feicui 前端**独立端口 5195 为主入口**。**实测**：`shu/web/vite.config.js` 内 `grep -n proxy` **零命中**（核验时点 2026-09-20 10:38；证据＝`grep`）——**该代理目前不存在**。**性质＝待确认项，不得写成已定**。**（v1.1 收口：Kevin 已拍板＝要（选项 ②）；落地时点＝feicui 前端骨架起来那一刻（目标现不存在，**本轮不落地**）；实现＝Vite `server.proxy`、**不落 SPA 路由**；**平台规范 §2.2 路由表仍 14 条、AC-88 / AC-89 扫描面不变**；**生产部署须在网关做同构改写**；属 **M1 冻结面之外的基础设施登记、不得当作功能变更**——完整口径见 **§6.4**。原句「性质＝待确认项，不得写成已定」**已被 v1.1 取代**。）** **v1.1 复核仍零命中**（核验时点 2026-09-20 11:29；证据＝`grep -n proxy shu/web/vite.config.js` → 零命中） | ① 不做（5195 独立入口为准）；② 做（须由 Kong 在 `shu/web/vite.config.js` 加 **dev 代理**）（**v1.2 收口**：**Kevin / Zang 已把 1c 口径定死**——`feicui/web` 侧 `base: '/feicui/'` + `server.hmr.clientPort: 5195`；`shu/web` 侧 `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、`changeOrigin: true`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 **14 条**、AC-88 / AC-89 扫描面不变；**生产须网关同构改写**；**四项验收判据原文见 §6.4 v1.2 块**（照录、一字未改）。**性质**＝**M1 冻结面之外的基础设施登记**。**实测**：核验时点 2026-09-20 12:01，两处 `vite.config.js` **均已含**该 proxy 键、`curl` 两条均 **200**（详见 §6.4）） | ⚠ **`shu/web/**` 属 M1 已封版冻结**：若选 ②，**必须先由 Zang/Kevin 明确解除该文件的冻结口径**（改它会作废另一角色的验收结论）；且代理只限 **dev**，不得进构建产物 |
| **R2** | **8501 上的 Streamlit 实例处置** | **实测观察（不改状态判定）**：`lsof -nP -iTCP -sTCP:LISTEN` → `Python 71267 *:8501`；`ps -o pid,ppid,pgid,lstart,command -p 71267` → **PID 71267 / PPID 1（已 reparent）/ PGID 71267**，`lstart = Fri Sep 18 09:51:16 2026`，命令＝`…/Python -m streamlit run app.py --server.port 8501 --server.headless false`；RSS **1546448 KB ≈ 1.47 GB**（核验时点 2026-09-20 10:45）。**（v1.1 收口）该实例已停**——**2026-09-20 10:57:50** 由 **Kong** 按 **Kevin 授权**以**进程组 `TERM`**（`kill -TERM -- -71267`）停止：**1 秒内释放**、**未用 `KILL`**、**无邻接误伤**（27 个无关 node/vite 进程全数存活、ctrl 面板 5555 仍 LISTEN + HTTP 200）；**证据**＝`feicui/ops/8501_stop_evidence.md` + `feicui/ops/8501_stop_before_after.txt`（md5 `cc07f93f30af4bf0af7bb91c8f12cf58`）。**v1.1 独立复核**（核验时点 2026-09-20 11:29）：`lsof -nP -iTCP:8501 -sTCP:LISTEN` → **无监听** ⇒ **8501 现空闲**（§0.3 已同步）。**原句「处置中，见 Kong 报告 / 本文件不写状态定论」已被 v1.1 取代**。**Jing 未 kill、未停、未重启、未占用**该进程 | 处置结论＝**已停止**（见左）；**退役时序**：feicui 主入口改由 5195 承担（§1.4），**`requirements.txt` / venv 中 `streamlit` 的清理仍属 Kong 动作**（§1.4 退役判据） | feicui 退役时序（§1.4）；**阻塞 §1.4「退役完成」判据的最后一环** |
| **R3** | **§4.4 的「必须换栈」阈值草案是否采纳** | §4.4 的 4 条触发条件与量级（**2 万影像 / 50 GB / 20 万行 / 2 写者 / 5 min 备份窗口**）系 **Jing 拟定草案**，**无既有出处**；锚点实测＝现状 **79 行 / 79 影像 / 3.4 MB / 576 KB 库 / 169 GB 可用 / 16 GB RAM** | ① 采纳；② 改数值（给值）；③ 不设阈值（到时再议） | 数据层演进路线、是否引入对象存储 / PostgreSQL 的时点 |
| **R4** | **worker 默认数** | §5.1 拟 **默认 8 / 上限 10**（物理核 10，实测）；§5.3 据此推 worker 池 RSS ≈ **6.5 GB**（单实例峰值 **0.81 GB** 实测）、内存预算 ≈ **8 GB** | ① 采纳 8；② 改值（给值）；③ 按书自动（小书单 worker / 大书多 worker） | 吞吐与内存占用；AC-04 的 N 取值。**（v1.3 收口）已裁＝4**：Zang 已定 **默认 worker 数＝4**（依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽），与 **AC-04 已钉的 `N=4` 对齐**；§5.1 / §5.3 已原位更正并留痕。**原「默认 8（草案，待裁）」不再有效** |
| **R5** | **`group` 归属** | §6.2 拟 `group = shu`（feicui 位于 `bistro/shu/` 下、属印索项目族；PORTS.md §2 既有分组无 `feicui`） | ① `shu`；② 新建独立分组 `feicui`（面板会多一个分组标题） | 面板分组显示、批量启停范围。**（v1.3 收口）已裁＝`shu`**：`ctrl/index.js` 实测两条 feicui 条目（`feicui-api` / `feicui-web`）**均用 `group: 'shu'`**（核验时点 2026-09-20 13:08；证据＝`ctrl/index.js` 第 49 / 58 行）⇒ **实现已按选项①落地**，本项收口 |
| **R6** | **`feicui` / `feicui-api` 何时写入 `index.js` `services` 表** | 现状：`index.js` `services` 表**无 feicui 条目**（实测 `grep -n feicui index.js` **零命中**，核验时点 2026-09-20 10:40）；且 **`feicui/web` 前端工程目录尚不存在**（**v1.1 收敛后的可复跑判据**：`ls -d /Users/kevin/bistro/shu/feicui/web` ⇒ **`No such file or directory`**；**注意**：`feicui/docs/` **已由本规范自身于 2026-09-20 10:40 建立**——即 §0.1「本文件」的落位目录，**故不得再以「无 `docs/`」作为工程目录不存在的证据**；原 v1.0 句「`ls feicui/docs` → No such file；`feicui/web` 同」**已被 v1.1 取代**，D-7）（**v1.2 原位更正 + 留痕（Neng 复核 OBS-2）**：本行原记「**`feicui/web` 前端工程目录尚不存在**」**已被 v1.2 取代**——**该目录已存在**：核验时点 **2026-09-20 12:00**，`ls -d /Users/kevin/bistro/shu/feicui/web` **命中**、`stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**。**R6 事项本身（何时写入 `index.js` `services` 表）仍未落地**（同一时点 `grep -n feicui ctrl/index.js` **零命中**）——但**判据的磁盘事实已变**：**不得再以「目录不存在」作为入表阻滞的理由**，§6.2 落地顺序纪律的**工程前提已满足**，入表时点由 Kong 执行 / Zang 确认） | ① 先落地工程再入表（**本规范 §6.2 的落地顺序纪律**）；② 先入表（**有风险**：`startAll` 会因 cwd 不存在失败，破坏「面板托管 N/N 全监听」判据） | 面板托管范围、批量启停可靠性。**（v1.3 收口）已落地**：核验时点 **2026-09-20 13:08**，`ctrl/index.js` 的 `services` 表**已含** `feicui-api`（sid、`port: 5196`、`cmd: './.venv/bin/python'`、`args: ['-m','app.main']`、`cwd: /Users/kevin/bistro/shu/feicui/server`、`env: {PORT:'5196'}`、`group:'shu'`）与 `feicui-web`（`port: 5195`、`cmd:'npm'`、`args:['run','dev']`、`cwd: /Users/kevin/bistro/shu/feicui/web`、`group:'shu'`、`directUrl:'http://localhost:5195/feicui/'`）两条——**落地顺序纪律的两种前提（目录存在 + 可 `npm run dev`）均已满足**；**原 v1.2 记「面板托管未落地（grep 零命中）」已被 v1.3 取代**（**该改写系 Kong 执行，Jing 未改 `ctrl/index.js` 一个字节**；`ctrl/index.js` 核验时点即 13:08、md5 `55b101fc643ad06d4bfcb61e56d7710d`）。**注意**：实际 sid 为 **`feicui-web`**（非 v1.2 §6.2 所记 `feicui`）、实际 `directUrl` 带 **`/feicui/`** 前缀（因前端 `base` 已为 `/feicui/`）⇒ §6.2 已按实况回填 |
| **R7** | **feicui 前端工程目录位置与形态** | **缺口：磁盘上不存在**（核验时点 2026-09-20 10:37，**v1.1 复核时点 2026-09-20 11:29**；证据＝`ls /Users/kevin/bistro/shu/feicui/` **无 `web/`**；**`docs/` 由本规范自身建立**（2026-09-20 10:40，§0.1），**不属缺口语义、不得计入本项证据**——原句「无 `web/`、无 `docs/`」**已被 v1.1 取代**，D-7）。§6.2 的 `cwd` 写作**计划路径** `/Users/kevin/bistro/shu/feicui/web`（**v1.2 原位更正 + 留痕（Neng 复核 OBS-2）**：本行原记「磁盘上不存在（核验时点 2026-09-20 10:37，v1.1 复核 11:29；证据＝`ls` 无 `web/`）」**已被 v1.2 取代**——**`feicui/web` 已存在**，核验时点 **2026-09-20 12:00**：`ls -d /Users/kevin/bistro/shu/feicui/web` **命中** + `stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**（另有 `package.json` / `vite.config.js` / `dist/` / `evidence/` 落盘）；§6.2 的 `cwd` 计划路径**即为实际路径**，**该行 cwd 已按 v1.2 回填**） | ① `feicui/web`（默认草案）；② 其他路径（给路径） | §6.2 登记值、§7 AC-13 的启动判据 |
| **R8** | **释文（`seal_name`）补齐路线** | **实测**：印面（篆书）直 OCR **不可用**（4 样本 3 个 `max_score=0.0`）；**边款 / 整页影像可用**（0.9989，41 框）；`ocr_text()` 的读取缺陷**已由 Kong 最小修复**；现状 `text` 非空 **2/79**（核验时点 2026-09-20 10:38）。证据＝`f2_report.json` → `3_ocr_feasibility` | ① 继续 OCR 路线（须加**分数阈值 + 去重**，Kong 侧）；② 改人工 / 半人工编目；③ 先解决 **§9.3 `seal_type` 章节映射**（无映射 ⇒ 必填项仍缺） | AC-08 必备项覆盖；平台侧汇入可否开正式包 |**（v1.3 状态）仍待裁**——1b-i/1b-ii **未推进释文路线**（无新证据）；**缺什么**：① OCR 路线的**分数阈值 + 去重**实测数据；② 人工 / 半人工编目的工作量口径；③ §9.3 #9 书简码签发（**归平台侧 M2**）与 `seal_name` 的先后关系。**v1.3 未改本项任何取值** |
| **R9** | **平台规范 §9.1 现状段落已与磁盘漂移，是否登记更正** | **漂移对照（双向时点）**：平台 §9.1（**其自记核验时点 2026-09-20，v1.24**）＝`stamps` **65 行** / 3 个 `pdf_name` 分别 **30/23/12** / `text` 非空 **0-65** / 影像缺失 **42-65**；**本文件磁盘实测（核验时点 2026-09-20 10:38）**＝**79 行** / **30/23/26** / `text` 非空 **2-79** / 影像缺失 **0-79**。**成因**＝Kong 侧 F2 恢复 + 增量重跑（`f2_report.json`：`2_image_recovery.copied=42 / still_missing=0`、`4_additive_rerun.rows_added=14`（页 7–8）、`5_selfcheck_before_after.rows 65 → 79`）**（v1.1 收口：平台规范已于 **v1.25** 按 §0.4 流程**原位更正 §9.1 三条读数**（快照 `docs/versions/yinsuo-web.spec.v1.24.md` → 升版本 → §0.5 + 表头两处同步 → 页脚同步），**故 R9 选项 ① 已执行完毕、本文件 §3.3 引用点无需改动，R9 事项收口**）** | ① 由 Jing 按平台规范 **§0.4** 流程登记更正（**先快照 `docs/versions/` → 升版本号 → 写 §0.5 变更记录 → 不动任何历史行**）；② 保持现状、只在平台侧 §0.7/§9.1 挂差异化登记 | 平台规范 §9.1 / §9.6「存量」行 / §0.6 证据行的**事实准确性**；**不影响**任何 AC 判据实质（AC-57 等不受影响） |
| **R10** | **边款影像的交付口径**（`REPORT_1b-i.md` §6 **G-2**） | **事实**：1b-i 的边款检测**照样做**（其结果参与 `exclude_mask`、影响释文块匹配），但**不落边款影像**（§4.1 D-4② 只定义印面交付影像 `faces/<book_key>/p####_i##.<ext>`）；旧 `output/<书名>/*_边款.webp` 属 Streamlit 路径、未动。平台侧 §9.2 有 `kind=EDGE` 的挂点，但**落地形态无规范** | ① 不入 `faces/`（保持 D-4② 现状）；② 入 `faces/` 并定命名；③ 入独立目录 `faces_edges/` | §4.1 D-4② / §4.2 命名规则 / §3.12 的 `assets[].kind` 取值面；**不阻断任何现有 AC** |
| **R11** | **影像 `sha256` / `bytes` / 宽高 的落库位置 + `stamps.id` 自增语义**（`REPORT_1b-i.md` §6 **G-6**） | **事实**：1b-i/1b-ii **只写** `stamps` + `job_pages` + `jobs`；影像 `sha256` 由 worker 回传、**只记在日志与自测证据里，未入表**；`images` / `seals` 侧表**未写**；`stamps.id` 的自增语义（是否可作跨轮稳定锚）未定 | ① 落到 `images` 侧表（沿用 F1 结构）；② 加列到 `stamps`；③ 另立 `job_images` 表 | §4.1 D-4① 的后续；**AC-09（`dedupe_key` 复算）** 与 AC-12 的证据面 |
| **R12** | **G-e：同区间重解析的行数 ≠ 库内行数（**待定性**）** | **观测（未定性）**：`tmp.pdf` 页 13–14 **库内 12 行 → 重解析 13 行**（`inserted=1 skipped=12`）；页 13–19 **库内 30 行 → 1b-i 首跑解析 31 行**。**反向证据现状**：**旧行零改写成立**（`skipped=12` 原样未动、AC-01 的「旧行不得被改写」面成立），但「**行数不变**」**不成立**；两种解释（**检测非确定性** vs **旧解析少一行**）**均未做实验判定** | **待定性**——**Zang 已另派质检任务定性**。**缺什么**：① 对同一页区间的**重复解析 N 次**的 idx 集合差分（判是否确定性）；② 对差异行（`inserted=1` 的那条）的**页/idx/bbox/影像复现性**取证；③ 旧行产出时的解析版本号与参数留痕 | §7 **AC-01** 的判据口径（**本版已按「键集合与内容不变」改写**）、§2.4 幂等语义 |
| **R13** | **换栈阈值与内存预算上限**（原 **R3** 的阈值部分） | §4.4 的 4 条触发条件（2 万影像 / 50 GB / 20 万行 / 2 写者 / 5 min 备份窗口）与 §5.3 的「worker 池 RSS 上限 ≈ 8 GB」**仍是 Jing 草案、无既有出处**；**v1.3 未改其数值**（仅因默认 worker 数改为 4，把**按 worker 数换算的池 RSS** 原位更正为 ≈ 3.3 GB，**8 GB 仍作宽松天花板保留**） | ① 采纳；② 改数值（给值）；③ 不设阈值 | 数据层演进路线、是否引入对象存储 / PostgreSQL |
| **R14** | **多 job 并行调度**（`REPORT_1b-i.md` §5-7 未做） | **实测**：池按 **FIFO 一次跑一个 job**（用满全部 worker）；§5.3 的上限口径是「同时跑的 job 数 ≤ worker 数」⇒ 取 **1 ≤ 4 合规**，但**不是最大化调度** | ① 维持 FIFO 单 job（当前）；② 允许多 job 并行（需定「每 job 的 worker 分配」与抢占规则） | 吞吐；§5.3 / AC-04 的解释面 |
| **R15** | **`jobs.state=PAUSED` 未实现** | **事实**：池不会主动暂停；`PAUSED` **仅在活跃 / 终态判定里被承认**（§2.1 表下注 G-4 的 `ACTIVE` 集合含它），**无实现路径**（`REPORT_1b-i.md` §5-6） | ① 保留为「口径承认、实现待定」；② 明确不实现（从 `ACTIVE` 集合移除，须同步 §2.1 表下注） | §2.2 状态机、§2.1 `ACTIVE` 集合 |
| **R16** | **AC-12 的 `N ∈ {0, 100, 1000}` 斜率实验未做** | **事实**：1b-i/1b-ii **遵守**影像外置（不写 BLOB）但**未做**该实验（`REPORT_1b-i.md` §5-4 / §4）。**不阻断**：AC-12 的三个子项**仍可机械复算**（§7 AC-12），只是**尚无留档证据** | ① 补做三档实验并留档；② 以 §4.1 D-4① 的「无 BLOB 列」子项 + 现库小规模读数替代 | AC-12 的通过判定（**证据未留档即视为未通过**，§7 用法） |
| **R17** | **平台规范 §9.3 ↔ §3.8 对 `sourceBook` / `sourcePageNo` 的必填性不一致（**报冲突、不自行改平台口径**）** | **实测（读平台规范原文）**：**§9.3** 把 `source_book` / `source_page_no` 列为**必填**（必填 11 项含第 7 / 8 行）；**§3.8** 的 `Seal` 字段表把 `sourceBook` / `sourcePageNo` 标为 **否（非必填）** ⇒ **同一文件内部必填性冲突**。feicui 侧**按 §9.3 执行**（§3.12 键路径已冻结、`missing_required` 含该两项） | **转平台侧按 §0.4 裁定**（① 按 §9.3 收紧 `Seal` 字段表；② 按 §3.8 放宽 §9.3。**Jing 不改平台规范一字**） | feicui 侧 `missing_required` 的取值面、AC-08 的判负面；**平台规范 §12 AC-57 判据实质不受影响** |

---

## 10. 变更记录

| 日期 | 版本 | 变更 | 变更人 |
| --- | --- | --- | --- |
| 2026-09-20 | **v1.0** | **建立 feicui 侧独立规范（只写文档，未动 `feicui/**` 任何 `.py` / 数据文件、未动 `shu/web/**`、未动平台规范）**：① **§1 目标形态**——Streamlit UI 退役 → **FastAPI 薄接口层 + 独立 Vue 前端 + 任务队列 / worker 池**，进程分离（计算与 UI 各自生死），并列 **4 条硬不变量**（依据＝Kevin 拍板方向 C + Zang 裁定「UI 框架不在热路径」）；② **§2 任务模型**——**一本书 = 一个 job**、job 内按页 chunk 并行、**页级断点游标**、**同书重跑幂等**（行级 `(pdf_name,page,idx)` + 影像 `sha256`）；③ **§3 API 契约草案**（E1 建 job / E2 查进度 / E3 分页取结果 / E4 触发导出 / E5 缺失清单）＋ **6 条语义纪律**，并与平台规范 **§9.3 必填 11 项 / §9.4 幂等键与 DPI 归一化前置 / §9.6 通道**对齐（**只引用，不动平台规范一字**）；④ **§4 数据层演进**——SQLite 保留 + **WAL** + **索引 `(pdf_name,page)`** + **批量事务**（替换现状**每页一次 connect/commit/close**，证据 `processor.py` 行 432/440/441）＋ 影像外置目录规则 ＋ **对象存储 / PostgreSQL 的四条换栈边界（草案，待裁定）**；⑤ **§5 并发与资源**——worker 数口径（**10 物理核实测**、默认 8 待裁定）、**OCR 由全局单例（`processor.py` 行 20–23）改为每 worker 一实例**（单实例实测 **init 1.8 s / 常驻 0.70 GB / 峰值 0.81 GB**）、单 job 并发上限 1、内存预算；⑥ **§6 端口与登记口径**——前端 **5195**、API **5196**（**实测空闲证据**：`lsof` 无监听 + `nc -z` CLOSED，核验时点 2026-09-20 10:38），`index.js` `services` **五要素对应**（sid / 端口 / 启动命令 / cwd / env + group `shu` + directUrl）与**落地顺序纪律**；⑦ **§7 验收判据 AC-01～AC-13**（**逐条可机械判负**，覆盖同书重跑幂等、断点续跑不重复、**并行与串行含 bbox 逐条一致**、进度真实、影像/释文缺失清单可查、必备 11 项、幂等键复算、批量事务、进程分离、影像外置、端口纪律）；⑧ **§8 现状时点纪律**（自带时点戳与证据来源；**派单转述与磁盘冲突以磁盘为准**）；⑨ **§9 待裁清单 R1–R9**（5164 `/feicui` 代理、8501 实例处置、§4.4 阈值、worker 数、group 归属、入 `services` 表时点、前端工程目录缺口、释文路线、平台规范 §9.1 漂移更正）；⑩ **§0.3 磁盘事实基线**（核验时点 **2026-09-20 10:38–10:45**，含 `stamps` **79 行 / 10 列**、3 个 `pdf_name` **30/23/26**、`text` 非空 **2/79**、影像缺失 **0/79**、`journal_mode=delete`、`stamps` 无索引、机器 **10 核 / 16 GB / 169 GB 可用**、**8501 被占**）。**同时**在 `ctrl/PORTS.md` 追加 feicui 登记行（§2 表 + §5 变更记录），**未重写任何历史行**。 | Jing |
| 2026-09-20 | **v1.1** | **按 §0.4 变更流程修 Neng 复检 7 项缺陷（D-1～D-7）+ 三项登记（本版只改文档，未动 `feicui/**` 任何代码 / 数据、未动 `shu/web/**`、未动平台规范历史行、未 kill / 停 / 重启任何进程）**：**(1) D-1｜分页信封（中）**——采「**扩展自平台 §3.1 信封**」口径（**理由：平台 §3.1 约束的是平台适配层方法 A13/A21/A24/A25，而 E3 是 feicui 内部端点；E3 取的是随 worker 推进而增长的页级顺序结果集，游标分页比页码分页稳定**），**逐项列出差异**：`limit` ↔ 平台 `pageSize`（同义不同名）、**`has_more` / `next_cursor` 为 feicui 侧游标分页新增**、`items` / `total` / `page` 与平台同义；**S-3 的判负形态绑到该 6 字段明确定义形态**（含 `has_more` / `next_cursor` 互斥一致性校验），**删去「与平台一致取向」的表述**（§3.1 E3 行 + 表下注 / §3.2 S-3）。**(2) D-2｜5196 登记口径互斥（中）**——§6.1 的 5196 单元格改为「**本文件与 `PORTS.md` v1.8 同轮新分配**（原表无 5196、非占用、非保留；登记行见 PORTS.md §2）」，**与同文件 §6.3 口径拉齐**（§0.1「以 PORTS.md 为准并当场修本文件」）。**(3) D-3｜AC-12 不可复算（低-中）**——改为**三个独立子项**：**① `PRAGMA table_info` 无 `BLOB`**（拆为独立子项）；**② 斜率式可复算**——影像数 `N ∈ {0,100,1000}` 三档各测 `du -k yinpu.db`，**斜率 < 1 KB/影像**判通过（等价式：`PRAGMA page_count × page_size` 增量 < 影像总字节 × 1%）；**③ `img_path` 相对路径**（抽样 ≥10 条）。**(4) D-4｜AC-11 不可定判（低）**——钉为**二值判定**「**worker 进程仍存活（`kill -0` 退出码 0）且 cursor 单调推进（≥5 s 两次采样）**」，删除「或按策略落为可续跑状态」（其能力由 AC-03 判定），并给出**可复算命令**。**(5) D-5｜自由变量钉值（低）**——AC-03 的 X 钉为 **X ∈ {25, 50}**（各至少一次）；AC-04 的 N 钉为 **`N=4`**，**依据 2026-09-20 实测**（阶段 0b：`w=1/2/4/8` ＝ 1.00× / 1.82× / 2.72× / 3.20×，**`w=4` 到顶、`w=8` 无收益**，来源 `feicui/spike-ocr/REPORT.md` + `results.json`）。**(6) D-7｜§9-R6/R7 证据句不可复跑（低）**——**删去「无 `docs/`」**，只保留「**无 `web/`**」并注明 **`feicui/docs/` 由本规范自身于 2026-09-20 10:40 建立**，同时给出复跑命令（`ls -d /Users/kevin/bistro/shu/feicui/web`）。**(7) 三项登记**——**① 8501 收口（R2）**：该孤儿实例已于 **2026-09-20 10:57:50** 由 **Kong 按 Kevin 授权**以**进程组 `TERM`** 停止（1 秒内释放、未用 `KILL`、零邻接误伤；证据 `feicui/ops/8501_stop_evidence.md` + `ops/8501_stop_before_after.txt`）；**v1.1 复核 8501 无监听**——已在 **§9-R2 / §1.4 / §0.3 端口现况行**原位更正并留痕（**Jing 本人始终未停任何进程**）；**② 5164 `/feicui` dev 代理（R1）**：**Kevin 已拍板＝要**，**落地时点＝feicui 前端骨架起来那一刻**（目标现不存在、本轮不落地），实现＝Vite `server.proxy`、**不落 SPA 路由**（**平台 §2.2 路由表仍 14 条、AC-88 / AC-89 扫描面不变**），**生产须在网关同构改写**，属 **M1 冻结面之外的基础设施登记、不得当作功能变更**——口径集中登记于**新增 §6.4**，§9-R1 同步收口；**③ 性能基线口径（新增 §5.4）**：单页现状 **8.668 s**（render 0.1587 / detect 0.0317 / **ocr 8.4777**）、关 doc 预处理 + `w=4`/`ct=2` 后 **2.481 s（3.49×）**、900 万页现状单核 **902.9 天** / 最优配置 **258.5 天**——**逐项标「实测 / 推断」，来源 `feicui/spike-ocr/REPORT.md` + `results.json`（Jing 未复跑，只读引用）**。**(8) 版本与流程留痕**——**§0.4 流程逐条执行**：改版**前**先快照 `feicui/docs/versions/feicui.spec.v1.0.md`（md5 `f2934cb0899953e00483c51a333da08c`，`cmp` 字节一致）→ 升版本 **v1.0 → v1.1** → 本行（**v1.0 行原文保留不改**）→ 同步受影响小节（§0.3 / §1.4 / §3.1 / §3.2 / §5.4 / §6.1 / §6.4 / §7 / §9）。**统计**：**AC 计数仍 13 条**（未增减；仅改写 AC-11 / AC-12、为 AC-03 / AC-04 钉值）；待裁项 **R3 / R4 / R5 / R8 仍待裁**，**R1 / R2 / R9 本轮收口**（R6 / R7 待工程落地）。**另**：平台规范同步升 **v1.26**（同轮，按平台 §0.4 流程：快照 `docs/versions/yinsuo-web.spec.v1.25.md` → §0.5 + 表头两处新增 v1.26 行 → 页脚横幅同步，**历史行零改动**）。 | Jing |
| 2026-09-20 | **v1.2** | **按 §0.4 变更流程一次性收口阶段 1a 暴露的全部规范缺口与登记项（本轮只写文档：本文件 + 平台规范 v1.27 + `ctrl/PORTS.md` v1.10，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未 kill / 停 / 重启任何进程、未占端口）**：**(1) 新增取图端点正式契约与编号 E6（前端 G-1）**——`GET /api/jobs/{job_id}/stamps/{page}/{idx}/image`（**必须带页段**：行级唯一锚是 `(pdf_name,page,idx)`，`idx` 单值在 job 内不唯一）；200＝影像字节（`Content-Type` 取文件实际类型、`Content-Length` 必填、**不包 JSON 信封**、可选 `x-feicui-img-path`）、404＝三类同码（job 不存在 / 记录不存在 / 文件不在盘上）、400＝参数非法、500＝读盘解码异常；**只读**（不得触发解析 / OCR / 写库）、**不得占位冒充**（无图 ⇒ 404）、**不得读 BLOB**；**临时路径的收口规则**＝废止前端的 `/stamps/{idx}/image`（2 段形态）、后端**不实现不兼容**（返 404 即可）、前端**一处常量**（`src/api/stampsImage.js`）收敛、收口证据＝结果页对「有图 / 无图」两种记录的可见性判据。落位 **§3.1 表（E6 行）+ 新增 §3.5**。**(2) 后端 8 条缺口 G-1～G-8 全部入账**——**新增 §3.4**（错误响应体形状：**409 冻结为** `{error:"ACTIVE_JOB_EXISTS", job_id, state, total_pages, created_at}`、**`job_id` 必填且为既有活跃 job**；400 / 404 / 422 / 500 冻结为**须含 `detail`**、**允许**额外字段（`error` / `missing`）、**多出字段不判负**；**明文规定 S-3 的字段封闭纪律不外推到错误体**，否则实现无法既带 `job_id` 又不「多出字段」）；**§3.1 表下注**（G-5 `total_pages` 派生顺序＝`page_range` 宽度 → 读 PDF 页数 → 否则 422，且读页数须用 worker 侧解释器子进程；G-6 **非 PDF 判定改以 `%PDF-` magic 为准**，不得只按扩展名——实测 PyMuPDF 会按扩展名把 `.txt` 当 1 页文档；**1a 未做、1b 补**）；**新增 §3.6**（G-8：**允许**非契约端点，限于 `/api/health` 与 `/api/meta/**` 只读，且不得被 AC 依赖；现状 `GET /api/health` / `GET /api/meta/migrations` 判定＝**合规、保留**）；**§4.1 D-2**（G-7：唯一约束**落地形态＝唯一索引** `uq_stamps_pdf_page_idx`，与「只许加法」相容，**严禁重建 `stamps`**，建前须实测重复组为 0）；**§2.1 表下注**（G-4：`job_id` 是**审计锚**不是游标容器——活跃 job ⇒ 一律 409（不看 `rerun`）、终态可再入队得**新 job_id**、**不得复用 / 重置旧 job 的页游标**）。**(3) 前端 5 条缺口全部入账**——G-1＝**新 §3.5**；G-2＝**E7**（新增 `GET /api/jobs`，E3 同款 6 字段信封，归属 1b；落地前前端按「后端尚未提供 + localStorage 本地记录分栏」过渡，**该现状不得作为验收依据**）落位 **§3.1（E7 行）+ 新增 §3.8**；G-3＝**§3.4**；G-4＝**§3.6**（`/api/health` **允许后端提供，但前端不得据其为契约或验收依据**，连通性仍走 dev 探针并容忍 404）；G-5＝**新增 §3.7**（**端点未实现＝404**；`404`/`405`/`501` 三码宽容**仅属前端处理、非规范口径**；**不得**用 200 + 空 items 冒充）；**前端附注**＝**新增 §3.9**（Vite dev 代理的 `503 {error:"backend_unreachable"}` **不属 API 错误码族**；「后端不可达」信号**定义为 dev / 前端侧**口径，探针 `GET /__feicui/backend-probe` 与代理 503 **必须同源**，二者均不属后端契约）。**(4) 登记项 R-1 按 §0.4 收口为正式口径**——§6.2 **启动命令原位更正**为 `cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python -m app.main`（等价 `uvicorn app.main:app`；host / port 不变）、**cwd 更正为 `feicui/server`**、**前端 cwd 由「计划路径」改为已建立**（birth 2026-09-20 11:35:25）；**新增 §6.5 解释器矩阵**（接口层＝`server/.venv/bin/python`、**3 个直接依赖 / freeze 13 行（实测 13）**；worker 与 Streamlit＝`feicui/venv`；E1 派生 `total_pages` 走 worker 侧解释器子进程；**硬约束：不得把新依赖装进 `feicui/venv`、不得升降级其中任何包**；`server/.venv` 重建命令与 13 行实测）。**(5) Neng 复核观察的入账**——**OBS-1**：**AC-11 的「判负形态」列原位等义替换为取反式**（worker 未存活 **或** cursor 未单调推进 ⇒ FAIL；判据实质**一字未改**）并留痕；**OBS-2**：**§9-R6 / R7 的「`feicui/web` 不存在」作废**（目录已存在、birth 2026-09-20 11:35:25；R6 事项仍为「入 `services` 表未落地」，但**不得再以目录不存在为由**）；**OBS-3**＝快照纪律，落位 **`ctrl/PORTS.md` v1.10 制度 (e)**；**OBS-4** 标注类，无需动作。**(6) 1c 代理口径按 Zang 原文照录入 §6.4**（`feicui/web` `base:'/feicui/'` + `server.hmr.clientPort:5195`；`shu/web` `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、`changeOrigin:true`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 14 条、AC-88 / AC-89 扫描面不变；**生产须网关同构改写**；**四项验收判据**），**原文一字未改**；**并附实测**（核验时点 2026-09-20 12:00–12:01：两处 `vite.config.js` 均已含该键、`5195/feicui/` ⇒ **200**、`localhost:5164/feicui/` ⇒ **200**；`check:pricing` / `smoke` / `build` **由 Kong / Neng 执行，Jing 未复跑**）；**落地状态句一律写作「已定、落地中（由 Kong 执行）」并自带时点戳**。**(7) §0.3 两条现状读数按磁盘实测原位更正**——**5195 现已被占用**（`node` PID 1329，`127.0.0.1:5195 LISTEN`；原记「空闲」被取代）、**`shu/web` 的 `/feicui` 代理已落地**（4 处 `proxy` 命中；原记「零命中」被取代）。**(8) 平台侧连带**：`shu/docs/yinsuo-web.spec.md` 升 **v1.27**（B4 v1.27 注 + §1.7 表下 v1.27 注 + §0.5 v1.27 行 + 表头两处 + 页脚横幅；**§12 AC-01～AC-90 判据一字未改、AC 计数仍 90 条、§2.2 路由表仍 14 条**）。**统计与自查**：**AC 计数仍 13 条**（只改写 AC-07 / AC-11 表述，未增减）；**未动** `feicui/**` 任何代码 / 数据、`shu/web/**`、`shu/mockups/**`、`ctrl/index.js`；**未 kill / 停 / 重启任何进程、未占端口**；**历史行（表头「版本」字段的 v1.0 / v1.1 叙述、§10 的 v1.0 / v1.1 行）逐字保留、只增不改**（版本字段以**前置** v1.2 条的方式同步，v1.1 原文完整保留）。 | Jing |
| 2026-09-20 | **v1.3** | **按 §0.4 流程一次性收口阶段 1b-i + 1b-ii 交回的全部规范缺口与 Zang 已裁定口径（本版只写文档：本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未启停任何服务、未占端口）**：**(1) E7 定案（Zang 口径 1 / 6 + 1b-ii G-a ～ G-d）**——§3.1 E7 行入参改写为 `?state=&page=&limit=&cursor=`，**`page` 与 `cursor` 互斥（同给 ⇒ `400 BAD_PARAM`）**、`page` 1-based 且**越末页返空 `items` + `has_more=false`（绝不回吐第一页）**；**新增 §3.10**：`limit` **默认 50 / 上限 500 / 越界或非法 ⇒ 400**、`total` ＝该 `state` 范围全量、**`has_more == (next_cursor is not None)` 恒成立**、**排序键 `ORDER BY created_at, job_id`**（实测 4 个 job 的 `created_at` 同秒 ⇒ 只按 `created_at` 会重叠 / 遗漏）、**游标 URL-safe base64**（`created_at` 含 `+` / `:` 直接进 query 会被解码成空格 ⇒ 第二页恒空），`items[]` **冻结 9 字段**（原「形状草案」表述作废），并**核过平台规范 §9 与 §3.8**（job 是 feicui 内部实体、平台无对应实体 ⇒ **不构成冲突**，核不上的项＝无）。**(2) 红线判据纪律（Zang 口径 2）**——**新增 §8 第 6 条**：凡「数据未变」类现状读数与红线判据**一律用内容指纹（列数 + 行数 + 三口径指纹 / 可复算 SQL），禁用数据库文件 md5**（依据：WAL 下 `yinpu.db` **文件** md5 在内容无变化时漂移 `254d3ff1…` → `56cbf7af…`，mtime 12:42:13，而同刻 `stamps` 三口径指纹逐字节未变）；**同源纪律同步写入平台规范 v1.28 与 `PORTS.md` v1.11**。**(3) AC-03 点位定义钉定（Zang 口径 3）**——**以 `done_pages / total_pages` 为唯一定义**（**不采用**「连续已提交前缀」口径）、**`{25%, 50%}` 两点各至少一次**、**允许 ±1 页容差但证据须写明实际百分比**（实测两口径不同：42.9% / 57.1% vs 28.6%）。**(4) worker 数口径对齐（Zang 口径 4）**——**§5.1 草案「默认 8」原位更正为 4**（与 AC-04 已钉 `N=4` 一致；依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽），**§5.3 的「全局 job 并发上限＝worker 数（默认 8）」与「池 RSS ≈ 6.5 GB（8 × 0.81）」同步原位更正**并留痕，**§9-R4 收口**。**(5) 池的进程形态定案（Zang 口径 5）**——**§1.3 表新增「池管理器 `feicui-pool`」行**：**独立常驻进程、无端口、非接口层子进程**；**池管理器用 `server/.venv`、worker 用 `feicui/venv`**；**接口层不含业务真值** ⇒ 这是 **AC-11 的形态依据**（1b-i 自测 ⑤ 已用 SIGKILL 5196 反证）；**§6.2 表下 v1.3 注**登记「池不进 `services` 表」与落地实况。**(6) E6 错误码定案（Zang 口径 9）**——**§3.5 表下 v1.3 块**：越界 / 不可得均 **404** 但**原因码分三类**（`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`）、**`img_path` 超出 `FEICUI_ROOT` 或为绝对路径 ⇒ `IMAGE_UNAVAILABLE`**、**无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`**（**不得**以 `application/octet-stream` 冒充）；§3.1 E6 行同步。**(7) E4 请求语义定案（Zang 口径 8）**——**新增 §3.11**：`batch_id` 非空 ⇒ 400（批次号由 `export.py` 派生、不臆造）、`dry_run=true` ⇒ 400（`export.py` 无该模式、不假装跑过）、`book_code` 仅作与 `config/book_codes.json` 的一致性校验、`counts` 三键映射登记为 `feicuiDecidable` 的 `formal` / `draftStaged` / `rejectedRequiredMissing`、`selfcheck_ref` **存在则给路径否则 `null`**（**`export.py` 的 export 子命令本身不产生 selfcheck，生成者是 `selfcheck_export.py`** ⇒ `null` 是正常态）。**(8) E3 records 形状与 AC-08 键路径冻结（Zang 口径 10）**——**新增 §3.12**：顶层平台字段名 + `assets[]` + `feicui` 子对象 + 顶层 `missing_required[]`；11 项必填逐项键路径表（`assets[].sha256` / `assets[].width` / `assets[].height` / `assets[].colorMode` / `assets[].batchId` 等）；**`missing_required` 用 feicui 语义名（snake_case）**、记录内用平台字段名（camelCase）——**两套命名的映射表即 §3.12**；**AC-08 判负改绑键路径**。**(9) `limit` 默认 / 上限与信封恒等式（Zang 口径 11）**——并入 **§3.10**。**(10) 响应头纪律（Zang 口径 7）**——**新增 §3.13**：`x-feicui-scope` 等含**非 ASCII 书名**时**必须百分号编码**（头值须 latin-1 可编码），并给出**4 条可机械判负的判据**（Latin-1 可编码 / 原始非 ASCII 计数须为 0 / `unquote` 后与 DB 字面逐字节相等 / 头不进 JSON 体）；依据＝原写法对中国书名**已真实发生 500**。**(11) G-e 待定性（Zang 口径 12）**——**§2.4 表下注 + §9-R12**：「同区间重解析行数 ≠ 库内行数」以**「待定性」**入账（写明观测值与**缺什么**：重复解析 N 次的 idx 差分 / 差异行的复现性取证 / 旧解析版本留痕；**Zang 已另派质检定性**）；**AC-01 幂等判据改写为「键集合与内容不变」，「行数不变」不再作判据**，并明确「**新键允许新增行**」。**(12) 1b-i §6 G-1 ～ G-9 逐条判定并入账**——**本轮已裁**：G-1（**AC-10 适用面＝新增解析链路**，`processor.py` 旧形态属 §1.4 退役边界、不单独判负）、G-3（worker＝4）、G-4（池＝独立进程）、G-5（**队列形态＝库即队列**——`jobs` + `job_pages` 即持久队列，不引入额外中间件）、G-7（**AC-11 的 cursor 读数来源＝库内 `count(distinct chunk_index) WHERE state='DONE'` 或 E2 的 `cursor.chunk_hi`，不新增 E2 字段**）、G-8（**`FEICUI_DOC_PREPROCESS` 默认 1，改默认须先补样本级精度验收**——实测「关 doc 预处理改文本」**是样本相关的**：页 20–21 为 1/8、页 63–64 为 0/10）、G-9（**`cpu_threads=2`**，§5.2 新行）；**仍待裁**：G-2（边款影像交付口径 ⇒ **R10**）、G-6（影像 `sha256` / 度量落库位置 + `stamps.id` 语义 ⇒ **R11**）。**(13) 新增 §7.1 验收夹具纪律**（F-1 ～ F-10：硬上界 / **夹具不得把被测方的自洽当终止条件** / 重复 FAIL 折叠计数 / 非信封即中止 / `finally` 精确 PID 清理 / 动态端口 / **断言总数闸门** / **版本身份钉** / 辅助函数不得假设调用点类型 / 恒真判据不得充当通过证据）——依据两起实测事故（**54,347 行 / 54,254 条重复 FAIL 的失控轮**；**「中途终止仍报 `FAIL=0`」的假绿形态**）。**(14) §6.2 按磁盘实测原位更正**——**sid 由 `feicui` 更正为 `feicui-web`**、**`directUrl` 更正为带 `/feicui/` 前缀的实际值**；**登记「面板托管已落地」**（核验时点 2026-09-20 13:08，`ctrl/index.js` 已含 `feicui-api` / `feicui-web` 两条），**§9-R6 收口**、**§9-R5 收口（实际 `group` ＝ `shu`）**；§0.3 端口现况行追加 v1.3 读数（**5195 / 5196 / 8501 均无监听**）。**(15) 平台侧报冲突一项**——**§9-R17**：平台规范 **§9.3** 把 `sourceBook` / `sourcePageNo` 标为**必填**，而 **§3.8** 的 `Seal` 字段表标为**非必填** ⇒ **平台规范内部必填性不一致**；feicui 侧**按 §9.3 执行**、**冲突转平台侧按 §0.4 裁定**（**Jing 不改平台规范一字**）。**(16) §9 待裁清单新增 R10 ～ R17**（边款影像 / 影像度量落库位置 / **G-e 待定性** / 换栈阈值与内存预算 / 多 job 并行调度 / `PAUSED` 未实现 / AC-12 斜率实验未做 / §9.3↔§3.8 冲突），**R8 维持待裁并补「仍缺什么」**。**AC 计数仍 13 条**（只改写 AC-01 / AC-03 / AC-08 / AC-10 的判据表述）；**被取代的原句一律就地留痕「已被 v1.3 取代」**。 | Jing |
