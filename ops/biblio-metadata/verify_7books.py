#!/usr/bin/env python
"""7 本对照表（收口复算）—— Kong / biblio-metadata 单 · 2026-10-11。

**只读 `var/biblio_ingest.db`**（Zang 逐书跑的产物），**不重跑全批量、不写库、不切目录键**。
把**收口后**的 `server/app/biblio.py` 三个纯函数（形态/长度闸 `shape_reason` ＋ 出版社交叉自证
`cross_verify` ＋ 目录键推荐 `recommend_dir_key`）**重放到库里已存的候选 `raw`** 上，
复算出「若用修正后的流水线跑同样文本，会得到什么」，并与库里（收口前）旧值对照。

复算的**忠实性**：三处缺陷（① 拼接噪声假号 ② 目录键推导 ③ 无号回退未规范化）全部是**抽取候选之后
的纯后处理**；新旧抽取器的唯一差别＝形态/长度闸（把 `>13` 位整段拒掉）。故**对库里已存候选的 `raw`
重放新闸**，恰等于新抽取器在同一文本上的输出。

    cd /Users/kevin/bistro/feicui
    python3 ops/biblio-metadata/verify_7books.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "ops" / "biblio-metadata"
DB = REPO / "var" / "biblio_ingest.db"
DIR_KEYS = REPO / "config" / "book_dir_keys.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = _load("biblio", REPO / "server" / "app" / "biblio.py")


def _shape_reapply(cands: list[dict]) -> tuple[list[dict], list[dict]]:
    """把**新形态闸**重放到库里已存候选上 ⇒ `(accepted, rejected)`。

    对每条候选按 `normalize_isbn(raw)` 重算形态闸：不合形 ⇒ 整段拒（不切片）；
    合形且校验位过且非退化且锚词邻近 ⇒ 采信。
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_rej: set[str] = set()
    for c in cands:
        raw = c.get("raw") or ""
        norm = b.normalize_isbn(raw) or ""
        sr = b.shape_reason(norm)
        if sr is not None:
            key = f"{sr}:{norm}"
            if key not in seen_rej:
                seen_rej.add(key)
                rejected.append({"raw": raw, "normalized": norm, "shape_reason": sr,
                                 "kind": None, "valid": False, "page": c.get("page"),
                                 "source": c.get("source")})
            continue
        brief = {"raw": raw, "normalized": c.get("normalized"), "kind": c.get("kind"),
                 "valid": c.get("valid"), "page": c.get("page"), "source": c.get("source"),
                 "anchor_near": c.get("anchor_near"),
                 "degenerate_reason": b.degenerate_reason(c.get("normalized") or "")}
        if b.is_accepted_candidate({"valid": c.get("valid"), "anchor_near": c.get("anchor_near"),
                                    "rejected_reason": brief["degenerate_reason"]}):
            accepted.append(brief)
        else:
            key = f"rej:{c.get('normalized')}"
            if key not in seen_rej:
                seen_rej.add(key)
                rejected.append({**brief, "shape_reason": None})
    return accepted, rejected


def main() -> int:
    keys = json.loads(DIR_KEYS.read_text(encoding="utf-8")).get("books", {})
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("select * from book_biblio order by book_ref")]
    conn.close()

    out_rows = []
    for r in rows:
        name = r["book_ref"]
        ev = json.loads(r["evidence"]) if r.get("evidence") else {}
        cands = ev.get("isbn_candidates", [])
        accepted, rejected = _shape_reapply(cands)

        # 排序偏好同 scan_biblio.summarize_book：labeled → isbn13 → 页/位置
        def _key(c):
            return (not c.get("labeled", False) if "labeled" in c else False,
                    c.get("kind") != "isbn13", c.get("page") or 0)
        valid = [c for c in accepted if c.get("valid")]
        valid.sort(key=lambda c: (c.get("kind") != "isbn13", c.get("page") or 0))
        c13 = next((c for c in valid if c.get("kind") == "isbn13"), None)
        c10 = next((c for c in valid if c.get("kind") == "isbn10"), None)
        isbn13_obs = c13["normalized"] if c13 else None
        isbn10_obs = c10["normalized"] if c10 else None

        publisher = r.get("publisher")
        if isbn13_obs or isbn10_obs:
            xv = b.cross_verify(isbn13_obs or isbn10_obs, publisher)
        else:
            xv = {"verify_state": "unverified", "note": "扫描面内未识别到可用 ISBN（校验位）",
                  "prefix": None, "table_publisher": None, "ocr_publisher": publisher, "match": None}

        cur = keys.get(name, {})
        unconfirmed = (cur.get("dir_key_source") == "pdf_name_unconfirmed")
        rec = b.recommend_dir_key(name, isbn10=isbn10_obs, isbn13=isbn13_obs,
                                  unconfirmed=unconfirmed)

        out = {
            "book_ref": name,
            "dir_key_current": cur.get("dir_key"),
            "dir_key_source_current": cur.get("dir_key_source"),
            "isbn13_recomputed": isbn13_obs,
            "isbn10_recomputed": isbn10_obs,
            "publisher": publisher,
            "verify_state_recomputed": xv["verify_state"],
            "verify_note": xv.get("note"),
            "dir_key_recommended": rec["dir_key"],
            "dir_key_source_recommended": rec["dir_key_source"],
            "needs_switch": (rec["dir_key"] != cur.get("dir_key")),
            # 收口前（库里旧值）—— 供对照
            "isbn13_db_old": r.get("isbn13"), "isbn10_db_old": r.get("isbn10"),
            "verify_state_db_old": r.get("verify_state"),
            "dir_key_recommended_db_old": r.get("dir_key_recommended"),
            "accepted": accepted,
            "rejected": rejected,
        }
        out_rows.append(out)

    payload = {"generated_at": __import__("datetime").datetime.now().astimezone()
               .replace(microsecond=0).isoformat(),
               "source_db": str(DB.relative_to(REPO)),
               "note": "收口后复算（形态闸重放）；只读库、不切目录键",
               "constants": {"MAX_ISBN_DIGITS": b.MAX_ISBN_DIGITS,
                             "PUBLISHER_PREFIX_MAP": b.PUBLISHER_PREFIX_MAP},
               "rows": out_rows}
    (OUT / "seven_book_table.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 7 本对照表（收口后复算 · Kong）", "",
             f"数据源：`{DB.relative_to(REPO)}`（Zang 逐书跑）＋ 收口后 `server/app/biblio.py` 复算。",
             "**只给建议：不切目录键、不改名、不改路径。**", "",
             "| 书（PDF 名） | 现目录键 | 识别 ISBN（直读） | 识别出版社 | 自证态 | 建议目录键 | 建议来源 | 需切键 | 旧（收口前）建议 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for o in out_rows:
        isbn = o["isbn13_recomputed"] or o["isbn10_recomputed"] or "—"
        old = o["dir_key_recommended_db_old"] or "—"
        lines.append("| {b} | {dc} | {isbn} | {pub} | {vs} | {rk} | {rs} | {sw} | {old} |".format(
            b=o["book_ref"], dc=o["dir_key_current"] or "—", isbn=isbn, pub=o["publisher"] or "—",
            vs=o["verify_state_recomputed"], rk=o["dir_key_recommended"] or "—",
            rs=o["dir_key_source_recommended"] or "—",
            sw="是" if o["needs_switch"] else "否", old=old))
    (OUT / "seven_book_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[wrote] {OUT/'seven_book_table.json'} / {OUT/'seven_book_table.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
