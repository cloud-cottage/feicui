# 阶段 1c-激活 · 收尾补齐报告（Kong / 工程师·收尾）

- 落盘：**2026-09-20 15:0x CST**
- 本单定位：**只做收尾补齐**，不重做已成立的工作。上一轮（14:45–14:50）的 e2e / 双起 / 重启验收结论**直接采信**。
- 位置变更：**2026-09-20 14:47 整个 `shu` 工程改名为 `/Users/kevin/bistro/xiai/`**；`~/bistro/shu/` 只剩空 `.vite` 壳（**本单未删**，属搬迁方产物）。
- 正式库（唯一真源）：`/Users/kevin/bistro/xiai/feicui/yinpu.db`
- 面板托管链路：`5164`(印索 shell/vite, cwd=`xiai/web`) → `5195`(feicui 前端 vite, cwd=`xiai/feicui/web`) → `5196`(FastAPI, cwd=`xiai/feicui/server`)

**一句话结论**：六项尾巴 **5 项完成 + 1 项部分**（DOM 证据做成；`ResultsPage.vue` 的**改前** md5 因上一轮从未落盘而**无法复核**，另发现**第三处遗留服务（5361）**不在本单授权范围内、只登记未动）。

---

## 0. 六项尾巴 · 结果速览

| # | 尾巴 | 结果 | 关键证据 |
| --- | --- | --- | --- |
| ① | 补写 `ops/1c/REPORT.md` | ✅ **本文件** | — |
| ② | 补齐所有被改文件**改后 md5** | ✅ 8 个文件全部补齐；`ctrl/index.js` 改前 md5 复核一致 | §2 |
| ③ | 修 `e2e_run.py` 旧路径硬编码 + 最后一次库内复算 | ✅ 改为 `FEICUI_DB` / `FEICUI_API_BASE` 可覆盖；复算 **PASS / inserted=0** | `1c_final_recompute.txt` |
| ④ | 按精确 PID 停 5371 / 5395 并确认无残留 | ✅ 两个端口均 **FREE**、两个 PID 均**不存在**；本单自起的 5371 副本 API 已按精确 PID 停掉 | §3.2 |
| ⑤ | 同步 `web/README.md` 取图口径 | ✅ §4-G-1 与 §5 目录树已改为 **E6 三段正式契约** | §3.3 |
| ⑥ | DOM 级「真实渲染出裁图」证据 | ✅ 自建 headless Chrome + 独立 profile：**20/20 行 `naturalWidth > 0`** | `1c_dom_e6_render.txt` |

---

## 1. 证据索引（`ops/1c/`，逐个一句话）

| 文件 | 一句话 |
| --- | --- |
| `1c_e2e_evidence.txt` | 经 5164 建 job → **人不出手**自动跑完：`QUEUED→RUNNING→DONE 7/7`；重复建同书 `409`；建单前 `stamps=79`。 |
| `1c_after_e2e_evidence.txt` | e2e 之后复核：`stamps` 原 79 行三口径指纹逐字未变；池自检 `prod_db=true`。 |
| `1c_e2e_after_move.txt` | 迁移到 `xiai` 后复跑：`job-6e7471ff…` **DONE 7/7**；但第 ④ 步库内复算因 `DB` 常量仍指旧 `shu` 路径 **崩溃**（`unable to open database file`）——本单 ③ 就是补这一步。 |
| `1c_double_start_evidence.txt` | **双起保护**：人为重复起池 `rc=5`（锁被占＝正常分支）；两单 A/B 并发 **双 DONE**（7/7 与 4/4）。 |
| `1c_jobA_repeat_samples.txt` | 同 job 重复跑的 E2 采样：终态 `detected=29 inserted=0 skipped=29` ⇒ **幂等**。 |
| **`1c_final_recompute.txt`** | **【本单新增】**副本库 + 非登记端口 5371 的最后一次库内复算（**由修复后最终版脚本产出**）：`QUEUED→RUNNING→DONE 7/7`、`409 OK`、复算 `inserted=0 skipped=29`、**`端到端判定=PASS`**。 |
| **`1c_dom_e6_render.txt`** | **【本单新增】**DOM 级证据：结果页 20 行全渲染真实裁图（`naturalWidth>0`），`img.src` 为三段 E6 路径，0 网络失败、0 控制台异常。 |
| `stamps_baseline_idmax79.txt` | 原有行（`id<=79`）指纹**基线**（删除遗孤 job **之前**）三口径 md5/sha256。 |
| `stamps_after_delete_idmax79.txt` | 删除遗孤 job **之后**复核：与基线**逐字相同**。 |
| **`stamps_final_idmax79_after_all_e2e.txt`** | **【本单新增】**所有 e2e / 双起测试**之后**再复核 `id<=79`：三口径指纹**逐字仍相同**（`A_raw_md5=8a21e57d…`、`B_canon_md5=d7abe995…`、`C_free_md5=22bdc0a7…`）。 |
| `orphan_job_delete_evidence.txt` | 遗孤 job 行删除（Kevin 已授权）：删 `jobs=1` + `job_pages=7`，**`stamps` 79→79 未变**（带 sqlite backup API 备份）。 |
| `1c_restart_before.txt` | 面板重启前快照：`index.js md5=90b925d7…`、`12/12 running`、三条 cwd 仍指 `shu`。 |
| `1c_restart_after.txt` | `pm2 restart bistro-ctrl`（**不带 `--update-env`**）+ startAll 后：12/12。 |
| `1c_restart_after_move.txt` | **迁移后**重启验收：`条目=12 running=12 非running={}`，三条 cwd 已改指 `xiai`。 |
| `1c_routes14_after_restart.txt` | 重启后 `yinsuo-web.spec §2.2` 的 **14 条对外路由全 200**（非 200 计数 = 0），feicui 入口 200。 |
| `before_restart.txt` / `after_restart_status.txt` / `before_restart2.txt` / `after_restart2_status.txt` | 13:08–13:16 的面板重启前后快照（含 `5195/5196 listeners=0` 到恢复的过程）。 |
| `lsof_ownership.txt` | 13:09 逐端口 lsof **归属**取证 + `ppid==1` 孤儿巡检。 |
| `probe1_out.txt` | 5164 `/feicui/` 探针：`/feicui/__feicui/backend-probe` **200 JSON `reachable:true`**；E1 建单 201。 |
| `probe2_out.txt` | 探针复测：横幅「后端已连接」与代理目标**同源**，无错报。 |
| `probe3_out.txt` / `probe5_out.txt` | 详情页 E2 **真实进度**采样（浏览器侧），`DONE 7/7`、`DONE 20/20`。 |
| `probe4_out.txt` | 第二次 E1 建单 201（浏览器侧）。 |
| `probe1_create_job.js` / `probe2_create_job_copy.js` / `probe3_progress.js` / `probe4_create_job2.js` / `probe5_progress_live.js` | 上述探针的 **JS 源码**（可复算）。 |
| `cdp_drive.py` | 一次性 CDP 驱动（新建 tab → 导航 → 执行 JS → 打印 console / 网络失败 / ≥400 报表）；本单 ⑥ 复用。 |
| `fingerprint_rows.py` | `stamps` 内容指纹三口径（A raw / B canon / C free），支持 `--id-max N` 证明**原有行未变**；**禁用库文件 md5**（WAL 下会漂）。 |
| `delete_orphan_job.py` | 遗孤 job 行删除脚本（单事务 `BEGIN IMMEDIATE`，带 backup）。 |
| `e2e_run.py` | 端到端采样器（建单 → 409 互斥 → E2 采样 → 库内复算）；**本单修复了它的旧路径硬编码**。 |
| `dom_e6_render.js` | **【本单新增】**DOM 级取图判定的 JS（点齐「取裁图」按钮 → 等 `naturalWidth>0` → 汇总）。 |
| `e2e_double.py` / `wait_running.py` | 双起取证脚本 / 等 RUNNING 的辅助脚本。 |
| `pool_run.log` / `pool_run2.log` / `pool_run3.log` | 早期（13:16–13:18，`var/feicui_work.db`，`prod_db=False`）池自检日志：`DONE 7/7`、`DONE 20/20`。 |
| `shu_web_npm_scripts.txt` | `shu/web`（现 `xiai/web`）npm 脚本实跑记录（`npm run build` exit=0）。 |
| **`1c_cleanup_evidence.txt`** | **【本单新增】**清场取证：5371/5395 已无残留的核验、本单副本 API（pid 64938）三重身份 + 精确 PID 停掉、池/worker 无残留、headless Chrome（70056/9711）停掉、面板 12/12、以及**第三处遗留 5361（pid 28295）只登记未停**。 |

---

## 2. 改动清单（改前 → 改后 md5）

`md5` 一律为 `md5 -q`（本机 BSD），**逐字复核于 2026-09-20 15:0x CST**。

| 文件 | 改前 md5 | **改后 md5** | size | 改动语义（简述） |
| --- | --- | --- | --- | --- |
| `ctrl/index.js` | `90b925d72cd76003f4a2091a89f6e512`（**已复核**：与 `1c_restart_before.txt` 逐字一致） | `143137f25c717596d4a8260db686794f` | 52321 → **52651** | 三条站点 cwd `shu` → `xiai`（**由另一路改**，本单只读复核） |
| `xiai/feicui/server/app/main.py` | *未落盘* | `a46afbbdc0b600e99bea5c724c538eb0` | **6747** | 探针/路由挂载相关（上一轮） |
| `xiai/feicui/server/app/pool.py` | *未落盘* | `56a85b8308c7c0e7b6e3785b904da889` | **29117** | 池：断点续跑 / 单写者锁 / 收尾判定 |
| `xiai/feicui/server/app/poolctl.py` | *未落盘* | `f5a55df8a8144221773445a30691855f` | **10181** | API 侧**按需自动拉起池**（激活单核心） |
| `xiai/feicui/server/app/routers/jobs.py` | *未落盘* | `bc86789264ac5daafc18ae000908a3f9` | **22224** | E1/E2/E3/E5/E6/E7 路由；E6 三段路径 + 头值百分号编码修复 |
| `xiai/feicui/server/app/repository.py` | *未落盘* | `eccba1616a29af866626025c1c6a444c` | **39312** | 库内复算（S-1）/ E7 有效态口径 |
| `xiai/feicui/web/src/api/stampsImage.js` | *未落盘* | `fe6cb3db2fbc2894fcaa88409a1f4aa1` | **7725** | 取图唯一常量源；**三段正式契约** + 废止两段形态 |
| `xiai/feicui/web/src/pages/ResultsPage.vue` | **⚠ 无从复核**（见下） | `b576baaf5d137e38080e2b2887f4f399` | **13551** | 结果页：E3 信封 + E6 取图（不造假图） |
| `xiai/feicui/web/README.md` | —— | `02d885493fe9b36cd7e2ecc4353f59cc` | 9658 → **10595** | **【本单改】**G-1 + §5 目录树 → E6 三段正式契约 |
| `xiai/feicui/ops/1c/e2e_run.py` | —— | `293edda667203bb72908ab93d9b05499` | 6019 → **6650** | **【本单改】**去绝对路径硬编码（`FEICUI_DB` / `FEICUI_API_BASE`） |
| `xiai/feicui/ops/1c/REPORT.md` | —— | `（本文件）` | —— | **【本单新增】** |

### 2.1 关于「改前 md5 未复核」的如实说明

- 全树搜索（`grep -rn` 于 `xiai/**` 的 `*.txt/*.md/*.json`）后确认：**上一轮只把 `ctrl/index.js` 的改前 md5 落了盘**（`ops/1c/1c_restart_before.txt`）。
- **`ResultsPage.vue` 的改前 md5 从未落盘**——`feicui/web/evidence-proxy/fix-1c/md5-before.txt` 覆盖的是 `router/index.js` / `config/env.js` / `vite.config.js`，**不含** `ResultsPage.vue`。
  ⇒ **无法复核**，只能给改后 md5。此不足**如实登记**，不用"看起来合理"的值填充。
- 其余 6 个 `server/app/**` 与 `stampsImage.js` 的改前 md5 同样**未落盘**，一并如实标注（不给臆测值）。

---

## 3. 逐项结果

### 3.1 ③ `e2e_run.py` 旧路径硬编码 —— 已修

**病**：`DB = "/Users/kevin/bistro/shu/feicui/yinpu.db"` 写死 —— 迁移后该路径已不存在，导致 `1c_e2e_after_move.txt` 第 ④ 步 `sqlite3.OperationalError: unable to open database file`。

**修**（`ops/**` 内，最小改动）：

```python
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "yinpu.db"   # ops/1c → feicui/yinpu.db
BASE = os.environ.get("FEICUI_API_BASE", "http://localhost:5164/feicui/api")
DB   = os.environ.get("FEICUI_DB", str(_DEFAULT_DB))
```

- 顺带修了第 ① 步那句**写死的**日志文案（原样打印 `BASE`，避免用 `FEICUI_API_BASE` 自测时**谎报链路**）。
- 语法校验：`ast.parse` OK。

### 3.2 ③ 最后一次库内复算 —— **PASS，`inserted=0`**

**做法（严格守硬约束）**：**不碰正式库** —— 用 `sqlite3 .backup` 造 WAL 一致副本 `/tmp/feicui_1c_final2.db`（stamps=89 / jobs=5 / job_pages=32），在**非登记端口 5371** 起一次性副本 API（`FEICUI_DB=/tmp/feicui_1c_final2.db`，pid 85491），再把采样器指过去。
（首次复算用 `/tmp/feicui_1c_final.db` + pid 64938 已 PASS；因该次产出的日志文案是**改文案之前**的旧版，遂**用最终修订的脚本重跑**，下表与 `1c_final_recompute.txt` 均为**重跑**结果。）

| 项 | 实测 |
| --- | --- |
| 建单 | `POST /api/jobs` → **201** `job-2d2f0cea4d5c4df0ac5311cc33dbc41c`，`total_pages=7` |
| 重复建同书 | → **409** `ACTIVE_JOB_EXISTS`（带既有 job_id） |
| 自动执行链 | `QUEUED → RUNNING → DONE 7/7`（**人不出手**，池由 API 自动拉起；采样 7 点） |
| 库内复算 | `total=7 done=7 failed=0 detected=29` **`inserted=0`** `updated=0` `skipped=29` `ocr_empty=2` |
| 幂等判定 | **`端到端判定 = PASS`，RC=0** |
| 副本库 `stamps` | 89 → **89**（跑完未增一行） |
| 池收尾 | `pool.state.json`：`reason=stopped`、4/4 worker `alive=false`、`inserted=0` |

**另一条补做**：把 `1c_e2e_after_move.txt` 崩掉的第 ④ 步**用只读查询补齐**（同一 job `job-6e7471ff9c464695b9463cdad5122246`）：`state=DONE`、`total=7 done=7 failed=0 detected=29` **`inserted=0`** `skipped=29` `ocr_empty=2` ⇒ 迁移后那一单同样是**幂等 PASS**。

**正式库零写入证明**：复算前后正式库 `stamps=89 / jobs=5 / job_pages=32` **完全一致**。

### 3.3 ④ 清场 —— 5371 / 5395 已无残留

- **上一轮的两个测试服务已不存在**：`ps -p 49149` → **NOT FOUND**；`ps -p 49563` → **NOT FOUND**；`lsof -iTCP:5371 / :5395` → **无监听**。本单未发现需再停的 5371/5395 进程。
- **本单自起的 5371 副本 API**（`pid 64938`，三重身份已核：`ps` 命令为 `./.venv/bin/python -m app.main`、cwd=`xiai/feicui/server`、env 含 `FEICUI_DB=/tmp/feicui_1c_final.db`）已按**精确 PID** `kill -TERM` 干净退出 → 端口 **FREE**。
- **全程未用 `pkill -f`**（符合硬约束）。
- **无残留池 / worker**：本单池自行收尾（`pool.state.json` 内 `"reason":"stopped"`、4 个 worker `alive:false`、`db=/private/tmp/feicui_1c_final.db`）；全机扫描无 `app.pool` 进程。自建 headless Chrome（pid 70056）亦按精确 PID 停掉，**9711 FREE**，临时 profile 已删。
- **面板未受影响**：`/api/status` → **条目=12 running=12 非running=[]**；`shu=5164 / feicui-api=5196 / feicui-web=5195` 三条 cwd 均指 `xiai`。**本单未启停面板**（无需重启）。

> ⚠️ **另发现第三处遗留（不在本单清单内，只登记未动）**：`pid 28295` 仍监听 `127.0.0.1:5361`，cwd=`xiai/feicui/server`，env 指向**旧 `shu` 路径**的 QA 临时库
> `…/shu/feicui/qa-recheck/p1bii-neng/evidence/run/tmpdb/neng.db`（起于 13:12:50）。**归属 Neng 的 QA 证据**，非本单授权范围，**未停**——见 §4 待裁。

### 3.4 ⑤ `web/README.md` 取图口径 —— 已同步

| 位置 | 改前 | 改后 |
| --- | --- | --- |
| §4 **G-1** | 「**临时取图端点，待规范收口**」+ 两段路径 `/api/jobs/{job_id}/stamps/{idx}/image` + 「**待 Zang / Kevin 裁定后收口**」+「临时取图端点未实现」 | 「取印面裁图 = **E6**，**已收口为正式契约**」+ **三段**路径 `/api/jobs/{job_id}/stamps/{page}/{idx}/image`，契约依据 **spec v1.3 §3.5 + §3.1**，含 `page` 1-based / `idx` 0-based、`200/400/404/500` 口径、**两段形态已废止**、**为何必须带 `page`**（行级唯一锚 `(pdf_name,page,idx)`，`idx` 页内不唯一）、一处收口纪律 |
| §5 目录树 | `stampsImage.js（**临时取图端点，待规范收口**）` | `stampsImage.js（**E6 取图契约：3 段正式路径**）` |

**校验**：源码侧 `grep` 确认 Web 工程内已无「临时取图端点 / 待规范收口」残留措辞（本次只改文档，未碰 `src/**`）。

### 3.5 ⑥ DOM 级「真实渲染出裁图」—— **做成**

上一轮因用户 Chrome 占用未能 attach；本单改用**自建 headless Chrome + 独立 profile**（`--headless=new --remote-debugging-port=9711 --remote-allow-origins=*`，profile 在 `/tmp`），复用 `cdp_drive.py` 驱动。

页面：`http://localhost:5164/feicui/jobs/job-6e7471ff9c464695b9463cdad5122246/results`

| 项 | 实测 |
| --- | --- |
| E3 items 行 | **20** |
| 「取裁图」按钮 / `img.stampimg` | **20 / 20** |
| **`naturalWidth > 0`** | **20 / 20** ⇒ **真实渲染出裁图**（不再出现「裁图不可用」） |
| `img.src` 形态 | `/feicui/api/jobs/{job_id}/stamps/{page}/{idx}/image`（**三段**，与 E6 契约一致） |
| 尺寸样本 | `123x122, 142x145, 92x70, 321x261, 158x158 …`（真实像素解码成功） |
| 真图文案 | 「**真实裁图 · image/png · output/pairs/p13_0/stamp.png**」（`x-feicui-img-path` 已还原） |
| 控制台异常 / 网络失败 | **0 / 0**（仅 2 条 vite debug；唯一 ≥400 是 `favicon.ico` 404，与本工程无关） |
| 「裁图不可用」字样 | **仅 1 处**，出现在**取图契约说明段**（"取图失败一律如实显示…"），**非**任何行的取图状态 ⇒ 无一行落入 unavailable 分支 |

**旁证（协议层）**：E6 三段 `curl` → `200 image/png`、`Content-Length: 27958`、`x-feicui-img-path: output/pairs/p13_0/stamp.png`；**废止的两段形态 `…/stamps/0/image` → `404`**（后端不两套并存，与文档承诺一致）。

---

## 4. 风险与待裁

1. **【高风险｜需裁定】正式库 `stamps` 已被上一轮测试写入：79 → 89 行。**
   - 原因：14:45–14:50 的 e2e / 双起测试**走的是面板托管链路 + 正式库**（`prod_db=true`），与「不得向正式库写 `stamps`」的纪律冲突。
   - 新增行 **`id=80..89`**（内容为真实新印面，**非污染**）：`tmp.pdf p14 idx6`（1 行，14:45 e2e `inserted=1`）；`秦汉印典 …ok.pdf p5 idx6–11 / p6 idx6–8`（9 行，14:47 双起第二单 `[5,8]`）。
   - **原有 79 行三口径指纹逐字未变**（本单复核，证据 `stamps_final_idmax79_after_all_e2e.txt`）⇒ 无篡改，只有**净增**。
   - 待裁：**保留**（视为有效新数据）还是**回退删 `id>79`**（可逆：`…/yinpu.db.bak-1c-before-delete-20260920144430` 为改动前快照）。**本单未动任何正式库行。**
2. **【中】正式库 `jobs` 残留 5 条 DONE 行 / `job_pages` 32 行**（`job-502016dd…` / `job-ccb79b59…` / `job-20e180ea…` / `job-f34120a8…` / `job-6e7471ff…`），全部 `state=DONE`、无活跃 job。其中 4 条 `pdf_path` 仍写**旧 `shu` 路径**。待裁：是否清掉当作测试痕迹。
3. **【中】第三处遗留服务 `pid 28295` @ `127.0.0.1:5361`**：cwd=`xiai/feicui/server`，库/faces/export 全指**旧 `shu` 路径**下的 `p1bii-neng` QA 临时目录（该目录已随改名失效）⇒ 实为**僵尸服务**。归属 Neng 的 QA 证据，**未停**，待授权。
4. **【低】其他遗留调试实例**（均非本单产生，未动）：CDP `9333`/`9462`/`9471`（cwd 在 `qa-recheck/m1-p3{b,c,d}-neng`）。
5. **【低】`web/README.md` 内仍有多处 `/Users/kevin/bistro/shu/...` 旧路径**（§1 的 `cd` 命令、§6 的历史性「未改动」陈述）。本单按任务**只同步取图口径**，未越界改路径——建议并入 Zang/Jing 的文档收口一轮统一改 `shu → xiai`。
6. **【低】`ctrl/index.js` 的三条 cwd** 由另一路改指 `xiai`（本单只读复核 md5），与本单无冲突。

---

## 5. 未完成项 / 明确未做

| 项 | 状态 | 原因 |
| --- | --- | --- |
| `ResultsPage.vue` 等 7 个文件的**改前 md5 复核** | **未完成** | 上一轮**从未落盘**，全树搜索确认无记录 ⇒ 无基线可比，不以臆测值填充 |
| 停 `pid 28295`（5361） | **未做** | 不在本单清单（5371/5395）且属 **Neng 的 QA 证据**，需授权 |
| 清理正式库 `id>79` 的 10 行 / 5 条 jobs | **未做** | 属**数据裁定**，需 Kevin/Zang 授权（硬约束只允许改代码与 `ops/**`） |
| `web/README.md` 其余旧 `shu` 路径 | **未做** | 超出本单「取图口径」范围 |
| 重跑面板重启（12/12） | **不必** | 本单未启停面板；`/api/status` 现测已 **12/12 running** |
| 删除 `~/bistro/shu/` 空 `.vite` 壳 | **未做（按令保留）** | 属搬迁方产物；实测仍在（`shu/web/.vite`、`shu/feicui/web/.vite`） |

---

## 6. 硬约束遵守情况（自证）

| 约束 | 本单实况 |
| --- | --- |
| 只改 `ops/**` / `server/app/{main,pool,poolctl,routers/jobs,repository}.py` / `web/README.md` / `ctrl/index.js` | ✅ 本单**只落在允许面内**：写 `web/README.md` + `ops/1c/` 下 6 个文件（`REPORT.md`、`e2e_run.py`、`1c_final_recompute.txt`、`1c_dom_e6_render.txt`、`1c_cleanup_evidence.txt`、`stamps_final_idmax79_after_all_e2e.txt`、`dom_e6_render.js`）；`ctrl/index.js` 与 6 个 `server/app/**`、`src/**` **仅只读复核 md5，未再审改** |
| 不改 `docs/**`、`migrations.py`、`worker/**`、`processor.py/export.py/app.py`、`labeling/**`、`spike-ocr/**`、`qa-baseline|recheck/**`、`mockups/**`、`xiai/web/src/**` | ✅ 未碰。mtime 佐证：`migrations.py 11:51`、`processor.py 10:07`、`export.py 09:03`、`app.py 09-17`；`docs/xiai-plan.md` 的改动属 Jing 本轮 |
| 不停面板托管的 `5195/5196/5164/5555`；不启停面板 | ✅ 未停、未重启；现测 12/12 running |
| 不向正式库写 `stamps`；要测就用副本 + 非登记端口 | ✅ 本单全部测试写 `/tmp/feicui_1c_final.db`；正式库复算前后 `stamps=89` 不变 |
| 不占 `5173/5174` | ✅ 用了 5371（上一轮已用过的非登记端口）+ 9711（CDP 调试口），均已释放 |
| **严禁 `pkill -f`** | ✅ 未使用；全部按**精确 PID**（先 `ps -p` + `lsof -a -p … -d cwd` + env 三重身份核对）停 |
| 不删 `~/bistro/shu/` 的 `.vite` 壳 | ✅ 仍在 |

---

*报告完 · Kong（工程师·收尾）· 2026-09-20*
