# feicui 读接口层（阶段 1b-ii）交付报告（Kong）——**收尾单**

| 项 | 值 |
| --- | --- |
| 时点 | 2026-09-20 12:4x–13:0x（Asia/Shanghai；ISO 戳见各节） |
| 规范 | `../docs/feicui.spec.md` **v1.2**（md5 `6dbe0b3c915d7f8ed43576a00122dcf1`，521 行；**本单未改**，mtime 2026-09-20 12:10） |
| 交付目录 | `/Users/kevin/bistro/shu/feicui/server/**`（改 3 个文件 / 新增 2 个文件，见 §7） |
| 本单性质 | **收尾单**：不改已完成的 E3/E4/E6 三个路由与 E7 的形状，只做「① 修 E7 `page` 真缺陷 ② 夹具护栏 ③ 补本报告」＋ Zang 追加三项（D-1 / D-2 / O-5） |
| 权威自测 | `server/selftest/verify_1b_ii.py`（含本节新增六条护栏） |
| 终态结论 | **`PASS=143  FAIL=0`（`exit 0`）**，9/9 子段全跑、全量断言命中（未运行断言 0 条），见 §3.1 |
| 派单方独立复核 | E7 修复已由 Zang 用独立探针（自有临时副本库 / 5351 端口 / 精确 PID 停服务）复核**通过**；本单不再复验（只照录，见 §1.7） |

---

## 0. 结论速览（一句话一条）

1. **E7 有真缺陷，且是两处**：① 路由/仓库层**根本没有 `page` 形参** ⇒ `?page=N` 被框架静默丢弃，`page=1..N` 永远返回同一份第一页；② 游标路径把 keyset `WHERE` 与 `OFFSET` **叠加**（重复跳过）⇒ 第 2 页起恒返 0 条，而 `has_more` 仍为真 ⇒ 信封出现 `has_more=true, next_cursor=null` ⇒ **客户端（含自测夹具）死循环**。两处都已修，见 §1。
2. 上一轮 54,347 行失控的机理**已闭环复现并定位到行**：54,256 次 `GET /api/jobs?limit=2` 与 54,254 次 `GET /api/jobs?limit=2&cursor=<同一游标>` 交替（API 访问日志佐证），每次第二页都触发同一条 `FAIL 4.4 E7 has_more↔next_cursor 一致：page=2`。见 §1.3。
3. 夹具已加**六条护栏**（硬上界 / 游标推进中止 / 折叠计数 / 信封与 job_id 守卫 / `finally` 清理 / 动态端口）＋ O-5 的「断言总数」闸门，见 §2。
4. 夹具本身还有**三处笔误级缺陷**（`ckT` 类型、回归臂页区间、E3/AC-08 循环无护栏），一并修正并单列口径表（**原判据 → 新判据 → 为何原来是错的**），见 §2.6。
5. `FAIL 7.7 detected=0` **定性为夹具取样错误，不是真回归**（原始证据见 §3.6）：该臂写死 `page_range=[1,2]`，而 `tmp.pdf` 的印面只在 **13–19 页**、库内 1–2 页**一行都没有**。
6. 红线全绿：`stamps` **10 列 / 79 行 / 三口径指纹逐字节未变**；`exports/` 仍 **12 个 `fb_*` + selfcheck_report.json（197 文件 md5 全等）**；`output/` 仍 **80 文件 / 49 webp**；`migrations.py`（mtime 11:51）、`worker/**`（12:40 后 0 个文件被写）、`docs/feicui.spec.md`、`shu/web`、`feicui/web`、`ctrl/**` **本单未写一个字**。见 §6。
7. 未完成项与规范缺口**如实单列**（§4 / §5），其中含两条需要规范侧裁定的**新观测**（E7 排序键、同区间重解析行数 +1）。

---

## 1. 【修产品】E7 `page` 参数失效（真缺陷）

### 1.1 症状（派单方独立实测 + 本单独立复现，两个证据源一致）

| 来源 | 现象 |
| --- | --- |
| Zang 独立实测（12:49 版代码） | `GET /api/jobs?limit=1&page=2` 与 `page=3` **都返回 `page=1` 的同一份数据** ⇒ `page` 被忽略 |
| 本单复现（改前探针，证据 `44_e7_page_probe_BEFORE.json`） | `total=5, limit=1` 下 `page=1..7` **七页全同**：`page` 恒 1、`items` 恒 1、`has_more` 恒真、`next_cursor` 恒为第一个 job 的游标 |

### 1.2 根因①：`page` 形参不存在（`?page=` 被 FastAPI 静默丢弃）

* 修前 `server/app/routers/jobs.py::list_jobs` 的签名只有 `state / limit / cursor`；`server/app/repository.py::jobs_page` 同样没有 `page` 形参 ⇒ **未知查询参数被框架忽略，不报错**。客户端传 `?page=2` 收到 200 + 第一页，**没有任何错误信号**。
* 修后：`page` 进入签名并**与 E3 完全同款**——1-based、`page` 与 `cursor` **互斥**（同给 ⇒ `400`）、非法值 ⇒ `400`、**超出末页 ⇒ 空 `items` + `has_more=false`**（绝不回吐第一页）。

### 1.3 根因②：游标路径「keyset `WHERE` + `OFFSET`」叠加 ⇒ 0 条 / 死循环（上一轮 54k 行的机理）

修前 `jobs_page` 的游标分支长这样（**两个跳过条件同时生效**）：

```sql
-- keyset 条件已把结果集定位到「游标行之后」…
WHERE (j.created_at > ? OR (j.created_at = ? AND j.job_id > ?))
-- …却又按「游标行之前的行数」再跳一次（重复跳过）
ORDER BY j.created_at, j.job_id LIMIT ? OFFSET ?
```

⇒ 第 2 页起恒返 **0 条**，而 `has_more = (offset + 0) < total` 仍算出 **真**，`next_cursor` 因「本页无末行」得不到 ⇒ 返回 **`has_more=true, next_cursor=null`**。夹具原判据是 `if not body["has_more"]: break` ⇒ 永不成立、`cursor=None` 又回到第一页 ⇒ **死循环**。

**闭环证据（上一轮那次失控）**：

* 输出：`server/selftest/evidence/1b_ii/00_console.log` = **54,347 行**，其中 `FAIL 4.4 E7 has_more↔next_cursor 一致：page=2` **54,254 条**（同一条断言重复）；
* 服务端访问日志（`main_api.log`）按请求去重计数：`GET /api/jobs?limit=2` **54,256** 次、`GET /api/jobs?limit=2&cursor=WyIyMDI2LTA5LTIwVDEyOjUxOjEyKzA4OjAwIiwiam9iLTUxM2M2YTNlYzNjMzQ2YmM5ZTI0NGRkNzM2YWNlZWI4Il0` **54,254** 次 ⇒ **一页有行、一页 0 行地交替**，与「`?limit=2` 出第 1 页（有行、给游标）→ 带游标出第 2 页（0 行、`has_more=true`、游标为 null）→ 回到第 1 页」完全吻合；
* 本轮我在**进程内**用同一份代码 + 同一批 job 复现了该信封（`page2: {'total': 4, 'offset': 2, 'page': 2, 'has_more': True, 'next_cursor': None}`，`items=[]`），并单独验证了「keyset 命中的就是那 2 行、被 `OFFSET 2` 全部跳过」⇒ 0 行的直接成因。

### 1.4 修法（3 处改动，见 §7 的 md5）

| # | 位置 | 改动 |
| --- | --- | --- |
| 1 | `server/app/routers/jobs.py::list_jobs` | 新增 `page` 查询参数；`page`+`cursor` 同给 ⇒ 400；`_int_param(page, minimum=1)`；`state` 校验保持 400；透传 `page` |
| 2 | `server/app/repository.py::jobs_page` | 新增 `page` 形参；**游标分支只发 `LIMIT`**（`offset` 仅用于回填 `page`）；页码分支 `offset=(page-1)*limit`（越界自然得到空页） |
| 3 | `server/app/repository.py::jobs_page` 尾部 | 结构性保证 `has_more == (next_cursor is not None)`：`has_more=true` 而本页无行 ⇒ 强制 `has_more=False`（**这是死循环的根治闸门**） |

`E3`（`stamps_page`）**一行未动**——它本来就是「游标分支不发 OFFSET」的正确写法，现 E7 与之同款。

### 1.5 修复前后**完整翻页表**（真跑：`server/selftest/probe_e7_page.py`）

探针设定（比真实使用更严）：临时副本库（backup API 一致快照）、**5 个 job**、`limit=1`、并**刻意把 5 个 job 的 `created_at` 抹平成同值**（`2026-09-20T00:00:00+08:00`）⇒ 排序只能靠 `job_id` 决胜，是最容易出错的情形；端口动态探测（5341/5342）、按精确 PID 停服务、`finally` 删临时库。

**改前（`44_e7_page_probe_BEFORE.json`）——页码路径 `page=1..7` 七页全同：**

| 请求 | 报回 `page` | `items` | `has_more` | `has_more == (next_cursor is not None)` | `next_cursor` |
| --- | --- | --- | --- | --- | --- |
| `?limit=1&page=1` | 1 | 1 | true | true | `…job-287df38d…`（第 1 个 job） |
| `?limit=1&page=2` | **1** | 1 | true | true | **同一个**游标 |
| `?limit=1&page=3` | **1** | 1 | true | true | 同上 |
| `?limit=1&page=4` | **1** | 1 | true | true | 同上 |
| `?limit=1&page=5` | **1** | 1 | true | true | 同上 |
| `?limit=1&page=6` | **1** | 1 | true | true | 同上 |
| `?limit=1&page=7` | **1** | 1 | true | true | 同上 |

（判定：`page_path_no_overlap_no_miss=False`、`page_path_no_duplicates=False`、`beyond_last_page_ok=False`）

**改前游标路径：** `page=1`(1 条) → `page=2`(1 条) → `page=4`(**0 条, has_more=true, next_cursor=null**) → 探针的「② 游标推进护栏」命中并中止（原文：`has_more=true 但 next_cursor=null（客户端会死循环）`）。

**改后（`45_e7_page_probe_AFTER.json`）——页码路径全表（题目要求的 ① ②）：**

| 请求 | 报回 `page` | `items` | `has_more` | `has_more == (next_cursor is not None)` | `next_cursor` |
| --- | --- | --- | --- | --- | --- |
| `?limit=1&page=1` | 1 | 1 | true | true | `…job-04867102…` |
| `?limit=1&page=2` | 2 | 1 | true | true | `…job-5fdf0598…` |
| `?limit=1&page=3` | 3 | 1 | true | true | `…job-61a0a024…` |
| `?limit=1&page=4` | 4 | 1 | true | true | `…job-91319de6…` |
| `?limit=1&page=5` | 5 | 1 | **false** | true | **null** |
| `?limit=1&page=6`（超末页） | 6 | **0** | **false** | true | **null** |
| `?limit=1&page=7`（超末页） | 7 | **0** | **false** | true | **null** |

**改后游标路径（`limit=1`）：** `page=1`(1) → `page=2`(1) → `page=3`(1) → `page=4`(1) → `page=5`(1, `has_more=false`, `next_cursor=null`)，**与页码路径逐页同构**。

**改后判定（三个必答项）：**

| 判据 | 结果 | 含义 |
| --- | --- | --- |
| `page_path_no_overlap_no_miss` | **True** | 页码路径 key 集合 == 库内 `ORDER BY created_at, job_id` 全集（题目 ③ 的前半） |
| `cursor_path_no_overlap_no_miss` | **True** | 游标路径同全集 |
| `page_path_equals_cursor_path` | **True** | **两路 key 集合完全相等**（题目 ③）——不重叠、不遗漏、不重复 |
| `beyond_last_page_ok` | **True** | **超末页返回空 `items` 且 `has_more=false`，不再吐第一页**（题目 ②） |
| `page_path_no_duplicates` / `cursor_path_no_duplicates` | **True** / **True** | 两路各自无重复 |
| `cursor_guard_broken` | **None** | 游标推进护栏未被触发（无死循环前兆） |

### 1.6 夹具内的同款回归判据（已进 `verify_1b_ii.py`，随每轮自测复跑）

`4.11` 逐页「报回页号 == 请求页号 且 `has_more↔next_cursor` 一致」、`4.12` 页码路径 no-overlap/no-miss、`4.13` 两路 key 集合相等、`4.14` 超末页空 `items`、`4.15` **`page=2` 与 `page=1` 内容必须不同（原缺陷回归判据）**、`4.16` `page=0 ⇒ 400`、`4.17` `page` 与 `cursor` 同给 ⇒ 400。终态实测（§3.1）：**全部 PASS**，例如
`4.11 …：[(1, 1, True), (2, 2, False), (3, 3, False), (4, 4, False)]`、
`4.14 …：[(3, 0, False), (4, 0, False)]`、
`4.15 …：page1=['job-879526c0…', 'job-2f6c054f…'] page2=['job-57830983…', 'job-a5f7d511…']`。

### 1.7 派单方独立复核（照录，本单未复验）

Zang 用**自有探针**（自有临时副本库、5351 端口、按精确 PID 停服务）复核结论＝**修好了**：`limit=1` 逐页 `page=1→1(1 条, True)` / `2→2(1 条, True)` / `3→3(1 条, False, next_cursor=None)` / `4→4(0 条, False)` / `5→5(0 条, False)`；`has_more == (next_cursor is not None)` 全成立；**超末页返回空 `items`（不再吐第一页）**；页码路径与游标路径各得 3 个互异 job；含中文书名的建单全部 201（响应头修复生效）。⇒ 本报告据此写「修产品：E7 `page` 生效；派单方独立复核通过」。

---

## 2. 【修夹具】`selftest/verify_1b_ii.py` 六条护栏 ＋ O-5 总数闸门

### 2.1 为什么必须加（不是洁癖，是事故复盘）

夹具**自己**放大了一次服务端缺陷：服务端给出「真而无游标」的信封时，夹具的停止条件 `if not body["has_more"]: break` 永不成立，于是把一条 FAIL 打印了 54,254 次、把证据文件写成 2.8 MB、最终被 SIGTERM 杀掉 ⇒ **那一轮的结论全部作废**。护栏的目标是：**任何一次服务端异常都必须在 1 条 FAIL 内收敛**。

### 2.2 六条护栏（逐条对应派单要求）

| # | 要求 | 实现（`verify_1b_ii.py`） |
| --- | --- | --- |
| ① | 翻页循环**硬上界**（`ceil(total/limit)+2` 或 50） | `page_cap(total, limit, extra=2, cap=50)`；E3 逐书用 `page_cap(该书页区间行数, LIMIT)`，E7 用 `page_cap(total_jobs, 2)`，AC-08 用 `page_cap(行数, 50)`；循环体用 `for _i in range(cap)` + `for…else` 命中上界即登记 |
| ② | 游标不推进 / `has_more` 为真而 `next_cursor` 为空或与上页相同 ⇒ **立即 break 并只报一条 FAIL（附两页原始报文）** | `cursor_step(prev, body, seen, raw) -> (next_cursor, 中止原因)`；三处游标循环（E3 / E7 / AC-08）统一调用；中止时 `ckT(..., False, why)` 且 `why` 内含**原始报文片段**（`_short(raw, 400)`） |
| ③ | 同一断言重复命中**折叠计数** | `_record_fail()`：同一 `(断言名, 判据)` 逐条打印至多 `FOLD_PRINT_CAP=3` 次，第 3 次后打印一条 `FOLD …` 公告，其余只累加 `FOLDED_FAILS`；**收尾必出** `97_fail_folds.json`（按命中次数降序）＋ 控制台汇总 ⇒ 重复失败不刷屏、但**绝不静默** |
| ④ | `job_id` 为 None / 响应不是信封 ⇒ **显式 FAIL 并中止该子段**（不产级联 FAIL） | E7 子段：`e7_ok` 守卫（200 + 是 dict + 有 `items` + 六字段封闭 + `items` 非空 + 每条 `job_id` 非空）；任一不成立 ⇒ 一条 FAIL + `say("✗ E7 子段中止…")` + `41_e7_pagination.json` 记 `aborted`，**不再往下产出断言**。E3/AC-08 子段同款（非信封 ⇒ 一条 FAIL + `break`） |
| ⑤ | `finally` 清理（停自己的服务、删临时库） | `__main__` 的 `finally`：三重身份校验（端口 listener + 本仓 `server/.venv/bin/python -m app.main` + `ps` 命令行）后**按精确 PID** `TERM`→`KILL`；等端口释放并落证 `96_cleanup.json`（`killed_by_exact_pid` / `ports_released`）；`rmtree` 只删自己 `mkdtemp` 出来且名字以 `feicui_1bii_` 开头的目录 |
| ⑥ | **不写死端口**（自己探测空闲端口，开头断言无监听） | 原有 `pick_free_port()` 保留并**判据化**：`0.9`/`0.10` 断言 main/reg 端口均无监听；端口从 **5321** 起探测，硬跳过 5164/5195/5196/5555/5173/5174。**全程无 `pkill -f` / `killall`** |

### 2.3 O-5：断言总数闸门（防「假绿」）

* `ASSERT_HITS` 记录**实际运行过的断言名**；收尾新增四条：
  * `9.1 断言总数 == 预期（PASS+FAIL，防「未运行的断言静默消失」）` ← `EXPECTED_ASSERTIONS = 139`（标定自实测跑通的那一轮，脚本内已注明「改任何断言必须同步改此数」）
  * `9.2 全流程跑到收尾（无中途静默终止）`（`END_REACHED`）
  * `9.3 子段齐全（9 个子段全部进入过）`（`section()` 登记，实测 9/9）
  * `9.4 无未收敛的游标护栏命中`
* **为何需要**：原脚本在中途终止时会**安静地少跑几条**而仍可能报 `FAIL=0`；`9.1` 的值若不等于实测总数即 FAIL。**标定过程本身可自证**：标定前那轮（`98c_run2_calibration_console.out`）`9.1` 报 `expect=0 got=139`，说明闸门真的会响（不是摆设）。

### 2.4 本轮「失败 → 收敛」实测（护栏有效性）

| 轮次 | 结果 | 说明 |
| --- | --- | --- |
| 上一轮（夹具修复前） | 54,347 行 / 54,254 条重复 FAIL | 无护栏 ⇒ 失控（证据 `98_run1_E7runaway_console.log`） |
| 本单 run1（加护栏后、夹具三处笔误未修） | **125 PASS / 1 FAIL**，脚本在第 7.10 处 `TypeError` 异常终止 | 护栏把「死循环」压成 1 条 FAIL；暴露出 3 处**夹具自身**缺陷（§2.6）⇒ 证据 `98b_run1_after_guard_console.out` |
| 本单 run2（夹具笔误修完） | **142 PASS / 1 FAIL`**，唯一 FAIL 是 `9.1` 的标定占位（`expect=0 got=139`） | 标定轮 ⇒ 证据 `98c_run2_calibration_console.out` |
| 本单 run3（终态／官方轮） | **`PASS=143 FAIL=0`，`exit 0`** | 9/9 子段、全量断言命中 ⇒ 证据 `98d_run3_official_console.log` / `98e_run3_official_console.out` |

### 2.5 顺带修正的恒真判据（原脚本的断言写法）

* E7 原来在循环内**只在失败时**调用 `ckT(..., False, …)` ⇒ 若接口全对，**这条断言一次都不会运行**（`4.4` 的“通过”无从体现，且失败时无限刷屏）。现改为：循环内只在**不一致时**记 FAIL（同判据），把「收敛性」单独交给 `4.4c`（总是运行）与收尾 `9.4`。

### 2.6 【单列一节】本单修改的测试口径 / 夹具改动（原判据 → 新判据 → 为何原来是错的）

| # | 项 | **原判据** | **新判据** | **为何原来是错的** |
| --- | --- | --- | --- | --- |
| 1 | E7 游标循环终止 | `while True` + `if not body["has_more"]: break` | `for _i in range(page_cap(total, limit))` ＋ `cursor_step` 三条件（`has_more` 为假 / `next_cursor` 为空 / 游标重复）任一命中即 break，只报一条 FAIL（含原始报文） | 原终止条件**依赖服务端自洽**：服务端给 `has_more=true, next_cursor=null` 时条件永不成立、`cursor=None` 回到第一页 ⇒ 死循环（实测 54,254 条重复 FAIL）。**夹具不得把「被测方的自洽」当成自己的终止条件**。 |
| 2 | E3 游标循环终止 | `while True` + `seen_cursors` 回环检测（`cursor in seen` 才 break） | 同 ①：硬上界 + `cursor_step` | 回环检测只覆盖「游标**重复出现**」；**漏掉了 `next_cursor=None` 这一支**（`None` 从不进入 `seen`）⇒ 服务端若给出「真而无游标」的信封，E3 循环同样会死循环。E3 服务端行为本身是对的，但**夹具的洞是真的**（同一缺陷在 AC-08 循环里更隐蔽：无输出、纯卡住）。 |
| 3 | AC-08 循环（`?limit=50` 全量覆盖） | `while True`，无任何护栏 | 硬上界 + 非信封守卫 + `cursor_step` 推进护栏 | 原循环**没有任何输出**，一旦服务端不收敛，表现为「脚本卡住」而不是「报错」——**最难诊断的一种失败**。 |
| 4 | 重复 FAIL 的输出 | 每次命中各打印一行 | 同一 `(断言名, 判据)` 打印 ≤3 次，之后折叠计数，收尾出 `97_fail_folds.json` ＋ 汇总行 | 同一条判据重复 5.4 万次会把**其他所有证据**挤出日志（2.8 MB / 54k 行），并使证据文件不可用。折叠**不降低严格性**（计数照记、收尾照报）。 |
| 5 | 非信封 / `job_id` 为空的响应 | 无守卫：`body["items"][0].keys()` 直接取（`body` 非 dict 时抛异常、`job_id=None` 时带着脏值继续断言） | `e7_ok` 守卫：一条 FAIL + **中止该子段** + 证据文件记 `aborted` | 原写法会**级联**：一条前置异常（或 1 个 `None`）会把后续 N 条断言全部染成假 FAIL/假 PASS，真缺陷被淹没。 |
| 6 | 回归臂页区间 | 写死 `page_range=[1, 2]`（tmp.pdf） | 取**该书的真实页跨度**：`_tmp_lo/_tmp_hi` 由库内 `stamps` 的 `MIN/MAX(page)` 得出 ⇒ `[13, 14]` | **夹具取样错误**：`tmp.pdf` 的印面全在 13–19 页，1–2 页在库内**一行都没有** ⇒ `detected=0` 是**必然**，于是 `7.7「真的跑了检测」` **恒 FAIL**。判据本身没错（「跑没跑检测」该判），错在**取样点没有印面**。 |
| 7 | `ckT` 的 `detail` 参数 | `f"PASS …{('：' + detail) if detail else ''}"`（假定 `detail` 是 `str`） | 入口统一 `detail = "" if detail is None else (detail if isinstance(detail, str) else str(detail))` | 调用点 `7.10` 传的是 **list**（`rc2.stdout.splitlines()[-1:]`），`PASS` 分支一拼就 `TypeError` ⇒ **整轮脚本在第 7.10 处异常终止**（该缺陷此前从未暴露：上一轮在 E7 死循环就被杀掉了，根本没跑到第 7 段）。**断言辅助函数不得对调用点的类型做单方面假设。** |
| 8 | 收尾判据 | 只报 `PASS/FAIL` 两个数 | 加 `9.1`（总数 == 预期，O-5）/ `9.2`（跑到收尾）/ `9.3`（9 子段齐全）/ `9.4`（无未收敛护栏命中） | 中途终止/静默跳过时，原脚本可能**少跑几条却仍报 FAIL=0** ⇒ 假绿。 |
| 9 | E7 子段新增判据 | 只有 4.1–4.10（不含 `page`） | 增 `4.11–4.17`（见 §1.6） | 原夹具只用 `cursor` 翻页 ⇒ **`?page=` 这条路径完全没有判据**，`page` 失效可以一路绿灯通过（这正是本单缺陷能被发布出去的原因）。 |

---

## 3. E3 / E4 / E6 / E7 逐项真实自测证据

### 3.1 命令与总结果

```bash
cd /Users/kevin/bistro/shu/feicui/server
./.venv/bin/python selftest/verify_1b_ii.py     # 终态轮（run3）
```

```
PASS=143  FAIL=0（折叠掉的重复失败 0 次；进入断言 143 种）
9.1 …：139          9.2 …：进入过的子段=9        9.3 …：9 个子段全部进入过        9.4 …：命中 0 类
[cleanup] 端口 5321 已释放 = True   [cleanup] 端口 5323 已释放 = True
EXIT=0
```

证据：`evidence/1b_ii/98d_run3_official_console.log`（逐行 PASS，含每步取值）、`99_summary.json`（`PASS=143 / FAIL=0 / assertions_run=143 / end_reached=true / sections_seen=9`）、`96_cleanup.json`、`97_fail_folds.json`（`folded_repeats=0`）。

前置取证（`01_prod_fingerprint_before.json`：`0.1` 列数 10 / `0.2` 行数 79 / `0.3`–`0.5` 三口径指纹与 `ops/prod_migrate_evidence.md §2.3` 期望**逐字节相等**：`8a21e57d…` / `d7abe995…` / `22bdc0a7…`；`0.6` `stamps/seals/images` 无 BLOB 列；`0.7` 改动前 `exports/` 批次包 **12**）。

### 3.2 E3（`GET /api/jobs/{job_id}/stamps`）——**正确，本单未动**

| 断言 | 结果（run3） |
| --- | --- |
| `3.1` 逐页 6 字段信封 | 4 本书全 PASS（`['has_more','items','limit','next_cursor','page','total']`） |
| `3.3` 游标翻页 no overlap no miss | `tmp.pdf` 5 页 / 30 条；`古玺汇编` 4 页 / 23 条；`秦汉印典` 4 页 / 26 条；fixture 1 页 / 4 条 |
| `3.6`/`3.7` 全表合并 83 条、无重复 key | `83` / `83`（＝ 79 真实行 + 4 fixture 行，副本库口径） |
| `3.8`/`3.9` `?page=` 与游标两路结果一致、页号递增 | PASS（`page=1..5`） |
| `3.10`/`3.11` **AC-08**：每条记录给出 §9.3 必填 11 项或明确 `missing_required` | `[]`（无静默缺字段）/ 覆盖 83 条 == 全量 83 条 |
| `3.12`/`3.13` 错误码 400/404（7 例）× 体含 `detail` | 全 PASS |

### 3.3 E7（`GET /api/jobs`）——**本单修复项**

`4.1` 200 / `4.2` 六字段信封 / `4.3` items 9 项 / `4.3b` `job_id` 非空 / `4.4c` 游标路径在硬上界内收敛 / `4.5` 游标 no overlap no miss / `4.6` `total == 库内 job 数`(4) / `4.7` 翻页数 == `ceil(total/2)`(2) / `4.8` `state=QUEUED` 过滤 / `4.9` `state` 非法 400 / `4.10` 游标非法 400 / **`4.11`–`4.17` 见 §1.6** ⇒ **全 PASS**（逐页表见 §1.5）。

### 3.4 E6（`GET /api/jobs/{job_id}/stamps/{page}/{idx}/image`）

题目要求的三项**逐条落实**：

**(a) 返回影像字节（不是 JSON 信封）**

| 断言 | 实测 |
| --- | --- |
| `5.1` 正常取图 ⇒ 200 | `200`（取 `tmp.pdf` p13 i0，`img_path='output/pairs/p13_0/stamp.png'`） |
| `5.2` `Content-Type ∈ {webp,png,jpeg}`（以文件实际类型为准） | `image/png` |
| `5.3` `Content-Length` 必填且 == 实际字节 | `27958`（== 盘上文件字节数） |
| `5.4` 字节与盘上文件**逐字节相同** | sha256 `518f52f4b46c32c4118dafba1de6f779ec228fe48590347b712a88ae0a409c0c`（双方一致） |
| `5.5` **不包 JSON 信封** | 首 12 字节 `b'\x89PNG\r\n\x1a\n\x00\x00\x00\r'` ⇒ 首字节不是 `{` |
| `5.6`/`5.7` `Cache-Control: no-store` / `x-feicui-img-path` == DB 内相对路径 | `no-store` / `output/pairs/p13_0/stamp.png` |

**(b) 三类不存在 ⇒ 404（同码）**

| 类别 | 路径 | 实测 |
| --- | --- | --- |
| job 不存在 | `/api/jobs/job-nope/stamps/1/0/image` | `404`（`5.8`） |
| `(page,idx)` 记录不存在 | `/api/jobs/{job}/stamps/999999/0/image` | `404`（`5.8`） |
| `img_path` 缺失/文件不在盘上 | fixture 4 行 | `404`×4（`5.9`：`output/../../../../etc/passwd` / `/etc/passwd` / `''` / `output/__1bii_missing__.webp`） |

**(c) 越界校验**

* `5.9` 的 fixture 三例即越界判据：**逃出 `FEICUI_ROOT` 的相对路径**、**绝对路径**、**空 `img_path`**、**相对但盘上无文件** ⇒ 一律 `404 IMAGE_UNAVAILABLE`；`54_e6_traversal_guard.json` 并排给出「DB 内 `img_path` ↔ `Path(FEICUI_ROOT+img_path).resolve()` ↔ 是否仍在 root 内 ↔ 判定」。
* `5.10` 参数非法 7 例（`page` 非整数 / `page<1` / `page` 负数 / `idx` 非整数 / `idx<0` / `page` 小数 `1.5` / URL 编码 `%2e%2e`）⇒ **全 400**；`5.11` 已废止的**两段**临时路径 `/stamps/0/image` ⇒ **404**（后端不两套并存）。

### 3.5 E4（`POST /api/jobs/{job_id}/export`）——**证明未污染既有 12 个批次包**

```bash
# 自测内部：export_root 指向临时目录（FEICUI_EXPORT_ROOT=<scratch>/exports_tmp_main）
./.venv/bin/python selftest/verify_1b_ii.py         # 段 6
```

| 断言 | 实测（run3） |
| --- | --- |
| `6.1`–`6.3` 200 / 响应 **4 字段** / `counts` 3 字段 | `['batch_id','counts','package_dir','selfcheck_ref']` / `['draft','formal','rejected']` |
| `6.4` 批包目录真实存在（**临时导出根内**） | `<scratch>/exports_tmp_main/fb_20260920_XTMP_05` |
| `6.5` 批包内文件集 | `['draft.jsonl','manifest.json','report.json','seals.jsonl']` |
| `6.6`–`6.8` `counts` == 批包 `report.json` 的 `counts.feicuiDecidable` | `formal 0` / `draft 30` / `rejected 30`（逐项相等） |
| `6.9` 影像被真实复制进批包 | **30 个** |
| `6.10` 指定 `batch_id` / `dry_run=true` / `book_code` 不符 ⇒ 400 | 全 400（不臆造批次号、不假装跑过） |
| `6.11` 未知 job ⇒ 404 | 404 |
| **`6.12` 正式 `exports/` 既有产物逐文件 md5 未变** | **197 个文件 md5 全等**（改动前/后两次 manifest 逐键比对） |
| **`6.12b` 12 个 `fb_*` 批次包名称集合未变** | 集合相等（12 个名字逐一列出） |
| **`6.13` 批次包数仍 12** | `12` |

⇒ **本单 E4 的产物只落临时导出根**，正式 `exports/`（12 个 `fb_20260920_*` + `selfcheck_report.json`，最大 mtime **10:08**）**一个字节未变**（`02_prod_exports_manifest_before.json` vs `63_prod_exports_manifest_after.json`；收尾 `8.7` 再复验一次）。

### 3.6 1b-i 回归臂 ＋ **`7.7 detected=0` 的定性（夹具取样错误，不是真回归）**

回归臂：临时副本库 `copy_reg.db`（backup API 一致快照）＋ `python -m app.pool --workers 2 --drain`（worker 用 `feicui/venv/bin/python`，OCR 在 worker 内）。

**定性判据（题目要求的三问，逐条给原始证据）：**

| 问题 | 原始证据 | 结论 |
| --- | --- | --- |
| 该臂往哪个副本库跑？ | 池日志首行 `db = /private/var/…/feicui_1bii_qibrhh06/copy_reg.db`；`FEICUI_FACES_DIR=<scratch>/faces_reg`（`70_reg_pool_stdout.txt`） | 临时副本库 + 临时 faces 目录，**未碰正式库/`output/`** |
| 页区间是什么？ | 池日志 `认领 job job-aa7db679… 页区间=[1,2] chunk_size=2`（**run1** 的臂） | 旧夹具：`[1,2]` |
| 该区间在库内 `stamps` 应有多少行？ | 只读正式库（同一份内容）：`tmp.pdf` 页分布 = `13:6, 14:6, 15:7, 16:3, 17:2, 18:2, 19:4`（共 30）；**`page BETWEEN 1 AND 2` ⇒ 0 行**；`page BETWEEN 13 AND 14 ⇒ 12 行` | **应为 0 行** ⇒ `detected=0` 是**必然结果** |
| worker 日志尾部 | `worker#0/#1 ready … paddleocr=3.7.0 doc_preprocess=True cpu_threads=2`；`提交 chunk c0（页 [1, 2]）：inserted=0 updated=0 skipped=0 failed=[]`；`池退出：{chunks_committed:1, pages_done:2, pages_failed:0, detected:0, imgs_written:0, worker_deaths:0}`；E2 读数 `state=DONE done_pages=2/2 failed_pages=[]` | **链路本身完全正常**（worker 就绪、chunk 提交、job 正常收尾、零 worker 死亡）——只是**这两页没有印面** |

**⇒ 定性：夹具取样错误（不是真回归）**。修法：页区间改为该书真实页跨度 `[13, 14]`（见 §2.6 #6）。修后 run3 实测：`PASS 7.7 回归臂 counters.detected > 0（真的跑了检测）：detected=13 inserted=1 skipped=12 ocr_empty=1`；`PASS 7.5 done_pages == total_pages == 2`；`PASS 7.13 E3 在池产出的 job 上可用：(200, 13)`；`PASS 7.3 池 --drain rc=0`；`PASS 7.15 回归臂接口层已停（精确 PID）`；`7.9` 1b-i 独立复算工具 `rc=0`、`7.10 e2check 逐字段 MATCH`、`7.11 counts rc=0`、`7.12` 临时 faces 目录真实产出影像、`7.14` 池退出后无残留 worker。**1b-i 执行层（`worker/**`、`pool.py`）本单未改一字（`server/worker/**` 在 12:40 之后 0 个文件被写）**。

> **附：一条值得规范侧注意的观测（未定性，仅登记，见 §5-G-e）**
> `7.7` 的 `skipped=12` 说明既有 12 行**原样未改写**（AC-01 的正确行为）；但它同时 `inserted=1`——即**在既有库上重解析同一区间，得到 13 条而库内只有 12 条**。这与 1b-i 首跑「`tmp.pdf` 7 页解析 detected=31 / inserted=31，而正式库同 7 页 30 行」**同向**。两种解释（检测非确定性 / 旧解析少一行）本单**未做实验判定**，故只在 §5 登记、不修不裁。

---

## 4. 未完成项（如实列）

| # | 项 | 状态 | 说明 |
| --- | --- | --- | --- |
| 1 | ~~**AC-03 的 50% 回退点**~~ | **已补（D-2 闭合）** | 追加探针 `selftest/probe_ac03_kill50.py`：`tmp.pdf` 27–33 / `chunk_size=1` / `w=2`，**已提交 4/7 页＝57.1%**（连续前缀亦 4 页）处 SIGKILL 池＋2 worker（精确 PID）→ 续跑收尾 ⇒ 终态 `DONE 7/7`、`failed=0`；**断点前 22 行零改写**（`SUBSET = IDENTICAL`）；**终态 42 行与 1b-i 串行臂逐字节相同**（`DIFFCSV = IDENTICAL`）。证据 `evidence/1b_ii/46_reg_ac03_kill50_probe.json`；口径同步回填 `REPORT_1b-i.md` §5-10 / §6.1-G-10 |
| 2 | `REPORT_1b-i.md` 的 D-1 终态回填 | **已完成（本单）** | §1 落盘文件/md5 表、§3 五条自测真实命令与输出、§6 裁定状态同步 ⇒ 已按 12:26–12:29 那轮实测数据回填（**未重跑测试**）。 |
| 3 | E7 的 `page`+`cursor` 同给 ⇒ 400 | **已实现（属规范缺口取法）** | 规范未定二者同给的语义；本层取「与 E3 同款互斥」，已登记（§5-G-a）。 |
| 4 | E7 `items[]` 形状 | **仍为草案** | §3.1 E7 行自注「形状草案，1b 落地时按 §0.4 回填」；本单未改形状（9 字段照草案）。 |
| 5 | 边款影像 / `images`·`seals` 侧表 / AC-12 斜率实验 / doc 预处理精度结论 / 多 job 并行调度 | **未做（1b-i 遗留，非本单范围）** | 逐条见 `REPORT_1b-i.md` §5。 |
| 6 | `app/models.py` | **未改**（md5 `0bbca37b…` 前后一致） | 6 字段信封与 E7 items 模型本来就对；缺陷在路由/仓库层 ⇒ **不需要改形状层**（这也是一条证据：形状不是问题所在）。 |
| 7 | 中文书名的 `x-feicui-scope` 响应头 | **本单未动（另一轮已修）** | 代码中已存在 `_header_safe()`（非 ASCII 百分号编码）；Zang 复核确认含中文书名建单全部 201。 |

---

## 5. 规范缺口（本单新增 / 仍未收口）

| # | 类型 | 内容 | 本单取法（**未静默**） |
| --- | --- | --- | --- |
| **G-a** | 缺口 | §3.1 **E7 行**的入参写作 `?state=&limit=&cursor=`，**未列 `page`**；但 §3.2 **S-3** 的信封含 `page` 字段，前端与自测都会用 `?page=`。 | 本单按**与 E3 同款**补齐 `page`（1-based、与 `cursor` 互斥、越界返回空页）。请规范侧把入参行改写为 `?state=&page=&limit=&cursor=`（这处不一致就是本单缺陷的温床）。 |
| **G-b** | 缺口 | E7 `items[]` 字段集仍标「**形状草案**」（§3.1 E7 行自注）。 | 沿用草案 9 字段（`job_id / pdf_name / pdf_path / state / total_pages / done_pages / failed_pages_count / created_at / updated_at`），未增未减。 |
| **G-c** | 缺口（**新观测定性所需**） | E7 的**排序键**规范未定。 | 本单取 `ORDER BY j.created_at, j.job_id`（`job_id` 唯一 ⇒ **全集序、无并列**）。**依据是实测**：4 个 job 的 `created_at` 常落在同一秒（12:51:12 三个、13:0x 四个），**只按 `created_at` 排序无法保证「不重叠 / 不遗漏」**。建议把这一个排序键写进规范，否则不同实现会给出不同的翻页结果。 |
| **G-d** | 缺口 | E7 游标编码格式规范未定。 | 本单用 **URL-safe base64**（`created_at` 含 `+`/`:`，直接进 query 会被解码成空格 ⇒ 已在 `repository.py:encode_cursor_e7` 留痕）；E3 的 `p<page>_i<idx>` 天然安全。 |
| **G-e** | **观测（未定性，只登记）** | 「**同区间重解析的行数**」与「库内行数」不一致：`tmp.pdf` 页 13–14 库内 12 行 → 重解析 13 行（`inserted=1 skipped=12`）；页 13–19 库内 30 行 → 1b-i 首跑解析 31 行。 | 本单**不修不裁**。请规范侧裁定：AC-01 的口径是「**旧行不得被改写**」（现状**成立**：`skipped=12` 原样未动）还是「**行数不变**」（现状**不成立**）。若后者入判据，需先定性差异来源（检测非确定性 vs 旧解析缺失）。 |
| **G-f** | 缺口 | **AC-03 的两点位**（25% / 50%）在 `X ∈ {25,50}` 里是「各至少一次」。 | 原仅 1 次（3/7＝42.9%）；**本单已补 57.1% 点位**（§4-1 探针）⇒ 两点位各 ≥1 次。仅剩一个小口径请规范侧钉定：**点位按「已提交页数」还是「连续已提交前缀」计**（`chunk_size>1` 且 `w>1` 时两者会不同：段② 是 42.9% vs 28.6%）。 |
| **G-g** | 缺口 | §3.5 只写 E6 的「404 三类同码」，未写**越界路径的 404 原因码是否需与「记录不存在」区分**。 | 本单：job 不存在 / 记录不存在 / 影像不可得（含越界、绝对路径、空路径、文件缺失）各用 `JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE` 三个码，**HTTP 码同为 404**（合规范）。 |
| **G-h** | 缺口 | `x-feicui-scope` 等**响应头**承载的判定范围，规范只说「可另以响应头暴露…不进 JSON 体」（§3.1 E5 行）。 | E3/E7 沿用该口径；头值经 `_header_safe()` 百分号编码（非 ASCII ⇒ `%XX`）。 |

---

## 6. 证据索引与红线复核

**证据目录**：`server/selftest/evidence/1b_ii/`

| 文件 | 内容 |
| --- | --- |
| `46_reg_ac03_kill50_probe.json` | **AC-03 追加点位**（57.1% SIGKILL → 续跑）的完整结果与三个工具的 stdout |
| `98d_run3_official_console.log` / `98e_run3_official_console.out` | 终态轮逐行输出（`PASS=143 FAIL=0 exit 0`） |
| `98c_run2_calibration_console.out` | 标定轮（`9.1` 报 `expect=0 got=139`） |
| `98b_run1_after_guard_console.out` | 加护栏后、夹具笔误未修那轮（125 PASS / 1 FAIL / 7.10 异常终止） |
| `98_run1_E7runaway_console.log` | **上一轮失控的原始证据**（54,347 行 / 54,254 条重复 FAIL） |
| `44_e7_page_probe_BEFORE.json` / `45_e7_page_probe_AFTER.json` | E7 翻页探针改前 / 改后全表（§1.5） |
| `40_e7_page1.json` / `41_e7_pagination.json` | E7 单页 + 两路翻页明细（含 `page_rows` / `cap` / `guard`） |
| `30_e3_pagination.json` / `31_e3_sample_items.json` / `32_ac08_coverage.json` / `33_e3_errors.json` | E3 与 AC-08 |
| `50_e6_image_200_headers.txt` / `51_e6_404.json` / `52_e6_400.json` / `53_e6_deprecated_path.json` / `54_e6_traversal_guard.json` | E6 全量 |
| `60_e4_export_response.json` / `61_e4_package.json` / `62_e4_errors.json` / `63_prod_exports_manifest_after.json` | E4 与「正式 exports 未变」 |
| `01_prod_fingerprint_before.json` / `02_…_before.json` / `90_prod_fingerprint_after.json` / `91_prod_output_manifest.json` | 正式库与产物前后指纹 |
| `70_reg_pool_stdout.txt` / `71_reg_e2.json` / `76_reg_e3.json` / `96_cleanup.json` / `97_fail_folds.json` / `99_summary.json` | 回归臂 / 清理 / 折叠 / 汇总 |

**红线复核（本单收尾实测）**：

| 判据 | 实测 | 结论 |
| --- | --- | --- |
| `stamps` 列数 / 行数 | **10 / 79** | 未变 |
| 三口径指纹 A/B/C | `8a21e57d5bd909fff282214640457c7f` / `d7abe995bff62761c27052dfc2bdf7bb` / `22bdc0a794382b6e6dab7855aaee456f` | 与 `ops/prod_migrate_evidence.md §2.3` 期望**逐字节相等**（`8.4`/`8.5`/`8.6` PASS） |
| `exports/` | **12 个 `fb_*` + `selfcheck_report.json`（197 文件 md5 全等，最大 mtime 10:08）** | 未污染 |
| `output/` | **80 文件 / 49 webp**（`91_prod_output_manifest.json`：`文件数=80`，本轮未写入） | 未污染 |
| `server/app/migrations.py` | 本单未写（mtime 2026-09-20 11:51，md5 `0061c6a1e97b6229b55a0860a453668c`） | 未改 |
| `server/worker/**` | 本单未写（12:40 之后 0 个文件被写） | 未改 |
| `docs/feicui.spec.md` | 本单未写（mtime 12:10，md5 `6dbe0b3c915d7f8ed43576a00122dcf1`） | 未改 |
| `shu/web/**` / `feicui/web/**` / `ctrl/**` | 本单未写 | 未改 |
| 正式库写入 | 全程 **只读**（`sqlite3.connect('file:…?mode=ro', uri=True)`；**不用 sqlite3 CLI**——WAL 下 CLI + `md5` 会得空输入 md5 的假结论） | 未写 |

> **⚠️ 库文件级 md5 不是本单（也不是任何单）的判据（实测再次印证）**
> `yinpu.db` 的**文件** md5 现为 `56cbf7afd124e86c6d9f810c0380c3eb`，而 1b-i 自测时点（12:29:26）记录为 `254d3ff132d3a8d14dcf8590f45c7232`。
> 差异**不是本单造成的**：该文件 **mtime = 2026-09-20 12:42**（早于本单开工时点），且库处于 **WAL**（旁文件 `-wal`/`-shm` 同时存在）——
> WAL 回拷/检查点会重写文件而**不改内容**。**可判定的判据只有内容口径**：`stamps` **10 列 / 79 行 / 三口径指纹**
> `8a21e57d…` / `d7abe995…` / `22bdc0a7…`（本单开头与收尾两次实测**逐字节相同**，且与 `ops/prod_migrate_evidence.md §2.3` 期望相等）。
> 建议规范侧把这条写进纪律：**红线判据一律用内容指纹，禁用库文件 md5**。
| 端口纪律 | 自测 **5321–5323**（动态探测）；探针 **5341/5342**（动态）；**未碰** 5164/5195/5196/5555/5173/5174；停服务一律**精确 PID**，**全程无 `pkill -f` / `killall`** | 合规 |

---

## 7. 本单落盘文件与 md5（改前 → 改后）

| 文件 | 改前 md5 | 改后 md5 | 性质 |
| --- | --- | --- | --- |
| `server/app/routers/jobs.py` | `a9158caa50255ffdee2137f5389d0b3f` | `d0a0e57432264ae001cf72dea1386747` | **修产品**：E7 新增 `page` 入参（互斥/校验/透传） |
| `server/app/repository.py` | `8ef1d8b0ab326e7fdd1d6529f67b0220` | `a5f4de5e6e9c82639024c5242b958161` | **修产品**：`jobs_page` 加 `page`；游标分支去掉 `OFFSET`；`has_more↔next_cursor` 结构性一致 |
| `server/selftest/verify_1b_ii.py` | `7297714e96bf904b8ddeb5934d17cb6c` | `beb1d20efe623ac54b1116a1ef67e6c4` | **修夹具**：六条护栏 + O-5 四条收尾断言 + E7 `page` 判据 `4.11–4.17` + 三处笔误（§2.6 #6/#7） |
| `server/selftest/probe_e7_page.py` | （新增） | `fae8a2dc73593899ccb23c23d692c542` | **新增**：E7 翻页探针（有界、动态端口、`finally` 清理），§1.5 的表由它产出 |
| `server/REPORT_1b-ii.md` | （新增） | 本文件 | **新增**：本报告 |
| `server/selftest/probe_ac03_kill50.py` | （新增） | `4bbc159663ed59c7231edc1f46b73da9` | **新增（D-2）**：AC-03 追加点位探针（≥50% 处精确 PID SIGKILL → 续跑），产出 `46_reg_ac03_kill50_probe.json` |
| `server/REPORT_1b-i.md` | `62f11aec62ea9169b284cfeb0a3e8535` | `a125494a53c18730a84b560285c52df1`（121 → 237 行） | **回填**（D-1）：§1 落盘文件/md5、§3 五条自测真实命令与输出、§5-10、§6.1 裁定状态 |
| `server/app/models.py` | `0bbca37b040fb4480e2706447503e123` | `0bbca37b040fb4480e2706447503e123` | **未改**（形状层无需改，见 §4-6） |

**改动面**：3 改 2 增；**未改** `migrations.py` / `worker/**` / `docs/feicui.spec.md` / `shu/web/**` / `feicui/web/**` / `ctrl/**` / `exports/**` / `output/**`。

---

## 8. 复跑命令（读者可自证）

```bash
# ① 终态自测（含六条护栏与 O-5 闸门；动态端口、只读正式库、临时导出根）
cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python selftest/verify_1b_ii.py
#   期望：PASS=143  FAIL=0，exit 0；随后打印 [cleanup] 端口 … 已释放 = True

# ② E7 翻页探针（页码路径 vs 游标路径全表，5 个 job / limit=1 / created_at 抹平）
cd /Users/kevin/bistro/shu/feicui/server && \
  ./.venv/bin/python selftest/probe_e7_page.py --out /tmp/e7_probe.json
#   期望：page_path_equals_cursor_path = True；beyond_last_page_ok = True；
#         cursor_guard_broken = None

# ③ AC-03 追加点位（≥50% 处 SIGKILL → 续跑；只碰临时副本库，精确 PID 停池/worker）
cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python selftest/probe_ac03_kill50.py
#   期望：kill 已提交 4/7 页（57.1%）→ 续跑 DONE 7/7 / failed=0；
#         subset = IDENTICAL（断点行零改写）；diffcsv vs 1b-i 串行臂 = IDENTICAL

# ④ 红线（只读正式库；**不要**用 sqlite3 CLI + md5，WAL 下会得空输入 md5）
cd /Users/kevin/bistro/shu/feicui && ls -1d exports/fb_* | wc -l   # 12
find output -type f | wc -l                                        # 80
```
