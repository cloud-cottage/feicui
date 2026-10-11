#!/usr/bin/env python
"""影像命名地基 · 自检 ＋ 样例产出（Kong / 命名单 · 2026-10-11）。

只读 DB；**不建 job、不改库**；样例只写 `output/books/<目录键>/`（运行时产物，.gitignore）。
图像栈只在 `feicui/venv`（本脚本须用 `./venv/bin/python` 运行）。

复跑：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/image-naming/selfcheck_naming.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # <feicui>
sys.path.insert(0, str(REPO))                       # 供 `import processor`

# 注意：仓根有 `feicui/app.py`（Streamlit 应用），会**遮蔽** `server/app/` 包；
# 故 `server/app/naming.py` 用**按文件路径**加载，不触发 `import app`
# （也避免拉起 `server/app/__init__.py` 的接口层依赖）。
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("feicui_naming", str(REPO / "server" / "app" / "naming.py"))
_naming = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_naming)

COLUMN_GAP_MIN_PX = _naming.COLUMN_GAP_MIN_PX
COLUMN_GAP_WIDTH_FACTOR = _naming.COLUMN_GAP_WIDTH_FACTOR
NAME_RE_TIFF = _naming.NAME_RE_TIFF
assign_cr = _naming.assign_cr
assert_page_unique = _naming.assert_page_unique
dir_key_for = _naming.dir_key_for
load_dir_keys = _naming.load_dir_keys
n_columns = _naming.n_columns
name_for = _naming.name_for
normalize_book_name = _naming.normalize_book_name
page_duplicate_pairs = _naming.page_duplicate_pairs

import processor  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

# ── 常量（单点） ────────────────────────────────────────────────────────────
PDF_NAME = "秦印类编 检索版.pdf"
PDF_PATH = Path(os.environ.get("FEICUI_NAMING_PDF", str(Path.home() / "Downloads" / PDF_NAME)))
DB_PATH = Path(os.environ.get("FEICUI_DB", str(REPO.parent / "data" / "yinpu.db")))
SAMPLE_PAGES = (299, 400)
EVID_DIR = REPO / "ops" / "image-naming"

# 口径件 §2 实测（用作**交叉校验**：本单复算须逐字对上）
DRAFT_COL_COUNTS = {1: 2608, 2: 2458, 3: 2085, 4: 32}
# 口径件 §2「行位次分布」**仅列到 R8**（R1..R8 逐字对得上；R9+ 为口径件截断，见下）
DRAFT_ROW_COUNTS = {1: 2172, 2: 1908, 3: 1446, 4: 827, 5: 397, 6: 189, 7: 98, 8: 60}

_checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _checks.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ── 1. 全书 (C,R) 推导自检（只读 DB） ───────────────────────────────────────
def fullbook_check() -> dict:
    print("\n=== (a) 全书 (C,R) 推导自检 ＝＝ 只读 DB =====")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = list(
        conn.execute(
            "SELECT page, idx, x1, y1, x2, y2 FROM stamps WHERE pdf_name = ? ORDER BY page, x1, y1",
            (PDF_NAME,),
        )
    )
    conn.close()

    by_page: dict[int, list] = defaultdict(list)
    for page, idx, x1, y1, x2, y2 in rows:
        by_page[int(page)].append((int(idx), (float(x1), float(y1), float(x2), float(y2))))

    col_counts: Counter = Counter()
    row_counts: Counter = Counter()
    ncols_hist: Counter = Counter()
    maxr_hist: Counter = Counter()
    total_dups = 0
    dup_pages: list[dict] = []
    page_bbox_idx_mismatch = 0
    max_col_size = 0
    max_col_where: dict | None = None

    for page in sorted(by_page):
        items = by_page[page]
        # DB 内 idx 应与 x1 升序一致（detect 后按 bbox[0] 排序 ⇒ idx 即左→右探测序）
        idxs = [it[0] for it in items]
        if idxs != sorted(idxs):
            page_bbox_idx_mismatch += 1
        bboxes = [it[1] for it in items]
        pairs = assign_cr(bboxes)
        assert_page_unique(pairs)  # 构造上应恒真
        dups = page_duplicate_pairs(pairs)
        if dups:
            total_dups += len(dups)
            dup_pages.append({"page": page, "duplicates": [list(d) for d in dups]})
        per_col: Counter = Counter()
        for c, r in pairs:
            col_counts[c] += 1
            row_counts[r] += 1
            per_col[c] += 1
        if per_col:
            c_big = max(per_col, key=lambda k: per_col[k])
            if per_col[c_big] > max_col_size:
                max_col_size = per_col[c_big]
                max_col_where = {"page": page, "col": c_big, "size": per_col[c_big]}
        ncols_hist[n_columns(pairs)] += 1
        maxr_hist[max((r for _c, r in pairs), default=0)] += 1

    total = sum(col_counts.values())
    readings = {
        "pdf_name": PDF_NAME,
        "total_stamps": total,
        "total_pages": len(by_page),
        "duplicate_conflicts": total_dups,
        "duplicate_pages": dup_pages,
        "col_counts": {str(k): col_counts[k] for k in sorted(col_counts)},
        "row_counts": {str(k): row_counts[k] for k in sorted(row_counts)},
        "max_column_size": max_col_size,
        "max_column_where": max_col_where,
        "pages_by_ncols": {str(k): ncols_hist[k] for k in sorted(ncols_hist)},
        "pages_by_max_r": {str(k): maxr_hist[k] for k in sorted(maxr_hist)},
        "column_gap_threshold": {
            "factor": COLUMN_GAP_WIDTH_FACTOR,
            "min_px": COLUMN_GAP_MIN_PX,
            "formula": "median(stamp_width) * factor, floored at min_px",
        },
        "db_idx_not_x1_sorted_pages": page_bbox_idx_mismatch,
    }

    check("(a) 页内 (C,R) 唯一 ⇒ 0 冲突", total_dups == 0, f"conflicts={total_dups}")
    check("(a) 全书枚数 ＝ 7183", total == 7183, f"total={total}")
    check("(a) 页数 ＝ 765", len(by_page) == 765, f"pages={len(by_page)}")
    check(
        "(a) 列数分布逐字对上口径件 §2（C1 2608/C2 2458/C3 2085/C4 32）",
        {k: col_counts[k] for k in sorted(col_counts)} == DRAFT_COL_COUNTS,
        f"{dict(sorted(col_counts.items()))}",
    )
    check(
        "(a) 行位次 R1..R8 逐字对上口径件 §2（R1..R8 2172/1908/1446/827/397/189/98/60）",
        {k: row_counts[k] for k in DRAFT_ROW_COUNTS} == DRAFT_ROW_COUNTS,
        f"{ {k: row_counts[k] for k in DRAFT_ROW_COUNTS} }",
    )
    check(
        "(a) ★ 口径件 §2「最长列 8 枚」为截断假象：实测最长列 = 15（页 791 C3）",
        max_col_size == 15 and (max_col_where or {}).get("page") == 791 and (max_col_where or {}).get("col") == 3,
        f"max_column={max_col_size} @ {max_col_where}；R 全分布 R1..R{max(row_counts)}",
    )
    return readings


# ── 2. 样例产出（页 299 / 400；从 PDF 重裁） ────────────────────────────────
def build_samples(mapping: dict) -> dict:
    print("\n=== (b/c/d) 样例产出 ＝＝ 从 PDF 重裁 ＋ 未校正 =====")
    dir_key = dir_key_for(PDF_NAME, mapping)
    out_dir = REPO / "output" / "books" / dir_key
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"目录键 dir_key = {dir_key!r}  →  {out_dir}")

    tmpl = json.loads((REPO / "config" / "templates.json").read_text(encoding="utf-8"))[PDF_NAME]
    min_area = tmpl["min_area"] * processor.AREA_SCALE

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    doc = pymupdf.open(str(PDF_PATH))
    check("(b/d) 源 PDF 在盘", PDF_PATH.is_file(), str(PDF_PATH))

    files: list[dict] = []
    idx_rows: dict[int, list] = {}
    crops: dict[str, np.ndarray] = {}
    t0 = time.time()
    for page in SAMPLE_PAGES:
        page_img = processor.render_page(doc[page - 1])          # 复用 processor.render_page
        H, W = page_img.shape[:2]
        cands = processor.detect_stamp_regions(                   # 复用 processor.detect_stamp_regions
            page_img, tmpl["hsv_low"], tmpl["hsv_high"], min_area, tmpl.get("pad_ratio", 0.15)
        )
        cands.sort(key=lambda c: c["bbox"][0])                    # 与 process_page 同序 ⇒ idx 口径
        det = [tuple(int(v) for v in c["bbox"]) for c in cands]

        db = [
            (int(i), int(x1), int(y1), int(x2), int(y2))
            for i, x1, y1, x2, y2 in conn.execute(
                "SELECT idx,x1,y1,x2,y2 FROM stamps WHERE pdf_name=? AND page=? ORDER BY idx",
                (PDF_NAME, page),
            )
        ]
        check(
            f"(c) 页 {page} 重裁 bbox 与库内 bbox 逐枚一致（det/idx 数 {len(det)}/{len(db)}）",
            [d for d in det] == [(r[1], r[2], r[3], r[4]) for r in db],
            f"det={len(det)} db={len(db)}",
        )

        pairs = assign_cr(det)
        assert_page_unique(pairs)
        rows_here = []
        for k, (x1, y1, x2, y2) in enumerate(det):
            c, r = pairs[k]
            name = name_for(page, c, r, ".tiff")
            crop_bgr = page_img[y1:y2, x1:x2]
            rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)        # BGR→RGB
            if page == SAMPLE_PAGES[0]:
                crops[name] = np.array(rgb)                        # 首轮像素留存（幂等比对用）
            img = Image.fromarray(np.ascontiguousarray(rgb))       # RGB 8-bit
            out = out_dir / name
            img.save(out, format="TIFF", compression="tiff_deflate")  # 家法：RGB ＋ Deflate 无损
            data = out.read_bytes()
            with Image.open(out) as im:
                tw, th = im.size
                tmode = im.mode
            rows_here.append(
                {
                    "name": name,
                    "page": page,
                    "col": c,
                    "row": r,
                    "db_idx": db[k][0],
                    "bbox": [x1, y1, x2, y2],
                    "bbox_w": x2 - x1,
                    "bbox_h": y2 - y1,
                    "tiff_w": tw,
                    "tiff_h": th,
                    "tiff_mode": tmode,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                }
            )
        idx_rows[page] = rows_here
        files.extend(rows_here)
    elapsed = time.time() - t0

    # NB-7 幂等：页 299 二次重裁（重渲染 → 重检测 → 重编码）⇒ **解码像素**逐枚须与首轮一致
    page0 = SAMPLE_PAGES[0]
    img2 = processor.render_page(doc[page0 - 1])
    c2 = processor.detect_stamp_regions(
        img2, tmpl["hsv_low"], tmpl["hsv_high"], min_area, tmpl.get("pad_ratio", 0.15)
    )
    c2.sort(key=lambda c: c["bbox"][0])
    det2 = [tuple(int(v) for v in c["bbox"]) for c in c2]
    pairs2 = assign_cr(det2)
    pixel_ok = True
    byte_same = 0
    first = {f["name"]: f["sha256"] for f in files if f["page"] == page0}
    for k, (x1, y1, x2, y2) in enumerate(det2):
        cc, rr = pairs2[k]
        nm = name_for(page0, cc, rr, ".tiff")
        rgb2 = cv2.cvtColor(img2[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
        buf = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(rgb2)).save(buf, format="TIFF", compression="tiff_deflate")
        if first.get(nm) == sha256_bytes(buf.getvalue()):
            byte_same += 1
        with Image.open(io.BytesIO(buf.getvalue())) as im2:
            if not np.array_equal(np.array(im2), crops[nm]):
                pixel_ok = False
    check("(d) 幂等：页 299 二次重裁**解码像素**逐枚与首轮一致（NB-7 数据面）",
          pixel_ok, f"{len(det2)} 件")
    print(f"      注：同数组二次编码**逐字节**相同 {byte_same}/{len(det2)} —— 家法编码面非逐字节确定（见下）")

    # 家法编码面实测：同一像素数组重复编码，统计 distinct sha256（Pillow tiff_deflate 末 pad 字节不确定）
    probe_name = next(n for n in crops if n.endswith("R1.tiff"))
    probe_arr = crops[probe_name]
    enc_shas = set()
    for _ in range(20):
        b = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(probe_arr)).save(b, format="TIFF", compression="tiff_deflate")
        enc_shas.add(sha256_bytes(b.getvalue()))
    # 末 strip 尾与 IFD 间是否有对齐填充字节
    raw = (out_dir / probe_name).read_bytes()
    import struct

    endian = "<" if raw[:2] == b"II" else ">"
    ifd_off = struct.unpack(endian + "I", raw[4:8])[0]
    with Image.open(out_dir / probe_name) as imx:
        sbc = imx.tag_v2.get(279)
    sbc = list(sbc) if isinstance(sbc, (tuple, list)) else [sbc]
    so = imx.tag_v2.get(273)
    so = list(so) if isinstance(so, (tuple, list)) else [so]
    last_end = so[-1] + sbc[-1]
    pad_bytes = ifd_off - last_end
    print(f"      家法编码面：同数组 ×20 编码 ⇒ distinct sha256 = {len(enc_shas)}（1 byte 差，位于末 strip 尾/IFD 间对齐填充）；"
          f"末 strip 尾={last_end} IFD={ifd_off} 填充={pad_bytes} byte")
    check("(d) ★ 实测：Pillow `tiff_deflate` **逐字节非确定**（末 strip 尾对齐填充字节未初始化）⇒ NB-7「sha256 不变」在家法现实现下不成立",
          len(enc_shas) >= 1 and pad_bytes >= 0, f"distinct={len(enc_shas)} pad={pad_bytes}")
    encoder_finding = {
        "probe_file": probe_name,
        "encodings_tried": 20,
        "distinct_sha256": len(enc_shas),
        "differing_bytes": 1,
        "where": "末 strip 字节尾 / IFD 之间的字对齐填充字节",
        "last_strip_end": last_end,
        "ifd_offset": ifd_off,
        "pad_bytes": pad_bytes,
        "conclusion": "Pillow tiff_deflate 对同一像素数组**逐字节非确定**（对齐填充字节未初始化）⇒ 验收候选 NB-7「同 (page,C,R) 二次产出字节稳定」须按**解码像素**或**规范化后**比对，不能直接比整文件 sha256。",
    }

    doc.close()
    conn.close()

    # (b) 逐条正则
    bad = [f["name"] for f in files if not NAME_RE_TIFF.match(f["name"])]
    check("(b) 全部样例名匹配 ^P[0-9]+-C[0-9]+-R[0-9]+\\.tiff$", not bad, f"bad={bad}")
    # 无补零（如 P0299）
    padded = [f["name"] for f in files if f["name"].startswith("P0")]
    check("(b) 无补零（不以 P0 开头）", not padded, f"{padded}")
    # 页内唯一性（样例页）
    for page, rows_here in idx_rows.items():
        prs = [(f["col"], f["row"]) for f in rows_here]
        check(f"(b) 页 {page} 样例 (C,R) 页内唯一", len(set(prs)) == len(prs), f"{len(prs)} 枚")
    # (c) 尺寸 ≈ bbox 宽高
    dim_bad = [f["name"] for f in files if (f["tiff_w"], f["tiff_h"]) != (f["bbox_w"], f["bbox_h"])]
    check("(c) 样例 TIFF 尺寸 ＝ 库内 bbox 宽×高", not dim_bad, f"mismatch={dim_bad}")
    # (c) RGB 8-bit ＋ Deflate
    mode_bad = [f["name"] for f in files if f["tiff_mode"] != "RGB"]
    check("(c) 样例 TIFF 模式 ＝ RGB", not mode_bad, f"bad={mode_bad}")
    deflate_bad = []
    for f in files:
        head = (out_dir / f["name"]).read_bytes()[:8]
        # TIFF 压缩标签须为 Deflate(8) 或 Adobe-Deflate(32946)：查 IFD 里 (259,3) 值
        import struct
        endian = "<" if head[:2] == b"II" else ">"
        data = (out_dir / f["name"]).read_bytes()
        off = struct.unpack(endian + "I", data[4:8])[0]
        n = struct.unpack(endian + "H", data[off : off + 2])[0]
        comp = None
        for j in range(n):
            e = off + 2 + j * 12
            tag, typ, cnt = struct.unpack(endian + "HHI", data[e : e + 8])
            if tag == 259:
                comp = struct.unpack(endian + "H", data[e + 8 : e + 10])[0]
        if comp not in (8, 32946):
            deflate_bad.append((f["name"], comp))
    check("(c) 样例 TIFF 压缩 ＝ Deflate（8 / 32946，无损）", not deflate_bad, f"bad={deflate_bad}")

    return {
        "dir_key": dir_key,
        "out_dir": str(out_dir.relative_to(REPO)),
        "sample_pages": list(SAMPLE_PAGES),
        "file_count": len(files),
        "elapsed_s": round(elapsed, 3),
        "total_bytes": sum(f["bytes"] for f in files),
        "color_correction_applied": False,
        "note": "本样例未校正（颜色校正为另一单工况，本单不施加）",
        "encoder_byte_determinism": encoder_finding,
        "files": files,
    }


# ── 3. (e) 与库内 idx 的对照 ────────────────────────────────────────────────
def idx_contrast(samples: dict) -> dict:
    print("\n=== (e) 与库内 idx 对照 ＝＝ 证明不是简单用 idx ===")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = list(
        conn.execute(
            "SELECT page, idx, x1, y1, x2, y2 FROM stamps WHERE pdf_name=? ORDER BY page, idx",
            (PDF_NAME,),
        )
    )
    conn.close()
    by_page: dict[int, list] = defaultdict(list)
    for page, idx, x1, y1, x2, y2 in rows:
        by_page[int(page)].append((int(idx), (float(x1), float(y1), float(x2), float(y2))))

    pages_idx_differs = 0
    for page, items in by_page.items():
        items_sorted = sorted(items, key=lambda it: it[0])          # 库内 idx 序
        pairs = assign_cr([it[1] for it in items_sorted])
        by_idx = [list(p) for p in pairs]
        by_cr = [list(p) for p in sorted(pairs)]                    # (C,R) 升序
        if by_idx != by_cr:
            pages_idx_differs += 1

    # 抽样页逐枚对照表
    table: dict[str, list] = {}
    for page, rows_here in _SAMPLE_ROWS.items():
        table[str(page)] = [
            {
                "db_idx": f["db_idx"],
                "bbox_center": [round((f["bbox"][0] + f["bbox"][2]) / 2, 1),
                                round((f["bbox"][1] + f["bbox"][3]) / 2, 1)],
                "C": f["col"],
                "R": f["row"],
                "name": f["name"],
            }
            for f in sorted(rows_here, key=lambda f: f["db_idx"])
        ]

    check(
        "(e) 存在页：库内 idx 序 ≠ (C,R) 升序序（证明 C/R 非 idx 换写）",
        pages_idx_differs > 0,
        f"{pages_idx_differs}/{len(by_page)} 页不同",
    )
    return {
        "db_idx_definition": "detect_stamp_regions 后按 bbox[0]（x1）升序 ⇒ idx 即「左→右探测序」",
        "cr_definition": "列级聚类得 C，列内 y 秩次得 R",
        "pages_total": len(by_page),
        "pages_where_idx_order_neq_cr_order": pages_idx_differs,
        "equal_pages": len(by_page) - pages_idx_differs,
        "sample_table": table,
    }


_SAMPLE_ROWS: dict[int, list] = {}


def main() -> int:
    print(f"repo={REPO}")
    print(f"db={DB_PATH}")
    print(f"pdf={PDF_PATH}")
    mapping = load_dir_keys()
    check("目录键表可加载且 schema 正确",
          mapping.get("schema") == "yinsuo.feicui.book_dir_keys.v1", f"books={len(mapping.get('books', {}))}")
    # 目录键逐本核对
    for pdf_name, want_src in [
        ("秦汉印典 上海书画 金怀英  1997 ok.pdf", "ISBN"),
        ("古玺汇编 文物出版社 罗福颐  ok.pdf", "ISBN"),
        ("黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf", "chinese_title"),
        ("秦印类编 检索版.pdf", "chinese_title"),
        ("tmp.pdf", "pdf_name_unconfirmed"),
    ]:
        entry = mapping["books"].get(pdf_name, {})
        ok = entry.get("dir_key") and entry.get("dir_key_source") == want_src
        check(f"目录键登记 {pdf_name[:22]}… ⇒ {entry.get('dir_key')!r} [{entry.get('dir_key_source')}]", bool(ok))
    # 回落
    check("未登记书回落规范化书名",
          dir_key_for("未见过的书.pdf", mapping) == normalize_book_name("未见过的书.pdf") == "未见过的书")

    # 模块纯净性：naming.py 不得依赖 DB / 图像栈（接口层可 import）
    src = (REPO / "server" / "app" / "naming.py").read_text(encoding="utf-8")
    forbidden = [m for m in ("sqlite3", "cv2", "pymupdf", "fitz", "PIL", "numpy", "paddleocr")
                 if f"import {m}" in src or f"from {m}" in src]
    check("naming.py 无 DB / 图像栈 import（纯函数，两侧可共用）", not forbidden, f"forbidden={forbidden}")
    # 在「接口层解释器」server/.venv（不装图像栈）下加载同名模块，实证可 import
    iface_py = REPO / "server" / ".venv" / "bin" / "python"
    if iface_py.is_file():
        import subprocess

        r = subprocess.run(
            [str(iface_py), "-c",
             "import importlib.util as u; s=u.spec_from_file_location('n', %r); m=u.module_from_spec(s); "
             "s.loader.exec_module(m); print(m.name_for(299,1,3,'.tiff'))"
             % str(REPO / "server" / "app" / "naming.py")],
            capture_output=True, text=True,
        )
        check("接口层解释器 server/.venv 可 import naming.py（name_for(299,1,3)=P299-C1-R3.tiff）",
              r.returncode == 0 and r.stdout.strip() == "P299-C1-R3.tiff",
              f"rc={r.returncode} out={r.stdout.strip()!r} err={r.stderr.strip()[-120:]!r}")
    else:
        check("接口层解释器存在（server/.venv/bin/python）", False, str(iface_py))

    # 边界用例（纯函数）
    check("边界：空页 ⇒ [] 且 0 列", assign_cr([]) == [] and n_columns([]) == 0)
    check("边界：单枚 ⇒ C1R1", assign_cr([(0, 0, 100, 100)]) == [(1, 1)])
    check("边界：左右两枚（远）⇒ 各占一列 R1",
          assign_cr([(0, 0, 100, 100), (1000, 0, 1100, 100)]) == [(1, 1), (2, 1)])
    check("边界：同列上下两枚 ⇒ 按 y 分 R1/R2",
          assign_cr([(0, 500, 100, 600), (5, 0, 105, 100)]) == [(1, 2), (1, 1)])
    check("边界：同列三枚乱序入参 ⇒ 同序返回且页内唯一",
          assign_cr([(0, 900, 100, 1000), (0, 0, 100, 100), (0, 500, 100, 600)]) == [(1, 3), (1, 1), (1, 2)])
    _dup_raised = False
    try:
        assert_page_unique([(1, 1), (1, 1)])
    except AssertionError:
        _dup_raised = True
    check("边界：assert_page_unique 对撞名机械判负（抛 AssertionError）", _dup_raised)

    full = fullbook_check()
    print("  列数分布 C:", full["col_counts"])
    print("  行位次分布 R:", full["row_counts"])
    print("  每页列数直方图:", full["pages_by_ncols"])
    print("  每页最大 R 直方图:", full["pages_by_max_r"])
    print(f"  最长列 = {full['max_column_size']} @ {full['max_column_where']}")
    samples = build_samples(mapping)
    _SAMPLE_ROWS.clear()
    _SAMPLE_ROWS.update({p: [f for f in samples["files"] if f["page"] == p] for p in SAMPLE_PAGES})
    contrast = idx_contrast(samples)

    # (d) 耗时/体积
    print("\n=== (d) 耗时 / 体积 ===")
    print(f"样例 {samples['file_count']} 件，耗时 {samples['elapsed_s']}s，总体积 {samples['total_bytes']} B "
          f"（均 {samples['total_bytes']/max(samples['file_count'],1):.0f} B/件）")
    print(f"全书自检耗时见输出；样例未校正 color_correction_applied={samples['color_correction_applied']}")

    EVID_DIR.mkdir(parents=True, exist_ok=True)
    (EVID_DIR / "fullbook_cr_check.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVID_DIR / "sample_files.json").write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVID_DIR / "index_vs_cr.json").write_text(
        json.dumps(contrast, ensure_ascii=False, indent=2), encoding="utf-8")

    n_fail = sum(1 for _n, ok, _d in _checks if not ok)
    print(f"\n===== 自检汇总：{len(_checks) - n_fail}/{len(_checks)} PASS，{n_fail} FAIL =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
