#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""历史 `stamps` 行的去重标记（方案 A）—— **幂等、只写加法列**（Kong / 去重方案 A 落地 2026-10-11）。

**它做什么**：把 `server/app/dedup.py`（去重规则的生产单一实现）对**历史 8708 行**逐页跑一遍，
把「标记为重复」的行写进**新增加法列**：

  * `dup_kind`   TEXT    —— `near_duplicate`（R1 近重复）| `group_frame`（R2 组框）；保留行＝ `NULL`；
  * `dup_of_id`  INTEGER —— 指向**保留行**的 `stamps.id`（R1 ⇒ 簇代表；R2 ⇒ 桥接的最大子框）；
  * `dup_algo`   TEXT    —— 算法版本 ＋ 阈值签名（`dedup.A.algo_signature()`；幂等重算的记账键）。

**它不做什么（红线）**：**不删任何行**、**不改任何既有列值**、**不动任何文件**、**不建 job**、**不重出图**。
新 job 的去重发生在**检测器侧**（`server/worker/feicui_worker.py` 调 `dedup.dedup_page`），
**不写**这三列（新 job 的每一行都已是去重后留下的，`dup_kind` 恒 `NULL`）。

**幂等**：判据＝「目标状态（`dup_kind`/`dup_of_id`/`dup_algo`）与库内当前值逐行相等」。
`--apply` 只更新**不一致**的行；第二次跑 ⇒ `updates=0`（可反复跑，见 README 的复跑命令）。

**闸**：解析到的 DB 若是仓库内正式库 `yinpu.db` ⇒ 默认**拒绝写入**（须 `FEICUI_ALLOW_PROD_MIGRATE=1`
显式授权，与 `app.migrations` 同闸）；自测用副本。

用法（cwd ＝ `feicui/server/`）：
    ./.venv/bin/python -m app.dedup_apply                                  # dry-run（默认，不写）
    ./.venv/bin/python -m app.dedup_apply --json /tmp/dup_summary.json     # dry-run ＋ 落汇总
    FEICUI_ALLOW_PROD_MIGRATE=1 ./.venv/bin/python -m app.dedup_apply --apply   # 写正式库
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# ---- 去重核心（生产单一实现）按文件路径加载（不 import 包，避免 feicui/app.py 遮蔽）--------------
def _load_core():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("feicui_dedup_core_apply", here / "dedup.py")
    assert spec is not None and spec.loader is not None, "无法加载 server/app/dedup.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load_core()

DUP_COLUMNS = ("dup_kind", "dup_of_id", "dup_algo")


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def plan(db_path: Path, *, t1: float | None = None, t2: float | None = None,
         tol: float | None = None, r2_min_children: int | None = None) -> dict:
    """只读：算出「目标状态」并与库内当前值比对 ⇒ 规划（不写）。"""
    t1 = core.T1_DEFAULT if t1 is None else t1
    t2 = core.T2_DEFAULT if t2 is None else t2
    tol = core.TOL_PX if tol is None else tol
    r2mc = core.R2_MIN_CHILDREN if r2_min_children is None else r2_min_children
    sig = core.algo_signature(t1, t2, tol, r2mc)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cols = _columns(conn, "stamps")
        missing = [c for c in DUP_COLUMNS if c not in cols]
        if missing:
            raise SystemExit(
                f"✗ stamps 缺去重列 {missing} —— 请先跑迁移："
                f"FEICUI_ALLOW_PROD_MIGRATE=1 ./.venv/bin/python -m app.migrations"
            )
        rows = [dict(r) for r in conn.execute(
            "SELECT id, pdf_name, page, idx, x1, y1, x2, y2, dup_kind, dup_of_id, dup_algo "
            "FROM stamps ORDER BY pdf_name, page, idx"
        )]
    finally:
        conn.close()

    pages: dict = defaultdict(list)
    for r in rows:
        pages[(r["pdf_name"], r["page"])].append(r)

    desired: dict[int, tuple] = {}
    by_kind: dict = defaultdict(int)
    by_book: dict = defaultdict(lambda: {"total": 0, "marked": 0, "near_duplicate": 0, "group_frame": 0})
    for pk, bs in pages.items():
        rects = [{"id": r["id"], "idx": r["idx"], "x1": r["x1"], "y1": r["y1"],
                  "x2": r["x2"], "y2": r["y2"]} for r in bs]
        res = core.dedup_page(rects, t1=t1, t2=t2, tol=tol, r2_min_children=r2mc,
                              tie_break=core.TIE_BREAK_DEFAULT, order=core.ORDER_DEFAULT)
        for m in res.marks:
            desired[m.box_id] = (m.kind, m.keeper_id, sig)
            by_kind[m.kind] += 1

    for r in rows:
        b = by_book[r["pdf_name"]]
        b["total"] += 1
        if r["id"] in desired:
            b["marked"] += 1
            b[desired[r["id"]][0]] += 1

    updates: list[tuple] = []
    for r in rows:
        cur = (r["dup_kind"], r["dup_of_id"], r["dup_algo"])
        want = desired.get(r["id"], (None, None, None))
        if cur != want:
            updates.append((want[0], want[1], want[2], r["id"]))

    return {
        "db_path": str(db_path),
        "algo": sig,
        "params": {"t1": t1, "t2": t2, "tol": tol, "r2_min_children": r2mc,
                   "tie_break": core.TIE_BREAK_DEFAULT, "order": core.ORDER_DEFAULT},
        "rows_total": len(rows),
        "rows_marked": len(desired),
        "rows_marked_pct": round(100.0 * len(desired) / max(len(rows), 1), 2),
        "marked_near_duplicate": by_kind.get(core.KIND_NEAR_DUPLICATE, 0),
        "marked_group_frame": by_kind.get(core.KIND_GROUP_FRAME, 0),
        "pages_total": len(pages),
        "pages_affected": len({pk for pk, bs in pages.items()
                               if any(r["id"] in desired for r in bs)}),
        "updates_needed": len(updates),
        "by_book": {k: v for k, v in sorted(by_book.items(), key=lambda kv: -kv[1]["marked"])},
        "_updates": updates,
    }


def apply_plan(db_path: Path, plan_: dict) -> int:
    """把规划写入库（单事务，只写 3 个加法列）。返回实际更新行数。"""
    updates = plan_["_updates"]
    if not updates:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE stamps SET dup_kind = ?, dup_of_id = ?, dup_algo = ? WHERE id = ?",
            updates,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(updates)


def _resolve_db(db_arg: str | None) -> Path:
    if db_arg:
        return Path(db_arg).expanduser().resolve()
    # 复用 API 层解析（含正式库默认路径）；只在能从 server/ 起时可用
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.config import get_settings  # type: ignore
        return Path(get_settings().db_path)
    except Exception:
        return Path("/Users/kevin/bistro/data/yinpu.db")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="历史 stamps 行去重标记（方案 A，加法列，幂等）")
    ap.add_argument("--db", default=None, help="DB 路径（缺省＝API 层解析的正式库）")
    ap.add_argument("--apply", action="store_true", help="真写库（缺省 dry-run，不写）")
    ap.add_argument("--t1", type=float, default=None, help="R1 阈值（缺省＝生产常量 0.5）")
    ap.add_argument("--t2", type=float, default=None, help="R2 面积比上限（缺省＝0.6）")
    ap.add_argument("--tol", type=float, default=None, help="包含判定容差 px（缺省＝8）")
    ap.add_argument("--r2-min-children", type=int, default=None, help="R2 子框数下限（缺省＝2）")
    ap.add_argument("--json", dest="json_out", default=None, help="汇总落 JSON 路径")
    args = ap.parse_args(argv)

    db_path = _resolve_db(args.db)
    import os
    prod = db_path == Path("/Users/kevin/bistro/data/yinpu.db").resolve()
    if args.apply and prod and os.environ.get("FEICUI_ALLOW_PROD_MIGRATE") != "1":
        print("✗ 拒绝：目标是仓库内正式库 yinpu.db（唯一真源）。")
        print("  若确需写入，请显式设 FEICUI_ALLOW_PROD_MIGRATE=1（须 Kevin/Zang 明示）；自测用副本。")
        return 3

    p = plan(db_path, t1=args.t1, t2=args.t2, tol=args.tol, r2_min_children=args.r2_min_children)
    applied = apply_plan(db_path, p) if args.apply else 0

    summary = {k: v for k, v in p.items() if k != "_updates"}
    summary["apply"] = bool(args.apply)
    summary["applied_updates"] = applied
    summary["mode"] = "apply" if args.apply else "dry-run"

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(f"db            = {summary['db_path']}")
    print(f"mode          = {summary['mode']}{'  applied=' + str(applied) if args.apply else ''}")
    print(f"algo          = {summary['algo']}")
    print(f"rows          = {summary['rows_total']}  marked = {summary['rows_marked']} "
          f"({summary['rows_marked_pct']}%: near_duplicate={summary['marked_near_duplicate']} "
          f"group_frame={summary['marked_group_frame']})")
    print(f"pages         = {summary['pages_affected']}/{summary['pages_total']}")
    print(f"updates_needed= {summary['updates_needed']}")
    print(f"by_book       = " + ", ".join(
        f"{k[:18]}:{v['marked']}/{v['total']}" for k, v in summary["by_book"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
