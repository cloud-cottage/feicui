#!/usr/bin/env python
"""ops/ocr-corrector · 从 `stamps.text` 挖「古玺用字」语料（**只读**，纯统计）。

产出（落 `ops/ocr-corrector/out/`）：
  - `char_freq.csv`        单字频次表（全表 2655 行非空 text 的逐字统计）
  - `char_freq_by_book.csv` 逐书（`pdf_name`）单字频次
  - `rare_chars.csv`       「在实际释文里出现、但通用 OCR 结构性不可输出 / 罕见」的字清单
  - `corpus_stats.json`    本次运行的读数总账（含 PP-OCR rec 字典指纹）

红线：
  - **只读** `~/bistro/data/yinpu.db`（`mode=ro`），不写任何库、不落 `output/`。
  - 不 import streamlit / webview / api / processor。

口径说明（**统计事实，不是映射**）：
  - `count` = 该字在 2655 行非空 `text` 里的出现次数（**含数字 / 拉丁 / 标点**，另立列分类）。
  - `in_ppocr_rec_dict` = 该字是否在 **本机 RapidOCR 所用 PP-OCRv6 rec 模型内嵌字符表**里
    （从 ONNX metadata 的 `character` 键现取，形态见下）。
    ★ 这个只有 `False` 才有强含义：**CTC 解码头只能吐出字典内的字** ⇒ `False` ⇒
      通用 OCR **结构上不可能**输出该字（不是「容易读错」，是「读不出来」）。
      而 `True` **不保证**能读对（例：`鈢` 在字典里，实测 248 枚池 0 命中 —— 见 README）。
  - `tier`：`hard_unmappable`（不在 rec 字典）｜`hapax`（corpus 出现 1 次）｜
    `rare_le3`（≤3）｜`common`（>3）。

跑法：
    ./venv/bin/python ops/ocr-corrector/extract_corpus_stats.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PROD_DB = Path("/Users/kevin/bistro/data/yinpu.db")
REC_MODEL = REPO / "venv/lib/python3.11/site-packages/rapidocr/models/PP-OCRv6_rec_small.onnx"

CATEGORIES = (
    ("digit", lambda c: c.isdigit() and c.isascii()),
    ("latin", lambda c: c.isascii() and c.isalpha()),
    ("punct", lambda c: not c.isalnum()),
    ("han", lambda c: not c.isascii()),
)


def classify(ch: str) -> str:
    if ch.isascii() and ch.isdigit():
        return "digit"
    if ch.isascii() and ch.isalpha():
        return "latin"
    if not ch.isalnum():
        return "punct"
    return "han"


def load_ppocr_dict(path: Path) -> tuple[set[str], dict]:
    """从 ONNX metadata 的 `character` 键取 PP-OCR rec 内嵌字符表（**零联网**）。"""
    if not path.exists():
        return set(), {"available": False, "path": str(path)}
    import onnxruntime as ort

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    chars = sess.get_modelmeta().custom_metadata_map["character"].splitlines()
    return set(chars), {
        "available": True,
        "path": str(path.relative_to(REPO)),
        "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
        "n_chars": len(chars),
        "keys": ["character"],
    }


def read_texts(db: Path) -> list[tuple[str, str]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select coalesce(pdf_name,''), text from stamps "
            "where text is not null and trim(text) <> ''"
        ).fetchall()
    finally:
        con.close()
    return [(str(a or ""), str(b)) for a, b in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(PROD_DB))
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    db = Path(a.db)
    rows = read_texts(db)
    dict_chars, dict_meta = load_ppocr_dict(REC_MODEL)

    freq: collections.Counter[str] = collections.Counter()
    by_book: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    rows_by_char: dict[str, int] = collections.Counter()
    cat_counts: collections.Counter[str] = collections.Counter()
    for pdf_name, text in rows:
        seen = set()
        for ch in text:
            freq[ch] += 1
            cat_counts[classify(ch)] += 1
            by_book[pdf_name][ch] += 1
            seen.add(ch)
        for ch in seen:
            rows_by_char[ch] += 1

    han_freq = {c: n for c, n in freq.items() if classify(c) == "han"}
    top = sorted(han_freq.items(), key=lambda kv: (-kv[1], kv[0]))

    # ---- char_freq.csv ----
    with (out / "char_freq.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "char", "codepoint", "count", "rows", "count_rank_han", "category",
            "in_ppocr_rec_dict", "tier", "name",
        ])
        for i, (c, n) in enumerate(top, 1):
            in_dict = (c in dict_chars) if dict_meta.get("available") else ""
            tier = "hard_unmappable" if in_dict is False else (
                "hapax" if n == 1 else "rare_le3" if n <= 3 else "common")
            w.writerow([c, f"U+{ord(c):04X}", n, rows_by_char[c], i, "han",
                        in_dict, tier, unicodedata.name(c, "")])
        # 非汉字单列（数字/拉丁/标点），便于看到噪声面
        for c, n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
            if classify(c) == "han":
                continue
            in_dict = (c in dict_chars) if dict_meta.get("available") else ""
            w.writerow([c, f"U+{ord(c):04X}", n, rows_by_char[c], "", classify(c),
                        in_dict, "non_han", unicodedata.name(c, "")])

    # ---- char_freq_by_book.csv（只列汉字，前 200/书）----
    with (out / "char_freq_by_book.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pdf_name", "rank", "char", "count", "in_ppocr_rec_dict"])
        for pdf_name, cnt in sorted(by_book.items(), key=lambda kv: -sum(kv[1].values())):
            han = [(c, n) for c, n in cnt.items() if classify(c) == "han"]
            for i, (c, n) in enumerate(sorted(han, key=lambda kv: (-kv[1], kv[0]))[:200], 1):
                in_dict = (c in dict_chars) if dict_meta.get("available") else ""
                w.writerow([pdf_name, i, c, n, in_dict])

    # ---- rare_chars.csv ----
    rare = []
    for c, n in top:
        in_dict = (c in dict_chars) if dict_meta.get("available") else None
        if in_dict is False or n <= 3:
            rare.append({
                "char": c, "codepoint": f"U+{ord(c):04X}", "count": n,
                "rows": rows_by_char[c], "in_ppocr_rec_dict": in_dict,
                "tier": "hard_unmappable" if in_dict is False else ("hapax" if n == 1 else "rare_le3"),
            })
    rare.sort(key=lambda r: (r["tier"] != "hard_unmappable", r["count"], r["codepoint"]))
    with (out / "rare_chars.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rare[0].keys()) if rare else
                           ["char", "codepoint", "count", "rows", "in_ppocr_rec_dict", "tier"])
        w.writeheader()
        w.writerows(rare)

    stats = {
        "source": {"db": str(db), "db_sha256_16": hashlib.sha256(db.read_bytes()).hexdigest()[:16]
                   if db.exists() else None,
                   "mode": "read_only", "rows_with_nonempty_text": len(rows)},
        "ppocr_rec_dict": dict_meta,
        "totals": {
            "chars_occurrences": sum(freq.values()),
            "chars_unique": len(freq),
            "han_unique": len(han_freq),
            "by_category": dict(cat_counts),
            "han_not_in_rec_dict": sum(1 for c in han_freq if dict_meta.get("available") and c not in dict_chars),
            "han_hapax": sum(1 for c, n in han_freq.items() if n == 1),
        },
        "top_han": [{"char": c, "count": n} for c, n in top[:50]],
        "books": {k: sum(v.values()) for k, v in sorted(by_book.items(), key=lambda kv: -sum(kv[1].values()))},
        "notes": [
            "count 含数字/拉丁/标点噪声；分析古玺用字请先按 category=='han' 过滤（本表 han 行已单列）。",
            "in_ppocr_rec_dict=False ⇒ CTC 解码头结构上无法输出该字（强含义）；True 不代表能读对。",
            "本表是**统计事实**，不是「异体字映射」——映射另见 local-dist/data/guxi_variant_map.json（每条带 source/confidence/verified）。",
        ],
    }
    (out / "corpus_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    t = stats["totals"]
    print(f"[corpus] rows={len(rows)}  unique={t['chars_unique']}  han_unique={t['han_unique']}")
    print(f"[corpus] categories={t['by_category']}")
    print(f"[corpus] han 不在 PP-OCR rec 字典: {t['han_not_in_rec_dict']}  hapax: {t['han_hapax']}")
    print(f"[corpus] rec 字典 {dict_meta.get('n_chars')} 字  sha16={dict_meta.get('sha256_16')}")
    print(f"[corpus] top20(han) = " + " ".join(f"{c}:{n}" for c, n in top[:20]))
    print(f"[out] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
