#!/usr/bin/env python
"""PDF 资料登记扫描 CLI —— Kong / output 四总目录落地单 · 2026-10-14。

口径真源：`docs/output-layout-v0.1.md`。核心逻辑全在 `server/app/pdf_registry.py`
（本脚本只做「走盘 ＋ sha256 ＋ PyMuPDF 探测 ＋ 编排」，**不写 yinpu.db、不建 job、零联网**）。

用法（图像栈只在 `feicui/venv` ⇒ 须用 `./venv/bin/python` 跑）：
    cd /Users/kevin/bistro/xiai/feicui
    ./venv/bin/python ops/pdf-registry/scan_pdf_registry.py                 # 扫 pdf_source_dir（默认【1】）
    ./venv/bin/python ops/pdf-registry/scan_pdf_registry.py --root <DIR>    # 追加扫描根（可多次）
    ./venv/bin/python ops/pdf-registry/scan_pdf_registry.py --register-missing '秦汉印典 …' [--notes …]
    ./venv/bin/python ops/pdf-registry/scan_pdf_registry.py --include-small # 不跳过 <100KB 小件

幂等口径（**by sha256**，真源＝`server/app/pdf_registry.py` 模块注释）：
    * 新文件 ⇒ `insert`；同路径同内容 ⇒ `noop`（重跑零写入）；
    * 同路径内容变 ⇒ `update`；**搬移（sha 不变、旧路径已不在盘）⇒ `moved`（原行原地更新 rel_path）**；
    * 同内容多副本（如 tmp.pdf ≡ 黄牧甫印谱）⇒ `duplicate`（只登记先到先得一行，其余不入册）。
探测：页数＝PyMuPDF；page_mm＝众数页宽高（毫米）；scan_dpi＝内嵌图像像素/页面盒估算（样本页中位数）。
探测失败（无 pymupdf/加密 PDF）⇒ 派生值如实留 NULL，**不编造**；sha/size 始终真实。
小于 100_000 字节的 *.pdf 一律跳过（拖曳测试/probe 假件），`--include-small` 解除。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from server.app.pdf_registry import (  # noqa: E402
    DB_PATH,
    DYNASTY_OPTIONS,
    apply_scan_row,
    ensure_db,
    pdf_source_dir,
    register_missing,
)

MIN_BYTES = 100_000


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_pdf(path: Path) -> dict:
    """页数 / page_mm（众数页）/ scan_dpi（样本页中位数）。失败 ⇒ 全 None（不编造）。"""
    out: dict = {"page_count": None, "page_mm": None, "scan_dpi": None}
    try:
        import pymupdf  # feicui venv 内已装（1.28.x）；import 失败 ⇒ 原样返回 NULL 值
    except Exception:
        return out
    try:
        with pymupdf.open(str(path)) as doc:
            out["page_count"] = int(doc.page_count)
            sizes: list[str] = []
            dpis: list[float] = []
            sample = list(doc.pages(min(doc.page_count, 8)))
            for page in sample:
                w_mm, h_mm = page.rect.width * 25.4 / 72, page.rect.height * 25.4 / 72
                sizes.append(f"{w_mm:.1f}x{h_mm:.1f}")
                infos = page.get_image_info()
                if infos:
                    info = max(infos, key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]))
                    bw = max(info["bbox"][2] - info["bbox"][0], 1e-6)
                    dpis.append(info["width"] / (bw / 72))
            out["page_mm"] = max(set(sizes), key=sizes.count) if sizes else None
            if dpis:
                dpis.sort()
                out["scan_dpi"] = int(round(dpis[len(dpis) // 2]))
    except Exception:
        return {"page_count": None, "page_mm": None, "scan_dpi": None}
    return out


def iter_pdfs(roots: list[Path], include_small: bool) -> tuple[list[Path], int]:
    found, skipped = [], 0
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            print(f"WARN 扫描根不存在，跳过：{root}", file=sys.stderr)
            continue
        for p in sorted(root.rglob("*.pdf")) + sorted(root.rglob("*.PDF")):
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            if p.name.lower() == "tmp.pdf":
                # 仓根临时副本（实测 sha ≡《黄牧甫印谱》）——物理迁入【1】但不重复入册，
                # 避免「搬移仲裁」把在册行错指到 tmp 名下（去重口径见 docs/output-layout-v0.1.md）。
                skipped += 1
                continue
            if not include_small and p.stat().st_size < MIN_BYTES:
                skipped += 1
                continue
            found.append(p)
    return sorted(found), skipped


def rel_to_repo(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF 资料登记扫描（幂等 by sha256）")
    ap.add_argument("--root", action="append", default=[], help="追加扫描根（可多次；缺省＝pdf_source_dir）")
    ap.add_argument("--register-missing", action="append", default=[], metavar="FILENAME",
                    help="登记「已收录未寻获」的书名（可多次；与 --notes 配合）")
    ap.add_argument("--notes", default=None, help="随 --register-missing 写入的说明")
    ap.add_argument("--include-small", action="store_true", help="不跳过 <100KB 的 pdf（默认跳过）")
    args = ap.parse_args()

    source_rel = pdf_source_dir()
    roots = [REPO / source_rel] + [Path(r).expanduser().resolve() for r in args.root]
    pdfs, skipped = iter_pdfs(roots, args.include_small)

    conn = ensure_db()
    summary: dict = {"db": str(DB_PATH),
                     "roots": [rel_to_repo(r) for r in roots], "scanned": len(pdfs),
                     "skipped_small": skipped, "insert": [], "moved": [], "update": [],
                     "noop": [], "duplicate": []}
    try:
        for p in pdfs:
            rel = rel_to_repo(p)
            info = probe_pdf(p)
            # dir_key ＝ 相对扫描根的直接子目录名（平铺在根下 ⇒ None）
            root = next((r for r in roots if p.is_relative_to(r)), REPO)
            dir_key = None
            try:
                pr = p.parent.relative_to(root)
                dir_key = pr.parts[0] if pr.parts else None
            except ValueError:
                dir_key = None
            action, row = apply_scan_row(
                conn,
                filename=p.name, rel_path=rel, sha256=sha256_of(p),
                size_bytes=p.stat().st_size,
                page_count=info["page_count"], page_mm=info["page_mm"], scan_dpi=info["scan_dpi"],
                dir_key=dir_key, notes=args.notes,
            )
            summary[action].append({"filename": p.name, "rel_path": rel, "sha8": row["sha256"][:8],
                                    "page_count": row["page_count"], "page_mm": row["page_mm"],
                                    "scan_dpi": row["scan_dpi"], "status": row["status"]})
            print(f"[{action:9s}] {rel}  sha8={row['sha256'][:8]}  pages={row['page_count']}  "
                  f"mm={row['page_mm']}  dpi={row['scan_dpi']}  dir_key={row['dir_key']}")

        for name in args.register_missing:
            action, row = register_missing(conn, name, notes=args.notes)
            summary.setdefault("missing", []).append({"filename": name, "action": action, "id": row["id"]})
            print(f"[missing:{action}] {name} (id={row['id']})")
    finally:
        conn.close()

    print("\n== summary ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n朝代值域（15，PATCH 校验用）：{' / '.join(DYNASTY_OPTIONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
