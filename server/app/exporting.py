"""E4 导出触发层（阶段 1b-ii）——Kong。

**规范锚点**：§3.1 E4（`POST /api/jobs/{job_id}/export`，请求 `{batch_id?, book_code?, dry_run?}`，
响应 `{batch_id, package_dir, counts:{formal,draft,rejected}, selfcheck_ref}`）、§3.3 §9.6
（**交付单位 = 一本书 = 一个批次**；**首版仍走本地目录** `feicui/exports/fb_…`，不得改用远端通道）、
§6.5 解释器矩阵（派生计算走 **worker 侧解释器**）。

**实现口径（本单取法，未静默）**：
  * **只调用现成的 `export.py` CLI**（派单硬约束；`export.py` 一行未改），参数＝`export --book <pdf_name>`；
  * 子进程环境变量显式注入 `FEICUI_DB` / `FEICUI_EXPORT_ROOT` / `FEICUI_CONFIG_DIR`，使导出的
    读库与落点＝**接口层当前的库与导出根**（自测把导出根指向临时目录 ⇒ **不污染 `exports/` 既有 12 个批次包**）；
  * `batch_id` 由 `export.py` 自己派生（`fb_YYYYMMDD_<简码>_NN`）⇒ 请求体带了 `batch_id` 一律 `400`
    （**不臆造批次号**，与 §3.3 纪律同源）；
  * `dry_run` 规范未定义、`export.py` 亦无该模式 ⇒ `true` 一律 `400`（**不假装跑过**）；
  * `book_code` 可选：与 `config/book_codes.json` 中本书记录比对，不一致 ⇒ `400`；一致 ⇒ 无副作用（透传校验）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger("feicui.api.exporting")

EXPORT_LINE_RE = re.compile(r"^\[export\]\s+(\S+)\s+→\s+(\S+)", re.M)


class ExportFailed(RuntimeError):
    """`export.py` 非零退出 / 超时 / 产物不可解析 ⇒ 路由层落 `500`（§3.4 500 纪律）。"""


def book_code_entry(config_dir: Path, pdf_name: str) -> dict[str, Any]:
    """读 `config/book_codes.json` 取本书记录（**只读**，缺文件 / 缺书 ⇒ `{}`）。"""
    path = Path(config_dir) / "book_codes.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("book_codes.json 读取失败：%s", exc)
        return {}
    books = data.get("books") or {}
    entry = books.get(pdf_name)
    return dict(entry) if isinstance(entry, dict) else {}


def run_export(
    *,
    db_path: Path,
    export_root: Path,
    export_script: Path,
    config_dir: Path,
    python_bin: Path,
    pdf_name: str,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """调 `export.py export --book <pdf_name>`，返回 E4 的 4 字段 + 自测用的诊断字段。"""
    if not Path(export_script).is_file():
        raise ExportFailed(f"export.py 不存在：{export_script}")
    if not Path(python_bin).is_file():
        raise ExportFailed(f"worker 侧解释器不存在（§6.5）：{python_bin}")

    export_root = Path(export_root)
    export_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["FEICUI_DB"] = str(db_path)
    env["FEICUI_EXPORT_ROOT"] = str(export_root)
    env["FEICUI_CONFIG_DIR"] = str(config_dir)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = [str(python_bin), str(export_script), "export", "--book", pdf_name]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            cwd=str(Path(export_script).resolve().parent),
        )
    except subprocess.TimeoutExpired as exc:
        raise ExportFailed(f"export.py 超时（>{timeout_s}s）") from exc

    stdout, stderr = proc.stdout or "", proc.stderr or ""
    if proc.returncode != 0:
        # 详细原因只进服务端日志（§3.4：500 体不得回吐堆栈 / 绝对路径）
        log.error("export.py 失败 rc=%s\nstdout=%s\nstderr=%s", proc.returncode, stdout[-2000:], stderr[-2000:])
        raise ExportFailed(f"export.py 退出码 {proc.returncode}")

    m = EXPORT_LINE_RE.search(stdout)
    if not m:
        log.error("export.py 输出不可解析：%s", stdout[-2000:])
        raise ExportFailed("export.py 输出不可解析（未找到 `[export] <batch_id> → <dir>` 行）")
    batch_id, pkg_from_stdout = m.group(1), m.group(2)

    pkg_dir = export_root / batch_id
    report_path = pkg_dir / "report.json"
    if not report_path.is_file():
        raise ExportFailed(f"批次包缺 report.json：{pkg_dir}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    counts = ((report.get("counts") or {}).get("feicuiDecidable") or {})
    package_dir = str(((report.get("package") or {}).get("dir")) or pkg_from_stdout)

    selfcheck = export_root / "selfcheck_report.json"
    return {
        "batch_id": batch_id,
        "package_dir": package_dir,
        "counts": {
            "formal": int(counts.get("formal", 0)),
            "draft": int(counts.get("draftStaged", 0)),
            "rejected": int(counts.get("rejectedRequiredMissing", 0)),
        },
        "selfcheck_ref": str(selfcheck) if selfcheck.is_file() else None,
        # ---- 以下仅供自测留证，不进 E4 响应体（响应体严格 4 字段）----
        "_diag": {
            "cmd": cmd,
            "rc": proc.returncode,
            "pkg_dir": str(pkg_dir),
            "stdout_tail": stdout.strip().splitlines()[-3:],
            "jsonl": report.get("jsonl"),
            "counts_feicuiDecidable": counts,
        },
    }
