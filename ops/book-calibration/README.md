# 秦印类编 检索版.pdf — 模板标定证据（ops/book-calibration/）

**日期**：2026-10-11　**角色**：Kong（实现）　**仓**：`/Users/kevin/bistro/xiai/feicui`

## 1. 为什么开这个目录（而不是 ops/page-preview/）

本单是**书目模板标定**（给 `config/templates.json` 加一条书模板），与文档预览 E9/E10（`ops/page-preview/`）不是同一件事。为免把「标定证据」混进「预览证据」，**新开 `ops/book-calibration/`**（`ops/` 属入库目录，见 `.gitignore` 口径）。

## 2. 改了什么（只许加法）

`config/templates.json` 顶层新增一条：`秦印类编 检索版.pdf`（文件名逐字）。**现有三本一键不动**（脚本断言：old keys 语义相等、无删键、新增集恰 `{'秦印类编 检索版.pdf'}`、未加 `default` 键）。

- 改动前 md5：`20acf9162baf0a0c4e5d6e164681b5ce`（＝派单给定的旧 md5，一致）
- 改动后 md5：`09daa84788bc929ca0904c88283977c6`（**规范 §3.14.6 引用了旧 md5，后续由 Jing 收口**）
- 顶层键数：3 → **4**

新项逐键（16 键）：

| 键 | 值 | 来源 |
| --- | --- | --- |
| `hsv_low` | `[0,120,70]` | 与现有三本逐字同 |
| `hsv_high` | `[10,255,255]` | 同上 |
| `min_area` | `800` | 同上 |
| `text_offset` | `[-120,0,110,140]` | 同上 |
| `density_min` | `0.002` | 同上 |
| `density_max` | `0.08` | 同上 |
| `page_range` | `[29, 794]` | **Kevin 2026-10-11 给定**（766 页，与「正文 766 页」对上） |
| `edge_enabled` | `true` | 与现有三本逐字同 |
| `pad_ratio` | `0.15` | **多数值**（黄牧甫 0.02 / 秦汉印典·古玺汇编 0.15）——**未按本书核验，一句话可改** |
| `style_red_ratio_threshold` | `0.5` | 与现有三本逐字同 |
| `style_inference_method` | `"red_ratio_v1"` | 同上 |
| `default_dynasty` | `"秦"` | **按书名推定、待 Kevin 一句话**（见 §5） |
| `default_dynasty_source` | `"book_title_annotation(unreviewed)：书名即「秦印类编」，按书名标注，待人工章节核对"` | 照「秦汉印典/古玺汇编」同款句式 |
| `default_seal_type` | `"UNKNOWN"` | 同上 |
| `default_seal_type_source` | `"no_chapter_map(待人工章节映射；UNKNOWN 触发 review_status=DRAFT)"` | 同上 |
| `annotation_status` | `"UNREVIEWED_PENDING_HUMAN_REVIEW"` | 同上 |

## 3. 自证（不建 job）

### 3.1 加载断言（`load_assert.txt`）

`feicui/venv/bin/python` ＋ `processor.load_templates()`（仓根 CWD）：
- 新项在场；**8 个必需键齐全**（6 个池判键 `REQUIRED_TEMPLATE_KEYS`（`server/app/books.py`：`hsv_low/hsv_high/min_area/text_offset/density_min/density_max`）＋ `page_range` ＋ `edge_enabled`）；`PASS`。
- 该原因即先前池报的 `template_unusable: missing keys [hsv_low, hsv_high, min_area, text_offset, density_min, density_max]`——现该条已可被判为 usable（`is_template_usable()` 判据 = 6 键齐全）。

### 3.2 只读单页检测（`detect_readings.txt` / `detect_readings.json`）

参数＝该书模板；`render_dpi=400`、`base_dpi=144`、`AREA_SCALE=7.7160` ⇒ `min_area_eff(int)=6172`（生产 400 dpi 口径，与池 `processor` 同式）。页 = **1-based 闭区间**（`processor.process_pdf`：`p_start=start_page-1`）。只读：`render_page` ＋ `detect_stamp_regions`（＋ `edge_enabled` 时的 `detect_edge_inscriptions`），**零 DB 写**（跑后 `repo-local yinpu.db` 未生成）。

| 页(1‑based) | idx | 在范围内 | 输出尺寸 | detected 印面 | 边款 | render | detect | 合计 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 29 | 28 | ✅ | 2834×4079 | **12** | 0 | 0.132s | 0.027s | 0.159s |
| 794 | 793 | ✅ | 2834×4079 | **4** | 0 | 0.136s | 0.024s | 0.161s |
| 28 | 27 | ❌ | 2834×4079 | **0** | 0 | 0.130s | 0.013s | 0.143s |
| 795 | 794 | ❌ | 2834×4079 | **0** | 0 | 0.140s | 0.014s | 0.154s |

**边界外对照说明**：PDF 全文 **851 页**。第 28 页（正文前）与第 795 页（正文后一页）均为 **0 枚印面**——即「有印面」的页恰落在 29〜794 之内，与 Kevin 给定的正文口径自洽；28/795 落在 `page_range` 之外，池不会把它们纳入解析。（第 795 之后尚有 56 页，超出本单核验面。）

## 4. 生产库守卫（`prod_db_fingerprint.txt`）

`/Users/kevin/bistro/xiai/data/yinpu.db`（**只读** URI 打开）：

- `stamps = 89` / `jobs = 5` / `job_pages = 32` —— **与派单基线逐字相等**；`stamps` 内容指纹（按 id 排序逐行 `repr` 的 md5）＝ `7c03e17258d670636f07a8aa829c55a8`。
- **本单未建任何 job、未写生产库一字**。
- 附带既存观察（**非本单所为、与基线一致**）：`job_pages` 32 行的 `job_id` 全部不在 `jobs` 内（孤儿 32/32）——先于本单存在，本单未动。

## 5. 待 Kevin 一句话的两项

1. **`pad_ratio = 0.15`**：取三本多数值，**未按本书核验**。若本书框过松/过紧，改这一个数值即可（不影响其余键）。
2. **身份标注组（`default_dynasty="秦"` 等 5 键）**：**按书名「秦印类编」推定**、沿「秦汉印典/古玺汇编」同款手法标 **`UNREVIEWED_PENDING_HUMAN_REVIEW`**，**不是已核验结论**；如章节朝代另有实据，按 §0.4 覆写并改 `annotation_status`。

## 6. 文件清单

- `templates.json.before` / `templates.json.after` —— 改动前/后全文
- `templates.diff` —— `git diff`（纯加法，仅新增一段）
- `md5.before.txt` = `20acf9162baf0a0c4e5d6e164681b5ce`　`md5.after.txt` = `09daa84788bc929ca0904c88283977c6`
- `load_assert.txt` —— `load_templates()` 8 键断言输出
- `detect_readings.txt` / `.json` —— 四页只读检测读数
- `prod_db_fingerprint.txt` —— 生产库只读守卫
