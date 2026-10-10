"""HTTP 路由层（**只做形状**）——Kong / 阶段 1a。

纪律（规范 §3.2 S-4「接口层不落业务真值」）：
  * 本文件**不含任何 SQL**，也不持有任何 job / 进度的进程内状态；
  * 所有读数一律调用 `..repository`（每次请求现开连接现查现算）；
  * 状态码族严格照 §3.2 S-6：`400` 参数非法 / `404` 资源不存在 / `409` 冲突 / `422` 必填不可派生 / `500` 内部错误。

本单实现：**E1 / E2 / E5**。E3 / E4 属阶段 1b，**此处未注册路由**。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from urllib.parse import quote

from .. import db, pdfmeta, poolctl, repository, uploader
from ..config import Settings, get_settings
from ..models import (
    PAGE_LIMIT_DEFAULT,
    PAGE_LIMIT_MAX,
    E4ExportRequest,
    E4ExportResponse,
    E7JobsResponse,
    JobConflictResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobProgressResponse,
    JobUploadResponse,
    MissingResponse,
    PagedEnvelope,
)

log = logging.getLogger("feicui.api.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _settings() -> Settings:
    return get_settings()


def _resolve_pdf_path(raw: str, st: Settings) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = st.root / p
    return p.resolve()


# ---- E1 的 PDF 判定（§3.1 表下注 **G-6**）----------------------------------------
PDF_MAGIC = b"%PDF-"
#: G-6 口径＝**文件前 1024 字节内**出现 `%PDF-` 即算 PDF（**不是** E8 口的「首字节即须为」）。
PDF_MAGIC_SCAN_BYTES = 1024


def _pdf_has_magic(pdf_abs: Path) -> bool:
    """**E1** 的既有文件 PDF 判定（§3.1 表下注 **G-6**）：非 PDF **以 `%PDF-` magic 为准**。

    判据＝**文件前 `PDF_MAGIC_SCAN_BYTES`（1024）字节内**出现 `%PDF-`（G-6 逐字：「文件前 1024 字节内
    出现 `%PDF-`」）——**不**只按扩展名分流（不得把纯文本当 PDF 收下：PyMuPDF 对 `.txt` 宽松、报 1 页）。

    **与 §3.19.4 的 E8 口的关系（防误用）**：E8 收新字节用**首字节即须为 `%PDF-`** 的严判定；此处用 G-6
    的宽松判定——规范明写「**两者是不同口的不同严格度，不互相代替、本版不统一**」⇒ **不得**照搬 E8 判据。
    """
    try:
        with pdf_abs.open("rb") as fh:
            head = fh.read(PDF_MAGIC_SCAN_BYTES)
    except OSError:
        return False
    return PDF_MAGIC in head


@router.post("", status_code=201, response_model=JobCreateResponse)
def create_job(payload: JobCreateRequest, st: Settings = Depends(_settings)) -> JobCreateResponse:
    """**E1** `POST /api/jobs` —— 建 job（一本书 = 一个 job，**入队**语义）。

    * 同 `pdf_path` 已有活跃 job ⇒ **409 + 既有 job_id**（绝不静默起第二个，§3.2 S-5）；
      并发抢占由库级部分唯一索引 `uq_jobs_active_pdf_path` 兜底，同样落成 409。
    * **建 job 之前**先校验 `pdf_path`（**真缺陷修复**，向 G-6 契约对齐）：
      ① 路径不存在 / 不是文件 ⇒ **400** `PDF_NOT_FOUND`；
      ② 存在但**非 PDF**（前 1024 字节内无 `%PDF-` magic，§3.1 表下注 G-6）⇒ **400** `NOT_A_PDF`；
      **两者都不得建 job、不得写任何行**（原实现只看 `is_file()` ⇒ 存在但非 PDF 的文件会被当 1 页 PDF
      收下、建出 job，违反 §3.1 G-6 ＋ §3.4 的 400 枚举）。
    * `total_pages` 派生：给了 `page_range` 就取区间宽；否则读 PDF 页数；
      都拿不到 ⇒ **422**（S-6「必填字段不可派生」）。
    """
    if not payload.pdf_path.strip():
        raise HTTPException(status_code=400, detail="pdf_path 不能为空")

    pdf_abs = _resolve_pdf_path(payload.pdf_path, st)
    if not pdf_abs.is_file():
        raise HTTPException(
            status_code=400,
            detail={"error": "PDF_NOT_FOUND", "detail": f"pdf_path 不存在或不是文件：{pdf_abs}"},
        )
    # ---- G-6：既有文件的 PDF 判定（**必须在建 job / 入队之前**）--------------------
    if not _pdf_has_magic(pdf_abs):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NOT_A_PDF",
                "detail": f"pdf_path 存在但非 PDF（前 {PDF_MAGIC_SCAN_BYTES} 字节内无 %PDF- magic）：{pdf_abs}",
            },
        )
    pdf_name = repository.pdf_name_of(pdf_abs)
    pdf_total = pdfmeta.pdf_page_count(pdf_abs)

    page_range = payload.page_range
    if page_range is not None:
        lo, hi = int(page_range[0]), int(page_range[1])
        if lo < 1 or hi < lo:
            raise HTTPException(
                status_code=400,
                detail={"error": "BAD_PAGE_RANGE", "detail": f"page_range 非法：[{lo},{hi}]（需 1-based 且 from<=to）"},
            )
        if pdf_total is not None and hi > pdf_total:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "PAGE_RANGE_OUT_OF_RANGE",
                    "detail": f"page_range 上界 {hi} 超出 PDF 页数 {pdf_total}",
                },
            )
    elif pdf_total is not None:
        lo, hi = 1, int(pdf_total)
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "FIELD_NOT_DERIVABLE",
                "detail": "无法派生 total_pages：既未给 page_range，也读不出 PDF 页数（PyMuPDF 不可用 / 文件损坏）",
                "missing": ["total_pages"],
            },
        )

    chunk_size = int(payload.chunk_size or st.chunk_size)
    total_pages = hi - lo + 1

    # 冲突判定（读路径）：活跃 job 已存在 ⇒ 409 + 既有 job_id
    with db.ro(st.db_path) as conn:
        existing = repository.find_active_job(conn, str(pdf_abs))
    if existing:
        return _conflict(existing)

    try:
        created = repository.create_job(
            st.db_path,
            pdf_path=str(pdf_abs),
            pdf_name=pdf_name,
            page_from=lo,
            page_to=hi,
            chunk_size=chunk_size,
            rerun=bool(payload.rerun),
            total_pages=total_pages,
        )
    except repository.ActiveJobExists as exc:  # 并发兜底
        return _conflict(exc.existing)

    # ---- 阶段 1c-激活：入队成功 ⇒ **异步**拉起池一次（不阻塞请求；失败只记日志，不影响 201）----
    # 池是独立进程（§1.3 进程分离）且不常驻（跑完即退），故**每次建 job 都要拉一次**；
    # 「已有池在跑」由池自身写锁 + 本层 flock 探测处理成正常分支（`poolctl` 模块文档）。
    try:
        poolctl.launch_pool_async(st, reason=f"E1:{created['job_id']}")
    except Exception as exc:  # pragma: no cover - 拉起侧任何异常都不得改变 E1 的返回
        log.warning("E1 后拉起池失败（不影响 job 入队）：job=%s err=%r", created["job_id"], exc)

    return JobCreateResponse(**created)


def _conflict(existing: dict) -> Response:
    body = JobConflictResponse(
        detail="同 pdf_path 已有活跃 job（§3.2 S-5：同一本书同时只允许一个活跃 job）",
        job_id=existing["job_id"],
        state=existing["state"],
        total_pages=int(existing["total_pages"]),
        created_at=existing["created_at"],
    )
    return Response(
        status_code=409,
        media_type="application/json",
        content=body.model_dump_json(),
    )


# ------------------------------------------------------ 拖曳上传（**additive**，本单新增）
@router.post("/upload")
async def upload_pdf(request: Request, st: Settings = Depends(_settings)) -> JSONResponse:
    """**additive** `POST /api/jobs/upload` —— PDF 拖曳上传**落盘**（**不建 job、零 DB 写**）。

    为什么需要它（浏览器事实）：拖入 / 选中的 `File` **不带本地路径**，而 E1 要吃**服务器侧
    `pdf_path`** ⇒ 必须先上传落盘，再把落盘路径交给 E1（E1 契约**一字未改**，本端点纯 additive）。

    **入口形态**（**裸字节流**，不走 multipart——`app/multipart.py` 会把整包读进内存，
    372 MB 会打爆；本端点用 `Request.stream()` 分块写盘、内存恒定）：
      * `Content-Type` **必须** ∈ {`application/pdf`, `application/octet-stream`}（§3.19.2）——
        **否则 `400 BAD_CONTENT_TYPE`**；Content-Type 本身**不作 PDF 判据**（真正的门是 `%PDF-` 魔数）；
      * **无查询参数**（未白名单 ⇒ `400 UNSUPPORTED_PARAM`，同 §3.16.3 Q5 / §3.18.6 型）；
      * 文件名：`X-Filename`（**URL-encoded UTF-8**）⇒ 回退 `Content-Disposition` 的
        `filename*` / `filename` ⇒ 再回退 `upload.pdf`；**一律清毒**（只留 basename、
        去控制字符与 `..`、后缀规范成 `.pdf`、stem ≤ 200 UTF-8 字节）——**清毒后越界 ⇒ `400`**。

    **落点**：`inbox/<yyyymmdd>/<safe-name>.pdf`（落在 `FEICUI_ROOT` 之内）。

    **校验顺序（§3.19.4 冻结）**：① `Content-Type` ⇒ ② 空体 ⇒ ③ 首字节 `%PDF-` ⇒ ④ 累计超限。
      * 空体 ⇒ `400 EMPTY_BODY`；首字节非 `%PDF-` ⇒ `400 NOT_A_PDF`；
      * 超过单文件上限（默认 **512 MiB**，`FEICUI_UPLOAD_MAX_BYTES` 可改）⇒
        **`413 PAYLOAD_TOO_LARGE`**——声明超限 ⇒ 魔数一过即拒（**不落一个字节**）；
        实收字节超限 ⇒ **每写一块即累加比较、一超即停并删除本轮分片**（不先写满盘）。
      * 磁盘 / IO 异常 ⇒ `500`（**结构化 JSON**，绝不 HTML 错误页）。

    **幂等**（Kevin 2026-10-10 口径）：同名同内容 ⇒ **不重写**（`idempotent=true`，mtime 不变）；
    同名异内容 ⇒ **绝不覆盖**（既有 job 的输入可能正靠它）⇒ `<stem>-<sha256[:8]>.pdf`
    并标 `dedup_suffix=true`。

    **响应**：`201`（新写入）/ `200`（幂等复用）`{pdf_path, rel_path, filename, bytes, sha256,
    idempotent, dedup_suffix}`；`pdf_path` ＝ **绝对服务器侧路径**、`rel_path` ＝ **相对 `feicui/`**
    的路径（两者都落在 §3.1 E1 的「绝对或相对 `feicui/`」口径内、**可直接喂给 E1**）。
    """
    try:
        res = await uploader.store_pdf(
            request,
            inbox_root=st.inbox_dir,
            max_bytes=st.upload_max_bytes,
            chunk_bytes=st.upload_chunk_bytes,
        )
    except uploader.UploadRejected as exc:
        log.warning("job-upload 拒收(%s %s)：%s", exc.status_code, exc.error, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "detail": exc.detail, **exc.extra},
        )
    except OSError as exc:  # 磁盘 / IO 异常 ⇒ 500（§3.4：**结构化 JSON**，且体不得回吐绝对路径）
        log.error("job-upload 落盘失败：%r", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "INBOX_WRITE_FAILED", "detail": "落盘失败（磁盘 / IO 异常，详见服务端日志）"},
        )
    except Exception as exc:  # noqa: BLE001 - 绝不把 HTML / 纯文本错误页抛给前端
        log.exception("job-upload 未预期异常")
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL", "detail": f"{type(exc).__name__}（详见服务端日志）"},
        )

    final: Path = res["path"]
    pdf_path = str(final)  # 绝对（§3.19.4 允许「绝对或相对 feicui/」；此处给绝对，rel_path 给相对）
    try:
        rel_path = final.relative_to(st.root).as_posix()  # 相对 FEICUI_ROOT（§3.19.4 冻结）
    except ValueError:  # 落点被 env 重定向到 root 之外（自测）：退回文件名，**不编造**
        rel_path = final.name

    body = JobUploadResponse(
        pdf_path=pdf_path,
        rel_path=rel_path,
        filename=res["filename"],
        bytes=int(res["bytes"]),
        sha256=res["sha256"],
        idempotent=bool(res["idempotent"]),
        dedup_suffix=bool(res["dedup_suffix"]),
    )
    log.info(
        "job-upload %s：%s bytes=%s sha256=%s dedup=%s",
        res["status_code"],
        pdf_path,
        body.bytes,
        body.sha256[:12],
        body.dedup_suffix,
    )
    return JSONResponse(status_code=int(res["status_code"]), content=body.model_dump())


@router.get("/{job_id}", response_model=JobProgressResponse)
def get_job(job_id: str, st: Settings = Depends(_settings)) -> JobProgressResponse:
    """**E2** `GET /api/jobs/{job_id}` —— 查进度（**库内复算**，§3.2 S-1 / S-2）。"""
    try:
        progress = repository.get_progress(st.db_path, job_id)
    except repository.JobNotFound:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND", "detail": f"job 不存在：{job_id}"})
    if progress["state"] == "FAILED_PARTIAL" and progress["failed_pages"]:
        log.warning(
            "job %s 库内 state=DONE 但存在 failed_pages=%s ⇒ S-2 下行报 FAILED_PARTIAL",
            job_id,
            progress["failed_pages"],
        )
    return JobProgressResponse(**progress)


@router.get("/{job_id}/missing", response_model=MissingResponse)
def missing(
    job_id: str,
    response: Response,
    kind: str | None = Query(default=None, description="image | text"),
    st: Settings = Depends(_settings),
) -> MissingResponse:
    """**E5** `GET /api/jobs/{job_id}/missing?kind=image|text` —— 影像 / 释文缺失清单。

    判定范围（该书 × 该 job 页区间）经响应头 `x-feicui-scope` 暴露，**不进 JSON 体**
    （保持 §3.1 E5 的字段形状不多不少）。
    """
    if kind not in {"image", "text"}:
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_KIND", "detail": "kind 必填且只能是 image 或 text"},
        )
    try:
        items, (pdf_name, lo, hi) = repository.missing_items(st.db_path, job_id, kind, root=st.root)
    except repository.JobNotFound:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND", "detail": f"job 不存在：{job_id}"})
    response.headers["x-feicui-scope"] = _header_safe(
        f"pdf_name={pdf_name};page_from={lo};page_to={hi};root={st.root}"
    )
    return MissingResponse(kind=kind, count=len(items), items=items)


# =========================================================================== 阶段 1b-ii：E3 / E4 / E6 / E7
# 形状纪律（§3.1 表 + §3.2 S-3 + §3.8）：
#   * E3 / E7 = **6 字段信封**，一个不多一个不少；`items` 为实体数组；`has_more=false ⇒ next_cursor=null`；
#   * E4 响应 = **4 字段**；E6 响应 = **影像字节**（不包 JSON 信封）；
#   * 错误码族严格照 §3.2 S-6 + §3.4（400/404/409/422/500，体必含 `detail`）。
ERROR_BAD_PARAM = "BAD_PARAM"


def _header_safe(value: str) -> str:
    """HTTP **头值必须 ASCII**（Starlette 按 latin-1 编码）。

    **实测踩坑（本轮修）**：`x-feicui-scope` 里带书名——`古玺汇编 …` / `秦汉印典 …` 是中文 ⇒
    直接塞进响应头会抛 `UnicodeEncodeError: 'latin-1' codec can't encode …`，接口层返 **500**
    （中国书名两本书的 E3 全页 500，ASCII 名书正常）。故非 ASCII 字符一律**百分号编码**
    （`%XX`，标准 URL 编码，前端可用 `decodeURIComponent` 还原；**只影响响应头，JSON 体一字未变**）。
    """
    return "".join(ch if ord(ch) < 128 else quote(ch) for ch in value)


def _int_param(raw: str | None, name: str, *, minimum: int | None = None) -> int | None:
    """查询参数整数解析 —— **非法一律 400**（§3.4 的 400 行；不用框架默认的 422）。"""
    if raw is None or raw == "":
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": f"{name} 必须为整数：{raw!r}"})
    if minimum is not None and value < minimum:
        raise HTTPException(
            status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": f"{name} 必须 >= {minimum}：{value}"}
        )
    return value


def _resolve_limit(raw: str | None) -> int:
    limit = _int_param(raw, "limit", minimum=1)
    if limit is None:
        return PAGE_LIMIT_DEFAULT
    if limit > PAGE_LIMIT_MAX:
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_BAD_PARAM, "detail": f"limit 上限 {PAGE_LIMIT_MAX}（收到 {limit}）"},
        )
    return limit


def _job_exists(st: Settings, job_id: str) -> dict:
    with db.ro(st.db_path) as conn:
        return repository.get_job_row(conn, job_id)


@router.get("/{job_id}/stamps", response_model=PagedEnvelope)
def list_stamps(
    job_id: str,
    response: Response,
    page: str | None = Query(default=None, description="1-based 页码（与 cursor 互斥）"),
    limit: str | None = Query(default=None, description=f"页长，默认 {PAGE_LIMIT_DEFAULT}，上限 {PAGE_LIMIT_MAX}"),
    cursor: str | None = Query(default=None, description="上一页的 next_cursor（游标分页，翻页稳定）"),
    st: Settings = Depends(_settings),
) -> PagedEnvelope:
    """**E3** `GET /api/jobs/{job_id}/stamps?page=&limit=&cursor=` —— 分页取结果。

    信封＝§3.2 S-3 的 **6 字段** `{items[], page, limit, total, has_more, next_cursor}`；
    `items[]` 为**实体数组**（每条＝与平台 §9.3 对齐的记录对象，逐条带 `missing_required`，见 `records.py`）。

    **规范缺口（本单取法，已登记）**：`page` 与 `cursor` 的同时给法规范未定 ⇒ 本层判**互斥**（同给即 400）。
    """
    if page is not None and cursor is not None:
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_BAD_PARAM, "detail": "page 与 cursor 互斥：二选一（翻页请一路用 cursor）"},
        )
    page_i = _int_param(page, "page", minimum=1)
    limit_i = _resolve_limit(limit)
    try:
        res = repository.stamps_page(st.db_path, job_id, limit=limit_i, cursor=cursor, page=page_i)
    except repository.JobNotFound:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND", "detail": f"job 不存在：{job_id}"})
    except repository.BadCursor as exc:
        raise HTTPException(status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": str(exc)})

    from ..records import build_items  # 延迟导入：本模块只做形状，形状层独立

    items = build_items(st.db_path, res["rows"], root=st.root)
    response.headers["x-feicui-scope"] = _header_safe(
        f"pdf_name={res['scope']['pdf_name']};page_from={res['scope']['page_from']};"
        f"page_to={res['scope']['page_to']};job_id={res['scope']['job_id']}"
    )
    return PagedEnvelope(
        items=items,
        page=res["page"],
        limit=res["limit"],
        total=res["total"],
        has_more=res["has_more"],
        next_cursor=res["next_cursor"],
    )


# --------------------------------------------------------------------------- E6
MEDIA_SNIFF = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
MEDIA_BY_SUFFIX = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
# §3.5：Content-Type ∈ {image/webp, image/png, image/jpeg}，**以文件实际类型为准**
E6_CONTENT_TYPES = {"image/webp", "image/png", "image/jpeg"}


def _sniff_media_type(data: bytes, rel_path: str) -> str:
    """按**内容**判定影像类型（magic 优先，后缀兜底）——不臆造、不用 `application/octet-stream` 兜底。"""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, ctype in MEDIA_SNIFF:
        if data.startswith(magic):
            return ctype
    by_suffix = MEDIA_BY_SUFFIX.get(Path(rel_path).suffix.lower())
    if by_suffix:
        return by_suffix
    raise HTTPException(
        status_code=500,
        detail={"error": "IMAGE_TYPE_UNKNOWN", "detail": "无法判定影像类型（magic 与后缀均不识别）"},
    )


@router.get("/{job_id}/stamps/{page}/{idx}/image")
def stamp_image(
    job_id: str,
    page: str,
    idx: str,
    st: Settings = Depends(_settings),
) -> Response:
    """**E6** `GET /api/jobs/{job_id}/stamps/{page}/{idx}/image` —— 取印面裁图（**二进制**，§3.5）。

    * `{page}` **1-based**（↔ `stamps.page`）、`{idx}` **0-based**（↔ `stamps.idx`）；**无查询参数**；
    * `200` = 影像字节（`Content-Type` 取文件实际类型、`Content-Length` 必填、**不包 JSON 信封**）；
    * `404` = **三类同码**（job 不存在 / 记录不存在 / `img_path` 缺失或文件不在盘上）；
    * `400` = 参数非法（非整数、`page < 1`、`idx < 0`）；`500` = 读盘异常；
    * **只读**（不解析 / 不 OCR / 不写库 / 不写缓存）、**不占位冒充**、**不读 BLOB**（库内本无 BLOB 列）。
    """
    page_i = _int_param(page, "page", minimum=1)
    if page_i is None:
        raise HTTPException(status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": "page 不能为空"})
    idx_i = _int_param(idx, "idx", minimum=0)
    if idx_i is None:
        raise HTTPException(status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": "idx 不能为空"})

    try:
        _pdf_name, rel, abs_path = repository.find_stamp_image(st.db_path, job_id, page_i, idx_i, root=st.root)
    except repository.JobNotFound:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND", "detail": f"job 不存在：{job_id}"})
    except repository.StampNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "STAMP_NOT_FOUND", "detail": str(exc)})
    except repository.ImageUnavailable as exc:
        raise HTTPException(status_code=404, detail={"error": "IMAGE_UNAVAILABLE", "detail": str(exc)})

    try:
        data = Path(abs_path).read_bytes()
    except OSError as exc:
        log.error("E6 读盘失败：%s", exc)  # 详细原因只进日志（§3.4：500 体不得回吐绝对路径）
        raise HTTPException(status_code=500, detail={"error": "IMAGE_READ_FAILED", "detail": "读盘失败（详见服务端日志）"})
    if not data:
        raise HTTPException(status_code=500, detail={"error": "IMAGE_READ_FAILED", "detail": "影像文件为空（0 字节）"})

    ctype = _sniff_media_type(data, rel)
    return Response(
        content=data,
        media_type=ctype,
        headers={
            "Content-Length": str(len(data)),
            # §3.5 纪律⑤：dev 口径，避免干扰 §2.4 重跑幂等比对
            "Cache-Control": "no-store",
            # §3.5 可选响应头：DB 内**相对**路径，供对账（不进体）
            # §3.13：头值必须 **latin-1 可编码** ⇒ 含中文书名的相对路径（如
            # `output/秦汉印典 …/p5_0.webp`）**必须百分号编码**——（本轮实测）原实现直接回吐
            # DB 原值 ⇒ starlette 编码头值抛 `UnicodeEncodeError` ⇒ **E6 整条 500**
            # （中文书名书取图全挂；ASCII 名书正常）。前端用 `decodeURIComponent` 还原。
            "x-feicui-img-path": _header_safe(rel),
        },
    )


# --------------------------------------------------------------------------- E4
@router.post("/{job_id}/export", response_model=E4ExportResponse)
def export_job(
    job_id: str,
    payload: E4ExportRequest | None = None,
    st: Settings = Depends(_settings),
) -> E4ExportResponse:
    """**E4** `POST /api/jobs/{job_id}/export` —— 触发导出（调现成 `export.py` CLI）。

    响应＝§3.1 E4 的 **4 字段**；`batch_id` / `package_dir` 一律取自 `export.py` 的真实产物
    （`report.json`），**不由接口层编造**。请求三项（`batch_id` / `dry_run` / `book_code`）的语义
    规范未定义 ⇒ 本单取法见 `exporting.py` 模块文档 + REPORT_1b-ii「规范缺口」。
    """
    payload = payload or E4ExportRequest()
    job = _job_exists(st, job_id)  # job 不存在 ⇒ 404（JobNotFound 由全局 handler 落 404）

    if payload.batch_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": ERROR_BAD_PARAM,
                "detail": "不支持指定 batch_id：batch_id 由 export.py 按「一本书 = 一个批次」派生（§3.3 §9.6），不臆造批次号",
            },
        )
    if payload.dry_run:
        raise HTTPException(
            status_code=400,
            detail={"error": "DRY_RUN_UNSUPPORTED", "detail": "export.py 无 dry-run 模式（不得假装跑过）"},
        )
    if payload.book_code:
        from ..exporting import book_code_entry

        entry = book_code_entry(st.export_config_dir, job["pdf_name"])
        if not entry:
            raise HTTPException(
                status_code=400,
                detail={"error": "BOOK_CODE_UNKNOWN", "detail": f"config/book_codes.json 无本书记录：{job['pdf_name']}"},
            )
        allowed = {str(entry.get("short_code") or ""), str(entry.get("key") or "")}
        if payload.book_code not in allowed:
            raise HTTPException(
                status_code=400,
                detail={"error": "BOOK_CODE_MISMATCH", "detail": f"book_code={payload.book_code!r} 与本书记录不符"},
            )

    from ..exporting import ExportFailed, run_export  # 延迟导入：只在 E4 需要时加载

    try:
        result = run_export(
            db_path=st.db_path,
            export_root=st.export_root,
            export_script=st.export_script,
            config_dir=st.export_config_dir,
            python_bin=st.worker_python,
            pdf_name=job["pdf_name"],
            timeout_s=st.export_timeout_s,
        )
    except ExportFailed as exc:
        log.error("E4 触发导出失败：job=%s book=%s err=%s", job_id, job["pdf_name"], exc)
        raise HTTPException(status_code=500, detail={"error": "EXPORT_FAILED", "detail": str(exc)})

    log.info("E4 导出完成：job=%s diag=%s", job_id, result.get("_diag"))
    return E4ExportResponse(
        batch_id=result["batch_id"],
        package_dir=result["package_dir"],
        counts=result["counts"],
        selfcheck_ref=result["selfcheck_ref"],
    )


# --------------------------------------------------------------------------- E7
E7_STATES = ("QUEUED", "RUNNING", "PAUSED", "DONE", "FAILED_PARTIAL")


@router.get("", response_model=E7JobsResponse)
def list_jobs(
    state: str | None = Query(
        default=None,
        description=(
            "按**有效态**（§3.2 S-2 复算：库内 DONE 但含 FAILED 页 ⇒ FAILED_PARTIAL）过滤，"
            "取值 QUEUED/RUNNING/PAUSED/DONE/FAILED_PARTIAL；口径与 items[].state 完全一致"
        ),
    ),
    page: str | None = Query(default=None, description="1-based 页码（与 cursor 互斥）"),
    limit: str | None = Query(default=None, description=f"页长，默认 {PAGE_LIMIT_DEFAULT}，上限 {PAGE_LIMIT_MAX}"),
    cursor: str | None = Query(default=None, description="上一页的 next_cursor"),
    st: Settings = Depends(_settings),
) -> E7JobsResponse:
    """**E7** `GET /api/jobs?state=&page=&limit=&cursor=` —— 列 job（§3.1 E7 / §3.8）。

    返回 **E3 同款 6 字段信封**；`items[]` 字段集见 §3.1 E7 行；`done_pages` /
    `failed_pages_count` 由 `job_pages` **复算**（S-1），`state` 经 `effective_state`（S-2）。

    **本单修的真缺陷**：原实现**没有 `page` 形参**（§3.1 E7 行的入参写作 `?state=&limit=&cursor=`，
    而前端与自测都会用 `?page=`）⇒ `page` 被 FastAPI 静默忽略，`page=1..N` 一律返回同一份第一页数据。
    `page` 与 `cursor` 的语义与 **E3 完全同款**（互斥、二选一；同给即 400），保证两路翻页的
    key 集合逐条相等（不重叠、不遗漏）；`page` 超出末页 ⇒ **空 `items` + `has_more=false`**
    （绝不回吐第一页）。
    """
    if page is not None and cursor is not None:
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_BAD_PARAM, "detail": "page 与 cursor 互斥：二选一（翻页请一路用 cursor）"},
        )
    if state is not None and state not in E7_STATES:
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_BAD_PARAM, "detail": f"state 非法：{state!r}（允许 {', '.join(E7_STATES)}）"},
        )
    page_i = _int_param(page, "page", minimum=1)
    limit_i = _resolve_limit(limit)
    try:
        res = repository.jobs_page(st.db_path, state=state, limit=limit_i, cursor=cursor, page=page_i)
    except repository.BadCursor as exc:
        raise HTTPException(status_code=400, detail={"error": ERROR_BAD_PARAM, "detail": str(exc)})
    return E7JobsResponse(**res)
