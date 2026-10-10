#!/usr/bin/env python3
"""xiai 就绪导入包 —— 机械自检（Kong，2026-10-10；交接件 §7 交付缝扩展；**D-1 三态对照版**）。

**权威契约**：`docs/person-ingest-handoff-v0.1.md` §7.2；键面真源＝
xiai 仓 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`
（**跨仓契约只引用不复制**）。**D-1 已落（xiai 线 2026-10-10 回执）**：键面 **18 → 21**，
新增 `courtesy_names_extraction` / `art_names_extraction` / `alias_names_extraction`（**逐字**）。

**引用对方规则（照登照做）**
  * ① **缺键不拒收**：18 键旧包（缺 extraction 三键）仍可直接提交 ⇒ **必须也判 PASS**；
  * ② **值域不封闭**：extraction 元素**不得**据 `'rule-based'` 硬校验（`'rule-based'` 仅作**本批数据断言**，非对外契约）；
  * ③ **违形态 ⇒ `INVALID_VALUE` ＋零写入**：形态 ＝ `string[]`、与对应值数组**等长**、元素**非空字符串**；
  * ④ **采纳后不落 person 行**（extraction 只留导入行作溯源）。

**三态对照（本单核心）** —— 同一批判据跑三个候选，**区别力**须成立：
  * (a) **21 键形态**（`person_imports.jsonl` 现形态）⇒ **PASS**；
  * (b) **18 键形态**（去掉 3 个 extraction 键的派生物；对方「缺键不拒收」）⇒ **也 PASS（兼容）**；
  * (c) **旧 feicui 形态**（`persons.jsonl`：32 键 / 三桶为对象数组 / 无 sidecar）⇒ **FAIL**（证明判据**非恒真**）。

判据（逐条**可判负**）：
  ① key_face   —— 每行键集 ⊆ xiai 21 键且**无多键**（多余键数须为 0）；**缺失键不作失败**（规则①）。
  ② buckets    —— 三桶（courtesy/art/alias_names）均为 `list[str]` 且元素**非空字符串**（**必写**）。
  ③ extraction —— **主交付内** 3 个 extraction 键（若在）均 `list[str]`、元素**非空字符串**、
                 且与对应值数组**等长**；**缺键 ⇒ 兼容（不判负）**。
  ④ sidecar    —— `source_person_id` ＋ 三 extraction 数组，与对应值数组**等长**、元素非空字符串。
  ⑤ rows/id    —— 行数 == 期望；`source_person_id` **非空且唯一**；**无 BOM**；一行一对象。
  ※ **数据断言（非契约）**：本批 extraction 全量 `'rule-based'` —— **单独列示、不参与判负**
    （对方规则②：值域不封闭）。

用法：
    python3 verify_import_package.py [--package-dir DIR] [--old-form FILE]
                                     [--expected-rows 570] [--out-txt P] [--out-json P]
退出码：(a)(b) 均 PASS **且** (c) 如预期 FAIL ⇒ 0；否则 2。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from datetime import datetime

# ── 权威 21 键（与 server/app/persons.py::XIAI_PERSON_IMPORT_ALLOWED_KEYS 同值；此处独立复写供自检）──
#   键序：3 个 extraction 键**紧随各自的值键之后**（确定性）。
XIAI_ALLOWED_KEYS = [
    "batch_id", "source", "source_person_id", "name_full", "family_name", "given_name",
    "courtesy_names", "courtesy_names_extraction",
    "art_names", "art_names_extraction",
    "alias_names", "alias_names_extraction",
    "birth_year", "death_year",
    "native_place", "native_place_chs", "biography", "biography_chs",
    "nationality", "cbdb_id", "source_id",
]
# 旧 18 键（对方规则①「缺键不拒收」的兼容面；供 18 键派生物构造 / 对照）。
XIAI_LEGACY_18_KEYS = [
    "batch_id", "source", "source_person_id", "name_full", "family_name", "given_name",
    "courtesy_names", "art_names", "alias_names", "birth_year", "death_year",
    "native_place", "native_place_chs", "biography", "biography_chs",
    "nationality", "cbdb_id", "source_id",
]
THREE_BUCKETS = ["courtesy_names", "art_names", "alias_names"]
EXTRACTION_KEYS = ["courtesy_names_extraction", "art_names_extraction", "alias_names_extraction"]
EXTRACTION = "rule-based"  # **本批数据断言用**（**非对外契约判据**）

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
EXPORT_ROOT = os.path.join(REPO_ROOT, "exports")


# ═══════════════════════════════════════════════════════════════════════════ 判据（纯函数，正负同用）
def _read_lines(path: str) -> list[bytes]:
    with open(path, "rb") as fh:
        raw = fh.read()
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
    """① 每行键集 ⊆ 21 键且**无多键**；**缺失键不作失败**（对方规则①「缺键不拒收」）。"""
    allowed = set(XIAI_ALLOWED_KEYS)
    extra: set[str] = set()
    missing: set[str] = set()
    for r in rows:
        ks = set(r.keys())
        extra |= (ks - allowed)
        missing |= (allowed - ks)
    ok = (len(extra) == 0)  # 只有「多键」判负；缺键不判负
    ext_keys_present = all(k in allowed for k in EXTRACTION_KEYS) and not set(EXTRACTION_KEYS) & extra
    return {
        "name": "key_face（键面 ⊆ xiai 21 键，无多键；缺键不拒收）",
        "ok": ok,
        "extra_keys": sorted(extra),
        "missing_keys": sorted(missing),
        "allowed_count": len(allowed),
        "extraction_keys_present": ext_keys_present,
        "detail": (f"多余键 {len(extra)}（须 0，判负）／缺失键 {len(missing)}（**不判负**，对方「缺键不拒收」）；"
                   f"允许键面 {len(allowed)} 键"),
    }


def check_buckets(rows: list[dict]) -> dict:
    """② 三桶均为 list[str] 且元素**非空字符串**。"""
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
        "name": "buckets（三桶均 list[str]，元素非空字符串）",
        "ok": (len(bad) == 0),
        "violations": bad[:20],
        "violations_total": len(bad),
        "detail": f"违规 {len(bad)} 处（须 0）",
    }


def check_extraction_form(rows: list[dict]) -> dict:
    """③ **主交付内** extraction 三键（若在）：`list[str]`、元素**非空字符串**、与对应值数组**等长**。

    **缺键 ⇒ 兼容（不判负）**（对方规则①）。**不得**据元素值 `'rule-based'` 判负（规则② 值域不封闭）。
    """
    bad: list[str] = []
    rows_with_keys = 0
    rows_without_keys = 0
    for i, r in enumerate(rows, start=1):
        present = [k for k in EXTRACTION_KEYS if k in r]
        if not present:
            rows_without_keys += 1
            continue
        rows_with_keys += 1
        for b, ek in zip(THREE_BUCKETS, EXTRACTION_KEYS):
            if ek not in r:
                continue  # 逐键独立：本键缺 ⇒ 兼容
            ext = r.get(ek)
            if not isinstance(ext, list):
                bad.append(f"行 {i} {ek}：非数组（{type(ext).__name__}）")
                continue
            for j, x in enumerate(ext):
                if not isinstance(x, str) or x.strip() == "":
                    bad.append(f"行 {i} {ek}[{j}]：非非空字符串（{x!r}）")
            vals = r.get(b)
            if isinstance(vals, list) and len(ext) != len(vals):
                bad.append(f"行 {i} {ek}：长度 {len(ext)} ≠ 值数组 {b} 长度 {len(vals)}")
    return {
        "name": "extraction_form（主交付内 extraction 三键：list[str] · 元素非空 · 与值数组等长；缺键兼容）",
        "ok": (len(bad) == 0),
        "rows_with_extraction_keys": rows_with_keys,
        "rows_without_extraction_keys": rows_without_keys,
        "violations": bad[:20],
        "violations_total": len(bad),
        "detail": (f"违规 {len(bad)} 处（须 0）；带 extraction 键行 {rows_with_keys}／"
                   f"缺键行 {rows_without_keys}（缺键兼容，不判负）"),
    }


def check_sidecar(rows: list[dict], side_rows: list[dict] | None, side_errors: list[str] | None) -> dict:
    """④ sidecar 三数组与主交付对应值等长、元素非空字符串。"""
    if side_rows is None:
        return {"name": "sidecar（extraction 等长 · 非空字符串）", "ok": False,
                "detail": "sidecar 缺失（无 person_imports_extraction.jsonl）"}
    if side_errors:
        return {"name": "sidecar（extraction 等长 · 非空字符串）", "ok": False,
                "detail": f"sidecar 解析错误 {len(side_errors)} 处", "violations": side_errors[:10]}
    side_by_id = {s.get("source_person_id"): s for s in side_rows}
    bad: list[str] = []
    for i, r in enumerate(rows, start=1):
        pid = r.get("source_person_id")
        s = side_by_id.get(pid)
        if s is None:
            bad.append(f"行 {i} pid={pid}：sidecar 无对应行")
            continue
        for b, sk in zip(THREE_BUCKETS, EXTRACTION_KEYS):
            vals = r.get(b) or []
            ext = s.get(sk)
            if not isinstance(ext, list):
                bad.append(f"pid={pid} {sk}：非数组")
                continue
            if len(ext) != len(vals):
                bad.append(f"pid={pid} {sk}：长度 {len(ext)} ≠ 值数组 {len(vals)}")
            for x in ext:
                if not isinstance(x, str) or x.strip() == "":
                    bad.append(f"pid={pid} {sk}：非非空字符串（{x!r}）")
                    break
    return {
        "name": "sidecar（extraction 等长 · 非空字符串）",
        "ok": (len(bad) == 0),
        "violations": bad[:20],
        "violations_total": len(bad),
        "detail": f"违规 {len(bad)} 处（须 0）",
    }


def check_rows_id_bom(rows: list[dict], main_path: str, expected_rows: int, parse_errors: list[str]) -> dict:
    """⑤ 行数 / 幂等键非空唯一 / 无 BOM / 一行一对象。"""
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


def _rule_based_data_assertion(rows: list[dict]) -> dict:
    """**数据断言（非契约）**：本批 extraction 元素全量 `'rule-based'`。

    **不参与判负**：对方规则②明示 extraction **值域不封闭**，不得据 `'rule-based'` 硬校验。
    """
    vals: list[str] = []
    for r in rows:
        for ek in EXTRACTION_KEYS:
            ext = r.get(ek)
            if isinstance(ext, list):
                vals += [x for x in ext if isinstance(x, str)]
    all_rb = bool(vals) and all(v == EXTRACTION for v in vals)
    distinct = sorted(set(vals))
    return {
        "name": "data_assertion（本批 extraction 全量 'rule-based'；**非对外契约判据**）",
        "applies_to_this_batch": all_rb,
        "elements_total": len(vals),
        "distinct_values": distinct,
        "note": ("**仅供本批数据断言**；对方规则②：extraction 值域不封闭 ⇒ "
                 "**不得**写成对外契约判据（不得据 'rule-based' 硬校验）。"),
        "included_in_verdict": False,
    }


def run_all_checks(main_path: str, side_path: str | None, expected_rows: int) -> dict:
    """在同一批判据下评估一个候选（21 键 / 18 键派生物 / 旧形态对照共用）。"""
    main_rows, main_errors = _parse_jsonl(main_path)
    side_rows = None
    side_errors = None
    if side_path and os.path.isfile(side_path):
        side_rows, side_errors = _parse_jsonl(side_path)

    checks = [
        check_key_face(main_rows),
        check_buckets(main_rows),
        check_extraction_form(main_rows),
        check_sidecar(main_rows, side_rows, side_errors),
        check_rows_id_bom(main_rows, main_path, expected_rows, main_errors),
    ]
    all_ok = all(c["ok"] for c in checks)
    return {
        "main_path": main_path,
        "sidecar_path": side_path,
        "main_bytes": os.path.getsize(main_path),
        "keys_first_row": sorted(main_rows[0].keys()) if main_rows else [],
        "checks": checks,
        "all_pass": all_ok,
        "verdict": "PASS" if all_ok else "FAIL",
        "data_assertion": _rule_based_data_assertion(main_rows),
    }


def _derive_18keys(main_path: str, tmp_dir: str) -> str:
    """从 21 键主交付派生 **18 键形态**（逐行剔除 3 个 extraction 键）⇒ 供兼容 PASS 对照。"""
    rows, _ = _parse_jsonl(main_path)
    out_path = os.path.join(tmp_dir, "person_imports_18keys.jsonl")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps({k: r.get(k) for k in XIAI_LEGACY_18_KEYS}, ensure_ascii=False) + "\n")
    return out_path


# ═══════════════════════════════════════════════════════════════════════════ 入口
def main() -> int:
    ap = argparse.ArgumentParser(description="xiai 就绪导入包机械自检（21 键 PASS / 18 键兼容 PASS / 旧形态 FAIL 三态）")
    ap.add_argument("--package-dir", default=None, help="导入包目录（缺省＝exports 下最新 person_import_*）")
    ap.add_argument("--old-form", default=None,
                    help="旧形态 persons.jsonl（缺省＝exports 下最新 person_<date>_NN/persons.jsonl）")
    ap.add_argument("--expected-rows", type=int, default=570)
    ap.add_argument("--out-txt", default=os.path.join(HERE, "14_import_package_21.txt"))
    ap.add_argument("--out-json", default=os.path.join(HERE, "14_import_package_21.json"))
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

    # ── (a) 21 键形态（现主交付）──
    positive = run_all_checks(main_path, side_path, args.expected_rows)

    # ── (b) 18 键形态（兼容：对方「缺键不拒收」⇒ 也必须 PASS）──
    with tempfile.TemporaryDirectory(prefix="feicui-verify-") as tmp_dir:
        compat_path = _derive_18keys(main_path, tmp_dir)
        compat = run_all_checks(compat_path, side_path, args.expected_rows)

    # ── (c) 旧 feicui 形态（32 键 / 对象数组三桶 / 无 sidecar ⇒ 必须 FAIL）──
    negative = None
    if old_form and os.path.isfile(old_form):
        negative = run_all_checks(old_form, None, args.expected_rows)

    manifest = None
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception as exc:
            manifest = {"_read_error": str(exc)}

    with open(main_path, encoding="utf-8") as fh:
        first_line = fh.readline().rstrip("\n")

    positive_ok = positive["all_pass"]
    compat_ok = compat["all_pass"]
    negative_ok = bool(negative and negative["verdict"] == "FAIL")
    overall = positive_ok and compat_ok and negative_ok

    report = {
        "generated_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "contract": "docs/person-ingest-handoff-v0.1.md §7.2（xiai D-1：键面 18 → 21）",
        "xiai_allowed_keys": XIAI_ALLOWED_KEYS,
        "xiai_allowed_keys_count": len(XIAI_ALLOWED_KEYS),
        "xiai_legacy_18_keys": XIAI_LEGACY_18_KEYS,
        "extraction_keys": EXTRACTION_KEYS,
        "cited_xiai_rules": {
            "rule_1_missing_key_not_rejected": "缺键不拒收：18 键旧包仍可直接提交",
            "rule_2_value_domain_open": "值域不封闭：不得据 'rule-based' 硬校验（仅本批数据断言）",
            "rule_3_form_violation": "违形态 ⇒ INVALID_VALUE ＋零写入（string[] / 等长 / 非空字符串）",
            "rule_4_no_person_row_on_accept": "采纳后不落 person 行",
        },
        "package_dir": pkg_dir,
        "positive_21keys": positive,
        "compat_18keys": compat,
        "negative_control_old_form": negative,
        "verdicts": {
            "positive_21keys_expected": "PASS",
            "positive_21keys": positive["verdict"],
            "compat_18keys_expected": "PASS",
            "compat_18keys": compat["verdict"],
            "negative_old_form_expected": "FAIL",
            "negative_old_form": (negative["verdict"] if negative else None),
        },
        "manifest_checks": (manifest or {}).get("checks"),
        "manifest_sidecar": (manifest or {}).get("sidecar"),
        "first_line_main": first_line,
        "overall": "PASS" if overall else "FAIL",
    }

    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    def _emit_checks(lines: list[str], tag: str, res: dict) -> None:
        for c in res["checks"]:
            lines.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}")
            lines.append(f"         {c['detail']}")
            if c.get("extra_keys"):
                lines.append(f"         多余键：{c['extra_keys']}")
            if c.get("violations"):
                lines.append(f"         违规样例：{c['violations'][:3]}")

    lines: list[str] = []
    lines.append("═══ xiai 就绪导入包 · 机械自检（D-1 三态对照）═══")
    lines.append(f"生成时点：{report['generated_at']}")
    lines.append(f"契约：{report['contract']}")
    lines.append(f"包目录：{pkg_dir}")
    lines.append(f"主交付：{main_path}")
    lines.append(f"sidecar：{side_path}")
    lines.append(f"xiai 允许键（{len(XIAI_ALLOWED_KEYS)}）：{', '.join(XIAI_ALLOWED_KEYS)}")
    lines.append("引用对方规则：①缺键不拒收 ②值域不封闭 ③违形态 INVALID_VALUE＋零写入 ④采纳后不落 person 行")
    lines.append("")
    lines.append("── (a) 21 键形态（主交付现形态）⇒ 期望 PASS ──")
    _emit_checks(lines, "a", positive)
    lines.append(f"  ⇒ 裁决：{positive['verdict']}（all_pass={positive['all_pass']}）")
    lines.append("")
    lines.append("── (b) 18 键形态（派生：逐行剔除 3 个 extraction 键；对方「缺键不拒收」）⇒ 期望 PASS ──")
    _emit_checks(lines, "b", compat)
    lines.append(f"  ⇒ 裁决：{compat['verdict']}（all_pass={compat['all_pass']}）")
    lines.append("")
    if negative is not None:
        old_label = os.path.basename(os.path.dirname(old_form or ""))
        lines.append(f"── (c) 旧 feicui 形态 FAIL 对照（{old_label}/persons.jsonl：32 键 / 三桶为对象数组）⇒ 期望 FAIL ──")
        _emit_checks(lines, "c", negative)
        lines.append(f"  ⇒ 裁决：{negative['verdict']}（期望 FAIL；对照成立={negative_ok}）")
    else:
        lines.append("── (c) 旧 feicui 形态 FAIL 对照：**未找到旧形态 persons.jsonl**（对照缺失）──")
    lines.append("")
    lines.append("── 数据断言（**非对外契约判据**；对方规则②：值域不封闭）──")
    da = positive["data_assertion"]
    lines.append(f"  本批 extraction 全量 'rule-based' ⇒ {da['applies_to_this_batch']}"
                 f"（元素总数 {da['elements_total']}；distinct={da['distinct_values']}）")
    lines.append(f"  说明：{da['note']}")
    lines.append("")
    lines.append("── 主交付首行原文（person_imports.jsonl 第 1 行）──")
    lines.append(first_line)
    lines.append("")
    lines.append(f"══ 总裁决：{report['overall']}（(a)PASS={positive_ok} · (b)PASS={compat_ok} · (c)FAIL={negative_ok}）══")

    with open(args.out_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\n[evidence] {args.out_txt}")
    print(f"[evidence] {args.out_json}")
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
