"""印谱采集线（item-ingest，批 1）——Kong。

**权威拆解件**：`../docs/item-ingest-draft-v0.1.md`（复旦印藏「印谱」采集）。
远端源 `https://yin.fudan.edu.cn`（**只读**：GET/POST 取数，**不上传任何数据**）。

**采集主链路（Kevin I-1 / I-2 裁定；2026-10-10 采集口径偏离，拆解件 §10）**：
  `book/list`（1 次，`pageRows=3000` 一次取全 **1742** 本，`total=1742`）→ **item 本体全部取自此处**
  → **逐本 `graph/book/<seqid>`**（**item↔person 关联主源**：`creatorType` / `name` / `id`（＝`personGrbsm`）；
    再与既有 `person_relations(kind='印谱')` 合并去重）
  →（可选）best-effort `book/detail/<seqid>`（**默认关**，`--with-detail` 才开，仅补
    `creatorRole` / `creatorRelator` / `bookDonor`）
  → 归一化 → 落**独立库** `var/item_ingest.db` → xiai 就绪包（`items.jsonl` + `item_creators.jsonl` +
    `manifest.json`）。

**关键源事实（实测，见 ops/item-ingest/）**：
  * `book/list` 的行**已带** `creatorList`/`itemList`/`titleList`/`bookDonor` 键，但**一律为 null**；
    真值只在 `book/detail/<seqid>` 里（详情为非空数组 / 非空串）——但 detail **严限流** ⇒ 本轮**不逐本调用**
    （本体字段，含题名繁简 / 卷册 / 成谱纪年 / 公元 / 题要长文 / `hasImage` 等，**列表行已齐**）。
  * 关联主源改用 **`graph/book/<seqid>`**（实测健康，2s 间隔 3/3 成功）；「印人」子项给
    `creatorType` / `name` / `id`（＝`personGrbsm`）。
  * 幂等键 ＝ `source_item_id`（＝ `seqid`）；`as_book_id`（＝补零 `asBookId`）为正数唯一桥接键。

**限流陷阱（实测）**：站点按时间窗限流，形态为 **HTTP 200** ＋ 信封 `{"code":"429", …}` 且
**无 `data`**（`status` 仍可能为 `true`）。**禁止**把这种回包计为成功；一律走指数退避
（5s→10s→20s→40s→60s）重试，退避耗尽才落失败清单。

纪律（逐条对应拆解件 §3 与 §6）：
  * **只加法**：不改既有 E1〜E7 / persons 四端点 / `stamps` / `jobs` / `output/` /
    `exports/fb_*` / `exports/person_*`；
  * **独立库**：本线一律写 `feicui/var/item_ingest.db`（`yinpu.db` 与 `var/person_ingest.db` 一字不碰）；
  * **HTTP 客户端只用 stdlib**（`urllib.request`），不改 `server/requirements.txt`；
  * **礼貌限速**：串行 + 请求间隔 + 抖动；**可断点续跑**（已入库者跳过网络取数）；
  * **不碰 xiai 仓**：就绪包即对外唯一交付缝；**不写 xiai 任何文件、不调云函数**；
  * **不得丢源**：源原文（列表行 ＋ 详情行）一律入 `raw_json`；
  * **失败不静默**：逐条失败写进批次包 `report.json` 的失败清单（**不写进 `items.jsonl`**）。

**繁简口径**：**繁体为正字段、简体入 `*_chs` 副字段**，**不做任何转换改写**（沿拆解件 §3）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("feicui.api.items")

ITEM_SCHEMA_VERSION = "feicui.item_ingest/1"
MANIFEST_SCHEMA_VERSION = 1

# ── item 本体字段（键序即 JSONL 键序；逐项对齐拆解件 §3 映射表）──────────────────────────────
ITEM_FIELDS: list[str] = [
    "source_item_id",     # seqid —— 幂等键（原样字符串）
    "as_book_id",         # asBookId —— 桥接印人侧关联的补零业务号
    "as_id",              # asId
    "book_uri",           # bookUri
    "category",           # bookFl（恒「印谱」）
    "title",              # bookTitleZheng（繁）
    "title_chs",          # bookTitleZhengChs（简）
    "title_other",        # bookTitleQt（繁）
    "title_other_chs",    # bookTitleQtChs（简）
    "volume_count",       # bookCs —— 整数或 null（不设特值）
    "date_text",          # bookCbLsjn —— 纪年原文
    "date_year",          # bookCbGyjn —— 整数或 null（不设特值）
    "publisher",          # bookCbz
    "abstract",           # bookTynr（繁，长文）
    "abstract_chs",       # bookTynrChs（简，长文）
    "abstract_title",     # bookTymc
    "edition",            # bookBbx
    "donor",              # bookDonor（详情独有）
    "has_image",          # hasImage —— 布尔
    "has_annotation",     # hasAnnotation —— 布尔
    "language",           # bookYz
    "misc",               # 低频子对象（bookZzxs/bookCj/bookSk/bookSz/bookPsqk）
    "raw_json",           # 源原文：{"list": 列表行, "detail": 详情行}
]
ITEM_CONTENT_COLS = ITEM_FIELDS  # 内容指纹参与列（排除 batch_id / updated_at）

# ── sidecar `item_creators`（item↔person）字段 ─────────────────────────────────────────────
CREATOR_FIELDS: list[str] = [
    "source_item_id", "creator_type", "creator_role", "creator_relator",
    "creator_name", "person_grbsm", "source_face", "seq",
]
CREATOR_CONTENT_COLS = CREATOR_FIELDS

# 关联来源面（拆解件 §3 末表；Kevin 2026-10-10 策略纠偏后）：
#   * `book_graph`   —— 主源：`graph/book/<seqid>` 的「印人」子项（`creatorType`/`name`/`id`）
#   * `person_graph` —— 既有印人侧 `person_relations(kind='印谱')`（asBookId↔seqid 映射）
#   * `book_detail.creator_list` —— 仅 `--with-detail` 时的补充面（`creatorRole`/`creatorRelator`）
# **非** person 侧被删的 `from`（姓名抽取源字段）概念。
FACE_BOOK_GRAPH = "book_graph"
FACE_PERSON = "person_graph"
FACE_DETAIL = "book_detail.creator_list"

MISC_SOURCE_KEYS = ["bookZzxs", "bookCj", "bookSk", "bookSz", "bookPsqk"]

RATE_LIMIT_MARKER = '{"code":"429", ...}'  # 陷阱形态（字符串 code）

# ── 限速自适应（实测：站点点级窗口限流，detail 端点更敏感，约 150–300s 自愈）──────────────
# 命中外层「全局冷却」后**重试同一本**（不丢本），并把稳态请求间隔抬升（上限 RL_DELAY_MAX）。
RL_COOLDOWN_BASE = 45.0     # 第 1 次冷却 45s，随后 90 / 180 / 180 …
RL_COOLDOWN_MAX = 180.0
RL_MAX_ATTEMPTS = 6         # 单本最多 6 次冷却重试（总等待上限 ≈ 45+90+180×4 ≈ 855s）
RL_DELAY_GROWTH = 1.6       # 每次限速把稳态间隔 ×1.6
RL_DELAY_MAX = 3.0


class FetchError(RuntimeError):
    """单条取数失败（网络 / 非 200 / 信封异常 / 源 code≠200）⇒ 计入失败清单，**不静默跳过**。"""


class RateLimited(FetchError):
    """源侧限速（实测：HTTP **200** + 信封 `code:"429"` + 无 `data`）。礼节信号 ⇒ 退避重试。"""


class ImportPackageError(RuntimeError):
    """生成 xiai 就绪包失败（结构化错误 ⇒ 路由层落 404/409 JSON，**绝不返 HTML**）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ═══════════════════════════════════════════════════════════════════════════ HTTP（stdlib）
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
    # 限速伪装成 200：信封 code＝字符串 "429"（或 msg 含「频密 / 频繁」）
    code = body.get("code")
    if str(code) == "429" or any(h in str(body.get("msg") or "") for h in ("频密", "频繁")):
        raise RateLimited(f"源侧限速 code={code!r} msg={body.get('msg')!r} @ {url}")
    return body


def _http_json(base: str, path: str, *, method: str = "GET", payload: dict | None = None,
               timeout: float = 30.0, retries: int = 5, backoff: float = 5.0) -> dict:
    """带**限速退避**的取数：命中 429 时指数退避重试（5→10→20→40→60 秒，上限 60s）。"""
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json", "User-Agent": "feicui-item-ingest/1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            body = _one_call(url, method=method, data=data, headers=headers, timeout=timeout)
            code = body.get("code")
            if code not in (200, "200"):
                raise FetchError(f"源信封 code={code!r} msg={body.get('msg')!r} @ {url}")
            return body
        except RateLimited as exc:
            last = exc
            if attempt >= retries:
                break
            sleep_s = min(backoff * (2 ** attempt), 60.0)
            log.warning("源侧限速，退避 %.1fs（第 %d/%d 次重试）：%s", sleep_s, attempt + 1, retries, url)
            time.sleep(sleep_s)
    raise last or FetchError(f"取数失败 @ {url}")


def fetch_items_list(base: str, *, page_rows: int = 3000, timeout: float = 30.0) -> tuple[list[dict], int]:
    """列表页：`POST book/list`，`pageRows=3000` 一次取全（源 `total`＝1742）。"""
    body = _http_json(
        base, "/book/list", method="POST",
        payload={
            "pageNum": 1, "pageRows": int(page_rows), "fullText": "",
            "facetBookCbz": "", "yearRange": "", "facetBookDonator": "",
            "orderField": "title", "orderType": "desc",
        },
        timeout=timeout,
    )
    rows = body.get("data") or []
    total = int(body.get("total") or len(rows))
    return list(rows), total


def fetch_item_detail(base: str, seqid: str, *, timeout: float = 30.0, retries: int = 5) -> dict:
    """详情页：`GET book/detail/<seqid>`（**路径参数＝ seqid**；传 asBookId ⇒ 信封 code:404）。

    **实测严限流**（站点按窗口限流，detail 更敏感）⇒ 本线**默认不逐本调用**（降为 best-effort，
    仅 `--with-detail` 开启），只用于补 `creatorRole` / `creatorRelator` / `bookDonor`。
    """
    body = _http_json(base, f"/book/detail/{seqid}", timeout=timeout, retries=retries, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"detail 无 data 字段：{seqid}")
    return data


def fetch_book_graph(base: str, seqid: str, *, timeout: float = 30.0, retries: int = 3) -> dict:
    """印记关联图：`GET graph/book/<seqid>`（**路径参数＝ seqid**；实测健康）。

    实测形态（`graph/book/2214`）：`{"children": [{"name":"印章","children":[…]},
    {"name":"印人","children":[{"creatorType":"辑","name":"吳隱","id":"907234486","type":"印人"}, …]}]}`。
    「印人」子项的 `id` 即 `personGrbsm`。
    """
    body = _http_json(base, f"/graph/book/{seqid}", timeout=timeout, retries=retries, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"graph 无 data 字段：{seqid}")
    return data


# ═══════════════════════════════════════════════════════════════════════════ 归一化（拆解件 §3）
def _text(v: Any) -> str | None:
    """文本：源原文照录；`None` / 空串 ⇒ `None`（不设空串特值）。"""
    if v is None:
        return None
    s = str(v)
    return s if s != "" else None


def _int_or_null(v: Any) -> int | None:
    """整数或 `null`（拆解件 §3：**不设特值**）——非纯整数 / 空 / `0` ⇒ `None`。"""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None
    return n if n != 0 else None


def _bool(v: Any) -> bool | None:
    """布尔：`1/true` ⇒ True；`0/false` ⇒ False；缺 / 异常 ⇒ None。"""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y"):
        return True
    if s in ("0", "false", "no", "n"):
        return False
    return None


def _str_or_none(v: Any) -> str | None:
    return None if v is None else str(v)


def normalize_item(list_row: dict, detail_row: dict | None) -> dict:
    """归一化一条 `items` 记录（拆解件 §3 逐项）。

    取值优先 **详情行**（`book/detail`），缺则退回列表行；`raw_json` 两行都留（**不得丢源**）。
    """
    src = detail_row if isinstance(detail_row, dict) else list_row
    seqid = str(list_row.get("seqid") if list_row.get("seqid") is not None
                else (detail_row or {}).get("seqid") or "").strip()
    misc = {k: _text(src.get(k)) for k in MISC_SOURCE_KEYS}
    return {
        "source_item_id": seqid,
        "as_book_id": _text(src.get("asBookId")),
        "as_id": _text(src.get("asId")),
        "book_uri": _text(src.get("bookUri")),
        "category": _text(src.get("bookFl")),
        "title": _text(src.get("bookTitleZheng")),
        "title_chs": _text(src.get("bookTitleZhengChs")),
        "title_other": _text(src.get("bookTitleQt")),
        "title_other_chs": _text(src.get("bookTitleQtChs")),
        "volume_count": _int_or_null(src.get("bookCs")),
        "date_text": _text(src.get("bookCbLsjn")),
        "date_year": _int_or_null(src.get("bookCbGyjn")),
        "publisher": _text(src.get("bookCbz")),
        "abstract": _text(src.get("bookTynr")),
        "abstract_chs": _text(src.get("bookTynrChs")),
        "abstract_title": _text(src.get("bookTymc")),
        "edition": _text(src.get("bookBbx")),
        "donor": _text(src.get("bookDonor")),
        "has_image": _bool(src.get("hasImage")),
        "has_annotation": _bool(src.get("hasAnnotation")),
        "language": _text(src.get("bookYz")),
        "misc": misc,
        "raw_json": {"list": list_row, "detail": detail_row},
    }


def creators_from_detail(seqid: str, detail_row: dict | None) -> list[dict]:
    """来源①：详情 `creatorList[]`（每项含 `creatorType`/`creatorRole`/`creatorRelator`/`creatorName`/`personGrbsm`）。"""
    out: list[dict] = []
    if not isinstance(detail_row, dict):
        return out
    for seq, c in enumerate(detail_row.get("creatorList") or []):
        if not isinstance(c, dict):
            continue
        out.append({
            "source_item_id": seqid,
            "creator_type": _text(c.get("creatorType")),
            "creator_role": _text(c.get("creatorRole")),
            "creator_relator": _text(c.get("creatorRelator")),
            "creator_name": _text(c.get("creatorName")),
            "person_grbsm": _text(c.get("personGrbsm")),
            "source_face": FACE_DETAIL,
            "seq": seq,
        })
    return out


def creators_from_book_graph(seqid: str, graph_data: dict | None) -> list[dict]:
    """来源①（**主源**）：`graph/book/<seqid>` 的「印人」子项。

    每项取 `creator_type`(＝`creatorType`) / `creator_name`(＝`name`) / `person_grbsm`(＝`id`)；
    `creator_role` / `creator_relator` graph 面无此字段 ⇒ 如实留空（不编造）。
    """
    out: list[dict] = []
    if not isinstance(graph_data, dict):
        return out
    for cat in (graph_data.get("children") or []):
        if str(cat.get("name") or "").strip() != "印人":
            continue
        for seq, c in enumerate(cat.get("children") or []):
            if not isinstance(c, dict):
                continue
            out.append({
                "source_item_id": seqid,
                "creator_type": _text(c.get("creatorType")),
                "creator_role": None,
                "creator_relator": None,
                "creator_name": _text(c.get("name")),
                "person_grbsm": _text(c.get("id")),
                "source_face": FACE_BOOK_GRAPH,
                "seq": seq,
            })
    return out


def creators_from_person_relations(seqid: str, rel_rows: list[dict], person_names: dict[str, str]) -> list[dict]:
    """来源②：既有印人侧关联（`person_relations` 的 `kind='印谱'`）。

    经 **`asBookId ↔ seqid` 映射**接入（**不得重新联网调 graph**）；`person_grbsm` ＝ 印人 `source_person_id`，
    `creator_name` 取该印人姓名（`persons.name_full`）。
    """
    out: list[dict] = []
    for r in rel_rows:
        grbsm = _text(r.get("source_person_id"))
        out.append({
            "source_item_id": seqid,
            "creator_type": _text(r.get("creator_type")),
            "creator_role": None,       # person_relations 无此字段 ⇒ 如实留空（不编造）
            "creator_relator": None,
            "creator_name": _text(person_names.get(str(grbsm))),
            "person_grbsm": grbsm,
            "source_face": FACE_PERSON,
            "seq": int(r.get("seq") or 0),
        })
    return out


def merge_creators(seqid: str, detail_creators: list[dict], person_creators: list[dict]) -> list[dict]:
    """合并各来源并按 **(source_item_id, person_grbsm, creator_type)** 去重（保首见）。

    入参顺序即优先级：**主源（graph）在前**，其后 detail（若开）、person_relations。
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in list(detail_creators) + list(person_creators):
        key = (c.get("source_item_id"), c.get("person_grbsm"), c.get("creator_type"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ═══════════════════════════════════════════════════════════════════════════ 存储（独立库）
SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS item_import_batches (
        batch_id TEXT PRIMARY KEY,
        created_at TEXT, updated_at TEXT, status TEXT,
        source_total INTEGER, fetched INTEGER, items_ok INTEGER, creators_ok INTEGER,
        failed_count INTEGER, elapsed_s REAL, package_dir TEXT, report_path TEXT,
        content_fingerprint TEXT, params_json TEXT, notes TEXT,
        last_run_kind TEXT, last_run_fetched INTEGER, last_run_skipped INTEGER,
        last_run_elapsed_s REAL, last_run_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS items (
        source_item_id TEXT PRIMARY KEY,
        as_book_id TEXT, as_id TEXT, book_uri TEXT, category TEXT,
        title TEXT, title_chs TEXT, title_other TEXT, title_other_chs TEXT,
        volume_count INTEGER, date_text TEXT, date_year INTEGER,
        publisher TEXT, abstract TEXT, abstract_chs TEXT, abstract_title TEXT, edition TEXT,
        donor TEXT, has_image INTEGER, has_annotation INTEGER, language TEXT,
        misc TEXT, raw_json TEXT, batch_id TEXT, updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS item_creators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_item_id TEXT, creator_type TEXT, creator_role TEXT, creator_relator TEXT,
        creator_name TEXT, person_grbsm TEXT, source_face TEXT, seq INTEGER, batch_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_item_creators_item ON item_creators(source_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_item_creators_grbsm ON item_creators(person_grbsm)",
    "CREATE INDEX IF NOT EXISTS idx_items_has_image ON items(has_image)",
    "CREATE INDEX IF NOT EXISTS idx_items_date_year ON items(date_year)",
    "CREATE INDEX IF NOT EXISTS idx_items_as_book_id ON items(as_book_id)",
]

BATCH_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("last_run_kind", "TEXT"),
    ("last_run_fetched", "INTEGER"),
    ("last_run_skipped", "INTEGER"),
    ("last_run_elapsed_s", "REAL"),
    ("last_run_at", "TEXT"),
]


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def ensure_schema(db_path: Path | str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for sql in SCHEMA_SQL:
            conn.execute(sql)
        have = {r[1] for r in conn.execute("PRAGMA table_info(item_import_batches)")}
        for name, decl in BATCH_EXTRA_COLUMNS:
            if name not in have:
                conn.execute(f"ALTER TABLE item_import_batches ADD COLUMN {name} {decl}")
        conn.commit()
    finally:
        conn.close()


def item_exists(db_path: Path | str, source_item_id: str) -> bool:
    conn = _connect(db_path)
    try:
        return conn.execute(
            "SELECT 1 FROM items WHERE source_item_id=?", (source_item_id,)).fetchone() is not None
    finally:
        conn.close()


def _item_columns() -> list[str]:
    return ITEM_FIELDS


def upsert_item(db_path: Path | str, rec: dict, batch_id: str) -> None:
    cols = list(ITEM_FIELDS)
    placeholders = ", ".join("?" for _ in cols)
    update = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "source_item_id")
    vals = []
    for c in cols:
        v = rec.get(c)
        if c in ("misc", "raw_json"):
            v = json.dumps(v, ensure_ascii=False)
        elif c in ("has_image", "has_annotation"):
            v = None if v is None else (1 if v else 0)
        vals.append(v)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"INSERT INTO items ({', '.join(cols)}, batch_id, updated_at) "
            f"VALUES ({placeholders}, ?, ?) "
            f"ON CONFLICT(source_item_id) DO UPDATE SET {update}, batch_id=excluded.batch_id, "
            f"updated_at=excluded.updated_at",
            vals + [batch_id, _now()],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def replace_item_creators(db_path: Path | str, source_item_id: str, creators: list[dict], batch_id: str) -> int:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM item_creators WHERE source_item_id=?", (source_item_id,))
        for c in creators:
            conn.execute(
                "INSERT INTO item_creators (source_item_id, creator_type, creator_role, creator_relator, "
                "creator_name, person_grbsm, source_face, seq, batch_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (c.get("source_item_id"), c.get("creator_type"), c.get("creator_role"),
                 c.get("creator_relator"), c.get("creator_name"), c.get("person_grbsm"),
                 c.get("source_face"), c.get("seq"), batch_id),
            )
        conn.commit()
        return len(creators)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def content_fingerprint(conn: sqlite3.Connection) -> str:
    """items + item_creators 的**内容指纹**（排除 batch_id / updated_at / 自增 id）。"""
    h = hashlib.sha256()
    for row in conn.execute(f"SELECT {', '.join(ITEM_CONTENT_COLS)} FROM items ORDER BY source_item_id"):
        h.update(json.dumps([row[i] for i in range(len(ITEM_CONTENT_COLS))], ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    for row in conn.execute(
        f"SELECT {', '.join(CREATOR_CONTENT_COLS)} FROM item_creators "
        f"ORDER BY source_item_id, source_face, person_grbsm, creator_type, seq"
    ):
        h.update(json.dumps([row[i] for i in range(len(CREATOR_CONTENT_COLS))], ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def db_counts(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        return {
            "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "creators": conn.execute("SELECT COUNT(*) FROM item_creators").fetchone()[0],
            "batches": conn.execute("SELECT COUNT(*) FROM item_import_batches").fetchone()[0],
        }
    finally:
        conn.close()


def batch_db_counts(db_path: Path | str, batch_id: str) -> dict:
    conn = _connect(db_path)
    try:
        return {
            "items": conn.execute("SELECT COUNT(*) FROM items WHERE batch_id=?", (batch_id,)).fetchone()[0],
            "creators": conn.execute(
                "SELECT COUNT(*) FROM item_creators WHERE batch_id=?", (batch_id,)).fetchone()[0],
        }
    finally:
        conn.close()


# ── 批次 ──────────────────────────────────────────────────────────────────────────────────
def next_batch_id(export_root: Path, when: datetime | None = None) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y%m%d")
    prefix = f"item_{stamp}_"
    used = set()
    if Path(export_root).is_dir():
        for p in Path(export_root).iterdir():
            if p.is_dir() and p.name.startswith(prefix):
                used.add(p.name)
    nn = 1
    while f"{prefix}{nn:02d}" in used:
        nn += 1
    return f"{prefix}{nn:02d}"


def get_batch(db_path: Path | str, batch_id: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM item_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def create_batch(db_path: Path | str, batch_id: str, params: dict, source_total: int | None = None) -> None:
    """开批次。**幂等**：同 `batch_id` 重跑**保留** `created_at` 与既有采集计数（绝不归零）。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO item_import_batches "
            "(batch_id, created_at, updated_at, status, source_total, fetched, items_ok, "
            " creators_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint, params_json, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(batch_id) DO UPDATE SET "
            "  updated_at=excluded.updated_at, status='RUNNING', "
            "  source_total=excluded.source_total, params_json=excluded.params_json",
            (batch_id, _now(), _now(), "RUNNING", source_total, 0, 0, 0, 0, 0.0,
             None, None, None, json.dumps(params, ensure_ascii=False), None),
        )
        conn.commit()
    finally:
        conn.close()


BATCH_FINISH_FIELDS = [
    "status", "source_total", "fetched", "items_ok", "creators_ok", "failed_count", "elapsed_s",
    "package_dir", "report_path", "content_fingerprint",
    "last_run_kind", "last_run_fetched", "last_run_skipped", "last_run_elapsed_s", "last_run_at", "notes",
]


def finish_batch(db_path: Path | str, batch_id: str, **kw: Any) -> None:
    fields = ["updated_at"] + BATCH_FINISH_FIELDS
    values = [_now()] + [kw.get(f) for f in BATCH_FINISH_FIELDS]
    conn = _connect(db_path)
    try:
        conn.execute(
            f"UPDATE item_import_batches SET {', '.join(f'{f}=?' for f in fields)} WHERE batch_id=?",
            values + [batch_id],
        )
        conn.commit()
    finally:
        conn.close()


def list_batches(db_path: Path | str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT batch_id, created_at, updated_at, status, source_total, fetched, items_ok, creators_ok, "
            "failed_count, elapsed_s, package_dir, report_path, content_fingerprint, "
            "last_run_kind, last_run_fetched, last_run_skipped, last_run_elapsed_s, last_run_at, notes "
            "FROM item_import_batches ORDER BY batch_id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ 印人侧关联（只读）
def _read_person_context(person_db_path: Path | None) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """**只读**读印人独立库：返回（`as_book_id → [person_relations 行]`, `source_person_id → name_full`）。

    * 只取 `kind='印谱'` 且 `as_book_id` 非空者；**只 SELECT**（`PRAGMA query_only=ON`，源库零写入）；
    * 库不存在 / 读不动 ⇒ 返回空（**不崩**，face② 缺省为空并如实标注）。
    """
    rel_map: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    if person_db_path is None or not Path(person_db_path).is_file():
        return rel_map, names
    try:
        conn = sqlite3.connect(str(person_db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            for r in conn.execute(
                "SELECT source_person_id, kind, ref_id, name, creator_type, as_book_id, seq "
                "FROM person_relations WHERE kind='印谱' AND as_book_id IS NOT NULL AND as_book_id<>'' "
                "ORDER BY as_book_id, source_person_id, seq"
            ):
                d = dict(r)
                rel_map.setdefault(str(d.get("as_book_id")), []).append(d)
            for r in conn.execute("SELECT source_person_id, name_full FROM persons"):
                if r["source_person_id"] is not None:
                    names[str(r["source_person_id"])] = r["name_full"]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 —— 印人库读不动不得挡印谱采集
        log.warning("读取印人独立库失败（face② 缺省为空）：%r", exc)
    return rel_map, names


# ═══════════════════════════════════════════════════════════════════════════ 采集主流程
def run_sync(
    *,
    db_path: Path,
    export_root: Path,
    base: str,
    person_db_path: Path | None = None,
    batch_id: str | None = None,
    resume: bool = True,
    delay: float = 0.5,
    limit: int | None = None,
    timeout: float = 30.0,
    page_rows: int = 3000,
    with_detail: bool = False,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """列表（1 次全量）→ 逐本 `graph/book`（**主源：印人关联**）→（可选 best-effort `detail`）→ 归一化 → 落库 → 就绪包。

    **Kevin 2026-10-10 策略纠偏**：`book/detail` **实测严限流**，故本线**不逐本调 detail** ——
    item 本体全部取自 `book/list`（一次取全，含题名繁简/卷册/成谱纪年/公元/题要长文/出版者/`hasImage`…）；
    item↔person 关联主源改用 **`graph/book/<seqid>`**（逐本 1 请求，实测健康）；
    `detail` 降为 **best-effort（默认关，`with_detail=True` 才开）**，仅补 `creatorRole`/`creatorRelator`/`bookDonor`。

    **可断点续跑**（`resume`：已入库者跳过网络取数）+ **礼貌限速**（`delay` + 抖动 + 限速自适应冷却）。
    `limit` ＝ 本轮**最多新增取数**条数（**分片续跑**口径；`None` ⇒ 不限）。
    """
    ensure_schema(db_path)
    t0 = time.time()

    rel_map, person_names = _read_person_context(person_db_path)

    rows, total = fetch_items_list(base, page_rows=page_rows, timeout=timeout)

    if batch_id is None:
        batch_id = next_batch_id(export_root)
    params = {"resume": resume, "delay": delay, "limit": limit, "page_rows": page_rows}
    prev_row = get_batch(db_path, batch_id) or {}
    create_batch(db_path, batch_id, params, source_total=total)

    failures: list[dict] = []
    detail_unconfirmed: list[dict] = []
    items_ok = 0
    creators_ok = 0
    skipped = 0
    fetched = 0
    detail_requests = 0
    rl_events = 0
    cur_delay = float(delay)

    def _jittered() -> float:
        return max(0.05, cur_delay * (1.0 + random.uniform(-0.25, 0.25)))

    for idx, row in enumerate(rows, start=1):
        seqid = str(row.get("seqid") or "").strip()
        if not seqid:
            failures.append({"source_item_id": None, "stage": "row", "error": "行缺 seqid"})
            continue
        if resume and item_exists(db_path, seqid):
            skipped += 1
            items_ok += 1
            continue
        if limit is not None and fetched >= int(limit):
            # 本轮分片额度已满 ⇒ 停止（未处理者留给下一次 run 续跑）
            break

        # graph/book（**主源：印人关联**）：限速感知重试（命中外层冷却 ⇒ 全局等待后重试同一本，绝不丢本）
        graph: dict | None = None
        rl_attempt = 0
        while True:
            try:
                graph = fetch_book_graph(base, seqid, timeout=timeout, retries=2)
                fetched += 1
                break
            except RateLimited as exc:
                rl_attempt += 1
                rl_events += 1
                if rl_attempt > RL_MAX_ATTEMPTS:
                    failures.append({"source_item_id": seqid, "as_book_id": _text(row.get("asBookId")),
                                     "stage": "graph_rate_limited", "error": str(exc)})
                    graph = None
                    break
                pause = min(RL_COOLDOWN_BASE * (2 ** (rl_attempt - 1)), RL_COOLDOWN_MAX)
                cur_delay = min(cur_delay * RL_DELAY_GROWTH, RL_DELAY_MAX)  # 自适应减速
                log.warning("源侧限速（本本第 %d 次）：全局冷却 %.1fs 后重试 graph %s（稳态间隔→%.2fs）",
                            rl_attempt, pause, seqid, cur_delay)
                time.sleep(pause)
            except FetchError as exc:
                failures.append({"source_item_id": seqid, "as_book_id": _text(row.get("asBookId")),
                                 "stage": "graph", "error": str(exc)})
                graph = None
                break
        if graph is None:
            time.sleep(_jittered())
            continue

        # detail（**best-effort，默认关**）：仅补 creatorRole / creatorRelator / bookDonor；失败不阻塞主交付
        detail: dict | None = None
        if with_detail:
            try:
                detail = fetch_item_detail(base, seqid, timeout=timeout, retries=1)
                detail_requests += 1
            except FetchError as exc:  # 含 RateLimited
                detail_unconfirmed.append({"source_item_id": seqid, "error": str(exc)})

        try:
            rec = normalize_item(row, detail)
            rec["raw_json"]["graph"] = graph  # 不丢源：三道源原文（list / detail / graph）都留
            as_book_id = rec.get("as_book_id")
            graph_creators = creators_from_book_graph(seqid, graph)
            detail_creators = creators_from_detail(seqid, detail) if detail else []
            person_creators = creators_from_person_relations(
                seqid, rel_map.get(str(as_book_id), []), person_names)
            creators = merge_creators(seqid, graph_creators + detail_creators, person_creators)
            upsert_item(db_path, rec, batch_id)
            creators_ok += replace_item_creators(db_path, seqid, creators, batch_id)
            items_ok += 1
        except Exception as exc:  # noqa: BLE001
            failures.append({"source_item_id": seqid, "stage": "store",
                             "error": f"{type(exc).__name__}: {exc}"})

        time.sleep(_jittered())
        if progress and (idx % 25 == 0 or idx == len(rows)):
            progress({"done": idx, "total": len(rows), "items_ok": items_ok,
                      "fetched": fetched, "failed": len(failures)})

    pkg = write_package(db_path=db_path, export_root=export_root, batch_id=batch_id, base=base,
                        source_total=total, params=params, failures=failures,
                        rows_seen=len(rows), person_db_path=person_db_path,
                        with_detail=with_detail, detail_requests=detail_requests,
                        detail_unconfirmed=detail_unconfirmed)

    run_elapsed = round(time.time() - t0, 3)
    is_replay = (len(rows) > 0 and skipped == len(rows) and fetched == 0)
    run_kind = "idempotent_replay" if is_replay else "live_ingest"
    prev_fetched = int(prev_row.get("fetched") or 0)
    prev_elapsed = float(prev_row.get("elapsed_s") or 0.0)
    acq_fetched = prev_fetched if is_replay else prev_fetched + fetched
    acq_elapsed = prev_elapsed if is_replay else prev_elapsed + run_elapsed
    counts = batch_db_counts(db_path, batch_id)
    remaining = total - counts["items"]

    finish_batch(
        db_path, batch_id, status="DONE", source_total=total,
        fetched=acq_fetched, items_ok=counts["items"], creators_ok=counts["creators"],
        failed_count=len(failures), elapsed_s=round(acq_elapsed, 3),
        package_dir=str(pkg["package_dir"]), report_path=str(pkg["report_path"]),
        content_fingerprint=pkg["fingerprint"],
        last_run_kind=run_kind, last_run_fetched=fetched, last_run_skipped=skipped,
        last_run_elapsed_s=run_elapsed, last_run_at=_now(),
        notes=json.dumps({"skipped_resume": skipped, "run_kind": run_kind,
                          "rate_limit_events": rl_events,
                          "counters_source": "db_counts(batch_id) + acquisition_run_cumulative"},
                         ensure_ascii=False),
    )
    return {
        "batch_id": batch_id,
        "run_kind": run_kind,
        "source_total": total,
        "rows_seen": len(rows),
        "fetched_requests": fetched,
        "fetched_requests_cumulative": acq_fetched,
        "skipped_resume": skipped,
        "items_ok": counts["items"],
        "creators_ok": counts["creators"],
        "remaining": remaining,
        "failed_count": len(failures),
        "failures": failures,
        "rate_limit_events": rl_events,
        "detail_requests": detail_requests,
        "detail_unconfirmed_count": len(detail_unconfirmed),
        "package_dir": str(pkg["package_dir"]),
        "report_path": str(pkg["report_path"]),
        "content_fingerprint": pkg["fingerprint"],
        "elapsed_s": round(acq_elapsed, 3),
        "last_run_elapsed_s": run_elapsed,
        "counts": db_counts(db_path),
    }


# ═══════════════════════════════════════════════════════════════════════════ 就绪包
# 字段字典（拆解件 §3 逐项；供 xiai 挑选键面）
FIELD_DICT: list[dict] = [
    {"name": "source_item_id", "source": "seqid", "type": "string", "role": "idempotency_key",
     "note": "内部键（详情路径参数）；幂等键，原样字符串"},
    {"name": "as_book_id", "source": "asBookId", "type": "string",
     "note": "补零业务号（如 0307）——印人侧关联（person_relations.as_book_id）的桥接键"},
    {"name": "as_id", "source": "asId", "type": "string", "note": "上游 id"},
    {"name": "book_uri", "source": "bookUri", "type": "string", "note": "GUID"},
    {"name": "category", "source": "bookFl", "type": "string", "note": "分类（恒「印谱」）"},
    {"name": "title", "source": "bookTitleZheng", "type": "string", "note": "正题名（繁体为正字段）"},
    {"name": "title_chs", "source": "bookTitleZhengChs", "type": "string", "note": "正题名简体副字段"},
    {"name": "title_other", "source": "bookTitleQt", "type": "string", "note": "其他题名（繁）"},
    {"name": "title_other_chs", "source": "bookTitleQtChs", "type": "string", "note": "其他题名（简）"},
    {"name": "volume_count", "source": "bookCs", "type": "integer|null",
     "note": "卷册数；非纯整数 / 空 / 0 ⇒ null（不设特值）"},
    {"name": "date_text", "source": "bookCbLsjn", "type": "string", "note": "成谱纪年原文（原样，如「清宣統二年」）"},
    {"name": "date_year", "source": "bookCbGyjn", "type": "integer|null",
     "note": "成谱公元年；非纯整数 / 空 / 0 ⇒ null（不设特值）"},
    {"name": "publisher", "source": "bookCbz", "type": "string", "note": "出版者"},
    {"name": "abstract", "source": "bookTynr", "type": "string", "note": "题要长文（繁）"},
    {"name": "abstract_chs", "source": "bookTynrChs", "type": "string", "note": "题要长文（简）"},
    {"name": "abstract_title", "source": "bookTymc", "type": "string", "note": "题要名"},
    {"name": "edition", "source": "bookBbx", "type": "string", "note": "版本 / 板框信息"},
    {"name": "donor", "source": "bookDonor", "type": "string",
     "note": "藏家——**详情独有**；detail 严限流默认不逐本调用 ⇒ 默认缺失（见 manifest.detail_policy）"},
    {"name": "has_image", "source": "hasImage", "type": "boolean", "note": "有无影像"},
    {"name": "has_annotation", "source": "hasAnnotation", "type": "boolean", "note": "有无释文"},
    {"name": "language", "source": "bookYz", "type": "string", "note": "语种（chi）"},
    {"name": "misc", "source": "bookZzxs/bookCj/bookSk/bookSz/bookPsqk", "type": "object",
     "note": "低频字段子对象（不散落顶层）：{bookZzxs, bookCj, bookSk, bookSz, bookPsqk}"},
    {"name": "raw_json", "source": "列表行 ＋ 详情行 ＋ 关联图", "type": "object",
     "note": "源原文 {list, detail, graph}（不得丢源）；detail 未取时为 null"},
]

CREATOR_FIELD_DICT: list[dict] = [
    {"name": "source_item_id", "source": "seqid", "type": "string", "note": "回指 items.jsonl 的幂等键"},
    {"name": "creator_type", "source": "graph/book 印人子项.creatorType | person_relations.creator_type | detail.creatorList[].creatorType",
     "type": "string", "note": "责任类型（辑 / 刻印…）"},
    {"name": "creator_role", "source": "detail.creatorList[].creatorRole", "type": "string|null",
     "note": "graph/book 与 person_relations 面无此字段 ⇒ 默认 null（仅 --with-detail 时可能有值）"},
    {"name": "creator_relator", "source": "detail.creatorList[].creatorRelator", "type": "string|null",
     "note": "graph/book 与 person_relations 面无此字段 ⇒ 默认 null（仅 --with-detail 时可能有值）"},
    {"name": "creator_name", "source": "graph/book 印人子项.name | persons.name_full | detail.creatorList[].creatorName",
     "type": "string|null", "note": "责任者姓名"},
    {"name": "person_grbsm", "source": "graph/book 印人子项.id | person_relations.source_person_id | detail.creatorList[].personGrbsm",
     "type": "string|null", "note": "印人侧键"},
    {"name": "source_face", "source": "—", "type": "string",
     "note": f"关联来源面：{FACE_BOOK_GRAPH}（主源） | {FACE_PERSON} | {FACE_DETAIL}（--with-detail）"},
    {"name": "seq", "source": "graph/book 印人子项次序 | person_relations.seq | 详情 creatorList 次序",
     "type": "integer", "note": "组内序号"},
]


def _read_items(conn: sqlite3.Connection, batch_id: str | None = None) -> list[dict]:
    where = " WHERE batch_id=?" if batch_id else ""
    args: tuple = (batch_id,) if batch_id else ()
    rows = conn.execute(
        f"SELECT {', '.join(ITEM_FIELDS)} FROM items{where} ORDER BY source_item_id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["has_image"] = None if d["has_image"] is None else bool(d["has_image"])
            d["has_annotation"] = None if d["has_annotation"] is None else bool(d["has_annotation"])
            d["misc"] = json.loads(d["misc"]) if d.get("misc") else None
            d["raw_json"] = json.loads(d["raw_json"]) if d.get("raw_json") else None
        except (ValueError, TypeError):
            pass
        out.append(d)
    return out


def _read_creators(conn: sqlite3.Connection, batch_id: str | None = None) -> list[dict]:
    where = " WHERE batch_id=?" if batch_id else ""
    args: tuple = (batch_id,) if batch_id else ()
    rows = conn.execute(
        f"SELECT {', '.join(CREATOR_FIELDS)} FROM item_creators{where} "
        f"ORDER BY source_item_id, source_face, person_grbsm, creator_type, seq", args).fetchall()
    return [dict(r) for r in rows]


def _coverage(items: list[dict]) -> dict:
    n = len(items) or 1
    keys = {
        "title": lambda p: bool(p.get("title")),
        "title_chs": lambda p: bool(p.get("title_chs")),
        "abstract": lambda p: bool(p.get("abstract")),
        "volume_count": lambda p: p.get("volume_count") is not None,
        "date_text": lambda p: bool(p.get("date_text")),
        "date_year": lambda p: p.get("date_year") is not None,
        "publisher": lambda p: bool(p.get("publisher")),
        "edition": lambda p: bool(p.get("edition")),
        "donor": lambda p: bool(p.get("donor")),
        "has_image": lambda p: p.get("has_image") is True,
    }
    return {k: f"{sum(1 for p in items if fn(p))}/{len(items)} ({(sum(1 for p in items if fn(p)) / n):.1%})"
            for k, fn in keys.items()}


def write_package(*, db_path: Path, export_root: Path, batch_id: str, base: str, source_total: int,
                  params: dict, failures: list[dict], rows_seen: int,
                  person_db_path: Path | None = None,
                  with_detail: bool = False, detail_requests: int = 0,
                  detail_unconfirmed: list[dict] | None = None) -> dict:
    """产 xiai 就绪包 `exports/item_import_<batch_id>/`：`items.jsonl` ＋ `item_creators.jsonl` ＋ `manifest.json`。

    `items.jsonl` 键面 ＝ 拆解件 §3 的 item 本体（**未裁剪**，由 `manifest.json` 给字段字典供 xiai 挑选）。

    **采集口径偏离登记（拆解件 §10）**：`book/detail` 严限流 ⇒ 降为 best-effort（默认关，`with_detail=True` 才开，
    仅补 `creatorRole` / `creatorRelator` / `bookDonor`）。manifest / report **如实登记** `detail_policy` /
    `detail_requests` / `detail_unconfirmed` 及**因此缺失的三个字段**。
    """
    detail_unconfirmed = list(detail_unconfirmed or [])
    conn = _connect(db_path)
    try:
        items = _read_items(conn, batch_id)
        creators = _read_creators(conn, batch_id)
        fp = content_fingerprint(conn)
    finally:
        conn.close()

    pkg_dir = Path(export_root) / f"item_import_{batch_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    items_path = pkg_dir / "items.jsonl"
    creators_path = pkg_dir / "item_creators.jsonl"
    manifest_path = pkg_dir / "manifest.json"

    with items_path.open("w", encoding="utf-8", newline="\n") as fh:
        for it in items:
            fh.write(json.dumps({k: it.get(k) for k in ITEM_FIELDS}, ensure_ascii=False) + "\n")
    with creators_path.open("w", encoding="utf-8", newline="\n") as fh:
        for c in creators:
            fh.write(json.dumps({k: c.get(k) for k in CREATOR_FIELDS}, ensure_ascii=False) + "\n")

    # ── 幂等键唯一计数 ──
    ids = [it.get("source_item_id") for it in items]
    id_non_null = sum(1 for x in ids if x not in (None, ""))
    id_unique = len({x for x in ids if x not in (None, "")})
    asb_ids = [it.get("as_book_id") for it in items]
    asb_unique = len({x for x in asb_ids if x not in (None, "")})

    # ── 数值负向：volume_count / date_year 不得出现 0 或空串 ──
    vc_bad = [it["source_item_id"] for it in items if it.get("volume_count") == 0 or it.get("volume_count") == ""]
    dy_bad = [it["source_item_id"] for it in items if it.get("date_year") == 0 or it.get("date_year") == ""]

    # ── sidecar 回指 items ──
    item_id_set = {x for x in ids if x not in (None, "")}
    orphan = sorted(str(x) for x in {c.get("source_item_id") for c in creators
                     if c.get("source_item_id") is not None and c.get("source_item_id") not in item_id_set})

    face_counts: dict[str, int] = {}
    for c in creators:
        face = str(c.get("source_face") or "unknown")
        face_counts[face] = face_counts.get(face, 0) + 1
    creators_distinct_items_person = len({c["source_item_id"] for c in creators if c.get("source_face") == FACE_PERSON})

    checks = {
        "rows": len(items),
        "creators_rows": len(creators),
        "idempotency_non_null": id_non_null,
        "idempotency_unique": id_unique,
        "idempotency_total": len(ids),
        "idempotency_all_non_null_and_unique": (id_non_null == len(ids) == id_unique),
        "as_book_id_unique": asb_unique,
        "volume_count_special_zero_or_empty": vc_bad,
        "date_year_special_zero_or_empty": dy_bad,
        "numeric_special_free": (len(vc_bad) == 0 and len(dy_bad) == 0),
        "items_no_bom": _no_bom(items_path),
        "creators_no_bom": _no_bom(creators_path),
        "creators_orphan_source_item_id": orphan,
        "creators_all_backref_items": len(orphan) == 0,
    }

    # ── 采集口径偏离登记（拆解件 §10）：detail 降 best-effort ⇒ 登记的缺失面 ──
    detail_policy = {
        "enabled": bool(with_detail),
        "default": "off",
        "switch": "--with-detail（CLI sync）/ with_detail=true（POST /api/items/sync 请求体）",
        "rationale": ("book/detail 实测严限流（5/10/20/40/60s 退避反复）；逐本 detail 在 1742 本量级不可行。"
                      "item 本体改取 book/list 一次全量，item↔person 关联主源改 graph/book，"
                      "detail 降为 best-effort（拆解件 §10 采集口径偏离）。"),
        "detail_only_fields": ["creatorRole", "creatorRelator", "bookDonor"],
        "missing_when_disabled": {
            "donor": "bookDonor 仅详情独有 ⇒ 默认（detail 关）缺失，items.donor=null",
            "creator_role": "creatorRole 仅详情独有 ⇒ 默认缺失，item_creators.creator_role=null",
            "creator_relator": "creatorRelator 仅详情独有 ⇒ 默认缺失，item_creators.creator_relator=null",
        },
        "detail_requests": int(detail_requests),
        "detail_unconfirmed": len(detail_unconfirmed),
        "detail_unconfirmed_list": detail_unconfirmed,
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "key_face_status": "pending_xiai",
        "form": "F1（manifest + items.jsonl + item_creators.jsonl）",
        "batch_id": batch_id,
        "created_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）「印谱」",
        "source_base": base,
        "source_endpoints": [
            "POST /service_yinpu/book/list  {pageNum:1, pageRows:3000, fullText:'', facetBookCbz:'', "
            "yearRange:'', facetBookDonator:'', orderField:'title', orderType:'desc'}（pageRows:3000 一次取全；"
            "**item 本体全部取自此处**）",
            "GET /service_yinpu/graph/book/<seqid>（路径参数＝ seqid；**item↔person 关联主源**；印人子项给 "
            "creatorType/name/id(＝personGrbsm)）",
            "GET /service_yinpu/book/detail/<seqid>（路径参数＝ seqid；**best-effort，默认关**，仅补 "
            "creatorRole/creatorRelator/bookDonor；严限流 ⇒ 见 detail_policy）",
        ],
        "source_total": source_total,
        "idempotency_key": "source_item_id（＝复旦 seqid）",
        "bridge_key": "as_book_id（＝补零 asBookId，桥接印人侧 person_relations.as_book_id）",
        "files": [
            {"name": "items.jsonl", "rows": len(items), "fields": ITEM_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM"},
            {"name": "item_creators.jsonl", "rows": len(creators), "fields": CREATOR_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM",
             "note": "sidecar（item↔person）：主源＝graph/book 的「印人」子项（source_face='book_graph'）＋"
                     "既有 person_relations(kind='印谱')（经 asBookId↔seqid 映射，源面 'person_graph'，未重新联网）"
                     "＋（仅 --with-detail 时）详情 creatorList（源面 'book_detail.creator_list'）；"
                     "按 (source_item_id, person_grbsm, creator_type) 去重；每行带 source_face"},
            {"name": "manifest.json", "rows": None, "fields": []},
        ],
        "field_dict": FIELD_DICT,
        "field_dict_creators": CREATOR_FIELD_DICT,
        "idempotency": {
            "key": "source_item_id", "non_null": id_non_null, "unique": id_unique, "total": len(ids),
            "all_non_null_and_unique": checks["idempotency_all_non_null_and_unique"],
        },
        "coverage": _coverage(items),
        "creators_summary": {
            "rows": len(creators),
            "by_source_face": face_counts,
            "distinct_items_with_person_graph_face": creators_distinct_items_person,
        },
        "checks": checks,
        "detail_policy": detail_policy,
        "submission": ("提交与审核在玺爱侧；feicui **不写 xiai 任何文件、不调任何云函数**。"
                       "本包为 feicui 自有树内产物，键面待人（xiai）挑选。"),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": ITEM_SCHEMA_VERSION,
        "batch_id": batch_id,
        "generated_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）「印谱」",
        "source_base": base,
        "params": params,
        "rows_seen": rows_seen,
        "idempotency_key": "source_item_id（＝seqid）",
        "counts": {
            "source_total": source_total,
            "items": len(items),
            "creators": len(creators),
            "failed_count": len(failures),
            "field_list_items": ITEM_FIELDS,
            "field_list_creators": CREATOR_FIELDS,
        },
        "content_fingerprint": fp,
        "failures": failures,
        "detail_policy": detail_policy,
        "rate_limit": {
            "trap_form_sanitized": RATE_LIMIT_MARKER,
            "trap_form_note": "HTTP 200；信封 code 是字符串 \"429\"；status 仍可能为 true；只有 data 缺失能暴露失败",
            "handling": "指数退避 5s→10s→20s→40s→60s（上限 60s）后重试；退避耗尽才落失败清单",
        },
    }
    (pkg_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "batch_id": batch_id,
        "package_dir": str(pkg_dir),
        "rows": len(items),
        "creators_rows": len(creators),
        "source_total": source_total,
        "key_face_status": manifest["key_face_status"],
        "idempotency_key": manifest["idempotency_key"],
        "bridge_key": manifest["bridge_key"],
        "idempotency": manifest["idempotency"],
        "coverage": manifest["coverage"],
        "creators_summary": manifest["creators_summary"],
        "checks": checks,
        "files": manifest["files"],
        "field_dict": FIELD_DICT,
        "field_dict_creators": CREATOR_FIELD_DICT,
        "detail_policy": detail_policy,
        "content_fingerprint": fp,
        "generated_at": manifest["created_at"],
        "submission": manifest["submission"],
    }
    return {"package_dir": pkg_dir, "report_path": pkg_dir / "report.json",
            "items_path": items_path, "creators_path": creators_path,
            "manifest_path": manifest_path, "fingerprint": fp, "summary": summary}


def _no_bom(path: Path) -> bool:
    with Path(path).open("rb") as fh:
        return fh.read(3) != b"\xef\xbb\xbf"


# ═══════════════════════════════════════════════════════════════════════════ 查询
def list_items(db_path: Path | str, *, page: int = 1, limit: int = 50, has_image: bool | None = None,
               has_year: bool | None = None, q: str | None = None) -> dict:
    """列表（**纯 offset 分页**）。

    * **分页不变式（钉死）**：`has_more == (page * limit < total)` —— **唯一**判据；
    * **不输出 `next_cursor`**（本端点不支持 cursor；路由侧对未白名单参数一律 400）；
    * `page` 越界 ⇒ `items=[]` 且 `has_more=False`（**绝不**回吐第一页）。
    """
    where: list[str] = []
    args: list[Any] = []
    if has_image is True:
        where.append("has_image = 1")
    elif has_image is False:
        where.append("(has_image = 0 OR has_image IS NULL)")
    if has_year is True:
        where.append("date_year IS NOT NULL")
    elif has_year is False:
        where.append("date_year IS NULL")
    if q:
        where.append("(title LIKE ? OR title_chs LIKE ? OR source_item_id = ?)")
        like = f"%{q}%"
        args += [like, like, q]
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    conn = _connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM items{where_sql}", args).fetchone()[0]
        offset = max(0, (page - 1) * limit)
        rows = conn.execute(
            f"""SELECT source_item_id, as_book_id, category, title, title_chs, volume_count,
                       date_text, date_year, publisher, donor, has_image, has_annotation,
                       (SELECT COUNT(*) FROM item_creators c WHERE c.source_item_id=items.source_item_id) AS creator_count
                FROM items{where_sql}
                ORDER BY as_book_id, source_item_id
                LIMIT ? OFFSET ?""",
            args + [limit, offset],
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["has_image"] = None if d["has_image"] is None else bool(d["has_image"])
            d["has_annotation"] = None if d["has_annotation"] is None else bool(d["has_annotation"])
            items.append(d)
        has_more = (page * limit) < total
        return {"items": items, "page": page, "limit": limit, "total": total, "has_more": has_more}
    finally:
        conn.close()


def list_facets(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        with_img = conn.execute("SELECT COUNT(*) FROM items WHERE has_image=1").fetchone()[0]
        with_year = conn.execute("SELECT COUNT(*) FROM items WHERE date_year IS NOT NULL").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        return {"total": total, "with_image": with_img, "with_year": with_year}
    finally:
        conn.close()


def get_item(db_path: Path | str, seqid: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM items WHERE source_item_id=?", (seqid,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["has_image"] = None if item["has_image"] is None else bool(item["has_image"])
            item["has_annotation"] = None if item["has_annotation"] is None else bool(item["has_annotation"])
            item["misc"] = json.loads(item["misc"]) if item.get("misc") else None
            item["raw_json"] = json.loads(item["raw_json"]) if item.get("raw_json") else None
        except (ValueError, TypeError):
            pass
        cre = conn.execute(
            "SELECT source_item_id, creator_type, creator_role, creator_relator, creator_name, "
            "person_grbsm, source_face, seq FROM item_creators WHERE source_item_id=? "
            "ORDER BY source_face, seq", (seqid,)).fetchall()
        item["creators"] = [dict(r) for r in cre]
        return item
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ CLI
def _cli() -> int:
    import argparse

    from .config import get_settings

    st = get_settings()
    ap = argparse.ArgumentParser(description="feicui 印谱采集线（批 1）")
    ap.add_argument("cmd", choices=["sync", "counts", "fingerprint", "list-count", "package", "anchors"],
                    help="子命令")
    ap.add_argument("--db", default=str(st.items_db_path))
    ap.add_argument("--export-root", default=str(st.items_export_root))
    ap.add_argument("--person-db", default=str(st.person_db_path))
    ap.add_argument("--base", default=st.items_source_base)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--delay", type=float, default=st.items_fetch_delay_s)
    ap.add_argument("--limit", type=int, default=None, help="本轮最多新增取数（分片续跑）")
    ap.add_argument("--with-detail", action="store_true",
                    help="best-effort 逐本 book/detail 补 creatorRole/creatorRelator/bookDonor（默认关；严格限流）")
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
        rows, total = fetch_items_list(args.base, timeout=st.items_fetch_timeout_s)
        print(json.dumps({"total": total, "rows": len(rows)}, ensure_ascii=False))
        return 0
    if args.cmd == "anchors":
        ensure_schema(args.db)
        out = {}
        for sid in ("2214", "3547"):
            out[sid] = get_item(args.db, sid)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "package":
        try:
            pkg = write_package_from_db(args.db, args.export_root, args.batch_id, args.base, args.person_db)
        except ImportPackageError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc)}, ensure_ascii=False))
            return 2
        out = {k: (str(v) if isinstance(v, Path) else v) for k, v in pkg.items() if k != "summary"}
        out["summary"] = pkg.get("summary")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    def _progress(p: dict) -> None:
        print(f"[sync] {p['done']}/{p['total']} ok={p['items_ok']} fetched={p['fetched']} "
              f"failed={p['failed']}", flush=True)

    summary = run_sync(
        db_path=Path(args.db), export_root=Path(args.export_root), base=args.base,
        person_db_path=Path(args.person_db) if args.person_db else None,
        batch_id=args.batch_id, resume=not args.no_resume, delay=args.delay,
        limit=args.limit, timeout=st.items_fetch_timeout_s, with_detail=args.with_detail,
        progress=_progress,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=2))
    print("FAILURES=" + json.dumps(summary["failures"], ensure_ascii=False))
    return 0


def write_package_from_db(db_path, export_root, batch_id=None, base=None, person_db=None) -> dict:
    """从库内重建就绪包（**不联网采集**）——CLI `package` 与 `POST /api/items/package` 共用。

    批次缺省＝库内最新批次；批次不存在 ⇒ `ImportPackageError("BATCH_NOT_FOUND")`；库内无批次 ⇒
    `ImportPackageError("NO_BATCH")`。返回 `write_package` 的完整 dict（含 `summary` 供接口层 / UI 上屏）。
    """
    if base is None:
        from .config import get_settings
        base = get_settings().items_source_base
    ensure_schema(db_path)
    conn = _connect(db_path)
    try:
        if batch_id:
            if conn.execute("SELECT 1 FROM item_import_batches WHERE batch_id=?", (batch_id,)).fetchone() is None:
                raise ImportPackageError("BATCH_NOT_FOUND", f"批次不存在：{batch_id}")
        else:
            r = conn.execute("SELECT batch_id FROM item_import_batches ORDER BY batch_id DESC LIMIT 1").fetchone()
            if r is None:
                raise ImportPackageError("NO_BATCH", "本库尚无任何批次 ⇒ 无法生成就绪包（先跑 POST /api/items/sync）")
            batch_id = r["batch_id"]
        total = conn.execute("SELECT source_total FROM item_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        source_total = total["source_total"] if total else None
    finally:
        conn.close()
    return write_package(db_path=Path(db_path), export_root=Path(export_root), batch_id=str(batch_id),
                         base=base, source_total=int(source_total or 0), params={"rebuilt": True}, failures=[],
                         rows_seen=0, person_db_path=Path(person_db) if person_db else None)


if __name__ == "__main__":
    raise SystemExit(_cli())
