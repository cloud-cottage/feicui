# 关联面（三表联立）· 拆解件 v0.1

> 状态：**待 Kevin 裁定「交付形态」后派实现单**（Zang 2026-10-10 起草；口径真源＝本轮实测）。
> 背景：Kevin 2026-10-10 裁定「印人关联面本轮先不导入、作为独立需求另开」；本条即该**独立需求**。三条采集线（印人 / 印谱 item / 印章 seal）**各自的关系数据已全部落在 feicui 库内**，本需求把它们缝成**一致的关联面**并产出面向 xiai 的**候选关系包**。

---

## 1. 三条线现存的关系数据（实测，2026-10-10）

| 库表 | 行数 | 关系语义 | 关键列 |
| --- | ---: | --- | --- |
| `person_ingest.db::person_relations` | **1650** | 印人 →（印谱 1349 / 印章 301） | `source_person_id`, `kind`, `ref_id`, `name`, `desc`, `creator_type`, `image_key`, `as_book_id`, `has_image`, `seq` |
| `item_ingest.db::item_creators` | **1440** | 印谱 → 印人 | `source_item_id`, `creator_type`, `creator_role`, `creator_relator`, `creator_name`, `person_grbsm`, `source_face`（`book_graph` 1281 / `person_graph` 159）, `seq` |
| `seal_ingest.db::seal_links` | **8964** | 印章 →（印谱 3679 / 印人 5285） | `source_seal_id`, `link_kind`（`book` 3679 / `person_yz` 2379 / `person_zzkz` 2652 / `person_bkzkz` 254）, `ref_id`, `ref_name`(+`_chs`), `creator_type`, `bridge_item_id`, `source_face`（恒 `seal_row`）, `seq` |

⚠ `person_relations` **无 `source_face` 列**（其来源恒为 `graph/person`）；`seal_links` 的 `source_face` 恒 `seal_row`；item 侧才有两源。

## 2. 可连键对账（**本需求的基础；全部实测**）

| 连接 | 读数 | 结论 |
| --- | --- | --- |
| `person_relations(印谱).as_book_id` → `items.as_book_id` | 唯一 932 → **命中 931 / 未命中 1** | 唯一未命中值 ＝ **`test`**（源侧测试占位行，印人名「【测试】印谱平台数据全样例…」；items 内无此书）⇒ **源侧幽灵行，登记不判负** |
| `person_relations(印谱).ref_id` → `items.source_item_id` | 唯一 932 → **命中 931** | 与上行同源，命中率一致 |
| `person_relations(印章).ref_id` → `seals.source_seal_id` | 261 → **命中 261/261（0 未命中）** | **印人侧印章关联天然接入印章表** |
| `person_relations(印章).image_key` → `seal_images.source_ref` | 261 → **命中 261/261** | **可精确接到影像面**（形如 `19_3250_1`） |
| `seal_links(book).ref_id` → `items.as_book_id` | 唯一 19 → **19/19** | 印章只涉 19 种印谱 |
| `seal_links(book).bridge_item_id` → `items.source_item_id` | 19 → **19/19** | 桥接键可用 |
| `item_creators.person_grbsm` → `persons.source_person_id` | 535 → **535/535** | 无未命中 |
| `seal_links(person_*).ref_id` → `persons.source_person_id` | 41 个 id → 命中 27 / **未命中 14** | **源侧引用未收录**（同一现象已由 Neng 在行数面量过：印主 8/438、篆者 1/403、边款篆者 6/11）⇒ 不判负，但**必须计数入包** |
| **去重面**：`item_creators(book_graph)` 1281 对 vs `person_relations(印谱)` 1349 对 | **交集 1249**；only-item 32；only-person 100 | **两源共报同一事实 1249 条** ⇒ 合并后并集 **1381 对**；provenance 需保留双源标记 |

**涉及实体规模**：印人 570 人中 539 出现在 `person_relations`、535 在 `item_creators`、27 在 `seal_links`；印章关联涉印人 261 枚唯一边；`person_relations(印章)` 的 `creator_type` **全为「印主」**，**40 个印章 ref 挂了多人**（源侧多主归属，照登）。

## 3. 候选统一模型（**待 xiai 裁定**，默认值已给）

统一「关系边」（edge）表，一行一条：

```json
{"predicate":"person_to_item|item_to_person|person_to_seal|seal_to_item|seal_to_person",
 "subject_type":"person|item|seal", "subject_id":"…",
 "object_type":"person|item|seal", "object_id":"…",
 "role":null, "role_note":null, "evidence":["person_graph","book_graph"],
 "source_ref":null, "image_ref":null, "name":null, "name_chs":null, "seq":0, "batch_id":"relation_20261010_01"}
```

| 口径项 | 默认（一句话可改） | 需 xiai 确认 |
| --- | --- | --- |
| **R-a 边数与方向** | **保留两向**（`person_to_item` 1349 ＋ `item_to_person` 1440）；理由＝两向的 `role`/`creator_type` 语义不同（印人侧给「辑、刻」，印谱侧给 `creator_role`/`creator_relator`） | 是否只留单向 ＋ 方向字段 |
| **R-b 去重** | 同一 `(subject,object,predicate)` 只一行，**`evidence` 数组保留双源**（去重后 1249 条标 `["person_graph","book_graph"]`） | 是否拆成两行以保留各源原字段 |
| **R-c 幽灵/未收录** | **保留并标记**（`as_book_id='test'` 1 条标 `ghost:true`；14 个未收录印人 id 保留原值、另给 `person_resolved:false`） | 是否剔除 |
| **R-d 印章的角色口径** | `seal_links` 的 印主/篆者/边款篆者 5285 条**全部保留并带 `link_kind`**；`person_relations(印章)` 的 301 条（`creator_type` 恒「印主」、带 `image_key`）**另标 `evidence:["person_graph"]`** —— 二者**粒度不同**（前者来自印章行的 `sealYz`/`sealYzzkzId`/`sealBkzkzId`，后者来自印人详情页关联图），默认**都留** | 是否合并为同一 predicate |
| **R-e 幂等键** | `(predicate, subject_id, object_id)` | 是否用合成 hash |
| **R-f 包形态** | `exports/relation_import_relation_20261010_01/`：`relations.jsonl` ＋ `manifest.json`（`key_face_status:"pending_xiai"`）＋ `report.json`（各 predicate 计数 / 去重前后 / 未命中清单） | 集合名 / 键面 / 导入通道（**同三线：归 xiai 定**） |

**去重前原始行合计 12054**（1349 ＋ 1440 ＋ 301 ＋ 3679 ＋ 5285）；去重后按 R-a/R-b 口径重算。

## 4. 产出与验收判据（拟）

- **A-1**：`relations.jsonl` 各 predicate 行数与 `report.json` 场景计数一致（逐类给数）。
- **A-2**：去重算术自洽 —— `|A ∪ B| = |A| + |B| − |A ∩ B|` 逐项可复算（1349+1281−1249=1381 形式）。
- **A-3**：**可连键**逐条成立：每条 `person_to_item` 的 `object_id` ∈ `items.source_item_id`（除 `ghost` 标记行）；每条印章边 `subject_id` ∈ `seals.source_seal_id`。
- **A-4**：未命中/幽灵行**有清单与计数**（不为 0 时必须逐条列出）。
- **A-5**：**门禁指纹**三库（`yinpu.db`/`person_ingest.db`/`item_ingest.db`/`seal_ingest.db` 的采集面）与三条既有就绪包**未变**（本需求只读三库、只新增自己的包）。
- **A-6**：重建幂等（仅时间戳变、JSONL 字节不变）；`key_face_status: "pending_xiai"`。
- **A-7**：**不新增采集请求**（零联网）——本需求是**纯本库联立**，不得再打复旦站点（四线既有数据已够）。

## 5. 边界

- feicui 侧只做：**读三库 → 联立/去重/归一 → 产出候选关系包 ＋ 报告**；**不写 xiai 任何文件、不调云函数**。
- **不重新联网采集**；**不改**三线的库与包（只读）。
- 新独立产物目录与规范节（`feicui.spec.md` §3.18）＋ AC ＋ R 计数由 Jing 走 §0.4 落册。
