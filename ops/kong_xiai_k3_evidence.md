# 玺爱（xiai）· 本单（三件小改）自测留证 —— Kong / 工程师

- 时点：2026-09-20（本文件读数由脚本直出，非事后转述）
- 范围（三件）：① 印章编号 `XA` + 9 位；② 删「印章名称」概念（印文可空 ⇒ 显示「佚名」、防重键改用印文）；③ 修 `AppSidebar.vue` 的 `logged` 未定义 bug；④ README 同步
- 自测载体（全部真跑）：
  - `feicui/ops/kong_xiai_k3_selftest.mjs`（Vite SSR 载入器执行工程内真实 `src/**` 模块 + SSR 真实渲染组件/页面；浏览器存储用替身：localStorage 内存表 + 最小 IndexedDB）→ `kong_xiai_k3_selftest_raw.{json,txt}`（**36 项全过**）
  - `feicui/ops/kong_xiai_k3_uiflow.py`（**自建 headless Chrome**、独立 profile `/tmp/xiai-kong3-prof`、`--remote-debugging-port=9433 --remote-allow-origins=*`；真登录 + 真点按钮 + 真选文件上传）→ `kong_xiai_k3_uiflow_raw.json`（**11 项全过**）
  - `feicui/ops/kong_xiai_k3_legacycheck.py`（真浏览器读 `localStorage` 逐行比对既有 8 行）→ `kong_xiai_k3_legacycheck_raw.json`（**5 项全过**）
  - `feicui/ops/kong_xiai_k3_uiflow_pre.txt`（改前 D-2 复现读数）
- 环境纪律：**未停 / 未重启 5163**（核验时点 `lsof` 仍为原 PID **91247** LISTEN）；**未占用 5173/5174**（`lsof` 两条均为空）；**未动用户自己的 Chrome**（自建 headless 已 `Browser.close` 关停，9433 已释放）；**未执行 `pkill -f` / `killall`**；未删库、未换命名空间（`storage.js` md5 未变）。

## 1. 改动文件（改前 / 改后 md5）

| 文件 | 改前 md5 | 改后 md5 | 说明 |
| --- | --- | --- | --- |
| `src/data/db.js` | `4c7328baa871c13c51bfc11f2ce343b5` | `3e17b165c80a6e4afe0b904ae5abdbf7` | ①编号生成器 `XA`+9 位（容错解析）②必填集去掉印文 ③防重键改 `(印文,朝代,分类,sha256)` ④归一载荷键 `name`→`seal_name`（旧键保留兼容） |
| `src/services/seals.js` | `21a10a766947b18d6354c478366d07eb` | `0045dd67cf400e9bc983a2eb2f4045bb` | 冻结 API ① 的 payload 文档口径（`seal_name` 选填；旧键 `name` 兼容别名）；视图模型 `name` 行注释 |
| `src/views/SealDetailView.vue` | `10dfb3c293bb3b78401a8603d80e4962` | `3ddb8817500f4de1b013d08086dd37aa` | `:233` / `:261` 回退词「待考」→「佚名」 |
| `src/components/SealCard.vue` | `2cf0dadb2f7154f4cadf6ad43188469e` | `c6bc9a2fa0734a273b03cb732626e350` | `:12` 回退词改「佚名」；卡片标题也加同口径回退 |
| `src/components/AppSidebar.vue` | `c73c2ad2dcbb336c562f43a48b6b942c` | `f69dfb67cfcbc0a7c03279d361f50503` | **D-2**：`import { isLoggedIn }` + `const logged = isLoggedIn`（与 AppHeader / SquareView / SealDetailView 同一取法） |
| `src/components/FaceFixedAttributesDialog.vue` | `307197d18ea996cc35a0f91fd555aad4` | `bda879fc106e6b7fe9aa015f032e5217` | `:111` 回退词改「佚名」 |
| `src/utils/file.js` | `b33b5117cf6a5f2ce98bb35083f03955` | `4f42f1acc0ade60793c9fff75c3f82dd` | `:52` 标签「印章名称：」→「印文：」且回退改「佚名」 |
| `README.md` | `4ab3975e8ec9eeca8b32261967203f9d` | `70430f538df5c53a9b21bdee918d7035` | 编号格式 / 印文可空 / 必填集 / 佚名回退 / 防重键 / 冻结 API payload |
| `src/components/UploadSealDialog.vue` | `7374becc9e4ec46a7ab2ee00cd89f148` | `f2b640f5774f25da51c0306562efe6e3` | **超出白名单（见 §5 说明）**：标签「印章名称」→「印文（选填）」、说明文字必填集、提交键改 `seal_name` |

**白名单内未改**：`src/views/SquareView.vue`（md5 与开工基线**逐字一致** `90008b41494d7ec9183908adf98935d7` —— 本单无需改动，其唯一相关点是新印章提示里的 `seal_name || id`，见 §6）。

**不得改、且已核验未改（md5 与开工读数一致）**：`src/services/photos.js` `de99997c…`、`src/data/blobstore.js` `d2cbe0f7…`、`src/data/storage.js` `916c7097…`（命名空间 `xiai:v1:` 未动）、`src/data/assetmeta.js` `b5ea832a…`、`src/router/index.js` `796225e7…`、`src/views/AdminView.vue` `fe513625…`、`src/views/MyCorrectionsView.vue` `b9d0326f…`、`index.html` `eef2b061…`、`vite.config.js` `3ab16821…`、`package.json` `23a80296…`；`xiai/docs/**`、`xiai/feicui/**`（本单新增的 4 个 ops 证据文件除外）、`xiai/web/**`、`xiai/yinsuo/**`、`ctrl/**` 一律未碰。

## 2. 三件改动的实现口径

**① 印章编号 = `XA` + 9 位零填充**（`db.js`）
- 新增 `SEAL_STAMP_ID_PATTERN = /^XA(\d{9})$/`（**只有它参与递增**）与 `LEGACY_STAMP_ID_PATTERN = /^XAI-(\d+)$/`（**仅用于派生序号的容错识别，不参与递增**）；`formatSealStampId` 零填充 9 位。
- `nextSealStampId`：max(既有新式序号)+1，`while (taken.has(...)) index += 1` **跳过已占用** ⇒ 第 1 枚 `XA000000001`。
- `stampSerial`：新式取 9 位序号、旧式取原数字（既有派生不变），否则回退「剥离非字母数字」⇒ **印面 id / 影像 id 的模板本身未改**（`fc-<序号>-f1` / `img-<序号>f`）。
- 既有种子 `XAI-0001`…`XAI-0008` **一行未改**（见 §3-① 的两处逐字比对）。

**② 删「印章名称」，名称＝印文**
- `REQUIRED_SEAL_FIELDS`：删掉 `{ key:'name', label:'名称' }` ⇒ **必填仅剩 朝代 / 分类**；印面图仍在组合写里单独必填。
- 显示回退词 `待考` → `佚名`，落点 5 处（`file.js:52`＋标签、`SealCard.vue:12`、`SealDetailView.vue:233` 与 `:261`、`FaceFixedAttributesDialog.vue:111`）＋ 上传表单标签「印文（选填）」。
- **显示取值顺序保持现有逻辑、未静默改动**：`SealCard` 的「当前印文」仍为 `transcription_simplified || seal_name || 佚名`；详情页 h1 / 印面名仍以 `seal_name` 为准（见 §6-③ 规范缺口）。
- 防重键：印章级改为 **`(印文＝seal_name, 朝代, 分类, sha256(印面图))`**（印文空串按空串比较）；印面级 / 二进制级不变。
- 内部载荷归一键 `name` → `seal_name`（`normalizeSealPayload` 接受 `seal_name` 优先、`name` 兜底）⇒ 出参 `message` 里的印章名空时打印「佚名」。
- **`seals.js:113` 的「印面归属待考」一字未改**（另一概念；自测第 27 项实测仍返回该字面值）。

**③ D-2 侧栏 `logged`**
- 按工程既有模式取登录态（`data/session.js` 的 `isLoggedIn`，与 `AppHeader.vue:15` / `SquareView.vue:16` / `SealDetailView.vue:53` 完全同一写法），未新造第三种取法。

## 3. 六条自测真实输出（贴原始读数）

**① 编号（真跑）**
- `第 1 枚 ⇒ stampId=XA000000001`（正则 `^XA\d{9}$` 通过、串长 11）；`第 2 枚 ⇒ XA000000002`；`第 3 枚 ⇒ XA000000003`。
- 新行实际值（`kong_xiai_k3_selftest_raw.json`，逐字）：
  `[{"stamp_id":"XA000000001","id":"XA000000001","sealGroupId":"g-000000001","seal_name":"","dynasty":"清","seal_type":"私印","source":"manual"},{"stamp_id":"XA000000002","id":"XA000000002","sealGroupId":"g-000000002","seal_name":"测试印","dynasty":"明","seal_type":"閒章","source":"manual"}]`
- 既有 8 行逐字未变：node 侧 `JSON.stringify(rows.slice(0,8))` 与改前快照**逐字相等**（PASS 09）；真浏览器侧以整行 JSON 比对 —— `legacy_rows_json 长度 2324 == 2324`，且 8 行 `(stamp_id, seal_name)` ＝ `[("XAI-0001","長壽"),("XAI-0002","騎都尉印"),("XAI-0003","昌"),("XAI-0004","文彭之印"),("XAI-0005","丁敬身印"),("XAI-0006","家在錢塘"),("XAI-0007","乾隆御覽之寶"),("XAI-0008","安持")]`（PASS）。
- 解析容错：旧规则会把既有 `XAI-0008` 推成 `0009`，本单首枚仍为 `XA000000001` ⇒ **旧 `XAI-000x` 未被误解析成序号**（PASS 08）。
- 其他 id 模板不变：`faceIds=["fc-000000001-f1"] imageIds=["img-000000001f"]`（PASS 12）。

**② 印文可空（核心，真跑）**
- 数据层：`{ok:true, message:"已新增印章《佚名》（XA000000001）与 1 个印面"}`，**不再返回 `MISSING_REQUIRED`**；落盘 `seal_name:""`（不写占位词）。
- **真浏览器 UI 端到端**（真登录管理员 → 点「上传印章」→ 印文留空 + 朝代=清 + 分类=私印 + 真选 PNG 文件 → 点「确认上传」）：
  - 表单反馈：`已新增印章《佚名》（XA000000001）与 1 个印面 查看「XA000000001」`
  - 广场卡片真实 DOM：`{"title":"佚名","dds":["佚名","","XA000000001"],"link":"/seal/XA000000001"}`
  - 详情页真实 DOM：`{"h1":"佚名","faceName":"佚名","stampTag":"藏品编号 XA000000001","body":true}`
  - 上传表单标签真实 DOM：`label[for=upload-seal-name] = "印文（选填）"`，值 `''` 直接提交成功
  - 高清资料清单（`file.js:52`）：`印文：佚名`（且全文不再出现「印章名称」）
- 显示取值顺序（未改口径）：仅填简体的第 3 枚（`seal_name=""` + `transcription_simplified="長壽合文"`）卡片显示「長壽合文」（PASS 19）。
- `待考` 已从广场页 / 详情页消失（PASS 20 / 23）；`印面归属待考` 保留（PASS 27）。

**③ 必填仍生效（各一次，真跑）**
- 缺朝代 ⇒ `{"ok":false,"reason":"MISSING_REQUIRED","missing":["朝代"],"message":"请补全必填项：朝代"}`
- 缺分类 ⇒ `missing:["分类"]`；缺印面图 ⇒ `missing:["印面图"]`
- 三次拒绝后集合计数**完全未变**：`{"seals":11,"faces":16,"images":16}` == `{"seals":11,"faces":16,"images":16}`（影像二进制数同计）⇒ 无半成品。
- 真浏览器侧：缺朝代时表单反馈原文 `请补全必填项：朝代`，且 `localStorage` 印章数仍为 9（8 既有 + 1 新建）。

**④ 防重仍生效（真跑）**
- 同一印章同图重复提交（印文留空）⇒ `{"ok":true,"deduped":true,"stampId":"XA000000001","message":"该印章与印面图此前已上传，本次未重复新增"}`
- 印文非空的一组重复提交同样 `deduped:true`（`stampId=XA000000002`）
- 两次 dedupe 前后计数逐字相等 ⇒ **未新增印章 / 印面 / 影像行，未重复落二进制**。

**⑤ D-2 侧栏（真机 DOM，修前 → 修后）**
- 修前（`kong_xiai_k3_uiflow_pre.txt`）：游客 `游客可自由浏览印章与印面。`；**登录后仍是**`游客可自由浏览印章与印面。`（顶栏已是「50 金」+ 账号头像 ⇒ 登录确实成功）⇒ `changed:false`
- 修后（`kong_xiai_k3_uiflow_raw.json`）：游客 `游客可自由浏览印章与印面。` → 登录后 `登录后可提交勘误、上传实物照片。`（`sidebar_logged_html = "<p>登录后可提交勘误、上传实物照片。</p>"`）⇒ 文案真实变化。

**⑥ `npm run build`**
- `npm run build` **成功**：`✓ built in 887ms`（产物落在 `dist/`，含 `SquareView` / `SealDetailView` / `file` 等 chunk）。

## 4. 未完成项 / 边界

- **AC-33（影像二进制不进 `localStorage`）不在本单**：其根因是既有实物照片路径（`photos.js`），本单**未碰**该文件（下单一处理）。
- 本单未做实物照片 / 勘误 / 积分路径的回归（不在改动面内，且 `photos.js`、`MyCorrectionsView.vue` 等为禁改文件）。
- 未清理自建 headless Chrome 的 profile 目录 `/tmp/xiai-kong3-prof`（保留以便复跑；不在工程树内）。
- 未改 `docs/**`（规范归 Jing）；规范缺口见 §6。

## 5. 白名单说明（必须显式登记）

- **`src/components/UploadSealDialog.vue` 不在本单白名单内，但「上传表单：印文字段标签改为『印文（选填）』、不再是必填校验项」这条要求只有该文件承载**（表单标签与提交载荷都在这里；`SquareView.vue` 只是它的宿主）。因此本单**改了它**，改动仅三类：`①` 标签文案「印章名称」→「印文（选填）」＋占位符；`②` 说明段必填集改成「朝代、分类、印面图为必填项」；`③` 表单字段与提交键 `name` → `seal_name`（服务层同时接受旧键 `name`，故对既有调用方零破坏）。DOM id `upload-seal-name` **保留未改**（避免打断既有选择器）。若这是越界，请判负并要求回退——但那样「表单标签＝印文（选填）」这条验收点在本单就无法成立。

## 6. 规范缺口（供 Jing/Zang 裁定）

1. **`docs/xiai.spec.md` §4.1.1 的 `name` 行**：现为「| `name` | 名称（**可空**） |」。本单口径把「名称」概念删掉、**名称＝印文（`seal_name`）**，则规范里印章的字段名是保留 `name` 但改语义为「印文」，还是改成 `seal_name`（与平台 `sealName` 同源）？实现现状：**落盘同时写 `seal_name`（口径字段）与 `name`（兼容别名）**，服务层视图模型也仍暴露 `name`（＝`seal_name`）；`REQUIRED_SEAL_FIELDS` 已无 `name` 行。**建议规范把 §4.1.1 的 `name` 行标注为「＝印文 `seal_name`（可空）」或直接改名**——需 Zang 定稿，我不静默改规范。
2. **§4.1.1 表下注 ③ / AC-34 的「canonical 必填」**：现行文字未列出必填字段名单，本单后必填＝**朝代 / 分类 / 印面图**（印文移出），建议规范补一句「`seal_name`（印文）不在必填集」。
3. **显示取值顺序的适用范围**：Zang 裁定「印文＝`seal_name`；简体优先仅为好读」。本单**未改动任何取值顺序**，于是详情页 h1 与印面名（`SealDetailView.vue:233/261`）仍以 `seal_name` 为准 → **若某印章只填了「印文简体字」而没填印文，h1 会显示「佚名」**（卡片「当前印文」则显示简体）。这是既有逻辑的自然结果，是否需要把 h1 / 印面名也改成 `transcription_simplified || seal_name || 佚名`，请裁定（我未静默改）。
4. **同族取值点仍以 id 兜底（非「待考」词，本单未改）**：`SquareView.vue:131`（新印章提示的链接文字 `seal_name || id`）、`AdminView.vue:193`、`MyCorrectionsView.vue:44`、`MyPhotosView.vue:31`、`PointsView.vue:29`。是否统一到「佚名」，需口径——其中 `AdminView` / `MyCorrectionsView` 属本单禁改文件。
5. **`stamp_id` 与 `id` 的关系**：本单新编号同时写入 `stamp_id` 与 `id`（两者同值，维持既有兼容口径）。规范 §4.1.1 只列 `id`、未列 `stamp_id`，建议在表下注里明确「`stamp_id` ＝ `id` 的兼容别名」。
6. **编号格式的长度影响**：新编号 11 字符（旧 8 字符），扫描既有记录 O(n) 未变；编号词表与广场检索的 `haystack` 会随之变长，规范未对编号长度设上限，如需约束请补。
