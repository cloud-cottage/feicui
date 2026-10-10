# 「印谱」（item）概念与采集线拆解草案 v0.1

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **草案（非规范）**。本件是 **Zang 的拆解产物**，**不得被引为规范条款**。feicui 侧正式落规范由 Jing 执行（新增 §3.16）；**xiai 侧模型 / 集合名 / 导入通道归 xiai 线**（Kevin 2026-10-10 裁定）。 |
| 时点 | 2026-10-10（CST）。凡引现状读数均带来源与核验时点。 |
| 任务来源 | Kevin 2026-10-10：**新建概念 `item`，对应 feicui 导入数据中的「印谱」概念；把目标数据里的 item 数据导入 xiai。** |
| 归属 | **数据供给侧 ＝ feicui 线**（采集 / 归一化 / 落 feicui 独立库 / 产出 xiai 就绪包）；**写入侧 ＝ xiai 线**（模型 / 集合名 / 导入通道 / 审核门；沿用 person 的三段式：暂存 → 审核 → 定稿）。**feicui 不写 xiai 任何文件、不调云函数、不碰 CloudBase。** |
| 未动作声明 | 本件只写文档：未跑采集 / 未起服务 / 未占端口 / 未写任何生产数据。 |

---

## 1. Kevin 门控四答（逐字口径，本件的输入）

| # | 问题 | 裁定 |
| --- | --- | --- |
| I-1 | **item 范围** | **全集 1742 本**（新采 `book/list` 全量）——「item 是『印谱』实体表，不应只装印人关联子集」 |
| I-2 | **采集深度** | **列表 ＋ detail（不采 graph）**：有结构化责任者（`creatorList` / `titleList` / `itemList` / `bookDonor`），**无印人关联面** |
| I-3 | **模型与通道归属** | **归 xiai 线**：本线出拆解草案 ＋ 采集 ＋ xiai 就绪包；**他们定 item 模型、集合名与导入通道**（沿用 person 三段式：暂存 → 审核 → 定稿） |
| I-4 | **印谱↔印人关联** | **随包交付 sidecar**（`item ↔ person`：`creatorType` ＋ `personGrbsm`），**是否入 xiai 由他们定** |

> **I-2 与 I-4 的一致化（实测支撑，非自行发明）**：不采 `graph/book` 也能出关联 —— **`book/detail` 的 `creatorList[]` 直接给 `personGrbsm`**（实测 `愚公自用印存`：`[{creatorType:'辑', creatorRole:'creator', creatorRelator:'edt', creatorName:'李鐘', personGrbsm:'907568497'}, …]`）。另可用**既有印人侧关联**（`person_relations` 的 `kind='印谱'`，1349 行 / 去重 932 本，含 `as_book_id` / `creatorType`）**互补**，经 `asBookId ↔ seqid` 映射接入；sidecar 每行标注来源面（`book_detail.creator_list` / `person_graph`）。

---

## 2. 数据源事实基线（**只读实测**）

**核验时点 2026-10-10；核验人 Zang；证据 ＝ 本机 curl / headless Chrome 钩取 XHR / 全量落盘 `fudan_books_raw.json`。**

| 端点 | 方法 | 入参 | 说明 |
| --- | --- | --- | --- |
| `/service_yinpu/book/list` | POST | `{pageNum, pageRows, fullText, facetBookCbz, yearRange, facetBookDonator, orderField, orderType}` | **`pageRows=3000` 一次取全 1742 本**（`total=1742`） |
| `/service_yinpu/book/detail/<seqid>` | GET | **路径参数 ＝ `seqid`** | 详情（**非同构**：多出 `creatorList` / `titleList` / `itemList` / `bookDonor`）；`/book/detail/<asBookId>` ⇒ **`code:404 数据或资源不存在`** |
| `/service_yinpu/book/facet` | POST | `{fullText}` | 分面（有无影像 / 年份 / 出版者 / 捐赠者 / 来源） |
| `/service_yinpu/graph/book/<seqid>` | GET | 路径参数 ＝ `seqid` | **印谱↔印人 ＋ 印章**（**本轮不采**，I-2）；`asBookId` 传入 ⇒ `印谱id错误` |
| `/service_yinpu/statistic/home` | GET | — | 站点计数：`bookCount=1742` / `personCount=570` / `sealCount=716` |

**列表字段覆盖（1742 本实测）**

| 字段 | 非空 | 说明 |
| --- | --- | --- |
| `seqid` | 1742 | **内部键**（详情 / graph 的路径参数） |
| `asBookId` | 1742 | **补零业务号**（如 `0307`）——**印人侧关联用的就是它** |
| `asId` / `bookUri` | 1742 | 上游 id / GUID |
| `bookFl` | 1742 | 分类（恒「印谱」） |
| `bookTitleZheng` / `bookTitleZhengChs` | 1742 | **正题名 繁 / 简** |
| `bookYz` | 1742 | 语种（`chi`） |
| `hasImage` / `hasAnnotation` | 1742 | 有无影像 / 有无释文（实测 `hasImage=1` **1714** 本） |
| `bookCs` | 1729 | **卷册数** |
| `bookCbLsjn` | 1625 | **成谱纪年原文**（如「清宣統二年」） |
| `bookCbGyjn` | 1076 | **成谱公元年** |
| `bookTynr` / `bookTynrChs` | 753 | **题要长文 繁 / 简** |
| `bookTymc` | 752 | 题要名（如「松蔭軒題要」） |
| `bookBbx` | 456 | 版本/板框信息 |
| `bookCbz` | 113 | 出版者 |
| `bookTitleQt` / `bookTitleQtChs` | 92 | 其他题名 |
| `bookZzxs` / `bookCj` / `bookSk` / `bookSz` | 28 / 19 / 14 / 9 | 撰作 / 丛辑 / 书口 / 书签 |
| `bookPsqk` | 1 | 破损情况 |

**详情独有字段**：`creatorList[]`（**结构化责任者**：`seqid` / `creatorId` / `bookSeqid` / **`creatorType`**（辑 / 刻印…）/ `creatorRole`（`creator`）/ `creatorRelator`（`edt`）/ `creatorRef` / **`creatorName`** / **`personGrbsm`**）、`titleList[]`、`itemList[]`（卷册条目：`kmType` / `kmContent` / `kmLevel` / `kmUri` …）、**`bookDonor`**（藏家，实测恒「林章松」）。覆盖待采集时实测（抽样 4 本中 1 本 `creatorList` 非空）。

---

## 3. 拟采字段面（item 本体，落 feicui 独立库）

| 目标字段 | 源 | 规则 |
| --- | --- | --- |
| `source_item_id` | `seqid` | **幂等键**（原样字符串） |
| `as_book_id` | `asBookId` | 原样（**桥接印人侧关联的键**） |
| `as_id` / `book_uri` | `asId` / `bookUri` | 原样 |
| `category` | `bookFl` | 原样（「印谱」） |
| `title` / `title_chs` | `bookTitleZheng` / `…Chs` | 原样（**繁体为正、简体入 `*_chs`**） |
| `title_other` / `title_other_chs` | `bookTitleQt` / `…Chs` | 原样 |
| `volume_count` | `bookCs` | 整数或 `null`（**不设特值**） |
| `date_text` | `bookCbLsjn` | 原样（纪年原文） |
| `date_year` | `bookCbGyjn` | 整数或 `null` |
| `publisher` | `bookCbz` | 原样 |
| `abstract` / `abstract_chs` | `bookTynr` / `…Chs` | 原样（长文） |
| `abstract_title` | `bookTymc` | 原样 |
| `edition` | `bookBbx` | 原样 |
| `donor` | `bookDonor`（详情独有） | 原样 |
| `has_image` / `has_annotation` | 同名字段 | 布尔 |
| `language` | `bookYz` | 原样 |
| `misc.*` | `bookZzxs` / `bookCj` / `bookSk` / `bookSz` / `bookPsqk` | 原样（低频字段，收在一个子对象，**不散落顶层**） |
| `raw_json` | 列表行 ＋ 详情行 | **保留源原文**（不得丢源） |
| `batch_id` / `updated_at` | — | 系统写 |

**sidecar `item_creators`（item↔person）**：`source_item_id`（＝seqid）/ `creator_type` / `creator_role` / `creator_relator` / `creator_name` / **`person_grbsm`** / `source_face`（`book_detail.creator_list` \| `person_graph`）/ `seq`。

> **注**：`source_face` 是**关联来源面**（用于去重与可追溯），与 person 侧被 Kevin 裁定删除的 `from`（姓名抽取的源字段名）**不是同一概念**。

---

## 4. 批划分

### 批 1（feicui 侧，本线交付）
1. **新页签「印谱采集」**（第三页签；与【印谱解析】【印人采集】并列）＋ 路由 **`/items`**（history 取 `import.meta.env.BASE_URL`）。
2. **后端（5196，additive）**：`POST /api/items/sync`（`book/list` 1 次取全 1742 → 逐本 `book/detail` → 归一化 → 落本库 → 产就绪包；**可断点续跑 + 礼貌限速 + 失败清单**）；`GET /api/items`（分页/筛选）；`GET /api/items/{seqid}`；`GET /api/items/batches`。
3. **存储**：**新独立库 `feicui/var/item_ingest.db`**（表 `items` / `item_creators` / `item_import_batches`）——**与 `person_ingest.db` 分库**（互不干扰）；`yinpu.db` 一字不碰。
4. **就绪包**：`feicui/exports/item_import_<batch_id>/`：`items.jsonl`（**候选键面**，见 §5）+ `item_creators.jsonl`（sidecar）+ `manifest.json`（字段字典 / 行数 / 幂等键唯一计数 / 覆盖统计 / **「键面待 xiai 定」明示**）。
5. **采集量预估**：1743 请求（list 1 + detail 1742）；按 0.5 s/请求 ≈ **20–25 min**；**限流风险实测存在**（见 §6）⇒ 必须分片续跑。

### 批 2（xiai 侧，归 xiai 线）
1. 定 **item 模型**（`xiai_items`? 集合名待其裁定）＋ 字段面 ＋ 是否收 `item_creators` 关联。
2. 定**导入通道**（沿用 person 三段式：`submitItemImport` → 暂存（PENDING）→ 管理员在「我的勘误记录」批量采纳 → 正式集合）。
3. 定**就绪包键面裁剪**（本线按其键面二次出包 —— 与 person 流程同型）。
4. 采集侧只剩「按最终键面重出包」，**无需重新联网**（feicui 本库已存全字段 ＋ `raw_json`）。

---

## 5. 就绪包（候选键面，待 xiai 定）

- `items.jsonl`：一行一对象、UTF-8、无 BOM、一行一对象；字段面 ＝ §3 的 item 本体（**键面未定前不裁剪**，由 `manifest.json` 给出**字段字典**供 xiai 线挑选）。
- `item_creators.jsonl`：一行一对象（§3 末表）。
- `manifest.json` 必含：`schema_version`（本版钉 **1**）、源端点（含 `pageRows:3000` 全量口径）、源侧 `total`（1742）、各文件行数、**字段字典**、幂等键（`source_item_id`）唯一计数、覆盖统计、**`key_face_status: "pending_xiai"`**。
- **交付缝定位**：与 person 一致 —— feicui 出包、写 xiai 归他们；**本线不写 xiai 任何文件、不调云函数**。

---

## 6. 硬约束与已知风险

- **只加法**：不动 `stamps` / `jobs` / `yinpu.db` / `output/` / 既有 `exports/fb_*` / `exports/person_*` / `var/person_ingest.db`。
- **零外链资源**（页面离线自洽）；**联网只在 feicui 服务端且只读**。
- **限流（实测）**：站点点级窗口限流 —— 超频回包 **HTTP 200 ＋ `code:"429"`（字符串）＋ `status:true` ＋ 无 `data`**（印人侧实测，约 150 s 自愈）；`detail` 类端点更敏感。⇒ **分片续跑 + 退避 + 失败清单可复算**，不得把 429 当成功。
- **禁止**：不写 xiai 文件 / 不调云函数 / 不碰 `ctrl/**` / 不占新端口。
- **判据用内容指纹，禁用数据库文件 md5**。

---

## 7. 建议验收判据（批 1，供 Jing 落成 AC）

| # | 判据 |
| --- | --- |
| IT-1 | 页签【印谱采集】在导航中，`/items` 经 5195 与经 5164 均可达、入口不回落 |
| IT-2 | 全量落库 **1742 / 1742**（与源 `total` 相符）；失败清单可复算 |
| IT-3 | 幂等键 `source_item_id`（＝`seqid`）**非空且唯一 = 行数**；`as_book_id` 唯一（1742） |
| IT-4 | 抽样锚点：`seqid=2214 / asBookId=0307`「龍泓山人印譜」→ 卷册 `8`、纪年「清宣統二年」、公元 `1910`、`hasImage=1`；`seqid=3547 / 1817`「楊仲子印存」→ `bookDonor=林章松` |
| IT-5 | 数值字段负向：`volume_count` / `date_year` 为整数或 `null`，**无 `0` / 空串特值** |
| IT-6 | 独立库隔离：`yinpu.db` 与 `var/person_ingest.db` 内容指纹未变（采集全程只写 `var/item_ingest.db`） |
| IT-7 | 就绪包：`manifest.json` 必含项齐备且明确 `key_face_status: pending_xiai`；JSONL 无 BOM、一行一对象；`item_creators.jsonl` 每行 `source_item_id` 可回指 `items.jsonl` |
| IT-8 | 幂等：同批次重跑 ⇒ 行数与内容指纹不变 |

---

## 8. 待裁（默认项，一句话可改）

| # | 内容 | 默认 |
| --- | --- | --- |
| WI-1 | 独立库文件名 | **`var/item_ingest.db`**（与 person 分库） |
| WI-2 | 影像（`hasImage=1714`）是否下载 | **只落标记，不下载影像** |
| WI-3 | `itemList`（卷册条目）/ `titleList` 是否落库 | **落 `raw_json`，不单列结构化表**（本轮） |
| WI-4 | 页签文案 | **【印谱采集】** |

---

## 9. 派单记录（2026-10-10 由 Zang 执行）

| 角色 | 范围 |
| --- | --- |
| **Kong**（实现） | 批 1：`feicui/web`（页签 / 路由 / 页面 / API 客户端）＋ `feicui/server`（4 端点 / 采集器 / 归一化 / 新独立库 / 就绪包 + sidecar）＋ 自检与证据 `feicui/ops/item-ingest/**` |
| **Jing**（规范） | 批 1 规范：`feicui/docs/feicui.spec.md` 新增 **§3.16「印谱（item）采集」** ＋ AC（IT-1〜IT-8 底稿）＋ 待裁 W 行 |
| **xiai 线**（另会话） | 批 2：item 模型 / 集合名 / 键面 / 导入通道（本线出交接件） |
| **Neng**（质检） | 待批 1 落地后派 |
