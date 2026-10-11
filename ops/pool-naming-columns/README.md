# ops/pool-naming-columns —— P0「池侧写库丢 col/row/img_path_tiff」修复 ＋ 补齐缺列行 ＋ 旧证据纠偏

**单**：Kong（实现）· 2026-10-11 · 质检来源＝Neng 独立质检 **F1**（P0 真缺陷）。
**范围**：印谱解析线（`server/app/repository.py` 写库路径 ＋ `server/app/backfill_book_images.py` 补数据 ＋
`ops/worker-naming/verify_worker_naming.py` 旧证据纠偏）。
**红线合规**：不建 job、历史行旧 10 列一字不改、不碰 `output/faces/**`、不删文件、不碰 `docs/**`。

---

## 1. P0 根因（已复核）

池侧写库路径**丢列**：

- `server/app/repository.py::_upsert_stamp` 的 `stamps` **INSERT 只写旧 10 列**
  （`pdf_name,page,idx,text,img_path,x1,y1,x2,y2`）；
- `commit_chunk` 传给 `_upsert_stamp` 的行 dict 也只带旧 10 列。

⇒ **新 job 行的 `col`/`row`/`img_path_tiff` 恒为 NULL**。

**实证**：新书 **黄牧甫印谱**（job `job-64bd6bebd36240a7b338c02c813302da`，**DONE**、1–50 页、**200 行**）：

- TIFF **已实际写出 200 件**（`output/books/黄牧甫印谱/`）；
- 但 200 行 `img_path_tiff` 为空、`img_path` 指 `output/faces/HMF/*.webp`（该批 webp 已按 Kevin 指令删除）；
- ⇒ 该书结果页「取裁图」**全 404（IMAGE_UNAVAILABLE）**。

## 2. 修复（写库路径）

`server/app/repository.py`：

| 处 | 改动 |
| --- | --- |
| `_upsert_stamp` INSERT | 带上 `col`/`row`/`img_path_tiff`；**新行 `img_path` 写 NULL**（该列语义＝历史 webp 面、已退场，不再写「虚拟 webp 路径」） |
| `commit_chunk` | 把 worker item 的 `col`/`row`/`img_path_tiff` 传入写库行 dict；`img_path` 传 `None` |
| `_upsert_stamp` update 分支 | 带上三新列；传入 `img_path` 为空时**保留既有值** ⇒ **绝不抹掉历史行既有 `img_path`**（红线） |

> 默认行级幂等 arm（`on_conflict=skip`）非 `update` 时**不覆盖任何既有行** ⇒ 历史行 `img_path` 值一字未改。

## 3. 补齐现有缺列行（幂等「只补缺列」模式）

`server/app/backfill_book_images.py` 新增 `--fill-missing-cols`：

- **只对缺列行**补 `col`/`row`/`img_path_tiff`；**`img_path_tiff` 已有效且在盘的行跳过**；
- 按库内 bbox（`x1..y2`，**不重跑检测**）用 `naming.assign_cr` 复算 (C,R) ⇒ 期望路径
  `output/books/<目录键>/P<页>-C<列>-R<行>.tiff` **必须在盘**才更新，否则逐条入失败清单；
- **不渲染、不重出图、不写 `img_path`**（现有 10 列一字不改）。

**真库跑（黄牧甫）**：

| 轮 | 行 | 补 | 跳 | 失败 | GREEN |
| --- | --- | --- | --- | --- | --- |
| 首跑（`backfill_fill_summary.json`） | 200 | **200** | 0 | 0 | ✓ |
| 复跑（`backfill_fill_rerun.json`，**幂等**） | 200 | 0 | **200** | 0 | ✓ |

## 4. 验证读数

### 4.1 写库路径（scratch 副本库，20 行；不建生产 job）

`write_path_probe.py` → `write_path_probe.txt`：`commit_chunk` 直调

- 20 行：`col` NULL=0 / `row` NULL=0 / `img_path_tiff` NULL=0 / **`img_path` NOT NULL=0（落 NULL）**；
- 同 items 二次提交（update arm）⇒ **skipped=20、updated=0**（幂等）；
- 历史行（`tmp.pdf` p13 idx0）走 update arm：`img_path` **保留既有值**（红线）；
- E6 来源列 = `img_path_tiff`；E5 image count = 0。

### 4.2 真库修复（黄牧甫 200 行）

| 读数 | 值 |
| --- | --- |
| 现有 10 列指纹（全表 7472 行）before ≡ after | `ee16bc755096239e…` **相同** |
| 现有 10 列指纹（黄牧甫 200 行）before ≡ after | `fa32d9fc93f3dab2…` **相同** |
| 黄牧甫 `col`/`row`/`img_path_tiff` NULL | 0 / 0 / 0 |
| 黄牧甫 `img_path` 逐 id 比对基线 | **逐字相同**（仍指 `output/faces/HMF/*.webp`） |
| 全表 `col`/`img_path_tiff` NULL | 0 / 0 |

### 4.3 E6 活体（`e6_readout.txt`）

```
GET http://127.0.0.1:5196/api/jobs/job-64bd6bebd36240a7b338c02c813302da/stamps/13/0/image
=> 200 OK
   content-type: image/png
   x-feicui-img-path: output/books/%E9%BB%84%E7%89%A7%E7%94%AB%E5%8D%B0%E8%B0%B1/P13-C1-R1.tiff
   png magic 89504e47…（343×341 RGB，79,182 B）
```

⇒ **p13 idx0 → 200 / image/png**，`x-feicui-img-path` 指 `output/books/黄牧甫印谱/P13-C1-R1.tiff`。

### 4.4 E5 活体（`e5_readouts.json`）

```
GET .../missing?kind=image => {"kind":"image","count":0,"items":[]}
GET .../missing?kind=text  => count=185（既有事实，与本单无关）
```

⇒ **E5 不误报该书影像缺失**。

### 4.5 活进程吃到新码

`feicui-api` 重启后 pid **57377**，`lstart = 2026-10-11T10:51:59` ≥
`server/app/repository.py` mtime `2026-10-11T10:50:40`（**≥ 成立**）。

## 5. 复跑命令

```bash
cd /Users/kevin/bistro/xiai/feicui

# ① 写库路径探针（scratch 副本库；不建生产 job、不碰生产库/output）
python3 ops/pool-naming-columns/write_path_probe.py

# ② 「只补缺列」幂等模式（不渲染；img_path_tiff 已有效且在盘的行跳过）
./venv/bin/python server/app/backfill_book_images.py \
  --book "黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf" \
  --fill-missing-cols --no-migrate \
  --evidence-dir ops/pool-naming-columns --summary-name backfill_fill_summary.json
#   （复跑第二次 ⇒ 应 filled=0 / skipped=200，证明幂等）

# ③ E6 / E5 活体（先确认 API 活进程启动时刻 ≥ 被改源文件 mtime）
curl -s -D - -o /tmp/e6.png "http://127.0.0.1:5196/api/jobs/job-64bd6bebd36240a7b338c02c813302da/stamps/13/0/image"
curl -s "http://127.0.0.1:5196/api/jobs/job-64bd6bebd36240a7b338c02c813302da/missing?kind=image"
```

## 6. 旧证据纠偏（F3）

`ops/worker-naming/verify_worker_naming.py` **已作废**（其断言的是旧「双份输出」口径，对应 commit
`f9be1d4`；该口径**已被 commit `58c879f` 取代**为「只出 TIFF」）。且它用 `git show HEAD:` 取「改造前」源码，
而 HEAD 现已是新码 ⇒ **跑它必然误判**。

处置：

- 脚本头 ＋ `main()` 起手加**醒目作废横幅**；默认**拒绝运行**（**exit 3**），仅
  `FEICUI_RUN_DEPRECATED_VERIFY=1` 才强制复跑（只作历史对照，**不得写进任何验收结论**）；
- `ops/worker-naming/README.md` 顶部同步加**作废横幅**。

## 7. 改动的文件

- `server/app/repository.py`（写库路径）
- `server/app/backfill_book_images.py`（`--fill-missing-cols` 幂等模式）
- `ops/worker-naming/verify_worker_naming.py`、`ops/worker-naming/README.md`（作废纠偏）
- `ops/pool-naming-columns/**`（本证据目录）

## 8. 红线核对

| 红线 | 结果 |
| --- | --- |
| 历史行旧 10 列一字不改 | ✓ 全表 + 黄牧甫子集指纹 **before ≡ after** |
| 不建 job（生产库不新建 jobs/job_pages） | ✓ 只 UPDATE 既有 `stamps` 行的加法列 |
| 不碰 `output/faces/**` | ✓ 一字未碰（HMF 目录仍空） |
| 不删文件 | ✓ 未删（scratch 探针副本自清理） |
| 不碰 `docs/**` | ✓ |
| 只暂存自己文件、显式 pathspec、永不 `git add -A` | ✓ 提交前 `git diff --cached --name-only` 核 index |
