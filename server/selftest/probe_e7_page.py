#!/usr/bin/env python
"""E7 `?page=` 翻页探针（可复现证据，**有界**，绝不进死循环）。

用途：把 E7 的**页码路径**与**游标路径**各翻一遍，逐页打印
`page / items / has_more / next_cursor`，并给出两路 key 集合的相等性判定。

为什么需要它（本单根因）：E7 的 `GET /api/jobs` 原先**没有 `page` 查询参数**（被框架静默忽略），
且游标路径把 keyset `WHERE` 与 `OFFSET` 叠加（重复跳过）⇒ 第二页恒为 0 条而 `has_more` 仍为真、
`next_cursor` 却为 `null` ⇒ 客户端（自测夹具）死循环（上一轮 54k 行失控的机理）。

纪律（与 `verify_1b_ii.py` 同）：
  * **只用副本库**（SQLite backup API 取一致快照，绝不动 `feicui/yinpu.db`）；
  * **动态空闲端口**（从 5341 起探测，避开 5164/5195/5196/5555/5173/5174）；
  * 停服务只按**自己记下的精确 PID**（无 pkill / killall）；
  * `finally` 清理：停服务 + 删临时工作区；
  * 循环**硬上界**（`总页数 + 2`，上限 50），游标不推进即 break。

跑法：
    cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python selftest/probe_e7_page.py [--out 文件.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SRV = Path(__file__).resolve().parents[1]          # feicui/server
FE = SRV.parent                                    # feicui
API_PY = SRV / ".venv" / "bin" / "python"
PROD_DB = FE / "yinpu.db"
PORT_START = 5341                                  # 非登记端口段
FORBIDDEN_PORTS = {5164, 5195, 5196, 5555, 5173, 5174}
N_JOBS = 5                                         # 题目要求：total=5、limit=1 ⇒ page=1..6 全表
PAGE_LOOP_CAP = 50                                 # ① 翻页循环硬上界（与夹具同款护栏）
CURSOR_LOOP_CAP = 50                               # 游标循环硬上界
UNIFY_CREATED_AT = "2026-09-20T00:00:00+08:00"     # 刻意把 5 个 job 的 created_at 抹平成同值（最严情形）

STATE: dict = {"port": None, "proc": None, "scratch": None}


# ------------------------------------------------------------------ 基础设施
def say(msg: str = "") -> None:
    print(msg, flush=True)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_free_port(start: int = PORT_START, tries: int = 20) -> int:
    for port in range(start, start + tries):
        if port in FORBIDDEN_PORTS:
            continue
        if port_free(port):
            with socket.socket() as sck:
                try:
                    sck.bind(("127.0.0.1", port))
                except OSError:
                    continue
            return port
    raise SystemExit(f"✗ {start}..{start + tries} 内无空闲端口，中止")


def ro_conn(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def http(method: str, path: str, body=None, timeout: float = 30.0):
    url = f"http://127.0.0.1:{STATE['port']}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def http_json(method: str, path: str, body=None):
    code, raw = http(method, path, body)
    try:
        return code, json.loads(raw.decode("utf-8")), raw
    except Exception:
        return code, None, raw


def start_api(db: Path, port: int, export_root: Path, log: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(FEICUI_DB=str(db), FEICUI_API_PORT=str(port), FEICUI_ROOT=str(FE),
               FEICUI_EXPORT_ROOT=str(export_root), PYTHONUNBUFFERED="1")
    fh = log.open("wb")
    proc = subprocess.Popen([str(API_PY), "-m", "app.main"], cwd=str(SRV), env=env,
                            stdout=fh, stderr=subprocess.STDOUT)
    for _ in range(75):
        if proc.poll() is not None:
            raise SystemExit(f"✗ 接口层启动即退出（rc={proc.returncode}），见 {log}")
        try:
            code, _ = http("GET", "/api/health", timeout=3)
            if code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.4)
    raise SystemExit(f"✗ 接口层 30 s 内未就绪，见 {log}")


def stop_api(proc: subprocess.Popen | None) -> str:
    """按**精确 PID** 停（严禁 pkill / killall）。"""
    if proc is None:
        return "noop"
    pid = proc.pid
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    alive = subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0
    return "STILL_ALIVE" if alive else "gone"


# ------------------------------------------------------------------ 主流程
def run(out_path: Path | None) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="feicui_e7probe_"))
    STATE["scratch"] = scratch
    say("=" * 78)
    say("E7 `?page=` 翻页探针（页码路径 vs 游标路径）")
    say(f"临时工作区 {scratch}")
    say("=" * 78)

    STATE["port"] = pick_free_port(PORT_START)
    assert port_free(STATE["port"]), "选定端口应无监听"
    say(f"端口 {STATE['port']}（动态选定，无监听 ✓）")

    copy_db = scratch / "copy.db"
    s, d = ro_conn(PROD_DB), sqlite3.connect(str(copy_db))
    try:
        d.execute("PRAGMA journal_mode=WAL")
        with d:
            s.backup(d)          # 一致快照（WAL 安全）
    finally:
        d.close()
        s.close()
    conn = sqlite3.connect(str(copy_db))
    try:
        with conn:
            conn.execute("DELETE FROM job_pages")
            conn.execute("DELETE FROM jobs")
    finally:
        conn.close()

    # 5 个 job：路径各异（避免 uq_jobs_active_pdf_path），书名各异
    pdfs = []
    for i in range(N_JOBS):
        p = scratch / f"e7probe_{i}.pdf"
        p.write_bytes(b"%PDF-1.4\n% e7 page-param probe fixture\n")
        pdfs.append(p)

    STATE["proc"] = start_api(copy_db, STATE["port"], scratch / "exports_tmp", scratch / "api.log")
    say(f"接口层 pid={STATE['proc'].pid}（精确 PID，收尾按此停）")

    job_ids = []
    for p in pdfs:
        code, body, raw = http_json("POST", "/api/jobs", {"pdf_path": str(p), "page_range": [1, 1]})
        if code != 201:
            raise SystemExit(f"✗ E1 建 job 失败 code={code} raw={raw[:200]!r}")
        job_ids.append(body["job_id"])
    say(f"已建 {len(job_ids)} 个 job")

    # 刻意抹平 created_at（最严情形：排序键相同 ⇒ 只能靠 job_id 决胜）
    conn = sqlite3.connect(str(copy_db))
    try:
        with conn:
            conn.execute("UPDATE jobs SET created_at = ?, updated_at = ?", (UNIFY_CREATED_AT, UNIFY_CREATED_AT))
    finally:
        conn.close()
    want_ids = [r["job_id"] for r in ro_conn(copy_db).execute(
        "SELECT job_id FROM jobs ORDER BY created_at, job_id").fetchall()]
    say(f"库内 job 顺序（created_at 已抹平为 {UNIFY_CREATED_AT}）：{want_ids}")

    limit = 1
    # ---------------- ① 页码路径：page=1..N+2 逐页全表（硬上界） ----------------
    pages_rows, page_ids, page_loop_broken = [], [], None
    for page in range(1, min(N_JOBS + 2, PAGE_LOOP_CAP) + 1):
        code, body, raw = http_json("GET", f"/api/jobs?limit={limit}&page={page}")
        row = {"request": f"/api/jobs?limit={limit}&page={page}", "code": code}
        if code == 200 and isinstance(body, dict) and "items" in body:
            row.update(page=body.get("page"), items=len(body["items"]),
                       has_more=body.get("has_more"), next_cursor=body.get("next_cursor"),
                       total=body.get("total"),
                       ids=[it["job_id"] for it in body["items"]],
                       envelope_keys=sorted(body.keys()),
                       has_more_consistent=(body.get("has_more") == (body.get("next_cursor") is not None)))
            page_ids += row["ids"]
        else:
            row.update(error=raw.decode("utf-8", "replace")[:200], has_more_consistent=False)
        pages_rows.append(row)
    if len(pages_rows) >= PAGE_LOOP_CAP:
        page_loop_broken = "cap"

    # ---------------- ② 游标路径（硬上界 + 不推进即 break） ----------------
    cursor_rows, cursor_ids = [], []
    cursor, seen = None, set()
    guard_broken = None
    for _ in range(CURSOR_LOOP_CAP):
        qs = f"?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        code, body, raw = http_json("GET", f"/api/jobs{qs}")
        brow = {"request": f"/api/jobs{qs}", "code": code}
        if code != 200 or not isinstance(body, dict) or "items" not in body:
            brow.update(error=raw.decode("utf-8", "replace")[:200])
            cursor_rows.append(brow)
            guard_broken = "非信封响应"
            break
        brow.update(page=body.get("page"), items=len(body["items"]),
                    has_more=body.get("has_more"), next_cursor=body.get("next_cursor"),
                    has_more_consistent=(body.get("has_more") == (body.get("next_cursor") is not None)),
                    ids=[it["job_id"] for it in body["items"]])
        cursor_rows.append(brow)
        cursor_ids += brow["ids"]
        if not body["has_more"]:
            break
        # ② 游标不推进 / has_more 为真而 next_cursor 为空 ⇒ 立即 break（只报一条）
        if body["next_cursor"] is None:
            guard_broken = ("has_more=true 但 next_cursor=null（客户端会死循环）"
                            f"；两页原始报文：{json.dumps(cursor_rows[-1], ensure_ascii=False)}")
            break
        if body["next_cursor"] in seen:
            guard_broken = ("next_cursor 未推进（与上页重复）"
                            f"；两页原始报文：{json.dumps(cursor_rows[-1], ensure_ascii=False)}")
            break
        seen.add(body["next_cursor"])
        cursor = body["next_cursor"]
    else:
        guard_broken = f"游标循环触及硬上界 {CURSOR_LOOP_CAP}"

    # ---------------- ③ 两路 key 集合相等 ----------------
    verdict = {
        "page_path_ids": page_ids,
        "cursor_path_ids": cursor_ids,
        "want_ids_sql": want_ids,
        "page_path_equals_cursor_path": sorted(page_ids) == sorted(cursor_ids),
        "page_path_no_overlap_no_miss": sorted(page_ids) == sorted(want_ids),
        "cursor_path_no_overlap_no_miss": sorted(cursor_ids) == sorted(want_ids),
        "page_path_no_duplicates": len(page_ids) == len(set(page_ids)),
        "cursor_path_no_duplicates": len(cursor_ids) == len(set(cursor_ids)),
        "cursor_guard_broken": guard_broken,
        "page_loop_cap_hit": page_loop_broken,
    }
    # 超出末页必须空 items 且 has_more=false（不得再吐第一页）
    beyond = [r for r in pages_rows if r.get("page") and r["page"] > N_JOBS]
    verdict["beyond_last_page"] = [
        {"page": r["page"], "items": r["items"], "has_more": r["has_more"], "next_cursor": r["next_cursor"]}
        for r in beyond
    ]
    verdict["beyond_last_page_ok"] = bool(beyond) and all(
        r["items"] == 0 and r["has_more"] is False and r["next_cursor"] is None for r in beyond
    )

    say("\n---- ① 页码路径（limit=1，page=1..%d）----" % min(N_JOBS + 2, PAGE_LOOP_CAP))
    say(f"{'page':>5} {'items':>5}  {'has_more':<9} {'has_more==(next_cursor!=null)':<30} next_cursor")
    for r in pages_rows:
        say(f"{str(r.get('page')):>5} {str(r.get('items')):>5}  {str(r.get('has_more')):<9} "
            f"{str(r.get('has_more_consistent')):<30} {r.get('next_cursor')}")
    say("\n---- ② 游标路径（limit=1）----")
    say(f"{'page':>5} {'items':>5}  {'has_more':<9} next_cursor")
    for r in cursor_rows:
        say(f"{str(r.get('page')):>5} {str(r.get('items')):>5}  {str(r.get('has_more')):<9} {r.get('next_cursor')}")
    say("\n---- ③ 判定 ----")
    for k in ("page_path_no_overlap_no_miss", "cursor_path_no_overlap_no_miss",
              "page_path_equals_cursor_path", "beyond_last_page_ok", "page_path_no_duplicates",
              "cursor_path_no_duplicates"):
        say(f"  {k} = {verdict[k]}")
    if guard_broken:
        say(f"  ⚠ 游标护栏命中：{guard_broken}")

    payload = {
        "probe": "E7 page 参数翻页探针",
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "api_version": "1b-ii",
        "port": STATE["port"],
        "db": "临时副本库（backup API 一致快照，prod 只读）",
        "prod_db_sha256_of_stamps_fingerprint_B": _stamps_fp_b(copy_db),
        "n_jobs": N_JOBS,
        "limit": limit,
        "created_at_unified": UNIFY_CREATED_AT,
        "page_path": pages_rows,
        "cursor_path": cursor_rows,
        "verdict": verdict,
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        say(f"\n证据已落 {out_path}")
    return 0 if not guard_broken else 0  # 探针**不判分**，只取证（判分在 verify_1b_ii.py）


def _stamps_fp_b(db: Path) -> str:
    conn = ro_conn(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stamps)")]
        blob = "\n".join(
            json.dumps({c: r[c] for c in cols}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for r in conn.execute("SELECT * FROM stamps ORDER BY id")
        )
        return hashlib.md5((blob + "\n").encode("utf-8")).hexdigest()
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="证据 JSON 落盘路径")
    args = ap.parse_args()
    try:
        return run(Path(args.out) if args.out else None)
    finally:
        # ⑤ finally 清理：停自己的服务 + 删临时库/临时导出根 + 断言端口已释放
        say(f"\n[cleanup] 停接口层：{stop_api(STATE['proc'])}")
        if STATE["port"] and not port_free(STATE["port"]):
            for _ in range(20):
                if port_free(STATE["port"]):
                    break
                time.sleep(0.3)
        say(f"[cleanup] 端口 {STATE['port']} 已释放 = {port_free(STATE['port']) if STATE['port'] else 'n/a'}")
        if STATE["scratch"] and Path(STATE["scratch"]).is_dir():
            shutil.rmtree(STATE["scratch"], ignore_errors=True)
        say(f"[cleanup] 临时工作区已删 = {not Path(STATE['scratch']).exists()}")


if __name__ == "__main__":
    sys.exit(main())
