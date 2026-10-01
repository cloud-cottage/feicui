"""Pydantic 请求 / 响应模型 —— 形状一律照 `../docs/feicui.spec.md` v1.1 §3。

纪律（§3.1 表下注 + §3.2 S-3）：**形状即契约**。E1 / E2 / E5 的字段名、字段数、可空性
逐字对齐规范；不多造字段、不省略字段（`failed_pages` 空时必须是 `[]`，不得为 `null` / 缺失）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- E1 ----------
class JobCreateRequest(BaseModel):
    """§3.1 E1 请求：`{pdf_path, page_range?:[from,to], chunk_size?, rerun?}`"""

    pdf_path: str = Field(..., min_length=1, description="PDF 路径（绝对或相对 feicui/）")
    page_range: tuple[int, int] | None = Field(default=None, description="1-based 闭区间 [from,to]")
    chunk_size: int | None = Field(default=None, ge=1, description="chunk＝页区间（§2.1）")
    rerun: bool | None = Field(default=None, description="重跑语义（§2.1 / §2.4）")


class JobCreateResponse(BaseModel):
    """§3.1 E1 201：`{job_id, state, total_pages, created_at}`"""

    job_id: str
    state: str
    total_pages: int
    created_at: str


class JobConflictResponse(BaseModel):
    """409 响应体（规范只写「409 + 既有 job_id」，字段由本层定并登记为规范缺口）。"""

    error: str = "ACTIVE_JOB_EXISTS"
    detail: str
    job_id: str
    state: str
    total_pages: int
    created_at: str


class ErrorResponse(BaseModel):
    """400 / 422 兜底形状（S-6 的错误码族，不新增码）。"""

    error: str
    detail: str
    missing: list[str] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)


# ---------- E2 ----------
class E2Cursor(BaseModel):
    chunk_lo: int | None
    chunk_hi: int | None


class E2Counters(BaseModel):
    detected: int
    inserted: int
    updated: int
    skipped: int
    ocr_empty: int


class JobProgressResponse(BaseModel):
    """§3.1 E2：逐字段；全部数值**由库内复算**（§3.2 S-1）。"""

    job_id: str
    state: str
    total_pages: int
    done_pages: int
    failed_pages: list[int]
    cursor: E2Cursor
    counters: E2Counters
    started_at: str | None
    updated_at: str


# ---------- E5 ----------
class MissingItem(BaseModel):
    pdf_name: str
    page: int
    idx: int
    img_path: str | None = None
    reason: str


class MissingResponse(BaseModel):
    """§3.1 E5：`{kind, count, items[...]}`"""

    kind: Literal["image", "text"]
    count: int
    items: list[MissingItem]


# =========================================================================== 阶段 1b-ii
# E3 / E4 / E7 的形状一律照 `../docs/feicui.spec.md` v1.2 §3.1 表 + §3.2 S-3（6 字段信封）+ §3.8。
# 形状纪律：**6 字段一个不多一个不少**（`items, page, limit, total, has_more, next_cursor`），
# `items` 必须是**实体数组**（不得裸数组）、`has_more=false` 时 `next_cursor` 必须为 `null`。
PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 500


class E3StampItem(BaseModel):
    """E3 单条记录。

    **形状依据**：规范 §3.1 E3 只定「`items[]` 为实体数组」，**未定义 item 字段集**（缺口已登记）；
    本层取**与 §9.3 已对齐的记录对象**＝`export.py::build_record` 的形态（平台字段名为顶层键 +
    `assets[]` + feicui 专有信息收在 `feicui` 子对象），逐条带 `feicui.missingRequired`
    （AC-08 的「或明确给出 missing_required」）。**不自造平台字段名**（§3.3 纪律）。

    因此本模型**不做字段封闭**（`extra="allow"`）——形状真源是 `seals.record_json` / `records.py`。
    """

    model_config = ConfigDict(extra="allow")


class PagedEnvelope(BaseModel):
    """§3.2 S-3 的 **6 字段分页信封**（E3 / E7 同款）。

    字段冻结：`items[] page limit total has_more next_cursor`（↔ 平台 5 字段信封的差异逐项见 §3.1 表下注）。
    """

    items: list[Any]
    page: int = Field(..., ge=1, description="1-based 页码")
    limit: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
    has_more: bool
    next_cursor: str | None = None


class E7JobItem(BaseModel):
    """§3.1 E7 `items[]` 字段集（**形状草案**，本层按 §0.4 回填；见 REPORT_1b-ii「规范缺口」）。"""

    job_id: str
    pdf_name: str
    pdf_path: str
    state: str
    total_pages: int
    done_pages: int
    failed_pages_count: int
    created_at: str
    updated_at: str


class E7JobsResponse(PagedEnvelope):
    items: list[E7JobItem]


# ---------- E4 ----------
class E4ExportRequest(BaseModel):
    """§3.1 E4 请求：`{batch_id?, book_code?, dry_run?}`（**三项语义规范均未定义**，见 REPORT_1b-ii 缺口）。"""

    batch_id: str | None = Field(default=None, description="规范未定义其语义 ⇒ 非空即 400，不臆造批次号")
    book_code: str | None = Field(default=None, description="可选：与 config/book_codes.json 的本书记录校验")
    dry_run: bool | None = Field(default=None, description="规范未定义 ⇒ export.py 无 dry-run 模式，true 即 400")


class E4ExportCounts(BaseModel):
    """E4 `counts`：`{formal, draft, rejected}`（取自批包 `report.json` 的 `counts.feicuiDecidable`）。"""

    formal: int
    draft: int
    rejected: int


class E4ExportResponse(BaseModel):
    """§3.1 E4 响应（**4 字段**）：`{batch_id, package_dir, counts:{formal,draft,rejected}, selfcheck_ref}`。"""

    batch_id: str
    package_dir: str
    counts: E4ExportCounts
    selfcheck_ref: str | None
