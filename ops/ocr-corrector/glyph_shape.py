#!/usr/bin/env python
"""ops/ocr-corrector · 字形相似度（**本地字体栅格代理**，纯 PIL + numpy）。

★ 诚实声明（写进交付口径，不得省略）：
   - 本地**没有** IDS / 部首 / Unihan 数据库（实测 2026-10-16：`venv` 与 `~/.hermes` 下
     搜 `*unihan*` / `*ids*.txt` 零命中），且本线**不许联网**下载 ⇒ 「按 IDS 部件」这条路
     在本环境**不可行**。替代方案＝用**本机字体**把字栅格化，比整字 IoU/NCC 与四象限 IoU
     作**形近代理**。
   - 字体是 **黑体（STHeiti Light / Heiti TC）**，不是篆书 ⇒ 该分数对**篆书字形**只有很弱的
     指示性。它只用来**给候选排序**（供人挑），**不得**当成「这两个字在古玺里同形」的证据。
   - 因此由本模块产生的所有映射一律 `source=font_glyph_shape`、`confidence<=0.5`、
     `verified=false`（`validate_map` 强制）。

跑法（自测 / 打印一组示例分数）：
    ./venv/bin/python ops/ocr-corrector/glyph_shape.py --selftest
    ./venv/bin/python ops/ocr-corrector/glyph_shape.py --pairs 錄鈢,團圖,干王
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

#: 本机可用的 CJK 字体（第一个能渲染出笔画的即用；实测 Songti.ttc index 0 渲不出）
FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)
GLYPH_SIZE = 64
INK_THRESHOLD = 40          # 灰度 > 此值算「墨」


def load_font(size: int = 128, index: int = 0, path: str | None = None) -> tuple[ImageFont.FreeTypeFont, str]:
    cands = (path,) if path else FONT_CANDIDATES
    last_err = None
    for p in cands:
        try:
            f = ImageFont.truetype(p, size, index=index)
        except Exception as e:  # pragma: no cover
            last_err = e
            continue
        im = Image.new("L", (size + 32, size + 32), 0)
        ImageDraw.Draw(im).text((16, 16), "錄", font=f, fill=255)
        if np.array(im).max() > 0:
            return f, p
        last_err = RuntimeError(f"{p} 渲染为空白")
    raise RuntimeError(f"没有可用 CJK 字体: {last_err}")


def glyph_raster(ch: str, font: ImageFont.FreeTypeFont, size: int = GLYPH_SIZE) -> np.ndarray:
    """把单个字渲染成 `size×size` 的灰度阵（紧贴 bbox 裁剪后等比补方再缩放）。"""
    big = 128
    im = Image.new("L", (big * 3, big * 3), 0)
    ImageDraw.Draw(im).text((big, big), ch, font=font, fill=255)
    a = np.array(im)
    ys, xs = np.nonzero(a > INK_THRESHOLD)
    if len(ys) == 0:
        return np.zeros((size, size), dtype=np.uint8)
    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    crop = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    side = max(h, w)
    canvas = np.zeros((side, side), dtype=np.uint8)
    canvas[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = crop
    return np.array(Image.fromarray(canvas).resize((size, size), Image.BILINEAR), dtype=np.uint8)


def _binary(g: np.ndarray) -> np.ndarray:
    return g > INK_THRESHOLD


def iou(a: np.ndarray, b: np.ndarray) -> float:
    ma, mb = _binary(a), _binary(b)
    u = int(np.logical_or(ma, mb).sum())
    if u == 0:
        return 0.0
    return float(np.logical_and(ma, mb).sum()) / u


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    x = a.astype(np.float64) - float(a.mean())
    y = b.astype(np.float64) - float(b.mean())
    d = float(np.sqrt((x * x).sum()) * np.sqrt((y * y).sum()))
    if d == 0:
        return 0.0
    return float((x * y).sum() / d)


def quadrant_iou(a: np.ndarray, b: np.ndarray) -> float:
    """四象限 IoU 均值 —— **部首/部件位置的粗略代理**（不是真 IDS 分解）。"""
    h, w = a.shape
    parts = []
    for i in range(2):
        for j in range(2):
            sl = (slice(i * h // 2, (i + 1) * h // 2), slice(j * w // 2, (j + 1) * w // 2))
            parts.append(iou(a[sl], b[sl]))
    return float(sum(parts) / len(parts))


class GlyphShape:
    """同一字多次查询时缓存栅格（避免重复渲染）。"""

    def __init__(self, size: int = GLYPH_SIZE, font_path: str | None = None) -> None:
        self.font, self.font_path = load_font(index=0, path=font_path)
        self.font_name = " ".join(str(x) for x in self.font.getname())
        self.size = size
        self._cache: dict[str, np.ndarray] = {}

    def raster(self, ch: str) -> np.ndarray:
        if ch not in self._cache:
            self._cache[ch] = glyph_raster(ch, self.font, self.size)
        return self._cache[ch]

    def compare(self, a: str, b: str) -> dict[str, float]:
        ga, gb = self.raster(a), self.raster(b)
        i, n, q = iou(ga, gb), ncc(ga, gb), quadrant_iou(ga, gb)
        return {
            "glyph_iou": round(i, 4),
            "glyph_ncc": round(n, 4),
            "glyph_quad_iou": round(q, 4),
            # 形近代理综合分（单纯算术平均，无魔法权重）
            "glyph_sim": round((i + n) / 2.0, 4),
        }

    @property
    def meta(self) -> dict[str, object]:
        return {
            "font_path": self.font_path,
            "font_name": self.font_name,
            "glyph_size": self.size,
            "ink_threshold": INK_THRESHOLD,
            "metrics": ["glyph_iou", "glyph_ncc", "glyph_quad_iou", "glyph_sim"],
            "caveat": "黑体栅格代理，非篆书；仅用于候选排序，不作为同形证据",
            "ids_available": False,
            "ids_note": "本地无 IDS/部首/Unihan 数据，且本线不许联网 ⇒ 部件级分解不可用",
        }


def _selftest() -> int:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ok   {name}")
        else:
            fail += 1
            print(f"  FAIL {name} {detail}")

    gs = GlyphShape()
    print(f"[glyph] font={gs.font_name} ({gs.font_path})")
    check("自身比较 = 1.0", gs.compare("錄", "錄")["glyph_iou"] == 1.0)
    check("对称性", gs.compare("錄", "鈢") == gs.compare("鈢", "錄"))
    d1 = gs.compare("錄", "鈢")["glyph_sim"]
    d2 = gs.compare("錄", "圖")["glyph_sim"]
    print(f"[glyph] 錄-鈢 sim={d1}  錄-圖 sim={d2}")
    check("相似度为有限数且落在 [0,1]", all(
        0.0 <= v <= 1.0 for v in gs.compare("錄", "圖").values()))
    check("确定性（同参数两次结果相同）", gs.compare("錄", "鈢") == gs.compare("錄", "鈢"))
    check("空白字（ASCII 空格）不崩", gs.compare(" ", "錄")["glyph_iou"] >= 0.0)
    print(f"[glyph] meta={gs.meta}")
    print(f"[selftest] {ok} passed, {fail} failed")
    return 0 if fail == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="字形相似度（本地字体栅格代理）")
    ap.add_argument("--pairs", default="", help="逗号分隔的二字对，如 錄鈢,團圖")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    gs = GlyphShape()
    print(f"font = {gs.font_name} ({gs.font_path})  ⚠ 黑体代理，非篆书")
    for pair in [p for p in a.pairs.split(",") if p]:
        if len(pair) != 2:
            print(f"  skip 非法字对 {pair!r}（需恰 2 字）")
            continue
        print(f"  {pair[0]} ↔ {pair[1]}: {gs.compare(pair[0], pair[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
