# 印章线接手收尾（第一段）· 续跑报告

> 接手单（Kong）。仓 `/Users/kevin/bistro/xiai/feicui`（main）。
> 本单**只做到「台账跑完 + 报计数」**；出包 / 证据包 / 浏览器 / 构建 / 提交留给下一单。
> **未 push、未提交**（`server/app/seals.py` 仍为未跟踪文件 `??`）。

## 0. 起点状态（动手前现查）

- 起点 HEAD ＝ `0c78dd01efd5795a01427e26da4e00f45e6c100c`（`docs(feicui): v1.14→v1.15 …`）。
  `git status --porcelain` 里本线相关：`?? server/app/seals.py`、`?? server/app/routers/seals.py`、
  `?? web/src/{api/seals.js,pages/SealsPage.vue}`、` M server/app/{config.py,main.py,requirements.txt}`、
  `?? ops/seal-ingest/`（另有 Jing 并行改的 `docs/**` —— **本单未碰**）。
- **并行线在跑单期间提交过**：HEAD 于 17:34 由 `0c78dd0` 前进到 `d73565a`
  （`docs(feicui): spec v1.15→v1.16 — 印章影像面三态分桶(source_no_image)+共用窗口限流+AC-47〜AC-52`，仅 `docs/**`）。
  **本单未提交、未 push**；`server/app/seals.py` 到收尾仍是未跟踪文件。
- `var/seal_ingest.db` 起点台账：`seal_images` 共 **690** 行 ⇒ `ok=584 / failed=104 / source_no_image=2`（子因全为 `nan_ref`）。
- 目标 ref 数 **6765** ＝ yt **3679**（含 2 个 `NaN_`）＋ ytsw **2627** ＋ yzbk **459**（实测 `seals` 3679 行，逐列非空计数吻合）。

## 1. 导入修复（第一步）

- 症状：`write_package` 引用**未定义**的 `source_missing_compact` ⇒ 文件不可导入。
- 修法（上一任给定，逐字照做，**未回退/未重写任何既有改动**）：
  - 在 `image_policy = {`（现 L2038）之前插入
    `source_missing = build_source_missing_summary(db_path)` ＋
    `source_missing_compact = {k: v for k, v in source_missing.items() if k != "rows"}`；
  - `db_path` 与 `write_package(*, db_path: Path, …)` 签名一致 ⇒ 无需改名。
- 接进两处（上一任未接完）：
  - `manifest`：新增顶层 `"source_missing": source_missing_compact`（＋ 原有 `image_policy.source_missing` 保留）。
  - `report`：新增顶层 `"source_missing": source_missing`（含 `rows` 全量，供证据用）。
- **自证①** `python -c "import ast;ast.parse(open('app/seals.py').read())"` ⇒ `ast ok` **PASS**
- **自证②** `cd server && ../server/.venv/bin/python -c "import app.seals; print('import ok')"` ⇒ `import ok` **PASS**

## 2. 幂等补转（convert-images）

```
../server/.venv/bin/python -m app.seals convert-images --db ../var/seal_ingest.db
=> {"total": 584, "done": 584, "converted": 0, "skipped": 584, "missing": 0, "failed": 0}   FAILURES=[]
```
与上一任结论一致（584 行 `ok` 的 TIFF 已全回填）⇒ **converted=0**，无待补。

## 3. 影像分片跑量（第二步 · 本单主交付）

- 跑法：`ops/seal-ingest/run_shards.sh`（本单新增）——每片
  `sync-images --batch-id seal_20261010_01 --img-workers 8 --img-delay 0.1 --img-limit 2500`，
  **单片墙钟硬上限 500s（看门狗 kill -TERM→-9）**、**片间停 25s**、幂等 resume；
  终态（`ok`＋`source_no_image`）达 6765 / 连续 2 片零进展 / 30 片上限即停。
  日志 `ops/seal-ingest/11_shard.log`，逐片进度 `ops/seal-ingest/11_shard_progress.json`。
- **resume 有效**：片内 `skipped` 即「已存在且 sha256 一致 ＋ TIFF 就绪」的 ref；**从未从头重跑**。

| 片 | 起(UTC+8) | 止 | 片前终态 | 片后终态 | 片后 ok | 片后 no_image |
| -: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 17:51:02 | 17:59:22（看门狗 500s） | 765 | 1566 | 1343 | 223 |
| 2 | 17:59:47 | 18:05:21（看门狗 500s） | 1566 | 4061 | 3808 | 253 |
| 3 | 18:05:46 | 18:14:06（看门狗 500s） | 4061 | 6215 | 5904 | 311 |
| 4 | 18:14:31 | 18:22:51（看门狗 500s） | 6215 | 6648 | 6253 | 395 |
| 5–7 | 18:23:16 | 18:26:21 | 6648 | **6764** | 6347 | 417 |

（片 5–7 是收尾片；第 6、7 片零进展 ⇒ 按「连续 2 片零进展」停手，`[runner] DONE`。）

## 4. 终态四桶计数（**本单交付**）

| 桶 | 计数 | 说明 |
| --- | ---: | --- |
| `ok` | **6347** | 源 JPEG 取到 ＋ 已无损转 TIFF（内容寻址缓存） |
| `source_no_image` | **417** | 源侧无图/坏图，**非采集失败** |
| ↳ 子因 `http_500` | 415 | 有界重试（3 轮 2/8/30s）后仍 5xx ⇒ 源侧坏图 |
| ↳ 子因 `nan_ref` | 2 | ref 以 `NaN_` 开头（源侧本就无图） |
| `failed` | **1** | 见 §6（非 5xx，属「200 但字节不是图」的边缘例） |
| 合计 | **6765** | ＝ 目标 ref 数（逐 ref 一行，无缺行/无多行） |

按 kind：

| kind | 目标 | ok | source_no_image | failed |
| --- | ---: | ---: | ---: | ---: |
| yt | 3679 | 3464 | 214 | 1 |
| ytsw | 2627 | 2424 | 203 | 0 |
| yzbk | 459 | **459** | 0 | 0 |

## 5. 源侧缺图清单 `ops/seal-ingest/08_source_missing.json`（本单新增）

- 由 `build_source_missing_summary()`（即修好后被 `write_package` 调用的同一函数）生成。
- `total=417`、`by_reason={'http_500':415,'nan_ref':2}`、`by_kind={'yt':214,'ytsw':203}`、
  **`by_prefix` 共 51 组**（kind × ref 前缀 × 子因，各带 ≤5 个样例 `seqid`）。
- 前缀分布（yt ≡ ytsw，两路同坏）：前缀 `2–24` 为主（单前缀 4–14 条），另有 `38/39`（yt）、`64`（ytsw）；
  `NaN` 前缀 2 条（`seqid 3921/3922`）。样例：`yt/prefix=17 n=14 → seqid 1045,1046,1047,1048,1049…`。
- 独立复核（非复用自测）：对 24 个 `yt` ref 用 `curl` **1 req/s 串行**复测 region `seqid 1381–1460`
  ⇒ `200=6 / 500=16 / other=2` ⇒ **500 是源侧持久坏图，不是限流**；全库抽样 40 ref（每 85 个取 1）
  ⇒ `200=38 / 302=2 / 500=0` ⇒ 站点整体健康。**全程 0 次 429**。

## 6. 唯一 `failed` 行（需下一单裁定口径）

```
seqid=3609 kind=yt ref=2_3609_1
error: tiff_convert: cannot identify image file '…/var/seal_images/yt/3609.jpg'
独立复测：curl -L https://yin.fudan.edu.cn/iiif_proxy/api/char_proxy/2_3609_1
  => HTTP 200, Content-Type: image/jpeg, bytes=697
     前 16 字节 = "Server: iipsrv/1.1\r\nContent-Type…"
     ⇒ iipsrv 把**自己的响应头当正文吐了出来**（697B），根本不是 JPEG，持久复现。
```
- 这是「200 ＋ 冒充 image/jpeg 的坏字节」，**第三个源侧子因（坏字节 / 非图）**，现有口径只有
  `nan_ref` / `http_500` 两种 ⇒ 它落进了 `failed`（非终态）。
- **本单不改口径**（新增子因属行为/规范变更，规范在 Jing 并行线 ⇒ 出本单范围）。
  建议下一单：在 `seals.py` 增 `NO_SOURCE_BAD_BYTES="bad_bytes"`（PIL 解码失败 ⇒ 落
  `source_no_image`＋该子因），并在 `docs/feicui.spec.md` 按 §0.4 升版登记。
  在此之前 resume 每次都会重取它 1 次（1 个 ref，成本可忽略；分片器已按「零进展」自动停）。

## 7. 自检（本单实测）

- `ok` 行**逐行**校验：本地 JPEG 存在 ＋ 字节 sha256 与台账一致 ＋ TIFF 就绪 ⇒ **6347/6347 通过，0 不合**。
- 磁盘：`var/seal_images_tiff/**.tiff` ＝ **6347**（与 `ok` 行一致）；`var/seal_images/**/*.jpg` ＝ **6348**
  （多出的 1 个即 §6 的坏字节文件 `yt/3609.jpg`）；**`.part` 残片 0 个**（看门狗 kill 未留垃圾）。
- 台账行数 6765 ＝ ref 数 6765 ⇒ 无重复 / 无遗漏。

## 8. 下一单继续命令

台账已跑完（除 §6 那 1 行）；直接进「出包 ＋ 证据」：

```bash
cd /Users/kevin/bistro/xiai/feicui/server
# ① 出包（零联网重建，含 images/ 内容寻址 TIFF ＋ images_manifest.jsonl ＋ source_missing 段）
../server/.venv/bin/python -m app.seals package --db ../var/seal_ingest.db --batch-id seal_20261010_01
# ② 若需再核台账（幂等，预期 0 增量；仅 §6 的 1 个 ref 会被重取）
../server/.venv/bin/python -m app.seals sync-images --db ../var/seal_ingest.db \
  --batch-id seal_20261010_01 --img-workers 8 --img-delay 0.1 --img-limit 2500
```
