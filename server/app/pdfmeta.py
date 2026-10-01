"""PDF 页数派生（E1 的 `total_pages` 来源）——Kong / 阶段 1a。

规范锚点：§3.1 E1（`total_pages` 是 201 响应的必填形状）、§3.2 S-6（**必填字段不可派生 ⇒ 422**）、
§1.2 I-1（解析仍是同一份 Python 实现 ⇒ 优先复用 feicui 自带运行时里的 PyMuPDF）。

两档取数（前者可用即不往后走）：
  1. 本进程内 `import fitz` / `import pymupdf`（server/.venv 若装了 pymupdf 时走这条）；
  2. **子进程**调用 feicui 自带 venv 的 python（`feicui/venv/bin/python`，PyMuPDF **已**在该 venv 内；
     注意该 venv 的 console script 因 shebang 失效，故一律用 `python -c`）；
  3. 都不可用 ⇒ 返回 `None` ⇒ E1 回 **422**（提示显式给 `page_range`）。

**坑（已实测，勿回退）**：PyMuPDF 的 `fitz` 弃用提示 `warning: The \`fitz\` API is deprecated…`
**打在 stdout 而不是 stderr**（本机 pymupdf 1.28.2 实测）——因此子进程回传必须用**标记行**
（`FEICUI_PAGES=`）解析，**不得**对 stdout 直接 `json.loads`（那样会恒失败并静默退化成 422）。
只读 PDF，绝不写、绝不上传。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_MARKER = "FEICUI_PAGES="
_SNIPPET = f"import fitz,sys;d=fitz.open(sys.argv[1]);print('{_MARKER}'+str(d.page_count))"


def _from_inprocess(pdf_path: Path) -> int | None:
    for mod in ("pymupdf", "fitz"):
        try:
            m = __import__(mod)
        except Exception:
            continue
        try:
            with m.open(str(pdf_path)) as doc:
                return int(doc.page_count)
        except Exception:
            return None
    return None


def feicui_venv_python() -> Path | None:
    """feicui 自带 venv 的解释器（可由 `FEICUI_PYTHON` 覆盖）。"""
    override = os.environ.get("FEICUI_PYTHON")
    cand = Path(override) if override else Path(__file__).resolve().parents[2] / "venv" / "bin" / "python"
    return cand if cand.is_file() else None


def _from_feicui_venv(pdf_path: Path) -> int | None:
    py = feicui_venv_python()
    if py is None:
        return None
    try:
        out = subprocess.run(
            [str(py), "-c", _SNIPPET, str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
    except Exception:
        return None
    for line in out.stdout.splitlines():  # 标记行解析：容忍 stdout 上的弃用提示噪声
        line = line.strip()
        if line.startswith(_MARKER):
            try:
                return int(line[len(_MARKER):])
            except ValueError:
                return None
    return None


def pdf_page_count(pdf_path: Path) -> int | None:
    n = _from_inprocess(pdf_path)
    return n if n is not None else _from_feicui_venv(pdf_path)
