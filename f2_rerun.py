#!/usr/bin/env python3
"""F2 加法式重跑（限一本书 + 限缺页段）。

用法：
  ./venv/bin/python f2_rerun.py --probe        # 只读探测（monkeypatch 掉 cv2.imwrite，不落盘、不入库）
  ./venv/bin/python f2_rerun.py --apply        # 真跑：process_pdf 只跑指定页段，INSERT 加法入库

硬约束遵循：
- 只跑 chosen book 的 page_range_missing 页段（默认 秦汉印典 p7–p8），不覆盖已有 65 行。
- 跑前 load_templates() 校验模板键与磁盘实况匹配（`hsv_low/hsv_high/min_area/text_offset/
  density_min/density_max/page_range/edge_enabled/pad_ratio`）。
- 跑前后各 dump 一次 stamps 全表，比对原 65 行是否逐字段未变。
"""
import argparse, json, os, sqlite3, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import processor  # noqa: E402

BOOK = "秦汉印典 上海书画 金怀英  1997 ok.pdf"
PDF = "/Users/kevin/Downloads/" + BOOK
PAGES = (7, 8)                      # 缺记录页段（现有记录仅 p5、p6）
REQUIRED_KEYS = ["hsv_low", "hsv_high", "min_area", "text_offset",
                 "density_min", "density_max", "page_range", "edge_enabled", "pad_ratio"]


def dump(path):
    con = sqlite3.connect(os.path.join(ROOT, "yinpu.db"))
    rows = [list(r) for r in con.execute(
        "select id,pdf_name,page,idx,text,img_path,x1,y1,x2,y2 from stamps order by id")]
    con.close()
    with open(path, "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    tmpl_all = processor.load_templates()
    tmpl = tmpl_all.get(BOOK)
    assert tmpl is not None, f"模板缺失: {BOOK}；磁盘模板键={list(tmpl_all)}"
    keycheck = {k: (k in tmpl) for k in REQUIRED_KEYS}
    print("[模板键校验] 全部必需键存在:", all(keycheck.values()), keycheck, flush=True)
    print(f"[模板] {BOOK} page_range={tmpl['page_range']} hsv_low={tmpl['hsv_low']} "
          f"min_area={tmpl['min_area']} density=[{tmpl['density_min']},{tmpl['density_max']}] "
          f"pad_ratio={tmpl.get('pad_ratio')} edge_enabled={tmpl.get('edge_enabled')}", flush=True)

    before = dump(os.path.join(ROOT, "f2_stamps_before.json"))
    print(f"[DB 跑前] stamps={len(before)} 行；现有页段:",
          sorted({(r[1][:6], r[2]) for r in before}), flush=True)

    doc = processor.pymupdf.open(PDF)
    print(f"[PDF] {BOOK} 共 {len(doc)} 页；本次只跑页 {PAGES}", flush=True)

    if a.probe:
        orig_imwrite = processor.cv2.imwrite
        processor.cv2.imwrite = lambda *args, **kw: True   # 不落盘
        try:
            for pg in PAGES:
                t = time.time()
                res = processor.process_page(doc, pg - 1, BOOK, tmpl)
                dt = time.time() - t
                print(f"[probe] page {pg}: {len(res)} 印章块, 耗时 {dt:.1f}s", flush=True)
                for r in res:
                    print(f"   idx={r['idx']} text={r['text']!r} bbox={r['stamp_bbox']} "
                          f"text_bbox={r['text_bbox']}", flush=True)
        finally:
            processor.cv2.imwrite = orig_imwrite
        doc.close()
        return

    if a.apply:
        t = time.time()
        results = processor.process_pdf(PDF, tmpl, start_page=PAGES[0], end_page=PAGES[1])
        dt = time.time() - t
        print(f"[apply] process_pdf 页 {PAGES} 完成：{len(results)} 条，耗时 {dt:.1f}s", flush=True)
        after = dump(os.path.join(ROOT, "f2_stamps_after.json"))
        old_n = len(before)
        old_same = after[:old_n] == before
        print(f"[DB 跑后] stamps={len(after)} 行（新增 {len(after)-old_n}）；"
              f"原 {old_n} 行逐字段未变 = {old_same}", flush=True)
        if not old_same:
            for i, (b, af) in enumerate(zip(before, after)):
                if b != af:
                    print("   DIFF at", i, "before=", b, "after=", af, flush=True)
        print("[新增行]", json.dumps([r for r in after[old_n:]], ensure_ascii=False)[:2000], flush=True)
        with open(os.path.join(ROOT, "f2_rerun_report.json"), "w") as f:
            json.dump({"book": BOOK, "pages": PAGES, "added": len(after) - old_n,
                       "old_rows_unchanged": old_same, "seconds": round(dt, 1),
                       "new_rows": after[old_n:]}, f, ensure_ascii=False, indent=1)
        doc.close()
        return

    print("需要 --probe 或 --apply")


if __name__ == "__main__":
    main()
