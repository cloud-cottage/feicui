# 印章包元数据补强报告（`source_bytes`/`source_sha256` ＋ 超档桶）

> 接手单（Kong · 元数据补强）。仓 `/Users/kevin/bistro/xiai/feicui`（main，HEAD `94abca1`）。
> 本单**不动影像内容、不重下、不重转**（6347 张 TIFF 已独立复验）；只做**元数据补强 ＋ 重出包 ＋ 提交**（不 push）。
> 写集＝`server/app/seals.py` ＋ `ops/seal-ingest/**`；**未碰** `docs/**`（Jing 并行）、`web/**`、各 `*.db`、`exports/person_*`/`exports/item_*`。

## ① `images_manifest.jsonl` 补两个源 JPEG 侧字段（12 → 15 键）

- 现有 12 键 `seqid/kind/source_ref/source_url/sha256/bytes/width/height/source_format/container/conversion/upscaled`
  **语义与值不动**（`sha256`/`bytes` 恒 ＝ **TIFF 字节**，内容寻址键）。
- 补：`source_bytes`（源 JPEG 字节数）＋ `source_sha256`（源 JPEG 字节 sha256）——**取值＝库 `seal_images.bytes`/`sha256`**（JPEG 侧台账，`status='ok'` 共 6347 行全非空）。
- 补：`oversize_for_xiai_store`（bool，逐行超档标记，见 ②）。
- 代码：`server/app/seals.py` → `_materialize_images()` 的 `SELECT` 增读 `bytes, sha256`；行体追加上述三键。
- **核对**：全量 6347 行 `source_bytes`/`source_sha256` **逐行 == 台账**；抽样 20 行再**对盘** `var/seal_images/<kind>/<seqid>.jpg`（`stat().st_size` 与 sha256）三方一致 ⇒ `0` 分歧。

## ② 超档桶（跨工程待裁项；机器可过滤）

实测 **6 张 TIFF > 4 MiB**（xiai `STORED_MAX_BYTES = 4194304`），均 `kind=yt`。**TIFF 格式不改**（RGB 8-bit + Deflate，合 xiai 家法；不换 JPEG-in-TIFF）。

三处显式登记：
- `images_manifest.jsonl`：逐行 `oversize_for_xiai_store`（`true` × 6）。
- `manifest.json` 顶层 `oversize_count: 6` ＋ `oversize_for_xiai_store{threshold_bytes,count,rows,policy}`；
  同桶亦挂 `manifest.json.image_policy.oversize_for_xiai_store`。
- `report.json` 顶层 `oversize_count: 6` ＋ `oversize_for_xiai_store{...}`。
- `policy`：本包保留原生裁切（`/full/` 1:1 源像素）与 xiai 家法格式；**超档项不自行降采样、不自行转码，去留由 xiai 侧裁定**。

6 条清单（`seqid/kind/TIFF bytes/宽×高/源 JPEG bytes`）：

| seqid | kind | TIFF bytes | W×H | 源 JPEG bytes |
| --- | --- | ---: | --- | ---: |
| 3510 | yt | 4960644 | 1586×1498 | 277175 |
| 3367 | yt | 4930210 | 1635×1590 | 278551 |
| 3464 | yt | 4822388 | 1488×1576 | 293939 |
| 3353 | yt | 4751398 | 1536×1510 | 284976 |
| 3506 | yt | 4639606 | 1557×1498 | 264871 |
| 3366 | yt | 4379040 | 1522×1533 | 262202 |

## ③ 重出包 ＋ 自检

```
cd server && ../server/.venv/bin/python -m app.seals package --batch-id seal_20261010_01 \
  --db ../var/seal_ingest.db --export-root ../exports --images-root ../var/seal_images
=> rows=3679 links=8964 images=6347 source_total=3679（约 4s；images/ 未删，仅补缺）
   （stdout `21_repackage.json`；日志 `21_repackage.log`）
```
`16_package_selfcheck.py` 增两条检查后重跑 ⇒ `17_package_selfcheck.json`（9 条）。

**逐条对比（上版＝本单前 `17_package_selfcheck.json`）**：

| # | 检查 | 上版读数 | 本版读数 | 一致 |
| --- | --- | --- | --- | --- |
| 1 | 双向一一对应 | 6347/6347/6347 · dup 0 · tree 6347 · orphan 0 · 缺失 0 · one_to_one ✔ | 同 | ✅ |
| 2 | 抽 20 行 sha256 重算 | n 20 · all_match ✔ | 同 | ✅ |
| 3 | 逐行 TIFF 魔数 | checked 6347 · fail 0 ✔ | 同 | ✅ |
| 4 | 尺寸档位 | stored_max 4194304 · over_stored **6** · over_input 225 · min 152 · max 4960644 | 同 | ✅ |
| 5 | width/height | manifest 缺 0 · db_ok 6347 · db 缺 0 ✔ | 同 | ✅ |
| 6 | `image_policy` 关键面 | 三子因 {bad_bytes,http_500,nan_ref} · upscale_probe ✔ · source_missing 418 · packaged_checks ✔ | 同 | ✅ |
| 7 | `report.json` 三态/前缀聚合 | ok 6347 · failed 0 · source_no_image 418 · total 6765 · 前缀组 52 · sum 418 · failures [] | 同 | ✅ |
| **8** | **`source_bytes`/`source_sha256` 逐行自洽（抽 20）** | — | **n 20 · all_self_consistent ✔ · 缺字段 0** | 🆕 |
| **9** | **超档清单计数＝6 且逐条可核** | — | **manifest 标记 6 · 顶层/manifest·image_policy/report 三处计数均 6 · seqid 集合＝{3353,3366,3367,3464,3506,3510} ✔ · 逐条 >4 MiB＋包内字节相符＋回指清单行 ✔** | 🆕 |

- **check1–7 与上版逐字段一致**（程序化比对 `==` True）。
- **TIFF 字节未变**：包内 `images/` 仍 6347 张、sha 集合与上版**完全相同**、按 sha 比对**无一条字节变化**（合计 1,235,816,312 B）。
- **未改现有 12 键**：逐行比对原 12 键投影，`0` 行差异。

## ④ 提交

`git add`（**只点名写集**，无 `-A`）：`server/app/seals.py`、`ops/seal-ingest/16_package_selfcheck.py`、
`ops/seal-ingest/17_package_selfcheck.json`、`ops/seal-ingest/21_repackage.{json,log}`、本文件。**不 push**。
`exports/**`、`var/**` 被 `.gitignore`（只在盘、不入库）；`docs/**`（Jing 并行）未纳入。
