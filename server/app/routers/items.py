"""`/api/items/*` 路由（**印谱采集线**，批 1）——Kong。

**权威拆解件**：`../docs/item-ingest-draft-v0.1.md` §4。端点一律 **additive**（不动 E1〜E7 与 persons）：

  * `POST /api/items/sync`    —— 列表 1 次取全 → 逐本 graph/book → 归一化 → 落独立库 → 就绪包（可断点续跑 / 礼貌限速 / 失败清单）
  * `GET  /api/items`         —— 分页 + 筛选（有无影像 / 有无年份 / 题名关键字）
  * `GET  /api/items/{seqid}` —— 单本（详情 + 关联责任者）
  * `GET  /api/items/batches` —— 批次列表（含回执读数）
  * `POST /api/items/package` —— 从本库重建 xiai 就绪包（**不联网**；返回摘要：行数 / 字段字典 / key_face_status …）

纪律：
  * 本文件**不含任何 SQL**，一切读数走 `..items`；
  * **不把业务真值缓存在接口层**（每次请求现开连接现查现算）；
  * 存储＝**独立库** `feicui/var/item_ingest.db`（`yinpu.db` 与 `var/person_ingest.db` 一律不碰）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import items
from ..config import Settings, get_settings

log = logging.getLogger("feicui.api.items.router")

router = APIRouter(prefix="/api/items", tags=["items"])

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 500

# 本端点**支持的查询参数白名单**。任何**未在此列**的查询参数一律 **400 UNSUPPORTED_PARAM**（**绝不静默忽略**）。
# 要点：本端点＝**纯 offset 分页**（`page`/`limit`），**不支持 `cursor`**（游标协议属 E3/E7 的 jobs 线）。
ALLOWED_QUERY_PARAMS = frozenset({"page", "limit", "has_image", "has_year", "q", "with_facets"})


def _reject_unsupported_query(request: Request, allowed: frozenset[str]) -> None:
    """未白名单查询参数 ⇒ **400 结构化 JSON**（绝不静默忽略）。"""
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


# ── 列表（**须在 `/{seqid}` 之前声明**，否则 `batches` 会被当作 seqid 吞掉）──────────────────
@router.get("")
def list_items(
    request: Request,
    page: str | None = Query(default=None, description="1-based 页码（默认 1）"),
    limit: str | None = Query(default=None, description=f"页长，默认 {PAGE_LIMIT_DEFAULT}，上限 {PAGE_LIMIT_MAX}"),
    has_image: str | None = Query(default=None, description="有无影像（true/false 可选）"),
    has_year: str | None = Query(default=None, description="有无公元年（true/false 可选）"),
    q: str | None = Query(default=None, description="题名 / 源 id 模糊查询"),
    with_facets: str | None = Query(default=None, description="是否附分面（默认 true）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`GET /api/items` —— 分页 + 筛选。信封＝ **5 字段** `{items, page, limit, total, has_more}`（**纯 offset 分页**；
    **不出现 `next_cursor`**）；另附 `_facets`（下划线前缀＝诊断口径）与 `_db_path`。

    分页口径（钉死）：
      * **不变式** `has_more == (page * limit < total)`；
      * **未白名单查询参数一律 400**（含 `cursor`）—— 白名单见 `ALLOWED_QUERY_PARAMS`，**绝不静默忽略**；
      * `page` 越界 ⇒ `items=[]` 且 `has_more=False`（**绝不**回吐第一页）。
    """
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
    items.ensure_schema(st.items_db_path)
    res = items.list_items(
        st.items_db_path, page=page_i, limit=limit_i,
        has_image=_bool_param(has_image, "has_image"), has_year=_bool_param(has_year, "has_year"), q=q,
    )
    want_facets = _bool_param(with_facets, "with_facets")
    if want_facets is not False:
        res["_facets"] = items.list_facets(st.items_db_path)
    res["_db_path"] = str(st.items_db_path)
    return res


@router.get("/batches")
def list_batches(st: Settings = Depends(_settings)) -> dict:
    """`GET /api/items/batches` —— 批次列表（含回执读数）。"""
    items.ensure_schema(st.items_db_path)
    rows = items.list_batches(st.items_db_path)
    return {"items": rows, "total": len(rows), "_db_path": str(st.items_db_path)}


# ── 就绪包（**须在 `/{seqid}` 之前声明**，否则 `package` 会被当作 seqid 吞掉）──────────────────
@router.post("/package")
def create_package(
    request: Request,
    batch_id: str | None = Query(default=None, description="源批次号（缺省＝库内最新批次）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`POST /api/items/package` —— 生成 **xiai 就绪包**（**从 feicui 本库重建，不联网采集**）。

    产物目录 `exports/item_import_<batch_id>/`：`items.jsonl`（候选键面，未裁剪）＋ `item_creators.jsonl`
    （sidecar）＋ `manifest.json`（字段字典 / 行数 / 幂等键唯一计数 / 覆盖统计 / `key_face_status:
    pending_xiai` / **`detail_policy`**）。

    * **不写 xiai 任何文件、不调任何云函数**（提交与审核在玺爱侧）；本端点只产 feicui 自有树内产物；
    * 未白名单查询参数 ⇒ **400**；批次不存在 ⇒ **404**（`BATCH_NOT_FOUND`）；库内无批次 ⇒ **404**（`NO_BATCH`）；
    * 响应＝就绪包**摘要**（行数 / 字段字典 / `key_face_status` / `detail_policy` / checks …）。
    """
    _reject_unsupported_query(request, frozenset({"batch_id"}))
    items.ensure_schema(st.items_db_path)
    try:
        pkg = items.write_package_from_db(
            st.items_db_path, st.items_export_root, batch_id=(batch_id or None),
            base=st.items_source_base, person_db=st.person_db_path,
        )
    except items.ImportPackageError as exc:
        status = 404 if exc.code in {"BATCH_NOT_FOUND", "NO_BATCH"} else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "detail": str(exc)})
    summary = pkg["summary"]
    log.info("xiai 就绪包已生成：batch_id=%s rows=%s dir=%s",
             summary["batch_id"], summary["rows"], summary["package_dir"])
    return summary


@router.post("/sync")
def sync(request: Request, payload: dict | None = None, st: Settings = Depends(_settings)) -> dict:
    """`POST /api/items/sync` —— 列表 1 次取全 → 逐本 graph/book → 归一化 → 落独立库 → 就绪包。

    **未白名单查询参数 ⇒ 400**（白名单＝空集：本端点不接受查询参数，一切走请求体）。
    请求体（均可选）：`{batch_id?, resume?, delay?, limit?, with_detail?}`。
      * `batch_id` 给出 ⇒ **复用同一批次**（同批次重跑 ⇒ 幂等）；缺省 ⇒ 按当日递增新开；
      * `resume`（默认 true）⇒ 已入库者跳过网络取数（**断点续跑**）；`false` ⇒ 强行重拉全部；
      * `delay`（默认 0.5s）⇒ 串行请求间隔（礼貌限速）；`limit` ⇒ **本轮最多新增取数**条数（**分片续跑**）；
      * `with_detail`（默认 false）⇒ best-effort 逐本 `book/detail` 补 `creatorRole`/`creatorRelator`/`bookDonor`
        （严限流，失败进清单、不阻塞主交付；manifest 如实登记 `detail_policy`）。
    """
    _reject_unsupported_query(request, frozenset())
    payload = payload or {}
    items.ensure_schema(st.items_db_path)
    delay = payload.get("delay")
    delay = float(delay) if delay is not None else st.items_fetch_delay_s
    if delay < 0.05:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": "delay 不得 < 0.05s（礼貌限速下限）"})
    limit = payload.get("limit")
    limit = int(limit) if limit is not None else None
    batch_id = payload.get("batch_id") or None
    resume = payload.get("resume")
    resume = True if resume is None else bool(resume)
    with_detail = bool(payload.get("with_detail") or False)
    log.info("印谱采集开始：batch_id=%s resume=%s delay=%s limit=%s with_detail=%s",
             batch_id, resume, delay, limit, with_detail)
    try:
        summary = items.run_sync(
            db_path=st.items_db_path, export_root=st.items_export_root, base=st.items_source_base,
            person_db_path=st.person_db_path, batch_id=batch_id, resume=resume, delay=delay,
            limit=limit, timeout=st.items_fetch_timeout_s, with_detail=with_detail,
        )
    except items.FetchError as exc:
        raise HTTPException(status_code=502, detail={"error": "SOURCE_UNREACHABLE", "detail": str(exc)})
    log.info("印谱采集完成：%s", {k: summary[k] for k in ("batch_id", "items_ok", "creators_ok", "failed_count")})
    return summary


@router.get("/{seqid}")
def get_item(seqid: str, st: Settings = Depends(_settings)) -> dict:
    """`GET /api/items/{seqid}` —— 单本（详情 + 关联责任者）。不存在 ⇒ 404。"""
    items.ensure_schema(st.items_db_path)
    rec = items.get_item(st.items_db_path, seqid)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "ITEM_NOT_FOUND", "detail": f"印谱不存在：{seqid}"})
    return rec
