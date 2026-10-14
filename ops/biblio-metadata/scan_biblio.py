#!/usr/bin/env python
"""版权页 OCR 抓取 ＋ 交叉自证 ＋ 目录键推荐 ＋ 落库 —— Kong / biblio-metadata 单 · 2026-10-11。

口径真源：`docs/biblio-metadata-draft-v0.1.md`（§5-2 抓取 / §5-3 交叉自证 / §5-4 目录键推荐 / §4 落点）。
**纯函数在 `server/app/biblio.py`**（本脚本只做「渲染 ＋ OCR ＋ 抽取 ＋ 落库」的编排）。

纪律：
* **图像栈只在 `feicui/venv`** ⇒ 本脚本须用 `./venv/bin/python` 跑；
* 复用既有 `processor.render_page`（**只读 monkeypatch 其模块常量 `RENDER_DPI=200`**，
  **不改 `processor.py` 一行**）＋ 既有 OCR（`processor._get_ocr()` / `processor.ocr_text`）；
* 扫描面 ＝ **前 6 页 ∪ 末 4 页**；锚词 ＝ `ISBN` / `圖書在版編目` / `在版编目` / `CIP` / `核字`；
* **只写 `var/biblio_ingest.db`**（**不写 `yinpu.db`、不改其列值**）；**不删文件、不建 job、零联网**；
* 抓不到 ⇒ 如实标 `unverified`，**不得伪造**。

复跑：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/biblio-metadata/scan_biblio.py            # 全量（已登记书）
    ./venv/bin/python ops/biblio-metadata/scan_biblio.py --only 秦印类编
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]           # <feicui>
sys.path.insert(0, str(REPO))                        # 供 `import processor`（仅图像栈侧需要）

from server.app.pdf_registry import pdf_source_dir  # noqa: E402  # PDF 取阅真源目录（stdlib-only 模块）


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# `server/app/biblio.py` 按**文件路径**加载（避免仓根 `app.py` 遮蔽 `server/app/` 包）。
biblio = _load_module("biblio", REPO / "server" / "app" / "biblio.py")

OUT_DIR = REPO / "ops" / "biblio-metadata"
DB_PATH = REPO / "var" / "biblio_ingest.db"
DIR_KEYS = REPO / "config" / "book_dir_keys.json"

BATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS biblio_import_batches (
    batch_id TEXT PRIMARY KEY,
    created_at TEXT, updated_at TEXT, status TEXT,
    source_total INTEGER, fetched INTEGER, books_ok INTEGER, candidates_ok INTEGER,
    failed_count INTEGER, elapsed_s REAL, package_dir TEXT, report_path TEXT,
    content_fingerprint TEXT, params_json TEXT, notes TEXT,
    last_run_kind TEXT, last_run_fetched INTEGER, last_run_skipped INTEGER,
    last_run_elapsed_s REAL, last_run_at TEXT
)"""
BOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS book_biblio (
    book_ref TEXT PRIMARY KEY,
    isbn13 TEXT, isbn10 TEXT, cip_code TEXT,
    title TEXT, publisher TEXT, pub_year TEXT, edition TEXT,
    source TEXT, verify_state TEXT, evidence TEXT, created_at TEXT,
    dir_key_recommended TEXT, dir_key_source_recommended TEXT,
    dir_key_current TEXT, dir_key_source_current TEXT,
    isbn_source TEXT, verify_note TEXT, candidates_json TEXT,
    pdf_sha256 TEXT, pages_scanned INTEGER, scan_dpi REAL, batch_id TEXT, updated_at TEXT
)"""


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_schema(db_path: Path, notes: str = "") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.execute(BATCH_SCHEMA)
        conn.execute(BOOK_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 渲染（200 dpi，复用 processor.render_page；只改其模块常量，不改文件）
# ---------------------------------------------------------------------------

def _render_page_200dpi(processor, page):
    """复用 `processor.render_page`，把其模块常量 `RENDER_DPI` 临时置 200（口径件 §5-2）。"""
    saved = processor.RENDER_DPI
    processor.RENDER_DPI = biblio.SCAN_DPI
    try:
        return processor.render_page(page)
    finally:
        processor.RENDER_DPI = saved


# ---------------------------------------------------------------------------
# 单页抓取：文本层优先 → 命中 ISBN/CIP 即用；否则回落 200 dpi OCR（口径件 C-5 默认兜底序）
# ---------------------------------------------------------------------------

def scan_page(processor, doc, page_idx: int, do_ocr: bool = True) -> dict:
    page = doc[page_idx]
    sources: list[dict] = []
    text_layer = ""
    try:
        text_layer = page.get_text() or ""
    except Exception:
        text_layer = ""
    if text_layer.strip():
        sources.append({"source": "text_layer", "text": text_layer})

    tl_has_isbn = bool(biblio.find_isbn_candidates(text_layer))
    tl_has_cip = bool(biblio.find_cip_codes(text_layer))
    ocr_used = False
    ocr_seconds = None
    ocr_text = ""
    if do_ocr and not (tl_has_isbn and tl_has_cip):
        img = _render_page_200dpi(processor, page)
        t0 = time.time()
        ocr_text = processor.ocr_text(img) or ""
        ocr_seconds = round(time.time() - t0, 2)
        ocr_used = True
        if ocr_text.strip():
            sources.append({"source": "local_ocr", "text": ocr_text,
                            "dpi": biblio.SCAN_DPI, "seconds": ocr_seconds})

    isbns: list[dict] = []
    cips: list[dict] = []
    pubs: list[str] = []
    years: list[int] = []
    for s in sources:
        for c in biblio.find_isbn_candidates(s["text"], keep_rejected=True):
            c = dict(c, source=s["source"])
            if not any(x["normalized"] == c["normalized"] and x["kind"] == c["kind"] for x in isbns):
                isbns.append(c)
        for c in biblio.find_cip_codes(s["text"]):
            c = dict(c, source=s["source"])
            if not any(x["code"] == c["code"] for x in cips):
                cips.append(c)
        for p in biblio.find_publishers(s["text"]):
            if p not in pubs:
                pubs.append(p)
        for y in biblio.find_pub_years(s["text"]):
            if y not in years:
                years.append(y)

    anchors = [w for w in biblio.ANCHOR_WORDS
               if biblio.contains_anchor("".join(s["text"] for s in sources), (w,))]
    return {
        "page": page_idx + 1,
        "text_layer_chars": len(text_layer.strip()),
        "ocr_used": ocr_used,
        "ocr_seconds": ocr_seconds,
        "sources": [s["source"] for s in sources],
        "anchors": anchors,
        "isbn_candidates": isbns,
        "cip_candidates": cips,
        "publishers": pubs,
        "pub_years": years,
        # 证据片段（留痕；截断以控体量）
        "evidence": [{"source": s["source"], "chars": len(s["text"]),
                      "excerpt": s["text"][:1200]} for s in sources],
    }


# ---------------------------------------------------------------------------
# 单书汇总
# ---------------------------------------------------------------------------

def summarize_book(pdf_name: str, pages: list[dict], current: dict, unconfirmed: bool) -> dict:
    # 汇总所有候选
    all_isbn: list[dict] = []
    for pg in pages:
        for c in pg["isbn_candidates"]:
            all_isbn.append(dict(c, page=pg["page"]))
    all_cip: list[dict] = []
    for pg in pages:
        for c in pg["cip_candidates"]:
            all_cip.append(dict(c, page=pg["page"]))
    all_pubs: list[str] = []
    for pg in pages:
        for p in pg["publishers"]:
            if p not in all_pubs:
                all_pubs.append(p)
    all_years: list[int] = []
    for pg in pages:
        for y in pg["pub_years"]:
            if y not in all_years:
                all_years.append(y)

    valid = [c for c in all_isbn if c["valid"]]
    # 排序偏好：① 带 `ISBN` 标签者优先（防无标签噪声胜出）② ISBN-13 优先 ③ 出现序（页 / 位置）
    valid.sort(key=lambda c: (not c.get("labeled", False), c["kind"] != "isbn13",
                              c.get("page", 0), c.get("start", 0)))
    c13 = next((c for c in valid if c["kind"] == "isbn13"), None)
    c10 = next((c for c in valid if c["kind"] == "isbn10"), None)
    # 「现场直读」形态（目录键口径，Kong 2026-10-11 收口·缺陷②）：
    #   ① 读到了 ISBN-13 ⇒ 目录键落 13 位（如 秦印类编 9787550847224）；
    #   ② 只读到 ISBN-10（13 位为派生）⇒ 目录键落 10 位（如 秦汉印典 7806350950 / 古玺汇编 7501007985）。
    isbn13_obs = c13["normalized"] if c13 else None
    isbn10_obs = c10["normalized"] if c10 else None
    # 落库列（含派生形态，供检索）：直读优先，缺失的一侧由另一侧派生。
    isbn13, isbn10 = isbn13_obs, isbn10_obs
    isbn10_derived = False
    isbn13_derived = False
    if isbn10 is None and isbn13 is not None:
        isbn10 = biblio.isbn13_to_isbn10(isbn13)          # 派生（标注 derived）
        isbn10_derived = True
    if isbn13 is None and isbn10 is not None:
        isbn13 = biblio.isbn10_to_isbn13(isbn10)
        isbn13_derived = True
    # ISBN 来源（文本层 / OCR）：取胜出候选的来源；13 优先
    win = c13 or c10
    isbn_source = win["source"] if win else None

    # 出版社：优先取与有效 ISBN 同页者
    isbn_pages = {c["page"] for c in valid}
    pub = None
    for pg in pages:
        if pg["page"] in isbn_pages and pg["publishers"]:
            pub = pg["publishers"][0]
            break
    if pub is None and all_pubs:
        pub = all_pubs[0]

    cip = all_cip[0]["code"] if all_cip else None

    if isbn13 or isbn10:
        xv = biblio.cross_verify(isbn13 or isbn10, pub)
    else:
        xv = {"verify_state": "unverified", "note": "版权页扫描面内未识别到可用 ISBN（校验位）",
              "prefix": None, "table_publisher": None, "ocr_publisher": pub, "match": None}

    source = isbn_source or ("local_ocr" if any(pg["ocr_used"] for pg in pages) else "text_layer")
    if not (isbn13 or isbn10):
        source = "local_ocr" if any(pg["ocr_used"] for pg in pages) else "text_layer"

    rec = biblio.recommend_dir_key(pdf_name, isbn10=isbn10_obs, isbn13=isbn13_obs,
                                   unconfirmed=unconfirmed, isbn_source=source)

    def _brief(c: dict) -> dict:
        return {"raw": c.get("raw"), "normalized": c.get("normalized"), "kind": c.get("kind"),
                "valid": c.get("valid"), "page": c.get("page"), "source": c.get("source"),
                "labeled": c.get("labeled"), "anchor_near": c.get("anchor_near"),
                "shape_reason": c.get("shape_reason"), "rejected_reason": c.get("rejected_reason")}

    evidence = {
        "scan_face_pages": [pg["page"] for pg in pages],
        "ocr_pages": [pg["page"] for pg in pages if pg["ocr_used"]],
        "isbn_candidates": all_isbn,
        "isbn_accepted": [_brief(c) for c in all_isbn if biblio.is_accepted_candidate(c)],
        "isbn_rejected": [_brief(c) for c in all_isbn if not biblio.is_accepted_candidate(c)],
        "cip_candidates": all_cip,
        "publishers": all_pubs,
        "pub_years": all_years,
        "cross_verify": {k: xv.get(k) for k in ("verify_state", "prefix", "table_publisher",
                                                "ocr_publisher", "match", "note")},
        "page_evidence": [{"page": pg["page"], "evidence": pg["evidence"]} for pg in pages
                          if pg["evidence"]],
    }
    return {
        "book_ref": pdf_name,
        "isbn13": isbn13, "isbn10": isbn10,
        "isbn13_derived": isbn13_derived, "isbn10_derived": isbn10_derived,
        "cip_code": cip,
        "title": None, "publisher": pub,
        "pub_year": str(all_years[0]) if all_years else None,
        "edition": None,
        "source": source,
        "verify_state": xv["verify_state"],
        "verify_note": xv.get("note"),
        "evidence": evidence,
        "dir_key_recommended": rec["dir_key"],
        "dir_key_source_recommended": rec["dir_key_source"],
        "dir_key_current": current.get("dir_key"),
        "dir_key_source_current": current.get("dir_key_source"),
        "isbn_source": source if (isbn13 or isbn10) else None,
        "recorded_isbn": current.get("isbn"),
    }


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------

def upsert_book(db_path: Path, rec: dict, batch_id: str) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(book_biblio)")}
        # 防御式读取：evidence 子键缺失不崩（契约由各分支负责填齐；此处兜底）
        ev = rec.get("evidence") or {}
        vals = {
            "book_ref": rec["book_ref"], "isbn13": rec.get("isbn13"), "isbn10": rec.get("isbn10"),
            "cip_code": rec.get("cip_code"), "title": rec.get("title"), "publisher": rec.get("publisher"),
            "pub_year": rec.get("pub_year"), "edition": rec.get("edition"), "source": rec.get("source"),
            "verify_state": rec.get("verify_state"),
            "evidence": json.dumps(ev, ensure_ascii=False),
            "created_at": _now(),
            "dir_key_recommended": rec.get("dir_key_recommended"),
            "dir_key_source_recommended": rec.get("dir_key_source_recommended"),
            "dir_key_current": rec.get("dir_key_current"),
            "dir_key_source_current": rec.get("dir_key_source_current"),
            "isbn_source": rec.get("isbn_source"), "verify_note": rec.get("verify_note"),
            "candidates_json": json.dumps({"isbn_candidates": ev.get("isbn_candidates", []),
                                           "cip_candidates": ev.get("cip_candidates", [])},
                                          ensure_ascii=False),
            "pdf_sha256": rec.get("pdf_sha256"), "pages_scanned": rec.get("pages_scanned"),
            "scan_dpi": rec.get("scan_dpi"), "batch_id": batch_id, "updated_at": _now(),
        }
        use = {k: v for k, v in vals.items() if k in cols}
        placeholders = ",".join("?" for _ in use)
        colnames = ",".join(use)
        conn.execute(f"INSERT OR REPLACE INTO book_biblio ({colnames}) VALUES ({placeholders})",
                     list(use.values()))
        conn.commit()
    finally:
        conn.close()


def write_batch(db_path: Path, batch_id: str, summary: dict, notes: str) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO biblio_import_batches "
            "(batch_id,created_at,updated_at,status,source_total,fetched,books_ok,candidates_ok,"
            "failed_count,elapsed_s,package_dir,report_path,content_fingerprint,params_json,notes,"
            "last_run_kind,last_run_fetched,last_run_skipped,last_run_elapsed_s,last_run_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, _now(), _now(), summary.get("status"), summary.get("books_total"),
             summary.get("books_scanned"), summary.get("books_ok"), summary.get("candidates_ok"),
             summary.get("books_failed"), summary.get("elapsed_s"), str(OUT_DIR),
             str(OUT_DIR / "summary.json"), summary.get("content_fingerprint"),
             json.dumps(summary.get("params"), ensure_ascii=False), notes,
             "scan", summary.get("books_scanned"), 0, summary.get("elapsed_s"), _now()))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

#: PDF 搜索根（**顺序即优先级**）：**`pdf_source_dir`（取阅真源，默认 `output/1_Original_PDF`，
#: `config/pdf_source.json` 可配；四总目录名不带括号，Kevin 2026-10-14 指令）** → `inbox/**`（旧面，回落）→ 仓根 `*.pdf`（旧面，回落）。
#: ★ Kevin 约定（2026-10-14，output 四总目录落地）：**`~/Downloads` 已移出默认搜索面**
#: ——不再从 Downloads 主动读 PDF；同名副本也不搬不删（sha 去重口径见 docs/output-layout-v0.1.md）。
PDF_SEARCH_GLOBS = [
    f"{pdf_source_dir()}/**/*.pdf",
    "inbox/**/*.pdf",
    "*.pdf",
]


def _norm_stem(name: str) -> str:
    """书名/文件名容错归一键：**去目录、去扩展名、压掉全部空白、大小写折叠**。

    用于「按书名匹配」时吸收**多空格 / 单空格差异 / 后缀差异**（口径：登记键＝PDF 名逐字，
    但物理盘上文件名可能空格不一，故匹配用归一键、留痕用原名）。
    """
    stem = os.path.splitext(os.path.basename(str(name)))[0]
    return re.sub(r"\s+", "", stem).casefold()


def _pdf_index() -> dict[str, Path]:
    """⇒ {归一键: 首个命中路径}（**按 `PDF_SEARCH_GLOBS` 顺序，先到先得**）。"""
    idx: dict[str, Path] = {}
    for g in PDF_SEARCH_GLOBS:
        pat = os.path.expanduser(g)
        if not os.path.isabs(pat):
            pat = str(REPO / pat)
        import glob as _glob
        for p in sorted(_glob.glob(pat, recursive=True)):
            path = Path(p)
            if not path.is_file():
                continue
            idx.setdefault(_norm_stem(path.name), path)
    return idx


def discover_books(only: str | None) -> list[tuple[str, Path | None, dict, bool]]:
    """⇒ `[(pdf_name, pdf_path|None, registered_entry, unconfirmed)]`（已登记 ∪ 盘上可寻者）。

    匹配：先**原名精确**（逐字），再**归一键**（压空白/扩展名，吸收空格差异）。
    """
    keys = json.loads(DIR_KEYS.read_text(encoding="utf-8"))
    books = keys.get("books", {})
    idx = _pdf_index()
    out = []
    for pdf_name, entry in books.items():
        if only and only not in pdf_name:
            continue
        unconfirmed = entry.get("dir_key_source") == "pdf_name_unconfirmed"
        # 原名精确与归一键等价（归一键压掉空格差异）；匹配优先级由 `PDF_SEARCH_GLOBS` 顺序决定。
        found = idx.get(_norm_stem(pdf_name))
        out.append((pdf_name, found, entry, unconfirmed))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只扫（子串匹配）书名")
    ap.add_argument("--no-ocr", action="store_true", help="只读文本层（不跑 OCR；调试用）")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db)

    import processor  # 仅此处起用图像栈（venv）

    books = discover_books(args.only)
    batch_id = "biblio-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    ensure_schema(db_path)      # 先建表，再落库（防空列名）
    t_start = time.time()
    results = []
    scanned = 0
    ok = 0
    failed = 0

    print(f"[biblio] batch={batch_id} books={len(books)} dpi={biblio.SCAN_DPI} "
          f"face=head{biblio.SCAN_FACE_HEAD_PAGES}+tail{biblio.SCAN_FACE_TAIL_PAGES}")
    for pdf_name, pdf_path, entry, unconfirmed in books:
        if pdf_path is None:
            print(f"[biblio] SKIP (PDF 不在盘，保留登记值): {pdf_name}")
            rec = {
                "book_ref": pdf_name, "isbn13": None, "isbn10": None, "cip_code": None,
                "title": None, "publisher": None, "pub_year": None, "edition": None,
                "source": "unscanned", "verify_state": "unverified",
                "verify_note": "PDF 不在盘 ⇒ 未现场识别（skipped_pdf_absent）；登记值见 dir_key_current/recorded_isbn",
                "evidence": {
                    "note": "PDF not on disk",
                    "skipped_pdf_absent": True,
                    "scan_face_pages": [], "ocr_pages": [],
                    "isbn_candidates": [], "cip_candidates": [],
                    "publishers": [], "pub_years": [],
                    "cross_verify": {"verify_state": "unverified", "prefix": None,
                                     "table_publisher": None, "ocr_publisher": None,
                                     "match": None, "note": "skipped_pdf_absent"},
                    "page_evidence": [],
                },
                "dir_key_recommended": None,
                "dir_key_source_recommended": None, "dir_key_current": entry.get("dir_key"),
                "dir_key_source_current": entry.get("dir_key_source"),
                "isbn_source": None, "recorded_isbn": entry.get("isbn"),
                "pdf_sha256": None, "pages_scanned": 0, "scan_dpi": biblio.SCAN_DPI,
                "isbn13_derived": False, "isbn10_derived": False,
            }
            results.append(rec)
            upsert_book(db_path, rec, batch_id)
            continue
        t0 = time.time()
        import pymupdf
        doc = pymupdf.open(str(pdf_path))
        n = len(doc)
        face = biblio.page_face_indices(n)
        pages = [scan_page(processor, doc, i, do_ocr=not args.no_ocr) for i in face]
        doc.close()
        rec = summarize_book(pdf_name, pages, entry, unconfirmed)
        rec["pdf_sha256"] = _sha256(pdf_path)
        rec["pages_scanned"] = len(face)
        rec["scan_dpi"] = biblio.SCAN_DPI
        rec["elapsed_s"] = round(time.time() - t0, 2)
        results.append(rec)
        scanned += 1
        if rec["verify_state"] == "ok":
            ok += 1
        if rec["verify_state"] in ("unverified", "checksum_fail"):
            failed += 0  # 不计失败——unverified 是如实结果
        upsert_book(db_path, rec, batch_id)
        print(f"[biblio] {pdf_name}: isbn13={rec['isbn13']} isbn10={rec['isbn10']} "
              f"publisher={rec['publisher']} state={rec['verify_state']} "
              f"rec_key={rec['dir_key_recommended']} ({rec['elapsed_s']}s)")

    summary = {
        "batch_id": batch_id,
        "created_at": _now(),
        "status": "done",
        "books_total": len(books),
        "books_scanned": scanned,
        "books_ok": ok,
        "books_failed": failed,
        "candidates_ok": sum(1 for r in results if r["isbn13"] or r["isbn10"]),
        "elapsed_s": round(time.time() - t_start, 2),
        "params": {"dpi": biblio.SCAN_DPI, "face_head": biblio.SCAN_FACE_HEAD_PAGES,
                   "face_tail": biblio.SCAN_FACE_TAIL_PAGES,
                   "anchor_words": list(biblio.ANCHOR_WORDS), "no_ocr": args.no_ocr,
                   "only": args.only},
        "constants": {"PUBLISHER_PREFIX_MAP": biblio.PUBLISHER_PREFIX_MAP},
    }
    (out_dir / "scan_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    ensure_schema(db_path)
    write_batch(db_path, batch_id, summary, "biblio-metadata 阶段1 原型：版权页 OCR ＋ 交叉自证 ＋ 目录键推荐")
    print(f"[biblio] done: {json.dumps({k: summary[k] for k in ('books_total','books_scanned','books_ok','elapsed_s')}, ensure_ascii=False)}")
    print(f"[biblio] out={out_dir} db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
