# 「印人采集」数据模型与采集线拆解草案 v0.1

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **草案（非规范）**。本件是 **Zang 的拆解产物**，**不得被引为规范条款**。正式落规范由 Jing 执行（feicui 侧新增节 + xiai 侧 §3.54 增量）。 |
| 时点 | 2026-10-10（CST）。凡引现状读数均带来源与核验时点。 |
| 任务来源 | Kevin 2026-10-10：**在 feicui 项目首页新增一个标签页，从 `https://yin.fudan.edu.cn/#/home?keyword=&sourceTap=3` 读取「印人」信息，存入 xiai 的数据库**。 |
| 目标仓 | **feicui （`github.com/cloud-cottage/feicui`，本地工作副本 `~/bistro/xiai/feicui`，HEAD `dcaba92`，与远端一致）**；数据落地在 **xiai（玺爱，canonical）**。 |
| 未动作声明 | 本件只写文档：未跑构建 / 未跑测试 / 未起服务 / 未占端口 / 未写任何生产数据 / 未对任何仓做 git 写操作（除本件自身）。侦察期间的只读联网取数**只写本机 scratch 目录**。 |

---

## 1. Kevin 门控四答（逐字口径，本件的输入）

| # | 问题 | 裁定 |
| --- | --- | --- |
| G-1 | 页签落点 | **feicui 前端首页导航新增「印人采集」页签**（5195 直连 / 经 5164 的 `/feicui` 均可达） |
| G-2 | 写入 xiai 的路径 | **新增「外部批量导入」通道：先落暂存集合（如 `xiai_person_imports` / PENDING），管理员批量采纳后落 `xiai_persons`**（守审核门、可回滚） |
| G-3 | 籍贯 / 传记 / 来源 / 外部 id | **A ＝ 扩展 person 模型新增 `native_place` / `biography` / `source` / `source_id`**；**追加口径（Kevin 逐字）：「我给你的地址并不是只要读取列表页就可以了，每行有详情页，你需要读详情页。」** |
| G-4 | 本轮范围 | **分两批**：批 1 ＝ feicui 侧（页签＋服务端拉取归一化＋落 feicui 本库＋批次包）先验收；批 2 ＝ 再接 xiai 落库通道与端到端 |

---

## 2. 数据源事实基线（**只读实测，非推断**）

**核验时点 2026-10-10（CST）；核验人 Zang；证据 ＝ 本机 curl / headless Chrome 钩取 XHR / 全量落盘 `fudan_persons_raw.json`（570 行）。**

### 2.1 端点清单（真源＝站点 SPA 的实际请求，非文档）

| 端点 | 方法 | 入参 | 用途 |
| --- | --- | --- | --- |
| `/service_yinpu/person/list` | POST | `{pageNum, pageRows, fullText, facetPersonGjqc, facetPersonInitial, orderField, orderType}` | **列表页**；`pageRows=1000` **一次返回全部 570 条**（`total=570`） |
| `/service_yinpu/person/facet` | POST | `{fullText}` | 分面（国籍 / 姓氏首字母） |
| `/service_yinpu/person/detail/<personGrbsm>` | GET | 路径参数 | **详情页**主数据（同一字段集；`seqid`/`createdTime` 与列表行不同） |
| `/service_yinpu/graph/person/<personGrbsm>` | GET | 路径参数 | **详情页关联图**：该印人的**印谱**与**印章**（列表页没有） |
| `/service_yinpu/statistic/home` | GET | — | 站点计数（`sealCount=716` / `personCount=570` / `bookCount=1742`） |
| `/service_yinpu/seal/detail/<id>`、`/service_yinpu/graph/seal/<id>` | GET | — | 印章侧（**本轮范围外**，仅登记） |

- 响应信封：`{data, total?, code:200, msg, status:true}`。
- **`person/detail|info|get`（POST 形态）不存在 ⇒ 404**；详情页实际走 **GET 路径参数** 形态。
- 响应头实测含 `Access-Control-Allow-Origin: *`（浏览器可直连；**本线仍主张经 feicui 服务端拉取**，理由是留痕 / 限速 / 归一化 / 落库单点）。
- 吞吐实测：详情单请求 **0.189 s**（20 连测，全 200）⇒ 570 人 ×（detail + graph）≈ **1140 请求 ≈ 3.7 min**，需**礼貌限速与可断点续跑**。

### 2.2 字段实测覆盖（570 条全量）

| 源字段 | 覆盖 | 说明 |
| --- | --- | --- |
| `personGrsm`（外部 id 形如 `907450151`） | 570/570 | **稳定外部键**（详情页 URL 段）；另有行级 `seqid`（列表与详情**不同号**，不作键） |
| `personGrsxmc` | 570/570 | **姓名全串**（**唯一姓名来源**） |
| `personXing` / `personMing` / `personZi` | **0/570** | **源侧无结构化 姓 / 名 / 字** ⇒ 须抽取，**抽取结果不得冒充权威分类** |
| `personBm` / `personBmChs` | 552/570 | **别名字号自由文本串**（「原名…一作…字…號…別署…齋堂為…」），**无结构化切分** |
| `personJj` / `personJjChs` | 570/570 | 小传（繁 / 简双份） |
| `personGrfz` | 79/570 | 生卒考订 / 按语（自由文本） |
| `personJg` / `personJgChs` | 568/570 | 籍贯原文（繁 / 简） |
| `personGj` / `personGjqc` / `personGjdm` | 569/570 | 国（繁）/ 国籍（简）/ 数字码 |
| `personCsrq` / `personSwrq` / `personSzn` | 362 / 301 / 371 | 生年 / 卒年 / 生卒串（含 `?`） |
| `personCbdbId` | 104/570 | CBDB id（**可直接对接 xiai `cbdb_id`**） |
| `dataSource` / `dataSourceId` | 570/570 | 恒为「林章松《印人小传》」/ `RW…` |
| `personSpell` / `personInitial` / `flag` | 570/570 | 拼音 / 首字母 / 标记（`flag=1` 24 条） |
| `personZz` / `personCd` / `personCsd` / `personDz` / `personJzd` / `personHdly` / `personRzdwmc` | 0/570 | **源侧全空**（预留位） |
| `delFlag` | 全 `0` | 无逻辑删除行 |

### 2.3 关联图（`graph/person/<id>`）形状（实测样本）

```
{"data":{"name":"吳昌碩","id":"907271790","children":[
  {"name":"印谱","count":0,"children":[]},
  {"name":"印章","count":10,"children":[
     {"image":"20_2868_1","creatorType":"印主","id":2868,"type":"印章","desc":"缶翁"}, …]}]}}
```
- **印谱**子项字段：`creatorType`（如「刻印」「辑、刻印」「辑、刻」）/ `name` / `asBookId`（补零字符串）/ `hasImage` / `id` / `type`。
- **印章**子项字段：`image`（影像键 `NN_<id>_1`）/ `creatorType`（如「印主」）/ `id` / `desc`（印文，含换行 `/`）/ `type`。
- 关联规模差异极大（实测：宗汝剛 0/0；鄒夢禪 印谱 1 / 印章 0；**趙之謙 印谱 23 / 印章 65**）⇒ **不可只抓列表**（Kevin 口径的实证）。

---

## 3. xiai 侧现状与落差（**冲突必须登记**）

≥ 核验时点 2026-10-10；证据 ＝ `xiai/docs/xiai.spec.md` v1.53 / `xiai/src/services/persons.js` 头注 / `xiai/docs/person-model-draft-v0.1.md`。

1. `xiai.spec.md` **v1.53（2026-10-10 入规范）** 已冻结印人模型：A 支（历史作者）落 `xiai_persons`，**「只经采纳路径写入；不开放任何直写入口」**，新增成员须管理员审核。
2. 模型字段面 **无** `native_place` / `biography` / `source` / `source_id` ⇒ **装不下复旦数据**（G-3 已裁定扩展）。
3. `xiai_persons` / `xiai_person_proposals` **两集合尚未人工新建**；云函数 person 写入 op **未接线** ⇒ `services/persons.js` 自述「当前只在本地 dev 形态落盘，云端落库路径不可达」。
4. ⇒ **批 2 的三处前置**：① 新集合 `xiai_person_imports`（暂存）＋ 既有两集合人工新建；② 云函数 op 接线；③ 规范增量（§3.54）。

---

## 4. 批 1 交付范围（feicui 侧）

### 4.1 前端（`feicui/web`）

- **App.vue 首页导航新增「印人采集」页签**（现导航仅「任务页」一项）；路由新增 **`/persons`**（**history base 仍须取 `import.meta.env.BASE_URL`**，沿既有 G-1 教训）。
- 页面三区：**采集区**（触发同步 / 进度 / 上次结果 / 批次列表）、**列表区**（570 条；筛选：姓氏首字母、国籍、有无生卒、有无关联；分页）、**详情区**（含关联印谱 / 印章）。
- 界面文案**简体**（feicui 侧）；**源数据一律按原文呈现，同时展示繁 / 简两版字段**；**不得**本地改写源数据。
- 后端不可达 ⇒ 沿用既有「未连接」横幅口径，**不得以假数据填充**。

### 4.2 后端（`feicui/server`，端口 5196；**端点一律 additive，不动 E1〜E7**）

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/persons/sync` | POST | 拉全量（`pageRows=1000`）→ 逐人 `person/detail` + `graph/person` → 归一化 → 落本库 → 产批次包；**可断点续跑**；**礼貌限速** |
| `/api/persons` | GET | 列表（分页 / 筛选） |
| `/api/persons/{grbsm}` | GET | 单人（详情 + 关联） |
| `/api/persons/batches` | GET | 批次列表（含回执读数） |

- **不得**把业务真值放进接口层缓存（沿 §3.2 S-4）。
- **CORS**：`127.0.0.1:5195` / `localhost:5195`（已在白名单）；**任何情况下不放开 `*`**。
- HTTP 客户端：**优先 stdlib（`urllib`）**，避免改动 `server/requirements.txt` 的既有 freeze 口径。

### 4.3 存储（**建议：独立库，不碰正式库**）

- **建议新增独立 SQLite（如 `feicui/var/person_ingest.db`）**，表：`persons` / `person_relations` / `person_import_batches`；
  **`yinpu.db`（印谱解析正式库）一字不碰**——理由：该库有「只能加法 + 红线判据」历史包袱，且印人采集与印谱解析无数据依赖。**（Zang 默认 · 一句话可改：若 Kevin 要求同库，改为加法式新表。）**
- 归一化落库须**保留源原文与源键**（`source_person_id` = `personGrbsm`、`source_data_source_id` = `dataSourceId`、`source_seqid`），**不得丢源**。

### 4.4 批次包（沿用 F1 形态，`feicui/exports/person_<yyyymmdd>_01/`）

`manifest.json` + `report.json`（计数 / 覆盖率 / 失败清单）+ `persons.jsonl` + `relations.jsonl`；**既有 `exports/fb_*` 一字不动**。

### 4.5 字段映射（批 1 采集面；批 2 落 xiai 沿用）

| 目标（拟） | 源 | 归一化规则（Zang 默认 · 一句话可改） |
| --- | --- | --- |
| `source_person_id` | `personGrbsm` | 原样字符串（**幂等键**） |
| `name_full` | `personGrsxmc` | 原样 |
| `family_name` | 抽取自 `personGrsxmc` | **首字为姓**；复姓白名单（歐陽/司馬/上官/諸葛/東方/皇甫/尉遲/公孫/慕容/司徒/獨孤/南宮/宇文/長孫/夏侯/西門/令狐/端木/聞人/赫連/澹臺/呼延/百里…）命中取二字；**4 字以上或无法判定 ⇒ `family_name=''`、整串落 `given_name`**（**不猜**） |
| `given_name` | 同上 | 余下部分 |
| `courtesy_names[]` / `art_names[]` / `alias_names[]` | `personBm`（繁）/ `personBmChs`（简） | **自由文本抽取**，逐项标注 **`extraction='rule-based'`**；**抽不准的一律落 `alias_names[]`**；**不得**把抽取结果写成权威分类 |
| `birth_year` / `death_year` | `personCsrq` / `personSwrq` | 纯数字 ⇒ 整数；含 `?` / 空 ⇒ `null`（**不设特值**，沿 person-model 口径） |
| `birth_death_text` | `personSzn` | 原样字符串 |
| `native_place` | `personJg`（繁） | 原样；简版另存 |
| `biography` | `personJj`（繁） | 原样；简版另存 |
| `nationality` | `personGj`（繁）/ `personGjqc` | 原样 |
| `cbdb_id` | `personCbdbId` | 原样（104 条有值）；**不联网核验** |
| `source` | `dataSource` | 原样（「林章松《印人小传》」） |
| `source_id` | `dataSourceId` | 原样 |
| `spell` / `initial` / `flag` | `personSpell` / `personInitial` / `flag` | 原样（检索与排查用） |
| 关联 | `graph/person` | 逐条落 `person_relations`（`kind` = 印谱/印章；`ref_id`；`name`/`desc`；`creator_type`；`image_key`；`as_book_id`；`has_image`） |

**繁简存法（Zang 默认 · 一句话可改）**：**繁体为正字段（xiai 上屏为繁体）、简体入副字段**（`*_chs`），**不做任何转换改写**（沿「不转用户输入」纪律）。

---

## 5. 批 2 交付范围（xiai 侧）

1. **新集合 `xiai_person_imports`（暂存 / PENDING）**：导入批次行（`batch_id` / `source` / `source_person_id` / 归一化载荷 / `status` / `imported_by` / `imported_at`）。
2. **管理员批量采纳通道**：`PENDING → ACCEPTED` ⇒ **幂等**落 `xiai_persons`（按 `source_person_id` 幂等；重复采纳不改写既有行）；`REJECTED` ⇒ 零写入；**复用「我的勘误记录」页形态**（不新开路由、不建管理员专区）。
3. **person 模型扩字段**：`native_place` / `biography` / `source` / `source_id`（＋ 繁简副字段口径）。
4. **云函数 op 接线**（`xiai-user-token` / `xiai-admin-token` 的 `ops.js`：`submitPersonImport` / `reviewPersonImport` 形态）＋ **两集合人工新建**（云控制台动作，**不代建**）。
5. **规范**：`xiai.spec.md` §3.54 增量（集合 17 → 18、新 AC、W 行、`[data-admin-action]` 计数）。
6. **端到端验收**：feicui 采集 → 批次包 → xiai 暂存 → 批量采纳 → `xiai_persons` 行可读回（**含幂等与零写入负向**）。

---

## 6. 硬约束（两批共用）

- **只加法**：不改既有端点语义、不动 `stamps` / `jobs` / `output/` / 既有 `exports/fb_*`、不动 `feicui/app.py`（Streamlit 退役面）。
- **不碰他线文件**：`xiai/src/**`（除批 2 明确清单）、`yinyuan/**`、`ctrl/**`、`docs/versions/**` 一律不动；**不占新端口**；启停登记一律以 ctrl 面板为准。
- **零外链资源**（页面仍离线自洽）；**联网只发生在 feicui 服务端**，且**只读**（GET/POST 取数，**不上传任何数据**）。
- **礼貌限速**：采集串行 + 间隔；**失败条目进 `report.json` 失败清单**，**不得静默跳过**。
- **红线判据**：证明「数据未变」一律用内容指纹，**禁用数据库文件 md5**。

---

## 7. 建议验收判据（批 1，供 Jing 落成 AC）

| # | 判据 |
| --- | --- |
| A-1 | 首页导航出现「印人采集」页签；`/persons` 经 5195 与经 5164 的 `/feicui/persons` **均可达**且 `location.href` 不回落 |
| A-2 | 全量采集落库 **570 / 570**（与源 `total` 相符）；失败条目数写入 `report.json` 且可复算 |
| A-3 | **关联面非空**：抽样赵之謙（`907404573`）⇒ 印谱 **23** / 印章 **65**；吴昌碩（`907271790`）⇒ 印章 **10**（**证明「读了详情页」**） |
| A-4 | 幂等：同一批次重跑 ⇒ `persons` 行数与内容指纹不变 |
| A-5 | 只加法：`yinpu.db` 内容指纹（`stamps`/`jobs` 行数与内容）**逐字节未变**；既有 `exports/fb_*` 未动 |
| A-6 | 归一化负向：`birth_year`/`death_year` 遇 `?`/空 ⇒ `null`；**不得**出现 `0` / `'?'` 等特值 |
| A-7 | 抽取标注：`courtesy_names`/`art_names`/`alias_names` 全部带规则来源标注，**无「权威分类」表述** |

---

## 8. 待裁 / 挂账

| # | 内容 | 默认（Zang） |
| --- | --- | --- |
| W-P1 | 印人采集是否**同库** `yinpu.db` | 默认**独立库**（一句话可改） |
| W-P2 | 关联面是否**递归**到印章详情 / 印谱详情（`seal/detail`、`graph/seal`） | 默认**只落直接关联**，递归面批 2 后另议 |
| W-P3 | 采集触发形态：手动按钮 / 定时任务 | 默认**手动按钮**（本轮） |
| W-P4 | 印章影像（`image_key`）是否下载 | 默认**只存键，不下载影像** |

---

## 9. 派单记录（2026-10-10 由 Zang 执行）

| 角色 | 范围 |
| --- | --- |
| **Kong**（实现） | 批 1：`feicui/web`（页签 / 路由 / 页面 / API 客户端）＋ `feicui/server`（新端点 / 采集器 / 归一化 / 新库 / 批次包）＋ 自检与证据留档 `feicui/ops/**` |
| **Jing**（规范） | 批 1 规范：`feicui/docs/feicui.spec.md` 新增「印人采集」节（端点 / 存储 / 批次 / UI / AC）；**批 2 规范前置**：`xiai/docs/xiai.spec.md` §3.54 增量（`xiai_person_imports` / 扩字段 / 批量采纳 / 集合计数 / 新 AC / W 行） |
| **Neng**（质检） | 待 Kong 批 1 落地后派：按 §7 判据逐条复核 + 证据裁决 |

---

## 10. 变更记录

| 时点 | 变更 |
| --- | --- |
| 2026-10-10 | **v0.1 建立**（Zang）：实测 API 契约、Kevin 门控四答、批 1 / 批 2 范围与映射表。 |
| 2026-10-10 | **范围裁定（Kevin）**：**xiai 侧数据写入（批 2）由另一会话接手** ⇒ 本线职责边界收窄为 **feicui 只负责采集 / 归一化 / 落 feicui 本库 / 产出批次包**；**批次包即对外唯一交付缝**；交接件 ＝ **`feicui/docs/person-ingest-handoff-v0.1.md`**（本件 §5 批 2 内容**读作待办清单与口径来源，不再由本线实现**）。已同步：Kong 侧「不得触碰 xiai 任何文件」、Jing 侧「停止写 xiai 规范、改在 feicui 规范冻结交付缝」。 |

### 10.1 实测补记（限流）

- **`person/detail/<id>` 有窗口限流**：超频回包 **HTTP 200** ＋ `{"msg":"操作频繁，请稍候再试!","code":"429","status":"true"}`（`code` 为**字符串**、`status` 仍 `true`、**仅 `data` 缺失可辨失败**）；自愈实测 **约 150 s**。
- **`person/detail` 与列表行字段等价**：15 人随机抽样逐字段比对，**仅 `seqid` / `createdTime` 不同，其余逐字节相同** ⇒ **详情页新增的只有 `graph/person`（关联图）**；采集主链路 ＝ `list`（1 次）＋ `graph/person`（570 次，实测 0.5 s 间隔 12/12 成功）；`detail` 降为 best-effort（失败进清单、不阻塞、不得计为成功）。
