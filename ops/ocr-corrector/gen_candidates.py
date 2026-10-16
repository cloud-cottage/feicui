#!/usr/bin/env python
"""ops/ocr-corrector · 候选生成（**只产候选，一律 verified=false**）。

输入（全部只读）：
  - `ops/ocr-rapid/raw/rapid_pool.jsonl`      248 枚池的 RapidOCR 逐枚输出（pipeline / rec_only）
  - `labeling/raw/abc_all_248.json`            248 枚池的 PaddleOCR A/B/C 输出（跨引擎证据）
  - `ops/ocr-corrector/out/char_freq.csv`      `stamps.text` 单字频次（由 extract_corpus_stats.py 产）

做法（每一步都可复算，**没有语言学猜测**）：
  1. **目标池**＝`stamps.text` 里出现 ≥ `--min-freq` 次的汉字（统计事实：这些字真的被用来写释文）。
  2. 取 248 池里**所有引擎/配置**输出的汉字；若它**不在**目标池 ⇒ 记为「非古玺高频用字」
     （＝实测里通用 OCR 报出来的字，却不在本仓释文用字域里）。
  3. 给每个这样的字，从目标池里按**字形代理相似度**取 `--top-k` 个候选（`glyph_shape.py`）。
  4. 再按固定键排序（**不设魔法权重**）：跨引擎在同一枚上一致提出的次数 ↓、glyph_sim ↓、
     该候选在 `stamps.text` 的频次 ↓。
  5. 产 `candidates_for_review.csv`（逐对）＋ `candidates_summary.csv`（逐字，Top-K 并排）＋
     `candidates_map_entries.json`（**待人工审核的字表条目**，`verified=false`）。

★ 字表内容纪律：本脚本产出的每一条都 `source ∈ {cross_engine, font_glyph_shape}`、
  `confidence<=0.5`、`verified=false` ⇒ 在纠错器里**默认只出候选、绝不自动改写**。
★ 「证据列」一律照登：出现在哪些样本（stem）、OCR 原始分、跨引擎对方报了什么、
  字形代理分数与字体名。人工审核时**只看这些列**判断，不看我们的排序。

跑法：
    ./venv/bin/python ops/ocr-corrector/gen_candidates.py
    ./venv/bin/python ops/ocr-corrector/gen_candidates.py --min-freq 3 --top-k 5
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from glyph_shape import GlyphShape  # noqa: E402

OUT = HERE / "out"
RAPID_JSONL = REPO / "ops/ocr-rapid/raw/rapid_pool.jsonl"
PP_ABC = REPO / "labeling/raw/abc_all_248.json"
FREQ_CSV = OUT / "char_freq.csv"
POOL_MANIFEST = REPO / "spike-ocr/raw/corpus_manifest.json"


def load_freq(min_freq: int) -> tuple[dict[str, int], dict[str, int]]:
    """→ (han 频次 dict, han 秩 dict)。只取 category=='han' 的行。"""
    freq: dict[str, int] = {}
    with FREQ_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["category"] != "han":
                continue
            n = int(row["count"])
            if n >= min_freq:
                freq[row["char"]] = n
    rank = {c: i for i, c in enumerate(sorted(freq, key=lambda c: (-freq[c], c)), 1)}
    return freq, rank


def load_rapid() -> list[dict]:
    rows = []
    with RAPID_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_paddle() -> dict[str, dict[str, str]]:
    d = json.loads(PP_ABC.read_text(encoding="utf-8"))
    return {c["stem"]: {k: v for k, v in c.items() if k in ("A", "B", "C")} for c in d["crops"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-freq", type=int, default=3, help="目标池阈值：corpus 出现次数 ≥ N")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--map-min-glyph-sim", type=float, default=0.35,
                    help="进字表的门槛（低于此只留在 CSV，不进字表）")
    ap.add_argument("--candidate-engine-prefix", default="rapid",
                    help="只把引擎名以此前缀开头的输出字当候选源字（其余引擎只作跨引擎证据）")
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    freq, rank = load_freq(a.min_freq)
    rapid = load_rapid()
    paddle = load_paddle()
    corpus_rows = json.loads((OUT / "corpus_stats.json").read_text(encoding="utf-8"))[
        "source"]["rows_with_nonempty_text"]

    # --- 逐枚收集各引擎输出：{stem: [(engine, text, scores)]} ---
    per_stem: dict[str, list[tuple[str, str, list[float]]]] = collections.defaultdict(list)
    for r in rapid:
        per_stem[r["stem"]].append((f"rapid:{r['config']}", "".join(r["texts"]),
                                    [float(s) for s in r["scores"]]))
    for stem, cfgs in paddle.items():
        for name, text in cfgs.items():
            if text:
                per_stem[stem].append((f"paddle:{name}", text, []))

    # --- 逐字收集证据 ---
    occ: dict[str, list[dict]] = collections.defaultdict(list)       # char -> [{stem,engine,score}]
    xengine: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    xengine_stems: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for stem, outs in per_stem.items():
        for engine, text, scores in outs:
            for i, ch in enumerate(text):
                if not _is_han(ch):
                    continue
                sc = scores[i] if i < len(scores) else None
                occ[ch].append({"stem": stem, "engine": engine, "score": sc})
                for engine2, text2, _ in outs:
                    if engine2 == engine:
                        continue
                    for ch2 in text2:
                        if _is_han(ch2) and ch2 != ch:
                            xengine[ch][ch2] += 1
                            if stem not in xengine_stems[ch][ch2]:
                                xengine_stems[ch][ch2].append(stem)

    gs = GlyphShape()
    # ★ 只把**待评估引擎**（默认 RapidOCR）的输出字当候选源字；Paddle 的输出只作**跨引擎证据**。
    #   （否则 Paddle 的现代字表会把候选面放大成几百条噪声 —— 实测未限制时 342 种/194 条。）
    src_prefix = a.candidate_engine_prefix
    pool_chars = sorted((c for c in occ if any(o["engine"].startswith(src_prefix) for o in occ[c])),
                        key=lambda c: (-len(occ[c]), c))
    not_in_target = [c for c in pool_chars if c not in freq]

    pair_rows: list[dict] = []
    summary_rows: list[dict] = []
    map_entries: list[dict] = []
    skipped_non_han = skipped_in_target = 0
    for ch in pool_chars:
        if not _is_han(ch):
            skipped_non_han += 1
            continue
        if ch in freq:
            skipped_in_target += 1
            continue
        sims = [(c, gs.compare(ch, c)["glyph_sim"], gs.compare(ch, c)["glyph_quad_iou"],
                 gs.compare(ch, c)["glyph_iou"]) for c in freq]
        sims.sort(key=lambda t: -t[1])
        glyph_top = sims[: a.top_k]
        cands = []
        for c, sim, quad, i in glyph_top:
            xe = xengine[ch].get(c, 0)
            cands.append({
                "from": ch, "to": c, "glyph_sim": sim, "glyph_iou": i, "glyph_quad_iou": quad,
                "cross_engine_count": xe,
                "cross_engine_stems": "|".join(xengine_stems[ch].get(c, [])[:5]),
                "corpus_count": freq[c], "corpus_rank": rank[c],
            })
        # 固定排序键（无魔法权重）：跨引擎一致次数 ↓ → glyph_sim ↓ → corpus 频次 ↓
        cands.sort(key=lambda d: (-d["cross_engine_count"], -d["glyph_sim"], -d["corpus_count"]))
        for r, d in enumerate(cands, 1):
            d["final_rank"] = r
        # glyph_rank 单独按 glyph_sim 重排（便于看出排序键改了什么）
        for r, d in enumerate(sorted(cands, key=lambda x: -x["glyph_sim"]), 1):
            d["glyph_rank"] = r
        stems = sorted({o["stem"] for o in occ[ch]})
        scores = [o["score"] for o in occ[ch] if o["score"] is not None]
        common = {
            "from_char": ch, "pool_occurrences": len(occ[ch]),
            "pool_stems": "|".join(stems[:6]) + ("…" if len(stems) > 6 else ""),
            "engines": "|".join(sorted({o["engine"] for o in occ[ch]})),
            "ocr_score_min": round(min(scores), 4) if scores else "",
            "ocr_score_max": round(max(scores), 4) if scores else "",
            "corpus_count_of_from": 0,
        }
        for d in cands:
            row = dict(common)
            row.update({k: v for k, v in d.items() if k != "from"})
            row["cross_engine_all"] = "|".join(f"{k}×{v}" for k, v in xengine[ch].most_common(5))
            pair_rows.append(row)
        summary_rows.append({
            **common,
            **{f"cand{i}_char": c["to"] for i, c in enumerate(cands, 1)},
            **{f"cand{i}_glyph_sim": c["glyph_sim"] for i, c in enumerate(cands, 1)},
            **{f"cand{i}_corpus_count": c["corpus_count"] for i, c in enumerate(cands, 1)},
            **{f"cand{i}_xe": c["cross_engine_count"] for i, c in enumerate(cands, 1)},
            "n_candidates": len(cands),
        })

        # --- 字表条目（一字一条；其余候选进 evidence.alternatives）---
        top = cands[0]
        if top["cross_engine_count"] > 0 or top["glyph_sim"] >= a.map_min_glyph_sim:
            src = "cross_engine" if top["cross_engine_count"] > 0 else "font_glyph_shape"
            map_entries.append({
                "rule_id": f"gx-cand-{len(map_entries) + 1:04d}",
                "from": ch,
                "to": top["to"],
                "source": src,
                "confidence": 0.3 if src == "cross_engine" else 0.25,
                "verified": False,
                "scope": "seal_text",
                "note": (
                    f"待人工审核候选（**无真值**，默认不生效）：248 枚池里该字被 OCR 报出 "
                    f"{len(occ[ch])} 次（engine={'|'.join(sorted({o['engine'] for o in occ[ch]}))}，"
                    f"最高原始分 {max(scores) if scores else 'N/A'}），但该字**不在** `stamps.text` "
                    f"的释文用字域（出现 0 次）；候选按「跨引擎一致次数 → 字形代理相似度 → corpus 频次」排序。"
                ),
                "evidence": {
                    "kind": "pool_observation",
                    "pool_occurrences": len(occ[ch]),
                    "pool_stems": stems[:10],
                    "engines": sorted({o["engine"] for o in occ[ch]}),
                    "ocr_scores": [o["score"] for o in occ[ch]][:10],
                    "corpus_count_of_from_char": 0,
                    "cross_engine_counter_proposals": dict(xengine[ch].most_common(5)),
                    "glyph": {k: v for k, v in top.items()
                              if k in ("glyph_sim", "glyph_iou", "glyph_quad_iou")},
                    "glyph_font": gs.font_name,
                    "alternatives": [
                        {"to": c["to"], "rank": c["final_rank"], "glyph_sim": c["glyph_sim"],
                         "cross_engine_count": c["cross_engine_count"],
                         "corpus_count": c["corpus_count"]}
                        for c in cands[1:]
                    ],
                },
            })

    # --- 落盘 ---
    if pair_rows:
        with (out / "candidates_for_review.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
            w.writeheader()
            w.writerows(pair_rows)
    if summary_rows:
        with (out / "candidates_summary.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            w.writerows(summary_rows)

    (out / "candidates_map_entries.json").write_text(json.dumps({
        "generated_by": "ops/ocr-corrector/gen_candidates.py",
        "params": {"min_freq": a.min_freq, "top_k": a.top_k,
                   "map_min_glyph_sim": a.map_min_glyph_sim},
        "glyph_meta": gs.meta,
        "corpus": {"rows_with_nonempty_text": corpus_rows,
                   "target_pool_size": len(freq), "min_freq": a.min_freq},
        "counts": {
            "pool_han_chars": len([c for c in pool_chars if _is_han(c)]),
            "pool_chars_in_target_pool": skipped_in_target,
            "pool_chars_not_in_target_pool": len(not_in_target),
            "map_entries_emitted": len(map_entries),
            "pair_rows": len(pair_rows),
        },
        "discipline": "全部 source∈{cross_engine,font_glyph_shape} / confidence<=0.5 / verified=false",
        "entries": map_entries,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[cand] 目标池（corpus 汉字 count>={a.min_freq}）= {len(freq)} 字（corpus 行 {corpus_rows}）")
    print(f"[cand] 248 池 OCR 汉字输出 {len([c for c in pool_chars if _is_han(c)])} 种；"
          f"在目标池内 {skipped_in_target}、不在 {len(not_in_target)}")
    print(f"[cand] 字表候选条目 {len(map_entries)}；逐对 CSV {len(pair_rows)} 行")
    print(f"[cand] 字体 {gs.font_name}（黑体代理，非篆书）")
    print(f"[out ] {out}")
    return 0


def _is_han(ch: str) -> bool:
    return not ch.isascii() and ch.isalnum()


if __name__ == "__main__":
    sys.exit(main())
