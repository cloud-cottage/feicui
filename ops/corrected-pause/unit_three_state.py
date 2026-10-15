#!/usr/bin/env python
"""校正件暂停单 · 回落链三态单测（Kong 2026-10-11）——**scratch 目录伪造三态，不写真文件**。

口径真源 `docs/image-original-crop-draft-v0.1.md` §6 第 4 条：
解析顺序 = `img_path_tiff`（校正件）→ 同目录同名 `-O.tiff`（原始切片）→ `img_path`（历史 webp）。

本单测在 **scratch 根**下伪造「仅校正件 / 仅 O / 皆无 / 仅 legacy webp」四态，
直接调 `app.repository.find_stamp_image`（E6 真源）与 `app.repository.missing_items`（E5 真源），
断言：
  * 仅校正件 ⇒ 用校正件（source=img_path_tiff、abs 指校正件）；
  * 仅 O     ⇒ 用 O（source=img_path_tiff/-O、abs 指 `-O.tiff`）——**新回落行为**；
  * 皆无     ⇒ `ImageUnavailable`（E6 404 第三类）；
  * E5：仅校正件 / 仅 O 两态**都不计缺失**；皆无计 `file_missing`。

**不触碰任何真文件**（根＝`--root`，默认 scratch 临时目录），跑完不清理真产出。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

SERVER = "/Users/kevin/bistro/feicui/server"
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)
import app.repository as repository  # noqa: E402
import app.naming as naming  # noqa: E402

PDF = "tmp.pdf"
JK = "tmp.pdf"          # 目录键（未登记的 tmp.pdf 回落规范化书名 ⇒ "tmp.pdf"）


def build_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE jobs(job_id TEXT PRIMARY KEY, pdf_name TEXT, pdf_path TEXT,
                          page_from INT, page_to INT, state TEXT, created_at TEXT);
        CREATE TABLE job_pages(job_id TEXT, page INT, state TEXT);
        CREATE TABLE stamps(id INTEGER PRIMARY KEY, pdf_name TEXT, page INT, idx INT, text TEXT,
                            img_path TEXT, x1 INT, y1 INT, x2 INT, y2 INT,
                            col INT, row INT, img_path_tiff TEXT);
        """
    )
    conn.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?)", ("job-UT", PDF, "/x/tmp.pdf", 1, 1, "DONE", "t"))
    conn.execute("INSERT INTO job_pages VALUES(?,?,?)", ("job-UT", 1, "DONE"))
    # 四态（同页 1，idx 0..3）
    rows = [
        # idx 0：仅校正件（tiff 在盘、无 O）
        (0, None, 1, 1, "output/books/%s/P1-C1-R1.tiff" % JK),
        # idx 1：仅 O（tiff 约定路径在盘上不存在、同名 -O.tiff 在盘）
        (1, "output/books/%s/P1-C1-R1.webp" % JK, 1, 1, "output/books/%s/P1-C1-R2.tiff" % JK),
        # idx 2：皆无（tiff 与 img_path 都非空但都不在盘、N-o.tiff 也不在盘）
        (2, None, 1, 1, "output/books/%s/P1-C1-R3.tiff" % JK),
        # idx 3：无 tiff（NULL）、仅 legacy webp 在盘 ⇒ 走 img_path 兼容回退
        (3, "output/books/%s/P1-C1-R4.webp" % JK, 1, 1, None),
    ]
    # (idx, img_path, col, row, img_path_tiff)
    for idx, legacy, c, r, tiff in rows:
        conn.execute(
            "INSERT INTO stamps(pdf_name,page,idx,text,img_path,x1,y1,x2,y2,col,row,img_path_tiff) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (PDF, 1, idx, None, legacy, 0, 0, 10, 10, c, r, tiff),
        )
    conn.commit()
    conn.close()


def touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"II*\x00")   # 仅需「文件在盘」（内容与本单测无关）


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="scratch 根（默认新建临时目录，不写真文件）")
    ap.add_argument("--out", default=None, help="汇总 JSON 落点（可选）")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(tempfile.mkdtemp(prefix="cp-ut-")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    books = root / "output" / "books" / JK
    db_path = root / "scratch.db"
    build_db(db_path)

    # 伪造盘上文件：idx0 校正件；idx1 的 O；idx3 的 legacy webp
    corrected0 = books / naming.name_for(1, 1, 1, ".tiff")
    o1 = books / naming.name_for_original(1, 1, 2, ".tiff")
    legacy3 = books / naming.name_for(1, 1, 4, ".webp")
    touch(corrected0)
    touch(o1)
    touch(legacy3)

    result: dict = {"root": str(root), "db": str(db_path), "scenarios": {}, "files_forged": {
        "corrected": str(corrected0.relative_to(root)), "o": str(o1.relative_to(root)),
        "legacy": str(legacy3.relative_to(root)),
    }}

    def call(idx: int):
        try:
            pdf_name, rel, abs_path, source = repository.find_stamp_image(db_path, "job-UT", 1, idx, root=root)
            return {"ok": True, "pdf_name": pdf_name, "rel": rel, "abs": abs_path, "source": source,
                    "abs_is_file": Path(abs_path).is_file()}
        except repository.ImageUnavailable as exc:
            return {"ok": False, "error": "IMAGE_UNAVAILABLE", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}

    checks: list[tuple[str, bool, str]] = []

    r0 = call(0)
    result["scenarios"]["only_corrected(idx0)"] = r0
    checks.append(("仅校正件 ⇒ 用校正件", bool(r0["ok"]) and r0["source"] == repository.E6_SOURCE_TIFF
                   and r0["abs"].endswith(naming.name_for(1, 1, 1, ".tiff")), r0.get("source", r0.get("error"))))

    r1 = call(1)
    result["scenarios"]["only_o(idx1)"] = r1
    checks.append(("仅 O ⇒ 用 O（新回落）", bool(r1["ok"]) and r1["source"] == repository.E6_SOURCE_ORIGINAL
                   and r1["abs"].endswith(naming.name_for_original(1, 1, 2, ".tiff")), r1.get("source", r1.get("error"))))

    r2 = call(2)
    result["scenarios"]["neither(idx2)"] = r2
    checks.append(("皆无 ⇒ IMAGE_UNAVAILABLE", (not r2["ok"]) and r2["error"] == "IMAGE_UNAVAILABLE",
                   r2.get("error", "?")))

    r3 = call(3)
    result["scenarios"]["legacy_only(idx3)"] = r3
    checks.append(("无 tiff、仅 legacy ⇒ 用 img_path", bool(r3["ok"]) and r3["source"] == repository.E6_SOURCE_LEGACY,
                   r3.get("source", r3.get("error"))))

    # E5：missing_items(kind=image) ⇒ 只有「皆无」(idx2) 计缺失
    items, scope = repository.missing_items(db_path, "job-UT", "image", root=root)
    result["e5"] = {"scope": list(scope), "missing": items,
                    "missing_idx": [it["idx"] for it in items],
                    "missing_reason": sorted({it["reason"] for it in items})}
    checks.append(("E5：仅校正件/仅 O 两态不计缺失，仅 idx2 计 file_missing",
                   [it["idx"] for it in items] == [2] and all(it["reason"] == "file_missing" for it in items),
                   str([it["idx"] for it in items])))

    result["checks"] = [{"name": n, "pass": bool(p), "read": d} for n, p, d in checks]
    result["all_pass"] = all(p for _n, p, _d in checks)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==", "ALL PASS" if result["all_pass"] else "FAIL", "==")
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
