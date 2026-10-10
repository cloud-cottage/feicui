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

**批次行计数口径（`person_import_batches`，Zang 2026-10-10 裁决）**——**「0」不得在「有数据」的场景冒充「未采集」**：
  * `persons_ok` / `relations_ok` ＝**库内对该批次的实测计数**（`COUNT(*) … WHERE batch_id=?`），
    **不是**单次 run 的循环计数器；任何 run 结束都按库内真值回填（**不得写死**）。
  * `fetched` / `elapsed_s` ＝**采集 run（真实取数 run）的读数**：跨 run **累计**（`+=`）且**幂等重放不改写**
    （重放 `fetched_this_run==0` 且全部 `skipped` ⇒ 视为 `idempotent_replay`，只对 `last_run_*` 计入，不动累计采集计数）。
  * `last_run_kind` / `last_run_fetched` / `last_run_skipped` / `last_run_elapsed_s` / `last_run_at` ＝
    **最近一次 run**（可能是幂等重放）的读数；重放的 `0` 只准出现在这里，**绝不**冒充 `fetched`/`relations_ok`。
  * 判定：`run_kind = idempotent_replay` ⇔ 本轮**无任何网络取数**（`fetched==0`）且**全部行命中 resume 跳过**；否则 `live_ingest`。
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


# ═══════════════════════════════════════════════════════════ xiai 就绪导入包（交接件 §7 交付缝扩展）
# xiai 侧 `submitPersonImport` 的**封闭允许键**——**跨仓契约，只引用不复制**：
#   源 ＝ xiai 仓 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`（**恰 18 键**）。
# **多一个键** ⇒ xiai 判 `INVALID_FIELD`「载荷含未知字段」＋**零写入**
#   ⇒ 主交付 `person_imports.jsonl` **必须严格限定在这 18 键**（键序即本元组序）。
XIAI_PERSON_IMPORT_ALLOWED_KEYS: tuple[str, ...] = (
    "batch_id", "source", "source_person_id", "name_full", "family_name", "given_name",
    "courtesy_names", "art_names", "alias_names", "birth_year", "death_year",
    "native_place", "native_place_chs", "biography", "biography_chs",
    "nationality", "cbdb_id", "source_id",
)
# 三桶（Kevin 2026-10-10 裁定）：主交付**降为 `string[]`（只传 `value`，保持原顺序）**。
IMPORT_THREE_BUCKETS: tuple[str, ...] = ("courtesy_names", "art_names", "alias_names")
# sidecar：extraction 标注（值恒 `'rule-based'`；**不含 `from`**）。
# 这 3 个键**待 xiai 走自己的规范流程扩键面后并入**主交付；扩键前主交付已可正常提交（不阻塞）。
IMPORT_SIDECAR_EXTRACTION_KEYS: tuple[str, ...] = (
    "courtesy_names_extraction", "art_names_extraction", "alias_names_extraction",
)
IMPORT_PACKAGE_SCHEMA_VERSION = 1
# 明确**不得**进主交付的 feicui 侧多余键（供自检 diff；多键 ⇒ xiai 零写入）。
IMPORT_FORBIDDEN_EXTRA_KEYS: tuple[str, ...] = (
    "source_seqid", "source_data_source_id", "name_full_chs", "name_extraction",
    "courtesy_names_chs", "art_names_chs", "alias_names_chs", "birth_death_text",
    "nationality_chs", "nationality_code", "spell", "initial", "flag", "notes", "raw_json",
)


class ImportPackageError(RuntimeError):
    """生成 xiai 就绪导入包失败（结构化错误 ⇒ 路由层落 400/404/409 JSON，**绝不返 HTML**）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
        content_fingerprint TEXT, params_json TEXT, notes TEXT,
        last_run_kind TEXT, last_run_fetched INTEGER, last_run_skipped INTEGER,
        last_run_elapsed_s REAL, last_run_at TEXT
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
        _migrate_batch_columns(conn)
        conn.commit()
    finally:
        conn.close()


# 增量列（老库补列；`CREATE TABLE IF NOT EXISTS` 对已存在的表不生效，须 ALTER）
BATCH_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("last_run_kind", "TEXT"),
    ("last_run_fetched", "INTEGER"),
    ("last_run_skipped", "INTEGER"),
    ("last_run_elapsed_s", "REAL"),
    ("last_run_at", "TEXT"),
]


def _migrate_batch_columns(conn: sqlite3.Connection) -> None:
    """把 `person_import_batches` 的增量列补齐（幂等；只 ADD COLUMN，不改既有列/数据）。"""
    have = {r[1] for r in conn.execute("PRAGMA table_info(person_import_batches)")}
    for name, decl in BATCH_EXTRA_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE person_import_batches ADD COLUMN {name} {decl}")


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


def get_batch(db_path: Path | str, batch_id: str) -> dict | None:
    """读取单批次行（不存在 ⇒ None）。"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM person_import_batches WHERE batch_id=?", (batch_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def batch_db_counts(db_path: Path | str, batch_id: str) -> dict:
    """**库内对该批次的实测计数**（`persons_ok` / `relations_ok` 的唯一来源；不得写死）。"""
    conn = _connect(db_path)
    try:
        return {
            "persons": conn.execute(
                "SELECT COUNT(*) FROM persons WHERE batch_id=?", (batch_id,)).fetchone()[0],
            "relations": conn.execute(
                "SELECT COUNT(*) FROM person_relations WHERE batch_id=?", (batch_id,)).fetchone()[0],
        }
    finally:
        conn.close()


def create_batch(db_path: Path | str, batch_id: str, params: dict, source_total: int | None = None) -> None:
    """开批次。**幂等**：同 `batch_id` 重跑时**保留** `created_at` 与既有采集计数
    （`fetched`/`elapsed_s`/`persons_ok`/`relations_ok`/`last_run_*`）——**绝不**因重跑把计数归零；
    只刷新 `updated_at`/`status`/`source_total`/`params_json`。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO person_import_batches "
            "(batch_id, created_at, updated_at, status, source_total, fetched, persons_ok, "
            " relations_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint, params_json, notes) "
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


# `finish_batch` 可写字段（顺序无关；`updated_at` 恒由本函数盖写）
BATCH_FINISH_FIELDS = [
    "status", "source_total", "fetched", "persons_ok", "relations_ok", "failed_count", "elapsed_s",
    "package_dir", "report_path", "content_fingerprint",
    "last_run_kind", "last_run_fetched", "last_run_skipped", "last_run_elapsed_s", "last_run_at",
    "notes",
]


def finish_batch(db_path: Path | str, batch_id: str, **kw: Any) -> None:
    fields = ["updated_at"] + BATCH_FINISH_FIELDS
    values = [_now()] + [kw.get(f) for f in BATCH_FINISH_FIELDS]
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
            "relations_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint, "
            "last_run_kind, last_run_fetched, last_run_skipped, last_run_elapsed_s, last_run_at, notes "
            "FROM person_import_batches ORDER BY batch_id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def repair_batch_counters(db_path: Path | str, batch_id: str, *, dry_run: bool = False) -> dict:
    """**一次性修复**受损批次行：把被幂等重放覆盖掉的采集计数恢复为真值。

    受损判据（本单成因，**幂等**）：批次行计数与库内**实测**不符
    （典型：库内确有 1650 关联，行内 `relations_ok` 却被重放覆盖成 0）⇒ 判为受损并修复；
    计数已等于库内真值时**原样返回**（不误伤、可反复调用）。

    真值来源（**不写死、不联网重采**）：
      * `persons_ok` / `relations_ok` ← 库内 `COUNT(*) … WHERE batch_id=?`（实测）；
      * `fetched` / `elapsed_s` ← 该批次包 `report.json` 的 `run_provenance.acquisition_run`
        （**采集期当场记录**的读数）：`fetched_requests_cumulative` / `last_shard_summary.elapsed_s`；
        证据缺失 ⇒ 保留原值（**不编值**）；
      * 原（被覆盖的）读数搬入 `last_run_*`（`kind=idempotent_replay`）。
    """
    ensure_schema(db_path)
    row = get_batch(db_path, batch_id)
    if row is None:
        return {"ok": False, "error": "BATCH_NOT_FOUND", "batch_id": batch_id}
    counts = batch_db_counts(db_path, batch_id)
    stored_persons = int(row.get("persons_ok") or 0)
    stored_relations = int(row.get("relations_ok") or 0)
    damaged = (stored_persons != counts["persons"]) or (stored_relations != counts["relations"])
    if not damaged:
        return {"ok": True, "repaired": False, "reason": "COUNTERS_ALREADY_TRUE",
                "batch_id": batch_id, "counts": counts, "row": row}
    if dry_run:
        return {"ok": True, "repaired": False, "dry_run": True, "batch_id": batch_id,
                "counts": counts, "before": row}

    acq_fetched: Any = None
    acq_elapsed: Any = None
    evidence_path: str | None = None
    rp = row.get("report_path")
    if rp and Path(rp).is_file():
        evidence_path = str(rp)
        try:
            rep = json.loads(Path(rp).read_text(encoding="utf-8"))
            acq = (rep.get("run_provenance") or {}).get("acquisition_run") or {}
            acq_fetched = acq.get("fetched_requests_cumulative")
            acq_elapsed = (acq.get("last_shard_summary") or {}).get("elapsed_s")
        except Exception as exc:  # 证据读不动 ⇒ 不编值
            log.warning("修复 %s：读取批次包采集证据失败 %s：%s", batch_id, rp, exc)

    new_fetched = acq_fetched if acq_fetched is not None else row.get("fetched")
    new_elapsed = acq_elapsed if acq_elapsed is not None else row.get("elapsed_s")
    old_notes = {}
    try:
        old_notes = json.loads(row.get("notes") or "{}")
    except Exception:
        old_notes = {}
    new_notes = {
        "skipped_resume": old_notes.get("skipped_resume"),
        "detail_unconfirmed": old_notes.get("detail_unconfirmed"),
        "run_kind": "idempotent_replay",
        "repair": {
            "at": _now(),
            "reason": "批次行计数被幂等重放覆盖（relations_ok 显示 0 冒充「无关联」）",
            "restored": {"persons_ok": counts["persons"], "relations_ok": counts["relations"],
                         "fetched": new_fetched, "elapsed_s": new_elapsed},
            "fetched_elapsed_evidence": evidence_path,
            "note": "采集计数＝库内实测；fetched/elapsed 取自批次包 run_provenance.acquisition_run（采集期记录）；"
                    "原被覆盖的重放读数已移至 last_run_*",
        },
    }
    finish_batch(
        db_path, batch_id, status=row.get("status"),
        source_total=row.get("source_total"),
        fetched=new_fetched, persons_ok=counts["persons"], relations_ok=counts["relations"],
        failed_count=row.get("failed_count"), elapsed_s=new_elapsed,
        package_dir=row.get("package_dir"), report_path=row.get("report_path"),
        content_fingerprint=row.get("content_fingerprint"),
        last_run_kind="idempotent_replay",
        last_run_fetched=row.get("fetched"), last_run_skipped=old_notes.get("skipped_resume"),
        last_run_elapsed_s=row.get("elapsed_s"), last_run_at=row.get("updated_at"),
        notes=json.dumps(new_notes, ensure_ascii=False),
    )
    after = get_batch(db_path, batch_id)
    return {"ok": True, "repaired": True, "batch_id": batch_id,
            "counts": counts, "before": row, "after": after}


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
    # 采集计数在重跑时须**保留**（create_batch 幂等、不归零）⇒ 先取既有一行留底。
    prev_row = get_batch(db_path, batch_id) or {}
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

    run_elapsed = round(time.time() - t0, 3)
    # ── 批次行计数（Zang 2026-10-10 裁决）：库内真值 + 采集 run 累计；幂等重放**不得**归零采集计数 ──
    # * persons_ok / relations_ok ← 库内对该批次的**实测计数**（不得写死）；
    # * fetched / elapsed_s ← **采集 run 累计**（`prev + 本轮`）；本轮为幂等重放（无网络取数且全部跳过）时**原样保留**；
    # * last_run_* ← 最近一次 run 的读数（重放的 0 只准落在这里）。
    is_replay = (len(rows) > 0 and skipped == len(rows) and fetched == 0)
    run_kind = "idempotent_replay" if is_replay else "live_ingest"
    prev_fetched = int(prev_row.get("fetched") or 0)
    prev_elapsed = float(prev_row.get("elapsed_s") or 0.0)
    acq_fetched = prev_fetched if is_replay else prev_fetched + fetched
    acq_elapsed = prev_elapsed if is_replay else prev_elapsed + run_elapsed
    counts = batch_db_counts(db_path, batch_id)

    finish_batch(
        db_path, batch_id, status="DONE", source_total=total,
        fetched=acq_fetched, persons_ok=counts["persons"], relations_ok=counts["relations"],
        failed_count=len(failures), elapsed_s=round(acq_elapsed, 3),
        package_dir=str(pkg["package_dir"]), report_path=str(pkg["report_path"]),
        content_fingerprint=fingerprint,
        last_run_kind=run_kind, last_run_fetched=fetched, last_run_skipped=skipped,
        last_run_elapsed_s=run_elapsed, last_run_at=_now(),
        notes=json.dumps({"skipped_resume": skipped, "detail_unconfirmed": len(detail_unconfirmed),
                          "run_kind": run_kind,
                          "counters_source": "db_counts(batch_id) + acquisition_run_cumulative"},
                         ensure_ascii=False),
    )
    return {
        "batch_id": batch_id,
        "run_kind": run_kind,
        "source_total": total,
        "rows_seen": len(rows),
        "fetched_requests": fetched,                 # 本轮（单次 run）网络请求数
        "fetched_requests_cumulative": acq_fetched,  # 采集 run 累计（重放不改写）
        "skipped_resume": skipped,
        "persons_ok": counts["persons"],             # 库内真值（不得写死）
        "relations_ok": counts["relations"],         # 库内真值（不得写死）
        "detail_confirmed": detail_confirmed,
        "detail_unconfirmed_count": len(detail_unconfirmed),
        "detail_skipped_circuit": detail_skipped_circuit,
        "failed_count": len(failures),
        "failures": failures,
        "detail_unconfirmed": detail_unconfirmed,
        "package_dir": str(pkg["package_dir"]),
        "report_path": str(pkg["report_path"]),
        "content_fingerprint": fingerprint,
        "elapsed_s": round(acq_elapsed, 3),          # 采集 run 累计墙钟
        "last_run_elapsed_s": run_elapsed,           # 本轮墙钟
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


# ═══════════════════════════════════════════════════════════ xiai 就绪导入包（§7）
def _import_bucket_values(items: Any) -> list[str]:
    """库内三桶（`list[{value,kind,extraction,from}]`）→ `string[]`（**只 `value`、保持原顺序**）。

    只收**非空字符串**元素（坏值 / `None` / 空串跳过）；幂等：真数组 / JSON 数组文本都吃。
    """
    out: list[str] = []
    for item in decode_name_list(items):
        v = item.get("value") if isinstance(item, dict) else item
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def build_import_payload(person: dict) -> tuple[dict, dict]:
    """单条 feicui person 行 →（主交付 18 键行, extraction sidecar 行）。

    * 主交付**逐键严格取自 `XIAI_PERSON_IMPORT_ALLOWED_KEYS`**（键序＝该元组序；**绝不带多键**）；
    * 三桶降为 `string[]`（只 `value`）；`birth_year` / `death_year` 整数或 `null`；
    * sidecar 三数组与对应值数组**等长**、元素恒 `'rule-based'`（**不含 `from`**）。
    """
    row: dict[str, Any] = {}
    buckets: dict[str, list[str]] = {}
    for k in XIAI_PERSON_IMPORT_ALLOWED_KEYS:
        if k in IMPORT_THREE_BUCKETS:
            vals = _import_bucket_values(person.get(k))
            buckets[k] = vals
            row[k] = vals
        elif k in ("birth_year", "death_year"):
            v = person.get(k)
            if v is None or v == "":
                row[k] = None
            else:
                try:
                    row[k] = int(v)
                except (TypeError, ValueError):
                    row[k] = None
        else:
            row[k] = person.get(k)
    side: dict[str, Any] = {"source_person_id": row.get("source_person_id")}
    for bucket, side_key in zip(IMPORT_THREE_BUCKETS, IMPORT_SIDECAR_EXTRACTION_KEYS):
        side[side_key] = [EXTRACTION for _ in buckets[bucket]]
    return row, side


def _no_bom(path: Path) -> bool:
    """文件是否**无 BOM**（读前 3 字节与 UTF-8 BOM 比对；**不**用 md5）。"""
    with Path(path).open("rb") as fh:
        return fh.read(3) != b"\xef\xbb\xbf"


def list_import_packages(export_root: Path | str) -> list[dict]:
    """扫描 `exports/person_import_*/` 逐个读 `manifest.json` 出**摘要**（缺 manifest ⇒ 如实标错）。"""
    root = Path(export_root)
    out: list[dict] = []
    if not root.is_dir():
        return out
    for p in sorted(root.glob("person_import_*"), reverse=True):
        if not p.is_dir():
            continue
        summary: dict[str, Any] = {"package_dir": str(p), "dir_name": p.name, "manifest_ok": False}
        man = p / "manifest.json"
        if man.is_file():
            try:
                m = json.loads(man.read_text(encoding="utf-8"))
                summary.update({
                    "manifest_ok": True,
                    "schema_version": m.get("schema_version"),
                    "source_batch": m.get("source_batch"),
                    "generated_at": m.get("generated_at"),
                    "rows": m.get("rows"),
                    "key_face_diff": m.get("key_face_diff"),
                    "idempotency": m.get("idempotency"),
                    "checks": m.get("checks"),
                    "sidecar_pending_keys": (m.get("sidecar") or {}).get("pending_xiai_keys"),
                })
            except Exception as exc:  # 坏 manifest ⇒ 如实报错，不猜
                summary["error"] = f"manifest 读取失败：{type(exc).__name__}: {exc}"
        else:
            summary["error"] = "缺 manifest.json"
        out.append(summary)
    return out


def write_import_package(*, db_path: Path, export_root: Path, batch_id: str | None = None) -> dict:
    """**从 feicui 本库重建** xiai 就绪导入包（**不联网采集**；只加法，不动 E1〜E7 与既有批次包）。

    产物目录 `exports/person_import_<batch_id>/`：
      * `person_imports.jsonl`（**主交付**，逐行恰 xiai 现行 **18 键**，可直接提交）；
      * `person_imports_extraction.jsonl`（**sidecar**，extraction 标注；不含 `from`）；
      * `manifest.json`（键面 diff / 幂等键计数 / sidecar 说明 / 校验读数）。

    `batch_id` 缺省 ⇒ 取库内**最新批次**。错误一律 `ImportPackageError`（结构化）。
    """
    ensure_schema(db_path)
    conn = _connect(db_path)
    try:
        if batch_id:
            if conn.execute("SELECT 1 FROM person_import_batches WHERE batch_id=?",
                            (batch_id,)).fetchone() is None:
                raise ImportPackageError("BATCH_NOT_FOUND", f"批次不存在：{batch_id}")
        else:
            r = conn.execute(
                "SELECT batch_id FROM person_import_batches ORDER BY batch_id DESC LIMIT 1").fetchone()
            if r is None:
                raise ImportPackageError("NO_BATCH", "本库尚无任何批次 ⇒ 无法生成导入包（先跑 POST /api/persons/sync）")
            batch_id = r["batch_id"]
        bid: str = str(batch_id)  # 至此必为非空字符串（已校验 / 已取库内最新）
        src_batch = get_batch(db_path, bid) or {}
        rows = conn.execute(
            f"SELECT {', '.join(PERSON_FIELDS)}, batch_id FROM persons "
            f"WHERE batch_id=? ORDER BY source_person_id", (bid,)).fetchall()
        persons_rows: list[dict] = []
        for r in rows:
            d = dict(r)
            for col in NAME_LIST_FIELDS:
                d[col] = decode_name_list(d.get(col))
            persons_rows.append(d)
    finally:
        conn.close()

    main_rows: list[dict] = []
    side_rows: list[dict] = []
    for p in persons_rows:
        m, s = build_import_payload(p)
        m["batch_id"] = p.get("batch_id") or batch_id  # 18 键之一：源批次号（必填）
        main_rows.append(m)
        side_rows.append(s)

    pkg_dir = Path(export_root) / f"person_import_{batch_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    main_path = pkg_dir / "person_imports.jsonl"
    side_path = pkg_dir / "person_imports_extraction.jsonl"
    manifest_path = pkg_dir / "manifest.json"

    # 主交付：**一行一对象、UTF-8、无 BOM、键序＝18 键元组序**（外部逐行解析）
    with main_path.open("w", encoding="utf-8", newline="\n") as fh:
        for m in main_rows:
            fh.write(json.dumps({k: m.get(k) for k in XIAI_PERSON_IMPORT_ALLOWED_KEYS},
                                ensure_ascii=False) + "\n")
    with side_path.open("w", encoding="utf-8", newline="\n") as fh:
        for s in side_rows:
            fh.write(json.dumps({k: s.get(k) for k in ("source_person_id",) + IMPORT_SIDECAR_EXTRACTION_KEYS},
                                ensure_ascii=False) + "\n")

    # ── 键面 diff（**多余键必须为 0**）：从**实际写入行**并集算，非写死 ──
    union_keys = sorted({k for m in main_rows for k in m.keys()})
    extra_keys = sorted(k for k in union_keys if k not in XIAI_PERSON_IMPORT_ALLOWED_KEYS)
    missing_keys = sorted(k for k in XIAI_PERSON_IMPORT_ALLOWED_KEYS if k not in union_keys)
    # 幂等键（source_person_id）非空且唯一
    ids = [m.get("source_person_id") for m in main_rows]
    id_non_null = sum(1 for x in ids if x not in (None, ""))
    id_unique = len({x for x in ids if x not in (None, "")})
    # 三桶均 list[str]
    buckets_all_str = all(
        isinstance(m.get(k), list) and all(isinstance(x, str) for x in (m.get(k) or []))
        for m in main_rows for k in IMPORT_THREE_BUCKETS
    )
    # 无 BOM
    main_no_bom = _no_bom(main_path)
    side_no_bom = _no_bom(side_path)

    checks = {
        "rows": len(main_rows),
        "key_face_diff_zero": (len(extra_keys) == 0 and len(missing_keys) == 0),
        "extra_keys": extra_keys,
        "missing_keys": missing_keys,
        "idempotency_non_null": id_non_null,
        "idempotency_unique": id_unique,
        "idempotency_total": len(ids),
        "idempotency_all_non_null_and_unique": (id_non_null == len(ids) == id_unique),
        "three_buckets_all_string_arrays": buckets_all_str,
        "main_no_bom": main_no_bom,
        "sidecar_no_bom": side_no_bom,
        "sidecar_lengths_match": all(
            len(s.get(sk) or []) == len(m.get(b) or [])
            for m, s in zip(main_rows, side_rows)
            for b, sk in zip(IMPORT_THREE_BUCKETS, IMPORT_SIDECAR_EXTRACTION_KEYS)
        ),
        "sidecar_elements_all_rule_based": all(
            all(x == EXTRACTION for x in (s.get(sk) or []))
            for s in side_rows for sk in IMPORT_SIDECAR_EXTRACTION_KEYS
        ),
    }

    manifest = {
        "schema_version": IMPORT_PACKAGE_SCHEMA_VERSION,
        "form": "xiai-person-import-package（F-import：主交付 18 键 + extraction sidecar + manifest）",
        "source_batch": batch_id,
        "source_batch_meta": {
            "persons_ok": src_batch.get("persons_ok"),
            "relations_ok": src_batch.get("relations_ok"),
            "status": src_batch.get("status"),
            "content_fingerprint": src_batch.get("content_fingerprint"),
        },
        "generated_at": _now(),
        "generated_from": "feicui 本库重建（`var/person_ingest.db::persons WHERE batch_id=?`；**不联网采集**）",
        "rows": len(main_rows),
        "idempotency_key": "source_person_id（＝复旦 personGrbsm）",
        "files": [
            {"name": "person_imports.jsonl", "rows": len(main_rows),
             "keys": list(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
             "format": "JSONL，一行一对象，UTF-8，无 BOM，键序＝xiai 18 键序"},
            {"name": "person_imports_extraction.jsonl", "rows": len(side_rows),
             "keys": ["source_person_id"] + list(IMPORT_SIDECAR_EXTRACTION_KEYS),
             "format": "JSONL，一行一对象，UTF-8，无 BOM"},
            {"name": "manifest.json", "rows": None, "keys": []},
        ],
        "xiai_contract": {
            "allowed_keys_source": ("xiai 仓 `cloudfunctions/xiai-user-token/lib/ops.js::PERSON_IMPORT_ALLOWED_KEYS`"
                                    "（跨仓契约，**只引用不复制**）"),
            "allowed_keys": list(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
            "allowed_keys_count": len(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
            "violation": "多一个键 ⇒ xiai 判 INVALID_FIELD「载荷含未知字段」＋零写入",
        },
        "key_face_diff": {
            "main_delivery_keys": list(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
            "extra_keys": extra_keys,
            "missing_keys": missing_keys,
            "extra_count": len(extra_keys),
            "forbidden_extra_present": [k for k in IMPORT_FORBIDDEN_EXTRA_KEYS if k in union_keys],
        },
        "idempotency": {
            "key": "source_person_id",
            "non_null": id_non_null,
            "unique": id_unique,
            "total": len(ids),
            "all_non_null_and_unique": checks["idempotency_all_non_null_and_unique"],
        },
        "three_buckets": {
            "keys": list(IMPORT_THREE_BUCKETS),
            "form": "string[]（只 value，保持原顺序）",
        },
        "sidecar": {
            "file": "person_imports_extraction.jsonl",
            "keys": list(IMPORT_SIDECAR_EXTRACTION_KEYS),
            "note": "extraction 标注（值恒 'rule-based'）；与对应值数组**等长**；**不含 from**。",
            "pending_xiai_keys": list(IMPORT_SIDECAR_EXTRACTION_KEYS),
            "pending_note": ("待 xiai 走自己的规范流程扩这 3 个 extraction 键后并入主交付；"
                             "扩键前 `person_imports.jsonl` 已可正常提交（**不阻塞**）。"),
        },
        "submission": ("提交与审核在玺爱侧（本包只读消费）；feicui **不写 xiai 任何文件、不调任何云函数**。"
                       "导入先落 xiai_person_imports（PENDING），管理员批量采纳后方成正式印人。"),
        "checks": checks,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "batch_id": batch_id,
        "package_dir": str(pkg_dir),
        "files": {
            "person_imports": str(main_path),
            "person_imports_extraction": str(side_path),
            "manifest": str(manifest_path),
        },
        "rows": len(main_rows),
        "key_face": {
            "delivery_keys": list(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
            "extra_keys": extra_keys,
            "missing_keys": missing_keys,
            "extra_count": len(extra_keys),
            "xiai_allowed_keys_count": len(XIAI_PERSON_IMPORT_ALLOWED_KEYS),
        },
        "idempotency": manifest["idempotency"],
        "checks": checks,
        "sidecar": manifest["sidecar"],
        "submission": manifest["submission"],
        "generated_at": manifest["generated_at"],
    }


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
    ap.add_argument("cmd", choices=["sync", "counts", "fingerprint", "list-count", "repair-batch",
                                    "import-package"],
                    help="子命令")
    ap.add_argument("--db", default=str(st.person_db_path))
    ap.add_argument("--export-root", default=str(st.person_export_root))
    ap.add_argument("--base", default=st.person_source_base)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--no-detail", action="store_true", help="关闭 best-effort detail（纯列表行 + graph）")
    ap.add_argument("--delay", type=float, default=st.person_fetch_delay_s)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="repair-batch：只算不改")
    args = ap.parse_args()

    if args.cmd == "counts":
        ensure_schema(args.db)
        print(json.dumps(db_counts(args.db), ensure_ascii=False))
        return 0
    if args.cmd == "repair-batch":
        ensure_schema(args.db)
        if not args.batch_id:
            print(json.dumps({"ok": False, "error": "MISSING_BATCH_ID",
                              "detail": "repair-batch 需 --batch-id"}, ensure_ascii=False))
            return 2
        print(json.dumps(repair_batch_counters(args.db, args.batch_id, dry_run=args.dry_run),
                         ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "import-package":
        # 从库内重建 xiai 就绪导入包（**不联网采集**）；产物落 exports/person_import_<batch_id>/
        try:
            summary = write_import_package(db_path=Path(args.db), export_root=Path(args.export_root),
                                           batch_id=args.batch_id)
        except ImportPackageError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps(summary, ensure_ascii=False, indent=2))
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
