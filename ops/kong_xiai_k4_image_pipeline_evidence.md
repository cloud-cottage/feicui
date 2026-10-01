# 玺爱（xiai）·「上传印章」印面图 —— 浏览器端处理管线接线 自测留证（Kong）

- 时点：2026-09-20 17:31–17:46（Asia/Shanghai；本文件由自测脚本真实读数直接生成，非事后转述）
- 本单范围：**只做「上传印章」弹窗里的印面图这一条路** —— `src/components/UploadSealDialog.vue`
- 硬约束遵守情况：**未调 5196**、**未自写 canvas 处理**（画布/编码全在 `src/utils/image.js`）、
  **未停 5163**（核验时点 `lsof -nP -iTCP:5163 -sTCP:LISTEN` 仍为原 PID **91247**）、
  **未占 5173 / 5174**（两者无监听）、**未用 `pkill -f` / `killall`**（全程只用自建 headless Chrome + 独立 profile）
- 自测环境：自建 headless Chrome（`--headless=new`、独立 profile `/tmp/xiai-kong4-prof-*`、
  `--remote-debugging-port=9444`、`--remote-allow-origins=*`），**未动用户自己的 Chrome**；
  页面与产品同源（`http://127.0.0.1:5163`）⇒ 真实 `localStorage` / IndexedDB 读数
- 自测载体：`feicui/ops/kong_xiai_k4_image_pipeline.py`（md5 `c45dc5e9bac83d7c4709b79497c2795b`）
  → 原始读数 `feicui/ops/kong_xiai_k4_image_pipeline_raw.json`（md5 `4e6d8fc2dcc891fae20f0f972bb7f4c5`）
- 复跑结论：**连续两次运行均 26/26 通过、exit 0**（其中页面脚本重注次数 `re_hydrations = 0`）

## 0. 冻结契约就绪状态（如实标注）

| 时点 | `src/utils/image.js` 状态 | 本单动作 |
| --- | --- | --- |
| 开工时（17:19–17:29 核验） | **不存在**（`src/utils/` 仅 `file.js` / `format.js`） | —— |
| 17:30 核验 | **已出现**（`c88d7fac07abd73dd1f5366ec1d6d28f`、385 行）；三个冻结名 `IMAGE_LIMITS` / `loadImageFile` / `exportSquareImage` **逐名核对在位** | 据此接线（静态 import） |
| 本单全部自测时点 | **在盘且 md5 未变**（`c88d7fac…`，自测前后各复核一次） | 端到端验收**已完成** |

- 只调**三个冻结名**：`IMAGE_LIMITS` / `loadImageFile(file)` / `exportSquareImage(bitmap, {crop, maxSide, quality})`；
  **未调用该模块的其余导出**（`MIN_CROP_SIDE` / `centerSquareCrop` / `canEncodeWebp` 等一律未用，
  取景框的中心方形/夹取算术在本组件内用**纯算术**实现，**不涉及任何画布操作**）。
- 降级提示分支（`PIPELINE_READY === false` ⇒ 「图像处理模块未就绪…」并**拒绝提交**）**已写入但未能在运行时触发**
  （模块已在盘，静态 import 必然解析成功）⇒ 属**防御性守卫**，见「未完成项」。

## 1. 改动文件（改前 / 改后 md5）

| 文件 | 改前 md5 | 改后 md5 | 体量 | 说明 |
| --- | --- | --- | --- | --- |
| `src/components/UploadSealDialog.vue` | `f2b640f5774f25da51c0306562efe6e3` | `296a27c2a6b666525a41356dea952ad0` | 18,765 B | 印面图入口改走浏览器端管线：1 MB 文件字节上限 + 可拖拽/缩放方形取景框 + `exportSquareImage` 出 WebP 字节后递交；元数据 `mime` 由数据层按字节魔数如实判定 |
| `feicui/ops/kong_xiai_k4_image_pipeline.py` | 新增（原不存在） | `c45dc5e9bac83d7c4709b79497c2795b` | — | 自测脚本（证据） |
| `feicui/ops/kong_xiai_k4_image_pipeline_raw.json` | 新增（原不存在） | `4e6d8fc2dcc891fae20f0f972bb7f4c5` | — | 自测原始读数（证据） |
| `feicui/ops/kong_xiai_k4_image_pipeline_evidence.md` | 新增（原不存在） | 本文件 | — | 留证 |

**未改动（本单零写入）**：`src/utils/**`、`src/services/**`、`src/data/**`、`src/views/**`、
`src/components/` 下其它文件、`src/router/**`、`docs/**`、`index.html`、`vite.config.js`、
`package.json`、`ctrl/**`、`web/**`、`yinsuo/**`。
（`src/utils/image.js` 由并行单拥有：本单自测前后 md5 均为 `c88d7fac07abd73dd1f5366ec1d6d28f`，**逐字节未动**。）

## 2. 四条自测真实输出

### ① 选 1.2 MB 图 ⇒ 拒 + 可读提示（含真实上限与所选体量）

- 造图：页面内 canvas 噪声 PNG `noise-700x520.png`，**1,253,125 字节（≈1.20 MB）**
- 结果：**被拒**；`[data-upload-preview]` **不存在**（未进入取景、未生成预览）
- 提示原文（DOM `[data-admin-feedback="upload-seal"]` 实读）：
  > `照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。（所选文件 1.20 MB，上限 1.00 MB）`
- 入口文案实读：`本机图片文件（JPG / PNG / WebP），单张不超过 1.00 MB（1048576 字节）。选定后在本机取方形并转成 WebP，再写入本地影像库，页面只保留运行时预览。`
- 判据：✅ 拒 | ✅ 提示含**真实上限 1.00 MB / 1048576 字节**与**所选体量 1.20 MB** | ✅ 无预览、无半成品

### ② 3000×1200 非方形 ⇒ 预览 + 可拖拽/缩放的方形框 ⇒ 入库正方形 WebP

- 造图：`wide-3000x1200.png`，**759,503 字节（741.7 KB）**
- 预览图**真的解码可见**：`<img class="cropper__img">` `complete=true`、`naturalWidth=3000`、`naturalHeight=1200`、渲染 `238 × 94`、`src` ＝本机 `blob:` URL（**零外链**）
- 预览 + 取景框（真实 DOM 读数）：框 `96 × 96`（正方形），读数文案
  `已选 wide-3000x1200.png · 原图 3000 × 1200 · 原文件 741.7 KB ⇒ 入库印面 1200 × 1200 · image/webp · 4.1 KB（最长边 ≤ 2048px、质量 0.85）`
- **拖拽移动**（真实 CDP 鼠标事件，先 `scrollIntoView` 保证方框完整落在视口内 `fullyInViewport=true`）：
  `left 72px → 132px`（框 `x 558 → 618`）
- **拖手柄缩放**：`96 × 96 → 51 × 51`（宽高同步变小、保持正方形）
- 提交后服务层 message 原文（广场通知实读）：
  > `已新增印章《佚名》（XA000000001）与 1 个印面 查看「XA000000001」`
- **IndexedDB / 元数据读回（真实读数）**：

| 判据 | 实读 | 结论 |
| --- | --- | --- |
| `width == height` | `638 × 638` | ✅ |
| `mime` | `image/webp` | ✅ |
| `bytes`（元数据体量） | `1746` 字节 | ✅ |
| 导出边长＝用户取景框（≠ 默认中心方形 1200） | `638` | ✅ 取景真的进了导出 |
| IndexedDB 读回二进制 | `head=[82,73,70,70,86,16,0,0,87,69,66,80]`（`RIFF….WEBP`）、`length=1746`、`valueType=[object Uint8Array]` | ✅ 真实 WebP 且字节数与元数据一致 |
| 影像 id / 所属印面 | `img-000000001f` / `fc-000000001-f1` | ✅ |

### ③ 英文字段只填朝代/分类、印文留空 ⇒ 提成成功且编号形如 `XA\d{9}`

- 造图：`portrait-500x900.png`（12,411 字节）；取景框 `133 × 133`（默认短边），框 `left 0px / top 53px`
- 表单：朝代 `漢`、分类 `官印`、**印文留空**（未填任何值）
- 落库读数：`stamp_id = XA000000002`（正则 `^XA\d{9}$` ✅）、`seal_name = ""`（如实为空，展示层归「佚名」）
- 入库影像：`500 × 500`、`mime = image/webp`、`bytes = 1298`、id `img-000000002f`
- 通知原文：`已新增印章《佚名》（XA000000002）与 1 个印面 查看「XA000000002」`

### ④ `npm run build` 可过

```
$ npm run build          # 退出码 0
dist/assets/image-Del7Xcv_.js                 5.62 kB │ gzip: 2.64 kB   ← 冻结模块已被打包（静态 import 解析成功）
dist/assets/SquareView-CsEzlSG8.js           15.32 kB │ gzip: 6.49 kB
✓ built in 795ms
```
（末次复跑：`✓ built in 757ms`，退出码 0）

### ⑤（附加判据）边界内必须被接受 —— 证明 1 MB 不是「一刀切拒绝」

- 造图：`noise-640x440.png`，**969,699 字节（946.9 KB，≤ 1,048,576）**
- 结果：**被接受并进入取景**（`[data-upload-preview]` 存在、无错误提示）；读数
  `⇒ 入库印面 440 × 440 · image/webp · 145.3 KB`
- 提交成功：`XA000000003`，影像 `440 × 440 / image/webp / 148,794 字节`（噪声图 WebP 压缩率低，体量大而真实）
- 说明：**上限两侧都有用例**（1.20 MB 拒 / 0.92 MB 收），拒绝不是体量一刀切。

### ⑥（口径未变）缺必填仍由服务层拒并展示其 message

- 已选印面图、朝代留空提交 ⇒ 反馈原文 `请补全必填项：朝代`；印章数 `11 → 11`（**无半成品**）

## 3. 网络证据（零 5196 / 零外链）

自测全程 `Network.enable` 捕获 **136 条请求**：

- `square_crop_requests`（含 `5196` 或 `square-crop` 的 URL）：**`[]`** ⇒ **未调斐萃 5196 / square-crop，一次都没有**
- `non_base_requests`（非 `http://127.0.0.1:5163` 且非 `data:` / `blob:` 的 URL）：**`[]`** ⇒ **零外链**
- 图像处理全部落在浏览器端：上传前后网络流量只有本机 dev 资源（JS/CSS/HMR）

## 4. 未完成项 / 已知边界（如实）

1. **降级提示分支未经运行时触发**：`PIPELINE_READY === false` 的「图像处理模块未就绪…」守卫在
   `src/utils/image.js` 已在盘的前提下无法在真实浏览器里触发（静态 import 必然解析成功）。
   本单只做了**代码层审读**，未做该分支的端到端验证（若需可判负，需并行单提供可注入的失效开关）。
2. **`canEncodeWebp` 兜底路径未覆盖**：本机 headless Chrome 能编 WebP，
   故「浏览器编不出 WebP ⇒ 如实入库 PNG/JPEG + 提示」这条分支**在本机未被实测**（口径由冻结模块声明）。
3. **体量上限只在 UI 前置校验**：数据层 `normalizeImagePayload` / `insertImageRow` **无字节上限**，
   绕过 UI 直调服务层仍可写入任意体量（本单不允许改 `src/services/**`、`src/data/**` ⇒ 留给对应单）。
4. **未做移动端真机触摸验证**：取景框用 Pointer Events + `setPointerCapture` 实现，
   桌面鼠标拖动已实测；触摸/触控板手势**未在真机验证**（headless 环境无法覆盖）。

## 5. 规范缺口（转 Jing / Zang）

1. **规范无对应条款**：`xiai/docs/xiai.spec.md`（v1.3）全文**无**「1 MB 文件字节上限」「浏览器端处理」
   「入库统一 WebP」「方形取景框」任何一条；AC-33 表下注的「单张 400 dpi 印面图就可能几百 KB」
   是 `localStorage` 体积论证（理由说明），**不是上限口径**。本单实现的「上限 + 格式」口径**先于规范**，
   建议补条款（含判负形态：超限仍入库 / 非 WebP 冒充 WebP / 静默用原图递交）。
2. **无 AC 覆盖「入库影像字节上限」**：AC-33 只管二进制去向（IndexedDB）与 `localStorage` 体量阈值；
   **「印面图输入上限 1 MB」缺少可机械判负的 AC**。
3. **「统一 WebP」缺兜底口径**：浏览器编不出 WebP 时，规范未规定是**拒绝**还是**如实入库 + 提示**；
   冻结模块选了后者（`mime` 按字节魔数如实回报）。需规范确认，否则「统一 WebP」不可机械判负。
4. **`mime` 真源未写进契约**：入库 `mime` 由数据层按字节魔数嗅探（`sniffMime`），**UI 无法注入 mime**；
   冻结 API `faceImage` 只收二进制（无 mime 参数）。若规范要求「上传方声明 mime」，需扩冻结 API。
5. **AC-28 与取景框的关系未定义**：AC-28 只要求「上传 1 张印面图」，未规定「非方形原图如何取方形」；
   「用户取景 vs 系统中心裁剪」属新增交互面，**没有对应判据**。
6. **`src/services/photos.js`（实物照片路径）已被并行单改为 `PHOTO_MAX_BYTES = 1024*1024`**，
   旧文案「照片过大，请选择 400 KB 以内」现已不存在于 `src/`（本单零写入该文件，仅登记同一口径在两处落地）。
