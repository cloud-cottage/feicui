"""印人采集线（person-ingest，批 1）——Kong。

**权威拆解件**：`../docs/person-ingest-draft-v0.1.md` v0.1（复旦印藏「印人」采集）。
远端源 `https://yin.fudan.edu.cn`（**只读**：GET/POST 取数，**不上传任何数据**）。

**采集主链路（Zang 2026-10-10 纠偏后）**：
  `person/list`（1 次，`pageRows=1000` 取全 570）
  → **`graph/person/<grbsm>` 逐人必读**（570 次；详情页真正新增的数据＝关联印谱/印章）
  → 归一化 → 落独立库 → 批次包。
  `person/detail/<grbsm>` **降级为 best-effort**（默认开启、失败不阻塞）：实测 detail 主数据与
  列表行**除 `seqid`/`createdTime` 外逐字节等价**，故 detail 取不到时可安全用列表行替代，
  仅记入 report 的「未取详情确认」计数。

**限流陷阱（实测）**：`person/detail` 与 `graph` 会**按时间窗限流**，形态为 **HTTP 200** ＋ body
`{"msg":"操作频繁，请稍候再试!","code":"429","status":"true"}` —— `code` 是**字符串** `"429"`、
`status` 仍是 `true`、**只有 `data` 缺失**能暴露失败。**禁止**把这种回包计为成功；一律走指数退避
（5s→10s→20s→60s）重试，退避耗尽才落失败/「未取详情确认」。

纪律（逐条对应拆解件 §4 与 §6）：
  * **只加法**：不改既有 E1〜E7、不动 `stamps` / `jobs` / `output/` / `exports/fb_*` / `app.py`；
  * **独立库**：本线一律写 `feicui/var/person_ingest.db`（`yinpu.db` 一字不碰）；
  * **HTTP 客户端只用 stdlib**（`urllib.request`），不改 `server/requirements.txt`；
  * **礼貌限速**：串行 + 请求间隔 + 抖动，**可断点续跑**（已入库者跳过网络取数）；
  * **不碰 xiai 仓**：批次包即对外唯一交付缝（另一个会话按它落 xiai）；
  * **不得丢源**：源原文（detail 整行或列表行）与源键（`source_person_id` /
    `source_data_source_id` / `source_seqid`）一律原样落库；
  * **失败不静默**：逐条失败写进批次包 `report.json` 的失败清单（**不写进 `persons.jsonl`**）。

**繁简口径**（拆解件 §4.5）：**繁体为正字段、简体入 `*_chs` 副字段**，**不做任何转换改写**。
"""
from __future__ import annotations

import json
import hashlib
import logging
import random
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("feicui.api.persons")

PERSON_SCHEMA_VERSION = "feicui.person_ingest/1"
# 交付缝 §3.15.10（AC-21）：批次包 `manifest.json` 的 `schema_version` **钉为整数 1**。
MANIFEST_SCHEMA_VERSION = 1

# 字 / 号 / 别名六字段（含 `_chs`）——**对外形态一律为 JSON 数组**（交付缝 §3.15.10 ＋ xiai §3.54.3
# 的 `courtesy_names[]` / `art_names[]` / `alias_names[]`），元素形如
# `{"value":…,"kind":…,"extraction":"rule-based","from":"personBm"|"personBmChs"}`；**空 ⇒ `[]`**（不得为 `''`）。
# SQLite 无原生数组类型 ⇒ 库内在 `persons` 表以**规范 JSON 数组文本**存储；**所有读取缝**
# （批次包 `persons.jsonl` 的 `write_package` ＋ API `get_person`）一律经 `decode_name_list` 解码为**真 `list`**。
NAME_LIST_FIELDS = ("courtesy_names", "courtesy_names_chs", "art_names", "art_names_chs",
                    "alias_names", "alias_names_chs")


def decode_name_list(value: Any) -> list:
    """把库内的「规范 JSON 数组文本」解码为**真 `list`**（交付缝 §3.15.10 / AC-22）。

    幂等：已是 `list` 则原样返回；`None` / 空串 / 非数组 JSON / 坏值 ⇒ `[]`（**绝不**回退成字符串）。
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []

# ── 复姓白名单（拆解件 §4.5 规则；**只用于抽取**，抽取结果一律标注 rule-based）────────────────
COMPOUND_SURNAMES = {
    "歐陽", "欧阳", "司馬", "司马", "上官", "諸葛", "诸葛", "東方", "东方", "皇甫", "尉遲", "尉迟",
    "公孫", "公孙", "慕容", "司徒", "獨孤", "独孤", "南宮", "南宫", "宇文", "長孫", "长孙", "夏侯",
    "西門", "西门", "令狐", "端木", "聞人", "闻人", "赫連", "赫连", "澹臺", "澹台", "呼延", "百里",
    "鍾離", "钟离", "子車", "子车", "拓跋", "夾谷", "夹谷", "完顏", "完颜", "万俟", "鮮于", "鲜于",
}

# personBm 自由文本 → 姓名类型 的**规则化**标记词（值＝目标分类：字 / 號 / 名 / 別署 / 齋名）
BM_MARKERS: list[tuple[str, str]] = [
    ("齋名", "齋名"), ("斋名", "齋名"), ("齋堂", "齋名"), ("斋堂", "齋名"),
    ("齋號", "齋名"), ("斋号", "齋名"),
    ("別署", "別署"), ("别署", "別署"),
    ("別號", "別署"), ("别号", "別署"),
    ("自號", "號"), ("自号", "號"), ("又號", "號"), ("又号", "號"),
    ("號", "號"), ("号", "號"),
    ("初名", "名"), ("後名", "名"), ("后名", "名"), ("始名", "名"), ("原名", "名"),
    ("又名", "名"), ("更名", "名"), ("改名", "名"), ("本名", "名"),
    ("字", "字"),
    ("名", "名"),
]

# 目标分类 → 归一化后的归属数组
KIND_TO_BUCKET = {"字": "courtesy", "號": "art", "別署": "art", "名": "alias", "齋名": "alias"}

EXTRACTION = "rule-based"  # 逐项标注：抽取（非权威分类）
RATE_LIMIT_MARKER = '{"msg":"操作频繁，请稍候再试!","code":"429","status":"true"}'  # 陷阱形态原文


# ═══════════════════════════════════════════════════════════════════════════ HTTP（stdlib）
class FetchError(RuntimeError):
    """单条取数失败（网络 / 非 200 / 信封异常）⇒ 计入失败清单，**不静默跳过**。"""


class RateLimited(FetchError):
    """源侧限速（实测：HTTP **200** + 信封 `code:"429"` + `msg:"操作频繁，请稍候再试!"`）。

    不是失败，而是**礼节信号** ⇒ 指数退避重试；退避耗尽才作数。
    """


_RATE_MSG_HINTS = ("频密", "频繁")


def _one_call(url: str, *, method: str, data: bytes | None, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            http_status = resp.status
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"HTTP 429 {url}") from exc
        raise FetchError(f"HTTP {exc.code} {url}") from exc
    except Exception as exc:
        raise FetchError(f"{type(exc).__name__}: {exc} @ {url}") from exc
    if http_status != 200:
        raise FetchError(f"HTTP {http_status} {url}")
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise FetchError(f"非 JSON 响应 @ {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise FetchError(f"响应信封非对象 @ {url}")
    # 限速伪装成 200：body 里 code＝"429" 或 msg 含「频密 / 频繁」
    code = str(body.get("code") or "")
    if code == "429" or any(h in str(body.get("msg") or "") for h in _RATE_MSG_HINTS):
        raise RateLimited(f"源侧限速 code={code} msg={body.get('msg')!r} @ {url}")
    return body


def _http_json(base: str, path: str, *, method: str = "GET", payload: dict | None = None,
               timeout: float = 30.0, retries: int = 5, backoff: float = 5.0) -> dict:
    """带**限速退避**的取数：命中 429 时指数退避重试（5→10→20→40→60 秒，上限 60s）。"""
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json", "User-Agent": "feicui-person-ingest/1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            body = _one_call(url, method=method, data=data, headers=headers, timeout=timeout)
            code = body.get("code")
            if code not in (200, "200"):
                raise FetchError(f"源信封 code={code} msg={body.get('msg')!r} @ {url}")
            return body
        except RateLimited as exc:
            last = exc
            if attempt >= retries:
                break
            sleep_s = min(backoff * (2 ** attempt), 60.0)
            log.warning("源侧限速，退避 %.1fs（第 %d/%d 次重试）：%s", sleep_s, attempt + 1, retries, url)
            time.sleep(sleep_s)
    raise last or FetchError(f"取数失败 @ {url}")


def fetch_list(base: str, *, page_rows: int = 1000, timeout: float = 30.0) -> tuple[list[dict], int]:
    """列表页：`POST person/list`，`pageRows=1000` 一次取全（source `total`＝570）。"""
    body = _http_json(
        base, "/person/list", method="POST",
        payload={
            "pageNum": 1, "pageRows": int(page_rows), "fullText": "",
            "facetPersonGjqc": "", "facetPersonInitial": "",
            "orderField": "name", "orderType": "desc",
        },
        timeout=timeout,
    )
    rows = body.get("data") or []
    total = int(body.get("total") or len(rows))
    return list(rows), total


def fetch_detail(base: str, grbsm: str, *, timeout: float = 30.0, retries: int = 3) -> dict:
    """详情页主数据：`GET person/detail/<personGrbsm>`（**best-effort**；POST 形态 404）。

    退避口径（Zang 纠偏）：5s → 10s → 20s（最多 3 轮），仍失败 ⇒ 由调用方降级为列表行。
    """
    body = _http_json(base, f"/person/detail/{grbsm}", timeout=timeout, retries=retries, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"detail 无 data 字段：{grbsm}")
    return data


def fetch_graph(base: str, grbsm: str, *, timeout: float = 30.0) -> dict:
    """详情页关联图：`GET graph/person/<personGrbsm>`（**列表页没有**，本线**必读**）。"""
    body = _http_json(base, f"/graph/person/{grbsm}", timeout=timeout, retries=5, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"graph 无 data 字段：{grbsm}")
    return data


# ═══════════════════════════════════════════════════════════════════════════ 归一化（拆解件 §4.5）
def extract_name(full: str) -> tuple[str, str]:
    """姓 / 名抽取（**rule-based，不猜**）：拆解件 §4.5 规则。

    * 复姓白名单命中（3 字名）⇒ 姓取二字；
    * 单姓（2 / 3 字名）⇒ 姓取首字；
    * **4 字以上或无法判定 ⇒ `family_name=''`、整串落 `given_name`**（不拆分）。
    """
    name = (full or "").strip()
    if not name:
        return "", ""
    if len(name) >= 4:
        return "", name
    if len(name) == 3:
        if name[:2] in COMPOUND_SURNAMES:
            return name[:2], name[2:]
        return name[0], name[1:]
    if len(name) == 2:
        return name[0], name[1:]
    return "", name


def _split_clause_values(remainder: str) -> list[str]:
    out: list[str] = []
    for tok in remainder.split("、"):
        for sub in tok.split("／"):
            v = sub.strip().strip("。.，,；; ")
            if v.startswith("為") or v.startswith("为"):
                v = v[1:].strip()
            v = v.strip("「」『』《》")
            if v:
                out.append(v)
    return out


def _best_marker(clause: str) -> tuple[int, str, str] | None:
    best: tuple[int, str, str] | None = None
    for kw, kind in BM_MARKERS:
        idx = clause.find(kw)
        if idx < 0:
            continue
        if best is None or idx < best[0] or (idx == best[0] and len(kw) > len(best[1])):
            best = (idx, kw, kind)
    return best


def parse_bm_text(text: str, source_field: str) -> dict[str, list[dict]]:
    """`personBm` / `personBmChs` 自由文本 → 三桶（courtesy / art / alias）。

    **规则化抽取**：逐项带 `extraction='rule-based'` 与来源字段；**抽不准的一律落 alias**。
    """
    buckets: dict[str, list[dict]] = {"courtesy": [], "art": [], "alias": []}
    if not text:
        return buckets
    seen: dict[str, set[str]] = {"courtesy": set(), "art": set(), "alias": set()}
    for raw_clause in text.replace("\n", "。").split("。"):
        for clause in raw_clause.split("，"):
            clause = clause.strip().strip("，,；;、")
            if not clause:
                continue
            found = _best_marker(clause)
            if found is None:
                for v in _split_clause_values(clause):
                    if v not in seen["alias"]:
                        seen["alias"].add(v)
                        buckets["alias"].append(
                            {"value": v, "kind": "未判定", "extraction": EXTRACTION, "from": source_field}
                        )
                continue
            idx, kw, kind = found
            bucket = KIND_TO_BUCKET.get(kind, "alias")
            for v in _split_clause_values(clause[idx + len(kw):]):
                if v not in seen[bucket]:
                    seen[bucket].add(v)
                    buckets[bucket].append(
                        {"value": v, "kind": kind, "extraction": EXTRACTION, "from": source_field}
                    )
    return buckets


def _year(text: Any) -> int | None:
    """生卒年：纯数字 ⇒ 整数；含 `?` / 空 / 非数字 / 0 ⇒ **null**（不设特值，拆解件 §4.5）。"""
    s = str(text).strip() if text is not None else ""
    if not s or "?" in s or "？" in s:
        return None
    if not s.isdigit():
        return None
    n = int(s)
    return n if n > 0 else None


def normalize_relations(graph: dict, source_person_id: str) -> list[dict]:
    """`graph/person` → 逐条关联（kind ∈ {印谱, 印章}；可空）。"""
    out: list[dict] = []
    for cat in (graph.get("children") or []):
        kind = str(cat.get("name") or "").strip()
        for seq, item in enumerate(cat.get("children") or []):
            out.append({
                "source_person_id": source_person_id,
                "kind": kind,
                "ref_id": None if item.get("id") is None else str(item.get("id")),
                "name": item.get("name"),
                "desc": item.get("desc"),
                "creator_type": item.get("creatorType"),
                "image_key": item.get("image"),
                "as_book_id": item.get("asBookId"),
                "has_image": None if item.get("hasImage") is None else str(item.get("hasImage")),
                "type": item.get("type"),
                "seq": seq,
            })
    return out


def normalize_person(row: dict, graph: dict) -> dict:
    """把源行（detail 整行，或降级时的列表行）+ 关联图归一化成一条 `persons` 记录。"""
    grbsm = str(row.get("personGrbsm") or "").strip()
    full = str(row.get("personGrsxmc") or "")
    family, given = extract_name(full)
    bm = parse_bm_text(str(row.get("personBm") or ""), "personBm")
    bm_chs = parse_bm_text(str(row.get("personBmChs") or ""), "personBmChs")

    def _json_list(items: list[dict]) -> str:
        return json.dumps(items, ensure_ascii=False)

    flag = row.get("flag")
    return {
        "source_person_id": grbsm,
        "source_seqid": None if row.get("seqid") is None else str(row.get("seqid")),
        "source_data_source_id": row.get("dataSourceId"),
        "name_full": full,
        "name_full_chs": None,  # 源无简体姓名版 ⇒ 留空，不自行转繁简
        "family_name": family,
        "given_name": given,
        "name_extraction": EXTRACTION,
        "courtesy_names": _json_list(bm["courtesy"]),
        "courtesy_names_chs": _json_list(bm_chs["courtesy"]),
        "art_names": _json_list(bm["art"]),
        "art_names_chs": _json_list(bm_chs["art"]),
        "alias_names": _json_list(bm["alias"]),
        "alias_names_chs": _json_list(bm_chs["alias"]),
        "birth_year": _year(row.get("personCsrq")),
        "death_year": _year(row.get("personSwrq")),
        "birth_death_text": row.get("personSzn"),
        "native_place": row.get("personJg"),
        "native_place_chs": row.get("personJgChs"),
        "biography": row.get("personJj"),
        "biography_chs": row.get("personJjChs"),
        "nationality": row.get("personGj"),
        "nationality_chs": row.get("personGjqc"),
        "nationality_code": None if row.get("personGjdm") is None else str(row.get("personGjdm")),
        "cbdb_id": row.get("personCbdbId"),
        "source": row.get("dataSource"),
        "source_id": row.get("dataSourceId"),
        "spell": row.get("personSpell"),
        "initial": row.get("personInitial"),
        "flag": None if flag is None else int(flag),
        "notes": row.get("personGrfz"),  # 生卒考订 / 按语（源字段，不丢）
        "raw_json": json.dumps(row, ensure_ascii=False),  # 源原文
        "relations": normalize_relations(graph, grbsm),
    }


# ═══════════════════════════════════════════════════════════════════════════ 存储（独立库）
SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS person_import_batches (
        batch_id TEXT PRIMARY KEY,
        created_at TEXT, updated_at TEXT, status TEXT,
        source_total INTEGER, fetched INTEGER, persons_ok INTEGER, relations_ok INTEGER,
        failed_count INTEGER, elapsed_s REAL, package_dir TEXT, report_path TEXT,
        content_fingerprint TEXT, params_json TEXT, notes TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS persons (
        source_person_id TEXT PRIMARY KEY,
        source_seqid TEXT, source_data_source_id TEXT,
        name_full TEXT, name_full_chs TEXT, family_name TEXT, given_name TEXT, name_extraction TEXT,
        courtesy_names TEXT, courtesy_names_chs TEXT,
        art_names TEXT, art_names_chs TEXT,
        alias_names TEXT, alias_names_chs TEXT,
        birth_year INTEGER, death_year INTEGER, birth_death_text TEXT,
        native_place TEXT, native_place_chs TEXT,
        biography TEXT, biography_chs TEXT,
        nationality TEXT, nationality_chs TEXT, nationality_code TEXT,
        cbdb_id TEXT, source TEXT, source_id TEXT,
        spell TEXT, initial TEXT, flag INTEGER, notes TEXT,
        raw_json TEXT, batch_id TEXT, updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS person_relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_person_id TEXT, kind TEXT, ref_id TEXT, name TEXT, desc TEXT,
        creator_type TEXT, image_key TEXT, as_book_id TEXT, has_image TEXT, type TEXT,
        seq INTEGER, batch_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_person_relations_pid ON person_relations(source_person_id)",
    "CREATE INDEX IF NOT EXISTS idx_persons_initial ON persons(initial)",
    "CREATE INDEX IF NOT EXISTS idx_persons_nationality ON persons(nationality)",
]

# 对外字段名（批次包 / 外部消费缝）——**顺序即 JSONL 键序**；与拆解件 §4.5 映射表逐项对齐
PERSON_FIELDS = [
    "source_person_id", "source_seqid", "source_data_source_id",
    "name_full", "name_full_chs", "family_name", "given_name", "name_extraction",
    "courtesy_names", "courtesy_names_chs", "art_names", "art_names_chs",
    "alias_names", "alias_names_chs", "birth_year", "death_year", "birth_death_text",
    "native_place", "native_place_chs", "biography", "biography_chs",
    "nationality", "nationality_chs", "nationality_code", "cbdb_id", "source", "source_id",
    "spell", "initial", "flag", "notes", "raw_json",
]
PERSON_CONTENT_COLS = PERSON_FIELDS  # 内容指纹参与列（排除 batch_id / updated_at）
RELATION_FIELDS = [
    "source_person_id", "kind", "ref_id", "name", "desc",
    "creator_type", "image_key", "as_book_id", "has_image", "type", "seq",
]
RELATION_CONTENT_COLS = RELATION_FIELDS


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def ensure_schema(db_path: Path | str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for sql in SCHEMA_SQL:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def person_exists(db_path: Path | str, source_person_id: str) -> bool:
    conn = _connect(db_path)
    try:
        return conn.execute(
            "SELECT 1 FROM persons WHERE source_person_id=?", (source_person_id,)
        ).fetchone() is not None
    finally:
        conn.close()


def upsert_person(db_path: Path | str, rec: dict, batch_id: str) -> None:
    cols = list(PERSON_FIELDS)
    placeholders = ", ".join("?" for _ in cols)
    update = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "source_person_id")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"INSERT INTO persons ({', '.join(cols)}, batch_id, updated_at) "
            f"VALUES ({placeholders}, ?, ?) "
            f"ON CONFLICT(source_person_id) DO UPDATE SET {update}, batch_id=excluded.batch_id, "
            f"updated_at=excluded.updated_at",
            [rec.get(c) for c in cols] + [batch_id, _now()],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def replace_relations(db_path: Path | str, source_person_id: str, relations: list[dict], batch_id: str) -> int:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM person_relations WHERE source_person_id=?", (source_person_id,))
        for rel in relations:
            conn.execute(
                "INSERT INTO person_relations (source_person_id, kind, ref_id, name, desc, "
                "creator_type, image_key, as_book_id, has_image, type, seq, batch_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_person_id, rel.get("kind"), rel.get("ref_id"), rel.get("name"), rel.get("desc"),
                 rel.get("creator_type"), rel.get("image_key"), rel.get("as_book_id"),
                 rel.get("has_image"), rel.get("type"), rel.get("seq"), batch_id),
            )
        conn.commit()
        return len(relations)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def content_fingerprint(conn: sqlite3.Connection) -> str:
    """persons + person_relations 的**内容指纹**（排除 batch_id / updated_at / 自增 id）。"""
    h = hashlib.sha256()
    for row in conn.execute(
        f"SELECT {', '.join(PERSON_CONTENT_COLS)} FROM persons ORDER BY source_person_id"
    ):
        h.update(json.dumps(list(row), ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    for row in conn.execute(
        f"SELECT {', '.join(RELATION_CONTENT_COLS)} FROM person_relations "
        f"ORDER BY source_person_id, kind, ref_id, seq"
    ):
        h.update(json.dumps(list(row), ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def db_counts(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        return {
            "persons": conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
            "relations": conn.execute("SELECT COUNT(*) FROM person_relations").fetchone()[0],
            "batches": conn.execute("SELECT COUNT(*) FROM person_import_batches").fetchone()[0],
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ 批次
def next_batch_id(export_root: Path, when: datetime | None = None) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y%m%d")
    prefix = f"person_{stamp}_"
    used = set()
    if Path(export_root).is_dir():
        for p in Path(export_root).iterdir():
            if p.is_dir() and p.name.startswith(prefix):
                used.add(p.name)
    nn = 1
    while f"{prefix}{nn:02d}" in used:
        nn += 1
    return f"{prefix}{nn:02d}"


def create_batch(db_path: Path | str, batch_id: str, params: dict, source_total: int | None = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO person_import_batches "
            "(batch_id, created_at, updated_at, status, source_total, fetched, persons_ok, "
            " relations_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint, params_json, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, _now(), _now(), "RUNNING", source_total, 0, 0, 0, 0, 0.0,
             None, None, None, json.dumps(params, ensure_ascii=False), None),
        )
        conn.commit()
    finally:
        conn.close()


def finish_batch(db_path: Path | str, batch_id: str, **kw: Any) -> None:
    fields = ["updated_at", "status", "source_total", "fetched", "persons_ok", "relations_ok",
              "failed_count", "elapsed_s", "package_dir", "report_path", "content_fingerprint", "notes"]
    values = [_now()] + [kw.get(f) for f in fields[1:]]
    conn = _connect(db_path)
    try:
        conn.execute(
            f"UPDATE person_import_batches SET {', '.join(f'{f}=?' for f in fields)} WHERE batch_id=?",
            values + [batch_id],
        )
        conn.commit()
    finally:
        conn.close()


def list_batches(db_path: Path | str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT batch_id, created_at, updated_at, status, source_total, fetched, persons_ok, "
            "relations_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint "
            "FROM person_import_batches ORDER BY batch_id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ 采集主流程
def run_sync(
    *,
    db_path: Path,
    export_root: Path,
    base: str,
    batch_id: str | None = None,
    resume: bool = True,
    delay: float = 0.5,
    limit: int | None = None,
    timeout: float = 30.0,
    page_rows: int = 1000,
    fetch_detail_best_effort: bool = True,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """列表 → 逐人 graph（**必读**）→（best-effort detail）→ 归一化 → 落库 → 批次包。

    **可断点续跑**（`resume`：已入库者跳过网络取数）+ **礼貌限速**（`delay` + 抖动）。
    """
    ensure_schema(db_path)
    t0 = time.time()

    rows, total = fetch_list(base, page_rows=page_rows, timeout=timeout)
    if limit is not None:
        rows = rows[: int(limit)]

    if batch_id is None:
        batch_id = next_batch_id(export_root)
    params = {"resume": resume, "delay": delay, "limit": limit, "page_rows": page_rows,
              "detail_best_effort": fetch_detail_best_effort}
    create_batch(db_path, batch_id, params, source_total=total)

    failures: list[dict] = []
    detail_unconfirmed: list[dict] = []
    persons_ok = 0
    relations_ok = 0
    skipped = 0
    fetched = 0
    detail_confirmed = 0
    detail_skipped_circuit = 0
    # detail 熔断（实测：detail 端点限速远严于 graph，429 退避会拖垮整体）——
    # 连续 DETAIL_STREAK_LIMIT 次 429 ⇒ 打开熔断，后续直接降级为列表行（detail ≡ 列表行，见证据 07）。
    detail_fail_streak = 0
    detail_disabled = False
    DETAIL_STREAK_LIMIT = 6

    def _jittered() -> float:
        return max(0.05, delay * (1.0 + random.uniform(-0.25, 0.25)))

    for idx, row in enumerate(rows, start=1):
        grbsm = str(row.get("personGrbsm") or "").strip()
        if not grbsm:
            failures.append({"source_person_id": None, "stage": "row", "error": "行缺 personGrbsm"})
            continue
        if resume and person_exists(db_path, grbsm):
            skipped += 1
            persons_ok += 1
            continue

        # ① graph（必读；失败 ⇒ 计入失败清单并跳过该人）
        try:
            graph = fetch_graph(base, grbsm, timeout=timeout)
            fetched += 1
        except FetchError as exc:
            failures.append({"source_person_id": grbsm, "stage": "graph", "error": str(exc)})
            time.sleep(_jittered())
            continue

        # ② detail（best-effort；429 只重试 1 次，连续失败则熔断 ⇒ 用列表行替代）
        src_row = row
        if fetch_detail_best_effort and not detail_disabled:
            try:
                detail = fetch_detail(base, grbsm, timeout=timeout, retries=1)
                fetched += 1
                if detail.get("personGrbsm"):
                    src_row = detail
                    detail_confirmed += 1
                    detail_fail_streak = 0
            except FetchError as exc:
                detail_fail_streak += 1
                detail_unconfirmed.append({"source_person_id": grbsm, "error": str(exc),
                                           "fallback": "list_row"})
                if detail_fail_streak >= DETAIL_STREAK_LIMIT:
                    detail_disabled = True
                    log.warning("detail 连续 %d 次限速 ⇒ 熔断，后续降级为列表行", detail_fail_streak)
        elif fetch_detail_best_effort and detail_disabled:
            detail_skipped_circuit += 1

        # ③ 归一化 + 落库
        try:
            rec = normalize_person(src_row, graph)
            upsert_person(db_path, rec, batch_id)
            relations_ok += replace_relations(db_path, grbsm, rec["relations"], batch_id)
            persons_ok += 1
        except Exception as exc:
            failures.append({"source_person_id": grbsm, "stage": "store", "error": f"{type(exc).__name__}: {exc}"})

        time.sleep(_jittered())
        if progress and (idx % 25 == 0 or idx == len(rows)):
            progress({"done": idx, "total": len(rows), "persons_ok": persons_ok,
                      "failed": len(failures), "detail_unconfirmed": len(detail_unconfirmed)})

    conn = _connect(db_path)
    try:
        fingerprint = content_fingerprint(conn)
        pkg = write_package(
            conn, export_root=export_root, batch_id=batch_id, source_total=total,
            fetched=fetched, skipped=skipped, failures=failures, detail_unconfirmed=detail_unconfirmed,
            detail_confirmed=detail_confirmed, detail_skipped_circuit=detail_skipped_circuit,
            params=params, elapsed_s=time.time() - t0, base=base,
        )
    finally:
        conn.close()

    finish_batch(
        db_path, batch_id, status="DONE", source_total=total, fetched=fetched,
        persons_ok=persons_ok, relations_ok=relations_ok, failed_count=len(failures),
        elapsed_s=round(time.time() - t0, 3), package_dir=str(pkg["package_dir"]),
        report_path=str(pkg["report_path"]), content_fingerprint=fingerprint,
        notes=json.dumps({"skipped_resume": skipped, "detail_unconfirmed": len(detail_unconfirmed)},
                         ensure_ascii=False),
    )
    return {
        "batch_id": batch_id,
        "source_total": total,
        "rows_seen": len(rows),
        "fetched_requests": fetched,
        "skipped_resume": skipped,
        "persons_ok": persons_ok,
        "relations_ok": relations_ok,
        "detail_confirmed": detail_confirmed,
        "detail_unconfirmed_count": len(detail_unconfirmed),
        "detail_skipped_circuit": detail_skipped_circuit,
        "failed_count": len(failures),
        "failures": failures,
        "detail_unconfirmed": detail_unconfirmed,
        "package_dir": str(pkg["package_dir"]),
        "report_path": str(pkg["report_path"]),
        "content_fingerprint": fingerprint,
        "elapsed_s": round(time.time() - t0, 3),
        "counts": db_counts(db_path),
    }


def write_package(conn: sqlite3.Connection, *, export_root: Path, batch_id: str, source_total: int,
                  fetched: int, skipped: int, failures: list[dict], detail_unconfirmed: list[dict],
                  detail_confirmed: int, detail_skipped_circuit: int = 0, params: dict,
                  elapsed_s: float, base: str, provenance: dict | None = None) -> dict:
    """F1 形态：`manifest.json` + `report.json` + `persons.jsonl` + `relations.jsonl`。

    批次包＝**对外唯一交付缝**：自描述、稳定、可被外部程序逐行消费。
    """
    pkg_dir = Path(export_root) / batch_id
    pkg_dir.mkdir(parents=True, exist_ok=True)

    persons = [dict(r) for r in conn.execute(
        f"SELECT {', '.join(PERSON_FIELDS)} FROM persons ORDER BY source_person_id"
    )]
    relations = [dict(r) for r in conn.execute(
        f"SELECT {', '.join(RELATION_FIELDS)} FROM person_relations ORDER BY source_person_id, kind, ref_id, seq"
    )]
    # 交付缝 §3.15.10 / xiai §3.54.3：字 / 号 / 别名六字段**一律输出 JSON 数组**（非字符串）。
    # 库内为规范 JSON 数组文本 ⇒ 此处解码为真 list；空值恒为 `[]`（`decode_name_list` 保证）。
    for p in persons:
        for col in NAME_LIST_FIELDS:
            p[col] = decode_name_list(p.get(col))

    # JSONL：**一行一对象、UTF-8、无 BOM、键序＝PERSON_FIELDS/RELATION_FIELDS**（外部逐行解析）
    persons_path = pkg_dir / "persons.jsonl"
    relations_path = pkg_dir / "relations.jsonl"
    with persons_path.open("w", encoding="utf-8", newline="\n") as fh:
        for p in persons:
            fh.write(json.dumps({k: p.get(k) for k in PERSON_FIELDS}, ensure_ascii=False) + "\n")
    with relations_path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in relations:
            fh.write(json.dumps({k: r.get(k) for k in RELATION_FIELDS}, ensure_ascii=False) + "\n")

    fp = content_fingerprint(conn)
    kind_counts: dict[str, int] = {}
    for r in relations:
        kind_counts[r["kind"]] = kind_counts.get(r["kind"], 0) + 1
    persons_with_relations = conn.execute(
        "SELECT COUNT(DISTINCT source_person_id) FROM person_relations"
    ).fetchone()[0]

    # ── 如实登记（本单新增）：① `name_full_chs` 恒空之因由；② 采集 run 与本次重放计数**分离** ──
    # ① 源侧**根本没有**简体姓名字段：实测 `raw_json` 的 `*Chs` 键只有
    #    `personBmChs` / `personJjChs` / `personJgChs` / `personZzChs`（＝字 / 传记 / 籍贯 / 籍贯），
    #    **无**姓名对应项（`personGrsxmc` 无 `*Chs`）⇒ `name_full_chs` 恒 `null` **属预期、非缺陷**；
    #    字段键保留、不删（保留 `*_chs` 面口径一致）。
    name_full_chs_note = {
        "value_always_null": True,
        "expected": True,
        "reason": "源侧（复旦印藏 person/list | detail）**无简体姓名字段**；繁体姓名字段 `personGrsxmc` 无对应 `*Chs` 键",
        "evidence": ("实测 raw_json 的 `*Chs` 键恰 4 个：personBmChs / personJjChs / personJgChs / personZzChs"
                     "（570/570 行），**无**姓名对应 `personGrsxmcChs`"),
        "discipline": "不自行转繁简（沿「不转用户输入」纪律）⇒ 该字段恒 null 为**预期行为**，非缺陷",
        "field_key_kept": True,
    }
    # ② 计数分区：**不得**让「本次重放的 0」冒充「未采集」。
    run_provenance = provenance or {
        "acquisition_run": None,
        "this_package_write": {
            "kind": "live_ingest_run",
            "fetched_requests": fetched,
            "skipped_resume": skipped,
            "failed_count": len(failures),
            "elapsed_s": round(elapsed_s, 3),
        },
    }

    report = {
        "schema_version": PERSON_SCHEMA_VERSION,
        "batch_id": batch_id,
        "generated_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）「印人」",
        "source_base": base,
        "endpoints": {
            "list": "POST /service_yinpu/person/list  {pageNum:1, pageRows:1000, …}（一次取全）",
            "graph": "GET /service_yinpu/graph/person/<personGrbsm>（逐人必读：印谱/印章关联）",
            "detail": "GET /service_yinpu/person/detail/<personGrbsm>（best-effort）",
        },
        "params": params,
        "elapsed_s": round(elapsed_s, 3),
        "idempotency_key": "source_person_id（＝复旦 personGrbsm）",
        "counts": {
            "source_total": source_total,
            "persons": len(persons),
            "relations": len(relations),
            "relations_by_kind": kind_counts,
            "persons_with_relations": persons_with_relations,
            "fetched_requests": fetched,
            "skipped_resume": skipped,
            "detail_confirmed": detail_confirmed,
            "detail_unconfirmed": len(detail_unconfirmed),
            "detail_skipped_circuit_breaker": detail_skipped_circuit,
            "failed_count": len(failures),
            "field_list_persons": PERSON_FIELDS,
            "field_list_relations": RELATION_FIELDS,
        },
        "content_fingerprint": fp,
        "failures": failures,
        "detail_unconfirmed": detail_unconfirmed,
        "rate_limit": {
            "trap_form_sanitized": RATE_LIMIT_MARKER,
            "trap_form_note": "HTTP 200；body.code 是字符串 \"429\"；status 仍为 true；只有 data 缺失能暴露失败",
            "hint_message": "操作频繁/频密，请稍候再试!",
            "handling": "指数退避 5s→10s→20s→40s→60s（上限 60s）后重试；退避耗尽才落失败/未取详情确认",
            "measured_recovery_s": "≥60s 仍 429；约 300s 后同 id 恢复 200（本机实测，含探测期间续打延长窗口的干扰）",
        },
        "detail_equivalence_evidence": {
            "claim": "person/detail 主数据与 person/list 行除 seqid / createdTime 外逐字节等价",
            "sample": "15 人随机抽样逐字段比对（见 ops/person-ingest/07_detail_equivalence.json）",
            "consequence": "故 detail 取不到时可用列表行替代，仅记「未取详情确认」；关联数据一律取 graph/person",
        },
        "coverage": _coverage(persons),
        "complexity_note": "繁简：繁体为正字段，简体入 *_chs 副字段，未做任何转换改写",
        "name_full_chs_note": name_full_chs_note,
        "run_provenance": run_provenance,
    }
    (pkg_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "batch_id": batch_id,
        "created_at": _now(),
        "form": "F1（manifest + report + jsonl）",
        "source": "复旦印藏（yin.fudan.edu.cn）「印人」",
        "source_base": base,
        "source_endpoints": [
            "POST /service_yinpu/person/list  {pageNum:1, pageRows:1000, fullText:'', facetPersonGjqc:'', facetPersonInitial:'', orderField:'name', orderType:'desc'}",
            "GET /service_yinpu/graph/person/<personGrbsm>",
            "GET /service_yinpu/person/detail/<personGrbsm>（best-effort）",
        ],
        "source_total": source_total,
        "idempotency_key": "source_person_id（＝复旦 personGrbsm）",
        "files": [
            {"name": "persons.jsonl", "rows": len(persons), "fields": PERSON_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM"},
            {"name": "relations.jsonl", "rows": len(relations), "fields": RELATION_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM"},
            {"name": "report.json", "rows": None, "fields": ["counts", "failures", "detail_unconfirmed", "coverage", "rate_limit"]},
            {"name": "manifest.json", "rows": None, "fields": []},
        ],
        "field_conventions": {
            "繁体为正字段": "name_full / biography / native_place / nationality / courtesy_names / art_names / alias_names",
            "简体副字段": "*_chs（源侧同时给出；**未做任何转换改写**）",
            "抽取项": "family_name / given_name / courtesy_names[] / art_names[] / alias_names[] ⇒ 逐项 extraction='rule-based'；非权威分类",
            "字/号/别名形态": ("courtesy_names / courtesy_names_chs / art_names / art_names_chs / alias_names / alias_names_chs "
                              "＝ **JSON 数组**（元素形如 {\"value\":…,\"kind\":…,\"extraction\":\"rule-based\",\"from\":\"personBm\"|\"personBmChs\"}），"
                              "**空 ⇒ []**（不得为 ''）；**非字符串**（交付缝 §3.15.10 / xiai §3.54.3 的 string[] 面）"),
            "生卒": "birth_year / death_year：纯数字⇒整数；'?'/空⇒null；**不得出现 0 或 '?' 特值**",
            "溯源": "source_person_id / source / source_id / source_seqid / source_data_source_id 原样保留",
        },
        "counts": report["counts"],
        "content_fingerprint": fp,
        "name_full_chs_note": name_full_chs_note,
        "run_provenance": run_provenance,
    }
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"package_dir": pkg_dir, "report_path": pkg_dir / "report.json", "fingerprint": fp}


def _coverage(persons: list[dict]) -> dict:
    n = len(persons) or 1
    keys = {
        "name_full": lambda p: bool(p.get("name_full")),
        "family_name": lambda p: bool(p.get("family_name")),
        "alias_names": lambda p: bool(p.get("alias_names")),  # 现为真数组：[] 即空（非缺陷，沿 §3.15.10）
        "birth_year": lambda p: p.get("birth_year") is not None,
        "death_year": lambda p: p.get("death_year") is not None,
        "native_place": lambda p: bool(p.get("native_place")),
        "biography": lambda p: bool(p.get("biography")),
        "nationality": lambda p: bool(p.get("nationality")),
        "cbdb_id": lambda p: bool(p.get("cbdb_id")),
        "notes(personGrfz)": lambda p: bool(p.get("notes")),
    }
    return {k: f"{sum(1 for p in persons if fn(p))}/{len(persons)}"
            f" ({(sum(1 for p in persons if fn(p)) / n):.1%})" for k, fn in keys.items()}


# ═══════════════════════════════════════════════════════════════════════════ 查询
def list_persons(db_path: Path | str, *, page: int = 1, limit: int = 50, initial: str | None = None,
                 nationality: str | None = None, has_dates: bool | None = None,
                 has_relations: bool | None = None, q: str | None = None) -> dict:
    """列表（**纯 offset 分页**）：口径 ＝ `page`（1-based）/ `limit` / `total`。

    * **分页不变式（钉死）**：`has_more == (page * limit < total)`——**唯一**判据，绝不再出现
      「`has_more=true` ＋ `next_cursor=null`」这类**两口径混用、自相矛盾**的形态（旧实现之缺陷）。
    * **本端点不支持 `cursor`**：游标协议属 **E3/E7（jobs）**，本线（persons）只做 offset 分页；
      路由侧对**任何未白名单查询参数**（含 `cursor`）**一律 400**，绝不静默忽略。
      ⇒ 既然拿不出「真实可用游标」，就**不再回吐 `next_cursor`**（旧键已删）。
    * **空页 / 末页**：`page` 越界（`offset >= total`）⇒ `items=[]` 且 `has_more=False`；
      末页（`page*limit >= total`）⇒ `has_more=False`。**绝不**回吐第一页。
    """
    where: list[str] = []
    args: list[Any] = []
    if initial:
        where.append("p.initial = ?")
        args.append(initial)
    if nationality:
        where.append("(p.nationality = ? OR p.nationality_chs = ?)")
        args += [nationality, nationality]
    if has_dates is True:
        where.append("(p.birth_year IS NOT NULL OR p.death_year IS NOT NULL)")
    elif has_dates is False:
        where.append("(p.birth_year IS NULL AND p.death_year IS NULL)")
    if has_relations is True:
        where.append("EXISTS (SELECT 1 FROM person_relations r WHERE r.source_person_id = p.source_person_id)")
    elif has_relations is False:
        where.append("NOT EXISTS (SELECT 1 FROM person_relations r WHERE r.source_person_id = p.source_person_id)")
    if q:
        where.append("(p.name_full LIKE ? OR p.spell LIKE ? OR p.source_person_id = ?)")
        like = f"%{q}%"
        args += [like, like, q]
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    conn = _connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM persons p{where_sql}", args).fetchone()[0]
        offset = max(0, (page - 1) * limit)
        rows = conn.execute(
            f"""SELECT p.source_person_id, p.name_full, p.name_full_chs, p.family_name, p.given_name,
                       p.birth_year, p.death_year, p.birth_death_text, p.nationality, p.nationality_chs,
                       p.spell, p.initial, p.flag, p.cbdb_id,
                       (SELECT COUNT(*) FROM person_relations r
                          WHERE r.source_person_id=p.source_person_id AND r.kind='印谱') AS sealbook_count,
                       (SELECT COUNT(*) FROM person_relations r
                          WHERE r.source_person_id=p.source_person_id AND r.kind='印章') AS seal_count
                FROM persons p{where_sql}
                ORDER BY p.spell, p.source_person_id
                LIMIT ? OFFSET ?""",
            args + [limit, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
        # 分页不变式（钉死）：has_more 恒等于 page*limit < total（与 offset+len(items)<total 等价，见 docstring）。
        # 不再输出 next_cursor —— 本端点不支持 cursor（路由侧对 cursor 等未白名单参数一律 400）。
        has_more = (page * limit) < total
        return {"items": items, "page": page, "limit": limit, "total": total, "has_more": has_more}
    finally:
        conn.close()


def get_person(db_path: Path | str, grbsm: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM persons WHERE source_person_id=?", (grbsm,)).fetchone()
        if row is None:
            return None
        person = dict(row)
        # API 读取缝同样输出**真数组**（与批次包 persons.jsonl 一致；交付缝 §3.15.10）
        for col in NAME_LIST_FIELDS:
            if col in person:
                person[col] = decode_name_list(person[col])
        rels = conn.execute(
            "SELECT kind, ref_id, name, desc, creator_type, image_key, as_book_id, has_image, type, seq "
            "FROM person_relations WHERE source_person_id=? ORDER BY kind, seq",
            (grbsm,),
        ).fetchall()
        person["relations"] = [dict(r) for r in rels]
        return person
    finally:
        conn.close()


def list_facets(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        initials = [r[0] for r in conn.execute(
            "SELECT DISTINCT initial FROM persons WHERE initial IS NOT NULL AND initial<>'' ORDER BY initial")]
        nats = [r[0] for r in conn.execute(
            "SELECT nationality, COUNT(*) c FROM persons WHERE nationality IS NOT NULL AND nationality<>'' "
            "GROUP BY nationality ORDER BY c DESC, nationality")]
        return {"initials": initials, "nationalities": nats}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ CLI（自证 / 运维）
def _cli() -> int:
    import argparse

    from .config import get_settings

    st = get_settings()
    ap = argparse.ArgumentParser(description="feicui 印人采集线（批 1）")
    ap.add_argument("cmd", choices=["sync", "counts", "fingerprint", "list-count"], help="子命令")
    ap.add_argument("--db", default=str(st.person_db_path))
    ap.add_argument("--export-root", default=str(st.person_export_root))
    ap.add_argument("--base", default=st.person_source_base)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--no-detail", action="store_true", help="关闭 best-effort detail（纯列表行 + graph）")
    ap.add_argument("--delay", type=float, default=st.person_fetch_delay_s)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.cmd == "counts":
        ensure_schema(args.db)
        print(json.dumps(db_counts(args.db), ensure_ascii=False))
        return 0
    if args.cmd == "fingerprint":
        ensure_schema(args.db)
        conn = _connect(args.db)
        try:
            print(content_fingerprint(conn))
        finally:
            conn.close()
        return 0
    if args.cmd == "list-count":
        rows, total = fetch_list(args.base, timeout=st.person_fetch_timeout_s)
        print(json.dumps({"total": total, "rows": len(rows)}, ensure_ascii=False))
        return 0

    def _progress(p: dict) -> None:
        print(f"[sync] {p['done']}/{p['total']} ok={p['persons_ok']} failed={p['failed']} "
              f"detail_unconfirmed={p['detail_unconfirmed']}", flush=True)

    summary = run_sync(
        db_path=Path(args.db), export_root=Path(args.export_root), base=args.base,
        batch_id=args.batch_id, resume=not args.no_resume, delay=args.delay,
        limit=args.limit, timeout=st.person_fetch_timeout_s,
        fetch_detail_best_effort=not args.no_detail, progress=_progress,
    )
    print(json.dumps({k: v for k, v in summary.items() if k not in ("failures", "detail_unconfirmed")},
                     ensure_ascii=False, indent=2))
    print("FAILURES=" + json.dumps(summary["failures"], ensure_ascii=False))
    print("DETAIL_UNCONFIRMED=" + json.dumps(summary["detail_unconfirmed"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
