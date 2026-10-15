#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox 清理策略（R41）· 活端点 + CLI 复验 —— Kong / feicui。

复验（关键读数一律取自**活端点 5196** 与**真 CLI**，不是读代码）：

  ① **ACTIVE 豁免**：用 `inbox/20261011/zang_probe.pdf`（真 `%PDF-` 文件）走 **E1** 建一个 **ACTIVE**
     job（持池写锁 ⇒ 池不起 ⇒ job 停在 QUEUED）；随后
       * `GET /api/jobs/inbox/summary` 必须把该文件列入 **exempt（reason=active_job）**；
       * CLI `--retention-days 0`（把保留期压到 0 造场景）⇒ **其余文件全进待回收**，
         而 zang_probe.pdf **仍豁免**（ACTIVE 豁免无条件）。
  ② **E1 / E8 错误体对齐**：E1 的新 400（PDF_NOT_FOUND / NOT_A_PDF）与 E8 的 400（BAD_CONTENT_TYPE）
     顶层键集合**同形**（`error` + `detail`）。
  ③ **端点默认 dry-run**：`POST /api/jobs/inbox/gc` 空体 与 `{"apply":false}` 都**不改盘**（inbox 文件数/字节不变）。

红线：**验完把该 job 及其 `job_pages` 删回基线**，报三数；**只**建/删这一个自造 job，不动既有 5 行；
持锁期间池不起 ⇒ **不动 stamps**。

跑法：
    cd /Users/kevin/bistro/feicui
    ./server/.venv/bin/python ops/job-upload/13_inbox_gc_probe.py        # 打 127.0.0.1:5196
"""
from __future__ import annotations

import fcntl
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/Users/kevin/bistro/feicui")
SERVER = ROOT / "server"
DB = Path("/Users/kevin/bistro/data/yinpu.db")
PROBE_PDF = ROOT / "inbox" / "20261011" / "zang_probe.pdf"
LOCK = SERVER / ".run" / "pool.state.lock"
API = "http://127.0.0.1:5196"
OUT = ROOT / "ops" / "job-upload" / "13_inbox_gc_probe_raw.json"

result: dict = {"steps": []}


def rec(name, **kw):
    result["steps"].append({"step": name, **kw})
    print(f"\n== {name} ==")
    for k, v in kw.items():
        print(f"   {k}: {json.dumps(v, ensure_ascii=False)}")


def http(method, path, body=None, headers=None, raw_body=None):
    url = API + path
    data = None
    hdrs = dict(headers or {})
    if raw_body is not None:
        data = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8")
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            return resp.status, parsed, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return e.code, parsed, raw


def counts():
    conn = sqlite3.connect(DB)
    try:
        return {
            "jobs": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "job_pages": conn.execute("SELECT COUNT(*) FROM job_pages").fetchone()[0],
            "stamps": conn.execute("SELECT COUNT(*) FROM stamps").fetchone()[0],
        }
    finally:
        conn.close()


def inbox_stat():
    files = [p for p in (ROOT / "inbox").rglob("*") if p.is_file() and ".trash" not in p.parts]
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def main() -> int:
    baseline = counts()
    rec("baseline", three_counts=baseline, inbox=inbox_stat())

    lockfh = LOCK.open("a")
    fcntl.flock(lockfh, fcntl.LOCK_EX | fcntl.LOCK_NB)  # 持池写锁 ⇒ 池不起 ⇒ 自造 job 停 QUEUED
    created_id = None
    try:
        # ── ① 走 E1 建一个 ACTIVE job（pdf_path = 真 %PDF- 探针文件）──
        st, body, raw = http("POST", "/api/jobs", {"pdf_path": str(PROBE_PDF)})
        rec("E1 建 job", http_status=st, body=body, raw=raw[:400])
        created_id = (body or {}).get("job_id")
        if st != 201 or not created_id:
            rec("ABORT", reason="E1 未返回 201/job_id", http_status=st)
            return 2

        st2, body2, _ = http("GET", f"/api/jobs/{created_id}")
        rec("E2 查该 job（应为 ACTIVE=QUEUED）", http_status=st2, state=(body2 or {}).get("state"), body=body2)

        # ── ② summary 端点：zang_probe.pdf 必须进 exempt(active_job) ──
        st3, body3, raw3 = http("GET", "/api/jobs/inbox/summary")
        exempt = {e["rel_path"]: e for e in (body3 or {}).get("exempt", [])}
        zp = exempt.get("20261011/zang_probe.pdf")
        rec(
            "GET /api/jobs/inbox/summary",
            http_status=st3,
            usage=(body3 or {}).get("usage"),
            collect_files=(body3 or {}).get("collect_files"),
            exempt_files=(body3 or {}).get("exempt_files"),
            zang_probe_exempt=zp,
        )
        assert zp and zp.get("reason") == "active_job" and zp.get("job_id") == created_id, (
            "summary 未把活跃 job 引用的文件列入 active_job 豁免"
        )

        # ── ③ 端点默认 dry-run：空体 / {"apply":false} 都不改盘 ──
        before = inbox_stat()
        s_no, b_no, _ = http("POST", "/api/jobs/inbox/gc", None)
        s_false, b_false, _ = http("POST", "/api/jobs/inbox/gc", {"apply": False})
        after = inbox_stat()
        rec(
            "POST /api/jobs/inbox/gc（空体 / apply:false）",
            no_body_status=s_no,
            no_body_mode=(b_no or {}).get("mode"),
            apply_false_status=s_false,
            apply_false_mode=(b_false or {}).get("mode"),
            inbox_before=before,
            inbox_after=after,
            unchanged=(before == after),
        )
        assert before == after, "默认 dry-run 竟然改了盘"

        # ── ④ CLI --retention-days 0：其余全回收，zang_probe 仍豁免 ──
        cp = subprocess.run(
            [str(SERVER / ".venv" / "bin" / "python"), "-m", "app.inbox_gc",
             "--dry-run", "--json", "--no-report", "--retention-days", "0"],
            cwd=str(SERVER), capture_output=True, text=True, timeout=180,
        )
        cli = json.loads(cp.stdout)
        cli_exempt = {e["rel_path"]: e for e in cli["exempt"]}
        cli_collect = {c["rel_path"]: c for c in cli["collect"]}
        rec(
            "CLI --retention-days 0 --dry-run",
            exit=cp.returncode,
            collect_files=cli["collect_files"],
            collect_reasons=sorted({c["reason"] for c in cli["collect"]}),
            zang_probe_exempt=cli_exempt.get("20261011/zang_probe.pdf"),
            zang_probe_in_collect=("20261011/zang_probe.pdf" in cli_collect),
        )
        assert "20261011/zang_probe.pdf" not in cli_collect, "ACTIVE 文件竟进了待回收"
        assert cli_exempt["20261011/zang_probe.pdf"]["reason"] == "active_job"

        # ── ⑤ E1 / E8 错误体对齐（顶层键集合同形）──
        txt = Path("/Users/kevin/.hermes/profiles/zang/cache/scratch/not_a_pdf.txt")
        txt.write_text("this is a plain text file, definitely not a portable document\n", encoding="utf-8")
        e1_missing = http("POST", "/api/jobs", {"pdf_path": "/nonexistent/xyz.pdf"})
        e1_notpdf = http("POST", "/api/jobs", {"pdf_path": str(txt)})
        # E8：错误的 Content-Type ⇒ 400 BAD_CONTENT_TYPE（裸字节流，非 JSON 体）
        e8 = http("POST", "/api/jobs/upload", raw_body=b"hello", headers={"Content-Type": "text/plain"})
        rec(
            "错误体对齐",
            e1_pdf_not_found={"status": e1_missing[0], "body": e1_missing[1], "top_keys": sorted((e1_missing[1] or {}).keys())},
            e1_not_a_pdf={"status": e1_notpdf[0], "body": e1_notpdf[1], "top_keys": sorted((e1_notpdf[1] or {}).keys())},
            e8_bad_content_type={"status": e8[0], "body": e8[1], "top_keys": sorted((e8[1] or {}).keys())},
        )
        assert e1_missing[0] == 400 and (e1_missing[1] or {}).get("error") == "PDF_NOT_FOUND"
        assert e1_notpdf[0] == 400 and (e1_notpdf[1] or {}).get("error") == "NOT_A_PDF"
        # 同形判据：三者**顶层都含 `error` ＋ `detail`**（E8 另有 `allowed`/`extra` 附加键，属其既有形态）
        for label, parsed in (("E1/PDF_NOT_FOUND", e1_missing[1]), ("E1/NOT_A_PDF", e1_notpdf[1]), ("E8/BAD_CONTENT_TYPE", e8[1])):
            assert {"error", "detail"} <= set(parsed or {}), f"{label} 顶层缺 error/detail"

    finally:
        # ── ⑥ 收尾：删该 job 及其 job_pages，回到基线 ──
        if created_id:
            conn = sqlite3.connect(DB)
            try:
                conn.execute("DELETE FROM job_pages WHERE job_id=?", (created_id,))
                conn.execute("DELETE FROM jobs WHERE job_id=?", (created_id,))
                conn.commit()
            finally:
                conn.close()
        after_counts = counts()
        rec("cleanup + final", deleted_job=created_id, three_counts=after_counts, matches_baseline=(after_counts == baseline))
        try:
            fcntl.flock(lockfh, fcntl.LOCK_UN)
        finally:
            lockfh.close()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nraw → {OUT}")
    return 0 if after_counts == baseline else 3


if __name__ == "__main__":
    sys.exit(main())
