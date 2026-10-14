# output 四总目录约定 v0.1（Kevin · 2026-10-14）

**状态**：已落地（Kong 实现单 · 2026-10-14）。**口径真源**＝本文件；目录内另有逐目录 README。

## §1 四总目录语义

| 目录 | 语义 | 现状（2026-10-14） |
|---|---|---|
| `output/【1_Original_PDF】/` | **PDF 唯一真源**：读 PDF 一律先取此处 | 项目 PDF 8 件（7 种内容，见 §2） |
| `output/【2_HighRes_PDF】/` | 高清页图（原 book-pages） | `9787550847224/` 两版 48bit TIFF（3.81 GB）已迁入 |
| `output/【3_Cropped_Tiff】/` | 件级裁片 TIFF（O 件终点） | **暂空**；O 件迁入 rides 下一重出轮（§5） |
| `output/【4_WebP】/` | webp 缓存位 | **空置＝webp 已停产**（2026-10-11 口径，`retire_webp.py` 停线） |

## §2 【1】迁入清单（全部真 mv，含真 sha256 种子）

| sha256（前 16） | 文件 | 大小 | 页数 | 来源 |
|---|---|---|---|---|
| 6b5e5dcae763289d | 秦印类编 检索版.pdf | 2,019,683,630 | 851 | `inbox/20261011/` |
| 0a82f2245d27eba2 | 福庵印缀 原版 高清.pdf | 1,224,531,421 | 236 | `inbox/20261011/` |
| f1d2c4a649fad2c9 | 古玺汇编 文物出版社 罗福颐  ok.pdf | 389,862,492 | 544 | `inbox/20261011/` |
| 6825a09a7ac225ae | 秦汉印典 上海书画 金怀英  1997 ok.pdf | 213,494,738 | 807 | `~/Downloads/` |
| e9c29a6dfb66cfab | 黄牧甫印谱_(西泠印社)_…(z-lib).pdf | 39,722,457 | 132 | `inbox/20261011/` |
| ac36bd40dab90c51 | 古图形玺印汇_(康殷著)_…(z-lib).pdf | 36,785,043 | 292 | `~/Downloads/` |
| 97f892b8fa62e2ef | 吴颐人篆刻作品展示.pdf | 2,098,940 | 32 | `inbox/20261011/` |
| e9c29a6dfb66cfab | tmp.pdf（≡黄牧甫印谱，**不重复入册**） | 39,722,457 | — | 仓根 `./tmp.pdf` |

**盘点差异备查**：2026-10-11 盘点记「古玺汇编/秦汉印典/吴颐人 missing」；三本随后均已寻获
（inbox 两本＋Downloads 一本），本轮迁入后 registry 全部 `status=present`，**当前无 missing 行**
（CLI `--register-missing` 备用）。

## §3 sha 去重口径

* registry 幂等键＝**sha256**（`pdf_records` 表 UNIQUE(sha256)）：同一内容只占一行。
* **同名副本不搬不删**：`~/Downloads/` 仍留 5 份同名副本（秦印类编/福庵印缀/黄牧甫印谱/
  古玺汇编/吴颐人）；入库按 sha 判重，只登记【1】内一份。
* `tmp.pdf` ＝黄牧甫印谱逐字节副本：物理保留于【1】，扫描 CLI 按名跳过不入册
  （避免搬移仲裁把在册行错指到 tmp 名下）。
* 搬移：sha 不变 ⇒ **原行原地更新 `rel_path`**（`moved` 动作）；本机制已真跑验证
  （5 行 inbox→【1】原位改路径）。

## §4 登记库与人工补填

* 库：`var/pdf_registry.db`（**独立库，不入仓**；`data/yinpu.db` 一律不碰）。
  表 `pdf_records`：id / filename / rel_path / sha256 / size_bytes / page_count / page_mm /
  scan_dpi / dir_key / isbn / **dynasty** / **author** / notes / status / created_at / updated_at。
* 朝代值域（15，逐字同值于 xiai `VALUE_DOMAINS.DYNASTY_OPTIONS`，NULL 合法）：
  春秋/戰國/秦/漢/魏晉/隋唐/宋元/明早中期/晚明/清初/清中期/晚清/民國/新中國/當代。
* API（feicui-api :5196，additive）：
  `GET /api/pdf-records`（status/q 筛选＋offset 分页；未白名单参数 400）、
  `PATCH /api/pdf-records/{id}`（dynasty/author/notes，缺省键＝不改；朝代非枚举 ⇒
  400 DYNASTY_INVALID；每次写 `updated_at`）。
* web：前端「**PDF 资料**」页（`/feicui/pdf-records`，vite :5195）：列表＋筛选＋
  行内编辑（朝代下拉＝15 枚举、作者/备注文本）→ PATCH 保存，成功回显 `updated_at`。
* 扫描 CLI：`./venv/bin/python ops/pdf-registry/scan_pdf_registry.py`
  （默认根＝`pdf_source_dir`；`--root` 追加；<100KB 假件与 `tmp.pdf` 跳过；
  幂等重跑零写入——已验证：二跑全 `noop`）。

## §5 取阅口改造（不再从 Downloads 主动读）

* 配置：`config/pdf_source.json`（独立文件，与 `book_dir_keys.json` 职责不同互不读写）：
  `pdf_source_dir`，默认 `output/【1_Original_PDF】`。
* `ops/biblio-metadata/scan_biblio.py`（`PDF_SEARCH_GLOBS`）：
  **【1】/\*\* 最先** → `inbox/**`（旧面回落）→ 仓根 `*.pdf`（旧面回落）；
  **`~/Downloads/*.pdf` 已移出默认搜索面**。
* `server/app/backfill_book_images.py`（`search_dirs_for`/`resolve_pdf`）：
  显式 `--pdf-dir`（覆盖）→ `pdf_source_dir` → `--root`；递归兜底仍走 `REPO/inbox/**`；
  **~/Downloads 移出默认面**。

## §6 book-pages 已迁【2】＋ shim

* `output/book-pages/9787550847224/P29-2400dpi-48bit{,-frozen}.tif` →
  `output/【2_HighRes_PDF】/9787550847224/`（纯 mv，无库引用）。
* 原路径留**同名符号链接**（兼容 shim）：`ops/book-page-2400/crop_c2r1.py`（裁切源）与
  `render_page_2400.py`（OUT_REL）路径常量暂未改；下一重出轮改脚本后**拆除 shim**。
* 两枚 `P29-C*-R1-*-O.tiff`（件级裁片，其中 C2-R1 系并行单 2026-10-14 产出）**留 book-pages**。

## §7 下一重出轮（待办，本轮不做）

1. **O 件迁【3_Cropped_Tiff】**：`output/books/` O 件（906 MB；库内 8455+ 行
   `img_path_tiff` 指向）整体迁入【3】，**单事务**改写 `img_path_tiff`（搬移＋写库同事务，
   杜绝悬空引用）；book-pages 的两枚 O 件同轮迁入。
2. 拆【2】兼容 shim（改 `ops/book-page-2400/` 两脚本路径常量）。
3. `output/seals/`（Kevin 手工整理）、`faces/`、`pairs/`、`samples/` 暂留原位，待裁。
4. 【4_WebP】保持空置；faces 既有 7354 件 webp 的删除与 E6 取图端点处置另立专单。

## §8 红线（本轮已遵守）

不写 `data/yinpu.db`；不动 `output/books/` 与 `output/seals/`；不建 job；不删文件
（同名副本不搬不删）；registry 是新库（var/ 不入仓）；API 改后重启＋自证
（新 pid lstart ≥ 文件 mtime）；只暂存自己文件、永不 `git add -A`。
