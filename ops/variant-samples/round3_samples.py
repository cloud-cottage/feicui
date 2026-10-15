#!/usr/bin/env python
"""C3 样张（Kong · ops/variant-samples/round3_samples.py）。

【本单两条（Kevin 已批，见 C2 README §9）】
  ① 纸底色域放宽：**先不改生产常量**（`seal_canvas.BG_*` 被印面 O 件成品面与整页线两条线共用），
     在样张脚本里把色域**参数化**（下限 × 基色色温 两个旋钮），出多档对比：
     下限 246/244/242 ×（中性基色 252.5 / 豆包暖白基色 253.09,248.90,247.84），幅度一律按豆包标定
     RMS 3.593（C2·OBV 组参数，只是被生产色域装不下）。每档实测：纸底 RMS、255 截顶占比、
     下限截顶占比、亮度 p10/p50/p90、mean RGB，与豆包逐项对照；600 vs 2400 dpi 对齐判据照跑。
  ② 观感档做实：以 C2_aes 为基线精修——语义浓淡**折半**（`sem=0.5`）、半透目标 1.56%、
     边缘过渡目标 5.65px@2400（近边旋钮 `edge_mm`/`edge_drop`，两种机制：
     `edge_mode="paper"` 近边向纸色混合＝本轮机制；`"chroma"` 色度倍率软化＝首版机制对照，
     实测**不加宽** 0.75→0.25 过渡带）、颗粒（7.97）与晕染（0.065/0.657mm）已达标保持。
     ★ 新增度量口径：除逐像素 ΔE2000 外，另报「色度分量 ΔE（Lab a*/b* 平面，排除 L*）」
       ＋「按浓度分层的 ΔE（dn 6 箱＝豆包语义箱 ＋ L* 分位箱）」——观感档故意改 L* ⇒
       逐像素 ΔE2000 必然升；「色相是否咬靶色」应以 a*/b* 平面读数为准（两口径都报）。

【实现口径】
  - 印泥算子＝`round2_samples.ink_chroma_v3` 观感档段的**完整重跑**（`ink_chroma_c3`）：
    靶色/平滑/毛糙/颗粒各步与 C2 逐行同式，仅两处参数化：语义 dL ×sem、色度 cscale ×近边软化。
    sem=1.0 且 edge 关时与 C2 输出**逐位一致**（main 里硬断言）；sem<1 时**在源头重算语义**
    （不做「C2 输出后再补一段」——那是把语义叠乘成 (1+sem)，方向性错误）。
    整页管线（光场/色调/纸底/渗透/晕染/冻结）直接复用 `round2_samples.run_variant`（只换算子）。
  - 纸底生成＝`round2_samples.paper_field_mm` 的参数化版（同一组 octave、同一 mm 位置哈希、同一种子），
    只把 色域下限/基色/微色偏σ 换成档位参数；上限仍 (255,255,255)＝生产值；幅度乘子 1.0＝豆包标定
    （`octave_spec` 的 k_extra 是**乘子**，不是 k 本身）。
  - 纸底只写「纸底类像素」掩膜（生产判据 gray≥210 ∧ sat≤0.15，`rp.build_masks` 单一真源）；
    印刷黑字/框线/印泥（掩膜外＋掩膜内白线）一字不动 —— 由 freeze 断言自证。
  - 旋钮可用环境变量覆盖（仅调参用）：`FEICUI_C3_KNOBS="sem=0.5,edge_mm=0.09,edge_drop=0.35"`。

红线：不改生产常量（`seal_canvas.py` / `colorcal.py` 只 import 只参考）／不写 yinpu.db／不建 job／
`2_HighRes_PDF` 与 `output/books` 只读／样张只落 `output/samples/book-page-2400-variants/round3/`／
可入库件只落 `ops/variant-samples/`。

跑法：cd /Users/kevin/bistro/xiai/feicui && ./venv/bin/python ops/variant-samples/round3_samples.py
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))
sys.path.insert(0, str(REPO / "ops" / "book-page-2400"))
sys.path.insert(0, str(REPO / "ops" / "variant-samples"))
import render_page_2400 as rp                                     # noqa: E402  生产整页实现（只读复用）
from app import seal_canvas as sc                                 # noqa: E402  生产常量（只 import 不改）
from app import colorcal as cc                                    # noqa: E402  靶色 / ΔE / V3 单一真源
import variants_samples as vs                                     # noqa: E402  C 版工具（只读复用）
import doubao_ink_reference as dr                                 # noqa: E402  印泥特征度量（与豆包同一套）
import round2_samples as r2                                       # noqa: E402  C2 全部机件（只读复用）

# C2 原始印泥算子（import 时绑定；c3_operator 换掉 r2.ink_chroma_v3 后仍可委托到它）
_R2_INK_V3 = r2.ink_chroma_v3

PAGE, XREF, SCAN_DPI = 29, 112, 300
SRC_W, SRC_H = 2125, 3059
COMP_DPI, PROD_DPI = 600, 2400
C1_BBOX, C2_BBOX = r2.C1_BBOX, r2.C2_BBOX
SAMPLES_DIR = REPO / "output/samples/book-page-2400-variants/round3"
OPS_DIR = Path(__file__).resolve().parent
READINGS_PATH = OPS_DIR / "readings-round3.json"
DOUBAO_PAPER_JSON = r2.DOUBAO_PAPER
DOUBAO_PAPER_IMG = Path(json.loads(DOUBAO_PAPER_JSON.read_text())["source"]["path"])
MM_PER_IN = 25.4
TEX_FIELD_MM, TEX_STAT_FIELD_MM = 8.0, 12.0
THUMB_W = 800

# ══════════════════════════════════════════════════════════════════════════════════════
# 0. 观感档旋钮（环境变量可覆盖，仅调参用）
# ══════════════════════════════════════════════════════════════════════════════════════
KNOB_DEFAULTS = {"sem": 0.5, "edge_mm": 0.09, "edge_drop": 0.35}


def _parse_knobs() -> dict:
    k = dict(KNOB_DEFAULTS)
    raw = os.environ.get("FEICUI_C3_KNOBS")
    if raw:
        for kv in raw.split(","):
            key, _, val = kv.partition("=")
            k[key.strip()] = float(val)
    return k


ACTIVE_KNOBS: dict = _parse_knobs()

# ══════════════════════════════════════════════════════════════════════════════════════
# 1. 色域档位（参数化；生产常量只读引用）
# ══════════════════════════════════════════════════════════════════════════════════════
DOUBAO_PAPER_BASE = (253.093, 248.896, 247.839)   # ← 豆包实测纸底均值（证据件 paper_color.mean_rgb）
NEUTRAL_BASE = (252.5, 252.5, 252.5)              # 中性基色（同生产均值亮度、无色温偏）
GAMUT_FLOORS = (246, 244, 242)
K_RMS = r2.TEX_RMS_TARGET                         # 豆包纸底总 RMS 3.593（幅度统一标定到它）


def gamut_defs() -> list[dict]:
    """色域档位表：① 生产基线 ② 3 下限 × 中性基色 ③ 3 下限 × 豆包暖白基色 ④ 2 档附加观察。

    amp_k 是 `octave_spec` 的**幅度乘子**（1.0＝豆包标定 OBV 幅度 k=3.593；0.75＝附档）。
    """
    out = [{"key": "PROD", "label": "现行生产色域（基线）", "base": tuple(float(v) for v in sc.BG_BASE_RGB),
            "min": tuple(float(v) for v in sc.BG_MIN_RGB), "max": tuple(float(v) for v in sc.BG_MAX_RGB),
            "chroma_sigma": float(sc.BG_CHROMA_SIGMA), "amp_k": 1.0,
            "amp_note": "＝豆包标定幅度乘子 1.0（OBV k=3.593；生产下限 250 装不下 ⇒ 截顶）",
            "source": "seal_canvas.BG_MIN/BG_BASE/BG_MAX/BG_CHROMA_SIGMA（只读引用，未改）"}]
    for tint, base in (("N", NEUTRAL_BASE), ("W", DOUBAO_PAPER_BASE)):
        for lo in GAMUT_FLOORS:
            out.append({"key": f"{tint}{lo}",
                        "label": f"下限{lo}·{'中性基色' if tint == 'N' else '豆包暖白基色'}",
                        "base": base, "min": (float(lo),) * 3, "max": (255.0, 255.0, 255.0),
                        "chroma_sigma": float(sc.BG_CHROMA_SIGMA), "amp_k": 1.0,
                        "amp_note": "幅度乘子 1.0（＝豆包标定 RMS 3.593）",
                        "source": "本轮参数化（下限＝逐通道统一最低允许值；上限＝生产值不动）"})
    out.append({"key": "W242x075", "label": "下限242·豆包暖白·幅度×0.75（附加观察）", "base": DOUBAO_PAPER_BASE,
                "min": (242.0,) * 3, "max": (255.0, 255.0, 255.0), "chroma_sigma": float(sc.BG_CHROMA_SIGMA),
                "amp_k": 0.75, "amp_note": "幅度乘子 0.75（标称 RMS ≈2.70，介于 C2·MID 2.30 与豆包 3.593）",
                "source": "本轮参数化（附加观察：不满幅时的替代档）"})
    out.append({"key": "W240", "label": "下限240·豆包暖白（诊断档：能否到 RMS 3.593）", "base": DOUBAO_PAPER_BASE,
                "min": (240.0,) * 3, "max": (255.0, 255.0, 255.0), "chroma_sigma": float(sc.BG_CHROMA_SIGMA),
                "amp_k": 1.0, "amp_note": "幅度乘子 1.0（＝豆包标定 RMS 3.593；下限再降一档做可达性诊断）",
                "source": "本轮参数化（附加观察：只进读数，不作推荐档）"})
    out.append({"key": "W242chroma", "label": "下限242·豆包暖白·暖偏σ×4（附加观察）", "base": DOUBAO_PAPER_BASE,
                "min": (242.0,) * 3, "max": (255.0, 255.0, 255.0), "chroma_sigma": round(4.0 * float(sc.BG_CHROMA_SIGMA), 4),
                "amp_k": 1.0, "amp_note": "幅度乘子 1.0；微色偏 σ 0.30→1.20（豆包暗尾大半是**色温**变化）",
                "source": "本轮参数化（附加观察：检验「豆包暗尾来自 G/B 色偏」假设）"})
    return out


GAMUTS = gamut_defs()
GAMUT_BY_KEY = {g["key"]: g for g in GAMUTS}
REC_KEY = "W242"          # 预告推荐档（最终以读数为准，报告里定）


def paper_field_gamut(rows, cols, dpi, cand, gamut, amp_level=1.0):
    """`r2.paper_field_mm` 的参数化版：同一组 octave/同一种子/**mm 位置哈希**，只换 色域/基色/微色偏σ。

    ★ rows/cols 是**像素索引**，须先换算成 mm 再进 vnoise_mm（与 r2.paper_field_mm 同式）——
      直接喂像素索引会变成「像素常量纹理」（600dpi 物理尺度 ×4，dpi 对齐判据 ac 比值≈0.25 当场抓获）。
    注意 cand 传 "OBV"（k=3.593 豆包标定），amp_level 传 gamut["amp_k"]（乘子）。
    """
    r_mm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    c_mm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / float(dpi)
    lum = np.zeros((r_mm.size, c_mm.size), np.float32)
    for o in r2.octave_spec(cand, dpi, 1.0, float(gamut["amp_k"]) * float(amp_level)):
        n = r2.vnoise_mm(r_mm, c_mm, o["long_mm"], o["short_mm"], r2.SEED, o["salt"])
        ref = r2.octave_std_ref(o["long_mm"], o["short_mm"], r2.SEED, o["salt"])
        lum += (np.float32(o["amp"] / ref) * (n.astype(np.float32) - np.float32(0.5)))
    h2 = rp._hash64(rows, cols, r2.SEED, 1)
    chroma = np.stack([rp._u(h2, 0, 21) - 0.5, rp._u(h2, 21, 21) - 0.5, rp._u(h2, 42, 21) - 0.5],
                      axis=-1).astype(np.float32) * 2.0
    out = (np.asarray(gamut["base"], np.float32)[None, None, :] + lum[:, :, None]
           + np.float32(gamut["chroma_sigma"]) * chroma)
    return np.clip(out, np.asarray(gamut["min"], np.float32)[None, None, :],
                   np.asarray(gamut["max"], np.float32)[None, None, :])


def paper_patch(cand, dpi, field_mm, gamut, origin_mm=(40.0, 25.0)):
    n = r2.mm2px_int(field_mm, dpi)
    rows = np.arange(r2.mm2px_int(origin_mm[1], dpi), r2.mm2px_int(origin_mm[1], dpi) + n, dtype=np.int64)
    cols = np.arange(r2.mm2px_int(origin_mm[0], dpi), r2.mm2px_int(origin_mm[0], dpi) + n, dtype=np.int64)
    return vs.to_u8(paper_field_gamut(rows, cols, dpi, cand, gamut))


def paper_for_gamut(gamut, h: int, w: int, dpi: int) -> np.ndarray:
    cols = np.arange(0, w, dtype=np.int64)
    out = np.empty((h, w, 3), np.uint8)
    for y0 in range(0, h, 384):
        y1 = min(y0 + 384, h)
        rows = np.arange(y0, y1, dtype=np.int64)
        out[y0:y1] = vs.to_u8(paper_field_gamut(rows, cols, dpi, "OBV", gamut))
    return out


def paper_metrics_ext(patch_u8, gamut=None) -> dict:
    """纸底实测：色域/明度直方图/总 RMS/255 截顶/下限截顶 —— 与参照图同一套口径 ＋ 档位自证。"""
    g = patch_u8.astype(np.float32)
    lum = vs.lum(g)
    m = {"mean_rgb": r2.rgb_mean(patch_u8.reshape(-1, 3)),
         "std_rgb": [round(float(v), 3) for v in g.reshape(-1, 3).std(0)],
         "rms_lum_0_255": round(float((lum - float(lum.mean())).std()), 4),
         "lum_deciles": [round(float(np.percentile(lum, p)), 2) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)],
         "lum_p10_p50_p90": [round(float(np.percentile(lum, p)), 2) for p in (10, 50, 90)],
         "clip255_share": round(float((g.max(axis=2) >= 255.0).mean()), 5),
         "min_rgb": [int(v) for v in g.reshape(-1, 3).min(0)],
         "max_rgb": [int(v) for v in g.reshape(-1, 3).max(0)]}
    if gamut is not None:
        lo = np.asarray(gamut["min"], np.float32)
        m["clip_floor_share"] = round(float((g.min(axis=2) <= lo.min() + 1e-4).mean()), 5)
        m["clip_floor_share_per_ch"] = [round(float((g[..., c] <= lo[c] + 1e-4).mean()), 5) for c in range(3)]
        m["gamut"] = {"key": gamut["key"], "min": list(gamut["min"]), "base": list(gamut["base"]),
                      "chroma_sigma": gamut["chroma_sigma"], "amp_k": gamut["amp_k"]}
    return m


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. ΔE 度量（逐像素 ΔE2000 ＋ 色度分量 ΔE ＋ 按浓度分层）
# ══════════════════════════════════════════════════════════════════════════════════════
TARGET_LAB = cc.srgb_to_lab(cc.TARGET_RGB)
_DN_EDGES = np.linspace(0.0, 1.0, 7)          # 与豆包语义箱同口径（d/d_p90 六箱）


def ciede2000_arr(lab, lab2) -> np.ndarray:
    """`cc.ciede2000_lab` 的向量化等价（脚本内用于批量分层；落盘前与标量逐点校验）。"""
    L1, a1, b1 = lab[..., 0], lab[..., 1], lab[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cb = 0.5 * (C1 + C2)
    Cb7 = Cb ** 7
    G = 0.5 * (1.0 - np.sqrt(Cb7 / (Cb7 + 25.0 ** 7)))
    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    dLp = L2 - L1
    dCp = C2p - C1p
    diff = h2p - h1p
    dhp = np.where(C1p * C2p == 0.0, 0.0, diff)
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2.0))
    Lp = 0.5 * (L1 + L2)
    Cp = 0.5 * (C1p + C2p)
    s = h1p + h2p
    hp = np.where(C1p * C2p == 0.0, s,
                  np.where(np.abs(h1p - h2p) <= 180.0, 0.5 * s,
                           np.where(s < 360.0, 0.5 * (s + 360.0), 0.5 * (s - 360.0))))
    T = (1.0 - 0.17 * np.cos(np.radians(hp - 30.0)) + 0.24 * np.cos(np.radians(2.0 * hp))
         + 0.32 * np.cos(np.radians(3.0 * hp + 6.0)) - 0.20 * np.cos(np.radians(4.0 * hp - 63.0)))
    dth = 30.0 * np.exp(-(((hp - 275.0) / 25.0) ** 2))
    Cp7 = Cp ** 7
    RC = 2.0 * np.sqrt(Cp7 / (Cp7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lp - 50.0) ** 2) / np.sqrt(20.0 + (Lp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cp
    SH = 1.0 + 0.015 * Cp * T
    RT = -np.sin(np.radians(2.0 * dth)) * RC
    tL, tC, tH = dLp / SL, dCp / SC, dHp / SH
    return np.sqrt(tL * tL + tC * tC + tH * tH + RT * tC * tH)


def delta_e_metrics(rgb_px, dn=None, max_px=160000) -> dict:
    """逐像素 ΔE2000 ＋ 色度分量 ΔE（a*/b* 平面，排除 L*）＋ 按浓度分层（dn 6 箱 / L* 分位箱）。"""
    px = np.asarray(rgb_px, np.float64)
    n_all = int(px.shape[0])
    if n_all == 0:
        return {"pixels": 0}
    stride = 1
    if n_all > max_px:
        stride = int(np.ceil(n_all / max_px))
        px = px[::stride]
    lab = cc._srgb_to_lab_arr(px)
    de = ciede2000_arr(lab, np.asarray(TARGET_LAB, np.float64)[None, :])
    dab = np.hypot(lab[:, 1] - TARGET_LAB[1], lab[:, 2] - TARGET_LAB[2])
    out = {"target_lab": [round(float(v), 4) for v in TARGET_LAB],
           "pixels": n_all, "sampled": int(px.shape[0]), "stride": stride,
           "delta_e2000": {"median": round(float(np.median(de)), 4), "p90": round(float(np.percentile(de, 90)), 4),
                           "mean": round(float(de.mean()), 4),
                           "leq5_rate": round(float((de <= 5.0).mean()), 5), "leq3_rate": round(float((de <= 3.0).mean()), 5)},
           "delta_e_ab": {"definition": "色度分量 ΔE ＝ sqrt(Δa*²＋Δb*²)（Lab a*/b* 平面，排除 L*）——"
                                        "「色相/饱和度是否咬靶色」的口径；观感档故意改 L* ⇒ 此口径不受影响",
                          "median": round(float(np.median(dab)), 4), "p90": round(float(np.percentile(dab, 90)), 4),
                          "mean": round(float(dab.mean()), 4), "leq5_rate": round(float((dab <= 5.0).mean()), 5),
                          "leq3_rate": round(float((dab <= 3.0).mean()), 5)}}
    if dn is not None and dn.size == n_all:
        d = dn[::stride]
        rows = []
        for i in range(6):
            sel = (d >= _DN_EDGES[i]) & (d <= _DN_EDGES[i + 1] if i == 5 else d < _DN_EDGES[i + 1])
            if int(sel.sum()) >= 30:
                rows.append({"bin": f"dn {_DN_EDGES[i]:.3f}–{_DN_EDGES[i + 1]:.3f}",
                             "share": round(float(sel.mean()), 4),
                             "L_mean": round(float(lab[sel, 0].mean()), 3),
                             "C_mean": round(float(np.hypot(lab[sel, 1], lab[sel, 2]).mean()), 3),
                             "dE2000_median": round(float(np.median(de[sel])), 4),
                             "dE_ab_median": round(float(np.median(dab[sel])), 4),
                             "centroid_rgb": r2.rgb_mean(px[sel])})
        out["stratified_by_dn"] = rows
        qs = np.percentile(lab[:, 0], [10, 30, 50, 70, 90])
        edges = np.concatenate([[-1e9], qs, [1e9]])
        rows = []
        for i in range(5):
            sel = (lab[:, 0] >= edges[i]) & (lab[:, 0] < edges[i + 1])
            if int(sel.sum()) >= 30:
                rows.append({"bin": f"L* {edges[i]:.1f}–{edges[i + 1]:.1f}" if 0 < i < 5
                             else ("L* 最深(≤p10)" if i == 0 else "L* 最浅(≥p90)"),
                             "share": round(float(sel.mean()), 4),
                             "L_mean": round(float(lab[sel, 0].mean()), 3),
                             "C_mean": round(float(np.hypot(lab[sel, 1], lab[sel, 2]).mean()), 3),
                             "dE2000_median": round(float(np.median(de[sel])), 4),
                             "dE_ab_median": round(float(np.median(dab[sel])), 4),
                             "centroid_rgb": r2.rgb_mean(px[sel])})
        out["stratified_by_Lstar"] = rows
        out["stratification_note"] = ("浓度分层＝① dn（到最近非印泥像素距离 / d_p90，与豆包语义箱同口径）"
                                      "② L* 分位箱（p10/30/50/70/90；L* 低＝浓度高）。"
                                      "两口径都给出 ΔE2000 与 ΔE_ab —— 观感档的「色相咬靶」看 ΔE_ab")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. C3 印泥算子＝`r2.ink_chroma_v3` 观感档段的完整重跑（旋钮：sem / edge_mm / edge_drop）
# ══════════════════════════════════════════════════════════════════════════════════════
EDGE_MODE = os.environ.get("FEICUI_C3_EDGE_MODE", "paper")   # "paper"＝近边向纸色混合（本轮机制）；"chroma"＝色度倍率软化（首版机制，留作对照）


def _paper_rgb_of(img, red_m):
    """窗口内纸底均色（生产判据 gray≥210 ∧ sat≤0.15；无纸底像素时回退生产基色）。"""
    u8 = vs.to_u8(img)
    pm = (vs.lum(u8) >= 210) & (vs.sat_of(u8) <= 0.15) & (~red_m)
    if pm.any():
        return img[pm].mean(axis=0).astype(np.float32)
    return np.asarray(sc.BG_BASE_RGB, np.float32)


def ink_chroma_c3(img, red_m, smooth_level, tier, ops, dpi: int = PROD_DPI):
    """观感档段完整重跑：靶色→平滑→毛糙→语义(×sem, ×近边软化)→颗粒→掩膜守卫。

    与 `r2.ink_chroma_v3`（aesthetic 分支）逐行同式，仅两处参数化：
      sem       —— 语义 L* 曲线整体乘子（1.0＝C2 原样；0.5＝本轮「强度折半」）；
      edge_mm/edge_drop —— 近边色度软化带（mm × 最大额外色度下降）：cscale ×= 1−drop×(1−d_mm/band)
                   ⇒ S 等值线内移、饱和度 0.75→0.25 过渡带加宽；L* 不动、掩膜不动。
    旋钮取 C2 值（sem=1.0 / edge 关）时与 C2 输出逐位一致（main 里断言自证）。
    ★ sem<1 时**不在 C2 输出上再补语义**（那会叠乘成 (1+sem)），而是在源头把 dL 曲线 ×sem 重算。
    """
    K = dict(ACTIVE_KNOBS)
    sem = float(K.get("sem", 1.0))
    edge_mm = float(K.get("edge_mm", 0.0))
    edge_drop = float(K.get("edge_drop", 0.0))
    emode = str(K.get("edge_mode", EDGE_MODE))
    if tier != "aesthetic" or (sem == 1.0 and edge_mm <= 0.0):
        return _R2_INK_V3(img, red_m, smooth_level, tier, ops, dpi)
    info: dict = {"smooth_level": float(smooth_level), "tier": tier, "ops": list(ops), "dpi": dpi,
                  "target_hex": cc.TARGET_HEX, "chroma_strength": float(cc.V3_FG_CHROMA_STRENGTH),
                  "chroma_impl": "colorcal.apply_foreground_chroma（V3）",
                  "c3_knobs": {**K, "impl": "sem：豆包语义 L* 曲线整体 ×sem（源头重算）；"
                                           "edge：近边色度软化带（cscale ×= 1−drop×(1−d_mm/band)）"}}
    if dpi < r2.INK_MIN_DPI_FINE:
        dropped = [o for o in ops if o in ("grain", "roughness")]
        if dropped:
            ops = tuple(o for o in ops if o not in ("grain", "roughness"))
            info["dropped_underresolved_ops"] = {
                "ops": dropped, "at_dpi": dpi, "min_dpi": r2.INK_MIN_DPI_FINE,
                "scale_mm": r2.INK_GRAIN_MM, "px_at_dpi": round(r2.mm2px(r2.INK_GRAIN_MM, dpi), 3),
                "reason": "物理尺度 <2px 不可表示 ⇒ 停用（避免画与 dpi 不匹配的假纹理）"}
        info["ops"] = list(ops)
    px_before = (img[..., :3][red_m].astype(np.float64) if red_m.any() else None)
    img, fg = cc.apply_foreground_chroma(img, red_m)
    info["fg_gamut_clip_rate"] = round(float(fg["gamut_clip_rate"]), 6)
    info["fg_chroma_reduced_rate"] = round(float(fg["chroma_reduced_rate"]), 6)
    info["fg_iou_raw"] = round(float(fg["iou_raw"]), 6)
    info["fg_mask_reverted_px"] = int(fg["mask_reverted_pixels"])
    rad = r2.mm2px_int(r2.GUIDE_RADIUS_MM, dpi)
    if smooth_level > 0 and red_m.any():
        y = vs.lum(img)
        sm = vs.guided_smooth_color(img, y, rad, r2.GUIDE_EPS)
        blend = float(smooth_level)
        img = img.copy()
        img[red_m] = img[red_m] * (1.0 - blend) + sm[red_m] * blend
        del sm
    # ③④ 语义浓淡（×sem）＋ 半透（×近边软化）＋ 毛糙（与 C2 同式）
    d = cv2.distanceTransform(red_m.astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)
    d_p90 = float(np.percentile(d[red_m], 90.0))
    dn = d / max(d_p90, 1e-6)
    if "roughness" in ops:
        rows = np.arange(img.shape[0], dtype=np.int64)
        cols = np.arange(img.shape[1], dtype=np.int64)
        cm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / dpi
        rm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / dpi
        jit = r2.vnoise_mm(rm, cm, r2.INK_ROUGH_MM, r2.INK_ROUGH_MM, r2.SEED, 311).astype(np.float32) - np.float32(0.5)
        amp_norm = (2.0 * r2.INK_ROUGH_MM) / max(r2.px2mm(d_p90, dpi), 1e-6)
        dn = np.clip(dn + jit * np.float32(amp_norm), 0.0, None)
        info["roughness"] = {"scale_mm": r2.INK_ROUGH_MM,
                             "jitter_amplitude_mm": round(2.0 * r2.INK_ROUGH_MM, 4),
                             "amp_in_dn_units": round(amp_norm, 5), "mask_moved": False,
                             "impl": "位置哈希噪声扰动距离场 ⇒ L* 等值线毛糙；**掩膜逐像素不动**"}
    dn = np.clip(dn, 0.0, 1.0)
    dn_lookup, dL_curve, s_curve = r2._semantic_curves()
    dL = (np.interp(dn, dn_lookup, dL_curve).astype(np.float64) * sem)
    cscale = np.interp(dn, dn_lookup, s_curve).astype(np.float64)
    edge_w = None
    if edge_mm > 0 and edge_drop > 0:
        d_mm = d * float(r2.px2mm(1.0, dpi))
        ef = np.clip(d_mm / edge_mm, 0.0, 1.0).astype(np.float64)
        edge_w = edge_drop * (1.0 - ef)          # 边界处＝drop → 带外＝0
        if emode == "chroma":
            cscale = cscale * (1.0 - edge_w)
            info["edge_softening"] = {"mode": "chroma", "band_mm": edge_mm, "band_px": round(r2.mm2px(edge_mm, dpi), 3),
                                      "max_drop": edge_drop,
                                      "impl": "近边色度倍率软化（首版机制；C1R1 实测不加宽 0.75→0.25 过渡带 ⇒ 留作对照）"}
        else:
            info["edge_softening"] = {"mode": "paper", "band_mm": edge_mm, "band_px": round(r2.mm2px(edge_mm, dpi), 3),
                                      "max_blend": edge_drop,
                                      "impl": "近边向纸色混合（渗透/半透机制）：c = c×(1−w)＋paper_rgb×w；"
                                              "sat 内降外不变 ⇒ 0.75→0.25 过渡带加宽；L* 随之抬（观感档允许）"}
    lab = cc._srgb_to_lab_arr(img[..., :3][red_m].astype(np.float64))
    L = lab[:, 0] + dL[red_m]
    ab = lab[:, 1:] * cscale[red_m][:, None]
    new_rgb = cc._lab_to_srgb_arr(np.stack([L, ab[:, 0], ab[:, 1]], axis=-1))
    if edge_mm > 0 and edge_drop > 0 and emode == "paper" and edge_w is not None:
        ew = edge_w[red_m][:, None]
        new_rgb = new_rgb * (1.0 - ew) + _paper_rgb_of(img, red_m)[None, :] * ew
    if "grain" in ops:
        er = cv2.erode(red_m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        g_blur = r2.mm2px(r2.CAL["ink_grain_blur_mm"], dpi)
        lum_now = vs.lum(img)
        hp = (lum_now - cv2.GaussianBlur(lum_now, (0, 0), g_blur))[er] if er.any() else np.zeros(1)
        cur = float(hp.std())
        sig = float(np.sqrt(max(r2.CAL["ink_grain_lum_highpass_sigma_target"] ** 2 - cur ** 2, 0.0)))
        rows = np.arange(img.shape[0], dtype=np.int64)
        cols = np.arange(img.shape[1], dtype=np.int64)
        cm = (cols.astype(np.float64) + 0.5) * MM_PER_IN / dpi
        rm = (rows.astype(np.float64) + 0.5) * MM_PER_IN / dpi
        g = r2.vnoise_mm(rm, cm, r2.INK_GRAIN_MM, r2.INK_GRAIN_MM, r2.SEED, 401).astype(np.float32)
        g = (g - float(g.mean())) / max(float(g.std()), 1e-6)
        new_rgb = new_rgb + np.float32(sig) * g[red_m][:, None]
        info["grain"] = {"scale_mm": r2.INK_GRAIN_MM, "blur_sigma_mm": round(r2.CAL["ink_grain_blur_mm"], 5),
                         "blur_sigma_px": round(g_blur, 2), "px_eroded": int(er.sum()),
                         "doubao_target_sigma_0_255": r2.CAL["ink_grain_lum_highpass_sigma_target"],
                         "current_sigma_after_smooth_0_255": round(cur, 4),
                         "sigma_added_0_255": round(sig, 4),
                         "expected_result_0_255": round(float(np.sqrt(cur ** 2 + sig ** 2)), 4),
                         "impl": "位置哈希噪声（mm 空间，零均值单位方差）×σ_add，加在 L* 域；"
                                 "掩膜守卫保证掉出 ink 掩膜的像素回退原值"}
    out = img.copy()
    cand_rgb = np.clip(np.rint(new_rgb), 0, 255).astype(out[..., :3].dtype)
    tmp = out.copy()
    tmp[..., :3][red_m] = cand_rgb
    keep = cc.ink_mask(tmp.astype(np.float64))[red_m]
    final = cand_rgb.copy()
    final[~keep] = out[..., :3][red_m][~keep]
    out[..., :3][red_m] = final
    info["semantic"] = {"L_curve_dn": [round(float(v), 4) for v in dL_curve],
                        "dL_wide_minus_thin_target": r2.CAL["ink_semantic_L_wide_minus_thin"],
                        "chroma_scale_curve": [round(float(v), 4) for v in s_curve],
                        "curve_source": "豆包参照图#2（doubao-ink-reference-features.json）",
                        "translucency_share_target": r2.CAL["ink_translucency_share_light_inside"],
                        "L_star_allowed_to_change": tier == "aesthetic"}
    info["mask_guard_dropped_and_reverted_px"] = int((~keep).sum())
    info["semantic"]["dL_wide_minus_thin_applied_max"] = round(
        float(np.interp(0.0, dn_lookup, dL_curve)) * sem, 4)
    info["semantic"]["sem_gain"] = sem
    r2._lstar_delta(info, px_before, out, red_m)
    return out, info


_C2_VARIANTS_BACKUP: dict | None = None


@contextlib.contextmanager
def c3_operator(knobs: dict):
    """把 `r2.run_variant` 的印泥算子换成本轮参数化版（退出即还原；C2 复现件零改动）。"""
    global ACTIVE_KNOBS, _C2_VARIANTS_BACKUP
    prev_fn, prev_knobs = r2.ink_chroma_v3, dict(ACTIVE_KNOBS)
    if _C2_VARIANTS_BACKUP is None:
        _C2_VARIANTS_BACKUP = dict(r2.VARIANTS)
    ACTIVE_KNOBS = dict(knobs)
    r2.ink_chroma_v3 = ink_chroma_c3
    r2.VARIANTS.update({
        "C3_aes": {"bg": "MID", "ink": "v3", "tier": "aesthetic", "smooth": 0.55,
                   "ops": ("semantic", "grain", "roughness"),
                   "label": f"C3观感档（语义×{knobs.get('sem', 0.5):g}＋边缘软化 {knobs.get('edge_mm', 0):g}mm/{knobs.get('edge_drop', 0):g}）"}})
    try:
        yield
    finally:
        r2.ink_chroma_v3 = prev_fn
        ACTIVE_KNOBS = prev_knobs
        r2.VARIANTS.clear()
        r2.VARIANTS.update(_C2_VARIANTS_BACKUP)


# 观感档候选（C1R1 窗口上的旋钮扫描；headline＝Kevin 指令「折半」）
# edge_mode："paper"＝近边向纸色混合（本轮机制）；"chroma"＝首版色度软化（对照，实测不加宽过渡带）
AES_CANDIDATES = {
    "C3_g100": {"knobs": {"sem": 1.0, "edge_mm": 0.0, "edge_drop": 0.0},
                "label": "C2 等价（sem=1.0＋边缘关）——逐位回归自证"},
    "C3_g050": {"knobs": {"sem": 0.5, "edge_mm": ACTIVE_KNOBS["edge_mm"], "edge_drop": ACTIVE_KNOBS["edge_drop"],
                          "edge_mode": "paper"},
                "label": "★折半（Kevin 指令）：语义 ×0.5＋近边混纸"},
    "C3_g080": {"knobs": {"sem": 0.8, "edge_mm": ACTIVE_KNOBS["edge_mm"], "edge_drop": ACTIVE_KNOBS["edge_drop"],
                          "edge_mode": "paper"},
                "label": "语义 ×0.8（半透 1.56% 标定行）＋近边混纸"},
    "C3_g020": {"knobs": {"sem": 0.2, "edge_mm": ACTIVE_KNOBS["edge_mm"], "edge_drop": ACTIVE_KNOBS["edge_drop"],
                          "edge_mode": "paper"},
                "label": "语义 ×0.2（斜率对齐豆包 −7.75）＋近边混纸"},
    "C3_g000": {"knobs": {"sem": 0.0, "edge_mm": ACTIVE_KNOBS["edge_mm"], "edge_drop": ACTIVE_KNOBS["edge_drop"],
                          "edge_mode": "paper"},
                "label": "语义 ×0（只用源图固有浓淡）＋近边混纸"},
    "C3_g050_noedge": {"knobs": {"sem": 0.5, "edge_mm": 0.0, "edge_drop": 0.0},
                       "label": "折半、无边缘软化（隔离边缘旋钮的贡献）"},
    "C3_g050_chromaedge": {"knobs": {"sem": 0.5, "edge_mm": ACTIVE_KNOBS["edge_mm"],
                                     "edge_drop": ACTIVE_KNOBS["edge_drop"], "edge_mode": "chroma"},
                           "label": "折半＋近边色度软化（首版机制对照：实测不加宽过渡带）"},
}


def ink_readout(img, core_m, red_m, dpi, label=""):
    """印泥读数：ΔE 两口径＋分层 ＋ 与豆包同一套特征（dr.ink_features）。"""
    px = img[core_m].astype(np.float64)
    red_px = img[red_m].astype(np.float64)
    d = cv2.distanceTransform(red_m.astype(np.uint8), cv2.DIST_L2, 3).astype(np.float64)
    d_p90 = float(np.percentile(d[red_m], 90.0)) if red_m.any() else 1.0
    dn = np.clip(d[red_m] / max(d_p90, 1e-6), 0.0, 1.0)
    feats = dr.ink_features(img, W_d=r2.W_O_PX, mm_per_px=r2.px2mm(1.0, dpi), label=label,
                            grain_blur_sigma_px=r2.CAL["ink_grain_blur_sigma_px_at_ours"])
    return {"delta_e": delta_e_metrics(px),
            "delta_e_mask": delta_e_metrics(red_px, dn=dn),
            "features_vs_doubao": feats,
            "core_centroid_rgb": r2.rgb_mean(px)}


def window_metrics(img, core_w, mk_w, dpi, label):
    px = img[core_w].astype(np.float64)
    feats = dr.ink_features(img, W_d=r2.W_O_PX, mm_per_px=r2.px2mm(1.0, dpi), label=label,
                            grain_blur_sigma_px=r2.CAL["ink_grain_blur_sigma_px_at_ours"])
    red_m = mk_w["red"]
    d = cv2.distanceTransform(red_m.astype(np.uint8), cv2.DIST_L2, 3).astype(np.float64)
    d_p90 = float(np.percentile(d[red_m], 90.0)) if red_m.any() else 1.0
    dn = np.clip(d[red_m] / max(d_p90, 1e-6), 0.0, 1.0)
    dm = delta_e_metrics(px)
    return {"label": label, "delta_e": dm, "delta_e_mask": delta_e_metrics(img[red_m].astype(np.float64), dn=dn),
            "features_vs_doubao": feats,
            "key": {"dE2000_med": dm["delta_e2000"]["median"],
                    "dE_ab_med": dm["delta_e_ab"]["median"],
                    "L_wide_minus_thin": feats["semantic_lightness"]["L_wide_minus_thin"],
                    "L_vs_dn_slope": feats["semantic_lightness"]["L_vs_dn_slope"],
                    "translucency": feats["translucency"]["share_light_inside"],
                    "edge_px": feats["edge"]["transition_width_px_median"],
                    "grain_sigma": (feats["grain"] or {}).get("lum_highpass_sigma_2px") if feats.get("grain") else None}}


def pick_window(mk_r, win):
    return r2.pick_window(mk_r, win) if hasattr(r2, "pick_window") else _pick_window(mk_r, win)


def _pick_window(mk_r, win):
    h, w = mk_r["red"].shape
    win = int(min(win, w - 20, h - 20))
    win -= win % 2
    dens = cv2.boxFilter((mk_r["red"] | mk_r["white"]).astype(np.float32), -1, (win, win),
                         normalize=False, borderType=cv2.BORDER_CONSTANT)
    v = dens[win // 2:h - win // 2:4, win // 2:w - win // 2:4]
    if v.size == 0:
        return (slice(0, h), slice(0, w))
    iy, ix = np.unravel_index(int(np.argmax(v)), v.shape)
    cy, cx = int(iy) * 4 + win // 2, int(ix) * 4 + win // 2
    return (slice(cy - win // 2, cy + win // 2), slice(cx - win // 2, cx + win // 2))


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. 主流程
# ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t00 = time.time()
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    samples: dict = {}
    md5 = rp.source_jpeg_md5(r2.PDF, XREF)
    prod = json.loads(r2.PROD_READINGS.read_text())
    r1 = json.loads(r2.ROUND1_READINGS.read_text())
    assert md5 == prod["source"]["embedded_jpeg_md5"] == r1["source"]["embedded_jpeg_md5"]
    src300 = rp.load_scan(r2.PDF, XREF)
    print(f"[0] provenance ok; knobs={ACTIVE_KNOBS}; gamuts={[g['key'] for g in GAMUTS]}", flush=True)

    # ── 1) 色域档位读数（12mm 统计视野，600 与 2400 双 dpi）───────────────────────────
    paper_rows, paper_labels, paper_board = [], [], {}
    for g in GAMUTS:
        p600 = paper_patch("OBV", 600, TEX_FIELD_MM, g)
        p2400 = paper_patch("OBV", 2400, TEX_FIELD_MM, g)
        s600 = paper_patch("OBV", 600, TEX_STAT_FIELD_MM, g)
        s2400 = paper_patch("OBV", 2400, TEX_STAT_FIELD_MM, g)
        r6, r24 = r2.tex_readout(r2.paper_lum_res(s600), 600, TEX_STAT_FIELD_MM), \
            r2.tex_readout(r2.paper_lum_res(s2400), 2400, TEX_STAT_FIELD_MM)
        paper_board[g["key"]] = {"gamut": {k: g[k] for k in ("key", "label", "base", "min", "max",
                                                            "chroma_sigma", "amp_k", "amp_note", "source")},
                                 "measured_600": paper_metrics_ext(s600, g), "measured_2400": paper_metrics_ext(s2400, g),
                                 "readout_600": r6, "readout_2400": r24,
                                 "mm_consistency_2400_over_600": {
                                     "autocorr_x": r2._ratio(r24["autocorr_half_decay_mm"]["x"], r6["autocorr_half_decay_mm"]["x"]),
                                     "autocorr_y": r2._ratio(r24["autocorr_half_decay_mm"]["y"], r6["autocorr_half_decay_mm"]["y"]),
                                     "psd_centroid": r2._ratio(r24["psd_centroid_cyc_per_mm"], r6["psd_centroid_cyc_per_mm"]),
                                     "psd_peak_wavelength": r2._ratio(r24["psd_peak_wavelength_mm"], r6["psd_peak_wavelength_mm"])},
                                 "cross_dpi_2400_div4_vs_600": r2.cross_dpi_sim(s2400, s600)}
        m24 = paper_board[g["key"]]["measured_2400"]
        print(f"[gamut {g['key']}] rms={m24['rms_lum_0_255']} clip255={m24['clip255_share']} "
              f"floor={m24['clip_floor_share']} p10/50/90={m24['lum_p10_p50_p90']} mean={m24['mean_rgb']}", flush=True)

    # ── 2) 纸底对比板：各档 ×（600dpi ＋ 2400dpi 1:1）×（我们 ｜ 豆包裁块）逐行并排 ──
    assert DOUBAO_PAPER_IMG.is_file(), f"豆包参照图缺失：{DOUBAO_PAPER_IMG}（只读引用，不复制进仓）"
    dp = np.asarray(Image.open(DOUBAO_PAPER_IMG).convert("RGB"))
    pr = json.loads(DOUBAO_PAPER_JSON.read_text())["ruler"]
    bx, by, bw, bh = (int(v) for v in pr["seal_bbox_px"])       # [x, y, w, h]（印面外接框）
    side = 260
    pm = np.asarray(cc.ink_mask(dp.astype(np.float64)), bool)
    # 裁块取「印面右侧同高、紧邻印面」的纸底区（确定坐标；如含印泥像素则逐步左移/上移避开）
    doubao_crop, dc_org = None, None
    for dy in (0, 260, 520):
        for dx in (8, -8 - side, 260, -2 * side):
            cx, cy = bx + bw + dx, by + dy
            if cx < 0 or cy < 0 or cx + side > dp.shape[1] or cy + side > dp.shape[0]:
                continue
            if int(pm[cy:cy + side, cx:cx + side].sum()) == 0:
                doubao_crop, dc_org = dp[cy:cy + side, cx:cx + side].copy(), (cx, cy)
                break
        if doubao_crop is not None:
            break
    assert doubao_crop is not None, "豆包参照图上找不到无印泥的 260px 裁块"
    del pm
    rows_paper, labels_paper = [], []
    for g in GAMUTS:
        p600 = paper_patch("OBV", 600, TEX_FIELD_MM, g)
        p2400 = paper_patch("OBV", 2400, TEX_FIELD_MM, g)
        p600 = cv2.resize(p600, (side, side), interpolation=cv2.INTER_NEAREST)
        rows_paper.append([p600, p2400[:side, :side], doubao_crop])
        labels_paper.append(f"{g['key']}｜{g['label']}")
    samples["paper_board"] = r2.panel_grid(
        rows_paper, labels_paper, ["我们 600dpi 8mm", "我们 2400dpi 1:1 (8mm)", "豆包参照裁块"],
        SAMPLES_DIR / "P29-paper-gamut-board-round3.png", left_w=330)
    print(f"[board] {samples['paper_board']['size_px']} doubao_crop@{dc_org}", flush=True)

    # ── 3) 页面 @600dpi：掩膜 ＋ 豆包幅度纸底（整页）─────────────────────────────────
    src600 = rp.lanczos_up(src300, (SRC_W * 2, SRC_H * 2))
    src600_u8 = vs.to_u8(src600)
    mk = r2.page_masks(src300, COMP_DPI)
    H6, W6 = SRC_H * 2, SRC_W * 2
    print(f"[masks600] red={int(mk['red'].sum())} white={int(mk['white'].sum())} "
          f"paper_rule={int(mk['paper_rule'].sum())}", flush=True)
    core = cc.ink_core_centroid(src600_u8)
    core_mask = core["mask"]
    core_px_src = src600_u8[core_mask].astype(np.float64)
    print(f"[ink] core_px={int(core_mask.sum())} centroid={r2.rgb_mean(core_px_src)} "
          f"ΔE={cc.delta_e2000(r2.rgb_mean(core_px_src), cc.TARGET_RGB):.4f}", flush=True)

    # ── 4) 整页缩略：原 ｜ C2观感(生产色域) ｜ C3观感(推荐色域) ｜ C3观感(暖偏σ×4) ──
    page_variants, page_read = {}, {}
    page_plans = [("C2_aes", GAMUT_BY_KEY["PROD"], None),
                  ("C3_aes", GAMUT_BY_KEY[REC_KEY], dict(AES_CANDIDATES["C3_g050"]["knobs"])),
                  ("C3_aes", GAMUT_BY_KEY["W242chroma"], dict(AES_CANDIDATES["C3_g050"]["knobs"]))]
    for i, (mode, gam, knobs) in enumerate(page_plans):
        t = time.time()
        paper = (r2.paper_for(mode, H6, W6, COMP_DPI) if gam is None else paper_for_gamut(gam, H6, W6, COMP_DPI))
        with c3_operator(knobs or {"sem": 1.0, "edge_mm": 0.0, "edge_drop": 0.0}):
            v, rd = r2.run_variant(mode, src600, mk, COMP_DPI, paper, grain_sigma_add=None)
        tag = f"{mode}@{gam['key']}" if gam is not None else f"{mode}@PROD"
        page_variants[tag] = v
        page_read[tag] = {**rd, "gamut": gam["key"] if gam else "PROD(生产)"}
        del paper
        print(f"[page {tag}] {rd['elapsed_s']}s", flush=True)

    # ── 5) 2400dpi 局部 1:1：印面四联（原｜C2严格｜C2观感｜C3观感折半）＋ 旋钮扫描 ──
    grain_add = None
    reg2400: dict = {}
    for rn, box, win in (("P29-C1R1", C1_BBOX, 1400), ("P29-C2R1", C2_BBOX, 1300)):
        t = time.time()
        src_r = r2.source_region(src300, box, PROD_DPI)
        mk_r = r2.region_masks(src300, box, PROD_DPI)
        sl = pick_window(mk_r, win)
        srcw = src_r[sl]
        mk_w = {k: (v[sl] if isinstance(v, np.ndarray) and v.ndim == 2 and v.shape == mk_r["red"].shape
                    else v) for k, v in mk_r.items()}
        core_w = cc.ink_core_centroid(vs.to_u8(srcw))["mask"]
        ladder = (["C2_strict", "C2_aes", "C3_g100", "C3_g080", "C3_g050", "C3_g020", "C3_g000",
                   "C3_g050_noedge", "C3_g050_chromaedge"]
                  if rn == "P29-C1R1" else ["C2_strict", "C2_aes", "C3_g050"])
        panels, reads = [vs.to_u8(srcw)], {}
        p_mid = r2.paper_for("C2_aes", srcw.shape[0], srcw.shape[1], PROD_DPI)   # bg MID：各版共用同一纸底
        for name in ladder:
            if name.startswith("C3_"):
                knobs = dict(AES_CANDIDATES[name]["knobs"])
                with c3_operator(knobs):
                    v, rd = r2.run_variant("C3_aes", srcw, mk_w, PROD_DPI, p_mid, grain_sigma_add=grain_add)
            else:
                v, rd = r2.run_variant(name, srcw, mk_w, PROD_DPI, p_mid, grain_sigma_add=grain_add)
            panels.append(v)
            reads[name] = {**window_metrics(v, core_w, mk_w, PROD_DPI,
                                            AES_CANDIDATES[name]["label"] if name.startswith("C3_")
                                            else r2.VARIANTS[name]["label"]),
                           "ink_ops": rd.get("ink_ops"), "gamut": "PROD(生产，各版共用)"}
        if "C3_g100" in reads:                                # 等价性断言只在 C1R1 阶梯上做
            eq_bit = bool(np.array_equal(panels[ladder.index("C2_aes") + 1],
                                         panels[ladder.index("C3_g100") + 1]))
            reads["C3_g100"]["bit_equal_to_C2_aes"] = eq_bit
        del p_mid
        if rn == "P29-C1R1":
            four = [panels[0], panels[1], panels[2], panels[5]]   # 原｜C2严格｜C2观感｜C3观感(折半＋近边混纸)
            samples[f"{rn}_fourpanel_2400"] = r2.panel_grid(
                [four], [f"@{rn} 1:1"], ["①原 2400dpi", "②C2严格(靶色/保L*)", "③C2观感(语义全量)",
                                        "④C3观感(语义×0.5＋近边混纸)"],
                SAMPLES_DIR / f"{rn}-fourpanel-round3.png", left_w=250)
            rows2, labs2 = [], []
            for j, name in enumerate(ladder[2:], start=3):
                rows2.append([panels[0], panels[2], panels[j]])
                labs2.append(f"{name}｜{AES_CANDIDATES[name]['label']}")
            samples[f"{rn}_knobscan_2400"] = r2.panel_grid(
                rows2, labs2, ["原", "C2观感", "C3候选"],
                SAMPLES_DIR / f"{rn}-knobscan-round3.png", left_w=430)
        else:
            samples[f"{rn}_fourpanel_2400"] = r2.panel_grid(
                [[panels[0], panels[1], panels[2], panels[3]]], [f"@{rn} 1:1"],
                ["①原 2400dpi", "②C2严格(靶色/保L*)", "③C2观感(语义全量)", "④C3观感(语义×0.5＋近边混纸)"],
                SAMPLES_DIR / f"{rn}-fourpanel-round3.png", left_w=250)
        reg2400[rn] = {"window_px": [win, win], "window_mm": round(r2.px2mm(win, PROD_DPI), 3),
                       "window_origin_px": [int(sl[1].start), int(sl[0].start)],
                       "ink_readouts": reads,
                       "doubao_ink_reference": json.loads(r2.DOUBAO_INK.read_text())["features"],
                       "elapsed_s": round(time.time() - t, 1)}
        print(f"[2400 {rn}] done {time.time()-t:.1f}s", flush=True)
        del src_r, mk_r, mk_w, panels

    # ── 6) freeze/确定性断言（C3_g050 @C1R1 窗口）────────────────────────────────────
    box, win = C1_BBOX, 1400
    src_r = r2.source_region(src300, box, PROD_DPI)
    mk_r = r2.region_masks(src300, box, PROD_DPI)
    sl = pick_window(mk_r, win)
    srcw = src_r[sl]
    mk_w = {k: (v[sl] if isinstance(v, np.ndarray) and v.ndim == 2 and v.shape == mk_r["red"].shape
                else v) for k, v in mk_r.items()}
    paper_w = r2.paper_for("C2_aes", srcw.shape[0], srcw.shape[1], PROD_DPI)   # 与印面阶梯同一纸底（bg MID）
    knobs = dict(AES_CANDIDATES["C3_g050"]["knobs"])
    with c3_operator(knobs):
        v, _ = r2.run_variant("C3_aes", srcw, mk_w, PROD_DPI, paper_w)
        v2, _ = r2.run_variant("C3_aes", srcw, mk_w, PROD_DPI, paper_w)
        ref, _ = r2.run_variant("C3_aes", srcw, mk_w, PROD_DPI, paper_w, ink_ops_on=False)
    d_out = int(((v != ref) & (~mk_w["red"])[:, :, None]).sum())
    d_white = int(((v != ref) & mk_w["white"][:, :, None]).sum())
    freeze_c3 = {"rule": "结构算子只写红墨区；白线区/掩膜外 对观感基线逐像素差=0",
                 "white_line_mismatch_px": d_white, "outside_mismatch_px": d_out,
                 "assert_ok": bool(d_white == 0 and d_out == 0),
                 "determinism_rerun_bit_equal": bool(np.array_equal(v, v2))}
    del src_r, mk_r, mk_w, v, v2, ref, paper_w

    # ── 7) 等价性断言（C3_g100 vs C2_aes 逐位一致）＋ 观感档读数落盘 ────────────────
    samples_meta = {"freeze_C3_g050_C1R1": freeze_c3,
                    "equivalence_bit_equal_C3_g100_vs_C2_aes":
                        reg2400["P29-C1R1"]["ink_readouts"]["C3_g100"]["bit_equal_to_C2_aes"],
                    "equivalence_note": ("C3_g100（sem=1.0/edge关）在 C1R1 窗口与 C2_aes 逐位一致 ⇒ "
                                         "ink_chroma_c3 是 ink_chroma_v3 的严格参数化超集")}

    # ── 8) 整页缩略拼板 ─────────────────────────────────────────────────────────────
    th = (THUMB_W, round(H6 * THUMB_W / W6))
    def _thumb(a):
        return np.asarray(Image.fromarray(a).resize(th, Image.Resampling.LANCZOS))
    thumbs = [_thumb(src600_u8), _thumb(page_variants["C2_aes@PROD"]),
              _thumb(page_variants[f"C3_aes@{REC_KEY}"]), _thumb(page_variants["C3_aes@W242chroma"])]
    samples["thumb"] = r2.panel_grid(
        [thumbs], ["@整页800px"], ["①原(600dpi)", "②C2观感·生产色域",
                                   f"③C3观感·{REC_KEY}(豆包暖白/下限242)",
                                   "④C3观感·W242chroma(暖偏σ×4)"],
        SAMPLES_DIR / "P29-thumb-round3.png", left_w=150)

    # ── 9) 豆包对照汇总 ＋ 读数落盘 ──────────────────────────────────────────────────
    P = json.loads(DOUBAO_PAPER_JSON.read_text())
    doubao_paper_ref = {"mean_rgb": P["paper_color"]["mean_rgb"], "lum_deciles": P["paper_color"]["lum_deciles"],
                        "p10_p50_p90": [P["paper_color"]["lum_deciles"][2], P["paper_color"]["lum_deciles"][4],
                                        P["paper_color"]["lum_deciles"][6]],
                        "texture_rms_0_255": P["paper_texture"]["texture_rms_0_255_median"],
                        "p5_rgb": P["paper_color"]["p5_p95_rgb"][0],
                        "min_rgb": P["paper_color"]["min_rgb"],
                        "note": "豆包参照裁块只作视觉并排；数值对照以 doubao-reference-features.json 为准"}
    readings = {
        "schema": "feicui.variant-samples.readings-round3.v1",
        "generator": "ops/variant-samples/round3_samples.py",
        "page": PAGE,
        "intent": "C3：①纸底色域参数化（下限×基色两旋钮，幅度一律豆包标定 RMS 3.593；不改生产常量）"
                  "②观感档做实（语义折半 sem=0.5、近边色度软化、半透 1.56%、边缘 5.65px）"
                  "③ΔE 双口径（逐像素 ΔE2000 ＋ a*/b* 色度分量 ΔE ＋ 按浓度分层）",
        "knobs": {"defaults": KNOB_DEFAULTS, "active": dict(ACTIVE_KNOBS),
                  "candidates": {k: v["knobs"] for k, v in AES_CANDIDATES.items()},
                  "env_override": "FEICUI_C3_KNOBS"},
        "gamut_candidates": paper_board,
        "gamut_recommendation_basis": {
            "doubao_target": doubao_paper_ref,
            "criteria": ["纸底 RMS → 3.593（截顶后仍达标）", "255 截顶占比 ≤ 豆包（豆包 p90 即 255）",
                         "亮度 p10 → 243（豆包实测）；p50/p90 不塌", "mean RGB → 豆包暖白 [253.1,248.9,247.8]",
                         "600/2400 dpi 对齐比值 ≈1", "下限截顶占比（新档特有的平坦化风险）"],
            "production_note": "生产常量本轮未动；定档后另行评估「改 seal_canvas.BG_* vs 整页线单独一套色域」"},
        "source": {"pdf": str(r2.PDF.relative_to(REPO)), "xref": XREF, "embedded_jpeg_md5": md5,
                   "matches_production_and_round1": True, "size_px": [SRC_W, SRC_H], "dpi": SCAN_DPI},
        "geometry": {"compare_dpi": COMP_DPI, "prod_dpi": PROD_DPI,
                     "ours_ruler": {"W_o_px": r2.W_O_PX, "W_o_mm": r2.W_O_MM}},
        "masks_600dpi": {"red_ink_px": int(mk["red"].sum()), "white_line_px": int(mk["white"].sum()),
                         "outside_px": int(mk["outside"].sum()), "paper_rule_px": int(mk["paper_rule"].sum()),
                         "note": "纸底类像素＝rp.build_masks（gray≥210 ∧ sat≤0.15）；文字/框线/印泥在掩膜外，一字未动"},
        "page_variants": page_read,
        "region_2400_1to1": reg2400,
        "assertions": samples_meta,
        "samples": samples,
        "elapsed_s": round(time.time() - t00, 1),
    }
    READINGS_PATH.write_text(json.dumps(readings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = freeze_c3["assert_ok"] and freeze_c3["determinism_rerun_bit_equal"] \
        and reg2400["P29-C1R1"]["ink_readouts"]["C3_g100"]["bit_equal_to_C2_aes"]
    print(json.dumps({"ok": ok, "freeze": freeze_c3, "elapsed_s": readings["elapsed_s"]},
                     ensure_ascii=False, indent=2), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
