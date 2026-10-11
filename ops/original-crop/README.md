# 印面「原始切片 `-O`」收尾 · 运行手册（Kong / 2026-10-11）

> 口径真源：`docs/image-original-crop-draft-v0.1.md`（§2 默认口径 / §4 验收候选 O-1〜O-5）。
> 权威实现面：`server/app/naming.py`（命名）、`server/app/backfill_book_images.py`（回填 CLI）、
> `server/worker/feicui_worker.py`（新 job）。
> **本目录只读复算脚本**：`verify_original_crop.py`（独立复算，不复用回填中间态）。

## 0. 一句话

每枚印面在**已有的颜色校正件** `P<页>-C<列>-R<行>.tiff` 之外，**另出一份未做颜色处理的原始切片**
`P<页>-C<列>-R<行>-O.tiff`（大写 `O`、短横分隔、不补零），**同目录、同 bbox / 同渲染倍率（400 dpi）、同尺寸**。
编码裁决：**TIFF · RGB 8-bit · Deflate ＋ `Predictor=2`**（Zang 实测：deflate 均 391.9 KB → +Predictor 均 289.7 KB，
解码像素与原片**逐像素相等**；`lzw` 反 137.5% ⇒ 不用）。

**校正件 `P-C-R.tiff` 的编码与字节一字不动**（`encode_tiff` / `write_tiff_idempotent_pixels` 的
`predictor=None` 分支逐字节与既往一致）。

## 1. 幂等判据（**不得按文件 sha256**）

`write_tiff_idempotent_pixels(path, arr, …, predictor=…)`：

- 文件已存在 且 **解码像素逐像素相等**（含 shape/dtype）**且** 容器合要求
  （`Compression=8` ∧ `Predictor==predictor`）⇒ **不重写、不动字节**；
- 否则覆盖写（`predictor` 非空 ⇒ `tiffinfo={317: predictor}`）。
- `predictor=None`（校正件路径）⇒ 只按解码像素判、**不查 / 不改编码** ⇒ 校正件字节一字不动（红线①）；
- `predictor=O_TIFF_PREDICTOR(=2)`（O 件路径）⇒ **旧编码 O 件（deflate-only）被自动升级重写**为
  `deflate+Predictor=2`；重写后复跑即按「像素＋容器」双判跳过。

> Pillow `tiff_deflate` 在大图上逐字节非确定（末 strip 对齐填充未初始化）⇒ 判据必须按**解码像素**。

## 2. 复跑命令（本收尾**实跑过**的三条；子集 ＝ 7 本书 × 13 页 ＝ **213 枚**）

```bash
cd /Users/kevin/bistro/xiai/feicui
BOOKS=( --book "秦印类编 检索版.pdf" --book "福庵印缀 原版 高清.pdf" \
        --book "吴颐人篆刻作品展示.pdf" \
        --book "黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf" \
        --book "秦汉印典 上海书画 金怀英  1997 ok.pdf" --book "tmp.pdf" \
        --book "古玺汇编 文物出版社 罗福颐  ok.pdf" )
PAGES=( --pages 5 --pages 8 --pages 13 --pages 17 --pages 18 --pages 19 --pages 24 \
        --pages 26 --pages 29 --pages 30 --pages 40 --pages 118 --pages 300 )

# ① 子集复测（--no-migrate --no-write-db ⇒ 不迁移、不写库）——自动把旧编码 O 件升级重写为 deflate+Predictor=2
venv/bin/python server/app/backfill_book_images.py "${BOOKS[@]}" "${PAGES[@]}" \
  --no-migrate --no-write-db --evidence-dir ops/original-crop --summary-name subset_run_2.json

# ② 幂等复跑（应「0 新写 / 213 跳」）
venv/bin/python server/app/backfill_book_images.py "${BOOKS[@]}" "${PAGES[@]}" \
  --no-migrate --no-write-db --evidence-dir ops/original-crop --summary-name subset_run_3.json

# ③ 独立复算（报 Predictor ＋ O-2 新判决式 ＋ 校正件 sha256 before≡after）
venv/bin/python ops/original-crop/verify_original_crop.py "${BOOKS[@]}" \
  --page 5 --page 8 --page 13 --page 17 --page 18 --page 19 --page 24 --page 26 \
  --page 29 --page 30 --page 40 --page 118 --page 300 \
  --corrected-hashes-before ops/original-crop/corrected_sha256_before.json \
  --out ops/original-crop/subset_verify.json
```

> 注：回填 CLI 的页开关是 **`--pages`**（复数、对所有选中书生效）；复算脚本是 **`--page`**（单数）。

## 3. 子集读数（实跑，2026-10-11）

| 项 | 读数 |
|---|---|
| 行数 / O 件 | **213 / 213**（7 书 × 13 页） |
| ① 复测 | O **新写 213 / 跳 0**（校正件 新写 0 / 像素一致跳 213） |
| ② 幂等复跑 | O **新写 0 / 跳 213** |
| O 件总体积 | **32,313,650 B ＝ 30.817 MiB**（重写前 deflate-only ＝ 37,987,836 B / 36.228 MiB ⇒ **85.1%**） |
| O 均值 | **151,707.3 B/件** |
| O 单张最大 | **1,691,450 B（1.613 MiB）** ＝ `output/books/黄牧甫印谱/P40-C1-R1-O.tiff` ⇒ **≤ xiai `store` 4 MiB ✔** |
| O-1 命名 | 合正则 **213/213**、与校正件名派生一致 213/213、缺 0 |
| O-2 原始性 | 解码像素 ≡ 400 dpi 渲染原片 **213/213**；「O ≠ 校正件」**197 ＝ V3-applied 197** ⇒ 判决 ✔ |
| O-3 几何 | O 与校正件尺寸逐行相等 **213/213** |
| O-4 容器 | `mode=RGB ∧ Photometric=2 ∧ Compression=8 ∧ Predictor=2` **213/213** |
| O-5 双向对账 | 库期望 213 / 盘上 O 213 / 盘上校正件 213；缺 0 / 孤儿 0 |
| 校正件字节未变 | `sha256` before ≡ after **213/213 unchanged**、changed 0、missing 0 ✔ |
| 10 列指纹 | before ≡ after **True** |
| 判决 | O-1〜O-5 ＋ `corrected_bytes_unchanged` **全 TRUE（ALL PASS）**；失败清单 0 条 |

### ★ O-2 判决式修正（2026-10-11；Zang 采纳 Kong 上轮发现的项）

「O ≠ 校正件」**只在 V3 生效的行成立**：V3 `skipped(ink_ratio<2%)` 的行里 V3 是 **no-op** ⇒ 校正件本就 ≡ 原片
⇒ **O == 校正件合法**。故判决式 ＝

```
eq_render == 行数   且   count(O ≠ 校正件) == V3-applied 的行数
```

（`v3_applied` 由 `colorcal.correct_image_v3(crop)` 返回报告里的 `mode=="applied"` 分类。）
子集读数：`decoded_pixels_equal = 213`（== 行数）、`differ = 197 == v3_applied = 197` ⇒ **O-2 由旧判决的
`false`（197 ≠ 213）改为 `true`**。

## 4. 红线核对（本收尾逐条自证）

| 红线 | 核对 |
|---|---|
| ① 校正件字节不得变 | `verify_original_crop.py --corrected-hashes-before …` ⇒ **213/213 unchanged、changed 0**；编码分支 `predictor=None` 逐字节不变 |
| ② 不改 `stamps` 列值、不加列 | 全程 `--no-migrate --no-write-db`；回填报 10 列指纹 before ≡ after **True**；不建 job、不写 `jobs`/`job_pages` |
| ③ 不删文件 | 只增 / 覆盖 O 件；盘上遗留 webp 只列不删 |
| ④ 不碰印章线 / `output/faces/**` | 只动 `output/books/**` 的 O 件；`faces/**` 不写 |
| ⑤ 只暂存自己的文件、永不 `git add -A` | 显式 pathspec：`server/app/naming.py` `server/app/backfill_book_images.py` `server/worker/feicui_worker.py` `ops/original-crop/`（`git diff --cached --name-only` 核过、无越界） |
| ⑥ 图像栈只在 `feicui/venv` | 三条命令一律 `venv/bin/python` |
| ⑦ 进程名单 | 跑前 `pgrep -fl "app.pool\|feicui_worker"` 记名单（空） |

## 5. 全量命令（**由 Zang 跑；Kong 不跑**）

```bash
# 全量只补 O 件：8,708 枚（口径件 §2「范围」）
cd /Users/kevin/bistro/xiai/feicui
venv/bin/python server/app/backfill_book_images.py --all --orig-only \
  --no-migrate --no-write-db --evidence-dir ops/original-crop --summary-name full_orig_only.json
```

- **`--orig-only`**：每次裁切**只写 `…-O.tiff`**，**不跑 V3、不写校正件、不写库** ⇒ **天然守红线**
  （不动既有校正件、不写 `stamps`、不加列、不建 job）。
- **幂等 / 可中断重入**：判据按「解码像素 ＋ 容器」双判；已落盘且合规的 O 件跳过，
  崩溃或中断后**重跑同命令即续**（已完成件跳过、未完成件补写），**不产生重复、不覆盖既有校正件**。
- 体量口径（诚实登记，**以实测为准**）：按子集均值（重写后 151,707 B/枚）外推 ≈ **1.26 GB**；
  样本均值差异可达 3 倍（口径件 §3.3）——**两值均不作结论**，全量总体积以 `full_orig_only.json` 读数为准。

## 6. 本目录文件

| 文件 | 说明 |
|---|---|
| `verify_original_crop.py` | 独立复算脚本（只读；唯一写件 ＝ `--out` 汇总 JSON） |
| `corrected_sha256_before.json` | 213 件校正件 before 指纹（红线①自证用） |
| `subset_run_1.json` | **重写前**（deflate-only）子集回填读数（留痕，37,987,836 B / 36.228 MiB） |
| `subset_run_2.json` | ① 子集复测读数（O 新写 213 ⇒ Predictor=2） |
| `subset_run_3.json` | ② 幂等复跑读数（O 新写 0 / 跳 213） |
| `subset_verify.json` | ③ 独立复算读数（O-1〜O-5 ＋ 校正件未变；**ALL PASS**） |
