#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重算「既有 13 列」内容指纹（`stamps` 路径面 before ≡ after）—— 方案 A 收口取证（2026-10-11）。

## 为什么需要它

去重方案 A 给 `stamps` **加法**新增 3 列（`dup_kind` / `dup_of_id` / `dup_algo`，migration `1a-0004`），
并由 `server/app/dedup_apply.py` 幂等写入标记。**红线：既有 13 列（`id..img_path_tiff`）的值一字不得改。**
本脚本用**一种可逐字节复现的序列化**，对「写入前备份（prebak）」与「写入后现状（prod）」分别算 md5，
证明 **before ≡ after**。

## 确切算法（此前口径不一致，此处钉死）

SQL 列序（**逐字照 `PRAGMA table_info` 的前 13 列**，即 `1a-0003` 之后的既有列面，**不含** 3 个去重列）：
    `id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2, col, row, img_path_tiff`

```python
parts = []
for row in conn.execute("SELECT id,pdf_name,page,idx,text,img_path,x1,y1,x2,y2,col,row,img_path_tiff "
                        "FROM stamps ORDER BY id"):
    parts.append("|".join("" if v is None else str(v) for v in row))  # 行内用 "|" 连接；NULL → 空串
digest = hashlib.md5("".join(parts).encode("utf-8")).hexdigest()      # ★ 行与行之间**不加分隔符**
```

要点（任一不同即得到完全不同的 md5，故必须逐项对齐）：
  * **列**＝前 13 列（含 `id`；含 `col`/`row`/`img_path_tiff`；**不含** 3 个 `dup_*` 列）；
  * **行序**＝`ORDER BY id`（等价 `rowid`，本表一致）；
  * **序列化**＝**每一行**的 13 个值先以 **`"|"`** 连接；再把各行结果用**空串 `""`** 依次拼接成
    单个字符串（**★ 行与行之间不加任何分隔符** —— 这一点是此前口径不一致的根源：若改成
    「把所有行的所有值展平后再用 `"|"` 连接」，会多出 `N−1` 个分隔符、得到另一个摘要
    `eb4fd59542fbcdef9dbcfedce479cfb1`）；
  * **NULL** → 空串 `""`；数值/文本 → `str()`；
  * **编码**＝UTF-8。

（口径说明：此形态即此前算得 `17ada51244edac62aa2147d6b9a9612d` 的确切算法；用 `"\t".join`、
`"\n".join(行)` 或「展平后 `"|".join`」等变体会得到**完全不同**的摘要，故**必须**按上表照抄。）

## 用法

    ./venv/bin/python ops/dedup-apply/recompute_cols13_md5.py <db> [<db2> ...]
    # 典型：before = 写入前备份，after = 现行 prod 库
    ./venv/bin/python ops/dedup-apply/recompute_cols13_md5.py \
        /Users/kevin/.hermes/profiles/zang/cache/scratch/dedup-apply/yinpu.db.prebak \
        /Users/kevin/bistro/data/yinpu.db
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys

COLS13 = ["id", "pdf_name", "page", "idx", "text", "img_path",
          "x1", "y1", "x2", "y2", "col", "row", "img_path_tiff"]


def cols13_md5(db_path: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stamps)")]
        missing = [c for c in COLS13 if c not in cols]
        if missing:
            raise SystemExit(f"✗ {db_path}：stamps 缺既有列 {missing}（列＝{cols}）")
        rows = conn.execute(
            f"SELECT {','.join(COLS13)} FROM stamps ORDER BY id").fetchall()
    finally:
        conn.close()
    parts = ["|".join("" if v is None else str(v) for v in row) for row in rows]
    digest = hashlib.md5("".join(parts).encode("utf-8")).hexdigest()
    return {
        "db_path": db_path,
        "cols13": COLS13,
        "schema_cols": cols,
        "rows": len(rows),
        "serialized_bytes": len("".join(parts).encode("utf-8")),
        "serialization": 'md5("".join("|".join(<13-col values> per row) for row in ORDER BY id; NULL->"").encode("utf-8"))',
        "cols13_md5": digest,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    out = {p: cols13_md5(p) for p in argv}
    for p, r in out.items():
        print(f"{r['cols13_md5']}  rows={r['rows']}  {p}")
    if len(argv) >= 2:
        base = out[argv[0]]["cols13_md5"]
        same = all(out[p]["cols13_md5"] == base for p in argv)
        print(f"\nbefore ≡ after : {same}   (baseline={base})")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
