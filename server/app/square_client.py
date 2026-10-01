"""`square-crop` 端点 → worker 解释器的**子进程桥**——Kong。

## 为什么必须走子进程（而不是在本进程里 import cv2）

规范 §6.5 解释器矩阵：接口层 `server/.venv` **只有 fastapi/uvicorn/pydantic**（无 cv2 / numpy / pymupdf），
图像栈只存在于 `feicui/venv`（worker 解释器）。这与 `app/pdfmeta.py` 的处理**同构**：
  * 能就地做就就地做；
  * 做不了（本单＝需要 cv2）⇒ **子进程**调 `feicui/venv/bin/python`，结果按**标记行**解析。

本模块**不碰 DB、不建 job、不落任何文件**：只把上传字节交给一条**一次性**子进程算完取回 JSON。
进程用完即退（无守护、无池、无进程内状态），符合 §1.1 / §3.2 S-4「接口层不落业务真值」。
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

from .config import Settings

RUNNER = Path(__file__).resolve().parent / "square_runner.py"
MARKER = "FEICUI_SQUARE="
DEFAULT_TIMEOUT_S = 60.0


class RunnerError(RuntimeError):
    """子进程桥的任何失败（都可映射成结构化 500 错误体）。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def run_square_crop(
    st: Settings,
    image_bytes: bytes,
    req_params: dict,
    *,
    quality: int,
    max_side: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """把上传字节 + 参数交给 `square_runner.py`（worker 解释器）算一遍，返回其 JSON 结果。

    抛 `RunnerError` 的情形（调用侧一律落 500，带可读 `reason`）：
      * `RUNNER_PYTHON_MISSING`：worker 解释器不存在（§6.5）；
      * `RUNNER_TIMEOUT` / `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`。
    """
    py = Path(st.worker_python)
    if not py.is_file():
        raise RunnerError("RUNNER_PYTHON_MISSING", f"worker 解释器不存在：{py}")
    payload = dict(req_params)
    payload.update(
        {
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
            "quality": int(quality),
            "max_side": int(max_side),
        }
    )
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
