# ops/book-page-2400 —— 第 29 页 2400 dpi 整页处理 → 48bit RGB TIFF

**书**：《秦印类编 检索版》（`inbox/20261011/秦印类编 检索版.pdf`，目录键 `9787550847224`）
**页**：第 29 页（1-based，与 `stamps.page` 同轴）｜**源**＝页内嵌 JPEG `xref 112`（2125×3059 @300 dpi，无文本层）
**出图**：17000×24472 px ＝ 416.02 Mpx @2400 dpi（＝ 8× 整数上采样；**与源扫描 dpi 无关**）｜48bit（16bit×3）RGB｜Deflate(8) ＋ Predictor 2｜BigTIFF

```
./venv/bin/python ops/book-page-2400/render_page_2400.py --smoke          # 自检（必先过）
./venv/bin/python ops/book-page-2400/render_page_2400.py                   # 全页（前台会被拖 ⇒ 后台跑）
./venv/bin/python ops/book-page-2400/render_page_2400.py --verify-only     # 只验证既有产物（全 96 strip）
```

---

## §0 本单交付（两版并存，Kevin 选）

| 版 | 文件（`output/` 不入库） | 口径 | 字节 | sha256（前 16） |
| --- | --- | --- | --- | --- |
| **主版** | `output/book-pages/9787550847224/P29-2400dpi-48bit.tif` | 含色彩校准 `--color-calib 0.35` | 1,903,843,591（1.773 GiB） | `9f238c756f754caa` |
| **冻结版** | `output/book-pages/9787550847224/P29-2400dpi-48bit-frozen.tif` | `--color-calib 0`（⑤ 完全关闭） | 1,906,199,278（1.775 GiB） | `d5585c188cd75e62` |

**第一枚裁件**（阅读序第 1 枚，见 §2）：
`output/book-pages/9787550847224/P29-C1-R1-无信息-戰國-佚名-O.tiff` —— **2120×2144 px**、RGB 8-bit ＋ Deflate ＋ Predictor 2（O 件家法；`-O` ＝ 未做印面级色彩处理的原始切片）、4,748,586 B、sha256 `55adbcc212f7d84d…`；
坐标 `(4264,4440)-(6384,6584)` @2400 dpi ＝ 源 `(533,555)-(798,823)` @300 dpi（`box_2400 = box_300 × 8`）。
**与页图逐像素相等**（`vs_page_mismatch_px = 0`；量化式 `q8 = round(page_u16/257)`，固定可逆）。
⚠ **裁件取自「主版」页图**（两者仅在印泥像素上不同，而 C1-R1 正是印泥区）⇒ 若 Kevin 选冻结版，同一命令加 `--color-calib 0` 重出即可；**冻结版对应裁件已另存** `output/samples/book-page-2400/P29-C1-R1-frozen-page-crop.tiff`（sha256 `260f36bfaa7d924d…`，与冻结页 `mismatch 0`），两版可并排看。

**读数 JSON**（入库证据）：`readings-P29-2400dpi-48bit.json`（渲染＋验证）｜`readings-P29-2400dpi-48bit-frozen.json`｜`readings-P29-2400dpi-48bit.verify-only.json`｜`readings-P29-2400dpi-48bit-frozen.verify-only.json`（后两份是**独立进程**的 `--verify-only` 复验，用于证明「重算确定性」与「产物未被改动」）。

---

## §1 算法映射（提示词 → 确定性算法）

| # | 提示词口径 | 落成算法（本脚本） |
| --- | --- | --- |
| ① | 内容面（印面 ＋ 印刷黑字/框线）**冻结** | 非纸底 ∧ 非印泥像素**逐像素** `== clip(8× Lanczos)`；唯一允许的变化是上采样 |
| ② | 背景＝**程序化宣纸**（无暗角、无重复纹理、色域 `#FAFAF7`–`#FFFFFF`） | 纸底类像素（`gray ≥ 210 ∧ 饱和 ≤ 0.15 ∧ 非印泥`）写位置哈希噪声：`splitmix64(row,col,seed)` 颗粒＋各向异性纤维晶格（长轴 66 px ≈0.70 mm／短轴 7 px ≈0.07 mm），逐通道限幅到色域 |
| ③ | 背景纯均匀、无渐晕，不做光影 | 背景层不含任何空间梯度；印面不做光影处理 |
| ④ | 印面外缘 **微晕染**（α≤8%） | 掩膜**外侧** 16 px 环带（2 px × 8×）、α 线性衰减、取全页印泥均色 `(196.47, 76.86, 75.49)`；**只落在新纸底**像素上（内容像素一律不动） |
| ⑤ | **色彩校准** | 仅印泥像素：归一化色度向全页印泥核心均色收敛（严格保 `R+G+B`），逐像素有界强度 `t ≤ strength` |

- **单一真源复用**：宣纸色域/种子/σ、晕染带宽与 α 上限、`ink_mask` 均**直接 import** `server/app/seal_canvas.py`、`server/app/colorcal.py`（不复制第二份常量）。
- ★ **① 与 ⑤ 直接冲突**（原提示词内部矛盾）：⑤ 必然改印泥像素的颜色值 ⇒ 本单**把它登记为待裁**并**两版并存**（§0/§5），不做单方面取舍。
- ⑤ 的强度是**逐像素有界**的：`t` 取「方向不变、且不使任一通道越出 [0,255]」的最大可行值 ⇒ `t ≤ 0.35`，主版实测均值 `0.309`、`px_at_cap` 13,447,060。
- ⑤ **只作用于有效域印泥像素**：8× Lanczos 在强边缘**振铃越界**（通道 >255 或 <0，Σ 甚至为负）的像素不参与色度换算（归一化不是良定义）⇒ 这些像素 `t = 0`、逐像素原样保留，主版实测跳过 444,787 px（见 §4）。
- **Lanczos 振铃是固有现象**（不是缺陷）：实测 12,201,268 px 的浮点值越出 [0,255]、最大超限 56.747（8bit 单位）⇒ 量化进 16bit 时按通道裁剪；属「Lanczos ＋ 量化」固有，未做任何额外处理。

## §2 几何、分块策略与「第一枚」口径

- 页尺寸取**分布众数**：**510.0 × 734.16 pt ＝ 179.92 × 259.00 mm**（780/851 页，91.66%）；其余为扫描裁切抖动（±2 pt 14 种）＋ 39 页 `490.0×726.0`（另一开本/装订差异）——逐条见 `geometry_report.json`。
- 目标像素：`510.0/72×2400 = 17000`、`734.16/72×2400 = 24472`（皆整数）；源 2125×3059 ÷ (510/72) = **300.0 dpi** 两侧一致。
- **分块策略＝水平 strip 流式（96 条 × 256 输出行）**，但**压缩不手写**：
  1. 逐条处理输出行 `[y0,y1)`，**邻域运算全在扩展窗口上做**（窗口 ＝ 目标行 ± `MARGIN_SRC=8` 源行 ＝ ±64 输出行 **> 晕染环带 16 px**）⇒ 掩膜 Lanczos 上采样、距离变换、晕染都与分块切分**无关**、无接缝（`--smoke` 自证 `strip == whole, maxdiff 0`）；
  2. 结果落 scratch 上的**整页 uint16 memmap**（24472×17000×3 ＝ 2.5 GB，磁盘而非 RSS）⇒ 峰值内存不随整页增长；
  3. 整块交给 **tifffile 自己**切 strip ＋ Predictor=2 ＋ Deflate（`maxworkers=4`，本机空闲内存偏紧）；
  4. **原子换入**：先写 `<name>.part`，再 `os.replace` ⇒ 半成品不会留在正式路径上。
- 实测：渲染 82.5 s（96 条，单条 0.45–0.97 s、中位 0.83 s）＋ 写盘 25.5 s ＝ **108 s / 版**；峰值 RSS 3.72 GiB（写盘阶段）。
- **掩膜互斥**：印泥优先（`paper &= ~ink`），两枚掩膜各自 Lanczos 上采样后可能在同一像素同时为真 ⇒ 实测互斥后交集 0。
- **面积口径**（整页 416.02 Mpx）：纸底 93.35%、印泥 3.91%、其余内容（印刷字/框线）2.73% ＝ **11,379,210 px**。
- **「第一枚」＝ 阅读序**：红掩膜 ＋ `MORPH_CLOSE(15)` ＋ 连通域（面积 ≥ 4000 @300 dpi、宽高比 ≤ 2.0），按 **上→下（行带聚合）→ 行内左→右** 排序 ⇒ 第 1 枚 ＝ `C1-R1`。★ **中文阅读序的「右上首枚」是另一口径**（本页 2 列 × 3 行，右上＝本口径的第 2 枚）——一句话可改。逐枚 bbox 见 `first_seal_probe.json`。
- **【印刷尺寸即实物尺寸】**：`mm = px/dpi×25.4` ⇒ 首枚 265×268 px @300 dpi ＝ **22.437 × 22.691 mm**（2400 dpi 的 2120×2144 px 反算一致 ⇒ 与页几何自洽）；秦印常态 ≈22 mm 见方 ⇒ 落在常识域内。已登记 `config/book_dir_keys.json` 的 `print_size_1to1: true`（★★ **勾选框尚未落 UI**，见 §5，**本单不自编 R 号**）。

## §3 两版差异与实测读数（全 96 strip；`--verify-only` 独立进程复验同值）

| 读数 | 主版（0.35） | 冻结版（0） |
| --- | --- | --- |
| 容器 | 24472×17000×3／16bit×3＝48bit／Deflate 8／Predictor 2／BigTIFF ✓／96 strip／XRes 2400 dpi ✓ | 同左 |
| 解码 ≡ 重算**逐像素** | 失配 **0** px（max_abs 0） | 失配 **0** px |
| **内容冻结**（非纸底 ∧ 非印泥） | 11,379,210 px，失配 **0**、max_abs 0 | 同左（失配 0） |
| 印泥像素 | 16,267,606 px；**被改** 15,822,660 px；逐通道最大偏差 16,244 u16（＝63.21/255） | 16,267,606 px；**被改 0 px**（逐像素 ≡ `clip(8×Lanczos)` ⇒ 完全冻结） |
| Σ(R+G+B) 不变量（浮点域） | max |Δ| = **6.10e-05** ≤ tol 1e-3（残差＝float32 末位） | 0.0 |
| store 域 Σ 差（u16） | max 2（仅出现在「振铃越界被裁剪」像素） | 0 |
| 纸底色域（u8 取整） | [1,1,1]–[255,255,255]；越出声明域 3,713,526 px，**越出域∧越出晕染环带 ＝ 0** | 同左 |
| 裁件 ≡ 页图对应区域 | **0** px 失配（2120×2144） | **0** px 失配（另存样张） |
| 体积 / 压缩比 | 1,903,843,591 B／0.7627（对 2,496,144,000 B 原始） | 1,906,199,278 B／0.7637 |

- 纸底越出声明域的 3.71 M px **全部落在晕染环带内**（按设计向印泥均色收敛、可越出 `#FAFAF7` 下限）⇒ 环带外越界 0。
- ★ **主版与冻结版差在哪**：只在**印泥像素的色度**（15.82 M px）。纸底、印刷内容、几何、容器、裁件坐标**两版完全一致**。
- ⚠ 体积几乎相同（冻结版反而大 2.36 MB，+0.12%）：⑤ 把印泥色度向均色收敛后**压缩率并未变好**（色度平滑被后面 Deflate 的熵抵消）；**不要拿体积判两版差异**，只认像素口径。
- **独立进程 `--verify-only`（第二次全 96 strip 复验，两个 RC=0）**：两版的 `verification` 块与渲染轮的**逐键字节相等**（含 `sha256`、各项失配 0、Σ 残差 6.10e-05、裁件失配 0）⇒ 同时证明 ① 重算**确定性**、② 产物**未被改动**。渲染轮与验证轮的读数 JSON 可直接对拍（`readings-*.json` vs `readings-*.verify-only.json`）。

## §4 实现纪律（两条，都是实测踩出来的）

1. **tifffile 不接受「strip 数组迭代器」**（源码 docstring：*Iterators of strip ndarrays are not supported*；实测 yield `(256,17000,3)` 抛 `ValueError: cannot reshape array of size …`）⇒ 设计改成「流式处理 → scratch memmap → 一次 `TiffWriter.write(ndarray, compression=8, predictor=2, rowsperstrip=256, bigtiff=True, maxworkers=4)`」，让 tifffile 独占「切 strip ＋ predictor ＋ deflate」；v1 手写编码器把 Predictor/stripsize 契约写歪，产物只 379 MB（＝块解码不匹配）——**别再手写这一段**。
2. **Σ(R+G+B) 不变量的判据必须带「有效域闸」**（本单最后一改的修复，`--smoke` 抓到）：归一化色度 `c = px/Σpx` 在**振铃越界**像素上不良定义（实测最坏像素 `(−24.5, −26.9, 16.1)`、Σ = −35.4）；旧写法把 Σ 夹到 `1e-6` 后 `c` 放大到 ~1e7，float32 精度崩掉 ⇒ Σ 守恒从 ~1e-4 恶化到 **12.39**。修为「各通道 ∈ [0,255] ∧ Σ > 0 才参与换算，否则 `t=0` 原样返回」，并把判据由 `== 0.0` 改为 `≤ SUM_INVARIANT_TOL = 1e-3`（＜0.0039 u16 LSB；不变量代数上恒成立，残差只是 float32 末位）。⇒ **旧读数的「Σ 严格不变 0.0」是巧合口径**，现行读数是「≤6.1e-05 ＋ 跳过 444,787 越界像素」。
3. 另：`verify` 的计数（`realized_strength` / 面积占比）现改为**本次验证重算自己累计**（`ctx.counters.clear()` 后逐 strip `collect=True`）⇒ `--verify-only` 也有真读数（旧版在 `--verify-only` 下这两个读数是空的 0）。

## §5 待裁项（本单只登记，**不自编 R 号** —— 编号面归 Jing）

1. **① 内容零色彩改动 vs ⑤ 印泥色彩校准**：提示词内部冲突。**现行处置＝两版并存**（§0）；Kevin 选一版后可一句话关掉另一版。
2. **【印刷尺寸即实物尺寸】勾选框**（Kevin 需求）：配置侧 `print_size_1to1: true` 已落 `config/book_dir_keys.json`（含实测锚点 22.437×22.691 mm）；**UI 勾选框尚未实现**（导入类书时显示）。⚠ 待 Jing 按 §0.4 入册后再编号。
3. **「第一枚」＝阅读序（上→下、行内左→右）**；若要「中文阅读序右上首枚」，`CROP_BOX_300DPI` 一处常量可改。
4. **裁件位深**：现为 RGB 8-bit（O 件家法，`--crop-bits 8`）；要 48bit 逐位同页图 ⇒ 加 `--crop-bits 16`。
5. **仅第 29 页**：其余 850 页未出图（单页 ≈108 s ＋ 1.77 GiB ⇒ 851 页 ≈ 25.5 h / ≈1.5 TiB，**须先裁口径再谈批量**）。
6. **`--crop` 与 `--color-calib` 的绑定**：裁件必须与页图同参（否则 `vs_page_mismatch_px ≠ 0`）；换版重出时两个参数一起改。

## §6 复跑命令（照抄即可）

```bash
cd /Users/kevin/bistro/xiai/feicui
S=/tmp/p29-run && mkdir -p "$S"

# 0) 自检（必预 SMOKE PASS）
./venv/bin/python ops/book-page-2400/render_page_2400.py --smoke

# 1) 主版（含校准 0.35）＋第一枚裁件：渲染 + 写盘 + 全 96 strip 验证 + 读数
./venv/bin/python -u ops/book-page-2400/render_page_2400.py \
  --out  "output/book-pages/9787550847224/P29-2400dpi-48bit.tif" \
  --crop "output/book-pages/9787550847224/P29-C1-R1-无信息-戰國-佚名-O.tiff" \
  --color-calib 0.35 --scratch "$S" --progress "$S/calib.progress.jsonl" \
  --readings ops/book-page-2400/readings-P29-2400dpi-48bit.json      # ≈108 s

# 2) 冻结版（--color-calib 0）
./venv/bin/python -u ops/book-page-2400/render_page_2400.py \
  --out  "output/book-pages/9787550847224/P29-2400dpi-48bit-frozen.tif" \
  --crop "output/samples/book-page-2400/P29-C1-R1-frozen-page-crop.tiff" \
  --color-calib 0 --scratch "$S" --progress "$S/frozen.progress.jsonl" \
  --readings ops/book-page-2400/readings-P29-2400dpi-48bit-frozen.json

# 3) 只验证（独立进程；两版各自出读数）
./venv/bin/python -u ops/book-page-2400/render_page_2400.py --verify-only \
  --out "output/book-pages/9787550847224/P29-2400dpi-48bit.tif" \
  --crop "output/book-pages/9787550847224/P29-C1-R1-无信息-戰國-佚名-O.tiff" --color-calib 0.35 \
  --readings ops/book-page-2400/readings-P29-2400dpi-48bit.verify-only.json
# 冻结版同理：--color-calib 0 ／ --out …-frozen.tif ／ --crop samples 里的冻结裁件
```

- 退出码：`0` ＝ 十项检查全 `true`；任一为 `false` ⇒ `1`（检查项见读数 JSON 的 `checks`）。
- 长跑纪律：**务必 `background + notify`**，用 `process_manage` 等；`--progress` 的 JSONL 是逐 strip 心跳（`elapsed_s` / `crop_rows_filled`）。

## §7 证据件（`ops/` 入库）与红线

| 文件 | 内容 |
| --- | --- |
| `geometry_report.json` / `.py` | 851 页页尺寸分布（众数 510.0×734.16 pt）／页 29 源图 300 dpi 实测／目标 2400 dpi 几何／无文本层 |
| `first_seal_probe.json` / `.py` | 页 29 六枚印面 bbox（300 dpi）＋阅读序 ＋ 首枚 @2400 dpi 坐标与 mm |
| `render_page_2400.py` | 本线唯一实现（`--smoke` / 全页 / `--verify-only` / `--samples`） |
| `readings-*.json` ×4 | 两版 ×（渲染 ＋ 独立 `--verify-only`）读数与 `checks` |
| `recon_p29_*.jpg|png` | 人看用的重建预览（300 dpi 页 / 掩膜 / 缩略） |

**红线（本单已守）**：不写 `yinpu.db`（本单零 DB 写）；不动 `output/seals/`；不建 job；大 TIFF 落在 `output/`（已 gitignore）**不入库**；提交只用显式 pathspec（`ops/book-page-2400/ config/book_dir_keys.json`），**永不 `git add -A`**。
