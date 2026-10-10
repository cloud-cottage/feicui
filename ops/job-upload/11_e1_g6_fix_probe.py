#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1（§3.1 表下注 G-6）真缺陷修复自证 —— 建 job **之前**校验 `pdf_path`。Kong / feicui 窄修复单。

真缺陷：E1 只看 `is_file()` ⇒ 「**存在但非 PDF**」的 `pdf_path` 被当 1 页 PDF 收下、**建出 job（201）**，
违反 §3.1 G-6（非 PDF 以 `%PDF-` magic 为准）＋ §3.4 的 `400` 行。本脚本复跑四例取证：

  ① 非 PDF 的**存在**文件 ⇒ `400`（error `NOT_A_PDF`），且 `jobs` / `job_pages` / `stamps` 行数**不变**；
  ② 不存在的路径         ⇒ `400`（error `PDF_NOT_FOUND`），且三表行数**不变**；
  ③ 真 PDF               ⇒ `201 {job_id,state,total_pages,created_at}`（原行为不变）；
  ④ 同 `pdf_path` 再提交 ⇒ `409` ＋ **既有** `job_id`（原行为不变，`error=ACTIVE_JOB_EXISTS`）。

判据归属：E1 的 PDF 判定＝**G-6**（文件前 1024 字节内出现 `%PDF-` 即算 PDF，**宽松**），
**不是** §3.19.4 的 E8 口（**首字节即须为** `%PDF-`，**严**）—— 规范明写两者「不同口的不同严格度、
不互相代替、不统一」。

红线与清理：③ 会**真切建 job** ⇒ 脚本记下 job_id，收尾按派单口径清理（**先备份**、再删**本脚本建的**
`job_pages` / `jobs` 行），并把三表行数复位读数打出来；**不删任何非本脚本所建的行**。

跑法（feicui/venv 有 pymupdf 造 fixture）：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/job-upload/11_e1_g6_fix_probe.py            # 打 127.0.0.1:5196
"""
from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OPS = Path(__file__).resolve().parent
FIXTURES = OPS / "fixtures"
DB_PATH = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
BACKUP_DIR = Path("/Users/kevin/.hermes/profiles/zang/cache/scratch")

TARGET = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:5196"
HOST, _, PORT = TARGET.partition(":")
PORT = int(PORT or 5196)

RESULTS: list[dict] = []


def log(step: str, **kw) -> None:
    row = {"step": step, **kw}
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False))


def e1(pdf_path: str, *, page_range=(1, 1), timeout: float = 60.0):
    """直接打 **E1** `POST /api/jobs`（JSON 体）。返回 (status, body_dict)。"""
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    payload = json.dumps({"pdf_path": pdf_path, "page_range": list(page_range)}).encode("utf-8")
    try:
        conn.request("POST", "/api/jobs", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
    finally:
        conn.close()
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        body = {"_raw": raw[:200].decode("utf-8", "replace")}
    return status, body


def err_code(body: dict) -> str | None:
    """错误码可能落在**顶层**或 `detail`（object）里 —— 两种都读，如实登记。"""
    if not isinstance(body, dict):
        return None
    top = body.get("error")
    if isinstance(top, str):
        return top
    detail = body.get("detail")
    if isinstance(detail, dict):
        inner = detail.get("error")
        if isinstance(inner, str):
            return inner
    return None


def counts() -> dict:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        out = {}
        for t in ("jobs", "job_pages", "stamps"):
            out[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        payload = "\n".join(
            "|".join("" if v is None else str(v) for v in row)
            for row in conn.execute("SELECT * FROM stamps ORDER BY id")
        )
        out["stamps_fingerprint_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    finally:
        conn.close()
    return out


def make_real_pdf(name: str, text: str) -> Path:
    import fitz  # feicui/venv 有 pymupdf

    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return path


def main() -> int:
    log("env", target=TARGET, repo=str(REPO), db=str(DB_PATH), python=sys.executable,
        time=time.strftime("%Y-%m-%d %H:%M:%S"))

    baseline = counts()
    log("db_baseline", **baseline)

    # fixture：真 PDF 与「存在但非 PDF」的文本文件
    real_pdf = make_real_pdf("e1-fix-real.pdf", "feicui E1 G-6 自证 · 真 PDF")
    not_pdf = FIXTURES / "e1-fix-not-a-pdf.txt"
    not_pdf.write_text("this file is definitely not a pdf\n", encoding="utf-8")
    log("fixtures", real_pdf=str(real_pdf), real_pdf_bytes=real_pdf.stat().st_size,
        real_pdf_head=real_pdf.read_bytes()[:5].decode("latin-1"),
        not_pdf=str(not_pdf), not_pdf_bytes=not_pdf.stat().st_size,
        not_pdf_head=not_pdf.read_bytes()[:5].decode("latin-1"))

    created_job_id: str | None = None

    # ---- ① 非 PDF（存在）⇒ 400 NOT_A_PDF，三表行数不变 -----------------------------
    s1, b1 = e1(str(not_pdf))
    after1 = counts()
    log("01_existing_non_pdf", status=s1, error=err_code(b1), body=b1,
        jobs_same=after1["jobs"] == baseline["jobs"],
        job_pages_same=after1["job_pages"] == baseline["job_pages"],
        stamps_same=after1["stamps"] == baseline["stamps"])

    # ---- ② 不存在路径 ⇒ 400 PDF_NOT_FOUND，三表行数不变 ---------------------------
    missing = str(FIXTURES / "definitely-missing-e1-fix.pdf")
    s2, b2 = e1(missing)
    after2 = counts()
    log("02_missing_path", status=s2, error=err_code(b2), body=b2,
        jobs_same=after2["jobs"] == baseline["jobs"],
        job_pages_same=after2["job_pages"] == baseline["job_pages"],
        stamps_same=after2["stamps"] == baseline["stamps"])

    # ---- ③ 真 PDF ⇒ 201（原行为不变） --------------------------------------------
    s3, b3 = e1(str(real_pdf))
    after3 = counts()
    created_job_id = b3.get("job_id") if isinstance(b3, dict) else None
    log("03_real_pdf", status=s3, body=b3, job_id=created_job_id,
        has_4_fields=bool(b3 and sorted(b3.keys()) == ["created_at", "job_id", "state", "total_pages"]),
        jobs_plus1=(after3["jobs"] == baseline["jobs"] + 1),
        stamps_same=after3["stamps"] == baseline["stamps"])

    # ---- ④ 同 pdf_path 再提交 ⇒ 409 + 既有 job_id（原行为不变） --------------------
    s4, b4 = e1(str(real_pdf))
    after4 = counts()
    log("04_conflict", status=s4, body=b4, error=err_code(b4),
        job_id=(b4 or {}).get("job_id"),
        same_job_id=((b4 or {}).get("job_id") == created_job_id),
        jobs_same_as_after3=(after4["jobs"] == after3["jobs"]),
        stamps_same=after4["stamps"] == baseline["stamps"])

    # ---- 清理：只删本脚本建的 job（先备份） --------------------------------------
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"yinpu.backup.{ts}.db"
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        # 一致快照（WAL 下比裸 cp 稳）：sqlite3 在线备份 API
        bconn = sqlite3.connect(str(backup))
        with bconn:
            conn.backup(bconn)
        bconn.close()
        log("cleanup_backup", path=str(backup), bytes=backup.stat().st_size)

        deleted_pages = deleted_jobs = 0
        if created_job_id:
            cur = conn.execute("DELETE FROM job_pages WHERE job_id = ?", (created_job_id,))
            deleted_pages = cur.rowcount
            cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (created_job_id,))
            deleted_jobs = cur.rowcount
            conn.commit()
        log("cleanup_deleted", job_id=created_job_id, deleted_pages=deleted_pages,
            deleted_jobs=deleted_jobs)
    finally:
        conn.close()

    final = counts()
    log("db_final", **final,
        jobs_restored=final["jobs"] == baseline["jobs"],
        job_pages_restored=final["job_pages"] == baseline["job_pages"],
        stamps_unchanged=final["stamps"] == baseline["stamps"],
        stamps_fingerprint_unchanged=(final["stamps_fingerprint_sha256"]
                                      == baseline["stamps_fingerprint_sha256"]))

    ok = (
        s1 == 400 and err_code(b1) == "NOT_A_PDF"
        and s2 == 400 and err_code(b2) == "PDF_NOT_FOUND"
        and s3 == 201 and s4 == 409
        and final["jobs"] == baseline["jobs"]
        and final["job_pages"] == baseline["job_pages"]
        and final["stamps"] == baseline["stamps"]
    )
    log("summary", all_pass=bool(ok), baseline=baseline, final=final)
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        status = main()
    except Exception as exc:  # noqa: BLE001
        log("EXC", detail=f"{type(exc).__name__}: {exc}")
        status = 3
    out = OPS / "11_e1_g6_fix_probe_raw.json"
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[raw] {out}")
    print(f"[exit] {status}")
    sys.exit(status)
