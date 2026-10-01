# 玺爱（xiai）·「上传印章」数据层 + 服务层 —— 自测留证（Kong / 地基单）

- 时点：2026-09-20（本文件由自测脚本读数直接生成，非事后转述）
- 范围：`xiai/src/data/**` + `xiai/src/services/**` + `xiai/README.md`（**不做 UI**）
- 真源：`xiai/docs/xiai.spec.md` **v1.3**（md5 `f9b38957e8cdc27ad1068ab261f5b6ba`、693 行，本轮开工时只读核验）
- 自测环境：**自建 headless Chrome**（`--headless=new`，独立 profile `/tmp/xiai-selftest-profile`，`--remote-debugging-port=9333`、`--remote-allow-origins=*`），页面与产品**同源**（`http://127.0.0.1:5163`）⇒ 真实 `localStorage` / IndexedDB 读数；**未动用户自己的 Chrome**，**未停 / 未重启 5163**（核验时点 `lsof` 仍为原 PID **91247** LISTEN）。
- 自测载体：临时页面 `src/data/__xiai_selftest__.html`（跑完即删，不入库）；报告经本地回环监听器（`127.0.0.1:8791`）落盘为 `kong_xiai_upload_seal_selftest_raw.json`。
- 环境读数：origin `http://127.0.0.1:5163`、`crypto.subtle` 可用 `True`、影像库 `{'available': True, 'db': 'xiai:v1:assetblobs', 'version': 1, 'store': 'assets'}`

## 1. 改动文件（改前 / 改后 md5）

| 文件 | 改前 md5 | 改后 md5 | 说明 |
| --- | --- | --- | --- |
| `src/data/db.js` | `03e9276d264dff20b1f4f22d4c0aad2e` | `4c7328baa871c13c51bfc11f2ce343b5` | 影像二进制数据层出口 + 五类写权限拒绝 + 必填校验 + 防重 + `source/uploaded_by/created_at` |
| `src/data/blobstore.js` | 新增（原不存在） | `d2cbe0f7c6ce6b4c678830e5bf494dc4` | **全工程唯一**碰 IndexedDB 的模块 |
| `src/data/assetmeta.js` | 新增（原不存在） | `b5ea832a829352339af05a48756ecb53` | 纯函数：sha256 / dataURL↔字节 / 图像尺寸与色彩模式 |
| `src/services/seals.js` | `330f8879eac1c4019fa781659ccd4fdf` | `21a10a766947b18d6354c478366d07eb` | 冻结 API ①②（`createSealWithFace` / `updateSealFixedAttributes`）+ `loadImageDataUrl` / `canUploadSeal` / 筛选项 |
| `src/services/corrections.js` | `487aeb8b947deb626e7bbe7306a258e7` | `dfd7b1296511eb8610b6d70e32aadfd7` | 冻结 API ③④（`listPendingForAdmin` / `review`）+ `canReviewCorrections`；`reviewCorrection` 保留为兼容包装 |
| `README.md` | `c397366e953d486d3fed60651c1743de` | `4ab3975e8ec9eeca8b32261967203f9d` | 能力表第 6 行 / 影像存储口径 / 冻结 API 一句话说明 / 目录 |

**未改动（md5 与开工时一致）**：`src/data/seed.js` `cc7f7b52…`、`src/data/storage.js` `916c7097…`（**命名空间 `xiai:v1:` 未动、未清库**）、`src/data/session.js`、`src/services/{admin,auth,bootstrap,photos,points,index}.js`（`index.js` 未改即在统一出口可见，因 `seals` / `corrections` 命名空间本就在门面里）；`src/views/**`、`src/components/**`、`src/router/**`、`docs/**`、`feicui/**`（本文件除外）、`yinsuo/**`、`web/**`、`index.html`、`vite.config.js`、`package.json` **一字未动**。

## 2. 冻结 API 清单（UI 单按此名调用，**不得改名**）

| # | 函数 | 入参 | 返回 | 异常 / 拒绝 |
| --- | --- | --- | --- | --- |
| ① | `seals.createSealWithFace(actor, payload)` **async** | `actor`（须管理员；缺省回落到登录态）；`payload`: `name`* / `dynasty`* / `type`*（也接受 `category`、`seal_type`）/ `material` / `author` / `transcription` / `transcription_simplified` / `seal_style` / `faceImage`*（二进制或 `data:image/...;base64,…`）/ `edgeImage`（可选） | `{ ok, deduped, id, stampId, faceId, seal, face, faces, images, message }`（`seal`/`face` 为视图模型，`images` 为影像**元数据**行） | 非管理员 ⇒ `{ok:false, reason:'PERMISSION_DENIED'}`；必填缺失 ⇒ `{ok:false, reason:'MISSING_REQUIRED', missing:[…]}`；重复上传 ⇒ `ok:true, deduped:true`（不算失败）。**不抛未捕获异常** |
| ② | `seals.updateSealFixedAttributes(actor, faceId, patch)` | `patch` 仅限 `face_image_id` / `material` / `edge_image_ids` | `{ ok, face, message }` | 非管理员 ⇒ `PERMISSION_DENIED`；越界字段 / 印面不存在 ⇒ `{ok:false, reason:'ERROR', message}`（同义能力 `admin.updateFaceFixedAttributes` 仍在，出错即抛 `PermissionError`，勿改） |
| ③ | `corrections.listPendingForAdmin(actor)` | `actor`（须管理员） | `Array<correction>`：**全部用户**的 `PENDING`，按提交时间倒序 | 非管理员 ⇒ **返回 `[]`**；数据层 `db.listPendingCorrectionRowsForAdmin` 同口径**拒绝**（抛 `PermissionError`）—— 两条路径都不给出任何数据 |
| ④ | `corrections.review(actor, correctionId, decision)` | `decision` ∈ `'ACCEPTED' | 'REJECTED'`（旧字面值 `'APPROVED'` 归一为采纳） | `{ ok, status, accepted, reward, row, message }`；采纳 ⇒ 提交者 +10 金、**只奖一次** | 非管理员 ⇒ `PERMISSION_DENIED`；已审过 ⇒ `{ok:false, reason:'ALREADY_REVIEWED'}`；找不到 ⇒ `NOT_FOUND` |
| 附 | `seals.loadImageDataUrl(imageId)` **async** | 影像 id | `{ ok, dataUrl, bytes, meta }`（**仅供运行时渲染**） | 影像不存在 ⇒ `{ok:false, reason:'NOT_FOUND'}`；IndexedDB 不可用 ⇒ `UNAVAILABLE` |
| 附 | `seals.canUploadSeal(actor?)` / `corrections.canReviewCorrections(actor?)` | — | `boolean`（供页面决定按钮是否**渲染**；**不等于**数据层拦截） | — |
| 附 | `seals.listDynastyOptions()` / `seals.listSealTypeOptions()` | — | 广场筛选选项（**由已入库数据派生**，新上传的朝代 / 分类立即出现在筛选条） | — |

全部经 `src/services/index.js` 门面可达（`services.seals.*` / `services.corrections.*`），**`index.js` 无需改动即成立**。

**数据层五类写（AC-30 的直调面）**：`db.insertSealRow(actor,p)` / `db.insertFaceRow(actor,p)` / `db.insertImageRow(actor,p)` / `db.writeFaceFixedAttributes(actor,faceId,patch)` / `db.writeCorrectionDecision(actor,id,decision)`（+ `db.listPendingCorrectionRowsForAdmin(actor)`）——**非管理员一律抛 `PermissionError`**（结构化拒绝信号，非静默放行）。

## 3. 防重键口径（实现自选，规范只要求可机械判负）

1. **印面级**：`(sealId, kind, sha256(印面图二进制))` —— 同一印章 · 同一类别 · 同一图内容 ⇒ 语义等价的印面**只保留 1 个**（`insertFaceRow` 返回 `deduped:true`，不新增印面行）。
2. **印章级**：`(名称, 朝代, 分类, sha256(印面图))` —— 整枚印章语义等价的重复提交（同一张图再点一次「上传印章」）不新增（`createSealWithFace` 返回 `deduped:true` + 既有 `stampId`）。
3. **二进制级**：IndexedDB 键 `asset:<影像 id>`；同一印章同 `sha256` 命中既有影像行时**复用该行**，不重复写二进制（`insertImageRow` 返回 `deduped:true`）。
4. 判重全部在**数据层**：UI 按钮置灰 / 禁用不构成防重（AC-35 判负形态）。

## 4. 六条自测真实输出（浏览器内跑，非读码推断）

### 4.1 AC-28（数据层部分）：`source='manual'` / `uploaded_by` / `created_at` + 广场筛选维度

- 测试图：1400×1400 PNG（canvas 造，**325178 字节**，> 200 KiB；`dataURL` 长度 433594）
- 新建结果：`stampId=XAI-0009`、`faceId=fc-0009-f1`、`ok=True`、影像元数据 1 条
- 落位读数：`source=manual`、`uploaded_by=u-16601061656`、`created_at=2026-09-20T08:24:19.481Z`、`stamp_id=XAI-0009`（id 不与既有冲突：印章数 8 → 9）
- 广场筛选（**页面侧入参形态** `seals.listSeals({dynasty, sealType, keyword})` → 返回集合）：`S_清=4`、`S_私印=5`、`S_组合=2`、`S_all=9`；三者**均含新印章**，组合 = 两条件交集；换到 `漢` / `官印` 时**不含**新印章（用例具备判负能力）。

| 判据 | 结论 | 读数 |
| --- | --- | --- |
| AC-33-setup: 测试图 > 200 KiB 且为真实尺寸 PNG | ✅ 过 | `325178 bytes` |
| AC-28: 新增成功（ok + 印章 + 印面 + 影像） | ✅ 过 | `ok=true stampId=XAI-0009 faceId=fc-0009-f1` |
| AC-28 数据层部分: source=manual / uploaded_by / created_at 均落位 | ✅ 过 | `{"source":"manual","uploaded_by":"u-16601061656","created_at":"2026-09-20T08:24:19.481Z"}` |
| AC-28: 新印章 id 不与既有冲突且计数 +1 | ✅ 过 | `8 → 9` |
| AC-28: 广场按朝代筛选命中新印章（S_清 ≠ S_all 且含新印章） | ✅ 过 | `S_清=4 S_all=9` |
| AC-28: 广场按分类筛选命中新印章（S_私印 ≠ S_all 且含新印章） | ✅ 过 | `S_私印=5 S_all=9` |
| AC-28: 朝代∩分类组合筛选 = 交集 且命中新印章 | ✅ 过 | `S_组合=2` |
| AC-28: 换到别的朝代/分类时集合真的改变（用例具备判负能力） | ✅ 过 | `S_漢=2 S_官印=1` |
| AC-33①: localStorage 无单值 ≥ 64 KiB（65,536 字符） | ✅ 过 | `max=5329 key=xiai:v1:faces` |
| AC-33②: localStorage 总量 < 512 KiB | ✅ 过 | `total=11306 chars` |
| AC-33④: localStorage 内无 data:image/ 长串 | ✅ 过 | `hits=[]` |
| AC-33③: IndexedDB 内可读回二进制且字节数 > 0 | ✅ 过 | `ok=true bytes=325178` |
| AC-33③: 读回二进制与上传字节逐字节一致 + sha256 与元数据一致 | ✅ 过 | `identical=true idbSha=1b705131741afe95… metaSha=1b705131741afe95…` |
| AC-34a: 缺名称 ⇒ 拒绝 + 可读提示 + 无半成品记录 | ✅ 过 | `{"reason":"MISSING_REQUIRED","missing":["名称"],"message":"请补全必填项：名称"}` |
| AC-34b: 缺朝代 ⇒ 拒绝 + 可读提示 + 无半成品记录 | ✅ 过 | `{"reason":"MISSING_REQUIRED","missing":["朝代"],"message":"请补全必填项：朝代"}` |
| AC-34c: 缺分类 ⇒ 拒绝 + 可读提示 + 无半成品记录 | ✅ 过 | `{"reason":"MISSING_REQUIRED","missing":["分类"],"message":"请补全必填项：分类"}` |
| AC-34d: 缺印面图 ⇒ 拒绝 + 可读提示 + 无半成品记录 | ✅ 过 | `{"reason":"MISSING_REQUIRED","missing":["印面图"],"message":"请补全必填项：印面图"}` |
| AC-35: 重复「上传印章」⇒ deduped + 计数不增（印章/印面/影像均不变） | ✅ 过 | `{"ok":true,"deduped":true,"stampId":"XAI-0009","message":"该印章与印面图此前已上传，本次未重复新增"}` |
| AC-35: 同印章重复上传同一张印面图 ⇒ 印面只 1 个、FACE 计数不增、有明确提示 | ✅ 过 | `{"faces":1,"msg":"该印面已存在（同一印章 · 同一类别 · 同一图），本次未重复新增"}` |
| AC-35: 影像二进制不重复落库（同印章同 sha 复用既有影像行） | ✅ 过 | `images 14 → 14` |
| AC-30（普通用户·服务层）: 五类写 ⇒ 结构化拒绝 ok:false 且无未捕获异常 | ✅ 过 | `[{"l":"服务层 services.seals.createSealWithFace","ok":false,"r":"PERMISSION_DENIED"},{"l":"服务层 services.seals.updateSealFixedAttributes","ok":false,"r":"PERMISSION_DENIED"},{"l":"服务层 services.corrections.review","ok":false,"r":"PERMISSION_DENIED"}]` |
| AC-30（普通用户·数据层）: 五类写 ⇒ PermissionError（结构化拒绝信号） | ✅ 过 | `[{"l":"数据层 db.insertSealRow","thrown":true,"name":"PermissionError"},{"l":"数据层 db.insertFaceRow","thrown":true,"name":"PermissionError"},{"l":"数据层 db.insertImageRow","thrown":true,"name":"PermissionError"},{"l":"数据层 db.writeFaceFixedAttributes","thrown":true,"name":"PermissionError"},{"l":"数据层 db.wr` |
| AC-30（普通用户）: 调用前后计数 / 固定属性原值 / 勘误状态逐项不变 | ✅ 过 | `{"before":{"seals":9,"faces":14,"facesFACE":10,"images":14,"corrections":1,"points":0},"after":{"seals":9,"faces":14,"facesFACE":10,"images":14,"corrections":1,"points":0},"material":"壽山石","status":"PENDING"}` |
| AC-30（游客）: 五类写全部被拒（服务层结构化 / 数据层 PermissionError） | ✅ 过 | `[{"l":"服务层 createSealWithFace(null)","thrown":false},{"l":"服务层 updateSealFixedAttributes(null)","thrown":false},{"l":"服务层 corrections.review(null)","thrown":false},{"l":"数据层 insertSealRow(null)","thrown":true,"name":"PermissionError"},{"l":"数据层 insertFaceRow(null)","thrown":true,"name":"PermissionEr` |
| AC-30（游客）: 计数逐项不变；listPendingForAdmin(非管理员) = 空 | ✅ 过 | `{"before":{"seals":9,"faces":14,"facesFACE":10,"images":14,"corrections":1,"points":0},"after":{"seals":9,"faces":14,"facesFACE":10,"images":14,"corrections":1,"points":0}}` |
| 审核闭环: 管理员看到全部用户 PENDING + 采纳 +10 且只奖一次 | ✅ 过 | `{"pendingForAdminLen":1,"pendingIsAllUsers":true,"first":{"ok":true,"status":"ACCEPTED","reward":{"ok":true,"awarded":true,"balance":60,"message":"已奖励 10 金"}},"second":{"ok":false,"reason":"ALREADY_REVIEWED","message":"该勘误已审核，不可重复处理"},"submitterPoints":{"before":50,"after":60,"delta":10},"rewardLedg` |
（上表含 AC-28 / AC-33 / AC-34 / AC-35 / AC-30 / 审核闭环全部断言；phase1 计 **26/26**）

### 4.2 AC-33：`localStorage` 只存元数据、二进制实落 IndexedDB

- `localStorage` 逐 key 读数：`[["xiai:v1:faces", 5329], ["xiai:v1:seals", 2547], ["xiai:v1:photos", 2], ["xiai:v1:corrections", 2], ["xiai:v1:downloaded", 2], ["xiai:v1:users", 249], ["xiai:v1:session", 26], ["xiai:v1:seeded", 25], ["xiai:v1:images", 2975], ["xiai:v1:points", 2]]`
- **单值最大 = 5329 字符**（键 `xiai:v1:faces`）< 65,536 ⇒ **无单值 ≥ 64 KiB**
- **总量 = 11306 字符** < 524,288 ⇒ **< 512 KiB**
- `data:image/` 长串命中：`[]`（空）
- IndexedDB 键：`['asset:img-0009f']`；读回字节 **325178 字节**，与上传字节**逐字节一致 `identical=True`**
- 摘要交叉校验（页面用 `crypto.subtle` 独立算、与实现内的纯 JS sha256 互为对照）：`idbSha=1b705131741afe95c4e483a07e312627d05bbe726b44eb5822daa0205c5f50b2` == 元数据 `sha256=1b705131741afe95c4e483a07e312627d05bbe726b44eb5822daa0205c5f50b2` ✅（**此对照曾抓出实现内 sha256 的字节序 bug，已修**）
- 影像元数据行（只标量，无内容）：`{"id": "img-0009f", "assetId": "img-0009f", "stamp_id": "XAI-0009", "sealId": "XAI-0009", "ownerType": "face", "ownerId": "fc-0009-f1", "kind": "FACE", "sha256": "1b705131741afe95c4e483a07e312627d05bbe726b44eb5822daa0205c5f50b2", "bytes": 325178, "width": 1400, "height": 1400, "colorMode": "RGB", "color_mode": "RGB", "mime": "image/png", "storage": "indexeddb", "storage_key": "asset:img-0009f", "source": "manual", "uploaded_by": "u-16601061656", "created_at": "2026-09-20T08:24:19.602Z"}`

### 4.3 AC-34：canonical 必填缺失即拒 + 无半成品

[
  {
    "id": "AC-34a: 缺名称",
    "ok": false,
    "reason": "MISSING_REQUIRED",
    "missing": [
      "名称"
    ],
    "message": "请补全必填项：名称",
    "countsStable": true,
    "counts": {
      "seals": 9,
      "faces": 14,
      "facesFACE": 10,
      "images": 14,
      "corrections": 0,
      "points": 0
    }
  },
  {
    "id": "AC-34b: 缺朝代",
    "ok": false,
    "reason": "MISSING_REQUIRED",
    "missing": [
      "朝代"
    ],
    "message": "请补全必填项：朝代",
    "countsStable": true,
    "counts": {
      "seals": 9,
      "faces": 14,
      "facesFACE": 10,
      "images": 14,
      "corrections": 0,
      "points": 0
    }
  },
  {
    "id": "AC-34c: 缺分类",
    "ok": false,
    "reason": "MISSING_REQUIRED",
    "missing": [
      "分类"
    ],
    "message": "请补全必填项：分类",
    "countsStable": true,
    "counts": {
      "seals": 9,
      "faces": 14,
      "facesFACE": 10,
      "images": 14,
      "corrections": 0,
      "points": 0
    }
  },
  {
    "id": "AC-34d: 缺印面图",
    "ok": false,
    "reason": "MISSING_REQUIRED",
    "missing": [
      "印面图"
    ],
    "message": "请补全必填项：印面图",
    "countsStable": true,
    "counts": {
      "seals": 9,
      "faces": 14,
      "facesFACE": 10,
      "images": 14,
      "corrections": 0,
      "points": 0
    }
  }
]

（每条：`reason=MISSING_REQUIRED`、`missing` 恰为 1 项、文案「请补全必填项：X」、**调用前后 印章/印面/影像 计数逐项不变** ⇒ 无半成品）

### 4.4 AC-35：防重

{"ok": true, "deduped": true, "stampId": "XAI-0009", "message": "该印章与印面图此前已上传，本次未重复新增"}
- 同印章再传同一张图（`db.insertFaceRow`）：`deduped=True`，提示「该印面已存在（同一印章 · 同一类别 · 同一图），本次未重复新增」
- 同印章再传同一张影像（`db.insertImageRow`）：`deduped=True`，提示「该影像此前已上传（内容相同），已复用既有影像，未重复落库」
- 该印章 FACE 印面数 = **1**（不增），影像行 **14 → 14**（不增），`source=manual` 印章数不增

### 4.5 AC-30：非管理员直调五类写全部被拒（独立要求 ②）

**普通用户（13800000002，`role=user`）**
[
  {
    "label": "服务层 services.seals.createSealWithFace",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以上传印章（新增进藏品库）"
    }
  },
  {
    "label": "服务层 services.seals.updateSealFixedAttributes",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以修改印面的固定属性"
    }
  },
  {
    "label": "服务层 services.corrections.review",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以审核勘误"
    }
  },
  {
    "label": "数据层 db.insertSealRow",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以上传印章（新增进藏品库）"
  },
  {
    "label": "数据层 db.insertFaceRow",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以在印章下新增印面"
  },
  {
    "label": "数据层 db.insertImageRow",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以上传印面图"
  },
  {
    "label": "数据层 db.writeFaceFixedAttributes",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以修改印面的固定属性"
  },
  {
    "label": "数据层 db.writeCorrectionDecision",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以审核勘误"
  },
  {
    "label": "数据层 db.listPendingCorrectionRowsForAdmin",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以查看全部用户的待审勘误"
  }
]
- **计数逐项不变（`countsStable=true`）**：调用前后 `{"seals": 9, "faces": 14, "facesFACE": 10, "images": 14, "corrections": 1, "points": 0}` **全等**（报告里 before/after 两串逐字节相同）
- 固定属性原值 `material` 仍为「壽山石」、勘误仍为 `PENDING`（`correctionStillPending=true`）、`listPendingForAdmin(普通用户)` = 0 条（空）

**游客（未登录，显式 `null` actor）**
[
  {
    "label": "服务层 createSealWithFace(null)",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以上传印章（新增进藏品库）"
    }
  },
  {
    "label": "服务层 updateSealFixedAttributes(null)",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以修改印面的固定属性"
    }
  },
  {
    "label": "服务层 corrections.review(null)",
    "thrown": false,
    "value": {
      "ok": false,
      "reason": "PERMISSION_DENIED",
      "message": "仅管理员可以审核勘误"
    }
  },
  {
    "label": "数据层 insertSealRow(null)",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以上传印章（新增进藏品库）"
  },
  {
    "label": "数据层 insertFaceRow(null)",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以在印章下新增印面"
  },
  {
    "label": "数据层 insertImageRow(null)",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以上传印面图"
  },
  {
    "label": "数据层 writeFaceFixedAttributes(null)",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以修改印面的固定属性"
  },
  {
    "label": "数据层 writeCorrectionDecision(null)",
    "thrown": true,
    "name": "PermissionError",
    "message": "仅管理员可以审核勘误"
  }
]
- 计数不变 `True`；`listPendingForAdmin(null) = 空`：`True`
- **无未捕获异常**：服务层全部返回结构化 `{ok:false}`，数据层全部 `PermissionError`（可捕获的结构化信号）

**审核闭环（管理员，附证 §7.4 奖励只发一次）**：`{"pendingForAdminLen": 1, "pendingIsAllUsers": true, "first": {"ok": true, "status": "ACCEPTED", "reward": {"ok": true, "awarded": true, "balance": 60, "message": "已奖励 10 金"}}, "second": {"ok": false, "reason": "ALREADY_REVIEWED", "message": "该勘误已审核，不可重复处理"}, "submitterPoints": {"before": 50, "after": 60, "delta": 10}, "rewardLedgerCount": 1, "notFound": {"ok": false, "reason": "NOT_FOUND", "message": "未找到该勘误"}}`

### 4.6 `npm run build`

```
✓ built in 876ms   （dist/ 产出正常；UI 未改，构建未受影响）
```
> 注：本轮的 `vite build` 仍会打进既有的 `AdminView` 等页面（`/admin` 退役属**下一轮 UI 单**），因此产物里仍能看到 `AdminView-*.js` —— **不属于本单范围**。

### 4.7 附加（第二轮页面加载，AC-31 同族）：重载后仍在

| 判据 | 结论 | 读数 |
| --- | --- | --- |
| 重载后: 上传的印章仍在（source=manual 的记录未丢） | ✅ 过 | `[{"stamp_id":"XAI-0009","seal_name":"自測上傳印","dynasty":"清","seal_type":"私印","uploaded_by":"u-16601061656","created_at":"2026-09-20T08:24:19.481Z"}]` |
| 重载后: 印面仍在（含 FACE 与 face_image_id 指向） | ✅ 过 | `[{"id":"fc-0009-f1","kind":"FACE","face_image_id":"img-0009f"}]` |
| 重载后: 印面图二进制仍能从 IndexedDB 读回且摘要一致（非空态 / 非破图） | ✅ 过 | `{"ok":true,"bytes":325178,"sha256":"1b705131741afe95c4e483a07e312627d05bbe726b44eb5822daa0205c5f50b2","metaSha":"1b705131741afe95c4e483a07e312627d05bbe726b44eb5822daa0205c5f50b2"}` |
| 重载后: 服务层能取回可渲染的影像（loadImageDataUrl） | ✅ 过 | `{"ok":true,"dataUrlHead":"data:image/png;base64,","dataUrlLength":433594}` |
| 重载后: 广场按朝代 / 朝代∩分类仍筛得到该印章 | ✅ 过 | `{"byDynasty":["XAI-0005","XAI-0006","XAI-0007","XAI-0009"],"combo":["XAI-0005","XAI-0009"],"total":9}` |
| 重载后: localStorage 仍无单值 ≥ 64 KiB、总量 < 512 KiB、无 data:image/ 长串 | ✅ 过 | `{"max":{"key":"xiai:v1:faces","length":5329,"hasDataImage":false},"total":11742}` |
| 重载后: 勘误终态与奖励流水仍在（ACCEPTED + 1 笔奖励） | ✅ 过 | `{"corrections":[{"id":"cr-mu9jvj5m-pt1hx","status":"ACCEPTED","rewarded_at":"2026-09-20T08:24:19.643Z"}],"rewards":1}` |
（phase2 计 **7/7**；同一 profile、同一存储命名空间，**另一次页面加载**；二进制仍可读回、摘要一致、`loadImageDataUrl` 可取回 `data:image/png;base64,…`、广场仍筛得到、`localStorage` 阈值仍达标）

## 5. 未完成项（**如实登记**）

1. **UI 一行未动**（本单范围外）：藏品广场的「上传印章」按钮、详情页「编辑固定属性」按钮的入口迁移、`/my/corrections` 的「采纳 / 驳回」按钮、`/admin` 路由与 `AdminView` 退役、左侧菜单 5 → 4 项 ⇒ **全部属下一轮 UI 单**（AC-29 / AC-36 / AC-37 的入口面未做，故本单**不声称**这些 AC 通过）。
2. **实物照片仍以 dataURL 落 `localStorage`**（`services/photos.js` 既有实现，`PHOTO_MAX_LENGTH = 400 KB`）⇒ **与 AC-33 的「单值 ≥ 64 KiB 即判负」阈值相冲突**：若在 AC-33 检查前上传过一张 > 64 KiB 的**实物照片**，`localStorage` 会立刻越线（本轮 AC-33 自测只按 AC-28 流程上传**印面图**，未走照片路径，故读数干净）。**本轮未改照片路径**：它不在本单范围（须同时改照片上传与画廊 / `/my/photos` 的渲染面，属 UI 单或另开一单）。
3. 照片 / 印面图的**渲染**（`<img>` 实际显示 IndexedDB 里的二进制）未接：现有详情页仍按「演示数据不含真实图象」的占位口径渲染影像元数据；接入点在 `seals.loadImageDataUrl(imageId)`（已提供，UI 单可直接用）。
4. 数据层未做**容量上限 / 配额**保护（IndexedDB 写入失败会返回 `UNAVAILABLE` / `FAILED` + 可读提示并回滚，但没有「单张最大字节数」的产品级上限）；照片侧有 400 KB 上限、印面图侧**无**上限。

## 6. 规范缺口 / 需裁定（交 Zang / Jing）

1. **AC-33 与实物照片口径冲突（最需处理）**：§4.1.3 表下注把「影像二进制走 IndexedDB」写成**影像**的通用口径，但 AC-33 的阈值是**整库**判定（单值 ≥ 64 KiB 即判负）；而 `photo`（§4.1.7）当前实现把 `data:image/...;base64,…` 整串存进 `localStorage`，上限 400 KB ⇒ **「上传过实物照片」这一常驻状态下 AC-33 必判负**（与是否上传印面图无关）。建议：把 `photo.image` 也改走 IndexedDB（元数据行改为 `image_id` 引用），或明确 AC-33 只对**印面 / 边款影像**生效并在 §4.1.7 表下注写明照片例外。**本轮未擅自改**（会牵动照片渲染面）。
2. **上传印章的「朝代 / 分类」取值面未定**：本实现**允许任意非空文本**（不锁死 seed 常量表）。广场筛选条是**由已入库数据派生**的（`SquareView` 用 `listSeals()` 的 distinct 值），所以新值能被筛到；但若 UI 单改用固定下拉（`seed.js` 的 `DYNASTY_OPTIONS` / `SEAL_TYPE_OPTIONS`，**当前全工程无任何页面引用**），则界面里选不到新值 ⇒ 建议规范明确：**上传印章的朝代 / 分类用「数据派生的下拉」（`seals.listDynastyOptions()` / `listSealTypeOptions()`）**，而不是 seed 常量表。
3. **`seal.name` 必填与 §4.1.1 的「名称（可空）」字面冲突**：§4.1.1 表把 `name` 标为**可空**，而 v1.3 §3.6 表下注 3 / AC-34 要求「缺印章名称等其它 canonical 必填项」即拒。本单按「上传印章这条写路径必填」实现（**仅新增路径**校验，既有种子 / 斐萃汇入记录不受影响）⇒ 建议在 §4.1.1 表下注补一句「`name` 在 `source='manual'` 的新增路径上为必填」。
4. **`source` 字段在印面 / 影像行上的语义**：§4.1.1 只冻结了**印章**的 `source='manual'`；印面行原有的「来源追踪（可空）」在种子里是**对象**（`{book,page}`）。本实现把新增的印面 / 影像行也标 `source:'manual'`（字符串）⇒ 同一字段出现「对象 / 字符串」两形态，建议规范明确二者关系（或给印面 / 影像另立字段名）。
5. **AC-30 的「五类写」在服务层的返回形态未统一**：本单新增的四个冻结 API 一律**结构化返回**（`{ok:false, reason, message}`），而既有的 `admin.updateFaceFixedAttributes` 仍是**抛 `PermissionError`**。两条都满足「明确拒绝信号、不静默、不抛未捕获异常」，但形态不一 ⇒ 建议规范（或 UI 单）指定统一形态；本轮为**不破坏既有页面**保留了两者并存。
6. **`review` 的 `rewarded_at` 与失败回滚**：采纳时「写状态 → 发奖 → 标 `rewarded_at`」是三步，若最后一步失败，奖励已实际发放但 `rewarded_at` 为空（本实现以**流水**为幂等真源，故不重复发奖）。规范 §7.4 只要求「只奖一次」，未规定标记失败时的口径 ⇒ 已按「以流水为准」处理，登记备查。
7. **`blobstore` 的库名 / 键口径未登记**：`xiai:v1:assetblobs`（store `assets`）、键 `asset:<影像 id>` 属实现自定；若规范希望冻结（便于跨单核对），建议在 §4.1.3 表下注登记一句。

## 7. 红线自查

- **未**改 `storage.js` 命名空间版本号（`xiai:v1:` 原样）、**未**清库、**未**动用户数据（种子只做加法）。
- **未**停 5163（自测期间 `lsof` 仍为原 node PID **91247** LISTEN）；**未**占 5173 / 5174；**未**用 `pkill -f` / `killall`（只 `kill` 自己起的 Chrome / 监听器 PID）。
- **未**动用户自己的 Chrome（自建 headless + 独立 profile `/tmp/xiai-selftest-profile`，用后已删）。
- **未**新增第三方依赖（sha256 / 图像尺寸解析自持；IndexedDB 用原生 API）。
- 只改 `xiai/src/data/**`、`xiai/src/services/**`、`xiai/README.md`（+ 本证据目录）；`docs/**`、`views/**`、`components/**`、`router/**`、`feicui/**`（本目录除外）、`yinsuo/**`、`web/**`、`index.html`、`vite.config.js`、`package.json` **一字未动**。
