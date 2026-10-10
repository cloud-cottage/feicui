"""inbox 清理策略（R41 结案）—— **扫描 / 计划 / 两段式回收** —— Kong / feicui。

口径真源：`docs/inbox-gc-draft-v0.1.md`（Zang 2026-10-11 起草；Kevin 2026-10-11 裁定「制定清理策略」）。
默认值**照 draft**，且**每一个都是单点可改常量**（`app/config.py` 的 `INBOX_GC_*`，可 env / server/config.json
覆盖，与既有 `upload_max_bytes` 同风格）。

## 铁律（结构性，**不可配置**）

1. **引用豁免**：被**活跃 job**（`QUEUED/RUNNING/PAUSED`）引用的文件**永不回收**——池 / worker 直接
   `pymupdf.open(pdf_path)`，删了就是运行中作业崩。
2. **永不自动删**：系统**没有任何自动删除路径**；API 启动扫描（`startup_scan`）**只 dry-run 记录/告警**，
   真删**只能由人触发**（CLI `--apply` 或 `POST /api/jobs/inbox/gc {"apply": true}`）。

## 保留与淘汰（三个可配数值）

* R1 **保留期**：终态 job（`DONE/FAILED_PARTIAL`）引用的文件自该 job `updated_at` 起保留 N 天；
  **无 job 引用**的文件按文件 `mtime` 起算同样 N 天。
* R2 **容量闸**：inbox 总量超 M 时，按「**最久未引用**」淘汰到 `ratio * M`（ACTIVE 豁免仍优先）。
* R3 **两段式销毁**：先**移入 `inbox/.trash/<yyyymmdd>/`**（可回滚），在 trash 再留 T 天才**硬删**。

## 只动文件、不动库

本模块**只读写磁盘上的 inbox 文件**；对 `jobs` 表**只读**（解析引用），**零 DB 写**——任何 apply 前后
`jobs` / `job_pages` / `stamps` 三数**逐字不变**。

用法：

    python -m app.inbox_gc --dry-run      # 只列清单（**默认**）
    python -m app.inbox_gc --apply        # 真移入 .trash/（+ 硬删 trash 过期项）

    from . import inbox_gc
    inbox_gc.run(get_settings())                 # 默认 dry-run，落报告
    inbox_gc.startup_scan(get_settings())        # API 启动扫描（**只 dry-run**）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import (
    INBOX_GC_CAPACITY_MAX_BYTES_DEFAULT,
    INBOX_GC_CAPACITY_TARGET_RATIO_DEFAULT,
    INBOX_GC_RETENTION_DAYS_DEFAULT,
    INBOX_GC_STARTUP_SCAN_DEFAULT,
    INBOX_GC_TRASH_DIRNAME,
    INBOX_GC_TRASH_RETENTION_DAYS_DEFAULT,
    Settings,
    get_settings,
)

log = logging.getLogger("feicui.api.inbox_gc")

#: 活跃态（**永久豁免**；删了运行中作业会崩——见模块文档铁律 ①）
ACTIVE_STATES = ("QUEUED", "RUNNING", "PAUSED")
#: 终态（按 `updated_at` 起算保留期）
TERMINAL_STATES = ("DONE", "FAILED_PARTIAL")

#: trash 子目录名（`inbox/.trash/`）与报告文件名前缀
TRASH_DIRNAME = INBOX_GC_TRASH_DIRNAME
REPORT_PREFIX = "inbox_gc_"

# ---- 豁免 / 淘汰原因（**结构化枚举**，不在别处硬编码字符串）----
REASON_ACTIVE = "active_job"                    # 被活跃 job 引用 ⇒ 永久豁免
REASON_RETENTION = "retention_not_expired"      # 保留期未到 ⇒ 豁免
REASON_TRASH_KEEP = "trash_retention_not_expired"  # trash 宽限期未到 ⇒ 暂留
REASON_COLLECT_RETENTION = "retention_expired"  # 保留期已过 ⇒ 待回收
REASON_COLLECT_CAPACITY = "capacity_pressure"   # 容量闸 ⇒ 按最久未引用淘汰


# --------------------------------------------------------------------------- 时间
def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_dt(value: Any) -> datetime | None:
    """解析 ISO8601（可带时区）字符串；不可解析 ⇒ None（不臆造时间）。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:  # 库内应恒带偏移（`db.now_iso`）；无偏移时按本机时区补
        dt = dt.replace(tzinfo=_now().tzinfo)
    return dt


def _mtime_dt(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone()


def _day_stamp(now: datetime | None = None) -> str:
    return (now or _now()).strftime("%Y%m%d")


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- 扫描
def scan_inbox(inbox_dir: Path) -> list[dict[str, Any]]:
    """扫 inbox 内的**普通文件**（**排除 `.trash/`**），返回 `{path, rel, bytes, mtime}` 列表。

    只读、不写、不跟隐藏目录（`.trash` 是策略自己的回收站，单独扫；其它 `.*` 目录一律跳过）。
    """
    inbox_dir = Path(inbox_dir)
    out: list[dict[str, Any]] = []
    if not inbox_dir.is_dir():
        return out
    for p in sorted(inbox_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(inbox_dir)
        if rel.parts and rel.parts[0] == TRASH_DIRNAME:
            continue  # `.trash/` 单独处理
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue  # 其它隐藏目录跳过
        try:
            size = p.stat().st_size
            mtime = _mtime_dt(p)
        except OSError:
            continue
        out.append({"path": p, "rel": rel.as_posix(), "bytes": int(size), "mtime": mtime})
    return out


def scan_trash(inbox_dir: Path) -> list[dict[str, Any]]:
    """扫 `inbox/.trash/` 内的普通文件（两段式的第二段：宽限期到 ⇒ 硬删）。"""
    trash_dir = Path(inbox_dir) / TRASH_DIRNAME
    out: list[dict[str, Any]] = []
    if not trash_dir.is_dir():
        return out
    for p in sorted(trash_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(trash_dir)
        try:
            size = p.stat().st_size
            mtime = _mtime_dt(p)
        except OSError:
            continue
        out.append({"path": p, "rel": rel.as_posix(), "bytes": int(size), "mtime": mtime})
    return out


# --------------------------------------------------------------------------- 引用解析
def job_references(db_path: Path | str) -> dict[str, list[dict[str, Any]]]:
    """从 `jobs` 表解析「文件 → 引用该文件的 job 列表」（**只读**；`pdf_path` 按绝对路径归一）。

    返回 `{规范化绝对路径: [{job_id, state, updated_at, pdf_path}, ...]}`。
    库不存在 / 无 `jobs` 表 ⇒ 返回 `{}`（策略对「引用存在但文件不在」的行不做处理，只按盘上文件算）。
    """
    path = Path(db_path)
    refs: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return refs
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return refs
    try:
        rows = conn.execute(
            "SELECT job_id, pdf_path, state, updated_at FROM jobs WHERE pdf_path IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return refs
    finally:
        conn.close()
    for r in rows:
        raw = str(r["pdf_path"])
        try:
            key = str(Path(raw).expanduser().resolve())
        except (OSError, RuntimeError):
            key = str(Path(raw).expanduser())
        refs.setdefault(key, []).append(
            {
                "job_id": r["job_id"],
                "state": r["state"],
                "updated_at": r["updated_at"],
                "pdf_path": raw,
            }
        )
    return refs


# --------------------------------------------------------------------------- 计划
def build_plan(
    st: Settings,
    *,
    now: datetime | None = None,
    inbox_dir: Path | None = None,
    db_path: Path | None = None,
    retention_days: int | None = None,
    capacity_max_bytes: int | None = None,
    capacity_target_ratio: float | None = None,
    trash_retention_days: int | None = None,
) -> dict[str, Any]:
    """构建清理计划（**纯计算 + 只读扫描**，绝不改盘、不改库）。

    返回清单含：用量、将回收项（＋体积）、可回收总量、**豁免清单及原因**、trash 硬删清单。
    """
    now = now or _now()
    inbox_dir = Path(inbox_dir if inbox_dir is not None else st.inbox_dir)
    db_path = Path(db_path if db_path is not None else st.db_path)
    retention_days = (
        int(retention_days) if retention_days is not None else int(st.inbox_gc_retention_days)
    )
    capacity_max_bytes = (
        int(capacity_max_bytes) if capacity_max_bytes is not None else int(st.inbox_gc_capacity_max_bytes)
    )
    capacity_target_ratio = (
        float(capacity_target_ratio) if capacity_target_ratio is not None else float(st.inbox_gc_capacity_target_ratio)
    )
    trash_retention_days = (
        int(trash_retention_days) if trash_retention_days is not None else int(st.inbox_gc_trash_retention_days)
    )

    refs = job_references(db_path)
    files = scan_inbox(inbox_dir)

    collect: list[dict[str, Any]] = []
    exempt: list[dict[str, Any]] = []
    total_bytes = 0

    for f in files:
        total_bytes += f["bytes"]
        key = str(f["path"].resolve())
        referencing = refs.get(key, [])
        active = [j for j in referencing if j["state"] in ACTIVE_STATES]
        terminal = [j for j in referencing if j["state"] in TERMINAL_STATES]

        item = {"rel_path": f["rel"], "abs_path": str(f["path"]), "bytes": f["bytes"]}

        if active:
            # 铁律 ①：活跃 job 引用 ⇒ 永久豁免（**连容量闸也不动它**）
            exempt.append(
                {
                    **item,
                    "reason": REASON_ACTIVE,
                    "job_id": active[0]["job_id"],
                    "state": active[0]["state"],
                    "referenced_by": [j["job_id"] for j in active],
                    "note": "活跃 job（QUEUED/RUNNING/PAUSED）引用 ⇒ 永久豁免",
                }
            )
            continue

        if terminal:
            last_ref = max((_parse_dt(j["updated_at"]) or f["mtime"]) for j in terminal)
            source = "job.updated_at"
            job_id = max(terminal, key=lambda j: (_parse_dt(j["updated_at"]) or f["mtime"]))["job_id"]
        else:
            last_ref = f["mtime"]
            source = "file.mtime"
            job_id = None

        expires_at = last_ref + timedelta(days=retention_days)
        item = {
            **item,
            "last_referenced_at": last_ref.isoformat(),
            "reference_source": source,
            "job_id": job_id,
            "expires_at": expires_at.isoformat(),
            "age_days": round((now - last_ref).total_seconds() / 86400.0, 3),
        }
        if now >= expires_at:
            collect.append({**item, "reason": REASON_COLLECT_RETENTION})
        else:
            exempt.append(
                {
                    **item,
                    "reason": REASON_RETENTION,
                    "note": f"保留期未到（{source} + {retention_days} 天）",
                }
            )

    # ---- R2 容量闸：总量 > M ⇒ 按「最久未引用」淘汰到 ratio*M（ACTIVE 仍豁免）----
    capacity_target_bytes = int(capacity_max_bytes * capacity_target_ratio)
    already = sum(c["bytes"] for c in collect)
    projected = total_bytes - already
    capacity_hit = total_bytes > capacity_max_bytes
    if capacity_hit:
        candidates = [e for e in exempt if e["reason"] == REASON_RETENTION]
        candidates.sort(key=lambda e: (e.get("last_referenced_at") or "", e["rel_path"]))
        for e in candidates:
            if projected <= capacity_target_bytes:
                break
            collect.append({**e, "reason": REASON_COLLECT_CAPACITY})
            exempt.remove(e)
            projected -= e["bytes"]

    # ---- R3 第二段：trash 内宽限期到 ⇒ 硬删；未到 ⇒ 暂留 ----
    hard_delete: list[dict[str, Any]] = []
    trash_keep: list[dict[str, Any]] = []
    trash_files = scan_trash(inbox_dir)
    for t in trash_files:
        item = {"rel_path": t["rel"], "abs_path": str(t["path"]), "bytes": t["bytes"]}
        expires = t["mtime"] + timedelta(days=trash_retention_days)
        if now >= expires:
            hard_delete.append(
                {
                    **item,
                    "reason": REASON_TRASH_KEEP.replace("not_expired", "expired"),
                    "moved_at": t["mtime"].isoformat(),
                    "age_days": round((now - t["mtime"]).total_seconds() / 86400.0, 3),
                }
            )
        else:
            trash_keep.append(
                {
                    **item,
                    "reason": REASON_TRASH_KEEP,
                    "moved_at": t["mtime"].isoformat(),
                    "expires_at": expires.isoformat(),
                    "note": f"trash 宽限期未到（{trash_retention_days} 天）",
                }
            )

    collect_bytes = sum(c["bytes"] for c in collect)
    return {
        "mode": "dry-run",
        "generated_at": now.isoformat(),
        "inbox_dir": str(inbox_dir),
        "db_path": str(db_path),
        "constants": {
            "retention_days": retention_days,
            "capacity_max_bytes": capacity_max_bytes,
            "capacity_target_ratio": capacity_target_ratio,
            "capacity_target_bytes": capacity_target_bytes,
            "trash_retention_days": trash_retention_days,
            "trash_dirname": TRASH_DIRNAME,
        },
        "usage": {"files": len(files), "bytes": total_bytes},
        "trash_usage": {"files": len(trash_files), "bytes": sum(t["bytes"] for t in trash_files)},
        "capacity_gate_triggered": capacity_hit,
        "collect": sorted(collect, key=lambda c: (c.get("last_referenced_at") or "", c["rel_path"])),
        "collect_files": len(collect),
        "collect_bytes": collect_bytes,
        "exempt": sorted(exempt, key=lambda e: e["rel_path"]),
        "exempt_files": len(exempt),
        "exempt_bytes": sum(e["bytes"] for e in exempt),
        "trash_keep": trash_keep,
        "hard_delete": hard_delete,
        "hard_delete_files": len(hard_delete),
        "hard_delete_bytes": sum(h["bytes"] for h in hard_delete),
    }


# --------------------------------------------------------------------------- 执行（两段式）
def _unique_dest(dest_dir: Path, name: str) -> Path:
    """trash 内目标名去重（同名不覆盖；加 `-2`/`-3`… 后缀）。"""
    base = Path(name).stem
    suffix = Path(name).suffix
    dest = dest_dir / name
    idx = 2
    while dest.exists():
        dest = dest_dir / f"{base}-{idx}{suffix}"
        idx += 1
    return dest


def apply_plan(st: Settings, plan: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """**两段式**执行：① 将回收项 move 进 `inbox/.trash/<yyyymmdd>/`；② 硬删 trash 过期项。

    **只动文件、不动库**（对 `jobs`/`job_pages`/`stamps` 零写）。任何单文件失败进 `errors`，
    不中断其余项（best effort）。
    """
    now = now or _now()
    trash_root = Path(plan["inbox_dir"]) / TRASH_DIRNAME
    day = _day_stamp(now)

    moved: list[dict[str, Any]] = []
    moved_bytes = 0
    errors: list[dict[str, Any]] = []

    for item in plan["collect"]:
        src = Path(item["abs_path"])
        try:
            dest_dir = trash_root / day
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = _unique_dest(dest_dir, src.name)
            shutil.move(str(src), str(dest))
            # 两段式宽限期从「入 trash 那一刻」起算（AC-74 / §3.20.3 R3）：
            # shutil.move 保留原 mtime ⇒ 被回收的旧 PDF（已过保留期，mtime 也许是几天前乃至几个月前）
            # 会带着旧 mtime 落进 .trash，scan_trash 按 mtime 算便当它「早已过期」而立即硬删，
            # 回滚窗口归零（两段式形同虚设）。故入 trash 时把 mtime 钉为当前时刻，宽限期 T 天自此刻起算。
            _ts = now.timestamp()
            os.utime(dest, (_ts, _ts))
        except OSError as exc:
            errors.append({"op": "move", "src": str(src), "error": f"{type(exc).__name__}: {exc}"})
            continue
        moved.append({"src": str(src), "trash_path": str(dest), "bytes": item["bytes"], "reason": item["reason"]})
        moved_bytes += item["bytes"]

    hard_deleted: list[dict[str, Any]] = []
    hard_deleted_bytes = 0
    for item in plan["hard_delete"]:
        src = Path(item["abs_path"])
        try:
            src.unlink()
        except OSError as exc:
            errors.append({"op": "hard_delete", "src": str(src), "error": f"{type(exc).__name__}: {exc}"})
            continue
        hard_deleted.append({"path": str(src), "bytes": item["bytes"]})
        hard_deleted_bytes += item["bytes"]

    return {
        "mode": "apply",
        "trash_dir": str(trash_root / day),
        "moved": moved,
        "moved_files": len(moved),
        "moved_bytes": moved_bytes,
        "hard_deleted": hard_deleted,
        "hard_deleted_files": len(hard_deleted),
        "hard_deleted_bytes": hard_deleted_bytes,
        "errors": errors,
    }


# --------------------------------------------------------------------------- 报告 + 编排
def _report_path(st: Settings, now: datetime) -> Path:
    d = Path(st.inbox_gc_report_dir)
    ts = now.strftime("%Y%m%d-%H%M%S")
    path = d / f"{REPORT_PREFIX}{ts}.json"
    if path.exists():  # 同秒多次 ⇒ 补微秒，绝不覆盖既有报告
        path = d / f"{REPORT_PREFIX}{now.strftime('%Y%m%d-%H%M%S-%f')}.json"
    return path


def _write_report(st: Settings, report: dict[str, Any], now: datetime) -> str:
    path = _report_path(st, now)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # 落报告失败不得挡住主链路
        log.warning("inbox_gc 报告落盘失败（不影响计划/执行结果）：%r", exc)
        return ""
    return str(path)


def run(
    st: Settings,
    *,
    apply: bool = False,
    now: datetime | None = None,
    write_report: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """一次 plan（＋可选 apply）：**默认 dry-run**；落报告到 `ops/job-upload/inbox_gc_<ts>.json`。"""
    now = now or _now()
    plan = build_plan(st, now=now, **overrides)
    report = plan
    if apply:
        applied = apply_plan(st, plan, now=now)
        # apply 后重扫用量，读数如实反映「现在盘上还有什么」
        report = {
            **plan,
            "mode": "apply",
            **applied,
            "usage_after": {
                "files": plan["usage"]["files"] - applied["moved_files"],
                "bytes": plan["usage"]["bytes"] - applied["moved_bytes"],
            },
        }
    if write_report:
        report = {**report, "report_path": _write_report(st, report, now)}
    return report


def startup_scan(st: Settings) -> dict[str, Any] | None:
    """API 启动扫描：**只 dry-run 记录/告警**，绝不删任何东西（铁律 ②）。"""
    if not st.inbox_gc_startup_scan:
        log.info("inbox 启动扫描：已关闭（FEICUI_INBOX_GC_STARTUP_SCAN=0）⇒ 跳过（未删任何文件）")
        return None
    report = run(st, apply=False)
    usage = report["usage"]
    log.info(
        "inbox 启动扫描（**只 dry-run，未删任何文件**）：文件 %d / %.2f MiB；"
        "将回收 %d（%.2f MiB）；豁免 %d；容量闸=%s；报告 %s",
        usage["files"],
        usage["bytes"] / 1048576,
        report["collect_files"],
        report["collect_bytes"] / 1048576,
        report["exempt_files"],
        report["capacity_gate_triggered"],
        report.get("report_path") or "（未落盘）",
    )
    if report["collect_files"]:
        log.warning(
            "inbox 启动告警：有 %d 个文件已过保留期/触容量闸（合计 %.2f MiB）待回收——"
            "**系统不会自动删**，请人工用 CLI `python -m app.inbox_gc --apply` 或 "
            "`POST /api/jobs/inbox/gc {\"apply\":true}` 触发",
            report["collect_files"],
            report["collect_bytes"] / 1048576,
        )
    return report


# --------------------------------------------------------------------------- CLI
def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    if n < 1024 ** 3:
        return f"{n / 1048576:.2f} MiB"
    return f"{n / 1073741824:.2f} GiB"


def _print_human(report: dict[str, Any]) -> None:
    c = report["constants"]
    print(f"inbox 清理计划（mode={report['mode']}）  {report['generated_at']}")
    print(f"  inbox      : {report['inbox_dir']}")
    print(f"  常量       : 保留期 {c['retention_days']} 天 | 容量闸 {_fmt_bytes(c['capacity_max_bytes'])}"
          f" → {_fmt_bytes(c['capacity_target_bytes'])}（ratio {c['capacity_target_ratio']}）"
          f" | trash 宽限 {c['trash_retention_days']} 天")
    print(f"  用量       : {report['usage']['files']} 文件 / {_fmt_bytes(report['usage']['bytes'])}"
          f"  | trash {report['trash_usage']['files']} 文件 / {_fmt_bytes(report['trash_usage']['bytes'])}")
    print(f"  将回收     : {report['collect_files']} 文件 / {_fmt_bytes(report['collect_bytes'])}"
          f"  | 容量闸触发={report['capacity_gate_triggered']}")
    for it in report["collect"]:
        print(f"      - [{it['reason']}] {it['rel_path']}  {_fmt_bytes(it['bytes'])}"
              f"  来源={it.get('reference_source', '—')}  末次引用={it.get('last_referenced_at', '—')}")
    print(f"  豁免       : {report['exempt_files']} 文件 / {_fmt_bytes(report['exempt_bytes'])}")
    for it in report["exempt"]:
        jid = f"  job={it.get('job_id')}({it.get('state', '')})" if it.get("job_id") else ""
        print(f"      - [{it['reason']}] {it['rel_path']}  {_fmt_bytes(it['bytes'])}{jid}")
    if report["trash_keep"]:
        print(f"  trash 暂留 : {len(report['trash_keep'])} 文件")
    if report["hard_delete_files"]:
        print(f"  trash 硬删 : {report['hard_delete_files']} 文件 / {_fmt_bytes(report['hard_delete_bytes'])}")
    if report["mode"] == "apply":
        print(f"  已移入 trash: {report['moved_files']} 文件 / {_fmt_bytes(report['moved_bytes'])} ⇒ {report['trash_dir']}")
        if report["hard_deleted_files"]:
            print(f"  已硬删     : {report['hard_deleted_files']} 文件 / {_fmt_bytes(report['hard_deleted_bytes'])}")
    if report.get("errors"):
        print(f"  ⚠ 错误     : {len(report['errors'])} 条（详见报告）")
    print(f"  报告       : {report.get('report_path') or '（未落盘）'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.inbox_gc",
        description="inbox 清理策略（R41）：扫描 + 出清单（**默认 dry-run**）/ 两段式回收。",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="只列清单（**默认**，绝不改盘）")
    group.add_argument("--apply", action="store_true", help="真移入 inbox/.trash/（+ 硬删 trash 过期项）")
    parser.add_argument("--inbox", type=Path, default=None, help="覆盖 inbox 根（默认取配置）")
    parser.add_argument("--db", type=Path, default=None, help="覆盖库路径（默认取配置；只读解析引用）")
    parser.add_argument("--retention-days", type=int, default=None, help="覆盖保留期（天）")
    parser.add_argument("--max-bytes", type=int, default=None, help="覆盖容量闸上限 M（字节）")
    parser.add_argument("--target-ratio", type=float, default=None, help="覆盖容量闸目标比（默认 0.8）")
    parser.add_argument("--trash-days", type=int, default=None, help="覆盖 trash 宽限期 T（天）")
    parser.add_argument("--report-dir", type=Path, default=None, help="覆盖报告落点目录")
    parser.add_argument("--no-report", action="store_true", help="不落报告文件")
    parser.add_argument("--json", action="store_true", help="只输出 JSON（供脚本消费）")
    args = parser.parse_args(argv)

    st = get_settings()
    if args.report_dir is not None:
        st = type(st)(**{**st.__dict__, "inbox_gc_report_dir": args.report_dir.expanduser().resolve()})

    overrides: dict[str, Any] = {}
    if args.inbox is not None:
        overrides["inbox_dir"] = args.inbox.expanduser().resolve()
    if args.db is not None:
        overrides["db_path"] = args.db.expanduser().resolve()
    if args.retention_days is not None:
        overrides["retention_days"] = args.retention_days
    if args.max_bytes is not None:
        overrides["capacity_max_bytes"] = args.max_bytes
    if args.target_ratio is not None:
        overrides["capacity_target_ratio"] = args.target_ratio
    if args.trash_days is not None:
        overrides["trash_retention_days"] = args.trash_days

    report = run(st, apply=bool(args.apply), write_report=not args.no_report, **overrides)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return 1 if report.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
