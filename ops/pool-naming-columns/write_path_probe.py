#!/usr/bin/env python3
"""P0 写库路径探针（scratch）：证明 commit_chunk → stamps 新行三列落库、img_path 落 NULL。

不建生产 job、不碰生产库（只对 scratch 副本操作）、不碰 output/**。
"""
import os
import sys
import sqlite3
import shutil
from pathlib import Path

REPO = Path("/Users/kevin/bistro/xiai/feicui")
sys.path.insert(0, str(REPO / "server"))
from app import repository, db  # noqa: E402

SCRATCH = Path(os.environ.get("TMPDIR", "/tmp"))
PROD = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
COPY = SCRATCH / "p0_write_path_probe.db"
if COPY.exists():
    COPY.unlink()
src = sqlite3.connect(str(PROD))
dst = sqlite3.connect(str(COPY))
src.backup(dst)          # 一致的快照副本（WAL 下安全）
dst.close()
src.close()

PDF = "P0PROBE.pdf"
JOB = "job-p0probe-write"
with sqlite3.connect(str(COPY)) as c:
    c.execute("INSERT INTO jobs(job_id,pdf_path,pdf_name,page_from,page_to,chunk_size,total_pages,"
              "state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (JOB, "/x/P0PROBE.pdf", PDF, 1, 1, 1, 1, "RUNNING", "2026-10-11T00:00:00+08:00",
               "2026-10-11T00:00:00+08:00"))
    c.execute("INSERT INTO job_pages(job_id,pdf_name,page,chunk_index,state,updated_at) "
              "VALUES (?,?,?,?,?,?)", (JOB, PDF, 1, 0, "RUNNING", "2026-10-11T00:00:00+08:00"))

# 20 枚：col/row 唯一，img_path_tiff 指向 scratch root 下真实落盘的 tiff（占位文件即可，见下）
items = []
for i in range(20):
    col = 1 + i // 5
    row = 1 + i % 5
    rel = f"output/books/P0PROBE/P1-C{col}-R{row}.tiff"
    items.append({"idx": i, "text": "", "img_path": f"output/faces/P0PROBE/p0001_{i:02d}.webp",
                  "col": col, "row": row, "img_path_tiff": rel,
                  "x1": 10, "y1": 20, "x2": 30, "y2": 40})
page_results = [{"page": 1, "ok": True, "detected": 20, "ocr_empty": 0, "items": items,
                 "pdf_name": PDF}]

res = repository.commit_chunk(str(COPY), job_id=JOB, chunk_index=0, page_results=page_results)
print("commit#1 counters:", res["counters"])

with sqlite3.connect(str(COPY)) as c:
    c.row_factory = sqlite3.Row
    rows = list(c.execute("SELECT id,idx,text,img_path,col,row,img_path_tiff,x1,y1,x2,y2 FROM stamps "
                          "WHERE pdf_name=? ORDER BY idx", (PDF,)))
print("inserted rows:", len(rows))
null_col = sum(1 for r in rows if r["col"] is None)
null_row = sum(1 for r in rows if r["row"] is None)
null_tiff = sum(1 for r in rows if r["img_path_tiff"] is None)
nonnull_img = sum(1 for r in rows if r["img_path"] is not None)
print(f"  col NULL={null_col} row NULL={null_row} img_path_tiff NULL={null_tiff} img_path NOT NULL={nonnull_img}")
print("  sample:", dict(rows[0]))

# 幂等：同 items 再提交一次（update arm）
res2 = repository.commit_chunk(str(COPY), job_id=JOB, chunk_index=0, page_results=page_results,
                               on_conflict=repository.ON_CONFLICT_UPDATE)
print("commit#2 counters:", res2["counters"])

# 历史行保护：对既有历史行（tmp.pdf p13 idx0，img_path = webp）跑 update arm，传入 img_path=None
with sqlite3.connect(str(COPY)) as c:
    c.row_factory = sqlite3.Row
    hist = c.execute("SELECT id,text,img_path,x1,y1,x2,y2,col,row,img_path_tiff FROM stamps "
                     "WHERE pdf_name='tmp.pdf' AND page=13 AND idx=0").fetchone()
print("historical 10-col before:", {k: hist[k] for k in ("id", "text", "img_path", "x1", "y1", "x2", "y2")})
with db.tx(str(COPY)) as conn:
    verdict = repository._upsert_stamp(conn, {
        "pdf_name": "tmp.pdf", "page": 13, "idx": 0,
        "text": "CHANGED-PROBE-TEXT", "img_path": None,
        "col": hist["col"], "row": hist["row"], "img_path_tiff": hist["img_path_tiff"],
        "x1": hist["x1"], "y1": hist["y1"], "x2": hist["x2"], "y2": hist["y2"],
    }, repository.ON_CONFLICT_UPDATE)
with sqlite3.connect(str(COPY)) as c:
    c.row_factory = sqlite3.Row
    after = c.execute("SELECT text,img_path,x1,y1,x2,y2 FROM stamps WHERE pdf_name='tmp.pdf' AND page=13 AND idx=0").fetchone()
print(f"update-arm verdict={verdict}; historical img_path after={after['img_path']!r} "
      f"(preserved={after['img_path'] == hist['img_path']}) text_updated={after['text'] == 'CHANGED-PROBE-TEXT'}")

# E6 / E5 读面：新行（img_path NULL + tiff 有效且在盘）必须可取图、且不进「影像缺失」
root = SCRATCH / "p0probe_root"
for i in range(20):
    col = 1 + i // 5
    row = 1 + i % 5
    f = root / f"output/books/P0PROBE/P1-C{col}-R{row}.tiff"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"II*\x00PROBE")
pdf_name, rel, abs_path, source = repository.find_stamp_image(str(COPY), JOB, 1, 0, root=root)
print(f"E6 find_stamp_image -> source={source} rel={rel}")
miss, scope = repository.missing_items(str(COPY), JOB, "image", root=root)
print(f"E5 missing_items(image) count={len(miss)} scope={scope}")

COPY.unlink()
shutil.rmtree(root, ignore_errors=True)
print("OK")
