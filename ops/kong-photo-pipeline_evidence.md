# 玺爱 · 影像管线（照片路径 + 印面图路径）产物侧上限口径 · Kong 收尾证据

> **本文件是本单（Kong／工程师）的收尾证据汇总**，头部先落盘骨架、随后逐节回写实测读数。
> 角色分工：Zang 裁口径（R-17）→ Kong 落工程 + 自证 → 质检另跑复核。
> 时点：**2026-09-20**（CST，UTC+8）。工程根：`/Users/kevin/bistro/xiai`。
> 跑法一律 **`/usr/bin/python3`**（绝对路径，3.9.6 + websocket-client 1.9.0）；全程未停 5163、未占 5173/5174、未调 5196。

## 0. 本单要解决的定性（一句话）

**「1 MB」是「用户所选文件的字节数」上限，不得拿去闸「浏览器端处理后的产物」。**
同一病根在本平台有**两个上传口**：

| 上传口 | 文件 | 旧形态（病根） | 本单状态 |
|---|---|---|---|
| 实物照片 | `src/services/photos.js` | 拿输入上限闸产物 ⇒ 回退 PNG（2.7 MB）被自家闸拒 + 误导文案 | 上一单已修（`PHOTO_ARTIFACT_MAX_BYTES`） |
| **印面图重新上传** | `src/services/seals.js` | **同一病根**：`replaceFaceImage` 判 `bytes.length > FACE_IMAGE_MAX_BYTES`(1 MB)，reason `TOO_LARGE`，文案「印面图过大…请换一张更小的图」 | **本单修完（A 项）** |

裁定的口径（R-17）：
1. **输入侧** 1 MB 只约束「用户选的原始文件字节」，判在 `src/utils/image.js::loadImageFile`（语义不得改）；
2. **产物侧** 另有更宽上限 `IMAGE_LIMITS.maxStoredBytes` = **4 MiB**（具名常量 `STORED_MAX_BYTES`），两个上传口**同源引用**，不得各写一份数值；
3. 产物超限先由 `exportSquareImage` 做**有界降质重编**（≤ `maxReencodeRounds`=3 轮），压不进才拒；
4. 拒的 reason = **`ARTIFACT_TOO_LARGE`**，文案 = **「本机影像生成失败…」**，与「你选的文件太大」**必须分开**；
5. 「认不出就不冒充」：格式判定一律按**字节魔数**（`sniffBytesMime`），认不出给可读拒绝。

### 0.1 附带定性：上轮「PNG 魔数认不出」是**探针的锅，不是产品**（完整复现链）

上一轮一度出现「真 PNG 被本单证据脚本判成**非 PNG**」的红灯。完整复现链（脚本 `feicui/ops/kong_png_magic_defn.mjs` / `.py`，原始读数落盘 `kong_png_magic_defn_raw.txt`）：

1. **取样**：`/tmp/kong-real.png`，187 字节，真实头 12 字节 = `89504e470d0a1a0a0000000d`；
2. **产品真源**（两侧都调真源码）：
   - `src/utils/image.js::sniffBytesMime` ⇒ **`image/png`** ✅
   - `src/data/assetmeta.js::sniffMime` ⇒ **`image/png`** ✅
3. **探针自写的尺子** `magicOf`（本单前的证据脚本里自建的那把）⇒ **`isPng: false`** ❌。原因不是字节不对，而是**读法错**：
   - 它取的是「4 字节 ASCII 标签」并与 `"PNG"` 比较；
   - 真 PNG 签名前 4 字节是 `0x89 'P' 'N' 'G'`，**第 4 字节是 `0x0D`（CR）**，不是 `0x00`；
   - 读数 `probe_tag_of_1_explained`：`bytes_at_1_2_3_4 = [80, 78, 71, 13]`、`as_string = "PNG\r"`、`equals_PNG = false`；
   - 同一份取样另取「按 3 字节 ASCII 标签」判 ⇒ `isPng: true` ⇒ 说明**只是这把尺子的读法错了**。
4. **结论**：PNG 签名的真判据是**8 字节** `89 50 4E 47 0D 0A 1A 0A`（产品真源就是按这个判的）；证据脚本自建「4 字节 PNG 标签」尺子本身是 bug，**把真 PNG 判成非 PNG**，与产品无关。
5. **修法（C 项）**：**删掉自建魔数尺子**，证据脚本做格式判定**只准调产品真源**，见 §4。

> 这一条同时解释了「为什么本单要立『只留一把尺』的规矩」：两把尺子必然漂移，红灯真假莫辨。

## 1. 改动文件与 md5（改前 / 改后）

| 文件 | 改前 md5（来源） | 改后 md5 | 字节数 | 本单角色 |
|---|---|---|---|---|
| `src/services/seals.js` | `53864a433c94501d65d22baf9a8a84b9`（**逆变换重建**，脚本 `kong_seals_before_md5.py` ⇒ 落盘 `kong_seals_js_before_reconstructed.js`） | `9bcf39e9a4e0fbcd81ebc7cfe2e98415` | 20140 → 22776 | **A 项主修**（本单唯一产品改动） |
| `src/views/SealDetailView.vue` | — | `2c70afb719d3557c8908dd179dcae9d7` | — | **本单未改**（D-2 两处已在位：`:945 var(--slot-tag-text)` / `:981 var(--slot-badge-text)`）。⚠️ 上一轮报告写作 `…179dc9a9d7` 是**笔误**，以本值为准 |
| `feicui/ops/kong-photo-pipeline-probe.mjs` | 未落盘（本单改动 = 真源桥接段 + 删 `magicOf` + 计数合并） | `904000c0722a56c5aa005b62d23c1de7` | 47563 | 探针源码（B/C 项） |
| `feicui/ops/kong-photo-pipeline-probe.js` | 未落盘（同上，`.js` 是 `.mjs` 的 esbuild bundle） | `2dbebb9f4f5f19d120e203e8edf54bde` | 215544 | 探针 bundle（浏览器实际加载件） |
| `feicui/ops/kong-image-truth-bridge.mjs` | — | `7c5895353ac70958ebb3e01b735043ea` | 1462 | 真源桥源（C 项） |
| `feicui/ops/kong-image-truth-bridge.js` | — | `ba2174b88d1ddb05b02374642425b80f` | 2227 | 真源桥 bundle（含 `src/utils/image.js::sniffBytesMime` 同一实现，非副本） |
| `feicui/ops/kong-photo-pipeline-cdp.py` | `10cddcd0de95fd7c300e6865e073c936`（本单收尾动手前） | `f26674c5f6c1e5953673077e715a5bd8` | 43684 → 47766 | 驱动脚本（**本单收尾再改**：断言计数合并口径修复，见 §3.4） |
| `src/data/assetmeta.js` | 未落盘 | `a47e82ddab746a08cd5c32fbbd408ac0`（mtime `18:46:20`） | 13053 | **非本单改动**：D 项由并行单（`src/data/**` 所有者）落地 |
| `src/data/db.js` | 未落盘 | `f726038a5d17942da7288f39671658d1`（mtime `18:46:44`） | 52884 | **非本单改动**（且在禁改清单内） |

改前 md5 的取证诚实说明：**工程不是 git 仓库、无改动前快照**，`seals.js` 改前 md5 由 `kong_seals_before_md5.py` 按「本单四处 patch 的逆变换」确定性重建后算出（逆变换逐字取自实际 patch 调用），重建件已落盘 `kong_seals_js_before_reconstructed.js` 供第三方复核。探针两件的改前 md5 **未落盘**，如实登记为缺口（不作为已核实值引用）。

## 2. A 项：`seals.js` 印面图路径的产物侧上限（本单主修）

改的是**四处**（全在一个文件内，产品行为）：

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | `import` | `{ IMAGE_LIMITS, describeBytes, sniffBytesMime }` | 增 `STORED_MAX_BYTES`（**同源引用**，不另写数值） |
| 2 | 常量 | `export const FACE_IMAGE_MAX_BYTES = IMAGE_LIMITS.maxInputBytes`（注释：产物侧 1 MB） | 新增 `export const FACE_IMAGE_ARTIFACT_MAX_BYTES = STORED_MAX_BYTES`（4 MiB）；`FACE_IMAGE_MAX_BYTES` **保留不删**，改为 `@deprecated` **兼容别名**、语义更正为**输入侧** 1 MB |
| 3 | 头注 | 「再兜一道 1 MB」 | 明写「③ **两套上限，不得混用**：输入侧 1 MB 判在 `loadImageFile`；产物侧 4 MiB 判处理后的二进制」 |
| 4 | 闸门与文案 | `bytes.length > FACE_IMAGE_MAX_BYTES` ⇒ `reason: 'TOO_LARGE'`，文案「印面图过大：当前内容 …（1 MB）。请换一张更小的图…」 | `bytes.length > FACE_IMAGE_ARTIFACT_MAX_BYTES` ⇒ `reason: 'ARTIFACT_TOO_LARGE'`，文案「本机影像生成失败：印面图处理后 4.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。」 |

派单方已复核改后 md5 `9bcf39e9a4e0fbcd81ebc7cfe2e98415`，与本次独立复算一致。

### 2.1 自证读数：phase3 印面图路径 **8 条断言逐条真实读数**（本单复跑，无注入 plain 路径）

跑法（**关掉强制 PNG 注入**）：

```bash
cd /Users/kevin/bistro/xiai
XIAI_RUN_MODE=plain_green /usr/bin/python3 feicui/ops/kong-photo-pipeline-cdp.py
# 解释器：/Library/Developer/CommandLineTools/usr/bin/python3（= /usr/bin/python3）3.9.6 / websocket-client 1.9.0
# 退出码 EXIT=0；日志 feicui/ops/kong-photo-pipeline-cdp_plain_green_run.txt（27195 B）
# 原始证据 feicui/ops/kong-photo-pipeline-cdp_raw_plain_green.json（90853 B）
```

**上一轮的病根与本次修复**：phase3 曾被放在「App 页面 `close` 之后」调用 ⇒ 探针全局随标签一起消失，`ConnectionResetError/BrokenPipeError`，8 条断言拿到 **0 条真实读数**。本次 phase3 已在 `phase2` 之后、探针页 `navigate`/`closeTarget` **之前**调用（`kong-photo-pipeline-cdp.py` `[4′]` 段），**8 条全部拿到真实读数，0 失败**。

| # | id | 结果 | 真实读数（`seals_replace_path.checks[i].detail` 摘录） |
|---|---|---|---|
| 1 | `seals-artifact-const` | **PASS** | `{"FACE_IMAGE_ARTIFACT_MAX_BYTES":4194304,"PHOTO_ARTIFACT_MAX_BYTES":4194304,"STORED_MAX_BYTES":4194304,"IMAGE_LIMITS_maxStoredBytes":4194304,"IMAGE_LIMITS_maxInputBytes":1048576,"FACE_IMAGE_MAX_BYTES_compatAlias":1048576,"maxReencodeRounds":3}` ⇒ **两个上传口同源同值 4 MiB，输入上限仍 1 MB，旧导出仅为兼容别名** |
| 2 | `seals-replace-ok` | **PASS** | 正常 WebP 小产物 **入库成功**：`exported={ok:true,mime:"image/webp",bytes:6238,size:"512 × 512",first12Hex:"524946465618000057454250"}`；`result={ok:true,reason:"",faceImageId:"img-0001f-2",previousFaceImageId:"img-0001f",imageMime:"image/webp",message:"印面图已替换：影像编号 img-0001f → img-0001f-2；旧影像行与二进制保留未删。新影像 512 × 512 · image/webp · 6238 字节"}`；`faceImageIdAfter="img-0001f-2"`、`oldImageRowKept=true`、`imageRowCount=14` |
| 3 | `seals-replace-mime-honest` | **PASS** | `{"rowMime":"image/webp","productMime":"image/webp"}` ⇒ 入库元数据 mime ＝**产品真源按字节**判出的格式（不采信声称值、不冒充 webp） |
| 4 | `seals-artifact-over-reject` | **PASS** | 注入「产物超上限」：`injectedBytes=4194305`（4 MiB+1）、`capBytes=4194304` ⇒ `ok=false`、**`reason:"ARTIFACT_TOO_LARGE"`**、文案 `"本机影像生成失败：印面图处理后 4.00 MB 超过入库上限 4.00 MB。这与「所选文件 ≤ 1 MB」的输入上限是两回事；请重试，或改用支持 WebP 编码的浏览器后再上传。"`、**`misleadingClause=false`（文案不含「请换一张更小的图」）**、`faceImageIdUnchanged=true` |
| 5 | `seals-artifact-over-no-halfwrite` | **PASS** | 产物超限被拒时**不留半成品**：`{"faceImageIdUnchanged":true,"imageRowCount":14}` |
| 6 | `seals-fallback-png-accepted` | **PASS** | 回退 PNG 大产物 **>1 MB 旧闸、<4 MiB 新上限** ⇒ **入库成功**：`{"artifactBytes":2832092,"artifactMiB":2.7,"mime":"image/png","reencodeRounds":0,"overOldInputGate":true,"underNewArtifactCap":true,"accepted":true,"reason":"","message":"印面图已替换：影像编号 img-0001f-2 → img-0001f-3；旧影像行与二进制保留未删。新影像 2048 × 2048 · image/png · 2832092 字节"}`（**旧实现在此必判 `TOO_LARGE` 并甩误导文案**） |
| 7 | `seals-input-over-rejected-by-pipeline` | **PASS** | 输入超 1 MB ⇒ **由管线（`loadImageFile`）拒**，文案为输入侧口径：`{"fileBytes":1258291,"ok":false,"message":"照片过大：所选文件 1.20 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。","mentionsSelectedFile":true,"isInputSideWording":true}` ⇒ **「所选文件太大」与产物侧文案确已分开** |
| 8 | `seals-not-image-still` | **PASS** | 放宽产物上限**不放松**「是不是图片」：`{"reason":"NOT_IMAGE","message":"这不是可用的图片内容（无法识别图片格式），请重新选择 JPG / PNG / WebP 图片（声称类型 image/webp）"}` |

`seals_replace_path.errors = null`（探针内零异常）。**逐条计数：8 / 8 PASS。**

## 3. B 项：补上一单丢失的尾巴

### 3.1 AC-33 三阈值回读（GREEN 跑，注入 PNG 模式）

来源文件 `feicui/ops/kong-photo-pipeline-cdp_raw_green.json`（`run.mode="green"`、`run.force_png=true`、`at=2026-09-20T18:25:29+0800`），字段路径 `app_ac33_after_reopen`（关标签重开页后）与 `app_ac33_final`（整套跑完后的最终审计）：

| 阈值 | 实测（关标签重开后） | 实测（最终审计） | 判定 |
|---|---|---|---|
| `data:image` 命中数 | **0**（`dataImageHits=0`、`dataImageKeys=[]`） | **0** | ✅ |
| localStorage 单值最大字符数（阈值 **65,536** 字符 = 64 KiB） | **4948** 字符 = **4.83 KiB**（键 `xiai:v1:faces`） | **4948** = 4.83 KiB（同键） | ✅ |
| localStorage 总量（阈值 **512 KiB**） | **12377** 字符 = **12.09 KiB** | **12774** = **12.47 KiB** | ✅ |
| `xiai:v1:photos` 键自身 | 2134 字符 = 2.08 KiB，`photosHasDataImage=false` | 2531 字符 = 2.47 KiB，`false` | ✅ |

localStorage 键集合（10 个，全部为元数据键）：`xiai:v1:users`、`xiai:v1:faces`、`xiai:v1:seals`、`xiai:v1:photos`、`xiai:v1:corrections`、`xiai:v1:downloaded`、`xiai:v1:seeded`、`xiai:v1:session`、`xiai:v1:images`、`xiai:v1:points`。

同一跑的 IndexedDB 读回（`app_indexeddb_final`）：`photo:ph-mu9o7eez-hk99e` = **2,832,092 字节**、`head12=89504e470d0a1a0a0000000d`、`isPngMagic=true` ⇒ 二进制确在 IDB、且是**真回退 PNG 产物**。

### 3.2 无注入的 plain GREEN（原生 WebP 路径端到端）

- **跑法**：`XIAI_RUN_MODE=plain_green /usr/bin/python3 feicui/ops/kong-photo-pipeline-cdp.py`（**不带** `XIAI_FORCE_PNG`）。`run.force_png=false`、`run.mode=plain_green`、`at=2026-09-20T18:45:11+0800`、Chrome `153.0.8010.52`（自建 headless，独立 profile `/tmp/xiai-probe-profile-kong`，调试口 9333）。
- **退出码**：**EXIT=0**。日志 `kong-photo-pipeline-cdp_plain_green_run.txt`（27195 B）；原始证据 `kong-photo-pipeline-cdp_raw_plain_green.json`（45688 B）；摘要 `kong-photo-pipeline-cdp_summary_plain_green.md`。
- **断言条数与结果**：**合计 41 条 = phase1 33 条 + 印面图路径（phase3）8 条**，**失败 0 条**；另网络断言 3 条（`net-external-0` / `net-5196-0` / `net-square-crop-0`）全 PASS，失败 0。
- **网络**：`total_requests=169`、`internal_count=169`、`external_urls=[]`（外部 0）、`port_5196_urls=[]`（**5196 = 0**）、`square_crop_urls=[]`（**square-crop = 0**）。
- **三档 UI 用例读数**：
  1. **正常档（原生 WebP）**：输入 `/tmp/xiai-ui-normal.jpg`（3000 × 1200，**73.0 KB / 76615 B**）⇒ 预览「已就绪：3000 × 1200 px / 71.3 KB（image/jpeg）」⇒ 上传结果 **`实物照片已上传：71.3 KB → 14.1 KB（1200 × 1200，image/webp）`**；入库行 `mime="image/webp"`、`bytes=14438`、`width/height=1200/1200`、`storage=indexeddb`；画廊首图 `data:image/webp;base64,UklGRl4`。**✅ 读数为 image/webp**（上一单病根：此处曾被 2.7 MB PNG 顶掉）。
  2. **输入超 1 MB 档**：输入 `/tmp/xiai-ui-over1mb.jpg`（**1,894,831 B = 1.81 MB**）⇒ 状态 `"照片过大：所选文件 1.81 MB，上限 1.00 MB（1 MB）。请换一张更小的图，或先用手机/系统自带的压缩再上传。"`、`kind="notice notice--error"`、**`hasCanvas=false`**（未进处理管线）；入库行数不变（仍 6 条、末行仍是正常档那条）⇒ **拒于输入侧，未产生任何新行**。
  3. **回退 PNG 档**：无注入路径下**不被触发**（`ui_upload_forced_png={}` 空读数，如实登记）。该档的端到端证据由 ① 注入跑（GREEN，见 3.1 的 IDB 2,832,092 B PNG 行）与 ② 本单 phase3 `seals-fallback-png-accepted`（真 2,832,092 B PNG **入库成功**）覆盖。
- **渲染端到端**：`/my/photos` 5 张照片卡**全部渲染完成**（`complete=true`，含 PNG 400×300、PNG 2048×2048、**WebP 2048×2048**、**WebP 1200×1200**、JPEG 各一）；`/seal/XAI-0001` 画廊 5 个 `figcaption` 与真实体量一致（`168.5 KB · image/png`、`2.70 MB · image/png`、`36.6 KB · image/webp`、`14.6 KB · image/webp` …）。
- **旧行迁移**（`probe_phase1.numbers.migration`）：迁移前 `data:image` 命中 1（`legacyDataUrlLength=230078`）⇒ `{ok:true,migrated:1,total:5,leftovers:0}`；**再跑一次幂等** `{ok:true,migrated:0,total:5,leftovers:0,"无需迁移：实物照片已全部为「元数据 + 二进制分层」形态"}`。

### 3.3 证据脚本改后 md5

| 脚本 | md5 | 字节 |
|---|---|---|
| `feicui/ops/kong-photo-pipeline-probe.js` | **`2dbebb9f4f5f19d120e203e8edf54bde`**（复核一致） | 215544 |
| `feicui/ops/kong-photo-pipeline-probe.mjs` | **`904000c0722a56c5aa005b62d23c1de7`** | 47563 |
| `feicui/ops/kong-photo-pipeline-cdp.py` | **`f26674c5f6c1e5953673077e715a5bd8`**（本单收尾改后冻结值） | 45602 |
| `feicui/ops/kong-image-truth-bridge.js` / `.mjs` | `ba2174b88d1ddb05b02374642425b80f` / `7c5895353ac70958ebb3e01b735043ea` | 2227 / 1462 |

### 3.4 断言计数自洽性（本单修掉的第二个计数口径缺陷）

上一轮 `[13]` 报「phase1+phase3 合计 **33** 条」是**把 phase3 算没**；本单首跑（未修合并口径前）又报「合计 **8** 条（其中印面图路径 8 条）」——**把 phase1 算没**，是同一个病的镜像。根因（harness 层，非产品）：

1. `[3]` 处读到的 phase1 结果 **33 条**（快照落在 `evidence.probe_phase1`）；
2. `[4]` 处 `Page.reload` ⇒ 页面里的 `window.__XIAI_PROBE_RESULTS__` **被重置**；phase2 只读不写，phase3 只写回自己那 8 条；
3. 于是 `[4′]` 单读页面全局只能拿到 **8 条**，phase1 的 33 条整段丢失。

**冻结口径（本单修复）**：`merge_results()` —— 以「**刷新前的 phase1 快照**」为底，并入「刷新后页面全局」与「`__XIAI_PROBE__.phase3()` 返回值」，checks 按 `id` 去重、numbers 浅合并。修复后真实读数：

```
[4′] 断言合并后共 41 条（phase1 33 条 + 印面图路径 8 条）；reload 后页面全局只剩 8 条，故必须以"刷新前快照"为底合并
[13] 断言：合计 41 条 = phase1 33 条 + 印面图路径(phase3) 8 条（合并口径：probe_phase1(刷新前快照) + __XIAI_PROBE_RESULTS__(刷新后页面全局) + __XIAI_PROBE__.phase3()，去重键 id）；失败 0 条＋ 网络 3 条（失败 0）
     计数自洽校验：33 + 8 = 41 （清单实长 41）⇒ OK；phase1 刷新前快照 33 条 / reload 后页面全局 8 条 / phase3 返回 8 条
```

原始 JSON 里同名机器可读字段 `merged_assertions` = `{"total":41,"phase1":33,"seals_replace_path":8,"page_global_after_reload":8,"phase1_snapshot_before_reload":33,"phase3_returned":8,"dedupe_key":"id","sources":"…"}` ⇒ **33 + 8 = 41，两种分解与清单实长三方一致。**
（注：上一轮的 GREEN 注入跑 JSON 里 `probe_phase1_final` 为空/0 条，是同一缺陷的历史产物，未回填；以本单 plain GREEN 的 41 条为冻结清单。）

## 4. C 项：修「尺子漂移」（证据脚本不得自建魔数判定）

- **病**：探针自建 `magicOf`（4 字节 ASCII 标签读法）把真 PNG 判成非 PNG，与产品真源结论相反（完整链见 §0.1）。
- **改**：
  1. **删掉自建尺子**：`kong-photo-pipeline-probe.js` 中 `magicOf*` 命中数 **0**（`kong-photo-pipeline-probe.mjs` 仅在注释里保留历史说明）；
  2. **只留一把尺**：探针 bundle 内 `import` 产品真源 `src/utils/image.js::sniffBytesMime`（**同一份实现，esbuild 打进 bundle，非副本**），暴露 `productMime` / `productMimeOfBytes: 'src/utils/image.js::sniffBytesMime'`；
  3. **第二处挂载**：`kong-image-truth-bridge.mjs` → `kong-image-truth-bridge.js` 把真源挂到 `globalThis.__XIAI_IMG_TRUTH__`（`source` 字段自报 `src/utils/image.js::sniffBytesMime`，`note` 明写「证据脚本做格式判定只准调这里（产品真源），不得自建魔数副本」），由驱动脚本在**探针页**与**重开的应用页**各注入一次。
- **对账读数**：
  - 真 PNG（187 B，`head12=89504e470d0a1a0a0000000d`）⇒ 产品真源 `image/png`；探针侧同值（`isPng` 冲突已消失）；
  - `seals-replace-mime-honest`：`rowMime == productMime == "image/webp"`（入库元数据与字节判定一致）；
  - IDB 2,832,092 B 行：`mimeByProduct="image/png"`、`truthSource="src/utils/image.js::sniffBytesMime"`、`metaMime="image/png"` ⇒ **元数据行与字节判定对账一致**。

## 5. D 项：`assetmeta.js::sniffMime` 的「认不出回落 image/png」

### 5.1 调用点全表（全仓 grep `sniffMime` / `bytesToDataUrl` / `normalizeImagePayload`）

| # | 调用点 | 形态 | 认不出的字节会落成 | 判定 |
|---|---|---|---|---|
| 0 | `src/data/assetmeta.js:186 sniffMime`（本体） | `return magicMime(...)` | 改前 **`image/png`**；**改后 `""`** | **改**（由并行单 18:46:20 落地） |
| 0′ | `src/data/assetmeta.js:154 magicMime`（内层实现） | 魔数分支，末尾 `return ''`（`:165`） | `""` | 已如实 |
| 1 | `src/data/assetmeta.js:177 bytesToDataUrl`（**渲染侧兜底**，默认参数） | `String(mime||'')… \|\| sniffMime(view) \|\| 'application/octet-stream'` | 改前 **`data:image/png;base64,…`**；**改后 `data:application/octet-stream;…`** | **改**（同一并行单） |
| 2 | `src/data/assetmeta.js:293 normalizeImagePayload`（**所有写入口**） | `const mime = sniffMime(bytes)`，空 ⇒ 拒 `UNRECOGNIZED_IMAGE` | 改前 `ok=true` + `image/png`（**冒充入库**）；**改后 `ok=false`** | **改**（同一并行单） |
| 3 | `src/data/db.js:505 migrateLegacyPhotoRows`（旧行迁移） | `mime: row.mime \|\| sniffMime(parsed.bytes)` | 改前 `image/png`；**改后 `""`** | **只登记不改**（`db.js` 在禁改清单内） |
| 4 | `src/data/db.js:39`（re-export 给下游） | `export { … sniffMime … } from './assetmeta.js'` | 随 0 号变化 | 只登记（透出口） |
| 5 | `normalizeImagePayload` 的下游调用 | `db.js:797`（上传照片）、`:1011`（影像行）、`:1097`（印面图）、`:1101`（边款图） | 随 2 号变化 ⇒ 认不出即拒 | 只登记（受益方） |
| 6 | `src/utils/file.js:25`（注释） | 文档引用，无调用 | — | 只登记 |

> 说明：`src/utils/image.js::sniffBytesMime`（**另一把尺子**，产物侧/格式判定用）与本表不是同一个函数，但其「认不出 ⇒ `''`」口径一致；两把尺子并存是历史，不属本单范围。

### 5.2 逐个判定与结论

- **判定：改**（三处源头：`sniffMime` 本体 / `bytesToDataUrl` 默认值 / `normalizeImagePayload` 采信声称值）。**落地方是并行单（`src/data/**` 所有者），不是本单**：本单在其改动前（18:40）测到的是**改前**读数（`kong_assetmeta_d_sites_raw.json`：`sniffMime(junk)="image/png"`、`normalizeImagePayload(junk).ok=true`）；18:46 后本单复测，落盘 `kong_assetmeta_d_sites_raw_after.json`：`sniffMime(junk)=""`、`normalizeImagePayload(junk).ok=false`、`bytesToDataUrl` 兜底 `data:application/octet-s`。
- **判定：只登记不改**（`db.js:505`）：`row.mime || sniffMime(parsed.bytes)` **忽略 `parsed.mime`**（dataURL 头里**真实**的 MIME），回落是该支唯一的 mime 来源；`db.js` 在本单禁改清单内 ⇒ **登记为规范缺口**，不动代码。
- 本单对 D 项**零改动**：未写任何 `src/**` 字节，只做调用点全表 + 改前/改后两次读数（脚本 `kong_assetmeta_d_sites.mjs` 全程只读）。

## 6. 未完成项与规范缺口

**本单（收尾）三项尾巴全部完成**：① phase3 八条断言拿到逐条真实读数（8/8 PASS，无注入 plain 路径，EXIT=0）；② 本文件从骨架逐节回写完整；③ 冻结后脚本 md5 取值见 §3.3。收尾自建 Chrome 按**精确 PID** 收尸：`cleanup={"pid":80811,"killed":true,"note":"SIGTERM 后已退出","exit_code":0,"exit_signal":null,"port_still_listening":""}`，`lsof` 复核 9333 已无监听、`/tmp/xiai-probe-profile-kong` 已删，**5163 全程未停**（收尾复核仍在 LISTEN）。

**未完成 / 主动不做的项**：

1. `db.js:505` 旧行迁移忽略 `parsed.mime`（§5.1 #3）——**禁改清单内，登记不改**。
2. 边款（EDGE）替换：数据层**无 `kind` 闸门**，仅 UI 层收紧（K5b 已登记，本单未动）。
3. 探针 `phase2` 只读不写 ⇒ `Page.reload` 后页面全局 `__XIAI_PROBE_RESULTS__` 必然只剩 phase3 的 8 条。本单在**驱动层**用「刷新前快照 + 页面全局 + phase3」三源合并修掉了计数口径（§3.4），**未改探针让它在 reload 后重跑 phase1**（会改变 phase2 的只读语义，超出本单范围）。
4. 工具链健壮性：plain GREEN 的 `step_errors.poll_predicate` 仍记 3 条 `AttributeError: 'str' object has no attribute 'get'`（`关标签重开后渲染` / `正常档 预览就绪` / `正常档 上传结果`，谓词吃到非对象返回）。**另有 3 条步骤异常以外的读数均已取到、不影响证据**，本单未修（如实登记，不并入产品缺陷）。
5. 无注入路径下 `ui_upload_forced_png` 读数为空（回退 PNG 档在真实浏览器里不被触发），该档证据取自注入跑与 phase3 第 6 条（§3.2 已说明）。
6. **RED（改前复现）未在本单重跑**：RED 证据为上一轮留存（`kong-photo-pipeline-cdp_RED_full.txt` / `_raw_red.json` / `_summary_red.md`），本单只做 plain GREEN 复跑，避免重复劳动。
7. 探针 `.mjs` / `.js` 的**改前 md5 未落盘**（工程非 git 仓库、无快照）——如实登记，见 §1 说明。
8. 规范缺口（沿用并行单结论）：`src/views/SealDetailView.vue` md5 `2c70afb719d3557c8908dd179dcae9d7` 为**当前基线**，上一轮报告中的 `…179dc9a9d7` 系笔误，已在本文件中更正。
