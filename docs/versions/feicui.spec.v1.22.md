# feicui 侧规范（feicui.spec.md）

| 项目 | 内容 |
| --- | --- |
| 文档性质 | **feicui（印谱 PDF 解析工具）的独立侧规范**。本文件**只约束 feicui 自身**（`/Users/kevin/bistro/xiai/feicui/**`）；**平台侧（印索）规范一字不改**，跨界处**只作引用**（引用对象＝`/Users/kevin/bistro/xiai/docs/yinsuo-web.spec.md`，下称「平台规范」）。（**v1.4 路径收口**：**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**） |
| 端口真源 | 跨项目端口唯一真源＝**`/Users/kevin/bistro/ctrl/PORTS.md`**；运行时真源＝**`/Users/kevin/bistro/ctrl/index.js` 的 `services` 表**。本文件第 6 节是**登记口径**，端口数值以 PORTS.md 为准。 |
| 版本 | **v1.22**（2026-10-11｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-11 裁定「上传单文件上限默认调到 5 GiB（5368709120 B）」**（**输入**：Kevin 拖入 `~/Downloads/秦印类编 检索版.pdf`（**1.88 GiB**／**2,019,683,630 B**／**851 页**，核验时点 **2026-10-11**）被现上限拒（**`413 PAYLOAD_TOO_LARGE`** ＋ `declared_bytes 2,019,683,630`、「**未落盘即拒**」），他问「这个 PDF 体积上限是多少？可以再大吗？比如 5G 以内」⇒ **裁定：上传单文件上限默认调到 5 GiB（5368709120 B）**）——**本版性质 ＝ 文字同步 ＋ 结案待裁项**（§3.19.2 已明写「**改数值不需升规范**」⇒ **不新增 AC、不改任何判据逻辑**）：① **把规范里「默认 512 MiB」的现行有效处同步为「默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准；2026-10-11 起 ＝ 5 GiB（5368709120 B）」**——逐处落位 **§3.4 表 `413` 行**／**§3.19.2 单文件上限行**／**§7 AC-65**（**判据逻辑一字未改**，只使其引用新值）／**§3.19.7 待裁行**，并各留痕；**§3.4 加 v1.22 表下注**；② **§9 R40 结案**（**已结（Kevin 2026-10-11 裁定：上限默认 5 GiB）**；**保号留行不删行**；两本实测体积 / 页数、磁盘余量、下游代价逐字附上）＋ **§9 R41（`inbox/` 清理策略）仍挂起**（v1.22 复核未变）；③ **本版未新增、未改写任何判据**；**AC 计数仍 71（不增）**；**R 计数仍 41（不增）**——**未新立 R42**（理由逐字见 §9（v1.22）留痕）；④ **表头「版本」行 ＋ 表头「本版硬约束（v1.22）」行 ＋ §7 计数留痕（v1.22）一条 ＋ §9 计数留痕（v1.22）一条 ＋ §10 本版行逐处同步**；**历史行逐字保留、只增不改**（**v1.21 的「默认 512 MiB」叙述作为历史留痕原样保留**）；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.21.md`，md5 `2433b3596752be768fa47da1d3001758`、1892 行 / 583,553 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/config.py` / `server/app/routers/jobs.py`）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口、未 push**）｜**v1.21**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10 需求「【新建 job（E1）】页的 `pdf_path` 输入框改为拖曳文件，不必手动键入」**（**两条裁定照登**：① **拖动上传为主 ＋ 保留折叠的「高级：手输服务器路径」（默认收起）**；② **落点 `feicui/inbox/<yyyymmdd>/<原文件名>.pdf`，同名同内容复用**；**浏览器事实（写入作前提）**：**拖入的 `File` 不带本地路径 ⇒ 拖曳＝上传到服务器再拿服务器侧路径调 E1**）——**① 新增 §3.19「E8 拖曳上传端点契约（`POST /api/jobs/upload`）（5196）」（含 §3.19.1 〜 §3.19.7）**：**裸字节流式落盘**（`Content-Type: application/pdf` 或 `application/octet-stream`；**不得走 multipart**——理由：源 PDF 实测 38 MB、历史 **372 MB**，而仓内既有 `server/app/multipart.py` 是把整体读进内存的纯 stdlib 实现（`parse_multipart(content_type, body: bytes)`））＋ **文件名走请求头 `X-Filename`（URL-encoded UTF-8；回退 `Content-Disposition.filename`、再回退 `upload.pdf`）＋ 必须清毒**（basename、无路径分隔符 / `..` / 控制字符、长度上限）＋ **校验**（空体 ⇒ `400 EMPTY_BODY`；首字节非 `%PDF-` ⇒ `400 NOT_A_PDF`；超单文件上限（默认 **512 MiB**、`config` 常量可改）⇒ **`413 PAYLOAD_TOO_LARGE`**（**边写边判、不得先写满盘**）；**错误一律结构化 JSON**）＋ **幂等**（目标已存在且 sha256 相同 ⇒ 不重写、`idempotent:true`、**mtime 不变**；同名异内容 ⇒ **绝不覆盖**、落 `<basename>-<sha256[:8]>.pdf` 并标 `dedup_suffix:true`）＋ **响应 `201`（幂等 `200`）** `{pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}`（**`pdf_path` 可直接交给 E1**）＋ **红线：本端点零 DB 写、不建 job（同 §3.14 工具端点风格）、只落盘；不动 E1 与 E2〜E7**；**② §3.1 端点表新增 E8 行 ＋ 表下注（E8）一条**（**裁定：登记为 E 系列的 E8**——理由逐字见 §3.19 落位声明：E8 属 job 体系输入面（E1 的前置步骤）、与 E1〜E7 同族，须进同一「端点一览」注册表，避免同一 job 链路出现两张注册表；**§3.19 仅作 E8 的细则节、不作端点号**，故**不另开「§3.19 端点」**）；**③ 前端行为（§3.19.5）**：`pdf_path` **可见输入框改为拖放区**（可拖、可点击选文件；显示文件名＋体积；**上传用 XHR 给进度百分比**——372 MB 必须有进度）；上传成功后填隐藏字段并**只读显示**服务器侧路径与「已就绪」；失败（非 PDF / 超限 / 网络）**必须可见**；新增**折叠的「高级：手输服务器路径」**（**默认收起**）保留原输入框；**既有的 `page_range` / `chunk_size` / `rerun` / 409 提示 / localStorage 本机记录不得改变**；**色值只走 token**（§0.5.2）；**④ §3.4 错误码族随动**（**登记 `413 PAYLOAD_TOO_LARGE` 与 `400 EMPTY_BODY`**；**§3.2 S-6 加 v1.21 补注：码族由五码扩为六码（含 `413`），S-6 五码原文逐字保留**；**§3.4 表下注（v1.21）留痕**）；**⑤ §7 新增 AC-62 〜 AC-71（共 10 条，AC 计数 61 → 71）**；**⑥ §9 新增待裁项 R40 〜 R41（共 2 条，R 计数 39 → 41）**；**⑦ 表头「版本」行 / 表头「本版硬约束（v1.21）」行 / §7 计数留痕（v1.21）一条 / §9 计数留痕（v1.21）一条 / §3.19 落位声明（v1.21）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.20.md`，md5 `e8911ed84db367bf0f0818e665f42cb1`、1773 行 / 544,064 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/routers/jobs.py` / `server/app/config.py` / `server/app/main.py` / `JobsPage.vue`）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口、未 push**）｜**v1.20**（2026-10-10｜Jing：**按本文件 §0.4 流程落「关联面（三表联立）」需求**（**口径真源 ＝ `feicui/docs/relation-ingest-draft-v0.1.md`（Zang 2026-10-10 起草；§1 / §2 为实测读数、§3 为默认口径），逐条照登、不自行发明**）——**① 新增 §3.18「关联面（三表联立）」**（含 §3.18.1 〜 §3.18.8：**三表来源与行数**（`person_relations` **1650** / `item_creators` **1440** / `seal_links` **8964**）＋ **统一关系边键面**（`predicate` 五值枚举 `person_to_item` / `item_to_person` / `person_to_seal` / `seal_to_item` / `seal_to_person` ／ `subject_type` · `subject_id` ／ `object_type` · `object_id` ／ `role` · `role_note` ／ `evidence` 数组 ／ `source_ref` ／ `image_ref` ／ `name`（＋ `_chs`）／ `seq` ／ `batch_id`）＋ **幂等键 `(predicate, subject_id, object_id)`** ＋ **口径 R-a 〜 R-f（默认值逐条照登 ＋ 标「待 xiai 裁定、一句话可改」）** ＋ **就绪包 `exports/relation_import_<batch_id>/`**（`relations.jsonl` / `manifest.json` / `report.json`，**`key_face_status:"pending_xiai"`**）＋ **两个 additive 端点**（`POST /api/relations/package`（零联网、可选 `batch_id`、未白名单参数 400、批次不存在 404）、`GET /api/relations/summary`）＋ **红线**（零联网（不得再打复旦站点、纯本库联立）／只读三库三包／feicui 不写 xiai 任何文件）＋ **本需求不加页签、不动 tabbar（不触发 AC-23）**）；**② §7 新增 AC-55 〜 AC-61（共 7 条，逐条对应拆解件 §4 的 A-1 〜 A-7）**；**③ §9 新增待裁项 R35 〜 R39（共 5 条，归 xiai 线裁、逐项写后果）**；**④ 表头「版本」行 / 表头「本版硬约束（v1.20）」行 / §7 计数留痕（v1.20）一条 / §9 计数留痕（v1.20）一条 / §3.18 落位声明（v1.20）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.19.md`，md5 `814df2a5e6fda7d6dfa4ccbc36e974eb`、1652 行 / 507,960 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/relations.py` 与包）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.19**（2026-10-10｜Jing：**按本文件 §0.4 流程落「AC-41 原位收窄（超档允许、但必须逐行标记；未被标记的超档行才是 FAIL）＋ 源侧 `ref_id` 未命中 person 库记账口径 ＋ 端点响应顶层内部键 `_db_path` 观察项」**（**口径真源 ＝ Neng 独立质检 OBS-1 ＋ Zang 对本包实物（`feicui/exports/seal_import_seal_20261010_01/`）与三线端点实测逐条照登**）——**① §7 AC-41 原位收窄**（**字面判负由「单张 > 4 MiB ⇒ FAIL」收窄为「**未被逐行标记 `oversize_for_xiai_store` 的超档行 ⇒ FAIL**」——**超档本身不判负，但必须逐行标记；已标记的超档行豁免本 AC**；**并写明与 AC-54 的分工：AC-54 管「标记 / 顶层计数 / 清单 / 不得自行降采样或转码」，AC-41 管「容器与尺寸上限的可判定口径」**；**依据 ＝ Neng 质检 OBS-1：AC-41（v1.15 立 / v1.18 已部分原位改写）与 AC-54（v1.18 新立）对同一事实（6 张超档）一判负一豁免、下一轮质检无法机械判定；真值 ＝ 包内 `images/` 6347 张中 6 张 > 4 MiB（`seqid 3353/3366/3367/3464/3506/3510`，均 `yt`，4.38–4.96 MB），已逐行标 `oversize_for_xiai_store: true` ＋ 顶层计数 6 ＋ 清单；1–4 MiB 219 张**；**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md` §7**）；**② §3.17.8 加 a-v1.19 追加块**（**① 源侧 `ref_id` 未命中 person 库的记账口径**——**印主面 8/438 行、篆者面 1/403、边款篆者面 6/11 的 `ref_id` 不在 `var/person_ingest.db` 的 570 人内；属源侧引用未收录、不判负；`seal_links` 允许 `ref_id` 不命中 person 库，但必须在 `report.json` 给计数（按面分列 ＋ 合计）**；**② 端点响应顶层内部键 `_db_path` 观察项**——**三线对照 `GET /api/seals` / `/api/persons` / `/api/items` 顶层键完全相同（均含 `_db_path`）⇒ 系三线共有惯例、非本线不一致；登记为观察项（不判负、不立 R、不立 AC）**）；**③ 本版未新增 AC（AC 计数仍 54）／未新增 R（R 计数仍 34；原拟 R35 已撤回，逐字理由见 §9（v1.19））**；**④ 表头「版本」行 / 表头「本版硬约束（v1.19）」行 / §7 计数留痕（v1.19）一条 / §9 计数留痕（v1.19）一条 / §3.17 落位声明（v1.19）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.18.md`，md5 `142349f93f6c867213f875d073a20636`、1640 行 / 491,387 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.18**（2026-10-10｜Jing：**按本文件 §0.4 流程落「印章影像面逐张台账字段语义纠偏（以包内实物为准）＋ AC-41 / AC-51 删去恒假的『输入档 ≤ 1 MB』判据 ＋ 新增 AC-54（超档逐行标记）＋ R34 ＋ 端点 mime 写清」**（**口径真源 ＝ Zang 对本包实物（`feicui/exports/seal_import_seal_20261010_01/`）实测逐条照登 ＋ xiai `server/app/store.py` 只读引用**）——**① §3.17.8 ④ 逐张台账字段语义原位更正**（**`sha256` ＝ TIFF 字节的 sha256（即内容寻址键、＝文件路径名）；`bytes` ＝ TIFF 字节数；新增 `source_bytes` / `source_sha256` ＝ 源 JPEG 侧（溯源用）；删去对 `tiff_sha256` 键的引用——包内实物 `images_manifest.jsonl` 无此键**）＋ **§3.17.5 成员 6 键面随动**；**② §7 AC-41 / AC-51 原位改写**（**判据只留「单张 ≤ 4 MiB（`STORED_MAX_BYTES`）＋ 逐行 TIFF 魔数」；删去「输入档 ≤ 1 MB」**——**依据 ＝ xiai `server/app/store.py::validate_payload` 只校验「空 / 4 MiB / TIFF 魔数」三面；`MAX_INPUT_BYTES` ＝ 1 MB 属 xiai 编解码口输入面，不得用作本包 / 本端点判据**）＋ **§7 AC-50 随动（`tiff_sha256` ⇒ `sha256`）**；**③ §7 新增 AC-54**（**`> 4 MiB` 的行须逐行标记（`oversize_for_xiai_store`）＋ 顶层计数 ＋ 清单，且不得自行降采样 / 转码**；⇒ **AC 计数 53 → 54**）；**④ §9 新增待裁项 R34**（**6 张超 xiai store 4 MiB 上限影像在 xiai 侧的去留**；⇒ **R 计数 33 → 34**）；**⑤ §3.17.3 端点表追加 S6**（`GET /api/seals/{seqid}/image/{kind}` ＝ **`image/jpeg`（源 JPEG 缓存，供页面缩略图；与包内 TIFF 交付面无关）**）；**⑥ 表头「版本」行 / 表头「本版硬约束（v1.18）」行 / §7 计数留痕（v1.18）一条 / §9 计数留痕（v1.18）一条 / §3.17 落位声明（v1.18）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.17.md`，md5 `4e33681c38a7a445ac39f9371998ad05`、1625 行 / 472,273 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.17**（2026-10-10｜Jing：**按本文件 §0.4 流程落「印章影像面子因由二扩三（补 `bad_bytes`）＋ `failed` ＝ 0 改口径 ＋ AC-53」**（**口径真源 ＝ Zang 影像台账终态实测 6765/6765 逐条照登**）——**① §3.17.8 a-v1.16 块的 `source_no_image` 子因行由「两类」原位扩为「三类」**（新增子因 **（c）坏字节 `bad_bytes`**：**HTTP `200` ＋ `content-type: image/jpeg`、正文非图像 / 不可解码**；**实例 `2_3609_1`：正文 697 B 为 iipsrv 把自己的响应头当正文吐出、非 JPEG 魔数、PIL 解码失败、持久复现**）＋ **`failed` 行原位改写为「收尾时 `failed` ＝ 0」**（**因三子因已穷尽枚举；将来新第四类须先入册再归类、不得静默落 `failed`**）＋ **判负形态随动**；**② §3.17.8 a. 影像面加 v1.17 追加块**（子因穷尽枚举三类 / `bad_bytes` 实例锚 `2_3609_1` / `failed` ＝ 0 理由）；**③ §7 AC-47 原位改写为「`failed` ＝ 0」＋ AC-48 证据形式随动（子因计数由两类扩为三类）＋ 新增 AC-53**（**承载 `bad_bytes` 实例归 `source_no_image` 面不在 `failed`**；⇒ **AC 计数 52 → 53**）；**④ §9 R33 行子因随动注（新增（c））＋ §9 计数留痕（v1.17）**（**R 计数仍 33、未新增 R：`bad_bytes` 属既有 `source_no_image` 分桶、其 xiai 侧去留恰为 R33 所问，理由逐字见 §9（v1.17）留痕**）；**⑤ 表头「版本」行 / 表头「本版硬约束（v1.17）」行 / §7 计数留痕（v1.17）一条 / §9 计数留痕（v1.17）一条 / §3.17 落位声明（v1.17）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.16.md`，md5 `391ac0e3cd4295ee7106784b5b1dbdd5`、1611 行 / 456,294 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.16**（2026-10-10｜Jing：**按本文件 §0.4 流程落「印章影像面三态分桶 ＋ 共用窗口限流 ＋ 可机械判负面」口径纠偏**（**口径真源 ＝ Zang 在 v1.15 落盘后实测的缺口逐条照登**）——**① §3.17.8 影像面追加/修正**：**源侧缺图独立分桶（三态 `ok` / `source_no_image` / `failed`）**——`source_no_image` 子因 **① `NaN_` 开头 ref；② 持久 `HTTP 500`（有界重试 3 轮 2/8/30s 后仍 500）**，`failed` **仅留给可重试的瞬态错误**；**`source_no_image` 不得计入采集失败、不得静默丢弃**；**观测证据**：60 refs 中 **11 条 `HTTP 500`**（响应体 `text/plain` 21 字节 `Internal Server Error`、**无跳转**），**1/4/8 并发下失败集合完全相同（49 ok / 11 fail）、0 次 429** ⇒ **按 ref 恒定、非限流**；失败 ref **按前缀聚批**（`11_*`/`12_*` 全挂、`19_*` 正常）；**站点自身详情页同一 ref 图 `naturalWidth=0`（坏图）**、正常 ref 渲染 204×365；**共用窗口限流**：**影像请求与 API 请求共用站点级窗口** ⇒ **429 一律判负、不得当成功**（出现即降并发＋退避）；实测 8 workers × 0.1s ⇒ 0 次 429、**17.2 张/秒**；**影像面每张记录 `width`/`height`/`bytes`/`tiff_sha256`** 与 **双档上限（xiai 产物 4 MiB / 输入 1 MB）**；**放大尺寸判负保留 v1.15 原文并补定量依据**（证据文件 `ops/seal-ingest/09_upscale_probe.json`；同区域 `full→204×365 / 400,→400×716 / 1200,→1200×2147 / 4096,→2795×5000`；Pillow 判定纯插值：边缘强度双三次上采样 **135.71** vs 服务器 1200 大图 **137.69**（差 1.5%）、MAD **4.32/255**、累方差 2858 vs 2824 ⇒ **不增真实信息**）；**② 新增 AC-47 〜 AC-52（共 6 条 ⇒ AC 计数 46 → 52）**——`failed` 桶空或仅瞬态且附重跑命令 / `source_no_image` 按 ref 前缀聚合清单＋计数＋样例 seqid / **`images_manifest.jsonl` ↔ `images/**` 双向一一对应（无孤儿、无缺失，给两个方向计数）** / 每行 `sha256` 与 TIFF 字节逐行自洽（随机 20 行重算）/ **TIFF 魔数逐行成立 ＋ 单张 ≤ 双档上限** / 台账每行有 `width`/`height`；**③ 新增待裁项 R33（1 条 ⇒ R 计数 32 → 33）**（**源侧缺图在 xiai 侧的去留：留空白行 vs 不落行**）；**④ ⚠ 原位改写 §3.17.8 的 `NaN_` ref 状态口径 ＋ §7 AC-40 的同一记号**（原写 `status=source_missing` ⇒ 统一为 **`source_no_image`**；原文字逐字留存于快照 `docs/versions/feicui.spec.v1.15.md`；**系原位改写，不是「既有条款自动失效」**）；**⑤ 表头「版本」行 / 表头「本版硬约束（v1.16）」行 / §7 计数留痕（v1.16）一条 / §9 计数留痕（v1.16）一条 / §3.17 落位声明（v1.16）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.15.md`，md5 `b542ff939c72c845201bee54244ec8b9`、1585 行 / 434,875 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.15**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10「印章全量包」需求**（**第三条采集线（与 §3.15 印人、§3.16 印谱同型）**；**口径真源 ＝ Zang 已实测的源契约 ＋ Kevin 三条裁定 A / B / C —— 逐条照登、不自行发明**）——**① 新增 §3.17「印章（seal）采集」（含 §3.17.1 〜 §3.17.9）**：**第四页签【印章采集】＋ 路由 `/seals`**（base 取 `import.meta.env.BASE_URL`；沿 §3.15.2 v1.9 注）＋ **五个新端点**（`POST /api/seals/sync` / `GET /api/seals` / `GET /api/seals/{seqid}` / `GET /api/seals/batches` / `POST /api/seals/package`；**additive、不动 E1 〜 E7 与 P1 〜 P4 / Q1 〜 Q5**）＋ **新独立库 `feicui/var/seal_ingest.db`**（表 `seals` / `seal_links` / `seal_import_batches` / **`seal_images`**；**与 `var/person_ingest.db` / `var/item_ingest.db` 分库、`yinpu.db` 一字不碰**）＋ **就绪包 `feicui/exports/seal_import_<batch_id>/`**（`seals.jsonl` / `seal_links.jsonl` / `manifest.json` / `report.json` / `images/` / `images_manifest.jsonl`；**候选键面未裁 ⇒ `key_face_status: "pending_xiai"`**）＋ **采集口径**（`seal/list` `pageRows=5000` 一次取全 3679 ＋ **形製码表本地派生** ＋ `seal/detail` 降 best-effort（**默认关**）＋ 断点续跑 ＋ 礼貌限速 ＋ 失败清单；限流 `code:"429"` 不得当成功）＋ **字段面与归一化**（**`null` 不得写空串 / `0` 特值**；繁体为正 ＋ `*_chs`；`raw_json` 不丢源；**保留 `audit_status` 字段与分布统计**）＋ **影像面（v1.15 改口径｜Kevin 裁定：TIFF 直供）**（**全部直供 xiai 影像库**：印面 3679 ＋ 印体释文 2627 ＋ 边款 459 ≈ **6765 张**；**本侧取图走 IIIF 只用原生裁切 `/full/0/default.jpg`、禁止放大尺寸**；**JPEG → TIFF 无损容器转换**；**就绪包 `images/` 镜像 xiai 形态 ⇒ `images/<sha256[:2]>/<sha256>.tiff`、包内不放 JPEG**；**`images_manifest.jsonl` 为唯一索引**；**重出包不得删或重转已有影像**；`NaN_` 开头 ref 记「源侧无图」）＋ **跨工程边界**（feicui 不写 xiai 文件 / 不调云函数）；**② 新增 AC-34 〜 AC-46（共 13 条 ⇒ AC 计数 33 → 46）**；**③ 新增待裁项 R29 〜 R32（共 4 条 ⇒ R 计数 28 → 32）**；**④ ⚠ 原位改写 AC-23**——**页签集合 3 → 4**（**恰为【印谱解析】/【印人采集】/【印谱采集】/【印章采集】**；判负「页签数量 ≠ 3」随动为「≠ 4」），行内加「v1.15 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.14.md` §7（**系原位改写，不是「既有条款自动失效」**）＋ **§3.15.2 v1.9 注 ＋ §3.16.2 对页签集合的 v1.15 追注随动**）；**⑤ 表头「版本」行 / 表头「本版硬约束（v1.15）」行 / §7 计数留痕（v1.15）一条 / §9 计数留痕（v1.15）一条 / §3.16 落位声明（v1.15）＋ §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.14.md`，md5 `5651c5fd7cad6a88081f9a311a6b6745`、1399 行 / 382,380 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.14**（2026-10-10｜Jing：**按本文件 §0.4 流程落「印谱（item）采集 — spec/实现分叉收口 ＋ 重建幂等口径登记」**（**输入 ＝ Neng 质检 OBS（均不判负、需收口）**：**① `POST /api/items/package`（Kong 实现中 additive 追加的第五端点）未入规范 ⇒ spec/实现分叉**；**② 点按钮重建就绪包会重写时间戳（实测 `created_at` 15:39:16 → 15:42:03）而两个 JSONL 逐字节未变**）——**① §3.16.3 端点表追加 Q5 `POST /api/items/package` 契约**（**语义 ＝ 从 `var/item_ingest.db` 本库重建就绪包、不联网采集、与 CLI `package` 共用实现**；**入参 ＝ 查询参数仅白名单 `batch_id`（可选，缺省＝库内最新批次）**；**错误码 ＝ 未白名单参数 400（`UNSUPPORTED_PARAM`）/ 批次不存在 404（`BATCH_NOT_FOUND`）/ 库内无批次 404（`NO_BATCH`）/ 其余 409，一律结构化 JSON**；**响应 ＝ 就绪包摘要**；**两条红线 ＝ 零联网 ＋ 不写 xiai 任何文件**）；**② §3.16.5 补「重建幂等」口径**（**仅 `created_at` / `generated_at` 与 manifest 时间戳变化，两个 JSONL 内容逐字节不变**）；**③ §7 新增 AC-33（共 1 条 ⇒ AC 计数 32 → 33，AC-01 〜 AC-33）**（**承载「`/api/items/package` 可达且重建后 JSONL 字节不变、仅时间戳变」＋ 两条负向（未白名单参数 400 / 批次不存在 404）**）；**④ §7 计数留痕（v1.14）一条 ＋ §9 计数留痕（v1.14）一条（R 计数不变，仍 28 条）＋ §10 本版行 ＋ 表头「版本」行 / 表头「本版硬约束（v1.14）」行 / §3.16 落位声明逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.13.md`，md5 `5dfcb49edbeb8dc5587f371c6ffbf5be`、1385 行 / 367,653 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.13**（2026-10-10｜Jing：**按本文件 §0.4 流程落「实测驱动的采集口径偏离」——对 v1.12 旧口径（列表 1 次 ＋ 逐本 detail、**不采 `graph/book`**）的正式偏离**（**口径真源 ＝ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §10（Zang 2026-10-10 采集口径偏离登记）**；**理由 ＝ 实测限流**：**`book/detail/<seqid>` 严限流**（Kong 实跑日志 `5/10/20/40/60s` 退避反复、我方另测该端点间歇 `429`）⇒ **「逐本 detail 取本体」在 1742 本量级不可行**；**`graph/book/<seqid>` 实测健康**（2 s 间隔 3/3 成功）**且同样给 `creatorType` ＋ `personGrbsm`**）——**① §3.16.6「⑤ 采集口径」原位改写**：**item 本体全部取自 `book/list` 一次全量**（不再逐本 detail 取本体）＋ **item↔person 关联主源改 `graph/book/<seqid>`**（`source_face='book_graph'`，与既有 `person_relations`（`source_face='person_graph'`）**合并去重**）＋ **`book/detail` 降为 best-effort（默认关，显式开关才开）**（仅补 `creatorRole` / `creatorRelator` / `bookDonor`，慢速分片、失败进清单、**不阻塞主交付**）＋ **manifest / report 必含 `detail_policy` ＋ 因 detail 降级缺失的三字段 ＋ `detail_unconfirmed` 计数**；**旧口径原文逐字保留并标「已被 v1.13 取代」（系原位改写＝对旧口径的正式偏离，非「既有条款自动失效」）**；**② §3.16.8 sidecar 随动**：`source_face` 取值集合明确为 `book_graph` / `person_graph` / `book_detail`（后者仅 best-effort 开启 detail 时出现）；**③ 逐条校正受影响 AC（编号 / 条数不变，仍 32 条）**：**AC-28**（`donor`／`bookDonor` 降 best-effort，缺失不判负、存在须逐字命中）＋ **AC-31**（manifest 必含项增补 `detail_policy` / 缺失三字段 / `detail_unconfirmed`）**原位改写**；**④ §7 计数留痕（v1.13）一条 ＋ §9 计数留痕（v1.13）一条（R 计数不变，仍 28 条）＋ §10 本版行 ＋ 表头「版本」行 / 表头「本版硬约束（v1.13）」行 / §3.16 落位声明逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.12.md`，md5 `b5581b7fd995e21f0f08a71676bbe8a2`、1369 行 / 349,648 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.12**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10「印谱（item）采集」需求**（**口径真源 ＝ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md`（Zang 2026-10-10）＋ 实测源契约（`book/list` `pageRows=3000` 一次取全 1742 本；`book/detail/<seqid>` 多出 `creatorList` / `titleList` / `itemList` / `bookDonor`，**`creatorList` 含 `personGrbsm`**；**`graph/book` 本轮不采**）；**本版逐条照登、不自行发明**）——**① 新增 §3.16「印谱（item）采集」（含 §3.16.1 〜 §3.16.9）**：**第三页签【印谱采集】＋ 路由 `/items`**（base 取 `import.meta.env.BASE_URL`；沿 §3.15.2）＋ **四个新端点**（`POST /api/items/sync` / `GET /api/items` / `GET /api/items/{seqid}` / `GET /api/items/batches`；**additive、不动 E1 〜 E7 与 P1 〜 P6**）＋ **新独立库 `feicui/var/item_ingest.db`**（表 `items` / `item_creators` / `item_import_batches`；**与 `var/person_ingest.db` 分库、`yinpu.db` 一字不碰**）＋ **就绪包 `feicui/exports/item_import_<batch_id>/`**（`items.jsonl` / `item_creators.jsonl` / `manifest.json`；**候选键面未裁 ⇒ `key_face_status: "pending_xiai"`**）＋ **采集口径**（列表 1 次 ＋ 逐本 detail，**不采 `graph/book`**，断点续跑 ＋ 礼貌限速 ＋ 失败清单；限流 `code:"429"` 不得当成功）＋ **字段面与归一化**（照登拆解件 §3；`volume_count` / `date_year` 整数或 `null` 禁特值；繁体为正 ＋ `*_chs`；`raw_json` 不丢源）＋ **跨工程边界**（feicui 不写 xiai 文件 / 不调云函数）＋ **item↔person sidecar**（合并 `book_detail.creator_list` 与既有 `person_relations`，带 `source_face`；**并写明 `source_face` 与 person 侧已删的 `from` 不是同一概念**）；**② 新增 AC-25 〜 AC-32（共 8 条 ⇒ AC 计数 24 → 32）**（底稿 ＝ 拆解件 §7 的 IT-1 〜 IT-8，逐条「判据 / 证据形式 / 判负形态」三元组）；**③ ⚠ 原位改写 AC-23**——**页签集合 2 → 3**（**恰为【印谱解析】/【印人采集】/【印谱采集】**；判负「页签数量 ≠ 2」随动为「≠ 3」），**行内加「v1.12 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.11.md` §7**（**系原位改写，不是「既有条款自动失效」**）；**④ §9 新增待裁项 R25 〜 R28（共 4 条 ⇒ R 计数 24 → 28）**（底稿 ＝ 拆解件 §8 的 WI-1 〜 WI-4）；**⑤ 表头「版本」行 / 表头「本版硬约束」行 / §7 计数 / §9 计数 / §10 本版行逐处同步**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.11.md`，md5 `7e7f75d9fd76bd9076df4534a1bd37a6`、1208 行 / 313,554 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）/ `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.11**（2026-10-10｜Jing：**按本文件 §0.4 流程落「xiai 侧 D-1 回执（键面 18 → 21）」与「Kevin 2026-10-10 关联面裁定（本轮先只落印人本体）」两件输入**（**D-1 回执逐字照登、不改写；口径真源 ＝ xiai 线回执 ＋ `xiai/docs/xiai.spec.md` v1.57（§3.54.19 ＋ §4.1.16 追加注 ＋ AC-507〜510，**只引用**））——**① §3.15.11 追加升版注（v1.11）**：**主交付键面 18 → 21**（**逐字列出 21 键**；3 新键 `courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction` **紧随各自值键（`courtesy_names` / `art_names` / `alias_names`）之后**）；三键语义与形态 ＝ **`string[]` / 与对应值数组等长 / 元素非空字符串 / 值域不封闭（不得据 `rule-based` 硬校验）**；**缺键不拒收（18 键形态仍可直接提交）**；**违形态由 xiai 侧判 `INVALID_VALUE` ＋ 零写入**；**采纳后不落 person 行**（extraction 只留导入行作溯源）；`person_imports_extraction.jsonl` **降为「派生冗余件（兼容保留）」**（同一计算结果导出、**非第二真源**）；**manifest 必含项随动**（允许键 **21** / 键面 diff **vs 21**）；**② §7 AC-24 同步为三态判据**——**(a) 21 键形态 PASS**；**(b) 18 键形态（缺 3 键）亦 PASS（兼容）**；**(c) 旧 feicui 形态（32 键 / 三桶为对象数组）FAIL**；并写明 **`'rule-based'` 只作本批数据断言、不得写成对外契约判据**；**③ 新增 §3.15.12「关联面范围裁定（v1.11 新增）」**——**登记 Kevin 2026-10-10 裁定「本轮先只落印人本体」**：**1650 条关联（印人 → 印谱 / 印章）留在 feicui 侧**（`exports/person_20261010_01/relations.jsonl` 留在原处、可复跑、数据不丢），**关联作为独立需求另开**；**④ §9 待裁面**：**R22 / R24 逐条处置**（**已被本裁定取代者**另注状态、**仍待裁者**保号留行）；**⑤ §9 未新增待裁项（R 计数仍 24）**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.10.md`，md5 `7eebeafec8137703c3edd0f574696d06`、1167 行 / 297,420 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/exports/**` / `feicui/var/**`、未动 `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）、未动 `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.10**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10 三答与「xiai 就绪导入包」交付缝扩展**（**口径真源 ＝ 交接件 `feicui/docs/person-ingest-handoff-v0.1.md` 第七节**，Zang 2026-10-10 写入；**本版逐条照登、不自行发明**）——**① 新增 §3.15.11「xiai 就绪导入包（对外导出面）」**：按钮「**生成 xiai 就绪导入包**」＋ **两个新端点**（`POST /api/persons/import-package` / `GET /api/persons/import-packages`）＋ **产物目录** `feicui/exports/person_import_<batch_id>/` 与三文件（`person_imports.jsonl` / `person_imports_extraction.jsonl` / `manifest.json`）＋ **主交付严格限在 xiai 现行 18 键**（**逐字列出**；来源 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`，**跨仓契约只引用、不复制其代码**）＋ **三桶降为 `string[]`（只 `value`）且保留 extraction 标注**（sidecar、与对应值等长、**不含 `from`**）＋ **生卒整数或 `null`** ＋ **manifest 必含项**（`schema_version` / 键面 diff＝0 / 幂等键唯一计数）＋ **跨工程边界（feicui 不得写 xiai 文件、不得调云函数）** ＋ **审核门维持**；**② 登记两条外部依赖（只登记、不代写）**——**D-1**：xiai 侧需扩 3 键（`courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction`，**归另一会话按其自己规范流程**）；**D-2**：xiai 侧提交需可验证令牌（`imported_by` 由服务端从令牌派生 ⇒ `uid`）⇒ **提交动作不在 feicui 侧**；**③ §7 新增 AC-24（共 1 条 ⇒ AC 计数 23 → 24）**——五条可机械判负子项（键面 ⊆ 18 键且无多余键 / 三桶为 `string[]` / sidecar 三数组等长且元素恒 `rule-based` 且无 `from` / 行数＝570 且幂等键唯一 / manifest 键面 diff＝0）；**④ §3.15.2「采集区」追加 v1.10 注**指向新端点；**⑤ §9 未新增待裁项（R 计数仍 24）**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.9.md`，md5 `3e73e508476f3f56ff714a70fee9322b`、1091 行 / 280,116 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/exports/**` / `feicui/var/**`、未动 `xiai/**`、未动 `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.9**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10 新口径「页签【任务页】→【印谱解析】＋ tabbar 下移 / 顶部固定页眉标题区」**——**① §3.15.2「① 页签与路由 `/persons`」追加 v1.9 注**：登记页签文案**现为【印谱解析】（原【任务页】）与【印人采集】**、**顶部＝固定页眉＋标题区（吸顶 / 固定、不透明背景、色值走 token）**、**tabbar 位于核心内容区顶部（`main` 内、`RouterView` 之前、不在页眉内）**、**固定页眉不得遮挡内容**（**系新口径、非既有条款改写**）；旧行「**现导航仅【任务页】一项**」**原文逐字保留**并标**已被 v1.9 取代**；**② §7 新增 AC-23「页签文案与 tabbar / 固定页眉布局」（共 1 条 ⇒ AC 计数 22 → 23）**，含**三条可机械判负子项**（页签文案恰为【印谱解析】与【印人采集】／tabbar 位于 `main` 内且在 `RouterView` 之前／固定页眉滚动后仍贴顶且不遮挡内容）；**AC-14 行内文字一字未改**，只**追加 v1.9 注**指向 AC-23；**③ §3.8「任务页需要列表」行追加 v1.9 注**；**④ §9 未新增待裁项（R 计数仍 24）**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.8.md`，md5 `3ed4310223233cca78a355c2bb62cfd5`、1080 行 / 270,552 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**`（实现由 Kong 并行另一单负责）/ `feicui/server/**`、未动 `ctrl/**`、未动 xiai 规范**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.8**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10 追加裁定「批 2（写入 xiai 的通道）由另一会话承接」并冻结交付缝**——**① §3.15.1 表下注追加一条（v1.8）**：登记该范围裁定（**feicui 侧职责收窄为「采集 / 归一化 / 落 feicui 本库 / 产出批次包」；feicui 侧不得写 xiai 任何文件、不得做任何 CloudBase 写操作**；**该句系新裁定、非既有条款改写**）＋ 指向交接件 `feicui/docs/person-ingest-handoff-v0.1.md`（**只引用、不复制其全文**）；**② 新增 §3.15.10「交付缝（对外接口面，冻结）」**：批次包四文件 ＋ `manifest.json` 必含字段（**`schema_version` 本版钉为 `1`**）＋ JSONL 形态 ＋ 幂等键 ＋ 溯源字段 ＋ 繁简存法 ＋ 抽取标注 ＋ 生卒 `null` 禁特值 ＋ **失败项只进 `report.json`**；**③ §7 新增 AC-21 / AC-22（共 2 条 ⇒ AC 计数 20 → 22）**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.7.md`，md5 `cf59f8c76b1915b59dc5708894909acf`、1032 行 / 257,941 B，`cmp` 逐字节一致）**；**未动 xiai 规范、未碰任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `feicui/exports/**` / `feicui/var/**`、未动 `ctrl/**`**；**未跑构建 / 测试、未起服务、未占端口**）｜**v1.7**（2026-10-10｜Jing：**按本文件 §0.4 流程落 Kevin 2026-10-10「印人采集」需求（口径真源 ＝ 拆解件 `feicui/docs/person-ingest-draft-v0.1.md`，Zang 2026-10-10；本版逐条照登、不自行发明）**——**① 新增 §3.15「印人采集」（含 §3.15.1 〜 §3.15.9）**：页签与路由 `/persons` ＋ 四条新端点契约（`/api/persons/sync` / `/api/persons` / `/api/persons/{grbsm}` / `/api/persons/batches`）＋ 独立 SQLite `feicui/var/person_ingest.db`（**不动 `yinpu.db`**）＋ 批次包 `exports/person_<yyyymmdd>_01/` ＋ 归一化与繁简存法 ＋ 礼貌限速 / 断点续跑 / 失败清单 ＋ 零外链资源与「联网只在服务端且只读」红线**；**② §7 新增 AC-14 〜 AC-20（共 7 条，AC 计数 13 → 20；底稿 ＝ 拆解件 §7 的 A-1 〜 A-7）**；**③ §9 新增待裁项 R21 〜 R24（底稿 ＝ 拆解件 §8 的 W-P1 〜 W-P4；R 计数 20 → 24）**；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.6.md`，md5 `88c6df8150f31c4009892acdfc27401c`、909 行 / 234,138 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `yinpu.db`、未动 `feicui/web/**` / `feicui/server/**` / `feicui/exports/**`、未动 `ctrl/**` 与 `xiai/docs/xiai.spec.md`（玺爱侧由其自己的 §1.3 流程同轮改）**；**未跑构建 / 测试、未起服务、未占端口、未 kill / 停 / 重启任何进程**）｜**v1.6**（2026-09-20｜Jing：**按本文件 §0.4 流程落「斐萃收尾四件事（F-1 〜 F-5）」**——**① 新增 §3.14（工具端点 `POST /api/tools/square-crop`（5196）完整契约：multipart 字段名逐字 `image` / 四个可选参数 / 响应字段集（`candidates[]` 的 `idx`/`bbox`/`square`/`side`/`width`/`height`/`mime`/`sha256`/`image_base64`/`area`/`aspect`/`degraded`）/ 错误码 400·422·500 **一律结构化 JSON、绝不返回 HTML 错误页** / CORS 白名单唯一真源（含 5163）/ **零 DB 写 · 不建 job · 不落盘** 红线；＝ F-1）**＋**② 新增 §5.5（惰性 OCR 替身口径 ＋ **冷启动测量口径**：**同机 A/B ＋ 交错多轮 ＋ 取中位数 ＋ 同时给绝对基线与相对 A/B 两个口径**；含「不做」清单；＝ F-2 / F-3）**＋**③ **来源标签口径**（`min_area_source` **不得引用不存在的来源**——`templates.json` 无 `default` 项 ⇒ 以内建常量为准并**如实标注常量位置与语料核验结果**；是否补 `default` 项登记为待裁 **R18**；＝ F-4）**＋**④ **玺爱接入状态 ＝ 已具备、暂不接入**（玺爱上传**零 5196 调用、零外链**；写明原因与将来适用场景「整页扫描含多枚印面」；＝ F-5，与玺爱侧 R-18 / §3.12.6 对齐）**＋**⑤ 新增待裁项 **R18**（是否在 `config/templates.json` 补 `default` 项）／**R19**（`server/README.md` 历史示例路径仍写 `/Users/kevin/bistro/shu/…`，登记待订正）／**R20**（冷启动**绝对基线**在 README §12.6 与 ops 证据里口径不一，是否统一）；**只写文档（本文件一处、先存快照）**；**未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `xiai/src/**`、`xiai/web/**`、`xiai/feicui/ops/**`（只读引用）、`ctrl/**`、平台规范、`xiai/docs/xiai.spec.md`（玺爱侧由其自己的 §1.3 流程同轮改）**；**未 kill / 停 / 重启任何进程、未占端口**）｜**v1.5**（2026-09-20｜Jing：按本文件 **§0.4 流程**落 **Kevin 2026-09-20 追加的两条口径**——**V-2（最高优先，方向性）**：**数据结构以玺爱为主**；斐萃（feicui）**此前的库结构并不完善、后者向前者靠**；斐萃既有表（`stamps` / `seals` / `images` / `export_batches` / `export_records` / `jobs`）的字段**仅作为「斐萃旧结构 → 玺爱 canonical」的入库映射来源**，**不得**反过来让玺爱迁就斐萃。**留痕（本工作台已发生过的失真形式，必须写明）**：**本文件改版前不存在任何「数据模型对齐斐萃」类表述，亦无任何数据方向条款**（核验时点 **2026-09-20 15:55**，证据＝`grep -n '对齐斐萃\|以斐萃\|数据模型\|canonical\|玺爱' feicui/docs/feicui.spec.md` **零命中**）⇒ **本条款属「新增条款」，不是既有条款被改写**（**不得**说成「既有条款方向反转」）。**V-1**：产品展示名＝**【斐萃】**；UI 配色＝**蓝绿色的宝石感**——落成**可判负条款**（展示名封闭 ＋ 色值一律走 CSS 变量 token ＋ 承担信息传递的图形元素对相邻背景非文本对比 **≥ 3:1** ＋ 槽位专用 token 不得跨用途复用）；落位 **§0.5**。**并如实登记本轮已落地的实现读数与「未落地 / 待裁」项（带时点戳、区分已落地与未落地）**，落位 **§0.6**；**§1.2 新增不变量 I-5（V-2 方向）**。**只写文档**（本文件一处）：**未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**；**未动 `xiai/web/**`、`ctrl/index.js`、`ctrl/public/**`、`xiai/src/**`、`xiai/docs/xiai-plan.md`**；**未 kill / 停 / 重启任何进程、未占端口**（核验时点 **2026-09-20 15:55**：5163 上由人类手动起的 dev server（`node` PID **91247**）照常 `LISTEN`，**未受影响**）。**AC 计数仍 13 条**（本版不改任何 AC 判据）；**历史行逐字保留、只增不改**；**改版前先存快照** `/Users/kevin/bistro/xiai/feicui/docs/versions/feicui.spec.v1.4.md`（md5 `9b246d25206c1a2353a056876733b088`、**675 行 / 177,059 B**，`cmp` 与改版前主文件**字节一致**））｜**v1.4**（2026-09-20｜Jing：按本文件 **§0.4 流程**一次性收口**工程改名（`shu` → `xiai`）的路径口径**+ **P9 池托管裁定** + **G-1b（E3 `idx` 锚点）** + **两条已实测 def- 类事实（E6 头值编码 / E7 有效态过滤）**+ **数据现状刷新（`stamps` 89 行 / `jobs` 5 行）**（**只写文档：本文件 + 平台规范 v1.29 + `ctrl/PORTS.md` v1.12，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件；未动 `xiai/web/**`；未启停任何服务、未占端口；未动 `feicui/server/**`、`feicui/web/**`、`ops/**`、`qa-recheck/**`、`spike-ocr/**`、`qa-baseline/**`、`labeling/**`**）——**① 路径迁移登记（2026-09-20 14:47 工程改名；改名非 Jing 执行）**：整个 `shu` 工程被改名为 **`/Users/kevin/bistro/xiai/`**（`~/bistro/shu/` 只剩空 `.vite` 壳、**零文件**；实测 xiai 侧 **33,596** 个文件）；**本文件内所有以 `/Users/kevin/bistro/shu/...` 起头的现行有效引用一律原位更正为 `/Users/kevin/bistro/xiai/...`**，逐处留痕「**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**」；**可复跑判据**：`ls -d /Users/kevin/bistro/shu/feicui/yinpu.db` ⇒ **`No such file or directory`**、`ls -d /Users/kevin/bistro/xiai/feicui/yinpu.db` ⇒ **命中**。**改版前本文件提及 `xiai` 0 处、写 `/Users/kevin/bistro/shu` 17 处（8 行）**；**现行有效引用全部收口**（落位：表头「文档性质」/ §6.2 表 `cwd` 与启动命令 / §9-R6 / §9-R7，**共 9 处原位更正**；「§6.2 表下 v1.3 注 ①」的 13:08 md5 锚定引文**按快照式引文保留原文**+ **追加 v1.4 路径取代注**）。**§0.3 新增 v1.4 注**＝路径迁移 + 数据现状刷新。**② §6.2 表下 v1.4 注：`index.js` 实况刷新（3 条 feicui 族条目）+ 池托管裁定收口**——核验时点 **2026-09-20 14:59**，`ctrl/index.js`（md5 `143137f25c717596d4a8260db686794f`、52,651 B）`services` 表共 **12 条**；feicui 族 **3 条**（`shu` / `feicui-api` / `feicui-web`），`cwd` 与 `FEICUI_DB` 均已指 `xiai`；**「池」不入 `services` 表＝ Zang 已定案（采纳选项 ①）**，改由 **API 提交 job 后异步、detached 拉起** `app.pool --workers 4 --drain`（env 带 `FEICUI_ALLOW_PROD_MIGRATE=1`）、**API 启动扫 `QUEUED`/`RUNNING` 补跑**；**已有池在跑 ⇒ 退出码 5 属正常分支（不得当故障）**；依据＝`server/app/poolctl.py` + `ops/1c/1c_double_start_evidence.txt`。**③ G-1b 入账（§3.12 补一行冻结）**——E6 需要 `(page, idx)`，而 §3.12 此前只冻结了 `page` 的键路径（顶层 `sourcePageNo`），**`idx` 无规范明文冻结** ⇒ 现**冻结 `idx` 的规范键路径＝`feicui.stampIdx`**（落地按真源 `export.py::build_record`，**以 `assets[].seq` 兜底**，**不得另立第三来源**）；**备选「`items[]` 加顶层 `idx`」本轮不采纳**（登记备查）。**④ 同步登记两条已实测的 def- 类事实（只登记，不重跑）**——**(a) E6 头值编码**：`x-feicui-img-path` 的原实现直接回吐 DB 原值 ⇒ starlette 编码头值抛 `UnicodeEncodeError` ⇒ **E6 整条 500（含中文书名的书取图全挂）**；现统一走 `_header_safe()`（§3.13 的 4 条判据**一字未改**）；**(b) E7 有效态过滤**：`?state=` 过滤口径**已按「有效态」定案**（与 `items[].state` **恒同出一处**，依据质检 D-1 的实测 FAIL / OBS-1），落位 **§3.10 v1.4 注**。**⑤ 数据现状读数（照磁盘实测，带时点）**——正式库 `stamps` 现 **89 行**（`id<=79` 的 79 行**三口径内容指纹与 `ops/prod_migrate_evidence.md` §2.3 逐字未变**；`id 80–89` 共 10 行为 **1c 阶段两轮真实解析新增**：`tmp.pdf` 1 行 + `秦汉印典 …ok.pdf` 9 行；**不属污染**），`jobs` **5 行**；落位 **§0.3 v1.4 注 ②**（并原位更正 §4.4 锚点行数）。**AC 计数仍 13 条**（本轮不改任何 AC 判据）；被取代的原句一律就地留痕「已被 v1.4 取代」）｜**v1.3**（2026-09-20｜Jing：按本文件 **§0.4 流程**一次性收口**阶段 1b-i（执行层）+ 1b-ii（E3/E4/E6/E7）**交回的全部规范缺口与 Zang 已裁定口径（**只写文档：本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未启停任何服务、未占端口**）——**① E7 入参补 `page` 并定「`page` 与 `cursor` 互斥（同给 ⇒ `400 BAD_PARAM`）」**（§3.1 E7 行 + **新增 §3.10**；依据＝真实事故：`page` 被框架静默丢弃 ⇒ `has_more` 恒真 ⇒ 客户端死循环）；**② 新增红线判据纪律：凡「数据未变」判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条；依据＝WAL 下 `yinpu.db` **文件** md5 在内容无变化时漂移 `254d3ff1…` → `56cbf7af…`）；**③ AC-03 点位定义钉定为 `done_pages / total_pages`**、`{25%, 50%}` 两点各 ≥1 次、允许 ±1 页容差但证据须写明实际百分比（§7 AC-03）；**④ worker 数口径对齐：§5.1 草案「默认 8」原位更正为 4**（与 AC-04 已钉的 `N=4` 一致，依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽）并留痕（§5.1 / §5.3 / §9-R4 收口）；**⑤ 池的进程形态定案＝独立进程**（池管理器用 `server/.venv`、worker 用 `feicui/venv`；**接口层不含业务真值**）——**AC-11 进程分离的形态依据**（§1.3 表 + §6.2）；**⑥ E7 排序键 `ORDER BY created_at, job_id` 与游标 URL-safe base64 定案**（§3.10）；**⑦ 响应头判据：`x-feicui-scope` 等含非 ASCII 书名时须百分号编码**，并写成**可机械判负**的判据（§3.13；依据＝原写法对中国书名**已真实发生 500**）；**⑧ E4 请求语义定案**（`batch_id` 非空 ⇒ 400、`dry_run=true` ⇒ 400、`book_code` 仅一致性校验、`selfcheck_ref` 口径、`counts` 映射登记；§3.11）；**⑨ E6 错误码定案**（`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`，HTTP 同 404；无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`，**不得**以 `application/octet-stream` 冒充；§3.5 v1.3 块）；**⑩ E3 records 形状与 AC-08 必填 11 项键路径冻结**（顶层平台字段名 + `assets[]` + `feicui` 子对象 + 顶层 `missing_required`；§3.12）；**⑪ `limit` 默认 50 / 上限 500 / 越界或非法 ⇒ 400**、`total` ＝该范围全量条数、`has_more == (next_cursor is not None)` **恒成立**（§3.10）；**⑫ G-e「同区间重解析行数 ≠ 库内行数」写为「待定性」挂账**——AC-01 幂等判据改「**键集合与内容不变**」，**「行数不变」不作判据**（§7 AC-01 + §2.4 + §9-R12）；**⑬ `REPORT_1b-i.md` §6 的 G-1～G-9 逐条判定「本轮已裁 / 仍待裁」并入账**（§3.10 / §5.2 / §5.4 / §7 / §9）；**⑭ 新增 §7.1 验收夹具纪律**（六条护栏 + 断言总数闸门 + 折叠计数 + 版本身份钉；依据＝54,347 行失控与「假绿」两起实测事故）；**⑮ §6.2 按磁盘实测原位更正 sid / directUrl 并登记「面板托管已落地」**（`ctrl/index.js` 实测含 `feicui-api` / `feicui-web` 两条）；**⑯ 平台侧报冲突一项**（§9.3 与 §3.8 对 `sourceBook` / `sourcePageNo` 的必填性不一致 ⇒ §9-R17，**不自行改平台口径**）。**AC 计数仍 13 条**（只改写 AC-01 / AC-03 / AC-08 / AC-10 的判据表述，未增减 AC）；**被取代的原句一律就地留痕「已被 v1.3 取代」**）｜**v1.2**（2026-09-20｜Jing：按本文件 **§0.4 流程**一次性收口阶段 1a 暴露的全部规范缺口与登记项（**只写文档，未动任何代码**）——**① 取图端点正式定契约并定编号 E6**（§3.1 表 + §3.5 全文），**并规定临时路径的收口规则**（原前端单方面假设的 `/api/jobs/{job_id}/stamps/{idx}/image` **已废止**）；**② 后端 8 条缺口 G-1～G-8 全部入账**——G-1 / G-2 错误响应体形状（**新增 §3.4**）、G-3（**AC-07 加书名 × 页区间过滤**，本版最重要）、G-4（**§2.1 表下注**：重跑不换 `job_id` 的真义＝审计锚，非游标容器）、G-5（`total_pages` 派生顺序，§3.1 表下注）、G-6（**非 PDF 以 `%PDF-` magic 为准**，§3.1 表下注）、G-7（**唯一约束落地形态＝唯一索引** `uq_stamps_pdf_page_idx`，§4.1 D-2）、G-8（**允许的额外端点**，**新增 §3.6**）；**③ 前端 5 条缺口全部入账**——G-1（E6，§3.5）、G-2（**新增 E7 `GET /api/jobs`** + 前端过渡形态，§3.1 / §3.8）、G-3（同 ②-G-1/G-2 的 §3.4）、G-4（`/api/health` 定性，§3.6）、G-5（**未实现端点＝`404`**，**新增 §3.7**）；**前端附注**（Vite dev 代理 503 **不属 API 错误码族**、「后端不可达」信号口径）**新增 §3.9**；**④ 登记项 R-1 按 §0.4 收口为正式口径**——§6.2 启动命令 / cwd 原位更正 + **新增 §6.5 解释器矩阵**（API＝`server/.venv`，13 行 freeze；worker＝`feicui/venv`）；**⑤ Neng 复核的 OBS-1 / OBS-2 原位更正**——**AC-11 判负形态列改取反式**（判据实质未改）、**§9-R6 / R7 的「`feicui/web` 不存在」作废**（该目录 **birth 2026-09-20 11:35:25** 已存在）；**⑥ 1c 代理口径按 Zang 原文照录入 §6.4**（`feicui/web` 侧 `base:'/feicui/'` + `hmr.clientPort:5195`；`shu/web` 侧 `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 14 条、AC-88 / AC-89 扫描面不变；生产须网关同构改写；四项验收判据）；**⑦ §0.3 两条现状读数按磁盘实测原位更正**（5195 已被占用 / `shu/web` 的 `/feicui` 代理已落地）。**AC 计数仍 13 条**（只改写 AC-07 / AC-11 的判据表述，未增减 AC）；**被取代的原句一律就地留痕「已被 v1.2 取代」**）｜**v1.1**（2026-09-20｜Jing：**v1.1**（2026-09-20｜Jing：按本文件 **§0.4 流程**修 **Neng 复检 7 项缺陷 D-1～D-7**——**D-1** E3/S-3 分页信封改为「**扩展自**平台 §3.1 信封 + 逐项列差异」（§3.1 表下注 / §3.2 S-3）；**D-2** §6.1 的 5196 口径改为「本文件与 `PORTS.md` v1.8 同轮新分配」（与 §6.3 拉齐）；**D-3** AC-12 改**可复算式**（测量点 / 样本量 / 阈值 / 判定式）并拆出「无 BLOB」独立子项；**D-4** AC-11 钉为**二值判定**；**D-5** AC-03 钉 X 值集 / AC-04 钉 `N=4`（**依据 2026-09-20 实测**）；**D-7** §9-R6/R7 证据句收敛。**并登记**：**8501 已按 Kevin 授权停止的收口（R2 / §1.4 / §0.3）**、**5164 `/feicui` dev 代理已定口径与落地时点（R1 / §6.4）**、**性能基线口径（§5.4，实测 / 推断分离）**。**被取代的原句一律就地留痕「已被 v1.1 取代」，未被取代的原文一律保留**，逐条见 §10）｜**v1.0**（2026-09-20｜Jing 建立） |
| 维护人 | **Jing**（制度 / 口径）。**实现属 Kong**：`feicui/**` 下任何 `.py` / 前端工程 / `index.js` 改动**一律不由 Jing 执行**。裁定人＝**Zang**（派单方）/**Kevin**（拍板方）。 |
| 范围 | `feicui/` 的目标形态、任务模型、API 契约形状、数据层演进、并发与资源、端口登记、验收判据、现状纪律、待裁清单。 |
| 本版硬约束（写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` 或数据文件**（Jing 只写本文档与 PORTS.md 登记行）；② **未改动 `shu/web/**`**（对外站 M1 已封版冻结，改它会作废另一角色的验收结论）；③ **未改动平台规范任何历史版本行**（`shu/docs/yinsuo-web.spec.md` 只在**追加**变更行时按 §0.4 流程处理）；④ **未 kill / 停 / 重启任何进程**、**未占用任何端口**（含 8501 上的 Streamlit 实例，见 §9-R2）；⑤ **PORTS.md 只加行 / 追加状态行**，未重写任何历史行。 |
| 本版硬约束（**v1.1**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / 数据文件 / `config/**` / `output/**` / `exports/**`**，亦**未动** `spike-ocr/**`、`qa-baseline/**`、`qa-recheck/**`（属其它角色已验收证据，改了就要重开验收）；② **未改动 `shu/web/**`**、`shu/mockups/**`、`shu/index.html`、`ctrl/index.js`；③ **未 kill / 停 / 重启任何进程、未占用任何端口**——**8501 的停止系 Kong 于 2026-09-20 10:57:50 按 Kevin 授权执行，非 Jing 动作**（§9-R2 收口）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.26 变更行**，**未改其任何历史行（§0.5 历史行 / 表头「最近修订」历史行 / 页脚历史叙述）**；⑤ **`PORTS.md` 只加行 / 追加状态行**。 |
| 本版硬约束（**v1.2**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**（本轮只写**本文件 + 平台规范 + `ctrl/PORTS.md`**，并各自留快照）；② **未改动 `shu/web/**` 任何代码文件**（含 `vite.config.js`——1c 的该文件改动**系 Kong 执行**，见 §6.4）；③ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 2026-09-20 12:00 运行中的 5195 / 5164 dev server **未受影响**）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.27 行**，**未改其任何历史行**；⑤ **`PORTS.md` 只加行 / 追加状态行**，并按**新采纳的快照纪律**先存 `ctrl/versions/PORTS.v1.9.md`（md5 `6d2eaa6a2dd784615d2e1011611733f8`）；⑥ **不写任何「本轮已实现」句**——凡涉实现侧的状态**一律写「已定、落地中（由 Kong 执行）」并自带时点戳**。 |
| 本版硬约束（**v1.3**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**（本轮只写**本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11**，三处均先存快照：`feicui/docs/versions/feicui.spec.v1.2.md`（md5 `6dbe0b3c915d7f8ed43576a00122dcf1`，521 行）、`shu/docs/versions/yinsuo-web.spec.v1.27.md`（md5 `a32215a4c5efedd069657be24b581933`，1624 行）、`ctrl/versions/PORTS.v1.10.md`（md5 `05f8fce4f075c14df918e6cc4cda7092`，173 行））；② **未改动 `shu/web/**` 任何代码文件**；③ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 **2026-09-20 13:08** 实测：**5195 / 5196 / 8501 均无监听**、5555 / 5164 照常监听，**未受影响**）；④ 平台规范（`shu/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.28 行**，**未改其任何历史行**（**AC-01 ～ AC-90 判据实质一字未改、AC 计数仍 90 条、§2.2 路由表仍 14 条**）；⑤ **`PORTS.md` 只加行 / 追加状态行**，并按制度 (e) 先存 `ctrl/versions/PORTS.v1.10.md`；⑥ **不写任何「本轮已实现」句**——凡涉实现侧的状态**一律写「已定、落地中（由 Kong 执行）」或按磁盘实测写读数并自带时点戳**。 |
| 本版硬约束（**v1.4**，写入时点 2026-09-20） | ① **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / .json` / 数据文件**（本轮只写**本文件 + 平台规范 v1.29 + `ctrl/PORTS.md` v1.12**，三处均先存快照：`feicui/docs/versions/feicui.spec.v1.3.md`（md5 `8a27ecb692a7a611f056b280fd7e0de4`，649 行）、`docs/versions/yinsuo-web.spec.v1.28.md`（md5 `1660ca9d40afa76e6cca15b45172b282`，1634 行）、`ctrl/versions/PORTS.v1.11.md`（md5 `ac47ab3fe5d4df67fba82ecc011823dd`，183 行）；② **未改动 `xiai/web/**`**（对外站 M1 已封版冻结，改它会作废另一角色的验收结论）；③ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 **2026-09-20 14:59**）；**工程改名（`shu` → `xiai`，2026-09-20 14:47）非 Jing 执行**，Jing 只做**路径口径的文档收口**（§0.3 v1.4 注）；④ 平台规范（`xiai/docs/yinsuo-web.spec.md`）**只按 §0.4 流程追加 v1.29 行**，**未改其任何历史行**（**AC-01 ～ AC-90 判据实质一字未改、AC 计数仍 90 条、§2.2 路由表仍 14 条**）；⑤ **`PORTS.md` 只加行 / 原位更正现行有效引用并逐处留痕**，并按制度 (e) 先存 `ctrl/versions/PORTS.v1.11.md`；⑥ **不写任何「本轮已实现」句**——凡涉实现侧的状态**一律按磁盘实测写读数并自带时点戳**。 |
| 本版硬约束（**v1.5**，写入时点 2026-09-20） | ① **只写文档**——本轮**只改本文件一处**（`feicui/docs/feicui.spec.md`），**未动平台规范**（`xiai/docs/yinsuo-web.spec.md`）、**未动 `xiai/docs/xiai.spec.md`**（玺爱侧由**另一单**按其自己的 §1.3 流程改）、**未动 `ctrl/PORTS.md`**；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**（§0.6 的实现读数**系只读实测**，**Jing 未写一个字节**）；③ **未改动** `xiai/web/**`、`xiai/src/**`、`xiai/index.html`、`xiai/README.md`、`xiai/package.json`、`xiai/vite.config.js`、`xiai/mockups/**`、`ctrl/index.js`、`ctrl/public/**`、`xiai/docs/xiai-plan.md`；④ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 **2026-09-20 15:55**，`lsof -nP -iTCP:5163 -sTCP:LISTEN` ＝ `node` PID **91247** 照常 LISTEN——**该进程系人类手动起的 dev server，全程未受本单影响**）；⑤ **不写任何「本轮已通过」类结论**——凡涉实现侧状态**一律区分「已落地（读数 + 时点 + 证据）」与「已定、落地中（由 Kong 执行）/（由 Neng 验收）」**，**不得**从派单转述；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.4.md`（md5 `9b246d25206c1a2353a056876733b088`、675 行 / 177,059 B，`cmp` 字节一致）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）。 |
| 本版硬约束（**v1.6**，写入时点 2026-09-20） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/docs/xiai.spec.md`（玺爱侧由其自己的 §1.3 流程**同轮**由 Jing 改）、`xiai/docs/yinsuo-web.spec.md`（平台规范）、`ctrl/PORTS.md`（同轮由 Jing 单独升 v1.14）；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**——**§3.14 / §5.5 的全部读数系「只读引用实现侧证据」**（`server/README.md` §12、`ops/kong_square_crop_evidence.md`、`ops/kong_square_crop_coldstart_raw.txt`、`ops/kong_square_crop_selftest_raw.txt`），**Jing 未复跑、未改一个字节**；③ **未改动** `xiai/src/**`、`xiai/web/**`、`xiai/feicui/server/**`、`xiai/feicui/web/**`、`xiai/feicui/ops/**`（只读引用）、`xiai/qa-recheck/**`（只读引用）、`ctrl/index.js`、`ctrl/public/**`、`xiai/docs/xiai-plan.md`；④ **未 kill / 停 / 重启任何进程、未占用任何端口**（核验时点 **2026-09-20 19:2x**；证据＝**同一轮 Jing 实测**，见 `ctrl/PORTS.md` v1.14 §2 末行：5163 / 5164 / 5195 / 5196 / 5555 照常 LISTEN、面板 **13/13 running**）；⑤ **不写任何「本轮已通过」类结论**——凡涉实现侧状态**一律区分「引证据文件（只读引用，Jing 未复跑）」与「已定、落地中（由 Kong 执行）/（由 Neng 验收）」**；**证据文件里自记的 `61/61 PASS` / `11/11 PASS` / `13 条断言` 等一律只引用、不背书**；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.5.md`（md5 `f7a46c3685b700d1fd959894f1f8d36f`、**737 行 / 194,914 B**，`cmp` 与改版前主文件**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版不改任何 AC 判据、AC 计数仍 13 条**（§3.14 / §5.5 均为**契约与口径登记**，**不各设 AC**——**新增 AC 的动议须走 §0.4**）。 |

| 本版硬约束（**v1.7**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/docs/xiai.spec.md`（玺爱侧由其自己的 §1.3 流程**同轮**改）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**——**§3.15 的全部读数系只读引用与口径登记**（**未复跑**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/yinpu.db`、`feicui/exports/**`、`xiai/src/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.6.md`（md5 `88c6df8150f31c4009892acdfc27401c`、**909 行 / 234,138 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 13 → 20**（新增 AC-14 〜 AC-20 共 7 条，走 §0.4）；**本版 R 计数 20 → 24**（新增 R21 〜 R24）。 |

| 本版硬约束（**v1.8**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/docs/xiai.spec.md`（**本版按 Kevin 2026-10-10 新裁定：批 2 由另一会话承接 ⇒ 本线已无 xiai 规范改动职责**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.json` / 数据文件**——**§3.15.10 与 AC-21 / AC-22 均为对外接口面口径冻结**（**未复跑**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/yinpu.db`、`feicui/exports/**`、`feicui/var/**`、`xiai/src/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.7.md`（md5 `cf59f8c76b1915b59dc5708894909acf`、**1032 行 / 257,941 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 20 → 22**（新增 AC-21 / AC-22 共 2 条，走 §0.4）；**本版 R 计数不变（仍 24 条，本版未新增待裁项）**。 |

| 本版硬约束（**v1.9**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/docs/xiai.spec.md`、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.15.2 v1.9 注与 AC-23 均为口径 / 布局冻结**（**未复跑**）；③ **未改动** `feicui/web/**`（**页签改名与 tabbar / 页眉布局的实现由 Kong 并行另一单负责**）、`feicui/server/**`、`feicui/yinpu.db`、`feicui/exports/**`、`feicui/var/**`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.8.md`（md5 `3ed4310223233cca78a355c2bb62cfd5`、**1080 行 / 270,552 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 22 → 23**（新增 AC-23 共 1 条，走 §0.4）；**本版 R 计数不变（仍 24 条，本版未新增待裁项）**。 |

| 本版硬约束（**v1.10**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/docs/xiai.spec.md`（**本版两条外部依赖归另一会话按其自己规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.15.11 与 AC-24 均为对外导出面口径冻结**（**未复跑**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/yinpu.db`、`feicui/exports/**`、`feicui/var/**`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.9.md`（md5 `3e73e508476f3f56ff714a70fee9322b`、**1091 行 / 280,116 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 23 → 24**（新增 AC-24 共 1 条，走 §0.4）；**本版 R 计数不变（仍 24 条，本版未新增待裁项）**。 |

| 本版硬约束（**v1.11**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；D-1 归 xiai 侧按其自己的规范流程）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.15.11 v1.11 升版注 / §3.15.12 关联面裁定 / AC-24 三态判据均为口径冻结**（**未复跑**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/yinpu.db`、`feicui/exports/**`（**尤其未动 `exports/person_20261010_01/relations.jsonl`**）、`feicui/var/**`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.10.md`（md5 `7eebeafec8137703c3edd0f574696d06`、**1167 行 / 297,420 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数不变（仍 24 条；AC-24 由 v1.10 的五子项改写为三态判据，走 §0.4）**；**本版 R 计数不变（仍 24 条，本版未新增待裁项；R22 / R24 为状态注记、保号留行）**。 |

| 本版硬约束（**v1.12**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ item 模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.16 全部与 AC-25 〜 AC-32 / AC-23 原位改写均为口径 / 契约 / 判据冻结**（**未复跑**；拆解件实测读数**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/ops/**`、`feicui/yinpu.db`、`feicui/exports/**`（**尤其未动 `exports/person_20261010_01/relations.jsonl`**）、`feicui/var/**`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **改版前先存快照**：`feicui/docs/versions/feicui.spec.v1.11.md`（md5 `7e7f75d9fd76bd9076df4534a1bd37a6`、**1208 行 / 313,554 B**，`cmp` 与本文件改版前**逐字节一致**）；**历史行逐字保留、只增不改**；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 24 → 32**（新增 AC-25 〜 AC-32 共 8 条 ＋ **AC-23 原位改写（页签集合 2 → 3）**，均走 §0.4）；**本版 R 计数 24 → 28**（新增 R25 〜 R28）。 |

| 本版硬约束（**v1.13**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.12.md`，md5 `b5581b7fd995e21f0f08a71676bbe8a2`、**1369 行 / 349,648 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ item 模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.16.6 原位改写 / §3.16.8 sidecar 随动 / AC-28 · AC-31 原位改写均为口径 / 契约 / 判据登记**（**未复跑**；拆解件 §10 实测读数**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**——**旧采集口径原文逐字保留并标「已被 v1.13 取代」**（**系原位改写、非「既有条款自动失效」**）；⑦ **凡「数据未变」类判据一律用内容指纹、禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数不变（仍 32 条，AC-01 〜 AC-32；本版只原位改写 AC-28 / AC-31，未新增、未删减 AC、未改编号）**；**本版 R 计数不变（仍 28 条，本版未新增待裁项）**。 |

| 本版硬约束（**v1.14**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.13.md`，md5 `5dfcb49edbeb8dc5587f371c6ffbf5be`、**1385 行 / 367,653 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ item 模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.16.3 Q5 契约登记 / §3.16.5 重建幂等口径 / AC-33 均为口径 / 契约 / 判据登记**（**只读引用 Kong 实现读数，未复跑、未改一个字节**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/ops/**`、`feicui/exports/**`（尤其**未动 `exports/item_import_item_20261010_01/**`**）、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 32 → 33**（新增 AC-33 共 1 条，走 §0.4）；**本版 R 计数不变（仍 28 条，本版未新增待裁项）**。 |

| 本版硬约束（**v1.15**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.14.md`，md5 `5651c5fd7cad6a88081f9a311a6b6745`、**1399 行 / 382,380 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ 印章模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.17 全部与 AC-34 〜 AC-46 / AC-23 原位改写均为口径 / 契约 / 判据登记**（**未复跑**；源契约与字段面实测读数**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 33 → 46**（新增 AC-34 〜 AC-46 共 13 条 ＋ **AC-23 原位改写（页签集合 3 → 4）**，均走 §0.4）；**本版 R 计数 28 → 32**（新增 R29 〜 R32）。 |
| 本版硬约束（**v1.16**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.15.md`，md5 `b542ff939c72c845201bee54244ec8b9`、**1585 行 / 434,875 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ 印章模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.17.6 ⑤ / §3.17.8 影像面追加 / AC-47 〜 AC-52 / §3.17.8 与 AC-40 的 `NaN_` ref 状态口径原位改写均为口径 / 契约 / 判据登记**（**未复跑**；Zang 实测读数与 `ops/seal-ingest/09_upscale_probe.json` **只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 46 → 52**（新增 AC-47 〜 AC-52 共 6 条，走 §0.4）；**本版 R 计数 32 → 33**（新增 R33）。 |
| 本版硬约束（**v1.17**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.16.md`，md5 `391ac0e3cd4295ee7106784b5b1dbdd5`、**1611 行 / 456,294 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**批 2 ＝ 印章模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.17.8 a-v1.16 块子因由二扩三 / `failed` 行原位改写 / §3.17.8 a-v1.17 追加块 / AC-47 · AC-48 原位改写 · 随动 / AC-53 新增 / §9 R33 子因随动均为口径 / 判据登记**（**未复跑**；Zang 影像台账终态 6765/6765 实测读数**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行；**原位改写 ＝ §3.17.8 a-v1.16 块子因行与 `failed` 行 ＋ §7 AC-47 / AC-48，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.16.md`**）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 52 → 53**（新增 AC-53 共 1 条 ＋ **AC-47 原位改写 / AC-48 随动**，均走 §0.4）；**本版 R 计数不变（仍 33 条；`bad_bytes` 属既有 `source_no_image` 分桶、其 xiai 侧去留恰为 R33 所问 ⇒ 不新增 R 行，理由逐字见 §9（v1.17）留痕）**。 |
| 本版硬约束（**v1.18**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.17.md`，md5 `4e33681c38a7a445ac39f9371998ad05`、**1625 行 / 472,273 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.17.8 ④ 逐张台账字段语义更正 / §3.17.5 成员 6 键面随动 / §3.17.3 S6 追加 / AC-41 · AC-50 · AC-51 原位改写 / AC-54 新增 / §9 R34 新增均为口径 / 契约 / 判据登记**（**未复跑**；Zang 对本包实物（`exports/seal_import_seal_20261010_01/`）的实测读数与 xiai `server/app/store.py` 只读引用**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行；**原位改写 ＝ §3.17.8 ④ 逐张台账字段语义行 ＋ §3.17.5 成员 6 ＋ §7 AC-41 / AC-50 / AC-51，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md`**）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 53 → 54**（新增 AC-54 共 1 条 ＋ **AC-41 / AC-50 / AC-51 原位改写**，均走 §0.4）；**本版 R 计数 33 → 34**（新增 R34）。 |
| 本版硬约束（**v1.19**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.18.md`，md5 `142349f93f6c867213f875d073a20636`、**1640 行 / 491,387 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§7 AC-41 原位收窄 ＋ §3.17.8 a-v1.19 追加块（源侧 `ref_id` 未命中 person 库记账口径 ＋ `_db_path` 观察项）均为口径 / 契约 / 判据登记**（**未复跑**；Neng 独立质检 OBS-1 与 Zang 对本包实物（`exports/seal_import_seal_20261010_01/`）及三线端点的实测读数**只登记、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`（**尤其未动 Kong 并行改的 `server/app/seals.py` 与前端**）、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行；**原位改写 ＝ §7 AC-41，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md` §7**）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数不变（仍 54 条）／R 计数不变（仍 34 条）**（**AC-41 原位收窄，走 §0.4；未新增 AC；未新增 R——原拟 R35 已撤回，逐字理由见 §9（v1.19）**）。 |

| 本版硬约束（**v1.20**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.19.md`，md5 `814df2a5e6fda7d6dfa4ccbc36e974eb`、**1652 行 / 507,960 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`**；**关系模型 / 集合名 / 键面 / 导入通道归 xiai 线按其自己的规范流程**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.18 全部（含 §3.18.1 〜 §3.18.8）与 AC-55 〜 AC-61 / R35 〜 R39 均为口径 / 契约 / 判据登记**（**未复跑**；拆解件 `feicui/docs/relation-ingest-draft-v0.1.md` §1 / §2 的实测读数与 §3 的默认口径**只照登、未复核**）；③ **未改动** `feicui/web/**`、`feicui/server/**`（**尤其未动 Kong 并行改的 `server/app/relations.py` 与包**）、`feicui/ops/**`、`feicui/exports/**`（**尤其未动三线既有就绪包与 `exports/person_20261010_01/relations.jsonl`**）、`feicui/var/**`（**尤其未动 `var/person_ingest.db` / `var/item_ingest.db` / `var/seal_ingest.db`**）、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试、未 push**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数 54 → 61**（新增 AC-55 〜 AC-61 共 7 条，走 §0.4）；**本版 R 计数 34 → 39**（新增 R35 〜 R39 共 5 条）。 |

| 本版硬约束（**v1.21**，写入时点 2026-10-10） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.20.md`，md5 `e8911ed84db367bf0f0818e665f42cb1`、**1773 行 / 544,064 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未动 `xiai/feicui/server/**` 与 `web/**` 的实现**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**§3.19 全部与 AC-62 〜 AC-71 / R40 〜 R41 均为口径 / 契约 / 判据登记**（**未复跑**；本版引用的现状读数（`server/app/models.py::JobCreate.pdf_path` 口径、`server/app/multipart.py::parse_multipart(content_type, body: bytes)` 的「整体读进内存」形态、`inbox/` 目录磁盘不存在、`server/app/config.py::Settings` 字段形态）**系只读引用 / 只读实测**）；③ **未改动** `feicui/web/**`（**尤其未动 Kong 并行改的 `server/app/routers/jobs.py` / `server/app/config.py` / `server/app/main.py` / `JobsPage.vue`**）、`feicui/server/**`、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试、未 push**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行；**本版无任何原位改写 / 原位收窄 / 原位更正**——全部属「只增行」）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据；**E8 的 mtime 不变属文件级幂等判据、非库文件判据**）；⑧ **本版 AC 计数 61 → 71**（新增 AC-62 〜 AC-71 共 10 条，走 §0.4）；**本版 R 计数 39 → 41**（新增 R40 〜 R41 共 2 条）。 |

| 本版硬约束（**v1.22**，写入时点 2026-10-11） | ① **只写文档、只改本文件一处**（`feicui/docs/feicui.spec.md`，先存快照 `feicui/docs/versions/feicui.spec.v1.21.md`，md5 `2433b3596752be768fa47da1d3001758`、**1892 行 / 583,553 B**，`cmp` 与本文件改版前**逐字节一致**）——**未动** `xiai/**`（尤其**未动 Kong 并行改的 `server/app/config.py` / `server/app/routers/jobs.py` 实现**）、平台规范（`xiai/docs/yinsuo-web.spec.md` / `xiai/docs/yinyuan-web.spec.md`）、`ctrl/PORTS.md`；② **未改动 `feicui/**` 任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件**——**本版全部为口径 / 契约的文字同步与待裁项结案**（**未新增、未改写任何判据**；§3.19.2 已明写「**改数值不需升规范**」；上限默认值、`config.UPLOAD_MAX_BYTES_DEFAULT` 与两本 PDF 读数**系只读引用 / 只读实测**）；③ **未改动** `feicui/web/**`（**尤其未动 Kong 并行改的 `server/app/config.py` / `server/app/routers/jobs.py` / `JobsPage.vue` 与前端**）、`feicui/server/**`、`feicui/ops/**`、`feicui/exports/**`、`feicui/var/**`、`feicui/yinpu.db`、`xiai/**`、`ctrl/**`；④ **未 kill / 停 / 重启任何进程、未占用任何端口、未起服务、未跑构建 / 测试、未 push**；⑤ **不写任何「本轮已实现」句**——凡涉实现侧状态**一律写「已定、落地中（由 Kong 执行）」**并自带时点戳；⑥ **历史行逐字保留、只增不改**（表头「版本」行 / 「本版硬约束」行 / §10 变更记录历史行；**本版的原位改写 ＝ §3.4 表 `413` 行、§3.19.2 单文件上限行、§3.19.7 待裁行、§7 AC-65 的「默认 512 MiB」措辞 ＋ §9 R40 行结案**——**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.21.md` 与本节各留痕**）；⑦ **凡「数据未变」类判据一律用内容指纹，禁用数据库文件 md5**（§8 第 6 条，本版未引入任何库文件 md5 判据）；⑧ **本版 AC 计数不变（仍 71 条）／R 计数不变（仍 41 条）**（**AC-65 仅措辞同步、判据逻辑未改；R40 结案保号留行；R41 仍挂起；未新立 R42（理由逐字见 §9（v1.22））**）。 |

---

## 0. 文档约定

### 0.1 与其他文档的关系（防混淆）

| 文档 | 角色 | 与本文件的关系 |
| --- | --- | --- |
| `shu/docs/yinsuo-web.spec.md` | **平台侧规范**（印索 Web / 数据模型 / 计费 / 汇入契约） | 本文件**只引用**其 §9（引「汇入契约」），**不改其任何一字**；平台侧需求变更**不回写**本文件，只同步引用点。 |
| `ctrl/PORTS.md` | **端口文档真源** | 本文件 §6 的数值与其**逐条一致**；不一致时**以 PORTS.md 为准**并当场修本文件。 |
| `ctrl/index.js` | **端口运行时真源** | `services` 表五要素为登记目标；落地由 **Kong** 执行（§6.3）。 |
| `feicui/README.md` | feicui 工程说明 | 工程实现细节（使用方式 / 历史版本）以 README 为准；**口径冲突时以本规范为准**。 |
| 本文件 | **feicui 侧规范** | 唯一。 |

### 0.2 现状读数的纪律（**硬约束**）

1. **一切「现状 / 实测 / 当前」类读数必须自带时点戳与证据来源**，格式：`核验时点 YYYY-MM-DD HH:MM（Asia/Shanghai）；证据＝<命令或文件路径>`。
2. **派单 / 聊天 / 口头转述与磁盘事实不一致时，一律以磁盘事实为准**；差异**就地登记**（本文件 §9 待裁清单或 §10 变更记录），**不得为迁就转述而编造原句**。
3. 本纪律与平台规范 **§0.2 / §0.4 第 8 条**同源（该条即「现状类段落以磁盘实测为准」，依据＝平台规范 §9.1 在 v1.23 及更早的六条事实错误全部源于转述）。

### 0.3 本文撰写时的磁盘事实基线（**本节即 §0.2 的实例**）

> **核验时点＝2026-09-20 10:38–10:45（Asia/Shanghai）**；核验人＝**Jing**。
> **统一证据来源**：① `wc -l feicui/{app,processor,export,selfcheck_export}.py`；② `feicui/venv/bin/python` 直连 `feicui/yinpu.db` 的 `sqlite_master` / `stamps` / `PRAGMA` 查询；③ `find feicui/output -name '*.webp'`、`du -sh`；④ `lsof -nP -iTCP -sTCP:LISTEN`、`nc -z 127.0.0.1 <port>`、`ps -o pid,ppid,pgid,lstart,command -p <pid>`；⑤ `sysctl -n hw.physicalcpu hw.logicalcpu hw.memsize`、`df -h /Users/kevin`；⑥ `feicui/f2_report.json`（Kong 侧 F2 报告，`generatedAt=2026-09-20T10:10:00+08:00`）。

| 项 | 实测读数（**核验时点 2026-09-20 10:38–10:45**） | 证据 |
| --- | --- | --- |
| 代码规模 | `app.py` **378** 行（Streamlit UI 层）／`processor.py` **517** 行（解析逻辑）／`export.py` **1270** 行／`selfcheck_export.py` **398** 行 | `wc -l` |
| UI 现状 | **Streamlit**（`app.py` 第 1 行 `import streamlit as st`） | `grep -n '^import' app.py` |
| 主表 `stamps` | **79 行 / 10 列**（`id` `pdf_name` `page` `idx` `text` `img_path` `x1` `y1` `x2` `y2`） | 直连 DB 查询 |
| 分书条数 | `tmp.pdf` **30** ／`古玺汇编 文物出版社 罗福颐  ok.pdf` **23** ／`秦汉印典 上海书画 金怀英  1997 ok.pdf` **26**（合计 79） | `select pdf_name,count(*) from stamps group by pdf_name` |
| `text` 非空 | **2 / 79** | `select count(*) from stamps where text is not null and trim(text)<>''` |
| 影像缺失 | **0 / 79**（逐条 `os.path.exists(img_path)` 全命中） | 直连 DB 逐条 `os.path.exists` |
| `output/` 影像 | **49 个 `.webp`**，目录形态 `output/<书名>/…` + `output/pairs/pNN_i/…`；`du -sh output` ＝ **3.4 M** | `find` / `du` |
| 侧表 | **4 张**：`seals`(79) / `images`(79) / `export_batches`(12) / `export_records`(49) | `sqlite_master` |
| 库文件 | `yinpu.db` **576 K**；备份 `yinpu.db.bak-f2` **466944 B** | `du -sh` / `ls -l` |
| **无** WAL | `PRAGMA journal_mode` → **`delete`**（**非 WAL**） | 直连 DB `PRAGMA` |
| **无**索引 / 唯一约束 | `sqlite_master` 内的 index 仅 4 条 `sqlite_autoindex_*`（**全部属侧表**）；**`stamps` 上无任何索引、无唯一约束** | `sqlite_master` 查询 |
| 写库形态 | `process_pdf` **逐页** `sqlite3.connect("yinpu.db")` → `commit()` → `close()`（**每页一次**，非批量事务） | `grep -n 'connect(\|commit()\|close()' processor.py` → 行 **432 / 440 / 441** |
| OCR 实例 | **全局单例**：`_get_ocr()` 用 `global _ocr_instance` 缓存（`processor.py` 行 **20–23**） | `grep -n '_get_ocr\|global ' processor.py` |
| PaddleOCR 单实例开销 | **init ≈ 1.8 s；常驻 RSS ≈ 0.70 GB；峰值 RSS ≈ 0.81 GB**（PP-OCRv6_medium_det + rec） | 本人实测：`./venv/bin/python -c "from paddleocr import PaddleOCR; …"`（`ru_maxrss` 与 `ps -o rss` 双读） |
| 单页渲染 | 古玺汇编 **544** 页、400 dpi 渲染 2106×3160 px、单页渲染 **66 ms**（沿用派单已核基线，本文件不重测） | 派单基线（Jing 未独立复测，**如实标注**） |
| 解析吞吐 | `process_pdf` 实测 **2 页 = 8.8 s** ⇒ 544 页 ≈ **40 min**／132 页 ≈ **10 min**／807 页 ≈ **59 min**（**单进程串行**） | `feicui/f2_report.json` → `3_ocr_feasibility.cost_estimate` |
| OCR 可用性 | **印面（篆书）直 OCR 不可用**：4 个印面样本 3 个 `max_score=0.0` 无字、1 个仅 2 字（0.23）；**边款 / 整页影像可用**（`max_score=0.9989`，41 框） | `feicui/f2_report.json` → `3_ocr_feasibility.verdict` |
| OCR 空释文机械根因 | `processor.ocr_text()` 以 `getattr(item,'rec_texts')` 读 PaddleOCR 3.x 的 `OCRResult`，该对象**无此属性**（字段在 `.json['res']` 下）⇒ 任何输入恒返回 `''`（**已由 Kong 最小修复**） | `feicui/f2_report.json` → `3_ocr_feasibility.root_cause_found` |
| 机器资源 | **10 物理核 / 10 逻辑核 / 16 GB RAM / 可用磁盘 169 GB（使用 60%）** | `sysctl` / `df -h` |
| 端口现况 | **5195 空闲**、**5196 空闲**、**5200 / 5201 / 5202 空闲**；**8501 空闲**（**v1.1 原位更正**：核验时点 2026-09-20 11:29，`lsof -nP -iTCP:8501 -sTCP:LISTEN` **无监听**；原记「**8501 被占**（见 §9-R2）」**已被 v1.1 取代**——存量实例已于 2026-09-20 10:57:50 按 Kevin 授权停止，见 §9-R2 收口注）（**v1.2 原位更正 + 留痕**：核验时点 **2026-09-20 12:00**——**5195 已被占用**（`node` PID **1329**，`TCP 127.0.0.1:5195 (LISTEN)`）、**5196 仍空闲**、**8501 仍空闲**；本行原记「**5195 空闲**」**已被 v1.2 取代**——成因＝**feicui 前端 dev server（阶段 1a 产物）已起**，**非端口纪律问题**（§7 AC-13 照常适用））（**v1.3 原位更正 + 留痕**：核验时点 **2026-09-20 13:08**——**5195 / 5196 / 8501 均无监听**（阶段 1a 的前端 dev server 与 1b 的接口层**当前均未运行**）；**本行 v1.2 的「5195 已被占用」属 12:00 时点读数、现已漂移**，**原句保留、不改写**；另：`ctrl/index.js` **已含 feicui 两条托管条目**，见 §6.2 / §9-R6） | `lsof -nP -iTCP:<p> -sTCP:LISTEN` + `nc -z 127.0.0.1 <p>` |
| 已有前端**无** `/feicui` 代理 | `shu/web/vite.config.js` 内 `grep -n proxy` **零命中**（核验时点 2026-09-20 10:38；**v1.1 复核 2026-09-20 11:29 仍零命中**——落地时点＝feicui 前端骨架起来那一刻，见 §6.4）（**v1.2 原位更正 + 留痕**：核验时点 **2026-09-20 12:01**——`shu/web/vite.config.js` 内 **4 处 `proxy` 命中**（`server.proxy` / `preview.proxy` **各含** `'/feicui'`，**第 48 / 53 行**）⇒ **1c 已落地**；原「**零命中 / 该代理目前不存在**」**已被 v1.2 取代**；口径与验收判据见 **§6.4**；**Jing 未改 `shu/web/**` 任何文件**（改动系 Kong 执行）） | `grep` |

> **§0.3 v1.4 注 —— 路径迁移（工程改名 `shu` → `xiai`）+ 可复跑判据 + 数据现状刷新**（核验时点 **2026-09-20 14:47–14:59**；核验人＝Jing）：
> ① **路径已变（关键，先读）**：**2026-09-20 14:47**，整个 `shu` 工程被改名为 **`/Users/kevin/bistro/xiai/`**（`~/bistro/shu/` 只剩**空 `.vite` 壳、零文件**；实测：`find /Users/kevin/bistro/shu -type f` ＝ **0**、`find /Users/kevin/bistro/xiai -type f` ＝ **33,596**）。**本文件内所有以 `/Users/kevin/bistro/shu/...` 起头的现行有效引用一律原位更正为 `/Users/kevin/bistro/xiai/...`**，逐处留痕「**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**」；**以 `shu/` 起头的相对形态引用**（例 `shu/web/**`、`shu/docs/**`、`shu/feicui/**`）**同样读作 `xiai/...`**。**可复跑判据**：`ls -d /Users/kevin/bistro/shu/feicui/yinpu.db` ⇒ **`No such file or directory`**；`ls -d /Users/kevin/bistro/xiai/feicui/yinpu.db` ⇒ **命中**。**改名动作非 Jing 执行**（Jing 只收口文档口径）。
> ② **数据现状刷新（照磁盘实测写，带时点）**：正式库 `stamps` **现 89 行**（核验时点 **2026-09-20 14:59**；证据＝`server/.venv/bin/python` 以 `mode=ro` 直连 `xiai/feicui/yinpu.db`）。**其中 `id<=79` 的 79 行三口径内容指纹与 `ops/prod_migrate_evidence.md` §2.3 逐字未变**（A raw `8a21e57d5bd909fff282214640457c7f` / B canon `d7abe995bff62761c27052dfc2bdf7bb` / C free `22bdc0a794382b6e6dab7855aaee456f`）；**`id 80–89` 的 10 行为 1c 阶段两轮真实解析新增**（`tmp.pdf` **1** 行 + `秦汉印典 上海书画 金怀英  1997 ok.pdf` **9** 行）——**属增量，不是「污染」**。**全表（89 行）三口径指纹**：A `5fcbd5afe43d79ae726d64cb6361ecc3` / B `d3932fdcd5e1f1482d115b735e8fb1bb` / C `401e520c6d9f1e99b75cdbe3291d7ecb`。**逐书计数**：`tmp.pdf` **31** / `秦汉印典 …ok.pdf` **35** / `古玺汇编 …ok.pdf` **23**（合计 89）。**`jobs` 表 5 行**（全部 `DONE`）。**红线判据一律用内容指纹、禁用库文件 md5**（§8 第 6 条）。
> ③ **上表（L40–L62）的其余读数**的核验时点仍为 **2026-09-20 10:38–10:45**，**本轮未重测、如实标注**；**唯 `stamps` 行数一项已由本注按 89 行刷新**（表内「79 行」系 10:45 时点读数，**按「历史读数只增不改」保留原文**）；**§4.4 的锚点行数已按本节原位更正并留痕**。

### 0.4 变更流程（本文件）

1. **提出**（Zang 派单 / Kevin 拍板 / Jing 自检发现）；
2. 若属未决，先登记 **§9 待裁清单**；
3. 裁定（Zang / Kevin）；
4. **升版本号**并在 **§10 变更记录**新增一行（**历史行原文保留、不重写**，数值性事实可原位替换并注明「已被 vX.Y 取代」）；
5. 同步受影响的小节与 **§6 端口登记**（端口变更须同时改 PORTS.md，见 PORTS.md §1(b)）。

### 0.5 产品展示与数据方向口径（**v1.5 新增**｜Kevin 2026-09-20 追加；**可判负**）

> **来源**：Kevin **2026-09-20** 追加的两条口径（**V-1** / **V-2**）。**V-2 为最高优先的方向性条款**。本节与 `xiai/docs/xiai.spec.md`（玺爱侧规范）的相关条款**逐字同源**；两文件不一致时，**V-2 方向以玺爱侧规范为准**（玺爱是数据归宿），**V-1（斐萃自身的展示名与配色）以本节为准**。

#### 0.5.1 V-2 · 数据结构以玺爱为主（**★ 新增条款，不是「既有条款被改写」**）

> **留痕（必须逐字保留，防失真）**：**本文件改版前不存在任何数据方向条款**——核验时点 **2026-09-20 15:55**，证据＝`grep -n '对齐斐萃\|以斐萃\|数据模型\|canonical\|玺爱' feicui/docs/feicui.spec.md` **零命中**（本文件原文既**未写过**「数据模型对齐斐萃」，也**未写过**任何反向表述）⇒ **本小节属「新增条款」**。**任何把本小节说成「既有条款方向反转」的叙述都是失真的**（该失真形式在本工作台已发生过）；**唯一被取代的同类表述在玺爱侧规范**（`xiai/docs/xiai.spec.md` §3.5 / §4：原「数据模型对齐斐萃」**已由该文件 v1.1 取代**——**本文件不改、不引其历史行**）。

**核心句（与玺爱侧规范逐字同源）**：**数据结构以玺爱为主**；斐萃（feicui）**此前的库结构并不完善，后者向前者靠**。**玺爱定义 canonical schema**；**斐萃是待改造的入库管线**；**玺爱是数据归宿**（Zang 裁定 R-7：以后斐萃的数据均存入玺爱的数据库）。

**斐萃既有表的角色（只此一种）**：斐萃既有表 **`stamps` / `seals` / `images` / `export_batches` / `export_records` / `jobs`** 的字段**仅作为「斐萃旧结构 → 玺爱 canonical」的入库映射来源**（映射表见 `xiai/docs/xiai.spec.md` **§4.4**），**不得**反过来让玺爱迁就斐萃。

| # | 判负形态（机械可判） | 判定方式 |
| --- | --- | --- |
| ① | 以「斐萃旧库 / 既有列里没有这一项」为由**拒绝或推迟** canonical 侧所需字段的**斐萃侧补列 / 补产出** | 任何「先让玺爱去掉该字段 / 改结构，斐萃以后再说」的方案 |
| ② | 把**斐萃既有列集合**当作 canonical 的**建模目标**（例：以 `stamps` 的 10 列为字段上限） | 新增字段的**存在理由**写作「与斐萃现有列一致」 |
| ③ | 在斐萃侧规范 / 实现里，以「canonical 某字段与我们现有列不一致」为由**要求改 canonical 字段名 / 结构** | 出现「让玺爱把 X 改名成 Y（斐萃就是这么写的）」类改动请求 |
| ④ | **反向**要求玺爱侧改名 / 改结构以匹配斐萃旧列名（含「旧列名兜底即真源」） | 玺爱侧字段表出现「对齐斐萃某列」类存在理由 |

**本文件内的落地含义**：① 既有表**只许加法**（§1.2 I-3 不变），**不为 canonical 需要而 drop / rename**；② **补列 / 补产出是斐萃侧的义务**，不是「玺爱降级」的理由；③ **落地（补列与映射实现）属实现侧（Kong）**——**本文件不写任何「本轮已实现」结论**，一律记「**已定、落地中（由 Kong 执行）/（由 Neng 验收）**」。

#### 0.5.2 V-1 · 产品展示名与配色（**可判负**）

| 项 | 冻结口径 | 判负形态（命中即 FAIL） |
| --- | --- | --- |
| **展示名** | 斐萃页面产品展示名＝**【斐萃】**（全角方括号为文档写法，实际界面用「斐萃」二字） | 界面文案 / `document.title` / 页面标题 / 品牌位**再出现 `feicui` 作为展示名**（**路径与工程标识不算展示名**：`/feicui/` base、目录名、包名、sid、环境变量等**不在此列**） |
| **配色** | **蓝绿色的宝石感**（深青墨底 + 翡翠 / 青绿主色；宝石感＝低饱和深底 + 高亮度青绿主色与描边） | 出现**非蓝绿系**的产品主色（如纯灰黑无青、朱红 / 金 / 紫为主色调）**或**配色被实现自行变更而未走 §0.4 流程 |
| **token 唯一来源** | 色值**只允许**定义在 CSS 变量 token 源（本项目＝`feicui/web/src/styles/base.css` 的 `:root` 变量块）；**组件 / 页面引用 token，不写字面色值** | 组件内（含内联 `style`、`<style>` 块、`<template>`）出现字面色值（`#rgb` / `rgb()` / `hsl()` / 具名色）；**`currentColor` / `transparent` / `inherit` 等关键字不计** |
| **不得散落色值** | 同一语义的色**不得**在多个文件各写一遍 | 同一色值出现在 **≥2 个**非 token 源位置 |
| **非文本对比 ≥ 3:1** | 凡**承担信息传递**的图形元素（描边 / 图标 / 进度条 / 切片 / 边框 / 状态点）**对相邻背景**的非文本对比**不小于 3:1** | 任一承担信息传递的图形元素与其相邻背景对比 **< 3:1**（**须给出计算式与取值**，不接受「看起来清楚」） |
| **槽位 token 不跨用途复用** | 为某用途定义的 token（例「卡面描边」）**不得**被挪作他用（例「状态点填充」） | 同一 token 在**两类不同用途**的槽位被引用 |

> **与 AC 的关系**：本节为**口径条款**，**不新增 AC**（**§7 AC 计数仍 13 条**）。其验收证据面落在**结果页 / 任务台的人工可见性**与**视觉纪律的可机械判负项**上；**验收执行属 Neng**。**落地状态＝已定、落地中（由 Kong 执行）**；**本文件不写任何「本轮已通过」结论**。

### 0.6 本轮实现事实登记（**v1.5 新增**｜**只读实测，带时点戳**）

> **纪律**：本节**只登记磁盘读数**（§0.2 / §8），**区分「已落地（读数 + 时点 + 证据）」与「未落地 / 待裁」**；**不得**从派单 / 报告转述当实测。**核验人＝Jing**；**核验时点＝2026-09-20 15:55（Asia/Shanghai）**。**本节不含任何「本轮已通过」类结论**——**验收结论归 Neng**。

#### 0.6.1 已落地（磁盘实测）

| # | 事实 | 实测读数（核验时点 2026-09-20 15:55） | 证据 |
| --- | --- | --- | --- |
| ① | **产品展示名已改为【斐萃】** | `feicui/web/index.html` **第 6 行**＝`<title>斐萃｜印谱解析任务台</title>`（**原值**`feicui ｜ 印谱解析任务台` **引自本轮实现侧口径，Jing 未复核历史值**——历史值已不在盘上） | `grep -n '<title>' feicui/web/index.html` |
| ② | **配色已换为深青墨底 + 翡翠青绿主色（蓝绿宝石感）** | `feicui/web/src/styles/base.css`：`--bg: #0a1a1d`（**第 6 行**，深青墨底）、`--accent: #2fd6a0`（**第 17 行**，翡翠青绿主色）、`--accent-line: #43e6bd`（**第 19 行**，青绿描边 / 高光 token）；同批另有 `--bg-card: #0f2629` / `--bg-card-gem: #0e302b` / `--accent-deep: #15a97c` / `--accent-soft: #0f332e` / `--on-accent: #04191a`；色值**集中于该文件 `:root`**（token 源 = §0.5.2 所称的唯一定义处） | `grep -n -- '--bg\|--accent' feicui/web/src/styles/base.css` |
| ③ | **启动提示已改为实际口径** | `feicui/web/src/components/BackendBanner.vue` **第 28 行**＝`cd /Users/kevin/bistro/xiai/feicui/server && ./.venv/bin/python -m app.main`（**原值**`cd /Users/kevin/bistro/shu/feicui` 与 `./venv/bin/uvicorn app:app` **引自本轮实现侧口径，Jing 未复核历史值**） | `grep -n 'app.main\|uvicorn' feicui/web/src/components/BackendBanner.vue` |
| ④ | **前端构建在本轮报告里已绿** | **引本轮实现侧报告（Kong 侧）**；**Jing 未复跑**（**不得**据此写「本轮已通过」；复跑属实现 / 验收侧动作） | 实现侧报告（**未复核**） |

#### 0.6.2 未落地 / 待裁（**不得写成 Kevin 已拍**）

| 项 | 现状登记 | 口径来源 | 状态 |
| --- | --- | --- | --- |
| **副标题里去掉外露的端口号（`5195` / `5196`）** | **尚未落地**；**改版前本文件与实现侧均无该条改动留痕** | **Zang 裁定 / 派单口径，不是 Kevin 原话**（**不得**写成「Kevin 已拍」） | **「已定、落地情形待核」**——落地属「**已定、落地中（由 Kong 执行）**」；**落地情形以磁盘实测为准、本轮未复核** |

#### 0.6.3 未复核项（**如实标注，不得当成已验证**）

1. 上表 ①②③ 的**原值**（改写前取值）——**无法从磁盘复核**（已被本次改动覆盖），一律标注「引自本轮实现侧口径」。
2. ④ 的 `npm run build` 绿灯读数——**Jing 未复跑**。
3. `base.css` 内 `--on-accent` 注释自记的「**对 `--accent` 9.70**」对比度读数——**系实现侧注释所载，Jing 未复算**（§0.5.2 的 3:1 判据仍须由验收侧独立计算，**不得引用该注释充当通过证据**）。

---

## 1. 目标形态：Streamlit 退役 → 薄接口层 + 独立前端 + worker 池

### 1.1 目标形态（结构）

```
  浏览器
    │  HTTP
    ▼
  [Vue 前端站点]  feicui-web   :5195   ← 独立进程、独立生死、纯静态/纯前端
    │  HTTP (JSON)
    ▼
  [FastAPI 薄接口层]  feicui-api :5196  ← 只做：参数校验 / 入队 / 查进度 / 分页取数 / 触发导出
    │  任务队列（进程内队列或本地持久队列，形态由 Kong 定）
    ▼
  [worker 池]  N 个独立计算进程        ← 复用同一份 Python 解析库（processor 路径）
    │  写
    ▼
  SQLite(yinpu.db, WAL)  +  影像外置目录
```

**依据**：① **Kevin 已拍板方向＝三选一的 C**，原话「**如果换 FastAPI + Vue 不影响数据处理效率，那么选 C**」；② **Zang 已裁定「不影响」**——理由：**计算路径是同一份 Python 库（PyMuPDF / OpenCV / PaddleOCR / Pillow），UI 框架不在热路径**。故本节不再论证可行性，只定形态与不变量。

### 1.2 硬不变量（换 UI 不得动的东西）

| # | 不变量 | 依据 / 判负形态 |
| --- | --- | --- |
| I-1 | **解析与 OCR 仍是同一份 Python 实现**（`processor.py` 的渲染 / 检测 / OCR / bbox 口径） | Zang 裁定前提。判负：为「提速」改写检测阈值、坐标口径或 DPI 口径而未走 §0.4 变更流程。 |
| I-2 | **UI 框架不得进入热路径**（前端与接口层不得参与逐页像素运算） | 同上。判负：逐页图像处理出现在 FastAPI 进程内且与 worker 争 CPU。 |
| I-3 | **`stamps` 的既有语义字段不变**（`pdf_name` / `page` / `idx` / `text` / `img_path` / `x1y1x2y2`）；演进只允许**加列 / 加侧表** | 平台规范 §9.3 / §9.4 依赖这些字段的语义（bbox 单位、页号 1-based）。 |
| I-4 | **FEICUI 侧不得改平台规范的任何一字**；跨界字段口径以平台规范 §9 为**唯一真源** | 本文 §3.4 引用纪律。 |
| **I-5**（**v1.5 新增**） | **数据方向不得反向**：**数据结构以玺爱为主**（canonical 由玺爱定义），**斐萃向前者靠**；斐萃既有表（`stamps` / `seals` / `images` / `export_batches` / `export_records` / `jobs`）的字段**只作「斐萃旧结构 → 玺爱 canonical」的入库映射来源** | **V-2（Kevin 2026-09-20，最高优先）**，完整条款与 4 条判负形态见 **§0.5.1**。**判负**：以「斐萃旧库没有这一项」为由拒绝 / 推迟斐萃侧补列或补产出；把斐萃既有列集合当作建模目标；要求改 canonical 字段名 / 结构以迁就旧列。**本行系新增**（改版前本文件无任何数据方向条款，§0.5.1 留痕）。 |

### 1.3 进程分离口径（计算进程与 UI 进程各自生死）

| 角色 | 独立进程 | 生死口径 |
| --- | --- | --- |
| 前端（5195） | ✅ | 死掉**只影响可视**，**不得**中断任何已入队的 job。 |
| 接口层（5196） | ✅ | 重启**不得**丢 job 列表与进度（进度以**库 / 持久队列**为准，不以内存为准）。 |
| worker（N 个） | ✅ | 单个 worker 崩溃 ⇒ **该 job 停在其页级游标**，可**续跑**（§2.3），**不得**产生半条记录或孤儿影像。 |
| OCR 运行时 | 随 worker | 见 §5.2（**每 worker 一实例**，不再全局单例）。 |
| **池管理器（`feicui-pool`）** | ✅（**v1.3 定案**：**独立常驻进程**、**无端口**、**不是接口层的子进程**） | 由运维 / 脚本拉起（`cd feicui/server && ./.venv/bin/python -m app.pool --workers 4`）；**池管理器用 `server/.venv/bin/python`、worker 用 `feicui/venv/bin/python`**（§6.5 解释器矩阵）；**池是唯一写者**（WAL 单写者落地的承载者，§4.3）。**依据（实测）**：AC-11 的「kill 接口层后 worker 继续推进 cursor」**只在「池为独立进程」这一形态下成立**——若改为「接口层拉起池」，则 **AC-11 与该形态互斥**；1b-i 自测 ⑤ 已用 SIGKILL 5196 反证（`REPORT_1b-i.md` §2.1）。**判负**：池出现在接口层的进程树内（接口层死 ⇒ 池死）。 |

**判据（可判负）**：见 §7 **AC-11**。

### 1.4 Streamlit 退役边界（**只定边界，不定时点**）

- **退役对象**：`app.py`（378 行，Streamlit UI 层）与其依赖的 Streamlit 运行方式。
- **退役后不得**：`feicui` 主入口再依赖 8501（改由 **5195** 承担，见 §6.1）。
- **8501 上的存量实例**：**（v1.1 收口）已停**——该实例（`Python -m streamlit run app.py --server.port 8501`，PID **71267**、PGID 71267、PPID 1 孤儿）**已于 2026-09-20 10:57:50 由 Kong 按 Kevin 授权、以进程组 `TERM` 停止**（1 秒内释放、**未用 `KILL`**、无邻接误伤；**证据**＝`feicui/ops/8501_stop_evidence.md` + `feicui/ops/8501_stop_before_after.txt`）；**8501 现已空闲**（§0.3 端口现况行已同步）。**原句「属处置中事项——本文件不写状态定论」已被 v1.1 取代**；**Jing 本人始终未 kill / 未停 / 未重启任何进程**。详见 **§9-R2** 收口注。
- **`requirements.txt` / venv 的清理**属实现侧动作（Kong）；本文件只登记目标：**退役完成时 `streamlit` 不得再是 feicui 的运行依赖**（判据：`requirements.txt` 无 `streamlit`，且 venv 内不再需要它）。

---

## 2. 任务模型

### 2.1 粒度

| 层级 | 单位 | 说明 |
| --- | --- | --- |
| **job** | **一本书 = 一个 job** | 一本书 = 一个 `job_id`（可重跑，重跑**不换 `job_id` 语义**，见 §2.4）。 |
| chunk | job 内的**页区间** | 一本书的页区间切若干 chunk（切法见 §5.3），chunk 为**并行单位**与**断点单位**。 |
| 记录 | 一页内一个印面（`idx`） | 落 `stamps` 一行（语义不变）。 |

**表下注（v1.2 收口｜G-4：「重跑不换 `job_id` 语义」的正解）**：`job_id` 是**审计锚**，**不是**可复用的游标容器。语义固定为五条——① **同一本书的历史 job 记录一律保留**（旧行不删、不重置，其 `job_pages` 保持终态），**重跑＝新 job**；② **`pdf_path` 存在活跃 job（`ACTIVE = {QUEUED, RUNNING, PAUSED}`）⇒ 一律 `409`**（**不看 `rerun`**，§3.1 E1；`409` 体形状见 §3.4）；③ **终态**（`DONE` / `FAILED_PARTIAL`）**不算活跃** ⇒ 允许再次入队，**得新 `job_id`**；④ **不得**复用 / 重置旧 `job_id` 的页游标（这会让 §2.3 的断点锚与 §7 AC-03「断点之前的页不被重写」**失去唯一锚**）；⑤ 任务模型不变（**1 书 = 1 job**）——「不换 `job_id`」的正确读法是「**同一本书的 job 身份由 `pdf_path` 唯一确定**」，**不是**「重跑复用同一行」。
**依据 / 证据**：`feicui/server/README.md` §5「活跃 / 终态口径」（`ACTIVE` / `TERMINAL` 定义、`FAILED_PARTIAL` 不算活跃）+ `REPORT_1a.md` G-4（实测：同 `pdf_path` 第二次 ⇒ **409 + 既有 `job_id`**；`FAILED_PARTIAL` 后可再入队**新 `job_id`**、旧行保留作审计）。**留痕**：§2.1 表内「（可重跑，重跑**不换 `job_id` 语义**，见 §2.4）」一句**原文保留不改**，其**歧义由本注消解**（本注为 v1.2 收口口径）。

**依据**：① 规模口径＝Kevin 原话「**单书数千页 × 数千本书分次执行**」；② 平台规范 **§9.6**「**交付单位：一本书 = 一个批次（`batch_id`）**」——feicui 侧 job 粒度与之**同构**（1 job ↔ 1 批），避免汇入侧再切分。

### 2.2 job 状态机（口径，形态由 Kong 定）

`QUEUED → RUNNING → (PAUSED) → DONE`；异常分支 `FAILED_PARTIAL`（部分页失败、已成功页**不丢**）。

- **`FAILED_PARTIAL` 不得**被当作 `DONE` 上报（**假完成**判负，见 §7 AC-05）。
- 每个 job 必须有：`total_pages` / `done_pages` / `failed_pages[]`（可为空数组，**不得省略**）。

### 2.3 页级断点游标（可续跑）

- **游标粒度＝页**（chunk 完成时提交，见 §4.3）；**断点信息必须落盘**（库或持久队列），**不得只存内存**。
- **续跑语义**：重启后从**未完成页**继续；**已提交页不得重算重写**（重算可接受与否由 §7 AC-03 判定）。
- **崩溃窗口约束**：任意时刻 SIGKILL worker，**不得**留下「半页记录」（页内多印要么全落、要么全不落）。

### 2.4 同书重跑幂等（不得产生重复记录 / 重复影像）

| 层 | 幂等键（feicui 侧） | 行为 |
| --- | --- | --- |
| **记录行** | **`(pdf_name, page, idx)` 唯一** | 已存在 ⇒ **upsert 或跳过**；**不得新增行**。当前 DB **无该唯一约束**（§0.3 实测），属**本规范的落地要求**。 |
| **影像文件** | **内容 `sha256`** | 内容相同 ⇒ **不重写、不另存**；路径相同 ⇒ 覆盖须**内容一致的校验后**才允许（或写临时文件 + 原子替换）。 |
| **导出批次** | `batch_id` | 与平台规范 **§9.4**「同一 `batch_id` 重复汇入 → 幂等跳过（`skipped_count`）」**对齐**。 |

**表下注（v1.3 收口｜G-e 待定性的口径边界）**：行级幂等的作用面是「**同一 `(pdf_name,page,idx)` 键**」——**同键命中 ⇒ 不得改写既有行、不得新增行**（默认 `skipped`）；**未命中的新键**（该页解析出了原库没有的 `idx`）**允许新增行**。**故「重跑后行数不变」不是本节的语义**——行数是否相等取决于「解析是否稳定复现同一 `idx` 集合」，该问题**已作 §9-R12「待定性」挂账**（Zang 已另派质检定性）；**在定性前，幂等判据一律写成「键集合与内容不变」（§7 AC-01）**。

**与平台幂等键的关系（必须分清）**：feicui 侧行级幂等键是 `(pdf_name,page,idx)`（**落库不重复**）；平台侧幂等键是 **§9.4 的 `dedupe_key`**（**跨系统去重**）。**两者都要**，**不得互相替代**；平台键**必须**按 §9.4 的公式与 DPI 归一化前置计算（见 §3.4）。

---

## 3. API 契约草案（**只定形状与语义，不定实现**）

> 纪律：① 本文只定**形状 / 语义 / 状态码族**，**不定**具体框架内部结构、不定线程模型、不定序列化库；② **不得**因本节的形状设计与平台规范 §9 冲突——冲突时**以平台规范为准**并改本节。

### 3.1 端点一览（草案）

| # | 方法 / 路径 | 语义 | 请求要点（形状） | 响应要点（形状） |
| --- | --- | --- | --- | --- |
| E1 | `POST /api/jobs` | **建 job**（一本书 = 一个 job，入队） | `{pdf_path, page_range?:[from,to], chunk_size?, rerun?:bool}` | `201 {job_id, state, total_pages, created_at}`；相同 `pdf_path` 已存在活跃 job ⇒ **`409` + 既有 `job_id`**（**不得**静默起第二个同书 job） |
| E2 | `GET /api/jobs/{job_id}` | **查进度**（真实进度） | — | `{job_id, state, total_pages, done_pages, failed_pages[], cursor:{chunk_lo,chunk_hi}, counters:{detected,inserted,updated,skipped,ocr_empty}, started_at, updated_at}` |
| E3 | `GET /api/jobs/{job_id}/stamps` | **分页取结果** | `?page=&limit=&cursor=` | **分页信封（＝平台 §3.1 信封的「扩展形态」，v1.1 定性见本节表下注）**：`{items[], page, limit, total, has_more, next_cursor}`（**6 字段**；与平台 §3.1 的 **5 字段** `{items, total, page, pageSize, totalPages}` 的差异**逐项列在表下注**） |
| E4 | `POST /api/jobs/{job_id}/export` | **触发导出** | `{batch_id?, book_code?, dry_run?}` | `{batch_id, package_dir, counts:{formal,draft,rejected}, selfcheck_ref}`（**v1.3 定案**：响应**恰 4 字段**；`counts` 的**映射登记**见 §3.11；`batch_id` / `dry_run` / `book_code` 的请求语义与 `selfcheck_ref` 口径见 **§3.11**） |
| E5 | `GET /api/jobs/{job_id}/missing` | **缺失清单**（影像 / 释文） | `?kind=image\|text`（**v1.2 收口｜G-3**：E5 的口径＝**该 job 的书名 × 该 job 的页区间**——`pdf_name` 取该 job 的 `pdf_name`、`page ∈ [page_from, page_to]`，**不是全表口径**；`reason` 枚举＝`text_empty` / `file_missing` / `img_path_null`；实现**可另**以响应头 `x-feicui-scope` 暴露本次判定范围（**不进 JSON 体**，§3.2 S-3 形状不受影响；**该头含非 ASCII 书名时须按 §3.13 百分号编码**）；**判据见 §7 AC-06 / AC-07，两条已按本口径改写**） | `{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}` |
| **E6** | `GET /api/jobs/{job_id}/stamps/{page}/{idx}/image` | **取印面裁图（二进制）**（**v1.2 新增、正式编号**） | 路径参数：`{page}` **1-based**（↔ `stamps.page`）、`{idx}` **0-based**（↔ `stamps.idx`）；**无查询参数** | `200` **影像字节**（`Content-Type` ∈ {`image/webp`, `image/png`, `image/jpeg`}，**以文件实际类型为准**；`Content-Length` 必填；**不包 JSON 信封**）；`404`＝job 不存在 / `(page,idx)` 记录不存在 / `img_path` 缺失或文件不在盘上（**三类同码**）；`400`＝参数非法；`500`＝读盘 / 解码异常 / **影像类型不可判定**。**（v1.3 定案）**：三类 404 **同码、原因码分列**——`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`；**`img_path` 超出 `FEICUI_ROOT` 或为绝对路径 ⇒ `IMAGE_UNAVAILABLE`**；**无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`**（**不得**以 `application/octet-stream` 冒充）。**契约全文见 §3.5（含 v1.3 块）** |
| **E7** | `GET /api/jobs` | **列 job（分页）**（**v1.2 新增**；**归属 1b 落地**） | `?state=&page=&limit=&cursor=`（**v1.3 定案**：`page` **与** `cursor` **互斥**，同给 ⇒ **`400 BAD_PARAM`**；`page` 1-based、**越末页 ⇒ 空 `items` + `has_more=false`**、**绝不回吐第一页**） | **E3 同款 6 字段信封** `{items[], page, limit, total, has_more, next_cursor}`；`items[`job_id`, `pdf_name`, `pdf_path`, `state`, `total_pages`, `done_pages`, `failed_pages_count`, `created_at`, `updated_at`]`（**v1.3 冻结 9 字段**——原「**形状草案**，1b 落地时按 §0.4 回填」**已被 v1.3 取代**；已核平台规范 §9 与 §3.8，**不构成冲突**，详见 **§3.10**）。**口径与前端过渡形态见 §3.8** |
| **E8** | `POST /api/jobs/upload` | **拖曳上传 PDF（裸字节流式落盘；E1 的前置步骤）**（**v1.21 新增**） | **无 JSON 体**：请求体 ＝ **PDF 裸字节流**；`Content-Type` ∈ {`application/pdf`, `application/octet-stream`}；文件名走请求头 **`X-Filename`**（URL-encoded UTF-8；回退 `Content-Disposition` 的 `filename`；再回退 `upload.pdf`）；**无查询参数** | `201`（幂等复用 ⇒ `200`）`{pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}`——`pdf_path` **可直接交给 E1**；错误：`400 EMPTY_BODY` / `400 NOT_A_PDF` / `413 PAYLOAD_TOO_LARGE`（＋ §3.4 既有族）；**契约全文见 §3.19** |

**E5 的依据**：派单要求「**影像/释文缺失清单可查**」（§7 AC-06 / AC-07）；现状缺口的**规模已实测**：影像缺失 **0/79**、`text` 非空 **2/79**（§0.3）。

**E3 分页信封的定性（v1.1｜D-1 收口）**：**采「扩展自平台 §3.1 信封」口径，并逐项列出差异**（原 v1.0 §3.2 S-3 写「**与平台一致取向**」而**未列差异**，**该表述已被 v1.1 取代**）。

- **平台真值**（平台规范 **§3.1「分页信封」** / §8.2 契约形状②）：`{items, total, page, pageSize, totalPages}`——**5 字段**，约束对象是**平台适配层的分页型方法**（A13 `listUsageRecords` / A21 `listRechargeOrders` / A24 `listLedgerEntries` / A25 `listSeals`）。
- **feicui E3 形态**：`{items[], page, limit, total, has_more, next_cursor}`——**6 字段**。
- **差异逐项**：① **`limit` ↔ 平台 `pageSize`**（**同义不同名**：本文件用 `limit`、平台用 `pageSize`）；② **`has_more`＝feicui 新增**（平台信封无此字段，其值可由 `page` / `totalPages` 推得）；③ **`next_cursor`＝feicui 新增的游标分页字段**（平台信封为纯页码分页、**无游标**）；④ `items` / `total` / `page` 三项**与平台语义一致**（`items` 为实体数组、**不返回裸数组**；`page` 1-based）。
- **为什么选「扩展」而不是直接采用平台 5 字段（理由）**：**(a) 约束面不同**——平台 §3.1 信封约束的是**平台侧适配层方法**，而 **E3 是 feicui 内部端点**，不与平台消费者直接对接；本文件 §3 引言所称「不得与平台规范 §9 冲突」的跨界义务**落在 §3.3 的汇入契约（§9.3 / §9.4 / §9.6）**上，分页信封不在其中；**(b) 取数场景需要游标**——E3 取的是**单个 job 的页级顺序结果集**（§2.1 chunk / §2.3 页级游标），结果集会随 worker 推进而增长，**页码分页在结果追加时会错位 / 重复 / 漏行**，**游标分页**（`cursor` 入参 + `next_cursor` 出参）才稳定；**(c)** `limit` / `has_more` 便于前端做无限滚动与增量拉取。
- **纪律（本条为 D-1 的收口口径，不得回退）**：① **不得再声称「与平台口径一致」而不说明差异**——凡引用本信封处，一律以本注的**明确定义的 6 字段形态**为准；② 若将来 E3 **需被平台侧直接消费**，或需与平台适配层形态互换，**必须先按 §0.4 变更流程改本节**，或在适配边界做**显式字段映射**（`limit→pageSize`、由 `has_more` 合成 `totalPages`、按需丢弃 `next_cursor`），**不得默认两者可互换**。

**E1 的两项派生态口径（v1.2 收口｜G-5 / G-6）**：

- **`total_pages` 的来源（G-5）**：**派生顺序固定**——① 给了 `page_range` ⇒ 取**区间宽度**（`to - from + 1`，1-based 闭区间）；② 未给 ⇒ **读 PDF 页数**；③ **两者皆不可得 ⇒ `422`**（体含缺失清单 `missing: ["total_pages"]`，形状见 **§3.4**）。`total_pages` 是 **E1 时点快照**（＝该 job 落下的 `job_pages` 行数），**E2 一律复算、不读快照**（§3.2 S-1）。**`page_range` 不得改为必填**（单书全量入队不该逼人肉数页）；**读页数属接口层的派生态职责**——§1.2 I-2 只禁「UI 框架进热路径」，**不禁**接口层读 PDF 元数据；读页数**必须**用 **worker 侧解释器**（`feicui/venv/bin/python`）**子进程**完成，**不得**为读页数而把 PyMuPDF 装进 `server/.venv`（§6.5 解释器矩阵 / R-1）。
- **非 PDF 文件的判定（G-6）**：**必须以内容为准**——**`%PDF-` magic 校验**（文件**前 1024 字节内**出现 `%PDF-`）；**不得**只按扩展名分流。**依据（实测）**：PyMuPDF 按扩展名宽松分流——`.txt` 被当文档打开并报 **1 页**（⇒ 不做校验会把纯文本当 1 页 PDF 收下），`.bin` 抛 `FileDataError`（证据 `server/selftest/evidence/5B_pymupdf_lenient.txt`；`REPORT_1a.md` G-6）。**判定归属**：校验不过 ⇒ **`400`**（`error = NOT_A_PDF`，形状见 §3.4）；**扩展名非 `.pdf` 而内容确为 PDF ⇒ 允许**（以内容为准）。**落地状态**＝**已定、落地中（由 Kong 执行）**：**1a 未做**（Kong 侧已如实登记 G-6），**1b 补**；**落地前不得声称已校验**。
- **S-3 的「字段封闭」不外推（G-1 收口的口径前提）**：§3.2 **S-3 的「字段缺失 / 多出未定义字段即判负」只适用于 §3.1 已明确定义字段集的成功响应体**（E2 / E3 / E5 / E6 / E7 的 200 形态），**不外推到错误响应体**——错误体形状见 **§3.4**。**理由**：§3.1 E1 只写「`409` + 既有 `job_id`」而**未定字段集**，若把 S-3 外推到 409 体，则任何实现都**无法既「带上既有 `job_id`」又不「多出字段」**（规范自相矛盾，`REPORT_1a.md` G-1）。
- **E8 的边界（v1.21 新增）**：**E8 只落盘、不建 job**（无任何 SQL、不碰 `jobs` / `job_pages`），**是 E1 的前置步骤**（落盘 → 拿服务器侧路径 → 再调 E1）；**E1 的请求 / 响应 / `400` / `409` 契约一字未改**（见 §3.19.6 红线 ＋ AC-69）；**本端点不属 §3.6 的「允许的额外端点」**（那里限定 `/api/health` 与 `/api/meta/**`）——**E8 已在本表注册为契约端点**；**也不同于 §3.14 的「与 job 体系完全无关的纯函数式工具端点」**（E8 属 job 体系输入面，故取 E 号、不以§号登记；形态与口径见 §3.19 落位声明）。

---

### 3.2 语义纪律（可判负）

| # | 纪律 | 判负形态 |
| --- | --- | --- |
| S-1 | **进度必须真实**：E2 的 `done_pages` 必须是**已完成页的复算值**，不得由前端计时器 / 估算推进 | 进度与库内复算不一致（§7 AC-05） |
| S-2 | **不得假完成**：有 `failed_pages` 时 `state` **不得**为 `DONE` | `failed_pages` 非空而 `state=DONE`（§7 AC-05） |
| S-3 | **分页信封形状＝平台 §3.1 信封的扩展形态**（**v1.1 定性**；原 v1.0 表述「**分页信封形状与平台一致取向**…（引用平台规范 §3.1「分页信封」口径）」**已被 v1.1 取代**——原句声称一致而未列差异，属 D-1 缺陷）：**判负形态绑定到本节明确定义的 6 字段形态** `{items[], page, limit, total, has_more, next_cursor}`——`items`＝实体数组（**不返回裸数组**）、`page`＝1-based 页码、`limit`＝页长（↔ 平台 `pageSize`）、`total`＝全量条数、`has_more`＝布尔、`next_cursor`＝下一页游标（**无下一页时为 `null`**）。**与平台 §3.1 的 5 字段差异逐项见 §3.1 表下注**（`limit` ↔ `pageSize`；`has_more` / `next_cursor` 为 **feicui 侧新增**） | **字段缺失 / 多出未定义字段 / 字段名与本行形态不符即判负**；**且**：`has_more=false` 而 `next_cursor` 非 `null`（或反之）、`has_more` 与实际是否还有下一页不符、`items` 为裸数组（§7 AC-08 的分页响应样本即证据） |
| S-4 | **接口层不落业务真值**：E2/E3 的数据**以库为准**；接口层内存缓存**不得**成为唯一真源 | 重启接口层丢 job / 丢进度（§7 AC-11） |
| S-5 | **同书并发上限 1**：同一 `pdf_path` 同时只能有一个 `RUNNING` job | 同书两 job 并行写（§7 AC-01） |
| S-6 | **错误码族**：`400` 参数非法 / `404` 资源不存在 / `409` 冲突（同书重复起 job） / `422` 必填字段不可派生 / `500` 内部错误。**枚举三值即可，不多造**（**v1.2 补注**：S-6 只管**码族与语义**，**不定响应体**——各码的**响应体形状见 §3.4**；S-6 的五码枚举**一字未改**）（**v1.21 补注**：**码族由五码扩为六码**——新增 **`413 PAYLOAD_TOO_LARGE`**（承 §3.4 v1.21 / §3.19 E8）；**原五码（`400` / `404` / `409` / `422` / `500`）枚举原文逐字保留、未改写**；`413` **只用于 E8 单文件上传口**，**不得**外推到 E1 〜 E7 与 §3.14 工具端点（§3.14 的 `>32 MiB ⇒ 400 UPLOAD_TOO_LARGE` 属**另一个口**、**一字未改**）） | 出现未定义码族或语义倒挂 |

### 3.3 与平台侧汇入契约的对齐（**引用，不改平台规范一字**）

| 平台规范锚点 | 平台侧原文要点（**照录引用，不改**） | 本文件对其的**承接** |
| --- | --- | --- |
| **§9.3 必填 11 项** | 必填项＝上表第 **1 / 2 / 4 / 6 / 7 / 8 / 9 / 10 / 11 / 13 / 14** 行，即 `seal_name` / `dynasty` / `seal_type` / `asset_kind` / `source_book` / `source_page_no` / `seal_code` / `sha256` / `image_bytes`·`width`·`height`·`color_mode` / `review_status` / `batch_id`；「**必填项缺失即不得进入平台正式库**，只能作为 `review_status=DRAFT` 暂存」 | feicui 侧 E3 / E4 的**每条记录**必须能给出这 11 项（**缺失时**必须附带**可解释的缺失原因**，与 `feicui/exports/selfcheck_report.json` 的 `requiredCoverage` 口径一致）。**现状**：`seal_name` **2/79**、`seal_code` **0/79**、`seal_type` **全部 UNKNOWN 哨兵**（§0.3 与 `f2_report.json` `5_selfcheck_before_after`） |
| **§9.4 幂等键** | `dedupe_key = sha256(sourceBook + '\|' + sourcePageNo + '\|' + quantize(bbox, 1pt) + '\|' + assetKind)`；**且** `sealCode` 为业务唯一键（`UNIQUE`）；图片以 `sha256` 幂等；写入语义＝**upsert** | feicui 侧必须**可独立复算**该键；`bbox` 输入一律为 **pt** |
| **§9.4 DPI 归一化前置（v1.24 限定）** | `bbox` **须先按该书 `coord_dpi` 归一化为 pt**，**再**作 `quantize(·, 1pt)`；**不得**以像素原值直接量化 | feicui 侧 `stamps.x1y1x2y2` 为**像素**且 **DPI 逐书不同**（实测 古玺汇编 **400** / 秦汉印典 **144** / `tmp.pdf` **144**，证据 `feicui/config/book_geometry.json`）⇒ **归一化是硬前置**，已在 `seals.coord_dpi` / `bbox_unit='pt'` / `bbox_pt_*` 落列 |
| **§9.6 通道** | **首版：本地目录投递**（平台侧导入器读取）；后续可换对象存储 + 队列；**交付单位**＝一本书 = 一个批次（`batch_id`）；**回滚**＝按 `batch_id` 整批撤销；**校验清单** 6 项 | feicui 侧 E4 产物**首版仍走本地目录**（`feicui/exports/fb_…/`，实测 12 个批次目录）；**不得**在平台侧未开对象存储前改用远端通道 |

> **纪律（重复声明）**：上表**只是引用**。**平台规范一字不改**；若平台规范升版改了口径，**由平台侧按 §0.4 流程改**，feicui 侧按新口径**同步本表的引用点**（同步记录写入 §10）。

---

### 3.4 错误响应体形状（**v1.2 新增**｜G-1 / G-2 收口）

> **依据**：§3.1 E1 只写「`409` + 既有 `job_id`」而未定字段集（`REPORT_1a.md` **G-1**）；S-6 只枚举码族而未定义体（**G-2**）。**本节形状为**冻结口径**，实现侧既有形态已对齐**（`server/app/models.py::JobConflictResponse`）。

| 码 | 语义 | 响应体（**冻结**） | 判负形态 |
| --- | --- | --- | --- |
| **409** | 冲突：同 `pdf_path` 已有活跃 job（§3.1 E1 / §3.2 S-5） | `{error: "ACTIVE_JOB_EXISTS", job_id: "<既有活跃 job 的 id>", state, total_pages, created_at}`——**`job_id` 必填**，且**必须是既有活跃 job 的 id**；`detail` **可选**（人类可读说明） | 缺 `job_id`；或 `job_id` 指向新 job / 为空；或**静默起第二个同书 job**（与 §7 AC-01 同源） |
| **400** | 参数非法（`pdf_path` 不存在 / 非 PDF、`page_range` 越界或非法、`kind` 缺失或非法、`page` / `idx` 非法；**v1.21 随动：加 E8 的 `EMPTY_BODY`（空体）/ `NOT_A_PDF`（首字节非 `%PDF-`）/ `BAD_CONTENT_TYPE`（非白名单 Content-Type）/ 未白名单查询参数 / 清毒后越界**） | `{detail: <string 或 object>, error?: <机器码>}`——**必须**含 `detail`；**允许**含 `error`（机器可读码，**推荐**，例 `PDF_NOT_FOUND` / `NOT_A_PDF` / **`EMPTY_BODY`** / **`BAD_CONTENT_TYPE`**） | 无 `detail`；或 HTTP 码与语义倒挂（用 `200` 承载失败） |
| **413** | 请求体过大：**E8 单文件上传超上限**（**默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准**——**2026-10-11 起 ＝ 5 GiB（5368709120 B）**；**原写「默认 512 MiB」已被 v1.22 取代**；见 §3.19.2） | `{detail: <string>, error: "PAYLOAD_TOO_LARGE"}`——**必须**含 `detail`；**允许**额外字段（如 `limit_bytes`） | **先写满盘再报错**（须**边写边判**、超限即停并清理已写分片）；或 HTTP 码与语义倒挂（用 `400` / `200` 承载） |
| **404** | 资源不存在（未知 `job_id`；未注册的端点，见 §3.7） | 同上：**必须**含 `detail` | 用 `200` + 空对象 / 空数组冒充「没有」 |
| **422** | 必填字段不可派生（`total_pages` 既无 `page_range` 又读不出 PDF 页数） | `{detail: {...}}`，**且必须**给出**缺失项清单** `missing: ["total_pages"]`（可嵌于 `detail` 内） | 报 `422` 而**不说明缺哪一项** |
| **500** | 内部错误 | **必须**含 `detail`；**不得**回吐堆栈 / 绝对路径 / 库文件路径 | 吞异常返 `200`；或把内部路径写进响应体 |

**学科纪律（本节为 D-1/G-1 的收口口径，不得回退）**：
1. 上表**只约束错误体**；成功体的**字段封闭纪律**见 §3.2 **S-3**，**两者不得互相外推**（G-1 的规范自相矛盾的根源）。
2. **除 409 外，错误体允许额外字段**（如 `error` / `missing`）——**多出字段不判负**（明确豁免 S-3 的封闭校验）。
3. **任何错误不得以 `200` 承载**（假成功判负；与 §7 AC-05 同源）。
4. **前端对 409 的处置（v1.2 定）**：**原样展示原始 body**（JSON 美化或纯文本），并按本节口径取 **`body.job_id`** 生成跳转链接——**规范口径是 `body.job_id`**；`body.detail.job_id` / `body.existing_job_id` 之类**启发式探取不再是规范口径**，**仅可**作向后兼容兜底（`feicui/web/README.md` §4-G-3 的启发式范围**据此收窄**）。

**（v1.21 随动｜留痕）**：**本节码族由五码扩为六码**——**新增 `413 PAYLOAD_TOO_LARGE`**（**触发面恰为 E8 `POST /api/jobs/upload` 的单文件上限，见 §3.19**）；**`400` 行随动**（机器码示例补 `EMPTY_BODY` / `BAD_CONTENT_TYPE`）。**原五码（`400` / `404` / `409` / `422` / `500`）的语义与响应体形状一字未改**；**§3.2 S-6 五码枚举原文逐字保留、另加 v1.21 补注**；**`413` 不得外推到 E1 〜 E7 与 §3.14 工具端点**（§3.14 的 `UPLOAD_TOO_LARGE` 返 `400`、属**另一个口**，**不得互相引用 / 不得同值复用**）。

**（v1.22 随动｜留痕）**：**`413` 行内的上限默认值随 §3.19.2 同步**——原写「默认 **512 MiB**，`config` 层常量可改」，现同步为 **「默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准；2026-10-11 起 ＝ 5 GiB（5368709120 B）」**（**仅数值与措辞同步，码族、语义、响应体形状、判负形态一字未改**）；依据 ＝ Kevin 2026-10-11 裁定（**§9-R40 结案**）。

### 3.5 E6 取印面裁图契约（**v1.2 新增｜正式编号**）

> **背景（前端阶段 1a 缺口 G-1）**：结果页需展示裁图，而 v1.1 §3 的 E1–E5 **无取图端点**；前端曾**单方面假设**临时路径 `GET /api/jobs/{job_id}/stamps/{idx}/image`（`feicui/web/README.md` §4-G-1；代码集中于 `src/api/stampsImage.js`）。**本版正式定契约、定编号＝ E6**（端点行见 §3.1）。

| 项 | 口径 |
| --- | --- |
| **路径** | `GET /api/jobs/{job_id}/stamps/{page}/{idx}/image`（**带页段**） |
| **为什么必须带 `{page}`** | 行级唯一锚是 **`(pdf_name, page, idx)`**（§2.4）——**`idx` 单值在 job 内不唯一**（同一本书的每一页各自有 `idx = 0..n`）⇒ 只给 `{idx}` 的路径**无法唯一定位一行**，故**必须**带页段；`{page}` **1-based**、`{idx}` **0-based** |
| **入参纪律** | 只有 3 个路径参数、**无查询参数**；**不接受**任何「文件路径」类入参（防目录穿越） |
| **200** | **影像字节**——`Content-Type` ∈ {`image/webp`, `image/png`, `image/jpeg`}（**以文件实际类型为准**）、`Content-Length` 必填、**不包 JSON 信封**；**可选**响应头 `x-feicui-img-path`（DB 内**相对**路径，供对账，**不进体**） |
| **404** | 三类**同码**：① `job_id` 不存在；② 该 `(page, idx)` 在 `stamps` 内不存在；③ 记录存在但 `img_path` 为空**或文件不在盘上**（`os.path.exists` 为假） |
| **400 / 500** | `page` / `idx` 非法（非整数、`page < 1`、`idx < 0`）／读盘或解码异常（**不得吞**，见 §3.4 500 纪律） |
| **纪律** | ① **只读**：不得触发解析 / OCR / 写库（§1.2 I-2）、不得写缓存文件；② **不得**以占位图 / 空白图冒充真图——**无图 ⇒ `404`**（与 §7 AC-06 分工：**缺失清单负责说缺什么、取图端点不伪造**）；③ **不得**从库里读影像 BLOB（§4.1 D-4 ①）；④ 路径**必须**＝`FEICUI_ROOT` + DB 相对路径，并做**越界校验**（不得逃出 `feicui/`）；⑤ 响应 `Cache-Control: no-store`（dev 口径，避免干扰 §2.4 重跑幂等比对） |
| **与 AC 的关系** | E6 **不单列 AC**（AC 计数仍 **13 条**）；其证据面落在 **AC-06**（影像缺失清单）+ **结果页裁图的人工可见性**上。**落地状态＝已定、落地中（由 Kong 执行）**——**落地前不得声称「取图已实现」**；前端结果页仍按现状显示「裁图不可用：临时取图端点未实现（待规范收口）」 |
| **临时路径的收口规则（**必须执行**）** | ① **废止**前端临时路径 `/api/jobs/{job_id}/stamps/{idx}/image`（**2 段之 `idx` 形态**）——**自 v1.2 起它不是契约**；② **后端不得两套并存**：临时路径**不实现**，被调用时返 `404` 即可，**无需**兼容；③ **前端收口为「一处常量」**：改 `feicui/web/src/api/stampsImage.js`（该文件即为此目的集中常量与注释），**不得**在多处硬编码路径；④ **收口完成的证据（须落盘）**：结果页对一条**影像存在**的记录显示**真实裁图**（非占位），对一条**影像缺失**的记录显示「不可用」且**不显示占位图** |

**§3.5 表下 v1.3 块 —— E6 错误码定案（Zang 已裁定；**原文口径写死**）**：

| 情形 | HTTP | 原因码（**机器可读**） | 判负形态 |
| --- | --- | --- | --- |
| `job_id` 不存在 | **404** | `JOB_NOT_FOUND` | 与另两类混用同码却**不区分原因**（客户无法区分「job 没了」与「这一行没图」） |
| `(page, idx)` 记录不存在 | **404** | `STAMP_NOT_FOUND` | 同上 |
| 记录存在但**影像不可得**（含：`img_path` 为空 / 文件不在盘上 / **路径超出 `FEICUI_ROOT`** / **绝对路径**） | **404** | `IMAGE_UNAVAILABLE` | 用占位图 / 空白图冒充真图（**与 §7 AC-06 分工：缺失清单负责说缺什么、取图端点不伪造**） |
| **无法判定影像类型**（既非 webp / png / jpeg，也判不出来） | **500** | `IMAGE_TYPE_UNKNOWN` | **以 `application/octet-stream` 冒充**（把「不知道」装成「知道」）；或吞异常返 200 |
| `page` / `idx` 非法（非整数、`page < 1`、`idx < 0`、小数、URL 编码穿越） | **400** | （参数非法族，§3.4） | 返 200 + 空体 |

- **纪律**：① **HTTP 码同 404、原因码分三类**——「同码」是可判定性 / 安全性的要求（不因区分原因而泄漏存在性以外的信息），「原因码分列」是**可诊断性**的要求（**二者不矛盾**）；② **越界路径一律 `IMAGE_UNAVAILABLE`**（**不得**回吐路径 / 不得尝试读取）；③ **不得**用 `application/octet-stream` 掩盖「类型未知」。
- **依据（实测）**：`REPORT_1b-ii.md` §3.4(b)(c)（三类 404 同码实测；fixture 四例越界：逃出 root 的相对路径 / `/etc/passwd` / 空 `img_path` / 盘上不存在的相对路径）；**同轮 E6 的 200 形态**：`Content-Type` 取**文件实际类型**（实测 `image/png`）、`Content-Length` == 盘上字节数、字节与盘上文件 **sha256 相同**、**不包 JSON 信封**（首字节非 `{`）、`Cache-Control: no-store`、`x-feicui-img-path` == DB 内相对路径（**该头按 §3.13 须百分号编码**）。**Jing 未复跑**（引其证据）。
- **落地状态＝已落地（由 Kong 执行）**；**已废止的两段临时路径** `/stamps/{idx}/image` 需返 **404**（后端**不两套并存**，实测合规）。


### 3.6 允许的额外端点（**v1.2 新增**｜后端 G-8 收口）

- **结论：允许**。§3 定义的 E1–E7 是**最小契约集**，**不是**端点白名单。允许存在**非契约端点**，条件四条：① 路径前缀限于 **`/api/health`**（存活探针）或 **`/api/meta/**`**（元数据 / 运维**只读**视图）；② **不得**与 E1–E7 语义重叠或改名重复（不得出现第二个「建 job」路径）；③ **不得**被任何 AC 的判据依赖（**验收面只用 E1–E7**；`/api/health` 见下条）；④ 新增 / 删除须在 `feicui/server/README.md` 登记（本文件只在**类别**上约束）。
- **现状登记（判定＝合规、保留）**：`GET /api/health`（存活探针）、`GET /api/meta/migrations`（迁移记账只读视图）——来源 `server/README.md` §6 末段 / `REPORT_1a.md` G-8；**实测**（核验时点 2026-09-20 12:00，证据＝`server/app/main.py` 第 **56** / **84** 行）两个路由**均已注册**。
- **`/api/health` 与前端连通性判定（前端 G-4 收口）**：**允许**后端提供 `/api/health`，但 **前端不得把「该端点存在」当作契约或验收依据**（后端**可以不提供**，也可以改变其体形状）；前端 dev 下的连通性判定**仍走 dev server 自己的探针**（`/__feicui/backend-probe`，见 §3.9），并**必须容忍 404**。

### 3.7 「端点尚未实现」的状态码（**v1.2 新增**｜前端 G-5 收口）

- **规范口径＝`404`**（路由未注册）。**依据**：Kong 阶段 1a 实测 **E3 / E4 未注册 ⇒ `404`**（`REPORT_1a.md` §4 与自测附件⑦）。
- **前端宽容面（允许，但须登记）**：前端出于兼容**可**把 **`404` / `405` / `501`** 一并判为「后端尚未提供该接口」——**这是前端宽容处理、不是规范口径**；**不得**把「尚未提供」渲染成空表 / 0 条 / 占位数据（**假数据判负**）。
- **不得**用 `200` + 空 `items` 冒充「接口未实现」（与 §3.4 纪律 3 同源）。
- **落地后语义**：E3 / E4 / E7 落地后本条**仍然成立**（未知 `job_id` 同为 `404`）；区分办法＝响应体形状（框架产生的未注册路由响应须与 §3.4 的 `detail` 形状同形）。

### 3.8 job 列表端点 E7 与前端 G-2 的处置（**v1.2 新增**）

- **缺口（前端 G-2）**：v1.1 §3 只有 E1（建 job）、**无「列 job」**，而任务页需要列表。
  > **（v1.9 注）**：本行「**任务页**」**指任务台主页面**；其**页签文案已由 v1.9 改为【印谱解析】**（原【任务页】；见 **§3.15.2 v1.9 注**）。本行**原文逐字保留、不改写**。
- **口径**：**新增 E7 `GET /api/jobs`**（端点行见 §3.1），**归属 1b**（与 E3 / E4 同批）；返回 **E3 同款 6 字段信封**（§3.2 S-3），`items` 字段集见 §3.1 E7 行（**形状草案**，1b 落地时按 §0.4 回填）。**E7 不新增 AC**。
- **E7 落地前的前端行为（现状，允许）**：先试 `GET /api/jobs`；未提供 ⇒ 明确显示「后端尚未提供该接口」，并**另列**一份「**本浏览器本地记录（localStorage；来源＝本机 E1 的 201 响应）**」——**两栏分开、来源标注清楚**（`feicui/web/README.md` §4-G-2）；**该现状不得作为任何验收依据**（过渡形态）。
- **纪律**：本地记录**不得**与后端数据混排、**不得**冒充后端数据；E7 落地后**一律以 E7 为准**，本地记录仅作「本机建过哪些 job」的辅助显示。

### 3.9 Vite dev 代理层的 503 与「后端不可达」信号（**v1.2 新增**｜前端附注收口）

- **事实**：`feicui/web` 的 Vite dev server 在后端不可达时（`ECONNREFUSED`）由**代理 error 钩子**产生 `503 {error:"backend_unreachable"}`（`feicui/web/README.md` §3）。
- **定性（本版定案）**：该 `503` **不属于 feicui API 的错误码族**（§3.2 S-6 的 `400 / 404 / 409 / 422 / 500`）——它是 **dev 代理层**产生的信号，**不由后端实现、不进构建产物、生产无此路径**；**API 自身码族未改动**（S-6 原文一字未改）。
- **「后端不可达」信号口径：定义，但仅限 dev / 前端侧**——允许**两个**信号并存，且**必须同源**：① dev server 探针 `GET /__feicui/backend-probe`（前端自有中间件，返回 `{reachable, target, detail}`）；② 代理 error 钩子的 `503 {error:"backend_unreachable"}`。**纪律**：① 探针目标与代理目标**必须同源**（同一 `API_TARGET`，默认 `http://127.0.0.1:5196`），**不得**出现「代理指向 A、横幅显示 B」；② 二者**均不属**后端 API 契约（后端**不需要**实现 `backend-probe`）；③ 前端在「网络错误 / `503 backend_unreachable`」时**统一**显示「后端未启动」——**不得**用示例 / 估算 / 缓存值填充（与「无假数据」硬约束同源）；④ 该 `503` **不得**被任何 AC 引用为后端错误语义。

### 3.10 E7 定案：入参 / 互斥 / 排序键 / 游标编码 / items 字段集（**v1.3 新增**｜G-a ～ G-d + 1b-ii §1 缺陷收口）

> **依据**：`REPORT_1b-ii.md` §1（**E7 两处真缺陷**：① 路由/仓库层**根本没有 `page` 形参** ⇒ `?page=N` 被框架**静默丢弃**；② 游标分支把 keyset `WHERE` 与 `OFFSET` **叠加** ⇒ 第 2 页起恒返 0 条而 `has_more` 仍为真 ⇒ 信封出现 `has_more=true, next_cursor=null` ⇒ **客户端死循环**，实测放大成 **54,347 行 / 54,254 条重复 FAIL**）+ §5-G-a ～ G-d。

| 项 | 定案（**v1.3 冻结**） | 依据 / 判负形态 |
| --- | --- | --- |
| **入参** | `?state=&page=&limit=&cursor=` | §3.1 E7 行**同步改写**（原写作 `?state=&limit=&cursor=`、**缺 `page`**，而 §3.2 S-3 的信封含 `page` ⇒ 该不一致即本单缺陷的温床） |
| **`page` 与 `cursor` 互斥** | **同给 ⇒ `400 BAD_PARAM`**（不静默取其一） | 判负：同给返回 200；或 `page` 被静默丢弃（**已真实发生**） |
| **`page` 语义** | **1-based**；**越末页 ⇒ 空 `items` + `has_more=false`**，**绝不回吐第一页** | 判负：越末页返回第一页数据 |
| **`limit`** | **默认 50、上限 500**；**越界或非法 ⇒ 400** | 判负：静默截断 / 静默放大 / 非法值返 200 |
| **`total`** | ＝**该 `state` 过滤范围内的全量 job 条数**（不是本页条数、不是全表） | 判负：`total` 随页变化 |
| **`has_more` 恒等式** | **`has_more == (next_cursor is not None)` 恒成立**（结构性保证：`has_more=true` 而本页无行 ⇒ 强制 `false`） | 判负：出现 `has_more=true, next_cursor=null`（**死循环前兆**）；或反之 |
| **排序键** | **`ORDER BY created_at, job_id`** | **实测依据**：4 个 job 的 `created_at` 常落**同一秒**（12:51:12 三个、13:0x 四个）⇒ **只按 `created_at` 排序无法保证「不重叠 / 不遗漏」**；`job_id` 唯一 ⇒ 全集序**无并列** |
| **游标编码** | **URL-safe base64**（载荷＝`[created_at, job_id]`） | **实测依据**：`created_at` 含 `+` 与 `:`，**直接进 query 会被解码成空格** ⇒ 第二页恒空（`repository.py::encode_cursor_e7` 已留痕）。E3 的 `p<page>_i<idx>` 只由整数构成、天然安全，**不改** |
| **两路一致性** | **页码路径与游标路径的 key 集合必须相等**（不重叠、不遗漏、不重复） | 证据形式：两路逐页 key 集合 + `page_path_equals_cursor_path = true` |

**`items[]` 字段集（**v1.3 冻结 9 字段**）**：`job_id` / `pdf_name` / `pdf_path` / `state` / `total_pages` / `done_pages` / `failed_pages_count` / `created_at` / `updated_at`。**原「形状草案（1b 落地时按 §0.4 回填）」表述已被 v1.3 取代**（G-b）。

- **与平台规范的核对（**必须先核，已核**；依据 Zang 口径「核不上的项列成待裁」）**：**E7 的 `items` 是 feicui 内部实体（job）**——平台规范 **§9** 只定义 **`Seal` + `ImageAsset` 著录模型**（§9.2）、**§3.8** 只定义 **`Seal` 字段集**；**平台规范中不存在「job」实体** ⇒ **无对应字段可核、不构成冲突**；命名风格沿用 **§3.1 E2 的 snake_case**（feicui 内部一致性优先，且 §3.8 的 camelCase 只约束汇入侧著录对象，**不约束 feicui 内部端点**）。
- **核不上的项 = 无**（既无同名冲突项，也无需平台侧裁定的映射项）；**唯一跨界项**是汇入侧的「1 job ↔ 1 批（`batch_id`）」同构关系（§2.1 依据②），**不在 E7 字段面**。
- **落地状态＝已落地（由 Kong 执行，1b-ii 修复轮）**；**Jing 未复跑**（引 `REPORT_1b-ii.md` §1.5 改后翻页全表 / §3.3 与派单方独立复核 §1.7 的照录）。

> **§3.10 v1.4 注 —— `state=` 过滤的「有效态」定案（E7 一条已实测缺陷的收口；依据质检 D-1）**：
> **口径**：**`?state=` 的过滤口径与 `items[].state` 恒同出一处**——即 **§3.2 S-2 复算后的有效态**（`repository.effective_state()`；**SQL 真源＝`repository.E7_EFFECTIVE_STATE_SQL`**：`CASE WHEN j.state = 'DONE' AND COALESCE(p.failed_pages, 0) > 0 THEN 'FAILED_PARTIAL' ELSE j.state END`，**只降级、不升级**），**恒等式 `items[].state == <过滤口径>`**。
> **定案**：**`?state=DONE` 只回「有效态＝DONE」的 job**（库内 `DONE` 但含 `FAILED` 页者**不在其中**）；**`?state=FAILED_PARTIAL` 恰好回它**。
> **依据（已实测的缺陷，本注只登记、不重跑）**：质检 `qa-recheck/p1bii-neng/` 的 E7 探针**当场 FAIL**——`?state=DONE` 返回的 `items[].state` 去重集合为 `['DONE','DONE','FAILED_PARTIAL']`（**筛出来的集合与每条 `items[].state` 不一致**，前端按状态筛选因此显示错误结果），并单列 **`OBS-1`** 观察项；**成因**＝**过滤走库内原始态（`WHERE j.state = ?`）、展示走复算后有效态，二者各算一套**。
> **判负形态（可机械判负）**：① `?state=<X>` 返回的 `items[].state` 出现非 `X` 值；② 过滤与展示各算一套（库内原始态 ↔ 有效态）。**证据形式**：同一筛选条件下列出 `items[].state` 去重集合 + `filter_total`。
> **落地状态＝已落地（由 Kong 执行，1b-ii 修复轮）**；**Jing 未复跑**（引 `qa-recheck/p1bii-neng/` 证据 + `server/app/repository.py` / `server/app/routers/jobs.py` 的注释留痕）。

**G-5 / G-7 收口（v1.3）**：① **任务队列形态 ＝ 库即队列**——`jobs` + `job_pages` **就是持久队列**（断点、并发上限、进度全部由库给出）⇒ **不引入额外队列中间件**（Redis / 消息队列等）；**依据**：AC-11 实测「kill 接口层后 worker 继续推进 cursor」⇒ **队列不在接口层内存里**（§1.1 的「进程内队列或本地持久队列，形态由 Kong 定」**由本条定案为持久队列（库）**）。② **chunk 级「已完成数」不新增 E2 契约字段**——`REPORT_1b-i.md` G-7 指出「§3.1 E2 只给 `cursor:{chunk_lo,chunk_hi}`，而 AC-11 的判据要「已完成 chunk 数」」；**定案**：AC-11 的读数**直接查库**（`select count(distinct chunk_index) from job_pages where job_id=? and state='DONE'`）或取 **E2 的 `cursor.chunk_hi`**，**E2 响应形状不变**（**不得**为验收便利而扩契约）。

### 3.11 E4 请求语义定案（**v1.3 新增**｜E4 请求侧缺口收口）

| 入参 / 字段 | 定案（**v1.3 冻结**） | 为什么（**不得臆造**） |
| --- | --- | --- |
| `batch_id` | **非空 ⇒ 400** | 批次号由 **`export.py` 派生**（`fb_<date>_<book_key>_<NN>`），**不接受客户端指定**——若允许指定，会出现「客户端有、库内无」的假批次 |
| `dry_run` | **`true` ⇒ 400** | `export.py` **无 dry-run 模式** ⇒ **不假装跑过**（与 §3.2 S-6 / §3.4 纪律 3「不得以 200 承载失败」同源） |
| `book_code` | **仅作与 `config/book_codes.json` 的一致性校验**；不一致 ⇒ 400 | 书简码的签发权在平台侧（平台规范 §9.3 #9），**feicui 侧不得借此另立第二份真源**；`issued` 全 `false` 期间该入参**不改变产物命名** |
| 响应字段集 | **恰 4 字段**：`batch_id` / `package_dir` / `counts` / `selfcheck_ref` | 与 §3.1 E4 行一致；多字段即偏离 |
| `counts` | 键名＝`formal` / `draft` / `rejected`（**3 键**）；**映射登记**＝批包 `report.json` 的 `counts.feicuiDecidable` 的 `formal` / `draftStaged` / `rejectedRequiredMissing`（**逐项相等**） | 这是 feicui 内部唯一真值的三键投影；映射必须写明，否则「`draft` 到底等于哪个量」无从复算 |
| `selfcheck_ref` | **`<export_root>/selfcheck_report.json` 存在 ⇒ 给路径；否则 `null`** | **`export.py` 的 export 子命令本身不产生 selfcheck**——生成者是 **`selfcheck_export.py`**；故 **`null` 是正常态**，**不得据此判负** |
| 未知 `job_id` | **404**（体须含 `detail`，§3.4） | 与 §3.7 同源 |

### 3.12 E3 `records` 形状与 AC-08 必填 11 项键路径（**v1.3 冻结**）

> **形状真源＝F1 交付物** `feicui/export.py::build_record`（顶层**平台字段名** + 内嵌 `assets[]` + feicui 专有信息收在 `feicui` 子对象），新键路径由 `server/app/records.py::_shell_record` 对**未导出行**同形补壳。**本表即 AC-08 的判负绑定面**。

| §9.3 # | `missing_required` 取值（**feicui 语义名，snake_case**） | 记录内键路径（**平台字段名形态**） |
| --- | --- | --- |
| 1 | `seal_name` | 顶层 `sealName` |
| 2 | `dynasty` | 顶层 `dynasty` |
| 4 | `seal_type` | 顶层 `sealType` |
| 6 | `asset_kind` | `assets[].kind`（行级常量 `FACE`） |
| 7 | `source_book` | 顶层 `sourceBook` |
| 8 | `source_page_no` | 顶层 `sourcePageNo`（1-based） |
| 9 | `seal_code` | 顶层 `sealCode` |
| 10 | `sha256` | `assets[].sha256` |
| 11 | `image_metrics` | `assets[].bytes` + `assets[].width` + `assets[].height` + `assets[].colorMode`（**4 子键**） |
| 13 | `review_status` | 顶层 `reviewStatus` |
| 14 | `batch_id` | `assets[].batchId` |

- **顶层另有**（非必填项 / 载体字段）：`transcription`、`bbox`（`{x1,y1,x2,y2,unit}`）、`dedupeKey`、`assets[]`、`feicui{}`、**`missing_required[]`**。
- **`missing_required` 一律用 feicui 语义名**（与 `records.py::REQUIRED_KEYS` 与 `exports/selfcheck_report.json` 的 `requiredCoverage` **同名**）。**记录内的平台字段名与 `missing_required` 的语义名是两套命名，映射即本表**——**不得混用**（AC-08 判负绑定到本表的**键路径**，不再以「字段名与 §9.3 字面一致」为判负条件；**该字面一致的旧写法与实现形态冲突，已由 v1.3 取代**）。
- **§9.3 的语义名 → 平台字段名的对齐来源**：平台规范 **§9.3「对应平台字段」列**（`seal_name`→`Seal.sealName`、`sha256`→`ImageAsset.sha256`、`image_bytes`/`width`/`height`/`color_mode`→`ImageAsset` 度量字段、`batch_id`→`Seal.batchId`/`ImageAsset.batchId`）与 **§3.8 / §3.9 字段表**。
- **⚠ 报冲突（**不自行改平台口径**，依据 Zang 口径 10）**：平台规范 **§9.3** 把 `sourceBook` / `sourcePageNo` 列为**必填**，而 **§3.8** 的 `Seal` 字段表把 `sourceBook` / `sourcePageNo` 标为**否（非必填）** ⇒ **平台规范内部必填性不一致**。feicui 侧按 §9.3 执行（**冻结键路径不变**），**冲突登记为 §9-R17**，**转平台侧按 §0.4 裁定**；**本轮不改平台规范任何一字**。
- **⚠ `idx` 锚点冻结（**v1.4 补齐｜G-1b 收口**）**：**E6 需要 `(page, idx)` 才唯一**（§3.5「必须带页段」：行级唯一锚是 `(pdf_name, page, idx)`），而本表此前**只冻结了 `page` 的键路径**（顶层 `sourcePageNo`）、**`idx` 没有规范明文冻结** ⇒ **同类「取不到锚点」缺陷会复发**。**定案（本行即冻结面，与上表同属 AC-08 绑定面）**：**`idx` 的规范键路径 ＝ `feicui.stampIdx`**（`feicui` 子对象内、整数、**行级**：同一 `(pdf_name, page)` 内唯一）。**落地形态兼容**：实现按真源 `feicui/export.py::build_record` 取 **`feicui.stampIdx`**，**并以 `assets[].seq` 兜底**（二者同值，见 `export.py` / `server/app/records.py::_shell_record`）⇒ **凡取行级锚点处一律以 `feicui.stampIdx` 为准、以 `assets[].seq` 为等价回退，不得另立第三来源**。**备选形态（未采纳，登记备查）**：为 `items[]` 加**顶层 `idx`**——**本轮不采纳**（避免同一语义两处出口；如后续确需顶层字段，须按 §0.4 立项、**同时改本表**并升版）。

### 3.13 响应头纪律：非 ASCII 值必须百分号编码（**v1.3 新增**｜G-h 收口）

| 项 | 定案（**v1.3 冻结**） |
| --- | --- |
| **适用面** | 凡以响应头承载**可能含非 ASCII 的值**（现存：`x-feicui-scope`（E3 / E5 / E7）、`x-feicui-img-path`（E6））——**头值必须 latin-1 可编码**，含中文书名等非 ASCII 时**必须百分号编码（RFC 3986 `%XX`，UTF-8 字节序）** |
| **可机械判负的判据（4 条，任一不成立即 FAIL）** | ① 头值可被 `str.encode('latin-1')` 编码（**不抛异常**）；② **原始非 ASCII 字符不得直接出现**（正则扫描头值，`[^\x00-\x7F]` 命中数须为 **0**）；③ **解码后与 DB 内字符串字面一致**（`urllib.parse.unquote` 逆变换后与 `stamps.pdf_name` **逐字节相等**）；④ **头不进 JSON 体**（§3.2 S-3 的字段封闭**不受影响**） |
| **判负形态** | 头值直接写中文 ⇒ **HTTP 头值 latin-1 编码失败 ⇒ 500**（**已真实发生**：含中文书名的建单曾被该写法拒掉）；或头值被截断 / 被框架丢弃而客户端拿到空值 |
| **证据形式** | 响应头原始字节 dump + 上述 4 条的复算输出（含 `unquote` 逆变换对照） |

> **§3.13 v1.4 注 —— E6 的 `x-feicui-img-path`：本条要求**已被实测违反过一次**（只登记，不重跑）**：
> **事实**（证据＝`server/app/routers/jobs.py` E6 处理处注释 + `server/REPORT_1b-ii.md`）：`x-feicui-img-path` 的原实现**直接回吐 DB 原值**（如 `output/秦汉印典 …/p5_0.webp`）⇒ **starlette 编码响应头时抛 `UnicodeEncodeError` ⇒ E6 整条 500**——**含中文书名的书取图全挂、ASCII 名书正常**（**同一缺陷形态**此前亦命中 E3 / E5 / E7 的 `x-feicui-scope` 头）。
> **收口形态**：现实现统一走 **`_header_safe()`**（非 ASCII 逐字符 `quote()`、UTF-8 字节序），前端以 `decodeURIComponent` 还原。**本注只登记事实**：**§3.13 的 4 条可机械判负判据一字未改**；**E6 的 `x-feicui-img-path` 头值必须百分号编码**——**该要求自 v1.3 起即已冻结，本次仅补登记其实测违例与收口**。

---

### 3.14 工具端点契约：`POST /api/tools/square-crop`（5196）（**v1.6 新增**｜F-1 / F-4 / F-5）

> **来源（只读引用，Jing 未复跑）**：`feicui/server/README.md` **§12**（**改后 md5 `12608c7bacb7dc1cc8368333b99f2188`**）＋ `feicui/ops/kong_square_crop_evidence.md`（**24,666 B / 311 行**，自记时点 2026-09-20 17:2x）＋ `feicui/ops/kong_square_crop_coldstart_raw.txt`（**6,561 B / 75 行**，脚本自记时点 **2026-09-20T17:25:31+08:00**）＋ `feicui/ops/kong_square_crop_selftest_raw.txt`（**54,539 B**）。

**定位**：**本端点与 job 体系完全无关**——它是**纯函数式工具端点**（「上传一张印面影像 → 拿回方形化后的候选」），**不参与** E1 ～ E7 的 job 流程，**不占** §7 AC-01 ～ AC-13 的证据面。

#### 3.14.1 请求（契约）

| 项 | 值（冻结） |
| --- | --- |
| 方法 / 路径 | **`POST /api/tools/square-crop`**（端口 **5196**；面板 sid **`feicui-api`**） |
| `Content-Type` | **必须** `multipart/form-data`（带 boundary）；否则 ⇒ **`400 BAD_CONTENT_TYPE`** |
| 文件字段名 | **逐字 `image`**（必填）；**字段名不逐字**（如 `file` / `img`）⇒ **`400 NO_IMAGE`** |
| 请求体上限 | `MAX_UPLOAD_BYTES = 32 MiB`（**只量 `Content-Length` 级别的原始 body**）；超限 ⇒ **`400 UPLOAD_TOO_LARGE`**；**不落任何临时文件** |
| 可选文本字段 | `pad_ratio`（默认 **`0.15`**，范围 `[0.0, 1.0]`）／`min_area_eff`（**默认不传**，`> 0`）／`quality`（默认 **`95`**，范围 `[1, 100]`）／`max_side`（默认 **`0`**，`>= 0`；`0` ＝不缩放，`>0` 且 `side > max_side` ⇒ 用 `INTER_AREA` 缩到 `max_side × max_side`（**只缩不放**，缩放后仍是正方形）） |
| 越界 / 非数字 | **`400 BAD_PARAM`**（`reason` 带可读原因） |

> **上限口径归属（与玺爱侧解耦，硬口径）**：**本端点自己的 `32 MiB` 请求体上限是「本端点这个口的输入上限」**，**与玺爱侧「用户所选文件 ≤ 1 MB（原始文件字节）」是两个不同的口**（**玺爱侧见 `xiai/docs/xiai.spec.md` §3.12.5 J-5 / §3.12.9 J-9**）。**两者不得互相引用、不得同值复用**；**任何一方改自己的上限，不需改另一方**（**判负形态：以本端点的 32 MiB 去覆盖玺爱侧口径，或反之**）。

#### 3.14.2 响应（`200`）与字段集（冻结）

信封：`{ok:true, count, source:{width,height}, candidates:[…], params_used:{…}, degraded:bool}`。

**单个候选 `candidates[i]` 的字段集封闭为以下 12 项 ＋ 1 项 reasons**：`idx` / `bbox` / `square` / `side` / `width` / `height` / `mime` / `sha256` / `image_base64` / `area` / `aspect` / `degraded`（＋ `degraded_reasons`）。

| 字段 | 语义（冻结） |
| --- | --- |
| `idx` | 排序后的位次（0 起）。**排序键 ＝ 面积降序，同面积按 `bbox` 的 `x1,y1` 升序** ⇒ **前端默认取第 0 个** |
| `bbox` | 检测到的**外扩后** bbox `[x1,y1,x2,y2]`（半开区间、**未方形化**，便于对比） |
| `square` | **方形化后**的 `[x1,y1,x2,y2]`：**恒满足 `x2-x1 == y2-y1 == side`** 且落在图像内 |
| `side` | 方形边长（＝ `max(bbox 宽, bbox 高)`；被图像短边夹过则**如实降级**） |
| `width` / `height` | **输出**影像尺寸（`max_side` 生效后）；**两者恒相等** |
| `mime` | **恒 `image/webp`**（**RIFF magic 自证**） |
| `sha256` | 输出 WebP **字节**的 sha256（**客户端可自算比对**） |
| `image_base64` | 输出 WebP 字节的 base64 |
| `area` / `aspect` | **检测阶段**原值（contour 面积 / 长宽比），**不因方形化改变** |
| `degraded` / `degraded_reasons` | 该候选是否降级；`reasons ⊂ {SHORT_SIDE_CLAMP, BOUNDARY_SHIFT}` |

`params_used`：`{hsv_low, hsv_high, min_area_eff, min_area_source, pad_ratio, quality, max_side, template_source}`——其中 **`min_area_eff` 是 worker 侧真实生效值**（**不是接口层复算值**）。**`source` 是输入影像尺寸**（`{width,height}`）。

**判负形态**：① `candidates[]` 缺上表任**必给**字段；② `square` **不满足 `x2-x1 == y2-y1 == side`**；③ **`mime` 非 `image/webp`**（或**声称 `image/webp` 而字节不是 WebP**）；④ **`sha256` 与 `image_base64` 解出的字节不符**；⑤ `width ≠ height`；⑥ **`params_used.min_area_eff` 是接口层复算值**而非 worker 侧真实生效值。

#### 3.14.3 错误码（**一律结构化 JSON、绝不返回 HTML 错误页**）

| 状态 | `error` | 触发 |
| --- | --- | --- |
| `400` | `BAD_CONTENT_TYPE` | 不是 `multipart/form-data` |
| `400` | `UPLOAD_TOO_LARGE` | body > **32 MiB** |
| `400` | `BAD_MULTIPART` | boundary 缺失 / multipart 结构损坏 |
| `400` | `NO_IMAGE` | 缺字段 `image` 或该字段为空 |
| `400` | `BAD_PARAM` | `pad_ratio` / `min_area_eff` / `quality` / `max_side` 越界或非数字 |
| `400` | `DECODE_FAILED` | `cv2.imdecode` 解不出来（不是可解码图片） |
| `422` | `NO_CANDIDATE` | 能解码但**零候选**（**必须附 `source` / `params_used` 便于排查**） |
| `500` | `RUNNER_*` / `INTERNAL` | 子进程失败（`RUNNER_PYTHON_MISSING` / `RUNNER_TIMEOUT` / `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`）或未预期异常 |

**错误体形状**：`{ok:false, error, reason, detail}`（`422` 另带 `source` / `params_used`）。

**判负形态**：① **任一错误响应返回 HTML / 非 JSON 体**（**含 500 的未捕获异常页**）；② 错误体**缺 `error` 或 `reason`**；③ **零候选错报成 `400`（应为 `422 NO_CANDIDATE`）**，或 `422` 不带 `source` / `params_used`；④ **用 200 + 空 `candidates` 冒充「无候选」**。

#### 3.14.4 CORS（**白名单唯一真源**）

- **白名单唯一真源 ＝ `Settings.cors_origins`**（env `FEICUI_CORS_ORIGINS`）。**默认含 5195 两项**（`http://127.0.0.1:5195` / `http://localhost:5195`）**与 5163**（玺爱）。
- **不放开 `*`**；**白名单外的 origin ⇒ 不回 `access-control-allow-origin`**。
- **实测口径（只读引用 `kong_square_crop_evidence.md` §4.2）**：实 POST（`Origin: http://127.0.0.1:5163`）回 `content-type: application/json` ＋ **`access-control-allow-origin: http://127.0.0.1:5163`** ＋ `vary: Origin`；**预检 `OPTIONS` 同样回 ACAO**；**负例** `Origin: http://127.0.0.1:59999` ⇒ **`400 Disallowed CORS origin`**、**无 ACAO**。

**判负形态**：① **`access-control-allow-origin: *`**；② **白名单外的 origin 也回 ACAO**；③ **预检不回 ACAO 而实 POST 回**（两者不一致）；④ **代码里另写一份 origin 列表**（**与 `Settings.cors_origins` 不是同一真源 ⇒ 即判负**）；⑤ **白名单里出现与 5195 / 5163 无关的域**（须走 §0.4 流程才可加）。

#### 3.14.5 红线：**零 DB 写 · 不建 job · 不落盘**

- **无任何 SQL、无 `repository` 调用、不读 `stamps`**；**不建 job**（`jobs` / `job_pages` **一个字都不碰**）；
- **不碰 `exports/` / `output/`**；上传字节**只进不出**（进来 → base64 回去），**全程不落盘、不建临时文件**；
- **不复制检测算法**：红掩膜口径**一律走 `processor.detect_stamp_regions`**（在 worker 子进程里跑）；**方形化只有一份实现**（`app/square.py`），两侧共用；
- **⇒ 该端点是 `yinpu.db` 的只读旁观者**：**`stamps` 行集指纹在调用前后逐字节不变**（**只读引用 `kong_square_crop_evidence.md` T8**：`stamps` rows **89 → 89**、`md5_B_canon` `d3932fdc…` → `d3932fdc…`、原 79 行子集 `d7abe995…` → `d7abe995…`；**Jing 未复跑**）。

**判负形态**：① 调用前后 `stamps` / `jobs` / `job_pages` **任一内容指纹变化**；② **产生 job**（`jobs` 行数 +1）；③ **在 `exports/` / `output/` / 临时目录落盘**；④ **在接口层复制一份检测算法**（出现第二份红掩膜 / `encode_webp` 实现）；⑤ **接口层 import `cv2`**（图像栈应只在 worker 侧，§6.5 解释器矩阵）。

#### 3.14.6 来源标签口径（F-4｜`min_area_source` **不得引用不存在的来源**）

- **红线：绝不引用不存在的键**。`template_source` 与 `min_area_source` **由同一个来源派生**（`app/square.py` 的 `load_template_params()` ＋ `min_area_source_label()`）⇒ **两者不可能互相矛盾**。
- **当前实况（只读引用）**：`config/templates.json` **顶层只有三本书名键、没有 `default` 键**（**脚本 ⓪ 前置核验会实时断言此点**；md5 `20acf9162baf0a0c4e5d6e164681b5ce` 未动）⇒ **一律以内建常量为准**，并**如实标注三件事**：① 它是**内建兜底常量**；② **常量在源码的确切位置**；③ **与语料逐字核验的结果**——冻结形状：**`builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)`**；各书之间不一致 ⇒ `builtin(corpus-DIVERGENT·…)`；文件缺失 / 读不出 ⇒ `builtin(no-template-file·…)` / `builtin(template-unreadable·…)`。
- **`min_area_source` 的形状** ＝ `<template_source>·min_area=<模板值>×processor.AREA_SCALE=<实际值>`；**显式给出 `min_area_eff` 时为 `explicit(min_area_eff)`**。
- **历史缺陷（登记，防复发）**：改前 `min_area_source` **硬编码 `templates.json:default`**，而 `templates.json` 顶层**并无 `default` 键** ⇒ 属「**引用了不存在的来源键**」（**那个 800 其实来自 `square.py` 的内建兜底常量**）。**改法 ＝ 只改标签文本与取值、算法与数值零改动**——自证读数：改前 / 改后 **`min_area_eff` 均为 `6172.839506172839`**（＝ 800 × 7.716049382716049）、**候选 `sha256` 均为 `b540bf97…`**、**`side/width/height` 均为 341**、**`square` 均为 `[1,0,342,341]`**。
- **待裁（登记，不阻塞）**：**是否要在 `config/templates.json` 里补一个 `default` 项**（值＝三本书现行值），使「真源」名副其实？→ **§9-R18**。

**判负形态**：① 标签**引用不存在的来源键**（如再写 `templates.json:default`）；② 标签**不指出内建常量的位置**，或**不给语料核验结果**；③ `template_source` 与 `min_area_source` **互相矛盾**；④ 为「修标签」而**偷偷往 `config/templates.json` 塞 `default` 键**（**该动作本身不作判负，但必须经 §9-R18 裁定并留痕**）；⑤ 修标签时**改动了 `min_area_eff` / 候选 `sha256` / `side`**（**即借修标签之名改了算法**）。

#### 3.14.7 玺爱（5163）接入状态：**已具备、暂不接入**（F-5｜与玺爱侧 R-18 / §3.12.6 对齐）

- **现状（口径）**：该端点**已具备**（契约见上；自测 / CORS / 零 DB 写证据见 §3.14.4 / §3.14.5 / §3.14.8），**但玺爱上传路径「零 5196 调用、零外链」——暂不接入**。**依据 ＝ 玺爱侧 Zang 裁定 R-18（「斐萃 `POST /api/tools/square-crop`（5196）保留但暂不接入」）＋ Kevin clarify 作答「单一印面不走斐萃」**；**同源写入 `xiai/docs/xiai.spec.md` §3.12.6（J-6）与 §3.12.9（J-9）**。
- **原因（写明，避免被读成「端点没用」）**：① **玺爱的上传场景是「单张印面图」**——**浏览器端即可完成**「解码 → 降采样（最长边 ≤ 2048）→ **方形裁切**（中心最大正方形 ＋ **用户可拖拽 / 缩放取景框**）→ WebP（q ≈ 0.85）」，**不需要机器自动检测**；② 接入 5196 会把**本地零依赖的纯前端路径**变成**跨进程 / 跨端口依赖**——**5196 未起 / 端口被占 / CORS 白名单漂移，任何一项都会让上传失败**（**而浏览器端路径无此风险**）；③ **红掩膜自动检测在实拍复杂背景下不可靠**（**这正是 R-15 选「取景框」而不是「自动检测」的直接理由**）⇒ 对玺爱场景**收益为负**。
- **将来适用场景（写明，避免被读成「永久不用」）**：**「整页扫描含多枚印面」**——即**一页影像里含多枚印面、需要机器圈选出多个候选**时（**此时 `candidates[]` 的多候选语义才有用**；**玺爱当前的上传口只处理单枚印面**）。**该场景出现时，须走 §0.4 流程改本节 + 玺爱侧 §3.12.6，两侧口径同步。**
- **判负形态**：① **玺爱上传路径出现对 5196 / `/api/tools/square-crop` 的调用**；② **玺爱上传路径出现任何对外（非本机）请求**；③ 把「暂不接入」实现为「**删除端点 / 停用端点 / 从 `services` 表移除**」（**端点须保留**——**它是将来适用场景的载体**，且 **§6.2 / PORTS.md 已登记 5196 为已托管**）；④ **以「已具备」为由宣称玺爱已接入**（**接入须先按 §0.4 改本节**）。

#### 3.14.8 证据索引（**只读引用，Jing 未复跑**）

| 编号 | 内容 | 证据文件 | 自记时点 |
| --- | --- | --- | --- |
| T1 | 端点全量自测（真实影像 200 / 方形 / `sha256` 自算 / 零 DB 写 / 错误码 / CORS / `curl -F` 独立客户端） | `ops/kong_square_crop_selftest_raw.txt` **第 3 段（自 418 行起）** | 2026-09-20 17:2x |
| T2 | 冷启动 A/B ＋ 来源标签如实性 ＋ `sha256` 不变 | `ops/kong_square_crop_coldstart_raw.txt` **第 2 段** | **2026-09-20T17:25:31+08:00** |
| T3 | 惰性替身对 OCR 路径语义等价（不加载真模型） | 同上 **第 1 段** | 同上 |
| T8 | 零 DB 写（调用前后 `stamps` 指纹） | `ops/kong_square_crop_selftest_raw.txt` 第 3 段 | 2026-09-20 17:2x |
| T9 | 改后响应关键字段（`count=1` / `side=width=height=341` / `mime=image/webp` / `sha256=b540bf97…` / `square=[1,0,342,341]` / `degraded=true(SHORT_SIDE_CLAMP)`） | `ops/kong_square_crop_evidence.md` §4.2 | 2026-09-20 17:2x |

> **证据引用纪律**：**本表只作索引与口径锚点**；**证据文件里自记的「61/61 PASS」「11/11 PASS」「13 条断言」等结论一律只引用、不背书**（**验收执行归 Neng**）。**证据文件一律不落 `/tmp`**（沿用 §7 的证据目录口径）。

**本节状态**：**本节为契约与口径登记**；**落地状态 ＝ 已定、已具备（引证据文件，Jing 未复跑）**；**验收执行归 Neng**；**本节不含任何「本轮已通过」结论**。**本节不各设 AC**（**§7 AC 计数仍 13 条**）。

### 3.15 印人采集（外部印人数据源采集线）（**v1.7 新增**｜只定口径 / 契约形状 / 存储 / 批次 / 判据，不定实现）

> **落位声明**：本小节为 **v1.7 追加**（**新增小节，置于 §3.14 及其表下注之后、`## 4. 数据层演进` 之前**）。**§3.1 〜 §3.14 的节标题、表、条文与各版表下注原文逐字未改**（**唯一新增 ＝ 本小节 ＋ §7 的 AC-14 〜 AC-20 七行 ＋ §7 表下注（v1.7 追加）一条 ＋ §9 的 R21 〜 R24 四行 ＋ §9 计数留痕（v1.7 追加）一条 ＋ §10 本版行，均属「只增行」**）。
> **口径真源**：**本小节逐条照登 Zang 2026-10-10 拆解件 `feicui/docs/person-ingest-draft-v0.1.md`**（**含实测 API 契约、Kevin 门控四答、批 1 / 批 2 范围、字段映射表、建议判据**）；**不自行发明、不改与之冲突的口径**。
> **性质**：**本小节只写口径 / 契约 / 判据**；**不含落地 · 验收结论、不含任何「实现现状」读数**（**落地属「已定、落地中（由 Kong 执行）」、验收归 Neng**）。**联网口径红线**：**联网只发生在 feicui 服务端、且只读**（§3.15.9）。

#### 3.15.1 逐字口径与范围（Kevin 门控四答 G-1 〜 G-4，**照登不改写**）

| # | 裁定（Kevin 2026-10-10 逐字口径） |
| --- | --- |
| **G-1** | **页签落点 ＝ feicui 前端首页导航新增「印人采集」页签**（**5195 直连 / 经 5164 的 `/feicui` 均可达**） |
| **G-2** | **写入 xiai 的路径 ＝ 新增「外部批量导入」通道：先落暂存集合（如 `xiai_person_imports` / PENDING），管理员批量采纳后落 `xiai_persons`**（守审核门、可回滚）——**批 2 范围、见 §3.15.1 表下注** |
| **G-3** | **籍贯 / 传记 / 来源 / 外部 id ＋ 详情页口径**：**A ＝ 扩展 person 模型新增 `native_place` / `biography` / `source` / `source_id`**；**追加口径（Kevin 逐字）「我给你的地址并不是只要读取列表页就可以了，每行有详情页，你需要读详情页。」** |
| **G-4** | **本轮范围 ＝ 分两批**：**批 1 ＝ feicui 侧（页签＋服务端拉取归一化＋落 feicui 本库＋批次包）先验收；批 2 ＝ 再接 xiai 落库通道与端到端** |

**表下注（v1.7 追加）**：① **本小节（§3.15）只覆盖批 1（feicui 侧）**；**批 2（xiai 落库通道 / 端到端）不在本文件范围**（**归 `xiai/docs/xiai.spec.md` 的 §3.54 增量，由玺爱侧按其自己的 §1.3 流程同轮改**）；② **G-2 的暂存集合名（`xiai_person_imports`）与 G-3 的四字段（`native_place` / `biography` / `source` / `source_id`）为 xiai 侧字段 / 集合面，本文件只**引用**、不另立第二真源**。

**表下注（v1.8 追加｜范围裁定登记）**：**Kevin 2026-10-10 裁定——批 2（写入 xiai 的通道）由另一会话承接**；**本文件只约束批 1**；**feicui 侧不得写 xiai 任何文件、不得做任何 CloudBase 写操作**。**本句系新裁定、非既有条款改写**——**上一条表下注（v1.7 追加）的 ①「批 2（xiai 落库通道 / 端到端）不在本文件范围（归 `xiai/docs/xiai.spec.md` 的 §3.54 增量，由玺爱侧按其自己的 §1.3 流程同轮改）」已被本裁定取代**（**该句原文逐字保留、不重写**）。**批 2 的入口与口径以交接件 `feicui/docs/person-ingest-handoff-v0.1.md` 为准**（**本文件只引用、不复制其全文、不另立第二真源**）。**批次包即对外唯一交付缝**，冻结于 **§3.15.10**（对外程序可机械校验粒度）。

#### 3.15.2 ① 页签与路由 `/persons`

- **页签**：**`feicui/web` 首页导航（`App.vue`）新增【印人采集】页签**（**现导航仅【任务页】一项**）。

> **（v1.9 注｜新口径，非既有条款改写）**：**Kevin 2026-10-10 新口径**——**① 页签文案**：**现为【印谱解析】（原【任务页】，即任务台主页面）与【印人采集】两项**；**② 顶部结构**：**页面顶部＝固定页眉（header）＋标题区**——**吸顶 / 固定、不透明背景、色值一律走 CSS 变量 token**（token 源见 §0.5.2）；**③ tabbar 位置**：**tabbar 位于核心内容区顶部，即 `main` 内、`RouterView` 之前，不在页眉内**；**④ 不遮挡**：**固定页眉不得遮挡内容**（滚动后仍贴顶且内容可见）。**本注系新口径登记，不改写上方旧行**——旧行「**现导航仅【任务页】一项**」**原文逐字保留**，**已被 v1.9 取代**（页签文案与 tabbar 布局）。**机械判据 ＝ §7 AC-23**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**。
> **（v1.15 追注｜页签集合随动，非「既有条款自动失效」）**：**v1.15 起页签集合为四项**——**① 页签文案**：**现为【印谱解析】（原【任务页】）、【印人采集】、【印谱采集】、【印章采集】（第四项，v1.15 新增，§3.17.2）四项**；**本 v1.9 注上句「现为【印谱解析】（原【任务页】，即任务台主页面）与【印人采集】两项」已被 v1.15 取代**（**原文逐字保留、不重写**）。**本追注系口径随动登记、不改写上方旧行**；**机械判据 ＝ §7 AC-23（v1.15 原位改写后为四项页签）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**。
- **路由**：**新增 `/persons`**；**history base 仍须取 `import.meta.env.BASE_URL`**（**不得写死 `/`**；沿既有 G-1 教训）。
- **可达性**：**经 5195 直连**与**经 5164 的 `/feicui/persons`**（**Vite proxy `/feicui` → `http://127.0.0.1:5195`，§6.4 已登记**）**均可达**且 `location.href` **不回落**首页。
- **页面三区**：**采集区**（触发同步 / 进度 / 上次结果 / 批次列表）、**列表区**（570 条；筛选：姓氏首字母 / 国籍 / 有无生卒 / 有无关联；分页）、**详情区**（含关联印谱 / 印章）。**界面文案简体**（feicui 侧）；**源数据一律按原文呈现，同时展示繁 / 简两版字段**（§3.15.6）；**不得本地改写源数据**。
- **后端不可达**：**沿用既有「未连接」横幅口径**（§3.9 / §3.6 表下注），**不得以假数据填充**（**无假数据**硬约束）。

> **（v1.10 注｜新口径，非既有条款改写）**：**「采集区」新增「生成 xiai 就绪导入包」按钮**（**触发 `POST /api/persons/import-package`**），产出**按 xiai 键面裁剪好**的导入载荷落到约定交换目录；**提交与审核仍在玺爱侧**（**审核门维持**）。**契约（两个新端点 / 产物目录 / 三文件 / 18 键面 / 三桶 `string[]` / 两条外部依赖）＝ §3.15.11**；**机械判据 ＝ §7 AC-24**。**本注系新口径登记，不改写上方旧行**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**。

#### 3.15.3 ② 四条新端点契约（`feicui/server`，端口 **5196**；**additive、不动 E1 〜 E7**）

| # | 方法 / 路径 | 语义 | 要点 |
| --- | --- | --- | --- |
| **P1** | `POST /api/persons/sync` | **拉全量并落库**（`pageRows=1000` 一次取全 570 条 → 逐人 `person/detail` ＋ `graph/person` → 归一化 → 落本库 → 产批次包） | **可断点续跑**；**礼貌限速**；**触发形态 ＝ 手动按钮**（§9-R23）；**响应给出批次号与计数** |
| **P2** | `GET /api/persons` | **列表（分页 / 筛选）** | 分页与筛选参数**形状随实现**；**不得把业务真值放进接口层缓存**（沿 §3.2 S-4） |
| **P3** | `GET /api/persons/{grbsm}` | **单人（详情 ＋ 关联）** | `{grbsm}` ＝ `personGrbsm`（稳定外部键）；未命中 ⇒ **404** |
| **P4** | `GET /api/persons/batches` | **批次列表（含回执读数）** | 逐批次给**计数 / 覆盖率 / 失败清单引用** |

- **错误码纪律（硬要求，写入即判据）**：**一律返回结构化 JSON**，**绝不返回 HTML 错误页**（含 500 的未捕获异常页）；错误体须含机器可读字段（如 `error` / `detail`）与人类可读说明。**禁止以 `200` + 空 `items` 冒充「接口未实现」或「无数据」**（沿 §3.4 纪律 3）。
- **CORS**：**白名单仅 `http://127.0.0.1:5195` / `http://localhost:5195`**（§3.14.4 既有白名单）；**任何情况下不放开 `*`**。
- **HTTP 客户端**：**优先 stdlib（`urllib`）**，**避免改动 `server/requirements.txt` 的既有 freeze 口径**。
- **源端契约（照登拆解件 §2.1 实测；本版只登记、未复跑）**：

| 源端点 | 方法 | 入参 / 路径 | 用途 |
| --- | --- | --- | --- |
| `/service_yinpu/person/list` | POST | `{pageNum,pageRows,fullText,facetPersonGjqc,facetPersonInitial,orderField,orderType}` | **列表页**；**`pageRows=1000` 一次返回全部 570 条**（`total=570`） |
| `/service_yinpu/person/facet` | POST | `{fullText}` | 分面（国籍 / 姓氏首字母） |
| `/service_yinpu/person/detail/<personGrbsm>` | GET | 路径参数 | **详情页主数据** |
| `/service_yinpu/graph/person/<personGrbsm>` | GET | 路径参数 | **详情页关联图：该印人的印谱与印章（列表页没有）** |
| `/service_yinpu/statistic/home` | GET | — | 站点计数（`sealCount=716` / `personCount=570` / `bookCount=1742`） |

- **响应信封**：`{data, total?, code:200, msg, status:true}`。**`person/detail|info|get`（POST 形态）不存在 ⇒ 404**（详情页实际走 **GET 路径参数** 形态）。**响应头实测含 `Access-Control-Allow-Origin: *`**（浏览器可直连；**本线仍主张经 feicui 服务端拉取**——理由 ＝ 留痕 / 限速 / 归一化 / 落库单点）。**吞吐实测 ＝ 详情单请求 0.189 s**（⇒ 570 人 ×（detail + graph）≈ 1140 请求 ≈ 3.7 min，**须礼貌限速与断点续跑**）。

#### 3.15.4 ③ 存储口径（**独立 SQLite，不碰正式库**）

- **新增独立 SQLite ＝ `feicui/var/person_ingest.db`**，表三张：**`persons`** / **`person_relations`** / **`person_import_batches`**。
- **`yinpu.db`（印谱解析正式库）一字不碰**——**理由** ＝ 该库有「只能加法 + 红线判据」历史包袱，且**印人采集与印谱解析无数据依赖**（§9-R21；**Zang 默认 · 一句话可改**）。
- **归一化落库须保留源原文与源键**（**不得丢源**）：`source_person_id` ＝ `personGrbsm`、`source_data_source_id` ＝ `dataSourceId`、`source_seqid`（行级 `seqid`；**列表与详情不同号，不作键**）。
- **只许加法**：**不得改既有端点语义、不动 `stamps` / `jobs` / `output/` / 既有 `exports/fb_*`、不动 `feicui/app.py`（Streamlit 退役面）**。

#### 3.15.5 ④ 批次包形态（沿用 F1 形态）

- **产物目录 ＝ `feicui/exports/person_<yyyymmdd>_01/`**，含 **`manifest.json`** ＋ **`report.json`（计数 / 覆盖率 / 失败清单）** ＋ **`persons.jsonl`** ＋ **`relations.jsonl`**。
- **既有 `exports/fb_*` 一字不动**（§3.15.4 只加法）；**同名 / 重复批次须幂等**（不覆盖既有批次、不产半成品）。

#### 3.15.6 ⑤ 归一化与繁简存法

**字段映射（批 1 采集面；批 2 落 xiai 沿用；照登拆解件 §4.5「Zang 默认 · 一句话可改」）**：

| 目标（拟） | 源 | 归一化规则 |
| --- | --- | --- |
| `source_person_id` | `personGrbsm` | 原样字符串（**幂等键**） |
| `name_full` | `personGrsxmc` | 原样（**唯一姓名来源**） |
| `family_name` | 抽取自 `personGrsxmc` | **首字为姓**；**复姓白名单**（歐陽/司馬/上官/諸葛/東方/皇甫/尉遲/公孫/慕容/司徒/獨孤/南宮/宇文/長孫/夏侯/西門/令狐/端木/聞人/赫連/澹臺/呼延/百里…）命中取二字；**4 字以上或无法判定 ⇒ `family_name=''`、整串落 `given_name`**（**不猜**） |
| `given_name` | 同上 | 余下部分 |
| `courtesy_names[]` / `art_names[]` / `alias_names[]` | `personBm`（繁）/ `personBmChs`（简） | **自由文本抽取**，逐项标注 **`extraction='rule-based'`**；**抽不准的一律落 `alias_names[]`**；**不得**写成权威分类 |
| `birth_year` / `death_year` | `personCsrq` / `personSwrq` | 纯数字 ⇒ 整数；含 `?` / 空 ⇒ **`null`**（**不设特值**） |
| `birth_death_text` | `personSzn` | 原样 |
| `native_place` | `personJg`（繁） | 原样；简版另存 `native_place_chs`（`personJgChs`） |
| `biography` | `personJj`（繁） | 原样；简版另存 `biography_chs`（`personJjChs`） |
| `nationality` | `personGj`（繁）/ `personGjqc` | 原样 |
| `cbdb_id` | `personCbdbId` | 原样（104 / 570 有值）；**不联网核验** |
| `source` | `dataSource` | 原样（「林章松《印人小传》」） |
| `source_id` | `dataSourceId` | 原样 |
| `spell` / `initial` / `flag` | `personSpell` / `personInitial` / `flag` | 原样（检索与排查用） |
| 关联 | `graph/person` | 逐条落 `person_relations`（`kind` ＝ 印谱 / 印章；`ref_id`；`name` / `desc`；`creator_type`；`image_key` ＝ `image`；`as_book_id`；`has_image`） |

- **繁简存法（Zang 默认 · 一句话可改）**：**繁体为正字段（上屏为繁体）、简体入副字段（`*_chs`）**，**不做任何转换改写**（沿「不转用户输入」纪律）。
- **源字段实测覆盖（照登拆解件 §2.2）**：`personGrsxmc` 570/570；`personBm` / `personBmChs` 552/570；`personJj` / `personJjChs` 570/570；`personGrfz` 79/570；`personJg` / `personJgChs` 568/570；`personGj` / `personGjqc` / `personGjdm` 569/570；`personCsrq` / `personSwrq` / `personSzn` 362 / 301 / 371；`personCbdbId` 104/570；`personXing` / `personMing` / `personZi` **0/570**（⇒ 须抽取）；`personZz` / `personCd` / `personCsd` / `personDz` / `personJzd` / `personHdly` / `personRzdwmc` **0/570**（预留位）。
- **关联规模差异极大**（实测锚点）：**宗汝剛 `907566313` ⇒ 印谱 0 / 印章 0；趙之謙 `907404573` ⇒ 印谱 23 / 印章 65；吳昌碩 `907271790` ⇒ 印章 10** ⇒ **不可只抓列表**（G-3 口径的实证，落 AC-16）。
- **印章影像（`image_key`）默认只存键、不下载影像**（§9-R24）；**关联面默认只落 `graph/person` 的直接关联，不递归到印章 / 印谱详情**（§9-R22）。

#### 3.15.7 ⑥ 礼貌限速 / 断点续跑 / 失败清单

- **礼貌限速**：**采集串行 ＋ 请求间隔**（**不得并发轰击源站**）；**吞吐锚点 0.189 s / 请求**（§3.15.3）。
- **断点续跑**：**采集进度须落盘**（本库或批次包）；**中断后从断点续采**，**已完成条目不得重算重写**（幂等，落 AC-17）。
- **失败清单**：**失败条目进 `report.json` 失败清单**，**不得静默跳过**（**失败条目数须可复算**，落 AC-15）；**不得以假数据 / 占位行填充失败项**。

#### 3.15.8 ⑦ 建议判据（AC-14 〜 AC-20，落 §7）

底稿 ＝ 拆解件 §7 的 **A-1 〜 A-7**；**编号按本文件现行 AC 序列分配 ＝ AC-14 〜 AC-20（共 7 条）**（**AC 计数 13 → 20**）。**判据全文 ＝ §7 AC-14 〜 AC-20 行**；**每条为可机械判负的三元组（判据 / 证据形式 / 判负形态）**；**证据未留档即视为未通过**。

#### 3.15.9 ⑧ 零外链资源与联网红线（**硬约束**）

- **零外链资源**：**页面仍离线自洽**（**不得引任何外链 CDN / 第三方脚本 / 字体 / 图片**，沿既有硬约束）。
- **联网红线**：**联网只发生在 feicui 服务端，且只读**（**GET / POST 取数，不上传任何数据**）；**前端不得直连源站**（**即使源站回 `Access-Control-Allow-Origin: *` 也不直连**——理由见 §3.15.3）。
- **数据不变判据**：**证明「数据未变」一律用内容指纹，禁用数据库文件 md5**（沿 §8 第 6 条）。
- **不改他线**：**不得动 `xiai/src/**`、`yinyuan/**`、`ctrl/**`；不占新端口；启停登记一律以 ctrl 面板为准**。

#### 3.15.10 交付缝（对外接口面，冻结）（**v1.8 新增**｜批 2 消费面）

> **性质**：本小节冻结 **批 1 的对外唯一交付缝 ＝ 批次包**，粒度到**外部程序可机械校验**。**批 2（写入 xiai 的通道）由另一会话承接**（§3.15.1 表下注 v1.8 追加）；**本文件只约束批 1**、**只引用**交接件 `feicui/docs/person-ingest-handoff-v0.1.md`（**不复制其全文、不另立第二真源**）。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**。

**1. 位置与文件（四件，缺一即非交付缝）**

- 批次包目录：**`feicui/exports/person_<yyyymmdd>_NN/`**（`NN` 两位、自 `01`）。
- 四个文件：**`manifest.json`** ＋ **`persons.jsonl`** ＋ **`relations.jsonl`** ＋ **`report.json`**。
- **既有 `exports/fb_*` 一字不动**（§3.15.4 只加法）；**同名 / 重复批次须幂等**（§3.15.5）。

**2. `manifest.json` 必含字段（钉值，可脚本校）**

| 必含字段 | 口径（钉值） |
| --- | --- |
| `schema_version` | **整数 `1`**（**本版钉为 `1`**；格式变更须升此值并走 §0.4） |
| 生成时点 | 批次生成时点（自带时区，ISO 8601 形如 `2026-10-10T…+08:00`） |
| 源端点 | 采集源端点清单；**须含全量口径 `pageRows=1000`**（`/service_yinpu/person/list` 一次取全，`total=570`） |
| 源侧 `total` | 源 `/person/list` 返回的 `total`（＝570） |
| 各文件行数 | `persons.jsonl` / `relations.jsonl` 的行数（**逐文件给**） |
| 字段名清单 | **数组**，**与 `persons.jsonl` / `relations.jsonl` 实际键面逐字一致**（**逐文件一份、键名逐字相同**） |

**3. JSONL 形态（硬约束）**：**一行一对象**、**UTF-8**、**无 BOM**、**字段名稳定**（同一批内同类对象键面一致）。

**4. 硬口径（外部可机械校验）**

| 口径 | 冻结值 |
| --- | --- |
| **幂等键** | **`source_person_id`** ＝ `personGrbsm`（9 位字符串，如 `907450151`）；**非空且批内唯一** |
| **溯源字段** | **`source`** / **`source_id`** / **`source_seqid`**（逐条随行落） |
| **繁简存法** | **繁体为正字段**（`name_full` / `native_place` / `biography` / 字号别名），**简体入 `*_chs` 副字段**；**零转换改写** |
| **抽取项标注** | 姓 / 名 / 字 / 号 / 别名 ＝ **规则抽取**，逐项标注 **`extraction='rule-based'`**；抽不准者一律落 `alias_names[]`；**不得表述为权威分类** |
| **生卒** | `birth_year` / `death_year` 为**整数或 `null`**；源侧 `?` / 空 ⇒ **`null`**；**禁特值**（**不得出现 `0` / `'?'` / 空串**） |
| **失败项** | **只进 `report.json`**（失败清单），**不得混入 `persons.jsonl`**（§3.15.7） |

- **关系面（`relations.jsonl`）**：逐条 `source_person_id`（宿主）/ `kind`（`印谱` / `印章`）/ `ref_id` / `name`（印谱名）或 `desc`（印章印文）/ `creator_type` / `as_book_id` / `has_image` / `image_key`（**默认只存键、不下载影像**，§9-R24）；**关联面只落 `graph/person` 的直接关联**（§9-R22）。
- **判据**：本交付缝的机械判据 ＝ **§7 AC-21 / AC-22**（**证据未留档即视为未通过**）。


#### 3.15.11 xiai 就绪导入包（对外导出面）（**v1.10 新增**｜Kevin 2026-10-10 三答）

> **性质**：本小节冻结 **feicui 侧的「导出 / 投递到交换目录」面**（**§3.15.10 批次包之外**、**面向 xiai 键面裁剪好的导入载荷**）。**口径真源 ＝ 交接件 `feicui/docs/person-ingest-handoff-v0.1.md` 第七节**（Zang 2026-10-10 写入）**，逐条照登**；**本文件只引用、不复制其全文、不另立第二真源**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**。

**Kevin 2026-10-10 三答（逐字口径）**

1. **按钮语义 ＝ 导出 / 投递到交换目录**：feicui 页加「**生成 xiai 就绪导入包**」按钮，产出**按 xiai 键面裁剪好**的导入载荷落到约定目录；**提交与审核仍在玺爱侧**（不破跨工程边界）。
2. **字 / 号 / 别名载荷形态 ＝ 降为 `string[]`（只传 `value`），但保留 `extraction` 标注、去掉 `from`**；**允许 xiai 侧扩属性，走它自己的规范流程**。
3. **审核门维持**：导入先落 `xiai_person_imports`（`PENDING`），**管理员在玺爱批量采纳后才成正式印人**（沿 §3.15.1 G-2）。

**1. 按钮与端点（additive、不动 E1 〜 E7 与 §3.15.3 的 P1 〜 P4）**

| # | 方法 / 路径 | 语义 | 要点 |
| --- | --- | --- | --- |
| **P5** | `POST /api/persons/import-package` | **生成「xiai 就绪导入包」**（按源批次裁剪 → 落交换目录 → 回批次号与计数） | **导出 / 投递**语义；**不提交 xiai、不写 xiai 任何文件、不调云函数**（跨工程边界，见本文第 5 条）；**响应给出 `batch_id` 与三文件行数** |
| **P6** | `GET /api/persons/import-packages` | **导入包列表（含回执读数）** | 逐包给**行数 / 键面 diff / 幂等键唯一计数**；**只读** |

- **按钮落点**：**§3.15.2「采集区」**新增「**生成 xiai 就绪导入包**」按钮（**触发 P5**）；**界面文案简体**（feicui 侧）。
- **错误码纪律**：**沿 §3.15.3**（**一律结构化 JSON、绝不返回 HTML 错误页**；**禁止以 `200` + 空冒充**）。
- **CORS**：**沿 §3.15.3 白名单**（**仅 `http://127.0.0.1:5195` / `http://localhost:5195`**；**不放开 `*`**）。

**2. 产物目录与三文件（冻结）**

- 产物目录：**`feicui/exports/person_import_<batch_id>/`**（`<batch_id>` ＝ §3.15.5 批次号形态；**位于 feicui 自有树内、gitignored**；**不写 xiai 仓任何文件**）。
- 三个文件：
  1. **`person_imports.jsonl`（主交付）**——**严格限于 xiai 现行 18 键**（见第 3 条，**可直接提交**）；三桶降为 `string[]`；生卒整数或 `null`；`source` / `source_id` 原样；`source_person_id` 为幂等键。
  2. **`person_imports_extraction.jsonl`（sidecar）**——**待 xiai 扩键面后并入**；`source_person_id` ＋ **`courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction`**（**与对应值等长的数组**，元素恒 `'rule-based'`）；**不含 `from`**（按 Kevin 裁定删除）。
  3. **`manifest.json`**——必含项见第 4 条。
- **JSONL 形态**：**沿 §3.15.10 第 3 条**（**一行一对象 / UTF-8 / 无 BOM / 字段名稳定**）。

**3. 主交付 ＝ 严格 xiai 键面（逐字 18 键，一个不多、一个不少）**

`batch_id` / `source` / `source_person_id` / `name_full` / `family_name` / `given_name` / `courtesy_names` / `art_names` / `alias_names` / `birth_year` / `death_year` / `native_place` / `native_place_chs` / `biography` / `biography_chs` / `nationality` / `cbdb_id` / `source_id`

- **键面来源**：xiai 仓 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`（**跨仓契约只引用、不复制其代码**；**本文件不另立第二真源**）。
- **必须裁剪**：feicui 侧 `persons.jsonl`（§3.15.10）一行 **32 键** ⇒ **主交付须裁到上述 18 键**；**多余键（如 `source_seqid` / `name_full_chs` / `nationality_chs` / `nationality_code` / `spell` / `initial` / `flag` / `notes` / `raw_json` 等）一律不得进主交付**（**直传 ⇒ xiai 侧 `INVALID_FIELD`「载荷含未知字段」＋ 零写入**）。
- **三桶形态**：xiai 侧 `asArray()` 走 `text(item)`、**期望 `string[]`** ⇒ 主交付的 `courtesy_names` / `art_names` / `alias_names` **必须为 `string[]`（只 `value`）**（**不得**传 `[{value,kind,extraction,from}]`，否则落成 `"[object Object]"`）。

**4. `manifest.json` 必含项（钉值，可脚本校）**

| 必含项 | 口径（钉值） |
| --- | --- |
| `schema_version` | 整数（**本版钉为 `1`**；格式变更须升此值并走 §0.4） |
| 源批次 | 生成该导入包的 §3.15.5 批次号 |
| 生成时点 | 自带时区（ISO 8601，形如 `2026-10-10T…+08:00`） |
| 行数 | `person_imports.jsonl` / `person_imports_extraction.jsonl` 行数（**逐文件给**） |
| 键面清单 ＋ **键面 diff** | 主交付实际键面清单 ＋ **与 xiai 18 键面的 diff（多余键必须为 `0`）** |
| 幂等键计数 | `source_person_id` **唯一计数**（**＝ 行数**） |
| sidecar 说明 | 说明 extraction 元数据暂以 sidecar 存放（**待 xiai 扩键后并入**） |

**5. 跨工程边界（硬约束）**

- **feicui 不得写 xiai 任何文件**；**不得调 xiai 云函数 / 不得做任何 CloudBase 写操作**（沿 §3.15.1 表下注 v1.8 追加）。
- **提交与审核不在 feicui 侧（审核门维持）**：导入先落 `xiai_person_imports`（`PENDING`），**管理员在玺爱批量采纳后才成正式印人**（沿 §3.15.1 G-2）。
- **交换方式**：**xiai 侧按上述目录只读消费**（本地路径约定）；如改为中立交换目录，**一句话可改**。

**6. 两条外部依赖（只登记、不代写；归 xiai 侧按其自己的规范流程）**

| # | 依赖 | 归属 |
| --- | --- | --- |
| **D-1** | **xiai 侧需扩 3 个键**（`courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction`） | **归另一会话按其自己规范流程**（`xiai/docs/xiai.spec.md` §1.3）；**本文件只引用**；**扩键面之前，主交付 `person_imports.jsonl`（18 键）已可正常提交**，extraction 元数据暂以 sidecar 存放 ⇒ **不阻塞** |
| **D-2** | **xiai 侧提交需可验证令牌**（`submitPersonImport` 的 `imported_by` 由**服务端从令牌派生** `uid`；feicui 侧无可验证令牌） | ⇒ **提交动作不在 feicui 侧**（**只能由玺爱侧提交**）；**本文件只登记、不代写** |

- **判据**：本小节的机械判据 ＝ **§7 AC-24**（**证据未留档即视为未通过**）。

> **§3.15.11 升版注（v1.11｜D-1 回执照登：主交付键面 18 → 21）**：**来源 ＝ xiai 线回执（D-1 已落）＋ `xiai/docs/xiai.spec.md` v1.57（§3.54.19 ＋ §4.1.16 追加注 ＋ AC-507〜510；跨仓契约只引用、不复制其代码）**。**本注系 v1.11 新增**——**上方第 3 条（逐字 18 键）与第 4 条（键面 diff＝0）的原文逐字保留**，其「18」**一律已被本注取代为「21」**。

**① 主交付键面 18 → 21（逐字 21 键；顺序钉定——3 新键紧随各自值键之后）**：

`batch_id` / `source` / `source_person_id` / `name_full` / `family_name` / `given_name` / `courtesy_names` / **`courtesy_names_extraction`** / `art_names` / **`art_names_extraction`** / `alias_names` / **`alias_names_extraction`** / `birth_year` / `death_year` / `native_place` / `native_place_chs` / `biography` / `biography_chs` / `nationality` / `cbdb_id` / `source_id`（**共 21 键**；**加粗者为 v1.11 新增**，均**紧随各自值键（`courtesy_names` / `art_names` / `alias_names`）之后**）。

**② 三键语义与形态（D-1 回执逐字）**：**`courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction` 各为 `string[]`；与对应值数组等长**（↔ `courtesy_names` / `art_names` / `alias_names`）；**元素为非空字符串**；**值域不封闭——不得据 `'rule-based'` 硬校验**（今日恒 `rule-based`，未来可另有取值 ⇒ **不得把「值不是 `rule-based`」判负**）。

**③ 缺键不拒收（加性 / 可选 / 不破坏）**：**不提供这 3 键的 18 键形态载荷仍可直接提交**（**不得因缺键拒收**）；**仅在提供了这 3 键时**才校等长与元素非空。

**④ 违形态由 xiai 侧判 `INVALID_VALUE` ＋ 零写入**：**形态校验与判定在 xiai 侧（写入前）**——feicui 侧**只负责产出形态合规的主交付**；**本文件不代为判定 xiai 侧写入结果**；**`reason` 沿 xiai 侧既有冻结表、零新增**（**归 xiai 侧口径**）。

**⑤ 采纳后不落 person 行**：**3 键只留导入行（`xiai_person_imports`）作溯源**；**管理员采纳生成 `xiai_persons` 行时不带这 3 键**（沿 `xiai.spec.md` §3.54.19 ④；**一句话可改**）。

**⑥ `person_imports_extraction.jsonl` 降为「派生冗余件（兼容保留）」**：**该 sidecar 与主交付内的 3 个 extraction 键是同一计算结果的两种导出**（今 3 键已并入主交付键面 21）⇒ **sidecar 不再是第二真源**，**降为派生冗余件、兼容保留**（**保留以兼容旧消费者 / 留存对账**；**正式面 ＝ 主交付内的 3 键**）。

**⑦ `manifest.json` 必含项随动**：第 4 条的「**与 xiai 18 键面的 diff（多余键必须为 `0`）**」**随动为「与 xiai 21 键面的 diff（多余键必须为 `0`）」**；**键面清单按 21 键核对**；**sidecar 说明**改注为「**派生冗余件（兼容保留）；extraction 元数据已并入主交付键面**」。

**⑧ 落地状态 ＝ 已定、落地中（由 Kong 执行）**；**提交由 xiai 侧写一次性脚本、待云函数重部署后执行**（**属 xiai 侧动作，不在 feicui 侧**）；**本注不含任何「本轮已通过」结论**。

#### 3.15.12 关联面范围裁定（**v1.11 新增**｜Kevin 2026-10-10：本轮先只落印人本体）

> **性质**：本小节为 **v1.11 追加**（**置于 §3.15.11 之后、`## 4.` 之前**）；**登记 Kevin 2026-10-10 裁定**，**逐条照登、不自行发明**。**上方 §3.15.5 / §3.15.6 / §3.15.10 与 §9-R22 / §9-R24 的原文一律逐字保留**；**本裁定为新口径（非既有条款改写）**。

**裁定（Kevin 2026-10-10，逐字口径）**：**关联面本轮先只落印人本体**。

- **本轮范围（硬口径）**：**本轮交付「印人本体」**（`persons` / 主交付 `person_imports.jsonl` 的印人字段面）；**关联面（印人 → 印谱 / 印章，共 1650 条）本轮不导入**。
- **数据留痕（不丢）**：**1650 条关联留在 feicui 侧**——`feicui/exports/person_20261010_01/relations.jsonl`（**留在原处、可复跑、数据不丢**）；**feicui 侧不删、不移、不改该文件**。
- **关联作为独立需求另开**：**「关联面（含是否导入、导入粒度、是否递归到印章 / 印谱详情）」作为一独立需求另行立项**（**不在本轮**）；**立项时随该需求的 §0.4 流程重新登记其口径与判据**。
- **与既有条款的关系**：**§3.15.5（批次包含 `relations.jsonl`）/ §3.15.6（关联面只落 `graph/person` 直接关联）/ §3.15.10（关系面 `relations.jsonl`）原文一字不改**——**批次包内的 `relations.jsonl` 照常产出（数据留在 feicui 侧）**；**本裁定只约束「是否把关联导入 xiai」，不改批次包本身**。**导入包（`person_import_<batch_id>/`）本就不含关联面**（主交付 ＝ 印人字段面 21 键）⇒ **与本裁定不冲突**。
- **§9 待裁面处置**：**R22（关联是否递归）/ R24（印章影像是否下载）** 属**关联面子问题** ⇒ **本轮随本裁定收口为「挂起 / 随关联独立需求另开时再议」**（**保号留行、状态列另注**，见 §9）。
- **判据面**：**本裁定不新增 AC**（**§7 AC 计数仍 24 条**）——**「只落印人本体」的可机械校验面 ＝ 主交付 `person_imports.jsonl` 的行键集 ⊆ 21 键**（**关联字段不在 21 键内**），**已由 AC-24 三态判据的第 ① 态承载**。
- **落地状态 ＝ 已定、落地中（由 Kong 执行）**；**本小节不含任何「本轮已通过」结论**。


#### 3.16 印谱（item）采集（外部印谱数据源采集线）（**v1.12 新增**｜只定口径 / 契约形状 / 存储 / 批次 / 判据，不定实现）

> **落位声明**：本小节为 **v1.12 追加**（**新增小节，置于 §3.15 及其全部子节之后、`## 4. 数据层演进` 之前**）。**§3.1 〜 §3.15 的节标题、表、条文与各版表下注原文逐字未改**（**唯一新增 ＝ 本小节 ＋ §7 的 AC-25 〜 AC-32 八行 ＋ AC-23 的原位改写（页签 2 → 3）＋ §7 计数留痕（v1.12）一条 ＋ §9 的 R25 〜 R28 四行 ＋ §9 计数留痕（v1.12）一条 ＋ §10 本版行**）。
> **（v1.14 落位声明｜Q5 端点登记 ＋ 重建幂等口径）**：**本版对 §3.16 追加 Q5（`POST /api/items/package`）契约（§3.16.3）＋ 补「重建幂等」口径（§3.16.5）＋ §7 新增 AC-33**（**收口 spec/实现分叉：Kong 实现中 additive 追加的第五端点未入 v1.12 规范**）。**§3.16.1 ～ §3.16.2 / §3.16.4 / §3.16.6 ～ §3.16.9 原文逐字未改**（**唯一改动面 ＝ §3.16.3 表追加 Q5 行 ＋ §3.16.3 v1.14 注 ＋ §3.16.5 重建幂等句 ＋ §7 AC-33 ＋ §7 / §9 计数留痕 ＋ 表头「版本」行 / 「本版硬约束（v1.14）」行 ＋ §10 本版行**）。

> **（v1.13 落位声明｜采集口径偏离）**：**本节 §3.16.6（⑤ 采集口径）原位改写**、**§3.16.8（⑦ 跨工程边界 ＋ item↔person sidecar）随动**、**§7 的 AC-28 / AC-31 原位改写**；**§3.16 其余小节（含 §3.16.1 的 Kevin 门控四答逐字口径）原文逐字未改**（**唯一改动面 ＝ §3.16.6 换采集口径 ＋ §3.16.8 `source_face` 取值集合随动 ＋ AC-28 / AC-31 原位改写 ＋ §3.16.1 表下注 ② / §3.16.3 Q1 / §3.16.5 manifest 必含三处加 v1.13 注随动 ＋ §7 计数留痕（v1.13）一条 ＋ §9 计数留痕（v1.13）一条 ＋ §10 本版行 ＋ 表头「版本」行 / 「本版硬约束」行**）。**本档系对 v1.12 旧采集口径（「列表 1 次 ＋ 逐本 detail、不采 `graph/book`」）的正式偏离**，**旧句原文逐字保留并标「已被 v1.13 取代」**（**系原位改写、非「既有条款自动失效」**）；**理由 ＝ 实测限流**（见 §3.16.6）。
> **（v1.15 落位声明｜§3.17 印章（seal）采集 新增 ＋ AC-23 页签随动 3 → 4）**：**本版新增 §3.17（置于 §3.16 及其全部子节之后、`## 4. 数据层演进` 之前）＋ §7 新增 AC-34 〜 AC-46 ＋ 原位改写 AC-23（页签集合 3 → 4）＋ §9 新增 R29 〜 R32**。**§3.16.1 〜 §3.16.9 原文逐字未改**（**唯一随动 ＝ §3.16.2 加 v1.15 追注（页签集合 3 → 4）＋ §3.15.2 v1.9 注加 v1.15 追注 ＋ §7 / §9 计数留痕 ＋ 表头「版本」行 / 「本版硬约束（v1.15）」行 ＋ §10 本版行**）。
> **口径真源**：**本小节逐条照登 Zang 2026-10-10 拆解件 `feicui/docs/item-ingest-draft-v0.1.md`**（**含实测源契约、Kevin 门控四答、批 1 / 批 2 范围、字段映射表、建议判据**）；**不自行发明、不改与之冲突的口径**。
> **性质**：**本小节只写口径 / 契约 / 判据**；**不含落地 · 验收结论、不含任何「实现现状」读数**（**落地属「已定、落地中（由 Kong 执行）」、验收归 Neng**）。**联网口径红线**：**联网只发生在 feicui 服务端、且只读**（§3.16.9）。**归属**：**批 2（item 模型 / 集合名 / 导入通道）归 xiai 线**（Kevin 2026-10-10 裁定，见 §3.16.1 I-3）。

##### 3.16.1 逐字口径与范围（Kevin 门控四答 I-1 〜 I-4，**照登不改写**）

| # | 裁定（Kevin 2026-10-10 逐字口径） |
| --- | --- |
| **I-1** | **item 范围 ＝ 全集 1742 本**（新采 `book/list` 全量）——「item 是『印谱』实体表，不应只装印人关联子集」 |
| **I-2** | **采集深度 ＝ 列表 ＋ detail（不采 graph）**：有结构化责任者（`creatorList` / `titleList` / `itemList` / `bookDonor`），**无印人关联面** |
| **I-3** | **模型与通道归属 ＝ xiai 线**：本线出拆解草案 ＋ 采集 ＋ xiai 就绪包；**他们定 item 模型、集合名与导入通道**（沿用 person 三段式：暂存 → 审核 → 定稿） |
| **I-4** | **印谱 ↔ 印人关联 ＝ 随包交付 sidecar**（`item ↔ person`：`creatorType` ＋ `personGrbsm`），**是否入 xiai 由他们定** |

**表下注（v1.12 追加）**：① **本小节（§3.16）只覆盖批 1（feicui 侧）**；**批 2（item 模型 / 集合名 / 键面 / 导入通道 / 落 xiai）不在本文件范围**（**归 xiai 线**；批 2 的入口与口径**由本线出交接件**，**本文件只引用、不另立第二真源**）；② **I-2 与 I-4 的一致化（实测支撑，非自行发明）**：**不采 `graph/book` 也能出关联**——**`book/detail` 的 `creatorList[]` 直接给 `personGrbsm`**（实测 `愚公自用印存`：`[{creatorType:'辑', creatorRole:'creator', creatorRelator:'edt', creatorName:'李鐘', personGrbsm:'907568497'}, …]`）；另可用**既有印人侧关联**（`person_relations` 的 `kind='印谱'`，1349 行 / 去重 932 本，含 `as_book_id` / `creatorType`）**互补**，经 `asBookId ↔ seqid` 映射接入；sidecar 每行**标注来源面**（`book_detail.creator_list` / `person_graph`）。

**（v1.13 注｜采集口径偏离，非「既有条款自动失效」）**：**本表下注 ② 中「不采 `graph/book` 也能出关联」「`book/detail` 的 `creatorList[]` …… 主来源」「sidecar 每行标注来源面（`book_detail.creator_list` / `person_graph`）」的表述已被 v1.13 取代**——**v1.13 起关联主源改 `graph/book/<seqid>`（`source_face='book_graph'`），既有 `person_relations` 为 `source_face='person_graph'`，`book/detail` 降 best-effort（`source_face='book_detail'` 仅在其开启时出现）**；**依据 ＝ 实测限流**（`book/detail` 严限流 ⇒ 逐本 detail 不可行；`graph/book` 健康且同样给四要素 `item / creatorType / name / personGrbsm`）。**原句逐字留存于快照 `docs/versions/feicui.spec.v1.12.md` §3.16.1**（**系原位改写、非「既有条款自动失效」**）。

##### 3.16.2 ① 页签与路由 `/items`

- **页签**：**`feicui/web` 首页导航新增【印谱采集】页签**（**第三页签**；**与【印谱解析】【印人采集】并列**）。
- **路由**：**新增 `/items`**；**history base 仍须取 `import.meta.env.BASE_URL`**（**不得写死 `/`**；沿 §3.15.2 G-1 教训）。
- **可达性**：**经 5195 直连**与**经 5164 的 `/feicui/items`**（**Vite proxy `/feicui` → `http://127.0.0.1:5195`，§6.4 已登记**）**均可达**且 `location.href` **不回落**首页。
- **页面结构**：**采集区**（触发同步 / 进度 / 上次结果 / 批次列表）、**列表区**（1742 条；分页 / 筛选）、**详情区**（item 本体字段；责任者 list；`raw_json` 不直接上屏）。**界面文案简体**（feicui 侧）；**源数据一律按原文呈现，同时展示繁 / 简两版字段**（§3.16.7）；**不得本地改写源数据**。
- **顶部结构 / tabbar 位置**：**沿 §3.15.2 v1.9 注**（**固定页眉 ＋ 标题区；tabbar 在 `main` 内、`RouterView` 之前、不在页眉内；固定页眉不得遮挡内容**）。**机械判据 ＝ §7 AC-23（v1.12 原位改写后为三项页签）**。
> **（v1.15 追注｜页签集合随动 3 → 4）**：**v1.15 起页签集合为四项**（【印谱解析】/【印人采集】/【印谱采集】/**【印章采集】**，第四项见 §3.17.2）；**本行「（v1.12 原位改写后为三项页签）」已被 v1.15 取代**（**原文逐字保留、不重写**）；**机械判据 ＝ §7 AC-23（v1.15 原位改写后为四项页签）**。**系原位改写、非「既有条款自动失效」**。
- **后端不可达**：**沿用既有「未连接」横幅口径**（§3.9 / §3.6 表下注），**不得以假数据填充**（**无假数据**硬约束）。

##### 3.16.3 ② 新端点契约（**v1.12 时点＝四个 Q1 〜 Q4；v1.14 追加 Q5（additive）⇒ 现共五个**）（`feicui/server`，端口 **5196**；**additive、不动 E1 〜 E7 与 §3.15.3 / §3.15.11 的 P1 〜 P6**）

| # | 方法 / 路径 | 语义 | 要点 |
| --- | --- | --- | --- |
| **Q1** | `POST /api/items/sync` | **拉全量并落库**（`book/list` `pageRows=3000` 一次取全 1742 → 逐本 `book/detail/<seqid>` → 归一化 → 落本库 → 产就绪包） | **可断点续跑**；**礼貌限速**；**本轮不采 `graph/book`**（I-2）；**触发形态 ＝ 手动按钮**（§9-R23 同型待裁）；**响应给出批次号与计数** |
| **Q2** | `GET /api/items` | **列表（分页 / 筛选）** | 分页与筛选参数**形状随实现**；**不得把业务真值放进接口层缓存**（沿 §3.2 S-4） |
| **Q3** | `GET /api/items/{seqid}` | **单本 item（详情 ＋ 责任者 sidecar）** | `{seqid}` ＝ **`seqid`（内部键 / 稳定外部键）**；未命中 ⇒ **404** |
| **Q4** | `GET /api/items/batches` | **批次列表（含回执读数）** | 逐批次给**计数 / 覆盖率 / 失败清单引用** |
| **Q5**（**v1.14 追加**） | `POST /api/items/package` | **从本库重建 xiai 就绪包**（目录 `feicui/exports/item_import_<batch_id>/`：`items.jsonl` ＋ `item_creators.jsonl` ＋ `manifest.json`）；**不联网采集**（**与 CLI `package` 共用同一实现**） | **入参**＝查询参数**仅白名单 `batch_id`（可选；缺省＝库内最新批次，按 `batch_id` 降序取首）**；**未白名单查询参数 ⇒ 400**（`UNSUPPORTED_PARAM`，结构化 JSON）；**给出 `batch_id` 但批次不存在 ⇒ 404**（`BATCH_NOT_FOUND`）；**未给 `batch_id` 且库内无任何批次 ⇒ 404**（`NO_BATCH`）；**其余生成失败 ⇒ 409**；**响应＝就绪包摘要**（`batch_id` / `package_dir` / `rows` / `creators_rows` / `key_face_status` / `detail_policy` / `checks` / `content_fingerprint` / `generated_at` …）；**零联网**（**不调任何源端点**）＋ **不写 xiai 任何文件**（**只产 feicui 自有树内 gitignored 产物**） |

> **（v1.13 注｜Q1 采集链路随 §3.16.6 改口径）**：**Q1（`POST /api/items/sync`）的采集链路按 §3.16.6（v1.13）读**——**item 本体全部取自 `book/list` 一次全量**（**不再逐本 `book/detail` 取本体**）；**item↔person 关联主源改 `graph/book/<seqid>`**（`source_face='book_graph'`）；**`book/detail` 降为 best-effort（默认关）**。**Q1 行「要点」列原句「本轮不采 `graph/book`（I-2）」已被 v1.13 取代**（**原文逐字留存于快照 `docs/versions/feicui.spec.v1.12.md` §3.16.3**），**依据 ＝ 实测限流**（**系原位改写、非「既有条款自动失效」**）。

> **（v1.14 注｜Q5 `POST /api/items/package` 登记：spec/实现分叉收口）**：**v1.12 立本小节时仅列四个端点（Q1 〜 Q4）**；**Kong 在 §3.16 实现中 additive 追加了第五端点 `POST /api/items/package`**（**Neng 质检 OBS 指出 spec/实现分叉**）⇒ **本版据实现读数登记其契约、收口分叉**（**系登记既有实现、非新立需求**）。**语义**：**从 feicui 本库（`feicui/var/item_ingest.db`）重建 xiai 就绪包**（产物目录 `feicui/exports/item_import_<batch_id>/`：`items.jsonl` ＋ `item_creators.jsonl` ＋ `manifest.json`），**与 CLI `package` 共用同一实现**（`write_package_from_db`）。**入参**：**查询参数白名单 ＝ 仅 `batch_id`（可选；缺省 ＝ 库内最新批次，按 `batch_id` 降序取首）**；**请求体不参与**（**本端点一切入参走查询串**）。**错误码**（**一律结构化 JSON、绝不返回 HTML 错误页**，沿本小节错误码纪律）：**未白名单查询参数 ⇒ 400（`UNSUPPORTED_PARAM`）**；**给出 `batch_id` 但批次不存在 ⇒ 404（`BATCH_NOT_FOUND`）**；**未给 `batch_id` 且库内无任何批次 ⇒ 404（`NO_BATCH`）**；**其余生成失败 ⇒ 409**。**响应**＝就绪包**摘要**（`batch_id` / `package_dir` / `rows` / `creators_rows` / `source_total` / `key_face_status`（＝`pending_xiai`）/ `idempotency_key` / `bridge_key` / `idempotency` / `coverage` / `creators_summary` / `checks` / `files` / `field_dict` / `field_dict_creators` / `detail_policy` / `content_fingerprint` / `generated_at`）。**两条红线**：**① 零联网**——**本端点不调任何源端点**（**不 `book/list` / 不 `graph/book` / 不 `book/detail`**，**仅读本库重建**）；**② 不写 xiai 任何文件**——**只产 feicui 自有树内（gitignored）产物，不写 `xiai/**`、不调任何云函数**（沿 §3.16.8 a）。**重建幂等**＝**仅时间戳变、两个 JSONL 字节不变**（**见 §3.16.5**）；**机械判据落 §7 AC-33**。

- **错误码纪律（硬要求，写入即判据）**：**一律返回结构化 JSON**，**绝不返回 HTML 错误页**（含 500 的未捕获异常页）；错误体须含机器可读字段（如 `error` / `detail`）与人类可读说明。**禁止以 `200` + 空 `items` 冒充「接口未实现」或「无数据」**（沿 §3.4 纪律 3）。**非白名单参数一律 400 结构化 JSON**（沿 §3.15.3 读口纪律）。
- **CORS**：**白名单仅 `http://127.0.0.1:5195` / `http://localhost:5195`**（§3.14.4 既有白名单）；**任何情况下不放开 `*`**。
- **HTTP 客户端**：**优先 stdlib（`urllib`）**，**避免改动 `server/requirements.txt` 的既有 freeze 口径**。
- **源端契约（照登拆解件 §2 实测；本版只登记、未复跑）**：

| 源端点 | 方法 | 入参 / 路径 | 用途 |
| --- | --- | --- | --- |
| `/service_yinpu/book/list` | POST | `{pageNum, pageRows, fullText, facetBookCbz, yearRange, facetBookDonator, orderField, orderType}` | **列表页**；**`pageRows=3000` 一次取全 1742 本**（`total=1742`） |
| `/service_yinpu/book/detail/<seqid>` | GET | **路径参数 ＝ `seqid`** | **详情（非同构：多出 `creatorList` / `titleList` / `itemList` / `bookDonor`）**；`/book/detail/<asBookId>` ⇒ **`code:404 数据或资源不存在`** |
| `/service_yinpu/book/facet` | POST | `{fullText}` | 分面（有无影像 / 年份 / 出版者 / 捐赠者 / 来源） |
| `/service_yinpu/graph/book/<seqid>` | GET | 路径参数 ＝ `seqid` | **印谱 ↔ 印人 ＋ 印章**（**本轮不采**，I-2）；`asBookId` 传入 ⇒ `印谱id错误` |
| `/service_yinpu/statistic/home` | GET | — | 站点计数（`bookCount=1742` / `personCount=570` / `sealCount=716`） |

- **响应信封**：`{data, total?, code:200, msg, status:true}`（**沿 §3.15.3**）。**限流陷阱（硬约束，跨线同源）**：超频回包 **HTTP 200 ＋ `code:"429"`（字符串）＋ `status:true` ＋ 无 `data`** ⇒ **任何「看到 200 就算成功」的写法都会把限流当采集成功**；**`detail` 类端点更敏感** ⇒ 必须**指数退避重试（5s → 60s）＋ 失败清单 ＋ 可断点续跑**（§3.16.6），**不得把 429 当成功**。

##### 3.16.4 ③ 存储口径（**独立 SQLite，不碰正式库、与 person 分库**）

- **新增独立 SQLite ＝ `feicui/var/item_ingest.db`**，表三张：**`items`** / **`item_creators`** / **`item_import_batches`**。
- **与 `var/person_ingest.db` 分库**（**互不干扰**）；**`yinpu.db`（印谱解析正式库）一字不碰**——**理由** ＝ 该库有「只能加法 + 红线判据」历史包袱，且印谱采集与印谱解析无数据依赖（§9-R25；**Zang 默认 · 一句话可改**）。
- **归一化落库须保留源原文与源键**（**不得丢源**）：`source_item_id` ＝ `seqid`（**幂等键**）；`as_book_id` ＝ `asBookId`（**桥接印人侧关联的键**）；`as_id` / `book_uri` ＝ `asId` / `bookUri`；另落 `raw_json`（列表行 ＋ 详情行，**不丢源**）。
- **只许加法**：**不得改既有端点语义、不动 `stamps` / `jobs` / `output/` / 既有 `exports/fb_*` / `exports/person_*` / `var/person_ingest.db`**。

##### 3.16.5 ④ 就绪包（xiai 就绪导入包，对外导出面）（**候选键面未裁**）

- **产物目录 ＝ `feicui/exports/item_import_<batch_id>/`**（**位于 feicui 自有树内、gitignored**；**不写 xiai 仓任何文件**）。
- **三个文件**：
  1. **`items.jsonl`（主交付候选）**——一行一对象、UTF-8、**无 BOM**；字段面 ＝ §3.16.7 的 item 本体（**键面未定前不裁剪**）。
  2. **`item_creators.jsonl`（sidecar）**——一行一对象（§3.16.8）。
  3. **`manifest.json`**——必含：`schema_version`（**本版钉 `1`**）、生成时点（ISO 8601 带时区）、源端点（**须含全量口径 `pageRows=3000`**）、源侧 `total`（**＝1742**）、**各文件行数**、**字段字典**、幂等键（`source_item_id`）**唯一计数**、覆盖统计、**`key_face_status: "pending_xiai"`**（**明示键面待 xiai 定**）。**（v1.13 追加必含项）**：**`detail_policy`**（**本批 `book/detail` 开关态**：**`off`（默认）** ｜ **`best_effort`**）＋ **因 detail 降级而缺失的三字段清单**（`creatorRole` / `creatorRelator` / `bookDonor`）＋ **`detail_unconfirmed` 计数**（**detail 未确认 / 失败条目数**）（§3.16.6 ④）。
- **形态（硬约束）**：**一行一对象 / UTF-8 / 无 BOM / 字段名稳定**（沿 §3.15.10 第 3 条）。
- **重建幂等（v1.14 追加）**：**由 `POST /api/items/package`（§3.16.3 Q5）或 CLI `package` 从本库重建就绪包时**，**仅 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 等时间戳变化**；**`items.jsonl` 与 `item_creators.jsonl` 的内容逐字节不变**（**只读本库、确定性重写**）⇒ **「点按钮重建就绪包」不得据时间戳变化判为数据变化**（**实测锚点**：连点两次，`created_at` 由 `15:39:16` → `15:42:03`，而两个 JSONL **逐字节未变**）。**判据落 AC-33**；**凡「数据未变」类判据一律用内容指纹 / 逐字节比对，禁用数据库文件 md5**（§8 第 6 条）。
- **交付缝定位**：**与 person 同型** —— feicui 出包、写 xiai 归他们；**本线不写 xiai 任何文件、不调云函数**（§3.16.8）。**候选键面未裁 ⇒ 不设「键面 diff＝0」判据**（**与 §3.15.11 的 person 就绪包不同**：person 侧键面已由 xiai 冻结为 21 键；**item 侧键面 `pending_xiai`**）⇒ **AC-31 只判 manifest 必含项齐备 ＋ `key_face_status: pending_xiai` 明示 ＋ 形态**。

##### 3.16.6 ⑤ 采集口径（**v1.13 原位改写**：本体全取 `book/list`；关联主源改 `graph/book`；`book/detail` 降 best-effort）

> **（v1.13 原位改写｜实测限流驱动，非「既有条款自动失效」）**：**本版对 v1.12 旧采集口径（「列表 1 次 ＋ 逐本 detail，**不采 `graph/book`**」）作正式偏离**；**理由 ＝ 实测限流**：**① `book/detail/<seqid>` 严限流**——**Kong 实跑日志 `5/10/20/40/60s` 退避反复**、**我方另测该端点间歇 `429`** ⇒ **按「逐本 detail 取本体」在 1742 本量级不可行**；**② `graph/book/<seqid>` 实测健康**——**2 s 间隔 3/3 成功**，**且同样给 `creatorType` ＋ `personGrbsm`**（实测 `graph/book/2214` ⇒ `{"creatorType":"辑","name":"吳隱","id":"907234486","type":"印人"}`）**即关联四要素（item / creatorType / name / personGrbsm）齐备**；**③ `book/list`（`pageRows=3000`）一次取全 1742 正常**。**口径真源 ＝ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §10（Zang 2026-10-10 采集口径偏离登记）**。**旧句原文逐字保留于下（逐句标「已被 v1.13 取代」）；系原位改写＝对旧口径的正式偏离，不是「既有条款自动失效」。**

- **① item 本体全部取自 `book/list` 一次全量（v1.13 生效）**：`pageRows=3000` **一次取全 1742 本**（**不得分页循环**，沿 §7.1 F-1 硬上界纪律）；**本体字段（§3.16.7 表中除 `donor` 外的全部）均从列表行落库**，**不再逐本 detail 取本体**。**旧句（已被 v1.13 取代）**：「**逐本 detail**：**每本调用一次** `book/detail/<seqid>`（**路径参数 ＝ `seqid`**，**不得用 `asBookId`**——`asBookId` 传入 ⇒ `code:404`）」——**已被 v1.13 取代**（本体改由 `book/list` 取；`book/detail` 降 best-effort）。
- **② item↔person 关联主源 ＝ `graph/book/<seqid>`（`source_face='book_graph'`）（v1.13 生效）**：**每本一次**（**路径参数 ＝ `seqid`**；`asBookId` 传入 ⇒ **`印谱id错误`**）；**与既有 `person_relations`（`source_face='person_graph'`，`kind='印谱'`，经 `asBookId ↔ seqid` 映射接入）合并去重**（§3.16.8）。**旧句（已被 v1.13 取代）**：「**不采 `graph/book`**（I-2 裁定）：**本轮不做关联图采集**；关联面由 §3.16.8 的 sidecar 承载」——**已被 v1.13 取代**（关联主源改 `graph/book/<seqid>`）。
- **③ `book/detail` 降为 best-effort（默认关，显式开关才开）（v1.13 生效）**：**仅补三字段** `creatorRole` / `creatorRelator` / `bookDonor`（**路径参数 ＝ `seqid`**，**不得用 `asBookId`**）；**慢速分片、失败进清单、不阻塞主交付**（manifest / report 如实登记）。
- **④ manifest / report 必含（v1.13 生效）**：`detail_policy`（**本批 `book/detail` 开关态**：**`off`（默认）** ｜ **`best_effort`**）＋ **因 detail 降级而缺失的三字段**（`creatorRole` / `creatorRelator` / `bookDonor`）＋ **`detail_unconfirmed` 计数**（**detail 未确认 / 失败条目数**）（落 **AC-31**）。
- **采集量（v1.13 新口径 · 预估，非实测）**：`book/list` 1 次 ＋ `graph/book` 1742 次（**主链路**）＝ **1743 请求**（按 **0.5–2 s / 请求** ≈ **15–60 min**）；**`book/detail` 默认 0 次**（**best-effort 开启时才增，慢速分片、失败不阻塞主交付**）。**旧句（已被 v1.13 取代）**：「**采集量**：**1743 请求**（`book/list` 1 次 + `book/detail` 1742 次）；按 **0.5 s / 请求** ≈ **20–25 min**（**预估，非实测**）」——**已被 v1.13 取代**（本体不再逐本 detail）。
- **礼貌限速**：**采集串行 ＋ 请求间隔**（**不得并发轰击源站**）。
- **断点续跑**：**采集进度须落盘**（本库或就绪包）；**中断后从断点续采**，**已完成条目不得重算重写**（幂等，落 AC-32）。
- **失败清单**：**失败条目进失败清单**（本库批次行 / 就绪包引用），**不得静默跳过**（**失败条目数须可复算**，落 AC-26）；**不得以假数据 / 占位行填充失败项**；**限流（`code:"429"`）必须指数退避重试（5s → 60s）并计失败**。

##### 3.16.7 ⑥ 字段面与归一化（**照登拆解件 §3**）

| 目标字段 | 源 | 规则 |
| --- | --- | --- |
| `source_item_id` | `seqid` | **幂等键**（原样字符串） |
| `as_book_id` | `asBookId` | 原样（**桥接印人侧关联的键**） |
| `as_id` / `book_uri` | `asId` / `bookUri` | 原样 |
| `category` | `bookFl` | 原样（「印谱」） |
| `title` / `title_chs` | `bookTitleZheng` / `…Chs` | 原样（**繁体为正、简体入 `*_chs`**） |
| `title_other` / `title_other_chs` | `bookTitleQt` / `…Chs` | 原样 |
| `volume_count` | `bookCs` | **整数或 `null`**（**不设特值**） |
| `date_text` | `bookCbLsjn` | 原样（纪年原文，如「清宣統二年」） |
| `date_year` | `bookCbGyjn` | **整数或 `null`** |
| `publisher` | `bookCbz` | 原样 |
| `abstract` / `abstract_chs` | `bookTynr` / `…Chs` | 原样（长文） |
| `abstract_title` | `bookTymc` | 原样 |
| `edition` | `bookBbx` | 原样 |
| `donor` | `bookDonor`（**详情独有**） | 原样 |
| `has_image` / `has_annotation` | 同名字段 | 布尔（实测 `hasImage=1` **1714** 本） |
| `language` | `bookYz` | 原样 |
| `misc.*` | `bookZzxs` / `bookCj` / `bookSk` / `bookSz` / `bookPsqk` | 原样（**低频字段收在一个子对象，不散落顶层**） |
| `raw_json` | 列表行 ＋ 详情行 | **保留源原文**（**不得丢源**） |
| `batch_id` / `updated_at` | — | 系统写 |

- **繁简存法（沿 §3.15.6）**：**繁体为正字段**（`title` / `abstract` / `title_other`），**简体入 `*_chs` 副字段**；**不做任何转换改写**（沿「不转用户输入」纪律）。
- **数值字段（硬口径）**：`volume_count` / `date_year` **为整数或 `null`**；源空 ⇒ **`null`**；**禁特值**（**不得出现 `0` / 空串**）（落 AC-29）。**注**：源侧 `bookCbGyjn` 空覆盖较大（非空 1076 / 1742）⇒ **空必须落 `null`、不得落 `0`**。
- **源字段覆盖（照登拆解件 §2；本版只登记、未复跑）**：`seqid` / `asBookId` / `asId` / `bookUri` / `bookFl` / `bookTitleZheng` / `bookTitleZhengChs` / `bookYz` / `hasImage` / `hasAnnotation` **1742/1742**；`bookCs` 1729；`bookCbLsjn` 1625；`bookCbGyjn` 1076；`bookTynr` / `bookTynrChs` 753；`bookTymc` 752；`bookBbx` 456；`bookCbz` 113；`bookTitleQt` / `…Chs` 92；`bookZzxs` / `bookCj` / `bookSk` / `bookSz` **28 / 19 / 14 / 9**；`bookPsqk` 1。
- **详情独有字段（照登）**：`creatorList[]`（**结构化责任者**：`seqid` / `creatorId` / `bookSeqid` / **`creatorType`**（辑 / 刻印…）/ `creatorRole`（`creator`）/ `creatorRelator`（`edt`）/ `creatorRef` / **`creatorName`** / **`personGrbsm`**）、`titleList[]`、`itemList[]`（卷册条目：`kmType` / `kmContent` / `kmLevel` / `kmUri` …）、**`bookDonor`**（藏家；实测恒「林章松」）。**覆盖待采集时实测**（抽样 4 本中 1 本 `creatorList` 非空）。

##### 3.16.8 ⑦ 跨工程边界 ＋ item↔person sidecar

**a. 跨工程边界（硬约束）**

- **feicui 不得写 xiai 任何文件**；**不得调 xiai 云函数 / 不得做任何 CloudBase 写操作**（沿 §3.15.1 表下注 v1.8 追加 / §3.15.11 第 5 条）。
- **提交与审核不在 feicui 侧（审核门维持）**：**item 的模型 / 集合名 / 导入通道 / 审核门归 xiai 线**（I-3）；**feicui 只出采集成果 ＋ 就绪包**。
- **交换方式**：**xiai 侧按上述目录只读消费**（本地路径约定）；如改为中立交换目录，**一句话可改**。

**b. sidecar `item_creators`（item ↔ person）**

| 字段 | 来源 | 规则 |
| --- | --- | --- |
| `source_item_id` | — | ＝ `seqid`（**回指 `items.jsonl`**） |
| `creator_type` | `creatorType` | 原样（辑 / 刻印…） |
| `creator_role` | `creatorRole` | 原样（`creator`） |
| `creator_relator` | `creatorRelator` | 原样（`edt`） |
| `creator_name` | `creatorName` | 原样 |
| `person_grbsm` | `personGrbsm` | 原样（**可回指印人侧 `source_person_id`**） |
| `source_face` | — | **关联来源面（v1.13 取值集合）**：`book_graph`（＝ `graph/book/<seqid>` 印人项，**主源**）｜ `person_graph`（＝ 既有 `person_relations`，**互补**）｜ `book_detail`（**仅 best-effort 开启 detail 时出现**）（**去重与可追溯用**） |
| `seq` | — | 序号（稳定排序） |

- **两路合并（v1.13 实测支撑）**：① **`graph/book/<seqid>` 的印人项**（形如 `{creatorType, name, id(＝personGrbsm), type:'印人'}`，**主源**，`source_face='book_graph'`）；② **既有印人侧关联**（`person_relations` 的 `kind='印谱'`，经 `asBookId ↔ seqid` 映射接入，**互补**，`source_face='person_graph'`）。**两路合并去重**；**每行标注 `source_face`**。**（v1.13 原位改写）**：**原 v1.12 旧句「① `book/detail` 的 `creatorList[]`（直接给 `personGrbsm`，**主来源**）；② 既有印人侧关联（`person_relations` 的 `kind='印谱'`，经 `asBookId ↔ seqid` 映射接入，**互补**）」的主源写 `book/detail`（`book_detail`）**已被 v1.13 取代**——**主源改 `graph/book`（`book_graph`），`book/detail` 降 best-effort（`source_face='book_detail'` 仅在其开启时才出现）**，**理由 ＝ 实测 `book/detail` 严限流 / `graph/book` 健康且同样给四要素（item / creatorType / name / personGrbsm）**。
- **三字段缺失（v1.13）**：**`graph/book` 缺 `creatorRole` / `creatorRelator`**（**改由 `book/detail` best-effort 补，缺则空**）；**关联的四要素（item / creatorType / name / personGrbsm）齐备 ⇒ sidecar 不受影响**（拆解件 §10）。
- **跨工程键桥**：`as_book_id`（`asBookId`，如 `0307`）**是印人侧关联用的键**；`source_item_id`（`seqid`）**是本库 / 就绪包的幂等键** —— **两者不同号、不得混用**（`book/detail` 用 `seqid`；`book/detail/<asBookId>` ⇒ `404`）。

> **⚠ 与已删 `from` 的关系（必须写明：二者不是同一概念）**：**`source_face` ＝ 关联来源面**（**v1.13 取值集合**：`book_graph` ｜ `person_graph`（**best-effort 开启 detail 时含 `book_detail`**），**用于去重与可追溯**）；**`from` ＝ 姓名抽取的源字段名**（person 侧 `[{value,kind,extraction,from}]` 三桶里的 `from`，**已被 Kevin 裁定删除**，见 §3.15.11 三答之② / §7 AC-24）。**二者语义无关、不得互相替代、不得据 `source_face` 的存在推断 `from` 应恢复**；**就绪包内两者均不存在于同一语义位**（item 侧无姓名三桶，person 侧 `from` 已删）。

##### 3.16.9 ⑧ 零外链资源与联网红线（**硬约束**）

- **零外链资源**：**页面仍离线自洽**（**不得引任何外链 CDN / 第三方脚本 / 字体 / 图片**，沿既有硬约束）。
- **联网红线**：**联网只发生在 feicui 服务端，且只读**（**GET / POST 取数，不上传任何数据**）；**前端不得直连源站**（**即使源站回 `Access-Control-Allow-Origin: *` 也不直连**——理由见 §3.15.3）。
- **数据不变判据**：**证明「数据未变」一律用内容指纹，禁用数据库文件 md5**（沿 §8 第 6 条）。
- **不改他线**：**不得动 `xiai/**`、`yinyuan/**`、`ctrl/**`；不占新端口；启停登记一律以 ctrl 面板为准**。
- **独立库隔离（硬约束）**：**采集全程只写 `var/item_ingest.db`**；`yinpu.db` 与 `var/person_ingest.db` 内容指纹**逐字节未变**（落 AC-30）。

---

#### 3.17 印章（seal）采集（外部印章数据源采集线）（**v1.15 新增**｜只定口径 / 契约形状 / 存储 / 批次 / 判据，不定实现）

> **落位声明**：本小节为 **v1.15 追加**（**新增小节，置于 §3.16 及其全部子节之后、`## 4. 数据层演进` 之前**）。**§3.1 〜 §3.16 的节标题、表、条文与各版表下注原文逐字未改**（**唯一新增 ＝ 本小节 ＋ §7 的 AC-34 〜 AC-46 十三行 ＋ AC-23 的原位改写（页签 3 → 4）＋ §7 计数留痕（v1.15）一条 ＋ §9 的 R29 〜 R32 四行 ＋ §9 计数留痕（v1.15）一条 ＋ §10 本版行；另 §3.15.2 v1.9 注 ＋ §3.16.2 对页签集合的 v1.15 追注随动**）。
> **口径真源**：**本小节逐条照登 Zang 2026-10-10 已实测的源契约 ＋ Kevin 三条裁定（裁定 A / B / C）**（**逐条照登、不自行发明、不改与之冲突的口径**）。
> **性质**：**本小节只写口径 / 契约 / 判据**；**不含落地 · 验收结论、不含任何「实现现状」读数**（**落地属「已定、落地中（由 Kong 执行）」、验收归 Neng**）。**联网口径红线**：**联网只发生在 feicui 服务端、且只读**（§3.17.9）。**归属**：**印章模型 / 集合名 / 导入通道归 xiai 线**（同 §3.16.1 的 I-3 口径）。
> **（v1.16 落位声明｜§3.17 影像面三态分桶 ＋ 共用窗口限流 ＋ 可机械判负面）**：**本版在 §3.17.6 ⑤ 加 v1.16 追注（共用窗口限流）＋ §3.17.8 a. 影像面加 v1.16 追加块（源侧缺图三态分桶 / 共用窗口限流 / 逐张台账 `width` · `height` · `bytes` · `tiff_sha256` ＋ 双档上限 / 放大尺寸判负保留 v1.15 原文并补定量依据）＋ §3.17.8 的 `NaN_` ref 状态口径原位改写（`source_missing` ⇒ `source_no_image`）＋ §7 新增 AC-47 〜 AC-52 ＋ §9 新增 R33 ＋ §9 计数留痕（v1.16）＋ 表头「版本」行 / 「本版硬约束（v1.16）」行 ＋ §10 本版行**。**§3.17.1 〜 §3.17.5 / §3.17.7 / §3.17.9 原文逐字未改**（**原位改写 ＝ §3.17.8 的 `NaN_` ref 状态口径 ＋ §7 AC-40 的同一记号，原文逐字留存于快照 `docs/versions/feicui.spec.v1.15.md`**）。
> **（v1.17 落位声明｜§3.17.8 影像面子因由二扩三 ＋ AC-47 族随动）**：**本版在 §3.17.8 a-v1.16 块的 `source_no_image` 子因行由「两类」原位扩为「三类」（新增子因（c）坏字节 `bad_bytes`）＋ `failed` 行原位改写为「收尾时 `failed` ＝ 0」＋ 判负形态随动 ＋ §3.17.8 a. 影像面加 v1.17 追加块（子因穷尽枚举三类 / `bad_bytes` 实例锚 `2_3609_1` / `failed` ＝ 0 理由）＋ §7 AC-47 原位改写为「`failed` ＝ 0」＋ §7 AC-48 证据形式由「两类子因计数」随动为「三类」＋ §7 新增 AC-53（承载 `bad_bytes` 实例归 `source_no_image` 面不在 `failed`）＋ §9 R33 行子因随动注（新增（c））＋ §9 计数留痕（v1.17）＋ §7 计数留痕（v1.17）＋ 表头「版本」行 / 「本版硬约束（v1.17）」行 ＋ §10 本版行**。**§3.17.1 〜 §3.17.7 / §3.17.9 原文逐字未改**（**原位改写 ＝ §3.17.8 a-v1.16 块的 `source_no_image` 子因行（两类 → 三类）与 `failed` 行（「空或仅瞬态且附重跑命令」→「＝ 0」）＋ §7 AC-47 / AC-48，原文逐字留存于快照 `docs/versions/feicui.spec.v1.16.md`**）。
> **（v1.18 落位声明｜§3.17 影像面逐张台账字段语义更正 ＋ AC-41 / AC-50 / AC-51 随动 ＋ AC-54 ＋ R34 ＋ 端点 mime 写清）**：**本版在 §3.17.8 ④ 逐张台账字段语义原位更正（`sha256` ＝ TIFF 字节的 sha256 ＝ 内容寻址键 / `bytes` ＝ TIFF 字节数 / 新增 `source_bytes` · `source_sha256` 源侧溯源 / 删去 `tiff_sha256` 键引用）＋ §3.17.8 加 a-v1.18 追加块（字段语义 ＋ 超 4 MiB 桶 6 张）＋ §3.17.5 成员 6 键面随动 ＋ §3.17.3 端点表追加 S6（`GET /api/seals/{seqid}/image/{kind}` ＝ `image/jpeg` 源 JPEG 缓存供缩略图）＋ §7 AC-41 / AC-50 / AC-51 原位改写（删「输入档 ≤ 1 MB」恒假判据 / `tiff_sha256` ⇒ `sha256`）＋ §7 新增 AC-54（超档逐行标记 / 不得自行降采样转码）＋ §9 新增 R34 ＋ §7 / §9 计数留痕（v1.18）＋ 表头「版本」行 / 「本版硬约束（v1.18）」行 ＋ §10 本版行**。**§3.17.1 〜 §3.17.3（S1 〜 S5） / §3.17.4 / §3.17.6 / §3.17.7 / §3.17.9 原文逐字未改**（**原位改写 ＝ §3.17.8 ④ 逐张台账字段语义行 ＋ §3.17.5 成员 6 ＋ §7 AC-41 / AC-50 / AC-51，原文逐字留存于快照 `docs/versions/feicui.spec.v1.17.md`**）。
> **（v1.19 落位声明｜AC-41 原位收窄 ＋ 源侧 ref 未命中 person 库记账口径 ＋ `_db_path` 观察项）**：**本版在 §7 AC-41 原位收窄（字面判负由「单张 > 4 MiB ⇒ FAIL」收窄为「未被逐行标记 `oversize_for_xiai_store` 的超档行 ⇒ FAIL」；超档允许、但必须逐行标记；已标记的超档行豁免本 AC；并写明与 AC-54 的分工）＋ §3.17.8 加 a-v1.19 追加块（① 源侧 `ref_id` 未命中 person 库记账口径（印主 8/438、篆者 1/403、边款篆者 6/11；属源侧引用未收录、不判负；`seal_links` 允许 `ref_id` 不命中 person 库但须在 `report.json` 给计数）＋ ② 端点响应顶层内部键 `_db_path` 观察项（三线对照 `GET /api/seals` / `/api/persons` / `/api/items` 顶层键相同 ⇒ 系共有惯例、非本线不一致；不立 R35））＋ §7 计数留痕（v1.19）＋ §9 计数留痕（v1.19）＋ 表头「版本」行 / 「本版硬约束（v1.19）」行 ＋ §10 本版行**。**§3.17.1 〜 §3.17.7 / §3.17.9 原文逐字未改**（**原位收窄 ＝ §7 AC-41，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md`**）。

##### 3.17.1 逐字口径与范围（源契约 ＋ Kevin 三条裁定，**照登不改写**）

| # | 裁定 / 事实（逐字口径） |
| --- | --- |
| **源端点 ①** | `POST /service_yinpu/seal/list`——**`pageRows=5000` ⇒ `total=3679` 一次全量**（**另支持 `auditStatus` 过滤**）；信封沿 §3.15.3 / §3.16.3 |
| **源端点 ②** | `GET /service_yinpu/seal/detail/<seqid>`——**与 list 不同构**：**list 独有 `*Chs` 字段；detail 独有 `sealYsXzLabel` / `sealYzRefId` / `auditUser`** |
| **源端点 ③** | `GET /service_yinpu/graph/seal/<seqid>`——**关联（印谱 / 印人 节点）**；**健康 8/8** |
| **裁定 A** | **范围 ＝ 全量 3679 枚**；**保留 `audit_status` 字段与分布统计**（实测 `1=2929` / `2=716` / `9=31` / `0=3`；**其中 `716` 恰等于站点 `statistic.sealCount`＝「已发布」子集**） |
| **裁定 B（v1.15 改口径｜Kevin 裁定：TIFF 直供 xiai 影像库）** | **影像 ＝ 全部直供 xiai 影像库（TIFF）**：印面 **3679**（`sealYtUrl`）＋ 印体释文 **2627**（`sealYtswUrl`）＋ 边款 **459**（`sealYzbkUrl`）≈ **6765 张**；**本侧取图走 IIIF**（`https://yin.fudan.edu.cn/iiif_proxy/api/char_proxy/<ref>` ⇒ 302 ⇒ JPEG；**只用原生裁切 `/full/0/default.jpg`、实测 160×149**；**禁止放大尺寸**）；⇒ **JPEG → TIFF 无损容器转换**（**不重采样、不二次有损编码**；**如实登记「IIIF 仅出 JPEG ⇒ 包内 TIFF 为无损容器转换，质量受源 JPEG 限制」**）；**入包形态镜像 xiai 影像库**（**`images/<sha256[:2]>/<sha256>.tiff`**；**包内不放 JPEG**）；**`NaN_` 开头的 ref 预期无图**（**登记「源侧无图」**） |
| **裁定 C** | **关联 ＝ 随包 sidecar** `seal_links.jsonl`（**印章 ↔ 印谱 ↔ 印人**） |
| **形製码表** | （**Zang 标定：每码 2 枚 × 0 冲突 ⇒ 纯函数**）`1=白文方印` `2=朱文方印` `3=白文圆印` `4=朱文圆印` `5=白文长方印` `6=朱文长方印` `7=白文椭圆印` `8=朱文椭圆印` `9=朱文异性印` `10=白文异性印`；**源侧原文为「异性」非「异形」——逐字照登** |
| **裁定默认（Zang 定，可裁）** | **`seal/detail` 默认关**（**形製标签已可本地码表派生 ⇒ 不再跑 3679 次 detail**）、降 best-effort（**仅 `sealYzRefId` / `auditUser`**）；**独立库 `var/seal_ingest.db`**（含影像台账表） |

**表下注（v1.15 追加）**：① **本小节（§3.17）只覆盖 feicui 侧**；**印章模型 / 集合名 / 键面 / 导入通道 / 落 xiai 不在本文件范围**（**归 xiai 线**；同 §3.16.1 I-3）；② **字段面实测（照登，本版只登记、未复跑）**：`seqid` **3679 唯一**（**幂等键**）；`sealYwSmwz`（＋`Chs`）**3679**；`sealYz`（印主）**2379**（**19 个值**）；`sealYzzkz` / `sealYzzkzId`（篆者）**2652**（10 个值）；`sealBk`（边款）**459**；`sealBkzkzId` **254**（21 个值）；`sealYsXz` **3035**（**644 行 `null` 合法**）；`asBookId` / `relatedBook` / `sealYtUrl` **3679**；`sealYtswUrl` **2627**；`sealYzbkUrl` **459**；**其余大多 `0` / `null`**；③ **桥接**：`graph/seal` 给的**印谱 id `1967` ↔ `var/item_ingest.db` 的 `source_item_id=1967` / `as_book_id=0113`**；**印章涉 19 种印谱全部命中 item 库**（落 AC-39）。

##### 3.17.2 ① 页签与路由 `/seals`

- **页签**：**`feicui/web` 首页导航新增【印章采集】页签**（**第四页签**；**与【印谱解析】【印人采集】【印谱采集】并列**）。
- **路由**：**新增 `/seals`**；**history base 仍须取 `import.meta.env.BASE_URL`**（**不得写死 `/`**；沿 §3.15.2 G-1 教训）。
- **可达性**：**经 5195 直连**与**经 5164 的 `/feicui/seals`**（**Vite proxy `/feicui` → `http://127.0.0.1:5195`，§6.4 已登记**）**均可达**且 `location.href` **不回落**首页。
- **页面结构**：**采集区**（触发同步 / 进度 / 上次结果 / 批次列表 / 「生成 xiai 就绪包」按钮）、**列表区**（3679 条；分页 / 筛选）、**详情区**（seal 本体字段；关联印谱 / 印人；`raw_json` 不直接上屏）。**界面文案简体**（feicui 侧）；**源数据一律按原文呈现，同时展示繁 / 简两版字段**（§3.17.7）；**不得本地改写源数据**。
- **顶部结构 / tabbar 位置**：**沿 §3.15.2 v1.9 注**（**固定页眉 ＋ 标题区；tabbar 在 `main` 内、`RouterView` 之前、不在页眉内；固定页眉不得遮挡内容**）。**机械判据 ＝ §7 AC-23（v1.15 原位改写后为四项页签）**。
- **后端不可达**：**沿用既有「未连接」横幅口径**（§3.9 / §3.6 表下注），**不得以假数据填充**（**无假数据**硬约束）。

##### 3.17.3 ② 新端点契约（**v1.15 时点＝四个 S1 〜 S4 ＋ additive 追加 S5**）（`feicui/server`，端口 **5196**；**additive、不动 E1 〜 E7 与 §3.15.3 / §3.16.3 的 P1 〜 P4 / Q1 〜 Q5**）

| # | 方法 / 路径 | 语义 | 要点 |
| --- | --- | --- | --- |
| **S1** | `POST /api/seals/sync` | **拉全量并落库**（`seal/list` `pageRows=5000` 一次取全 3679 → 关联走 `graph/seal/<seqid>` → **形製标签本地码表派生** → `seal/detail`（**默认关**）best-effort → 归一化 → 落本库 → 产就绪包 → 影像按裁定 B' 转 TIFF 直供入包） | **可断点续跑**；**礼貌限速**；**`seal/detail` 默认关**（§3.17.6③）；**触发形态 ＝ 手动按钮**（§9-R23 同型待裁）；**响应给出批次号与计数** |
| **S2** | `GET /api/seals` | **列表（分页 / 筛选）** | 读口分页用 `page` / `limit` / `has_more`（**`has_more == page*limit < total`**）；**不支持 `cursor` —— 传了必须 400，不得静默忽略**（沿 §3.15.3）；非白名单参数一律 400 结构化 JSON |
| **S3** | `GET /api/seals/{seqid}` | **单枚 seal（详情 ＋ sidecar）** | `{seqid}` ＝ **`seqid`（内部键 / 稳定外部键）**；未命中 ⇒ **404** |
| **S4** | `GET /api/seals/batches` | **批次列表（含回执读数）** | 逐批次给**计数 / 覆盖率 / 失败清单引用**；**UI 须分行展示「采集 run」与「最近 run（重放）」**（沿 §3.15.11 计数器纪律） |
| **S5**（**v1.15 追加**） | `POST /api/seals/package` | **从本库重建 xiai 就绪包**（目录 `feicui/exports/seal_import_<batch_id>/`：`seals.jsonl` ＋ `seal_links.jsonl` ＋ `manifest.json` ＋ `report.json` ＋ `images/` ＋ `images_manifest.jsonl`）；**不联网采集**（**从本库重建、零联网**） | **入参**＝查询参数**仅白名单 `batch_id`（可选；缺省＝库内最新批次）**；**未白名单查询参数 ⇒ 400**（`UNSUPPORTED_PARAM`，结构化 JSON）；**给出 `batch_id` 但批次不存在 ⇒ 404**（`BATCH_NOT_FOUND`）；**未给 `batch_id` 且库内无任何批次 ⇒ 404**（`NO_BATCH`）；**其余生成失败 ⇒ 409**；**响应＝就绪包摘要**；**两条红线 ＝ 零联网 ＋ 不写 xiai 任何文件** |
| **S6**（**v1.18 追加**） | `GET /api/seals/{seqid}/image/{kind}` | **取印章影像（二进制；供页面缩略图）** | 路径参数：`{seqid}` ＝ `seqid`、`{kind} ∈ {yt, ytsw, yzbk}`；**响应 `Content-Type` ＝ `image/jpeg`**——**服务的是源 JPEG 缓存（`var/seal_images/<kind>/<seqid>.jpg`），供页面缩略图**（**浏览器不渲染 TIFF**；**与包内 TIFF 交付面（§3.17.5 / §3.17.8）无关**）；**只读**（不触发采集 / 转换 / 写库）；未命中 / 文件不在盘 ⇒ **404**（`IMAGE_NOT_FOUND`）；非白名单 `kind` ⇒ **400**（`BAD_PARAM`）；一律结构化 JSON 错误体 |

- **错误码纪律（硬要求，写入即判据）**：**一律返回结构化 JSON**，**绝不返回 HTML 错误页**（含 500 的未捕获异常页）；错误体须含机器可读字段（如 `error` / `detail`）与人类可读说明。**禁止以 `200` + 空 `items` 冒充「接口未实现」或「无数据」**（沿 §3.4 纪律 3）。**非白名单参数一律 400 结构化 JSON**（沿 §3.15.3 读口纪律）。
- **CORS**：**白名单仅 `http://127.0.0.1:5195` / `http://localhost:5195`**（§3.14.4 既有白名单）；**任何情况下不放开 `*`**。
- **HTTP 客户端**：**优先 stdlib（`urllib`）**，**避免改动 `server/requirements.txt` 的既有 freeze 口径**。
- **源端契约（照登实测；本版只登记、未复跑）**：

| 源端点 | 方法 | 入参 / 路径 | 用途 |
| --- | --- | --- | --- |
| `/service_yinpu/seal/list` | POST | `{pageNum,pageRows,fullText,auditStatus,orderField,orderType}` | **列表页**；**`pageRows=5000` 一次取全 3679 枚**（`total=3679`）；**支持 `auditStatus` 过滤** |
| `/service_yinpu/seal/detail/<seqid>` | GET | **路径参数 ＝ `seqid`** | **详情（非同构：独有 `sealYsXzLabel` / `sealYzRefId` / `auditUser`；list 独有 `*Chs`）** |
| `/service_yinpu/graph/seal/<seqid>` | GET | 路径参数 ＝ `seqid` | **印章 ↔ 印谱 / 印人 节点**（关联面；**健康 8/8**） |
| `/service_yinpu/statistic/home` | GET | — | 站点计数（`sealCount=716` / `personCount=570` / `bookCount=1742`） |

- **响应信封**：`{data, total?, code:200, msg, status:true}`（**沿 §3.15.3**）。**限流陷阱（硬约束，跨线同源）**：超频回包 **HTTP 200 ＋ `code:"429"`（字符串）＋ `status:true` ＋ 无 `data`** ⇒ **任何「看到 200 就算成功」的写法都会把限流当采集成功**；**必须指数退避重试（5s → 60s）＋ 失败清单 ＋ 可断点续跑**（§3.17.6），**不得把 429 当成功**。

##### 3.17.4 ③ 存储口径（**独立 SQLite，不碰正式库、与 person / item 分库**）

- **新增独立 SQLite ＝ `feicui/var/seal_ingest.db`**，表四张：**`seals`** / **`seal_links`** / **`seal_import_batches`** / **`seal_images`**（**影像台账表**）。
- **与 `var/person_ingest.db` / `var/item_ingest.db` 分库**（**互不干扰**）；**`yinpu.db`（印谱解析正式库）一字不碰**——**理由** ＝ 该库有「只能加法 + 红线判据」历史包袱，且印章采集与印谱解析无数据依赖（§9-R29；**Zang 默认 · 一句话可改**）。
- **归一化落库须保留源原文与源键**（**不得丢源**）：`source_seal_id` ＝ `seqid`（**幂等键**）；`audit_status`（**保留源 `auditStatus` 原值**）；另落 `raw_json`（列表行 ＋ 详情行，**不丢源**）。
- **只许加法**：**不得改既有端点语义、不动 `stamps` / `jobs` / `output/` / 既有 `exports/fb_*` / `exports/person_*` / `exports/item_*` / `var/person_ingest.db` / `var/item_ingest.db`**。

##### 3.17.5 ④ 就绪包（xiai 就绪导入包，对外导出面）（**候选键面未裁**）

- **产物目录 ＝ `feicui/exports/seal_import_<batch_id>/`**（**位于 feicui 自有树内、gitignored**；**不写 xiai 仓任何文件**）。
- **六个成员**：
  1. **`seals.jsonl`（主交付候选）**——一行一对象、UTF-8、**无 BOM**；字段面 ＝ §3.17.7 的 seal 本体（**键面未定前不裁剪**）。
  2. **`seal_links.jsonl`（sidecar）**——一行一对象（§3.17.8）。
  3. **`manifest.json`**——必含：`schema_version`（**本版钉 `1`**）、生成时点（ISO 8601 带时区）、源端点（**须含全量口径 `pageRows=5000`**）、源侧 `total`（**＝3679**）、**各文件行数**、**字段字典**、幂等键（`source_seal_id`）**唯一计数**、覆盖统计、**`audit_status` 分布统计**（**裁定 A**）、**`key_face_status: "pending_xiai"`**（**明示键面待 xiai 定**）、**`detail_policy`**（**本批 `seal/detail` 开关态**：**`off`（默认）** ｜ **`best_effort`**）＋ **影像摘要**（张数 / 总字节 / 无图计数）。
  4. **`report.json`**——计数 ＋ 覆盖率 ＋ **失败清单**（**不得静默跳过**）＋ **影像三态分桶计数**（`ok` / `source_no_image` / `failed` 各计数）＋ **`source_no_image` 按 ref 前缀聚合的清单 ＋ 计数 ＋ 样例 `seqid`**（**v1.16 追加**；**源侧缺图是源侧事实，不得写成 feicui 采集失败**）。（**v1.16 判据落 AC-47 / AC-48**。）
  5. **`images/`**——**影像二进制（TIFF，镜像 xiai 影像库形态）**（**`images/<sha256[:2]>/<sha256>.tiff`**；**sha256 ＝ TIFF 字节**；**包内不放 JPEG**；**印面 / 印体释文 / 边款**三类；按裁定 B' 全部 TIFF 直供）。
  6. **`images_manifest.jsonl`**——**唯一索引、一行一图**（§3.17.8：`seqid` / `kind ∈ {yt, ytsw, yzbk}` / `source_ref` / `source_url` / `sha256`（**＝ TIFF 字节的 sha256 ＝ 内容寻址键**）/ `bytes`（**＝ TIFF 字节数**）/ `source_bytes` / `source_sha256`（**＝ 源 JPEG 侧、溯源用**）/ `width` / `height` / `source_format` / `container` / `conversion` / `upscaled:false` / **`oversize_for_xiai_store`（boolean，超 4 MiB 标记）** / **`status ∈ {ok, source_no_image, failed}`**（**v1.18 原位更正**：**实物 `images_manifest.jsonl` 仅含 `ok` 行、无 `status` 键——三态计数落 `report.json` / 台账 `seal_images`**）。（**v1.16 追加三态 `status`**；**（v1.18 原位更正｜以包内实物为准）**：**原 v1.16 键面列了 `sha256` / `tiff_sha256` / `bytes` 且未列源侧字段——包内实物 `images_manifest.jsonl` 键面恰为 `[bytes, container, conversion, height, kind, seqid, sha256, source_format, source_ref, source_url, upscaled, width]`（无 `tiff_sha256` 键）；`sha256` 即 TIFF 字节的 sha256（内容寻址键、＝文件路径名），`bytes` 即 TIFF 字节数**；**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §3.17.5；系原位更正，不是「既有条款自动失效」**）。**判据落 AC-47 / AC-48 / AC-51 / AC-52 / AC-54**。）
- **形态（硬约束）**：**一行一对象 / UTF-8 / 无 BOM / 字段名稳定**（沿 §3.15.10 第 3 条）。
- **重建幂等（v1.15）**：**由 `POST /api/seals/package`（§3.17.3 S5）或 CLI `package` 从本库重建就绪包时**，**仅 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 等时间戳变化**；**`seals.jsonl` 与 `seal_links.jsonl` 的内容逐字节不变**（**只读本库、确定性重写**）⇒ **「点按钮重建就绪包」不得据时间戳变化判为数据变化**。**判据落 AC-42**；**凡「数据未变」类判据一律用内容指纹 / 逐字节比对，禁用数据库文件 md5**（§8 第 6 条）。
- **重建不得删或重转影像（硬约束）**：**重出包（`/api/seals/package` 或 CLI `package`）不得删除 `images/`、不得重转既有影像**——**包内既有 TIFF 须按 `images_manifest.jsonl` 的 `sha256` 复用（已存在则跳过）**，**不得清空后重下 / 重转、不得因重建而丢图或改图**。

##### 3.17.6 ⑤ 采集口径

- **① `seal/list` 一次全量**：`pageRows=5000` **一次取全 3679 枚**（**不得分页循环**，沿 §7.1 F-1 硬上界纪律）；**本体字段（§3.17.7 表中除 detail 独有项外的全部）均从列表行落库**；**支持 `auditStatus` 过滤**（**本轮不按 `auditStatus` 裁剪、落全量**，裁定 A）。
- **② 形製标签本地码表派生**：**`sealYsXz`（形製码）经 §3.17.1 形製码表纯函数派生标签**（**每码 2 枚 × 0 冲突 ⇒ 纯函数**）；**源侧原文「异性」逐字照登**（**不得改写成「异形」**）。
- **③ `seal/detail` 降 best-effort（默认关，显式开关才开）**：**仅补 `sealYzRefId` / `auditUser`**（**路径参数 ＝ `seqid`**）；**慢速分片、失败进清单、不阻塞主交付**（manifest / report 如实登记 `detail_policy`）。**理由** ＝ **形製标签已可本地码表派生 ⇒ 不再跑 3679 次 detail**（**Zang 默认 · 一句话可改**）。
- **④ 关联面**：**关联主源 ＝ `graph/seal/<seqid>`**（**每枚一次**；**实测健康 8/8**）；**给印谱 / 印人节点**（落 sidecar `seal_links.jsonl`，裁定 C）。
- **⑤ `429` 陷阱判负**：**限流回包（HTTP 200 ＋ `code:"429"`）不得计作成功**；**必须指数退避重试（5s → 60s）＋ 失败清单 ＋ 可断点续跑**。**（v1.16 追注｜共用窗口限流）**：**影像请求（IIIF `char_proxy`）与 API 请求（`seal/list` / `graph/seal` / `seal/detail`）共用站点级窗口** ⇒ **429 一律判负、不得当成功**；**一旦出现 429 就降并发 ＋ 退避**（不得靠「换端点」绕过）。**实测**：**8 workers × 0.1 s ⇒ 0 次 429、17.2 张/秒**（**影像面取证见 §3.17.8 a. v1.16 追加块**）。**（v1.16 判据落 AC-35 / AC-47）**。
- **⑥ 断点续跑**：**采集进度须落盘**（本库或就绪包）；**中断后从断点续采**，**已完成条目不得重算重写**（幂等，落 AC-36）。
- **⑦ 失败清单**：**失败条目进失败清单**（本库批次行 / 就绪包 `report.json`），**不得静默跳过**（**失败条目数须可复算**，落 AC-35）；**不得以假数据 / 占位行填充失败项**。
- **⑧ 采集量（预估，非实测）**：`seal/list` **1 次** ＋ `graph/seal` **3679 次**（**主链路**）＋ **影像取数 6765 次**（IIIF 原生裁切，裁定 B'）≈ **10,445 请求**（按 **0.5–2 s / 请求** ≈ **1.5–6 h**）；**`seal/detail` 默认 0 次**（best-effort 开启时才增，慢速分片、失败不阻塞主交付）。

##### 3.17.7 ⑥ 字段面与归一化

| 目标字段 | 源 | 规则 |
| --- | --- | --- |
| `source_seal_id` | `seqid` | **幂等键**（原样字符串） |
| `audit_status` | `auditStatus` | **原样整数**（**保留 + 分布统计**；裁定 A） |
| `seal_text` / `seal_text_chs` | `sealYwSmwz` / `…Chs` | 原样（**繁体为正、简体入 `*_chs`**） |
| `owner` | `sealYz` | 原样（印主；**19 个值**） |
| `owner_zkz` / `owner_zkz_id` | `sealYzzkz` / `sealYzzkzId` | 原样（篆者；**10 个值**） |
| `side_inscription` | `sealBk` | 原样（边款） |
| `side_inscription_zkz_id` | `sealBkzkzId` | 原样（**21 个值**） |
| `form_code` / `form_label` | `sealYsXz` | **整数或 `null`** ＋ **§3.17.1 形製码表派生标签**（**644 行 `null` 合法**） |
| `as_book_id` | `asBookId` | 原样（**桥接印谱 / 印人侧的键**） |
| `related_book` | `relatedBook` | 原样 |
| `seal_face_ref` | `sealYtUrl` | 原样（**IIIF ref**；≈ 3679） |
| `seal_face_sw_ref` | `sealYtswUrl` | 原样（**IIIF ref**；≈ 2627） |
| `seal_face_bk_ref` | `sealYzbkUrl` | 原样（**IIIF ref**；≈ 459） |
| （detail 独有）`seal_ys_xz_label` / `seal_yz_ref_id` / `audit_user` | `sealYsXzLabel` / `sealYzRefId` / `auditUser` | 原样（**仅 `seal/detail` best-effort 开启时落**） |
| `raw_json` | 列表行 ＋ 详情行 | **保留源原文**（**不得丢源**） |
| `batch_id` / `updated_at` | — | 系统写 |

- **繁简存法（沿 §3.15.6 / §3.16.7）**：**繁体为正字段**（`seal_text`），**简体入 `*_chs` 副字段**；**不做任何转换改写**。
- **数值字段（硬口径）**：`form_code` / `audit_status` **为整数或 `null`**；源空 ⇒ **`null`**；**禁特值**（**不得出现 `0` / 空串**）。**`null` 不得写空串 / `0` 特值**（**硬约束**）。
- **源字段覆盖（照登实测；本版只登记、未复跑）**：`seqid` **3679 唯一**；`sealYwSmwz`（＋`Chs`）3679；`sealYz` 2379；`sealYzzkz` / `sealYzzkzId` 2652；`sealBk` 459；`sealBkzkzId` 254；`sealYsXz` 3035（**644 行 `null` 合法**）；`asBookId` / `relatedBook` / `sealYtUrl` 3679；`sealYtswUrl` 2627；`sealYzbkUrl` 459；**其余大多 `0` / `null`**。
- **detail 独有字段（照登）**：`sealYsXzLabel`（形製标签原文）/ `sealYzRefId`（印主引用 id）/ `auditUser`（审核人）——**与 list 不同构**（**list 独有 `*Chs`**）。

##### 3.17.8 ⑦ 影像面 ＋ seal↔印谱↔印人 sidecar

**a. 影像面（裁定 B'；v1.15 改口径：TIFF 直供 xiai 影像库）（硬约束）**

- **范围 ＝ 全部入包（TIFF 直供）**：印面 **3679**（`sealYtUrl`）＋ 印体释文 **2627**（`sealYtswUrl`）＋ 边款 **459**（`sealYzbkUrl`）≈ **6765 张**；**包内不放 JPEG**（**JPEG 仅作 `var/seal_images/` 源缓存**）；**入包形态 ＝ TIFF**（见下）。
- **本侧取图（IIIF，只读）**：`https://yin.fudan.edu.cn/iiif_proxy/api/char_proxy/<ref>` ⇒ **302 ⇒ JPEG**（**实测 6,702 B / 张**）；**只用原生裁切 `/full/0/default.jpg`**（**实测 160×149**）；**明确禁止放大尺寸**——**`!400,400` 实测回 200 但为 IIPImage 上采样插值 ⇒ 失真**（**写入规范作判负形态**；**不得请求非原生尺寸**）。
- **转换（JPEG → TIFF 无损容器转换）**：**不重采样、不二次有损编码**；**RGB**；**压缩可选 `tiff_deflate`（无损）**。**如实登记**：**「IIIF 仅出 JPEG ⇒ 包内 TIFF 为无损容器转换，质量受源 JPEG 限制」**（**写入 `images_manifest.jsonl` 的 `conversion` 标注**）。
- **xiai 影像库权威契约（只引用、不复制其代码；来源 ＝ `xiai/server/app/store.py` ＋ `codec.py`）**：**`POST /api/image/store`**（**服务端权威存储、内容寻址**）；**权威路径形状 ＝ `<sha256[:2]>/<sha256>.tiff`**；**只收 TIFF 容器**（**魔数 `II*\0` / `MM\0*`**，**不回落、不冒充**）；**上限 ＝ 产物侧 4 MiB（`STORED_MAX_BYTES`）／输入侧 1 MB（`MAX_INPUT_BYTES`）**；**幂等**（**同名同 size 同 sha256 ⇒ 不重写**）；**行内 `sha256` 即索引键**；**读 `GET /api/image/original/{sha256}`**，另 **`slices|thumb|download` 加 `?sha256=`**。**入库动作归 xiai 侧**（**feicui 只出包**，沿 §3.17.9 边界）。
- **就绪包影像面（镜像 xiai 形态）**：`images/` ⇒ **`images/<sha256[:2]>/<sha256>.tiff`**（**sha256 ＝ TIFF 字节**）；**包内不放 JPEG**。
- **`images_manifest.jsonl` ＝ 唯一索引（硬约束）**：**内容寻址后文件名不含 `seqid` / `kind` ⇒ 必须靠索引回指**；**每行**含 `seqid` / `kind ∈ {yt, ytsw, yzbk}` / `source_ref` / `source_url` / `sha256` / `bytes` / `width` / `height` / `source_format` / `container` / `conversion` / `upscaled:false`。
- **`NaN_` 开头 ref**：**预期无图 ⇒ 登记「源侧无图」**（`images_manifest.jsonl` 的 `status` 记 **`source_no_image`**；**不计作失败**、**不得静默跳过**）。**（v1.16 原位改写**：原写 `status` 记 `source_missing`，**已被 v1.16 取代、统一为 `source_no_image`**；**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.15.md`**；**系原位改写，不是「既有条款自动失效」**；**详见下方 v1.16 追加块**）。
- **缓存与入包**：**下载缓存 `var/seal_images/`（JPEG 源）** ＋ **入包写 TIFF**；**重出包不得删或重转已有影像**（**已有 TIFF 按 `sha256` 复用、不重转**）。
- **断点续跑**：**已下载 / 已转换影像按 `sha256` 复用、不重下不重转**；**失败影像进失败清单、可续跑**。

**a-v1.16. 源侧缺图三态分桶 ＋ 共用窗口限流 ＋ 逐张台账（v1.16 追加/修正）（硬约束）**

- **① 三态分桶（硬口径）**：影像台账（`seal_images`）与包内 `report.json` / `images_manifest.jsonl` **必须分三态**——`ok` / **`source_no_image`** / **`failed`**：
  - **`ok`** ＝ 取图 ＋ 转换成功。
  - **`source_no_image`（源侧缺图；源侧事实，非 feicui 采集失败）**——**子因三类（v1.17 由二扩三）**：**（a）`NaN_` 开头 ref**（确定无图）；**（b）持久 `HTTP 500`（有界重试 3 轮 2/8/30 s 退避后仍 500）**，**`error` 字段记 `HTTP 500`**；**（c）坏字节 `bad_bytes`（v1.17 新增）——HTTP `200` ＋ `content-type: image/jpeg`，但正文非图像 / 不可解码**（**实例如 `2_3609_1`：正文 697 B 为 iipsrv 把自己的响应头当正文吐出、非 JPEG 魔数、PIL 解码失败、持久复现**），**`error` 字段记实际现象原文**。**三子因均为源侧事实、不得计入采集失败**；**`source_no_image` 不得计入采集失败、不得静默丢弃**。（**（c）系 v1.17 追加；原「子因两类」原文留存于快照 `docs/versions/feicui.spec.v1.16.md`**。）
  - **`failed`** ＝ **仅留给可重试的瞬态错误**（超时 / 连接错误 / 转换失败等）；**收尾时 `failed` ＝ 0**（**v1.17 改口径**：**因 `source_no_image` 三子因已穷尽枚举（`NaN_` / 持久 5xx / 坏字节 `bad_bytes`），确定性（按 ref 恒定 / 非瞬态）失败不得留在 `failed`；若将来出现新的第四类，必须先入册再归类，不得静默落 `failed`**）。**（原「`failed` 桶须为空，或仅瞬态且附重跑命令」已被 v1.17 取代，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.16.md`；系原位改写，不是「既有条款自动失效」。）**
  - **判负形态**：把 `source_no_image`（**源侧事实**）写成 **feicui 采集失败**；或把源侧缺图**静默丢弃**（不进台账 / 不进 `report.json`）；或 **`failed` 桶 ≠ 0**（**v1.17 改口径**：含残留确定性（非瞬态）失败；或**出现新的第四类子因而未先入册即落 `failed`**）。
- **② 观测证据（照登 Zang 实测）**：60 refs 中 **11 条 `HTTP 500`**（响应体 `text/plain` 21 字节 `Internal Server Error`、**无跳转**）；**1 / 4 / 8 并发下失败集合完全相同（49 ok / 11 fail）、0 次 429** ⇒ **按 ref 恒定、非限流**；失败 ref **按前缀聚批**（**`11_*` / `12_*` 全挂、`19_*` 正常**）；**站点自身详情页同一 ref 图 `naturalWidth=0`（坏图）**、正常 ref 渲染 **204×365** ⇒ **源侧整批缺图，站点自己都显示不出**。（**取证判据落 AC-47 / AC-48**。）
- **③ 共用窗口限流（硬口径）**：**影像请求（IIIF `char_proxy`）与 API 请求（`seal/list` / `graph/seal` / `seal/detail`）共用站点级窗口** ⇒ **收到 429 一律判负、不得当成功**；**出现 429 就降并发 ＋ 退避重试**（**不得靠「换端点」绕过**）。**实测：8 workers × 0.1 s ⇒ 0 次 429、17.2 张/秒**。（**取证判据落 AC-35 / AC-47**。）
- **④ 逐张台账字段（硬口径）（v1.18 原位更正字段语义，以包内实物为准）**：影像面**每张记录 `width` / `height` / `bytes` / `sha256`（＋ 源侧溯源字段 `source_bytes` / `source_sha256`）**——**`width` / `height` ＝ TIFF 尺寸；`bytes` ＝ TIFF 字节数；`sha256` ＝ TIFF 字节的 sha256（即内容寻址键、＝文件路径名）；`source_bytes` / `source_sha256` ＝ 源 JPEG 侧（溯源用）；`tiff_sha256` 键不存在（包内实物无此键，本版删去其引用）**；**上限**——**单张 ≤ 4 MiB（xiai 产物侧 `STORED_MAX_BYTES`）**；**`MAX_INPUT_BYTES` ＝ 1 MB 属 xiai 编解码口输入面，不得用作本包 / 本端点判据**（**依据 ＝ xiai `server/app/store.py::validate_payload` 只校验「空 / `STORED_MAX_BYTES`（4 MiB）/ TIFF 魔数」三面**）。（**取证判据落 AC-51 / AC-52；**超 4 MiB 桶落 AC-54（超档行逐行标 `oversize_for_xiai_store: true`）**。）（**留痕：原 v1.16 文字「影像面每张记录 `width` / `height` / `bytes` / `tiff_sha256`（`width` / `height` 为 TIFF 尺寸；`bytes` / `sha256` 记源 JPEG 字节与其 sha256，`tiff_sha256` 记 TIFF 容器字节的 sha256）；双档上限——xiai 产物侧 4 MiB / 输入侧 1 MB，单张 ≤ 两档上限」逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §3.17.8；系原位更正，不是「既有条款自动失效」**。）
- **⑤ 放大尺寸判负（保留 v1.15 原文 ＋ 补定量依据）**：**v1.15 已写「禁止放大、`!400,400` 上采样写入判负」**（**原文保留、一字未改**）。**定量依据**（**证据文件 `ops/seal-ingest/09_upscale_probe.json`，Kong 本单产出；Jing 只引用、未复跑**）：**同区域尺寸读数**——**`full→204×365` / `400,→400×716` / `1200,→1200×2147` / `4096,→2795×5000`**；**Pillow 判定纯插值**——边缘强度：我方**双三次上采样 135.71** vs 服务器 **1200 大图 137.69**（**差 1.5%**）、**MAD 4.32/255**（与「原生 ↔ 大图降回原生」的 **4.37** 同量级）、**累方差 2858 vs 2824** ⇒ **不增真实信息**。（**取证判据落 AC-40**。）

**a-v1.17. `source_no_image` 第三子因 `bad_bytes` ＋ `failed` ＝ 0（v1.17 追加/修正）（硬约束）**

- **① 子因由二扩三（硬口径）**：`source_no_image` 子因**穷尽枚举三类**——**（a）`NaN_` 开头 ref**（ref 以 `NaN_` 开头、确定无图）；**（b）持久 `HTTP 500`**（有界重试 3 轮 2/8/30 s 退避后仍 5xx）；**（c）坏字节 `bad_bytes`**（**HTTP `200` ＋ `content-type: image/jpeg`，但正文非图像 / 不可解码**）。**三子因均为源侧事实、不得计入采集失败**；**`error` 字段记实际现象原文**（**（b）记 `HTTP 500`、（c）如实登记响应头当正文等实际现象，不得改写为自造错误码**）。
- **② `bad_bytes` 实例锚（照登 Zang 实测）**：**唯一失败项 `2_3609_1`**——**HTTP `200` ＋ `content-type: image/jpeg`，但正文 697 B 为 iipsrv 把自己的响应头当正文吐出**（**非 JPEG 魔数 `FFD8`、PIL 解码失败、持久复现**）⇒ **归 `source_no_image`（子因 `bad_bytes`）**，**不在 `failed`**。（**该实例在影像台账跑到终态 6765/6765 时为唯一落 `failed` 者；`ok 6347` / `source_no_image 417`（`http_500` 415 ＋ `nan_ref` 2）＋ 本项 `bad_bytes` 1 ⇒ 三子因合计 418、`failed` 归零。取证判据落 AC-53。**）
- **③ `failed` ＝ 0（改口径）**：**收尾时 `failed` 桶必须为 0**（**原「空或仅瞬态且附重跑命令」已被取代，见上 ① 处 `failed` 行 v1.17 改口径**）——**理由 ＝ 三子因（`NaN_` / 持久 5xx / 坏字节）已穷尽枚举**；**若出现新的第四类子因，必须先入册再归类，不得静默落 `failed`**。（**取证判据落 AC-47 / AC-53。**）

**a-v1.18. 逐张台账字段语义更正（以包内实物为准）＋ 超 4 MiB 桶（v1.18 追加/修正）（硬约束）**

- **① 字段语义（硬口径，以包内实物为准）**：**`images_manifest.jsonl` 与影像台账（`seal_images`）**的键面与语义＝**`sha256` ＝ TIFF 字节的 sha256（即内容寻址键、＝文件路径名）**；**`bytes` ＝ TIFF 字节数**；**新增 `source_bytes` / `source_sha256` ＝ 源 JPEG 侧（溯源用）**；**`tiff_sha256` 键不存在、不得引用**（**不设 `tiff_sha256` 别名**：实物无此键，杜绝与 `sha256` 并存冲突）。**实测自洽（Zang 对包内实物实测，本版只登记、未复核）**：`sha256(TIFF 文件) == 行.sha256`、`len(TIFF) == 行.bytes`、随机 20 行 0 违规（含逐行 TIFF 魔数成立）。
- **② 超 4 MiB 桶（新事实）**：包内 **6 张**影像 **> 4 MiB（`STORED_MAX_BYTES`）**——**`seqid 3353 / 3366 / 3367 / 3464 / 3506 / 3510`**（**均 `kind=yt`、~1500×1500、4.37–4.96 MB**）。**裁定（Zang）**：**本包保留原生裁切与「RGB 8-bit ＋ Deflate」家法格式，不自行降采样、不自行转码**；**6 条逐行标记（**实物字段名 `oversize_for_xiai_store`（boolean）**）＋ 顶层计数 ＋ 清单，去留由 xiai 侧裁**（落 §9-R34）。**取证判据落 AC-54**。**（计数对照：≤ 1 MiB 6122 ＋ 1–4 MiB 219 ＋ > 4 MiB 6 ＝ 6347 ＝ `images_manifest.jsonl` 行数。）**

**a-v1.19. 源侧引用未收录（`ref_id` 未命中 person 库）记账口径 ＋ 端点响应顶层内部键 `_db_path` 观察项（v1.19 追加）（观察项，不判负）**

- **① 源侧 `ref_id` 未命中 person 库（源侧引用未收录；不判负）**：采集后实测，`seal_links`（`graph/seal` 派生）中若干 `ref_id`（印谱 / 印人节点 id）**不在 `var/person_ingest.db` 的 570 人内**——**实测分布：印主面 8/438 行、篆者面 1/403、边款篆者面 6/11**（**均以 `ref_id` 计；本版只登记、未复核**）。**性质 ＝ 源侧引用未收录（源侧事实），非 feicui 采集缺陷 ⇒ 不判负**。**记账口径（硬口径）**：**`seal_links` 允许 `ref_id` 不命中 `var/person_ingest.db` 的 person 库**（**不得因未命中而丢行 / 静默跳过 / 强行为空**）；**但必须在就绪包 `report.json` 给出「`ref_id` 未命中 person 库」的计数**（**按面分列：印主 / 篆者 / 边款篆者各一计数 ＋ 合计**），**并标明该 `ref_id` 命中的是什么面**（**可追溯**）。**判负形态**：因 `ref_id` 未命中 person 库而**丢行 / 静默跳过**；或**未在 `report.json` 给出未命中计数**。**说明：本项不新增 AC**（**系源侧事实登记 ＋ 记账口径，非 feicui 可判负的实现目标**）。
- **② 端点响应顶层内部键 `_db_path`（观察项；三线共有惯例，非本线不一致）**：实测三线对照——**`GET /api/seals`、`GET /api/persons`、`GET /api/items` 的响应顶层键完全相同**，均为 `['items','page','limit','total','has_more','_facets','_db_path']`（**核验时点 2026-10-10；证据 ＝ 三线 `GET /api/*` 响应顶层键对照**）⇒ **`_db_path` 是三条采集线共有的既有惯例，不属印章线的本线不一致**。**本版据此不引入「从响应中删去内部路径键」类 AC / 待裁项**——**原拟的待裁项 R35 已撤回（逐字理由见 §9（v1.19）计数留痕 ＋ §10 本版行）**。**登记为观察项（不判负、不立 R、不立 AC）**：**如将来需统一口径从三线响应中移除 `_db_path`，须三线同轮同改**（**单改一线即构成新的本线不一致**）。

**b. sidecar `seal_links`（seal ↔ 印谱 ↔ 印人）（裁定 C）**

| 字段 | 来源 | 规则 |
| --- | --- | --- |
| `source_seal_id` | — | ＝ `seqid`（**回指 `seals.jsonl`**） |
| `link_kind` | `graph/seal` 节点 `name` | 原样（**`印谱` / `印人`**） |
| `target_id` | `graph/seal` 节点 `id` | 原样（**印谱 ⇒ `seqid`（可接 `var/item_ingest.db` 的 `source_item_id`）；印人 ⇒ `personGrbsm`**） |
| `target_name` | `graph/seal` 节点 `name` | 原样 |
| `as_book_id` | — | （印谱侧）**桥接键**（**`graph/seal` 给的印谱 id `1967` ↔ `source_item_id=1967` / `as_book_id=0113`**） |
| `seq` | — | 序号（稳定排序） |

- **桥接（实测；落 AC-39）**：**`graph/seal` 给的印谱 id ↔ `var/item_ingest.db` 的 `source_item_id` / `as_book_id`**；**印章涉 19 种印谱全部命中 item 库**。
- **跨工程键桥**：`source_seal_id`（`seqid`）**是本库 / 就绪包的幂等键**；`as_book_id`（`asBookId`）**是印谱 / 印人侧关联用的键** —— **两者不同号、不得混用**。

##### 3.17.9 ⑧ 跨工程边界 ＋ 零外链资源与联网红线（**硬约束**）

**a. 跨工程边界（硬约束）**

- **feicui 不得写 xiai 任何文件**；**不得调 xiai 云函数 / 不得做任何 CloudBase 写操作**（沿 §3.15.1 表下注 v1.8 追加 / §3.16.8 a）。
- **提交与审核不在 feicui 侧（审核门维持）**：**印章的模型 / 集合名 / 导入通道 / 审核门归 xiai 线**；**feicui 只出采集成果 ＋ 就绪包**。
- **键面未裁 ⇒ `key_face_status: "pending_xiai"`（硬约束）**：**候选键面未定前不裁剪**；`manifest.json` 给**字段字典**并标 `key_face_status: "pending_xiai"`；**对方定键面后二次出包、无需重新联网**（本库已存全字段 ＋ `raw_json`）。
- **交换方式**：**xiai 侧按上述目录只读消费**（本地路径约定）；如改为中立交换目录，**一句话可改**。

**b. 零外链资源与联网红线（硬约束）**

- **零外链资源**：**页面仍离线自洽**（**不得引任何外链 CDN / 第三方脚本 / 字体 / 图片**，沿既有硬约束）。
- **联网红线**：**联网只发生在 feicui 服务端，且只读**（**GET / POST 取数，不上传任何数据**）；**前端不得直连源站**（**即使源站回 `Access-Control-Allow-Origin: *` 也不直连**——理由见 §3.15.3）。
- **数据不变判据**：**证明「数据未变」一律用内容指纹，禁用数据库文件 md5**（沿 §8 第 6 条）。
- **不改他线**：**不得动 `xiai/**`、`yinyuan/**`、`ctrl/**`；不占新端口；启停登记一律以 ctrl 面板为准**。
- **独立库隔离（硬约束）**：**采集全程只写 `var/seal_ingest.db`**；`yinpu.db`、`var/person_ingest.db`、`var/item_ingest.db` 内容指纹**逐字节未变**（落 AC-43）。

---

#### 3.18 关联面（三表联立）（**v1.20 新增**｜只定口径 / 契约形状 / 存储 / 批次 / 判据，不定实现）

> **落位声明（v1.20）**：本小节为 **v1.20 追加**（**新增小节，置于 §3.17 及其全部子节之后、`## 4. 数据层演进` 之前**）。**§3.1 〜 §3.17 的节标题、表、条文与各版表下注原文逐字未改**（**唯一新增 ＝ 本小节 ＋ §7 的 AC-55 〜 AC-61 七行 ＋ §7 计数留痕（v1.20）一条 ＋ §9 的 R35 〜 R39 五行 ＋ §9 计数留痕（v1.20）一条 ＋ 表头「版本」行 / 「本版硬约束（v1.20）」行 ＋ §10 本版行**）。
> **口径真源**：**本小节逐条照登 `feicui/docs/relation-ingest-draft-v0.1.md`（Zang 2026-10-10 起草；其中 §1 / §2 为实测读数、§3 为默认口径）**（**逐条照登、不自行发明、不改与之冲突的口径**；**本版只登记、未复核**）。
> **性质**：**本小节只写口径 / 契约 / 判据**；**不含落地 · 验收结论、不含任何「实现现状」读数**（**落地属「已定、落地中（由 Kong 执行）」、验收归 Neng**）。
> **背景**：Kevin 2026-10-10 裁定「印人关联面本轮先不导入、作为独立需求另开」（§3.15.12）；**本条即该独立需求**——三条采集线（印人 / 印谱 item / 印章 seal）**各自的关系数据已全部落在 feicui 库内**，本需求把它们缝成**一致的关联面**并产出面向 xiai 的**候选关系包**。
> **归属**：**关系模型 / 集合名 / 键面裁剪 / 导入通道归 xiai 线**（同 §3.16.1 的 I-3 口径；**缺口见 §9-R35 / R36 / R37 / R39**）。

##### 3.18.1 ① 三表来源与行数（**实测照登**，2026-10-10）

| 库表 | 行数 | 关系语义 | 关键列 |
| --- | ---: | --- | --- |
| `var/person_ingest.db::person_relations` | **1650** | **印人 →（印谱 1349 / 印章 301）** | `source_person_id` / `kind` / `ref_id` / `name` / `desc` / `creator_type` / `image_key` / `as_book_id` / `has_image` / `seq` |
| `var/item_ingest.db::item_creators` | **1440** | **印谱 → 印人** | `source_item_id` / `creator_type` / `creator_role` / `creator_relator` / `creator_name` / `person_grbsm` / `source_face`（**`book_graph` 1281 / `person_graph` 159**）/ `seq` |
| `var/seal_ingest.db::seal_links` | **8964** | **印章 →（印谱 3679 / 印人 5285）** | `source_seal_id` / `link_kind`（**`book` 3679 / `person_yz` 2379 / `person_zzkz` 2652 / `person_bkzkz` 254**）/ `ref_id` / `ref_name`（＋ `_chs`）/ `creator_type` / `bridge_item_id` / `source_face`（**恒 `seal_row`**）/ `seq` |

- **表下注（硬口径）**：**`person_relations` 无 `source_face` 列**（**其来源恒为 `graph/person`**，照登不改写）；**`seal_links` 的 `source_face` 恒 `seal_row`**；**只有 item 侧才有两源**（`book_graph` / `person_graph`）。
- **可连键对账（实测照登；本需求的基础）**：`person_relations(印谱).as_book_id` → `items.as_book_id` **唯一 932 ⇒ 命中 931 / 未命中 1**（唯一未命中值 ＝ **`test`**，源侧测试占位行 ⇒ **源侧幽灵行，登记不判负**）；`person_relations(印章).ref_id` → `seals.source_seal_id` **261/261（0 未命中）**；`person_relations(印章).image_key` → `seal_images.source_ref` **261/261**；`seal_links(book).ref_id` → `items.as_book_id` **19/19**；`item_creators.person_grbsm` → `persons.source_person_id` **535/535**；`seal_links(person_*).ref_id` → `persons.source_person_id` **41 个 id ⇒ 命中 27 / 未命中 14**（**源侧引用未收录**，同 §3.17.8 a-v1.19 ① 口径：**不判负、但必须计数入包**）。
- **去重面（实测照登）**：`item_creators(book_graph)` **1281 对** vs `person_relations(印谱)` **1349 对** ⇒ **交集 1249**、only-item **32**、only-person **100** ⇒ **合并后并集 1381 对**（**去重算术落 AC-56**）。
- **涉及实体规模（实测照登）**：印人 **570** 人中 **539** 出现在 `person_relations`、**535** 在 `item_creators`、**27** 在 `seal_links`；印章关联涉印人 **261 枚唯一边**；`person_relations(印章)` 的 `creator_type` **全为「印主」**、**40 个印章 ref 挂了多人**（**源侧多主归属，照登**）。

##### 3.18.2 ② 统一关系边键面（**候选键面；`key_face_status:"pending_xiai"`**）

- **统一「关系边」（edge）表，一行一条**（**形态照登拆解件 §3**）：

```json
{"predicate":"person_to_item|item_to_person|person_to_seal|seal_to_item|seal_to_person",
 "subject_type":"person|item|seal", "subject_id":"…",
 "object_type":"person|item|seal", "object_id":"…",
 "role":null, "role_note":null, "evidence":["person_graph","book_graph"],
 "source_ref":null, "image_ref":null, "name":null, "name_chs":null, "seq":0, "batch_id":"relation_20261010_01"}
```

| 键 | 取值 / 语义（照登） |
| --- | --- |
| `predicate` | **五值枚举**：`person_to_item` / `item_to_person` / `person_to_seal` / `seal_to_item` / `seal_to_person`（**不得自造第六值**） |
| `subject_type` / `subject_id` | **`subject_type ∈ {person, item, seal}`**；`subject_id` ＝ 该类型主键（印人 `personGrbsm` / 印谱 `seqid` / 印章 `seqid`） |
| `object_type` / `object_id` | **同上，对象侧** |
| `role` / `role_note` | **角色**（印人侧给「辑、刻」；印谱侧给 `creator_role` / `creator_relator`；印章侧给 `link_kind` 对应面）；**无角色 ⇒ `null`**（**照登，不加默认值**） |
| `evidence` | **来源数组**（`person_graph` / `book_graph` / …；**双源共报同一事实时保留双源标记**，例 `["person_graph","book_graph"]`） |
| `source_ref` | 源侧引用（**可为 `null`**） |
| `image_ref` | 影像引用（**可为 `null`**；印人侧印章关联的 `image_key` 形如 `19_3250_1`） |
| `name` / `name_chs` | **名称（繁体为正）** ＋ **简体副字段**（**沿 §3.15.6 / §3.16.7 / §3.17.7 繁简存法：不做任何转换改写**） |
| `seq` | 序号（**稳定排序**） |
| `batch_id` | 批次号（**系统写**；默认形如 `relation_20261010_01`） |

##### 3.18.3 ③ 幂等键（**硬口径**）

- **幂等键 ＝ `(predicate, subject_id, object_id)`**（**三元组唯一**）；**同批次重跑 ⇒ 行数与内容指纹不变**（**已完成条目不得重算重写**，沿 §3.16 / §3.17 幂等口径）。
- **是否改用合成 hash 未定**（**归 xiai 裁，见 §9-R36**）；**未裁前一律以三元组为幂等键**。
- **凡「数据未变」类判据一律用内容指纹 / 逐字节比对，禁用数据库文件 md5**（§8 第 6 条）。

##### 3.18.4 ④ 口径 R-a 〜 R-f（**默认值逐条照登 ＋ 标「待 xiai 裁定、一句话可改」**）

| 口径项 | 默认（**一句话可改**｜**待 xiai 裁定**） | 需 xiai 确认 |
| --- | --- | --- |
| **R-a 边数与方向** | **保留两向**（`person_to_item` **1349** ＋ `item_to_person` **1440**）；**理由** ＝ 两向的 `role` / `creator_type` 语义不同（**印人侧给「辑、刻」，印谱侧给 `creator_role` / `creator_relator`**） | **是否只留单向 ＋ 方向字段** |
| **R-b 去重** | **同一 `(subject,object,predicate)` 只一行**，**`evidence` 数组保留双源**（去重后 **1249** 条标 `["person_graph","book_graph"]`） | **是否拆成两行以保留各源原字段**（见 §9-R39） |
| **R-c 幽灵 / 未收录** | **保留并标记**（`as_book_id='test'` **1** 条标 `ghost:true`；**14** 个未收录印人 id **保留原值**、另给 `person_resolved:false`） | **是否剔除**（见 §9-R38） |
| **R-d 印章的角色口径** | `seal_links` 的 印主 / 篆者 / 边款篆者 **5285** 条**全部保留并带 `link_kind`**；`person_relations(印章)` 的 **301** 条（`creator_type` 恒「印主」、带 `image_key`）**另标 `evidence:["person_graph"]`** —— **二者粒度不同**（前者来自印章行的 `sealYz` / `sealYzzkzId` / `sealBkzkzId`，后者来自印人详情页关联图），**默认都留** | **是否合并为同一 `predicate`** |
| **R-e 幂等键** | **`(predicate, subject_id, object_id)`** | **是否用合成 hash**（见 §3.18.3 / §9-R36） |
| **R-f 包形态** | **`exports/relation_import_<batch_id>/`**：`relations.jsonl` ＋ `manifest.json`（**`key_face_status:"pending_xiai"`**）＋ `report.json`（**各 `predicate` 计数 / 去重前后 / 未命中清单**） | **集合名 / 键面 / 导入通道**（**同三线：归 xiai 定**；见 §9-R35 / R36 / R37） |

- **去重前原始行合计 12054**（**1349 ＋ 1440 ＋ 301 ＋ 3679 ＋ 5285**）；**去重后按 R-a / R-b 口径重算**（**去重算术落 AC-56**）。

##### 3.18.5 ⑤ 就绪包（`exports/relation_import_<batch_id>/`）（**候选键面未裁**）

- **产物目录 ＝ `feicui/exports/relation_import_<batch_id>/`**（**位于 feicui 自有树内、gitignored**；**不写 xiai 仓任何文件**）。
- **三个成员**：
  1. **`relations.jsonl`（主交付候选）**——**一行一对象、UTF-8、无 BOM**；键面 ＝ §3.18.2 的统一关系边（**键面未定前不裁剪**）。
  2. **`manifest.json`**——必含：`schema_version`（**本版钉 `1`**）、生成时点（ISO 8601 带时区）、源表（三表 ＋ 行数）、**各文件行数**、**字段字典**、幂等键（**`(predicate, subject_id, object_id)`**）**唯一计数**、**各 `predicate` 计数**、**覆盖统计**、**`key_face_status: "pending_xiai"`**（**明示键面待 xiai 定**）。
  3. **`report.json`**——**各 `predicate` 计数** ＋ **去重前后计数**（**原始 12054 / 去重后按 R-a · R-b 重算**）＋ **未命中 / 幽灵清单**（**不得静默跳过**；**不为 0 必逐条列出**：`as_book_id='test'` 1 条 ＋ 14 个未收录印人 id）＋ **`ref_id` 未命中 person 库计数（按面分列 ＋ 合计，沿 §3.17.8 a-v1.19 ①）**。
- **重建幂等（硬约束）**：**由 `POST /api/relations/package`（§3.18.6）或 CLI 从本库重建就绪包时**，**仅 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 等时间戳变化**；**`relations.jsonl` 的内容逐字节不变**（**只读三库、确定性重写**）⇒ **「点按钮重建就绪包」不得据时间戳变化判为数据变化**（**判据落 AC-60**）。
- **形态（硬约束）**：**一行一对象 / UTF-8 / 无 BOM / 字段名稳定**（沿 §3.15.10 第 3 条）。

##### 3.18.6 ⑥ 两个 additive 端点（`feicui/server`，端口 **5196**；**additive、不动 E1 〜 E7 与 §3.15.3 / §3.16.3 / §3.17.3 既有端点**）

| # | 方法 / 路径 | 语义 | 要点 |
| --- | --- | --- | --- |
| **T1** | `POST /api/relations/package` | **从三库联立、重建 xiai 就绪包**（目录 `feicui/exports/relation_import_<batch_id>/`：`relations.jsonl` ＋ `manifest.json` ＋ `report.json`）；**不联网采集**（**纯本库联立、零联网**） | **入参** ＝ 查询参数**仅白名单 `batch_id`（可选；缺省＝本库最新批次）**；**未白名单查询参数 ⇒ 400**（`UNSUPPORTED_PARAM`，结构化 JSON）；**给出 `batch_id` 但批次不存在 ⇒ 404**（`BATCH_NOT_FOUND`）；**响应 ＝ 就绪包摘要**（**`key_face_status == "pending_xiai"`**）；**两条红线 ＝ 零联网 ＋ 不写 xiai 任何文件** |
| **T2** | `GET /api/relations/summary` | **关联面摘要（只读）** | 给**各 `predicate` 计数** / **三表行数** / **去重前后计数** / **未命中 · 幽灵计数**（**只读、不重建包、不落盘**）；**非白名单参数一律 400 结构化 JSON**（沿 §3.15.3 读口纪律） |

- **错误码纪律（硬要求，写入即判据）**：**一律返回结构化 JSON**，**绝不返回 HTML 错误页**（含 500 的未捕获异常页）；错误体须含机器可读字段（如 `error` / `detail`）与人类可读说明。**禁止以 `200` + 空 `items` 冒充「接口未实现」或「无数据」**（沿 §3.4 纪律 3）。
- **CORS**：**白名单仅 `http://127.0.0.1:5195` / `http://localhost:5195`**（§3.14.4 既有白名单）；**任何情况下不放开 `*`**。

##### 3.18.7 ⑦ 红线（**硬约束**）

- **零联网（最高优先）**：**本需求是纯本库联立**——**不得再打复旦站点任何端点**（四线既有数据已够；`relation-ingest-draft-v0.1.md` §5 边界同此）；**`POST /api/relations/package` 与 `GET /api/relations/summary` 重建 / 摘要期间不得产生任何源站请求**（**判据落 AC-61**）。
- **只读三库三包**：**只读** `var/person_ingest.db` / `var/item_ingest.db` / `var/seal_ingest.db`（**三库内容指纹须逐字节未变**）；**只读**三线既有就绪包（`exports/person_*` / `exports/item_*` / `exports/seal_*`）；**不改三线的库与包**（**判据落 AC-59**）。
- **不写 xiai**：**feicui 不写 xiai 任何文件、不调云函数 / 不做任何 CloudBase 写操作**（沿 §3.15.1 表下注 v1.8 / §3.16.8 a / §3.17.9 a）。
- **键面未裁 ⇒ `key_face_status: "pending_xiai"`（硬约束）**：**候选键面未定前不裁剪**；`manifest.json` 给**字段字典**并标 `key_face_status: "pending_xiai"`；**对方定键面后二次出包、无需重新联网**（本库已存全字段）。**重出包不得改 `relations.jsonl` 字节**（§3.18.5 重建幂等）。
- **数据不变判据**：**证明「数据未变」一律用内容指纹，禁用数据库文件 md5**（沿 §8 第 6 条）。
- **不改他线**：**不得动 `xiai/**`、`yinyuan/**`、`ctrl/**`；不占新端口；启停登记一律以 ctrl 面板为准**。

##### 3.18.8 ⑧ 页面形态（**本需求不加页签、不动 tabbar**）（**硬约束**）

- **本需求不加页签、不动 tabbar**：**不加新页签、不动 `App.vue` 的 tabbar / 顶部页眉布局** ⇒ **不触发 §7 AC-23**（**页签集合仍恰为【印谱解析】/【印人采集】/【印谱采集】/【印章采集】四项、tabbar 位置与固定页眉口径一字未改**）。**此句显式写入，避免下轮误改**。
- **如将来确需为关联面加入口**：**须走 §0.4 原位改写 AC-23（页签集合 4 → N）并逐处留痕**（**不得**写成「既有条款自动失效」）；**本版不做**。
- **触发形态**：`POST /api/relations/package`（T1）**经既有接口层暴露**（**无 UI 按钮要求**；**触发形态 ＝ 命令行 / 端点调用**，沿 §9-R23 同型待裁项的口径）。

---

### 3.19 E8 拖曳上传端点契约：`POST /api/jobs/upload`（5196）（**v1.21 新增**｜只定形状 / 语义 / 判据，不定实现）

> **需求来源**：Kevin **2026-10-10**——**【新建 job（E1）】页的 `pdf_path` 输入框改为拖曳文件，不必手动键入**。**两条裁定照登**：① **拖动上传为主 ＋ 保留折叠的「高级：手输服务器路径」（默认收起）**；② **落点 `feicui/inbox/<yyyymmdd>/<原文件名>.pdf`，同名同内容复用**。**本小节逐条照登、不自行发明**。

**落位声明**：本小节为 **v1.21 追加**（**新增小节，置于 §3.18 及其小节之后、`## 4. 数据层演进` 之前**）。**§3.1 〜 §3.18 的节标题、表、条文与各版表下注原文逐字未改**；**本版唯一新增 ＝ 本小节 ＋ §3.1 端点表 E8 行 ＋ §3.1 表下注（E8）一条 ＋ §3.2 S-6 v1.21 补注 ＋ §3.4 表 `413` 行与 `400` 行随动 ＋ §3.4 表下注（v1.21）一条 ＋ §7 的 AC-62 〜 AC-71 十行 ＋ §7 表下注（v1.21）一条 ＋ §9 的 R40 〜 R41 两行 ＋ §9 计数留痕（v1.21）一条 ＋ 表头两行 ＋ §10 本版行，均属「只增行」**。

**端编号裁定（登记为 E 系列的 E8，不另开「§3.19 端点」）**：本端点**登记为 E 系列的 E8**、与 E1 〜 E7 同表（§3.1）。**理由（逐条）**：① **同族**——E8 是 **E1 的前置步骤**（把 PDF 落到服务器可寻址的位置，再把该路径交给 E1 建 job），属 **job 体系的输入面**，与 E1 〜 E7 共用一个「端点一览」注册表；② **避免同一链路两处分叉**——本仓已有「实现侧 additive 端点未同轮入规范 ⇒ spec/实现分叉」的教训（§3.16.3 Q5 / v1.14 收口），**同一 job 链路的端点必须落同一张表**；③ **§3.14 的形态不适用**——§3.14（`POST /api/tools/square-crop`）是**与 job 体系完全无关的纯函数式工具端点**，故它以§号而不以 E 号登记；**E8 与 job 体系有关，故取 E 号**；④ **§3.19 仍是「细则节」**：本小节承载 E8 的请求 / 响应 / 幂等 / 红线 / 前端行为的完整契约，**但它不是端点号**（端点号是 **E8**）。**定式：将来另立 job 体系外的端点，照 §3.14 以§号登记；另立 job 体系内的端点，照本条取 E（E9、E10…）**。

#### 3.19.1 前提：浏览器事实（**硬前提，不得绕过**）

- **拖入的 `File` 不带本地路径**：浏览器安全模型下，`File` 只有 `name` / `size` / `type` / 内容，**没有**本地路径字段（`webkitRelativePath` 只给目录选择场景的相对路径，**不适用于普通拖放**）⇒ **拖曳 ≠ 直接拿到本地路径**。
- ⇒ **拖曳上传的实现语义必然是**：**浏览器把字节 POST 到服务器 → 服务器落盘 → 返回服务器侧路径 → 前端把该路径填进表单的 `pdf_path` → 再调 E1**。**任何「拖进来就有了 `pdf_path`」的写法都是错的**（该路径在浏览器侧不存在）。
- **E1 的 `pdf_path` 口径不变**：**「PDF 路径（绝对或相对 `feicui/`）」**（`server/app/models.py::JobCreate`；核验时点 **2026-10-10**，只读实测）——E8 返回的 `pdf_path` 必须**落在该口径内**、可直接喂给 E1（见 §3.19.3 / §3.19.4）。

#### 3.19.2 请求（契约）

| 项 | 值（冻结） |
| --- | --- |
| 方法 / 路径 | **`POST /api/jobs/upload`**（端口 **5196**；面板 sid **`feicui-api`**） |
| `Content-Type` | **必须** ∈ {`application/pdf`, `application/octet-stream`}；**否则 ⇒ `400 BAD_CONTENT_TYPE`**（§3.4 的 `400` 族） |
| **请求体** | **PDF 裸字节流**（**不经 multipart / 不经 base64 / 无 JSON 信封**） |
| 文件名 | 请求头 **`X-Filename`**（**URL-encoded UTF-8**）；**回退链**：`X-Filename` → `Content-Disposition` 的 `filename`（含 `filename*=UTF-8''…` 形态）→ 常量 **`upload.pdf`** |
| 查询参数 | **无**（**未白名单的查询参数 ⇒ `400`**，与 §3.16.3 Q5 / §3.18.6 同型） |
| 单文件上限 | **默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准**——**2026-10-11 起 ＝ 5 GiB（5368709120 B）**（`server/app/config.py::UPLOAD_MAX_BYTES_DEFAULT = 5 * 1024 * 1024 * 1024`；`FEICUI_UPLOAD_MAX_BYTES` 环境变量或 `server/config.json` 的 `upload_max_bytes` 可覆盖）；**原写「默认 512 MiB（＝ `1024*1024*512` 字节）」已被 v1.22 取代**（**v1.22 裁定：Kevin 2026-10-11，见 §9-R40**）；**改数值不需升规范**，但**改「有上限/有默认值/可改」这三件口径本身须走 §0.4** |

**（v1.22 随动｜留痕）**：**单文件上限默认值由「512 MiB」同步为「5 GiB（5368709120 B）」**（**默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准**）；**「有上限 / 有默认值 / 可改」三件口径本身一字未改**（§3.19.2 原已明写「**改数值不需升规范**」）；依据 ＝ Kevin 2026-10-11 裁定（**§9-R40 结案**；实测：`秦印类编 检索版.pdf` **1.88 GiB / 851 页**、`福庵印缀 原版 高清.pdf` **1.14 GiB / 236 页**、本机 `df` 余量 **191 GiB**、下游代价 **8.67 s/页**）。

**为什么必须裸字节流、不得走 multipart（理由，写死）**：
1. **体量**：源 PDF 实测 **38 MB**（`feicui/tmp.pdf`）、历史最大 **372 MB**（古玺汇编）——而仓内既有 **`server/app/multipart.py` 是纯 stdlib 实现、把整体读进内存**（签名 `parse_multipart(content_type: str, body: bytes)`——**`body` 是 `bytes`、不是流**）⇒ **数百 MB 的 multipart 上传会在接口层再复制一份整车内存**，与「薄接口层」（§1.2 I-2）相悖。
2. **本端点只需一个文件 ＋ 一段文件名**——multipart 的多字段 / 多文件能力**在此无用**。
3. ⇒ **本端点走 `request.stream()`（或等价的分块读）边收边写、边写边判上限**；**不得**先 `await request.body()` 再落盘（那等于把整车读进内存，与第 1 条同病）。
- **纪律**：**本端点不复用 `multipart.py`**；**`multipart.py` 一字不改**（§3.14 工具端点继续用它，**32 MiB 口不变**）。

#### 3.19.3 落点、文件名清毒与幂等

| 项 | 值（冻结） |
| --- | --- |
| **落点** | **`feicui/inbox/<yyyymmdd>/<basename>.pdf`**（`<yyyymmdd>` 按**服务器当日**日期；`inbox/` 为**新建目录**——核验时点 **2026-10-10** 实测 **磁盘上尚不存在**，**由实现创建**；**最终路径必须落在 `FEICUI_ROOT` 之内**） |
| **文件名清毒（必做，硬约束）** | ① 只取 **basename**（丢弃任何目录部分）；② **剔除路径分隔符**（`/`、`\`）与 **`..`**（含 `....//` 一类变体）与**控制字符**（U+0000–U+001F）与 **NUL / 百分号编码二次解码后的分隔符**；③ **UTF-8 解码失败 / 空名 ⇒ 回退** `upload.pdf`；④ **长度上限**（例 200 字节；超长截断并保留 `.pdf` 后缀）；⑤ 只允许 **单个 `.pdf` 后缀**（**不得**出现 `x.pdf/../y` 一类形态）。**清毒结果必须落在 `<yyyymmdd>/` 之内**（**越界 ⇒ `400`**，**不得静默改写为任意路径**） |
| **幂等（同名同内容）** | 目标文件**已存在**且其 **sha256 ＝ 本次上传字节的 sha256** ⇒ **不重写**（**mtime 不变**、字节不变），响应 **`200`** ＋ **`idempotent:true`**、`dedup_suffix:false` |
| **不覆盖（同名异内容）** | 同名但 **sha256 不同** ⇒ **绝不覆盖**：落 **`<basename>-<sha256[:8]>.pdf`**（同目录），响应 **`201`** ＋ **`dedup_suffix:true`**；**原文件的字节与 mtime 均不变** |
| **sha256 口径** | **`sha256` ＝ 上传字节本身的 sha256**（＝落盘文件的 sha256）；幂等判定与 `dedup_suffix` 命名**同一份字节**派生（**不得**用源侧 / 客户端声称值） |

**纪律**：① **本端点只落盘、不解析 PDF、不读页数、不建 job**（读页数属 E1 的派生态职责，见 §3.1 表下注 G-5）；② **同名异内容一律落后缀、不留任何覆盖路径**（红线「不得覆盖」）；③ `inbox/` 的**清理策略未定** ⇒ §9-**R41**（**本版不实现清理**）。

#### 3.19.4 校验、响应与错误码

**校验顺序（冻结）**：① `Content-Type` 非白名单 ⇒ `400 BAD_CONTENT_TYPE`；② **空体**（收到 0 字节）⇒ **`400 EMPTY_BODY`**（**先于** magic 判定——空体连首字节都没有）；③ **首字节非 `%PDF-`** ⇒ **`400 NOT_A_PDF`**；④ **累计写入字节 > 单文件上限** ⇒ **`413 PAYLOAD_TOO_LARGE`**（**边写边判**：每写一块即累加并比较，**一超即停写、删除本轮已写分片**；**不得**「先写满盘再报错」）。

- **与 §3.1 表下注 G-6 的关系（写清，防误用）**：**G-6 管 E1 对既有文件的宽松判定**（**前 1024 字节内**出现 `%PDF-` 即可），**E8 管新收字节的严格判定**（**首字节即须为 `%PDF-`**——PDF 规范要求 `%PDF-` 位于文件头）——**两者是「不同口的不同严格度」，不互相代替、本版不统一**；非 PDF 一律以 **`%PDF-` magic** 为准、**不得**按扩展名分流（承 G-6 的「以内容为准」原则）。

| 情形 | HTTP | 体（**恰 7 字段**，冻结） |
| --- | --- | --- |
| 新落盘 | **`201`** | `{pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}` |
| 幂等复用（同名同内容） | **`200`** | 同上（`idempotent:true`、`dedup_suffix:false`） |
| 同名异内容（落后缀） | **`201`** | 同上（`idempotent:false`、`dedup_suffix:true`） |

字段语义（冻结）：`pdf_path` ＝ **可直接交给 E1 的路径**（**绝对或相对 `feicui/`**，承 `models.py` 口径）；`rel_path` ＝ **相对 `FEICUI_ROOT`** 的路径（如 `inbox/20261010/<名>.pdf`）；`filename` ＝ **清毒后**的落盘文件名（若落后缀则含 `-<sha256[:8]>` 后缀）；`bytes` ＝ 落盘字节数；`sha256` ＝ 落盘字节的 sha256；`idempotent` / `dedup_suffix` ＝ 布尔。

**错误码（一律结构化 JSON，承 §3.4）**：`400 BAD_CONTENT_TYPE` ／ `400 EMPTY_BODY` ／ `400 NOT_A_PDF` ／ `400`（未白名单查询参数 / 清毒后越界） ／ **`413 PAYLOAD_TOO_LARGE`** ／ `500`（磁盘 / IO 异常）。

**判负形态**：① **任一错误返回 HTML / 非 JSON 体**；② **超限返 `400`（或 `200`）**——**须 `413`**；③ **空体返 `NOT_A_PDF`**（须 `EMPTY_BODY`；两者可机械区分）；④ **`413` 之前已把超限字节落满盘**（见 AC-65）；⑤ **用 `200` ＋ 空体冒充失败**（§3.4 纪律 3）。

#### 3.19.5 前端行为（`pdf_path` 拖放区 ＋ 折叠手输）

> **落位**：**本节**（E1 表单无独立小节；**不得**改动 §3.8 的 E7 列表口径与 §3.2 / §3.4 的既有纪律）。

| 项 | 口径（**可机械判负**） |
| --- | --- |
| **可见输入框 → 拖放区** | 【印谱解析】页新建 job 表单里的 `pdf_path` **可见输入框改为拖放区**：**可拖入**（`dragover` / `drop`；**默认行为必须 `preventDefault`**，否则浏览器会直接打开该文件）＋ **可点击选文件**（`<input type="file" accept="application/pdf,.pdf">` 隐藏、由点击触发） |
| **显示** | 选定 / 拖入后**显示文件名 ＋ 体积**（人类可读，如 `12.3 MB`）；上传中显示**进度百分比**；上传完成显示**服务器侧路径（只读）**＋**「已就绪」** |
| **上传（必须有进度）** | **用 `XMLHttpRequest`**（**不用 `fetch`**——`fetch` 拿不到上传进度）＋ `xhr.upload.onprogress` **算百分比**；**372 MB 必须有可见进度**，**不得**只显示「上传中」 |
| **上传成功后** | 把 **E8 返回的 `pdf_path` 填进提交给 E1 的字段**；**只读显示**服务器侧路径与「已就绪」；**不得**把本地文件名当 `pdf_path` 提交 |
| **失败必须可见** | 非 PDF（`400 NOT_A_PDF`）/ 空体（`400 EMPTY_BODY`）/ 超限（`413`）/ 网络错误 ⇒ **必须有可见错误**（结构化 JSON 的 `error` / `detail` 原样或人读化展示）；**不得静默失败、不得渲染成「已就绪」** |
| **折叠的「高级：手输服务器路径」** | **新增默认收起的折叠区**，标题**逐字「高级：手输服务器路径」**，**保留原 `pdf_path` 文本输入框**（供服务器上已有路径直接输入）；**默认收起**（**不得默认展开**） |
| **不得改变** | **`page_range` / `chunk_size` / `rerun` 三个字段、`409` 提示（§3.4 纪律 4：原样展示 body ＋ 取 `body.job_id`）、localStorage 本机记录（§3.8：两栏分开、不与后端数据混排）一律不得改变** |
| **色值** | **只走 token**（§0.5.2：色值只允许定义在 `web/src/styles/base.css` 的 `:root`；组件不写字面色值）；**承担信息传递的图形元素（进度条 / 状态点）对相邻背景非文本对比 ≥ 3:1** |

**判负形态**：① 拖放区缺失 / `dragover` 未 `preventDefault`（一拖即跳走）；② **无上传进度百分比**（数百 MB 只显示「上传中」）；③ 失败静默（无可见错误）或把失败渲染为「已就绪」；④ **折叠区缺失 / 默认展开**（须默认收起）；⑤ **`pdf_path` 被写成客户端文件名**（本地路径在浏览器侧不存在）；⑥ 改动 `page_range` / `chunk_size` / `rerun` / `409` 提示 / localStorage 行为；⑦ 组件内出现字面色值。

#### 3.19.6 红线（**硬约束**）

- **零 DB 写**：**无任何 SQL、无 `repository` 调用、不读 `stamps`**；**不建 job**（`jobs` / `job_pages` **一个字都不碰**）——**同 §3.14 工具端点风格**（判据＝调用前后 `jobs` 行数与内容指纹逐字节不变，见 AC-68）。
- **只落盘**：本端点的**唯一副作用 ＝ 在 `feicui/inbox/<yyyymmdd>/` 下新增 / 复用 PDF 文件**；**不碰 `exports/` / `output/` / `var/` / `yinpu.db`**。
- **不动 E1 〜 E7**：**E1 的请求 / 响应 / `400` / `409` 契约一字未改**（见 AC-69）；**E2 〜 E7 不受影响**。
- **不写 xiai / 不动他线**：**不得动 `xiai/**` / `yinyuan/**` / `ctrl/**`**；**不占新端口**（仍 5196）；**启停登记一律以 ctrl 面板为准**。
- **零外链**：本端点**不访问任何外部站点**（本地落盘；与 §3.15.9 / §3.16.9 / §3.17.9 / §3.18.7 的联网红线同源）。

#### 3.19.7 与 AC 的关系 ＋ 落地状态

- **AC 索引**：本小节的可机械判负面由 **§7 AC-62 〜 AC-71**（**10 条**）承载：拖曳上传全链路（AC-62）＋ 非 PDF 判负（AC-63）＋ 空体（AC-64）＋ 超限且不得先写满盘（AC-65）＋ 同名同内容幂等（AC-66）＋ 同名异内容不覆盖（AC-67）＋ 零 DB 写（AC-68）＋ E1 契约未变（AC-69）＋ 折叠手输仍在且默认收起（AC-70）＋ 上传进度可见（AC-71）。
- **落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本节不含任何「本轮已通过」结论**；**实现侧文件**（`server/app/routers/jobs.py` / `server/app/config.py` / `server/app/main.py` / `JobsPage.vue`）**由 Kong 并行另一单负责，Jing 未动一个字节**。
- **待裁**：§9-**R40**（上传上限是否合适）——**已结（Kevin 2026-10-11 裁定：上限默认 5 GiB；见 §9-R40）**；§9-**R41**（`inbox/` 清理策略：谁清、何时清）——**仍挂起（v1.22 复核未变）**。（**v1.22 随动｜留痕**：原写「§9-**R40**（上传上限 512 MiB 是否合适）／§9-**R41**（`inbox/` 清理策略：谁清、何时清）」；**R40 已于 v1.22 结案、R41 仍挂起**。）
- **将来若需**批量拖入多个 PDF / 断点续传 / 分片：**须走 §0.4 另立需求**（**本版不做**）。

---

## 4. 数据层演进

### 4.1 演进项（SQLite 保留 + 四项改造）

| # | 改造 | 现状（核验时点 2026-09-20 10:38） | 目标 / 口径 |
| --- | --- | --- | --- |
| D-1 | **开 WAL** | `PRAGMA journal_mode` → **`delete`** | `PRAGMA journal_mode=WAL`（进程启动即设并**校验返回值**）；`synchronous=NORMAL` **仅在** WAL 下采用 |
| D-2 | **建索引 `(pdf_name,page)`** | `stamps` 上**无任何索引**（**v1.2 收口｜G-7：落地形态＝唯一索引** `uq_stamps_pdf_page_idx`——SQLite **无法给既有表补表级约束**，只能建**唯一索引**，其幂等语义**等价**（`PRAGMA table_info` 内**不出现**约束行，**不算落地失败**）；**与 §4.1「只许加法」完全相容**；**判据**＝`PRAGMA index_list(stamps)` 含该索引 **且** `PRAGMA index_info(uq_stamps_pdf_page_idx)` 恰为 `(pdf_name, page, idx)` **且** `idx` 唯一性生效；**严禁**为落地「表约束形态」而**重建 `stamps`**（重建＝破坏「只许加法」与既有 79 条数据的判负动作）。**落地前置**＝建索引前**实测重复组为 0**（Kong 侧已实测 0，见 `server/README.md` §4.3）） | 建 `idx_stamps_pdf_page(pdf_name,page)`；**并**建 `UNIQUE(pdf_name,page,idx)` 承载 §2.4 行级幂等（**唯一约束是本规范要求，现状不存在**） |
| D-3 | **批量事务**（替换每页一次 connect/commit/close） | `processor.py` 行 **432 / 440 / 441**：**每页** `connect → commit → close` | **按 chunk（或按页内全部记录）一次事务提交**；单页内**不得**多次开合连接。**判据见 §7 AC-10** |
| D-4 | **影像外置目录规则** | 影像散在 `output/<书名>/…` 与 `output/pairs/pNN_i/…`（49 个 `.webp`，`du=3.4 M`） | ① **DB 只存路径 / `sha256` / `bytes` / `width`·`height`·`color_mode`，不得存影像 BLOB**；② 影像统一落 **`feicui/output/faces/<book_key>/p<页4位>_<idx2位>.<ext>`**（`book_key` 取 `config/book_codes.json` 的本地简码）；③ **迁移旧路径须留映射**（`images.src_path` 与 `images.package_path` 已分列，沿用） |

### 4.2 影像目录规则（细则）

1. **路径一律相对 `feicui/`**（不写绝对路径入 DB；现状 `img_path` 为 `output/...` 相对形态，**保持**）。
2. **文件名稳定**：同 `(pdf_name,page,idx)` 重跑 ⇒ **同一路径**（便于 §2.4 幂等比对）。
3. **不得**在热路径生成新命名（如带时间戳 / 随机后缀），否则幂等判定失效。
4. 中间产物（如 `output/pairs/**/stamp.png`）与**交付影像**分层：交付影像以 `faces/` 为唯一口径，中间产物**可清理**（清理须记录）。

### 4.3 事务与断点的耦合口径

- **提交点 = chunk 边界**（也是断点粒度，§2.3）；**页内记录与页内影像必须同批生效**（先写影像文件 + `fsync`，后提交 DB 行；崩溃窗口允许**孤儿影像**，**不允许孤儿 DB 行**——**孤儿影像由重跑覆盖，不产生重复**）。
- **多 worker 写同一 SQLite 文件**：**WAL 单写者** ⇒ **必须串行化写**（唯一写者进程 / 写队列）。**不得**让 N 个 worker 各自直连 `yinpu.db` 并发 `INSERT`（**这会触发 `database is locked` 或假成功**）。**依据**：WAL 语义 + 现状「每页 connect/commit/close」已是最坏形态（§0.3 D-3）。

### 4.4 未来扩展的边界条件（**阈值＝Jing 拟定门槛，待 Zang 裁定**）

> **诚实标注**：下述阈值**不是既有事实、也不是派单口径**，是 **Jing 依据本机实测资源与现状规模提出的门槛草案**；**须 Zang 裁定**（登记 §9-R3）。**落地前不得当作正式口径引用**。**锚点（实测）**：现状 `stamps` **89 行**（**v1.4 原位更正 + 留痕**：原记 **79 行**（核验时点 2026-09-20 10:45），**已由 v1.4 取代**——核验时点 **2026-09-20 14:59** 实测 **89 行**；`id<=79` 的 79 行三口径指纹逐字未变、`id 80–89` 为 1c 阶段两轮真实解析新增，见 **§0.3 v1.4 注 ②**）、影像 **79 个**、`output` **3.4 MB**、库 **576 KB**、可用磁盘 **169 GB**、RAM **16 GB**。

| 触发条件（**任一命中**） | 必须换成什么 | 为什么（依据） |
| --- | --- | --- |
| **① 影像文件数 > 2 万** 或 **影像总量 > 50 GB** | 影像 ⇒ **对象存储**（content-addressed，**以 `sha256` 命名 / 去重**） | 单机目录在**数万文件**量级后 `ls`/备份/迁移成本陡增；且 §9.6 已预留「后续可换对象存储 + 队列」。以 `sha256` 命名为**唯一可行**的幂等锚（§9.4 图片幂等同源）。 |
| **② 主表（`stamps` + `seals`）合计 > 20 万行** | 著录表 ⇒ **PostgreSQL** | 规模口径「数千本 × 数千页」（Kevin 原话）在**页级**即到数十万～百万级；SQLite **单写者**不满足并行写与远程访问。> 20 万行为**保守**阈值，取的是「单库备份窗口与写并发开始难受」的经验点。 |
| **③ 需要 ≥ 2 个写者进程 / 写者跨主机** 或 **需要远程 / 多机读** | ⇒ **PostgreSQL**（写入者从 1 变 N） | WAL 只允许**一个写者**（§4.3）；跨机访问 SQLite 文件是反模式。**此条一旦成立，与行数无关，必须换。** |
| **④ 单库全量备份窗口 > 5 分钟** | ⇒ **PostgreSQL**（+ 增量 / PITR） | 备份窗口是运维硬指标；现库 576 KB（**秒级**），余量充分。 |

**换的时候的迁移锚（必须先具备，才能谈换）**：

1. **`sha256`**（影像内容）——对象存储去重键与迁移完整性校验（现有 `images.sha256` 列已具备）；
2. **`(pdf_name,page,idx)`**——记录行唯一锚（§2.4；**须先补唯一约束**）；
3. **`dedupe_key`（§9.4 口径）**——跨系统去重锚（现有 `seals.dedupe_key` 列已具备）；
4. **`batch_id`**——批次回滚锚（§9.6；现有 `export_batches` 已具备）。

**边界纪律**：**在上述触发条件命中前，不得提前引入对象存储 / PostgreSQL**（避免为了「以后」而牺牲现在——§1.2 I-1/I-2 的效率前提是现阶段的实测结论）。

---

## 5. 并发与资源

### 5.1 worker 数口径

| 项 | 口径 | 依据 |
| --- | --- | --- |
| 硬件基线 | **10 物理核 / 10 逻辑核**（`sysctl -n hw.physicalcpu hw.logicalcpu`） | §0.3 实测 |
| **默认 worker 数** | **4**（**v1.3 定案，原位更正**；**原「8（草案，待 Zang 裁定）」已被 v1.3 取代**，留痕见本行末注；原登记项 §9-R4 **已收口**） | **v1.3 依据（Zang 已裁定）**：阶段 0b 实测 **`w=4` 到顶、`w=8` 无收益**（单枚成本膨胀 **+114%**、效率 **40%**），且 **swap 近耗尽** ⇒ **以 4 为准**，与 **AC-04 已钉的 `N=4`** 对齐（**原 §5.1 草案值 8 与 AC-04 冲突，本节即该冲突的收口点**）。**留核口径（原文保留）**：留 **1 核**给接口层 / 前端 / 系统，留 **1 核**给 OCR 峰值与 I/O 抖动。**不得**把 10 核全部分给 worker。 |
| 上限 | **10**（= 物理核数）；**超过物理核数须 Zang 明示** | 单页渲染/OCR 均为 **CPU 密集**（§0.3：单页渲染 66 ms、PaddleOCR init 1.8 s） |
| 下限 | **1**（1 即「串行基线」，§7 AC-04 的对照臂） | 并行必须能与串行**逐条一致**，故串行模式**必须保留可跑** |
| 队列形态 | **进程内队列**或**本地持久队列**（形态由 Kong 定） | 本文件只约束**可见行为**（§3 S-4/C 的 E5 与 §2.3 断点必须落盘） |

### 5.2 OCR 实例：全局单例 → **每 worker 一实例**

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 实例数 | **1 个全局单例**：`processor.py` 行 **20–23** `_get_ocr()`（`global _ocr_instance`） | **每 worker 进程内 1 个实例**（**进程内单例、跨进程不共享**） |
| 为什么必须改 | 全局单例在**多进程**下**不成立**（每进程有独立内存空间，「全局」只是**进程内**的全局）；且现状「单核串行」下它就是**唯一实例**，扩 worker 后自然要**每 worker 一份** | —— |
| 单实例代价（**实测**） | **init ≈ 1.8 s**；**常驻 RSS ≈ 0.70 GB**；**峰值 RSS ≈ 0.81 GB** | 8 个 worker ⇒ **≈ 6.5 GB**（按峰值 0.81 GB × 8 ≈ 6.5 GB），**占 16 GB RAM 的 ≈ 41 %** |
| **`cpu_threads` 取值（v1.3 收口｜1b-i **G-9**）** | 规范未写（§5.2 只说「每 worker 一实例」） | **`cpu_threads=2`**（**≤2 上限**）；**不得**回归 `_common_args` 的默认 10。**依据**：§5.4 最优臂 `B_nodoc_w4_ct2`（单页 **2.481 s / 页、3.49×**）；`w=4` 到顶亦与该取值同源（PaddleOCR 内部线程 × 进程数超订） |
| 初始化时机 | 现状在首次 OCR 时 lazy init | **worker 启动即预热**（避免首个 chunk 承担 1.8 s 抖动）；**不得**在每页 / 每 chunk 重新 init |
| 模型与联网 | PP-OCRv6_medium_det + rec，**模型本地缓存**（`~/.paddlex/official_models`），**全程不联网下载、不上传** | **保持**（feicui 定位为本地工具；与平台规范 §9.1「本地运行，不上传外网」一致） |

### 5.3 内存上限与单 job 并发上限

| 项 | 口径 | 依据 |
| --- | --- | --- |
| **单 job 并发上限＝1** | **同一本书同时只允许 1 个 `RUNNING` job** | 防同书双写、防重复影像（§2.4 / §3.2 S-5） |
| **全局 job 并发上限＝worker 数** | 同时在跑的 job 数 ≤ worker 数（**默认 4**；**v1.3 原位更正**：原记「默认 8」**已被 v1.3 取代**，与 §5.1 同源），超出的 job 排队 `QUEUED` | 队列语义，非资源浪费 |
| **单 job 页内并发上限＝1** | 页内多印**串行**处理（同一页不并发） | 现状 `stamps.idx` 的顺序语义 + bbox 依赖（页内先检测后切图） |
| **不得全量累积内存** | **现状问题**：`process_pdf` 把结果**全量累积在 `all_results` 内存里**，最后一并落库（派单基线） | ⇒ 目标形态必须**按 chunk 流式落库**（§4.3）；判负形态＝「页数增长而内存线性增长、且末尾才提交」 |
| **内存预算（草案，待裁定）** | 全机可用 **16 GB**；`worker 池（**4** × 0.81 GB ≈ **3.3 GB**；**v1.3 原位更正**，原按默认 8 计 6.5 GB）` + 接口层/前端 + 系统 ⇒ **worker 池 RSS 上限 ≈ 8 GB**（约 50 % RAM；**该上限系 §9-R3 / R13 的 Jing 草案，v1.3 未改其数值**——按 `w=4` 实际约 3.3 GB，8 GB 为**宽松天花板**）；超限时**降 worker 数**而非降协议 | 峰值 RSS 为实测值（§0.3）；**阈值同属 Jing 草案**（§9-R3/R4 一并裁定） |
| **磁盘预算** | `output` 现 **3.4 MB** / 可用 **169 GB** | §4.4 阈值 ① 以 50 GB 为换栈触发点 |

### 5.4 性能基线口径（**v1.1 新增**｜**实测 / 推断必须分开标注**）

> **来源**：`feicui/spike-ocr/REPORT.md` + `feicui/spike-ocr/results.json`（阶段 0b「OCR 成本归因 spike」）。**该目录属其它角色已验收证据，本版只读引用、不得改动**；**Jing 未复跑该 spike**——下表「性质」列中「实测」项系**引自上列文件**、「推断」项系**本文件据实测换算**。**引用本表时必须连性质一起引用**（§0.2 / §8）。

| # | 口径 | 数值 | 性质 | 来源 |
| --- | --- | --- | --- | --- |
| 1 | **单页现状（单进程串行）** | **8.668 s / 页**——render **0.1587 s** / detect **0.0317 s** / **OCR 8.4777 s（占 97.80%）** | **实测**（引自 spike；Jing 未复跑） | `spike-ocr/REPORT.md` §7 成本模型 + `results.json` |
| 2 | **单页最优配置**（关 doc 预处理 + `w=4` / `cpu_threads=2`） | **2.481 s / 页（3.49×）**，OCR 占比降至 **92.33%** | **实测**（同源，权威臂 `B_nodoc_w4_ct2`） | 同上 |
| 3 | **并行收益与「到顶」** | `w=1 / 2 / 4 / 8` ＝ **1.00× / 1.82× / 2.72× / 3.20×**；**`w=4` 到顶、`w=8` 无收益**（单枚成本膨胀 **+114%**、效率 **40%**，疑 PaddleOCR 内部线程 × 进程数超订） | **实测**（同源） | 同上；**亦为 §7 AC-04 钉 `N=4` 的依据（依据 2026-09-20 实测）** |
| 4 | **900 万页外推** | 现状单核 **902.9 天**；最优配置（`w=4` / `ct=2`）**258.5 天** | **推断**（由实测单页成本 × 900 万页线性外推；**非实测端到端跑 900 万页**） | 本文件据 1 / 2 换算 |
| 5 | 单本换算 | 544 页 ≈ **78.6 分钟**；3000 页 ≈ **433 分钟** | **推断**（同 1 换算） | 本文件换算（与 §0.3 解析吞吐同源） |

**v1.3 收口｜doc 预处理开关（1b-i **G-8**）**：开关名 **`FEICUI_DOC_PREPROCESS`**，**默认 = 1（开）**＝PaddleOCR 默认＝**现状行为**（**默认不得静默变化**）；`=0` 需**显式**开启。**实测**：关闭后**识别文本会变**——但**是样本相关的**：页 20–21 样本 **1/8 条文本不同**、页 63–64 样本 **0/10 条不同**（质检侧独立复现，`qa-recheck/p1b-neng/REPORT.md` §5 / O-3）；**bbox 无一行不同**。**纪律**：**任何「改默认值」的动议都必须先补样本级精度验收**（否则省下的是时间、丢掉的是释文）。

**纪律**：① **性能类读数一律标「实测」或「推断」**（本表「性质」列即为此用）；**未标性质者视为未定义读数**；② **不得用渲染耗时（0.16 s/页 级）外推全量**——该做法会低估约 **60 倍**（瓶颈是 OCR、不是渲染；spike 结论）；③ 本表**只作口径登记**，**不构成换栈、调参或排期依据**（换栈阈值见 §4.4、worker 数见 §5.1，两者均**待裁定**）。

---

### 5.5 惰性 OCR 替身口径与冷启动测量口径（**v1.6 新增**｜F-2 / F-3）

> **只读引用声明**：本节全部读数**引自** `ops/kong_square_crop_coldstart_raw.txt`（**6,561 B / 75 行**，脚本自记时点 **2026-09-20T17:25:31+08:00**）与 `ops/kong_square_crop_evidence.md`（**24,666 B / 311 行**，自记时点 2026-09-20 17:2x）；**Jing 未复跑、未复测**；**证据自记的 PASS 结论只引用、不背书**（验收归 Neng）。

#### 5.5.1 F-3 · 冷启动测量口径（**正式采纳，硬性**）

> **背景（为什么必须定口径）**：**「冷启动耗时」在本工程缺少统一测量口径**——**页缓存冷热可使同一段代码的中位数相差约 2 倍**（同一段代码实测到 **2.964 s** 与 **1.429 s** 两个中位数，见 `kong_square_crop_evidence.md` §3.4 / 缺口 G-3）。**不定口径 ⇒ 同一改动可被量出「降 92%」也可被量出「降 83%」，复检者无法定判。**

| # | 约定（硬性） | 判负形态（复检者可机械判） |
| --- | --- | --- |
| 1 | **同机 A/B**：**同一台机器、同一时段、同一输入样本**下做两臂对照；**唯一变量 ＝ 被测开关**（本项 ＝ `FEICUI_SQUARE_NO_LAZY_OCR`） | 两臂**不同机 / 不同输入样本 / 同时改了第二个变量** |
| 2 | **交错多轮**：两臂**交替执行、各 ≥ 3 轮**（**不得**跑完全部 A 再跑全部 B——**页缓存预热会系统性偏向后跑的臂**） | 证据里 A 臂连续 3 次后才出现 B 臂（**即非交错**） |
| 3 | **取中位数**：报**中位数**，**不报均值、不报单次最好值**；**并给出全部轮次原始值** | 只给单次最好值 / 只给均值；或**不给全部轮次原始值** |
| 4 | **同时给两个口径**：**「绝对基线」**（改前原码在同一基准上的实测）**与「相对 A/B」**（同机交错的两臂中位数）**必须同时给出、不得混用** | **只给一个口径**；或**把两个口径混用**（如拿绝对基线的 s 值当相对 A/B 的分子） |
| 5 | **输出等价性必须一并取证**：耗时不单独看——**必须同时给「输出 `sha256` 不变」**（见 §5.5.2 硬要求 4） | **只给耗时、不给输出 `sha256` 不变**（**性能改善而输出变了＝实质缺陷**） |
| 6 | **起点一致**：两臂的计时**起点 / 终点必须同构**（含不含解释器启动须写明） | 用 `time` 类外部测量覆盖**不同起点**却声称可比 |

**本项实测（只读引用，原始读数见 `kong_square_crop_coldstart_raw.txt` 第 2 段）**：

| 口径 | 值 | 备注 |
| --- | --- | --- |
| **A 臂**（惰性 OCR 生效 / 优化后）中位数 | **0.260 s** | 各轮 `0.276 / 0.260 / 0.251` |
| **B 臂**（关惰性 / 模拟优化前）中位数 | **1.724 s** | 各轮 `2.085 / 1.724 / 1.409` |
| **相对 A/B（同机、交错）** | **1.724 s → 0.260 s（降 1.464 s，84.9%）** | **同一次运行、同一机器负载 ⇒ 归因最干净** |
| **绝对基线（改前原码直接跑）** | **2.964 s → 0.242 s** | 首轮 4.256 s（**文件系统缓存冷**），后两轮 2.964 / 1.831 s ⇒ 中位 2.964 s |
| **输出候选 `sha256`** | **`b540bf974bceca6aa1358f6f914d773a2983d3f83337e23255dfb3415824aad5`** | **改前 / 改后逐字相同**；全轮次全模式一致 |

> **口径分歧登记（如实，不粉饰；→ §9-R20）**：`server/README.md` **§12.6** 写作 **1.429 s → 0.242 s（−83%）**，而 `ops` 侧证据的**绝对基线**为 **2.964 s → 0.242 s**、**相对 A/B** 为 **1.724 s → 0.260 s**——**三处读数出自同一批实测的不同轮次**（页缓存状态不同，见 G-3），**互不矛盾但口径不一**。**本文件登记为：同一代码段的两个绝对基线中位数（2.964 / 1.429）＋ 一个相对 A/B 值（1.724 → 0.260）**；**建议后续统一按本节口径出数**（两个口径同时给）。**是否统一 README §12.6 的表述 → §9-R20。**

#### 5.5.2 F-2 · 惰性 OCR 替身口径（`server/app/ocr_lazy.py`）

**为何可惰性（病因与可行性）**：`processor.py` 顶部 `from paddleocr import PaddleOCR` 是**模块级 import**，会拉起整套推理栈（**实测 `import paddleocr` ≈ 1.28 s**，`import processor` ≈ 1.4 ～ 3.2 s）；而**本端点只走 `processor.detect_stamp_regions`**（HSV 红掩膜 → `MORPH_CLOSE` → `findContours` → 面积 / 长宽比 → `_pad_bbox`），**纯 `cv2` / `numpy`、一次 OCR 都不做** ⇒ **这笔开销纯属浪费**。

**做法（口径）**：在 `import processor` **之前**把 `sys.modules["paddleocr"]` 换成**惰性替身模块**；其 `PaddleOCR` 是 **shim 类**，**只有真正被实例化时**才弹出自身、import 真包，并以**原样 args / kwargs** 构造真 `PaddleOCR`；实例对任意属性 / 方法**透明转发**。

**硬要求（可机械判负）**：

| # | 要求 | 判负形态 |
| --- | --- | --- |
| 1 | **`processor.py` 字节未动**（**md5 `31ec6cdb907ac60b63e814d7b6122c24`**，与既有 QA pin 及 `server/REPORT_1b-i.md` §1 逐字一致）——**实现方式是把 `paddleocr` 这个「模块名」换成替身，不是改 `processor.py` 源码** | **`processor.py` 的 md5 与 QA pin 不等** |
| 2 | **`config/templates.json` 字节未动**（md5 `20acf9162baf0a0c4e5d6e164681b5ce`）——**没有偷偷塞 `default` 键来「修」标签**（来源标签走「如实标注」，见 §3.14.6） | `templates.json` md5 变化**且未走 §9-R18 裁定** |
| 3 | **检测口径不变**：`detect_stamp_regions` **走同一份 `processor.py` 源码**（**未复制、未改写**） | 出现**第二份**红掩膜 / 检测实现 |
| 4 | **`processor.py` 现有函数默认行为不变**：`_get_ocr()` 的构造参数（`use_angle_cls=False, lang="ch"`）、**单例缓存语义**、**真包缺失时抛 `ModuleNotFoundError`** 的行为**全部保持** | 构造参数被改写（如 `use_angle_cls=True`）；或单例缓存语义被改（每次重建）；或**真包缺失时不再抛 `ModuleNotFoundError`**（被替身吞掉） |
| 5 | **输出字节不变（等价性判据）**：**候选 `sha256` 在「开替身 / 关替身」两模式下全池唯一且与改前逐字相同**（值见 §5.5.1 表末行）——**这是本项的等价性判据，不是耗时** | **候选 `sha256` 与改前不一致**（**含两模式之间不一致**）；或**只以耗时证明等价** |
| 6 | **可一键回滚**：**`FEICUI_SQUARE_NO_LAZY_OCR=1` ⇒ 不装替身、回到优化前行为** | **开关不生效 / 开关被删**（**回滚口不得删除**） |
| 7 | **证据脚本纪律（与玺爱侧 `xiai/docs/xiai.spec.md` §1.3 第 9 条同源）**：**自测 / 证据脚本不得自建产品已实现的判定副本**（**格式判定一律调产品真源**） | 脚本内出现自建的魔数表 / 字节比较 / `magicOf` 类函数并**以其结论判产品** |

#### 5.5.3 明确「不做」的优化面（**如实登记，避免被当漏实现**）

| 项 | 状态 | 理由（口径） |
| --- | --- | --- |
| 把 `pymupdf`（≈ 0.15 s）也惰性化 | **不做** | `worker.feicui_worker` 与 `processor` 都在模块级 `import pymupdf` 且被 `render_page` 等**真实使用**；替身方案须**逐函数验证等价**，**风险 > 收益** |
| 让 runner 不 import `worker.feicui_worker`（省 `pymupdf`） | **不做** | 会破坏 §1.2 I-1「**同一份 `encode_webp` 实现**」这一**更重要的口径**（**不许复制算法**） |
| 常驻子进程 / 进程池（消掉解释器启动 ≈ 0.15 s） | **不做** | 与 §1.1 / §3.2 S-4「**一次性子进程、无守护无池**」相冲突；**「用完即退」本身是红线级的隔离手段** |
| `min_area_source` 里 `AREA_SCALE` 的展示位数（`:.6f`） | **保留** | 仅展示用；**实际生效值走 `min_area_eff`（全精度）**；改它会变更标签文本、非优化目标 |

**本节状态**：**口径与登记**；**落地状态 ＝ 已定、已具备（引证据文件，Jing 未复跑）**；**验收执行归 Neng**；**本节不含任何「本轮已通过」结论**（**证据自记的「13 条断言」「11/11 PASS」等只引用、不背书**）。

## 6. 端口与登记口径

### 6.1 端口分配（本规范口径）

| 服务 | 端口 | 说明 | 实测空闲证据 |
| --- | --- | --- | --- |
| **feicui 前端（Vue）** | **5195** | **主入口**（Kevin 裁定）；`strictPort:true`，**不得**静默回退 | `lsof -nP -iTCP:5195 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5195` → **CLOSED**（核验时点 2026-09-20 10:38） |
| **feicui API（FastAPI）** | **5196** | **本文件与 `PORTS.md` v1.8 同轮新分配**（**原表无 5196、非占用、非保留**；登记行见 **PORTS.md §2**——启动命令 / cwd / group / directUrl 五要素与本文件 §6.2 同源）。**原 v1.0 句「PORTS.md 内**无** 5196 条目」已被 v1.1 取代**：该句写成时 PORTS.md v1.8 的登记行尚未落盘（两文件 mtime 相差 28 秒），既与同文件 **§6.3**「Jing 本版已追加登记行」自相矛盾，也违反 §0.1「不一致时以 PORTS.md 为准并当场修本文件」（D-2） | `lsof -nP -iTCP:5196 -sTCP:LISTEN` → **无监听**；`nc -z 127.0.0.1 5196` → **CLOSED**（同一时点） |

**为何选 5196**：① **实测空闲**（上表）；② **不在保留段**（PORTS.md §1(c)：保留仅 **5173 / 5174**）；③ **不与既有条目相邻冲突**（5195 前端 / 5197-5198 为 jiazu legacy 退役中 / 5199 jiazu H5）；④ **与前端 5195 同段**便于辨识。**同时实测 5200 / 5201 / 5202 亦空闲**（留作后备；`jiazu/README.md` 示例曾用 5201，故**优先 5196**）。

### 6.2 与 `ctrl/index.js` `services` 表五要素的对应（**登记形态，落地由 Kong**）

| 五要素 | `feicui`（前端） | `feicui-api`（后端） |
| --- | --- | --- |
| **sid** | **`feicui-web`**（**v1.3 原位更正**：原记 `feicui` **已被 v1.3 取代**；核验时点 2026-09-20 13:08，证据＝`ctrl/index.js` 第 58 行） | `feicui-api`（与实测一致，未变） |
| **端口** | `5195` | `5196` |
| **启动命令** | `npm run dev`（Vite，`server.port=5195` + `strictPort:true`）（**v1.2 补充**：**1c 起 `feicui/web/vite.config.js` 另设 `base: '/feicui/'` 与 `server.hmr.clientPort: 5195`**——见 §6.4；端口 / `strictPort` **不变**） | `./venv/bin/uvicorn app:app --host 127.0.0.1 --port 5196`（**形态草案**，入口文件名由 Kong 定）**（v1.2 收口｜R-1）**：**实际口径**＝`cd /Users/kevin/bistro/xiai/feicui/server && ./.venv/bin/python -m app.main`（等价 `uvicorn app.main:app`；host `127.0.0.1` / port `5196` **不变**）——**解释器＝`server/.venv/bin/python`、cwd＝`feicui/server`**；**原「`./venv/bin/uvicorn app:app`（形态草案）」已被 v1.2 取代**（理由：`feicui/venv/bin/*` console script 因 shebang 失效、且其中**无 fastapi**；完整依据与解释器矩阵见 **§6.5**）（**v1.4 路径收口**：**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**）（核验时点 **2026-09-20 14:59**：`ctrl/index.js` 的 `feicui-api.cwd` 即此值） |
| **cwd** | `/Users/kevin/bistro/xiai/feicui/web`（**计划路径**）（**v1.2 收口**：该工程目录**已建立**——核验时点 2026-09-20 12:00，`stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**；原「**计划路径 / 尚未建立**」表述**已被 v1.2 取代**。**但面板托管（`index.js` `services` 表）仍未落地**：同一时点 `grep -n feicui ctrl/index.js` **零命中** ⇒ 本行的**落地状态＝工程已建立 · 面板托管未落地**） | `/Users/kevin/bistro/xiai/feicui`（**v1.2 收口｜R-1**：**实际 cwd ＝ `/Users/kevin/bistro/xiai/feicui/server`**——原记 `feicui` 根目录**已被 v1.2 取代**，见 §6.5）（**v1.4 路径收口**：本行 `cwd` **三处**已**原位更正为 `xiai/...`**（**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**）；核验时点 **2026-09-20 14:59**，`ctrl/index.js` 的 `feicui-web.cwd` ＝ `/Users/kevin/bistro/xiai/feicui/web`、`feicui-api.cwd` ＝ `/Users/kevin/bistro/xiai/feicui/server`；§6.2 表下见 **v1.4 注**） |
| **env** | **无**（端口写 `vite.config.*`，不依赖 env） | `PORT=5196`（如需）；**须继承 `PATH`**（面板 spawn 语义，PORTS.md §3 排错要点） |
| **`group`**（必填） | `shu`（**与 5164 同组**——feicui 属印索项目族、位于 `bistro/shu/` 之下） | `shu` |
| **`directUrl`**（可选） **`http://localhost:5195/feicui/`**（**v1.3 按实况回填**：实际值**带 `/feicui/` 前缀**——因前端 `base: '/feicui/'`，直跳必须带前缀；核验时点 2026-09-20 13:08，证据＝`ctrl/index.js` `feicui-web.directUrl`。原记「`http://localhost:5195`（**与 §2 既有 6 条同形**）…」**已被 v1.3 取代**） | **无**（后端服务不设 directUrl，与 `jiazu-api` / `jinli-api` / `liwu-proxy` 同例） |

> **⚠ 落地顺序纪律（必须先读）**：**在 `feicui/web` 前端工程目录真实存在并可 `npm run dev` 之前，`feicui` 行不得写入 `index.js` 的 `services` 表**——否则面板**批量启动 / `startAll`** 会因 cwd 不存在而失败，**破坏「面板托管 N/N 全监听」的既有判据**（PORTS.md §3.1 / §4-P6 的口径）。**登记顺序＝先登记（本文件 + PORTS.md）、再落地工程、最后入 `services` 表**（Kong）。

> **§6.2 表下 v1.3 注 —— 落地实况与「池」的托管口径**：
> ① **落地实况（核验时点 2026-09-20 13:08；证据＝`ctrl/index.js`，md5 `55b101fc643ad06d4bfcb61e56d7710d`）**：`services` 表**已含** feicui 两条——**`feicui-api`**（`port: 5196`、`cmd: './.venv/bin/python'`、`args: ['-m','app.main']`、`cwd: /Users/kevin/bistro/shu/feicui/server`、`env: {PORT:'5196'}`、`group: 'shu'`、无 `directUrl`）与 **`feicui-web`**（`port: 5195`、`cmd: 'npm'`、`args: ['run','dev']`、`cwd: /Users/kevin/bistro/shu/feicui/web`、`group: 'shu'`、`directUrl: 'http://localhost:5195/feicui/'`）。**⇒ v1.2 所记「面板托管未落地（`grep` 零命中）」已被 v1.3 取代**（**改动系 Kong 执行；Jing 未改 `ctrl/index.js` 一字**）。**该文件的 mtime 在本轮核验窗口内仍在变化**（并行写入），**故本注只对该 md5 时点成立**。**（v1.4 路径取代 + 实况刷新**：上列引文系 **13:08 时点、锚定 md5 `55b101fc643ad06d4bfcb61e56d7710d`** 的**逐字快照式引文**，按「历史 / 快照行只增不改」**保留原文**；**但其中的 `cwd` 旧路径（`shu/feicui/**`）已被 v1.4 取代**——**现读作 `/Users/kevin/bistro/xiai/feicui/**`**（**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**；**Jing 未执行改名**）；**§6.2 表本体的 `cwd` 已原位更正为 `xiai/...`**，**实况刷新见下条 v1.4 注 ② / ③**）**
> ② **「池」不进 `services` 表**（**v1.3 定案**）：`feicui-pool` 是**无端口**的常驻 daemon ⇒ **不在面板的「端口服务」托管语义内**；由**运维 / 脚本**拉起（`cd feicui/server && ./.venv/bin/python -m app.pool --workers 4`），**生命周期独立于接口层**（AC-11 的形态前提，§1.3 表）。**若将来要求面板托管池**，须先由 Zang 裁定「无端口服务是否入 `services` 表」（本文件不自行改该语义）。
> ③ **三处同步纪律仍适用**（§6.3）：端口 / 启动命令 / cwd 任何一处变化必须**一次改齐**①项目配置 ②`PORTS.md` ③本文件。

> **§6.2 表下 v1.4 注 —— `index.js` 实况刷新 + 「池」的托管裁定收口（Zang 已定案）**：
> ① **§6.2 表本体已原位更正**：`feicui-web` 行 `cwd`（2 处）与 `feicui-api` 行 `cwd`（3 处）/ 启动命令（1 处）的旧 `shu` 路径**已由 v1.4 取代为 `xiai/...`**（**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**）；**行内其余要素（端口 5195 / 5196、命令、`group: 'shu'`、`directUrl: 'http://localhost:5195/feicui/'`）一字未改**。
> ② **`index.js` 实况刷新（照磁盘实测写，不照旧文）**：核验时点 **2026-09-20 14:59**，`ctrl/index.js`（md5 `143137f25c717596d4a8260db686794f`、**52,651 B**、mtime **2026-09-20 14:49:58**）的 `services` 表共 **12 条**，其中 **feicui 族 3 条**——**`shu`**（sid **未改**；`port: 5164`；`cwd: /Users/kevin/bistro/xiai/web`；`group: 'shu'`；`directUrl: 'http://localhost:5164'`）、**`feicui-api`**（`5196`；`cmd: './.venv/bin/python'`；`args: ['-m','app.main']`；`cwd: /Users/kevin/bistro/xiai/feicui/server`；**`env: {PORT:'5196', FEICUI_DB: '/Users/kevin/bistro/xiai/feicui/yinpu.db'}`**；`group: 'shu'`；无 `directUrl`）、**`feicui-web`**（`5195`；`cmd: 'npm'`；`args: ['run','dev']`；`cwd: /Users/kevin/bistro/xiai/feicui/web`；`group: 'shu'`；`directUrl: 'http://localhost:5195/feicui/'`）。**⇒ v1.3 注 ① 记的「feicui 两条」已被 v1.4 取代为「三条」**（新增 **`shu` 条**——其 **sid 未改**、`cwd` 已由 Kong 指 `xiai/web`）；**改动系 Kong 执行，Jing 未改 `ctrl/index.js` 一字**。
> ③ **「池」不进 `services` 表 ＝ Zang 已定案（v1.4 收口，采纳选项 ①）**——**上条 v1.3 注 ② 的「若将来要求面板托管池，须先由 Zang 裁定」至此收口**。**裁定内容**：`feicui-pool` **仍不由面板托管**；改为**由 API 提交 job 后异步拉起**——`feicui-api` 在 **E1 建 job 成功（201）后**异步、**detached** 拉起一次 `cd /Users/kevin/bistro/xiai/feicui/server && ./.venv/bin/python -m app.pool --workers 4 --drain`（**子进程 env 显式带 `FEICUI_ALLOW_PROD_MIGRATE=1` 与 `FEICUI_DB`**；**不给就不写、不绕过闸门**）；**API 启动时扫一次 `QUEUED` / `RUNNING`，有则同样补跑**（防 API 重启后 job 被遗忘）；**池跑完自行退出、不常驻**。**⇒ 原 v1.3 注 ② 的「由运维 / 脚本拉起」已被 v1.4 取代**（池不再以「人工 / 脚本拉起」为运行前提）。
>   **「已有池在跑」＝正常分支**：池自身以 `flock` 占 `server/.run/pool.state.lock`，重复拉起者**立刻以退出码 5 退出**——**该码不得当故障**（不重试、不堆进程、不告警升级）；`poolctl` 另有**「至多 3 次 / 每次间隔 2.5 s」的有界补跑兜底**（只在「仍有活跃 job 且无池在跑」时再拉一次，次数有上界）。**裁定理由**＝**面板的健康模型是端口可达性**（`state` / `portOpen` / `occupier` / `startAll` 全按端口建），**无端口常驻服务入表会污染「面板托管 N/N 全监听」的既有判态**；**且**池必须是**独立于接口层**的进程（**AC-11 的形态前提**，§1.3 表），**此点不受托管方式影响**。
>   **依据（可复跑）**＝`feicui/server/app/poolctl.py`（池拉起器：异步 / detached / 写正式库授权变量 / 双起保护 / 有界补跑兜底）+ `feicui/ops/1c/1c_double_start_evidence.txt`（**2026-09-20 14:46:59** 实测：人为再起同库同锁的池 ⇒ **`rc=5`（期望 5）**，stderr 明写「**这是正常分支**」；同批两单 A / B 均 **DONE**、`stamps` 全表 **89**、活跃 job **0**）。**对端登记**＝`ctrl/PORTS.md` **§4-P9（v1.12 收口）**。

### 6.3 真源与同步责任

| 真源 | 内容 | 同步责任 |
| --- | --- | --- |
| `ctrl/PORTS.md` | **端口文档真源** | **Jing** 本版已追加登记行（含端口 / 启动命令 / cwd / group / directUrl + 变更记录），并注明**运行时真源由实现侧 Kong 同步落地** |
| `ctrl/index.js` `services` 表 | **运行时真源** | **Kong**（Jing 不改代码）；落地后本文件 §6.2 与 PORTS.md **按实况回填** |
| 本文件 §6 | feicui 侧端口口径 | **Jing** |
| `feicui/web/vite.config.*` | 前端端口配置 | **Kong**（`strictPort:true`，**不得**回退 5173/5174——PORTS.md §1(c)） |

**三处同步纪律**（沿用 PORTS.md §1(b)）：任何端口变更必须**一次改齐** —— ① 项目自身配置 ② `PORTS.md` ③ 本文件（feicui 的 spec）。**只改其一即为口径漂移**。

### 6.4 `5164 /feicui` dev 代理（**已定口径**，v1.1 登记｜原 §9-R1 待裁项收口）

| 项 | 口径 | 依据 / 落位 |
| --- | --- | --- |
| **要不要** | **要**（**Kevin 已拍板**） | §9-R1 收口（R1 行已同步） |
| **落地时点** | **feicui 前端骨架起来那一刻**——即 `feicui/web` 工程真实存在、可 `npm run dev` 时**同步**；**当前目标不存在**（§9-R7），**故本轮不落地**（**v1.2 补充**：**该前提已于 2026-09-20 11:35:25 满足**——`feicui/web` 工程目录已建立（§6.2 cwd 行 v1.2 注）；**1c 已定、落地中（由 Kong 执行）**，口径原文见本表下 **v1.2 块**） | 与 §6.2 落地顺序纪律同源 |
| **实现形态** | 由 `shu/web` 的 **Vite `server.proxy`** 拦截 `/feicui` → **`http://127.0.0.1:5195`**；**不落 SPA 路由** | 代理属 **dev / 构建服务层**的转发，**不进 `src/router/**`** |
| **对平台路由与判据的影响** | **零**——平台规范 **§2.2 路由表仍 14 条**、**AC-88 / AC-89 扫描面不变**（两条按 `document.body.innerText` 扫那 14 条对外路由；代理**不新增对外路由**、**不渲染任何文案**） | 平台规范 §2.2 / §12 AC-88 / AC-89 |
| **生产部署** | **必须在网关做同构改写**（与平台侧 `consoleEntryRewrite` 同类已知坑：dev 生效而生产不生效 ⇒ 直达 404） | 平台规范 §2.3-6 / 附录 B（环境硬约束） |
| **性质（防误读）** | 属 **M1 冻结面之外的基础设施登记**，**不得当作功能变更**；落地时改的是 `shu/web/vite.config.js` | 平台规范 §1.7 表下 v1.23 注（M1 冻结只禁「功能与门禁变更」，基础设施登记不在其内） |
| **谁写代码** | **Jing 不改任何 `.js` / `vite.config.*` / `index.js`**；落地由 **Kong** 执行，落地后如有形态差异**按实况回填本表**（§6.3 同步责任） | §0.1 / §6.3 |

---


**§6.4 表下 v1.2 块 —— 1c 代理口径（Zang 已定；**原文照录、一字未改**，给实现侧照此执行）**：

> **Zang 已定的 1c 代理口径（原文，v1.2 照录）**：
> - `feicui/web/vite.config.js` 增 `base: '/feicui/'`，并设 `server.hmr.clientPort: 5195`（保留 host `127.0.0.1` / port `5195` / strictPort）；preview 同 base。
> - `shu/web/vite.config.js` 在 `server.proxy` 与 `preview.proxy` 各加键 `'/feicui'` → target `http://127.0.0.1:5195`，`changeOrigin: true`，**不 rewrite 前缀**（因为 feicui 侧 base 已为 `/feicui/`）。
> - **不新增任何 SPA 路由** → 平台 §2.2 路由表仍 **14 条**、AC-88 / AC-89 扫描面不变。
> - 生产部署须网关同构改写（同 console 入口的已知坑）。
> - **验收判据**：① 直连 `http://127.0.0.1:5195/feicui/` 返回 200；② `http://localhost:5164/feicui/` 返回 200 且为 feicui 页面（不是 SPA 404）；③ 14 条对外路由逐一仍正常；④ `npm run check:pricing` + `npm run smoke` + `npm run build` 全通过。

**Jing 附注（口径边界，不改上列原文）**：

| 项 | 口径 |
| --- | --- |
| **1c 落地时点** | **已定、落地中（由 Kong 执行）**。原 v1.1 记「落地时点＝feicui 前端骨架起来那一刻」——该前提**已于 2026-09-20 11:35:25 满足**（`feicui/web` 目录 birth）；**落地状态的读数以磁盘实测为准**（§0.2 / §8），见下「实测」行 |
| **落地实测（核验时点 2026-09-20 12:00–12:01）** | ① `feicui/web/vite.config.js`：`base` 命中（**第 80 行** `base: BASE`，`BASE` 为其上注释所定义之 `/feicui/`）、`hmr: { clientPort: PORT }`（**第 97 行**）、`host: '127.0.0.1'` / `port` / `strictPort: true` **保留**；② `shu/web/vite.config.js`：`server.proxy` 与 `preview.proxy` **各含** `'/feicui'` → `FEICUI_PROXY = { target: 'http://127.0.0.1:5195', changeOrigin: true }`（**第 48 / 53 行**），**无 rewrite**；③ 判据 ① `curl -o /dev/null -w %{http_code} http://127.0.0.1:5195/feicui/` ⇒ **200**；判据 ② `… http://localhost:5164/feicui/` ⇒ **200**；④ 判据 ④ 的 `npm run check:pricing` / `smoke` / `build` **由 Kong / Neng 侧执行，Jing 未复跑（如实标注）**。**证据**＝`grep -n` 输出 + 三条 `curl` 状态码（本注即留档） |
| **性质（防误读）** | 属 **M1 冻结面之外的基础设施登记**（平台 §1.7 表下 v1.23 封版口径只禁「功能与门禁变更」），**不得当作功能变更** |
| **谁写代码** | **Jing 不改任何 `.js` / `vite.config.*` / `index.js`**；两处 `vite.config.js` 的改动系 **Kong** 执行（本版只登记口径与实测事实） |

### 6.5 解释器矩阵（**v1.2 新增**｜登记项 R-1 的正式口径）

> **收口来源**：`feicui/server/REPORT_1a.md`「登记项 R-1」+ `server/README.md` §2。**性质**＝**实现实际口径升为规范口径**（原 §6.2 为「形态草案 / 入口文件名由 Kong 定」；实际偏离**已显式上报**，本轮按 §0.4 收口；§6.2 原草案句**原文保留并留痕**）。

| 角色 | 解释器 | 装了什么 | 为什么 |
| --- | --- | --- | --- |
| **接口层 `feicui-api`（5196）** | **`server/.venv/bin/python`**（**不是** `feicui/venv`） | `fastapi` / `uvicorn` / `pydantic` 等——**3 个直接依赖、freeze 13 行** | §1.2 I-2：**接口层不进热路径、不装 OCR 栈**。**实测**（核验时点 2026-09-20 12:00，证据＝`server/.venv/lib/python3.11/site-packages` 计数）＝**13** |
| **worker（阶段 1b）** | **`feicui/venv/bin/python`** | `pymupdf` / `paddleocr` / `paddlepaddle` / `numpy` / `opencv-python` / …（**86 行 freeze**） | §1.2 I-1：解析与 OCR 仍是**同一份 Python 实现**；§5.2：每 worker 一实例 |
| **feicui Streamlit（退役中）** | `feicui/venv/bin/python` | 同上 + `streamlit 1.63.0` | §1.4 退役边界 |
| **接口层派生 `total_pages`（E1）** | **子进程调 `feicui/venv/bin/python`** | — | `server/app/**` 内**无静态** `import pymupdf` / `fitz`（实测 0 命中）；**不得**为读页数把 PyMuPDF 装进 `server/.venv`（§3.1 表下注 G-5） |

**硬约束（Zang 追加口径 1 / 2，本轮正式入规范）**：① **不得**把新依赖装进 `feicui/venv`，也**不得**升级 / 降级其中任何既有包（`spike-ocr/` 的性能基线全部依赖这套版本）；② `server/.venv` **可重建**，命令＝`uv venv .venv --python 3.11` → `uv pip install --python .venv/bin/python -r requirements.txt` → `uv pip freeze --python .venv/bin/python | wc -l`（实测 **13**）；③ `server/.venv` 已列入 `server/.gitignore`（仓库当前非 git 仓库，为将来预置）。
**判负形态**：接口层进程内出现 OCR 栈 / PyMuPDF；或 `feicui/venv` 被就地改包（与 §7 AC-13 的「环境不被污染」面同源）。

---

## 7. 验收判据（AC）——**逐条可机械判负**

> **用法**：每条给出「**判据**（可机械复算）」＋「**证据形式**（须落盘留档）」＋「**判负形态**」。**判负形态命中即 FAIL**，不做「偶发 / 轻微 / 人工点测已确认」类豁免。**证据目录口径**沿用平台侧：留档于项目内证据目录（**不得**以 `/tmp` 临时物作证据）。

| AC | 判据（可机械复算） | 证据形式 | 判负形态（命中即 FAIL） |
| --- | --- | --- | --- |
| **AC-01 同书重跑幂等（行级）** | 同一 `pdf_path`、同一 `page_range` **连跑两次**；第二次结束后 `select count(*) from stamps where pdf_name=?` **不变**，且第二次的 `counters.inserted == 0` | 两次跑前/跑后的 **键集合（`(pdf_name,page,idx)` 去重后集合）** + **逐字段内容指纹**（对该范围内全部行的有序全字段导出做 sha256）+ 独立复算的 `count(distinct …)` + E2 的 `counters` 快照 | 条数增加；或 `inserted > 0`；或旧行任一字段被改写。**（v1.3 原位改写｜G-e 待定性）**：**判据＝「键集合与内容不变」**，**「行数不变」不再作判据**——**理由**：实测存在「**同区间重解析行数 ≠ 库内行数**」（库 12 → 解析 13；库 30 → 解析 31）而**旧行零改写成立**的观测，其成因**未定性**（检测非确定性 vs 旧解析少一行，§9-**R12**，Zang 已另派质检定性）。**在定性前，判负形态只绑定「旧行被改写 / 新键产生重复行 / `inserted > 0`」**；**新增行数若源于新键，属允许面**（§2.4 表下注）。留痕：原 v1.2 判据的「第二次结束后 `count(*)` 不变」一句**已被 v1.3 取代**（该句仍作为**观测项**要求一并留档，**不作判负依据**） |
| **AC-02 同书重跑幂等（影像级）** | 两次跑后，影像目录**文件数不变**，且各文件 `sha256` **逐一不变** | 跑后 `find … -type f \| sort` + `sha256sum` 清单两次对比 | 文件数增加；或同名文件内容变；或出现同内容不同名的新文件 |
| **AC-03 断点续跑不重复** | job 跑到 **X ∈ {25, 50}**（**两个百分点各至少一次**；**v1.1 钉值**——原 v1.0 写「**X %（0 < X < 100）**」为自由变量，**已被 v1.1 取代**）后 **SIGKILL** 全部 worker → 重启同一 job 续跑至结束；最终行数 == **串行一次跑完**的行数，且 `count(*) == count(distinct pdf_name\|\|'\|\|'\|\|page\|\|'\|\|'\|\|idx)` | **（v1.3 钉定｜G-f 收口）** 点位口径＝**`done_pages / total_pages`**（**唯一**定义，**不采用**「连续已提交前缀」口径；两者在 `chunk_size>1` 且 `w>1` 时**结果不同**——实测 **42.9% / 57.1%（已提交页）vs 28.6%（连续前缀）**）；**`{25%, 50%}` 两点各至少一次**；**允许 ±1 页容差**，但**证据里必须写明实际百分比**（例：25% 点实测 42.9%、50% 点实测 57.1%，两点分别落 `chunk_size=2/w=4` 与 `chunk_size=1/w=2`，见 `REPORT_1b-i.md` §5-10 与 `evidence/1b_ii/46_reg_ac03_kill50_probe.json`）。事件时序（kill 时点 + 续跑起止）、键集合与内容指纹复算、重复性复算 SQL 输出 | 行数不等；或重复性复算不等；或断点之前的页**被重写**（字段 diff 非空） |
| **AC-04 并行 == 串行逐条一致（含 bbox）** | 同一本书、同一模板，在**空库**上分别以 **worker=1** 与 **worker=N=4**（**v1.1 钉值**；**依据 2026-09-20 实测**：阶段 0b 实测 `w=1/2/4/8` ＝ 1.00× / 1.82× / 2.72× / 3.20×，**`w=4` 到顶、`w=8` 无收益**——来源 `feicui/spike-ocr/REPORT.md` + `results.json`，见 §5.4；原 v1.0 写「worker=N」并依赖 §5.1 草案默认 **8** 与 §9-R4，属自由变量，**已被 v1.1 取代**）各跑一次；导出 `(pdf_name,page,idx,text,x1,y1,x2,y2)` 全字段、按 `(page,idx)` 排序后 **diff** | 两臂的导出文件（CSV/JSONL）+ `diff` 原始输出（须 **0 差异**） | 任一行**任一字段**不同；或行数不同；**特别地 `x1y1x2y2` 任一分量不同即 FAIL**（bbox 必须逐条一致） |
| **AC-05 进度真实（不得假进度）** | 任意时刻 E2 的 `done_pages` **必须**等于「按已完成 chunk 记录复算的页数」；`state=DONE` 时 `failed_pages` **必须**为空；`progress_ratio = done_pages / total_pages` 与复算值**误差 ≤ 1 页** | E2 响应快照（含时间戳）+ 同刻库内 chunk 状态复算输出（**两者并排给出**） | 进度与复算不一致；或 `failed_pages` 非空而 `state=DONE`；或进度由计时器/估算推进（无法与库内复算对齐） |
| **AC-06 影像缺失清单可查** | E5 `?kind=image` 返回的 `count` **必须**等于「逐条 `os.path.exists(img_path)` 为假的记录数」的独立复算值 | E5 响应 + 独立复算脚本输出（同刻） | 两者不等；或该端点不存在 / 无法按此复算 |
| **AC-07 释文缺失清单可查** | E5 `?kind=text` 的 `count` **必须**等于 `select count(*) from stamps where text is null or trim(text)=''` **同范围**的独立复算值——复算式固定为 `select count(*) from stamps where pdf_name=? and page between ? and ? and (text is null or trim(text)='')`（`pdf_name` 与页区间＝**该 job 的** `jobs.pdf_name` 与其 `[page_from, page_to]`）。**（v1.2 原位改写｜G-3 收口）**：原 v1.1 的复算式为**全表**口径（`select count(*) from stamps where text is null or trim(text)=''`，**无** `pdf_name` 过滤），**已被 v1.2 取代**——**理由**：E5 是 **job 内该书**口径，在「**1 书 = 1 job**」（§2.1）下，同库有 3 本书时**全表口径恒 ≠ 本 job 口径**，判据**无法机械判负**。**实测证据**（快照 `state_50.db`，核验时点 2026-09-20 11:56；来源 `feicui/server/REPORT_1a.md` G-3 / `server/README.md` §6）：**全表 ＝ 77**（正是 v1.1 所钉基线）、**本 job（`tmp.pdf`，页 13–19）＝ 30**，**差 47**。**全表读数仅作历史留痕，不再作判据** | E5 响应 + **同范围**复算 SQL 输出（**须含 `pdf_name` 与页区间字面量**） | 两者不等；或复算 SQL **未带** `pdf_name` / 页区间过滤（**即以全表口径复算**）；或端点不存在 |
| **AC-08 必备 11 项覆盖可查** | E3 每条记录**必须**给出平台规范 **§9.3 的 11 项必填字段**（或明确给出 `missing_required[]` 原因）；**不得**静默缺字段 | E3 分页响应样本 + `missing_required` 逐条清单 + **§3.12 键路径对照表** | 缺字段且无 `missing_required`；**或键路径与 §3.12 冻结表不符**。**（v1.3 原位改写｜G-10 收口）**：**判负绑定面改为 §3.12 的冻结键路径**（顶层平台字段名 + `assets[].sha256` / `assets[].width` / `assets[].height` / `assets[].colorMode` / `assets[].batchId` + 顶层 `missing_required[]`）；**原「字段名与 §9.3 不一致（以平台规范为准）即判负」的写法已被 v1.3 取代**——理由：§9.3 的字段名是 **feicui 侧需补字段的语义名（snake_case）**，而记录内是**平台字段名（camelCase，§3.8 / §3.9 形态）**，**两套命名并存是既成事实**，按字面比对会把正确实现判负。**`missing_required` 一律用 §3.12 的 feicui 语义名**；**缺项清单为空数组的写法（`[]`）＝「无缺失」，不是「未实现」** |
| **AC-09 幂等键可独立复算** | 记录中的 `dedupe_key` **必须**等于按平台规范 **§9.4 公式**独立复算的值，**且** `bbox` **先按该书 `coord_dpi` 归一化为 pt** 再 `quantize(·,1pt)` | 独立复算脚本输出 + 逐条 diff（须 0 差异）+ 该书 `coord_dpi` 取值来源（`config/book_geometry.json`） | 复算不等；或直接用像素原值量化；或未使用该书 `coord_dpi` |
| **AC-10 批量事务（无每页一次 connect/commit/close）** | 静态：解析链路内**不再存在**「每页一次 `connect` + `commit` + `close`」的形态（现状证据＝`processor.py` 行 432/440/441）；动态：单页写库的**连接开合次数**必须为 **0**（按 chunk 提交） | 静态检查输出（文件 + 行号 + 片段）+ 动态计数（连接开合计数或 DB 层 hook 日志） | 每页仍开合连接；或未按 chunk 提交（逐页 commit）。**（v1.3 钉定适用面｜1b-i **G-1** 收口）**：本条的**静态判据面 ＝「新增解析链路」（池 `app/pool.py` + `worker/feicui_worker.py`）**——该链路必须**按 chunk 一事务提交**且 **worker 进程 0 次 DB 连接**；**`processor.py` 行 432/440/441 的「每页一次 connect/commit/close」属 §1.4 的 Streamlit 退役边界内遗留形态**（1b-i 依派单硬约束「只许加法、默认行为不变」**未改其一个字节**）⇒ **legacy 形态不单独判负**，但**退役完成时须一并消除**（§1.4 退役判据）；**判负只针对新链路**。**留痕**：原判据的适用面**未被写明**（1b-i 自认会「仍会命中 `processor.py`」），**该歧义由 v1.3 消解**；如 Zang 另有裁定，**一句话可改**（把 `processor.py` 一并纳入判据面或维持本条） |
| **AC-11 进程分离（计算 / UI 各自生死）** | **SIGKILL 接口层进程**后：① **二值判定**——**worker 进程仍存活**（`kill -0 <worker_pid>` 退出码 **0**、被 kill 后首次采样即在进程表中）**且 cursor 单调推进**（相邻两次采样间隔 **≥ 5 s**，`chunk_hi` 或「已完成 chunk 数」**严格不减 / 增长**）——**两项同时成立＝通过，任一不成立＝FAIL**；② 重启接口层后 E2 能报出**与库内复算一致**的进度。**备注（v1.1）**：原 v1.0 的「**或按策略落为可续跑状态**」**已删除**（「按策略」未界定、复检者无法定判，属 D-4）；**「可续跑」能力不改由本条判定，由 AC-03 判定** | kill 前后的进程表（`ps`） + **可复算命令**：`kill -0 <worker_pid>; echo $?`（须为 `0`）、`ps -o pid,lstart,command -p <worker_pid>`、两次采样 `sqlite3 yinpu.db "select count(*) from <chunk 日志表>"`（或 E2 的 `cursor.chunk_hi`）× 间隔 ≥ 5 s 的取值 | **取反式（v1.2 原位等义替换｜Neng 复核 OBS-1）**：接口层 SIGKILL 后——① worker 进程**未存活**（`kill -0 <worker_pid>` 退出码 **≠ 0**，或被 kill 后**首次采样即不在进程表**）**或** ② cursor **未单调推进**（相邻两次采样间隔 **≥ 5 s**，`chunk_hi` 或「已完成 chunk 数」**减少或不变**）⇒ **任一成立即 FAIL**；**或**重启接口层后 E2 报出的进度与库内复算**不一致**；（可选，非判负项）库内出现半页记录。**留痕**：本列原 v1.1 叙述「接口层死 ⇒ 丢 job / 丢进度 / 库内出现半页记录」为**旧叙述**（与「判据」列已钉的**二值判定**不同构，故复检者无法据此定判），**已被 v1.2 取代**——**判据实质一字未改**，仅**判负形态改为该二值判据的取反式** |
| **AC-12 影像外置与库不膨胀** | **（v1.1 改为可复算式；原 v1.0「库体积**不随影像线性增长**」未给测量点 / 样本量 / 阈值 / 判定式，**已被 v1.1 取代**）**分三个**独立子项**，逐项二值判定：**① 无影像 BLOB 列**——`PRAGMA table_info(stamps)`（并查 `seals` / `images`）的 `type` 值**均不含 `BLOB`**；**② 库体积增量与影像字节不相关（斜率阈值）**——影像数 **N ∈ {0, 100, 1000}** 三档，各档导入后测 **`du -k feicui/yinpu.db`**（KB），**判定式＝斜率 `k = ΔKB / ΔN < 1 KB/影像` 判通过**（即 1000 个影像带来的库增长 **< 1 MB**）；**等价复算式（二选一，须在证据中写明选了哪个）**：**`PRAGMA page_count × PRAGMA page_size` 的增量 < 该批影像总字节 × 1%**；**③ `img_path` 为相对路径**——抽样 **≥ 10** 条记录，`img_path` **不以 `/` 开头**、**不含用户目录前缀**（须匹配 `^[^/]` 且不含 `/Users/`） | **①** `PRAGMA table_info` 原始输出（全文搜索 `BLOB`，**计数须为 0**）；**②** 三档 N 的 `du -k`（或 `page_count × page_size`）**原始读数 + 斜率复算过程**（须给出两次 N 与两次测值）；**③** `img_path` **抽样清单（≥10 条）+ 相对性校验输出** | **任一子项命中即 FAIL**：**①** 出现 `BLOB` 列；**②** 斜率 **≥ 1 KB/影像**（或 `page_count × page_size` 增量 **≥ 影像总字节 × 1%**）；**③** 入库绝对路径（`/` 开头或含 `/Users/`） |
| **AC-13 端口纪律** | 前端 **5195** / API **5196** 启动后 `lsof` 确认为**新起进程**占用；**未回退** 5173/5174；**未占用** PORTS.md 既有端口 | `lsof -nP -iTCP:<port> -sTCP:LISTEN` + `ps -o pid,lstart,command -p <pid>` | 回退 5173/5174；或占用既有端口；或静默换端口（`strictPort` 失效） |
| **AC-14 页签与路由 `/persons` 可达** | 首页导航出现【印人采集】页签；`/persons` 经 **5195** 直连与经 **5164** 的 `/feicui/persons` **均可达**且 `location.href` 不回落（**base 仍须取 `import.meta.env.BASE_URL`**）。**（v1.9 注）**：**本行行内文字一字未改**；**页签改名（【任务页】→【印谱解析】）与 tabbar 下移 / 顶部固定页眉属 v1.9 新口径**（见 §3.15.2 v1.9 注）——故本行的「首页导航」**按 v1.9 后布局读作「核心内容区顶部 tabbar」**；**改名与布局的机械判据见 §7 AC-23**（**本条判据实质不受影响**） | 两处 URL 的 HTTP 200 响应 + `location.href` 快照 + 导航栏 DOM 逐字（页签名【印人采集】） | 任一路径 404 / 回落首页；或页签缺失；或 base 写死为 `/`（非 `import.meta.env.BASE_URL`） |
| **AC-15 全量采集落库 570 / 570** | 全量拉取（`pageRows=1000` 一次返回 `total=570`）⇒ `persons` 行数 **570 / 570**（与源 `total` 相符）；**失败条目数写入 `report.json` 且可复算** | 库内 `select count(*) from persons` + 源 `/person/list` 的 `total` 读数 + `report.json` 失败清单逐条 | 行数 ≠ 570；或失败条目静默跳过（`report.json` 无失败清单）；或与源 `total` 不符 |
| **AC-16 关联面非空（证明「读了详情页」）** | `graph/person/<id>` 关联面落库：**抽样 趙之謙（`907404573`）⇒ 印谱 23 / 印章 65；吳昌碩（`907271790`）⇒ 印章 10**（**列表页没有该数据 ⇒ 非空即证明走了详情页**） | `person_relations` 按 `source_person_id` 分组的 `kind` 计数（逐条与锚点比对）+ 关联覆盖率 | 关联面为空；或锚点计数不符；或仅凭列表页字段即声称关联已落（无 `graph/person` 证据） |
| **AC-17 幂等（同批次重跑）** | 同一批次重跑 ⇒ `persons` **行数与内容指纹不变** | 两轮跑后的**内容指纹**（**列数 + 行数 + 有序全字段导出 sha256**；**禁用库文件 md5**，§8 第 6 条） | 行数增加；或任一旧行字段被改写；或用了库文件 md5 作判据 |
| **AC-18 只加法（`yinpu.db` 与既有导出未动）** | `yinpu.db` 的 `stamps` / `jobs` 行数与内容指纹**逐字节未变**；既有 `exports/fb_*` 未动 | 跑前 / 跑后 `yinpu.db` 内容指纹 + `stamps` / `jobs` 行数 + `exports/fb_*` 目录清单与 mtime | `yinpu.db` 任一表内容变化；或 `exports/fb_*` 被改写 / 删除 |
| **AC-19 归一化负向（生卒 `?` / 空 ⇒ `null`）** | `birth_year` / `death_year` 遇 `?` / 空 ⇒ **`null`**；**不得出现 `0` / `'?'` 等特值** | 对含 `?` / 空的源行取落库值（应 `null`）+ 全表 `birth_year` / `death_year` 去重取值清单（**不得含 `0` / `'?'`**） | 出现 `0` / `'?'` / 空串等特值；或把 `?` 当整数值落库 |
| **AC-20 抽取标注（无「权威分类」表述）** | `courtesy_names` / `art_names` / `alias_names` **全部带规则来源标注（`extraction='rule-based'`）**、**无「权威分类」表述**；**抽不准的一律落 `alias_names[]`** | 落库行的抽取标注逐条 + 全表检索「权威 / 权威分类」类表述（**应为 0**） | 抽取项无规则来源标注；或出现「权威分类」类表述；或把抽取结果写成权威分类 |
| **AC-21 交付缝 manifest 必含字段与 `schema_version`** | 批次包 `manifest.json` **必含**：`schema_version`（**值 `1`**）＋ 生成时点 ＋ 源端点（**含 `pageRows=1000` 全量口径**）＋ 源侧 `total` ＋ **各文件行数** ＋ **字段名清单（数组）**；且**字段名清单与 `persons.jsonl` / `relations.jsonl` 实际键面逐字一致**（**可脚本校**，§3.15.10） | `manifest.json` 原文 + 脚本逐项校验输出（`schema_version == 1` 断言 + `persons.jsonl` / `relations.jsonl` 首行 `keys()` 与 manifest 字段名清单的 **diff（须 0 差异）**） | 缺任一必含字段；或 `schema_version != 1`；或字段名清单与实际 JSONL 键面不一致（多 / 少 / 改名） |
| **AC-22 交付缝硬口径逐行可校** | 逐行校 §3.15.10 的四条硬口径：**① 幂等键** `source_person_id` **非空且批内唯一**；**② 繁简** 相应正字段的 **`*_chs` 副字段存在**；**③ 生卒** `birth_year` / `death_year` 为**整数或 `null`**，**全表无 `0` / `'?'` 特值**；**④ 抽取项带 `extraction` 标注**（＝`'rule-based'`）；**并含 JSONL 形态**（**一行一对象 / 无 BOM**） | 逐行扫描脚本输出（`source_person_id` 去重计数 **＝ 行数**、`*_chs` 字段存在清单、`birth_year` / `death_year` 去重取值清单、`extraction='rule-based'` 计数、**BOM 检测 ＝ 否**） | 幂等键空值或批内重复；或 `*_chs` 副字段缺失；或生卒出现 `0` / `'?'` / 空串特值；或抽取项无 `extraction='rule-based'`；或文件带 BOM / 一行多对象 |
| **AC-23 页签文案与 tabbar / 固定页眉布局（v1.9；**v1.12 原位改写：页签集合 2 → 3**；**v1.15 原位改写：页签集合 3 → 4**）** | **三条可机械判负子项**：**① 页签文案**——以 `App.vue` 渲染的 tabbar 为准，**页签文案恰为【印谱解析】、【印人采集】、【印谱采集】、【印章采集】四项**（**不得残留【任务页】**）；**（v1.12 原位改写｜页签集合 2 → 3**——新增第三页签【印谱采集】（§3.16.2）；**原「恰为【印谱解析】与【印人采集】两项」逐字留存于快照 `docs/versions/feicui.spec.v1.11.md` §7**；**系原位改写，不是「既有条款自动失效」**）**；**（v1.15 原位改写｜页签集合 3 → 4**——新增第四页签【印章采集】（§3.17.2）；**原「恰为【印谱解析】、【印人采集】、【印谱采集】三项」逐字留存于快照 `docs/versions/feicui.spec.v1.14.md` §7**；**系原位改写，不是「既有条款自动失效」**）**；**② tabbar 位置**——**tabbar 位于核心内容区 `main` 内、且在 `RouterView` 之前**（**不在顶部页眉 `header` 内**）；**③ 固定页眉**——**滚动后页眉仍贴顶（吸顶 / 固定 `sticky`｜`fixed`）且不遮挡内容**（内容首屏可见、未被页眉覆盖） | **①** tabbar 渲染的 DOM 逐字（**四项**页签文案，须与【印谱解析】/【印人采集】/【印谱采集】/【印章采集】逐字一致）；**②** DOM 结构证据（`App.vue` 模板或渲染树：tabbar 节点路径**在 `main` 内且在 `RouterView` 之前**）；**③** 滚动前 / 滚动后两次证据（`getBoundingClientRect()` / `position: sticky｜fixed` 计算值 + 页眉贴顶快照）+ 「内容首屏未被页眉覆盖」的可见性证据 | **①** 页签文案非【印谱解析】/【印人采集】/【印谱采集】/【印章采集】（**含残留【任务页】**），或页签数量 ≠ **4**（**v1.12 原位改写**：原「≠ 2」随页签集合 2 → 3 随动；**原文留存于快照 `docs/versions/feicui.spec.v1.11.md` §7**；**v1.15 原位改写**：随页签集合 3 → 4 随动，原「≠ 3」**原文留存于快照 `docs/versions/feicui.spec.v1.14.md` §7**）；**②** tabbar 不在 `main` 内，或位于 `RouterView` 之后 / 与内容区并列而非其顶部，或落在顶部页眉内；**③** 滚动后页眉不贴顶（非吸顶 / 固定），或页眉遮挡内容（内容首屏被覆盖） |
| **AC-24 xiai 就绪导入包键面与形态（v1.11 三态判据）** | **三态判据**（对象 ＝ `feicui/exports/person_import_<batch_id>/` 的**主交付 / sidecar / manifest**）——**判据二值：命中 (a) 或 (b) ⇒ PASS；命中 (c) ⇒ FAIL**：**(a) 21 键形态 ⇒ PASS**——`person_imports.jsonl` **每一行**的键集 **⊆ §3.15.11 v1.11 注第 ① 条的 xiai 21 键**、**无一多余键**（`set(row.keys()) - ALLOWED21 == ∅`），且 `courtesy_names` / `art_names` / `alias_names` **为 `string[]`**、行内若带 3 个 extraction 键则**各为 `string[]`（与对应值数组等长、元素非空）**；**(b) 18 键形态（缺 3 键）⇒ 亦 PASS（兼容）**——每行键集 **⊆ 旧 18 键**、**不得因缺这 3 键判负**（缺键不拒收）；**(c) 旧 feicui 形态 ⇒ FAIL**——出现 **32 键**（feicui `persons.jsonl` 原形态），**或** 三桶为**对象数组**（`[{value,kind,extraction,from}]` / 落成 `"[object Object]"`）。**共同硬口径（三态均适用）**：`source_person_id` **唯一计数 ＝ 行数**（满量批次 **＝ 570**）；`manifest.json` 的**键面 diff 与该行所落形态一致且 ＝ `0`**（**21 键形态 ⇒ vs 21；18 键形态 ⇒ vs 18**）。**`'rule-based'` 只作本批数据断言、不得写成对外契约判据**（**值域不封闭** ⇒ **不得把 extraction 值 ≠ `'rule-based'` 判负，亦不得据本批恒 `rule-based` 外推为键的值域约束**） | `person_imports.jsonl` / `person_imports_extraction.jsonl` / `manifest.json` 三文件原文 ＋ **逐行扫描脚本输出**（**态别判定**：`row_keys ⊆ ALLOWED21` ⇒ (a)；`row_keys ⊆ ALLOWED18` ⇒ (b)；**命中 32 键 / 对象数组 ⇒ (c) FAIL**；`type` 断言三桶为 `list` 且元素 `isinstance(str)`；3 个 extraction 键**若在行内**：`len()` 与对应值数组相等、元素 `isinstance(str)` 且非空；`len(set(source_person_id)) == 行数`；manifest 键面 diff **`== 0`**（按所落形态的键面）） | **命中 (c) 即 FAIL**：**①** 主交付任一行含 **21 键（或 18 键）之外的键**（多 / 改）；**②** 三桶非 `string[]`（含对象元素 / 落成 `"[object Object]"` / 非数组）；**③** 提供了 extraction 键但**与对应值数组不等长**或**含空元素**；**④** `source_person_id` 有重复 / 空值；**⑤** manifest 键面 diff ≠ 0（**含多余键**）。**封堵（不得判负）**：**缺 3 键 ⇒ 命中 (b)、PASS（不得因缺键拒收 / 判负）**；**extraction 值 ≠ `'rule-based'` ⇒ 不判负**（**值域不封闭**）。**（留痕｜v1.11 原位改写）**：原 v1.10 的「**五条可机械判负子项**」（① 键面 ⊆ 18 键 / ② 三桶为 `string[]` / ③ sidecar 三数组等长且元素恒 `rule-based` 且无 `from` / ④ 行数＝570 且幂等键唯一 / ⑤ manifest 键面 diff＝0）**已被 v1.11 取代为上述三态判据**（由 D-1 键面 18 → 21 与「缺键不拒收」驱动）；**原五子项逐字文本保留于 `docs/versions/feicui.spec.v1.10.md` §7**（**历史行逐字保留、只增不改**）。 |
| **AC-25 页签【印谱采集】与路由 `/items` 可达（v1.12）** | 首页导航出现【印谱采集】页签（**第三页签**，与【印谱解析】【印人采集】并列）；`/items` 经 **5195** 直连与经 **5164** 的 `/feicui/items` **均可达**且 `location.href` 不回落（**base 仍须取 `import.meta.env.BASE_URL`**） | 两处 URL 的 HTTP 200 响应 + `location.href` 快照 + 导航栏 DOM 逐字（页签名【印谱采集】，且页签集合 ＝【印谱解析】/【印人采集】/【印谱采集】） | 任一路径 404 / 回落首页；或页签缺失；或 base 写死为 `/`（非 `import.meta.env.BASE_URL`）；或页签集合非三项 |
| **AC-26 全量采集落库 1742 / 1742 与失败清单可复算（v1.12）** | 全量拉取（`book/list` **`pageRows=3000` 一次返回 `total=1742`**）⇒ `items` 行数 **1742 / 1742**（与源 `total` 相符）；**失败条目数写入失败清单且可复算**；**限流回包（HTTP 200 ＋ `code:"429"`）不得计作成功** | 库内 `select count(*) from items` + 源 `/book/list` 的 `total` 读数（1742）+ 失败清单逐条（可复算命令输出） | 行数 ≠ 1742；或失败条目静默跳过（无失败清单）；或与源 `total` 不符；或把 `code:"429"` 的 200 回包计作成功 |
| **AC-27 幂等键非空且唯一＝行数 / `as_book_id` 唯一（v1.12）** | `source_item_id`（＝`seqid`）**非空且批内唯一 ＝ 行数**；`as_book_id`（＝`asBookId`）**唯一 ＝ 1742**；**两者不得混用**（`seqid` 是详情路径参数与幂等键；`asBookId` 只是桥接键） | 逐行扫描脚本输出（`len(set(source_item_id)) == 行数`、空值计数 ＝ 0；`len(set(as_book_id)) == 1742`） | 幂等键有重复 / 空值；或 `as_book_id` 不唯一；或把 `asBookId` 当详情路径参数 / 幂等键使用 |
| **AC-28 抽样锚点（卷册 / 纪年 / 藏家）（v1.12；**v1.13 原位改写：`donor` 降 best-effort**）** | **锚点分两档**：**（硬档 · 列表可取，仍判负）** **`seqid=2214` / `asBookId=0307`「龍泓山人印譜」⇒ 卷册 `8`（`volume_count`）、纪年「清宣統二年」（`date_text`）、公元 `1910`（`date_year`）、`hasImage=1`**；**（best-effort 档 · detail 独有，不判负）** **`seqid=3547` / `1817`「楊仲子印存」⇒ `bookDonor=林章松`（`donor`）** —— **`donor`（`bookDonor`）属 `book/detail` 独有字段，而 v1.13 已把 `book/detail` 降为 best-effort（默认关）⇒ `donor` 缺失不判负**（**存在时须逐字等于 `林章松`**；**detail 未开 ⇒ 本条不适用**） | 库内（或 `items.jsonl`）这两条记录的对应字段值逐字 ＋ **（硬档）源 `book/list` 行片段** / **（best-effort 档）源 `book/detail` 回包片段** | **硬档（卷册 / 纪年 / 公元 / `hasImage`）任一锚点字段值不符 / 缺失 ⇒ FAIL**；**（v1.13）`donor` 未落（detail best-effort 未开）⇒ 不判负**；**但若 `donor` 已落而值 ≠ `林章松` ⇒ FAIL**。**留痕**：原 v1.12 判负形态「或 `donor` 未落（详情独有字段未采）」**随 detail 降 best-effort 已被 v1.13 原位改写**（**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.12.md` §7**；**系原位改写、非「既有条款自动失效」**） |
| **AC-29 数值字段负向（`volume_count` / `date_year` 整数或 `null`，无特值）（v1.12）** | `volume_count` / `date_year` **为整数或 `null`**；源空 / 非数字 ⇒ **`null`**；**全表不得出现 `0` / 空串等特值** | 全表 `volume_count` / `date_year` 去重取值清单（**不得含 `0` / `''`**）+ 对源空行取落库值（应 `null`） | 出现 `0` / 空串等特值；或把源空 / 非数字落成 `0` / 字符串 |
| **AC-30 独立库隔离（`yinpu.db` 与 `var/person_ingest.db` 内容指纹未变）（v1.12）** | 采集全程**只写 `var/item_ingest.db`**；`yinpu.db` 的 `stamps` / `jobs` 行数与内容指纹**逐字节未变**；`var/person_ingest.db` 的 `persons` / `person_relations` 行数与内容指纹**逐字节未变**；既有 `exports/fb_*` / `exports/person_*` 未动 | 跑前 / 跑后 `yinpu.db` 与 `var/person_ingest.db` 的**内容指纹**（列数 + 行数 + 有序全字段导出 sha256；**禁用库文件 md5**，§8 第 6 条）+ `exports/fb_*` / `exports/person_*` 目录清单与 mtime | `yinpu.db` 或 `var/person_ingest.db` 任一表内容变化；或既有 `exports/**` 被改写 / 删除；或用库文件 md5 作判据 |
| **AC-31 就绪包 manifest 必含项与 `key_face_status: pending_xiai`（v1.12；**v1.13 增补 `detail_policy` / 缺失三字段 / `detail_unconfirmed`**）** | 就绪包 `feicui/exports/item_import_<batch_id>/` **三文件齐备**（`items.jsonl` / `item_creators.jsonl` / `manifest.json`）；`manifest.json` **必含**：`schema_version`（**值 `1`**）＋ 生成时点（带时区）＋ 源端点（**含 `pageRows=3000` 全量口径 ＋ `graph/book/<seqid>` 关联面**）＋ 源侧 `total`（**＝1742**）＋ **各文件行数** ＋ **字段字典** ＋ 幂等键唯一计数 ＋ 覆盖统计 ＋ **`key_face_status: "pending_xiai"`** ＋ **（v1.13 增补）`detail_policy`**（本批 `book/detail` 开关态：`off`（默认）｜`best_effort`）＋ **（v1.13 增补）因 detail 降级而缺失的三字段清单**（`creatorRole` / `creatorRelator` / `bookDonor`）＋ **（v1.13 增补）`detail_unconfirmed` 计数**；**JSONL 一行一对象 / UTF-8 / 无 BOM**；**`item_creators.jsonl` 每行 `source_item_id` 可回指 `items.jsonl`**。**候选键面未裁 ⇒ 不判「键面 diff＝0」** | `manifest.json` 原文 + 逐项校验脚本输出（`schema_version == 1` 断言、必含键齐备、`key_face_status == 'pending_xiai'`、**`detail_policy ∈ {off, best_effort}`**、**缺失三字段清单 / `detail_unconfirmed` 存在**、行数一致；`items.jsonl` / `item_creators.jsonl` 首行 `keys()`、BOM 检测 ＝ 否；`item_creators` 的 `source_item_id` ⊆ `items` 的 `source_item_id`） | 缺任一必含字段（**含 v1.13 增补的 `detail_policy` / 缺失三字段清单 / `detail_unconfirmed`**）；或 `schema_version != 1`；或**未明示 `key_face_status: pending_xiai`**；或文件带 BOM / 一行多对象；或 `item_creators` 存在无法回指 `items.jsonl` 的 `source_item_id`；或**对本包误判「键面 diff＝0」**（键面未裁） |
| **AC-32 幂等（同批次重跑，行数与内容指纹不变）（v1.12）** | 同一批次重跑 ⇒ `items`（及 `item_creators`）**行数与内容指纹不变**（已完成条目不得重算重写） | 两轮跑后的**内容指纹**（**列数 + 行数 + 有序全字段导出 sha256**；**禁用库文件 md5**，§8 第 6 条） | 行数增加；或任一旧行字段被改写；或用了库文件 md5 作判据 |
| **AC-33 `/api/items/package` 可达且重建幂等（仅时间戳变 / JSONL 字节不变）（v1.14）** | **三条可机械判负子项 ＋ 两条负向**：**① 可达**——`POST /api/items/package`（无参数）返 **200**，响应为就绪包摘要且 **`key_face_status == "pending_xiai"`**、`rows` 为整数；**② 重建幂等**——**同批次连续两次 `POST /api/items/package?batch_id=<id>`**（或 UI 连点两次「生成就绪包」）后：**`items.jsonl` 与 `item_creators.jsonl` 的内容逐字节一致**（**md5 两次相等 / 内容指纹不变**），**而 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 随重建时点变化**（**即「仅时间戳变、内容不变」**）；**③ 零联网与不写 xiai**——**重建期间不产生任何对源站（`yin.fudan.edu.cn`）的请求**、**`xiai/**` 任一文件未新增 / 未改写** | 两次 `POST` 的 HTTP 200 响应体（`generated_at` / `content_fingerprint`）＋ **两次 `items.jsonl` / `item_creators.jsonl` 的 `md5` 逐字节比对输出**（须相等）＋ **两次 `manifest.json` 的 `created_at` 读数**（须不等 / 随重建时点变化）＋ **源站请求计数（＝0）** ＋ **`xiai/**` 目录清单与 mtime（未变）** | **①** `/api/items/package` 不可达 / 非 200；**或** **②** 重建后 `items.jsonl` / `item_creators.jsonl` 内容发生变化（**重建非幂等**）；**或** **③** 重建期间产生源站请求 / 写了 `xiai/**` 任一文件。**（负向）**：**未白名单查询参数（如 `?foo=1`）⇒ 须 400（`UNSUPPORTED_PARAM`）**；**指定不存在的 `batch_id` ⇒ 须 404（`BATCH_NOT_FOUND`）**；**回包非结构化 JSON（HTML 错误页 / 200＋空 `data` 冒充）⇒ FAIL** |
| **AC-34 页签【印章采集】与路由 `/seals` 可达（v1.15）** | 首页导航出现【印章采集】页签（**第四页签**，与【印谱解析】【印人采集】【印谱采集】并列）；`/seals` 经 **5195** 直连与经 **5164** 的 `/feicui/seals` **均可达**且 `location.href` 不回落（**base 仍须取 `import.meta.env.BASE_URL`**） | 两处 URL 的 HTTP 200 响应 + `location.href` 快照 + 导航栏 DOM 逐字（页签名【印章采集】，且页签集合 ＝【印谱解析】/【印人采集】/【印谱采集】/【印章采集】） | 任一路径 404 / 回落首页；或页签缺失；或 base 写死为 `/`（非 `import.meta.env.BASE_URL`）；或页签集合非四项 |
| **AC-35 全量采集落库 3679 / 3679 与失败清单可复算（v1.15）** | 全量拉取（`seal/list` **`pageRows=5000` 一次返回 `total=3679`**）⇒ `seals` 行数 **3679 / 3679**（与源 `total` 相符）；**失败条目数写入 `report.json` 失败清单且可复算**；**限流回包（HTTP 200 ＋ `code:"429"`）不得计作成功** | 库内 `select count(*) from seals` + 源 `/seal/list` 的 `total` 读数（3679）+ 失败清单逐条（可复算命令输出） | 行数 ≠ 3679；或失败条目静默跳过（无失败清单）；或与源 `total` 不符；或把 `code:"429"` 的 200 回包计作成功 |
| **AC-36 幂等键 `source_seal_id` 非空且唯一＝行数（v1.15）** | `source_seal_id`（＝`seqid`）**非空且批内唯一 ＝ 行数（3679）**；**同批次重跑 ⇒ 行数与内容指纹不变**（已完成条目不得重算重写） | 逐行扫描脚本输出（`len(set(source_seal_id)) == 行数`、空值计数 ＝ 0）；两轮跑后的**内容指纹**（**列数 + 行数 + 有序全字段导出 sha256**；**禁用库文件 md5**，§8 第 6 条） | 幂等键有重复 / 空值；或行数增加；或任一旧行字段被改写；或用了库文件 md5 作判据 |
| **AC-37 `audit_status` 字段保留与分布统计（v1.15）** | `seals` 每行**保留 `audit_status`**（＝源 `auditStatus` 原值整数）；**分布统计与实测一致**：`1=2929` / `2=716` / `9=31` / `0=3`（**合计 3679**；**`716` ＝ 站点 `statistic.sealCount` 已发布子集**）；`manifest.json` **含该分布统计** | 库内 `select audit_status, count(*) from seals group by audit_status` + 源分布锚点（`1=2929` / `2=716` / `9=31` / `0=3`）+ `manifest.json` 分布字段 | 分布计数与实测不符；或 `audit_status` 字段丢失 / 被裁剪；或 `manifest.json` 无分布统计 |
| **AC-38 形製码表纯函数无冲突且源文「异性」逐字（v1.15）** | **形製码表为纯函数（每码 2 枚 × 0 冲突）**：`1=白文方印` … `10=白文异性印`（§3.17.1）；**源侧原文「异性」逐字照登**（**不得改写成「异形」**）；`form_label` 与 `form_code` 一一对应 | 码表逐码抽样（**每码 2 枚**、逐码 0 冲突）＋ **全表检索「异形」应为 0 / 「异性」应命中** ＋ 落库 `form_label` 与 `form_code` 映射表 | 码表冲突；或出现「异形」（源文被改写）；或 `form_label` 与码表不符 |
| **AC-39 桥接（印章涉 19 种印谱 ⊆ item 库）（v1.15）** | `graph/seal/<seqid>` 给出的**印谱节点 id ↔ `var/item_ingest.db` 的 `source_item_id`**（如 `1967` ↔ `as_book_id=0113`）；**印章涉 19 种印谱全部命中 item 库**（**无悬空印谱 id**） | `seal_links.jsonl`（或库内 `seal_links`）按 `link_kind=印谱` 分组的 id 集合 ∩ `var/item_ingest.db.items.source_item_id` ⇒ **差集 ＝ 0（19 种全部命中）** + `1967` ↔ `0113` 锚点 | 出现无法命中 item 库的印谱 id；或锚点映射不符；或 sidecar 缺 `印谱` 节点 |
| **AC-40 影像取数 / 张数上限 / 实际计数 / 放大尺寸判负 / `NaN_` 源侧无图（v1.15）** | **取图只用原生裁切**（`iiif_proxy/api/char_proxy/<ref>` ⇒ 302 ⇒ JPEG；**只用 `/full/0/default.jpg`**）——**任何放大 / 非原生尺寸请求 ⇒ 判负**（**`!400,400` 实测回 200 但为 IIPImage 上采样插值 ⇒ 失真**）；**张数上限** ≈ **6765**（印面 3679 ＋ 印体释文 2627 ＋ 边款 459，**不得超上限**）；**实际计数**写入 `report.json` / `manifest.json` 且与 `images_manifest.jsonl` 行数**一致**；**`NaN_` 开头 ref 记「源侧无图」**（`status=source_no_image`、**不计失败**；**v1.16 原位改写：原写 `source_missing`，已由 v1.16 取代、统一为 `source_no_image`，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.15.md`**） | `images_manifest.jsonl` 行数 + `find images/ -type f \| wc -l` + **请求 URL 清单（须全部为 `/full/0/default.jpg`，放大请求计数 ＝ 0）** + `NaN_` ref 清单与 `status` | 出现放大 / 非原生尺寸请求（如 `!400,400`）；或张数超上限；或实际计数与 manifest 不符；或 `NaN_` ref 被计作失败 / 未登记 |
| **AC-41 影像为 TIFF 容器（魔数判负）＋ 尺寸上限可判定口径（超档须已逐行标记）（v1.15；**v1.18 原位改写：删去恒假的「输入档 ≤ 1 MB」判据**；**v1.19 原位收窄：字面判负由「单张 > 4 MiB」收窄为「未被标记的超档行」**）** | **`images/` 内全部为 TIFF 容器**（**魔数 `II*\0` / `MM\0*`**；**不得回落 JPEG、不得冒充**）；**尺寸上限的可判定口径 ＝ `bytes`（＝ TIFF 字节数）> 4 MiB（`STORED_MAX_BYTES`）的行必须已逐行标记 `oversize_for_xiai_store`（boolean）**——**超档本身不判负；已标记的超档行豁免本 AC；仅未被标记的超档行 ⇒ FAIL**（**v1.18 删去「输入档 ≤ 1 MB」——`MAX_INPUT_BYTES` ＝ 1 MB 属 xiai 编解码口输入面，不得用作本包 / 本端点判据；依据 ＝ xiai `server/app/store.py::validate_payload` 只校验「空 / 4 MiB / TIFF 魔数」三面**）。**与 AC-54 的分工**：**本 AC 管「容器与尺寸上限的可判定口径」（超档行的可判定形态）；AC-54 管「超档行的标记 / 顶层计数 / 清单 / 不得自行降采样或转码」（记账与红线）**——**两者对同一事实（超档行）口径一致、不互相判负** | 逐文件魔数检测（`xxd` / `file` 命中 `TIFF`，**JPEG 魔数 `FFD8` 计数 ＝ 0**）+ 全表 `bytes`（＝ TIFF 字节数）与 `oversize_for_xiai_store` 标记列的**交叉核对**（**`bytes > 4 MiB` 且未标记的行计数 ＝ 0**） | 任一文件非 TIFF（含 JPEG / 无魔数 / 冒充）；**或存在 `bytes > 4 MiB` 且未逐行标记 `oversize_for_xiai_store` 的行**（`bytes > 4 MiB` 但**已标记**的行**不判负**）。**（v1.19 原位收窄）**：原 v1.18 版「**或单张 > 4 MiB**」字面判负与原「全表 `bytes` 去重清单（max ≤ 4 MiB）」证据，**已随收窄改为「未被标记的超档行」口径**（**超档允许、但必须逐行标记；未标记的超档行才是 FAIL**），**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md` §7；系原位收窄，不是「既有条款自动失效」**。**（v1.18 原位改写｜恒假判据删除）**：原「或源输入 > 1 MB」判负与「源 JPEG `bytes` ≤ 1 MB 清单」证据随「输入档」删除，**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §7；系原位改写，不是「既有条款自动失效」**。 |
| **AC-42 `images/` 路径形状为 `<sha256[:2]>/<sha256>.tiff` 且 sha256 与字节自洽（v1.15）** | **`images/` 下每个文件路径 ＝ `<sha256[:2]>/<sha256>.tiff`**（**内容寻址**）；**文件名 sha256 与文件字节的 sha256 自洽**（**重算 ＝ 文件名**）；**`images_manifest.jsonl` 的 `sha256` 与之逐行一致** | `find images/ -type f` 路径清单（**正则校验 `<hex2>/<hex64>.tiff`**）+ **逐文件 `sha256sum` 与文件名比对输出** | 路径形状不符（非 `<sha256[:2]>/<sha256>.tiff`）；或文件名 sha256 与字节不符；或含非 `.tiff` 后缀 |
| **AC-43 `images_manifest.jsonl` 与文件一一对应（无孤儿 / 无缺失）（v1.15）** | **`images_manifest.jsonl` 每一行 ↔ `images/` 一个文件**（**双射**）：**无孤儿**（manifest 行无对应文件 ＝ 0）、**无缺失**（文件无对应 manifest 行 ＝ 0）；每行**必含** `seqid` / `kind ∈ {yt, ytsw, yzbk}` / `source_ref` / `source_url` / `sha256` / `bytes` / `width` / `height` / `source_format` / `container` / `conversion` / `upscaled:false` | `images_manifest.jsonl` 行数 与 `find images/ -type f \| wc -l` **相等** + 集合差（manifest `sha256` 集 △ 文件 `sha256` 集 ＝ ∅）+ 逐行字段齐备脚本输出 | 行数与文件数不等；或存在孤儿 / 缺失（集合差非空）；或任一必含字段缺失；或 `upscaled` 非 `false` / `conversion` 未标注 |
| **AC-44 `/api/seals` 读口分页自洽且 `cursor` ⇒ 400（v1.15）** | `GET /api/seals` 分页用 `page` / `limit` / `has_more`（**`has_more == page*limit < total`**）；**传 `cursor` ⇒ 400**（**不得静默忽略**）；**非白名单参数一律 400 结构化 JSON**；`total` ＝该范围全量（**3679**） | 分页响应样本（逐页 `has_more` 与复算一致）+ `?cursor=…` 的 **400** 响应体 + 非白名单参数的 **400** 响应体 | 分页 `has_more` 与复算不符；或 `cursor` 被静默忽略（非 400）；或非白名单参数未 400；或回包非结构化 JSON |
| **AC-45 `/api/seals/package` 可达且重建幂等（`images/` 不得删或重转）（v1.15）** | **① 可达**——`POST /api/seals/package`（无参数）返 **200**，响应为就绪包摘要且 **`key_face_status == "pending_xiai"`**；**② 重建幂等**——**同批次连续两次重建**后：`seals.jsonl` 与 `seal_links.jsonl` 内容**逐字节一致**（md5 两次相等），而 `manifest.json` 的 `created_at` 与 `report.json` 的 `generated_at` **随重建时点变化**（**仅时间戳变、内容不变**）；**③ `images/` 不得删或重转**——重建前后 `images/` 文件数与 `sha256` 清单**不变**；**④ 零联网且不写 xiai**——重建期**无源站请求**、**`xiai/**` 未变**；**（负向）** 未白名单参数 ⇒ **400**（`UNSUPPORTED_PARAM`）、批次不存在 ⇒ **404**（`BATCH_NOT_FOUND`） | 两次 `POST` 的 200 响应体（`generated_at` / `content_fingerprint`）+ 两次 `seals.jsonl` / `seal_links.jsonl` 的 `md5` 比对输出 + 两次 `manifest.json` 的 `created_at` 读数 + 重建前后 `images/` 清单（文件数与 `sha256`）+ 源站请求计数（＝0）+ `xiai/**` 目录清单 | `/api/seals/package` 不可达 / 非 200；或重建后 `seals.jsonl` / `seal_links.jsonl` 变化（非幂等）；或**重建删除了 `images/` 任一文件 / 重转了既有影像（`sha256` 变）**；或重建期产生源站请求 / 写了 `xiai/**`；**或**（负向）未白名单参数未 400 / 批次不存在未 404 / 回包非结构化 JSON |
| **AC-46 独立库隔离（`yinpu.db` / `var/person_ingest.db` / `var/item_ingest.db` 内容指纹未变）（v1.15）** | 采集全程**只写 `var/seal_ingest.db`**；`yinpu.db` 的 `stamps` / `jobs` 行数与内容指纹**逐字节未变**；`var/person_ingest.db` 的 `persons` / `person_relations` **逐字节未变**；`var/item_ingest.db` 的 `items` / `item_creators` **逐字节未变**；既有 `exports/fb_*` / `exports/person_*` / `exports/item_*` 未动 | 跑前 / 跑后三库的**内容指纹**（列数 + 行数 + 有序全字段导出 sha256；**禁用库文件 md5**，§8 第 6 条）+ `exports/fb_*` / `exports/person_*` / `exports/item_*` 目录清单与 mtime | `yinpu.db` / `var/person_ingest.db` / `var/item_ingest.db` 任一表内容变化；或既有 `exports/**` 被改写 / 删除；或用库文件 md5 作判据 |
| **AC-47 影像 `failed` ＝ 0（v1.16；**v1.17 原位改写：由「空或仅瞬态且附重跑命令」改为「＝ 0」**）** | 影像台账（`seal_images`）与包内 `report.json` 的 **`failed` 桶必须为 0**（**因 `source_no_image` 三子因已穷尽枚举（`NaN_` / 持久 5xx / 坏字节 `bad_bytes`），确定性（按 ref 恒定 / 非瞬态）失败不得留在 `failed`**）；**源侧缺图（`source_no_image`，含 `bad_bytes`）不得计入 `failed`** | `seal_images` 按 `status` 分组计数（**`failed` 组计数 ＝ 0**）+ `report.json` 的 `failed` 清单（**须为空**）+ **对照 Run-1 / Run-2 失败集合**（恒定项须已归入 `source_no_image` 三子因之一） | **`failed` 桶 ≠ 0**（含残留确定性（非瞬态）失败）；或把源侧缺图（`source_no_image`，含 `bad_bytes`）计入 `failed`；或**出现新的第四类子因而未先入册即落 `failed`**。**（v1.17 原位改写；原「`failed` 桶空或仅瞬态且附重跑命令」原文逐字留存于快照 `docs/versions/feicui.spec.v1.16.md`；系原位改写，不是「既有条款自动失效」。）** |
| **AC-48 `source_no_image` 按 ref 前缀聚合清单 ＋ 计数 ＋ 样例 `seqid`（v1.16；**v1.17 随动：子因计数由「两类」扩为「三类」**）** | 包内 `report.json` 含 **`source_no_image` 分桶**——**按 ref 前缀聚合的清单**（如 `11_*` / `12_*`）＋ **每前缀计数** ＋ **样例 `seqid`**；总数与台账 `status='source_no_image'` 一致；**源侧缺图是源侧事实，不得写成 feicui 采集失败** | `report.json` 的 `source_no_image` 段（前缀 → 计数 → 样例 `seqid`）+ `seal_images` 中 `status='source_no_image'` 的行数与前缀聚合复算 + **三类子因计数（`NaN_` 开头 ref / 持久 `HTTP 500`（`error='HTTP 500'`）/ 坏字节 `bad_bytes`（v1.17 新增））** | 无 `source_no_image` 分桶；或未按 ref 前缀聚合 / 无计数 / 无样例 `seqid`；或把源侧缺图计入采集失败 / 静默丢弃；**或子因计数缺 `bad_bytes` 一类** |
| **AC-49 `images_manifest.jsonl` ↔ `images/**` 双向一一对应（v1.16；承 AC-43 加严：须给两个方向计数）** | **双射（两方向计数均为 0）**：**无孤儿**（manifest 行无对应文件 ＝ 0）、**无缺失**（文件无对应 manifest 行 ＝ 0）；**须同时给两个方向的计数** | `images_manifest.jsonl` 行数 与 `find images/ -type f \| wc -l` **相等** + **两个方向的集合差**（manifest `sha256` 集 − 文件 `sha256` 集 ＝ ∅ 且文件 → manifest ＝ ∅）；逐项计数（非仅相等） | 行数与文件数不等；或任一方向存在孤儿 / 缺失（集合差非空）；或只给一个方向计数 |
| **AC-50 每行 `sha256` 与该 TIFF 字节逐行自洽（v1.16；承 AC-42 加严：随机 20 行重算；**v1.18 原位更正：`tiff_sha256` ⇒ `sha256`**）** | **`images_manifest.jsonl` 每行的 `sha256` 与该行指向的 TIFF 文件字节重算 sha256 相等**（**随机 20 行重算、逐行自洽**；**包内实物 `sha256` 即 TIFF 字节的内容寻址键、无 `tiff_sha256` 键**） | 随机抽 **20 行**，逐行 `sha256sum images/<sha256[:2]>/<sha256>.tiff` 与行内 `sha256` 比对输出（**20/20 全等**） | 任一行 `sha256` 与文件字节不符；或抽样 < 20 行；或未逐行比对（只比总数）。**（v1.18 原位更正：原写 `tiff_sha256` 键——实物无此键，原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §7；系原位更正，不是「既有条款自动失效」。）** |
| **AC-51 TIFF 魔数逐行成立 ＋ 单张 ≤ 4 MiB（v1.16；承 AC-41 加严：逐行非抽验；**v1.18 原位改写：删去恒假的「输入档 ≤ 1 MB」判据**）** | **`images/` 内每个文件魔数成立**（**`II*\0` / `MM\0*`**；**JPEG 魔数 `FFD8` 计数 ＝ 0**）；**单张产物 ≤ 4 MiB（`STORED_MAX_BYTES`）**（**v1.18 删去「输入档 ≤ 1 MB」——同 AC-41，`MAX_INPUT_BYTES` ＝ 1 MB 属 xiai 编解码口输入面，不得用作本包 / 本端点判据**） | **逐文件（非抽验）**魔数检测输出（`file` / `xxd` 命中 `TIFF`；JPEG 计数 ＝ 0）+ `images_manifest.jsonl` 全表 `bytes`（＝ TIFF 字节数）重算的 **max ≤ 4 MiB** | 任一文件非 TIFF（含 JPEG / 无魔数 / 冒充）；或单张 > 4 MiB；或未逐行（只抽验）。**（v1.18 原位改写｜恒假判据删除）**：原「或源输入 > 1 MB」判负与「源 JPEG `bytes` ≤ 1 MB 清单」证据随「输入档」删除，**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §7；系原位改写，不是「既有条款自动失效」**。 |
| **AC-52 影像台账每行有 `width` / `height`（v1.16）** | **影像台账（`seal_images`）与 `images_manifest.jsonl` 每行必含非空 `width` / `height`**（整数，TIFF 尺寸）；`ok` 行缺失即判负 | 台账与 manifest 逐行 `width` / `height` 齐备脚本输出（**空值 / 缺键计数 ＝ 0**） | 任一行缺 `width` / `height`（或为空 / 非整数） |
| **AC-53 `bad_bytes` 实例归 `source_no_image` 面不在 `failed`（v1.17）** | **HTTP `200` ＋ `content-type: image/jpeg`，但正文非图像 / 不可解码的影像 ref**（**实例如 `2_3609_1`：正文 697 B 为 iipsrv 把自己的响应头当正文吐出、非 JPEG 魔数 `FFD8`、PIL 解码失败、持久复现**）**必须归入 `source_no_image` 面（子因 `bad_bytes`）而非 `failed`**；**`failed` 桶不得含此类项**（**与 AC-47 的 `failed` ＝ 0 自洽**）；**台账 `error` 字段记实际现象原文、不得改写为自造错误码** | 影像台账（`seal_images`）中 `source_ref='2_3609_1'`（及同类）行的 `status='source_no_image'` 且 `error` 记实际现象原文 + `failed` 桶该 ref 计数 ＝ 0 + `report.json` 的 `bad_bytes` 子因计数（≥1、含该实例） | 把 `bad_bytes` 实例（如 `2_3609_1`）落 `failed`；或 `error` 被改写为自造错误码；或 `report.json` 无 `bad_bytes` 子因一类 / 缺该实例计数 |
| **AC-54 超 xiai store 4 MiB 上限的行须逐行标记、不得自行降采样 / 转码（v1.18）** | **`images_manifest.jsonl` 中 `bytes`（＝ TIFF 字节数）> 4 MiB（`STORED_MAX_BYTES`）的行必须逐行标记**（**实物字段名 `oversize_for_xiai_store`（boolean，逐行；超档行 ＝ `true`）**）**＋ 顶层计数 ＋ 清单**（`report.json` / `manifest.json` 给出超档桶计数与逐行清单）；**且本包不得对超档影像自行降采样 / 自行转码**（**保留原生裁切与「RGB 8-bit ＋ Deflate」家法格式**；去留由 xiai 侧裁，见 §9-R34） | `images_manifest.jsonl` 超档行清单（`bytes > 4 MiB`，**实测 6 条：`seqid 3353 / 3366 / 3367 / 3464 / 3506 / 3510`，均 `kind=yt`、~1500×1500、4.37–4.96 MB**）＋ 每行标记字段 ＋ `report.json` / `manifest.json` 的超档桶计数与清单 ＋ **影像字节格式证据（RGB 8-bit ＋ Deflate、未降采样 / 未转码）** | **`bytes > 4 MiB` 的行**未逐行标记 / 无顶层计数 / 无清单；**或**对超档影像**自行降采样 / 自行转码**（`width` / `height` 或 `bytes` 与原生裁切不符、像素被缩） |
| **AC-55 各 `predicate` 计数与 `report.json` 一致（v1.20）** | `relations.jsonl` **各 `predicate` 行数**（**逐类给数**）**必须等于** `report.json` 的同名场景计数（**五类逐项**）；**且五类之和 ＝ `relations.jsonl` 行数** | `relations.jsonl` 按 `predicate` 分组计数输出（**五类逐项**）＋ `report.json` 场景计数原文 ＋ **两者逐项比对表（须 0 差异）** | 任一类计数与 `report.json` 不一致；或五类之和 ≠ `relations.jsonl` 行数；或只给合计不给逐类 |
| **AC-56 去重算术可复算（`|A∪B| = |A| + |B| − |A∩B|`）（v1.20）** | **去重算术自洽、可复算**：`item_creators(book_graph)` **1281** vs `person_relations(印谱)` **1349** ⇒ **交集 1249** ⇒ **并集 1381**（**`1349 + 1281 − 1249 = 1381`** 三元逐字可复算）；**`report.json` 须给出 `|A|` / `|B|` / `|A∩B|` / `|A∪B|` 四数**，且四数满足该等式 | `report.json` 的四数原文（`|A|=1281` / `|B|=1349` / `|A∩B|=1249` / `|A∪B|=1381`）＋ **独立复算脚本输出**（分别从两表取对集合求交 / 求并，须得同四数）＋ 等式验算 | 四数任一不符；或等式不成立（`|A|+|B|−|A∩B| ≠ |A∪B|`）；或只报并集不给交集 / 不给分项 |
| **AC-57 可连键逐条成立（除 `ghost` 行）（v1.20）** | **可连键逐条成立**：**每条 `person_to_item` 的 `object_id` ∈ `items.source_item_id`**（**除被标 `ghost:true` 的行**）；**每条 `seal_to_item` / `seal_to_person` / `person_to_seal` 的印章侧 `id` ∈ `seals.source_seal_id`**；**每条边的人侧 / 谱侧 `id` 命中对应库**（`persons.source_person_id` / `items.source_item_id` / `seals.source_seal_id`） | **`relations.jsonl` 逐条扫描脚本输出**（各 predicate 的 `object_id` / `subject_id` 与对应库主键集合求差，**未被 `ghost` 标记的差集须为 ∅**）＋ 三库主键集合读数 | 任一条可连键不成立（`id` 不在对应库内）**且未标 `ghost` / 未按 §3.18.4 R-c 标记**；或无法按 predicate 逐类复算 |
| **AC-58 未命中 / 幽灵有清单与计数（不为 0 必逐条列出）（v1.20）** | **未命中 / 幽灵行有清单与计数**：`report.json` 须给 **`as_book_id='test'` 幽灵行计数（实测 1）** ＋ **14 个未收录印人 id 清单与计数** ＋ **`ref_id` 未命中 person 库计数（按面分列 ＋ 合计）**；**计数不为 0 时必须逐条列出**（**不得只给合计**） | `report.json` 的幽灵 / 未命中段（**逐条清单 ＋ 各计数**）＋ 三库对账复算（`person_relations.as_book_id` 与 `items.as_book_id` 差集 ＝ `{test}`；`seal_links(person_*).ref_id` 与 `persons.source_person_id` 差集 ＝ 14 个 id） | 计数不为 0 却**只给合计不给逐条清单**；或把源侧幽灵 / 未收录**计入采集失败**或**静默剔除**；或漏计任一类 |
| **AC-59 四库指纹 ＋ 三包未变（只读三库、不改三线包）（v1.20）** | 联立 / 出包全程**只读**三库：`yinpu.db` 的 `stamps` / `jobs` 行数与内容指纹**逐字节未变**；`var/person_ingest.db` 的 `persons` / `person_relations` **逐字节未变**；`var/item_ingest.db` 的 `items` / `item_creators` **逐字节未变**；`var/seal_ingest.db` 的 `seals` / `seal_links` / `seal_images` **逐字节未变**；三线既有就绪包（`exports/person_*` / `exports/item_*` / `exports/seal_*`）**未动** | 跑前 / 跑后四库的**内容指纹**（列数 ＋ 行数 ＋ 有序全字段导出 sha256；**禁用库文件 md5**，§8 第 6 条）＋ 三线就绪包目录清单与 mtime（**未变**） | `yinpu.db` / `var/person_ingest.db` / `var/item_ingest.db` / `var/seal_ingest.db` 任一表内容变化；或三线既有 `exports/**` 被改写 / 删除；或用库文件 md5 作判据 |
| **AC-60 `POST /api/relations/package` 可达且重建幂等（仅时间戳变 / JSONL 字节不变）（v1.20）** | **三条可机械判负子项 ＋ 两条负向**：**① 可达**——`POST /api/relations/package`（无参数）返 **200**，响应为就绪包摘要且 **`key_face_status == "pending_xiai"`**、`rows` 为整数；**② 重建幂等**——**同批次连续两次 `POST /api/relations/package?batch_id=<id>`** 后：**`relations.jsonl` 的内容逐字节一致**（**md5 两次相等 / 内容指纹不变**），**而 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 随重建时点变化**（**即「仅时间戳变、内容不变」**）；**③ 零联网与不写 xiai**——**重建期间不产生任何对源站（`yin.fudan.edu.cn`）的请求**、**`xiai/**` 任一文件未新增 / 未改写**；**（负向）**：**未白名单查询参数（如 `?foo=1`）⇒ 须 400（`UNSUPPORTED_PARAM`）**；**指定不存在的 `batch_id` ⇒ 须 404（`BATCH_NOT_FOUND`）**；**回包非结构化 JSON（HTML 错误页 / 200＋空 `data` 冒充）⇒ FAIL** | 两次 `POST` 的 200 响应体（`generated_at` / `content_fingerprint`）＋ **两次 `relations.jsonl` 的 `md5` 逐字节比对输出**（须相等）＋ **两次 `manifest.json` 的 `created_at` 读数**（须不等 / 随重建时点变化）＋ **源站请求计数（＝0）** ＋ **`xiai/**` 目录清单与 mtime（未变）** | **①** `/api/relations/package` 不可达 / 非 200；**或** **②** 重建后 `relations.jsonl` 内容发生变化（**重建非幂等**）；**或** **③** 重建期间产生源站请求 / 写了 `xiai/**` 任一文件；**或**（负向）未白名单参数未 400 / 批次不存在未 404 / 回包非结构化 JSON |
| **AC-61 零联网（无新增采集请求）（v1.20）** | **本需求不新增任何采集请求**（**零联网**）：**`relations.jsonl` 出包 / `GET /api/relations/summary` 摘要 / `POST /api/relations/package` 重建全程，对源站（`yin.fudan.edu.cn`）的请求数 ＝ 0**（**纯本库联立**，四线既有数据已够） | **源站请求计数（＝0；抓包 / 请求日志 / 代理计数任一可复算口径）** ＋ 出包 / 摘要期间的进程网络活动证据 | 出包 / 摘要 / 重建期间**产生任何源站请求**（**含 `person/*` / `book/*` / `seal/*` / `graph/*` / `statistic/*` / `iiif_proxy/*`**）；或为「补取」而重新联网 |
| **AC-62 拖曳上传全链路（drop ⇒ `POST /api/jobs/upload` ⇒ 表单拿到服务器侧 `pdf_path` ⇒ E1 `201`）（v1.21）** | 在真浏览器里对【印谱解析】页的新建 job 区**拖入一个真 PDF**（或点击选文件）⇒ 触发 **`POST /api/jobs/upload`**（**不是 E1**）⇒ 响应 `201` / `200` ⇒ 提交的表单 `pdf_path` ＝ **响应里的服务器侧 `pdf_path`**（**不是**本地文件名）⇒ 提交 ⇒ E1 返 **`201`**（带 `job_id`） | **拖放事件与网络记录**（`POST /api/jobs/upload` 的请求体与响应体原文）＋ **表单 `pdf_path` 字段值快照**（须**逐字等于**响应的 `pdf_path`）＋ **随后 `POST /api/jobs` 的 `201` 响应体**（含 `job_id`） | 拖曳未触发上传（**把本地文件名当 `pdf_path` 提交**）；或表单 `pdf_path` ≠ 响应 `pdf_path`；或 E1 最终非 `201`；或上传走了 E1（无 upload 请求） |
| **AC-63 非 PDF 判负（`400 NOT_A_PDF`）（v1.21）** | `POST /api/jobs/upload` 送**首字节非 `%PDF-`** 的字节（如纯文本 / JPEG）⇒ **`400`** ＋ 体含机器码 **`NOT_A_PDF`**；**且** `inbox/<yyyymmdd>/` 下**无新增文件**（不得留半成品） | 响应状态码与 **JSON 体原文** ＋ 上传前后 `inbox/` **文件清单 diff（须无新增 / 或已清理）** ＋ 结构化 JSON 断言（**非 HTML**） | 返 `200` / `201`；或错误体非结构化 JSON（HTML 错误页）；或盘上留下非 PDF 半成品；或**空体也返 `NOT_A_PDF`**（须 `EMPTY_BODY`，见 AC-64） |
| **AC-64 空体（`400 EMPTY_BODY`）（v1.21）** | `Content-Type: application/pdf` ＋ **0 字节**体 ⇒ **`400`** ＋ 机器码 **`EMPTY_BODY`** | 响应状态码与 **JSON 体原文** | 返 `400 NOT_A_PDF`（空体无首字节）；或返 `200` / `201`；或非结构化 JSON |
| **AC-65 超限（`413`，且不得先写满盘）（v1.21）** | 上传**大于单文件上限**（**默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准——2026-10-11 起 ＝ 5 GiB（5368709120 B）**；**原写「默认 512 MiB」已被 v1.22 取代**；**判据逻辑未变**）的体 ⇒ **`413`** ＋ 机器码 **`PAYLOAD_TOO_LARGE`**；**且**：**（a）盘上不得留下被拒文件的完整 / 超限分片**（已写分片须删除；判据＝**残留字节 ＝ 0** 或**无残留文件**）；**（b）不得依赖「先写满盘再比较」**——证据须能显示**边写边判**（写盘峰值字节 ≤ 上限 ＋ 报错早于整车收完） | 响应状态码与 **JSON 体原文** ＋ 上传前后 `inbox/` 清单 与 **盘上残留字节数（＝0）** ＋ **边写边判的实现证据**（分块写入日志 / 计数钩子；**不得只给结论**） | 返 `400` / `200`（须 `413`）；或盘上留下被拒文件的完整字节 / 超限分片；或证据显示「先写满盘再报错」（实现先 `await request.body()` / 先落整文件再比较） |
| **AC-66 同名同内容幂等（`200` `idempotent:true` 且 mtime 不变）（v1.21）** | **同名且字节相同**的 PDF 连传两次 ⇒ 第二次 **`200`** ＋ `idempotent:true`、`dedup_suffix:false`；**目标文件的 `sha256` 与 `mtime` 均不变**（**不重写**）；`inbox/<yyyymmdd>/` **文件数不变** | 两次响应体 ＋ 目标文件两次的 **`sha256` 与 `stat` mtime 读数（须相等）** ＋ 目录清单（文件数不变） | 第二次返 `201`（重写）；或 mtime / sha256 变化；或**产生第二个文件**（多余 `-<sha>` 后缀）；或文件数增加 |
| **AC-67 同名异内容不覆盖（落后缀且原文件字节不变）（v1.21）** | **同名但字节不同**的 PDF 再传 ⇒ **`201`** ＋ `dedup_suffix:true`，落 **`<basename>-<sha256[:8]>.pdf`**；**原文件的字节与 mtime 不变** | 响应体 `filename` / `dedup_suffix` ＋ 两个文件的 `sha256`（各自 ＝ 各自字节） ＋ **原文件 sha256 / mtime 的前后读数（须不变）** | **覆盖原文件**（原文件 sha256 变化）；或未落后缀（同一路径被改写）；或原文件被删 / 改名 |
| **AC-68 本端点零 DB 写（`jobs` 行数前后不变）（v1.21）** | 调 `POST /api/jobs/upload`（**成功 / 失败各至少一次**）前后：**`jobs` / `job_pages` / `stamps` 的行数与内容指纹逐字节不变** | 调用前后三表的**行数 ＋ 有序全字段导出 sha256**（**禁用库文件 md5**，§8 第 6 条） | `jobs` 行数 +1（建了 job）；或任一表内容变化；或用库文件 md5 作判据 |
| **AC-69 E1 契约未变（原 `400` / `409` 逐条仍成立）（v1.21）** | **逐条复跑 E1 既有行为**：① `pdf_path` 不存在 ⇒ **`400`**（含 `detail`，`error = PDF_NOT_FOUND`）；② 非 PDF 的既有文件 ⇒ **`400 NOT_A_PDF`**；③ 同 `pdf_path` 存在活跃 job ⇒ **`409` ＋ 既有 `job_id`**（`error = ACTIVE_JOB_EXISTS`，`job_id` 必填）；④ 正常新建 ⇒ **`201 {job_id, state, total_pages, created_at}`**；**且** E8 落盘后的 `pdf_path` 喂给 E1 **走 ④ 成功** | 四条请求 / 响应原文（**并排给出**，逐条对照 §3.1 / §3.4 的冻结形状） ＋ `409` 体的 `job_id` 断言（**须 ＝ 既有活跃 job**） ＋ E8 → E1 的联调响应 | 任一条 E1 行为改变（HTTP 码或响应体形状）；或 `409` 缺 `job_id`；或 E8 返回的 `pdf_path` 喂给 E1 **不成立 / 触发 `400 PDF_NOT_FOUND`** |
| **AC-70 折叠手输仍在且默认收起（v1.21）** | 新建 job 区存在标题**逐字「高级：手输服务器路径」的折叠区**，**默认收起**（初始渲染时其内容 / 原 `pdf_path` 文本框**不可见**：`open=false` 或计算样式 `display:none`）；**展开后**原 `pdf_path` 文本输入框**可用**且其值能提交给 E1 | 折叠区 DOM（**标题逐字** ＋ 初始 `open` / `display` 计算值） ＋ 展开后输入框可见性 ＋ **用该输入框提交 E1 的 `201` 响应** | 折叠区缺失 / 标题不符；或 **默认展开**；或手输框被删除 / 展开后不可用；或手输值不能提交 |
| **AC-71 上传进度可见（v1.21）** | 上传一个**足够大的** PDF（建议 ≥ 100 MB）时，界面在传输过程中**显示进度百分比**（读数随传输**单调不降**、至少出现 **≥ 2 个不同百分比值**），完成后切到「已就绪」；**实现用 `XMLHttpRequest` 的上传进度事件**（**不用 `fetch`**） | 上传期间 **≥ 2 次进度读数快照**（含百分比） ＋ 完成态快照 ＋ **实现证据**（`xhr.upload.onprogress` 绑定；**非仅结论**） | 无进度显示（只有「上传中」）；或进度恒 `0` / 恒 `100`（不随传输更新）；或把「已就绪」提前到传输完成之前 |

**AC 计数＝13 条**（**v1.0** 建立；**v1.1 未增减任何 AC，仍 13 条**——本版只改写 **AC-11**（钉为二值判定）与 **AC-12**（改可复算式并拆出「无 BLOB」独立子项），并为 **AC-03 / AC-04** 钉值）。**v1.2 亦未增减任何 AC：仍 13 条**——本版只**改写** **AC-07**（加书名 × 页区间过滤）与 **AC-11**（判负形态列改取反式）两条的**判据表述**，**未新增、未删减 AC**；本版新增的 **E6 / E7 属端点**（不各设 AC），其证据面落在 **AC-06** 与结果页裁图的**人工可见性**上。**每条均为可机械判负**；**证据未留档即视为未通过**。**v1.3 亦未增减任何 AC：仍 13 条**——本版只**改写** **AC-01**（幂等判据改「键集合与内容不变」）、**AC-03**（点位口径钉定为 `done_pages/total_pages`，两点位 + ±1 页容差须写实际百分比）、**AC-08**（判负绑定 §3.12 键路径）、**AC-10**（适用面＝新增解析链路）四条**判据表述**，**未新增、未删减 AC**；本版新增的 **§7.1 验收夹具纪律**与 **§3.10–§3.13** 均为**口径 / 形状登记**，**不各设 AC**。**新增 AC 的动议须走 §0.4**（例：`has_more↔next_cursor` 一致性能否升格为独立 AC——本版按「已有 S-3 与 §3.10 承载，不单列」处置）。

**（v1.7 更新｜留痕）**：**新增 AC-14 〜 AC-20（共 7 条 ⇒ §7 现共 20 条，AC-01 〜 AC-20）**；上句「**AC 计数＝13 条**」系 **v1.0 〜 v1.6 时点读数**，**原文逐字保留 + 就地留痕**。**新增分布（v1.7）** ＝ **页签与路由可达 1**（AC-14）＋ **全量采集落库 570/570 与失败清单可复算 1**（AC-15）＋ **关联面非空（读详情页）1**（AC-16）＋ **幂等（内容指纹不变）1**（AC-17）＋ **只加法（`yinpu.db` / `exports/fb_*` 未动）1**（AC-18）＋ **归一化负向（生卒 `?` / 空 ⇒ `null`）1**（AC-19）＋ **抽取标注（无权威分类）1**（AC-20）。**编号唯一、无跳号**（AC-01 〜 AC-20 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-13 一字未动**）。**依据 ＝ §3.15（含 §3.15.1 〜 §3.15.9）＋ 拆解件 §7 的 A-1 〜 A-7**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.8 更新｜留痕）**：**新增 AC-21 〜 AC-22（共 2 条 ⇒ §7 现共 22 条，AC-01 〜 AC-22）**；上句「**§7 现共 20 条，AC-01 〜 AC-20**」（**v1.7 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.8）** ＝ **交付缝 manifest 必含字段与 `schema_version==1`（可脚本校）1**（AC-21）＋ **交付缝硬口径逐行可校（幂等键非空且批内唯一 / `*_chs` 副字段存在 / 生卒整数或 `null` 无特值 / 抽取项带 `extraction` 标注）1**（AC-22）。**编号唯一、无跳号**（AC-01 〜 AC-22 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-20 一字未动**）。**依据 ＝ §3.15.1 表下注（v1.8 追加）＋ §3.15.10（交付缝冻结）＋ Kevin 2026-10-10 范围裁定**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.9 更新｜留痕）**：**新增 AC-23（共 1 条 ⇒ §7 现共 23 条，AC-01 〜 AC-23）**；上句「**§7 现共 22 条，AC-01 〜 AC-22**」（**v1.8 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.9）** ＝ **页签文案（恰为【印谱解析】与【印人采集】）＋ tabbar 位于 `main` 内且在 `RouterView` 之前 ＋ 固定页眉滚动后仍贴顶且不遮挡内容，三条可机械判负子项各 1 条**（AC-23）。**编号唯一、无跳号**（AC-01 〜 AC-23 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-22 一字未动**——**AC-14 只追加 v1.9 注、行内文字未改写**）。**依据 ＝ §3.15.2 页签与路由 `/persons`（v1.9 注）＋ Kevin 2026-10-10 新口径「页签【任务页】→【印谱解析】＋ tabbar 下移 / 顶部固定页眉标题区」**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.10 更新｜留痕）**：**新增 AC-24（共 1 条 ⇒ §7 现共 24 条，AC-01 〜 AC-24）**；上句「**§7 现共 23 条，AC-01 〜 AC-23**」（**v1.9 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.10）** ＝ **xiai 就绪导入包键面与形态（键面 ⊆ 18 键且无多余键 / 三桶为 `string[]` / sidecar 三数组等长且元素恒 `rule-based` 且无 `from` / 行数＝570 且幂等键唯一 / manifest 键面 diff＝0，五条子项各 1 条）1**（AC-24）。**编号唯一、无跳号**（AC-01 〜 AC-24 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-23 一字未动**）。**依据 ＝ §3.15.11（xiai 就绪导入包）＋ 交接件 `feicui/docs/person-ingest-handoff-v0.1.md` 第七节 ＋ Kevin 2026-10-10 三答**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.11 更新｜留痕）**：**本版 AC 计数不变（仍 24 条，AC-01 〜 AC-24）**（**未新增、未删减 AC**）；**AC-24 由 v1.10 的「五条可机械判负子项」原位改写为「三态判据」**——**(a) 21 键形态 ⇒ PASS**；**(b) 18 键形态（缺 3 键）⇒ 亦 PASS（兼容）**；**(c) 旧 feicui 形态（32 键 / 三桶为对象数组）⇒ FAIL**；并写明 **`'rule-based'` 只作本批数据断言、不得写成对外契约判据**（**值域不封闭**）。**依据 ＝ §3.15.11 v1.11 升版注（xiai 线 D-1 回执：键面 18 → 21；缺键不拒收）＋ §3.15.12（Kevin 2026-10-10 关联面裁定）**。**原 v1.10 五子项的逐字文本保留于 `docs/versions/feicui.spec.v1.10.md` §7**（**历史行逐字保留、只增不改**；**AC-01 〜 AC-23 一字未动**）。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.12 更新｜留痕）**：**新增 AC-25 〜 AC-32（共 8 条 ⇒ §7 现共 32 条，AC-01 〜 AC-32）**；上句「**§7 现共 24 条，AC-01 〜 AC-24**」（**v1.11 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.12）** ＝ **页签【印谱采集】与路由 `/items` 可达 1**（AC-25）＋ **全量采集落库 1742/1742 与失败清单可复算 1**（AC-26）＋ **幂等键 `source_item_id` 非空且唯一＝行数 / `as_book_id` 唯一 1**（AC-27）＋ **抽样锚点（`seqid=2214`… / `seqid=3547`…）1**（AC-28）＋ **数值字段负向（`volume_count` / `date_year` 整数或 `null` 无特值）1**（AC-29）＋ **独立库隔离（`yinpu.db` 与 `var/person_ingest.db` 内容指纹未变）1**（AC-30）＋ **就绪包 manifest 必含项与 `key_face_status: pending_xiai` 明示 1**（AC-31）＋ **幂等（同批次重跑行数与内容指纹不变）1**（AC-32）。**编号唯一、无跳号**（AC-01 〜 AC-32 连续）。**本版对既有 AC 的唯一改动 ＝ AC-23 的原位改写**（**页签集合 2 → 3：【印谱解析】/【印人采集】/【印谱采集】**，行内已加「v1.12 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.11.md` §7）；**AC-01 〜 AC-22 / AC-24 一字未动**（**AC-14 的 v1.9 注保留**）。**依据 ＝ §3.16（含 §3.16.1 〜 §3.16.9）＋ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §7 的 IT-1 〜 IT-8 ＋ Kevin 2026-10-10 门控四答（I-1 〜 I-4）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.13 更新｜留痕）**：**本版 AC 计数不变（仍 32 条，AC-01 〜 AC-32）**（**未新增、未删减 AC、未改编号**）；**本版因采集口径偏离（§3.16.6 v1.13）原位改写 AC-28 / AC-31 两条**——**AC-28**：**`donor`（`bookDonor`）降为 best-effort**（detail 独有字段；**detail 默认关 ⇒ 缺失不判负、存在须逐字命中 `林章松`**），**硬档（卷册 / 纪年 / 公元 / `hasImage`，均列表可取）仍判负**；**AC-31**：**manifest 必含项增补 `detail_policy` / 因 detail 降级而缺失的三字段清单 / `detail_unconfirmed` 计数**；并写明 **`source_face` 取值集合改为 `book_graph` / `person_graph` / `book_detail`（后者仅 best-effort 出现）**。**依据 ＝ §3.16.6 v1.13（采集口径偏离：本体取 `book/list` / 关联主源 `graph/book` / detail 降 best-effort）＋ §3.16.8（sidecar 随动）＋ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §10（Zang 2026-10-10 采集口径偏离登记）**。**原 AC-28 / AC-31 的逐字文本保留于 `docs/versions/feicui.spec.v1.12.md` §7**（**历史行逐字保留、只增不改**；**AC-01 〜 AC-27 / AC-32 一字未动**）。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.14 更新｜留痕）**：**新增 AC-33（共 1 条 ⇒ §7 现共 33 条，AC-01 〜 AC-33）**；上句「**本版 AC 计数不变（仍 32 条，AC-01 〜 AC-32）**」（**v1.13 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.14）** ＝ **`POST /api/items/package` 可达且重建幂等（同批次重建仅 `created_at` / `generated_at` 时间戳变、`items.jsonl` 与 `item_creators.jsonl` 字节不变；零联网；不写 xiai）＋ 两条负向（未白名单参数 400 / 批次不存在 404）1**（AC-33）。**编号唯一、无跳号**（AC-01 〜 AC-33 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-32 一字未动**）。**依据 ＝ §3.16.3 Q5（v1.14 追加）＋ §3.16.5（v1.14 重建幂等）＋ Neng 质检 OBS（spec/实现分叉：`POST /api/items/package` 未入规范；点按钮会重写就绪包时间戳）＋ Kong 实现读数（`server/app/routers/items.py` / `server/app/items.py`：`UNSUPPORTED_PARAM` / `BATCH_NOT_FOUND` / `NO_BATCH`）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.15 更新｜留痕）**：**新增 AC-34 〜 AC-46（共 13 条 ⇒ §7 现共 46 条，AC-01 〜 AC-46）**；上句「**新增 AC-33（共 1 条 ⇒ §7 现共 33 条，AC-01 〜 AC-33）**」（**v1.14 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.15）** ＝ **页签【印章采集】与路由 `/seals` 可达 1**（AC-34）＋ **全量采集落库 3679/3679 与失败清单可复算 1**（AC-35）＋ **幂等键 `source_seal_id`（`seqid`）非空且唯一＝行数 1**（AC-36）＋ **`audit_status` 字段保留与分布统计（2929/716/31/3）1**（AC-37）＋ **形製码表纯函数无冲突且源文「异性」逐字 1**（AC-38）＋ **桥接（印章涉 19 种印谱 ⊆ item 库）1**（AC-39）＋ **影像取数 / 张数 / 实际计数 / 放大尺寸判负 / `NaN_` 源侧无图 1**（AC-40）＋ **影像为 TIFF 容器（魔数判负）＋ 单张 ≤ 4 MiB 且 ≤ 1 MB 输入档 1**（AC-41）＋ **`images/` 路径形状 `<sha256[:2]>/<sha256>.tiff` 且 sha256 与字节自洽 1**（AC-42）＋ **`images_manifest.jsonl` 与文件一一对应（无孤儿 / 无缺失）1**（AC-43）＋ **`/api/seals` 读口分页自洽且 `cursor` ⇒ 400 1**（AC-44）＋ **`/api/seals/package` 可达且重建幂等（`images/` 不得删或重转）1**（AC-45）＋ **独立库隔离（`yinpu.db` / `var/person_ingest.db` / `var/item_ingest.db` 内容指纹未变）1**（AC-46）。**编号唯一、无跳号**（AC-01 〜 AC-46 连续）。**本版对既有 AC 的唯一改动 ＝ AC-23 的原位改写**（**页签集合 3 → 4：【印谱解析】/【印人采集】/【印谱采集】/【印章采集】**，行内已加「v1.15 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.14.md` §7）；**AC-01 〜 AC-22 / AC-24 〜 AC-33 一字未动**（**AC-14 的 v1.9 注 / AC-28 · AC-31 的 v1.13 注保留**）。**影像面 v1.15 改口径（Kevin 裁定：TIFF 直供 xiai 影像库）**——**AC-40 〜 AC-43 承载其机械判负面**。**依据 ＝ §3.17（含 §3.17.1 〜 §3.17.9）＋ Kevin 2026-10-10 三条裁定 A / B（改口径 TIFF 直供）/ C ＋ Zang 实测源契约与字段面**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.16 更新｜留痕）**：**新增 AC-47 〜 AC-52（共 6 条 ⇒ §7 现共 52 条，AC-01 〜 AC-52）**；上句「**新增 AC-34 〜 AC-46（共 13 条 ⇒ §7 现共 46 条，AC-01 〜 AC-46）**」（**v1.15 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.16）** ＝ **影像 `failed` 桶空或仅瞬态且附重跑命令 1**（AC-47）＋ **`source_no_image` 按 ref 前缀聚合清单 ＋ 计数 ＋ 样例 `seqid` 1**（AC-48）＋ **`images_manifest.jsonl` ↔ `images/**` 双向一一对应（无孤儿 / 无缺失，两方向计数）1**（AC-49）＋ **每行 `sha256` 与 TIFF 字节逐行自洽（随机 20 行重算）1**（AC-50）＋ **TIFF 魔数逐行成立 ＋ 单张 ≤ 双档上限 1**（AC-51）＋ **影像台账每行有 `width` / `height` 1**（AC-52）。**编号唯一、无跳号**（AC-01 〜 AC-52 连续）。**本版对既有 AC 的唯一改动 ＝ AC-40 的 `NaN_` ref 状态记号原位改写（`source_missing` ⇒ `source_no_image`，与 §3.17.8 统一、同一处留痕）**；**AC-01 〜 AC-39 / AC-41 〜 AC-46 一字未动**；**AC-49 / AC-50 / AC-51 系承 v1.15 的 AC-43 / AC-42 / AC-41 加严，另立新号、不重号**）。**依据 ＝ §3.17.6 ⑤（v1.16 追注）＋ §3.17.8 a-v1.16 追加块（源侧缺图三态分桶 / 共用窗口限流 / 逐张台账 / 放大尺寸判负定量依据）＋ Zang v1.15 后实测缺口 ＋ `ops/seal-ingest/09_upscale_probe.json`**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.17 更新｜留痕）**：**新增 AC-53（共 1 条 ⇒ §7 现共 53 条，AC-01 〜 AC-53）**；上句「**新增 AC-47 〜 AC-52（共 6 条 ⇒ §7 现共 52 条，AC-01 〜 AC-52）**」（**v1.16 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.17）** ＝ **`bad_bytes` 实例（`2_3609_1`）归 `source_no_image` 面不在 `failed` 1**（AC-53）。**编号唯一、无跳号**（AC-01 〜 AC-53 连续）。**本版对既有 AC 的改动 ＝ AC-47 原位改写（由「`failed` 桶空或仅瞬态且附重跑命令」改为「`failed` ＝ 0」）＋ AC-48 证据形式随动（子因计数由「两类」扩为「三类」）**（**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.16.md` §7；系原位改写，不是「既有条款自动失效」**）；**AC-01 〜 AC-46 / AC-49 〜 AC-52 一字未动**。**依据 ＝ §3.17.8 a-v1.16 块（子因由二扩三之原位改写）＋ §3.17.8 a-v1.17 追加块（子因穷尽枚举三类 / `bad_bytes` 实例锚 `2_3609_1` / `failed` ＝ 0 理由）＋ Zang 影像台账终态 6765/6765 实测（`ok 6347` / `source_no_image 417`（`http_500` 415 ＋ `nan_ref` 2）/ `failed` 唯一项 `2_3609_1` 归 `bad_bytes`）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.18 更新｜留痕）**：**新增 AC-54（共 1 条 ⇒ §7 现共 54 条，AC-01 〜 AC-54）**；上句「**新增 AC-53（共 1 条 ⇒ §7 现共 53 条，AC-01 〜 AC-53）**」（**v1.17 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.18）** ＝ **超 xiai store 4 MiB 上限的表行须逐行标记 ＋ 顶层计数 ＋ 清单，且不得自行降采样 / 转码 1**（AC-54）。**编号唯一、无跳号**（AC-01 〜 AC-54 连续）。**本版对既有 AC 的改动 ＝ AC-41 / AC-51 原位改写（删去恒假的「输入档 ≤ 1 MB」判据——依据 ＝ xiai `server/app/store.py::validate_payload` 只校验「空 / 4 MiB / TIFF 魔数」三面）＋ AC-50 原位更正（`tiff_sha256` ⇒ `sha256`）**（**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.17.md` §7；系原位改写 / 更正，不是「既有条款自动失效」**）；**AC-01 〜 AC-40 / AC-42 〜 AC-49 / AC-52 / AC-53 一字未动**。**依据 ＝ §3.17.8 ④（逐张台账字段语义原位更正）＋ §3.17.8 a-v1.18 追加块（字段语义 / 超 4 MiB 桶）＋ Zang 对本包实物（`exports/seal_import_seal_20261010_01/`）实测（`images_manifest.jsonl` 键面无 `tiff_sha256`；`sha256`/`bytes` 与 TIFF 字节逐行自洽；超 4 MiB 6 条 ＝ `seqid 3353 / 3366 / 3367 / 3464 / 3506 / 3510`）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.19 更新｜留痕）**：**本版 AC 计数不变（仍 54 条，AC-01 〜 AC-54）**（**未新增、未删减 AC**）；**本版对既有 AC 的唯一改动 ＝ AC-41 原位收窄**——**字面判负由「单张 > 4 MiB ⇒ FAIL」收窄为「未被逐行标记 `oversize_for_xiai_store` 的超档行 ⇒ FAIL」**（**超档本身不判负；已标记的超档行豁免本 AC**），**并写明与 AC-54 的分工（AC-54 管「标记 / 顶层计数 / 清单 / 不得自行降采样或转码」，AC-41 管「容器与尺寸上限的可判定口径」）**（**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md` §7；系原位收窄，不是「既有条款自动失效」**）；**AC-01 〜 AC-40 / AC-42 〜 AC-54 一字未动**。**依据 ＝ Neng 独立质检 OBS-1（AC-41（v1.15 立 / v1.18 已部分原位改写）与 AC-54（v1.18 新立）文字张力：同一事实（6 张超档）在两 AC 下一判负一豁免 ⇒ 下一轮质检无法机械判定；本版按「超档允许、但必须逐行标记；未标记的超档行才是 FAIL」原位收窄收口）＋ Zang 对包内实物实测（`images/` 6347 张中 6 张 > 4 MiB（`seqid 3353/3366/3367/3464/3506/3510`，均 `yt`，4.38–4.96 MB），已逐行标 `oversize_for_xiai_store: true` ＋ 顶层计数 6 ＋ 清单；1–4 MiB 219 张）**。**本版未新增任何 AC**——**逐字理由：「源侧 `ref_id` 未命中 person 库（印主 8/438、篆者 1/403、边款篆者 6/11）属源侧引用未收录、不判负，落 §3.17.8 a-v1.19 ① 记账口径；端点响应顶层内部键 `_db_path` 属三线共有惯例、非本线不一致，落 §3.17.8 a-v1.19 ② 观察项；二者均非 feicui 可判负的实现目标，故不设新 AC」**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.20 更新｜留痕）**：**新增 AC-55 〜 AC-61（共 7 条 ⇒ §7 现共 61 条，AC-01 〜 AC-61）**；上句「**本版 AC 计数不变（仍 54 条，AC-01 〜 AC-54）**」（**v1.19 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.20）＝ 拆解件 §4 的 A-1 〜 A-7 逐条对应**——**各 `predicate` 计数与 `report.json` 一致 1**（AC-55）＋ **去重算术可复算（`|A∪B| = |A| + |B| − |A∩B|`，点名 1349 / 1281 / 1249 ⇒ 1381）1**（AC-56）＋ **可连键逐条成立（除 `ghost` 行）1**（AC-57）＋ **未命中 / 幽灵有清单与计数（不为 0 必逐条列出）1**（AC-58）＋ **四库指纹 ＋ 三包未变 1**（AC-59）＋ **重建幂等（仅时间戳变 / JSONL 字节不变）1**（AC-60）＋ **零联网（无新增采集请求）1**（AC-61）。**编号唯一、无跳号**（AC-01 〜 AC-61 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-54 一字未动**）。**依据 ＝ §3.18（含 §3.18.1 〜 §3.18.8）＋ 拆解件 `feicui/docs/relation-ingest-draft-v0.1.md` §4 的 A-1 〜 A-7 ＋ §5 边界**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.21 更新｜留痕）**：**新增 AC-62 〜 AC-71（共 10 条 ⇒ §7 现共 71 条，AC-01 〜 AC-71）**；上句「**新增 AC-55 〜 AC-61（共 7 条 ⇒ §7 现共 61 条，AC-01 〜 AC-61）**」（**v1.20 时点读数**）**原文逐字保留 + 就地留痕**。**新增分布（v1.21）** ＝ **拖曳上传全链路（drop ⇒ `POST /api/jobs/upload` ⇒ 表单拿到 `pdf_path` ⇒ E1 `201`）1**（AC-62）＋ **非 PDF 判负（`400 NOT_A_PDF`）1**（AC-63）＋ **空体（`400 EMPTY_BODY`）1**（AC-64）＋ **超限（`413`，且不得先写满盘）1**（AC-65）＋ **同名同内容幂等（`200` `idempotent:true` 且 mtime 不变）1**（AC-66）＋ **同名异内容不覆盖（落后缀且原文件字节不变）1**（AC-67）＋ **本端点零 DB 写（`jobs` 行数前后不变）1**（AC-68）＋ **E1 契约未变（原 `400` / `409` 逐条仍成立）1**（AC-69）＋ **折叠手输仍在且默认收起 1**（AC-70）＋ **上传进度可见 1**（AC-71）。**编号唯一、无跳号**（AC-01 〜 AC-71 连续）。**本版不改任何既有 AC 的编号与行内文字**（**AC-01 〜 AC-61 一字未动**）。**依据 ＝ §3.19（含 §3.19.1 〜 §3.19.7）＋ §3.1 E8 行 / 表下注（E8）＋ §3.4 表 `413` 行与 v1.21 随动 ＋ Kevin 2026-10-10 两条裁定**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

**（v1.22 更新｜留痕）**：**本版 AC 计数不变（仍 71 条，AC-01 〜 AC-71）**（**未新增、未删减 AC、未改编号**）；**本版对既有 AC 的唯一改动 ＝ AC-65 的上限默认值措辞同步**（`默认 512 MiB；config 常量` ⇒ **默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准；2026-10-11 起 ＝ 5 GiB（5368709120 B）**，**判据逻辑一字未改**——「**大于单文件上限 ⇒ `413`**」不变，**只使引用新值**）；**该行标题仍标 `（v1.21）`**（系 v1.21 立、v1.22 随动，**不另立新号**）。**依据 ＝ §3.19.2（v1.22 数值同步）＋ Kevin 2026-10-11 裁定（§9-R40 结案）**。**落地状态 ＝ 已定、落地中（由 Kong 执行）**；**验收执行归 Neng**；**本版不含任何「本轮已通过」结论**。

### 7.1 验收夹具纪律（**v1.3 新增**｜由两起实测事故换来）

> **性质**：本节约束**验收 / 自测夹具本身**（不是被检产品）。**依据**：① **失控轮**——服务端给出「`has_more=true` 而 `next_cursor=null`」时，夹具的终止条件 `if not body["has_more"]: break` **永不成立** ⇒ 同一条 FAIL 打印 **54,254** 次、证据文件 2.8 MB、最终被 SIGTERM 杀掉，**那一轮结论全部作废**（`REPORT_1b-ii.md` §2.1）；② **假绿形态**——中途终止 / 漏挂子命令 / `$?` 被 `| tee` 吞掉时，汇总**可能少跑几条却仍报 `FAIL=0`**（`qa-recheck/p1b-neng/REPORT.md` §6.4、O-5）。

| # | 纪律（**硬约束**） | 判负形态 |
| --- | --- | --- |
| F-1 | **翻页循环必须有硬上界**（`ceil(total/limit)+2` 或常量上限 50），不得用 `while True` | 出现无上界循环 |
| F-2 | **夹具不得把「被测方的自洽」当作自己的终止条件**：游标推进须由**三条件**之一中止（`has_more` 为假 / `next_cursor` 为空 / 游标与上页重复），且**一条 FAIL 内收敛**（附两页原始报文） | 终止条件依赖服务端给出自洽信封 |
| F-3 | **重复 FAIL 折叠计数**：同一 `(断言名, 判据)` 打印 ≤3 次，其余只累加计数，**收尾必须出清单**（按命中次数降序）——**折叠 ≠ 静默** | 同一判据刷屏把其他证据挤出日志；或折叠后不再出现 |
| F-4 | **非信封 / 关键字段为空 ⇒ 显式 FAIL + 中止该子段**（不产级联 FAIL、不带脏值继续断言） | 一条前置异常把后续 N 条染成假 FAIL / 假 PASS |
| F-5 | **`finally` 清理**：停服务一律**精确 PID**（并做身份校验），删临时物**只删自己建的同名前缀目录**；**全程禁用 `pkill -f` / `killall` / 宽匹配 kill** | 残留服务占端口；或误删他人产物 |
| F-6 | **不写死端口**：动态探测空闲端口，开头断言无监听，硬跳过登记端口与保留段（5173 / 5174） | 与别人撞端口；或与既有验收判据端口对不上 |
| F-7 | **断言总数闸门**：收尾必须有「**实际运行的断言总数 == 预期常数**」一条断言（外加「跑到收尾」「子段齐全」「无未收敛护栏命中」三条） | 中途终止仍报 `FAIL=0`（**假绿**） |
| F-8 | **版本身份钉**：被检文件的 md5 **逐文件记录**（开工 / 收官两份）。**结论的适用范围随版本走**——若复检期内被检源码被并行改写，则**执行层结论可平移、接口层结论只对该 md5 版成立**，**不得反向盖章** | 用较新版的复检结果给较旧版的交付盖章 |
| F-9 | **辅助函数不得对调用点的类型做单方面假设**（如假定 `detail` 是 `str` 而调用点传 `list`） | 整轮脚本因 `TypeError` 异常终止 |
| F-10 | **断言「必须被执行」**：恒真判据（只在失败时调用的断言）不得充当「通过」证据——「通过」须由**总会运行**的收敛性断言或总数闸门承载 | 接口全对时该断言一次都没运行 |

---

## 8. 现状时点纪律
（**本文件范围的强制口径**）

1. **原文**：凡写「现状 / 事实 / 实测 / 当前 / 已核对」类段落，**① 内容必须来自磁盘实测或可复算的命令输出**；**② 必须标注核验时点与证据来源**（格式：`核验时点 YYYY-MM-DD HH:MM（Asia/Shanghai）；证据＝<命令或文件路径>`）；**③ 派单 / 聊天 / 转述与磁盘事实不一致时以磁盘事实为准**，并把差异登记（本文件 **§9** 或 **§10**）。
2. **适用范围（非穷举，示例即示例）**：§0.3 基线表、§3.3 的现状数字、§4.x 的「现状」列、§5.x 的实测代价、§6.1 的空闲证据、§7 AC 里写死的基线值（如 AC-07 的 **77**）。
3. **时点戳是证据的一部分**：**无时点戳的现状读数 = 无效读数**；复检时须**重测并刷新时点**，**不得**沿用旧时点。

6. **红线判据纪律：内容指纹，禁用库文件 md5（**v1.3 新增**｜Zang 已裁定口径）**——凡需证明「**数据未变**」的**现状读数**与**红线判据**，**一律使用内容口径**（例：`stamps` 的**列数 + 行数 + 三口径内容指纹**，或可复算 SQL 输出），**禁用数据库文件 md5**。
   **实测依据（本机）**：库处于 **WAL** 时，`yinpu.db` 的**文件** md5 会在**内容无任何变化**的情况下漂移——`254d3ff132d3a8d14dcf8590f45c7232`（1b-i 自测时点 12:29:26）→ `56cbf7afd124e86c6d9f810c0380c3eb`（文件 mtime **12:42:13**，**早于**该轮开工时点）；同刻 `stamps` 的**内容口径**（10 列 / 79 行 + 三口径指纹 `8a21e57d…` / `d7abe995…` / `22bdc0a7…`）**逐字节未变**。WAL 回拷 / 检查点会**重写文件而不改内容**。
   **判负形态**：① 以「库文件 md5 不等」为由判「数据被改」；② 要求复检者提交**库文件 md5** 作为通过判据；③ 用 `sqlite3` CLI + md5 在 WAL 库上取数（**会得到空输入的 md5 假结论**）。
   **同源纪律**：本条第 6 款在**平台规范 v1.29** 与 **`ctrl/PORTS.md` v1.12** 同步写入（跨文件一律适用）。

4. **不得跨文件外推**：本文件的实测结论**只对 feicui 有效**；平台侧现状（如平台规范 §9.1）**以平台规范为准且由平台侧按 §0.4 流程维护**。
5. **已知的转述 ↔ 磁盘差异（本版登记）**：平台规范 **§9.1 现状表**（v1.24 时点 2026-09-20 的读数：**65 行 / 影像缺失 42-65 / `text` 非空 0-65**）与**本文件核验时点 2026-09-20 10:38 的磁盘实测**（**79 行 / 影像缺失 0-79 / `text` 非空 2-79**）**已漂移**——**差异原因＝Kong 侧 F2 数据恢复与增量重跑**（`feicui/f2_report.json`，`generatedAt=2026-09-20T10:10:00+08:00`）。**处置**：平台侧 §9.1 的更正**属平台规范范围内的动作**（须按其 §0.4 流程：先快照 `docs/versions/` → 升版本 → 写 §0.5 变更记录 → **不动历史行**），**本文件只登记差异、不改平台规范**；登记项见 **§9-R9**。

---

## 9. 待 Kevin / Zang 裁定清单

> 口径：本表**只登记事实与选项**，**不带倾向性结论**；未裁定前**不得**据本表执行实现。**编号 R#**（本文件独立编号，与平台规范 §11.3 的 GB-# 不混用）。

| # | 事项 | 现状（**事实 + 时点 + 证据**） | 待裁选项（一句话可改） | 影响面 |
| --- | --- | --- | --- | --- |
| **R1** | **5164 是否加一条 dev 代理 `/feicui → 5195`** | 已定：feicui 前端**独立端口 5195 为主入口**。**实测**：`shu/web/vite.config.js` 内 `grep -n proxy` **零命中**（核验时点 2026-09-20 10:38；证据＝`grep`）——**该代理目前不存在**。**性质＝待确认项，不得写成已定**。**（v1.1 收口：Kevin 已拍板＝要（选项 ②）；落地时点＝feicui 前端骨架起来那一刻（目标现不存在，**本轮不落地**）；实现＝Vite `server.proxy`、**不落 SPA 路由**；**平台规范 §2.2 路由表仍 14 条、AC-88 / AC-89 扫描面不变**；**生产部署须在网关做同构改写**；属 **M1 冻结面之外的基础设施登记、不得当作功能变更**——完整口径见 **§6.4**。原句「性质＝待确认项，不得写成已定」**已被 v1.1 取代**。）** **v1.1 复核仍零命中**（核验时点 2026-09-20 11:29；证据＝`grep -n proxy shu/web/vite.config.js` → 零命中） | ① 不做（5195 独立入口为准）；② 做（须由 Kong 在 `shu/web/vite.config.js` 加 **dev 代理**）（**v1.2 收口**：**Kevin / Zang 已把 1c 口径定死**——`feicui/web` 侧 `base: '/feicui/'` + `server.hmr.clientPort: 5195`；`shu/web` 侧 `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、`changeOrigin: true`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 **14 条**、AC-88 / AC-89 扫描面不变；**生产须网关同构改写**；**四项验收判据原文见 §6.4 v1.2 块**（照录、一字未改）。**性质**＝**M1 冻结面之外的基础设施登记**。**实测**：核验时点 2026-09-20 12:01，两处 `vite.config.js` **均已含**该 proxy 键、`curl` 两条均 **200**（详见 §6.4）） | ⚠ **`shu/web/**` 属 M1 已封版冻结**：若选 ②，**必须先由 Zang/Kevin 明确解除该文件的冻结口径**（改它会作废另一角色的验收结论）；且代理只限 **dev**，不得进构建产物 |
| **R2** | **8501 上的 Streamlit 实例处置** | **实测观察（不改状态判定）**：`lsof -nP -iTCP -sTCP:LISTEN` → `Python 71267 *:8501`；`ps -o pid,ppid,pgid,lstart,command -p 71267` → **PID 71267 / PPID 1（已 reparent）/ PGID 71267**，`lstart = Fri Sep 18 09:51:16 2026`，命令＝`…/Python -m streamlit run app.py --server.port 8501 --server.headless false`；RSS **1546448 KB ≈ 1.47 GB**（核验时点 2026-09-20 10:45）。**（v1.1 收口）该实例已停**——**2026-09-20 10:57:50** 由 **Kong** 按 **Kevin 授权**以**进程组 `TERM`**（`kill -TERM -- -71267`）停止：**1 秒内释放**、**未用 `KILL`**、**无邻接误伤**（27 个无关 node/vite 进程全数存活、ctrl 面板 5555 仍 LISTEN + HTTP 200）；**证据**＝`feicui/ops/8501_stop_evidence.md` + `feicui/ops/8501_stop_before_after.txt`（md5 `cc07f93f30af4bf0af7bb91c8f12cf58`）。**v1.1 独立复核**（核验时点 2026-09-20 11:29）：`lsof -nP -iTCP:8501 -sTCP:LISTEN` → **无监听** ⇒ **8501 现空闲**（§0.3 已同步）。**原句「处置中，见 Kong 报告 / 本文件不写状态定论」已被 v1.1 取代**。**Jing 未 kill、未停、未重启、未占用**该进程 | 处置结论＝**已停止**（见左）；**退役时序**：feicui 主入口改由 5195 承担（§1.4），**`requirements.txt` / venv 中 `streamlit` 的清理仍属 Kong 动作**（§1.4 退役判据） | feicui 退役时序（§1.4）；**阻塞 §1.4「退役完成」判据的最后一环** |
| **R3** | **§4.4 的「必须换栈」阈值草案是否采纳** | §4.4 的 4 条触发条件与量级（**2 万影像 / 50 GB / 20 万行 / 2 写者 / 5 min 备份窗口**）系 **Jing 拟定草案**，**无既有出处**；锚点实测＝现状 **79 行 / 79 影像 / 3.4 MB / 576 KB 库 / 169 GB 可用 / 16 GB RAM** | ① 采纳；② 改数值（给值）；③ 不设阈值（到时再议） | 数据层演进路线、是否引入对象存储 / PostgreSQL 的时点 |
| **R4** | **worker 默认数** | §5.1 拟 **默认 8 / 上限 10**（物理核 10，实测）；§5.3 据此推 worker 池 RSS ≈ **6.5 GB**（单实例峰值 **0.81 GB** 实测）、内存预算 ≈ **8 GB** | ① 采纳 8；② 改值（给值）；③ 按书自动（小书单 worker / 大书多 worker） | 吞吐与内存占用；AC-04 的 N 取值。**（v1.3 收口）已裁＝4**：Zang 已定 **默认 worker 数＝4**（依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽），与 **AC-04 已钉的 `N=4` 对齐**；§5.1 / §5.3 已原位更正并留痕。**原「默认 8（草案，待裁）」不再有效** |
| **R5** | **`group` 归属** | §6.2 拟 `group = shu`（feicui 位于 `bistro/shu/` 下、属印索项目族；PORTS.md §2 既有分组无 `feicui`） | ① `shu`；② 新建独立分组 `feicui`（面板会多一个分组标题） | 面板分组显示、批量启停范围。**（v1.3 收口）已裁＝`shu`**：`ctrl/index.js` 实测两条 feicui 条目（`feicui-api` / `feicui-web`）**均用 `group: 'shu'`**（核验时点 2026-09-20 13:08；证据＝`ctrl/index.js` 第 49 / 58 行）⇒ **实现已按选项①落地**，本项收口 |
| **R6** | **`feicui` / `feicui-api` 何时写入 `index.js` `services` 表** | 现状：`index.js` `services` 表**无 feicui 条目**（实测 `grep -n feicui index.js` **零命中**，核验时点 2026-09-20 10:40）；且 **`feicui/web` 前端工程目录尚不存在**（**v1.1 收敛后的可复跑判据**：`ls -d /Users/kevin/bistro/xiai/feicui/web` ⇒ **`No such file or directory`**；**注意**：`feicui/docs/` **已由本规范自身于 2026-09-20 10:40 建立**——即 §0.1「本文件」的落位目录，**故不得再以「无 `docs/`」作为工程目录不存在的证据**；原 v1.0 句「`ls feicui/docs` → No such file；`feicui/web` 同」**已被 v1.1 取代**，D-7）（**v1.2 原位更正 + 留痕（Neng 复核 OBS-2）**：本行原记「**`feicui/web` 前端工程目录尚不存在**」**已被 v1.2 取代**——**该目录已存在**：核验时点 **2026-09-20 12:00**，`ls -d /Users/kevin/bistro/xiai/feicui/web` **命中**、`stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**。**R6 事项本身（何时写入 `index.js` `services` 表）仍未落地**（同一时点 `grep -n feicui ctrl/index.js` **零命中**）——但**判据的磁盘事实已变**：**不得再以「目录不存在」作为入表阻滞的理由**，§6.2 落地顺序纪律的**工程前提已满足**，入表时点由 Kong 执行 / Zang 确认） | ① 先落地工程再入表（**本规范 §6.2 的落地顺序纪律**）；② 先入表（**有风险**：`startAll` 会因 cwd 不存在失败，破坏「面板托管 N/N 全监听」判据） | 面板托管范围、批量启停可靠性。**（v1.3 收口）已落地**：核验时点 **2026-09-20 13:08**，`ctrl/index.js` 的 `services` 表**已含** `feicui-api`（sid、`port: 5196`、`cmd: './.venv/bin/python'`、`args: ['-m','app.main']`、`cwd: /Users/kevin/bistro/xiai/feicui/server`、`env: {PORT:'5196'}`、`group:'shu'`）与 `feicui-web`（`port: 5195`、`cmd:'npm'`、`args:['run','dev']`、`cwd: /Users/kevin/bistro/xiai/feicui/web`、`group:'shu'`、`directUrl:'http://localhost:5195/feicui/'`）两条——**落地顺序纪律的两种前提（目录存在 + 可 `npm run dev`）均已满足**；**原 v1.2 记「面板托管未落地（grep 零命中）」已被 v1.3 取代**（**该改写系 Kong 执行，Jing 未改 `ctrl/index.js` 一个字节**；`ctrl/index.js` 核验时点即 13:08、md5 `55b101fc643ad06d4bfcb61e56d7710d`）。**注意**：实际 sid 为 **`feicui-web`**（非 v1.2 §6.2 所记 `feicui`）、实际 `directUrl` 带 **`/feicui/`** 前缀（因前端 `base` 已为 `/feicui/`）⇒ §6.2 已按实况回填（**v1.4 路径收口**：本行 4 处 `shu` 路径已**原位更正为 `xiai/...`**（**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**）；**判据可复跑**：改后判据一律用 `ls -d /Users/kevin/bistro/xiai/feicui/web`（**旧写法**`ls -d /Users/kevin/bistro/shu/feicui/web` ⇒ **`No such file or directory`**）；**本项事项（入 `services` 表）的落地状态仍为 v1.3 所记「已落地」**，**新增 feicui 族第三条（`shu`）见 §6.2 表下 v1.4 注 ②**） |
| **R7** | **feicui 前端工程目录位置与形态** | **缺口：磁盘上不存在**（核验时点 2026-09-20 10:37，**v1.1 复核时点 2026-09-20 11:29**；证据＝`ls /Users/kevin/bistro/xiai/feicui/` **无 `web/`**；**`docs/` 由本规范自身建立**（2026-09-20 10:40，§0.1），**不属缺口语义、不得计入本项证据**——原句「无 `web/`、无 `docs/`」**已被 v1.1 取代**，D-7）。§6.2 的 `cwd` 写作**计划路径** `/Users/kevin/bistro/xiai/feicui/web`（**v1.2 原位更正 + 留痕（Neng 复核 OBS-2）**：本行原记「磁盘上不存在（核验时点 2026-09-20 10:37，v1.1 复核 11:29；证据＝`ls` 无 `web/`）」**已被 v1.2 取代**——**`feicui/web` 已存在**，核验时点 **2026-09-20 12:00**：`ls -d /Users/kevin/bistro/xiai/feicui/web` **命中** + `stat -f '%SB'` ＝ **birth 2026-09-20 11:35:25**（另有 `package.json` / `vite.config.js` / `dist/` / `evidence/` 落盘）；§6.2 的 `cwd` 计划路径**即为实际路径**，**该行 cwd 已按 v1.2 回填**） | ① `feicui/web`（默认草案）；② 其他路径（给路径） | §6.2 登记值、§7 AC-13 的启动判据（**v1.4 路径收口**：本行 3 处 `shu` 路径已**原位更正为 `xiai/...`**（**原写 `shu`，已由 v1.4 取代（2026-09-20 14:47 工程改名）**）；**判据可复跑**：`ls /Users/kevin/bistro/shu/feicui/` ⇒ **`No such file or directory`**、`ls -d /Users/kevin/bistro/xiai/feicui/web` ⇒ **命中**；**本项事项（前端工程目录位置与形态）结论不变**——目录已存在（birth 2026-09-20 11:35:25），**改名后现值为 `/Users/kevin/bistro/xiai/feicui/web`**） |
| **R8** | **释文（`seal_name`）补齐路线** | **实测**：印面（篆书）直 OCR **不可用**（4 样本 3 个 `max_score=0.0`）；**边款 / 整页影像可用**（0.9989，41 框）；`ocr_text()` 的读取缺陷**已由 Kong 最小修复**；现状 `text` 非空 **2/79**（核验时点 2026-09-20 10:38）。证据＝`f2_report.json` → `3_ocr_feasibility` | ① 继续 OCR 路线（须加**分数阈值 + 去重**，Kong 侧）；② 改人工 / 半人工编目；③ 先解决 **§9.3 `seal_type` 章节映射**（无映射 ⇒ 必填项仍缺） | AC-08 必备项覆盖；平台侧汇入可否开正式包 |**（v1.3 状态）仍待裁**——1b-i/1b-ii **未推进释文路线**（无新证据）；**缺什么**：① OCR 路线的**分数阈值 + 去重**实测数据；② 人工 / 半人工编目的工作量口径；③ §9.3 #9 书简码签发（**归平台侧 M2**）与 `seal_name` 的先后关系。**v1.3 未改本项任何取值** |
| **R9** | **平台规范 §9.1 现状段落已与磁盘漂移，是否登记更正** | **漂移对照（双向时点）**：平台 §9.1（**其自记核验时点 2026-09-20，v1.24**）＝`stamps` **65 行** / 3 个 `pdf_name` 分别 **30/23/12** / `text` 非空 **0-65** / 影像缺失 **42-65**；**本文件磁盘实测（核验时点 2026-09-20 10:38）**＝**79 行** / **30/23/26** / `text` 非空 **2-79** / 影像缺失 **0-79**。**成因**＝Kong 侧 F2 恢复 + 增量重跑（`f2_report.json`：`2_image_recovery.copied=42 / still_missing=0`、`4_additive_rerun.rows_added=14`（页 7–8）、`5_selfcheck_before_after.rows 65 → 79`）**（v1.1 收口：平台规范已于 **v1.25** 按 §0.4 流程**原位更正 §9.1 三条读数**（快照 `docs/versions/yinsuo-web.spec.v1.24.md` → 升版本 → §0.5 + 表头两处同步 → 页脚同步），**故 R9 选项 ① 已执行完毕、本文件 §3.3 引用点无需改动，R9 事项收口**）** | ① 由 Jing 按平台规范 **§0.4** 流程登记更正（**先快照 `docs/versions/` → 升版本号 → 写 §0.5 变更记录 → 不动任何历史行**）；② 保持现状、只在平台侧 §0.7/§9.1 挂差异化登记 | 平台规范 §9.1 / §9.6「存量」行 / §0.6 证据行的**事实准确性**；**不影响**任何 AC 判据实质（AC-57 等不受影响） |
| **R10** | **边款影像的交付口径**（`REPORT_1b-i.md` §6 **G-2**） | **事实**：1b-i 的边款检测**照样做**（其结果参与 `exclude_mask`、影响释文块匹配），但**不落边款影像**（§4.1 D-4② 只定义印面交付影像 `faces/<book_key>/p####_i##.<ext>`）；旧 `output/<书名>/*_边款.webp` 属 Streamlit 路径、未动。平台侧 §9.2 有 `kind=EDGE` 的挂点，但**落地形态无规范** | ① 不入 `faces/`（保持 D-4② 现状）；② 入 `faces/` 并定命名；③ 入独立目录 `faces_edges/` | §4.1 D-4② / §4.2 命名规则 / §3.12 的 `assets[].kind` 取值面；**不阻断任何现有 AC** |
| **R11** | **影像 `sha256` / `bytes` / 宽高 的落库位置 + `stamps.id` 自增语义**（`REPORT_1b-i.md` §6 **G-6**） | **事实**：1b-i/1b-ii **只写** `stamps` + `job_pages` + `jobs`；影像 `sha256` 由 worker 回传、**只记在日志与自测证据里，未入表**；`images` / `seals` 侧表**未写**；`stamps.id` 的自增语义（是否可作跨轮稳定锚）未定 | ① 落到 `images` 侧表（沿用 F1 结构）；② 加列到 `stamps`；③ 另立 `job_images` 表 | §4.1 D-4① 的后续；**AC-09（`dedupe_key` 复算）** 与 AC-12 的证据面 |
| **R12** | **G-e：同区间重解析的行数 ≠ 库内行数（**待定性**）** | **观测（未定性）**：`tmp.pdf` 页 13–14 **库内 12 行 → 重解析 13 行**（`inserted=1 skipped=12`）；页 13–19 **库内 30 行 → 1b-i 首跑解析 31 行**。**反向证据现状**：**旧行零改写成立**（`skipped=12` 原样未动、AC-01 的「旧行不得被改写」面成立），但「**行数不变**」**不成立**；两种解释（**检测非确定性** vs **旧解析少一行**）**均未做实验判定** | **待定性**——**Zang 已另派质检任务定性**。**缺什么**：① 对同一页区间的**重复解析 N 次**的 idx 集合差分（判是否确定性）；② 对差异行（`inserted=1` 的那条）的**页/idx/bbox/影像复现性**取证；③ 旧行产出时的解析版本号与参数留痕 | §7 **AC-01** 的判据口径（**本版已按「键集合与内容不变」改写**）、§2.4 幂等语义 |
| **R13** | **换栈阈值与内存预算上限**（原 **R3** 的阈值部分） | §4.4 的 4 条触发条件（2 万影像 / 50 GB / 20 万行 / 2 写者 / 5 min 备份窗口）与 §5.3 的「worker 池 RSS 上限 ≈ 8 GB」**仍是 Jing 草案、无既有出处**；**v1.3 未改其数值**（仅因默认 worker 数改为 4，把**按 worker 数换算的池 RSS** 原位更正为 ≈ 3.3 GB，**8 GB 仍作宽松天花板保留**） | ① 采纳；② 改数值（给值）；③ 不设阈值 | 数据层演进路线、是否引入对象存储 / PostgreSQL |
| **R14** | **多 job 并行调度**（`REPORT_1b-i.md` §5-7 未做） | **实测**：池按 **FIFO 一次跑一个 job**（用满全部 worker）；§5.3 的上限口径是「同时跑的 job 数 ≤ worker 数」⇒ 取 **1 ≤ 4 合规**，但**不是最大化调度** | ① 维持 FIFO 单 job（当前）；② 允许多 job 并行（需定「每 job 的 worker 分配」与抢占规则） | 吞吐；§5.3 / AC-04 的解释面 |
| **R15** | **`jobs.state=PAUSED` 未实现** | **事实**：池不会主动暂停；`PAUSED` **仅在活跃 / 终态判定里被承认**（§2.1 表下注 G-4 的 `ACTIVE` 集合含它），**无实现路径**（`REPORT_1b-i.md` §5-6） | ① 保留为「口径承认、实现待定」；② 明确不实现（从 `ACTIVE` 集合移除，须同步 §2.1 表下注） | §2.2 状态机、§2.1 `ACTIVE` 集合 |
| **R16** | **AC-12 的 `N ∈ {0, 100, 1000}` 斜率实验未做** | **事实**：1b-i/1b-ii **遵守**影像外置（不写 BLOB）但**未做**该实验（`REPORT_1b-i.md` §5-4 / §4）。**不阻断**：AC-12 的三个子项**仍可机械复算**（§7 AC-12），只是**尚无留档证据** | ① 补做三档实验并留档；② 以 §4.1 D-4① 的「无 BLOB 列」子项 + 现库小规模读数替代 | AC-12 的通过判定（**证据未留档即视为未通过**，§7 用法） |
| **R17** | **平台规范 §9.3 ↔ §3.8 对 `sourceBook` / `sourcePageNo` 的必填性不一致（**报冲突、不自行改平台口径**）** | **实测（读平台规范原文）**：**§9.3** 把 `source_book` / `source_page_no` 列为**必填**（必填 11 项含第 7 / 8 行）；**§3.8** 的 `Seal` 字段表把 `sourceBook` / `sourcePageNo` 标为 **否（非必填）** ⇒ **同一文件内部必填性冲突**。feicui 侧**按 §9.3 执行**（§3.12 键路径已冻结、`missing_required` 含该两项） | **转平台侧按 §0.4 裁定**（① 按 §9.3 收紧 `Seal` 字段表；② 按 §3.8 放宽 §9.3。**Jing 不改平台规范一字**） | feicui 侧 `missing_required` 的取值面、AC-08 的判负面；**平台规范 §12 AC-57 判据实质不受影响** |
| **R18**（**v1.6 新增**｜来自 F-4 / §3.14.6） | **是否在 `config/templates.json` 补一个 `default` 项** | **事实（只读引用，Jing 未复跑）**：`config/templates.json` **顶层只有三本书名键**（`黄牧甫印谱_(西泠印社)_…pdf` / `秦汉印典 上海书画 金怀英  1997 ok.pdf` / `古玺汇编 文物出版社 罗福颐  ok.pdf`），**没有 `default` 键**；而形状契约（`min_area_eff` 不传 ⇒ 用模板默认项）**默认它存在** ⇒ 任何实现都只能走**内建兜底常量**（`square.py::BUILTIN_TEMPLATE_PARAMS`，**与三本书逐字一致：`verified 3/3`**）。**md5 `20acf9162baf0a0c4e5d6e164681b5ce` 未动**（本单**没有**偷塞 `default` 键） | ① **在 `templates.json` 里显式加 `default` 项**（＝三本书现行值），让「真源」名副其实（**标签将回到 `templates.json:default`**）；② **明确「无 `default` 时以内建常量为准」并 REQUIRE 响应如实标注常量位置与核验结果**（**当前实况、本单已按 ② 实现**） | **拟：维持 ② 现状并把「无 `default` ⇒ 内建常量 + 如实标注」写成本文件的**正式口径**（§3.14.6 已落位）；**是否补 `default` 项须由 Zang / Kevin 明示**（补它属**修改 `feicui/config/**`** ⇒ **须另派实现单，本版不动作**） | `params_used.template_source` / `min_area_source` 的字面取值、契约的「默认项」语义；**缺**：对「模板文件是否应承载默认项」的产品决策 |
| **R19**（**v1.6 新增**｜来自 P-3 同轮要求） | **`server/README.md` 内多处示例路径仍写 `/Users/kevin/bistro/shu/feicui/...`，登记待订正** | **事实（实测，本轮）**：`grep -c 'bistro/shu' feicui/server/README.md` ＝ **7**（命中行例：**第 3 行**「本目录 ＝ `/Users/kevin/bistro/shu/feicui/server/**`」、**第 156 / 168 / 178 / 198 行**的 `cd /Users/kevin/bistro/shu/feicui/server` 等；**核验时点 2026-09-20 19:2x**，证据＝`grep -n 'bistro/shu'`）。**工程实际在 `/Users/kevin/bistro/xiai/feicui`**（2026-09-20 14:47 工程改名）⇒ **照抄这些命令会失败** | ① 由 Kong 按「**现行有效引用 → `xiai/...`，逐处留痕**」的口径**原位订正**（历史叙述行保留原文 + 留痕）；② 或明确「README 的历史段落**冻结不改**」并把**现行命令段**单独抽到「现行路径」小节（**读者只需看那一节**） | **拟：采纳 ①**（**与 PORTS.md v1.12 / 本文件 v1.4 / 玺爱 v1.1 的路径收口口径一致**）——**但本版不动作**：**README 属实现侧文档（`feicui/server/**`），Jing 不改**；**本项只在规范里登记为待订正**（**缺口编号沿用 Kong 证据里的 G-4**） | 读者可跑性（照抄会失败）、`server/README.md` 的 §9 / §11.3 命令段；**缺**：订正时点与是否同时抽「现行路径」小节的决策 |
| **R20**（**v1.6 新增**｜来自 §5.5.1 口径分歧登记） | **冷启动「绝对基线」在 `server/README.md` §12.6 与 `ops` 证据里口径不一，是否统一** | **事实（只读引用，Jing 未复跑）**：`README.md` §12.6 写 **1.429 s → 0.242 s（−83%）**；`ops/kong_square_crop_evidence.md` §3.4 的**绝对基线**为 **2.964 s → 0.242 s**、**相对 A/B** 为 **1.724 s → 0.260 s**。**三处出自同一批实测的不同轮次**（页缓存冷热，G-3） | ① 把 `README.md` §12.6 的表述**订正为「两个口径同时给」**（**并按 §5.5.1 的统一口径**）；② 保留现状（**因为 §5.5.1 已把口径钉住，README 只是叙述**），只在本规范登记分歧 | **拟：采纳 ①**（**但须走实现侧文档订正 ⇒ 与 R19 同批**）；**本版只登记**（**§5.5.1 已给正式测量口径，故本项不阻塞任何判据**） | `server/README.md` §12.6 的事实准确性；**不影响**任何 AC 判据实质（**§7 AC 里没有「冷启动耗时」类判据**） |

| **R21** | **印人采集是否同库 `yinpu.db`** | §3.15.4 已定 ＝ **独立 SQLite `feicui/var/person_ingest.db`**、**`yinpu.db` 一字不碰**；**依据** ＝ `yinpu.db` 有「只能加法 + 红线判据」历史包袱，且印人采集与印谱解析无数据依赖（拆解件 §8 W-P1） | ① 维持独立库（**现状、本版已按此落**）；② 若 Kevin 要求同库 ⇒ 改为**加法式新表**（另开单） | §3.15.4 的库落点；**缺**：Kevin 一句话确认 |
| **R22** | **关联面是否递归**到印章详情 / 印谱详情（`seal/detail`、`graph/seal`） | §3.15.6 已定 ＝ **只落 `graph/person` 的直接关联**（印谱 / 印章）；`seal/detail` / `graph/seal` **本轮范围外、仅登记**（拆解件 §2.1 / §8 W-P2） | ① 维持只落直接关联（**现状**）；② 递归面批 2 后另议 | §3.15.6 的采集深度；**缺**：是否递归 + 递归深度**。**（v1.11 状态注｜Kevin 2026-10-10 裁定）**：**本轮关联面整体不导入 xiai（只落印人本体，见 §3.15.12）⇒ 本项「是否递归」不作本轮议题**；**状态 ＝ 挂起（随「关联作为独立需求另开」时重新登记并再议）**；**保号留行、不删除**。 |
| **R23** | **采集触发形态**（手动按钮 / 定时任务） | §3.15.3 / §3.15.7 拟 ＝ **手动按钮触发 `POST /api/persons/sync`**（拆解件 §8 W-P3；**Zang 默认**） | ① 手动按钮（**现状**）；② 定时任务 | §3.15.2 采集区交互；**缺**：Kevin 裁定 |
| **R24** | **印章影像（`image_key`）是否下载** | §3.15.6 拟 ＝ **只存键、不下载影像**（拆解件 §8 W-P4；**Zang 默认**）；`image` 形如 `NN_<id>_1` | ① 只存键（**现状**）；② 下载影像（须定命名 / 存储 / 体量口径） | §3.15.6 的产物面；**缺**：Kevin 裁定**。**（v1.11 状态注｜Kevin 2026-10-10 裁定）**：**印章影像（`image_key`）属关联面子问题**；**本轮关联面整体不导入 xiai ⇒ 同随「关联作为独立需求另开」时再议**；**状态 ＝ 挂起**；**保号留行、不删除**。 |
| **R25**（**v1.12 新增**｜来自 §3.16.4 / 拆解件 §8 WI-1） | **印谱（item）采集的独立库文件名** | §3.16.4 已定 ＝ **独立 SQLite `feicui/var/item_ingest.db`**（表 `items` / `item_creators` / `item_import_batches`）、**与 `var/person_ingest.db` 分库**、**`yinpu.db` 一字不碰**；**依据** ＝ `yinpu.db` 有「只能加法 + 红线判据」历史包袱，且印谱采集与印谱解析无数据依赖（拆解件 §8 WI-1） | ① 维持独立库（**现状、本版已按此落**）；② 改文件名 / 与 person 合库（另开单） | §3.16.4 的库落点；**缺**：Kevin 一句话确认 |
| **R26**（**v1.12 新增**｜来自 §3.16.7 / 拆解件 §8 WI-2） | **影像（`hasImage=1` 共 1714 本）是否下载** | §3.16.7 拟 ＝ **只落标记（`has_image` 布尔）、不下载影像**（拆解件 §8 WI-2；**Zang 默认**） | ① 只落标记（**现状**）；② 下载影像（须定命名 / 存储 / 体量口径） | §3.16.5 就绪包 / 采集产物面；**缺**：Kevin 裁定 |
| **R27**（**v1.12 新增**｜来自 §3.16.7 / 拆解件 §8 WI-3） | **`itemList`（卷册条目）/ `titleList` 是否落库** | §3.16.7 拟 ＝ **本轮只落 `raw_json`、不单列结构化表**（拆解件 §8 WI-3；**Zang 默认**） | ① 只落 `raw_json`（**现状**）；② 单列结构化表（须定表结构 / 粒度） | §3.16.4 存储面 / §3.16.5 就绪包字段面；**缺**：Kevin 裁定 |
| **R28**（**v1.12 新增**｜来自 §3.16.2 / 拆解件 §8 WI-4） | **第三页签文案** | §3.16.2 拟 ＝ **【印谱采集】**（拆解件 §8 WI-4；**Zang 默认**；**已由 §7 AC-23（v1.12 原位改写）机械承载**） | ① 【印谱采集】（**现状**）；② 改文案（须同步 §3.16.2 与 §7 AC-23） | §3.16.2 页签文案 / §7 AC-23；**缺**：Kevin 一句话确认或改写 |
| **R29**（**v1.15 新增**｜来自 §3.17.4） | **印章（seal）采集的独立库文件名** | §3.17.4 已定 ＝ **独立 SQLite `feicui/var/seal_ingest.db`**（表 `seals` / `seal_links` / `seal_import_batches` / `seal_images`）、**与 `var/person_ingest.db` / `var/item_ingest.db` 分库**、**`yinpu.db` 一字不碰**；**依据** ＝ `yinpu.db` 有「只能加法 + 红线判据」历史包袱，且印章采集与印谱解析无数据依赖 | ① 维持独立库（**现状、本版已按此落**）；② 改文件名 / 与 person / item 合库（另开单） | §3.17.4 的库落点；**缺**：Kevin 一句话确认 |
| **R30**（**v1.15 新增**｜来自 §3.17.8） | **影像是否给 xiai 直接消费的形态** | §3.17.8 已定 ＝ **影像全部直供 xiai 影像库（TIFF）**（印面 / 印体释文 / 边款 ≈ 6765 张；**JPEG → TIFF 无损容器转换**；**入包镜像 xiai 形态** `images/<sha256[:2]>/<sha256>.tiff`、**包内不放 JPEG**），落 `exports/seal_import_<batch_id>/images/` ＋ `images_manifest.jsonl`（唯一索引，含 `sha256` / `bytes` / 尺寸 / `conversion`） | ① 镜像 xiai 影像库形态随包直供（**现状、Kevin 2026-10-10 裁定：TIFF 直供**）；② 改其他分发 / 存储形态（须定命名 / 存储 / 体量口径） | §3.17.5 就绪包 / §3.17.8 影像面；**状态 ＝ 已裁（Kevin 2026-10-10：TIFF 直供）**；**保号留行** |
| **R31**（**v1.15 新增**｜来自 §3.17.1 裁定 A） | **`audit_status` 未审核行（`2=716` / `9=31` / `0=3`）在 xiai 侧的去留** | §3.17.1 裁定 A ＝ **范围全量 3679、保留 `audit_status` 字段与分布统计**；**但未审核 / 非「已发布」行（`audit_status ∈ {2, 9, 0}` 共 750 枚）在 xiai 侧是否落库 / 是否过滤未定** | ① 全量入包、去留由 xiai 侧定（**现状**）；② 按 `audit_status` 预裁（仅「已发布」子集 716 枚入包） | §3.17.1 裁定 A / §3.17.5 就绪包；**缺**：Kevin 裁定 |
| **R32**（**v1.15 新增**｜来自 §3.17.6③） | **`seal/detail` 默认关的开关态** | §3.17.6③ 拟 ＝ **`seal/detail` 默认关**（**形製标签已可本地码表派生 ⇒ 不再跑 3679 次 detail**）、降 best-effort（**仅补 `sealYzRefId` / `auditUser`**）；**Zang 默认 · 一句话可改** | ① 默认关 best-effort（**现状**）；② 默认开（逐枚 detail） | §3.17.6③ 采集口径 / §3.17.5 manifest `detail_policy`；**缺**：Kevin 一句话确认或改写 |
| **R33**（**v1.16 新增**｜来自 §3.17.8 a-v1.16；**v1.17 子因随动**） | **源侧缺图（`source_no_image`）在 xiai 侧的去留** | §3.17.8 已定 ＝ **源侧缺图独立分桶（`source_no_image`），非 feicui 采集失败、不得静默丢弃**（子因 **① `NaN_` 开头 ref**；**② 持久 `HTTP 500`**；**③ 坏字节 `bad_bytes`（v1.17 随动新增，与 §3.17.8 a-v1.16 块子因二扩三同步）**）；**但这些 ref 在 xiai 侧是「留空白行」还是「不落行」未定** | ① **留空白行**（占位、标 `source_no_image`，保持 `seals.jsonl` 行数 ＝ 3679）；② **不落行**（xiai 侧只见有图项） | §3.17.5 就绪包 / §3.17.8 影像面；**缺**：Kevin 裁定 |
| **R34**（**v1.18 新增**｜来自 §3.17.8） | **6 张超 xiai store 4 MiB 上限影像在 xiai 侧的去留** | §3.17.8 已定 ＝ **本包保留原生裁切与「RGB 8-bit ＋ Deflate」家法格式、不自行降采样 / 不自行转码**；**包内 `bytes > 4 MiB`（`STORED_MAX_BYTES`）的影像 6 张**（`seqid 3353 / 3366 / 3367 / 3464 / 3506 / 3510`，均 `kind=yt`、~1500×1500、4.37–4.96 MB）**超过 xiai `store.validate_payload` 的 4 MiB 写入上限** ⇒ **逐行标记 `oversize_for_xiai_store` ＋ 计数 ＋ 清单（落 AC-54）；去留未定** | ① **xiai 侧放宽 `STORED_MAX_BYTES`**（须 xiai 线按其 §0.4 流程改 `codec.STORED_MAX_BYTES`；影响面 ＝ 存储 / 传输 / 展示口径）；② **落库但标超档、不做缩图**（store 侧对超档行特批 / 跳过 4 MiB 校验之一面，须 xiai 侧定）；③ **由 xiai 侧另降采样**（本包不降；xiai 侧入库时另生成合规缩图、原图留档）；④ **本包剔除这 6 条**（feicui 侧删行，xiai 侧不见） | §3.17.5 就绪包 / §3.17.8 影像面 / §7 AC-54；**归 xiai 线裁（Kevin / xiai 规范）**；**缺**：Kevin 裁定 |
| **R35**（**v1.20 新增**｜来自 §3.18.2 / §3.18.5） | **关系集合名 / 关系模型（落 xiai 的哪一集合、是否新立集合）** | §3.18.2 已定 ＝ **统一「关系边」（edge）候选键面**（`predicate` 五值枚举 ＋ `subject_*` / `object_*` / `role` / `evidence` / `source_ref` / `image_ref` / `name`(`_chs`) / `seq` / `batch_id`）；**但「落 xiai 的哪一集合 / 是否新立关系集合 / 是否合并进既有 person·item·seal 集合的关联字段」未定**（**归 xiai 线**，同 §3.16.1 I-3 / §3.17.9 a 口径） | ① **新立独立关系集合**（如 `relations`）；② **并入既有集合的关联字段**（`person` / `item` / `seal` 各持关联位）；③ **其他模型**（xiai 线给形态） | §3.18.2 键面 / §3.18.5 就绪包主交付；**归 xiai 线裁（Kevin / xiai 规范）**；**缺**：Kevin / xiai 裁定 |
| **R36**（**v1.20 新增**｜来自 §3.18.2 / §3.18.3） | **键面裁剪（`key_face_status: "pending_xiai"`）＋ 幂等键是否改用合成 hash** | §3.18.5 已定 ＝ **候选键面未裁前不裁剪**，`manifest.json` 给**字段字典**并标 **`key_face_status: "pending_xiai"`**；**对方定键面后二次出包、无需重新联网**（本库已存全字段）。§3.18.3 已定 ＝ **幂等键 ＝ `(predicate, subject_id, object_id)`**（**是否改用合成 hash 未定**） | ① **按现行候选键面原样入库**（xiai 侧收全字段）；② **裁剪至 xiai 封闭键面**（feicui 二次出包、不重新联网）；**幂等键**：① 维持三元组；② 改用合成 hash（须给算法） | §3.18.2 键面 / §3.18.3 幂等键 / §3.18.5 manifest；**归 xiai 线裁（Kevin / xiai 规范）**；**缺**：xiai 侧键面与导入 op 契约 |
| **R37**（**v1.20 新增**｜来自 §3.18.7） | **导入通道（是否沿用三线既有「三段式提交 / 审核」通道）** | §3.18.7 已定 ＝ **feicui 只出候选关系包、不写 xiai 任何文件、不调云函数**；**提交与审核不在 feicui 侧**（沿 §3.15.1 表下注 v1.8 / §3.16.8 a / §3.17.9 a）；**关系面的导入通道（是否走与 person 同型的 `PENDING` → 管理员采纳三段式、是否另立通道）未定** | ① **沿用三线三段式提交 / 审核通道**（与 person 导入一致）；② **另立关系导入通道**（须 xiai 线定）；③ **暂不导入**（只出包留 feicui 侧） | §3.18.7 红线 / §3.18.5 就绪包；**归 xiai 线裁（Kevin / xiai 规范）**；**缺**：xiai 侧导入 op 与审核门口径 |
| **R38**（**v1.20 新增**｜来自 §3.18.1 / §3.18.4 R-c） | **幽灵行（`as_book_id='test'` 1 条）与 14 个未收录印人 id 的去留** | §3.18.4 R-c 默认 ＝ **保留并标记**（`as_book_id='test'` **1** 条标 `ghost:true`；**14** 个未收录印人 id **保留原值**、另给 `person_resolved:false`）；**实测来源** ＝ `person_relations(印谱).as_book_id` 唯一 932 ⇒ 未命中 1（值 ＝ `test`，源侧测试占位行）；`seal_links(person_*).ref_id` 41 个 id ⇒ 未命中 14（**同 §3.17.8 a-v1.19 ① 口径**） | ① **保留并标记**（默认；xiai 侧按标记处理）；② **剔除**（feicui 侧删行、xiai 侧不见）；③ **保留但不标记**（不推荐：违反 §3.18.4 R-c 可追溯口径） | §3.18.1 对账 / §3.18.4 R-c / §3.18.5 report.json 未命中清单 / §7 AC-58；**归 xiai 线裁**；**缺**：Kevin 裁定 |
| **R39**（**v1.20 新增**｜来自 §3.18.4 R-b） | **双源去重形态（合一行 ＋ `evidence` 数组 vs 拆成两行保留各自原字段）** | §3.18.4 R-b 默认 ＝ **同一 `(subject,object,predicate)` 只一行、`evidence` 数组保留双源**（去重后 **1249** 条标 `["person_graph","book_graph"]`；**原始 12054 ⇒ 去重后按 R-a · R-b 重算**） | ① **合一行 ＋ `evidence` 数组**（默认；**双源共报同一事实时 provenance 折进数组**）；② **拆成两行、保留各自原字段**（`creator_role` / `creator_relator` 等各源原字段不丢，**但同一事实重复两行**） | §3.18.4 R-b / §3.18.5 就绪包行数 / §7 AC-55 · AC-56（去重算术与逐类计数随形态变）；**归 xiai 线裁**；**缺**：Kevin 裁定 |
| **R40**（**v1.21 新增**｜来自 §3.19.2；**v1.22 结案**） | **单文件上传上限是否合适**（原问「**512 MiB** 是否合适」） | **已结（Kevin 2026-10-11 裁定：上传单文件上限默认 5 GiB ＝ 5368709120 B）**。**【v1.22 结案依据（逐字）】** ① **本单输入**：Kevin 拖入 `~/Downloads/秦印类编 检索版.pdf` 被现上限拒（**`413 PAYLOAD_TOO_LARGE`**、`declared_bytes 2,019,683,630`、「**未落盘即拒**」），他问「这个 PDF 体积上限是多少？可以再大吗？比如 5G 以内」；② **实测（核验时点 2026-10-11）**：`秦印类编 检索版.pdf` **1.88 GiB / 2,019,683,630 B / 851 页**、`福庵印缀 原版 高清.pdf` **1.14 GiB / 1,224,531,421 B / 236 页**（体积与页数由 Jing 只读复核）；③ **本机 `df` 余量 191 GiB**（`/dev/disk3s1s1 460Gi 10Gi 191Gi`），容得下 5 GiB 上限；④ **下游代价**：按 **8.67 s/页** ⇒ **851 页单核 ≈2.0 h / `w=4` ≈0.8 h**（≈ §5.1 实测 `w=4` ≈2.72× 折算）。**原 v1.21 依据（源 PDF 实测 38 MB、历史最大 372 MB、按 512 MiB ≈1.4× 默认落）原文逐字留存于快照 `docs/versions/feicui.spec.v1.21.md` §9。** | ① 维持 512 MiB（**已被本次裁定取代**）；② **改为 5 GiB（5368709120 B）**（**Kevin 2026-10-11 采纳 / 现状默认**）；③ 按书自动（小书小限、大书大限）（**未采纳**） | §3.19.2 上限（**v1.22 已同步**）/ §3.4 `413` 行 / **AC-65 的判据面**（**v1.22 已同步措辞、判据逻辑未改**）/ §3.19.7 待裁行。**本次仅数值与文字同步，未新增 / 未改写任何判据。** |
| **R41**（**v1.21 新增**｜来自 §3.19.3） | **`inbox/` 清理策略（谁清、何时清）** | §3.19.3 已定 ＝ 落点 **`feicui/inbox/<yyyymmdd>/<原文件名>.pdf`**、**同名同内容复用**；**但「谁清、何时清、保留多久、是否按日期回收」未定**——**核验时点 2026-10-10：`inbox/` 目录磁盘上尚不存在**（本端点落地时由实现创建） | ① **不自动清**（人工清；风险 ＝ 盘满）；② **按日期保留 N 天**（须定 N 与触发点：启动时 / 每次上传时）；③ **按体积水位回收**（须定水位与回收顺序）；④ **由 job 终态触发回收**（须定「job 结束后是否删源 PDF」——**与 E1 的可重跑语义耦合**，须谨慎） | §3.19.3 落点 / 盘容量 / **E1 的同书重跑与 `pdf_path` 有效性**（删源 PDF 会使 `pdf_path` 失效 ⇒ 与 §2.4 / AC-01 的语义耦合）；**缺**：Kevin 裁定；**（v1.22 复核：仍挂起** —— Kevin 2026-10-11 未就此裁定；**上限已升 5 GiB ⇒ 盘占用压力更需对策，本项仍未裁**） |
**（v1.6 更新｜留痕）**：**新增待裁项 R18 ～ R20（共 3 条）⇒ 本表现共 20 条（R1 ～ R20）**。**R18 属「口径二选一」**（是否补 `default` 项）、**R19 / R20 属「实现侧文档待订正」**（`server/README.md` 历史路径 / 冷启动表述）——**后两条均不阻塞任何 AC 判据**（**§7 AC 计数仍 13 条**）。**未裁定前不得据本表执行实现**（沿用本节口径）。
**（v1.7 更新｜留痕）**：**新增待裁项 R21 〜 R24（共 4 条）⇒ 本表现共 24 条（R1 〜 R24）**；**新增来源 ＝ §3.15（印人采集）**（底稿 ＝ 拆解件 §8 的 W-P1 〜 W-P4）；**上句「本表现共 20 条（R1 〜 R20）」系 v1.6 时点读数，原文逐字保留 + 就地留痕**。**R21 已按 §3.15.4 落为「独立库」（Zang 默认 · 一句话可改）**；**R22 / R23 / R24 均为 Zang 默认、待 Kevin 一句话确认或改写**。**未裁定前不得据本表执行实现**。

**（v1.8 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 24 条（R1 〜 R24）**（**R 计数不变**；v1.7 时点读数「R1 〜 R24」沿用、**无变化**）。**来源** ＝ Kevin 2026-10-10 追加裁定「批 2（写入 xiai 的通道）由另一会话承接」（**§3.15.1 表下注 v1.8 追加**）——**该裁定属已决的范围划定，非待裁项，故不设新 R 行**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.9 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 24 条（R1 〜 R24）**（**R 计数不变**；v1.8 时点读数「R1 〜 R24」沿用、**无变化**）。**来源** ＝ Kevin 2026-10-10 新口径「页签【任务页】→【印谱解析】＋ tabbar 下移 / 顶部固定页眉标题区」（**§3.15.2 v1.9 注**）——**该口径属已决的改名与布局登记，非待裁项，故不设新 R 行**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.10 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 24 条（R1 〜 R24）**（**R 计数不变**；v1.9 时点读数「R1 〜 R24」沿用、**无变化**）。**来源** ＝ Kevin 2026-10-10 三答之②③与「xiai 就绪导入包」交付缝扩展（**§3.15.11**）——**其中两条外部依赖（`D-1`：xiai 侧需扩 3 键；`D-2`：xiai 侧提交需可验证令牌）系跨工程登记、归 xiai 侧按其自己的规范流程处理，属已决的边界划定，非本文件待裁项，故不设新 R 行**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.11 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 24 条（R1 〜 R24）**（**R 计数不变**；v1.10 时点读数「R1 〜 R24」沿用、**无变化**）。**来源 ＝ Kevin 2026-10-10 关联面裁定「本轮先只落印人本体」（§3.15.12）**——**该裁定属已决的范围划定（故不设新 R 行）**；**其中与「是否导入关联」相关的关联面子问题（`R22`：关联是否递归 / `R24`：印章影像是否下载）逐条处置为「挂起（随『关联作为独立需求另开』时重新登记并再议）」**（**状态列已就地另注；保号留行、不删行**）；**其余 R 行（R1 〜 R21 / R23）不受本裁定影响、维持原状态（仍待裁）**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.12 更新｜留痕）**：**新增待裁项 R25 〜 R28（共 4 条）⇒ 本表现共 28 条（R1 〜 R28）**；**新增来源 ＝ §3.16（印谱（item）采集）**（底稿 ＝ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §8 的 WI-1 〜 WI-4）；**上句「本表现共 24 条（R1 〜 R24）」系 v1.11 时点读数，原文逐字保留 + 就地留痕**。**R25 已按 §3.16.4 落为「独立库 `var/item_ingest.db`（与 person 分库）」（Zang 默认 · 一句话可改）**；**R26 / R27 / R28 均为 Zang 默认、待 Kevin 一句话确认或改写**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.13 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 28 条（R1 〜 R28）**（**R 计数不变**；v1.12 时点读数「R1 〜 R28」沿用、**无变化**）。**来源 ＝ §3.16.6 v1.13 采集口径偏离（关联主源改 `graph/book` ＋ `book/detail` 降 best-effort）**——**其中 `book/detail` best-effort 开关态（`detail_policy` 默认 `off`）与「关联主源取 `graph/book`」系 Zang 默认（一句话可改），属已决的口径登记、非待裁项，故不设新 R 行**；**R25 〜 R28 状态不变（仍待 Kevin 一句话确认或改写）**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.14 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 28 条（R1 〜 R28）**（**R 计数不变**；v1.13 时点读数「R1 〜 R28」沿用、**无变化**）。**来源 ＝ §3.16.3 Q5（v1.14 追加 `POST /api/items/package`）＋ §3.16.5（v1.14 重建幂等口径）**——**二者系对既有实现（additive 端点）的契约登记与已决口径，属登记、非待裁项，故不设新 R 行**；**R25 〜 R28 状态不变（仍待 Kevin 一句话确认或改写）**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.15 更新｜留痕）**：**新增待裁项 R29 〜 R32（共 4 条）⇒ 本表现共 32 条（R1 〜 R32）**；**新增来源 ＝ §3.17（印章（seal）采集）**；**上句「本表仍共 28 条（R1 〜 R28）」（v1.14 时点读数）原文逐字保留 + 就地留痕**。**R29 已按 §3.17.4 落为「独立库 `var/seal_ingest.db`（与 person / item 分库）」（Zang 默认 · 一句话可改）**；**R30 / R31 / R32 均为 Zang 默认、待 Kevin 一句话确认或改写**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.16 更新｜留痕）**：**新增待裁项 R33（共 1 条）⇒ 本表现共 33 条（R1 〜 R33）**；**新增来源 ＝ §3.17.8 a-v1.16（源侧缺图三态分桶）**；**上句「本表现共 32 条（R1 〜 R32）」（v1.15 时点读数）原文逐字保留 + 就地留痕**。**R33（源侧缺图在 xiai 侧的去留：留空白行 vs 不落行）为 Zang 默认、待 Kevin 裁定**；**R29 〜 R32 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.17 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 33 条（R1 〜 R33）**（**R 计数不变**；v1.16 时点读数「R1 〜 R33」沿用、**无变化**）。**来源 ＝ §3.17.8 a-v1.16 块之子因由二扩三（新增子因（c）坏字节 `bad_bytes`）**——**该新子因已属既有 `source_no_image` 分桶，其「在 xiai 侧留空白行 vs 不落行」的去留问题与子因无关、恰为本 R33 所问**（**§3.17.8 三子因同属 `source_no_image`、R33 不作子因区分**）⇒ **逐字理由：「`bad_bytes` 已在 §3.17.8 a-v1.16 块的 `source_no_image` 子因行随动追加（子因二扩三），其 xiai 侧去留与 `NaN_` / `HTTP 500` 两子因同归 R33 的「源侧缺图在 xiai 侧的去留（留空白行 vs 不落行）」一问，R33 覆盖面不因子因细分而改变，故 **不新增 R 行**」**。**R33 行已就地加「v1.17 子因随动」注（子因三扩为「① `NaN_` / ② 持久 `HTTP 500` / ③ 坏字节 `bad_bytes`」）**；**R33 状态不变（仍待 Kevin 裁定）；R29 〜 R32 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.18 更新｜留痕）**：**新增待裁项 R34（共 1 条）⇒ 本表现共 34 条（R1 〜 R34）**；**新增来源 ＝ §3.17.8 a-v1.18（超 4 MiB 桶）**；**上句「本表仍共 33 条（R1 〜 R33）」（v1.17 时点读数）原文逐字保留 + 就地留痕**。**R34（6 张超 xiai store 4 MiB 上限影像在 xiai 侧的去留：① xiai 放宽 `STORED_MAX_BYTES` / ② 落库标超档不做缩图 / ③ xiai 侧另降采样 / ④ 本包剔除这 6 条）为 Zang 默认、待 Kevin / xiai 线裁定**；**R29 〜 R33 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.19 更新｜留痕）**：**本版未新增任何待裁项 ⇒ 本表仍共 34 条（R1 〜 R34）**（**R 计数不变**；v1.18 时点读数「R1 〜 R34」沿用、**无变化**）。**来源 ＝ (a) 源侧 `ref_id` 未命中 person 库（印主 8/438、篆者 1/403、边款篆者 6/11）＋ (b) 三线响应顶层 `_db_path` 对照**。**(a) 源侧 `ref_id` 未命中 person 库**——**属源侧引用未收录（源侧事实），非 feicui 采集缺陷 ⇒ 不判负**；**其记账口径（`seal_links` 允许 `ref_id` 不命中 person 库、但须在 `report.json` 给计数）已落 §3.17.8 a-v1.19 ①，属已定口径登记、非待裁项，故不设新 R 行**。**(b) 端点响应顶层内部键 `_db_path`**——**三线对照实测 `GET /api/seals` / `/api/persons` / `/api/items` 的响应顶层键完全相同（均为 `['items','page','limit','total','has_more','_facets','_db_path']`）⇒ 系三条采集线共有的既有惯例、非印章线不一致**；**原拟的待裁项 R35（「是否从响应中删去内部路径键」）已撤回**——**逐字理由：「三线实测响应顶层键同为 `['items','page','limit','total','has_more','_facets','_db_path']`，`_db_path` 系三条采集线共有的既有惯例、非印章线的本线不一致；既非不一致、亦非本线可判负 / 待裁目标，故不立待裁项，R35 撤回，R 计数回退到 34」**；**改登记为观察项（落 §3.17.8 a-v1.19 ②，不判负、不立 R）**。**R29 〜 R34 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.20 更新｜留痕）**：**新增待裁项 R35 〜 R39（共 5 条）⇒ 本表现共 39 条（R1 〜 R39）**；**新增来源 ＝ §3.18（关联面（三表联立））**（底稿 ＝ 拆解件 `feicui/docs/relation-ingest-draft-v0.1.md` §3 的默认口径 R-a 〜 R-f ＋ §5 边界）；**上句「本表仍共 34 条（R1 〜 R34）」（v1.19 时点读数）原文逐字保留 + 就地留痕**。**新增分布（v1.20）** ＝ **关系集合名 / 模型 1**（R35，**归 xiai 线裁**）＋ **键面裁剪（`pending_xiai`）＋ 幂等键是否改用合成 hash 1**（R36，**归 xiai 线裁**）＋ **导入通道（是否沿用三段式提交 / 审核）1**（R37，**归 xiai 线裁**）＋ **幽灵行（`as_book_id='test'` 1 条）与 14 个未收录印人 id 的去留 1**（R38）＋ **双源去重形态（合一行 ＋ `evidence` 数组 vs 拆两行保各自原字段）1**（R39）。**五条逐项写明后果（影响面列）**；**均归 xiai 线裁**（Kevin / xiai 规范）。**R29 〜 R34 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.21 更新｜留痕）**：**新增待裁项 R40 〜 R41（共 2 条）⇒ 本表现共 41 条（R1 〜 R41）**；**新增来源 ＝ §3.19（E8 拖曳上传端点）**；**上句「新增待裁项 R35 〜 R39（共 5 条）⇒ 本表现共 39 条（R1 〜 R39）」（v1.20 时点读数）原文逐字保留 + 就地留痕**。**新增分布（v1.21）** ＝ **上传上限 512 MiB 是否合适 1**（R40）＋ **`inbox/` 清理策略（谁清、何时清）1**（R41）。**两条逐项写明后果（影响面列）**；**均待 Kevin / Zang 裁定**（**R40 改默认值须同步 AC-65 措辞；R41 与 E1 的同书重跑 / `pdf_path` 有效性语义耦合**）。**R29 〜 R39 状态不变**。**未裁定前不得据本表执行实现**（沿用本节口径）。

**（v1.22 更新｜留痕）**：**§9 R40 已结（保号留行不删行）；R41 仍挂起；本版未新增待裁项 ⇒ 本表仍共 41 条（R1 〜 R41）**（**R 计数不变**；v1.21 时点读数「R1 〜 R41」沿用）。**R40 结案**（Kevin 2026-10-11 裁定：上传单文件上限默认 5 GiB ＝ 5368709120 B；详见 R40 行）；**R41（`inbox/` 清理策略：谁清、何时清）v1.22 复核仍挂起**。**逐字理由（未新立 R42「大文件重传无断点续传」）**：「**本版未新增 R 行**——**断点续传 / 分片 / 批量拖入**已在本文件 **§3.19.7** 明写「**将来若需…须走 §0.4 另立需求（本版不做）**」，属**已决的范围划定**（**明确置于现范围之外、并给了再议路径**），**非「未裁的口径缺口」**；若再立 R42 会与 §3.19.7 的既有处置**重复登记**、并把**已明确置于范围外**的项无据拉回待裁表；**5 GiB 上限带来的大文件重传代价与 `inbox/` 盘占用压力，已由 R41（清理策略）承载其盘侧后果**，故 **不新立 R42，R 计数保持 41**」。**本次仅数值与文字同步，未新增 / 未改写任何判据。**

---

## 10. 变更记录

| 日期 | 版本 | 变更 | 变更人 |
| --- | --- | --- | --- |
| 2026-09-20 | **v1.0** | **建立 feicui 侧独立规范（只写文档，未动 `feicui/**` 任何 `.py` / 数据文件、未动 `shu/web/**`、未动平台规范）**：① **§1 目标形态**——Streamlit UI 退役 → **FastAPI 薄接口层 + 独立 Vue 前端 + 任务队列 / worker 池**，进程分离（计算与 UI 各自生死），并列 **4 条硬不变量**（依据＝Kevin 拍板方向 C + Zang 裁定「UI 框架不在热路径」）；② **§2 任务模型**——**一本书 = 一个 job**、job 内按页 chunk 并行、**页级断点游标**、**同书重跑幂等**（行级 `(pdf_name,page,idx)` + 影像 `sha256`）；③ **§3 API 契约草案**（E1 建 job / E2 查进度 / E3 分页取结果 / E4 触发导出 / E5 缺失清单）＋ **6 条语义纪律**，并与平台规范 **§9.3 必填 11 项 / §9.4 幂等键与 DPI 归一化前置 / §9.6 通道**对齐（**只引用，不动平台规范一字**）；④ **§4 数据层演进**——SQLite 保留 + **WAL** + **索引 `(pdf_name,page)`** + **批量事务**（替换现状**每页一次 connect/commit/close**，证据 `processor.py` 行 432/440/441）＋ 影像外置目录规则 ＋ **对象存储 / PostgreSQL 的四条换栈边界（草案，待裁定）**；⑤ **§5 并发与资源**——worker 数口径（**10 物理核实测**、默认 8 待裁定）、**OCR 由全局单例（`processor.py` 行 20–23）改为每 worker 一实例**（单实例实测 **init 1.8 s / 常驻 0.70 GB / 峰值 0.81 GB**）、单 job 并发上限 1、内存预算；⑥ **§6 端口与登记口径**——前端 **5195**、API **5196**（**实测空闲证据**：`lsof` 无监听 + `nc -z` CLOSED，核验时点 2026-09-20 10:38），`index.js` `services` **五要素对应**（sid / 端口 / 启动命令 / cwd / env + group `shu` + directUrl）与**落地顺序纪律**；⑦ **§7 验收判据 AC-01～AC-13**（**逐条可机械判负**，覆盖同书重跑幂等、断点续跑不重复、**并行与串行含 bbox 逐条一致**、进度真实、影像/释文缺失清单可查、必备 11 项、幂等键复算、批量事务、进程分离、影像外置、端口纪律）；⑧ **§8 现状时点纪律**（自带时点戳与证据来源；**派单转述与磁盘冲突以磁盘为准**）；⑨ **§9 待裁清单 R1–R9**（5164 `/feicui` 代理、8501 实例处置、§4.4 阈值、worker 数、group 归属、入 `services` 表时点、前端工程目录缺口、释文路线、平台规范 §9.1 漂移更正）；⑩ **§0.3 磁盘事实基线**（核验时点 **2026-09-20 10:38–10:45**，含 `stamps` **79 行 / 10 列**、3 个 `pdf_name` **30/23/26**、`text` 非空 **2/79**、影像缺失 **0/79**、`journal_mode=delete`、`stamps` 无索引、机器 **10 核 / 16 GB / 169 GB 可用**、**8501 被占**）。**同时**在 `ctrl/PORTS.md` 追加 feicui 登记行（§2 表 + §5 变更记录），**未重写任何历史行**。 | Jing |
| 2026-09-20 | **v1.1** | **按 §0.4 变更流程修 Neng 复检 7 项缺陷（D-1～D-7）+ 三项登记（本版只改文档，未动 `feicui/**` 任何代码 / 数据、未动 `shu/web/**`、未动平台规范历史行、未 kill / 停 / 重启任何进程）**：**(1) D-1｜分页信封（中）**——采「**扩展自平台 §3.1 信封**」口径（**理由：平台 §3.1 约束的是平台适配层方法 A13/A21/A24/A25，而 E3 是 feicui 内部端点；E3 取的是随 worker 推进而增长的页级顺序结果集，游标分页比页码分页稳定**），**逐项列出差异**：`limit` ↔ 平台 `pageSize`（同义不同名）、**`has_more` / `next_cursor` 为 feicui 侧游标分页新增**、`items` / `total` / `page` 与平台同义；**S-3 的判负形态绑到该 6 字段明确定义形态**（含 `has_more` / `next_cursor` 互斥一致性校验），**删去「与平台一致取向」的表述**（§3.1 E3 行 + 表下注 / §3.2 S-3）。**(2) D-2｜5196 登记口径互斥（中）**——§6.1 的 5196 单元格改为「**本文件与 `PORTS.md` v1.8 同轮新分配**（原表无 5196、非占用、非保留；登记行见 PORTS.md §2）」，**与同文件 §6.3 口径拉齐**（§0.1「以 PORTS.md 为准并当场修本文件」）。**(3) D-3｜AC-12 不可复算（低-中）**——改为**三个独立子项**：**① `PRAGMA table_info` 无 `BLOB`**（拆为独立子项）；**② 斜率式可复算**——影像数 `N ∈ {0,100,1000}` 三档各测 `du -k yinpu.db`，**斜率 < 1 KB/影像**判通过（等价式：`PRAGMA page_count × page_size` 增量 < 影像总字节 × 1%）；**③ `img_path` 相对路径**（抽样 ≥10 条）。**(4) D-4｜AC-11 不可定判（低）**——钉为**二值判定**「**worker 进程仍存活（`kill -0` 退出码 0）且 cursor 单调推进（≥5 s 两次采样）**」，删除「或按策略落为可续跑状态」（其能力由 AC-03 判定），并给出**可复算命令**。**(5) D-5｜自由变量钉值（低）**——AC-03 的 X 钉为 **X ∈ {25, 50}**（各至少一次）；AC-04 的 N 钉为 **`N=4`**，**依据 2026-09-20 实测**（阶段 0b：`w=1/2/4/8` ＝ 1.00× / 1.82× / 2.72× / 3.20×，**`w=4` 到顶、`w=8` 无收益**，来源 `feicui/spike-ocr/REPORT.md` + `results.json`）。**(6) D-7｜§9-R6/R7 证据句不可复跑（低）**——**删去「无 `docs/`」**，只保留「**无 `web/`**」并注明 **`feicui/docs/` 由本规范自身于 2026-09-20 10:40 建立**，同时给出复跑命令（`ls -d /Users/kevin/bistro/shu/feicui/web`）。**(7) 三项登记**——**① 8501 收口（R2）**：该孤儿实例已于 **2026-09-20 10:57:50** 由 **Kong 按 Kevin 授权**以**进程组 `TERM`** 停止（1 秒内释放、未用 `KILL`、零邻接误伤；证据 `feicui/ops/8501_stop_evidence.md` + `ops/8501_stop_before_after.txt`）；**v1.1 复核 8501 无监听**——已在 **§9-R2 / §1.4 / §0.3 端口现况行**原位更正并留痕（**Jing 本人始终未停任何进程**）；**② 5164 `/feicui` dev 代理（R1）**：**Kevin 已拍板＝要**，**落地时点＝feicui 前端骨架起来那一刻**（目标现不存在、本轮不落地），实现＝Vite `server.proxy`、**不落 SPA 路由**（**平台 §2.2 路由表仍 14 条、AC-88 / AC-89 扫描面不变**），**生产须在网关同构改写**，属 **M1 冻结面之外的基础设施登记、不得当作功能变更**——口径集中登记于**新增 §6.4**，§9-R1 同步收口；**③ 性能基线口径（新增 §5.4）**：单页现状 **8.668 s**（render 0.1587 / detect 0.0317 / **ocr 8.4777**）、关 doc 预处理 + `w=4`/`ct=2` 后 **2.481 s（3.49×）**、900 万页现状单核 **902.9 天** / 最优配置 **258.5 天**——**逐项标「实测 / 推断」，来源 `feicui/spike-ocr/REPORT.md` + `results.json`（Jing 未复跑，只读引用）**。**(8) 版本与流程留痕**——**§0.4 流程逐条执行**：改版**前**先快照 `feicui/docs/versions/feicui.spec.v1.0.md`（md5 `f2934cb0899953e00483c51a333da08c`，`cmp` 字节一致）→ 升版本 **v1.0 → v1.1** → 本行（**v1.0 行原文保留不改**）→ 同步受影响小节（§0.3 / §1.4 / §3.1 / §3.2 / §5.4 / §6.1 / §6.4 / §7 / §9）。**统计**：**AC 计数仍 13 条**（未增减；仅改写 AC-11 / AC-12、为 AC-03 / AC-04 钉值）；待裁项 **R3 / R4 / R5 / R8 仍待裁**，**R1 / R2 / R9 本轮收口**（R6 / R7 待工程落地）。**另**：平台规范同步升 **v1.26**（同轮，按平台 §0.4 流程：快照 `docs/versions/yinsuo-web.spec.v1.25.md` → §0.5 + 表头两处新增 v1.26 行 → 页脚横幅同步，**历史行零改动**）。 | Jing |
| 2026-09-20 | **v1.2** | **按 §0.4 变更流程一次性收口阶段 1a 暴露的全部规范缺口与登记项（本轮只写文档：本文件 + 平台规范 v1.27 + `ctrl/PORTS.md` v1.10，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未 kill / 停 / 重启任何进程、未占端口）**：**(1) 新增取图端点正式契约与编号 E6（前端 G-1）**——`GET /api/jobs/{job_id}/stamps/{page}/{idx}/image`（**必须带页段**：行级唯一锚是 `(pdf_name,page,idx)`，`idx` 单值在 job 内不唯一）；200＝影像字节（`Content-Type` 取文件实际类型、`Content-Length` 必填、**不包 JSON 信封**、可选 `x-feicui-img-path`）、404＝三类同码（job 不存在 / 记录不存在 / 文件不在盘上）、400＝参数非法、500＝读盘解码异常；**只读**（不得触发解析 / OCR / 写库）、**不得占位冒充**（无图 ⇒ 404）、**不得读 BLOB**；**临时路径的收口规则**＝废止前端的 `/stamps/{idx}/image`（2 段形态）、后端**不实现不兼容**（返 404 即可）、前端**一处常量**（`src/api/stampsImage.js`）收敛、收口证据＝结果页对「有图 / 无图」两种记录的可见性判据。落位 **§3.1 表（E6 行）+ 新增 §3.5**。**(2) 后端 8 条缺口 G-1～G-8 全部入账**——**新增 §3.4**（错误响应体形状：**409 冻结为** `{error:"ACTIVE_JOB_EXISTS", job_id, state, total_pages, created_at}`、**`job_id` 必填且为既有活跃 job**；400 / 404 / 422 / 500 冻结为**须含 `detail`**、**允许**额外字段（`error` / `missing`）、**多出字段不判负**；**明文规定 S-3 的字段封闭纪律不外推到错误体**，否则实现无法既带 `job_id` 又不「多出字段」）；**§3.1 表下注**（G-5 `total_pages` 派生顺序＝`page_range` 宽度 → 读 PDF 页数 → 否则 422，且读页数须用 worker 侧解释器子进程；G-6 **非 PDF 判定改以 `%PDF-` magic 为准**，不得只按扩展名——实测 PyMuPDF 会按扩展名把 `.txt` 当 1 页文档；**1a 未做、1b 补**）；**新增 §3.6**（G-8：**允许**非契约端点，限于 `/api/health` 与 `/api/meta/**` 只读，且不得被 AC 依赖；现状 `GET /api/health` / `GET /api/meta/migrations` 判定＝**合规、保留**）；**§4.1 D-2**（G-7：唯一约束**落地形态＝唯一索引** `uq_stamps_pdf_page_idx`，与「只许加法」相容，**严禁重建 `stamps`**，建前须实测重复组为 0）；**§2.1 表下注**（G-4：`job_id` 是**审计锚**不是游标容器——活跃 job ⇒ 一律 409（不看 `rerun`）、终态可再入队得**新 job_id**、**不得复用 / 重置旧 job 的页游标**）。**(3) 前端 5 条缺口全部入账**——G-1＝**新 §3.5**；G-2＝**E7**（新增 `GET /api/jobs`，E3 同款 6 字段信封，归属 1b；落地前前端按「后端尚未提供 + localStorage 本地记录分栏」过渡，**该现状不得作为验收依据**）落位 **§3.1（E7 行）+ 新增 §3.8**；G-3＝**§3.4**；G-4＝**§3.6**（`/api/health` **允许后端提供，但前端不得据其为契约或验收依据**，连通性仍走 dev 探针并容忍 404）；G-5＝**新增 §3.7**（**端点未实现＝404**；`404`/`405`/`501` 三码宽容**仅属前端处理、非规范口径**；**不得**用 200 + 空 items 冒充）；**前端附注**＝**新增 §3.9**（Vite dev 代理的 `503 {error:"backend_unreachable"}` **不属 API 错误码族**；「后端不可达」信号**定义为 dev / 前端侧**口径，探针 `GET /__feicui/backend-probe` 与代理 503 **必须同源**，二者均不属后端契约）。**(4) 登记项 R-1 按 §0.4 收口为正式口径**——§6.2 **启动命令原位更正**为 `cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python -m app.main`（等价 `uvicorn app.main:app`；host / port 不变）、**cwd 更正为 `feicui/server`**、**前端 cwd 由「计划路径」改为已建立**（birth 2026-09-20 11:35:25）；**新增 §6.5 解释器矩阵**（接口层＝`server/.venv/bin/python`、**3 个直接依赖 / freeze 13 行（实测 13）**；worker 与 Streamlit＝`feicui/venv`；E1 派生 `total_pages` 走 worker 侧解释器子进程；**硬约束：不得把新依赖装进 `feicui/venv`、不得升降级其中任何包**；`server/.venv` 重建命令与 13 行实测）。**(5) Neng 复核观察的入账**——**OBS-1**：**AC-11 的「判负形态」列原位等义替换为取反式**（worker 未存活 **或** cursor 未单调推进 ⇒ FAIL；判据实质**一字未改**）并留痕；**OBS-2**：**§9-R6 / R7 的「`feicui/web` 不存在」作废**（目录已存在、birth 2026-09-20 11:35:25；R6 事项仍为「入 `services` 表未落地」，但**不得再以目录不存在为由**）；**OBS-3**＝快照纪律，落位 **`ctrl/PORTS.md` v1.10 制度 (e)**；**OBS-4** 标注类，无需动作。**(6) 1c 代理口径按 Zang 原文照录入 §6.4**（`feicui/web` `base:'/feicui/'` + `server.hmr.clientPort:5195`；`shu/web` `server.proxy` / `preview.proxy` 各加 `'/feicui'` → `http://127.0.0.1:5195`、`changeOrigin:true`、**不 rewrite 前缀**；**不新增 SPA 路由** ⇒ 平台 §2.2 仍 14 条、AC-88 / AC-89 扫描面不变；**生产须网关同构改写**；**四项验收判据**），**原文一字未改**；**并附实测**（核验时点 2026-09-20 12:00–12:01：两处 `vite.config.js` 均已含该键、`5195/feicui/` ⇒ **200**、`localhost:5164/feicui/` ⇒ **200**；`check:pricing` / `smoke` / `build` **由 Kong / Neng 执行，Jing 未复跑**）；**落地状态句一律写作「已定、落地中（由 Kong 执行）」并自带时点戳**。**(7) §0.3 两条现状读数按磁盘实测原位更正**——**5195 现已被占用**（`node` PID 1329，`127.0.0.1:5195 LISTEN`；原记「空闲」被取代）、**`shu/web` 的 `/feicui` 代理已落地**（4 处 `proxy` 命中；原记「零命中」被取代）。**(8) 平台侧连带**：`shu/docs/yinsuo-web.spec.md` 升 **v1.27**（B4 v1.27 注 + §1.7 表下 v1.27 注 + §0.5 v1.27 行 + 表头两处 + 页脚横幅；**§12 AC-01～AC-90 判据一字未改、AC 计数仍 90 条、§2.2 路由表仍 14 条**）。**统计与自查**：**AC 计数仍 13 条**（只改写 AC-07 / AC-11 表述，未增减）；**未动** `feicui/**` 任何代码 / 数据、`shu/web/**`、`shu/mockups/**`、`ctrl/index.js`；**未 kill / 停 / 重启任何进程、未占端口**；**历史行（表头「版本」字段的 v1.0 / v1.1 叙述、§10 的 v1.0 / v1.1 行）逐字保留、只增不改**（版本字段以**前置** v1.2 条的方式同步，v1.1 原文完整保留）。 | Jing |
| 2026-09-20 | **v1.3** | **按 §0.4 流程一次性收口阶段 1b-i + 1b-ii 交回的全部规范缺口与 Zang 已裁定口径（本版只写文档：本文件 + 平台规范 v1.28 + `ctrl/PORTS.md` v1.11，三处均先存快照；未动任何 `.py` / `.vue` / `.js` / `.json`、未动 `shu/web/**`、未启停任何服务、未占端口）**：**(1) E7 定案（Zang 口径 1 / 6 + 1b-ii G-a ～ G-d）**——§3.1 E7 行入参改写为 `?state=&page=&limit=&cursor=`，**`page` 与 `cursor` 互斥（同给 ⇒ `400 BAD_PARAM`）**、`page` 1-based 且**越末页返空 `items` + `has_more=false`（绝不回吐第一页）**；**新增 §3.10**：`limit` **默认 50 / 上限 500 / 越界或非法 ⇒ 400**、`total` ＝该 `state` 范围全量、**`has_more == (next_cursor is not None)` 恒成立**、**排序键 `ORDER BY created_at, job_id`**（实测 4 个 job 的 `created_at` 同秒 ⇒ 只按 `created_at` 会重叠 / 遗漏）、**游标 URL-safe base64**（`created_at` 含 `+` / `:` 直接进 query 会被解码成空格 ⇒ 第二页恒空），`items[]` **冻结 9 字段**（原「形状草案」表述作废），并**核过平台规范 §9 与 §3.8**（job 是 feicui 内部实体、平台无对应实体 ⇒ **不构成冲突**，核不上的项＝无）。**(2) 红线判据纪律（Zang 口径 2）**——**新增 §8 第 6 条**：凡「数据未变」类现状读数与红线判据**一律用内容指纹（列数 + 行数 + 三口径指纹 / 可复算 SQL），禁用数据库文件 md5**（依据：WAL 下 `yinpu.db` **文件** md5 在内容无变化时漂移 `254d3ff1…` → `56cbf7af…`，mtime 12:42:13，而同刻 `stamps` 三口径指纹逐字节未变）；**同源纪律同步写入平台规范 v1.28 与 `PORTS.md` v1.11**。**(3) AC-03 点位定义钉定（Zang 口径 3）**——**以 `done_pages / total_pages` 为唯一定义**（**不采用**「连续已提交前缀」口径）、**`{25%, 50%}` 两点各至少一次**、**允许 ±1 页容差但证据须写明实际百分比**（实测两口径不同：42.9% / 57.1% vs 28.6%）。**(4) worker 数口径对齐（Zang 口径 4）**——**§5.1 草案「默认 8」原位更正为 4**（与 AC-04 已钉 `N=4` 一致；依据阶段 0b 实测 `w=4` 到顶 / `w=8` 无收益 / swap 近耗尽），**§5.3 的「全局 job 并发上限＝worker 数（默认 8）」与「池 RSS ≈ 6.5 GB（8 × 0.81）」同步原位更正**并留痕，**§9-R4 收口**。**(5) 池的进程形态定案（Zang 口径 5）**——**§1.3 表新增「池管理器 `feicui-pool`」行**：**独立常驻进程、无端口、非接口层子进程**；**池管理器用 `server/.venv`、worker 用 `feicui/venv`**；**接口层不含业务真值** ⇒ 这是 **AC-11 的形态依据**（1b-i 自测 ⑤ 已用 SIGKILL 5196 反证）；**§6.2 表下 v1.3 注**登记「池不进 `services` 表」与落地实况。**(6) E6 错误码定案（Zang 口径 9）**——**§3.5 表下 v1.3 块**：越界 / 不可得均 **404** 但**原因码分三类**（`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`）、**`img_path` 超出 `FEICUI_ROOT` 或为绝对路径 ⇒ `IMAGE_UNAVAILABLE`**、**无法判定影像类型 ⇒ `500 IMAGE_TYPE_UNKNOWN`**（**不得**以 `application/octet-stream` 冒充）；§3.1 E6 行同步。**(7) E4 请求语义定案（Zang 口径 8）**——**新增 §3.11**：`batch_id` 非空 ⇒ 400（批次号由 `export.py` 派生、不臆造）、`dry_run=true` ⇒ 400（`export.py` 无该模式、不假装跑过）、`book_code` 仅作与 `config/book_codes.json` 的一致性校验、`counts` 三键映射登记为 `feicuiDecidable` 的 `formal` / `draftStaged` / `rejectedRequiredMissing`、`selfcheck_ref` **存在则给路径否则 `null`**（**`export.py` 的 export 子命令本身不产生 selfcheck，生成者是 `selfcheck_export.py`** ⇒ `null` 是正常态）。**(8) E3 records 形状与 AC-08 键路径冻结（Zang 口径 10）**——**新增 §3.12**：顶层平台字段名 + `assets[]` + `feicui` 子对象 + 顶层 `missing_required[]`；11 项必填逐项键路径表（`assets[].sha256` / `assets[].width` / `assets[].height` / `assets[].colorMode` / `assets[].batchId` 等）；**`missing_required` 用 feicui 语义名（snake_case）**、记录内用平台字段名（camelCase）——**两套命名的映射表即 §3.12**；**AC-08 判负改绑键路径**。**(9) `limit` 默认 / 上限与信封恒等式（Zang 口径 11）**——并入 **§3.10**。**(10) 响应头纪律（Zang 口径 7）**——**新增 §3.13**：`x-feicui-scope` 等含**非 ASCII 书名**时**必须百分号编码**（头值须 latin-1 可编码），并给出**4 条可机械判负的判据**（Latin-1 可编码 / 原始非 ASCII 计数须为 0 / `unquote` 后与 DB 字面逐字节相等 / 头不进 JSON 体）；依据＝原写法对中国书名**已真实发生 500**。**(11) G-e 待定性（Zang 口径 12）**——**§2.4 表下注 + §9-R12**：「同区间重解析行数 ≠ 库内行数」以**「待定性」**入账（写明观测值与**缺什么**：重复解析 N 次的 idx 差分 / 差异行的复现性取证 / 旧解析版本留痕；**Zang 已另派质检定性**）；**AC-01 幂等判据改写为「键集合与内容不变」，「行数不变」不再作判据**，并明确「**新键允许新增行**」。**(12) 1b-i §6 G-1 ～ G-9 逐条判定并入账**——**本轮已裁**：G-1（**AC-10 适用面＝新增解析链路**，`processor.py` 旧形态属 §1.4 退役边界、不单独判负）、G-3（worker＝4）、G-4（池＝独立进程）、G-5（**队列形态＝库即队列**——`jobs` + `job_pages` 即持久队列，不引入额外中间件）、G-7（**AC-11 的 cursor 读数来源＝库内 `count(distinct chunk_index) WHERE state='DONE'` 或 E2 的 `cursor.chunk_hi`，不新增 E2 字段**）、G-8（**`FEICUI_DOC_PREPROCESS` 默认 1，改默认须先补样本级精度验收**——实测「关 doc 预处理改文本」**是样本相关的**：页 20–21 为 1/8、页 63–64 为 0/10）、G-9（**`cpu_threads=2`**，§5.2 新行）；**仍待裁**：G-2（边款影像交付口径 ⇒ **R10**）、G-6（影像 `sha256` / 度量落库位置 + `stamps.id` 语义 ⇒ **R11**）。**(13) 新增 §7.1 验收夹具纪律**（F-1 ～ F-10：硬上界 / **夹具不得把被测方的自洽当终止条件** / 重复 FAIL 折叠计数 / 非信封即中止 / `finally` 精确 PID 清理 / 动态端口 / **断言总数闸门** / **版本身份钉** / 辅助函数不得假设调用点类型 / 恒真判据不得充当通过证据）——依据两起实测事故（**54,347 行 / 54,254 条重复 FAIL 的失控轮**；**「中途终止仍报 `FAIL=0`」的假绿形态**）。**(14) §6.2 按磁盘实测原位更正**——**sid 由 `feicui` 更正为 `feicui-web`**、**`directUrl` 更正为带 `/feicui/` 前缀的实际值**；**登记「面板托管已落地」**（核验时点 2026-09-20 13:08，`ctrl/index.js` 已含 `feicui-api` / `feicui-web` 两条），**§9-R6 收口**、**§9-R5 收口（实际 `group` ＝ `shu`）**；§0.3 端口现况行追加 v1.3 读数（**5195 / 5196 / 8501 均无监听**）。**(15) 平台侧报冲突一项**——**§9-R17**：平台规范 **§9.3** 把 `sourceBook` / `sourcePageNo` 标为**必填**，而 **§3.8** 的 `Seal` 字段表标为**非必填** ⇒ **平台规范内部必填性不一致**；feicui 侧**按 §9.3 执行**、**冲突转平台侧按 §0.4 裁定**（**Jing 不改平台规范一字**）。**(16) §9 待裁清单新增 R10 ～ R17**（边款影像 / 影像度量落库位置 / **G-e 待定性** / 换栈阈值与内存预算 / 多 job 并行调度 / `PAUSED` 未实现 / AC-12 斜率实验未做 / §9.3↔§3.8 冲突），**R8 维持待裁并补「仍缺什么」**。**AC 计数仍 13 条**（只改写 AC-01 / AC-03 / AC-08 / AC-10 的判据表述）；**被取代的原句一律就地留痕「已被 v1.3 取代」**。 | Jing |
| 2026-09-20 | **v1.4** | **工程改名（`shu` → `xiai`）路径口径收口 + P9 池托管裁定收口 + G-1b（E3 `idx` 锚点冻结）+ 两条已实测 def- 类事实登记（E6 头值编码 / E7 有效态过滤）+ 数据现状刷新**（**本轮只写文档：本文件 + 平台规范 v1.29 + `ctrl/PORTS.md` v1.12，三处均先存快照：`feicui/docs/versions/feicui.spec.v1.3.md`（md5 `8a27ecb692a7a611f056b280fd7e0de4`，649 行）、`docs/versions/yinsuo-web.spec.v1.28.md`（md5 `1660ca9d40afa76e6cca15b45172b282`，1634 行）、`ctrl/versions/PORTS.v1.11.md`（md5 `ac47ab3fe5d4df67fba82ecc011823dd`，183 行）；**未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `xiai/web/**`、未 kill / 停 / 重启任何进程、未占端口**）**：① **路径迁移登记（2026-09-20 14:47 工程改名；改名非 Jing 执行）**——整个 `shu` 工程改名为 `/Users/kevin/bistro/xiai/`（`~/bistro/shu/` 只剩空 `.vite` 壳、**零文件**；xiai 侧实测 **33,596** 个文件）；**本文件内所有 `/Users/kevin/bistro/shu/...` 起头的现行有效引用一律原位更正为 `xiai/...`**，逐处留痕；**可复跑判据**＝`ls -d /Users/kevin/bistro/shu/feicui/yinpu.db` ⇒ **`No such file or directory`**、`ls -d /Users/kevin/bistro/xiai/feicui/yinpu.db` ⇒ **命中**；**落位**＝表头「文档性质」（2 处）+ §6.2 表（4 处）+ §9-R6（4 处）+ §9-R7（3 处）= **9 处原位更正**，另「§6.2 表下 v1.3 注 ①」的 13:08 md5 锚定引文**按快照式引文保留原文 + 追加 v1.4 取代注**；**§0.3 新增 v1.4 注**（路径 + 判据 + 数据现状）。**改版前**本文件提及 `xiai` **0 处**、写 `/Users/kevin/bistro/shu` **17 处（8 行）**。② **面板服务条目实况同步（照磁盘实测）**——核验时点 **2026-09-20 14:59**，`ctrl/index.js`（md5 `143137f25c717596d4a8260db686794f`、52,651 B、mtime 14:49:58）`services` 表共 **12 条**，feicui 族 **3 条**：**`shu`**（sid 未改、`5164`、`cwd=/Users/kevin/bistro/xiai/web`、`directUrl=http://localhost:5164`）、**`feicui-api`**（`5196`、`./.venv/bin/python -m app.main`、`cwd=/Users/kevin/bistro/xiai/feicui/server`、**`FEICUI_DB=/Users/kevin/bistro/xiai/feicui/yinpu.db`**、无 `directUrl`）、**`feicui-web`**（`5195`、`npm run dev`、`cwd=/Users/kevin/bistro/xiai/feicui/web`、`directUrl=http://localhost:5195/feicui/`）；落位 **§6.2 表下 v1.4 注 ②**。**改动系 Kong 执行，Jing 未改 `ctrl/index.js` 一字**。③ **P9 裁定收口（Zang 已定案：采纳选项 ①）**——**池不入 `services` 表**；改为**由 API 提交 job 后异步、detached 拉起**（`app.pool --workers 4 --drain`，env 带 **`FEICUI_ALLOW_PROD_MIGRATE=1`**），**API 启动扫 `QUEUED`/`RUNNING` 补跑**；**已有池在跑 ⇒ 退出码 5 属正常分支（不得当故障）**；**理由**＝面板健康模型是端口可达性、无端口常驻服务入表会污染「N/N 全监听」判态；**依据**＝`server/app/poolctl.py` + `ops/1c/1c_double_start_evidence.txt`；落位 **§6.2 表下 v1.4 注 ③**（**对端＝`ctrl/PORTS.md` §4-P9 v1.12**）。④ **G-1b 入账（§3.12 补一行冻结）**——**冻结 `idx` 的规范键路径＝`feicui.stampIdx`**（行级、同一 `(pdf_name, page)` 内唯一），实现按真源 `export.py::build_record` 取、**以 `assets[].seq` 兜底**，**不得另立第三来源**；**备选「`items[]` 加顶层 `idx`」本轮不采纳**（登记备查）。**理由**＝E6 需要 `(page, idx)`，而 §3.12 此前**只冻结 `page`（顶层 `sourcePageNo`）**，`idx` 无明文冻结 ⇒ 同类「取不到锚点」缺陷会复发。⑤ **两条已实测 def- 类事实入账（只登记、不重跑）**——**(a) E6 头值编码（§3.13 v1.4 注）**：`x-feicui-img-path` 原实现直接回吐 DB 原值 ⇒ starlette 编码头值抛 `UnicodeEncodeError` ⇒ **E6 整条 500**（**含中文书名的书取图全挂**）；现统一 `_header_safe()`；**§3.13 的 4 条判据一字未改**。**(b) E7 有效态过滤（§3.10 v1.4 注）**：`?state=` 过滤**已按「有效态」定案**（与 `items[].state` **恒同出一处**，SQL 真源 `E7_EFFECTIVE_STATE_SQL`）；**依据**＝质检 `qa-recheck/p1bii-neng/` 的 E7 探针实测 FAIL + `OBS-1`。⑥ **数据现状读数（照磁盘实测，带时点）**——正式库 `stamps` 现 **89 行**（核验时点 **2026-09-20 14:59**）：**`id<=79` 的 79 行三口径指纹与 `ops/prod_migrate_evidence.md` §2.3 逐字未变**（`8a21e57d…` / `d7abe995…` / `22bdc0a7…`）；**`id 80–89` 共 10 行为 1c 阶段两轮真实解析新增**（`tmp.pdf` 1 + `秦汉印典 …ok.pdf` 9），**不属污染**；全表指纹 A `5fcbd5af…` / B `d3932fdc…` / C `401e520c…`；**`jobs` 5 行**（全 `DONE`）；落位 **§0.3 v1.4 注 ②**，并**原位更正 §4.4 锚点行数**（79 → 89，留痕）。⑦ **统计与自查**——**AC 计数仍 13 条**（**本轮未新增、未改写任何 AC 判据**）；待裁项 **R3 / R4 / R5 / R8 仍待裁**，**R6 / R7 维持 v1.3 的「已落地」结论**（**仅路径与判据刷新**）；**R1 / R2 / R9 / R17 状态未变**；**历史行（§10 的 v1.0 / v1.1 / v1.2 / v1.3 行、表头「版本」字段的 v1.0～v1.3 叙述、表头 v1.0～v1.3「本版硬约束」行）逐字保留、只增不改**；**被取代的原句一律就地留痕「已被 v1.4 取代」**。⑧ **跨文件连带（同轮，由 Jing 执行）**：平台规范 `xiai/docs/yinsuo-web.spec.md` 升 **v1.29**、`ctrl/PORTS.md` 升 **v1.12**——两处**均先存快照**、**历史行零改动**。 | Jing |
| 2026-09-20 | **v1.5** | **落 Kevin 2026-09-20 追加的两条口径（V-1 / V-2）并如实登记本轮已落地的实现读数**（**本版只写文档：本文件一处、先存快照；未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `xiai/web/**`、`xiai/src/**`、`ctrl/index.js`、`ctrl/public/**`、`xiai/docs/xiai-plan.md`、平台规范、`ctrl/PORTS.md`；未 kill / 停 / 重启任何进程、未占端口**）**：**① 新增 §0.5（产品展示与数据方向口径）**——**§0.5.1 V-2（方向性、最高优先）**：**数据结构以玺爱为主；斐萃此前的库结构并不完善，后者向前者靠**；**玺爱定义 canonical schema**，**斐萃是待改造的入库管线**，**玺爱是数据归宿**；斐萃既有表 **`stamps` / `seals` / `images` / `export_batches` / `export_records` / `jobs`** 的字段**仅作为「斐萃旧结构 → 玺爱 canonical」的入库映射来源**，**不得**反过来让玺爱迁就斐萃（映射表见玺爱侧规范 **§4.4**）；给出 **4 条判负形态**（① 以「旧库无此列」拒绝 / 推迟斐萃侧补列或补产出；② 把斐萃既有列集合当建模目标；③ 要求改 canonical 字段名 / 结构以迁就旧列；④ 反向要求玺爱改名 / 改结构）。**留痕（防失真，必须原文保留）**：**改版前本文件不存在任何「数据模型对齐斐萃」类表述、亦无任何数据方向条款**（核验时点 **2026-09-20 15:55**，证据＝`grep -n '对齐斐萃\|以斐萃\|数据模型\|canonical\|玺爱' feicui/docs/feicui.spec.md` **零命中**）⇒ **本条属「新增条款」，不是既有条款被改写 / 反转**；被取代的同类表述只存在于**玺爱侧规范**（其 §3.5 / §4，**已由该文件 v1.1 取代**）。**§0.5.2 V-1（可判负）**：产品展示名＝**【斐萃】**（界面 / `document.title` / 页面标题 / 品牌位**不得再出现 `feicui` 作为展示名**；路径与工程标识如 `/feicui/` base、目录名、包名、sid、env **不算展示名**）；配色＝**蓝绿色的宝石感**；**色值一律走 CSS 变量 token**（token 源＝`feicui/web/src/styles/base.css` 的 `:root`）**、不得在组件里散落色值**、**承担信息传递的图形元素对相邻背景非文本对比 ≥ 3:1**、**槽位专用 token 不得跨用途复用**。**② 新增 §0.6（本轮实现事实登记，只读实测 + 时点戳）**——**已落地**：`feicui/web/index.html` **第 6 行**＝`<title>斐萃｜印谱解析任务台</title>`（**原值**`feicui ｜ 印谱解析任务台` **引自实现侧口径、Jing 未复核历史值**）；`feicui/web/src/styles/base.css` 的 `--bg: #0a1a1d`（**第 6 行**，深青墨底） / `--accent: #2fd6a0`（**第 17 行**，翡翠青绿主色） / `--accent-line: #43e6bd`（**第 19 行**）；`feicui/web/src/components/BackendBanner.vue` **第 28 行**启动提示＝`cd /Users/kevin/bistro/xiai/feicui/server && ./.venv/bin/python -m app.main`（**原值**`cd /Users/kevin/bistro/shu/feicui` 与 `./venv/bin/uvicorn app:app` **同上标注**）；`npm run build` 在本轮报告里已绿（**引实现侧报告，Jing 未复跑**）。**未落地 / 待裁**：「副标题去掉外露端口号（`5195` / `5196`）」系 **Zang 裁定、非 Kevin 原话**，登记为「**已定、落地情形待核**」（**不得写成 Kevin 已拍**）。**未复核项 3 条**如实标注（三条历史原值 / build 绿灯 / `--on-accent` 注释自记「对 `--accent` 9.70」的对比度读数）。**③ §1.2 新增不变量 I-5（数据方向不得反向）**，判负面指向 §0.5.1。**④ 流程（本文件 §0.4）**：**改版前先存快照** `/Users/kevin/bistro/xiai/feicui/docs/versions/feicui.spec.v1.4.md`（md5 `9b246d25206c1a2353a056876733b088`、**675 行 / 177,059 B**，`cmp` 与改版前主文件**字节一致**）→ **升版本 v1.4 → v1.5** → **表头「版本」字段补 v1.5 条（原 v1.0 ～ v1.4 叙述逐字保留）** + **表头新增「本版硬约束（v1.5）」行** + **本表新增本行**（**三处版本记录同步、历史行只增不改**）。**AC 计数仍 13 条**（本版不改任何 AC 判据、不新增 AC）；**不写任何「本轮已通过」类结论**——凡涉实现侧状态一律写「**已落地（读数 + 时点 + 证据）**」或「**已定、落地中（由 Kong 执行）/（由 Neng 验收）**」。 | Jing |
| 2026-09-20 | **v1.6** | **按 §0.4 流程落「斐萃收尾四件事（F-1 〜 F-5）」**（**只写文档：本文件一处、先存快照；未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件；未动 `xiai/src/**`、`xiai/web/**`、`xiai/feicui/ops/**`（只读引用）、`ctrl/index.js`、`ctrl/public/**`、`xiai/docs/xiai-plan.md`、平台规范；未 kill / 停 / 重启任何进程、未占端口**）——**① 新增 §3.14（工具端点 `POST /api/tools/square-crop`（5196）完整契约）**（依据＝**F-1**）：**定位**＝**与 job 体系完全无关的纯函数式工具端点**；**§3.14.1 请求**＝`multipart/form-data` 硬要求、**文件字段名逐字 `image`**（否则 `400 NO_IMAGE`）、请求体上限 **`32 MiB`**（`400 UPLOAD_TOO_LARGE`，**不落临时文件**）、四个可选文本字段（`pad_ratio` 默认 `0.15` / `min_area_eff` 默认不传 / `quality` 默认 `95` / `max_side` 默认 `0`）、越界 ⇒ `400 BAD_PARAM`；**并写明「本端点的 `32 MiB` 与玺爱侧「文件 ≤ 1 MB」是两个不同的口，不得互相引用、不得同值复用」**。**§3.14.2 响应字段集**＝信封 `{ok,count,source,candidates[],params_used,degraded}` ＋ **候选 12 项封闭字段**（`idx`/`bbox`/`square`/`side`/`width`/`height`/`mime`/`sha256`/`image_base64`/`area`/`aspect`/`degraded`＋`degraded_reasons`）＋ 逐字段语义冻结（排序键＝面积降序、`square` 恒正方、`mime` 恒 `image/webp` 且 RIFF magic 自证、`min_area_eff` 是 **worker 侧真实生效值**）。**§3.14.3 错误码**＝**`400`（`BAD_CONTENT_TYPE`/`UPLOAD_TOO_LARGE`/`BAD_MULTIPART`/`NO_IMAGE`/`BAD_PARAM`/`DECODE_FAILED`）＋ `422 NO_CANDIDATE`（须附 `source`/`params_used`）＋ `500`（`RUNNER_*`/`INTERNAL`）**，**一律 `{ok:false,error,reason,detail}` 结构化 JSON、绝不返回 HTML 错误页**。**§3.14.4 CORS**＝**白名单唯一真源 ＝ `Settings.cors_origins`**（默认含 **5195 两项 + 5163**）、**不放开 `*`**、白名单外不回 ACAO、**预检与实 POST 同回**；**判负形态含「代码里另写一份 origin 列表」**。**§3.14.5 红线**＝**零 DB 写（无 SQL / 不读 `stamps`）· 不建 job（`jobs`/`job_pages` 一个字不碰）· 不落盘（不碰 `exports/`/`output/`、不建临时文件）· 不复制检测算法（走 `processor.detect_stamp_regions`，方形化只有一份实现）**；**⇒ `stamps` 行集指纹调用前后逐字节不变**（引 T8 读数）。**§3.14.8 证据索引**＝T1/T2/T3/T8/T9 ＋ **证据引用纪律**（**自记 PASS 只引用不背书**、**证据不落 `/tmp`**）。**② 新增 §3.14.6 来源标签口径（F-4）**——**红线：`min_area_source` 绝不引用不存在的键**；`template_source` / `min_area_source` **同源派生、不可能互相矛盾**；**当前实况＝ `config/templates.json` 顶层无 `default` 键** ⇒ **以内建常量为准并如实标注三件事**（内建兜底常量 / **常量在源码的确切位置** / **与语料逐字核验结果**），冻结形状 **`builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)`**（并给 `corpus-DIVERGENT` / `no-template-file` / `template-unreadable` 三种退化形态）；**登记历史缺陷**（改前硬编码 `templates.json:default` 而该键不存在）**与「只改标签、算法与数值零改动」的自证读数**（`min_area_eff` 均为 `6172.839506172839`、`sha256` 均为 `b540bf97…`、`side/width/height` 均为 341）。**③ 新增 §3.14.7 玺爱接入状态（F-5）**——**该端点「已具备、暂不接入」**：**玺爱上传零 5196 调用、零外链**（**依据 R-18 ＋ Kevin clarify「单一印面不走斐萃」；与 `xiai/docs/xiai.spec.md` §3.12.6 同源**）；**写明原因**（单张印面浏览器端即可完成、接入会把零依赖前端路径变成跨进程依赖、红掩膜自动检测在实拍背景不可靠）**与将来适用场景**（**「整页扫描含多枚印面」时 `candidates[]` 的多候选语义才有用**）；**判负形态含「把暂不接入实现为删除端点」**。**④ 新增 §5.5（惰性 OCR 替身口径 ＋ 冷启动测量口径）（F-2 / F-3）**——**§5.5.1 冷启动测量口径（正式采纳，6 条硬性约定）**＝**同机 A/B ＋ 交错多轮（各 ≥3 轮）＋ 取中位数（并给全部轮次原始值）＋ 同时给「绝对基线」与「相对 A/B」两个口径且不得混用 ＋ 输出等价性（`sha256` 不变）必须一并取证 ＋ 两臂计时起点同构**；**并如实登记三处读数的口径分歧**（README §12.6 **1.429 s → 0.242 s** vs ops 绝对基线 **2.964 s → 0.242 s** vs 相对 A/B **1.724 s → 0.260 s**，**同批实测不同轮次、互不矛盾但口径不一**）；**本项实测读数照录**（A 中位 **0.260 s**、B 中位 **1.724 s**、相对降幅 **84.9%**、输出 `sha256` 改前改后逐字同）。**§5.5.2 惰性 OCR 替身口径**＝**为何可惰性**（`processor.py` 模块级 `from paddleocr import PaddleOCR` 拉起整套推理栈 ≈1.28 s，而本端点只走**纯 cv2/numpy** 的 `detect_stamp_regions`、**一次 OCR 都不做**）＋**做法**（`import processor` **之前**把 `sys.modules["paddleocr"]` 换为惰性 shim，真实例化时才加载真包、**args/kwargs 原样透传**、属性方法透明转发）＋**7 条硬要求**（`processor.py` md5 `31ec6cdb…` 未动 / `templates.json` md5 `20acf916…` 未动 / 走同一份源码不复制 / `_get_ocr()` 构造参数与单例缓存语义与「真包缺失抛 `ModuleNotFoundError`」行为全保持 / **输出 `sha256` 不变才是等价性判据** / **`FEICUI_SQUARE_NO_LAZY_OCR=1` 回滚开关不得删** / 证据脚本不得自建判定副本）**＋ §5.5.3「不做」清单**（`pymupdf` 惰性化 / runner 不进 `worker.feicui_worker` / 常驻子进程池 / `AREA_SCALE` 展示位数——**逐项给理由，避免被当漏实现**）。**⑤ 新增待裁项 R18 ～ R20（共 3 条）**——**R18** ＝ **是否在 `config/templates.json` 补 `default` 项**（拟维持「无 `default` ⇒ 内建常量 ＋ 如实标注」，补项须走实现单）；**R19** ＝ **`server/README.md` 内 7 处 `bistro/shu/…` 历史示例路径登记待订正**（**本版不动作：README 属实现侧文档**，缺口编号沿用 G-4）；**R20** ＝ **冷启动绝对基线在 README §12.6 与 ops 证据口径不一，是否统一**（**不阻塞任何 AC 判据**）；**并追加 R 计数留痕行（现共 20 条）**。**⑥ 表头**：**「版本」字段补 v1.6 条**（原 v1.0 ～ v1.5 叙述**逐字保留**）＋ **新增「本版硬约束（v1.6）」行**（8 条：只写文档 / 未改任何代码与数据文件 / 未动 `ops/**` 与 `qa-recheck/**`（只读引用）/ 未启停未占端口（**附本轮 Jing 实测的 13/13 running 读数来源**）/ 不写「本轮已通过」且**证据自记 PASS 只引用不背书** / 先存快照 / 内容指纹纪律 / **AC 计数仍 13 条**）。**⑦ 流程（§0.4）**：**第 0 步快照**＝改版前先存 `feicui/docs/versions/feicui.spec.v1.5.md`（md5 `f7a46c3685b700d1fd959894f1f8d36f`、**737 行 / 194,914 B**，`cmp` 与改版前主文件**逐字节一致**）→ **升版本 v1.5 → v1.6** → **表头「版本」字段 ＋ 表头「本版硬约束」行 ＋ 本表本行**（**三处同步、历史行只增不改**）。**同轮跨文件连带（由 Jing 执行）**：`xiai/docs/xiai.spec.md` 升 **v1.4**（先存 `xiai/docs/versions/xiai.spec.v1.3.md`，md5 `f9b38957e8cdc27ad1068ab261f5b6ba`、693 行 / 135,555 B）、`ctrl/PORTS.md` 升 **v1.14**（先存 `ctrl/versions/PORTS.v1.13.md`，md5 `e3ac8185a91c165ed41d5429676a2155`、199 行 / 97,827 B）。**AC 计数仍 13 条**（本版不改任何 AC 判据、不新增 AC——**§3.14 / §5.5 均为契约与口径登记，不各设 AC**）；**不写任何「本轮已通过」类结论**（**证据自记的 `61/61 PASS` / `11/11 PASS` / `13 条断言` 一律只引用、不背书**）。 | Jing |
| 2026-10-10 | **v1.7** | **按 §0.4 流程落 Kevin 2026-10-10「印人采集」需求（只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.6.md`，md5 `88c6df8150f31c4009892acdfc27401c`、909 行 / 234,138 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `yinpu.db`、未动 `feicui/web/**` / `feicui/server/**`、未动 `ctrl/**`、未动 `xiai/docs/xiai.spec.md`；未跑构建 / 测试、未起服务、未占端口）**：① **新增 §3.15「印人采集」（含 §3.15.1 〜 §3.15.9）**——**页签与路由 `/persons`**（base 取 `import.meta.env.BASE_URL`、经 5164 `/feicui` 反代可达）＋ **四条新端点契约**（`/api/persons/sync` / `/api/persons` / `/api/persons/{grbsm}` / `/api/persons/batches`；**additive、不动 E1 〜 E7**；**错误码一律结构化 JSON、不返回 HTML 错误页**）＋ **存储口径 ＝ 独立 SQLite `feicui/var/person_ingest.db`**（表 `persons` / `person_relations` / `person_import_batches`；`yinpu.db` 一字不碰）＋ **批次包 `exports/person_<yyyymmdd>_01/`**（`manifest.json` + `report.json` + `persons.jsonl` + `relations.jsonl`；既有 `exports/fb_*` 一字不动）＋ **归一化与繁简存法**（繁为正字段、简入 `*_chs` 副字段；抽取项标注 `extraction='rule-based'`；生卒 `?` / 空 ⇒ `null` 无特值）＋ **礼貌限速 / 断点续跑 / 失败清单不得静默跳过** ＋ **零外链资源与「联网只在服务端且只读」红线**；② **§7 新增 AC-14 〜 AC-20（共 7 条 ⇒ AC 计数 13 → 20）**；③ **§9 新增待裁项 R21 〜 R24（共 4 条 ⇒ R 计数 20 → 24）**。**口径真源 ＝ 拆解件 `feicui/docs/person-ingest-draft-v0.1.md`（Zang 2026-10-10）**。 | Jing |
| 2026-10-10 | **v1.8** | **按 §0.4 流程落 Kevin 2026-10-10 追加裁定「批 2（写入 xiai 的通道）由另一会话承接」并冻结交付缝**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.7.md`，md5 `cf59f8c76b1915b59dc5708894909acf`、1032 行 / 257,941 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.json` / 数据文件、未动 `feicui/exports/**` / `feicui/var/**`、未动 `ctrl/**`、未动 `xiai/docs/xiai.spec.md`；未跑构建 / 测试、未起服务、未占端口）**：① **§3.15.1 表下注追加一条（v1.8）＝ 范围裁定登记**（**批 2 由另一会话承接；本文件只约束批 1；feicui 侧不得写 xiai 任何文件、不得做任何 CloudBase 写操作**；**系新裁定、非既有条款改写**；v1.7 表下注①「批 2 归 `xiai/docs/xiai.spec.md` §3.54 增量、由玺爱侧同轮改」**已被取代、原文逐字保留**；**指交接件 `feicui/docs/person-ingest-handoff-v0.1.md`，只引用不复制其全文**）；② **新增 §3.15.10「交付缝（对外接口面，冻结）」**——批次包四文件（`manifest.json` / `persons.jsonl` / `relations.jsonl` / `report.json`）＋ `manifest.json` **必含字段**（**`schema_version` 钉为 `1`**、生成时点、源端点含 `pageRows=1000` 全量口径、源侧 `total`、各文件行数、**字段名清单（数组，与实际 JSONL 键面逐字一致）**）＋ JSONL 形态（**一行一对象 / UTF-8 / 无 BOM / 字段名稳定**）＋ 幂等键 **`source_person_id`（`personGrbsm`）** ＋ 溯源字段 `source` / `source_id` / `source_seqid` ＋ 繁简存法（**繁体为正、简体入 `*_chs`、零转换改写**）＋ 抽取项 `extraction='rule-based'` ＋ 生卒 `?` / 空 ⇒ `null`、禁特值 ＋ **失败项只进 `report.json`**；③ **§7 新增 AC-21 / AC-22（共 2 条 ⇒ AC 计数 20 → 22）**——**AC-21** ＝ manifest 必含字段与 `schema_version==1`、字段名清单与实际 JSONL 键面一致（可脚本校）；**AC-22** ＝ 交付缝四条硬口径逐行可校（幂等键非空且批内唯一 / `*_chs` 副字段存在 / 生卒整数或 `null` 无 `0`·`'?'` 特值 / 抽取项带 `extraction` 标注）；④ **§9 未新增待裁项（R 计数仍 24）**；**表头「版本」行 ＋ 表头「本版硬约束（v1.8）」行 ＋ 本行（§10 变更记录）/ §7 / §9 计数逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-20 一字未动**）。 | Jing |
| 2026-10-10 | **v1.9** | **按 §0.4 流程落 Kevin 2026-10-10 新口径「页签【任务页】→【印谱解析】＋ tabbar 下移 / 顶部固定页眉标题区」**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.8.md`，md5 `3ed4310223233cca78a355c2bb62cfd5`、1080 行 / 270,552 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**`（实现由 Kong 并行另一单负责）/ `feicui/server/**`、未动 `ctrl/**`、未动 xiai 规范；未跑构建 / 测试、未起服务、未占端口**）：① **§3.15.2「① 页签与路由 `/persons`」追加 v1.9 注**——登记**页签文案现为【印谱解析】（原【任务页】）与【印人采集】**、**顶部＝固定页眉＋标题区（吸顶 / 固定、不透明背景、色值走 token）**、**tabbar 位于核心内容区顶部（`main` 内、`RouterView` 之前、不在页眉内）**、**固定页眉不得遮挡内容**（**系新口径、非既有条款改写**）；旧行「**现导航仅【任务页】一项**」**原文逐字保留**并标**已被 v1.9 取代**；② **§7 新增 AC-23（共 1 条 ⇒ AC 计数 22 → 23）**——含**三条可机械判负子项**（页签文案恰为【印谱解析】与【印人采集】／tabbar 位于 `main` 内且在 `RouterView` 之前／固定页眉滚动后仍贴顶且不遮挡内容）；**AC-14 行内文字一字未改**，只**追加 v1.9 注**指向 AC-23；③ **§3.8「任务页需要列表」行追加 v1.9 注**（该「任务页」页签文案已改为【印谱解析】）；④ **§9 未新增待裁项（R 计数仍 24）**；**表头「版本」行 ＋ 表头「本版硬约束（v1.9）」行 ＋ 本行（§10 变更记录）/ §7 / §9 计数逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-22 一字未动**）。 | Jing |
| 2026-10-10 | **v1.10** | **按 §0.4 流程落 Kevin 2026-10-10 三答与「xiai 就绪导入包」交付缝扩展**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.9.md`，md5 `3e73e508476f3f56ff714a70fee9322b`、1091 行 / 280,116 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/exports/**` / `feicui/var/**`、未动 `xiai/**`、未动 `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **新增 §3.15.11「xiai 就绪导入包（对外导出面）」**——按钮「**生成 xiai 就绪导入包**」＋ **两个新端点**（`POST /api/persons/import-package` / `GET /api/persons/import-packages`）＋ **产物目录** `feicui/exports/person_import_<batch_id>/` 与三文件（`person_imports.jsonl` / `person_imports_extraction.jsonl` / `manifest.json`）＋ **主交付严格限在 xiai 现行 18 键**（**逐字列出**；来源 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`，**跨仓契约只引用、不复制其代码**）＋ **三桶降为 `string[]`（只 `value`）且保留 extraction 标注**（sidecar、与对应值等长、元素 `'rule-based'`、**不含 `from`**）＋ **生卒整数或 `null`** ＋ **manifest 必含项**（`schema_version` / 键面 diff＝0 / 幂等键唯一计数）＋ **跨工程边界（feicui 不得写 xiai 文件、不得调云函数）** ＋ **审核门维持**；② **登记两条外部依赖（只登记、不代写）**——**D-1**：xiai 侧需扩 3 键（`courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction`，**归另一会话按其自己规范流程**）；**D-2**：xiai 侧提交需可验证令牌（`imported_by` 由服务端从令牌派生 `uid`）⇒ **提交动作不在 feicui 侧**；③ **§7 新增 AC-24（共 1 条 ⇒ AC 计数 23 → 24）**——五条可机械判负子项（键面 ⊆ 18 键且无多余键 / 三桶为 `string[]` / sidecar 三数组等长且元素恒 `rule-based` 且无 `from` / 行数＝570 且幂等键唯一 / manifest 键面 diff＝0）；④ **§3.15.2「采集区」追加 v1.10 注**指向新端点；⑤ **§9 未新增待裁项（R 计数仍 24）**；**表头「版本」行 ＋ 表头「本版硬约束（v1.10）」行 ＋ 本行（§10 变更记录）/ §7 / §9 计数逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-23 一字未动**）。 | Jing |
| 2026-10-10 | **v1.11** | **按 §0.4 流程落「xiai 线 D-1 回执（主交付键面 18 → 21）」与「Kevin 2026-10-10 关联面裁定（本轮先只落印人本体）」两件输入**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.10.md`，md5 `7eebeafec8137703c3edd0f574696d06`、1167 行 / 297,420 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/exports/**`（尤其未动 `exports/person_20261010_01/relations.jsonl`）/ `feicui/var/**`、未动 `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）、未动 `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§3.15.11 追加升版注（v1.11）**——**主交付键面 18 → 21**（**逐字列出 21 键**；3 新键 `courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction` **紧随各自值键（`courtesy_names` / `art_names` / `alias_names`）之后**）；三键形态 ＝ **`string[]` / 与对应值数组等长 / 元素非空字符串 / 值域不封闭（不得据 `rule-based` 硬校验）**；**缺键不拒收（18 键形态仍可直接提交）**；**违形态由 xiai 侧判 `INVALID_VALUE` ＋ 零写入**；**采纳后不落 person 行**；`person_imports_extraction.jsonl` **降为「派生冗余件（兼容保留）」**（同一计算结果导出、**非第二真源**）；**manifest 必含项随动**（允许键 **21** / 键面 diff **vs 21**）；② **§7 AC-24 同步为三态判据**——**(a) 21 键形态 ⇒ PASS** / **(b) 18 键形态（缺 3 键）⇒ 亦 PASS（兼容）** / **(c) 旧 feicui 形态（32 键 / 三桶为对象数组）⇒ FAIL**；并写明 **`'rule-based'` 只作本批数据断言、不得写成对外契约判据**（**AC 计数不变，仍 24**）；③ **新增 §3.15.12「关联面范围裁定（v1.11 新增）」**——**登记 Kevin 2026-10-10 裁定「本轮先只落印人本体」**：**1650 条关联留在 feicui 侧**（`exports/person_20261010_01/relations.jsonl` 留在原处、可复跑、数据不丢）、**关联作为独立需求另开**；④ **§9 待裁面**：**R22 / R24 逐条处置为「挂起」（保号留行、状态列就地另注；R 计数仍 24，未新增待裁项）**；⑤ **表头「版本」行 ＋ 表头「本版硬约束（v1.11）」行 ＋ §7 / §9 计数留痕 ＋ 本行（§10 变更记录）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-23 一字未动**）。 | Jing |
| 2026-10-10 | **v1.12** | **按 §0.4 流程落 Kevin 2026-10-10「印谱（item）采集」需求**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.11.md`，md5 `7e7f75d9fd76bd9076df4534a1bd37a6`、1208 行 / 313,554 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**`（尤其未动 `exports/person_20261010_01/relations.jsonl`）/ `feicui/var/**`、未动 `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）、未动 `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **新增 §3.16「印谱（item）采集」（含 §3.16.1 〜 §3.16.9）**——**第三页签【印谱采集】＋ 路由 `/items`**（base 取 `import.meta.env.BASE_URL`）＋ **四个新端点**（`POST /api/items/sync` / `GET /api/items` / `GET /api/items/{seqid}` / `GET /api/items/batches`；**additive、不动 E1 〜 E7 与 P1 〜 P6**；**错误码一律结构化 JSON、不返回 HTML 错误页**）＋ **新独立库 `feicui/var/item_ingest.db`**（表 `items` / `item_creators` / `item_import_batches`；**与 `var/person_ingest.db` 分库、`yinpu.db` 一字不碰**）＋ **就绪包 `feicui/exports/item_import_<batch_id>/`**（`items.jsonl` / `item_creators.jsonl` / `manifest.json`；**候选键面未裁 ⇒ `key_face_status: "pending_xiai"`**）＋ **采集口径**（`book/list` `pageRows=3000` 一次取全 1742 ＋ 逐本 `book/detail`，**不采 `graph/book`**，断点续跑 ＋ 礼貌限速 ＋ 失败清单；限流 `code:"429"` 不得当成功）＋ **字段面与归一化**（照登拆解件 §3；`volume_count` / `date_year` 整数或 `null` 禁特值；繁体为正 ＋ `*_chs`；`raw_json` 不丢源）＋ **跨工程边界**（feicui 不写 xiai 文件 / 不调云函数）＋ **item↔person sidecar**（`source_item_id` / `creator_type` / `creator_role` / `creator_relator` / `creator_name` / **`person_grbsm`** / **`source_face`**（`book_detail.creator_list` ｜ `person_graph`）/ `seq`；**并写明 `source_face` 与 person 侧已删的 `from` 不是同一概念**）；② **§7 新增 AC-25 〜 AC-32（共 8 条 ⇒ AC 计数 24 → 32）**（底稿 ＝ 拆解件 §7 的 IT-1 〜 IT-8，逐条「判据 / 证据形式 / 判负形态」三元组）；③ **⚠ 原位改写 AC-23**——**页签集合 2 → 3**（**恰为【印谱解析】/【印人采集】/【印谱采集】**；判负「页签数量 ≠ 2」随动为「≠ 3」），**行内加「v1.12 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.11.md` §7**（**系原位改写，不是「既有条款自动失效」**）；④ **§9 新增待裁项 R25 〜 R28（共 4 条 ⇒ R 计数 24 → 28）**（底稿 ＝ 拆解件 §8 的 WI-1 〜 WI-4）；⑤ **表头「版本」行 ＋ 表头「本版硬约束（v1.12）」行 ＋ §7 / §9 计数留痕 ＋ 本行（§10 变更记录）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-22 / AC-24 一字未动；AC-23 走原位改写并留痕**）。 | Jing |
| 2026-10-10 | **v1.13** | **按 §0.4 流程落「实测驱动的采集口径偏离」——对 v1.12 旧采集口径（列表 1 次 ＋ 逐本 detail、**不采 `graph/book`**）的正式偏离**（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.12.md`，md5 `b5581b7fd995e21f0f08a71676bbe8a2`、1369 行 / 349,648 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**`、未动 `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）、未动 `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：**理由 ＝ 实测限流**（**`book/detail/<seqid>` 严限流**，Kong 实跑日志 `5/10/20/40/60s` 退避反复 ⇒ 逐本 detail 取本体在 1742 本量级不可行；**`graph/book/<seqid>` 实测健康**、2 s 间隔 3/3 成功、且同样给 `creatorType` ＋ `personGrbsm`）（**口径真源 ＝ 拆解件 `feicui/docs/item-ingest-draft-v0.1.md` §10**）：① **§3.16.6「⑤ 采集口径」原位改写**——**item 本体全部取自 `book/list` 一次全量**（不再逐本 detail 取本体）＋ **item↔person 关联主源改 `graph/book/<seqid>`（`source_face='book_graph'`）**（与既有 `person_relations`（`source_face='person_graph'`）合并去重）＋ **`book/detail` 降 best-effort（默认关，显式开关才开）**（仅补 `creatorRole` / `creatorRelator` / `bookDonor`，慢速分片、失败进清单、不阻塞主交付）＋ **manifest / report 必含 `detail_policy` ＋ 因 detail 降级缺失的三字段 ＋ `detail_unconfirmed` 计数**；**旧口径原文逐字保留并标「已被 v1.13 取代」（系原位改写、非「既有条款自动失效」）**；② **§3.16.8 sidecar 随动**：`source_face` 取值集合明确为 `book_graph` / `person_graph` / `book_detail`（后者仅 best-effort 出现）；③ **逐条校正受影响 AC（编号 / 条数不变，仍 32 条）**：**AC-28**（`donor`／`bookDonor` 降 best-effort，缺失不判负、存在须逐字命中 `林章松`）＋ **AC-31**（manifest 必含项增补 `detail_policy` / 缺失三字段 / `detail_unconfirmed`）**原位改写**；④ **§3.16.1 表下注 ② / §3.16.3 Q1 / §3.16.5 manifest 必含三处加 v1.13 注随动**（**§0.4 第 5 条：同步受影响的小节**）；⑤ **§7 计数留痕（v1.13）一条 ＋ §9 计数留痕（v1.13）一条（R 计数不变，仍 28 条）＋ 表头「版本」行 ＋ 表头「本版硬约束（v1.13）」行 ＋ §3.16 落位声明（v1.13）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-27 / AC-32 一字未动；AC-28 / AC-31 走原位改写并留痕**）。 | Jing |
| 2026-10-10 | **v1.14** | **按 §0.4 流程落「印谱（item）采集 — spec/实现分叉收口 ＋ 重建幂等口径登记」**（**输入 ＝ Neng 质检 OBS（均不判负、需收口）**：**① `POST /api/items/package`（Kong 实现中 additive 追加的第五端点）未入规范 ⇒ spec/实现分叉**；**② 点按钮重建就绪包会重写时间戳（实测 `created_at` 15:39:16 → 15:42:03）而两个 JSONL 逐字节未变**）（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.13.md`，md5 `5dfcb49edbeb8dc5587f371c6ffbf5be`、1385 行 / 367,653 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**`（尤其未动 `exports/item_import_item_20261010_01/**`）/ `feicui/var/**` / `feicui/yinpu.db`、未动 `xiai/**`（尤其未改对方已入库的 `xiai/docs/person-import-handoff-from-feicui.md`）、未动 `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§3.16.3 端点表追加 Q5 `POST /api/items/package` 契约**（**语义 ＝ 从 `var/item_ingest.db` 本库重建 xiai 就绪包、不联网采集、与 CLI `package` 共用实现 `write_package_from_db`**；**入参 ＝ 查询参数仅白名单 `batch_id`（可选；缺省＝库内最新批次，按 `batch_id` 降序取首）**；**错误码 ＝ 未白名单参数 400（`UNSUPPORTED_PARAM`）/ 批次不存在 404（`BATCH_NOT_FOUND`）/ 库内无批次 404（`NO_BATCH`）/ 其余 409，一律结构化 JSON**；**响应 ＝ 就绪包摘要**；**两条红线 ＝ 零联网（不调任何源端点）＋ 不写 xiai 任何文件**）＋ **§3.16.3 v1.14 注**（spec/实现分叉收口）＋ **§3.16 落位声明（v1.14）**；② **§3.16.5 就绪包补「重建幂等」口径**——**仅 `manifest.json` 的 `created_at`（≡ 摘要 `generated_at`）与 `report.json` 的 `generated_at` 等时间戳变化，`items.jsonl` 与 `item_creators.jsonl` 内容逐字节不变**（**实测锚点 15:39:16 → 15:42:03、两 JSONL 未变**）；③ **§7 新增 AC-33（共 1 条 ⇒ AC 计数 32 → 33，AC-01 〜 AC-33）**——**三条子项（可达 / 重建幂等 / 零联网且不写 xiai）＋ 两条负向（未白名单参数 400 / 批次不存在 404）**；④ **§7 计数留痕（v1.14）一条 ＋ §9 计数留痕（v1.14）一条（R 计数不变，仍 28 条）＋ 表头「版本」行 ＋ 表头「本版硬约束（v1.14）」行 ＋ §3.16 落位声明（v1.14）＋ 本行（§10 变更记录）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-32 一字未动**）。 |
| 2026-10-10 | **v1.15** | **按 §0.4 流程落 Kevin 2026-10-10「印章全量包」需求（第三条采集线，与 §3.15 印人 / §3.16 印谱同型）**（**口径真源 ＝ Zang 已实测的源契约 ＋ Kevin 三条裁定 A / B / C —— 逐条照登、不自行发明**；**影像面 v1.15→ 改口径（Kevin 裁定：TIFF 直供 xiai 影像库）**；**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.14.md`，md5 `5651c5fd7cad6a88081f9a311a6b6745`、1399 行 / 382,380 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**` / `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **新增 §3.17「印章（seal）采集」（含 §3.17.1 〜 §3.17.9）**——**第四页签【印章采集】＋ 路由 `/seals`**（base 取 `import.meta.env.BASE_URL`）＋ **五个新端点**（`POST /api/seals/sync` / `GET /api/seals` / `GET /api/seals/{seqid}` / `GET /api/seals/batches` / `POST /api/seals/package`；**additive、不动 E1 〜 E7 与 P1 〜 P4 / Q1 〜 Q5**；**错误码一律结构化 JSON、不返回 HTML 错误页**）＋ **新独立库 `feicui/var/seal_ingest.db`**（表 `seals` / `seal_links` / `seal_import_batches` / **`seal_images`**；**与 `var/person_ingest.db` / `var/item_ingest.db` 分库、`yinpu.db` 一字不碰**）＋ **就绪包 `feicui/exports/seal_import_<batch_id>/`**（`seals.jsonl` / `seal_links.jsonl` / `manifest.json` / `report.json` / `images/` / `images_manifest.jsonl`；**候选键面未裁 ⇒ `key_face_status: "pending_xiai"`**）＋ **采集口径**（`seal/list` `pageRows=5000` 一次取全 3679 ＋ **形製码表本地派生** ＋ `seal/detail` 降 best-effort（**默认关**）＋ 断点续跑 ＋ 礼貌限速 ＋ 失败清单；限流 `code:"429"` 不得当成功）＋ **字段面与归一化**（**`null` 不得写空串 / `0` 特值**；繁体为正 ＋ `*_chs`；`raw_json` 不丢源；**保留 `audit_status` 字段与分布统计**）＋ **影像面（v1.15 改口径：TIFF 直供 xiai 影像库）**（**全部直供**：印面 3679 ＋ 印体释文 2627 ＋ 边款 459 ≈ **6765 张**；**本侧取图走 IIIF 只用原生裁切 `/full/0/default.jpg`、禁止放大尺寸（`!400,400` 上采样判负）**；**JPEG → TIFF 无损容器转换（不重采样 / 不二次有损；如实登记「质量受源 JPEG 限制」）**；**就绪包 `images/` 镜像 xiai 形态 ⇒ `images/<sha256[:2]>/<sha256>.tiff`、包内不放 JPEG**；**`images_manifest.jsonl` 为唯一索引（含 `seqid`/`kind`/`source_ref`/`sha256`/`bytes`/尺寸/`conversion`/`upscaled:false`）**；**重出包不得删或重转已有影像**；`NaN_` 开头 ref 记「源侧无图」；**xiai 影像库权威契约（只引用 `xiai/server/app/store.py` ＋ `codec.py`，不复制其代码）：`POST /api/image/store`／路径 `<sha256[:2]>/<sha256>.tiff`／只收 TIFF（魔数 `II*\0`／`MM\0*`）／产物侧 4 MiB · 输入侧 1 MB／幂等**）＋ **跨工程边界**（feicui 不写 xiai 文件 / 不调云函数）＋ **seal↔印谱↔印人 sidecar**（`seal_links.jsonl`：`source_seal_id` / `link_kind` / `target_id` / `target_name` / `as_book_id` / `seq`；**桥接 `graph/seal` 印谱 id ↔ item 库 `source_item_id`**）；② **§7 新增 AC-34 〜 AC-46（共 13 条 ⇒ AC 计数 33 → 46）**（全量 3679 ＋ `seqid` 唯一 / `audit_status` 分布 / 形製码表「异性」逐字 / 桥接 19 种印谱 ⊆ item 库 / 影像取数与张数上限与放大判负 / **影像为 TIFF 容器（魔数判负）＋ 单张 ≤ 4 MiB 且 ≤ 1 MB 输入档** / **`images/` 路径形状 `<sha256[:2]>/<sha256>.tiff` 且 sha256 与字节自洽** / **`images_manifest.jsonl` 与文件一一对应（无孤儿 / 无缺失）** / `/api/seals` 分页自洽且 `cursor`⇒400 / `/api/seals/package` 重建幂等（`images/` 不得删或重转）/ 门禁三库指纹未变）；③ **⚠ 原位改写 AC-23**——**页签集合 3 → 4**（**恰为【印谱解析】/【印人采集】/【印谱采集】/【印章采集】**；判负「页签数量 ≠ 3」随动为「≠ 4」），**行内加「v1.15 原位改写」注、原文字逐字留存于快照 `docs/versions/feicui.spec.v1.14.md` §7**（**系原位改写，不是「既有条款自动失效」**）；**§3.15.2 v1.9 注 ＋ §3.16.2 对页签集合的 v1.15 追注随动**；④ **§9 新增待裁项 R29 〜 R32（共 4 条 ⇒ R 计数 28 → 32）**（**R30 已由 Kevin 2026-10-10「TIFF 直供」裁定处置、保号留行**）；⑤ **表头「版本」行 ＋ 表头「本版硬约束（v1.15）」行 ＋ §7 计数留痕（v1.15）一条 ＋ §9 计数留痕（v1.15）一条 ＋ §3.16 落位声明（v1.15）＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-32 一字未动**）。 | Jing | Jing |
| 2026-10-10 | **v1.16** | **按 §0.4 流程落「印章影像面三态分桶 ＋ 共用窗口限流 ＋ 可机械判负面」口径纠偏**（**口径真源 ＝ Zang 在 v1.15 落盘后实测的缺口逐条照登**；**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.15.md`，md5 `b542ff939c72c845201bee54244ec8b9`、1585 行 / 434,875 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/seals.py` 与前端）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§3.17.8 影像面追加/修正**——**源侧缺图独立分桶（三态 `ok` / `source_no_image` / `failed`）**：`source_no_image` 子因 **① `NaN_` 开头 ref；② 持久 `HTTP 500`（有界重试 3 轮 2/8/30s 后仍 500，`error` 记 `HTTP 500`）**，`failed` **仅留给可重试的瞬态错误**；**`source_no_image` 不得计入采集失败、不得静默丢弃**；**观测证据**：60 refs 中 **11 条 `HTTP 500`**（响应体 `text/plain` 21 字节 `Internal Server Error`、无跳转），**1/4/8 并发下失败集合完全相同（49 ok / 11 fail）、0 次 429** ⇒ **按 ref 恒定、非限流**；失败 ref **按前缀聚批**（`11_*`/`12_*` 全挂、`19_*` 正常）；**站点自身详情页同一 ref `naturalWidth=0`（坏图）**、正常 ref 渲染 204×365；**共用窗口限流**：**影像请求与 API 请求共用站点级窗口** ⇒ **429 一律判负、不得当成功**（出现即降并发＋退避）；实测 8 workers × 0.1s ⇒ 0 次 429、**17.2 张/秒**；**影像面每张记录 `width`/`height`/`bytes`/`tiff_sha256`** 与 **双档上限（xiai 产物 4 MiB / 输入 1 MB）**；**放大尺寸判负保留 v1.15 原文并补定量依据**（证据文件 `ops/seal-ingest/09_upscale_probe.json`；同区域 `full→204×365 / 400,→400×716 / 1200,→1200×2147 / 4096,→2795×5000`；Pillow 判定纯插值：边缘强度双三次上采样 **135.71** vs 服务器 1200 大图 **137.69**（差 1.5%）、MAD **4.32/255**、累方差 2858 vs 2824 ⇒ **不增真实信息**）；**§3.17.6 ⑤ 加 v1.16 追注（共用窗口限流）**；**§3.17.5 `report.json` 增补影像三态分桶计数 ＋ `source_no_image` 按 ref 前缀聚合清单/计数/样例 `seqid`**；**§3.17.5 `images_manifest.jsonl` 增 `tiff_sha256` 与三态 `status`**；② **§7 新增 AC-47 〜 AC-52（共 6 条 ⇒ AC 计数 46 → 52）**——**影像 `failed` 桶空或仅瞬态且附重跑命令 1**（AC-47）＋ **`source_no_image` 按 ref 前缀聚合清单＋计数＋样例 `seqid` 1**（AC-48）＋ **`images_manifest.jsonl` ↔ `images/**` 双向一一对应（无孤儿/无缺失，两方向计数）1**（AC-49）＋ **每行 `sha256` 与 TIFF 字节逐行自洽（随机 20 行重算）1**（AC-50）＋ **TIFF 魔数逐行成立 ＋ 单张 ≤ 双档上限 1**（AC-51）＋ **影像台账每行有 `width`/`height` 1**（AC-52）；③ **§9 新增待裁项 R33（共 1 条 ⇒ R 计数 32 → 33）**（**源侧缺图在 xiai 侧的去留：留空白行 vs 不落行**）；④ **⚠ 原位改写 §3.17.8 的 `NaN_` ref 状态口径 ＋ §7 AC-40 的同一记号**（原写 `status=source_missing` ⇒ 统一为 **`source_no_image`**；原文字逐字留存于快照 `docs/versions/feicui.spec.v1.15.md`；**系原位改写，不是「既有条款自动失效」**）；⑤ **表头「版本」行 ＋ 表头「本版硬约束（v1.16）」行 ＋ §7 计数留痕（v1.16）一条 ＋ §9 计数留痕（v1.16）一条 ＋ §3.17 落位声明（v1.16）＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-39 / AC-41 〜 AC-46 一字未动；AC-40 原位改写仅限 `status` 记号**）。 | Jing | Jing |
| 2026-10-10 | **v1.17** | **按 §0.4 流程落「印章影像面孔径子因由二扩三（补 `bad_bytes`）＋ `failed` ＝ 0 改口径 ＋ AC-53」**（**口径真源 ＝ Zang 影像台账终态实测 6765/6765 逐条照登**：`ok 6347` / `source_no_image 417`（`http_500` 415 ＋ `nan_ref` 2）/ **`failed` 仅 1 ＝ `2_3609_1`**——HTTP `200` ＋ `content-type: image/jpeg` 但正文 697 B 为 iipsrv 把自己的响应头当正文、非 JPEG、PIL 解码失败、**持久复现** ⇒ 属**第三个源侧子因**，与 `failed` 现有定义（仅可重试瞬态）不相容、必须入册）（**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.16.md`，md5 `391ac0e3cd4295ee7106784b5b1dbdd5`、1611 行 / 456,294 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/seals.py` 与前端）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§3.17.8 a-v1.16 块的 `source_no_image` 子因行由「两类」原位扩为「三类」**——新增子因 **（c）坏字节 `bad_bytes`**（**HTTP `200` ＋ `content-type: image/jpeg`、正文非图像 / 不可解码**；**实例 `2_3609_1`：正文 697 B 为 iipsrv 把自己的响应头当正文吐出、非 JPEG 魔数 `FFD8`、PIL 解码失败、持久复现**），并写明**三子因均为源侧事实、不得计入采集失败**，`error` 字段记实际现象原文；② **同块 `failed` 行原位改写**——由「收尾时 `failed` 桶须为空，或仅瞬态且附重跑命令」改为 **「收尾时 `failed` ＝ 0」**（**因三子因（`NaN_` / 持久 5xx / 坏字节）已穷尽枚举；将来新第四类必须先入册再归类、不得静默落 `failed`**）＋ **判负形态随动（`failed` 桶 ≠ 0）**；③ **§3.17.8 a. 影像面加 v1.17 追加块**（子因穷尽枚举三类 / `bad_bytes` 实例锚 `2_3609_1` / `failed` ＝ 0 理由）；**§3.17 落位声明（v1.17）随动**；④ **§7 AC-47 原位改写为「`failed` ＝ 0」＋ AC-48 证据形式随动（子因计数由「两类」扩为「三类」）＋ 新增 AC-53**（**承载「`bad_bytes` 实例（`2_3609_1`）归 `source_no_image` 面不在 `failed`」**；⇒ **AC 计数 52 → 53，AC-01 〜 AC-53**）；⑤ **§9 R33 行子因随动注（子因三扩为「① `NaN_` / ② 持久 `HTTP 500` / ③ 坏字节 `bad_bytes`」）＋ §9 计数留痕（v1.17）**——**本版未新增任何待裁项（R 计数仍 33）**，**逐字理由 ＝「`bad_bytes` 已在 §3.17.8 a-v1.16 块的 `source_no_image` 子因行随动追加（子因二扩三），其 xiai 侧去留与 `NaN_` / `HTTP 500` 两子因同归 R33 的『源侧缺图在 xiai 侧的去留（留空白行 vs 不落行）』一问，R33 覆盖面不因子因细分而改变，故不新增 R 行」**；⑥ **表头「版本」行 ＋ 表头「本版硬约束（v1.17）」行 ＋ §7 计数留痕（v1.17）一条 ＋ §9 计数留痕（v1.17）一条 ＋ §3.17 落位声明（v1.17）＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-46 / AC-49 〜 AC-52 一字未动；AC-47 原位改写 / AC-48 随动均留痕**）。 | Jing |
| 2026-10-10 | **v1.18** | **按 §0.4 流程落「印章影像面逐张台账字段语义纠偏（以包内实物为准）＋ AC-41 / AC-51 删去恒假的『输入档 ≤ 1 MB』判据 ＋ 新增 AC-54（超档逐行标记）＋ R34 ＋ 端点 mime 写清」**（**口径真源 ＝ Zang 对本包实物（`feicui/exports/seal_import_seal_20261010_01/`）实测逐条照登 ＋ xiai `server/app/store.py` 只读引用**；**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.17.md`，md5 `4e33681c38a7a445ac39f9371998ad05`、1625 行 / 472,273 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/seals.py` 与前端）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§3.17.8 ④ 逐张台账字段语义原位更正（以包内实物为准）**——**`sha256` ＝ TIFF 字节的 sha256（即内容寻址键、＝文件路径名）；`bytes` ＝ TIFF 字节数；新增 `source_bytes` / `source_sha256` ＝ 源 JPEG 侧（溯源用）；删去对 `tiff_sha256` 键的引用——包内实物 `images_manifest.jsonl` 键面 ＝ `[bytes, container, conversion, height, kind, seqid, sha256, source_format, source_ref, source_url, upscaled, width]`，无 `tiff_sha256` 键**（**错误在规范描述，内容寻址键必须是 TIFF 字节、此点是对的**）；**§3.17.5 成员 6 键面随动**；**§3.17.8 加 a-v1.18 追加块（字段语义 ＋ 超 4 MiB 桶 6 张）**；② **§7 AC-41 / AC-51 原位改写**——**判据只留「单张 ≤ 4 MiB（`STORED_MAX_BYTES`）＋ 逐行 TIFF 魔数」；删去恒假的「输入档 ≤ 1 MB」**（**依据 ＝ xiai `server/app/store.py::validate_payload` 只校验「空 / `STORED_MAX_BYTES`（4 MiB）/ TIFF 魔数」三面，**不校验 1 MB**；`codec.MAX_INPUT_BYTES` ＝ 1 MB 属 xiai 编解码口输入面，不得用作本包 / 本端点判据；**按现文字 AC 必然 FAIL 而实际是规范写错了**）；**§7 AC-50 随动（`tiff_sha256` ⇒ `sha256`）**；③ **§7 新增 AC-54**——**`> 4 MiB` 的行须逐行标记（`oversize_for_xiai_store`）＋ 顶层计数 ＋ 清单，且不得自行降采样 / 转码**，判负形态 ＝「超档而未标记」或「自行降采样 / 转码」（⇒ **AC 计数 53 → 54，AC-01 〜 AC-54**）；④ **§9 新增待裁项 R34**——**6 张超 xiai store 4 MiB 上限影像（`seqid 3353 / 3366 / 3367 / 3464 / 3506 / 3510`，均 `kind=yt`、4.37–4.96 MB）在 xiai 侧的去留**：① xiai 放宽 `STORED_MAX_BYTES` / ② 落库标超档不做缩图 / ③ xiai 侧另降采样 / ④ 本包剔除这 6 条（**逐项写明后果**，归 xiai 线裁）（⇒ **R 计数 33 → 34**）；⑤ **§3.17.3 端点表追加 S6**（`GET /api/seals/{seqid}/image/{kind}` 的 mime 写清为 **`image/jpeg`（源 JPEG 缓存，供页面缩略图；与包内 TIFF 交付面无关）**；**实测该端点返回 `image/jpeg`，正确**）；⑥ **§7 计数留痕（v1.18）一条 ＋ §9 计数留痕（v1.18）一条 ＋ §3.17 落位声明（v1.18）＋ 表头「版本」行 ＋ 表头「本版硬约束（v1.18）」行 ＋ 本行（§10 变更记录）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-40 / AC-42 〜 AC-49 / AC-52 / AC-53 一字未动；AC-41 / AC-50 / AC-51 走原位改写 / 更正并留痕**）。 | Jing |
| 2026-10-10 | **v1.19** | **按 §0.4 流程落「AC-41 原位收窄（超档允许、但必须逐行标记；未被标记的超档行才是 FAIL）＋ 源侧 `ref_id` 未命中 person 库记账口径 ＋ 端点响应顶层内部键 `_db_path` 观察项」**（**口径真源 ＝ Neng 独立质检 OBS-1 ＋ Zang 对本包实物（`feicui/exports/seal_import_seal_20261010_01/`）与三线端点实测逐条照登**；**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.18.md`，md5 `142349f93f6c867213f875d073a20636`、1640 行 / 491,387 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/seals.py` 与前端）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口**）：① **§7 AC-41 原位收窄**——**字面判负由「单张 > 4 MiB ⇒ FAIL」收窄为「未被逐行标记 `oversize_for_xiai_store` 的超档行 ⇒ FAIL」**（**超档本身不判负，但必须逐行标记；已标记的超档行豁免本 AC**）；**并写明与 AC-54 的分工**（**AC-54 管「标记 / 顶层计数 / 清单 / 不得自行降采样或转码」，AC-41 管「容器与尺寸上限的可判定口径」**）——**依据 ＝ Neng 质检 OBS-1：AC-41（v1.15 立 / v1.18 已部分原位改写）与 AC-54（v1.18 新立）对同一事实（6 张超档）一判负一豁免、下一轮质检无法机械判定；真值 ＝ 包内 `images/` 6347 张中 6 张 > 4 MiB（`seqid 3353/3366/3367/3464/3506/3510`，均 `yt`，4.38–4.96 MB），已逐行标 `oversize_for_xiai_store: true` ＋ 顶层计数 6 ＋ 清单；1–4 MiB 219 张**（**原文字逐字留存于快照 `docs/versions/feicui.spec.v1.18.md` §7；系原位收窄，不是「既有条款自动失效」**）；② **§3.17.8 加 a-v1.19 追加块**——**① 源侧 `ref_id` 未命中 person 库的记账口径**（**印主面 8/438 行、篆者面 1/403、边款篆者面 6/11 的 `ref_id` 不在 `var/person_ingest.db` 的 570 人内；属源侧引用未收录、不判负；`seal_links` 允许 `ref_id` 不命中 person 库，但必须在 `report.json` 给计数（按面分列 ＋ 合计）**）＋ **② 端点响应顶层内部键 `_db_path` 观察项**（**三线对照 `GET /api/seals` / `/api/persons` / `/api/items` 顶层键完全相同（均含 `_db_path`）⇒ 系三条采集线共有惯例、非本线不一致；登记为观察项（不判负、不立 R、不立 AC）**）；③ **本版 AC 计数不变（仍 54 条，AC-01 〜 AC-54）／R 计数不变（仍 34 条，R1 〜 R34）**——**源侧 `ref_id` 未命中 person 库属源侧引用未收录（不判负）、`_db_path` 属三线共有惯例（非不一致），二者均不作 feicui 可判负目标 ⇒ 不设新 AC；原拟的待裁项 R35（「是否从响应中删去内部路径键」）已撤回（逐字理由见 §9（v1.19））⇒ 不设新 R，R 计数回退到 34**；④ **§7 计数留痕（v1.19）一条 ＋ §9 计数留痕（v1.19）一条 ＋ §3.17 落位声明（v1.19）＋ 表头「版本」行 ＋ 表头「本版硬约束（v1.19）」行 ＋ 本行（§10 变更记录）逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-40 / AC-42 〜 AC-54 一字未动；AC-41 走原位收窄并留痕**）。 | Jing |
| 2026-10-10 | **v1.20** | **按 §0.4 流程落 Kevin 2026-10-10「关联面（三表联立）」需求**（**口径真源 ＝ `feicui/docs/relation-ingest-draft-v0.1.md`（Zang 2026-10-10 起草；§1 / §2 为实测读数、§3 为默认口径）—— 逐条照登、不自行发明**；**背景 ＝ Kevin 2026-10-10 裁定「印人关联面本轮先不导入、作为独立需求另开」（§3.15.12）**；**只写文档：本文件一处、先存快照 `feicui/docs/versions/feicui.spec.v1.19.md`，md5 `814df2a5e6fda7d6dfa4ccbc36e974eb`、1652 行 / 507,960 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/relations.py` 与包）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口、未 push**）：① **新增 §3.18「关联面（三表联立）」（含 §3.18.1 〜 §3.18.8）**——**① 三表来源与行数**（`person_relations` **1650** / `item_creators` **1440** / `seal_links` **8964**；含表下注与可连键对账、去重面、涉及实体规模）＋ **② 统一关系边键面**（`predicate` 五值枚举 `person_to_item` / `item_to_person` / `person_to_seal` / `seal_to_item` / `seal_to_person` ／ `subject_type` · `subject_id` ／ `object_type` · `object_id` ／ `role` · `role_note` ／ `evidence` 数组 ／ `source_ref` ／ `image_ref` ／ `name`（＋ `_chs`）／ `seq` ／ `batch_id`）＋ **③ 幂等键 `(predicate, subject_id, object_id)`** ＋ **④ 口径 R-a 〜 R-f（默认值逐条照登 ＋ 标「待 xiai 裁定、一句话可改」）** ＋ **⑤ 就绪包 `exports/relation_import_<batch_id>/`**（`relations.jsonl` / `manifest.json` / `report.json`，**`key_face_status:"pending_xiai"`**；重建幂等口径）＋ **⑥ 两个 additive 端点**（**T1** `POST /api/relations/package`（零联网、可选 `batch_id`、未白名单参数 400（`UNSUPPORTED_PARAM`）、批次不存在 404（`BATCH_NOT_FOUND`）、响应含 `key_face_status:"pending_xiai"`）、**T2** `GET /api/relations/summary`）＋ **⑦ 红线**（**零联网（不得再打复旦站点、纯本库联立）**／**只读三库三包**／**feicui 不写 xiai 任何文件**）＋ **⑧ 页面形态**（**本需求不加页签、不动 tabbar ⇒ 不触发 AC-23**，此句显式写入避免下轮误改）；② **§7 新增 AC-55 〜 AC-61（共 7 条 ⇒ AC 计数 54 → 61，AC-01 〜 AC-61）**——**逐条对应拆解件 §4 的 A-1 〜 A-7**：**各 `predicate` 计数与 `report.json` 一致**（AC-55）＋ **去重算术可复算（`|A∪B| = |A| + |B| − |A∩B|`，点名 1349 / 1281 / 1249 ⇒ 1381）**（AC-56）＋ **可连键逐条成立（除 `ghost` 行）**（AC-57）＋ **未命中 / 幽灵有清单与计数（不为 0 必逐条列出）**（AC-58）＋ **四库指纹 ＋ 三包未变**（AC-59）＋ **重建幂等（仅时间戳变 / JSONL 字节不变）**（AC-60）＋ **零联网（无新增采集请求）**（AC-61）；③ **§9 新增待裁项 R35 〜 R39（共 5 条 ⇒ R 计数 34 → 39）**——**R35** 关系集合名 / 模型；**R36** 键面裁剪（`pending_xiai`）＋ 幂等键是否用合成 hash；**R37** 导入通道（是否沿用三段式提交 / 审核）；**R38** 幽灵行（`as_book_id='test'` 1 条）与 14 个未收录印人 id 的去留；**R39** 双源去重形态（合一行 ＋ `evidence` 数组 vs 拆两行保各自原字段）——**逐项写明后果（影响面列）、归 xiai 线裁**；④ **§7 计数留痕（v1.20）一条 ＋ §9 计数留痕（v1.20）一条 ＋ §3.18 落位声明（v1.20）＋ 表头「版本」行 ＋ 表头「本版硬约束（v1.20）」行 ＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**AC-01 〜 AC-54 一字未动；R1 〜 R34 一字未动**）。 | Jing |
| 2026-10-10 | **v1.21** | **按 §0.4 流程落 Kevin 2026-10-10 需求「【新建 job（E1）】页的 `pdf_path` 输入框改为拖曳文件，不必手动键入」**（**两条裁定照登**：① **拖动上传为主 ＋ 保留折叠的「高级：手输服务器路径」（默认收起）**；② **落点 `feicui/inbox/<yyyymmdd>/<原文件名>.pdf`，同名同内容复用**；**浏览器事实（写入作前提）**：**拖入的 `File` 不带本地路径 ⇒ 拖曳＝上传到服务器再拿服务器侧路径调 E1**；**只写文档：本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.20.md`，md5 `e8911ed84db367bf0f0818e665f42cb1`、1773 行 / 544,064 B，`cmp` 逐字节一致；未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/routers/jobs.py` / `server/app/config.py` / `server/app/main.py` / `JobsPage.vue`）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`；未跑构建 / 测试、未起服务、未占端口、未 push**）：① **新增 §3.19「E8 拖曳上传端点契约（`POST /api/jobs/upload`）（5196）」（含 §3.19.1 〜 §3.19.7）**——**前提**（拖入 `File` 无本地路径 ⇒ 必为「上传后拿服务器侧路径调 E1」）＋ **请求**（**裸字节流**；`Content-Type` ∈ {`application/pdf`, `application/octet-stream`}；**不得走 multipart**——理由：源 PDF 实测 38 MB、历史 **372 MB**，而仓内既有 `server/app/multipart.py` 是**把整体读进内存**的纯 stdlib 实现（`parse_multipart(content_type, body: bytes)`）；文件名走 **`X-Filename`**（URL-encoded UTF-8，回退 `Content-Disposition.filename`、再回退 `upload.pdf`）；单文件上限 **默认 512 MiB**（`config` 常量可改））＋ **落点 / 清毒 / 幂等**（**`feicui/inbox/<yyyymmdd>/<basename>.pdf`**；**basename ＋ 剔路径分隔符 / `..` / 控制字符 ＋ 长度上限 ＋ 越界 ⇒ 400**；**同名同内容 ⇒ 不重写、`200` `idempotent:true`、mtime 不变**；**同名异内容 ⇒ 绝不覆盖、落 `<basename>-<sha256[:8]>.pdf`、`dedup_suffix:true`**）＋ **校验 / 响应 / 错误码**（空体 ⇒ `400 EMPTY_BODY`；首字节非 `%PDF-` ⇒ `400 NOT_A_PDF`；超限 ⇒ **`413 PAYLOAD_TOO_LARGE`**（**边写边判、不得先写满盘**）；**错误一律结构化 JSON**；**响应恰 7 字段** `{pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}`，`pdf_path` **可直接交给 E1**）＋ **前端行为**（可见输入框改**拖放区**（可拖 / 可点击选文件 / 显示文件名＋体积）；**上传用 `XMLHttpRequest` 给进度百分比**——数百 MB 必须有进度；成功后**只读显示**服务器侧路径与「已就绪」；失败**必须可见**；新增**默认收起的「高级：手输服务器路径」**保留原输入框；**`page_range` / `chunk_size` / `rerun` / `409` 提示 / localStorage 本机记录不得改变**；**色值只走 token**）＋ **红线**（**零 DB 写、不建 job**（同 §3.14 工具端点风格）／**只落盘**／**不动 E1 与 E2〜E7**／不写 xiai、零外链）；② **§3.1 端点表新增 E8 行 ＋ 表下注（E8）一条**（**端编号裁定：登记为 E 系列的 E8，不另开「§3.19 端点」**——理由逐字见 §3.19 落位声明：E8 属 **job 体系输入面**（E1 的前置步骤）、与 E1 〜 E7 同族，须进同一「端点一览」注册表以**避免同一 job 链路两张注册表**（§3.16.3 Q5 的 spec/实现分叉教训）；§3.14 的§号形态只适用于**与 job 体系无关的工具端点**；**§3.19 仍是 E8 的细则节、不是端点号**）；③ **§3.4 错误码族随动**（**新增 `413 PAYLOAD_TOO_LARGE` 行**；**`400` 行随动**（机器码示例补 `EMPTY_BODY` / `BAD_CONTENT_TYPE`）；**表下注（v1.21）留痕**；**§3.2 S-6 加 v1.21 补注**：码族**由五码扩为六码**、**原五码枚举原文逐字保留**、`413` 不得外推到 E1 〜 E7 与 §3.14）；④ **§7 新增 AC-62 〜 AC-71（共 10 条 ⇒ AC 计数 61 → 71）**——拖曳上传全链路 / 非 PDF 判负 / 空体 / 超限（且不得先写满盘）/ 同名同内容幂等（mtime 不变）/ 同名异内容不覆盖（原文件字节不变）/ 零 DB 写（`jobs` 行数前后不变）/ E1 契约未变（原 400 · 409 逐条仍成立）/ 折叠手输仍在且默认收起 / 上传进度可见；⑤ **§9 新增待裁项 R40 〜 R41（共 2 条 ⇒ R 计数 39 → 41）**（**上传上限 512 MiB 是否合适** / **`inbox/` 清理策略（谁清、何时清）**）；⑥ **表头「版本」行 ＋ 表头「本版硬约束（v1.21）」行 ＋ §7 计数留痕（v1.21）一条 ＋ §9 计数留痕（v1.21）一条 ＋ §3.19 落位声明（v1.21）＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**本版无任何原位改写 / 收窄 / 更正；AC-01 〜 AC-61 一字未动**）。 | Jing |
| 2026-10-11 | **v1.22** | **按 §0.4 流程落 Kevin 2026-10-11 裁定「上传单文件上限默认调到 5 GiB（5368709120 B）」**（**输入**：Kevin 拖入 `~/Downloads/秦印类编 检索版.pdf`（**1.88 GiB**／**2,019,683,630 B**／**851 页**）被现上限拒（**`413 PAYLOAD_TOO_LARGE`**、`declared_bytes 2,019,683,630`、「**未落盘即拒**」），他问「这个 PDF 体积上限是多少？可以再大吗？比如 5G 以内」⇒ **裁定：上传单文件上限默认调到 5 GiB（5368709120 B）**；**本版性质 ＝ 文字同步 ＋ 结案待裁项**——§3.19.2 已明写「**改数值不需升规范**」⇒ **不新增 AC、不改任何判据逻辑**）：① **把规范里「默认 512 MiB」的现行有效处逐处同步为「默认值以 `config.UPLOAD_MAX_BYTES_DEFAULT` 为准；2026-10-11 起 ＝ 5 GiB（5368709120 B）」**——落位 **§3.4 表 `413` 行**（＋ **§3.4 表下注（v1.22）一条**）／**§3.19.2 单文件上限行**（表内 ＋ 表后留痕段）／**§3.19.7 待裁行**／**§7 AC-65**（**判据逻辑一字未改**——「大于单文件上限 ⇒ `413`」不变，**只使引用新值**），各处**逐处留痕**；② **§9 R40 结案**——标为「**已结（Kevin 2026-10-11 裁定：上限默认 5 GiB）**」，**保号留行不删行**；**依据（两本实测体积 / 页数、磁盘余量、下游代价）逐字附上**，并写明「**本次仅数值与文字同步，未新增 / 未改写任何判据**」；③ **§9 R41（`inbox/` 清理策略）仍挂起**（v1.22 复核未变）；**未新立 R42**（逐字理由见 §9（v1.22））；④ **计数结论：AC 计数不变（仍 71 条，AC-01 〜 AC-71）；R 计数不变（仍 41 条，R1 〜 R41）**（**R 39 → 41 已在前版 v1.21 发生**；**本版 R40 结案保号留行、未新增 R，故 R 计数仍 41**）；⑤ **表头「版本」行 ＋ 表头「本版硬约束（v1.22）」行 ＋ §7 计数留痕（v1.22）一条 ＋ §9 计数留痕（v1.22）一条 ＋ 本行逐处同步**；**历史行逐字保留、只增不改**（**v1.21 的「默认 512 MiB」叙述作为历史留痕原样保留**）；**只写文档（本文件一处，先存快照 `feicui/docs/versions/feicui.spec.v1.21.md`，md5 `2433b3596752be768fa47da1d3001758`、1892 行 / 583,553 B，`cmp` 逐字节一致）**；**未动任何 `.py` / `.vue` / `.js` / `.css` / `.json` / 数据文件、未动 `feicui/web/**` / `feicui/server/**`（尤其未动 Kong 并行改的 `server/app/config.py` / `server/app/routers/jobs.py`）/ `feicui/ops/**` / `feicui/exports/**` / `feicui/var/**` / `feicui/yinpu.db` / `xiai/**` / `ctrl/**`；**未跑构建 / 测试、未起服务、未占端口、未 push**） | Jing |
