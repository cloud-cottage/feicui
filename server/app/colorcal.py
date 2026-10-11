"""影像颜色校正 V1（印泥锚点白平衡）—— **纯函数模块**（两侧共用唯一一份实现）。

口径真源：`feicui/docs/image-color-tiff-draft-v0.1.md` **§2.2**（逐条照登）。
本模块是 **Kong 地基单**（先行）的产物：只提供纯函数 ＋ 常量，**不接入任何线、不读写文件 / DB**。

算法 V1（§2.2 逐条）：
  1. **印泥掩膜** `ink_mask`：`r > g+15` 且 `r > b+15` 且 `S > 0.25`（`S =(max−min)/max`）。
  2. **质心** `ink_centroid`：掩膜内像素均值（＝本件定义的「主色调」）＋ 印泥占比。
  3. **锚点映射** `gains_for`：通道增益 `k = target / C`（**线性 RGB** 中算、sRGB 往返），
     clamp `k ∈ [K_MIN, K_MAX]`（默认 0.5 / 2.0），整图施加同一变换（`apply_correction`）。
  4. **跳过兜底** `correct_image`：`ink_ratio < threshold`（默认 2%）⇒ **不校正**并逐行标记
     `skipped(ink_ratio=<值>)`（**不得静默**，承 AC-54 / CA-5 同一纪律）。
  5. 目标色 **`#C95021` ＝ rgb(201,80,33)**（`TARGET_RGB`，**唯一常量、单点可改**）。

### 为什么写成「可被两侧 import」
本仓解释器矩阵（`feicui.spec.md` §6.5）：worker 侧 `feicui/venv` 有 numpy/PIL/cv2；
接口层 `server/.venv` **只有 PIL、没有 numpy**。故本模块：

* 顶部 **numpy 为可选依赖**（`try/except`）—— 缺 numpy 时模块仍可被 `server/.venv` import，
  只是**像素函数**（`ink_mask` / `ink_centroid` / `apply_correction` / `correct_image` / `paper_mask`）
  被调用时抛 `RuntimeError`；**纯算术函数**（`delta_e2000` / `gains_for` / 色彩空间换算 / 常量）
  用 `math` 实现、**零 numpy 依赖**，两侧都能跑。
* **不含 skimage / cv2 依赖**（CIEDE2000 为手写实现）。
* 只依赖 **numpy（可选）＋ 标准库**。

### 「纸保中性」的准确含义（**须与 CA-2 一起读**）
§2.2.3 说「整图施加同一变换 ⇒ 纸保持中性（不被染色）」。本模块的实现是**单条全局对角增益**
（`out_linear = k ⊙ in_linear`，**无偏移项**）——即「同一变换」的字面义：不按区域分别染色。
**但**：对角增益只在 3 个 k 相等时才严格保白；实测本语料需压蓝/压绿 ⇒ k 不等 ⇒
近白（纸）会有可测的**色相漂移**（实测见 `ops/image-colorcal/`）。因此本模块**不宣称零漂移**，
而是把漂移**如实读数并回报**（`paper_mask` ＋ 报告里的纸质心/色相），供 CA-2 与 R 裁处断。
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
    "TARGET_RGB", "K_MIN", "K_MAX", "INK_RATIO_MIN",
    # 色彩空间 / 色差
    "hex_to_rgb", "rgb_to_hex", "rgb_to_hsv", "srgb_to_linear", "linear_to_srgb",
    "srgb_to_xyz", "xyz_to_lab", "srgb_to_lab", "lab_to_state", "ciede2000_lab", "delta_e2000",
    # 像素面（需 numpy）
    "ink_mask", "ink_centroid", "paper_mask", "region_mean_rgb",
    # 校正主体
    "gains_for", "apply_correction", "correct_image", "skip_marker",
]

# --------------------------------------------------------------------------------------
# 常量（§2.2.5「唯一常量、单点可改」）
# --------------------------------------------------------------------------------------
TARGET_RGB: Tuple[int, int, int] = (201, 80, 33)   # #C95021 印泥目标色
TARGET_HEX: str = "#C95021"

K_MIN: float = 0.5      # 通道增益下限（§2.2.3）
K_MAX: float = 2.0      # 通道增益上限
INK_RATIO_MIN: float = 0.02   # 印泥占比跳过阈值（§2.2.4，待裁 R-c）

# 印泥掩膜常量（§2.2.1）
_INK_RG_DOMINANCE: float = 15.0   # r > g + 15 且 r > b + 15
_INK_S_MIN: float = 0.25          # S > 0.25

# 跳过标记格式（§2.2.4：`skipped(ink_ratio=<值>)`）—— 值＝原始占比，单点可改
_SKIP_FMT = "skipped(ink_ratio={ratio:.6f})"


# --------------------------------------------------------------------------------------
# 依赖守卫
# --------------------------------------------------------------------------------------
def _np():
    if np is None:  # pragma: no cover
        raise RuntimeError(
            "colorcal 的像素函数需要 numpy（worker 侧 feicui/venv 已装）；"
            "接口层 server/.venv 无 numpy（feicui.spec.md §6.5），该层只应 import 本模块的"
            "常量与纯算术函数（delta_e2000 / gains_for / 色彩空间换算）。"
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
    return srgb_to_linear(float(v) / 255.0)


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


def ink_mask(rgb_array) -> Any:
    """印泥掩膜（§2.2.1）：`r > g+15` 且 `r > b+15` 且 `S > 0.25`，返回 `(H, W)` 布尔数组。

    `S =(max−min)/max`；`max==0`（纯黑）时 `S` 记 0（不入选）。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    r = arr[..., 0].astype(np_.float64)
    g = arr[..., 1].astype(np_.float64)
    b = arr[..., 2].astype(np_.float64)
    mx = np_.maximum(np_.maximum(r, g), b)
    mn = np_.minimum(np_.minimum(r, g), b)
    s = np_.zeros_like(mx)
    np_.divide(mx - mn, mx, out=s, where=mx > 0)
    return (r > g + _INK_RG_DOMINANCE) & (r > b + _INK_RG_DOMINANCE) & (s > _INK_S_MIN)


def _mean_over_mask(arr, mask) -> Optional[Tuple[float, float, float]]:
    np_ = _np()
    n = int(mask.sum())
    if n == 0:
        return None
    px = arr[..., :3][mask].astype(np_.float64)
    c = px.mean(axis=0)
    return (float(c[0]), float(c[1]), float(c[2]))


def ink_centroid(rgb_array) -> Tuple[Optional[Tuple[float, float, float]], float]:
    """印泥质心 ＋ 印泥占比（§2.2.2）。

    返回 `(centroid_rgb, ink_ratio)`：无印泥像素时 `centroid_rgb is None`（`ratio=0.0`）。
    """
    arr = _as_rgb_array(rgb_array)
    mask = ink_mask(arr)
    total = int(arr.shape[0]) * int(arr.shape[1])
    ratio = (int(mask.sum()) / total) if total else 0.0
    return _mean_over_mask(arr, mask), ratio


def paper_mask(rgb_array, v_min: float = 0.70):
    """纸区掩膜（**本模块自定，用于 CA-2 读数**）：`非印泥` 且 `V ≥ v_min`（`V = max/255`）。

    纸＝亮、低饱和的背景；用它取纸区均值色，量校正前后**色相漂移**（CA-2 / ②(c)）。
    """
    np_ = _np()
    arr = _as_rgb_array(rgb_array)
    mx = arr[..., :3].max(axis=2).astype(np_.float64)
    return (~ink_mask(arr)) & (mx >= v_min * 255.0)


def region_mean_rgb(rgb_array, mask) -> Optional[Tuple[float, float, float]]:
    """给定掩膜内的均值色（`(r,g,b)` 0–255）；掩膜为空返回 None。"""
    return _mean_over_mask(_as_rgb_array(rgb_array), mask)


# --------------------------------------------------------------------------------------
# 锚点映射 / 校正主体
# --------------------------------------------------------------------------------------
def gains_for(centroid: Sequence[float],
              target: Sequence[float] = TARGET_RGB,
              k_min: float = K_MIN,
              k_max: float = K_MAX,
              space: str = "linear-rgb") -> Dict[str, Any]:
    """算通道增益（§2.2.3）：`k = target / C`，**线性 RGB** 中算、clamp 到 `[k_min, k_max]`。

    参数
      centroid : 印泥质心（**0–255 sRGB**）
      target   : 目标色（0–255 sRGB；默认 `TARGET_RGB`）
      space    : 只支持 `"linear-rgb"`（口径唯一）
    返回 dict：`gains`(clamp 后 3 元组) / `raw_gains`(clamp 前，可能 ±inf) /
              `clamped`(bool 任一通道被 clamp) / `clamped_channels`(如 `["g","b"]`) /
              `clamped_detail`(逐通道 raw→final) / `centroid_rgb` / `target_rgb` / `k_min` / `k_max` / `space`。
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


def _srgb_to_linear_arr(c):
    np_ = _np()
    c = np_.clip(c, 0.0, None)
    return np_.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb_arr(c):
    np_ = _np()
    c = np_.clip(c, 0.0, None)
    return np_.where(c <= 0.0031308, c * 12.92, 1.055 * np_.power(c, 1.0 / 2.4) - 0.055)


def apply_correction(rgb_array, gains) -> Any:
    """整图施加同一变换（§2.2.3）：线性 RGB 中逐通道乘增益，再回 sRGB。

    `gains` 可为 `gains_for(...)` 的返回 dict，或长度 3 的序列。返回与输入同 shape / dtype。
    变换＝**单条全局对角增益**（无偏移项）——「纸保中性」的字面义（同一变换整图施加）。
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


def skip_marker(ink_ratio: float) -> str:
    """`skipped(ink_ratio=<值>)` 标记串（§2.2.4 / CA-5）。"""
    return _SKIP_FMT.format(ratio=float(ink_ratio))


def correct_image(rgb_array,
                  target: Sequence[float] = TARGET_RGB,
                  ink_ratio_min: float = INK_RATIO_MIN,
                  k_min: float = K_MIN,
                  k_max: float = K_MAX,
                  ) -> Tuple[Any, Dict[str, Any]]:
    """单图校正（§2.2 全流程）→ `(校正后图, 报告 dict)`。

    报告键（**逐行可落 `images_manifest.jsonl` 的 `color_correction` 面**）：
      * `mode`          : `"applied"` / `"skipped"`
      * `marker`        : `"applied"` 或 `skipped(ink_ratio=<值>)`
      * `ink_ratio`     : 印泥占比（校正前掩膜）
      * `centroid_before` / `centroid_after` : 前后质心（`centroid_after` ＝ **同一印泥像素集合**
        校色后的均值 ⇒ 无 clamp 时 **恰等于 target**；这正是「把印泥质心映射到目标色」的判据）
      * `ink_ratio_after` : 校正后**重算掩膜**的占比（观察项：校色可能把纸也推进印泥掩膜）
      * `delta_e_before` / `delta_e_after` : 质心→target 的 CIEDE2000（前 / 后）
      * `clamped` / `clamped_channels` / `gains` / `raw_gains`
      * `paper_hue_before` / `paper_hue_after` / `paper_hue_shift` : 纸区色相漂移读数（CA-2）
    """
    arr = _as_rgb_array(rgb_array)
    mask = ink_mask(arr)
    total = int(arr.shape[0]) * int(arr.shape[1]) or 1
    ratio = int(mask.sum()) / total
    c_before = _mean_over_mask(arr, mask)

    report: Dict[str, Any] = {
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

    # 纸区读数（掩膜取**原图**，前后共用同一像素集合）
    pmask = paper_mask(arr)
    paper_before = _mean_over_mask(arr, pmask)

    if c_before is None or ratio < ink_ratio_min:
        report.update({
            "mode": "skipped",
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

    # 映射后质心：**同一印泥像素集合**在纠正图上的均值（无 clamp ⇒ = target）
    c_after = _mean_over_mask(corrected, mask)
    # 重算掩膜（观察项）
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
