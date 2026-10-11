#!/usr/bin/env python
"""校正件暂停单 · worker 单页函数级验证（Kong 2026-10-11）——**scratch 落点，不写真文件**。

验证 `server/worker/feicui_worker.py::process_page` 在校正件暂停后：
  * **新写校正件（非 O 件 `P?-C?-R?.tiff`）数 = 0**；
  * 只新写原始切片 `…-O.tiff`（数量 = 本页检出枚数）；
  * 返回值**口径保持**：`img_path_tiff` 仍回校正件的约定路径（该文件**不落盘**），
    `img_path` 仍回旧 webp 字符串（不落盘），`col`/`row`/`img_sha256`/`img_bytes` 齐备。

**三重定向**（FEICUI_ROOT = 仓根；FEICUI_FACES_DIR / FEICUI_BOOKS_DIR = scratch）
⇒ 不触及 `output/faces/**`、`output/books/**` 任何真文件。OCR 用桩替换（与影像产物无关）。
用：`cd <feicui> && ./venv/bin/python ops/corrected-pause/verify_worker_single_page.py \
       --pdf "inbox/20261011/吴颐人篆刻作品展示.pdf" --book "吴颐人篆刻作品展示.pdf" --page 8 --out <json>`
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")


def count_tiffs(d: Path) -> tuple[int, int]:
    """⇒ (校正件数, O 件数)。"""
    if not d.is_dir():
        return 0, 0
    files = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".tiff"]
    o = [f for f in files if f.name.endswith("-O.tiff")]
    return len(files) - len(o), len(o)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="PDF 路径（相对仓根或绝对）")
    ap.add_argument("--book", required=True, help="pdf_name（逐字，含扩展名）")
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--scratch", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    scratch = Path(args.scratch).resolve() if args.scratch else Path(tempfile.mkdtemp(prefix="cp-wk-")).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = REPO / pdf_path
    assert pdf_path.is_file(), f"PDF 不存在：{pdf_path}"

    # ── 三重定向（必须在 import worker 之前设 env；worker 于 import 期读 env）──────────
    os.environ["FEICUI_ROOT"] = str(REPO)
    os.environ["FEICUI_BOOKS_DIR"] = str(scratch / "books")
    os.environ["FEICUI_FACES_DIR"] = str(scratch / "faces")
    os.chdir(REPO)

    spec = importlib.util.spec_from_file_location("feicui_worker", str(REPO / "server" / "worker" / "feicui_worker.py"))
    assert spec and spec.loader
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.ocr_text = lambda crop: ""   # 桩：跳过 PaddleOCR（与影像产物无关）

    templates = json.loads((REPO / "config" / "templates.json").read_text(encoding="utf-8"))
    tpl = templates[args.book]

    import pymupdf

    dir_key = w.naming.dir_key_for(args.book, w.DIR_KEYS)
    books_out = Path(os.environ["FEICUI_BOOKS_DIR"]) / dir_key
    corr_b, o_b = count_tiffs(books_out)

    doc = pymupdf.open(str(pdf_path))
    try:
        out = w.process_page(doc, args.page, tpl, args.book, args.book)
    finally:
        doc.close()

    corr_a, o_a = count_tiffs(books_out)
    items = out["items"]
    # 每枚：img_path_tiff 指校正件约定路径（**不在盘**）；同名 -O.tiff **在盘**；img_path 指旧 webp（不在盘）
    detail = []
    ok_all = True
    for it in items:
        tiff_p = Path(os.environ["FEICUI_ROOT"]) / it["img_path_tiff"]
        o_rel = w.naming.original_name_from_corrected(os.path.basename(it["img_path_tiff"]))
        o_p = books_out / o_rel
        webp_p = Path(os.environ["FEICUI_ROOT"]) / it["img_path"]
        rec = {
            "idx": it["idx"], "col": it["col"], "row": it["row"],
            "img_path": it["img_path"], "img_path_tiff": it["img_path_tiff"],
            "img_sha256": it["img_sha256"], "img_bytes": it["img_bytes"], "img_written": it["img_written"],
            "tiff_on_disk(应 False)": tiff_p.is_file(),
            "o_on_disk(应 True)": o_p.is_file(),
            "webp_on_disk(应 False)": webp_p.is_file(),
            "o_name": o_rel,
        }
        if tiff_p.is_file() or not o_p.is_file() or webp_p.is_file():
            ok_all = False
        detail.append(rec)

    result = {
        "repo": str(REPO), "scratch": str(scratch), "pdf": str(pdf_path),
        "book": args.book, "dir_key": dir_key, "page": args.page,
        "detected": out["detected"], "items": len(items),
        "books_out": str(books_out),
        "corrected_files_before": corr_b, "o_files_before": o_b,
        "corrected_files_after": corr_a, "o_files_after": o_a,
        "corrected_new_written": corr_a - corr_b,      # ★ 必须 == 0
        "o_new_written": o_a - o_b,                    # ★ 应 == items
        "checks": {
            "新写校正件数 == 0": (corr_a - corr_b) == 0,
            "只新写 O（数 == 枚数 ∧ > 0）": (o_a - o_b) == len(items) and (o_a - o_b) > 0,
            "各枚 img_path_tiff 约定路径不在盘 ∧ -O 在盘 ∧ webp 不在盘": ok_all,
            "返回值齐备 col/row/img_sha256/img_bytes": all(
                it.get("col") and it.get("row") and it.get("img_sha256") and it.get("img_bytes") for it in items
            ),
        },
        "items_detail_sample": detail[:5],
    }
    result["all_pass"] = all(result["checks"].values())

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==", "ALL PASS" if result["all_pass"] else "FAIL", "==")
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
