#!/usr/bin/env python
"""ops/ocr-corrector · 248 枚池评估（**描述性读数，不是准确率**）。

★ 诚实口径（硬约束）：`labeling/labels.csv` 的 `text_correct` 列**全空** ⇒ 本仓**没有真值**
  ⇒ 本脚本**不报**「准确率 / 准确率提升」。只报：
    触发率（含「域外字」的样本占比）／候选命中分布／Top 混淆对／逐字命中明细。
  要量化准确率，必须先有真值（格式与解锁条件见 `ops/ocr-corrector/README.md`）。

输入（只读）：`ops/ocr-rapid/raw/rapid_pool.jsonl`（Rapid 输出）、`labeling/raw/abc_all_248.json`
（Paddle A/B/C，作跨引擎对照）、`ops/ocr-corrector/out/char_freq.csv`（域内字表）、字表 JSON。

跑法：
    ./venv/bin/python ops/ocr-corrector/eval_corrector.py
    ./venv/bin/python ops/ocr-corrector/eval_corrector.py --mode auto     # 看自动改写面
"""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "webui" / "src"))
sys.path.insert(0, str(HERE))

from glyph_shape import GlyphShape            # noqa: E402
from ocr_corrector import correct, load_map, map_summary  # noqa: E402

OUT = HERE / "out"
RAPID_JSONL = REPO / "ops/ocr-rapid/raw/rapid_pool.jsonl"
PP_ABC = REPO / "labeling/raw/abc_all_248.json"
FREQ_CSV = OUT / "char_freq.csv"
SEED_OCR, SEED_TRUTH = "左軍丞錄", "左軍丞鈢"


def is_han(ch: str) -> bool:
    return not ch.isascii() and ch.isalnum()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(REPO / "webui/data/guxi_variant_map.json"))
    ap.add_argument("--min-freq", type=int, default=3)
    ap.add_argument("--mode", default="suggest", choices=["suggest", "auto"])
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = load_map(a.map)
    rapid = [json.loads(l) for l in RAPID_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    paddle = {c["stem"]: {k: v for k, v in c.items() if k in ("A", "B", "C")}
              for c in json.loads(PP_ABC.read_text(encoding="utf-8"))["crops"]}
    freq = {r["char"]: int(r["count"]) for r in csv.DictReader(FREQ_CSV.open(encoding="utf-8"))
            if r["category"] == "han" and int(r["count"]) >= a.min_freq}

    n_samples = 0
    n_with_hit = n_with_hit_verified = n_with_cand_only = 0
    n_with_outdomain = 0
    n_empty = 0
    applied_total = 0
    per_cfg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    hit_dist: collections.Counter = collections.Counter()
    unmapped_dist: collections.Counter = collections.Counter()
    outdomain_dist: collections.Counter = collections.Counter()
    changed_samples: list[dict] = []

    for r in rapid:
        text = "".join(r["texts"])
        n_samples += 1
        if not text.strip():
            n_empty += 1
        res = correct(text, mode=a.mode, map_data=data)
        hit_froms = {h["from"] for h in res["hits"]}
        if res["stats"]["n_hits"]:
            n_with_hit += 1
            if any(h["verified"] for h in res["hits"]):
                n_with_hit_verified += 1
            elif all(not h["verified"] for h in res["hits"]):
                n_with_cand_only += 1
            for h in res["hits"]:
                hit_dist[(h["from"], h["to"], h["source"], h["verified"])] += 1
        od = [ch for ch in text if is_han(ch) and ch not in freq]
        if od:
            n_with_outdomain += 1
            for ch in od:
                outdomain_dist[ch] += 1
        for u in res["unmapped"]:
            unmapped_dist[u["char"]] += 1
        applied_total += res["stats"]["n_applied"]
        if res["corrected"] != res["raw"]:
            changed_samples.append({"stem": r["stem"], "config": r["config"],
                                    "raw": res["raw"], "corrected": res["corrected"],
                                    "hits": [h for h in res["hits"] if h["applied"]]})
        c = per_cfg[r["config"]]
        c["n"] += 1
        c["empty"] += 1 if not text.strip() else 0
        c["hit"] += 1 if res["stats"]["n_hits"] else 0
        c["outdomain"] += 1 if od else 0
        c["applied"] += res["stats"]["n_applied"]
        assert not (hit_froms and res["stats"]["enabled"] and a.mode == "suggest"
                    and res["corrected"] != res["raw"]), "suggest 模式不得改写"

    # --- 跨引擎混淆对（同图、不同引擎，用 difflib.SequenceMatcher 逐位对齐）---
    xconf: collections.Counter = collections.Counter()
    rapid_by_stem: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for r in rapid:
        rapid_by_stem[r["stem"]].append((f"rapid:{r['config']}", "".join(r["texts"])))
    for stem, outs in rapid_by_stem.items():
        others = [(f"paddle:{k}", v) for k, v in paddle.get(stem, {}).items() if v]
        for (e1, t1) in outs:
            for (e2, t2) in others:
                sm = difflib.SequenceMatcher(a=t1, b=t2, autojunk=False)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag != "replace":
                        continue
                    if (i2 - i1) == 1 and (j2 - j1) == 1:
                        xconf[(e1, t1[i1], e2, t2[j1])] += 1

    # --- 种子标定：唯一有真值的字对在「字形代理」里的位次 ---
    gs = GlyphShape()
    seed_sim = gs.compare(SEED_OCR[-1], SEED_TRUTH[-1])["glyph_sim"]
    ranked = sorted(((gs.compare(SEED_OCR[-1], c)["glyph_sim"], c) for c in freq), reverse=True)
    hypot_rank = 1 + sum(1 for s, _ in ranked if s > seed_sim)
    seed_block = {
        "pair": f"{SEED_OCR[-1]}→{SEED_TRUTH[-1]}",
        "source": "measured_truth（Kevin 样本「左軍丞鈢」：两引擎一致误读为「左軍丞錄」）",
        "glyph_sim": seed_sim,
        "glyph_font": gs.font_name,
        "best_corpus_candidate": {"char": ranked[0][1], "glyph_sim": ranked[0][0]},
        "hypothetical_rank_in_corpus_pool": hypot_rank,
        "corpus_pool_size": len(freq),
        "truth_char_in_corpus_pool": SEED_TRUTH[-1] in freq,
        "truth_char_corpus_count": freq.get(SEED_TRUTH[-1], 0),
        "reading": ("字形代理把**真值字**排在语料池全部候选之前（sim 高于池内最高者）"
                    " ⇒ 排序启发式站得住；但**真值字本身不在语料池里**"
                    " ⇒ 候选生成本质上不可能提出它 —— 瓶颈是**语料覆盖**，不是排序。"
                    if hypot_rank == 1 and SEED_TRUTH[-1] not in freq else "见字段读数"),
    }

    # --- 冒烟：已知真值样本（文本级）---
    smoke = {}
    for mode in ("suggest", "auto"):
        sm = correct(SEED_OCR, mode=mode, map_data=data)
        smoke[mode] = {"raw": sm["raw"], "corrected": sm["corrected"],
                       "n_applied": sm["stats"]["n_applied"],
                       "top1_candidate": (sm["hits"][0]["to"] if sm["hits"] else None),
                       "hits": [{k: h[k] for k in ("pos", "from", "to", "rule_id", "source",
                                                   "confidence", "verified", "applied")}
                                for h in sm["hits"] if h["from"] == SEED_OCR[-1]]}
    smoke["expected"] = SEED_TRUTH
    smoke["auto_reaches_truth"] = smoke["auto"]["corrected"] == SEED_TRUTH

    report = {
        "generated_by": "ops/ocr-corrector/eval_corrector.py",
        "disclaimer": ("★ 无真值 ⇒ 本报告**不含任何准确率 / 准确率提升**读数；"
                       "`labeling/labels.csv` 的 text_correct 为空，量化准确率的解锁条件见 README。"),
        "config": {"map": str(Path(a.map).relative_to(REPO)), "map_summary": map_summary(data),
                   "mode": a.mode, "min_freq": a.min_freq, "freq_pool_size": len(freq)},
        "pool": {
            "n_samples": n_samples,
            "n_relabeled_stems": len(rapid_by_stem),
            "n_outputs_empty": n_empty,
            "note": "496 样本 = 248 枚 × 2 配置（pipeline / rec_only），与 ops/ocr-rapid/raw 一致",
            "per_config": {
                k: {"n": v["n"], "empty": v["empty"], "empty_rate": round(v["empty"] / v["n"], 4),
                    "hit": v["hit"], "outdomain": v["outdomain"], "applied": v["applied"]}
                for k, v in sorted(per_cfg.items())},
        },
        "trigger": {
            "n_samples_with_any_rule_hit": n_with_hit,
            "rate_any_rule_hit": round(n_with_hit / n_samples, 4),
            "n_samples_with_verified_rule_hit": n_with_hit_verified,
            "n_samples_with_candidate_only_hit": n_with_cand_only,
            "n_samples_with_outdomain_char": n_with_outdomain,
            "rate_outdomain_char": round(n_with_outdomain / n_samples, 4),
            "n_applied_total_in_this_mode": applied_total,
            "mode_semantics": ("suggest ⇒ n_applied 恒 0（只给候选）；auto ⇒ 只有 verified=true "
                               "条目会被改写，本池出现的字里没有 verified 源字时为 0"),
        },
        "hit_distribution": [
            {"from": k[0], "to": k[1], "source": k[2], "verified": k[3], "count": v}
            for k, v in hit_dist.most_common()
        ],
        "top_outdomain_chars": [{"char": c, "count": n} for c, n in outdomain_dist.most_common(30)],
        "top_unmapped_chars": [{"char": c, "count": n} for c, n in unmapped_dist.most_common(30)],
        "top_cross_engine_confusions": [
            {"engine_a": k[0], "char_a": k[1], "engine_b": k[2], "char_b": k[3], "count": v}
            for k, v in xconf.most_common(30)
        ],
        "seed_calibration": seed_block,
        "smoke_known_truth_sample": smoke,
        "changed_samples": changed_samples[:20],
    }
    stem = "eval_report" if a.mode == "suggest" else f"eval_report_{a.mode}"
    (out / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    _write_md(report, out / f"{stem}.md")

    t = report["trigger"]
    print(f"[eval] 样本 {n_samples}（空输出 {n_empty}）；命中规则的样本 {n_with_hit}"
          f"（{t['rate_any_rule_hit']:.1%}）；含域外字的样本 {n_with_outdomain}"
          f"（{t['rate_outdomain_char']:.1%}）")
    print(f"[eval] mode={a.mode} 自动改写 {applied_total} 处")
    print(f"[eval] 冒烟 auto: {smoke['auto']['raw']} → {smoke['auto']['corrected']}"
          f"  （期望 {SEED_TRUTH}，达标={smoke['auto_reaches_truth']}）")
    print(f"[eval] 种子标定: {seed_block['pair']} glyph_sim={seed_sim} "
          f"假设位次={hypot_rank}/{len(freq)}；真值字在语料池里？{seed_block['truth_char_in_corpus_pool']}")
    print(f"[out ] {out}/{stem}.json | {stem}.md")
    return 0


def _write_md(rep: dict, path: Path) -> None:
    t = rep["trigger"]
    s = rep["seed_calibration"]
    lines = [
        "# 248 枚池 · 纠错层评估（描述性读数）",
        "",
        f"> {rep['disclaimer']}",
        "",
        f"- 字表：`{rep['config']['map']}` v{rep['config']['map_summary']['version']}"
        f"（条目 {rep['config']['map_summary']['n_entries']}，"
        f"verified {rep['config']['map_summary']['n_verified']}）",
        f"- 模式：`{rep['config']['mode']}`；语料域内字池（`stamps.text` 出现 ≥"
        f"{rep['config']['min_freq']} 次）= {rep['config']['freq_pool_size']} 字",
        "",
        "## 触发率（**不是准确率**）",
        f"- 样本：{rep['pool']['n_samples']}（248 枚 × 2 配置；空输出 {rep['pool']['n_outputs_empty']}）",
        f"- 命中任一规则（候选即可）的样本：{t['n_samples_with_any_rule_hit']}"
        f" = **{t['rate_any_rule_hit']:.1%}**",
        f"- 其中命中 `verified=true` 规则：{t['n_samples_with_verified_rule_hit']}；"
        f"仅命中未验证候选：{t['n_samples_with_candidate_only_hit']}",
        f"- 含「域外字」（该字不在 `stamps.text` 释文用字域）的样本："
        f"{t['n_samples_with_outdomain_char']} = **{t['rate_outdomain_char']:.1%}**",
        f"- 本次自动改写处数：{t['n_applied_total_in_this_mode']}",
        "",
        "## 映射命中分布（Top 15）",
        "| from | to | source | verified | count |",
        "|---|---|---|---|---|",
    ]
    for h in rep["hit_distribution"][:15]:
        lines.append(f"| {h['from']} | {h['to']} | {h['source']} | {h['verified']} | {h['count']} |")
    lines += ["", "## 域外字（OCR 报出、但不在释文用字域）Top 15", "",
              "| char | count |", "|---|---|"]
    for c in rep["top_outdomain_chars"][:15]:
        lines.append(f"| {c['char']} | {c['count']} |")
    lines += ["", "## 跨引擎混淆对（Rapid vs Paddle，逐位对齐；Top 15）", "",
              "| engine A | char | engine B | char | count |", "|---|---|---|---|---|"]
    for c in rep["top_cross_engine_confusions"][:15]:
        lines.append(f"| {c['engine_a']} | {c['char_a']} | {c['engine_b']} | {c['char_b']} |"
                     f" {c['count']} |")
    lines += ["", "## 已知真值样本冒烟（文本级）",
              f"- 输入（实测 OCR 输出）：`{rep['smoke_known_truth_sample']['auto']['raw']}`",
              f"- `auto` 输出：`{rep['smoke_known_truth_sample']['auto']['corrected']}`"
              f"（期望 `{rep['smoke_known_truth_sample']['expected']}`，"
              f"达标 = {rep['smoke_known_truth_sample']['auto_reaches_truth']}）",
              f"- `suggest` 模式未改写（n_applied="
              f"{rep['smoke_known_truth_sample']['suggest']['n_applied']}）",
              "",
              "## 种子标定（唯一有真值的字对在字形代理里的位次）",
              f"- 字对 `{s['pair']}`；glyph_sim = {s['glyph_sim']}（字体 {s['glyph_font']}）",
              f"- 语料池里字形最像 `{s['from'] if 'from' in s else s['pair'][0]}` 的是 "
              f"`{s['best_corpus_candidate']['char']}`（{s['best_corpus_candidate']['glyph_sim']}）",
              f"- 真值字是否在语料池：{s['truth_char_in_corpus_pool']}"
              f"（corpus count = {s['truth_char_corpus_count']}）",
              f"- 解读：{s['reading']}",
              ""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
