#!/usr/bin/env python3
"""PP-10 / 第 7 项：**边款绿框是否真的渲染** —— 对截图做确定性像素判定（非 LLM 目视）。

判据：产品默认样式的框边色是
  * stamp（印章）＝ `--danger`  → `rgb(255,115,133)` ＝ `#FF7385`
  * edge （边款）＝ `--accent`  → `rgb(47,214,160)`  ＝ `#2FD6A0`
（真源：`web/src/pages/JobDetailPage.vue` 的 `.pv-box--stamp / .pv-box--edge` 的 border-color
＋ `web/src/styles/base.css` 的 token —— 本脚本只**数像素**，不猜。）

做法：对截图逐像素按 BGR 欧氏距离找**贴近这两种边框色**的像素，再做连通域，
报每种色的像素总数、连通域数（≈框的条数 / 边段数）与整体外接框 —— 绿像素存在且成条
⇒ 绿框**确实画进了截图像素**（排除「只是 CSS 里设了色、实际没画」）。

只读截图；结果走 stdout（由调用方重定向到 box_visibility.json 的 pixel 段）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

# 产品 token 的 BGR（OpenCV 读入即 BGR）：#FF7385 / #2FD6A0
BORDERS = {
    "stamp_danger_FF7385": (0x85, 0x73, 0xFF),
    "edge_accent_2FD6A0": (0xA0, 0xD6, 0x2F),
}
TOL = 40  # 允许抗锯齿 / 缩放的色偏


def main() -> int:
    png = Path(sys.argv[1]).resolve()
    img = cv2.imread(str(png), cv2.IMREAD_COLOR)
    if img is None:
        print(json.dumps({"error": f"读不出 PNG：{png}"}, ensure_ascii=False))
        return 2
    H, W = img.shape[:2]
    out = {"png": png.name, "size": [W, H], "tol": TOL, "colors": {}}
    for name, bgr in BORDERS.items():
        diff = np.linalg.norm(img.astype(np.int16) - np.array(bgr, np.int16), axis=2)
        mask = (diff <= TOL).astype(np.uint8)
        n = int(cv2.countNonZero(mask))
        n_lab, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
        comps = sorted(
            (
                {
                    "area": int(stats[i, cv2.CC_STAT_AREA]),
                    "bbox_xywh": [int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                                  int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])],
                }
                for i in range(1, n_lab)
            ),
            key=lambda d: d["area"], reverse=True,
        )
        ys, xs = np.nonzero(mask)
        out["colors"][name] = {
            "pixel_count": n,
            "component_count": n_lab - 1,
            "overall_bbox_xywh": (
                [int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())]
                if n else None
            ),
            "top_components": comps[:12],
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
