#!/usr/bin/env python3
"""F2 影像恢复（只读废纸篓、只复制）。

策略：**不改 stamps 表**（硬约束）。stamps.img_path 已是记录的权威路径，
因此把废纸篓里的影像复制回 img_path 所指的**原路径**，使记录自然解析。
严禁删除/移动废纸篓内容：本脚本只用 shutil.copy2（读源、写目标）。
"""
import json, os, shutil, sqlite3, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "yinpu.db")
TRASH = "/Users/kevin/.Trash"
TRASH_QHYD = os.path.join(TRASH, "秦汉印典 上海书画 金怀英  1997 ok")
TRASH_PAIRS = os.path.join(TRASH, "pairs")

def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    rows = list(con.execute("select id,pdf_name,page,idx,img_path from stamps order by id"))

    missing, present = [], []
    for r in rows:
        p = os.path.join(ROOT, r[4]) if not os.path.isabs(r[4]) else r[4]
        (present if os.path.isfile(p) else missing).append((r, p))

    # 废纸篓索引
    pairs_idx = {}   # (page, idx) -> stamp.png 绝对路径
    if os.path.isdir(TRASH_PAIRS):
        for d in sorted(os.listdir(TRASH_PAIRS)):
            full = os.path.join(TRASH_PAIRS, d)
            if not os.path.isdir(full) or "_" not in d:
                continue
            pt, it = d.rsplit("_", 1)
            if not (pt.startswith("p") and pt[1:].isdigit() and it.isdigit()):
                continue
            png = os.path.join(full, "stamp.png")
            if os.path.isfile(png):
                pairs_idx[(int(pt[1:]), int(it))] = png
    qhyd_idx = {}    # 文件名 -> 绝对路径（顶级，不含子目录）
    if os.path.isdir(TRASH_QHYD):
        for f in sorted(os.listdir(TRASH_QHYD)):
            full = os.path.join(TRASH_QHYD, f)
            if os.path.isfile(full):
                qhyd_idx.setdefault(f, full)

    plan, unmatched = [], []
    for (r, target) in missing:
        _id, pdf, page, idx, img = r
        base = os.path.basename(img)
        src, why = None, None
        if os.path.basename(os.path.dirname(img)) == "pairs" or img.startswith("output/pairs/"):
            src = pairs_idx.get((page, idx))
            why = f"pairs dir name p{page}_{idx} == (page,idx)"
        elif base in qhyd_idx:
            src = qhyd_idx[base]
            why = f"filename {base} == basename(img_path)"
        if src:
            plan.append({"id": _id, "pdf_name": pdf, "page": page, "idx": idx,
                         "src": src, "dst": target, "match": why})
        else:
            unmatched.append({"id": _id, "pdf_name": pdf, "page": page, "idx": idx,
                              "img_path": img, "reason": "废纸篓无对应文件"})

    copied = []
    if apply:
        for it in plan:
            os.makedirs(os.path.dirname(it["dst"]), exist_ok=True)
            if os.path.exists(it["dst"]):
                it["skipped_exists"] = True
                continue
            shutil.copy2(it["src"], it["dst"])     # 只复制，源不动
            copied.append(it["dst"])

    unused_pairs = sorted(set(pairs_idx) - {(i["page"], i["idx"]) for i in plan}
                          - {(r[0][2], r[0][3]) for r in present})
    out = {
        "apply": apply,
        "total_records": len(rows),
        "already_on_disk": len(present),
        "missing_before": len(missing),
        "matched_to_trash": len(plan),
        "unmatched": unmatched,
        "copied_now": len(copied),
        "trash_pairs_dirs_indexed": len(pairs_idx),
        "trash_qhyd_files_indexed": len(qhyd_idx),
        "trash_pairs_dirs_unused_by_records": len(unused_pairs),
        "trash_qhyd_files_unused_by_records": sorted(set(qhyd_idx) - {os.path.basename(r[4]) for r in rows}),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(ROOT, "f2_recover_report.json"), "w") as f:
        json.dump({"summary": out, "plan": plan, "copied": copied}, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
