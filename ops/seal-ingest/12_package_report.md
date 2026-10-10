# 印章线第二段（收尾）· 出包 / 证据 / 浏览器 / 提交报告

> 接手单（Kong · 第二段）。仓 `/Users/kevin/bistro/xiai/feicui`（main，HEAD `d73565a`）。
> 本单：**补 `bad_bytes` 子因使 `failed` 归零 → 出就绪包 → 逐条自检 → 复跑对拍 09_upscale_probe →
> 门禁/幂等/API 证据 → 真浏览器与构建 → 提交（不 push）**。
> 前两任已完成的后端/前端/库/影像台账**已在盘、勿重做不回退**；本单对 `server/app/seals.py` **只追加不回退**。

## 0. 起点状态（动手前现查）

- HEAD ＝ `d73565a8da8ff802cae1987d0e7d4ddac3dae6a0`（`docs(feicui): spec v1.15→v1.16 …`）。
- `git status --porcelain`：`M server/app/{config,main}.py`、`M server/requirements.txt`、
  `M web/src/{App.vue,router/index.js}`、`?? ops/seal-ingest/`、`?? server/app/seals.py`、
  `?? server/app/routers/seals.py`、`?? web/src/api/seals.js`、`?? web/src/pages/SealsPage.vue`。
- `var/seal_ingest.db`：`seals=3679`、`seal_links=8964`、`seal_images=6765`（`ok=6347` / `source_no_image=417` /
  `failed=1`）；`var/seal_images_tiff/**.tiff`＝`6347`。

## 1. 补第三个源侧子因 `bad_bytes`（代码路径重跑 ⇒ `failed` 归零）

**代码改动（`server/app/seals.py` 只追加）**：
- 常量 `NO_SOURCE_BAD_BYTES = "bad_bytes"` ＋ `NO_SOURCE_REASON_NOTE` 增该条注（口径：HTTP 200 且
  content-type=image/jpeg，但正文非可解码影像 ⇒ 源侧坏字节，持久复现）。
- 新纯函数 `is_undecodable_image_error(exc)`（`PIL.UnidentifiedImageError` / `'cannot identify image file'` ⇒ True）。
- `_fetch_convert_one`（并发路径）与 `download_images`（串行路径）的 TIFF 转换 except 分支：若判别为
  「不可解码」，返回/落 **`source_no_image` ＋ 子因 `bad_bytes`**（**不再落 `failed`**），`error` ＝
  `HTTP 200 image/jpeg but undecodable (697B)`；两路径返回体增 `no_source_bad_bytes` / `bad_bytes` 清单。
- `_no_source_reason_of` 认 `bad_bytes`；`image_policy.no_image_rule` 文案改为**三条子因**。
- 附带修一处**既有缺陷**：`finish_batch` 原按 `BATCH_FINISH_FIELDS` 全字段写，影像子流程只报 `images_*` 时会把
  `source_total`/`seals_ok` 清空 ⇒ 改为**只更新显式传入字段**（未传者保留原值）。

**代码路径重跑（`sync-images`，非手工改行）**：
```
cd server && ../server/.venv/bin/python -m app.seals sync-images \
  --db ../var/seal_ingest.db --batch-id seal_20261010_01 --img-workers 4 --img-delay 0.1
=> total_refs=6765 ok=6347 skipped_resume=6762 no_source=418 convert_failed=0
   no_source_bad_bytes=1  bad_bytes=[{3609/yt/2_3609_1  "HTTP 200 image/jpeg but undecodable (697B)"}]
   FAILURES=[]     （日志 ops/seal-ingest/13_bad_bytes_rerun.log）
```
`failed` 桶由 1 ⇒ **0**；唯一那行 `3609/yt` 转 `source_no_image`/`bad_bytes`（`error` 记实际现象）。

**重跑后四桶新计数**（`image_status_counts`）：

| 桶 | 计数 |
| --- | ---: |
| `ok` | **6347** |
| `source_no_image` | **418** |
| ↳ `bad_bytes` | 1 |
| ↳ `http_500` | 415 |
| ↳ `nan_ref` | 2 |
| `failed` | **0** |
| 合计 | **6765** |

按 kind（ok / source_no_image / failed）：`yt 3464/215/0`、`ytsw 2424/203/0`、`yzbk 459/0/0`。

## 2. 出就绪包

```
cd server && ../server/.venv/bin/python -m app.seals package --batch-id seal_20261010_01 --db ../var/seal_ingest.db
```
产物 `exports/seal_import_seal_20261010_01/`（日志 `14_package.log`）：

| 文件 | 读数 |
| --- | --- |
| `seals.jsonl` | 3679 行 |
| `seal_links.jsonl` | 8964 行 |
| `images_manifest.jsonl` | 6347 行（唯一索引） |
| `images/<sha256[:2]>/<sha256>.tiff` | 6347 个文件 |
| `manifest.json` / `report.json` | ✓ |
| 入包方式 | hardlink 6347 / copy 0 / missing_cache 0（**不重转、不删已有 images/**） |
| content_fingerprint | `e8155837ff2785cbef1466ab7c419c1b3ed52c213fc6f7de2ecf57dc85e3c447` |

> 说明：`finish_batch` 修复后，为让批次行 `source_total` 正确落库，先跑了一次**幂等重放 `sync`**（列表 1 次、
> 全跳过，`run_kind=idempotent_replay`），再重跑 `package`（把 images 段重新写进 manifest/report）。
> 批次行现为：`status=DONE source_total=3679 seals_ok=3679 links_ok=8964 images_ok=6347 images_failed=0
> images_no_source=418 last_run_kind=idempotent_replay`。

## 3. 包自检（逐条读数 · 脚本 `16_package_selfcheck.py` ⇒ `17_package_selfcheck.json`）

① **`images_manifest.jsonl` ↔ `images/**` 双向一一对应**
| 读数 | 值 |
| --- | --- |
| manifest 行数 | 6347 |
| 唯一 sha256（行） | 6347（重复行 0） |
| 树上文件数 | 6347 |
| 方向 A：树上有 / 清单无（orphan_files） | **0** |
| 方向 B：清单有 / 树上无（rows_without_file） | **0** |
| `one_to_one` | **true** |

② **随机 20 行 sha256 重算自洽**：20/20 `match=true`。
③ **逐行 TIFF 魔数**（`II*\0` / `MM\0*`）：检查 6347 张，`magic_fail=0`。
④ **尺寸档位**：
| 档 | 上限 | 越档数 |
| --- | ---: | ---: |
| xiai 产物档（STORED_MAX_BYTES） | 4 MiB | **6** |
| xiai 输入档（MAX_INPUT_BYTES） | 1 MB | **225** |
- 单张范围：**152 B … 4,960,644 B**（min/max）。
- **越 4 MiB 清单（6 张，逐张）**：`yt/3353 4,751,398B`、`yt/3366 4,379,040B`、`yt/3367 4,930,210B`、
  `yt/3464 4,822,388B`、`yt/3506 4,639,606B`、`yt/3510 4,960,644B`（sha256 见 17 件 `over_stored`）。
  ⚠ 依 `xiai/server/app/store.py`（`len(data) > STORED_MAX_BYTES ⇒ NOT_IMAGE`，415），这 6 张**会被 xiai 影像库
  按现口径拒收**——系「只用原生裁切、不放大」口径下大源图的必然结果（非本单回归）；**登记为待裁定项**（下一单/
  xiai 侧）。1 MB 档的 225 张属「输入档」参考口径，不阻断产物入库。
⑤ **台账每行有 width/height**：`images_manifest` 缺 wh 0 行、DB `ok` 行（6347）缺 wh **0** 行。
⑥ **`manifest.image_policy`**：`no_source_reasons` 三键齐 `{nan_ref, http_500, bad_bytes}`；`no_image_rule` 三子因齐；
  `upscale_probe` 在（verdict＝「禁用放大尺寸；只取 /full/ 原生裁切」）；`source_missing` compact 在（total 418，无 rows）；
  `packaged_checks` 在（`one_to_one=true`、`sha256_equals_tiff_bytes=true`、`tiff_magic_all_ok=true`）。
⑦ **`report.json`**：三态计数 `ok=6347 / failed=0 / source_no_image=418 / total=6765`；
   `source_no_image.by_reason={bad_bytes:1, http_500:415, nan_ref:2}`；**按 ref 前缀聚合** `by_prefix` **52 组**，组内
   `count` 之和 ＝ 418 ＝ total（含 `kind/prefix/reason/count/sample_seqids`）；`failures=[]`。

**旧形态 FAIL 对照**：本单出包前，`images/` 与 `images_manifest.jsonl` 均为 **空（0 行 / 0 文件）**，`report` 三态
`failed=1` ⇒ ① 的双向对应表面 `0==0` 成立，但 `packaged rows=0 ≠ ok 6347`、且 `failed≠0` ⇒ **旧形态判 FAIL**；
② ③ 亦因无行无可校验。新形态 `6347==6347`、`one_to_one=true`、`failed=0` ⇒ 全 PASS。

## 4. 复跑对拍 `ops/seal-ingest/09_upscale_probe`（⇒ `09_upscale_probe.recheck.json`，**未改 09 原文**）

按 09 `commands_used` 重跑 **probe_A（尺寸阶梯，ref `19_1000_1` / `62_3894_1`）** 与 **probe_C（插值判定）**：
- **A**：尺寸阶梯 8 个测量点 **逐点复现** —— bytes 差 ≤ **0.02%**、w/h **全等**（如 `1200,` 135742 vs 135742；
  `62_3894_1` `1200,` 86914 vs 86907）。`A_all_within_2pct=true`。
- **C**（口径 = `ImageStat.Stat(L.filter(FIND_EDGES)).var` / 灰度方差 / 灰度 MAD）：**8 项原始读数全部 ≤ 0.46%** ——
  `edge_strength_bicubic 135.81 vs 135.71`（0.07%）、`edge_strength_server_big 137.55 vs 137.69`（0.10%）、
  `variance_native 2864.7 vs 2865`、`mad_mine_vs_big 4.32 vs 4.32`、`mad_native_vs_big_down 4.35 vs 4.37`。
  `C_all_primary_within_2pct=true`。
- 唯一派生比值（|mine−big|/big）1.26% vs 09 的 1.5%：系 09 的 mine 含一次 JPEG 回环（135.71）与本件内存态（135.81）
  的微差，非实质性；**判定以两绝对读数（135.81 vs 137.55，均 ≈ 09）为准**。**结论一致**：服务器大图 ＝ 双三次上采样，
  禁用放大尺寸。

## 5. 门禁 / 幂等 / API 证据

- **红线门禁**（`fingerprint_guard.py` ⇒ `00_guard_after.json`）：与 `00_guard_before.json` **逐字节相同**
  （`json.dumps(sort_keys)` 相等）——`yinpu.db`（8 表）/ `var/person_ingest.db`（3 表）/ `var/item_ingest.db`（3 表）
  内容指纹**未变**；`exports/person_*` / `exports/item_*` 目录指纹**未变**。
- **幂等重放（库副本，不动生产库）**（`19_idempotent_replay.{json,log}`）：`.backup` 出 `var/seal_ingest.replay.db` →
  副本上跑 `sync`：`run_kind=idempotent_replay`、`fetched_requests=0`、`skipped_resume=3679`、`failed_count=0`；
  副本内容指纹 **before==after==`e815…`**；副本产出的 `seals.jsonl`/`seal_links.jsonl` 与生产包 **`cmp` 逐字节相同**。
  副本用后已删除（生产库未动）。
- **API 自检**（`20_api_and_browser_selfcheck.json`，base 5196）：`?cursor=x⇒400`；`?audit_status=2⇒total 716`；
  `/api/seals/3922⇒二金蝶堂 / 白文方印 / 趙之謙`；`/api/seals/1000/image/yt⇒200 image/jpeg 13355B`、
  `/image/ytsw⇒200 image/jpeg 5112B`。
  ⚠ **与派单预期的差异**：任务写「`/image/yt⇒200 image/tiff`」，**实测为 `200 image/jpeg`** —— `routers/seals.py`
  该端点从 `var/seal_images/` 的 **JPEG 源缓存**供图（供页面 `<img>` 缩略图；浏览器不渲染 TIFF）。该文件**不在本单
  允许改动集**（硬约束），故**未改**，如实登记待裁定。（另 `/api/seals/3922/image/yt⇒404`：3922 的 yt ref 以 `NaN_`
  开头 ⇒ 源侧无图 ⇒ 本地无图，符合端点语义。）
- **单路重启**：`feicui-api` 由 `POST /api/stop`＋`POST /api/start`（**仅该 sid**；未 startAll、未 pkill）自
  PID **74689 ⇒ 63108**（running、portOpen=true）；重启后三端点复验仍 `400 / 716 / 二金蝶堂…`。

## 6. 真浏览器 + 构建

两源真浏览器（Chromium/CDP，文本读取 DOM）：
| 源 | h2 | 页签（4） | 四区（4 card） | 按钮 | 上屏结果 |
| --- | --- | --- | --- | --- | --- |
| `http://127.0.0.1:5195/feicui/seals` | 印章采集 | 印谱解析/印人采集/印谱采集/印章采集 | 采集区/就绪包（xiai）/印章列表/印章详情 | 【生成 xiai 就绪包】可点 | seals **3679** 行 · sidecar **8964** 行 · 影像 **6347** 张 · 源 total **3679** · `key_face_status=pending_xiai` |
| `http://localhost:5164/feicui/seals` | 印章采集 | 同上 | 同上 | 同上 | 同上（生成时点 18:32:49） |

- 两源点击后**均上屏行数与 `key_face_status`**（未改数据、走真实 `POST /api/seals/package`）。
- **构建**：`cd web && npm run build` ⇒ **EXIT=0**（`index-B74Wlqs7.js 220.71 kB`、`index-YdSyThVR.css 7.37 kB`，
  built in 728ms；`dist/` 为 `web/.gitignore` 忽略，不入提交）。

## 7. 提交（只暂存点名文件、未 `git add -A`、未 push）

暂存写集（与 `git status --porcelain` 完全一致）：
`M server/app/{config,main}.py`、`M server/requirements.txt`、`M web/src/{App.vue,router/index.js}`、
`?? server/app/seals.py`、`?? server/app/routers/seals.py`、`?? web/src/api/seals.js`、
`?? web/src/pages/SealsPage.vue`、`?? ops/seal-ingest/`。
`var/**`、`exports/**`、`web/dist/**` 已被 `.gitignore` 忽略（只在盘）。**未 push。**

（提交读数见 §7 末——命令与 commit hash 见下：）

## 8. 遗留 / 待裁定

1. **`/image/{kind}` 端点返回 `image/jpeg` 而非 `image/tiff`**（§5）；`routers/seals.py` 不在本单改动集。
2. **6 张 TIFF > 4 MiB**（§3④）会被 xiai 影像库拒收——需 xiai 侧或口径裁定。
3. `docs/feicui.spec.md` 的 `bad_bytes` 子因登记由 **Jing 并行线**负责（本单未碰 `docs/**`）。
