"""影像颜色校正 V2（**双锚点仿射**）—— **纯函数模块**（两侧共用唯一一份实现）。

口径真源：`feicui/docs/image-color-tiff-draft-v0.1.md`（§2.2 算法口径 / §4 验收候选）。
本模块是 **Kong 地基单**（先行）的产物：只提供纯函数 ＋ 常量，**不接入任何线、不读写文件 / DB**。

算法 V2（**双锚点仿射**，承 Zang / Kevin 2026-10-11 追加裁定）：
  1. **印泥掩膜** `ink_mask`：`r > g+15` 且 `r > b+15` 且 `S > 0.25`（`S =(max−min)/max`）。**未变**。
  2. **印泥锚点 `C`＝「主色调」＝核心质心**：掩膜内**饱和度 ≥ p75** 的像素均值（**非**掩膜全体均值——
     全体均值含大量淡边像素、离纸色太近 ⇒ 两点定线病态）。
  3. **纸区锚点 `W`**：**亮度（`V=max(RGB)/255`）≥ p90** 的像素均值。
  4. 两点定线，**每通道 `out = a·in + b`**（**线性 RGB 中解、sRGB 往返**）：
       锚点② `C` → **`#C95021`**（`TARGET_RGB`）；锚点① `W` → **`#FFFFFF`**（`WHITE_RGB`）。
       线性 0–255 标度上逐字成立：`a = (T − 255)/(C − W)`、`b = 255 − a·W`。
  5. **限幅** `a ∈ [A_MIN, A_MAX]`（默认 0 / 3）、`b ∈ [B_MIN, B_MAX]`（默认 −255 / 255）；
     **越界** ⇒ `skipped(degenerate)`（`skip_reason="limiting"`）；**病态**（线性空间任一分量
     `|C−W| < DEGENERATE_MIN_LIN`＝0.02）⇒ `skipped(degenerate)`（`skip_reason="degenerate"`）。
     **不得静默**，界值单点可改。
  6. **跳过兜底**：`ink_ratio < threshold`（默认 2%）⇒ 不校正，逐行标记 `skipped(ink_ratio=<值>)`。
  7. 目标色 **`#C95021` ＝ rgb(201,80,33)**（锚点②，**唯一常量、单点可改**）；白色锚点 `#FFFFFF`。

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
    "A_MIN", "A_MAX", "B_MIN", "B_MAX",
    "PAPER_QUANTILE", "INK_CORE_SAT_QUANTILE", "DEGENERATE_MIN_LIN",
    # 色彩空间 / 色差
    "hex_to_rgb", "rgb_to_hex", "rgb_to_hsv", "srgb_to_linear", "linear_to_srgb",
    "srgb_to_xyz", "xyz_to_lab", "srgb_to_lab", "lab_to_state", "ciede2000_lab", "delta_e2000",
    # 像素面（需 numpy）
    "ink_mask", "ink_centroid", "ink_core_centroid", "paper_mask", "paper_centroid",
    "region_mean_rgb",
    # 校正主体（V2 双锚点仿射）
    "affine_for", "apply_affine", "apply_affine_color", "correct_image",
    "skip_marker", "skip_marker_degenerate",
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

# 印泥掩膜常量（§2.2.1）
_INK_RG_DOMINANCE: float = 15.0   # r > g + 15 且 r > b + 15
_INK_S_MIN: float = 0.25          # S > 0.25

# 分母数值零守卫（线性 0–255 标度上；`|C−W|` 过小另由病态判据兜底）
_DENOM_EPS: float = 1e-9

# 跳过标记
_SKIP_FMT = "skipped(ink_ratio={ratio:.6f})"
_SKIP_DEGENERATE = "skipped(degenerate)"


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


def paper_centroid(rgb_array, quantile: float = PAPER_QUANTILE) -> Dict[str, Any]:
    """**纸区质心（V2 锚点①）**：**亮度（`V = max(RGB)/255`）≥ p90** 的像素均值 → `#FFFFFF`。

    返回 `{"rgb": (r,g,b), "linear255": (…), "pixels": n, "v_threshold": v, "mask": ndarray}`。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    rgb = arr[..., :3].astype(np_.float64)
    v = rgb.max(axis=2) / 255.0
    thr = float(np_.percentile(v, float(quantile) * 100.0))
    mask = v >= thr
    px = rgb[mask]
    lin255 = 255.0 * _srgb_to_linear_arr(px / 255.0)
    return {
        "rgb": tuple(float(x) for x in px.mean(axis=0)),
        "linear255": tuple(float(x) for x in lin255.mean(axis=0)),
        "pixels": int(mask.sum()),
        "v_threshold": thr,
        "mask": mask,
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
    """`skipped(degenerate)` 标记串（V2 病态 / 越界，**不得静默**）。"""
    return _SKIP_DEGENERATE


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
                  ) -> Tuple[Any, Dict[str, Any]]:
    """单图校正（**V2 双锚点仿射**）→ `(校正后图, 报告 dict)`。

    报告键（逐行可落 `images_manifest.jsonl` 的 `color_correction` 面）：
      * `mode`          : `"applied"` / `"skipped"`
      * `marker`        : `"applied"` / `skipped(ink_ratio=<值>)` / `skipped(degenerate)`
      * `skip_reason`   : `None` / `"ink_ratio"` / `"degenerate"` / `"limiting"`
      * `ink_ratio`     : 印泥占比（**校正前掩膜**）
      * `centroid_core_before` / `centroid_core_after` : **核心质心**前后（**判据**；`after` 在
        **同一核心像素集合**上算，**不重算掩膜** ⇒ 无 clip 时恰＝target）
      * `centroid_all_before` / `centroid_all_after` : 掩膜**全体**质心（**观察项**，勿当判据）
      * `delta_e_before` / `delta_e_after` : **核心质心**→target 的 CIEDE2000（前 / 后）
      * `ink_ratio_after` : 校正后**重算掩膜**的占比（观察项）
      * `a` / `b` / `raw_a` / `raw_b` / `clamped` / `clamped_channels` / `min_lin_component`
      * `paper_before_rgb` / `paper_after_rgb` / `paper_pixels`
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

    paper = paper_centroid(arr, paper_quantile)
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

    if c_core is None or ratio < ink_ratio_min or paper_before is None:
        return _skip("ink_ratio", skip_marker(ratio))

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
        return _skip(aff["degenerate_reason"], skip_marker_degenerate(), **common)

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
