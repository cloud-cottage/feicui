#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox 清理策略（R41 / §3.20）· **两条 OBS 收口复验**（修前 FAIL / 修后 PASS ＋ 容量闸缺口场景）—— Kong / feicui。

本脚本只做两件事（**全在临时目录 ＋ 临时库**，不碰真 `inbox/`、不碰生产库、不打 5196）：

  **OBS-1（CLI 命名分叉）**：规范 §3.20.4 / §3.20.5（Jing 冻结）写的是
      `python -m app.inbox_gc gc [--dry-run|--apply]`，而修前实现是 `python -m app.inbox_gc [--dry-run|--apply]`
      ⇒ 带 `gc` 报 `unrecognized arguments: gc`（exit 2）。
      * 修前读数：由 **HEAD 版模块真跑**取得（临时包 = `git show HEAD:server/app/inbox_gc.py` ＋ 真 `config.py`）；
      * 修后：**两种形态都 exit 0**，且 **dry-run 输出逐字段一致**（唯一差异 `generated_at`，另列不提 `report_path`）。
      * 反向哨兵：`python -m app.inbox_gc foo` 仍须 exit 2（**不得**把 argparse 松成「吞任何词」）。

  **OBS-2（容量闸缺口无显式字段）**：修前触发容量闸时只有 `capacity_gate_triggered: true` ＋ 清单，
      没有可直接读的缺口量。修后 plan / apply 输出（CLI 与端点**同源**）恒给三个数：
      `capacity_target_bytes` / `collectable_bytes` / `capacity_gap_bytes`，**缺口 > 0** 时另给一条人读 `note`；
      且 **`ACTIVE` 引用项一个不删、一个不进 collect**（不越权删）。

场景算术（夹具精确到字节，便于复算）：`active.pdf` 5000 B（被 `QUEUED` job 引用 ⇒ `ACTIVE`）
  ＋ `noref_old.pdf` 1000 B（mtime −60 天 ⇒ 超保留期）＋ `noref_2d.pdf` 1000 B（mtime −2 天 ⇒ 保留期内）
  ⇒ 总量 7000 B；`--max-bytes 6000`、ratio 0.8 ⇒ 目标 4800 B；可回收 = 1000 + 1000 = 2000 B
  ⇒ 淘汰到极限后剩 5000 B > 4800 B ⇒ **缺口 = 200 B**。

跑法：
    cd /Users/kevin/bistro/xiai/feicui
    ./server/.venv/bin/python ops/job-upload/16_inbox_gc_cli_gap_probe.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path("/Users/kevin/bistro/xiai/feicui")
SERVER = ROOT / "server"
PY = SERVER / ".venv" / "bin" / "python"
PROD_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
SCRATCH = Path("/Users/kevin/.hermes/profiles/zang/cache/scratch/inbox_gc_obs_20261011")
OUT = ROOT / "ops" / "job-upload" / "16_inbox_gc_cli_gap_probe_raw.json"

ACTIVE_BYTES = 5000
SMALL_BYTES = 1000
MAX_BYTES = 6000          # 容量闸上限 M
TARGET_BYTES = int(MAX_BYTES * 0.8)   # 4800
EXPECTED_GAP = (ACTIVE_BYTES - TARGET_BYTES)   # 200

result: dict = {"steps": [], "verdicts": {}}


def rec(name, **kw):
    result["steps"].append({"step": name, **kw})
    print(f"\n== {name} ==")
    for k, v in kw.items():
        print(f"   {k}: {json.dumps(v, ensure_ascii=False)}")


def verdicts():
    print("\n===== VERDICT =====")
    for k, v in result["verdicts"].items():
        print(f"  {v:4s}  {k}")


# --------------------------------------------------------------------------- 夹具
def make_pdf(path: Path, size: int) -> None:
    head = b"%PDF-1.7\n% fixture for inbox_gc obs probe\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = head + b"0" * max(0, size - len(head))
    path.write_bytes(body[:size] if len(body) > size else body)


def set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_for(inbox: Path, db: Path, reports: Path) -> dict:
    e = dict(os.environ)
    e["FEICUI_INBOX_DIR"] = str(inbox)
    e["FEICUI_DB"] = str(db)
    e["FEICUI_INBOX_GC_REPORT_DIR"] = str(reports)
    e["FEICUI_SERVER_CONFIG"] = str(reports / "no_config.json")  # 不读仓内 server/config.json
    e.pop("PYTHONPATH", None)
    return e


def build_env(root: Path):
    """临时 inbox（含 ACTIVE / 超期 / 保留期内三件）＋ 临时库（真库 WAL 感知副本 + 自造 job）。"""
    if root.exists():
        shutil.rmtree(root)
    inbox = root / "inbox"
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    today = datetime.now().astimezone()
    d = inbox / "20261011"
    make_pdf(d / "active.pdf", ACTIVE_BYTES)
    make_pdf(d / "noref_old.pdf", SMALL_BYTES)
    make_pdf(d / "noref_2d.pdf", SMALL_BYTES)
    set_mtime(d / "active.pdf", today)                       # ACTIVE：mtime 新，但被活跃 job 引用
    set_mtime(d / "noref_old.pdf", today - timedelta(days=60))
    set_mtime(d / "noref_2d.pdf", today - timedelta(days=2))

    db = root / "test.db"
    sqlite3.connect(PROD_DB).backup(sqlite3.connect(db))
    now_iso = today.replace(microsecond=0).isoformat()
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO jobs(job_id, pdf_path, pdf_name, chunk_size, total_pages, state, rerun, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("obs-active", str((d / "active.pdf").resolve()), "active.pdf", 8, 1, "QUEUED", 0, now_iso, now_iso),
        )
        conn.commit()
    finally:
        conn.close()
    return inbox, db, reports


def counts(db: Path) -> dict:
    conn = sqlite3.connect(db)
    try:
        return {
            "jobs": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "job_pages": conn.execute("SELECT COUNT(*) FROM job_pages").fetchone()[0],
            "stamps": conn.execute("SELECT COUNT(*) FROM stamps").fetchone()[0],
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------- 跑 CLI（修前 / 修后同签名）
def run_cli(cwd: Path, env: dict, *args: str, want_json: bool = True):
    cp = subprocess.run(
        [str(PY), "-m", "app.inbox_gc", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=180,
    )
    parsed = None
    if want_json:
        try:
            parsed = json.loads(cp.stdout)
        except json.JSONDecodeError:
            parsed = None
    return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr, "json": parsed}


def build_prefix_package() -> tuple[Path, str]:
    """HEAD 版模块副本（修前基线）——**真跑**而不是「读代码推断」。"""
    head_sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    head_src = subprocess.run(
        ["git", "-C", str(ROOT), "show", "HEAD:server/app/inbox_gc.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    pkg = SCRATCH / "prefix_pkg"
    (pkg / "app").mkdir(parents=True, exist_ok=True)
    (pkg / "app" / "__init__.py").write_text("", encoding="utf-8")
    # 真 `config.py`（只依赖 stdlib；`Settings` 字段与修后一致，缺口逻辑全在 inbox_gc.py）
    shutil.copy2(SERVER / "app" / "config.py", pkg / "app" / "config.py")
    (pkg / "app" / "inbox_gc.py").write_text(head_src, encoding="utf-8")
    return pkg, head_sha


def main() -> int:  # noqa: C901 - 线性复验脚本
    (SCRATCH / "prefix_pkg").parent.mkdir(parents=True, exist_ok=True)
    # ── 0. 修前基线身份自证（HEAD 副本确实是「修前」）──
    pkg, head_sha = build_prefix_package()
    prefix_src = (pkg / "app" / "inbox_gc.py").read_text(encoding="utf-8")
    post_src = (SERVER / "app" / "inbox_gc.py").read_text(encoding="utf-8")
    rec(
        "0 基线身份（HEAD 副本 = 修前；工作副本 = 修后）",
        head_sha=head_sha,
        prefix_has_gc_choices=('choices=["gc"]' in prefix_src),
        prefix_has_gap_field=("capacity_gap_bytes" in prefix_src),
        post_has_gc_choices=('choices=["gc"]' in post_src),
        post_has_gap_field=("capacity_gap_bytes" in post_src),
        prefix_len=len(prefix_src),
        post_len=len(post_src),
    )
    assert not prefix_src.count('choices=["gc"]') and "capacity_gap_bytes" not in prefix_src, "修前基线不是修前"
    assert 'choices=["gc"]' in post_src and "capacity_gap_bytes" in post_src, "工作副本不是修后"

    inbox, db, reports = build_env(SCRATCH / "cli")
    env = env_for(inbox, db, reports)
    common = ("--json", "--no-report", "--inbox", str(inbox), "--db", str(db),
              "--max-bytes", str(MAX_BYTES))

    # ── 1. OBS-1 修前：带 `gc` ⇒ exit 2 `unrecognized arguments: gc`（FAIL）──
    pre_gc = run_cli(pkg, env, "gc", "--dry-run", *common)
    pre_plain = run_cli(pkg, env, "--dry-run", *common)
    rec(
        "1 OBS-1 修前读数（HEAD 版模块真跑）",
        with_gc={"rc": pre_gc["rc"], "stderr_tail": pre_gc["stderr"].strip().splitlines()[-1:]},
        without_gc={"rc": pre_plain["rc"], "json_ok": pre_plain["json"] is not None},
    )
    result["verdicts"]["OBS-1 修前（`gc` 形）＝ FAIL（exit 2）"] = (
        "PASS" if pre_gc["rc"] == 2 and "unrecognized arguments: gc" in pre_gc["stderr"] else "FAIL"
    )
    result["verdicts"]["OBS-1 修前（省写形）＝ 可用（exit 0）"] = "PASS" if pre_plain["rc"] == 0 else "FAIL"
    assert pre_gc["rc"] == 2 and "unrecognized arguments: gc" in pre_gc["stderr"]
    assert pre_plain["rc"] == 0

    # ── 2. OBS-2 修前：容量闸触发但输出无缺口字段（FAIL）──
    pre_keys = sorted((pre_plain["json"] or {}).keys())
    rec(
        "2 OBS-2 修前读数（容量闸触发态，HEAD 版）",
        capacity_gate_triggered=(pre_plain["json"] or {}).get("capacity_gate_triggered"),
        collect=[{"rel": c["rel_path"], "reason": c["reason"], "bytes": c["bytes"]}
                 for c in (pre_plain["json"] or {}).get("collect", [])],
        keys_present={k: (k in (pre_plain["json"] or {})) for k in
                      ("capacity_target_bytes", "collectable_bytes", "capacity_gap_bytes", "note")},
        top_keys=pre_keys,
    )
    pre_gap_keys = [k for k in ("capacity_target_bytes", "collectable_bytes", "capacity_gap_bytes")
                    if k in (pre_plain["json"] or {})]
    result["verdicts"]["OBS-2 修前（缺口字段缺失）＝ FAIL"] = "PASS" if pre_gap_keys == [] else "FAIL"
    assert pre_gap_keys == [], "HEAD 版竟然已有缺口字段"

    # ── 3. OBS-1 修后：两种形态都 exit 0 ＋ 输出逐字段一致 ──
    post_gc = run_cli(SERVER, env, "gc", "--dry-run", *common)
    post_plain = run_cli(SERVER, env, "--dry-run", *common)
    a, b = post_gc["json"] or {}, post_plain["json"] or {}
    diff_keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    rec(
        "3 OBS-1 修后读数（规范形 `gc` vs 省写形）",
        with_gc_rc=post_gc["rc"],
        without_gc_rc=post_plain["rc"],
        keys_identical=(sorted(a) == sorted(b)),
        differing_keys=diff_keys,
        value_diff_of_differing_keys={k: [a.get(k), b.get(k)] for k in diff_keys},
    )
    result["verdicts"]["OBS-1 修后（规范形 `gc` exit 0）"] = "PASS" if post_gc["rc"] == 0 else "FAIL"
    result["verdicts"]["OBS-1 修后（省写形 exit 0）"] = "PASS" if post_plain["rc"] == 0 else "FAIL"
    result["verdicts"]["OBS-1 修后（两形输出逐字段一致，仅 generated_at 变）"] = (
        "PASS" if a and b and diff_keys == ["generated_at"] else "FAIL"
    )
    assert post_gc["rc"] == 0 and post_plain["rc"] == 0
    assert diff_keys == ["generated_at"], f"两形输出不一致：{diff_keys}"

    # ── 3b. 反向哨兵：非法子命令仍 exit 2（不得吞任何词）──
    post_bad = run_cli(SERVER, env, "foo", "--dry-run", *common, want_json=False)
    rec(
        "3b 反向哨兵：`python -m app.inbox_gc foo`",
        rc=post_bad["rc"], stderr_tail=post_bad["stderr"].strip().splitlines()[-1:],
    )
    result["verdicts"]["OBS-1 修后（非法子命令仍 exit 2，argparse 未被放松）"] = (
        "PASS" if post_bad["rc"] == 2 and "invalid choice" in post_bad["stderr"] else "FAIL"
    )
    assert post_bad["rc"] == 2

    # ── 4. OBS-2 修后：缺口场景（可回收 < 需回收）完整读数 ──
    r = a  # 修后规范形 dry-run
    rec(
        "4 OBS-2 修后 · 容量闸缺口场景（active=5000 / 两个 1000；M=6000 ⇒ 目标 4800 ⇒ 期望缺口 200）",
        capacity_gate_triggered=r["capacity_gate_triggered"],
        capacity_max_bytes=r["constants"]["capacity_max_bytes"],
        capacity_target_ratio=r["constants"]["capacity_target_ratio"],
        capacity_target_bytes=r["capacity_target_bytes"],
        capacity_target_bytes_in_constants=r["constants"]["capacity_target_bytes"],
        collectable_bytes=r["collectable_bytes"],
        capacity_gap_bytes=r["capacity_gap_bytes"],
        usage=r["usage"],
        collect=[{"rel": c["rel_path"], "reason": c["reason"], "bytes": c["bytes"]} for c in r["collect"]],
        exempt=[{"rel": e["rel_path"], "reason": e["reason"], "bytes": e["bytes"],
                 "job_id": e.get("job_id"), "state": e.get("state")} for e in r["exempt"]],
        note=r["note"],
    )
    gap_ok = (
        r["capacity_gate_triggered"] is True
        and r["capacity_target_bytes"] == TARGET_BYTES
        and r["collectable_bytes"] == 2 * SMALL_BYTES
        and r["capacity_gap_bytes"] == EXPECTED_GAP
        and isinstance(r.get("note"), str)
        and str(EXPECTED_GAP) in r["note"]
    )
    result["verdicts"][f"OBS-2 修后（缺口 {EXPECTED_GAP} B ＋ note 可读）"] = "PASS" if gap_ok else "FAIL"
    assert gap_ok, "缺口字段/note 不符"
    # ACTIVE 项：既不进 collect，也不因缺口被删（不越权删）
    collected_rels = {c["rel_path"] for c in r["collect"]}
    active_exempt = [e for e in r["exempt"] if e["reason"] == "active_job"]
    rec(
        "4b 不越权删 ACTIVE（铁律 ①）",
        active_in_collect=("20261011/active.pdf" in collected_rels),
        active_exempt_item=active_exempt[0] if active_exempt else None,
    )
    result["verdicts"]["OBS-2 修后（ACTIVE 项不进 collect、仍在豁免清单）"] = (
        "PASS" if active_exempt and "20261011/active.pdf" not in collected_rels else "FAIL"
    )
    assert active_exempt and "20261011/active.pdf" not in collected_rels

    # ── 5. apply 输出同源：三个数 ＋ note 也在 apply 报告里；ACTIVE 文件真没被删 ──
    active_before = sha256(inbox / "20261011" / "active.pdf")
    before_counts = counts(db)
    ap = run_cli(SERVER, env, "gc", "--apply", *common)
    after_counts = counts(db)
    body = ap["json"] or {}
    src_gone = {n: (not (inbox / "20261011" / n).exists())
                for n in ("noref_old.pdf", "noref_2d.pdf", "active.pdf")}
    active_after = sha256(inbox / "20261011" / "active.pdf")
    rec(
        "5 OBS-2 修后 · apply 输出（与 plan 同源）",
        rc=ap["rc"],
        mode=body.get("mode"),
        capacity_target_bytes=body.get("capacity_target_bytes"),
        collectable_bytes=body.get("collectable_bytes"),
        capacity_gap_bytes=body.get("capacity_gap_bytes"),
        note=body.get("note"),
        moved_files=body.get("moved_files"),
        moved=[m["src"] for m in body.get("moved", [])],
        trash_dir=body.get("trash_dir"),
        src_gone=src_gone,
        active_sha256_before=active_before,
        active_sha256_after=active_after,
        active_unchanged=(active_before == active_after),
        three_counts_before=before_counts,
        three_counts_after=after_counts,
        three_counts_unchanged=(before_counts == after_counts),
    )
    apply_ok = (
        body.get("mode") == "apply"
        and body.get("capacity_gap_bytes") == EXPECTED_GAP
        and body.get("capacity_target_bytes") == TARGET_BYTES
        and body.get("collectable_bytes") == 2 * SMALL_BYTES
        and body.get("note")
    )
    result["verdicts"]["OBS-2 修后（apply 输出含三个数 ＋ note）"] = "PASS" if apply_ok else "FAIL"
    result["verdicts"]["OBS-2 修后（缺口态 ACTIVE 文件未被删、sha256 不变）"] = (
        "PASS" if (active_before == active_after and src_gone["active.pdf"] is False) else "FAIL"
    )
    result["verdicts"]["红线（三数 jobs/job_pages/stamps 前后不变）"] = (
        "PASS" if before_counts == after_counts else "FAIL"
    )
    assert apply_ok, "apply 输出缺三个数/note"
    assert active_before == active_after and not src_gone["active.pdf"], "缺口场景竟动了 ACTIVE 文件"
    assert src_gone["noref_old.pdf"] and src_gone["noref_2d.pdf"], "可回收项未被真回收"
    assert before_counts == after_counts, "apply 动了库"

    # ── 6. 端点同源（临时 API 实例 :5198，独立 inbox / 库 / 端口）：缺口场景在**活端点**上同样可读 ──
    ep_root = SCRATCH / "endpoint"
    ep_inbox, ep_db, ep_reports = build_env(ep_root)
    ep_env = env_for(ep_inbox, ep_db, ep_reports)
    ep_env.update({
        "PORT": "5198",
        "FEICUI_INBOX_GC_CAPACITY_MAX_BYTES": str(MAX_BYTES),   # 单点可改常量：造「超闸」态
        "FEICUI_POOL_STATE": str(ep_root / "pool.state.json"),
        "FEICUI_WORKER_LOG_DIR": str(ep_root / "worker-logs"),
    })
    proc = subprocess.Popen([str(PY), "-m", "app.main"], cwd=str(SERVER), env=ep_env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ok = False
        for _ in range(80):
            try:
                with urllib.request.urlopen("http://127.0.0.1:5198/api/health", timeout=2) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                time.sleep(0.25)
        assert ok, "临时 API 5198 未就绪"

        def ep(method: str, path: str, body=None):
            data = json.dumps(body).encode() if body is not None else None
            hdrs = {"Content-Type": "application/json"} if data else {}
            req = urllib.request.Request("http://127.0.0.1:5198" + path, data=data, method=method, headers=hdrs)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode())

        ep_before_counts = counts(ep_db)
        st_sum, sum_body = ep("GET", "/api/jobs/inbox/summary")
        st_gc, gc_body = ep("POST", "/api/jobs/inbox/gc", {"apply": False})   # dry-run
        st_ap, ap_body = ep("POST", "/api/jobs/inbox/gc", {"apply": True})    # 真回收
        ep_after_counts = counts(ep_db)
        ep_active_before = sha256(ep_inbox / "20261011" / "active.pdf")
        rec(
            "6 端点同源 · 临时实例 :5198（GET summary / POST gc dry-run / POST gc apply）",
            summary_status=st_sum,
            summary_capacity_gate_triggered=sum_body.get("capacity_gate_triggered"),
            summary_capacity_target_bytes=sum_body.get("capacity_target_bytes"),
            summary_collectable_bytes=sum_body.get("collectable_bytes"),
            summary_capacity_gap_bytes=sum_body.get("capacity_gap_bytes"),
            summary_note=sum_body.get("note"),
            gc_dryrun_status=st_gc,
            gc_dryrun_mode=gc_body.get("mode"),
            gc_dryrun_capacity_gap_bytes=gc_body.get("capacity_gap_bytes"),
            gc_apply_status=st_ap,
            gc_apply_mode=ap_body.get("mode"),
            gc_apply_capacity_target_bytes=ap_body.get("capacity_target_bytes"),
            gc_apply_collectable_bytes=ap_body.get("collectable_bytes"),
            gc_apply_capacity_gap_bytes=ap_body.get("capacity_gap_bytes"),
            gc_apply_note=ap_body.get("note"),
            gc_apply_moved_files=ap_body.get("moved_files"),
            ep_active_unchanged=(ep_active_before == sha256(ep_inbox / "20261011" / "active.pdf")),
            ep_three_counts_before=ep_before_counts,
            ep_three_counts_after=ep_after_counts,
            ep_three_counts_unchanged=(ep_before_counts == ep_after_counts),
        )
        ep_ok = (
            st_sum == 200 and sum_body.get("capacity_gap_bytes") == EXPECTED_GAP and sum_body.get("note")
            and st_gc == 200 and gc_body.get("mode") == "dry-run" and gc_body.get("capacity_gap_bytes") == EXPECTED_GAP
            and st_ap == 200 and ap_body.get("mode") == "apply" and ap_body.get("capacity_gap_bytes") == EXPECTED_GAP
            and ap_body.get("note")
        )
        result["verdicts"]["OBS-2 修后（端点 summary/gc 与 CLI 同源：缺口 200 B ＋ note 可读）"] = (
            "PASS" if ep_ok else "FAIL"
        )
        result["verdicts"]["端点缺口语义（ACTIVE 文件未被删、三数不变）"] = (
            "PASS" if (ep_active_before == sha256(ep_inbox / "20261011" / "active.pdf")
                       and ep_before_counts == ep_after_counts) else "FAIL"
        )
        assert ep_ok, "临时端点未给缺口字段/note"
        assert ep_before_counts == ep_after_counts
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    result["verdicts"]["全部（上面无 FAIL ⇒ 两条 OBS 收口成立）"] = (
        "PASS" if "FAIL" not in result["verdicts"].values() else "FAIL"
    )
    total_ok = "FAIL" not in result["verdicts"].values()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    verdicts()
    print(f"\nraw → {OUT}")
    return 0 if total_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
