# 影像颜色校正 V2 · 双锚点仿射（Kong 单 · 2026-10-11）

口径真源：`feicui/docs/image-color-tiff-draft-v0.1.md`（§2.2 算法口径 / §4 验收候选）
＋ **Zang / Kevin 2026-10-11 追加裁定**（双锚点仿射、纸锚点→`#FFFFFF`、主色调＝印泥**核心**质心）。
本目录是**地基单**的产物：只交付 **纯函数模块 ＋ 自检 ＋ 语料实测读数**，**不接入任何线、不重出任何 TIFF、不写 DB**。

> **V2 覆盖 V1**：V2 把 V1 的「单条对角增益」**升级为「双锚点仿射」**，默认路径即 V2；
> V1 对角函数**保留为兼容 / 对照**（`gains_for` / `apply_correction` / `correct_image_diagonal`），**不再作默认路径**。
> 理由见 §5.1（V1 对角口径**数学上无法**同时满足「印泥→`#C95021`」与「纸保中性」）。

## 1. 交付物

| 文件 | 角色 | 入库 |
| --- | --- | --- |
| `server/app/colorcal.py` | **校正算法唯一实现**（纯函数；两侧共用）——**默认 V2 双锚点仿射** ＋ V1 对角兼容 | ✅ |
| `ops/image-colorcal/selfcheck_colorcal.py` | 自检脚本（派单 a–f ＋ V2 追加断言） | ✅ |
| `ops/image-colorcal/selfcheck_output.txt` | 自检输出（**23/23 PASS**） | ✅ |
| `ops/image-colorcal/corpus_readings_affine.py` | **新**语料复测脚本（V2 vs V1 对照；**只读** 6347 件、抽样 120） | ✅ |
| `ops/image-colorcal/corpus_readings_affine.json` | **新**语料读数（**聚合 ＋ 120 抽样 ＋ 对照**） | ✅ |
| `ops/image-colorcal/corpus_readings_affine_output.txt` | **新**语料读数人读汇总 | ✅ |
| `ops/image-colorcal/corpus_readings.py` / `.json` / `_output.txt` | **上单 V1 对角口径**历史证据（`.py` 已改为显式调 `correct_image_diagonal`） | ✅（不改历史） |

**未改任何既有产品文件 / DB**（`git status` 仅本目录 ＋ `colorcal.py` ＋ 上游 Zang 的口径件）。

## 2. 模块接口（`server/app/colorcal.py`）

常量：`TARGET_RGB=(201,80,33)`（`#C95021`，锚点②）、`WHITE_RGB=(255,255,255)`（`#FFFFFF`，锚点①）、
`A_MIN=0`、`A_MAX=3`、`B_MIN=−255`、`B_MAX=255`、`PAPER_QUANTILE=0.90`、`INK_CORE_SAT_QUANTILE=0.75`、
`DEGENERATE_MIN_LIN=0.02`、`INK_RATIO_MIN=0.02`（**皆单点可改**）。

| 函数 | 作用 |
| --- | --- |
| `ink_mask(rgb)` | 印泥掩膜：`r>g+15` 且 `r>b+15` 且 `S>0.25`（**V2 未变**） |
| `ink_core_centroid(rgb, sat_quantile=0.75)` | **主色调 C＝核心质心**：掩膜内**饱和度 ≥ p75** 的像素均值（＋`linear255`） |
| `paper_centroid(rgb, quantile=0.90)` | **纸锚点 W**：**亮度 `V=max(RGB)/255 ≥ p90`** 的像素均值 |
| `affine_for(C, W, target, white, a_min…b_max, degenerate_min_lin)` | **双锚点仿射系数**：`a=(T−255)/(C−W)`、`b=255−a·W`（线性 0–255 标度）；含 `clamped / raw_a / raw_b / degenerate / degenerate_reason / min_lin_component` |
| `apply_affine(rgb, affine)` / `apply_affine_color(rgb, affine)` | 整图 / 标量施加仿射（线性往返、sRGB 回程） |
| `delta_e2000(a,b)` ／ `ciede2000_lab(l1,l2)` | CIEDE2000（**手写**，零 skimage/cv2）；含 Sharma 34 组自检 |
| `correct_image(rgb, …)` | **默认路径（V2）** → `(校正后图, 报告 dict)`：`applied / skipped(ink_ratio=…) / skipped(degenerate)`、核心前后质心、全体前后质心（观察）、前后 ΔE、纸区→白 ΔE、纸区色相、`gray180_after` |
| 兼容（V1） | `gains_for` / `apply_correction` / `correct_image_diagonal`（**不再作默认路径**） |
| 辅助 | `ink_centroid` / `paper_mask` / `region_mean_rgb` / `rgb_to_hsv` / `srgb_to_lab` / `skip_marker(_degenerate)` |

**算法（§2.2 V2）**：① 掩膜不变；② 核心质心 `C`（掩膜 ∩ `S≥p75`）→ `#C95021`；③ 纸区质心 `W`（`V≥p90`）→ `#FFFFFF`；
④ 两点定线，每通道 `out = a·in + b`（**线性 RGB 中解、sRGB 往返**），限幅 `a∈[0,3]`、`b∈[−255,255]`；
⑤ **越界**（`limiting`）或 **病态**（线性任一分量 `|C−W| < 0.02`，`degenerate`）⇒ `skipped(degenerate)`（**不得静默**）；
⑥ `ink_ratio < 2%` ⇒ `skipped(ink_ratio=…)`。

**两侧共用**：`numpy` 为**可选依赖**——缺 numpy 时模块仍可被接口层 `server/.venv` import（常量 ＋ 纯算术函数
`delta_e2000` / `affine_for` / `gains_for` / `apply_affine_color` 均可用），仅**像素函数**调用时抛 `RuntimeError`。自检已实测。

## 3. 自检结果（`selfcheck_output.txt`，**23/23 PASS**）

| 派单项 | 断言 | 结果 |
| --- | --- | --- |
| (a)/(f) | `ciede2000_lab` 对 **Sharma, Wu & Dalal (2005)** 官方 **34 组** Lab 色对，容差 `1e-4` | PASS，**最大误差 4.95e-05** |
| (a) | `delta_e2000(rgb,rgb)=0`；`delta_e2000(黑,白)=100.0000` | PASS |
| (b) | 合成图（纸 `(234,224,200)` ＋ 印泥 `(200,95,45)`）校正后：**印泥核心质心→`#C95021` ΔE=0.0000 ≤ 2** | PASS |
| (b) | 同图：**纸区质心→`#FFFFFF` ΔE=0.0000 ≤ 3**（两条**同时**成立，`a=(1.696,1.458,1.786)`∈[0,3]） | PASS |
| (c) | 退化用例（纸≈印泥色 ⇒ 线性 `|C−W|` 分量=0）⇒ `mode=skipped`、`marker=skipped(degenerate)`、`skip_reason=degenerate` | PASS |
| (d) | 限幅越界用例（`raw_a_r=5.447`）⇒ `skipped(degenerate)`、`skip_reason=limiting`、**标记可见**（`clamped=True` 通道 `['r']`） | PASS |
| (e) | `ink_ratio=1%＜2%` ⇒ `mode=skipped`、`marker=skipped(ink_ratio=0.010000)`、图**逐字节未改** | PASS |

（其余：`ink_mask` 逐像素判据、`apply_affine(a=1,b=0)` 恒等、接口层 `server/.venv` 无 numpy 可 import。）

## 4. 语料实测（`corpus_readings_affine.json`）

**抽样**：`var/seal_images_tiff/**/*.tiff` 全 **6347** 件按路径排序后**等距系统抽样** `idxᵢ=round(i·N/n)`，`n=120`
（**与上单同口径**）。**只读**、不写盘、不写 DB、不建 job。

### 4.1 新旧对照表（applied 行）

| 指标 | **新（双锚点仿射）** | 旧（对角增益） |
| --- | --- | --- |
| ΔE_core 前（核心质心→`#C95021`，全体 ok） | p50 **11.87** / p90 30.10 / max 35.86 | 同左 |
| **ΔE_core 后**（核心质心→`#C95021`） | p50 **0.42** / p90 **5.17** / max **11.30** | p50 10.73 / p90 12.94 / max 22.99 |
| ΔE_all 后（掩膜全体质心，**观察项**） | p50 23.05 / p90 27.13 / max 31.38 | p50 11.09 / p90 14.04 / max 19.29 |
| **纸区质心 → `#FFFFFF` ΔE 后** | p50 **2.59** / p90 **3.57** / max **5.04** | p50 30.52 / p90 33.17 / max 35.30 |
| 纸区色相偏移° | p50 **−6.88** / p90 0.91 / max 11.81 | p50 −12.38 / p90 −10.88 |
| ΔE_core ≤ 2 命中 | **25 / 33** | 0 / 72 |
| ΔE_core ≤ 5 命中 | **29 / 33** | 0 / 72 |

### 4.2 skip / 限幅 触发率（按子因分桶）

| | 新（仿射） | 旧（对角） |
| --- | --- | --- |
| applied / skipped | 33 / 87（skip_rate **0.725**） | 72 / 48（skip_rate 0.400） |
| └ `ink_ratio`（<2%） | 48（**0.400**） | 48（0.400） |
| └ `degenerate`（**病态**） | **0**（0.000） | —（此路径无） |
| └ `limiting`（**越界**） | **39（0.325）** | — |
| 限幅（clamp/越界）触发 | 越界 39/120 命中通道 | **clamp 100%**（72/72 applied 全 clamp） |

### 4.3 新读数（V2 追加）

| 读数 | 值 |
| --- | --- |
| `a` 分布（applied） | r p50 **0.945** / p90 1.317；g p50 **1.734** / p90 2.124；b p50 **2.362** / p90 2.927 |
| `b` 分布（applied，线性 0–255 标度） | r p50 **+36.7** / p90 79.6；g p50 **−21.6** / p90 1.4；b p50 **−34.3** / p90 −11.3 |
| `min|C−W|_lin`（病态阈 0.02） | p50 0.2969 / p90 0.4408 / min 0.1823 ⇒ **无一病态** |
| 纸区质心色（中位） | 前 `(234.6, 210.7, 189.4)` → **后（新）`(253.5, 248.3, 246.5)`**（→纯白）；后（旧）`(228.0,146.9,125.9)`（→偏红） |
| **中灰 180 校正后色（中位，applied）** | 新 `(200.2, 214.8, 244.7)`（**偏冷/蓝**）；旧 `(176.0, 131.0, 131.0)`（偏红） |

### 4.4 抽样 5 张逐张读数（新，applied）

| sha8 | 印泥% | 核心质心(前) | 核心质心(后·新) | ΔE 前 | ΔE 后(新) | ΔE 后(旧) | 纸偏移°(新) | 纸→白 ΔE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 03ac720b | 5.95 | (76,57,39) | (201,80,32) | 29.00 | **0.31** | 22.99 | −2.25 | 1.04 |
| 09e2ce87 | 68.50 | (174,83,68) | (201,78,32) | 9.76 | **0.47** | 12.63 | −8.15 | 2.65 |
| 0d84221c | 8.00 | (180,107,96) | (201,75,34) | 13.03 | **1.87** | 10.90 | 1.05 | 2.13 |
| 139fed67 | 76.04 | (190,96,73) | (201,64,42) | 7.33 | **6.32** | 9.32 | 11.81 | 1.10 |
| 17e8e3b3 | 63.56 | (186,69,53) | (201,80,31) | 8.54 | **0.40** | 10.85 | −4.82 | 3.05 |

## 5. ★ 关键发现（实测，供 Zang / Jing / Neng / R 裁）

1. **V2 双锚点仿射把「印泥→`#C95021`」与「纸→`#FFFFFF`」同时做成。** applied 行 `ΔE_core` 中位 **0.42**、p90 **5.17**、
   `≤2` 命中 **25/33**、`≤5` 命中 **29/33**；纸→白 ΔE 中位 **2.59**。**对照 V1 对角口径**：`ΔE_core` 中位 **10.73**、
   `≤2/≤5` 命中 **0/72**，且纸区**被染红**（纸→白 ΔE 中位 30.52、色相偏移中位 −12.38°）。⇒ **口径升级成立**。
2. **「主色调＝核心质心」修正了病态定线。** 掩膜全体均值离纸色太近 ⇒ V1 需 `a` 达 3.3〜8.7（越限幅）；
   改用核心质心（`S≥p75`）后实测 `a` 落在 `0.73〜2.96`（p90：g 2.12 / b 2.93）——裁定判断被实测印证。
3. **★ 新口径的瓶口＝「越界跳过率 32.5%」（39/120），且几乎全部是「蓝通道 `a>3`」。** 高印泥占比图（ink 80〜96%）
   的「纸区＝亮度 p90 像素」实为**较亮的印泥**，与核心质心**离得近** ⇒ 两点定线陡（`a_b` 3.0〜3.9，**刚越 3.0**），
   `limiting` 跳过。**反事实（诊断，非口径）**：若纸区改取「**非印泥** ∧ `V≥p90(非印泥)`」的均值，
   则 `limiting` 降至 **10/71≈14.1%**、applied 升至 61、`ΔE_core` 中位仍 **0.43**。⇒ **请裁**：抬 `A_MAX`（如 4.0）、
   或纸区**排除印泥像素**、或接受 32.5% 跳过。**（本单不改口径，仅报读数。）**
4. **「全体质心」口径必须与「核心质心」分开。** 判定用**核心质心**（→ΔE 中位 **0.42**）；掩膜**全体**质心会**变差**
   （本单读数 p50 **23.05**、max 31.38，且**方向与 Zang 预判一致**：纸→纯白使全图偏冷，全体均值掺入变白后的纸 ⇒ 质心偏冷偏离靶色）。
   **不得**拿全体质心当判据（`centroid_all_*` 仅观察项）。
5. **「整体变冷」已量化。** 中灰 180 校正后中位色：**新 `(200.2, 214.8, 244.7)`（蓝 > 红，偏冷）**。
   这是「纸→纯白」口径的**必然副产品**：为把暖纸推成纯白，须压红/提蓝 ⇒ 中性灰随之偏冷。
   ⇒ 若「灰阶保中性」是硬要求，则**纸锚点是否应改为 `#FFFFFF`**需再裁（V1 旧口径灰偏红 `(176,131,131)`）。
6. **skip 率仍高（新 72.5% = ink_ratio 40.0% ＋ 越界 32.5%）。** `ink_ratio` 部分与上单一一致（语料 `ytsw`/`yzbk` 类多无红印泥）；
   越界部分见发现 3。⇒ 直接影响 R-c 与「印谱线对无印泥图要不要也跳过」的判断。

## 6. 复跑

```bash
cd /Users/kevin/bistro/xiai/feicui
venv/bin/python ops/image-colorcal/selfcheck_colorcal.py          # 自检（23/23 期望）
venv/bin/python ops/image-colorcal/corpus_readings_affine.py      # V2 vs V1 对照读数（只读，≈1 min）
venv/bin/python ops/image-colorcal/corpus_readings.py            # 上单 V1 对角口径读数（历史复现，只读）
```

## 7. 明确未做（后续单的事）

- ❌ 未接入**印章采集线**（不重出 6347 张 TIFF、不出包、不入 xiai 影像库）。
- ❌ 未接入**印谱解析线**（不产 `.tiff`、不动 `stamps`、不写 `img_path_tiff`）。
- ❌ 未建 job、未写生产库 `/Users/kevin/bistro/xiai/data/yinpu.db`、未动任何既有 TIFF / webp。
- ❌ 未按发现 3 / 5 改口径（`A_MAX` / 纸区定义 / 纸锚点目标）——**属裁定，本单只报读数**。
