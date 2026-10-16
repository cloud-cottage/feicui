#!/usr/bin/env python
"""ops/ocr-corrector · 生成「需人工审核的候选清单」表（≤ `--n` 行，供 Kevin/专家逐条判）。

严格按 `ops/ocr-corrector/out/candidates_summary.csv`（=`gen_candidates.py` 的产物）排序后
截前 N 条 —— **不新增任何判断**，只把证据列排版成一张表。

排序键（与 gen_candidates 一致，无魔法权重）：池内出现次数 ↓ → 跨引擎一致次数 ↓ → 字形代理分 ↓

跑法：
    ./venv/bin/python ops/ocr-corrector/make_review_table.py --n 30
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out_dir)

    rows = list(csv.DictReader((out / "candidates_summary.csv").open(encoding="utf-8")))
    entries = {e["from"]: e for e in json.loads(
        (out / "candidates_map_entries.json").read_text(encoding="utf-8"))["entries"]}
    rows.sort(key=lambda r: (-int(r["pool_occurrences"]),
                             -max(int(r.get(f"cand{i}_xe") or 0) for i in range(1, 6)),
                             -max(float(r.get(f"cand{i}_glyph_sim") or 0) for i in range(1, 6))))
    rows = rows[: a.n]

    hdr = ("| # | OCR 报出的字 | 建议候选 Top1 | 备选（字形分/跨引擎次/corpus次） | 池内出现 | "
           "OCR 最高原始分 | 出现样本 | 跨引擎对方报的字 | 字形代理分 | corpus 频次 | 字表 rule_id |")
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [hdr, sep]
    csv_rows = []
    for i, r in enumerate(rows, 1):
        ch = r["from_char"]
        alt = " / ".join(
            f"{r.get(f'cand{j}_char')}({r.get(f'cand{j}_glyph_sim')}/{r.get(f'cand{j}_xe')}/"
            f"{r.get(f'cand{j}_corpus_count')})"
            for j in range(2, min(int(r["n_candidates"]), 5) + 1) if r.get(f"cand{j}_char"))
        e = entries.get(ch)
        xe = "|".join(f"{k}×{v}" for k, v in
                      (e["evidence"]["cross_engine_counter_proposals"].items() if e else []))
        lines.append(
            f"| {i} | `{ch}` | `{r['cand1_char']}` | {alt or '—'} | {r['pool_occurrences']} | "
            f"{r['ocr_score_max'] or '—'} | `{r['pool_stems']}` | {xe or '—'} | "
            f"{r['cand1_glyph_sim']} | {r['cand1_corpus_count']} | "
            f"{e['rule_id'] if e else '_(未入表)_'} |")
        csv_rows.append({
            "no": i, "from": ch, "suggest_top1": r["cand1_char"],
            "alternatives": alt, "pool_occurrences": r["pool_occurrences"],
            "ocr_score_max": r["ocr_score_max"], "pool_stems": r["pool_stems"],
            "cross_engine_all": xe,
            "glyph_sim_top1": r["cand1_glyph_sim"], "corpus_count_top1": r["cand1_corpus_count"],
            "rule_id": e["rule_id"] if e else "",
            "source": e["source"] if e else "",
            "verified": False,
        })

    md = ["# 需人工审核的候选清单（Top %d）" % len(rows), "",
          "> 生成：`ops/ocr-corrector/make_review_table.py --n %d`（数据源 "
          "`out/candidates_summary.csv` / `out/candidates_map_entries.json`）" % a.n,
          "> ★ 全部 **`verified=false`、默认不生效**：本表只作人工审核的输入，"
          "不构成任何「已验证映射」。审核通过 ⇒ 改 `source='measured_truth'` + `verified=true`；"
          "不通过 ⇒ 删条。", "",
          "排序键：池内出现次数 ↓ → 跨引擎一致次数 ↓ → 字形代理分 ↓（无魔法权重）；"
          "`备选` 括号内 = 字形代理分/跨引擎一致次数/corpus 频次。", "", *lines, ""]
    (out / "candidates_top_table.md").write_text("\n".join(md), encoding="utf-8")
    if csv_rows:
        with (out / "candidates_top_table.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)

    print("\n".join(md))
    print(f"[table] 写出 {out}/candidates_top_table.md | .csv（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
