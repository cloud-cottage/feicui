# feicui（斐萃）｜本地印谱 PDF 处理 + 汇入包导出

本地印谱 PDF → 印面/边款抽取 → 著录字段对齐 → **批次导出包**（给印索平台汇入用）。
**全部本地运行，不上传任何文件到外网。**

> 本文档已按磁盘实况重写。旧版的失实之处：① 让用户「双击 `start.bat`」——该文件**不存在**（实际是 `start.sh`）；
> ② 未提 F1 的汇入导出能力；③ 目录/产物说明与磁盘现状不符（见 §7）。端口 8501 本身不算错（那是 Streamlit 默认端口），
> 但**本机当时已被其它 python 进程占用**，务必自行指定空闲端口。

---

## 1. 快速开始（先读这一段，避免踩坑）

| 事项 | 实况 |
| --- | --- |
| Python 解释器 | **必须用 `feicui/venv/bin/python`**（已装 PyMuPDF / PaddleOCR / Pillow / OpenCV） |
| 界面 | **Streamlit**（`app.py`，378 行）。**不是 FastAPI**（规范 §9.1 描述与实际不符，见 §8） |
| 启动界面 | `cd feicui && ./venv/bin/python -m streamlit run app.py --server.port <PORT>`；或 `./start.sh`（会自建/复用 `venv`、装依赖，然后 `streamlit run app.py` —— **不指定端口，走 Streamlit 默认 8501**） |
| 端口纪律 | **启动前先探测**：`lsof -nP -iTCP:<PORT> -sTCP:LISTEN`。本机写作时 **8501 已被其它 python 进程占用**，所以 `start.sh` 直接跑会撞端口；请显式加 `--server.port 8503`（先确认空闲），用完关掉自己的进程 |
| 依赖 | `requirements.txt`（pymupdf / opencv-python / numpy / paddlepaddle / paddleocr / streamlit / pillow） |
| 上传件落盘 | 走 UI 上传通道的 PDF 会以 **`tmp.pdf`** 保存到本目录（书本身份会丢，见 §7「身份未知」） |

界面的三个 Tab 用途不变：① 版式标定与预览（存模板）② 批量解析（`processor.process_pdf`）③ 结果浏览。

---

## 2. 目录说明

| 路径 | 说明 | 本轮是否改动 |
| --- | --- | --- |
| `app.py` | Streamlit 界面（标定 / 批量解析 / 浏览） | **未改** |
| `processor.py` | 解析核心：渲染、红色印面检测、边款检测、释文匹配、OCR、写 `stamps` | **未改** |
| `config/templates.json` | 按书标定模板（`hsv_low`/`hsv_high`/`min_area`/`text_offset`/`density_min`/`density_max`/`page_range`/`edge_enabled`/`pad_ratio`） | **仅加法新增键**（见 §4.4） |
| `config/book_codes.json` | **新**：书名 → 书简码映射 + 签发状态 + PDF 路径 + 别名线索 | 新增 |
| `config/book_geometry.json` | **新**：每本书 `coord_dpi`（实测）+ 页尺寸（pt），供相对 bbox/dedupe 量化 | 新增 |
| `yinpu.db` | SQLite：既有 `stamps` 表 + F1 新增 4 张侧表 | 只新增表，**`stamps` 65 条逐行未变** |
| `output/<书名>/pXX_N.webp` | 印面裁剪图产物（既有） | **未动**（导出只读取复制） |
| `exports/<batch_id>/` | **新**：批次导出包（JSONL + 计数报告 + 影像副本） | 新增 |
| `export.py` | **新**：F1 导出模块 + CLI（字段对齐 / 标定 / 批次导出 / 书简码登记） | 新增 |
| `selfcheck_export.py` | **新**：可复跑自检（必填覆盖率 + 计数 + 管线完整性 + 沙箱逻辑自测） | 新增 |
| `tmp.pdf` | 上传通道落盘的临时 PDF（132 页；高置信推定＝「黄牧甫印谱」上传件，**未人工确认**） | 未动 |
| `start.sh` | 建 venv / 装依赖 / `streamlit run app.py`（见 §1 端口提醒） | **未改** |

---

## 3. 数据库

### 3.1 既有表 `stamps`（8 个逻辑字段 / 10 列，**原样保留**）
`id` / `pdf_name` / `page` / `idx` / `text` / `img_path` / `x1,y1,x2,y2`（bbox）。
> 本轮**不**加列、不改名、不重建、不重写任何一行；导出模块对它**只 SELECT**。

### 3.2 F1 新增 4 张侧表（纯加法，与 `stamps` 用 `stamp_id` 弱引用）

| 表 | 用途 |
| --- | --- |
| `seals` | 每条印面的 §9.3 全字段落地（含 `stage`=FORMAL/DRAFT、`missing_required`、`draft_reasons`、原始整条 `record_json`）；`UNIQUE(stamp_id)` ⇒ 每 `stamp_id` 一行最新状态 |
| `images` | ImageAsset 侧：`kind/seq/sha256/bytes/width/height/color_mode/mime` + bbox（πx/pt/相对）；`UNIQUE(stamp_id, kind, seq)` |
| `export_batches` | 批次台账：`batch_id`/序号/日期/书/简码状态/计数/覆盖率快照/包目录 |
| `export_records` | **幂等账本**：按 `dedupe_key` 记录首见/末见批次、`seen_count`、`sha256` |

设计选择说明：**新增独立导出实体**（`seals`/`images`）而非给 `stamps` 加列或改结构 —— 满足「字段扩展一律加法、不得改写现有 65 条」；
DB 侧存**最新状态**，每个批次的**不可变快照**留在 `exports/<batch_id>/*.jsonl`（平台导入以包为准）。

---

## 4. F1：字段对齐与批次导出包

### 4.1 命令清单

```bash
cd feicui
PY=./venv/bin/python

$PY export.py books                 # 列书：条数/页码范围/书简码状态/坐标标定
$PY export.py calibrate             # 实测坐标标定 → config/book_geometry.json（需能读到源 PDF）
$PY export.py export                # 全部书各出一个批次（一本书 = 一个 batch_id）
$PY export.py export --book "古玺汇编 文物出版社 罗福颐  ok.pdf" --seq 3 --date 20260920
$PY export.py batches               # 批次台账
$PY export.py issue-code --book "<pdf_name>" --short-code GXHB   # 登记平台签发的书简码（issued=true）

$PY selfcheck_export.py             # 全量自检（会新导批次）
$PY selfcheck_export.py --no-export # 只用已有包做统计
```

### 4.2 包结构（`exports/<batch_id>/`）

```
manifest.json   批次元信息（书/简码状态/警告/行格式说明）
report.json     ★ 包内计数报告 + §9.3 十七项覆盖率（含缺失原因、取值分布）
seals.jsonl     正式包：必填齐备且 reviewStatus!=DRAFT 的条目（一行一条 Seal）
draft.jsonl     DRAFT 暂存：必填缺失/待人工判定，附 missingRequired + draftReasons
images/         被引用影像的副本（源 `output/**` 只读，不移动不改写）
```

`batch_id` 形态：`fb_YYYYMMDD_<书简码>_NN`；**书简码未签发时用 `X<本地KEY>` 显式占位**（如 `fb_20260920_XGXHB_01`），
同时 `manifest.json` 里 `batchIdUsesPlaceholderShortCode=true`、`shortCodeState=PENDING_ISSUE` —— 不假装已签发。

### 4.3 JSONL 行格式

一行一条 Seal：**平台字段名（照 §9.3「对应平台字段」列）为顶层键**，内嵌 `assets[]`（ImageAsset）；
feicui 侧抽取来源 / 批次状态 / 原始像素 bbox 收在 `feicui` 子对象内，不污染平台字段。

### 4.4 §9.3 十七项落地（必填按规范＝**11 项**）

| # | feicui 字段 | 平台字段 | 必填 | 本轮取值来源 |
| --- | --- | --- | --- | --- |
| 1 | `seal_name` | `Seal.sealName` | 必填 | `stamps.text`（OCR 释文优先）；空则缺 ⇒ DRAFT |
| 2 | `dynasty` | `Seal.dynasty` | 必填 | 模板加法键 `default_dynasty`（按书名人工标注，标注状态 `UNREVIEWED_PENDING_HUMAN_REVIEW`） |
| 3 | `material` | `Seal.material` | 选填 | 未知填 `UNKNOWN`（哨兵） |
| 4 | `seal_type` | `Seal.sealType` | 必填 | 模板 `default_seal_type`（当前 `UNKNOWN`，待人工章节映射）⇒ 触发 DRAFT |
| 5 | `seal_style` | `Seal.sealStyle` | 选填 | 由裁剪图红色前景占比推断（阈值 `style_red_ratio_threshold`，默认 0.5；证据入 `ext.sealStyleEvidence`） |
| 6 | `asset_kind` | `ImageAsset.kind` | 必填 | 印面提取结果 = `FACE` |
| 7 | `source_book` | `Seal.sourceBook` | 必填 | `pdf_name` 规范化（书名/出版社/编者三段；含年号另存） |
| 8 | `source_page_no` | `Seal.sourcePageNo` | 必填 | `stamps.page`（1-based） |
| 9 | `seal_code` | `Seal.sealCode` | 必填 | `<书简码>-p<页4位>-<序号2位>`；**未签发 ⇒ `null` + `sealCodeState=PENDING_ISSUE` + 候选值另存** |
| 10 | `sha256` | `ImageAsset.sha256` | 必填 | 导出时对影像文件计算 |
| 11 | `image_bytes/width/height/color_mode` | `ImageAsset.(bytes\|width\|height\|colorMode)` | 必填 | Pillow 读取（colorMode 判定 BINARY/PALETTE/COLOR） |
| 12 | `ocr_confidence/ocr_engine` | `Seal.ext.{ocrConfidence,ocrEngine}` | 选填 | `ocrEngine` 写实际版本；置信度 `stamps` 无该列 ⇒ 留 `null`（**不臆造**） |
| 13 | `review_status` | `Seal.reviewStatus` | 必填 | 机器产出默认 `MACHINE_EXTRACTED`；有 draft 原因则 `DRAFT` |
| 14 | `batch_id` | `Seal.batchId` / `ImageAsset.batchId` | 必填 | 本书本次导出批次 |
| 15 | `source_bbox` | `Seal.bbox` | 选填 | **同时**给：源空间像素 / 点位（pt）/ 相对比例（rel）+ 页几何 + `coordDpi` |
| 16 | `rights_status` | `Seal.rightsStatus` | 选填 | 未知填 `UNKNOWN` |
| 17 | `size_mm` | `Seal.sizeMm` | 选填 | 无比例尺标注且未人工录入 ⇒ 留空（`ext.sizeMmNote` 说明） |

**必填缺失处理（§9.3 尾注 + §9.5）**：只要有一条必填缺失（或 `sealType=UNKNOWN`、或 `sealCode` 未签发），
该条 `reviewStatus=DRAFT`，**只进 `draft.jsonl`（暂存）**，**不得进 `seals.jsonl`（正式包）**，
并附拒收原因 `missingRequired` / `draftReasons`（可修复后重投新 `batch_id`）。

### 4.5 `dedupe_key` 预计算（§9.4）

`dedupe_key = sha256(sourceBook + "|" + sourcePageNo + "|" + quantize(bbox,1pt) + "|" + assetKind)`，
其中量化 bbox 渲染为 `x1,y1,x2,y2`（各坐标按所在坐标空间的 DPI 换算成 pt 后**四舍五入到 1pt**）。
同页多印由 `idx`（→ `seal_code` 序号段、`assets[].seq`）区分。
`sourceBook` 为空（书本身份未定）时 `dedupe_key=null`（无法按公式计算，不臆造），原因写入报告。

### 4.6 书简码与占位策略

- 书简码**由平台在首次汇入时签发并回填**（§9.3 #9）。本地映射表 `config/book_codes.json` 记录
  `{key, short_code, issued, issued_at, short_code_source}`。
- `issued=false`（含规范示例给出的 `GXHB`、本地提议的 `QHYD`）：`sealCode` 一律 `null`，只给
  `feicui.sealCodeCandidate`（如 `GXHB-p0024-00`）作为**占位线索**，并在记录里写死
  「候选值不作为正式码使用」；批次号同时用 `X<KEY>` 占位 token。
- 平台签发后：`export.py issue-code --book <pdf_name> --short-code <CODE>` → `issued=true` → 重跑导出即得正式 `sealCode`。
- `tmp.pdf`（上传临时名）：书本身份未定 ⇒ 连候选简码都不给；别名（黄牧甫印谱）**只用于借用影像阈值类模板键**，
  身份类键（`default_dynasty`/`default_seal_type`）**不采信**（除非人工在 `book_codes.json` 置 `trust_alias_identity=true`）。

### 4.7 坐标系（实测，不是猜的）

`stamps.x1y1x2y2` 是**页内像素坐标**，且**渲染 DPI 逐书不同**。`export.py calibrate` 用
「按候选 DPI 重新渲染 → 重跑红色检测（复用既有算法等价实现）→ 与库内 bbox 逐值比对（容差 3px）」实测：

| 书 | 实测 `coord_dpi` | 证据 |
| --- | --- | --- |
| 古玺汇编 文物出版社 罗福颐 | **400**（现版 `RENDER_DPI`） | 页 24、25 上 bbox **全部精确命中**（400 唯一命中，144/200/600 均不命中） |
| 秦汉印典 上海书画 金怀英 1997 | **144**（旧版 `BASE_DPI`） | 页 5、6 上全部精确命中 |
| tmp.pdf | **144** | 页 13、14 上全部精确命中 |

据此换算：点位 bbox、页内相对比例 bbox（`relX1..relY2`）、`dedupe_key` 的 1pt 量化 bbox。

### 4.8 计数报告口径（`report.json → counts`）

- `feicuiDecidable`：**feicui 侧可判定**的部分 —— `rejectedRequiredMissing`（§9.5 单条拒收：必填缺失）、
  `formal` / `draftStaged` / `total`，以及依据本地幂等账本的**候选**分类
  `insertedCandidate` / `updatedCandidate`（同 `dedupe_key` 但 `sha256` 变）/ `skippedDuplicateCandidate`（同 `dedupe_key` 且 `sha256` 同）、
  `draftNew` / `draftRepeatWithinLedger`、`dedupeKeysComputed` / `dedupeKeysNull`。
- `awaitingPlatformReceipt`：`inserted` / `updated` / `skipped` / `conflicted` 的**权威值一律标注「待平台回执」** ——
  平台侧需按 §9.5 字段级优先级（人工复核值 > 平台维护值 > 机器抽取）判定，feicui 无法替它下结论。

---

## 5. 自检（可复跑）

```bash
cd feicui && ./venv/bin/python selfcheck_export.py
```

打印并落盘（`exports/selfcheck_report.json`）：
① 逐包 JSONL 行数 / 影像复制数 / 计数报告；② §9.3 十七项覆盖率（逐项 present/total、%、哨兵占比、缺失原因）；
③ 必填项覆盖率汇总；④ 沙箱逻辑自测（必填齐备⇒正式包、必填缺失⇒DRAFT+原因、§9.4 幂等跳过、`dedupe_key` 公式独立复算）；
⑤ 既有 `stamps` 表导出前后**逐行 diff**（证明现有管线与 65 条数据未被改动）。

---

## 6. 当前状态（基于一次真实运行）

- 数据：`stamps` 共 **65 条**，分属 **3 个 `pdf_name`**（`tmp.pdf` 30 / 古玺汇编 23 / 秦汉印典 12），无一条有释文（`text` 全空）。
- 本轮导出：3 个批次（每书一个），共 **65 条**全为 `DRAFT`（`seals.jsonl` 0 行 / `draft.jsonl` 65 行），影像复制 23 个。
- 必填覆盖率（§9.3 主口径）：`seal_name` 0%、`dynasty` 53.85%、`seal_type` 100%（但全是 `UNKNOWN` 哨兵，不可入库）、
  `asset_kind` 100%、`source_book` 53.85%、`source_page_no` 100%、`seal_code` 0%、`sha256` 35.38%、
  `image_metrics` 35.38%、`review_status` 100%、`batch_id` 100%。
- **正式包为空**的四个原因（都可解，且已量化）：① 书简码未签发（`seal_code` 0%）② 无释文（`seal_name` 0%）
  ③ `seal_type` 无章节映射（哨兵 `UNKNOWN`）④ 42/65 影像文件在磁盘上已不存在（`output/pairs/**`、`output/秦汉印典…/**` 缺失）
  ⇒ 无法计算 `sha256`/尺寸。

---

## 7. 规范 §9.1 与实际不符（供规范角色更正，本文档不改 `docs/`）

1. **技术栈**：§9.1 写「FastAPI + PyMuPDF + PaddleOCR」；实际界面是 **Streamlit**（`app.py`），
   本 venv **未安装 fastapi**（`importlib.metadata.version('fastapi')` 取不到）。PyMuPDF + PaddleOCR 属实。
2. **数据量**：§9.1 写「当前仅 1 本书、65 条记录（`pdf_name = tmp.pdf`）」；
   实际 `stamps` 有 **3 个 `pdf_name`**：`tmp.pdf` 30 条、`古玺汇编 文物出版社 罗福颐  ok.pdf` 23 条、
   `秦汉印典 上海书画 金怀英  1997 ok.pdf` 12 条（合计 65）。
3. **影像产物**：§9.1 写「`output/<书名>/pXX_N.webp`；另有 `output/stamps`（识别成功）与 `output/unknown`（识别失败）」；
   实际 `output/` 下**只有** `古玺汇编 文物出版社 罗福颐  ok/`（23 个 webp），**不存在** `output/stamps`、`output/unknown`，也没有 `output/pairs`（而 30 条 `tmp.pdf` 记录的 `img_path` 正好指向 `output/pairs/pXX_N/stamp.png`）。
4. **`stamps` 字段数**：§9.1 写「**8 个字段**」但随后列出 10 个名字 —— 实际表列数为 **10**（`id,pdf_name,page,idx,text,img_path,x1,y1,x2,y2`），
   若把 `x1y1x2y2` 合成一个 bbox 才是 8 个逻辑字段。
5. **`x1y1x2y2` 单位**：§9.3 #15 写「现 `x1y1x2y2` 为页内**绝对点**」；实测是**像素**坐标，且**渲染 DPI 逐书不同**
   （本书库内混用 144dpi 与 400dpi，见 §4.7 的命中证据）。这直接影响 `bbox` 语义与 `dedupe_key` 的 1pt 量化口径，建议规范补一句「按导出时标定的 `coordDpi` 换算」。
6. **必填项计数**：§9.3 表里标「必填」的共 **11 项**（#1,2,4,6,7,8,9,10,11,13,14）；派单文字写「必填 10 项」，疑似把 #10/#11 併作一组。本实现按规范表＝**11 项**，覆盖率逐项报。

---

## 8. 不破坏现有管线的保证

- `processor.py` / `app.py` / `output/**` / `stamps` 表结构与 65 条数据：**本轮零改动**（自检脚本导出前后逐行 diff 佐证）。
- 模板只**新增键**（`default_dynasty`、`default_dynasty_source`、`default_seal_type`、`default_seal_type_source`、
  `annotation_status`、`style_red_ratio_threshold`、`style_inference_method`），既有键名/结构不变；
  既有代码用 `template["hsv_low"]`、`template.get("pad_ratio")` 等读取，**读不到新键不报错**（已实跑 `processor.load_templates()` 与 `processor.visualize_page()` 验证）。
- 导出只在 `exports/` 下写新包，并在 `yinpu.db` 建 4 张**新表**；既有表只 `SELECT`。

---

## 9. F2：数据恢复与补全（本轮，实现角色 Kong）

**备份**：`yinpu.db.bak-f2`（原库只读复制，466,944 B；原库未被替换/删除）。

**① 影像恢复（只读废纸篓、只复制，未删除/移动任何废纸篓内容）**

- 跑前：65 条记录中 **23 条**影像在盘、**42 条缺失**。
- 对齐依据（不改 `stamps`，把影像复制回 `img_path` 原路径）：
  - `tmp.pdf` 30 条 ⇒ `~/.Trash/pairs/pNN_i/`（目录名 == `page`+`idx`）→ `stamp.png` 复制到 `output/pairs/pNN_i/stamp.png`；
  - `秦汉印典` 12 条 ⇒ `~/.Trash/秦汉印典 上海书画 金怀英  1997 ok/p{5,6}_{0..5}.webp`（文件名 == `basename(img_path)`）复制回原目标目录；
  - `古玺汇编` 23 条本轮前已在盘。
- 结果：**恢复 42 张 / 仍缺 0 张**；恢复后 79/79 行 `img_path` 可解析且 PIL 可读。
- 废纸篓证据未变：`pairs` 61 文件/31 目录、`秦汉印典…` 24 文件，mtime 仍为 9/16 09:54 与 9/17 07:03。
- 未复制：废纸篓里 12 个 `pX_N_边款.webp`（无 `stamps` 记录指向）。

**② OCR 小样本实测（PaddleOCR 3.7.0，模型本地缓存，全程不联网/不上传）**

| 影像 | 单张耗时 | 结果 | 最高置信度 |
|---|---|---|---|
| `pairs/p13_0/stamp.png`（印面 123×122） | 0.18 s | 无字 | 0.0 |
| `秦汉印典/p5_0.webp`（印面） | 0.10 s | 无字 | 0.0 |
| `秦汉印典/p6_0.webp`（印面） | 0.35 s | `国` `巨` | 0.2304 |
| `古玺汇编/p24_0.webp`（印面 595×598） | 1.18 s | 无字 | 0.0 |
| `pairs/p13_0/edge.png`（边款/整块 1042×1468） | 11.25 s | 41 框，可读行如 `黄士陵印`/`壬申十月`/`末伎游食之民` | **0.9989**（均值 0.6209） |

⇒ 结论：**直接 OCR 印面（篆书）不可用**；释文只能取自**释文区/边款**影像。耗时估算：印面裁切 0.10–1.18 s/张；
`process_pdf` 实测 2 页 = 8.8 s ⇒ 807 页单进程约 **59 min**、544 页约 40 min、132 页约 10 min。

**③ 找到并修掉「全库无释文」的机械根因**

`processor.ocr_text()` 用 `getattr(item, "rec_texts")` 读 PaddleOCR 3.x 的 `OCRResult`，该对象**没有** `rec_texts`
属性（字段在 `item.json["res"]` 下）⇒ **任何输入恒返回 `''`**。这是 F1 结论「`stamps.text` 全空」的代码层原因，
与篆书难度无关。已做**最小修复**（`processor.py` +6 行，保留原 attribute 分支、完全向后兼容）；修复后同一
`edge.png` 返回 125 字符、`秦汉印典 p7/p8` 有 2 个区块出字。**这是本轮唯一改动到既有代码的地方**（F1 的
「processor.py 零改动」仅适用于 F1 轮）。

**④ 加法式重跑（只一本书、只缺页段）**

- 书：`秦汉印典 上海书画 金怀英  1997 ok.pdf`，页段 **7–8**（现有记录仅 p5、p6）。
- 前置校验：`processor.load_templates()` 的 9 个必需键全部存在 = True。
- 结果：**新增 14 条**（id 66–79），耗时 8.8 s；对照 `yinpu.db.bak-f2` 逐字段 diff，**原 65 行完全未变 = True**。
- 新增里 2 条有释文：`右馬廐將右馬廐`(p8_0)、`田用海厦`(p7_0)。**未做分数过滤**，`右馬廐將` 合理但尾部重复、
  `田用海厦` 可疑 ⇒ 建议 F3 加 `rec_score` 阈值 + 去重后再当 `seal_name`。

**⑤ F1 自检重跑前后对比**（`selfcheck_export.py`，总判定仍「全部通过」）

| 必填项 | 前(65 行) | 后(79 行) |
|---|---|---|
| `seal_name` | 0 % | **2.53 %** |
| `dynasty` | 53.85 % | **62.03 %** |
| `seal_type` | 100 %（全 UNKNOWN 哨兵） | 100 %（全 UNKNOWN 哨兵，非哨兵 0） |
| `asset_kind` | 100 % | 100 % |
| `source_book` | 53.85 % | **62.03 %** |
| `source_page_no` | 100 % | 100 % |
| `seal_code` | 0 % | 0 %（书简码仍未签发） |
| `sha256` | 35.38 % | **100 %** |
| `image_metrics` | 35.38 % | **100 %** |
| `review_status` / `batch_id` | 100 % | 100 % |
| `seal_style`（非必填） | 35.38 % | **100 %** |

正式包仍 **0 行 / DRAFT 79 行**（batchId `fb_20260920_*_04`）；`stamps` 导出前后逐行一致 = True。
仍未解的阻塞：**书简码未签发**（须平台）、`seal_type` 章节映射缺失、`seal_name` 仍 97.5 % 缺失。

**本轮产物**：`f2_recover_images.py`（恢复脚本）、`f2_recover_report.json`、`f2_ocr_sample.py`、
`f2_ocr_sample_report.json`、`f2_rerun.py`、`f2_stamps_before/after.json`、`f2_rerun_report.json`、`f2_report.json`。

## sealbank ⇒ xiai 试水批 100 条（2026-10-19，已投生产暂存、未采纳）

- 投喂物：`local-private/datasrc/sealbank/out/xiai_imports_sealbank_placeholder.ndjson`
  （5,529 行，占位图形态：`faces[0].image_storage_key='placeholder/seal-no-image'`、sha `18d94039…`、`image_status='present'`）。
- 执行方：xiai 仓 `scripts/submit-sealbank-batch.mjs`（等距抽样 `stride=55` 取 100、限速 400ms/条、
  幂等键 `(source, source_seal_id)` 预检＋op 体内复核、真实提交门 `ops.js::submitSealImport` ＋ `persist`）。
- 结果（生产读回，非脚本内存）：**ok=99 / skipped=1（金丝雀幂等命中）/ rejected=0 / error=0**；
  生产 `xiai_seal_imports` 中 `source='真微印網 sealbank.net'` 共 **100 行**，全部 `PENDING`、
  `image_status=present`、faces 100/100 指向占位键且 sha ＝ 登记值、`content_fingerprint` 逐行重算一致。
- 抽 3 条核验：`1268-001`（宋元/吾丘衍/魯郡吾氏）、`1859-183`（晚清/吳熙載/仲陶手斠）、
  `1910-164`（晚清/趙石/沈成伯氏祕笈之印）—— 朝代均落在 xiai 15 类枚举内。
- 批次号：`sealbank_idx_1051_1911`；回滚清单在 xiai 仓 `scripts/out/submit_batch_ids.json`
  （按幂等键删、仅限仍 `PENDING` 行、需 `--yes` 二次确认）。**采纳（reviewSealImport）未跑、留给人类**。
- 详见 xiai 仓 `docs/spec-increments/sealbank-trial-batch-100.md`（身份要求、执行读数、前端核验）。

