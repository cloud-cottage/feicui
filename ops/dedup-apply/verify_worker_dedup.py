#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""**新 job 路径**的单页验证（方案 A）—— 证明检测器侧去重生效（scratch，不写生产库、不建 job）。

它调**生产 worker 的真实 `process_page`**（`server/worker/feicui_worker.py`，含方案 A 去重接线），
用 **scratch 输出目录**（`FEICUI_FACES_DIR` / `FEICUI_BOOKS_DIR`）跑指定的几页，输出三条真读数并与
**库内期望**对照：

  * 去重**前**框数 `detected_raw`   ←→ 该页 `stamps` **全量行数**（历史行＝未去重的原始检测 ⇒ 逐页必须相等）；
  * 去重**后**框数 `detected_after`  ←→ 该页 `stamps` **去重后行数**（＝ 全量 − `dup_kind IS NOT NULL`）；
  * 丢弃数 `dedup_dropped`          ←→ 该页 `stamps` **标记行数**（`dup_kind IS NOT NULL`）。

另加一条**几何恒等**判据：worker 保留下来的框集合（`(x1,y1,x2,y2)` 多重集）必须**逐框等于**库内该页
`dup_kind IS NULL` 的行 —— 证明「worker 现场去重保留的行」＝「离线标记保留的行」（同规则、同取舍）。

**纪律**：`FEICUI_DB` 只用于**只读**取期望值（不写）；**不建 job**、**不写生产库**、不碰 `output/**`。
OCR 被替换为空函数（去重发生在 OCR **之前**，与框数无关）⇒ 验证快且确定。

**P0 背景（2026-10-11）**：本脚本最初崩在 worker **导入阶段** —— `server/app/dedup.py` 用了
`@dataclass`，而 worker 的 `_load_by_path` 未先把模块注册进 `sys.modules` ⇒ `dataclasses` 解析
`cls.__module__` 得 `None` ⇒ `AttributeError: 'NoneType' object has no attribute '__dict__'`。
修复＝① `_load_by_path` 先 `sys.modules[name]=mod` 再 `exec_module`；② `dedup.py` 去 `@dataclass`
（改普通类）。本脚本即为修复后的回归验证。

用法（cwd ＝ feicui/）：
    ./venv/bin/python ops/dedup-apply/verify_worker_dedup.py <scratch_dir> [page ...]
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path("/Users/kevin/bistro/xiai/feicui")
PROD_DB = "/Users/kevin/bistro/xiai/data/yinpu.db"
PDF = "/Users/kevin/Downloads/秦印类编 检索版.pdf"
PDF_NAME = "秦印类编 检索版.pdf"
BOOK = "_scratch"

# 覆盖 R1/R2 两类、含高标记页（页面 <- 库内: 全量/标记）
#   725:19/5  776:34/3  773:28/3  749:22/3  56:21/3  96:13/3  73:4/1  387:3/1  446:6/2
DEFAULT_PAGES = [725, 776, 773, 749, 56, 96, 73, 387, 446]


def main() -> int:
    scratch = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dedup-verify")
    pages = [int(p) for p in sys.argv[2:]] or DEFAULT_PAGES
    (scratch / "faces").mkdir(parents=True, exist_ok=True)
    (scratch / "books").mkdir(parents=True, exist_ok=True)

    # 输出落点重定向到 scratch（必须在 import worker 之前设，模块级读 env）
    os.environ["FEICUI_ROOT"] = str(ROOT)
    os.environ["FEICUI_FACES_DIR"] = str(scratch / "faces")
    os.environ["FEICUI_BOOKS_DIR"] = str(scratch / "books")
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    spec = importlib.util.spec_from_file_location("feicui_worker_verify", str(ROOT / "server/worker/feicui_worker.py"))
    assert spec and spec.loader, "无法加载 worker"
    w = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = w
    spec.loader.exec_module(w)                 # ★ P0 修复点：此处曾因 dataclass 未注册而崩
    w.ocr_text = lambda crop: ""               # 去重在 OCR 之前 ⇒ 不影响框数

    import pymupdf  # worker 侧解释器（feicui/venv）

    tmpl = json.loads((ROOT / "config/templates.json").read_text(encoding="utf-8"))[PDF_NAME]

    conn = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    results = []
    doc = pymupdf.open(PDF)
    try:
        for page in pages:
            out = w.process_page(doc, page, tmpl, BOOK, PDF_NAME)
            exp = conn.execute(
                "SELECT COUNT(*) total,"
                " SUM(CASE WHEN dup_kind IS NOT NULL THEN 1 ELSE 0 END) marked"
                " FROM stamps WHERE pdf_name=? AND page=?", (PDF_NAME, page)).fetchone()
            # 库内「去重后保留行」的 bbox 多重集（dup_kind IS NULL）
            keep_rows = conn.execute(
                "SELECT x1,y1,x2,y2 FROM stamps WHERE pdf_name=? AND page=? AND dup_kind IS NULL",
                (PDF_NAME, page)).fetchall()
            db_kept_boxes = sorted((int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])) for r in keep_rows)
            worker_kept_boxes = sorted((int(it["x1"]), int(it["y1"]), int(it["x2"]), int(it["y2"]))
                                       for it in out["items"])
            total, marked = int(exp["total"]), int(exp["marked"] or 0)
            rec = {
                "page": page,
                "detected_raw": out["detected_raw"],
                "detected_after": out["detected"],
                "dedup_dropped": out["dedup_dropped"],
                "items": len(out["items"]),
                "db_rows": total,
                "db_marked": marked,
                "db_kept": total - marked,
                "match_raw": out["detected_raw"] == total,               # 去重前 == 库内全量行
                "match_after": out["detected"] == total - marked,        # 去重后 == 库内保留行
                "match_dropped": out["dedup_dropped"] == marked,         # 丢弃 == 库内标记
                "match_kept_boxes": worker_kept_boxes == db_kept_boxes,  # 几何恒等（逐框同取舍）
            }
            results.append(rec)
            print(json.dumps(rec, ensure_ascii=False))
    finally:
        doc.close()
        conn.close()

    all_match = all(r["match_raw"] and r["match_after"] and r["match_dropped"] and r["match_kept_boxes"]
                    for r in results)
    agg = {
        "pages_checked": len(results),
        "detected_raw_sum": sum(r["detected_raw"] for r in results),
        "detected_after_sum": sum(r["detected_after"] for r in results),
        "dedup_dropped_sum": sum(r["dedup_dropped"] for r in results),
        "db_rows_sum": sum(r["db_rows"] for r in results),
        "db_marked_sum": sum(r["db_marked"] for r in results),
        "all_match(raw&after&dropped&boxes)": all_match,
    }
    print("\n[verify] " + json.dumps(agg, ensure_ascii=False))
    (scratch / "verify_worker_dedup.json").write_text(
        json.dumps({"pdf": PDF_NAME, "pages": results, "aggregate": agg, "all_match": all_match},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    return 0 if all_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
