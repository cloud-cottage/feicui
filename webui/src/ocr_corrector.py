# webui/src/ocr_corrector.py
"""「斐萃」本地版 · 古玺异体/形近字后处理纠错层 —— **纯逻辑，无 GUI / 无引擎依赖**。

分层纪律（与 `webui/src/ocr_rapid.py` / `webui/api.py` 同规）：
  本文件 **不 import streamlit、不 import webview、不 import api/app、不 import 任何 OCR 引擎**
  （连 numpy / cv2 / rapidocr 都不需要）⇒ 可被脚本直接 import 做单测、可在无模型机器上跑。

设计红线（Kevin 定，逐条落成代码约束）：
  1. **默认保守**：`mode='suggest'`（默认）**只给候选、不改写**；`auto` 只对
     `verified=true` 且 `confidence >= auto_min_confidence` 的条目动刀。
  2. **每次替换可追溯**：`hits[]` 每条带 `pos / from / to / rule_id / source / confidence /
     verified / applied / note`；`corrected` 与 `raw` 的差异**只能**由 `hits` 里
     `applied=true` 的那些位置解释（自测里逐字断言）。
  3. **一键关闭**：`enabled=False` ⇒ 直通（`corrected == raw`、`hits == []`），不需要卸字表。
  4. **字表内容不得凭空编造**：`source` 只允许下列取值（`validate_map` 强制），
     `confidence` 必须由 `source` 落在允许区间内；`verified=true` 只许来自 `measured_truth`。
  5. **无真值 ⇒ 不报准确率**：本模块只产出**描述性读数**（触发率 / 命中分布 / 改了哪些字），
     准确率必须等人工真值（见 `ops/ocr-corrector/README.md` §解锁条件）。

字表 schema（`webui/data/guxi_variant_map.json`，见 `validate_map`）：
    {
      "schema": "guxi_variant_map/v1",
      "version": "0.1.0-draft",
      "updated_at": "YYYY-MM-DD",
      "last_reviewed_by": null | "<人名>",
      "review_status": "unreviewed" | "partially_reviewed" | "reviewed",
      "auto_min_confidence": 0.9,
      "entries": [
        {"rule_id": "gx-0001", "from": "錄", "to": "鈢",
         "source": "measured_truth", "confidence": 0.9, "verified": true,
         "note": "…出处…", "evidence": {...},
         "context": {"any_of": [], "none_of": []},   # 可选：邻字约束（空 = 无约束）
         "scope": "seal_text"}                       # 可选，仅作标注
      ],
      "notes": ["…"]
    }

命令行自检（不需要 GUI / 不需要引擎 / 不需要库）：
    ./venv/bin/python webui/src/ocr_corrector.py --selftest
    ./venv/bin/python webui/src/ocr_corrector.py --map webui/data/guxi_variant_map.json --text 左軍丞錄 --mode auto
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "DEFAULT_MAP_PATH",
    "SCHEMA",
    "ALLOWED_SOURCES",
    "SOURCE_CONFIDENCE_RANGE",
    "load_map",
    "validate_map",
    "map_summary",
    "correct",
    "correct_many",
]

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "guxi_variant_map.json"

SCHEMA = "guxi_variant_map/v1"

#: `source` 白名单 —— 每条映射必须标明出处；不得自造来源标签。
#:   measured_truth        : 有真值的实测（人工核定过的正确释文 vs 引擎输出）。**唯一可 verified=true 的来源。**
#:   corpus_stats          : 从 `stamps.text` 统计出的事实（只有「哪些字高频」是事实，
#:                           「A→B」这类映射本身仍是推断 ⇒ 不许 verified=true）。
#:   cross_engine          : 两套引擎同图输出不一致（观测事实，谁对未知）。
#:   font_glyph_shape      : 本地字体栅格化的字形相似度（楷/黑体代理，非篆书）。
#:   inferred              : 人工/工具给出的待审候选，无上述证据。
ALLOWED_SOURCES: dict[str, tuple[float, float]] = {
    "measured_truth": (0.5, 1.0),
    "corpus_stats": (0.0, 0.6),
    "cross_engine": (0.0, 0.6),
    "font_glyph_shape": (0.0, 0.5),
    "inferred": (0.0, 0.4),
}
SOURCE_CONFIDENCE_RANGE = ALLOWED_SOURCES

#: 允许被 `auto` 模式自动替换的最低条目标注置信度（可由字表顶层 `auto_min_confidence` 覆盖）
DEFAULT_AUTO_MIN_CONFIDENCE = 0.9

_MODES = ("suggest", "auto")


# --------------------------------------------------------------------------------------
# 字表加载 / 校验
# --------------------------------------------------------------------------------------
class MapError(ValueError):
    """字表结构性错误（缺字段 / 非法来源 / 非法区间 / from==to / 重复 from 等）。"""


def load_map(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_MAP_PATH
    if not p.exists():
        raise MapError(f"字表不存在: {p}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    errs = validate_map(data)
    if errs:
        raise MapError(f"字表校验失败（{p}）: " + "; ".join(errs[:8]))
    return data


def validate_map(data: dict[str, Any]) -> list[str]:
    """返回错误串列表（空 = 通过）。字表内容纪律的**唯一实现**，勿在别处重写。"""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"]
    if data.get("schema") != SCHEMA:
        errs.append(f"schema 必须是 {SCHEMA!r}，实得 {data.get('schema')!r}")
    for key in ("version", "updated_at", "entries"):
        if key not in data:
            errs.append(f"缺顶层键 {key!r}")
    if "last_reviewed_by" not in data:
        errs.append("缺顶层键 'last_reviewed_by'（审核人未定时写 null，不许省略）")
    if not isinstance(data.get("entries"), list):
        errs.append("'entries' 必须是数组")
        return errs

    seen: dict[str, str] = {}
    for i, e in enumerate(data["entries"]):
        tag = f"entries[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{tag} 必须是对象")
            continue
        for key in ("from", "to", "source", "confidence", "verified", "note"):
            if key not in e:
                errs.append(f"{tag} 缺字段 {key!r}")
        f, t = e.get("from"), e.get("to")
        for name, v in (("from", f), ("to", t)):
            if not isinstance(v, str) or len(v) != 1:
                errs.append(f"{tag}.{name} 必须是**单个字符**（保证 pos 级可追溯），实得 {v!r}")
        if isinstance(f, str) and f == t:
            errs.append(f"{tag} from == to（恒等映射无意义）")
        if isinstance(f, str) and len(f) == 1:
            if f in seen:
                errs.append(f"{tag} from={f!r} 与 {seen[f]} 重复（同一字两条规则 ⇒ 命中歧义）")
            else:
                seen[f] = tag
        src = e.get("source")
        if src not in ALLOWED_SOURCES:
            errs.append(f"{tag}.source={src!r} 不在白名单 {sorted(ALLOWED_SOURCES)}")
        else:
            lo, hi = ALLOWED_SOURCES[src]
            c = e.get("confidence")
            if not isinstance(c, (int, float)) or not (lo <= float(c) <= hi):
                errs.append(
                    f"{tag}.confidence={c!r} 超出 source={src!r} 允许区间 [{lo}, {hi}]")
        if e.get("verified") is True and src != "measured_truth":
            errs.append(f"{tag}: verified=true 只允许 source='measured_truth'（现为 {src!r}）"
                        " —— 无真值不得标已验证")
        if e.get("verified") not in (True, False):
            errs.append(f"{tag}.verified 必须是布尔值（true/false），不许缺省")
        ctx = e.get("context")
        if ctx is not None and not isinstance(ctx, dict):
            errs.append(f"{tag}.context 必须是对象或省略")
    return errs


def map_summary(data: dict[str, Any]) -> dict[str, Any]:
    entries = data.get("entries", [])
    by_source: dict[str, int] = {}
    n_verified = 0
    for e in entries:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        n_verified += 1 if e.get("verified") else 0
    return {
        "schema": data.get("schema"),
        "version": data.get("version"),
        "updated_at": data.get("updated_at"),
        "last_reviewed_by": data.get("last_reviewed_by"),
        "review_status": data.get("review_status"),
        "n_entries": len(entries),
        "n_verified": n_verified,
        "n_unverified": len(entries) - n_verified,
        "by_source": by_source,
    }


def _index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["from"]: e for e in data.get("entries", [])}


def _context_ok(entry: dict[str, Any], raw: str, pos: int) -> tuple[bool, str]:
    """邻字约束（可选）。空 context == 无约束。"""
    ctx = entry.get("context") or {}
    if not ctx:
        return True, ""
    left = raw[:pos]
    right = raw[pos + 1:]
    any_of = ctx.get("any_of") or []
    if any_of and not any(c in raw for c in any_of):
        return False, f"context.any_of {any_of} 未出现在文本中"
    none_of = ctx.get("none_of") or []
    for c in none_of:
        if c in raw:
            return False, f"context.none_of 命中 {c!r}"
    if ctx.get("not_at_first") and pos == 0:
        return False, "context.not_at_first"
    if ctx.get("not_at_last") and pos == len(raw) - 1:
        return False, "context.not_at_last"
    if ctx.get("require_any_of_left") and not any(c in left for c in ctx["require_any_of_left"]):
        return False, "require_any_of_left 未满足"
    if ctx.get("require_any_of_right") and not any(c in right for c in ctx["require_any_of_right"]):
        return False, "require_any_of_right 未满足"
    return True, ""


# --------------------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------------------
def correct(
    text: str,
    *,
    mode: str = "suggest",
    map_data: dict[str, Any] | None = None,
    map_path: str | Path | None = None,
    enabled: bool = True,
    auto_min_confidence: float | None = None,
    max_replacements: int | None = None,
) -> dict[str, Any]:
    """对一段（单枚印面的）释文做纠错 / 给候选。

    `mode='suggest'`（默认）：**不改写**。`corrected == raw`，`hits` 里 `applied=False`，
        供人工在 UI 上逐条采纳。
    `mode='auto'`：只自动替换 `verified=true` 且 `confidence >= auto_min_confidence`
        的条目；其余条目照旧只出现在 `hits`（`applied=False` + `skip_reason`）。
    `enabled=False`：整体关闭（直通），用于「一键关掉纠错」。
    """
    if mode not in _MODES:
        raise ValueError(f"mode 必须是 {_MODES} 之一，实得 {mode!r}")
    if not isinstance(text, str):
        raise TypeError("text 必须是 str（本层不做图片/数组输入）")

    data = map_data if map_data is not None else load_map(map_path)
    errs = validate_map(data)
    if errs:
        raise MapError("字表校验失败: " + "; ".join(errs[:8]))
    thr = (auto_min_confidence if auto_min_confidence is not None
           else float(data.get("auto_min_confidence", DEFAULT_AUTO_MIN_CONFIDENCE)))

    out_chars = list(text)
    hits: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    n_applied = 0
    by_source: dict[str, int] = {}

    if enabled:
        idx = _index(data)
        for pos, ch in enumerate(text):
            entry = idx.get(ch)
            if entry is None:
                unmapped.append({
                    "pos": pos, "char": ch,
                    "reason": "not_in_map",
                    "hint": "该字既非已验证映射的源字、也不在任何候选规则里",
                })
                continue
            ok, why = _context_ok(entry, text, pos)
            applied = False
            skip = why
            if mode == "auto":
                if not entry.get("verified"):
                    skip = skip or "unverified（无真值，不自动改写）"
                elif float(entry["confidence"]) < thr:
                    skip = skip or f"confidence {entry['confidence']} < auto_min_confidence {thr}"
                elif not ok:
                    pass
                elif max_replacements is not None and n_applied >= max_replacements:
                    skip = skip or f"max_replacements={max_replacements} 已达上限"
                else:
                    out_chars[pos] = entry["to"]
                    applied = True
                    n_applied += 1
            else:
                skip = skip or "mode=suggest（只给候选，不自动改写）"
            by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1
            hits.append({
                "pos": pos,
                "from": ch,
                "to": entry["to"],
                "rule_id": entry.get("rule_id"),
                "source": entry["source"],
                "confidence": entry["confidence"],
                "verified": bool(entry.get("verified")),
                "applied": applied,
                "skip_reason": skip,
                "note": entry.get("note", ""),
            })

    corrected = "".join(out_chars) if enabled else text
    stats = {
        "mode": mode,
        "enabled": bool(enabled),
        "map_version": data.get("version"),
        "map_review_status": data.get("review_status"),
        "auto_min_confidence": thr,
        "n_chars": len(text),
        "n_hits": len(hits),
        "n_applied": n_applied,
        "n_unmapped": len(unmapped),
        "n_changed": sum(1 for a, b in zip(text, corrected) if a != b),
        "hit_by_source": by_source,
        "triggered": bool(hits) and enabled,          # 该样本「触发纠错」= 至少一条规则命中
        # ★ 描述性读数的分母是「本段文本」，不是「准确率」：
        "hits_per_char": round(len(hits) / len(text), 4) if text else 0.0,
    }
    _assert_traceable(text, corrected, hits)
    return {"raw": text, "corrected": corrected, "hits": hits,
            "unmapped": unmapped, "stats": stats}


def _assert_traceable(raw: str, corrected: str, hits: Iterable[dict[str, Any]]) -> None:
    """自证：`corrected` 与 `raw` 的每一位差异都必须由 applied 的 hit 解释。"""
    applied = {h["pos"]: h for h in hits if h.get("applied")}
    if len(corrected) != len(raw):
        raise AssertionError("长度变了 —— 本层只做逐字替换，不得增删字符")
    for i, (a, b) in enumerate(zip(raw, corrected)):
        if a == b:
            if i in applied:
                raise AssertionError(f"pos={i} 标记 applied 但字符未变 —— 追溯断裂")
            continue
        h = applied.get(i)
        if h is None:
            raise AssertionError(f"pos={i} 字符被改（{a}→{b}）但无 applied 记录 —— 不可追溯")
        if (h["from"], h["to"]) != (a, b):
            raise AssertionError(f"pos={i} hit({h['from']}→{h['to']}) 与实际改写({a}→{b}) 不一致")


def correct_many(texts: Iterable[str], **kw: Any) -> list[dict[str, Any]]:
    data = kw.pop("map_data", None) or load_map(kw.pop("map_path", None))
    return [correct(t, map_data=data, **kw) for t in texts]


# --------------------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------------------
def _selftest(map_path: Path) -> int:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ok   {name}")
        else:
            fail += 1
            print(f"  FAIL {name} {detail}")

    print(f"[selftest] 字表 = {map_path}")
    data = load_map(map_path)
    s = map_summary(data)
    print(f"[selftest] 字表摘要 = {json.dumps(s, ensure_ascii=False)}")
    check("字表 schema 合法", validate_map(data) == [], str(validate_map(data)[:3]))
    check("存在已验证（有真值）条目", s["n_verified"] >= 1, f"n_verified={s['n_verified']}")
    check("last_reviewed_by 字段在场", "last_reviewed_by" in data)
    check("候选条目默认 verified=false", all(
        e["verified"] is False for e in data["entries"] if e["source"] != "measured_truth"))

    # --- 1) suggest 模式：只给候选、不改写 ---
    r = correct("左軍丞錄", mode="suggest", map_data=data)
    check("suggest: raw 未动", r["corrected"] == r["raw"] == "左軍丞錄")
    check("suggest: 有 hit", r["stats"]["n_hits"] >= 1, str(r["stats"]))
    check("suggest: n_applied == 0", r["stats"]["n_applied"] == 0)
    seed = [h for h in r["hits"] if h["from"] == "錄"]
    check("suggest: 錄→鈢 候选在场", bool(seed) and seed[0]["to"] == "鈢", str(seed))
    check("suggest: 候选带 rule_id/source/confidence",
          bool(seed) and all(k in seed[0] for k in
                             ("pos", "from", "to", "rule_id", "source", "confidence", "note")))

    # --- 2) auto 模式：已验证条目生效、未验证条目不动 ---
    a = correct("左軍丞錄", mode="auto", map_data=data)
    check("auto: 左軍丞錄 → 左軍丞鈢", a["corrected"] == "左軍丞鈢", a["corrected"])
    check("auto: 恰 1 处改写", a["stats"]["n_applied"] == 1, str(a["stats"]["n_applied"]))
    applied = [h for h in a["hits"] if h["applied"]]
    check("auto: 改写可追溯（pos/from/to/rule_id/source）",
          len(applied) == 1 and applied[0]["pos"] == 3
          and applied[0]["from"] == "錄" and applied[0]["to"] == "鈢"
          and applied[0]["rule_id"] and applied[0]["source"] == "measured_truth")
    check("auto: 未验证候选未被自动应用",
          all(not h["applied"] for h in a["hits"] if not h["verified"]))

    # --- 3) 关闭开关：直通 ---
    off = correct("左軍丞錄", mode="auto", map_data=data, enabled=False)
    check("enabled=False: 直通（不改写）", off["corrected"] == off["raw"] and off["hits"] == [])
    check("enabled=False: stats 如实标注", off["stats"]["enabled"] is False
          and off["stats"]["n_applied"] == 0)

    # --- 4) 无命中 / 空串 / 多枚重复 ---
    z = correct("田用海厦", mode="auto", map_data=data)
    check("无命中文案不变", z["corrected"] == "田用海厦" and z["stats"]["triggered"] is False)
    check("无命中时 unmapped 逐字登记", len(z["unmapped"]) == 4, str(len(z["unmapped"])))
    e = correct("", mode="auto", map_data=data)
    check("空串安全", e["corrected"] == "" and e["stats"]["n_chars"] == 0)
    m = correct("錄錄錄", mode="auto", map_data=data, max_replacements=2)
    check("同一字多次出现：逐个登记且 max_replacements 生效",
          m["stats"]["n_applied"] == 2 and
          [h["pos"] for h in m["hits"] if h["applied"]] == [0, 1], str(m["hits"]))
    check("max_replacements 未及的位置给出 skip_reason",
          any("max_replacements" in (h.get("skip_reason") or "") for h in m["hits"]))

    # --- 5) 字表内容纪律：非法来源 / 越界置信 / 假 verified 必须被判负 ---
    bad = [
        ({"source": "linguistic_guess"}, "非法 source 必须判负"),
        ({"source": "corpus_stats", "confidence": 0.95}, "corpus_stats 不得高置信"),
        ({"source": "corpus_stats", "confidence": 0.3, "verified": True}, "非实测来源不得 verified=true"),
    ]
    base = dict(data)
    for patch, why in bad:
        e0 = dict(data["entries"][0])
        e0.update(patch)
        e0.setdefault("rule_id", "bad")
        cand = dict(base, entries=[e0])
        check(why, validate_map(cand) != [], str(validate_map(cand)[:2]))
    dup = dict(base, entries=[dict(data["entries"][0], rule_id="a"),
                              dict(data["entries"][0], rule_id="b")])
    check("同 from 重复规则判负", any("重复" in x for x in validate_map(dup)))

    # --- 6) mode 非法值 ---
    try:
        correct("甲", mode="blind-write", map_data=data)
        check("非法 mode 抛错", False)
    except ValueError:
        check("非法 mode 抛错", True)

    print(f"[selftest] {ok} passed, {fail} failed")
    return 0 if fail == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="古玺异体/形近字后处理纠错层（纯逻辑）")
    ap.add_argument("--map", default=str(DEFAULT_MAP_PATH))
    ap.add_argument("--text", action="append", default=[], help="待纠错文本（可多次）")
    ap.add_argument("--mode", default="suggest", choices=list(_MODES))
    ap.add_argument("--off", action="store_true", help="一键关闭纠错（直通）")
    ap.add_argument("--summary", action="store_true", help="只打字表摘要")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest(Path(a.map))
    data = load_map(a.map)
    if a.summary or not a.text:
        print(json.dumps(map_summary(data), ensure_ascii=False, indent=2))
        return 0
    for t in a.text:
        r = correct(t, mode=a.mode, map_data=data, enabled=not a.off)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
