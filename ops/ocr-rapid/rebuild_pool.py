#!/usr/bin/env python
"""ops/ocr-rapid · 重建「248 枚印面评估池」裁图（原池落在 /tmp，已被系统清理）。

背景：`spike-ocr/raw/corpus_manifest.json`（248 枚池清单）**还在**，但它指向的裁图目录
`/tmp/spike-ocr-crops` 已被清理 ⇒ 「用现成池跑 RapidOCR」这条路的前置资产没了。
本脚本用**同一份清单参数 + 同一份 processor.py 只读函数**把裁图重造出来，并**逐枚校验
md5 与清单里记录的值相等** —— 校验通过 ⇒ 重造的池与原池逐像素同一批，评估读数可比。

- 只调用 `processor.py` 的只读函数（render_page / detect_stamp_regions /
  detect_edge_inscriptions / match_shishi_blocks / calc_text_density），
  **不调用** process_page / process_pdf / init_db。
- 不写 `output/`、不写 `~/bistro/data/yinpu.db`、不改 `spike-ocr/raw/corpus_manifest.json`。
- 落盘目录默认 `ops/ocr-rapid/var/crops/{stamp,text}`（`var/` 已被根 .gitignore 忽略）。

跑法：
    ./venv/bin/python ops/ocr-rapid/rebuild_pool.py [--crops-dir DIR] [--pages N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
import processor as P  # noqa: E402

MANIFEST = REPO / "spike-ocr" / "raw" / "corpus_manifest.json"
DEFAULT_CROPS = REPO / "ops" / "ocr-rapid" / "var" / "crops"


def arr_md5(a: np.ndarray) -> str:
    return hashlib.md5(np.ascontiguousarray(a).tobytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops-dir", default=str(DEFAULT_CROPS))
    ap.add_argument("--pages", type=int, default=0, help="只跑前 N 页（0=全部）")
    a = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    TMPL = man["template"]
    PDF = man["pdf"]
    PAGES = man["pages"][: a.pages] if a.pages else man["pages"]
    HSV_LOW, HSV_HIGH = TMPL["hsv_low"], TMPL["hsv_high"]
    MIN_AREA, PAD = man["min_area_eff"], man["pad_ratio"]
    DENSITY_MIN, DENSITY_MAX = man["density_min"], man["density_max"]
    REL_DX, REL_DY, REL_W, REL_H = TMPL["text_offset"]

    crops = Path(a.crops_dir)
    (crops / "stamp").mkdir(parents=True, exist_ok=True)
    (crops / "text").mkdir(parents=True, exist_ok=True)

    want = {c["stem"]: c for c in man["crops"]}
    t0 = time.perf_counter()
    doc = pymupdf.open(PDF)
    rows, mismatch = [], []
    for pi in PAGES:
        page = doc[pi]
        img = P.render_page(page)
        H, W = img.shape[:2]
        cands = P.detect_stamp_regions(img, HSV_LOW, HSV_HIGH, MIN_AREA, PAD)
        cands.sort(key=lambda c: c["bbox"][0])
        edge_cands = P.detect_edge_inscriptions(img, float(np.mean([c["area"] for c in cands]))) \
            if TMPL.get("edge_enabled", True) and cands else []
        exclude = np.zeros((H, W), np.uint8)
        for c in list(cands) + list(edge_cands):
            x1, y1, x2, y2 = [int(v) for v in c["bbox"]]
            exclude[max(0, y1):y2, max(0, x1):x2] = 255
        shishi_map = P.match_shishi_blocks(img, [c["bbox"] for c in cands], exclude_mask=exclude)

        for idx, c in enumerate(cands):
            sx1, sy1, sx2, sy2 = [int(v) for v in c["bbox"]]
            sx1, sy1 = max(0, sx1), max(0, sy1)
            sx2, sy2 = min(W, sx2), min(H, sy2)
            stamp = img[sy1:sy2, sx1:sx2]
            tb = shishi_map.get(idx)
            if tb is not None:
                tx1, ty1, tx2, ty2 = [int(v) for v in tb]
                src = "shishi"
            else:
                tx1, ty1 = int(sx1 + REL_DX), int(sy1 + REL_DY)
                tx2, ty2 = int(tx1 + REL_W), int(ty1 + REL_H)
                src = "template"
            tx1, ty1 = max(0, tx1), max(0, ty1)
            tx2, ty2 = min(W, tx2), min(H, ty2)
            text = img[ty1:ty2, tx1:tx2]

            stem = f"p{pi}_{idx}"
            np.save(crops / "stamp" / f"{stem}.npy", stamp)
            if text.size:
                np.save(crops / "text" / f"{stem}.npy", text)

            ref = want.get(stem)
            row = {"stem": stem, "page": pi, "idx": idx, "text_src": src,
                   "stamp_md5": arr_md5(stamp), "stamp_shape": list(stamp.shape),
                   "text_md5": arr_md5(text) if text.size else None,
                   "text_shape": list(text.shape)}
            if ref:
                ok = (row["stamp_md5"] == ref["stamp_md5"]
                      and row["text_md5"] == ref["text_md5"]
                      and row["stamp_shape"] == ref["stamp_shape"])
                row["matches_manifest"] = bool(ok)
                if not ok:
                    mismatch.append(row)
            rows.append(row)
        print(f"[rebuild] page {pi} stamps={len(cands)} total={len(rows)}", flush=True)
    doc.close()

    summary = {
        "script": "ops/ocr-rapid/rebuild_pool.py",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "crops_dir": str(crops),
        "pdf": PDF, "pages": PAGES,
        "n_rebuilt": len(rows), "n_manifest": man["n_stamps"],
        "all_md5_match": (not mismatch and len(rows) == len(want)),
        "n_mismatch": len(mismatch),
        "mismatch": mismatch[:20],
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "note": "重造池逐枚 md5 与 corpus_manifest.json 比对；all_md5_match=true ⇒ 与原池逐像素同批。",
    }
    out = crops.parent / "pool_rebuild.json"
    out.write_text(json.dumps({**summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["all_md5_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
