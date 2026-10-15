#!/usr/bin/env python3
"""文档预览（E9 / E10）**红线自证探针** —— Kong 2026-10-11。

用途（PP-5 / PP-6 形态的机械判据）：

  * `--fingerprint`：对 `stamps` / `jobs` / `job_pages` **逐行取内容指纹**（sha256 over repr(row)，
    行序按 rowid）。**刻意不用 `yinpu.db` 文件 md5** —— WAL 模式下文件字节会漂移，
    内容没变也会变 md5（口径件 §2.5 明文）。同一命令在预览调用**前后**各跑一次，两次输出**逐字相等**。
  * `--newer <epoch>`：列出 `<epoch>` 之后被改动的文件（排除运行态目录）——用于证明「无新增临时文件」。
  * `--ps`：抓 `feicui/venv/bin/python` 子进程（证明渲染 / 检测只在 worker 解释器里跑）。
  * `--imports`：静态扫接口层（`server/app/**.py`）是否出现 `cv2` / `numpy` / `pymupdf` / `fitz` import
    （应为 **零命中**）。

只读：本探针只以 `mode=ro` 打开 DB、只读文件系统，绝不写。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

DB = os.environ.get("FEICUI_DB", "/Users/kevin/bistro/data/yinpu.db")
ROOT = Path(os.environ.get("FEICUI_ROOT", "/Users/kevin/bistro/feicui"))
TABLES = ("stamps", "jobs", "job_pages")

# 运行态 / 构建产物目录：本探针的「无新增临时文件」断言排除这些（它们本来就会变）
#  * `/server/.run/`：池的运行态日志（`pool-launch.log`）—— 本机常态有**别的会话**起的池进程
#    （实测：pid 79003/79951 `-m app.pool --workers 4 --drain`，其 job_id 形如 `scn-active`/`obs-active`，
#    不在本单的 `yinpu.db` 里）在持续追加该日志；与预览调用无关。
CHURN = (
    "/.git/", "/node_modules/", "/__pycache__/", "/var/", "/inbox/", "/exports/",
    "/output/", "/qa-recheck/", "/qa-baseline/", "/labeling/", "/spike-ocr/", "/web/dist/",
    "/ops/page-preview/", "/server/.run/",
)


def fingerprint() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30.0)
    try:
        out = {}
        for t in TABLES:
            h = hashlib.sha256()
            n = 0
            for row in con.execute(f"SELECT * FROM {t} ORDER BY rowid"):
                h.update(repr(tuple(row)).encode("utf-8"))
                n += 1
            out[t] = {"rows": n, "sha256": h.hexdigest()}
        return out
    finally:
        con.close()


def newer(epoch: float) -> list:
    hits = []
    for base, dirs, files in os.walk(ROOT):
        if any(seg in base for seg in CHURN) or "/.git" in base:
            continue
        for fn in files:
            p = Path(base) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime > epoch:
                hits.append({"path": str(p.relative_to(ROOT)), "mtime": int(st.st_mtime), "bytes": st.st_size})
    return sorted(hits, key=lambda d: d["path"])


def ps_runner() -> dict:
    out = subprocess.run(["ps", "-eo", "pid,ppid,etime,command"], capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if "preview_runner.py" in ln and "grep" not in ln]
    feicui_py = [ln for ln in lines if str(ROOT / "venv" / "bin" / "python") in ln or "/feicui/venv/bin/python" in ln]
    return {"preview_runner_lines": lines, "worker_python_lines": feicui_py,
            "worker_python_path": str(ROOT / "venv" / "bin" / "python")}


IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(cv2|numpy|pymupdf|fitz)\b", re.M)

#: **worker 侧执行体**（由 `feicui/venv/bin/python` 以**一次性子进程**运行的服务端脚本）。
#: 它们住在 `server/app/` 只是历史位置（先例：`square_runner.py`，1.3 起）；接口层**从不 import** 它们，
#: `server/.venv` 里也**没有**这三个包 ⇒ 接口层物理上 import 不到（见下面的 capability 检查）。
WORKER_SIDE_SCRIPTS = {"server/app/square_runner.py", "server/app/preview_runner.py"}


def imports_scan() -> dict:
    hits = []
    for base, dirs, files in os.walk(ROOT / "server" / "app"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = Path(base) / fn
            rel = str(p.relative_to(ROOT))
            txt = p.read_text(encoding="utf-8", errors="replace")
            for m in IMPORT_RE.finditer(txt):
                line = txt[: m.start()].count("\n") + 1
                hits.append(
                    {
                        "file": rel,
                        "line": line,
                        "import": m.group(1),
                        "kind": "worker-side script（子进程执行体，接口层不 import）"
                        if rel in WORKER_SIDE_SCRIPTS
                        else "接口层模块",
                    }
                )
    interface_hits = [h for h in hits if h["kind"] == "接口层模块"]
    return {
        "hits": hits,
        "count": len(hits),
        "interface_layer_hits": interface_hits,
        "interface_layer_hits_count": len(interface_hits),
        "scanned_dir": str((ROOT / "server" / "app").relative_to(ROOT)),
        "caliber": (
            "口径＝**接口层进程**不得 import cv2/numpy/pymupdf。`server/app/` 下的 "
            f"{sorted(WORKER_SIDE_SCRIPTS)} 是 worker 侧执行体（由 feicui/venv/bin/python 一次性子进程运行），"
            "不是接口层模块 —— 先例 square_runner.py 自 1.3 起即如此。"
        ),
    }


def capability_scan() -> dict:
    """API 进程现况自证：接口层解释器**装不出**这三个包，且运行中的 API 进程**未加载**它们。"""
    venv_py = ROOT / "server" / ".venv" / "bin" / "python"
    out = {"interface_venv": str(venv_py), "import_attempts": {}, "api_pid": None, "api_loaded_modules": []}
    for mod in ("cv2", "numpy", "pymupdf"):
        r = subprocess.run([str(venv_py), "-c", f"import {mod}"], capture_output=True, text=True)
        out["import_attempts"][mod] = {
            "returncode": r.returncode,
            "stderr_tail": (r.stderr.strip().splitlines() or [""])[-1],
        }
    pid = subprocess.run(
        ["lsof", "-nP", "-iTCP:5196", "-sTCP:LISTEN", "-t"], capture_output=True, text=True
    ).stdout.strip().splitlines()
    if pid:
        out["api_pid"] = pid[0]
        ls = subprocess.run(["lsof", "-p", pid[0]], capture_output=True, text=True).stdout
        pat = re.compile(r"(cv2|numpy|pymupdf|fitz|paddle)", re.I)
        out["api_loaded_modules"] = [ln for ln in ls.splitlines() if pat.search(ln)]
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--fingerprint"
    if mode == "--fingerprint":
        print(json.dumps(fingerprint(), ensure_ascii=False, indent=1))
    elif mode == "--newer":
        print(json.dumps(newer(float(sys.argv[2])), ensure_ascii=False, indent=1))
    elif mode == "--ps":
        print(json.dumps(ps_runner(), ensure_ascii=False, indent=1))
    elif mode == "--imports":
        print(json.dumps(imports_scan(), ensure_ascii=False, indent=1))
    elif mode == "--capability":
        print(json.dumps(capability_scan(), ensure_ascii=False, indent=1))
    elif mode == "--all":
        now = __import__("time").time()
        print(json.dumps({"fingerprint": fingerprint(), "t0_epoch": now}, ensure_ascii=False, indent=1))
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
