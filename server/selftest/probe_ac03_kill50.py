#!/usr/bin/env python
"""AC-03 **追加点位**探针：在「已提交 ≥ 50%」处 SIGKILL（本单 D-2 收口用）。

背景：`REPORT_1b-i.md` §3 段② 的唯一一次 kill 落在**已提交 3/7 页（42.9%）**（连续前缀 2/7＝28.6%），
而 AC-03 的 X 取 **{25%, 50%} 两个百分点各 ≥1 次** ⇒ **50% 点未覆盖**。本探针补这一点位。

纪律（与既有自测同款）：
  * **只用副本库**（SQLite backup API 一致快照；正式库全程 `mode=ro`）；
  * **精确 PID** SIGKILL（池 + 状态文件里的 worker），**无 `pkill -f` / `killall`**；
  * `chunk_size=1`（提交粒度＝1 页）⇒ 让「已提交页数」这个变量可控，点位命中更精确；
  * `w=2`（比 4 慢，给轮询留出窗口；同时仍是并行臂）；
  * 与 **1b-i 串行臂同页区间**（`tmp.pdf` 27–33）并用 **1b-i 自己的工具**交叉验证：
    `verify_1b_i.py export/diffcsv/subset`；
  * `finally` 清理：停自己的池与 worker（精确 PID）＋ 删临时工作区。

跑法：
    cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python selftest/probe_ac03_kill50.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SRV = Path(__file__).resolve().parents[1]           # feicui/server
FE = SRV.parent                                     # feicui
API_PY = SRV / ".venv" / "bin" / "python"
VERIFY = SRV / "selftest" / "verify_1b_i.py"
PROD_DB = FE / "yinpu.db"
EVID = SRV / "selftest" / "evidence" / "1b_ii"
PAGE_LO, PAGE_HI = 27, 33                            # 与 evidence/1b_i/52_serial_rows.csv 同区间
WORKERS = 2
CHUNK = 1                                            # 提交粒度 = 1 页
TARGET_DONE = 4                                      # 4/7 = 57.1% ≥ 50%（目标点位）
SERIAL_CSV = SRV / "selftest" / "evidence" / "1b_i" / "52_serial_rows.csv"
POLL_TIMEOUT_S = 120.0

STATE: dict = {"scratch": None, "pool": None, "pids": []}


def say(msg: str = "") -> None:
    print(msg, flush=True)


def ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def q1(db: Path, sql: str, params: tuple = ()):
    c = ro(db)
    try:
        row = c.execute(sql, params).fetchone()
        return None if row is None else row[0]
    finally:
        c.close()


def tool(*args) -> tuple[int, str]:
    r = subprocess.run([str(API_PY), str(VERIFY), *map(str, args)], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def read_worker_pids(state_file: Path) -> list[int]:
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [int(w["pid"]) for w in data.get("workers", []) if w.get("pid")]


def spawn_pool(env: dict, log: Path, drain: bool) -> subprocess.Popen:
    args = [str(API_PY), "-m", "app.pool", "--workers", str(WORKERS)]
    if drain:
        args.append("--drain")
    fh = log.open("ab")
    return subprocess.Popen(args, cwd=str(SRV), env=env, stdout=fh, stderr=subprocess.STDOUT)


def kill_exact(pid: int, sig: str = "-KILL") -> int:
    """只按精确 PID 发信号（绝无宽匹配）。"""
    subprocess.run(["kill", sig, str(pid)], capture_output=True)
    time.sleep(0.2)
    return subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="feicui_ac03_50_"))
    STATE["scratch"] = scratch
    say("=" * 78)
    say("AC-03 追加点位探针：已提交 ≥50% 处 SIGKILL → 续跑")
    say(f"时点 {datetime.now().astimezone().isoformat(timespec='seconds')}｜临时工作区 {scratch}")
    say(f"页区间 [{PAGE_LO},{PAGE_HI}] chunk_size={CHUNK} workers={WORKERS} 目标已提交页 ≥{TARGET_DONE}/7")
    say("=" * 78)

    copy_db = scratch / "copy50.db"
    src, dst = ro(PROD_DB), sqlite3.connect(str(copy_db))
    try:
        dst.execute("PRAGMA journal_mode=WAL")
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()

    job_id = "job-ac03kill50-" + datetime.now().strftime("%H%M%S")
    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    conn = sqlite3.connect(str(copy_db))
    try:
        with conn:  # **只在副本库**：清历史 job + 直接落一个 job（AC-03 不经 E1 路径）
            conn.execute("DELETE FROM job_pages")
            conn.execute("DELETE FROM jobs")
            conn.execute(
                """INSERT INTO jobs(job_id,pdf_path,pdf_name,page_from,page_to,chunk_size,
                                    total_pages,state,rerun,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, str(FE / "tmp.pdf"), "tmp.pdf", PAGE_LO, PAGE_HI, CHUNK,
                 PAGE_HI - PAGE_LO + 1, "QUEUED", 0, now, now),
            )
            conn.executemany(
                """INSERT INTO job_pages(job_id,pdf_name,page,chunk_index,state,updated_at)
                   VALUES (?,?,?,?,?,?)""",
                [(job_id, "tmp.pdf", p, p - PAGE_LO, "PENDING", now) for p in range(PAGE_LO, PAGE_HI + 1)],
            )
    finally:
        conn.close()
    say(f"副本库 {copy_db.name}：job={job_id}，job_pages={PAGE_HI - PAGE_LO + 1} 行（chunk_size={CHUNK}）")

    env = dict(os.environ)
    env.update(
        FEICUI_DB=str(copy_db),
        FEICUI_FACES_DIR=str(scratch / "faces"),
        FEICUI_WORKERS=str(WORKERS),
        FEICUI_POOL_STATE=str(scratch / "pool.state.json"),
        FEICUI_WORKER_LOG_DIR=str(scratch / "wlog"),
        PYTHONUNBUFFERED="1",
    )
    state_file = scratch / "pool.state.json"
    pool = spawn_pool(env, scratch / "pool_kill.log", drain=False)
    STATE["pool"] = pool
    say(f"池已起：pid={pool.pid}（w={WORKERS}，chunk_size={CHUNK}）")

    # ---- 轮询到「已提交 ≥ TARGET_DONE」立即 SIGKILL（精确 PID）----
    t0, done_at_kill, killed = time.time(), None, []
    while time.time() - t0 < POLL_TIMEOUT_S:
        done = int(q1(copy_db, "SELECT COUNT(*) FROM job_pages WHERE state='DONE'") or 0)
        if done >= TARGET_DONE:
            done_at_kill = done
            worker_pids = read_worker_pids(state_file)
            killed = [f"worker:{p}:rc={kill_exact(p)}" for p in worker_pids]
            killed.append(f"pool:{pool.pid}:rc={kill_exact(pool.pid)}")
            break
        if pool.poll() is not None:
            say(f"✗ 池提前退出（rc={pool.returncode}）——轮询窗口内没等到 {TARGET_DONE} 页，见日志")
            return 1
        time.sleep(0.05)

    if done_at_kill is None:
        say(f"✗ {POLL_TIMEOUT_S:.0f}s 内未达到 {TARGET_DONE} 页已提交（点位未命中）")
        return 1

    say(f"\n[SIGKILL] 已提交 {done_at_kill}/{PAGE_HI - PAGE_LO + 1} 页"
        f"（{done_at_kill / (PAGE_HI - PAGE_LO + 1) * 100:.1f}%），逐 PID 结果：{'；'.join(killed)}")
    pages_at_kill = [
        dict(r) for r in ro(copy_db).execute(
            "SELECT page, chunk_index, state FROM job_pages WHERE job_id=? AND state='DONE' ORDER BY page", (job_id,))
    ]
    rows_at_kill = int(q1(copy_db, "SELECT COUNT(*) FROM stamps WHERE pdf_name='tmp.pdf' AND page BETWEEN ? AND ?",
                          (PAGE_LO, PAGE_HI)) or 0)
    rc_k, out_k = tool("export", copy_db, "tmp.pdf", PAGE_LO, PAGE_HI, scratch / "killrows.csv")
    say(f"[库里状态] 已 DONE 页={[p['page'] for p in pages_at_kill]}｜stamps 行数={rows_at_kill}｜"
        f"出口状态={q1(copy_db, 'SELECT state FROM jobs WHERE job_id=?', (job_id,))}")

    # ---- 续跑（--drain 跑完）----
    say("\n[续跑] 重新拉起池 --drain（残留 RUNNING 页由 claim_job 退回 PENDING）…")
    pool2 = spawn_pool(env, scratch / "pool_resume.log", drain=True)
    STATE["pool"] = pool2
    tail, _ = pool2.communicate(timeout=600)
    say(f"[续跑] 池 rc={pool2.returncode}")

    # ---- 复算与交叉验证（用 1b-i 自己的工具）----
    rc_a, out_a = tool("export", copy_db, "tmp.pdf", PAGE_LO, PAGE_HI, scratch / "afterrows.csv")
    rc_s, out_s = tool("subset", scratch / "killrows.csv", scratch / "afterrows.csv")
    rc_c, out_c = tool("counts", copy_db, "tmp.pdf", PAGE_LO, PAGE_HI)
    rc_d, out_d = tool("diffcsv", SERIAL_CSV, scratch / "afterrows.csv")
    rc_r, out_r = tool("rowsig", copy_db, "tmp.pdf", PAGE_LO, PAGE_HI)

    total_pages = PAGE_HI - PAGE_LO + 1
    failed = int(q1(copy_db, "SELECT COUNT(*) FROM job_pages WHERE job_id=? AND state='FAILED'", (job_id,)) or 0)
    done_final = int(q1(copy_db, "SELECT COUNT(*) FROM job_pages WHERE job_id=? AND state='DONE'", (job_id,)) or 0)
    result = {
        "probe": "AC-03 追加点位：≥50% 处 SIGKILL",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "range": [PAGE_LO, PAGE_HI], "chunk_size": CHUNK, "workers": WORKERS,
        "kill_point": {
            "committed_pages": done_at_kill, "total_pages": total_pages,
            "committed_pct": round(done_at_kill / total_pages * 100, 1),
            "contiguous_prefix_pages": len(pages_at_kill),
            "pages_done_at_kill": [p["page"] for p in pages_at_kill],
            "rows_at_kill": rows_at_kill,
            "killed_pids": killed,
            "pool_state": q1(copy_db, "SELECT state FROM jobs WHERE job_id=?", (job_id,)),
        },
        "after_resume": {
            "state": q1(copy_db, "SELECT state FROM jobs WHERE job_id=?", (job_id,)),
            "done_pages": done_final, "failed_pages": failed,
            "rows": int(q1(copy_db, "SELECT COUNT(*) FROM stamps WHERE pdf_name='tmp.pdf' AND page BETWEEN ? AND ?",
                           (PAGE_LO, PAGE_HI)) or 0),
        },
        "tools": {
            "export_killrows": out_k[-400:], "export_afterrows": out_a[-400:],
            "subset_kill_vs_final": out_s, "counts_final": out_c, "rowsig_final": out_r,
            "diffcsv_vs_1bi_serial_arm": out_d,
            "diffcsv_note": f"对照文件 = evidence/1b_i/52_serial_rows.csv（1b-i 串行臂，同区间 {PAGE_LO}-{PAGE_HI}）",
        },
        "rc": {"export_k": rc_k, "export_a": rc_a, "subset": rc_s, "counts": rc_c, "rowsig": rc_r, "diffcsv": rc_d},
        "verdict": {
            "kill_at_or_above_50pct": done_at_kill / total_pages >= 0.5,
            "resume_completed": failed == 0 and done_final == total_pages,
            "killrows_zero_rewrite": "IDENTICAL" in out_s.upper(),
            "matches_1bi_serial_arm": "IDENTICAL" in out_d.upper(),
        },
    }
    say("\n---- 结论 ----")
    for k, v in result["verdict"].items():
        say(f"  {k} = {v}")
    say(f"  kill 点位 = 已提交 {done_at_kill}/{total_pages} 页（{result['kill_point']['committed_pct']}%）"
        f"｜连续前缀 {len(pages_at_kill)} 页｜断点行数 {rows_at_kill}")
    say(f"  subset(killrows → final) = {out_s}")
    say(f"  diffcsv(1b-i 串行臂 vs 本臂) = {out_d}")
    out_path = EVID / "46_reg_ac03_kill50_probe.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"\n证据已落 {out_path}")
    return 0 if all(result["verdict"].values()) else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        # 清理：只停**自己**的池与 worker（精确 PID）；删自己的临时工作区
        pool = STATE.get("pool")
        if pool is not None and pool.poll() is None:
            pool.kill()
        for pid in read_worker_pids(Path(STATE["scratch"]) / "pool.state.json") if STATE.get("scratch") else []:
            kill_exact(pid)
        if STATE.get("scratch") and Path(STATE["scratch"]).is_dir():
            shutil.rmtree(STATE["scratch"], ignore_errors=True)
        print(f"[cleanup] 临时工作区已删 = {not Path(STATE['scratch'] or '/nonexistent').exists()}", flush=True)
    sys.exit(code)
