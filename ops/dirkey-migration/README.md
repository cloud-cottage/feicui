# 书籍目录键迁移（dirkey-migration）· Kong 2026-10-13

## 0. 单据与授权

- 单据：**书籍目录键迁移**（5 改 2 不变；8708 件 `-O.tiff` 与 8708 行 `img_path_tiff` 同步）。
- 授权：**Kevin 2026-10-11**（切键＋目录键一律 13 位 ISBN＋福庵去缀；**明确授权改写 `stamps.img_path_tiff` 既有列值**）。
- 生产库 `/Users/kevin/bistro/xiai/data/yinpu.db`（`stamps` 16 列 / 8708 行；全库仅 `stamps.img_path_tiff` 持有 `output/books/` 路径——迁移前全表全列扫描证实）。
- 实际执行面勘误：单据现状栏记「5 个书目目录」，实测 **7 个目录**；其中 **黄牧甫印谱已处目标态**（目录名 / 库内 dir 段 / config 三处一致）⇒ 实际 mv **4** 本、改 config 键 **4** 本、改写行 **8455**。

## 1. 映射（逐本，行数为库内实测）

| PDF 名 | 旧目录键 | 新目录键 | 行数 | dir_key_source | isbn_source |
| --- | --- | --- | ---: | --- | --- |
| 秦印类编 检索版.pdf | 秦印类编 检索版 | **9787550847224** | 7183 | ISBN | local_ocr（第 850 页版权页 OCR，anchor_near；前缀 5508＝西泠印社出版社自洽） |
| 秦汉印典 上海书画 金怀英  1997 ok.pdf | 7806350950 | **9787806350959** | 35 | ISBN | text_layer（第 2 页文本层直读） |
| 古玺汇编 文物出版社 罗福颐  ok.pdf | 7501007985 | **9787501007981** | 23 | ISBN | local_ocr（第 3 页版权页 OCR，anchor_near；前缀 5010＝文物出版社自洽） |
| 福庵印缀 原版 高清.pdf | 福庵印缀 原版 高清 | **福庵印缀**（去扫描品质缀） | 1214 | chinese_title | — |
| 黄牧甫印谱_(西泠印社)_(…).pdf | 黄牧甫印谱 | 黄牧甫印谱（**已处目标态，no-op**） | 200 | chinese_title | — |
| 吴颐人篆刻作品展示.pdf | 吴颐人篆刻作品展示 | 不变 | 22 | chinese_title | — |
| tmp.pdf | tmp.pdf | 不变（`pdf_name_unconfirmed`） | 31 | pdf_name_unconfirmed | — |

- ISBN-13 换算与校验位：`7806350950→9787806350959`、`7501007985→9787501007981` 均「978＋前 9 位＋重算校验位」并在实现里**再次程序验算**（ISBN-13 加权 1/3；三条新键 `9787550847224`/`9787806350959`/`9787501007981` 全过）。来源证据＝`ops/biblio-metadata/seven_book_table.*`（accepted 候选逐条带 page/source）。

## 2. 执行（严格按单序）

1. **备份**：库 WAL-safe `.backup` → scratch `dirkey_migration/yinpu.db.pre_dirkey_migration`（rows=8708 / jobs=12 / integrity=ok）；目录 APFS clonefile 拷贝 → `output/books.pre_key_migration`（8708 O 件＋4 `.DS_Store`）；清单 `manifest_books_pre.tsv`（**8708 件 ×（相对路径＋字节＋sha256）**，清单文件 sha256＝`8b26e61d5e4c0667d2f4ec6c545016f0fed6f954cba3bd319a1416537c8ddcfb`）。`.DS_Store` 4 件记为 **strays**，不参与对账与 mv 判定。
2. **config**：`config/book_dir_keys.json` 4 本 `dir_key` 更新；3 本 ISBN 书加 `isbn13`＋`isbn_source`（`dir_key_source=ISBN`）；7 本全加 `migrated_at`；顶层加 `migration` 块（授权、行数 8455、证据路径）。原文件快照在 scratch。
3. **mv**：4 目录改名（非拷贝；`.DS_Store` 随目录走）。
4. **改库**：`UPDATE stamps` **仅 `img_path_tiff` 一列**，单事务（`BEGIN IMMEDIATE … COMMIT`）**8455 行**＝7183＋35＋23＋1214；逐行断言仅前缀替换＋新值合 `^output/books/<新键>/P\d+-C\d+-R\d+\.tiff$`；任一步失败自动回滚事务＋回退 mv。
5. **验证**：见 §3。
6. **收尾**：验证全绿后删除 `output/books.pre_key_migration`（8712 件拷贝；删除后复点 O 件仍 8708）。

## 3. 验证读数（2026-10-13 全部真跑；机器可读件＝本目录 `before_evidence.json` / `step5_results.json`）

| 判据 | 读数 |
| --- | --- |
| O-5 双向对账（DB 行 ↔ 盘上 `-O.tiff`） | DB→盘 **8708/8708（缺 0）**；盘→DB **8708/8708（孤儿 0）** |
| 逐件 sha256 对迁移前清单（路径按前缀映射） | **8708/8708 全符，0 不匹配**（mv 未动内容） |
| `img_path_tiff` 命名合规 | **8708/8708** |
| 目录面 | 7 目录＝{9787550847224:7183, 福庵印缀:1214, 黄牧甫印谱:200, 9787806350959:35, tmp.pdf:31, 9787501007981:23, 吴颐人篆刻作品展示:22}；旧键目录 0 残留 |
| E5 `missing?kind=image` | **12/12 job count=0** |
| E3 totals（12 job × default/include_duplicates 两口径） | **12/12 before≡after**；**101/105 对＝`job-13539d819b…`（秦印类编 检索版 11 页 job）仍在** |
| E6 同位复打（before 基线同一 job/page/idx） | **6/7 本 200 ＋ `image/png` ＋ PNG magic ＋ `x-feicui-img-path` 落新目录**；**古玺汇编（23 行）无 job** —— E6 为 job 作用域、红线不建 job，该本以 O-5 双向对账＋命名合规覆盖（如实登记，非缺陷） |
| 15 列指纹（16 列中除 `img_path_tiff` 外全部） | **before ≡ after ✓**（算法见 §4）；`jobs` 表指纹不变 ✓ |
| strays（`.DS_Store`） | 迁移前后均 4 件，随目录改名走，计数一致 |

## 4. 指纹算法（可复现）

```
按 id 升序取 stamps 全行（16 列，含 NULL）。
对每个列 c（除 img_path_tiff 外共 15 列）：
    digest_c = sha256( "".join( f"{id}\t{json.dumps(value_c, ensure_ascii=False)}\n" for each row ) )
（REAL 经 json 序列化为 repr 形，确定性成立。）
before/after 逐列 digest 两两相等 ⇒ 除 img_path_tiff 外零漂移。
另算：jobs 表整表按 job_id 排序逐行 join(\x1f) 后 sha256，before ≡ after。
全 16 列行级 sha256 before ≠ after（img_path_tiff 前缀变更所致，预期内）。
```

## 5. 回滚说明

- **备份点**：库备份 `~/.hermes/profiles/zang/cache/scratch/dirkey_migration/yinpu.db.pre_dirkey_migration`（注意 scratch 24h 空闲清理；迁移前 config 快照同目录）。目录拷贝已按单据在验证全绿后删除。
- **确定性回滚（不依赖备份，两步幂等）**：
  1. `mv` 回 4 目录：`9787550847224→秦印类编 检索版`、`9787806350959→7806350950`、`9787501007981→7501007985`、`福庵印缀→福庵印缀 原版 高清`；
  2. 反向前缀 UPDATE（新→旧，同 8455 行口径、同逐行校验）。
- 回滚触发条件＝§3 任一判据复跑不绿；本单执行时全绿未触发。

## 6. 红线自证

未删任何 O 件（只 mv，sha256 逐件复核）；除 `img_path_tiff` 外未写 stamps 任何列（15 列指纹证明，含 3 个去重加法列 dup_kind/dup_of_id/dup_algo）；未建 job（jobs 表指纹不变）；未碰印章线与 `output/faces/**`；未重出图；未 `git add -A`（显式 pathspec）。
