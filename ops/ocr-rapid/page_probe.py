#!/usr/bin/env python
"""ops/ocr-rapid · 版权页 / ISBN / 印刷体 探针（① 用途）—— 逐页独立子进程。

口径（本仓既有）：
  - **200 dpi 足够**（历史实测 400 dpi 慢 2.9×，见 `ops/biblio-metadata/`）；
  - 一页一子进程（原生推理栈纪律，见 `webui/build/README.md` §2.1）；
  - 只读源 PDF，不写 `output/`。

跑法：
    # 探某 PDF 的指定页（0 基）
    ./venv/bin/python ops/ocr-rapid/page_probe.py --pdf "output/1_Original_PDF/秦汉印典 上海书画 金怀英  1997 ok.pdf" \
        --pages 0,1,2,3,page_count-1,page_count-2 --dpi 200 --out ops/ocr-rapid/raw/isbn_probe_qhyd.json
    # 只跑 worker（父进程用）
    ./venv/bin/python ops/ocr-rapid/page_probe.py --render-page <pdf> <page> <dpi>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PY = REPO / "venv" / "bin" / "python"
SELF = str(Path(__file__).resolve())

#: ISBN 形态串（**实测口径**）：
#:   - 中文版权页老书写作 `ISBN7-80635-095-0/J·895`（ISBN 与数字**无空格**，还带 `/J·895` 后缀）
#:   - 新书写作 `ISBN 978-7-101-12345-6`
#:   ⇒ 不能用「97[89] 开头」的严格式当唯一判据，必须两条都留（本单第一版只有严格式，
#:     结果 1997 年那本 ISBN-10 **漏判**）。
ISBN10_OR_13_RE = re.compile(r"ISBN[\s:：]*([0-9Xx][0-9Xx\-\s]{7,20})")
ISBN13_RE = re.compile(r"(?:97[89])[\-\s]?\d{1,5}[\-\s]?\d{1,7}[\-\s]?\d{1,7}[\-\s]?[\dXx]")
KEY_RE = re.compile(r"ISBN|书号|統一書號|统一书号|定价|定價|印数|印張|印张|开本|開本|版次|出版发行|出版發行|中国版本图书馆|CIP")


def _render_page(pdf: str, page: int, dpi: int) -> int:
    sys.path.insert(0, str(REPO / "webui"))
    import cv2
    import numpy as np
    import pymupdf
    from src.ocr_rapid import get_engine, ocr_image

    t0 = time.perf_counter()
    doc = pymupdf.open(pdf)
    p = doc[page]
    pix = p.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
    doc.close()
    t_render = time.perf_counter() - t0

    t1 = time.perf_counter()
    eng = get_engine()
    ocr_image(img, eng=eng)  # 预热（首调用含模型加载）
    warm = time.perf_counter() - t1

    t2 = time.perf_counter()
    r = ocr_image(img, eng=eng)
    t_ocr = time.perf_counter() - t2
    joined = " ".join(r["texts"])
    rec = {"pdf": Path(pdf).name, "page": page, "dpi": dpi,
           "shape": [img.shape[1], img.shape[0]],
           "n_lines": r["n_lines"], "texts": r["texts"],
           "scores": [round(s, 4) for s in r["scores"]],
           "joined": joined,
           "isbn13_hits": ISBN13_RE.findall(joined),
           "isbn_hits": [m.strip() for m in ISBN10_OR_13_RE.findall(joined)][:4],
           "key_hits": sorted(set(KEY_RE.findall(joined))),
           "render_s": round(t_render, 3), "warmup_s": round(warm, 3), "ocr_s": round(t_ocr, 3),
           "total_s": round(t_render + t_ocr, 3)}
    print("@@JSON@@" + json.dumps(rec, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf")
    ap.add_argument("--pages", default="")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default="")
    ap.add_argument("--render-page", nargs=3, metavar=("PDF", "PAGE", "DPI"))
    a = ap.parse_args()
    if a.render_page:
        return _render_page(a.render_page[0], int(a.render_page[1]), int(a.render_page[2]))

    import pymupdf

    doc = pymupdf.open(a.pdf)
    n = doc.page_count
    doc.close()
    toks = [t.strip() for t in a.pages.split(",") if t.strip()]
    pages = []
    for t in toks:
        pages.append(n - 1 if t == "last" else (n - 2 if t == "second_last" else int(t)))
    print(f"[probe] {Path(a.pdf).name} page_count={n} pages={pages} dpi={a.dpi}", flush=True)

    def one(pg):
        pr = subprocess.run([str(PY), SELF, "--render-page", str(REPO / a.pdf) if not Path(a.pdf).is_absolute() else a.pdf,
                             str(pg), str(a.dpi)], capture_output=True, text=True)
        for line in pr.stdout.splitlines():
            if line.startswith("@@JSON@@"):
                return json.loads(line[len("@@JSON@@"):])
        return {"page": pg, "error": (pr.stderr or pr.stdout or "no output")[-300:]}

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        rows = list(ex.map(one, pages))
    res = {"schema": "feicui.ocr-rapid.page_probe.v1",
           "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "pdf": str(a.pdf), "pdf_name": Path(a.pdf).name, "page_count": n, "dpi": a.dpi,
           "pages_probed": pages, "elapsed_s": round(time.perf_counter() - t0, 1), "rows": rows,
           "isbn13_pages": [r["page"] for r in rows if r.get("isbn13_hits")],
           "isbn_pages": [r["page"] for r in rows if r.get("isbn_hits")],
           "key_pages": [r["page"] for r in rows if r.get("key_hits")]}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[probe] wrote {a.out}")
    for r in rows:
        print(f"[probe] p{r.get('page')} lines={r.get('n_lines')} ocr={r.get('ocr_s')}s "
              f"render={r.get('render_s')}s isbn={r.get('isbn_hits')} isbn13={r.get('isbn13_hits')} "
              f"keys={r.get('key_hits')} head={(r.get('joined') or r.get('error',''))[:70]!r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
