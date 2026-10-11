# 两本新书模板标定 + 全量 job（吴颐人篆刻作品展示 / 福庵印缀 原版 高清）

**日期**：2026-10-11　**角色**：Kong（实现）　**仓**：`/Users/kevin/bistro/xiai/feicui`
**口径真源**：`docs/feicui.spec.md` §3.14 ＋ 先例流程（`ops/book-calibration/README.md` 的「秦印类编 检索版.pdf」标定）＋ `config/templates.json` 既有 4 项的实际键面。
**本单授权**：Kevin 已批「**按全量页数执行**」；`default_dynasty` 按书名推定 ＝ 两本均「**近现代**」。

---

## 1. 结论（一句话）

两本模板**均已真标定**（键面与既有项**逐键对齐、8 键齐全**，`books.template_usable()` 均 `True` / `missing=[]`），`book_dir_keys.json` 加法登记两本；并用**仓内既有 E1 建 job 通道**建了两个**全量** job —— **均在池内跑起来了，**没有一个页报 `template_unusable`（旧两单的失败原因已消除）**。**不盯终态**（父级 Zang 盯池并做终态验收）。**

---

## 2. 标定参数（与既有 4 本逐字对齐）

检测器 6 池判键 ＋ 2 结构键沿用既有 4 本**逐字同值**（`hsv_low [0,120,70]` / `hsv_high [10,255,255]` / `min_area 800` / `text_offset [-120,0,110,140]` / `density_min 0.002` / `density_max 0.08`），故 `template_unusable: missing keys [...]` 的 6 个缺键**全部补齐**。

| 键 | 吴颐人 | 福庵印缀 | 来源 |
| --- | --- | --- | --- |
| `hsv_low` | `[0,120,70]` | `[0,120,70]` | 与既有 4 本逐字同 |
| `hsv_high` | `[10,255,255]` | `[10,255,255]` | 同上 |
| `min_area` | `800` | `800` | 同上 |
| `text_offset` | `[-120,0,110,140]` | `[-120,0,110,140]` | 同上 |
| `density_min` | `0.002` | `0.002` | 同上 |
| `density_max` | `0.08` | `0.08` | 同上 |
| `page_range` | `[1, 32]` | `[1, 236]` | Kevin 批「全量」；与 PDF 总页数（实测 32 / 236）一致 |
| `edge_enabled` | `true` | `true` | 与既有 4 本逐字同 |
| `pad_ratio` | `0.15` | `0.15` | **多数值**（秦汉印典/古玺汇编/秦印类编 ＝ 0.15；黄牧甫 0.02）——**未按本书逐页核验，一句话可改，不影响其余键** |
| `style_red_ratio_threshold` | `0.5` | `0.5` | 与既有 4 本逐字同 |
| `style_inference_method` | `"red_ratio_v1"` | `"red_ratio_v1"` | 同上 |
| `default_dynasty` | `"近现代"` | `"近现代"` | **按书名/作者推定**（吴颐人 b.1942；王福庵 1879–1960）——**单列待裁**，见 §6 |
| `default_dynasty_source` | `book_title_annotation(unreviewed)：…吴颐人（b.1942）属近现代…` | `…王福庵（1879–1960）属近现代…` | 照「秦汉印典/古玺汇编/秦印类编」同款句式 |
| `default_seal_type` | `"UNKNOWN"` | `"UNKNOWN"` | 同上 |
| `default_seal_type_source` | `no_chapter_map(待人工章节映射；UNKNOWN 触发 review_status=DRAFT)` | 同左 | 同上 |
| `annotation_status` | `"UNREVIEWED_PENDING_HUMAN_REVIEW"` | 同左 | 照既有口径 |

**键数**：两本各 **16 键**（与「秦印类编 检索版.pdf」逐键同集）。8 个必需键（6 池判键 ＋ `page_range` ＋ `edge_enabled`）齐全。

---

## 3. 多页抽样验证读数（真标定证据）

渲染 `RENDER_DPI=400` / `BASE_DPI=144` ⇒ `AREA_SCALE=7.7160` ⇒ `min_area_eff(int)=6172`（生产 400 dpi 口径，与池 `processor` 同式）。只读：`processor.render_page` ＋ `detect_stamp_regions`（＋ `edge_enabled` 时 `detect_edge_inscriptions`）。**零 DB 写**（跑后 repo-local `yinpu.db` 未生成）。JSON 全文见 `detect_readings.json`。

### 3.1 吴颐人篆刻作品展示.pdf（32 页 · 逐页全采样）

| 页(1‑based) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
| --- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| 印面 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | **4** | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 |

| 页 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 32 |
| --- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| 印面 | **4** | 0 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | 1 | **4** | 0 | 0 | 1 |

- **首** 页 1 ＝ **0**（封面，允许 0）；**末** 页 32 ＝ **1**；**明显多枚印面**页 ＝ 8 / 17 / 29（各 **4** 枚）。
- 全书 32 页检出印面 **22 枚**（零框页含封面/版权/文字页，属正常）。
- 输出尺寸 2205×4095px（每页 render ≈0.02s / detect ≈0.013s）。

### 3.2 福庵印缀 原版 高清.pdf（236 页 · 首/中/末 ＋ 中间摊点）

| 页(1‑based) | 1 | 2 | 3 | 30 | 60 | 90 | 118 | 150 | 180 | 200 | 234 | 235 | 236 |
| --- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| 印面 | 0 | 0 | 0 | 6 | 5 | 4 | **6** | 3 | **7** | 5 | 0 | 0 | 0 |
| 边款 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |

- **首** 页 1 ＝ **0**（封面，允许 0）；**中** 页 118 ＝ **6**；**末** 页 236 ＝ **0**（封底/空白，允许 0）。
- **明显多枚印面**页 ＝ 30/60/90/118/180/200（4〜7 枚；页 180 ＝ **7** 枚最多）。
- 输出尺寸 2331×4410px（每页 render ≈0.5s / detect ≈0.015s）。

> 两本均**确有印面被检出**且**至少一页明显多枚** ⇒ 模板不是「空转的拷贝」，检测器参数对这两本**实际生效**。

---

## 4. 建 job（`jobs_created.json` / `prod_db_fingerprint.txt`）

**走仓内既有建 job 通道 ＝ E1 `POST /api/jobs`（`http://127.0.0.1:5196`）**——两个旧 job 亦由此通道建。
（E8 `POST /api/jobs/upload` 只落盘 inbox、**不建 job**；两本 PDF 已在 `inbox/20261011/`，无需再上传。）
**不得手改 DB、未直插 `jobs` 行**（新增行一律经 E1，201）。

| 书 | job_id | 范围 | total_pages | 模板取自哪一项 | 建单读数 |
| --- | --- | --- | --- | --- | --- |
| 吴颐人篆刻作品展示.pdf | **`job-e919e55e979f4386908918a6f8136e85`** | **1–32** | 32 | `config/templates.json` → 键 `吴颐人篆刻作品展示.pdf` | 201 QUEUED |
| 福庵印缀 原版 高清.pdf | **`job-e1723d3d7b7e4f03aa578b3d84f32518`** | **1–236** | 236 | `config/templates.json` → 键 `福庵印缀 原版 高清.pdf` | 201 QUEUED |

**为何新建而非改既有 FAILED_PARTIAL 重跑**：既有两单为**终态**（`FAILED_PARTIAL`），池 `claim_job` 只认 `QUEUED`/`RUNNING`/`PAUSED`；对既有 job 改范围须改 `jobs` **既有行** ⇒ **违派单红线②**。故取派单允许的**后备路径＝新建 job**。

**池侧即时证据（记录时点 11:04，非终态）**：池已起（`app.pool` ＋ 4× `feicui_worker`，PID 72742/72745–72748），**福庵 job `RUNNING`：24 页 DONE / 32 RUNNING / 180 PENDING**；**两 job 的 `job_pages.error` 含 `template_unusable` 的 ＝ 0 行**；`stamps` 7472 → **7505**（池正常产出）。**⇒ 旧单的失败原因（模板未标定）已消除。**

---

## 5. md5 before → after（`md5.before.txt` / `md5.after.txt`）

| 文件 | before | after |
| --- | --- | --- |
| `config/templates.json` | `09daa84788bc929ca0904c88283977c6` | `0fa50f000161f6ac1bb5a58215db5d8b` |
| `config/book_dir_keys.json` | `e76d7ec3ca6ed5ff10a490191eb7be24` | `e549ab4dec586ba154146fdf414c2fcd` |

（before ＝ `git show HEAD:` 逐字节，md5 与派单给定旧 md5 一致。）

---

## 6. 红线核对（`load_assert.txt` ＝ 机械断言输出）

1. **`config/templates.json` 只许加法** ✅ —— 旧顶层键**深比较逐一相等**、无删键、新增集**恰** ＝ `{吴颐人篆刻作品展示.pdf, 福庵印缀 原版 高清.pdf}`（顶层 **4 → 6**）、**未加 `default` 键**。`git diff --stat` ＝ **68 行纯增、0 删**。
2. **`config/book_dir_keys.json` 只许加法** ✅ —— 旧 `books` 键深比较相等、无删、新增集恰两份（`git diff --stat` ＝ 12 行纯增、0 删）；`dir_key_source ∈ {chinese_title}` 属许可集。
3. **未改 `stamps` / `jobs` 既有行** ✅ —— 既有 10 个 job 行逐字段未改（见 `prod_db_fingerprint.txt`）；未手改 DB、未直插 `jobs` 行。
4. **未删任何文件** ✅。
5. **未碰印章线** ✅。
6. **只暂存自己的文件、未 `git add -A`** ✅ —— 提交用显式 pathspec（见 §8）。

> **单列待裁（父级转呈 Kevin，一句话可改）**：**`default_dynasty` 两本均取 `"近现代"`**（按书名/作者推定：吴颐人 b.1942、王福庵 1879–1960），`annotation_status` 照既有口径 ＝ `UNREVIEWED_PENDING_HUMAN_REVIEW`。**本书章节朝代若有实据，改这一个字段即可。**
>
> **另一处单点可改**：`pad_ratio = 0.15`（取多数值，未按本书逐页核验）；`福庵印缀` 目录键暂取机械规范化值 `福庵印缀 原版 高清`，若裁「去扫描品质缀」改为 `福庵印缀`。

---

## 7. 文件清单

- `templates.json.before` / `templates.json.after`（＋ `templates.diff`）
- `book_dir_keys.json.before` / `book_dir_keys.json.after`（＋ `book_dir_keys.diff`）
- `md5.before.txt` / `md5.after.txt`
- `load_assert.txt` —— 加法自证（深比较 / 无删 / 8 键 / 无 `default`）
- `detect_readings.json` / `detect_readings.txt` —— 只读多页抽样读数
- `jobs_created.json` —— 两 job 的 E1 记录与 DB 行
- `prod_db_fingerprint.txt` —— 生产库只读守卫（基线 / 新 job / 既有行未改）
