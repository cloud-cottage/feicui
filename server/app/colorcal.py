"""影像颜色校正 V2（**双锚点仿射**）—— **纯函数模块**（两侧共用唯一一份实现）。

口径真源：`feicui/docs/image-color-tiff-draft-v0.1.md`（§2.2 算法口径 / §4 验收候选）。
本模块是 **Kong 地基单**（先行）的产物：只提供纯函数 ＋ 常量，**不接入任何线、不读写文件 / DB**。

算法 V2（**双锚点仿射**，承 Zang / Kevin 2026-10-11 追加裁定）：
  1. **印泥掩膜** `ink_mask`：`r > g+15` 且 `r > b+15` 且 `S > 0.25`（`S =(max−min)/max`）。**未变**。
  2. **印泥锚点 `C`＝「主色调」＝核心质心**：掩膜内**饱和度 ≥ p75** 的像素均值（**非**掩膜全体均值——
     全体均值含大量淡边像素、离纸色太近 ⇒ 两点定线病态）。
  3. **纸区锚点 `W`**：**「非印泥 ∧ 亮度（`V=max(RGB)/255`）≥ p90」** 的像素均值（**★ v0.1 修订 3**）。
     纸集**先排除印泥像素**，再在**非印泥集**上取 p90 —— 高印泥占比的页上，若把淡印泥算进纸集，
     `W` 被拉近 `C` ⇒ 两点定线病态、**蓝/绿通道 `a` 越界**（实测 120 抽样 limiting **32.5% → 14.1%**、
     生效 **33 → 61**，而 ΔE 中位不变）。开关 `paper_centroid(..., exclude_ink=True)`（**默认 True**）；
     `exclude_ink=False` 只作**对照读数**（旧口径）。
  4. 两点定线，**每通道 `out = a·in + b`**（**线性 RGB 中解、sRGB 往返**）：
       锚点② `C` → **`#C95021`**（`TARGET_RGB`）；锚点① `W` → **`#FFFFFF`**（`WHITE_RGB`）。
       线性 0–255 标度上逐字成立：`a = (T − 255)/(C − W)`、`b = 255 − a·W`。
  5. **限幅** `a ∈ [A_MIN, A_MAX]`（默认 0 / 3）、`b ∈ [B_MIN, B_MAX]`（默认 −255 / 255）；
     **越界** ⇒ `skipped(limiting)`（`skip_reason="limiting"`，**★ v0.1 修订 4：独立标记，不再并入 degenerate**；
     默认**不放宽上限**）；**病态**（线性空间任一分量 `|C−W| < DEGENERATE_MIN_LIN`＝0.02，
     或**纸锚点不可得**——非印泥集为空）⇒ `skipped(degenerate)`（`skip_reason="degenerate"`）。
     **不得静默**，界值单点可改。
  6. **跳过兜底**：`ink_ratio < threshold`（默认 2%）⇒ 不校正，逐行标记 `skipped(ink_ratio=<值>)`。
  7. 目标色 **`#C95021` ＝ rgb(201,80,33)**（锚点②，**唯一常量、单点可改**）；白色锚点 `#FFFFFF`。

### V1b（**可选口径，不取代默认**）：仅做「纸 → 纯白」的白平衡
`whitebalance_gains_for` / `apply_gains_color` / `correct_image_whitebalance` —— **不咬印泥靶色**：
  1. 纸锚点 `W` 同第 3 条（**非印泥 ∧ `V ≥ p90`**）。
  2. 逐通道增益 **`k = white_lin / W_lin`**（线性 RGB、0–255 标度）⇒ **整图对角施加** `out_lin = k ⊙ in_lin`。
  3. **限幅** `k ∈ [0.5, 3]`（`WB_K_MIN` / `WB_K_MAX`）；`k > 3` ⇒ `skipped(limiting)`。
     **几何事实（如实登记）**：`W_lin255 ≤ 255`（纸不可能比纯白更亮）⇒ **`k ≥ 1` 恒成立**，
     故 `k_min=0.5` 在本口径下**天然不生效**。
  4. **跳过口径同形**：`skipped(ink_ratio=…)` / `skipped(degenerate)`（纸锚点不可得或线性任一分量 < 0.02）/ `skipped(limiting)`。
  5. **代价**：核心质心 → `#C95021` 的 ΔE 在本口径下**通常不为 0**（这正是 A/B 的看点：温和 vs 咬靶）；
     换来的是纸区白平衡 + 更小的「变冷」幅度（读数见 `ops/image-colorcal/`）。

### V3（**默认口径**）：双色分层处理（Kevin 2026-10-11；口径件 §2.3）
`v3_buckets` / `apply_foreground_chroma` / `flatten_paper` / `correct_image_v3` —— 分**三桶**：
  1. `ink`＝印泥（**前景 / 核心**）；`paper`＝**浅色**非印泥（`非印泥 ∧ V=max/255 ≥ V3_LIGHTNESS_V_MIN=0.70`，**背景**）；
     `other`＝**深色**非印泥（**黑墨 / 边款 / 墨拓 / 污渍**）；三桶互斥穷尽。
  2. **前景高保真**：只把 `ink` 像素的**色度**（Lab `a*`/`b*`）向 `#C95021` 靠拢，**保留 `L*`（明度结构 / 纹理 / 边缘）**；
     色度按靶色相取到**该 `L*` 的 sRGB 上限**（逐像素二分，**保 L\* ⇒ 不越域、不裁剪**）；含**保形兜底**（守 IoU≈1）。
  3. **背景压平**：`paper` 桶阈值化 → **`#FFFFFF`**（可选抬亮曲线 / 3×3 开运算 / 中值去噪；**清理只作用 `paper` 桶**）。
  4. **`other` 桶逐像素不变**（Kevin 已裁：黑墨 / 边款 / 墨拓 / 污渍都不动）。
  5. **跳过口径**：`ink_ratio < 2%` ⇒ `skipped(ink_ratio=…)`（V3 无仿射 ⇒ 不产生 `limiting`/`degenerate`）。
  6. **V1a（`correct_image` 双锚点仿射）/ V1b（纸白平衡）仍保留**（备选 / 对照，**未删**）。

### 判据口径（务必区分）
* `centroid_core_*`（**核心质心**，**与锚点同定义**）：CA-1 判据——「印泥核心质心→目标色」，预期 ΔE≈0。
* `centroid_all_*`（掩膜**全体**质心）：**仅观察项**。纸→纯白使全图变冷，全体质心**会变差**，
  **不得**拿它当判据（实测 9.2 → 20.6）。

### 为什么是「线性 RGB、0–255 标度」的 a / b
「线性 RGB 中解、sRGB 往返」指像素变换走 `sRGB → 线性 → 仿射 → 线性 → sRGB`（**gamma 正确**）。
系数在同一线性域上给出：把线性分量按 0–255 标度表达（`in_lin255 = 255·srgb_to_linear(in/255)`），
则 `a = (T − 255)/(C − W)`、`b = 255 − a·W` 逐字成立，且 `b` 天然落在 `[−255, 255]`——
这是「限幅 `b ∈ [−255, 255]`」有意义的唯一标度（若用 0–1 线性域，`b` 恒 ∈ [−1, 1]，界形同虚设）。

### 为什么写成「可被两侧 import」
本仓解释器矩阵（`feicui.spec.md` §6.5）：worker 侧 `feicui/venv` 有 numpy/PIL/cv2；
接口层 `server/.venv` **只有 PIL、没有 numpy**。故本模块：

* 顶部 **numpy 为可选依赖**（`try/except`）—— 缺 numpy 时模块仍可被 `server/.venv` import，
  只是**像素函数**（掩膜 / 质心 / 纸区 / `apply_affine` / `apply_correction` / `correct_image`）
  被调用时抛 `RuntimeError`；**纯算术函数**（`delta_e2000` / `affine_for` / `gains_for` /
  `apply_affine_color` / 色彩空间换算 / 常量）用 `math` 实现、**零 numpy 依赖**，两侧都能跑。
* **不含 skimage / cv2 依赖**（CIEDE2000 为手写实现）。
* 只依赖 **numpy（可选）＋ 标准库**。

### 兼容：旧的「对角增益」路径
V1 的单条全局对角增益 `out_linear = k ⊙ in_linear`（`k = target / C`，clamp 到 `[0.5, 2.0]`）
**保留为兼容函数**（`gains_for` / `apply_correction` / `correct_image_diagonal`），
但**不再作默认路径**——实测对角增益**数学上无法**同时满足「印泥→`#C95021`」与「纸保中性」
（`ops/image-colorcal/` 有对照读数）。默认路径＝ `correct_image`（**双锚点仿射**）。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # 可选依赖：接口层 server/.venv 无 numpy（§6.5）
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - 仅接口层命中
    np = None  # type: ignore

__all__ = [
    # 常量
    "TARGET_RGB", "TARGET_HEX", "WHITE_RGB", "K_MIN", "K_MAX", "INK_RATIO_MIN",
    "A_MIN", "A_MAX", "B_MIN", "B_MAX", "WB_K_MIN", "WB_K_MAX",
    "PAPER_QUANTILE", "INK_CORE_SAT_QUANTILE", "DEGENERATE_MIN_LIN",
    # 色彩空间 / 色差
    "hex_to_rgb", "rgb_to_hex", "rgb_to_hsv", "srgb_to_linear", "linear_to_srgb",
    "srgb_to_xyz", "xyz_to_lab", "srgb_to_lab", "lab_to_state", "ciede2000_lab", "delta_e2000",
    # 像素面（需 numpy）
    "ink_mask", "ink_centroid", "ink_core_centroid", "paper_mask", "paper_centroid",
    "region_mean_rgb",
    # 校正主体（V2 双锚点仿射）
    "affine_for", "apply_affine", "apply_affine_color", "correct_image",
    "skip_marker", "skip_marker_degenerate", "skip_marker_limiting",
    # V1b（可选口径：纸→纯白白平衡）
    "whitebalance_gains_for", "apply_gains_color", "correct_image_whitebalance",
    # V3（**默认口径**：双色分层处理）
    "V3_LIGHTNESS_V_MIN", "V3_FG_CHROMA_STRENGTH", "V3_PAPER_MODE", "V3_CLEAN",
    "V3_CLEAN_K", "V3_FG_IOU_MIN", "V3_LSTAR_MEAN_TOL", "V3_LSTAR_P90_TOL", "V3_OTHER_DE_TOL",
    "V3_FG_PRESERVE_MASK",
    "v3_buckets", "apply_foreground_chroma", "flatten_paper", "v3_open3x3", "v3_median3x3",
    "correct_image_v3",
    # 兼容（V1 对角增益）
    "gains_for", "apply_correction", "correct_image_diagonal",
]

# --------------------------------------------------------------------------------------
# 常量（§2.2「唯一常量、单点可改」）
# --------------------------------------------------------------------------------------
TARGET_RGB: Tuple[int, int, int] = (201, 80, 33)      # #C95021 印泥目标色（锚点②）
WHITE_RGB: Tuple[int, int, int] = (255, 255, 255)     # #FFFFFF 纸区目标色（锚点①）
TARGET_HEX: str = "#C95021"

# 仿射限幅（**线性 RGB、0–255 标度**；界值单点可改）
A_MIN: float = 0.0        # 增益下限（负增益＝反相，判越界 ⇒ 退化跳过）
A_MAX: float = 3.0        # 增益上限
B_MIN: float = -255.0     # 偏移下限（0–255 线性标度）
B_MAX: float = 255.0      # 偏移上限

# 锚点定义（分位）
PAPER_QUANTILE: float = 0.90          # 纸区：亮度 V 最高的 10% 像素均值 → #FFFFFF
INK_CORE_SAT_QUANTILE: float = 0.75   # 印泥核心：掩膜内饱和度 S ≥ p75 的像素均值 → #C95021
# 病态判定：线性空间（0–1）任一分量 `|C−W|` 低于此值 ⇒ skipped(degenerate)
DEGENERATE_MIN_LIN: float = 0.02

# 兼容（V1 对角增益）常量
K_MIN: float = 0.5      # 通道增益下限（旧路径 §2.2.3）
K_MAX: float = 2.0      # 通道增益上限
INK_RATIO_MIN: float = 0.02   # 印泥占比跳过阈值（§2.2.4，待裁 R-c）

# V1b（可选口径：纸→纯白白平衡）限幅 —— 单点可改
WB_K_MIN: float = 0.5   # 增益下限（**几何上不生效**：W_lin255 ≤ 255 ⇒ k ≥ 1）
WB_K_MAX: float = 3.0   # 增益上限（越界 ⇒ skipped(limiting)）

# V3（**默认口径**：双色分层处理）—— 单点可改
V3_LIGHTNESS_V_MIN: float = 0.70      # ★ 浅 / 深分界阀值：非印泥 ∧ V(=max/255) ≥ 此值 ⇒ paper 桶；否则 other 桶
V3_FG_CHROMA_STRENGTH: float = 1.0    # 前景色度向 #C95021 靠拢强度（0=不动；1=色度完全对齐靶色、L* 保留）
V3_PAPER_MODE: str = "threshold"      # 背景压平：'threshold'（阈值化→纯白）| 'curve'（抬亮曲线）
V3_CLEAN: bool = False                # 背景压平是否先做形态学清理（3×3 开运算）；**默认关** —— threshold 全压平下
                                      #   清理只会把**薄纸边**留在原色 ⇒ 反成背景残差（实测 p90 4.36/max 14.89）。
                                      #   `clean=True` 为**可选去噪**（曲线模式更有意义），能力已实现并自检。
V3_CLEAN_K: int = 3                   # 清理核尺寸（3×3）
V3_FG_PRESERVE_MASK: bool = True       # 前景保形兜底：越域边界缘像素若会掉出 ink 掩膜 ⇒ 保留原色（掩膜逐像素不变）
V3_FG_IOU_MIN: float = 0.98           # 前景掩膜前后 IoU 验收下限（§2.3.4）
V3_LSTAR_MEAN_TOL: float = 1.0        # 前景 L* 均值允许变化（验收）
V3_LSTAR_P90_TOL: float = 2.0         # 前景 L* p90 允许变化（验收）
V3_OTHER_DE_TOL: float = 1.0          # other 桶允许色差（**硬口径：应逐像素不变 ⇒ ΔE=0**）

# 印泥掩膜常量（§2.2.1）
_INK_RG_DOMINANCE: float = 15.0   # r > g + 15 且 r > b + 15
_INK_S_MIN: float = 0.25          # S > 0.25

# 分母数值零守卫（线性 0–255 标度上；`|C−W|` 过小另由病态判据兜底）
_DENOM_EPS: float = 1e-9

# 跳过标记
_SKIP_FMT = "skipped(ink_ratio={ratio:.6f})"
_SKIP_DEGENERATE = "skipped(degenerate)"
_SKIP_LIMITING = "skipped(limiting)"   # ★ v0.1 修订 4：独立标记（不再并入 degenerate）


# --------------------------------------------------------------------------------------
# 依赖守卫
# --------------------------------------------------------------------------------------
def _np():
    if np is None:  # pragma: no cover
        raise RuntimeError(
            "colorcal 的像素函数需要 numpy（worker 侧 feicui/venv 已装）；"
            "接口层 server/.venv 无 numpy（feicui.spec.md §6.5），该层只应 import 本模块的"
            "常量与纯算术函数（delta_e2000 / affine_for / gains_for / apply_affine_color / "
            "色彩空间换算）。"
        )
    return np


# --------------------------------------------------------------------------------------
# 基础色彩换算（纯算术，零 numpy）
# --------------------------------------------------------------------------------------
def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    """`#C95021` / `C95021` → `(201, 80, 33)`。"""
    s = str(h).strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"hex 需 6 位十六进制，收到 {h!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = (int(round(x)) for x in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_to_hsv(rgb: Sequence[float]) -> Tuple[float, float, float]:
    """0–255 的 RGB → `(h_deg ∈ [0,360), s ∈ [0,1], v ∈ [0,1])`（与 §1.2 口径一致）。"""
    r, g, b = (float(x) / 255.0 for x in rgb[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = 60.0 * (((g - b) / d) % 6.0)
    elif mx == g:
        h = 60.0 * (((b - r) / d) + 2.0)
    else:
        h = 60.0 * (((r - g) / d) + 4.0)
    s = 0.0 if mx == 0 else d / mx
    return (h % 360.0, s, mx)


def srgb_to_linear(x: float) -> float:
    """sRGB 分量（**0–1**）→ 线性 RGB（IEC 61966-2-1）。"""
    x = float(x)
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def linear_to_srgb(x: float) -> float:
    """线性 RGB（**0–1**）→ sRGB 分量。"""
    x = max(float(x), 0.0)
    return x * 12.92 if x <= 0.0031308 else 1.055 * (x ** (1.0 / 2.4)) - 0.055


def _srgb255_to_linear(v: float) -> float:
    """0–255 sRGB → 线性（**0–1**）。"""
    return srgb_to_linear(float(v) / 255.0)


def _srgb255_to_linear255(v: float) -> float:
    """0–255 sRGB → 线性（**0–255 标度**，仿射求解域）。"""
    return 255.0 * srgb_to_linear(float(v) / 255.0)


def srgb_to_xyz(rgb: Sequence[float], ) -> Tuple[float, float, float]:
    """0–255 sRGB → CIE XYZ（D65）。"""
    r = srgb_to_linear(float(rgb[0]) / 255.0)
    g = srgb_to_linear(float(rgb[1]) / 255.0)
    b = srgb_to_linear(float(rgb[2]) / 255.0)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return (x, y, z)


def xyz_to_lab(xyz: Sequence[float],
               white: Tuple[float, float, float] = (0.95047, 1.00000, 1.08883),
               ) -> Tuple[float, float, float]:
    """CIE XYZ → CIE L*a*b*（默认 D65 白点）。"""
    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
    fx = f(xyz[0] / white[0])
    fy = f(xyz[1] / white[1])
    fz = f(xyz[2] / white[2])
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def srgb_to_lab(rgb: Sequence[float]) -> Tuple[float, float, float]:
    """0–255 sRGB → CIE L*a*b*（D65）。"""
    return xyz_to_lab(srgb_to_xyz(rgb))


def lab_to_state(lab: Sequence[float]) -> Tuple[float, float, float, float, float]:
    """Lab → `(L, a, b, C=hypot(a,b), h_deg)`（CIEDE2000 中间量，供调试）。"""
    L, a, b = (float(x) for x in lab[:3])
    return (L, a, b, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0)


# --------------------------------------------------------------------------------------
# CIEDE2000（手写实现，零 skimage / cv2 / numpy）
# 实现依据：Sharma, Wu & Dalal (2005)《The CIEDE2000 Color-Difference Formula:
#           Implementation Notes, Supplementary Test Data, and Mathematical Observations》
# --------------------------------------------------------------------------------------
def ciede2000_lab(lab1: Sequence[float], lab2: Sequence[float],
                  kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> float:
    """CIEDE2000 色差（**输入即 Lab**；纯标量、纯 stdlib）。"""
    L1, a1, b1 = (float(x) for x in lab1[:3])
    L2, a2, b2 = (float(x) for x in lab2[:3])

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_bar = 0.5 * (C1 + C2)
    C_bar7 = C_bar ** 7
    G = 0.5 * (1.0 - math.sqrt(C_bar7 / (C_bar7 + 25.0 ** 7)))

    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0 if (a1p != 0.0 or b1 != 0.0) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0 if (a2p != 0.0 or b2 != 0.0) else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0.0:
        dhp = 0.0
    else:
        diff = h2p - h1p
        if abs(diff) <= 180.0:
            dhp = diff
        elif diff > 180.0:
            dhp = diff - 360.0
        else:
            dhp = diff + 360.0
    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    Lp_bar = 0.5 * (L1 + L2)
    Cp_bar = 0.5 * (C1p + C2p)

    if C1p * C2p == 0.0:
        hp_bar = h1p + h2p
    else:
        s = h1p + h2p
        if abs(h1p - h2p) <= 180.0:
            hp_bar = 0.5 * s
        elif s < 360.0:
            hp_bar = 0.5 * (s + 360.0)
        else:
            hp_bar = 0.5 * (s - 360.0)

    T = (1.0
         - 0.17 * math.cos(math.radians(hp_bar - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hp_bar))
         + 0.32 * math.cos(math.radians(3.0 * hp_bar + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hp_bar - 63.0)))
    d_theta = 30.0 * math.exp(-(((hp_bar - 275.0) / 25.0) ** 2))
    Cp_bar7 = Cp_bar ** 7
    RC = 2.0 * math.sqrt(Cp_bar7 / (Cp_bar7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lp_bar - 50.0) ** 2) / math.sqrt(20.0 + (Lp_bar - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cp_bar
    SH = 1.0 + 0.015 * Cp_bar * T
    RT = -math.sin(math.radians(2.0 * d_theta)) * RC

    tL = dLp / (kL * SL)
    tC = dCp / (kC * SC)
    tH = dHp / (kH * SH)
    return math.sqrt(tL * tL + tC * tC + tH * tH + RT * tC * tH)


def delta_e2000(rgb_a: Sequence[float], rgb_b: Sequence[float], **kw) -> float:
    """两色（**0–255 sRGB**）的 CIEDE2000 色差（内部先转 Lab 再调 `ciede2000_lab`）。"""
    return ciede2000_lab(srgb_to_lab(rgb_a), srgb_to_lab(rgb_b), **kw)


# --------------------------------------------------------------------------------------
# 像素面（需 numpy）
# --------------------------------------------------------------------------------------
def _as_rgb_array(rgb_array: Any):
    np_ = _np()
    arr = np_.asarray(rgb_array)
    if arr.ndim != 3 or arr.shape[-1] < 3:
        raise ValueError(f"期望 (H, W, 3+) 的影像数组，收到 shape={arr.shape}")
    return arr


def _sat_array(rgb):
    """逐像素饱和度 `S =(max−min)/max`（`max==0` ⇒ 0）。"""
    np_ = _np()
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    s = np_.zeros_like(mx, dtype=np_.float64)
    np_.divide(mx - mn, mx, out=s, where=mx > 0)
    return s


def ink_mask(rgb_array) -> Any:
    """印泥掩膜（§2.2.1）：`r > g+15` 且 `r > b+15` 且 `S > 0.25`，返回 `(H, W)` 布尔数组（**V2 未变**）。

    `S =(max−min)/max`；`max==0`（纯黑）时 `S` 记 0（不入选）。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    s = _sat_array(rgb)
    return (r > g + _INK_RG_DOMINANCE) & (r > b + _INK_RG_DOMINANCE) & (s > _INK_S_MIN)


def _mean_over_mask(arr, mask) -> Optional[Tuple[float, float, float]]:
    np_ = _np()
    n = int(mask.sum())
    if n == 0:
        return None
    px = arr[..., :3][mask].astype(np_.float64)
    c = px.mean(axis=0)
    return (float(c[0]), float(c[1]), float(c[2]))


def region_mean_rgb(rgb_array, mask) -> Optional[Tuple[float, float, float]]:
    """给定掩膜内的均值色（`(r,g,b)` 0–255）；掩膜为空返回 None。"""
    return _mean_over_mask(_as_rgb_array(rgb_array), mask)


def ink_centroid(rgb_array) -> Tuple[Optional[Tuple[float, float, float]], float]:
    """印泥**掩膜全体**质心 ＋ 印泥占比（§2.2.2）。

    返回 `(centroid_rgb, ink_ratio)`：无印泥像素时 `centroid_rgb is None`（`ratio=0.0`）。
    **注**：V2 的「主色调」锚点用 `ink_core_centroid`（核心质心），此全体质心仅作观察项。
    """
    arr = _as_rgb_array(rgb_array)
    mask = ink_mask(arr)
    total = int(arr.shape[0]) * int(arr.shape[1])
    ratio = (int(mask.sum()) / total) if total else 0.0
    return _mean_over_mask(arr, mask), ratio


def ink_core_centroid(rgb_array, sat_quantile: float = INK_CORE_SAT_QUANTILE) -> Dict[str, Any]:
    """**印泥核心质心（V2「主色调」锚点）**：掩膜内**饱和度 `S ≥ p75**` 的像素均值。

    返回 `{"rgb": (r,g,b), "linear255": (…), "pixels": n, "mask": ndarray,
    "sat_threshold": s, "all_pixels": n_all}`；掩膜为空时各值 `None` / 0。
    `mask` 为**核心**像素集合（供 `centroid_after` 在同一集合上量），不可序列化到 JSON。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    m = ink_mask(arr)
    n_all = int(m.sum())
    if n_all == 0:
        return {"rgb": None, "linear255": None, "pixels": 0, "mask": m,
                "sat_threshold": None, "all_pixels": 0}
    s = _sat_array(rgb)
    thr = float(np_.percentile(s[m], float(sat_quantile) * 100.0))
    core = m & (s >= thr)
    px = rgb[core]
    lin255 = 255.0 * _srgb_to_linear_arr(px / 255.0)
    return {
        "rgb": tuple(float(x) for x in px.mean(axis=0)),
        "linear255": tuple(float(x) for x in lin255.mean(axis=0)),
        "pixels": int(core.sum()),
        "mask": core,
        "sat_threshold": thr,
        "all_pixels": n_all,
    }


def paper_mask(rgb_array, v_min: float = 0.70):
    """纸区掩膜（**V1 兼容，仅供对照读数**）：`非印泥` 且 `V ≥ v_min`（`V = max/255`）。"""
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    mx = arr[..., :3].max(axis=2).astype(np_.float64)
    return (~ink_mask(arr)) & (mx >= v_min * 255.0)


def paper_centroid(rgb_array, quantile: float = PAPER_QUANTILE,
                   exclude_ink: bool = True) -> Dict[str, Any]:
    """**纸区质心（V2 / V1b 锚点①）**：纸集 → `#FFFFFF`。

    **★ v0.1 修订 3（采纳 Kong 实测）—— 默认先排除印泥像素**：纸集 ＝
    **非印泥 ∧ 亮度（`V = max(RGB)/255`）≥ p90(非印泥)** 的像素均值。
    p90 阈值在**非印泥集**上取（不是全图 p90）—— 高印泥占比的页上，全图 p90 会落到**淡印泥**上
    ⇒ 纸锚点 `W` 被拉近印泥质心 `C` ⇒ 两点定线病态、`a` 越界（实测 120 抽样 limiting `32.5% → 14.1%`、
    生效 `33 → 61`）。`exclude_ink=False` 只作**对照读数**（旧口径，仅供诊断）。

    返回 `{"rgb","linear255","pixels","v_threshold","mask","ink_excluded"}`；
    **非印泥集为空**（整图皆印泥）或纸集为空时 ⇒ `rgb=None` / `pixels=0` / `mask` 全 False
    （调用方据此判 `skipped(degenerate)`：纸锚点不可得）。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    v = rgb.max(axis=2) / 255.0
    sel = (~ink_mask(arr)) if exclude_ink else np_.ones(v.shape, dtype=bool)
    empty = {"rgb": None, "linear255": None, "pixels": 0, "v_threshold": None,
             "mask": np_.zeros(v.shape, dtype=bool), "ink_excluded": bool(exclude_ink)}
    if not bool(sel.any()):
        return empty
    thr = float(np_.percentile(v[sel], float(quantile) * 100.0))
    mask = sel & (v >= thr)
    if not bool(mask.any()):
        return empty
    px = rgb[mask]
    lin255 = 255.0 * _srgb_to_linear_arr(px / 255.0)
    return {
        "rgb": tuple(float(x) for x in px.mean(axis=0)),
        "linear255": tuple(float(x) for x in lin255.mean(axis=0)),
        "pixels": int(mask.sum()),
        "v_threshold": thr,
        "mask": mask,
        "ink_excluded": bool(exclude_ink),
    }


# --------------------------------------------------------------------------------------
# 数组版 sRGB ↔ 线性（被 apply_* 共用）
# --------------------------------------------------------------------------------------
def _srgb_to_linear_arr(c):
    np_ = _np()
    c = np_.clip(c, 0.0, None)
    return np_.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb_arr(c):
    np_ = _np()
    c = np_.clip(c, 0.0, None)
    return np_.where(c <= 0.0031308, c * 12.92, 1.055 * np_.power(c, 1.0 / 2.4) - 0.055)


# --------------------------------------------------------------------------------------
# V2 校正主体：双锚点仿射
# --------------------------------------------------------------------------------------
def affine_for(centroid: Sequence[float],
               paper: Sequence[float],
               target: Sequence[float] = TARGET_RGB,
               white: Sequence[float] = WHITE_RGB,
               a_min: float = A_MIN, a_max: float = A_MAX,
               b_min: float = B_MIN, b_max: float = B_MAX,
               degenerate_min_lin: float = DEGENERATE_MIN_LIN) -> Dict[str, Any]:
    """双锚点仿射系数（**逐通道 `out = a·in + b`，线性 RGB、0–255 标度**）。

    两点定线：
      * 锚点② 印泥核心质心 `centroid`(C) → `target`(T，默认 `#C95021`）；
      * 锚点① 纸区质心 `paper`(W) → `white`（默认 `#FFFFFF`）。
    ⇒ `a = (T − 255) / (C − W)`、`b = 255 − a·W`（线性 0–255 标度；`255` ＝ 白色锚点值）。

    返回 dict：
      * `a` / `b`             : 逐通道系数（tuple3；`b` 为 0–255 线性标度）
      * `raw_a` / `raw_b`     : clamp 前（越界时如实给出，可 ±inf / nan）
      * `clamped`             : 任一通道越界
      * `clamped_channels`    : 如 `["r","b"]`
      * `clamped_detail`      : 逐通道 raw→final ＋ 线性分量
      * `degenerate`          : 退化（病态 / 越界）
      * `degenerate_reason`   : `None` / `"degenerate"`（线性任一分量 `|C−W|` 过小）/ `"limiting"`（越界）
      * `dist_cw`             : `|C−W|`（0–255 RGB 欧氏）
      * `min_lin_component`   : `min_b |C_lin − W_lin|`（线性 0–1 标度）
      * `centroid_rgb` / `paper_rgb` / `target_rgb` / `white_rgb` : 输入回显
    """
    if centroid is None or paper is None or len(centroid) < 3 or len(paper) < 3:
        raise ValueError("centroid / paper 需为长度≥3 的 0–255 RGB")
    c = [float(x) for x in centroid[:3]]
    w = [float(x) for x in paper[:3]]
    t = [float(x) for x in target[:3]]
    wh = [float(x) for x in white[:3]]
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(c, w)))
    min_lin_component = min(abs(_srgb255_to_linear(x) - _srgb255_to_linear(y)) for x, y in zip(c, w))

    raw_a: List[float] = []
    raw_b: List[float] = []
    detail: List[Dict[str, Any]] = []
    denom_degen = False
    for ch, cv, wv, tv, whv in zip("rgb", c, w, t, wh):
        cl = _srgb255_to_linear255(cv)      # C（线性 0–255）
        wl = _srgb255_to_linear255(wv)      # W（线性 0–255）
        tl = _srgb255_to_linear255(tv)      # T（线性 0–255）
        whl = _srgb255_to_linear255(whv)    # 白（线性 0–255；#FFFFFF ⇒ 255）
        denom = cl - wl
        if abs(denom) < _DENOM_EPS:
            denom_degen = True
            ar = math.inf
            br = math.nan
        else:
            ar = (tl - whl) / denom         # a = (T − 255)/(C − W)
            br = whl - ar * wl              # b = 255 − a·W
        raw_a.append(ar)
        raw_b.append(br)
        detail.append({"channel": ch, "w_lin255": wl, "c_lin255": cl, "t_lin255": tl,
                       "raw_a": (None if math.isinf(ar) else ar),
                       "raw_b": (None if math.isnan(br) else br)})

    a_final: List[float] = []
    b_final: List[float] = []
    clamped_channels: List[str] = []
    for ch, ar, br in zip("rgb", raw_a, raw_b):
        af = ar if not math.isfinite(ar) else min(max(ar, a_min), a_max)
        bf = br if not math.isfinite(br) else min(max(br, b_min), b_max)
        a_final.append(af)
        b_final.append(bf)
        if (not math.isfinite(ar)) or af != ar:
            clamped_channels.append(ch)
        elif (not math.isfinite(br)) or bf != br:
            clamped_channels.append(ch)
    clamped = bool(clamped_channels)

    # 退化 / 越界判定（病态优先：线性任一分量 |C−W| 过小）
    if denom_degen or min_lin_component < degenerate_min_lin:
        degenerate, reason = True, "degenerate"
    elif clamped:
        degenerate, reason = True, "limiting"
    else:
        degenerate, reason = False, None

    return {
        "a": tuple(a_final),
        "b": tuple(b_final),
        "raw_a": tuple(raw_a),
        "raw_b": tuple(raw_b),
        "clamped": clamped,
        "clamped_channels": clamped_channels,
        "clamped_detail": detail,
        "degenerate": degenerate,
        "degenerate_reason": reason,
        "dist_cw": dist,
        "min_lin_component": min_lin_component,
        "centroid_rgb": tuple(c),
        "paper_rgb": tuple(w),
        "target_rgb": tuple(int(round(x)) for x in t),
        "white_rgb": tuple(int(round(x)) for x in wh),
        "a_min": float(a_min), "a_max": float(a_max),
        "b_min": float(b_min), "b_max": float(b_max),
        "degenerate_min_lin": float(degenerate_min_lin),
    }


def _coerce_affine(affine: Any) -> Tuple[List[float], List[float]]:
    if isinstance(affine, dict):
        a = affine.get("a")
        b = affine.get("b")
        if a is None or b is None:
            raise ValueError("affine dict 缺 'a' / 'b' 键")
    else:
        seq = list(affine)
        if len(seq) != 2:
            raise ValueError("affine 需为 (a, b) 二元组或 affine_for(...) 的 dict")
        a, b = seq
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if len(a) != 3 or len(b) != 3:
        raise ValueError(f"a / b 需各 3 个通道，收到 len(a)={len(a)} len(b)={len(b)}")
    return a, b


def apply_affine(rgb_array, affine) -> Any:
    """整图施加双锚点仿射（**线性 0–255 标度**、sRGB 往返）：`out_lin255 = a·in_lin255 + b`。

    `affine` 可为 `affine_for(...)` 的返回 dict，或 `(a, b)`（各 3 元）。同 shape / dtype。
    """
    np_ = _np()
    a, b = _coerce_affine(affine)
    arr = _as_rgb_array(rgb_array)
    orig_dtype = arr.dtype
    rgb = arr[..., :3].astype(np_.float64)
    lin255 = 255.0 * _srgb_to_linear_arr(rgb / 255.0)
    out_lin255 = lin255 * np_.asarray(a, dtype=np_.float64) + np_.asarray(b, dtype=np_.float64)
    out = _linear_to_srgb_arr(np_.clip(out_lin255, 0.0, 255.0) / 255.0) * 255.0
    out = np_.clip(out, 0.0, 255.0)
    if np_.issubdtype(orig_dtype, np_.integer):
        out = np_.rint(out).astype(orig_dtype)
    else:
        out = out.astype(orig_dtype)
    result = arr.copy()
    result[..., :3] = out
    return result


def apply_affine_color(rgb: Sequence[float], affine: Any) -> Tuple[float, float, float]:
    """标量版：把单个 0–255 sRGB 色过一遍双锚点仿射（**纯 math，无 numpy**）。

    用于「中灰 180 校正后色」等观察项。
    """
    a, b = _coerce_affine(affine)
    out = [
        255.0 * linear_to_srgb(
            min(max(_srgb255_to_linear255(float(v)) * av + bv, 0.0), 255.0) / 255.0
        )
        for v, av, bv in zip([float(x) for x in rgb[:3]], a, b)
    ]
    return (min(max(out[0], 0.0), 255.0),
            min(max(out[1], 0.0), 255.0),
            min(max(out[2], 0.0), 255.0))


def skip_marker(ink_ratio: float) -> str:
    """`skipped(ink_ratio=<值>)` 标记串（§2.2.4 / CA-5）。"""
    return _SKIP_FMT.format(ratio=float(ink_ratio))


def skip_marker_degenerate() -> str:
    """`skipped(degenerate)` 标记串（病态 / 纸锚点不可得，**不得静默**）。"""
    return _SKIP_DEGENERATE


def skip_marker_limiting() -> str:
    """`skipped(limiting)` 标记串（**★ v0.1 修订 4：越界独立成标记**，不再并入 `degenerate`）。"""
    return _SKIP_LIMITING


def apply_gains_color(rgb: Sequence[float], gains: Any) -> Tuple[float, float, float]:
    """标量版：把单个 0–255 sRGB 色过一遍**对角增益**（**纯 math，无 numpy**）。

    `out_lin255 = k · in_lin255`（线性 RGB、0–255 标度）。用于「灰瓦 90/128/180/220 校正后色」
    一类观察项（V1b / V1 兼容路径共用）。
    """
    k = _coerce_gains(gains)
    out = [
        255.0 * linear_to_srgb(
            min(max(_srgb255_to_linear255(float(v)) * kv, 0.0), 255.0) / 255.0
        )
        for v, kv in zip([float(x) for x in rgb[:3]], k)
    ]
    return (min(max(out[0], 0.0), 255.0),
            min(max(out[1], 0.0), 255.0),
            min(max(out[2], 0.0), 255.0))


# --------------------------------------------------------------------------------------
# 单图校正（V2 默认路径：双锚点仿射）
# --------------------------------------------------------------------------------------
def correct_image(rgb_array,
                  target: Sequence[float] = TARGET_RGB,
                  white: Sequence[float] = WHITE_RGB,
                  ink_ratio_min: float = INK_RATIO_MIN,
                  a_min: float = A_MIN, a_max: float = A_MAX,
                  b_min: float = B_MIN, b_max: float = B_MAX,
                  paper_quantile: float = PAPER_QUANTILE,
                  core_sat_quantile: float = INK_CORE_SAT_QUANTILE,
                  degenerate_min_lin: float = DEGENERATE_MIN_LIN,
                  paper_exclude_ink: bool = True,
                  ) -> Tuple[Any, Dict[str, Any]]:
    """单图校正（**V2 双锚点仿射**）→ `(校正后图, 报告 dict)`。

    `paper_exclude_ink=True`（默认）＝纸锚点集合为「**非印泥 ∧ `V ≥ p90`**」（★ v0.1 修订 3）；
    `False` 只作**对照读数**（旧口径）。

    报告键（逐行可落 `images_manifest.jsonl` 的 `color_correction` 面）：
      * `mode`          : `"applied"` / `"skipped"`
      * `marker`        : `"applied"` / `skipped(ink_ratio=<值>)` / `skipped(degenerate)` / `skipped(limiting)`
      * `skip_reason`   : `None` / `"ink_ratio"` / `"degenerate"` / `"limiting"`
      * `ink_ratio`     : 印泥占比（**校正前掩膜**）
      * `centroid_core_before` / `centroid_core_after` : **核心质心**前后（**判据**；`after` 在
        **同一核心像素集合**上算，**不重算掩膜** ⇒ 无 clip 时恰＝target）
      * `centroid_all_before` / `centroid_all_after` : 掩膜**全体**质心（**观察项**，勿当判据）
      * `delta_e_before` / `delta_e_after` : **核心质心**→target 的 CIEDE2000（前 / 后）
      * `ink_ratio_after` : 校正后**重算掩膜**的占比（观察项）
      * `a` / `b` / `raw_a` / `raw_b` / `clamped` / `clamped_channels` / `min_lin_component`
      * `paper_before_rgb` / `paper_after_rgb` / `paper_pixels` / `paper_ink_excluded`
      * `paper_delta_e_before` / `paper_delta_e_after` : 纸区质心→**white** 的 CIEDE2000（锚点①判据）
      * `paper_hue_before` / `paper_hue_after` / `paper_hue_shift` : 纸区色相漂移读数（观察项）
      * `gray180_after` : 中灰 (180,180,180) 校正后色（观察项；量化「整体变冷」）
    """
    arr = _as_rgb_array(rgb_array)
    total = int(arr.shape[0]) * int(arr.shape[1]) or 1
    m_all = ink_mask(arr)
    ratio = int(m_all.sum()) / total

    core = ink_core_centroid(arr, core_sat_quantile)
    c_core = core["rgb"]
    c_all = _mean_over_mask(arr, m_all)

    paper = paper_centroid(arr, paper_quantile, exclude_ink=paper_exclude_ink)
    pmask = paper["mask"]
    paper_before = paper["rgb"] if paper["pixels"] else None

    report: Dict[str, Any] = {
        "algorithm": "affine-2anchor",
        "target_rgb": tuple(int(round(v)) for v in target[:3]),
        "target_hex": rgb_to_hex(target),
        "white_rgb": tuple(int(round(v)) for v in white[:3]),
        "ink_ratio": ratio,
        "core_pixels": core["pixels"],
        "core_sat_threshold": core["sat_threshold"],
        "centroid_core_before": c_core,
        "centroid_core_before_hsv": (rgb_to_hsv(c_core) if c_core else None),
        "delta_e_before": (delta_e2000(c_core, target) if c_core else None),
        "centroid_all_before": c_all,
        "delta_e_all_before": (delta_e2000(c_all, target) if c_all else None),
        "paper_pixels": int(pmask.sum()),
        "paper_v_threshold": paper["v_threshold"],
        "paper_ink_excluded": paper["ink_excluded"],
        "paper_before_rgb": paper_before,
        "paper_delta_e_before": (delta_e2000(paper_before, white) if paper_before else None),
        "paper_hue_before": (rgb_to_hsv(paper_before)[0] if paper_before else None),
        "a": None, "b": None, "raw_a": None, "raw_b": None,
        "clamped": False, "clamped_channels": [], "min_lin_component": None,
    }

    def _skip(reason: str, marker: str, **extra) -> Tuple[Any, Dict[str, Any]]:
        report.update({
            "mode": "skipped",
            "marker": marker,
            "skip_reason": reason,
            "centroid_core_after": c_core,
            "centroid_all_after": c_all,
            "ink_ratio_after": ratio,
            "delta_e_after": report["delta_e_before"],
            "delta_e_all_after": report["delta_e_all_before"],
            "paper_after_rgb": paper_before,
            "paper_delta_e_after": report["paper_delta_e_before"],
            "paper_hue_after": report["paper_hue_before"],
            "paper_hue_shift": (0.0 if paper_before else None),
            "gray180_after": (180.0, 180.0, 180.0),
        })
        report.update(extra)
        return arr.copy(), report

    if c_core is None or ratio < ink_ratio_min:
        return _skip("ink_ratio", skip_marker(ratio))
    if paper_before is None:
        # **纸锚点不可得**（非印泥集为空）⇒ 病态；**不得**与「低印泥占比」混为一谈
        return _skip("degenerate", skip_marker_degenerate(), paper_anchor_unavailable=True)

    aff = affine_for(c_core, paper_before, target=target, white=white,
                     a_min=a_min, a_max=a_max, b_min=b_min, b_max=b_max,
                     degenerate_min_lin=degenerate_min_lin)
    common = {
        "a": aff["a"], "b": aff["b"], "raw_a": aff["raw_a"], "raw_b": aff["raw_b"],
        "clamped": aff["clamped"], "clamped_channels": aff["clamped_channels"],
        "clamped_detail": aff["clamped_detail"], "dist_cw": aff["dist_cw"],
        "min_lin_component": aff["min_lin_component"],
        "paper_rgb": aff["paper_rgb"], "white_rgb": aff["white_rgb"],
        "target_rgb": aff["target_rgb"],
    }
    if aff["degenerate"]:
        reason = aff["degenerate_reason"]
        marker = skip_marker_limiting() if reason == "limiting" else skip_marker_degenerate()
        return _skip(reason, marker, **common)

    corrected = apply_affine(arr, aff)

    # 映射后质心：**同一像素集合**在纠正图上的均值
    c_core_after = _mean_over_mask(corrected, core["mask"])
    c_all_after = _mean_over_mask(corrected, m_all)
    # 重算掩膜（观察项）
    mask_after = ink_mask(corrected)
    ratio_after = int(mask_after.sum()) / total

    paper_after = _mean_over_mask(corrected, pmask)
    hue_b = rgb_to_hsv(paper_before)[0] if paper_before else None
    hue_a = rgb_to_hsv(paper_after)[0] if paper_after else None
    hue_shift = None
    if hue_b is not None and hue_a is not None:
        hue_shift = (hue_a - hue_b + 180.0) % 360.0 - 180.0  # 环绕到 [-180,180]

    report.update(common)
    report.update({
        "mode": "applied",
        "marker": "applied",
        "skip_reason": None,
        "centroid_core_after": c_core_after,
        "centroid_core_after_hsv": (rgb_to_hsv(c_core_after) if c_core_after else None),
        "delta_e_after": (delta_e2000(c_core_after, target) if c_core_after else None),
        "centroid_all_after": c_all_after,
        "delta_e_all_after": (delta_e2000(c_all_after, target) if c_all_after else None),
        "ink_ratio_after": ratio_after,
        "paper_after_rgb": paper_after,
        "paper_delta_e_after": (delta_e2000(paper_after, white) if paper_after else None),
        "paper_hue_after": hue_a,
        "paper_hue_shift": hue_shift,
        "gray180_after": apply_affine_color((180, 180, 180), aff),
    })
    return corrected, report


# --------------------------------------------------------------------------------------
# V1b（**可选口径，不取代默认**）：仅做「纸 → 纯白」的白平衡
# --------------------------------------------------------------------------------------
def whitebalance_gains_for(paper: Sequence[float],
                           white: Sequence[float] = WHITE_RGB,
                           k_min: float = WB_K_MIN,
                           k_max: float = WB_K_MAX,
                           degenerate_min_lin: float = DEGENERATE_MIN_LIN) -> Dict[str, Any]:
    """【V1b】逐通道增益 `k = white_lin / W_lin`（线性 RGB、**0–255 标度**、白点 `#FFFFFF`）。

    **不咬印泥靶色**：只把纸区质心 `W` 白平衡到 `white`。整图**对角**施加 `out_lin255 = k·in_lin255`。

    返回 dict：
      * `gains` / `raw_gains`  : 逐通道增益（clamp 前 / 后；`raw` 分母为零时记 `None`）
      * `clamped` / `clamped_channels` / `clamped_detail` : 越界（`k ∉ [k_min, k_max]`）
      * `degenerate` / `degenerate_reason` : `None` / `"degenerate"`（`W` 线性 0–1 任一分量 < 阈值 ⇒ 纸近黑）/ `"limiting"`
      * `min_lin_component`    : `min W_lin(0–1)`
      * `space` / `paper_rgb` / `white_rgb` / `k_min` / `k_max`

    **几何事实（如实登记）**：`W_lin255 ≤ 255`（纸不可能比纯白更亮）⇒ **`k ≥ 1` 恒成立**，
    故 `k_min` 在本口径下**天然不生效**，只有 `k > k_max` 会触发 `skipped(limiting)`。
    """
    if paper is None or len(paper) < 3:
        raise ValueError("paper 需为长度≥3 的 0–255 RGB")
    w = [float(x) for x in paper[:3]]
    wh = [float(x) for x in white[:3]]

    min_lin_component = min(_srgb255_to_linear(v) for v in w)  # 线性 0–1
    raw: List[float] = []
    detail: List[Dict[str, Any]] = []
    for ch, wv, whv in zip("rgb", w, wh):
        wl = _srgb255_to_linear255(wv)       # W（线性 0–255）
        whl = _srgb255_to_linear255(whv)     # 白（线性 0–255；#FFFFFF ⇒ 255）
        raw_k = (whl / wl) if wl > _DENOM_EPS else math.inf
        raw.append(raw_k)
        detail.append({"channel": ch, "w_lin255": wl, "white_lin255": whl,
                       "raw_k": (None if math.isinf(raw_k) else raw_k)})

    gains: List[float] = []
    clamped_channels: List[str] = []
    for ch, rk, d in zip("rgb", raw, detail):
        gk = rk if not math.isfinite(rk) else min(max(rk, k_min), k_max)
        gains.append(gk)
        d["final"] = gk
        if (not math.isfinite(rk)) or gk != rk:
            clamped_channels.append(ch)
    clamped = bool(clamped_channels)

    if min_lin_component < degenerate_min_lin:
        degenerate, reason = True, "degenerate"
    elif clamped:
        degenerate, reason = True, "limiting"
    else:
        degenerate, reason = False, None

    return {
        "gains": tuple(gains),
        "raw_gains": tuple((None if math.isinf(k) else k) for k in raw),
        "clamped": clamped,
        "clamped_channels": clamped_channels,
        "clamped_detail": detail,
        "degenerate": degenerate,
        "degenerate_reason": reason,
        "min_lin_component": min_lin_component,
        "paper_rgb": tuple(w),
        "white_rgb": tuple(int(round(x)) for x in wh),
        "k_min": float(k_min), "k_max": float(k_max),
        "degenerate_min_lin": float(degenerate_min_lin),
        "space": "linear-rgb-255",
    }


def correct_image_whitebalance(rgb_array,
                               white: Sequence[float] = WHITE_RGB,
                               target: Sequence[float] = TARGET_RGB,
                               ink_ratio_min: float = INK_RATIO_MIN,
                               k_min: float = WB_K_MIN, k_max: float = WB_K_MAX,
                               paper_quantile: float = PAPER_QUANTILE,
                               degenerate_min_lin: float = DEGENERATE_MIN_LIN,
                               paper_exclude_ink: bool = True,
                               ) -> Tuple[Any, Dict[str, Any]]:
    """单图校正（**V1b 白平衡，可选口径**）→ `(校正后图, 报告 dict)`。**默认路径仍是 `correct_image`**。

    **只做纸 → 纯白的白平衡**：纸锚点 `W`（非印泥 ∧ `V ≥ p90`）→ `white`（`#FFFFFF`），
    逐通道对角增益 `k = white_lin / W_lin`，**不咬印泥靶色**。

    **跳过口径与默认路径同形**：`skipped(ink_ratio=…)` / `skipped(degenerate)` / `skipped(limiting)`；
    逐行可判、不得静默。

    报告**额外**保留 `centroid_core_*` → `target` 的 ΔE（**观察项**）：本口径下它**通常不为 0**，
    这正是「温和 V1b」与「咬靶默认路径」的直接对照读数。
    """
    arr = _as_rgb_array(rgb_array)
    total = int(arr.shape[0]) * int(arr.shape[1]) or 1
    m_all = ink_mask(arr)
    ratio = int(m_all.sum()) / total

    core = ink_core_centroid(arr)
    c_core = core["rgb"]
    c_all = _mean_over_mask(arr, m_all)

    paper = paper_centroid(arr, paper_quantile, exclude_ink=paper_exclude_ink)
    pmask = paper["mask"]
    paper_before = paper["rgb"] if paper["pixels"] else None

    report: Dict[str, Any] = {
        "algorithm": "whitebalance-diagonal",
        "target_rgb": tuple(int(round(v)) for v in target[:3]),
        "target_hex": rgb_to_hex(target),
        "target_role": "observation-only（本口径不咬靶色）",
        "white_rgb": tuple(int(round(v)) for v in white[:3]),
        "ink_ratio": ratio,
        "core_pixels": core["pixels"],
        "core_sat_threshold": core["sat_threshold"],
        "centroid_core_before": c_core,
        "delta_e_before": (delta_e2000(c_core, target) if c_core else None),
        "centroid_all_before": c_all,
        "delta_e_all_before": (delta_e2000(c_all, target) if c_all else None),
        "paper_pixels": int(pmask.sum()),
        "paper_v_threshold": paper["v_threshold"],
        "paper_ink_excluded": paper["ink_excluded"],
        "paper_before_rgb": paper_before,
        "paper_delta_e_before": (delta_e2000(paper_before, white) if paper_before else None),
        "paper_hue_before": (rgb_to_hsv(paper_before)[0] if paper_before else None),
        "gains": None, "raw_gains": None, "clamped": False, "clamped_channels": [],
        "min_lin_component": None,
    }

    def _skip(reason: str, marker: str, **extra) -> Tuple[Any, Dict[str, Any]]:
        report.update({
            "mode": "skipped",
            "marker": marker,
            "skip_reason": reason,
            "centroid_core_after": c_core,
            "centroid_all_after": c_all,
            "ink_ratio_after": ratio,
            "delta_e_after": report["delta_e_before"],
            "delta_e_all_after": report["delta_e_all_before"],
            "paper_after_rgb": paper_before,
            "paper_delta_e_after": report["paper_delta_e_before"],
            "paper_hue_after": report["paper_hue_before"],
            "paper_hue_shift": (0.0 if paper_before else None),
            "gray180_after": (180.0, 180.0, 180.0),
        })
        report.update(extra)
        return arr.copy(), report

    if c_core is None or ratio < ink_ratio_min:
        return _skip("ink_ratio", skip_marker(ratio))
    if paper_before is None:
        return _skip("degenerate", skip_marker_degenerate(), paper_anchor_unavailable=True)

    g = whitebalance_gains_for(paper_before, white=white, k_min=k_min, k_max=k_max,
                               degenerate_min_lin=degenerate_min_lin)
    common = {
        "gains": g["gains"], "raw_gains": g["raw_gains"],
        "clamped": g["clamped"], "clamped_channels": g["clamped_channels"],
        "clamped_detail": g["clamped_detail"], "min_lin_component": g["min_lin_component"],
        "paper_rgb": g["paper_rgb"], "white_rgb": g["white_rgb"],
    }
    if g["degenerate"]:
        reason = g["degenerate_reason"]
        marker = skip_marker_limiting() if reason == "limiting" else skip_marker_degenerate()
        return _skip(reason, marker, **common)

    corrected = apply_correction(arr, g["gains"])
    c_core_after = _mean_over_mask(corrected, core["mask"])
    c_all_after = _mean_over_mask(corrected, m_all)
    mask_after = ink_mask(corrected)
    ratio_after = int(mask_after.sum()) / total
    paper_after = _mean_over_mask(corrected, pmask)
    hue_b = rgb_to_hsv(paper_before)[0] if paper_before else None
    hue_a = rgb_to_hsv(paper_after)[0] if paper_after else None
    hue_shift = None
    if hue_b is not None and hue_a is not None:
        hue_shift = (hue_a - hue_b + 180.0) % 360.0 - 180.0

    report.update(common)
    report.update({
        "mode": "applied",
        "marker": "applied",
        "skip_reason": None,
        "centroid_core_after": c_core_after,
        "delta_e_after": (delta_e2000(c_core_after, target) if c_core_after else None),
        "centroid_all_after": c_all_after,
        "delta_e_all_after": (delta_e2000(c_all_after, target) if c_all_after else None),
        "ink_ratio_after": ratio_after,
        "paper_after_rgb": paper_after,
        "paper_delta_e_after": (delta_e2000(paper_after, white) if paper_after else None),
        "paper_hue_after": hue_a,
        "paper_hue_shift": hue_shift,
        "gray180_after": apply_gains_color((180, 180, 180), g["gains"]),
    })
    return corrected, report


# --------------------------------------------------------------------------------------
# V3（**默认口径**）：双色分层处理 —— 前景高保真 / 背景压平 / 深色保留原样
#   口径真源：`docs/image-color-tiff-draft-v0.1.md` §2.3（Kevin 2026-10-11 新口径）。
#   ① 分层三桶；② 前景只改**色度**、保留 **L\***；③ 背景压平向 `#FFFFFF`；
#   ④ `other`（深色非印泥）桶**逐像素不变**（Kevin 已裁：黑墨 / 边款 / 墨拓 / 污渍都不动）。
# --------------------------------------------------------------------------------------
def v3_buckets(rgb_array, light_v_min: float = V3_LIGHTNESS_V_MIN) -> Dict[str, Any]:
    """V3 分层三桶（§2.3.1）：

    * `ink`   ＝ `ink_mask`（**前景 / 核心**，与既有掩膜同定义）；
    * `paper` ＝ **非印泥 ∧ 亮度 `V = max(RGB)/255 ≥ light_v_min`**（**浅色背景**，可失真）；
    * `other` ＝ **非印泥 ∧ `V < light_v_min`**（**深色非印泥**：黑墨 / 边款 / 阴影，默认保留原样）。

    `light_v_min` 即**浅 / 深分界阀值**（单点可改，默认 `V3_LIGHTNESS_V_MIN = 0.70`）。
    三桶**互斥且穷尽**整图（`ink` ∪ `paper` ∪ `other` ＝ 全图，两两不交）。

    返回 `{"ink","paper","other"}` 三个 `(H,W)` 布尔数组 ＋ `{"ink_ratio","paper_ratio",
    "other_ratio","light_v_min","total"}`。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    ink = ink_mask(arr)
    v = rgb.max(axis=2) / 255.0
    nonink = ~ink
    paper = nonink & (v >= light_v_min)
    other = nonink & (v < light_v_min)
    total = int(rgb.shape[0]) * int(rgb.shape[1]) or 1
    return {
        "ink": ink, "paper": paper, "other": other,
        "ink_ratio": int(ink.sum()) / total,
        "paper_ratio": int(paper.sum()) / total,
        "other_ratio": int(other.sum()) / total,
        "light_v_min": float(light_v_min), "total": total,
    }


# ---- Lab 数组换算（V3 前景只改色度需要 Lab 往返；纯 numpy）--------------------------------
_SRGB_TO_XYZ_M = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_D65_WHITE = (0.95047, 1.00000, 1.08883)
_LAB_EPS = 0.008856          # 与标量 xyz_to_lab 逐字一致
_LAB_KAPPA = 7.787
_LAB_OFF = 16.0 / 116.0


def _srgb_to_lab_arr(rgb255):
    """`(...,3)` 0–255 sRGB → `(...,3)` Lab（D65）；与标量 `srgb_to_lab` 同式（向量化）。"""
    np_ = _np()
    c = np_.clip(np_.asarray(rgb255, dtype=np_.float64) / 255.0, 0.0, None)
    lin = _srgb_to_linear_arr(c)
    xyz = lin @ np_.asarray(_SRGB_TO_XYZ_M, dtype=np_.float64).T
    xyz = xyz / np_.asarray(_D65_WHITE, dtype=np_.float64)
    f = np_.where(xyz > _LAB_EPS, np_.cbrt(np_.clip(xyz, 0.0, None)),
                  _LAB_KAPPA * xyz + _LAB_OFF)
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np_.stack([L, a, b], axis=-1)


def _lab_to_lin_arr(lab):
    """`(...,3)` Lab → `(...,3)` **线性 sRGB**（未裁剪；`_srgb_to_lab_arr` 的数值逆，同一矩阵求逆）。"""
    np_ = _np()
    lab = np_.asarray(lab, dtype=np_.float64)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0

    def _finv(u):
        u3 = u ** 3
        return np_.where(u3 > _LAB_EPS, u3, (u - _LAB_OFF) / _LAB_KAPPA)

    xyz = np_.stack([_finv(fx), _finv(fy), _finv(fz)], axis=-1) * np_.asarray(_D65_WHITE, dtype=np_.float64)
    m_inv = np_.linalg.inv(np_.asarray(_SRGB_TO_XYZ_M, dtype=np_.float64))
    return xyz @ m_inv.T


def _lab_to_srgb_arr(lab, return_clip: bool = False):
    """`(...,3)` Lab → `(...,3)` 0–255 sRGB。

    `return_clip=True` 时**额外**返回 `(...,3)` 布尔「线性分量越出 `[0,1]`（色域外）」掩膜。
    """
    np_ = _np()
    lin = _lab_to_lin_arr(lab)
    clip = (lin < -_GAMUT_EPS) | (lin > 1.0 + _GAMUT_EPS)
    out = np_.clip(_linear_to_srgb_arr(np_.clip(lin, 0.0, 1.0)) * 255.0, 0.0, 255.0)
    return (out, clip) if return_clip else out


_GAMUT_EPS = 1e-4


def _lab_in_gamut(L, a, b):
    """按分量判 `(L,a*,b*)` 是否落在 sRGB 色域内（线性分量 ∈ `[0,1]`，容差 `_GAMUT_EPS`）。"""
    np_ = _np()
    lin = _lab_to_lin_arr(np_.stack([L, a, b], axis=-1))
    return (lin.min(axis=-1) >= -_GAMUT_EPS) & (lin.max(axis=-1) <= 1.0 + _GAMUT_EPS)


# ---- 前景（高保真）：只改色度、保留 L* --------------------------------------------------
def apply_foreground_chroma(rgb_array, mask, target: Sequence[float] = TARGET_RGB,
                            strength: float = V3_FG_CHROMA_STRENGTH,
                            preserve_mask: bool = V3_FG_PRESERVE_MASK) -> Tuple[Any, Dict[str, Any]]:
    """把 `mask`（V3 的 `ink` 桶）像素的**色度**向 `target`（`#C95021`）靠拢，
    **保留 `L*`（明度结构 / 纹理 / 边缘）** ⇒ `(校正后图, 读数 dict)`。

    **实现选择（在 Lab 中，只改 `a*` / `b*`）—— 且做色域自适应**：
    设靶色 Lab ＝ `(t_L, t_a, t_b)`，靶色相 `h_t = atan2(t_b, t_a)`、靶色度 `C_t = hypot(t_a,t_b)`。
    对每个 `ink` 像素：`out_L* = in_L*`（**逐像素精确保留**）；色度取**靶色相**方向、并**裁剪到该 `L*`
    在 sRGB 内可达的最大色度**（`out_C = min(strength·C_t, C_max(L, h_t))`，`C_max` 用逐分量二分求）：
    即 `out_{a*,b*} = strength·out_C·(cos h_t, sin h_t) + (1−strength)·in_{a*,b*}`。

    * **为何「保 L*」必须配「色域自适应」**：`#C95021` 是**亮而高饱和**（`L*≈49.8`）的红；
      暗印泥（如 `L*≈26`）在 sRGB 内**根本装不下**该色度 ⇒ 若强行写入再裁剪，会**破坏 `L*`**
      （实测暗印泥簇裁剪率 56〜68%、`L*` 均值漂移 2〜3）。改按 `L*` 上限取色度后 **`L*` 逐像素零漂移**、
      且色度**尽量**贴近靶色 —— 正合 Kevin「高保真、保 L*、尽可能向 `#C95021` 靠拢」。
    * **为何选 Lab 而非 HSV**：判据要「保留 `L*` 分布」——Lab 的 `L*` 是感知明度、与色度正交，
      只写 `a*`/`b*` 时 `L*` 精确保留；HSV 的 `V` 只是最大通道，改 `H`/`S` 会连带改 `L*`。
    * `strength=1`（默认）：色度完全按靶色相取到色域上限；`strength<1`：与原始色度按比混合。
    * **保形兜底**（`preserve_mask=True`，默认）：色域边界处的**极亮淡缘像素**（`S` 恰在 0.25 附近）
      在靶色相下可达色度略低，可能跌破 `ink_mask` 阈值而**掉出前景掩膜**（实测真样本原始 IoU 0.95〜0.98）。
      为守 §2.3.4「前景掩膜前后 IoU ≈ 1」这些像素**保留原色** ⇒ **掩膜逐像素不变（IoU＝1.0）**；
      未兜底的原始 IoU 另记 `iou_raw`（如实读数，不掩盖）。

    **只改 `mask` 内像素**；`mask` 外**逐字节原样**（前景口径不得整体位移 / 重采样 / 模糊）。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    m = np_.asarray(mask, dtype=bool)
    tL, ta, tb = srgb_to_lab(target)
    h_t = math.atan2(tb, ta)
    c_t = math.hypot(ta, tb) * float(strength)     # 目标色度（strength 缩放）
    ca, cb = math.cos(h_t), math.sin(h_t)
    out = arr.copy()
    n = int(m.sum())
    info: Dict[str, Any] = {
        "masked_pixels": n, "gamut_clip_pixels": 0, "gamut_clip_rate": 0.0,
        "chroma_reduced_pixels": 0, "chroma_reduced_rate": 0.0,
        "mask_reverted_pixels": 0, "mask_reverted_rate": 0.0, "iou_raw": 1.0,
        "target_lab": (float(tL), float(ta), float(tb)),
        "target_hue_deg": math.degrees(h_t) % 360.0,
        "target_chroma": math.hypot(ta, tb),
        "strength": float(strength),
        "change": "chroma-only (target hue; chroma capped to sRGB gamut at each L*); L* preserved",
    }
    if n:
        rgb = arr[..., :3][m].astype(np_.float64)
        lab = _srgb_to_lab_arr(rgb)
        L = lab[..., 0]
        a_i = lab[..., 1]
        b_i = lab[..., 2]
        # 逐像素在「靶色相」方向二分该 L* 的可达最大色度（保 L* ⇒ 不越域、不裁剪）
        lo = np_.zeros_like(L)
        hi = np_.full_like(L, c_t)
        for _ in range(18):
            mid = (lo + hi) * 0.5
            ing = _lab_in_gamut(L, mid * ca, mid * cb)
            lo = np_.where(ing, mid, lo)
            hi = np_.where(ing, hi, mid)
        c_use = lo
        a_tgt = c_use * ca
        b_tgt = c_use * cb
        s = float(strength)
        a_o = s * a_tgt + (1.0 - s) * a_i
        b_o = s * b_tgt + (1.0 - s) * b_i
        new_rgb, clip = _lab_to_srgb_arr(np_.stack([L, a_o, b_o], axis=-1), return_clip=True)
        info["gamut_clip_pixels"] = int(clip.any(axis=-1).sum())
        info["gamut_clip_rate"] = info["gamut_clip_pixels"] / n
        info["chroma_reduced_pixels"] = int((c_use < c_t - 1e-6).sum())
        info["chroma_reduced_rate"] = info["chroma_reduced_pixels"] / n
        view = out[..., :3]
        view[m] = np_.clip(np_.rint(new_rgb), 0.0, 255.0).astype(view.dtype)
        # 保形兜底：未兜底的原始 IoU（非印泥像素未被改动 ⇒ 掩膜只会丢、不会增）
        ink_after = ink_mask(out)
        inter = int((m & ink_after).sum())
        info["iou_raw"] = (inter / n) if n else 1.0
        if preserve_mask:
            lost = m & ~ink_after
            info["mask_reverted_pixels"] = int(lost.sum())
            info["mask_reverted_rate"] = int(lost.sum()) / n
            if bool(lost.any()):
                view[lost] = arr[..., :3][lost]
    return out, info


# ---- 背景（可失真）：形态学清理 ＋ 压平向 #FFFFFF（**清理只作用于 paper 桶**）-------------
def _erode3x3(mask):
    """二值 3×3 腐蚀（**edge 复制填充**；边界不致被无谓啃掉）。纯 numpy。"""
    np_ = _np()
    m = np_.asarray(mask, dtype=bool)
    h, w = m.shape
    mp = np_.pad(m, 1, mode="edge")
    er = np_.ones_like(m)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            er &= mp[dy:dy + h, dx:dx + w]
    return er


def _dilate3x3(mask):
    """二值 3×3 膨胀（edge 复制填充）。纯 numpy。"""
    np_ = _np()
    m = np_.asarray(mask, dtype=bool)
    h, w = m.shape
    mp = np_.pad(m, 1, mode="edge")
    dl = np_.zeros_like(m)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            dl |= mp[dy:dy + h, dx:dx + w]
    return dl


def v3_open3x3(mask):
    """二值 3×3 **开运算**（先腐蚀后膨胀），纯 numpy。用于 `paper` 桶清理：

    只会**删去**孤立的纸点（纸纹噪点 / 椒盐），**绝不新增** —— 且与原始掩膜相与，
    严格保证 `结果 ⊆ 输入` ⇒ **清理永远不会把非纸像素变白**（不会污染 `other` / `ink` 桶）。
    """
    np_ = _np()
    m = np_.asarray(mask, dtype=bool)
    return _dilate3x3(_erode3x3(m)) & m


def v3_median3x3(rgb_array):
    """逐通道 3×3 **中值滤波**（纯 numpy，edge 复制填充）。**仅供背景（paper 桶）去噪**。"""
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    h, w = rgb.shape[0], rgb.shape[1]
    pad = np_.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    stack = np_.empty((9, h, w, 3), dtype=np_.float64)
    k = 0
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            stack[k] = pad[dy:dy + h, dx:dx + w]
            k += 1
    med = np_.median(stack, axis=0)
    out = arr.copy()
    out[..., :3] = np_.clip(np_.rint(med), 0.0, 255.0).astype(out[..., :3].dtype)
    return out


def flatten_paper(rgb_array, paper_mask, mode: str = V3_PAPER_MODE,
                  clean: bool = V3_CLEAN, white: Sequence[float] = WHITE_RGB
                  ) -> Tuple[Any, Dict[str, Any]]:
    """背景压平：把 `paper` 桶像素向 `#FFFFFF` 推平 → `(校正后图, 读数 dict)`。

    * `mode="threshold"`（**默认**）：`paper`（清理后）像素 `:= white`（**阈值化 → 纯白**，
      背景质心 → `#FFFFFF` 的 ΔE ＝ **0**）；
    * `mode="curve"`：先 3×3 中值去噪，再在**线性 RGB** 做抬亮曲线（把 `paper` 桶亮度 p95 映到 1.0）。

    `clean=True` 时先对 `paper` 掩膜做 3×3 **开运算**（`v3_open3x3`，保证 ⊆ 原掩膜）去掉孤立纸点。
    **默认 `clean=False`**（见常量注）：threshold 模式下纸桶是**薄边/碎屑**时，开运算会把它们整块删掉
    ⇒ 反而**留在原色、拉高背景残差**；故压平默认**全量** `paper` 桶，形态学清理为**可选项**。
    **清理与压平只写 `paper` 桶像素；`ink` / `other` 桶逐字节不变。**
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    pm = np_.asarray(paper_mask, dtype=bool)
    info: Dict[str, Any] = {"mode": mode, "raw_paper_pixels": int(pm.sum())}
    if clean:
        pm2 = v3_open3x3(pm)
        info["cleaned_removed"] = int(pm.sum()) - int(pm2.sum())
        info["clean"] = "open3x3"
        pm = pm2
    else:
        info["clean"] = "none"
    out = arr.copy()
    view = out[..., :3]
    if mode == "threshold":
        view[pm] = np_.asarray([int(round(x)) for x in white[:3]], dtype=view.dtype)
    elif mode == "curve":
        src = v3_median3x3(arr) if clean else arr
        rgb = src[..., :3].astype(np_.float64)
        v = rgb.max(axis=2) / 255.0
        ref = float(np_.percentile(v[pm], 95.0)) if bool(pm.any()) else 1.0
        gain = 1.0 / max(ref, 1e-3)
        lin = _srgb_to_linear_arr(rgb / 255.0) * gain
        outv = np_.clip(np_.rint(_linear_to_srgb_arr(np_.clip(lin, 0.0, 1.0)) * 255.0), 0.0, 255.0)
        view[pm] = outv.astype(view.dtype)[pm]
        info["curve_gain"] = gain
    else:
        raise ValueError(f"paper mode 只支持 'threshold' / 'curve'，收到 {mode!r}")
    info["flattened_pixels"] = int(pm.sum())
    return out, info


# ---- V3 单图校正（默认口径） -----------------------------------------------------------
def _lstar_stats(img, mask) -> Optional[Dict[str, float]]:
    np_ = _np()
    if not bool(np_.asarray(mask, dtype=bool).any()):
        return None
    px = img[..., :3][mask].astype(np_.float64)
    L = _srgb_to_lab_arr(px)[:, 0]
    return {"mean": float(L.mean()), "p10": float(np_.percentile(L, 10.0)),
            "p50": float(np_.percentile(L, 50.0)), "p90": float(np_.percentile(L, 90.0))}


def correct_image_v3(rgb_array,
                     target: Sequence[float] = TARGET_RGB,
                     white: Sequence[float] = WHITE_RGB,
                     ink_ratio_min: float = INK_RATIO_MIN,
                     light_v_min: float = V3_LIGHTNESS_V_MIN,
                     fg_strength: float = V3_FG_CHROMA_STRENGTH,
                     fg_preserve_mask: bool = V3_FG_PRESERVE_MASK,
                     paper_mode: str = V3_PAPER_MODE,
                     clean: bool = V3_CLEAN,
                     core_sat_quantile: float = INK_CORE_SAT_QUANTILE,
                     ) -> Tuple[Any, Dict[str, Any]]:
    """V3 单图校正（**双色分层处理，默认口径**）→ `(校正后图, 报告 dict)`。

    流程：① 分三桶 → ② 前景（`ink`）只改色度、保 `L*` → ③ 背景（`paper`）清理后压平向 `#FFFFFF`
    → ④ `other` 桶**逐像素不变**。

    **跳过口径**：`ink_ratio < ink_ratio_min`（默认 2%）⇒ `skipped(ink_ratio=<值>)`。
    （V3 **无仿射** ⇒ 不产生 `limiting`；`degenerate` 在 V1a 里指「两点定线病态」，
     V3 无此中间量，故**仅继承方法无关的 `ink_ratio` 跳过** —— 如实登记，不虚设。）

    报告键（可落 `images_manifest.jsonl` 的 `color_correction` 面）：
      * `algorithm`＝`"dual-layer-v3"`、`mode`（applied/skipped）、`marker`、`skip_reason`
      * `ink_ratio` / `paper_ratio` / `other_ratio`（三桶占比）
      * `centroid_core_before` / `_after` ＋ `delta_e_before` / `_after`（**核心质心 → `#C95021`**，判据）
      * `centroid_all_before` / `_after` ＋ ΔE（掩膜全体质心，**观察项**）
      * `paper_before_rgb` / `paper_after_rgb` ＋ `bg_delta_e_before` / `_after`（**背景 → `#FFFFFF`**，判据）
      * `iou`（前景掩膜前后 IoU，含**保形兜底**）＋ `iou_raw`（**未兜底**原始 IoU）＋ `iou_inter` / `iou_union`
      * `lstar_before` / `lstar_after`（均值 / p10 / p50 / p90）＋ `lstar_mean_delta` / `_p50_delta` / `_p90_delta`
      * `other_unchanged_rate`（`other` 桶逐像素不变率；**硬口径应 = 1.0**）
      * `fg_gamut_clip_rate`（前景越色域裁剪率）、`bg_flattened_pixels` / `bg_cleaned_removed`
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    bk = v3_buckets(arr, light_v_min)
    ink, paper, other = bk["ink"], bk["paper"], bk["other"]
    total = bk["total"]
    ratio = bk["ink_ratio"]

    core = ink_core_centroid(arr, core_sat_quantile)
    cmask = core["mask"]
    c_core_before = core["rgb"]
    c_all_before = _mean_over_mask(arr, ink)
    paper_before = _mean_over_mask(arr, paper)
    ls_before = _lstar_stats(arr, ink)

    report: Dict[str, Any] = {
        "algorithm": "dual-layer-v3",
        "target_rgb": tuple(int(round(v)) for v in target[:3]),
        "target_hex": rgb_to_hex(target),
        "white_rgb": tuple(int(round(v)) for v in white[:3]),
        "light_v_min": float(light_v_min),
        "fg_chroma_strength": float(fg_strength),
        "paper_mode": paper_mode, "clean": bool(clean),
        "ink_ratio": ratio, "paper_ratio": bk["paper_ratio"], "other_ratio": bk["other_ratio"],
        "core_pixels": core["pixels"], "paper_pixels": int(paper.sum()),
        "other_pixels": int(other.sum()),
        "centroid_core_before": c_core_before,
        "delta_e_before": (delta_e2000(c_core_before, target) if c_core_before else None),
        "centroid_all_before": c_all_before,
        "delta_e_all_before": (delta_e2000(c_all_before, target) if c_all_before else None),
        "paper_before_rgb": paper_before,
        "bg_delta_e_before": (delta_e2000(paper_before, white) if paper_before else None),
        "lstar_before": ls_before,
    }

    def _skip(reason: str, marker: str) -> Tuple[Any, Dict[str, Any]]:
        report.update({
            "mode": "skipped", "marker": marker, "skip_reason": reason,
            "centroid_core_after": c_core_before,
            "centroid_all_after": c_all_before,
            "delta_e_after": report["delta_e_before"],
            "delta_e_all_after": report["delta_e_all_before"],
            "ink_ratio_after": ratio,
            "paper_after_rgb": paper_before,
            "bg_delta_e_after": report["bg_delta_e_before"],
            "iou": 1.0, "iou_inter": None, "iou_union": None,
            "iou_raw": 1.0, "mask_reverted_pixels": 0, "mask_reverted_rate": 0.0,
            "lstar_after": ls_before, "lstar_mean_delta": 0.0,
            "lstar_p50_delta": 0.0, "lstar_p90_delta": 0.0,
            "other_unchanged_rate": 1.0,
            "fg_gamut_clip_rate": None, "fg_masked_pixels": 0,
            "bg_flattened_pixels": 0, "bg_cleaned_removed": None,
        })
        return arr.copy(), report

    if c_core_before is None or ratio < ink_ratio_min:
        return _skip("ink_ratio", skip_marker(ratio))

    out, fg = apply_foreground_chroma(arr, ink, target=target, strength=fg_strength,
                                      preserve_mask=fg_preserve_mask)
    out, bg = flatten_paper(out, paper, mode=paper_mode, clean=clean, white=white)

    c_core_after = _mean_over_mask(out, cmask)
    c_all_after = _mean_over_mask(out, ink)
    paper_after = _mean_over_mask(out, paper)
    ink_after = ink_mask(out)
    inter = int((ink & ink_after).sum())
    union = int((ink | ink_after).sum())
    iou = (inter / union) if union else 1.0
    ls_after = _lstar_stats(out, ink)
    if bool(other.any()):
        eq = np_.all(out[..., :3][other] == arr[..., :3][other], axis=-1)
        other_rate = float(eq.mean())
    else:
        other_rate = 1.0

    def _d(a, b, key):
        if a is None or b is None:
            return None
        return abs(a[key] - b[key])

    report.update({
        "mode": "applied", "marker": "applied", "skip_reason": None,
        "centroid_core_after": c_core_after,
        "delta_e_after": (delta_e2000(c_core_after, target) if c_core_after else None),
        "centroid_all_after": c_all_after,
        "delta_e_all_after": (delta_e2000(c_all_after, target) if c_all_after else None),
        "ink_ratio_after": int(ink_after.sum()) / total,
        "paper_after_rgb": paper_after,
        "bg_delta_e_after": (delta_e2000(paper_after, white) if paper_after else None),
        "iou": iou, "iou_inter": inter, "iou_union": union,
        "iou_raw": fg["iou_raw"], "mask_reverted_pixels": fg["mask_reverted_pixels"],
        "mask_reverted_rate": fg["mask_reverted_rate"],
        "lstar_after": ls_after,
        "lstar_mean_delta": _d(ls_after, ls_before, "mean"),
        "lstar_p50_delta": _d(ls_after, ls_before, "p50"),
        "lstar_p90_delta": _d(ls_after, ls_before, "p90"),
        "other_unchanged_rate": other_rate,
        "fg_gamut_clip_rate": fg["gamut_clip_rate"],
        "fg_masked_pixels": fg["masked_pixels"],
        "bg_flattened_pixels": bg["flattened_pixels"],
        "bg_cleaned_removed": bg.get("cleaned_removed"),
    })
    return out, report


# --------------------------------------------------------------------------------------
# 兼容（V1 对角增益）—— **不得再作默认路径**
# --------------------------------------------------------------------------------------
def gains_for(centroid: Sequence[float],
              target: Sequence[float] = TARGET_RGB,
              k_min: float = K_MIN,
              k_max: float = K_MAX,
              space: str = "linear-rgb") -> Dict[str, Any]:
    """【V1 兼容】算通道增益（§2.2.3）：`k = target / C`，**线性 RGB** 中算、clamp 到 `[k_min, k_max]`。

    **保留仅为兼容 / 对照**；V1 对角口径数学上无法同时满足「印泥→`#C95021`」与「纸保中性」，
    **默认路径已改为双锚点仿射**（`correct_image`）。
    """
    if space != "linear-rgb":
        raise ValueError(f"space 只支持 'linear-rgb'（口径 V1），收到 {space!r}")
    if centroid is None or len(centroid) < 3:
        raise ValueError("centroid 需为长度≥3 的 0–255 RGB")

    c_lin = [_srgb255_to_linear(v) for v in centroid[:3]]
    t_lin = [_srgb255_to_linear(v) for v in target[:3]]

    raw: List[float] = []
    for cl, tl in zip(c_lin, t_lin):
        raw.append(math.inf if cl <= 0.0 else tl / cl)

    gains: List[float] = []
    clamped_channels: List[str] = []
    detail: List[Dict[str, Any]] = []
    for ch, k in zip("rgb", raw):
        kc = min(max(k, k_min), k_max)
        gains.append(kc)
        if kc != k:
            clamped_channels.append(ch)
        detail.append({"channel": ch, "raw": (None if math.isinf(k) else k), "final": kc,
                       "clamped": kc != k})

    return {
        "gains": tuple(gains),
        "raw_gains": tuple((None if math.isinf(k) else k) for k in raw),
        "clamped": bool(clamped_channels),
        "clamped_channels": clamped_channels,
        "clamped_detail": detail,
        "centroid_rgb": tuple(float(v) for v in centroid[:3]),
        "target_rgb": tuple(int(round(v)) for v in target[:3]),
        "k_min": float(k_min),
        "k_max": float(k_max),
        "space": "linear-rgb",
    }


def _coerce_gains(gains: Any) -> List[float]:
    if isinstance(gains, dict):
        gains = gains.get("gains")
        if gains is None:
            raise ValueError("gains dict 缺 'gains' 键")
    seq = [float(x) for x in gains]
    if len(seq) != 3:
        raise ValueError(f"gains 需恰 3 个通道增益，收到 {len(seq)}")
    return seq


def apply_correction(rgb_array, gains) -> Any:
    """【V1 兼容】整图施加对角增益（§2.2.3）：线性 RGB 中逐通道乘增益，再回 sRGB。

    `gains` 可为 `gains_for(...)` 的返回 dict，或长度 3 的序列。返回与输入同 shape / dtype。
    **默认路径已改为双锚点仿射**（`apply_affine`）。
    """
    np_ = _np()
    k = _coerce_gains(gains)
    arr = _as_rgb_array(rgb_array)
    orig_dtype = arr.dtype
    rgb = arr[..., :3].astype(np_.float64)
    lin = _srgb_to_linear_arr(rgb / 255.0) * np_.asarray(k, dtype=np_.float64)
    out = _linear_to_srgb_arr(lin) * 255.0
    out = np_.clip(out, 0.0, 255.0)
    if np_.issubdtype(orig_dtype, np_.integer):
        out = np_.rint(out).astype(orig_dtype)
    else:
        out = out.astype(orig_dtype)
    result = arr.copy()
    result[..., :3] = out
    return result


def correct_image_diagonal(rgb_array,
                           target: Sequence[float] = TARGET_RGB,
                           ink_ratio_min: float = INK_RATIO_MIN,
                           k_min: float = K_MIN,
                           k_max: float = K_MAX,
                           ) -> Tuple[Any, Dict[str, Any]]:
    """【V1 兼容】单图校正（对角增益口径）→ `(校正后图, 报告 dict)`。

    报告的键与 V1 一致（`gains` / `raw_gains` / `clamped` / 前后质心 / ΔE / 纸区色相…）。
    纸区读数沿用 V1 的 `paper_mask`（非印泥且 `V≥0.70`）定义。**仅为对照 / 复现历史读数。**
    """
    arr = _as_rgb_array(rgb_array)
    mask = ink_mask(arr)
    total = int(arr.shape[0]) * int(arr.shape[1]) or 1
    ratio = int(mask.sum()) / total
    c_before = _mean_over_mask(arr, mask)

    report: Dict[str, Any] = {
        "algorithm": "diagonal-gain",
        "target_rgb": tuple(int(round(v)) for v in target[:3]),
        "target_hex": rgb_to_hex(target),
        "ink_ratio": ratio,
        "centroid_before": c_before,
        "centroid_before_hsv": (rgb_to_hsv(c_before) if c_before else None),
        "delta_e_before": (delta_e2000(c_before, target) if c_before else None),
        "clamped": False,
        "clamped_channels": [],
        "gains": None,
        "raw_gains": None,
    }

    pmask = paper_mask(arr)
    paper_before = _mean_over_mask(arr, pmask)

    if c_before is None or ratio < ink_ratio_min:
        report.update({
            "mode": "skipped",
            "skip_reason": "ink_ratio",
            "marker": skip_marker(ratio),
            "centroid_after": c_before,
            "ink_ratio_after": ratio,
            "delta_e_after": report["delta_e_before"],
            "paper_pixels": int(pmask.sum()),
            "paper_hue_before": (rgb_to_hsv(paper_before)[0] if paper_before else None),
            "paper_hue_after": (rgb_to_hsv(paper_before)[0] if paper_before else None),
            "paper_hue_shift": 0.0 if paper_before else None,
        })
        return arr.copy(), report

    g = gains_for(c_before, target=target, k_min=k_min, k_max=k_max)
    corrected = apply_correction(arr, g["gains"])

    c_after = _mean_over_mask(corrected, mask)
    mask_after = ink_mask(corrected)
    ratio_after = int(mask_after.sum()) / total

    paper_after = _mean_over_mask(corrected, pmask)
    hue_b = rgb_to_hsv(paper_before)[0] if paper_before else None
    hue_a = rgb_to_hsv(paper_after)[0] if paper_after else None
    hue_shift = None
    if hue_b is not None and hue_a is not None:
        d = (hue_a - hue_b + 180.0) % 360.0 - 180.0  # 环绕到 [-180,180]
        hue_shift = d

    report.update({
        "mode": "applied",
        "skip_reason": None,
        "marker": "applied",
        "clamped": g["clamped"],
        "clamped_channels": g["clamped_channels"],
        "clamped_detail": g["clamped_detail"],
        "gains": g["gains"],
        "raw_gains": g["raw_gains"],
        "centroid_after": c_after,
        "centroid_after_hsv": (rgb_to_hsv(c_after) if c_after else None),
        "ink_ratio_after": ratio_after,
        "delta_e_after": (delta_e2000(c_after, target) if c_after else None),
        "paper_pixels": int(pmask.sum()),
        "paper_before_rgb": paper_before,
        "paper_after_rgb": paper_after,
        "paper_hue_before": hue_b,
        "paper_hue_after": hue_a,
        "paper_hue_shift": hue_shift,
    })
    return corrected, report
