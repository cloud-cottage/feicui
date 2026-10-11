# feicui 印面去重 · 方案 A 收口（P0 修复 ＋ 应用面）（Kong，2026-10-11）

> **角色**：Kong（实现）。**标定依据**：`ops/dedup-calibration/`（commit `f5b901f`；全量 8708 行 ⇒ 保留 8440 / 标记 268）。
> **本单交付**：① 修 P0（按路径加载器 ＋ `@dataclass`）＋ 重跑新 job 路径验证；② 历史行走加法列标记的现场取证 ＋ md5 口径钉死；
> ③ 展示面（E3 `include_duplicates`）与导出面默认排除的语义落地。本目录是**应用面证据**（标定读数见 `ops/dedup-calibration/`）。

---

## 0. 一句话

去重规则本体 ＝ **`server/app/dedup.py`（唯一实现）**；worker 在**检测后、命名/写盘前**调它 ⇒ **只对新 job 生效**；
历史 8708 行由 `server/app/dedup_apply.py` **幂等写 3 个加法列**标记（不改既有 13 列、不删行）；
展示（E3）与导出默认**排除**被标记行（可 `include_duplicates=true` 回溯）。

红线全守：**不删文件 / 不改既有 13 列值 / 不建 job / 不重出图 / 不动印章线与 `output/faces/**`**。

---

## 1. ★ P0 修复（worker 导入阶段崩溃）

### 1.1 症状（Zang 实跑发现）

跑 `ops/dedup-apply/verify_worker_dedup.py` 时崩在 **worker 导入阶段**：

```
server/worker/feicui_worker.py:98  dedup = _load_by_path("feicui_dedup", "server/app/dedup.py")
  → server/app/dedup.py:117  @dataclass
  → dataclasses.py:712  ns = sys.modules.get(cls.__module__).__dict__
  → AttributeError: 'NoneType' object has no attribute '__dict__'
```

**影响＝任何新 job 在 worker 导入阶段即挂（生产 P0）。**

### 1.2 根因

`@dataclass` 在**装饰期**要解析 `cls.__module__`/注解，走 `dataclasses` → `sys.modules.get(cls.__module__).__dict__`。
worker 的 `_load_by_path` 用 `spec_from_file_location + module_from_spec + exec_module` **但没有先把模块注册进 `sys.modules`** ⇒
模块执行期间 `sys.modules.get("feicui_dedup")` 得 `None` ⇒ 崩。

### 1.3 修法（两道防线都做，防再踩）

| # | 位置 | 改动 |
|---|---|---|
| ① | `server/worker/feicui_worker.py::_load_by_path` | `exec_module` **之前**先 `sys.modules[mod_name] = mod`（标准做法）；执行失败则 `sys.modules.pop` 回滚，不残留半成品模块。 |
| ② | `server/app/dedup.py` | 去掉 `@dataclass`（`from dataclasses import dataclass, field` 一并删除）；`DedupMark` / `PageDedup` 改**普通类 ＋ `__slots__`**（字段与旧 dataclass **逐一对应**；`reason` 仍是 `@property`）。⇒ 本模块**不依赖 `sys.modules`**，在任何加载器下都安全。 |

> 同族加载器 `dedup_apply._load_core` / `dedup_eval._load_module` **本就已**先注册再 exec（故它们没踩到），本次把 worker 侧对齐。

### 1.4 回归验证（新 job 路径真读数）

`ops/dedup-apply/verify_worker_dedup.py`（scratch；调**生产 worker 的真实 `process_page`**；OCR 置空函数——去重在 OCR **之前**、与框数无关；
输出重定向到 scratch 的 `FEICUI_FACES_DIR`/`FEICUI_BOOKS_DIR`；`FEICUI_DB` 只读取期望值；**不建 job / 不写生产库 / 不碰 `output/**`**）：

```
cd feicui/ && ./venv/bin/python ops/dedup-apply/verify_worker_dedup.py <scratch_dir>
```

样本＝`秦印类编 检索版.pdf` 的 9 页（含 R1/R2 两类、覆盖高标记页）：

| page | detected_raw（去重前） | detected_after（去重后） | dedup_dropped（丢弃） | db_rows（库内全量） | db_kept（库内保留） | db_marked（库内标记） |
|---|---|---|---|---|---|---|
| 725 | 19 | 14 | 5 | 19 | 14 | 5 |
| 776 | 34 | 31 | 3 | 34 | 31 | 3 |
| 773 | 28 | 25 | 3 | 28 | 25 | 3 |
| 749 | 22 | 19 | 3 | 22 | 19 | 3 |
| 56  | 21 | 18 | 3 | 21 | 18 | 3 |
| 96  | 13 | 10 | 3 | 13 | 10 | 3 |
| 73  | 4  | 3  | 1 | 4  | 3  | 1 |
| 387 | 3  | 2  | 1 | 3  | 2  | 1 |
| 446 | 6  | 4  | 2 | 6  | 4  | 2 |
| **Σ** | **150** | **126** | **24** | **150** | **126** | **24** |

**判据（全 9 页均 True）**：
* `detected_raw == db_rows`（**去重前框数逐页等于库内全量行数** ⇒ worker 现场检测与历史行**逐位同源，无漂移**）；
* `detected_after == db_kept`（去重后 ＝ 库内保留行）；
* `dedup_dropped == db_marked`（**丢弃数逐页等于库内标记数** ⇒ 现场去重与离线标记**同一规则、同一取舍**）；
* `match_kept_boxes`：worker 保留的 `(x1,y1,x2,y2)` **多重集**逐框等于库内 `dup_kind IS NULL` 的行 ⇒ **几何恒等**。

原始读数：`ops/dedup-apply/worker_dedup_verify.json`（`all_match: true`）。

---

## 2. 历史行标记 —— DB 面读数

| 项 | 值 |
|---|---|
| `stamps` 列数 | **16**（既有 13 ＋ `dup_kind`/`dup_of_id`/`dup_algo`） |
| 行数 | **8708** |
| 被标记行 | **268**（`near_duplicate`＝143 ＋ `group_frame`＝125） |
| `dup_algo` 取值 | **单一值** `dedup-A-v1;t1=0.5;t2=0.6;tol=8.0;minc=2` |
| `dup_of_id` 违例（非空但指向不存在的 `stamps.id`） | **0** |
| 保留锚点 id 7990 / 7701 | 均 `dup_kind = NULL`（保留，✓） |
| 迁移 | `1a-0004-stamps-dedup-columns` 已应用（`schema_migrations` 含 `1a-0001..1a-0004`） |

按书分布（`ops/dedup-apply/summary.json` → `db_face.per_book`）：

| 书 | 全量 | 标记 |
|---|---|---|
| 秦印类编 检索版.pdf | 7183 | 231 |
| 福庵印缀 原版 高清.pdf | 1214 | 25 |
| 黄牧甫印谱_(西泠印社)….pdf | 200 | 6 |
| 古玺汇编 文物出版社 罗福颐 ok.pdf | 23 | 5 |
| tmp.pdf | 31 | 1 |
| 吴颐人篆刻作品展示.pdf | 22 | 0 |
| 秦汉印典 上海书画 金怀英 1997 ok.pdf | 35 | 0 |

---

## 3. 列语义

| 列 | 类型 | 语义 |
|---|---|---|
| `dup_kind` | TEXT | `near_duplicate`（R1 近重复）｜`group_frame`（R2 组框）｜保留行＝`NULL`。**两类分开**，可分别回溯。 |
| `dup_of_id` | INTEGER | 指向**保留行**的 `stamps.id`（R1 ⇒ 簇代表；R2 ⇒ 桥接的最大子框）。 |
| `dup_algo` | TEXT | 算法版本 ＋ 阈值签名 ＝ `dedup.algo_signature()`（**幂等重算的记账键**）。 |

* 部分索引 `idx_stamps_dup_kind ON stamps(dup_kind) WHERE dup_kind IS NOT NULL`（只索引被标记行，命中展示/导出侧的过滤）。
* **只加列、不改既有列、不删行**；新 job 的行**不写**这三列（`dup_kind` 恒 `NULL`——新 job 已在检测器侧去重）。

### 3.1 算法版本

`ALGO_VERSION = "dedup-A-v1"`，签名 ＝ `dedup-A-v1;t1=0.5;t2=0.6;tol=8.0;minc=2`。规则/阈值**单点可改**常量（`server/app/dedup.py` 顶部 `#:` 行）：
`T1_DEFAULT=0.50`｜`TOL_PX=8.0`｜`R2_MIN_CHILDREN=2`｜`T2_DEFAULT=0.60`｜`TIE_BREAK_DEFAULT="area_max"`｜`ORDER_DEFAULT="r2_first"`。
**改动任一常量即改变签名** ⇒ 幂等重算据此判「是否同一口径」。

---

## 4. 接入点（三处消费方，规则唯一）

**唯一实现**：`server/app/dedup.py`（纯 stdlib，无 cv2/numpy/sqlite ⇒ `server/.venv` 与 `feicui/venv` 都可加载）。

1. **worker（新 job）**—— `server/worker/feicui_worker.py::process_page`，在 `detect_stamp_regions` **之后**、`naming.assign_cr` / 写盘 **之前** 调 `_dedup_candidates`（→ `dedup.dedup_page`）。
   幸存候选**重排为连续 idx（0..k-1）** ⇒ 下游 `(C,R)` / 影像命名 / 落库行数随之收敛；**bbox 一字不改**。
   返回值新增 `detected_raw`（去重前）与 `dedup_dropped`（丢弃数），协议帧同步（`handle_chunk`）。
2. **历史标记**—— `server/app/dedup_apply.py`（`python -m app.dedup_apply`，幂等、只写 3 列；闸＝`FEICUI_ALLOW_PROD_MIGRATE=1`）。
3. **离线标定**—— `ops/dedup-calibration/dedup_eval.py`（几何/规则**委托** `dedup.py`，不自持第二份）。

---

## 5. 展示面（E3）与导出面的默认排除语义

### 5.1 E3 `include_duplicates`

`GET /api/jobs/{job_id}/stamps?page=&limit=&cursor=&include_duplicates=`：

* `include_duplicates` 缺省 / `false` ⇒ 结果**排除** `stamps.dup_kind IS NOT NULL` 的行（「前端/导出侧隐藏」的展示面）；
* `total` / `has_more` / `next_cursor` 与行集**同口径**过滤（**信封自洽**）；
* 置 `true` ⇒ 含被标记行（**可回溯口径**）；
* 非法值（非 true/false）⇒ **400**（不静默忽略）；库无 `dup_kind` 列（未跑 `1a-0004`）⇒ **自动退化为不过滤**（向后兼容）。
* **不删行、不改行。**

**活体读数**（API 重启载新码后，PID 45901）：

| 请求 | total | 说明 |
|---|---|---|
| `GET …/stamps`（默认） | **6952** | 排除 231 个标记行 |
| `GET …/stamps?include_duplicates=true` | **7183** | 全量 |

（demo job＝`job-90344a7802954afdaad447d875f2e15b`，书＝`秦印类编 检索版.pdf`；7183 − 6952 ＝ **231** ＝ 该书标记数 ✓）

### 5.2 导出面（`export.py`）

`export_book(..., include_duplicates=False)`（**默认 False ⇒ 排除标记行**）；CLI `export.py export [--include-duplicates]`（`--book` 等沿用）。
库无 `dup_kind` 列时自动退化不过滤。**导出前排除**：`秦印类编` ⇒ 6952（含被标记行：7183，排除 231）。
（`export.py::has_column` 为加法列的向后兼容闸；`_field_presence` 等既有口径一字未动。）

### 5.3 同族读面现状（核验）

* **E5 `missing?kind=image` count ＝ 0**（影像存在性判据与 E6 同解析顺序，不受去重列影响）；
* **E6 对「已标记为重复」的行仍 200 / `image/png`**（PNG magic `89504e47…`）——实测页 29 idx 4（`group_frame`）返回
  `x-feicui-img-path = output/books/秦印类编 检索版/P29-C2-R6-O.tiff`（**三跳回落**：`img_path_tiff` → 同目录同名 `-O.tiff` → `img_path`）。
  ⇒ **去重只影响「是否成行」，不影响已存在行的取图**。

---

## 6. ★ md5 口径（此前不一致的根源已钉死）

### 6.1 结论

「既有 **13 列**（`id..img_path_tiff`，**不含** 3 个去重列）」的内容指纹：

```
before（写入前备份）≡ after（现行 prod）≡ 17ada51244edac62aa2147d6b9a9612d        (rows=8708)
```

### 6.2 **确切算法**（此前 Zang 用 6 种序列化都复现不出，原因在这里）

**SQL 列序**（逐字照 `PRAGMA table_info` 的前 13 列，即 `1a-0003` 后的既有列面）：
`id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2, col, row, img_path_tiff`

```python
parts = []
for row in conn.execute("SELECT id,pdf_name,page,idx,text,img_path,x1,y1,x2,y2,col,row,img_path_tiff "
                        "FROM stamps ORDER BY id"):
    parts.append("|".join("" if v is None else str(v) for v in row))   # 行内 13 值用 "|" 连接；NULL → 空串
digest = hashlib.md5("".join(parts).encode("utf-8")).hexdigest()       # ★ 行与行之间**不加分隔符**
```

* **行序** ＝ `ORDER BY id`；**NULL** → `""`；**编码** ＝ UTF-8。
* **★ 关键点（此前对不上的根源）**：序列化是「**每行**先以 `"|"` 连成一个片段；再把各片段用**空串 `""`** 依次拼接」。
  若改成「把所有行的所有值**展平**后**一个** `"|".join`」，会多出 `N−1` 个分隔符（8708−1＝8707 字节）⇒ 得到**另一个**摘要
  `eb4fd59542fbcdef9dbcfedce479cfb1`（我就是之前误用了这一形态，故 `17ada51…` 复现不出）。两者**长度差恰 8707 字节**可自证。
  其它变体（`"\t".join`、`"\n".join(行)`、`rowid` 序等）亦会得到完全不同的摘要 ⇒ **必须**按上表照抄。

### 6.3 可复现命令

```bash
cd /Users/kevin/bistro/xiai/feicui

# 脚本：ops/dedup-apply/recompute_cols13_md5.py（本目录，已入库）
# after ＝ 现行 prod 库；before ＝ 写入前备份（见下）
./venv/bin/python ops/dedup-apply/recompute_cols13_md5.py \
    /Users/kevin/.hermes/profiles/zang/cache/scratch/dedup-apply/yinpu.db.prebak \
    /Users/kevin/bistro/xiai/data/yinpu.db
# ⇒ 17ada51244edac62aa2147d6b9a9612d  (×2, rows=8708)
#    before ≡ after : True
```

**「before 备份」的两条可复现来源**（互为佐证，都给出同一摘要）：

1. **写入前备份 `yinpu.db.prebak`**（`apply` 前 `cp` 副本）：
   `/Users/kevin/.hermes/profiles/zang/cache/scratch/dedup-apply/yinpu.db.prebak`
   （`sha256 = 1e33e6910ec4bc8d88256789a2a8836b35ef9bf97cebaf1740702a3dc1ef0061`，rows=8708，13 列无 `dup_*`）。
   ⚠ scratch 目录闲置 24h 会被清 ⇒ 见下第 2 条。
2. **从现行 prod 重建**（**不依赖任何 scratch**，永久可复算）：`dedup_apply.py` 是**唯一**写 `dup_*` 列的写者，
   故「写入前状态」≡「prod 副本把这 3 列置 NULL」：

```bash
cp /Users/kevin/bistro/xiai/data/yinpu.db /tmp/before.db
python3 - <<'PY'
import sqlite3; c=sqlite3.connect("/tmp/before.db")
c.execute("UPDATE stamps SET dup_kind=NULL, dup_of_id=NULL, dup_algo=NULL"); c.commit(); c.close()
PY
./venv/bin/python ops/dedup-apply/recompute_cols13_md5.py /tmp/before.db /Users/kevin/bistro/xiai/data/yinpu.db
# ⇒ 17ada51244edac62aa2147d6b9a9612d  (×2)
```

实测三路同值：`prebak` ＝ `reconstructed` ＝ `prod` ＝ `17ada51244edac62aa2147d6b9a9612d`
（读数件：`ops/dedup-apply/fingerprint_cols13.json`，`before_eq_after: true`）。

---

## 7. 红线核对

| 红线 | 结果 |
|---|---|
| ① 不删文件 | ✓ 未删任何文件（scratch 运行目录已清） |
| ② 不改既有 13 列值 | ✓ `before ≡ after ＝ 17ada51244edac62aa2147d6b9a9612d`（§6） |
| ③ 不建 job | ✓ 未建任何 job（仅**只读**打 E3/E5/E6）；池/worker 进程收尾为空 |
| ④ 不重出图 | ✓ 未重出图；`output/faces/**` 一字未动 |
| ⑤ 只暂存自己的文件、永不 `git add -A` | ✓ 显式 pathspec；提交前核 `git diff --cached --name-only` |
| ⑥ 改 `server/app/**` 后重启 API 并自证活进程 ≥ 源文件 mtime | ✓ API 重启（PID 45901，启动 **13:15:54** ≥ `dedup.py` mtime **13:14:26**），health 200 |
| ⑦ 图像栈只在 `feicui/venv` | ✓ 验证脚本用 `feicui/venv/bin/python`；接口层未 import cv2/numpy/pymupdf |

---

## 8. 复跑命令（全在本目录）

```bash
cd /Users/kevin/bistro/xiai/feicui

# 1) 新 job 路径去重验证（scratch，不写库、不建 job）
mkdir -p /tmp/dv && ./venv/bin/python ops/dedup-apply/verify_worker_dedup.py /tmp/dv
#    ⇒ 9 页 raw/after/dropped/geometry 全 match，退出码 0

# 2) 13 列指纹 before ≡ after
./venv/bin/python ops/dedup-apply/recompute_cols13_md5.py \
    /Users/kevin/.hermes/profiles/zang/cache/scratch/dedup-apply/yinpu.db.prebak \
    /Users/kevin/bistro/xiai/data/yinpu.db

# 3) 历史标记幂等（dry-run；第二次应 updates_needed=0）
cd server && ./.venv/bin/python -m app.dedup_apply --json /tmp/dedup_rerun.json
```

证据件：`ops/dedup-apply/worker_dedup_verify.json`｜`fingerprint_cols13.json`｜`summary.json`｜`recompute_cols13_md5.out`。

---

## 9. 未决 / 边界（如实登记，非本单缺陷）

* **丢桥接框会连带丢掉「未被单独检出的子印」**：属**检测器的分割能力**（把桥接区拆成 N 枚），不是去重规则能解决的 ⇒ 另立一单。
* **`(C,R)` 因去重而重排**：已产 TIFF/O 件存在对应冗余件，需一次性清理（**不重出图**；见 `ops/dedup-calibration/README.md` §3）。
* 离线标定读数、两版变体与边界带见 **`ops/dedup-calibration/README.md`**（标定 commit `f5b901f`）。
