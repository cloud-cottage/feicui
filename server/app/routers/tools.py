"""`/api/tools/*` 路由（**纯函数端点**，与 jobs 体系**完全无关**）——Kong。

本单：`POST /api/tools/square-crop`（Zang 冻结契约，字段名逐字对齐；玺爱 5163 侧按此调用）。

红线（本文件即其守门处）：
  * **不写 DB**（无任何 SQL / 无 repository 调用）、**不读 `stamps`**、**不建 job**（无 `jobs` / `job_pages`
    任何读写）、**不碰 `exports/` `output/`**（字节只进不出：上传进来、base64 回去，全程不落盘）；
  * **不复制检测算法**：红掩膜口径一律走 `processor.detect_stamp_regions`（在 worker 子进程里）；
  * 任何错误一律**结构化 JSON**（`{"ok":false,"error":…,"reason":…,"detail":…}`），**绝不返回 HTML 错误页**。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import multipart as mpart
from .. import square
from ..config import get_settings
from ..square_client import RunnerError, run_square_crop

log = logging.getLogger("feicui.api.tools")

router = APIRouter(prefix="/api/tools", tags=["tools"])

# 上传上限：本机 dev 用途（玺爱新增印章时的单张印面图，真实样本 30KB～120KB）。超限 ⇒ 400（不建临时文件）。
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def _err(status_code: int, code: str, reason: str, **extra) -> JSONResponse:
    """结构化错误体。`error` = 机器码，`reason` = 契约要求的可读原因，`detail` = 兼容 §3.4 的既有形状。"""
    body: dict = {"ok": False, "error": code, "reason": reason, "detail": reason}
    body.update(extra)
    return JSONResponse(status_code=status_code, content=body)


class _BadParam(ValueError):
    """请求参数非法（⇒ 400 BAD_PARAM）。"""


def _opt_float(fields: dict, name: str, default: float | None) -> float | None:
    v = fields.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(str(v).strip())
    except ValueError as exc:
        raise _BadParam(f"{name} 不是合法数字：{v!r}") from exc


def _opt_int(fields: dict, name: str, default: int) -> int:
    v = fields.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(float(str(v).strip()))
    except ValueError as exc:
        raise _BadParam(f"{name} 不是合法整数：{v!r}") from exc


@router.post("/square-crop")
async def square_crop(request: Request) -> JSONResponse:
    """**方形化裁剪**：`multipart/form-data`（文件字段名 `image`）→ JSON（候选按面积降序）。

    入参：`image`（必填）、`pad_ratio`（默认 0.15）、`min_area_eff`（可选）、`quality`（默认 95）、
    `max_side`（默认 0＝不缩放）。
    出参 200：`ok=true` / `candidates[]`（`idx`/`bbox`/`square`/`side`/`width`/`height`/`mime`/`sha256`/
    `image_base64`）/ `count` / `source` / `params_used` / `degraded`。
    错误：400（缺 `image` / 图片无法解码 / 参数非法）、422（无候选 `NO_CANDIDATE`）、500（内部错误）。
    """
    try:
        st = get_settings()
        content_type = request.headers.get("content-type", "")
        if not mpart.is_multipart(content_type):
            return _err(
                400,
                "BAD_CONTENT_TYPE",
                "请求须为 multipart/form-data，文件字段名 `image`（当前 Content-Type＝"
                f"{content_type or '（缺失）'}）",
            )
        body = await request.body()
        if len(body) > MAX_UPLOAD_BYTES:
            return _err(400, "UPLOAD_TOO_LARGE", f"请求体过大：{len(body)} B > 上限 {MAX_UPLOAD_BYTES} B")

        try:
            fields, files = mpart.parse_multipart(content_type, body)
        except mpart.MultipartError as exc:
            return _err(400, "BAD_MULTIPART", f"multipart 解析失败：{exc}")

        image_bytes = files.get("image")
        if not image_bytes:
            return _err(
                400,
                "NO_IMAGE",
                "缺少文件字段 `image`（multipart/form-data 的文件部分，字段名必须为 image），或该字段为空",
            )

        try:
            pad_ratio = _opt_float(fields, "pad_ratio", square.PAD_RATIO_DEFAULT)
            min_area_eff = _opt_float(fields, "min_area_eff", None)
            quality = _opt_int(fields, "quality", square.QUALITY_DEFAULT)
            max_side = _opt_int(fields, "max_side", square.MAX_SIDE_DEFAULT)
            assert pad_ratio is not None
            if not (square.PAD_RATIO_MIN <= pad_ratio <= square.PAD_RATIO_MAX):
                raise _BadParam(
                    f"pad_ratio 越界：{pad_ratio}（须在 [{square.PAD_RATIO_MIN}, {square.PAD_RATIO_MAX}]）"
                )
            if min_area_eff is not None and min_area_eff <= 0:
                raise _BadParam(f"min_area_eff 必须 > 0：{min_area_eff}")
            if not (square.QUALITY_MIN <= quality <= square.QUALITY_MAX):
                raise _BadParam(f"quality 越界：{quality}（须在 [{square.QUALITY_MIN}, {square.QUALITY_MAX}]）")
            if max_side < 0:
                raise _BadParam(f"max_side 必须 >= 0（0＝不缩放）：{max_side}")
        except _BadParam as exc:
            return _err(400, "BAD_PARAM", str(exc))

        req_params = square.resolve_params(st.root, pad_ratio=pad_ratio, min_area_eff=min_area_eff)

        try:
            out = run_square_crop(
                st, image_bytes, req_params, quality=quality, max_side=max_side
            )
        except RunnerError as exc:
            log.warning("square-crop 子进程失败：%s", exc)
            return _err(500, exc.code, f"图像处理子进程失败：{exc.detail}")

        if not out.get("ok"):
            code = str(out.get("error") or "RUNNER_ERROR")
            detail = str(out.get("detail") or code)
            if code == "DECODE_FAILED":
                return _err(400, "DECODE_FAILED", "上传内容不是可解码的图片（cv2.imdecode 失败）")
            return _err(500, code, detail)

        count = int(out.get("count", len(out.get("candidates") or [])))
        if count == 0:
            return _err(
                422,
                "NO_CANDIDATE",
                "NO_CANDIDATE",
                source=out.get("source"),
                params_used=out.get("params_used"),
            )
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "count": count,
                "source": out.get("source"),
                "candidates": out.get("candidates"),
                "params_used": out.get("params_used"),
                "degraded": bool(out.get("degraded")),
            },
        )
    except Exception as exc:  # noqa: BLE001 - 绝不把 HTML/纯文本错误页抛给前端
        log.exception("square-crop 未预期异常")
        return _err(500, "INTERNAL", f"{type(exc).__name__}: {exc}")
