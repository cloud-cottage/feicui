# 校正件输出暂停 · 运行手册与证据（Kong / 2026-10-11）

> **口径真源**：`docs/image-original-crop-draft-v0.1.md` **§6（校正件输出暂停，Kevin 2026-10-11，最高优先）**。
> **权威实现面**：`server/app/repository.py`（E6/E5 回落链）、`server/worker/feicui_worker.py`（新 job）、
> `server/app/backfill_book_images.py`（回填 CLI）、`server/app/routers/jobs.py`（E6 路由 docstring）。
> **本目录**：`summary.json`（汇总读数）、`three_state.json`（E6/E5 三态单测）、
> `worker_single_page.json`（worker 单页验证）；脚本 `unit_three_state.py` / `verify_worker_single_page.py` / `gen_summary.py`。

## 0. 一句话

**「非 O 件」＝颜色校正件 `P<页>-C<列>-R<行>.tiff`（V3 双色分层）⇒ 停止生产**；**O 件（`…-O.tiff` 原始切片）是当前唯一在产面**。
已产出的 **8708 件校正件（376.99 MiB）原样保留、不删不改**（删除由 Zang 执行）。E6 取图 / E5 影像缺失的**解析链**
改为 **`img_path_tiff`（校正件）→ 同目录同名 `-O.tiff`（原始切片）→ `img_path`（历史 webp）** ⇒ 校正件停产后取图**自动落 O 件**。

## 1. 改动点（四个文件，均为「暂停生产 + 回落链」，**不改 `stamps` 既有列值、不加列、不建 job**）

| 文件 | 改了什么 |
|---|---|
| `server/app/repository.py` | 新增 `_original_rel_from_tiff`（校正件相对路径 → 同目录同名 `-O.tiff`）；**E6** `find_stamp_image` 与 **E5** `_stamp_image_on_disk` 解析链统一改为 `img_path_tiff` → `-O.tiff` → `img_path`；新增来源常量 `E6_SOURCE_ORIGINAL="img_path_tiff/-O"`。**404 三码不变**（`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`）；越界/绝对路径照旧**拒绝**（不静默换列）。 |
| `server/app/routers/jobs.py` | E6 路由 **docstring 随新回落链更新**（**无逻辑改动**：仍是「有字节就回、命中 TIFF（校正件或 O）即 PIL 解码→`image/png`、404 三码」）。 |
| `server/worker/feicui_worker.py` | `process_page` **停写校正件**：不再跑 `correct_image_v3`、不再落 `P<页>-C<列>-R<行>.tiff`；**只写 `…-O.tiff`**。`img_path_tiff` **仍回校正件的约定路径**（不落盘），由 E6/E5 回落处理。`write_tiff_idempotent_pixels` 返回值加 `sha256`；`img_sha256`/`img_bytes`/`img_written` 改取**实际落盘的 O 件**。`colorcal` 模块**按路径加载保留接线**（恢复生产一行接回）。 |
| `server/app/backfill_book_images.py` | 新增 `--write-corrected`（`WRITE_CORRECTED_DEFAULT=False`，**默认关**）；`process_book` 增 `write_corrected` 门控「跑 V3 + 写校正件」；`write_db`（加法三列）与校正件**同生同灭** ⇒ 默认只写 O **不写库**；默认 `layout="original-only"`；`--no-original` 且未给 `--write-corrected` ⇒ **rc=2（无事可做）**。 |

**默认行为对照**：`--all`（无附加开关）＝**只写 O**（不跑 V3、不写校正件、不写库）；`--orig-only` 照旧（只补 O 的最省路径）；
写校正件须显式 `--write-corrected`。⇒ **默认路径不触碰任何已有校正件**。

## 2. 单测 / 验证读数（**全部真读数**）

### 2.1 E6/E5 回落链三态单测（`three_state.json`；**scratch 目录伪造三态，未触及真文件**）

用 `./server/.venv/bin/python`（接口层解释器，**纯 stdlib**，证明回落链不引图像栈）直调 `app.repository.find_stamp_image` / `missing_items`：

| 场景 | 期望 | 实读 |
|---|---|---|
| **仅校正件** | 用校正件 | ✔ `source=img_path_tiff`，abs 指 `P1-C1-R1.tiff` |
| **仅 O**（校正件不在盘、`-O.tiff` 在盘） | 用 O（**新回落**） | ✔ `source=img_path_tiff/-O`，abs 指 `P1-C1-R2-O.tiff` |
| **皆无** | `IMAGE_UNAVAILABLE` | ✔ `IMAGE_UNAVAILABLE`（E6 404 第三类） |
| 附带：无 tiff、仅 legacy webp | 用 `img_path` | ✔ `source=img_path` |

E5 读数：仅校正件 / 仅 O **两态都不计缺失**；仅「皆无」计 `file_missing`（`missing_idx=[2]`）。**ALL PASS**。

### 2.2 worker 单页函数级验证（`worker_single_page.json`；**三重定向到 scratch**）

`FEICUI_ROOT=仓根`＋`FEICUI_FACES_DIR`/`FEICUI_BOOKS_DIR`=scratch ⇒ 不触 `output/faces/**`、`output/books/**`；
`吴颐人篆刻作品展示.pdf` p8（检出 **4** 枚）：**新写校正件 = 0** ／ **新写 O = 4**；各枚 `img_path_tiff` 约定路径**不在盘**、同名 `-O.tiff` **在盘**、旧 webp **不在盘**；返回值 `col/row/img_sha256/img_bytes` 齐备。**ALL PASS**。

### 2.3 回填 CLI 默认面（scratch `--out-root`，`--no-write-db`）

- **默认**（无开关）：`写校正件 = OFF ｜ 写库 = OFF`，`layout=original-only` ⇒ **校正件新写 0 / O 新写 4**；10 列指纹 **before ≡ after=True**。
- **`--write-corrected`**：`写校正件 = ON` ⇒ **校正件新写 4 / O 新写 4**（历史形态仅在显式开关下成立）。

### 2.4 现存行活体回归（活 API，端口 5196，job `job-90344a7802954afdaad447d875f2e15b`）

- **E6**：`GET /api/jobs/<job>/stamps/40/0/image` ⇒ **200**、`content-type: image/png`、PNG magic `89504e47…`、
  `x-feicui-img-path: output/books/秦印类编 检索版/P40-C1-R6.tiff`（既有行校正件在盘 ⇒ 仍服务校正件，**行为不变**）。
- **E5**：`GET /api/jobs/<job>/missing?kind=image` ⇒ **count 0**。
- **404 三码**：bogus job ⇒ `JOB_NOT_FOUND`；越界页 ⇒ `STAMP_NOT_FOUND`；`IMAGE_UNAVAILABLE` 由 §2.1 三态单测覆盖。

### 2.5 活进程自证（`summary.json.api_liveness`）

`POST http://127.0.0.1:5555/api/restart {"sid":"feicui-api"}` ⇒ 新 pid **53674**、`lstart = Sun Oct 11 12:01:25 2026`；
`repository.py` mtime `12:01:20`、`routers/jobs.py` mtime `12:01:24` ⇒ **活进程启动时刻 ≥ 被改源文件 mtime** ✔。
（`worker` / 回填 CLI **不**被 API 进程加载，故不在该判据内——它们的验证见 §2.2 / §2.3。）

## 3. 红线核对

| 红线 | 核对 |
|---|---|
| ① 不删 / 不改任何已有校正件与 O 件 | 本单**零删除、零覆写**；`output/books/**` 实读 **8708 校正件 + 8708 O = 17416 tiff**（不变），样本 mtime 未变 |
| ② 不改 `stamps` 列值 / 不加列 / 不建 job / 不写 `jobs`\|`job_pages` | 全程 `--no-write-db`；10 列指纹 before ≡ after **True**；无任何 job 写 |
| ③ 不碰印章线 / `output/faces/**` | worker 验证三处定向到 scratch；`faces/**` 未写 |
| ④ 只暂存自己的文件、永不 `git add -A` | commit 用**显式 pathspec**（4 个源文件 + `ops/corrected-pause/`）；`git diff --cached --name-only` 已核，**未带入**他人 `docs/` |
| ⑤ 进程名单 | 跑前 `pgrep -fl "app.pool\|feicui_worker"` 记名单；**未杀任何他人进程**（只按 sid 重启 `feicui-api`） |
| ⑥ 图像栈只在 `feicui/venv` | worker / 回填烟测用 `./venv/bin/python`；接口层回落单测用 `./server/.venv/bin/python`（**纯 stdlib**、不 import cv2/numpy/pymupdf） |
| ⑦ 改 `server/app/**` 后重启 API 并自证 | 见 §2.5 |

## 4. 源文件 md5（`summary.json.sources.md5`）

| 文件 | md5 |
|---|---|
| `server/app/repository.py` | `2212253c336b52a2c057ca6bce80fa3e` |
| `server/app/routers/jobs.py` | `405f75970db486271903fd3d0b40406c` |
| `server/worker/feicui_worker.py` | `fd0ecd88f4e0810d5a36dc085890b9e8` |
| `server/app/backfill_book_images.py` | `4070e71f53f9d9d10f975cfa1621b246` |

## 5. 恢复条件

Kevin 确定新的颜色 / 图像处理算法后另行下令开启；恢复动作：worker `process_page` 接回 `colorcal.correct_image_v3` + 写校正件（一行接回）；
回填 CLI 加 `--write-corrected`（已就位）。本文件的 §1–§5（O 件）不受影响、继续有效。
