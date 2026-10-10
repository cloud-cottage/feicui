# 18 · inbox 清理策略（R41 / §3.20）· **两条 OBS 收口**证据报告 —— Kong（窄修单）

- **仓**：`/Users/kevin/bistro/xiai/feicui`（分支 `main`）
- **本单性质**：**窄修**。只修 Neng 独立质检报的两条 OBS（**不重构、不改口径、不动 E1〜E8 语义、不碰 `docs/**`**）。
- **口径真源**：`feicui/docs/feicui.spec.md` **v1.23 §3.20**（含 §3.20.4 / §3.20.5 冻结命名、AC-72〜AC-77）。
  **规范是权威 ⇒ 本单未改规范一个字**；新字段命名与 CLI 两形已在本报告 §5 写明，**交 Jing 同步**。
- **提交哈希**：`<待填>`（本报告随该提交入库的说明见 §6；哈希由紧随其后的一次小提交登记，同 15 报告先例）

---

## 0. 本单改了什么（两处，均「只加法 / 不放松」）

| # | 文件 | 类型 | 要点 |
|---|------|------|------|
| 1 | `server/app/inbox_gc.py` | **CLI 命名分叉修复**（OBS-1） | 给 `main()` 的 argparse 加 **可选位置参数 `command`**（`nargs="?"`、`default="gc"`、`choices=["gc"]`、`metavar="[gc]"`）⇒ **规范冻结形 `python -m app.inbox_gc gc [...]` 与实现旧形 `python -m app.inbox_gc [...]` 两种都成立**（缺省动作不变＝`gc`）。**规范命名一字未改**。反向哨兵：非法词仍 `exit 2`（argparse 未被松成「吞任何词」）。同时把 usage / `--help` / 启动告警里的示例命令补成规范形。 |
| 2 | `server/app/inbox_gc.py` | **容量闸缺口显式字段**（OBS-2） | `build_plan()` 的返回体**平铺**三个可直接读的数：`capacity_target_bytes`（目标 `M×ratio`）／`collectable_bytes`（容量闸下**最多**可回收量）／**`capacity_gap_bytes`（缺口）**；**缺口 > 0** 时另给一条人读 `note`。`run()` 的 apply 分支 `{**plan, ...}` ⇒ **plan / apply 输出同源**，端点（`GET .../summary`、`POST .../gc`）与 CLI 同源。`_print_human` 加一行读数 ＋ 一行缺口说明；`startup_scan` 的信息日志加三个数、缺口 > 0 时加一条 `warning`。 |
| 3 | `server/app/routers/jobs.py` | **仅 docstring** | `inbox_summary` 的返回字段说明补上三个新数（无行为改动）。 |

**缺口定义（写进报告与规范同步告知，命名自定）**

```
collectable_bytes    = Σ(collect 项) + Σ(仍处保留期内、非 ACTIVE 的豁免项)   # = inbox 总量 − ACTIVE 引用项体积
capacity_gap_bytes   = max(0, (总量 − collectable_bytes) − capacity_target_bytes)
                     # 把可回收项「全数淘汰」后仍高于目标值的量；> 0 ⇒ 可回收 < 需回收
note                 = "可回收不足：可回收 X B 已全数列入淘汰，仍高于目标 Y B ⇒ 仍缺 Z B；
                       ACTIVE 豁免项 W B 不参与回收（不越权删）"        # 仅 gap > 0 时存在
```

> **为什么不把「保留期未到」算作不可回收**：容量闸的口径本就是「按最久未引用淘汰到 `ratio×M`」（§3.20.3 R2），
> 闸**允许**淘汰保留期未到的项（`reason=capacity_pressure`）⇒ 容量闸下**唯一**不可回收的就是 `ACTIVE` 引用项（铁律 ①）。
> 故 `collectable_bytes` 恒等于「非 `ACTIVE` 文件体积合计」，缺口＝「淘汰到极限仍差多少」。**不得为凑回收量去删 `ACTIVE` 引用项。**

---

## 1. OBS-1（CLI 命名分叉）：修前 FAIL / 修后 PASS

**修前基线取法（不是读代码推断）**：`git show HEAD:server/app/inbox_gc.py` 落**临时包**（scratch `prefix_pkg/app/`，配真 `config.py`）
⇒ 用真解释器 `server/.venv/bin/python -m app.inbox_gc ...` **真跑**。基线身份自证：`prefix_has_gc_choices=false`、
`prefix_has_gap_field=false`（对 `post_has_gc_choices=true` / `post_has_gap_field=true`），HEAD ＝ `8be7f7199c63a4af2ed69db107599be1b2618824`。

| 读数 | 修前（HEAD 版真跑） | 修后（工作副本真跑） |
|---|---|---|
| `python -m app.inbox_gc gc --dry-run` | **rc=2**，`error: unrecognized arguments: gc` ⇒ **FAIL** | **rc=0** ⇒ **PASS** |
| `python -m app.inbox_gc --dry-run` | rc=0（旧形可用） | **rc=0** ⇒ **PASS** |
| 两形 dry-run 输出逐字段一致 | —（无法比较） | **key 集合相同、唯一差异 `generated_at`**（两次运行时刻不同）；其余全部字段（`collect` / `exempt` / `collect_bytes` / `collect_files` / `capacity_*` / `constants` / `trash_*` …）逐个值相等 |
| 反向哨兵 `python -m app.inbox_gc foo --dry-run` | — | **rc=2**，`argument [gc]: invalid choice: 'foo'` ⇒ PASS（argparse 未被放松） |

逐字段比对原文（`16_…_raw.json` → step 3）：`keys_identical: true`、`differing_keys: ["generated_at"]`、
`value_diff_of_differing_keys: {"generated_at": ["2026-10-11T07:15:18.149910+08:00", "2026-10-11T07:15:18.187791+08:00"]}`。
（两形均带 `--json --no-report` ⇒ 无 `report_path` 参与比对。）

---

## 2. OBS-2（容量闸缺口无显式字段）：修前 FAIL / 修后 PASS ＋ 缺口场景完整输出

**缺口场景夹具（临时目录 ＋ 临时库副本，字节精确、可复算）**

| 文件 | 体积 | 引用 | mtime | 期望 |
|---|---|---|---|---|
| `inbox/20261011/active.pdf` | 5000 B | `QUEUED` job（`obs-active`）⇒ **ACTIVE** | 今天 | **永久豁免**（连容量闸也不动） |
| `inbox/20261011/noref_old.pdf` | 1000 B | 无 | −60 天 | 超保留期 ⇒ `retention_expired` |
| `inbox/20261011/noref_2d.pdf` | 1000 B | 无 | −2 天 | 保留期内 ⇒ 容量闸下转 `capacity_pressure` |

总量 **7000 B**；`--max-bytes 6000`、ratio 0.8 ⇒ **目标 4800 B**；可回收 **2000 B** ⇒ 淘汰到极限后剩 **5000 B** > 4800
⇒ **期望缺口 200 B**。

### 2.1 修前读数（HEAD 版真跑，同一夹具）：**无缺口字段 ⇒ FAIL**

- `capacity_gate_triggered: true`；`collect: [noref_old(retention_expired, 1000), noref_2d(capacity_pressure, 1000)]`；
- `keys_present: {capacity_target_bytes: false, collectable_bytes: false, capacity_gap_bytes: false, note: false}`；
- 顶层键（修前全部 18 个）无一个能直接读出「还差多少」 ⇒ **AC-75「报告须如实给出缺口」字面不可满足** ⇒ **FAIL**。

### 2.2 修后读数（工作副本真跑，同一夹具）：**三个数 ＋ note ⇒ PASS**

CLI `gc --dry-run`（规范形）原文：

```
capacity_gate_triggered : true
capacity_max_bytes      : 6000        capacity_target_ratio : 0.8
capacity_target_bytes   : 4800        （constants.capacity_target_bytes 亦 4800，同值）
collectable_bytes       : 2000
capacity_gap_bytes      : 200         ← **缺口**
usage                   : {"files": 3, "bytes": 7000}
collect                 : [ {rel: 20261011/noref_old.pdf, reason: retention_expired, bytes: 1000},
                            {rel: 20261011/noref_2d.pdf , reason: capacity_pressure, bytes: 1000} ]
exempt                  : [ {rel: 20261011/active.pdf, reason: active_job, bytes: 5000,
                             job_id: obs-active, state: QUEUED} ]
note                    : "可回收不足：可回收 2000 B 已全数列入淘汰，仍高于目标 4800 B ⇒ 仍缺 200 B；
                           ACTIVE 豁免项 5000 B 不参与回收（不越权删）"
```

**`--apply` 输出（与 plan 同源）**：`mode=apply`、`capacity_target_bytes=4800`、`collectable_bytes=2000`、
`capacity_gap_bytes=200`、`note` 同上一字不差；`moved_files=2`（`noref_old` / `noref_2d` 真移入 `inbox/.trash/20261011/`）、
`src_gone={noref_old:true, noref_2d:true, active.pdf:false}`、
`active.pdf sha256 = 3529b45a590b160efc6117a0ee5b467ab377ed0b1f35764aae8c4f61235d878b`（**前后不变**）、
三数 `{jobs:6, job_pages:32, stamps:89}` **前后逐字不变**。

**端点同源（临时 API 实例 `:5198`，独立 inbox / 库 / 端口）**：

| 调用 | 状态 | 缺口三数 | note |
|---|---|---|---|
| `GET /api/jobs/inbox/summary` | 200 | 4800 / 2000 / **200** | 有 |
| `POST /api/jobs/inbox/gc {"apply": false}` | 200（`mode=dry-run`） | **200** | 有 |
| `POST /api/jobs/inbox/gc {"apply": true}` | 200（`mode=apply`、`moved_files=2`） | 4800 / 2000 / **200** | 有 |

端点缺口态下：`active.pdf` sha256 不变（**未被删**）、三数 `{jobs:6, job_pages:32, stamps:89}` 前后不变。

> **不越权删自证**：缺口 > 0 时 `ACTIVE` 项**既不在 `collect` 内、也未被删**（`active_in_collect=false`，
> 且 `active.pdf` 仍在豁免清单 `reason=active_job`）。

---

## 3. 重启载新码自证（单路重启 5196）

- **路径**：`POST http://localhost:5555/api/restart {"sid":"feicui-api"}`（**未用 `pkill` / `killall`、未用 stop→start、未用 startAll**）；
  面板回执 `{"sid":"feicui-api","ok":true,"state":"running","pid":79505,"msg":"已启动"}`；`GET /api/health` 轮询 **0.1 s 内 200**。

| 时点 | 读数 |
|---|---|
| 重启前 PID | **67718**（`lstart = Sun Oct 11 07:06:44 2026`） |
| 重启后 PID | **79505**（`lstart = Sun Oct 11 07:15:46 2026`） |
| `server/app/inbox_gc.py` **mtime** | **2026-10-11 07:14:57** |
| **进程启动 − 源文件 mtime** | **+48.4 s**（`lstart ≥ mtime` ⇒ **新码已载**） |

**端点面（重启前 ⇒ 旧码 / 重启后 ⇒ 新码）**

| 端点 | 重启前（旧码） | 重启后（新码） |
|---|---|---|
| `GET /api/jobs/inbox/summary` | 200，`usage={files:9, bytes:6786}`，**新字段全 false** | **200**，`capacity_target_bytes=42949672960`、`collectable_bytes=6786`、`capacity_gap_bytes=0`、`note=null`（本机 inbox 未超闸 ⇒ 缺口 0，符合定义） |
| `POST /api/jobs/inbox/gc`（空体 ⇒ dry-run） | 200，`mode=dry-run`，**新字段全 false** | **200**，`mode=dry-run`，三个数同上 |

**dry-run 不改盘**：重启后两次调用前后 `inbox` `{files:9, bytes:6786}` 不变。

---

## 4. 红线与不变读数

- **只动文件、不动库**：CLI apply（临时库）与端点 apply（临时实例）前后 `jobs/job_pages/stamps` ＝ `{6,32,89}` 与
  `{6,32,89}` **逐字不变**；生产库本单**零写**（未跑生产 inbox 的 apply）。
- **`ACTIVE` 引用豁免不可绕**：缺口场景下 `active.pdf` 未被删、sha256 不变、仍在豁免清单 ⇒ 未为凑数越权删。
- **未碰**：`docs/**`（规范一字未改）、`xiai/**`、`ctrl/**`、`web/**`（前端本单不需要改）、三采集库与三采集包、
  生产 `inbox/`（只读端点）、`yinpu.db`（未 apply）。
- **无 `pkill` / `killall` / `startAll`**；唯一进程动作 ＝ 面板单路 `restart`；临时验证实例 `:5197`/`:5198` 由脚本自行 `terminate()`，
  现存监听：5196（feicui-api）＋ 5197/5198 均无残留（`lsof` 计数 0）。
- **既有证据脚本无回归**：`ops/job-upload/14_inbox_gc_scenarios.py`（用**旧形** CLI 与 `:5197` 端点）重跑 **exit 0**，S1〜S4 全通过。

---

## 5. 未完成项 ＋ 交 Jing 同步的口径告知（本单不写 `docs/**`）

**未完成项**：无（两条 OBS 均已收口并自证；进程与端点已复核）。

**规范同步建议（供 Jing 走 §0.4；本单未动规范）**——建议在 §3.20.4 / §3.20.5 与 **AC-73 / AC-75** 上各补一句（只增不改）：

1. **§3.20.5 冻结命名行**补：`gc` 为**可选子命令**，`python -m app.inbox_gc gc [--dry-run|--apply]`（冻结形）
   与 `python -m app.inbox_gc [--dry-run|--apply]`（等价省写形）**两种形态都成立、输出逐字段一致**（AC-73 因此两形都可判）。
2. **§3.20.3 R2 或 §3.20.4 dry-run 输出（冻结）行**补三个字段名与语义：`capacity_target_bytes` /
   `collectable_bytes`（容量闸下最多可回收量 ＝ 总量 − `ACTIVE` 引用项体积）/ **`capacity_gap_bytes`（缺口）**，
   并写明「缺口 > 0 ⇒ 另给 `note`；**不得为凑回收量删 `ACTIVE` 引用项**」（AC-75 的「缺口说明」即由此字段与 `note` 承载）。
3. **落地状态**：以上两处均**已落地并自证**（本报告 §1〜§3），非「落地中」。

**另需登记的两点（观察，不判负）**

- `constants.capacity_target_bytes` 与新增顶层 `capacity_target_bytes` **同值并存**（平铺是为了「不必下钻即可读缺口」）；
  若 Jing 认为应只留一处，请裁定后本侧再改（本单不改口径、不删既有键＝不破 AC-76 之外的既有读者）。
- 端点响应顶层 `note` 与**清单项内**的 `note` 同名但**不同层级**（顶层仅缺口说明，且仅在缺口 > 0 时出现）。

---

## 6. 证据文件与提交

| 文件 | 说明 |
|---|---|
| `ops/job-upload/16_inbox_gc_cli_gap_probe.py` | 本单自证脚本（修前/修后 ＋ 缺口场景 ＋ 端点同源，临时目录/临时库） |
| `ops/job-upload/16_inbox_gc_cli_gap_probe_raw.json` | 其原始读数（15 条 verdict 全 PASS） |
| `ops/job-upload/17_inbox_gc_live_recheck.py` | 5196 单路重启 ＋ 新码自证脚本 |
| `ops/job-upload/17_inbox_gc_live_recheck_raw.json` | 其原始读数（8 条 verdict 全 PASS） |
| `server/app/inbox_gc.py` / `server/app/routers/jobs.py` | 本单实现改动（§0） |

**复跑**：

```bash
cd /Users/kevin/bistro/xiai/feicui
./server/.venv/bin/python ops/job-upload/16_inbox_gc_cli_gap_probe.py   # 修前/修后 ＋ 缺口场景（exit 0）
./server/.venv/bin/python ops/job-upload/17_inbox_gc_live_recheck.py    # 面板重启 5196 ＋ 新码自证（exit 0）
./server/.venv/bin/python ops/job-upload/14_inbox_gc_scenarios.py       # 既有场景回归（exit 0）
```

**提交哈希**：`<待填>`（登记见紧随其后的一次小提交）
