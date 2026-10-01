#!/usr/bin/env python3
"""双起保护 + 并发两单的端到端取证（阶段 1c-激活）。

做四件事（全程只调 HTTP + 只读 SELECT，只有最后那步是"人为再起一个池"以取证 exit 5）：
  ① 经 `http://localhost:5164/feicui/api/jobs` 建 job A（tmp.pdf 13–19）；
  ② 1.5s 后建 job B（秦汉印典 5–8，**另一本书 ⇒ 不撞 409**）；此刻 A 的池应已在跑
     ⇒ 期望拉起器走「池已在跑 ⇒ 跳过」分支（或候选池 exit 5）——两种都算正常分支；
  ③ 人为再起一个池（同库同锁）⇒ 期望 **exit 5** + 「⏭ 跳过启动」提示（池自身的双起保护）；
  ④ 采 E2 直到 A/B 双双 DONE，并与库内复算交叉核对。

两本书的页区间都**已被既有行覆盖** ⇒ 行级幂等 `skip` 生效、**不新增 `stamps` 行**（便于证明「原有行未变」）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://localhost:5164/feicui/api"
DB = "/Users/kevin/bistro/shu/feicui/yinpu.db"
SERVER_DIR = "/Users/kevin/bistro/shu/feicui/server"
LAUNCH_LOG = "/Users/kevin/bistro/shu/feicui/server/.run/pool-launch.log"


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


def tail(path: str, n: int = 6) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-n:]).rstrip()
    except OSError as exc:
        return f"(读不到 {path}：{exc!r})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="tmp.pdf:13:19")
    ap.add_argument("--b", default="秦汉印典 上海书画 金怀英  1997 ok.pdf:5:8")
    ap.add_argument("--poll", type=float, default=300.0)
    args = ap.parse_args()

    def split(spec: str):
        pdf, lo, hi = spec.rsplit(":", 2)
        return pdf, int(lo), int(hi)

    pdf_a, a_lo, a_hi = split(args.a)
    pdf_b, b_lo, b_hi = split(args.b)
    t0 = time.time()

    log(f"=== ① 建 job A：{pdf_a} [{a_lo},{a_hi}] ===")
    code, body = _req("POST", "/jobs", {"pdf_path": pdf_a, "page_range": [a_lo, a_hi]})
    log(f"→ {code} {json.dumps(body, ensure_ascii=False)}")
    if code != 201:
        return 1
    job_a = body["job_id"]  # type: ignore[index]

    time.sleep(1.5)
    log(f"=== ② 建 job B（另一本书，1.5s 后）：{pdf_b} [{b_lo},{b_hi}] ===")
    code, body = _req("POST", "/jobs", {"pdf_path": pdf_b, "page_range": [b_lo, b_hi]})
    log(f"→ {code} {json.dumps(body, ensure_ascii=False)}")
    if code != 201:
        return 1
    job_b = body["job_id"]  # type: ignore[index]
    log("--- pool-launch.log 尾部（看拉起器怎么处理第二单）---")
    print(tail(LAUNCH_LOG, 12), flush=True)

    log("=== ③ 人为再起一个池（同库同锁）⇒ 期望 exit 5 ===")
    env = os.environ.copy()
    env.update({"FEICUI_DB": DB, "FEICUI_ALLOW_PROD_MIGRATE": "1", "PYTHONUNBUFFERED": "1"})
    proc = subprocess.run(
        [os.path.join(SERVER_DIR, ".venv", "bin", "python"), "-m", "app.pool", "--workers", "1", "--drain"],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    log(f"重复起的池 rc={proc.returncode}（期望 5）")
    print("--- stderr ---\n" + (proc.stderr or "(空)"), flush=True)
    print("--- stdout(tail) ---\n" + "\n".join((proc.stdout or "").splitlines()[-4:]), flush=True)

    log("=== ④ E2 采样（两单都要 DONE；人不出手）===")
    jobs = {job_a: "A", job_b: "B"}
    states: dict[str, list[str]] = {job_a: [], job_b: []}
    finals: dict[str, dict] = {}
    while time.time() - t0 < args.poll:
        pending = [j for j in jobs if j not in finals]
        if not pending:
            break
        for jid in pending:
            code, prog = _req("GET", f"/jobs/{jid}")
            if code != 200 or not isinstance(prog, dict):
                log(f"{jobs[jid]} E2 读失败 {code}：{prog}")
                continue
            print(
                f"t+{time.time() - t0:6.1f}s {jobs[jid]} state={prog['state']:14s} "
                f"done={prog['done_pages']}/{prog['total_pages']} failed={prog['failed_pages']}",
                flush=True,
            )
            states[jid].append(prog["state"])
            if prog["state"] in {"DONE", "FAILED_PARTIAL"}:
                finals[jid] = prog
        time.sleep(3.0)

    log("=== ⑤ 库内复算交叉核对 + 计数 ===")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        for jid, tag in jobs.items():
            jr = dict(conn.execute("SELECT * FROM jobs WHERE job_id = ?", (jid,)).fetchone())
            agg = dict(
                conn.execute(
                    "SELECT COUNT(*) total, SUM(state='DONE') done, SUM(state='FAILED') failed,"
                    " COALESCE(SUM(inserted),0) inserted, COALESCE(SUM(updated),0) updated,"
                    " COALESCE(SUM(skipped),0) skipped FROM job_pages WHERE job_id = ?",
                    (jid,),
                ).fetchone()
            )
            print(f"{tag} jobs 行 = " + json.dumps(jr, ensure_ascii=False))
            print(f"{tag} 复算   = " + json.dumps(agg, ensure_ascii=False))
        print(f"stamps 全表 = {conn.execute('SELECT count(*) FROM stamps').fetchone()[0]}")
        print(
            "活跃 job（应 0）= "
            + json.dumps(
                [r[0] for r in conn.execute("SELECT job_id FROM jobs WHERE state IN ('QUEUED','RUNNING','PAUSED')")]
            )
        )
    finally:
        conn.close()

    log("--- pool-launch.log 尾部 20 行 ---")
    print(tail(LAUNCH_LOG, 20), flush=True)

    ok_a = finals.get(job_a, {}).get("state") == "DONE"
    ok_b = finals.get(job_b, {}).get("state") == "DONE"
    seq_a = " -> ".join(dict.fromkeys(states[job_a]))
    seq_b = " -> ".join(dict.fromkeys(states[job_b]))
    print()
    print(f"job A = {job_a} 序列 = {seq_a}")
    print(f"job B = {job_b} 序列 = {seq_b}")
    print(f"重复池 rc = {proc.returncode}（5 = 锁被占，正常分支）")
    print(f"判定 = {'PASS' if ok_a and ok_b and proc.returncode == 5 else 'FAIL'}")
    return 0 if ok_a and ok_b else 1


if __name__ == "__main__":
    raise SystemExit(main())
