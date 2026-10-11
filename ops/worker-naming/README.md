> ⚠⚠ **本目录整份已作废（DEPRECATED）—— 不得作为验收依据** ⚠⚠
> 本目录记录的是**旧「双份输出」口径**（TIFF ＋ 同名 webp 并存，脚本/读数对应 commit
> `f9be1d4`）。该口径**已被 commit `58c879f` 取代**：现行＝「**只出 TIFF**」（worker 只写
> `output/books/<目录键>/P<页>-C<列>-R<行>.tiff`；旧 `output/faces/**` webp 退场）。Kevin
> 2026-10-11 裁定「本地文件一律不再保存 webp」。
> 其中「新 webp 列」「三套并存」「旧 webp 未变」等读数与断言**在新口径下不再成立**；
> `verify_worker_naming.py` 已加运行时**拒绝执行**闸（默认 exit 3）。现行验收见
> **`ops/pool-naming-columns/`**。本目录保留仅作历史对照。

# ops/worker-naming —— worker 接「P-C-R 命名 ＋ V3 校正 ＋ 双份输出」单页函数级验证

**单**：Kong（实现）· 2026-10-11 · 把新出图口径接进 worker（新 job 默认**双份输出**）。
**口径真源**：`docs/image-naming-draft-v0.1.md`（命名 P-C-R ＋ 书籍目录键）＋ `docs/image-color-tiff-draft-v0.1.md`（V3 双色分层）；规范 §3.22 / §3.23。
**红线合规**：**不建 job、不写库、不碰旧文件**。本目录只放可复跑脚本 ＋ 读数 JSON（入库）；运行时产物（`output/**`）按 `.gitignore` 只在盘。

## 1. 代码改动（仅 1 个文件：`server/worker/feicui_worker.py`）

新增（旧路径与旧文件名**一字不动**、并存）：

| 处 | 改动 |
| --- | --- |
| 模块头 | 新增 `import importlib.util / io / from PIL import Image`；`BOOKS_DIR`（env `FEICUI_BOOKS_DIR`，默认 `output/books/`） |
| 地基加载 | `naming.py` / `colorcal.py` **按文件路径**加载（`feicui/app.py` 会遮蔽 `server/app` 包名）；`DIR_KEYS = naming.load_dir_keys()`（缺失则不致命） |
| `encode_tiff(rgb)` | 新增：`PIL.Image.save(format="TIFF", compression="tiff_deflate")` → RGB 8-bit ＋ Deflate 字节 |
| `process_page(...)` | 签名加 `pdf_name`；检测后 `cr = naming.assign_cr(bboxes)` ＋ `assert_page_unique`；`dir_key = naming.dir_key_for(pdf_name, DIR_KEYS)`；每枚**额外**写 `output/books/<dir_key>/P<页>-C<列>-R<行>.tiff`（V3 校正后 RGB）与同名 `.webp`（q95）；返回值加 `col`/`row`/`img_path_tiff` |
| `handle_chunk` | `pdf_name = basename(req["pdf_path"])` 传入 `process_page` |
| `ready_banner` | 补 `books_dir` 诊断字段 |

**未动**：检测算法（`processor.*`）、旧 webp 命名/路径/编码（`p 页4位_序2位.webp`，q95）、`img_path`。**worker 仍不写库**——`col`/`row`/`img_path_tiff` 交池侧写。

## 2. 单页函数级验证读数（`verify_readings.json`；17/17 PASS）

样本：**`tmp.pdf` 第 13 页**（小图快；book_key=`TMP`、模板别名＝黄牧甫印谱 range[13,19]、目录键 `tmp.pdf`）。**不建 job**：直接调 `process_page`；改造前代码取自 `git show HEAD:server/worker/feicui_worker.py`。

- **三套产出（6 枚，逐枚）**：

| idx | 旧 webp（未变） | 新 tiff（V3） | 新 webp（V3, q95） |
| --- | --- | --- | --- |
| 0 | `faces/TMP/p0013_00.webp` | `books/tmp.pdf/P13-C1-R1.tiff` 343×341 RGB comp=8 73,572 B | `P13-C1-R1.webp` 27,980 B |
| 1 | `p0013_01.webp` | `P13-C2-R1.tiff` 399×408 comp=8 90,066 B | `P13-C2-R1.webp` 32,808 B |
| 2 | `p0013_02.webp` | `P13-C3-R1.tiff` 255×186 comp=8 37,646 B | `P13-C3-R1.webp` 19,078 B |
| 3 | `p0013_03.webp` | `P13-C4-R3.tiff` 398×407 comp=8 118,432 B | `P13-C4-R3.webp` 40,960 B |
| 4 | `p0013_04.webp` | `P13-C4-R2.tiff` 347×352 comp=8 91,664 B | `P13-C4-R2.webp` 33,964 B |
| 5 | `p0013_05.webp` | `P13-C4-R1.tiff` 234×236 comp=8 31,880 B | `P13-C4-R1.webp` 14,074 B |

- **旧 webp 未变**：6/6 枚 **sha256 未变** ＋ **mtime 未变**（幂等写判「内容相同⇒不重写」；先验探针亦确认现有 detector 对本书本节裁图 6/6 逐字节复现既有件）。
- **新 tiff**：尺寸 ＝ 库/检测 bbox 宽×高、`mode=RGB`、Photometric=2、SamplesPerPixel=3、**Compression=8（Deflate）**。
- **命名**：6/6 匹配 `^P[0-9]+-C[0-9]+-R[0-9]+\.(tiff|webp)$`，无补零。
- **(C,R)**：返回 `[(1,1),(2,1),(3,1),(4,3),(4,2),(4,1)]`（与 `assign_cr` 独立复算逐字一致），**页内 6/6 唯一**，`assert_page_unique` 未触发。
- **返回新字段**：每枚 `col`/`row`/`img_path_tiff`（如 `idx0 → col=1,row=1,img_path_tiff=output/books/tmp.pdf/P13-C1-R1.tiff`）。

### 耗时对比（同页、预热后 min×2）

| 口径 | 改造前 | 改造后 | Δ |
| --- | --- | --- | --- |
| 本页（旧路径**未触发 OCR**，density 门未过 ⇒ 基线偏低） | 263.9 ms | 1162.0 ms | +898 ms (+340%) |
| 含 OCR 投影（OCR 用同尺寸裁图代理 ≈6.9 s/页，生产页常见） | 7194 ms | 8092 ms | **+12.5%** |

**新增块分解（6 枚合计）**：**V3 校正 968.9 ms（≈92%）** ｜ TIFF Deflate 16.7 ms ｜ webp 编码 66.6 ms。
⇒ **本单接线自身只加 ≈83 ms/页**（编码＋IO）；页面增量几乎全是**被规定的 V3 校正算法**（`server/app/colorcal.py`，本单不得改写）。故「无明显变慢」在 OCR 承载页成立（+12.5%），而增量是**新口径的固有成本**、非接线开销。

- **TIFF 编码确定性**：同像素数组 20 次 ⇒ distinct sha256 = 1（343×341；本尺寸确定），**解码像素 20/20 一致**。注意家法已知 **大图**上 Pillow `tiff_deflate` 有末 pad 字节不确定 ⇒ 幂等判据一律按**解码像素**，不按整文件 sha256。

## 3. 复跑

```bash
cd /Users/kevin/bistro/xiai/feicui
./venv/bin/python ops/worker-naming/verify_worker_naming.py   # 17/17 PASS；写 verify_readings.json
```

## 4. 未完成 / 待补

- **落库验证待 migration 到位后补跑**：新增列 `col`/`row`/`img_path_tiff` 的 migration（另一子代理）**代码已在树但未施加到生产库**（实测 `PRAGMA table_info(stamps)` 仍是原 10 列）⇒ 本单**未做**「新 job → 池侧写库」的端到端验证（亦不建 job，遵红线）。列到位后按同页补一次即可。
- 验证写入的运行时产物 `output/books/tmp.pdf/`（12 件）已**清理**（读数/名/尺寸/sha 见 `verify_readings.json`）；`output/books/秦印类编 检索版/` 既有 16 件样例与其 mtime **未触碰**。
