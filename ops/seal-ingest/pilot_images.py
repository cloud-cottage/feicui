#!/usr/bin/env python
"""印章影像下载 pilot：取 60 张，分别量并发 1 / 4 / 8 的成功率与 429/5xx。

证据落 ops/seal-ingest/02_image_pilot.json。**先量后跑**，据此定全量节奏。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from app import seals            # noqa: E402
from app.config import get_settings  # noqa: E402

OUT = Path(__file__).resolve().parent / "02_image_pilot.json"


def pick_refs(n=60):
    st = get_settings()
    refs = seals.collect_image_refs(st.seals_db_path)
    # 跳过源侧无图；按 kind 分层抽样（yt 多为常态；ytsw / yzbk 各取若干）
    by = {"yt": [], "ytsw": [], "yzbk": []}
    for (sid, kind, ref) in refs:
        if ref.startswith("NaN_"):
            continue
        by.setdefault(kind, []).append((sid, kind, ref))
    mix = by["yt"][:40] + by["ytsw"][:15] + by["yzbk"][:5]
    return mix[:n]


def one(url, timeout=30.0):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"Accept": "image/*", "User-Agent": "feicui-seal-pilot/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return {"ok": True, "status": resp.status, "bytes": len(data),
                    "latency": round(time.time() - t0, 3)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "latency": round(time.time() - t0, 3), "kind": "http"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "latency": round(time.time() - t0, 3),
                "kind": type(exc).__name__, "error": str(exc)[:120]}


def run_batch(refs, base, workers, sleep_s):
    """并发 workers；每张前/后按 sleep_s 节流（串行 sleep 用 token 桶近似）。"""
    urls = [(sid, kind, ref, seals.image_url(base, ref)) for (sid, kind, ref) in refs]
    results = []
    t0 = time.time()

    if workers == 1:
        for (sid, kind, ref, url) in urls:
            r = one(url)
            r.update({"seqid": sid, "kind": kind})
            results.append(r)
            time.sleep(sleep_s)
    else:
        # 有 sleep 的并发：分批派发，批内并发，批间 sleep
        batch = max(1, workers)
        for i in range(0, len(urls), batch):
            chunk = urls[i:i + batch]
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(one, u[3]) for u in chunk]
                for (u, f) in zip(chunk, futs):
                    r = f.result()
                    r.update({"seqid": u[0], "kind": u[1]})
                    results.append(r)
            time.sleep(sleep_s)

    wall = round(time.time() - t0, 3)
    ok = sum(1 for r in results if r["ok"])
    r429 = sum(1 for r in results if r.get("status") == 429)
    r5xx = sum(1 for r in results if r.get("status") and 500 <= r["status"] < 600)
    other_fail = len(results) - ok - r429 - r5xx
    lats = [r["latency"] for r in results]
    return {
        "workers": workers, "sleep_s": sleep_s, "n": len(results),
        "ok": ok, "fail": len(results) - ok, "rate_429": r429, "rate_5xx": r5xx,
        "other_fail": other_fail, "success_rate": round(ok / len(results), 4),
        "wall_s": wall, "throughput_img_s": round(len(results) / wall, 3) if wall else None,
        "latency_avg": round(statistics.mean(lats), 3) if lats else None,
        "latency_p95": round(sorted(lats)[int(len(lats) * 0.95) - 1], 3) if lats else None,
    }


def main():
    st = get_settings()
    refs = pick_refs(60)
    print(f"pilot refs: {len(refs)} (kinds: "
          f"{ {k: sum(1 for r in refs if r[1]==k) for k in ('yt','ytsw','yzbk')} })", flush=True)
    out = {"source_base": st.seals_source_base, "n_refs": len(refs),
           "targets_per_ref": 1, "note": "只用原生裁切 /full/0/default.jpg（跟跳转）", "runs": []}
    for (workers, sleep_s) in ((1, 1.5), (4, 0.3), (8, 0.1)):
        res = run_batch(refs, st.seals_source_base, workers, sleep_s)
        print(json.dumps(res, ensure_ascii=False), flush=True)
        out["runs"].append(res)
        time.sleep(5)  # 批间留冷间隔
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", OUT)


if __name__ == "__main__":
    main()
