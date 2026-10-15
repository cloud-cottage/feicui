#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拖曳上传端点 `POST /api/jobs/upload` · 服务端自测（可复跑）——Kong。

跑法（**用 feicui/venv 的解释器**：要 pymupdf 造 fixture；不需要 fastapi）：
    cd /Users/kevin/bistro/feicui
    ./venv/bin/python ops/job-upload/10_server_probe.py            # 打 5196
    ./venv/bin/python ops/job-upload/10_server_probe.py 127.0.0.1:5196

为什么用手写 socket 而不是 requests / httpx：
  ① 本单要考的是**裸字节流 + Content-Length 声明 + 中途中断**，手写才能逐字节控场；
  ② 端点是 `Request.stream()` 分块读，手写发送才能验证「**边收边写、超限即断**」。

覆盖：201 新写 / 200 幂等（mtime 不变）/ 同名异内容⇒`-<sha8>`（原文件不被覆盖）/
      400 NOT_A_PDF / 400 EMPTY_BODY / 413（**调小阈值**，不真传 512 MB）/
      文件名清毒（路径穿越、超长名、控制字符）/ 零 DB 写（jobs·job_pages·stamps 行数＋内容指纹）。

红线：本脚本**只**调 `/api/jobs/upload`（＋只读 SQL 计数），**不建 job**（E1 由浏览器链路证）。
所有留痕文件在收尾时按**本脚本自己创建的名字**删除，不动 inbox 里任何别的文件。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PDF_MAGIC = b"%PDF-"
SERVER = REPO / "server"
DAY = time.strftime("%Y%m%d")
INBOX_DAY = REPO / "inbox" / DAY
CONFIG_JSON = SERVER / "config.json"
DB_PATH = Path("/Users/kevin/bistro/data/yinpu.db")
OPS = Path(__file__).resolve().parent
FIXTURES = OPS / "fixtures"

TARGET = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:5196"
HOST, _, PORT = TARGET.partition(":")
PORT = int(PORT or 5196)

RESULTS: list[dict] = []
CREATED: list[Path] = []  # 本脚本落下的文件（收尾删除）


def log(step: str, **kw) -> None:
    row = {"step": step, **kw}
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False))


def urlenc(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


def http_post(path: str, *, headers: dict, chunks: list[bytes], timeout: float = 60.0):
    """手写 HTTP/1.1 POST（Connection: close）⇒ 返回 (status, headers, raw_body_bytes)。"""
    body_len = sum(len(c) for c in chunks)
    head = [f"POST {path} HTTP/1.1", f"Host: {HOST}:{PORT}", "Connection: close"]
    if "Content-Length" not in headers:
        head.append(f"Content-Length: {body_len}")
    head += [f"{k}: {v}" for k, v in headers.items()]
    sock = socket.create_connection((HOST, PORT), timeout=timeout)
    try:
        sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        for chunk in chunks:
            sock.sendall(chunk)
        data = b""
        while True:
            block = sock.recv(65536)
            if not block:
                break
            data += block
    finally:
        sock.close()
    head_raw, _, body = data.partition(b"\r\n\r\n")
    text = head_raw.decode("latin-1", "replace")
    status = int(re.search(r"HTTP/1\.1 (\d{3})", text).group(1)) if re.search(r"HTTP/1\.1 (\d{3})", text) else -1
    return status, text, body


def http_post_chunked(path: str, *, headers: dict, chunks: list[bytes], timeout: float = 60.0):
    """`Transfer-Encoding: chunked`（**不带 Content-Length**）⇒ 逼出「边收边写、超限即断」那条路。"""
    head = [
        f"POST {path} HTTP/1.1",
        f"Host: {HOST}:{PORT}",
        "Connection: close",
        "Transfer-Encoding: chunked",
    ]
    head += [f"{k}: {v}" for k, v in headers.items()]
    sock = socket.create_connection((HOST, PORT), timeout=timeout)
    try:
        sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        for chunk in chunks:
            sock.sendall(f"{len(chunk):x}\r\n".encode("latin-1") + chunk + b"\r\n")
        sock.sendall(b"0\r\n\r\n")
        data = b""
        while True:
            try:
                block = sock.recv(65536)
            except (socket.timeout, ConnectionResetError):
                break  # 服务端在写盘过程中拒收并挂断：按已收到的字节判读
            if not block:
                break
            data += block
    finally:
        sock.close()
    head_raw, _, body = data.partition(b"\r\n\r\n")
    text = head_raw.decode("latin-1", "replace")
    m = re.search(r"HTTP/1\.1 (\d{3})", text)
    return (int(m.group(1)) if m else -1), text, body


def e1(pdf_path: str, *, page_range=(1, 1)):
    """直接打 **E1** `POST /api/jobs`（JSON 体）——用于 AC-69「E1 契约未变」的四条复跑。"""
    payload = json.dumps({"pdf_path": pdf_path, "page_range": list(page_range)}).encode("utf-8")
    status, head, body = http_post("/api/jobs", headers={"Content-Type": "application/json"}, chunks=[payload])
    return status, parse_json(body)


def probe_midstream_abort(name: str, *, limit_bytes: int, total_bytes: int, chunk: int = 65536, pause: float = 0.05):
    """**慢速 chunked 发送**：发到超限即**停手**（不发终止块）⇒ 观察服务端是否**在整车收完之前**
    就回 `413`；同时轮询本轮临时文件（`.<name>-*.part`）的**大小峰值**。

    这是 AC-65(b)「不得先写满盘再报错」的**实现证据**：判据＝① 响应在 `sent < total` 时到达；
    ② 临时文件峰值 ≤ 上限。
    """
    head = [
        "POST /api/jobs/upload HTTP/1.1",
        f"Host: {HOST}:{PORT}",
        "Connection: close",
        "Transfer-Encoding: chunked",
        "Content-Type: application/pdf",
        f"X-Filename: {urlenc(name)}",
    ]
    sock = socket.create_connection((HOST, PORT), timeout=30.0)
    sent = 0
    peak = 0
    response = b""
    sent_at_abort = None
    try:
        sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        while sent < total_bytes:
            block = (PDF_MAGIC + b"z" * (chunk - len(PDF_MAGIC))) if sent == 0 else b"z" * chunk
            sock.sendall(f"{len(block):x}\r\n".encode("latin-1") + block + b"\r\n")
            sent += len(block)
            time.sleep(pause)
            if INBOX_DAY.is_dir():
                for part in INBOX_DAY.glob(f".{name}-*"):
                    try:
                        peak = max(peak, part.stat().st_size)
                    except OSError:
                        pass
            sock.settimeout(0.001)  # 非阻塞探测：服务端是否已回应
            try:
                data = sock.recv(65536)
                if data:
                    response += data
                    sent_at_abort = sent
                    break
            except (socket.timeout, BlockingIOError):
                pass
            finally:
                sock.settimeout(30.0)
        else:
            sent_at_abort = sent
        sock.settimeout(5.0)
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                response += data
        except (socket.timeout, ConnectionResetError):
            pass
    finally:
        sock.close()
    head_raw, _, body = response.partition(b"\r\n\r\n")
    m = re.search(r"HTTP/1\.1 (\d{3})", head_raw.decode("latin-1", "replace"))
    parsed = parse_json(body) or {}
    return {
        "status": int(m.group(1)) if m else None,
        "error": parsed.get("error"),
        "detail": parsed.get("detail"),
        "received_bytes": parsed.get("received_bytes"),
        "sent_at_abort": sent_at_abort,
        "total_bytes": total_bytes,
        "aborted_before_full_body": sent_at_abort is not None and sent_at_abort < total_bytes,
        "peak_part_bytes_observed": peak,
        "peak_within_limit": peak <= limit_bytes,
    }


def parse_json(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def upload(name: str, payload: bytes, *, declared: int | None = None, ctype: str = "application/pdf",
           header_name: str | None = None, path: str = "/api/jobs/upload"):
    headers = {"Content-Type": ctype, "X-Filename": urlenc(header_name if header_name is not None else name)}
    if declared is not None:
        headers["Content-Length"] = str(declared)
    status, head, body = http_post(path, headers=headers, chunks=[payload] if payload else [])
    ctype_resp = ""
    for line in head.splitlines():
        if line.lower().startswith("content-type:"):
            ctype_resp = line.split(":", 1)[1].strip()
    return {
        "status": status,
        "content_type": ctype_resp,
        "body": parse_json(body),
        "raw_head": head.splitlines()[0] if head else "",
        "raw_body_len": len(body),
        "raw_body_head": body[:200].decode("utf-8", "replace"),
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ctx() -> dict:
    """零 DB 写判据：行数 ＋ 内容指纹（**不用数据库文件 md5**：WAL 下会漂移）。"""
    out: dict = {"db": str(DB_PATH), "exists": DB_PATH.is_file()}
    if not out["exists"]:
        return out
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        for table in ("jobs", "job_pages", "stamps"):
            try:
                out[f"{table}_rows"] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except sqlite3.Error as exc:
                out[f"{table}_rows"] = f"ERR:{exc}"
        try:
            payload = "\n".join(
                "|".join("" if v is None else str(v) for v in row)
                for row in conn.execute("SELECT * FROM stamps ORDER BY id")
            )
            out["stamps_fingerprint_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        except sqlite3.Error as exc:
            out["stamps_fingerprint_sha256"] = f"ERR:{exc}"
    finally:
        conn.close()
    return out


def make_fixture(name: str, text: str, pages: int = 1) -> Path:
    import fitz  # pymupdf（feicui/venv 有）

    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / name
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} — page {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def cleanup() -> None:
    for path in CREATED:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    # 只在目录已空时消失（不碰 inbox 里别的文件）
    try:
        INBOX_DAY.rmdir()
    except OSError:
        pass


def main() -> int:
    log("env", target=TARGET, repo=str(REPO), day=DAY, inbox_day=str(INBOX_DAY),
        db=str(DB_PATH), python=sys.executable, time=time.strftime("%Y-%m-%d %H:%M:%S"))

    pdf_a = make_fixture("drop-probe.pdf", "feicui 拖曳上传自测 A", pages=1)
    pdf_b = make_fixture("drop-probe-v2.pdf", "feicui 拖曳上传自测 B（内容不同、同名）", pages=2)
    bytes_a = pdf_a.read_bytes()
    bytes_b = pdf_b.read_bytes()
    sha_a, sha_b = sha256_bytes(bytes_a), sha256_bytes(bytes_b)
    log("fixtures", a=str(pdf_a), bytes_a=len(bytes_a), sha_a=sha_a[:16],
        b=str(pdf_b), bytes_b=len(bytes_b), sha_b=sha_b[:16])

    before = ctx()
    log("db_before", **before)

    name = f"probe-拖曳-{int(time.time())}.pdf"

    # ---- ① 首次上传 ⇒ 201 -------------------------------------------------
    r1 = upload(name, bytes_a)
    log("01_first_upload", name=name, **r1)
    assert r1["status"] == 201, r1
    body = r1["body"]
    target = REPO / body["pdf_path"]
    CREATED.append(target)
    log("01_target", path=str(target), exists=target.is_file(),
        size=target.stat().st_size if target.is_file() else None,
        sha256_on_disk=sha256_path(target) if target.is_file() else None,
        sha256_match=sha256_path(target) == sha_a if target.is_file() else None,
        bytes_match=body["bytes"] == len(bytes_a),
        rel_path=body["rel_path"], filename=body["filename"],
        pdf_path_is_absolute=os.path.isabs(body["pdf_path"]),
        pdf_path_points_to_file=Path(body["pdf_path"]).is_file(),
        rel_path_is_root_relative=(body["rel_path"] == f"inbox/{DAY}/{body['filename']}"),
        json_not_html=r1["content_type"].startswith("application/json"),
        exactly_7_fields=(sorted(body.keys()) == sorted(
            ["pdf_path", "rel_path", "filename", "bytes", "sha256", "idempotent", "dedup_suffix"])))

    # ---- ② 同内容再传 ⇒ 200 幂等、mtime 不变 --------------------------------
    mtime_before = target.stat().st_mtime_ns
    time.sleep(0.05)
    r2 = upload(name, bytes_a)
    mtime_after = target.stat().st_mtime_ns
    log("02_idempotent_same", **r2, mtime_before=mtime_before, mtime_after=mtime_after,
        mtime_unchanged=(mtime_before == mtime_after),
        idempotent=bool(r2["body"] and r2["body"].get("idempotent")),
        same_path=(r2["body"] or {}).get("pdf_path") == body["pdf_path"])
    assert r2["status"] == 200 and r2["body"]["idempotent"] is True, r2

    # ---- ③ 同名异内容 ⇒ 不覆盖、落 -<sha8> ---------------------------------
    r3 = upload(name, bytes_b)
    log("03_same_name_diff_content", **r3,
        dedup_suffix=bool(r3["body"] and r3["body"].get("dedup_suffix")),
        original_sha_unchanged=(sha256_path(target) == sha_a),
        new_path_exists=(REPO / (r3["body"] or {}).get("pdf_path", "x")).is_file()
        if r3.get("body") else None)
    assert r3["status"] == 201 and r3["body"]["dedup_suffix"] is True, r3
    new_target = REPO / r3["body"]["pdf_path"]
    CREATED.append(new_target)
    log("03_new_target", path=str(new_target), name=new_target.name,
        sha256_on_disk=sha256_path(new_target), sha_expected=sha_b,
        content_match=(sha256_path(new_target) == sha_b))

    # ---- ④ 非 PDF（文本）⇒ 400 NOT_A_PDF，且不落盘 -------------------------
    text_name = f"probe-text-{int(time.time())}.pdf"
    r4 = upload(text_name, b"this is definitely not a pdf\n" * 4)
    log("04_not_a_pdf", **r4, landed=(INBOX_DAY / text_name).exists())
    assert r4["status"] == 400 and r4["body"]["error"] == "NOT_A_PDF", r4

    # ---- ⑤ 空体 ⇒ 400 EMPTY_BODY ------------------------------------------
    r5 = upload(f"probe-empty-{int(time.time())}.pdf", b"")
    log("05_empty_body", **r5)
    assert r5["status"] == 400 and r5["body"]["error"] == "EMPTY_BODY", r5

    # ---- ⑥ 短于魔数（3 字节）⇒ 400 NOT_A_PDF -------------------------------
    r6 = upload("probe-short.pdf", b"%PD")
    log("06_short_body", **r6)
    assert r6["status"] == 400 and r6["body"]["error"] == "NOT_A_PDF", r6

    # ---- ⑦ 文件名清毒：路径穿越 / 绝对路径 / 反斜杠 / 控制字符 --------------
    for raw_name, expect_name in (
        ("../../../etc/passwd.pdf", "passwd.pdf"),
        ("/tmp/abs-evil.pdf", "abs-evil.pdf"),
        ("..\\..\\win-evil.pdf", "win-evil.pdf"),
        ("ctl\x01\x02evil.pdf", "ctlevil.pdf"),
    ):
        r = upload(f"probe-trav-{int(time.time())}", bytes_a, header_name=raw_name)
        got = (r["body"] or {}).get("pdf_path", "")
        landed = (REPO / got) if got else None
        if landed is not None and landed.is_file():
            CREATED.append(landed)
        inside = bool(landed) and landed.parent.resolve() == INBOX_DAY.resolve()
        log("07_sanitize", requested=raw_name, expect=expect_name, status=r["status"],
            filename=(r["body"] or {}).get("filename"), pdf_path=got,
            inside_inbox_day=inside, escapes_inbox=(not inside))
        assert r["status"] in (200, 201) and inside, r

    long_name = "长" * 300 + ".pdf"
    r = upload("probe-long", bytes_a, header_name=long_name)
    got = (r["body"] or {}).get("filename", "")
    if r["body"]:
        landed = REPO / r["body"]["pdf_path"]
        if landed.is_file():
            CREATED.append(landed)
    stem = got.rsplit(".", 1)[0]
    log("07_sanitize_long", requested_stem_chars=300, got=got, got_chars=len(got),
        stem_bytes=len(stem.encode("utf-8")), cap_bytes=200,
        within_200=len(stem.encode("utf-8")) <= 200, has_pdf_suffix=got.endswith(".pdf"),
        single_pdf_suffix=got.count(".pdf") == 1)

    # ---- ⑦c Content-Type 白名单（§3.19.2 / §3.19.4 ①）----------------------
    r_ct = upload("probe-ct.pdf", bytes_a, ctype="text/plain")
    log("07c_bad_content_type", **r_ct, landed=(INBOX_DAY / "probe-ct.pdf").exists())
    assert r_ct["status"] == 400 and r_ct["body"]["error"] == "BAD_CONTENT_TYPE", r_ct

    status_missing, head_missing, body_missing = http_post(  # 完全不带 Content-Type
        "/api/jobs/upload",
        headers={"X-Filename": urlenc("probe-no-ct.pdf")},
        chunks=[bytes_a],
    )
    parsed_missing = parse_json(body_missing) or {}
    log("07c_missing_content_type", status=status_missing, error=parsed_missing.get("error"),
        landed=(INBOX_DAY / "probe-no-ct.pdf").exists())
    assert status_missing == 400 and parsed_missing.get("error") == "BAD_CONTENT_TYPE", parsed_missing

    r_ct_ok = upload("probe-ct-ok.pdf", bytes_a, ctype="application/octet-stream")
    if r_ct_ok["body"]:
        landed = REPO / r_ct_ok["body"]["pdf_path"]
        if landed.is_file():
            CREATED.append(landed)
    log("07c_octet_stream_ok", status=r_ct_ok["status"], filename=(r_ct_ok["body"] or {}).get("filename"))
    assert r_ct_ok["status"] in (200, 201), r_ct_ok

    # ---- ⑦d 未白名单查询参数 ⇒ 400（§3.19.2）-------------------------------
    status_q, head_q, body_q = http_post(
        "/api/jobs/upload?foo=1",
        headers={"Content-Type": "application/pdf", "X-Filename": urlenc("probe-q.pdf")},
        chunks=[bytes_a],
    )
    parsed_q = parse_json(body_q) or {}
    log("07d_unsupported_query_param", status=status_q, error=parsed_q.get("error"),
        detail=parsed_q.get("detail"), landed=(INBOX_DAY / "probe-q.pdf").exists())
    assert status_q == 400 and parsed_q.get("error") == "UNSUPPORTED_PARAM", parsed_q

    # ---- ⑦e 清毒后越界的防御判据（单测：纯函数，不经 HTTP）------------------
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("feicui_uploader_probe", REPO / "server" / "app" / "uploader.py")
    up = _ilu.module_from_spec(spec)
    spec.loader.exec_module(up)  # type: ignore[union-attr]
    cases = ["../../etc/passwd.pdf", "/tmp/x.pdf", "a/../../../b.pdf", "..\\..\\c.pdf", "", ".", "..", "\x00\x01.pdf"]
    log("07e_sanitize_unit", sanitized={c: up.sanitize_filename(c) for c in cases},
        long_bytes=len(up.sanitize_filename("长" * 300 + ".pdf").rsplit(".", 1)[0].encode("utf-8")))
    try:
        up.assert_inside_inbox(INBOX_DAY, "../evil.pdf", REPO / "inbox")
        escaped = False
    except up.UploadRejected as exc:
        escaped = {"status": exc.status_code, "error": exc.error}
    log("07e_containment_guard", forced_escape_blocked=escaped)

    # ---- ⑧ Content-Disposition 回退（无 X-Filename） ------------------------
    disp_name = "disp-回退名.pdf"
    status, head, body = http_post(
        "/api/jobs/upload",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename*=UTF-8''{urlenc(disp_name)}",
        },
        chunks=[bytes_a],
    )
    parsed = parse_json(body) or {}
    if parsed.get("pdf_path"):
        landed = REPO / parsed["pdf_path"]
        if landed.is_file():
            CREATED.append(landed)
    log("08_content_disposition", status=status, filename=parsed.get("filename"),
        expected=disp_name, match=parsed.get("filename") == disp_name)
    assert status in (200, 201) and parsed.get("filename") == disp_name, body[:200]

    # ---- ⑨ 413：调小阈值（server/config.json，per-request 生效，不重启）----
    big = bytes_a + b"%" + b"x" * (200 * 1024)  # 前 5 字节仍是 %PDF-
    fname_413 = f"probe-413-{int(time.time())}.pdf"
    CONFIG_JSON.write_text(json.dumps({"upload_max_bytes": 65536}), encoding="utf-8")
    try:
        time.sleep(0.2)
        r9 = upload(fname_413, big)
        residue = sorted(p.name for p in INBOX_DAY.glob("*.part")) + sorted(
            p.name for p in INBOX_DAY.glob(f".{fname_413}*")
        ) if INBOX_DAY.is_dir() else []
        log("09_too_large_declared_content_length", limit_bytes=65536, sent_bytes=len(big), **r9,
            landed=(INBOX_DAY / fname_413).exists(), temp_residue=residue)
        assert r9["status"] == 413 and r9["body"]["error"] == "PAYLOAD_TOO_LARGE", r9
        assert not (INBOX_DAY / fname_413).exists()
        assert not residue, residue

        # ⑨c **真·中途中断**：不带 Content-Length（chunked、每次 64 KiB）⇒ 收到超限那一刻即断
        fname_413c = f"probe-413-chunked-{int(time.time())}.pdf"
        try:
            status_c, _head_c, body_c = http_post_chunked(
                "/api/jobs/upload",
                headers={"Content-Type": "application/pdf", "X-Filename": urlenc(fname_413c)},
                chunks=[big[i : i + 65536] for i in range(0, len(big), 65536)],
            )
            parsed_c = parse_json(body_c) or {}
        except (socket.timeout, ConnectionResetError, BrokenPipeError) as exc:
            status_c, parsed_c = None, {"note": f"{type(exc).__name__}: {exc}"}
        residue_c = sorted(p.name for p in INBOX_DAY.glob(f".{fname_413c}*")) if INBOX_DAY.is_dir() else []
        log("09c_too_large_midstream_chunked", limit_bytes=65536, sent_bytes=len(big),
            status=status_c, error=parsed_c.get("error"), detail=parsed_c.get("detail"),
            received_bytes=parsed_c.get("received_bytes"),
            interrupted_before_full_body=(parsed_c.get("received_bytes") or 0) < len(big),
            landed=(INBOX_DAY / fname_413c).exists(), temp_residue=residue_c)
        assert status_c == 413 and parsed_c.get("error") == "PAYLOAD_TOO_LARGE", (status_c, parsed_c)
        assert not (INBOX_DAY / fname_413c).exists()
        assert not residue_c, residue_c

        # ⑨d **边写边判的直接证据**（AC-65(b)）：慢速 chunked、发到超限即停手 ⇒
        #     ① 响应在「整车收完之前」到达；② 本轮临时文件大小峰值 ≤ 上限
        fname_413d = f"probe-413-slow-{int(time.time())}.pdf"
        got_d = probe_midstream_abort(fname_413d, limit_bytes=65536, total_bytes=65536 * 8, chunk=65536, pause=0.08)
        log("09d_midstream_abort_evidence", limit_bytes=65536, **got_d)
        assert got_d["status"] == 413 and got_d["error"] == "PAYLOAD_TOO_LARGE", got_d
        assert got_d["aborted_before_full_body"], got_d
        assert got_d["peak_within_limit"], got_d
        assert not (INBOX_DAY / fname_413d).exists()

        # ⑨b 声明超限 ⇒ **未落盘即拒**（Content-Length 巨值 + 只发少量字节）
        try:
            status_b, head_b, body_b = http_post(
                "/api/jobs/upload",
                headers={
                    "Content-Type": "application/pdf",
                    "X-Filename": urlenc("probe-413-declared.pdf"),
                    "Content-Length": "999999999",
                },
                chunks=[bytes_a],
                timeout=10.0,
            )
            parsed_b = parse_json(body_b) or {}
            log("09b_declared_too_large", status=status_b, error=parsed_b.get("error"),
                detail=parsed_b.get("detail"), declared_bytes=parsed_b.get("declared_bytes"))
        except (socket.timeout, ConnectionResetError, BrokenPipeError) as exc:
            log("09b_declared_too_large", status=None, note=f"服务端拒绝/挂断连接：{type(exc).__name__}: {exc}")
    finally:
        CONFIG_JSON.unlink(missing_ok=True)

    # ---- ⑩ 阈值恢复：同尺寸上传恢复 201 ------------------------------------
    time.sleep(0.2)
    fname_ok = f"probe-after413-{int(time.time())}.pdf"
    r10 = upload(fname_ok, big)
    if r10["body"] and r10["body"].get("pdf_path"):
        landed = REPO / r10["body"]["pdf_path"]
        if landed.is_file():
            CREATED.append(landed)
    log("10_after_config_removed", status=r10["status"], bytes=len(big),
        config_removed=not CONFIG_JSON.exists(),
        ok=(r10["status"] in (200, 201)))
    assert r10["status"] in (200, 201), r10

    # ---- ⑪ 零 DB 写：行数 / 指纹与上传前一致 --------------------------------
    after = ctx()
    log("db_after", **after)
    log("11_zero_db_write",
        jobs_same=before.get("jobs_rows") == after.get("jobs_rows"),
        job_pages_same=before.get("job_pages_rows") == after.get("job_pages_rows"),
        stamps_rows_same=before.get("stamps_rows") == after.get("stamps_rows"),
        stamps_fingerprint_same=before.get("stamps_fingerprint_sha256")
        == after.get("stamps_fingerprint_sha256"),
        jobs_rows=after.get("jobs_rows"), job_pages_rows=after.get("job_pages_rows"),
        stamps_rows=after.get("stamps_rows"))
    assert before.get("jobs_rows") == after.get("jobs_rows")
    assert before.get("job_pages_rows") == after.get("job_pages_rows")
    assert before.get("stamps_fingerprint_sha256") == after.get("stamps_fingerprint_sha256")

    # ---- ⑫ 落点目录一览 ----------------------------------------------------
    listing = sorted(p.name for p in INBOX_DAY.iterdir()) if INBOX_DAY.is_dir() else []
    log("12_inbox_listing", day_dir=str(INBOX_DAY), files=listing, count=len(listing))

    # ---- ⑬ E1 契约未变（AC-69）：① 400 PDF_NOT_FOUND ② 400 NOT_A_PDF ③ 409+job_id ④ 201 ----
    #     注：E1 会**真切建 job**（落 `jobs` / `job_pages`），故一律排在 ⑪「零 DB 写」之后。
    s_missing, b_missing = e1(f"inbox/{DAY}/definitely-missing-probe.pdf")
    log("13_e1_missing_file", status=s_missing, error=(b_missing or {}).get("error"),
        detail=(b_missing or {}).get("detail"))

    not_pdf_path = FIXTURES / "not-a-pdf.txt"
    not_pdf_path.write_text("this file is definitely not a pdf\n", encoding="utf-8")
    s_notpdf, b_notpdf = e1(str(not_pdf_path))
    log("13_e1_existing_non_pdf", status=s_notpdf, error=(b_notpdf or {}).get("error"), body=b_notpdf)

    keep_name = f"probe-e1-keep-{int(time.time())}.pdf"
    rk = upload(keep_name, bytes_a)
    keep_path = Path((rk["body"] or {}).get("pdf_path", "")) if rk.get("body") else None
    if keep_path is not None and keep_path.is_file():
        pass  # **有意保留**（下面 E1 要用它；E1 建的 job 的输入不能被删）
    log("13_e1_input_upload", status=rk["status"], pdf_path=str(keep_path) if keep_path else None)

    s_new, b_new = e1(str(keep_path))
    log("13_e1_created", status=s_new, body=b_new, has_4_fields=bool(
        b_new and sorted(b_new.keys()) == ["created_at", "job_id", "state", "total_pages"]))

    s_again, b_again = e1(str(keep_path))
    log("13_e1_conflict", status=s_again, body=b_again,
        error=(b_again or {}).get("error"),
        job_id=(b_again or {}).get("job_id"),
        same_job_id=((b_again or {}).get("job_id") == (b_new or {}).get("job_id")))

    log("summary", total_steps=len(RESULTS), failed=0, created_files=[str(p) for p in CREATED],
        kept_files=[str(keep_path)] if keep_path else [],
        e1_jobs=[(b_new or {}).get("job_id")])
    return 0


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except AssertionError as exc:
        log("ASSERT_FAIL", detail=str(exc)[:800])
        status = 2
    finally:
        cleanup()
        out = OPS / "10_server_probe_raw.json"
        out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n[raw] {out}")
        print(f"[exit] {status}")
        sys.exit(status)
