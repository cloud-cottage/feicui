"""页级「生成 HighRes」→ worker 解释器的**子进程桥**（接口层）——Kong。

## 为什么必须走子进程

规范 §6.5 解释器矩阵：接口层 `server/.venv` **只有 fastapi/uvicorn/pydantic + PIL**
（`import pymupdf|cv2|numpy|tifffile` 逐个 `ModuleNotFoundError`），整页渲染栈只存在于
`feicui/venv`（worker 解释器）。本模块与 `app/pdfmeta.py` / `app/preview.py` /
`app/square_client.py` **同构**：做不了 ⇒ **一次性子进程**调 `feicui/venv/bin/python`
`server/app/highres_runner.py`，结果按**标记行**（`FEICUI_HIGHRES=`）解析。

本模块**不碰 DB、不建 job、不复制渲染/命名逻辑**：产物落点、预估、幂等判断全在 runner 侧
（那里才有渲染栈与 `config/book_dir_keys.json` 的目录键实现）⇒ 接口层**零**路径规则、**零** cv2/numpy。

## 口径

* `dpi` 白名单 `{1200, 2400}`、默认 **1200**（Kevin 2026-10-16）；
* **页级、幂等**：产物已在盘 ⇒ 不重写，如实报 `existed: true`；`force=true` 才重写；
* **禁无限制整本生成**：runner **拒收**区间字段（`pages`/`page_from`/`page_to`/…）⇒ 400；
* 超时：单页 ≈27 s@1200 / ≈108 s@2400（实测）⇒ 默认 **900 s**（env `FEICUI_HIGHRES_TIMEOUT_S` 可改）；
* 错误面与 `E9/E10` 同族：`BAD_PARAM` / `JOB_NOT_FOUND` / `PDF_MISSING` / `PAGE_OUT_OF_PDF` /
  `PDF_NO_IMAGE` / `DISK_INSUFFICIENT` / `RUNNER_*` / `RENDER_FAILED`。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .config import Settings

RUNNER = Path(__file__).resolve().parent / "highres_runner.py"
MARKER = "FEICUI_HIGHRES="
DEFAULT_TIMEOUT_S = 900.0            # 单页 1200dpi 实测 ≈27 s、2400dpi ≈108 s ⇒ 留足余量
ENV_TIMEOUT = "FEICUI_HIGHRES_TIMEOUT_S"

#: `dpi` 白名单（与 runner 侧同源；非白名单 ⇒ 接口层 400，**不**起子进程）
DPI_WHITELIST: tuple[int, ...] = (1200, 2400)
DPI_DEFAULT = 1200


class RunnerError(RuntimeError):
    """子进程桥的任何失败（都可映射成结构化 500 错误体，码族＝§3.14 五码）。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def timeout_s() -> float:
    """本次调用的超时（env 可改；非法值回落默认，不静默变 NaN）。"""
    raw = os.environ.get(ENV_TIMEOUT)
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_S


def run_highres(
    st: Settings,
    *,
    pdf_path: Path,
    page: int,
    dpi: int,
    force: bool = False,
    estimate_only: bool = False,
    timeout: float | None = None,
) -> dict:
    """把一次「生成 HighRes」交给 `highres_runner.py`（worker 解释器）算一遍，返回其 JSON 结果。

    **长跑**：1200dpi 单页 ≈27 s、2400dpi ≈108 s（实测）；`estimate_only` 只读页几何（<2 s）。
    抛 `RunnerError`（调用侧一律落 500，码族＝§3.14）：`RUNNER_PYTHON_MISSING` /
    `RUNNER_TIMEOUT` / `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`。
    """
    py = Path(st.worker_python)
    if not py.is_file():
        raise RunnerError("RUNNER_PYTHON_MISSING", f"worker 解释器不存在：{py}")
    payload = {
        "pdf_path": str(pdf_path),
        "page": int(page),
        "dpi": int(dpi),
        "force": bool(force),
        "estimate_only": bool(estimate_only),
    }
    env = os.environ.copy()
    env["FEICUI_ROOT"] = str(st.root)
    env["PYTHONUNBUFFERED"] = "1"
    tmo = float(timeout) if timeout else timeout_s()
    try:
        proc = subprocess.run(  # noqa: S603 - 路径来自配置，非用户输入
            [str(py), str(RUNNER)],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            cwd=str(st.root),
            env=env,
            timeout=tmo,
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("RUNNER_TIMEOUT", f"worker 子进程超时（>{tmo:g}s）") from exc

    stdout = proc.stdout.decode("utf-8", "replace")
    line = next((ln for ln in stdout.splitlines() if ln.startswith(MARKER)), None)
    if line is None:
        tail = (proc.stderr.decode("utf-8", "replace") or "")[-800:]
        if proc.returncode != 0:
            raise RunnerError("RUNNER_EXIT_NONZERO",
                              f"worker 子进程 exit={proc.returncode}；stderr 尾部：{tail}")
        raise RunnerError("RUNNER_NO_OUTPUT", f"worker 子进程未输出标记行；stderr 尾部：{tail}")
    try:
        out = json.loads(line[len(MARKER):])
    except Exception as exc:  # pragma: no cover - 只可能是 runner 自身 bug
        raise RunnerError("RUNNER_BAD_OUTPUT", f"标记行不是合法 JSON：{exc!r}") from exc
    if not isinstance(out, dict):
        raise RunnerError("RUNNER_BAD_OUTPUT", "标记行 JSON 不是对象")
    return out
