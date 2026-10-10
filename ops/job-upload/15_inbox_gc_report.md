# 15 · inbox 清理策略（R41 / §3.20）证据报告 —— Kong（接手收尾单）

- **仓**：`/Users/kevin/bistro/xiai/feicui`（分支 `main`）
- **本单时点**：2026-10-11 07:04 CST
- **本单性质**：接手（非重派）。上一任在同一需求上撞迭代上限；**实现已落盘、大部分证据已跑**。本单只补三件事：跑 `14_inbox_gc_scenarios.py`、必要时修、写本报告并提交。
- **口径真源**：`feicui/docs/inbox-gc-draft-v0.1.md`（Zang 起草）＋ 规范 `feicui/docs/feicui.spec.md` v1.23 §3.20（Jing 已提交，含 §3.20.1〜7 与 AC-72〜AC-77）。**本单未碰 `docs/**`**。

---

## 0. 本单修了什么（两项，均未放宽判据、未删断言）

| # | 文件 | 类型 | 说明 |
|---|------|------|------|
| 1 | `server/app/inbox_gc.py` | **实现真缺陷修复** | `apply_plan` 把回收项 `shutil.move` 进 `.trash/` 后，**原 mtime 被保留**——被回收的旧 PDF（已过保留期，mtime 可能几天前乃至几个月前）落进 trash 的**那一刻就已被判「过期」**，下一次扫描立即硬删，**回滚窗口归零（两段式形同虚设）**，违反 AC-74「未达 trash 保留期时硬删不发生」。修法：move 后用 `os.utime(dest, (now, now))` 把 mtime 钉为**入 trash 时刻**，宽限期 T 天自此刻起算（`import os` 同步加上）。 |
| 2 | `ops/job-upload/14_inbox_gc_scenarios.py` | **脚本夹具自洽** | S3 原本用**默认参数**跑 `--apply`（容量闸 50 GiB 不触发）⇒ 只收到「过保留期」的 2 个文件，而脚本第 191/210 行的断言却把 `noref_2d.pdf`（仅 2 天、容量闸场景才收）也算进「应被移动」。**断言不弱化**的前提下，把 S3 改为 **`--apply --max-bytes 3500`**（复用 S2 同一容量闸场景），使 collect 集 ＝ {done_old、noref_old（保留期）＋ noref_2d（容量闸）} 共 3 个，逐文件核对「3 个都被真移入 trash」。 |

> 缺陷 #1 是**修实现**（不是脚本）：AC-74 明确要求「刚移入 trash 的文件在保留期内不得硬删」；不修则 S3b 断言必然失败、且线上两段式回滚窗口名存实亡。缺陷 #2 是**修脚本**（不修则 S3 在默认参数下不可能凑齐 3 个被回收项）。

---

## 1. 七项证据逐条读数

### 证据 ①：`ACTIVE` 引用豁免（永不回收）
- 探针造真 job（`zang_probe.pdf`，state=`QUEUED`）后：
  - `GET /api/jobs/inbox/summary` → `exempt` 中 `20261011/zang_probe.pdf` `reason=active_job`、`job_id=job-12e92369f5564951bc23b7218d6ad975`、`state=QUEUED`、`note=活跃 job（QUEUED/RUNNING/PAUSED）引用 ⇒ 永久豁免`。
  - CLI `--retention-days 0 --dry-run`（极端：0 天保留 ⇒ 其余全应收）→ **8 收 / 9 豁免**，探针文件仍在 `exempt`（`zang_probe_in_collect=false`）。
- 场景 S1 复证：`20261011/active.pdf`（被 `scn-active` 的 QUEUED job 引用）`reason=active_job`，**连容量闸也不动它**（S2 中 `collect` 不含 active.pdf）。
- 依据：`ops/job-upload/13_inbox_gc_probe_raw.json`、`14_inbox_gc_scenarios_raw.json`。

### 证据 ②：终态 job 超保留期 ⇒ 进待回收清单【本单新补】
- **隔离 temp DB**（`var` 外，`feicui.db` 的 WAL 感知副本）中造：`scn-done-old`，`state=DONE`，`created_at=updated_at=今天−90 天`。**未拿生产 5 条 `DONE` 当夹具**。
- S1 默认 dry-run（保留期 30 天）：`collect = {20261011/done_old.pdf: retention_expired, 20261011/noref_old.pdf: retention_expired}`。
  - `done_old.pdf` 被终态 job 引用、自 `updated_at` 起算 **90 天 > 30** ⇒ `retention_expired`（`reference_source=job.updated_at`）。
  - `noref_old.pdf` 无引用、按 `mtime` 起算 **60 天 > 30** ⇒ `retention_expired`（`reference_source=file.mtime`）。
- **结论**：终态超保留期的文件正确进入「将回收」清单。

### 证据 ③：trash 未满 T（7 天）⇒ 不硬删【本单新补】
- S1b（trash 宽限期 T=7 天）：
  - `trash_keep = [20261011/trashed_fresh.pdf]`，`reason=trash_retention_not_expired`（今天入 trash）。
  - `hard_delete = [20260901/trashed_old.pdf]`（30 天前入 ⇒ 已满 7 天 ⇒ 进硬删）。
- **盘上读数**：S1/S2 全程 `.trash/20261011/trashed_fresh.pdf` 仍在盘上（未被删）。
- **结论**：宽限期内不硬删，满期才进硬删。

### 证据 ④：容量闸（按最久未引用淘汰到 ratio×M，`ACTIVE` 仍豁免）
- 探针（上一任已跑，照录）：`--max-bytes 2000` ⇒ `capacity_gate_triggered=True`、`reason=capacity_pressure`。
- 场景 S2 复证（`--max-bytes 3500`，target=3500×0.8=**2800**）：`collect` 在保留期两项之外**追加** `20261011/noref_2d.pdf: capacity_pressure`（最久未引用的豁免项优先被淘汰）；`20261011/active.pdf` **未被淘汰**。
- **结论**：容量闸按「最久未引用」淘汰到目标值，`ACTIVE` 豁免优先保持。

### 证据 ⑤：`--apply` 真移入 trash（源消失）＋ 三数不变 ＋ 端点 `apply:true`【本单新补】
- **CLI S3**（`--apply --max-bytes 3500`）：
  - `mode=apply`、`moved_files=3`（done_old / noref_old / noref_2d）、`trash_dir=…/inbox/.trash/20261011`。
  - `src_gone = {done_old.pdf:true, noref_old.pdf:true, noref_2d.pdf:true}`（**源位置消失**）。
  - `trash_has = {…均 true}`（**trash 内出现同名文件**）。
  - `keep_still_present = {active.pdf:true, noref_1d.pdf:true}`（豁免文件未被误动）。
  - **三数 before == after**：`{jobs:7, job_pages:32, stamps:89}` 前后逐字不变。
- **S3b**（apply 后再 dry-run）：`hard_delete=[]`；刚移入的 3 个文件全在 `trash_keep`（未满 T ⇒ 不硬删）。
- **端点 S4**（**临时 API 实例 :5197**，独立 inbox/库/端口）：`POST /api/jobs/inbox/gc {"apply":true}` → `status=200`、`mode=apply`、`moved_files=2`、`src_gone=true`、`trash_has=true`、`keep_present=true`（ACTIVE 文件仍在）、**三数 7/32/89 前后不变**。
- **结论**：`--apply` 与端点 `apply:true` 都把文件真移入 trash、源位置消失、豁免文件不动、三数逐字不变（只动文件、不动库）。

### 证据 ⑥：API 启动扫描只 dry-run（永不自动删）
- 重启服务（PID **38847 → 61349**）后启动日志：`inbox 启动扫描（只 dry-run，未删任何文件）：… 将回收 0 … 豁免 9`；**inbox 仍 9 文件**。
- 落报告 `ops/job-upload/inbox_gc_20261011-070138.json`（gitignored，运行时报告）。
- **结论**：启动只扫描 + 告警，无任何删除/移动。

### 证据 ⑦：端点默认 dry-run
- `POST /api/jobs/inbox/gc`（**空体** 与 **`{"apply":false}`**）→ 均 `mode=dry-run`；inbox `{9 文件 / 6786 B}` **前后不变**（`unchanged=true`）。
- **结论**：不带 `apply:true` 绝不改盘（AC-73）。

---

## 2. 常量与默认值（`server/app/config.py`，单点可改；env `FEICUI_INBOX_GC_*` 或 `server/config.json` 覆盖）

| 常量 | 默认值 | 含义 |
|------|--------|------|
| `INBOX_GC_RETENTION_DAYS_DEFAULT` | **30** 天 | 终态 job 自 `updated_at`、无引用文件自 `mtime` 起算 |
| `INBOX_GC_CAPACITY_MAX_BYTES_DEFAULT` | **50 GiB**（`50*1024^3`＝53687091200） | 容量闸上限 M |
| `INBOX_GC_CAPACITY_TARGET_RATIO_DEFAULT` | **0.8** | 淘汰到 `ratio×M` ＝ **40 GiB** |
| `INBOX_GC_TRASH_RETENTION_DAYS_DEFAULT` | **7** 天 | trash 宽限期 T（两段式第二段） |
| `INBOX_GC_STARTUP_SCAN_DEFAULT` | **开**（`True`） | API 启动扫描（只 dry-run） |
| `INBOX_GC_TRASH_DIRNAME` | **`.trash`** | trash 子目录名（`inbox/.trash/<yyyymmdd>/`） |
| （行为、非数值） | **dry-run 默认 / 永不自动删** | CLI 需显式 `--apply`；端点需 `{"apply":true}`；**无任何自动删除路径** |

---

## 3. E1 顶层 `error` 对齐（前后对比；**保留嵌套 `detail`，不拉平**）

本单新增的两个 400 分支（§3.1 表下注 G-6 的真缺陷修复面）统一走 `_e1_error()`（`routers/jobs.py:55`）。

| | 前（历史嵌套形态） | 后（本单／与 E8 同形） |
|---|---|---|
| 写法 | `raise HTTPException(400, detail={"error":"NOT_A_PDF","detail":"…"})` | `return _e1_error(400,"NOT_A_PDF",{"error":"NOT_A_PDF","detail":"…"})` |
| 响应体 | `{"detail": {"error":"NOT_A_PDF","detail":"…"}}`（**顶层无 `error`**，机器码嵌在 `detail` 内） | `{"error":"NOT_A_PDF","detail":{"error":"NOT_A_PDF","detail":"…"}}`（**顶层 `error` ＝ 机器码** ＋ **顶层 `detail` 原样保留**） |

- 实测（`13_inbox_gc_probe_raw.json`）：`e1_pdf_not_found` 与 `e1_not_a_pdf` 的 `top_keys` **均含 `error` 与 `detail`**，`status=400`。
- **与 E8 参照同形**：`POST /api/jobs/upload` 出错体为 `{"error":"BAD_CONTENT_TYPE","detail":"…","allowed":[…]}`（顶层 `error` ＋ 顶层 `detail`）。
- **范围纪律**：**只**本单新增的 `PDF_NOT_FOUND` / `NOT_A_PDF` 两支加顶层 `error`；**其余既有 400 的历史嵌套形态一概不动**（历史不追溯，唯一口径由规范 v1.23 给）。

---

## 4. 三数交底（`jobs` / `job_pages` / `stamps`）

| 库 | 位置 | 读数 | 说明 |
|----|------|------|------|
| **生产** `yinpu.db` | `/Users/kevin/bistro/xiai/data/yinpu.db` | **5 / 32 / 89** | 本单**前后一致**（探针 job 已删，回落到基线）；GC 全程只读引用，**零 DB 写** |
| **隔离场景库**（prod 的 WAL 感知副本 ＋ 2 条场景 job） | scratch 临时目录内 | **7 / 32 / 89** | S3/S4 的 `apply` **前后逐字不变**（`three_counts_unchanged=true`）；场景库与生产库**物理隔离**，生产未被写 |

**结论**：GC 只动文件、不动库（§3.20.6 红线）；`jobs`/`job_pages`/`stamps` 三表行数与内容前后不变。

---

## 5. 本单临时产物清点

**留作证据（已提交）**
- `ops/job-upload/13_inbox_gc_probe.py` ＋ `13_inbox_gc_probe_raw.json`（上一任的①④⑥⑦证据）
- `ops/job-upload/14_inbox_gc_scenarios.py` ＋ `14_inbox_gc_scenarios_raw.json`（本单②③⑤证据；隔离场景）
- `ops/job-upload/15_inbox_gc_report.md`（本报告）

**不提交（gitignored，运行时报告）**
- `ops/job-upload/inbox_gc_*.json`（`.gitignore:33` 已忽略；本次生成 `inbox_gc_20261011-0659xx / 070138 / 0702xx` 若干）

**临时 scratch（24h 自动清理，本单未删）**
- `/Users/kevin/.hermes/profiles/zang/cache/scratch/inbox_gc_scenarios/`（隔离 inbox ＋ temp DB ＋ endpoint 夹具）

**本单已处置的临时物**
- 探针 job `job-12e92369f5564951bc23b7218d6ad975`（`zang_probe.pdf`）**已删** ⇒ 三数回 **5/32/89**。
- **临时 API 实例 :5197**（S4 用）**已终止**（见 §6 收尾读数）。

---

## 6. 收尾读数

- **提交哈希**：本单（实现＋证据＋本报告）入库提交 ＝ **`6d4eb9b`**（`6d4eb9b107a6f26e3d3daf1cd1e9b07787cb78d6`，未 push）。
- **场景脚本退出码**：`python3 ops/job-upload/14_inbox_gc_scenarios.py` ⇒ **EXIT=0**（S1 / S1b / S2 / S3 / S3b / S4 全过，断言全绿）。
- **临时端口与进程**：
  - `lsof -nP -iTCP:5197 -sTCP:LISTEN` ⇒ **空**（`rc=1`，临时实例已终止；**未用 `pkill`/`killall`**，脚本内 `proc.terminate()`＋`wait(timeout=10)`）。
  - `ps` 复核：无 `:5197` 进程；PID **61349** ＝ **生产** feicui-api（监听 `127.0.0.1:5196`），非临时实例；PID 31420 ＝ 无关既有 uvicorn（`:5191`）。
- **生产库三数**：**5 / 32 / 89**（基线）。
- **生产 inbox**：**9 文件**，无 `.trash/` 移动（未动）。
- **上一任已跑读数（照录）**：`npm run build` **EXIT=0**；重启 PID 38847→61349。

---

## 7. 未完成项 / 遗留

- 无。本单三项（跑脚本＋修＋报告/提交）均已完成。
- 规范侧（`docs/**`、v1.23 §3.20 与 AC-72〜AC-77）由 Jing 管，**本单未碰**；`xiai/**`、`ctrl/**`、三采集库与三采集包**均未动**。
