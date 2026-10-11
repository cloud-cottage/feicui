#!/usr/bin/env python
"""**webp 退场 · 删除脚本安全闸的合成夹具测试**（Kong，2026-10-11）。

真库当前读数里「豁免」桶为 0（全部 7272 行的 TIFF 都在盘）⇒ **豁免分支在真数据上不被行使**。
本脚本用**合成夹具**把四个分桶**逐个走通**，机械证明安全闸按行判、不放手删：

| 夹具行 | 形态 | 期望判决 |
| --- | --- | --- |
| A | `img_path=…/p1_0.webp`（在盘）＋ `img_path_tiff=…/P1-C1-R1.tiff`（在盘） | **删**（① 旧印面面 ＋ ② 命名目录面同胞） |
| B | `img_path=…/p2_0.webp`（在盘）＋ `img_path_tiff=NULL` | **豁免 `no_img_path_tiff`** |
| C | `img_path=…/p3_0.webp`（在盘）＋ `img_path_tiff=…/P9-C1-R1.tiff`（**不在盘**） | **豁免 `tiff_file_absent`** |
| D | `img_path=NULL`（非 webp 且空）＋ `img_path_tiff=…/P4-C1-R1.tiff`（在盘） | **无处置面**（没有 webp 候选） |
| E | `img_path=/abs/evil.webp`（**绝对路径**）＋ `img_path_tiff=NULL` | **豁免**（越界路径不当候选） |
| F | 盘上放一个**任何行都没派生到**的孤儿 webp | **不删**，只进「盘面观测」计数 |

另验 `apply_plan`：**只删过闸的那一件**，且删除后 `stamps` 行数/内容逐字不变。

用法（cwd 任意；夹具建在 `$TMPDIR`，不碰真库、不碰 output/）：

    server/.venv/bin/python ops/webp-retire/gate_test.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # feicui/
sys.path.insert(0, str(ROOT / "server"))

from app import retire_webp  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    work = Path(os.environ.get("TMPDIR", "/tmp")) / f"retire-webp-gate-{int(time.time())}"
    root = work / "root"
    (root / "output" / "faces" / "bk").mkdir(parents=True)
    (root / "output" / "books" / "BK").mkdir(parents=True)
    (root / "output" / "books" / "BK" / "orphan").mkdir(parents=True)

    # ---- 夹具文件 ---------------------------------------------------------
    (root / "output" / "faces" / "bk" / "p1_0.webp").write_bytes(b"WEBP-a")
    (root / "output" / "faces" / "bk" / "p2_0.webp").write_bytes(b"WEBP-b")
    (root / "output" / "faces" / "bk" / "p3_0.webp").write_bytes(b"WEBP-c")
    (root / "output" / "books" / "BK" / "P1-C1-R1.tiff").write_bytes(b"II*\x00tiff-a")
    (root / "output" / "books" / "BK" / "P1-C1-R1.webp").write_bytes(b"WEBP-named-a")
    (root / "output" / "books" / "BK" / "P4-C1-R1.tiff").write_bytes(b"II*\x00tiff-d")
    (root / "output" / "books" / "BK" / "orphan" / "X1-C1-R1.webp").write_bytes(b"WEBP-orphan")

    db_path = work / "fixture.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE stamps (id INTEGER PRIMARY KEY, pdf_name TEXT, page INTEGER, idx INTEGER,
                                text TEXT, img_path TEXT, x1 REAL, y1 REAL, x2 REAL, y2 REAL,
                                col INTEGER, row INTEGER, img_path_tiff TEXT)"""
    )
    rows = [
        (1, "bookA.pdf", 1, 0, "A", "output/faces/bk/p1_0.webp", "output/books/BK/P1-C1-R1.tiff"),
        (2, "bookA.pdf", 2, 0, "B", "output/faces/bk/p2_0.webp", None),
        (3, "bookA.pdf", 3, 0, "C", "output/faces/bk/p3_0.webp", "output/books/BK/P9-C1-R1.tiff"),
        (4, "bookA.pdf", 4, 0, "D", None, "output/books/BK/P4-C1-R1.tiff"),
        (5, "bookA.pdf", 5, 0, "E", "/abs/evil.webp", None),
    ]
    for rid, pdf, page, idx, text, ip, itiff in rows:
        conn.execute(
            "INSERT INTO stamps(id,pdf_name,page,idx,text,img_path,img_path_tiff) VALUES(?,?,?,?,?,?,?)",
            (rid, pdf, page, idx, text, ip, itiff),
        )
    conn.commit()
    before = conn.execute("SELECT id,pdf_name,page,idx,img_path,img_path_tiff FROM stamps ORDER BY id").fetchall()
    conn.close()

    # ---- 扫描 -------------------------------------------------------------
    plan = retire_webp.scan(db_path, root)
    print("\n--- scan() 读数 ---")
    print(json.dumps({k: v for k, v in plan.items() if k in ("stamps_rows",)}, ensure_ascii=False))
    print("delete:", plan["delete"]["files"], "files /", plan["delete"]["rows"], "rows")
    print("exempt:", {k: v for k, v in plan["exempt"]["by_reason"].items()})
    print("exempt files by reason:", plan["exempt"]["by_reason_files"])
    print("census:", json.dumps(plan["disk_census"], ensure_ascii=False))

    dels = sorted(f["rel"] for f in plan["delete"]["list"])
    check("A 行两件 webp 过闸（faces ＋ named）", dels, [
        "output/books/BK/P1-C1-R1.webp", "output/faces/bk/p1_0.webp",
    ])
    check("豁免行数", plan["exempt"]["rows"], 2)
    check("豁免件数", plan["exempt"]["files"], 2)
    check("桶 no_img_path_tiff（B）", plan["exempt"]["by_reason_files"].get("no_img_path_tiff"), 1)
    check("桶 tiff_file_absent（C）", plan["exempt"]["by_reason_files"].get("tiff_file_absent"), 1)
    check("E 行绝对路径 ⇒ 记观测、不当候选", plan["unsafe_paths"], [{"id": 5, "column": "img_path", "value": "/abs/evil.webp"}])
    check("E 行确实未进任何桶/清单", [f["rel"] for f in plan["exempt"]["list"] if f["id"] == 5], [])
    check("D 行（无 webp 候选）不删不豁免", any(f["id"] == 4 for f in plan["delete"]["list"] + plan["exempt"]["list"]), False)
    check("孤儿 webp 未进删除清单", any("orphan" in f["rel"] for f in plan["delete"]["list"]), False)
    check("盘面观测：孤儿计数", plan["disk_census"]["webp_unreferenced"], 1)
    check("盘面观测：盘上 webp 总数", plan["disk_census"]["webp_on_disk"], 5)

    # ---- apply（只删过闸的）------------------------------------------------
    res = retire_webp.apply_plan(plan, root=root)
    print("\n--- apply_plan() ---")
    print("deleted:", [d["rel"] for d in res["deleted"]], "failed:", res["failed"])
    check("真删件数", res["count"], 2)
    check("faces webp 已删", (root / "output" / "faces" / "bk" / "p1_0.webp").exists(), False)
    check("named webp 已删", (root / "output" / "books" / "BK" / "P1-C1-R1.webp").exists(), False)
    check("TIFF 未动", (root / "output" / "books" / "BK" / "P1-C1-R1.tiff").exists(), True)
    check("豁免件仍在盘（B）", (root / "output" / "faces" / "bk" / "p2_0.webp").exists(), True)
    check("豁免件仍在盘（C）", (root / "output" / "faces" / "bk" / "p3_0.webp").exists(), True)
    check("孤儿 webp 仍在盘", (root / "output" / "books" / "BK" / "orphan" / "X1-C1-R1.webp").exists(), True)

    conn = sqlite3.connect(db_path)
    after = conn.execute("SELECT id,pdf_name,page,idx,img_path,img_path_tiff FROM stamps ORDER BY id").fetchall()
    conn.close()
    check("库逐字不变（apply 前后）", after, before)
    check("库仍 5 行", len(after), 5)

    print(f"\n夹具：{work}")
    print(f"断言：{'ALL PASS' if not FAILS else 'FAIL ' + str(len(FAILS)) + ' 项: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
