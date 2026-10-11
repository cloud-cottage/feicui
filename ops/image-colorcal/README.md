# 影像颜色校正 V1 · 地基模块（Kong 单 · 2026-10-11）

口径真源：`feicui/docs/image-color-tiff-draft-v0.1.md`（**§2.2 算法口径 / §4 验收候选**）。
本目录是**地基单**的产物：只交付 **纯函数模块 ＋ 自检 ＋ 语料实测读数**，**不接入任何线、不重出任何 TIFF、不写 DB**。

## 1. 交付物

| 文件 | 角色 | 入库 |
| --- | --- | --- |
| `server/app/colorcal.py` | **校正算法唯一实现**（纯函数；两侧共用，口径件 §2.5 红线 3） | ✅ |
| `ops/image-colorcal/selfcheck_colorcal.py` | 自检脚本（派单 ② a–d） | ✅ |
| `ops/image-colorcal/selfcheck_output.txt` | 自检输出（15/15 PASS） | ✅ |
| `ops/image-colorcal/corpus_readings.py` | 语料实测脚本（派单 ③，**只读** 6347 件 TIFF，抽样 120） | ✅ |
| `ops/image-colorcal/corpus_readings.json` | 语料读数（**聚合 ＋ 120 抽样**；不 dump 全量） | ✅ |
| `ops/image-colorcal/corpus_readings_output.txt` | 语料读数人读汇总 | ✅ |

**未改任何既有文件 / 产物 / DB**（`git status` 只有上述新增 ＋ 上游 Zang 的口径件）。

## 2. 模块接口（`server/app/colorcal.py`）

常量：`TARGET_RGB=(201,80,33)`（`#C95021`，**唯一常量、单点可改**）、`K_MIN=0.5`、`K_MAX=2.0`、`INK_RATIO_MIN=0.02`。

函数：

| 函数 | 作用（§2.2 对应） |
| --- | --- |
| `ink_mask(rgb)` | 印泥掩膜：`r>g+15` 且 `r>b+15` 且 `S>0.25`（§2.2.1） |
| `ink_centroid(rgb)` | → `(质心色, 印泥占比)`（§2.2.2） |
| `gains_for(centroid, target, k_min, k_max, space='linear-rgb')` | 通道增益 `k=target/C`（**线性 RGB 中算、sRGB 往返**），clamp 到 `[k_min,k_max]`，返回含 `clamped / clamped_channels / raw_gains`（§2.2.3） |
| `apply_correction(rgb, gains)` | 整图施加同一变换（线性 RGB 逐通道乘增益；同 shape/dtype） |
| `delta_e2000(rgb_a, rgb_b)` | CIEDE2000（**手写**，零 skimage/cv2）；另公开 `ciede2000_lab` |
| `correct_image(rgb, target, ink_ratio_min=0.02)` | → `(校正后图, 报告 dict)`；报告含 `applied / skipped(ink_ratio=…) / clamp`、前后质心、前后 ΔE2000、纸区色相漂移 |
| 辅助 | `paper_mask` / `region_mean_rgb` / `rgb_to_hsv` / `srgb_to_lab` / `hex_to_rgb` / `skip_marker` |

**两侧共用**：`numpy` 为**可选依赖**——缺 numpy 时模块仍可被接口层 `server/.venv` import（常量 ＋ 纯算术函数可用），仅**像素函数**在调用时抛 `RuntimeError`。自检已实测该形态（`server/.venv` 无 numpy ⇒ import ✓、常量 ✓、`delta_e2000` ✓、`gains_for` ✓、`ink_mask` 抛错 ✓）。

## 3. 自检结果（`selfcheck_output.txt`，15/15 PASS）

| 派单项 | 断言 | 结果 |
| --- | --- | --- |
| (a) | `ciede2000_lab` 对 **Sharma, Wu & Dalal (2005)** 官方 **34 组** Lab 色对，容差 `1e-4` | PASS，**最大误差 4.95e-05** |
| (a) | `delta_e2000(rgb,rgb)=0`；`delta_e2000(黑,白)=100.0000` | PASS |
| (b) | 合成图（印泥 `(200,95,45)` ＋ 纸 `(234,224,200)`）校正后质心→靶色 **ΔE2000 = 0.0000 ≤ 2**（前 3.92，无 clamp） | PASS |
| (c) | 纸区色相偏移**读数** = **−15.77°**（如实回报；见 §5 发现） | PASS（有限读数） |
| (d) | `ink_ratio=1%＜2%` ⇒ `mode=skipped`、`marker="skipped(ink_ratio=0.010000)"`、图**逐字节未改**、`ΔE_after==ΔE_before` | PASS |
| (d) | 边界 3%＞2% ⇒ `applied` | PASS |

CIEDE2000 参考来源逐字照登于脚本 `SHARMA_PAIRS`（34 组）＋ 期望值；`delta_e2000`（sRGB 入口）与 `ciede2000_lab`（Lab 核心）共用同一算法。

### 「业界已知色对」为何是 Lab 三元组
Sharma 官方测试数据给的是 **Lab 三元组**（如 `(50, 2.6772, −79.7751)`）。故已知色对断言打在 **Lab 核心** `ciede2000_lab`；`delta_e2000(rgb,rgb)` 只是同一核心的 sRGB 入口（自检另附 `rgb,rgb→0` 与 `黑/白≈100` 两条 sRGB 断言）。**未**把 Sharma 的 Lab 反算成 sRGB（部分色对超出 sRGB 色域，反算会裁剪致假误差）。

## 4. 语料实测读数（`corpus_readings.json`）

**抽样方式**：`var/seal_images_tiff/**/*.tiff` 全 **6347** 件按路径排序后**等距系统抽样** `idxᵢ=round(i·N/n)`，`n=120`（覆盖首尾、跨 256 个 sha 前缀目录）。**只读**、不写盘、不写 DB、不建 job。

| 读数 | 值 |
| --- | --- |
| 印泥占比 | p50 **0.115**，`[0.0000, 1.0000]`（min 非零 ≈ 5.8e-05） |
| 质心 HSV | H p50 **24.1°**、S p50 **0.354**、V p50 **0.795** |
| ΔE2000（校正前，质心→靶色） | p50 **22.78**，p90 32.41，max 36.53 |
| ΔE2000（**校正后**，applied） | p50 **11.09**，p90 14.05，max 19.29 |
| ΔE 改善量 | p50 **9.04** |
| **skip 触发率** | **40.0%**（48/120，`ink_ratio<2%`；语料含 `yt/ytsw/yzbk` 三类，释文/边款图多无红印泥） |
| **clamp 触发率** | **applied 中 100%**（72/72）；命中通道：`b` 72、`g` 68、`r` 1 |
| raw 增益（clamp 前）p50 | r **0.950**、g **0.262**、b **0.072** |
| 纸区色相偏移（applied） | p50 **−20.84°**，p90 −17.92°，max\|29.19\|° |

**抽样 5 张逐张读数（校正前后质心 / ΔE / 纸区色相偏移）**

| sha8 | 尺寸 | 印泥% | 质心(前) | 质心(后) | ΔE 前 | ΔE 后 | 纸偏移° |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 03ac720b | 68×136 | 5.95 | (134,113,92) | (174,81,66) | 20.87 | 9.69 | −22.86 |
| 09e2ce87 | 310×292 | 68.50 | (212,161,132) | (201,117,96) | 22.58 | 11.96 | −22.08 |
| 0d84221c | 267×195 | 8.00 | (196,138,127) | (201,100,92) | 19.23 | 12.59 | −16.89 |
| 11883588 | 242×236 | 91.37 | (213,171,132) | (201,125,96) | 26.15 | 12.73 | −22.60 |
| 139fed67 | 808×965 | 76.04 | (217,169,132) | (201,123,95) | 24.86 | 12.41 | −20.01 |

## 5. ★ 关键发现（实测，供 Zang / Jing / Neng / R 裁）

1. **`k_min=0.5` 下限 clamp 在现语料上 100% 触发，是 CA-1 不达标的唯一阻因。**
   raw 增益 p50 为 `g=0.262`、`b=0.072`——都远低于 0.5 ⇒ 被 clamp 到 0.5 ⇒ **校正后质心够不到 `#C95021`**（ΔE 后 p50 = 11.09，`≤5` 命中 **0/72**，`≤2` **0/72**）。
   **反事实**（只 clamp 上限 2.0、放开下限）：ΔE 后 p50 = **0.011**、p90 0.05、max 5.74，`≤2` 命中 **71/72**。
   ⇒ 口径件 §4 **CA-1「ΔE2000 ≤ 5」在默认参数下恒不可达**；要么放宽 `k_min`（甚至去掉下限）、要么改 CA-1 期望。**归 R 裁**（属 R-c 邻域，建议单列）。
2. **「纸保中性 / 白点不漂」与实测不符。** §2.2.3 的对角增益（`out=k⊙in`，无偏移）**只在 3 个 k 相等时才保白**；本语料需强压绿/蓝 ⇒ **纸区色相偏移 p50 ≈ −21°**（向红偏）。对角增益**数学上不可能**同时「C→T」且「白不动」——后者需**仿射/偏移**变换（口径件未给）。→ CA-2 的「色相偏移 ≤ 阈值」需要一个**非零阈值**，并请 Jing 澄清 §2.2.3 的表述。
3. **skip 率 40%（远超直觉的「个别边款图」）。** 语料的 `ytsw`（印文释文）/`yzbk`（边款）类多数无红印泥 ⇒ 阈值 2% 会跳过四成。→ 直接影响 R-c 与「印谱线要不要对无印泥图也跳过」的判断。
4. **校正会把纸也推进印泥掩膜。** 首张样本 `ink_ratio` 校正后升至 **1.0**（整图）。报告里给了 `ink_ratio_after` 作观察项——**莫把「校正后重算掩膜」当作质心判据**（见下 §6 口径歧义 1）。
5. **口径歧义：`centroid_after` 用哪套像素集合？** 本实现＝**校正前同一印泥掩膜**在纠正图上的均值（无 clamp 时恰＝target，正是「把印泥质心映射到目标色」的判据）；若「重算掩膜」则纸会掺入、质心漂向纸（本语料可差数十 ΔE）。**规范须明写**，否则 CA-1 会因口径不同而两边打架。

## 6. 复跑

```bash
cd /Users/kevin/bistro/xiai/feicui
venv/bin/python ops/image-colorcal/selfcheck_colorcal.py         # 自检（15/15 期望）
venv/bin/python ops/image-colorcal/corpus_readings.py            # 语料读数（只读，≈1 min）
```

## 7. 明确未做（后续两单的事）

- ❌ 未接入**印章采集线**（不重出 6347 张 TIFF、不出包、不入 xiai 影像库）。
- ❌ 未接入**印谱解析线**（不产 `.tiff`、不动 `stamps`、不写 `img_path_tiff`）。
- ❌ 未建 job、未写生产库 `/Users/kevin/bistro/xiai/data/yinpu.db`、未动任何既有 TIFF / webp。
