"""E9 / E10「文档预览」→ worker 解释器的**子进程桥**（接口层）——Kong。

## 为什么必须走子进程（与本进程里 import 无关）

规范 §6.5 解释器矩阵 / 待裁项 R-1：接口层 `server/.venv` **只有 fastapi/uvicorn/pydantic + PIL**
（`import pymupdf|cv2|numpy` 逐个 `ModuleNotFoundError`），渲染与检测栈只存在于 `feicui/venv`
（worker 解释器）。这与 `app/pdfmeta.py` / `app/square_client.py` 的处理**同构**：做不了 ⇒
**一次性子进程**调 `feicui/venv/bin/python`，结果按**标记行**（`FEICUI_PREVIEW=`）解析。

本模块**不碰 DB 写、不建 job、不落任何文件**：PNG 字节经 base64 从子进程 stdout 回传，**不落盘**
（§2.5 红线 ②）。检测算法只有一份（在 worker 侧 `processor.py`），本文件**零检测代码**、
**零 cv2/numpy/pymupdf import**（§2.5 红线 ③）。

## 口径（逐条照 `docs/page-preview-draft-v0.1.md` §2）

* `dpi` 白名单 `{72, 110, 150}`、默认 **110**（§2.6）；
* 每页超时 **20 s**（§2.5 红线 ⑤）；
* 错误面：`BAD_PARAM` / `JOB_NOT_FOUND` / `PDF_MISSING` / `PAGE_OUT_OF_PDF` /
  `RUNNER_*`（§3.14 五码）/ `RENDER_FAILED`（§2.1）；
* `db.stamp_rows` 是**只读对照**（该 `(pdf_name,page)` 在 `stamps` 的行数）——框**不来自 DB**。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import db
from .config import Settings

RUNNER = Path(__file__).resolve().parent / "preview_runner.py"
MARKER = "FEICUI_PREVIEW="
DEFAULT_TIMEOUT_S = 20.0                     # §2.5 红线 ⑤：每页 20 s 超时

#: `dpi` 白名单（§2.6 默认 110；非白名单 ⇒ 接口层 400 BAD_PARAM，**不**起子进程）
DPI_WHITELIST: tuple[int, ...] = (72, 110, 150)
DPI_DEFAULT = 110


class RunnerError(RuntimeError):
    """子进程桥的任何失败（都可映射成结构化 500 错误体，码族＝§3.14 五码）。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def run_preview(
    st: Settings,
    *,
    pdf_path: Path,
    page: int,
    dpi: int,
    png: bool,
    detect: bool,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """把一次预览请求交给 `preview_runner.py`（worker 解释器）算一遍，返回其 JSON 结果。

    抛 `RunnerError` 的情形（调用侧一律落 500，码族＝§3.14）：
      * `RUNNER_PYTHON_MISSING`：worker 解释器不存在（§6.5）；
      * `RUNNER_TIMEOUT`（> 20 s）/ `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`。
    """
    py = Path(st.worker_python)
    if not py.is_file():
        raise RunnerError("RUNNER_PYTHON_MISSING", f"worker 解释器不存在：{py}")
    payload = {
        "pdf_path": str(pdf_path),
        "page": int(page),
        "dpi": int(dpi),
        "png": bool(png),
        "detect": bool(detect),
    }
    env = os.environ.copy()
    env["FEICUI_ROOT"] = str(st.root)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.run(  # noqa: S603 - 路径来自配置，非用户输入
            [str(py), str(RUNNER)],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            cwd=str(st.root),
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("RUNNER_TIMEOUT", f"worker 子进程超时（>{timeout_s:g}s）") from exc

    stdout = proc.stdout.decode("utf-8", "replace")
    line = next((ln for ln in stdout.splitlines() if ln.startswith(MARKER)), None)
    if line is None:
        tail = (proc.stderr.decode("utf-8", "replace") or "")[-500:]
        if proc.returncode != 0:
            raise RunnerError("RUNNER_EXIT_NONZERO", f"worker 子进程 exit={proc.returncode}；stderr 尾部：{tail}")
        raise RunnerError("RUNNER_NO_OUTPUT", f"worker 子进程未输出标记行；stderr 尾部：{tail}")
    try:
        out = json.loads(line[len(MARKER):])
    except Exception as exc:  # pragma: no cover - 只可能是 runner 自身 bug
        raise RunnerError("RUNNER_BAD_OUTPUT", f"标记行不是合法 JSON：{exc!r}") from exc
    if not isinstance(out, dict):
        raise RunnerError("RUNNER_BAD_OUTPUT", "标记行 JSON 不是对象")
    return out


def stamp_rows(db_path: Path | str, pdf_name: str, page: int) -> int:
    """`(pdf_name, page)` 在 `stamps` 的行数（**只读对照**，§2.1：框不来自 DB）。

    只读 `COUNT(*)`（§2.5 红线 ①「只读 `COUNT(*)` 允许」）；`db.ro` 是只读连接
    （`file:<path>?mode=ro`），物理上写不进去。
    """
    with db.ro(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM stamps WHERE pdf_name = ? AND page = ?",
            (pdf_name, int(page)),
        ).fetchone()
    return int(row["n"] if row is not None else 0)
