#!/usr/bin/env python
"""ops/ocr-rapid · 用待评估引擎在**同一 248 枚印面池**上跑读数（逐件独立子进程 + 幂等落账）。

纪律（本仓硬约束，见 `local-dist/build/README.md` §2.1）：
  - **一件一子进程**：driver 只负责起进程与记账；每个进程只处理 **1 枚** crop 就退出
    （历史实测：原生推理栈在同进程反复建立/释放上下文会 SIGSEGV）。
  - **幂等落账**：结果逐行 append 到 JSONL，`(stem, config)` 已存在即跳过 ⇒ 中断可续跑。
  - 不碰 `output/`、`server/`、`web/`、`~/bistro/data/yinpu.db`。

配置（与 `labeling/raw/abc_all_248.json` 对齐，便于同类比）：
  - `pipeline`  : det + cls + rec（RapidOCR 默认管线）—— 对应历史 A/B 的形态
  - `rec_only`  : 关 det/cls，整枚 crop 直接喂 rec —— 直接对应历史 **C_rec_only**

跑法：
    ./venv/bin/python ops/ocr-rapid/run_rapid.py --run --configs pipeline,rec_only --jobs 4
    ./venv/bin/python ops/ocr-rapid/run_rapid.py --report          # 汇总 → readings JSON
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
CROPS = HERE / "var" / "crops"
JSONL = RAW / "rapid_pool.jsonl"
MANIFEST = REPO / "spike-ocr" / "raw" / "corpus_manifest.json"
PP_ABC = REPO / "labeling" / "raw" / "abc_all_248.json"
READINGS = REPO / "local-dist" / "build" / "readings-ocr-rapid.json"
PY = REPO / "venv" / "bin" / "python"
WORKER = Path(__file__).resolve()
SELF = str(WORKER)

CONFIGS = {
    "pipeline": {"Global.use_det": True, "Global.use_cls": True, "Global.use_rec": True},
    "rec_only": {"Global.use_det": False, "Global.use_cls": False, "Global.use_rec": True},
}


def _worker(npy: str, cfg: str) -> int:
    """子进程体：跑 1 枚，把结果以 @@JSON@@ 单行打给父进程。"""
    sys.path.insert(0, str(REPO / "local-dist"))
    import numpy as np
    from src.ocr_rapid import ocr_image, get_engine

    img = np.load(npy)
    t0 = time.perf_counter()
    eng = get_engine(CONFIGS[cfg])
    init = time.perf_counter() - t0
    t1 = time.perf_counter()
    r = ocr_image(img, eng=eng)
    infer = time.perf_counter() - t1
    rec = {"stem": Path(npy).stem, "config": cfg, "kind": Path(npy).parent.name,
           "texts": r["texts"], "scores": [round(s, 6) for s in r["scores"]],
           "boxes": r["boxes"], "n_lines": r["n_lines"],
           "scores_max": (max(r["scores"]) if r["scores"] else None),
           "scores_mean": (round(sum(r["scores"]) / len(r["scores"]), 6) if r["scores"] else None),
           "init_s": round(init, 4), "infer_s": round(infer, 4),
           "shape": list(img.shape)}
    print("@@JSON@@" + json.dumps(rec, ensure_ascii=False), flush=True)
    return 0


def done_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                keys.add((r["stem"], r["config"]))
    return keys


def run(configs: list[str], jobs: int, limit: int | None, kinds: list[str]) -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stems = [c["stem"] for c in man["crops"]]
    if limit:
        stems = stems[:limit]
    RAW.mkdir(parents=True, exist_ok=True)
    have = done_keys()
    todo = [(s, k, c) for c in configs for k in kinds for s in stems
            if (s, c) not in have and (CROPS / k / f"{s}.npy").exists()]
    print(f"[run] stems={len(stems)} kinds={kinds} configs={configs} todo={len(todo)} "
          f"(already done={len(have)}) jobs={jobs}", flush=True)

    lock_lines: list[str] = []

    def one(item):
        s, k, c = item
        p = subprocess.run([str(PY), SELF, "--one", str(CROPS / k / f"{s}.npy"), "--config", c],
                           capture_output=True, text=True)
        for line in p.stdout.splitlines():
            if line.startswith("@@JSON@@"):
                return line[len("@@JSON@@"):]
        return json.dumps({"stem": s, "config": c, "kind": k, "error":
                           (p.stderr or p.stdout or "no output")[-400:]}, ensure_ascii=False)

    t0 = time.perf_counter()
    n = 0
    with JSONL.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=jobs) as ex:
        for res in ex.map(one, todo):
            fh.write(res + "\n")
            n += 1
            if n % 25 == 0:
                fh.flush()
                print(f"[run] {n}/{len(todo)} ({time.perf_counter()-t0:.0f}s)", flush=True)
    print(f"[run] wrote {n} rows -> {JSONL} in {time.perf_counter()-t0:.0f}s", flush=True)
    return 0


def _rate(xs: int, n: int) -> float:
    return round(xs / n, 4) if n else 0.0


def report() -> int:
    rows = [json.loads(l) for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    order = [c["stem"] for c in man["crops"]]
    pp = json.loads(PP_ABC.read_text(encoding="utf-8"))
    pprows = {c["stem"]: c for c in pp["crops"]}

    def agg(kind: str, cfg: str) -> dict:
        rs = [r for r in rows if r["kind"] == kind and r["config"] == cfg and "error" not in r]
        errs = [r for r in rows if r["kind"] == kind and r["config"] == cfg and "error" in r]
        n = len(rs)
        joined = {r["stem"]: "".join(r["texts"]) for r in rs}
        nonempty = [s for s in order if joined.get(s)]
        scores = [r["scores_mean"] for r in rs if r["scores_mean"] is not None]
        maxs = [r["scores_max"] for r in rs if r["scores_max"] is not None]
        cmp_pp, cmp_c = {}, {}
        for tag, field in (("A_baseline", "A"), ("B_no_doc", "B"), ("C_rec_only", "C")):
            same = both_ne = differ_both = rapid_only = pp_only = both_empty = 0
            for s in order:
                if s not in joined:
                    continue
                a, b = joined[s] or "", pprows[s].get(field) or ""
                if a == b:
                    same += 1
                    both_ne += 1 if a else 0
                    both_empty += 1 if not a else 0
                elif a and b:
                    differ_both += 1
                elif a:
                    rapid_only += 1
                else:
                    pp_only += 1
            d = {"both_empty": both_empty, "exact_same": same, "exact_same_nonempty": both_ne,
                 "both_nonempty_but_diff": differ_both,
                 "rapid_only_nonempty": rapid_only, "pp_only_nonempty": pp_only}
            (cmp_c if field == "C" else cmp_pp)[tag] = d
        return {
            "kind": kind, "config": cfg, "n": n, "n_error": len(errs),
            "n_nonempty": len(nonempty), "nonempty_rate": _rate(len(nonempty), len(order)),
            "empty_stems": [s for s in order if not joined.get(s)],
            "mean_item_score": (round(statistics.fmean(scores), 4) if scores else None),
            "mean_item_score_over_nonempty": round(statistics.fmean(scores), 4) if scores else None,
            "mean_item_max_score": round(statistics.fmean(maxs), 4) if maxs else None,
            "n_lines_total": sum(r["n_lines"] for r in rs),
            "median_infer_s": round(statistics.median([r["infer_s"] for r in rs]), 3) if rs else None,
            "median_init_s": round(statistics.median([r["init_s"] for r in rs]), 3) if rs else None,
            "cmp_vs_pp": {**cmp_pp, **cmp_c},
            "texts": {s: joined[s] for s in order if s in joined},
            "scores": {r["stem"]: r["scores_mean"] for r in rs},
            "errors": [{"stem": r["stem"], "error": r["error"]} for r in errs[:5]],
        }

    kinds = sorted({r["kind"] for r in rows})
    cfgs = sorted({r["config"] for r in rows})
    out = {
        "schema": "feicui.ocr-rapid.readings.v1",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "engine": {"package": "rapidocr", "version": "3.10.0", "backend": "onnxruntime 1.31.0",
                   "models": ["PP-OCRv6_det_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
                              "PP-OCRv6_rec_small.onnx"],
                   "models_bundled_in_wheel": True},
        "pool": {"manifest": str(MANIFEST), "n": man["n_stamps"],
                 "crops_rebuilt_pixel_identical": True,
                 "rebuild_evidence": str(HERE / "var" / "pool_rebuild.json")},
        "pp_baseline_ref": {"source": str(PP_ABC),
                            "C_rec_only_nonempty": "128/248=51.6%", "C_rec_only_mean_score": 0.2113,
                            "A_median_ms": 758.6, "B_median_ms": 418.9, "C_median_ms": 57.4},
        "seal_248": {f"{k}:{c}": agg(k, c) for k in kinds for c in cfgs},
        "jsonl": str(JSONL),
    }
    READINGS.parent.mkdir(parents=True, exist_ok=True)
    READINGS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    slim = {k: {kk: vv for kk, vv in v.items() if kk not in ("texts", "scores", "empty_stems")}
            for k, v in out["seal_248"].items()}
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print(f"[report] wrote {READINGS}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--config", default="pipeline")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--configs", default="pipeline,rec_only")
    ap.add_argument("--kinds", default="stamp")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.one:
        return _worker(a.one, a.config)
    if a.run:
        return run(a.configs.split(","), a.jobs, a.limit or None, a.kinds.split(","))
    if a.report:
        return report()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
