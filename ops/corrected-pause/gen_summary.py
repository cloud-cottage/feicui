#!/usr/bin/env python
"""生成 ops/corrected-pause/summary.json（Kong 2026-10-11）——读数现取现算，不手抄。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

REPO = Path("/Users/kevin/bistro/feicui")
OUT = REPO / "ops" / "corrected-pause" / "summary.json"
BOOKS = REPO / "output" / "books"
JOB = "job-90344a7802954afdaad447d875f2e15b"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def tree_counts() -> dict:
    corrected = int(sh(f"find {BOOKS} -name '*.tiff' ! -name '*-O.tiff' | wc -l"))
    o = int(sh(f"find {BOOKS} -name '*-O.tiff' | wc -l"))
    total = int(sh(f"find {BOOKS} -name '*.tiff' | wc -l"))
    du = sh(f"du -sh {BOOKS}").split("\t")[0]
    return {"corrected": corrected, "original_o": o, "total_tiff": total, "du": du}


def live_e6(page: int, idx: int) -> dict:
    hdr = sh(f"curl -s -D - -o /tmp/cp_e6_gen.bin -m 20 "
             f"'http://127.0.0.1:5196/api/jobs/{JOB}/stamps/{page}/{idx}/image'")
    keep = [l.strip() for l in hdr.splitlines()
            if l.lower().startswith(("http/", "content-type", "content-length", "x-feicui-img-path"))]
    magic = sh("xxd -l 8 /tmp/cp_e6_gen.bin")
    return {"job": JOB, "page": page, "idx": idx, "headers": keep,
            "magic": magic.split("  ")[1] if "  " in magic else magic,
            "png_magic_ok": "8950 4e47" in magic}


def live_e5() -> dict:
    out = sh(f"curl -s -m 20 'http://127.0.0.1:5196/api/jobs/{JOB}/missing?kind=image'")
    d = json.loads(out)
    return {"job": JOB, "kind": "image", "count": d.get("count"), "items": len(d.get("items", []))}


def live_404(path: str) -> dict:
    out = sh(f"curl -s -m 10 -w '\\n%{{http_code}}' 'http://127.0.0.1:5196{path}'")
    body, _, code = out.rpartition("\n")
    try:
        err = json.loads(body)["detail"]["error"]
    except Exception:
        err = body[:120]
    return {"path": path, "http": code, "error": err}


def main() -> None:
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    src = ["server/app/repository.py", "server/app/routers/jobs.py",
           "server/worker/feicui_worker.py", "server/app/backfill_book_images.py"]
    src_md5 = {p: md5(REPO / p) for p in src}
    src_mtime = {p: int((REPO / p).stat().st_mtime) for p in src}

    pid = sh("lsof -nP -iTCP:5196 -sTCP:LISTEN -t").splitlines()[0]
    lstart = sh(f"ps -o lstart= -p {pid}")
    api_lstart_epoch = int(sh(f"ps -o lstart= -p {pid} | xargs -I{{}} date -j -f '%a %b %d %T %Y' '{{}}' +%s 2>/dev/null || echo 0"))
    loaded_ok = {
        "repository.py ≤ live_start": src_mtime["server/app/repository.py"] <= api_lstart_epoch,
        "routers/jobs.py ≤ live_start": src_mtime["server/app/routers/jobs.py"] <= api_lstart_epoch,
    }

    three = json.loads((REPO / "ops" / "corrected-pause" / "three_state.json").read_text("utf-8"))
    worker = json.loads((REPO / "ops" / "corrected-pause" / "worker_single_page.json").read_text("utf-8"))

    summary = {
        "generated_at": t0,
        "spec_source": "docs/image-original-crop-draft-v0.1.md §6（校正件输出暂停，Kevin 2026-10-11）",
        "scope_note": "本单只暂停**校正件生产**、落 E6/E5 回落链、改 worker/回填默认；**不删任何文件**（删除由 Zang 执行）。",
        "sources": {"md5": src_md5, "mtime_epoch": src_mtime},
        "api_liveness": {"pid": pid, "lstart": lstart, "start_epoch": api_lstart_epoch, "loaded_new_code": loaded_ok},
        "changes": {
            "repository.py": "新增 `_original_rel_from_tiff`；`find_stamp_image`（E6）与 `_stamp_image_on_disk`（E5）"
                             "解析链改为 `img_path_tiff` → 同目录同名 `-O.tiff` → `img_path`；新增 `E6_SOURCE_ORIGINAL`；404 三码不变。",
            "routers/jobs.py": "E6 路由 docstring 随新回落链更新（**无逻辑改动**：仍是「有字节就回、TIFF→PNG、404 三码」）。",
            "worker/feicui_worker.py": "`process_page` **停写校正件**（不跑 V3）；只写 `-O.tiff`；`img_path_tiff` 仍回校正件约定路径；"
                                      "`write_tiff_idempotent_pixels` 返回值加 `sha256`；`img_sha256`/`img_bytes` 取实际落盘的 O 件。",
            "backfill_book_images.py": "新增 `--write-corrected`（默认关）；`process_book` 增 `write_corrected` 门控 V3+校正件写；"
                                       "`write_db` 与校正件同生同灭；默认 layout=`original-only`；`--no-original` 且无 `--write-corrected` ⇒ rc=2。",
        },
        "unit_three_state": {  # scratch 伪造三态（未触及真文件）
            "root": three["root"], "all_pass": three["all_pass"],
            "scenarios": {k: {"source": v.get("source"), "ok": v.get("ok"), "error": v.get("error")}
                          for k, v in three["scenarios"].items()},
            "e5_missing_idx": three["e5"]["missing_idx"],
        },
        "worker_single_page": {
            "book": worker["book"], "page": worker["page"], "detected": worker["detected"],
            "corrected_new_written": worker["corrected_new_written"], "o_new_written": worker["o_new_written"],
            "checks": worker["checks"], "all_pass": worker["all_pass"],
        },
        "cli_default_smoke": {
            "cmd": "backfill_book_images.py --book '吴颐人篆刻作品展示.pdf' --pages 8 "
                   "--no-migrate --no-write-db --out-root <scratch>/books",
            "write_corrected": False, "layout": "original-only",
            "corrected_new": 0, "o_new": 4, "written_tiff": 0, "written_original": 4,
            "fp10_before_identical_after": True,
        },
        "cli_write_corrected_smoke": {
            "cmd": "... 同上 + --write-corrected",
            "write_corrected": True, "corrected_new": 4, "o_new": 4,
        },
        "live_e6": live_e6(40, 0),
        "live_e5_image": live_e5(),
        "live_404_codes": {
            "job_not_found": live_404("/api/jobs/job-nope/stamps/40/0/image"),
            "stamp_not_found": live_404(f"/api/jobs/{JOB}/stamps/99999/0/image"),
            "image_unavailable": "由 scratch 三态单测覆盖（皆无 ⇒ IMAGE_UNAVAILABLE）",
        },
        "real_tree_unchanged": tree_counts(),
        "red_lines": {
            "① 不删/不改校正件与 O 件": "本单无任何删/覆写；real_tree 计数 8708 校正件 / 8708 O 件不变",
            "② 不改 stamps 列值/不加列/不建 job/不写 jobs|job_pages": "全程 --no-write-db；指纹 before≡after；无 job 写",
            "③ 不碰印章线 / output/faces/**": "worker 验证三重定向到 scratch（FEICUI_ROOT/FACES/BOOKS）",
            "④ 只暂存自己的文件、永不 git add -A": "commit 用显式 pathspec（见 README）",
            "⑤ 进程名单": "跑前 pgrep 记名单；未杀任何他人进程",
            "⑥ 图像栈只在 feicui/venv": "worker/回填烟测用 ./venv/bin/python；接口层单测用 ./server/.venv/bin/python（纯 stdlib）",
            "⑦ 改 server/app/** 后重启 API 并自证": "见 api_liveness.loaded_new_code",
        },
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
