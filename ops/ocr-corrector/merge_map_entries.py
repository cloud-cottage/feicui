#!/usr/bin/env python
"""ops/ocr-corrector · 把候选条目**合并**进正式字表（`local-dist/data/guxi_variant_map.json`）。

幂等：按 `rule_id` 去重、按 `from` 去重（`validate_map` 禁止同 `from` 两条规则）；
已存在的 `from` **不覆盖**（人工审核过的条目永远不会被脚本改写）。

★ 只写 `local-dist/data/guxi_variant_map.json` 这一个文件；不碰数据库、不碰 `output/`。

跑法：
    ./venv/bin/python ops/ocr-corrector/merge_map_entries.py --apply
    ./venv/bin/python ops/ocr-corrector/merge_map_entries.py            # dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "local-dist" / "src"))

from ocr_corrector import load_map, map_summary, validate_map  # noqa: E402

MAP = REPO / "local-dist/data/guxi_variant_map.json"
CAND = HERE / "out/candidates_map_entries.json"
MERGE_NOTE = ("由 ops/ocr-corrector/merge_map_entries.py 合入的候选（source∈{cross_engine,"
              "font_glyph_shape}，verified=false，默认不生效）：待人工逐条审核后，若与真值一致，"
              "应改为 source='measured_truth' + verified=true + 更新 confidence/evidence；"
              "若不一致则删除该条（**不要**把它标成 verified=false 后就地保留成高置信）。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(MAP))
    ap.add_argument("--entries", default=str(CAND))
    ap.add_argument("--apply", action="store_true", help="真写；缺省 dry-run")
    a = ap.parse_args()

    map_path = Path(a.map)
    data = load_map(map_path)
    cand = json.loads(Path(a.entries).read_text(encoding="utf-8"))
    have = {e["from"] for e in data["entries"]}
    have_ids = {e.get("rule_id") for e in data["entries"]}
    # ★ 人工裁定删除的条目（字表顶层 `rejected[]`）：**不得**被脚本重新合入
    rejected = {r.get("from") for r in data.get("rejected", [])}
    rejected_ids = {r.get("rule_id") for r in data.get("rejected", [])}

    added, skipped_from, skipped_id, skipped_rejected = [], [], [], []
    for e in cand["entries"]:
        if e.get("rule_id") in rejected_ids or e["from"] in rejected:
            skipped_rejected.append(e["from"])
            continue
        if e.get("rule_id") in have_ids:
            skipped_id.append(e["rule_id"])
            continue
        if e["from"] in have:
            skipped_from.append(e["from"])
            continue
        added.append(e)
        have.add(e["from"])
        have_ids.add(e.get("rule_id"))

    print(f"[merge] 现表 {len(data['entries'])} 条 → 新增 {len(added)} 条"
          f"（跳过 same-from {len(skipped_from)} / same-rule_id {len(skipped_id)}）")
    if skipped_rejected:
        print(f"[merge] 因人工裁定删除（`rejected[]`）而跳过的源字：{''.join(skipped_rejected)}"
              " —— 裁定判错，**不得**重新合入；如需复活请先改字表 `rejected[]` 与 `notes`")
    if skipped_from:
        print(f"[merge] 因同 from 已存在而跳过的源字：{''.join(skipped_from)}")
    if not added:
        print("[merge] 无新增，字表未变（幂等）")
    if not a.apply:
        print("[merge] dry-run：未写文件（加 --apply 才写）")
        return 0

    new_entries = data["entries"] + added
    out = dict(data)
    out["entries"] = new_entries
    # ★ 不得回退人工审核状态：本脚本只「合入候选」，不重新审核。
    #   （曾经把 version/review_status 定死成 0.2.0-draft/unreviewed，会把人工裁定留痕抹掉。）
    out["version"] = data.get("version") or "0.2.0-draft"
    out["updated_at"] = data.get("updated_at") or "2026-10-16"
    out["review_status"] = data.get("review_status") or "unreviewed"
    notes = list(data.get("notes", []))
    if MERGE_NOTE not in notes:
        notes.append(MERGE_NOTE)
    notes.append(f"候选条目来源：`ops/ocr-corrector/out/candidates_map_entries.json`"
                 f"（params={cand['params']}，字形代理={cand['glyph_meta']['font_name']}）；"
                 f"本次新增 {len(added)} 条（rule_id gx-cand-XXXX）。")
    out["notes"] = notes

    errs = validate_map(out)
    if errs:
        print("[merge] ABORT：合并后字表校验失败 → " + "; ".join(errs[:5]))
        return 1
    map_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[merge] 已写 {map_path}")
    print("[merge] 新摘要 = " + json.dumps(map_summary(out), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
