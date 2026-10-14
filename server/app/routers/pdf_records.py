"""`/api/pdf-records/*` 路由（**PDF 资料登记**，output 四总目录落地单）—— Kong · 2026-10-14。

口径真源：`../../docs/output-layout-v0.1.md`。存储＝**独立库** `var/pdf_registry.db`
（真源逻辑 `../pdf_registry.py`；**yinpu.db 一律不碰**）。端点一律 **additive**（不动 E1〜E7
与 persons/items/seals/relations）：

  * `GET   /api/pdf-records`            —— 列表＋筛选（`status` / `q` 模糊命中文件名·作者·备注·ISBN；offset 分页）
  * `PATCH /api/pdf-records/{id}`       —— 人工补填：`dynasty`（**必须 ∈ 15 枚举或 null**）/
                                          `author` / `notes`（缺省键＝不改；写入 updated_at）

纪律：现开连接现查现算（沿 §3.2 S-4，接口层不缓存业务真值）；朝代值域真源＝
xiai `VALUE_DOMAINS.DYNASTY_OPTIONS`，非枚举值 ⇒ **400 DYNASTY_INVALID**（绝不静默放行）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .. import pdf_registry

log = logging.getLogger("feicui.api.pdf_records.router")

router = APIRouter(prefix="/api/pdf-records", tags=["pdf-records"])

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 200

#: `GET /api/pdf-records` 的查询参数白名单（**未白名单参数一律 400**，沿 persons 既有惯例）。
ALLOWED_QUERY_PARAMS = frozenset({"page", "limit", "status", "q"})


class PdfRecordPatch(BaseModel):
    """PATCH 请求体：**缺省键＝不改**；显式 null＝清空（朝代回 NULL/未知）。"""

    model_config = {"extra": "forbid"}

    dynasty: str | None = None
    author: str | None = None
    notes: str | None = None


def _reject_unsupported_query(request: Request, allowed: frozenset[str]) -> None:
    """未白名单查询参数 ⇒ **400 结构化 JSON**（沿 `list_persons` 惯例，绝不静默忽略）。"""
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


@router.get("")
def list_pdf_records(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(PAGE_LIMIT_DEFAULT, ge=1, le=PAGE_LIMIT_MAX),
    status: str | None = Query(None),
    q: str | None = Query(None),
):
    """列表＋筛选。出参：`{total, page, limit, records[{…pdf_records 全列}]}`。"""
    _reject_unsupported_query(request, ALLOWED_QUERY_PARAMS)
    conn = pdf_registry.ensure_db()
    try:
        return pdf_registry.list_records(conn, status=status, q=q, page=page, limit=limit)
    finally:
        conn.close()


@router.patch("/{record_id}")
def patch_pdf_record(record_id: int, body: PdfRecordPatch):
    """人工补填朝代/作者/备注。成功 ⇒ `{record: {…}}`（含刷新后的 updated_at）。"""
    fields = body.model_dump(exclude_unset=True)
    conn = pdf_registry.ensure_db()
    try:
        record = pdf_registry.patch_record(conn, record_id, fields)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "PDF_RECORD_NOT_FOUND", "detail": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "DYNASTY_INVALID" if "dynasty" in str(exc) or "朝代" in str(exc) else "BAD_FIELD",
                    "detail": str(exc),
                    "allowed_dynasties": list(pdf_registry.DYNASTY_OPTIONS)},
        ) from exc
    finally:
        conn.close()
    return {"record": record}
