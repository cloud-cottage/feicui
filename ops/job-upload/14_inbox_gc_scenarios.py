#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox 清理策略（R41）· 场景复验（**全在临时目录 + 临时库**，不碰真 inbox / 真库）—— Kong / feicui。

覆盖派单要求里需要「造场景」的几项：

  ② **终态超保留期** ⇒ 进清单：DONE job 自 `updated_at`（回溯 90 天）起算 > 30 天 ⇒ `retention_expired`；
  ③ **trash 未满 T（7 天）⇒ 不硬删**；已满 T 的才进 `hard_delete`；
  ④ **容量闸**：`--max-bytes` 造场景 ⇒ 按「最久未引用」淘汰到 `target=ratio*M`，**ACTIVE 仍豁免**；
  ⑤ **`--apply` 真移入 trash**（源位置消失、trash 内有）且 **jobs/job_pages/stamps 三数不变**（**只动文件、
     不动库**）；同一 apply 语义再走 **`POST /api/jobs/inbox/gc {"apply":true}`**（临时 API 实例 :5197）复证。

跑法：
    cd /Users/kevin/bistro/xiai/feicui
    python3 ops/job-upload/14_inbox_gc_scenarios.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path("/Users/kevin/bistro/xiai/feicui")
SERVER = ROOT / "server"
PY = SERVER / ".venv" / "bin" / "python"
PROD_DB = Path("/Users/kevin/bistro/xiai/data/yinpu.db")
SCRATCH = Path("/Users/kevin/.hermes/profiles/zang/cache/scratch/inbox_gc_scenarios")
OUT = ROOT / "ops" / "job-upload" / "14_inbox_gc_scenarios_raw.json"

FILE_BYTES = 1000  # 每个 fixture 精确 1000 字节（便于容量闸算术确定性）
result: dict = {"steps": []}


def rec(name, **kw):
    result["steps"].append({"step": name, **kw})
    print(f"\n== {name} ==")
    for k, v in kw.items():
        print(f"   {k}: {json.dumps(v, ensure_ascii=False)}")


def make_pdf(path: Path, size: int) -> None:
    """造一个**真 `%PDF-` 头**、精确 `size` 字节的文件。"""
    head = b"%PDF-1.7\n% fixture for inbox_gc scenario\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = head + b"0" * max(0, size - len(head))
    path.write_bytes(body[:size] if len(body) > size else body)


def set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


def env_for(inbox: Path, db: Path, reports: Path) -> dict:
    e = dict(os.environ)
    e["FEICUI_INBOX_DIR"] = str(inbox)
    e["FEICUI_DB"] = str(db)
    e["FEICUI_INBOX_GC_REPORT_DIR"] = str(reports)
    e["FEICUI_SERVER_CONFIG"] = str(reports / "no_config.json")  # 不读仓内 server/config.json
    return e


def cli(inbox: Path, db: Path, reports: Path, *args: str) -> dict:
    cp = subprocess.run(
        [str(PY), "-m", "app.inbox_gc", "--json", *args],
        cwd=str(SERVER), env=env_for(inbox, db, reports), capture_output=True, text=True, timeout=180,
    )
    if cp.returncode not in (0, 1):
        raise RuntimeError(f"CLI 异常 rc={cp.returncode}: {cp.stderr[-800:]}")
    return json.loads(cp.stdout)


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


def build_env(root: Path) -> tuple[Path, Path, Path, dict]:
    """造临时 inbox（含 .trash）+ 临时库（prod 副本 + 场景 job）。"""
    if root.exists():
        shutil.rmtree(root)
    inbox = root / "inbox"
    reports = root / "reports"
    today = datetime.now().astimezone()
    d = inbox / "20261011"
    make_pdf(d / "active.pdf", FILE_BYTES)        # 被 ACTIVE job 引用
    make_pdf(d / "done_old.pdf", FILE_BYTES)      # 被 DONE job（updated_at 回溯 90 天）引用
    make_pdf(d / "noref_old.pdf", FILE_BYTES)     # 无引用，mtime 回溯 60 天
    make_pdf(d / "noref_2d.pdf", FILE_BYTES)      # 无引用，mtime 回溯 2 天
    make_pdf(d / "noref_1d.pdf", FILE_BYTES)      # 无引用，mtime 回溯 1 天
    set_mtime(d / "active.pdf", today)
    set_mtime(d / "done_old.pdf", today - timedelta(days=90))
    set_mtime(d / "noref_old.pdf", today - timedelta(days=60))
    set_mtime(d / "noref_2d.pdf", today - timedelta(days=2))
    set_mtime(d / "noref_1d.pdf", today - timedelta(days=1))
    # trash：一个「未满 T」（今天入）：一个「已满 T」（30 天前入）
    make_pdf(inbox / ".trash" / "20261011" / "trashed_fresh.pdf", FILE_BYTES)
    make_pdf(inbox / ".trash" / "20260901" / "trashed_old.pdf", FILE_BYTES)
    set_mtime(inbox / ".trash" / "20261011" / "trashed_fresh.pdf", today)
    set_mtime(inbox / ".trash" / "20260901" / "trashed_old.pdf", today - timedelta(days=30))

    db = root / "test.db"
    sqlite3.connect(PROD_DB).backup(sqlite3.connect(db))  # WAL 感知复制
    now_iso = today.replace(microsecond=0).isoformat()
    old_iso = (today - timedelta(days=90)).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(db)
    try:
        rows = [
            ("scn-active", str((d / "active.pdf").resolve()), "active.pdf", "QUEUED", now_iso),
            ("scn-done-old", str((d / "done_old.pdf").resolve()), "done_old.pdf", "DONE", old_iso),
        ]
        for jid, p, name, state, upd in rows:
            conn.execute(
                "INSERT INTO jobs(job_id, pdf_path, pdf_name, chunk_size, total_pages, state, rerun, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (jid, p, name, 8, 1, state, 0, upd, upd),
            )
        conn.commit()
    finally:
        conn.close()
    return inbox, db, reports, {"today": now_iso}


def main() -> int:
    root = SCRATCH
    inbox, db, reports, meta = build_env(root)
    d = inbox / "20261011"

    # ── S1：默认（保留期 30 天 / 容量闸 50 GiB 不触发）──
    p1 = cli(inbox, db, reports, "--dry-run")
    collect1 = {c["rel_path"]: c["reason"] for c in p1["collect"]}
    exempt1 = {e["rel_path"]: e["reason"] for e in p1["exempt"]}
    rec(
        "S1 默认 dry-run（终态超保留期）",
        usage=p1["usage"],
        collect=collect1,
        exempt=exempt1,
        capacity_gate=p1["capacity_gate_triggered"],
        trash_keep=[t["rel_path"] for t in p1["trash_keep"]],
        hard_delete=[h["rel_path"] for h in p1["hard_delete"]],
    )
    assert collect1.get("20261011/done_old.pdf") == "retention_expired", "终态超保留期未进待回收"
    assert collect1.get("20261011/noref_old.pdf") == "retention_expired", "无引用超保留期未进待回收"
    assert exempt1.get("20261011/active.pdf") == "active_job", "ACTIVE 未被豁免"
    assert exempt1.get("20261011/noref_1d.pdf") == "retention_not_expired"
    assert "20261011/trashed_fresh.pdf" not in [h["rel_path"] for h in p1["hard_delete"]], "trash 未满 T 竟要硬删"
    assert "20260901/trashed_old.pdf" in [h["rel_path"] for h in p1["hard_delete"]], "trash 已满 T 未进硬删"

    # 分开记两条证据（③ trash 未满 T 不硬删）
    rec(
        "S1b trash 两段式 T=7 天",
        trash_keep=[t["rel_path"] for t in p1["trash_keep"]],
        hard_delete=[h["rel_path"] for h in p1["hard_delete"]],
        trash_keep_reason=(p1["trash_keep"][0]["reason"] if p1["trash_keep"] else None),
    )

    # ── S2：容量闸（--max-bytes 3500 / ratio 0.8 ⇒ target 2800）──
    p2 = cli(inbox, db, reports, "--dry-run", "--max-bytes", "3500")
    collect2 = {c["rel_path"]: c["reason"] for c in p2["collect"]}
    rec(
        "S2 容量闸 --max-bytes 3500（按最久未引用淘汰到 target 2800）",
        usage=p2["usage"],
        target_bytes=p2["constants"]["capacity_target_bytes"],
        capacity_gate=p2["capacity_gate_triggered"],
        collect=collect2,
    )
    assert p2["capacity_gate_triggered"] is True
    assert collect2.get("20261011/noref_2d.pdf") == "capacity_pressure", "容量闸未按最久未引用淘汰"
    assert collect2.get("20261011/noref_1d.pdf") is None, "淘汰应停在 target，不应多淘汰更新者"
    assert collect2.get("20261011/active.pdf") is None, "ACTIVE 文件竟被容量闸淘汰"

    # ── S3：--apply（真移入 trash）＋ 三数不变 ──
    # 用 S2 同一容量闸场景（--max-bytes 3500）让 collect 集＝{done_old, noref_old（保留期）＋ noref_2d（容量闸）}，
    # 才能逐文件核对「3 个被回收项都真移入 trash 且源位置消失」（默认 50 GiB 下 noref_2d 未过保留期、不入 collect）。
    before_counts = counts(db)
    p3 = cli(inbox, db, reports, "--apply", "--max-bytes", "3500")
    after_counts = counts(db)
    moved = {m["src"]: m["trash_path"] for m in p3["moved"]}
    src_gone = {name: (not (d / name).exists()) for name in ("done_old.pdf", "noref_old.pdf", "noref_2d.pdf")}
    trash_has = {
        name: list((inbox / ".trash").rglob(name)) != []
        for name in ("done_old.pdf", "noref_old.pdf", "noref_2d.pdf")
    }
    keep_still = {name: (d / name).exists() for name in ("active.pdf", "noref_1d.pdf")}
    rec(
        "S3 --apply（两段式：move ⇒ .trash/<today>/）",
        mode=p3["mode"],
        moved_files=p3["moved_files"],
        trash_dir=p3["trash_dir"],
        hard_deleted_files=p3["hard_deleted_files"],
        src_gone=src_gone,
        trash_has=trash_has,
        keep_still_present=keep_still,
        three_counts_before=before_counts,
        three_counts_after=after_counts,
        three_counts_unchanged=(before_counts == after_counts),
    )
    assert all(src_gone.values()) and all(trash_has.values())
    assert all(keep_still.values()), "豁免文件被误动"
    assert before_counts == after_counts, "apply 动了库（三数变了）"

    # apply 后再 dry-run：移入 trash 的文件应「宽限期未到 ⇒ 不硬删」
    p3b = cli(inbox, db, reports, "--dry-run")
    rec(
        "S3b apply 后再 dry-run（新入 trash 未满 T ⇒ 不硬删）",
        collect_files=p3b["collect_files"],
        trash_keep=[t["rel_path"] for t in p3b["trash_keep"]],
        hard_delete=[h["rel_path"] for h in p3b["hard_delete"]],
    )
    assert all("done_old" not in h["rel_path"] and "noref_2d" not in h["rel_path"] for h in p3b["hard_delete"])

    # ── S4：端点 apply=true（临时 API 实例 :5197，独立 inbox/库/端口）──
    ep_root = root / "endpoint"
    ep_inbox, ep_db, ep_reports, _ = build_env(ep_root)
    ep_d = ep_inbox / "20261011"
    ep_env = env_for(ep_inbox, ep_db, ep_reports)
    ep_env.update({"PORT": "5197", "FEICUI_POOL_STATE": str(ep_root / "pool.state.json"),
                   "FEICUI_WORKER_LOG_DIR": str(ep_root / "worker-logs")})
    proc = subprocess.Popen([str(PY), "-m", "app.main"], cwd=str(SERVER), env=ep_env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ok = False
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:5197/api/health", timeout=2) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                time.sleep(0.25)
        assert ok, "临时 API 5197 未就绪"
        ep_before = counts(ep_db)
        req = urllib.request.Request("http://127.0.0.1:5197/api/jobs/inbox/gc",
                                     data=json.dumps({"apply": True}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
        ep_after = counts(ep_db)
        rec(
            "S4 POST /api/jobs/inbox/gc {\"apply\":true}（临时实例 :5197）",
            status=resp.status,
            mode=body["mode"],
            moved_files=body["moved_files"],
            trash_dir=body["trash_dir"],
            src_gone=(not (ep_d / "done_old.pdf").exists()),
            trash_has=list((ep_inbox / ".trash").rglob("done_old.pdf")) != [],
            keep_present=(ep_d / "active.pdf").exists(),
            three_counts_before=ep_before,
            three_counts_after=ep_after,
            unchanged=(ep_before == ep_after),
        )
        assert body["mode"] == "apply" and body["moved_files"] >= 1
        assert not (ep_d / "done_old.pdf").exists()
        assert (ep_d / "active.pdf").exists(), "端点 apply 误动 ACTIVE 文件"
        assert ep_before == ep_after
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nraw → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
