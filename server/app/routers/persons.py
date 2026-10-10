"""`/api/persons/*` 路由（**印人采集线**，批 1）——Kong。

**权威拆解件**：`../docs/person-ingest-draft-v0.1.md` §4.2。端点一律 **additive**（不动 E1〜E7）：

  * `POST /api/persons/sync`   —— 全量拉取 → 逐人 detail+graph → 归一化 → 落独立库 → 产批次包（可断点续跑 / 礼貌限速）
  * `GET  /api/persons`        —— 分页 + 筛选（姓氏首字母 / 国籍 / 有无生卒 / 有无关联）
  * `GET  /api/persons/{grbsm}`—— 单人（详情 + 关联印谱/印章）
  * `GET  /api/persons/batches`—— 批次列表（含回执读数）

纪律：
  * 本文件**不含任何 SQL**，一切读数走 `..persons`；
  * **不把业务真值缓存在接口层**（每次请求现开连接现查现算，沿 §3.2 S-4）；
  * 存储＝**独立库** `feicui/var/person_ingest.db`（`yinpu.db` 一律不碰）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import persons
from ..config import Settings, get_settings

log = logging.getLogger("feicui.api.persons.router")

router = APIRouter(prefix="/api/persons", tags=["persons"])

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 500

# 本端点**支持的查询参数白名单**。任何**未在此列**的查询参数一律 **400 UNSUPPORTED_PARAM**（**绝不静默忽略**）。
# 要点：本端点＝**纯 offset 分页**（`page`/`limit`），**不支持 `cursor`**（游标协议属 E3/E7 的 jobs 线）；
# 旧实现对未白名单参数静默放行（如 `?cursor=abc` 仍 200）—— 属缺陷，已收口。
ALLOWED_QUERY_PARAMS = frozenset({
    "page", "limit", "initial", "nationality", "has_dates", "has_relations", "q", "with_facets",
})

# 「导入包」端点**支持的查询参数白名单**（沿既有惯例：**未白名单参数一律 400**，绝不静默忽略）。
#   * `POST /api/persons/import-package`：仅 `batch_id`（可选，缺省＝库内最新批次）；
#   * `GET  /api/persons/import-packages`：无查询参数。
IMPORT_PACKAGE_QUERY_PARAMS = frozenset({"batch_id"})


def _reject_unsupported_query(request: Request, allowed: frozenset[str]) -> None:
    """未白名单查询参数 ⇒ **400 结构化 JSON**（沿 `list_persons` 既有惯例，绝不静默忽略）。"""
    unsupported = sorted(k for k in request.query_params.keys() if k not in allowed)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSUPPORTED_PARAM",
                "detail": f"不支持的查询参数：{unsupported}。支持的参数：{sorted(allowed)}",
                "unsupported": unsupported,
                "supported": sorted(allowed),
            },
        )


def _settings() -> Settings:
    return get_settings()


def _int_param(raw: str | None, name: str, *, minimum: int | None = None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": f"{name} 必须为整数：{raw!r}"})
    if minimum is not None and value < minimum:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": f"{name} 必须 >= {minimum}：{value}"})
    return value


def _bool_param(raw: str | None, name: str) -> bool | None:
    if raw is None or raw == "":
        return None
    low = str(raw).strip().lower()
    if low in {"1", "true", "yes", "y"}:
        return True
    if low in {"0", "false", "no", "n"}:
        return False
    raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": f"{name} 只能是 true/false：{raw!r}"})


# ── 列表（**须在 `/{grbsm}` 之前声明**，否则 `batches` 会被当作 grbsm 吞掉）──────────
@router.get("")
def list_persons(
    request: Request,
    page: str | None = Query(default=None, description="1-based 页码（默认 1）"),
    limit: str | None = Query(default=None, description=f"页长，默认 {PAGE_LIMIT_DEFAULT}，上限 {PAGE_LIMIT_MAX}"),
    initial: str | None = Query(default=None, description="姓氏首字母过滤（personInitial）"),
    nationality: str | None = Query(default=None, description="国籍过滤（繁或简任一命中）"),
    has_dates: str | None = Query(default=None, description="有无生卒（true/false 可选）"),
    has_relations: str | None = Query(default=None, description="有无关联（true/false 可选）"),
    q: str | None = Query(default=None, description="姓名 / 拼音 / 源 id 模糊查询"),
    with_facets: str | None = Query(default=None, description="是否附分面（默认 true）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`GET /api/persons` —— 分页 + 筛选。信封＝ **5 字段** `{items, page, limit, total, has_more}`（**纯 offset 分页**；
    `next_cursor` 已删、`cursor` 不受支持）；另附 `_facets`（下划线前缀＝诊断口径）与 `_db_path`。

    分页口径（钉死）：
      * **不变式** `has_more == (page * limit < total)`；不再出现「`has_more=true` ＋ `next_cursor=null`」的自相矛盾形态；
      * **未白名单查询参数一律 400**（含 `cursor`）—— 白名单见 `ALLOWED_QUERY_PARAMS`，**绝不静默忽略**；
      * `page` 越界 ⇒ `items=[]` 且 `has_more=False`（**绝不**回吐第一页）。
    """
    # ① 未白名单参数一律显式拒绝（**绝不静默忽略**）：`cursor` 等不在白名单 ⇒ 400 结构化 JSON。
    unsupported = sorted(k for k in request.query_params.keys() if k not in ALLOWED_QUERY_PARAMS)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSUPPORTED_PARAM",
                "detail": (f"不支持的查询参数：{unsupported}。本端点只做 offset 分页（page/limit），"
                           f"**不支持 cursor**；支持的参数：{sorted(ALLOWED_QUERY_PARAMS)}"),
                "unsupported": unsupported,
                "supported": sorted(ALLOWED_QUERY_PARAMS),
            },
        )
    page_i = _int_param(page, "page", minimum=1) or 1
    limit_i = _int_param(limit, "limit", minimum=1) or PAGE_LIMIT_DEFAULT
    if limit_i > PAGE_LIMIT_MAX:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": f"limit 上限 {PAGE_LIMIT_MAX}"})
    persons.ensure_schema(st.person_db_path)
    res = persons.list_persons(
        st.person_db_path, page=page_i, limit=limit_i, initial=initial, nationality=nationality,
        has_dates=_bool_param(has_dates, "has_dates"), has_relations=_bool_param(has_relations, "has_relations"), q=q,
    )
    want_facets = _bool_param(with_facets, "with_facets")
    if want_facets is not False:
        res["_facets"] = persons.list_facets(st.person_db_path)
    res["_db_path"] = str(st.person_db_path)
    return res


@router.get("/batches")
def list_batches(st: Settings = Depends(_settings)) -> dict:
    """`GET /api/persons/batches` —— 批次列表（含回执读数）。"""
    persons.ensure_schema(st.person_db_path)
    items = persons.list_batches(st.person_db_path)
    return {"items": items, "total": len(items), "_db_path": str(st.person_db_path)}


# ── 导入包（**须在 `/{grbsm}` 之前声明**，否则 `import-packages` 会被当作 grbsm 吞掉）──
@router.post("/import-package")
def create_import_package(
    request: Request,
    batch_id: str | None = Query(default=None, description="源批次号（缺省＝库内最新批次）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`POST /api/persons/import-package` —— 生成 **xiai 就绪导入包**（**从 feicui 本库重建，不联网采集**）。

    产物目录 `exports/person_import_<batch_id>/`：主交付 `person_imports.jsonl`（**逐行恰 xiai 现行 21 键**（含
    3 个 extraction 键））＋ sidecar `person_imports_extraction.jsonl`（**派生冗余件，兼容保留**）＋ `manifest.json`。

    * **不写 xiai 任何文件、不调任何云函数**（提交与审核在玺爱侧）；本端点只产 feicui 自有树内产物；
    * 未白名单查询参数 ⇒ **400**；批次不存在 ⇒ **404**（`BATCH_NOT_FOUND`）；库内无批次 ⇒ **404**（`NO_BATCH`）。
    """
    _reject_unsupported_query(request, IMPORT_PACKAGE_QUERY_PARAMS)
    try:
        summary = persons.write_import_package(
            db_path=st.person_db_path, export_root=st.person_export_root, batch_id=(batch_id or None),
        )
    except persons.ImportPackageError as exc:
        status = 404 if exc.code in {"BATCH_NOT_FOUND", "NO_BATCH"} else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "detail": str(exc)})
    log.info("xiai 就绪导入包已生成：batch_id=%s rows=%s dir=%s",
             summary["batch_id"], summary["rows"], summary["package_dir"])
    return summary


@router.get("/import-packages")
def list_import_packages(request: Request, st: Settings = Depends(_settings)) -> dict:
    """`GET /api/persons/import-packages` —— 列出已生成的导入包与其摘要（读各包 `manifest.json`，缺则如实标错）。"""
    _reject_unsupported_query(request, frozenset())
    items = persons.list_import_packages(st.person_export_root)
    return {"items": items, "total": len(items), "_export_root": str(st.person_export_root)}


@router.post("/sync")
def sync(payload: dict | None = None, st: Settings = Depends(_settings)) -> dict:
    """`POST /api/persons/sync` —— 全量拉取 → 归一化 → 落独立库 → 产批次包。

    请求体（均可选）：`{batch_id?, resume?, delay?, limit?, detail?}`。
      * `batch_id` 给出 ⇒ **复用同一批次**（同批次重跑 ⇒ persons 行数与内容指纹不变）；缺省 ⇒ 按当日递增新开；
      * `resume`（默认 true）⇒ 已入库者跳过网络取数（**断点续跑**）；`false` ⇒ 强行重拉全部；
      * `delay`（默认 0.5s）⇒ 串行请求间隔（礼貌限速）；`limit` ⇒ 只取前 N 人（自测用）；
      * `detail`（默认 true）⇒ best-effort 读详情页主数据；失败不阻塞（降级为列表行，记「未取详情确认」）。
    """
    payload = payload or {}
    persons.ensure_schema(st.person_db_path)
    delay = payload.get("delay")
    delay = float(delay) if delay is not None else st.person_fetch_delay_s
    if delay < 0.05:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": "delay 不得 < 0.05s（礼貌限速下限）"})
    limit = payload.get("limit")
    limit = int(limit) if limit is not None else None
    batch_id = payload.get("batch_id") or None
    resume = payload.get("resume")
    resume = True if resume is None else bool(resume)
    detail = payload.get("detail")
    detail = True if detail is None else bool(detail)
    log.info("印人采集开始：batch_id=%s resume=%s delay=%s limit=%s detail=%s", batch_id, resume, delay, limit, detail)
    try:
        summary = persons.run_sync(
            db_path=st.person_db_path, export_root=st.person_export_root, base=st.person_source_base,
            batch_id=batch_id, resume=resume, delay=delay, limit=limit,
            timeout=st.person_fetch_timeout_s, fetch_detail_best_effort=detail,
        )
    except persons.FetchError as exc:
        raise HTTPException(status_code=502, detail={"error": "SOURCE_UNREACHABLE", "detail": str(exc)})
    log.info("印人采集完成：%s", {k: summary[k] for k in ("batch_id", "persons_ok", "relations_ok", "failed_count")})
    return summary


@router.get("/{grbsm}")
def get_person(grbsm: str, st: Settings = Depends(_settings)) -> dict:
    """`GET /api/persons/{grbsm}` —— 单人（详情 + 关联印谱/印章）。不存在 ⇒ 404。"""
    persons.ensure_schema(st.person_db_path)
    rec = persons.get_person(st.person_db_path, grbsm)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "PERSON_NOT_FOUND", "detail": f"印人不存在：{grbsm}"})
    return rec
