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
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import multipart as mpart
from .. import square
from ..config import get_settings
from ..enhance_client import RunnerError as EnhanceRunnerError
from ..enhance_client import run_enhance
from ..square_client import RunnerError, run_square_crop

log = logging.getLogger("feicui.api.tools")

router = APIRouter(prefix="/api/tools", tags=["tools"])

# 上传上限：本机 dev 用途（玺爱新增印章时的单张印面图，真实样本 30KB～120KB）。超限 ⇒ 400（不建临时文件）。
MAX_UPLOAD_BYTES = 32 * 1024 * 1024

# ---- `POST /api/tools/enhance`（图片高清化＝成品化）冻结契约 ----
ENHANCE_WIDTH_DEFAULT = 1200     # 默认成品**宽度**
ENHANCE_WIDTH_MIN = 200          # 合法区间下界
ENHANCE_WIDTH_MAX = 4000         # 合法区间上界
ENHANCE_BACKGROUNDS = ("paper", "plain_white")   # ＝ seal_canvas.BACKGROUND_MODES（同名同值）


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


@router.post("/enhance")
async def enhance(request: Request) -> JSONResponse:
    """**图片高清化（成品化）**：`multipart/form-data`（文件字段名 `image`）→ JSON（成品 PNG ＋ 读数）。

    入参：`image`（必填）、`width`（默认 1200，区间 [200, 4000]＝**成品宽度**）、
    `background`（`paper` 宣纸底纹｜`plain_white` 纯白，默认 `paper`）。

    出参 200：`ok` / `mime` / `bytes` / `sha256` / `image_base64` / `width` / `height` /
    `source{width,height,mode,bytes,sha256}` / `params_used{width,background,caliber,subject_ratio,seed,
    halo_policy}` / `readings`（`compose()` 原样）/ `elapsed_ms`。

    口径：**算法＝`app/seal_canvas.py` 的唯一实现**（worker 子进程里跑）；本端点只做参数校验与错误归一化。
    本端点**不承诺**提升真实分辨率（唯一像素变换＝Lanczos 几何重采样）。
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
            width = _opt_int(fields, "width", ENHANCE_WIDTH_DEFAULT)
            if not (ENHANCE_WIDTH_MIN <= width <= ENHANCE_WIDTH_MAX):
                raise _BadParam(
                    f"width 越界：{width}（须在 [{ENHANCE_WIDTH_MIN}, {ENHANCE_WIDTH_MAX}]，单位 px，指成品**宽度**）"
                )
            background = str(fields.get("background") or "paper").strip() or "paper"
            if background not in ENHANCE_BACKGROUNDS:
                raise _BadParam(f"background 只能是 {list(ENHANCE_BACKGROUNDS)}，收到 {background!r}")
        except _BadParam as exc:
            return _err(400, "BAD_PARAM", str(exc))

        t0 = time.perf_counter()
        try:
            out = run_enhance(st, image_bytes, width=width, background=background)
        except EnhanceRunnerError as exc:
            log.warning("enhance 子进程失败：%s", exc)
            return _err(500, exc.code, f"图像处理子进程失败：{exc.detail}")
        elapsed_ms = int(round((time.perf_counter() - t0) * 1000))

        if not out.get("ok"):
            code = str(out.get("error") or "INTERNAL")
            detail = str(out.get("detail") or code)
            if code == "BAD_IMAGE":
                return _err(
                    400,
                    "BAD_IMAGE",
                    f"上传内容不是可解码的图片（PNG/JPEG/WebP/TIFF 等 PIL 可解码格式）：{detail}",
                )
            if code == "NO_INK":
                return _err(
                    422,
                    "NO_INK",
                    "图上检测不到印泥像素（红色掩膜为空）⇒ 不可成品化；请上传含红色印泥的印章图。",
                    runner_detail=detail,
                )
            if code in ("BAD_REQUEST", "BAD_PARAM"):
                return _err(400, "BAD_PARAM", detail)
            log.warning("enhance 子进程返回失败：%s / %s", code, detail)
            return _err(500, "INTERNAL", f"图像处理子进程返回 {code}：{detail}")

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "mime": out.get("mime", "image/png"),
                "bytes": int(out["bytes"]),
                "sha256": out["sha256"],
                "image_base64": out["image_base64"],
                "width": int(out["width"]),
                "height": int(out["height"]),
                "source": out.get("source"),
                "params_used": out.get("params_used"),
                "readings": out.get("readings"),
                "elapsed_ms": elapsed_ms,
            },
        )
    except Exception as exc:  # noqa: BLE001 - 绝不把 HTML/纯文本错误页抛给前端
        log.exception("enhance 未预期异常")
        return _err(500, "INTERNAL", f"{type(exc).__name__}: {exc}")
