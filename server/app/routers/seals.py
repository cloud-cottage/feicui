"""`/api/seals/*` 路由（**印章采集线**，批 1）——Kong。

端点一律 **additive**（不动 E1〜E7 与 persons / items）：

  * `POST /api/seals/sync`    —— 列表 1 次取全 → 行内字段构建关联 → 归一化 → 落独立库 → 就绪包
                                （可断点续跑 / 礼貌限速 / 失败清单 / 429 指数退避）
  * `GET  /api/seals`         —— 分页（`page`/`limit`/`has_more`；**不支持 `cursor`**）
  * `GET  /api/seals/{seqid}` —— 单枚（详情 + 关联 + 影像台账）
  * `GET  /api/seals/batches` —— 批次列表（含回执读数）
  * `POST /api/seals/package` —— 从本库重建 xiai 就绪包（**不联网**；含 TIFF 影像内容寻址树）
  * `GET  /api/seals/{seqid}/image/{kind}` —— 读本地影像（kind ∈ yt|ytsw|yzbk）供页面缩略图
  * `POST /api/seals/uploads` —— **本地上传印面导入**（multipart 多图 ＋ dynasty/author/…；
    seal-uploads 线，Kevin 2026-10-13；落 `seal_uploads` ＋ `seals` 新行，只加法）

纪律：
  * 本文件**不含任何 SQL**，一切读数走 `..seals`；
  * 存储＝**独立库** `feicui/var/seal_ingest.db`（`yinpu.db` / `var/person_ingest.db` /
    `var/item_ingest.db` 一律不碰）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .. import seal_uploads
from .. import seals
from .. import multipart as multipart_lib
from ..config import Settings, get_settings

log = logging.getLogger("feicui.api.seals.router")

router = APIRouter(prefix="/api/seals", tags=["seals"])

PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 500

# 本端点**支持的查询参数白名单**。任何**未在此列**的查询参数一律 **400 UNSUPPORTED_PARAM**。
# 要点：本端点＝**纯 offset 分页**（`page`/`limit`），**不支持 `cursor`**；也**不接受** camelCase
# `auditStatus`（源侧形态，非本端点参数名）——传了即 400。
ALLOWED_QUERY_PARAMS = frozenset({"page", "limit", "q", "audit_status", "has_image", "with_facets"})
IMAGE_KINDS = frozenset({"yt", "ytsw", "yzbk"})


def _reject_unsupported_query(request: Request, allowed: frozenset[str]) -> None:
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


# ── 列表（**须在 `/{seqid}` 之前声明**，否则 `batches`/`package` 会被当作 seqid 吞掉）──────────
@router.get("")
def list_seals(
    request: Request,
    page: str | None = Query(default=None, description="1-based 页码（默认 1）"),
    limit: str | None = Query(default=None, description=f"页长，默认 {PAGE_LIMIT_DEFAULT}，上限 {PAGE_LIMIT_MAX}"),
    q: str | None = Query(default=None, description="印文 / 印谱名 / 源 id 模糊查询"),
    audit_status: str | None = Query(default=None, description="审核状态过滤（如 1 / 2 / 9）"),
    has_image: str | None = Query(default=None, description="有无印面图（true/false 可选）"),
    with_facets: str | None = Query(default=None, description="是否附分面（默认 true）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`GET /api/seals` —— 分页 + 筛选。信封＝ **5 字段** `{items, page, limit, total, has_more}`
    （**纯 offset 分页**；**不出现 `next_cursor`**）；另附 `_facets` 与 `_db_path`。

    分页口径（钉死）：
      * **不变式** `has_more == (page * limit < total)`；
      * **未白名单查询参数一律 400**（含 `cursor` 与 camelCase `auditStatus`）；
      * `page` 越界 ⇒ `items=[]` 且 `has_more=False`。
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
    seals.ensure_schema(st.seals_db_path)
    res = seals.list_seals(
        st.seals_db_path, page=page_i, limit=limit_i,
        audit_status=(audit_status if audit_status not in (None, "") else None),
        has_image=_bool_param(has_image, "has_image"), q=q,
    )
    want_facets = _bool_param(with_facets, "with_facets")
    if want_facets is not False:
        res["_facets"] = seals.list_facets(st.seals_db_path)
    res["_db_path"] = str(st.seals_db_path)
    return res


@router.get("/batches")
def list_batches(st: Settings = Depends(_settings)) -> dict:
    """`GET /api/seals/batches` —— 批次列表（含回执读数）。"""
    seals.ensure_schema(st.seals_db_path)
    rows = seals.list_batches(st.seals_db_path)
    return {"items": rows, "total": len(rows), "_db_path": str(st.seals_db_path)}


# ── 就绪包（**须在 `/{seqid}` 之前声明**）──────────────────────────────────────────────────
@router.post("/package")
def create_package(
    request: Request,
    batch_id: str | None = Query(default=None, description="源批次号（缺省＝库内最新批次）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`POST /api/seals/package` —— 生成 **xiai 就绪包**（**从 feicui 本库重建，不联网采集**）。

    产物目录 `exports/seal_import_<batch_id>/`：`seals.jsonl`（候选键面，未裁剪）＋ `seal_links.jsonl`
    （sidecar）＋ `images/<sha256[:2]>/<sha256>.tiff`（**内容寻址 TIFF 树**，镜像 xiai 影像库形态）＋
    `images_manifest.jsonl`（唯一索引）＋ `manifest.json`（字段字典 / 形製码表＋标定证据 / audit 分布 /
    `image_policy` / `key_face_status: pending_xiai`）。

    * **不写 xiai 任何文件、不调任何云函数**；本端点只产 feicui 自有树内产物；
    * 未白名单查询参数 ⇒ **400**；批次不存在 ⇒ **404**（`BATCH_NOT_FOUND`）；库内无批次 ⇒ **404**（`NO_BATCH`）。
    """
    _reject_unsupported_query(request, frozenset({"batch_id"}))
    seals.ensure_schema(st.seals_db_path)
    try:
        pkg = seals.write_package_from_db(
            st.seals_db_path, st.seals_export_root, batch_id=(batch_id or None),
            base=st.seals_source_base, images_root=st.seal_images_dir, item_db=st.items_db_path,
        )
    except seals.ImportPackageError as exc:
        status = 404 if exc.code in {"BATCH_NOT_FOUND", "NO_BATCH"} else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "detail": str(exc)})
    summary = pkg["summary"]
    log.info("xiai 就绪包已生成（seal）：batch_id=%s rows=%s dir=%s",
             summary["batch_id"], summary["rows"], summary["package_dir"])
    return summary


@router.post("/sync")
def sync(request: Request, payload: dict | None = None, st: Settings = Depends(_settings)) -> dict:
    """`POST /api/seals/sync` —— 列表 1 次取全 → 行内字段构建关联 → 归一化 → 落独立库 → 就绪包。

    **未白名单查询参数 ⇒ 400**（白名单＝空集）。请求体（均可选）：
    `{batch_id?, resume?, delay?, limit?, with_detail?, with_graph?}`。
    """
    _reject_unsupported_query(request, frozenset())
    payload = payload or {}
    seals.ensure_schema(st.seals_db_path)
    delay = payload.get("delay")
    delay = float(delay) if delay is not None else st.seals_fetch_delay_s
    if delay < 0.05:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM", "detail": "delay 不得 < 0.05s（礼貌限速下限）"})
    limit = payload.get("limit")
    limit = int(limit) if limit is not None else None
    batch_id = payload.get("batch_id") or None
    resume = payload.get("resume")
    resume = True if resume is None else bool(resume)
    with_detail = bool(payload.get("with_detail") or False)
    with_graph = bool(payload.get("with_graph") or False)
    log.info("印章采集开始：batch_id=%s resume=%s delay=%s limit=%s with_detail=%s with_graph=%s",
             batch_id, resume, delay, limit, with_detail, with_graph)
    try:
        summary = seals.run_sync(
            db_path=st.seals_db_path, export_root=st.seals_export_root, base=st.seals_source_base,
            item_db_path=st.items_db_path, batch_id=batch_id, resume=resume, delay=delay,
            limit=limit, timeout=st.seals_fetch_timeout_s,
            with_detail=with_detail, with_graph=with_graph,
        )
    except seals.FetchError as exc:
        raise HTTPException(status_code=502, detail={"error": "SOURCE_UNREACHABLE", "detail": str(exc)})
    log.info("印章采集完成：%s", {k: summary[k] for k in ("batch_id", "seals_ok", "links_ok", "failed_count")})
    return summary


@router.post("/uploads")
async def upload_seals(request: Request, st: Settings = Depends(_settings)) -> dict:
    """`POST /api/seals/uploads` —— **本地上传印面导入**（seal-uploads 线，Kevin 2026-10-13）。

    multipart/form-data：**多图**（文件段任意字段名、带 filename；同名多值保留）＋ 表单字段
    `dynasty`（必填；枚举真源＝xiai 15 种，本侧不复制）、`author`（可选）、`transcription`
    （可选，默认空＝释文留空）、`dynasty_source`（可选，谁指定的）、`batch_id`（可选，缺省自增）、
    `source_note`（可选）。

    行为：原始字节落 `var/seal_uploads/<batch_id>/` ＋ `seal_uploads` 台账 ＋ `seals` 新行
    （`source_kind='local_upload'`、`audit_status='UNREVIEWED_PENDING_HUMAN_REVIEW'`，**只 INSERT**）。
    **幂等**：同 batch 同 sha ⇒ skipped，不重写文件；`source_seal_id` 撞号（同日多批）⇒ 400（不覆盖）。
    本端点**不产 O 件 / 成品**（批跑另做，见 ops/seal-uploads/）。
    """
    _reject_unsupported_query(request, frozenset())
    ctype = request.headers.get("content-type", "")
    if not multipart_lib.is_multipart(ctype):
        raise HTTPException(status_code=400, detail={
            "error": "UNSUPPORTED_MEDIA_TYPE",
            "detail": f"Content-Type 必须 multipart/form-data：{ctype!r}"})
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > seal_uploads.MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail={
            "error": "PAYLOAD_TOO_LARGE", "detail": f"请求体超上限 {seal_uploads.MAX_TOTAL_BYTES} bytes"})
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail={"error": "EMPTY_BODY", "detail": "请求体为空"})
    if len(body) > seal_uploads.MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail={
            "error": "PAYLOAD_TOO_LARGE", "detail": f"请求体超上限 {seal_uploads.MAX_TOTAL_BYTES} bytes"})
    try:
        fields, _ = multipart_lib.parse_multipart(ctype, body)
        file_parts = multipart_lib.iter_file_parts(ctype, body)
    except multipart_lib.MultipartError as exc:
        raise HTTPException(status_code=400, detail={"error": "BAD_MULTIPART", "detail": str(exc)})

    dynasty = (fields.get("dynasty") or "").strip()
    if not dynasty:
        raise HTTPException(status_code=400, detail={
            "error": "BAD_PARAM", "detail": "表单字段 dynasty 必填（朝代枚举真源＝xiai，如「戰國」）"})
    author = (fields.get("author") or fields.get("author_name") or "").strip() or None
    transcription = fields.get("transcription") or ""
    dynasty_source = (fields.get("dynasty_source") or "").strip() or None
    source_note = (fields.get("source_note") or "").strip() or None
    batch_id = (fields.get("batch_id") or "").strip() or seal_uploads.next_batch_id(st.seals_db_path)

    if not file_parts:
        raise HTTPException(status_code=400, detail={
            "error": "NO_FILES", "detail": "没有文件段（文件段须带 filename；字段名任意，如 files）"})
    if len(file_parts) > seal_uploads.MAX_FILES:
        raise HTTPException(status_code=400, detail={
            "error": "TOO_MANY_FILES", "detail": f"单请求文件数上限 {seal_uploads.MAX_FILES}：{len(file_parts)}"})

    seals.ensure_schema(st.seals_db_path)
    seal_uploads.ensure_schema(st.seals_db_path)
    uploads_root = st.seals_db_path.parent / "seal_uploads"
    accepted: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    seq = 1
    for part in file_parts:
        fname = part["filename"] or f"upload-{seq}.png"
        try:
            if len(part["content"]) > seal_uploads.MAX_FILE_BYTES:
                raise seal_uploads.UploadError(
                    f"单文件超上限 {seal_uploads.MAX_FILE_BYTES} bytes：{len(part['content'])}")
            res = seal_uploads.record_upload(
                st.seals_db_path, data=part["content"], filename=fname, batch_id=batch_id,
                seq=seq, dynasty=dynasty, dynasty_source=dynasty_source, author_name=author,
                transcription=transcription, uploads_root=uploads_root, source_note=source_note)
        except seal_uploads.UploadError as exc:
            failed.append({"filename": fname, "error": str(exc)})
            continue
        (skipped if res["status"] == "skipped" else accepted).append(res)
        seq += 1
    summary = {"batch_id": batch_id, "dynasty": dynasty, "author": author,
               "transcription": transcription, "accepted": accepted, "skipped": skipped,
               "failed": failed,
               "counts": {"accepted": len(accepted), "skipped": len(skipped), "failed": len(failed)},
               "_db_path": str(st.seals_db_path), "_uploads_root": str(uploads_root)}
    log.info("印章本地上传导入：batch_id=%s accepted=%s skipped=%s failed=%s",
             batch_id, len(accepted), len(skipped), len(failed))
    return summary


@router.get("/{seqid}/image/{kind}")
def get_seal_image(seqid: str, kind: str, st: Settings = Depends(_settings)) -> FileResponse:
    """`GET /api/seals/{seqid}/image/{kind}` —— 读本地影像（kind ∈ yt|ytsw|yzbk）供页面缩略图。

    只读 `var/seal_images/` 缓存；不存在 ⇒ 404。kind 非法 ⇒ 400。
    """
    if kind not in IMAGE_KINDS:
        raise HTTPException(status_code=400, detail={"error": "BAD_PARAM",
                            "detail": f"kind 只能是 {sorted(IMAGE_KINDS)}：{kind!r}"})
    seals.ensure_schema(st.seals_db_path)
    path = seals.seal_image_path(st.seals_db_path, st.seal_images_dir, seqid, kind)
    if path is None:
        raise HTTPException(status_code=404, detail={"error": "IMAGE_NOT_FOUND",
                            "detail": f"本地无影像：seqid={seqid} kind={kind}"})
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/{seqid}")
def get_seal(seqid: str, st: Settings = Depends(_settings)) -> dict:
    """`GET /api/seals/{seqid}` —— 单枚（详情 + 关联 + 影像台账）。不存在 ⇒ 404。"""
    seals.ensure_schema(st.seals_db_path)
    rec = seals.get_seal(st.seals_db_path, seqid)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "SEAL_NOT_FOUND", "detail": f"印章不存在：{seqid}"})
    return rec
