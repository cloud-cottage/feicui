"""印章成品画布 V0（**确定性算法原型** · Kong 单 · 2026-10-13）。

把 Kevin 给的**一段面向生成式图像模型的提示词**拆成**确定性图像处理算法**（可复现、不引任何生成模型）。
本模块是**纯函数 ＋ CLI**：不写 DB、不建 job、**只读输入影像**，产物只落到调用方指定的目录。

## 0. 提示词 → 算法特征拆解（逐条对应，验收见 §4）

| # | 提示词原意 | 确定性算法 | 本实现的常量 / 开关 |
| --- | --- | --- | --- |
| 1 | 印章本体**冻结**（红色印泥区、内部白色文字线条、轮廓、字法、形状） | 唯一允许的像素变化＝**几何重采样**：Lanczos 缩放，逐像素**不做任何颜色处理**；验收给出「成品印区内像素 vs 重采样结果」**逐像素相等** + 往返 SSIM/ΔE 读数 | `LANCZOS`（`lanczos`） |
| 2 | 背景替换为**白色宣纸底纹**（细弱纤维、柔和、不抢主体） | 程序化生成：**零均值低幅噪声**（细颗粒 ＋ **沿画布长轴拉伸**的纤维）＋ 微色偏，逐通道限幅到 `#FAFAF7`–`#FFFFFF`；**种子固定 ⇒ 逐像素可复现** | `BG_SEED_DEFAULT=20261013`、`BG_MIN_RGB`/`BG_MAX_RGB`/`BG_BASE_RGB`、`BG_GRAIN_SIGMA`/`BG_FIBER_SIGMA`/`BG_FIBER_STRETCH_*` |
| 3 | 光影：均匀柔和微距实拍 ⇒ 背景**亮度均匀化**，不得对印章做光影 | 背景**纯均匀**（无渐晕 / 无明暗过渡 / **无投影**）；印章区域内**无任何合成光影** | 无参数（刻意不做） |
| 4 | 印泥**微晕染**：只在红掩膜**最外缘 1–3 px 环带**、极低 alpha（≤8%）、取**该印自身印泥色均值**；**严禁进入掩膜内部** | `dilate(mask, band) & ~mask` 的**外侧**环带；alpha 由内向外线性衰减到 0；颜色＝该印 `ink_mask` 像素均值；**掩膜内 alpha≡0** | `HALO_BAND_PX=2`（1–3 合法）、`HALO_ALPHA_MAX=0.08` |
| 5 | 色彩校准（红色均匀度） | **默认不做**（与「冻结」冲突）——登记为**待裁**（若 Kevin 要，只可加极轻的 red 通道 gamma，会破冻结） | 无（`--red-gamma` 未实现，待裁） |
| 6 | 构图：画布最长边 **1200 px**、纵横比沿用原片；主体缩放至画布最长边 **62%** 居中 | `画布 = 1200 ×(1200·短/长)` 取整；主体最长边＝`round(0.62·1200)=744`，按原比例取整，居中（整数偏移） | `CANVAS_LONG_SIDE=1200`、`SUBJECT_LONG_SIDE_RATIO=0.62` |
| 7 | **「主体」的两种读法**（提示词歧义） | **A ＝印章本体紧致外接框内容**（掩膜闭合后的外接框；几何框内含框内白线）；**B ＝整幅原片**。两种都出 | `CALIBER_A`/`CALIBER_B` |

## 1. 分割：**复用既有掩膜**（不重写检测）

`colorcal.ink_mask`（**V2 口径未变**：`r>g+15 ∧ r>b+15 ∧ S>0.25`）→ **闭运算**（椭圆核，连通笔画）
→ **软边收编**（原始掩膜像素 ∩ 距闭合掩膜 ≤ `FRINGE_PX` 内 ⇒ 并入，收编照片上印面 1–2 px 软边，
使「掩膜外无印泥」判据不含软边假阳性）→ 取**紧致外接框**。**默认不做孔洞填充**
（`fill_holes=False`）：朱文（阳文）笔画间本无「本体」、白文（阴文）内部白线本就该透出新纸底；
孔洞面积 `hole_px` 一律**如实登记**，`fill_holes=True` 时改为实心（＝「框内容」的严格读法）。

## 2. 主体两种口径（A/B）在本实现里差在哪

| | A（印章本体） | B（整幅原片） |
| --- | --- | --- |
| 主体像素 | 闭合掩膜外接框**内容**（几何框；`alpha_mode="ink"` 时只把**印泥本体**贴到新纸，框内非印泥处由新纸底透过） | **整幅 O 件**（含照片纸边、扫描底色 —— 一整块不透明矩形） |
| alpha | `ink`＝掩膜（默认）／`rect`＝几何框（`--alpha rect` 可选） | 恒为矩形（不透明） |
| 用于 | 印蜕式成品（新纸底可见） | 「原片裱在宣纸上」式成品（照片纸底保留） |

两种口径的**画布尺寸、主体 62%、居中、晕染、背景纹理**算法**完全一致**，差异只在主体取谁。

## 3. 红线（本模块自身）

只读输入影像、不写 DB、不建 job、不删文件；**产物落点由调用方给**（本单＝`ops/seal-canvas/samples/`，
**绝不**写 `output/books/**`）。图像栈（numpy / Pillow / OpenCV）只在 **worker 侧 `feicui/venv`** 可用
（接口层 `server/.venv` 无 numpy），故 numpy / cv2 均**延迟导入**：缺栈时模块仍可 import，调用像素函数才报错。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # 可选依赖（接口层 server/.venv 无 numpy）
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

# ── 常量（**皆单点可改**）─────────────────────────────────────────────────────────────
CANVAS_LONG_SIDE = 1200          # ⑥ 画布最长边
SUBJECT_LONG_SIDE_RATIO = 0.62   # ⑥ 主体最长边 / 画布最长边

CLOSE_KERNEL_PX = 5              # 闭运算核（椭圆，奇数）
FRINGE_PX = 2                    # 软边收编半径（§1）

HALO_BAND_PX = 2                 # ④ 晕染环带宽度（1–3 px 合法）
HALO_ALPHA_MAX = 0.08            # ④ 晕染最大 alpha（≤8%）

BG_SEED_DEFAULT = 20261013       # ② 固定种子 ⇒ 逐像素可复现
BG_MIN_RGB = (250, 250, 247)     # #FAFAF7（色域下限）
BG_MAX_RGB = (255, 255, 255)     # #FFFFFF（色域上限）
BG_BASE_RGB = (252.5, 252.5, 250.5)  # 基色（落在色域内、略暖）
BG_GRAIN_SIGMA = 0.85            # 细颗粒幅度（0–255 标度）
BG_FIBER_SIGMA = 1.45            # 纤维幅度（0–255 标度）
BG_FIBER_STRETCH_LONG = 22.0     # 纤维沿**长轴**拉伸倍率（各向异性）
BG_FIBER_STRETCH_SHORT = 2.4     # 纤维沿**短轴**拉伸倍率
BG_CHROMA_SIGMA = 0.30           # 通道独立微色偏幅度

CALIBER_A = "A"
CALIBER_B = "B"
CALIBERS = (CALIBER_A, CALIBER_B)
ALPHA_MODE_INK = "ink"
ALPHA_MODE_RECT = "rect"
ALPHA_MODES = (ALPHA_MODE_INK, ALPHA_MODE_RECT)
HALO_POLICY_SEAL = "seal"        # 环带贴印章本体（默认；A/B 一致）
HALO_POLICY_PAPER = "paper"      # 环带只落在新宣纸纸底（B 时贴片内不加晕染）
HALO_POLICIES = (HALO_POLICY_SEAL, HALO_POLICY_PAPER)

RESAMPLE = "lanczos"
TIFF_TAG_PREDICTOR = 317
TIFF_PREDICTOR = 2               # 与 O 件同容器：TIFF RGB8 + Deflate + Predictor=2

__all__ = [
    # 常量
    "CANVAS_LONG_SIDE", "SUBJECT_LONG_SIDE_RATIO", "CLOSE_KERNEL_PX", "FRINGE_PX",
    "HALO_BAND_PX", "HALO_ALPHA_MAX", "BG_SEED_DEFAULT", "BG_MIN_RGB", "BG_MAX_RGB",
    "BG_BASE_RGB", "BG_GRAIN_SIGMA", "BG_FIBER_SIGMA", "BG_FIBER_STRETCH_LONG",
    "BG_FIBER_STRETCH_SHORT", "BG_CHROMA_SIGMA", "CALIBER_A", "CALIBER_B", "CALIBERS",
    "ALPHA_MODE_INK", "ALPHA_MODE_RECT", "ALPHA_MODES",
    "HALO_POLICY_SEAL", "HALO_POLICY_PAPER", "HALO_POLICIES", "TIFF_PREDICTOR",
    # 分割 / 背景 / 构图
    "ink_mask", "seal_mask", "bbox_of", "canvas_size", "subject_target_size",
    "paper_background", "resample_subject", "resize_mask_bool", "halo_layer",
    # 合成 / 读数
    "compose", "ssim", "delta_e76_mean", "sha256_array", "array_stats",
    # 批量 / CLI
    "write_tiff_lossless", "run_batch", "main",
]


def _np():
    if np is None:  # pragma: no cover - 仅接口层命中
        raise RuntimeError("seal_canvas 需要 numpy（worker 侧 feicui/venv）；接口层 server/.venv 无 numpy")
    return np


def _cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("seal_canvas 需要 OpenCV（worker 侧 feicui/venv）") from exc
    return cv2


def _pil():
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("seal_canvas 需要 Pillow（worker 侧 feicui/venv）") from exc
    return Image


def _lanczos():
    """Lanczos 重采样常量（Pillow ≥ 9.1 走 `Resampling.LANCZOS`，老版本回落 `Image.LANCZOS`）。"""
    Image = _pil()
    res = getattr(Image, "Resampling", None)
    if res is not None and hasattr(res, "LANCZOS"):
        return res.LANCZOS
    return Image.LANCZOS  # type: ignore[attr-defined]


# ── ① 分割（复用既有 ink_mask ＋ 闭运算）─────────────────────────────────────────────
def ink_mask(rgb) -> Any:
    """印泥掩膜 —— **直接委托 `server.app.colorcal.ink_mask`**（V2 口径未变，不重写检测）。"""
    from .colorcal import ink_mask as _ink_mask  # 同包内相对导入（模块内唯一一处跨模块依赖）
    return _ink_mask(rgb)


def bbox_of(mask) -> Optional[Tuple[int, int, int, int]]:
    """掩膜紧致外接框（`x0, y0, x1, y1`，**右/下开区间**）；空掩膜 ⇒ `None`。"""
    np_ = _np()
    m = np_.asarray(mask, dtype=bool)
    if not bool(m.any()):
        return None
    ys, xs = np_.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _fill_holes(mask) -> Any:
    """孔洞填充（1 px 假边框 + 背景泛洪 ⇒ 对贴边掩膜同样成立）。"""
    np_ = _np()
    cv2 = _cv2()
    m = np_.asarray(mask, dtype=bool)
    pad = np_.zeros((m.shape[0] + 2, m.shape[1] + 2), np_.uint8)
    pad[1:-1, 1:-1] = m.astype(np_.uint8)
    ff = pad.copy()
    flood_mask = np_.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np_.uint8)
    cv2.floodFill(ff, flood_mask, (0, 0), 1)
    holes = pad.astype(bool) & ~ff.astype(bool)
    filled = pad.astype(bool) | holes
    return filled[1:-1, 1:-1], holes[1:-1, 1:-1]


def seal_mask(rgb, *, close_px: int = CLOSE_KERNEL_PX, fringe_px: int = FRINGE_PX,
              fill_holes: bool = False) -> Dict[str, Any]:
    """印章掩膜分割：`ink_mask` → 闭运算 → （可选孔洞填充）→ 软边收编 → 外接框。

    返回 dict（**不落盘、不写库**）：
      * `raw`：`colorcal.ink_mask` 原始掩膜；
      * `closed`：闭运算（椭圆核 `close_px`）后的连通掩膜；
      * `holes` / `hole_px`：被闭合掩膜**围住**的孔洞（＝「框内白线」区域；如实登记，默认不填）；
      * `mask`：**操作掩膜** ＝（闭合 ∪ 孔洞〔`fill_holes=True` 时〕）∪ 距其 ≤ `fringe_px` 的原始印泥像素；
      * `bbox` / `size` / `ink_ratio` / `fringe_px_added` / `radius_effective_px`。
    """
    np_ = _np()
    cv2 = _cv2()
    arr = np_.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError(f"期望 (H, W, 3+) 的 RGB 数组，收到 shape={arr.shape}")
    raw = np_.asarray(ink_mask(arr), dtype=bool)
    n_raw = int(raw.sum())
    k = int(close_px) if int(close_px) % 2 == 1 else int(close_px) + 1
    k = max(1, k)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    closed = cv2.morphologyEx(raw.astype(np_.uint8), cv2.MORPH_CLOSE, se) > 0
    filled, holes = _fill_holes(closed)
    base = filled if fill_holes else closed
    if int(fringe_px) > 0:
        fk = 2 * int(fringe_px) + 1
        dil = cv2.dilate(base.astype(np_.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (fk, fk))) > 0
        mask = base | (raw & dil)
    else:
        mask = base
    fringe_added = int((mask & ~base & raw).sum())
    # 等效半径（用于「软边收编半径」读数）
    area0 = int(raw.sum())
    radius = float(np_.sqrt(area0 / np_.pi)) if area0 else 0.0
    return {
        "raw": raw, "closed": closed, "holes": holes, "mask": mask,
        "bbox": bbox_of(mask), "size": (int(arr.shape[1]), int(arr.shape[0])),
        "ink_ratio": (n_raw / float(arr.shape[0] * arr.shape[1])) if arr.size else 0.0,
        "hole_px": int(holes.sum()), "closed_px": int(closed.sum()), "mask_px": int(mask.sum()),
        "fringe_px_added": fringe_added, "close_kernel_px": k, "fringe_px": int(fringe_px),
        "fill_holes": bool(fill_holes), "radius_effective_px": round(radius, 2),
    }


# ── ⑥ 构图 ──────────────────────────────────────────────────────────────────────
def canvas_size(w: int, h: int, long_side: int = CANVAS_LONG_SIDE) -> Tuple[int, int]:
    """画布尺寸：最长边 ＝ `long_side`，**纵横比沿用原片**（短边四舍五入，下限 1）。"""
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        raise ValueError(f"非法原片尺寸 {w}x{h}")
    if w >= h:
        return int(long_side), max(1, int(round(long_side * h / w)))
    return max(1, int(round(long_side * w / h))), int(long_side)


def subject_target_size(crop_w: int, crop_h: int,
                        long_side: int = CANVAS_LONG_SIDE,
                        ratio: float = SUBJECT_LONG_SIDE_RATIO) -> Tuple[int, int]:
    """主体目标尺寸：**最长边 ＝ round(ratio·long_side)**，另一边按原比例取整（下限 1）。"""
    crop_w, crop_h = int(crop_w), int(crop_h)
    if crop_w <= 0 or crop_h <= 0:
        raise ValueError(f"非法主体尺寸 {crop_w}x{crop_h}")
    target_long = max(1, int(round(float(ratio) * int(long_side))))
    if crop_w >= crop_h:
        return target_long, max(1, int(round(target_long * crop_h / crop_w)))
    return max(1, int(round(target_long * crop_w / crop_h))), target_long


def _stretched_noise(rng, h: int, w: int, sx: float, sy: float) -> Any:
    """**各向异性**低幅噪声：低分辨率正态噪声 → 双三次放大（`sx`/`sy` ＝ 沿 x / y 的拉伸倍率）。"""
    np_ = _np()
    cv2 = _cv2()
    lh = max(2, int(round(h / max(1e-6, float(sy)))))
    lw = max(2, int(round(w / max(1e-6, float(sx)))))
    n = rng.standard_normal((lh, lw))
    return cv2.resize(n, (int(w), int(h)), interpolation=cv2.INTER_CUBIC)


def paper_background(w: int, h: int, seed: int = BG_SEED_DEFAULT) -> Any:
    """② 程序化**白色宣纸**底纹：均匀基色 ＋ 细颗粒 ＋ 沿长轴拉伸的纤维 ＋ 微色偏，逐通道限幅。

    口径：**零均值、低幅**（不留斑块）；**同种子逐像素可复现**（`numpy.default_rng(seed)`，
    生成顺序固定 ⇒ 逐字节稳定）；色域落 `BG_MIN_RGB`(#FAFAF7)–`BG_MAX_RGB`(#FFFFFF)。
    **无渐晕 / 无投影 / 无明暗过渡**（③ 背景亮度均匀化）。
    """
    np_ = _np()
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        raise ValueError(f"非法画布尺寸 {w}x{h}")
    rng = np_.random.default_rng(int(seed))
    long_is_x = w >= h
    if long_is_x:
        fiber = _stretched_noise(rng, h, w, BG_FIBER_STRETCH_LONG, BG_FIBER_STRETCH_SHORT)
    else:
        fiber = _stretched_noise(rng, h, w, BG_FIBER_STRETCH_SHORT, BG_FIBER_STRETCH_LONG)
    grain = rng.standard_normal((h, w))
    chroma = rng.standard_normal((h, w, 3))
    for field in (fiber, grain):
        s = float(field.std())
        field -= field.mean()
        if s > 0:
            field /= s
    lum = BG_FIBER_SIGMA * fiber + BG_GRAIN_SIGMA * grain
    base = np_.asarray(BG_BASE_RGB, dtype=np_.float64)
    lo = np_.asarray(BG_MIN_RGB, dtype=np_.float64)
    hi = np_.asarray(BG_MAX_RGB, dtype=np_.float64)
    out = base[None, None, :] + lum[:, :, None] + BG_CHROMA_SIGMA * chroma
    return np_.clip(out, lo[None, None, :], hi[None, None, :]).round().astype(np_.uint8)


# ── ① 重采样（唯一允许的像素变化）──────────────────────────────────────────────────
def resize_mask_bool(mask, size: Tuple[int, int]) -> Any:
    """掩膜重采样 → **二值**（Lanczos 后 ≥128 为 True）。

    二值是刻意的：任何软 alpha 都会在边缘产生「印泥 × 纸底」混色像素，使「掩膜外无印泥」
    与「印泥区＝纯重采样」两条判据同时失真。
    """
    np_ = _np()
    Image = _pil()
    size = (max(1, int(size[0])), max(1, int(size[1])))
    a = np_.asarray(mask, dtype=bool)
    up = np_.asarray(Image.fromarray((a.astype(np_.uint8) * 255)).resize(size, _lanczos()))
    return up >= 128


def resample_subject(crop, alpha, size: Tuple[int, int]) -> Tuple[Any, Any]:
    """**Lanczos** 重采样主体与 alpha（alpha 二值化 ⇒ 合成面**不产生混色边**）。"""
    np_ = _np()
    Image = _pil()
    size = (max(1, int(size[0])), max(1, int(size[1])))
    arr = np_.asarray(crop)
    sub = np_.asarray(Image.fromarray(arr.astype(np_.uint8)).resize(size, _lanczos()))
    return sub.astype(np_.uint8), resize_mask_bool(alpha, size)


# ── ④ 晕染 ──────────────────────────────────────────────────────────────────────
def halo_layer(mask, *, band_px: int = HALO_BAND_PX, alpha_max: float = HALO_ALPHA_MAX,
               ink_rgb: Optional[Sequence[float]] = None, allow: Optional[Any] = None) -> Dict[str, Any]:
    """④ 印泥微晕染层：**掩膜外侧** 1–`band_px` px 环带，alpha 由内向外线性衰减到 0。

    `allow`（可选 bool 数组）把环带**限制在**某些像素上——本单只用于 `halo_policy="paper"`：
    B 口径下贴片内是照片纸边，限制环带只落在**新宣纸纸底**上（`allow = ~paste_canvas`）。

    返回 `{"alpha": (H,W) float64, "band": bool, "dist_px": (H,W) int16, "inside_alpha_max": 0.0,
    "outside_alpha_max": 0.0, "alpha_band_max": …}`。**掩膜内 alpha 恒 0**（严禁进入掩膜内部），
    环带外 alpha 恒 0。`alpha_max` 上限 `HALO_ALPHA_MAX`（≤8%），颜色由调用方给（该印自身印泥色均值）。
    """
    np_ = _np()
    cv2 = _cv2()
    m = np_.asarray(mask, dtype=bool)
    band_px = int(max(1, min(3, int(band_px))))
    alpha_max = float(min(alpha_max, HALO_ALPHA_MAX))
    allow = None if allow is None else np_.asarray(allow, dtype=bool)
    alpha = np_.zeros(m.shape, dtype=np_.float64)
    dist = np_.zeros(m.shape, dtype=np_.int16)
    cur = m
    band = np_.zeros(m.shape, dtype=bool)
    for d in range(1, band_px + 1):
        dil = cv2.dilate(cur.astype(np_.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0
        ring = dil & ~m & ~band
        if allow is not None:
            ring = ring & allow
        band |= ring
        dist[ring] = d
        # d=1 最贴边 ⇒ 取满幅 alpha_max；向外线性衰减（d=band_px 时 ＝ alpha_max/band_px）
        alpha[ring] = alpha_max * (band_px - d + 1) / float(band_px)
        cur = dil
    if ink_rgb is None:
        alpha[:] = 0.0
        band[:] = False
    return {
        "alpha": alpha, "band": band, "dist_px": dist, "band_px": band_px,
        "allow": None if allow is None else int(allow.sum()),
        "alpha_max_cap": alpha_max,
        "alpha_band_max": float(alpha.max()) if alpha.size else 0.0,
        "inside_alpha_max": float(alpha[m].max()) if bool(m.any()) else 0.0,
        "outside_alpha_max": float(alpha[~band].max()) if alpha.size else 0.0,
        "band_px_count": int(band.sum()),
        "color_rgb": (None if ink_rgb is None else [round(float(c), 3) for c in ink_rgb]),
    }


# ── 读数（验收自证）───────────────────────────────────────────────────────────────
def sha256_array(arr) -> str:
    """数组字节流 sha256（**逐像素可复现**判据用；与容器/编码无关）。"""
    np_ = _np()
    a = np_.ascontiguousarray(np_.asarray(arr))
    return hashlib.sha256(a.tobytes()).hexdigest()


def array_stats(arr) -> Dict[str, Any]:
    """逐通道 min / max / mean / std ＋ 整体读数（背景色域自证用）。"""
    np_ = _np()
    a = np_.asarray(arr)
    flat = a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1, 1)
    return {
        "shape": list(a.shape),
        "min": [float(v) for v in flat.min(axis=0)],
        "max": [float(v) for v in flat.max(axis=0)],
        "mean": [round(float(v), 3) for v in flat.mean(axis=0)],
        "std": [round(float(v), 3) for v in flat.std(axis=0)],
    }


def ssim(a, b, *, sigma: float = 1.5, win: int = 11, data_range: float = 255.0) -> float:
    """SSIM（**手写实现**：Gaussian 窗，逐通道后取均值；不依赖 skimage）。"""
    np_ = _np()
    cv2 = _cv2()
    x = np_.asarray(a, dtype=np_.float64)
    y = np_.asarray(b, dtype=np_.float64)
    if x.shape != y.shape:
        raise ValueError(f"SSIM 形状不一致：{x.shape} vs {y.shape}")
    if x.ndim == 2:
        x = x[:, :, None]
        y = y[:, :, None]
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2
    k = (int(win), int(win))
    vals = []
    for c in range(x.shape[2]):
        xc, yc = x[:, :, c], y[:, :, c]
        mx = cv2.GaussianBlur(xc, k, sigma)
        my = cv2.GaussianBlur(yc, k, sigma)
        sxx = cv2.GaussianBlur(xc * xc, k, sigma) - mx * mx
        syy = cv2.GaussianBlur(yc * yc, k, sigma) - my * my
        sxy = cv2.GaussianBlur(xc * yc, k, sigma) - mx * my
        s = ((2 * mx * my + c1) * (2 * sxy + c2)) / ((mx * mx + my * my + c1) * (sxx + syy + c2))
        vals.append(float(s.mean()))
    return round(sum(vals) / max(1, len(vals)), 6)


def delta_e76_mean(a, b) -> float:
    """平均 ΔE76（CIELAB，`cv2.cvtColor(..., RGB2LAB)` on float32 0–1 ⇒ L 0–100 / a,b −128–127）。"""
    np_ = _np()
    cv2 = _cv2()
    x = np_.asarray(a, dtype=np_.float32) / 255.0
    y = np_.asarray(b, dtype=np_.float32) / 255.0
    lx = cv2.cvtColor(x, cv2.COLOR_RGB2LAB)
    ly = cv2.cvtColor(y, cv2.COLOR_RGB2LAB)
    d = np_.sqrt(((lx - ly) ** 2).sum(axis=2))
    return round(float(d.mean()), 4)


def _ink_mean_rgb(rgb, mask) -> Optional[Tuple[float, float, float]]:
    """该印**自身印泥色均值**（掩膜内逐通道均值；无印泥 ⇒ None）。"""
    np_ = _np()
    m = np_.asarray(mask, dtype=bool)
    if not bool(m.any()):
        return None
    px = np_.asarray(rgb)[..., :3][m].astype(np_.float64)
    c = px.mean(axis=0)
    return float(c[0]), float(c[1]), float(c[2])


# ── 合成主体 ──────────────────────────────────────────────────────────────────────
def compose(rgb, *, caliber: str = CALIBER_A, alpha_mode: str = ALPHA_MODE_INK,
            seed: int = BG_SEED_DEFAULT, canvas_long_side: int = CANVAS_LONG_SIDE,
            subject_ratio: float = SUBJECT_LONG_SIDE_RATIO, halo_band_px: int = HALO_BAND_PX,
            halo_alpha_max: float = HALO_ALPHA_MAX, close_px: int = CLOSE_KERNEL_PX,
            fringe_px: int = FRINGE_PX, fill_holes: bool = False,
            halo: bool = True, halo_policy: str = HALO_POLICY_SEAL) -> Dict[str, Any]:
    """**成品合成**（确定性：同输入同参数 ⇒ 逐像素相同）。

    流程：分割 → 取主体（A＝掩膜外接框 / B＝整幅）→ Lanczos 到 62% → 居中贴到宣纸画布
    → 掩膜外侧晕染 → 出读数。返回 dict：`canvas`（uint8 HxWx3）、`mask_canvas`、`halo`、`readings`、`meta`。
    """
    np_ = _np()
    if caliber not in CALIBERS:
        raise ValueError(f"caliber 只能是 {CALIBERS}，收到 {caliber!r}")
    if alpha_mode not in ALPHA_MODES:
        raise ValueError(f"alpha_mode 只能是 {ALPHA_MODES}，收到 {alpha_mode!r}")
    if halo_policy not in HALO_POLICIES:
        raise ValueError(f"halo_policy 只能是 {HALO_POLICIES}，收到 {halo_policy!r}")
    arr = np_.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError(f"期望 (H, W, 3+) 的 RGB 数组，收到 shape={arr.shape}")
    arr = arr[..., :3].astype(np_.uint8)
    src_h, src_w = int(arr.shape[0]), int(arr.shape[1])

    seg = seal_mask(arr, close_px=close_px, fringe_px=fringe_px, fill_holes=fill_holes)
    if seg["bbox"] is None:
        raise ValueError("掩膜为空（该 O 件无印泥像素）⇒ 不可成品化")
    ink_rgb = _ink_mean_rgb(arr, seg["raw"]) or _ink_mean_rgb(arr, seg["mask"])

    if caliber == CALIBER_A:
        x0, y0, x1, y1 = seg["bbox"]
        crop = arr[y0:y1, x0:x1]
        seal_src = seg["mask"][y0:y1, x0:x1]
    else:
        x0, y0, x1, y1 = 0, 0, src_w, src_h
        crop = arr
        seal_src = seg["mask"]

    # alpha_mode：ink ＝ 只贴印泥本体（默认）／rect ＝ 贴满几何框（**B 恒为整幅矩形**）
    if caliber == CALIBER_A and alpha_mode == ALPHA_MODE_INK:
        paste_src = seal_src
    else:
        paste_src = np_.ones(seal_src.shape, dtype=bool)
    crop_h, crop_w = int(crop.shape[0]), int(crop.shape[1])
    cw, ch = canvas_size(src_w, src_h, long_side=canvas_long_side)
    tw, th = subject_target_size(crop_w, crop_h, long_side=canvas_long_side, ratio=subject_ratio)
    sub, a_sub = resample_subject(crop, paste_src, (tw, th))
    seal_local = resize_mask_bool(seal_src, (tw, th))   # 真印章掩膜（画布尺度：② 判据用）
    ox, oy = (cw - tw) // 2, (ch - th) // 2

    bg = paper_background(cw, ch, seed)
    bg_again = paper_background(cw, ch, seed)          # ⑤ 同种子复算
    bg_reproducible = bool(np_.array_equal(bg, bg_again))

    canvas = bg.copy()
    region = canvas[oy:oy + th, ox:ox + tw]
    region[a_sub] = sub[a_sub]                          # ★ 只做几何重采样 ⇒ 本体像素=重采样结果
    paste_canvas = np_.zeros((ch, cw), dtype=bool)
    paste_canvas[oy:oy + th, ox:ox + tw] = a_sub
    seal_canvas = np_.zeros((ch, cw), dtype=bool)
    seal_canvas[oy:oy + th, ox:ox + tw] = seal_local
    mask_canvas = paste_canvas                          # 兼容旧键名

    # ④ 晕染**贴印章本体**（不是贴片矩形）。`halo_policy`：
    #   * "seal"（默认）＝ 环带贴印章本体，A/B 一致（B 时环带落在贴片内的照片纸边上 ⇒ 如实登记效果量）；
    #   * "paper"      ＝ 环带只落在**新宣纸纸底**上（`allow=~paste_canvas`）⇒ B 时贴片内不再加晕染。
    allow = (~paste_canvas) if halo_policy == HALO_POLICY_PAPER else None
    halo_out = halo_layer(seal_canvas, band_px=halo_band_px, alpha_max=halo_alpha_max,
                          ink_rgb=ink_rgb if halo else None, allow=allow)
    h_alpha = halo_out["alpha"]
    canvas_pre_halo = canvas
    if halo and ink_rgb is not None and float(h_alpha.max()) > 0:
        canvas_pre_halo = canvas.copy()
        col = np_.asarray(ink_rgb, dtype=np_.float64)[None, None, :]
        blended = canvas.astype(np_.float64) * (1.0 - h_alpha[:, :, None]) + col * h_alpha[:, :, None]
        canvas = np_.clip(blended, 0, 255).round().astype(np_.uint8)

    # ── 读数 ──────────────────────────────────────────────────────────────────
    def _maxdiff(sel_canvas, sel_sub):
        if not bool(sel_canvas.any()):
            return 0, 0
        a = canvas[sel_canvas].astype(np_.int16)
        b = sub[sel_sub].astype(np_.int16)
        return int(a.shape[0]), int(np_.abs(a - b).max())

    freeze_px, freeze_max_abs = _maxdiff(paste_canvas, a_sub)
    seal_px, seal_max_abs = _maxdiff(seal_canvas, seal_local)

    # 往返：主体（画布分辨率）→ 回主体原尺寸 ⇒ 与原片主体比 SSIM / ΔE（＝纯重采样损失读数）
    Image = _pil()
    back = np_.asarray(Image.fromarray(sub).resize((crop_w, crop_h), _lanczos()))
    ssim_rt = ssim(crop, back)
    de_rt = delta_e76_mean(crop, back)
    scale = (tw / float(crop_w)) if crop_w else 1.0

    ink_after = ink_mask(canvas)
    bg_region = ~paste_canvas & ~halo_out["band"]        # ＝新宣纸纸底（无贴片、无晕染环带）
    ink_in_background = int((ink_after & bg_region).sum())
    ink_outside_seal = int((ink_after & ~seal_canvas).sum())
    ink_outside_seal_nohalo = int((ink_after & ~seal_canvas & ~halo_out["band"]).sum())
    ink_in_halo_band = int((ink_after & halo_out["band"]).sum())

    readings = {
        "freeze": {
            "claim": "印泥本体像素与原片的差异＝**仅几何重采样**（零色彩处理）",
            "resample": RESAMPLE,
            "paste_px": freeze_px,
            "seal_mask_px": seal_px,
            "max_abs_pixel_diff_vs_resampled_source": freeze_max_abs,
            "max_abs_pixel_diff_over_seal_mask": seal_max_abs,
            "bit_exact_no_color_processing": bool(freeze_max_abs == 0 and seal_max_abs == 0),
            "roundtrip_ssim_vs_source_crop": ssim_rt,
            "roundtrip_deltaE76_mean_vs_source_crop": de_rt,
            "source_crop_size": [crop_w, crop_h],
            "subject_size_on_canvas": [tw, th],
            "scale": round(scale, 6),
            "note": "bit_exact ⇒ 印区内像素**逐像素等于** Lanczos 重采样结果（未做任何颜色/光影处理）；"
                    "roundtrip 读数＝主体下/上采样再还原的损失量",
        },
        "bg_no_seal": {
            "claim": "成品**宣纸纸底**与**印章掩膜外**均无印泥像素",
            "ink_px_in_generated_background": ink_in_background,
            "ink_px_outside_seal_mask": ink_outside_seal,
            "ink_px_outside_seal_mask_excluding_halo_band": ink_outside_seal_nohalo,
            "ink_px_in_halo_band": ink_in_halo_band,
            "background_region_px": int(bg_region.sum()),
            "ok": bool(ink_in_background == 0),
            "note": "口径①「背景」＝新宣纸纸底（贴片外 ∧ 晕染环带外）＝判据 `ok`；"
                    "「掩膜外交集」另给两个读数（含/不含晕染环带）：B 口径下贴片内照片纸边"
                    "可能有照片自带的淡红边，本读数如实登记",
        },
        "halo": {
            "claim": "晕染只在掩膜**外侧** 1–3 px 环带、alpha ≤ 8%，掩膜内 ≡ 0",
            "applied": bool(halo and ink_rgb is not None),
            "policy": halo_policy,
            "band_px": halo_out["band_px"],
            "alpha_band_max": halo_out["alpha_band_max"],
            "alpha_cap": halo_out["alpha_max_cap"],
            "alpha_inside_mask_max": halo_out["inside_alpha_max"],
            "alpha_outside_band_max": halo_out["outside_alpha_max"],
            "band_px_count": halo_out["band_px_count"],
            "color_rgb_ink_mean": halo_out["color_rgb"],
            "band_px_on_paste_region": int((halo_out["band"] & paste_canvas).sum()),
            "effect_on_paste_region_mean_abs_delta_rgb": (
                round(float(np_.abs(canvas[(halo_out["band"] & paste_canvas)].astype(np_.int16)
                                     - canvas_pre_halo[(halo_out["band"] & paste_canvas)].astype(np_.int16)).mean()), 4)
                if bool((halo_out["band"] & paste_canvas).any()) else 0.0),
            "ok": bool(halo_out["inside_alpha_max"] == 0.0 and halo_out["outside_alpha_max"] == 0.0
                       and halo_out["alpha_band_max"] <= HALO_ALPHA_MAX + 1e-12),
        },
        "composition": {
            "claim": "画布最长边 1200、主体最长边＝画布最长边×62%±1%、居中偏差 ≤ 2 px",
            "canvas_size": [cw, ch],
            "canvas_long_side": int(max(cw, ch)),
            "subject_size": [tw, th],
            "subject_long_side": int(max(tw, th)),
            "subject_ratio_actual": round(max(tw, th) / float(max(cw, ch)), 6),
            "subject_ratio_target": float(subject_ratio),
            "subject_ratio_ok": bool(abs(max(tw, th) / float(max(cw, ch)) - float(subject_ratio)) <= 0.01),
            "offset_px": [ox, oy],
            "center_offset_px": [round(abs((ox + tw / 2.0) - cw / 2.0), 3),
                                 round(abs((oy + th / 2.0) - ch / 2.0), 3)],
            "center_ok": bool(abs((ox + tw / 2.0) - cw / 2.0) <= 2.0 and abs((oy + th / 2.0) - ch / 2.0) <= 2.0),
            "canvas_long_side_ok": bool(int(max(cw, ch)) == int(canvas_long_side)),
            "aspect_source": [src_w, src_h],
            "aspect_canvas": [cw, ch],
        },
        "reproducibility": {
            "claim": "同种子同输出（背景逐像素相同 ＋ 成品逐像素相同）",
            "bg_seed": int(seed),
            "bg_reproducible_same_seed": bg_reproducible,
            "bg_sha256": sha256_array(bg),
            "canvas_sha256": sha256_array(canvas),
            "bg_stats": array_stats(bg),
            "bg_in_gamut": bool(
                np_.asarray(bg).min(axis=(0, 1))[0] >= BG_MIN_RGB[0]
                and np_.asarray(bg).min(axis=(0, 1))[1] >= BG_MIN_RGB[1]
                and np_.asarray(bg).min(axis=(0, 1))[2] >= BG_MIN_RGB[2]
                and np_.asarray(bg).max() <= 255),
        },
        "segmentation": {
            "close_kernel_px": seg["close_kernel_px"], "fringe_px": seg["fringe_px"],
            "fill_holes": seg["fill_holes"], "ink_ratio": round(seg["ink_ratio"], 6),
            "raw_px": int(seg["raw"].sum()), "closed_px": seg["closed_px"],
            "mask_px": seg["mask_px"], "hole_px": seg["hole_px"],
            "fringe_px_added": seg["fringe_px_added"], "radius_effective_px": seg["radius_effective_px"],
            "bbox_in_source": [x0, y0, x1, y1],
            "bbox_size": [x1 - x0, y1 - y0],
            "source_margin_px": [x0, y0, src_w - x1, src_h - y1],
        },
    }
    meta = {
        "caliber": caliber, "alpha_mode": alpha_mode,
        "caliber_reading": ("A＝印章本体紧致外接框内容（掩膜闭合后的外接框）" if caliber == CALIBER_A
                           else "B＝整幅原片"),
        "seed": int(seed), "source_size": [src_w, src_h],
        "canvas_long_side": int(canvas_long_side), "subject_ratio": float(subject_ratio),
        "halo_band_px": int(halo_band_px), "halo_alpha_max": float(halo_alpha_max),
        "halo_policy": halo_policy,
        "halo_applied": bool(halo and ink_rgb is not None),
        "resample": RESAMPLE,
    }
    return {"canvas": canvas, "mask_canvas": mask_canvas, "halo": halo_out,
            "readings": readings, "meta": meta, "seg": seg}


# ── 落盘 / 批量 / CLI ────────────────────────────────────────────────────────────
def write_tiff_lossless(path: Path, arr) -> Dict[str, Any]:
    """无损 TIFF（**与 O 件同容器**：RGB 8-bit ＋ Deflate ＋ Predictor=2）。"""
    np_ = _np()
    Image = _pil()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np_.asarray(arr).astype(np_.uint8)
    Image.fromarray(a).save(path, format="TIFF", compression="tiff_deflate",
                            tiffinfo={TIFF_TAG_PREDICTOR: TIFF_PREDICTOR})
    return {"path": str(path), "bytes": int(path.stat().st_size)}


def _label(img, text: str, xy: Tuple[int, int]):
    """左上角标签（默认位图字体；只画 ASCII 说明，避免字体依赖）。"""
    Image = _pil()
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.rectangle([xy[0] - 3, xy[1] - 3, xy[0] + 8 * len(text) + 3, xy[1] + 14], fill=(0, 0, 0))
    d.text(xy, text, fill=(255, 255, 255))
    return img


def comparison_image(source_rgb, canvas_rgb, *, height: int = 744, gap: int = 8,
                     left_label: str = "O (original)", right_label: str = "OUT") -> Any:
    """「原片｜成品」并排对照（等高显示；不改变任何读数）。"""
    np_ = _np()
    Image = _pil()
    left = Image.fromarray(np_.asarray(source_rgb).astype(np_.uint8))
    right = Image.fromarray(np_.asarray(canvas_rgb).astype(np_.uint8))
    lh = max(1, int(round(height * left.height / left.width)))
    rh = max(1, int(round(height * right.height / right.width)))
    left = left.resize((int(height), lh), _lanczos())
    right = right.resize((int(height), rh), _lanczos())
    H = max(lh, rh)
    out = Image.new("RGB", (int(height) * 2 + int(gap), H), (32, 32, 32))
    out.paste(left, (0, (H - lh) // 2))
    out.paste(right, (int(height) + int(gap), (H - rh) // 2))
    _label(out, left_label, (6, 6))
    _label(out, right_label, (int(height) + int(gap) + 6, 6))
    return out


def run_batch(inputs: Sequence[Dict[str, Any]], out_dir: Path, *, calibers: Sequence[str] = CALIBERS,
              alpha_mode: str = ALPHA_MODE_INK, seed: int = BG_SEED_DEFAULT,
              canvas_long_side: int = CANVAS_LONG_SIDE, subject_ratio: float = SUBJECT_LONG_SIDE_RATIO,
              halo_band_px: int = HALO_BAND_PX, halo_alpha_max: float = HALO_ALPHA_MAX,
              close_px: int = CLOSE_KERNEL_PX, fringe_px: int = FRINGE_PX,
              fill_holes: bool = False, halo: bool = True, halo_policy: str = HALO_POLICY_SEAL,
              compare_height: int = 744, write_compare: bool = True) -> Dict[str, Any]:
    """批量成品化：每份输入 × 每口径 ⇒ `PNG（预览）＋ TIFF（无损）＋ 对照图`，并汇总读数。

    `inputs` 项：`{"name": str, "path": str|Path, "meta": {...任意溯源字段...}}`（**只读** `path`）。
    """
    np_ = _np()
    Image = _pil()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples: List[Dict[str, Any]] = []
    for item in inputs:
        name = str(item["name"])
        src = Path(item["path"])
        rec: Dict[str, Any] = {"name": name, "source": str(src), "meta_in": item.get("meta") or {}}
        if not src.is_file():
            rec["error"] = "source_missing"
            samples.append(rec)
            continue
        arr = np_.asarray(Image.open(src).convert("RGB"))
        rec["source_size"] = [int(arr.shape[1]), int(arr.shape[0])]
        for cal in calibers:
            try:
                res = compose(arr, caliber=cal, alpha_mode=alpha_mode, seed=seed,
                              canvas_long_side=canvas_long_side, subject_ratio=subject_ratio,
                              halo_band_px=halo_band_px, halo_alpha_max=halo_alpha_max,
                              close_px=close_px, fringe_px=fringe_px, fill_holes=fill_holes, halo=halo,
                              halo_policy=halo_policy)
            except Exception as exc:
                rec.setdefault("outputs", []).append({"caliber": cal, "error": f"{type(exc).__name__}: {exc}"})
                continue
            stem = f"{name}-{cal}"
            png = out_dir / f"{stem}.png"
            tif = out_dir / f"{stem}.tiff"
            cmp_png = out_dir / f"{stem}-compare.png"
            Image.fromarray(res["canvas"]).save(png, format="PNG", optimize=False, compress_level=6)
            tinfo = write_tiff_lossless(tif, res["canvas"])
            cinfo = None
            if write_compare:
                cimg = comparison_image(arr, res["canvas"], height=compare_height,
                                        left_label=f"O {arr.shape[1]}x{arr.shape[0]}",
                                        right_label=f"OUT {cal} {res['meta']['canvas_long_side']}px")
                cimg.save(cmp_png, format="PNG", optimize=False, compress_level=6)
                cinfo = {"path": str(cmp_png), "bytes": int(cmp_png.stat().st_size)}
            rec.setdefault("outputs", []).append({
                "caliber": cal, "alpha_mode": alpha_mode,
                "png": {"path": str(png), "bytes": int(png.stat().st_size)},
                "tiff": tinfo, "compare": cinfo,
                "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                "meta": res["meta"], "readings": res["readings"],
            })
        samples.append(rec)
    summary = {
        "module": "server/app/seal_canvas.py",
        "constants": {
            "canvas_long_side": int(canvas_long_side), "subject_long_side_ratio": float(subject_ratio),
            "subject_long_side_target_px": int(round(subject_ratio * canvas_long_side)),
            "halo_band_px": int(halo_band_px), "halo_alpha_max": float(halo_alpha_max),
            "close_kernel_px": int(close_px), "fringe_px": int(fringe_px),
            "fill_holes": bool(fill_holes), "halo": bool(halo), "halo_policy": halo_policy,
            "bg_seed": int(seed), "bg_min_rgb": list(BG_MIN_RGB), "bg_max_rgb": list(BG_MAX_RGB),
            "resample": RESAMPLE, "alpha_mode": alpha_mode, "calibers": list(calibers),
        },
        "samples": samples,
    }
    return summary


def _parse_inputs(argv_inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """`--input name=path`（可重复）。"""
    out = []
    for spec in argv_inputs:
        if "=" not in spec:
            raise SystemExit(f"--input 需形如 name=path，收到 {spec!r}")
        name, path = spec.split("=", 1)
        out.append({"name": name.strip(), "path": path.strip()})
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI：`python -m server.app.seal_canvas --input A=… --input B=… --out DIR --summary JSON`。"""
    ap = argparse.ArgumentParser(prog="seal_canvas", description="印章成品画布 V0（确定性原型）")
    ap.add_argument("--input", action="append", default=[], help="name=path（可重复；只读）")
    ap.add_argument("--src-dir", default=None, help="目录模式：取目录下 *.tiff/*.png/*.jpg，name=文件名去扩展名")
    ap.add_argument("--out", required=True, help="产物目录（PNG/TIFF/对照图）")
    ap.add_argument("--summary", default=None, help="汇总 JSON 落点")
    ap.add_argument("--calibers", default="A,B", help="口径，逗号分隔（A/B）")
    ap.add_argument("--alpha", default=ALPHA_MODE_INK, choices=list(ALPHA_MODES))
    ap.add_argument("--seed", type=int, default=BG_SEED_DEFAULT)
    ap.add_argument("--canvas-long-side", type=int, default=CANVAS_LONG_SIDE)
    ap.add_argument("--subject-ratio", type=float, default=SUBJECT_LONG_SIDE_RATIO)
    ap.add_argument("--halo-band-px", type=int, default=HALO_BAND_PX)
    ap.add_argument("--halo-alpha-max", type=float, default=HALO_ALPHA_MAX)
    ap.add_argument("--halo-policy", default=HALO_POLICY_SEAL, choices=list(HALO_POLICIES))
    ap.add_argument("--close-px", type=int, default=CLOSE_KERNEL_PX)
    ap.add_argument("--fringe-px", type=int, default=FRINGE_PX)
    ap.add_argument("--fill-holes", action="store_true")
    ap.add_argument("--no-halo", action="store_true")
    ap.add_argument("--no-compare", action="store_true")
    args = ap.parse_args(argv)

    items = _parse_inputs(args.input)
    if args.src_dir:
        for p in sorted(Path(args.src_dir).iterdir()):
            if p.suffix.lower() in (".tiff", ".tif", ".png", ".jpg", ".jpeg"):
                items.append({"name": p.stem, "path": str(p)})
    if not items:
        raise SystemExit("没有输入：给 --input name=path 或 --src-dir DIR")

    summary = run_batch(
        items, Path(args.out), calibers=[c.strip() for c in args.calibers.split(",") if c.strip()],
        alpha_mode=args.alpha, seed=args.seed, canvas_long_side=args.canvas_long_side,
        subject_ratio=args.subject_ratio, halo_band_px=args.halo_band_px,
        halo_alpha_max=args.halo_alpha_max, close_px=args.close_px, fringe_px=args.fringe_px,
        fill_holes=args.fill_holes, halo=not args.no_halo, halo_policy=args.halo_policy,
        write_compare=not args.no_compare,
    )
    if args.summary:
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = True
    for s in summary["samples"]:
        if s.get("error"):
            print(f"[SKIP] {s['name']}: {s['error']}")
            continue
        for o in s.get("outputs", []):
            if o.get("error"):
                print(f"[FAIL] {s['name']} {o['caliber']}: {o['error']}")
                ok = False
                continue
            r = o["readings"]
            print(f"[OK] {s['name']}-{o['caliber']} canvas={r['composition']['canvas_size']} "
                  f"subject={r['composition']['subject_size']} ratio={r['composition']['subject_ratio_actual']:.4f} "
                  f"freezeΔ={r['freeze']['max_abs_pixel_diff_vs_resampled_source']} "
                  f"bg_no_seal={r['bg_no_seal']['ink_px_in_generated_background']} "
                  f"halo_in={r['halo']['alpha_inside_mask_max']} halo_max={r['halo']['alpha_band_max']}")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
