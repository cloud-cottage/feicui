# 关联面（三表联立）· 交付报告（Kong / 2026-10-10）

> 仓：`/Users/kevin/bistro/xiai/feicui`（main；实现前 HEAD ＝ `3df0dae`）。口径真源 ＝ `docs/relation-ingest-draft-v0.1.md`；规范 ＝ `docs/feicui.spec.md` §3.18（v1.20，Jing）。
> 本需求：**纯本库联立、零联网**。三条线的关系数据全在库内，缝成统一关系边并产出面向 xiai 的候选关系包。

## 0. 交付物清单

- [x] `server/app/relations.py`（核心：三库只读 → 归一 → 去重 → 产出包；CLI）
- [x] `server/app/routers/relations.py`（两 additive 端点）
- [x] `server/app/main.py`（接线）／`server/app/config.py`（新增 `relations_export_root`，additive）
- [x] 就绪包 `exports/relation_import_relation_20261010_01/`（3 文件）
- [x] `ops/relation-ingest/**`（九行对账 + 门禁指纹 + 幂等 + 包自检；脚本可复跑）
- [x] 提交（不 push）——见 §9

## 1. 各 predicate 行数（去重前 / 后）

| predicate | 去重前（原始行） | 去重后 | 合并 |
| --- | ---: | ---: | ---: |
| `person_to_item`（person_relations 印谱） | 1349 | **1349** | 0 |
| `item_to_person`（item_creators，两源交叉重复 61） | 1440 | **1379** | 61 |
| `person_to_seal`（person_relations 印章） | 301 | **301** | 0 |
| `seal_to_item`（seal_links book） | 3679 | **3679** | 0 |
| `seal_to_person`（seal_links person_*，同 (seal,person) 多角色合并 2017） | 5285 | **3268** | 2017 |
| **合计** | **12054** | **9976** | **2078** |

> `relations.jsonl` 行数 ＝ **9976**；`(predicate,subject_id,object_id)` 三元组**全唯一**（9976/9976）。
> 规范 §3.18.4「去重前原始行合计 12054」照登；去重后 **9976**（R-a 保两向、R-b 同 `(subject,object,predicate)` 合并）。

## 2. 去重算术逐项（A-2 / AC-56）

**去重面**（跨表，两源共报同一事实）：

| 项 | 值 |
| --- | ---: |
| \|A\| ＝ `item_creators(source_face='book_graph')` 对 (person,item) | 1281 |
| \|B\| ＝ `person_relations(kind='印谱')` 对 (person,item) | 1349 |
| \|A ∩ B\| | **1249** |
| only-item（A−B） | 32 |
| only-person（B−A） | 100 |
| **\|A ∪ B\| ＝ 1281 + 1349 − 1249** | **1381** |

**行内去重**（同 predicate 内同 `(subject,object)`）：

- `item_to_person`：1440 − **61** ＝ 1379（61 组均为 **跨源** `book_graph` ∩ `person_graph` 的同一 (item,person) ⇒ `evidence:["person_graph","book_graph"]`）。
- `seal_to_person`：5285 − **2017** ＝ 3268（同一 (seal,person) 在 印主/篆者/边款篆者 多面重复 ⇒ 合并为一行、`role` 以 `|` 保留各面）。
- 其余 predicate 行内无重复（person_to_item 1349 / person_to_seal 301 / seal_to_item 3679 组内全唯一）。

**evidence 双源计数**：`person_graph+book_graph` ＝ **2498**（＝ person_to_item 侧 1249 ＋ item_to_person 侧 1249）；`person_graph` 单源 499；`book_graph` 单源 32；`seal_row` 6947。

## 3. 九行对账逐条读数（独立重算，`02_recon.py` → `02_recon.json`）

| # | 连接 | 唯一 | 命中 | 未命中 | 未命中清单 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | `person_relations(印谱).as_book_id` → `items.as_book_id` | 932 | 931 | **1** | `test` |
| 2 | `person_relations(印谱).ref_id` → `items.source_item_id` | 932 | 931 | **1** | `103` |
| 3 | `person_relations(印章).ref_id` → `seals.source_seal_id` | 261 | 261 | 0 | — |
| 4 | `person_relations(印章).image_key` → `seal_images.source_ref` | 261 | 261 | 0 | — |
| 5 | `seal_links(book).ref_id` → `items.as_book_id` | 19 | 19 | 0 | — |
| 6 | `seal_links(book).bridge_item_id` → `items.source_item_id` | 19 | 19 | 0 | — |
| 7 | `item_creators.person_grbsm` → `persons.source_person_id` | 535 | 535 | 0 | — |
| 8 | `seal_links(person_*).ref_id` → `persons.source_person_id` | 41 | 27 | **14** | 见 §4 |
| 9 | 去重面（见 §2） | — | — | — | ∩1249 / ∪1381 |

**与拆解件 §2 逐条一致**（第 1 行「唯一 932 → 命中 931 / 未命中 1」；第 8 行「41 个 id ⇒ 命中 27 / 未命中 14」；第 9 行「交集 1249 / only-item 32 / only-person 100 / 并集 1381」）。
**涉及实体规模**：印人 570 中 539 在 `person_relations`、535 在 `item_creators`、27（解析后）在 `seal_links`；印章关联涉印人 261 唯一边；`person_relations(印章)` 的 `creator_type` 全为「印主」、**40** 个印章 ref 挂了多人。

## 4. 未命中 / 幽灵清单（A-4；不为 0 必逐条列出）

**幽灵（`ghost:true`）——`as_book_id='test'` 源侧测试占位行**：

| predicate | subject_id | object_id | evidence | source_ref | name |
| --- | --- | --- | --- | --- | --- |
| person_to_item | 907118823 | 103 | ["person_graph"] | test | 【测试】印谱平台数据全样例，请勿改动… |
| person_to_item | 907135358 | 103 | ["person_graph"] | test | 【测试】印谱平台数据全样例，请勿改动… |

> **计数口径**：`as_book_id` 唯一值 **1 个（`test`）**（照拆解件 §2 唯一口径）；**行 2 条**（两印人各挂同一 `ref_id=103`）。包内 `ghost` 逐行标 true ⇒ **ghost 行 ＝ 2**、`ghost_unique_as_book_id ＝ ["test"]`。

**未收录印人 id（`person_resolved:false`）—— 14 个**（`seal_links(person_*)` 引用未在 `persons` 内）：

`907057883` `907195552` `907196266` `907289639` `907302845` `907352770` `907355275` `907442887` `907564849` `907565309` `907565542` `907565815` `907566509` `907567697`

**`ref_id` 未命中 person 库（按面分列 ＋ 合计，沿 §3.17.8 a-v1.19 ①）**：

| 面 | 标签 | 行数 | 唯一 ref | 未命中唯一 |
| --- | --- | ---: | ---: | ---: |
| `person_yz` | 印主 | 2379 | 19 | 8 |
| `person_zzkz` | 篆者 | 2652 | 10 | 1 |
| `person_bkzkz` | 边款篆者 | 254 | 21 | 6 |
| **合计** | — | 5285 | 41 | **14** |

## 5. 包内文件与行数

目录 ＝ `exports/relation_import_relation_20261010_01/`

| 文件 | 大小 | 行数 | 说明 |
| --- | ---: | ---: | --- |
| `relations.jsonl` | 3,653,848 B | **9976** | 统一关系边（16 键稳定序、UTF-8、无 BOM） |
| `manifest.json` | 10,668 B | — | `schema_version=1` / `key_face_status:"pending_xiai"` / 字段字典 / 各 predicate 计数 / 幂等唯一计数 / 覆盖统计 / R-a〜R-f / 九行对账 |
| `report.json` | 9,847 B | — | 各 predicate 计数 / 去重前后 / 九行对账 / 幽灵·未收录清单 / 门禁指纹 |

`relations.jsonl` sha256 ＝ `12d103a63f96a61667a45652ca8fc8d01fa8ee9617f1367073721ff4eadffc10`（CLI 与端点**逐字节一致**）。

## 6. 门禁指纹（before / after；内容指纹，**禁用库文件 md5**）

`03_guard.py before/after` → `03_guard_before.json` / `04_guard_after.json`（逐表行数 ＋ 有序全字段 sha256）。

| 库 | 表（行数） | before ＝ after |
| --- | --- | :---: |
| `yinpu.db` | stamps 89 / jobs 5 / job_pages 32 / seals 79 / images 79 / export_batches 12 / export_records 49 / schema_migrations 2 | ✅（8 表 sha256 全同） |
| `var/person_ingest.db` | persons 570 / person_relations 1650 / person_import_batches 1 | ✅ |
| `var/item_ingest.db` | items 1742 / item_creators 1440 / item_import_batches 1 | ✅ |
| `var/seal_ingest.db` | seals 3679 / seal_links 8964 / seal_images 6765 / seal_import_batches 1 | ✅ |

**三线既有就绪包**（树指纹 sha256_names_sizes）：

| 包 | n_files | before ＝ after |
| --- | ---: | :---: |
| `exports/person_20261010_01` | 4 | ✅ `8c8c0a1f…` |
| `exports/person_import_person_20261010_01` | 3 | ✅ `756b5bd4…` |
| `exports/item_import_item_20261010_01` | 4 | ✅ `d7ba7723…` |
| `exports/seal_import_seal_20261010_01` | 6352 | ✅ `46013d67…` |

⇒ **四库 × 三包 逐字节未变**（本需求只读、只新增自有 `relation_import_*` 包）。

## 7. 重建幂等读数（A-6 / AC-60；`06_idempotency.json`）

- CLI `package` 连跑 2 次，退出码 0/0；
- `relations.jsonl` sha256 **三次全同**（`12d103a6…`）⇒ **内容逐字节不变**；
- `manifest.created_at` / `report.generated_at`：`21:44:33+08:00 → 21:44:37+08:00`（**仅时间戳变**）；
- 门禁：`dbs_unchanged=true`、`packages_unchanged=true`。

## 8. 端点验活（改码后单路重启，真 PID）

- 重启前 `feicui-api` PID **80441**（6:46PM 起，旧码）；单路重启后 PID **80097**（9:44PM 起，新码）。
- `GET /api/relations/summary` ⇒ **200**：predicate 计数 / 去重前后（12054→9976）/ ghost 2 / unresolved 14（只读、不落盘）。
- `POST /api/relations/package?batch_id=relation_20261010_01` ⇒ **200**（rows 9976、`key_face_status:"pending_xiai"`）。
- `POST /api/relations/package`（无参）⇒ **200**（缺省＝既有最新批次）。
- `POST /api/relations/package?batch_id=relation_19990101_01` ⇒ **404** `BATCH_NOT_FOUND`；`?foo=1` ⇒ **400** `UNSUPPORTED_PARAM`（结构化 JSON）。
- `GET /api/relations/summary?cursor=x` ⇒ **400** `UNSUPPORTED_PARAM`。
- 错误体 `content-type: application/json`（**绝不 HTML**）。
- **additive 回归**：`/api/persons|items|seals`、三线 `/batches`、`/api/health`、`/api/jobs` 全 **200**（未动 E1〜E7 与既有 S/Q 端点）。
- 包自检（`05_package_selfcheck.py`）：形态 PASS / 无 BOM / 计数一致 / 三元组唯一 / 去重算术自洽 / A-3 可连键 PASS / manifest 必含项 PASS / `key_face_status=pending_xiai`；**旧形态 FAIL 对照 PASS**（`evidence` 由真数组改字符串 ⇒ 形态判据判负）。

## 9. 提交哈希与未完成项

- **实现提交**：`615a5d8`（feat(feicui): 关联面（三表联立）—— 统一关系边 + 两 additive 端点 + 就绪包）。
  实现前 HEAD ＝ `83aa96a`（Jing 的 spec v1.20 提交，位于本次派单预期的 `3df0dae` 之上）。
- **只暂存本单点名文件**（`server/app/{relations.py,routers/relations.py,main.py,config.py}` ＋ `ops/relation-ingest/**`）；**未 `git add -A`**、**未暂存** `docs/relation-ingest-draft-v0.1.md`（Zang 的拆解件，仍留 untracked 由期归属方处理）、**未 push**。
- **零联网**：`relations.py` / `routers/relations.py` **无任何 HTTP/网络导入**（仅 `sqlite3`/`json` 等）；端点只读三库。
- **未完成/待裁**：无阻塞项。跨工程待 xiai 裁定者（键面 / 集合名 / 导入通道 / 合成 hash）已登记于包 `manifest.r_defaults` 与 §3.18.4，**本侧按默认值交付、拿到键面二次出包不重采**。
