#!/usr/bin/env python3
"""关联面抽样核验（证据②）：证明采集**读了详情页**（列表页没有关联图）。

拿 DB 里的落库关联数 vs 远端 `graph/person` 的实时读数，逐条比对：
  * 趙之謙 personGrbsm=907404573 ⇒ 印谱 23 / 印章 65
  * 吳昌碩 personGrbsm=907271790 ⇒ 印谱 0  / 印章 10
  * 宗汝剛 personGrbsm=907566313 ⇒ 印谱 0  / 印章 0
  * 鄒夢禪 personGrbsm=907450151 ⇒ 印谱 1  / 印章 0
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/kevin/bistro/feicui")
DB = REPO / "var" / "person_ingest.db"
BASE = "https://yin.fudan.edu.cn/service_yinpu"

sys.path.insert(0, str(REPO / "server"))
from app import persons as P  # noqa: E402

ANCHORS = [("907404573", "趙之謙"), ("907271790", "吳昌碩"), ("907566313", "宗汝剛"), ("907450151", "鄒夢禪")]


def db_counts(grbsm: str) -> dict:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT kind, COUNT(*) c FROM person_relations WHERE source_person_id=? GROUP BY kind", (grbsm,)
        ).fetchall()
        return {r["kind"]: r["c"] for r in rows}
    finally:
        conn.close()


def main() -> int:
    ok = True
    report = []
    for grbsm, name in ANCHORS:
        src = P.fetch_graph(BASE, grbsm)
        src_counts = {c.get("name"): int(c.get("count") or 0) for c in src.get("children", [])}
        db = db_counts(grbsm)
        row = {
            "personGrbsm": grbsm, "name": name,
            "source_graph": src_counts,
            "db_relations": db,
            "match": (db.get("印谱", 0) == src_counts.get("印谱", 0)
                      and db.get("印章", 0) == src_counts.get("印章", 0)),
        }
        report.append(row)
        if not row["match"]:
            ok = False
    print(json.dumps({"ok": ok, "anchors": report}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
