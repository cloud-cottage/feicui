"""关联面（三表联立）—— Kong（2026-10-10）。

**权威口径**：Kevin 2026-10-10 裁定「印人关联面另开」后的**独立需求**。
口径真源 ＝ `docs/relation-ingest-draft-v0.1.md`（Zang）；规范锚点 ＝ `docs/feicui.spec.md` **§3.18**（v1.20）。

**本质：纯本库联立、零联网。** 三条采集线的关系数据已全在库内，本模块把它们缝成**一致的关联面**：

  * `var/person_ingest.db::person_relations`（印人 → 印谱 1349 / 印章 301）
  * `var/item_ingest.db::item_creators`（印谱 → 印人；`book_graph` 1281 / `person_graph` 159）
  * `var/seal_ingest.db::seal_links`（印章 → 印谱 3679 / 印人 5285）

**统一关系边（edge）· 一行一条**（键面照登 §3.18.2／拆解件 §3）：

  `predicate` / `subject_type`·`subject_id` / `object_type`·`object_id` / `role`·`role_note` /
  `evidence`（数组） / `source_ref` / `image_ref` / `name`·`name_chs` / `seq` / `batch_id`
  ＋（R-c 标记）`ghost` / `person_resolved`

**口径（默认值，一句话可改；待 xiai 裁定）**：
  * **R-a 保留两向**：`person_to_item` 与 `item_to_person` 都出（role / creator_type 语义不同）。
  * **R-b 去重**：同一 `(subject,object,predicate)` 只一行；`evidence` 数组保留双源
    （`["person_graph","book_graph"]`）。
  * **R-c 幽灵 / 未收录**：**保留并标记**（`ghost:true` / `person_resolved:false`）。
  * **R-d 印章角色**：`seal_links` 的 印主 / 篆者 / 边款篆者整面**保留**（`role` ＝ `link_kind` 面）；
    `person_relations(印章)` 的 301 条**另标** `evidence:["person_graph"]`。**二者不同 predicate、都留**。
  * **R-e 幂等键**：`(predicate, subject_id, object_id)`（三元组唯一 ⇒ 生效去重键即它）。
  * **R-f 包形态**：`exports/relation_import_<batch_id>/`＝`relations.jsonl` ＋ `manifest.json`
    （`key_face_status:"pending_xiai"`）＋ `report.json`。

**红线**：① 零联网（不打复旦站点任何端点）；② **只读三库＋三线既有就绪包**（不改一个字节）；
③ 不写 xiai 任何文件、不调云函数。**本模块全程只 SELECT。**

**批次（`batch_id`）口径（本实现默认）**：本线**不新建任何 DB**（红线「只读三库」）——批次登记
＝**本线就绪包目录本身**（`exports/relation_import_<batch_id>/`）。缺省批次 ＝ 既有 `relation_import_*`
中最新者；若无，则以 `<relation_<yyyymmdd>_01>`（同日默认名）创建。**显式给出的 `batch_id` 若在
既有批次中不存在 ⇒ `BATCH_NOT_FOUND`（404）**；CLI 为**批次创建入口**（可创建新批次）。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

RELATION_SCHEMA_VERSION = "feicui.relation_ingest/1"
MANIFEST_SCHEMA_VERSION = 1

# ── 统一关系边字段（**键序即 JSONL 键序**；照登 §3.18.2，后两键为 R-c 标记、additive）──
EDGE_FIELDS: list[str] = [
    "predicate",
    "subject_type", "subject_id",
    "object_type", "object_id",
    "role", "role_note",
    "evidence",
    "source_ref",
    "image_ref",
    "name", "name_chs",
    "seq",
    "batch_id",
    # —— R-c 幽灵 / 未收录标记（additive；保留并标记，不剔除）——
    "ghost",
    "person_resolved",
]

# 五值枚举（**不得自造第六值**）
PREDICATES: tuple[str, ...] = (
    "person_to_item",
    "item_to_person",
    "person_to_seal",
    "seal_to_item",
    "seal_to_person",
)

# evidence 规范序（稳定序；示例 `["person_graph","book_graph"]` 照登 §3.18.2）
SOURCE_ORDER: tuple[str, ...] = ("person_graph", "book_graph", "seal_row")

# 印章 person 面的角色标签（`link_kind` → 人类可读）
SEAL_LINK_ROLE_LABEL: dict[str, str] = {
    "person_yz": "印主",
    "person_zzkz": "篆者",
    "person_bkzkz": "边款篆者",
}
SEAL_LINK_FACE_ORDER: tuple[str, ...] = ("person_yz", "person_zzkz", "person_bkzkz")

# 字段字典（供 manifest；键面未裁前**不裁剪**）
FIELD_DICT: dict[str, str] = {
    "predicate": "关系谓词（五值枚举）：person_to_item / item_to_person / person_to_seal / seal_to_item / seal_to_person",
    "subject_type": "主语类型 ∈ {person,item,seal}",
    "subject_id": "主语主键（印人 personGrbsm / 印谱 seqid / 印章 seqid）",
    "object_type": "宾语类型 ∈ {person,item,seal}",
    "object_id": "宾语主键（同上口径）",
    "role": "角色：印人侧给 creator_type（如「辑、刻」）；印谱侧给 creator_type；印章侧给 link_kind 面；合并多值时以 `|` 连接",
    "role_note": "角色备注（如印章 person 面的人类可读标签「印主/篆者/边款篆者」）",
    "evidence": "来源面数组（person_graph / book_graph / seal_row）；双源共报同一事实时保留双源",
    "source_ref": "源侧引用（可为 null；如印谱 as_book_id、印章侧 book 面 as_book_id）",
    "image_ref": "影像引用（可为 null；印人侧印章关联的 image_key，形如 19_3250_1）",
    "name": "名称（繁体为正；印谱名 / 印章印文释文 / 印人名）",
    "name_chs": "简体副字段（沿繁简存法；不做任何转换改写）",
    "seq": "序号（稳定排序）",
    "batch_id": "批次号（系统写；如 relation_20261010_01）",
    "ghost": "R-c 标记：该边宾语/主语无法在对应本库实体表解析（如 as_book_id='test'）⇒ true",
    "person_resolved": "R-c 标记：该边涉印人一侧是否在 persons.source_person_id 内；未收录 ⇒ false；无印人端点 ⇒ null",
}

# 三表来源（照登 §3.18.1）
SOURCE_TABLES: list[dict[str, Any]] = [
    {"db": "var/person_ingest.db", "table": "person_relations", "rows": 1650,
     "semantics": "印人 →（印谱 1349 / 印章 301）",
     "key_cols": ["source_person_id", "kind", "ref_id", "name", "desc", "creator_type",
                  "image_key", "as_book_id", "has_image", "seq"]},
    {"db": "var/item_ingest.db", "table": "item_creators", "rows": 1440,
     "semantics": "印谱 → 印人",
     "key_cols": ["source_item_id", "creator_type", "creator_role", "creator_relator",
                  "creator_name", "person_grbsm", "source_face", "seq"]},
    {"db": "var/seal_ingest.db", "table": "seal_links", "rows": 8964,
     "semantics": "印章 →（印谱 3679 / 印人 5285）",
     "key_cols": ["source_seal_id", "link_kind", "ref_id", "ref_name", "ref_name_chs",
                  "creator_type", "bridge_item_id", "source_face", "seq"]},
]

R_A_NOTE = ("R-a 保留两向（person_to_item ＋ item_to_person）：两向的 role / creator_type 语义不同"
            "（印人侧给「辑、刻」，印谱侧给 creator_role / creator_relator）")
R_B_NOTE = ("R-b 同一 (subject,object,predicate) 只一行，evidence 数组保留双源（去重后交集行标 "
            "[\"person_graph\",\"book_graph\"]）")
R_C_NOTE = "R-c 幽灵 / 未收录一律保留并标记（ghost:true / person_resolved:false）"
R_D_NOTE = ("R-d seal_links 的印主/篆者/边款篆者整面与 person_relations(印章) 的 301 条**都留**"
            "（后者另标 evidence:[\"person_graph\"]；二者 predicate 不同、粒度不同）")
R_E_NOTE = "R-e 幂等键 ＝ (predicate, subject_id, object_id)（三元组唯一；未裁前不加合成 hash）"


class ImportPackageError(RuntimeError):
    """就绪包生成失败（`code` ∈ BATCH_NOT_FOUND / NO_BATCH / …）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ═══════════════════════════════════════════════════════════════════════════ 工具
def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _ro_connect(db_path: Path | str) -> sqlite3.Connection:
    """**只读**连接（uri mode=ro ＋ query_only）：源库零写入。

    WAL 库在 `-shm` 受限时 `mode=ro` 可能报「unable to open database file」⇒ 退回 `immutable=1`。
    """
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("SELECT 1").fetchone()
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _ev_sort(ev: set[str] | list[str]) -> list[str]:
    """evidence 稳定序（规范序优先，未知值殿后按字典序）。"""
    def key(x: str):
        return (SOURCE_ORDER.index(x) if x in SOURCE_ORDER else len(SOURCE_ORDER), x)
    return sorted(set(ev), key=key)


def _join_roles(vals: list[str]) -> str | None:
    distinct = sorted({v for v in vals if v not in (None, "")})
    if not distinct:
        return None
    return "|".join(distinct)


# ═══════════════════════════════════════════════════════════════════════════ 读三库（只读）
def _read_indexes(person_db: Path, item_db: Path, seal_db: Path) -> dict[str, Any]:
    pc = _ro_connect(person_db)
    ic = _ro_connect(item_db)
    sc = _ro_connect(seal_db)
    try:
        items_seq = {r[0] for r in ic.execute("SELECT source_item_id FROM items")}
        items_book = {r[0] for r in ic.execute("SELECT as_book_id FROM items")}
        persons = {r[0] for r in pc.execute("SELECT source_person_id FROM persons")}
        seal_ids = {r[0] for r in sc.execute("SELECT source_seal_id FROM seals")}
        seal_img_refs = {r[0] for r in sc.execute("SELECT source_ref FROM seal_images")}
    finally:
        pc.close(); ic.close(); sc.close()
    return {"items_seq": items_seq, "items_book": items_book, "persons": persons,
            "seal_ids": seal_ids, "seal_img_refs": seal_img_refs}


def _read_raw(person_db: Path, item_db: Path, seal_db: Path) -> dict[str, list[dict]]:
    pc = _ro_connect(person_db)
    ic = _ro_connect(item_db)
    sc = _ro_connect(seal_db)
    try:
        pr_item = [dict(r) for r in pc.execute(
            "SELECT source_person_id, kind, ref_id, name, desc, creator_type, image_key, "
            "as_book_id, has_image, seq FROM person_relations WHERE kind='印谱' "
            "ORDER BY source_person_id, ref_id, seq")]
        pr_seal = [dict(r) for r in pc.execute(
            "SELECT source_person_id, kind, ref_id, name, desc, creator_type, image_key, "
            "as_book_id, has_image, seq FROM person_relations WHERE kind='印章' "
            "ORDER BY source_person_id, ref_id, seq")]
        ic_all = [dict(r) for r in ic.execute(
            "SELECT source_item_id, creator_type, creator_role, creator_relator, creator_name, "
            "person_grbsm, source_face, seq FROM item_creators "
            "ORDER BY source_item_id, person_grbsm, source_face, seq")]
        sl_all = [dict(r) for r in sc.execute(
            "SELECT source_seal_id, link_kind, ref_id, ref_name, ref_name_chs, creator_type, "
            "bridge_item_id, source_face, seq FROM seal_links "
            "ORDER BY source_seal_id, link_kind, ref_id, seq")]
    finally:
        pc.close(); ic.close(); sc.close()
    return {"pr_item": pr_item, "pr_seal": pr_seal, "ic_all": ic_all, "sl_all": sl_all}


# ═══════════════════════════════════════════════════════════════════════════ 建边
def _person_resolved_of(person_ids: list[str], persons: set[str]) -> bool | None:
    ids = [p for p in person_ids if p]
    if not ids:
        return None
    return all(p in persons for p in ids)


def build_edges(person_db: Path, item_db: Path, seal_db: Path, batch_id: str) -> dict[str, Any]:
    """三库只读 → 归一为统一关系边 → 按 R-b 去重 → 返回 `{edges, stats}`。"""
    idx = _read_indexes(person_db, item_db, seal_db)
    raw = _read_raw(person_db, item_db, seal_db)

    items_seq, items_book, persons = idx["items_seq"], idx["items_book"], idx["persons"]
    seal_ids = idx["seal_ids"]

    pr_item = raw["pr_item"]; pr_seal = raw["pr_seal"]
    ic_all = raw["ic_all"]; sl_all = raw["sl_all"]

    # 双源交集（去重面）：A ＝ item_creators(book_graph) 的对 vs B ＝ person_relations(印谱) 的对
    # 统一为 **(person, item)** 定向；同时预备 (item, person) 定向供出边时查证
    A = {(r["person_grbsm"], r["source_item_id"]) for r in ic_all if r["source_face"] == "book_graph"}   # (person,item)
    B = {(r["source_person_id"], r["ref_id"]) for r in pr_item}                                          # (person,item)
    ic_book_pi = A
    ic_book_ip = {(it, p) for (p, it) in A}          # (item,person)
    pr_pairs_ip = {(it, p) for (p, it) in B}         # (item,person)

    edges: list[dict] = []

    # ── predicate 1：person_to_item（印人 → 印谱）─────────────────────────────
    for r in pr_item:
        pid, item_id = r["source_person_id"], r["ref_id"]
        ev = {"person_graph"}
        if (pid, item_id) in ic_book_pi:
            ev.add("book_graph")
        ghost = item_id not in items_seq
        edges.append({
            "predicate": "person_to_item",
            "subject_type": "person", "subject_id": pid,
            "object_type": "item", "object_id": item_id,
            "role": r["creator_type"], "role_note": None,
            "evidence": _ev_sort(ev),
            "source_ref": r["as_book_id"], "image_ref": None,
            "name": r["name"], "name_chs": None,
            "seq": r["seq"] if r["seq"] is not None else 0,
            "batch_id": batch_id,
            "ghost": bool(ghost),
            "person_resolved": pid in persons,
        })

    # ── predicate 2：item_to_person（印谱 → 印人）─────────────────────────────
    for r in ic_all:
        item_id, pid = r["source_item_id"], r["person_grbsm"]
        ev = {r["source_face"]}
        if (item_id, pid) in pr_pairs_ip:
            ev.add("person_graph")
        if (item_id, pid) in ic_book_ip:
            ev.add("book_graph")
        ghost = item_id not in items_seq
        edges.append({
            "predicate": "item_to_person",
            "subject_type": "item", "subject_id": item_id,
            "object_type": "person", "object_id": pid,
            "role": r["creator_type"],
            "role_note": r["creator_role"] or r["creator_relator"],
            "evidence": _ev_sort(ev),
            "source_ref": None, "image_ref": None,
            "name": r["creator_name"], "name_chs": None,
            "seq": r["seq"] if r["seq"] is not None else 0,
            "batch_id": batch_id,
            "ghost": bool(ghost),
            "person_resolved": pid in persons,
        })

    # ── predicate 3：person_to_seal（印人 → 印章；来源恒 graph/person）────────
    for r in pr_seal:
        pid, seal_id = r["source_person_id"], r["ref_id"]
        edges.append({
            "predicate": "person_to_seal",
            "subject_type": "person", "subject_id": pid,
            "object_type": "seal", "object_id": seal_id,
            "role": r["creator_type"], "role_note": None,
            "evidence": ["person_graph"],
            "source_ref": None, "image_ref": r["image_key"],
            "name": r["desc"], "name_chs": None,
            "seq": r["seq"] if r["seq"] is not None else 0,
            "batch_id": batch_id,
            "ghost": bool(seal_id not in seal_ids),
            "person_resolved": pid in persons,
        })

    # ── predicate 4 / 5：seal_to_item / seal_to_person（来源恒 seal_row）──────
    for r in sl_all:
        sid, kind, ref_id = r["source_seal_id"], r["link_kind"], r["ref_id"]
        if kind == "book":
            item_id = r["bridge_item_id"]
            edges.append({
                "predicate": "seal_to_item",
                "subject_type": "seal", "subject_id": sid,
                "object_type": "item", "object_id": item_id,
                "role": None, "role_note": kind,
                "evidence": ["seal_row"],
                "source_ref": ref_id, "image_ref": None,
                "name": r["ref_name"], "name_chs": r["ref_name_chs"],
                "seq": r["seq"] if r["seq"] is not None else 0,
                "batch_id": batch_id,
                "ghost": bool(item_id is not None and item_id not in items_seq),
                "person_resolved": None,
            })
        elif kind.startswith("person_"):
            edges.append({
                "predicate": "seal_to_person",
                "subject_type": "seal", "subject_id": sid,
                "object_type": "person", "object_id": ref_id,
                "role": kind, "role_note": SEAL_LINK_ROLE_LABEL.get(kind),
                "evidence": ["seal_row"],
                "source_ref": None, "image_ref": None,
                "name": r["ref_name"], "name_chs": r["ref_name_chs"],
                "seq": r["seq"] if r["seq"] is not None else 0,
                "batch_id": batch_id,
                "ghost": False,
                "person_resolved": ref_id in persons,
            })

    raw_counts: dict[str, int] = {}
    for e in edges:
        raw_counts[e["predicate"]] = raw_counts.get(e["predicate"], 0) + 1

    # ── R-b 去重：键 ＝ (predicate, subject_type, subject_id, object_type, object_id) ──
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    for e in edges:
        key = (e["predicate"], e["subject_type"], e["subject_id"], e["object_type"], e["object_id"])
        if key not in merged:
            merged[key] = e
            merged[key]["evidence"] = set(e["evidence"])
            merged[key]["_roles"] = {e["role"]} if e["role"] is not None else set()
            merged[key]["_role_notes"] = {e["role_note"]} if e["role_note"] is not None else set()
            order.append(key)
        else:
            m = merged[key]
            m["evidence"] |= set(e["evidence"])
            if e["role"] is not None:
                m["_roles"].add(e["role"])
            if e["role_note"] is not None:
                m["_role_notes"].add(e["role_note"])
            # R-c / 标记取并（任一为真即真；None 视作未标记）
            if e.get("ghost"):
                m["ghost"] = True
            if e.get("person_resolved") is False:
                m["person_resolved"] = False

    out: list[dict] = []
    for key in order:
        m = merged[key]
        m["evidence"] = _ev_sort(m["evidence"])
        m["role"] = _join_roles(sorted(m["_roles"]))
        m["role_note"] = _join_roles(sorted(m["_role_notes"]))
        m.pop("_roles", None); m.pop("_role_notes", None)
        out.append(m)

    # 稳定排序（predicate 枚举序 → subject_id → object_id → role → seq）
    out.sort(key=lambda e: (
        PREDICATES.index(e["predicate"]),
        e["subject_type"], e["subject_id"] or "",
        e["object_type"], e["object_id"] or "",
        e["role"] or "", e["seq"] or 0,
    ))

    dedup_counts: dict[str, int] = {}
    for e in out:
        dedup_counts[e["predicate"]] = dedup_counts.get(e["predicate"], 0) + 1

    stats = _build_stats(idx, raw, out, A, B, raw_counts, dedup_counts)
    return {"edges": out, "stats": stats}


def _build_stats(idx, raw, edges, A, B, raw_counts, dedup_counts) -> dict[str, Any]:
    pr_item, pr_seal = raw["pr_item"], raw["pr_seal"]
    ic_all, sl_all = raw["ic_all"], raw["sl_all"]
    items_seq, persons = idx["items_seq"], idx["persons"]
    seal_ids, seal_img_refs = idx["seal_ids"], idx["seal_img_refs"]

    # ── §2 九行对账（逐行重算；给命中/未命中数 + 未命中清单）──
    pr_bk = sorted({r["as_book_id"] for r in pr_item if r["as_book_id"] not in (None, "")})
    pr_ref = sorted({r["ref_id"] for r in pr_item if r["ref_id"] not in (None, "")})
    miss_bk = [x for x in pr_bk if x not in idx["items_book"]]
    miss_ref = [x for x in pr_ref if x not in items_seq]
    pr_s_ref = sorted({r["ref_id"] for r in pr_seal if r["ref_id"] not in (None, "")})
    pr_s_img = sorted({r["image_key"] for r in pr_seal if r["image_key"] not in (None, "")})
    miss_s_ref = [x for x in pr_s_ref if x not in seal_ids]
    miss_s_img = [x for x in pr_s_img if x not in seal_img_refs]
    sl_book = [(r["source_seal_id"], r["ref_id"], r["bridge_item_id"]) for r in sl_all if r["link_kind"] == "book"]
    sl_book_ref = sorted({x[1] for x in sl_book if x[1] not in (None, "")})
    sl_book_bridge = sorted({x[2] for x in sl_book if x[2] not in (None, "")})
    miss_book_ref = [x for x in sl_book_ref if x not in idx["items_book"]]
    miss_book_bridge = [x for x in sl_book_bridge if x not in items_seq]
    ic_p = sorted({r["person_grbsm"] for r in ic_all if r["person_grbsm"] not in (None, "")})
    miss_ic_p = [x for x in ic_p if x not in persons]
    sl_p_rows = [r for r in sl_all if r["link_kind"].startswith("person_")]
    sl_p_refs = sorted({r["ref_id"] for r in sl_p_rows if r["ref_id"] not in (None, "")})
    miss_sl_p = [x for x in sl_p_refs if x not in persons]

    inter = A & B
    dedup_arith = {
        "sets": {
            "A": {"label": "item_creators(source_face='book_graph') 对 (item,person)",
                  "rows": sum(1 for r in ic_all if r["source_face"] == "book_graph"), "set": len(A)},
            "B": {"label": "person_relations(kind='印谱') 对 (person,item)",
                  "rows": sum(1 for r in pr_item), "set": len(B)},
        },
        "intersection": len(inter),
        "only_item": len(A - B),
        "only_person": len(B - A),
        "union": len(A | B),
        "formula": f"|A∪B| = |A|+|B|−|A∩B| = {len(A)}+{len(B)}−{len(inter)} = {len(A) + len(B) - len(inter)}",
    }

    recon: list[dict] = [
        {"#": 1, "join": "person_relations(印谱).as_book_id → items.as_book_id",
         "unique": len(pr_bk), "hit": len(pr_bk) - len(miss_bk), "miss": len(miss_bk),
         "miss_values": miss_bk, "verdict": "源侧测试占位行（未知书）⇒ 幽灵，登记不判负" if miss_bk else "全命中"},
        {"#": 2, "join": "person_relations(印谱).ref_id → items.source_item_id",
         "unique": len(pr_ref), "hit": len(pr_ref) - len(miss_ref), "miss": len(miss_ref),
         "miss_values": miss_ref, "verdict": "与 #1 同行（ref_id=103 ⇒ as_book_id=test）"},
        {"#": 3, "join": "person_relations(印章).ref_id → seals.source_seal_id",
         "unique": len(pr_s_ref), "hit": len(pr_s_ref) - len(miss_s_ref), "miss": len(miss_s_ref),
         "miss_values": miss_s_ref, "verdict": "印人侧印章关联天然接入印章表"},
        {"#": 4, "join": "person_relations(印章).image_key → seal_images.source_ref",
         "unique": len(pr_s_img), "hit": len(pr_s_img) - len(miss_s_img), "miss": len(miss_s_img),
         "miss_values": miss_s_img, "verdict": "可精确接到影像面"},
        {"#": 5, "join": "seal_links(book).ref_id → items.as_book_id",
         "unique": len(sl_book_ref), "hit": len(sl_book_ref) - len(miss_book_ref), "miss": len(miss_book_ref),
         "miss_values": miss_book_ref, "verdict": "印章只涉 19 种印谱"},
        {"#": 6, "join": "seal_links(book).bridge_item_id → items.source_item_id",
         "unique": len(sl_book_bridge), "hit": len(sl_book_bridge) - len(miss_book_bridge), "miss": len(miss_book_bridge),
         "miss_values": miss_book_bridge, "verdict": "桥接键可用"},
        {"#": 7, "join": "item_creators.person_grbsm → persons.source_person_id",
         "unique": len(ic_p), "hit": len(ic_p) - len(miss_ic_p), "miss": len(miss_ic_p),
         "miss_values": miss_ic_p, "verdict": "无未命中"},
        {"#": 8, "join": "seal_links(person_*).ref_id → persons.source_person_id",
         "unique": len(sl_p_refs), "hit": len(sl_p_refs) - len(miss_sl_p), "miss": len(miss_sl_p),
         "miss_values": miss_sl_p, "verdict": "源侧引用未收录 ⇒ 不判负，必须计数入包（R-c：person_resolved:false）"},
        {"#": 9, "join": "去重面：item_creators(book_graph) vs person_relations(印谱)",
         "unique": None, "hit": None, "miss": None,
         "arithmetic": dedup_arith, "verdict": "两源共报同一事实 ⇒ 合并；provenance 保留双源"},
    ]

    # ── 幽灵 / 未收录清单 ──
    ghosts = [e for e in edges if e.get("ghost")]
    ghost_rows = [{"predicate": e["predicate"], "subject_id": e["subject_id"],
                   "object_id": e["object_id"], "evidence": e["evidence"],
                   "name": e["name"], "source_ref": e["source_ref"]}
                  for e in ghosts]
    unresolved = sorted({e["object_id"] for e in edges
                         if e["person_resolved"] is False and e["object_type"] == "person"}
                        | {e["subject_id"] for e in edges
                           if e["person_resolved"] is False and e["subject_type"] == "person"})

    # ref_id 未命中 person 库：按面分列（§3.17.8 a-v1.19 ①）
    miss_by_face: dict[str, Any] = {}
    for face in SEAL_LINK_FACE_ORDER:
        refs = sorted({r["ref_id"] for r in sl_p_rows if r["link_kind"] == face and r["ref_id"] not in (None, "")})
        rows_n = sum(1 for r in sl_p_rows if r["link_kind"] == face)
        miss = [x for x in refs if x not in persons]
        miss_by_face[face] = {"label": SEAL_LINK_ROLE_LABEL[face], "rows": rows_n,
                              "unique_refs": len(refs), "miss_unique": len(miss), "miss_ids": miss}
    miss_total = sorted({x for v in miss_by_face.values() for x in v["miss_ids"]})

    # ── evidence 双源计数 ──
    ev_counts: dict[str, int] = {}
    for e in edges:
        k = "+".join(e["evidence"])
        ev_counts[k] = ev_counts.get(k, 0) + 1
    double = [e for e in edges if len(e["evidence"]) > 1]

    # ── 涉及实体规模 ──
    pr_persons = {r["source_person_id"] for r in pr_item} | {r["source_person_id"] for r in pr_seal}
    ic_persons = {r["person_grbsm"] for r in ic_all}
    sl_persons = {r["ref_id"] for r in sl_p_rows}
    multi_seal = sum(1 for r in _group_count(pr_seal, "ref_id").values() if r > 1)

    coverage = {
        "persons_total": len(persons),
        "persons_in_person_relations": len(pr_persons),
        "persons_in_item_creators": len(ic_persons),
        "persons_in_seal_links": len(sl_persons & persons),
        "persons_in_seal_links_raw": len(sl_persons),
        "seal_person_unique_edges": len(pr_s_ref),
        "person_relations_seal_creator_type": sorted({r["creator_type"] for r in pr_seal}),
        "seal_refs_with_multi_person": multi_seal,
    }

    return {
        "schema_version": RELATION_SCHEMA_VERSION,
        "predicate_counts": {p: dedup_counts.get(p, 0) for p in PREDICATES},
        "raw_counts": {p: raw_counts.get(p, 0) for p in PREDICATES},
        "raw_total": sum(raw_counts.values()),
        "dedup_total": sum(dedup_counts.values()),
        "dedup": {
            "before": sum(raw_counts.values()),
            "after": sum(dedup_counts.values()),
            "merged_rows": sum(raw_counts.values()) - sum(dedup_counts.values()),
            "per_predicate": {p: {"raw": raw_counts.get(p, 0), "dedup": dedup_counts.get(p, 0),
                                  "merged": raw_counts.get(p, 0) - dedup_counts.get(p, 0)} for p in PREDICATES},
        },
        "dedup_arithmetic": dedup_arith,
        "join_reconciliation": recon,
        "ghost": {"count": len(ghosts), "unique_as_book_id": sorted({r["source_ref"] for r in ghosts if r["source_ref"]}),
                  "rows": ghost_rows},
        "unresolved_person_ids": unresolved,
        "ref_id_unresolved_person": {"by_face": miss_by_face, "total": len(miss_total), "ids": miss_total},
        "evidence_dual_source": {"count": len(double), "by_evidence": ev_counts},
        "coverage": coverage,
    }


def _group_count(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


# ═══════════════════════════════════════════════════════════════════════════ 内容指纹（只读）
def db_fingerprint(db_path: Path | str) -> dict[str, Any]:
    """库内容指纹（逐表：行数 + 有序全字段导出的 sha256）。**不用库文件 md5**（§8 第 6 条）。"""
    p = Path(db_path)
    out: dict[str, Any] = {"exists": p.is_file(), "path": str(p), "tables": {}}
    if not p.is_file():
        return out
    conn = _ro_connect(p)
    try:
        tabs = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tabs:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            h = hashlib.sha256()
            n = 0
            for row in conn.execute(f"SELECT * FROM {t}"):
                vals = [row[c] for c in cols]
                h.update(json.dumps(vals, ensure_ascii=False, default=str).encode("utf-8"))
                h.update(b"\n")
                n += 1
            out["tables"][t] = {"rows": n, "n_cols": len(cols), "sha256": h.hexdigest()}
    finally:
        conn.close()
    out["n_tables"] = len(out["tables"])
    return out


def package_tree_fingerprint(pkg_dir: Path) -> dict[str, Any]:
    """包目录指纹（文件名 + 大小 + 逐个 sha256 的 sha256）。"""
    p = Path(pkg_dir)
    recs = []
    if p.is_dir():
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            h = hashlib.sha256()
            with f.open("rb") as fh:
                for c in iter(lambda: fh.read(1 << 16), b""):
                    h.update(c)
            recs.append({"name": str(f.relative_to(p)), "size": f.stat().st_size, "sha256": h.hexdigest()})
    agg = hashlib.sha256()
    for r in recs:
        agg.update(json.dumps([r["name"], r["size"], r["sha256"]], ensure_ascii=False).encode("utf-8"))
        agg.update(b"\n")
    return {"path": str(p), "n_files": len(recs), "sha256_names_sizes": agg.hexdigest(),
            "files": {r["name"]: r["sha256"] for r in recs}}


# ═══════════════════════════════════════════════════════════════════════════ 批次登记（包目录即登记）
def relation_batches(export_root: Path) -> list[str]:
    root = Path(export_root)
    if not root.is_dir():
        return []
    return sorted(p.name[len("relation_import_"):] for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("relation_import_"))


def next_batch_id(export_root: Path, when: datetime | None = None) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y%m%d")
    prefix = f"relation_{stamp}_"
    used = set(relation_batches(export_root))
    nn = 1
    while f"{prefix}{nn:02d}" in used:
        nn += 1
    return f"{prefix}{nn:02d}"


def resolve_batch_id(export_root: Path, batch_id: str | None, *, create: bool) -> str:
    """缺省批次 ＝ 既有 `relation_import_*` 最新者；若无 ⇒ 当日默认名。"""
    if batch_id:
        if not create and batch_id not in set(relation_batches(export_root)):
            raise ImportPackageError("BATCH_NOT_FOUND", f"批次不存在：{batch_id}")
        return batch_id
    existing = relation_batches(export_root)
    if existing:
        return existing[-1]
    return next_batch_id(export_root)


# ═══════════════════════════════════════════════════════════════════════════ 出包
def _no_bom(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(3) != b"\xef\xbb\xbf"


def write_package_from_db(person_db, item_db, seal_db, export_root, batch_id: str | None = None,
                          *, create: bool = False) -> dict:
    """三库只读 → 联立 / 去重 / 归一 → 就绪包 `exports/relation_import_<batch_id>/`。

    `create=True`：允许以新 `batch_id` 创建（CLI 入口）；`create=False`：显式批次须已存在（端点口径）。
    """
    export_root = Path(export_root)
    batch_id = resolve_batch_id(export_root, batch_id, create=create)
    built = build_edges(Path(person_db), Path(item_db), Path(seal_db), batch_id)
    edges, stats = built["edges"], built["stats"]

    pkg_dir = export_root / f"relation_import_{batch_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = pkg_dir / "relations.jsonl"
    manifest_path = pkg_dir / "manifest.json"

    with jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
        for e in edges:
            fh.write(json.dumps({k: e.get(k) for k in EDGE_FIELDS}, ensure_ascii=False) + "\n")

    # ── 幂等键（三元组）唯一计数 ──
    triples = [(e["predicate"], e["subject_id"], e["object_id"]) for e in edges]
    tri_unique = len(set(triples))

    # ── 自检 ──
    checks = {
        "rows": len(edges),
        "idempotency_key_unique": tri_unique,
        "idempotency_key_total": len(triples),
        "idempotency_all_unique": tri_unique == len(triples),
        "predicates_only_enum": sorted({e["predicate"] for e in edges}),
        "predicates_all_in_enum": all(e["predicate"] in PREDICATES for e in edges),
        "no_bom": _no_bom(jsonl_path),
    }

    # ── 门禁指纹（只读；三库 + 三线既有包）──
    guard = {
        "yinpu.db": db_fingerprint(Path(person_db).parent.parent / "data" / "yinpu.db"),
        "var/person_ingest.db": db_fingerprint(person_db),
        "var/item_ingest.db": db_fingerprint(item_db),
        "var/seal_ingest.db": db_fingerprint(seal_db),
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "key_face_status": "pending_xiai",
        "form": "F2（manifest + relations.jsonl + report.json）",
        "batch_id": batch_id,
        "created_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）三线关联数据 · **本库联立（零联网）**",
        "source_note": "本包由 `var/person_ingest.db` / `var/item_ingest.db` / `var/seal_ingest.db` 三库联立；"
                       "**不联网、不重采**（四线既有数据已够）。",
        "source_tables": SOURCE_TABLES,
        "source_totals": {"person_relations": 1650, "item_creators": 1440, "seal_links": 8964},
        "idempotency_key": "(predicate, subject_id, object_id)",
        "idempotency": {
            "key": "(predicate, subject_id, object_id)",
            "non_null": len(triples), "unique": tri_unique, "total": len(triples),
            "all_unique": tri_unique == len(triples),
        },
        "predicate_counts": stats["predicate_counts"],
        "predicate_raw_counts": stats["raw_counts"],
        "files": [
            {"name": "relations.jsonl", "rows": len(edges), "fields": EDGE_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM，字段名稳定"},
            {"name": "manifest.json", "rows": None, "fields": []},
            {"name": "report.json", "rows": None, "fields": []},
        ],
        "field_dict": FIELD_DICT,
        "dedup": stats["dedup"],
        "dedup_arithmetic": stats["dedup_arithmetic"],
        "coverage": stats["coverage"],
        "ghost_unresolved": {
            "ghost_count": stats["ghost"]["count"],
            "ghost_unique_as_book_id": stats["ghost"]["unique_as_book_id"],
            "unresolved_person_count": len(stats["unresolved_person_ids"]),
            "ref_id_unresolved_person_total": stats["ref_id_unresolved_person"]["total"],
        },
        "join_reconciliation": stats["join_reconciliation"],
        "r_defaults": {"R-a": R_A_NOTE, "R-b": R_B_NOTE, "R-c": R_C_NOTE,
                       "R-d": R_D_NOTE, "R-e": R_E_NOTE,
                       "R-f": "exports/relation_import_<batch_id>/：relations.jsonl + manifest.json + report.json"},
        "checks": checks,
        "submission": "提交与审核在玺爱侧；feicui **不写 xiai 任何文件、不调任何云函数**。"
                      "本包为 feicui 自有树内产物，键面待人（xiai）挑选；键面未裁 ⇒ key_face_status=pending_xiai。",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": RELATION_SCHEMA_VERSION,
        "batch_id": batch_id,
        "generated_at": _now(),
        "source": manifest["source"],
        "predicate_counts": stats["predicate_counts"],
        "predicate_raw_counts": stats["raw_counts"],
        "dedup": stats["dedup"],
        "dedup_arithmetic": stats["dedup_arithmetic"],
        "join_reconciliation": stats["join_reconciliation"],
        "ghost": stats["ghost"],
        "unresolved_person_ids": stats["unresolved_person_ids"],
        "ref_id_unresolved_person": stats["ref_id_unresolved_person"],
        "evidence_dual_source": stats["evidence_dual_source"],
        "coverage": stats["coverage"],
        "guard_fingerprints": guard,
    }
    (pkg_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "batch_id": batch_id,
        "package_dir": str(pkg_dir),
        "key_face_status": manifest["key_face_status"],
        "predicate_counts": stats["predicate_counts"],
        "rows": len(edges),
        "raw_total": stats["raw_total"],
        "dedup": stats["dedup"],
        "idempotency_key": manifest["idempotency_key"],
        "idempotency": manifest["idempotency"],
        "ghost_unresolved": manifest["ghost_unresolved"],
        "checks": checks,
        "files": manifest["files"],
        "generated_at": manifest["created_at"],
        "submission": manifest["submission"],
    }
    return {"package_dir": pkg_dir, "jsonl_path": jsonl_path, "manifest_path": manifest_path,
            "report_path": pkg_dir / "report.json", "summary": summary}


# ═══════════════════════════════════════════════════════════════════════════ 摘要（只读，不落盘）
def summary_only(person_db, item_db, seal_db) -> dict:
    """`GET /api/relations/summary`：各 predicate 计数 / 三表行数 / 去重前后 / 未命中·幽灵计数。

    **只读、不重建包、不落盘。**
    """
    built = build_edges(Path(person_db), Path(item_db), Path(seal_db), "(summary)")
    st = built["stats"]
    return {
        "source_tables": SOURCE_TABLES,
        "predicate_counts": st["predicate_counts"],
        "predicate_raw_counts": st["raw_counts"],
        "dedup": st["dedup"],
        "dedup_arithmetic": st["dedup_arithmetic"],
        "ghost_unresolved": {
            "ghost_count": st["ghost"]["count"],
            "ghost_unique_as_book_id": st["ghost"]["unique_as_book_id"],
            "unresolved_person_count": len(st["unresolved_person_ids"]),
            "unresolved_person_ids": st["unresolved_person_ids"],
            "ref_id_unresolved_person": st["ref_id_unresolved_person"],
        },
        "coverage": st["coverage"],
        "idempotency_key": "(predicate, subject_id, object_id)",
    }


# ═══════════════════════════════════════════════════════════════════════════ CLI
def _cli() -> int:
    import argparse

    from .config import get_settings

    st = get_settings()
    ap = argparse.ArgumentParser(description="feicui 关联面（三表联立）")
    ap.add_argument("cmd", choices=["package", "summary", "recon", "fingerprint"],
                    help="子命令")
    ap.add_argument("--person-db", default=str(st.person_db_path))
    ap.add_argument("--item-db", default=str(st.items_db_path))
    ap.add_argument("--seal-db", default=str(st.seals_db_path))
    ap.add_argument("--export-root", default=str(st.relations_export_root))
    ap.add_argument("--batch-id", default=None)
    args = ap.parse_args()

    if args.cmd == "summary":
        print(json.dumps(summary_only(args.person_db, args.item_db, args.seal_db),
                         ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "recon":
        built = build_edges(Path(args.person_db), Path(args.item_db), Path(args.seal_db),
                            args.batch_id or "(recon)")
        print(json.dumps(built["stats"], ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "fingerprint":
        out = {
            "var/person_ingest.db": db_fingerprint(args.person_db),
            "var/item_ingest.db": db_fingerprint(args.item_db),
            "var/seal_ingest.db": db_fingerprint(args.seal_db),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    # package（CLI 为批次创建入口 ⇒ create=True）
    try:
        pkg = write_package_from_db(args.person_db, args.item_db, args.seal_db,
                                    args.export_root, args.batch_id, create=True)
    except ImportPackageError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc)}, ensure_ascii=False))
        return 2
    out = {k: (str(v) if isinstance(v, Path) else v) for k, v in pkg.items() if k != "summary"}
    out["summary"] = pkg.get("summary")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
