#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上传单文件上限＝**5 GiB**（Kevin 2026-10-11 裁定，原 512 MiB）· 真跑复验 —— Kong / feicui。

三条复验（关键读数一律取自**活端点**，不是读代码）：
  ① **活端点自报 `limit_bytes`**：声明 `Content-Length = 6 GiB`（> 新上限）的小体请求 ⇒ `413`，
     响应体 `limit_bytes` **必须** ＝ `5368709120`；
  ② **「> 新上限 ⇒ 413 且未落盘」**：同上一次请求，`inbox/<day>/` **不得**多出任何文件（**未落盘即拒**，
     预检路径）；
  ③ **「≥512 MiB 且 < 5 GiB ⇒ 真的放行」**：造一个**约 700 MiB、带 `%PDF-` 头**的临时文件真上传 ⇒
     **`201`**；盘上字节与 `sha256` 与响应**逐位一致**；验完**删除**临时文件与落盘件，报**磁盘峰值 + 已回收**。

红线：临时文件与落盘件在收尾**全部删除**；**不建 job**（E8 只落盘、零 DB 写）；只在 `inbox/<day>/` 落一个
脚本自名的文件并自行回收；**不动** inbox 里任何别的文件。

跑法：
    cd /Users/kevin/bistro/feicui
    ./venv/bin/python ops/job-upload/12_upload_limit_5gib_probe.py        # 打 127.0.0.1:5196
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
OPS = Path(__file__).resolve().parent
SCRATCH = Path(os.environ.get("TMPDIR", "/tmp"))
DAY = time.strftime("%Y%m%d")
INBOX_DAY = REPO / "inbox" / DAY
NEW_LIMIT = 5 * 1024 * 1024 * 1024            # 5368709120
SIZE_700M = 700 * 1024 * 1024                 # 734003200

TARGET = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:5196"
HOST, _, PORT = TARGET.partition(":")
PORT = int(PORT or 5196)

RESULTS: list[dict] = []


def log(step: str, **kw) -> None:
    row = {"step": step, **kw}
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False))


def http_post(path: str, *, headers: dict, chunks, declare: int | None, timeout: float = 600.0):
    """手写 HTTP/1.1 POST（Connection: close）。`chunks` ＝ 可迭代的 bytes（真上传用生成器，内存恒定）。"""
    head = [f"POST {path} HTTP/1.1", f"Host: {HOST}:{PORT}", "Connection: close"]
    if "Content-Length" not in headers and declare is not None:
        head.append(f"Content-Length: {declare}")
    head += [f"{k}: {v}" for k, v in headers.items()]
    sock = socket.create_connection((HOST, PORT), timeout=timeout)
    sent = 0
    t0 = time.time()
    try:
        sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        for chunk in chunks:
            sock.sendall(chunk)
            sent += len(chunk)
        data = b""
        while True:
            try:
                block = sock.recv(65536)
            except (socket.timeout, ConnectionResetError, BrokenPipeError):
                break
            if not block:
                break
            data += block
    finally:
        sock.close()
    elapsed = time.time() - t0
    head_raw, _, body = data.partition(b"\r\n\r\n")
    text = head_raw.decode("latin-1", "replace")
    m = re.search(r"HTTP/1\.1 (\d{3})", text)
    status = int(m.group(1)) if m else -1
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = None
    return status, parsed, sent, elapsed


def sha256_path(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def inbox_day_files() -> list[str]:
    return sorted(p.name for p in INBOX_DAY.iterdir()) if INBOX_DAY.is_dir() else []


def df_avail_bytes() -> int:
    out = subprocess.run(["df", "-k", str(REPO)], capture_output=True, text=True, check=True).stdout
    return int(out.splitlines()[1].split()[3]) * 1024


def make_pdf(path: Path, size: int) -> str:
    """造 `size` 字节、首 5 字节为 `%PDF-` 的文件；返回其 sha256（边写边算）。"""
    digest = hashlib.sha256()
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    written = 0
    zeros = b"\x00" * (8 * 1024 * 1024)
    with path.open("wb") as fh:
        while written < size:
            block = header if written == 0 else zeros[: min(len(zeros), size - written)]
            fh.write(block)
            digest.update(block)
            written += len(block)
    return digest.hexdigest()


def main() -> int:
    log("env", target=TARGET, repo=str(REPO), db_day=DAY, new_limit_bytes=NEW_LIMIT,
        size_700m_bytes=SIZE_700M, python=sys.executable, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    log("df_avail_before_bytes", avail=df_avail_bytes())
    files_before = inbox_day_files()
    log("inbox_before", day_dir=str(INBOX_DAY), count=len(files_before), files=files_before)

    # ---- ①②：声明 6 GiB（> 新上限）的小体请求 ⇒ 413，limit_bytes=self-report，未落盘 ----
    name_big = f"probe-5gib-declared-{int(time.time())}.pdf"
    tiny = b"%PDF-1.4\n% probe declared-too-large\n"
    s_decl, b_decl, sent_decl, _ = http_post(
        "/api/jobs/upload",
        headers={
            "Content-Type": "application/pdf",
            "X-Filename": quote(name_big, safe=""),
            "Content-Length": str(6 * 1024 * 1024 * 1024),  # 6 GiB（> 5 GiB 新上限）
        },
        chunks=[tiny],
        declare=None,
        timeout=30.0,
    )
    files_after_decl = inbox_day_files()
    log("01_declared_6gib",
        status=s_decl,
        error=(b_decl or {}).get("error"),
        detail=(b_decl or {}).get("detail"),
        limit_bytes=(b_decl or {}).get("limit_bytes"),
        limit_bytes_is_5gib=((b_decl or {}).get("limit_bytes") == NEW_LIMIT),
        declared_bytes=(b_decl or {}).get("declared_bytes"),
        sent_bytes=sent_decl,
        landed=(name_big in files_after_decl),
        inbox_count_delta=len(files_after_decl) - len(files_before))

    # ---- ③：约 700 MiB 真 PDF（%PDF- 头）⇒ 201；盘上字节 + sha256 与响应一致 -------
    src = SCRATCH / f"feicui-700mib-{int(time.time())}.pdf"
    log("03_build_temp", path=str(src), bytes=SIZE_700M)
    sha_src = make_pdf(src, SIZE_700M)
    name_700 = f"probe-700mib-{int(time.time())}.pdf"
    avail_mid = df_avail_bytes()

    def gen():
        with src.open("rb") as fh:
            while True:
                block = fh.read(8 * 1024 * 1024)
                if not block:
                    return
                yield block

    s700, b700, sent700, elapsed700 = http_post(
        "/api/jobs/upload",
        headers={"Content-Type": "application/pdf", "X-Filename": quote(name_700, safe="")},
        chunks=gen(),
        declare=SIZE_700M,
        timeout=600.0,
    )
    pdf_path = (b700 or {}).get("pdf_path")
    landed_path = Path(pdf_path) if pdf_path else None
    on_disk_bytes = landed_path.stat().st_size if landed_path and landed_path.is_file() else None
    on_disk_sha = sha256_path(landed_path) if landed_path and landed_path.is_file() else None
    log("03_upload_700mib",
        status=s700,
        response=(b700 or {}),
        sent_bytes=sent700,
        elapsed_s=round(elapsed700, 2),
        pdf_path=pdf_path,
        on_disk_bytes=on_disk_bytes,
        bytes_match=(on_disk_bytes == SIZE_700M and (b700 or {}).get("bytes") == SIZE_700M),
        sha_src=sha_src,
        sha_on_disk=on_disk_sha,
        sha_response=(b700 or {}).get("sha256"),
        sha_match=(on_disk_sha == sha_src == (b700 or {}).get("sha256")),
        idempotent=(b700 or {}).get("idempotent"))

    # ---- 收尾：删除源临时文件 + 落盘件，报磁盘峰值 + 已回收 -------------------------
    peak_bytes = SIZE_700M * 2  # 源临时文件 + inbox 落盘件（同一时点共存）
    reclaimed = 0
    if landed_path and landed_path.is_file():
        reclaimed += landed_path.stat().st_size
        landed_path.unlink()
    if src.exists():
        reclaimed += src.stat().st_size
        src.unlink()
    try:
        INBOX_DAY.rmdir()  # 只在目录已空时成功（不碰别的文件）
    except OSError:
        pass
    files_after = inbox_day_files()
    log("cleanup",
        deleted=[str(landed_path) if landed_path else None, str(src)],
        disk_peak_bytes_estimate=peak_bytes,
        disk_peak_MiB=round(peak_bytes / 1024 / 1024, 1),
        reclaimed_bytes=reclaimed,
        reclaimed_MiB=round(reclaimed / 1024 / 1024, 1),
        avail_mid_upload_bytes=avail_mid,
        avail_after_bytes=df_avail_bytes(),
        inbox_restored=(files_after == files_before),
        inbox_after_count=len(files_after))

    ok = (
        s_decl == 413
        and (b_decl or {}).get("limit_bytes") == NEW_LIMIT
        and not (name_big in files_after_decl)
        and s700 == 201
        and on_disk_bytes == SIZE_700M
        and on_disk_sha == sha_src
        and files_after == files_before
    )
    log("summary", all_pass=bool(ok), limit_bytes_self_report=(b_decl or {}).get("limit_bytes"),
        declared_413=s_decl, real_700mib_201=s700, sha_match=(on_disk_sha == sha_src))
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        status = main()
    except Exception as exc:  # noqa: BLE001
        log("EXC", detail=f"{type(exc).__name__}: {exc}")
        status = 3
    out = OPS / "12_upload_limit_5gib_probe_raw.json"
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[raw] {out}")
    print(f"[exit] {status}")
    sys.exit(status)
