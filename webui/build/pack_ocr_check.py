#!/usr/bin/env python
# webui/build/pack_ocr_check.py —— **包内 OCR 验收脚本**（只在 `.app` 内跑；走 `--engine-run`）。
"""用途：在**打包产物自己的解释器**里渲染 PDF 页 → RapidOCR 识别 → 落读数 JSON。

跑法（示例，路径按实际产物替换）：
    /path/斐萃-s2.app/Contents/MacOS/斐萃 --engine-run \
        /Users/kevin/bistro/feicui/webui/build/pack_ocr_check.py \
        --pdf "/Users/kevin/bistro/feicui/output/1_Original_PDF/秦汉印典 上海书画 金怀英  1997 ok.pdf" \
        --page 1 --dpi 200 --out /tmp/pack_ocr_check.json

判据（与源码态读数 `ops/ocr-rapid/README.md` 对照）：
  * `render_ok` / `ocr_ok` 为真、`texts` 非空、ISBN 命中（**双式** ISBN-10 + ISBN-13）。
  * `elapse_s` 与源码态同页同 dpi 的 0.62 s/页 同量级。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ISBN13 = re.compile(r"97[89][-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,6}[-\s]?[\dXx]")
ISBN10_OR_13 = re.compile(r"(?:ISBN[-\s]?)?(?:97[89][-\s]?)?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,6}[-\s]?[\dXx]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, default=0, help="单页（兼容旧调用）")
    ap.add_argument("--pages", default="", help="逗号分隔的多页，例 `1,2,3`（与 --page 二选一）")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    pages = [int(x) for x in args.pages.split(",") if x.strip()] or [args.page or 1]

    res: dict = {"frozen": bool(getattr(sys, "frozen", False)), "exe": sys.executable,
                 "meipass": getattr(sys, "_MEIPASS", ""), "pdf": args.pdf,
                 "pages": pages, "dpi": args.dpi}
    pdf = Path(args.pdf)
    res["pdf_exists"] = pdf.is_file()
    if not res["pdf_exists"]:
        print(json.dumps(res, ensure_ascii=False)); return 2

    # ── ① 包内渲染（pymupdf 随包）──────────────────────────────────────────────
    import pymupdf
    sys.path.insert(0, str(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))))
    from src import ocr_rapid  # noqa: E402

    rows = []
    t0 = time.perf_counter()
    with pymupdf.open(str(pdf)) as doc:
        res["page_count"] = doc.page_count
        for pg in pages:
            t_r = time.perf_counter()
            pix = doc[pg - 1].get_pixmap(dpi=args.dpi)
            png = pix.tobytes("png")
            render_s = time.perf_counter() - t_r
            r = ocr_rapid.ocr_image(png)                 # 直接喂 PNG 字节（引擎内部解码）
            joined = r.get("texts_joined") or ""
            row = {
                "page": pg, "render_s": round(render_s, 3), "ocr_s": round(r.get("elapse_s") or 0, 3),
                "page_s": round(render_s + (r.get("elapse_s") or 0), 3),
                "png_bytes": len(png), "png_px": [pix.width, pix.height],
                "n_lines": r.get("n_lines"), "texts": r.get("texts"),
                "scores": [round(float(s), 4) for s in (r.get("scores") or [])],
                "isbn13_hits": ISBN13.findall(joined),
                "isbn_any_hits": [h for h in ISBN10_OR_13.findall(joined)
                                  if len(re.sub(r"\D", "", h)) in (10, 13)],
            }
            rows.append(row)
            print("PAGE_" + json.dumps(row, ensure_ascii=False), flush=True)
    res["wall_s"] = round(time.perf_counter() - t0, 3)
    res["rows"] = rows
    res["ocr_ok"] = any(r["n_lines"] for r in rows)
    res["isbn_pages"] = [r["page"] for r in rows if r["isbn_any_hits"] or r["isbn13_hits"]]
    res["last_error"] = ocr_rapid.last_error()
    res["engine_name"] = ocr_rapid.OCR_ENGINE_NAME

    text = json.dumps(res, ensure_ascii=False, indent=2)
    print("PACK_OCR_CHECK=" + json.dumps({k: res[k] for k in
          ("frozen", "pdf_exists", "page_count", "wall_s", "isbn_pages", "ocr_ok", "engine_name")},
          ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if res["ocr_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
