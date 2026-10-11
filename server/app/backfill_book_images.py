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

★ **原始切片 `-O`（2026-10-11 新增；口径真源 `docs/image-original-crop-draft-v0.1.md`）**：
每次裁切**额外**写 `P<页>-C<列>-R<行>-O.tiff` ＝ **未做颜色处理的原片**
（400 dpi 渲染后按库内 bbox 原样裁出）；**同几何 / 同容器（TIFF RGB 8-bit＋Deflate）/ 同目录**；
命名由 `naming.name_for_original` 派生（**不落库、不新增列**）。

* 开关：**默认开**，`--no-original` 关；`--orig-only` ＝「**只出 O 件**」
  （不跑 V3、**不写校正件**、不写库——全量补 O 的最省路径，也天然满足「不改既有校正件」红线）。
* **幂等按解码像素判**（§2：不得按文件 sha256 —— Pillow `tiff_deflate` 大图逐字节非确定）：
  已存在且**解码像素逐像素相等** ⇒ 跳过不重写。
* **校正件也按解码像素幂等**（红线①「只增文件」）：已存在且像素一致 ⇒ **不重写**
  ⇒ 既有 8708 件校正件的字节**不得变**。
* 失败**逐条入清单**、不得静默跳过。

红线：只许加法；不建 job、不写 `jobs`/`job_pages`；零联网；图像栈只在 `feicui/venv`；
不碰 `output/faces/**`（旧 webp 并存、不动）、不碰印章线；失败**逐条入清单**、不得静默跳过。

复跑：`cd <feicui> && ./venv/bin/python server/app/backfill_book_images.py --all`
      `... --book "tmp.pdf"`（按书名单跑）
      `... --all --verify-only`（只做核对，不渲染/不写）
      `... --all --orig-only`（**只补原始切片 O**：不跑 V3、不写校正件、不写库——全量补 O 用这条）
      `... --all --no-original`（只出校正件，回到本单之前的形态）
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
# ★ O 件编码（Kevin 2026-10-11 裁定「O 件用 TIFF 编码」＋ Zang 实测裁决）：
#   **Deflate ＋ Predictor=2（水平差分）**。实测量：deflate 均 391.9 KB → deflate+Predictor 均 289.7 KB
#   ＝ 73.9%（省 26.1%）；lzw 反而 137.5%；**三种编码下解码像素与原片逐像素相等均成立**。
#   ⇒ O 件一律以此编码写出；**已写出的旧编码 O 件由幂等判据自动升级重写**
#      （判据 ＝ 解码像素相等 **且** 容器合要求，见 `write_tiff_idempotent_pixels`）。
#   ★ **校正件 `P-C-R.tiff` 的编码与字节一字不动**（红线①照旧；其幂等只按解码像素判、不查 Predictor）。
O_TIFF_PREDICTOR = 2
TIFF_TAG_PREDICTOR = 317
TIFF_TAG_COMPRESSION = 259
LIMIT_4MIB = 4 * 1024 * 1024
# ★ 口径变更（Kevin 2026-10-11，最高优先）：**本地文件一律不再保存 webp**。
# 新命名目录只写 `.tiff`；`--write-webp` 仅供历史/对照，默认关。
WRITE_WEBP_DEFAULT = False
# ★ 原始切片 `-O`（口径件 `docs/image-original-crop-draft-v0.1.md`）：**默认开**
#   （Kevin 2026-10-11「输出时保留原始切片」）；`--no-original` 关；`--orig-only` 只出 O。
WRITE_ORIGINAL_DEFAULT = True

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


def write_tiff_idempotent_pixels(path: Path, arr, PIL_Image, np_, predictor: int | None = None) -> dict:
    """**按解码像素**幂等写 TIFF（口径件 §2「幂等」）。

    判据（**不得按文件 sha256** —— Pillow `tiff_deflate` 在大图上逐字节非确定）：

      * 文件已存在且**解码像素逐像素相等**（含 shape/dtype）**且**（`predictor is None`
        或 **容器合要求**：`Compression=8` ∧ `Predictor==predictor`）⇒ **不重写、不动字节**；
      * 否则写入（`predictor` 非空 ⇒ `tiffinfo={317: predictor}`，即 **Deflate ＋ Predictor=2**）。

    `predictor=None`（**校正件路径**）⇒ 只按解码像素判，**不查 / 不改编码**
    ⇒ 既有校正件的编码与字节**一字不动**（红线①）。
    `predictor=O_TIFF_PREDICTOR`（**O 件路径**）⇒ 旧编码 O 件会被**升级重写**为新编码
    （O 件系本轮新产物，不受「既有校正件不可动」约束）；重写后复跑即按像素＋容器双判跳过。

    返回 `{"written": bool, "action": str, "bytes": int}`；`action ∈
    {written, skip_pixels_and_container}`。解不开 / 像素不一致 ⇒ 覆盖写（并非静默跳过）。
    """
    want_tiffinfo = {TIFF_TAG_PREDICTOR: int(predictor)} if predictor else None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            with PIL_Image.open(path) as im:
                ondisk = np_.asarray(im)
                tag_pred = im.tag_v2.get(TIFF_TAG_PREDICTOR)
                tag_comp = im.tag_v2.get(TIFF_TAG_COMPRESSION)
            pixels_same = (
                ondisk.shape == arr.shape
                and ondisk.dtype == arr.dtype
                and bool(np_.array_equal(ondisk, arr))
            )
            container_ok = (
                predictor is None
                or (tag_pred == predictor and tag_comp == 8)
            )
            if pixels_same and container_ok:
                return {"written": False, "action": "skip_pixels_and_container",
                        "bytes": path.stat().st_size}
        except Exception:
            pass  # 解不开/坏件 ⇒ 落到下面覆盖写（不静默）
    kw = {"format": "TIFF", "compression": TIFF_COMPRESSION}
    if want_tiffinfo:
        kw["tiffinfo"] = want_tiffinfo
    PIL_Image.fromarray(np_.ascontiguousarray(arr)).save(path, **kw)
    return {"written": True, "action": "written", "bytes": path.stat().st_size}


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
    write_original: bool,
    orig_only: bool,
    only_pages: list[int] | None,
    limit_pages: int | None,
    limit_stamps: int | None,
    sample_names: set[str],
) -> dict:
    """单书出图 ⇒ 统计 dict（含 updates / failures / sample）。

    `write_original`（默认口径开）⇒ 每次裁切**额外**写 `…-O.tiff`（无颜色处理的原片）。
    `orig_only=True` ⇒ **只出 O 件**：不跑 V3、不写校正件、不写库（全量补 O 的最省路径）。
    """
    import numpy as np
    import cv2

    rows = book_rows(conn, pdf_name)
    by_page: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_page[int(r["page"])].append(r)
    pages = sorted(by_page)
    if only_pages:                                  # 子集/冒烟：只跑指定页（幂等可重入）
        want = set(int(p) for p in only_pages)
        pages = [p for p in pages if p in want]
    if limit_pages is not None:
        pages = pages[:limit_pages]

    out_dir = out_root / dir_key
    if write_files:
        out_dir.mkdir(parents=True, exist_ok=True)

    stat = {
        "pdf_name": pdf_name, "pdf_path": str(pdf_path), "dir_key": dir_key,
        "out_dir": safe_rel(out_dir),
        "pages": 0, "stamps": 0, "written_tiff": 0, "written_webp": 0, "failed": 0,
        "skipped_tiff_existing": 0,
        "written_original": 0, "skipped_original_existing": 0,
        "tiff_bytes": 0, "webp_bytes": 0, "max_tiff": None, "max_webp": None,
        "original_bytes": 0, "max_original": None, "original_files_touched": 0,
        "webp_written_this_run": 0,
        "elapsed_s": 0.0,
        "mode": ("orig-only" if orig_only else ("tiff+original" if write_original else "tiff-only")),
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
                tiff_name = naming.name_for(int(page), c, rr, ".tiff")
                webp_name = naming.name_for(int(page), c, rr, ".webp")
                orig_name = naming.name_for_original(int(page), c, rr, ".tiff")
                tiff_path = out_dir / tiff_name
                webp_path = out_dir / webp_name
                orig_path = out_dir / orig_name

                # ── ① 原始切片 O（**无颜色处理的原片**；同 bbox / 同渲染倍率 / 同容器 / 同目录）
                #    口径件 `docs/image-original-crop-draft-v0.1.md` §2；幂等按**解码像素**判。
                if write_original or orig_only:
                    if write_files:
                        try:
                            info_o = write_tiff_idempotent_pixels(orig_path, crop_bgr, PIL_Image, np, predictor=O_TIFF_PREDICTOR)
                        except Exception as exc:
                            failures.append({
                                "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                                "bbox": [x1, y1, x2, y2],
                                "reason": f"write_original_failed: {type(exc).__name__}: {exc}",
                            })
                            stat["failed"] += 1
                            continue
                        stat["original_files_touched"] += 1
                        stat["original_bytes"] += info_o["bytes"]
                        if info_o["written"]:
                            stat["written_original"] += 1
                        else:
                            stat["skipped_original_existing"] += 1
                        if stat["max_original"] is None or info_o["bytes"] > stat["max_original"]["bytes"]:
                            stat["max_original"] = {"name": orig_name, "bytes": info_o["bytes"],
                                                    "rel": safe_rel(orig_path)}

                # ── ② 校正件（V3 后像素；**只增文件** ⇒ 已存在且像素一致则不重写）
                corrected = None
                rep: dict = {}
                if not orig_only:
                    try:
                        corrected, rep = colorcal.correct_image_v3(crop_bgr)   # V3 默认口径
                    except Exception as exc:
                        failures.append({
                            "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                            "bbox": [x1, y1, x2, y2], "reason": f"colorcal_failed: {type(exc).__name__}: {exc}",
                        })
                        stat["failed"] += 1
                        continue

                if (not orig_only) and write_files:
                    try:
                        info_c = write_tiff_idempotent_pixels(tiff_path, corrected, PIL_Image, np)
                        if write_webp:                                                      # 口径默认关
                            PIL_Image.fromarray(np.ascontiguousarray(corrected)).save(
                                webp_path, format="WEBP", quality=WEBP_QUALITY)
                    except Exception as exc:
                        failures.append({
                            "pdf_name": pdf_name, "page": int(page), "idx": int(r["idx"]),
                            "bbox": [x1, y1, x2, y2],
                            "reason": f"write_failed: {type(exc).__name__}: {exc}",
                        })
                        stat["failed"] += 1
                        continue
                    tb = info_c["bytes"]
                    stat["tiff_bytes"] += tb
                    if info_c["written"]:
                        stat["written_tiff"] += 1
                    else:
                        stat["skipped_tiff_existing"] += 1
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

                if rep and tiff_name in sample_names and len(sample) < 200:
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
# 「只补缺列」幂等模式（P0 修后补数据 · 2026-10-11）
#   ★ 背景：池侧写库曾丢 `col`/`row`/`img_path_tiff` ⇒ 新 job 行**三列全 NULL**
#     （实证：黄牧甫印谱 job job-64bd… 200 行，TIFF 已实际写出 200 件）。
#   本模式**只补这 200 行**：逐行判「缺列」⇒ 按库内 bbox 复算 (C,R) ⇒ 期望
#   `output/books/<目录键>/P<页>-C<列>-R<行>.tiff` **必须在盘**才更新；
#   `img_path_tiff` 已有效且在盘的行**跳过**（幂等，复跑 0 更新）。
#   **不渲染、不重出图**（复用已落盘 TIFF）；**不写 `img_path`**（现有 10 列一字不改）。
# ──────────────────────────────────────────────────────────────────────────────
def fill_missing_columns(
    conn: sqlite3.Connection,
    books: list[str],
    out_root: Path,
    mapping: dict,
    *,
    root: Path = REPO,
) -> dict:
    """只对**缺列行**补 `col`/`row`/`img_path_tiff`（幂等、不渲染、不写 `img_path`）。

    「需补」判据（逐行）：`col` 为空 **或** `row` 为空 **或** `img_path_tiff` 空 **或**
    其指向文件不在盘。补法＝按库内 bbox（`x1..y2`，**不重跑检测**）用 `naming.assign_cr`
    复算 (C,R) ⇒ 期望路径；**该文件必须在盘**，否则逐条入失败清单（不静默跳过）。
    """
    updated = skipped = 0
    failures: list[dict] = []
    per_book: dict[str, dict] = {}
    for b in books:
        dir_key = naming.dir_key_for(b, mapping)
        rows = list(
            conn.execute(
                "SELECT id, page, idx, x1, y1, x2, y2, col, row, img_path_tiff FROM stamps "
                "WHERE pdf_name=? ORDER BY page, idx",
                (b,),
            )
        )
        by_page: dict[int, list[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            by_page[int(r["page"])].append(r)

        updates: list[tuple[int, int, str, int]] = []
        b_upd = b_skip = 0
        for page, prs in sorted(by_page.items()):
            bboxes = [(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])) for r in prs]
            pairs = naming.assign_cr(bboxes)
            for k, r in enumerate(prs):
                cur = str(r["img_path_tiff"]).strip() if r["img_path_tiff"] else ""
                on_disk = bool(cur) and (root / cur).is_file()
                need = (r["col"] is None) or (r["row"] is None) or (not cur) or (not on_disk)
                if not need:
                    b_skip += 1
                    continue
                c, rr = pairs[k]
                tiff_abs = (out_root / dir_key / naming.name_for(page, c, rr, ".tiff")).resolve()
                if not tiff_abs.is_file():
                    failures.append({
                        "pdf_name": b, "page": int(page), "idx": int(r["idx"]),
                        "reason": f"tiff_not_on_disk: {safe_rel(tiff_abs)}",
                    })
                    continue
                updates.append((int(c), int(rr), safe_rel(tiff_abs), int(r["id"])))
                b_upd += 1
        if updates:
            conn.executemany(
                "UPDATE stamps SET col=?, row=?, img_path_tiff=? WHERE id=?", updates
            )
            conn.commit()
        updated += b_upd
        skipped += b_skip
        per_book[b] = {"dir_key": dir_key, "rows": len(rows), "filled": b_upd, "skipped": b_skip}
    return {
        "mode": "fill-missing-cols-only",
        "note": "只补缺列；img_path_tiff 已有效且在盘的行跳过；不渲染、不写 img_path（10 列一字不改）。",
        "updated": updated,
        "skipped": skipped,
        "failures": failures,
        "per_book": per_book,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 核对（新列↔文件名、页内唯一、双向对账〔TIFF〕、webp 遗留清点、体量）
#   ★ 口径：本地文件**只认 `.tiff`**；既有 `.webp`（本人本轮已产者）**只列不删**，留删除单统一处置。
# ──────────────────────────────────────────────────────────────────────────────
def verify(conn: sqlite3.Connection, books: list[str], out_root: Path, mapping: dict,
           webp_list_cap: int = 200, expect_original: bool = True) -> dict:
    rows = list(conn.execute(
        f"SELECT {','.join(DB_COLS_10 + NEW_COLS)} FROM stamps "
        f"WHERE pdf_name IN ({','.join('?' * len(books))}) ORDER BY pdf_name, page, idx",
        tuple(books),
    ))
    name_re_tiff = naming.NAME_RE_TIFF
    name_re_orig = naming.NAME_RE_ORIG

    colname_mismatch: list[dict] = []
    null_new: list[dict] = []
    per_page: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
    db_tiff: set[str] = set()
    db_orig: set[str] = set()
    orig_name_mismatch = 0
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
        # O-1 命名：O 路径由命名**派生**（校正件名换 `-O`）⇒ 合名字形、无补零
        want_orig = naming.name_for_original(page, c, rr, ".tiff")
        if naming.original_name_from_corrected(want_tiff) != want_orig or not name_re_orig.match(want_orig):
            orig_name_mismatch += 1
        db_orig.add(str(out_root / dir_key / want_orig))

    # 页内 (C,R) 唯一
    dup_pages = []
    for (pdf_name, page), prs in per_page.items():
        if len(set(prs)) != len(prs):
            dups = [list(x) for x in naming.page_duplicate_pairs(prs)]
            dup_pages.append({"pdf_name": pdf_name, "page": page, "duplicates": dups})

    # 盘上文件：校正件（交付面）／原始切片 O／webp（遗留清点）／意外 P* 文件
    disk_tiff: set[str] = set()
    disk_orig: set[str] = set()
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
            elif name_re_orig.match(f.name):
                disk_orig.add(str(f))
            elif f.name.startswith("P") and f.suffix.lower() == ".webp" and naming.NAME_RE.match(f.name):
                disk_webp.append(str(f))
            elif f.name.startswith("P") and f.suffix.lower() in (".tiff", ".webp"):
                disk_other.append(str(f))

    missing_tiff = sorted(db_tiff - disk_tiff)
    orphan_tiff = sorted(disk_tiff - db_tiff)
    missing_orig = sorted(db_orig - disk_orig)
    orphan_orig = sorted(disk_orig - db_orig)

    return {
        "scope_books": books,
        "rows_in_scope": len(rows),
        "layout_spec": "TIFF-only（本地不再保存 webp；Kevin 2026-10-11 口径变更）"
                       " ＋ 原始切片 O（`-O` 后缀，2026-10-11 新增）",
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
        # O-1 命名 ＋ O-5 双向对账（原始切片）
        "original_crop": {
            "expect_original": bool(expect_original),
            "name_regex_orig": {"checked": len(rows) - len(null_new),
                                "mismatch_count": orig_name_mismatch},
            "two_way_reconcile_orig": {
                "db_expected_orig": len(db_orig), "disk_orig": len(disk_orig),
                "missing_orig": {"count": len(missing_orig), "detail": missing_orig[:50]},
                "orphan_orig": {"count": len(orphan_orig), "detail": orphan_orig[:50]},
            },
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
    """单张最大字节（对照 4 MiB）＋总体量（校正件 ＋ 原始切片 O）。"""
    max_tiff = {"bytes": -1, "path": None}
    max_webp = {"bytes": -1, "path": None}
    max_orig = {"bytes": -1, "path": None}
    n_tiff = n_webp = n_orig = 0
    sum_tiff = sum_webp = sum_orig = 0
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
            elif naming.NAME_RE_ORIG.match(f.name):
                b = f.stat().st_size
                n_orig += 1
                sum_orig += b
                if b > max_orig["bytes"]:
                    max_orig = {"bytes": b, "path": safe_rel(f), "name": f.name}
            elif f.suffix.lower() == ".webp" and naming.NAME_RE.match(f.name):
                b = f.stat().st_size
                n_webp += 1
                sum_webp += b
                if b > max_webp["bytes"]:
                    max_webp = {"bytes": b, "path": safe_rel(f), "name": f.name}
    return {
        "tiff_files": n_tiff, "webp_files": n_webp, "original_files": n_orig,
        "tiff_bytes": sum_tiff, "webp_bytes": sum_webp, "original_bytes": sum_orig,
        "tiff_total_mib": round(sum_tiff / 1048576, 3), "webp_total_mib": round(sum_webp / 1048576, 3),
        "original_total_mib": round(sum_orig / 1048576, 3),
        "original_mean_bytes": (round(sum_orig / n_orig, 1) if n_orig else None),
        "tiff_mean_bytes": (round(sum_tiff / n_tiff, 1) if n_tiff else None),
        "tiff_plus_original_total_mib": round((sum_tiff + sum_orig) / 1048576, 3),
        "max_tiff": max_tiff, "max_webp": max_webp, "max_original": max_orig,
        "limit_4mib": LIMIT_4MIB,
        "max_tiff_within_4mib": (max_tiff["bytes"] <= LIMIT_4MIB),
        "max_webp_within_4mib": (max_webp["bytes"] <= LIMIT_4MIB),
        "max_original_within_4mib": (max_orig["bytes"] <= LIMIT_4MIB),
        "webp_note": "webp 为本轮口径变更**之前**已产出的遗留件（只列不删）；"
                     "新口径 TIFF-only ⇒ 本次/复跑**不再产 webp**（webp_written=0）。",
        "original_note": "原始切片 O ＝ 400 dpi 渲染后按库内 bbox 原样的裁片（**无颜色处理**）；"
                         "单张最大字节对照 xiai 影像库 `store` 上限 4 MiB。",
    }


# ──────────────────────────────────────────────────────────────────────────────
# O-4 容器核对：O 件须 `mode=RGB` / `Photometric=2` / `Compression=8`（非 JPEG-in-TIFF）
# ──────────────────────────────────────────────────────────────────────────────
def container_check_original(books: list[str], out_root: Path, mapping: dict,
                             sample_cap: int = 30) -> dict:
    """抽样读 O 件 TIFF 标签 ⇒ O-4 容器判据读数（`mode`/`Photometric`/`Compression`）。

    口径件 §2「容器」：**TIFF · RGB 8-bit · Deflate**，**不得** JPEG-in-TIFF、不得 webp。
    """
    from PIL import Image as PIL_Image

    checked: list[dict] = []
    bad: list[dict] = []
    for pdf_name in books:
        d = out_root / naming.dir_key_for(pdf_name, mapping)
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if len(checked) >= sample_cap:
                break
            if not f.is_file() or not naming.NAME_RE_ORIG.match(f.name):
                continue
            try:
                with PIL_Image.open(f) as im:
                    t = im.tag_v2
                    rec = {
                        "name": f.name, "rel": safe_rel(f), "mode": im.mode,
                        "size": list(im.size),
                        "compression": t.get(259), "photometric": t.get(262),
                        "predictor": t.get(TIFF_TAG_PREDICTOR),
                        "samples_per_pixel": t.get(277), "bits_per_sample": t.get(258),
                    }
                ok = (rec["mode"] == "RGB" and rec["photometric"] == 2
                      and rec["compression"] == 8 and rec["predictor"] == O_TIFF_PREDICTOR)
                rec["ok"] = ok
                checked.append(rec)
                if not ok:
                    bad.append(rec)
            except Exception as exc:
                bad.append({"name": f.name, "rel": safe_rel(f), "ok": False,
                            "reason": f"{type(exc).__name__}: {exc}"})
    return {
        "criterion": "mode=RGB && Photometric=2 && Compression=8（Deflate） && Predictor=2；非 JPEG-in-TIFF",
        "checked": len(checked), "bad_count": len(bad),
        "all_ok": (len(bad) == 0 and len(checked) > 0),
        "sample": checked[:10], "bad": bad[:10],
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
    # 原始切片 O 的幂等读数（按**解码像素**判；口径件 §2）
    orig_checked = 0
    orig_pixel_mismatch: list[dict] = []
    orig_byte_same = 0
    orig_reencode_pixel_stable = True
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

            # ── 原始切片 O：盘上解码像素 ≡ 本轮重渲染的**原片**（无颜色处理）
            raw = rgb_page[y1:y2, x1:x2]
            orig_name = naming.name_for_original(page, c, rr, ".tiff")
            ofp = out_dir / orig_name
            if not ofp.is_file():
                orig_pixel_mismatch.append({"name": orig_name, "reason": "file_missing"})
            else:
                orig_checked += 1
                with PIL_Image.open(ofp) as im:
                    o_disk = np.array(im)
                if not np.array_equal(o_disk, raw):
                    orig_pixel_mismatch.append({
                        "name": orig_name, "reason": "decoded_pixels_differ_from_400dpi_render",
                        "max_abs_diff": int(np.abs(o_disk.astype(int) - raw.astype(int)).max()),
                    })
                import io
                buf = io.BytesIO()
                PIL_Image.fromarray(np.ascontiguousarray(raw)).save(
                    buf, format="TIFF", compression=TIFF_COMPRESSION,
                    tiffinfo={TIFF_TAG_PREDICTOR: O_TIFF_PREDICTOR})
                with PIL_Image.open(io.BytesIO(buf.getvalue())) as im2:
                    if not np.array_equal(np.array(im2), raw):
                        orig_reencode_pixel_stable = False
                if sha256_bytes(buf.getvalue()) == sha256_bytes(ofp.read_bytes()):
                    orig_byte_same += 1

            corrected, _ = colorcal.correct_image_v3(raw)
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
        "original": {
            "method": "decode-and-compare-pixels vs 400dpi render（原始切片 O）",
            "checked": orig_checked,
            "pixel_mismatch_count": len(orig_pixel_mismatch),
            "pixel_mismatch": orig_pixel_mismatch,
            "reencode_decoded_pixels_stable": orig_reencode_pixel_stable,
            "byte_identical_on_resave": orig_byte_same,
        },
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
    p.add_argument("--pages", action="append", type=int, default=[],
                   help="**只跑指定页**（1-based，可重复；对所有选中书生效；"
                        "子集/冒烟与幂等复跑用；与 --limit-pages 叠加）")
    p.add_argument("--limit-stamps", type=int, default=None, help="全局限枚（冒烟）")
    p.add_argument("--no-write-files", action="store_true", help="只算不落盘")
    p.add_argument("--no-write-db", action="store_true", help="不写新列")
    p.add_argument("--write-webp", action="store_true", default=WRITE_WEBP_DEFAULT,
                   help="【默认关】同时写 .webp（口径变更后本地不再保存 webp；仅供历史/对照）")
    og = p.add_mutually_exclusive_group()
    og.add_argument("--no-original", action="store_true",
                    help="【默认**开**原始切片 O 的情况下**关掉**】只出校正件"
                         "（回到 2026-10-11 本单之前的形态）")
    og.add_argument("--orig-only", action="store_true",
                    help="【只出原始切片 O】每次裁切只写 `…-O.tiff`（无颜色处理）；"
                         "**不跑 V3、不写校正件、不写库** —— 全量补 O 的最省路径"
                         "（也天然满足「不改既有校正件」红线）")
    p.add_argument("--no-migrate", action="store_true", help="跳过迁移（列须已存在）")
    p.add_argument("--verify-only", action="store_true", help="只核对已落盘/已落库，不渲染不写")
    p.add_argument("--fill-missing-cols", action="store_true",
                   help="【只补缺列】幂等模式：仅对 col/row/img_path_tiff 缺列的行补这三列"
                        "（img_path_tiff 已有效且在盘的行跳过）；不渲染、不写 img_path，可配 --all/--book")
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
    # 原始切片 O：默认开（口径件 `docs/image-original-crop-draft-v0.1.md`）；`--no-original` 关。
    write_original = bool(WRITE_ORIGINAL_DEFAULT and not args.no_original)
    orig_only = bool(args.orig_only)
    write_db = (not args.no_write_db) and (not orig_only)
    if orig_only:
        print("原始切片    = ON（--orig-only：只写 `…-O.tiff`，不跑 V3、不写校正件、不写库）")
    else:
        print(f"原始切片    = {'ON' if write_original else 'OFF（--no-original）'}"
              f"（`P<页>-C<列>-R<行>-O.tiff`，无颜色处理的原片）")

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
        "page_filter": (sorted(set(args.pages)) or None),
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
        "write_original": write_original,
        "orig_only": orig_only,
        "original_crop": {
            "enabled": write_original,
            "orig_only": orig_only,
            "suffix": naming.ORIGINAL_SUFFIX,
            "naming": "P<page>-C<col>-R<row>-O.tiff（大写 O、短横、不补零；后缀在扩展名之前）",
            "definition": "400 dpi 渲染后按库内 bbox 原样裁出，**不做任何颜色处理**",
            "container": "RGB 8-bit + tiff_deflate（与校正件同容器）",
            "落点": "output/books/<目录键>/（与校正件同目录）",
            "落库": "不新增列；O 路径由命名规则派生（校正件名换 `-O`）",
            "idempotency": "按解码像素判（不得按文件 sha256）",
        },
        "layout": ("tiff+original" if (write_original and not orig_only)
                   else ("original-only" if orig_only
                         else ("tiff-only" if not args.write_webp else "tiff+webp"))),
        "render_dpi": 400,
        "naming": "P<page>-C<col>-R<row> (大写/短横/不补零)",
        "per_book": {},
        "failures": [],
        "correction_sample": [],
        "fp10_before": fp_before, "fp10_rows_before": n_before,
    }

    if args.verify_only:
        books_stat = {}
    elif args.fill_missing_cols:
        # 【只补缺列】：不渲染、不重出图 —— 复用已落盘 TIFF 把缺列的 200 行补上（幂等）。
        print(f"\n=== 【只补缺列】模式（{len(books)} 本；不渲染、不写 img_path）===")
        fill = fill_missing_columns(conn, books, out_root, mapping)
        report["fill_missing_cols"] = fill
        for b, s in fill["per_book"].items():
            print(f"  · {b[:28]:<28} 行 {s['rows']:>5} / 补 {s['filled']:>4} / 跳 {s['skipped']:>5}"
                  f"  → output/books/{s['dir_key']}/")
        print(f"  合计：补 {fill['updated']} 行、跳 {fill['skipped']} 行、失败 {len(fill['failures'])} 条")
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
                write_db=write_db, write_webp=args.write_webp,
                write_original=write_original, orig_only=orig_only,
                only_pages=sorted(set(args.pages)) or None,
                limit_pages=args.limit_pages,
                limit_stamps=args.limit_stamps, sample_names=s_names,
            )
            report["correction_sample"].extend(st.pop("_sample"))
            report["failures"].extend(st.pop("_failures"))
            st.pop("_updates", None)
            report["per_book"][b] = st
            print(f"  ✓ {st['stamps']} 枚（页 {st['pages']}，失败 {st['failed']}）"
                  f"｜校正件 新写 {st['written_tiff']} / 跳（像素一致）{st['skipped_tiff_existing']}"
                  f"｜O 件 新写 {st['written_original']} / 跳 {st['skipped_original_existing']}"
                  f"（{st['original_bytes']/1048576:.2f} MiB）"
                  f"｜用时 {st['elapsed_s']}s  → {st['out_dir']}", flush=True)
        report["elapsed_s_total"] = round(time.time() - t_all, 3)

    # ── 收尾：指纹 ＋ 核对 ＋ 体量 ＋ 幂等 ─────────────────────────────────────
    fp_after, n_after = _col_fingerprint(conn)
    report["fp10_after"] = fp_after
    report["fp10_rows_after"] = n_after
    report["fp10_identical"] = (fp_before == fp_after) and (n_before == n_after)

    vchk = verify(conn, books, out_root, mapping, expect_original=(write_original or orig_only))
    report["checks"] = vchk
    report["sizes"] = size_report(conn, books, out_root, mapping)
    report["o4_container_check"] = container_check_original(books, out_root, mapping)

    report["totals"] = {
        "stamps_in_scope": sum(st.get("stamps", 0) for st in report["per_book"].values()) if report["per_book"] else None,
        "written_tiff": report["sizes"]["tiff_files"],
        "written_original": report["sizes"]["original_files"],
        "tiff_written_this_run": sum(st.get("written_tiff", 0) for st in report["per_book"].values()),
        "tiff_skipped_existing": sum(st.get("skipped_tiff_existing", 0) for st in report["per_book"].values()),
        "original_written_this_run": sum(st.get("written_original", 0) for st in report["per_book"].values()),
        "original_skipped_existing": sum(st.get("skipped_original_existing", 0) for st in report["per_book"].values()),
        "webp_written_this_run": sum(st.get("webp_written_this_run", 0) for st in report["per_book"].values()),
        "webp_present_legacy": report["sizes"]["webp_files"],
        "failures": len(report["failures"]),
        "tiff_bytes": report["sizes"]["tiff_bytes"],
        "webp_bytes": report["sizes"]["webp_bytes"],
        "original_bytes": report["sizes"]["original_bytes"],
    }

    # 幂等核对（渲染模式跑；fill-missing-cols 不产图 ⇒ 无需像素幂等探针）
    if args.fill_missing_cols:
        report["idempotency"] = {
            "skipped": "fill-missing-cols-only 模式不渲染、不产图；新列落库的幂等由复跑同一模式证明"
                       "（第二次全部 skipped、updated=0）。"
        }
    else:
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
    print(f"校正件（交付面）：盘上 {report['sizes']['tiff_files']} 件 / "
          f"{report['sizes']['tiff_total_mib']} MiB（本次新写 {report['totals']['tiff_written_this_run']}、"
          f"像素一致跳过 {report['totals']['tiff_skipped_existing']}）")
    print(f"原始切片 O ：盘上 {report['sizes']['original_files']} 件 / "
          f"{report['sizes']['original_total_mib']} MiB"
          f"（本次新写 {report['totals']['original_written_this_run']}、"
          f"像素一致跳过 {report['totals']['original_skipped_existing']}）"
          f"｜均 {report['sizes']['original_mean_bytes']} B/件")
    print(f"O 单张最大 {report['sizes']['max_original']['bytes']} B"
          f"（≤4MiB: {report['sizes']['max_original_within_4mib']}）"
          f"｜{report['sizes']['max_original'].get('name')}")
    print(f"O-4 容器抽样 {report['o4_container_check']['checked']} 件 ⇒ "
          f"mode=RGB/Photometric=2/Compression=8 全对: {report['o4_container_check']['all_ok']}")
    print(f"本次写 webp 数 = {report['totals']['webp_written_this_run']}"
          f"；盘上遗留 webp（口径变更前已产，只列不删）= {report['sizes']['webp_files']} 件")
    print(f"单张最大 TIFF {report['sizes']['max_tiff']['bytes']} B（≤4MiB: {report['sizes']['max_tiff_within_4mib']}）")
    print(f"页内 (C,R) 冲突页：{vchk['page_cr_unique']['conflicts']}；空新列：{vchk['null_new_columns']['count']}；"
          f"名不符：{vchk['name_regex_tiff']['mismatch_count']}")
    tw = vchk["two_way_reconcile_tiff"]
    print(f"双向对账（TIFF）：库期望 {tw['db_expected_tiff']} / 盘上 {tw['disk_tiff']}；"
          f"缺 {tw['missing_tiff']['count']} / 孤儿 {tw['orphan_tiff']['count']}；"
          f"意外 P* 文件 {tw['unexpected_P_files']['count']}")
    ow = vchk["original_crop"]["two_way_reconcile_orig"]
    print(f"双向对账（原始切片 O-5）：库期望 {ow['db_expected_orig']} / 盘上 {ow['disk_orig']}；"
          f"缺 {ow['missing_orig']['count']} / 孤儿 {ow['orphan_orig']['count']}；"
          f"命名不符 {vchk['original_crop']['name_regex_orig']['mismatch_count']}")
    print(f"失败清单：{len(report['failures'])} 条")
    print(f"证据：{outp}")

    orig_ok = True
    if (write_original or orig_only) and not args.no_write_files and not args.verify_only:
        o = vchk["original_crop"]
        ow = o["two_way_reconcile_orig"]
        orig_ok = (
            o["name_regex_orig"]["mismatch_count"] == 0
            and ow["missing_orig"]["count"] == 0
            and ow["orphan_orig"]["count"] == 0
            and report["o4_container_check"]["all_ok"]
        )
    ok = (
        report["fp10_identical"]
        and vchk["page_cr_unique"]["conflicts"] == 0
        and vchk["null_new_columns"]["count"] == 0
        and vchk["name_regex_tiff"]["mismatch_count"] == 0
        and tw["missing_tiff"]["count"] == 0 and tw["orphan_tiff"]["count"] == 0
        and tw["unexpected_P_files"]["count"] == 0
        and orig_ok
        and len(report["failures"]) == 0
        and len(report.get("fill_missing_cols", {}).get("failures", [])) == 0
    )
    print(f"\n== {'GREEN' if ok else 'RED（见失败清单/核对详表）'} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
