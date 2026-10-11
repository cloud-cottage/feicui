#!/usr/bin/env python3
"""E9/E10 框与图上红印面的**几何对齐量测**（PP-3 的机械判据）—— Kong 2026-10-11。

做法：拿浏览器里量到的**覆盖层框**（`.pv-box` 的 `getBoundingClientRect` 换算回图像像素空间）与
E9 那张 PNG（`ops/page-preview/e9_p13_dpi110.png`，与页面加载的是同一 URL ⇒ 同一字节）做对照：

  * 对每个 **stamp 框**，在 PNG 上算「红掩膜（与 `processor.detect_stamp_regions` 同一 HSV 区间）」
    在该框内的覆盖率，与**全页基线覆盖率**比较 —— 框若真的落在红印面上，覆盖率应显著高于基线；
  * 额外给「框内红像素质心」相对框中心的偏移（归一化到框短边），越小越说明框扣在印面上；
  * **edge 框**不做红色断言（边款＝黑为主），只报其暗像素占比（与 `detect_edge_inscriptions`
    的 `dark_ratio` 同口径：gray<80 占比）。

只读：本脚本只读 PNG 与 JSON，不写库、不落盘（输出走 stdout）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HSV_LOW = np.array([0, 120, 70])
HSV_HIGH = np.array([10, 255, 255])


def red_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, HSV_LOW, HSV_HIGH)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def main() -> int:
    # 路径一律先 `.resolve()` 成绝对路径：`relative_to(ROOT)` 在**相对** argv 上会抛
    # ValueError（`Path('ops/page-preview/x.png').relative_to(ABS_ROOT)`）—— 上一轮即因此崩在
    # 写 `alignment_check_p13.json` 之前（落了 0 字节）。默认值本就是绝对的，此处统一。
    png = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ops/page-preview/e9_p13_dpi110.png").resolve()
    boxes_json = (
        Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "ops/page-preview/browser_boxes_5195_p13.json"
    ).resolve()
    img = cv2.imread(str(png), cv2.IMREAD_COLOR)
    if img is None:
        print(json.dumps({"error": f"读不出 PNG：{png}"}, ensure_ascii=False))
        return 2
    H, W = img.shape[:2]
    boxes = json.loads(Path(boxes_json).read_text(encoding="utf-8"))["boxes"]
    mask = red_mask(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    base = float(cv2.countNonZero(mask)) / float(H * W)

    rows = []
    stamp_int_boxes = []  # 供下面的「框外残留红」统计复用（同一套取整坐标）
    for b in boxes:
        x1, y1, x2, y2 = (int(round(float(b["imgSpace"][k]))) for k in ("x1", "y1", "x2", "y2"))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W, x2), min(H, y2)
        sub = mask[y1:y2, x1:x2]
        area = max(sub.shape[0] * sub.shape[1], 1)
        cov = float(cv2.countNonZero(sub)) / area
        row = {
            "kind": b["cls"].split("--")[-1],
            "imgSpace": [x1, y1, x2, y2],
            "red_coverage_in_box": round(cov, 4),
            "red_coverage_page_baseline": round(base, 4),
            "ratio_in_box_over_baseline": round(cov / base, 1) if base > 0 else None,
        }
        if "stamp" in b["cls"]:
            ys, xs = np.nonzero(sub)
            if len(xs):
                cx, cy = float(xs.mean()) + x1, float(ys.mean()) + y1
                bcx, bcy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                short = max(min(x2 - x1, y2 - y1), 1)
                row["red_centroid_offset_norm"] = round(
                    float(((cx - bcx) ** 2 + (cy - bcy) ** 2) ** 0.5) / short, 4
                )
            else:
                row["red_centroid_offset_norm"] = None
        else:
            dk = np.count_nonzero(gray[y1:y2, x1:x2] < 80) / area
            row["dark_pixel_ratio_in_box"] = round(float(dk), 4)
        rows.append(row)
        if "stamp" in b["cls"]:
            stamp_int_boxes.append((x1, y1, x2, y2))

    # ── 框外残留红（「框外是否还有大片红」＝有无**漏检印章**）────────────────────────────
    # 整页红掩膜 － 落在任一 stamp 框内的红 ⇒ 未被任何框覆盖的红；再对残留做连通域分析，
    # 报最大红团面积 / 占整页比 / 其质心落在哪个框（落框内 ⇒ 只是框内的边缘外溢，非漏检）。
    covered = np.zeros_like(mask)
    for bx1, by1, bx2, by2 in stamp_int_boxes:
        covered[by1:by2, bx1:bx2] = mask[by1:by2, bx1:bx2]
    total_red = int(cv2.countNonZero(mask))
    in_box_red = int(cv2.countNonZero(covered))
    outside = cv2.bitwise_and(mask, cv2.bitwise_not(covered))
    outside_red = int(cv2.countNonZero(outside))
    n_labels, _labels, stats, cents = cv2.connectedComponentsWithStats(outside, connectivity=8)
    blobs = [
        {
            "area": int(stats[i, cv2.CC_STAT_AREA]),
            "bbox": [int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                     int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])],
            "centroid": [round(float(cents[i][0]), 1), round(float(cents[i][1]), 1)],
        }
        for i in range(1, n_labels)  # 0 号是背景
    ]
    blobs.sort(key=lambda d: d["area"], reverse=True)
    biggest = blobs[0] if blobs else None
    cx, cy = (biggest["centroid"] if biggest else (None, None))
    inside_any = bool(
        biggest
        and any(bx1 <= cx < bx2 and by1 <= cy < by2 for bx1, by1, bx2, by2 in stamp_int_boxes)
    )
    outside_stats = {
        "page_total_red_px": total_red,
        "red_in_any_stamp_box_px": in_box_red,
        "red_outside_all_stamp_boxes_px": outside_red,
        "red_outside_fraction_of_page_red": round(outside_red / total_red, 4) if total_red else None,
        "outside_red_fraction_of_page_area": round(outside_red / float(H * W), 5),
        "largest_outside_blob": biggest,
        "largest_outside_blob_centroid_inside_a_box": inside_any,
        "verdict_no_large_missed_stamp": (
            # 最大框外红团若 < 0.2% 整页面积 ⇒ 无「大片红」；或它本就在某框内（边缘外溢）
            (biggest is None)
            or inside_any
            or (biggest["area"] / float(H * W) < 0.002)
        ),
    }

    stamps = [r for r in rows if r["kind"] == "stamp"]
    out = {
        "png": str(png.relative_to(ROOT)),
        "png_size": [W, H],
        "boxes_source": str(boxes_json.relative_to(ROOT)),
        "page_red_baseline": round(base, 5),
        "stamp_boxes_min_coverage": min((r["red_coverage_in_box"] for r in stamps), default=None),
        "stamp_boxes_max_centroid_offset_norm": max(
            (r["red_centroid_offset_norm"] for r in stamps if r["red_centroid_offset_norm"] is not None),
            default=None,
        ),
        "verdict_stamp_boxes_on_red": all(
            r["red_coverage_in_box"] > 3 * base for r in stamps
        )
        if stamps and base > 0
        else None,
        "outside_boxes": outside_stats,
        "rows": rows,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
