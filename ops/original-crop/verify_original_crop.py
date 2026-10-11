#!/usr/bin/env python
"""印面**原始切片 `-O`** 子集验收（Kong / 原始切片单 · 2026-10-11）。

口径真源：`docs/image-original-crop-draft-v0.1.md`（§2 默认口径 / §4 验收候选 O-1〜O-5）。

本脚本**独立复算**（不复用回填脚本的中间态），逐行给读数：

  * **O-1 命名**：`P<页>-C<列>-R<行>-O.tiff` 存在性 ＋ 逐行合正则、无补零；
  * **O-2 原始性（最强判据）**：O 件**解码像素 ≡ 400 dpi 渲染原片**（逐像素相等，== 行数）
    **且**「O ≠ 校正件」的**计数 == V3-applied 的行数**（用 `colorcal.correct_image_v3` 的 `mode`
    分类 —— V3 `skipped(ink_ratio<2%)` 行 V3 是 **no-op** ⇒ 校正件本就 ≡ 原片 ⇒ **O == 校正件合法**）；
  * **O-3 几何一致**：O 与同页同 `(C,R)` 校正件**尺寸逐行相等**；
  * **O-4 容器**：`mode=RGB`、`Photometric=2`、`Compression=8`（Deflate）、`Predictor=2`、非 JPEG-in-TIFF；
  * **O-5 双向对账**：库行数 × 2 ＝ 盘上两类文件数（两方向计数）。
  * 附加读数：**O 件单张最大字节**（对照 xiai 4 MiB）／O 件总体积与均值／单枚与单页耗时。

**只读**：不写盘、不写库（唯一写件 ＝ 本脚本的 `--out` 汇总 JSON）。

用法：
    cd <feicui> && ./venv/bin/python ops/original-crop/verify_original_crop.py \
        --book "秦印类编 检索版.pdf" --page 40 --page 300 \
        --book "福庵印缀 原版 高清.pdf" --page 18 --page 30 \
        --out ops/original-crop/subset_verify.json

★ 渲染/裁切一律**复用实现模块**（`processor.render_page` / `app.naming` / `app.colorcal`），
  不手写等价式（家法：颜色 / 几何量判据必须调实现模块的函数）。
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
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO / "server"
sys.path.insert(0, str(SERVER_DIR))
from app import naming, colorcal  # noqa: E402

DEFAULT_DB = REPO.parent / "data" / "yinpu.db"
DEFAULT_OUT_ROOT = REPO / "output" / "books"
TIFF_COMPRESSION = "tiff_deflate"
LIMIT_4MIB = 4 * 1024 * 1024


def load_processor():
    """`processor.py` 按**文件路径**加载（仓根 `feicui/app.py` 会遮蔽 `server/app` 包名）。"""
    spec = importlib.util.spec_from_file_location("feicui_processor", str(REPO / "processor.py"))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="印面原始切片 -O 子集验收（只读）")
    p.add_argument("--db", default=str(os.environ.get("FEICUI_DB") or DEFAULT_DB))
    p.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    p.add_argument("--book", action="append", default=[], help="书（PDF 名，逐字；可重复）")
    p.add_argument("--page", action="append", type=int, default=[], help="页号（可重复）")
    p.add_argument("--pdf-dir", action="append", default=[], help="PDF 搜索目录（可重复）")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "subset_verify.json"))
    p.add_argument("--corrected-hashes-before", default=None,
                   help="『校正件字节未变』自证用的 before 指纹 JSON（由 --hash-corrected 产物给出）")
    p.add_argument("--hash-corrected", action="store_true",
                   help="【模式】只做：对所选 (书, 页) 的**既有校正件**逐件 sha256 并落盘（before 取证）")
    return p


def resolve_pdf(pdf_name: str, search_dirs: list[Path]) -> Path | None:
    for d in search_dirs:
        p = Path(d).expanduser() / pdf_name
        if p.is_file():
            return p
    inbox = REPO / "inbox"
    if inbox.is_dir():
        for p in sorted(inbox.rglob(pdf_name)):
            if p.is_file():
                return p
    return None


def row_ids_for(conn, pdf_name: str, pages: list[int]) -> dict[int, list[sqlite3.Row]]:
    by_page: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(
        "SELECT id, page, idx, col, row, img_path_tiff, x1, y1, x2, y2 FROM stamps "
        "WHERE pdf_name=? ORDER BY page, idx",
        (pdf_name,),
    ):
        by_page[int(r["page"])].append(r)
    return {p: by_page[p] for p in pages if p in by_page}


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    out_root = Path(args.out_root).resolve()
    db_path = Path(args.db).resolve()
    search_dirs = [Path(d).expanduser() for d in args.pdf_dir] + [REPO, Path.home() / "Downloads"]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    mapping = naming.load_dir_keys()
    pages = sorted(set(args.page))

    # ── 模式：只取「既有校正件」before 指纹 ────────────────────────────────────
    if args.hash_corrected:
        hashes: dict[str, str] = {}
        n = 0
        for b in args.book:
            dir_key = naming.dir_key_for(b, mapping)
            d = out_root / dir_key
            for pg, rows in row_ids_for(conn, b, pages).items():
                for r in rows:
                    c, rr = int(r["col"]), int(r["row"])
                    fp = d / naming.name_for(pg, c, rr, ".tiff")
                    if fp.is_file():
                        hashes[str(fp)] = sha256_file(fp)
                        n += 1
        print(json.dumps({"corrected_files_hashed": n, "sample": dict(list(hashes.items())[:3])},
                         ensure_ascii=False, indent=2))
        Path(args.out).write_text(json.dumps({"corrected_sha256_before": hashes},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"before 指纹已落盘：{args.out}")
        conn.close()
        return 0

    import numpy as np
    import cv2
    from PIL import Image as PIL_Image
    processor = load_processor()

    before: dict[str, str] = {}
    if args.corrected_hashes_before and Path(args.corrected_hashes_before).is_file():
        before = json.loads(Path(args.corrected_hashes_before).read_text(encoding="utf-8"))\
            .get("corrected_sha256_before", {})

    rep: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "criterion_source": "docs/image-original-crop-draft-v0.1.md §2/§4（O-1〜O-5）",
        "db_path": str(db_path), "out_root": str(out_root),
        "page_filter": pages,
        "render_dpi": processor.RENDER_DPI,
        "per_book": {},
        "rows": [],
        "failures": [],
        "timing": {},
        "corrected_bytes_unchanged": {},
    }

    t_all = time.time()
    # O-1/O-3/O-4/O-5 计数
    n_rows = 0
    n_o_present = n_o_missing = 0
    n_o_name_ok = 0
    n_o_pixels_equal_render = 0
    n_o_pixels_differ_corrected = 0
    n_v3_applied = 0
    n_o_same_size_as_corrected = 0
    n_container_ok = 0
    o_sizes: list[int] = []
    corr_sizes: list[int] = []
    db_expected_o: set[str] = set()
    db_expected_c: set[str] = set()
    disk_o: set[str] = set()
    disk_corr: set[str] = set()
    per_page_timing: list[dict] = []

    for b in args.book:
        pdf_path = resolve_pdf(b, search_dirs)
        dir_key = naming.dir_key_for(b, mapping)
        out_dir = out_root / dir_key
        print(f"\n=== {b}  → output/books/{dir_key}/ ===", flush=True)
        if pdf_path is None:
            rep["per_book"][b] = {"pdf_found": False, "dir_key": dir_key}
            rep["failures"].append({"pdf_name": b, "reason": "pdf_not_found"})
            print("  ✗ PDF 未找到 ⇒ 该本入失败清单")
            continue
        by_page = row_ids_for(conn, b, pages)
        doc = processor.pymupdf.open(str(pdf_path))
        b_stat = {"pdf_path": str(pdf_path), "pages": {}, "pdf_found": True}
        try:
            for pg, page_rows in sorted(by_page.items()):
                t0 = time.time()
                page_img = processor.render_page(doc[pg - 1])       # 400 dpi（生产同口径），BGR
                H, W = page_img.shape[:2]
                rgb_page = cv2.cvtColor(page_img, cv2.COLOR_BGR2RGB)
                bboxes = [(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])) for r in page_rows]
                pairs = naming.assign_cr(bboxes)
                naming.assert_page_unique(pairs)
                pg_stat = {"stamps": 0, "o_present": 0, "o_missing": 0,
                           "pixels_equal_render": 0, "pixels_differ_corrected": 0,
                           "same_size_as_corrected": 0, "container_ok": 0, "elapsed_s": 0.0}
                for k, r in enumerate(page_rows):
                    c, rr = pairs[k]
                    x1, y1, x2, y2 = (int(round(v)) for v in bboxes[k])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(W, x2), min(H, y2)
                    raw = rgb_page[y1:y2, x1:x2]                     # 400 dpi 渲染原片（无处理）
                    o_name = naming.name_for_original(pg, c, rr, ".tiff")
                    c_name = naming.name_for(pg, c, rr, ".tiff")
                    o_path = out_dir / o_name
                    c_path = out_dir / c_name
                    db_expected_o.add(str(o_path))
                    db_expected_c.add(str(c_path))
                    n_rows += 1
                    pg_stat["stamps"] += 1
                    rec = {"pdf_name": b, "page": pg, "idx": int(r["idx"]), "col": c, "row": rr,
                           "o_name": o_name, "corrected_name": c_name,
                           "bbox": [x1, y1, x2, y2], "raw_size": [int(raw.shape[1]), int(raw.shape[0])]}

                    # O-1 命名（存在性 ＋ 名字形 ＋ 与校正件名派生一致）
                    name_ok = bool(naming.NAME_RE_ORIG.match(o_name)) and \
                        naming.original_name_from_corrected(c_name) == o_name
                    rec["o1_name_ok"] = name_ok
                    n_o_name_ok += int(name_ok)
                    if o_path.is_file():
                        n_o_present += 1
                        pg_stat["o_present"] += 1
                    else:
                        n_o_missing += 1
                        pg_stat["o_missing"] += 1
                        rep["failures"].append({"pdf_name": b, "page": pg, "idx": int(r["idx"]),
                                                "reason": f"o_missing: {o_name}"})
                        rep["rows"].append(rec)
                        continue

                    # O-2 原始性：解码像素 ≡ 渲染原片
                    with PIL_Image.open(o_path) as im:
                        o_arr = np.asarray(im)
                        t = im.tag_v2
                        rec["o_mode"] = im.mode
                        rec["o_size"] = list(im.size)
                        rec["o_compression"] = t.get(259)
                        rec["o_photometric"] = t.get(262)
                        rec["o_predictor"] = t.get(317)
                        rec["o_bits_per_sample"] = t.get(258)
                    o_sz = o_path.stat().st_size
                    o_sizes.append(o_sz)
                    rec["o_bytes"] = o_sz
                    eq = (o_arr.shape == raw.shape and o_arr.dtype == raw.dtype
                          and bool(np.array_equal(o_arr, raw)))
                    rec["o2_pixels_equal_400dpi_render"] = eq
                    if eq:
                        n_o_pixels_equal_render += 1
                        pg_stat["pixels_equal_render"] += 1
                    else:
                        rep["failures"].append({
                            "pdf_name": b, "page": pg, "idx": int(r["idx"]),
                            "reason": "o2_decoded_pixels_differ_from_render",
                            "max_abs_diff": (int(np.abs(o_arr.astype(int) - raw.astype(int)).max())
                                             if o_arr.shape == raw.shape else None)})

                    # O-4 容器（含 Predictor=2）
                    container_ok = (rec["o_mode"] == "RGB" and rec["o_photometric"] == 2
                                    and rec["o_compression"] == 8 and rec["o_predictor"] == 2)
                    rec["o4_container_ok"] = container_ok
                    n_container_ok += int(container_ok)
                    pg_stat["container_ok"] += int(container_ok)

                    # O-2 后半：O ≠ 校正件（校正件背景纯白 / O 保留原背景）
                    if c_path.is_file():
                        with PIL_Image.open(c_path) as imc:
                            c_arr = np.asarray(imc)
                        rec["corrected_size"] = list(imc.size)
                        corr_sizes.append(c_path.stat().st_size)
                        # O-3 几何一致
                        size_eq = (imc.size == tuple(rec["o_size"]))
                        rec["o3_same_size_as_corrected"] = size_eq
                        n_o_same_size_as_corrected += int(size_eq)
                        pg_stat["same_size_as_corrected"] += int(size_eq)
                        if not size_eq:
                            rep["failures"].append({
                                "pdf_name": b, "page": pg, "idx": int(r["idx"]),
                                "reason": "o3_size_mismatch",
                                "o_size": list(im.size), "corrected_size": list(imc.size)})
                        # O-2 分类：调实现模块判 V3 是否 applied（applied 行 O 必须 ≠ 校正件；
                        #   skipped(ink_ratio<2%) 行 V3 是 no-op ⇒ 校正件 ≡ 原片 ⇒ O == 校正件合法）。
                        _corr_v3, rep_v3 = colorcal.correct_image_v3(raw)
                        v3_applied = (rep_v3.get("mode") == "applied")
                        rec["v3_mode"] = rep_v3.get("mode")
                        rec["v3_marker"] = rep_v3.get("marker")
                        n_v3_applied += int(v3_applied)
                        # O ≠ 校正件（逐像素）
                        differ = not (c_arr.shape == o_arr.shape and bool(np.array_equal(c_arr, o_arr)))
                        rec["o2_o_differs_from_corrected"] = differ
                        n_o_pixels_differ_corrected += int(differ)
                        pg_stat["pixels_differ_corrected"] += int(differ)
                        # 判决：applied 行须 differ；skipped 行须相等（O == 校正件）
                        if v3_applied and not differ:
                            rep["failures"].append({"pdf_name": b, "page": pg, "idx": int(r["idx"]),
                                                    "reason": "o2_applied_row_o_equals_corrected"})
                        if (not v3_applied) and differ:
                            rep["failures"].append({"pdf_name": b, "page": pg, "idx": int(r["idx"]),
                                                    "reason": "o2_skipped_row_o_differs_corrected"})
                    else:
                        rec["o3_same_size_as_corrected"] = None
                        rec["o2_o_differs_from_corrected"] = None
                        rep["failures"].append({"pdf_name": b, "page": pg, "idx": int(r["idx"]),
                                                "reason": f"corrected_missing: {c_name}"})
                    rep["rows"].append(rec)

                # 盘上文件清点（该页目标名）
                pg_stat["elapsed_s"] = round(time.time() - t0, 3)
                per_page_timing.append({"pdf_name": b, "page": pg, **pg_stat})
                b_stat["pages"][str(pg)] = pg_stat
                print(f"  p{pg}: {pg_stat['stamps']} 枚｜O 在盘 {pg_stat['o_present']}｜"
                      f"像素≡渲染原片 {pg_stat['pixels_equal_render']}｜"
                      f"≠校正件 {pg_stat['pixels_differ_corrected']}｜"
                      f"同尺寸 {pg_stat['same_size_as_corrected']}｜"
                      f"容器对 {pg_stat['container_ok']}｜{pg_stat['elapsed_s']}s", flush=True)
        finally:
            doc.close()
        # 双向对账（**限本子集的页**：只清点页号落在 `--page` 集合内的件，
        #   与「库期望集合」同轴 ⇒ 全量跑过的盘也不会被误报成孤儿）
        page_set = set(pages)
        if out_dir.is_dir():
            for f in out_dir.iterdir():
                if not f.is_file():
                    continue
                info = naming.parse_original_name(f.name)
                if info is not None:
                    if info["page"] in page_set:
                        disk_o.add(str(f))
                    continue
                info = naming.parse_name(f.name)
                if info is not None and info["page"] in page_set:
                    disk_corr.add(str(f))
        rep["per_book"][b] = b_stat

    rep["elapsed_s_total"] = round(time.time() - t_all, 3)
    # 双向对账（**子集页**限定的库期望集合 ↔ 该本盘上实际件）
    miss_o = sorted(db_expected_o - disk_o)
    orph_o = sorted(disk_o - db_expected_o)
    miss_c = sorted(db_expected_c - disk_corr)

    tot_o = sum(o_sizes)
    tot_c = sum(corr_sizes)
    rep["summary"] = {
        "books": args.book, "pages": pages,
        "rows_checked": n_rows,
        "O-1 naming": {"rows": n_rows, "name_ok": n_o_name_ok,
                       "mismatch": n_rows - n_o_name_ok,
                       "o_present": n_o_present, "o_missing": n_o_missing},
        "O-2 originality": {
            "decoded_pixels_equal_400dpi_render": n_o_pixels_equal_render,
            "o_differs_from_corrected": n_o_pixels_differ_corrected,
            "v3_applied_rows": n_v3_applied,
            "o2_expected_differs": n_v3_applied,
            "rows": n_rows,
            "criterion": "解码像素 ≡ 400dpi 渲染原片（计数 == 行数）且 「O ≠ 校正件」计数 == V3-applied 行数"
                         "（V3 skipped(ink_ratio<2%) 行 V3 是 no-op ⇒ 校正件 ≡ 原片 ⇒ O == 校正件合法）",
        },
        "O-3 geometry": {"same_size_as_corrected": n_o_same_size_as_corrected, "rows": n_rows},
        "O-4 container": {"ok_rows": n_container_ok, "rows": n_rows,
                          "criterion": "mode=RGB && Photometric=2 && Compression=8 && Predictor=2"},
        "O-5 two_way_reconcile": {
            "db_expected_o_subset": len(db_expected_o), "disk_o_total": len(disk_o),
            "disk_corrected_total": len(disk_corr),
            "missing_o": {"count": len(miss_o), "detail": miss_o[:20]},
            "orphan_o": {"count": len(orph_o), "detail": orph_o[:20]},
            "missing_corrected": {"count": len(miss_c), "detail": miss_c[:20]},
        },
        "sizes": {
            "o_files": len(o_sizes), "o_total_bytes": tot_o,
            "o_total_mib": round(tot_o / 1048576, 3),
            "o_mean_bytes": round(tot_o / len(o_sizes), 1) if o_sizes else None,
            "o_max_bytes": max(o_sizes) if o_sizes else None,
            "o_max_rel": None, "limit_4mib": LIMIT_4MIB,
            "o_max_within_4mib": (max(o_sizes) <= LIMIT_4MIB) if o_sizes else None,
            "corrected_total_bytes": tot_c,
            "corrected_total_mib": round(tot_c / 1048576, 3),
            "corrected_mean_bytes": round(tot_c / len(corr_sizes), 1) if corr_sizes else None,
            "ratio_o_over_corrected": round(tot_o / tot_c, 3) if tot_c else None,
        },
        "timing": {
            "elapsed_s_total": rep["elapsed_s_total"],
            "pages": len(per_page_timing),
            "per_page": per_page_timing,
            "stamps": n_rows,
            "ms_per_stamp_incl_render": (round(rep["elapsed_s_total"] * 1000 / n_rows, 1)
                                         if n_rows else None),
            "s_per_page": (round(rep["elapsed_s_total"] / len(per_page_timing), 3)
                           if per_page_timing else None),
        },
    }
    # 单张最大 O（找 rel）
    if o_sizes:
        for p in db_expected_o:
            if Path(p).is_file() and Path(p).stat().st_size == max(o_sizes):
                try:
                    rep["summary"]["sizes"]["o_max_rel"] = str(Path(p).resolve().relative_to(REPO))
                except ValueError:
                    rep["summary"]["sizes"]["o_max_rel"] = str(p)
                break

    # 『已存在校正件字节未变』自证（before vs after）
    if before:
        unchanged = changed = missing = 0
        changed_list = []
        for path, h_before in before.items():
            fp = Path(path)
            if not fp.is_file():
                missing += 1
                continue
            if sha256_file(fp) == h_before:
                unchanged += 1
            else:
                changed += 1
                changed_list.append(path)
        rep["corrected_bytes_unchanged"] = {
            "checked": len(before), "unchanged": unchanged, "changed": changed,
            "missing": missing, "changed_detail": changed_list[:20],
            "criterion": "既有校正件 sha256 before ≡ after（红线①「只增文件」）",
        }

    rep["verdict"] = {
        "O-1": rep["summary"]["O-1 naming"]["mismatch"] == 0 and n_o_missing == 0,
        "O-2": (n_o_pixels_equal_render == n_rows
                and n_o_pixels_differ_corrected == n_v3_applied),
        "O-3": n_o_same_size_as_corrected == n_rows,
        "O-4": n_container_ok == n_rows,
        "O-5": (len(miss_o) == 0 and len(orph_o) == 0),
        "corrected_bytes_unchanged": (not before) or rep["corrected_bytes_unchanged"]["changed"] == 0,
    }
    rep["verdict_all_pass"] = all(rep["verdict"].values())

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    print("\n===== 子集验收汇总 =====")
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=2)[:4000])
    print("\n判决：", json.dumps(rep["verdict"], ensure_ascii=False),
          "⇒ ALL PASS:", rep["verdict_all_pass"])
    print(f"失败清单 {len(rep['failures'])} 条；证据 {args.out}")
    return 0 if rep["verdict_all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
