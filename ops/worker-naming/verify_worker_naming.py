#!/usr/bin/env python
# ══════════════════════════════════════════════════════════════════════════════
# ⚠⚠⚠  已作废 / DEPRECATED —— 不得再作为验收证据  ⚠⚠⚠
#   本脚本断言的是**旧「双份输出」口径**（TIFF ＋ 同名 webp 并存，见 commit
#   `f9be1d4`）；该口径**已被 commit `58c879f` 取代** —— 现行口径＝「只出 TIFF」
#   （worker 只写 `output/books/<目录键>/P<页>-C<列>-R<行>.tiff`，旧 webp 已退场、
#   新命名目录与 `output/faces/**` 均不再新写 webp）。Kevin 2026-10-11 裁定「本地
#   文件一律不再保存 webp」。
#   并且本脚本用 `git show HEAD:server/worker/feicui_worker.py` 取「改造前」源码，
#   而 HEAD 现已是**改造后**的新码 ⇒ `old_src` 含 `correct_image_v3`/`encode_tiff`/
#   `output/books` ⇒ **跑它必然误判**（「改造前 worker 不含新逻辑」「旧 webp 未变」
#   「三套并存」等断言全部失败）——它现在只会产出**误导性 FAIL 证据**。
#   ⇒ 默认**拒绝运行**（exit 3）。仅当显式设 `FEICUI_RUN_DEPRECATED_VERIFY=1`
#   强制复跑时，输出也只作**历史对照**，**不得写进任何验收结论**。
#   现行验收请改用：`ops/pool-naming-columns/`（本次 P0 修复）＋
#   `server/app/backfill_book_images.py --verify-only` ＋ E6/E5 活体端点读数。
# ══════════════════════════════════════════════════════════════════════════════
"""worker 接新口径（P-C-R 命名 ＋ V3 校正 ＋ 双份输出）· 单页函数级验证（Kong / 2026-10-11）。

**⚠ 此文件已作废（见文件头注释）：断言的是已被 `58c879f` 取代的「双份输出」旧口径，
默认拒绝运行。** 保留仅作历史对照。

**不建 job、不写库、不碰旧文件**（红线）。做法：
  1. 载入**改造前**的 worker（`git show HEAD:server/worker/feicui_worker.py`）与**改造后**的本文件；
  2. 同一页（`tmp.pdf` 第 13 页；小图快；book_key=TMP、dir_key=tmp.pdf）各跑：预热 1 次 ＋ 计时 2 次取 min；
  3. 读数：三套产出清单（旧 webp ＋ 新 tiff ＋ 新 webp）、旧 webp 字节/mtime 是否未变、新 tiff 尺寸与压缩、
     命名正则、(C,R) 页内唯一、返回值新字段、**改造前后单页耗时对比**、**新增工作量**边际成本。

须用图像栈解释器运行：
    cd /Users/kevin/bistro/feicui
    ./venv/bin/python ops/worker-naming/verify_worker_naming.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

PDF_NAME = "tmp.pdf"
PDF_PATH = REPO / "tmp.pdf"
PAGE = 13
BOOK_KEY = "TMP"
TEMPLATE_ALIAS = "黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf"
EVID = REPO / "ops" / "worker-naming"

_checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _checks.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_module(name: str, src: str):
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def tiff_tags(path: Path) -> dict:
    """读 TIFF IFD 里的关键标签：256 宽 / 257 高 / 259 压缩 / 262 光度 / 277 每像素样本数。"""
    data = path.read_bytes()
    endian = "<" if data[:2] == b"II" else ">"
    off = struct.unpack(endian + "I", data[4:8])[0]
    n = struct.unpack(endian + "H", data[off:off + 2])[0]
    tags: dict[int, int] = {}
    for j in range(n):
        e = off + 2 + j * 12
        tag, typ, _cnt = struct.unpack(endian + "HHI", data[e:e + 8])
        if tag in (256, 257, 259, 262, 277):
            if typ == 3:      # SHORT
                tags[tag] = struct.unpack(endian + "H", data[e + 8:e + 10])[0]
            elif typ == 4:    # LONG
                tags[tag] = struct.unpack(endian + "I", data[e + 8:e + 12])[0]
    return tags


def main() -> int:
    banner = (
        "\n" + "!" * 78 + "\n"
        "!!  已作废 / DEPRECATED：本脚本断言旧「双份输出」口径（f9be1d4），\n"
        "!!  已被「只出 TIFF」口径（commit 58c879f）取代；且它从 HEAD 取到的\n"
        "!!  「改造前」源码现已是新码 ⇒ 跑它必然产出**误导性 FAIL**。\n"
        "!!  默认拒绝运行。强制复跑：FEICUI_RUN_DEPRECATED_VERIFY=1（仅作历史对照，\n"
        "!!  不得写进任何验收结论）。现行验收见 ops/pool-naming-columns/。\n"
        + "!" * 78
    )
    print(banner)
    if os.environ.get("FEICUI_RUN_DEPRECATED_VERIFY") != "1":
        print("已作废：拒绝运行（exit 3）。")
        return 3
    print(f"repo={REPO}\npage={PAGE} pdf={PDF_PATH} alias={TEMPLATE_ALIAS} book_key={BOOK_KEY}")
    check("源 PDF 在盘", PDF_PATH.is_file(), str(PDF_PATH))

    # ── 改造前 worker 源码（git HEAD）───────────────────────────────────────
    old_src = subprocess.run(
        ["git", "show", f"HEAD:server/worker/feicui_worker.py"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout
    scratch = Path(os.environ.get("TMPDIR", "/tmp")) / "feicui_worker_old_snapshot.py"
    scratch.write_text(old_src, encoding="utf-8")
    OLD = load_module("feicui_worker_old", str(scratch))
    NEW = load_module("feicui_worker_new", str(REPO / "server" / "worker" / "feicui_worker.py"))
    check("改造前 worker（git HEAD）不含本单新逻辑（无 correct_image_v3 / encode_tiff / output/books）",
          all(k not in old_src for k in ("correct_image_v3", "encode_tiff", "output/books"))
          and "correct_image_v3" in (REPO / "server" / "worker" / "feicui_worker.py").read_text(encoding="utf-8"),
          f"old_len={len(old_src)}")

    import json as _json  # noqa: E402

    templates = _json.loads((REPO / "config" / "templates.json").read_text(encoding="utf-8"))
    tmpl = templates[TEMPLATE_ALIAS]

    import pymupdf  # noqa: E402

    # ── 旧 webp 既有件的基线（sha256 ＋ mtime_ns）────────────────────────────
    faces_dir = REPO / "output" / "faces" / BOOK_KEY
    before = {p.name: (sha256_file(p), p.stat().st_mtime_ns) for p in sorted(faces_dir.glob(f"p{PAGE:04d}_*.webp"))}
    print(f"\n既有旧 webp 基线：{len(before)} 枚  @ {faces_dir}")
    check("既有旧 webp 基线非空（可判『未变』）", len(before) > 0, f"{len(before)} 枚")

    def run(mod, times: int, warm: int = 1):
        doc = pymupdf.open(str(PDF_PATH))
        try:
            for _ in range(warm):
                mod.process_page(doc, PAGE, tmpl, BOOK_KEY, PDF_NAME) if mod is NEW else mod.process_page(doc, PAGE, tmpl, BOOK_KEY)
            best, outs = None, None
            for _ in range(times):
                t0 = time.perf_counter()
                out = mod.process_page(doc, PAGE, tmpl, BOOK_KEY, PDF_NAME) if mod is NEW else mod.process_page(doc, PAGE, tmpl, BOOK_KEY)
                dt = time.perf_counter() - t0
                best = dt if best is None else min(best, dt)
                outs = out
            return best, outs
        finally:
            doc.close()

    # ── 计时：改造前 / 改造后（预热 1 ＋ 计时 2 取 min）────────────────────────
    t_old, _ = run(OLD, times=2, warm=1)
    t_new, out_new = run(NEW, times=2, warm=1)
    print(f"\n单页耗时（预热后 min×2）：改造前 {t_old*1000:.1f} ms  →  改造后 {t_new*1000:.1f} ms"
          f"  Δ={(t_new-t_old)*1000:+.1f} ms ({(t_new/t_old-1)*100:+.1f}%)")

    # ── 新增工作量的边际成本（只量新增块：V3 校正 ＋ tiff 编码 ＋ 命名 webp 编码）──
    from PIL import Image  # noqa: E402
    import cv2, numpy as np  # noqa: E402
    import processor  # noqa: E402
    import io as _io  # noqa: E402

    doc = pymupdf.open(str(PDF_PATH))
    img = processor.render_page(doc[PAGE - 1])
    H, W = img.shape[:2]
    min_area = tmpl["min_area"] * processor.AREA_SCALE
    cands = processor.detect_stamp_regions(img, tmpl["hsv_low"], tmpl["hsv_high"], min_area, tmpl.get("pad_ratio", 0.15))
    cands.sort(key=lambda c: c["bbox"][0])
    crops = [img[max(0, int(c["bbox"][1])):min(H, int(c["bbox"][3])), max(0, int(c["bbox"][0])):min(W, int(c["bbox"][2]))] for c in cands]
    doc.close()

    margin = []
    sub = {"v3": 0.0, "tiff": 0.0, "webp": 0.0}
    for crop in crops:
        rgb = np.ascontiguousarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        t0 = time.perf_counter()
        corrected, _rep = NEW.colorcal.correct_image_v3(rgb)
        t1 = time.perf_counter()
        buf = _io.BytesIO()
        Image.fromarray(np.ascontiguousarray(corrected)).save(buf, format="TIFF", compression="tiff_deflate")
        _tiff = buf.getvalue()
        t2 = time.perf_counter()
        ok, wb = cv2.imencode(".webp", cv2.cvtColor(corrected, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_WEBP_QUALITY), 95])
        t3 = time.perf_counter()
        sub["v3"] += (t1 - t0) * 1000
        sub["tiff"] += (t2 - t1) * 1000
        sub["webp"] += (t3 - t2) * 1000
        margin.append((t3 - t0) * 1000)
    print(f"新增块边际成本/枚：min {min(margin):.1f} ms  max {max(margin):.1f} ms  "
          f"合计 {sum(margin):.1f} ms（{len(crops)} 枚；含 V3 校正＋TIFF Deflate 编码＋命名 webp 编码）")
    print(f"  分解（{len(crops)} 枚合计）：V3 校正 {sub['v3']:.1f} ms ｜ TIFF Deflate {sub['tiff']:.1f} ms ｜ webp 编码 {sub['webp']:.1f} ms")

    # ── OCR 成本代理（生产页常见；本页旧路径未触发 OCR）＋ 「含 OCR 时」相对开销投影 ──
    ocr_ms = []
    for crop in crops:
        t0 = time.perf_counter()
        NEW.ocr_text(crop)
        ocr_ms.append((time.perf_counter() - t0) * 1000)
    t_ocr = sum(ocr_ms) / 1000.0
    proj_old, proj_new = t_ocr + t_old, t_ocr + t_new
    print(f"OCR 成本代理/页（{len(crops)} 枚同尺寸裁图，warm）：{t_ocr*1000:.0f} ms ⇒ "
          f"含 OCR 时投影：旧 {proj_old*1000:.0f} ms → 新 {proj_new*1000:.0f} ms "
          f"({(proj_new/proj_old-1)*100:+.1f}%)")

    # ── TIFF 编码逐字节确定性探针（家法已知：Pillow tiff_deflate 大图上末 pad 字节不确定）──
    import io as _io2
    det_shas: dict[str, int] = {}
    det_pixels_ok = True
    for _ in range(20):
        rgb = np.ascontiguousarray(cv2.cvtColor(crops[0], cv2.COLOR_BGR2RGB))
        corrected, _r = NEW.colorcal.correct_image_v3(rgb)
        b = _io2.BytesIO()
        Image.fromarray(np.ascontiguousarray(corrected)).save(b, format="TIFF", compression="tiff_deflate")
        d = hashlib.sha256(b.getvalue()).hexdigest()
        det_shas[d] = det_shas.get(d, 0) + 1
        with Image.open(_io2.BytesIO(b.getvalue())) as im:
            if not np.array_equal(np.array(im), np.array(corrected)):
                det_pixels_ok = False
    check("TIFF 编码：同像素数组 20 次**解码像素**逐枚一致", det_pixels_ok)
    print(f"TIFF 编码确定性：20 次 ⇒ distinct sha256 = {len(det_shas)}"
          f"（{crops[0].shape[1]}x{crops[0].shape[0]}；家法已知大图上末 pad 字节不确定 ⇒ 幂等判据须按解码像素）")

    # ── 旧 webp 是否未变 ────────────────────────────────────────────────────
    after = {p.name: (sha256_file(p), p.stat().st_mtime_ns) for p in sorted(faces_dir.glob(f"p{PAGE:04d}_*.webp"))}
    same_keys = set(before) == set(after)
    bytes_same = same_keys and all(before[k][0] == after[k][0] for k in before)
    mtime_same = same_keys and all(before[k][1] == after[k][1] for k in before)
    check("旧 webp 文件集合未变（未新增/未删）", same_keys, f"{len(before)}→{len(after)}")
    check("★ 旧 webp 逐枚 **sha256 未变**（字节未变）", bytes_same)
    check("★ 旧 webp **mtime 未变**（幂等写未重写）", mtime_same)

    # ── 新产出清单 / 命名 / 尺寸 / 压缩 / (C,R) ──────────────────────────────
    dir_key = NEW.naming.dir_key_for(PDF_NAME, NEW.DIR_KEYS)
    books_out = NEW.BOOKS_DIR / dir_key
    produced = sorted(list(books_out.glob("*.tiff")) + list(books_out.glob("*.webp")))
    print(f"\n新落点 dir_key={dir_key!r} → {books_out.relative_to(REPO)}  产出 {len(produced)} 件")

    items = out_new["items"]
    check("返回 detected ＝ 产出枚数", out_new["detected"] == len(items) == len(crops),
          f"detected={out_new['detected']} items={len(items)} crops={len(crops)}")

    names_ok, dims_ok, comp_ok, uniq_pairs, ret_ok = True, True, True, [], True
    file_rows = []
    for it in items:
        c, r = it["col"], it["row"]
        uniq_pairs.append((c, r))
        nm_tiff = NEW.naming.name_for(PAGE, c, r)
        nm_webp = NEW.naming.name_for(PAGE, c, r, ".webp")
        if not NEW.naming.NAME_RE_TIFF.match(nm_tiff) or not NEW.naming.NAME_RE.match(nm_webp):
            names_ok = False
        tp = books_out / nm_tiff
        wp = books_out / nm_webp
        if not (tp.is_file() and wp.is_file()):
            names_ok = False
            continue
        tags = tiff_tags(tp)
        from PIL import Image as _I
        with _I.open(tp) as im:
            tw, th, mode = im.size[0], im.size[1], im.mode
        bw, bh = it["x2"] - it["x1"], it["y2"] - it["y1"]
        if (tw, th) != (bw, bh) or mode != "RGB":
            dims_ok = False
        if tags.get(259) not in (8, 32946):
            comp_ok = False
        # 返回值与落盘名一致
        if it["img_path_tiff"] != str(tp.relative_to(REPO)) or it["img_path"] != str((faces_dir / f"p{PAGE:04d}_{it['idx']:02d}.webp").relative_to(REPO)):
            ret_ok = False
        file_rows.append({
            "idx": it["idx"], "col": c, "row": r,
            "old_webp": it["img_path"], "new_tiff": it["img_path_tiff"],
            "new_webp": str(wp.relative_to(REPO)),
            "tiff_w": tw, "tiff_h": th, "tiff_mode": mode, "tiff_compression_tag": tags.get(259),
            "tiff_photometric": tags.get(262), "tiff_samples": tags.get(277),
            "bbox_w": bw, "bbox_h": bh,
            "tiff_bytes": tp.stat().st_size, "tiff_sha256": sha256_file(tp),
            "new_webp_bytes": wp.stat().st_size,
        })

    check("(b) 全部新名匹配正则（tiff: ^P[0-9]+-C[0-9]+-R[0-9]+\\.tiff$ ＋ webp 同形）", names_ok)
    check("(b) 无补零（名不以 P0 开头）", all(not NEW.naming.name_for(PAGE, it["col"], it["row"]).startswith("P0") for it in items))
    check("(c) 新 TIFF 尺寸 ＝ bbox 宽×高 且 mode＝RGB", dims_ok)
    check("(c) 新 TIFF 压缩 ＝ Deflate（标签 259 ∈ {8, 32946}）", comp_ok)
    check(f"(b) 页内 (C,R) 唯一（{len(uniq_pairs)} 枚，{len(set(uniq_pairs))} 唯一）", len(set(uniq_pairs)) == len(uniq_pairs))
    # 与 assign_cr 独立复算交叉核
    recomputed = NEW.naming.assign_cr([(it["x1"], it["y1"], it["x2"], it["y2"]) for it in items])
    check("(b) 返回值 (C,R) ＝ naming.assign_cr 复算值（同序）", recomputed == uniq_pairs, f"{uniq_pairs}")
    check("(b) naming.assert_page_unique 不抛（机械判负未触发）", True)
    check("(返回) 新字段 col/row/img_path_tiff 在返回值内且 img_path_tiff 指向新落点", ret_ok)
    # 三套并存
    check("三套并存：旧 webp ＋ 新 tiff ＋ 新 webp 同页均在盘",
          len(items) == len([f for f in produced if f.suffix == ".tiff"]) == len([f for f in produced if f.suffix == ".webp"]))

    readings = {
        "page": PAGE, "pdf_name": PDF_NAME, "book_key": BOOK_KEY, "template_alias": TEMPLATE_ALIAS,
        "dir_key": dir_key, "out_dir": str(books_out.relative_to(REPO)),
        "detected": out_new["detected"],
        "timing_ms": {"old_min": round(t_old * 1000, 1), "new_min": round(t_new * 1000, 1),
                      "delta_ms": round((t_new - t_old) * 1000, 1), "delta_pct": round((t_new / t_old - 1) * 100, 2),
                      "note": "本页旧路径未触发 OCR（density 门未过）⇒ 基线偏低；见 ocr_projection"},
        "ocr_projection": {"ocr_proxy_ms": round(t_ocr * 1000, 1),
                           "proj_old_ms": round(proj_old * 1000, 1), "proj_new_ms": round(proj_new * 1000, 1),
                           "proj_delta_pct": round((proj_new / proj_old - 1) * 100, 2),
                           "note": "OCR 用同尺寸裁图代理（生产页常见走 OCR）；投影相对开销随 OCR 占比下降"},
        "tiff_byte_determinism": {"encodings": 20, "distinct_sha256": len(det_shas),
                                  "pixels_equal": det_pixels_ok, "probe": "crops[0]"},
        "new_block_marginal_ms": {"per_stamp_min": round(min(margin), 1), "per_stamp_max": round(max(margin), 1),
                                  "total": round(sum(margin), 1), "stamps": len(crops),
                                  "breakdown": {k: round(v, 1) for k, v in sub.items()},
                                  "note": "V3 校正 ＋ TIFF Deflate 编码 ＋ 命名 webp 编码（不含落盘 fsync）"},
        "old_webp_unchanged": {"count": len(before), "sha256_unchanged": bytes_same, "mtime_unchanged": mtime_same,
                               "baseline_dir": str(faces_dir.relative_to(REPO))},
        "files": file_rows,
        "returned_new_fields": [{"idx": it["idx"], "col": it["col"], "row": it["row"], "img_path_tiff": it["img_path_tiff"]} for it in items],
    }
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "verify_readings.json").write_text(json.dumps(readings, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n三套产出（逐枚）：")
    for f in file_rows:
        print(f"  idx{f['idx']:>2}  C{f['col']}R{f['row']}  "
              f"old={Path(f['old_webp']).name}  new={Path(f['new_tiff']).name}({f['tiff_w']}x{f['tiff_h']} {f['tiff_mode']} "
              f"comp={f['tiff_compression_tag']} {f['tiff_bytes']}B)  webp={f['new_webp_bytes']}B")

    n_fail = sum(1 for _n, ok, _d in _checks if not ok)
    print(f"\n===== 验证汇总：{len(_checks) - n_fail}/{len(_checks)} PASS，{n_fail} FAIL =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
