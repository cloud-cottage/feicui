#!/usr/bin/env python3
"""E1 ⇒ 自动跑完 的端到端采样器（阶段 1c-激活；只读 + 一次建单）。

用法：
    python3 ops/1c/e2e_run.py --create tmp.pdf:13:19 --poll 300

流程：
  1. **经** `http://localhost:5164/feicui/api/jobs`（＝面板托管链路：5164 → 5195 前端代理 → 5196 API）
     建一个 job（**人是缺席的**：本脚本不碰池、不碰 DB，只调 HTTP）；
  2. 立刻重复建同一本书 ⇒ 期望 **409**（活跃 job 互斥）；
  3. 每 3s 采一次 E2（`state` / `done_pages` / `failed_pages` / 计数）直到 `DONE`/`FAILED_PARTIAL`/超时；
  4. 结束后用**库内复算**（只读 SELECT）交叉核对最后一次 E2 读数。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# 迁移后（2026-09-20 14:47 shu → xiai）：**不再硬编码绝对路径**。
#   * 默认 DB 由本脚本自身位置推导（ops/1c/e2e_run.py → parents[2] = feicui/ ⇒ feicui/yinpu.db）；
#   * `FEICUI_DB` 可覆盖 —— **自测一律指向副本库**（硬约束：不得向正式库写 stamps）；
#   * `FEICUI_API_BASE` 同理可覆盖（自测用**非登记端口**的一次性副本 API，不动面板托管链路）。
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "yinpu.db"
BASE = os.environ.get("FEICUI_API_BASE", "http://localhost:5164/feicui/api")
DB = os.environ.get("FEICUI_DB", str(_DEFAULT_DB))


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", required=True, help="pdf_path:page_from:page_to（pdf_path 相对 feicui/）")
    ap.add_argument("--poll", type=float, default=300.0)
    ap.add_argument("--interval", type=float, default=3.0)
    args = ap.parse_args()

    pdf, lo, hi = args.create.split(":")
    lo, hi = int(lo), int(hi)

    log(f"=== ① 经 {BASE} 建 job（默认＝面板托管链路 5164 → 5195 前端代理 → 5196 API；自测可被 FEICUI_API_BASE 覆盖）===")
    code, body = _req("POST", "/jobs", {"pdf_path": pdf, "page_range": [lo, hi]})
    log(f"POST /feicui/api/jobs → {code}")
    print(json.dumps(body, ensure_ascii=False, indent=2), flush=True)
    if code != 201:
        log("✗ 建单未返回 201，终止")
        return 1
    job_id = body["job_id"]  # type: ignore[index]

    log("=== ② 立刻重复建同书 ⇒ 期望 409 ===")
    code2, body2 = _req("POST", "/jobs", {"pdf_path": pdf, "page_range": [lo, hi]})
    log(f"POST（重复） → {code2}")
    print(json.dumps(body2, ensure_ascii=False, indent=2), flush=True)
    dup_ok = code2 == 409

    log("=== ③ E2 采样（人不出手）===")
    t0 = time.time()
    samples = []
    final = None
    while time.time() - t0 < args.poll:
        code3, prog = _req("GET", f"/jobs/{job_id}")
        if code3 != 200 or not isinstance(prog, dict):
            log(f"E2 读失败 {code3}：{prog}")
            break
        line = (
            f"t+{time.time() - t0:6.1f}s state={prog['state']:14s} "
            f"done={prog['done_pages']}/{prog['total_pages']} failed={prog['failed_pages']} "
            f"detected={prog.get('detected')} inserted={prog.get('inserted')} "
            f"updated={prog.get('updated')} skipped={prog.get('skipped')} ocr_empty={prog.get('ocr_empty')}"
        )
        print(line, flush=True)
        samples.append((round(time.time() - t0, 1), prog["state"], prog["done_pages"], prog["failed_pages"]))
        if prog["state"] in {"DONE", "FAILED_PARTIAL"}:
            final = prog
            break
        time.sleep(args.interval)

    log("=== ④ 库内复算交叉核对（只读）===")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        jr = dict(conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())
        agg = dict(
            conn.execute(
                "SELECT COUNT(*) total, SUM(state='DONE') done, SUM(state='FAILED') failed,"
                " COALESCE(SUM(detected),0) detected, COALESCE(SUM(inserted),0) inserted,"
                " COALESCE(SUM(updated),0) updated, COALESCE(SUM(skipped),0) skipped,"
                " COALESCE(SUM(ocr_empty),0) ocr_empty FROM job_pages WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        )
        print("jobs 行            = " + json.dumps(jr, ensure_ascii=False))
        print("job_pages 复算     = " + json.dumps(agg, ensure_ascii=False))
        print(f"stamps 全表行数    = {conn.execute('SELECT count(*) FROM stamps').fetchone()[0]}")
        print(
            "逐页 job_pages     = "
            + json.dumps(
                [
                    dict(r)
                    for r in conn.execute(
                        "SELECT page, state, detected, inserted, skipped, ocr_empty, error"
                        " FROM job_pages WHERE job_id = ? ORDER BY page",
                        (job_id,),
                    )
                ],
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()

    states = [s[1] for s in samples]
    print()
    print(f"采样点数 = {len(samples)}；出现过的 state 序列 = {' -> '.join(dict.fromkeys(states))}")
    print(f"job_id   = {job_id}")
    print(f"409 分支 = {'OK' if dup_ok else 'FAIL'}")
    ok = (
        final is not None
        and final["state"] in {"DONE", "FAILED_PARTIAL"}
        and "QUEUED" in states
        and "RUNNING" in states
        and dup_ok
    )
    print(f"端到端判定 = {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
