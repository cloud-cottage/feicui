#!/usr/bin/env python
"""纹理「物理尺度」不变性判据（Kevin 2026-10-16 指令：纹理按 mm 定义，随目标 dpi 换算）。

判据（同一物理尺度在 1200 / 2400 两个 dpi 下必须一致）——三条一起看，全在**同一物理坐标**上取：
  ① **同一物理位置的纹理值**：两个 dpi 各按「物理位置 ⇒ 虚拟像素索引」求值 ⇒ 逐点一致
     （pearson_r ≥ 0.9999 且 rms 差 ≈0）；
  ② **自相关（共栅格）**：在**同一 mm 栅格**上算自相关 —— 半衰长度 / 积分相关长度换算成 mm 后一致；
  ③ **共带谱质心**：公共物理频带 0.5–20 cyc/mm（两个 dpi 都能表示）内的谱质心一致。
另附**旧像素常量（66 / 7 px 写死）的反例对照**：同一物理位置的值 + mm 尺度**双向判负**。

为什么要「物理位置 ⇒ 虚拟索引」：像素中心在 `(i+0.5)/dpi` 英寸处，直接拿 `fine[::2]` 与 `coarse`
对比会带**半像素相位差**（实测 r 只有 0.80）—— 那是取样相位，不是纹理尺度。按物理坐标求值可消掉它。

做法：直接调 `ops/book-page-2400/render_page_2400.py` 的**同一份**纹理实现（`_fiber_lattice`，
**不复制**），只改 `configure_geometry()` 的目标 dpi。

用法：./venv/bin/python ops/book-page-2400/probe_texture_mm_invariance.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
RENDER = REPO / "ops" / "book-page-2400" / "render_page_2400.py"
OUT = REPO / "ops" / "book-page-2400" / "readings-texture-mm-invariance.json"
COARSE, FINE = 1200, 2400         # 粗 / 细采样 dpi
WINDOW_MM = 20.0                  # 物理窗口（mm）—— 长轴 0.6986 mm ⇒ 28.6 个晶格；短轴 ⇒ 270 个
N_SAMPLES = 2048                  # 窗口内采样点数（两个 dpi 用同一物理栅格 ⇒ 可直接逐点比）
GRID_MM = 2.0                     # 2-D「同一物理位置」栅格边长（mm）
GRID_N = 256
TOL_REL = 0.02                    # 共栅格 mm 尺度判定容差（2%：同一物理栅格上应几乎恒等）
TOL_CENTROID_REL = 0.05           # 共带谱质心容差（5%）
MIN_CORR = 0.9999                 # 同一物理位置纹理值的相关度下限


def load_render_module():
    """按**文件路径**载入 render_page_2400.py。

    ★ 必须先注册进 `sys.modules` 再 `exec_module` —— 该模块带 `@dataclass`，
    `dataclasses` 靠 `sys.modules[cls.__module__]` 解析注解，未注册会 AttributeError（本仓 P0 教训）。
    """
    name = "feicui_render_page_2400_probe"
    spec = importlib.util.spec_from_file_location(name, RENDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def at_physical(rp, dpi: int, xs_mm: np.ndarray, ys_mm: np.ndarray) -> np.ndarray:
    """在**物理坐标** (xs_mm × ys_mm) 上求纤维晶格值（对任何 dpi 都该是同一个场）。

    像素中心位于 `(i+0.5)/dpi` 英寸 ⇒ 反解「该 dpi 下的虚拟像素索引」`i = x_mm/25.4*dpi − 0.5`，
    再交给 `_fiber_lattice`（它内部仍按 `(i+0.5)/cell_px` 换算 ⇒ 等价于 `x_mm/cell_mm`）。
    """
    cols = np.asarray(xs_mm, dtype=np.float64) / 25.4 * dpi - 0.5
    rows = np.asarray(ys_mm, dtype=np.float64) / 25.4 * dpi - 0.5
    return rp._fiber_lattice(rows, cols, rp.BG_SEED)


def acf_profile(profile: np.ndarray) -> np.ndarray:
    p = np.asarray(profile, dtype=np.float64)
    p = p - p.mean()
    n = p.size
    f = np.fft.rfft(p, n=2 * n)
    acf = np.fft.irfft(np.abs(f) ** 2, n=2 * n)[: n]
    return acf / acf[0]


def acf_stats_mm(profile: np.ndarray, step_mm: float) -> dict:
    """自相关读数（输入＝等距 mm 栅格上的剖面 ⇒ 长度一律 mm）。"""
    acf = acf_profile(profile)

    def crossing(level):
        below = np.where(acf <= level)[0]
        if not below.size:
            return float("nan")
        i = int(below[0])
        lag = float(i)
        if i > 0 and acf[i - 1] != acf[i]:
            lag = (i - 1) + (acf[i - 1] - level) / (acf[i - 1] - acf[i])
        return lag * step_mm
    nonpos = np.where(acf <= 0.0)[0]
    cut = int(nonpos[0]) if nonpos.size else acf.size
    return {"half_decay_mm": round(crossing(0.5), 6),
            "corr_len_mm": round(float(acf[:cut].sum()) * step_mm, 6),
            "z0_mm": round(crossing(0.0), 6) if nonpos.size else None}


def band_centroid(profile: np.ndarray, step_mm: float, band=(0.5, 20.0)) -> dict:
    """公共物理频带内的谱质心（cycles/mm）与其波长（mm）。"""
    p = np.asarray(profile, dtype=np.float64)
    p = p - p.mean()
    n = p.size
    ps = np.abs(np.fft.rfft(p)) ** 2
    f = np.fft.rfftfreq(n, d=step_mm)          # cyc/mm（栅格步长＝mm ⇒ 直接是物理频率）
    m = (f >= band[0]) & (f <= band[1])
    c = float((f[m] * ps[m]).sum() / ps[m].sum()) if ps[m].sum() > 0 else float("nan")
    pk = ps[m].max() if m.any() else 0.0
    half = float(f[m][np.argmax(ps[m] <= 0.5 * pk)]) if (m.any() and pk > 0) else float("nan")
    return {"band_cyc_per_mm": list(band), "centroid_cyc_per_mm": round(c, 6),
            "centroid_wavelength_mm": round(1 / c, 6) if c else None,
            "half_power_cyc_per_mm": round(half, 6) if half == half else None,
            "half_power_wavelength_mm": round(1 / half, 6) if (half == half and half > 0) else None}


def rel(x, y):
    return float(abs(x - y) / abs(y)) if (y not in (0, None) and y == y) else None


def main() -> int:
    t0 = time.time()
    rp = load_render_module()
    xs = np.linspace(0.0, WINDOW_MM, N_SAMPLES + 1)[:-1]
    step_mm = WINDOW_MM / N_SAMPLES
    fixed_y = 7.3                      # 任取一个非特殊位置的 mm 值（横剖面固定行）
    fixed_x = 5.1
    gx = np.linspace(0.0, GRID_MM, GRID_N)
    gy = np.linspace(0.0, GRID_MM, GRID_N)

    geo = {}
    lat = {}
    for tag, dpi in (("coarse_1200", COARSE), ("fine_2400", FINE)):
        g = rp.configure_geometry(dpi, 2125, 3059)
        geo[tag] = {"fiber_cell_px": [round(rp.FIBER_CELL_LONG, 6), round(rp.FIBER_CELL_SHORT, 6)],
                    "fiber_cell_mm": [rp.FIBER_CELL_LONG_MM, rp.FIBER_CELL_SHORT_MM],
                    "halo_band_out_px": rp.HALO_BAND_OUT_PX, "halo_band_mm": rp.HALO_BAND_MM,
                    "upsample_factor": rp.UP, "out_px": g["out_px"], "target_dpi": g["target_dpi"]}
        lat[tag] = {
            "x_line": at_physical(rp, dpi, xs, np.array([fixed_y]))[0],
            "y_line": at_physical(rp, dpi, np.array([fixed_x]), xs)[:, 0],
            "grid2d": at_physical(rp, dpi, gx, gy),
        }

    # ---- 反例：旧像素常量（66 / 7 px 写死，不随 dpi 换算）在 1200 dpi 的网格上 ----
    saved = (rp.FIBER_CELL_LONG, rp.FIBER_CELL_SHORT)
    rp.FIBER_CELL_LONG, rp.FIBER_CELL_SHORT = 66.0, 7.0
    old = {
        "x_line": at_physical(rp, COARSE, xs, np.array([fixed_y]))[0],
        "y_line": at_physical(rp, COARSE, np.array([fixed_x]), xs)[:, 0],
        "grid2d": at_physical(rp, COARSE, gx, gy),
    }
    rp.FIBER_CELL_LONG, rp.FIBER_CELL_SHORT = saved

    def agree(a: np.ndarray, b: np.ndarray) -> dict:
        d = a.ravel() - b.ravel()
        return {"n": int(a.size), "pearson_r": round(float(np.corrcoef(a.ravel(), b.ravel())[0, 1]), 8),
                "rms_diff": round(float(np.sqrt((d ** 2).mean())), 9),
                "max_abs_diff": round(float(np.abs(d).max()), 9),
                "rms_of_reference": round(float(a.std()), 6)}

    same_place = {
        "lattice_2d": agree(lat["fine_2400"]["grid2d"], lat["coarse_1200"]["grid2d"]),
        "x_line": agree(lat["fine_2400"]["x_line"], lat["coarse_1200"]["x_line"]),
        "y_line": agree(lat["fine_2400"]["y_line"], lat["coarse_1200"]["y_line"]),
    }
    counter = {
        "lattice_2d": agree(lat["fine_2400"]["grid2d"], old["grid2d"]),
        "x_line": agree(lat["fine_2400"]["x_line"], old["x_line"]),
        "y_line": agree(lat["fine_2400"]["y_line"], old["y_line"]),
    }

    acf = {ax: {"mm_defined": {t: acf_stats_mm(lat[t][f"{ax}_line"], step_mm)
                               for t in ("coarse_1200", "fine_2400")},
                "old_pixel_constants_coarse_1200": acf_stats_mm(old[f"{ax}_line"], step_mm)}
           for ax in ("x", "y")}
    spec = {ax: {"mm_defined": {t: band_centroid(lat[t][f"{ax}_line"], step_mm)
                                for t in ("coarse_1200", "fine_2400")},
                 "old_pixel_constants_coarse_1200": band_centroid(old[f"{ax}_line"], step_mm)}
            for ax in ("x", "y")}

    checks: dict[str, dict] = {}
    checks[f"phys_same_place_lattice_corr_ge_{MIN_CORR}"] = {
        "pearson_r": same_place["lattice_2d"]["pearson_r"], "threshold": MIN_CORR,
        "rms_diff": same_place["lattice_2d"]["rms_diff"],
        "pass": bool(same_place["lattice_2d"]["pearson_r"] >= MIN_CORR)}
    for ax in ("x", "y"):
        for metric in ("half_decay_mm", "corr_len_mm"):
            c, f = acf[ax]["mm_defined"]["coarse_1200"][metric], acf[ax]["mm_defined"]["fine_2400"][metric]
            v = rel(c, f)
            checks[f"acf_{ax}_{metric}_equal"] = {
                "1200": c, "2400": f, "rel_diff": round(v, 6) if v is not None else None,
                "pass": bool(v is not None and v <= TOL_REL)}
        c = spec[ax]["mm_defined"]["coarse_1200"]["centroid_cyc_per_mm"]
        f = spec[ax]["mm_defined"]["fine_2400"]["centroid_cyc_per_mm"]
        v = rel(c, f)
        checks[f"spectral_centroid_{ax}_cyc_per_mm_equal"] = {
            "1200": c, "2400": f, "rel_diff": round(v, 6) if v is not None else None,
            "pass": bool(v is not None and v <= TOL_CENTROID_REL)}

    counterexample = {
        "note": ("旧实现把晶格写死成像素常量（长轴 66 px / 短轴 7 px，与 dpi 无关）—— 在 1200 dpi 的网格上"
                 "直接沿用 ⇒ **同一物理位置的值**与**同一物理尺度**两处都不成立"),
        "old_px_constants": {"long": 66, "short": 7},
        "phys_same_place_vs_2400": counter,
        "mm_scale_old": {str(d): {"long_mm": round(66 / d * 25.4, 6), "short_mm": round(7 / d * 25.4, 6)}
                         for d in (COARSE, FINE)},
        "mm_scale_rel_diff_long": rel(66 / COARSE * 25.4, 66 / FINE * 25.4),
        "mm_scale_rel_diff_short": rel(7 / COARSE * 25.4, 7 / FINE * 25.4),
    }
    counterexample["judged_negative"] = bool(
        counter["lattice_2d"]["pearson_r"] < MIN_CORR
        and counterexample["mm_scale_rel_diff_long"] > TOL_REL)

    rp.configure_geometry(rp.DPI_DEFAULT, 2125, 3059)     # 还原缺省几何
    out = {
        "schema": "feicui.book-page-2400.texture-mm-invariance.v3",
        "task": "Kong：纹理按 mm 物理尺度定义、随目标 dpi 换算（Kevin 2026-10-16）",
        "generator": "ops/book-page-2400/probe_texture_mm_invariance.py",
        "impl_source": "ops/book-page-2400/render_page_2400.py（_fiber_lattice，同一份实现，不复制）",
        "method": ("两 dpi 一律在**同一物理栅格**上求值（物理 mm ⇒ 该 dpi 的虚拟像素索引，"
                   "消掉半像素取样相位）⇒ 逐点比较 / 同栅格自相关 / 共带谱质心"),
        "window_mm": WINDOW_MM, "n_samples": N_SAMPLES, "grid_mm": GRID_MM, "grid_n": GRID_N,
        "dpi_pair": [COARSE, FINE],
        "tolerances": {"mm_scale_rel": TOL_REL, "centroid_rel": TOL_CENTROID_REL,
                       "min_pearson_r": MIN_CORR, "centroid_band_cyc_per_mm": [0.5, 20.0]},
        "geometry": geo,
        "phys_same_place": same_place, "acf": acf, "spectrum": spec,
        "checks": checks, "counterexample_old_pixel_constants": counterexample,
        "all_ok": bool(all(c["pass"] for c in checks.values()) and counterexample["judged_negative"]),
        "observations": {
            "grain": ("细颗粒是**逐像素**位置哈希白噪（σ=0.85），不是 mm 定义的纹理 ⇒ 两个 dpi 下都是约 1 px，"
                      "其 mm 尺度必然随 dpi 变（「按像素定义」的固有属性，非本单改动对象；本轮**未改**）"),
            "halo": "晕染环带同样 mm 化（HALO_BAND_MM=0.169333 mm ⇒ 1200dpi 8 px / 2400dpi 16 px）",
            "render_grid_acf": ("按各自渲染像素栅格直接量自相关（不做物理坐标对齐）会带取样相位/栅格效应，"
                                "长轴换算成 mm 后差 5–7% —— 那是取样效应，故判据取同物理栅格口径"),
        },
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"readings": str(OUT), "checks": checks,
                      "counterexample": {k: counterexample[k] for k in
                                         ("phys_same_place_vs_2400", "mm_scale_old",
                                          "mm_scale_rel_diff_long", "judged_negative")},
                      "all_ok": out["all_ok"]}, ensure_ascii=False, indent=2))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
