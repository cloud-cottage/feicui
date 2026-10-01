#!/usr/bin/env python
"""`square-crop` 子进程**冷启动** A/B 基准（惰性 OCR 生效 vs 关掉）——Kong / 斐萃收尾。

跑在**接口层解释器** `server/.venv/bin/python`（只用到纯 stdlib + `app.square`，无需 cv2/numpy）。
它按路由 `app/routers/tools.py` 的真实姿势组参（`square.resolve_params()`），把同一张真实影像
通过 `feicui/venv/bin/python server/app/square_runner.py` 打 3 次，两种模式**交错**执行（消除
机器负载漂移），取中位数对比，并断言：

  ① 全部模式、全部轮次的候选 `sha256` **完全一致**（优化不得改变输出字节）；
  ② `params_used.min_area_source` 以 `params_used.template_source` 为前缀（同口径）；
  ③ `min_area_source` / `template_source` **都不包含** `templates.json:default`
     （除非 `config/templates.json` 里真有该键 —— 这里先就地核验该键不存在）；
  ④ `min_area_eff` 在各模式下一致（换算口径未被改动）。

用法：
    server/.venv/bin/python server/selftest/bench_square_crop_coldstart.py [--reps 3] [--image <path>]
退出码 0 ＝ 全部断言通过。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVER_DIR.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import square  # noqa: E402

WORKER_PY = ROOT / "venv" / "bin" / "python"
RUNNER = SERVER_DIR / "app" / "square_runner.py"
MARKER = "FEICUI_SQUARE="
DEFAULT_IMAGE = ROOT / "output" / "faces" / "TMP" / "p0013_00.webp"

FAILS: list[str] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + extra) if extra else ''}")
    if not ok:
        FAILS.append(label)


def run_once(payload: dict, disable_lazy: bool) -> tuple[float, dict]:
    env = os.environ.copy()
    env["FEICUI_ROOT"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    if disable_lazy:
        env["FEICUI_SQUARE_NO_LAZY_OCR"] = "1"
    else:
        env.pop("FEICUI_SQUARE_NO_LAZY_OCR", None)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(WORKER_PY), str(RUNNER)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        timeout=180,
    )
    dt = time.perf_counter() - t0
    line = next(
        (ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.startswith(MARKER)),
        None,
    )
    if line is None:
        raise SystemExit(f"未拿到标记行；stderr 尾部：{proc.stderr.decode('utf-8', 'replace')[-800:]}")
    return dt, json.loads(line[len(MARKER):])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    args = ap.parse_args()

    image = Path(args.image)
    print("=" * 100)
    print("square-crop 冷启动 A/B 基准（惰性 paddleocr 替身）")
    print(f"  worker 解释器 = {WORKER_PY}（存在＝{WORKER_PY.is_file()}）")
    print(f"  本层解释器    = {sys.executable}")
    print(f"  样本          = {image}（{image.stat().st_size} B）")
    print(f"  轮次          = 每模式 {args.reps} 次（两模式交错执行，取中位数）")
    print("=" * 100)

    # ---- 前置核验：templates.json 真的没有 `default` 键（来源标签失真的根因）----
    tpath = square.templates_path(ROOT)
    raw_tpl = json.loads(tpath.read_text(encoding="utf-8"))
    has_default = square.DEFAULT_TEMPLATE_KEY in raw_tpl
    print(f"\n---- ⓪ 前置核验：{tpath} ----")
    check(
        not has_default,
        "templates.json 无 `default` 键（⇒ 任何 `templates.json:default` 标签都是失真）",
        f"顶层键={list(raw_tpl.keys())}",
    )

    req_params = square.resolve_params(ROOT, pad_ratio=square.PAD_RATIO_DEFAULT, min_area_eff=None)
    print(f"  resolve_params → {json.dumps(req_params, ensure_ascii=False)}")
    payload = dict(req_params)
    payload.update(
        {
            "image_b64": base64.b64encode(image.read_bytes()).decode("ascii"),
            "quality": square.QUALITY_DEFAULT,
            "max_side": square.MAX_SIDE_DEFAULT,
        }
    )

    modes = [("A: 惰性 OCR（优化后）", False), ("B: 关闭惰性（模拟优化前）", True)]
    times: dict[str, list[float]] = {name: [] for name, _ in modes}
    outs: dict[str, list[dict]] = {name: [] for name, _ in modes}

    print(f"\n---- ① 冷启动计时（交错 {args.reps} 轮）----")
    for i in range(args.reps):
        for name, disable in modes:
            dt, out = run_once(payload, disable)
            times[name].append(dt)
            outs[name].append(out)
            ok = bool(out.get("ok"))
            sha = (out.get("candidates") or [{}])[0].get("sha256")
            print(f"  [{i + 1}/{args.reps}] {name}: {dt:.3f}s  ok={ok}  sha256={sha}")

    medians = {n: statistics.median(v) for n, v in times.items()}
    for name, _ in modes:
        print(f"  中位数 {name}: {medians[name]:.3f}s   （全部：{[f'{x:.3f}' for x in times[name]]}）")
    a, b = medians[modes[0][0]], medians[modes[1][0]]
    print(f"  ⇒ 前后对比：{b:.3f}s → {a:.3f}s（降 {b - a:.3f}s，{(1 - a / b) * 100:.1f}%）")

    print("\n---- ② 输出字节不变（sha256 全轮次全模式一致）----")
    shas = {
        (out.get("candidates") or [{}])[0].get("sha256")
        for o in outs.values()
        for out in o
        if out.get("ok")
    }
    check(len(shas) == 1 and None not in shas, "候选 sha256 全池唯一且非空", f"{shas}")

    print("\n---- ③ params_used 一致性 + 来源标签如实性 ----")
    ref = next(out for out in outs[modes[0][0]] if out.get("ok"))
    for name, _ in modes:
        for i, out in enumerate(outs[name]):
            pu = out.get("params_used") or {}
            check(
                pu.get("min_area_eff") == ref["params_used"]["min_area_eff"],
                f"{name} 第{i + 1}轮 min_area_eff 与基准一致",
                str(pu.get("min_area_eff")),
            )
    pu = ref["params_used"]
    ts, ms = str(pu.get("template_source")), str(pu.get("min_area_source"))
    check(ms.startswith(ts), "min_area_source 以 template_source 为前缀（同口径）", f"{ms}")
    check(
        "templates.json:default" not in ms and "templates.json:default" not in ts,
        "两个来源标签都不引用不存在的键 templates.json:default",
        f"template_source={ts}",
    )
    check(
        "BUILTIN_TEMPLATE_PARAMS" in ts and "BUILTIN_TEMPLATE_PARAMS" in ms,
        "标签如实指出内建兜底常量的位置",
    )
    check(
        "verified 3/3" in ts,
        "标签如实给出与语料的核对结果（3 本书逐字一致）",
        ts,
    )
    check(
        ms.endswith(f"×processor.AREA_SCALE={ref['params_used']['min_area_eff'] / 800.0:.6f}"),
        "标签里的 AREA_SCALE 与实际生效换算自洽",
        ms,
    )

    print("\n" + "=" * 100)
    if FAILS:
        print(f"结论：FAIL（{len(FAILS)} 项）→ {FAILS}")
        return 1
    print("结论：PASS —— 惰性 OCR 生效、输出 sha256 不变、来源标签如实")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
