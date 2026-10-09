# 「印人采集」批 2 交接件 v0.1 —— feicui → xiai 交付缝

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **交接说明（非规范）**。Zang 汇总产物。**规范以两侧 spec 为准**：feicui 侧 `feicui/docs/feicui.spec.md`（v1.7 起含印人采集节）、xiai 侧 `xiai/docs/xiai.spec.md`（§3.54）。 |
| 时点 | 2026-10-10（CST）。 |
| 范围裁定（Kevin 2026-10-10） | **xiai 侧数据写入（批 2）由另一会话接手**；本件即该会话的入口件。feicui 侧（批 1）**只负责采集 / 归一化 / 落 feicui 本库 / 产出批次包**，**不写 xiai 任何文件、不做任何 CloudBase 写操作**。 |
| 上游拆解件 | `feicui/docs/person-ingest-draft-v0.1.md`（含 API 契约、Kevin 门控四答、字段映射表） |

---

## 1. 批 2 要做什么（Kevin 已裁，逐字口径）

| # | 裁定 |
| --- | --- |
| G-2 | **写入路径 ＝ 新增「外部批量导入」通道**：先落**暂存集合**（建议 `xiai_person_imports`，行态 `PENDING`），**管理员批量采纳后**落 `xiai_persons`（守审核门、可回滚） |
| G-3 | **扩展 person 模型字段**：`native_place` / `biography` / `source` / `source_id`（＋繁简副字段口径） |
| G-3 追加 | **「我给你的地址并不是只要读取列表页就可以了，每行有详情页，你需要读详情页。」** ⇒ 详情页的**实质新增数据是 `graph/person/<personGrbsm>`（印谱/印章关联）**，已由批 1 逐人采集并落在批次包里（见 §3） |

---

## 2. feicui 侧现状（xiai 侧需知道的现状缺口）

≥ 核验时点 2026-10-10；证据 ＝ `xiai/docs/xiai.spec.md` v1.53 / `xiai/src/services/persons.js` 头注。

1. `xiai.spec.md` v1.53 已冻结印人模型：A 支（历史作者）落 `xiai_persons`，**「只经采纳路径写入；不开放任何直写入口」**，新增成员须管理员审核 ⇒ **批 2 的批量导入通道即对该条款的正式增量**（**不得说成「既有条款」**）。
2. 现模型**无** `native_place` / `biography` / `source` / `source_id` ⇒ 装不下复旦数据（G-3 已裁扩字段）。
3. `xiai_persons` / `xiai_person_proposals` **两集合尚未人工新建**；云函数 person 写入 op **未接线**（`services/persons.js` 自述：当前只在本地 dev 形态落盘，云端落库路径不可达）。
4. ⇒ 批 2 前置三件：**① 新集合 `xiai_person_imports`（暂存）＋ 既有两集合人工新建；② 云函数 op 接线；③ 规范增量（§3.54 ＋ 集合清单 17 → 18 ＋ 新 AC / W 行）。**

---

## 3. 交付缝（**冻结**：xiai 侧按此消费，不要改字段名）

### 3.1 位置与形态

- 批次包目录：**`feicui/exports/person_<yyyymmdd>_NN/`**（NN 两位，自 `01`）。
- 文件：`manifest.json` ＋ `persons.jsonl` ＋ `relations.jsonl` ＋ `report.json`。
- JSONL：**一行一对象、UTF-8、无 BOM、字段名稳定**；**失败项只进 `report.json`**，不得混入 `persons.jsonl`。
- 另可经 feicui 服务端（5196）取数：`GET /api/persons`（分页/筛选）、`GET /api/persons/{grbsm}`（详情＋关联）、`GET /api/persons/batches`。

### 3.2 硬口径（外部可机械校验）

| 口径 | 冻结值 |
| --- | --- |
| **幂等键** | `source_person_id` ＝ 复旦 `personGrbsm`（9 位字符串，如 `907450151`） |
| 溯源字段 | `source`（＝「林章松《印人小传》」）/ `source_id`（＝ `dataSourceId`）/ `source_seqid` |
| 繁简存法 | **繁体为正字段**（`name_full` / `native_place` / `biography` / 字号别名），**简体入 `*_chs` 副字段**；**零转换改写** |
| 抽取项标注 | 姓 / 名 / 字 / 号 / 别名＝**规则抽取**，逐项标注 `extraction='rule-based'`；抽不准者一律落 `alias_names[]`；**不得表述为权威分类** |
| 生卒 | `birth_year` / `death_year` 整数或 `null`；源侧 `?`/空 ⇒ **`null`**（**禁用 `0` 或 `'?'` 特值**）；另存 `birth_death_text`（源 `personSzn` 原样） |
| 其他 | `cbdb_id`（源 `personCbdbId`，104/570 有值，**不联网核验**）/ `nationality`（源 `personGj`）/ `spell` / `initial` / `flag` 原样 |

### 3.3 关系面（`relations.jsonl`；**这是「读详情页」的产物**）

逐条：`source_person_id`（宿主）/ `kind`（`印谱` | `印章`）/ `ref_id` / `name`（印谱名）或 `desc`（印章印文）/ `creator_type` / `as_book_id`（印谱）/ `has_image`（印谱）/ `image_key`（印章，如 `20_2868_1`；**默认只存键、不下载影像**）。

实测锚点（用于校验关系面确实采到）：**趙之謙 `907404573` ⇒ 印谱 23 / 印章 65**；吳昌碩 `907271790` ⇒ 印章 10；鄒夢禪 `907450151` ⇒ 印谱 1 / 印章 0；宗汝剛 `907566313` ⇒ 0 / 0。

---

## 4. 源 API 契约摘要（只读实测，2026-10-10）

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `POST https://yin.fudan.edu.cn/service_yinpu/person/list` | POST | body `{pageNum,pageRows,fullText,facetPersonGjqc,facetPersonInitial,orderField,orderType}`；**`pageRows=1000` 一次返回全部 570 条** |
| `GET /service_yinpu/person/detail/<personGrbsm>` | GET | **与列表行字段等价**（15 人抽样：仅 `seqid`/`createdTime` 异）；**有窗口限流** |
| `GET /service_yinpu/graph/person/<personGrbsm>` | GET | **详情页关联图（印谱/印章）**——列表页没有 |
| `GET /service_yinpu/statistic/home`、`POST /service_yinpu/person/facet` | — | 计数、分面 |

- **限流陷阱（务必知道）**：超频回包为 **HTTP 200** ＋ `{"msg":"操作频繁，请稍候再试!","code":"429","status":"true"}`——`code` 是**字符串**、`status` 仍 `true`，**只有 `data` 缺失能暴露失败**；约 **150 s 自愈**。任何人写消费端时不要以「HTTP 200」判成功。
- 响应头含 `Access-Control-Allow-Origin: *`；本机 DNS 将其解析为 `198.18.x.x`（代理假 IP），`web_extract` 会拒取 ⇒ 用 curl / 浏览器工具。

---

## 5. 批 2 待办清单（建议顺序）

1. 规范：`xiai.spec.md` §3.54 增量（`xiai_person_imports`、person 扩字段、批量采纳通道、集合 17 → 18、新 AC、W 行；走该文件 §1.3 流程）。
2. 人工前置：云控制台新建 `xiai_person_imports`（＋既有 `xiai_persons` / `xiai_person_proposals`）。
3. 实现：云函数 op 接线（`submitPersonImport` / `reviewPersonImport` 形态）＋ 数据层集合读写 ＋ 管理员批量采纳 UI（**复用「我的勘误记录」页形态，不新开路由、不建管理员专区**）。
4. 导入器：消费 feicui 批次包（`persons.jsonl` / `relations.jsonl`）→ 写 `xiai_person_imports`（`PENDING`）。
5. 采纳：`ACCEPTED` ⇒ **按 `source_person_id` 幂等**落 `xiai_persons`（重复采纳不改写既有行）；`REJECTED` ⇒ 零写入。
6. 验收：570 条落库可读回 ＋ 幂等重放 ＋ 负向（非法引用 / 重复采纳零写入）。

## 6. 待裁（本线默认，一句话可改）

| # | 内容 | 默认 |
| --- | --- | --- |
| W-P2 | 关联面是否递归到 `seal/detail` / `graph/seal` | **只落直接关联**，递归面另议 |
| W-P4 | 印章影像（`image_key`）是否下载 | **只存键，不下载** |
| W-P5 | 批 2 是否直接消费 feicui 批次包，还是经 feicui 端点实时拉取 | **优先批次包**（可复现、可存档） |
