# Round4 · 示例纹理合成（exemplar-based，豆包纸底）

现行程序化宣纸纹理判不合格（含 10 档色域参数）⇒ 本单不再调色域/幅度，改从豆包参照图
`~/Library/Application Support/Hermes/composer-images/image_673b34.png`（1536×1536，**只读引用**）
的纸底直接学纹理形态。尺度口径：`ma.MM_PER_PX = 22.437/923`（明示假设：豆包印面实物宽＝C1-R1 印面 22.437 mm）。

## ① 素材充足性评估（先做，结论：**不够**）

脚本 `round4_material_adequacy.py` → `readings-round4-material-adequacy.json`（全量读数）。

- **可用纸底**：排除印泥/溅红渗色（513k px）/文字水印/暗角 + 0.4 mm 印泥晕圈 + 边缘 6 px 后，
  **仅 1 个连通块，1,531,429 px ＝ 904.9 mm²**（占全图 64.9%；约为 9.05 cm²，≈3.1×3.1 cm）。
- **最大全净 patch 只有 4 mm 见方**：4 mm 不重叠 patch **13 块**（209.1 mm²；含半步位置 62 个）；
  5 mm 仅 1 块，6 mm 为 0。素材里没有一块 ≥5 mm 的纯纸可作整单元。
- **独立纹理单元**：主导单元波长 λ≈1.26 mm（coarse 带峰）⇒ 素材含约 **572** 个独立单元；
  8500×12236 整页需约 **29,458** 个 ⇒ **平均复用 ≈51.5×**（面积比口径，与尺度无关）。
- **视觉可辨重复**（30 cm 观读、2° 视角 ⇒ 重复尺度 ~10.5 mm）：素材仅容纳 **8.2** 个视觉单元，
  整页需 **422.7** 个 ⇒ 同样 **51.5×复用**。patch quilting 无论怎么拼，同形态平均重复 50+ 次。
- 另：素材纸底自带低频照明梯度（3 mm 低通 p1–p99＝5.17/255），整页拼贴会把梯度碎片化。

**判定：现有素材不足以生成 8500×12236 无可见重复的整页**（复用 51.5× ≫ 1）。
本单按指示仍交三版样张（R2/R1/R3，见下）用于看"像不像"，但**无可见重复**这一条只有换素材才可能达标。

**需要 Kevin 再给的素材**（按优先级）：
1. **2–3 张整页空白宣纸照片**（A4 ≈ 624 cm²/张 ⇒ 2 张即 >1000 cm²，复用 <1）；实拍时纸面加标尺或说明 dpi；
2. 或 **8–12 张**与现素材同构图的豆包纸底照（每张干净纸底 ≥60 cm²，印面只占小部分）；
3. 拍摄要求：均匀光照（避免照明梯度）、对焦纸面纤维、长边 ≥2000 px、同批同色温。

## ② 三版样张（R2 / R1 / R3）

脚本 `round4_texture_mimic.py`（种子 20261016，确定性；mm 物理尺度 × dpi 换算）→
`readings-round4.json`（全量读数）＋ `output/samples/book-page-2400-variants/round4-texture-mimic/`：

- **R2 patch quilting**：4 mm patch（重叠 0.68 mm）最小误差边界（SSD＋top-4 随机）＋羽化＋局部均值对齐；
- **R1 频谱匹配**：估豆包分带（mm）幅度/峰波长/各向异性 → `round2_samples.vnoise_mm` **mm 位置哈希**
  随机相位重建（跨 dpi 同一场，不复制素材像素）；
- **R3 混合**：低频云斑（1.35–3 mm）取豆包条带（行高 3.5–6.5 mm 抖动拼铺＋1.5 mm 羽化），
  高频（≤1.35 mm）走 R1 机制。

每版：600/1200 dpi 局部 1:1、整页 800 px 缩略、与豆包参照并排 1:1 对照板；另有 `all-versions-vs-doubao-600dpi-1to1.png` 总板。

### 读数摘要（判据①③；全量见 `readings-round4.json`；参照＝13 个 4mm 豆包净 patch 中位）

| 版 | vs豆包 带能量占比 L1 | 带RMS rel_diff（cloud/coarse/fine/grain） | lum_std syn/ref | 明度 p50 syn/ref | 无重复（整页600dpi 场 ac） | 双dpi max rel | 确定性 |
|---|---|---|---|---|---|---|---|
| R2 quilting | 0.314 | 9.2% / 13.6% / 11.9% / 22.4% | 3.40 / 3.95 | 244.0 / 245.1 | **远距(>20mm) ac 0.367**；短距峰 3.1–4.3mm @0.46–0.47（patch 复用固有，非规则格距；格距抖动前规则网格在 3.3mm 出 0.65 强峰） | 0.116 | ✓ 逐位一致 |
| R1 频谱 | **0.113** | 12.0% / 3.9% / 3.6% / 4.5% | **3.947 / 3.950** | 245.2 / 245.1 | **ac>20mm 仅 0.0019，无任何周期峰** | 0.341* | ✓ |
| R3 混合 | **0.111** | **2.2% / 2.4% / 0.1% / 9.1%** | 3.994 / 3.950 | 245.0 / 245.1 | **ac>20mm 仅 0.0059，无周期峰** | 0.224* | ✓ |

\* 双 dpi rel_diff 明细：mm 带 RMS 的 cloud/coarse rel ≤1%、fine ≤4.7%，**grain ~19%**、half_decay_y rel 22–34%——
grain/half-decay 差来自 2400→1200 INTER_AREA 下采样对 ~0.06mm 细粒的轻微低通（b 场 grain RMS 1.65 vs a 场 2.04），
非 mm 尺度失配（位置哈希场本身跨 dpi 同一场；mm 物理波长逐带一致）。lum_std rel 8.2–8.7%。
R2 双 dpi max 0.116（grain）。

**判读**：
- **像不像**：R1/R3 与豆包的分带 RMS/明度分位高度一致（R3 全带 rel ≤9%，总 RMS rel 1.1%）；
  R2 因羽化平均与局部对齐略软（lum_std −14%，grain −22%），但形态是素材本身的。
- **无重复**：R1/R3 达标（合成场，无像素复制，远距 ac ≤0.006）；**R2 不达标且无法达标**——
  61 个不同 patch 撑 26 Mpx 页（复用 51.5×），远距 ac 0.37 是素材稀缺的直接证据，与 ① 结论互证。
- **结论**：可无重复放大到整页的路径是 **R1/R3（频谱/混合）**；R2 只适合小面积（≤素材独立单元数支撑的面积）
  或作为拿到更多素材后的拼贴基线。


## ④ 顺手修一处（已完成）

`ops/book-page-2400/render_page_2400.py::write_tiff`：`TiffWriter(..., shaped=False)`。
真因实测（本库 tifffile 2026.3.3）：`shaped` 是 **TiffWriter 构造参数**；默认把 `{"shape": ...}` JSON
写进 `ImageDescription`(270) 且顶掉 `description=` ⇒ 270 只剩 shape JSON ⇒ macOS sips/Quick Look 读不到
（`pixelWidth <nil>`）。改后**重出 1200dpi 页 29**：`sips -g pixelWidth` ＝ **8500**、pixelHeight ＝ 12236，
270 只剩 description 一条；其余属性（Deflate/Predictor 2/RowsPerStrip 256/1200dpi/RGB 16bit/经典 TIFF/Software）逐项与原件一致。

## 纪律

豆包图只读；生产常量一字不动（只 import）；不写 yinpu.db、不建 job；
产物只进 `output/samples/book-page-2400-variants/round4-texture-mimic/` 与 `output/2_HighRes_PDF/`（页 29 重出）。
