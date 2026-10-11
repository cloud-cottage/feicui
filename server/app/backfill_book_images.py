#!/usr/bin/env python
"""全量印面出图回填（Kong / 全量出图单 · 2026-10-11）。

口径真源：
  * `docs/image-color-tiff-draft-v0.1.md`（颜色校正 **V3 双色分层**，§2.3）；
  * `docs/image-naming-draft-v0.1.md`（命名 **P-C-R** ＋ 书籍目录键，§6 / §6.1）。
地基（本模块**直接复用，不重写**）：
  * `server/app/naming.py`（`assign_cr` / `name_for` / `dir_key_for` / `load_dir_keys`）；
  * `server/app/colorcal.py`（`correct_image_v3`）；
  * `processor.render_page`（400 dpi 渲染，与生产同口径）；
  * `config/book_dir_keys.json`（目录键；加法文件）。

做法（Zang 定，逐字照实现）：
  逐页渲染 **400 dpi** ⇒ 按**库内 bbox**（`stamps.x1..y2`，**不重跑检测**——保证与库行一一对应）
  ⇒ **V3 校正**（`colorcal.correct_image_v3`）⇒ 按 `assign_cr` 算 `(C,R)`
  ⇒ 写 `output/books/<目录键>/P<页>-C<列>-R<行>.tiff`（RGB 8-bit ＋ Deflate）。

★ 口径变更（Kevin 2026-10-11，最高优先）：**本地文件一律不再保存 webp**（停止写新命名目录下的
`.webp`；`output/faces/**` 既有 7354 件 webp **不删**——删除与 `stamps.img_path`／E6 取图端点
一起处置，另有专单）。`--write-webp` 仅供历史/对照，默认关。
落库（加法）：`stamps.col` / `stamps.row` / `stamps.img_path_tiff`（既有 10 列**一字不动**）。

红线：只许加法；不建 job、不写 `jobs`/`job_pages`；零联网；图像栈只在 `feicui/venv`；
不碰 `output/faces/**`（旧 webp 并存、不动）、不碰印章线；失败**逐条入清单**、不得静默跳过。

复跑：`cd <feicui> && ./venv/bin/python server/app/backfill_book_images.py --all`
      `... --book "tmp.pdf"`（按书名单跑）
      `... --all --verify-only`（只做核对，不渲染/不写）
幂等：按**解码像素**判（不得按文件 sha256 —— Pillow `tiff_deflate` 在大图上逐字节非确定）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# server/app/backfill_book_images.py -> app -> server -> feicui（仓根）
REPO = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO / "server"

# 仓根有 `feicui/app.py`（Streamlit），会**遮蔽** `server/app/` 包；
# 故把 `server/` 置于 sys.path 首位再 `from app import …`（接口层包名不被遮蔽）。
sys.path.insert(0, str(SERVER_DIR))
from app import naming, colorcal, migrations  # noqa: E402

# 既有 10 列（红线：内容指纹 before ≡ after，本模块一字不改）
DB_COLS_10 = ("id", "pdf_name", "page", "idx", "text", "img_path", "x1", "y1", "x2", "y2")
NEW_COLS = ("col", "row", "img_path_tiff")

WEBP_QUALITY = 95          # 既有 q95 口径（仅在显式 `--write-webp` 时使用）
TIFF_COMPRESSION = "tiff_deflate"
LIMIT_4MIB = 4 * 1024 * 1024
# ★ 口径变更（Kevin 2026-10-11，最高优先）：**本地文件一律不再保存 webp**。
# 新命名目录只写 `.tiff`；`--write-webp` 仅供历史/对照，默认关。
WRITE_WEBP_DEFAULT = False

DEFAULT_DB = REPO.parent / "data" / "yinpu.db"
DEFAULT_OUT_ROOT = REPO / "output" / "books"
DEFAULT_EVIDENCE_DIR = REPO / "ops" / "book-images"


# ──────────────────────────────────────────────────────────────────────────────
# 依赖按路径加载（processor.py 无相对 import ⇒ 不会误触仓根 app.py）
# ──────────────────────────────────────────────────────────────────────────────
def load_processor():
    spec = importlib.util.spec_from_file_location("feicui_processor", str(REPO / "processor.py"))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# 小工具
# ──────────────────────────────────────────────────────────────────────────────
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_arr(arr) -> str:
    """像素数组指纹（幂等按解码像素判；含 shape/dtype）。"""
    import numpy as np

    h = hashlib.sha256()
    a = np.ascontiguousarray(arr)
    h.update(str(a.shape).encode())
    h.update(str(a.dtype).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _col_fingerprint(conn: sqlite3.Connection, cols=DB_COLS_10) -> tuple[str, int]:
    """既有列内容指纹（逐行按 id 升序、canonical repr）——收尾证明 before ≡ after。"""
    h = hashlib.sha256()
    n = 0
    for row in conn.execute(f"SELECT {','.join(cols)} FROM stamps ORDER BY id"):
        h.update(repr(tuple(row)).encode("utf-8"))
        h.update(b"\n")
        n += 1
    return h.hexdigest(), n


def resolve_pdf(pdf_name: str, search_dirs: list[Path]) -> Path | None:
    """PDF 定位：显式 `--pdf-dir` 目录 → 仓内 `REPO` → `~/Downloads` → `REPO/inbox/**` 递归。"""
    for d in search_dirs:
        p = Path(d) / pdf_name
        if p.is_file():
            return p
    inbox = REPO / "inbox"
    if inbox.is_dir():
        for p in sorted(inbox.rglob(pdf_name)):
            if p.is_file():
                return p
    return None


def search_dirs_for(args) -> list[Path]:
    """PDF 搜索目录：始终含 `--root` 与 `~/Downloads`，外加显式 `--pdf-dir`（去重保序）。"""
    dirs: list[Path] = [Path(args.root).expanduser(), Path.home() / "Downloads"]
    for d in args.pdf_dir:
        dirs.append(Path(d).expanduser())
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def safe_rel(p: Path, base: Path = REPO) -> str:
    try:
        return str(p.resolve().relative_to(base))
    except ValueError:
        return str(p)


# ──────────────────────────────────────────────────────────────────────────────
# 库访问
# ──────────────────────────────────────────────────────────────────────────────
def connect_rw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    return conn


def list_books(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT pdf_name FROM stamps GROUP BY pdf_name ORDER BY pdf_name")]


def book_rows(conn: sqlite3.Connection, pdf_name: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT id, page, idx, x1, y1, x2, y2 FROM stamps WHERE pdf_name=? ORDER BY page, idx",
            (pdf_name,),
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# 出图主循环
# ──────────────────────────────────────────────────────────────────────────────
def process_book(
    *,
    conn: sqlite3.Connection,
    processor,
    PIL_Image,
    pdf_name: str,
    pdf_path: Path,
    dir_key: str,
    out_root: Path,
    write_files: bool,
    write_db: bool,
    write_webp: bool,
    limit_pages: int | None,
    limit_stamps: int | None,
    sample_names: set[str],
) -> dict:
    """单书出图 ⇒ 统计 dict（含 updates / failures / sample）。"""
    import numpy as np
    import cv2

    rows = book_rows(conn, pdf_name)
    by_page: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_page[int(r["page"])].append(r)
    pages = sorted(by_page)
    if limit_pages is not None:
        pages = pages[:limit_pages]

    out_dir = out_root / dir_key
    if write_files:
        out_dir.mkdir(parents=True, exist_ok=True)

    stat = {
        "pdf_name": pdf_name, "pdf_path": str(pdf_path), "dir_key": dir_key,
        "out_dir": safe_rel(out_dir),
        "pages": 0, "stamps": 0, "written_tiff": 0, "written_webp": 0, "failed": 0,
        "tiff_bytes": 0, "webp_bytes": 0, "max_tiff": None, "max_webp": None,
        "webp_written_this_run": 0,
        "elapsed_s": 0.0,
    }
    updates: list[tuple[int, int, int, str]] = []   # (id, col, row, img_path_tiff)
    failures: list[dict] = []
    sample: list[dict] = []

    t0 = time.time()
    doc = processor.pymupdf.open(str(pdf_path))
    n_stamps_seen = 0
    try:
        for pi, page in enumerate(pages):
            page_rows = by_page[page]
            try:
                page_img = processor.render_page(doc[page - 1])       # 400 dpi，BGR
            except Exception as exc:                                   # 渲染失败 ⇒ 整页失败（不静默）
                for r in page_rows:
                    failures.append({
                        "pdf_name": pdf_name, "page": page, "idx": int(r["idx"]),
                        "bbox": [r["x1"], r["y1"], r["x2"], r["y2"]],
                        "reason": f"render_failed: {type(exc).__name__}: {exc}",
                    })
                stat["failed"] += len(page_rows)
                continue
            H, W = page_img.shape[:2]
            rgb_page = cv2.cvtColor(page_img, cv2.COLOR_BGR2RGB)       # 校正口径为 RGB

            bboxes = [(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])) for r in page_rows]
            pairs = naming.assign_cr(bboxes)
            naming.assert_page_unique(pairs)                           # 构造上应恒真
            stat["pages"] += 1

            for k, r in enumerate(page_rows):
                if limit_stamps is not None and n_stamps_seen >= limit_stamps:
                    break
                n_stamps_seen += 1
                c, rr = pairs[k]
                x1, y1, x2, y2 = (int(round(v)) for v in bboxes[k])
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(W, x2), min(H, y2)
                if x2 <= x1 or y2 <= y1:                               # 库内 bbox 越界/退化
                    failures.append({
                        "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                        "bbox": [r["x1"], r["y1"], r["x2"], r["y2"]],
                        "reason": f"empty_crop after clamp: {(x1, y1, x2, y2)} page_wh={(W, H)}",
                    })
                    stat["failed"] += 1
                    continue
                crop_bgr = rgb_page[y1:y2, x1:x2]
                try:
                    corrected, rep = colorcal.correct_image_v3(crop_bgr)   # V3 默认口径
                except Exception as exc:
                    failures.append({
                        "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                        "bbox": [x1, y1, x2, y2], "reason": f"colorcal_failed: {type(exc).__name__}: {exc}",
                    })
                    stat["failed"] += 1
                    continue

                tiff_name = naming.name_for(int(page), c, rr, ".tiff")
                webp_name = naming.name_for(int(page), c, rr, ".webp")
                tiff_path = out_dir / tiff_name
                webp_path = out_dir / webp_name

                if write_files:
                    try:
                        img = PIL_Image.fromarray(np.ascontiguousarray(corrected))
                        img.save(tiff_path, format="TIFF", compression=TIFF_COMPRESSION)   # ★ 唯一容器
                        if write_webp:                                                      # 口径默认关
                            img.save(webp_path, format="WEBP", quality=WEBP_QUALITY)
                    except Exception as exc:
                        failures.append({
                            "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                            "bbox": [x1, y1, x2, y2],
                            "reason": f"write_failed: {type(exc).__name__}: {exc}",
                        })
                        stat["failed"] += 1
                        continue
                    tb = tiff_path.stat().st_size
                    stat["tiff_bytes"] += tb
                    stat["written_tiff"] += 1
                    if stat["max_tiff"] is None or tb > stat["max_tiff"]["bytes"]:
                        stat["max_tiff"] = {"name": tiff_name, "bytes": tb, "rel": safe_rel(tiff_path)}
                    if write_webp and webp_path.is_file():
                        wb = webp_path.stat().st_size
                        stat["webp_bytes"] += wb
                        stat["written_webp"] += 1
                        stat["webp_written_this_run"] = stat["written_webp"]
                        if stat["max_webp"] is None or wb > stat["max_webp"]["bytes"]:
                            stat["max_webp"] = {"name": webp_name, "bytes": wb, "rel": safe_rel(webp_path)}

                rel_tiff = os.path.relpath(tiff_path.resolve(), REPO)
                updates.append((int(r["id"]), int(c), int(rr), rel_tiff))
                stat["stamps"] += 1

                if tiff_name in sample_names and len(sample) < 200:
                    sample.append({
                        "name": tiff_name, "page": int(page), "idx": int(r["idx"]),
                        "col": int(c), "row": int(rr), "bbox": [x1, y1, x2, y2],
                        "marker": rep.get("marker"), "ink_ratio": rep.get("ink_ratio"),
                        "core_delta_e_before": rep.get("delta_e_before"),
                        "core_delta_e_after": rep.get("delta_e_after"),
                        "bg_delta_e_before": rep.get("bg_delta_e_before"),
                        "bg_delta_e_after": rep.get("bg_delta_e_after"),
                        "iou": rep.get("iou"), "lstar_p90_delta": rep.get("lstar_p90_delta"),
                        "other_unchanged_rate": rep.get("other_unchanged_rate"),
                    })
            if (pi + 1) % 50 == 0 or (pi + 1) == len(pages):
                print(f"    [{pdf_name[:16]}] 页 {pi + 1}/{len(pages)}（本页 {len(page_rows)} 枚）"
                      f" … 已出图 {stat['written_tiff']} 件 / 失败 {stat['failed']} 条", flush=True)
            if limit_stamps is not None and n_stamps_seen >= limit_stamps:
                break
    finally:
        doc.close()

    if write_db and updates:
        conn.executemany(
            "UPDATE stamps SET col=?, row=?, img_path_tiff=? WHERE id=?",
            [(c, rr, p, i) for (i, c, rr, p) in updates],
        )
        conn.commit()

    stat["elapsed_s"] = round(time.time() - t0, 3)
    stat["_updates"] = updates
    stat["_failures"] = failures
    stat["_sample"] = sample
    return stat


# ──────────────────────────────────────────────────────────────────────────────
# 核对（新列↔文件名、页内唯一、双向对账〔TIFF〕、webp 遗留清点、体量）
#   ★ 口径：本地文件**只认 `.tiff`**；既有 `.webp`（本人本轮已产者）**只列不删**，留删除单统一处置。
# ──────────────────────────────────────────────────────────────────────────────
def verify(conn: sqlite3.Connection, books: list[str], out_root: Path, mapping: dict,
           webp_list_cap: int = 200) -> dict:
    rows = list(conn.execute(
        f"SELECT {','.join(DB_COLS_10 + NEW_COLS)} FROM stamps "
        f"WHERE pdf_name IN ({','.join('?' * len(books))}) ORDER BY pdf_name, page, idx",
        tuple(books),
    ))
    name_re_tiff = naming.NAME_RE_TIFF

    colname_mismatch: list[dict] = []
    null_new: list[dict] = []
    per_page: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
    db_tiff: set[str] = set()
    for r in rows:
        pdf_name = r["pdf_name"]
        if r["col"] is None or r["row"] is None or not r["img_path_tiff"]:
            null_new.append({"pdf_name": pdf_name, "page": r["page"], "idx": r["idx"]})
            continue
        dir_key = naming.dir_key_for(pdf_name, mapping)
        page, c, rr = int(r["page"]), int(r["col"]), int(r["row"])
        per_page[(pdf_name, page)].append((c, rr))
        want_tiff = naming.name_for(page, c, rr, ".tiff")
        base_tiff = os.path.basename(r["img_path_tiff"])
        # 与文件名一致性（新列 ↔ 文件名 ＋ 名字形）
        if base_tiff != want_tiff or not name_re_tiff.match(base_tiff):
            colname_mismatch.append({"pdf_name": pdf_name, "page": page, "col": c, "row": rr,
                                     "img_path_tiff": r["img_path_tiff"], "want": want_tiff})
        db_tiff.add(str(out_root / dir_key / want_tiff))

    # 页内 (C,R) 唯一
    dup_pages = []
    for (pdf_name, page), prs in per_page.items():
        if len(set(prs)) != len(prs):
            dups = [list(x) for x in naming.page_duplicate_pairs(prs)]
            dup_pages.append({"pdf_name": pdf_name, "page": page, "duplicates": dups})

    # 盘上文件：TIFF（交付面）＋ webp（遗留清点）＋ 意外 P* 文件
    disk_tiff: set[str] = set()
    disk_webp: list[str] = []
    disk_other: list[str] = []
    for pdf_name in books:
        d = out_root / naming.dir_key_for(pdf_name, mapping)
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            if name_re_tiff.match(f.name):
                disk_tiff.add(str(f))
            elif f.name.startswith("P") and f.suffix.lower() == ".webp" and naming.NAME_RE.match(f.name):
                disk_webp.append(str(f))
            elif f.name.startswith("P") and f.suffix.lower() in (".tiff", ".webp"):
                disk_other.append(str(f))

    missing_tiff = sorted(db_tiff - disk_tiff)
    orphan_tiff = sorted(disk_tiff - db_tiff)

    return {
        "scope_books": books,
        "rows_in_scope": len(rows),
        "layout_spec": "TIFF-only（本地不再保存 webp；Kevin 2026-10-11 口径变更）",
        "null_new_columns": {"count": len(null_new), "detail": null_new[:50]},
        "name_regex_tiff": {"checked": len(rows) - len(null_new),
                            "mismatch_count": len(colname_mismatch),
                            "detail": colname_mismatch[:50]},
        "page_cr_unique": {"conflicts": len(dup_pages), "detail": dup_pages[:50]},
        "two_way_reconcile_tiff": {
            "db_expected_tiff": len(db_tiff), "disk_tiff": len(disk_tiff),
            "missing_tiff": {"count": len(missing_tiff), "detail": missing_tiff[:50]},
            "orphan_tiff": {"count": len(orphan_tiff), "detail": orphan_tiff[:50]},
            "unexpected_P_files": {"count": len(disk_other), "detail": disk_other[:50]},
        },
        "legacy_webp_present": {
            "count": len(disk_webp),
            "note": "本轮口径变更前已产出的 webp（新命名目录下）——**只列不删**，"
                    "删除与 stamps.img_path／E6 取图端点一起处置，另有专单。",
            "listed_cap": webp_list_cap,
            "detail": disk_webp[:webp_list_cap],
        },
    }


def size_report(conn: sqlite3.Connection, books: list[str], out_root: Path, mapping: dict) -> dict:
    """单张最大字节（对照 4 MiB）＋总体量。"""
    max_tiff = {"bytes": -1, "path": None}
    max_webp = {"bytes": -1, "path": None}
    n_tiff = n_webp = 0
    sum_tiff = sum_webp = 0
    for pdf_name in books:
        d = out_root / naming.dir_key_for(pdf_name, mapping)
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            if naming.NAME_RE_TIFF.match(f.name):
                b = f.stat().st_size
                n_tiff += 1
                sum_tiff += b
                if b > max_tiff["bytes"]:
                    max_tiff = {"bytes": b, "path": safe_rel(f), "name": f.name}
            elif f.suffix.lower() == ".webp" and naming.NAME_RE.match(f.name):
                b = f.stat().st_size
                n_webp += 1
                sum_webp += b
                if b > max_webp["bytes"]:
                    max_webp = {"bytes": b, "path": safe_rel(f), "name": f.name}
    return {
        "tiff_files": n_tiff, "webp_files": n_webp,
        "tiff_bytes": sum_tiff, "webp_bytes": sum_webp,
        "tiff_total_mib": round(sum_tiff / 1048576, 3), "webp_total_mib": round(sum_webp / 1048576, 3),
        "max_tiff": max_tiff, "max_webp": max_webp,
        "limit_4mib": LIMIT_4MIB,
        "max_tiff_within_4mib": (max_tiff["bytes"] <= LIMIT_4MIB),
        "max_webp_within_4mib": (max_webp["bytes"] <= LIMIT_4MIB),
        "webp_note": "webp 为本轮口径变更**之前**已产出的遗留件（只列不删）；"
                     "新口径 TIFF-only ⇒ 本次/复跑**不再产 webp**（webp_written=0）。",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 幂等：按**解码像素**判（不得按文件 sha256）
# ──────────────────────────────────────────────────────────────────────────────
def idempotency_check(conn, processor, PIL_Image, pdf_name, pdf_path, dir_key, out_root, mapping,
                      n_sample=6) -> dict:
    import numpy as np
    import cv2

    rows = book_rows(conn, pdf_name)
    if not rows:
        return {"checked": 0}
    by_page: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_page[int(r["page"])].append(r)
    # 取前若干页里各 1 枚，重渲染→重裁→重校正⇒与盘上文件解码像素比
    doc = processor.pymupdf.open(str(pdf_path))
    checked = 0
    pixel_mismatch = []
    byte_same = 0
    reencode_pixel_stable = True
    out_dir = out_root / dir_key
    try:
        for page in sorted(by_page)[:n_sample]:
            page_rows = by_page[page]
            page_img = processor.render_page(doc[page - 1])
            H, W = page_img.shape[:2]
            rgb_page = cv2.cvtColor(page_img, cv2.COLOR_BGR2RGB)
            bboxes = [(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])) for r in page_rows]
            pairs = naming.assign_cr(bboxes)
            r = page_rows[0]
            c, rr = pairs[0]
            x1, y1, x2, y2 = (int(round(v)) for v in bboxes[0])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(W, x2), min(H, y2)
            corrected, _ = colorcal.correct_image_v3(rgb_page[y1:y2, x1:x2])
            tiff_name = naming.name_for(page, c, rr, ".tiff")
            fp = out_dir / tiff_name
            if not fp.is_file():
                pixel_mismatch.append({"name": tiff_name, "reason": "file_missing"})
                continue
            checked += 1
            with PIL_Image.open(fp) as im:
                ondisk = np.array(im)
            if not np.array_equal(ondisk, corrected):
                pixel_mismatch.append({"name": tiff_name, "reason": "decoded_pixels_differ",
                                       "max_abs_diff": int(np.abs(ondisk.astype(int) - corrected.astype(int)).max())})
            # 同数组二次编码 ⇒ 解码像素稳定？（即使字节非确定，像素须稳）
            import io
            buf = io.BytesIO()
            PIL_Image.fromarray(np.ascontiguousarray(corrected)).save(
                buf, format="TIFF", compression=TIFF_COMPRESSION)
            with PIL_Image.open(io.BytesIO(buf.getvalue())) as im2:
                if not np.array_equal(np.array(im2), corrected):
                    reencode_pixel_stable = False
            if sha256_bytes(buf.getvalue()) == sha256_bytes(fp.read_bytes()):
                byte_same += 1
    finally:
        doc.close()
    return {
        "method": "decode-and-compare-pixels (NOT file sha256)",
        "checked": checked,
        "pixel_mismatch_count": len(pixel_mismatch),
        "pixel_mismatch": pixel_mismatch,
        "reencode_decoded_pixels_stable": reencode_pixel_stable,
        "byte_identical_on_resave": byte_same,
        "note": "同参数二次产出 ⇒ 解码像素逐字节相同；文件 sha256 可不同（Pillow tiff_deflate 大图末 strip 对齐填充字节未初始化）。",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────────────
def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="全量印面出图回填（V3 校正 ＋ P-C-R 命名）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="全量（库内所有书）")
    g.add_argument("--book", action="append", default=[], help="按书名单跑（PDF 名，逐字；可重复）")
    p.add_argument("--db", default=str(env_db_default()), help=f"DB 路径（默认 {DEFAULT_DB}）")
    p.add_argument("--root", default=str(REPO), help="仓根（默认 <feicui>）")
    p.add_argument("--out-root", default=None, help="出图根（默认 <root>/output/books）")
    p.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    p.add_argument("--pdf-dir", action="append", default=[], help="PDF 搜索目录（可重复）")
    p.add_argument("--limit-pages", type=int, default=None, help="每书限页（冒烟）")
    p.add_argument("--limit-stamps", type=int, default=None, help="全局限枚（冒烟）")
    p.add_argument("--no-write-files", action="store_true", help="只算不落盘")
    p.add_argument("--no-write-db", action="store_true", help="不写新列")
    p.add_argument("--write-webp", action="store_true", default=WRITE_WEBP_DEFAULT,
                   help="【默认关】同时写 .webp（口径变更后本地不再保存 webp；仅供历史/对照）")
    p.add_argument("--no-migrate", action="store_true", help="跳过迁移（列须已存在）")
    p.add_argument("--verify-only", action="store_true", help="只核对已落盘/已落库，不渲染不写")
    p.add_argument("--summary-name", default="summary.json")
    return p


def env_db_default() -> Path:
    return Path(os.environ.get("FEICUI_DB") or str(DEFAULT_DB))


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    root = Path(args.root).resolve()
    out_root = Path(args.out_root).resolve() if args.out_root else root / "output" / "books"
    evidence_dir = Path(args.evidence_dir)
    db_path = Path(args.db).resolve()

    if not db_path.is_file():
        print(f"✗ DB 不存在：{db_path}")
        return 2
    print(f"repo        = {REPO}")
    print(f"db          = {db_path}")
    print(f"out_root    = {out_root}")
    print(f"mode        = {'all' if args.all else args.book}")

    mapping = naming.load_dir_keys()
    search_dirs = search_dirs_for(args)
    conn = connect_rw(db_path)

    # ── 迁移（加法列；仓内既有机制）───────────────────────────────────────────
    if not args.no_migrate and not args.verify_only:
        os.environ["FEICUI_DB"] = str(db_path)
        rc = migrations.run()
        if rc not in (0, 3):
            print(f"✗ 迁移失败 rc={rc}")
            return rc
    have_cols = {r[1] for r in conn.execute("PRAGMA table_info(stamps)")}
    missing = [c for c in NEW_COLS if c not in have_cols]
    if missing and not args.verify_only:
        print(f"✗ 缺列 {missing} —— 请先跑迁移（去掉 --no-migrate）或 ./venv/bin/python -m app.migrations")
        return 3

    books = list_books(conn) if args.all else list(args.book)
    unknown = [b for b in books if b not in set(list_books(conn))]
    if unknown:
        print(f"✗ 库内无此书：{unknown}")
        return 2

    fp_before, n_before = _col_fingerprint(conn)
    print(f"现有 10 列指纹 before = {fp_before} （{n_before} 行）")

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(REPO), "db_path": str(db_path), "out_root": str(out_root),
        "scope": "all" if args.all else "books",
        "books": books,
        "correction_algorithm": "dual-layer-v3",
        "correction_params": {
            "V3_LIGHTNESS_V_MIN": colorcal.V3_LIGHTNESS_V_MIN,
            "V3_FG_CHROMA_STRENGTH": colorcal.V3_FG_CHROMA_STRENGTH,
            "V3_PAPER_MODE": colorcal.V3_PAPER_MODE,
            "V3_CLEAN": colorcal.V3_CLEAN,
            "INK_RATIO_MIN": colorcal.INK_RATIO_MIN,
            "TARGET_HEX": colorcal.TARGET_HEX,
        },
        "tiff_container": "RGB 8-bit + tiff_deflate (Deflate, 无损)",
        "webp_quality": WEBP_QUALITY,
        "write_webp": bool(args.write_webp),
        "layout": "tiff-only" if not args.write_webp else "tiff+webp",
        "render_dpi": 400,
        "naming": "P<page>-C<col>-R<row> (大写/短横/不补零)",
        "per_book": {},
        "failures": [],
        "correction_sample": [],
        "fp10_before": fp_before, "fp10_rows_before": n_before,
    }

    if args.verify_only:
        books_stat = {}
    else:
        processor = load_processor()
        from PIL import Image as PIL_Image  # 延迟到需要时（图像栈在 venv）

        t_all = time.time()
        # 抽样页：各书首页 + 页 299/400（若在册），供「抽样说明校正差异」
        want_pages = {b: set() for b in books}
        for b in books:
            first_pages = [r[0] for r in conn.execute(
                "SELECT DISTINCT page FROM stamps WHERE pdf_name=? ORDER BY page LIMIT 1", (b,))]
            want_pages[b].update(first_pages)
            for pg in (299, 400):
                if conn.execute("SELECT 1 FROM stamps WHERE pdf_name=? AND page=?", (b, pg)).fetchone():
                    want_pages[b].add(pg)

        for bi, b in enumerate(books, 1):
            pdf_path = resolve_pdf(b, search_dirs)
            print(f"\n=== [{bi}/{len(books)}] {b} ===")
            if pdf_path is None:
                rows = book_rows(conn, b)
                fails = [{"pdf_name": b, "page": int(r["page"]), "idx": int(r["idx"]),
                          "bbox": [r["x1"], r["y1"], r["x2"], r["y2"]],
                          "reason": "pdf_not_found in search dirs"} for r in rows]
                report["per_book"][b] = {"pdf_name": b, "dir_key": naming.dir_key_for(b, mapping),
                                         "stamps": 0, "failed": len(fails), "pdf_found": False}
                report["failures"].extend(fails)
                print(f"  ✗ PDF 未找到 ⇒ {len(fails)} 行入失败清单")
                continue
            dir_key = naming.dir_key_for(b, mapping)
            # 抽样名（供 correction_sample）：用 (C,R) 对齐的 TIFF 名
            s_names = set()
            for pg in sorted(want_pages[b]):
                rws = list(conn.execute(
                    "SELECT x1,y1,x2,y2 FROM stamps WHERE pdf_name=? AND page=? ORDER BY idx", (b, pg)))
                bxs = [(r[0], r[1], r[2], r[3]) for r in rws]
                prs = naming.assign_cr(bxs)
                for c, rr in prs[:2]:
                    s_names.add(naming.name_for(pg, c, rr, ".tiff"))
            st = process_book(
                conn=conn, processor=processor, PIL_Image=PIL_Image, pdf_name=b, pdf_path=pdf_path,
                dir_key=dir_key, out_root=out_root, write_files=not args.no_write_files,
                write_db=not args.no_write_db, write_webp=args.write_webp,
                limit_pages=args.limit_pages,
                limit_stamps=args.limit_stamps, sample_names=s_names,
            )
            report["correction_sample"].extend(st.pop("_sample"))
            report["failures"].extend(st.pop("_failures"))
            st.pop("_updates", None)
            report["per_book"][b] = st
            print(f"  ✓ {st['stamps']} 枚出图（页 {st['pages']}，失败 {st['failed']}）"
                  f" TIFF {st['tiff_bytes']/1048576:.1f} MiB / webp {st['webp_bytes']/1048576:.1f} MiB"
                  f" 用时 {st['elapsed_s']}s  → {st['out_dir']}", flush=True)
        report["elapsed_s_total"] = round(time.time() - t_all, 3)

    # ── 收尾：指纹 ＋ 核对 ＋ 体量 ＋ 幂等 ─────────────────────────────────────
    fp_after, n_after = _col_fingerprint(conn)
    report["fp10_after"] = fp_after
    report["fp10_rows_after"] = n_after
    report["fp10_identical"] = (fp_before == fp_after) and (n_before == n_after)

    vchk = verify(conn, books, out_root, mapping)
    report["checks"] = vchk
    report["sizes"] = size_report(conn, books, out_root, mapping)

    report["totals"] = {
        "stamps_in_scope": sum(st.get("stamps", 0) for st in report["per_book"].values()) if report["per_book"] else None,
        "written_tiff": report["sizes"]["tiff_files"],
        "webp_written_this_run": sum(st.get("webp_written_this_run", 0) for st in report["per_book"].values()),
        "webp_present_legacy": report["sizes"]["webp_files"],
        "failures": len(report["failures"]),
        "tiff_bytes": report["sizes"]["tiff_bytes"], "webp_bytes": report["sizes"]["webp_bytes"],
    }

    # 幂等核对（两种模式都跑；只需少量渲染 ＋ 解码像素比对）：同参数二次产出 ⇒ 解码像素逐字节相同
    processor = load_processor()
    from PIL import Image as PIL_Image
    for b in books:
        pdf_path = resolve_pdf(b, search_dirs)
        if pdf_path is None:
            report.setdefault("idempotency", {})[b] = {"skipped": "pdf_not_found"}
            continue
        report.setdefault("idempotency", {})[b] = idempotency_check(
            conn, processor, PIL_Image, b, pdf_path, naming.dir_key_for(b, mapping), out_root, mapping)

    conn.close()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    outp = evidence_dir / args.summary_name
    outp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 打印摘要 ─────────────────────────────────────────────────────────────
    print("\n===== 汇总 =====")
    print(f"现有 10 列指纹 before ≡ after : {report['fp10_identical']}  ({fp_before[:16]}…)")
    print(f"出图（交付面 = TIFF-only）：TIFF {report['sizes']['tiff_files']} 件 / "
          f"{report['sizes']['tiff_total_mib']} MiB")
    print(f"本次写 webp 数 = {report['totals']['webp_written_this_run']}"
          f"；盘上遗留 webp（口径变更前已产，只列不删）= {report['sizes']['webp_files']} 件")
    print(f"单张最大 TIFF {report['sizes']['max_tiff']['bytes']} B（≤4MiB: {report['sizes']['max_tiff_within_4mib']}）")
    print(f"页内 (C,R) 冲突页：{vchk['page_cr_unique']['conflicts']}；空新列：{vchk['null_new_columns']['count']}；"
          f"名不符：{vchk['name_regex_tiff']['mismatch_count']}")
    tw = vchk["two_way_reconcile_tiff"]
    print(f"双向对账（TIFF）：库期望 {tw['db_expected_tiff']} / 盘上 {tw['disk_tiff']}；"
          f"缺 {tw['missing_tiff']['count']} / 孤儿 {tw['orphan_tiff']['count']}；"
          f"意外 P* 文件 {tw['unexpected_P_files']['count']}")
    print(f"失败清单：{len(report['failures'])} 条")
    print(f"证据：{outp}")

    ok = (
        report["fp10_identical"]
        and vchk["page_cr_unique"]["conflicts"] == 0
        and vchk["null_new_columns"]["count"] == 0
        and vchk["name_regex_tiff"]["mismatch_count"] == 0
        and tw["missing_tiff"]["count"] == 0 and tw["orphan_tiff"]["count"] == 0
        and tw["unexpected_P_files"]["count"] == 0
        and len(report["failures"]) == 0
    )
    print(f"\n== {'GREEN' if ok else 'RED（见失败清单/核对详表）'} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
