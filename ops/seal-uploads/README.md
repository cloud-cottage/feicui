# seal-uploads —— 本地上传印面导入 ＋ O 件 ＋ 1200px 成品（批 1 ＋ 批 2，Kevin 2026-10-13）

实现＝Kong（subagent）。本单四件事：**① 印章采集线加法扩展**（seals 加法四列 ＋ 新表
`seal_uploads`）→ **② 导入 12 张本地印面图**（戰國／佚名／释文留空）→ **③ O 件 12 件**
（红掩膜 bbox ＋ 20px 留白）→ **④ 1200px 成品 24 件**（A 口径 × 两版背景：宣纸 / 纯白），
外加 **⑤ 导入端点**（`POST /api/seals/uploads`）与 **⑥ 终验证据**。
（2026-10-13 追加 **⑦ 第三版成品**：纯白底＋四周只留 20px ⇒ `…-canvas-white-20px.png` ×12，
`verify.json all_pass=true` 复验含新增判据。）
（2026-10-13 追加 **⑧ 批 2**：再导入 2 张（朝代＝**`當代`**、作者＝佚名、释文留空）⇒ seals 3691→**3693**、
O 件 ＋2（`…-13-O.tiff`／`…-14-O.tiff`）、三版成品各 ＋2；**每张一个批次** `seal_upload_20261013_13/_14`
（与 source_seal_id 同名 ⇒ 原件目录形沿 `var/seal_uploads/<batch_id>/`）；`verify.json all_pass=true`
复验扩到 **14 件**。）

## 0. 一页汇总（真读数；判据全过，`verify.json all_pass=true`，现扩到 **14 件**＝批 1 十二＋批 2 二）

| 面 | 读数 |
| --- | --- |
| seals 行数 | 3679 → **3691**（批 1 ＋12）→ **3693**（批 2 ＋2）；既有行**逐字节指纹 before≡after**（两道 guard：fudan 3679 行 `2214e13c…`；批 2 写前全量 3691 行 `010f168cea9c…`，见 `guard_before_02.json`） |
| 新行逐项 | 批 1 12/12：`dynasty='戰國'`、`dynasty_source='kevin_2026-10-13 指定'`、`author_name='佚名'`、`seal_wen=''`、`audit_status='UNREVIEWED_PENDING_HUMAN_REVIEW'`、`source_kind='local_upload'`、`batch_id='seal_upload_20261013_01'`；批 2 2/2：**同上各列，唯 `dynasty='當代'`**、`batch_id='seal_upload_20261013_13/_14'`（每张一个批次） |
| 加法迁移 | seals ＋`dynasty`/`dynasty_source`/`author_name`/`source_kind TEXT DEFAULT 'fudan_api'`（既有行读值即 `fudan_api`，**不回填**）；新表 `seal_uploads`（13 列）；seal_links 8964 / seal_images 6765 全程零改动（指纹证明）；seal_import_batches 1→2→**4**（批 2 各 +1 行） |
| O 件 | 14/14（批 1 12＋批 2 2）：TIFF RGB 8-bit ＋ **Deflate(8) ＋ Predictor=2**；尺寸＝bbox＋40px（clamp 原图界；14 件**无一 clamp**）；**四边留白实测恰 20px**（O 件上复算掩膜 bbox 数值验证）；**解码像素 ≡ 源裁区逐像素**（本体零色彩处理） |
| canvas·paper | 14/14：长边 **1200** ✓；主体 **62.00%** ✓；居中偏差 ≤2px ✓；印区位级冻结（max_abs_diff=0）✓；宣纸底无印泥像素 ✓；晕染掩膜内 α≡0、环带 ≤8% ✓；背景色域 `#FAFAF7–#FFFFFF` ✓；同种子复现 ✓（批 1 12 件已被 Kevin 本人移入子目录 `异形印章 1200px/`，sha 未变） |
| canvas·plain_white | 14/14：同上全绿；**背景恰 `#FFFFFF`**（min=max=255，角部四点逐点 =255）✓（批 1 12 件仍在规范位置） |
| canvas·plain_white·20px（第三版，Kevin 2026-10-13 追加） | 14/14：长边 **1200** ✓；**四周留白几何恰 20px**（`[20,20,20,20]`，主体长边 **1160**＝画布 **96.67%**，不加 19% 宽留白）✓；居中偏差 **0**（判据 ≤1px）✓；印区位级冻结（max_abs_diff=0）✓；**背景纯白 `#FFFFFF`（std=0，角部四点逐点 =255）**✓；晕染 α≤8%（band_max=0.08）且掩膜内≡0 ✓；同参复算**逐像素可复现**、verify 独立复算与成品**逐像素相等** ✓；掩膜外无印泥 ✓（批 1 12 件已被 Kevin 本人移入子目录 `异形印章 1200px 裁切原图/`，sha 未变；**06 曾在该搬移中遗失**（子目录与 zip 内均无）⇒ 已按批 1 记录的确定性参数重算重建落回该子目录，sha256 `88a784e8…` 与批 1 记录**位级同一件**，详见 §1b） |
| 原件 | 14/14 sha256 未动（批 1 十二张；批 2 两张源图 ＋ `var/seal_uploads/` 副本） |
| yinpu.db | **一字未写**：stamps 8708 行 dump sha256 ＋ 三表计数 ＋ 主库 size 全等（指纹取 scratch 只读副本） |
| API | `total=3693`；批 1（戰國）/批 2（當代）上传行与新列可读；`POST /api/seals/uploads` 路由活（非 multipart ⇒ 400，零写入）；**批 2 未改 server/app／未重启**（活进程读库即见新行） |

## 1. 数据与文件

- 库：`var/seal_ingest.db`（**备份**：scratch `seal-uploads-20261013/seal_ingest.backup-20261013.db`，
  sha256 `da68aa8a…`，integrity ok，3679 行）。写前先取 guard（`guard_before.json`），写后复核
  （`guard_after_import.json`、`verify.json`）。
- 原件拷贝：`var/seal_uploads/seal_upload_20261013_01/image_<hash>.png`（12 件，字节＝源文件）；
  批 2：`var/seal_uploads/seal_upload_20261013_13/image_91eca8.png`（816×1164）、
  `seal_upload_20261013_14/image_827d80.png`（886×1400）。
- 库备份（批 2 前）：scratch `seal-uploads-20261013-b2/seal_ingest.backup-20261013-b2.db`
  （3691 行，sha256 `1e2116e8aaab520f…`，sqlite backup API）。
- 产物：`output/seals/无信息/`——O 件 14 ＋ `…-canvas-white.png` 14 ＋ `…-canvas-white-20px.png` 14
  ＋ `…-canvas.png` 14；**批 1 的 paper 版 12 件与 white-20px 版 12 件已被 Kevin 本人分别移入
  子目录 `异形印章 1200px/`、`异形印章 1200px 裁切原图/`（sha 未变，另有同名 zip 与
  `.DS_Store`/`__MACOSX` 附属——如实登记，未代移回**）；`seal_uploads.canvas_path` 仍指规范位置
  （子目录为用户现状）。批 2 的 8 件（13/14 × O＋三版）全在规范位置。
- 汇总/证据（入库）：本目录 `guard_before.json` / `guard_after_import.json` / `batch_spec.json` /
  `guard_before_02.json` / `guard_after_import_02.json` / `batch_spec_02.json` /
  `make_o_canvas_summary.json`（14 件；批 1 十二条的 readings/sha 锚**逐字节未动**） /
  `verify.json` / `endpoint_live_test.log` ＋ 四个可复跑脚本（批 2 新增 `import_uploads_02.py`）。

## 1b. 批 2 记录（Kevin 2026-10-13 追加 2 张，朝代＝當代）

- **源图**：`image_91eca8.png`（816×1164，sha256 `d6e6f0ac…`，红掩膜 8.02%，core bbox=(205,211,580,957)）
  ＋ `image_827d80.png`（886×1400，sha256 `f76e95a2…`，19.0%，bbox=(112,90,776,1255)）
  ——源在 `~/Library/Application Support/Hermes/composer-images/`，字节已拷 `var/seal_uploads/`。
- **入库**：`seals` ＋2 行（`local_upload_20261013_13/_14`，**dynasty='當代'**（xiai 枚举形，同「戰國」
  繁体口径）、`dynasty_source='kevin_2026-10-13 指定'`、`author_name='佚名'`、`seal_wen=''`、
  `audit_status='UNREVIEWED_PENDING_HUMAN_REVIEW'`）＋ `seal_uploads` ＋2 行 ＋
  `seal_import_batches` ＋2 行（`seal_upload_20261013_13/_14`，**每张一个批次**——batch_id 与
  source_seal_id 同名，`record_upload` 的落盘目录形即 `var/seal_uploads/<batch_id>/`，恰合 Kevin
  指定的 `_13/`、`_14/` 目录；seq 沿批 1 续 13/14 ⇒ source_seal_id 亦续号，不撞批 1）。
  **既有 3691 行零改动**：写前/写后全量指纹 `010f168cea9c…` 逐字节相等（`WHERE source_seal_id
  NOT IN (两个新 id)`），links/images/既有 batch 行同法全等；**只 INSERT，零 UPDATE**。
- **产物**：`…-13-O.tiff`（415×786）/`…-14-O.tiff`（704×1205），红掩膜 bbox＋20px 留白（四边实测
  恰 20）；三版成品 13/14 各一件（宣纸 62%／纯白 62%／纯白 20px），读数同批 1 口径（冻结
  bit_exact／背景纯白 std=0／晕染 α≤8% 掩膜内≡0／62% 或 0.9667／居中 0～0.5px／同参复算可复现）。
- **make/verify 的批 2 通道**：`make_o_and_canvas.py` 加 `--spec/--summary`（批 2 用
  `batch_spec_02.json`；汇总按 seq **合并**——spec 外条目原样保留 ⇒ 批 1 十二条的 readings/sha
  锚不动；dynasty 取 item 级）；`verify.py` 扩到 14 件（批 2 两道指纹口径 ＋ 批 1 的 36 文件
  sha 冻结锚单列），真跑 **all_pass（0 fail，exit 0）**。
- **★ Kevin 同日整理批 1 产物的现状登记（本单只登记、未代改）**：paper 12 件 → `异形印章 1200px/`
  （zip 13.3 MB）；white-20px 12 件 → `异形印章 1200px 裁切原图/`（zip 4.27 MB）。**其中 06 的
  white-20px 在搬移后盘面与 zip 内均缺失** ⇒ 本单按 `make_o_canvas_summary.json` 记录的确定性
  参数（同源裁区 ＋ `compose(plain_white, padding_px=20)` ＋ 同 PNG 编码参数）重算重建、落回该
  子目录，**sha256 `88a784e8…` 与批 1 生成时记录逐字节相等（位级同一件，非近似重造）**；其余
  11 件搬移后 sha 未变（verify ③b 全数核过）。批 1 的 36 件冻结锚（O 12＋两版 canvas 24）全程
  sha 未动。

## 2. 命名（Kevin 规则 ＋ 两个本单裁定）

`P?-C?-R?-印面釋文-朝代-作者-O.tiff` ⇒ 本批：`无信息-无信息-无信息-无信息-戰國-佚名-O-<01..12>.tiff`
（P/C/R/釋文无信息；**书的编号本批未指定 ⇒ 目录名用 `无信息`**）。canvas：`<同名去 -O>-canvas.png`
／`…-canvas-white.png`。两个**可改**裁定：
1. **目录键** `无信息`——Kevin 给出书的编号后整目录重命名即可（`seal_uploads.meta_json` 有全量溯源）；
2. **同名冲突**——12 件按规则会同名 ⇒ 尾部加 `-<序号>` 去重；待他定（或等书的编号/释文补齐后自然区分）。

## 3. 口径

- **核心图像**＝`seal_canvas.seal_mask`（`colorcal.ink_mask` V2 `r>g+15 ∧ r>b+15 ∧ S>0.25` ＋ 闭运算
  核 5 ＋ 软边收编 2px，`fill_holes=False`）外接框；O 件＝该 bbox 四周各 **20px**（clamp 图界）的
  **原始像素裁切**。不另写第二套红掩膜（复用唯一实现）。
- **成品**＝`seal_canvas.compose(caliber="A")`（印章本体紧致外接框、Lanczos、本体零色彩处理、
  宣纸/纯白底、62% 居中、长边 1200、外缘 1–3px α≤8% 晕染取该印印泥均值）。**两版背景**
  （Kevin 2026-10-13 追加）：`background="paper"`（宣纸底纹，原口径）与 `"plain_white"`
  （纯白 `#FFFFFF`，跳过纹理；其余算法完全相同）；`run_batch(backgrounds=…)`／CLI
  `--backgrounds paper,plain_white` 默认两版都出。canvas 交付 **PNG**（tiff 为可选项，本批未产，
  需要时 `write_tiff_lossless` 一行可得）。**第三版**（Kevin 2026-10-13 追加）：`compose(padding_px=20)`
  ——主体长边＝1200−2×20＝**1160**、画布＝主体四周各外扩 20px（四边留白恰 20、居中偏差 0）、
  纯白底 ⇒ `…-canvas-white-20px.png`；`--variant white20` 只出第三版（**不写库、不动既有文件**，
  动笔前先与既有 O 件只读逐像素核对）。
- **朝代枚举真源＝xiai**（15 种）；「战国」按枚举写 **`戰國`**；批 2 指定「当代」按枚举写 **`當代`**。
  feicui 侧不复制枚举，只如实记 `dynasty` ＋ `dynasty_source`。

## 4. 导入端点（本单新增；未接前端）

`POST /api/seals/uploads`（multipart/form-data）：文件段**任意字段名、可重复**（多图；带 filename）
＋ 表单 `dynasty`（**必填**）／`author`／`transcription`（缺省空＝释文留空）／`dynasty_source`／
`batch_id`（缺省 `seal_upload_<日期>_<NN>` 自增）／`source_note`。行为：原件落
`var/seal_uploads/<batch_id>/` ＋ `seal_uploads` 台账 ＋ `seals` 新行（**只 INSERT**；同批同 sha 幂等
skipped）。限额：单件 16 MiB／单请求 64 MiB／200 件；非图像容器 400；413 超限。
**活体测试**（scratch 库副本 ：5557，见 `endpoint_live_test.log`）：多图 accepted 2、幂等重放
skipped 1、缺 dynasty/非 multipart/空文件段 400、列表与单枚读面带新列、既有行 200。
**已知限制（待裁）**：`source_seal_id=local_upload_<batch 内 8 位日期>_<seq>` ——**同日多批会撞号**，
撞号显式 400（绝不覆盖既有行）；届时给 batch_id 换日期段，或另立单把批次序号编进 id。

## 5. 红线自证（算法见 `guard_before.json.algorithm`）

- 指纹＝sha256 over canonical jsonl（逐行 `json.dumps(list(row), ensure_ascii=False, separators=(',',':'))`＋`\n`，
  seals 按 `source_seal_id` 序）；「既有行」＝迁移前快照的 54 列 × 3679 行，after 按
  `WHERE source_kind='fudan_api'` 复算 ⇒ **before ≡ after**（`2214e13c…`）。
- **批 2 追加 guard**：写前全量 54 列 × **3691 行**（＝批 1 后状态），after 按 `WHERE source_seal_id
  NOT IN ('local_upload_20261013_13','local_upload_20261013_14')` 复算 ⇒ **before ≡ after**
  （`010f168cea9c…`，`guard_before_02.json`／`guard_after_import_02.json`）；links / images /
  既有 batch 行（除 2 个新 batch 行）同法全等；批 2 两行逐项断言（當代/佚名/空释文/audit/
  batch_id/目录形）2/2 ✓。
- seal_links / seal_images / seal_import_batches（除本批新 batch 行）同法全等。
- yinpu.db：`stamps` 全行 dump sha `cdcf45e1…` ＋ counts(8708/12/1170) ＋ 主库 size 3,182,592 全等；
  库文件只在 scratch 副本上打开（`mode=ro`）。
- 原件 12 张 sha256 全等；未删任何文件（Kevin 移动/打包的产物原样保留）。

## 6. 复跑命令

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/seal-uploads/import_uploads.py     # 批 1（幂等重放仅在其导入前成立；重放请先核 guard 口径）
./venv/bin/python ops/seal-uploads/make_o_and_canvas.py  # 批 1 幂等：确定性重算覆盖（不动 Kevin 子目录/zip）
./venv/bin/python ops/seal-uploads/make_o_and_canvas.py --variant white20  # 批 1 第三版：只新增 …-canvas-white-20px.png ×12（不写库、不动既有文件）
./venv/bin/python ops/seal-uploads/import_uploads_02.py --emit-guard  # 批 2 ① 写前指纹（只读库）
./venv/bin/python ops/seal-uploads/import_uploads_02.py               # 批 2 ② 导入＋写后断言（幂等：重放＝skipped）
./venv/bin/python ops/seal-uploads/make_o_and_canvas.py --spec ops/seal-uploads/batch_spec_02.json            # 批 2：O 件＋两版 canvas（汇总按 seq 合并，批 1 条目原样保留）
./venv/bin/python ops/seal-uploads/make_o_and_canvas.py --variant white20 --spec ops/seal-uploads/batch_spec_02.json  # 批 2 第三版
./venv/bin/python ops/seal-uploads/verify.py             # 终验（现 14 件）；全绿 exit 0 → verify.json（判据含批 2 双 guard／③b/③c 36 文件冻结锚）
```

## 7. 待裁项（给 Kevin）

1. **书的编号**：给出后目录 `无信息/` 整体重命名（O 件与 canvas 同步改名即可，库内路径在
   `seal_uploads.o_path/canvas_path/meta_json`）。
2. **释文**：本批 `seal_wen=''`；补齐后直接 UPDATE 这 12 行（它们本就是本批新行）。
3. **同名去重后缀** `-<序号>`：是否保留／换形（如等 P/C/R 信息补齐）。
4. **同日多批 id 规则**（见 §4 已知限制）。
5. **paper 版 canvas 已被移入 `异形印章 1200px/`、white-20px 版已被移入 `异形印章 1200px 裁切原图/`**：
   若这是最终归置，建议把 `seal_uploads.canvas_path`（批 1 十二行）一并指向子目录（一句话可改；
   **改既有行需 Kevin 明确授权**，本单红线＝既有行零改动）；white 62% 版仍在规范位置。
6. **批 2 的 06 white-20px 重建件**：已是位级同一件（sha 证），无待裁；若 Kevin 后续重新整理
   子目录，请连 06 一起搬（避免再次遗漏）。
