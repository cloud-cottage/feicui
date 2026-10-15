#!/usr/bin/env python
"""页级「生成 HighRes」（整页 dpi 参数化大图）的 **worker 侧执行体**（一次性子进程，stdin → stdout）——Kong。

**必须**由 `feicui/venv/bin/python` 运行：渲染栈（PyMuPDF / cv2 / numpy / tifffile）只在该 venv 内，
接口层 `server/.venv` **无**这些包（规范 §6.5 解释器矩阵）。**cwd 必须是 `<feicui>/` 根**
（`config/`、`output/` 的相对路径口径）。形态照 `preview_runner.py` / `square_runner.py` 先例：
stdin 读一行 JSON → stdout **只**输出一行带标记前缀的 JSON（`FEICUI_HIGHRES=`）→ 诊断走 stderr。

它**只做页级**、与 jobs 体系无关（红线：**零 DB 写、不建 job、不动 inbox/`output/books`**）：

  * 产物落 `output/2_HighRes_PDF/<目录键>/P<页>-<dpi>dpi-48bit.tif`（目录键＝`config/book_dir_keys.json`）；
  * **幂等**：产物已在盘 ⇒ 不重写、如实报 `existed: true`；只有 `force: true` 才重写；
  * **禁无限制整本生成**：本执行体**只接受单页**（`page` 一个整数，**拒收** `pages` / `page_to` /
    `page_from` 之类区间字段）⇒ 请求里出现这些键一律 `BAD_REQUEST`；响应里另附**整本算账**
    （851 页 ≈ 404 GB / ≈6.4 h）供 UI 明示；
  * **容量闸**：落盘前要求空闲空间 ≥ 预估体积 × `FREE_SPACE_FACTOR`，不足 ⇒ `DISK_INSUFFICIENT`；
  * `estimate_only: true` ⇒ 只算不渲染（供 GET 预估；
    仍会读 PDF 页几何 ⇒ 需要 worker 解释器）。

请求（一行 JSON）：
  {"pdf_path": "<绝对或相对 feicui/ 的路径>", "page": 29, "dpi": 1200,
   "force": false, "estimate_only": false}

响应（成功）：
  {"ok": true, "page": 29, "dpi": 1200, "pdf_name": "秦印类编 检索版.pdf", "dir_key": "9787550847224",
   "out_path": "...", "out_rel": "output/2_HighRes_PDF/.../P29-1200dpi-48bit.tif",
   "out_bytes": ..., "out_gib": ..., "written": true, "existed": false,
   "geometry": {...}, "estimate": {...}, "container": {...}, "seconds": {...}, "force": false}

错误码（**只出这几个**）：
  `BAD_REQUEST`（缺字段 / 类型不对 / 传了区间字段）· `PDF_MISSING` · `PAGE_OUT_OF_PDF` ·
  `PDF_NO_IMAGE`（该页无内嵌图像）· `DISK_INSUFFICIENT` · `RENDER_FAILED` · `INTERNAL`。
"""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import shutil
import sys
import time
from pathlib import Path

MARKER = "FEICUI_HIGHRES="

HERE = Path(__file__).resolve()                      # <feicui>/server/app/highres_runner.py
SERVER_DIR = HERE.parents[1]                         # <feicui>/server
ROOT = Path(os.environ.get("FEICUI_ROOT") or SERVER_DIR.parent).resolve()
for _p in (str(ROOT), str(SERVER_DIR)):              # app.* 在 SERVER_DIR；processor 在 ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(ROOT)                                       # 相对路径口径（config/、output/）

RENDER_SCRIPT = ROOT / "ops" / "book-page-2400" / "render_page_2400.py"

# ── 预估常量（皆**实测单点**，不是外推；改动要同步写在响应里）────────────────────────
SEC_PER_MPX = 0.26              # 实测：2400dpi 整页 416 Mpx ⇒ 108.12 s（处理 82.47 + 写 25.53）
DEFLATE_RATIO = 0.7627          # 实测：1.773 GiB / 2.325 GiB（48bit Deflate+Predictor2）
FREE_SPACE_FACTOR = 1.5         # 落盘前的容量闸：空闲空间 ≥ 预估体积 × 1.5
BOOK_PAGES_DEFAULT = 851        # 《秦印类编 检索版》页数（「整本不可行」算账用）
DPI_WHITELIST: tuple[int, ...] = (1200, 2400)
DPI_DEFAULT = 1200


def log(msg: str) -> None:
    print(f"[highres_runner {os.getpid()}] {msg}", file=sys.stderr, flush=True)


class HighresError(RuntimeError):
    """worker 侧可读失败（调用侧映射成结构化错误体）。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def load_render_module():
    """按**文件路径**载入 `ops/book-page-2400/render_page_2400.py`（**同一份渲染实现，不复制**）。

    ★ 必须先注册进 `sys.modules` 再 `exec_module` —— 该模块带 `@dataclass Ctx`，
    `dataclasses` 靠 `sys.modules[cls.__module__]` 解析注解，未注册即
    `AttributeError: 'NoneType' object has no attribute '__dict__'`（本仓 P0 教训）。
    """
    name = "feicui_highres_render_module"
    spec = importlib.util.spec_from_file_location(name, RENDER_SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise HighresError("INTERNAL", f"载入渲染模块失败：{RENDER_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def human(gib: float) -> str:
    return f"{gib:.3f} GiB"


def main() -> int:
    t_start = time.time()
    payload: dict = {}
    try:
        req = json.loads(sys.stdin.read() or "{}")
        if not isinstance(req, dict):
            raise HighresError("BAD_REQUEST", f"请求必须是 JSON 对象：{type(req).__name__}")
        payload = process(req)
    except HighresError as exc:
        payload = {"ok": False, "error": exc.code, "detail": exc.detail}
    except (KeyError, TypeError, ValueError) as exc:
        payload = {"ok": False, "error": "BAD_REQUEST", "detail": f"请求字段非法：{exc!r}"}
    except Exception as exc:  # noqa: BLE001 - 任何异常都必须是可解析的 JSON
        log(f"未预期异常：{exc!r}")
        payload = {"ok": False, "error": "INTERNAL", "detail": f"{type(exc).__name__}: {exc}"}
    payload["runner_seconds"] = round(time.time() - t_start, 2)
    sys.stdout.write(MARKER + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def process(req: dict) -> dict:
    # ---- ① 拒收「整本 / 区间」字段（**禁无限制整本生成**）----
    for k in ("pages", "page_from", "page_to", "page_range", "all_pages"):
        if k in req:
            raise HighresError(
                "BAD_REQUEST",
                f"本端点只做**页级**（单页 {k!r} 被拒）：整本不可行 —— 1200dpi 48bit 整页未压缩 "
                f"8500×12236×6 B = 624 MB（deflate ≈475 MB）⇒ {BOOK_PAGES_DEFAULT} 页 ≈ "
                f"{BOOK_PAGES_DEFAULT * 0.475:.0f} GB / ≈{BOOK_PAGES_DEFAULT * 27 / 3600:.1f} h",
            )

    pdf_path = Path(str(req.get("pdf_path") or ""))
    if not str(pdf_path):
        raise HighresError("BAD_REQUEST", "缺 pdf_path")
    if not pdf_path.is_absolute():
        pdf_path = ROOT / pdf_path
    if not pdf_path.is_file():
        raise HighresError("PDF_MISSING", f"pdf_path 不在盘上：{pdf_path}")

    page = int(req.get("page"))
    if page < 1:
        raise HighresError("BAD_REQUEST", f"page 必须 >= 1（1-based）：{page}")
    dpi = int(req.get("dpi", DPI_DEFAULT))
    if dpi not in DPI_WHITELIST:
        raise HighresError("BAD_REQUEST", f"dpi 不在白名单 {list(DPI_WHITELIST)} 内：{dpi}")
    force = bool(req.get("force", False))
    estimate_only = bool(req.get("estimate_only", False))

    rp = load_render_module()

    # ---- ② 页数预检（★ 必须在 `load_scan` **之前**：越界时 load_scan 抛 IndexError 会被误包成
    #        RENDER_FAILED(500)，而契约要求 404 `PAGE_OUT_OF_PDF` —— 2026-10-16 实测抓获）----
    try:
        pdf_pages = int(rp.pymupdf.open(str(pdf_path)).page_count)
    except Exception as exc:  # noqa: BLE001
        raise HighresError("RENDER_FAILED", f"打开 PDF 失败：{type(exc).__name__}: {exc}") from exc
    if page > pdf_pages:
        raise HighresError("PAGE_OUT_OF_PDF", f"page={page} 超出 PDF 实际页数 {pdf_pages}")

    # ---- ③ 页几何 + 目标几何（同一份实现里派生，别处不得另立）----
    try:
        src, xref, meta = rp.load_scan(pdf_path, page)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "没有内嵌图像" in msg:
            raise HighresError("PDF_NO_IMAGE", msg) from exc
        raise HighresError("RENDER_FAILED", f"读源扫描图失败：{type(exc).__name__}: {msg}") from exc

    geom = rp.configure_geometry(dpi, meta["src_px"][0], meta["src_px"][1], None, meta["scan_dpi"])
    dir_key = rp.dir_key_of(pdf_path.name)
    out_abs = (ROOT / rp.out_rel(dir_key, page, dpi)).resolve()

    out_w, out_h = geom["out_px"]
    raw_bytes = int(out_w * out_h * 3 * 2)
    est_bytes = int(raw_bytes * DEFLATE_RATIO)
    est = {
        "out_px": [out_w, out_h], "raw_uncompressed_bytes": raw_bytes,
        "expected_bytes": est_bytes, "expected_gib": round(est_bytes / 2**30, 3),
        "expected_seconds": round(out_w * out_h / 1e6 * SEC_PER_MPX, 1),
        "basis": {"sec_per_mpx": SEC_PER_MPX, "deflate_ratio": DEFLATE_RATIO,
                  "note": "单点实测（2400dpi 416 Mpx / 108.12 s；1.773GiB÷2.325GiB），非外推"},
        "whole_book_refusal": {
            "pages": BOOK_PAGES_DEFAULT,
            "bytes": int(BOOK_PAGES_DEFAULT * est_bytes),
            "gib": round(BOOK_PAGES_DEFAULT * est_bytes / 2**30, 1),
            "hours": round(BOOK_PAGES_DEFAULT * (out_w * out_h / 1e6 * SEC_PER_MPX) / 3600, 1),
            "note": "整本生成**被禁止**（本端点只做页级）；此数为算账，供 UI 明示",
        },
    }
    base = {
        "ok": True, "page": page, "dpi": dpi, "pdf_name": pdf_path.name, "dir_key": dir_key,
        "pdf_path": str(pdf_path), "pdf_page_count": pdf_pages, "xref": int(xref),
        "source": meta, "out_path": str(out_abs),
        "out_rel": str(out_abs.relative_to(ROOT)) if str(out_abs).startswith(str(ROOT)) else str(out_abs),
        "geometry": geom, "estimate": est, "force": force,
    }

    # ---- ③ estimate_only：只算不渲染（GET 预估用）----
    if estimate_only:
        exists = out_abs.is_file()
        return {**base, "estimate_only": True, "existed": bool(exists), "written": False,
                "out_bytes": int(out_abs.stat().st_size) if exists else None,
                "free_bytes": int(shutil.disk_usage(str(ROOT)).free)}

    # ---- ④ 幂等：已在盘且未 force ⇒ 不重写 ----
    if out_abs.is_file() and not force:
        return {**base, "existed": True, "written": False, "out_bytes": int(out_abs.stat().st_size),
                "out_gib": round(out_abs.stat().st_size / 2**30, 3),
                "note": "产物已存在（幂等：不重写）；要重出请显式 force=true"}

    # ---- ⑤ 容量闸（落盘前）----
    free = int(shutil.disk_usage(str(ROOT)).free)
    if free < est_bytes * FREE_SPACE_FACTOR:
        raise HighresError(
            "DISK_INSUFFICIENT",
            f"空闲空间不足：{human(free / 2**30)} < 预估 {human(est_bytes / 2**30)} × "
            f"{FREE_SPACE_FACTOR}（不先写满盘）",
        )

    # ---- ⑥ 真渲染（同一份实现；裁件不涉及）----
    ctx = rp.build_ctx(src, rp.COLOR_CALIB_DEFAULT)
    t0 = time.time()
    try:
        res = rp.render_page(ctx, out_abs, crop_box=None,
                             description=rp.image_description(page, dpi))
    except Exception as exc:  # noqa: BLE001
        raise HighresError("RENDER_FAILED", f"渲染失败：{type(exc).__name__}: {exc}") from exc
    res.pop("preview", None)
    res.pop("crop", None)
    if not out_abs.is_file():
        raise HighresError("RENDER_FAILED", f"渲染返回成功但产物不在盘上：{out_abs}")

    try:
        container = rp.container_tags(out_abs)
    except Exception as exc:  # noqa: BLE001
        container = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        **base, "existed": False, "written": True,
        "out_bytes": int(out_abs.stat().st_size), "out_gib": round(out_abs.stat().st_size / 2**30, 3),
        "container": container, "render": {k: v for k, v in res.items() if k != "strip_stats"},
        "seconds": {"processing": res.get("processing_seconds"), "write": res.get("write_seconds"),
                    "total": round(time.time() - t0, 2)},
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "verify_note": ("本端只读回容器 tags 自证（shape/位深/dpi tag/压缩）；整页逐条验证走 CLI "
                        "ops/book-page-2400/render_page_2400.py --verify-only"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
