#!/usr/bin/env python3
"""F2 OCR 小样本可行性验证：在**已有影像**上跑 PaddleOCR 3–5 张，测耗时/样例/置信度。

- 只用本地缓存模型（~/.paddlex/official_models），显式关闭联网型前置（doc_ori/unwarping）。
- 目的：判定「补释文」是否可行 + 估算全量耗时；本轮不全量跑。
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLES = [
    # (标签, 书, 相对路径)  —— 覆盖三本书，含印面裁切图与整块边缘图
    ("tmp.pdf p13_0 印面裁切", "tmp.pdf", "output/pairs/p13_0/stamp.png"),
    ("秦汉印典 p5_0 印面裁切", "秦汉印典", "output/秦汉印典 上海书画 金怀英  1997 ok/p5_0.webp"),
    ("秦汉印典 p6_0 印面裁切", "秦汉印典", "output/秦汉印典 上海书画 金怀英  1997 ok/p6_0.webp"),
    ("古玺汇编 p24_0 印面裁切", "古玺汇编", "output/古玺汇编 文物出版社 罗福颐  ok/p24_0.webp"),
    ("tmp.pdf p13_0 边款/整块 edge", "tmp.pdf", "/Users/kevin/.Trash/pairs/p13_0/edge.png"),
]

def main():
    from paddleocr import PaddleOCR
    t0 = time.time()
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False, lang="ch")
    init_s = time.time() - t0
    print(f"[init] PaddleOCR 构造耗时 {init_s:.2f}s（模型本地缓存，不联网下载）", flush=True)

    out = {"init_seconds": round(init_s, 2), "samples": []}
    for label, book, rel in SAMPLES:
        path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        rec = {"label": label, "book": book, "path": rel, "exists": os.path.isfile(path)}
        if not rec["exists"]:
            rec["error"] = "file not found"
            out["samples"].append(rec); continue
        t = time.time()
        try:
            res = ocr.predict(path)
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["seconds"] = round(time.time() - t, 2)
            out["samples"].append(rec)
            print(json.dumps(rec, ensure_ascii=False), flush=True)
            continue
        rec["seconds"] = round(time.time() - t, 2)
        texts, scores, boxes = [], [], 0
        for page in res:
            d = page if isinstance(page, dict) else getattr(page, "json", {}).get("res", {})
            texts += [str(t) for t in (d.get("rec_texts") or [])]
            scores += [round(float(s), 4) for s in (d.get("rec_scores") or [])]
            rb = d.get("rec_boxes")
            if rb is None:
                rb = d.get("dt_polys")
            boxes += len(rb) if rb is not None else 0
        rec["n_boxes"] = boxes
        rec["rec_texts"] = texts
        rec["rec_scores"] = scores
        rec["max_score"] = max(scores) if scores else None
        rec["mean_score"] = round(sum(scores) / len(scores), 4) if scores else None
        out["samples"].append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)

    times = [s["seconds"] for s in out["samples"] if "seconds" in s]
    out["timing"] = {
        "n": len(times),
        "per_image_seconds": times,
        "mean_seconds": round(sum(times) / len(times), 2) if times else None,
        "estimated_seconds_for_65_images": round(sum(times) / len(times) * 65, 1) if times else None,
        "estimated_seconds_for_372p_pdf_1img_per_stamp_note": "见备注",
    }
    with open(os.path.join(ROOT, "f2_ocr_sample_report.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n[summary] " + json.dumps({k: out[k] for k in ("init_seconds", "timing")}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
