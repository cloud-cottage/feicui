# 影像命名地基 ＋ 样例（Kong 单 · 2026-10-11）

口径真源：`feicui/docs/image-naming-draft-v0.1.md`（**§6 Kevin 四答** ＋ **§6.1 落地清单**）。
本单是**命名地基单**：交付 **纯函数模块 ＋ 目录键表 ＋ 单本双页样例 ＋ 自检证据**。
**不做颜色校正**（另一单在做）；**不碰印章线**；**不建 job、不改库、不接 worker、不全量回填、零联网**。

> ⚠️ **本样例未校正**（`color_correction_applied = false`）——TIFF 为 PDF 重裁原样，颜色校正为另一条工况。

## 1. 交付物

| 文件 | 角色 | 入库 |
| --- | --- | --- |
| `server/app/naming.py` | **命名推导唯一实现**（纯函数；无 DB / 图像栈依赖；两侧共用） | ✅ |
| `config/book_dir_keys.json` | **书籍目录键表**（加法文件；待 Jing 入册） | ✅ |
| `ops/image-naming/selfcheck_naming.py` | 自检 ＋ 样例产出脚本（只读 DB；写样例到 `output/books/`） | ✅ |
| `ops/image-naming/selfcheck_output.txt` | 自检输出（**34/34 PASS**） | ✅ |
| `ops/image-naming/fullbook_cr_check.json` | (a) 全书 7183 枚 `(C,R)` 推导读数（分布 / 直方图 / 冲突） | ✅ |
| `ops/image-naming/sample_files.json` | (b/c/d) 16 件样例逐枚读数（名 / 尺寸 / 字节 / sha256 / 编码面实测） | ✅ |
| `ops/image-naming/index_vs_cr.json` | (e) 与库内 `idx` 的对照（逐枚表 ＋ 742/765 页不同） | ✅ |
| `output/books/秦印类编 检索版/P<页>-C<列>-R<行>.tiff` | 16 件样例（6 页 299 ＋ 10 页 400；RGB 8-bit ＋ Deflate 无损；**未校正**） | ⛔（`output/` 已 .gitignore，运行时产物） |

**未改任何既有产品文件 / DB**；`stamps` 一行未动；旧 `output/faces/**` webp 与印章线 TIFF **一字未碰**。

## 2. 模块接口（`server/app/naming.py`，纯函数）

常量：`COLUMN_GAP_WIDTH_FACTOR=0.6`、`COLUMN_GAP_MIN_PX=8.0`（**皆单点可改**）；
`NAME_RE`（通用名字形）、`NAME_RE_TIFF=^P[0-9]+-C[0-9]+-R[0-9]+\.tiff$`；`DEFAULT_DIR_KEYS_PATH`。

| 函数 | 作用 |
| --- | --- |
| `assign_cr(bboxes) -> list[(C,R)]` | 入参〔页内各枚 bbox `(x1,y1,x2,y2)`〕⇒ 逐枚 `(C,R)`（**与入参同序**） |
| `assign_cr_ex(bboxes) -> (list[(C,R)], 列数)` | 同上 ＋ **列数** |
| `column_gap_threshold(widths)` | 列间阈值 ＝ `max(中位印宽 × 0.6, 8)` |
| `n_columns(assignments)` / `page_duplicate_pairs` / `is_page_unique` / `assert_page_unique` | 列数 / **页内唯一性自检**（构造上恒真；违则 `AssertionError`，机械判负） |
| `name_for(page, c, r, ext='.tiff') -> str` | `P<页>-C<列>-R<行>.<ext>`（**大写、短横、不补零**） |
| `parse_name` / `matches_name` | 名字形解析 / 匹配 |
| `normalize_book_name(pdf_name)` | 目录键回落用的规范化书名（去扩展名、压空白） |
| `dir_key_for(pdf_name, mapping) -> str` / `dir_key_entry -> (dir_key, source)` | PDF 名 ⇒ 目录键（已登记取表值；未登记回落并暴露 `fallback_unregistered`） |
| `load_dir_keys(path=None)` | 读 `config/book_dir_keys.json` |

**算法**（口径 §6.1-1）：① 每枚取 **x 中心**升序；② **1D 间隙切分**——相邻 x 中心差 `> 阈值` 即开新列 ⇒ `C` 自左向右 `1..K`；
③ 列内按 **y 中心**升序得**秩次** `R` 自 `1` 起。构造上页内 `(C,R)` **恒唯一**。

**两侧共用实证**：`naming.py` 只 import `json/os/re/typing/pathlib`（自检断言无 `sqlite3/cv2/pymupdf/PIL/numpy/paddleocr`），
并在**接口层解释器** `server/.venv/bin/python`（不装图像栈）下实测可加载、`name_for(299,1,3)=='P299-C1-R3.tiff'`。

## 3. 书籍目录键表（`config/book_dir_keys.json`，加法）

顶层形 `{"schema":..., "books": {"<PDF 名>": {"dir_key":..., "dir_key_source":...}}}`。**已登记五条**：

| PDF 名（逐字） | `dir_key` | `dir_key_source` |
| --- | --- | --- |
| `秦汉印典 上海书画 金怀英  1997 ok.pdf` | `7806350950` | `ISBN` |
| `古玺汇编 文物出版社 罗福颐  ok.pdf` | `7501007985` | `ISBN` |
| `黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf` | `黄牧甫印谱` | `chinese_title` |
| `秦印类编 检索版.pdf` | `秦印类编 检索版` | `chinese_title` |
| `tmp.pdf` | `tmp.pdf` | `pdf_name_unconfirmed` |

- **未登记**的书 ⇒ 目录键回落 `normalize_book_name`（去扩展名规范化），并标 `fallback_unregistered`（**未登记即暴露**，不静默）。
- `黄牧甫印谱` 的「中文书名」去掉了书目来源缀 `_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk)`（口径件 §6 逐字枚举该书中文书名为「黄牧甫印谱」）；**单点可改**——若 Jing 裁「机械去扩展名规范化」，改回完整 stem 即可（文件内 `note` 已写明）。
- 本表与 `config/book_codes.json`（**平台签发**的 `seal_code` 面）**职责不同**，不得相互覆盖。
- **本单不改库、不入册**；此文件属**加法**，**待 Jing 按规范流程入册**。

## 4. 自检结果（`selfcheck_output.txt`，**34/34 PASS**）

| 派单项 | 断言 | 结果 |
| --- | --- | --- |
| ① | 边界：空页 / 单枚 / 左右两列 / 同列 y 秩次 / 乱序入参同序返回 / `assert_page_unique` 机械判负 | PASS |
| ①② | 目录键表 schema / 五本逐条 `dir_key` ＋ `source` / 未登记回落 | PASS |
| ① | `naming.py` 无 DB/图像栈 import；`server/.venv` 可加载 | PASS |
| (a) | 全书 **7183 枚 / 765 页**；页内 `(C,R)` **0 冲突** | PASS |
| (a) | 列数分布逐字对上口径件 §2（C1 2608 / C2 2458 / C3 2085 / C4 32） | PASS |
| (a) | 行位次 R1..R8 逐字对上口径件 §2（2172/1908/1446/827/397/189/98/60） | PASS |
| (a) | ★ 口径件 §2「最长列 8 枚」为**截断假象** ⇒ 实测最长列 **15**（页 791 C3） | PASS（见 §6） |
| (b) | 16 件样例名逐条匹配 `^P[0-9]+-C[0-9]+-R[0-9]+\.tiff$`；无补零 | PASS |
| (b) | 样例页 299 / 400 页内 `(C,R)` 唯一 | PASS |
| (c) | 重裁 bbox 与**库内 bbox 逐枚一致**（页 299：6/6；页 400：10/10） | PASS |
| (c) | 样例 TIFF 尺寸 **＝** 库内 bbox 宽×高（逐枚） | PASS |
| (c) | 样例 TIFF 模式 ＝ **RGB**；压缩 ＝ **Deflate**（tag 259 ∈ {8, 32946}，无损） | PASS |
| (d) | 幂等（**解码像素**面）：页 299 二次重裁逐枚一致 | PASS |
| (d) | ★ 家法编码面：Pillow `tiff_deflate` **逐字节非确定**（见 §6） | PASS（判据＝能复现该现象） |
| (e) | 库内 `idx` 序 ≠ `(C,R)` 升序序：**742/765 页不同** | PASS（证明非 idx 换写） |

### 4.1 (a) 全书分布读数（`fullbook_cr_check.json`）

- 列数分布 `C`：**C1 2608 / C2 2458 / C3 2085 / C4 32**（＝口径件 §2 逐字）
- 行位次分布 `R`：R1 2172 / R2 1908 / R3 1446 / R4 827 / R5 397 / R6 189 / R7 98 / R8 60 / **R9 37 / R10 25 / R11 15 / R12 5 / R13 2 / R14 1 / R15 1**
- **每页列数**直方图：1 列 16 页 / 2 列 99 页 / 3 列 642 页 / 4 列 8 页
- **每页最大 `R`** 直方图：4→1 / 45→2 / 171→3 / 248→4 / 150→5 / 71→6 / 27→7 / 21→8 / 8→9 / 8→10 / 8→11 / 2→12 / 1→13 / 1→15
- **最长列 ＝ 15**（页 791 第 3 列）；长列集中在本检索版**索引段**（页 749–793，如页 776 三列 12/11/11、页 791 三列 9/12/15）

## 5. 样例产出（16 件；`output/books/秦印类编 检索版/`）

**从 PDF 重裁**（复用 `processor.render_page` ＋ `processor.detect_stamp_regions`，参数＝该书模板，**未另写检测**），
BGR→RGB，Pillow `format="TIFF", compression="tiff_deflate"`（**家法：RGB 8-bit ＋ Deflate 无损**）。目录键 `秦印类编 检索版`。

| 文件 | 页 | C | R | 库内 idx | bbox(x1,y1,x2,y2) | 尺寸 W×H | 字节 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `P299-C1-R1.tiff` | 299 | 1 | 1 | 0 | (1253,1415,1600,1749) | 347×334 | 196112 |
| `P299-C1-R2.tiff` | 299 | 1 | 2 | 1 | (1280,2285,1576,2567) | 296×282 | 159934 |
| `P299-C2-R1.tiff` | 299 | 2 | 1 | 2 | (2020,614,2276,861) | 256×247 | 129674 |
| `P299-C2-R2.tiff` | 299 | 2 | 2 | 5 | (2035,2307,2264,2545) | 229×238 | 116568 |
| `P299-C2-R3.tiff` | 299 | 2 | 3 | 3 | (2030,3053,2269,3279) | 239×226 | 126858 |
| `P299-C2-R4.tiff` | 299 | 2 | 4 | 4 | (2032,3234,2267,3446) | 235×212 | 120500 |
| `P400-C1-R1.tiff` | 400 | 1 | 1 | 1 | (536,567,766,815) | 230×248 | 138634 |
| `P400-C1-R2.tiff` | 400 | 1 | 2 | 0 | (516,1470,790,1736) | 274×266 | 160320 |
| `P400-C1-R3.tiff` | 400 | 1 | 3 | 2 | (541,2349,768,2528) | 227×179 | 91710 |
| `P400-C1-R4.tiff` | 400 | 1 | 4 | 3 | (582,3159,730,3388) | 148×229 | 75810 |
| `P400-C2-R1.tiff` | 400 | 2 | 1 | 7 | (1293,609,1471,775) | 178×166 | 76656 |
| `P400-C2-R2.tiff` | 400 | 2 | 2 | 6 | (1293,743,1471,900) | 178×157 | 71800 |
| `P400-C2-R3.tiff` | 400 | 2 | 3 | 5 | (1273,1416,1493,1783) | 220×367 | 167810 |
| `P400-C2-R4.tiff` | 400 | 2 | 4 | 4 | (1258,3135,1518,3406) | 260×271 | 146798 |
| `P400-C3-R1.tiff` | 400 | 3 | 1 | 9 | (2001,569,2212,795) | 211×226 | 118544 |
| `P400-C3-R2.tiff` | 400 | 3 | 2 | 8 | (1999,752,2208,919) | 209×167 | 86828 |

- 尺寸逐枚 **＝** 库内 bbox 宽×高（无缩放、无重采样、无 pad 二次外扩）。
- 页 299 实例与口径件 §2 逐字对上：`P299-C1-R1`(x1426,y1582) / `C2-R1`(x2148,y737) / `C1-R2`(x1428,y2426) / `C2-R2`(x2149,y2426) / `C2-R3`(y3166) / `C2-R4`(y3340)。

### 5.1 (e) 与库内 `idx` 对照 —— 证明**不是**简单用 `idx`

库内 `idx` ＝ `detect_stamp_regions` 后**按 `bbox[0]`(x1) 升序**的「左→右探测序」；`(C,R)` ＝ **列级聚类 ＋ 列内 y 秩次**。
**765 页里 742 页**两序不同（仅 23 页恰好一致）。抽样页 400 逐枚（idx → C/R）：

| idx | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 库内顺序 | C1R2 | C1R1 | C1R3 | C1R4 | C2R4 | C2R3 | C2R2 | C2R1 | C3R2 | C3R1 |

页 299：idx0→C1R1、idx1→C1R2、**idx2→C2R1、idx3→C2R3、idx4→C2R4、idx5→C2R2**（列内 y 秩次**重排**了 idx 2..5）。
⇒ `R` 在列内**不是** `idx` 的单调换写；`P/C/R` 名字形与 `idx` 无一一映射。

## 6. ★ 关键发现（实测，供 Zang / Jing / Neng / R 裁）

1. **口径件 §2「行位次分布 … 最长列 8 枚」是截断假象。** §2 的 R1..R8 **八个桶**（2172/1908/1446/827/397/189/98/60）本单**逐字复现**，
   但**全分布延到 R15**（R9 37 / R10 25 / R11 15 / R12 5 / R13 2 / R14 1 / R15 1）⇒ **最长列 ＝ 15**，不是 8。
   §2 应是把 `Counter` 只打印/录入了前 8 桶。长列集中在**本检索版索引段**（页 749–793）；页 791 第 3 列 15 枚为全书最长。
   **影响**：不影响 `(C,R)` 唯一性（0 撞名）与列数分布（逐字对上）；只影响「列内最多几枚」的描述与任何**定长 `R` 位**的假设（本口径**不补零**，故无影响）。
2. **家法编码面逐字节非确定 ⇒ 验收候选 NB-7「sha256 不变」在现实现下不成立。**
   用同一像素数组以 Pillow `tiff_deflate` **重复 20 次编码，得到 5 个不同 sha256**（**仅差 1 byte**，
   位于**末 strip 字节尾与 IFD 之间**）；实测该文件 `末 strip 尾=195931 / IFD=195932 ⇒ 对齐填充 = 1 byte`。
   即 **Pillow 在把 IFD 对齐到偶地址时插入的填充字节未初始化**。
   ⇒ **NB-7 须改判据**：按**解码像素**或**规范化后（清空该填充字节）**比对，**不能**直接比整文件 sha256。
   本单幂等自检已按**解码像素**判（页 299 二次重裁逐枚一致，PASS）；**不改家法**（写 TIFF 仍走 Pillow `tiff_deflate`，报给 Zang/Jing 裁）。
   *旁注*：印章线 `seal-ingest` 的 `tiff_sha256` 是**内容寻址键**，同受此单字节抖动影响（重转同图可能得到不同 sha）——**属另一线，本单只报不动**。

## 7. 复跑

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/image-naming/selfcheck_naming.py     # 自检 ＋ 样例产出（≈1 s；期望 34/34 PASS）
```

可覆盖：`FEICUI_DB`（默认 `../data/yinpu.db`）、`FEICUI_NAMING_PDF`（默认 `~/Downloads/秦印类编 检索版.pdf`）。

## 8. 明确未做（后续单的事）

- ❌ **未施加颜色校正**（本样例为 PDF 重裁原样；校正为另一条工况）。
- ❌ 未**接入 worker** / 未改 `processor.py` / 未动 `app.pool` 链。
- ❌ 未**全量回填** 7183 枚（本单只出**页 299 / 400 共 16 件样例**）。
- ❌ **未改库**：`stamps` 一行未动（`col`/`row`/`img_path_tiff` 等加法列**另行**）；未建 job、未写 `jobs`/`job_pages`。
- ❌ 未碰**印章采集线**（内容寻址 TIFF / `images_manifest.jsonl` 一字未动）。
- ❌ 未删/未改任何既有 `output/faces/**` webp。
- ❌ 未按 §6 发现 1 / 2 改口径（**属裁定**，本单只报读数）。
- ❌ `config/book_dir_keys.json` **未入册**（待 Jing）。
