# feicui 执行层（阶段 1b-i）交付报告（Kong）

| 项 | 值 |
| --- | --- |
| 时点 | 2026-09-20 12:26–12:29（自测终态 12:29:26）／**回填 13:1x**（Asia/Shanghai） |
| 规范 | `../docs/feicui.spec.md` **v1.2**（md5 `6dbe0b3c915d7f8ed43576a00122dcf1`，521 行） |
| 交付目录 | `/Users/kevin/bistro/shu/feicui/server/**`（**新增** worker 模块 / 池 / 自测；**未改** `processor.py` / `export.py` / `app.py`；**未写** `feicui/web/**`） |
| 本单范围 | **执行层**：常驻 4-worker 池 + 页级 chunk 并行 + 页游标落库推进 + 断点续跑 + 行/影像幂等 |
| 不在本单 | E3 / E4 / E7 读接口（1b-ii）、前端联调、`ctrl/index.js` 入表 |
| 正式库 | `yinpu.db` **md5 前后一致**＝`254d3ff132d3a8d14dcf8590f45c7232`（size 577536、mtime 10:08:36 未变；`81_prod_db_md5_after.txt`）；`stamps` 三口径指纹亦未变 |
| 自测 | `server/selftest/selftest_1b_i.sh` ⇒ **`PASS=52  FAIL=0  结论：ALL PASS`**（汇总时点 **2026-09-20 12:29:26**，`evidence/1b_i/90_summary.txt`） |
| 终态回填 | **2026-09-20 13:1x 由本单（Kong 收尾轮）按 12:26–12:29 那轮实测数据回填 §1 / §3 / §5-10 / §6 裁定状态；未重跑任何测试、未改任何代码/数据**（`REPORT_1b-i.md` 改前 md5 `62f11aec…`） |

## 0. 本文件写法

- **逐节回写**：每完成一节立即写入本文件（不攒到最后），并在每节末尾给出 `wc -l` 自证。
- **性能类读数**：一律标注「**同机可能有并发任务、非受控基线**」，**不作为验收依据**（受控基线＝`spike-ocr/REPORT.md`）。

## 1. 落盘文件与 md5

实测时点 2026-09-20 12:29（`wc -l` + `md5`，本机实测）：

| 文件（`feicui/server/`） | 行数 | md5 |
| --- | --- | --- |
| `app/pool.py`（**新增**：池 supervisor / 唯一写者） | 676 | `1d11c946b9c8ccbe142e3fa14f83cb23` |
| `worker/feicui_worker.py`（**新增**：worker 子进程；**绝不碰 DB**） | 330 | `5cd0cf5d6fa133d4a3b6cceb5bfe5fb7` |
| `selftest/selftest_1b_i.sh`（**新增**：五条自测的编排） | 421 | `9d792ef7f677f2ce2c691dc8d158666c` |
| `selftest/verify_1b_i.py`（**新增**：独立复算工具 `recompute` / `e2check` / `counts`） | 306 | `9156e38c3247fa5b9ef2521a84f1a8ad` |
| `selftest/check_1b_i_docpreprocess.sh`（**新增**：doc 预处理开关检查） | 106 | `4e3f96bc62a624cc4e73b5a0a5b546c1` |
| `README.md`（**追加**：启动/解释器矩阵/开关登记） | 283 | `f274d84f1dcac10e057501834e6a30d2` |
| `REPORT_1b-i.md`（本文件；**回填前** md5） | 121 | `62f11aec62ea9169b284cfeb0a3e8535` |

**未触碰（改前/改后 md5 逐字节相同，`05_untouched_files_before.txt` vs `82_untouched_files_after.txt`）**：

| 文件 | md5（前后一致） |
| --- | --- |
| `feicui/processor.py` | `31ec6cdb907ac60b63e814d7b6122c24` |
| `feicui/export.py` | `a1ca4064cb4b41319dab5809fd57db54` |
| `feicui/app.py` | `1d7cc46348e85cdc6470b8fef7f343a7` |

**正式库**：`yinpu.db` md5 `254d3ff132d3a8d14dcf8590f45c7232`（size 577536 / mtime 10:08:36，改后复验时点 12:29:26 一致）；库内 `stamps` 10 列 / 79 行 / 三口径指纹见 `REPORT_1b-ii.md` §6（同一时点前后逐字节相等）。

## 2. 架构：进程与写者口径

### 2.1 三个进程、两种解释器（§1.3 进程分离 / §6.5 解释器矩阵）

```
  feicui-api（5196，注册端口）    薄接口层：只管「入队 / 查询」；**无进程内业务状态**（1a 已定）
      │ E1：一个事务写 jobs(QUEUED) + job_pages(PENDING)
      ▼
  feicui-pool（**无端口**，常驻 daemon）   执行层 supervisor＝**唯一写者**
      ├── worker#0..3（**子进程**，feicui/venv/bin/python）
      │     渲染 / 检测 / 边款检测 / 释文块匹配 / OCR / 写 .webp —— **绝不碰 DB**
      └── 主循环：claim chunk → 派活 → 收结果 → **单事务 commit chunk**
      ▼
  yinpu.db(WAL) + output/faces/<book_key>/p####_i##.webp
```

* **池不在接口层的进程树里**（自测 ⑤ 用 SIGKILL 5196 反证）：接口层死掉后池与 worker 照跑、游标照推进。
* 池与 worker 的作用域锁：`flock(<state>.lock)` ⇒ 同库同刻只有一个池实例（§4.3 单写者）。
* worker 与池是**父子进程**（同一进程组），故 AC-03 的「SIGKILL 全部 worker」＝按状态文件里的**精确 PID**
  逐个 `kill -9`（自测脚本如此做，**不含任何宽匹配 kill**）。

### 2.2 页级 chunk 并行与游标推进

| 环节 | 实现 | 规范锚点 |
| --- | --- | --- |
| chunk 认领 | `claim_next_chunk`：`SELECT MIN(chunk_index) WHERE state='PENDING'` + **CAS** `UPDATE … WHERE state='PENDING'` | §2.1（chunk＝并行单位与断点单位） |
| 派活 | 一个空闲 worker 领一个 chunk；worker 内**逐页串行**（单 job 页内并发上限 = 1） | §5.3 |
| 收结果 | 每页一行 JSON（含 `idx/text/bbox/img_path/img_sha256`）；chunk 页全到齐 ⇒ 提交 | §4.3 |
| 提交 | `commit_chunk` **单事务**：`stamps` 行（幂等）+ `job_pages`→`DONE/FAILED` + 5 个页级计数 + `jobs.cursor_chunk_*` | §4.3 / §2.3 |
| 终态 | 全部页到终态 ⇒ 无 FAILED 记 `DONE`，否则 `FAILED_PARTIAL`（绝不假完成） | §2.2 / S-2 |

### 2.3 断点续跑

游标**只在库里**（`job_pages`）。重启池后第一件事是 `claim_job`：把该 job 残留的 `RUNNING` 页
**退回 `PENDING`**、把 `jobs.state` 置回 `RUNNING`，**已 `DONE` 的页原样不动** ⇒ 从断点继续。
worker 在飞行中崩掉时同理（`requeue_pages`，不记 FAILED）——只有反复崩（>4 次）才落 `FAILED`。

### 2.4 幂等

* 行：`(pdf_name,page,idx)` 命中 ⇒ 默认 **跳过、绝不改写旧行**（AC-01 的判负形态就是「旧行被改写」）；
  另留 `FEICUI_ON_CONFLICT=update`（内容有别才改、计 `updated`）作显式逃生门。
* 影像：路径只由 `(book_key,page,idx)` 决定 ⇒ 重跑同路径；写前比 `sha256`，一致则**不重写**；
  写盘一律「临时文件 + `fsync` + `os.replace`」原子替换 ⇒ AC-02 的「文件数不变 + sha256 不变」成立。

### 2.5 与 `processor.py` 的关系（§1.2 I-1）

worker 的**像素级处理全部调用 `processor.py` 既有函数**（`render_page` / `detect_stamp_regions` /
`detect_edge_inscriptions` / `match_shishi_blocks` / `calc_text_density` / `AREA_SCALE`），
`processor.py` **一行未改**（md5 前后一致，见 §1）。只重写两处**编排**：
① 影像命名（改为规范 §4.1 D-4② 的稳定命名，`process_page` 的旧命名依赖 OCR 文本、同名重跑会换路径）；
② OCR 调用（自建**进程内单例**，§5.2 要求「每 worker 一实例」；并带 `cpu_threads<=2` 与 doc 预处理开关）。
释文抽取逻辑与 `processor.ocr_text` 逐行同构（含 PaddleOCR 3.x `.json["res"]["rec_texts"]` 兜底）。

## 3. 五条自测：真实命令与输出

编排脚本：`cd /Users/kevin/bistro/shu/feicui/server && bash selftest/selftest_1b_i.sh`（全程**非登记端口 5301–5305**、**空库副本**、`FC` 只读正式库；收尾 `80_port_after.txt` 五端口 0 监听）。
池一律以 `"$PY" -m app.pool --workers <N> [--drain]` 拉起（`selftest_1b_i.sh` 行 97–108），`PY=/Users/kevin/bistro/shu/feicui/server/.venv/bin/python`；worker 用 `feicui/venv/bin/python`。
E2 读数经 HTTP，**独立复算**用 `./.venv/bin/python selftest/verify_1b_i.py e2check <副本库> <job_id> <e2.json>`（`recompute` / `counts` 同族）。
**性能类读数一律标注「同机可能有并发任务、非受控基线」，不作判据**（受控基线＝`spike-ocr/REPORT.md`）。

### ① 推进（池 `--drain` 跑满一个 job：`tmp.pdf` 页 13–19 / chunk 2 / w=4）

命令（编排内等价形态）：

```bash
FEICUI_DB=<…>/copy_A_main.db FEICUI_FACES_DIR=<…>/faces/t1 FEICUI_WORKERS=4 \
  ./.venv/bin/python -m app.pool --workers 4 --drain
./.venv/bin/python selftest/verify_1b_i.py e2check <…>/copy_A_main.db <job_id> evidence/1b_i/33_e2_job1.json
./.venv/bin/python selftest/verify_1b_i.py counts  <…>/copy_A_main.db tmp.pdf 13 19
```

输出摘要（`33_e2_job1.json` / `35_e2check_job1.txt` / `36_counts_after_run.txt`）：

* E2：`state=DONE`、`total_pages=done_pages=7`、`failed_pages=[]`、`cursor={chunk_lo:null, chunk_hi:3}`、
  `counters={detected:31, inserted:31, updated:0, skipped:0, ocr_empty:1}`；
* 独立复算 `E2CHECK = MATCH`（`state/total_pages/done_pages/failed_pages/cursor/counters` **6/6 行全 MATCH**）；
* 行级唯一性：`scope_rows=31 == scope_distinct_keys=31`、`table_rows=110 == table_distinct_keys=110`、`dup_groups=[]`；
* 耗时：`started_at 12:27:00 → finished_at 12:27:03`（≈3 s，w=4；**同机有并发任务、非受控基线**）。

### ② 断点续跑（中途 SIGKILL 全部 worker ＋ 池 → 重启续跑）

命令（`selftest_1b_i.sh` 段③；**无任何宽匹配 kill**）：

```bash
kill -9 <池 58158> <worker 58165 58166 58167 58168>     # 精确 PID（64_ps_before_kill.txt）
kill -0 <各 PID>                                        # 65_kill_verify.txt：每个 -> 1（确已死）
<重启>.venv/bin/python -m app.pool --workers 4 --drain   # 67_resume_log.txt
```

输出摘要：

* **崩溃后库内状态**（`66_after_kill_db.txt`）：`job_pages` 状态分布 `[('DONE',3), ('RUNNING',4)]`、`jobs.state=RUNNING`、
  `stamps 行数=17`、chunk 级 `[(0,'DONE,DONE'), (1,'RUNNING,RUNNING'), (2,'RUNNING,RUNNING'), (3,'DONE')]`
  ⇒ **提交点＝chunk 边界，库里没有「半页」**；
* **续跑入口**（`67_resume_log.txt`）：`残留 RUNNING 页退回 PENDING=4（断点续跑入口）` → 收尾 `DONE（total=7 done=7 failed=0）`；
* **终态**（`68_e2_resume.json` / `69_e2check_resume.txt`）：`counters={detected:42, inserted:42, updated:0, skipped:0, ocr_empty:15}`、`E2CHECK = MATCH`；
* **与串行臂逐字段 diff**（`6C_diff_serial_vs_resume.txt`）：`DIFFCSV = IDENTICAL（42 行数据逐字节相同）`；
* **断点前已提交行零改写**（`6E_subset_killrows.txt`）：`断点行数=17 终态行数=42 未原样保留=0` ⇒ `SUBSET = IDENTICAL`；
* **kill 点位**：库内**已提交 3/7 页（42.9%）**，其中**连续已提交前缀 2/7（28.6%）**（页 33 的 chunk 在 4 worker 下并行先完成）；
  在飞 4 页为 `RUNNING`（续跑时退回 `PENDING`，**不记 FAILED**）⇒ 见 §5-10（**50% 点位未覆盖**，需规范侧裁定）。

### ③ 幂等（同书重跑：同 `pdf_path` + 同 `page_range` 再跑一次）

命令：同 ① 再跑一次（得**新 job_id**，符合 §2.1 表下注 G-4「终态可再入队得新 job_id」）。

输出摘要（`44_e1_job2_rerun.json` / `45_e2_job2.json` / `46_e2check_job2.txt` / `47_rowsig_after_rerun.txt` / `49_diff_before_after_rerun.txt` / `4A_imgman_after_rerun.txt` / `4B_unique_after_rerun.txt`）：

* 第二次 `counters={detected:31, inserted:0, updated:0, skipped:31, ocr_empty:1}` ⇒ **`inserted=0`、31 条全部 `skipped`（旧行一行未改写）**；
* `49_diff_before_after_rerun.txt`：`DIFFCSV = IDENTICAL（31 行数据逐字节相同）`（`42_rows_before_rerun.csv` vs `48_rows_after_rerun.csv`）；
* 行集指纹：`41_rowsig_before_rerun.txt` 与 `47_rowsig_after_rerun.txt` 同为 `rows=31`、sha256 `e366da146eb912426b97fd071ac125cc491aa7d3d487d5ea1976e8d1f5b61c54`；
* **影像级**：`43_imgman_before_rerun.txt` vs `4A_imgman_after_rerun.txt` 影像清单（路径 + `sha256` + 字节数）**完全一致** ⇒ ✅ AC-02；
* 表级唯一性：`110/110` 唯一、无重复组（`4B`）。

### ④ 并行 == 串行（含 bbox）

命令：同一页区间 **`tmp.pdf` 页 [27,33]** 在两个**空库副本**上分别 `--workers 1` 与 `--workers 4` 跑完。

输出摘要（`51/53` 串行臂、`57/59` 并行臂、`5C` diff）：

| 臂 | counts | rowsig（行集指纹） |
| --- | --- | --- |
| 串行 `--workers 1` | `51_serial_counts.txt`：`42/42` 唯一、无重复组 | `53_serial_rowsig.txt`：`rows=42` sha256 `75a61a4f344e71fd49f5cf7c54d11cceb5adbecc6b7eaaa24968bfab4fe83c9a` |
| 并行 `--workers 4` | `57_parallel_counts.txt`：`42/42` 唯一、无重复组 | `59_parallel_rowsig.txt`：`rows=42` sha256 **同上（逐字符相同）** |

* `5C_diff_serial_vs_parallel.txt`：`DIFFCSV = IDENTICAL（42 行数据逐字节相同）`——导出列为 `(pdf_name,page,idx,text,x1,y1,x2,y2)`（**含 bbox**）并按序比对 ⇒ ✅ AC-04；
* E2：`5B_e2_parallel.json` `counters={detected:42, inserted:42, updated:0, skipped:0, ocr_empty:15}`；串行臂见 `55_e2_serial.json`；
* 耗时：并行 12:27:50 → 12:28:02（≈12 s）——**同机有并发任务、非受控基线**。

### ⑤ 进程分离（kill 接口层，池与 worker 照跑）

命令（`selftest_1b_i.sh` 段⑤）：建一个 51 页 job（`70_e1_sep.json`）→ 接口层进程 `kill -9`（精确 PID）→ 观察 worker。

输出摘要：

* `71_after_api_kill.txt`：4 个 worker `kill -0 -> 0`（**0=存活**）、池进程仍在（接口层死后执行层不受影响）；
* `72_cursor_advance.txt`：`采样1 12:28:42 已完成 chunk=2` → `采样2 12:28:48（+6 s）已完成 chunk=4` ⇒ **游标严格推进** ⇒ ✅ AC-11（二值判定：worker 存活 **且** cursor 单调推进）；
* `73_e2_after_restart.json` / `75_e2check_sep.txt`：接口层重启后 E2（`total=done=51`、`cursor.chunk_hi=25`、`counters={detected:302, inserted:302, updated:0, skipped:0, ocr_empty:54}`）与库内复算**逐字段 MATCH** ⇒ **重启接口层不丢 job、不丢进度**；
* `80_port_after.txt`：5301–5305 **全 0 监听**（停服务按精确 PID，无 `pkill -f`/`killall`）。

## 4. AC 覆盖（本单可判定的部分）

| AC | 本单覆盖 | 证据 |
| --- | --- | --- |
| **AC-01** 同书重跑幂等（行级） | ✅ 同 `pdf_path` + 同 `page_range` 连跑两次：第二次 `counters.inserted == 0`、行数不变、行集指纹与逐字段 CSV diff 为零 | `1b_i/4*.txt/…`、`1b_i/49_diff_before_after_rerun.txt` |
| **AC-02** 同书重跑幂等（影像级） | ✅ 影像清单（路径 + `sha256` + 字节数）重跑前后**完全一致** | `1b_i/43_imgman_before_rerun.txt` vs `4A_imgman_after_rerun.txt` |
| **AC-03** 断点续跑不重复 | ✅ 中途（已提交页 ≥2 且 < 总数）SIGKILL 全部 worker + 池（精确 PID）→ 重启续跑至结束：终态行数 == 串行臂、`count == count(distinct …)`、**断点前已提交行逐字节未变** | `1b_i/6*.txt` |
| **AC-04** 并行 == 串行（含 bbox） | ✅ 空库副本上 w=1 与 w=4 各跑一次；`(pdf_name,page,idx,text,x1,y1,x2,y2)` 全字段有序导出 **diff = 0 差异** | `1b_i/5C_diff_serial_vs_parallel.txt` |
| **AC-05** 进度真实 / 不得假完成 | ✅ E2 的 `total/done/failed/cursors/counters` 与独立复算脚本逐字段 MATCH；`state=DONE` 时 `failed_pages` 为空 | `1b_i/35_*.txt` / `46_*.txt` / `69_*.txt` / `75_*.txt` |
| **AC-10** 批量事务（无每页一次 connect/commit/close） | ✅ 新增写路径**按 chunk 一事务**（`commit_chunk`）；worker 进程 0 次 DB 连接（静态：worker 不 import sqlite3） | 见 §3 ④ 与 §6 偏差 D-1（`processor.py` 旧逐页写法**未改**） |
| **AC-11** 进程分离 | ✅ SIGKILL 接口层后：worker `kill -0` 全 0（存活）+ 6 s 两次采样已完成 chunk 数**严格增长**；重启接口层后 E2 ↔ 库内复算逐字段一致 | `1b_i/71_*.txt` / `72_cursor_advance.txt` / `75_e2check_sep.txt` |
| **AC-13** 端口纪律 | ✅ 全程只用 **5301–5305**（非登记端口），起停前后 `lsof` 取证；未碰 5164/5195/5196/5555/5173/5174 | `1b_i/06_port_before.txt` / `80_port_after.txt` |

**本单不覆盖（留 1b-ii / 未做）**：AC-06 / AC-07（E5 已实现但缺 E3 结果面与本次全量对账）、
AC-08 / AC-09（依赖 E3 与 `dedupe_key` 复算）、AC-12（影像外置：本单**遵守**但未做 N∈{0,100,1000} 斜率实验）。

## 5. 未完成项（**如实列**）

| # | 项 | 状态 | 说明 |
| --- | --- | --- | --- |
| 1 | **E3 / E4 / E7** | **未做** | 派单明确留 1b-ii；E3/E4 仍未注册 ⇒ `404` |
| 2 | **边款影像** | **未落盘** | 检测**照样做**（其结果参与 `exclude_mask`，会影响释文块匹配，不做就不是同一份解析），但规范 §4.1 D-4② 只定义印面交付影像（`faces/<book_key>/p####_i##.<ext>`），故 1b-i **不写边款图**（旧 `output/<书名>/*_边款.webp` 属 Streamlit 路径，未动）。**缺口已登记**（§6 G-2） |
| 3 | **`images` 侧表 / `seals` 侧表** | **未写** | 本单只写 `stamps` + `job_pages` + `jobs`；`sha256` / `bytes` / `width·height·color_mode` 未落库（影像 `sha256` 由 worker 回传给池、记在日志与自测证据里，**未入表**）——属 §4.1 D-4① 的后续 |
| 4 | **AC-12 的斜率实验** | **未做** | 需 N∈{0,100,1000} 三档影像导入与 `du -k` 测量；本单不涉及 |
| 5 | **`book_key` 未登记时的退化** | **已实现但未测** | `books.book_key_for` 退化为文件名主干（`tmp.pdf` → `TMP` 走的是 `book_codes.json` 的正规 `key`）；退化分支无自测样本 |
| 6 | **`jobs.state` 的 `PAUSED`** | **未实现** | 池不会主动暂停；`PAUSED` 仅在活跃/终态判定里被承认（1a 既有口径） |
| 7 | **多 job 并行** | **未做** | 池按 FIFO **一次跑一个 job**（用满全部 worker）。§5.3 的上限是「同时跑的 job 数 ≤ worker 数」，取 1 ≤ 4 **合规**，但不是最大化调度 |
| 8 | **`ctrl/index.js` 入表 / 前端联调** | **未做** | 不属本单；`feicui/web/**` 未写一行 |
| 9 | **doc 预处理开关的精度结论** | **未定论** | 开关**已实现且默认关闭开关口径不变（默认＝开）**；`=0` 形态**未做**样本级文本比对 = **若将来要改默认，必须先补精度验收** |
| 10 | **AC-03 的 50% 回退点**（`X ∈ {25%, 50%}` 要求**两个百分点各 ≥1 次**） | **已补（50% 点 → 实测 57.1%）** | 段② 的那次 kill 落在**已提交 3/7 页＝42.9%**（连续前缀 2/7＝28.6%）⇒ 只近似 25% 点。**补测**（本单 D-2，工具 `server/selftest/probe_ac03_kill50.py`，`tmp.pdf` 27–33 / `chunk_size=1` / `w=2`）：**已提交 4/7 页＝57.1%**（连续前缀亦 4 页）处 SIGKILL 池＋2 worker（精确 PID，`kill -0` 逐 PID 确认已死）→ 续跑 `--drain` 收尾 ⇒ ① 终态 `DONE 7/7`、`failed=0`；② **断点前 22 行零改写**（`SUBSET = IDENTICAL`）；③ **终态 42 行与 1b-i 串行臂 `52_serial_rows.csv` 逐字节相同**（`DIFFCSV = IDENTICAL`）⇒ 两个点位（25% 附近 42.9%／50% 点 57.1%）**均已各 ≥1 次**。证据：`evidence/1b_ii/46_reg_ac03_kill50_probe.json` |

## 6. 规范缺口 / 偏差登记（**不发明契约**，请规范角色按 §0.4 裁定）

| # | 类型 | 内容 | 本单取法（**未静默**） |
| --- | --- | --- | --- |
| **G-1** | 偏差（**不改既有代码**） | §4.1 **D-3** 要求「批量事务（替换每页一次 connect/commit/close）」，证据面落在 `processor.py` 行 432/440/441 | 本单**未改 `processor.py` 一个字节**（派单硬约束：只许加法、默认行为不变）。**新增的执行路径**（池 + worker）**完全按 chunk 一事务**、且 worker **0 次 DB 连接**；旧的逐页写法仍在 `processor.py` 里（Streamlit 退役边界内）。**AC-10 的静态判据仍会命中 `processor.py`** ⇒ 需规范角色裁定：AC-10 的适用面是「新增解析链路」还是「全仓」 |
| **G-2** | 缺口 | 边款影像的交付口径（是否入 `faces/`、命名、是否入库）规范未定 | 本单**不落边款影像**（见 §5-2） |
| **G-3** | 缺口 | `worker 数` 默认值：§5.1 写「**默认 8**（草案，待 Zang 裁定）」且 §9-R4 未裁 | 本单按**派单 + AC-04 钉值 4** 落地（`FEICUI_WORKERS=4`）；**未**按 §5.1 的 8 —— 该偏差是**口径冲突**（规范草案 vs 钉值），需收口 |
| **G-4** | 缺口 | 「池」这一进程的形态规范未定：§1.1 只写「worker 池 N 个独立计算进程」＋「任务队列（进程内队列或本地持久队列，形态由 Kong 定）」；**池本身是不是独立进程、谁拉起它**没定 | 本单取：**池＝独立常驻进程（无端口、不是接口层的子进程）**，由运维/脚本拉起（`python -m app.pool`）。这是 AC-11「kill 接口层后 worker 仍推进游标」**唯一可行**的形态；若规范要求「接口层拉起池」，则该 AC 与本形态互斥（须裁） |
| **G-5** | 缺口 | **任务队列**形态规范未定（持久队列 vs 进程内） | 本单取**库即队列**：`jobs` + `job_pages` 就是持久队列（断点、并发上限、进度全部由库给出）⇒ 重启不丢任务，且 AC-11 的「接口层死不掉任务」天然成立 |
| **G-6** | 缺口 | `stamps.id` 的自增语义与影像 `sha256` 落库位置（`images` 侧表 vs 新列）未定 | 本单**不写 `images`/`seals`**、不加列（只加法的最小面）；影像 `sha256` 只在 worker 回传与自测证据中（§5-3） |
| **G-7** | 缺口 | §3.1 E2 只给 `cursor:{chunk_lo,chunk_hi}`；**chunk 级「已完成数」无契约字段**，而 AC-11 的判据正是「已完成 chunk 数 / `chunk_hi` 推进」 | 本单**未改 E2 响应形状**（不动契约）：AC-11 的读数由自测脚本**直接查库**（`count(distinct chunk_index) WHERE state='DONE'`）取得；`jobs.cursor_chunk_lo/hi` 列已开始真实推进（可作 E2 之外的观测面） |
| **G-8** | 偏差（**默认值纪律**） | 派单要求「doc 预处理开关必须可配置，且**默认保持现状行为**」；规范正文**无此开关**（§5.4 只是性能口径） | 本单：`FEICUI_DOC_PREPROCESS=1` 为默认（＝PaddleOCR 默认＝现状），`=0` 需显式开启；README §11.5 已登记 |
| **G-9** | 缺口 | `cpu_threads` 的取值规范未写（§5.2 只说「每 worker 一实例」） | 本单按派单口径 `cpu_threads=2`（≤2 上限）落地，并未回归 `_common_args` 默认 10 —— 需规范登记 |

### 6.1 裁定状态（回填时点 **2026-09-20 13:1x**）

| 项 | 状态（实测/核验，非推测） |
| --- | --- |
| 规范真源 | `docs/feicui.spec.md` **v1.2**，md5 `6dbe0b3c915d7f8ed43576a00122dcf1`，**mtime 2026-09-20 12:10**（＝本单前后**未变**） |
| G-1 ～ G-9 | **全部仍是「待裁定」**：规范侧（Jing）截至 13:1x **未对本表任一缺口做出裁定**（v1.2 是收尾前的最后一版，其后未见新版本行） |
| 其中**必须**先裁的两条 | **G-3**（§5.1 草案「默认 8」 vs AC-04 钉值 `N=4`——本单按 4 落地，与草案字面不一致）；**G-4**（池是否独立进程——AC-11「kill 接口层后 worker 仍推进」**只在「池为独立常驻进程」这一形态下成立**，若规范改要求「接口层拉起池」，则 AC-11 与本形态互斥） |
| **G-10（本单新增）** | **AC-03 的两点位**：原仅 1 次 kill（42.9% / 连续前缀 28.6%）；**本单已补 50% 点位**（57.1%，见 §5-10 / `evidence/1b_ii/46_reg_ac03_kill50_probe.json`）⇒ 两点位各 ≥1 次，**该缺口已闭合**（仅剩「点位口径按已提交页数还是连续前缀」这一点请规范侧顺手钉一句） |
| **G-11（本单新增）** | **「同区间重解析行数」≠「库内行数」的观测**（见 `REPORT_1b-ii.md` §5-G-e）：`tmp.pdf` 页 13–14 库内 12 行 → 重解析 13 行（`inserted=1 skipped=12`）；页 13–19 库内 30 行 → 1b-i 首跑解析 31 行。**旧行零改写（AC-01 现状成立）**，但「行数不变」不成立 ⇒ 请裁定 AC-01 的口径并按需定性差异来源 |

**回填自证**：本文件改动仅限 §1 / §3 / §5-10 / §6.1 的**填充**（无删改结论性表述）；回填**未重跑任何测试、未改任何代码或数据**，所有数字均取自已留档的证据文件（`evidence/1b_i/**`，时点 12:26–12:29）。
