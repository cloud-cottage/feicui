# 玺爱（xiai）·「重新上传印面图」留证报告（Kong / 工程师）

- 单号口径：在 `/seal/:id` 为**每个印面**加管理员专属「重新上传印面图」按钮；复用浏览器端影像管线（≤1MB → 方形取景 → WebP）；**原子**新增影像 + 改印面指向；**旧影像保留**；非管理员 DOM 零命中 + 数据层拒绝越权。
- 开工/收工：2026-09-20 17:2x → 18:0x（CST）
- 环境：工程根 `/Users/kevin/bistro/xiai`，dev server `http://127.0.0.1:5163`（**PID 91247，全程未停**）
- 取证方式：① node 层 Vite SSR 载入**真实模块**（绕过 UI 直调服务层 / 数据层）；② 自建 headless Chrome（独立 profile `/tmp/xiai-kong5-prof`、端口 9434、`--remote-allow-origins=*`）真登录 · 真选图 · 真上传 · 真拖拽（CDP Input 域真鼠标事件）。

## 1. 改动文件与 md5（只改 3 个文件，均在授权范围内）

| 文件 | 改前 md5 | 改后 md5 |
|---|---|---|
| `src/data/db.js` | `4f76c269326cf7ff9f9b07395ff6ce3d` | `431ed332e4fbb1390ece986abd28a3bb` |
| `src/services/seals.js` | `0045dd67cf400e9bc983a2eb2f4045bb` | `53864a433c94501d65d22baf9a8a84b9` |
| `src/views/SealDetailView.vue` | `b23e6e7e328bd881c113ebfaba9816d5` | `5653cebea33cdf2822d23278637d9d86` |
| `src/utils/image.js`（**只调不改**） | `c88d7fac07abd73dd1f5366ec1d6d28f` | `c88d7fac07abd73dd1f5366ec1d6d28f`（未变） |

改动要点：
- **数据层** `replaceFaceImage(actor, faceId, imageInput)`：权限（非管理员 ⇒ `{ok:false, reason:'FORBIDDEN'}`，**零写入**）→ 解析影像（不过即拒、一行不写）→ 快照 → 新增影像行（`kind` 取印面自身类别 ⇔ 印面为 `FACE` 时即 `FACE`）+ 二进制 → **回读校验新行确实落盘** → 写印面 `face_image_id`；任一步失败**回滚**（集合还原 + 删**本次新增行**的二进制，含「行未落盘」时的裸键清理）。旧行 / 旧二进制全程不动。
- **服务层** `canReplaceFaceImage(actor?)`（管理员判定）与 `replaceFaceImage(faceId, {bytes, mime?, width, height})`：兜 1 MB（`IMAGE_LIMITS.maxInputBytes`＝入库字节）、按**字节魔数**判格式（不采信声称 mime）、返回结构化 `{ok, reason, message, face, faceImageId, previousFaceImageId}`，**不抛未捕获异常**；`face` 为替换后的视图模型（`faceImage` 立即指向新影像）。
- **UI** `SealDetailView.vue`：每个 `face-block` 加 `data-admin-action="replace-face-image"` 按钮（`v-if` 权限，与「编辑固定属性」同粒度）；弹窗复用 `utils/image.js` 的 `loadImageFile` / `exportSquareImage` / `IMAGE_LIMITS` / `MIN_CROP_SIDE`（**未自写 canvas 处理**），预览 + 可拖拽/缩放方形取景框 + 1 MB 上限提示；提交后按**新影像编号**经服务层取回二进制**立即渲染（无需刷新）**，并如实反馈「影像编号 旧 → 新」。

非授权文件确认未改：`src/utils/image.js` md5 未变；其余禁改文件 mtime 均早于本次开工（本单 3 个文件的 mtime 为 17:55–17:58，禁改文件中最晚的是 17:38，且非本会话所写）。

## 2. 五条自测（真跑）

### ① 权限两道门 —— PASS
- **DOM 门**（headless Chrome 真登录）：
  - 管理员 `16601061656`（role=admin）：`/seal/XAI-0001` 上 `.face-block` = **3**，`[data-admin-action="replace-face-image"]` = **3**（face_id 依次 `fc-0001-f1` / `fc-0001-f2` / `fc-0001-e1`，与印面块 id 一一对应；与 `edit-fixed-attributes` 数量相同＝同粒度），按钮文案均为「重新上传印面图」。
  - 游客（未登录）：`replace = 0`、`edit = 0`、正文文案命中 `false`。
  - 普通用户 `13800000001`（旧管理员号，已降为 `user`）：`blocks=3` 但 `replace = 0`、`[data-admin-action]` 合计 = **0**、弹窗 = 0、`body.innerText` 与 `body.innerHTML` 均零命中 `replace-face-image`。
- **数据层门**（绕过 UI，node 层 + 页内直调真实模块，用普通用户会话）：
  - node：`seals.replaceFaceImage('fc-0001-f1', …)` ⇒ `{ok:false, reason:'FORBIDDEN', message:'仅管理员可以重新上传印面图'}`；越权前后读数 **images 13 / faces 13 / seals 8 / blobs 0 → 13 / 13 / 8 / 0**，`face_image_id` 恒为 `img-0001f`。
  - node：数据层直调（actor=普通用户 / actor=null 游客）同样 `FORBIDDEN`，库零变化。
  - 浏览器页内：服务层 ⇒ `FORBIDDEN`；数据层 ⇒ `FORBIDDEN`；前后 `{face_image_id:'img-0001f-3', image_count:15, blob_keys:['asset:img-0001f-2','asset:img-0001f-3']}` **完全一致**。
  - `canReplaceFaceImage`：管理员 `true` / 普通用户 `false` / 游客 `false`。

### ② 端到端替换（3000 × 1200 非方形） —— PASS
- 选图读数：`已选 selftest-3000x1200.jpg · 原图 3000 × 1200 · 原文件 104.7 KB ⇒ 入库印面 1200 × 1200 · image/webp · 15.0 KB（最长边 ≤ 2048px、质量 0.85）`（原文件 107232 B ≤ 1 MB；提示文案「单张不超过 1.00 MB（1048576 字节）」）。
- 取景框可**真拖拽**（CDP 真鼠标按下/移动/抬起）：`left 72px → 114px`、宽高恒 `96px × 96px`，导出读数仍为 `1200 × 1200 · image/webp`。
- 提交反馈：`印面图已替换：影像编号 img-0001f → img-0001f-2；旧影像行与二进制保留未删。新影像 1200 × 1200 · image/webp · 14366 字节`。
- 库读数：`image_count 13 → 14`；新行 `{id:'img-0001f-2', kind:'FACE', stamp_id:'XAI-0001', width:1200, height:1200, bytes:14366, mime:'image/webp'}`（**width == height**、mime = `image/webp`）；`face_image_id` = `img-0001f-2`；旧行 `img-0001f` 元数据与基线**逐字一致**；二进制键 `asset:img-0001f-2` 存在且长度 = 行内 `bytes` = 14366。
- **不刷新即显示新图**：提交后同页（页内标记 `no-reload-1789898522300` 未丢 ⇒ 未发生导航/刷新）图注 = `印面影像 img-0001f-2`、`img.naturalWidth > 0`、固定属性 dd = `影像编号 img-0001f-2`。
- **旧影像保留（②′ 二次替换）**：第二次反馈 `影像编号 img-0001f-2 → img-0001f-3`（新行 `320 × 320 · image/webp · 2006 字节`）；第一次的**行** `img-0001f-2` 仍在 `image_ids` 且元数据未改，**二进制** `asset:img-0001f-2` 仍在且字节 **14366 与原值一致**；`image_count 14 → 15`（只增不删）。

### ③ 回滚 / 原子（人为制造中途失败） —— PASS
- 浏览器内注入：`IDBObjectStore.prototype.put` 抛错（模拟影像库写失败）⇒ `{ok:false, reason:'STORAGE_UNAVAILABLE', message:'影像库写入失败：影像存储操作失败：注入故障：影像库写入失败'}`（**未抛未捕获异常**）；前后 `image_count 15 → 15`、`face_image_id` 恒 `img-0001f-3`、`blob_keys ['asset:img-0001f-2','asset:img-0001f-3'] → 相同`。**无半成品行 / 无孤儿二进制**。
- node 双注入：
  - 二进制写失败（IDB `put` 抛错）⇒ 同上 `STORAGE_UNAVAILABLE`，`images 15 → 15`、`blobs 2 → 2`、指向不变。
  - **元数据未落盘**（注入 `localStorage.setItem('xiai:v1:images')` 抛错，`writeKey` 只返回 false 不抛）⇒ 被「回读校验」拦下：`STORAGE_UNAVAILABLE`，`images 15 → 15`、`blobs 2 → 2`、指向不变（**不留孤儿二进制**）。

### ④ 持久化（关标签重开） —— PASS
- 全新加载 `/seal/XAI-0001`（页内标记已丢 ⇒ 确为重新打开）：`face_image_id = img-0001f-3`、影像行元数据与二进制长度与替换后一致；DOM 图注 = `印面影像 img-0001f-3`、图已加载且 `src` 为 `data:image/...`。
- node：重新读回（印面指向 / 影像行 / 二进制字节）三者一致；视图模型 `faceImage.id === face_image_id === img-0001f-3`。
- 附加：同内容再传 ⇒ `deduped:true`，复用既有影像行，行数与指向均不变。

### ⑤ `npm run build` + 网络捕获 —— PASS
- `npm run build`：`✓ built in 767ms`（最终代码，退出码 0）。
- 网络捕获（`Network.enable` 全量）：共 **59** 条请求，`5196` 命中 **0**、`square-crop` 命中 **0**、外部 URL 命中 **0**（全部为 `http://127.0.0.1:5163/...`，仅 `about:` 起始页）。**未调斐萃 5196，未走 square-crop，无任何外部请求。**

## 3. 证据文件（均已落盘于 `xiai/feicui/ops/`）

- `kong_xiai_k5_replace_face_image_selftest.mjs`（node 层自测脚本，36/36 PASS）
- `kong_xiai_k5_replace_face_image_selftest_raw.json`（原始读数，含逐条断言与 before/after 快照）
- `kong_xiai_k5_replace_face_image_selftest_raw.txt`（逐条 PASS/FAIL 纪要）
- `kong_xiai_k5_replace_face_image_uiflow.py`（真浏览器端到端脚本，32/32 PASS）
- `kong_xiai_k5_replace_face_image_uiflow_raw.json`（原始读数：DOM 计数、库读数、拖拽坐标、网络全量）
- `kong_xiai_k5_replace_face_image_uiflow_raw.txt`（逐条 PASS/FAIL 纪要）
- 本报告 `kong_xiai_k5_replace_face_image_evidence.md`

## 4. 未完成项

1. **边款（EDGE）专属流程未做**（按 Zang 口径本单不做）：`edge_image_ids` 未触及；但按「与「编辑固定属性」同粒度」渲染，边款块**也**有该按钮 —— 它改的是该边款印面的 `face_image_id`（边款影像走 `edge_image_ids`，故对边款块点击后画面**不会**变化）。若口径要求边款块不出现按钮，需一行 `v-if` 增补（现无）。
2. 取景框仅支持**拖拽移动 + 右下角缩放**（与「上传印章」弹窗一致）；未做双指手势 / 键盘微调。
3. 未做「替换历史列表 / 回滚到旧影像」的 UI（数据层旧影像在库、可按 `previousFaceImageId` 读回，但页面无入口）。
4. 未在真机移动端（触摸）验证拖拽；桌面 headless 真鼠标已验。
5. 同内容重复上传走**复用既有影像行**（`deduped:true`、指向不变、行数不增）——若口径期望「每次都新增一行」，此处行为需改。

## 5. 规范缺口（供 Zang/规范单判断）

1. `xiai/docs/xiai.spec.md` 未收录「重新上传印面图」能力：§6.1 权限矩阵的「五类写」（① 新增印章 ② 新增印面 ③ 上传印面图 ④ 编辑固定属性 ⑤ 审核勘误）**没有对应项**；本单按「与 ④ 同规格（仅管理员）」实现，规范需补一行并与 AC 对应。
2. 规范未定义**影像不可变 / 只增不改**口径：本单自定「替换＝新增影像行 + 改指向，旧行与二进制永不删」。该口径（含「旧影像可回溯」）建议写进影像章节，否则后续实现可能覆盖旧图。
3. 规范未定义**数据层拒绝结果的 reason 字面值**：既有服务层用 `PERMISSION_DENIED`，`photos.js` 用 `FORBIDDEN`。本单按任务口径用 `FORBIDDEN`（服务层 + 数据层一致），建议在规范里冻结一份 reason 枚举。
4. 规范未写「入库字节上限」与「原始文件上限」的区别：本单服务层兜的是**入库字节** ≤ 1 MB，管线判的是**原始文件字节** ≤ 1 MB；两处常量同源（`IMAGE_LIMITS.maxInputBytes`）但语义不同，规范需明说。
5. 影像 `kind` 与印面 `kind` 的对应关系规范未明说（印面 `FACE` ⇒ 影像 `FACE`）；本单按「取印面自身类别」实现，边款印面则落 `EDGE` 影像。
6. 「非管理员 DOM 零命中」缺可机械判负的判据（例如「`[data-admin-action]` 全量计数 = 0」）——本单留了该读数，建议纳入规范 AC。

## 6. 环境收尾

- 自建 headless Chrome（profile `/tmp/xiai-kong5-prof`）以**精确 PID 停止**：`11281 11287 11288 11289 11291 11292 11293 11294`（主进程 **11281**），停后同 profile 进程数 **0**；**未使用** `pkill -f` / `killall`。
- 用户自己的 Chrome（PID 60297）**未触碰**；`5163` dev server（**PID 91247**）**全程未停**（收尾仍 200）；未占用 5173 / 5174；未访问 5196。
