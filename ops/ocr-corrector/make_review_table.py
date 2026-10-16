#!/usr/bin/env python
"""ops/ocr-corrector · 生成「需人工审核的候选清单」表（≤ `--n` 行，供 Kevin/专家逐条判）。

严格按 `ops/ocr-corrector/out/candidates_summary.csv`（=`gen_candidates.py` 的产物）排序后
截前 N 条 —— **不新增任何判断**，只把证据列排版成一张表。

排序键（与 gen_candidates 一致，无魔法权重）：池内出现次数 ↓ → 跨引擎一致次数 ↓ → 字形代理分 ↓

★ 分区（Kevin 2026-10-16 抽检裁定后）：
  - **A 区**：非字形代理候选（`cross_engine` / 未入表）—— 仍只作待审（`cross_engine` 已核 N=1 且判错，样本太小）。
  - **B 区**：`font_glyph_shape`（黑体栅格字形代理）候选 —— **仅存证/待审，一律不得作为推荐**：
    人工抽检 4 条判错 3 条，含**全表最高分 0.7454** 的 `干→千` ⇒ 该分数作为正确性判据已被证伪。
  - 已按裁定删除的条目（字表顶层 `rejected[]`）单独列出，**不参与纠错**。

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
MAP = HERE.parents[1] / "webui/data/guxi_variant_map.json"

HDR = ("| # | OCR 报出的字 | 建议候选 Top1 | 备选（字形分/跨引擎次/corpus次） | 池内出现 | "
       "OCR 最高原始分 | 出现样本 | 跨引擎对方报的字 | 字形代理分 | corpus 频次 | 字表 rule_id |")
SEP = "|---|---|---|---|---|---|---|---|---|---|---|"

#: B 区固定警告行（**不得**因为「看着分高」而删掉）
GLYPH_WARNING = (
    "> ★ **警告（人工抽检证伪）**：本区证据是「黑体栅格字形代理分」——人工抽检 4 条判错 3 条，"
    "含**全表最高分 0.7454** 的 `干→千`（判错）⇒ 该分数**不能**作为「映射正确」的判据。"
    "本区行**一律不得作为推荐**（不得进推荐位、不得进自动改写、不得据此排序结论），**只作存证/待审**。"
)
CROSS_WARNING = (
    "> 口径：本区（`cross_engine` / 未入表）同样 `verified=false`、默认不生效；`cross_engine` 已核样本 N=1 "
    "且判错 ⇒ **样本太小不足以定论**，保留待审，但不得作为推荐。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out_dir)

    rows: list[dict] = list(csv.DictReader((out / "candidates_summary.csv").open(encoding="utf-8")))
    entries = {e["from"]: e for e in json.loads(
        (out / "candidates_map_entries.json").read_text(encoding="utf-8"))["entries"]}
    map_data = json.loads(MAP.read_text(encoding="utf-8"))
    rejected = {r.get("from"): r for r in map_data.get("rejected", [])}

    rows.sort(key=lambda r: (-int(r["pool_occurrences"]),
                             -max(int(r.get(f"cand{i}_xe") or 0) for i in range(1, 6)),
                             -max(float(r.get(f"cand{i}_glyph_sim") or 0) for i in range(1, 6))))
    dropped = [r for r in rows if r["from_char"] in rejected]
    rows = [r for r in rows if r["from_char"] not in rejected][: a.n]

    def src_of(row: dict) -> str:
        e = entries.get(row["from_char"])
        return e["source"] if e else ""

    sec_a = [r for r in rows if src_of(r) != "font_glyph_shape"]
    sec_b = [r for r in rows if src_of(r) == "font_glyph_shape"]

    csv_rows = []

    def render(rs: list[dict], offset: int) -> list[str]:
        out_lines = [HDR, SEP]
        for i, r in enumerate(rs, offset + 1):
            ch = r["from_char"]
            alt = " / ".join(
                f"{r.get(f'cand{j}_char')}({r.get(f'cand{j}_glyph_sim')}/{r.get(f'cand{j}_xe')}/"
                f"{r.get(f'cand{j}_corpus_count')})"
                for j in range(2, min(int(r["n_candidates"]), 5) + 1) if r.get(f"cand{j}_char"))
            e = entries.get(ch)
            xe = "|".join(f"{k}×{v}" for k, v in
                          (e["evidence"]["cross_engine_counter_proposals"].items() if e else []))
            out_lines.append(
                f"| {i} | `{ch}` | `{r['cand1_char']}` | {alt or '—'} | {r['pool_occurrences']} | "
                f"{r['ocr_score_max'] or '—'} | `{r['pool_stems']}` | {xe or '—'} | "
                f"{r['cand1_glyph_sim']} | {r['cand1_corpus_count']} | "
                f"{e['rule_id'] if e else '_(未入表)_'} |")
            csv_rows.append({
                "no": i, "section": "B_font_glyph_shape" if src_of(r) == "font_glyph_shape" else "A_cross_engine",
                "from": ch, "suggest_top1": r["cand1_char"],
                "alternatives": alt, "pool_occurrences": r["pool_occurrences"],
                "ocr_score_max": r["ocr_score_max"], "pool_stems": r["pool_stems"],
                "cross_engine_all": xe,
                "glyph_sim_top1": r["cand1_glyph_sim"], "corpus_count_top1": r["cand1_corpus_count"],
                "rule_id": e["rule_id"] if e else "",
                "source": e["source"] if e else "",
                "verified": False,
                "recommendation_level": ("evidence_only（不得作为推荐）"
                                         if e and e["source"] == "font_glyph_shape" else "pending_review"),
            })
        return out_lines

    md = ["# 需人工审核的候选清单", "",
          "> 生成：`ops/ocr-corrector/make_review_table.py --n %d`（数据源 `out/candidates_summary.csv` / "
          "`out/candidates_map_entries.json` / 字表 `webui/data/guxi_variant_map.json`）" % a.n,
          "> ★ 全部 **`verified=false`、默认不生效**：本表只作人工审核的输入，不构成任何「已验证映射」。",
          "> 审核通过 ⇒ 改 `source='measured_truth'` + `verified=true`；不通过 ⇒ 删条（并在字表顶层 `rejected[]` 留痕）。",
          "> 排序键：池内出现次数 ↓ → 跨引擎一致次数 ↓ → 字形代理分 ↓（无魔法权重）。", ""]

    if rejected:
        md += ["## 已按人工裁定删除（Kevin 2026-10-16；不参与纠错，存证于字表 `rejected[]`）", "",
               " / ".join(f"`{f}→{v['to']}`（{v.get('rule_id')}，{v.get('source')}）"
                          for f, v in rejected.items()), ""]

    md += ["## A 区 · 非字形代理候选（`cross_engine` / 未入表）", "", CROSS_WARNING, ""]
    md += render(sec_a, 0)
    md += ["", "## B 区 · `font_glyph_shape`（黑体栅格字形代理）候选 —— 仅存证/待审，**一律不得作为推荐**", "",
           GLYPH_WARNING, ""]
    md += render(sec_b, len(sec_a))
    md += ["", f"（A 区 {len(sec_a)} 行 / B 区 {len(sec_b)} 行；已裁定删除 {len(dropped)} 行见上）", ""]

    (out / "candidates_top_table.md").write_text("\n".join(md), encoding="utf-8")
    if csv_rows:
        with (out / "candidates_top_table.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)

    print("\n".join(md))
    print(f"[table] 写出 {out}/candidates_top_table.md | .csv"
          f"（A {len(sec_a)} + B {len(sec_b)} = {len(csv_rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
