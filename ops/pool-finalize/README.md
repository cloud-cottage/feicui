# ops/pool-finalize —— 池侧「B 项：`template_unusable` 一次落终态」对照证据

**结论（一句话）**：修复后（commit `67b0419`），模板不可用的 job 在**被认领的那一轮内**就写进终态——池日志 **3 行 / 1 轮**、`jobs.state=FAILED_PARTIAL`、`jobs.error` 写明真实原因、`finished_at` 落库，池 **3.7 s 内自行退出（rc=0）**；修复前同一场景 **187 轮 × ≈0.31 s** 无限重试、`state` 停在 `RUNNING`、`error`/`finished_at` 均为 `null`、池启动 **62 s 后仍活**，只能人工 `SIGTERM` 终止。

全部证据来自 **scratch 探针库**（日志表头 `prod_db = False`），**未建生产 job、未写生产库、未动生产池**。

---

## 1. 修前 / 修后对照表

| 维度 | 修前（`before.log`，修复未生效的池） | 修后（`after.log` / `after2.log`，`67b0419` 生效的池） |
|---|---|---|
| 该 job 的池日志行数 | **374 行**（= 187 轮 × 2 行）※ | **3 行** |
| 轮数 | **187 轮**（无效重试） | **1 轮** |
| 每轮间隔 | **≈0.3101 s**（min 0.3040 / max 0.3940；`FEICUI_POOL_POLL=0.3`） | 不适用（无第二轮） |
| 每轮落 FAILED 页数 | 第 1 轮 6 页；其后 **186 轮全部 0 页** | 1 轮 6 页 |
| `jobs.state` | **`RUNNING`**（`claim_job` 置的，永不收口）※ | **`FAILED_PARTIAL`** |
| `jobs.error` | **`null`**※ | **`template_unusable: missing keys ['hsv_low', 'hsv_high', 'min_area', 'text_offset', 'density_min', 'density_max']`** |
| `jobs.finished_at` | **`null`**※ | **`2026-10-11T08:49:53+08:00`** |
| `job_pages` | 6 页记 FAILED（第 1 轮即完成），但 job 行不收口 | 6 页 `FAILED` / 0 `PENDING` / 0 `RUNNING`（`after_db_state.json`） |
| 池进程 | 启动后 **61.97 s 仍活**（55 s 检查点 `POOL_STILL_ALIVE=1`），最终被 `SIGTERM` 人工终止 | **3.66 s 内自行退出**（`after2`），`wait $PID` 得 **rc=0** |
| 日志尾部 | `收到信号 15 ⇒ 优雅退出`（人工） | `池退出：{"pages_failed": 6, ...}`（自行） |

※ **来源说明（不掩盖缺口）**：修前的 `state=RUNNING` / `error=null` / `finished_at=null` 与「55 s 后仍活」是**当次探针现场读数**（`run_probe.sh` 打印的 `POOL_STILL_ALIVE` 行 + 当时对 scratch 库的 SQL 读数），**scratch 未留修前库快照**，故本目录**没有** before 版 JSON。日志本身能独立佐证的部分是：第一轮之后 **186 轮全为 0 页重试**、job 从未收口、池最终靠人工信号才退出（`before.stats.txt` 逐行统计）。
※ **数字勘误**：交办单记的「342 行 / 171 轮」是**读取当时**（≈08:48:56，`before.log` 仍在增长中）的中间值；本目录一律按**最终文件**统计：**374 行 / 187 轮 / 0.3101 s 一轮**。结论不变。
※ **rc=0 来源**：`after_run.sh` / `after_run2.sh` 里 `wait $PID; RC=$?` 的 **stdout**（scratch 未留存该行；`after.log` 只接住了 python 的输出）。日志侧佐证：无「收到信号」行、脚本未走 `TIMEOUT` 分支、退出发生在启动后 3.66 s。

---

## 2. 变动清单（`67b0419`，与本项相关的两处）

| 文件 / 函数 | 改动 | 缺省行为 |
|---|---|---|
| `server/app/pool.py::Pool._pick_job`（模板不可用分支） | `_fail_all_pending(...)` 之后新增 `state = repository.maybe_finalize_job(self.st.db_path, claimed["job_id"], error=err)`；`self.job_finished = state or "FAILED_PARTIAL"`；日志追加「，job 一次落终态」与 `收尾 ⇒ %s（error=%s）` | 只有该分支变化（模板不可用原本就不该继续） |
| `server/app/repository.py::maybe_finalize_job` | 新增 **keyword-only** `error: str \| None = None`；`error is None` 时仍按旧形态写入（`FAILED_PARTIAL` ⇒ `failed_pages=<n>`、`DONE` ⇒ `NULL`）；SQL 由 `CASE WHEN` 改为参数化 `error = ?` | **不变**——既有调用方（常规收尾路径）不传 `error`，落库形态与改前逐字节等价 |

- 同提交还含 `server/README.md`、`web/src/api/jobsPreview.js`（预览默认 dpi 110→150）等，**与本项无关**。
- `fix.patch`（本目录）是探针期生成的**等价补丁**，与 `67b0419` 同源，便于对照读 diff。

---

## 3. 测法复跑说明（命令逐字）

```bash
# 0) 选一个 scratch 目录（本单用的是 ~/.hermes/profiles/zang/cache/scratch/feicui_tpl_unusable）
S=~/.hermes/profiles/zang/cache/scratch/feicui_tpl_unusable
mkdir -p "$S/faces" "$S/run" "$S/wlogs"
cp "$S/test.db" "$S/probe.db"          # 只用 scratch 副本作库；严禁指向生产库

# 1) 四处重定向 + 探针参数（缺一不可）
export FEICUI_DB="$S/probe.db"                       # ① 库
export FEICUI_FACES_DIR="$S/faces"                   # ② 印面/素材目录
export FEICUI_POOL_STATE="$S/run/pool.state.json"    # ③ 池写锁＋状态（★ 必须重定向，见 §4(b)）
export FEICUI_WORKER_LOG_DIR="$S/wlogs"              # ④ worker 日志
export FEICUI_ALLOW_PROD_MIGRATE=1                   # 允许对 scratch 库跑迁移自检
export FEICUI_WORKERS=1
export FEICUI_POOL_POLL=0.3                          # 复现 ≈0.31 s/轮

# 2) 起池：--drain ＝ 跑完活跃 job 即自行退出
cd /Users/kevin/bistro/xiai/feicui/server
./.venv/bin/python -m app.pool --workers 1 --drain 2>&1 | tee "$S/replay.log"
echo "exit=$?"    # 修后期望：自行退出且 rc=0；修前：3.66 s 内不会退出，需 55 s 后人工 kill
```

- 三个现成脚本（**原样入库**，含各自用途注释）：`run_probe.sh <before|after>`（`SECS` 默认 55，起池→等 55 s→报 `POOL_STILL_ALIVE` / worker pid）、`after_run.sh`（起池并等其**自行退出**，报退出码；120 s 未退出才清场）、`after_run2.sh`（精简版）。
- 读库快照（只读，`?mode=ro`）：
  ```bash
  sqlite3 "file:$S/test.db?mode=ro" -header -column \
    "select job_id,state,error,finished_at,started_at,updated_at from jobs;"
  sqlite3 "file:$S/test.db?mode=ro" -header -column \
    "select state,count(*) n from job_pages group by state;"
  ```
- 复现前置：scratch 库里需有一个 `pdf_name` 未配模板（`books.template_for` 拿不到全部键）的**活跃 job**，本单用 `未标定探针书.pdf`（`placeholder.pdf` 56 B）＋ `page_from=1, page_to=6, chunk_size=3`。造 job 只在 scratch 库发生。

---

## 4. 两条已知约束

**(a) 旧池不吃新码 —— 修复在「下次拉起池」时生效。**
`67b0419` 改的是池进程内的代码路径；**已在跑的池**（本轮为 pid 9595 `-m app.pool --workers 4 --drain` ＋ 4 个 `feicui_worker.py`）是修复前拉起的进程，Python 已加载旧字节码，**不会**因文件改动而变。旧池遇到模板不可用的 job 仍会每 ≈0.31 s 重试、`state` 停在 `RUNNING`，直到下次拉起池才收口。⇒ 结论与验收都要注明「修复生效时点 ＝ 池重启」，**不要**在旧池上验证本项。

**(b) 起 scratch 池必须重定向 `FEICUI_POOL_STATE`。**
池的单写者锁取自 `FEICUI_POOL_STATE`（`server/app/config.py:227`，缺省 `server/.run/pool.state.json`），**不随 `FEICUI_DB` 走**。只改 `FEICUI_DB` 而漏改它，scratch 池会去抢**生产池的同一个 flock**（本单日志 `🔒 单写者锁：<scratch>/run/pool.state.lock` 即证明已重定向生效）——轻则 scratch 池起不来/挡住生产池，重则扰动生产写入。起 scratch 池的安全姿势：**四处 env 全给**（`FEICUI_DB`/`FEICUI_FACES_DIR`/`FEICUI_POOL_STATE`/`FEICUI_WORKER_LOG_DIR`）＋ `--workers 1`。

---

## 5. 文件清单与来源（原件在 scratch，闲置 24h 会被清理 ⇒ 本目录为长期留档）

| 本目录文件 | 大小 / mtime | sha256（前 16） | 来源（scratch 原件） |
|---|---|---|---|
| `after.log` | 2217 B / 08:49:29 | `31280cae6f810fa2` | 同名原件（**原样拷贝、mtime 保留**） |
| `after2.log` | 2217 B / 08:49:53 | `6977381fadf993c3` | 同名原件（同上；两文件仅时间戳/pid 不同，结论一致） |
| `after_db_state.json` | 6084 B | `65ec08a55c3171a7` | `test.db` 的**只读读数快照**（含 `jobs` 行、6 条 `job_pages`、聚合；另附 `supplementary_run`＝`copy_regress.db` 旁证） |
| `before.excerpt.log` | 4646 B | `581f6e2d0fefe8b2` | `before.log` 的**节选**（头 15 行 ＋ 尾 8 行 ＋ 「省略第 16--379 行 / 364 行 / 182 轮」说明） |
| `before.stats.txt` | 1815 B | `fcabd41f17f504a7` | 对 `before.log` 全文的**逐行统计**（行数/轮数/间隔/时间跨度/退出方式） |
| `run_probe.sh` | 1427 B / 08:47:57 | `182f606e24e03916` | 同名原件（产生 `before.log` 的探针脚本，原样拷贝） |
| `after_run.sh` | 1235 B / 08:49:11 | `d6d6c6bd7632b77a` | 同名原件（产生 `after.log`） |
| `after_run2.sh` | 662 B / 08:49:43 | `8166e7f3c73a7296` | 同名原件（产生 `after2.log`） |
| `fix.patch` | 3882 B / 08:47:35 | `7a18ae6391af1dad` | 同名原件（等价补丁） |
| `README.md` | 本文件 | — | — |

**未入库的 scratch 原件（按纪律剔除无信息巨型日志 / 二进制）：**

| 原件 | 规模 | 处置理由 |
|---|---|---|
| `before.log` | 83352 B / 387 行 / sha256 `237da6a6a8ec6f70e3c12dbfa522f8a574570bb9ddf4123fc6c4e0555e1c8ccf` / mtime `2026-10-11 08:49:01` | 387 行中 **374 行是同一 job 的同构重复**（187 轮 × 2 行），无新信息 ⇒ 只留节选 ＋ 统计（**未编造、未改写任何日志内容**） |
| `test.db`（+ `-shm`/`-wal`）、`copy_regress.db`、`placeholder.pdf`、`faces/`、`wlogs/worker0.log` | 61 KB / 32 KB / 56 B / 8 KB | 二进制库与运行中间物；其**读数**已摘入 `after_db_state.json`，库文件本身不入库 |

> 旁证（`after_db_state.json::supplementary_run`，源 `copy_regress.db`，mtime 08:51:40）：修复后另一次 scratch 回归跑，模板缺键集合不同（`['a','b']`），仍是**一次收口**——`state=FAILED_PARTIAL`、`error=template_unusable: missing keys ['a','b']`、`finished_at=2026-10-11T08:51:40+08:00`、6 页 `FAILED`。说明 `error` 写入的是**本次真实原因**，而非写死的字符串。
