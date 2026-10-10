#!/usr/bin/env python3
"""xiai 就绪导入包 —— 机械自检（Kong，2026-10-10；交接件 §7 交付缝扩展）。

**权威契约**：`docs/person-ingest-handoff-v0.1.md` §7.2（主交付严格 xiai 现行 18 键）。
xiai 侧允许键 = `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`
（恰 18 键，**跨仓契约只引用不复制**）：多一个键 ⇒ xiai 判 `INVALID_FIELD`＋零写入。

判据（四项，逐条**可判负**）：
  ① key_face   —— 每行键集 ⊆ xiai 18 键且**无多键**（多余键数须为 0）；
  ② buckets    —— 三桶（courtesy/art/alias_names）均为 `list[str]` 且元素**非空字符串**；
  ③ sidecar    —— `source_person_id` ＋ 三 extraction 数组，**与对应值数组等长**、元素恒 `'rule-based'`；
  ④ rows/id    —— 行数 == 期望（570）；`source_person_id` **非空且唯一**；**无 BOM**；一行一对象。

**对照（⑤ 要求）**：拿**旧形态**（feicui 批次包 `persons.jsonl`：32 键 / 三桶为对象数组）跑**同一批判据**
⇒ 必须 **FAIL**（证明判据有区分力，不是恒真）。

用法：
    python3 verify_import_package.py [--package-dir DIR] [--old-form FILE]
                                     [--expected-rows 570] [--out-txt P] [--out-json P]
退出码：正样本全过 **且** 旧形态如预期 FAIL ⇒ 0；否则 2。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime

# ── 权威 18 键（与 server/app/persons.py::XIAI_PERSON_IMPORT_ALLOWED_KEYS 同值；此处独立复写供自检）──
XIAI_ALLOWED_KEYS = [
    "batch_id", "source", "source_person_id", "name_full", "family_name", "given_name",
    "courtesy_names", "art_names", "alias_names", "birth_year", "death_year",
    "native_place", "native_place_chs", "biography", "biography_chs",
    "nationality", "cbdb_id", "source_id",
]
THREE_BUCKETS = ["courtesy_names", "art_names", "alias_names"]
SIDECAR_EXTRACTION_KEYS = ["courtesy_names_extraction", "art_names_extraction", "alias_names_extraction"]
EXTRACTION = "rule-based"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
EXPORT_ROOT = os.path.join(REPO_ROOT, "exports")


# ═══════════════════════════════════════════════════════════════════════════ 判据（纯函数，正负同用）
def _read_lines(path: str) -> list[bytes]:
    with open(path, "rb") as fh:
        raw = fh.read()
    # 一行一对象：按 \n 切，去掉末尾空行
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def _parse_jsonl(path: str) -> tuple[list, list[str]]:
    """返回 (rows, errors)。每行须为 JSON **对象**；坏行进 errors（**不静默跳过**）。"""
    rows: list = []
    errors: list[str] = []
    for i, line in enumerate(_read_lines(path), start=1):
        s = line.strip()
        if not s:
            errors.append(f"第 {i} 行：空行")
            continue
        try:
            obj = json.loads(s.decode("utf-8"))
        except Exception as exc:
            errors.append(f"第 {i} 行：非 JSON（{exc}）")
            continue
        if not isinstance(obj, dict):
            errors.append(f"第 {i} 行：非对象（{type(obj).__name__}）")
            continue
        rows.append(obj)
    return rows, errors


def has_bom(path: str) -> bool:
    with open(path, "rb") as fh:
        return fh.read(3) == b"\xef\xbb\xbf"


def check_key_face(rows: list[dict]) -> dict:
    """① 每行键集 ⊆ 18 键且无多键。"""
    allowed = set(XIAI_ALLOWED_KEYS)
    extra: set[str] = set()
    missing: set[str] = set()
    for r in rows:
        ks = set(r.keys())
        extra |= (ks - allowed)
        missing |= (allowed - ks)
    ok = (len(extra) == 0)
    return {
        "name": "key_face（键面 ⊆ xiai 18 键，无多键）",
        "ok": ok,
        "extra_keys": sorted(extra),
        "missing_keys": sorted(missing),
        "allowed_count": len(allowed),
        "detail": (f"多余键 {len(extra)}（须 0）／缺失键 {len(missing)}；"
                   f"允许键面 {len(allowed)} 键"),
    }


def check_buckets(rows: list[dict]) -> dict:
    """② 三桶均为 list[str] 且元素非空字符串。"""
    bad: list[str] = []
    for i, r in enumerate(rows, start=1):
        for b in THREE_BUCKETS:
            v = r.get(b)
            if not isinstance(v, list):
                bad.append(f"行 {i} {b}：非数组（{type(v).__name__}）")
                continue
            for j, x in enumerate(v):
                if not isinstance(x, str) or x.strip() == "":
                    bad.append(f"行 {i} {b}[{j}]：非非空字符串（{x!r}）")
    return {
        "name": "buckets（三桶均 list[str]，元素非空）",
        "ok": (len(bad) == 0),
        "violations": bad[:20],
        "violations_total": len(bad),
        "detail": f"违规 {len(bad)} 处（须 0）",
    }


def check_sidecar(rows: list[dict], side_rows: list[dict] | None, side_errors: list[str] | None) -> dict:
    """③ sidecar 三数组与主交付对应值等长、元素恒 'rule-based'。"""
    if side_rows is None:
        return {"name": "sidecar（extraction 等长 · rule-based）", "ok": False,
                "detail": "sidecar 缺失（无 person_imports_extraction.jsonl）"}
    if side_errors:
        return {"name": "sidecar（extraction 等长 · rule-based）", "ok": False,
                "detail": f"sidecar 解析错误 {len(side_errors)} 处", "violations": side_errors[:10]}
    side_by_id = {s.get("source_person_id"): s for s in side_rows}
    bad: list[str] = []
    for i, r in enumerate(rows, start=1):
        pid = r.get("source_person_id")
        s = side_by_id.get(pid)
        if s is None:
            bad.append(f"行 {i} pid={pid}：sidecar 无对应行")
            continue
        for b, sk in zip(THREE_BUCKETS, SIDECAR_EXTRACTION_KEYS):
            vals = r.get(b) or []
            ext = s.get(sk)
            if not isinstance(ext, list):
                bad.append(f"pid={pid} {sk}：非数组")
                continue
            if len(ext) != len(vals):
                bad.append(f"pid={pid} {sk}：长度 {len(ext)} ≠ 值数组 {len(vals)}")
            for x in ext:
                if x != EXTRACTION:
                    bad.append(f"pid={pid} {sk}：元素 {x!r} ≠ {EXTRACTION!r}")
                    break
    return {
        "name": "sidecar（extraction 等长 · rule-based）",
        "ok": (len(bad) == 0),
        "violations": bad[:20],
        "violations_total": len(bad),
        "detail": f"违规 {len(bad)} 处（须 0）",
    }


def check_rows_id_bom(rows: list[dict], main_path: str, expected_rows: int, parse_errors: list[str]) -> dict:
    """④ 行数 / 幂等键非空唯一 / 无 BOM / 一行一对象。"""
    ids = [r.get("source_person_id") for r in rows]
    non_null = [x for x in ids if x not in (None, "")]
    unique = len(set(non_null))
    bom = has_bom(main_path)
    ok = (len(rows) == expected_rows and len(non_null) == len(rows) == unique
          and not bom and len(parse_errors) == 0)
    return {
        "name": "rows/id/bom（行数=期望 · 幂等键非空唯一 · 无 BOM · 一行一对象）",
        "ok": ok,
        "rows": len(rows),
        "expected_rows": expected_rows,
        "id_non_null": len(non_null),
        "id_unique": unique,
        "has_bom": bom,
        "parse_errors": parse_errors[:10],
        "parse_errors_total": len(parse_errors),
        "detail": (f"行数 {len(rows)}（期望 {expected_rows}）／幂等键非空 {len(non_null)} 唯一 {unique}／"
                   f"BOM={'有' if bom else '无'}／坏行 {len(parse_errors)}"),
    }


def run_all_checks(main_path: str, side_path: str | None, expected_rows: int) -> dict:
    """在同一批判据下评估一个候选（正样本 / 旧形态对照共用）。"""
    main_rows, main_errors = _parse_jsonl(main_path)
    side_rows = None
    side_errors = None
    if side_path and os.path.isfile(side_path):
        side_rows, side_errors = _parse_jsonl(side_path)

    checks = [
        check_key_face(main_rows),
        check_buckets(main_rows),
        check_sidecar(main_rows, side_rows, side_errors),
        check_rows_id_bom(main_rows, main_path, expected_rows, main_errors),
    ]
    all_ok = all(c["ok"] for c in checks)
    return {
        "main_path": main_path,
        "sidecar_path": side_path,
        "main_bytes": os.path.getsize(main_path),
        "checks": checks,
        "all_pass": all_ok,
        "verdict": "PASS" if all_ok else "FAIL",
    }


# ═══════════════════════════════════════════════════════════════════════════ 入口
def _newest(pattern: str) -> str | None:
    hits = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return hits[0] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser(description="xiai 就绪导入包机械自检（正样本 + 旧形态 FAIL 对照）")
    ap.add_argument("--package-dir", default=None, help="导入包目录（缺省＝exports 下最新 person_import_*）")
    ap.add_argument("--old-form", default=None,
                    help="旧形态 persons.jsonl（缺省＝exports 下最新 person_<date>_NN/persons.jsonl）")
    ap.add_argument("--expected-rows", type=int, default=570)
    ap.add_argument("--out-txt", default=os.path.join(HERE, "13_import_package.txt"))
    ap.add_argument("--out-json", default=os.path.join(HERE, "13_import_package.json"))
    args = ap.parse_args()

    pkg_dir = args.package_dir
    if not pkg_dir:
        cands = [d for d in glob.glob(os.path.join(EXPORT_ROOT, "person_import_*")) if os.path.isdir(d)]
        pkg_dir = sorted(cands, key=os.path.getmtime, reverse=True)[0] if cands else None
    if not pkg_dir or not os.path.isdir(pkg_dir):
        print(f"ERROR: 找不到导入包目录：{pkg_dir}", file=sys.stderr)
        return 2
    main_path = os.path.join(pkg_dir, "person_imports.jsonl")
    side_path = os.path.join(pkg_dir, "person_imports_extraction.jsonl")
    manifest_path = os.path.join(pkg_dir, "manifest.json")

    old_form = args.old_form
    if not old_form:
        old_cands = [p for p in glob.glob(os.path.join(EXPORT_ROOT, "person_2*", "persons.jsonl"))
                     if os.path.basename(os.path.dirname(p)).startswith("person_")
                     and not os.path.basename(os.path.dirname(p)).startswith("person_import_")]
        old_form = sorted(old_cands, key=os.path.getmtime, reverse=True)[0] if old_cands else None

    positive = run_all_checks(main_path, side_path, args.expected_rows)

    negative = None
    if old_form and os.path.isfile(old_form):
        # 旧形态：三桶为对象数组、32 键、无 sidecar ⇒ 同判据必须 FAIL
        negative = run_all_checks(old_form, None, args.expected_rows)

    manifest = None
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception as exc:
            manifest = {"_read_error": str(exc)}

    # ── 首行原文（主交付） ──
    with open(main_path, encoding="utf-8") as fh:
        first_line = fh.readline().rstrip("\n")

    negative_ok = bool(negative and negative["verdict"] == "FAIL")
    overall = positive["all_pass"] and negative_ok

    report = {
        "generated_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "contract": "docs/person-ingest-handoff-v0.1.md §7.2（xiai 现行 18 键）",
        "xiai_allowed_keys": XIAI_ALLOWED_KEYS,
        "xiai_allowed_keys_count": len(XIAI_ALLOWED_KEYS),
        "package_dir": pkg_dir,
        "positive": positive,
        "negative_control": negative,
        "negative_control_expected": "FAIL",
        "negative_control_ok": negative_ok,
        "manifest_checks": (manifest or {}).get("checks"),
        "first_line_main": first_line,
        "overall": "PASS" if overall else "FAIL",
    }

    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    lines: list[str] = []
    lines.append("═══ xiai 就绪导入包 · 机械自检 ═══")
    lines.append(f"生成时点：{report['generated_at']}")
    lines.append(f"契约：{report['contract']}")
    lines.append(f"包目录：{pkg_dir}")
    lines.append(f"主交付：{main_path}")
    lines.append(f"sidecar：{side_path}")
    lines.append(f"xiai 允许键（{len(XIAI_ALLOWED_KEYS)}）：{', '.join(XIAI_ALLOWED_KEYS)}")
    lines.append("")
    lines.append("── ①~④ 判据（正样本，逐条）──")
    for c in positive["checks"]:
        lines.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}")
        lines.append(f"         {c['detail']}")
    lines.append(f"  ⇒ 正样本裁决：{positive['verdict']}（all_pass={positive['all_pass']}）")
    lines.append("")
    lines.append("── 行数 / 幂等键 / BOM 读数 ──")
    c4 = positive["checks"][3]
    lines.append(f"  行数 = {c4['rows']}（期望 {c4['expected_rows']}）")
    lines.append(f"  幂等键 source_person_id：非空 {c4['id_non_null']} / 唯一 {c4['id_unique']}")
    lines.append(f"  无 BOM = {not c4['has_bom']}")
    lines.append(f"  坏行 = {c4['parse_errors_total']}")
    lines.append("")
    lines.append("── 主交付首行原文（person_imports.jsonl 第 1 行）──")
    lines.append(first_line)
    lines.append("")
    if negative is not None:
        old_label = os.path.basename(os.path.dirname(old_form)) if old_form else "旧形态"
        lines.append(f"── ⑤ 旧形态 FAIL 对照（{old_label}/persons.jsonl）──")
        for c in negative["checks"]:
            lines.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}")
            lines.append(f"         {c['detail']}")
            if c.get("extra_keys"):
                lines.append(f"         多余键：{c['extra_keys']}")
            if c.get("violations"):
                lines.append(f"         违规样例：{c['violations'][:3]}")
        lines.append(f"  ⇒ 旧形态裁决：{negative['verdict']}（期望 FAIL；对照成立={negative_ok}）")
    else:
        lines.append("── ⑤ 旧形态 FAIL 对照：**未找到旧形态 persons.jsonl**（对照缺失）──")
    lines.append("")
    lines.append(f"══ 总裁决：{report['overall']} ══")

    with open(args.out_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\n[evidence] {args.out_txt}")
    print(f"[evidence] {args.out_json}")
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
