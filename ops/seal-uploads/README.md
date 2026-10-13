# seal-uploads —— 本地上传印面导入 ＋ O 件 ＋ 1200px 成品（批 1，Kevin 2026-10-13）

实现＝Kong（subagent）。本单四件事：**① 印章采集线加法扩展**（seals 加法四列 ＋ 新表
`seal_uploads`）→ **② 导入 12 张本地印面图**（戰國／佚名／释文留空）→ **③ O 件 12 件**
（红掩膜 bbox ＋ 20px 留白）→ **④ 1200px 成品 24 件**（A 口径 × 两版背景：宣纸 / 纯白），
外加 **⑤ 导入端点**（`POST /api/seals/uploads`）与 **⑥ 终验证据**。

## 0. 一页汇总（真读数；判据全过，`verify.json all_pass=true`）

| 面 | 读数 |
| --- | --- |
| seals 行数 | 3679 → **3691**（＋12，既有 3679 行**逐字节指纹 before≡after**） |
| 新行逐项 | 12/12：`dynasty='戰國'`、`dynasty_source='kevin_2026-10-13 指定'`、`author_name='佚名'`、`seal_wen=''`、`audit_status='UNREVIEWED_PENDING_HUMAN_REVIEW'`、`source_kind='local_upload'`、`batch_id='seal_upload_20261013_01'` |
| 加法迁移 | seals ＋`dynasty`/`dynasty_source`/`author_name`/`source_kind TEXT DEFAULT 'fudan_api'`（既有行读值即 `fudan_api`，**不回填**）；新表 `seal_uploads`（13 列）；seal_links 8964 / seal_images 6765 / seal_import_batches 1→2 全部零改动（指纹证明） |
| O 件 | 12/12：TIFF RGB 8-bit ＋ **Deflate(8) ＋ Predictor=2**；尺寸＝bbox＋40px（clamp 原图界；本批 12 件**无一 clamp**）；**四边留白实测恰 20px**（O 件上复算掩膜 bbox 数值验证）；**解码像素 ≡ 源裁区逐像素**（本体零色彩处理） |
| canvas·paper | 12/12：长边 **1200** ✓；主体 **62.00%** ✓；居中偏差 ≤2px ✓；印区位级冻结（max_abs_diff=0）✓；宣纸底无印泥像素 ✓；晕染掩膜内 α≡0、环带 ≤8% ✓；背景色域 `#FAFAF7–#FFFFFF` ✓；同种子复现 ✓ |
| canvas·plain_white | 12/12：同上全绿；**背景恰 `#FFFFFF`**（min=max=255，角部四点逐点 =255）✓ |
| 原件 | 12/12 sha256 未动 |
| yinpu.db | **一字未写**：stamps 8708 行 dump sha256 ＋ 三表计数 ＋ 主库 size 全等（指纹取 scratch 只读副本） |
| API | 已重启（ctrl 面板，新 PID lstart ≥ 全部源文件 mtime）；`total=3691`；上传行/新列可读；`POST /api/seals/uploads` 路由活（非 multipart ⇒ 400，零写入） |

## 1. 数据与文件

- 库：`var/seal_ingest.db`（**备份**：scratch `seal-uploads-20261013/seal_ingest.backup-20261013.db`，
  sha256 `da68aa8a…`，integrity ok，3679 行）。写前先取 guard（`guard_before.json`），写后复核
  （`guard_after_import.json`、`verify.json`）。
- 原件拷贝：`var/seal_uploads/seal_upload_20261013_01/image_<hash>.png`（12 件，字节＝源文件）。
- 产物：`output/seals/无信息/`——O 件 12 ＋ `…-canvas-white.png` 12；**paper 版 12 件已被 Kevin
  本人移入子目录 `异形印章 1200px/`（sha 未变，另有同名 zip）——如实登记，未代移回**；
  `seal_uploads.canvas_path` 仍指规范位置（子目录为用户现状）。
- 汇总/证据（入库）：本目录 `guard_before.json` / `guard_after_import.json` / `batch_spec.json` /
  `make_o_canvas_summary.json` / `verify.json` / `endpoint_live_test.log` ＋ 三个可复跑脚本。

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
  需要时 `write_tiff_lossless` 一行可得）。
- **朝代枚举真源＝xiai**（15 种）；「战国」按枚举写 **`戰國`**。feicui 侧不复制枚举，只如实记
  `dynasty` ＋ `dynasty_source`。

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
- seal_links / seal_images / seal_import_batches（除本批新 batch 行）同法全等。
- yinpu.db：`stamps` 全行 dump sha `cdcf45e1…` ＋ counts(8708/12/1170) ＋ 主库 size 3,182,592 全等；
  库文件只在 scratch 副本上打开（`mode=ro`）。
- 原件 12 张 sha256 全等；未删任何文件（Kevin 移动/打包的产物原样保留）。

## 6. 复跑命令

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/seal-uploads/import_uploads.py     # 幂等：重放＝skipped 12
./venv/bin/python ops/seal-uploads/make_o_and_canvas.py  # 幂等：确定性重算覆盖（不动 Kevin 子目录/zip）
./venv/bin/python ops/seal-uploads/verify.py             # 终验；全绿 exit 0 → verify.json
```

## 7. 待裁项（给 Kevin）

1. **书的编号**：给出后目录 `无信息/` 整体重命名（O 件与 canvas 同步改名即可，库内路径在
   `seal_uploads.o_path/canvas_path/meta_json`）。
2. **释文**：本批 `seal_wen=''`；补齐后直接 UPDATE 这 12 行（它们本就是本批新行）。
3. **同名去重后缀** `-<序号>`：是否保留／换形（如等 P/C/R 信息补齐）。
4. **同日多批 id 规则**（见 §4 已知限制）。
5. **paper 版 canvas 已被移入 `异形印章 1200px/`**：若这是最终归置，建议把
   `seal_uploads.canvas_path` 一并指向子目录（一句话可改）；white 版仍在规范位置。
