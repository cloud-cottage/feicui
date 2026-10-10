#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox 清理策略（R41 / §3.20）· **活端点 5196 复验**（重启载新码 ＋ 新字段可达 ＋ 「进程启动 ≥ 源文件 mtime」）—— Kong / feicui。

本脚本做三件事（**只读端点 ＋ 一次面板重启**，不跑 apply）：

  ① **重启前**：记 5196 监听 PID / `ps -o lstart` / `server/app/inbox_gc.py` mtime；打
     `GET /api/jobs/inbox/summary` 与 `POST /api/jobs/inbox/gc`（空体 ⇒ dry-run），记**新字段是否已在**；
  ② **面板单路重启**：`POST http://localhost:5555/api/restart {"sid":"feicui-api"}`（**不用 `pkill`/`killall`、不用 startAll**），
     轮询 `GET /api/health` 到 200；
  ③ **重启后**：记新 PID / `ps -o lstart` ⇒ 自证 **活进程启动时刻 ≥ `server/app/inbox_gc.py` mtime**；
     再打两端点 ⇒ 200 且**含新字段**（`capacity_target_bytes` / `collectable_bytes` / `capacity_gap_bytes` / `note`）；
     顺带核 dry-run 不改盘（inbox 文件数 / 总字节前后一致）。

跑法：
    cd /Users/kevin/bistro/xiai/feicui
    ./server/.venv/bin/python ops/job-upload/17_inbox_gc_live_recheck.py
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/Users/kevin/bistro/xiai/feicui")
SRC = ROOT / "server" / "app" / "inbox_gc.py"
API = "http://127.0.0.1:5196"
PANEL = "http://localhost:5555"
OUT = ROOT / "ops" / "job-upload" / "17_inbox_gc_live_recheck_raw.json"

NEW_KEYS = ("capacity_target_bytes", "collectable_bytes", "capacity_gap_bytes", "note")

result: dict = {"steps": [], "verdicts": {}}


def rec(name, **kw):
    result["steps"].append({"step": name, **kw})
    print(f"\n== {name} ==")
    for k, v in kw.items():
        print(f"   {k}: {json.dumps(v, ensure_ascii=False)}")


def http(method, url, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), raw
            except json.JSONDecodeError:
                return resp.status, None, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), raw
        except json.JSONDecodeError:
            return e.code, None, raw


def listener_pid(port=5196) -> int | None:
    cp = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
    for line in cp.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    return None


def lstart(pid: int | None) -> str | None:
    if not pid:
        return None
    cp = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True)
    return cp.stdout.strip() or None


def mtime_iso(path: Path) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))


def epoch(ts: str | None) -> float:
    """`ps -o lstart` 形如 `Sat Oct 11 07:06:33 2026` ⇒ epoch（None ⇒ 0.0）。"""
    return time.mktime(time.strptime(ts)) if ts else 0.0


def inbox_stat() -> dict:
    inbox = ROOT / "inbox"
    files = [p for p in inbox.rglob("*") if p.is_file() and ".trash" not in p.parts]
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def keys_of(body) -> dict:
    b = body or {}
    return {k: (k in b) for k in NEW_KEYS}


def main() -> int:
    # ── ① 重启前 ──
    pid_before = listener_pid()
    rec(
        "① 重启前（活进程 / 源文件）",
        pid=pid_before,
        lstart=lstart(pid_before),
        src_mtime=mtime_iso(SRC),
        src_bytes=SRC.stat().st_size,
        health=http("GET", f"{API}/api/health")[0],
    )
    s_b, sum_b, _ = http("GET", f"{API}/api/jobs/inbox/summary")
    g_b, gc_b, _ = http("POST", f"{API}/api/jobs/inbox/gc", None)
    rec(
        "① 重启前 · 端点读数（旧码 ⇒ 应无缺口字段）",
        summary_status=s_b,
        summary_usage=(sum_b or {}).get("usage"),
        summary_capacity_gate_triggered=(sum_b or {}).get("capacity_gate_triggered"),
        summary_new_keys_present=keys_of(sum_b),
        gc_status=g_b,
        gc_mode=(gc_b or {}).get("mode"),
        gc_new_keys_present=keys_of(gc_b),
    )
    before_keys_absent = not any(keys_of(sum_b).values()) and not any(keys_of(gc_b).values())
    result["verdicts"]["① 重启前旧码缺新字段（对照基线成立）"] = "PASS" if before_keys_absent else "FAIL"

    # ── ② 面板单路重启（含健康轮询）──
    st, body, raw = http("POST", f"{PANEL}/api/restart", {"sid": "feicui-api"})
    rec("② 面板重启 POST /api/restart {sid:feicui-api}", panel_status=st, panel_body=body, panel_raw=raw[:400])
    assert st == 200 and (body or {}).get("ok"), f"面板重启未成功：{st} {raw[:200]}"

    ok = False
    tries = 0
    t0 = time.time()
    while time.time() - t0 < 90:
        tries += 1
        try:
            with urllib.request.urlopen(f"{API}/api/health", timeout=3) as resp:
                if resp.status == 200:
                    ok = True
                    break
        except Exception:
            pass
        time.sleep(1.0)
    rec("② health 轮询", healthy=ok, poll_seconds=round(time.time() - t0, 1), tries=tries)
    result["verdicts"]["② 重启后 /api/health 200"] = "PASS" if ok else "FAIL"
    assert ok, "重启后 5196 health 未达 200"

    # ── ③ 重启后：新码已载 ＋ 端点含新字段 ＋ dry-run 不改盘 ──
    pid_after = listener_pid()
    ls_after = lstart(pid_after)
    src_mt = SRC.stat().st_mtime
    rec(
        "③ 重启后（活进程启动时刻 ≥ 源文件 mtime）",
        pid_before=pid_before,
        pid_after=pid_after,
        pid_changed=(pid_before != pid_after),
        lstart_after=ls_after,
        src_mtime=mtime_iso(SRC),
        proc_start_epoch=epoch(ls_after),
        src_mtime_epoch=src_mt,
        proc_start_minus_src_mtime_s=round(epoch(ls_after) - src_mt, 1),
    )
    result["verdicts"]["③ 活进程启动时刻 ≥ server/app/inbox_gc.py mtime"] = (
        "PASS" if epoch(ls_after) >= src_mt else "FAIL"
    )
    result["verdicts"]["③ 重启换 PID（新进程，非旧进程复用）"] = "PASS" if pid_after != pid_before else "FAIL"
    assert epoch(ls_after) >= src_mt, "活进程仍早于源文件 mtime（未载新码）"

    stat_before = inbox_stat()
    s_a, sum_a, raw_a = http("GET", f"{API}/api/jobs/inbox/summary")
    g_a, gc_a, raw_g = http("POST", f"{API}/api/jobs/inbox/gc", None)
    stat_after = inbox_stat()
    rec(
        "③ 重启后 · 端点读数（新码 ⇒ 应含缺口三数 ＋ note）",
        summary_status=s_a,
        summary_usage=(sum_a or {}).get("usage"),
        summary_capacity_gate_triggered=(sum_a or {}).get("capacity_gate_triggered"),
        summary_capacity_target_bytes=(sum_a or {}).get("capacity_target_bytes"),
        summary_collectable_bytes=(sum_a or {}).get("collectable_bytes"),
        summary_capacity_gap_bytes=(sum_a or {}).get("capacity_gap_bytes"),
        summary_note=(sum_a or {}).get("note"),
        gc_status=g_a,
        gc_mode=(gc_a or {}).get("mode"),
        gc_capacity_target_bytes=(gc_a or {}).get("capacity_target_bytes"),
        gc_collectable_bytes=(gc_a or {}).get("collectable_bytes"),
        gc_capacity_gap_bytes=(gc_a or {}).get("capacity_gap_bytes"),
        gc_note=(gc_a or {}).get("note"),
        inbox_before=stat_before,
        inbox_after=stat_after,
        inbox_unchanged=(stat_before == stat_after),
    )
    summary_ok = s_a == 200 and all(k in (sum_a or {}) for k in NEW_KEYS[:3])
    gc_ok = g_a == 200 and all(k in (gc_a or {}) for k in NEW_KEYS[:3])
    result["verdicts"]["③ GET /api/jobs/inbox/summary 200 且含缺口三数"] = "PASS" if summary_ok else "FAIL"
    result["verdicts"]["③ POST /api/jobs/inbox/gc 200 且含缺口三数（mode=dry-run）"] = (
        "PASS" if gc_ok and (gc_a or {}).get("mode") == "dry-run" else "FAIL"
    )
    result["verdicts"]["③ 端点默认 dry-run 不改盘（inbox 前后一致）"] = (
        "PASS" if stat_before == stat_after else "FAIL"
    )
    assert summary_ok and gc_ok, "重启后端点仍缺新字段"
    assert stat_before == stat_after, "端点 dry-run 改了盘"

    result["verdicts"]["全部（上面无 FAIL ⇒ 新码已载且端点可达）"] = (
        "PASS" if "FAIL" not in result["verdicts"].values() else "FAIL"
    )
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== VERDICT =====")
    for k, v in result["verdicts"].items():
        print(f"  {v:4s}  {k}")
    print(f"\nraw → {OUT}")
    return 0 if "FAIL" not in result["verdicts"].values() else 3


if __name__ == "__main__":
    raise SystemExit(main())
