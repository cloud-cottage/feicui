#!/usr/bin/env python
"""**webp 退场 · 删除脚本（两段式；dry-run 默认）** —— Kong / feicui，2026-10-11。

## 口径（Kevin 2026-10-11 裁定）

> **「本地文件一律不再保存 webp，已经生产的可以删掉。」**

⇒ 印谱解析线的 `webp` 产物（旧 `output/faces/<book_key>/p<页4位>_<序2位>.webp` 与
`output/books/<目录键>/P<页>-C<列>-R<行>.webp`）**退场**；该行影像的**唯一产物 ＝ TIFF**
（`output/books/<目录键>/P<页>-C<列>-R<行>.tiff`，落 `stamps.img_path_tiff`）。

## 两段式 ＋ 安全闸（**本脚本的全部要害**）

* **默认 dry-run**：不给 `--apply` **一个字节都不动**，只打印「将删 / 豁免」两个计数与总字节；
* **逐行安全闸**：某行的 webp **只有**同时满足 ① `img_path_tiff` 非空 **且** ② 该 TIFF **文件在盘**
  才删该行的 webp。**未覆盖（无 `img_path_tiff`）/ 缺文件（TIFF 不在盘）一律不删**，并按原因分桶
  进清单——**绝不静默、绝不「差不多就删」**；
* **只动文件、不动库**：`stamps` 只读；**`img_path` 一字不改**（E6 的兼容回退靠它）；
  `jobs` / `job_pages` / `stamps` 三表行数与内容在 plan / apply 前后**逐字不变**；
* **不碰** `output/books/**` 的 TIFF（唯一产物，删了 E6 就全挂）；**不碰印章线**（它的
  `images/<sha256[:2]>/<sha256>.tiff` 与 xiai 影像库是跨工程契约，与本脚本无关）。

## 本脚本可删的两类 webp（**都从 DB 行派生**，不漫游磁盘乱删）

| 类 | 路径 | 派生方式 |
| --- | --- | --- |
| ① 旧印面面 | `output/faces/…/pNNNN_II.webp` | 行内 `img_path`（以 `.webp` 结尾且文件在盘） |
| ② 命名目录面 | `output/books/<目录键>/P<页>-C<列>-R<行>.webp` | 行内 `img_path_tiff` 的**同目录同名同胞** `.webp` |

盘上**未被任何行派生到**的 webp **不删**，只作为「盘面观测」如实计数（本单不动它们、不臆造归属）。

## 用法

    python -m app.retire_webp                # **默认 dry-run**：出清单 ＋ 落报告，绝不删
    python -m app.retire_webp --json         # dry-run，只吐 JSON（供脚本消费）
    python -m app.retire_webp --apply        # 真删（**只删过闸的那些**，逐条打印并记 sha256）

    from . import retire_webp
    retire_webp.scan(db_path, root)                 # 只读扫描（plan）
    retire_webp.run(get_settings(), apply=False)    # 干跑 ＋ 落报告
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:  # `python -m app.retire_webp`（server/ 为 cwd，app 是包）
    from . import db
    from .config import Settings, get_settings
except ImportError:  # 直接 `python server/app/retire_webp.py` 时的兜底
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import db  # type: ignore[no-redef]
    from app.config import Settings, get_settings  # type: ignore[no-redef]

__all__ = ["scan", "apply_plan", "run", "main", "REASONS", "WEBP_SUFFIX"]

WEBP_SUFFIX = ".webp"

#: 豁免（不删）的原因分桶 —— **按实际形态分列，不合并、不臆造**
REASONS = {
    "no_img_path_tiff": "该行 `img_path_tiff` 为空（未回填 ⇒ 无 TIFF 可依 ⇒ 不删）",
    "tiff_file_absent": "`img_path_tiff` 有值但该 TIFF **文件不在盘**（回填未落盘 ⇒ 不删）",
    "img_path_tiff_unsafe": "`img_path_tiff` 为绝对路径 / 越出 FEICUI_ROOT（拒绝 ⇒ 不删）",
}

#: 报告默认落点（证据入库：`ops/webp-retire/`）
REPORT_DIRNAME = ("ops", "webp-retire")


def _sha256_file(path: Path, *, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel_abs(root_abs: Path, rel: Any) -> tuple[Path | None, str | None]:
    """DB 内相对路径 → 绝对路径；**绝对路径 / 越界一律拒绝**（返回 `(None, 原因码)`）。

    与 `repository._resolve_img_rel`（E6）同一纪律：路径必须 ＝ `FEICUI_ROOT` ＋ 相对路径。
    """
    if rel is None or str(rel).strip() == "":
        return None, None
    raw = str(rel).strip()
    if os.path.isabs(raw):
        return None, "unsafe"
    p = (root_abs / raw).resolve()
    try:
        p.relative_to(root_abs)
    except ValueError:
        return None, "unsafe"
    return p, None


def scan(db_path: Path | str, root: Path | str) -> dict[str, Any]:
    """**只读**扫描：出「将删 / 豁免」两个清单（**不删任何文件、不写库**）。"""
    root_abs = Path(root).resolve()
    delete_files: list[dict[str, Any]] = []
    exempt_files: list[dict[str, Any]] = []
    exempt_rows: dict[str, int] = {k: 0 for k in REASONS}
    unsafe_paths: list[dict[str, Any]] = []
    delete_rows = 0
    exempt_row_count = 0

    with db.ro(db_path) as conn:
        rows = db.query_all(
            conn,
            """SELECT id, pdf_name, page, idx, img_path, img_path_tiff FROM stamps
                ORDER BY pdf_name, page, idx""",
        )
        total_rows = len(rows)

    for r in rows:
        legacy = r["img_path"]
        tiff_rel = r["img_path_tiff"]
        legacy_s = str(legacy).strip() if legacy is not None else ""
        tiff_s = str(tiff_rel).strip() if tiff_rel is not None else ""

        # ---- 本行的 webp 候选（① 旧印面面 ② 命名目录面同胞）----------------
        # **绝对路径 / 越界一律不当候选**（只记观测）；候选只可能是 FEICUI_ROOT 内的相对路径。
        cands: list[tuple[str, Path]] = []
        if legacy_s.lower().endswith(WEBP_SUFFIX):
            p, unsafe = _rel_abs(root_abs, legacy_s)
            if unsafe:
                unsafe_paths.append({"id": int(r["id"]), "column": "img_path", "value": legacy_s})
            elif p is not None:
                cands.append(("img_path", p))
        if tiff_s.lower().endswith(".tiff"):
            sibling_rel = tiff_s[: -len(".tiff")] + ".webp"
            p, unsafe = _rel_abs(root_abs, sibling_rel)
            if unsafe:
                unsafe_paths.append({"id": int(r["id"]), "column": "img_path_tiff(同胞)", "value": sibling_rel})
            elif p is not None:
                cands.append(("named", p))

        # 盘上真实存在的候选（不存在 ⇒ 无事可做，不进任何桶）
        on_disk = [c for c in cands if c[1].is_file()]

        # ---- 安全闸 ---------------------------------------------------------
        reason: str | None = None
        if not tiff_s:
            reason = "no_img_path_tiff"
        else:
            tiff_abs, unsafe = _rel_abs(root_abs, tiff_s)
            if unsafe or tiff_abs is None:
                reason = "img_path_tiff_unsafe"
            elif not tiff_abs.is_file():
                reason = "tiff_file_absent"

        if reason is None:
            # 过闸：删本行**所有盘上存在的** webp 候选
            for kind, p in on_disk:
                rel = str(p.relative_to(root_abs))
                delete_files.append(
                    {
                        "id": int(r["id"]),
                        "pdf_name": r["pdf_name"],
                        "page": int(r["page"]),
                        "idx": int(r["idx"]),
                        "which": kind,
                        "rel": rel,
                        "abs": str(p),
                        "bytes": int(p.stat().st_size),
                    }
                )
            if on_disk:
                delete_rows += 1
            continue

        # 豁免：进清单（**不删**）
        if on_disk:
            exempt_row_count += 1
            exempt_rows[reason] = exempt_rows.get(reason, 0) + 1
            for kind, p in on_disk:
                exempt_files.append(
                    {
                        "id": int(r["id"]),
                        "pdf_name": r["pdf_name"],
                        "page": int(r["page"]),
                        "idx": int(r["idx"]),
                        "which": kind,
                        "reason": reason,
                        "rel": str(p.relative_to(root_abs)),
                        "abs": str(p),
                        "bytes": int(p.stat().st_size),
                        "img_path_tiff": tiff_s or None,
                    }
                )

    del_bytes = sum(f["bytes"] for f in delete_files)
    exempt_bytes = sum(f["bytes"] for f in exempt_files)
    census = _disk_census(root_abs, delete_files, exempt_files)
    return {
        "generated_at": db.now_iso() if hasattr(db, "now_iso") else time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "db_path": str(db_path),
        "root": str(root_abs),
        "stamps_rows": total_rows,
        "delete": {
            "files": len(delete_files),
            "rows": delete_rows,
            "bytes": del_bytes,
            "by_tree": _tree_summary(delete_files),
            "list": delete_files,
        },
        "exempt": {
            "files": len(exempt_files),
            "rows": exempt_row_count,
            "bytes": exempt_bytes,
            "by_reason": {k: v for k, v in exempt_rows.items() if v},
            "by_reason_files": _count_by(exempt_files, "reason"),
            "by_tree": _tree_summary(exempt_files),
            "list": exempt_files,
        },
        "unsafe_paths": unsafe_paths,
        "disk_census": census,
    }


def _walk_webp(root_abs: Path, subdirs: tuple[str, ...]) -> list[Path]:
    """`output/**` 下的全部 `.webp`（**只读**，用于盘面观测）。

    只走 `output/`（印谱解析线的落点树）；**不碰印章线**（其 TIFF 在别的目录、且与 xiai 影像库
    是跨工程契约）。
    """
    out: list[Path] = []
    for sub in subdirs:
        base = root_abs / sub
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                if name.lower().endswith(WEBP_SUFFIX):
                    out.append(Path(dirpath) / name)
    return out


def _disk_census(
    root_abs: Path, delete_files: list[dict[str, Any]], exempt_files: list[dict[str, Any]]
) -> dict[str, Any]:
    """**盘面观测（只读）**：盘上到底有多少 webp、其中多少在本脚本处置面内。

    处置面 ＝ 由 `stamps` 行派生到的候选（`delete` ／ `exempt`）。**未被任何行派生到**的 webp
    （孤儿 / 另册产物）**本脚本一律不删**，只如实计数 ＋ 给样例路径（不臆造归属）。
    """
    subs = ("output",)
    on_disk = _walk_webp(root_abs, subs)
    known = {str(Path(f["abs"]).resolve()) for f in delete_files}
    known |= {str(Path(f["abs"]).resolve()) for f in exempt_files}
    orphans = [p for p in on_disk if str(p.resolve()) not in known]
    by_tree: dict[str, dict[str, int]] = {}
    for p in on_disk:
        tree = _tree_of(str(p.relative_to(root_abs)))
        slot = by_tree.setdefault(tree, {"on_disk": 0, "bytes": 0, "referenced": 0, "unreferenced": 0})
        slot["on_disk"] += 1
        slot["bytes"] += p.stat().st_size
        if str(p.resolve()) in known:
            slot["referenced"] += 1
        else:
            slot["unreferenced"] += 1
    return {
        "scope_dirs": list(subs),
        "webp_on_disk": len(on_disk),
        "webp_on_disk_bytes": sum(p.stat().st_size for p in on_disk),
        "webp_in_delete_list": len(delete_files),
        "webp_in_exempt_list": len(exempt_files),
        "webp_unreferenced": len(orphans),
        "webp_unreferenced_bytes": sum(p.stat().st_size for p in orphans),
        "by_tree": by_tree,
        "webp_unreferenced_sample": [
            str(p.relative_to(root_abs)) for p in sorted(orphans)[:20]
        ],
        "note": (
            "未被任何 stamps 行派生到的 webp **不属本脚本处置面**（安全闸要求有 TIFF 可依）；"
            "本单只报数、不删。"
        ),
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        out[str(it[key])] = out.get(str(it[key]), 0) + 1
    return out


#: 分树报数（派单口径：`output/faces/**` 与 `output/books/**` 两桶分列）
TREES = ("output/faces/", "output/books/")


def _tree_of(rel: str) -> str:
    """相对路径 → 树名（`faces` / `books` / `other`）。"""
    for t in TREES:
        if rel.startswith(t):
            return t.rstrip("/").split("/")[-1]
    return "other"


def _tree_summary(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """按树给 `{files, rows, bytes}`（一行为同一文件时可重复计数 ⇒ `rows` 用「行」去重计数）。"""
    out: dict[str, dict[str, Any]] = {}
    seen: dict[str, set] = {}
    for it in items:
        tree = _tree_of(it["rel"])
        slot = out.setdefault(tree, {"files": 0, "rows": 0, "bytes": 0})
        slot["files"] += 1
        slot["bytes"] += int(it["bytes"])
        seen.setdefault(tree, set()).add(int(it["id"]))
    for tree, ids in seen.items():
        out[tree]["rows"] = len(ids)
    return out


def apply_plan(plan: dict[str, Any], *, root: Path | str) -> dict[str, Any]:
    """**真删**（只删 `plan["delete"]` 里过闸的那些）。逐条记 `sha256` ＋ 字节（删前读）。

    红线：**只删清单里的 webp**；清单外一个字节都不动；**不写库**。
    """
    root_abs = Path(root).resolve()
    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    freed = 0
    for f in plan["delete"]["list"]:
        p = Path(f["abs"])
        # 二次闸（防 plan → apply 之间盘面变动）：仍在 root 内、仍是 `.webp`、仍存在
        try:
            p.relative_to(root_abs)
        except ValueError:
            failed.append({**f, "error": "越出 FEICUI_ROOT（apply 二次闸拒绝）"})
            continue
        if p.suffix.lower() != WEBP_SUFFIX:
            failed.append({**f, "error": "非 .webp（apply 二次闸拒绝）"})
            continue
        if not p.is_file():
            failed.append({**f, "error": "文件已不在盘（跳过）"})
            continue
        sha = _sha256_file(p)
        size = int(p.stat().st_size)
        try:
            os.remove(p)
        except OSError as exc:
            failed.append({**f, "error": f"删除失败：{exc}"})
            continue
        deleted.append({**f, "sha256": sha, "bytes": size})
        freed += size
    return {"deleted": deleted, "failed": failed, "freed_bytes": freed, "count": len(deleted)}


def run(
    st: Settings,
    *,
    apply: bool = False,
    report_dir: Path | None = None,
    db_path: Path | None = None,
    root: Path | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """**一段式入口**：扫描 → （可选）真删 → 落报告。返回报告 dict。

    `apply=False`（默认）⇒ **绝不改盘**；报告里 `dry_run=true`。
    """
    db_p = Path(db_path or st.db_path)
    root_p = Path(root or st.root)
    plan = scan(db_p, root_p)
    result: dict[str, Any] = {"deleted": [], "failed": [], "freed_bytes": 0, "count": 0}
    if apply:
        result = apply_plan(plan, root=root_p)

    report: dict[str, Any] = {
        "generated_at": plan["generated_at"],
        "tool": "app.retire_webp",
        "dry_run": (not apply),
        "db_path": plan["db_path"],
        "root": plan["root"],
        "stamps_rows": plan["stamps_rows"],
        "will_delete_files": plan["delete"]["files"],
        "will_delete_rows": plan["delete"]["rows"],
        "will_delete_bytes": plan["delete"]["bytes"],
        "will_delete_mb": round(plan["delete"]["bytes"] / 1024 / 1024, 2),
        "exempt_files": plan["exempt"]["files"],
        "exempt_rows": plan["exempt"]["rows"],
        "exempt_bytes": plan["exempt"]["bytes"],
        "exempt_mb": round(plan["exempt"]["bytes"] / 1024 / 1024, 2),
        "exempt_by_reason_rows": plan["exempt"]["by_reason"],
        "exempt_by_reason_files": plan["exempt"]["by_reason_files"],
        "delete_by_tree": plan["delete"]["by_tree"],
        "exempt_by_tree": plan["exempt"]["by_tree"],
        "deleted_files": result["count"],
        "deleted_bytes": result["freed_bytes"],
        "deleted_mb": round(result["freed_bytes"] / 1024 / 1024, 2),
        "deleted": result["deleted"],
        "delete_failures": result["failed"],
        "notes": [
            "安全闸：只有 `img_path_tiff` 非空**且**该 TIFF 文件在盘的行，其 webp 才被删。",
            "未覆盖（无 img_path_tiff）/ 缺文件（TIFF 不在盘）⇒ 一律不删，按原因分桶进 exempt 清单。",
            "只动文件、不动库：stamps 只读、`img_path` 一字不改；jobs / job_pages / stamps 三表逐字不变。",
            "不碰 output/books/** 的 TIFF、不碰印章线。",
            "盘上未被任何 stamps 行派生到的 webp 不属本脚本处置面（见 evidence 的盘面观测）。",
        ],
        "delete_list": plan["delete"]["list"],
        "unsafe_paths": plan.get("unsafe_paths", []),
    }
    report["disk_census"] = plan.get("disk_census", {})

    out_dir = Path(report_dir) if report_dir else (Path(st.root) / REPORT_DIRNAME[0] / REPORT_DIRNAME[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = "apply" if apply else "dryrun"
    json_path = out_dir / f"retire_webp_{suffix}_{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    # 豁免清单单独成件（逐行 JSONL，可能上万条；主报告只放计数 ＋ 分桶）
    exempt_path = out_dir / f"retire_webp_{suffix}_{stamp}_exempt.jsonl"
    with exempt_path.open("w", encoding="utf-8") as fh:
        for it in plan["exempt"]["list"]:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    report["report_paths"] = {"json": str(json_path), "exempt_jsonl": str(exempt_path)}

    if not quiet:
        print(f"== webp 退场（{'APPLY' if apply else 'DRY-RUN'}）==")
        print(f"库：{report['db_path']}  根：{report['root']}")
        print(f"stamps 行数：{report['stamps_rows']}")
        print(
            f"将删：{report['will_delete_files']} 件 / {report['will_delete_rows']} 行 / "
            f"{report['will_delete_bytes']} B（{report['will_delete_mb']} MB）"
        )
        for tree, s in sorted(report["delete_by_tree"].items()):
            print(f"    · 将删[{tree}]：{s['files']} 件 / {s['rows']} 行 / {s['bytes']} B")
        print(
            f"豁免：{report['exempt_files']} 件 / {report['exempt_rows']} 行 / "
            f"{report['exempt_bytes']} B（{report['exempt_mb']} MB）"
        )
        for tree, s in sorted(report["exempt_by_tree"].items()):
            print(f"    · 豁免[{tree}]：{s['files']} 件 / {s['rows']} 行 / {s['bytes']} B")
        for k, v in report["exempt_by_reason_rows"].items():
            print(f"    · {k}：{v} 行（{report['exempt_by_reason_files'].get(k, 0)} 件）—— {REASONS.get(k, '')}")
        print(f"释放总字节（dry-run 预估）：{report['will_delete_bytes']} B（{report['will_delete_mb']} MB）")
        cen = report.get("disk_census") or {}
        if cen:
            print(
                f"盘面观测：{'+'.join(cen.get('scope_dirs', []))} 下 webp {cen.get('webp_on_disk')} 件 / "
                f"{cen.get('webp_on_disk_bytes')} B；其中未被任何行派生到（不删）"
                f"{cen.get('webp_unreferenced')} 件 / {cen.get('webp_unreferenced_bytes')} B"
            )
            for tree, s in sorted((cen.get("by_tree") or {}).items()):
                print(
                    f"    · 盘上[{tree}]：{s['on_disk']} 件 / {s['bytes']} B"
                    f"（被行派生 {s['referenced']} / 未被派生 {s['unreferenced']}）"
                )
        if apply:
            print(f"已删：{report['deleted_files']} 件 / {report['deleted_bytes']} B（{report['deleted_mb']} MB）")
            if report["delete_failures"]:
                print(f"删除失败：{len(report['delete_failures'])} 件（见报告）")
        print(f"报告：{json_path}")
        print(f"豁免清单：{exempt_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.retire_webp",
        description=(
            "webp 退场 · 删除脚本（**两段式；默认 dry-run**）：逐行过安全闸"
            "（`img_path_tiff` 非空 且 TIFF 在盘）才删该行的 webp；未覆盖 / 缺文件一律不删进清单。\n"
            "只动文件、不动库；不碰 output/books/** 的 TIFF、不碰印章线。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "两段式：先 `python -m app.retire_webp` 读「将删 / 豁免」两数（绝不改盘），\n"
            "确认无误后再 `python -m app.retire_webp --apply` 真删。"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="retire",
        choices=["retire"],
        help="缺省动作（该脚本只有一个动作；保留位以便与 inbox_gc 同形）",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="只出清单（**默认**，绝不改盘）")
    group.add_argument("--apply", action="store_true", help="真删（**只删过闸的那些**）")
    parser.add_argument("--db", type=Path, default=None, help="覆盖库路径（默认取配置；只读）")
    parser.add_argument("--root", type=Path, default=None, help="覆盖 FEICUI_ROOT（默认取配置）")
    parser.add_argument("--report-dir", type=Path, default=None, help="覆盖报告落点（默认 ops/webp-retire/）")
    parser.add_argument("--json", action="store_true", help="只输出 JSON（供脚本消费；quiet）")
    args = parser.parse_args(argv)

    st = get_settings()
    report = run(
        st,
        apply=bool(args.apply),
        report_dir=args.report_dir,
        db_path=args.db,
        root=args.root,
        quiet=bool(args.json),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
