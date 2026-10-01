# feicui 正式库 `yinpu.db` 迁移取证（角色：Kong / 运维执行）

> 状态：**已完成** ✅
> 授权：Kevin 明确授权对正式库执行本次迁移——**只新增 3 张侧表 + 索引 + 开 WAL，
> 不得动 `stamps` 的 10 列与 79 条数据**。
> 时间窗：2026-09-20 12:41:57 → 12:42:52 CST（全程约 55 秒）
> 原始命令输出（全文，未删改，含一次作废段落留痕）：`ops/prod_migrate_before_after.txt`
> 复算脚本（**全只读**）：`ops/prod_migrate_fingerprint.py`、`ops/prod_migrate_crosscheck.py`
> 迁移入口（现成，未改一行）：`cd server && ./.venv/bin/python -m app.migrations`

## 0. 硬约束遵守声明

| 约束 | 遵守情况 |
|---|---|
| 不启动任何服务、不占 5195/5196/任何端口 | ✅ 只跑 4 次**短命 CLI**（负向对照 1 + 迁移 2 + `--status` 1）+ 只读脚本；`lsof -nP -iTCP:5195 -iTCP:5196 -sTCP:LISTEN` 无输出 |
| 不重启 ctrl 面板 | ✅ 未触碰 `ctrl/**`，未向面板发任何请求 |
| 不改/删备份与其它数据文件 | ✅ 只**新增**一份备份；`yinpu.db.bak-f2`（466944 B / 10:04）md5 未变、未被删改 |
| 不改写 `stamps` 任何行 | ✅ 见 §4/§7：三套口径指纹 + 逐表比对 + `.dump` INSERT 行 md5 全部逐字相同 |
| 不改 `processor.py`/`export.py`/`app.py`/`server/app/**` | ✅ 只**调用**现成入口 `python -m app.migrations`，未写 `server/**` 任何文件（未 `pkill`/未 `kill`） |
| 不改 `feicui/web/**`、`shu/web/**`、`docs/**`、`ctrl/**` | ✅ 未触碰 |
| 严禁 `pkill -f`/`killall`、不 kill 任何进程 | ✅ 未执行任何 `kill`/`pkill`/`killall`；`ps` 无 feicui/streamlit/uvicorn 常驻进程 |
| 交付物不写进 `qa-baseline/`、`qa-recheck/` | ✅ 全部落 `feicui/ops/` |

**本次新增/改动文件（只有这些）**：
`ops/prod_migrate_evidence.md`（本文件，新建）、`ops/prod_migrate_before_after.txt`（新建）、
`ops/prod_migrate_fingerprint.py`（新建，只读）、`ops/prod_migrate_crosscheck.py`（新建，只读）、
`yinpu.db.bak-premigrate-202609201241`（新建备份）、`yinpu.db`（**迁移目标**：加表/加索引/开 WAL）。

## 1. 备份

| 项 | 值 |
|---|---|
| 备份文件 | `/Users/kevin/bistro/shu/feicui/yinpu.db.bak-premigrate-202609201241` |
| 备份 md5 | **`254d3ff132d3a8d14dcf8590f45c7232`** |
| 备份 size / mtime | `577536` / `1789870116`（=`2026-09-20 10:08:36`，`cp -p` 保留源 mtime） |
| 源库 md5（备份前） | `254d3ff132d3a8d14dcf8590f45c7232` ⇒ **与备份逐字节相同** |
| 命名/防覆盖 | `yinpu.db.bak-premigrate-<YYYYMMDDHHMM>`；脚本先探测同名，存在则追加 `-N`，**绝不覆盖** |
| 原有备份 | `yinpu.db.bak-f2`（`466944` B，`2026-09-20 10:04`）**未触碰**（存续至 §9 复核） |

## 2. 迁移前取证

库：md5 `254d3ff132d3a8d14dcf8590f45c7232`，size `577536`，inode `59624593`，mtime `2026-09-20 10:08:36`。

### 2.1 `PRAGMA table_info(stamps)` = **10 列**

```
0|id|INTEGER|0||1
1|pdf_name|TEXT|0||0
2|page|INTEGER|0||0
3|idx|INTEGER|0||0
4|text|TEXT|0||0
5|img_path|TEXT|0||0
6|x1|REAL|0||0
7|y1|REAL|0||0
8|x2|REAL|0||0
9|y2|REAL|0||0
```

### 2.2 行数 = **79**；逐书名计数

| pdf_name | count |
|---|---|
| `tmp.pdf` | 30 |
| `古玺汇编 文物出版社 罗福颐  ok.pdf` | 23 |
| `秦汉印典 上海书画 金怀英  1997 ok.pdf` | 26 |

### 2.3 内容指纹（**三套口径**，迁后必须逐字相同）

| 口径 | 精确定义（可复算） | md5 | sha256 |
|---|---|---|---|
| **A raw** | 等值于 `sqlite3 yinpu.db "select * from stamps order by id" \| md5`：逐行用 `\|` 连接全部列（`NULL`→空串），行尾 `\n`，无表头 | `8a21e57d5bd909fff282214640457c7f` | `76d2547a8b502dec93b75a0ed1666d3fc9f7b40c3025a13617b833a9e3a18961` |
| **B canon** | 逐行 `{"列名":值}` 的 JSON（`ensure_ascii=False, sort_keys=True, separators=(',',':')`），按 `id` 升序、行间 `\n`、末尾补 `\n` | `d7abe995bff62761c27052dfc2bdf7bb` | `19aa714841b366c15c7d53327d3753bbc008b8ef4b6c0bc978542076d11024ea` |
| **C free** | 各行 canonical JSON 字符串**升序排序**后拼接（与 `id` 顺序无关，交叉校验 B） | `22bdc0a794382b6e6dab7855aaee456f` | `96c237c0bc49895e15f31d27d56a459a92c7d3cfc713a874011db940b4848b92` |

A 口径已双重核实：shell `sqlite3 … | md5` 与脚本口径 A 输出一致；`wc -l` = 79；
脚本**未**打印 `WARN: 存在含 '|' 或换行的文本值` ⇒ 文本列不含 `|`/换行，A 无歧义。

逐列非空：`id/pdf_name/page/idx/img_path/x1/y1/x2/y2` 各 79；`text` **2**（与已知事实一致）。

### 2.4 其它基线

* `PRAGMA journal_mode` = **`delete`**
* `.tables` = `export_batches  export_records  images  seals  stamps`（既有侧表已存在，非本次创建）
* `sqlite_master` 中**没有任何显式索引**，只有 4 个 `sqlite_autoindex_*`（`export_batches/export_records/images/seals`）
* `integrity_check` = `ok`；`user_version` = 0；`foreign_key_check` = 0 行
* 既有表行数：`export_batches` 12 / `export_records` 49 / `images` 79 / `seals` 79

## 3. 执行迁移

### 3a. 负向对照（先证明安全闸是真的，再打开它）

```
$ FEICUI_DB=/Users/kevin/bistro/shu/feicui/yinpu.db ./.venv/bin/python -m app.migrations
✗ 拒绝：解析到的 DB 是仓库内正式库 yinpu.db（唯一真源，不得被本层写入）。
  解析路径 = /Users/kevin/bistro/shu/feicui/yinpu.db
  若确需对正式库执行，请显式设 FEICUI_ALLOW_PROD_MIGRATE=1（须 Kevin/Zang 明示）；
  自测请用副本：cp yinpu.db /tmp/feicui_copy.db && FEICUI_DB=/tmp/feicui_copy.db …
exit=3        # 且 md5 仍为 254d3ff132d3a8d14dcf8590f45c7232（未写任何字节）
```

### 3b. 正式执行（显式授权闸）

```
$ cd server && FEICUI_DB=/Users/kevin/bistro/shu/feicui/yinpu.db \
    FEICUI_ALLOW_PROD_MIGRATE=1 ./.venv/bin/python -m app.migrations
db           = /Users/kevin/bistro/shu/feicui/yinpu.db
prod_db      = True
applied      = 2
skipped      = 0
journal_mode = wal
schema_sha256= d35d052b6aee2a195c6879009c2116b87578a357bbeed829176410ccffd608be
tables       = export_batches,export_records,images,job_pages,jobs,schema_migrations,seals,sqlite_sequence,stamps
exit=0
```

> `schema_sha256` 与副本自测值一致 `d35d052b…608be`：该指纹只由 `sqlite_master`（结构）决定，
> 与行数据无关，因此副本/正式库同构即同值——**不是**从别处照抄。

### 3c. 迁移后文件状态

| 项 | 迁移前 | 迁移后 |
|---|---|---|
| md5 | `254d3ff132d3a8d14dcf8590f45c7232` | `56cbf7afd124e86c6d9f810c0380c3eb` |
| size | `577536` | `638976`（+61440） |
| inode | `59624593` | `59624593`（**未变** ⇒ 原文件就地修改，未被替换） |
| mtime | `1789870116`（10:08:36） | `1789879333`（12:42:13） |
| journal_mode | `delete` | `wal` |

## 4. 迁移后取证（逐项对比 §2）

| 检查项 | 迁移前 | 迁移后 | 判定 |
|---|---|---|---|
| `stamps` 列数 | 10（`id,pdf_name,page,idx,text,img_path,x1,y1,x2,y2`） | 10，**列名/类型/顺序/notnull/pk 全部逐字符一致** | ✅ 未变 |
| `stamps` 行数 | 79 | 79 | ✅ 未变 |
| `tmp.pdf` | 30 | 30 | ✅ 未变 |
| `古玺汇编 文物出版社 罗福颐  ok.pdf` | 23 | 23 | ✅ 未变 |
| `秦汉印典 上海书画 金怀英  1997 ok.pdf` | 26 | 26 | ✅ 未变 |
| 口径 **A** md5 | `8a21e57d5bd909fff282214640457c7f` | `8a21e57d5bd909fff282214640457c7f` | ✅ **一字不差** |
| 口径 **B** md5 | `d7abe995bff62761c27052dfc2bdf7bb` | `d7abe995bff62761c27052dfc2bdf7bb` | ✅ 一字不差 |
| 口径 **C** md5 | `22bdc0a794382b6e6dab7855aaee456f` | `22bdc0a794382b6e6dab7855aaee456f` | ✅ 一字不差 |
| 逐列非空 | text=2，其余=79 | text=2，其余=79 | ✅ 未变 |
| `journal_mode` | `delete` | **`wal`** | ✅ 目标达成 |
| `integrity_check` | `ok` | `ok` | ✅ |
| `.tables` | 5 张 | 8 张 | ✅ 多出 3 张 |

`.tables`（迁后）：`export_batches  images  jobs  seals / export_records  job_pages  schema_migrations  stamps`

**新增 3 张侧表**（实测行数）：

| 表 | 行数 | 说明 |
|---|---|---|
| `jobs` | **0** | 新，空表（未产生业务数据） |
| `job_pages` | **0** | 新，空表 |
| `schema_migrations` | 2 | 迁移记账（2 条，见下） |

**新增 6 个显式索引**（迁移前显式索引为 0）：

```
idx_jobs_pdf_path_state         ON jobs(pdf_path, state)
uq_jobs_active_pdf_path         ON jobs(pdf_path) WHERE state IN ('QUEUED','RUNNING','PAUSED')   -- UNIQUE 部分索引
idx_job_pages_job_state         ON job_pages(job_id, state)
idx_job_pages_job_chunk         ON job_pages(job_id, chunk_index)
idx_stamps_pdf_page             CREATE INDEX idx_stamps_pdf_page ON stamps(pdf_name, page)
uq_stamps_pdf_page_idx          CREATE UNIQUE INDEX uq_stamps_pdf_page_idx ON stamps(pdf_name, page, idx)
```

`schema_migrations` 记账：

```
1a-0001-jobs|2026-09-20T12:42:13+08:00|新增侧表 jobs / job_pages 及其幂等约束与索引（规范 §2.1–§2.4 / §4.1）
1a-0002-stamps-indexes|2026-09-20T12:42:13+08:00|stamps 加索引与行级幂等唯一索引（规范 §4.1 D-2 / §2.4）——只加索引，不改列不改行
```

新增 `uq_stamps_pdf_page_idx` UNIQUE 索引**建立成功**这一事实本身，也是 `(pdf_name,page,idx)` 无重复的证明。

## 5. 幂等复跑

```
$ md5 yinpu.db                        # 复跑前
MD5 (yinpu.db) = 56cbf7afd124e86c6d9f810c0380c3eb
$ cd server && FEICUI_DB=/Users/kevin/bistro/shu/feicui/yinpu.db \
    FEICUI_ALLOW_PROD_MIGRATE=1 ./.venv/bin/python -m app.migrations
db           = /Users/kevin/bistro/shu/feicui/yinpu.db
prod_db      = True
applied      = 0
skipped      = 2
journal_mode = wal
schema_sha256= d35d052b6aee2a195c6879009c2116b87578a357bbeed829176410ccffd608be
tables       = export_batches,export_records,images,job_pages,jobs,schema_migrations,seals,sqlite_sequence,stamps
exit=0
$ md5 yinpu.db                        # 复跑后
MD5 (yinpu.db) = 56cbf7afd124e86c6d9f810c0380c3eb     # ← 与复跑前**完全相同**
$ sqlite3 yinpu.db 'select count(*) from stamps'
79
$ sqlite3 yinpu.db "select * from stamps order by id" | md5
8a21e57d5bd909fff282214640457c7f                       # ← 与 §2.3 口径 A 相同
```

判定 **幂等成立**：`applied=0/skipped=2`，`schema_sha256` 与首次一致（`d35d052b…608be`），
库 md5、表清单、`stamps` 行数与内容指纹全部不变，**未重复建表、未改数据**。

> **与任务书写法的一处出入（如实报）**：任务书第 5 步预期 `skipped=3`，实测为 **`skipped=2`**。
> 原因：`app.migrations` 的 `MIGRATIONS` 列表**只有 2 个条目**（`1a-0001-jobs`、`1a-0002-stamps-indexes`），
> `skipped` 计的是「已记账而被跳过的迁移条目数」，不是 `schema_migrations` 行数（后者为 2 行亦吻合）。
> 幂等性判定不受影响；此项**不是**数据或结构异常。

## 6. 只读体检 `--status`

```
$ cd server && FEICUI_DB=/Users/kevin/bistro/shu/feicui/yinpu.db ./.venv/bin/python -m app.migrations --status
db            = /Users/kevin/bistro/shu/feicui/yinpu.db
prod_db       = True
journal_mode  = wal
schema_sha256 = d35d052b6aee2a195c6879009c2116b87578a357bbeed829176410ccffd608be
tables        = export_batches,export_records,images,job_pages,jobs,schema_migrations,seals,sqlite_sequence,stamps
indexes       = idx_job_pages_job_chunk,idx_job_pages_job_state,idx_jobs_pdf_path_state,idx_stamps_pdf_page,sqlite_autoindex_export_batches_1,sqlite_autoindex_export_records_1,sqlite_autoindex_images_1,sqlite_autoindex_job_pages_1,sqlite_autoindex_jobs_1,sqlite_autoindex_schema_migrations_1,sqlite_autoindex_seals_1,uq_jobs_active_pdf_path,uq_stamps_pdf_page_idx
applied       = 1a-0001-jobs,1a-0002-stamps-indexes
count[jobs]    = 0
count[job_pages]    = 0
exit=0
```

## 7. 交叉校验：备份（迁移前）vs 现行（迁移后）

用 `ops/prod_migrate_crosscheck.py`（**全 `mode=ro` 只读**）逐表比对，口径 D＝
`SELECT * FROM <t> ORDER BY rowid` 的规范化 JSON（同 B 口径）整体 md5/sha256：

| 表 | 行数 前→后 | md5 | 判定 |
|---|---|---|---|
| `stamps` | 79→79 | `d7abe995bff62761c27052dfc2bdf7bb` → 同 | **SAME** |
| `images` | 79→79 | `110db5676ff5653a53d6b1ca25a75b39` → 同 | **SAME** |
| `seals` | 79→79 | `f2e5f8fac627d98e4a3038a730140b8c` → 同 | **SAME** |
| `export_batches` | 12→12 | `c131728fff35239e568de988ce1234d0` → 同 | **SAME** |
| `export_records` | 49→49 | `b291c936317191e09f6a3cc0b04aa570` → 同 | **SAME** |
| `jobs` / `job_pages` / `schema_migrations` | — → 0/0/2 | 新增 | **NEW** |

判读：**所有迁移前既存表内容与迁移后逐字相同，无 DIFF；无表被删除（GONE = none）**。

独立复核（第三方口径，不依赖我的脚本）：

```
$ sqlite3 "file:yinpu.db.bak-premigrate-202609201241?mode=ro" ".dump stamps" | grep '^INSERT' | md5
d833bea48be065248b11387a3ff792d4
$ sqlite3 yinpu.db                                            ".dump stamps" | grep '^INSERT' | md5
d833bea48be065248b11387a3ff792d4        # ← 完全相同
```

备份库只读复核（证明备份**未被动过**）：`journal_mode=delete`（未开 WAL）、`stamps` 79 行。

## 8. 异常与踩坑（如实记录，含一条作废段落）

1. **【已修正】`sqlite3` CLI 对 WAL 库的只读 URI 打不开** —— 迁移后现行库进入 WAL，
   `sqlite3 "file:<abs>?mode=ro" "select …"` 报 `Error: in prepare, unable to open database file (14)`，
   而 `| md5` 于是算出**空输入**的 md5 `d41d8cd98f00b204e9800998ecf8427e`。
   首次交叉校验（原始输出 `[7]` 段）因此出现 5 个假 `DIFF`，**已判定作废**并在原始输出文件中保留留痕，
   修正版为 `[7-修正]` 段（结论以修正版为准）。**教训：把 `md5 of empty string` 误读成「数据被改了」是这个陷阱的典型后果，
   凡哈希比对必须同时打印行数/字节数。** 现行库的只读取证改用 Python `sqlite3` 的 `mode=ro` URI（对 WAL 可用，已实测）。
2. **`.tables` 多出一张 `sqlite_sequence`** —— 这是 `job_pages` 用了 `AUTOINCREMENT` 触发的 SQLite 内部表，
   属迁移的必然副产物，非业务表、无数据风险。
3. **`skipped` 实测 2 而非任务书预期的 3** —— 见 §5 说明，`MIGRATIONS` 只有 2 条。
4. 负向对照（§3a）为**故意**执行的拒绝路径，退出码 3、零写入，用于证明安全闸有效。
5. **WAL 副产物文件** —— 开启 WAL 后同目录出现 `yinpu.db-shm`（32768 B）与 `yinpu.db-wal`。
   这是 WAL 模式的正常伴生物（任何一次对 WAL 库的连接都会创建），**不是**额外数据改动：
   封账时 `yinpu.db-wal` = **0 字节**（无未落盘事务），且 `yinpu.db` md5 始终为 `56cbf7af…c3eb`。
   `yinpu.db.bak-f2` 与备份文件均**无** `.db-*` 伴生文件。
6. **非本单产生的同窗口改动（如实标注）** —— 全仓 mtime 扫描发现
   `qa-recheck/p1b-neng/evidence/00_md5_start.txt` 在 12:42 被写过。**该文件非本单写入**
   （本单只写 `yinpu.db`、备份、`ops/` 下 4 个文件），来源是并行任务（Neng 侧 `server/**` 一路）。
   本单**未触碰** `qa-recheck/**` 与 `qa-baseline/**` 任何文件。

### 8.1 改动范围证明（全仓 mtime 扫描）

```bash
find /Users/kevin/bistro/shu/feicui -newermt '2026-09-20 12:41:00' -type f \
     -not -path '*/__pycache__/*' -not -path '*/.venv/*' -not -path '*/venv/*'
```

输出（`feicui/` 全仓，本单窗口 12:41–12:43 内被修改的**全部**文件）：

```
/Users/kevin/bistro/shu/feicui/yinpu.db                      ← 迁移目标
/Users/kevin/bistro/shu/feicui/yinpu.db-shm                  ← WAL 副产物
/Users/kevin/bistro/shu/feicui/yinpu.db-wal                  ← WAL 副产物（0 B）
/Users/kevin/bistro/shu/feicui/ops/prod_migrate_evidence.md
/Users/kevin/bistro/shu/feicui/ops/prod_migrate_before_after.txt
/Users/kevin/bistro/shu/feicui/ops/prod_migrate_fingerprint.py
/Users/kevin/bistro/shu/feicui/ops/prod_migrate_crosscheck.py
/Users/kevin/bistro/shu/feicui/qa-recheck/p1b-neng/evidence/00_md5_start.txt   ← 并行任务所写，非本单
```

禁改路径 mtime 复核（全部**早于**本单窗口，未被触碰）：

| 路径 | mtime |
|---|---|
| `processor.py` | 2026-09-20 10:07:39 |
| `export.py` | 2026-09-20 09:03:06 |
| `app.py` | 2026-09-17 06:39:30 |
| `server/app/migrations.py` | 2026-09-20 11:51:15 |
| `server/app/db.py` | 2026-09-20 11:36:12 |
| `server/app/config.py` | 2026-09-20 12:14:37 |
| `server/app/pool.py` | 2026-09-20 12:15:16 |
| `server/app/repository.py` | 2026-09-20 12:14:29 |
| `server/app/__init__.py` | 2026-09-20 12:15:19 |
| `server/README.md` | 2026-09-20 12:17:58 |
| `docs/feicui.spec.md` | 2026-09-20 12:10:05 |
| `web/`（目录） | 2026-09-20 12:12:06 |
| `docs/`（目录） | 2026-09-20 12:03:23 |
| `qa-baseline/`（目录） | 2026-09-20 10:54:31 |

> `shu` 不是 git 工作树（`git rev-parse` 失败），故用 mtime 全仓扫描替代 `git status` 作为改动范围证明。

## 9. 交付文件与最终 md5

```
-rw-r--r--@ 1 kevin staff  638976 Sep 20 12:42 yinpu.db                        (inode 59624593，未换文件)
-rw-r--r--@ 1 kevin staff   32768 Sep 20 12:43 yinpu.db-shm                    (WAL 副产物)
-rw-r--r--@ 1 kevin staff       0 Sep 20 12:42 yinpu.db-wal                    (WAL 副产物，0 B)
-rw-r--r--@ 1 kevin staff  466944 Sep 20 10:04 yinpu.db.bak-f2                 (未触碰)
-rw-r--r--@ 1 kevin staff  577536 Sep 20 10:08 yinpu.db.bak-premigrate-202609201241
```

| 文件 | md5 |
|---|---|
| `yinpu.db`（迁移后） | `56cbf7afd124e86c6d9f810c0380c3eb` |
| `yinpu.db.bak-premigrate-202609201241` | `254d3ff132d3a8d14dcf8590f45c7232` |
| `ops/prod_migrate_before_after.txt` | `677655cddbaecf6ad1f9a6d70e1db6e7` |
| `ops/prod_migrate_evidence.md` | 见交付回复（本文件自身哈希随回写变化） |
| `ops/prod_migrate_fingerprint.py` | `1d06de310f80dc84bedb73cb57f8eb17` |
| `ops/prod_migrate_crosscheck.py` | `1ca240caeb72964c0a2060b1a5254d68` |

**回滚方式（如需）**：把 `yinpu.db.bak-premigrate-202609201241` 拷回 `yinpu.db` 即可；
注意备份为 `journal_mode=delete` 版本，回滚后 WAL 状态亦一并复原。回滚动作**不在本单范围内**，未执行。

## 10. 结论

**`stamps` 的 10 列与 79 条数据逐字未变。** 迁移只做了加法：新增 3 张空侧表（`jobs`/`job_pages`/`schema_migrations`）
与 6 个显式索引，并把 `journal_mode` 由 `delete` 改为 `wal`；`schema_sha256` 复跑不变，迁移幂等成立。
全程未启动任何服务、未占用任何端口、未重启面板、未 kill 任何进程、未改动 `server/**` 任何源文件。
