# ops/biblio-metadata — 书目元数据 · 阶段 1 收口（Kong · 2026-10-11）

版权页 ISBN/CIP 抽取 ＋ 交叉自证 ＋ 目录键推荐 的**证据目录**与**复跑入口**。
本单＝阶段 1 收口：修三处缺陷 ＋ 前缀表落成配置文件 ＋ 批次汇总。

* 纯函数真源：`server/app/biblio.py`（**只依赖标准库**：`json` / `os` / `re` / `pathlib` / `typing`；
  不 import `sqlite3` / `cv2` / `pymupdf` / `PIL` / `paddleocr` / `numpy`）。
* 编排/落库：`ops/biblio-metadata/scan_biblio.py`（图像栈只在 `feicui/venv`）。
* 前缀表配置：`config/isbn_publisher_prefixes.json`（**新增**，供审计与扩展）。
* 库：`var/biblio_ingest.db`（**只写这里**；**不碰 `yinpu.db`**）。库 `var/` 已被 `.gitignore`（不入库）。

---

## 1. 复跑命令

```bash
cd /Users/kevin/bistro/xiai/feicui

# ① 纯函数自检（任意解释器；不必 venv）—— 84 项
python3 ops/biblio-metadata/selfcheck_biblio.py

# ② 逐书单进程（**必须**；见 §2）—— 每本书一个独立进程
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 秦印类编
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 古玺汇编
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 秦汉印典
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 福庵印缀
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 吴颐人
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 黄牧甫印谱
./venv/bin/python ops/biblio-metadata/scan_biblio.py --only tmp.pdf

# ③ 7 本对照表（只读库复算，不重跑 OCR、不切目录键）
python3 ops/biblio-metadata/verify_7books.py

# ④ 批次汇总（幂等；写 biblio_import_batches 一行汇总批次）
python3 ops/biblio-metadata/summarize_batches.py

# ⑤ 「识别结果 vs 现目录键」对照（读 scan_results.json）
python3 ops/biblio-metadata/compare_keys.py
```

可选开关：`--no-ocr`（只读文本层，调试用）、`--db <path>`、`--out-dir <dir>`。

---

## 2. 逐书单进程的**必要性**（SIGSEGV 实测）

**整批单进程会在第 4 本崩**（Paddle 原生栈 `SIGSEGV`）——`ops/biblio-metadata/scan_run.log`
留有整批单进程实跑的现场：跑到第 4 本（`秦汉印典`）后进程死于段错误，后续 4 本未产出。
根因：PaddleOCR（`PP-OCRv6` det/rec ＋ UVDoc ＋ PP-LCNet 方向分类）**每页渲染 200 dpi ⇒ 反复
建立/释放原生推理上下文**，在同一进程内跨多本 PDF 累计后触发原生栈崩溃（Python 层看不到 traceback，
只有 `Segmentation fault: 11`）。

**结论（硬口径）**：扫描**一律逐书各起一进程**（`--only <书名>` 一次一本，或外层 shell 循环
**每本一个新 `python` 进程**）。**禁止整批单进程**。

> 逐书跑均 `rc=0`（见 §8 单书抽验）；Zang 的 7 本逐书跑亦全 `rc=0`。

---

## 3. 阈值 / 常量（**全部单点可改**，`server/app/biblio.py`）

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `SCAN_FACE_HEAD_PAGES` | 6 | 版权页扫描面：前 6 页 |
| `SCAN_FACE_TAIL_PAGES` | 4 | 版权页扫描面：末 4 页 |
| `SCAN_DPI` | 200.0 | OCR 渲染分辨率 |
| `ANCHOR_WORDS` | `ISBN` / `圖書在版編目` / `在版编目` / `CIP` / `核字` | 锚词（大小写不敏感） |
| `ANCHOR_WINDOW` | 120 | **闸①** 锚词邻近窗口（字符） |
| `MIN_DISTINCT_DIGITS` | 3 | **闸③** 候选至少含这么多个不同数字 |
| `ONES_RUN_MIN` | 4 | **闸③** `1` 连续重复 ≥ 此 ⇒ 退化 |
| `MONOTONIC_RUN_MIN` | 8 | **闸③** 连续递增/递减段 ≥ 此 ⇒ 退化 |
| `MAX_ISBN_DIGITS` | 13 | **闸④** 数字连续段上限；**>13 整段拒、不滑窗** |
| `EBOOK_SOURCE_MARKERS` | `z-library`/`z-lib`/`1lib`/`libgen`/`annas(-archive)`/… | 缺陷③ 去下载站来源缀标记 |
| `PUBLISHER_MISMATCH_AS_UNVERIFIED` | `False` | 前缀命中而 OCR 出版社不一致 ⇒ `conflict`（不落 `unverified`） |

---

## 4. 三重闸（＋收口新增「形态/长度闸」）

候选 ISBN 须**同时**过闸方可采信（`is_accepted_candidate`）：

1. **① 锚词邻近闸** `anchor_near`（±`ANCHOR_WINDOW`）：排检索表 / 正文数字噪声
   （《秦印类编》800–834 页是检索表格，含大量 `978…`）。
2. **② 出版社前缀白名单闸**（`cross_verify`）：命中本地前缀表 ∧ OCR 出版社一致 ⇒ `ok`；
   命中而不一致 ⇒ `conflict`（保留双方证据）；**未命中 ⇒ `unverified`（不得判 `ok`）**。
3. **③ 退化串闸** `degenerate_reason`：全同 / 连续 `1` / 不同数字过少 / 单调连号 ⇒ 拒。
   （换来的教训：`1111111111` 在数学上恰好是最小合法 ISBN-10，纯校验位判据拦不住。）
4. **④ 形态/长度闸** `shape_reason`（**本次收口新增 / 判负缺陷①**）：规范化后数字**连续段**必须
   恰为 **10 或 13** 位；`978`/`979` 前缀（13 位）／前 9 位数字 ＋ 末位数字或 `X`（10 位）。
   **`>13` 位整段拒绝、不再滑窗**。原因见下：

   * 福庵印缀版权页 OCR：`978-988-19923-2-19789881992321`（规范化后 **26** 位，真号＋噪声被
     连字符/无空格串接）。**旧版滑窗**把它切成 13/10 位窗口，其中 `9789881992321`
     **校验位恰好合法** ⇒ 冒充成功（`state=unverified`、目录键落伪号）。
   * 秦印类编检索表：`978-7-5508-4722-4787550847224`（**25** 位）同理，10 位窗口
     `2478755084` **校验位恰好合法**、冒充 ISBN-10 ⇒ 目录键错。
   * 收口后两者**整段拒**（留痕 `too_long(26)` / `too_long(25)`）。

---

## 5. 出版社前缀本地表（配置文件）

真源：`config/isbn_publisher_prefixes.json`（`server/app/biblio.py:load_publisher_prefixes()`
载入；**文件缺失/不可解析 ⇒ 回落内联最小集** `PUBLISHER_PREFIXES_DEFAULT`）。最小集三条：

| 前缀 | 出版社 | 来源 |
| --- | --- | --- |
| `5508` | 西泠印社出版社 | 口径件 §5-3 样本锚（照登） |
| `80635` | 上海书画出版社 | Kevin 2026-10-11 复核给定 |
| `5010` | 文物出版社 | Kevin 2026-10-11 复核给定 |

**未登记前缀一律 `unverified`、不得判 `ok`**；命中本表但与 OCR 出版社不一致 ⇒ `conflict`
（现有行为已对：秦汉印典前缀 `80635` ⇒ 上海书画出版社 ≠ OCR「上海节画出版社」⇒ `conflict`）。

---

## 6. 7 本对照表（收口后复算）—— 见 `seven_book_table.md` / `.json`

> 复算忠实性：三处缺陷全部是**抽取候选之后的纯后处理**；新旧抽取器唯一差别＝形态闸（把 `>13` 位
> 整段拒掉）。故**对库中已存候选的 `raw` 重放新闸**，恰等于新抽取器在同一文本上的输出
> （`verify_7books.py`）。**只给建议：不切目录键、不改名、不改路径。**

| 书（PDF 名） | 现目录键 | 识别 ISBN（直读） | 出版社 | 自证态 | 建议目录键 | 建议来源 | 需切键 | 旧（收口前） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 秦印类编 检索版.pdf | 秦印类编 检索版 | **9787550847224** | 西泠印社出版社 | ok | **9787550847224** | ISBN | 是 | ~~2478755084~~ ❌ |
| 秦汉印典 …ok.pdf | 7806350950 | 7806350950 | 上海节画出版社 | conflict | 7806350950 | ISBN | 否 | 7806350950 |
| 古玺汇编 …ok.pdf | 7501007985 | 7501007985 | 文物出版社 | ok | 7501007985 | ISBN | 否 | 7501007985 |
| 福庵印缀 原版 高清.pdf | 福庵印缀 原版 高清 | —（假号被拒） | 中國藝術家出版社 | unverified | 福庵印缀 原版 高清 | chinese_title | 否 | ~~2321978988~~ ❌ |
| 黄牧甫印谱_(西泠印社)_(z-library…).pdf | 黄牧甫印谱 | — | 印刷厂印刷浙江省新华书店 | unverified | **黄牧甫印谱** | chinese_title | 否 | ~~黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk)~~ ❌ |
| 吴颐人篆刻作品展示.pdf | 吴颐人篆刻作品展示 | — | — | unverified | 吴颐人篆刻作品展示 | chinese_title | 否 | 吴颐人篆刻作品展示 |
| tmp.pdf | tmp.pdf | — | 印刷厂印刷浙江省新华书店 | unverified | tmp.pdf | pdf_name_unconfirmed | 否 | tmp.pdf |

**三缺陷修正达成**：秦印类编推荐键＝`9787550847224`（旧 `2478755084`）；福庵假号被拒、目录键不再
输出垃圾（落中文书名）；黄牧甫无号回退**规范化中文书名**`黄牧甫印谱`。

---

## 7. 接受 / 拒绝候选明细（收口后复算；逐书）

见 `seven_book_table.json` 的 `rows[].accepted` / `rows[].rejected`。要点：

| 书 | 接受（采信） | 拒绝（摘） |
| --- | --- | --- |
| 秦印类编 | `9787550847224`（13，p850，labeled＋anchor） | `978…47224787550847224` → `too_long(25)`（p851，检索表）；窗切伪 10 位 `2478755084` 随整段拒而消失 |
| 秦汉印典 | `7806350950`（10，p2，text_layer） | 无 |
| 古玺汇编 | `7501007985`（10，p3，OCR） | 无 |
| 福庵印缀 | —（无） | `978-988-19923-2-19789881992321` → `too_long(26)`（假 13 位 `9789881992321` 与假 10 位 `2321978988` 随整段拒而消失） |
| 黄牧甫印谱 | —（无 ISBN） | 无候选（扫面无号） |
| 吴颐人 | —（无 ISBN） | 无候选 |
| tmp.pdf | —（无 ISBN） | 无候选 |

---

## 8. 单书抽验（实跑；逐书单进程）

> **实跑读数**（`./venv/bin/python ops/biblio-metadata/scan_biblio.py --only <书名>`，
> 独立进程；写**独立库** `var/biblio_ingest.spotcheck.db` 与 `ops/biblio-metadata/spotcheck/<书名>/`，
> **不动主干库与产物**）。逐书 `rc=0`，无崩溃。日志见 `spotcheck/run.log`。

| 书 | 用时 | isbn13 | isbn10 | 出版社 | 自证态 | 建议目录键 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 秦印类编 检索版.pdf | 202.4s | **9787550847224** | 7550847223（派生） | 西泠印社出版社 | ok | **9787550847224** | ✅ 缺陷②修正（旧 `2478755084`） |
| 福庵印缀 原版 高清.pdf | 118.1s | — | — | 中國藝術家出版社 | unverified | **福庵印缀 原版 高清** | ✅ 缺陷①修正（旧假号 `9789881992321`/`2321978988` 被拒） |
| 黄牧甫印谱_(西泠印社)_(z-library…).pdf | 116.4s | — | — | 印刷厂印刷浙江省新华书店 | unverified | **黄牧甫印谱** | ✅ 缺陷③修正（旧＝整串文件名） |
| 秦汉印典 …ok.pdf | 58.5s | 9787806350959（派生） | 7806350950 | 上海节画出版社 | conflict | 7806350950 | ✅ 回归：10 位键＋conflict 不破 |

**接受/拒绝候选明细（抽验实跑）**：见各 `spotcheck/<书名>/scan_results.json` 的
`evidence.isbn_accepted` / `evidence.isbn_rejected`（形态闸留痕 `too_long(N)`）。
要点：秦印类编检索表的 25 位拼接串被整段拒（`too_long(25)`）⇒ 伪 10 位 `2478755084` 不再进入；
福庵 26 位拼接串被整段拒（`too_long(26)`）⇒ 伪 13/10 位不再进入。

---

## 9. 批次汇总

Zang 的「逐书各起一进程」为**每本书**产一条批次行（`biblio_import_batches`，`source_total=1`）。
`summarize_batches.py` 把这些成员批次归并成**一条汇总批次**（一个 `batch_id` 总括 7 本）：

* 汇总 `batch_id` ＝ `biblio-summary-<sha1(成员批次集合)[:12]>`（**幂等**：同一成员集合重跑得同一 id）。
* **只写** `biblio_import_batches` **一行**；不改 `book_biblio` 任何列值、不切目录键、不建 job。
* 见 `batch_summary.json` / `batch_summary.md`。

现有形态（每书一条 + 一条汇总）已够审计：单书行 = 逐书实跑原始读数；汇总行 = 归并视图。

---

## 10. 待确认项

1. **目录键口径（§5-4）**：本收口按「**直读形态**」定键 —— 直读 ISBN-13 ⇒ 落 13 位（秦印类编
   `9787550847224`）；**只**读到 ISBN-10（13 位为派生）⇒ 落 10 位（秦汉印典/古玺汇编 `7806350950`/
   `7501007985`，与 `config/book_dir_keys.json` 既有键一致）。**待 Jing/Kevin 确认**是否统一改为
   「一律派生成 13 位」（那两本键将变为 `9787806350959` / `9787501007981`）。
2. **秦印类编是否切键**：现键 `秦印类编 检索版`（chinese_title）⇢ 建议 `9787550847224`（ISBN）。
   本单**只给建议**，切键并入未来「重出轮」。
3. **福庵印缀来源缀**：`福庵印缀 原版 高清` 中「原版 高清」为扫描品质缀；`EBOOK_SOURCE_MARKERS`
   只处理下载站来源缀，**未**去扫描品质缀（`config/book_dir_keys.json` 裁「保留」）。**单点可改**。
4. **前缀表扩展**：现最小集三条；L1 商用 API（`jisu` / `juhe`）端点待阶段 2 定，密钥走环境变量。
5. **OCR 非确定性**：PaddleOCR 跨次跑可能有 ±字符差异；单书抽验与 Zang 读数若有微差属正常。

---

## 11. 文件清单

| 文件 | 说明 |
| --- | --- |
| `README.md` | 本文件（复跑命令 / 常量 / 三重闸 / 前缀表 / 7 本对照表 / 单书抽验 / 待确认项） |
| `selfcheck_biblio.py` / `selfcheck_output.txt` | 纯函数自检脚本 ＋ 输出（84/84 PASS） |
| `scan_biblio.py` | 编排/落库 CLI（渲染 200 dpi ＋ OCR ＋ 抽取 ＋ 交叉自证 ＋ 落库） |
| `verify_7books.py` / `seven_book_table.{json,md}` | 收口后 7 本对照表（只读库复算） |
| `summarize_batches.py` / `batch_summary.{json,md}` | 批次汇总（幂等写一行汇总批次） |
| `compare_keys.py` | 「识别结果 vs 现目录键」对照（读 `scan_results.json`） |
| `scan_run.log` | **整批单进程 SIGSEGV 实测现场**（逐书单进程必要性依据） |
| `spotcheck/<书名>/` | 单书抽验（独立进程实跑）的 `scan_results.json` / `summary.json` |
